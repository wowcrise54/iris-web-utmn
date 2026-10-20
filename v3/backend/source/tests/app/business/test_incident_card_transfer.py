"""Old bundles lose obsolete fields and links without mutating their source."""

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[3] / "app/business"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class CardTransferTests(unittest.TestCase):
    def helper(self):
        with patch.dict(
            sys.modules,
            {
                "app": types.ModuleType("app"),
                "app.business": types.ModuleType("app.business"),
            },
        ):
            load(
                "app.business.incident_card_catalog", ROOT / "incident_card_catalog.py"
            )
            load(
                "app.business.incident_card_cleanup", ROOT / "incident_card_cleanup.py"
            )
            return load("card_transfer", ROOT / "incident_card_transfer.py")

    def test_old_bundle_keeps_regulation_values_and_drops_all_source_links(self):
        helper = self.helper()
        original = {
            "fields": {
                "description": {"value": "Сохранить", "mode": "manual"},
                "files": {"value": "Удалить", "mode": "auto"},
            },
            "selections": {"file_ids": [4], "alert_id": 7},
            "missing_sources": ["alert_id"],
        }
        restored = helper.decode_card_references(
            helper.encode_card_references(original), {"dsfile:4": 204}
        )
        self.assertEqual(set(restored["fields"]), {"description"})
        self.assertEqual(restored["fields"]["description"]["value"], "Сохранить")
        self.assertEqual(restored["selections"], {})
        self.assertEqual(restored["missing_sources"], [])
        self.assertEqual(original["selections"]["alert_id"], 7)

    def test_large_legacy_investigator_list_remains_valid_after_conversion(self):
        helper = self.helper()
        original = {
            "fields": {
                "investigators": {
                    "value": [
                        {"name": "И" * 500, "position": "А" * 500} for _ in range(50)
                    ],
                    "mode": "manual",
                }
            }
        }
        fields = helper.decode_card_references(original, {})["fields"]
        self.assertGreater(len(fields["investigators"]["value"]), 50000)
        with patch.dict(
            sys.modules,
            {
                "app": types.ModuleType("app"),
                "app.business": types.ModuleType("app.business"),
            },
        ):
            load(
                "app.business.incident_card_catalog", ROOT / "incident_card_catalog.py"
            )
            logic = load("converted_card_logic", ROOT / "incident_cards.py")
            payload = {
                k: {"value": v["value"], "mode": v["mode"]} for k, v in fields.items()
            }
            logic.validate_update(
                dict(schema_version=1, revision=0, fields=payload, selections={})
            )

    def test_legacy_preparer_pair_becomes_one_repeatable_person(self):
        helper = self.helper()
        original = {
            "fields": {
                "prepared_by": {"value": "Иванов", "mode": "manual"},
                "prepared_position": {"value": "Аналитик", "mode": "manual"},
            }
        }
        result = helper.decode_card_references(original, {})
        self.assertEqual(
            result["fields"]["prepared_by"]["value"],
            [{"name": "Иванов", "position": "Аналитик"}],
        )
        self.assertNotIn("prepared_position", result["fields"])
        self.assertEqual(original["fields"]["prepared_position"]["value"], "Аналитик")

    def test_known_legacy_criticality_survives_bundle_import_as_russian_enum(self):
        helper = self.helper()
        for before, after in [
            ("High", "Высокий"),
            ("Medium", "Средний"),
            ("Low", "Низкий"),
        ]:
            original = {"fields": {"criticality": {"value": before, "mode": "manual"}}}
            result = helper.decode_card_references(original, {})
            self.assertEqual(result["fields"]["criticality"]["value"], after)
            self.assertEqual(original["fields"]["criticality"]["value"], before)

    def test_former_auto_values_are_frozen_and_reports_are_combined(self):
        helper = self.helper()
        original = {
            "fields": {
                "performed_actions": {
                    "value": "Выполнено",
                    "mode": "auto",
                    "source": "tasks:1",
                },
                "report_url": {"value": "https://example.test/report"},
                "report_location": {"value": "Архив"},
                "investigators": {
                    "value": [{"name": "Иванов", "position": "Аналитик"}]
                },
                "reporter_address": {"value": "Неоднозначный адрес"},
            }
        }
        fields = helper.decode_card_references(original, {})["fields"]
        self.assertEqual(fields["performed_actions"]["mode"], "manual")
        self.assertIsNone(fields["performed_actions"]["source"])
        self.assertEqual(
            fields["report_url"]["value"], "https://example.test/report\nАрхив"
        )
        self.assertEqual(fields["investigators"]["value"], "Иванов / Аналитик")
        self.assertNotIn("reporter_address", fields)
        self.assertNotIn("incident_location", fields)


if __name__ == "__main__":
    unittest.main()
