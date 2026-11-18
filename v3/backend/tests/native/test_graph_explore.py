from pathlib import Path
import logging
from runpy import run_path
from types import SimpleNamespace
import sys

import pytest


@pytest.fixture
def explore(monkeypatch):
    source = Path(__file__).resolve().parents[2] / 'source/app'
    monkeypatch.setitem(sys.modules, 'app.logger', SimpleNamespace(logger=logging.getLogger(__name__)))
    errors = run_path(str(source / 'models/errors.py'))
    monkeypatch.setitem(sys.modules, 'app.models.errors', SimpleNamespace(**errors))
    return run_path(str(source / 'business/case_graph_explore.py'))


@pytest.fixture
def graph():
    return {
        'nodes': [{'key': key} for key in ['asset:1', 'asset:2', 'ioc:3', 'node:4']],
        'edges': [
            {'key': 'e:1', 'source': 'asset:1', 'target': 'asset:2', 'directed': True},
            {'key': 'e:2', 'source': 'asset:2', 'target': 'ioc:3', 'directed': False},
            {'key': 'e:3', 'source': 'ioc:3', 'target': 'asset:1', 'directed': True},
        ],
    }


def test_paths_follow_direction_without_repeating_nodes(explore, graph):
    paths = explore['case_graph_explore_paths'](graph, 'asset:2', 'asset:1')
    assert paths == {
        'paths': [{'node_keys': ['asset:2', 'ioc:3', 'asset:1'], 'edge_keys': ['e:2', 'e:3']}],
        'shortest_length': 2,
    }
    reverse = explore['case_graph_explore_paths'](graph, 'asset:2', 'asset:1', directed=False)
    assert reverse['paths'][0] == {'node_keys': ['asset:2', 'asset:1'], 'edge_keys': ['e:1']}
    assert explore['case_graph_explore_paths'](graph, 'asset:1', 'node:4')['paths'] == []


def test_neighbours_exclude_disconnected_nodes_and_reject_invalid_requests(explore, graph):
    result = explore['case_graph_explore_neighbours'](graph, 'asset:1')
    assert {node['key'] for node in result['nodes']} == {'asset:1', 'asset:2', 'ioc:3'}
    assert len(result['edges']) == 3
    with pytest.raises(explore['BusinessProcessingError']):
        explore['case_graph_explore_neighbours'](graph, 'asset:1', hops=True)
    with pytest.raises(explore['ObjectNotFoundError']):
        explore['case_graph_explore_paths'](graph, 'asset:1', 'asset:999')
