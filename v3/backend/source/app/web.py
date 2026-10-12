"""Native ASGI HTTP layer for IRIS's synchronous business handlers.

FastAPI owns routing and the ASGI protocol. Werkzeug is used only for its
HTTP data structures, upload parser and URL builder; no WSGI application is
created or called. Each handler's context and cleanup execute in one worker.
"""
from __future__ import annotations

import base64
import hashlib
import importlib
import io
import json
import logging
import os
import re
import sys
import tempfile
import uuid
from contextvars import ContextVar
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from urllib.parse import quote

from fastapi import FastAPI
from itsdangerous import BadSignature, URLSafeTimedSerializer
from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as ASGIHTTPException
from starlette.requests import Request as ASGIRequest
from starlette.routing import Match
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles
from starlette.responses import Response as ASGIResponse, StreamingResponse
from werkzeug.datastructures import Headers
from werkzeug.exceptions import HTTPException, InternalServerError, MethodNotAllowed, RequestEntityTooLarge, default_exceptions
from werkzeug.local import LocalProxy
from werkzeug.routing import Map, Rule
from werkzeug.test import EnvironBuilder
from werkzeug.utils import redirect as _redirect, send_file as _send_file, send_from_directory as _send_from_directory
from werkzeug.wrappers import Request, Response
from werkzeug.http import http_date, parse_date


_app_ctx: ContextVar[AppContext | None] = ContextVar("iris_app_context", default=None)
_request_ctx: ContextVar[RequestContext | None] = ContextVar("iris_request_context", default=None)


def _context_app():
    ctx = _app_ctx.get()
    if ctx is None:
        raise RuntimeError("Working outside of application context")
    return ctx.app


def _context_request():
    ctx = _request_ctx.get()
    if ctx is None:
        raise RuntimeError("Working outside of request context")
    return ctx


class _Globals(SimpleNamespace):
    def get(self, name, default=None):
        return getattr(self, name, default)

    def pop(self, name, default=None):
        return self.__dict__.pop(name, default)

    def setdefault(self, name, default=None):
        return self.__dict__.setdefault(name, default)

    def __contains__(self, name):
        return name in self.__dict__


current_app = LocalProxy(_context_app)
request = LocalProxy(lambda: _context_request().request)
session = LocalProxy(lambda: _context_request().session)
g = LocalProxy(lambda: _app_ctx.get().g if _app_ctx.get() else _context_app())


def has_app_context():
    return _app_ctx.get() is not None


def has_request_context():
    return _request_ctx.get() is not None


class Config(dict):
    def from_object(self, obj):
        if isinstance(obj, str):
            module, _, name = obj.rpartition(".")
            try:
                obj = importlib.import_module(obj)
            except ModuleNotFoundError:
                obj = getattr(importlib.import_module(module), name)
        self.update({key: getattr(obj, key) for key in dir(obj) if key.isupper()})


class SecureCookieSession(dict):
    """Track top-level mutations, matching the existing cookie session API."""
    def __init__(self, values=None):
        super().__init__(values or {})
        self.modified = False
        self.accessed = False
        self.new = False

    def __getitem__(self, key):
        self.accessed = True
        return super().__getitem__(key)

    def get(self, key, default=None):
        self.accessed = True
        return super().get(key, default)

    def __setitem__(self, key, value):
        self.modified = self.accessed = True
        super().__setitem__(key, value)

    def __delitem__(self, key):
        self.modified = self.accessed = True
        super().__delitem__(key)

    def update(self, *args, **kwargs):
        self.modified = self.accessed = True
        super().update(*args, **kwargs)

    def pop(self, *args):
        self.modified = self.accessed = True
        return super().pop(*args)

    def popitem(self):
        self.modified = self.accessed = True
        return super().popitem()

    def clear(self):
        self.modified = self.accessed = True
        super().clear()

    def setdefault(self, key, default=None):
        self.accessed = True
        if key not in self:
            self[key] = default
        return super().__getitem__(key)

    @property
    def permanent(self):
        return self.get("_permanent", False)

    @permanent.setter
    def permanent(self, value):
        self["_permanent"] = bool(value)


