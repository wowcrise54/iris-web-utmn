"""Server-side internationalization for the native IRIS alpha UI.

The layer is intentionally dependency free: catalogs live as GNU gettext
``.po`` files (the format translators and ``msgfmt``/Babel already understand)
and are parsed here into an in-memory, read-only :class:`Catalog`.

Design goals (see ``tests/localization/README.md``):

* **English is the source language and the default.** Missing translations
  always fall back to the ``msgid`` so an incomplete Russian catalog can never
  render a blank string.
* **Explicit calls only.** Nothing rewrites the DOM; templates call
  ``_("...")``/``ngettext(...)`` and JavaScript calls ``IRIS_I18N.t("...")``.
  User supplied data, enum values, API payloads and log records are never
  routed through the catalog.
* **Thread safe locale.** The active locale lives in a :class:`ContextVar` so
  concurrent ASGI worker threads never leak a locale into one another.
* **Validated locales.** Only :data:`SUPPORTED_LOCALES` are ever accepted from
  a request; anything else degrades to :data:`DEFAULT_LOCALE`.

Drop a new catalog at ``app/locales/<locale>/LC_MESSAGES/messages.po`` and add
the code to :data:`SUPPORTED_LOCALES` to enable a language.
"""
from __future__ import annotations

import json
import os
import threading
from contextvars import ContextVar
from typing import Dict, Iterable, List, Optional, Tuple

# --------------------------------------------------------------------------- #
# Supported locales
# --------------------------------------------------------------------------- #
# ``code -> (english label, endonym)``. The first entry is the default and the
# source language; it is kept first so ``DEFAULT_LOCALE`` stays obvious.
SUPPORTED_LOCALES: Tuple[str, ...] = ("en", "ru")
DEFAULT_LOCALE: str = "en"
LOCALE_LABELS: Dict[str, Dict[str, str]] = {
    "en": {"label": "English", "endonym": "English"},
    "ru": {"label": "Russian", "endonym": "Русский"},
}

# Name of the long lived, signed cookie that remembers an anonymous visitor's
# choice (and is reused as the per-user preference once logged in through the
# cookie session). Signed with the application SECRET_KEY.
LOCALE_COOKIE_NAME = "iris_locale"
LOCALE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # one year
LOCALE_SESSION_KEY = "locale"
_LOCALE_COOKIE_SALT = "iris-locale"

CATALOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locales")
CATALOG_FILENAME = "messages.po"


def normalize_locale(value: Optional[str]) -> Optional[str]:
    """Return a supported locale code for ``value`` or ``None``.

    Accepts exact codes (``ru``) and region variants (``ru-RU``, ``ru_RU``),
    only ever returning a member of :data:`SUPPORTED_LOCALES`.
    """
    if not value or not isinstance(value, str):
        return None
    candidate = value.strip().replace("_", "-").lower()
    if not candidate:
        return None
    if candidate in SUPPORTED_LOCALES:
        return candidate
    base = candidate.split("-", 1)[0]
    if base in SUPPORTED_LOCALES:
        return base
    return None


def resolve_locale(value: Optional[str]) -> str:
    """Validated locale code, falling back to :data:`DEFAULT_LOCALE`."""
    return normalize_locale(value) or DEFAULT_LOCALE


def is_supported(value: Optional[str]) -> bool:
    return normalize_locale(value) is not None


# --------------------------------------------------------------------------- #
# Plural rules
# --------------------------------------------------------------------------- #
def _plural_index(value: int, locale: str) -> int:
    """Plural form index for ``value`` using the CLDR rules for our locales."""
    try:
        n = abs(int(value))
    except (TypeError, ValueError):
        n = 0
    if locale == "ru":
        # Russian: one / few / many (0, 5-20, 11-14 use the "many" form).
        if n % 10 == 1 and n % 100 != 11:
            return 0
        if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
            return 1
        return 2
    # English (and default): singular for exactly one, plural otherwise.
    return 0 if n == 1 else 1


# --------------------------------------------------------------------------- #
# GNU gettext .po parsing
# --------------------------------------------------------------------------- #
def _unescape(text: str) -> str:
    out: List[str] = []
    index = 0
    length = len(text)
    escapes = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}
    while index < length:
        char = text[index]
        if char == "\\" and index + 1 < length:
            nxt = text[index + 1]
            out.append(escapes.get(nxt, nxt))
            index += 2
            continue
        out.append(char)
        index += 1
    return "".join(out)


