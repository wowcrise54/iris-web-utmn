"""Regression tests for the OpenCTI auto-enrich config normalisation.

The auto-enrichment Celery task and the manual REST endpoint both read
``iris_module.module_config`` and pass it to ``OpenCTIHandler``. The DB column
stores a JSON *list* of parameter dicts, but the handler expects a
*param_name -> value* dict. The previous implementation also redeclared
``Table('iris_module', db.Model.metadata)`` which collides with the already
mapped ``IrisModule`` model (SQLAlchemy ``InvalidRequestError``).

These tests exercise the pure ``normalize_module_config`` helper (no DB, no
Flask app) to lock in the list->dict contract, and assert that the module no
longer redeclares the ``iris_module`` Table on ``db.Model.metadata``.
"""
from unittest import TestCase

from iris_opencti_module.opencti_handler import auto_enrich


class TestNormalizeModuleConfig(TestCase):
    """The helper must turn the DB's list-of-params into a flat dict."""

    def test_list_of_param_dicts_becomes_flat_dict(self):
        raw = [
            {"param_name": "opencti_url", "value": "http://localhost:8080/graphql", "type": "string"},
            {"param_name": "opencti_token", "value": "secret", "type": "sensitive_string"},
            {"param_name": "opencti_min_score", "value": 50, "type": "int"},
        ]
        result = auto_enrich.normalize_module_config(raw)
        self.assertEqual(
            result,
            {
                "opencti_url": "http://localhost:8080/graphql",
                "opencti_token": "secret",
                "opencti_min_score": 50,
            },
        )
        self.assertIsInstance(result, dict)
        # The original list must be usable via .get() like a dict.
        self.assertEqual(result.get("opencti_min_score"), 50)

    def test_dict_passthrough_unchanged(self):
        raw = {"opencti_url": "http://x", "opencti_min_score": 10}
        self.assertIs(auto_enrich.normalize_module_config(raw), raw)

    def test_empty_list_becomes_empty_dict(self):
        self.assertEqual(auto_enrich.normalize_module_config([]), {})

    def test_none_becomes_empty_dict(self):
        self.assertEqual(auto_enrich.normalize_module_config(None), {})

    def test_malformed_entries_are_ignored(self):
        raw = [
            {"param_name": "opencti_url", "value": "http://x"},
            "not-a-dict",
            7,
            None,
            {"value": "missing-param-name"},
        ]
        self.assertEqual(
            auto_enrich.normalize_module_config(raw),
            {"opencti_url": "http://x", None: "missing-param-name"},
        )

    def test_missing_value_becomes_none(self):
        raw = [{"param_name": "opencti_url"}]
        self.assertEqual(auto_enrich.normalize_module_config(raw), {"opencti_url": None})


class TestAutoEnrichDoesNotRedefineIrisModuleTable(TestCase):
    """The module source must not redeclare Table('iris_module').

    Redeclaring ``Table('iris_module', db.Model.metadata, ...)`` raises
    ``sqlalchemy.exc.InvalidRequestError`` because ``IrisModule`` is already
    mapped to that table name. The fix queries the ORM model instead.
    """

    def test_no_table_redefinition_in_source(self):
        import inspect
        import re

        src = inspect.getsource(auto_enrich)
        # The anti-pattern is constructing Table('iris_module', db.Model.metadata,
        # ...). Match that specifically (comments/docstrings mentioning the bug
        # should not trip this).
        self.assertIsNone(
            re.search(r"Table\(\s*['\"]iris_module['\"]", src),
            "auto_enrich must not build Table('iris_module')",
        )
        self.assertNotIn("autoload_with", src, "no raw autoload Table() needed")

    def test_exposes_canonical_helpers(self):
        self.assertTrue(callable(getattr(auto_enrich, "get_opencti_module_config", None)))
        self.assertTrue(callable(getattr(auto_enrich, "normalize_module_config", None)))
        self.assertTrue(callable(getattr(auto_enrich, "enrich_alert_task", None)))
