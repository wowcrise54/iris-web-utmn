"""Migration guarantees: native ASGI routes and byte-identical existing UI."""
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parent))
from check_app import inspect_contract


class MigrationContractTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("IRIS_MIGRATION_RUNTIME"), "run inside initialized isolated stack")
    def test_native_asgi_preserves_all_registered_flask_routes(self):
        inspect_contract()

    def test_existing_ui_and_templates_are_byte_identical(self):
        root = Path(__file__).parents[2]
        contract = json.loads((Path(__file__).parent / "contracts.json").read_text(encoding="utf-8"))
        for relative, expected in contract["ui_sha256"].items():
            with self.subTest(file=relative):
                path = root / relative
                self.assertTrue(path.is_file(), f"Existing UI file was removed: {relative}")
                self.assertEqual(expected, hashlib.sha256(path.read_bytes()).hexdigest(), relative)


if __name__ == "__main__":
    unittest.main()
