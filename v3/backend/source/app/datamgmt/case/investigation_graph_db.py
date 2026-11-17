from collections import defaultdict

from app.business.investigation_graph import derive_event_edges, validate_edge_endpoints
from app.db import db
from app.models.assets import AssetsType, CaseAssets, CompromiseStatus
from app.models.cases import Cases, CasesEvent
from app.models.iocs import Ioc
from app.models.investigation_graph import (
    InvestigationGraphEdge,
    InvestigationGraphEvidence,
    InvestigationGraphNode,
    InvestigationGraphView,
)
from app.models.models import CaseEventsAssets, CaseEventsIoc, IocAssetLink


def read_investigation_graph(case_id):
    assets = CaseAssets.query.with_entities(
        CaseAssets.asset_id, CaseAssets.asset_name, CaseAssets.asset_description, CaseAssets.asset_ip,
        CaseAssets.asset_compromise_status_id, AssetsType.asset_icon_compromised,
        AssetsType.asset_icon_not_compromised,
    ).outerjoin(AssetsType, CaseAssets.asset_type_id == AssetsType.asset_id).filter(CaseAssets.case_id == case_id).order_by(CaseAssets.asset_id)
    iocs = Ioc.query.with_entities(
        Ioc.ioc_id, Ioc.ioc_value, Ioc.ioc_description,
    ).filter(Ioc.case_id == case_id).order_by(Ioc.ioc_id)

    nodes = []
    for identifier, label, description, ip_address, status, compromised_icon, default_icon in assets:
        icon = compromised_icon if status == CompromiseStatus.compromised.value else default_icon
        nodes.append({
            'key': f'asset:{identifier}', 'kind': 'asset', 'id': identifier,
            'label': label or str(identifier), 'description': description, 'subtitle': ip_address,
            'icon': f'/static/assets/img/graph/{icon}' if icon else None,
        })
    nodes.extend(
        {'key': f'ioc:{identifier}', 'kind': 'ioc', 'id': identifier,
         'label': label or str(identifier), 'description': description}
        for identifier, label, description in iocs
    )
    nodes.extend(serialize_graph_item(node) for node in InvestigationGraphNode.query.filter_by(
        case_id=case_id,
    ).order_by(InvestigationGraphNode.id))
    node_keys = {node['key'] for node in nodes}

    events = {}
    event_roles = defaultdict(list)
    for kind, model, entity in [
        ('asset', CaseEventsAssets, CaseEventsAssets.asset_id),
        ('ioc', CaseEventsIoc, CaseEventsIoc.ioc_id),
    ]:
        rows = model.query.with_entities(
            model.event_id, entity, model.role, CasesEvent.event_title, CasesEvent.event_date,
        ).join(CasesEvent, CasesEvent.event_id == model.event_id).filter(
            model.case_id == case_id,
            CasesEvent.case_id == case_id,
            CasesEvent.event_in_graph.is_not(False),
        )
        for event_id, identifier, role, title, date in rows:
            key = f'{kind}:{identifier}'
            if key in node_keys:
                event_roles[event_id].append((key, role))
                events[event_id] = {
                    'id': event_id, 'title': title, 'date': date.isoformat() if date else None,
                }

    edges = [
        {
            'key': f'd:{source}:{target}:{int(directed)}',
            'source': source, 'target': target, 'directed': directed,
            'event_ids': sorted(event_ids), 'origin': 'event',
        }
        for (source, target, directed), event_ids in sorted(
            derive_event_edges(event_roles.items()).items(),
        )
    ]
    links = IocAssetLink.query.with_entities(
        IocAssetLink.asset_id, IocAssetLink.ioc_id,
    ).join(CaseAssets, IocAssetLink.asset_id == CaseAssets.asset_id).join(
        Ioc, IocAssetLink.ioc_id == Ioc.ioc_id,
    ).filter(CaseAssets.case_id == case_id, Ioc.case_id == case_id).distinct()
    edges.extend({
        'key': f'ioc-link:{asset_id}:{ioc_id}', 'source': f'ioc:{ioc_id}',
        'target': f'asset:{asset_id}', 'directed': False, 'event_ids': [],
        'origin': 'ioc_asset_link',
    } for asset_id, ioc_id in links)
    manual_edges = [
        edge for edge in InvestigationGraphEdge.query.filter_by(case_id=case_id)
        if edge.source in node_keys and edge.target in node_keys
    ]
    linked_event_ids = {item.event_id for edge in manual_edges for item in edge.evidence}
    if linked_event_ids:
        for event_id, title, date in CasesEvent.query.with_entities(
            CasesEvent.event_id, CasesEvent.event_title, CasesEvent.event_date,
        ).filter(CasesEvent.case_id == case_id, CasesEvent.event_id.in_(linked_event_ids)):
            events[event_id] = {
                'id': event_id, 'title': title, 'date': date.isoformat() if date else None,
            }

    for edge in manual_edges:
        item = serialize_graph_item(edge)
        item['event_ids'] = [event_id for event_id in item['event_ids'] if event_id in events]
        edges.append(item)

    views = InvestigationGraphView.query.filter_by(case_id=case_id).order_by(InvestigationGraphView.id)
    return {
        'nodes': nodes, 'edges': edges, 'events': [events[key] for key in sorted(events)],
        'views': [serialize_graph_item(view) for view in views],
    }


