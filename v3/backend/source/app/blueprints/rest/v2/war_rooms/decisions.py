from pydantic import ValidationError

from app.blueprints.access_controls import ac_api_requires
from app.blueprints.iris_user import iris_current_user
from app.blueprints.rest.api_doc import api_doc
from app.blueprints.rest.endpoints import (
    response_api_created, response_api_error, response_api_not_found, response_api_success,
)
from app.blueprints.rest.v2.war_rooms.access import (
    can_write_war_room, require_war_room_read, require_war_room_write,
)
from app.business.war_room_decisions import DecisionCreate, DecisionStatus, InvalidDecisionTransition
from app.datamgmt.war_room_decisions_db import create_decision, list_decisions, transition_decision
from app.db import db
from app.web import Blueprint, request


war_rooms_decisions_blueprint = Blueprint(
    'war_rooms_decisions_rest_v2', __name__, url_prefix='/<int:war_room_id>/decisions',
)


@war_rooms_decisions_blueprint.get('')
@ac_api_requires()
@api_doc(tags=['WarRoomDecisions'], summary='Read the decision journal')
def get_decisions(war_room_id):
    error = require_war_room_read(war_room_id)
    if error is not None:
        return error
    before = request.args.get('before', type=int)
    if before is not None and not 0 < before <= 2**63 - 1:
        return response_api_error('Invalid decision cursor')
    return response_api_success({**list_decisions(war_room_id, before), 'can_write': can_write_war_room(war_room_id)})


@war_rooms_decisions_blueprint.post('')
@ac_api_requires()
@api_doc(tags=['WarRoomDecisions'], summary='Propose a decision', response_shape='created')
def post_decision(war_room_id):
    error = require_war_room_write(war_room_id)
    if error is not None:
        return error
    try:
        payload = DecisionCreate.model_validate(request.get_json())
    except ValidationError:
        return response_api_error('Invalid decision')
    row = create_decision(
        war_room_id, payload.title, payload.rationale, iris_current_user.id, iris_current_user.user,
    )
    return response_api_created(row)


@war_rooms_decisions_blueprint.post('/<int:decision_id>/status')
@ac_api_requires()
@api_doc(tags=['WarRoomDecisions'], summary='Record a decision status change')
def post_decision_status(war_room_id, decision_id):
    error = require_war_room_write(war_room_id)
    if error is not None:
        return error
    if not 0 < decision_id <= 2**63 - 1:
        return response_api_not_found()
    try:
        payload = DecisionStatus.model_validate(request.get_json())
    except ValidationError:
        return response_api_error('Invalid decision status')
    try:
        row = transition_decision(
            war_room_id, decision_id, payload.status, iris_current_user.id, iris_current_user.user, payload.comment,
        )
    except InvalidDecisionTransition as exc:
        db.session.rollback()
        return response_api_error(str(exc), status=409)
    return response_api_not_found() if row is None else response_api_success(row)