def _parse_quoted(line: str) -> str:
    """Parse a ``msgid "..."`` payload, honouring escapes."""
    line = line.strip()
    if not line:
        return ""
    if line[0] != '"':
        raise ValueError(f"Expected quoted string, got: {line!r}")
    if line[-1] != '"':
        raise ValueError(f"Unterminated quoted string: {line!r}")
    return _unescape(line[1:-1])


class POEntry:
    __slots__ = ("msgctxt", "msgid", "msgid_plural", "msgstr", "msgstr_plural", "fuzzy")

    def __init__(self):
        self.msgctxt: Optional[str] = None
        self.msgid = ""
        self.msgid_plural: Optional[str] = None
        self.msgstr: Optional[str] = None
        self.msgstr_plural: Dict[int, str] = {}
        self.fuzzy = False


def parse_po(text: str) -> List[POEntry]:
    """Parse a ``.po`` document into :class:`POEntry` objects.

    Handles multi-line strings, ``msgctxt``, plural forms, comments and the
    ``fuzzy`` flag (fuzzy entries are parsed but flagged so callers can skip
    them, matching gettext behaviour).
    """
    entries: List[POEntry] = []
    current: Optional[POEntry] = None
    last_field: Optional[str] = None

    def flush():
        nonlocal current
        if current is not None and current.msgid:
            entries.append(current)
        current = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            flush()
            last_field = None
            continue
        if line.startswith("#"):
            if current is None:
                current = POEntry()
            if line.startswith("#,") and "fuzzy" in line:
                current.fuzzy = True
            continue
        if current is None:
            current = POEntry()
        if line.startswith("msgctxt "):
            current.msgctxt = _parse_quoted(line[len("msgctxt "):])
            last_field = "msgctxt"
        elif line.startswith("msgid_plural "):
            current.msgid_plural = _parse_quoted(line[len("msgid_plural "):])
            last_field = "msgid_plural"
        elif line.startswith("msgid "):
            current.msgid = _parse_quoted(line[len("msgid "):])
            last_field = "msgid"
        elif line.startswith("msgstr["):
            close = line.index("]")
            index = int(line[len("msgstr["):close])
            current.msgstr_plural[index] = _parse_quoted(line[close + 1:].strip())
            last_field = f"msgstr[{index}]"
        elif line.startswith("msgstr "):
            current.msgstr = _parse_quoted(line[len("msgstr "):])
            last_field = "msgstr"
        elif line.startswith('"'):
            chunk = _parse_quoted(line)
            if last_field == "msgctxt":
                current.msgctxt = (current.msgctxt or "") + chunk
            elif last_field == "msgid":
                current.msgid += chunk
            elif last_field == "msgid_plural":
                current.msgid_plural = (current.msgid_plural or "") + chunk
            elif last_field == "msgstr":
                current.msgstr = (current.msgstr or "") + chunk
            elif last_field and last_field.startswith("msgstr["):
                index = int(last_field[len("msgstr["):-1])
                current.msgstr_plural[index] = current.msgstr_plural.get(index, "") + chunk
        else:
            raise ValueError(f"Unrecognised .po line: {raw!r}")
    flush()
    return entries


# --------------------------------------------------------------------------- #
# Catalog
# --------------------------------------------------------------------------- #
class Catalog:
    """Read-only lookup table built from a ``.po`` file."""

    def __init__(self, locale: str, entries: Iterable[POEntry]):
        self.locale = locale
        self.singular: Dict[Tuple[Optional[str], str], str] = {}
        self.plural: Dict[Tuple[Optional[str], str], List[str]] = {}
        for entry in entries:
            if entry.fuzzy:
                continue
            key = (entry.msgctxt, entry.msgid)
            if entry.msgstr_plural:
                forms = [entry.msgstr_plural[i] for i in sorted(entry.msgstr_plural)]
                self.plural[key] = forms
            elif entry.msgstr:
                self.singular[key] = entry.msgstr

    def gettext(self, msgid: str, context: Optional[str] = None) -> str:
        return self.singular.get((context, msgid), msgid)

    def ngettext(self, singular: str, plural: str, n: int, context: Optional[str] = None) -> str:
        forms = self.plural.get((context, singular))
        if not forms:
            # No plural translation: fall back to the matching English form.
            return singular if _plural_index(n, DEFAULT_LOCALE) == 0 else plural
        index = _plural_index(n, self.locale)
        if index >= len(forms):
            index = len(forms) - 1
        return forms[index] or (singular if index == 0 else plural)

    def messages(self) -> Dict[str, str]:
        """msgid -> msgstr map for the JavaScript runtime."""
        return {msgid: value for (_ctx, msgid), value in self.singular.items()}

    def plurals(self) -> Dict[str, List[str]]:
        return {msgid: list(value) for (_ctx, msgid), value in self.plural.items()}


