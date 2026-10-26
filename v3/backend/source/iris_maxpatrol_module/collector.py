"""MaxPatrol API contract, independent of the IRIS application and worker."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import re
import warnings
from itertools import chain
from time import perf_counter
from uuid import UUID
from urllib.parse import quote, urlsplit

import requests
from urllib3.exceptions import InsecureRequestWarning

from iris_maxpatrol_module.logging_utils import context_logger, logging_context

log = context_logger(__name__)
REQUEST_REVISION = 'mp10-inline-clean-json-3'
LOOKBACK_DESCRIPTION = '1–8760; capped at 24 hours on every poll, including the first.'


class SIEMError(ValueError):
    """A bounded error that never contains a response body or credentials."""

    def __init__(self, message, *, code='siem_error', diagnostic=None):
        super().__init__(message)
        self.code = code
        self.diagnostic = diagnostic or {}


def error_reason(error):
    # Exception bodies may contain tokens, URLs, SQL parameters or SIEM content.
    return error.code if isinstance(error, SIEMError) else type(error).__name__


def error_details(error):
    return {'reason': error_reason(error), **(error.diagnostic if isinstance(error, SIEMError) else {})}


def without_null_fields(value):
    """Drop null object fields; preserve scalar values, array positions and raw strings."""
    if isinstance(value, dict):
        return {key: without_null_fields(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [without_null_fields(item) for item in value]
    return value


def request_diagnostic(method, path, body, response_text, token):
    # Retain no headers or full request/response. Redact before truncation so
    # the prefix of a long token cannot survive at the excerpt boundary.
    text = response_text if isinstance(response_text, str) else ''
    text = text.replace(token, '[REDACTED]') if token else text
    text = re.sub(r'(?i)\bpat_[a-z0-9_-]+', '[REDACTED]', text)
    text = re.sub(r'(?i)\bBearer\s+[^\s"<>]+', 'Bearer [REDACTED]', text)
    result = {'request_revision': REQUEST_REVISION, 'method': method, 'endpoint': path,
              'response_excerpt': ' '.join(text.split())[:1024]}
    if isinstance(body, dict):
        for source, target in (('timeFrom', 'time_from'), ('timeTo', 'time_to')):
            value = body.get(source)
            if isinstance(value, (int, float)):
                result[target] = value
        query_filter = body.get('filter')
        if isinstance(query_filter, str):
            result['filter_sha256'] = hashlib.sha256(query_filter.encode()).hexdigest()
            if query_filter.startswith('select('):
                result['fields_count'] = query_filter.split(')', 1)[0].count(',') + 1
    return result


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


class Client:
    def __init__(self, config, session=None):
        self.config = config
        self.session = session or requests.Session()
        self.session.trust_env = False
        self._insecure_notice_logged = False

    def close(self):
        self.session.close()

    def request(self, method, path, *, body=None, params=None):
        started = perf_counter()
        log.debug('MaxPatrol HTTP started: method=%s endpoint=%s offset=%s',
                  method, path, (params or {}).get('offset'))
        try:
            data, status = self._request(method, path, body=body, params=params)
        except SIEMError as exc:
            diagnostic = exc.diagnostic
            query_details = ' '.join(f'{label}={diagnostic[key]}' for key, label in (
                ('time_from', 'time_from'), ('time_to', 'time_to'), ('fields_count', 'fields')) if key in diagnostic)
            log.warning('MaxPatrol HTTP request failed: method=%s endpoint=%s status=%s reason=%s duration_ms=%.1f '
                        '%sresponse=%r',
                        method, path, diagnostic.get('status', '-'), error_reason(exc), (perf_counter() - started) * 1000,
                        query_details + ' ' if query_details else '', diagnostic.get('response_excerpt', ''))
            raise
        rows = data.get('events', data.get('incidents'))
        log.info('MaxPatrol HTTP completed: method=%s endpoint=%s status=%s duration_ms=%.1f rows=%s',
                 method, path, status, (perf_counter() - started) * 1000,
                 len(rows) if isinstance(rows, list) else '-')
        return data

    def _request(self, method, path, *, body=None, params=None):
        try:
            with warnings.catch_warnings():
                if not self.config.verify_tls:
                    if not self._insecure_notice_logged:
                        log.warning('MaxPatrol TLS certificate verification disabled: verify_tls=false; '
                                    'notice=once_per_poll')
                        self._insecure_notice_logged = True
                    host = re.escape(repr(urlsplit(self.config.url).hostname))
                    warnings.filterwarnings('ignore', category=InsecureRequestWarning,
                        message=r'Unverified HTTPS request is being made to host ' + host + r'\.',
                        module=r'(?:requests\.packages\.)?urllib3\.connectionpool')
                response = self.session.request(method, self.config.url + path,
                    headers={'Authorization': f'Bearer {self.config.token}', 'Accept': 'application/json',
                             'Content-Type': 'application/json'},
                    json=body, params=params, timeout=self.config.timeout,
                    verify=self.config.verify_tls, allow_redirects=False)
            if not 200 <= response.status_code < 300:
                raise SIEMError(f'MaxPatrol HTTP {response.status_code}', code=f'http_{response.status_code}',
                    diagnostic={'status': response.status_code,
                                **request_diagnostic(method, path, body, response.text, self.config.token)})
            # Filter each object during decoding, before collecting events or building the tree.
            data = response.json(object_pairs_hook=lambda pairs: {key: value for key, value in pairs if value is not None})
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
        return data, response.status_code

    def incidents(self, start, _end):
        offset = 0
        previous = None
        while True:
            data = self.request('POST', '/api/v2/incidents/', body={
                'offset': offset, 'limit': 50, 'groups': {'filterType': 'no_filter'},
                'timeFrom': timestamp(start), 'timeTo': None, 'filterTimeType': 'creation',
                'filter': {'select': INCIDENT_SELECT_FIELDS, 'where': 'status != "Closed"', 'orderby': [
                    {'field': 'created', 'sortOrder': 'descending'},
                    {'field': 'status', 'sortOrder': 'ascending'},
                    {'field': 'severity', 'sortOrder': 'descending'}]},
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


def event_uuid(event):
    meta = event.get('_meta') if isinstance(event.get('_meta'), dict) else {}
    try:
        return str(UUID(str(event.get('uuid') or meta.get('id'))))
    except (ValueError, TypeError, AttributeError):
        return None


def build_event_materials(rows, *, is_active=None):
    """Build links only from the supplied v3 response. Never make HTTP calls."""
    events, edges, errors, missing, unidentified = {}, {}, [], set(), []
    for row in rows:
        uid = event_uuid(row)
        if uid:
            events.setdefault(uid, row)
        else:
            unidentified.append(row)
            errors.append({'reason': 'event_reference_invalid'})
    for uid, row in events.items():
        if is_active and not is_active():
            errors.append({'reason': 'module_inactive'})
            break
        children = row.get('subevents') or []
        if not isinstance(children, list):
            children = []
            errors.append({'uuid': uid, 'reason': 'subevents_field_invalid'})
        child_ids = [event_uuid({'uuid': value}) for value in children]
        if any(value is None for value in child_ids):
            errors.append({'uuid': uid, 'reason': 'subevents_reference_invalid'})
        edges[uid] = list(dict.fromkeys(value for value in child_ids if value))
        missed = row.get('subevents.missed') or []
        if not isinstance(missed, list):
            missed = []
            errors.append({'uuid': uid, 'reason': 'subevents_missed_invalid'})
        for value in missed:
            child_id = event_uuid({'uuid': value})
            if child_id:
                missing.add(child_id)
            else:
                errors.append({'uuid': uid, 'reason': 'subevents_reference_invalid'})
        count = row.get('count.subevents') or 0
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            errors.append({'uuid': uid, 'reason': 'subevents_count_invalid'})
        elif count > len(edges[uid]):
            errors.append({'uuid': uid, 'reason': 'subevents_count_mismatch'})
    children_ids = {child for children in edges.values() for child in children}
    missing.update(children_ids - events.keys())
    missing.difference_update(events.keys())
    roots = [uid for uid in events if uid not in children_ids] or list(events)
    summary = {'version': 2, 'complete': not (errors or missing), 'root_count': len(rows),
               'event_count': len(events), 'missing_uuids': sorted(missing), 'errors': errors,
               'collected_at': timestamp(datetime.now(timezone.utc)), 'source': 'incident_events_v3'}
    log.info('MaxPatrol subevents summary: roots=%s events=%s missing=%s errors=%s complete=%s',
             len(rows), len(events), len(missing), len(errors), summary['complete'])
    if missing:
        log.warning('MaxPatrol v3 response has missing linked events: count=%s sample=%r; no additional API requests',
                    len(missing), sorted(missing)[:10])
    return {'events': [*events.values(), *unidentified],
            'event_tree': render_event_tree(roots, events, edges),
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

    result = [branch(uid) for uid in dict.fromkeys(root_ids) if uid]
    # Keep disconnected cyclic components visible as well as ordinary roots.
    result.extend(branch(uid) for uid in events if uid not in rendered)
    return result


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
    started = perf_counter()
    end = now or datetime.now(timezone.utc)
    start = end - timedelta(hours=min(config.lookback_hours, 24))
    successes = received = already_imported = failed = invalid = events_failed = refreshed = 0
    incomplete_incidents = 0
    closed_skipped = 0
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
            with logging_context(incident=incident_id):
                existing = False
                try:
                    existing = store.seen(incident_id)
                    if existing and not store.needs_event_refresh(incident_id):
                        already_imported += 1
                        continue
                    log.info('MaxPatrol incident import started: incident=%r', incident_id)
                    stored = store.stored_incident(incident_id) if existing else None
                    # List rows are authoritative for current selected fields. Keep
                    # previously collected extra fields when refreshing an alert.
                    detail = {**(stored if isinstance(stored, dict) else {}), **incident}
                    incident_source = 'incidents_list_v2' if not existing or len(incident) > 1 else 'saved_import'
                    if detail.get('status') == 'Closed':
                        closed_skipped += 1
                        log.info('MaxPatrol closed incident skipped: incident=%r', incident_id)
                        continue
                    log.info('MaxPatrol incident data loaded: source=%s fields=%s', incident_source, len(detail))
                    try:
                        event_start, event_end = incident_event_window(detail, start, end)
                        events = client.events(incident_id, event_start, event_end)
                        materials = build_event_materials(events, is_active=store.active)
                    except SIEMError as exc:
                        events_failed += 1
                        log.warning('MaxPatrol event retrieval failed: incident=%r reason=%s; importing without events',
                                    incident_id, error_reason(exc))
                        events = []
                        materials = {'events': [], 'event_collection': {'version': 2, 'complete': False,
                            'errors': [error_details(exc)], 'collected_at': timestamp(end)}}
                    materials['incident'] = detail
                    materials['incident_source'] = incident_source
                    materials['incident_refresh_error'] = None  # Clear obsolete card-GET failures.
                    event_state = materials['event_collection']
                    if not event_state['complete']:
                        incomplete_incidents += 1
                    log.info('MaxPatrol incident events received: incident=%r events=%s', incident_id, len(events))
                    if existing:
                        if store.refresh_events(incident_id, materials):
                            refreshed += 1
                            log.info('MaxPatrol incident events refreshed: incident=%r events=%s complete=%s '
                                     'missing=%s errors=%s', incident_id, len(materials['events']),
                                     event_state['complete'], len(event_state.get('missing_uuids', [])),
                                     len(event_state.get('errors', [])))
                        continue
                    store.create(incident_id, alert_payload(config, incident_id, detail, events, end,
                                                           event_materials=materials))
                    successes += 1
                    log.info('MaxPatrol incident imported: incident=%r events=%s complete=%s missing=%s errors=%s',
                             incident_id, len(materials['events']), event_state['complete'],
                             len(event_state.get('missing_uuids', [])), len(event_state.get('errors', [])))
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
                 'events_failed=%s complete=%s refreshed=%s incomplete_incidents=%s closed_skipped=%s duration_ms=%.1f',
                 received, successes, already_imported, failed, invalid, events_failed, complete, refreshed,
                 incomplete_incidents, closed_skipped, (perf_counter() - started) * 1000)
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
