"""Offline PCAP analysis and retirement of legacy Sandbox jobs."""
import datetime as dt
import hashlib
import logging
from app import celery
from app.db import db
from app.models.authorization import User, CaseAccessLevel
from app.models.case_chat import CaseChatConversation, CaseChatMessage, ROLE_ASSISTANT
from app.models.evidence_analysis import EvidenceAnalysis
from app.business.access_controls import ac_fast_check_user_has_case_access
from app.business import case_chat
from app.business.evidence_analysis import read_source
from app.iris_engine.evidence.pcap import analyze_capture
from app.iris_engine.evidence.text import prune_caches

log = logging.getLogger('iris.evidence')


def authorized(job):
    user = db.session.get(User, job.requested_by)
    if not user or not user.active or not ac_fast_check_user_has_case_access(
            user.id, job.case_id, [CaseAccessLevel.read_only, CaseAccessLevel.full_access]):
        raise ValueError('Requesting user no longer has case access')
    return user


def publish(job):
    if not job.conversation_id:
        return
    conv = db.session.get(CaseChatConversation, job.conversation_id)
    if not conv or conv.user_id != job.requested_by or conv.case_id != job.case_id or conv.archived_at:
        return
    summary = (job.result or {}).get('summary') or ''
    if not summary and not job.error:
        return
    body = (job.result or {}).get('partial_response') or summary
    if job.error:
        body += '\n\nФоновый анализ остановлен. Для нового анализа откройте проверку PT Sandbox и запустите анализ событий в чате Yuki.'
    omissions = (job.result or {}).get('omissions', [])
    if omissions:
        body += '\n\nОграничения охвата:\n' + '\n'.join('- ' + item for item in omissions)
    body += f'\n\n[Источники и состояние анализа #{job.id}](/case/{job.case_id}/analysis?analysis={job.id})'
    content = [{'type': 'text', 'text': body}]
    message = db.session.get(CaseChatMessage, job.message_id) if job.message_id else None
    if message:
        message.content = content
    else:
        message = case_chat.append_message(conversation=conv, role=ROLE_ASSISTANT, content=content)
        job.message_id = message.id
    db.session.commit()
    try:
        from app import socket_io
        socket_io.emit('analysis_updated', {'conversation_id': conv.id, 'analysis_id': job.id,
                                          'status': job.status}, namespace='/chat', to=f'conv-{conv.id}')
    except Exception:
        log.warning('analysis_notification_failed analysis_id=%s', job.id)


@celery.task(name='iris.evidence.process', soft_time_limit=360, time_limit=390)
def process_analysis(identifier):
    job = EvidenceAnalysis.query.filter_by(id=identifier).with_for_update(skip_locked=True).first()
    if not job or job.status != 'queued':
        return
    job.status, job.updated_at = 'running', dt.datetime.utcnow()
    db.session.commit()
    try:
        authorized(job)
        if job.kind == 'pcap':
            raw = read_source(job.case_id, job.source)
            result = analyze_capture(raw)
            authorized(job)
            job.result = {**result, 'original_sha256': hashlib.sha256(raw).hexdigest(), 'source': job.source}
            job.status, job.progress, job.total = ('partial' if result['partial'] else 'completed'), 1, 1
        else:
            raise ValueError('Batch Sandbox analysis was retired; analyze events in Yuki chat')
        job.updated_at = dt.datetime.utcnow()
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        job = db.session.get(EvidenceAnalysis, identifier)
        if job:
            # Error bodies/URLs and subprocess stderr are never exposed.
            job.status, job.error, job.updated_at = 'failed', str(exc)[:240] if isinstance(exc, ValueError) else 'Analysis failed; check worker diagnostics', dt.datetime.utcnow()
            log.warning('analysis_failed analysis_id=%s kind=%s category=%s', job.id, job.kind, type(exc).__name__)
            db.session.commit()
            try:
                authorized(job)
                publish(job)
            except ValueError:
                pass


@celery.task(name='iris.evidence.recover')
def recover_analyses():
    try:
        prune_caches()
    except OSError:
        log.warning('analysis_cache_prune_failed')
    cutoff = dt.datetime.utcnow() - dt.timedelta(minutes=10)
    queued = []
    for job in EvidenceAnalysis.query.filter(EvidenceAnalysis.status.in_(('queued', 'running')),
            EvidenceAnalysis.updated_at < cutoff).with_for_update(skip_locked=True).all():
        if job.status == 'running':
            job.status, job.error = 'failed', ('Open the Sandbox check and analyze events in Yuki chat'
                                               if job.kind == 'sandbox' else 'Worker interrupted; retry the analysis')
        else:
            queued.append(job.id)
        job.updated_at = dt.datetime.utcnow()
    db.session.commit()
    for identifier in queued:
        process_analysis.delay(identifier)


celery.conf.beat_schedule['evidence-recover'] = {'task': 'iris.evidence.recover', 'schedule': 60.0}
