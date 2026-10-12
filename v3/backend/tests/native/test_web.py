"""Behavioral regression tests for the native ASGI handler adapter.

Load the module in isolation: database/bootstrap side effects do not belong to
the HTTP adapter's unit tests.
"""
import asyncio
import importlib.util
import io
import os
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def web():
    path = Path(__file__).parents[2] / "source" / "app" / "web.py"
    assert path.exists(), "The native app.web HTTP adapter has not been implemented"
    spec = importlib.util.spec_from_file_location("iris_test_web", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def app(web, tmp_path):
    app = web.IRISApp("iris_test_web", fs_root_path=str(tmp_path), static_folder=None)
    app.config.update(SECRET_KEY="migration-test-secret", TESTING=True)
    return app


def test_blueprint_nested_routes_converters_and_endpoint_urls(web, app):
    parent = web.Blueprint("api", __name__, url_prefix="/api/v2")
    child = web.Blueprint("cases", __name__, url_prefix="/cases")

    @child.route("/<int:case_id>/<uuid:identifier>")
    def detail(case_id, identifier):
        assert isinstance(case_id, int)
        assert isinstance(identifier, uuid.UUID)
        return {"case": case_id, "url": web.url_for(".detail", case_id=case_id, identifier=identifier, q="a b")}

    parent.register_blueprint(child)
    app.register_blueprint(parent)
    result = app.test_client().get("/api/v2/cases/42/01234567-89ab-cdef-0123-456789abcdef")
    assert result.status_code == 200
    assert result.json == {"case": 42, "url": "/api/v2/cases/42/01234567-89ab-cdef-0123-456789abcdef?q=a+b"}
    assert app.test_client().get("/api/v2/cases/no/01234567-89ab-cdef-0123-456789abcdef").status_code == 404


def test_request_json_forms_files_and_response_headers(web, app):
    @app.route("/upload", methods=["POST"])
    def upload():
        return {"tags": web.request.form.getlist("tag"), "body": web.request.files["file"].read().decode()}, 201, {"X-Upload": "ok"}

    @app.route("/json", methods=["POST"])
    def echo():
        return web.request.get_json()

    client = app.test_client()
    result = client.post("/upload", data={"tag": ["a", "b"], "file": (io.BytesIO(b"report"), "report.txt")})
    assert result.status_code == 201
    assert result.json == {"tags": ["a", "b"], "body": "report"}
    assert result.headers["X-Upload"] == "ok"
    assert client.post("/json", json={"nested": [1, 2]}).json == {"nested": [1, 2]}
    assert client.post("/json", data="{", content_type="application/json").status_code == 400
    assert client.post("/json", data="abc", content_type="text/plain").status_code == 415


def test_flask_cookie_is_read_and_updated_without_resigning_reads(web, app):
    from itsdangerous import URLSafeTimedSerializer
    import hashlib

    # Independent known Flask cookie payload; no Flask import at runtime.
    serializer = URLSafeTimedSerializer("migration-test-secret", salt="cookie-session", signer_kwargs={"key_derivation": "hmac", "digest_method": hashlib.sha1})
    cookie = serializer.dumps({"_user_id": "7", "permissions": 12})

    @app.route("/read")
    def read():
        return {"user": web.session.get("_user_id"), "permissions": web.session.get("permissions")}

    @app.route("/write")
    def write():
        web.session["permissions"] = 20
        return "saved"

    client = app.test_client()
    client.set_cookie("session", cookie)
    result = client.get("/read")
    assert result.json == {"user": "7", "permissions": 12}
    assert "Set-Cookie" not in result.headers
    result = client.get("/write")
    assert "Secure" in result.headers["Set-Cookie"]
    assert "HttpOnly" in result.headers["Set-Cookie"]
    assert "SameSite=Lax" in result.headers["Set-Cookie"]
    new_cookie = result.headers["Set-Cookie"].split(";", 1)[0].split("=", 1)[1]
    assert serializer.loads(new_cookie)["permissions"] == 20


def test_sessions_roundtrip_tagged_types_and_delete_empty_cookie(web, app):
    @app.route("/set")
    def set_session():
        web.session.update(pair=("hello", 3), blob=b"bytes", identifier=uuid.UUID(int=3), when=datetime(2020, 1, 2, tzinfo=timezone.utc))
        web.session.permanent = True
        return "ok"

    @app.route("/read")
    def read_session():
        assert web.session["pair"] == ("hello", 3)
        assert web.session["blob"] == b"bytes"
        assert web.session["identifier"] == uuid.UUID(int=3)
        assert web.session["when"].year == 2020
        return {"permanent": web.session.permanent}

    @app.route("/clear")
    def clear_session():
        web.session.clear()
        return "ok"

    client = app.test_client()
    assert "Expires=" in client.get("/set").headers["Set-Cookie"]
    assert client.get("/read").json == {"permanent": True}
    assert "Max-Age=0" in client.get("/clear").headers["Set-Cookie"]


def test_templates_include_blueprint_loaders_context_and_escaped_values(web, app, tmp_path):
    templates = tmp_path / "blueprint_templates"
    templates.mkdir()
    (templates / "page.html").write_text("{{ organisation }}|{{ value }}|{{ request.path }}|{{ session['name'] }}|{{ get_flashed_messages()[0] }}", encoding="utf-8")
    bp = web.Blueprint("pages", __name__, template_folder=str(templates))

    @app.context_processor
    def organisation():
        return {"organisation": "IRIS"}

    @bp.route("/page")
    def page():
        web.session["name"] = "Alice"
        web.flash("welcome")
        return web.render_template("page.html", value="<unsafe>")

    app.register_blueprint(bp)
    assert app.test_client().get("/page").data == b"IRIS|&lt;unsafe&gt;|/page|Alice|welcome"


def test_hooks_errors_redirect_and_teardown_keep_context(web, app):
    calls = []

    @app.before_request
    def before():
        web.g.marker = "request"

    @app.after_request
    def after(response):
        response.headers.add("X-Context", web.g.marker)
        return response

    @app.teardown_appcontext
    def cleanup(error):
        calls.append((web.current_app is not None, web.g.marker, error))

    @app.errorhandler(404)
    def missing(error):
        return {"message": "missing"}, 404

    @app.route("/go")
    def go():
        return web.redirect("/target")

    @app.route("/method", methods=["POST"])
    def method():
        return "ok"

    client = app.test_client()
    result = client.get("/absent")
    assert result.status_code == 404
    assert result.json == {"message": "missing"}
    assert result.headers["X-Context"] == "request"
    assert client.get("/method").status_code == 405
    result = client.get("/go")
    assert result.status_code == 302
    assert result.headers["Location"] == "/target"
    assert len(calls) == 3
    assert not web.has_request_context()
    assert not web.has_app_context()


def test_proxy_headers_external_urls_and_app_context_urls(web, app):
    @app.route("/target/<int:item>")
    def target(item):
        return web.url_for("target", item=item, _external=True)

    result = app.test_client().get("/target/4", headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "iris.example", "X-Forwarded-Prefix": "/iris"})
    assert result.data == b"https://iris.example/iris/target/4"
    app.config["SERVER_NAME"] = "jobs.example"
    with app.app_context():
        assert web.url_for("target", item=9) == "http://jobs.example/target/9"


