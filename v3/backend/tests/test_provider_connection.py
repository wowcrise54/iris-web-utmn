"""Isolated provider tests; no app startup, DB, credentials or external calls."""
import importlib
import ast
from dataclasses import replace
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import requests

ROOT = Path(__file__).resolve().parents[1] / 'source' / 'app'
app = types.ModuleType('app')
app.__path__ = [str(ROOT)]
settings = types.ModuleType('app.business.server_settings')
settings.get_srv_settings = lambda: SimpleNamespace()
secrets = types.ModuleType('app.iris_engine.mail.secrets')
secrets.decrypt_secret = lambda value: value
with patch.dict(sys.modules, {'app': app, 'app.business.server_settings': settings,
                             'app.iris_engine.mail.secrets': secrets}):
    client = importlib.import_module('app.iris_engine.llm.client')
    check = importlib.import_module('app.iris_engine.llm.connection_check')


def config(**overrides):
    values = dict(enabled=True, provider='custom', api_key='test-key',
                  model='test-model', base_url='https://provider.example/api/v1',
                  max_turns_per_conversation=25, max_tool_calls_per_turn=8,
                  auto_execute_read_tools=True, auto_approve_write_tools=False,
                  daily_token_budget_per_user=1000, daily_token_budget_org=1000,
                  redact_ips=False, redact_emails=False, redact_hashes=False)
    return client.ChatbotConfig(**(values | overrides))


def response(payload=None, status=200):
    result = MagicMock()
    result.__enter__.return_value = result
    result.status_code = status
    result.json.return_value = payload
    return result


@pytest.mark.parametrize('base,expected', [
    ('https://provider.example', 'https://provider.example/v1/chat/completions'),
    ('https://provider.example/v1/', 'https://provider.example/v1/chat/completions'),
    ('https://provider.example/api/v1', 'https://provider.example/api/v1/chat/completions'),
])
def test_custom_completion_url(base, expected):
    adapter = client.get_llm_provider(config(api_key='', base_url=base))
    assert adapter.name == 'custom'
    assert adapter.api_url('chat/completions') == expected
    with patch.object(requests, 'post', side_effect=requests.ConnectionError) as post:
        list(adapter.stream_completion(model='m', system='', messages=[], tools=[]))
    assert post.call_args.args[0] == expected
    assert 'Authorization' not in post.call_args.kwargs['headers']


@pytest.mark.parametrize('base', ['', 'file:///tmp/x', 'https://u:p@example.org',
                                   'https://example.org?key=x', 'https://example.org#x'])
def test_invalid_custom_url(base):
    with pytest.raises((client.ChatbotDisabledError, ValueError)):
        client.get_llm_provider(config(base_url=base))


def test_builtin_openai_still_requires_key():
    with pytest.raises(client.ChatbotDisabledError):
        client.get_llm_provider(config(provider='openai', api_key=''))


def test_list_and_generation_are_checked_separately():
    replies = [response({'data': [{'id': 'z'}, {'id': 'test-model'}, {'id': 'z'}]}),
               response({'choices': [{'message': {'content': 'OK'}}]})]
    with patch.object(requests, 'request', side_effect=replies) as request:
        result = check.check_connection(config(enabled=False))
    assert result['models'] == ['test-model', 'z']
    assert result['model_accessible'] is True
    assert result['models_error'] is None
    assert request.call_args_list[0].args == ('GET', 'https://provider.example/api/v1/models')
    probe = request.call_args_list[1]
    assert probe.kwargs['json'] == {
        'model': 'test-model', 'messages': [{'role': 'user', 'content': 'Reply OK.'}],
        'stream': False, 'max_tokens': 16}
    assert probe.kwargs['allow_redirects'] is False
    assert probe.kwargs['timeout'] == (10, 30)


@pytest.mark.parametrize('status', [401, 403, 404, 429, 500, 302])
def test_listing_does_not_prove_model_access(status):
    with patch.object(requests, 'request', side_effect=[response({'data': []}), response(status=status)]):
        result = check.check_connection(config())
    assert result['model_accessible'] is False
    assert result['model_error'] == f'http_{status}'


def test_generation_can_succeed_without_listing_endpoint():
    with patch.object(requests, 'request', side_effect=[response(status=404),
                      response({'choices': [{'message': {'content': 'OK'}}]})]):
        result = check.check_connection(config())
    assert result['models_error'] == 'http_404'
    assert result['model_accessible'] is True


def test_no_selected_model_only_lists():
    with patch.object(requests, 'request', return_value=response({'data': [{'id': 'm'}]})) as request:
        result = check.check_connection(config(model=''))
    assert result['model_accessible'] is None
    assert request.call_count == 1


