"""The framework migration leaves existing handler and domain code intact."""
import ast
import hashlib
import json
from pathlib import Path


class FrameworkNames(ast.NodeTransformer):
    def visit_Import(self, node):
        return None

    def visit_ImportFrom(self, node):
        return None

    def visit_Name(self, node):
        # The form base has a new provider; all declared fields and logic stay.
        if node.id == "WebForm":
            node.id = "FlaskForm"
        return node


def fingerprint(source, migration_environment=False):
    syntax = FrameworkNames().visit(ast.parse(source))
    if migration_environment:
        # The only additional adaptation is SQLAlchemy 2 transaction ownership.
        # Its persisted-revision behavior has a separate regression test.
        for node in ast.walk(syntax):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "connectable" and node.func.attr == "begin"):
                node.func.attr = "connect"
    return hashlib.sha256(ast.dump(syntax, include_attributes=False).encode()).hexdigest()


def test_existing_business_and_handler_implementation_is_preserved():
    root = Path(__file__).parents[2]
    expected = json.loads((Path(__file__).parent / "business_contracts.json").read_text(encoding="utf-8"))
    assert expected, "The original implementation contract must contain source files"
    for relative, digest in expected.items():
        path = root / relative
        assert path.is_file(), f"Existing source removed: {relative}"
        assert fingerprint(path.read_text(encoding="utf-8"),
                           migration_environment=relative == "source/app/alembic/env.py") == digest, \
            f"Existing logic changed: {relative}"
