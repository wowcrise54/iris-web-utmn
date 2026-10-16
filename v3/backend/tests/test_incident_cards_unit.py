import importlib.util
import pathlib
import unittest
import sys
import types

app = types.ModuleType("app")
app.__path__ = []
sys.modules.setdefault("app", app)
business = types.ModuleType("app.business")
business.__path__ = []
sys.modules.setdefault("app.business", business)
ROOT = pathlib.Path(__file__).resolve().parents[1] / "source" / "app" / "business"
spec = importlib.util.spec_from_file_location(
    "app.business.incident_card_catalog", ROOT / "incident_card_catalog.py"
)
cat = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cat
spec.loader.exec_module(cat)


class IncidentCardTests(unittest.TestCase):
    def test_importance_matrix_and_priority(self):
        self.assertTrue(
            (ROOT / "incident_cards.py").exists(), "incident-card feature absent"
        )
        spec = importlib.util.spec_from_file_location(
            "incident_cards", ROOT / "incident_cards.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        result = mod.derive(
            {
                "categories": {"value": [1, 4]},
                "prioritization_type": {"value": "auxiliary"},
            }
        )
        self.assertEqual(result["importance"], "medium")
        self.assertEqual(result["priority"], 8)

    def load(self):
        spec = importlib.util.spec_from_file_location(
            "incident_cards", ROOT / "incident_cards.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_full_matrix(self):
        mod = self.load()
        matrix = [
            ["medium", "high", "high"],
            ["high", "high", "high"],
            ["medium", "high", "high"],
            ["low", "medium", "medium"],
            ["low", "low", "medium"],
            ["low", "medium", "medium"],
            ["low", "low", "low"],
        ]
        priorities = {
            "auxiliary": {"low": 9, "medium": 8, "high": 6},
            "key": {"low": 7, "medium": 5, "high": 3},
            "target": {"low": 4, "medium": 2, "high": 1},
        }
        for category, row in enumerate(matrix, 1):
            for asset, importance in zip(priorities, row):
                result = mod.derive(
                    {
                        "categories": {"value": [category]},
                        "prioritization_type": {"value": asset},
                    }
                )
                self.assertEqual(result["importance"], importance)
                self.assertEqual(result["priority"], priorities[asset][importance])

    def test_category8_requires_reason_even_with_other_category(self):
        mod = self.load()
        fields = {
            "categories": {"value": [2, 8]},
            "prioritization_type": {"value": "key"},
            "category8_importance": {"value": "low"},
        }
        self.assertIsNone(mod.derive(fields)["importance"])
        fields["category8_reason"] = {"value": "reason"}
        self.assertEqual(mod.derive(fields)["importance"], "high")

    def test_timestamps_and_completed_duration(self):
        mod = self.load()
        fields = {
            key: {"value": value}
            for key, value in {
                "occurred_at": "2026-01-01T01:00:00+01:00",
                "detected_at": "2026-01-01T00:10:00Z",
                "investigation_started_at": "2026-01-01T00:15:00Z",
                "incident_ended_at": "2026-01-01T01:00:00Z",
                "completed": False,
            }.items()
        }
        result = mod.derive(fields)
        self.assertEqual(result["reaction_seconds"], 300)
        self.assertIsNone(result["incident_duration_seconds"])
        fields["completed"]["value"] = True
        self.assertEqual(mod.derive(fields)["incident_duration_seconds"], 3600)
        fields["incident_ended_at"]["value"] = "2025-12-31T00:00:00Z"
        with self.assertRaises(mod.CardValidationError):
            mod.derive(fields)

    def test_strict_boundary_and_normalization(self):
        mod = self.load()
        base = {"schema_version": 1, "revision": 0, "fields": {}, "selections": {}}
        for entry in [
            {"unknown": {"value": "x", "mode": "manual"}},
            {"completed": {"value": "true", "mode": "manual"}},
            {"title": {"value": "x", "mode": "evil"}},
            {"categories": {"value": [True], "mode": "manual"}},
            {"occurred_at": {"value": "2026-01-01", "mode": "manual"}},
            {
                "acquainted": {
                    "value": [{"name": "A", "position": "B", "id": 1}],
                    "mode": "manual",
                }
            },
        ]:
            with self.assertRaises(mod.CardValidationError):
                mod.validate_update(dict(base, fields=entry))
        for additions in [
            {"meta": {}},
            {"revision": True},
            {"selections": {"alert_id": True}},
            {"selections": {"file_ids": [1, 1]}},
        ]:
            with self.assertRaises(mod.CardValidationError):
                mod.validate_update(dict(base, **additions))
        result = mod.validate_update(
            dict(
                base,
                fields={
                    "occurred_at": {
                        "value": "2026-01-01T05:00:00+05:00",
                        "mode": "manual",
                    }
                },
            )
        )
        self.assertEqual(
            result["fields"]["occurred_at"]["value"], "2026-01-01T00:00:00+00:00"
        )

    def test_manual_preservation_and_missing_source_snapshot(self):
        mod = self.load()
        context = {
            "meta": {"case_id": 1},
            "sources": {},
            "automatic": {"title": ("new", "case.name")},
        }
        stored = {
            "revision": 2,
            "fields": {
                "title": {"value": "manual", "mode": "manual"},
                "files": {"value": "old", "mode": "auto", "source": "file_ids:1"},
            },
            "selections": {"file_ids": [1]},
        }
        result = mod.build_snapshot(context, stored)
        self.assertEqual(result["fields"]["title"]["value"], "manual")
        self.assertEqual(result["fields"]["files"]["value"], "old")
        self.assertEqual(result["fields"]["files"]["status"], "missing")
        self.assertIn("files", result["completeness"]["missing"])
        self.assertTrue(result["warnings"])
        self.assertNotIn("source", stored["fields"]["title"])

    def test_unknown_incident_type_is_exclusive(self):
        mod = self.load()
        with self.assertRaises(mod.CardValidationError):
            mod.validate_update(
                {
                    "schema_version": 1,
                    "revision": 0,
                    "fields": {
                        "incident_types": {
                            "value": ["unknown", "intentional_theft"],
                            "mode": "manual",
                        }
                    },
                    "selections": {},
                }
            )

    def test_auto_edits_cannot_forge_missing_source_snapshot(self):
        mod = self.load()
        self.assertTrue(
            hasattr(mod, "merge_fields"), "server-owned auto provenance merge missing"
        )
        stored = {
            "files": {
                "value": "original",
                "mode": "auto",
                "source": "file_ids:3",
                "status": "ok",
            }
        }
        merged = mod.merge_fields(
            stored,
            {
                "files": {"value": "forged", "mode": "auto"},
                "hashes": {"value": "forged hash", "mode": "auto"},
            },
        )
        result = mod.build_snapshot(
            {"meta": {}, "sources": {}, "automatic": {}}, {"fields": merged}
        )
        self.assertEqual(result["fields"]["files"]["value"], "original")
        self.assertEqual(result["fields"]["files"]["source"], "file_ids:3")
        self.assertEqual(result["fields"]["files"]["status"], "missing")
        self.assertIsNone(result["fields"]["hashes"]["value"])
        self.assertEqual(stored["files"]["status"], "ok")

    def test_echoed_transfer_selections_keep_missing_source_warning(self):
        mod = self.load()
        self.assertTrue(
            hasattr(mod, "unresolved_sources"),
            "material selection change detection missing",
        )
        stored = {
            "selections": {"file_ids": [1], "alert_id": None},
            "missing_sources": ["file_ids", "alert_id"],
        }
        available = {"file_ids": {1, 2}, "alert_id": {3}}
        echoed = mod.deepcopy(mod.SELECTIONS)
        echoed.update(stored["selections"])
        self.assertEqual(
            mod.unresolved_sources(stored, echoed, available), ["file_ids", "alert_id"]
        )
        echoed["file_ids"] = [1, 2]
        self.assertEqual(
            mod.unresolved_sources(stored, echoed, available), ["alert_id"]
        )
        echoed["alert_id"] = 3
        self.assertEqual(mod.unresolved_sources(stored, echoed, available), [])
        echoed["file_ids"] = []
        echoed["alert_id"] = None
        self.assertEqual(
            mod.unresolved_sources(stored, echoed, available), ["file_ids", "alert_id"]
        )

    def test_empty_read_side_effect_free(self):
        mod = self.load()
        context = {"meta": {"case_id": 1}, "sources": {}, "automatic": {}}
        first = mod.build_snapshot(context)
        second = mod.build_snapshot(context)
        self.assertEqual(first, second)
        self.assertEqual(first["revision"], 0)
        self.assertIsNone(first["fields"]["reporter_name"]["value"])


if __name__ == "__main__":
    unittest.main()
