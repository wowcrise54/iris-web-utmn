from marshmallow import Schema, ValidationError, fields
from marshmallow.validate import Length, Range

from app.blueprints.access_controls import (
    ac_api_requires,
    ac_api_return_access_denied,
    ac_fast_check_current_user_has_case_access,
)
from app.blueprints.rest.api_doc import api_doc
from app.blueprints.rest.endpoints import (
    response_api_created,
    response_api_error,
    response_api_not_found,
    response_api_success,
)
from app.business.cases import cases_exists
from app.datamgmt.case.investigation_graph_db import read_investigation_graph, write_graph_item
from app.db import db
from app.models.authorization import CaseAccessLevel
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
    directed = fields.Boolean(required=True)
    event_ids = fields.List(
        fields.Integer(strict=True, validate=Range(min=1, max=2**63 - 1)),
        load_default=list, validate=Length(max=500),
    )


class GraphPositionSchema(Schema):
    x = fields.Float(required=True, validate=Range(min=-1e8, max=1e8))
    y = fields.Float(required=True, validate=Range(min=-1e8, max=1e8))


class GraphViewStateSchema(Schema):
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
    return response_api_success(read_investigation_graph(case_identifier))


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
