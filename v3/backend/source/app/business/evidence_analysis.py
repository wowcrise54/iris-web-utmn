"""Case/owner-scoped job creation and bounded result projections."""
import datetime as dt
from pathlib import Path
from sqlalchemy.exc import IntegrityError
from app.db import db
from app.business import ptsandbox
from app.models.evidence_analysis import EvidenceAnalysis
from app.models.errors import BusinessProcessingError
from app.models.authorization import User
from app.iris_engine.evidence.pcap import MAX_INPUT


def get_job(case_id, identifier, user_id):
    job = EvidenceAnalysis.query.filter_by(id=identifier, case_id=case_id, requested_by=user_id).first()
    if not job:
        raise LookupError('Analysis not found')
    return job


def projection(job, *, graph=True):
    result = {key: value for key, value in (job.result or {}).items() if not key.startswith('_')}
    if not graph:
        # The LLM gets metadata and selected flows, never the complete graph or packets.
        result.pop('nodes', None)
        if result.get('sources'):
            result['sources'] = result['sources'][-20:]
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
    log = ptsandbox.read_capture(case_id, source['scan_id'], source['log_id'])
    if log.content is None:
        raise BusinessProcessingError('Source log is unavailable')
    return bytes(log.content)


def start_job(case_id, user, body):
    if isinstance(body, dict) and body.get('kind') == 'sandbox':
        raise BusinessProcessingError('Analyze Sandbox events in Yuki chat')
    if not isinstance(body, dict) or body.get('kind') != 'pcap':
        raise BusinessProcessingError('Select PCAP analysis')
    kind = 'pcap'
    source = {k: body[k] for k in ('file_id', 'scan_id', 'log_id') if body.get(k) is not None}
    if any(type(v) is not int or v <= 0 for v in source.values()):
        raise BusinessProcessingError('Invalid source identifier')
    valid = set(source) in ({'file_id'}, {'scan_id', 'log_id'})
    if not valid:
        raise BusinessProcessingError('Select one case file or a Sandbox check/log')
    if 'log_id' in source:
        ptsandbox.read_capture(case_id, source['scan_id'], source['log_id'])
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
    # Serialize the per-user resource quota, including requests from different tabs.
    db.session.query(User).filter(User.id == user.id).with_for_update().one()
    if EvidenceAnalysis.query.filter_by(requested_by=user.id).filter(EvidenceAnalysis.status.in_(('queued', 'running'))).count() >= 2:
        raise BusinessProcessingError('Wait for an active analysis to finish (maximum 2)')
    job = EvidenceAnalysis(case_id=case_id, requested_by=user.id, kind=kind, source=source,
                           source_key=key, result={})
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
    if job.kind != 'pcap':
        raise BusinessProcessingError('Analyze Sandbox events in Yuki chat')
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
