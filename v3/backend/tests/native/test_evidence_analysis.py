"""Evidence integrity, transport failures and offline isolation without booting IRIS."""
import ast
import gzip
import importlib.util
import json
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

SOURCE = Path(os.environ.get('IRIS_SOURCE') or (Path(__file__).parents[2] / 'source'))
ENGINE = SOURCE / 'app/iris_engine/evidence'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def pcap():
    return load(ENGINE / 'pcap.py', 'evidence_pcap_test')


@pytest.mark.parametrize('magic', [b'\xd4\xc3\xb2\xa1', b'\xa1\xb2\xc3\xd4', b'\x4d\x3c\xb2\xa1', b'\xa1\xb2\x3c\x4d', b'\x0a\x0d\x0d\x0a'])
def test_content_detection_including_nanosecond_and_big_endian(pcap, magic):
    assert pcap.capture_bytes(magic + b'capture') == magic + b'capture'
    assert pcap.capture_bytes(gzip.compress(magic + b'capture')).startswith(magic)


def test_video_invalid_and_expansion_limits(pcap, monkeypatch):
    for raw in (b'\x00\x00\x00\x18ftypmp42', b'video.mp4', b'PK\x03\x04sample'):
        with pytest.raises(ValueError, match='Only PCAP'):
            pcap.capture_bytes(raw)
    monkeypatch.setattr(pcap, 'MAX_INPUT', 128)
    with pytest.raises(ValueError, match='Expanded'):
        pcap.capture_bytes(gzip.compress(b'\xd4\xc3\xb2\xa1' + b'a' * 500))
    with pytest.raises(ValueError, match='exceeds'):
        pcap.capture_bytes(b'x' * 129)


def row(frame=1, src='10.0.0.1', dst='1.1.1.1', sport='1234', port='53', domain='example.org'):
    return '\t'.join(map(str, [frame, 1700000000 + frame, 100, src, '', dst, '', '', sport, '', port, 'DNS', domain, '', '']))


def test_flows_are_bounded_and_cite_frames_without_payload(pcap):
    result = pcap.parse_rows([row(), row(2), row(3, sport='4321'), 'malformed payload=private'])
    assert result['packets'] == 3
    assert len(result['edges']) == 2
    assert result['edges'][0]['packets'] == 2
    assert result['edges'][0]['first_frame'] == 1
    assert result['indicators'][0]['frame'] == 1
    assert 'private' not in json.dumps(result)
    result = pcap.parse_rows(row(i + 1, port=str(1000 + i)) for i in range(200))
    assert len(result['edges']) == 150
    assert result['omitted_packets_from_graph'] == 50
    assert result['partial'] is True


@pytest.mark.skipif(sys.platform != 'linux', reason='Linux process launcher')
def test_timeout_cleans_temporary_evidence(pcap, monkeypatch):
    folders = []
    def timeout(args, **kwargs):
        folders.append(Path(args[-1]).parent)
        raise subprocess.TimeoutExpired(args, 120)
    monkeypatch.setattr(pcap.subprocess, 'run', timeout)
    with pytest.raises(ValueError, match='120 seconds'):
        pcap.analyze_capture(b'\xd4\xc3\xb2\xa1capture')
    assert folders and not folders[0].exists()


def sample_packet():
    dns = b'\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x07example\x03org\x00\x00\x01\x00\x01'
    udp = struct.pack('!HHHH', 12000, 53, 8 + len(dns), 0) + dns
    ip = struct.pack('!BBHHHBBH4s4s', 0x45, 0, 20 + len(udp), 1, 0, 64, 17, 0, b'\x0a\x00\x00\x01', b'\x01\x01\x01\x01') + udp
    return b'\x00' * 12 + b'\x08\x00' + ip


