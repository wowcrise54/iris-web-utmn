"""Case-scoped sandbox operations, secrets and bounded log reading."""
import copy
import datetime as dt
import gzip
import hashlib
import io
from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import defer
from app.db import db
from app.models.models import IrisModule
from app.models.sandbox import SandboxScan, SandboxLog
from app.models.war_rooms import WarRoomCase
from app.models.errors import BusinessProcessingError
from app.iris_engine.mail.secrets import encrypt_secret, decrypt_secret
from app.iris_engine.ptsandbox.client import SandboxClient, SandboxError, validate_url, report_summary
from app.datamgmt.datastore.datastore_db import datastore_get_local_file_path

MODULE = 'iris_ptsandbox_module'
ACTIVE = ('queued', 'uploading', 'submitting', 'running', 'collecting', 'submission_unknown')


def module_config(module_id=None, *, active=True, require_image=True):
    query = IrisModule.query.filter_by(module_name=MODULE)
    row = query.filter_by(id=module_id).first() if module_id else query.order_by(IrisModule.id).first()
    if not row or (active and not row.is_active):
        raise SandboxError('PT Sandbox module is not enabled')
    cfg = {p['param_name']: p.get('value', p.get('default')) for p in row.module_config or []}
    cfg['sandbox_token'] = decrypt_secret(cfg.get('sandbox_token'))
    validate_url(cfg.get('sandbox_url'))
    if not cfg['sandbox_token']:
        raise SandboxError('PT Sandbox token is not configured')
    if require_image and not cfg.get('image_id'):
        raise SandboxError('PT Sandbox VM image ID is required')
    return row, cfg


def client_from_config(cfg):
    return SandboxClient(cfg.get('sandbox_url'), cfg.get('sandbox_token'), cfg.get('ca_bundle'))


def prepare_parameter(name, value, existing=None):
    if name == 'sandbox_token':
        if value in (None, '', '********') and existing:
            return existing
        if not isinstance(value, str) or not value.strip() or '\r' in value or '\n' in value:
            raise BusinessProcessingError('API token is required')
        return encrypt_secret(value.strip())
    try:
        if name == 'sandbox_url':
            validate_url(value)
        elif name in ('analysis_duration', 'max_file_mb'):
            lower, upper = (10, 600) if name == 'analysis_duration' else (1, 512)
            if isinstance(value, bool) or not lower <= int(value) <= upper:
                raise ValueError()
            value = str(int(value))
        elif name == 'image_id' and (not isinstance(value, str) or not value.strip() or len(value) > 200):
            raise ValueError()
        elif name == 'ca_bundle' and value and (not isinstance(value, str) or not Path(value).is_file()):
            raise SandboxError('CA file is not available on the application server')
    except (SandboxError, ValueError, TypeError, OSError) as exc:
        raise BusinessProcessingError(str(exc) or 'Invalid PT Sandbox parameter') from None
    return value


def public_config(parameters):
    out = copy.deepcopy(parameters or [])
    for p in out:
        if p['param_name'] == 'sandbox_token':
            p['has_value'] = bool(p.get('value'))
            p['value'] = ''
    return out


def connection_check(module_id):
    row, cfg = module_config(module_id, active=False, require_image=False)
    client = client_from_config(cfg)
    result = {'checked_at': dt.datetime.utcnow().isoformat(), 'target_version': '5.37'}
    try:
        result.update(client.check_connection())
        result['ok'] = result['version_matches'] and result['health'].lower() in ('ok', 'healthy', 'good')
        if not result['version_matches']:
            result['error'] = 'Expected PT Sandbox 5.37; check the appliance address/version'
    except SandboxError as exc:
        result.update(ok=False, error=str(exc))
    finally:
        client.close()
    # Store only a bounded non-secret status, not model bodies or credentials.
    config = copy.deepcopy(row.module_config or [])
    for p in config:
        if p['param_name'] == 'sandbox_url':
            p['connection_check'] = {k: v for k, v in result.items() if k != 'images'}
    row.module_config = config
    db.session.commit()
    return result


def projection(scan, detail=False):
    result = {key: getattr(scan, key) for key in ('id', 'case_id', 'file_id', 'war_room_id', 'file_name',
              'sha256', 'status', 'scan_id', 'verdict', 'error', 'notification_id')}
    result['source_url'] = f'/case/{scan.case_id}/sandbox?scan={scan.id}'
    for key in ('created_at', 'updated_at', 'finished_at'):
        value = getattr(scan, key)
        result[key] = value.isoformat() + 'Z' if value else None
    if detail:
        result['report'] = scan.report
        result['summary'] = report_summary(scan.report)
        result['logs'] = [{'id': log.id, 'name': log.name, 'kind': log.kind, 'size': log.size,
                           'sha256': log.sha256, 'error': log.error}
                          for log in SandboxLog.query.options(defer(SandboxLog.content)).filter_by(scan_id=scan.id).order_by(SandboxLog.id)]
    return result


