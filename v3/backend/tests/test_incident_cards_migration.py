"""Migration tolerates the application's create_all-before-Alembic startup."""

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


class Integer:
    pass


class BigInteger(Integer):
    pass


class Text:
    pass


class JSONB:
    pass


class DateTime:
    def __init__(self, timezone=False):
        self.timezone = timezone


class MigrationTests(unittest.TestCase):
    def load(self, exists):
        self.inspector = Mock()
        self.inspector.has_table.return_value = exists
        self.operation = types.SimpleNamespace(
            get_bind=Mock(), create_table=Mock(), drop_table=Mock()
        )
        sa = types.ModuleType("sqlalchemy")
        for cls in [Integer, BigInteger, Text, DateTime]:
            setattr(sa, cls.__name__, cls)
        sa.inspect = Mock(return_value=self.inspector)
        sa.Column = Mock()
        sa.ForeignKey = Mock()
        modules = {
            "alembic": types.SimpleNamespace(op=self.operation),
            "sqlalchemy": sa,
            "sqlalchemy.dialects.postgresql": types.SimpleNamespace(JSONB=JSONB),
        }
        with patch.dict(sys.modules, modules):
            path = (
                Path(__file__).resolve().parents[1]
                / "source/app/alembic/versions/utmn_incident_card01_add_incident_cards.py"
            )
            spec = importlib.util.spec_from_file_location("card_migration_test", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        self.columns = [
            dict(name=n, type=t, nullable=null)
            for n, t, null in [
                ("case_id", BigInteger(), False),
                ("schema_version", Integer(), False),
                ("revision", Integer(), False),
                ("fields", JSONB(), False),
                ("selections", JSONB(), False),
                ("author_id", BigInteger(), True),
                ("author_name", Text(), True),
                ("created_at", DateTime(True), False),
                ("updated_at", DateTime(True), False),
                ("missing_sources", JSONB(), False),
            ]
        ]
        self.inspector.get_columns.return_value = self.columns
        self.inspector.get_pk_constraint.return_value = {
            "constrained_columns": ["case_id"]
        }
        self.inspector.get_foreign_keys.return_value = [
            dict(
                constrained_columns=["case_id"],
                referred_table="cases",
                referred_columns=["case_id"],
                options={"ondelete": "CASCADE"},
            ),
            dict(
                constrained_columns=["author_id"],
                referred_table="user",
                referred_columns=["id"],
                options={"ondelete": "SET NULL"},
            ),
        ]
        return mod

    def test_fresh_table_created(self):
        self.load(False).upgrade()
        self.operation.create_table.assert_called_once()

    def test_existing_compatible_table_skipped(self):
        self.load(True).upgrade()
        self.operation.create_table.assert_not_called()

    def test_existing_missing_column_rejected(self):
        mod = self.load(True)
        self.inspector.get_columns.return_value = self.columns[:-1]
        with self.assertRaises(RuntimeError):
            mod.upgrade()
        self.operation.create_table.assert_not_called()

    def test_existing_incompatible_type_timezone_key_or_fk_rejected(self):
        for kind in ["type", "timezone", "pk", "fk", "nullable"]:
            mod = self.load(True)
            if kind == "type":
                self.columns[3]["type"] = Text()
            if kind == "timezone":
                self.columns[7]["type"] = DateTime(False)
            if kind == "pk":
                self.inspector.get_pk_constraint.return_value = {
                    "constrained_columns": ["author_id"]
                }
            if kind == "fk":
                self.inspector.get_foreign_keys.return_value = []
            if kind == "nullable":
                self.columns[1]["nullable"] = True
            with self.subTest(kind=kind), self.assertRaises(RuntimeError):
                mod.upgrade()
            self.operation.create_table.assert_not_called()


if __name__ == "__main__":
    unittest.main()