def fixture_capture(pcapng=False):
    packet = sample_packet()
    if not pcapng:
        return struct.pack('<IHHIIII', 0xa1b2c3d4, 2, 4, 0, 0, 65535, 1) + struct.pack('<IIII', 1700000000, 0, len(packet), len(packet)) + packet
    def block(kind, body):
        n = len(body) + 12
        return struct.pack('<II', kind, n) + body + struct.pack('<I', n)
    header = block(0x0a0d0d0a, struct.pack('<IHHq', 0x1a2b3c4d, 1, 0, -1))
    interface = block(1, struct.pack('<HHI', 1, 0, 65535))
    ticks = 1700000000000000
    body = struct.pack('<IIIII', 0, ticks >> 32, ticks & 0xffffffff, len(packet), len(packet)) + packet
    body += b'\x00' * ((-len(packet)) % 4)
    return header + interface + block(6, body)


@pytest.mark.skipif(sys.platform != 'linux' or not shutil.which('tshark'), reason='Requires packaged Linux TShark')
@pytest.mark.parametrize('pcapng', [False, True])
def test_real_isolated_tshark(pcap, pcapng):
    result = pcap.analyze_capture(fixture_capture(pcapng))
    assert result['packets'] == 1
    assert result['indicators'][0]['value'] == 'example.org'
    assert result['edges'][0]['first_frame'] == 1


@pytest.mark.skipif(sys.platform != 'linux', reason='Linux syscall isolation')
def test_isolation_blocks_even_socket_creation():
    script = """import importlib.util, socket, os, sys
spec=importlib.util.spec_from_file_location('child', sys.argv[1]); c=importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
def probe(*args):
    try: socket.socket()
    except PermissionError: print('network denied')
    else: raise AssertionError('socket creation was allowed')
    try: open('/iriswebapp/app/configuration.py').read()
    except PermissionError: print('other files denied'); return
    raise AssertionError('socket creation was allowed')
os.execve=probe
sys.argv=['child',sys.argv[1]]
c.main()
"""
    result = subprocess.run([sys.executable, '-c', script, str(ENGINE / 'pcap_child.py')], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert 'network denied' in result.stdout
    assert 'other files denied' in result.stdout


@pytest.fixture
def events(monkeypatch):
    base = load(SOURCE / 'app/iris_engine/llm/providers/base.py', 'evidence_llm_base_test')
    monkeypatch.setitem(sys.modules, 'app.iris_engine.llm.providers.base', base)
    diagnostics = load(SOURCE / 'app/iris_engine/llm/diagnostics.py', 'evidence_diagnostics_test')
    return base, diagnostics


def extract(path, name, scope):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    node = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    node.decorator_list = []
    future = ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)
    module = ast.fix_missing_locations(ast.Module(body=[future, node], type_ignores=[]))
    exec(compile(module, str(path), 'exec'), scope)
    return scope[name]


def test_provider_timeout_diagnostics_never_log_sensitive_body(events, caplog):
    base, diagnostics = events
    def broken(**kwargs):
        yield base.TextDelta('partial')
        raise requests.Timeout('private-api-key private-packet-data')
    output = list(diagnostics.provider_events(SimpleNamespace(name='test', stream_completion=broken), correlation_id='test-123'))
    assert output[-1].provider_code == 'timeout'
    assert 'test-123' in caplog.text
    assert 'private-api-key' not in caplog.text
    assert 'private-packet-data' not in str(output)


