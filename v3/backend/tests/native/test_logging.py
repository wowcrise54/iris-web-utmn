"""Logging contracts without database/bootstrap side effects."""
import asyncio
import importlib.util
import io
import json
import math
import logging
import ast
import sys
import types
from functools import wraps
from pathlib import Path

import pytest


@pytest.fixture
def logs():
    path = Path(__file__).parents[2] / 'source/app/observability_logging.py'
    assert path.exists(), 'Unified logging is not implemented'
    spec = importlib.util.spec_from_file_location('iris_logging_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    states = {name: (obj.level, obj.handlers[:], obj.propagate)
              for name, obj in root.manager.loggerDict.items() if isinstance(obj, logging.Logger)}
    yield module
    root.handlers[:], root.level = handlers, level
    for name, obj in root.manager.loggerDict.items():
        if isinstance(obj, logging.Logger):
            obj.level, obj.handlers[:], obj.propagate = states.get(name, (0, [], True))


def test_levels_overrides_and_idempotent_initialization(logs):
    stream = io.StringIO()
    config = {'LOG_LEVEL': 'INFO', 'IRIS_LOG_FORMAT': 'json',
              'IRIS_LOG_LEVELS': '{"iris.mcp":"TRACE","urllib3":"ERROR"}'}
    logs.configure_logging(config, stream=stream)
    logs.configure_logging(config, stream=stream)
    logging.getLogger('iris.mcp').log(5, 'tool_started')
    logging.getLogger('iris.api').debug('hidden')
    logging.getLogger('iris.api').info('request_completed')
    logging.getLogger('urllib3').warning('hidden')
    logging.getLogger('urllib3.connectionpool').warning('hidden_child')
    rows = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert [row['level'] for row in rows] == ['TRACE', 'INFO']
    assert rows[0]['event'] == 'tool_started'
    assert rows[1]['service'] == 'app'
    assert rows[0]['time'].endswith('Z')


@pytest.mark.parametrize('config', [
    {'LOG_LEVEL': 'oops'}, {'IRIS_LOG_FORMAT': 'xml'},
    {'IRIS_LOG_LEVELS': '[]'}, {'IRIS_LOG_LEVELS': '{"iris":"oops"}'},
    {'IRIS_LOG_LEVELS': '{'},
    {'IRIS_LOG_LEVELS': '{"invalid logger name":"INFO"}'},
])
def test_invalid_configuration_fails_without_echoing_values(logs, config):
    with pytest.raises(ValueError) as error:
        logs.configure_logging(config, stream=io.StringIO())
    assert 'oops' not in str(error.value)


def test_redaction_and_exception_never_dump_objects_or_exception_values(logs):
    stream = io.StringIO()
    logs.configure_logging({'LOG_LEVEL': 'TRACE', 'IRIS_LOG_FORMAT': 'json'}, stream=stream)
    cycle = {'password': 'inert-secret', 'body': 'private-body'}
    cycle['cycle'] = cycle
    log = logging.getLogger('iris.api')
    log.info('password=inert-secret Bearer inert-bearer https://host/path?token=inert-query',
             extra={'event': 'safe_event', 'metadata': cycle})
    log.info('credentials {"password": "inert quoted secret"}')
    log.info('credentials {"password": "inert multiline\nsecret"}')
    log.info('metric', extra={'metadata': {'duration_ms': math.nan}})
    log.warning({'incident_data': 'private-body'})
    log.warning('unexpected_payload %s', {'incident_data': 'private-body'})
    log.exception('no_active_exception')
    try:
        raise ValueError('private-body inert-secret')
    except ValueError:
        log.exception('request_failed')
    output = stream.getvalue()
    for secret in ('inert-secret', 'inert-bearer', 'inert-query', 'private-body', 'inert quoted secret', 'inert multiline'):
        assert secret not in output
    assert json.loads(output.splitlines()[-1])['error_type'] == 'ValueError'
    assert any(json.loads(line)['event'] == 'no_active_exception' for line in output.splitlines())


def test_context_isolated_between_concurrent_operations_and_restored(logs):
    async def operation(identifier):
        with logs.logging_context(request_id=identifier):
            await asyncio.sleep(0)
            assert logs.current_context()['request_id'] == identifier
        assert not logs.current_context()

    async def run():
        await asyncio.gather(operation('one'), operation('two'))
    asyncio.run(run())