# --------------------------------------------------------------------------- #
# Catalog loading (cached, thread safe)
# --------------------------------------------------------------------------- #
_catalog_lock = threading.RLock()
_catalogs: Dict[str, Catalog] = {}
_missing_reported: set = set()


def catalog_path(locale: str) -> str:
    return os.path.join(CATALOG_DIR, locale, "LC_MESSAGES", CATALOG_FILENAME)


def load_catalog(locale: str) -> Catalog:
    """Load (and cache) the catalog for ``locale``; empty catalog if absent."""
    locale = resolve_locale(locale)
    with _catalog_lock:
        if locale in _catalogs:
            return _catalogs[locale]
        path = catalog_path(locale)
        entries: List[POEntry] = []
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as handle:
                entries = parse_po(handle.read())
        catalog = Catalog(locale, entries)
        _catalogs[locale] = catalog
        return catalog


def clear_catalog_cache() -> None:
    with _catalog_lock:
        _catalogs.clear()


def load_all_catalogs() -> Dict[str, Catalog]:
    """Eagerly load every supported catalog (used at startup and by tests)."""
    return {locale: load_catalog(locale) for locale in SUPPORTED_LOCALES}


# --------------------------------------------------------------------------- #
# Active locale + translation API
# --------------------------------------------------------------------------- #
_locale_var: ContextVar[Optional[str]] = ContextVar("iris_locale", default=None)


def get_locale() -> str:
    """Locale active for the current thread/context (validated)."""
    return resolve_locale(_locale_var.get())


def set_locale(locale: Optional[str]) -> str:
    """Set the active locale for the current context; returns the applied one."""
    applied = resolve_locale(locale)
    _locale_var.set(applied)
    return applied


def _translation(msgid: str, context: Optional[str] = None) -> str:
    return load_catalog(get_locale()).gettext(msgid, context)


def gettext(msgid: str, context: Optional[str] = None) -> str:
    """Translate ``msgid`` for the active locale (returns msgid on miss)."""
    if not msgid:
        return msgid
    return _translation(msgid, context)


def ngettext(singular: str, plural: str, n: int, context: Optional[str] = None) -> str:
    return load_catalog(get_locale()).ngettext(singular, plural, n, context)


def pgettext(context: str, msgid: str) -> str:
    return gettext(msgid, context)


class LazyString:
    """A string resolved against the active locale at ``str()`` time.

    Used by ``forms.py`` for field labels that are built at import time, before
    any request (and therefore locale) exists.
    """

    __slots__ = ("_func", "_args")

    def __init__(self, func, args):
        self._func = func
        self._args = args

    def __str__(self):
        return self._func(*self._args)

    def __html__(self):
        return str(self)

    def __repr__(self):
        return f"LazyString({self._args[0]!r})"

    def format(self, *args, **kwargs):
        return str(self).format(*args, **kwargs)


def lazy_gettext(msgid: str, context: Optional[str] = None) -> LazyString:
    return LazyString(gettext, (msgid, context))


# --------------------------------------------------------------------------- #
# JavaScript catalog
# --------------------------------------------------------------------------- #
def js_catalog(locale: Optional[str] = None) -> Dict[str, object]:
    """Return the JSON-safe catalog the browser runtime consumes."""
    locale = resolve_locale(locale or get_locale())
    catalog = load_catalog(locale)
    return {
        "locale": locale,
        "fallback": DEFAULT_LOCALE,
        "messages": catalog.messages(),
        "plurals": catalog.plurals(),
    }


def js_catalog_json(locale: Optional[str] = None) -> str:
    """Serialised catalog, safe to embed inside a ``<script>`` block."""
    payload = json.dumps(js_catalog(locale), ensure_ascii=False)
    # Prevent ``</script>`` inside a translation from ending the element early.
    return payload.replace("</", "<\\/")


# --------------------------------------------------------------------------- #
# Locale negotiation + persistence
# --------------------------------------------------------------------------- #
def _accept_language_locale() -> Optional[str]:
    try:
        from .web import request  # local import: avoid import cycle
        best = request.accept_languages.best_match(SUPPORTED_LOCALES)
    except Exception:  # pragma: no cover - only when no request context
        return None
    return normalize_locale(best)


