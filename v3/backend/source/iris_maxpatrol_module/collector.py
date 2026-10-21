"""MaxPatrol API contract, independent of the IRIS application and worker."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import logging
from urllib.parse import quote, urlsplit

import requests

log = logging.getLogger(__name__)


class SIEMError(ValueError):
    """A bounded error that never contains a response body or credentials."""

    def __init__(self, message, *, code='siem_error'):
        super().__init__(message)
        self.code = code


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
                         'Content-Type': 'application/json; charset=UTF-8'},
                json=body, params=params, timeout=self.config.timeout,
                verify=self.config.verify_tls, allow_redirects=False)
            if not 200 <= response.status_code < 300:
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
        events, offset, previous = [], 0, None
        while True:
            data = self.request('POST', '/api/events/v2/events/',
                params={'incidentId': incident_id, 'offset': offset, 'limit': 250, 'noCount': 'true'},
                body={'filter': {'aggregateBy': [], 'aliases': None, 'distributeBy': [], 'groupBy': [],
                    'orderBy': [{'field': 'time', 'sortOrder': 'descending'}],
                    'select': EVENT_SELECT_FIELDS, 'top': None, 'where': ''},
                    'groupValues': [], 'timeFrom': int(start.timestamp()), 'timeTo': int(end.timestamp())})
            page = data.get('events')
            if not isinstance(page, list) or any(not isinstance(item, dict) for item in page):
                raise SIEMError('MaxPatrol events must be an array of objects')
            if page and page == previous:
                raise SIEMError('MaxPatrol did not advance the event page')
            log.info('MaxPatrol events page received: incident=%r offset=%s count=%s',
                     incident_id, offset, len(page))
            events.extend(item for value in page if (item := strip_nulls(value)))
            if len(page) < 250:
                return events
            previous, offset = page, offset + len(page)


def alert_payload(config, incident_id, detail, events, now):
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
        'alert_source_content': {'incident': detail, 'events': events},
    }


def collect(config, client, store, *, now=None):
    end = now or datetime.now(timezone.utc)
    start = end - timedelta(hours=config.lookback_hours)
    successes = received = already_imported = failed = invalid = events_failed = 0
    complete = False
    log.info('MaxPatrol collection started: customer=%s time_from=%s time_to=%s',
             config.customer_id, timestamp(start), timestamp(end))
    try:
        for incident in client.incidents(start, end):
            received += 1
            if not store.active():
                log.info('MaxPatrol collection stopped: module disabled or configuration changed')
                break
            incident_id = str(incident.get('id') or '').strip()
            if not incident_id or len(incident_id) > 512:
                invalid += 1
                log.warning('MaxPatrol incident without a valid id skipped')
                continue
            try:
                if store.seen(incident_id):
                    already_imported += 1
                    continue
                log.info('MaxPatrol incident import started: incident=%r', incident_id)
                detail = client.detail(incident_id)
                try:
                    events = client.events(incident_id, start, end)
                except SIEMError as exc:
                    events_failed += 1
                    log.warning('MaxPatrol event retrieval failed: incident=%r reason=%s; importing without events',
                                incident_id, error_reason(exc))
                    events = []
                log.info('MaxPatrol incident details received: incident=%r events=%s', incident_id, len(events))
                store.create(incident_id, alert_payload(config, incident_id, detail, events, end))
                successes += 1
                log.info('MaxPatrol incident imported: incident=%r', incident_id)
            except Exception as exc:
                store.rollback()
                if store.seen(incident_id):
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
                 'events_failed=%s complete=%s', received, successes, already_imported, failed, invalid,
                 events_failed, complete)
    return successes


INCIDENT_SELECT_FIELDS = ['key', 'name', 'category', 'type', 'status', 'created', 'assigned']
EVENT_SELECT_FIELDS = [
    'action',
    'alert.context',
    'alert.key',
    'alert.regex_match',
    'asset_ids',
    'assigned_dst_host',
    'assigned_dst_ip',
    'assigned_dst_port',
    'assigned_src_host',
    'assigned_src_ip',
    'assigned_src_port',
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
    'datafield2',
    'datafield3',
    'datafield4',
    'datafield5',
    'datafield6',
    'datafield7',
    'datafield8',
    'datafield9',
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
    'datafield20',
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
    'object.process.path',
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
    'site_address',
    'site_alias',
    'site_id',
    'site_name',
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
    'subject.process.path',
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
