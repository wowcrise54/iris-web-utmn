"""Appendix 4 incident-card field definitions, shared by API and exports."""


def options(items):
    return [{"value": v, "label_ru": ru, "label_en": en} for v, ru, en in items]


SECTIONS = []


def section(identifier, ru, en, specs):
    fields = []
    for key, label_ru, label_en, kind, auto, choices in specs:
        item = dict(key=key, label_ru=label_ru, label_en=label_en, type=kind, auto=auto)
        if choices:
            item["options"] = options(choices)
        fields.append(item)
    SECTIONS.append(dict(id=identifier, label_ru=ru, label_en=en, fields=fields))


def f(key, ru, en, kind="textarea", auto=False, choices=None):
    return (key, ru, en, kind, auto, choices)


section(
    "general",
    "Общие сведения",
    "General information",
    [
        f("id", "Идентификатор", "Identifier", "text", True),
        f("title", "Название инцидента", "Incident title", "text", True),
        f(
            "incident_at",
            "Дата и время инцидента",
            "Incident date and time",
            "datetime",
            True,
        ),
        f("detection_source", "Источник обнаружения", "Detection source", "text", True),
        f("external_id", "Внешний идентификатор", "External identifier", "text", True),
        f("criticality", "Критичность", "Criticality", "text", True),
    ],
)
section(
    "reporter",
    "Заявитель",
    "Reporter",
    [
        f("reporter_name", "ФИО", "Name", "text"),
        f("reporter_phone", "Телефон", "Phone", "text"),
        f("reporter_email", "Электронная почта", "Email", "text"),
        f("reporter_address", "Адрес", "Address", "text"),
        f(
            "reporter_organization",
            "Организация заявителя",
            "Reporter organization",
            "text",
        ),
        f("organization", "Организация", "Organization", "text", True),
    ],
)
section(
    "description",
    "Описание и категоризация",
    "Description and classification",
    [
        f("description", "Описание инцидента", "Incident description", auto=True),
        f("affected_assets", "Затронутые активы", "Affected assets", auto=True),
        f("occurred_at", "Возникновение", "Occurred at", "datetime"),
        f("detected_at", "Обнаружение", "Detected at", "datetime"),
        f("notified_at", "Уведомление", "Notified at", "datetime"),
        f(
            "categories",
            "Категории инцидента",
            "Incident categories",
            "multichoice",
            choices=[
                (
                    1,
                    "Отказ систем, сервисов и сетей в обслуживании",
                    "Systems, services and networks denial of service",
                ),
                (
                    2,
                    "Внедрение в сетевую инфраструктуру Университета вредоносного программного обеспечения",
                    "Malware introduced into the University's network infrastructure",
                ),
                (
                    3,
                    "Несанкционированные попытки доступа в систему",
                    "Unauthorized attempts to access the system",
                ),
                (
                    4,
                    "Действия, связанные с определением потенциальных целей атаки и получением представления о сервисах, работающих на идентифицированных целях атаки",
                    "Identifying potential attack targets and their running services",
                ),
                (
                    5,
                    "Несоблюдение пользователями ИС требований ОРД по защите информации",
                    "Information system users failing to comply with information protection policies",
                ),
                (
                    6,
                    "Нарушение мер физической защиты ИС",
                    "Violation of information system physical protection measures",
                ),
                (
                    7,
                    "Непреднамеренное воздействие пользователя на ИС, пользовательская ошибка",
                    "Unintentional user impact on the information system, user error",
                ),
                (8, "Иной тип инцидента", "Other incident type"),
            ],
        ),
        f("completed", "Инцидент завершён", "Incident completed", "boolean"),
        f(
            "unacceptable_event",
            "Недопустимое событие",
            "Unacceptable event",
            "boolean",
        ),
        f(
            "unacceptable_event_kinds",
            "Виды недопустимых событий",
            "Unacceptable event kinds",
            "multichoice",
            choices=[
                (
                    "personal_data_leak",
                    "Утечка персональных данных",
                    "Personal data leak",
                ),
                (
                    "confidential_information_leak",
                    "Утечка конфиденциальной информации",
                    "Confidential information leak",
                ),
                (
                    "business_interruption",
                    "Сбой или остановка операционных процессов из-за недоступности поддерживающих их информационных систем",
                    "Operational process disruption or stoppage due to supporting information systems being unavailable",
                ),
                (
                    "public_system_unavailability",
                    "Недоступность публичных систем, в которых размещена информация согласно требованиям регулятора",
                    "Unavailability of public systems hosting information required by regulators",
                ),
                (
                    "financial_loss",
                    "Вывод/потеря денежных средств со счета Университета",
                    "Withdrawal or loss of funds from the University's account",
                ),
                (
                    "unlawful_publication",
                    "Публикация/предоставление недостоверной или противоправной информации",
                    "Publication or provision of false or unlawful information",
                ),
            ],
        ),
        f("vulnerabilities", "Уязвимости", "Vulnerabilities"),
    ],
)
TYPE_GROUPS = [
    (
        "intentional",
        "Умышленные",
        "Intentional",
        [
            ("theft", "Хищение", "Theft"),
            ("fraud", "Мошенничество", "Fraud"),
            ("sabotage", "Саботаж/физический ущерб", "Sabotage/physical damage"),
            ("malware", "Вредоносное ПО", "Malware"),
            ("unlawful_access", "Неправомерный доступ", "Unlawful access"),
            (
                "resource_use",
                "Неправомерное использование ресурсов",
                "Unlawful resource use",
            ),
            (
                "destruction",
                "Неправомерное уничтожение информации",
                "Unlawful information destruction",
            ),
            ("other", "Прочее", "Other"),
        ],
    ),
    (
        "accidental",
        "Случайные",
        "Accidental",
        [
            (
                "hardware",
                "Отказ аппаратного обеспечения/средств связи",
                "Hardware/communications failure",
            ),
            ("software_failure", "Сбой программного обеспечения", "Software failure"),
            ("user_error", "Ошибка пользователя", "User error"),
            ("communication_failure", "Отказ связи", "Communication failure"),
            ("power_failure", "Отказ электропитания", "Power failure"),
            ("service_loss", "Потеря сервиса", "Service loss"),
            (
                "hardware_support_error",
                "Ошибка поддержки аппаратного обеспечения",
                "Hardware support error",
            ),
            (
                "software_support_error",
                "Ошибка поддержки программного обеспечения",
                "Software support error",
            ),
            ("staffing", "Недостаток персонала", "Staffing shortage"),
            ("operational_error", "Ошибка эксплуатации", "Operational error"),
            ("design_error", "Ошибка проектирования", "Design error"),
            ("other", "Прочее", "Other"),
        ],
    ),
    (
        "natural",
        "Природные и техногенные",
        "Natural and technogenic",
        [
            ("fire", "Пожар", "Fire"),
            ("flood", "Наводнение", "Flood"),
            ("disaster", "Стихийное бедствие", "Disaster"),
            ("technogenic", "Техногенное событие", "Technogenic"),
            ("other", "Прочее", "Other"),
        ],
    ),
]
section(
    "types",
    "Типы инцидента",
    "Incident types",
    [
        f(
            "incident_types",
            "Типы инцидента",
            "Incident types",
            "multichoice",
            choices=[
                (prefix + "_" + key, ru + ": " + lr, en + ": " + le)
                for prefix, ru, en, items in TYPE_GROUPS
                for key, lr, le in items
            ]
            + [("unknown", "Неизвестно", "Unknown")],
        )
    ],
)
section(
    "assets",
    "Сведения об активах и последствия",
    "Assets and impact",
    [
        f("asset_data", "Данные", "Data"),
        f("asset_hardware", "Аппаратное обеспечение", "Hardware"),
        f("asset_software", "Программное обеспечение", "Software"),
        f("asset_communications", "Средства связи", "Communications"),
        f("asset_documentation", "Документация", "Documentation"),
        f(
            "business_impact",
            "Негативное воздействие на бизнес-процессы",
            "Impact on business processes",
        ),
    ],
)
section(
    "priority",
    "Приоритизация",
    "Prioritization",
    [
        f(
            "prioritization_type",
            "Тип системы",
            "System type",
            "choice",
            choices=[
                ("auxiliary", "Вспомогательный", "Auxiliary"),
                ("key", "Ключевой", "Key"),
                ("target", "Целевой", "Target"),
            ],
        ),
        f(
            "category8_importance",
            "Важность категории 8",
            "Category 8 importance",
            "choice",
            choices=[
                ("low", "Низкая", "Low"),
                ("medium", "Средняя", "Medium"),
                ("high", "Высокая", "High"),
            ],
        ),
        f("category8_reason", "Обоснование категории 8", "Category 8 rationale"),
    ],
)
section(
    "investigation",
    "Расследование",
    "Investigation",
    [
        f(
            "investigation_started_at",
            "Начало расследования",
            "Investigation started",
            "datetime",
        ),
        f("incident_ended_at", "Окончание инцидента", "Incident ended", "datetime"),
        f("impact_ended_at", "Окончание воздействия", "Impact ended", "datetime"),
        f(
            "investigation_ended_at",
            "Окончание расследования",
            "Investigation ended",
            "datetime",
        ),
        f("investigators", "Участники расследования", "Investigators", "people"),
        f("report_url", "Ссылка на отчёт", "Report URL", "text"),
        f("report_location", "Место хранения отчёта", "Report location", "text"),
    ],
)
section(
    "response",
    "Итоги и ознакомление",
    "Response and acknowledgement",
    [
        f(
            "actors",
            "Причастные лица",
            "Actors",
            "multichoice",
            choices=[
                ("individual", "Физическое лицо", "Individual"),
                ("organized_group", "Организованная группа", "Organized group"),
                (
                    "legal_organization",
                    "Легально учреждённая организация/учреждение",
                    "Legally established organization/institution",
                ),
                ("unknown", "Неизвестен", "Unknown"),
                (
                    "none",
                    "Нет виновного (природные факторы, отказ оборудования)",
                    "No offender (natural factors, equipment failure)",
                ),
            ],
        ),
        f(
            "motives",
            "Мотивы",
            "Motives",
            "multichoice",
            choices=[
                (
                    "financial",
                    "Криминальная/финансовая выгода",
                    "Criminal/financial gain",
                ),
                ("political", "Политика/терроризм", "Politics/terrorism"),
                ("entertainment", "Развлечение/хакерство", "Entertainment/hacking"),
                ("revenge", "Реванш", "Revenge"),
                ("other", "Другие мотивы", "Other motives"),
            ],
        ),
        f("offender_description", "Описание нарушителя", "Offender description"),
        f("performed_actions", "Выполненные действия", "Performed actions", auto=True),
        f("planned_actions", "Запланированные действия", "Planned actions", auto=True),
        f(
            "preventive_measures",
            "Выработанные организационные и технические меры",
            "Organizational and technical measures",
        ),
        f("prepared_by", "Составил", "Prepared by", "text"),
        f("prepared_position", "Должность составителя", "Preparer position", "text"),
        f("acquainted", "Ознакомлены", "Acknowledged by", "people"),
    ],
)
section(
    "technical",
    "Дополнительные сведения",
    "Supplemental information",
    [
        f("mitre_tactic", "Тактика MITRE", "MITRE tactic", "text"),
        f("mitre_technique", "Техника MITRE", "MITRE technique", "text"),
        f("mitre_subtechnique", "Подтехника MITRE", "MITRE subtechnique", "text"),
        f("attack_source", "Источник атаки", "Attack source", auto=True),
        f("attack_target", "Цель атаки", "Attack target", auto=True),
        f("account", "Учётная запись", "Account", "text"),
        f("additional_info", "Дополнительная информация", "Additional information"),
        f("hashes", "Хеши", "Hashes", auto=True),
        f("files", "Файлы", "Files", auto=True),
    ],
)
FIELDS = {field["key"]: field for section in SECTIONS for field in section["fields"]}
