"""Transport and worker failure contracts without booting IRIS or contacting an appliance."""
import ast
from datetime import datetime
import gzip
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

SOURCE = Path(__file__).parents[2] / 'source'


@pytest.fixture
def client_module():
    spec = importlib.util.spec_from_file_location('ptsandbox_transport_test', SOURCE / 'app/iris_engine/ptsandbox/client.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Response:
    def __init__(self, body, status=200, headers=None):
        self.status_code = status
        self.headers = headers or {}
        self.raw = body if isinstance(body, bytes) else json.dumps(body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def iter_content(self, size):
        for start in range(0, len(self.raw), size):
            yield self.raw[start:start + size]


def client_with_response(module, response):
    client = module.SandboxClient('https://sandbox.test', 'private-token')
    client.session.post = Mock(return_value=response)
    return client


@pytest.mark.parametrize('url', ['http://sandbox.test', 'https://u:p@sandbox.test',
                               'https://sandbox.test?key=x', 'https://sandbox.test/path',
                               'https://sandbox.test/#x', None])
def test_only_validated_https_appliance_addresses(client_module, url):
    with pytest.raises(client_module.SandboxError):
        client_module.validate_url(url)


def test_mcp_handshake_and_sse_query(client_module):
    client = client_module.SandboxClient('https://sandbox.test', 'private-token')
    result = {'columns': ['status', 'verdict_is_final'], 'rows': [['SUCCESS', 1]]}
    message = {'jsonrpc': '2.0', 'id': 2, 'result': {
        'structuredContent': {'result': json.dumps(result)}, 'isError': False,
    }}
    responses = [
        Response({'jsonrpc': '2.0', 'id': 1, 'result': {'protocolVersion': '2025-03-26'}},
                 headers={'Mcp-Session-Id': 'test-session'}),
        Response(b'', 202),
        Response(('event: message\r\ndata: ' + json.dumps(message) + '\r\n\r\n').encode(),
                 headers={'Content-Type': 'text/event-stream; charset=utf-8'}),
    ]
    client.session.post = Mock(side_effect=responses)
    client.session.delete = Mock(return_value=Response(b''))
    client.connect()
    assert client.query('SELECT 1') == [{'status': 'SUCCESS', 'verdict_is_final': 1}]
    calls = client.session.post.call_args_list
    assert [call.kwargs['json']['method'] for call in calls] == [
        'initialize', 'notifications/initialized', 'tools/call',
    ]
    assert 'id' not in calls[1].kwargs['json']
    assert calls[2].kwargs['json']['params'] == {'name': 'run_query', 'arguments': {'query': 'SELECT 1'}}
    assert all(call.args == ('https://sandbox.test/mcp',) and not call.kwargs['allow_redirects']
               for call in calls)
    assert client.session.headers['Authorization'] == 'Bearer private-token'
    assert client.session.headers['Mcp-Session-Id'] == 'test-session'
    assert client.session.headers['MCP-Protocol-Version'] == '2025-03-26'
    assert client.session.trust_env is False
    client.close()
    assert client.session.delete.call_args.args == ('https://sandbox.test/mcp',)


@pytest.mark.parametrize('setting,ca,expected', [(True, None, True), (False, None, False),
    (True, '/trusted/ca.pem', '/trusted/ca.pem'), (False, '/trusted/ca.pem', False),
    ('true', None, True), ('false', None, False)])
def test_tls_setting_reaches_http_transport(client_module, setting, ca, expected):
    client = client_module.SandboxClient('https://sandbox.test', 'private-token', ca, verify_tls=setting)
    client.session.post = Mock(return_value=Response(b'', 202))
    client._rpc('notifications/initialized', notification=True)
    assert client.session.post.call_args.kwargs['verify'] == expected


@pytest.mark.parametrize('value', [None, 0, 1, '', 'yes'])
def test_invalid_tls_setting_rejected(client_module, value):
    with pytest.raises(client_module.SandboxError, match='true or false'):
        client_module.SandboxClient('https://sandbox.test', 'private-token', verify_tls=value)


def test_size_limit_applies_to_mcp_response(client_module):
    client = client_with_response(client_module, Response(b'x' * (1024 * 1024 + 1)))
    with pytest.raises(client_module.SandboxError, match='exceeds'):
        client.query('SELECT 1')


@pytest.mark.parametrize('response', [
    Response({'jsonrpc': '2.0', 'id': 1, 'error': {'message': 'private-token'}}),
    Response(b'private-token', 302), Response(b'private-token', 401),
    Response(b'private-token'),
])
def test_server_bodies_and_tokens_are_never_echoed(client_module, response):
    client = client_with_response(client_module, response)
    with pytest.raises(client_module.SandboxError) as error:
        client.query('SELECT 1')
    assert 'private-token' not in str(error.value)


def test_transport_error_is_redacted(client_module):
    client = client_with_response(client_module, None)
    client.session.post.side_effect = requests.Timeout('private-token')
    with pytest.raises(client_module.SandboxError) as error:
        client.query('SELECT 1')
    assert 'private-token' not in str(error.value)


def test_malformed_query_result_rejected(client_module):
    result = {'structuredContent': {'result': '{"columns":["status"],"rows":[["SUCCESS",1]]}'}}
    with pytest.raises(client_module.SandboxError, match='invalid query result'):
        client_module.decode_rows(result)


def load_without_app_imports(relative_path, namespace):
    """Keep actual function bodies; inject only the app infrastructure boundaries."""
    path = SOURCE / relative_path
    tree = ast.parse(path.read_text(encoding='utf-8'))
    tree.body = [node for node in tree.body if not (isinstance(node, ast.ImportFrom)
                 and node.module and node.module.startswith('app'))]
    exec(compile(tree, str(path), 'exec'), namespace)
    return SimpleNamespace(**namespace)


@pytest.fixture
def business(client_module):
    spec = importlib.util.spec_from_file_location('sandbox_text_helpers_test', SOURCE / 'app/iris_engine/evidence/text.py')
    helpers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helpers)
    return load_without_app_imports('app/business/ptsandbox.py', {
        'BusinessProcessingError': RuntimeError, 'SandboxError': client_module.SandboxError,
        'text_chunks': helpers.text_chunks, 'BinaryLogError': helpers.BinaryLogError,
        'SandboxClient': client_module.SandboxClient, 'validate_url': client_module.validate_url,
        'report_summary': client_module.report_summary,
        'parse_verify_tls': client_module.parse_verify_tls,
        'encrypt_secret': lambda value: 'encrypted:' + value,
    })


def test_public_configuration_never_exposes_token_or_mutates_storage(business):
    original = [{'param_name': 'sandbox_token', 'value': 'encrypted:secret'},
                {'param_name': 'image_id', 'value': 'win10'}]
    public = business.public_config(original)
    assert public[0]['value'] == '' and public[0]['has_value'] is True
    assert original[0]['value'] == 'encrypted:secret'
    assert business.prepare_parameter('sandbox_token', '', 'encrypted:old') == 'encrypted:old'
    assert business.prepare_parameter('sandbox_token', 'new') == 'encrypted:new'


def test_configured_tls_and_default_are_used_by_all_callers(business):
    config = {'sandbox_url': 'https://sandbox.test', 'sandbox_token': 'private-token', 'ca_bundle': '/ca.pem'}
    assert business.client_from_config(config).verify == '/ca.pem'
    assert business.client_from_config({**config, 'verify_tls': False}).verify is False
    assert business.prepare_parameter('verify_tls', 'false') is False
    assert business.prepare_parameter('verify_tls', True) is True
    with pytest.raises(RuntimeError, match='true or false'):
        business.prepare_parameter('verify_tls', 'invalid')


def test_legacy_module_requires_fresh_mcp_configuration(business, monkeypatch):
    configuration = [
        {'param_name': 'sandbox_url', 'default': ''}, {'param_name': 'sandbox_token', 'default': ''},
        {'param_name': 'database', 'default': 'scans_v2'}, {'param_name': 'verify_tls', 'default': True},
    ]
    interface = SimpleNamespace(_module_configuration=configuration, _module_version='2.0.0', _module_description='MCP task import')
    monkeypatch.setitem(sys.modules, 'iris_ptsandbox_module.IrisPTSandboxInterface',
                        SimpleNamespace(IrisPTSandboxInterface=interface))
    row = SimpleNamespace(module_version='1.0.1', is_active=True, module_config=[
        {'param_name': 'sandbox_token', 'value': 'encrypted:old'},
        {'param_name': 'sandbox_url', 'value': 'https://original.test/api/v1', 'connection_check': {'ok': True}},
        {'param_name': 'verify_tls', 'value': False},
    ])
    namespace = business.sync_module_parameters.__globals__
    namespace['IrisModule'] = SimpleNamespace(query=Mock())
    namespace['IrisModule'].query.filter_by.return_value = [row]
    namespace['db'] = SimpleNamespace(session=Mock())
    business.sync_module_parameters()
    assert {p['param_name']: p['value'] for p in row.module_config} == {
        'sandbox_url': '', 'sandbox_token': '', 'database': 'scans_v2', 'verify_tls': False,
    }
    assert 'connection_check' not in row.module_config[0]
    assert row.is_active is False
    config = row.module_config
    business.sync_module_parameters()
    assert row.module_config is config


def test_text_logs_are_paged_and_compressed_logs_supported(business):
    log = SimpleNamespace(id=4, name='events.json.gz', content=gzip.compress(b'abcdefghijk'))
    first = business.text_page(log, offset=0, length=4)
    assert first['text'] == 'abcd' and first['next_offset'] == 4
    second = business.text_page(log, offset=4, length=20)
    assert second['text'] == 'efghijk' and second['next_offset'] is None
    assert second['untrusted_data'] is True


def test_binary_logs_not_treated_as_model_instructions(business):
    with pytest.raises(RuntimeError, match='Binary log'):
        business.text_page(SimpleNamespace(content=b'\x0a\x0d\x0d\x0a' + b'payload', id=1, name='network.pcapng'))


@pytest.mark.parametrize('old_status,new_status', [
    ('queued', 'failed'), ('submitting', 'submission_unknown'), ('completed', 'completed'),
])
def test_pending_rest_job_is_retired_without_remote_requests(old_status, new_status):
    scan = SimpleNamespace(status=old_status, report={'result': {'verdict': 'CLEAN'}})
    query = Mock()
    query.filter_by.return_value.with_for_update.return_value.first.return_value = scan
    tasks = load_without_app_imports('app/iris_engine/ptsandbox/tasks.py', {
        'celery': SimpleNamespace(task=lambda **kwargs: lambda fn: fn, conf=SimpleNamespace(beat_schedule={})),
        'db': SimpleNamespace(session=Mock()), 'SandboxScan': SimpleNamespace(query=query),
    })
    tasks.process_scan(1)
    assert scan.status == new_status
    assert scan.report == {'result': {'verdict': 'CLEAN'}}


def test_text_source_citations_work_past_sixteen_mib(business):
    raw = b'event\n' * 3000000 + 'последнее событие'.encode()
    decoded = raw.decode()
    offset = len(decoded)-len('последнее событие')
    log = SimpleNamespace(id=4, name='large.log.gz', content=gzip.compress(raw))
    page = business.text_page(log, offset=offset)
    assert offset>16*1024*1024
    assert page['text']=='последнее событие' and page['next_offset'] is None


def test_task_query_is_bounded_to_exact_scan_and_utc_start(client_module):
    scan_id = 'f549dadc-e402-11f1-a6f6-2fb4d4d5a685'
    start = datetime(2026, 11, 19, 10, 21, 18)
    query = client_module.SandboxClient.task_sql('scans_v2_repl', scan_id, start)
    assert 'FROM scans_v2_repl.tasks FINAL' in query
    assert "start = toDateTime('2026-11-19 10:21:18', 'UTC')" in query
    assert f"AND scan_id = toUUID('{scan_id}') LIMIT 1" in query
    with pytest.raises(client_module.SandboxError):
        client_module.SandboxClient.task_sql('other', scan_id, start)


@pytest.mark.parametrize('scan_id,started_at', [
    ('invalid', '2026-11-19T10:21:18Z'),
    ('f549dadc-e402-11f1-a6f6-2fb4d4d5a685', '2026-11-19T10:21:18+05:00'),
    ('f549dadc-e402-11f1-a6f6-2fb4d4d5a685', '2026-11-19T10:21:18Z extra'),
])
def test_import_rejects_invalid_lookup_before_connecting(business, scan_id, started_at):
    with pytest.raises(RuntimeError, match='task UUID and UTC start time'):
        business.import_scan(1, scan_id, started_at, 3)


def test_task_search_uses_literal_filename(client_module):
    name = "file'%_\u0422\u0435\u0441\u0442"
    sql = client_module.SandboxClient.search_sql('scans_v2', name, 7)
    assert name not in sql
    assert name.encode().hex() in sql
    assert 'INTERVAL 7 DAY' in sql
    assert 'LIMIT 30' in sql


def test_events_summary_precedes_bounded_chronology(client_module):
    client = client_module.SandboxClient('https://sandbox.test', 'test-token')
    client.query = Mock(side_effect=[[{'type': 'process', 'c': 500}], [{'type': 'process'}]])
    payload = client.task_events('scans_v2', 'f549dadc-e402-11f1-a6f6-2fb4d4d5a685', datetime(2026, 11, 19))
    assert payload['total'] == 500 and payload['truncated']
    summary, events = (call.args[0] for call in client.query.call_args_list)
    assert 'GROUP BY type' in summary
    assert 'ORDER BY create_time' in events
    assert all("toDateTime('2026-11-19 00:00:00', 'UTC')" in q and "type != 'netpacket'" in q
               for q in (summary, events))


def test_large_event_response_retries_with_smaller_chronology(client_module):
    client = client_module.SandboxClient('https://sandbox.test', 'test-token')
    client.query = Mock(side_effect=[[{'type': 'process', 'c': 400}],
        client_module.SandboxResponseTooLarge('oversized'), [{'type': 'process'}]])
    behavior = client.task_events('scans_v2', 'f549dadc-e402-11f1-a6f6-2fb4d4d5a685', datetime(2026, 11, 19))
    assert behavior['truncated'] and behavior['total'] == 400
    assert client.query.call_args_list[1].args[0].endswith('LIMIT 400')
    assert client.query.call_args_list[2].args[0].endswith('LIMIT 200')
