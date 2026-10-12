"""Capture the pre-migration public route and immutable UI contracts without imports.

Run this against a preserved Flask checkout, never regenerate contracts from the
application being checked. The import-free extractor follows Blueprint imports,
registrations and nested prefixes, including the GraphQL factory.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path


def literal(node, fallback=None):
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return fallback


def extract(root):
    root = Path(root)
    source = root / "source"
    modules = {}
    for path in (source / "app").rglob("*.py"):
        parts = list(path.relative_to(source).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        modules[".".join(parts)] = (path, ast.parse(path.read_text(encoding="utf-8-sig")))
    aliases, blueprints, routes, registrations = {}, {}, [], []
    for module, (path, tree) in modules.items():
        local = aliases.setdefault(module, {})
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for name in node.names:
                    local[name.asname or name.name] = f"{node.module}.{name.name}"
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                call = node.value
                if isinstance(call.func, ast.Name) and call.func.id == "Blueprint":
                    name = literal(call.args[0])
                    kwargs = {kw.arg: literal(kw.value) for kw in call.keywords}
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            key = f"{module}.{target.id}"
                            blueprints[key] = {"name": name, "prefix": kwargs.get("url_prefix", "") or ""}
        # GraphQL is a factory returning the local blueprint.
        if module == "app.blueprints.graphql.graphql_route":
            local["graphql_blueprint"] = f"{module}.blueprint"

    def resolve(module, node):
        if isinstance(node, ast.Name):
            key = aliases[module].get(node.id, f"{module}.{node.id}")
            target_module, _, name = key.rpartition(".")
            return aliases.get(target_module, {}).get(name, key)
        return None

    def route(module, path, owner, call, default_endpoint, line):
        kwargs = {kw.arg: literal(kw.value) for kw in call.keywords}
        rule = literal(call.args[0]) if call.args else kwargs.get("rule")
        if rule is None:
            raise ValueError(f"Nonliteral rule at {path}:{line}")
        method = call.func.attr.upper()
        methods = kwargs.get("methods", [method] if method not in {"ROUTE", "ADD_URL_RULE"} else ["GET"])
        if "GET" in methods and "HEAD" not in methods:
            methods = [*methods, "HEAD"]
        if "OPTIONS" not in methods:
            methods = [*methods, "OPTIONS"]
        routes.append({"owner": owner, "rule": rule, "endpoint": kwargs.get("endpoint") or default_endpoint,
                       "methods": sorted(methods), "source": path.relative_to(root).as_posix(), "line": line})

    for module, (path, tree) in modules.items():
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                        if decorator.func.attr in {"route", "get", "post", "put", "patch", "delete", "options", "head"}:
                            route(module, path, resolve(module, decorator.func.value), decorator, node.name, decorator.lineno)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "register_blueprint" and node.args:
                    kwargs = {kw.arg: literal(kw.value) for kw in node.keywords}
                    registrations.append((resolve(module, node.func.value), resolve(module, node.args[0]), kwargs))
                if node.func.attr == "add_url_rule":
                    # GraphQLView.as_view('graphql') supplies the function name.
                    route(module, path, resolve(module, node.func.value), node, "graphql", node.lineno)

    children, roots = {}, []
    for owner, child, options in registrations:
        if owner in blueprints:
            children.setdefault(owner, []).append((child, options))
        elif owner in {"app.views.app", "app.app"}:
            roots.append((child, options))
    effective = []

    def walk(key, prefix="", endpoint_prefix="", options=None):
        options = options or {}
        if key not in blueprints:
            raise ValueError(f"Unresolved blueprint {key}")
        info = blueprints[key]
        prefix += options.get("url_prefix", info["prefix"])
        endpoint_prefix += options.get("name", info["name"]) + "."
        for item in routes:
            if item["owner"] == key:
                effective.append({"path": prefix + item["rule"], "endpoint": endpoint_prefix + item["endpoint"],
                                  "methods": item["methods"], "source": item["source"], "line": item["line"]})
        for child, child_options in children.get(key, []):
            walk(child, prefix, endpoint_prefix, child_options)

    for key, options in roots:
        walk(key, options=options)
    for item in routes:
        if item["owner"] == "app.app":
            effective.append({"path": item["rule"], "endpoint": item["endpoint"], "methods": item["methods"],
                              "source": item["source"], "line": item["line"]})
    effective.append({"path": "/static/<path:filename>", "endpoint": "static", "methods": ["GET", "HEAD", "OPTIONS"],
                      "source": "source/app/__init__.py", "line": None})
    hashes = {}
    for directory in (source / "app" / "templates", source / "app" / "static", source / "templates", source / "static", root / "ui",
                      *(source / "app" / "blueprints").rglob("templates")):
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*")):
            if path.is_file() and not any(p in {"node_modules", "dist", ".svelte-kit"} for p in path.parts):
                hashes[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"format": 1, "capture": "Flask baseline via Python AST; GET implies HEAD; implicit OPTIONS included",
            "routes": sorted(effective, key=lambda r: (r["path"], r["endpoint"])), "ui_sha256": hashes}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    contract = extract(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    print(f"Captured {len(contract['routes'])} routes and {len(contract['ui_sha256'])} UI/template files")
