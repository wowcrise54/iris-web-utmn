"""Incident prioritization logic per the Tyumen State University Position
on security event monitoring and incident response.

Table 5.1 — importance (важность) from incident category and system type.
Table 5.2 — priority from system type and importance.

This module is pure Python with no framework dependencies so it can be
unit-tested in isolation.

Codes used:
  system type: 1 = целевая (target), 2 = ключевая (key), 3 = вспомогательная/иная (auxiliary)
  importance:  1 = высокая (high), 2 = средняя (medium), 3 = низкая (low)
  priority:    1 (highest) .. 9 (lowest)
"""

# Table 5.1 of the Position: (category_code, system_type_code) -> importance_code
IMPORTANCE_TABLE_5_1 = {
    # 1: отказ систем, сервисов и сетей в обслуживании
    (1, 3): 2, (1, 2): 1, (1, 1): 1,
    # 2: внедрение вредоносного ПО
    (2, 3): 1, (2, 2): 1, (2, 1): 1,
    # 3: несанкционированные попытки доступа
    (3, 3): 2, (3, 2): 1, (3, 1): 1,
    # 4: разведка / рекогносцировка
    (4, 3): 3, (4, 2): 2, (4, 1): 2,
    # 5: несоблюдение требований ОРД
    (5, 3): 3, (5, 2): 3, (5, 1): 2,
    # 6: нарушение мер физической защиты
    (6, 3): 3, (6, 2): 2, (6, 1): 2,
    # 7: ошибка пользователя
    (7, 3): 3, (7, 2): 3, (7, 1): 3,
    # 8: иной тип инцидента
    (8, 3): 3, (8, 2): 3, (8, 1): 3,
}

# Table 5.2 of the Position: (system_type_code, importance_code) -> priority
PRIORITY_TABLE_5_2 = {
    (1, 1): 1, (1, 2): 2, (1, 3): 4,  # target system
    (2, 1): 3, (2, 2): 5, (2, 3): 7,  # key system
    (3, 1): 6, (3, 2): 8, (3, 3): 9,  # auxiliary system
}


def calc_importance(category_code, system_type_code):
    """Return the importance code (1/2/3) per Table 5.1.

    Args:
        category_code: incident category code 1-8.
        system_type_code: system type code (1=target, 2=key, 3=auxiliary).

    Returns:
        Importance code 1 (high), 2 (medium) or 3 (low); None if unknown.
    """
    return IMPORTANCE_TABLE_5_1.get((int(category_code), int(system_type_code)))


def calc_priority(system_type_code, importance_code):
    """Return the priority level (1-9) per Table 5.2.

    Args:
        system_type_code: system type code (1=target, 2=key, 3=auxiliary).
        importance_code: importance code (1=high, 2=medium, 3=low).

    Returns:
        Priority level 1-9; None if the combination is unknown.
    """
    return PRIORITY_TABLE_5_2.get((int(system_type_code), int(importance_code)))


def calc_priority_from_category(category_code, system_type_code):
    """Full pipeline: category + system type -> (importance_code, priority).

    Returns:
        Tuple (importance_code, priority) or (None, None) if either table
        lookup fails.
    """
    importance = calc_importance(category_code, system_type_code)
    if importance is None:
        return None, None
    priority = calc_priority(system_type_code, importance)
    return importance, priority
