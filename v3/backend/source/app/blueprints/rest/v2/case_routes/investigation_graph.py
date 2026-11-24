from datetime import datetime, timezone

from itsdangerous import BadData, URLSafeTimedSerializer
from sqlalchemy.exc import IntegrityError

from marshmallow import Schema, ValidationError, fields
from marshmallow.validate import Length, OneOf, Range, Regexp

from app.blueprints.access_controls import (
    ac_api_requires,
    ac_api_return_access_denied,
    ac_fast_check_current_user_has_case_access,
)
from app.blueprints.rest.api_doc import api_doc
from app.blueprints.iris_user import iris_current_user
from app.blueprints.rest.endpoints import (
    response_api_created,
    response_api_error,
    response_api_not_found,
    response_api_success,
)
from app.business.cases import cases_exists
from app.business.case_graph_exchange import case_graph_exchange_to_graphml, case_graph_exchange_to_stix
from app.business.case_graph_import import import_case_graph
from app.business.case_graph_explore import case_graph_explore_neighbours, case_graph_explore_paths
from app.business.case_graph_gaps import case_graph_gaps_compute
from app.datamgmt.case.investigation_graph_db import (
    apply_graph_lifecycle, read_investigation_graph, record_graph_edge_event,
    update_graph_edge_relations, write_graph_item,
)
from app.db import db
from app.models.authorization import CaseAccessLevel
from app.models.case_graph import CaseGraphView
from app.iris_engine.utils.graph_snapshot import png_snapshot_base64
from app.models.errors import BusinessProcessingError, ObjectNotFoundError
from app.web import Blueprint, current_app, request


case_graph_blueprint = Blueprint(
    'case_graph_rest_v2', __name__, url_prefix='/<int:case_identifier>/graph',
)


def _publish_change(case_id):
    from app.blueprints.socket_io_event_handlers.graph_event_handlers import publish_graph_change
    publish_graph_change(case_id, iris_current_user.name or iris_current_user.user)


def _label():
    return fields.String(required=True, validate=lambda label: _validate_label(label))


def _validate_label(label):
    if not 1 <= len(label.strip()) <= 200 or len(label) > 200:
        raise ValidationError('Enter a label of 1 to 200 characters.')


class GraphNodeSchema(Schema):
    label = _label()
    description = fields.String(load_default='', validate=Length(max=10000))


class GraphEdgeSchema(Schema):
    source = fields.String(required=True, validate=Length(min=3, max=32))
    target = fields.String(required=True, validate=Length(min=3, max=32))
    label = _label()
    relation = fields.String(allow_none=True, validate=Regexp(r'^[a-z][a-z0-9_]{1,63}$'))
    directed = fields.Boolean(required=True)
    event_ids = fields.List(
        fields.Integer(strict=True, validate=Range(min=1, max=2**63 - 1)),
        load_default=list, validate=Length(max=500),
    )


class GraphPositionSchema(Schema):
    x = fields.Float(required=True, validate=Range(min=-1e8, max=1e8))
    y = fields.Float(required=True, validate=Range(min=-1e8, max=1e8))


class GraphViewStateSchema(Schema):
    layout = fields.String(load_default='fcose', validate=OneOf(
        ('fcose', 'dagre', 'chronological', 'radial', 'grouped', 'grid'),
    ))
    positions = fields.Dict(
        keys=fields.String(validate=Length(min=3, max=32)),
        values=fields.Nested(GraphPositionSchema),
        required=True, validate=Length(max=10000),
    )
    center = fields.Nested(GraphPositionSchema, required=True)
    scale = fields.Float(required=True, validate=Range(min=0.001, max=20))
    search = fields.String(load_default='', validate=Length(max=500))
    show_assets = fields.Boolean(load_default=True)
    show_iocs = fields.Boolean(load_default=True)
    show_manual_nodes = fields.Boolean(load_default=True)
    show_events = fields.Boolean(load_default=False)
    include_objects = fields.List(fields.String(validate=OneOf(('evidences', 'tasks', 'notes'))),
                                  validate=Length(max=3), load_default=list)


def _validate_graph_snapshot(value):
    if png_snapshot_base64(value) is None:
        raise ValidationError('Upload a valid PNG snapshot up to 1.5 MB and 4096 pixels per side.')


