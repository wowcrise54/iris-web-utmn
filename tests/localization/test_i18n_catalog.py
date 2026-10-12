"""Russian catalog integrity: real translations, placeholders, JS parity."""
import json
import os
import re

import app.i18n as i18n

PLACEHOLDER_RE = re.compile(r"\{(\w+)\}|%\((\w+)\)s")


def test_supported_locales_have_catalogs():
    for locale in i18n.SUPPORTED_LOCALES:
        assert os.path.exists(i18n.catalog_path(locale)), locale


def test_russian_catalog_is_substantial():
    catalog = i18n.load_catalog("ru")
    assert len(catalog.singular) >= 80
    assert len(catalog.plural) >= 2


def test_every_russian_entry_is_actually_translated():
    catalog = i18n.load_catalog("ru")
    untranslated = [msgid for (_ctx, msgid), msgstr in catalog.singular.items()
                    if not msgstr or msgstr == msgid]
    assert untranslated == [], untranslated


def test_placeholders_are_preserved():
    catalog = i18n.load_catalog("ru")
    for (_ctx, msgid), msgstr in catalog.singular.items():
        source_tokens = {a or b for a, b in PLACEHOLDER_RE.findall(msgid)}
        target_tokens = {a or b for a, b in PLACEHOLDER_RE.findall(msgstr)}
        assert source_tokens <= target_tokens, (msgid, msgstr)


def test_english_catalog_is_the_identity_source():
    catalog = i18n.load_catalog("en")
    assert catalog.gettext("Dashboard") == "Dashboard"
    assert catalog.gettext("anything") == "anything"


def test_js_catalog_is_json_and_script_safe():
    payload = i18n.js_catalog_json("ru")
    assert "</" not in payload  # cannot break out of <script>
    data = json.loads(payload)
    assert data["locale"] == "ru"
    assert data["fallback"] == "en"
    assert data["messages"]["Dashboard"] == "Панель управления"
    assert data["plurals"]["task"] == ["задача", "задачи", "задач"]


def test_js_catalog_matches_python_catalog():
    catalog = i18n.load_catalog("ru")
    data = i18n.js_catalog("ru")
    assert data["messages"] == catalog.messages()
    assert data["plurals"] == catalog.plurals()