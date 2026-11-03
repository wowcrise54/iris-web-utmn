"""Bounded provider error diagnostics, without an app, database or network."""
import importlib.util
import json
import logging
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

SOURCE = Path(__file__).parents[2] / 'source/app'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def modules(monkeypatch):
    base = load(SOURCE / 'iris_engine/llm/providers/base.py', 'error_details_base')
    monkeypatch.setitem(sys.modules, 'app.iris_engine.llm.providers.base', base)
    safe = load(SOURCE / 'observability_logging.py', 'error_details_logging')
    monkeypatch.setitem(sys.modules, 'app.observability_logging', safe)
    adapter = load(SOURCE / 'iris_engine/llm/providers/openai.py', 'error_details_openai')
    diagnostics = load(SOURCE / 'iris_engine/llm/diagnostics.py', 'error_details_diagnostics')
    return base, adapter, diagnostics


def failure(modules, monkeypatch, payload, status=400):
    _, adapter, _ = modules
    response = requests.Response()
    response.status_code = status
    response._content = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    response._content_consumed = True
    response.close = Mock()
    post = Mock(return_value=response)
    monkeypatch.setattr(adapter.requests, 'post', post)
    provider = adapter.OpenAIProvider(api_key='fixture-key')
    result = list(provider.stream_completion(model='qwen-fixture', system='s', messages=[], tools=[]))
    response.close.assert_called_once()
    return result, post


@pytest.mark.parametrize('error', [
    {'code': 'context_length_exceeded', 'message': 'input rejected'},
    {'message': 'This model maximum context length is 262144 tokens. You requested 300000 tokens.'},
])
def test_context_rejection_has_a_specific_user_error(modules, monkeypatch, error):
    result, _ = failure(modules, monkeypatch, {'error': error})
    assert result[0].provider_code == 'context_length_exceeded'
    assert result[0].http_status == 400
    assert 'context limit' in result[0].message


def test_unknown_400_is_not_misdiagnosed_as_context_overflow(modules, monkeypatch):
    result, _ = failure(modules, monkeypatch, {'error': {'code': 'invalid_parameter', 'message': 'bad tool schema'}})
    assert result[0].provider_code == 'http_400'


def test_error_body_is_not_logged_by_default(modules, monkeypatch, caplog):
    caplog.set_level(5)
    failure(modules, monkeypatch, {'error': {'message': 'private incident detail'}})
    assert 'private incident detail' not in caplog.text


def test_opt_in_error_excerpt_is_redacted_and_bounded(modules, monkeypatch, caplog):
    monkeypatch.setenv('IRIS_CHATBOT_LOG_PROVIDER_ERRORS', '1')
    caplog.set_level(5)
    failure(modules, monkeypatch, {'error': {'message':
        'fixture-key Bearer fixture-bearer https://provider.test/path?token=fixture-query ' + 'x' * 3000}})
    excerpt = next(r.getMessage() for r in caplog.records if getattr(r, 'event', '') == 'llm_error_detail')
    assert all(secret not in excerpt for secret in ('fixture-key', 'fixture-bearer', 'fixture-query'))
    assert len(excerpt) < 2300


def test_large_error_body_is_read_with_a_ceiling(modules, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    result, _ = failure(modules, monkeypatch, b'x' * 100_000)
    record = next(r for r in caplog.records if getattr(r, 'event', '') == 'llm_http_error')
    assert record.metadata['error_body_bytes_read'] <= 16_384
    assert record.metadata['error_body_truncated'] is True
    assert result[0].provider_code == 'http_400'


@pytest.mark.parametrize('successful', [False, True])
def test_completion_event_means_the_provider_actually_finished(modules, caplog, successful):
    base, _, diagnostics = modules
    events = [base.MessageEnd('end_turn')] if successful else [base.Error('rejected', 'http_400', 400)]
    provider = SimpleNamespace(name='custom', stream_completion=lambda **kwargs: iter(events))
    caplog.set_level(logging.INFO)
    list(diagnostics.provider_events(provider, correlation_id='fixture-request'))
    completed = [r for r in caplog.records if getattr(r, 'event', '') == 'llm_completed']
    assert bool(completed) == successful


def test_wire_request_size_is_logged_without_request_content(modules, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    _, post = failure(modules, monkeypatch, b'')
    record = next(r for r in caplog.records if getattr(r, 'event', '') == 'llm_input')
    assert record.metadata['request_bytes'] == len(json.dumps(post.call_args.kwargs['json']).encode())
    assert record.metadata['message_count'] == 1
