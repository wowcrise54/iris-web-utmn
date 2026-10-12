"""Application extensions built on standalone libraries.

The public database and schema APIs preserve the contracts used by IRIS while
request lifetime and dispatch are owned by :mod:`app.web`.
"""

from functools import wraps
import hashlib
from math import ceil
import re
import sys
from threading import get_ident, RLock

import bcrypt
from cachelib import NullCache, SimpleCache
import marshmallow
import marshmallow_sqlalchemy
import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.sql import visitors
from sqlalchemy.pool import StaticPool
from werkzeug.exceptions import NotFound


def _request_args():
    web = sys.modules.get("app.web")
    if web is not None and web.request:
        return web.request.args
    return {}


class Pagination:
    """Paginated SQLAlchemy query with the existing navigation attributes."""

    def __init__(self, *, query, page=None, per_page=None, max_per_page=None,
                 error_out=True, count=True):
        args = _request_args()
        page = args.get("page", 1) if page is None else page
        per_page = args.get("per_page", 20) if per_page is None else per_page
        self.page = self._positive_integer(page, 1, error_out)
        self.per_page = self._positive_integer(per_page, 20, error_out)
        if max_per_page is not None:
            self.per_page = min(self.per_page, max_per_page)
        self.max_per_page = max_per_page
        self._query = query
        self.items = query.limit(self.per_page).offset(
            (self.page - 1) * self.per_page).all()
        if not self.items and self.page != 1 and error_out:
            raise NotFound()
        self.total = query.order_by(None).count() if count else None

    @staticmethod
    def _positive_integer(value, fallback, error_out):
        try:
            number = int(value)
            if number >= 1:
                return number
        except (TypeError, ValueError, OverflowError):
            pass
        if error_out:
            raise NotFound()
        return fallback

    def __iter__(self):
        return iter(self.items)

    @property
    def first(self):
        return (self.page - 1) * self.per_page + 1 if self.items else 0

    @property
    def last(self):
        return self.first + len(self.items) - 1 if self.items else 0

    @property
    def pages(self):
        return ceil(self.total / self.per_page) if self.total else 0

    @property
    def has_prev(self):
        return self.page > 1

    @property
    def has_next(self):
        return self.page < self.pages

    @property
    def prev_num(self):
        return self.page - 1 if self.has_prev else None

    @property
    def next_num(self):
        return self.page + 1 if self.has_next else None

    def _neighbor(self, page, error_out):
        result = type(self)(query=self._query, page=page, per_page=self.per_page,
                            max_per_page=self.max_per_page, error_out=error_out,
                            count=False)
        result.total = self.total
        return result

    def prev(self, *, error_out=False):
        return self._neighbor(self.page - 1, error_out)

    def next(self, *, error_out=False):
        return self._neighbor(self.page + 1, error_out)

    def iter_pages(self, *, left_edge=2, left_current=2, right_current=4, right_edge=2):
        previous = 0
        for number in range(1, self.pages + 1):
            if (number <= left_edge or number > self.pages - right_edge
                    or self.page - left_current <= number <= self.page + right_current):
                if number > previous + 1:
                    yield None
                yield number
                previous = number


class Query(orm.Query):
    def paginate(self, *, page=None, per_page=None, max_per_page=None,
                 error_out=True, count=True):
        return Pagination(query=self, page=page, per_page=per_page,
                          max_per_page=max_per_page, error_out=error_out, count=count)

    def first_or_404(self, description=None):
        result = self.first()
        if result is None:
            raise NotFound(description=description)
        return result

    def get_or_404(self, ident, description=None):
        result = self.session.get(self.column_descriptions[0]["entity"], ident)
        if result is None:
            raise NotFound(description=description)
        return result