class TaggedJSONSerializer:
    """The Flask cookie format: tags and signing parameters remain compatible."""
    tags = {" di", " t", " b", " m", " u", " d"}

    def tag(self, value):
        if isinstance(value, dict):
            if len(value) == 1 and next(iter(value)) in self.tags:
                key = next(iter(value))
                return {" di": {key + "__": self.tag(value[key])}}
            return {key: self.tag(item) for key, item in value.items()}
        if isinstance(value, tuple):
            return {" t": [self.tag(item) for item in value]}
        if isinstance(value, list):
            return [self.tag(item) for item in value]
        if isinstance(value, bytes):
            return {" b": base64.b64encode(value).decode("ascii")}
        if hasattr(value, "__html__"):
            return {" m": str(value.__html__())}
        if isinstance(value, uuid.UUID):
            return {" u": value.hex}
        if isinstance(value, datetime):
            return {" d": http_date(value)}
        return value

    def untag(self, value):
        if isinstance(value, list):
            return [self.untag(item) for item in value]
        if not isinstance(value, dict):
            return value
        if len(value) == 1:
            key, item = next(iter(value.items()))
            if key == " di":
                inner_key, inner_value = next(iter(item.items()))
                return {inner_key[:-2]: self.untag(inner_value)}
            if key == " t":
                return tuple(self.untag(part) for part in item)
            if key == " b":
                return base64.b64decode(item)
            if key == " m":
                return Markup(item)
            if key == " u":
                return uuid.UUID(item)
            if key == " d":
                return parse_date(item)
        return {key: self.untag(item) for key, item in value.items()}

    def dumps(self, value):
        return json.dumps(self.tag(value), separators=(",", ":"), ensure_ascii=True)

    def loads(self, value):
        return self.untag(json.loads(value))


class SessionInterface:
    def get_signing_serializer(self, app):
        secret = app.config.get("SECRET_KEY")
        if not secret:
            return None
        keys = [*(app.config.get("SECRET_KEY_FALLBACKS") or []), secret]
        return URLSafeTimedSerializer(keys, salt="cookie-session", serializer=TaggedJSONSerializer(), signer_kwargs={"key_derivation": "hmac", "digest_method": hashlib.sha1})

    def open_session(self, app, req):
        serializer = self.get_signing_serializer(app)
        cookie = req.cookies.get(app.config["SESSION_COOKIE_NAME"])
        if serializer and cookie:
            try:
                value = serializer.loads(cookie, max_age=int(app.permanent_session_lifetime.total_seconds()))
                if isinstance(value, dict):
                    return SecureCookieSession(value)
            except (BadSignature, ValueError, TypeError):
                pass
        return SecureCookieSession()

    def save_session(self, app, values, response):
        if values.accessed:
            response.vary.add("Cookie")
        name = app.config["SESSION_COOKIE_NAME"]
        cookie_args = dict(path=app.config.get("SESSION_COOKIE_PATH") or "/", domain=app.config.get("SESSION_COOKIE_DOMAIN"), secure=app.config["SESSION_COOKIE_SECURE"], httponly=app.config["SESSION_COOKIE_HTTPONLY"], samesite=app.config["SESSION_COOKIE_SAMESITE"])
        if not values:
            if values.modified:
                response.delete_cookie(name, **cookie_args)
                response.vary.add("Cookie")
            return
        if not (values.modified or (values.permanent and app.config["SESSION_REFRESH_EACH_REQUEST"])):
            return
        serializer = self.get_signing_serializer(app)
        if serializer is None:
            raise RuntimeError("SECRET_KEY must be configured to save sessions")
        expires = datetime.now(timezone.utc) + app.permanent_session_lifetime if values.permanent else None
        response.set_cookie(name, serializer.dumps(dict(values)), expires=expires, **cookie_args)
        response.vary.add("Cookie")


class AppContext:
    def __init__(self, app):
        self.app = app
        self.g = _Globals()
        self.tokens = []

    def push(self):
        self.tokens.append(_app_ctx.set(self))

    def pop(self, exc=None):
        try:
            if len(self.tokens) == 1:
                for callback in reversed(self.app.teardown_appcontext_funcs):
                    callback(exc)
        finally:
            _app_ctx.reset(self.tokens.pop())

    def __enter__(self):
        self.push()
        return self

    def __exit__(self, kind, value, traceback):
        self.pop(value)


class RequestContext:
    def __init__(self, app, req):
        self.app = app
        self.request = req
        self.session = app.session_interface.open_session(app, req)
        self.flashes = None
        self.app_context = None
        self.after_callbacks = []

    def push(self):
        if not has_app_context() or current_app._get_current_object() is not self.app:
            self.app_context = self.app.app_context()
            self.app_context.push()
        self.token = _request_ctx.set(self)

    def pop(self, exc=None):
        try:
            for callback in reversed(self.app.teardown_request_funcs.get(None, [])):
                callback(exc)
        finally:
            _request_ctx.reset(self.token)
            if self.app_context is not None:
                self.app_context.pop(exc)

    def __enter__(self):
        self.push()
        return self

    def __exit__(self, kind, value, traceback):
        self.pop(value)


