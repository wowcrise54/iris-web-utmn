"""Database and serialization contracts without importing the IRIS application."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
import importlib.util
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest


EXTENSIONS_PATH = Path(__file__).parents[2] / "source" / "app" / "extensions.py"


def test_extensions_load_without_flask_or_application_initialization():
    assert EXTENSIONS_PATH.is_file(), "Standalone extension module is not implemented"
    script = f"""
import importlib.abc, importlib.util, sys
class RejectFlask(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'flask' or fullname.startswith(('flask.', 'flask_')):
            raise AssertionError('Forbidden runtime import: ' + fullname)
sys.meta_path.insert(0, RejectFlask())
spec = importlib.util.spec_from_file_location('standalone_extensions', {str(EXTENSIONS_PATH)!r})
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
assert 'app' not in sys.modules
assert all(hasattr(module, n) for n in ['SQLAlchemy', 'Marshmallow', 'Bcrypt', 'Cache', 'Pagination'])
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.fixture
def extensions():
    spec = importlib.util.spec_from_file_location("migration_extensions_under_test", EXTENSIONS_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def database(extensions, tmp_path):
    scope = ContextVar("extension_test_scope", default=None)
    app = SimpleNamespace(config={
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "SQLALCHEMY_BINDS": {"iris_tasks": {
            "url": f"sqlite:///{(tmp_path / 'tasks.sqlite').as_posix()}",
        }},
    }, extensions={}, teardown_callbacks=[], instance_path=str(tmp_path))
    app.teardown_appcontext = app.teardown_callbacks.append
    db = extensions.SQLAlchemy(app, scopefunc=lambda: scope.get())

    class Customer(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(100), unique=True, nullable=False)

    class Task(db.Model):
        __bind_key__ = "iris_tasks"
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(100), nullable=False)

    db.create_all()

    @contextmanager
    def context():
        token = scope.set(object())
        try:
            yield
        finally:
            for teardown in app.teardown_callbacks:
                teardown(None)
            scope.reset(token)

    with context():
        yield db, Customer, Task, app, context
    for engine in db.engines.values():
        engine.dispose()


def test_models_query_and_transactions_preserve_legacy_contract(database):
    db, Customer, _, app, _ = database
    first = Customer(name="first")
    db.session.add(first)
    db.session.commit()
    assert first.id == 1
    assert Customer.query.filter_by(name="first").one() is first
    db.session.add(Customer(name="aborted"))
    db.session.rollback()
    assert [row.name for row in db.session.query(Customer).all()] == ["first"]
    assert app.extensions["sqlalchemy"] is db


def test_models_and_core_statements_route_to_metadata_bind(database):
    from sqlalchemy import inspect, insert, select, update

    db, Customer, Task, _, _ = database
    db.session.add_all([Customer(name="customer"), Task(name="queued")])
    db.session.commit()
    assert inspect(db.engine).get_table_names() == ["customer"]
    assert inspect(db.engines["iris_tasks"]).get_table_names() == ["task"]
    assert Task.__table__.metadata.info["bind_key"] == "iris_tasks"
    assert Task.__table__.metadata.naming_convention == Customer.__table__.metadata.naming_convention
    db.session.execute(insert(Task.__table__).values(name="second"))
    db.session.execute(update(Task.__table__).where(Task.id == 1).values(name="done"))
    db.session.commit()
    assert db.session.scalars(select(Task.name).order_by(Task.id)).all() == ["done", "second"]
    assert db.session.scalars(select(Task.__table__.c.name).order_by(Task.id)).all() == ["done", "second"]
    assert db.session.get_bind(mapper=Task) is db.engines["iris_tasks"]


def test_create_and_drop_all_can_target_only_one_bind(database):
    from sqlalchemy import inspect

    db, _, _, _, _ = database
    db.drop_all(bind_key="iris_tasks")
    assert inspect(db.engines["iris_tasks"]).get_table_names() == []
    assert inspect(db.engine).get_table_names() == ["customer"]
    db.create_all(bind_key="iris_tasks")
    db.drop_all(bind_key=None)
    assert inspect(db.engines["iris_tasks"]).get_table_names() == ["task"]
    assert inspect(db.engine).get_table_names() == []


def test_unknown_bind_raises_instead_of_writing_into_default_database(database):
    from sqlalchemy.exc import UnboundExecutionError

    db, _, _, _, _ = database

    class UnknownTask(db.Model):
        __bind_key__ = "unknown"
        id = db.Column(db.Integer, primary_key=True)

    with pytest.raises(UnboundExecutionError):
        db.session.query(UnknownTask).all()


def test_sessions_are_scoped_per_context_and_removed_at_teardown(database):
    db, _, _, _, context = database
    outer_session = db.session()
    with context():
        inner_session = db.session()
        assert inner_session is not outer_session
        assert db.session() is inner_session
    assert db.session() is outer_session
    db.session.remove()
    assert db.session() is not outer_session


def test_concurrent_async_contexts_do_not_share_session(database):
    db, _, _, _, context = database

    async def worker():
        with context():
            session = db.session()
            await asyncio.sleep(0)
            assert db.session() is session
            return session

    # Exercise the same context switching as asyncio Tasks without creating
    # a Windows socket-backed event loop in a network-restricted sandbox.
    first_context, second_context = copy_context(), copy_context()
    first_worker, second_worker = worker(), worker()
    first_context.run(first_worker.send, None)
    second_context.run(second_worker.send, None)
    with pytest.raises(StopIteration) as first:
        first_context.run(first_worker.send, None)
    with pytest.raises(StopIteration) as second:
        second_context.run(second_worker.send, None)
    assert first.value.value is not second.value.value


def test_pagination_returns_counts_navigation_and_unordered_count(database):
    db, Customer, _, _, _ = database
    db.session.add_all([Customer(name=f"customer-{i}") for i in range(5)])
    db.session.commit()
    page = Customer.query.order_by(Customer.id).paginate(page=2, per_page=2)
    assert [item.id for item in page] == [3, 4]
    assert (page.total, page.pages, page.first, page.last) == (5, 3, 3, 4)
    assert (page.prev_num, page.next_num, page.has_prev, page.has_next) == (1, 3, True, True)
    assert [item.id for item in page.prev().items] == [1, 2]
    assert [item.id for item in page.next().items] == [5]
    assert list(page.iter_pages()) == [1, 2, 3]
    assert Customer.query.paginate(per_page=500, max_per_page=100).per_page == 100
    assert Customer.query.paginate(count=False).total is None


def test_pagination_handles_invalid_and_missing_pages_and_404_queries(database):
    from werkzeug.exceptions import NotFound

    db, Customer, _, _, _ = database
    db.session.add(Customer(name="present"))
    db.session.commit()
    assert Customer.query.first_or_404().name == "present"
    assert Customer.query.get_or_404(1).name == "present"
    assert Customer.query.paginate(page=0, per_page=0, error_out=False).page == 1
    assert Customer.query.paginate(page=4, error_out=False).items == []
    assert Customer.query.paginate(page=4, error_out=False).first == 0
    for operation in [
        lambda: Customer.query.paginate(page=0),
        lambda: Customer.query.paginate(page=3),
        lambda: Customer.query.filter_by(name="absent").first_or_404(),
        lambda: Customer.query.get_or_404(999),
    ]:
        with pytest.raises(NotFound):
            operation()


def test_table_factory_and_auto_names_preserve_metadata_constraints(database):
    from sqlalchemy import inspect

    db, _, _, _, _ = database
    association = db.Table("customer_link", db.Column("customer_id", db.Integer,
                          db.ForeignKey("customer.id"), primary_key=True))
    assert association.metadata is db.Model.metadata

    class APIEvent(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        external_key = db.Column(db.String, index=True)

    db.create_all(bind_key=None)
    assert APIEvent.__tablename__ == "api_event"
    assert inspect(db.engine).get_indexes("api_event")[0]["name"] == "ix_api_event_external_key"
    assert next(iter(association.foreign_key_constraints)).name is None


def test_marshmallow_loads_and_updates_model_with_implicit_scoped_session(extensions, database):
    db, Customer, _, app, _ = database
    ma = extensions.Marshmallow(app)

    class CustomerSchema(ma.SQLAlchemyAutoSchema):
        class Meta:
            model = Customer
            load_instance = True

    schema = CustomerSchema()
    customer = schema.load({"name": "created"})
    assert isinstance(customer, Customer)
    db.session.add(customer)
    db.session.commit()
    loaded = schema.load({"id": customer.id, "name": "renamed"})
    assert loaded is customer
    assert schema.dump(loaded) == {"id": 1, "name": "renamed"}
    assert schema.session is db.session
    assert ma.fields.String is not None


def test_marshmallow_explicit_schema_session_and_foreign_keys(extensions, database):
    db, Customer, _, app, _ = database
    ma = extensions.Marshmallow(app)

    class Contact(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"))
        customer = db.relationship(Customer)

    class ContactSchema(ma.SQLAlchemyAutoSchema):
        class Meta:
            model = Contact
            load_instance = True
            include_fk = True
            sqla_session = db.session

    db.create_all(bind_key=None)
    db.session.add(Customer(name="parent"))
    db.session.commit()
    contact = ContactSchema().load({"customer_id": 1})
    db.session.add(contact)
    db.session.commit()
    assert contact.customer.name == "parent"
    assert ContactSchema().dump(contact) == {"id": 1, "customer_id": 1}


def test_bcrypt_accepts_stored_bytes_and_text_and_configured_rounds(extensions):
    bc = extensions.Bcrypt(SimpleNamespace(config={"BCRYPT_LOG_ROUNDS": 4}))
    encoded = bc.generate_password_hash("пароль")
    assert encoded.startswith(b"$2b$04$")
    assert bc.check_password_hash(encoded.decode(), "пароль")
    assert bc.check_password_hash(encoded, "пароль".encode())
    assert not bc.check_password_hash(encoded, "wrong")


def test_cache_decorator_reuses_result_and_delete_invalidates(extensions):
    cache = extensions.Cache(SimpleNamespace(config={"CACHE_TYPE": "SimpleCache",
                             "CACHE_DEFAULT_TIMEOUT": 300}, extensions={}))
    calls = []

    @cache.cached(timeout=3600, key_prefix="iris_has_updates")
    def has_updates():
        calls.append(True)
        return {"has_updates": len(calls) > 1}

    assert has_updates() == {"has_updates": False}
    assert has_updates() == {"has_updates": False}
    assert len(calls) == 1
    assert cache.delete("iris_has_updates")
    assert has_updates() == {"has_updates": True}
    cache.set("none", None)
    assert cache.has("none")
    assert cache.clear()
    assert not cache.has("none")


def test_cache_concurrent_increment_is_atomic(extensions):
    cache = extensions.Cache()
    cache.set("counter", 0)
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda _: cache.inc("counter"), range(100)))
    assert cache.get("counter") == 100
