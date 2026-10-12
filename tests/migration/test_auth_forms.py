"""Session and form contracts used by the unchanged HTML and API handlers."""
import importlib.util
import sys
import types
from pathlib import Path

from werkzeug.datastructures import MultiDict
from wtforms import StringField
from wtforms.validators import DataRequired


ROOT = Path(__file__).resolve().parents[2] / "source" / "app"


def modules():
    for filename in ("web.py", "auth_login.py", "web_forms.py"):
        assert (ROOT / filename).exists(), f"Native ASGI integration missing: {filename}"
    name = "_iris_auth_contract"
    if name not in sys.modules:
        package = types.ModuleType(name)
        package.__path__ = [str(ROOT)]
        sys.modules[name] = package
    loaded = []
    for module in ("web", "auth_login", "web_forms"):
        full_name = f"{name}.{module}"
        if full_name not in sys.modules:
            spec = importlib.util.spec_from_file_location(full_name, ROOT / f"{module}.py")
            instance = importlib.util.module_from_spec(spec)
            sys.modules[full_name] = instance
            spec.loader.exec_module(instance)
        loaded.append(sys.modules[full_name])
    return loaded


def test_cookie_login_persists_identity_and_logout_removes_it():
    web, auth, _ = modules()
    app = web.IRISApp(__name__)
    app.config.update(SECRET_KEY="test-key", SESSION_COOKIE_SECURE=False)
    manager = auth.LoginManager(app)

    class User(auth.UserMixin):
        id = 12

    manager.user_loader(lambda uid: User() if uid == "12" else None)

    @app.route("/login", methods=["POST"])
    def login():
        assert auth.login_user(User())
        return {"id": auth.current_user.get_id()}

    @app.route("/who")
    def who():
        return {"authenticated": auth.current_user.is_authenticated,
                "id": auth.current_user.get_id()}

    @app.route("/logout")
    def logout():
        auth.logout_user()
        return "ok"

    from starlette.testclient import TestClient
    with TestClient(app) as client:
        assert client.get("/who").json() == {"authenticated": False, "id": None}
        assert client.post("/login").json() == {"id": "12"}
        assert client.get("/who").json() == {"authenticated": True, "id": "12"}
        client.get("/logout")
        assert client.get("/who").json() == {"authenticated": False, "id": None}


def test_api_loader_authenticates_without_creating_cookie_identity():
    web, auth, _ = modules()
    app = web.IRISApp(__name__)
    app.config.update(SECRET_KEY="test-key", SESSION_COOKIE_SECURE=False)
    manager = auth.LoginManager(app)

    class User(auth.UserMixin):
        id = 15

    manager.request_loader(lambda req: User() if req.headers.get("Authorization") == "Bearer good" else None)

    @app.route("/who")
    def who():
        return {"id": auth.current_user.get_id()}

    from starlette.testclient import TestClient
    with TestClient(app) as client:
        assert client.get("/who", headers={"Authorization": "Bearer good"}).json() == {"id": "15"}
        assert client.get("/who").json() == {"id": None}


def test_csrf_token_renders_and_validates_form_json_and_header():
    web, _, forms = modules()
    app = web.IRISApp(__name__)
    app.config.update(SECRET_KEY="csrf-key", WTF_CSRF_TIME_LIMIT=None)

    class Form(forms.WebForm):
        name = StringField(validators=[DataRequired()])

    with app.test_request_context("/"):
        token = forms.generate_csrf()
        saved_session = dict(web.session)
        hidden = str(Form().hidden_tag())
        assert 'id="csrf_token" name="csrf_token" type="hidden"' in hidden
        assert token in hidden

    for kwargs in [
        {"data": MultiDict({"name": "Alice", "csrf_token": token})},
        {"json": {"name": "Alice", "csrf_token": token}},
        {"data": {"name": "Alice"}, "headers": {"X-CSRFToken": token}},
    ]:
        with app.test_request_context("/", method="POST", **kwargs):
            web.session.update(saved_session)
            assert Form().validate()

    with app.test_request_context("/", method="POST", data={"name": "Alice", "csrf_token": "tampered"}):
        web.session.update(saved_session)
        form = Form()
        assert not form.validate()
        assert form.csrf_token.errors


def test_csrf_token_is_bound_to_session():
    web, _, forms = modules()
    app = web.IRISApp(__name__)
    app.config["SECRET_KEY"] = "csrf-key"
    with app.test_request_context("/"):
        token = forms.generate_csrf()
    with app.test_request_context("/", method="POST", data={"csrf_token": token}):
        assert not forms.WebForm().validate()


def test_legacy_flask_login_cookie_retains_fresh_identity():
    web, auth, _ = modules()
    app = web.IRISApp(__name__)
    app.config["SECRET_KEY"] = "test-key"
    manager = auth.LoginManager(app)

    class User(auth.UserMixin):
        id = 12

    manager.user_loader(lambda uid: User() if uid == "12" else None)
    # Flask-Login 0.6.3 fixture for remote127.0.0.1 and User-Agent legacy-browser.
    # In a proxy chain, Flask-Login deliberately uses the first forwarded address.
    legacy_identifier = "ccfeeddd3fc39d24cc870b520992d8f65ef35c5b1bb405128ba2e620e54a7e63856ac86baa4be43b3456a10d6a68a1a230886ded0115184fcd22bfe7761c2cc0"
    with app.test_request_context("/", headers={"User-Agent": "legacy-browser", "X-Forwarded-For": "127.0.0.1, 10.0.0.2"}):
        web.session.update({"_user_id": "12", "_fresh": True, "_id": legacy_identifier})
        assert auth.current_user.get_id() == "12"
        assert web.session["_fresh"] is True

def test_login_required_uses_session_request_loader_and_disabled_mode():
    web, auth, _ = modules()
    from starlette.testclient import TestClient
    app = web.IRISApp(__name__)
    app.config.update(SECRET_KEY='key', SESSION_COOKIE_SECURE=False)
    manager = auth.LoginManager(app)
    class User(auth.UserMixin):
        id = 7
    manager.request_loader(lambda req: User() if req.headers.get('X-Key') == 'valid' else None)
    @app.route('/private')
    @auth.login_required
    def private():
        return 'private'
    @app.route('/sign-in')
    def sign_in():
        return 'login'
    with TestClient(app) as client:
        assert client.get('/private').status_code == 401
        manager.login_view = 'sign_in'
        response = client.get('/private?x=1', follow_redirects=False)
        assert response.status_code == 302
        from urllib.parse import parse_qs, urlsplit
        assert urlsplit(response.headers['location']).path == '/sign-in'
        assert parse_qs(urlsplit(response.headers['location']).query)['next'] == ['/private?x=1']
        assert client.get('/private', headers={'X-Key': 'valid'}).text == 'private'
        app.config['LOGIN_DISABLED'] = True
        assert client.get('/private').text == 'private'
    with app.test_request_context('/private'):
        auth.login_user(User())
        assert private() == 'private'


def test_login_required_exempts_options_and_uses_unauthorized_callback():
    web, auth, _ = modules()
    app = web.IRISApp(__name__)
    manager = auth.LoginManager(app)
    manager.unauthorized_handler(lambda: ('custom rejection', 403))
    @auth.login_required
    def protected():
        return 'accepted'
    with app.test_request_context('/private'):
        assert protected() == ('custom rejection', 403)
    with app.test_request_context('/private', method='OPTIONS'):
        assert protected() == 'accepted'
