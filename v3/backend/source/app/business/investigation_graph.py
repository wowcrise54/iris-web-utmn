from collections import defaultdict
from collections.abc import Iterable
from itertools import combinations, product


def derive_event_edges(
    events: Iterable[tuple[int, Iterable[tuple[str, str]]]],
) -> dict[tuple[str, str, bool], set[int]]:
    """Group case-local graph links by direction and retain every supporting event."""
    edges: dict[tuple[str, str, bool], set[int]] = defaultdict(set)
    for event_id, entities in events:
        roles = dict(entities)
        sources = [key for key, role in roles.items() if role == 'source']
        targets = [key for key, role in roles.items() if role == 'target']

        if sources and targets:
            for source, target in product(sources, targets):
                edges[source, target, True].add(event_id)
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
            edges[first, second, False].add(event_id)

    return dict(edges)


def resolve_event_roles(entity_ids, requested_roles, previous_roles):
    """Keep roles on legacy updates and default newly linked entities to involved."""
    roles = previous_roles if requested_roles is None else requested_roles
    return {int(entity_id): roles.get(int(entity_id), 'involved') for entity_id in entity_ids}


def validate_edge_endpoints(source, target, case_node_keys):
    if source == target:
        raise ValueError('Choose two different graph nodes')
    if source not in case_node_keys or target not in case_node_keys:
        raise ValueError('Both graph nodes must belong to this case')
