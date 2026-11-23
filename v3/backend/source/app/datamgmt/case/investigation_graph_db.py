from collections import defaultdict

from app.business.investigation_graph import derive_event_edges, project_graph_events, validate_edge_endpoints
from app.business.case_graph_relation_types import case_graph_relation_types_list
from app.db import db
from app.models.assets import AnalysisStatus, AssetsType, CaseAssets, CompromiseStatus
from app.models.cases import Cases, CasesEvent
from app.models.evidences import CaseReceivedFile
from app.models.iocs import Ioc
from app.models.case_graph import (
    CaseGraphEdge, CaseGraphEdgeEvent, CaseGraphNode, CaseGraphRelationType, CaseGraphView,
)
from app.models.models import CaseEventCategory, CaseEventsAssets, CaseEventsIoc, EventCategory, IocAssetLink
from app.models.models import CaseTasks, IocType, Notes


CASE_OBJECT_NODES = {
    'evidence': ('evidences', CaseReceivedFile.id, CaseReceivedFile.case_id, CaseReceivedFile.filename),
    'task': ('tasks', CaseTasks.id, CaseTasks.task_case_id, CaseTasks.task_title),
    'note': ('notes', Notes.note_id, Notes.note_case_id, Notes.note_title),
}


def read_investigation_graph(case_id, *, include_events=False, includes=()):
    assets = CaseAssets.query.with_entities(
        CaseAssets.asset_id, CaseAssets.asset_name, CaseAssets.asset_description, CaseAssets.asset_ip,
        CaseAssets.asset_compromise_status_id, AssetsType.asset_icon_compromised,
        AssetsType.asset_icon_not_compromised, AnalysisStatus.name,
    ).outerjoin(AssetsType, CaseAssets.asset_type_id == AssetsType.asset_id).outerjoin(
        AnalysisStatus, CaseAssets.analysis_status_id == AnalysisStatus.id,
    ).filter(CaseAssets.case_id == case_id).order_by(CaseAssets.asset_id)
    iocs = Ioc.query.with_entities(
        Ioc.ioc_id, Ioc.ioc_value, Ioc.ioc_description, IocType.type_name,
    ).outerjoin(IocType, IocType.type_id == Ioc.ioc_type_id).filter(Ioc.case_id == case_id).order_by(Ioc.ioc_id)

    nodes = []
    for identifier, label, description, ip_address, status, compromised_icon, default_icon, analysis in assets:
        compromised = status == CompromiseStatus.compromised.value
        icon = compromised_icon if compromised else default_icon
        nodes.append({
            'key': f'asset:{identifier}', 'kind': 'asset', 'id': identifier,
            'label': label or str(identifier), 'description': description, 'subtitle': ip_address,
            'icon': f'/static/assets/img/graph/{icon}' if icon else None,
            'compromised': compromised, 'analysis_status': analysis,
        })
    nodes.extend(
        {'key': f'ioc:{identifier}', 'kind': 'ioc', 'id': identifier,
         'label': label or str(identifier), 'description': description, 'type': type_name}
        for identifier, label, description, type_name in iocs
    )
    nodes.extend(serialize_graph_item(node) for node in CaseGraphNode.query.filter_by(
        case_id=case_id,
    ).order_by(CaseGraphNode.node_id))
    node_keys = {node['key'] for node in nodes}

    events = {}
    categories = {}
    event_roles = defaultdict(list)
    for kind, model, entity in [
        ('asset', CaseEventsAssets, CaseEventsAssets.asset_id),
        ('ioc', CaseEventsIoc, CaseEventsIoc.ioc_id),
    ]:
        rows = model.query.with_entities(
            model.event_id, entity, model.role, CasesEvent.event_title, CasesEvent.event_date, EventCategory.name,
        ).join(CasesEvent, CasesEvent.event_id == model.event_id).outerjoin(
            CaseEventCategory, CaseEventCategory.event_id == CasesEvent.event_id,
        ).outerjoin(EventCategory, EventCategory.id == CaseEventCategory.category_id).filter(
            model.case_id == case_id,
            CasesEvent.case_id == case_id,
            CasesEvent.event_in_graph.is_not(False),
        )
        for event_id, identifier, role, title, date, category in rows:
            key = f'{kind}:{identifier}'
            if key in node_keys:
                event_roles[event_id].append((key, role))
                if category:
                    categories[event_id] = category
                events[event_id] = {
                    'id': event_id, 'title': title, 'date': date.isoformat() if date else None,
                }

    event_counts = defaultdict(int)
    for roles in event_roles.values():
        for key in {key for key, _ in roles}:
            event_counts[key] += 1
    for node in nodes:
        node['event_count'] = event_counts[node['key']]

    edges = [
        {
            'key': f'd:{source}:{target}:{int(directed)}:{relation}',
            'source': source, 'target': target, 'directed': directed,
            'event_ids': sorted(event_ids), 'origin': 'event', 'relation': relation,
        }
        for (source, target, directed, relation), event_ids in sorted(
            derive_event_edges(event_roles.items(), categories).items(),
        )
    ]
    if include_events:
        event_rows = list(CasesEvent.query.with_entities(
            CasesEvent.event_id, CasesEvent.event_title, CasesEvent.event_date, CasesEvent.parent_event_id,
        ).filter(
            CasesEvent.case_id == case_id, CasesEvent.event_in_graph.is_not(False),
        ).order_by(CasesEvent.event_id))
        event_nodes, event_edges = project_graph_events(event_rows, event_roles)
        nodes.extend(event_nodes)
        edges.extend(event_edges)
        events.update({
            identifier: {'id': identifier, 'title': title, 'date': date.isoformat() if date else None}
            for identifier, title, date, _ in event_rows
        })

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
    stored_edges = CaseGraphEdge.query.filter_by(case_id=case_id, review_state='accepted').all()
    referenced = defaultdict(set)
    for edge in stored_edges:
        referenced[edge.source_kind].add(edge.source_id)
        referenced[edge.target_kind].add(edge.target_id)
    for kind, (include, identifier, owner, title) in CASE_OBJECT_NODES.items():
        query = identifier.class_.query.with_entities(identifier, title).filter(owner == case_id)
        if include not in includes:
            if not referenced[kind]:
                continue
            query = query.filter(identifier.in_(referenced[kind]))
        for object_id, label in query.order_by(identifier):
            key = f'{kind}:{object_id}'
            nodes.append({'key': key, 'kind': kind, 'id': object_id, 'label': label or str(object_id)})
            node_keys.add(key)
    manual_edges = [
        edge for edge in stored_edges
        if f'{edge.source_kind}:{edge.source_id}' in node_keys
        and f'{edge.target_kind}:{edge.target_id}' in node_keys
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

    views = CaseGraphView.query.filter_by(case_id=case_id).order_by(CaseGraphView.view_id)
    return {
        'nodes': nodes, 'edges': edges, 'events': [events[key] for key in sorted(events)],
        'views': [serialize_graph_item(view) for view in views],
        'relation_types': case_graph_relation_types_list(),
    }


GRAPH_ITEMS = {
    'nodes': CaseGraphNode,
    'edges': CaseGraphEdge,
    'views': CaseGraphView,
}
GRAPH_ITEM_IDS = {
    'nodes': CaseGraphNode.node_id, 'edges': CaseGraphEdge.edge_id, 'views': CaseGraphView.view_id,
}
NODE_IDENTIFIERS = {
    'asset': (CaseAssets.asset_id, CaseAssets.case_id),
    'ioc': (Ioc.ioc_id, Ioc.case_id),
    'node': (CaseGraphNode.node_id, CaseGraphNode.case_id),
    **{kind: (identifier, owner) for kind, (_, identifier, owner, _) in CASE_OBJECT_NODES.items()},
}


def serialize_graph_item(item):
    if isinstance(item, CaseGraphNode):
        identifier = item.node_id
        return {
            'id': identifier, 'key': f'node:{identifier}', 'kind': 'node',
            'label': item.label, 'description': item.description, 'type': item.node_type,
        }
    if isinstance(item, CaseGraphEdge):
        return {
            'id': item.edge_id, 'key': f'e:{item.edge_id}', 'origin': item.origin, 'editable': True,
            'label': item.label, 'relation': item.relation_type.name,
            'description': item.description, 'confidence': item.confidence,
            'first_seen': item.first_seen.isoformat() if item.first_seen else None,
            'last_seen': item.last_seen.isoformat() if item.last_seen else None,
            'source': f'{item.source_kind}:{item.source_id}',
            'target': f'{item.target_kind}:{item.target_id}',
            'directed': item.directed, 'event_ids': sorted(link.event_id for link in item.evidence),
        }
    return {'id': item.view_id, 'label': item.name, 'state': item.state}


def _case_endpoint_keys(case_id, keys):
    valid = set()
    for key in keys:
        kind, _, identifier = key.partition(':')
        columns = NODE_IDENTIFIERS.get(kind)
        if columns is None or not identifier.isascii() or not identifier.isdecimal():
            continue
        column, owner = columns
        number = int(identifier)
        if not 0 < number <= 2**63 - 1 or key != f'{kind}:{number}':
            continue
        if column is CaseGraphNode.node_id and number > 2**31 - 1:
            continue
        model = column.class_
        if model.query.filter(column == number, owner == case_id).first() is not None:
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
    ] if item.edge_id is not None else []
    current_ids = {link.event_id for link in item.evidence}
    item.evidence.extend(CaseGraphEdgeEvent(event_id=event_id)
                         for event_id in sorted(requested_ids - current_ids))


