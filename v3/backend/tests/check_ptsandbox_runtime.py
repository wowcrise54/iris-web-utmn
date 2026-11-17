"""Read-only module loading and anonymous access checks in an IRIS container."""
from app import app
from app.business.ptsandbox import prepare_parameter, public_config
from app.iris_engine.mail.secrets import decrypt_secret
from app.iris_engine.module_handler.module_handler import check_module_health
from app.blueprints.rest.v2.mcp.registry import TOOL_REGISTRY
from app.blueprints.rest.v2.mcp.classification import is_read_only
from iris_ptsandbox_module.IrisPTSandboxInterface import IrisPTSandboxInterface


def main():
    with app.app_context():
        ready, _ = check_module_health(IrisPTSandboxInterface())
        assert ready, 'Module interface failed validation'
        stored = prepare_parameter('sandbox_token', 'non-secret-runtime-fixture')
        assert decrypt_secret(stored) == 'non-secret-runtime-fixture'
        assert public_config([{'param_name': 'sandbox_token', 'value': stored}])[0]['value'] == ''
        names = sorted(n for n in TOOL_REGISTRY if 'sandbox' in n)
        assert len(names) == 3
        assert all(TOOL_REGISTRY[n].case_scoped and is_read_only(n) for n in names)
    client = app.test_client()
    for method, path in (('get', '/api/v2/cases/2/sandbox'), ('post', '/api/v2/cases/2/sandbox'),
                         ('get', '/api/v2/cases/2/sandbox/1'), ('post', '/api/v2/manage/modules/1/check-connection'),
                         ('get', '/api/v2/cases/2/sandbox/1/logs/1')):
        response = getattr(client, method)(path)
        assert response.status_code in (401, 403), (path, response.status_code)
    print('PT Sandbox runtime: module health, encrypted/redacted token, scoped read tools and anonymous ACL passed')


if __name__ == '__main__':
    main()