@pytest.mark.parametrize('failure', ['http502', 'abrupt'])
def test_partial_chat_output_is_persisted_on_gateway_failure(events, failure):
    base, diagnostics = events
    emitted, saved = [], []
    def stream(**kwargs):
        assert kwargs['max_tokens'] == 2048
        yield base.TextDelta('Important partial findings')
        if failure == 'http502':
            yield base.Error('Provider HTTP 502', provider_code='http_502', http_status=502)
    def finalize(**kwargs):
        saved.append(kwargs)
        return SimpleNamespace(terminated=True)
    scope = dict(provider_events=diagnostics.provider_events, TextDelta=base.TextDelta, ToolUseEnd=base.ToolUseEnd,
                 MessageEnd=base.MessageEnd, Error=base.Error, ROLE_TOOL='tool', _event_bytes=lambda e: 0,
                 ChatEvent=lambda name,payload: SimpleNamespace(name=name,payload=payload),
                 _TurnResult=SimpleNamespace, _finalise_turn=finalize,
                 case_chat_biz=SimpleNamespace(finalise_egress=Mock()))
    consume = extract(SOURCE / 'app/blueprints/rest/v2/case_chat/loop.py', '_consume_stream', scope)
    consume(provider=SimpleNamespace(name='test', stream_completion=stream), model='m', system='s', history=[],
            tools=[], conversation=SimpleNamespace(id=1), audit_row=SimpleNamespace(id=2), emit=emitted.append)
    assert saved[0]['text'] == 'Important partial findings'
    assert saved[0]['tool_uses'] == []
    assert emitted[-1].name == 'error'
    assert emitted[-1].payload['request_id'] == 'chat-1-2'


def test_rolling_pages_are_complete_and_input_bounded(events):
    summary = load(ENGINE / 'summary.py', 'evidence_summary_test')
    data = 'данные ' * 4000
    chunks = list(summary.pages(data, 'sandbox:2:log:3'))
    assert ''.join(p['text'] for p in chunks) == data
    assert max(len(p['text']) for p in chunks) <= 12000
    message = summary.summary_messages('prior notes', chunks[1])[0].content[0]['text']
    assert 'sandbox:2:log:3' in message
    assert str(chunks[1]['offset']) in message
    assert len(message) < 14000


def test_api_refuses_access_before_creating_a_job():
    start = Mock()
    scope = {'access': lambda cid: False, 'ac_api_return_access_denied': lambda: 'denied', 'start_job': start}
    route = extract(SOURCE / 'app/blueprints/rest/v2/case_routes/evidence_analysis.py', 'start_analysis', scope)
    assert route(123) == 'denied'
    start.assert_not_called()


def test_job_lookup_is_bound_to_case_and_owner():
    query = Mock()
    query.filter_by.return_value.first.return_value = None
    lookup = extract(SOURCE / 'app/business/evidence_analysis.py', 'get_job', {'EvidenceAnalysis': SimpleNamespace(query=query)})
    with pytest.raises(LookupError): lookup(12, 34, 56)
    query.filter_by.assert_called_once_with(id=34, case_id=12, requested_by=56)


def test_provider_budget_stops_oversized_tool_arguments(events):
    base, diagnostics = events
    closed = []
    def stream(**kwargs):
        try:
            yield base.ToolUseDelta('tool-id', 'x' * 49000)
            raise AssertionError('Should stop before more provider data is consumed')
        finally:
            closed.append(True)
    result = list(diagnostics.provider_events(SimpleNamespace(name='test', stream_completion=stream), correlation_id='budget'))
    assert isinstance(result[-1], base.Error)
    assert result[-1].provider_code == 'output_limit'
    assert closed == [True]


@pytest.mark.parametrize('name', ['openai', 'anthropic', 'ollama'])
def test_adapters_preserve_502_status_without_gateway_body(events, monkeypatch, name):
    base, _ = events
    module = load(SOURCE / f'app/iris_engine/llm/providers/{name}.py', 'evidence_adapter_' + name)
    response = SimpleNamespace(status_code=502, close=Mock(), text='secret gateway body')
    monkeypatch.setattr(module.requests, 'post', Mock(return_value=response))
    cls = {'openai': module.__dict__.get('OpenAIProvider'), 'anthropic': module.__dict__.get('AnthropicProvider'), 'ollama': module.__dict__.get('OllamaProvider')}[name]
    provider = cls(api_key='test', base_url='https://example.test')
    result = list(provider.stream_completion(model='m',system='s',messages=[],tools=[]))
    assert result[0].http_status == 502
    assert 'secret' not in result[0].message
    response.close.assert_called_once()


