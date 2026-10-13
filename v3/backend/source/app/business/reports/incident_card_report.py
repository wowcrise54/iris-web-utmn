"""Regulation appendix 4, rendered twice from one resolved incident-card snapshot."""

import base64
from datetime import datetime
from html import escape
from io import BytesIO
import re
from zoneinfo import ZoneInfo

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


_IMPORTANCE = {"low": "Низкая", "medium": "Средняя", "high": "Высокая"}
_IMPORTANCE_ROWS = [
    ("1", "Средняя", "Высокая", "Высокая"),
    ("2", "Высокая", "Высокая", "Высокая"),
    ("3", "Средняя", "Высокая", "Высокая"),
    ("4", "Низкая", "Средняя", "Средняя"),
    ("5", "Низкая", "Низкая", "Средняя"),
    ("6", "Низкая", "Средняя", "Средняя"),
    ("7", "Низкая", "Низкая", "Низкая"),
]
_PRIORITY_ROWS = [
    ("Вспомогательная", "9", "8", "6"),
    ("Ключевая", "7", "5", "3"),
    ("Целевая", "4", "2", "1"),
]


def _clean(value):
    # Word XML cannot contain these characters, even when HTML can escape them.
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value))


def _value(field, value, timezone_name):
    if field.get("type") == "multichoice":
        selected = value or []
        return "\n".join(
            f"{'☑' if option['value'] in selected else '☐'} {option['label_ru']}"
            for option in field.get("options", [])
        )
    if value is None or value == "" or value == []:
        return ""
    kind = field.get("type")
    if kind == "boolean":
        return "Да" if value else "Нет"
    if kind == "datetime":
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return _clean(value)
            return parsed.astimezone(ZoneInfo(timezone_name)).strftime("%d.%m.%Y %H:%M")
        except (ValueError, TypeError):
            return _clean(value)
    options = field.get("options", [])
    labels = {option["value"]: option["label_ru"] for option in options}
    if kind == "choice":
        return _clean(labels.get(value, value))
    if kind == "multichoice":
        return "\n".join(
            f"{'☑' if option['value'] in value else '☐'} {option['label_ru']}"
            for option in options
        )
    if kind == "people":
        return "\n".join(
            " / ".join(_clean(person.get(key, "")) for key in ("name", "position"))
            for person in value
        )
    if isinstance(value, list):
        return "\n".join(_clean(item) for item in value)
    return _clean(value)


