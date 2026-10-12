import importlib.util
from pathlib import Path
from starlette.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2] / 'source/app'

def test_permission_migration_preserves_meaning_without_granting_new_nonadmin_rights():
    spec = importlib.util.spec_from_file_location('v3_permissions', ROOT / 'alembic/versions/utmn_v3_permissions01_preserve_v2_permissions.py')
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.translate_mask(0xffff) == 0xfffffff
    assert migration.translate_mask(0x2001) == 0x1001
    assert migration.translate_mask(0x4001) == 0x2001
    assert migration.translate_mask(0x8001) == 0x4001
    assert migration.translate_mask(0x1001) == 0x1001
    assert migration.translate_mask(0x46d) == 0x46d
    assert migration.translate_mask(0x2001) & 0x8000 == 0

def test_response_callbacks_run_before_response_is_sent():
    import sys
    spec = importlib.util.spec_from_file_location('v3_test_web', ROOT / 'web.py')
    web = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = web
    spec.loader.exec_module(web)
    app = web.IRISApp(__name__)
    @app.route('/export')
    def export():
        @web.after_this_request
        def add_header(response):
            response.headers['X-Export-Ready'] = 'yes'
            return response
        return 'data'
    response = TestClient(app).get('/export')
    assert response.status_code == 200
    assert response.headers['X-Export-Ready'] == 'yes'
