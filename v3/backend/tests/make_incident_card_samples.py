"""Generate synthetic empty/full cards for document layout QA, without opening the DB."""

import base64
import importlib.util
from pathlib import Path
import sys
import types


ROOT = Path(__file__).parents[1] / "source/app/business"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    catalog = load("catalog", ROOT / "incident_card_catalog.py")
    for name in ("app", "app.business"):
        sys.modules.setdefault(name, types.ModuleType(name))
    sys.modules["app.business.incident_card_catalog"] = catalog
    reports = load("reports", ROOT / "reports/incident_card_report.py")
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "meta": {"case_id": 0},
        "revision": 1,
        "fields": {},
        "warnings": [],
        "derived": {},
        "catalog": {"sections": catalog.SECTIONS},
    }
    for populated, name in [(False, "empty"), (True, "filled")]:
        fields = {}
        if populated:
            for key, field in catalog.FIELDS.items():
                kind = field["type"]
                value = "Заполненный пример: сведения по расследованию."
                if kind == "datetime":
                    value = "2026-10-13T06:00:00+00:00"
                elif kind == "boolean":
                    value = True
                elif kind == "choice":
                    value = field["options"][0]["value"]
                elif kind == "multichoice":
                    value = [field["options"][0]["value"]]
                elif kind == "people":
                    value = [
                        {"name": "Иванов Иван Иванович", "position": "Аналитик ИБ"}
                    ]
                fields[key] = {"value": value, "mode": "manual"}
            fields["description"]["value"] = (
                "Обнаружено фишинговое письмо. Проведён анализ заголовков, вложений "
                "и сетевых соединений. Доказательства сохранены, опасные адреса заблокированы.\n"
            ) * 35
            fields["categories"]["value"] = [2, 3]
            fields["incident_types"]["value"] = ["intentional_malware"]
        snapshot["fields"] = fields
        snapshot["derived"] = (
            {
                "importance": "high",
                "priority": 1,
                "incident_duration_seconds": 7200,
                "reaction_seconds": 900,
            }
            if populated
            else {}
        )
        result = reports.build_export(snapshot)
        (output / f"{name}.docx").write_bytes(base64.b64decode(result["docx_base64"]))
        (output / f"{name}.html").write_text(result["html"], encoding="utf-8")
    print(f"Generated synthetic cards ({len(catalog.FIELDS)} fields) in {output}")


if __name__ == "__main__":
    main()
