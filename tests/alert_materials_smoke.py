"""Local authenticated smoke test. Creates and removes only its own synthetic alert/case."""
import hashlib
import json
import sys
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import requests


def main():
    root = Path(__file__).resolve().parents[1]
    settings = {}
    for line in (root / '.env.v3.live').read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            settings[key] = value.strip().strip('"').strip("'")
    client = requests.Session()
    client.trust_env = False
    base = 'http://127.0.0.1:18082/api/v2'
    if '--https' in sys.argv:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        # Only the known local development endpoint uses its self-signed certificate.
        base = 'https://localhost:18543/api/v2'
        client.verify = False

    def call(method, url, expected=(200,), **kwargs):
        response = client.request(method, base + url, timeout=60, **kwargs)
        if response.status_code not in expected:
            # No request body or credential-bearing response is logged.
            raise AssertionError(f'{method} {url}: HTTP {response.status_code}; {response.text[:300]}')
        return response

    auth = call('POST', '/auth/login', json={'username': 'administrator',
                                           'password': settings['IRIS_ADM_PASSWORD']}).json()
    client.headers['Authorization'] = 'Bearer ' + auth['tokens']['access_token']
    template = call('GET', '/alerts/1').json()
    marker = '[SMOKE alert-materials ' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + ']'
    alert_id = case_id = ioc_id = None
    results = []
    try:
        alert = call('POST', '/alerts', expected=(200, 201), json={
            'alert_title': marker, 'alert_description': 'Temporary feature validation',
            'alert_customer_id': template['alert_customer_id'],
            'alert_severity_id': template['alert_severity_id'],
            'alert_status_id': template['alert_status_id'],
            'alert_owner_id': auth['id'], 'alert_source': 'feature-smoke',
            'alert_source_event_time': datetime.now(timezone.utc).isoformat(),
        }).json()
        alert_id = alert['alert_id']
        prefix = f'/alerts/{alert_id}'
        types = call('GET', '/manage/case-objects/ioc-types?per_page=10000').json()['data']
        domain = next(t for t in types if t['type_name'].lower() == 'domain')
        tlp = call('GET', '/manage/tlp?per_page=10000').json()['data'][0]
        ioc = call('POST', prefix + '/iocs', json={'ioc_value': 'smoke-alert.example',
                   'ioc_type_id': domain['type_id'], 'ioc_tlp_id': tlp['tlp_id']}).json()
        ioc_id = int(ioc['ioc_id'])
        results.append('IOC creation')
        process = call('POST', prefix + '/artifacts', json={'kind': 'process', 'value': 'test-process.exe',
                        'description': 'Synthetic observation'}).json()
        call('PUT', prefix + f'/artifacts/{process["id"]}', json={'kind': 'command', 'value': 'whoami',
             'description': 'Updated synthetic observation', 'include_in_case': False})
        content = b'\xd4\xc3\xb2\xa1\x02\x00\x04\x00synthetic-pcap'
        file = call('POST', prefix + '/artifacts', files={'file': ('sample.pcap', content)},
                    data={'description': 'Synthetic PCAP', 'include_in_case': 'true'}).json()
        assert file['sha256'] == hashlib.sha256(content).hexdigest()
        downloaded = call('GET', prefix + f'/artifacts/{file["id"]}/content')
        assert downloaded.content == content
        assert downloaded.headers['Content-Disposition'].startswith('attachment;')
        assert 'nosniff' in downloaded.headers['X-Content-Type-Options'].lower().split(', ')
        results.append('File round trip, SHA-256, safe attachment headers; structured edit')
        call('PUT', prefix, json={'iocs': [], 'artifacts': []})
        assert len(call('GET', prefix).json()['iocs']) == 1
        results.append('Generic update cannot replace materials')
        call('PUT', prefix, json={'alert_owner_id': -1})
        call('POST', prefix + '/artifacts', expected=(403,), json={'kind': 'command', 'value': 'denied'})
        call('DELETE', prefix + f'/iocs/{ioc["ioc_id"]}', expected=(403,))
        call('PUT', prefix + f'/iocs/{ioc["ioc_id"]}', expected=(403,), json={'ioc_description': 'denied'})
        call('DELETE', prefix + f'/artifacts/{file["id"]}', expected=(403,))
        assert call('GET', prefix + f'/artifacts/{file["id"]}/content').content == content
        call('PUT', prefix, json={'alert_owner_id': auth['id']})
        results.append('Unassigned alert denies material writes, permits authorized reads')
        call('PUT', prefix + f'/iocs/{ioc["ioc_id"]}', json={'ioc_description': 'Edited by owner'})
        call('DELETE', prefix + f'/iocs/{ioc["ioc_id"]}')
        assert not call('GET', prefix).json()['iocs']
        results.append('Owner IOC edit and unlink')
        case = call('POST', f'/alerts/escalate/{alert_id}', expected=(200, 201), json={
            'case_title': marker, 'import_as_event': False, 'iocs_import_list': [], 'assets_import_list': []}).json()
        case_id = case['case_id']
        listing = call('GET', f'/cases/{case_id}/datastore/files').json()
        assert listing['total'] == 1
        copied_file = listing['data'][0]
        assert copied_file['file_original_name'] == 'sample.pcap'
        assert call('GET', f'/cases/{case_id}/datastore/files/{copied_file["file_id"]}').content == content
        call('DELETE', prefix + f'/artifacts/{process["id"]}')
        call('DELETE', prefix, expected=(200, 204))
        alert_id = None
        assert call('GET', f'/cases/{case_id}/datastore/files/{copied_file["file_id"]}').content == content
        results.append('Only selected artifact copied to case; case bytes survive alert deletion')
        results.append('Artifact and alert deletion')
        print(json.dumps({'status': 'passed', 'checks': results}, ensure_ascii=False))
    finally:
        if alert_id is not None:
            call('DELETE', f'/alerts/{alert_id}', expected=(200, 204))
        if case_id is not None:
            call('DELETE', f'/cases/{case_id}', expected=(200, 204))
        if ioc_id is not None:
            # Unlink intentionally keeps the IOC in the registry; remove only this test's exact row.
            sql = (f"DELETE FROM ioc WHERE ioc_id={ioc_id} AND ioc_value='smoke-alert.example' "
                   "AND case_id IS NULL AND NOT EXISTS (SELECT 1 FROM alert_iocs_association a "
                   "WHERE a.ioc_id=ioc.ioc_id)")
            subprocess.run(['docker', 'exec', 'iris-upgrade-2-4-29-fastapi-db-1',
                            'psql', '-U', 'postgres', '-d', 'iris_db', '-c', sql],
                           check=True, stdout=subprocess.DEVNULL)


if __name__ == '__main__':
    main()
