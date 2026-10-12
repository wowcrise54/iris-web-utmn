# IRIS 2.4.29 isolated acceptance

Always use `-p iris-upgrade-2-4-29-fastapi` and this compose file. The app binds localhost 18082, nginx 18543. Only new project-prefixed volumes are used. Public credentials in public.env are solely for this isolated database.

```
python tests/upgrade_2_4_29/prepare_stack.py
docker compose -p iris-upgrade-2-4-29-fastapi -f docker-compose.upgrade-validation.yml up --build -d
python tests/upgrade_2_4_29/run_official_suite.py --url http://localhost:18082 --output tests/upgrade_2_4_29/runtime/official-fastapi.json
python tests/upgrade_2_4_29/probe_http.py --http http://localhost:18082 --https https://localhost:18543 --output tests/upgrade_2_4_29/runtime/http-fastapi.json
```

Official source tests are loaded unchanged from D:/Diplom/iris-upstream-2.4.29/tests. The runner replaces only test harness start/stop and constructor: upstream lifecycle copies over .env and uses an unsafe default compose project. Port guard permits only 18082/18083. Upstream has four active tests and one skipped clean-slate example; there is no GraphQL or APIv2 suite in this release.

Optional reference: compose.flask.yml overrides image/build with an external official Dockerfile copy. Only shell line endings are normalized. Set UPGRADE_HTTP_PORT=18083 and UPGRADE_HTTPS_PORT=18544 before using project iris-upgrade-2-4-29-flask. Never reuse primary project names or volumes.
