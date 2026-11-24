from ast import Module, parse
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


def test_node_history_is_captured_under_lock_and_rejects_stale_restore():
    path = (Path(__file__).resolve().parents[2]
            / 'source/app/datamgmt/case/investigation_graph_db.py')
    names = {'_graph_edit_state', 'write_graph_item'}
    functions = [node for node in parse(path.read_text(encoding='utf-8')).body
                 if getattr(node, 'name', '') in names]
    cases = Mock()
    node_model = Mock()
    db = Mock()
    item = SimpleNamespace(label='Before', description=None)
    node_model.query.filter.return_value.first.return_value = item
    scope = dict(
        Cases=cases, GRAPH_ITEMS={'nodes': node_model}, GRAPH_ITEM_IDS={'nodes': Mock()}, db=db,
        serialize_graph_item=lambda item: {'id': 3, 'label': item.label, 'description': item.description},
    )
    exec(compile(Module(body=functions, type_ignores=[]), str(path), 'exec'), scope)
    write = scope['write_graph_item']
    before = {'label': 'Before', 'description': ''}
    after = {'label': 'After', 'description': 'New note'}

    result = write(9, 'nodes', 3, after.copy())
    assert result['history'] == {'before': before, 'after': after}
    cases.query.filter_by.return_value.with_for_update.assert_called()
    assert write(9, 'nodes', 3, before.copy(), expected=after)['history']['after'] == before
    assert write(9, 'nodes', 3, after.copy(), expected=before)['history']['after'] == after

    item.description = 'Concurrent edit'
    with pytest.raises(ValueError, match='graph item changed'):
        write(9, 'nodes', 3, before.copy(), expected=after)

    assert item.description == 'Concurrent edit'
    assert db.session.commit.call_count == 3

def test_lifecycle_history_keeps_attached_edges_and_rejects_extra_connections():
    source = (Path(__file__).resolve().parents[2]
              / 'source/app/datamgmt/case/investigation_graph_db.py')
    definition = next(node for node in parse(source.read_text(encoding='utf-8')).body
                      if getattr(node, 'name', '') == 'apply_graph_lifecycle')
    db, cases, model, attached, restore = (Mock() for _ in range(5))
    node = SimpleNamespace(node_id=3)
    model.query.filter.return_value.first.return_value = node
    captured = {'row': {'node_id': 3}, 'edges': [{'edge_id': 7, 'event_ids': [9]}]}
    snapshot = Mock(return_value=captured)
    scope = dict(
        Cases=cases, GRAPH_ITEMS={'nodes': model}, GRAPH_ITEM_IDS={'nodes': Mock()},
        _LIFECYCLE_COLUMNS={'nodes': ('node_id',)}, _restore_graph_row=restore,
        _graph_lifecycle_snapshot=snapshot, _attached_edges=attached, db=db,
    )
    exec(compile(Module(body=[definition], type_ignores=[]), str(source), 'exec'), scope)
    apply = scope[definition.name]
    assert apply(11, 'nodes', captured, 'restore')
    assert [invocation.args for invocation in restore.call_args_list] == [
        (11, 'nodes', captured['row']), (11, 'edges', captured['edges'][0]),
    ]
    assert apply(11, 'nodes', captured, 'remove')
    attached.assert_called_once_with(11, 3)
    db.session.delete.assert_called_once_with(node)

    snapshot.return_value = {**captured, 'edges': [*captured['edges'], {'edge_id': 8}]}
    with pytest.raises(ValueError, match='connections changed'):
        apply(11, 'nodes', captured, 'remove')
    assert db.session.commit.call_count == 2
    assert db.session.delete.call_count == 1
