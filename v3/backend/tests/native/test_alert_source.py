"""Lossless source factoring: unknown fields, variants and complete packet coverage."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest


@pytest.fixture
def source():
    path = Path(__file__).parents[2] / 'source/app/iris_engine/evidence/alert_source.py'
    assert path.exists(), 'source normalizer is required'
    spec = importlib.util.spec_from_file_location('alert_source_test', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_exact_duplicates_preserve_variants_unknown_fields_and_paths(source):
    event = {'uuid': 'a', 'message': 'long evidence ' * 200, '_whitelisting': {'x/y~z': [1, True, None]}}
    value = {'events': [event, event, dict(event, variant='different')],
             'event_tree': {'event': event}, 'unknown': {'$ref': 'literal'},
             'event_collection': {'complete': False, 'missing_uuids': ['b', 'c']}}
    result = source.normalize_source(value)
    assert source.reconstruct_source(json.loads(json.dumps(result))) == value
    assert result['coverage'] == {'available_events': 1, 'missing_events': ['b', 'c'],
                                  'source_complete': False, 'normalization_complete': True}
    repeated = [u for u in result['units'] if '/events/0' in u['paths']]
    assert len(repeated) == 1
    assert repeated[0]['occurrences'] == 3
    assert '/event_tree/event' in repeated[0]['paths']
    assert 'a' in repeated[0]['event_ids']
    assert source.normalize_source(value)['source_sha256'] == result['source_sha256']


def test_packets_cover_all_unit_and_manifest_characters_with_exact_offsets(source):
    value = {'events': [{'uuid': str(i), 'body': 'Unicode Я文 ' * 300} for i in range(9)]}
    result = source.normalize_source(value)
    packets = source.pack_units(result, max_chars=190, overlap=17)
    texts = {u['id']: u['text'] for u in result['units']}
    texts['manifest'] = source.manifest_text(result)
    covered = {key: set() for key in texts}
    for packet in packets:
        assert len(packet['text']) <= 190
        assert packet['source_ids']
        for ref in packet['references']:
            key = ref['source_id']
            start, end = ref['offset'], ref['end_offset']
            assert texts[key][start:end] in packet['text']
            covered[key].update(range(start, end))
    assert all(covered[key] == set(range(len(text))) for key, text in texts.items())
    assert result['coverage']['available_events'] == 9


def test_small_units_share_packets_without_repeating_manifest_paths(source):
    result = source.normalize_source({'events': [{'uuid': str(i), 'x': i} for i in range(30)]})
    packets = source.pack_units(result)
    assert len(packets) < len(result['units']) / 2
    assert 'paths' not in source.manifest_text(result)


@pytest.mark.parametrize('as_text', [False, True])
def test_envelope_coverage_describes_nested_source_without_altering_metadata(source, as_text):
    content = {'events': [{'uuid': str(i)} for i in range(9)],
               'event_collection': {'complete': False, 'missing_uuids': [str(i) for i in range(9, 15)]}}
    content = json.dumps(content, indent=3) + '\n' if as_text else content
    value = {'alert_id': 17, 'alert_source_content': content,
             'alert_context': {'unknown': ['retained', None]},
             'iocs': [{'type': 'hash', 'value': 'synthetic'}], 'assets': [{'name': 'test'}]}
    result = source.normalize_source(value)
    assert source.reconstruct_source(result) == value
    assert result['coverage']['available_events'] == 9
    assert len(result['coverage']['missing_events']) == 6
    assert result['coverage']['source_complete'] is False


@pytest.mark.parametrize('value', [' { "events": [] }\n', '', [True, None, 1, 'x'], {'a/b~': {'$ref': 1}}])
def test_arbitrary_json_values_and_original_strings_roundtrip(source, value):
    assert source.reconstruct_source(source.normalize_source(value)) == value


def test_malformed_or_undeclared_sources_do_not_claim_complete_collection(source):
    result = source.normalize_source('{broken JSON')
    assert source.reconstruct_source(result) == '{broken JSON'
    assert result['coverage']['normalization_complete'] is False
    assert result['coverage']['source_complete'] is False
    assert source.normalize_source({'events': [{'uuid': 'one'}]})['coverage']['source_complete'] is False


def test_duplicate_json_keys_remain_raw_evidence_instead_of_silently_losing_a_field(source):
    value = '{"events":[{"uuid":"one"}],"events":[{"uuid":"two"}],"event_collection":{"complete":true}}'
    normalized = source.normalize_source(value)
    assert source.reconstruct_source(normalized) == value
    assert normalized['coverage']['normalization_complete'] is False
    assert normalized['coverage']['source_complete'] is False
