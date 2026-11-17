"""Public API transport. Keep raw report fields, including vendor extensions."""
import json
import re
from urllib.parse import urlsplit

import requests


class SandboxError(Exception):
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
    p = urlsplit(url)
    if (p.scheme != 'https' or not p.hostname or p.username or p.password
            or p.query or p.fragment or p.path not in ('', '/api/v1')):
        raise SandboxError('Use an HTTPS address without credentials; /api/v1 is optional')
    return url if p.path else url + '/api/v1'


def log_references(report):
    """Only log entries, not executable artifacts or attacker-controlled URLs."""
    found = {}

    def visit(node):
        if isinstance(node, dict):
            for entry in node.get('logs', []) if isinstance(node.get('logs'), list) else []:
                if not isinstance(entry, dict):
                    continue
                uri = str(entry.get('file_uri') or '')[:200]
                found.setdefault(uri, dict(file_uri=uri, file_name=str(entry.get('file_name') or 'log')[:240],
                                           type=str(entry.get('type') or 'unknown')[:80]))
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)
    visit(report)
    return list(found.values())


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


class SandboxClient:
    def __init__(self, url, token, ca_bundle=None, *, verify_tls=True):
        self.url = validate_url(url)
        if not isinstance(token, str) or not token.strip() or '\n' in token or '\r' in token:
            raise SandboxError('PT Sandbox API token is required')
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update({'X-API-Key': token, 'Accept': 'application/json'})
        self.verify = (ca_bundle or True) if parse_verify_tls(verify_tls) else False

    def close(self):
        self.session.close()

    def request(self, path, *, method='POST', payload=None, file=None, limit=32 * 1024 * 1024):
        try:
            with self.session.request(method, self.url + '/' + path, json=payload, data=file,
                                      headers={'Content-Type': 'application/octet-stream'} if file else None,
                                      verify=self.verify, timeout=(10, 120), stream=True,
                                      allow_redirects=False) as response:
                if response.status_code != 200:
                    raise SandboxError(f'PT Sandbox HTTP {response.status_code}')
                chunks, size = [], 0
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > limit:
                        raise SandboxError('PT Sandbox response exceeds configured size limit')
                    chunks.append(chunk)
                raw = b''.join(chunks)
            if path == 'storage/downloadArtifact':
                return raw
            body = json.loads(raw)
            if not isinstance(body, dict) or body.get('errors') or not isinstance(body.get('data'), (dict, list)):
                raise SandboxError('PT Sandbox returned an error or invalid response')
            if path != 'engines/sandbox/getImages' and not isinstance(body['data'], dict):
                raise SandboxError('PT Sandbox returned an invalid response')
            return body['data']
        except (requests.RequestException, ValueError, TypeError):
            # Neither remote bodies nor request headers belong in application logs.
            raise SandboxError('PT Sandbox connection, TLS or response error') from None

    def check_connection(self):
        health = self.request('maintenance/checkHealth', method='GET')
        version = self.request('maintenance/getVersion', method='GET').get('version', '')
        images = self.request('engines/sandbox/getImages')
        return {'health': str(health.get('status', 'unknown'))[:80], 'version': str(version)[:80],
                'version_matches': bool(re.match(r'^5\.37(?:\.|$)', str(version))), 'images': images}

    def upload(self, file):
        data = self.request('storage/uploadScanFile', file=file)
        if not isinstance(data.get('file_uri'), str):
            raise SandboxError('PT Sandbox did not return a file URI')
        return data['file_uri']

    def start(self, file_uri, name, image_id, duration, passwords):
        data = self.request('analysis/createScanTask', payload={
            'file_uri': file_uri, 'file_name': name, 'async_result': True, 'short_result': False,
            'options': {'analysis_depth': 2, 'passwords_for_unpack': passwords,
                        'sandbox': {'enabled': True, 'image_id': image_id,
                                    'analysis_duration': duration, 'save_video': True}}})
        from uuid import UUID
        try:
            return str(UUID(data['scan_id']))
        except (KeyError, ValueError, TypeError):
            raise SandboxError('PT Sandbox did not return a valid scan ID') from None