def test_send_file_stream_and_safe_static_paths(web, app, tmp_path):
    (tmp_path / "report.bin").write_bytes(b"download-data")

    @app.route("/download")
    def download():
        return web.send_file(tmp_path / "report.bin", as_attachment=True, download_name="case.bin")

    @app.route("/files/<path:filename>")
    def files(filename):
        return web.send_from_directory(tmp_path, filename)

    client = app.test_client()
    result = client.get("/download")
    assert result.data == b"download-data"
    assert 'filename=case.bin' in result.headers["Content-Disposition"]
    assert result.headers["Content-Length"] == "13"
    assert client.get("/files/report.bin").data == b"download-data"
    assert client.get("/files/../outside.txt").status_code == 404


def test_explicit_request_context_supports_socket_callback_and_teardown(web, app):
    seen = []

    @app.teardown_appcontext
    def cleanup(exc):
        seen.append(web.g.get("token"))

    with app.test_request_context("/socket", headers={"Cookie": "bad=value"}):
        web.request.sid = "socket-id"
        web.g.token = "owned"
        assert web.request.sid == "socket-id"
        assert web.request.path == "/socket"
        assert web.current_app._get_current_object() is app
    assert seen == ["owned"]
    assert not web.has_app_context()


def test_concurrent_sync_handlers_do_not_block_loop_or_leak_context(web, app):
    import httpx

    @app.route("/sleep/<int:identifier>")
    def sleepy(identifier):
        web.g.identifier = identifier
        time.sleep(0.15)
        return {"identifier": web.g.identifier, "thread": threading.get_ident()}

    async def exercise():
        loop_thread = threading.get_ident()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            start = time.monotonic()
            results = await asyncio.gather(client.get("/sleep/1"), client.get("/sleep/2"))
            elapsed = time.monotonic() - start
        assert [result.json()["identifier"] for result in results] == [1, 2]
        assert all(result.json()["thread"] != loop_thread for result in results)
        assert elapsed < 0.28
    asyncio.run(exercise())


