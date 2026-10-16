"""Case ACL guarded incident-card endpoints."""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.web import Blueprint, request
from app.blueprints.access_controls import (
    ac_api_requires,
    ac_fast_check_current_user_has_case_access,
    ac_api_return_access_denied,
)
from app.blueprints.iris_user import iris_current_user
from app.models.authorization import CaseAccessLevel
from app.blueprints.rest.endpoints import (
    response_api_success,
    response_api_error,
    response_api_not_found,
)
from app.business.incident_cards import CardValidationError, CardConflictError
from app.business.incident_cards import get_incident_card, save_incident_card

case_incident_card_blueprint = Blueprint(
    "case_incident_card", __name__, url_prefix="/<int:case_identifier>/incident-card"
)


def permitted(case_identifier, write=False):
    levels = (
        [CaseAccessLevel.full_access]
        if write
        else [CaseAccessLevel.read_only, CaseAccessLevel.full_access]
    )
    return ac_fast_check_current_user_has_case_access(case_identifier, levels)


@case_incident_card_blueprint.get("")
@ac_api_requires()
def read_incident_card(case_identifier):
    if not permitted(case_identifier):
        return ac_api_return_access_denied(caseid=case_identifier)
    try:
        return response_api_success(get_incident_card(case_identifier))
    except LookupError:
        return response_api_not_found()


@case_incident_card_blueprint.put("")
@ac_api_requires()
def update_incident_card(case_identifier):
    if not permitted(case_identifier, True):
        return ac_api_return_access_denied(caseid=case_identifier)
    if request.content_length is not None and request.content_length > 256000:
        return response_api_error("Card exceeds 256 KB", status=413)
    try:
        result = save_incident_card(
            case_identifier, request.get_json(), iris_current_user.id
        )
        return response_api_success(result)
    except CardConflictError as exc:
        return response_api_error(str(exc), status=409)
    except CardValidationError as exc:
        return response_api_error(str(exc))
    except LookupError:
        return response_api_not_found()


@case_incident_card_blueprint.get("/export")
@ac_api_requires()
def export_incident_card(case_identifier):
    if not permitted(case_identifier):
        return ac_api_return_access_denied(caseid=case_identifier)
    timezone_name = request.args.get("timezone", "Asia/Yekaterinburg")
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        return response_api_error("Unknown export timezone")
    try:
        from app.business.reports.incident_card_report import build_export

        return response_api_success(
            build_export(
                get_incident_card(case_identifier), timezone_name=timezone_name
            )
        )
    except LookupError:
        return response_api_not_found()
