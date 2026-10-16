"""Tests for alert ownership, artifact validation and bounded file storage."""
import importlib.util
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest


def load_helpers():
    path = Path(__file__).parents[1] / 'v3/backend/source/app/business/alert_materials_validation.py'
    spec = importlib.util.spec_from_file_location('alert_materials_validation', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AlertMaterialsTests(unittest.TestCase):
    def test_only_assigned_owner_can_manage(self):
        helpers = load_helpers()
        self.assertTrue(helpers.is_alert_owner(SimpleNamespace(alert_owner_id=7), 7))
        self.assertFalse(helpers.is_alert_owner(SimpleNamespace(alert_owner_id=7), 8))
        self.assertFalse(helpers.is_alert_owner(SimpleNamespace(alert_owner_id=None), None))

    def test_invalid_artifacts_are_rejected(self):
        helpers = load_helpers()
        payloads = [None, [], {'kind': 'file'}, {'kind': 'command', 'value': ''},
                    {'kind': 'unknown', 'value': 'x'}, {'kind': 'process', 'value': 1}]
        for payload in payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    helpers.validate_artifact(payload)

    def test_artifact_metadata_cannot_override_identity_or_storage(self):
        self.assertEqual(
            load_helpers().validate_artifact({
                'kind': 'command', 'value': 'whoami', 'description': 'triage',
                'id': 99, 'user_id': 3, 'storage_name': '../secret',
            }),
            {'kind': 'command', 'value': 'whoami', 'description': 'triage'},
        )

    def test_upload_hashes_binary_and_enforces_size(self):
        helpers = load_helpers()
        with TemporaryDirectory() as directory:
            target = Path(directory) / 'sample'
            size, digest = helpers.write_upload(io.BytesIO(b'abc'), target, 3)
            self.assertEqual(size, 3)
            self.assertEqual(digest, 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')

            target = Path(directory) / 'oversize'
            with self.assertRaises(ValueError):
                helpers.write_upload(io.BytesIO(b'1234'), target, 3)
            self.assertFalse(target.exists())


if __name__ == '__main__':
    unittest.main()
