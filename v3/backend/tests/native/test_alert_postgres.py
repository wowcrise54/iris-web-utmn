"""Opt-in real PostgreSQL migration/locking test; use a disposable empty database only."""
import ast
from contextlib import contextmanager
import hashlib
import importlib.util
import os
from pathlib import Path
import threading
import time
import json
from urllib.parse import urlsplit
from types import SimpleNamespace as NS

import pytest

URL = os.environ.get('IRIS_ALERT_TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not URL, reason='disposable PostgreSQL database required')
SOURCE = Path(__file__).parents[2] / 'source/app'


def selected(path, name, env):
    node = next(n for n in ast.parse(path.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), str(path), 'exec'), env)
    return env[name]


def test_migration_preserves_legacy_data_and_locks_are_cross_connection():
    import sqlalchemy as sa
    from sqlalchemy.orm import declarative_base, scoped_session, sessionmaker
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    engine = sa.create_engine(URL, pool_size=5)
    for attempt in range(40):
        try:
            with engine.connect() as connection:
                connection.execute(sa.text('SELECT 1'))
            break
        except sa.exc.OperationalError:
            if attempt == 39:
                raise
            time.sleep(0.5)
    with engine.begin() as connection:
        # Refuse populated/non-test databases; never drop an existing schema.
        assert not connection.execute(sa.text("SELECT to_regclass('public.evidence_analysis')")).scalar()
        for sql in (
            'CREATE TABLE cases (case_id bigint PRIMARY KEY)',
            'CREATE TABLE alerts (alert_id bigint PRIMARY KEY)',
            'CREATE TABLE client (client_id bigint PRIMARY KEY)',
            'CREATE TABLE server_settings (id integer PRIMARY KEY)',
            'CREATE TABLE chatbot_policy (id integer PRIMARY KEY)',
            'CREATE TABLE case_chat_conversation (id bigint PRIMARY KEY, case_id bigint REFERENCES cases, war_room_id bigint)',
            "CREATE TABLE evidence_analysis (id bigint PRIMARY KEY, case_id bigint NOT NULL REFERENCES cases, requested_by bigint, source_key text, status text, result jsonb NOT NULL DEFAULT '{}')",
            'INSERT INTO cases VALUES (1)',
            'INSERT INTO alerts VALUES (9)',
            'INSERT INTO client VALUES (3)',
            'INSERT INTO case_chat_conversation VALUES (1,1,NULL)',
            "INSERT INTO evidence_analysis VALUES (1,1,7,'sandbox:1','completed','{}')",
        ):
            connection.execute(sa.text(sql))
    spec = importlib.util.spec_from_file_location('pg_alert_migration', SOURCE / 'alembic/versions/utmn_alert_analysis01.py')
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        migration.upgrade()
        assert connection.execute(sa.text('SELECT case_id FROM evidence_analysis WHERE id=1')).scalar() == 1
        connection.execute(sa.text("INSERT INTO evidence_analysis(id,case_id,alert_id,requested_by,source_key,status) VALUES (2,NULL,9,7,'alert:9','queued')"))
        connection.execute(sa.text('INSERT INTO case_chat_conversation(id,alert_id,alert_customer_id) VALUES(2,9,3)'))
    for sql in (
        "INSERT INTO evidence_analysis(id,case_id,alert_id,requested_by,source_key,status) VALUES(3,NULL,9,7,'alert:9','running')",
        "INSERT INTO evidence_analysis(id,case_id,alert_id,requested_by,source_key,status) VALUES(3,1,9,7,'other','queued')",
        'INSERT INTO case_chat_conversation(id,alert_id) VALUES(3,9)',
    ):
        with pytest.raises(sa.exc.IntegrityError), engine.begin() as connection:
            connection.execute(sa.text(sql))
    with pytest.raises(sa.exc.DBAPIError), engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        migration.downgrade()

    # The production model-slot context manager releases even on exceptions.
    slot = selected(SOURCE / 'iris_engine/evidence/alert_tasks.py', '_provider_slot',
                    {'contextmanager': contextmanager, 'hashlib': hashlib, 'json': json,
                     'urlsplit': urlsplit, 'text': sa.text, 'db': NS(engine=engine)})
    provider = NS(_base_url='http://fixture-litellm/v1')
    with slot(provider) as first:
        assert first is True
        with slot(NS(_base_url='http://fixture-litellm')) as second:
            assert second is False
    with pytest.raises(RuntimeError):
        with slot(provider) as acquired:
            assert acquired is True
            raise RuntimeError('fixture')
    with slot(provider) as acquired:
        assert acquired is True

    # Exercise the actual worker reload and API cancel functions with a real ORM.
    base = declarative_base()
    class Job(base):
        __table__ = sa.Table('evidence_analysis', base.metadata, autoload_with=engine)
    session = scoped_session(sessionmaker(bind=engine))
    Job.query = session.query_property()
    db = NS(session=session)
    worker_lock = selected(SOURCE / 'iris_engine/evidence/alert_tasks.py', '_locked', {'db': db, 'EvidenceAnalysis': Job})
    api_lock = selected(SOURCE / 'business/alert_analysis.py', '_lock_job', {'db': db, 'EvidenceAnalysis': Job})
    import datetime as dt
    cancel = selected(SOURCE / 'business/alert_analysis.py', 'cancel_alert_job',
                      {'db': db, '_lock_job': api_lock, 'authorize_alert_analysis': lambda job: None, 'dt': dt})
    stale = session.get(Job, 2)
    stale.result = {'checkpoint': 1}
    def cancel_first():
        row = session.get(Job, 2)
        cancel(row)
        session.remove()
    thread = threading.Thread(target=cancel_first)
    thread.start(); thread.join(timeout=10)
    assert not thread.is_alive()
    worker_lock(stale)
    assert stale.result['_cancel_requested'] is True
    stale.result = {**stale.result, 'checkpoint': 1}
    session.commit()
    assert session.get(Job, 2).result == {'_cancel_requested': True, 'stage': 'cancelled', 'checkpoint': 1}
    # Reset only this disposable fixture row for the blocking-order test.
    row = session.get(Job, 2)
    row.status, row.result = 'running', {'checkpoint': 1}
    session.commit()
    worker_lock(row)
    worker_pid = session.execute(sa.text('SELECT pg_backend_pid()')).scalar()
    started = threading.Event()
    api_pid = []
    errors = []
    def wait_and_cancel():
        try:
            api_pid.append(session.execute(sa.text('SELECT pg_backend_pid()')).scalar())
            target = session.get(Job, 2)
            started.set()
            cancel(target)
        except Exception as exc:
            errors.append(type(exc).__name__)
        finally:
            session.remove()
    thread = threading.Thread(target=wait_and_cancel)
    thread.start()
    assert started.wait(5)
    blocked = False
    for _ in range(40):
        with engine.connect() as connection:
            blockers = connection.execute(sa.text('SELECT pg_blocking_pids(:pid)'), {'pid': api_pid[0]}).scalar()
        if worker_pid in blockers:
            blocked = True
            break
        time.sleep(0.05)
    row.result = {'checkpoint': 2}
    session.commit()
    thread.join(timeout=10)
    assert blocked and not thread.is_alive() and errors == []
    session.expire_all()
    assert session.get(Job, 2).result['checkpoint'] == 2
    assert session.get(Job, 2).result['_cancel_requested'] is True
    session.remove()
    with engine.begin() as connection:
        connection.execute(sa.text('DELETE FROM evidence_analysis WHERE alert_id IS NOT NULL'))
        connection.execute(sa.text('DELETE FROM case_chat_conversation WHERE alert_id IS NOT NULL'))
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        migration.downgrade()
        assert connection.execute(sa.text('SELECT case_id FROM evidence_analysis WHERE id=1')).scalar() == 1
    engine.dispose()