@pytest.mark.parametrize('name', ['openai', 'anthropic', 'ollama'])
def test_adapters_do_not_mark_abrupt_stream_as_completed(events, monkeypatch, name):
    base, _ = events
    module = load(SOURCE / f'app/iris_engine/llm/providers/{name}.py', 'evidence_abrupt_' + name)
    lines = {
        'openai': ['data: ' + json.dumps({'choices':[{'delta':{'content':'partial'}}]}), 'data: [DONE]'],
        'anthropic': ['event: content_block_delta', 'data: '+json.dumps({'delta':{'type':'text_delta','text':'partial'}}), ''],
        'ollama': [json.dumps({'message':{'content':'partial'},'done':False})]
    }[name]
    response = SimpleNamespace(status_code=200, close=Mock(), iter_lines=lambda **kw: iter(lines))
    monkeypatch.setattr(module.requests, 'post', Mock(return_value=response))
    cls = {'openai': module.__dict__.get('OpenAIProvider'), 'anthropic': module.__dict__.get('AnthropicProvider'), 'ollama': module.__dict__.get('OllamaProvider')}[name]
    provider = cls(api_key='test',base_url='https://example.test')
    result = list(provider.stream_completion(model='m',system='s',messages=[],tools=[]))
    assert any(isinstance(event, base.TextDelta) for event in result)
    assert isinstance(result[-1], base.Error) and result[-1].provider_code == 'incomplete_stream'
    assert not any(isinstance(event, base.MessageEnd) for event in result)
    assert response.close.called


def test_sequential_pages_cover_all_sources_and_exclude_binary(monkeypatch, tmp_path):
    text = load(ENGINE / 'text.py', 'evidence_text_sequence_test')
    raw = ('начало\n' + 'event command line\n' * 10000 + 'critical last event').encode()
    entries = [SimpleNamespace(id=i, name=name, kind=kind, size=len(content), sha256=str(i), error=None, content=content)
               for i, name, kind, content in [(1, 'events.log.gz', 'EVENT_NORMALIZED', gzip.compress(raw)),
                                              (2, 'short.log', 'EVENT_CORRELATED', b'important short log'),
                                              (3, 'video.mp4', 'SCREENSHOT', b'video')]]
    query = Mock()
    query.options.return_value.filter_by.return_value.order_by.return_value = entries
    monkeypatch.setitem(sys.modules, 'app.models.sandbox', SimpleNamespace(SandboxLog=SimpleNamespace(query=query, content='content', id='id')))
    namespace = dict(json=json, hashlib=__import__('hashlib'), defer=lambda x:x,
        db=SimpleNamespace(session=Mock()), text_chunks=text.text_chunks, write_pages=text.write_pages,
        TextPages=text.TextPages, cache_folder=lambda _:tmp_path, MAX_CACHE_BYTES=text.MAX_CACHE_BYTES,
        ptsandbox=SimpleNamespace(get_scan=lambda *args:SimpleNamespace(id=7,report={'large':'r'*120000})))
    collect = extract(ENGINE / 'tasks.py', 'evidence_pages', namespace)
    job = SimpleNamespace(id=9, case_id=2, source={'scan_id':7}, progress=0, result={})
    chunks, omissions = collect(job)
    assert not omissions and len(chunks)>20
    selected = [chunks[i] for i in range(len(chunks)) if chunks[i]['source']=='sandbox:7:log:1']
    assert ''.join(page['text'] for page in selected).encode() == raw
    assert selected[-1]['text'].endswith('critical last event')
    assert all(page['end_offset']==selected[i+1]['offset'] for i,page in enumerate(selected[:-1]))
    assert chunks.coverage(len(chunks))[1]['complete']
    assert chunks.coverage(1)[1]['processed_pages']==0
    assert chunks.coverage(len(chunks))[3]['excluded']
    assert not chunks.references('[sandbox:7:log:1@999999999]')
    assert chunks.references('[sandbox:7:log:1@0]')[0]['text'].startswith('начало')
    # Cached pages are reused, without rerunning the decoder.
    namespace['text_chunks'] = Mock(side_effect=AssertionError('must reuse cache'))
    again, _ = collect(job)
    assert len(again)==len(chunks)
    # Rebuild a lost cache without losing a sequential checkpoint.
    namespace['text_chunks'] = text.text_chunks
    (tmp_path/'1.idx').unlink()
    job.progress = 5
    rebuilt, _ = collect(job)
    assert job.progress == 5 and len(rebuilt) == len(chunks)
    assert rebuilt[5] == chunks[5]
    # Old sampled checkpoints must restart, not mix with a full-pass report.
    job.result.pop('text_analysis_version')
    job.result['summary'] = 'legacy sampled notes'
    collect(job)
    assert job.progress == 0 and 'summary' not in job.result
    assert job.result['legacy_checkpoint_restarted']
    entries[0].sha256='changed'
    with pytest.raises(ValueError, match='Source evidence changed'):
        collect(job)


