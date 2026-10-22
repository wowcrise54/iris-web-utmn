"""Bounded, restart-safe MP10 ingestion. Full events are stored once, outside alerts."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from uuid import uuid5

from sqlalchemy import or_, func, text, Text
from sqlalchemy.orm import defer

from app.db import db
from app.models.alerts import Alert
from app.models.maxpatrol import MaxPatrolPollState, MaxPatrolReceipt, MaxPatrolIngestState, MaxPatrolEventRecord
from app.business.maxpatrol import MODULE, NAMESPACE, configuration
from app.models.models import IrisModule
from iris_maxpatrol_module.collector import (SIEMError, EVENT_SELECT_FIELDS, alert_payload,
    event_uuid, incident_event_window, timestamp, without_null_fields, error_reason)
from iris_maxpatrol_module.logging_utils import context_logger, logging_context

log = context_logger(__name__)
QUERY = 'select(' + ', '.join(EVENT_SELECT_FIELDS) + ') | sort(time desc)'
QUERY_HASH = hashlib.sha256(QUERY.encode()).hexdigest()


def utcnow():
    return datetime.now(timezone.utc)


def naive(value):
    return value.astimezone(timezone.utc).replace(tzinfo=None)


class Budget:
    def __init__(self, config):
        self.events = config.max_events_per_poll
        self.bytes = config.max_bytes_per_poll_mb * 1024 * 1024
        self.requests = config.max_requests_per_poll

    @property
    def available(self):
        return self.events > 0 and self.bytes > 0 and self.requests > 0


def _active(module_id, config):
    db.session.expire_all()
    row = db.session.get(IrisModule, module_id)
    return bool(row and row.is_active and row.module_name == MODULE and configuration(row) == config)


def _receipt(config, incident_id):
    return db.session.get(MaxPatrolReceipt, (config.source_key, incident_id))


def _alert(config, incident_id):
    receipt = _receipt(config, incident_id)
    if not receipt:
        return None
    # Never hydrate a legacy multi-megabyte alert_source_content into the worker.
    return db.session.query(Alert).options(defer(Alert.alert_source_content)).filter_by(
        alert_uuid=receipt.alert_uuid, alert_customer_id=config.customer_id,
        alert_source='MaxPatrol SIEM', alert_source_ref=incident_id).first()


def _enqueue(config, incident, *, include_closed=False):
    incident_id = str(incident.get('id') or '').strip()
    if not incident_id or len(incident_id) > 512 or (incident.get('status') == 'Closed' and not include_closed):
        return
    state = db.session.get(MaxPatrolIngestState, (config.source_key, incident_id))
    if state is None:
        state = MaxPatrolIngestState(source_key=config.source_key, incident_id=incident_id,
                                    incident=without_null_fields(incident), deleted=False, legacy_migrated=False)
        db.session.add(state)
    else:
        state.incident = {**state.incident, **without_null_fields(incident)}


def _request(client, budget, method, path, **kwargs):
    if not budget.available:
        raise SIEMError('Poll budget exhausted', code='poll_budget')
    client.byte_limit = min(client.config.max_response_mb * 1024 * 1024, budget.bytes)
    budget.requests -= 1
    try:
        return client.request(method, path, **kwargs)
    finally:
        budget.bytes = max(0, budget.bytes - client.last_response_bytes)


def discover(config, client, budget, now):
    poll = db.session.get(MaxPatrolPollState, config.source_key)
    if poll is None:
        poll = MaxPatrolPollState(source_key=config.source_key, last_poll=naive(now))
        db.session.add(poll)
    discovery = poll.discovery or {'offset': 0, 'time_from': timestamp(now - timedelta(hours=config.lookback_hours))}
    data = _request(client, budget, 'POST', '/api/v2/incidents/', body={
        'offset': discovery['offset'], 'limit': 50, 'groups': {'filterType': 'no_filter'},
        'timeFrom': discovery['time_from'], 'timeTo': None, 'filterTimeType': 'creation',
        'filter': {'select': ['key', 'name', 'category', 'type', 'status', 'created', 'assigned'],
            'where': 'status != "Closed"', 'orderby': [
                {'field': 'created', 'sortOrder': 'descending'}, {'field': 'status', 'sortOrder': 'ascending'},
                {'field': 'severity', 'sortOrder': 'descending'}]}, 'queryIds': ['all_incidents']})
    rows = data.get('incidents')
    if data.get('errors') or not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise SIEMError('Invalid incident discovery response', code='incidents_response_error')
    for row in rows:
        _enqueue(config, row)
    poll.discovery = (None if len(rows) < 50 else
                      {**discovery, 'offset': discovery['offset'] + len(rows)})
    # Queueing and advancing discovery are one transaction.
    db.session.commit()
    log.info('MaxPatrol discovery saved: incidents=%s next_offset=%s', len(rows), (poll.discovery or {}).get('offset', 0))


def queue_legacy(config):
    """Queue existing imports with only the incident subdocument, not the event array."""
    rows = db.session.query(MaxPatrolReceipt.incident_id, Alert.alert_source_content['incident']).join(
        Alert, Alert.alert_uuid == MaxPatrolReceipt.alert_uuid).outerjoin(MaxPatrolIngestState,
            (MaxPatrolIngestState.source_key == MaxPatrolReceipt.source_key)
            & (MaxPatrolIngestState.incident_id == MaxPatrolReceipt.incident_id)).filter(
                MaxPatrolReceipt.source_key == config.source_key, MaxPatrolIngestState.incident_id.is_(None),
                Alert.alert_customer_id == config.customer_id, Alert.alert_source == 'MaxPatrol SIEM',
                Alert.alert_source_ref == MaxPatrolReceipt.incident_id).limit(50).all()
    for incident_id, incident in rows:
        _enqueue(config, {**(incident if isinstance(incident, dict) else {}), 'id': incident_id}, include_closed=True)
    db.session.commit()


def _upsert_event(state, alert, row):
    payload = without_null_fields(row)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode()
    key = event_uuid(payload) or 'hash:' + hashlib.md5(encoded, usedforsecurity=False).hexdigest()
    values = dict(source_key=state.source_key, incident_id=state.incident_id, event_key=key,
                  alert_uuid=alert.alert_uuid, payload=payload, byte_size=len(encoded))
    dialect = db.engine.dialect.name
    if dialect == 'postgresql':
        from sqlalchemy.dialects.postgresql import insert
        stmt = insert(MaxPatrolEventRecord).values(**values)
        # Merge richer refreshes without losing earlier fields absent from this page.
        merged = MaxPatrolEventRecord.payload.op('||')(stmt.excluded.payload)
        db.session.execute(stmt.on_conflict_do_update(
            index_elements=['source_key', 'incident_id', 'event_key'],
            set_={'payload': merged, 'byte_size': func.octet_length(merged.cast(Text))}))
    else:
        existing = db.session.get(MaxPatrolEventRecord, (state.source_key, state.incident_id, key))
        if existing is None:
            db.session.add(MaxPatrolEventRecord(**values))
        else:
            existing.payload = {**existing.payload, **payload}
            existing.byte_size = len(json.dumps(existing.payload, ensure_ascii=False).encode())


LEGACY_COPY_SQL = """
WITH raw_events AS (
SELECT e, priority FROM alerts a, LATERAL (
    SELECT flat_event.value AS e, 0 AS priority FROM jsonb_array_elements(
        CASE WHEN jsonb_typeof(a.alert_source_content::jsonb->'events') = 'array'
             THEN a.alert_source_content::jsonb->'events' ELSE '[]'::jsonb END) AS flat_event(value)
    UNION ALL
    SELECT tree_event.value AS e, 1 AS priority
    FROM jsonb_path_query(a.alert_source_content::jsonb, '$.event_tree.**.event') AS tree_event(value)
) legacy
WHERE a.alert_uuid = CAST(:alert_uuid AS uuid)
AND jsonb_typeof(e) = 'object'
), keyed AS (
    SELECT COALESCE(NULLIF(LOWER(e->>'uuid'), ''), NULLIF(LOWER(e#>>'{_meta,id}'), ''),
                    'legacy:' || md5(e::text)) AS event_key, jsonb_strip_nulls(e) AS payload, priority
    FROM raw_events
), merged AS (
    SELECT event_key, jsonb_object_agg(field.key, field.value ORDER BY priority) AS payload
    FROM keyed CROSS JOIN LATERAL jsonb_each(payload) field GROUP BY event_key
)
INSERT INTO maxpatrol_event_record(source_key, incident_id, event_key, alert_uuid, payload, byte_size)
SELECT :source_key, :incident_id, event_key, CAST(:alert_uuid AS uuid), payload, octet_length(payload::text)
FROM merged
ON CONFLICT DO NOTHING
"""


def _migrate_legacy(state, alert):
    if state.legacy_migrated:
        return
    if db.engine.dialect.name == 'postgresql':
        # Transfer inside PostgreSQL: no legacy event payload crosses into worker RAM.
        db.session.execute(text(LEGACY_COPY_SQL), dict(source_key=state.source_key,
            incident_id=state.incident_id, alert_uuid=str(alert.alert_uuid)))
    else:
        # SQLite test adapter streams individual legacy objects, never the whole array.
        result = db.session.execute(text("SELECT j.value FROM alerts a, json_tree(a.alert_source_content) j "
                                        "WHERE j.type='object' AND (j.path='$.events' OR "
                                        "(j.key='event' AND (j.fullkey LIKE '$.event_tree%' OR "
                                        "j.fullkey LIKE '$.\"event_tree\"%'))) AND "
                                        "a.alert_uuid=:uuid"), {'uuid': alert.alert_uuid.hex})
        for (value,) in result:
            row = json.loads(value)
            if isinstance(row, dict):
                _upsert_event(state, alert, row)
    state.legacy_migrated = True


def persist_page(config, module_id, state, rows, cursor, now):
    """Events, compact alert manifest, and cursor advance commit atomically."""
    if not _active(module_id, config):
        raise SIEMError('Module disabled or configuration changed', code='module_inactive')
    alert = _alert(config, state.incident_id)
    receipt = _receipt(config, state.incident_id)
    if receipt and alert is None:
        state.deleted = True  # Do not recreate a deliberately deleted/reassigned alert.
        db.session.commit()
        return False
    created = alert is None
    if created:
        payload = alert_payload(config, state.incident_id, state.incident, [], now)
        payload['alert_source_content'] = {}
        alert = Alert(alert_uuid=uuid5(NAMESPACE, config.source_key + ':' + state.incident_id), **payload)
        db.session.add(alert)
        db.session.flush()
        db.session.add(MaxPatrolReceipt(source_key=config.source_key, incident_id=state.incident_id,
            alert_uuid=alert.alert_uuid, imported_at=naive(now)))
    _migrate_legacy(state, alert)
    for row in rows:
        _upsert_event(state, alert, row)
    db.session.flush()
    count = db.session.query(func.count()).select_from(MaxPatrolEventRecord).filter_by(
        source_key=state.source_key, incident_id=state.incident_id).scalar()
    state.cursor = cursor
    state.due_at = naive(now + timedelta(seconds=max(300, config.interval) if cursor['done'] else config.interval))
    state.last_attempt = naive(now)
    manifest = without_null_fields({'incident': state.incident, 'incident_source': 'incidents_list_v2',
        'event_storage': {'kind': 'maxpatrol', 'url': f'/api/v2/alerts/{alert.alert_id}/siem-events', 'count': count},
        'event_collection': {'version': 3, 'complete': False, 'pagination_complete': cursor['done'],
            'linked_events_checked': False, 'next_offset': cursor['offset'], 'stored_events': count,
            'errors': [{'reason': cursor['last_error']}] if cursor.get('last_error') else [],
            'batch_events': len(rows), 'time_from': cursor['time_from'], 'time_to': cursor['time_to'],
            'collected_at': timestamp(now), 'source': 'incident_events_v3'}})
    # No full legacy source column is fetched or copied into Python.
    if created:
        alert.alert_source_content = manifest
        from app.business.alerts import alerts_create
        alerts_create(alert, iocs=[], assets=[])
    else:
        if db.engine.dialect.name == 'postgresql':
            # Preserve unrelated source metadata inside PostgreSQL, never loading the old payload.
            db.session.execute(text("UPDATE alerts SET alert_source_content = "
                "((COALESCE(alert_source_content::jsonb, '{}'::jsonb) - 'events' - 'event_tree') "
                "|| CAST(:manifest AS jsonb) || jsonb_build_object('incident', "
                "COALESCE(alert_source_content::jsonb->'incident', '{}'::jsonb) "
                "|| (CAST(:manifest AS jsonb)->'incident')))::json WHERE alert_uuid=CAST(:uuid AS uuid)"),
                {'manifest': json.dumps(manifest), 'uuid': str(alert.alert_uuid)})
        else:
            db.session.execute(text("UPDATE alerts SET alert_source_content=json_patch("
                "json_remove(alert_source_content, '$.events', '$.event_tree'), :manifest) "
                "WHERE alert_uuid=:uuid"), {'manifest': json.dumps(manifest), 'uuid': alert.alert_uuid.hex})
        db.session.commit()
    log.info('MaxPatrol page committed: offset=%s saved=%s total=%s pagination_complete=%s',
             cursor['offset'], len(rows), count, cursor['done'])
    return created


def _cursor_for(state, config, now):
    cursor = copy.deepcopy(state.cursor or {})
    if not cursor or cursor.get('done'):
        start, end = incident_event_window(state.incident,
            now - timedelta(hours=config.lookback_hours), now)
        cursor = {'time_from': int(start.timestamp()), 'time_to': int(end.timestamp()), 'offset': 0,
                  'token': None, 'done': False, 'page_size': config.event_page_size, 'query_hash': QUERY_HASH}
    elif cursor.get('query_hash') != QUERY_HASH:
        cursor.update(offset=0, token=None, query_hash=QUERY_HASH)
    return cursor


def run_bounded_poll(config, client, module_id, *, now=None):
    now = now or utcnow()
    budget = Budget(config)
    created = 0
    try:
        discover(config, client, budget, now)
    except SIEMError as exc:
        db.session.rollback()
        log.warning('MaxPatrol discovery failed: reason=%s; discovery cursor not advanced', error_reason(exc))
        if exc.code in ('http_401', 'http_403'):
            return 0
    queue_legacy(config)
    states = db.session.query(MaxPatrolIngestState).filter(
        MaxPatrolIngestState.source_key == config.source_key, MaxPatrolIngestState.deleted.is_(False),
        or_(MaxPatrolIngestState.due_at.is_(None), MaxPatrolIngestState.due_at <= naive(now))).order_by(
            MaxPatrolIngestState.last_attempt.asc().nullsfirst(), MaxPatrolIngestState.incident_id).limit(
                config.max_incidents_per_poll).all()
    for state in states:
        if not budget.available or not _active(module_id, config):
            break
        with logging_context(incident=state.incident_id):
            cursor = _cursor_for(state, config, now)
            state.cursor = cursor
            state.last_attempt = naive(now)
            state.due_at = naive(now + timedelta(seconds=config.interval))
            db.session.commit()  # Freeze the query window even if the next HTTP call dies.
            limit = min(cursor['page_size'], budget.events)
            params = {'incidentId': state.incident_id, 'offset': cursor['offset'], 'limit': limit, 'noCount': 'true'}
            if cursor.get('token'):
                params['token'] = cursor['token']
            log.info('MaxPatrol events request: api=v3 offset=%s limit=%s time_from=%s time_to=%s fields=%s',
                     cursor['offset'], limit, cursor['time_from'], cursor['time_to'], len(EVENT_SELECT_FIELDS))
            try:
                data = _request(client, budget, 'POST', '/api/events/v3/events/', params=params,
                    body={'filter': QUERY, 'timeFrom': cursor['time_from'], 'timeTo': cursor['time_to']})
                page = data.get('events')
                if data.get('errors') or not isinstance(page, list) or any(not isinstance(e, dict) for e in page):
                    raise SIEMError('Invalid event page', code='events_response_error')
                if len(page) > limit:
                    raise SIEMError('Server ignored requested page limit; cursor unchanged', code='event_limit_ignored')
                accepted = page
                fingerprint = hashlib.sha256(json.dumps(accepted, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                if accepted and cursor.get('last_page_hash') == fingerprint:
                    raise SIEMError('Server repeated the previous page', code='event_page_repeated')
                next_cursor = {**cursor, 'offset': cursor['offset'] + len(accepted),
                    'token': data.get('token') or cursor.get('token'), 'done': len(page) < limit, 'last_page_hash': fingerprint}
                next_cursor.pop('last_error', None)
                created += bool(persist_page(config, module_id, state, accepted, next_cursor, now))
                budget.events -= len(accepted)
            except SIEMError as exc:
                db.session.rollback()
                if exc.code == 'response_too_large':
                    cursor['page_size'] = max(1, limit // 2)
                elif cursor.get('token') and exc.code in ('http_400', 'http_404', 'http_410'):
                    cursor.update(offset=0, token=None)
                    cursor.pop('last_page_hash', None)
                cursor['last_error'] = error_reason(exc)
                try:
                    # Notify about the incident even while its event page is unavailable.
                    created += bool(persist_page(config, module_id, state, [], cursor, now))
                except Exception as persistence_error:
                    db.session.rollback()
                    log.warning('MaxPatrol deferred page status failed: reason=%s; cursor retained',
                                error_reason(persistence_error))
                log.warning('MaxPatrol page deferred: reason=%s next_offset=%s page_size=%s; data not skipped',
                            error_reason(exc), cursor['offset'], cursor['page_size'])
            except Exception as exc:
                db.session.rollback()
                log.warning('MaxPatrol page persistence failed: reason=%s; durable cursor determines retry position',
                            error_reason(exc))
    log.info('MaxPatrol bounded poll finished: created=%s event_budget_left=%s byte_budget_left=%s request_budget_left=%s',
             created, budget.events, budget.bytes, budget.requests)
    return created


def list_alert_events(alert, offset=0, limit=25):
    """Read a bounded page only after the caller has authorized this alert."""
    offset, limit = max(0, int(offset)), max(1, min(25, int(limit)))
    receipt = db.session.query(MaxPatrolReceipt).filter_by(alert_uuid=alert.alert_uuid).first()
    if not receipt:
        return {'data': [], 'offset': offset, 'limit': limit, 'total': 0, 'next_offset': None, 'has_more': False}
    query = db.session.query(MaxPatrolEventRecord).filter_by(source_key=receipt.source_key, incident_id=receipt.incident_id)
    total = query.count()
    refs = query.with_entities(MaxPatrolEventRecord.event_key, MaxPatrolEventRecord.byte_size).order_by(
        MaxPatrolEventRecord.event_key).offset(offset).limit(limit).all()
    result, size = [], 0
    for key, byte_size in refs:
        if result and size + byte_size > 4 * 1024 * 1024:
            break
        if byte_size > 16 * 1024 * 1024:
            result.append({'event_key': key, 'event': {}, 'error': 'legacy_event_exceeds_read_limit', 'bytes': byte_size})
        else:
            payload = query.with_entities(MaxPatrolEventRecord.payload).filter_by(event_key=key).scalar()
            result.append({'event_key': key, 'event': payload})
        size += byte_size
    next_offset = offset + len(result)
    has_more = next_offset < total
    return {'data': result, 'offset': offset, 'limit': limit, 'total': total,
            'next_offset': next_offset if has_more else None, 'has_more': has_more}