def test_request_ids_reject_controls_and_overlong_values(logs):
    assert logs.request_id('req-1:abc_2') == 'req-1:abc_2'
    for value in ('injected\nline', 'x' * 129, '', 'spaces here'):
        result = logs.request_id(value)
        assert result != value and len(result) == 32


def test_operation_metadata_has_duration_and_never_payload(logs):
    stream = io.StringIO()
    logs.configure_logging({'LOG_LEVEL': 'TRACE', 'IRIS_LOG_FORMAT': 'json'}, stream=stream)
    with logs.observed_operation('iris.mcp', 'tool'):
        pass
    with pytest.raises(ValueError):
        with logs.observed_operation('iris.mcp', 'tool'):
            raise ValueError('private-operation-data')
    rows = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert [row['level'] for row in rows] == ['TRACE', 'INFO', 'TRACE', 'WARNING']
    assert rows[-1]['result'] == 'error' and rows[-1]['error_type'] == 'ValueError'
    assert rows[-1]['duration_ms'] >= 0
    assert 'private-operation-data' not in stream.getvalue()


def test_asgi_correlation_success_error_and_context_cleanup(logs):
    stream = io.StringIO()
    logs.configure_logging({'IRIS_LOG_FORMAT': 'json'}, stream=stream)
    messages = []

    async def downstream(scope, receive, send):
        assert logs.current_context()['request_id'] == 'req-one'
        logs.bind_request_identity(user_id=7)
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        await send({'type': 'http.response.body', 'body': b'ok'})

    async def send(message):  # noqa: RUF029 -- ASGI requires an awaitable send.
        messages.append(message)
    scope = {'type': 'http', 'method': 'GET', 'path': '/api/v2/cases',
             'headers': [(b'x-request-id', b'req-one')]}
    asyncio.run(logs.LoggingMiddleware(downstream)(scope, None, send))
    assert (b'x-request-id', b'req-one') in messages[0]['headers']
    row = json.loads(stream.getvalue())
    assert row['request_id'] == 'req-one' and row['status'] == 200
    assert row['user_id'] == 7
    assert row['event'] == 'http_completed'
    assert not logs.current_context()


def test_client_events_validation_and_atomic_rate_limit(logs):
    intake = logs.ClientEvents()
    good = {'level': 'WARNING', 'event': 'ui_failed', 'message': 'password=inert-secret',
            'path': '/case/1?token=inert-query', 'request_id': 'req-one'}
    events = intake.validate({'events': [good]})
    assert 'inert-secret' not in json.dumps(events)
    assert events[0]['path'] == '/case/1'
    assert intake.allow(7, 20, now=0)
    assert intake.allow(7, 20, now=1)
    assert intake.allow(7, 20, now=2)
    assert not intake.allow(7, 1, now=3)
    assert intake.allow(8, 1, now=3)
    assert intake.allow(7, 20, now=61)
    for body in ({'events': [good] * 21}, {'events': [{**good, 'user_id': 9}]},
                 {'events': [{**good, 'level': 'DEBUG'}]}, {'events': 'bad'}):
        with pytest.raises(ValueError):
            intake.validate(body)


@pytest.fixture
def isolated_app(logs, monkeypatch):
    root = Path(__file__).parents[2] / 'source/app'
    package = types.ModuleType('app')
    package.__path__ = [str(root)]
    monkeypatch.setitem(sys.modules, 'app', package)
    monkeypatch.setitem(sys.modules, 'app.observability_logging', logs)
    # Keep production imports isolated from any other native test's adapter.

    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, root / path)
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
        return module
    web = load('app.web', 'web.py')
    package.app = web.IRISApp('logging_contract')
    package.app.config.update(SECRET_KEY='inert-test-secret', TESTING=True)
    return package, web, load


