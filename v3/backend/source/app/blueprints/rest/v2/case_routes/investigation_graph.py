from datetime import datetime, timezone

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
from app.datamgmt.case.investigation_graph_db import read_investigation_graph, write_graph_item
from app.db import db
from app.models.authorization import CaseAccessLevel
from app.models.errors import BusinessProcessingError, ObjectNotFoundError
from app.web import Blueprint, request


case_graph_blueprint = Blueprint(
    'case_graph_rest_v2', __name__, url_prefix='/<int:case_identifier>/graph',
)


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


class GraphViewSchema(Schema):
    label = _label()
    state = fields.Nested(GraphViewStateSchema, required=True)


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
    return read_investigation_graph(case_id, include_events='events' in includes, includes=includes)


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
        return response_api_success(import_case_graph(case_identifier, iris_current_user.id, body))
    except ObjectNotFoundError:
        db.session.rollback()
        return response_api_not_found()
    except BusinessProcessingError as exc:
        db.session.rollback()
        return response_api_error(exc.get_message())


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
        values = None if delete else schema.load(request.get_json())
        if values is not None:
            values['label'] = values['label'].strip()
        item = write_graph_item(case_id, resource, identifier, values)
    except ValidationError as exc:
        return response_api_error('Data error', data=exc.normalized_messages())
    except ValueError as exc:
        db.session.rollback()
        return response_api_error(str(exc))

    if item is None:
        return response_api_not_found()
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