def _root_path(import_name):
    module = sys.modules.get(import_name)
    filename = getattr(module, "__file__", None)
    if filename:
        return os.path.dirname(os.path.abspath(filename))
    spec = importlib.util.find_spec(import_name) if import_name != "__main__" else None
    if spec and spec.origin:
        return os.path.dirname(os.path.abspath(spec.origin))
    return os.getcwd()


class Blueprint:
    def __init__(self, name, import_name, template_folder=None, static_folder=None, static_url_path=None, url_prefix=None, root_path=None, **kwargs):
        self.name, self.import_name = name, import_name
        self.root_path = root_path or _root_path(import_name)
        self.template_folder = template_folder
        self.static_folder = os.path.join(self.root_path, static_folder) if static_folder else None
        self.static_url_path = static_url_path or ("/" + os.path.basename(self.static_folder) if self.static_folder else None)
        self.url_prefix = url_prefix or ""
        self.routes = []
        self.children = []
        self.before_request_funcs = []
        self.after_request_funcs = []
        self.context_processors = []
        self.error_handlers = {}
        self.app_error_handlers = {}

    def route(self, rule, **options):
        def decorate(func):
            self.add_url_rule(rule, view_func=func, **options)
            return func
        return decorate

    def get(self, rule, **options):
        return self.route(rule, methods=["GET"], **options)

    def post(self, rule, **options):
        return self.route(rule, methods=["POST"], **options)

    def put(self, rule, **options):
        return self.route(rule, methods=["PUT"], **options)

    def patch(self, rule, **options):
        return self.route(rule, methods=["PATCH"], **options)

    def delete(self, rule, **options):
        return self.route(rule, methods=["DELETE"], **options)

    def head(self, rule, **options):
        return self.route(rule, methods=["HEAD"], **options)

    def options(self, rule, **options):
        return self.route(rule, methods=["OPTIONS"], **options)

    def add_url_rule(self, rule, endpoint=None, view_func=None, **options):
        self.routes.append((rule, endpoint or view_func.__name__, view_func, options))

    def register_blueprint(self, blueprint, **options):
        self.children.append((blueprint, options))

    def before_request(self, func):
        self.before_request_funcs.append(func)
        return func

    def after_request(self, func):
        self.after_request_funcs.append(func)
        return func

    def context_processor(self, func):
        self.context_processors.append(func)
        return func

    def errorhandler(self, code):
        def decorate(func):
            self.error_handlers[code] = func
            return func
        return decorate

    def app_errorhandler(self, code):
        def decorate(func):
            self.app_error_handlers[code] = func
            return func
        return decorate


def _convert_rule(rule):
    def convert(match):
        converter, name = match.group(1), match.group(2)
        converter = converter or "str"
        converter = {"string": "str"}.get(converter, converter)
        if converter not in {"str", "int", "uuid", "path", "float"}:
            raise ValueError(f"Unsupported URL converter: {converter}")
        return "{" + name + (":" + converter if converter != "str" else "") + "}"
    return re.sub(r"<(?:([^:<>]+):)?([^<>]+)>", convert, rule)


class JSONProvider:
    def __init__(self, app):
        self.app = app

    @staticmethod
    def default(value):
        if isinstance(value, (date, datetime)):
            return http_date(value)
        if isinstance(value, (Decimal, uuid.UUID)):
            return str(value)
        if hasattr(value, "__html__"):
            return str(value.__html__())
        raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")

    def dumps(self, value, **kwargs):
        kwargs.setdefault("default", self.default)
        kwargs.setdefault("ensure_ascii", True)
        kwargs.setdefault("sort_keys", True)
        return json.dumps(value, **kwargs)

    def loads(self, value, **kwargs):
        return json.loads(value, **kwargs)

    def response(self, value):
        return Response(self.dumps(value, separators=(",", ":")) + "\n", mimetype="application/json")


