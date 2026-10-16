"""Authenticated file submission and case-scoped report/log access."""
import datetime as dt
import io
from werkzeug.utils import secure_filename
from app.web import Blueprint, request, send_file
from app.blueprints.access_controls import ac_api_requires, ac_fast_check_current_user_has_case_access, ac_api_return_access_denied
from app.blueprints.iris_user import iris_current_user
from app.blueprints.rest.endpoints import response_api_success, response_api_error, response_api_created, response_api_not_found
from app.blueprints.rest.v2.war_rooms.access import require_war_room_write
from app.business import ptsandbox as sandbox
from app.db import db
from app.models.authorization import CaseAccessLevel
from app.models.errors import BusinessProcessingError
from app.blueprints.rest.api_doc import api_doc

case_sandbox_blueprint = Blueprint('case_sandbox', __name__, url_prefix='/<int:case_identifier>/sandbox')


def access(case_id, write=False):
    levels = [CaseAccessLevel.full_access] if write else [CaseAccessLevel.read_only, CaseAccessLevel.full_access]
    return ac_fast_check_current_user_has_case_access(case_id, levels)


@case_sandbox_blueprint.get('')
@ac_api_requires()
@api_doc(tags=['PTSandbox'], summary='List case sandbox checks')
def list_checks(case_identifier):
    if not access(case_identifier):
        return ac_api_return_access_denied()
    try:
        sandbox.module_config()
        enabled = True
    except sandbox.SandboxError:
        enabled = False
    return response_api_success({'enabled': enabled, 'checks': sandbox.list_scans(case_identifier,
        before=request.args.get('before', type=int)), 'target_version': '5.37'})


@case_sandbox_blueprint.post('')
@ac_api_requires()
@api_doc(tags=['PTSandbox'], summary='Submit a case file to PT Sandbox', response_shape='created')
def create_check(case_identifier):
    if not access(case_identifier, True):
        return ac_api_return_access_denied()
    raw = request.get_json() or {}
    if not isinstance(raw, dict) or type(raw.get('file_id')) is not int or raw['file_id'] <= 0:
        return response_api_error('Select a file from this case')
    war_room_id = raw.get('war_room_id')
    if war_room_id is not None:
        if type(war_room_id) is not int or war_room_id <= 0:
            return response_api_error('Invalid war room ID')
        err = require_war_room_write(war_room_id)
        if err is not None:
            return err
    try:
        return response_api_created(sandbox.start_scan(case_identifier, raw['file_id'], iris_current_user.id,
                                      confirmed=raw.get('confirmed'), war_room_id=war_room_id))
    except BusinessProcessingError as exc:
        return response_api_error(exc.get_message())


@case_sandbox_blueprint.get('/files/<int:file_id>/submission-info')
@ac_api_requires()
@api_doc(tags=['PTSandbox'], summary='Preview the actual stored file before sending it to Sandbox')
def submission_info(case_identifier, file_id):
    if not access(case_identifier):
        return ac_api_return_access_denied()
    from pathlib import Path
    error, file = sandbox.datastore_get_local_file_path(file_id, case_identifier)
    if error or not Path(file.file_local_name).is_file():
        return response_api_not_found()
    zipped = bool(file.file_is_ioc or file.file_password)
    return response_api_success({'file_id': file.file_id, 'file_name': file.file_original_name + ('.zip' if zipped else ''),
                                 'size': Path(file.file_local_name).stat().st_size, 'is_stored_zip': zipped})


@case_sandbox_blueprint.get('/<int:identifier>')
@ac_api_requires()
@api_doc(tags=['PTSandbox'], summary='Get a case sandbox check and log metadata')
def get_check(case_identifier, identifier):
    if not access(case_identifier):
        return ac_api_return_access_denied()
    try:
        return response_api_success(sandbox.projection(sandbox.get_scan(case_identifier, identifier), True))
    except LookupError:
        return response_api_not_found()


@case_sandbox_blueprint.post('/<int:identifier>/resume')
@ac_api_requires()
@api_doc(tags=['PTSandbox'], summary='Resume retrieving an existing sandbox task')
def resume_check(case_identifier, identifier):
    if not access(case_identifier, True):
        return ac_api_return_access_denied()
    try:
        scan = sandbox.get_scan(case_identifier, identifier)
        if scan.status not in ('failed', 'partial') or not scan.scan_id:
            return response_api_error('Only a failed check with an existing Sandbox task can be resumed')
        if scan.war_room_id:
            err = require_war_room_write(scan.war_room_id)
            if err is not None:
                return err
        scan.status = 'running'
        scan.error = None
        scan.finished_at = None
        scan.notification_id = None
        scan.requested_by = iris_current_user.id
        scan.options = {**scan.options, 'wait_started_at': dt.datetime.utcnow().isoformat()}
        scan.updated_at = dt.datetime.utcnow()
        try:
            db.session.commit()
        except sandbox.IntegrityError:
            db.session.rollback()
            return response_api_error('Another active check exists for this file')
        from app.iris_engine.ptsandbox.tasks import process_scan
        try:
            process_scan.delay(scan.id)
        except Exception:
            pass  # The recovery task enqueues this persisted row when the broker returns.
        return response_api_success(sandbox.projection(scan))
    except LookupError:
        return response_api_not_found()


@case_sandbox_blueprint.post('/<int:identifier>/acknowledge')
@ac_api_requires()
@api_doc(tags=['PTSandbox'], summary='Acknowledge manual investigation of an ambiguous submission')
def acknowledge_unknown(case_identifier, identifier):
    if not access(case_identifier, True):
        return ac_api_return_access_denied()
    raw = request.get_json() or {}
    try:
        scan = sandbox.get_scan(case_identifier, identifier)
        if scan.status != 'submission_unknown' or not isinstance(raw, dict) or raw.get('confirmed') is not True:
            return response_api_error('Confirm that you have checked the task in PT Sandbox')
        scan.status = 'acknowledged'
        scan.updated_at = dt.datetime.utcnow()
        db.session.commit()
        return response_api_success(sandbox.projection(scan))
    except LookupError:
        return response_api_not_found()


@case_sandbox_blueprint.get('/<int:identifier>/logs/<int:log_id>')
@ac_api_requires()
@api_doc(tags=['PTSandbox'], summary='Download an original sandbox log or read a text page')
def get_log(case_identifier, identifier, log_id):
    if not access(case_identifier):
        return ac_api_return_access_denied()
    try:
        log = sandbox.read_log(case_identifier, identifier, log_id)
        if request.args.get('view') == 'text':
            return response_api_success(sandbox.text_page(log, offset=max(0, request.args.get('offset', 0, type=int))))
        if log.content is None:
            return response_api_error(log.error or 'Log unavailable')
        response = send_file(io.BytesIO(log.content), as_attachment=True,
                             download_name=secure_filename(log.name) or 'sandbox-log.bin',
                             mimetype='application/octet-stream')
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cache-Control'] = 'no-store'
        return response
    except LookupError:
        return response_api_not_found()
    except BusinessProcessingError as exc:
        return response_api_error(exc.get_message())
