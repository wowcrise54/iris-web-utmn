#!/usr/bin/env python3
"""Unit tests for incident prioritization per the Tyumen State University
Position (Tables 5.1 and 5.2).

system type codes: 1=target (целевая), 2=key (ключевая), 3=auxiliary (вспомогательная)
importance codes:  1=high, 2=medium, 3=low
priority:          1 (highest) .. 9 (lowest)
"""
import importlib.util
import sys
from pathlib import Path

# Load the pure module directly by path — it has no framework dependencies,
# and importing it through the `app` package would pull in Flask deps that
# are not installed on the test host.
_MODULE_PATH = Path(__file__).parent.parent.parent.parent / "source" / "app" / "blueprints" / "incident_management" / "prioritization.py"
_spec = importlib.util.spec_from_file_location("incident_prioritization", _MODULE_PATH)
prioritization = importlib.util.module_from_spec(_spec)
sys.modules["incident_prioritization"] = prioritization
_spec.loader.exec_module(prioritization)

IMPORTANCE_TABLE_5_1 = prioritization.IMPORTANCE_TABLE_5_1
PRIORITY_TABLE_5_2 = prioritization.PRIORITY_TABLE_5_2
calc_importance = prioritization.calc_importance
calc_priority = prioritization.calc_priority
calc_priority_from_category = prioritization.calc_priority_from_category


class TestImportanceTable51:
    """Table 5.1 — importance from category and system type."""

    # (category, system_type_aux, system_type_key, system_type_target)
    EXPECTED = {
        1: (2, 1, 1),  # service outage: medium/high/high
        2: (1, 1, 1),  # malware: high everywhere
        3: (2, 1, 1),  # unauthorized access: medium/high/high
        4: (3, 2, 2),  # recon: low/medium/medium
        5: (3, 3, 2),  # policy violation: low/low/medium
        6: (3, 2, 2),  # physical security: low/medium/medium
        7: (3, 3, 3),  # user error: low everywhere
        8: (3, 3, 3),  # other: low everywhere
    }

    def test_all_24_combinations(self):
        for cat in range(1, 9):
            aux, key, target = self.EXPECTED[cat]
            assert calc_importance(cat, 3) == aux, f"category {cat} auxiliary"
            assert calc_importance(cat, 2) == key, f"category {cat} key"
            assert calc_importance(cat, 1) == target, f"category {cat} target"

    def test_malware_always_high(self):
        assert calc_importance(2, 1) == 1
        assert calc_importance(2, 2) == 1
        assert calc_importance(2, 3) == 1

    def test_unknown_category_returns_none(self):
        assert calc_importance(99, 1) is None
        assert calc_importance(0, 1) is None

    def test_unknown_system_type_returns_none(self):
        assert calc_importance(1, 99) is None

    def test_table_has_all_24_entries(self):
        assert len(IMPORTANCE_TABLE_5_1) == 24


class TestPriorityTable52:
    """Table 5.2 — priority from system type and importance."""

    EXPECTED = {
        (1, 1): 1, (1, 2): 2, (1, 3): 4,  # target
        (2, 1): 3, (2, 2): 5, (2, 3): 7,  # key
        (3, 1): 6, (3, 2): 8, (3, 3): 9,  # auxiliary
    }

    def test_all_9_combinations(self):
        for (st, imp), expected in self.EXPECTED.items():
            assert calc_priority(st, imp) == expected

    def test_priority_1_is_target_high(self):
        assert calc_priority(1, 1) == 1

    def test_priority_9_is_auxiliary_low(self):
        assert calc_priority(3, 3) == 9

    def test_unknown_returns_none(self):
        assert calc_priority(99, 1) is None
        assert calc_priority(1, 99) is None

    def test_table_has_all_9_entries(self):
        assert len(PRIORITY_TABLE_5_2) == 9


class TestCombinedPipeline:
    """Full pipeline: category + system type -> (importance, priority)."""

    # (category, system_type) -> (importance, priority)
    EXPECTED = {
        (1, 1): (1, 1), (1, 2): (1, 3), (1, 3): (2, 8),
        (2, 1): (1, 1), (2, 2): (1, 3), (2, 3): (1, 6),
        (3, 1): (1, 1), (3, 2): (1, 3), (3, 3): (2, 8),
        (4, 1): (2, 2), (4, 2): (2, 5), (4, 3): (3, 9),
        (5, 1): (2, 2), (5, 2): (3, 7), (5, 3): (3, 9),
        (6, 1): (2, 2), (6, 2): (2, 5), (6, 3): (3, 9),
        (7, 1): (3, 4), (7, 2): (3, 7), (7, 3): (3, 9),
        (8, 1): (3, 4), (8, 2): (3, 7), (8, 3): (3, 9),
    }

    def test_all_24_combinations(self):
        for (cat, st), expected in self.EXPECTED.items():
            got = calc_priority_from_category(cat, st)
            assert got == expected, f"category {cat}, system type {st}: {got} != {expected}"

    def test_ransomware_on_target_system_is_priority_1(self):
        assert calc_priority_from_category(2, 1) == (1, 1)

    def test_user_error_on_auxiliary_is_priority_9(self):
        assert calc_priority_from_category(7, 3) == (3, 9)

    def test_invalid_input_returns_none_pair(self):
        assert calc_priority_from_category(99, 1) == (None, None)

    def test_accepts_string_codes(self):
        assert calc_priority_from_category("2", "1") == (1, 1)
