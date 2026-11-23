"""Settle legacy queued REST checks after switching the module to MCP."""
import datetime as dt

from app.db import db
from app.models.sandbox import SandboxScan
from app import celery


LEGACY_ACTIVE = ('queued', 'uploading', 'submitting', 'running', 'collecting')


def _retire(scan):
    scan.status = 'submission_unknown' if scan.status == 'submitting' else 'failed'
    scan.error = 'Legacy PT Sandbox check interrupted by the MCP upgrade'
    scan.finished_at = scan.updated_at = dt.datetime.now(dt.UTC).replace(tzinfo=None)


@celery.task(name='iris.ptsandbox.process', acks_late=True, reject_on_worker_lost=True)
def process_scan(identifier):
    scan = SandboxScan.query.filter_by(id=identifier).with_for_update().first()
    if scan and scan.status in LEGACY_ACTIVE:
        _retire(scan)
    db.session.commit()


@celery.task(name='iris.ptsandbox.recover')
def recover_scans():
    scans = SandboxScan.query.filter(SandboxScan.status.in_(LEGACY_ACTIVE)).with_for_update(skip_locked=True).all()
    for scan in scans:
        _retire(scan)
    db.session.commit()


celery.conf.beat_schedule['ptsandbox-recover'] = {'task': 'iris.ptsandbox.recover', 'schedule': 60.0}
