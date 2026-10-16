"""One polling request per Celery task; persistent IDs survive worker restarts."""
import datetime as dt
import hashlib
import re
from pathlib import Path

from app import celery
from app.db import db
from app.business.ptsandbox import module_config, client_from_config
from app.business.access_controls import ac_fast_check_user_has_case_access
from app.business.war_rooms_access import ac_fast_check_user_has_war_room_access
from app.datamgmt.datastore.datastore_db import datastore_get_local_file_path
from app.models.authorization import CaseAccessLevel, WarRoomAccessLevel, User
from app.models.sandbox import SandboxScan, SandboxLog
from app.models.war_rooms import WarRoomCase, WarRoomChatMessage
from app.iris_engine.ptsandbox.client import SandboxError, log_references, validate_url, report_summary

MAX_LOG_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024


def _authorized(scan):
    user = db.session.get(User, scan.requested_by) if scan.requested_by else None
    if not user or not user.active:
        return False
    if not ac_fast_check_user_has_case_access(user.id, scan.case_id, [CaseAccessLevel.full_access]):
        return False
    if scan.war_room_id:
        return bool(ac_fast_check_user_has_war_room_access(user.id, scan.war_room_id, [WarRoomAccessLevel.full_access])
                    and WarRoomCase.query.filter_by(war_room_id=scan.war_room_id, case_id=scan.case_id).first())
    return True


def _notify(scan):
    if not scan.war_room_id or scan.notification_id or not _authorized(scan):
        return
    url = f'/case/{scan.case_id}/sandbox?scan={scan.id}'
    logs = SandboxLog.query.with_entities(SandboxLog.error, SandboxLog.size).filter_by(scan_id=scan.id).all()
    available = sum(log.size is not None for log in logs)
    # Message is plain text/Markdown. File names must not inject links or mentions.
    name = scan.file_name.translate(str.maketrans({'[': '_', ']': '_', '\n': ' ', '\r': ' ', '@': '_', '`': '_'}))
    body = (f'PT Sandbox · {name}\nSHA-256: {scan.sha256}\n'
            f'{scan.verdict or scan.status}\nLogs: {available}/{len(logs)}\n'
            f'[Report and original logs]({url})')
    summary = report_summary(scan.report)
    if summary['scan_state']:
        body += '\nAnalysis: ' + re.sub(r'[^A-Z_]', '', str(summary['scan_state']))[:30]
    if summary['detections']:
        body += '\nDetections: ' + ', '.join(re.sub(r'[\[\]`@\r\n]', '_', name) for name in summary['detections'])
    if scan.error:
        body += '\n' + scan.error
    msg = WarRoomChatMessage(war_room_id=scan.war_room_id, author_id=None, kind='system', body=body,
                             ref_type=None, ref_case_id=scan.case_id)
    # Topic may have been removed/archived since submission; deliver to Main.
    db.session.add(msg)
    db.session.flush()
    scan.notification_id = msg.message_id


def _finish(scan, status, error=None):
    scan.status = status
    scan.error = error
    scan.finished_at = scan.updated_at = dt.datetime.utcnow()
    _notify(scan)
    db.session.commit()
    if scan.war_room_id and scan.notification_id:
        try:
            from app import socket_io
            socket_io.emit('message:new', {'message_id': scan.notification_id}, room=f'war_room_{scan.war_room_id}')
        except Exception:
            pass


def _collect(scan, client):
    total = 0
    # A resumed collection atomically replaces its prior attempt.
    SandboxLog.query.filter_by(scan_id=scan.id).delete()
    for index, entry in enumerate(log_references(scan.report)):
        log = SandboxLog(scan_id=scan.id, file_uri=entry['file_uri'], name=entry['file_name'], kind=entry['type'])
        db.session.add(log)
        try:
            if not re.fullmatch(r'sha256:[0-9a-fA-F]{64}', log.file_uri):
                raise SandboxError('Log URI is not a public API SHA-256 reference')
            if index >= 128:
                raise SandboxError('Automatic download limit reached (128 logs); reference retained in report')
            if not _authorized(scan):
                raise SandboxError('Access changed during log collection')
            _, cfg = module_config(scan.module_id)
            if validate_url(cfg['sandbox_url']) != scan.options['url']:
                raise SandboxError('Module address changed; original logs were not downloaded')
            remaining = MAX_TOTAL_BYTES - total
            if remaining <= 0:
                raise SandboxError('Total log size limit reached (256 MiB); original remains in PT Sandbox')
            raw = client.request('storage/downloadArtifact', payload={'file_uri': log.file_uri},
                                 limit=min(MAX_LOG_BYTES, remaining))
            if hashlib.sha256(raw).hexdigest() != log.file_uri.split(':', 1)[1].lower():
                raise SandboxError('Downloaded log hash does not match the report reference')
            log.content, log.size = raw, len(raw)
            log.sha256 = hashlib.sha256(raw).hexdigest()
            total += len(raw)
        except SandboxError as exc:
            log.error = str(exc)
    db.session.flush()
    failed = SandboxLog.query.filter_by(scan_id=scan.id).filter(SandboxLog.error.isnot(None)).count()
    state = str((scan.report.get('result') or {}).get('scan_state') or 'UNKNOWN')
    errors = []
    if failed:
        errors.append(f'{failed} log(s) could not be downloaded; see individual errors')
    if state != 'FULL':
        errors.append('Sandbox analysis state: ' + re.sub(r'[^A-Z_]', '', state)[:30])
    _finish(scan, 'partial' if errors else 'completed', '; '.join(errors) or None)