def test_worker_context_headers_execution_failure_and_retry(logs, isolated_app, monkeypatch):
    from contextlib import nullcontext
    from celery import Celery
    from celery.exceptions import Retry
    package, web, load = isolated_app
    config = types.ModuleType('app.configuration')
    config.CeleryConfig = type('CeleryConfig', (), {})
    monkeypatch.setitem(sys.modules, 'app.configuration', config)
    tasker = load('_iris_task_logging_test', 'iris_engine/tasker/celery.py')
    worker = Celery('logging_contract', broker='memory://', backend='cache+memory://')
    tasker.set_celery_flask_context(worker, types.SimpleNamespace(app_context=nullcontext))
    stream = io.StringIO()
    logs.configure_logging({'IRIS_LOG_FORMAT': 'json'}, stream=stream)

    @worker.task(name='iris.test.logging', lazy=False)
    def operation(mode='ok'):
        assert logs.current_context()['request_id'] == 'req-chain'
        if mode == 'fail':
            raise ValueError('private-task-input')
        if mode == 'retry':
            raise Retry('private-task-input')
        return 'private-task-result'
    with logs.logging_context(request_id='req-chain', user_id=7):
        operation.apply_async(queue='logging-contract')
    with worker.connection() as connection:
        queue = connection.SimpleQueue('logging-contract')
        message = queue.get(block=False)
        assert message.headers['iris_log_context'] == {'request_id': 'req-chain', 'user_id': 7}
        message.ack()
        queue.close()
    for mode in ('ok', 'fail', 'retry'):
        operation.apply(args=(mode,), headers={'iris_log_context': {'request_id': 'req-chain', 'user_id': 7}}, throw=False)
        assert not logs.current_context()
    output = stream.getvalue()
    assert 'private-task' not in output
    rows = [json.loads(line) for line in output.splitlines()]
    own = [row for row in rows if row['logger'] == 'iris.worker']
    assert [row['event'] for row in own] == ['task_started', 'task_completed', 'task_started', 'task_failed', 'task_started', 'task_retry']
    assert all(row['request_id'] == 'req-chain' and row['user_id'] == 7 for row in own)
    # Avoid persistent signal receivers between tests.
    for signal, receiver in ((tasker.signals.before_task_publish, tasker.carry_logging_context),
                             (tasker.signals.setup_logging, tasker.configure_worker_logging),
                             (tasker.signals.worker_process_init, tasker.configure_worker_child_logging),
                             (tasker.signals.worker_ready, tasker.worker_ready),
                             (tasker.signals.worker_shutdown, tasker.worker_shutdown)):
        signal.disconnect(receiver)


