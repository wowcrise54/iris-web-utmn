"""Storage, immutable snapshots and one-step worker contract without IRIS startup."""
import ast
from contextlib import nullcontext
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

SOURCE = Path(__file__).parents[2] / 'source/app/iris_engine/evidence'


def load(name):
    spec = importlib.util.spec_from_file_location('alert_worker_test_' + name, SOURCE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


storage = load('alert_storage')
normalizer = load('alert_source')
pipeline = load('alert_pipeline')


def functions(**env):
    import hashlib
    import re
    env = {'dt': dt, 'json': json, 'hashlib': hashlib, 'digest': pipeline.digest,
           'VERSION': pipeline.VERSION, 'SYSTEM': 'system', 'FACTS': 'facts', 're': re, 'os': os, **env}
    tree = ast.parse((SOURCE / 'alert_tasks.py').read_text())
    tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    for node in tree.body:
        node.decorator_list = []
    exec(compile(ast.fix_missing_locations(tree), '<alert-worker>', 'exec'), env)
    return env


def cfg(**values):
    return NS(provider='custom', model='qwen-fixture', base_url='http://litellm.test/v1',
              api_key='fixture-credential', max_output_tokens=8192, context_window_tokens=262144,
              redact_ips=False, redact_emails=False, redact_hashes=False, **values)


def alert(**values):
    return NS(alert_id=9, alert_customer_id=3, alert_source_content={'events': [{'uuid': 'one', 'script': 'test'}],
              'event_collection': {'complete': False, 'missing_uuids': ['missing']}},
              alert_context={}, iocs=[], assets=[], **values)


def workspace_env(tmp_path):
    db = NS(session=NS(get=Mock(return_value=NS(resolved_policy_id=4)), commit=Mock()))
    api = functions(Workspace=storage.Workspace, normalize_source=normalizer.normalize_source,
                    pack_units=normalizer.pack_units, initial_state=pipeline.initial_state, db=db,
                    CaseChatConversation=object, parse_source_json=normalizer.parse_source_json)
    api['_folder'] = lambda key: tmp_path / key
    api['_locked'] = lambda job: job
    return api


def job(**values):
    return NS(id=1, requested_by=7, conversation_id=5, result={}, **values)


def test_private_immutable_objects_and_integrity_checks(tmp_path):
    store = storage.Workspace(tmp_path)
    value = {'script': 'Не выполнять: example', 'unknown': [1, 2]}
    key = store.put(value)
    assert store.get(key) == value
    assert store.put(value) == key
    assert len(list(tmp_path.iterdir())) == 1
    with pytest.raises(ValueError, match='Invalid'):
        store.get('../outside')
    (tmp_path / (key + '.json')).write_text('{}')
    with pytest.raises(ValueError, match='integrity'):
        store.get(key)


def test_response_cache_persists_between_workspace_instances(tmp_path):
    store = storage.Workspace(tmp_path)
    key = pipeline.digest({'packet': 1, 'policy': 4})
    assert store.cached(key) is None
    store.cache(key, {'facts': []})
    assert storage.Workspace(tmp_path).cached(key) == {'facts': []}


def test_normalized_manifest_offsets_remain_identical_after_reload(tmp_path):
    value = normalizer.normalize_source({'z': 1, 'a': {'z': 'текст', 'a': 3}})
    store = storage.Workspace(tmp_path)
    store.normalized = value
    original = store.source('manifest')
    identifier = store.put(value)
    store.normalized = store.get(identifier)
    assert store.source('manifest') == original == normalizer.manifest_text(value)


def test_snapshot_is_not_changed_when_live_alert_changes(tmp_path):
    api = workspace_env(tmp_path)
    value, task = alert(), job()
    store = api['_workspace'](task, value, cfg())
    original = store.get(task.result['_snapshot_key'])
    value.alert_source_content = {'events': ['changed']}
    restored = api['_workspace'](task, value, cfg())
    assert restored.get(task.result['_snapshot_key']) == original
    assert original['alert_source_content'] != value.alert_source_content


def test_initial_packets_label_every_original_reference(tmp_path):
    api = workspace_env(tmp_path)
    task = job()
    store = api['_workspace'](task, alert(), cfg())
    for key in task.result['_pipeline']['pending']:
        packet = store.get(key)
        for ref in packet['references']:
            assert f"SOURCE {ref['source_id']} [{ref['offset']}:{ref['end_offset']}]" in packet['text']


def test_cancel_during_snapshot_preparation_survives_checkpoint(tmp_path):
    api = workspace_env(tmp_path)
    task = job()
    def locked(task):
        task.result = {'_cancel_requested': True}
        return task
    api['_locked'] = locked
    api['_workspace'](task, alert(), cfg())
    assert task.result['_cancel_requested'] is True
    assert task.result['_pipeline']['stage'] == 'map'


def test_completed_snapshot_is_reused_but_owner_and_customer_are_isolated(tmp_path):
    api = workspace_env(tmp_path)
    first = job()
    store = api['_workspace'](first, alert(), cfg())
    cache_key = pipeline.digest({'completed': True, 'snapshot': first.result['snapshot_hash'],
                                 'config': api['_config_key'](cfg())})
    complete = pipeline.initial_state([])
    complete.update(stage='completed', inferences=23, cache_hits=0)
    store.cache(cache_key, complete)
    repeat = job()
    api['_workspace'](repeat, alert(), cfg())
    assert repeat.result['_pipeline']['stage'] == 'completed'
    assert repeat.result['_pipeline']['inferences'] == 0
    assert repeat.result['_pipeline']['cache_hits'] == 23
    other = job()
    other.requested_by = 8
    api['_workspace'](other, alert(), cfg())
    assert other.result['_pipeline']['stage'] == 'map'
    moved = alert()
    moved.alert_customer_id = 6
    another = job()
    api['_workspace'](another, moved, cfg())
    assert another.result['_workspace_key'] != first.result['_workspace_key']


def test_model_change_does_not_mix_old_facts(tmp_path):
    api = workspace_env(tmp_path)
    task = job()
    api['_workspace'](task, alert(), cfg())
    changed = cfg()
    changed.model = 'other'
    with pytest.raises(ValueError, match='Model settings changed'):
        api['_workspace'](task, alert(), changed)


def test_unchanged_packet_cache_scope_survives_new_snapshot_but_not_customer_changes(tmp_path):
    api = workspace_env(tmp_path)
    first = job()
    api['_workspace'](first, alert(), cfg())
    changed = alert()
    changed.alert_source_content = {'events': [{'uuid': 'new-event'}]}
    second = job()
    api['_workspace'](second, changed, cfg())
    assert first.result['_workspace_key'] != second.result['_workspace_key']
    assert first.result['_response_scope_key'] == second.result['_response_scope_key']
    changed.alert_customer_id = 8
    third = job()
    api['_workspace'](third, changed, cfg())
    assert third.result['_response_scope_key'] != second.result['_response_scope_key']


def test_checkpoint_reload_is_locked_and_does_not_autoflush_stale_json():
    query = Mock()
    query.filter_by.return_value.populate_existing.return_value.with_for_update.return_value.one.return_value = 'fresh'
    db = NS(session=NS(no_autoflush=nullcontext()))
    api = functions(db=db, EvidenceAnalysis=NS(query=query))
    assert api['_locked'](NS(id=4)) == 'fresh'
    query.filter_by.assert_called_once_with(id=4)
    query.filter_by.return_value.populate_existing.assert_called_once()


def test_source_reads_are_bounded_and_recheck_acl(tmp_path):
    api = workspace_env(tmp_path)
    task = job()
    store = api['_workspace'](task, alert(), cfg())
    api['authorize_alert_analysis'] = Mock()
    unit = store.normalized['units'][0]
    value = api['read_analysis_source'](task, unit['id'], 0, 3)
    assert value['text'] == unit['text'][:3]
    assert value['untrusted_data'] is True
    api['authorize_alert_analysis'].assert_called_once_with(task)
    with pytest.raises(ValueError):
        api['read_analysis_source'](task, '../outside', 0, 3)
    with pytest.raises(ValueError):
        api['read_analysis_source'](task, unit['id'], 0, 9000)


def test_claim_markdown_cannot_inject_an_image_or_heading():
    state = {'verdict': 'suspicious', 'verified': [{'claim': '# injected\n![track](https://example.test)',
             'reference': {'source_id': 'one', 'offset': 0, 'end_offset': 1}}], 'unsupported': []}
    text = pipeline.report(state, {'available_events': 1, 'missing_events': [], 'source_complete': True}, lambda ref: '/safe')
    assert '\n# injected' not in text
    assert '![track](' not in text


def test_request_metrics_count_failed_attempts_without_inventing_usage():
    api = functions()
    stats = api['_request_stats']({'model_requests': 1}, {'request_bytes': 1200})
    assert stats['model_requests'] == 2 and stats['request_bytes_total'] == 1200
    assert stats['usage_incomplete'] is True
    assert 'prompt_tokens_total' not in stats


def test_revocation_during_token_counting_stops_generation_before_audit(tmp_path):
    task = NS(id=1, result={'_workspace_key': 'a' * 64})
    store = storage.Workspace(tmp_path / ('a' * 64))
    user, conv, settings = NS(id=7), NS(id=8), cfg()
    authorize = Mock(side_effect=[(user, None), LookupError('revoked')])
    biz = NS(record_egress=Mock())
    api = functions(Workspace=storage.Workspace, authorize_alert_analysis=authorize, case_chat=biz,
        ChatMessage=lambda **kw:NS(**kw), redact_text=lambda value,**kw:value,
        check_request_budget=lambda *a,**kw:NS(fits=True,request_bytes=100,method='mapped_token_counter',input_tokens=20),
        log=Mock())
    api['_folder'] = lambda key: tmp_path / key
    api['_config'] = lambda *a: (conv, settings)
    with pytest.raises(LookupError):
        api['_infer'](task, store, NS(name='custom'), settings, conv, user, 'map',
                      {'text':'source','references':[{'source_id':'one','offset':0,'end_offset':6}]})
    biz.record_egress.assert_not_called()
