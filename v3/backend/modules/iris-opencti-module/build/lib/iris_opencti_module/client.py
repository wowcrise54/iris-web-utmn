"""Read-only OpenCTI GraphQL client. Values are variables, never query text."""
import ipaddress
import json
import logging
import os
from uuid import uuid4
import re
import socket
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from time import monotonic


class OpenCTIError(Exception):
    def __init__(self, status):
        self.status = status
        super().__init__(f'OpenCTI: {status}')


def normalize_ioc(kind, raw):
    if not isinstance(raw, str):
        raise ValueError('Invalid IOC value')
    kind, value = str(kind).lower().strip(), str(raw).strip()
    if not value or len(value) > 8192:
        raise ValueError('Invalid IOC value')
    if kind in ('ip-src', 'ip-dst', 'ip', 'ipv4', 'ipv6', 'ipv4-addr', 'ipv6-addr'):
        ip = ipaddress.ip_address(value)
        if kind in ('ipv4', 'ipv4-addr') and ip.version != 4 or kind in ('ipv6', 'ipv6-addr') and ip.version != 6:
            raise ValueError('IP version mismatch')
        return f'IPv{ip.version}-Addr', ip.compressed, 'value'
    if kind in ('domain', 'domain-name', 'hostname'):
        value = value.rstrip('.').encode('idna').decode('ascii').lower()
        if len(value) > 253 or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in value.split('.')):
            raise ValueError('Invalid domain')
        return ('Hostname' if kind == 'hostname' else 'Domain-Name'), value, 'value'
    if kind in ('url', 'uri'):
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in ('http', 'https') or not parsed.hostname:
            raise ValueError('Invalid URL')
        # Path and query are case sensitive; do not lower-case the complete URL.
        return 'Url', value, 'value'
    if kind in ('email', 'email-src', 'email-dst', 'email-addr'):
        local, separator, domain = value.rpartition('@')
        if not separator or not local or any(c.isspace() for c in value):
            raise ValueError('Invalid email')
        return 'Email-Addr', f'{local}@{normalize_ioc("domain", domain)[1]}', 'value'
    hashes = {'md5': ('MD5', 32), 'sha1': ('SHA-1', 40), 'sha-1': ('SHA-1', 40),
              'sha256': ('SHA-256', 64), 'sha-256': ('SHA-256', 64),
              'sha512': ('SHA-512', 128), 'sha-512': ('SHA-512', 128)}
    if kind in hashes:
        algorithm, length = hashes[kind]
        if not re.fullmatch('[a-fA-F0-9]{' + str(length) + '}', value):
            raise ValueError('Invalid hash')
        return 'StixFile', value.lower(), 'hashes.' + algorithm
    raise ValueError('Unsupported IOC type')


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def indicator_validity(indicator):
    if indicator.get('revoked'):
        return 'revoked'
    now = datetime.now(timezone.utc)
    try:
        for field, state, predicate in (
            ('valid_until', 'expired', lambda value: value <= now),
            ('valid_from', 'not_yet_valid', lambda value: value > now),
        ):
            if indicator.get(field):
                value = datetime.fromisoformat(indicator[field].replace('Z', '+00:00'))
                if predicate(value):
                    return state
    except (ValueError, TypeError):
        return 'unknown'
    return 'active'


def nodes(connection):
    return [edge['node'] for edge in (connection or {}).get('edges', []) if edge.get('node')]


COMMON_FIELDS = '''id entity_type
    createdBy { ... on Identity { name } }
    objectMarking { definition }
    externalReferences { edges { node { source_name url } } }'''
INDICATOR_FIELDS = COMMON_FIELDS + ''' name description pattern pattern_type confidence
    revoked valid_from valid_until x_opencti_score x_opencti_detection
    killChainPhases { kill_chain_name phase_name }'''
