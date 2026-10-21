"""MaxPatrol API contract, independent of the IRIS application and worker."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import logging
from itertools import chain
from uuid import UUID
from urllib.parse import quote, urlsplit

import requests

log = logging.getLogger(__name__)


class SIEMError(ValueError):
    """A bounded error that never contains a response body or credentials."""

    def __init__(self, message, *, code='siem_error'):
        super().__init__(message)
        self.code = code


class EventBatch(list):
    """Available rows plus an explicit reason for interrupted pagination."""

    def __init__(self, rows=(), *, reason=None):
        super().__init__(rows)
        self.reason = reason
        self.complete = reason is None


def error_reason(error):
    # Exception bodies may contain tokens, URLs, SQL parameters or SIEM content.
    return error.code if isinstance(error, SIEMError) else type(error).__name__


def positive_int(value, name, maximum=2147483647):
    if isinstance(value, bool) or not str(value).isdigit() or not 1 <= int(value) <= maximum:
        raise ValueError(f'Invalid {name}')
    return int(value)


@dataclass(frozen=True)
class Config:
    url: str
    token: str = field(repr=False)
    customer_id: int = 1
    interval: int = 30
    lookback_hours: int = 72
    timeout: int = 60
    verify_tls: bool = True
    severity_id: int = 1
    status_id: int = 5

    @classmethod
    def from_values(cls, values):
        url = str(values.get('siem_url') or '').strip().rstrip('/')
        parsed = urlsplit(url)
        if (any(ord(char) <= 32 for char in url) or parsed.scheme != 'https'
                or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment):
            raise ValueError('MaxPatrol URL must be HTTPS without credentials, query or fragment')
        try:
            parsed.port
        except ValueError:
            raise ValueError('Invalid MaxPatrol port') from None
        token = values.get('api_token')
        if not isinstance(token, str) or not token.strip() or '\n' in token or '\r' in token:
            raise ValueError('MaxPatrol API token is required')
        tls = values.get('verify_tls', True)
        if isinstance(tls, str) and tls.lower() in ('true', 'false'):
            tls = tls.lower() == 'true'
        if not isinstance(tls, bool):
            raise ValueError('verify_tls must be true or false')
        numbers = {name: positive_int(values.get(name, default), name, maximum) for name, default, maximum in (
            ('customer_id', 1, 2147483647), ('interval', 30, 86400),
            ('lookback_hours', 72, 8760), ('timeout', 60, 600),
            ('severity_id', 1, 2147483647), ('status_id', 5, 2147483647))}
        return cls(url=url, token=token.strip(), verify_tls=tls, **numbers)

    @property
    def source_key(self):
        # Token rotation and module reinstallation must not reset deduplication.
        parsed = urlsplit(self.url)
        origin = f'{parsed.hostname.lower()}:{parsed.port or 443}{parsed.path}'
        return hashlib.sha256(f'{origin}\n{self.customer_id}'.encode()).hexdigest()


def timestamp(moment):
    return moment.astimezone(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def strip_nulls(obj):
    if isinstance(obj, dict):
        return {k: clean for k, v in obj.items() if (clean := strip_nulls(v)) not in (None, {}, [])}
    if isinstance(obj, list):
        return [clean for v in obj if (clean := strip_nulls(v)) not in (None, {}, [])]
    return obj


class Client:
    def __init__(self, config, session=None):
        self.config = config
        self.session = session or requests.Session()
        self.session.trust_env = False

    def close(self):
        self.session.close()

    def request(self, method, path, *, body=None, params=None):
        try:
            response = self.session.request(method, self.config.url + path,
                headers={'Authorization': f'Bearer {self.config.token}', 'Accept': 'application/json',
                         'Content-Type': 'application/json'},
                json=body, params=params, timeout=self.config.timeout,
                verify=self.config.verify_tls, allow_redirects=False)
            if not 200 <= response.status_code < 300:
                log.warning('MaxPatrol HTTP request failed: method=%s endpoint=%s status=%s',
                            method, path, response.status_code)
                raise SIEMError(f'MaxPatrol HTTP {response.status_code}', code=f'http_{response.status_code}')
            data = response.json()
        except requests.exceptions.SSLError:
            raise SIEMError('MaxPatrol TLS request failed', code='tls_error') from None
        except requests.exceptions.Timeout:
            raise SIEMError('MaxPatrol request timed out', code='timeout') from None
        except requests.exceptions.ConnectionError:
            raise SIEMError('MaxPatrol connection failed', code='connection_error') from None
        except requests.exceptions.JSONDecodeError:
            raise SIEMError('MaxPatrol returned invalid JSON', code='invalid_json') from None
        except (requests.RequestException, ValueError) as exc:
            if isinstance(exc, SIEMError):
                raise
            code = 'request_error' if isinstance(exc, requests.RequestException) else 'invalid_json'
            raise SIEMError('MaxPatrol request failed or returned invalid JSON', code=code) from None
        if not isinstance(data, dict):
            raise SIEMError('MaxPatrol response must be an object')
        return data

    def incidents(self, start, end):
        offset = 0
        previous = None
        while True:
            data = self.request('POST', '/api/v2/incidents', body={
                'offset': offset, 'limit': 50, 'groups': {'filterType': 'no_filter'},
                'timeFrom': timestamp(start), 'timeTo': timestamp(end), 'filterTimeType': 'creation',
                'filter': {'select': INCIDENT_SELECT_FIELDS, 'where': '', 'orderby': [
                    {'field': 'created', 'sortOrder': 'ascending'},
                    {'field': 'key', 'sortOrder': 'ascending'}]},
                'queryIds': ['all_incidents']})
            page = data.get('incidents')
            if not isinstance(page, list) or any(not isinstance(item, dict) for item in page):
                raise SIEMError('MaxPatrol incidents must be an array of objects')
            if page and page == previous:
                raise SIEMError('MaxPatrol did not advance the incident page')
            log.info('MaxPatrol incidents page received: offset=%s count=%s', offset, len(page))
            yield from page
            if len(page) < 50:
                return
            previous, offset = page, offset + len(page)

    def detail(self, incident_id):
        return self.request('GET', '/api/incidentsReadModel/incidents/' + quote(incident_id, safe=''))

    def events(self, incident_id, start, end):
        events, offset, previous, token = [], 0, None, None
        while True:
            params = {'incidentId': incident_id, 'offset': offset, 'limit': 250, 'noCount': 'true'}
            if token:
                params['token'] = token
            log.info('MaxPatrol events request: api=v3 offset=%s time_from=%s time_to=%s fields=%s',
                     offset, int(start.timestamp()), int(end.timestamp()), len(EVENT_SELECT_FIELDS))
            data = self.request('POST', '/api/events/v3/events/', params=params,
                body={'filter': 'select(' + ', '.join(EVENT_SELECT_FIELDS) + ') | sort(time desc)',
                      'timeFrom': int(start.timestamp()), 'timeTo': int(end.timestamp())})
            page = data.get('events')
            if data.get('errors') or not isinstance(page, list) or any(not isinstance(item, dict) for item in page):
                raise SIEMError('MaxPatrol events must be an array of objects')
            if page and page == previous:
                raise SIEMError('MaxPatrol did not advance the event page')
            log.info('MaxPatrol events page received: incident=%r offset=%s count=%s',
                     incident_id, offset, len(page))
            events.extend(page)
            if len(page) < 250:
                return events
            previous, offset, token = page, offset + len(page), data.get('token')

    def event_details(self, event_id, event_time):
        uid = str(UUID(event_id))
        response = self.request('GET', f'/api/events/v2/events/{uid}/normalized', params={'time': event_time})
        event = response.get('event')
        if response.get('errors') or not isinstance(event, dict):
            raise SIEMError('MaxPatrol normalized event is unavailable', code='event_details_error')
        if 'Data' in event:
            rows = event['Data']
            if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
                raise SIEMError('MaxPatrol normalized event is unavailable', code='event_details_error')
            event = rows[0]
        if event_uuid(event) != uid:
            raise SIEMError('MaxPatrol returned a different event', code='event_identity_mismatch')
        return event

    def subevents(self, event_id, event_time, *, max_events=10000, is_active=None):
        uid = str(UUID(event_id))
        result, offset, previous, token = [], 0, None, None
        while True:
            if is_active and not is_active():
                return EventBatch(result, reason='module_inactive')
            remaining = max_events - len(result)
            if remaining <= 0:
                return EventBatch(result, reason='event_limit')
            page_size = min(250, remaining)
            params = {'field': 'subevents', 'time': event_time, 'limit': page_size, 'offset': offset}
            if token:
                params['token'] = token
            try:
                response = self.request('POST', f'/api/events/v2/subevents/{uid}', params=params,
                    body={'filter': {'select': EVENT_SELECT_FIELDS, 'where': '', 'groupBy': [],
                                     'orderBy': [{'field': 'time', 'sortOrder': 'ascending'}]},
                          'timeFrom': 0, 'timeTo': int(datetime.now(timezone.utc).timestamp()) + 1})
                page = response.get('events')
                if response.get('errors') or not isinstance(page, list) or any(not isinstance(e, dict) for e in page):
                    raise SIEMError('Invalid MaxPatrol subevents response', code='subevents_response_error')
                if page and page == previous:
                    raise SIEMError('MaxPatrol did not advance the subevent page', code='subevents_page_repeated')
            except SIEMError as exc:
                if result:
                    return EventBatch(result, reason=error_reason(exc))
                raise
            log.info('MaxPatrol subevents page received: parent=%r offset=%s count=%s', uid, offset, len(page))
            result.extend(page[:remaining])
            if len(page) < page_size:
                return EventBatch(result)
            previous, offset, token = page, offset + len(page), response.get('token')


def event_uuid(event):
    meta = event.get('_meta') if isinstance(event.get('_meta'), dict) else {}
    try:
        return str(UUID(str(event.get('uuid') or meta.get('id'))))
    except (ValueError, TypeError, AttributeError):
        return None


def event_date(event):
    meta = event.get('_meta') if isinstance(event.get('_meta'), dict) else {}
    value = event.get('time') or meta.get('time')
    try:
        datetime.fromisoformat(value.replace('Z', '+00:00'))
        return value
    except (ValueError, TypeError, AttributeError):
        return None


def expand_subevents(client, roots, *, max_events=10000, is_active=None, source_complete=False):
    """Load full events once per UUID and retain a cycle-safe nested view."""
    events, edges, errors, missing, visited = {}, {}, [], set(), set()
    queue = list(roots)
    root_ids = [event_uuid(event) for event in roots]
    preloaded = {uid for uid in root_ids if uid} if source_complete else set()
    limit_reached = False
    index = 0
    while index < len(queue):
        if is_active and not is_active():
            errors.append({'reason': 'module_inactive'})
            break
        candidate = queue[index]
        index += 1
        uid = event_uuid(candidate)
        if uid in visited:
            continue
        if len(visited) >= max_events:
            limit_reached = True
            break
        visited.add(uid)
        date = event_date(candidate)
        if not uid or not date:
            errors.append({'uuid': uid, 'reason': 'event_reference_invalid'})
            if uid:
                events[uid] = candidate
            continue
        events[uid] = candidate
        if uid not in preloaded:
            try:
                full = client.event_details(uid, date)
                events[uid] = {**candidate, **full}
            except SIEMError as exc:
                errors.append({'uuid': uid, 'reason': error_reason(exc)})
                log.warning('MaxPatrol event details failed: uuid=%r reason=%s', uid, error_reason(exc))
        full = events[uid]
        expected = full.get('subevents') or []
        if not isinstance(expected, list):
            expected = []
            errors.append({'uuid': uid, 'reason': 'subevents_field_invalid'})
        expected_ids = [event_uuid({'uuid': value}) for value in expected]
        expected_ids = [value for value in expected_ids if value]
        for value in full.get('subevents.missed') or []:
            if child_id := event_uuid({'uuid': value}):
                missing.add(child_id)
        count = full.get('count.subevents') or 0
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            errors.append({'uuid': uid, 'reason': 'subevents_count_invalid'})
            count = len(expected_ids)
        if len(expected_ids) != len(expected):
            errors.append({'uuid': uid, 'reason': 'subevents_reference_invalid'})
        if not expected_ids and not count:
            edges[uid] = []
            continue
        if expected_ids and set(expected_ids) <= preloaded and len(set(expected_ids)) >= count:
            edges[uid] = list(dict.fromkeys(expected_ids))
            continue
        try:
            children = client.subevents(uid, event_date(full) or date,
                                        max_events=max_events - len(visited), is_active=is_active)
            if isinstance(children, EventBatch) and not children.complete:
                errors.append({'uuid': uid, 'reason': children.reason})
                limit_reached |= children.reason == 'event_limit'
            child_ids = [event_uuid(child) for child in children]
            edges[uid] = list(dict.fromkeys([*expected_ids, *(value for value in child_ids if value)]))
            missing.update(set(expected_ids) - set(child_ids))
            if len({value for value in child_ids if value}) < count:
                errors.append({'uuid': uid, 'reason': 'subevents_count_mismatch'})
            queue.extend(children)
        except SIEMError as exc:
            edges[uid] = expected_ids
            missing.update(expected_ids)
            errors.append({'uuid': uid, 'reason': error_reason(exc)})
            log.warning('MaxPatrol subevents failed: uuid=%r reason=%s', uid, error_reason(exc))
    missing.update({value for values in edges.values() for value in values} - events.keys())
    missing.difference_update(events.keys())
    summary = {'version': 2, 'complete': not (errors or missing or limit_reached),
               'root_count': len(roots), 'event_count': len(events),
               'missing_uuids': sorted(missing), 'errors': errors, 'limit_reached': limit_reached,
               'collected_at': timestamp(datetime.now(timezone.utc))}
    # A v3 incident response can include parents and their children together,
    # in any order. Render top-level parents before shared child references.
    children_ids = {child for children in edges.values() for child in children}
    tree_roots = [uid for uid in root_ids if uid not in children_ids] or root_ids
    log.info('MaxPatrol subevents summary: roots=%s events=%s missing=%s errors=%s complete=%s',
             len(roots), len(events), len(missing), len(errors), summary['complete'])
    # Keep unidentified source rows too; they cannot be traversed, but are evidence.
    return {'events': [*events.values(), *(row for row in roots if not event_uuid(row))],
            'event_tree': render_event_tree(tree_roots, events, edges),
            'event_links': edges, 'event_collection': summary}


def render_event_tree(root_ids, events, edges):
    rendered = set()

    def branch(uid, depth=0):
        node = {'uuid': uid}
        if uid not in events:
            return {**node, 'missing': True}
        if uid in rendered or depth >= 64:
            return {**node, 'reference': True}
        rendered.add(uid)
        return {**node, 'event': events[uid],
                'subevents': [branch(child, depth + 1) for child in edges.get(uid, [])]}

    return [branch(uid) for uid in dict.fromkeys(root_ids) if uid]


def incident_event_window(detail, start, end):
    """Bound normal polls; center historical refreshes on incident creation."""
    try:
        created = datetime.fromisoformat(detail['created'].replace('Z', '+00:00'))
        created = created.replace(tzinfo=timezone.utc) if created.tzinfo is None else created.astimezone(timezone.utc)
        if created < start or created > end:
            span = end - start
            return created - span, created + span
    except (KeyError, ValueError, TypeError, AttributeError, OverflowError):
        pass
    return start, end


def alert_payload(config, incident_id, detail, events, now, *, event_materials=None):
    event_time = now
    if isinstance(detail.get('created'), str):
        try:
            event_time = datetime.fromisoformat(detail['created'].replace('Z', '+00:00'))
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return {
        'alert_title': detail.get('name') or f'SIEM incident {incident_id}',
        'alert_description': detail.get('description') or 'Incident from MaxPatrol SIEM',
        'alert_source': 'MaxPatrol SIEM', 'alert_source_ref': incident_id,
        'alert_source_link': config.url + '/#/incident/incidents/view/' + quote(incident_id, safe=''),
        'alert_severity_id': config.severity_id, 'alert_status_id': config.status_id,
        'alert_tags': 'siem', 'alert_customer_id': config.customer_id,
        'alert_source_event_time': event_time.astimezone(timezone.utc).replace(tzinfo=None),
        'alert_source_content': {'incident': detail, 'events': events, **(event_materials or {})},
    }


def collect(config, client, store, *, now=None, extra_incidents=()):
    end = now or datetime.now(timezone.utc)
    start = end - timedelta(hours=config.lookback_hours)
    successes = received = already_imported = failed = invalid = events_failed = refreshed = 0
    complete = False
    processed_incidents = set()
    log.info('MaxPatrol collection started: customer=%s time_from=%s time_to=%s',
             config.customer_id, timestamp(start), timestamp(end))
    try:
        for incident in chain(client.incidents(start, end), ({'id': uid} for uid in extra_incidents)):
            incident_id = str(incident.get('id') or '').strip()
            if incident_id and incident_id in processed_incidents:
                continue
            processed_incidents.add(incident_id)
            received += 1
            if not store.active():
                log.info('MaxPatrol collection stopped: module disabled or configuration changed')
                break
            if not incident_id or len(incident_id) > 512:
                invalid += 1
                log.warning('MaxPatrol incident without a valid id skipped')
                continue
            existing = False
            try:
                existing = store.seen(incident_id)
                if existing and not store.needs_event_refresh(incident_id):
                    already_imported += 1
                    continue
                log.info('MaxPatrol incident import started: incident=%r', incident_id)
                detail = client.detail(incident_id)
                try:
                    event_start, event_end = incident_event_window(detail, start, end)
                    events = client.events(incident_id, event_start, event_end)
                    materials = expand_subevents(client, events, is_active=store.active, source_complete=True)
                except SIEMError as exc:
                    events_failed += 1
                    log.warning('MaxPatrol event retrieval failed: incident=%r reason=%s; importing without events',
                                incident_id, error_reason(exc))
                    events = []
                    materials = {'events': [], 'event_collection': {'version': 2, 'complete': False,
                        'errors': [{'reason': error_reason(exc)}], 'collected_at': timestamp(end)}}
                log.info('MaxPatrol incident details received: incident=%r events=%s', incident_id, len(events))
                if existing:
                    if store.refresh_events(incident_id, materials):
                        refreshed += 1
                        log.info('MaxPatrol incident events refreshed: incident=%r', incident_id)
                    continue
                store.create(incident_id, alert_payload(config, incident_id, detail, events, end,
                                                       event_materials=materials))
                successes += 1
                log.info('MaxPatrol incident imported: incident=%r', incident_id)
            except Exception as exc:
                store.rollback()
                if not existing and store.seen(incident_id):
                    successes += 1
                    log.warning('MaxPatrol alert committed; a post-commit action failed: incident=%r reason=%s',
                                incident_id, error_reason(exc))
                    continue
                failed += 1
                log.warning('MaxPatrol incident import failed: incident=%r reason=%s; retry within lookback window',
                            incident_id, error_reason(exc))
        else:
            complete = True
    finally:
        log.info('MaxPatrol collection summary: received=%s created=%s already_imported=%s failed=%s invalid=%s '
                 'events_failed=%s complete=%s refreshed=%s', received, successes, already_imported, failed, invalid,
                 events_failed, complete, refreshed)
    return successes


INCIDENT_SELECT_FIELDS = ['key', 'name', 'category', 'type', 'status', 'created', 'assigned']
EVENT_SELECT_FIELDS = [
    '_checkpoint',
    '_meta',
    '_presentation',
    '_whitelisting',
    'action',
    'agent_id',
    'aggregation_name',
    'alert.context',
    'alert.ioc_description',
    'alert.ioc_importance',
    'alert.ioc_provider',
    'alert.ioc_type',
    'alert.ioc_value',
    'alert.key',
    'alert.regex_match',
    'asset_ids',
    'assigned_dst_host',
    'assigned_dst_ip',
    'assigned_dst_port',
    'assigned_src_host',
    'assigned_src_ip',
    'assigned_src_port',
    'bad.clustering.cluster_id',
    'bad.clustering.cluster_size',
    'bad.clustering.reduction_coef',
    'bad.hack_tracker.is_hacker',
    'bad.hack_tracker.root_process',
    'bad.risk_score',
    'bad.risk_score_raw',
    'bad.triggered_models',
    'bad.triggered_rule_score_raw',
    'body',
    'category.generic',
    'category.high',
    'category.low',
    'chain_id',
    'correlation_name',
    'correlation_type',
    'count',
    'count.bytes',
    'count.bytes_in',
    'count.bytes_out',
    'count.packets',
    'count.packets_in',
    'count.packets_out',
    'count.subevents',
    'datafield1',
    'datafield10',
    'datafield11',
    'datafield12',
    'datafield13',
    'datafield14',
    'datafield15',
    'datafield16',
    'datafield17',
    'datafield18',
    'datafield19',
    'datafield2',
    'datafield20',
    'datafield3',
    'datafield4',
    'datafield5',
    'datafield6',
    'datafield7',
    'datafield8',
    'datafield9',
    'detect',
    'direction',
    'dst.asset',
    'dst.fqdn',
    'dst.geo.asn',
    'dst.geo.city',
    'dst.geo.country',
    'dst.geo.org',
    'dst.host',
    'dst.hostname',
    'dst.ip',
    'dst.mac',
    'dst.mac.vendor',
    'dst.port',
    'duration',
    'event_src.asset',
    'event_src.category',
    'event_src.description',
    'event_src.fqdn',
    'event_src.host',
    'event_src.hostname',
    'event_src.id',
    'event_src.ip',
    'event_src.mac',
    'event_src.mac.vendor',
    'event_src.provider',
    'event_src.rule',
    'event_src.subsys',
    'event_src.title',
    'event_src.vendor',
    'event_type',
    'external_dst.fqdn',
    'external_dst.geo.asn',
    'external_dst.geo.city',
    'external_dst.geo.country',
    'external_dst.geo.org',
    'external_dst.host',
    'external_dst.hostname',
    'external_dst.ip',
    'external_dst.mac',
    'external_dst.mac.vendor',
    'external_link',
    'external_src.fqdn',
    'external_src.geo.asn',
    'external_src.geo.city',
    'external_src.geo.country',
    'external_src.geo.org',
    'external_src.host',
    'external_src.hostname',
    'external_src.ip',
    'external_src.mac',
    'external_src.mac.vendor',
    'generator',
    'generator.type',
    'generator.version',
    'historical',
    'id',
    'importance',
    'incident.attacking_addresses',
    'incident.attacking_assets',
    'incident.compromised_assets',
    'incident.related_addresses',
    'incident.related_assets',
    'incorrect_time',
    'input_id',
    'interface',
    'job_id',
    'labels',
    'logon_auth_method',
    'logon_service',
    'logon_type',
    'mime',
    'msgid',
    'nas_fqdn',
    'nas_ip',
    'normalized',
    'numfield1',
    'numfield2',
    'numfield3',
    'numfield4',
    'numfield5',
    'object',
    'object.account.company',
    'object.account.contact',
    'object.account.department',
    'object.account.dn',
    'object.account.domain',
    'object.account.fullname',
    'object.account.group',
    'object.account.id',
    'object.account.name',
    'object.account.privileges',
    'object.account.provider',
    'object.account.session_id',
    'object.account.title',
    'object.application.account.domain',
    'object.application.account.id',
    'object.application.account.name',
    'object.application.account.privileges',
    'object.application.account.session_id',
    'object.application.name',
    'object.domain',
    'object.fullpath',
    'object.group',
    'object.hash',
    'object.hash.imphash',
    'object.hash.md5',
    'object.hash.sha1',
    'object.hash.sha256',
    'object.id',
    'object.meta',
    'object.name',
    'object.new_value',
    'object.num_value',
    'object.original_name',
    'object.path',
    'object.process.chain',
    'object.process.chain_info',
    'object.process.cmdline',
    'object.process.cwd',
    'object.process.decoded_data',
    'object.process.fullpath',
    'object.process.guid',
    'object.process.hash',
    'object.process.hash.imphash',
    'object.process.hash.md5',
    'object.process.hash.sha1',
    'object.process.hash.sha256',
    'object.process.id',
    'object.process.meta',
    'object.process.name',
    'object.process.original_name',
    'object.process.parent.cmdline',
    'object.process.parent.decoded_data',
    'object.process.parent.fullpath',
    'object.process.parent.guid',
    'object.process.parent.hash',
    'object.process.parent.hash.imphash',
    'object.process.parent.hash.md5',
    'object.process.parent.hash.sha1',
    'object.process.parent.hash.sha256',
    'object.process.parent.id',
    'object.process.parent.name',
    'object.process.parent.path',
    'object.process.parent.system_id',
    'object.process.path',
    'object.process.system_id',
    'object.process.version',
    'object.property',
    'object.query',
    'object.state',
    'object.storage.fullpath',
    'object.storage.id',
    'object.storage.name',
    'object.storage.path',
    'object.type',
    'object.value',
    'object.vendor',
    'object.version',
    'origin_app_alias',
    'origin_app_id',
    'origin_app_name',
    'original_time',
    'primary_siem_app_alias',
    'primary_siem_app_id',
    'primary_siem_app_name',
    'protocol',
    'protocol.layer7',
    'reason',
    'recv_asset',
    'recv_host',
    'recv_ipv4',
    'recv_ipv6',
    'recv_time',
    'related_events',
    'related_events.time',
    'remote',
    'scope_id',
    'siem_alias',
    'siem_id',
    'site_id',
    'src.asset',
    'src.fqdn',
    'src.geo.asn',
    'src.geo.city',
    'src.geo.country',
    'src.geo.org',
    'src.host',
    'src.hostname',
    'src.ip',
    'src.mac',
    'src.mac.vendor',
    'src.port',
    'start_time',
    'status',
    'storage_app_alias',
    'storage_app_id',
    'storage_app_name',
    'subevents',
    'subevents.missed',
    'subject',
    'subject.account.company',
    'subject.account.contact',
    'subject.account.department',
    'subject.account.dn',
    'subject.account.domain',
    'subject.account.fullname',
    'subject.account.group',
    'subject.account.id',
    'subject.account.name',
    'subject.account.privileges',
    'subject.account.provider',
    'subject.account.session_id',
    'subject.account.title',
    'subject.application.account.domain',
    'subject.application.account.id',
    'subject.application.account.name',
    'subject.application.account.privileges',
    'subject.application.account.session_id',
    'subject.application.name',
    'subject.domain',
    'subject.group',
    'subject.id',
    'subject.name',
    'subject.privileges',
    'subject.process.chain',
    'subject.process.chain_info',
    'subject.process.cmdline',
    'subject.process.cwd',
    'subject.process.decoded_data',
    'subject.process.fullpath',
    'subject.process.guid',
    'subject.process.hash',
    'subject.process.hash.imphash',
    'subject.process.hash.md5',
    'subject.process.hash.sha1',
    'subject.process.hash.sha256',
    'subject.process.id',
    'subject.process.meta',
    'subject.process.name',
    'subject.process.original_name',
    'subject.process.parent.cmdline',
    'subject.process.parent.decoded_data',
    'subject.process.parent.fullpath',
    'subject.process.parent.guid',
    'subject.process.parent.hash',
    'subject.process.parent.hash.imphash',
    'subject.process.parent.hash.md5',
    'subject.process.parent.hash.sha1',
    'subject.process.parent.hash.sha256',
    'subject.process.parent.id',
    'subject.process.parent.name',
    'subject.process.parent.path',
    'subject.process.parent.system_id',
    'subject.process.path',
    'subject.process.system_id',
    'subject.process.version',
    'subject.state',
    'subject.type',
    'subject.version',
    'tag',
    'task_id',
    'taxonomy_version',
    'tcp_flag',
    'tenant_id',
    'text',
    'time',
    'type',
    'uuid',
]