class _BoundSession(orm.Session):
    def __init__(self, db, **kwargs):
        super().__init__(**kwargs)
        self._db = db

    def _table_engine(self, table):
        metadata = getattr(table, "metadata", None)
        if metadata is None or "bind_key" not in metadata.info:
            return None
        bind_key = metadata.info["bind_key"]
        if bind_key not in self._db.engines:
            raise sa.exc.UnboundExecutionError(
                f"Bind key {bind_key!r} is not configured in SQLALCHEMY_BINDS")
        return self._db.engines[bind_key]

    def get_bind(self, mapper=None, *, clause=None, bind=None, **kwargs):
        if bind is not None:
            return bind
        if mapper is not None:
            engine = self._table_engine(sa.inspect(mapper).local_table)
            if engine is not None:
                return engine
        if clause is not None:
            # Include standalone Core select/insert/update/delete statements.
            engines = {engine for node in visitors.iterate(clause)
                       if (engine := self._table_engine(node)) is not None}
            if len(engines) > 1:
                raise sa.exc.UnboundExecutionError("A statement cannot span database binds")
            if engines:
                return engines.pop()
        if None in self._db.engines:
            return self._db.engines[None]
        return super().get_bind(mapper=mapper, clause=clause, bind=bind, **kwargs)


class _ModelMeta(orm.DeclarativeMeta):
    def __init__(cls, name, bases, namespace, **kwargs):
        db = getattr(cls, "_db", None)
        if db is not None and "metadata" not in namespace and "__table__" not in namespace:
            cls.metadata = db._metadata_for(getattr(cls, "__bind_key__", None))
        if (not namespace.get("__abstract__", False)
                and "__tablename__" not in namespace and "__table__" not in namespace
                and not any("__table__" in base.__dict__ for base in bases)):
            cls.__tablename__ = re.sub(
                r"((?<=[a-z0-9])[A-Z]|(?!^)[A-Z](?=[a-z]))", r"_\1", name).lower().lstrip("_")
        super().__init__(name, bases, namespace, **kwargs)


class _QueryProperty:
    def __get__(self, instance, model):
        return model.query_class(model, session=model._db.session())


class SelectPagination(Pagination):
    def __init__(self, *, select, session, page=None, per_page=None, max_per_page=None,
                 error_out=True, count=True):
        args = _request_args()
        self.page = self._positive_integer(args.get('page', 1) if page is None else page, 1, error_out)
        self.per_page = self._positive_integer(args.get('per_page', 20) if per_page is None else per_page, 20, error_out)
        if max_per_page is not None:
            self.per_page = min(self.per_page, max_per_page)
        self.max_per_page = max_per_page
        self._query_args = {'select': select, 'session': session}
        self._query_offset = (self.page - 1) * self.per_page
        self.items = self._query_items()
        self.total = session.scalar(sa.select(sa.func.count()).select_from(select.order_by(None).subquery())) if count else None
        if not self.items and self.page != 1 and error_out:
            raise NotFound()

    def _query_items(self):
        statement = self._query_args['select'].limit(self.per_page).offset(self._query_offset)
        return list(self._query_args['session'].execute(statement).unique().scalars())

    def _neighbor(self, page, error_out):
        return type(self)(**self._query_args, page=page, per_page=self.per_page,
                          max_per_page=self.max_per_page, error_out=error_out)