def test_text_cache_reaches_beyond_old_prefix_limit_and_keeps_exact_offsets(tmp_path):
    text = load(ENGINE / 'text.py', 'evidence_text_large_test')
    raw = (b'log event\n' * 1800000) + 'финальное событие'.encode()
    state = {}
    info = text.write_pages(tmp_path, 0, text.text_chunks(gzip.compress(raw), state))
    assert info['characters']>16*1024*1024 and not state['truncated'] and not info['error']
    last = text.read_page(tmp_path, 0, info['pages']-1)
    assert last.endswith('финальное событие')
    assert len(text.read_page(tmp_path, 0, 1400))==text.PAGE_CHARS


def test_text_decoding_and_cache_limits_are_explicit(tmp_path):
    text = load(ENGINE / 'text.py', 'evidence_text_limits_test')
    state = {}
    info = text.write_pages(tmp_path, 0, text.text_chunks(gzip.compress(b'x'*30000), state, limit=20000))
    assert state['truncated'] and info['characters']==20000
    info = text.write_pages(tmp_path, 1, iter(['x'*30000]), budget=12000)
    assert info['truncated'] and info['characters']==12000
    broken = gzip.compress(b'x'*100000)[:-8]
    info = text.write_pages(tmp_path, 2, text.text_chunks(broken, {}))
    assert info['error']=='EOFError' and info['characters']>0
    info = text.write_pages(tmp_path, 3, text.text_chunks(b'\x00binary', {}))
    assert info['error']=='BinaryLogError' and info['pages']==0


def test_private_cache_details_never_leave_job_projection():
    project = extract(SOURCE / 'app/business/evidence_analysis.py', 'projection', {})
    job = SimpleNamespace(id=1,case_id=2,kind='sandbox',status='running',progress=1,total=2,error=None,conversation_id=3,
                          result={'_text_manifest':[{'private':'cache'}], '_source_summaries':{'private':'notes'}, 'coverage':[]})
    assert '_text_manifest' not in project(job)['result']
    assert '_source_summaries' not in project(job,graph=False)['result']


@pytest.mark.skipif(sys.platform != 'linux', reason='Linux process launcher')
def test_metadata_output_limit_keeps_only_complete_rows(pcap, monkeypatch):
    first = (row() + '\n').encode()
    monkeypatch.setattr(pcap,'MAX_OUTPUT',len(first)+2)
    def bounded(args, **kwargs):
        kwargs['stdout'].write(first + (row(2)+'\n').encode())
        return SimpleNamespace(returncode=-25)
    monkeypatch.setattr(pcap.subprocess,'run',bounded)
    result=pcap.analyze_capture(b'\xd4\xc3\xb2\xa1capture')
    assert result['partial'] and result['packets']==1
    assert result['omissions']==['Metadata output size limit reached']


