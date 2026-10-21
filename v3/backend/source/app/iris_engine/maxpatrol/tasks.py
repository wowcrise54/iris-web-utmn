"""Short beat ticks dispatch source polls with a database-wide concurrency lock."""
from contextlib import contextmanager
from datetime import datetime, timezone
import logging

from sqlalchemy import text
from app import celery
from app.db import db
from app.business.maxpatrol import MODULE, configuration, IrisStore
from app.models.models import IrisModule
from app.models.maxpatrol import MaxPatrolPollState
from iris_maxpatrol_module.collector import Client, collect, error_reason

log = logging.getLogger(__name__)


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
            log.info('MaxPatrol poll started: module=%s interval=%s', module_id, config.interval)
            client = Client(config)
            count = collect(config, client, IrisStore(module_id, config))
            log.info('MaxPatrol poll completed: module=%s alerts_created=%s', module_id, count)
    except Exception as exc:
        db.session.rollback()
        log.warning('MaxPatrol poll failed: module=%s stage=%s reason=%s', module_id, stage, error_reason(exc))
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