class HTTPRequestBufferMiddleware:
    """Spool ASGI input to bounded memory; perform disk I/O in workers."""
    def __init__(self, app, iris_app):
        self.app, self.iris_app = app, iris_app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        body = tempfile.SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b")
        size = 0
        limit = self.iris_app.config.get("MAX_CONTENT_LENGTH")
        oversized = False
        req = None
        try:
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                size += len(chunk)
                if limit is not None and size > limit:
                    oversized = True
                elif not oversized:
                    await run_in_threadpool(body.write, chunk)
                if not message.get("more_body", False):
                    break
            await run_in_threadpool(body.seek, 0)
            req = self.iris_app._request_from_scope(scope, body, size)
            scope["iris.request"] = req
            if oversized:
                response = await run_in_threadpool(self.iris_app._dispatch, req, None, {}, RequestEntityTooLarge())
                return await response(scope, receive, send)
            # The route does not re-read the body, but other ASGI components can.
            delivered = False
            read_offset = 0
            def read_chunk():
                original_position = body.tell()
                try:
                    body.seek(read_offset)
                    return body.read(65536)
                finally:
                    body.seek(original_position)
            async def buffered_receive():
                nonlocal delivered, read_offset
                if not delivered:
                    chunk = await run_in_threadpool(read_chunk)
                    read_offset += len(chunk)
                    delivered = read_offset >= size
                    return {"type": "http.request", "body": chunk, "more_body": not delivered}
                return await receive()
            await self.app(scope, buffered_receive, send)
        finally:
            if req is not None:
                await run_in_threadpool(req.close)
            await run_in_threadpool(body.close)


