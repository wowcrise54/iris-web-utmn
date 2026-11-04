"""Local bounded analysis API; case ACL and job ownership on every operation."""
import logging
from app.web import Blueprint, request
from app.blueprints.access_controls import ac_api_requires, ac_api_return_access_denied
from app.blueprints.rest.v2.case_routes.sandbox import access
from app.blueprints.iris_user import iris_current_user
from app.blueprints.rest.endpoints import response_api_success, response_api_error, response_api_created, response_api_not_found
from app.blueprints.rest.api_doc import api_doc
from app.business.evidence_analysis import start_job, get_job, retry_job, projection
from app.models.evidence_analysis import EvidenceAnalysis
from app.models.errors import BusinessProcessingError

case_analysis_blueprint = Blueprint('case_evidence_analysis', __name__, url_prefix='/<int:case_identifier>/analysis')
log = logging.getLogger('iris.evidence.api')


@case_analysis_blueprint.get('')
@ac_api_requires()
@api_doc(tags=['EvidenceAnalysis'], summary='List the caller analysis jobs in this case')
def list_analyses(case_identifier):
    if not access(case_identifier):
        return ac_api_return_access_denied()
    rows = EvidenceAnalysis.query.filter_by(case_id=case_identifier, requested_by=iris_current_user.id).order_by(EvidenceAnalysis.id.desc()).limit(50).all()
    return response_api_success({'analyses': [{**projection(row, graph=False), 'result': {}} for row in rows]})


@case_analysis_blueprint.post('')
@ac_api_requires()
@api_doc(tags=['EvidenceAnalysis'], summary='Start bounded local PCAP or Yuki Sandbox analysis', response_shape='created')
def start_analysis(case_identifier):
    if not access(case_identifier):
        return ac_api_return_access_denied()
    try:
        job = start_job(case_identifier, iris_current_user._get_current_object(), request.get_json(silent=True))
        log.info('analysis_start request_id=%s analysis_id=%s kind=%s', request.headers.get('X-Request-ID', '-'), job.id, job.kind)
        return response_api_created(projection(job))
    except LookupError:
        return response_api_not_found()
    except BusinessProcessingError as exc:
        return response_api_error(exc.get_message())


@case_analysis_blueprint.get('/<int:identifier>')
@ac_api_requires()
@api_doc(tags=['EvidenceAnalysis'], summary='Read a bounded analysis result and graph')
def get_analysis(case_identifier, identifier):
    if not access(case_identifier):
        return ac_api_return_access_denied()
    try:
        return response_api_success(projection(get_job(case_identifier, identifier, iris_current_user.id)))
    except LookupError:
        return response_api_not_found()


@case_analysis_blueprint.post('/<int:identifier>/continue')
@ac_api_requires()
@api_doc(tags=['EvidenceAnalysis'], summary='Continue a failed analysis from its saved summary')
def continue_analysis(case_identifier, identifier):
    if not access(case_identifier):
        return ac_api_return_access_denied()
    try:
        return response_api_success(projection(retry_job(get_job(case_identifier, identifier, iris_current_user.id))))
    except LookupError:
        return response_api_not_found()
    except BusinessProcessingError as exc:
        return response_api_error(exc.get_message())
