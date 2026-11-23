"""Case-scoped sandbox operations, secrets and bounded log reading."""
import copy
import datetime as dt
from uuid import UUID
from sqlalchemy import func, select
from pathlib import Path

from sqlalchemy.orm import defer
from app.db import db
from app.iris_engine.evidence.text import text_chunks, BinaryLogError
from app.models.models import IrisModule
from app.models.sandbox import SandboxScan, SandboxLog
from app.models.errors import BusinessProcessingError
from app.iris_engine.mail.secrets import encrypt_secret, decrypt_secret
from app.iris_engine.ptsandbox.client import SandboxClient, SandboxError, validate_url, report_summary, parse_verify_tls

MODULE = 'iris_ptsandbox_module'


def module_config(module_id=None, *, active=True):
    query = IrisModule.query.filter_by(module_name=MODULE)
    row = query.filter_by(id=module_id).first() if module_id else query.order_by(IrisModule.id).first()
    if not row or (active and not row.is_active):
        raise SandboxError('PT Sandbox module is not enabled')
    cfg = {p['param_name']: p.get('value', p.get('default')) for p in row.module_config or []}
    cfg['sandbox_token'] = decrypt_secret(cfg.get('sandbox_token'))
    validate_url(cfg.get('sandbox_url'))
    if not cfg['sandbox_token']:
        raise SandboxError('PT Sandbox token is not configured')
    if cfg.get('database') not in ('scans_v2', 'scans_v2_repl'):
        raise SandboxError('Configure the PT Sandbox MCP database')
    return row, cfg


def client_from_config(cfg):
    return SandboxClient(cfg.get('sandbox_url'), cfg.get('sandbox_token'), cfg.get('ca_bundle'),
                         verify_tls=cfg.get('verify_tls', True))


def sync_module_parameters():
    """Update stored parameter definitions and clear obsolete REST credentials."""
    from iris_ptsandbox_module.IrisPTSandboxInterface import IrisPTSandboxInterface
    interface = IrisPTSandboxInterface
    version = interface._module_version
    for row in IrisModule.query.filter_by(module_name=MODULE):
        if row.module_version == version:
            continue
        old = {p['param_name']: p.get('value', p.get('default')) for p in row.module_config or []}
        row.module_config = [
            {**p, 'value': old.get(p['param_name'], p['default'])
             if p['param_name'] in ('verify_tls', 'ca_bundle') else p['default']}
            for p in interface._module_configuration
        ]
        row.module_description = interface._module_description
        row.module_version = version
        row.is_active = False
    db.session.commit()


def prepare_parameter(name, value, existing=None):
    if name == 'sandbox_token':
        if value in (None, '', '********') and existing:
            return existing
        if not isinstance(value, str) or not value.strip() or '\r' in value or '\n' in value:
            raise BusinessProcessingError('MCP token is required')
        return encrypt_secret(value.strip())
    try:
        if name == 'verify_tls':
            value = parse_verify_tls(value)
        elif name == 'sandbox_url':
            validate_url(value)
        elif name == 'database' and value not in ('scans_v2', 'scans_v2_repl'):
            raise SandboxError('Use scans_v2 or scans_v2_repl')
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
    row, cfg = module_config(module_id, active=False)
    client = client_from_config(cfg)
    result = {'checked_at': dt.datetime.now(dt.UTC).isoformat(), 'target_version': '5.39', 'transport': 'mcp'}
    try:
        result.update(client.check_connection(cfg['database']))
    except SandboxError as exc:
        result.update(ok=False, error=str(exc))
    finally:
        client.close()
    # Store only a bounded non-secret status, not model bodies or credentials.
    config = copy.deepcopy(row.module_config or [])
    for p in config:
        if p['param_name'] == 'sandbox_url':
            p['connection_check'] = result
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
        if scan.options.get('transport') == 'mcp':
            result['remote_task'] = (scan.report or {}).get('task')
            result['mcp_started_at'] = scan.options.get('started_at')
            behavior = (scan.report or {}).get('behavioral_events')
            if behavior:
                result['behavioral_events'] = {'total': behavior['total'],
                    'included': len(behavior['events']), 'truncated': behavior['truncated']}
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


def checked_module_config():
    module, cfg = module_config()
    checked = next((p.get('connection_check') for p in module.module_config or []
                    if p['param_name'] == 'sandbox_url'), None)
    if not checked or not checked.get('ok') or checked.get('transport') != 'mcp':
        raise SandboxError('Administrator must verify the PT Sandbox MCP connection first')
    return module, cfg


