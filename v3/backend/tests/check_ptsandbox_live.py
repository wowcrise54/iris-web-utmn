"""Read-only deployment smoke. Reads the local administrator key without printing it."""
from pathlib import Path
from types import SimpleNamespace
import requests
import zstandard

from app import app
from app.models.authorization import User, Permissions
from app.iris_engine.access_control.utils import ac_get_effective_permissions_of_user
from app.models.models import DataStoreFile
from app.models.sandbox import SandboxScan
from app.business.ptsandbox import text_page


def main():
    compressed = zstandard.ZstdCompressor().compress(b'bounded zstd runtime fixture')
    assert text_page(SimpleNamespace(content=compressed, name='trace.zst', id=1))['text'] == 'bounded zstd runtime fixture'
    with app.app_context():
        user = next(u for u in User.query.filter_by(active=True).order_by(User.id)
                    if ac_get_effective_permissions_of_user(u) & Permissions.server_administrator.value)
        token = user.api_key
        source = DataStoreFile.query.order_by(DataStoreFile.file_id).first()
        file_info = (source.file_case_id, source.file_id, Path(source.file_local_name).stat().st_size) if source else None
        assert SandboxScan.query.count() == 0, 'Unexpected live checks exist before setup'
    session = requests.Session()
    session.trust_env = False
    base = 'http://127.0.0.1:8000/api/v2'
    assert session.get(base + '/cases/2/sandbox', timeout=20).status_code == 401
    session.headers['X-IRIS-AUTH'] = token
    modules = session.get(base + '/manage/modules?per_page=200', timeout=20)
    assert modules.status_code == 200
    row = next((m for m in modules.json()['data'] if m['module_human_name'] == 'PT Sandbox'), None)
    assert row and row['is_active'] is False, 'Sandbox must be present and disabled before setup'
    detail = session.get(base + f'/manage/modules/{row["id"]}', timeout=20).json()
    parameter = next(p for p in detail['module_config'] if p['param_name'] == 'sandbox_token')
    assert parameter['value'] == '' and parameter['has_value'] is False
    checks = session.get(base + '/cases/2/sandbox', timeout=20)
    assert checks.status_code == 200 and checks.json()['checks'] == [] and checks.json()['enabled'] is False
    missing = session.get(base + '/cases/2/sandbox/99999999', timeout=20)
    assert missing.status_code == 404
    refused = session.post(base + '/cases/2/sandbox', json={'file_id': 1, 'confirmed': False}, timeout=20)
    assert refused.status_code == 400
    if file_info:
        case_id, file_id, size = file_info
        preview = session.get(base + f'/cases/{case_id}/sandbox/files/{file_id}/submission-info', timeout=20)
        assert preview.status_code == 200 and preview.json()['size'] == size
    catalog = session.get(base + '/manage/server/mcp/tools', timeout=20)
    assert catalog.status_code == 200
    print('Live API: module registered disabled, token redacted, case history and stored-file preview work; unauthenticated/invalid requests rejected')
    print('No file was sent to an external appliance and no Yuki provider call was made')


if __name__ == '__main__':
    main()
