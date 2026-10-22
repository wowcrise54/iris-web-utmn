"""IOC extraction is restricted to the MaxPatrol field allowlist."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'source'))
from iris_maxpatrol_module.iocs import extract_iocs, pending_iocs


def test_allowed_flat_and_nested_fields_and_hash_boundaries():
    content = {'events': [{'src.ip': '192.0.2.1', 'dst': {'ip': '198.51.100.2'},
        'object.hash': 'A' * 32 + ' ' + 'b' * 40 + ' ' + 'c' * 64,
        'ignored': '203.0.113.9', 'datafield1': '999.1.2.3 ' + 'd' * 65}]}
    found = extract_iocs(content)
    assert set(found) == {('ip-src', '192.0.2.1'), ('ip-dst', '198.51.100.2'),
                          ('md5', 'a' * 32), ('sha1', 'b' * 40), ('sha256', 'c' * 64)}
    assert found[('md5', 'a' * 32)] == ['object.hash']


def test_urls_domains_paths_and_lists():
    found = extract_iocs({'events': [{'dst.fqdn': ['Example.COM.', 'other.example.org'],
        'object.process.cmdline': 'curl https://Example.com/a?q=1 --out C:\\temp\\program.exe',
        'object.fullpath': 'C:\\Users\\a\\program.exe',
        'object.query': 'example.net', 'datafield2': '203.0.113.4'}]})
    assert ('url', 'https://Example.com/a?q=1') in found
    assert ('domain', 'example.com') in found
    assert ('domain', 'example.net') in found
    assert ('domain', 'program.exe') not in found
    assert ('ip-src', '203.0.113.4') in found


def test_refresh_deduplicates_and_does_not_restore_removed_iocs():
    alert = SimpleNamespace(alert_source='MaxPatrol EDR',
        alert_source_content={'events': [{'src.ip': '192.0.2.1'}]}, iocs=[])
    first, seen = pending_iocs(alert)
    assert len(first) == 1
    alert.alert_source_content['_iris_auto_iocs'] = seen
    assert pending_iocs(alert)[0] == {}
    alert.alert_source_content['events'].append({'dst.fqdn': 'new.example.org'})
    assert set(pending_iocs(alert)[0]) == {('domain', 'new.example.org')}
    alert.alert_source = 'Other SIEM'
    assert pending_iocs(alert)[0] == {}


def test_transient_ioc_with_type_id_is_not_duplicated():
    alert = SimpleNamespace(alert_source='MaxPatrol SIEM',
        alert_source_content={'object.hash': 'A' * 32},
        iocs=[SimpleNamespace(ioc_value='A' * 32, ioc_type=None, ioc_type_id=17)])
    assert pending_iocs(alert, {17: 'md5'})[0] == {}


def test_existing_manual_ioc_is_not_duplicated():
    alert = SimpleNamespace(alert_source='MaxPatrol SIEM',
        alert_source_content={'src.ip': '192.0.2.1'},
        iocs=[SimpleNamespace(ioc_value='192.0.2.1', ioc_type=SimpleNamespace(type_name='ip-src'))])
    assert pending_iocs(alert)[0] == {}
    alert.alert_source_content = {'object.hash.md5': 'A' * 32, 'dst.fqdn': 'EXAMPLE.COM'}
    alert.iocs = [SimpleNamespace(ioc_value=value, ioc_type=SimpleNamespace(type_name=kind))
                  for kind, value in [('md5', 'A' * 32), ('domain', 'EXAMPLE.COM.')]]
    assert pending_iocs(alert)[0] == {}