def get_scan(case_id, scan_id):
    scan = SandboxScan.query.filter_by(case_id=case_id, id=scan_id).first()
    if not scan:
        raise LookupError('Unknown sandbox check')
    return scan


def list_scans(case_id, limit=50, before=None):
    query = SandboxScan.query.options(defer(SandboxScan.report)).filter_by(case_id=case_id)
    if before:
        query = query.filter(SandboxScan.id < before)
    rows = query.order_by(SandboxScan.id.desc()).limit(limit).all()
    return [projection(s) for s in rows]


def start_scan(case_id, file_id, user_id, *, confirmed=False, war_room_id=None, topic_id=None):
    if confirmed is not True:
        raise BusinessProcessingError('Confirm sending this file to PT Sandbox')
    try:
        module, cfg = module_config()
    except SandboxError as exc:
        raise BusinessProcessingError(str(exc)) from None
    # A connection check proves the target product version before any sample leaves IRIS.
    checked = next((p.get('connection_check') for p in module.module_config or []
                    if p['param_name'] == 'sandbox_url'), None)
    if not checked or not checked.get('ok'):
        raise BusinessProcessingError('Administrator must check the PT Sandbox 5.37 connection first')
    error, file = datastore_get_local_file_path(file_id, case_id)
    if error or not Path(file.file_local_name).is_file():
        raise BusinessProcessingError('File is not available in this case')
    if war_room_id and not WarRoomCase.query.filter_by(war_room_id=war_room_id, case_id=case_id).first():
        raise BusinessProcessingError('The case is not linked to this war room')
    path = Path(file.file_local_name)
    if path.stat().st_size > int(cfg['max_file_mb']) * 1024 * 1024:
        raise BusinessProcessingError('File exceeds the module size limit')
    with path.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    name = file.file_original_name + ('.zip' if file.file_is_ioc or file.file_password else '')
    scan = SandboxScan(case_id=case_id, file_id=file_id, module_id=module.id, requested_by=user_id,
                       war_room_id=war_room_id, topic_id=topic_id, file_name=name, sha256=digest,
                       options={'url': validate_url(cfg['sandbox_url']), 'image_id': cfg['image_id'],
                                'analysis_duration': int(cfg['analysis_duration'])}, status='queued')
    try:
        db.session.add(scan)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise BusinessProcessingError('An active or unresolved check already exists for this file') from None
    from app.iris_engine.ptsandbox.tasks import process_scan
    try:
        process_scan.delay(scan.id)
    except Exception:
        # Persistent queued rows are also recovered by the periodic worker task.
        pass
    return projection(scan)


def read_log(case_id, scan_id, log_id):
    get_scan(case_id, scan_id)
    log = SandboxLog.query.filter_by(scan_id=scan_id, id=log_id).first()
    if not log:
        raise LookupError('Unknown sandbox log')
    return log


def text_page(log, offset=0, length=12000):
    if log.content is None:
        raise BusinessProcessingError(log.error or 'Log is not available')
    raw = log.content
    cap = 16 * 1024 * 1024
    # Decompress only a bounded prefix; never extract archives to disk.
    try:
        if raw.startswith(b'\x1f\x8b'):
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
                raw = stream.read(cap + 1)
        elif raw.startswith(b'\x28\xb5\x2f\xfd'):
            import zstandard
            with zstandard.ZstdDecompressor().stream_reader(io.BytesIO(raw)) as stream:
                raw = stream.read(cap + 1)
    except Exception:
        raise BusinessProcessingError('Unable to decode this compressed log; download the original') from None
    if b'\x00' in raw[:4096] or raw[:4] in (b'\xd4\xc3\xb2\xa1', b'\x0a\x0d\x0d\x0a', b'PK\x03\x04'):
        raise BusinessProcessingError('Binary log: download the original; textual analysis is unavailable')
    decoded = raw[:cap].decode('utf-8', errors='replace')
    return {'log_id': log.id, 'name': log.name, 'offset': offset, 'text': decoded[offset:offset + length],
            'next_offset': offset + length if offset + length < len(decoded) else None,
            'truncated': len(raw) > cap, 'untrusted_data': True}
