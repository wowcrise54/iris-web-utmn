"""Appendix 4 logical blocks and normalization of legacy card values."""

from copy import deepcopy

SECTIONS = [
    {
        "id": "general",
        "label_ru": "Общие сведения об инциденте",
        "label_en": "General incident information",
        "fields": [
            {
                "key": "id",
                "label_ru": "Идентификатор инцидента",
                "label_en": "Identifier",
                "type": "text",
                "auto": True,
            },
            {
                "key": "incident_at",
                "label_ru": "Дата и время инцидента",
                "label_en": "Incident date and time",
                "type": "datetime",
                "auto": True,
            },
            {
                "key": "detection_source",
                "label_ru": "Источник инцидента/средство обнаружения",
                "label_en": "Detection source",
                "type": "text",
                "auto": True,
            },
            {
                "key": "criticality",
                "label_ru": "Уровень критичности",
                "label_en": "Criticality",
                "type": "choice",
                "auto": True,
                "options": [
                    {"value": "Высокий", "label_ru": "Высокий", "label_en": "Высокий"},
                    {"value": "Средний", "label_ru": "Средний", "label_en": "Средний"},
                    {"value": "Низкий", "label_ru": "Низкий", "label_en": "Низкий"},
                ],
            },
        ],
    },
    {
        "id": "reporter",
        "label_ru": "Информация о сообщающем лице",
        "label_en": "Reporter information",
        "fields": [
            {
                "key": "reporter_name",
                "label_ru": "ФИО",
                "label_en": "Name",
                "type": "text",
                "auto": False,
            },
            {
                "key": "reporter_phone",
                "label_ru": "Телефон",
                "label_en": "Phone",
                "type": "text",
                "auto": False,
            },
            {
                "key": "reporter_email",
                "label_ru": "Эл. почта",
                "label_en": "Email",
                "type": "text",
                "auto": False,
            },
            {
                "key": "incident_location",
                "label_ru": "Адрес, по которому был зафиксирован инцидент",
                "label_en": "Address",
                "type": "text",
                "auto": False,
            },
            {
                "key": "reporter_organization",
                "label_ru": "Организация",
                "label_en": "Reporter organization",
                "type": "text",
                "auto": False,
            },
        ],
    },
    {
        "id": "description",
        "label_ru": "Описание инцидента",
        "label_en": "Incident description",
        "fields": [
            {
                "key": "description",
                "label_ru": "Описание инцидента",
                "label_en": "Incident description",
                "type": "textarea",
                "auto": True,
            },
            {
                "key": "affected_assets",
                "label_ru": "Пораженные активы",
                "label_en": "Affected assets",
                "type": "textarea",
                "auto": False,
            },
        ],
    },
    {
        "id": "details",
        "label_ru": "Детали инцидента",
        "label_en": "Incident details",
        "fields": [
            {
                "key": "occurred_at",
                "label_ru": "Дата и время возникновения инцидента",
                "label_en": "Occurred at",
                "type": "datetime",
                "auto": True,
            },
            {
                "key": "detected_at",
                "label_ru": "Дата и время обнаружения инцидента",
                "label_en": "Detected at",
                "type": "datetime",
                "auto": False,
            },
            {
                "key": "notified_at",
                "label_ru": "Дата и время отправки сообщения об инциденте",
                "label_en": "Notified at",
                "type": "datetime",
                "auto": False,
            },
            {
                "key": "categories",
                "label_ru": "Категория инцидента",
                "label_en": "Incident categories",
                "type": "multichoice",
                "auto": False,
                "options": [
                    {
                        "value": 1,
                        "label_ru": "Отказ систем, сервисов и сетей в обслуживании",
                        "label_en": "Systems, services and networks denial of service",
                    },
                    {
                        "value": 2,
                        "label_ru": "Внедрение в сетевую инфраструктуру Университета "
                        "вредоносного программного обеспечения",
                        "label_en": "Malware introduced into the University's network "
                        "infrastructure",
                    },
                    {
                        "value": 3,
                        "label_ru": "Несанкционированные попытки доступа в систему",
                        "label_en": "Unauthorized attempts to access the system",
                    },
                    {
                        "value": 4,
                        "label_ru": "Действия, связанные с определением потенциальных целей "
                        "атаки и получением представления о сервисах, работающих на "
                        "идентифицированных целях атаки",
                        "label_en": "Identifying potential attack targets and their running "
                        "services",
                    },
                    {
                        "value": 5,
                        "label_ru": "Несоблюдение пользователями ИС требований ОРД по защите "
                        "информации",
                        "label_en": "Information system users failing to comply with "
                        "information protection policies",
                    },
                    {
                        "value": 6,
                        "label_ru": "Нарушение мер физической защиты ИС",
                        "label_en": "Violation of information system physical protection "
                        "measures",
                    },
                    {
                        "value": 7,
                        "label_ru": "Непреднамеренное воздействие пользователя на ИС, "
                        "пользовательская ошибка",
                        "label_en": "Unintentional user impact on the information system, user "
                        "error",
                    },
                    {
                        "value": 8,
                        "label_ru": "Иной тип инцидента",
                        "label_en": "Other incident type",
                    },
                ],
            },
            {
                "key": "completed",
                "label_ru": "Закончился ли инцидент (отметить)",
                "label_en": "Incident completed",
                "type": "boolean",
                "auto": False,
            },
        ],
    },
    {
        "id": "unacceptable_event",
        "label_ru": "Недопустимое событие",
        "label_en": "Unacceptable event",
        "fields": [
            {
                "key": "unacceptable_event",
                "label_ru": "Недопустимое событие (отметить и выбрать ниже)",
                "label_en": "Unacceptable event",
                "type": "boolean",
                "auto": False,
            },
            {
                "key": "unacceptable_event_kinds",
                "label_ru": "Недопустимое событие",
                "label_en": "Unacceptable event kinds",
                "type": "multichoice",
                "auto": False,
                "options": [
                    {
                        "value": "personal_data_leak",
                        "label_ru": "Утечка персональных данных",
                        "label_en": "Personal data leak",
                    },
                    {
                        "value": "confidential_information_leak",
                        "label_ru": "Утечка конфиденциальной информации",
                        "label_en": "Confidential information leak",
                    },
                    {
                        "value": "business_interruption",
                        "label_ru": "Сбой или остановка операционных процессов из-за "
                        "недоступности поддерживающих их информационных систем",
                        "label_en": "Operational process disruption or stoppage due to "
                        "supporting information systems being unavailable",
                    },
                    {
                        "value": "public_system_unavailability",
                        "label_ru": "Недоступность публичных систем, в которых размещена "
                        "информация согласно требованиям регулятора",
                        "label_en": "Unavailability of public systems hosting information "
                        "required by regulators",
                    },
                    {
                        "value": "financial_loss",
                        "label_ru": "Вывод/потеря денежных средств со счета Университета",
                        "label_en": "Withdrawal or loss of funds from the University's account",
                    },
                    {
                        "value": "unlawful_publication",
                        "label_ru": "Публикация/предоставление недостоверной или противоправной "
                        "информации",
                        "label_en": "Publication or provision of false or unlawful "
                        "information",
                    },
                ],
            },
        ],
    },
    {
        "id": "vulnerabilities",
        "label_ru": "Идентифицированные уязвимости",
        "label_en": "Identified vulnerabilities",
        "fields": [
            {
                "key": "vulnerabilities",
                "label_ru": "Идентифицированные уязвимости",
                "label_en": "Vulnerabilities",
                "type": "textarea",
                "auto": False,
            }
        ],
    },
    {
        "id": "types",
        "label_ru": "Тип инцидента",
        "label_en": "Incident type",
        "fields": [
            {
                "key": "incident_types",
                "label_ru": "Тип инцидента",
                "label_en": "Incident types",
                "type": "multichoice",
                "auto": False,
                "options": [
                    {
                        "value": "intentional_theft",
                        "label_ru": "Хищение",
                        "label_en": "Intentional: Theft",
                        "group_ru": "Преднамеренный",
                        "group_en": "Intentional",
                    },
                    {
                        "value": "intentional_fraud",
                        "label_ru": "Мошенничество",
                        "label_en": "Intentional: Fraud",
                        "group_ru": "Преднамеренный",
                        "group_en": "Intentional",
                    },
                    {
                        "value": "intentional_sabotage",
                        "label_ru": "Саботаж/Физический ущерб",
                        "label_en": "Intentional: Sabotage/physical damage",
                        "group_ru": "Преднамеренный",
                        "group_en": "Intentional",
                    },
                    {
                        "value": "intentional_malware",
                        "label_ru": "Вредоносное программное обеспечение",
                        "label_en": "Intentional: Malware",
                        "group_ru": "Преднамеренный",
                        "group_en": "Intentional",
                    },
                    {
                        "value": "intentional_unlawful_access",
                        "label_ru": "Неправомерный доступ",
                        "label_en": "Intentional: Unlawful access",
                        "group_ru": "Преднамеренный",
                        "group_en": "Intentional",
                    },
                    {
                        "value": "intentional_resource_use",
                        "label_ru": "Неправомерное использование ресурсов",
                        "label_en": "Intentional: Unlawful resource use",
                        "group_ru": "Преднамеренный",
                        "group_en": "Intentional",
                    },
                    {
                        "value": "intentional_destruction",
                        "label_ru": "Неправомерное уничтожение информации",
                        "label_en": "Intentional: Unlawful information destruction",
                        "group_ru": "Преднамеренный",
                        "group_en": "Intentional",
                    },
                    {
                        "value": "intentional_other",
                        "label_ru": "Другой случай",
                        "label_en": "Intentional: Other",
                        "group_ru": "Преднамеренный",
                        "group_en": "Intentional",
                    },
                    {
                        "value": "accidental_hardware",
                        "label_ru": "Отказ вычислительной и коммуникационной техники",
                        "label_en": "Accidental: Hardware/communications failure",
                        "group_ru": "Случайный/непреднамеренный",
                        "group_en": "Accidental/unintentional",
                    },
                    {
                        "value": "accidental_software_failure",
                        "label_ru": "Отказ/ошибка ПО",
                        "label_en": "Accidental: Software failure",
                        "group_ru": "Случайный/непреднамеренный",
                        "group_en": "Accidental/unintentional",
                    },
                    {
                        "value": "accidental_user_error",
                        "label_ru": "Ошибка пользователя",
                        "label_en": "Accidental: User error",
                        "group_ru": "Случайный/непреднамеренный",
                        "group_en": "Accidental/unintentional",
                    },
                    {
                        "value": "accidental_communication_failure",
                        "label_ru": "Отказ связи",
                        "label_en": "Accidental: Communication failure",
                        "group_ru": "Случайный/непреднамеренный",
                        "group_en": "Accidental/unintentional",
                    },
                    {
                        "value": "accidental_power_failure",
                        "label_ru": "Отказ системы электропитания",
                        "label_en": "Accidental: Power failure",
                        "group_ru": "Случайный/непреднамеренный",
                        "group_en": "Accidental/unintentional",
                    },
                    {
                        "value": "accidental_service_loss",
                        "label_ru": "Потеря существенных сервисов",
                        "label_en": "Accidental: Service loss",
                        "group_ru": "Случайный/непреднамеренный",
                        "group_en": "Accidental/unintentional",
                    },
                    {
                        "value": "accidental_hardware_support_error",
                        "label_ru": "Ошибка аппаратной поддержки",
                        "label_en": "Accidental: Hardware support error",
                        "group_ru": "Случайный/непреднамеренный",
                        "group_en": "Accidental/unintentional",
                    },
                    {
                        "value": "accidental_software_support_error",
                        "label_ru": "Ошибка поддержки ПО",
                        "label_en": "Accidental: Software support error",
                        "group_ru": "Случайный/непреднамеренный",
                        "group_en": "Accidental/unintentional",
                    },
                    {
                        "value": "accidental_staffing",
                        "label_ru": "Недостаточное кадровое обеспечение",
                        "label_en": "Accidental: Staffing shortage",
                        "group_ru": "Случайный/непреднамеренный",
                        "group_en": "Accidental/unintentional",
                    },
                    {
                        "value": "accidental_operational_error",
                        "label_ru": "Операционная ошибка",
                        "label_en": "Accidental: Operational error",
                        "group_ru": "Случайный/непреднамеренный",
                        "group_en": "Accidental/unintentional",
                    },
                    {
                        "value": "accidental_design_error",
                        "label_ru": "Ошибка конструкции",
                        "label_en": "Accidental: Design error",
                        "group_ru": "Случайный/непреднамеренный",
                        "group_en": "Accidental/unintentional",
                    },
                    {
                        "value": "accidental_other",
                        "label_ru": "Другой случай",
                        "label_en": "Accidental: Other",
                        "group_ru": "Случайный/непреднамеренный",
                        "group_en": "Accidental/unintentional",
                    },
                    {
                        "value": "natural_fire",
                        "label_ru": "Пожар",
                        "label_en": "Natural and technogenic: Fire",
                        "group_ru": "Естественный",
                        "group_en": "Natural",
                    },
                    {
                        "value": "natural_flood",
                        "label_ru": "Наводнение",
                        "label_en": "Natural and technogenic: Flood",
                        "group_ru": "Естественный",
                        "group_en": "Natural",
                    },
                    {
                        "value": "natural_disaster",
                        "label_ru": "Стихийное бедствие",
                        "label_en": "Natural and technogenic: Disaster",
                        "group_ru": "Естественный",
                        "group_en": "Natural",
                    },
                    {
                        "value": "natural_fire_repeat",
                        "label_ru": "Пожар",
                        "label_en": "Fire",
                        "group_ru": "Естественный",
                        "group_en": "Natural",
                    },
                    {
                        "value": "natural_technogenic",
                        "label_ru": "Техногенная авария",
                        "label_en": "Natural and technogenic: Technogenic",
                        "group_ru": "Естественный",
                        "group_en": "Natural",
                    },
                    {
                        "value": "natural_other_phenomena",
                        "label_ru": "Другие явления, не зависящие от человека",
                        "label_en": "Other phenomena independent of humans",
                        "group_ru": "Естественный",
                        "group_en": "Natural",
                    },
                    {
                        "value": "natural_technogenic_repeat",
                        "label_ru": "Техногенная авария",
                        "label_en": "Technogenic accident",
                        "group_ru": "Естественный",
                        "group_en": "Natural",
                    },
                    {
                        "value": "natural_other",
                        "label_ru": "Другой случай",
                        "label_en": "Natural and technogenic: Other",
                        "group_ru": "Естественный",
                        "group_en": "Natural",
                    },
                    {
                        "value": "unknown",
                        "label_ru": "Неизвестно",
                        "label_en": "Unknown",
                        "group_ru": "",
                    },
                ],
            }
        ],
    },
    {
        "id": "assets",
        "label_ru": "Пораженные активы",
        "label_en": "Affected assets",
        "fields": [
            {
                "key": "asset_data",
                "label_ru": "Информация/Данные",
                "label_en": "Data",
                "type": "text",
                "auto": False,
            },
            {
                "key": "asset_hardware",
                "label_ru": "Оборудование",
                "label_en": "Hardware",
                "type": "text",
                "auto": False,
            },
            {
                "key": "asset_software",
                "label_ru": "Программное обеспечение",
                "label_en": "Software",
                "type": "text",
                "auto": False,
            },
            {
                "key": "asset_communications",
                "label_ru": "Средства связи",
                "label_en": "Communications",
                "type": "text",
                "auto": False,
            },
            {
                "key": "asset_documentation",
                "label_ru": "Документация",
                "label_en": "Documentation",
                "type": "text",
                "auto": False,
            },
        ],
    },
    {
        "id": "impact",
        "label_ru": "Негативное воздействие/влияние инцидента на бизнес-процессы",
        "label_en": "Impact on business processes",
        "fields": [
            {
                "key": "business_impact",
                "label_ru": "Негативное воздействие/влияние инцидента на бизнес-процессы",
                "label_en": "Impact on business processes",
                "type": "textarea",
                "auto": False,
            }
        ],
    },
    {
        "id": "priority",
        "label_ru": "Приоритизация инцидента",
        "label_en": "Incident prioritization",
        "fields": [
            {
                "key": "prioritization_type",
                "label_ru": "Тип системы",
                "label_en": "System type",
                "type": "choice",
                "auto": False,
                "options": [
                    {
                        "value": "auxiliary",
                        "label_ru": "Вспомогательный",
                        "label_en": "Auxiliary",
                    },
                    {"value": "key", "label_ru": "Ключевой", "label_en": "Key"},
                    {"value": "target", "label_ru": "Целевой", "label_en": "Target"},
                ],
            },
            {
                "key": "priority_override",
                "label_ru": "Приоритет инцидента по таблице",
                "label_en": "Incident priority",
                "type": "choice",
                "auto": True,
                "options": [
                    {"value": 1, "label_ru": "1", "label_en": "1"},
                    {"value": 2, "label_ru": "2", "label_en": "2"},
                    {"value": 3, "label_ru": "3", "label_en": "3"},
                    {"value": 4, "label_ru": "4", "label_en": "4"},
                    {"value": 5, "label_ru": "5", "label_en": "5"},
                    {"value": 6, "label_ru": "6", "label_en": "6"},
                    {"value": 7, "label_ru": "7", "label_en": "7"},
                    {"value": 8, "label_ru": "8", "label_en": "8"},
                    {"value": 9, "label_ru": "9", "label_en": "9"},
                ],
            },
        ],
    },
    {
        "id": "investigation",
        "label_ru": "Расследование инцидента",
        "label_en": "Incident investigation",
        "fields": [
            {
                "key": "investigation_started_at",
                "label_ru": "Дата начала расследования инцидента",
                "label_en": "Investigation started",
                "type": "datetime",
                "auto": False,
            },
            {
                "key": "investigators",
                "label_ru": "ФИО лица (лиц), проводившего (их) расследование инцидента",
                "label_en": "Investigators",
                "type": "textarea",
                "auto": False,
            },
            {
                "key": "incident_ended_at",
                "label_ru": "Дата окончания инцидента",
                "label_en": "Incident ended",
                "type": "datetime",
                "auto": False,
            },
            {
                "key": "impact_ended_at",
                "label_ru": "Дата окончания воздействия",
                "label_en": "Impact ended",
                "type": "datetime",
                "auto": False,
            },
            {
                "key": "investigation_ended_at",
                "label_ru": "Дата завершения расследования инцидента",
                "label_en": "Investigation ended",
                "type": "datetime",
                "auto": False,
            },
            {
                "key": "report_url",
                "label_ru": "Ссылка и место хранения отчета о расследовании",
                "label_en": "Report URL",
                "type": "text",
                "auto": False,
            },
        ],
    },
    {
        "id": "actors",
        "label_ru": "Причастные лица",
        "label_en": "Involved parties",
        "fields": [
            {
                "key": "actors",
                "label_ru": "Причастные лица",
                "label_en": "Actors",
                "type": "multichoice",
                "auto": False,
                "options": [
                    {
                        "value": "individual",
                        "label_ru": "Физическое лицо",
                        "label_en": "Individual",
                    },
                    {
                        "value": "organized_group",
                        "label_ru": "Организованная группа",
                        "label_en": "Organized group",
                    },
                    {
                        "value": "legal_organization",
                        "label_ru": "Легально учрежденная организация/учреждение",
                        "label_en": "Legally established organization/institution",
                    },
                    {
                        "value": "unknown",
                        "label_ru": "Неизвестен",
                        "label_en": "Unknown",
                    },
                    {
                        "value": "none",
                        "label_ru": "Нет виновного (природные факторы, отказ оборудования)",
                        "label_en": "No offender (natural factors, equipment failure)",
                    },
                ],
            }
        ],
    },
    {
        "id": "motives",
        "label_ru": "Мотивация",
        "label_en": "Motivation",
        "fields": [
            {
                "key": "motives",
                "label_ru": "Мотивация",
                "label_en": "Motives",
                "type": "multichoice",
                "auto": False,
                "options": [
                    {
                        "value": "financial",
                        "label_ru": "Криминальная/Финансовая выгода",
                        "label_en": "Criminal/financial gain",
                    },
                    {
                        "value": "political",
                        "label_ru": "Политика/Терроризм",
                        "label_en": "Politics/terrorism",
                    },
                    {
                        "value": "entertainment",
                        "label_ru": "Развлечение/Хакерство",
                        "label_en": "Entertainment/hacking",
                    },
                    {"value": "revenge", "label_ru": "Реванш", "label_en": "Revenge"},
                    {
                        "value": "other",
                        "label_ru": "Другие мотивы",
                        "label_en": "Other motives",
                    },
                ],
            }
        ],
    },
    {
        "id": "offender",
        "label_ru": "Описание нарушителя",
        "label_en": "Offender description",
        "fields": [
            {
                "key": "offender_description",
                "label_ru": "Описание нарушителя",
                "label_en": "Offender description",
                "type": "textarea",
                "auto": False,
            }
        ],
    },
    {
        "id": "performed_actions",
        "label_ru": "Действия, предпринятые для разрешения инцидента",
        "label_en": "Actions taken to resolve the incident",
        "fields": [
            {
                "key": "performed_actions",
                "label_ru": "Действия, предпринятые для разрешения инцидента",
                "label_en": "Performed actions",
                "type": "textarea",
                "auto": False,
            }
        ],
    },
    {
        "id": "planned_actions",
        "label_ru": "Действия, запланированные для разрешения инцидента",
        "label_en": "Actions planned to resolve the incident",
        "fields": [
            {
                "key": "planned_actions",
                "label_ru": "Действия, запланированные для разрешения инцидента",
                "label_en": "Planned actions",
                "type": "textarea",
                "auto": False,
            }
        ],
    },
    {
        "id": "measures",
        "label_ru": "Выработанные организационные и технические меры",
        "label_en": "Organizational and technical measures",
        "fields": [
            {
                "key": "preventive_measures",
                "label_ru": "Выработанные организационные и технические меры",
                "label_en": "Organizational and technical measures",
                "type": "textarea",
                "auto": False,
            }
        ],
    },
    {
        "id": "prepared",
        "label_ru": "Составил",
        "label_en": "Prepared by",
        "fields": [
            {
                "key": "prepared_by",
                "label_ru": "Составил",
                "label_en": "Prepared by",
                "type": "people",
                "auto": False,
            }
        ],
    },
    {
        "id": "acquainted",
        "label_ru": "С результатами проведенного расследования ознакомлен(ы):",
        "label_en": "Investigation results acknowledged by",
        "fields": [
            {
                "key": "acquainted",
                "label_ru": "С результатами проведенного расследования ознакомлен(ы):",
                "label_en": "Acknowledged by",
                "type": "people",
                "auto": False,
            }
        ],
    },
]

FIELDS = {f["key"]: f for s in SECTIONS for f in s["fields"]}


def normalize_criticality(value):
    """Known legacy/source labels only; never infer a level from arbitrary text."""
    if not isinstance(value, str):
        return None
    return {
        "high": "Высокий",
        "высокий": "Высокий",
        "высокая": "Высокий",
        "medium": "Средний",
        "средний": "Средний",
        "средняя": "Средний",
        "low": "Низкий",
        "низкий": "Низкий",
        "низкая": "Низкий",
    }.get(value.strip().casefold())


def normalize_preparers(fields):
    """Read old scalar author/position pairs as the new repeatable person rows."""
    result = deepcopy(fields or {})
    position = result.pop("prepared_position", {}) or {}
    entry = result.get("prepared_by") or {}
    name = entry.get("value")
    role = position.get("value")
    if isinstance(name, list):
        return result
    if isinstance(name, str) or (name is None and role):
        result["prepared_by"] = dict(
            entry,
            mode=entry.get("mode", "manual"),
            value=[{"name": name or "", "position": role or ""}]
            if name or role
            else None,
        )
    return result
