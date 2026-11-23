"""Streamable HTTP client for the built-in PT Sandbox MCP server."""
from datetime import datetime
import json
from uuid import UUID
from urllib.parse import urlsplit

import requests


class SandboxError(Exception):
    pass


class SandboxResponseTooLarge(SandboxError):
    pass


def parse_verify_tls(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ('true', 'false'):
        return value.strip().lower() == 'true'
    raise SandboxError('TLS verification must be true or false')


def validate_url(value):
    if not isinstance(value, str):
        raise SandboxError('PT Sandbox URL is required')
    url = value.strip().rstrip('/')
    try:
        p = urlsplit(url)
        p.port
    except ValueError:
        raise SandboxError("Invalid PT Sandbox MCP address") from None
    if (p.scheme != 'https' or not p.hostname or p.username or p.password
            or p.query or p.fragment or p.path not in ('', '/mcp')):
        raise SandboxError('Use an HTTPS address without credentials; /mcp is optional')
    return url if p.path else url + '/mcp'


def report_summary(report):
    result = report.get('result', {}) if isinstance(report, dict) else {}
    detections = []

    def visit(node):
        if isinstance(node, dict):
            for item in node.get('detections', []) if isinstance(node.get('detections'), list) else []:
                name = item.get('detect') if isinstance(item, dict) else None
                if isinstance(name, str) and name not in detections and len(detections) < 8:
                    detections.append(name[:160])
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)
    visit(report)
    return {'verdict': result.get('verdict'), 'threat': result.get('threat'),
            'scan_state': result.get('scan_state'), 'detections': detections}


def decode_rows(result):
    try:
        if result.get('isError'):
            raise ValueError
        structured = result.get('structuredContent')
        raw = structured['result'] if structured is not None else result['content'][0]['text']
        data = json.loads(raw)
        columns, rows = data['columns'], data['rows']
        if (not isinstance(columns, list) or not all(isinstance(c, str) for c in columns)
                or len(set(columns)) != len(columns) or not isinstance(rows, list)):
            raise ValueError
        if not all(isinstance(row, list) for row in rows):
            raise ValueError
        return [dict(zip(columns, row, strict=True)) for row in rows]
    except (KeyError, IndexError, AttributeError, TypeError, ValueError):
        raise SandboxError('PT Sandbox MCP returned an invalid query result') from None