def test_client_endpoint_auth_csrf_sizes_rate_and_identity(logs, isolated_app, monkeypatch):
    package, web, load = isolated_app
    forms = load('app.web_forms', 'web_forms.py')
    user = types.SimpleNamespace(id=7)
    users = types.ModuleType('app.blueprints.iris_user')
    users.iris_current_user = user
    monkeypatch.setitem(sys.modules, users.__name__, users)

    def error(message, data=None, status=400):
        return {'message': message}, status
    endpoints = types.ModuleType('app.blueprints.rest.endpoints')
    endpoints.response_api_error = error
    endpoints.response_api_success = lambda data: {'data': data}
    monkeypatch.setitem(sys.modules, endpoints.__name__, endpoints)
    # Exercise the real permission/CSRF wrapper; replace only database-backed
    # identity/permission lookups with an inert authenticated principal.
    tree = ast.parse((Path(__file__).parents[2] / 'source/app/blueprints/access_controls.py').read_text(encoding='utf-8'))
    names = {'_is_csrf_token_valid', 'wrap_with_permission_checks', 'ac_api_requires'}
    auth = types.ModuleType('app.blueprints.access_controls')
    auth.__dict__.update(wraps=wraps, request=web.request, g=web.g, session=web.session,
        FlaskForm=forms.WebForm, response_error=error, iris_current_user=user, current_user=user,
        ac_get_effective_permissions_of_user=lambda _: 1,
        _user_has_at_least_a_required_permission=lambda _: True,
        is_user_authenticated=lambda _: bool(web.session.get('_user_id')) or web.request.headers.get('Authorization') == 'Bearer inert-access')
    exec(compile(ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names], type_ignores=[]), 'access_controls.py', 'exec'), auth.__dict__)
    monkeypatch.setitem(sys.modules, auth.__name__, auth)
    intake = load('_iris_client_events_test', 'blueprints/rest/v2/client_events.py')
    doc = types.ModuleType('app.blueprints.rest.api_doc')
    doc.api_doc = lambda **_options: lambda handler: handler
    tracker = types.ModuleType('app.iris_engine.utils.tracker')
    tracker.track_activity = lambda *_args, **_kwargs: None
    monkeypatch.setitem(sys.modules, doc.__name__, doc)
    monkeypatch.setitem(sys.modules, tracker.__name__, tracker)
    reports = load('_iris_bug_reports_logging_test', 'blueprints/rest/v2/bug_reports.py')
    root = web.Blueprint('api', __name__, url_prefix='/api/v2')
    root.register_blueprint(intake.client_events_blueprint)
    root.register_blueprint(reports.bug_reports_blueprint)
    package.app.register_blueprint(root)

    @package.app.route('/csrf')
    def csrf():
        web.session['_user_id'] = 7
        return {'csrf': forms.generate_csrf()}
    client = package.app.test_client()
    url = '/api/v2/observability/client-events'
    body = {'events': [{'level': 'ERROR', 'event': 'ui_failed', 'message': 'password=inert-secret', 'request_id': 'req-ui'}]}
    assert client.post(url, json=body).status_code == 401
    csrf_token = client.get('/csrf').json['csrf']
    assert client.post(url, json=body).status_code == 400
    stream = io.StringIO()
    logs.configure_logging({'IRIS_LOG_FORMAT': 'json'}, stream=stream)
    assert client.post(url, json={**body, 'csrf_token': csrf_token}).status_code == 200
    row = json.loads(stream.getvalue())
    assert row['source'] == 'browser' and row['user_id'] == 7 and row['request_id'] == 'req-ui'
    assert 'inert-secret' not in stream.getvalue()
    headers = {'Authorization': 'Bearer inert-access'}
    assert client.post(url, json={'events': [{**body['events'][0], 'user_id': 999}]}, headers=headers).status_code == 400
    assert client.post(url, data='x' * 65537, content_type='application/json', headers=headers).status_code == 413
    for _ in range(2):
        assert client.post(url, json={'events': body['events'] * 20}, headers=headers).status_code == 200
    assert client.post(url, json={'events': body['events'] * 20}, headers=headers).status_code == 429
    stream.seek(0)
    stream.truncate()
    assert client.post('/api/v2/bug-reports', headers=headers, json={
        'title': 'Diagnostic report', 'description': 'Useful details password=inert-secret',
    }).status_code == 200
    report = json.loads(stream.getvalue())
    assert report['metadata']['title'] == 'Diagnostic report'
    assert 'Useful details' in report['metadata']['description']
    assert 'inert-secret' not in stream.getvalue()


def test_sentry_preserves_backend_errors_without_replaying_browser(logs, isolated_app, monkeypatch):
    import sentry_sdk
    from sentry_sdk.transport import Transport
    envelopes = []

    class MemoryTransport(Transport):
        def capture_envelope(self, envelope):
            envelopes.append(envelope)

    original_init = sentry_sdk.init

    def inert_init(**options):
        return original_init(**options, transport=MemoryTransport(), auto_enabling_integrations=False)
    monkeypatch.setattr(sentry_sdk, 'init', inert_init)
    _, _, load = isolated_app
    reporter = load('_iris_reporter_test', 'iris_engine/observability/reporter.py')
    reporter._do_init('https://inert@errors.example.invalid/1', environment='test', sample_rate=1.0,
                      release='logging-test', strict_frame_vars=True)
    try:
        logs.configure_logging({'IRIS_LOG_FORMAT': 'json'}, stream=io.StringIO())
        with logs.logging_context(request_id='sentry-correlation'):
            logging.getLogger('iris.api').error('backend_failed')
            logging.getLogger('iris.worker').error('worker_failed')
        logging.getLogger('iris.browser').error('browser_replayed')
        logging.getLogger('celery.app.trace').error('task_trace_replayed')
        events = [item.payload.json for envelope in envelopes for item in envelope.items if item.type == 'event']
        assert [event['logentry']['formatted'] for event in events] == ['backend_failed', 'worker_failed']
        assert all(event.get('extra', {}).get('request_id') == 'sentry-correlation' for event in events)
    finally:
        original_init(dsn=None)
