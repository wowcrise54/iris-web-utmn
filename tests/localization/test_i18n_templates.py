"""Template-layer tests: Jinja globals, the switch partial, the JS catalog."""
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
    return application


def test_jinja_exposes_gettext_helpers(app):
    with app.test_request_context("/"):
        i18n.set_locale("ru")
        assert web.render_template_string("{{ _('Dashboard') }}") == "Панель управления"
        assert web.render_template_string("{{ gettext('Home') }}") == "Главная"
        assert web.render_template_string("{{ ngettext('task', 'tasks', 5) }}") == "задач"


def test_user_data_is_never_translated(app):
    """Only explicitly wrapped strings change; wrapped-identical user data does not."""
    with app.test_request_context("/"):
        i18n.set_locale("ru")
        html = web.render_template_string(
            "{{ _('Dashboard') }}|{{ user_text }}|{{ asset_name }}",
            user_text="Dashboard", asset_name="Dashboard",
        )
        assert html == "Панель управления|Dashboard|Dashboard"


def test_language_switch_partial_renders_both_locales(app):
    with app.test_request_context("/dashboard"):
        i18n.set_locale("en")
        html = web.render_template_string("{% include 'includes/language_switch.html' %}")
        assert 'name="locale"' in html
        assert "English" in html and "Русский" in html
        assert 'name="csrf_token"' in html
        assert 'value="/dashboard"' in html

        i18n.set_locale("ru")
        html_ru = web.render_template_string("{% include 'includes/language_switch.html' %}")
        assert "Язык" in html_ru


def test_i18n_scripts_embeds_active_catalog(app):
    with app.test_request_context("/"):
        i18n.set_locale("ru")
        html = web.render_template_string("{% include 'includes/i18n_scripts.html' %}")
        assert "window.IRIS_I18N" in html
        assert "Панель управления" in html
        assert "/static/assets/js/iris/i18n.js" in html


def test_customer_dialog_translates_without_changing_customer_data(app):
    from app.forms import AddCustomerForm
    from jinja2 import ChoiceLoader, FileSystemLoader

    app.jinja_env.loader = ChoiceLoader([
        app.jinja_env.loader,
        FileSystemLoader(str(ROOT / "blueprints" / "manage" / "templates")),
    ])

    with app.test_request_context("/"):
        for locale, heading, save in [("ru", "Добавить заказчика", "Сохранить"),
                                      ("en", "Add customer", "Save")]:
            i18n.set_locale(locale)
            form = AddCustomerForm(customer_name='Dashboard <script>')
            html = web.render_template(
                "modal_add_customer.html", form=form,
                customer={"client_id": None, "client_uuid": None},
            )
            assert heading in html and save in html
            assert 'Dashboard &lt;script&gt;' in html


def test_management_form_labels_and_required_errors_follow_locale(app):
    from app.forms import AddCustomerForm

    with app.test_request_context("/"):
        for locale, label, error in [("ru", "Название заказчика", "Обязательное поле."),
                                     ("en", "Customer name", "This field is required.")]:
            i18n.set_locale(locale)
            form = AddCustomerForm()
            assert str(form.customer_name.label.text) == label
            form.customer_name.validate(form)
            assert str(form.customer_name.errors[0]) == error


def test_layout_sets_html_lang_and_translates_error_page(app):
    with app.test_request_context("/missing"):
        i18n.set_locale("ru")
        html = web.render_template("pages/error-404.html")
        assert 'lang="ru"' in html
        assert "ИЗВИНИТЕ!" in html
        assert "Запрошенная страница не найдена." in html

        i18n.set_locale("en")
        html_en = web.render_template("pages/error-404.html")
        assert 'lang="en"' in html_en
        assert "SORRY!" in html_en


def _all_templates():
    roots = [ROOT / "templates"]
    roots += sorted((ROOT / "blueprints").glob("*/templates"))
    for root in roots:
        for path in sorted(root.rglob("*.html")):
            yield root, path


def test_every_template_compiles():
    """A syntax error in any template (e.g. a broken ``_()`` edit) fails here.

    The environment is permissive about the app's custom filters/tests (they are
    registered in ``app/__init__.py`` which this isolated suite does not boot),
    but it still fully *parses* every template, so a broken tag or jinja
    expression in an edited file is caught.
    """
    from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape

    class _Permissive(dict):
        def __missing__(self, key):
            return lambda *args, **kwargs: ""

        def get(self, key, default=None):
            if key in self:
                return dict.__getitem__(self, key)
            return self["__missing__"]

    roots = [ROOT / "templates"] + sorted((ROOT / "blueprints").glob("*/templates"))
    env = Environment(
        loader=ChoiceLoader([FileSystemLoader(str(root)) for root in roots]),
        autoescape=select_autoescape(),
        extensions=["jinja2.ext.i18n", "jinja2.ext.do", "jinja2.ext.loopcontrols"],
    )
    env.filters = _Permissive(env.filters)
    env.tests = _Permissive(env.tests)
    env.install_gettext_translations(
        type("T", (), {"gettext": staticmethod(lambda s: s),
                       "ngettext": staticmethod(lambda s, p, n: s)})(),
        newstyle=False,
    )
    compiled = 0
    for root, path in _all_templates():
        name = path.relative_to(root).as_posix()
        env.get_template(name)  # raises TemplateSyntaxError on failure
        compiled += 1
    assert compiled >= 100
