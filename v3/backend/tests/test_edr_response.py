from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'source'))
from iris_maxpatrol_module.edr import EdrClient, event_asset, valid_file_path, summarize_events, catalog_targets
from iris_maxpatrol_module.edr import execution_enabled


ASSET = 'd6a044ca-e05e-46e2-b3be-8afad6c3ec86'
AGENT = 'a' * 32
SERVICE = 'b' * 32
PATH = r'C:\Temp\sample.exe'
EVENT = {'event_src.asset': ASSET, 'asset_ids': [ASSET], 'object.fullpath': PATH}
ACTION = {'module': 'file_remover', 'action': 'fr_remove_object_file', 'fields': ['object.fullpath']}


def test_edr_module_setting_overrides_legacy_environment(monkeypatch):
    monkeypatch.delenv('IRIS_EDR_RESPONSE_ENABLED', raising=False)
    parameter = {'param_name': 'edr_response_enabled', 'default': False}
    assert not execution_enabled([parameter])
    assert execution_enabled([{**parameter, 'value': True}])
    monkeypatch.setenv('IRIS_EDR_RESPONSE_ENABLED', 'true')
    assert execution_enabled([])
    assert execution_enabled([parameter])
    assert not execution_enabled([{**parameter, 'value': False}])


def test_catalog_offers_host_and_process_actions_without_a_file_path():
    event = {'event_src.asset': ASSET, 'asset_ids': [ASSET], 'subject.process.id': 123}
    catalog = [
        ACTION,
        {'module': 'host_isolator', 'action': 'example_isolate', 'fields': []},
        {'module': 'proc_terminator', 'action': 'example_terminate', 'fields': ['subject.process.id']},
        {'module': 'proc_terminator', 'action': '../unsafe', 'fields': []},
    ]
    targets = catalog_targets(catalog, event, AGENT, SERVICE, 'endpoint')
    assert [(target.action, target.parameters) for target in targets] == [
        ('example_isolate', {}), ('example_terminate', {'subject.process.id': 123}),
    ]
    rows, _ = summarize_events([(7, 'Alert', [{**event, 'uuid': ASSET}])])
    assert rows[0]['asset'] == ASSET


def test_execute_sends_only_the_selected_catalog_action(monkeypatch):
    event = {'dst.ip': '192.0.2.10'}
    target, = catalog_targets([
        {'module': 'ip_blocker', 'action': 'example_block', 'fields': ['dst.ip']},
    ], event, AGENT, SERVICE, 'endpoint')

    def request(method, path, **kwargs):
        assert method == 'POST'
        assert path == f'/app/mpx/api/edr/v1/agents/{AGENT}/modules/ip_blocker/actions/example_block'
        assert kwargs['body'] == {'data': event}
        return {'status': 'success', 'data': {'status': 'success'}}, 200

    client = EdrClient(None)
    monkeypatch.setattr(client, '_request', request)
    try:
        assert client.execute(target) == {'status': 'success', 'reason': ''}
    finally:
        client.close()


def test_listing_counts_saved_events_even_when_they_cannot_be_used_for_removal():
    uid = 'd6a044ca-e05e-46e2-b3be-8afad6c3ec87'
    row = {**EVENT, 'uuid': uid, 'time': '2026-11-16T05:36:48Z', 'text': 'Process started',
           'event_src.host': 'endpoint', 'subject.process.name': 'sample.exe', 'body': 'raw data'}
    events, counts = summarize_events([
        (7, 'Alert', [row, {'uuid': uid}, EVENT]),
        (8, 'Empty alert', None),
    ])
    assert counts == {'matched_alerts': 2, 'saved_events': 3}
    assert events == [{
        'alert_id': 7, 'alert_title': 'Alert', 'event_id': uid, 'asset': ASSET,
        'time': row['time'], 'host': 'endpoint', 'text': 'Process started',
        'details': {'subject.process.name': 'sample.exe', 'object.fullpath': PATH},
    }]


def test_unmapped_event_is_not_actionable():
    assert event_asset({**EVENT, 'asset_ids': []}) is None


@pytest.mark.parametrize('path', ['relative.exe', r'\REGISTRY\MACHINE\SOFTWARE\Test'])
def test_non_file_paths_are_rejected(path):
    assert not valid_file_path(path)


def test_discover_and_execute_the_har_action(monkeypatch):
    requests = []
    responses = iter([
        {'token': 'pdql'},
        {'records': [{'xdrAgentsIds': {'data': [AGENT], 'totalCount': 1}}]},
        {'status': 'success', 'data': {
            'agent': {'hash': AGENT, 'status': 'connected', 'auth_status': 'authorized',
                      'info': {'net': {'hostname': 'endpoint'}}},
            'service': {'hash': SERVICE},
        }},
        {'status': 'success', 'data': {'actions': [ACTION]}},
        {'status': 'success', 'data': {'status': 'failure', 'reason': 'No such file or directory'}},
    ])
    client = EdrClient(None)

    def request(method, path, **kwargs):
        requests.append((method, path, kwargs))
        return next(responses), 200

    monkeypatch.setattr(client, '_request', request)
    try:
        target, = client.discover(EVENT)
        assert target.hostname == 'endpoint'
        assert target.parameters == {'object.fullpath': PATH}
        assert client.execute(target) == {'status': 'failure', 'reason': 'No such file or directory'}
    finally:
        client.close()

    assert requests[0][2]['body']['additionalFilterParameters'] == {'assetIds': [ASSET]}
    assert requests[3][2]['params']['service_hash'] == SERVICE
    assert requests[4] == (
        'POST', f'/app/mpx/api/edr/v1/agents/{AGENT}/modules/file_remover/actions/fr_remove_object_file',
        {'params': {'lang': 'ru', 'service_hash': SERVICE}, 'body': {'data': {'object.fullpath': PATH}}},
    )


def test_multiple_agent_mappings_never_reach_discovery(monkeypatch):
    responses = iter([
        {'token': 'pdql'},
        {'records': [{'xdrAgentsIds': {'data': [AGENT, 'c' * 32], 'totalCount': 2}}]},
    ])
    client = EdrClient(None)
    monkeypatch.setattr(client, '_request', lambda *_args, **_kwargs: (next(responses), 200))
    try:
        assert client.discover(EVENT) == []
    finally:
        client.close()
