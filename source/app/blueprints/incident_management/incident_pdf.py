#  IRIS Source Code
#  Copyright (C) 2021 - Airbus CyberSecurity (SAS)
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 3 of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""PDF export of the incident card — a faithful reproduction of the
'Карточка данных об инциденте' form, Приложение №4 к Положению о
мониторинге событий и реагировании на инциденты информационной
безопасности (Tyumen State University security position).

Layout: 4 A4 pages, section order and cell labels match the form 1:1:

* page 1: identifier header, reporting party, description, incident
  details (3 dates, category checklist, duration),
* page 2: undesirable event, vulnerabilities, incident type checklist,
  affected assets, business impact,
* page 3: prioritization (static importance/priority matrices with the
  selected cell highlighted), investigation, actors/motivation,
  perpetrator,
* page 4: resolution actions (taken/planned), corrective measures,
  signature blocks.

Uses reportlab + DejaVu Sans (full Cyrillic + U+2610/U+2612 checkbox
glyphs). The font pair ships with the blueprint (``fonts/``) and is also
picked up from the system when available.
"""
import datetime
import io
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
    TableStyle
)

FONT = "DejaVu"
FONT_BOLD = "DejaVu-Bold"

HERE = os.path.dirname(os.path.abspath(__file__))

# Candidate TTF pairs tried in order: (regular, bold).
_FONT_CANDIDATES = [
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    (os.path.join(HERE, "fonts", "DejaVuSans.ttf"),
     os.path.join(HERE, "fonts", "DejaVuSans-Bold.ttf")),
    (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
    (r"C:\Windows\Fonts\tahoma.ttf", r"C:\Windows\Fonts\tahomabd.ttf"),
    (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\seguiemj.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
     "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
]

CHECK = "\u2612"   # ☒ checked box
EMPTY = "\u2610"   # ☐ empty box

SEVERITY_LABELS = {
    "Low": "Низкий",
    "Medium": "Средний",
    "High": "Высокий",
    "Critical": "Критический",
    "Informational": "Информационный",
    "Unspecified": "Не указан",
}

PHASE_LABELS = {
    "registration": "Регистрация",
    "containment": "Сдерживание",
    "eradication": "Ликвидация",
    "recovery": "Восстановление",
    "closure": "Подведение итогов",
    "false_positive": "Ложноположительный",
}

# --- form constants (verbatim from Appendix No. 4) -------------------------

CATEGORIES = [
    (1, "отказ систем, сервисов и сетей в обслуживании"),
    (2, "внедрение в сетевую инфраструктуру Университета вредоносного "
        "программного обеспечения"),
    (3, "несанкционированные попытки доступа в систему"),
    (4, "действия, связанные с определением потенциальных целей атаки и "
        "получением представления о сервисах, работающих на "
        "идентифицированных целях атаки"),
    (5, "несоблюдения пользователями ИС требований ОРД по защите информации"),
    (6, "нарушение мер физической защиты ИС"),
    (7, "непреднамеренное воздействие пользователя на ИС, пользовательская "
        "ошибка"),
    (8, "иной тип инцидента"),
]

UNDESIRABLE_EVENTS = [
    (1, "Утечка персональных данных"),
    (2, "Утечка конфиденциальной информации"),
    (3, "Сбои или остановка операционных процессов из-за недоступности "
        "поддерживающих их информационных систем"),
    (4, "Недоступность публичных систем, в которых размещена информация "
        "согласно требованиям регулятора"),
    (5, "Вывод/потеря денежных средств со счета Университета"),
    (6, "Публикация/предоставление недостоверной или противоправной "
        "информации"),
]

# (id, label, group header shown before the row) — form order, verbatim.
INCIDENT_TYPES = [
    (1, "Хищение", "Преднамеренный"),
    (2, "Неправомерный доступ", None),
    (3, "Мошенничество", None),
    (4, "Неправомерное использование ресурсов", None),
    (5, "Саботаж/Физический ущерб", None),
    (6, "Неправомерное уничтожение информации", None),
    (7, "Вредоносное программное обеспечение", None),
    (8, "Другой случай", None),
    (9, "Отказ вычислительной и коммуникационной техники",
     "Случайный/непреднамеренный"),
    (10, "Ошибка аппаратной поддержки", None),
    (11, "Отказ/ошибка ПО", None),
    (12, "Ошибка поддержки ПО", None),
    (13, "Ошибка пользователя", None),
    (14, "Недостаточное кадровое обеспечение", None),
    (15, "Отказ связи", None),
    (16, "Операционная ошибка", None),
    (17, "Отказ системы электропитания", None),
    (18, "Ошибка конструкции", None),
    (19, "Потеря существенных сервисов", None),
    (20, "Другой случай", None),
    (21, "Пожар", "Естественный"),
    (22, "Техногенная авария", None),
    (23, "Наводнение", None),
    (24, "Другие явления, не зависящие от человека", None),
    (25, "Стихийное бедствие", None),
    (26, "Другой случай", None),
]
TYPE_UNKNOWN_NOTE = ("(если еще не установлен тип инцидента, то следует "
                     "отметить квадрат «неизвестно»)")

ACTORS = [
    "Физическое лицо",
    "Организованная группа",
    "Легально учрежденная организация/учреждение",
    "Неизвестен",
    "Нет виновного (природные факторы, отказ оборудования)",
]

MOTIVATIONS = [
    (1, "Криминальная/финансовая выгода"),
    (2, "Политика/Терроризм"),
    (3, "Развлечение/Хакерство"),
    (4, "Неизвестен"),
    (5, "Реванш"),
    (6, "Другие мотивы"),
]

# Importance matrix: Категории 1-7 x (Вспомогательная, Ключевая, Целевая).
IMPORTANCE_MATRIX = [
    ("Категория 1", "Средняя", "Высокая", "Высокая"),
    ("Категория 2", "Высокая", "Высокая", "Высокая"),
    ("Категория 3", "Средняя", "Высокая", "Высокая"),
    ("Категория 4", "Низкая", "Средняя", "Средняя"),
    ("Категория 5", "Низкая", "Низкая", "Средняя"),
    ("Категория 6", "Низкая", "Средняя", "Средняя"),
    ("Категория 7", "Низкая", "Низкая", "Низкая"),
]
# Priority matrix: (Вспомогательная, Ключевая, Целевая) x (Низкая, Средняя, Высокая).
PRIORITY_MATRIX = [
    ("Вспомогательная", "9", "8", "6"),
    ("Ключевая", "7", "5", "3"),
    ("Целевая", "4", "2", "1"),
]

_ASSET_ROWS = ["Информация/Данные", "Оборудование", "Программное обеспечение",
               "Средства связи", "Документация"]

# system_type_id -> column index of the matrices
_SYS_COL = {3: 0, 2: 1, 1: 2}
# importance_id -> column index of the priority matrix
_IMP_COL = {3: 0, 2: 1, 1: 2}


def _register_fonts():
    """Register a Cyrillic-capable TTF pair with reportlab (idempotent)."""
    try:
        pdfmetrics.getFont(FONT)
        return  # already registered
    except KeyError:
        pass
    for regular, bold in _FONT_CANDIDATES:
        if os.path.exists(regular) and os.path.exists(bold):
            pdfmetrics.registerFont(TTFont(FONT, regular))
            pdfmetrics.registerFont(TTFont(FONT_BOLD, bold))
            return
    raise RuntimeError(
        "No Cyrillic-capable TTF font found for the incident card PDF. "
        "Install DejaVu Sans (DejaVuSans.ttf / DejaVuSans-Bold.ttf) in the "
        "container or a system font on the host.")


def _fmt_dt(value):
    """Format a datetime for display (empty string if None)."""
    if not value:
        return ""
    if isinstance(value, datetime.datetime):
        return value.strftime("%d.%m.%Y %H:%M")
    if isinstance(value, datetime.date):
        return value.strftime("%d.%m.%Y")
    return str(value)


def _fmt_duration(seconds):
    if not seconds:
        return ""
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h} ч {m} мин"
    if m:
        return f"{m} мин {s} с" if s else f"{m} мин"
    return f"{s} с"


def _rel_attr(obj, *attrs, default=""):
    """Duck-typed attribute chain: first truthy value wins."""
    cur = obj
    for a in attrs:
        cur = getattr(cur, a, None) if cur is not None else None
        if cur:
            return cur
    return default


def _to_id(value):
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def build_incident_card_pdf(case, generated_by=None):
    """Build the incident-card PDF for a Case model instance.

    Args:
        case: an app.models.cases.Cases instance (relations must be loaded).
        generated_by: display name of the user requesting the export.

    Returns:
        bytes of the rendered PDF (4 pages, Appendix-No.4 layout).
    """
    _register_fonts()

    base = getSampleStyleSheet()["Normal"]
    h1 = ParagraphStyle("h1", parent=base, fontName=FONT_BOLD, fontSize=13,
                        leading=16, spaceAfter=1)
    sub = ParagraphStyle("sub", parent=base, fontName=FONT, fontSize=8,
                         leading=10, textColor=colors.HexColor("#444444"),
                         spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=base, fontName=FONT_BOLD, fontSize=10,
                        leading=13, spaceBefore=8, spaceAfter=3,
                        textColor=colors.HexColor("#1f3864"))
    lbl = ParagraphStyle("lbl", parent=base, fontName=FONT_BOLD, fontSize=8.5,
                         leading=11)
    cell = ParagraphStyle("cell", parent=base, fontName=FONT, fontSize=8.5,
                          leading=11)
    note = ParagraphStyle("note", parent=base, fontName=FONT, fontSize=7.5,
                          leading=10, textColor=colors.HexColor("#555555"))
    small = ParagraphStyle("small", parent=base, fontName=FONT, fontSize=7.5,
                           leading=10, textColor=colors.HexColor("#555555"))

    def P(text, style=cell):
        if text is None:
            text = ""
        t = (str(text).replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace("\n", "<br/>"))
        return Paragraph(t, style)

    def rel(rel, attr="name"):
        return _rel_attr(rel, attr) or ""

    # --- derived values ---
    cat_id = _to_id(_rel_attr(case.incident_category, "code", "id"))
    sys_id = _to_id(getattr(case, "system_type_id", None)
                    or _rel_attr(case.system_type, "id"))
    imp_id = _to_id(getattr(case, "importance_id", None)
                    or _rel_attr(case.importance, "id"))
    type_id = _to_id(getattr(case, "incident_type_id", None)
                     or _rel_attr(case.incident_type, "id"))
    und_id = _to_id(getattr(case, "undesirable_event_id", None)
                    or _rel_attr(case.undesirable_event, "id"))
    mot_id = _to_id(getattr(case, "motivation_id", None)
                    or _rel_attr(case.motivation, "id"))

    severity_name = _rel_attr(case.severity, "severity_name")
    severity_label = SEVERITY_LABELS.get(severity_name, "—")
    ended = bool(getattr(case, "close_date", None)) or \
        getattr(case, "response_phase", None) in ("closure", "false_positive")
    is_undesirable = bool(getattr(case, "is_undesirable_event", False))

    def box(checked):
        return CHECK if checked else EMPTY

    def kv_row(label, value):
        return [P(label, lbl), P(value if value not in (None, "") else "")]

    def blank_block(label, value, rows=3, min_mm=8):
        """Label row + value spanning the given number of empty rows."""
        data = [kv_row(label, value)]
        data += [[P(""), P("")] for _ in range(rows)]
        return data

    def grid_table(data, col_widths, row_heights=None, grid="ALL"):
        t = Table(data, colWidths=col_widths, rowHeights=row_heights)
        t.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, -1), FONT, 8.5),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        return t

    story = []

    # ============================ PAGE 1 ============================
    story.append(P("Карточка данных об инциденте", h1))
    story.append(P("Приложение №4 к Положению о мониторинге событий и "
                   "реагировании на инциденты информационной безопасности", sub))

    header = grid_table([
        kv_row("Идентификатор инцидента",
               getattr(case, "soc_id", None) or f"#{getattr(case, 'case_id', '')}"),
        kv_row("Дата и время инцидента",
               _fmt_dt(getattr(case, "incident_occurrence_date", None))),
        kv_row("Источник инцидента/средство обнаружения", "IRIS"),
        kv_row("Уровень критичности", severity_label),
    ], [60 * mm, 92 * mm])
    story.append(header)

    story.append(P("Информация о сообщающем лице", h2))
    story.append(grid_table([
        kv_row("ФИО", getattr(case, "reporter_name", None)),
        kv_row("Телефон", getattr(case, "reporter_phone", None)),
        kv_row("Эл. почта", getattr(case, "reporter_email", None)),
        kv_row("Адрес, по которому был зафиксирован инцидент",
               getattr(case, "reporter_location", None)),
        kv_row("Организация", getattr(case, "reporter_organization", None)),
    ], [60 * mm, 92 * mm]))

    story.append(P("Описание инцидента", h2))
    story.append(grid_table([
        kv_row("Описание инцидента", getattr(case, "description", None)),
        [P(""), P("")],
        [P(""), P("")],
        [P(""), P("")],
        kv_row("Пораженные активы", getattr(case, "affected_assets_info", None)),
    ], [45 * mm, 107 * mm], row_heights=[None, 8 * mm, 8 * mm, 8 * mm, None]))

    story.append(P("Детали инцидента", h2))
    detail_rows = [
        kv_row("Дата и время возникновения инцидента",
               _fmt_dt(getattr(case, "incident_occurrence_date", None))),
        kv_row("Дата и время обнаружения инцидента",
               _fmt_dt(getattr(case, "incident_discovery_date", None))),
        kv_row("Дата и время отправки сообщения об инциденте",
               _fmt_dt(getattr(case, "incident_report_date", None))),
        kv_row("Категория инцидента", rel(case.incident_category)),
    ]
    for num, text in CATEGORIES:
        detail_rows.append([
            P(f"{box(cat_id == num)} {num}", cell),
            P(text, cell),
        ])
    detail_rows.append([
        P("Закончился ли инцидент (отметить)", lbl),
        P(f"{box(ended)} Да      {box(not ended)} Нет", cell),
    ])
    detail_rows.append(kv_row(
        "Если «да», то уточнить, как долго длился инцидент в днях/часах/минутах",
        _fmt_duration(getattr(case, "incident_duration_seconds", None))
        if ended else ""))
    story.append(grid_table(detail_rows, [70 * mm, 82 * mm]))

    story.append(PageBreak())

    # ============================ PAGE 2 ============================
    story.append(grid_table([[
        P("Недопустимое событие (отметить и выбрать ниже)", lbl),
        P(f"{box(is_undesirable)} Да      {box(not is_undesirable)} Нет", cell),
    ]], [100 * mm, 52 * mm]))
    story.append(Spacer(1, 2))

    ev_rows = []
    for i in range(0, len(UNDESIRABLE_EVENTS), 2):
        left = UNDESIRABLE_EVENTS[i]
        right = UNDESIRABLE_EVENTS[i + 1] if i + 1 < len(UNDESIRABLE_EVENTS) \
            else (None, "")
        ev_rows.append([
            P(box(und_id == left[0]), cell), P(left[1], cell),
            P(box(und_id == right[0]) if right[0] else "", cell),
            P(right[1], cell) if right[0] else P("", cell),
        ])
    story.append(grid_table(ev_rows, [8 * mm, 84 * mm, 8 * mm, 52 * mm]))
    story.append(Spacer(1, 2))

    story.append(grid_table([kv_row(
        "Идентифицированные уязвимости",
        getattr(case, "vulnerability_info", None))], [45 * mm, 107 * mm],
        row_heights=[None]))
    story.append(Spacer(1, 2))

    story.append(P("Тип инцидента", h2))
    type_rows = []
    type_style_cmds = []
    type_col_widths = [8 * mm, 76 * mm, 8 * mm, 60 * mm]
    r = 0
    # group the 26 options by their header row
    groups = []
    header = "Преднамеренный"
    buf = []
    for tid, text, hdr in INCIDENT_TYPES:
        if hdr:
            if buf:
                groups.append((header, buf))
                buf = []
            header = hdr
        buf.append((tid, text))
    if buf:
        groups.append((header, buf))

    for header, items in groups:
        type_rows.append([P(header, lbl), P(""), P(""), P("")])
        type_style_cmds.append(("SPAN", (0, r), (-1, r)))
        type_style_cmds.append(("BACKGROUND", (0, r), (-1, r),
                                colors.HexColor("#e8eef7")))
        r += 1
        for i in range(0, len(items), 2):
            left = items[i]
            right = items[i + 1] if i + 1 < len(items) else (None, "")
            type_rows.append([
                P(box(type_id == left[0]), cell), P(left[1], cell),
                P(box(type_id == right[0]) if right[0] else "", cell),
                P(right[1], cell) if right[0] else P("", cell),
            ])
            r += 1
    type_rows.append([
        P(box(type_id is None), cell),
        P("Неизвестно", cell),
        P(TYPE_UNKNOWN_NOTE, note), P(""),
    ])
    type_style_cmds.append(("SPAN", (2, r), (3, r)))
    tt = Table(type_rows, colWidths=type_col_widths)
    tt.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), FONT, 8.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ] + type_style_cmds))
    story.append(tt)
    story.append(Spacer(1, 4))

    story.append(P("Пораженные активы", h2))
    story.append(grid_table(
        [kv_row(name, "") for name in _ASSET_ROWS], [45 * mm, 107 * mm]))

    story.append(P("Негативное воздействие/влияние инцидента на "
                   "бизнес-процессы", h2))
    story.append(grid_table([
        [P(getattr(case, "business_impact_description", None) or "", cell)],
        [P("", cell)],
        [P("", cell)],
    ], [152 * mm], row_heights=[None, 8 * mm, 8 * mm]))

    story.append(PageBreak())

    # ============================ PAGE 3 ============================
    story.append(P("Приоритизация инцидента", h2))
    story.append(grid_table([
        kv_row("Важность инцидента по таблице:",
               rel(case.importance)),
    ], [60 * mm, 92 * mm]))

    imp_data = [[P(row[0], lbl), P(row[1], cell), P(row[2], cell),
                 P(row[3], cell)] for row in IMPORTANCE_MATRIX]
    imp_cmds = []
    if cat_id and 1 <= cat_id <= 7 and sys_id in _SYS_COL:
        r_ = cat_id - 1  # matrix row 0 == Категория 1
        imp_cmds.append(("BACKGROUND", (1 + _SYS_COL[sys_id], r_),
                         (1 + _SYS_COL[sys_id], r_),
                         colors.HexColor("#cfe2f3")))
        imp_cmds.append(("FONT", (1 + _SYS_COL[sys_id], r_),
                         (1 + _SYS_COL[sys_id], r_), FONT_BOLD, 8.5))
    it = Table(imp_data, colWidths=[38 * mm, 38 * mm, 38 * mm, 38 * mm])
    it.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), FONT, 8.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ] + imp_cmds))
    imp_hdr = [P("Категория инцидента / тип системы", lbl), P("Вспомогательная", lbl),
               P("Ключевая", lbl), P("Целевая", lbl)]
    hdr_tbl = grid_table([imp_hdr], [38 * mm, 38 * mm, 38 * mm, 38 * mm])
    story.append(hdr_tbl)
    story.append(it)
    story.append(Spacer(1, 4))

    story.append(grid_table([
        kv_row("Приоритет инцидента по таблице:",
               f"Уровень {getattr(getattr(case, 'priority', None), 'level', '')}"
               if getattr(getattr(case, "priority", None), "level", None) else "—"),
    ], [60 * mm, 92 * mm]))
    pri_data = [[P(row[0], lbl), P(row[1], cell), P(row[2], cell),
                 P(row[3], cell)] for row in PRIORITY_MATRIX]
    pri_cmds = []
    if sys_id in _SYS_COL and imp_id in _IMP_COL:
        r_, c_ = _SYS_COL[sys_id], 1 + _IMP_COL[imp_id]
        pri_cmds.append(("BACKGROUND", (c_, r_), (c_, r_),
                         colors.HexColor("#cfe2f3")))
        pri_cmds.append(("FONT", (c_, r_), (c_, r_), FONT_BOLD, 8.5))
    pri_hdr = [P("Тип системы / Важность", lbl), P("Низкая", lbl),
               P("Средняя", lbl), P("Высокая", lbl)]
    hdr_tbl2 = grid_table([pri_hdr], [38 * mm, 38 * mm, 38 * mm, 38 * mm])
    pt = Table(pri_data, colWidths=[38 * mm, 38 * mm, 38 * mm, 38 * mm])
    pt.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), FONT, 8.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ] + pri_cmds))
    story.append(hdr_tbl2)
    story.append(pt)
    sys_type_name = rel(case.system_type)
    if sys_type_name:
        story.append(P(f"Тип системы: {sys_type_name}", small))
    story.append(Spacer(1, 4))

    story.append(P("Расследование инцидента", h2))
    story.append(grid_table([
        kv_row("Дата начала расследования инцидента",
               _fmt_dt(getattr(case, "investigation_start_date", None))),
        kv_row("ФИО лица (лиц), проводившего (их) расследование инцидента",
               getattr(case, "investigator_name", None)),
        kv_row("Дата окончания инцидента",
               _fmt_dt(getattr(case, "investigation_end_date", None))),
        kv_row("Дата окончания воздействия",
               _fmt_dt(getattr(case, "impact_end_date", None))),
        kv_row("Дата завершения расследования инцидента",
               _fmt_dt(getattr(case, "investigation_completion_date", None))),
        kv_row("Ссылка и место хранения отчета о расследовании",
               getattr(case, "investigation_report_path", None)),
    ], [75 * mm, 77 * mm]))

    story.append(Spacer(1, 4))
    # Причастные лица | Мотивация — 5 rows x (box, actor, box, motivation)
    mot_map = dict(MOTIVATIONS)
    am_rows = [[P("Причастные лица", lbl), P(""), P("Мотивация", lbl), P("")]]
    am_cmds = [("SPAN", (0, 0), (1, 0)), ("SPAN", (2, 0), (3, 0)),
               ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef7"))]
    for i, actor in enumerate(ACTORS):
        mid, mtext = MOTIVATIONS[i] if i < len(MOTIVATIONS) else (None, "")
        am_rows.append([
            P(EMPTY, cell), P(actor, cell),
            P(box(mot_id == mid) if mid else "", cell),
            P(mtext, cell) if mid else P("", cell),
        ])
    amt = Table(am_rows, colWidths=[8 * mm, 68 * mm, 8 * mm, 68 * mm])
    amt.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), FONT, 8.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ] + am_cmds))
    story.append(amt)
    story.append(Spacer(1, 4))

    story.append(grid_table([
        kv_row("Описание нарушителя", getattr(case, "perpetrator_description", None)),
        [P(""), P("")],
        [P(""), P("")],
    ], [45 * mm, 107 * mm], row_heights=[None, 8 * mm, 8 * mm]))

    story.append(PageBreak())

    # ============================ PAGE 4 ============================
    story.append(P("Действия, предпринятые для разрешения инцидента", h2))
    story.append(P("(например, «никаких действий», «подручными средствами», "
                   "«внутреннее расследование», «внешнее расследование с "
                   "привлечением…»)", note))
    story.append(grid_table([
        [P(getattr(case, "resolution_actions_taken", None) or "", cell)],
        [P("", cell)],
        [P("", cell)],
    ], [152 * mm], row_heights=[None, 8 * mm, 8 * mm]))
    story.append(Spacer(1, 4))

    story.append(P("Действия, запланированные для разрешения инцидента", h2))
    story.append(P("(например, см. выше)", note))
    story.append(grid_table([
        [P(getattr(case, "resolution_actions_planned", None) or "", cell)],
        [P("", cell)],
        [P("", cell)],
    ], [152 * mm], row_heights=[None, 8 * mm, 8 * mm]))
    story.append(Spacer(1, 4))

    story.append(P("Выработанные организационные и технические меры", h2))
    story.append(P("(организационные и технические меры, направленные на "
                   "снижение рисков нарушения информационной безопасности, "
                   "предотвращение и минимизацию подобных нарушений в "
                   "будущем)", note))
    story.append(grid_table([
        [P(getattr(case, "corrective_measures_org", None) or "", cell)],
        [P("", cell)],
        [P(getattr(case, "corrective_measures_tech", None) or "", cell)],
        [P("", cell)],
    ], [152 * mm], row_heights=[None, 8 * mm, None, 8 * mm]))
    story.append(Spacer(1, 6))

    owner_name = _rel_attr(getattr(case, "owner", None), "name") or \
        _rel_attr(getattr(case, "owner", None), "user", "name")
    story.append(P("Составил:", h2))
    story.append(grid_table([
        [P(owner_name, cell), P(""), P("(должность)", cell), P(""),
         P("(подпись)", cell)],
    ], [45 * mm, 20 * mm, 35 * mm, 20 * mm, 32 * mm], row_heights=[12 * mm]))
    story.append(Spacer(1, 6))

    story.append(P("С результатами проведенного расследования ознакомлен(ы):", h2))
    story.append(grid_table([
        [P(""), P(""), P("(должность)", cell), P(""), P("(подпись)", cell)],
        [P(""), P(""), P("(должность)", cell), P(""), P("(подпись)", cell)],
    ], [45 * mm, 20 * mm, 35 * mm, 20 * mm, 32 * mm],
        row_heights=[12 * mm, 12 * mm]))

    # footer
    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=0.5,
                            color=colors.HexColor("#bbbbbb")))
    now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
    footer = f"Сформировано: {now}" + \
        (f" · Запросил: {generated_by}" if generated_by else "")
    story.append(P(footer, small))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=14 * mm, rightMargin=14 * mm,
        topMargin=12 * mm, bottomMargin=12 * mm,
        title=f"Инцидент #{getattr(case, 'case_id', '')} — карточка данных",
        author=generated_by or "IRIS",
    )
    doc.build(story)
    return buf.getvalue()


def incident_card_filename(case):
    """Suggested download file name for the exported PDF."""
    safe = "".join(c for c in (case.name or f"case-{case.case_id}") if c.isalnum()
                   or c in ("-", "_", " "))
    safe = safe.strip().replace(" ", "_")[:60]
    return f"incident_card_{case.case_id}_{safe}.pdf"
