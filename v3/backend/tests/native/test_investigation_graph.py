from pathlib import Path
from runpy import run_path


MODULE = Path(__file__).resolve().parents[2] / 'source/app/business/investigation_graph.py'
derive_event_edges = run_path(str(MODULE))['derive_event_edges']


def test_preserves_direction_and_all_evidence_without_inventing_direction():
    source, target = 'asset:2', 'asset:10'
    edges = derive_event_edges([
        (1, [(source, 'source'), (target, 'target')]),
        (2, [(source, 'source'), (target, 'target')]),
        (3, [(target, 'source'), (source, 'target')]),
        (4, [(source, 'involved'), (target, 'involved')]),
    ])

    assert edges == {
        (source, target, True): {1, 2},
        (target, source, True): {3},
        (target, source, False): {4},
    }


def test_involved_entities_are_undirected_and_ioc_only_events_are_supported():
    source, target, witness = 'asset:2', 'asset:10', 'ioc:1'
    edges = derive_event_edges([
        (1, [(source, 'source'), (target, 'target'), (witness, 'involved')]),
        (2, [(witness, 'involved'), ('ioc:3', 'involved')]),
    ])

    assert edges == {
        (source, target, True): {1},
        (source, witness, False): {1},
        (target, witness, False): {1},
        (witness, 'ioc:3', False): {2},
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
