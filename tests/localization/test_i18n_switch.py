"""End-to-end locale switch: CSRF, validation, safe redirect, persistence."""
from pathlib import Path

import pytest

import app.i18n as i18n
import app.web as web
import app.web_forms as web_forms
from app.blueprints.i18n import i18n_routes

ROOT = Path(__file__).resolve().parents[2] / "source" / "app"


@pytest.fixture
def app():
    application = web.IRISApp("app.web", fs_root_path=str(ROOT), static_folder=None)
    application.config.update(
        SECRET_KEY="loc-test-secret", TESTING=True, SESSION_COOKIE_SECURE=False,
    )
    i18n.init_i18n(application)
    web_forms.init_forms(application)
    application.register_blueprint(i18n_routes.i18n_blueprint)

    @application.route("/csrf-token")
    def csrf_token_route():
        return web.render_template_string("{{ csrf_token() }}")

    @application.route("/whoami")
    def whoami():
        return web.render_template_string("{{ current_locale }}")

    @application.route("/e404")
    def e404():
        return web.render_template("pages/error-404.html")

    return application


def _csrf(client):
    return client.get("/csrf-token").get_data(as_text=True).strip()


def test_switch_persists_locale_and_redirects_safely(app):
    client = app.test_client()
    token = _csrf(client)
    resp = client.post(
        "/i18n/set-locale",
        data={"csrf_token": token, "locale": "ru", "next": "/dashboard"},
    )
    assert resp.status_code in (302, 303, 307, 308)
    assert resp.headers["Location"].endswith("/dashboard")
    assert "iris_locale" in resp.headers.get("Set-Cookie", "")

    # The following requests are served in Russian from the persisted session.
    assert "ИЗВИНИТЕ!" in client.get("/e404").get_data(as_text=True)
    assert client.get("/whoami").get_data(as_text=True).strip() == "ru"


def test_rejects_unsupported_locale(app):
    client = app.test_client()
    resp = client.post("/i18n/set-locale", data={"csrf_token": _csrf(client), "locale": "de"})
    assert resp.status_code == 400


def test_requires_csrf(app):
    client = app.test_client()
    resp = client.post("/i18n/set-locale", data={"locale": "ru"})
    assert resp.status_code == 400


def test_switch_is_post_only(app):
    assert app.test_client().get("/i18n/set-locale").status_code == 405


def test_unsafe_next_target_is_rejected(app):
    client = app.test_client()
    resp = client.post(
        "/i18n/set-locale",
        data={"csrf_token": _csrf(client), "locale": "ru", "next": "https://evil.example/x"},
    )
    assert "evil.example" not in resp.headers.get("Location", "")


def test_accept_language_negotiation(app):
    client = app.test_client()
    resp = client.get("/whoami", headers={"Accept-Language": "ru-RU,ru;q=0.9,en;q=0.5"})
    assert resp.get_data(as_text=True).strip() == "ru"