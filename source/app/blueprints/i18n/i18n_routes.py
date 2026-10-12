"""Language switch endpoint.

The switch is POST-only and CSRF protected; the target locale is validated
against :data:`app.i18n.SUPPORTED_LOCALES` and the redirect target is forced to
be a site-relative path (no open redirect). The chosen locale is persisted in
the signed session and a long lived signed cookie so it survives re-login and
browser restarts.
"""
from urllib.parse import urlsplit

from wtforms.validators import ValidationError

from app.i18n import is_supported, persist_locale
from app.web import Blueprint, abort, current_app, redirect, request
from app.web_forms import validate_csrf

i18n_blueprint = Blueprint("i18n", __name__)


def _safe_next(raw):
    """Return ``raw`` only when it is a safe site-relative path, else ``None``.

    Rejects absolute URLs, protocol-relative URLs, control characters and
    backslashes so the switch cannot be abused as an open redirect.
    """
    if not raw or not isinstance(raw, str):
        return None
    if any(ord(char) < 0x20 or char == "\\" for char in raw):
        return None
    if not raw.startswith("/") or raw.startswith("//"):
        return None
    parts = urlsplit(raw)
    if parts.scheme or parts.netloc:
        return None
    return raw


@i18n_blueprint.route("/i18n/set-locale", methods=["POST"])
def set_locale():
    try:
        validate_csrf(request.form.get("csrf_token"))
    except ValidationError:
        abort(400)

    locale = request.form.get("locale", "", type=str)
    if not is_supported(locale):
        abort(400)

    target = _safe_next(request.form.get("next")) or _safe_next(request.referrer) or "/"
    response = redirect(target)
    persist_locale(current_app._get_current_object(), response, locale)
    return response