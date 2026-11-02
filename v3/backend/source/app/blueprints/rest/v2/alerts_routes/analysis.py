"""Authenticated, owner-only asynchronous alert analysis API."""
from app.web import Blueprint, request
from app.blueprints.access_controls import ac_api_requires
from app.blueprints.iris_user import iris_current_user
from app.blueprints.rest.endpoints import response_api_success, response_api_created, response_api_error, response_api_not_found
from app.business.alert_analysis import (authorize_alert, start_alert_job, get_alert_job,
    retry_alert_job, cancel_alert_job, alert_projection, alert_metadata, authorize_alert_analysis)
from app.models.authorization import Permissions
from app.models.evidence_analysis import EvidenceAnalysis
from app.models.errors import BusinessProcessingError, ObjectNotFoundError

alerts_analysis_blueprint = Blueprint('alerts_analysis', __name__, url_prefix='/<int:alert_id>/analysis')


@alerts_analysis_blueprint.get('')
@ac_api_requires(Permissions.alerts_read)
def list_analyses(alert_id):
    try:
        authorize_alert(alert_id, iris_current_user._get_current_object())
        jobs = EvidenceAnalysis.query.filter_by(alert_id=alert_id, requested_by=iris_current_user.id, kind='alert').order_by(EvidenceAnalysis.id.desc()).limit(50).all()
        allowed = []
        for job in jobs:
            try:
                authorize_alert_analysis(job)
                allowed.append(alert_metadata(job))
            except ObjectNotFoundError:
                continue
        return response_api_success({'analyses': allowed})
    except ObjectNotFoundError:
        return response_api_not_found()


@alerts_analysis_blueprint.post('')
@ac_api_requires(Permissions.alerts_read)
def start_analysis(alert_id):
    try:
        return response_api_created(alert_projection(start_alert_job(alert_id, iris_current_user._get_current_object(), request.get_json(silent=True))))
    except ObjectNotFoundError:
        return response_api_not_found()
    except BusinessProcessingError as exc:
        return response_api_error(exc.get_message())


@alerts_analysis_blueprint.get('/<int:job_id>')
@ac_api_requires(Permissions.alerts_read)
def get_analysis(alert_id, job_id):
    try:
        return response_api_success(alert_projection(get_alert_job(alert_id, job_id, iris_current_user.id)))
    except ObjectNotFoundError:
        return response_api_not_found()


def _change(alert_id, job_id, operation):
    try:
        return response_api_success(alert_projection(operation(get_alert_job(alert_id, job_id, iris_current_user.id))))
    except ObjectNotFoundError:
        return response_api_not_found()
    except BusinessProcessingError as exc:
        return response_api_error(exc.get_message())


@alerts_analysis_blueprint.post('/<int:job_id>/retry')
@ac_api_requires(Permissions.alerts_read)
def retry_analysis(alert_id, job_id):
    return _change(alert_id, job_id, retry_alert_job)


@alerts_analysis_blueprint.post('/<int:job_id>/cancel')
@ac_api_requires(Permissions.alerts_read)
def cancel_analysis(alert_id, job_id):
    return _change(alert_id, job_id, cancel_alert_job)


@alerts_analysis_blueprint.get('/<int:job_id>/sources/<source_id>')
@ac_api_requires(Permissions.alerts_read)
def get_analysis_source(alert_id, job_id, source_id):
    try:
        job = get_alert_job(alert_id, job_id, iris_current_user.id)
        offset = int(request.args.get('offset', 0))
        limit = int(request.args.get('limit', 4096))
        if offset < 0 or not 1 <= limit <= 8192:
            raise ValueError()
        from app.iris_engine.evidence.alert_tasks import read_analysis_source
        return response_api_success(read_analysis_source(job, source_id, offset, limit))
    except ObjectNotFoundError:
        return response_api_not_found()
    except LookupError:
        return response_api_not_found()
    except (ValueError, BusinessProcessingError):
        return response_api_error('Invalid or unavailable analysis source range')
