"""Request-local authentication for the existing IRIS session and API keys."""
from hashlib import sha512
from functools import wraps
from urllib.parse import urlencode

from werkzeug.local import LocalProxy

from .web import abort, current_app, flash, g, redirect, request, session, url_for


class UserMixin:
    @property
    def is_active(self):
        return True

    @property
    def is_authenticated(self):
        return self.is_active

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)


class AnonymousUserMixin:
    is_active = False
    is_authenticated = False
    is_anonymous = True

    def get_id(self):
        return None


def _session_identifier():
    remote = request.headers.get("X-Forwarded-For", request.remote_addr)
    agent = request.headers.get("User-Agent")
    if remote is not None:
        remote = remote.encode("utf-8").split(b",")[0].strip()
    if agent is not None:
        agent = agent.encode("utf-8")
    return sha512(f"{remote}|{agent}".encode()).hexdigest()


class LoginManager:
    def __init__(self, app=None):
        self._user_callback = None
        self._request_callback = None
        self.anonymous_user = AnonymousUserMixin
        self.session_protection = "basic"
        self.login_view = None
        self.login_message = "Please log in to access this page."
        self.login_message_category = "message"
        self.unauthorized_callback = None
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        app.login_manager = self
        app.extensions["login_manager"] = self
        app.jinja_env.globals["current_user"] = current_user

    def user_loader(self, callback):
        self._user_callback = callback
        return callback

    def request_loader(self, callback):
        self._request_callback = callback
        return callback

    def unauthorized_handler(self, callback):
        self.unauthorized_callback = callback
        return callback

    def unauthorized(self):
        if self.unauthorized_callback is not None:
            return self.unauthorized_callback()
        if not self.login_view:
            abort(401)
        if self.login_message:
            flash(self.login_message, self.login_message_category)
        target = self.login_view
        if not target.startswith(("/", "http://", "https://")):
            target = url_for(target)
        next_url = request.full_path.rstrip("?")
        separator = "&" if "?" in target else "?"
        return redirect(target + separator + urlencode({"next": next_url}))

    def _load_user(self):
        user = None
        identifier = session.get("_user_id")
        if identifier is not None and self._user_callback is not None:
            user = self._user_callback(identifier)
            protection = current_app.config.get("SESSION_PROTECTION", self.session_protection)
            if protection and session.get("_id") != _session_identifier():
                if protection == "strong" and not session.get("_permanent"):
                    for key in ("_user_id", "_fresh", "_id"):
                        session.pop(key, None)
                    user = None
                else:
                    session["_fresh"] = False
        if user is None and self._request_callback is not None:
            user = self._request_callback(request)
        g._login_user = user if user is not None else self.anonymous_user()
        return g._login_user


def _get_user():
    if not hasattr(g, "_login_user"):
        manager = getattr(current_app, "login_manager", None)
        if manager is None:
            g._login_user = AnonymousUserMixin()
        else:
            manager._load_user()
    return g._login_user


current_user = LocalProxy(_get_user)


def login_required(func):
    @wraps(func)
    def protected(*args, **kwargs):
        if request.method != "OPTIONS" and not current_app.config.get("LOGIN_DISABLED"):
            if not current_user.is_authenticated:
                return current_app.login_manager.unauthorized()
        return func(*args, **kwargs)
    return protected


def login_user(user, remember=False, duration=None, force=False, fresh=True):
    if not force and not user.is_active:
        return False
    session["_user_id"] = user.get_id()
    session["_fresh"] = fresh
    session["_id"] = _session_identifier()
    g._login_user = user
    return True


def logout_user():
    for key in ("_user_id", "_fresh", "_id"):
        session.pop(key, None)
    g._login_user = current_app.login_manager.anonymous_user()
    return True
