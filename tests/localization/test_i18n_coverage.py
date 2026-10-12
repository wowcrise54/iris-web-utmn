"""Verify translation coverage from the extracted string inventory.

Every msgid referenced by an explicit ``_()``/``gettext()``/``ngettext()`` call
in a template or module must have a Russian translation.  This is the guard
against "we translated three pages and called it done".
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "source" / "app"


def _extractor():
    path = Path(__file__).with_name("extract_strings.py")
    spec = importlib.util.spec_from_file_location("iris_extract_strings", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_extractor_only_matches_explicit_translation_calls():
    ex = _extractor()
    hits = ex.extract_from_text("{{ _('Dashboard') }} {{ asset_label('Dashboard') }}", "t")
    assert [msgid for msgid, _fn, _o in hits] == ["Dashboard"]


def test_extractor_reads_plural_and_context_arguments():
    ex = _extractor()
    hits = ex.extract_from_text("{{ ngettext('task', 'tasks', n) }}", "t")
    assert {msgid for msgid, _fn, _o in hits} == {"task", "tasks"}


def test_extractor_reads_client_calls_and_unicode_form_labels():
    ex = _extractor()
    hits = ex.extract_from_text("IRIS_I18N.t('Save'); lazy_gettext(u'Name')", "t")
    assert {msgid for msgid, _fn, _o in hits} == {"Save", "Name"}


def test_all_wrapped_msgids_have_russian_translations():
    ex = _extractor()
    result = ex.coverage(SOURCE, SOURCE / "locales")
    assert result["referenced"] > 0, "extraction found no wrapped strings"
    assert result["missing"] == [], result["missing"]


def test_coverage_spans_multiple_templates():
    ex = _extractor()
    result = ex.coverage(SOURCE, SOURCE / "locales")
    assert result["report"]["files"] >= 8