OBSERVABLE_QUERY = '''query IrisOpenCTI($types: [String], $filters: FilterGroup, $after: ID) {
  stixCyberObservables(types: $types, filters: $filters, first: 100, after: $after) {
    edges { node { ''' + COMMON_FIELDS + ''' observable_value x_opencti_description x_opencti_score
      ... on StixFile { hashes { algorithm hash } }
      indicators(first: 100) { edges { node { ''' + INDICATOR_FIELDS + ''' } } pageInfo { hasNextPage } }
    } } pageInfo { hasNextPage endCursor }
  }
}'''
INDICATOR_QUERY = '''query IrisOpenCTIIndicators($filters: FilterGroup, $after: ID) {
  indicators(filters: $filters, first: 100, after: $after) {
    edges { node { ''' + INDICATOR_FIELDS + ''' } } pageInfo { hasNextPage endCursor }
  }
}'''
RELATION_QUERY = '''query IrisOpenCTIRelations($ids: [String], $after: ID) {
  stixCoreRelationships(fromOrToId: $ids, first: 100, after: $after) {
    edges { node { id relationship_type
      from {
        ... on StixObject { id entity_type }
        ... on StixRelationship { id entity_type }
        ... on Creator { id entity_type }
      }
      to {
        ... on StixObject { id entity_type }
        ... on StixRelationship { id entity_type }
        ... on Creator { id entity_type }
        ... on Malware { name } ... on Tool { name } ... on Campaign { name }
        ... on IntrusionSet { name } ... on AttackPattern { name }
        ... on ThreatActorGroup { name }
      }
    } } pageInfo { hasNextPage endCursor }
  }
}'''


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class OpenCTIClient:
    def __init__(self, url, token, timeout=10, is_active=None):
        try:
            if not isinstance(url, str) or any(c in url for c in '\r\n') or not isinstance(token, str):
                raise ValueError()
            parsed = urlsplit(url)
            if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError()
            parsed.port
            if not token or any(c in token for c in '\r\n'):
                raise ValueError()
        except ValueError:
            raise OpenCTIError('configuration_error') from None
        self.url = url.rstrip('/')
        self.token = token
        self.timeout = timeout
        self.is_active = is_active
        self.deadline = None
        self.opener = build_opener(ProxyHandler({}), _NoRedirect())

    def _trace(self, direction, request_id, body, http_status=None, clock=None):
        log = logging.getLogger(__name__)
        if not (os.environ.get('IRIS_OPENCTI_LOG_LEVEL', '').upper() == 'TRACE'
                or os.environ.get('IRIS_OPENCTI_LOG_PAYLOADS', '').lower() == 'true'):
            return
        if not log.isEnabledFor(logging.DEBUG):
            return
        # Redact before truncating, including JSON-escaped appearances of the token.
        body = body.decode('utf-8', errors='replace') if isinstance(body, bytes) else body
        for token in (json.dumps(self.token)[1:-1], self.token):
            body = body.replace(token, '[REDACTED]')
        truncated = len(body) > 16384
        log.debug('OpenCTI TRACE %s request_id=%s http_status=%s duration_ms=%.1f truncated=%s body=%s',
                  direction, request_id, http_status, (monotonic() - clock) * 1000,
                  str(truncated).lower(), json.dumps(body[:16384], ensure_ascii=True))

    def query(self, document, variables):
        log = logging.getLogger(__name__)
        operation = {OBSERVABLE_QUERY: 'observables', INDICATOR_QUERY: 'indicators',
                     RELATION_QUERY: 'relationships'}.get(document, 'connection')
        clock = monotonic()
        log.debug('OpenCTI request_started operation=%s', operation)
        try:
            result = self._query(document, variables, uuid4().hex)
        except OpenCTIError as error:
            log.warning('OpenCTI request_failed operation=%s status=%s duration_ms=%.1f',
                        operation, error.status, (monotonic() - clock) * 1000)
            raise
        log.debug('OpenCTI request_completed operation=%s duration_ms=%.1f',
                  operation, (monotonic() - clock) * 1000)
        return result

    def _query(self, document, variables, request_id):
        if self.is_active is not None and not self.is_active():
            raise OpenCTIError('disabled')
        request = Request(self.url + '/graphql',
                          data=json.dumps({'query': document, 'variables': variables}).encode(),
                          headers={'Authorization': f'Bearer {self.token}', 'Content-Type': 'application/json'})
        clock = monotonic()
        self._trace('request', request_id, request.data, clock=clock)
        try:
            remaining = self.deadline - monotonic() if self.deadline else self.timeout
            if remaining <= 0:
                raise OpenCTIError('timeout')
            with self.opener.open(request, timeout=min(self.timeout, remaining)) as response:
                raw = response.read(4 * 1024 * 1024 + 1)
                self._trace('response', request_id, raw, response.status, clock)
            if len(raw) > 4 * 1024 * 1024:
                raise OpenCTIError('response_too_large')
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise OpenCTIError('invalid_response')
            if payload.get('errors'):
                codes = {e.get('extensions', {}).get('code') for e in payload['errors'] if isinstance(e, dict)}
                if codes & {'UNAUTHENTICATED', 'FORBIDDEN', 'AUTH_REQUIRED'}:
                    raise OpenCTIError('unauthorized')
                raise OpenCTIError('schema_error')
            if not isinstance(payload.get('data'), dict):
                raise OpenCTIError('invalid_response')
            return payload['data']
        except HTTPError as error:
            status = 'unauthorized' if error.code in (401, 403) else 'unavailable' if error.code >= 500 else 'http_error'
            try:
                # Only read error bodies when payload logging is enabled.
                if (os.environ.get('IRIS_OPENCTI_LOG_LEVEL', '').upper() == 'TRACE'
                        or os.environ.get('IRIS_OPENCTI_LOG_PAYLOADS', '').lower() == 'true'):
                    self._trace('response', request_id, error.read(16384 + len(self.token) * 6 + 1), error.code, clock)
            except (OSError, ValueError):
                pass
            finally:
                error.close()
            raise OpenCTIError(status) from None
        except (TimeoutError, socket.timeout):
            raise OpenCTIError('timeout') from None
        except URLError as error:
            raise OpenCTIError('timeout' if isinstance(error.reason, TimeoutError) else 'unavailable') from None
        except OSError:
            raise OpenCTIError('unavailable') from None
        except (ValueError, UnicodeError):
            raise OpenCTIError('invalid_response') from None

    def pages(self, query, key, variables):
        after = None
        for page_number in range(1, 11):
            connection = self.query(query, {**variables, 'after': after}).get(key)
            if not isinstance(connection, dict):
                raise OpenCTIError('invalid_response')
            logging.getLogger(__name__).debug('OpenCTI page_received connection=%s page=%d items=%d',
                                               key, page_number, len(nodes(connection)))
            yield connection
            page = connection.get('pageInfo', {})
            if not page.get('hasNextPage'):
                return
            if not page.get('endCursor') or page['endCursor'] == after:
                raise OpenCTIError('pagination_error')
            after = page['endCursor']
        raise OpenCTIError('result_limit')

    @staticmethod
    def filters(key, value):
        return {'mode': 'and', 'filters': [{'key': [key], 'values': [value], 'operator': 'eq', 'mode': 'or'}], 'filterGroups': []}

    def lookup(self, kind, raw):
        self.deadline = monotonic() + 30
        entity_type, value, field = normalize_ioc(kind, raw)
        observables, indicators = {}, {}
        partial = False
        for connection in self.pages(OBSERVABLE_QUERY, 'stixCyberObservables', {
            'types': [entity_type], 'filters': self.filters(field, value)
        }):
            for observable in nodes(connection):
                if observable.get('entity_type') != entity_type:
                    continue
                candidate = observable.get('observable_value', '')
                if field.startswith('hashes.'):
                    algorithm = field.split('.', 1)[1]
                    matches = any(h.get('algorithm') == algorithm and str(h.get('hash', '')).lower() == value for h in observable.get('hashes', []))
                else:
                    try:
                        matches = normalize_ioc(kind, candidate)[1] == value
                    except ValueError:
                        matches = False
                if not matches:
                    continue
                observable = dict(observable)
                linked = observable.pop('indicators', {})
                partial |= linked.get('pageInfo', {}).get('hasNextPage', False)
                for indicator in nodes(linked):
                    indicators[indicator['id']] = {**indicator, 'match_method': 'linked_observable'}
                observable['url'] = self.url + '/dashboard/observations/observables/' + quote(observable['id'], safe='')
                observables[observable['id']] = observable

        # Exact simple STIX indicators can exist without a linked Observable.
        attribute = f"hashes.'{field.split('.', 1)[1]}'" if field.startswith('hashes.') else 'value'
        stix_type = 'file' if entity_type == 'StixFile' else entity_type.lower()
        escaped = value.replace('\\', '\\\\').replace("'", "\\'")
        pattern = f"[{stix_type}:{attribute} = '{escaped}']"
        for connection in self.pages(INDICATOR_QUERY, 'indicators', {'filters': self.filters('pattern', pattern)}):
            for indicator in nodes(connection):
                if indicator.get('pattern') == pattern and indicator.get('pattern_type') == 'stix':
                    indicators[indicator['id']] = {**indicator, 'match_method': 'exact_stix_pattern'}

        for indicator in indicators.values():
            indicator['validity'] = indicator_validity(indicator)
            indicator['url'] = self.url + '/dashboard/observations/indicators/' + quote(indicator['id'], safe='')
        relations = {}
        ids = list(observables) + list(indicators)
        if ids:
            for connection in self.pages(RELATION_QUERY, 'stixCoreRelationships', {'ids': ids}):
                for relation in nodes(connection):
                    relations[relation['id']] = relation
        return {'status': 'partial' if partial else 'matched' if ids else 'no_match',
                'observables': list(observables.values()), 'indicators': list(indicators.values()),
                'relationships': list(relations.values())}

    def check_connection(self):
        self.query('query IrisOpenCTIConnection { about { version } }', {})
        self.lookup('domain', 'iris-opencti-connectivity-check.invalid')
        self.query(RELATION_QUERY, {'ids': ['00000000-0000-0000-0000-000000000000'], 'after': None})