GRAPH_ITEMS = {
    'nodes': InvestigationGraphNode,
    'edges': InvestigationGraphEdge,
    'views': InvestigationGraphView,
}
NODE_IDENTIFIERS = {
    'asset': CaseAssets.asset_id,
    'ioc': Ioc.ioc_id,
    'node': InvestigationGraphNode.id,
}


def serialize_graph_item(item):
    if isinstance(item, InvestigationGraphNode):
        return {
            'id': item.id, 'key': f'node:{item.id}', 'kind': 'node',
            'label': item.label, 'description': item.description,
        }
    if isinstance(item, InvestigationGraphEdge):
        return {
            'id': item.id, 'key': f'e:{item.id}', 'origin': 'manual',
            'label': item.label, 'source': item.source, 'target': item.target,
            'directed': item.directed, 'event_ids': sorted(link.event_id for link in item.evidence),
        }
    return {'id': item.id, 'label': item.label, 'state': item.state}


def _case_endpoint_keys(case_id, keys):
    valid = set()
    for key in keys:
        kind, _, identifier = key.partition(':')
        column = NODE_IDENTIFIERS.get(kind)
        if column is None or not identifier.isascii() or not identifier.isdecimal():
            continue
        number = int(identifier)
        if not 0 < number <= 2**63 - 1 or key != f'{kind}:{number}':
            continue
        if column is InvestigationGraphNode.id and number > 2**31 - 1:
            continue
        model = column.class_
        if model.query.filter(column == number, model.case_id == case_id).first() is not None:
            valid.add(key)
    return valid


def _set_manual_edge(item, values):
    source, target = values['source'], values['target']
    validate_edge_endpoints(source, target, _case_endpoint_keys(item.case_id, {source, target}))

    requested_ids = set(values.pop('event_ids'))
    if requested_ids:
        valid_ids = {
            row.event_id for row in CasesEvent.query.with_entities(CasesEvent.event_id).filter(
                CasesEvent.case_id == item.case_id, CasesEvent.event_id.in_(requested_ids),
            )
        }
        if valid_ids != requested_ids:
            raise ValueError('All linked events must belong to this case')

    item.evidence = [
        link for link in item.evidence if link.event_id in requested_ids
    ] if item.id is not None else []
    current_ids = {link.event_id for link in item.evidence}
    item.evidence.extend(InvestigationGraphEvidence(event_id=event_id)
                         for event_id in sorted(requested_ids - current_ids))


def write_graph_item(case_id, resource, identifier, values):
    # Serialize edits for a case so edge creation cannot race manual node removal.
    case = Cases.query.filter_by(case_id=case_id).with_for_update().first()
    if case is None:
        return None

    model = GRAPH_ITEMS[resource]
    item = model(case_id=case_id) if identifier is None else model.query.filter_by(
        id=identifier, case_id=case_id,
    ).first()
    if item is None:
        return None

    if values is None:
        if resource == 'nodes':
            key = f'node:{identifier}'
            InvestigationGraphEdge.query.filter(
                InvestigationGraphEdge.case_id == case_id,
                (InvestigationGraphEdge.source == key) | (InvestigationGraphEdge.target == key),
            ).delete(synchronize_session=False)
        db.session.delete(item)
        db.session.commit()
        return {'id': identifier}

    if resource == 'edges':
        _set_manual_edge(item, values)
    for field, value in values.items():
        setattr(item, field, value)
    db.session.add(item)
    db.session.flush()
    result = serialize_graph_item(item)
    db.session.commit()
    return result