def write_graph_item(case_id, resource, identifier, values):
    # Serialize edits for a case so edge creation cannot race manual node removal.
    case = Cases.query.filter_by(case_id=case_id).with_for_update().first()
    if case is None:
        return None

    model = GRAPH_ITEMS[resource]
    item = model(case_id=case_id) if identifier is None else model.query.filter(
        GRAPH_ITEM_IDS[resource] == identifier, model.case_id == case_id,
    ).first()
    if item is None:
        return None

    if values is None:
        if resource == 'nodes':
            CaseGraphEdge.query.filter(
                CaseGraphEdge.case_id == case_id,
                ((CaseGraphEdge.source_kind == 'node') & (CaseGraphEdge.source_id == identifier))
                | ((CaseGraphEdge.target_kind == 'node') & (CaseGraphEdge.target_id == identifier)),
            ).delete(synchronize_session=False)
        db.session.delete(item)
        db.session.commit()
        return {'id': identifier}

    if resource == 'edges':
        _set_manual_edge(item, values)
        for endpoint in ('source', 'target'):
            kind, identifier_text = values.pop(endpoint).split(':')
            setattr(item, endpoint + '_kind', kind)
            setattr(item, endpoint + '_id', int(identifier_text))
        if 'relation' in values or item.edge_id is None:
            name = values.pop('relation', None) or 'related_to'
            relation = CaseGraphRelationType.query.filter_by(name=name).first()
            if relation is None:
                raise ValueError('Unknown graph relation type')
            item.relation_type = relation
    if resource == 'views':
        values['name'] = values.pop('label')
    for field, value in values.items():
        setattr(item, field, value)
    db.session.add(item)
    db.session.flush()
    result = serialize_graph_item(item)
    db.session.commit()
    return result