class IRISApp(FastAPI):
    response_class = Response

    def __init__(self, import_name, static_folder="static", template_folder="templates", fs_root_path=None, **kwargs):
        kwargs.setdefault("docs_url", None)
        kwargs.setdefault("redoc_url", None)
        kwargs.setdefault("openapi_url", None)
        super().__init__(**kwargs)
        self.router.redirect_slashes = False
        self.import_name = import_name
        self.name = import_name
        self.fs_root_path = fs_root_path or _root_path(import_name)
        self.logger = logging.getLogger(import_name)
        self.config = Config(SECRET_KEY=None, SESSION_COOKIE_NAME="session", SESSION_COOKIE_SECURE=True, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_DOMAIN=None, SESSION_COOKIE_PATH=None, SESSION_REFRESH_EACH_REQUEST=True, PERMANENT_SESSION_LIFETIME=timedelta(days=31), PREFERRED_URL_SCHEME="http", SERVER_NAME=None, APPLICATION_ROOT="/", MAX_CONTENT_LENGTH=None, TESTING=False, PROPAGATE_EXCEPTIONS=None)
        self.extensions = {}
        self.blueprints = {}
        self.view_functions = {}
        self.url_map = Map()
        self.session_interface = SessionInterface()
        self.json = JSONProvider(self)
        self.jinja_options = {"autoescape": select_autoescape()}
        self._template_loaders = []
        if template_folder:
            self._template_loaders.append(FileSystemLoader(os.path.join(self.fs_root_path, template_folder)))
        self.jinja_env = Environment(loader=ChoiceLoader(self._template_loaders), **self.jinja_options)
        self.jinja_env.globals.update(request=request, session=session, g=g, config=self.config, url_for=url_for, get_flashed_messages=get_flashed_messages, current_user=LocalProxy(_current_user))
        self.template_context_processors = {None: []}
        self.before_request_funcs = {None: []}
        self.after_request_funcs = {None: []}
        self.teardown_request_funcs = {None: []}
        self.teardown_appcontext_funcs = []
        self.error_handlers = {None: {}}
        self.static_folder = os.path.join(self.fs_root_path, static_folder) if static_folder else None
        self.add_middleware(HTTPRequestBufferMiddleware, iris_app=self)
        self.add_exception_handler(ASGIHTTPException, self._http_exception_handler)
        if self.static_folder:
            self.add_url_rule("/static/<path:filename>", endpoint="static", view_func=lambda filename: send_from_directory(self.static_folder, filename))

    @property
    def secret_key(self):
        return self.config.get("SECRET_KEY")

    def expose_image_store(self, path="images", prefix="/static/assets/images/"):
        """Expose imageattach's filesystem store directly through native ASGI.

        The storage object retains its upstream write and URL semantics. Put
        this route first because the normal static route shares its prefix.
        """
        route = Mount(prefix.rstrip("/"), app=StaticFiles(directory=os.path.abspath(path), check_dir=False), name="image_store")
        self.router.routes.insert(0, route)

    @secret_key.setter
    def secret_key(self, value):
        self.config["SECRET_KEY"] = value

    @property
    def testing(self):
        return self.config["TESTING"]

    @testing.setter
    def testing(self, value):
        self.config["TESTING"] = value

    @property
    def permanent_session_lifetime(self):
        value = self.config["PERMANENT_SESSION_LIFETIME"]
        return value if isinstance(value, timedelta) else timedelta(seconds=value)

    def route(self, rule, **options):
        def decorate(func):
            self.add_url_rule(rule, view_func=func, **options)
            return func
        return decorate

    def add_url_rule(self, rule, endpoint=None, view_func=None, methods=None, defaults=None, **options):
        endpoint = endpoint or view_func.__name__
        self.view_functions[endpoint] = view_func
        methods = set(methods or getattr(view_func, "methods", None) or ["GET"])
        methods = {method.upper() for method in methods}
        if "GET" in methods:
            methods.add("HEAD")
        automatic_options = options.pop("provide_automatic_options", "OPTIONS" not in methods)
        if automatic_options:
            methods.add("OPTIONS")
        self.url_map.add(Rule(rule, endpoint=endpoint, methods=methods, defaults=defaults))
        async def native_endpoint(native_request: ASGIRequest):
            req = native_request.scope["iris.request"]
            req.endpoint = endpoint
            req.blueprint = endpoint.rpartition(".")[0] or None
            req.blueprints = _blueprint_chain(req.blueprint)
            values = dict(defaults or {})
            values.update(native_request.path_params)
            req.view_args = values
            if req.method == "OPTIONS" and automatic_options:
                handler = lambda: Response(headers={"Allow": ", ".join(sorted(self._allowed_methods(req)))}, mimetype="text/html")
                values = {}
            else:
                handler = view_func
            return await run_in_threadpool(self._dispatch, req, handler, values)
        self.add_api_route(_convert_rule(rule), native_endpoint, methods=sorted(methods), name=endpoint, response_model=None, include_in_schema=False)

    def register_blueprint(self, blueprint, **options):
        name = options.pop("name", blueprint.name)
        name_prefix = options.pop("name_prefix", "")
        full_name = ".".join(part for part in [name_prefix, name] if part)
        prefix = options.pop("url_prefix", blueprint.url_prefix) or ""
        self.blueprints[full_name] = blueprint
        self.before_request_funcs[full_name] = blueprint.before_request_funcs
        self.after_request_funcs[full_name] = blueprint.after_request_funcs
        self.template_context_processors[full_name] = blueprint.context_processors
        self.error_handlers[full_name] = blueprint.error_handlers
        self.error_handlers[None].update(blueprint.app_error_handlers)
        if blueprint.template_folder:
            self._template_loaders.append(FileSystemLoader(os.path.join(blueprint.root_path, blueprint.template_folder)))
            self.jinja_env.loader = ChoiceLoader(self._template_loaders)
        if blueprint.static_folder:
            self.add_url_rule(prefix + blueprint.static_url_path + "/<path:filename>", endpoint=full_name + ".static", view_func=lambda filename: send_from_directory(blueprint.static_folder, filename))
        for rule, endpoint, handler, route_options in blueprint.routes:
            self.add_url_rule(prefix + rule, endpoint=full_name + "." + endpoint, view_func=handler, **route_options)
        for child, child_options in blueprint.children:
            child_options = dict(child_options)
            child_options["name_prefix"] = full_name
            child_options["url_prefix"] = prefix + (child_options.get("url_prefix", child.url_prefix) or "")
            self.register_blueprint(child, **child_options)

    def before_request(self, func):
        self.before_request_funcs[None].append(func)
        return func

    def after_request(self, func):
        self.after_request_funcs[None].append(func)
        return func

    def teardown_request(self, func):
        self.teardown_request_funcs[None].append(func)
        return func

    def teardown_appcontext(self, func):
        self.teardown_appcontext_funcs.append(func)
        return func

    def context_processor(self, func):
        self.template_context_processors[None].append(func)
        return func

    def template_filter(self, name=None):
        def decorate(func):
            self.jinja_env.filters[name or func.__name__] = func
            return func
        return decorate

    def errorhandler(self, code):
        def decorate(func):
            self.error_handlers[None][code] = func
            return func
        return decorate

    def app_context(self):
        return AppContext(self)

    def request_context(self, environ):
        req = environ if isinstance(environ, Request) else Request(environ)
        if not hasattr(req, "endpoint"):
            req.endpoint = req.blueprint = None
            req.blueprints = []
            req.view_args = {}
        return RequestContext(self, req)

    def test_request_context(self, *args, **kwargs):
        kwargs.setdefault("base_url", "http://" + (self.config.get("SERVER_NAME") or "localhost"))
        builder = EnvironBuilder(*args, **kwargs)
        try:
            return self.request_context(builder.get_environ())
        finally:
            builder.close()

    def test_client(self, **kwargs):
        return ASGITestClient(self, **kwargs)

    def make_response(self, value):
        status, headers = None, None
        if isinstance(value, tuple):
            if len(value) == 3:
                value, status, headers = value
            elif len(value) == 2:
                value, second = value
                if isinstance(second, (dict, Headers, list, tuple)):
                    headers = second
                else:
                    status = second
            else:
                raise TypeError("Handler tuples must contain two or three values")
        if isinstance(value, (dict, list)):
            response = self.json.response(value)
        elif isinstance(value, Response):
            response = value
        elif isinstance(value, (str, bytes, bytearray)):
            response = self.response_class(value, mimetype="text/html")
        elif value is None:
            raise TypeError("The handler did not return a response")
        else:
            response = self.response_class(value, mimetype="text/html")
        if status is not None:
            if isinstance(status, str):
                response.status = status
            else:
                response.status_code = status
        if headers is not None:
            response.headers.update(headers)
        return response

    def _handle_error(self, error, req):
        for name in [*getattr(req, "blueprints", []), None]:
            handlers = self.error_handlers.get(name, {})
            if isinstance(error, HTTPException) and error.code in handlers:
                return handlers[error.code](error)
            for cls in type(error).__mro__:
                if cls in handlers:
                    return handlers[cls](error)
        if isinstance(error, HTTPException):
            return error.get_response(req.environ)
        self.logger.exception("Unhandled request exception")
        propagate = self.config.get("PROPAGATE_EXCEPTIONS")
        if propagate is True or (propagate is None and self.testing):
            raise error
        error = InternalServerError(original_exception=error)
        handler = self.error_handlers[None].get(500)
        return handler(error) if handler else error.get_response(req.environ)

    def _dispatch(self, req, handler, values, initial_error=None):
        error = None
        ctx = self.request_context(req)
        ctx.push()
        try:
            try:
                result = None
                for name in [None, *reversed(getattr(req, "blueprints", []))]:
                    for before in self.before_request_funcs.get(name, []):
                        result = before()
                        if result is not None:
                            break
                    if result is not None:
                        break
                if result is None:
                    if initial_error is not None:
                        raise initial_error
                    result = handler(**values)
                response = self.make_response(result)
            except Exception as exc:
                error = exc
                response = self.make_response(self._handle_error(exc, req))
            for after in ctx.after_callbacks:
                response = after(response)
            for name in [*getattr(req, "blueprints", []), None]:
                for after in reversed(self.after_request_funcs.get(name, [])):
                    response = after(response)
            self.session_interface.save_session(self, ctx.session, response)
            return self._asgi_response(response, req)
        except Exception as exc:
            error = exc
            raise
        finally:
            ctx.pop(error)

    async def _http_exception_handler(self, native_request, error):
        req = native_request.scope["iris.request"]
        if error.status_code == 404 and not req.path.endswith("/"):
            candidate = dict(native_request.scope)
            candidate["path"] += "/"
            for route in self.router.routes:
                if route.matches(candidate)[0] == Match.FULL:
                    location = req.base_url + "/"
                    if req.query_string:
                        location += "?" + req.query_string.decode("latin-1")
                    return await run_in_threadpool(self._dispatch, req, lambda: redirect(location, 308), {})
        if error.status_code == 405:
            error = MethodNotAllowed(valid_methods=sorted(self._allowed_methods(req)))
        else:
            error = default_exceptions.get(error.status_code, InternalServerError)()
        return await run_in_threadpool(self._dispatch, req, None, {}, error)

    def _allowed_methods(self, req):
        # URL metadata only: actual HTTP route dispatch stays in FastAPI.
        return self.url_map.bind_to_environ(req.environ).allowed_methods(req.path)

    def _asgi_response(self, response, req):
        headers = response.get_wsgi_headers(req.environ)
        if req.method == "HEAD" or response.status_code in {204, 304} or response.status_code < 200:
            response.close()
            native = ASGIResponse(b"", status_code=response.status_code)
        elif response.is_streamed or response.direct_passthrough:
            def chunks():
                try:
                    yield from response.iter_encoded()
                finally:
                    response.close()
            native = StreamingResponse(chunks(), status_code=response.status_code)
        else:
            native = ASGIResponse(response.get_data(), status_code=response.status_code)
            response.close()
        native.raw_headers = [(key.lower().encode("latin-1"), value.encode("latin-1")) for key, value in headers]
        return native

    def _request_from_scope(self, scope, body, content_length=None):
        if isinstance(body, bytes):
            content_length = len(body)
            body = io.BytesIO(body)
        headers = Headers((key.decode("latin-1"), value.decode("latin-1")) for key, value in scope.get("headers", []))
        scheme = headers.get("X-Forwarded-Proto", scope.get("scheme", "http")).split(",")[-1].strip()
        server = scope.get("server") or ("localhost", 80)
        host = headers.get("X-Forwarded-Host", headers.get("Host", f"{server[0]}:{server[1]}")).split(",")[-1].strip()
        prefix = headers.get("X-Forwarded-Prefix", scope.get("root_path", "")).split(",")[-1].strip().rstrip("/")
        req_path = scope.get("path", "/")
        root = scope.get("root_path", "")
        if root and req_path.startswith(root):
            req_path = req_path[len(root):] or "/"
        environ = {"REQUEST_METHOD": scope["method"], "SCRIPT_NAME": prefix, "PATH_INFO": req_path.encode("utf-8").decode("latin-1"), "QUERY_STRING": scope.get("query_string", b"").decode("latin-1"), "SERVER_NAME": server[0], "SERVER_PORT": str(server[1]), "SERVER_PROTOCOL": "HTTP/" + scope.get("http_version", "1.1"), "HTTP_HOST": host, "wsgi.url_scheme": scheme, "wsgi.input": body, "wsgi.errors": sys.stderr, "wsgi.version": (1, 0), "wsgi.multithread": True, "wsgi.multiprocess": False, "wsgi.run_once": False, "CONTENT_LENGTH": str(content_length)}
        for key, value in headers:
            key = key.upper().replace("-", "_")
            if key in {"CONTENT_LENGTH", "HOST"}:
                continue
            if key == "CONTENT_TYPE":
                environ[key] = value
            else:
                environ["HTTP_" + key] = value
        remote = headers.get("X-Forwarded-For", (scope.get("client") or ("", 0))[0]).split(",")[-1].strip()
        environ["REMOTE_ADDR"] = remote
        req = Request(environ)
        req.max_content_length = self.config.get("MAX_CONTENT_LENGTH")
        req.endpoint = req.blueprint = None
        req.blueprints = []
        req.view_args = {}
        return req


