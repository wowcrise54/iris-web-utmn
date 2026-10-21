"""Short beat ticks dispatch source polls with a database-wide concurrency lock."""
from contextlib import contextmanager
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from sqlalchemy import text
from app import celery
from app.db import db
from app.business.maxpatrol import MODULE, configuration, IrisStore
from app.models.models import IrisModule
from app.models.maxpatrol import MaxPatrolPollState
from iris_maxpatrol_module.collector import Client, collect, error_reason, REQUEST_REVISION
from iris_maxpatrol_module.logging_utils import context_logger, logging_context

log = context_logger(__name__)


@contextmanager
def source_lock(source_key):
    # A separate session-level lock survives the commits made by alerts_create.
    # Always release it before returning this connection to SQLAlchemy's pool.
    key = int.from_bytes(bytes.fromhex(source_key)[:8], signed=True)
    with db.engine.connect() as connection:
        acquired = connection.execute(text('SELECT pg_try_advisory_lock(:key)'), {'key': key}).scalar()
        try:
            connection.commit()
            yield acquired
        finally:
            if acquired:
                try:
                    released = connection.execute(text('SELECT pg_advisory_unlock(:key)'), {'key': key}).scalar()
                    if not released:
                        connection.invalidate()
                except Exception:
                    connection.invalidate()


@celery.task(name='iris.maxpatrol.poll')
def poll(module_id):
    with logging_context(module=module_id, poll=uuid4().hex[:12]):
        return _poll(module_id)


def _poll(module_id):
    started = perf_counter()
    row = db.session.get(IrisModule, module_id)
    if not row or not row.is_active or row.module_name != MODULE:
        return
    client = None
    stage = 'configuration'
    try:
        config = configuration(row)
        stage = 'source_lock'
        with source_lock(config.source_key) as acquired:
            if not acquired:
                return
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            stage = 'poll_state'
            state = db.session.get(MaxPatrolPollState, config.source_key)
            if state and (now - state.last_poll).total_seconds() < config.interval:
                return
            if not state:
                state = MaxPatrolPollState(source_key=config.source_key)
                db.session.add(state)
            state.last_poll = now
            db.session.commit()
            stage = 'collection'
            log.info('MaxPatrol poll started: module=%s interval=%s request_revision=%s verify_tls=%s',
                     module_id, config.interval, REQUEST_REVISION, config.verify_tls)
            client = Client(config)
            store = IrisStore(module_id, config)
            count = collect(config, client, store, extra_incidents=store.refresh_candidates())
            log.info('MaxPatrol poll completed: module=%s alerts_created=%s duration_ms=%.1f',
                     module_id, count, (perf_counter() - started) * 1000)
    except Exception as exc:
        db.session.rollback()
        log.warning('MaxPatrol poll failed: module=%s stage=%s reason=%s duration_ms=%.1f',
                    module_id, stage, error_reason(exc), (perf_counter() - started) * 1000)
    finally:
        if client:
            client.close()


@celery.task(name='iris.maxpatrol.dispatch')
def dispatch():
    for row in IrisModule.query.filter_by(module_name=MODULE, is_active=True).all():
        poll.apply_async(args=[row.id], expires=5)


celery.conf.beat_schedule['maxpatrol-poll'] = {
    'task': 'iris.maxpatrol.dispatch', 'schedule': 5.0, 'options': {'expires': 5},
}