def _duration(value):
    if value is None:
        return "Не определено"
    minutes, seconds = divmod(int(value), 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    return f"{days} д. {hours} ч. {minutes} мин. {seconds} с."


def _rows(snapshot, timezone_name):
    fields = snapshot.get("fields", {})
    for section in snapshot.get("catalog", {}).get("sections", []):
        yield (
            section["id"],
            section["label_ru"],
            [
                (
                    field["label_ru"],
                    _value(
                        field, fields.get(field["key"], {}).get("value"), timezone_name
                    ),
                )
                for field in section["fields"]
            ],
        )


def _doc_table(doc, headings, rows):
    table = doc.add_table(rows=1, cols=len(headings))
    table.style = "Table Grid"
    for cell, text in zip(table.rows[0].cells, headings):
        cell.text = text
    repeat = OxmlElement("w:tblHeader")
    table.rows[0]._tr.get_or_add_trPr().append(repeat)
    for values in rows:
        for cell, text in zip(table.add_row().cells, values):
            cell.text = text or "________________________________"
    return table


def _html_table(headings, rows):
    head = "".join(f"<th>{escape(_clean(text))}</th>" for text in headings)
    body = "".join(
        "<tr>"
        + "".join(
            f"<td>{escape(_clean(text or '________________________________'))}</td>"
            for text in row
        )
        + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _form_rows(doc, html, rows):
    """Long narratives and checkbox lists use the full page width."""
    compact = []

    def flush():
        if compact:
            _doc_table(doc, ("Поле", "Сведения"), compact)
            html.append(_html_table(("Поле", "Сведения"), compact))
            compact.clear()

    for label, value in rows:
        if len(value) > 200 or "\n" in value:
            flush()
            paragraph = doc.add_paragraph()
            paragraph.add_run(label).bold = True
            paragraph.paragraph_format.keep_with_next = True
            for line in value.splitlines():
                doc.add_paragraph(line)
            html.append(
                f'<div class="long-field"><h3>{escape(label)}</h3>'
                f"<p>{escape(value)}</p></div>"
            )
        else:
            compact.append((label, value))
    flush()


def _append_calculations(doc, html, snapshot):
    derived = snapshot.get("derived", {})
    calculations = [
        (
            "Важность инцидента",
            _IMPORTANCE.get(derived.get("importance"), "Не определено"),
        ),
        ("Приоритет инцидента", str(derived.get("priority") or "Не определено")),
        (
            "Длительность: возникновение → окончание инцидента",
            _duration(derived.get("incident_duration_seconds")),
        ),
        (
            "Время реакции: обнаружение → начало расследования",
            _duration(derived.get("reaction_seconds")),
        ),
    ]
    _doc_table(doc, ("Показатель", "Значение"), calculations)
    html.append(_html_table(("Показатель", "Значение"), calculations))
    for title, headings, rows in [
        (
            "Важность по таблице регламента",
            ("Категория", "Вспомогательная", "Ключевая", "Целевая"),
            _IMPORTANCE_ROWS,
        ),
        (
            "Приоритет по таблице регламента",
            ("Тип системы", "Низкая", "Средняя", "Высокая"),
            _PRIORITY_ROWS,
        ),
    ]:
        doc.add_heading(title, 2)
        _doc_table(doc, headings, rows)
        html.append(f"<h3>{title}</h3>" + _html_table(headings, rows))
    note = (
        "Категория 8: важность задаётся вручную с обоснованием. "
        "Для нескольких категорий выбирается максимальная важность."
    )
    doc.add_paragraph(note)
    html.append(f"<p>{note}</p>")


def build_export(snapshot, timezone_name="Asia/Yekaterinburg"):
    """Return downloadable DOCX and self-contained printable HTML, with no disk writes."""
    doc = Document()
    section = doc.sections[0]
    section.page_height, section.page_width = Cm(29.7), Cm(21)
    section.top_margin = section.bottom_margin = Cm(1.8)
    section.left_margin, section.right_margin = Cm(2.0), Cm(1.5)
    style = doc.styles["Normal"]
    style.font.name, style.font.size = "Times New Roman", Pt(11)
    style._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
    style.paragraph_format.space_after = Pt(4)
    for name in ("Title", "Heading 1", "Heading 2"):
        doc.styles[name].font.color.rgb = RGBColor(0, 0, 0)
        doc.styles[name].font.name = "Times New Roman"
        doc.styles[name].font.size = Pt(16 if name == "Title" else 13)
        doc.styles[name].font.bold = True
    for doc_style in doc.styles:
        for borders in list(doc_style.element.iter(qn("w:pBdr"))):
            borders.getparent().remove(borders)
    heading = (
        "Приложение № 4 к Положению о мониторинге событий и реагировании "
        "на инциденты информационной безопасности"
    )
    appendix = doc.add_paragraph(heading)
    appendix.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    title = doc.add_heading("Карточка данных об инциденте", 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    case_id = snapshot.get("meta", {}).get("case_id", 0)
    revision = snapshot.get("revision", 0)
    stamp = f"Кейс № {case_id} · Ревизия {revision} · Часовой пояс: {timezone_name}"
    doc.add_paragraph(stamp)
    html = [
        f'<p class="appendix">{escape(heading)}</p><h1>Карточка данных об инциденте</h1>',
        f"<p>{escape(stamp)}</p>",
    ]
    technical = []
    calculations_added = False
    for key, label, rows in _rows(snapshot, timezone_name):
        if key == "technical":
            technical.append((label, rows))
            continue
        doc.add_heading(label, 1)
        html.append(f"<section><h2>{escape(label)}</h2>")
        _form_rows(doc, html, rows)
        html.append("</section>")
        if key == "priority":
            _append_calculations(doc, html, snapshot)
            calculations_added = True
    if not calculations_added:
        doc.add_heading("Приоритизация и длительность", 1)
        html.append("<h2>Приоритизация и длительность</h2>")
        _append_calculations(doc, html, snapshot)
    fields = snapshot.get("fields", {})
    blank = "________________________"
    for title in (
        "Составил",
        "С результатами проведённого расследования ознакомлен(ы)",
    ):
        doc.add_heading(title, 1)
        rows = [
            (
                _clean(fields.get("prepared_by", {}).get("value") or blank),
                _clean(fields.get("prepared_position", {}).get("value") or blank),
                blank,
            )
        ]
        if title != "Составил":
            people = fields.get("acquainted", {}).get("value") or []
            rows = [
                (
                    _clean(person.get("name") or blank),
                    _clean(person.get("position") or blank),
                    blank,
                )
                for person in people
            ]
            rows.extend([(blank, blank, blank)] * max(0, 3 - len(rows)))
        _doc_table(doc, ("ФИО", "Должность", "Подпись"), rows)
        html.append(
            f"<h2>{title}</h2>" + _html_table(("ФИО", "Должность", "Подпись"), rows)
        )
    for label, rows in technical:
        doc.add_page_break()
        doc.add_heading(label, 1)
        html.append(f'<section class="technical"><h2>{escape(label)}</h2>')
        _form_rows(doc, html, rows)
        html.append("</section>")
    stream = BytesIO()
    doc.save(stream)
    document = (
        """<!doctype html><html lang="ru"><meta charset="utf-8">
<title>Карточка инцидента</title><style>
body{max-width:190mm;margin:24px auto;padding:20px;color:#111;background:#fff;font:12pt "Times New Roman",serif}
h1{text-align:center;font-size:18pt}h2{font-size:14pt;margin-top:22px}h3{font-size:12pt}
table{border-collapse:collapse;width:100%;margin:10px 0;table-layout:fixed}
td,th{border:1px solid #777;padding:7px;vertical-align:top;white-space:pre-wrap;overflow-wrap:anywhere}
thead{display:table-header-group}th{text-align:left;background:#f4f4f4}h1,h2,h3{break-after:avoid}
.long-field p{white-space:pre-wrap;overflow-wrap:anywhere}.appendix{text-align:right;margin-left:40%} @page{size:A4;margin:18mm 16mm}
@media print{body{margin:0;padding:0;max-width:none}thead{display:table-header-group}.technical{break-before:page}}
</style><body>"""
        + "".join(html)
        + "</body></html>"
    )
    return {
        "filename": f"incident-card-{case_id}.docx",
        "revision": revision,
        "docx_base64": base64.b64encode(stream.getvalue()).decode("ascii"),
        "html": document,
        "warnings": snapshot.get("warnings", []),
    }
