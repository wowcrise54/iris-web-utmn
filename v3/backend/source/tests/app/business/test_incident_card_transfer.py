"""Transfers must remap references rather than reuse another instance's IDs."""

import importlib.util
from pathlib import Path
import unittest


MODULE = Path(__file__).parents[3] / "app/business/incident_card_transfer.py"


class CardTransferTests(unittest.TestCase):
    def module(self):
        self.assertTrue(
            MODULE.is_file(), "Incident card transfer helper is not implemented"
        )
        spec = importlib.util.spec_from_file_location("card_transfer", MODULE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_remaps_known_refs_retains_values_and_flags_missing_alert(self):
        helper = self.module()
        original = {
            "selections": {"alert_id": 7, "affected_asset_ids": [2], "file_ids": [4]},
            "fields": {"description": {"value": "Сохранить текст", "mode": "manual"}},
            "missing_sources": [],
        }
        exported = helper.encode_card_references(original)
        self.assertEqual(exported["selections"]["affected_asset_ids"], ["asset:2"])
        restored = helper.decode_card_references(
            exported, {"asset:2": 102, "dsfile:4": 204}
        )
        self.assertEqual(restored["selections"]["affected_asset_ids"], [102])
        self.assertEqual(restored["selections"]["file_ids"], [204])
        self.assertIsNone(restored["selections"]["alert_id"])
        self.assertIn("alert_id", restored["missing_sources"])
        self.assertEqual(restored["fields"], original["fields"])
        self.assertEqual(original["selections"]["alert_id"], 7)

    def test_untrusted_numeric_and_wrong_kind_refs_never_survive_import(self):
        helper = self.module()
        restored = helper.decode_card_references(
            {
                "selections": {"source_asset_id": 55, "ioc_ids": ["task:2", "ioc:3"]},
                "fields": {},
            },
            {"task:2": 100, "ioc:3": 101},
        )
        self.assertIsNone(restored["selections"]["source_asset_id"])
        self.assertEqual(restored["selections"]["ioc_ids"], [101])
        self.assertIn("source_asset_id", restored["missing_sources"])
        self.assertIn("ioc_ids", restored["missing_sources"])


if __name__ == "__main__":
    unittest.main()
