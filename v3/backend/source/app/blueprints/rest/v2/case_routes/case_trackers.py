from pydantic import ValidationError
from sqlalchemy.orm.exc import StaleDataError

from app.blueprints.access_controls import (
    ac_api_requires,
    ac_api_return_access_denied,
    ac_fast_check_current_user_has_case_access,
)
from app.blueprints.iris_user import iris_current_user
from app.blueprints.rest.api_doc import api_doc
from app.blueprints.rest.endpoints import (
    response_api_created,
    response_api_error,
    response_api_not_found,
    response_api_success,
)
from app.business.case_trackers import InvalidTrackerRow, TrackerSchema
from app.business.cases import cases_exists
from app.datamgmt.case.case_tracker_items_db import ITEMS, InvalidTrackerItem, list_tracker_items
from app.datamgmt.case.case_trackers_db import list_trackers, save_tracker
from app.db import db
from app.models.authorization import CaseAccessLevel
from app.web import Blueprint, request


case_trackers_blueprint = Blueprint(
    'case_trackers_rest_v2', __name__, url_prefix='/<int:case_identifier>/trackers',
)


def _access_error(case_id, levels):
    if not cases_exists(case_id):
        return response_api_not_found()
    if not ac_fast_check_current_user_has_case_access(case_id, levels):
        return ac_api_return_access_denied(caseid=case_id)
    return None


@case_trackers_blueprint.get('')
@ac_api_requires()
@api_doc(tags=['Case trackers'], summary='List case response trackers')
def get_trackers(case_identifier):
    error = _access_error(case_identifier, [CaseAccessLevel.read_only, CaseAccessLevel.full_access])
    if error is not None:
        return error
    return response_api_success(list_trackers(case_identifier))


@case_trackers_blueprint.get('/items/<kind>')
@ac_api_requires()
@api_doc(tags=['Case trackers'], summary='Find case items linkable from a response tracker')
def get_tracker_items(case_identifier, kind):
    error = _access_error(case_identifier, [CaseAccessLevel.read_only, CaseAccessLevel.full_access])
    if error is not None:
        return error
    if kind not in ITEMS:
        return response_api_not_found()
    search = request.args.get('query', '').strip()
    after = request.args.get('after', default=0, type=int)
    if len(search) > 128 or not 0 <= after <= 2**63 - 1:
        return response_api_error('Invalid item search')
    return response_api_success(list_tracker_items(case_identifier, kind, search, after))


def _write(case_id, tracker_id=None, version=None, *, delete=False):
    error = _access_error(case_id, [CaseAccessLevel.full_access])
    if error is not None:
        return error
    if tracker_id is not None and not (0 < tracker_id < 2**31 and 0 < version < 2**31):
        return response_api_not_found()
    try:
        data = None if delete else TrackerSchema.model_validate(request.get_json()).model_dump()
    except ValidationError as exc:
        return response_api_error('Invalid tracker', data=exc.errors(
            include_url=False, include_context=False, include_input=False,
        ))
    try:
        tracker = save_tracker(case_id, tracker_id, version, data, iris_current_user.id)
    except (InvalidTrackerItem, InvalidTrackerRow) as exc:
        return response_api_error(str(exc))
    except StaleDataError:
        db.session.rollback()
        return response_api_error('The tracker has changed. Reload it before editing.', status=409)
    if tracker is None:
        return response_api_not_found()
    return response_api_created(tracker) if tracker_id is None else response_api_success(tracker)


@case_trackers_blueprint.post('')
@ac_api_requires()
@api_doc(tags=['Case trackers'], summary='Create a case response tracker')
def create_tracker(case_identifier):
    return _write(case_identifier)


@case_trackers_blueprint.put('/<int:tracker_id>/<int:version>')
@ac_api_requires()
@api_doc(tags=['Case trackers'], summary='Update a case response tracker')
def update_tracker(case_identifier, tracker_id, version):
    return _write(case_identifier, tracker_id, version)


@case_trackers_blueprint.delete('/<int:tracker_id>/<int:version>')
@ac_api_requires()
@api_doc(tags=['Case trackers'], summary='Delete a case response tracker')
def delete_tracker(case_identifier, tracker_id, version):
    return _write(case_identifier, tracker_id, version, delete=True)