class GraphViewSchema(Schema):
    label = _label()
    state = fields.Nested(GraphViewStateSchema, required=True)
    is_shared = fields.Boolean()
    is_report_default = fields.Boolean()
    snapshot = fields.String(allow_none=True, validate=_validate_graph_snapshot)


_SCHEMAS = {
    'nodes': GraphNodeSchema(),
    'edges': GraphEdgeSchema(),
    'views': GraphViewSchema(),
}


def _case_access_error(case_id, levels):
    if not cases_exists(case_id):
        return response_api_not_found()
    if not ac_fast_check_current_user_has_case_access(case_id, levels):
        return ac_api_return_access_denied(caseid=case_id)
    return None


@case_graph_blueprint.get('')
@ac_api_requires()
@api_doc(tags=['Case graph'], summary='Read the investigation graph')
def get_case_graph(case_identifier):
    error = _case_access_error(case_identifier, [CaseAccessLevel.read_only, CaseAccessLevel.full_access])
    if error is not None:
        return error
    return response_api_success(_read_requested_graph(case_identifier))


def _read_requested_graph(case_id):
    includes = set(request.args.get('include', '').split(','))
    return read_investigation_graph(case_id, include_events='events' in includes, includes=includes,
                                    viewer_id=iris_current_user.id)


@case_graph_blueprint.get('/gaps')
@ac_api_requires()
@api_doc(tags=['Case graph'], summary='List gaps in the investigation graph')
def get_graph_gaps(case_identifier):
    error = _case_access_error(case_identifier, [CaseAccessLevel.read_only, CaseAccessLevel.full_access])
    if error is not None:
        return error
    return response_api_success(case_graph_gaps_compute(_read_requested_graph(case_identifier)))


@case_graph_blueprint.get('/export')
@ac_api_requires()
@api_doc(tags=['Case graph'], summary='Export the investigation graph as JSON, STIX 2.1 or GraphML')
def export_case_graph(case_identifier):
    error = _case_access_error(case_identifier, [CaseAccessLevel.read_only, CaseAccessLevel.full_access])
    if error is not None:
        return error
    export_format = request.args.get('format', 'json')
    extensions = {'json': 'json', 'stix': 'stix.json', 'graphml': 'graphml'}
    if export_format not in extensions:
        return response_api_error('format must be one of json, stix, graphml')
    graph = _read_requested_graph(case_identifier)
    relations = {item['name']: item for item in graph['relation_types']}
    origins = {'parent_event': 'parent_of', 'ioc_asset_link': 'related_to', 'event': 'involved_in'}
    for edge in graph['edges']:
        name = edge.get('relation') or origins.get(edge.get('origin'))
        edge['relation'] = relations.get(name)
        edge['editable'] = edge.get('id') is not None
    timestamp = datetime.now(timezone.utc).isoformat()
    graph['meta'] = {'node_count': len(graph['nodes']), 'edge_count': len(graph['edges']),
                     'generated_at': timestamp}
    content = graph
    if export_format == 'stix':
        content = case_graph_exchange_to_stix(graph, graph['relation_types'], case_identifier, timestamp)
    elif export_format == 'graphml':
        content = case_graph_exchange_to_graphml(graph)
    return response_api_success({
        'format': export_format, 'filename': f'case-{case_identifier}-graph.{extensions[export_format]}',
        'content': content,
    })


@case_graph_blueprint.post('/import')
@ac_api_requires()
@api_doc(tags=['Case graph'], summary='Import JSON or STIX into the investigation graph')
def import_graph(case_identifier):
    error = _case_access_error(case_identifier, [CaseAccessLevel.full_access])
    if error is not None:
        return error
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return response_api_error('A JSON object is required')
    try:
        result = import_case_graph(case_identifier, iris_current_user.id, body)
    except ObjectNotFoundError:
        db.session.rollback()
        return response_api_not_found()
    except BusinessProcessingError as exc:
        db.session.rollback()
        return response_api_error(exc.get_message())

    _publish_change(case_identifier)
    return response_api_success(result)


class GraphNeighboursSchema(Schema):
    node = fields.String(required=True, validate=Length(min=3, max=32))
    hops = fields.Integer(load_default=1, validate=Range(min=1, max=3))


