from ast import Module, parse
from pathlib import Path
from types import SimpleNamespace


def test_graph_transfer_uses_new_ids_and_rejects_references_outside_the_bundle():
    source = (Path(__file__).resolve().parents[2]
              / 'source/app/datamgmt/case_transfer/transfer_db.py')
    names = {'make_ref', '_read_row', '_resolve_graph_references', '_remap_graph_positions'}
    functions = [node for node in parse(source.read_text(encoding='utf-8')).body
                 if getattr(node, 'name', '') in names]
    kinds = {'asset': 'asset', 'node': 'graph_node', 'event': 'event'}
    scope = {'GRAPH_ENDPOINT_ENTITIES': kinds}
    exec(compile(Module(body=functions, type_ignores=[]), str(source), 'exec'), scope)

    edge_spec = SimpleNamespace(
        key='graph_edge', pk='edge_id', blob_column=None,
        fields=('label',), user_refs=(), entity_refs={}, self_refs=(),
        lookup_refs={'relation_type_id': 'graph_relation_type'},
        required_refs=('relation_type_id',),
        poly_refs=(('source_kind', 'source_id', kinds), ('target_kind', 'target_id', kinds)),
    )
    edge = SimpleNamespace(edge_id=4, label='Link', relation_type_id=3,
                           source_kind='asset', source_id=12, target_kind='node', target_id=8)
    collector = SimpleNamespace(lookup_ids={'graph_relation_type': set()})
    payload = scope['_read_row'](edge, edge_spec, collector)
    assert payload['source_id'] == 'asset:12'
    assert payload['target_id'] == 'graph_node:8'
    assert collector.lookup_ids['graph_relation_type'] == {3}

    graph_refs = {'asset': {'asset:12': 112}, 'graph_node': {'graph_node:8': 108},
                  'graph_edge': {'graph_edge:4': 104}, 'event': {'event:1': 101}}
    global_refs = {'graph_relation_type:3': 23, 'asset:999': 999}
    imported = SimpleNamespace()
    assert scope['_resolve_graph_references'](imported, edge_spec, payload, graph_refs, global_refs)
    assert (imported.source_id, imported.target_id, imported.relation_type_id) == (112, 108, 23)
    for foreign_ref in ('asset:999', 'event:1'):
        assert not scope['_resolve_graph_references'](
            SimpleNamespace(), edge_spec, {**payload, 'source_id': foreign_ref}, graph_refs, global_refs,
        )

    evidence_spec = SimpleNamespace(required_refs=('edge_id', 'event_id'),
                                    entity_refs={'edge_id': 'graph_edge', 'event_id': 'event'}, poly_refs=())
    evidence = SimpleNamespace()
    evidence_payload = {'edge_id': 'graph_edge:4', 'event_id': 'event:1'}
    assert scope['_resolve_graph_references'](evidence, evidence_spec, evidence_payload, graph_refs, global_refs)
    assert (evidence.edge_id, evidence.event_id) == (104, 101)
    assert not scope['_resolve_graph_references'](
        evidence, evidence_spec, {**evidence_payload, 'event_id': 'asset:12'}, graph_refs, global_refs,
    )

    state = {'search': 'asset:12', 'positions': {'asset:12': [1, 2], 'node:8': [3, 4], 'asset:999': [5, 6]}}
    assert scope['_remap_graph_positions'](state, graph_refs) == {
        'search': 'asset:12', 'positions': {'asset:112': [1, 2], 'node:108': [3, 4]},
    }
