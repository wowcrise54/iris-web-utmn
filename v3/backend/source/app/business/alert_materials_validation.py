"""Validation shared by alert material operations; no application bootstrap."""
import hashlib

ARTIFACT_KINDS = ('process', 'command', 'path', 'registry', 'other')
MAX_FILE_BYTES = 200 * 1024 * 1024


def is_alert_owner(alert, user_id):
    return user_id is not None and alert.alert_owner_id == user_id


def validate_artifact(payload):
    if not isinstance(payload, dict) or payload.get('kind') not in ARTIFACT_KINDS:
        raise ValueError('Invalid artifact type')
    value = payload.get('value')
    description = payload.get('description', '')
    if not isinstance(value, str) or not value.strip() or len(value) > 65536:
        raise ValueError('Artifact value is required (maximum 65536 characters)')
    if not isinstance(description, str) or len(description) > 65536:
        raise ValueError('Invalid artifact description')
    return {'kind': payload['kind'], 'value': value.strip(), 'description': description}


def write_upload(stream, path, limit=MAX_FILE_BYTES):
    digest = hashlib.sha256()
    size = 0
    try:
        with open(path, 'xb') as target:
            while chunk := stream.read(64 * 1024):
                size += len(chunk)
                if size > limit:
                    raise ValueError('File exceeds the 200 MiB limit')
                digest.update(chunk)
                target.write(chunk)
    except FileExistsError:
        raise
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return size, digest.hexdigest()
