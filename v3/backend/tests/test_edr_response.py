from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'source'))
from iris_maxpatrol_module.edr import EdrClient, event_target


ASSET = 'd6a044ca-e05e-46e2-b3be-8afad6c3ec86'
AGENT = 'a' * 32
SERVICE = 'b' * 32
PATH = r'C:\Temp\sample.exe'
EVENT = {'event_src.asset': ASSET, 'asset_ids': [ASSET], 'object.fullpath': PATH}
ACTION = {'module': 'file_remover', 'action': 'fr_remove_object_file', 'fields': ['object.fullpath']}


@pytest.mark.parametrize('event', [
    {**EVENT, 'asset_ids': []},
    {**EVENT, 'object.fullpath': 'relative.exe'},
    {**EVENT, 'object.fullpath': r'\REGISTRY\MACHINE\SOFTWARE\Test'},
])
def test_unmapped_or_relative_target_is_not_actionable(event):
    assert event_target(event) is None


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
        target = client.discover(EVENT)
        assert target.hostname == 'endpoint'
        assert target.path == PATH
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
        assert client.discover(EVENT) is None
    finally:
        client.close()