class SQLAlchemy:
    """SQLAlchemy models, bind routing, and context scoped sessions for IRIS."""

    Query = Query

    def __init__(self, app=None, *, engine_options=None, session_options=None, scopefunc=None, query_class=Query):
        self._engine_options = dict(engine_options or {})
        self.engines = {}
        self.metadatas = {}
        self.metadata = self._metadata_for(None)
        self._app = None
        extension = self

        class Model:
            _db = extension
            pass
            query = _QueryProperty()

        self.Model = orm.declarative_base(cls=Model, name="Model", metadata=self.metadata,
                                         metaclass=_ModelMeta)
        self.Model.query_class = query_class
        options = dict(session_options or {})
        session_scope = scopefunc or options.pop("scopefunc", None) or self._scope_id
        options.setdefault("class_", _BoundSession)
        options.setdefault("query_cls", query_class)
        factory = orm.sessionmaker(db=self, **options)
        self.session = orm.scoped_session(factory, scopefunc=session_scope)
        if app is not None:
            self.init_app(app)

    @staticmethod
    def _scope_id():
        web = sys.modules.get("app.web")
        if web is not None:
            return id(web.g._get_current_object())
        return get_ident()

    def _metadata_for(self, bind_key):
        if bind_key not in self.metadatas:
            options = {"info": {"bind_key": bind_key}}
            if bind_key is not None:
                options["naming_convention"] = self.metadata.naming_convention
            self.metadatas[bind_key] = sa.MetaData(**options)
        return self.metadatas[bind_key]

    def init_app(self, app):
        if self._app is app:
            return
        if self._app is not None:
            raise RuntimeError("Each SQLAlchemy instance belongs to one application")
        self._app = app
        app.extensions["sqlalchemy"] = self
        config = app.config
        bind_options = dict(config.get("SQLALCHEMY_BINDS") or {})
        if config.get("SQLALCHEMY_DATABASE_URI"):
            bind_options[None] = {"url": config["SQLALCHEMY_DATABASE_URI"],
                                  **config.get("SQLALCHEMY_ENGINE_OPTIONS", {})}
        if not bind_options:
            raise RuntimeError("SQLALCHEMY_DATABASE_URI or SQLALCHEMY_BINDS must be configured")
        for bind_key, configured in bind_options.items():
            options = {**self._engine_options,
                       **(configured if isinstance(configured, dict) else {"url": configured})}
            url = sa.engine.make_url(options.pop("url"))
            if "SQLALCHEMY_ECHO" in config:
                options.setdefault("echo", config["SQLALCHEMY_ECHO"])
            if url.get_backend_name() == "sqlite" and url.database in (None, "", ":memory:"):
                options.setdefault("poolclass", StaticPool)
                options["connect_args"] = {"check_same_thread": False,
                                           **options.get("connect_args", {})}
            self._metadata_for(bind_key)
            self.engines[bind_key] = sa.create_engine(url, **options)
        if hasattr(app, "teardown_appcontext"):
            app.teardown_appcontext(self._teardown_session)

    def _teardown_session(self, exception=None):
        self.session.remove()

    @property
    def engine(self):
        return self.engines[None]

    def get_engine(self, bind_key=None, **kwargs):
        return self.engines[kwargs.get("bind", bind_key)]

    def Table(self, name, *args, bind_key=None, **kwargs):
        if args and isinstance(args[0], sa.MetaData):
            return sa.Table(name, *args, **kwargs)
        return sa.Table(name, self._metadata_for(bind_key), *args, **kwargs)

    def _metadata_operation(self, operation, bind_key):
        keys = list(self.metadatas) if bind_key == "__all__" else (
            list(bind_key) if isinstance(bind_key, (tuple, list)) else [bind_key])
        for key in keys:
            if key not in self.engines:
                raise sa.exc.UnboundExecutionError(f"No engine configured for bind {key!r}")
            getattr(self._metadata_for(key), operation)(bind=self.engines[key])

    def create_all(self, bind_key="__all__"):
        self._metadata_operation("create_all", bind_key)

    def paginate(self, select, **kwargs):
        return SelectPagination(select=select, session=self.session(), **kwargs)

    def drop_all(self, bind_key="__all__"):
        self._metadata_operation("drop_all", bind_key)

    def __getattr__(self, name):
        if hasattr(sa, name):
            return getattr(sa, name)
        if hasattr(orm, name):
            return getattr(orm, name)
        raise AttributeError(name)


