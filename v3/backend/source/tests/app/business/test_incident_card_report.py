"""Exercise the native form exports, values, escaping and continuation."""

import base64
import importlib.util
from io import BytesIO
from pathlib import Path
import unittest
import sys
import types
from zipfile import ZipFile
from lxml import etree

ROOT = Path(__file__).parents[3] / "app/business"


for name in ("app", "app.business"):
    sys.modules.setdefault(name, types.ModuleType(name))
spec = importlib.util.spec_from_file_location(
    "app.business.incident_card_catalog", ROOT / "incident_card_catalog.py"
)
catalog = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = catalog
spec.loader.exec_module(catalog)


class IncidentCardReportTests(unittest.TestCase):
    def render(self, fields=None, derived=None, **kwargs):
        spec = importlib.util.spec_from_file_location(
            "report", ROOT / "reports/incident_card_report.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.build_export(
            dict(
                meta={"case_id": 2},
                revision=7,
                fields=fields or {},
                derived=derived or {},
            ),
            **kwargs,
        )

    def xml(self, result):
        with ZipFile(BytesIO(base64.b64decode(result["docx_base64"]))) as archive:
            return etree.fromstring(archive.read("word/document.xml"))

    def test_first_preparer_uses_form_and_extra_people_use_continuation(self):
        result = self.render(
            {
                "prepared_by": {
                    "value": [
                        {"name": "Иванов", "position": "Аналитик"},
                        {"name": "Петров", "position": "Руководитель"},
                    ]
                }
            }
        )
        text = "".join(self.xml(result).itertext())
        for value in ("Иванов", "Аналитик", "Петров", "Руководитель"):
            self.assertIn(value, text)
            self.assertIn(value, result["html"])
        self.assertIn("Продолжение.", result["html"])
        self.assertNotIn("'name':", result["html"])

    def test_empty_export_has_no_backgrounds_and_source_page_breaks(self):
        result = self.render()
        xml = self.xml(result)
        ns = {
            "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
            "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
        }
        self.assertEqual(len(xml.xpath("//wp:anchor", namespaces=ns)), 0)
        self.assertEqual(
            len(xml.xpath('//w:br[@w:type="page"]', namespaces=ns)),
            2,
        )
        self.assertEqual(result["filename"], "incident-card-2.docx")
        self.assertEqual(result["revision"], 7)
        self.assertNotIn("Ревизия", result["html"])

    def test_timezone_and_signatures_use_same_values_in_both_formats(self):
        result = self.render(
            {
                "detected_at": {"value": "2026-10-13T06:00:00Z"},
                "prepared_by": {"value": "Иванов"},
                "prepared_position": {"value": "Аналитик"},
                "acquainted": {
                    "value": [{"name": "Петров", "position": "Руководитель"}]
                },
            },
            timezone_name="Asia/Yekaterinburg",
        )
        text = "".join(self.xml(result).itertext())
        for expected in (
            "13.10.2026 11:00",
            "Иванов",
            "Аналитик",
            "Петров",
            "Руководитель",
        ):
            self.assertIn(expected, text)
            self.assertIn(expected, result["html"])

    def test_continuation_preserves_long_text_and_escapes_html(self):
        narrative = "<script>alert(1)</script> Кириллица " + "текст " * 1500
        result = self.render({"description": {"value": narrative}})
        self.assertIn(narrative, "".join(self.xml(result).itertext()))
        self.assertNotIn("<script>", result["html"])
        self.assertIn("&lt;script&gt;", result["html"])
        self.assertIn("Продолжение.", result["html"])

    def test_obsolete_fields_cannot_appear_even_in_an_old_snapshot(self):
        result = self.render(
            {
                "mitre_tactic": {"value": "SECRET-MITRE"},
                "files": {"value": "SECRET-FILE"},
                "title": {"value": "SECRET-TITLE"},
            }
        )
        for value in ("SECRET-MITRE", "SECRET-FILE", "SECRET-TITLE"):
            self.assertNotIn(value, result["html"])
            self.assertNotIn(value, "".join(self.xml(result).itertext()))

    def test_controls_are_removed_and_more_than_two_signers_use_continuation(self):
        result = self.render(
            {
                "description": {"value": "safe\x00text"},
                "acquainted": {
                    "value": [{"name": str(i), "position": "Роль"} for i in range(3)]
                },
            }
        )
        self.assertIn("safetext", result["html"])
        self.assertIn("Продолжение.", result["html"])
        self.assertIn("2 / Роль", result["html"])


if __name__ == "__main__":
    unittest.main()