@pytest.mark.parametrize('exception,code', [(requests.Timeout('secret'), 'timeout'),
                                         (requests.ConnectionError('secret'), 'connection_error'),
                                         (ValueError('secret'), 'invalid_response')])
def test_errors_do_not_expose_secrets(exception, code):
    with patch.object(requests, 'request', side_effect=exception):
        result = check.check_connection(config())
    assert result['model_error'] == code
    assert 'secret' not in str(result)


@pytest.mark.parametrize('payload', [[], {}, {'choices': []}, {'error': 'secret'}])
def test_malformed_generation_response_is_failure(payload):
    with patch.object(requests, 'request', side_effect=[response({'data': []}), response(payload)]):
        result = check.check_connection(config())
    assert result['model_accessible'] is False
    assert result['model_error'] == 'invalid_response'


@pytest.mark.parametrize('provider,listing,reply,suffix', [
    ('anthropic', {'data': [{'id': 'test-model'}]}, {'content': [{'type': 'text', 'text': 'OK'}]}, '/v1/messages'),
    ('ollama', {'models': [{'name': 'test-model'}]}, {'message': {'content': 'OK'}, 'done': True}, '/api/chat'),
    ('openai', {'data': [{'id': 'test-model'}]}, {'choices': [{'message': {'content': 'OK'}}]}, '/v1/chat/completions'),
])
def test_builtin_providers(provider, listing, reply, suffix):
    with patch.object(requests, 'request', side_effect=[response(listing), response(reply)]) as request:
        result = check.check_connection(config(provider=provider, base_url='https://provider.example'))
    assert result['model_accessible'] is True
    assert result['models'] == ['test-model']
    assert request.call_args.args[1] == 'https://provider.example' + suffix


@pytest.fixture
def endpoint():
    # Execute the real handler without importing unrelated app/DB boot code.
    tree = ast.parse((ROOT / 'blueprints/rest/v2/manage_routes/case_chat.py').read_text(encoding='utf-8'))
    handler = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                   and node.name == 'check_provider')
    assert any('server_administrator' in ast.unparse(dec) for dec in handler.decorator_list)
    handler.decorator_list = []
    namespace = dict(request=MagicMock(), db=MagicMock(), ChatbotPolicy=object, replace=replace,
                     response_api_error=lambda message: ('error', message),
                     response_api_not_found=lambda: ('not_found', None),
                     response_api_success=lambda result: ('success', result))
    exec(compile(ast.Module(body=[handler], type_ignores=[]), 'check_provider', 'exec'), namespace)
    return namespace


@pytest.mark.parametrize('body,expected', [
    ({'provider': 'custom'}, 'test-key'),
    ({'provider': 'custom', 'api_key': None}, ''),
    ({'provider': 'custom', 'api_key': 'new-key'}, 'new-key'),
    ({'policy_id': None, 'api_key': None}, 'test-key'),
    ({'policy_id': 7, 'api_key': None}, 'test-key'),
    ({'policy_id': 7}, 'policy-key'),
])
def test_endpoint_secret_resolution(endpoint, body, expected):
    policy = SimpleNamespace()
    endpoint['request'].get_json.return_value = body
    endpoint['db'].session.get.return_value = policy
    with patch.object(client, 'load_config', side_effect=lambda p=None: config(api_key='policy-key' if p else 'test-key')), \
         patch.object(check, 'check_connection', return_value={}) as probe, \
         patch.dict(sys.modules, {'app.iris_engine.llm.client': client,
                                  'app.iris_engine.llm.connection_check': check}):
        assert endpoint['check_provider']()[0] == 'success'
    assert probe.call_args.args[0].api_key == expected


def test_new_policy_empty_fields_inherit_global(endpoint):
    endpoint['request'].get_json.return_value = {
        'policy_id': None, 'provider': '', 'model': '', 'base_url': ''}
    with patch.object(client, 'load_config', return_value=config()), \
         patch.object(check, 'check_connection', return_value={}) as probe, \
         patch.dict(sys.modules, {'app.iris_engine.llm.client': client,
                                  'app.iris_engine.llm.connection_check': check}):
        endpoint['check_provider']()
    assert probe.call_args.args[0] == config()


@pytest.mark.parametrize('body', [[], {'api_key': 42}, {'provider': {}}, {'policy_id': True},
                                  {'policy_id': -1}, {'unknown': 'x'}])
def test_endpoint_rejects_invalid_payload(endpoint, body):
    endpoint['request'].get_json.return_value = body
    with patch.dict(sys.modules, {'app.iris_engine.llm.client': client,
                                 'app.iris_engine.llm.connection_check': check}):
        assert endpoint['check_provider']()[0] == 'error'