Application = IRISApp


def _blueprint_chain(name):
    names = []
    while name:
        names.append(name)
        name = name.rpartition(".")[0]
    return names


def _current_user():
    app = _context_app()
    manager = getattr(app, "login_manager", None)
    if manager is not None and "_login_user" not in g:
        manager._load_user()
    return g.get("_login_user")


def url_for(endpoint, *, _anchor=None, _method=None, _scheme=None, _external=None, **values):
    app = _context_app()
    if has_request_context():
        req = request._get_current_object()
        if endpoint.startswith("."):
            endpoint = (req.blueprint or "") + endpoint
            endpoint = endpoint.lstrip(".")
        adapter = app.url_map.bind_to_environ(req.environ)
        external = bool(_external) if _external is not None else _scheme is not None
    else:
        server_name = app.config.get("SERVER_NAME")
        if not server_name:
            raise RuntimeError("SERVER_NAME is required to build URLs outside a request")
        adapter = app.url_map.bind(server_name, script_name=app.config["APPLICATION_ROOT"], url_scheme=_scheme or app.config["PREFERRED_URL_SCHEME"])
        external = True if _external is None else _external
    result = adapter.build(endpoint, values, method=_method, force_external=external, url_scheme=_scheme)
    if _anchor is not None:
        result += "#" + quote(str(_anchor), safe="%!#$&'()*+,/:;=?@")
    return result


