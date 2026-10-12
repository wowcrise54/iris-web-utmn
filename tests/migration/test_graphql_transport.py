"""GraphQL protocol remains identical when its Flask view is replaced."""
import importlib.util
import sys
import types
from pathlib import Path

from graphql import GraphQLField, GraphQLObjectType, GraphQLSchema, GraphQLString


ROOT = Path(__file__).resolve().parents[2] / "source" / "app"


def test_graphql_success_syntax_error_and_invalid_json_status():
    assert (ROOT / "graphql_view.py").exists(), "Native GraphQL view is missing"
    package_name = "_iris_graphql_contract"
    package = types.ModuleType(package_name)
    package.__path__ = [str(ROOT)]
    sys.modules[package_name] = package
    for module in ("web", "graphql_view"):
        spec = importlib.util.spec_from_file_location(f"{package_name}.{module}", ROOT / f"{module}.py")
        loaded = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = loaded
        spec.loader.exec_module(loaded)
    web = sys.modules[f"{package_name}.web"]
    view = sys.modules[f"{package_name}.graphql_view"].GraphQLView
    schema = GraphQLSchema(query=GraphQLObjectType("Query", {
        "hello": GraphQLField(GraphQLString, resolve=lambda source, info: "world")
    }))
    app = web.IRISApp(__name__)
    app.add_url_rule("/graphql", view_func=view.as_view("graphql", schema=schema), methods=["POST"])
    from starlette.testclient import TestClient
    with TestClient(app) as client:
        result = client.post("/graphql", json={"query": "{ hello }"})
        assert result.status_code == 200
        assert result.json() == {"data": {"hello": "world"}}
        invalid = client.post("/graphql", json={"query": "{"})
        assert invalid.status_code == 400
        assert invalid.json()["errors"][0]["message"].startswith("Syntax Error")
        invalid_json = client.post("/graphql", content="{", headers={"Content-Type": "application/json"})
        assert invalid_json.status_code == 400
        assert "errors" in invalid_json.json()
