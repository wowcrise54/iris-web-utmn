"""Case/owner-scoped job creation and bounded result projections."""
import datetime as dt
from pathlib import Path
from sqlalchemy.exc import IntegrityError
from app.db import db
from app.business import ptsandbox
from app.models.evidence_analysis import EvidenceAnalysis
from app.models.errors import BusinessProcessingError
from app.models.case_chat import CaseChatConversation
from app.models.authorization import User
from app.iris_engine.evidence.pcap import MAX_INPUT


def get_job(case_id, identifier, user_id):
    job = EvidenceAnalysis.query.filter_by(id=identifier, case_id=case_id, requested_by=user_id).first()
    if not job:
        raise LookupError('Analysis not found')
    return job


def projection(job, *, graph=True):
    result = dict(job.result or {})
    if not graph:
        # The LLM gets metadata and selected flows, never the complete graph or packets.
        result.pop('nodes', None)
        flows = result.pop('edges', [])
        if flows:
            result['flows'] = flows[:12]
            result['flows_omitted'] = max(0, len(flows) - 12)
        result['indicators'] = result.get('indicators', [])[:20]
    return {'id': job.id, 'case_id': job.case_id, 'kind': job.kind, 'status': job.status,
            'progress': job.progress, 'total': job.total, 'result': result, 'error': job.error,
            'conversation_id': job.conversation_id,
            'source_url': f'/case/{job.case_id}/analysis?analysis={job.id}', 'untrusted_data': True}


def read_source(case_id, source):
    if source.get('file_id'):
        error, file = ptsandbox.datastore_get_local_file_path(source['file_id'], case_id)
        if error or not file:
            raise BusinessProcessingError('Source file is not available in this case')
        path = Path(file.file_local_name)
        if not path.is_file() or path.stat().st_size > MAX_INPUT:
            raise BusinessProcessingError('Source file is missing or exceeds 100 MiB')
        return path.read_bytes()
    log = ptsandbox.read_log(case_id, source['scan_id'], source['log_id'])
    if log.content is None:
        raise BusinessProcessingError('Source log is unavailable')
    return bytes(log.content)


def start_job(case_id, user, body):
    if not isinstance(body, dict) or body.get('kind') not in ('pcap', 'sandbox'):
        raise BusinessProcessingError('Select PCAP or Sandbox analysis')
    kind = body['kind']
    source = {k: body[k] for k in ('file_id', 'scan_id', 'log_id') if body.get(k) is not None}
    if any(type(v) is not int or v <= 0 for v in source.values()):
        raise BusinessProcessingError('Invalid source identifier')
    valid = set(source) == {'scan_id'} if kind == 'sandbox' else set(source) in ({'file_id'}, {'scan_id', 'log_id'})
    if not valid:
        raise BusinessProcessingError('Select one case file or a Sandbox check/log')
    if 'scan_id' in source:
        ptsandbox.get_scan(case_id, source['scan_id'])
    if 'log_id' in source:
        ptsandbox.read_log(case_id, source['scan_id'], source['log_id'])
    # Content validation runs in the worker; request handlers never read/decompress large binaries.
    if 'file_id' in source:
        error, file = ptsandbox.datastore_get_local_file_path(source['file_id'], case_id)
        if error or not file:
            raise BusinessProcessingError('Source file is not available in this case')
    key = kind + ':' + ':'.join(f'{k}={v}' for k, v in sorted(source.items()))
    active = EvidenceAnalysis.query.filter_by(case_id=case_id, requested_by=user.id, source_key=key).filter(
        EvidenceAnalysis.status.in_(('queued', 'running'))).first()
    if active:
        return active
    if EvidenceAnalysis.query.filter_by(requested_by=user.id).filter(EvidenceAnalysis.status.in_(('queued', 'running'))).count() >= 2:
        raise BusinessProcessingError('Wait for an active analysis to finish (maximum 2)')
    conversation_id = body.get('conversation_id')
    if conversation_id is not None and (type(conversation_id) is not int or conversation_id <= 0):
        raise BusinessProcessingError('Invalid conversation identifier')
    if kind == 'sandbox':
        from app.business import case_chat
        from app.iris_engine.llm.client import load_config
        from app.iris_engine.llm.policy import resolve_for_case
        cfg = load_config(policy=resolve_for_case(case_id).policy)
        if not cfg.enabled:
            raise BusinessProcessingError('Yuki is disabled')
        if conversation_id is not None:
            conv = CaseChatConversation.query.filter_by(id=conversation_id, user_id=user.id, case_id=case_id).first()
            if not conv or conv.archived_at is not None:
                raise BusinessProcessingError('Select an active conversation owned by you in this case')
        else:
            conv = case_chat.create_conversation(user=user, case_id=case_id, model=cfg.model,
                                                 title=f"PT Sandbox #{source['scan_id']}")
            conversation_id = conv.id
    else:
        conversation_id = None
    # Serialize the per-user resource quota, including requests from different tabs.
    db.session.query(User).filter(User.id == user.id).with_for_update().one()
    if EvidenceAnalysis.query.filter_by(requested_by=user.id).filter(EvidenceAnalysis.status.in_(('queued', 'running'))).count() >= 2:
        raise BusinessProcessingError('Wait for an active analysis to finish (maximum 2)')
    job = EvidenceAnalysis(case_id=case_id, requested_by=user.id, kind=kind, source=source,
                           source_key=key, conversation_id=conversation_id, result={})
    try:
        db.session.add(job)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return EvidenceAnalysis.query.filter_by(case_id=case_id, requested_by=user.id, source_key=key).filter(
            EvidenceAnalysis.status.in_(('queued', 'running'))).one()
    from app.iris_engine.evidence.tasks import process_analysis
    try:
        process_analysis.delay(job.id)
    except Exception:
        # Recovery task picks up persistently queued jobs when the broker is back.
        pass
    return job


def retry_job(job):
    if job.status != 'failed':
        raise BusinessProcessingError('Only failed analyses can be continued')
    db.session.query(User).filter(User.id == job.requested_by).with_for_update().one()
    active = EvidenceAnalysis.query.filter_by(case_id=job.case_id, requested_by=job.requested_by,
        source_key=job.source_key).filter(EvidenceAnalysis.status.in_(('queued', 'running'))).first()
    if active:
        return active
    if EvidenceAnalysis.query.filter_by(requested_by=job.requested_by).filter(EvidenceAnalysis.status.in_(('queued', 'running'))).count() >= 2:
        raise BusinessProcessingError('Wait for an active analysis to finish (maximum 2)')
    job.status, job.error, job.updated_at = 'queued', None, dt.datetime.utcnow()
    db.session.commit()
    from app.iris_engine.evidence.tasks import process_analysis
    try:
        process_analysis.delay(job.id)
    except Exception:
        pass
    return job