@celery.task(name='iris.ptsandbox.process', acks_late=True, reject_on_worker_lost=True)
def process_scan(identifier):
    scan = SandboxScan.query.filter_by(id=identifier).with_for_update(skip_locked=True).first()
    if not scan or scan.status not in ('queued', 'running', 'collecting'):
        return
    client = None
    try:
        if not _authorized(scan):
            raise SandboxError('Requesting user no longer has access')
        _, cfg = module_config(scan.module_id)
        if validate_url(cfg['sandbox_url']) != scan.options['url']:
            raise SandboxError('Module address changed; check cannot continue against another appliance')
        client = client_from_config(cfg)
        if scan.status == 'queued':
            checked = client.check_connection()
            if not checked['version_matches']:
                raise SandboxError('Expected PT Sandbox 5.37')
            error, file = datastore_get_local_file_path(scan.file_id, scan.case_id)
            if error:
                raise SandboxError('Source file is no longer available')
            path = Path(file.file_local_name)
            if not path.is_file() or path.stat().st_size > int(cfg['max_file_mb']) * 1024 * 1024:
                raise SandboxError('Source file is missing or exceeds size limit')
            with path.open('rb') as source:
                if hashlib.file_digest(source, 'sha256').hexdigest() != scan.sha256:
                    raise SandboxError('Source file changed after submission')
                source.seek(0)
                scan.status = 'uploading'
                scan.updated_at = dt.datetime.utcnow()
                db.session.commit()
                uri = client.upload(source)
            # Never automatically repeat this request after an ambiguous response.
            scan.status = 'submitting'
            scan.updated_at = dt.datetime.utcnow()
            db.session.commit()
            scan.scan_id = client.start(uri, scan.file_name, scan.options['image_id'],
                                       scan.options['analysis_duration'],
                                       [file.file_password or 'infected'] if file.file_is_ioc or file.file_password else [])
            scan.status = 'running'
            scan.updated_at = dt.datetime.utcnow()
            db.session.commit()
            process_scan.apply_async(args=[scan.id], countdown=30)
            return
        wait_start = dt.datetime.fromisoformat(scan.options['wait_started_at']) if scan.options.get('wait_started_at') else scan.created_at
        if dt.datetime.utcnow() - wait_start > dt.timedelta(hours=6):
            raise SandboxError('Analysis wait exceeded 6 hours; use Resume to fetch the existing task')
        if scan.status == 'running':
            status = client.request('analysis/checkTask', payload={'scan_id': scan.scan_id, 'allow_preflight': False})
            if not status.get('result') or status.get('is_preflight'):
                scan.updated_at = dt.datetime.utcnow()
                db.session.commit()
                process_scan.apply_async(args=[scan.id], countdown=30)
                return
            report = client.request('analysis/report', payload={'scan_id': scan.scan_id})
            if not isinstance(report.get('result'), dict):
                raise SandboxError('PT Sandbox detailed report is not ready')
            scan.report = report
            scan.verdict = str(report['result'].get('verdict') or 'unknown')[:120]
            scan.status = 'collecting'
        # Keep the row lock across log downloads so duplicate tasks cannot publish twice.
        _collect(scan, client)
    except SandboxError as exc:
        _finish(scan, 'submission_unknown' if scan.status == 'submitting' else 'failed', str(exc))
    except Exception:
        was_submitting = scan.status == 'submitting'
        db.session.rollback()
        scan = db.session.get(SandboxScan, identifier)
        if scan:
            _finish(scan, 'submission_unknown' if was_submitting else 'failed', 'PT Sandbox task failed; no automatic resubmission')
    finally:
        if client:
            client.close()
        db.session.rollback()


@celery.task(name='iris.ptsandbox.recover')
def recover_scans():
    cutoff = dt.datetime.utcnow() - dt.timedelta(minutes=10)
    rows = SandboxScan.query.filter(SandboxScan.status.in_(('queued', 'uploading', 'submitting', 'running', 'collecting')),
                                    SandboxScan.updated_at < cutoff).with_for_update(skip_locked=True).all()
    queued = []
    for scan in rows:
        if scan.status == 'submitting':
            _finish(scan, 'submission_unknown', 'Worker stopped during submission; verify the task in PT Sandbox before a new check')
        else:
            if scan.status == 'uploading':
                scan.status = 'queued'
            scan.updated_at = dt.datetime.utcnow()
            queued.append(scan.id)
    db.session.commit()
    for identifier in queued:
        process_scan.delay(identifier)


celery.conf.beat_schedule['ptsandbox-recover'] = {'task': 'iris.ptsandbox.recover', 'schedule': 60.0}
