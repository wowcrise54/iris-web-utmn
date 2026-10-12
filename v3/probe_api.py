"""Read-only API smoke checks against the isolated v3 rehearsal."""
import json
from pathlib import Path
import requests
import os

root = Path(__file__).resolve().parents[1]
env_file = root / '.env.v3.validation'
env = dict(line.split('=', 1) for line in env_file.read_text(encoding='utf-8').splitlines() if '=' in line) if env_file.exists() else os.environ
base = os.environ.get('IRIS_PROBE_URL', 'http://127.0.0.1:18084')
session = requests.Session()
session.trust_env = False
report = {}

response = session.get(base + '/api/v2/manage/server/authentication-settings', timeout=30)
report['auth_settings'] = response.status_code
response.raise_for_status()
response = session.post(base + '/api/v2/auth/login', json={
    'username': 'administrator', 'password': env['IRIS_ADM_PASSWORD']
}, timeout=30)
report['login'] = response.status_code
response.raise_for_status()
payload = response.json()
data = payload.get('data', payload)
token = data['tokens']['access_token']
session.headers['Authorization'] = 'Bearer ' + token
for path in ['/api/v2/auth/whoami', '/api/v2/cases', '/api/v2/cases/2',
             '/api/v2/alerts', '/api/v2/alerts/1', '/api/v2/war-rooms',
             '/api/v2/alert-clusters', '/api/v2/investigation-flows',
             '/api/v2/custom-dashboards']:
    response = session.get(base + path, timeout=30)
    report[path] = response.status_code
    if response.status_code != 200:
        print(path, 'status', response.status_code, 'message', response.text[:150])
    else:
        payload = response.json()
        body = payload.get('data', payload) if isinstance(payload, dict) else payload
        print(path, '200', 'shape', list(body)[:8] if isinstance(body, dict) else type(body).__name__)
print(json.dumps(report, indent=2))
Path(os.environ.get('IRIS_PROBE_REPORT', str(root / 'v3/api-probe.json'))).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
assert all(value == 200 for value in report.values()), 'API smoke check failed'