def search_tasks(name, days):
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 255:
        raise BusinessProcessingError('Enter a file name of up to 255 characters')
    try:
        _, cfg = checked_module_config()
        client = client_from_config(cfg)
        try:
            client.connect()
            rows = client.query(client.search_sql(cfg['database'], name.strip(), days))
        finally:
            client.close()
        return [{**row, 'started_at': row['started_utc'].replace(' ', 'T') + 'Z'} for row in rows]
    except (SandboxError, KeyError, AttributeError) as exc:
        message = str(exc) if isinstance(exc, SandboxError) else 'Invalid PT Sandbox search response'
        raise BusinessProcessingError(message) from None


def import_scan(case_id, scan_id, started_at, user_id, *, include_events=False):
    try:
        if not isinstance(scan_id, str) or not isinstance(started_at, str):
            raise ValueError
        scan_id = str(UUID(scan_id))
        # ClickHouse stores the sorting key at second precision.
        start = dt.datetime.strptime(started_at, '%Y-%m-%dT%H:%M:%SZ')
        if start.strftime('%Y-%m-%dT%H:%M:%SZ') != started_at:
            raise ValueError
    except ValueError:
        raise BusinessProcessingError('Provide a task UUID and UTC start time YYYY-MM-DDTHH:MM:SSZ') from None
    try:
        module, cfg = checked_module_config()
        client = client_from_config(cfg)
        try:
            client.connect()
            rows = client.query(client.task_sql(cfg['database'], scan_id, start))
            if not rows:
                raise SandboxError('PT Sandbox task not found at that UTC start time')
            row = rows[0]
            if len(rows) != 1 or row.get('sid') != scan_id or row.get('verdict_is_final') not in (0, 1):
                raise SandboxError('PT Sandbox returned an invalid task summary')
            behavior = client.task_events(cfg['database'], scan_id, start) if include_events else None
        finally:
            client.close()
    except SandboxError as exc:
        raise BusinessProcessingError(str(exc)) from None

    source = {'transport': 'mcp', 'url': client.url, 'database': cfg['database'], 'started_at': started_at}
    # Serialize writes for this imported task so concurrent retries reuse the case record.
    key = f'ptsandbox:{case_id}:{client.url}:{cfg["database"]}:{started_at}:{scan_id}'
    db.session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(key, 0))))
    scan = next((item for item in SandboxScan.query.filter_by(case_id=case_id, scan_id=scan_id)
                 if item.options == source), None)
    if scan is None:
        scan = SandboxScan(case_id=case_id, module_id=module.id, requested_by=user_id,
                           scan_id=scan_id, options=source)
        db.session.add(scan)
    final = bool(row['verdict_is_final'])
    if scan.status != 'completed' or final:
        scan.file_name = str(row.get('object_name') or scan_id)[:512]
        scan.status = 'completed' if final else 'preliminary'
        scan.verdict = str(row.get('verdict') or 'UNKNOWN')[:120]
        scan.report = {**(scan.report or {}), 'source': 'mcp', 'task': row}
        scan.updated_at = dt.datetime.now(dt.UTC).replace(tzinfo=None)
        scan.finished_at = (scan.finished_at or scan.updated_at) if final else None
    if behavior is not None:
        scan.report = {**scan.report, 'behavioral_events': behavior}
    db.session.commit()
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
    state, parts, position = {}, [], 0
    wanted = max(0, int(offset))
    length = min(12000, max(1, int(length)))
    stream = text_chunks(bytes(log.content), state)
    try:
        for chunk in stream:
            end = position + len(chunk)
            if end > wanted:
                parts.append(chunk[max(0, wanted - position):max(0, wanted + length + 1 - position)])
            position = end
            if position > wanted + length:
                break
    except BinaryLogError:
        raise BusinessProcessingError('Binary log: download the original; textual analysis is unavailable') from None
    except Exception:
        raise BusinessProcessingError('Unable to decode this log; download the original') from None
    finally:
        stream.close()
    text = ''.join(parts)
    return {'log_id': log.id, 'name': log.name, 'offset': wanted, 'text': text[:length],
            'next_offset': wanted + length if len(text) > length else None,
            'truncated': state.get('truncated', False), 'untrusted_data': True}
