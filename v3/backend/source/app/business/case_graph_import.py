"""Apply a beta.23 graph exchange plan within a single case transaction."""

from datetime import datetime, timezone

from app.business.case_graph_exchange import case_graph_exchange_parse_json, case_graph_exchange_parse_stix
from app.business.ioc_type_detect import ioc_type_detect_pick
from app.db import db
from app.models.assets import CaseAssets
from app.models.case_graph import CASE_GRAPH_NODE_TYPES, CaseGraphEdge, CaseGraphNode, CaseGraphRelationType
from app.models.cases import Cases
from app.models.errors import BusinessProcessingError, ObjectNotFoundError
from app.models.iocs import Ioc, Tlp
from app.models.models import IocType


def _text(value, limit):
    return value.replace('\0', '')[:limit] if isinstance(value, str) else None


def _edge_identity(source, target, relation_id, directed):
    endpoints = (source, target) if directed else tuple(sorted((source, target)))
    return endpoints, relation_id, directed


def _timestamp(value):
    try:
        timestamp = datetime.fromisoformat(value)
        if timestamp.tzinfo is not None:
            timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)
        return timestamp
    except (TypeError, ValueError, OverflowError):
        return None


def import_case_graph(case_id, user_id, payload):
    parsers = {'json': case_graph_exchange_parse_json, 'stix': case_graph_exchange_parse_stix}
    file_format = payload.get('format')
    if not isinstance(file_format, str) or file_format not in parsers:
        raise BusinessProcessingError('format must be json or stix')
    plan = parsers[file_format](payload.get('content'))
    if Cases.query.filter_by(case_id=case_id).with_for_update().first() is None:
        raise ObjectNotFoundError()

    refs, skipped = {}, list(plan['skipped'])
    nodes_created = edges_created = 0
    assets = {}
    for row in CaseAssets.query.filter_by(case_id=case_id).order_by(CaseAssets.asset_id):
        assets.setdefault((row.asset_name or '').strip().lower(), row.asset_id)
    nodes = {((row.label or '').strip().lower(), row.node_type): row
             for row in CaseGraphNode.query.filter_by(case_id=case_id)}
    iocs = {(row.ioc_value or '').strip().lower(): row for row in Ioc.query.filter_by(case_id=case_id)}
    types = [{'type_name': row.type_name, 'type_id': row.type_id} for row in IocType.query]
    types_by_name = {row['type_name'].lower(): row for row in types if row['type_name']}
    tlp = Tlp.query.filter_by(tlp_name='amber').first()

    new_nodes = []
    for item in plan['assets'] + plan['nodes']:
        ref = item['ref']
        label = (_text(item['label'], 200) or '').strip()
        if not label:
            skipped.append(ref)
            continue
        if 'node_type' not in item and label.lower() in assets:
            refs[ref] = ('asset', assets[label.lower()])
            continue
        kind = item.get('node_type', 'infrastructure')
        if kind not in CASE_GRAPH_NODE_TYPES:
            kind = 'other'
        key = (label.lower(), kind)
        if key not in nodes:
            nodes[key] = CaseGraphNode(case_id=case_id, created_by_id=user_id, label=label,
                                       node_type=kind, description=_text(item.get('description'), 10000))
            db.session.add(nodes[key])
            nodes_created += 1
        new_nodes.append((ref, nodes[key]))

    imported_iocs = []
    for item in plan['iocs']:
        ref = item['ref']
        value = (_text(item['value'], 4096) or '').strip()
        hint = item.get('type_hint')
        if not value:
            skipped.append(ref)
            continue
        key = value.lower()
        if key not in iocs:
            ioc_type = types_by_name.get(hint.lower()) if isinstance(hint, str) else None
            ioc_type = ioc_type or ioc_type_detect_pick(value, types)
            if not ioc_type:
                skipped.append(ref)
                continue
            iocs[key] = Ioc(case_id=case_id, user_id=user_id, ioc_value=value,
                            ioc_type_id=ioc_type['type_id'], ioc_tlp_id=tlp.tlp_id if tlp else None,
                            ioc_description=_text(item.get('description'), 10000))
            db.session.add(iocs[key])
            nodes_created += 1
        imported_iocs.append((ref, iocs[key]))
    db.session.flush()
    refs.update((ref, ('node', node.node_id)) for ref, node in new_nodes)
    refs.update((ref, ('ioc', ioc.ioc_id)) for ref, ioc in imported_iocs)

    relations = CaseGraphRelationType.query.order_by(CaseGraphRelationType.sort_order, CaseGraphRelationType.id).all()
    by_name = {relation.name: relation for relation in relations}
    by_stix = {}
    for relation in relations:
        by_stix.setdefault(relation.stix_relationship, relation)
    identities = {
        _edge_identity((edge.source_kind, edge.source_id), (edge.target_kind, edge.target_id),
                       edge.relation_type_id, edge.directed)
        for edge in CaseGraphEdge.query.filter_by(case_id=case_id)
    }
    for item in plan['edges']:
        source, target = (refs.get(item.get(key)) if isinstance(item.get(key), str) else None
                          for key in ('source_ref', 'target_ref'))
        name, stix = item.get('relation'), item.get('stix_relationship')
        relation = (by_name.get(name) if isinstance(name, str) else None)
        relation = relation or (by_stix.get(stix) if isinstance(stix, str) else None) or by_name.get('related_to')
        if source is None or target is None or source == target or relation is None:
            skipped.append(item.get('ref'))
            continue
        directed = item.get('directed')
        directed = directed if isinstance(directed, bool) else relation.directed
        identity = _edge_identity(source, target, relation.id, directed)
        if identity in identities:
            skipped.append(item.get('ref'))
            continue
        confidence = item.get('confidence')
        if type(confidence) is not int or not 0 <= confidence <= 100:
            confidence = None
        db.session.add(CaseGraphEdge(
            case_id=case_id, created_by_id=user_id, origin='import', directed=directed,
            source_kind=source[0], source_id=source[1], target_kind=target[0], target_id=target[1],
            relation_type_id=relation.id, label=_text(item.get('label'), 200),
            description=_text(item.get('description'), 10000),
            confidence=confidence, first_seen=_timestamp(item.get('first_seen')),
            last_seen=_timestamp(item.get('last_seen')),
        ))
        identities.add(identity)
        edges_created += 1
    db.session.commit()
    return {'nodes_created': nodes_created, 'edges_created': edges_created,
            'skipped': len(skipped), 'skipped_details': [str(item)[:200] for item in skipped[:200]]}
