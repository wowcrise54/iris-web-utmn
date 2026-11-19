"""Authenticated MCP task import and case-scoped report/log access."""
import datetime as dt
import io
from werkzeug.utils import secure_filename
from app.web import Blueprint, request, send_file
from app.blueprints.access_controls import ac_api_requires, ac_fast_check_current_user_has_case_access, ac_api_return_access_denied
from app.blueprints.iris_user import iris_current_user
from app.blueprints.rest.endpoints import response_api_success, response_api_error, response_api_created, response_api_not_found
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
        sandbox.checked_module_config()
        enabled = True
    except sandbox.SandboxError:
        enabled = False
    return response_api_success({'enabled': enabled, 'checks': sandbox.list_scans(case_identifier,
        before=request.args.get('before', type=int)), 'target_version': '5.39'})


@case_sandbox_blueprint.post('')
@ac_api_requires()
@api_doc(tags=['PTSandbox'], summary='Import an existing PT Sandbox task summary', response_shape='created')
def create_check(case_identifier):
    if not access(case_identifier, True):
        return ac_api_return_access_denied()
    raw = request.get_json() or {}
    if not isinstance(raw, dict):
        return response_api_error('Expected a task UUID and UTC start time')
    try:
        return response_api_created(sandbox.import_scan(case_identifier, raw.get('scan_id'),
                                    raw.get('started_at'), iris_current_user.id))
    except BusinessProcessingError as exc:
        return response_api_error(exc.get_message())


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
