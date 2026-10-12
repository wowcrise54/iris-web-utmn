"""WTForms and signed CSRF tokens shared by HTML forms and JSON requests."""
import hashlib
import hmac
import os
from datetime import timedelta

from itsdangerous import BadData, SignatureExpired, URLSafeTimedSerializer
from markupsafe import Markup
from werkzeug.datastructures import CombinedMultiDict, ImmutableMultiDict
from wtforms import Form
from wtforms.csrf.core import CSRF
from wtforms.validators import ValidationError
from wtforms.widgets import HiddenInput

from .web import current_app, g, request, session


def generate_csrf():
    field_name = current_app.config.get("WTF_CSRF_FIELD_NAME", "csrf_token")
    if field_name not in session:
        session[field_name] = hashlib.sha1(os.urandom(64)).hexdigest()
    cache_name = f"_csrf_{field_name}"
    if not hasattr(g, cache_name):
        secret = current_app.config.get("WTF_CSRF_SECRET_KEY") or current_app.config["SECRET_KEY"]
        token = URLSafeTimedSerializer(secret, salt="wtf-csrf-token").dumps(session[field_name])
        setattr(g, cache_name, token)
    return getattr(g, cache_name)


def validate_csrf(token):
    field_name = current_app.config.get("WTF_CSRF_FIELD_NAME", "csrf_token")
    if not token:
        raise ValidationError("The CSRF token is missing.")
    if field_name not in session:
        raise ValidationError("The CSRF session token is missing.")
    secret = current_app.config.get("WTF_CSRF_SECRET_KEY") or current_app.config["SECRET_KEY"]
    limit = current_app.config.get("WTF_CSRF_TIME_LIMIT", 3600)
    if isinstance(limit, timedelta):
        limit = limit.total_seconds()
    try:
        value = URLSafeTimedSerializer(secret, salt="wtf-csrf-token").loads(token, max_age=limit)
    except SignatureExpired as exc:
        raise ValidationError("The CSRF token has expired.") from exc
    except BadData as exc:
        raise ValidationError("The CSRF token is invalid.") from exc
    if not hmac.compare_digest(session[field_name], value):
        raise ValidationError("The CSRF tokens do not match.")


class _FormCSRF(CSRF):
    def generate_csrf_token(self, csrf_token_field):
        return generate_csrf()

    def validate_csrf_token(self, form, field):
        if getattr(g, "csrf_valid", False):
            return
        token = field.data
        if not token:
            for header in current_app.config.get("WTF_CSRF_HEADERS", ["X-CSRFToken", "X-CSRF-Token"]):
                token = request.headers.get(header)
                if token:
                    break
        validate_csrf(token)


_AUTO = object()


class WebForm(Form):
    class Meta:
        csrf_class = _FormCSRF

        @property
        def csrf(self):
            return current_app.config.get("WTF_CSRF_ENABLED", True)

        @property
        def csrf_field_name(self):
            return current_app.config.get("WTF_CSRF_FIELD_NAME", "csrf_token")

        def get_translations(self, form):
            return None

    def __init__(self, formdata=_AUTO, **kwargs):
        if formdata is _AUTO:
            if self.is_submitted():
                if request.files:
                    formdata = CombinedMultiDict((request.files, request.form))
                elif request.form:
                    formdata = request.form
                elif request.is_json:
                    data = request.get_json(silent=True)
                    formdata = ImmutableMultiDict(data) if isinstance(data, dict) else None
                else:
                    formdata = None
            else:
                formdata = None
        super().__init__(formdata=formdata, **kwargs)

    def is_submitted(self):
        return request.method in ("POST", "PUT", "PATCH", "DELETE")

    def validate_on_submit(self, extra_validators=None):
        return self.is_submitted() and self.validate(extra_validators=extra_validators)

    def hidden_tag(self, *fields):
        selected = (self[name] if isinstance(name, str) else name for name in fields) if fields else self
        return Markup("\n".join(str(field()) for field in selected if isinstance(field.widget, HiddenInput)))


def init_forms(app):
    app.jinja_env.globals["csrf_token"] = generate_csrf