def test_head_options_and_strict_trailing_slash_match_handler_contract(web, app):
    @app.route("/slash/", methods=["GET", "POST"])
    def slash():
        return "hello"

    @app.route("/exact")
    def exact():
        return "exact"

    client = app.test_client()
    result = client.open("/slash/", method="HEAD")
    assert result.data == b""
    assert result.headers["Content-Length"] == "5"
    result = client.options("/slash/")
    assert result.status_code == 200
    assert result.mimetype == "text/html"
    assert set(result.headers["Allow"].split(", ")) == {"GET", "POST", "HEAD", "OPTIONS"}
    result = client.post("/slash?x=1")
    assert result.status_code == 308
    assert result.headers["Location"] == "https://localhost/slash/?x=1"
    assert client.get("/exact/").status_code == 404


def test_size_limit_rejects_request_without_executing_upload_handler(web, app):
    app.config["MAX_CONTENT_LENGTH"] = 5
    calls = []

    @app.route("/upload", methods=["POST"])
    def upload():
        calls.append(True)
        return "accepted"

    assert app.test_client().post("/upload", data="123456").status_code == 413
    assert calls == []


def test_invalid_cookie_cannot_restore_user_or_permissions(web, app):
    @app.route("/identity")
    def identity():
        return {"user": web.session.get("_user_id"), "permissions": web.session.get("permissions")}

    client = app.test_client()
    client.set_cookie("session", "eyJfdXNlcl9pZCI6IjEiLCJwZXJtaXNzaW9ucyI6MX0.invalid.signature")
    result = client.get("/identity")
    assert result.json == {"user": None, "permissions": None}
    assert "Set-Cookie" not in result.headers


def test_unhandled_exception_uses_500_handler_and_cleans_request_scope(web, app):
    app.config["TESTING"] = False
    cleanup = []

    @app.route("/broken")
    def broken():
        web.g.connection = "allocated"
        raise ValueError("failed")

    @app.errorhandler(500)
    def server_error(error):
        assert isinstance(error.original_exception, ValueError)
        return {"error": "internal"}, 500

    @app.teardown_appcontext
    def remove_connection(exc):
        cleanup.append((web.g.connection, type(exc)))

    result = app.test_client().get("/broken")
    assert result.status_code == 500
    assert result.json == {"error": "internal"}
    assert cleanup == [("allocated", ValueError)]


def test_json_lists_response_tuples_and_duplicate_cookies_are_preserved(web, app):
    @app.route("/list")
    def listing():
        return [1, "two"], {"X-Result": "list"}

    @app.route("/cookies")
    def cookies():
        response = web.make_response("ok", 202)
        response.set_cookie("one", "1")
        response.set_cookie("two", "2")
        return response

    client = app.test_client()
    assert client.get("/list").json == [1, "two"]
    result = client.get("/cookies")
    assert result.status_code == 202
    assert len(result.headers.getlist("Set-Cookie")) == 2