class SandboxClient:
    def __init__(self, url, token, ca_bundle=None, *, verify_tls=True):
        self.url = validate_url(url)
        if not isinstance(token, str) or not token.strip() or any(c in token for c in ('\n', '\r')):
            raise SandboxError('PT Sandbox MCP token is required')
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update({'Authorization': f'Bearer {token}',
                                     'Accept': 'application/json, text/event-stream'})
        self.verify = (ca_bundle or True) if parse_verify_tls(verify_tls) else False
        self.request_id = 0

    def close(self):
        try:
            if 'Mcp-Session-Id' in self.session.headers:
                with self.session.delete(self.url, verify=self.verify, timeout=(3, 3),
                                         allow_redirects=False, stream=True):
                    pass
        except requests.RequestException:
            pass
        finally:
            self.session.close()

    def _rpc(self, method, params=None, *, notification=False):
        body = {'jsonrpc': '2.0', 'method': method}
        if params is not None:
            body['params'] = params
        if not notification:
            self.request_id += 1
            body['id'] = self.request_id
        try:
            with self.session.post(self.url, json=body, verify=self.verify, timeout=(5, 15),
                                   stream=True, allow_redirects=False) as response:
                expected = 202 if notification else 200
                if response.status_code != expected:
                    raise SandboxError(f'PT Sandbox MCP HTTP {response.status_code}')
                if notification:
                    return None
                if method == 'initialize' and response.headers.get('Mcp-Session-Id'):
                    self.session.headers['Mcp-Session-Id'] = response.headers['Mcp-Session-Id']
                sse = response.headers.get('Content-Type', '').split(';')[0].strip() == 'text/event-stream'
                for message in self._messages(response, sse):
                    if message.get('id') != body['id']:
                        continue
                    if (message.get('jsonrpc') != '2.0' or 'error' in message
                            or not isinstance(message.get('result'), dict)):
                        raise SandboxError('PT Sandbox MCP rejected the request')
                    return message['result']
        except (requests.RequestException, ValueError, AttributeError, TypeError):
            raise SandboxError('PT Sandbox MCP connection, TLS or response error') from None
        raise SandboxError('PT Sandbox MCP response did not contain the requested result')

    @staticmethod
    def _messages(response, sse):
        total = 0
        pending = bytearray()
        event = []
        for chunk in response.iter_content(8192):
            total += len(chunk)
            if total > 1024 * 1024:
                raise SandboxResponseTooLarge('PT Sandbox MCP response exceeds 1 MiB')
            pending.extend(chunk)
            if sse:
                while (newline := pending.find(b'\n')) >= 0:
                    line = bytes(pending[:newline]).rstrip(b'\r')
                    del pending[:newline + 1]
                    if line.startswith(b'data:'):
                        event.append(line[5:].lstrip(b' '))
                    elif not line and event:
                        yield json.loads(b'\n'.join(event))
                        event.clear()
        if not sse:
            yield json.loads(pending)

    def connect(self):
        result = self._rpc('initialize', {
            'protocolVersion': '2025-03-26', 'capabilities': {},
            'clientInfo': {'name': 'IRIS PT Sandbox', 'version': '2.0.0'},
        })
        version = result.get('protocolVersion')
        if version not in ('2025-03-26', '2025-06-18', '2025-11-25'):
            raise SandboxError('Unsupported PT Sandbox MCP protocol version')
        self.session.headers['MCP-Protocol-Version'] = version
        self._rpc('notifications/initialized', notification=True)

    def query(self, sql):
        return decode_rows(self._rpc('tools/call', {'name': 'run_query', 'arguments': {'query': sql}}))

    def check_connection(self, database):
        self.connect()
        tools = self._rpc('tools/list').get('tools', [])
        if not any(isinstance(tool, dict) and tool.get('name') == 'run_query' for tool in tools):
            raise SandboxError('PT Sandbox MCP does not offer run_query')
        if self.query('SELECT 1 AS connection_ok') != [{'connection_ok': 1}]:
            raise SandboxError('PT Sandbox MCP connection query returned an unexpected result')
        self.query(self.task_sql(database, UUID(int=0), datetime(2000, 1, 1)))
        return {'ok': True}

    TASK_COLUMNS = (
        "toString(toTimeZone(start, 'UTC')) AS started_utc, toString(scan_id) AS sid, "
        "status, action, entry_point_type, object_type, object_name, "
        "correlated_verdict_threat_level AS verdict, correlated_verdict_priority AS priority, verdict_is_final"
    )

    @staticmethod
    def scan_filter(database, scan_id, start):
        if database not in ('scans_v2', 'scans_v2_repl'):
            raise SandboxError('Unknown PT Sandbox database')
        scan_id = UUID(str(scan_id))
        start = start.strftime('%Y-%m-%d %H:%M:%S')
        return f"start = toDateTime('{start}', 'UTC') AND scan_id = toUUID('{scan_id}')"

    @classmethod
    def task_sql(cls, database, scan_id, start):
        where = cls.scan_filter(database, scan_id, start)
        return f'SELECT {cls.TASK_COLUMNS} FROM {database}.tasks FINAL WHERE {where} LIMIT 1'

    @classmethod
    def search_sql(cls, database, name, days):
        if database not in ('scans_v2', 'scans_v2_repl'):
            raise SandboxError('Unknown PT Sandbox database')
        if type(days) is not int or not 1 <= days <= 90:
            raise SandboxError('Search window must be between 1 and 90 days')
        literal = name.encode('utf-8').hex()
        return (
            f'SELECT {cls.TASK_COLUMNS} FROM {database}.tasks FINAL '
            f'WHERE start >= now() - INTERVAL {days} DAY '
            f"AND positionCaseInsensitiveUTF8(object_name, unhex('{literal}')) > 0 "
            'ORDER BY start DESC, scan_id DESC LIMIT 30'
        )

    def task_events(self, database, scan_id, start):
        where = self.scan_filter(database, scan_id, start) + " AND type != 'netpacket'"
        table = f'{database}.ba_events'
        counts = self.query(f'SELECT type, count() AS c FROM {table} WHERE {where} GROUP BY type ORDER BY c DESC')
        total = sum(int(row['c']) for row in counts)
        events = []
        if total:
            fields = (
                "toString(toTimeZone(create_time, 'UTC')) AS t, type, node_id, stage_index, pid, target_pid, "
                "name, arguments, process_action, process_name, ip, url, host, port, src_ip, dst_ip, country, "
                "key, key_data, value, description, detect_name, mitre_threat_id, confidence"
            )
            sql = (f'SELECT {fields} FROM {table} WHERE {where} '
                   'ORDER BY create_time, node_id, stage_index, type')
            limit = min(400, total)
            while True:
                try:
                    events = self.query(f'{sql} LIMIT {limit}')
                    break
                except SandboxResponseTooLarge:
                    if limit == 1:
                        raise
                    limit = max(1, limit // 2)
        return {'counts': counts, 'total': total, 'events': events, 'truncated': len(events) < total}
