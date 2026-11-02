"""Owner-scoped alert analysis lifecycle; workers use the same explicit ACL."""
import datetime as dt

from app.db import db
from app.business.alerts import alerts_get
from app.models.authorization import User, Permissions, ac_flag_match_mask
from app.models.alerts import Alert
from app.models.evidence_analysis import EvidenceAnalysis
from app.models.errors import BusinessProcessingError, ObjectNotFoundError
from app.iris_engine.access_control.utils import ac_get_effective_permissions_of_user


def authorize_alert(alert_id, user):
    # JWT/socket principals carry identity only; enabled state belongs to User.
    if user is not None and not isinstance(user, User):
        user = db.session.get(User, getattr(user, 'id', None))
    if user is None:
        raise ObjectNotFoundError()
    db.session.refresh(user, attribute_names=['active'])
    if not user.active:
        raise ObjectNotFoundError()
    # A long-running stream can retain an Alert identity-map entry after a
    # customer reassignment. Refresh the tenant column after the ACL lookup,
    # before comparing it with the immutable conversation binding.
    alert = db.session.get(Alert, alert_id)
    if alert is None:
        raise ObjectNotFoundError()
    permissions = ac_get_effective_permissions_of_user(user)
    if not (ac_flag_match_mask(permissions, Permissions.alerts_read.value) or
            ac_flag_match_mask(permissions, Permissions.server_administrator.value)):
        raise ObjectNotFoundError()
    alert = alerts_get(user, permissions, alert_id)
    db.session.refresh(alert, attribute_names=['alert_customer_id'])
    return alert


def authorize_alert_analysis(job):
    user = db.session.get(User, job.requested_by)
    from app.models.case_chat import CaseChatConversation
    conv = db.session.get(CaseChatConversation, job.conversation_id)
    if not conv or conv.alert_id != job.alert_id:
        raise ObjectNotFoundError()
    alert = authorize_alert_conversation(conv, user)
    return user, alert


def authorize_alert_conversation(conv, user):
    if (user is None or conv.user_id != user.id or conv.alert_id is None or
            conv.case_id is not None or conv.war_room_id is not None):
        raise ObjectNotFoundError()
    alert = authorize_alert(conv.alert_id, user)
    if conv.alert_customer_id != alert.alert_customer_id:
        raise ObjectNotFoundError()
    from app.iris_engine.llm.policy import resolve_for_alert
    resolved = resolve_for_alert(alert.alert_id)
    policy_id = resolved.policy.id if resolved.policy else None
    if conv.resolved_policy_id != policy_id:
        raise ObjectNotFoundError()
    return alert


def get_alert_job(alert_id, job_id, user_id):
    job = EvidenceAnalysis.query.filter_by(id=job_id, alert_id=alert_id, requested_by=user_id, kind='alert').first()
    if job is None:
        raise ObjectNotFoundError()
    authorize_alert_analysis(job)
    return job


def _active(user_id, alert_id):
    return EvidenceAnalysis.query.filter_by(requested_by=user_id, alert_id=alert_id, source_key=f'alert:{alert_id}').filter(
        EvidenceAnalysis.status.in_(('queued', 'running'))).with_for_update().populate_existing().first()


def _lock_job(job):
    return EvidenceAnalysis.query.filter_by(id=job.id, requested_by=job.requested_by).with_for_update().populate_existing().one()


def _quota(user_id):
    if EvidenceAnalysis.query.filter_by(requested_by=user_id).filter(EvidenceAnalysis.status.in_(('queued', 'running'))).count() >= 2:
        raise BusinessProcessingError('Wait for an active analysis to finish (maximum 2)')


def _queue(job):
    from app.iris_engine.evidence.alert_tasks import process_alert_analysis
    try:
        process_alert_analysis.delay(job.id)
    except Exception:
        # The recovery task picks up durable queued work after broker outages.
        pass


