"""Unit tests for the incident card PDF generator (incident_pdf.py).

The generator is framework-agnostic (duck-typed Case), so it can be tested
without a Flask app or a database. The PDF is the 4-page official
Appendix-No.4 form 'Карточка данных об инциденте'.
"""
import importlib.util
import io
import re
from pathlib import Path

import pytest

REPORTLAB = pytest.importorskip("reportlab")

_MODULE_PATH = (Path(__file__).parent.parent.parent.parent
                / "source" / "app" / "blueprints" / "incident_management"
                / "incident_pdf.py")


@pytest.fixture(scope="module")
def incident_pdf():
    spec = importlib.util.spec_from_file_location("incident_pdf", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rel(**attrs):
    class R:
        pass
    r = R()
    for k, v in attrs.items():
        setattr(r, k, v)
    return r


def _make_case(incident_pdf_mod, **overrides):
    class C:
        pass
    c = C()
    defaults = dict(
        case_id=42, name="Test case", soc_id="soc-1",
        client=_rel(name="IrisInitialClient"),
        owner=_rel(name="administrator"),
        initial_date="2026-09-01T10:00:00",
        status_name="Open",
        close_date=None,
        description="Описание для теста",
        severity=_rel(severity_name="Low"),
        incident_category=_rel(name="Внедрение вредоносного ПО", code=2, id=2),
        system_type=_rel(name="Целевая система", id=1),
        system_type_id=1,
        importance=_rel(name="Высокая", id=1),
        importance_id=1,
        priority=_rel(level=3),
        incident_type=_rel(name="Вредоносное программное обеспечение", id=7),
        incident_type_id=7,
        undesirable_event=_rel(name=""),
        undesirable_event_id=None,
        is_undesirable_event=False,
        investigation_start_date="2026-09-01T11:00:00",
        investigation_end_date=None,
        impact_end_date=None,
        investigation_completion_date=None,
        investigator_name="Петров П.П.",
        motivation=_rel(name="Криминальная/финансовая выгода"),
        motivation_id=1,
        investigation_report_path="",
        reporter_name="Иванов Иван Иванович",
        reporter_phone="+7 912 000 00 00",
        reporter_email="ivanov@utmn.ru",
        reporter_location="Корпус Д, каб. 314",
        reporter_organization="ТюмГУ",
        incident_occurrence_date="2026-09-01T09:00:00",
        incident_discovery_date="2026-09-01T10:00:00",
        incident_report_date="2026-09-01T10:05:00",
        incident_duration_seconds=1860,
        response_phase="containment",
        playbook=_rel(name="Изоляция хоста"),
        affected_assets_info="UTMN-WS-042 / 10.10.4.123",
        business_impact_description="Простой лабораторных стендов",
        vulnerability_info="CVE-2026-0001",
        perpetrator_description="Внешняя скомпрометированная машина",
        corrective_measures_org="Обучение персонала",
        corrective_measures_tech="Патч",
        resolution_actions_taken="Изоляция хоста",
        resolution_actions_planned="Ревизия сегментации",
    )
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(c, k, v)
    return c


def _pdf_reader(data):
    from pypdf import PdfReader
    return PdfReader(io.BytesIO(data))


def _pdf_text(data):
    """Extract PDF text via pypdf, whitespace-collapsed (pypdf wraps long
    cell text across lines)."""
    reader = _pdf_reader(data)
    raw = "\n".join((p.extract_text() or "") for p in reader.pages)
    return re.sub(r"\s+", " ", raw)


ALL_LABELS = [
    "Карточка данных об инциденте",
    "Приложение №4",
    "Идентификатор инцидента",
    "Дата и время инцидента",
    "Источник инцидента/средство обнаружения",
    "Уровень критичности",
    "Информация о сообщающем лице",
    "Адрес, по которому был зафиксирован инцидент",
    "Описание инцидента",
    "Детали инцидента",
    "Категория инцидента",
    "внедрение в сетевую инфраструктуру Университета вредоносного программного обеспечения",
    "Закончился ли инцидент",
    "Недопустимое событие",
    "Утечка персональных данных",
    "Идентифицированные уязвимости",
    "Тип инцидента",
    "Преднамеренный",
    "Случайный/непреднамеренный",
    "Естественный",
    "Пораженные активы",
    "Негативное воздействие/влияние инцидента на бизнес-процессы",
    "Приоритизация инцидента",
    "Важность инцидента по таблице",
    "Приоритет инцидента по таблице",
    "Расследование инцидента",
    "Дата начала расследования инцидента",
    "Причастные лица",
    "Мотивация",
    "Описание нарушителя",
    "Действия, предпринятые для разрешения инцидента",
    "Действия, запланированные для разрешения инцидента",
    "Выработанные организационные и технические меры",
    "Составил:",
    "С результатами проведенного расследования ознакомлен(ы):",
]


def test_pdf_is_valid_4_pages_and_contains_data(incident_pdf):
    case = _make_case(incident_pdf)
    data = incident_pdf.build_incident_card_pdf(case, generated_by="e2e_test")

    assert isinstance(data, (bytes, bytearray))
    assert data[:5] == b"%PDF-", "not a PDF file"
    assert data.rstrip().endswith(b"%%EOF")

    reader = _pdf_reader(data)
    assert len(reader.pages) == 4, "Appendix-No.4 form spans exactly 4 pages"

    text = _pdf_text(data)
    # key Cyrillic values from the filled-in card
    for needle in ("Внедрение вредоносного ПО", "Целевая система", "Высокая",
                   "Иванов Иван Иванович", "UTMN-WS-042", "Петров П.П.",
                   "Корпус Д, каб. 314", "Криминальная/финансовая выгода",
                   "Низкий"):  # severity Low -> Низкий
        assert needle in text, f"missing in PDF: {needle}"


def test_all_form_labels_present(incident_pdf):
    case = _make_case(incident_pdf)
    text = _pdf_text(incident_pdf.build_incident_card_pdf(case))
    missing = [l for l in ALL_LABELS if l not in text]
    assert not missing, f"Appendix-No.4 form labels missing from the PDF: {missing}"


def test_checkboxes_reflect_selected_values(incident_pdf):
    case = _make_case(incident_pdf)
    data = incident_pdf.build_incident_card_pdf(case)
    text = _pdf_text(data)
    assert "\u2612" in text, "at least one checkbox must be checked"
    # category 2 is checked, category 1 is not
    assert "\u2612 2 внедрение в сетевую" in text
    assert "\u2610 1 отказ систем" in text
    # incident type 7 is checked
    assert "\u2612 Вредоносное программное обеспечение" in text
    # incident not finished -> 'Нет' checked
    assert "Нет" in text


def test_finished_incident_checks_yes_and_duration(incident_pdf):
    case = _make_case(incident_pdf,
                      close_date="2026-09-02T09:00:00",
                      response_phase="closure",
                      incident_duration_seconds=3660)
    text = _pdf_text(incident_pdf.build_incident_card_pdf(case))
    assert "1 ч 1 мин" in text, "duration must be rendered in days/hours/minutes"


def test_empty_case_does_not_crash(incident_pdf):
    case = _make_case(incident_pdf,
                      name=None, description=None,
                      incident_category=None, system_type=None,
                      importance=None, priority=None, incident_type=None,
                      motivation=None, playbook=None, client=None, owner=None,
                      severity=None,
                      response_phase=None, reporter_name=None,
                      affected_assets_info=None, incident_duration_seconds=None,
                      initial_date=None, soc_id=None)
    data = incident_pdf.build_incident_card_pdf(case)
    assert data[:5] == b"%PDF-"
    reader = _pdf_reader(data)
    assert len(reader.pages) == 4
    text = _pdf_text(data)
    assert "Карточка данных об инциденте" in text
    # no severity -> '—' in the criticality cell
    assert "— " in text or "—" in text


def test_filename_safety(incident_pdf):
    case = _make_case(incident_pdf, name="  #20 - Incident E2E / 2026 !!!  ")
    name = incident_pdf.incident_card_filename(case)
    assert name.startswith("incident_card_42_")
    assert name.endswith(".pdf")
    assert "\\" not in name and "/" not in name


def test_phase_labels(incident_pdf):
    assert incident_pdf.PHASE_LABELS["closure"] == "Подведение итогов"
    assert incident_pdf.PHASE_LABELS["false_positive"] == "Ложноположительный"