def negotiate_locale(session_values=None, cookie_value: Optional[str] = None,
                     user=None) -> str:
    """Resolve the request locale by precedence.

    user record -> session -> signed cookie -> Accept-Language -> default.
    """
    if user is not None:
        stored = getattr(user, "ui_language", None)
        if normalize_locale(stored):
            return normalize_locale(stored)
    if session_values:
        stored = session_values.get(LOCALE_SESSION_KEY)
        if normalize_locale(stored):
            return normalize_locale(stored)
    if normalize_locale(cookie_value):
        return normalize_locale(cookie_value)
    accepted = _accept_language_locale()
    if accepted:
        return accepted
    return DEFAULT_LOCALE


def locale_cookie_serializer(app):
    from itsdangerous import URLSafeTimedSerializer
    secret = app.config.get("SECRET_KEY") or "iris-locale-fallback"
    return URLSafeTimedSerializer(secret, salt=_LOCALE_COOKIE_SALT)


def read_locale_cookie(app, cookie_value: Optional[str]) -> Optional[str]:
    if not cookie_value:
        return None
    try:
        value = locale_cookie_serializer(app).loads(
            cookie_value, max_age=LOCALE_COOKIE_MAX_AGE)
    except Exception:
        return None
    return normalize_locale(value)


def sign_locale(app, locale: str) -> str:
    return locale_cookie_serializer(app).dumps(resolve_locale(locale))


def persist_locale(app, response, locale: str) -> str:
    """Persist ``locale`` in the session and on the response cookie.

    Returns the applied locale. Only supported locales are accepted; the
    cookie is signed so a tampered value is ignored on read.
    """
    applied = resolve_locale(locale)
    try:
        from .web import session
        session[LOCALE_SESSION_KEY] = applied
        session.modified = True
    except Exception:  # pragma: no cover - no request context
        pass
    if response is not None:
        response.set_cookie(
            LOCALE_COOKIE_NAME,
            sign_locale(app, applied),
            max_age=LOCALE_COOKIE_MAX_AGE,
            path="/",
            secure=bool(app.config.get("SESSION_COOKIE_SECURE", True)),
            httponly=False,
            samesite=app.config.get("SESSION_COOKIE_SAMESITE", "Lax"),
        )
    return applied


# --------------------------------------------------------------------------- #
# Wiring
# --------------------------------------------------------------------------- #
def request_locale() -> str:
    """Compute the locale for the current request without mutating state."""
    from .web import request, session
    cookie = request.cookies.get(LOCALE_COOKIE_NAME)
    from .web import current_app
    cookie_value = read_locale_cookie(current_app._get_current_object(), cookie)
    user = None
    try:
        from .auth_login import current_user
        if current_user.is_authenticated:
            user = current_user._get_current_object()
    except Exception:
        user = None
    return negotiate_locale(session, cookie_value, user)


def init_i18n(app) -> None:
    """Attach the catalog, Jinja helpers and per-request locale to ``app``."""
    # Preload catalogs so the first request never pays the parse cost and a
    # broken catalog fails loudly at boot rather than mid-request.
    load_all_catalogs()

    @app.before_request
    def _apply_request_locale():
        set_locale(request_locale())
        return None

    env = app.jinja_env
    env.add_extension("jinja2.ext.i18n")
    # Bind the Jinja i18n extension to our translator so templates can also use
    # the ``{% trans %}`` block form with the same catalog.
    class _JinjaTranslations:
        def gettext(self, string):
            return gettext(string)

        def ngettext(self, singular, plural, n):
            return ngettext(singular, plural, n)

    env.install_gettext_translations(_JinjaTranslations(), newstyle=False)
    # install_gettext_translations registers gettext/ngettext; re-assert our
    # explicit globals (and the ``_`` alias) afterwards so they cannot drift.
    env.globals["gettext"] = gettext
    env.globals["_"] = gettext
    env.globals["ngettext"] = ngettext
    env.globals["pgettext"] = pgettext
    env.globals["get_locale"] = get_locale
    env.globals["supported_locales"] = SUPPORTED_LOCALES
    env.globals["locale_labels"] = LOCALE_LABELS
    env.globals["locale_cookie_name"] = LOCALE_COOKIE_NAME

    @app.context_processor
    def _i18n_context():
        locale = get_locale()
        return {
            "current_locale": locale,
            "i18n_js_catalog": js_catalog_json(locale),
        }