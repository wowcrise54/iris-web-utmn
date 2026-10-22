"""Offline IOC candidates from explicitly selected MaxPatrol fields."""
import ipaddress
import re
from urllib.parse import urlsplit

FIELDS = (
    'src.ip', 'dst.ip', 'external_src.ip', 'external_dst.ip', 'event_src.ip',
    'dst.fqdn', 'object.query', 'external_dst.fqdn', 'external_src.fqdn',
    'datafield1', 'datafield2', 'object.fullpath', 'object.path',
    'object.process.hash.md5', 'object.process.hash.sha1', 'object.process.hash.sha256',
    'object.hash.md5', 'object.hash.sha1', 'object.hash.sha256',
    'object.process.cmdline', 'object.hash',
)
HASH = re.compile(r'(?<![\w])(?:[a-fA-F0-9]{64}|[a-fA-F0-9]{40}|[a-fA-F0-9]{32})(?![\w])')
IP = re.compile(r'(?<![\w.:])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![\w.]|:[0-9a-fA-F]*:)')
URL = re.compile(r'\b(?:https?|ftp)://[^\s<>"\x27]+', re.I)
DOMAIN = re.compile(r'(?<![\w@\\/.-])(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}(?![\w.-])')
FILE_SUFFIXES = {'exe', 'dll', 'sys', 'bat', 'cmd', 'ps1', 'sh', 'txt', 'log', 'json', 'xml', 'pdf', 'zip', 'doc', 'docx'}
STATE_KEY = '_iris_auto_iocs'


def _values(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _values(item)


def _lookup(row, field):
    if field in row:
        yield from _values(row[field])
    head, sep, tail = field.partition('.')
    if sep and isinstance(row.get(head), dict):
        yield from _lookup(row[head], tail)


def extract_iocs(content):
    found = {}

    def add(kind, value, field):
        fields = found.setdefault((kind, value), [])
        if field not in fields:
            fields.append(field)

    stack = [content]
    while stack:
        row = stack.pop()
        if isinstance(row, list):
            stack.extend(row)
            continue
        if not isinstance(row, dict):
            continue
        stack.extend(value for key, value in row.items() if key != STATE_KEY and isinstance(value, (dict, list)))
        for field in FIELDS:
            for value in _lookup(row, field):
                for match in HASH.finditer(value):
                    token = match.group().lower()
                    add({32: 'md5', 40: 'sha1', 64: 'sha256'}[len(token)], token, field)
                for match in IP.finditer(value):
                    try:
                        token = str(ipaddress.IPv4Address(match.group()))
                    except ValueError:
                        continue
                    add('ip-dst' if field in ('dst.ip', 'external_dst.ip') else 'ip-src', token, field)
                for match in URL.finditer(value):
                    token = match.group().rstrip('.,;)]}')
                    try:
                        parsed = urlsplit(token)
                        valid = parsed.hostname and parsed.port != 0
                    except ValueError:
                        valid = False
                    if valid:
                        add('url', token, field)
                        host = parsed.hostname.lower().rstrip('.')
                        if DOMAIN.fullmatch(host):
                            add('domain', host, field)
                for match in DOMAIN.finditer(value.rstrip('.')):
                    token = match.group().lower()
                    if len(token) <= 253 and (field.endswith('.fqdn') or token.rsplit('.', 1)[-1] not in FILE_SUFFIXES):
                        add('domain', token, field)
    return found


def pending_iocs(alert, type_names=None):
    source = re.sub(r'[^a-z0-9]', '', (alert.alert_source or '').lower())
    if source not in {'maxpatrolsiem', 'maxpatroledr'}:
        return {}, []
    content = alert.alert_source_content if isinstance(alert.alert_source_content, dict) else {}
    state = content.get(STATE_KEY)
    seen = {tuple(item) for item in (state if isinstance(state, list) else []) if isinstance(item, list) and len(item) == 2 and all(isinstance(v, str) for v in item)}
    existing = set()
    for ioc in alert.iocs:
        kind = ioc.ioc_type.type_name if ioc.ioc_type else (type_names or {}).get(ioc.ioc_type_id)
        if kind:
            value = ioc.ioc_value
            if kind in {'md5', 'sha1', 'sha256', 'domain'} and isinstance(value, str):
                value = value.lower().rstrip('.')
            existing.add((kind, value))
    found = extract_iocs(content)
    pending = {key: fields for key, fields in found.items() if key not in seen and key not in existing}
    return pending, [list(key) for key in sorted(seen | set(found))]
