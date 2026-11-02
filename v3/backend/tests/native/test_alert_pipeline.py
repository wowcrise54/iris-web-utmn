"""Finite orchestration tests with inert model replies, no IRIS startup."""
import importlib.util
from pathlib import Path
import json

import pytest

PATH = Path(__file__).parents[2] / 'source/app/iris_engine/evidence/alert_pipeline.py'
spec = importlib.util.spec_from_file_location('alert_pipeline_test_module', PATH)
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)


class Store:
    def __init__(self):
        self.items = {}
        self.texts = {'u:one': 'PowerShell executed a documented local script. ' * 100}
        self.coverage = {'available_events': 9, 'missing_events': ['missing'] * 6,
                         'source_complete': False}

    def put(self, value):
        key = pipeline.digest(value)
        self.items[key] = json.loads(json.dumps(value))
        return key

    def get(self, key):
        return self.items[key]

    def source(self, key):
        return self.texts[key]

    def packet(self, start=0, end=1200):
        return self.put({'text': self.texts['u:one'][start:end], 'references': [
            {'source_id': 'u:one', 'offset': start, 'end_offset': end}]})


def answer(stage, payload):
    if stage in ('map', 'reduce'):
        return {'facts': [{'claim': 'A local script executed.', 'kind': 'observation', 'source_ids': ['u:one']}]}
    if stage == 'verify':
        return {'supported': True}
    return {'verdict': 'likely_legitimate', 'decisive_fact_ids': [payload['facts'][0]['id']]}


def test_finite_full_coverage_and_missing_source_are_not_a_clean_verdict():
    store = Store()
    state = pipeline.initial_state([store.packet(0, 1200), store.packet(1200, 2400)])
    calls = []
    def infer(stage, payload):
        calls.append((stage, json.dumps(payload)))
        return answer(stage, payload)
    for _ in range(40):
        state = pipeline.advance(state, store, infer)
        if state['stage'] == 'completed':
            break
    assert state['stage'] == 'completed'
    assert state['mapped_count'] == 2
    assert [stage for stage, _ in calls] == ['map', 'map', 'reduce', 'verify', 'final']
    assert state['verdict'] == 'insufficient_evidence'
    assert 'PowerShell' not in calls[-1][1]  # final request contains facts, not raw history
    report = pipeline.report(state, store.coverage, lambda ref: '/source')
    assert '9' in report and '6' in report and 'неполная' in report


def test_context_rejection_splits_only_current_packet_and_preserves_ranges():
    store = Store()
    state = pipeline.initial_state([store.packet(0, 2400)])
    def reject(stage, payload):
        raise pipeline.SplitPacket('context', provider_rejection=True)
    state = pipeline.advance(state, store, reject)
    packets = [store.get(key) for key in state['pending']]
    refs = [p['references'][0] for p in packets]
    assert refs[0]['offset'] == 0 and refs[1]['end_offset'] == 2400
    assert refs[0]['end_offset'] >= refs[1]['offset']
    assert state['mapped_count'] == 0 and state['map_total'] == 2
    for _ in range(1):
        state = pipeline.advance(state, store, reject)
    with pytest.raises(ValueError, match='two smaller-packet retries'):
        pipeline.advance(state, store, reject)


def test_reducer_cannot_invent_source_references():
    with pytest.raises(ValueError, match='unsupported source'):
        pipeline.validate_node({'facts': [{'claim': 'Invented', 'source_ids': ['other']}]},
                               [{'source_id': 'one', 'offset': 0, 'end_offset': 1}])


def test_checkpoint_is_not_mutated_when_call_fails():
    store = Store()
    state = pipeline.initial_state([store.packet()])
    original = json.dumps(state)
    def fail(*args):
        raise RuntimeError('network interrupted')
    with pytest.raises(RuntimeError):
        pipeline.advance(state, store, fail)
    assert json.dumps(state) == original


def test_unsupported_claim_is_not_in_final_report():
    store = Store()
    state = pipeline.initial_state([store.packet()])
    def infer(stage, payload):
        if stage == 'verify':
            return {'supported': False}
        if stage == 'final':
            return {'verdict': 'malicious', 'decisive_fact_ids': []}
        return answer(stage, payload)
    for _ in range(40):
        state = pipeline.advance(state, store, infer)
        if state['stage'] == 'completed':
            break
    assert state['stage'] == 'completed' and not state['verified']
    assert len(state['unsupported']) == 1
    assert state['verdict'] == 'insufficient_evidence'
    assert 'A local script executed' not in pipeline.report(state, store.coverage, lambda r: '/')


def test_large_node_is_rejected_without_silently_truncating_claims():
    with pytest.raises(ValueError, match='bounded working memory'):
        pipeline.validate_node({'facts': [{'claim': 'Я' * 6000, 'source_ids': ['one']}]},
                               [{'source_id': 'one', 'offset': 0, 'end_offset': 7000}])