@pytest.mark.parametrize('name', ['openai', 'anthropic', 'ollama'])
def test_initial_provider_timeout_is_distinct_from_connection_failure(events, monkeypatch, name):
    base, _ = events
    module = load(SOURCE / f'app/iris_engine/llm/providers/{name}.py', 'evidence_timeout_' + name)
    monkeypatch.setattr(module.requests, 'post', Mock(side_effect=requests.Timeout('private token')))
    cls = {'openai': module.__dict__.get('OpenAIProvider'), 'anthropic': module.__dict__.get('AnthropicProvider'), 'ollama': module.__dict__.get('OllamaProvider')}[name]
    result = list(cls(api_key='test',base_url='https://example.test').stream_completion(model='m',system='s',messages=[],tools=[]))
    assert result[0].provider_code == 'timeout'
    assert 'private token' not in result[0].message


@pytest.mark.parametrize('live_level', [20, 40])
@pytest.mark.parametrize('response', ['text', 'text_limit', 'empty_limit', 'empty_stop', 'interrupted', 'empty_final_limit', 'empty_retry_exhausted', 'local_openai'])
@pytest.mark.parametrize('output_limit', [0, 2048, 32768])
def test_background_summary_preserves_pinned_chat_policy(events, live_level, response, output_limit, monkeypatch):
    base, diagnostics = events
    conv_type, policy_type = object(), object()
    pinned = SimpleNamespace(id=11)
    conv = SimpleNamespace(id=1, user_id=2, case_id=3, archived_at=None,
                           resolved_policy_id=11, resolved_restriction_level=30)
    session = Mock()
    session.get.side_effect = lambda kind, identifier: conv if kind is conv_type else pinned
    cfg = SimpleNamespace(enabled=True, model='model', max_output_tokens=output_limit, redact_ips=False, redact_emails=False, redact_hashes=False,
                          daily_token_budget_per_user=0, daily_token_budget_org=0)
    configure = Mock(return_value=cfg)
    requests_seen = []
    def stream(**kwargs):
        requests_seen.append(kwargs)
        if response in ('text', 'text_limit'):
            yield base.TextDelta('summary')
        if response != 'interrupted':
            yield base.MessageEnd('end_turn' if response in ('text', 'empty_stop') else 'max_tokens', prompt_tokens=1, completion_tokens=1024)
    provider = SimpleNamespace(name='test', stream_completion=stream)
    if response == 'local_openai':
        module = load(SOURCE/'app/iris_engine/llm/providers/openai.py', 'evidence_local_qwen_adapter')
        fake = Mock(status_code=200)
        fake.iter_lines.return_value = [
            'data: '+json.dumps({'choices':[{'delta':{'reasoning_content':'private reasoning'},'finish_reason':None}]}),
            'data: '+json.dumps({'choices':[{'delta':{'content':'summary'},'finish_reason':'stop'}]}),
            'data: [DONE]']
        def post(url, **kwargs):
            requests_seen.append({'max_tokens':kwargs['json'].get('max_tokens')})
            assert url=='http://local-model.test/v1/chat/completions'
            return fake
        monkeypatch.setattr(module.requests, 'post', post)
        provider = module.OpenAIProvider(api_key='test', base_url='http://local-model.test')
    summary = load(ENGINE / 'summary.py', 'evidence_policy_summary_test')
    namespace = dict(db=SimpleNamespace(session=session), CaseChatConversation=conv_type, ChatbotPolicy=policy_type,
        resolve_for_conversation=lambda _: SimpleNamespace(restriction_level=live_level, policy=SimpleNamespace(id=22)),
        load_config=configure, get_llm_provider=Mock(return_value=provider),
        case_chat=SimpleNamespace(sum_tokens_today=lambda **kw: 0, record_egress=Mock(return_value=SimpleNamespace(id=9)), finalise_egress=Mock()),
        summary_messages=summary.summary_messages, redact_text=lambda value, **kwargs: value,
        provider_events=diagnostics.provider_events, FINAL_TOKENS=2048, SUMMARY_TOKENS=1024,
        TextDelta=base.TextDelta, MessageEnd=base.MessageEnd, Error=base.Error, log=Mock())
    fn=extract(ENGINE / 'tasks.py', 'summarize', namespace)
    job=SimpleNamespace(id=4, case_id=3, conversation_id=1, progress=0, result={})
    if live_level > 30:
        with pytest.raises(ValueError, match='policy changed'): fn(job, SimpleNamespace(id=2), '', None)
        configure.assert_not_called()
    else:
        if response in ('empty_retry_exhausted', 'local_openai'):
            job.result = {'summary_token_budget': 8192}
        page = {'text': 'untrusted data'} if response in ('text_limit', 'empty_limit', 'empty_retry_exhausted', 'local_openai') else None
        if response in ('text', 'text_limit', 'local_openai'):
            assert fn(job, SimpleNamespace(id=2), 'notes', page) == 'summary'
            if response == 'text_limit':
                assert job.result['notes_limited'] == 1
        elif response == 'empty_limit' and 0 < output_limit < 8192:
            assert fn(job, SimpleNamespace(id=2), 'notes', page) is None
            assert job.result['summary_token_budget'] == 8192
        else:
            message = {'empty_stop': 'empty answer', 'interrupted': 'stream ended',
                       'empty_final_limit': 'token budget' if output_limit else 'output limit',
                       'empty_limit': 'token budget' if output_limit else 'output limit',
                       'empty_retry_exhausted': 'token budget' if output_limit else 'output limit'}[response]
            with pytest.raises(ValueError, match=message):
                fn(job, SimpleNamespace(id=2), 'notes', page)
        configure.assert_called_once_with(policy=pinned)
        assert len(requests_seen) == 1
        if output_limit == 0:
            assert requests_seen[0]['max_tokens'] is None
            assert namespace['case_chat'].record_egress.call_args.kwargs['request_snapshot']['max_output_tokens'] is None
        elif output_limit > 8192:
            assert requests_seen[0]['max_tokens'] == output_limit


