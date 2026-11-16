"""Poll Wazuh using the existing Celery worker and a per-source lock."""
import logging
from datetime import datetime, timedelta, timezone
import requests

from app import celery
from app.db import db
from app.business.wazuh import MODULE, IrisStore, configuration
from app.iris_engine.maxpatrol.tasks import source_lock
from app.models.models import IrisModule
from app.models.wazuh import WazuhPollState
from iris_wazuh_module.collector import Client, collect_window

log = logging.getLogger(__name__)
OVERLAP = timedelta(minutes=5)


def timestamp(value):
    return value.isoformat(timespec='microseconds') + 'Z'


@celery.task(name='iris.wazuh.poll')
def poll(module_id):
    client = None
    stage = 'configuration'
    try:
        row = db.session.get(IrisModule, module_id)
        if not row or not row.is_active or row.module_name != MODULE:
            return
        config = configuration(row)
        stage = 'lock'
        with source_lock(config['source_key']) as acquired:
            if not acquired:
                return
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            state = db.session.get(WazuhPollState, config['source_key'])
            if not state:
                state = WazuhPollState(source_key=config['source_key'], started_at=now,
                                       watermark=now, last_poll=now)
                db.session.add(state)
                db.session.commit()
                log.info('Wazuh collection initialized at %s UTC; no history imported', now)
                return
            if (now - state.last_poll).total_seconds() < config['interval']:
                return
            state.last_poll = now
            db.session.commit()
            start = max(state.started_at, state.watermark - OVERLAP)
            stage = 'collection'
            client = Client(config['url'], config['username'], config['password'], config['index'],
                            config['timeout'], config['verify_tls'])
            count = collect_window(client.hits(timestamp(start), timestamp(now), config['min_level']),
                                   IrisStore(module_id, config, state), now)
            log.info('Wazuh collection completed: module=%s alerts_created=%s', module_id, count)
    except Exception as exc:
        db.session.rollback()
        if isinstance(exc, requests.exceptions.SSLError):
            reason = 'TLS verification failed'
        elif isinstance(exc, requests.exceptions.Timeout):
            reason = 'Indexer request timed out'
        elif isinstance(exc, requests.exceptions.HTTPError):
            status = exc.response.status_code if exc.response is not None else None
            reason = f'Indexer returned HTTP {status}'
        elif isinstance(exc, requests.exceptions.ConnectionError):
            reason = 'Indexer connection failed'
        elif isinstance(exc, (ValueError, KeyError, TypeError)):
            reason = 'invalid configuration, changed settings, or malformed/incomplete Indexer response'
        else:
            reason = 'processing failed; retry scheduled'
        log.warning('Wazuh poll failed: module=%s stage=%s reason=%s', module_id, stage, reason)
    finally:
        if client:
            client.close()


@celery.task(name='iris.wazuh.dispatch')
def dispatch():
    for row in IrisModule.query.filter_by(module_name=MODULE, is_active=True).all():
        poll.apply_async(args=[row.id], expires=5)


celery.conf.beat_schedule['wazuh-poll'] = {
    'task': 'iris.wazuh.dispatch', 'schedule': 5.0, 'options': {'expires': 5},
}