class Marshmallow:
    Schema = marshmallow.Schema
    fields = marshmallow.fields

    def __init__(self, app=None):
        self._session = None
        extension = self

        class SessionSchemaMixin:
            @property
            def session(self):
                return super().session or extension._session

            @session.setter
            def session(self, value):
                self._session = value

        class SQLAlchemySchema(SessionSchemaMixin, marshmallow_sqlalchemy.SQLAlchemySchema):
            pass

        class SQLAlchemyAutoSchema(SessionSchemaMixin, marshmallow_sqlalchemy.SQLAlchemyAutoSchema):
            pass

        self.SQLAlchemySchema = SQLAlchemySchema
        self.SQLAlchemyAutoSchema = SQLAlchemyAutoSchema
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        self._session = app.extensions["sqlalchemy"].session
        app.extensions["marshmallow"] = self

    def __getattr__(self, name):
        if hasattr(marshmallow.fields, name):
            return getattr(marshmallow.fields, name)
        if hasattr(marshmallow_sqlalchemy, name):
            return getattr(marshmallow_sqlalchemy, name)
        raise AttributeError(name)


class Bcrypt:
    def __init__(self, app=None):
        self._rounds = 12
        self._prefix = "2b"
        self._handle_long_passwords = False
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        self._rounds = int(app.config.get("BCRYPT_LOG_ROUNDS", 12))
        self._prefix = app.config.get("BCRYPT_HASH_PREFIX", "2b")
        self._handle_long_passwords = app.config.get("BCRYPT_HANDLE_LONG_PASSWORDS", False)

    def _password_bytes(self, password):
        if isinstance(password, str):
            password = password.encode("utf-8")
        if self._handle_long_passwords:
            return hashlib.sha256(password).hexdigest().encode("ascii")
        # Preserve bcrypt 4 / Flask-Bcrypt's historical 72-byte behavior.
        return password[:72]

    def generate_password_hash(self, password, rounds=None, prefix=None):
        if not password:
            raise ValueError("Password must be non-empty")
        prefix = prefix or self._prefix
        if isinstance(prefix, str):
            prefix = prefix.encode("ascii")
        salt = bcrypt.gensalt(rounds=self._rounds if rounds is None else rounds, prefix=prefix)
        return bcrypt.hashpw(self._password_bytes(password), salt)

    def check_password_hash(self, pw_hash, password):
        if isinstance(pw_hash, str):
            pw_hash = pw_hash.encode("utf-8")
        return bcrypt.checkpw(self._password_bytes(password), pw_hash)


class Cache:
    """Process local cache with synchronization around cachelib operations."""

    def __init__(self, app=None, config=None):
        self._lock = RLock()
        self.cache = SimpleCache()
        if app is not None:
            self.init_app(app, config=config)

    def init_app(self, app, config=None):
        settings = {**app.config, **(config or {})}
        cache_type = settings.get("CACHE_TYPE", "SimpleCache")
        cache_class = NullCache if cache_type in ("NullCache", "null") else SimpleCache
        self.cache = cache_class(default_timeout=settings.get("CACHE_DEFAULT_TIMEOUT", 300),
                                 **({"threshold": settings.get("CACHE_THRESHOLD", 500)}
                                    if cache_class is SimpleCache else {}))
        app.extensions.setdefault("cache", {})[self] = self.cache

    def __getattr__(self, name):
        method = getattr(self.cache, name)
        if not callable(method):
            return method

        @wraps(method)
        def synchronized(*args, **kwargs):
            with self._lock:
                return method(*args, **kwargs)
        return synchronized

    def cached(self, timeout=None, key_prefix="view/%s", unless=None,
               forced_update=None, response_filter=None, cache_none=False,
               make_cache_key=None):
        def decorate(function):
            @wraps(function)
            def wrapped(*args, **kwargs):
                if unless is not None and unless():
                    return function(*args, **kwargs)
                if make_cache_key is not None:
                    key = make_cache_key(*args, **kwargs)
                elif callable(key_prefix):
                    key = key_prefix()
                elif "%s" in key_prefix:
                    web = sys.modules.get("app.web")
                    key = key_prefix % (web.request.path if web is not None and web.request
                                        else function.__name__)
                else:
                    key = key_prefix
                if forced_update is None or not forced_update():
                    result = self.get(key)
                    if result is not None or (cache_none and self.has(key)):
                        return result
                result = function(*args, **kwargs)
                if response_filter is None or response_filter(result):
                    self.set(key, result, timeout=timeout)
                return result
            wrapped.uncached = function
            return wrapped
        return decorate