def test_cache_expiry_and_cleanup_only_touch_private_job_files(monkeypatch, tmp_path):
    text = load(ENGINE / 'text.py', 'evidence_text_cleanup_test')
    monkeypatch.setitem(sys.modules, 'app', SimpleNamespace(app=SimpleNamespace(config={'DATASTORE_PATH': str(tmp_path/'datastore')})))
    folder = text.cache_folder(77)
    text.write_pages(folder, 0, iter(['evidence']))
    text.clear_cache(77)
    assert not folder.exists()
    folder = text.cache_folder(78)
    text.write_pages(folder, 0, iter(['expired evidence']))
    past = __import__('time').time() - 73*3600
    os.utime(folder, (past,past))
    active = text.cache_folder(79)
    text.prune_caches()
    assert not folder.exists() and active.exists()



def test_zstd_log_with_multimegabyte_window_is_read_to_end(tmp_path):
    zstd = pytest.importorskip('zstandard')
    text = load(ENGINE / 'text.py', 'evidence_zstd_window_test')
    raw = b'event metadata\n' * 200000 + b'last event'
    params = zstd.ZstdCompressionParameters.from_level(3, window_log=21, write_content_size=0)
    compressed = zstd.ZstdCompressor(compression_params=params).compress(raw)
    assert zstd.get_frame_parameters(compressed).window_size >= 2*1024*1024
    state = {}
    info = text.write_pages(tmp_path, 0, text.text_chunks(compressed, state))
    assert not info['error'] and not state['truncated']
    assert text.read_page(tmp_path, 0, info['pages']-1).endswith('last event')


def test_zstd_truncation_and_concatenated_frames_are_not_silently_accepted(tmp_path):
    zstd = pytest.importorskip('zstandard')
    text = load(ENGINE / 'text.py', 'evidence_zstd_eof_test')
    raw = b'first event\n' * 20000
    compressed = zstd.ZstdCompressor().compress(raw)
    info = text.write_pages(tmp_path, 0, text.text_chunks(compressed[:-3], {}))
    assert info['error'] == 'EOFError'
    joined = compressed + zstd.ZstdCompressor().compress(b'last event')
    info = text.write_pages(tmp_path, 1, text.text_chunks(joined, {}))
    assert not info['error'] and text.read_page(tmp_path, 1, info['pages']-1).endswith('last event')