def _template_context(context):
    app = _context_app()
    original = dict(context)
    names = [None]
    if has_request_context():
        names.extend(reversed(request.blueprints))
    for name in names:
        for processor in app.template_context_processors.get(name, []):
            context.update(processor())
    context.update(original)
    return context


def render_template(template_name_or_list, **context):
    app = _context_app()
    return app.jinja_env.get_or_select_template(template_name_or_list).render(_template_context(context))


def render_template_string(source, **context):
    return _context_app().jinja_env.from_string(source).render(_template_context(context))


def after_this_request(callback):
    _context_request().after_callbacks.append(callback)
    return callback


def flash(message, category="message"):
    messages = session.get("_flashes", [])
    messages.append((category, message))
    session["_flashes"] = messages


def get_flashed_messages(with_categories=False, category_filter=()):
    ctx = _context_request()
    if ctx.flashes is None:
        ctx.flashes = session.pop("_flashes", []) if "_flashes" in session else []
    messages = ctx.flashes
    if category_filter:
        messages = [(category, message) for category, message in messages if category in category_filter]
    return messages if with_categories else [message for _, message in messages]


def redirect(location, code=302, Response=Response):
    return _redirect(location, code, Response)


def abort(code, *args, **kwargs):
    if isinstance(code, Response):
        raise HTTPException(response=code)
    raise default_exceptions[code](*args, **kwargs)


