"""Regression checks derived from the supplied Appendix 4, not its old catalog."""

import base64
import importlib.util
from io import BytesIO
from pathlib import Path
import sys
import types
import unittest
from zipfile import ZipFile
from lxml import etree

ROOT = Path(__file__).resolve().parents[1] / "source" / "app"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


for name in ("app", "app.business"):
    sys.modules.setdefault(name, types.ModuleType(name))
catalog = load(
    "app.business.incident_card_catalog", ROOT / "business/incident_card_catalog.py"
)
logic = load("card_logic", ROOT / "business/incident_cards.py")
report = load("card_report", ROOT / "business/reports/incident_card_report.py")


class Appendix4Tests(unittest.TestCase):
    def test_alert_defaults_use_scoped_first_escalation_not_case_severity(self):
        from datetime import datetime, timezone

        case = types.SimpleNamespace(
            case_id=2, client_id=1, soc_id="7", initial_date=datetime(2026, 10, 19, 10)
        )
        alert = types.SimpleNamespace(
            alert_id=7,
            alert_customer_id=1,
            alert_source="SIEM",
            severity=types.SimpleNamespace(severity_name="Medium"),
            alert_source_event_time=datetime(2026, 10, 19, 8),
            modification_history={
                "1792404000": {"action": "Alert escalated to case #2"}
            },
        )
        defaults = logic.alert_defaults(case, [alert])
        self.assertEqual(defaults["criticality"][0], "Средний")
        self.assertEqual(defaults["detection_source"][0], "SIEM")
        self.assertEqual(
            defaults["incident_at"][0],
            datetime.fromtimestamp(1792404000, timezone.utc).isoformat(),
        )
        self.assertEqual(defaults["occurred_at"][0], "2026-10-19T08:00:00+00:00")
        alert.alert_customer_id = 99
        self.assertEqual(logic.alert_defaults(case, [alert]), {})

    def test_automatic_priority_ignores_cached_value(self):
        fields = {
            "categories": {"value": [2]},
            "prioritization_type": {"value": "target"},
            "priority_override": {"value": 9, "mode": "auto"},
        }
        self.assertEqual(logic.derive(fields)["priority"], 1)
        fields["priority_override"]["mode"] = "manual"
        self.assertEqual(logic.derive(fields)["priority"], 9)

    def test_preparers_are_repeatable_name_position_rows(self):
        people = [
            {"name": "Иванов", "position": "Аналитик"},
            {"name": "Петров", "position": "Руководитель"},
        ]
        result = logic.validate_update(
            dict(
                schema_version=1,
                revision=0,
                fields={"prepared_by": dict(value=people, mode="manual")},
                selections={},
            )
        )
        self.assertEqual(result["fields"]["prepared_by"]["value"], people)
        with self.assertRaises(logic.CardValidationError):
            logic.validate_update(
                dict(
                    schema_version=1,
                    revision=0,
                    fields={"prepared_position": dict(value="Legacy", mode="manual")},
                    selections={},
                )
            )

    def test_legacy_preparer_pair_survives_projection_without_changing_source(self):
        stored = {
            "fields": {
                "prepared_by": dict(value="Иванов", mode="manual"),
                "prepared_position": dict(value="Аналитик", mode="manual"),
            }
        }
        result = logic.build_snapshot({"meta": {}, "automatic": {}}, stored)
        self.assertEqual(
            result["fields"]["prepared_by"]["value"],
            [{"name": "Иванов", "position": "Аналитик"}],
        )
        self.assertNotIn("prepared_position", result["fields"])
        self.assertEqual(stored["fields"]["prepared_position"]["value"], "Аналитик")

    def test_criticality_is_a_three_value_russian_enum(self):
        for value in ("Высокий", "Средний", "Низкий"):
            result = logic.validate_update(
                dict(
                    schema_version=1,
                    revision=0,
                    fields={"criticality": dict(value=value, mode="manual")},
                    selections={},
                )
            )
            self.assertEqual(result["fields"]["criticality"]["value"], value)
        for value in ("Критический", "Critical", "High", "Highbla", 1, True):
            with (
                self.subTest(value=value),
                self.assertRaises(logic.CardValidationError),
            ):
                logic.validate_update(
                    dict(
                        schema_version=1,
                        revision=0,
                        fields={"criticality": dict(value=value, mode="manual")},
                        selections={},
                    )
                )

    def test_case_and_legacy_snapshot_criticality_are_normalized_without_mutation(self):
        for old, want in [
            ("High", "Высокий"),
            ("Medium", "Средний"),
            ("Low", "Низкий"),
            ("Высокая", "Высокий"),
            ("Критический", None),
            ("Highbla", None),
        ]:
            context = {
                "meta": {"case_id": 2},
                "automatic": {"criticality": (old, "case.severity")},
            }
            self.assertEqual(
                logic.build_snapshot(context)["fields"]["criticality"]["value"], want
            )
            stored = {"fields": {"criticality": dict(value=old, mode="manual")}}
            self.assertEqual(
                logic.build_snapshot({"meta": {}, "automatic": {}}, stored)["fields"][
                    "criticality"
                ]["value"],
                want,
            )
            self.assertEqual(stored["fields"]["criticality"]["value"], old)

    def test_catalog_groups_fields_by_regulation_headings_without_loss(self):
        sections = {s["id"]: s for s in catalog.SECTIONS}
        expected = {
            "general": ["id", "incident_at", "detection_source", "criticality"],
            "reporter": [
                "reporter_name",
                "reporter_phone",
                "reporter_email",
                "incident_location",
                "reporter_organization",
            ],
            "description": ["description", "affected_assets"],
            "details": [
                "occurred_at",
                "detected_at",
                "notified_at",
                "categories",
                "completed",
            ],
            "unacceptable_event": ["unacceptable_event", "unacceptable_event_kinds"],
            "vulnerabilities": ["vulnerabilities"],
            "types": ["incident_types"],
            "assets": [
                "asset_data",
                "asset_hardware",
                "asset_software",
                "asset_communications",
                "asset_documentation",
            ],
            "impact": ["business_impact"],
            "priority": ["prioritization_type", "priority_override"],
            "investigation": [
                "investigation_started_at",
                "investigators",
                "incident_ended_at",
                "impact_ended_at",
                "investigation_ended_at",
                "report_url",
            ],
            "actors": ["actors"],
            "motives": ["motives"],
            "offender": ["offender_description"],
            "performed_actions": ["performed_actions"],
            "planned_actions": ["planned_actions"],
            "measures": ["preventive_measures"],
            "prepared": ["prepared_by"],
            "acquainted": ["acquainted"],
        }
        self.assertEqual(list(sections), list(expected))
        all_keys = []
        for name, keys in expected.items():
            actual = [f["key"] for f in sections[name]["fields"]]
            self.assertEqual(actual, keys)
            all_keys.extend(actual)
        self.assertEqual(len(all_keys), len(set(all_keys)))

    def test_api_rejects_removed_fields_and_links(self):
        for key in (
            "title",
            "external_id",
            "organization",
            "mitre_tactic",
            "files",
            "hashes",
            "category8_reason",
        ):
            with self.subTest(key=key), self.assertRaises(logic.CardValidationError):
                logic.validate_update(
                    dict(
                        schema_version=1,
                        revision=0,
                        fields={key: dict(value="x", mode="manual")},
                        selections={},
                    )
                )
        with self.assertRaises(logic.CardValidationError):
            logic.validate_update(
                dict(
                    schema_version=1,
                    revision=0,
                    fields={},
                    selections={"file_ids": [1]},
                )
            )

    def test_snapshot_does_not_leak_old_fields_or_links(self):
        result = logic.build_snapshot(
            {
                "meta": {"case_id": 2},
                "automatic": {},
                "sources": {"files": [{"id": 1, "label": "SECRET"}]},
            },
            {
                "fields": {"files": {"value": "SECRET", "mode": "manual"}},
                "selections": {"file_ids": [1]},
            },
        )
        self.assertNotIn("files", result["fields"])
        self.assertEqual(result["selections"], {})
        self.assertNotIn("sources", result)

    def test_category8_and_expert_priority(self):
        for system, priority in [("auxiliary", 9), ("key", 7), ("target", 4)]:
            fields = {
                "categories": {"value": [8]},
                "prioritization_type": {"value": system},
            }
            self.assertEqual(logic.derive(fields)["importance"], "low")
            self.assertEqual(logic.derive(fields)["priority"], priority)
            fields["priority_override"] = {"value": 2}
            self.assertEqual(logic.derive(fields)["priority"], 2)

    def test_each_repeated_checkbox_can_be_selected_independently(self):
        opts = catalog.FIELDS["incident_types"]["options"]
        fire = [o["value"] for o in opts if o["label_ru"] == "Пожар"]
        accident = [o["value"] for o in opts if o["label_ru"] == "Техногенная авария"]
        self.assertEqual(len(fire), 2)
        self.assertEqual(len(accident), 2)
        self.assertEqual(len(set(fire + accident)), 4)

    def test_four_page_template_and_unabridged_continuation(self):
        text = "Полный текст <script> и кириллица\n" * 500
        result = report.build_export(
            {
                "meta": {"case_id": 2},
                "revision": 9,
                "fields": {
                    "description": {"value": text},
                    "acquainted": {
                        "value": [{"name": "Иванов", "position": "Аналитик"}]
                    },
                },
                "derived": {},
            }
        )
        self.assertNotIn("<script>", result["html"])
        self.assertNotIn("MITRE", result["html"])
        self.assertNotIn("Ревизия", result["html"])
        self.assertIn("Продолжение", result["html"])
        self.assertIn("Иванов", result["html"])
        with ZipFile(BytesIO(base64.b64decode(result["docx_base64"]))) as archive:
            xml = etree.fromstring(archive.read("word/document.xml"))
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            values = xml.xpath("//w:t/text()", namespaces=ns)
            self.assertIn(text.replace("\n", ""), "".join(values))
            self.assertEqual(
                len([n for n in archive.namelist() if n.startswith("word/media/")]), 0
            )


if __name__ == "__main__":
    unittest.main()
