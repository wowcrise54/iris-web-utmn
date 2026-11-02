"""Full wire request budget and conservative handling of unmapped tokenizers."""
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


@pytest.fixture
def budget():
    path = Path(__file__).parents[2] / 'source/app/iris_engine/llm/request_budget.py'
    assert path.exists(), 'request budget guard is required'
    spec = importlib.util.spec_from_file_location('request_budget_test', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Provider:
    _base_url = ''
    _api_key = ''

    def _build_body(self, model, system, messages, tools, max_tokens):
        return {'model': model, 'messages': [{'role': 'system', 'content': system}] + messages,
                'tools': tools, 'max_tokens': max_tokens}


def check(budget, provider=None, **kwargs):
    args = dict(model='custom', system='system', messages=[], tools=[], max_output_tokens=100)
    args.update(kwargs)
    return budget.check_request_budget(provider or Provider(), **args)


def test_fallback_counts_system_tools_history_and_utf8_bytes(budget):
    assert check(budget).fits
    assert not check(budget, system='Я' * 9000).fits
    assert not check(budget, tools=[{'description': 'x' * 17000}]).fits
    decision = check(budget, messages=[{'role': 'user', 'content': 'x' * 17000}])
    assert not decision.fits
    assert decision.input_tokens is None
    assert decision.method == 'utf8_bytes_fallback'
    assert decision.request_bytes > 17000
    assert not check(budget, fallback_bytes=90000, system='x' * 20000).fits


def test_chat_unknown_context_accepts_large_tool_catalog_but_caps_history(budget):
    args=dict(model='custom',system='system',messages=[{'role':'user','content':'hello'}],
              tools=[{'description':'schema documentation '*12000}],max_output_tokens=0)
    assert not budget.check_request_budget(Provider(),**args).fits
    greeting=budget.check_chat_request_budget(Provider(),**args)
    assert greeting.fits
    assert greeting.input_tokens is None
    assert greeting.method=='chat_utf8_bytes_safety_cap'
    assert greeting.limit==1048576
    args['messages']=[{'role':'tool','content':'raw evidence '*100000}]
    oversized=budget.check_chat_request_budget(Provider(),**args)
    assert not oversized.fits
    assert oversized.input_tokens is None


def test_chat_known_physical_context_retains_reserves_and_reliable_counts(budget,monkeypatch):
    args=dict(model='custom',system='x'*20000,messages=[],tools=[],max_output_tokens=1000,
              context_window_tokens=64000,working_input_tokens=32768)
    result=budget.check_chat_request_budget(Provider(),**args)
    assert result.fits
    assert result.input_tokens is None
    assert result.limit==56600
    args['system']='x'*57000
    assert not budget.check_chat_request_budget(Provider(),**args).fits
    monkeypatch.setattr(budget,'_token_count',lambda *a:(33000,'mapped_token_counter'))
    result=budget.check_chat_request_budget(Provider(),**args)
    assert not result.fits
    assert result.input_tokens==33000
    assert result.limit==32768


def test_reliable_count_checks_working_limit_and_output_reservation(budget, monkeypatch):
    monkeypatch.setattr(budget, '_token_count', lambda *a: (1000, 'mapped_token_counter'))
    assert check(budget, working_input_tokens=1001).fits
    assert not check(budget, working_input_tokens=999).fits
    assert not check(budget, context_window_tokens=2000, max_output_tokens=900).fits
    assert not check(budget, context_window_tokens=9000, max_output_tokens=0).fits


def test_unmapped_litellm_count_is_not_exact_and_prefix_is_preserved(budget, monkeypatch):
    calls = []
    class Response:
        status_code = 200
        def json(self):
            return {'total_tokens': 1, 'model_used': 'underlying-other'}
    def post(url, **kwargs):
        calls.append((url, kwargs))
        return Response()
    monkeypatch.setattr(budget.requests, 'post', post)
    provider = Provider()
    provider._base_url = 'https://example.test/proxy/v1'
    provider._api_key = 'secret'
    decision = check(budget, provider, system='x' * 17000)
    assert not decision.fits
    assert decision.input_tokens is None
    assert calls[0][0] == 'https://example.test/proxy/utils/token_counter'
    assert calls[0][1]['timeout'] <= 2
    assert calls[0][1]['allow_redirects'] is False
    assert calls[0][1]['headers']['Authorization'] == 'Bearer secret'


def test_missing_endpoint_capability_is_cached(budget, monkeypatch):
    calls = []
    def post(*args, **kwargs):
        calls.append(1)
        return SimpleNamespace(status_code=404)
    monkeypatch.setattr(budget.requests, 'post', post)
    provider = Provider()
    provider._base_url = 'https://offline.test/v1'
    check(budget, provider)
    check(budget, provider, system='different')
    assert len(calls) == 1


def test_fallback_respects_small_context_and_reliable_metadata(budget, monkeypatch):
    assert not check(budget, context_window_tokens=100, max_output_tokens=100).fits
    provider = Provider()
    provider._base_url = 'https://mapped.test/v1'
    response = SimpleNamespace(status_code=200, json=lambda: {
        'total_tokens': 1200, 'request_model': 'custom', 'model_used': 'real-model',
        'tokenizer': 'real-tokenizer', 'exact': True})
    monkeypatch.setattr(budget.requests, 'post', lambda *a, **kw: response)
    decision = check(budget, provider, working_input_tokens=1000)
    assert decision.input_tokens == 1200
    assert not decision.fits


def test_stock_litellm_provider_count_needs_no_invented_exact_field(budget, monkeypatch):
    provider = Provider()
    provider._base_url = 'https://provider-counter.test/v1'
    response = SimpleNamespace(status_code=200, json=lambda: {
        'total_tokens': 1200, 'request_model': 'custom', 'model_used': 'Qwen/deployed',
        'count_source': 'provider', 'tokenizer_type': 'provider'})
    monkeypatch.setattr(budget.requests, 'post', lambda *a, **kw: response)
    result = check(budget, provider, working_input_tokens=1000)
    assert result.input_tokens == 1200
    assert not result.fits


def test_local_qwen_counter_requires_explicit_verified_alias_mapping(budget, monkeypatch):
    provider = Provider()
    provider._base_url = 'https://mapped-local-counter.test/v1'
    response = SimpleNamespace(status_code=200, json=lambda: {
        'total_tokens': 1200, 'request_model': 'custom', 'model_used': 'Qwen/deployed',
        'count_source': 'local_estimate', 'tokenizer_type': 'huggingface_tokenizer'})
    monkeypatch.setenv('IRIS_CHATBOT_TOKENIZER_MODELS', '{"custom":"Qwen/deployed"}')
    monkeypatch.setattr(budget.requests, 'post', lambda *a, **kw: response)
    result = check(budget, provider, working_input_tokens=1000)
    assert result.input_tokens == 1200
    assert result.method == 'verified_tokenizer_estimate'
    assert not result.fits


@pytest.mark.parametrize('error_flag', [False, True])
def test_zero_or_failed_count_does_not_authorize_an_oversized_request(budget, monkeypatch, error_flag):
    provider = Provider()
    provider._base_url = 'https://invalid-count.test/v1'
    response = SimpleNamespace(status_code=200, json=lambda: {
        'total_tokens': 0, 'request_model': 'custom', 'model_used': 'Qwen/deployed',
        'count_source': 'provider', 'error': error_flag})
    monkeypatch.setattr(budget.requests, 'post', lambda *a, **kw: response)
    decision = check(budget, provider, system='x' * 17000)
    assert decision.input_tokens is None
    assert not decision.fits


def test_real_openai_wire_includes_tool_result_content_and_schema(budget, monkeypatch):
    source = Path(__file__).parents[2] / 'source/app'
    def load(relative, name):
        spec = importlib.util.spec_from_file_location(name, source / relative)
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
        return module
    base = load('iris_engine/llm/providers/base.py', 'app.iris_engine.llm.providers.base')
    load('observability_logging.py', 'app.observability_logging')
    adapter = load('iris_engine/llm/providers/openai.py', 'budget_openai_adapter')
    provider = adapter.OpenAIProvider(api_key='test', base_url='https://wire.test/v1')
    monkeypatch.setattr(budget, '_token_count', lambda *a: (None, 'utf8_bytes_fallback'))
    messages = [base.ChatMessage(role='tool', content=[{
        'type': 'tool_result', 'tool_use_id': 'call1', 'content': 'Я' * 6000}])]
    tools = [base.ToolSpec(name='inspect', description='test', input_schema={'type': 'object'})]
    decision = check(budget, provider, messages=messages, tools=tools)
    assert not decision.fits
    assert decision.request_bytes > 36000
    # A small wire request still includes the full provider-generated envelope.
    small = check(budget, provider, system='s', messages=[], tools=tools)
    assert small.fits
    wire = provider._build_body('custom', 's', [], tools, 100)
    assert small.request_bytes == len(json.dumps(wire, allow_nan=False).encode('utf-8'))


def test_reliable_counter_caches_hash_only_and_separates_changed_request(budget, monkeypatch):
    calls = []
    provider = Provider()
    provider._base_url = 'https://cache.test/v1'
    provider._api_key = 'sensitive-credential'
    def post(*args, **kwargs):
        calls.append(1)
        return SimpleNamespace(status_code=200, json=lambda: {
            'total_tokens': 10, 'request_model': 'custom', 'model_used': 'mapped',
            'tokenizer': 'mapped', 'exact': True})
    monkeypatch.setattr(budget.requests, 'post', post)
    check(budget, provider, system='sensitive-source-text')
    check(budget, provider, system='sensitive-source-text')
    check(budget, provider, system='changed')
    assert len(calls) == 2
    cache_text = repr(budget._COUNTS) + repr(budget._CAPABILITIES)
    assert 'sensitive-credential' not in cache_text
    assert 'sensitive-source-text' not in cache_text