class GraphPathsSchema(Schema):
    source = fields.String(required=True, validate=Length(min=3, max=32))
    target = fields.String(required=True, validate=Length(min=3, max=32))
    directed = fields.Boolean(load_default=True)
    max_paths = fields.Integer(load_default=5, validate=Range(min=1, max=50))
    max_length = fields.Integer(load_default=8, validate=Range(min=1, max=12))


def _explore_graph(case_id, schema, explore):
    error = _case_access_error(case_id, [CaseAccessLevel.read_only, CaseAccessLevel.full_access])
    if error is not None:
        return error
    try:
        arguments = schema.load({
            key: request.args.get(key) for key in schema.fields if key in request.args
        })
        if 'node' in arguments:
            arguments['node_key'] = arguments.pop('node')
        graph = _read_requested_graph(case_id)
        return response_api_success(explore(graph, **arguments))
    except ValidationError as exc:
        return response_api_error('Data error', data=exc.normalized_messages())
    except ObjectNotFoundError:
        return response_api_not_found()
    except BusinessProcessingError as exc:
        return response_api_error(exc.get_message())


@case_graph_blueprint.get('/neighbours')
@ac_api_requires()
@api_doc(tags=['Case graph'], summary='Explore neighbours of a graph node')
def get_graph_neighbours(case_identifier):
    return _explore_graph(case_identifier, GraphNeighboursSchema(), case_graph_explore_neighbours)


@case_graph_blueprint.get('/paths')
@ac_api_requires()
@api_doc(tags=['Case graph'], summary='Find paths between investigation graph nodes')
def get_graph_paths(case_identifier):
    return _explore_graph(case_identifier, GraphPathsSchema(), case_graph_explore_paths)


def _write_item(case_id, resource, identifier=None, *, delete=False):
    schema = _SCHEMAS.get(resource)
    if schema is None:
        return response_api_not_found()
    error = _case_access_error(case_id, [CaseAccessLevel.full_access])
    if error is not None:
        return error
    if identifier is not None and not 0 < identifier <= 2**31 - 1:
        return response_api_not_found()

    try:
        payload = None if delete else request.get_json()
        expected = None
        if (identifier is not None and resource in ('nodes', 'edges')
                and isinstance(payload, dict) and 'expected' in payload):
            payload = dict(payload)
            expected = schema.load(payload.pop('expected'))
            if resource == 'edges':
                expected['event_ids'] = sorted(set(expected['event_ids']))
        values = None if delete else schema.load(payload)
        if values is not None and expected is None:
            values['label'] = values['label'].strip()
        item = write_graph_item(
            case_id, resource, identifier, values, user_id=iris_current_user.id, expected=expected,
        )
    except ValidationError as exc:
        return response_api_error('Data error', data=exc.normalized_messages())
    except ValueError as exc:
        db.session.rollback()
        return response_api_error(str(exc))

    if item is None:
        return response_api_not_found()
    lifecycle = item.pop('lifecycle', None)
    if lifecycle is not None:
        item['history_token'] = _history_serializer().dumps({
            'case_id': case_id, 'user_id': iris_current_user.id, 'resource': resource,
            'action': 'restore' if delete else 'remove', 'snapshot': lifecycle,
        })
    if resource in ('nodes', 'edges'):
        _publish_change(case_id)
    return response_api_created(item) if identifier is None else response_api_success(item)


@case_graph_blueprint.post('/<resource>')
@ac_api_requires()
@api_doc(tags=['Case graph'], summary='Create an investigation graph node, edge or view')
def create_item(case_identifier, resource):
    return _write_item(case_identifier, resource)


@case_graph_blueprint.put('/<resource>/<int:identifier>')
@ac_api_requires()
@api_doc(tags=['Case graph'], summary='Update an investigation graph node, edge or view')
def update_item(case_identifier, resource, identifier):
    return _write_item(case_identifier, resource, identifier)


@case_graph_blueprint.delete('/<resource>/<int:identifier>')
@ac_api_requires()
@api_doc(tags=['Case graph'], summary='Delete an investigation graph node, edge or view')
def delete_item(case_identifier, resource, identifier):
    return _write_item(case_identifier, resource, identifier, delete=True)



class GraphEdgeEventSchema(Schema):
    title = _label()
    occurred_at = fields.AwareDateTime(required=True)
    description = fields.String(load_default='', validate=Length(max=10000))