def start_alert_job(alert_id, user, body):
    if not isinstance(body, dict) or body:
        raise BusinessProcessingError('Alert analysis accepts an empty object')
    alert = authorize_alert(alert_id, user)
    from app.business.case_chat import create_conversation
    from app.iris_engine.llm.client import load_config
    from app.iris_engine.llm.policy import resolve_for_alert
    cfg = load_config(policy=resolve_for_alert(alert_id).policy)
    if not cfg.enabled:
        raise BusinessProcessingError('Yuki is disabled')
    db.session.query(User).filter(User.id == user.id).with_for_update().one()
    active = _active(user.id, alert_id)
    if active:
        try:
            authorize_alert_analysis(active)
            return active
        except ObjectNotFoundError:
            # Retire only this owner's obsolete scope to free its active index;
            # the old snapshot/chat remains inaccessible after reassignment.
            active.status = 'failed'
            active.error = 'Alert customer or policy changed; start a new analysis.'
            active.result = {**(active.result or {}), '_cancel_requested': True}
            active.updated_at = dt.datetime.utcnow()
            db.session.flush()
    _quota(user.id)
    # Flush the conversation without committing to keep the per-user lock until
    # the job is inserted; simultaneous tabs cannot create orphan conversations.
    conv = create_conversation(user=user, case_id=None, alert_id=alert_id,
                               model=cfg.model, title=f'Alert #{alert.alert_id} analysis', commit=False)
    job = EvidenceAnalysis(alert_id=alert_id, requested_by=user.id, kind='alert',
                           source={'alert_id': alert_id}, source_key=f'alert:{alert_id}',
                           conversation_id=conv.id, result={'stage': 'queued'})
    db.session.add(job)
    db.session.commit()
    _queue(job)
    return job


def retry_alert_job(job):
    authorize_alert_analysis(job)
    db.session.query(User).filter(User.id == job.requested_by).with_for_update().one()
    job = _lock_job(job)
    authorize_alert_analysis(job)
    if job.status not in ('failed', 'partial', 'cancelled'):
        raise BusinessProcessingError('Only failed, partial or cancelled analyses can be continued')
    active = _active(job.requested_by, job.alert_id)
    if active:
        return active
    _quota(job.requested_by)
    result = dict(job.result or {})
    result.pop('_cancel_requested', None)
    result['stage'] = 'queued'
    job.result = result
    job.status, job.error, job.updated_at = 'queued', None, dt.datetime.utcnow()
    db.session.commit()
    _queue(job)
    return job


def cancel_alert_job(job):
    authorize_alert_analysis(job)
    job = _lock_job(job)
    authorize_alert_analysis(job)
    if job.status in ('queued', 'running'):
        job.result = {**(job.result or {}), '_cancel_requested': True}
        if job.status == 'queued':
            job.status = 'cancelled'
            job.result = {**job.result, 'stage': 'cancelled'}
        job.updated_at = dt.datetime.utcnow()
        db.session.commit()
    return job


def alert_projection(job):
    # Explicit public fields: checkpoint, snapshot paths and raw source are private.
    result = {k: v for k, v in (job.result or {}).items()
              if k in ('stage', 'coverage', 'report', 'summary', 'sources', 'limitations', 'usage', 'snapshot_hash', 'captured_at', 'stats')}
    if 'sources' in result:
        result['sources'] = [{k: v for k, v in source.items()
                              if k in ('id', 'source_id', 'label', 'kind', 'sha256', 'bytes', 'size', 'status')}
                             for source in result['sources'] if isinstance(source, dict)]
    return {'id': job.id, 'alert_id': job.alert_id, 'conversation_id': job.conversation_id,
            'kind': 'alert', 'status': job.status, 'stage': result.get('stage', job.status),
            'progress': job.progress, 'total': job.total, 'result': result,
            'error': job.error, 'source_url': f'/alerts/{job.alert_id}?analysis={job.id}',
            'created_at': job.created_at.isoformat() if job.created_at else None,
            'updated_at': job.updated_at.isoformat() if job.updated_at else None}


def alert_metadata(job):
    value = alert_projection(job)
    coverage = dict(value['result'].get('coverage', {}))
    missing = coverage.get('missing_events')
    if isinstance(missing, list):
        coverage['missing_events_count'] = len(missing)
        coverage.pop('missing_events')
        coverage['missing_events_omitted'] = len(missing)
    value['coverage'] = coverage
    value.pop('result')
    value.pop('error')
    return value