def make_response(*args):
    return _context_app().make_response(args[0] if len(args) == 1 else args if args else "")


def jsonify(*args, **kwargs):
    if args and kwargs:
        raise TypeError("Use either positional arguments or keyword arguments")
    return _context_app().json.response(args[0] if len(args) == 1 else list(args) if args else kwargs)


def send_file(path_or_file, **kwargs):
    app = _context_app()
    kwargs.setdefault("response_class", app.response_class)
    kwargs.setdefault("_root_path", app.fs_root_path)
    return _send_file(path_or_file, request.environ, **kwargs)


def send_from_directory(directory, path, **kwargs):
    app = _context_app()
    kwargs.setdefault("response_class", app.response_class)
    kwargs.setdefault("_root_path", app.fs_root_path)
    return _send_from_directory(directory, path, request.environ, **kwargs)


class TestResponse:
    def __init__(self, response):
        self.status_code = response.status_code
        self.data = response.content
        self.headers = Headers(response.headers.multi_items())
        self.content_type = response.headers.get("content-type")
        self.mimetype = (self.content_type or "").split(";", 1)[0]
        self.request = response.request

    def get_data(self, as_text=False):
        return self.data.decode("utf-8") if as_text else self.data

    def get_json(self, force=False, silent=False):
        try:
            return json.loads(self.data)
        except (ValueError, UnicodeError):
            if silent:
                return None
            raise

    @property
    def json(self):
        return self.get_json()


class ASGITestClient:
    """Small Flask-shaped client backed by Starlette's real ASGI TestClient."""
    def __init__(self, app, **kwargs):
        from starlette.testclient import TestClient
        self.app = app
        self.client = TestClient(app, base_url="https://localhost", raise_server_exceptions=True, **kwargs)

    def open(self, path="/", method="GET", follow_redirects=False, **kwargs):
        kwargs.setdefault("base_url", "https://localhost")
        builder = EnvironBuilder(path=path, method=method, **kwargs)
        try:
            environ = builder.get_environ()
            headers = dict(Request(environ).headers)
            body = environ["wsgi.input"].read()
            query = environ.get("QUERY_STRING", "")
            url = environ["wsgi.url_scheme"] + "://" + environ["HTTP_HOST"] + environ.get("SCRIPT_NAME", "") + environ["PATH_INFO"]
            if query:
                url += "?" + query
            return TestResponse(self.client.request(method, url, headers=headers, content=body, follow_redirects=follow_redirects))
        finally:
            builder.close()

    def get(self, path="/", **kwargs):
        return self.open(path, method="GET", **kwargs)

    def post(self, path="/", **kwargs):
        return self.open(path, method="POST", **kwargs)

    def put(self, path="/", **kwargs):
        return self.open(path, method="PUT", **kwargs)

    def delete(self, path="/", **kwargs):
        return self.open(path, method="DELETE", **kwargs)

    def patch(self, path="/", **kwargs):
        return self.open(path, method="PATCH", **kwargs)

    def options(self, path="/", **kwargs):
        return self.open(path, method="OPTIONS", **kwargs)

    def set_cookie(self, key, value="", *, domain="localhost", **kwargs):
        cookie_domain = "localhost.local" if domain == "localhost" else domain
        self.client.cookies.set(key, value, domain=cookie_domain, path=kwargs.get("path", "/"))

    def delete_cookie(self, key, *, domain="localhost", path="/"):
        cookie_domain = "localhost.local" if domain == "localhost" else domain
        self.client.cookies.delete(key, domain=cookie_domain, path=path)

    def __enter__(self):
        self.client.__enter__()
        return self

    def __exit__(self, *args):
        return self.client.__exit__(*args)