@case_graph_blueprint.post('/edges/<int:edge_id>/events')
@ac_api_requires()
@api_doc(tags=['Case graph'], summary='Record a supporting timeline event for a graph connection')
def create_edge_event(case_identifier, edge_id):
    error = _case_access_error(case_identifier, [CaseAccessLevel.full_access])
    if error is not None:
        return error
    try:
        values = GraphEdgeEventSchema().load(request.get_json())
        event = record_graph_edge_event(case_identifier, edge_id, iris_current_user.id, **values)
        if event is None:
            return response_api_not_found()
        _publish_change(case_identifier)
        return response_api_created(event)
    except ValidationError as exc:
        return response_api_error('Data error', data=exc.normalized_messages())
    except ValueError as exc:
        db.session.rollback()
        return response_api_error(str(exc))



class GraphRelationChangeSchema(Schema):
    id = fields.Integer(required=True, strict=True, validate=Range(min=1, max=2**31 - 1))
    expected = fields.String(required=True, validate=Regexp(r'^[a-z][a-z0-9_]{1,63}$'))
    relation = fields.String(required=True, validate=Regexp(r'^[a-z][a-z0-9_]{1,63}$'))


class GraphRelationBatchSchema(Schema):
    changes = fields.List(fields.Nested(GraphRelationChangeSchema), required=True, validate=Length(min=1, max=100))


@case_graph_blueprint.post('/edges/relations')
@ac_api_requires()
@api_doc(tags=['Case graph'], summary='Update types of selected graph connections atomically')
def update_edge_relations(case_identifier):
    error = _case_access_error(case_identifier, [CaseAccessLevel.full_access])
    if error is not None:
        return error
    try:
        values = GraphRelationBatchSchema().load(request.get_json())
        result = update_graph_edge_relations(case_identifier, values['changes'])
    except ValidationError as exc:
        return response_api_error('Data error', data=exc.normalized_messages())
    except ValueError as exc:
        db.session.rollback()
        return response_api_error(str(exc))
    if result is None:
        return response_api_not_found()
    _publish_change(case_identifier)
    return response_api_success(result)



def _history_serializer():
    return URLSafeTimedSerializer(current_app.secret_key, salt='case-graph-lifecycle')


@case_graph_blueprint.post('/history/apply')
@ac_api_requires()
@api_doc(tags=['Case graph'], summary='Undo or redo graph node and connection creation and deletion')
def apply_lifecycle_history(case_identifier):
    error = _case_access_error(case_identifier, [CaseAccessLevel.full_access])
    if error is not None:
        return error
    body = request.get_json(silent=True)
    token = body.get('token') if isinstance(body, dict) else None
    if not isinstance(token, str):
        return response_api_error('A graph history token is required')
    try:
        data = _history_serializer().loads(token, max_age=86400)
    except BadData:
        return response_api_error('This graph history action is invalid or expired')
    if data['case_id'] != case_identifier or data['user_id'] != iris_current_user.id:
        return response_api_not_found()

    try:
        applied = apply_graph_lifecycle(case_identifier, data['resource'], data['snapshot'], data['action'])
    except ValueError as exc:
        db.session.rollback()
        return response_api_error(str(exc))
    except IntegrityError:
        db.session.rollback()
        return response_api_error('A referenced object has changed or is no longer available')
    if not applied:
        return response_api_not_found()
    data['action'] = 'remove' if data['action'] == 'restore' else 'restore'
    _publish_change(case_identifier)
    return response_api_success({'history_token': _history_serializer().dumps(data)})


@case_graph_blueprint.get('/views/<int:view_id>/snapshot')
@ac_api_requires()
@api_doc(tags=['Case graph'], summary='Read a saved graph PNG snapshot')
def get_view_snapshot(case_identifier, view_id):
    error = _case_access_error(case_identifier, [CaseAccessLevel.read_only, CaseAccessLevel.full_access])
    if error is not None:
        return error
    view = CaseGraphView.query.filter_by(case_id=case_identifier, view_id=view_id).first()
    if (view is None or png_snapshot_base64(view.snapshot) is None
            or (not view.is_shared and view.owner_id not in (None, iris_current_user.id))):
        return response_api_not_found()
    return response_api_success({'snapshot': view.snapshot})
