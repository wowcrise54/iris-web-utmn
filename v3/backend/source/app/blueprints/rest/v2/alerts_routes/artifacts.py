from app.web import Blueprint, request, session, send_file
from app.blueprints.access_controls import (
    ac_api_requires, ac_api_return_access_denied, ac_current_user_has_customer_access)
from app.blueprints.iris_user import iris_current_user
from app.blueprints.rest.endpoints import (
    response_api_success, response_api_error, response_api_not_found)
from app.business.alerts import alerts_get
from app.business.alert_materials import (
    artifact_path, create_artifact, get_artifact, update_artifact, delete_artifact)
from app.business.alert_materials_validation import is_alert_owner
from app.models.authorization import Permissions
from app.models.errors import ObjectNotFoundError
from app.iris_engine.demo_builder import demo_mode_over_upload_cap, demo_mode_upload_cap_message


alerts_artifacts_blueprint = Blueprint('alerts_artifacts', __name__,
                                      url_prefix='/<int:alert_identifier>/artifacts')


def _alert(identifier):
    return alerts_get(iris_current_user, session.get('permissions') or 0, identifier,
                      fallback_customer_access=ac_current_user_has_customer_access)


@alerts_artifacts_blueprint.get('')
@ac_api_requires(Permissions.alerts_read)
def list_artifacts(alert_identifier):
    try:
        alert = _alert(alert_identifier)
        return response_api_success([row.serialize() for row in alert.artifacts])
    except ObjectNotFoundError:
        return response_api_not_found()


@alerts_artifacts_blueprint.post('')
@ac_api_requires(Permissions.alerts_write)
def add_artifact(alert_identifier):
    try:
        alert = _alert(alert_identifier)
        if not is_alert_owner(alert, iris_current_user.id):
            return ac_api_return_access_denied()
        upload = request.files.get('file')
        if upload is not None and demo_mode_over_upload_cap(upload):
            return response_api_error(demo_mode_upload_cap_message())
        payload = request.form.to_dict() if upload is not None else request.get_json()
        row = create_artifact(alert, iris_current_user.id, payload, upload)
        return response_api_success(row.serialize())
    except ObjectNotFoundError:
        return response_api_not_found()
    except ValueError as exc:
        return response_api_error(str(exc))


@alerts_artifacts_blueprint.put('/<int:identifier>')
@ac_api_requires(Permissions.alerts_write)
def edit_artifact(alert_identifier, identifier):
    try:
        alert = _alert(alert_identifier)
        if not is_alert_owner(alert, iris_current_user.id):
            return ac_api_return_access_denied()
        payload = request.get_json()
        if not isinstance(payload, dict):
            return response_api_error('Expected an object')
        row = update_artifact(alert, get_artifact(alert, identifier), iris_current_user.id, payload)
        return response_api_success(row.serialize())
    except ObjectNotFoundError:
        return response_api_not_found()
    except ValueError as exc:
        return response_api_error(str(exc))


@alerts_artifacts_blueprint.delete('/<int:identifier>')
@ac_api_requires(Permissions.alerts_write)
def remove_artifact(alert_identifier, identifier):
    try:
        alert = _alert(alert_identifier)
        if not is_alert_owner(alert, iris_current_user.id):
            return ac_api_return_access_denied()
        delete_artifact(alert, get_artifact(alert, identifier))
        return response_api_success(None)
    except ObjectNotFoundError:
        return response_api_not_found()


@alerts_artifacts_blueprint.get('/<int:identifier>/content')
@ac_api_requires(Permissions.alerts_read)
def download_artifact(alert_identifier, identifier):
    try:
        row = get_artifact(_alert(alert_identifier), identifier)
        if row.kind != 'file' or not artifact_path(row).is_file():
            return response_api_not_found()
        response = send_file(artifact_path(row), as_attachment=True, download_name=row.value,
                             mimetype='application/octet-stream')
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cache-Control'] = 'private, no-store'
        return response
    except ObjectNotFoundError:
        return response_api_not_found()
