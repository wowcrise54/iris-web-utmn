import sys
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


MODULE = Path(__file__).resolve().parents[2] / 'source/app/business/investigation_graph.py'
derive_event_edges = run_path(str(MODULE))['derive_event_edges']


def test_manual_edge_relation_migration_preserves_existing_edges(monkeypatch):
    migration_path = MODULE.parents[1] / 'alembic/versions/utmn_graph_edge_relation01.py'
    engine = sa.create_engine('sqlite://')
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE investigation_graph_edge (id INTEGER PRIMARY KEY, label TEXT)')
        connection.exec_driver_sql("INSERT INTO investigation_graph_edge VALUES (1, 'Original label')")
        monkeypatch.setitem(sys.modules, 'app.alembic.alembic_utils', SimpleNamespace(
            _table_has_column=lambda table, name: any(
                column['name'] == name for column in sa.inspect(connection).get_columns(table)
            ),
        ))
        migration = run_path(str(migration_path))
        with Operations.context(MigrationContext.configure(connection)):
            migration['upgrade']()
            migration['upgrade']()
            assert connection.exec_driver_sql('SELECT label, relation FROM investigation_graph_edge').one() == (
                'Original label', None,
            )
            connection.exec_driver_sql("UPDATE investigation_graph_edge SET relation = 'lateral_movement'")
            migration['downgrade']()
            assert connection.exec_driver_sql('SELECT * FROM investigation_graph_edge').one() == (1, 'Original label')


def test_event_nodes_preserve_parent_direction_and_linked_entity_roles():
    project = run_path(str(MODULE))['project_graph_events']
    nodes, edges = project([
        (1, 'Parent', None, None),
        (2, 'Child', None, 1),
        (3, 'Event with unavailable parent', None, 99),
    ], {2: [('asset:4', 'source'), ('ioc:5', 'target'), ('asset:6', 'involved')],
        99: [('asset:4', 'source')]})

    assert [node['key'] for node in nodes] == ['event:1', 'event:2', 'event:3']
    assert {(edge['source'], edge['target'], tuple(edge['event_ids'])) for edge in edges} == {
        ('event:1', 'event:2', (1, 2)),
        ('asset:4', 'event:2', (2,)),
        ('event:2', 'ioc:5', (2,)),
        ('asset:6', 'event:2', (2,)),
    }
    assert all(edge['directed'] for edge in edges)


def test_preserves_direction_and_all_evidence_without_inventing_direction():
    source, target = 'asset:2', 'asset:10'
    edges = derive_event_edges([
        (1, [(source, 'source'), (target, 'target')]),
        (2, [(source, 'source'), (target, 'target')]),
        (3, [(target, 'source'), (source, 'target')]),
        (4, [(source, 'involved'), (target, 'involved')]),
    ], {})

    assert edges == {
        (source, target, True, 'connected_to'): {1, 2},
        (target, source, True, 'connected_to'): {3},
        (target, source, False, 'co_occurs'): {4},
    }


def test_directional_edges_keep_distinct_relations_between_the_same_nodes():
    source, target = 'asset:2', 'asset:10'
    roles = [(source, 'source'), (target, 'target')]
    edges = derive_event_edges(
        [(identifier, roles) for identifier in range(1, 7)]
        + [(7, [(source, 'involved'), (target, 'involved')])],
        {
            1: 'Lateral Movement', 2: 'MITRE: lateral movement', 3: 'Exfiltration',
            5: 'Command and Control', 6: 'Execution', 7: 'Execution',
        },
    )

    assert edges == {
        (source, target, True, 'lateral_movement'): {1, 2},
        (source, target, True, 'exfiltrated_to'): {3},
        (source, target, True, 'connected_to'): {4},
        (source, target, True, 'beacons_to'): {5},
        (source, target, True, 'executed_on'): {6},
        (target, source, False, 'co_occurs'): {7},
    }


def test_involved_entities_are_undirected_and_ioc_only_events_are_supported():
    source, target, witness = 'asset:2', 'asset:10', 'ioc:1'
    edges = derive_event_edges([
        (1, [(source, 'source'), (target, 'target'), (witness, 'involved')]),
        (2, [(witness, 'involved'), ('ioc:3', 'involved')]),
    ], {})

    assert edges == {
        (source, target, True, 'connected_to'): {1},
        (source, witness, False, 'co_occurs'): {1},
        (target, witness, False, 'co_occurs'): {1},
        (witness, 'ioc:3', False, 'co_occurs'): {2},
    }



def test_role_update_preserves_existing_roles_only_when_payload_omits_them():
    resolve = run_path(str(MODULE))['resolve_event_roles']
    assert resolve([1, 2, 3], None, {1: 'source', 2: 'target', 4: 'source'}) == {
        1: 'source', 2: 'target', 3: 'involved',
    }
    assert resolve([1, 2], {2: 'source'}, {1: 'source', 2: 'target'}) == {
        1: 'involved', 2: 'source',
    }


def test_manual_edge_endpoints_are_case_local_and_distinct():
    validate = run_path(str(MODULE))['validate_edge_endpoints']
    assert validate('asset:1', 'node:2', {'asset:1', 'node:2'}) is None
    for source, target in [('asset:1', 'asset:1'), ('asset:1', 'asset:3')]:
        try:
            validate(source, target, {'asset:1', 'node:2'})
        except ValueError:
            continue
        raise AssertionError(f'invalid edge accepted: {source} -> {target}')
