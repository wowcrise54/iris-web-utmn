from ast import Module, parse
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


def test_bulk_relation_change_rejects_stale_edges_without_partial_write():
    path = (Path(__file__).resolve().parents[2]
            / 'source/app/datamgmt/case/investigation_graph_db.py')
    definition = next(node for node in parse(path.read_text(encoding='utf-8')).body
                      if getattr(node, 'name', '') == 'update_graph_edge_relations')
    old = SimpleNamespace(name='related_to')
    new = SimpleNamespace(name='connected_to')
    edges = [SimpleNamespace(edge_id=1, relation_type=old),
             SimpleNamespace(edge_id=2, relation_type=old)]
    case_model, edge_model, relation_model, db = (Mock() for _ in range(4))
    edge_model.query.filter.return_value.all.return_value = edges
    relation_model.query.filter.return_value.all.return_value = [new]
    scope = dict(Cases=case_model, CaseGraphEdge=edge_model, CaseGraphRelationType=relation_model, db=db)
    exec(compile(Module(body=[definition], type_ignores=[]), str(path), 'exec'), scope)
    update = scope[definition.name]
    changes = [{'id': 1, 'expected': 'related_to', 'relation': 'connected_to'},
               {'id': 2, 'expected': 'same_as', 'relation': 'connected_to'}]

    with pytest.raises(ValueError, match='connections changed'):
        update(9, changes)

    assert all(edge.relation_type is old for edge in edges)
    db.session.commit.assert_not_called()

    changes[1]['expected'] = 'related_to'
    assert update(9, changes) == {'updated': 2}
    assert all(edge.relation_type is new for edge in edges)
    db.session.commit.assert_called_once_with()
    case_model.query.filter_by.assert_called_with(case_id=9)