def test_asgi_root_path_prefix_and_filesystem_root_are_independent(web, tmp_path):
    app = web.IRISApp("iris_test_web", fs_root_path=str(tmp_path), root_path="/edge", static_folder=None)

    @app.route("/path")
    def path():
        return web.url_for("path")

    result = app.test_client().get("/edge/path")
    assert result.status_code == 200
    assert result.data == b"/edge/path"


def test_template_filter_decorator_uses_default_and_explicit_names(web, app):
    @app.template_filter()
    def prefix(value, addition):
        return addition + value

    @app.template_filter("loud")
    def uppercase(value):
        return value.upper()

    @app.route("/filter")
    def filtered():
        return web.render_template_string("{{ 'iris'|prefix('case:') }}|{{ 'iris'|loud }}")

    assert app.test_client().get("/filter").data == b"case:iris|IRIS"


def test_shared_resource_options_and_405_allow_all_registered_methods(web, app):
    @app.route("/api/v2/cases/<int:case_id>", methods=["GET"])
    def read_case(case_id):
        return "read"

    @app.route("/api/v2/cases/<int:case_id>", methods=["PUT"])
    def edit_case(case_id):
        return "edit"

    @app.route("/api/v2/cases/<int:case_id>", methods=["DELETE"])
    def delete_case(case_id):
        return "delete"

    client = app.test_client()
    assert client.get("/api/v2/cases/1").data == b"read"
    assert client.put("/api/v2/cases/1").data == b"edit"
    assert client.delete("/api/v2/cases/1").data == b"delete"
    result = client.options("/api/v2/cases/1")
    assert result.status_code == 200
    assert set(result.headers["Allow"].split(", ")) == {"GET", "HEAD", "OPTIONS", "PUT", "DELETE"}
    result = client.post("/api/v2/cases/1")
    assert result.status_code == 405
    assert set(result.headers["Allow"].split(", ")) == {"GET", "HEAD", "OPTIONS", "PUT", "DELETE"}


def test_large_upload_has_seekable_disk_backing_and_closes_after_response(web, app):
    payload = b"start:" + b"x" * (1024 * 1024 + 2048) + b":end"
    body_streams = []

    @app.route("/large", methods=["POST"])
    def large():
        body = web.request.environ["wsgi.input"]
        # A real disk descriptor demonstrates bounded input memory; BytesIO
        # cannot satisfy this contract. The multipart parser reads the file.
        assert os.fstat(body.fileno()).st_size > 1024 * 1024
        body_streams.append(body)
        uploaded = web.request.files["evidence"].read()
        return {"size": len(uploaded), "start": uploaded[:6].decode(), "end": uploaded[-4:].decode()}

    result = app.test_client().post("/large", data={"evidence": (io.BytesIO(payload), "large.bin")})
    assert result.status_code == 200
    assert result.json == {"size": len(payload), "start": "start:", "end": ":end"}
    assert len(body_streams) == 1
    assert body_streams[0].closed


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
def test_blueprint_http_method_decorators_preserve_existing_v2_routes(web, app, method):
    bp = web.Blueprint("v2", __name__, url_prefix="/api/v2")

    @getattr(bp, method.lower())("/resource")
    def resource():
        return {"method": web.request.method}

    app.register_blueprint(bp)
    result = app.test_client().open("/api/v2/resource", method=method)
    assert result.status_code == 200
    if method == "HEAD":
        assert result.data == b""
    else:
        assert result.json == {"method": method}

def test_image_store_is_native_static_route_before_default_static(web, tmp_path):
    app = web.IRISApp("iris_test_web", fs_root_path=str(tmp_path))
    from starlette.testclient import TestClient
    image_root = tmp_path / 'images'
    image_root.mkdir()
    (image_root / 'avatar.png').write_bytes(b'image-content')
    app.expose_image_store(path=str(image_root), prefix='/static/assets/images/')
    with TestClient(app) as client:
        response = client.get('/static/assets/images/avatar.png')
        assert response.status_code == 200
        assert response.content == b'image-content'
        assert client.head('/static/assets/images/avatar.png').content == b''
        assert client.get('/static/assets/images/missing.png').status_code == 404
        assert client.get('/static/assets/images/%2e%2e/outside.txt').status_code == 404
