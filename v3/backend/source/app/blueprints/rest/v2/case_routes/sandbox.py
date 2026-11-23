"""Authenticated MCP task import and case-scoped PCAP access."""
import io
import zlib
from werkzeug.utils import secure_filename
from app.web import Blueprint, request, send_file
from app.blueprints.access_controls import ac_api_requires, ac_fast_check_current_user_has_case_access, ac_api_return_access_denied
from app.blueprints.iris_user import iris_current_user
from app.blueprints.rest.endpoints import response_api_success, response_api_error, response_api_created, response_api_not_found
from app.business import ptsandbox as sandbox
from app.models.authorization import CaseAccessLevel
from app.iris_engine.evidence.pcap import capture_bytes
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


@case_sandbox_blueprint.get('/search')
@ac_api_requires()
@api_doc(tags=['PTSandbox'], summary='Search PT Sandbox tasks by file name')
def search_tasks(case_identifier):
    if not access(case_identifier, True):
        return ac_api_return_access_denied()
    try:
        days = int(request.args.get('days', '30'))
    except ValueError:
        return response_api_error('Search window must be between 1 and 90 days')
    try:
        return response_api_success({'tasks': sandbox.search_tasks(request.args.get('name'), days)})
    except BusinessProcessingError as exc:
        return response_api_error(exc.get_message())


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
                                    raw.get('started_at'), iris_current_user.id, include_events=raw.get('include_events') is True))
    except BusinessProcessingError as exc:
        return response_api_error(exc.get_message())


@case_sandbox_blueprint.get('/<int:identifier>')
@ac_api_requires()
@api_doc(tags=['PTSandbox'], summary='Get a case sandbox check and PCAP metadata')
def get_check(case_identifier, identifier):
    if not access(case_identifier):
        return ac_api_return_access_denied()
    try:
        return response_api_success(sandbox.projection(sandbox.get_scan(case_identifier, identifier), True))
    except LookupError:
        return response_api_not_found()


@case_sandbox_blueprint.get('/<int:identifier>/logs/<int:log_id>')
@ac_api_requires()
@api_doc(tags=['PTSandbox'], summary='Download a stored Sandbox PCAP')
def get_log(case_identifier, identifier, log_id):
    if not access(case_identifier):
        return ac_api_return_access_denied()
    try:
        if request.args.get('view') == 'text':
            return response_api_not_found()
        log = sandbox.read_capture(case_identifier, identifier, log_id)
        if log.content is None:
            return response_api_error(log.error or 'PCAP unavailable')
        raw = bytes(log.content)
        try:
            capture_bytes(raw)
        except (ValueError, OSError, EOFError, zlib.error):
            return response_api_error('Capture is invalid or exceeds 100 MiB')
        response = send_file(io.BytesIO(raw), as_attachment=True,
                             download_name=secure_filename(log.name) or 'sandbox.pcap',
                             mimetype='application/octet-stream')
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cache-Control'] = 'no-store'
        return response
    except LookupError:
        return response_api_not_found()
    except BusinessProcessingError as exc:
        return response_api_error(exc.get_message())
