from collections import defaultdict
from collections.abc import Iterable, Mapping
from itertools import combinations, product


EVENT_RELATIONS = {
    'lateral movement': 'lateral_movement',
    'exfiltration': 'exfiltrated_to',
    'command and control': 'beacons_to',
    'execution': 'executed_on',
}
MANUAL_EDGE_RELATIONS = (
    'related_to', 'connected_to', 'authenticated_to', 'lateral_movement', 'executed_on',
    'dropped', 'downloaded_from', 'resolves_to', 'beacons_to', 'exfiltrated_to',
    'owns_account', 'same_as',
)


def derive_event_edges(
    events: Iterable[tuple[int, Iterable[tuple[str, str]]]],
    categories: Mapping[int, str],
) -> dict[tuple[str, str, bool, str], set[int]]:
    """Group case-local links by direction and relation, keeping all supporting events."""
    edges: dict[tuple[str, str, bool, str], set[int]] = defaultdict(set)
    for event_id, entities in events:
        roles = dict(entities)
        sources = [key for key, role in roles.items() if role == 'source']
        targets = [key for key, role in roles.items() if role == 'target']

        if sources and targets:
            category = categories.get(event_id, '').casefold()
            relation = next(
                (kind for name, kind in EVENT_RELATIONS.items() if name in category),
                'connected_to',
            )
            for source, target in product(sources, targets):
                edges[source, target, True, relation].add(event_id)
            involved = [key for key, role in roles.items() if role == 'involved']
            undirected = product(involved, sources + targets)
        else:
            has_asset = any(key.startswith('asset:') for key in roles)
            undirected = (
                (left, right) for left, right in combinations(roles, 2)
                if not (has_asset and left.startswith('ioc:') and right.startswith('ioc:'))
            )

        for left, right in undirected:
            first, second = sorted((left, right))
            edges[first, second, False, 'co_occurs'].add(event_id)

    return dict(edges)


def project_graph_events(events, event_roles):
    rows = list(events)
    event_ids = {identifier for identifier, *_ in rows}
    nodes, edges = [], []
    for identifier, title, date, parent_id in rows:
        key = f'event:{identifier}'
        nodes.append({
            'key': key, 'kind': 'event', 'id': identifier,
            'label': title or str(identifier), 'subtitle': date.isoformat() if date else None,
        })
        if parent_id in event_ids:
            edges.append({
                'key': f'parent:{identifier}', 'source': f'event:{parent_id}', 'target': key,
                'directed': True, 'event_ids': [parent_id, identifier], 'origin': 'parent_event',
            })
        for entity, role in event_roles.get(identifier, ()):
            source, target = (key, entity) if role == 'target' else (entity, key)
            edges.append({
                'key': f'involved:{identifier}:{entity}', 'source': source, 'target': target,
                'directed': True, 'event_ids': [identifier], 'origin': 'event',
            })
    return nodes, edges


def resolve_event_roles(entity_ids, requested_roles, previous_roles):
    """Keep roles on legacy updates and default newly linked entities to involved."""
    roles = previous_roles if requested_roles is None else requested_roles
    return {int(entity_id): roles.get(int(entity_id), 'involved') for entity_id in entity_ids}


def validate_edge_endpoints(source, target, case_node_keys):
    if source == target:
        raise ValueError('Choose two different graph nodes')
    if source not in case_node_keys or target not in case_node_keys:
        raise ValueError('Both graph nodes must belong to this case')
