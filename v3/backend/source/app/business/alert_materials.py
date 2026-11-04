"""Alert-owned investigation materials and their audit trail."""
from datetime import datetime
from pathlib import Path
import uuid

from app.db import db
from app.web import current_app
from app.business.alert_materials_validation import validate_artifact, write_upload
from app.models.alert_artifacts import AlertArtifact
from app.models.errors import ObjectNotFoundError
from app.models.errors import BusinessProcessingError
from app.iris_engine.utils.tracker import track_activity
from app.util import add_obj_history_entry


def artifact_path(row):
    root = Path(current_app.config.get('DATASTORE_PATH', '/home/iris/server_data/datastore'))
    return root / 'alerts' / str(row.alert_id) / row.storage_name


def material_history(alert, action):
    add_obj_history_entry(alert, action)
    # track_activity commits the material and both history records together.
    track_activity(f'{action} of alert #{alert.alert_id}', ctx_less=True)


def get_artifact(alert, identifier):
    row = AlertArtifact.query.filter_by(alert_id=alert.alert_id, id=identifier).first()
    if row is None:
        raise ObjectNotFoundError()
    return row


def create_artifact(alert, user_id, payload, upload=None):
    path = None
    if not isinstance(payload, dict):
        raise ValueError('Expected an object')
    include_in_case = _include_in_case(payload)
    if upload is None:
        data = validate_artifact(payload)
    else:
        filename = (upload.filename or '').replace('\\', '/').split('/')[-1].strip()
        description = payload.get('description', '')
        if not filename or filename in ('.', '..') or len(filename) > 512 or any(ord(c) < 32 for c in filename):
            raise ValueError('Invalid filename')
        if not isinstance(description, str) or len(description) > 65536:
            raise ValueError('Invalid artifact description')
        data = {'kind': 'file', 'value': filename, 'description': description,
                'storage_name': uuid.uuid4().hex}
    row = AlertArtifact(alert_id=alert.alert_id, created_by_id=user_id,
                        include_in_case=include_in_case, **data)
    try:
        if upload is not None:
            path = artifact_path(row)
            path.parent.mkdir(parents=True, exist_ok=True)
            row.size_bytes, row.sha256 = write_upload(upload.stream, path)
        db.session.add(row)
        db.session.flush()
        material_history(alert, f'added artifact #{row.id}')
    except Exception:
        db.session.rollback()
        if path is not None:
            path.unlink(missing_ok=True)
        raise
    return row


def update_artifact(alert, row, user_id, payload):
    include_in_case = _include_in_case(payload, default=row.include_in_case)
    if row.kind == 'file':
        payload = validate_artifact({'kind': 'other', 'value': row.value,
                                     'description': payload.get('description', '')})
        row.description = payload['description']
    else:
        for key, value in validate_artifact(payload).items():
            setattr(row, key, value)
    row.updated_at = datetime.utcnow()
    row.include_in_case = include_in_case
    row.updated_by_id = user_id
    material_history(alert, f'updated artifact #{row.id}')
    return row


def delete_artifact(alert, row):
    path = artifact_path(row) if row.storage_name else None
    identifier = row.id
    db.session.delete(row)
    material_history(alert, f'deleted artifact #{identifier}')
    if path is not None:
        path.unlink(missing_ok=True)


def _include_in_case(payload, default=True):
    value = payload.get('include_in_case', default)
    if isinstance(value, str) and value in ('true', 'false'):
        return value == 'true'
    if type(value) is not bool:
        raise ValueError('Invalid include_in_case value')
    return value


def export_artifacts_to_case(alert, case, user_id):
    """Copy selected materials into the case datastore; deleting the alert cannot remove case files."""
    import hashlib
    import shutil
    from app.datamgmt.datastore.datastore_db import datastore_get_root, datastore_get_standard_path
    from app.models.models import DataStoreFile

    selected = [row for row in alert.artifacts if row.include_in_case]
    if not selected:
        return
    require_artifact_import_access(alert, case, user_id)
    root = datastore_get_root(case.case_id)
    paths = []
    try:
        for row in selected:
            tag = f'alert-{alert.alert_id}-artifact-{row.id}'
            if DataStoreFile.query.filter_by(file_case_id=case.case_id, file_tags=tag).first():
                continue
            item = DataStoreFile(
                file_uuid=uuid.uuid4(), file_original_name=row.value if row.kind == 'file' else f'{row.kind}-{row.id}.txt',
                file_description=f'Alert #{alert.alert_id}, {row.kind}\n{row.description}',
                file_tags=tag, file_date_added=datetime.utcnow(), file_is_ioc=False, file_is_evidence=False,
                file_parent_id=root.path_id, file_case_id=case.case_id, added_by_user_id=user_id,
                file_local_name='',
            )
            path = datastore_get_standard_path(item, case.case_id)
            paths.append(path)
            if row.kind == 'file':
                shutil.copyfile(artifact_path(row), path)
                item.file_size, item.file_sha256 = row.size_bytes, row.sha256
            else:
                content = f'{row.kind}: {row.value}\n\n{row.description}\n'.encode('utf-8')
                path.write_bytes(content)
                item.file_size = len(content)
                item.file_sha256 = hashlib.sha256(content).hexdigest()
            item.file_local_name = str(path)
            db.session.add(item)
        add_obj_history_entry(case, f'imported artifacts from alert #{alert.alert_id}')
        material_history(alert, f'copied artifacts to case #{case.case_id}')
    except Exception:
        db.session.rollback()
        for path in paths:
            path.unlink(missing_ok=True)
        raise


def require_artifact_import_access(alert, case, user_id):
    from app.business.access_controls import ac_fast_check_user_has_case_access
    from app.models.authorization import CaseAccessLevel
    if any(row.include_in_case for row in alert.artifacts) and not ac_fast_check_user_has_case_access(
            user_id, case.case_id, [CaseAccessLevel.full_access]):
        raise BusinessProcessingError('Full case access is required to import artifacts')
