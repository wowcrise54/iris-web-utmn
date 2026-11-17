"""Transport and worker failure contracts without booting IRIS or contacting an appliance."""
import ast
import datetime as dt
import gzip
import hashlib
import importlib.util
import io
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
    def __init__(self, body, status=200):
        self.status_code = status
        self.raw = body if isinstance(body, bytes) else json.dumps(body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def iter_content(self, size):
        yield self.raw


def client_with_response(module, response):
    client = module.SandboxClient('https://sandbox.test', 'private-token')
    client.session.request = Mock(return_value=response)
    return client


@pytest.mark.parametrize('url', ['http://sandbox.test', 'https://u:p@sandbox.test',
                               'https://sandbox.test?key=x', 'https://sandbox.test/path',
                               'https://sandbox.test/#x', None])
def test_only_validated_https_appliance_addresses(client_module, url):
    with pytest.raises(client_module.SandboxError):
        client_module.validate_url(url)


def test_upload_sends_original_stream_and_no_redirects(client_module):
    client = client_with_response(client_module, Response({'data': {'file_uri': 'sfm:temporary'}, 'errors': []}))
    content = io.BytesIO(b'sample')
    assert client.upload(content) == 'sfm:temporary'
    call = client.session.request.call_args
    assert call.args[1] == 'https://sandbox.test/api/v1/storage/uploadScanFile'
    assert call.kwargs['data'] is content
    assert call.kwargs['verify'] is True
    assert call.kwargs['allow_redirects'] is False
    assert client.session.trust_env is False


@pytest.mark.parametrize('setting,ca,expected', [(True, None, True), (False, None, False),
    (True, '/trusted/ca.pem', '/trusted/ca.pem'), (False, '/trusted/ca.pem', False),
    ('true', None, True), ('false', None, False)])
def test_tls_setting_reaches_http_transport(client_module, setting, ca, expected):
    client = client_module.SandboxClient('https://sandbox.test', 'private-token', ca, verify_tls=setting)
    client.session.request = Mock(return_value=Response({'data': {'status': 'ok'}}))
    client.request('maintenance/checkHealth', method='GET')
    assert client.session.request.call_args.kwargs['verify'] == expected


@pytest.mark.parametrize('value', [None, 0, 1, '', 'yes'])
def test_invalid_tls_setting_rejected(client_module, value):
    with pytest.raises(client_module.SandboxError, match='true or false'):
        client_module.SandboxClient('https://sandbox.test', 'private-token', verify_tls=value)


def test_report_unknown_fields_are_preserved(client_module):
    report = {'result': {'verdict': 'DANGEROUS'}, 'vendor_extension': {'new': [1, 2]}}
    client = client_with_response(client_module, Response({'data': report}))
    assert client.request('analysis/report', payload={'scan_id': 'id'}) == report


def test_size_limit_applies_to_streamed_logs(client_module):
    client = client_with_response(client_module, Response(b'12345'))
    with pytest.raises(client_module.SandboxError, match='size limit'):
        client.request('storage/downloadArtifact', payload={'file_uri': 'sha256:x'}, limit=4)


@pytest.mark.parametrize('response', [Response({'data': {}, 'errors': [{'message': 'private-token'}]}),
                                      Response(b'private-token', 302), Response(b'private-token', 401),
                                      Response(b'private-token')])
def test_server_bodies_and_tokens_are_never_echoed(client_module, response):
    client = client_with_response(client_module, response)
    with pytest.raises(client_module.SandboxError) as error:
        client.request('analysis/report')
    assert 'private-token' not in str(error.value)


def test_transport_error_is_redacted(client_module):
    client = client_with_response(client_module, None)
    client.session.request.side_effect = requests.Timeout('private-token')
    with pytest.raises(client_module.SandboxError) as error:
        client.request('analysis/report')
    assert 'private-token' not in str(error.value)


def test_all_nested_log_references_collected_without_executable_artifacts(client_module):
    uri = 'sha256:' + 'a' * 64
    report = {'artifacts': [{'file_info': {'file_uri': 'sha256:' + 'b' * 64},
               'engine_results': [{'details': {'sandbox': {'logs': [{'file_uri': uri, 'file_name': 'trace.zst'}],
                    'stages': [{'logs': [{'file_uri': uri}, {'file_uri': 'https://evil.test'}]}]}}}]}]}
    refs = client_module.log_references(report)
    assert [r['file_uri'] for r in refs] == [uri, 'https://evil.test']
    assert refs[0]['file_name'] == 'trace.zst'


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


def test_installed_module_gets_tls_setting_without_resetting_secrets_or_choices(business, monkeypatch):
    interface = SimpleNamespace(_module_configuration=[{'param_name': 'verify_tls', 'type': 'bool', 'default': True}],
                                _module_version='1.0.1')
    monkeypatch.setitem(sys.modules, 'iris_ptsandbox_module.IrisPTSandboxInterface',
                        SimpleNamespace(IrisPTSandboxInterface=interface))
    row = SimpleNamespace(module_config=[{'param_name': 'sandbox_token', 'value': 'encrypted:existing'},
        {'param_name': 'sandbox_url', 'value': 'https://original.test', 'connection_check': {'ok': True}}], is_active=True)
    namespace = business.sync_module_parameters.__globals__
    namespace['IrisModule'] = SimpleNamespace(query=Mock())
    namespace['IrisModule'].query.filter_by.return_value = [row]
    namespace['db'] = SimpleNamespace(session=Mock())
    business.sync_module_parameters()
    assert row.module_config[0]['value'] == 'encrypted:existing'
    assert row.module_config[1]['connection_check'] == {'ok': True}
    assert row.is_active is True
    assert row.module_config[-1]['value'] is True
    row.module_config[-1]['value'] = False
    business.sync_module_parameters()
    assert len(row.module_config) == 3 and row.module_config[-1]['value'] is False


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


@pytest.fixture
def worker(client_module, tmp_path):
    source = tmp_path / 'sample.bin'
    source.write_bytes(b'safe unit-test sample')
    scan = SimpleNamespace(id=1, case_id=7, file_id=8, module_id=2, requested_by=1,
        war_room_id=None, notification_id=None, scan_id=None, file_name='sample.bin', status='queued',
        sha256=hashlib.sha256(source.read_bytes()).hexdigest(), created_at=dt.datetime.utcnow(),
        options={'url': 'https://sandbox.test/api/v1', 'image_id': 'win10', 'analysis_duration': 120})
    query = Mock()
    query.filter_by.return_value.with_for_update.return_value.first.side_effect = lambda: scan
    client = Mock()
    client.check_connection.return_value = {'version_matches': True}
    client.upload.return_value = 'sfm:temporary'
    client.start.return_value = '12345678-1234-1234-1234-123456789abc'
    cfg = {'sandbox_url': 'https://sandbox.test', 'max_file_mb': 100}

    def task(**kwargs):
        def decorate(fn):
            fn.delay = Mock()
            fn.apply_async = Mock()
            return fn
        return decorate
    namespace = {'celery': SimpleNamespace(task=task, conf=SimpleNamespace(beat_schedule={})),
        'db': SimpleNamespace(session=Mock()), 'SandboxScan': SimpleNamespace(query=query),
        'SandboxError': client_module.SandboxError, 'validate_url': client_module.validate_url,
        'log_references': client_module.log_references, 'module_config': Mock(return_value=(None, cfg)),
        'client_from_config': Mock(return_value=client),
        'datastore_get_local_file_path': Mock(return_value=(False, SimpleNamespace(file_local_name=str(source),
                                                                               file_password='', file_is_ioc=False)))}
    load_without_app_imports('app/iris_engine/ptsandbox/tasks.py', namespace)
    namespace['_authorized'] = Mock(return_value=True)
    namespace['_finish'] = Mock(side_effect=lambda scan, status, _error=None: setattr(scan, 'status', status))
    return SimpleNamespace(ns=namespace, scan=scan, client=client)


def test_successful_submission_schedules_poll_without_blocking(worker):
    worker.ns['process_scan'](1)
    assert worker.scan.status == 'running'
    assert worker.scan.scan_id == '12345678-1234-1234-1234-123456789abc'
    worker.ns['process_scan'].apply_async.assert_called_once_with(args=[1], countdown=30)


def test_ambiguous_submission_is_never_automatically_repeated(worker):
    worker.client.start.side_effect = worker.ns['SandboxError']('connection error')
    worker.ns['process_scan'](1)
    assert worker.scan.status == 'submission_unknown'
    worker.ns['process_scan'](1)
    worker.client.start.assert_called_once()
    worker.ns['process_scan'].apply_async.assert_not_called()


def test_preliminary_verdict_is_not_published_as_final(worker):
    worker.scan.status, worker.scan.scan_id = 'running', 'existing'
    worker.client.request.return_value = {'result': {'verdict': 'CLEAN'}, 'is_preflight': True}
    worker.ns['process_scan'](1)
    assert worker.scan.status == 'running'
    assert worker.client.request.call_count == 1
    worker.ns['_finish'].assert_not_called()


def test_revoked_access_blocks_upload(worker):
    worker.ns['_authorized'].return_value = False
    worker.ns['process_scan'](1)
    assert worker.scan.status == 'failed'
    worker.client.upload.assert_not_called()


def test_different_product_version_blocks_upload(worker):
    worker.client.check_connection.return_value = {'version_matches': False}
    worker.ns['process_scan'](1)
    assert worker.scan.status == 'failed'
    worker.client.upload.assert_not_called()


def test_text_source_citations_work_past_sixteen_mib(business):
    raw = b'event\n' * 3000000 + 'последнее событие'.encode()
    decoded = raw.decode()
    offset = len(decoded)-len('последнее событие')
    log = SimpleNamespace(id=4, name='large.log.gz', content=gzip.compress(raw))
    page = business.text_page(log, offset=offset)
    assert offset>16*1024*1024
    assert page['text']=='последнее событие' and page['next_offset'] is None
