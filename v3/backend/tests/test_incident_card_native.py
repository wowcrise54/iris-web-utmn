import base64
from copy import deepcopy
import importlib.util
from io import BytesIO
from pathlib import Path
import sys
import types
import unittest
from zipfile import ZipFile
from lxml import etree

ROOT = Path(__file__).resolve().parents[1] / "source/app/business"
for name in ["app", "app.business"]:
    sys.modules.setdefault(name, types.ModuleType(name))
spec = importlib.util.spec_from_file_location(
    "app.business.incident_card_catalog", ROOT / "incident_card_catalog.py"
)
catalog = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = catalog
spec.loader.exec_module(catalog)
spec = importlib.util.spec_from_file_location(
    "report", ROOT / "reports/incident_card_report.py"
)
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


class NativeReportTests(unittest.TestCase):
    def render(self, fields=None):
        snapshot = {
            "meta": {"case_id": 2},
            "revision": 5,
            "fields": fields or {},
            "derived": {"importance": "high", "priority": 3},
        }
        before = deepcopy(snapshot)
        output = report.build_export(snapshot)
        self.assertEqual(snapshot, before)
        z = ZipFile(BytesIO(base64.b64decode(output["docx_base64"])))
        return output, z, etree.fromstring(z.read("word/document.xml"))

    def test_supplied_four_page_template_without_images(self):
        output, z, xml = self.render()
        self.assertFalse(any(n.startswith("word/media/") for n in z.namelist()))
        self.assertEqual(
            len(
                xml.xpath(
                    '//w:br[@w:type="page"]',
                    namespaces=xml.nsmap,
                )
            ),
            2,
        )
        self.assertEqual(output["html"].count('<section class="form-page">'), 4)
        self.assertNotIn("data:image", output["html"])
        self.assertNotIn("position:absolute", output["html"])
        self.assertIn("Категория 7", output["html"])

    def test_blank_export_preserves_supplied_template_xml_and_styles(self):
        output = report.build_export(
            {"meta": {"case_id": 2}, "fields": {}, "derived": {}}
        )
        original = ZipFile(report.TEMPLATE)
        generated = ZipFile(BytesIO(base64.b64decode(output["docx_base64"])))
        for name in ("word/document.xml", "word/styles.xml"):

            def canonical(data):
                return etree.tostring(etree.fromstring(data), method="c14n")

            self.assertEqual(
                canonical(original.read(name)), canonical(generated.read(name))
            )
        self.assertNotIn("Приложение № 4 к Положению", output["html"])
        self.assertIn("@page continuation", output["html"])
        self.assertIn("line-height:27.6", output["html"])

    def test_page_number_text_in_narrative_is_not_a_structural_header(self):
        output, archive, xml = self.render({"description": {"value": "Стр. 2"}})
        self.assertEqual(output["html"].count('<section class="form-page">'), 4)
        self.assertEqual(output["html"].count('<section class="continuation">'), 0)
        self.assertIn("Стр. 2", "".join(xml.itertext()))

    def test_independent_repeats_and_false_choices(self):
        output, z, xml = self.render(
            {
                "incident_types": {"value": ["natural_fire_repeat"]},
                "completed": {"value": False},
                "unacceptable_event": {"value": False},
                "unacceptable_event_kinds": {"value": ["personal_data_leak"]},
            }
        )
        text = "".join(xml.itertext())
        self.assertEqual(text.count("☒"), 3)
        self.assertIn("☒  Пожар", text)
        self.assertIn("☐  Пожар", text)
        self.assertIn("☐  Утечка персональных данных", text)
        self.assertIn("☒ Нет", text)

    def test_long_signature_and_unbroken_value_go_to_continuations(self):
        url = "https://example.test/" + ("x" * 1800)
        name = "Фамилия " * 200
        output, z, xml = self.render(
            {
                "report_url": {"value": url},
                "prepared_by": {"value": [{"name": name, "position": "Аналитик"}]},
            }
        )
        text = "".join(xml.itertext())
        self.assertIn(url, text)
        self.assertIn(name, text)
        self.assertIn("Продолжение. Инцидент 2.", text)
        self.assertIn("Аналитик", text)


if __name__ == "__main__":
    unittest.main()
