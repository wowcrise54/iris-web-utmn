"""Core translation-engine tests: .po parsing, locale resolution, plurals.

These run without a request context and prove the engine is correct on its own.
"""
import threading

import pytest

import app.i18n as i18n


PO_SAMPLE = '''# header
msgid ""
msgstr ""
"Language: ru\\n"

#. a comment
#, fuzzy
msgid "Fuzzy"
msgstr "нет"

msgctxt "menu"
msgid "Open"
msgstr "Открыть"

msgid "task"
msgid_plural "tasks"
msgstr[0] "задача"
msgstr[1] "задачи"
msgstr[2] "задач"

msgid ""
"multi "
"line"
msgstr ""
"много "
"строчный"
'''


def test_po_parser_handles_context_plurals_multiline_and_fuzzy():
    entries = i18n.parse_po(PO_SAMPLE)
    catalog = i18n.Catalog("ru", entries)

    # Fuzzy entries are parsed but ignored, exactly like gettext.
    assert catalog.gettext("Fuzzy") == "Fuzzy"
    # Context-qualified entry is reachable only with its context.
    assert catalog.gettext("Open", "menu") == "Открыть"
    assert catalog.gettext("Open") == "Open"
    # Adjacent string literals are concatenated.
    assert catalog.gettext("multi line") == "много строчный"
    # Plural forms round-trip.
    assert catalog.ngettext("task", "tasks", 5) == "задач"


@pytest.mark.parametrize("value,expected", [
    ("ru", "ru"), ("RU", "ru"), ("ru-RU", "ru"), ("ru_RU", "ru"),
    ("en", "en"), ("en-GB", "en"), ("de", None), ("", None), (None, None),
])
def test_normalize_locale_only_accepts_supported(value, expected):
    assert i18n.normalize_locale(value) == expected


def test_resolve_locale_falls_back_to_default():
    assert i18n.resolve_locale("de") == i18n.DEFAULT_LOCALE
    assert i18n.resolve_locale(None) == "en"
    assert i18n.is_supported("ru") and not i18n.is_supported("fr")


def test_gettext_switches_with_active_locale():
    i18n.set_locale("ru")
    assert i18n.gettext("Dashboard") == "Панель управления"
    i18n.set_locale("en")
    assert i18n.gettext("Dashboard") == "Dashboard"


def test_ngettext_uses_locale_plural_rules():
    i18n.set_locale("ru")
    assert i18n.ngettext("task", "tasks", 1) == "задача"
    assert i18n.ngettext("task", "tasks", 2) == "задачи"
    assert i18n.ngettext("task", "tasks", 5) == "задач"
    assert i18n.ngettext("task", "tasks", 21) == "задача"
    assert i18n.ngettext("task", "tasks", 22) == "задачи"
    i18n.set_locale("en")
    assert i18n.ngettext("task", "tasks", 1) == "task"
    assert i18n.ngettext("task", "tasks", 2) == "tasks"


def test_missing_translation_falls_back_to_msgid():
    i18n.set_locale("ru")
    assert i18n.gettext("No such string in the catalog") == "No such string in the catalog"


def test_unknown_plural_falls_back_to_english_forms():
    assert i18n.ngettext("widget", "widgets", 1) == "widget"
    assert i18n.ngettext("widget", "widgets", 4) == "widgets"


def test_locale_is_isolated_between_threads():
    """The ContextVar must not leak one request's locale into another thread."""
    results = {}
    i18n.set_locale("ru")

    def worker():
        results["inherited"] = i18n.get_locale()
        i18n.set_locale("en")
        results["worker_value"] = i18n.gettext("Dashboard")

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()

    assert results["inherited"] == "en"          # fresh thread -> default
    assert results["worker_value"] == "Dashboard"
    assert i18n.gettext("Dashboard") == "Панель управления"  # main thread untouched


def test_lazy_string_resolves_at_render_time():
    i18n.set_locale("ru")
    lazy = i18n.lazy_gettext("Username")
    assert str(lazy) == "Имя пользователя"
    assert lazy.__html__() == "Имя пользователя"
    i18n.set_locale("en")
    assert str(lazy) == "Username"