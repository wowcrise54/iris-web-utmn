"""Inspect the actual initialized application inside the isolated Docker stack."""
import argparse
import json
from pathlib import Path
import re
import sys


def canonical(path):
    path = re.sub(r"<(?:(?:[^:<>]+):)?([^<>]+)>", r"{\1}", path)
    return re.sub(r"\{([^}:]+):[^}]+\}", r"{\1}", path)


def inspect_contract(native=True):
    sys.path.insert(0, str(Path.cwd()))
    import app
    application = app.app
    if native:
        assert any(base.__name__ == "FastAPI" for base in type(application).__mro__), \
            f"Expected native FastAPI, got {type(application)}"
        from fastapi import FastAPI
        assert isinstance(application, FastAPI), f"Expected native FastAPI, got {type(application)}"
        assert "flask" not in sys.modules, "Flask was imported by the native runtime"
        assert not hasattr(application, "wsgi_app"), "WSGI runtime is still present"
        actual = [(canonical(r.path), r.name, sorted(r.methods or [])) for r in application.routes
                  if hasattr(r, "methods") and r.methods]
        for route in application.routes:
            mounted = getattr(route, "app", None)
            assert not (mounted and "wsgi" in type(mounted).__name__.lower()), "WSGI mount present"
        import run
        exported = run.app
        assert exported is application or getattr(exported, "other_asgi_app", None) is application, \
            "run:app does not export the native app or the Socket.IO ASGI dispatcher"
    else:
        actual = [(canonical(r.rule), r.endpoint, sorted(r.methods)) for r in application.url_map.iter_rules()]
    contract = json.loads((Path(__file__).parent / "contracts.json").read_text(encoding="utf-8"))
    expected = [(canonical(r["path"]), r["endpoint"], r["methods"]) for r in contract["routes"]]
    # These OIDC-only handlers are registered only with AUTHENTICATION_TYPE=oidc.
    if application.config.get("AUTHENTICATION_TYPE") != "oidc":
        expected = [r for r in expected if not r[1].startswith("login.oidc_")]
    if application.config.get("DEMO_MODE_ENABLED") != "True":
        expected = [r for r in expected if r[1] != "demo-landing.demo_landing"]
    missing = sorted(set((p, n, tuple(m)) for p, n, m in expected) - set((p, n, tuple(m)) for p, n, m in actual))
    assert not missing, f"Missing/changed route contracts ({len(missing)}): {missing[:20]}"
    unexpected = sorted(set((p, n, tuple(m)) for p, n, m in actual) - set((p, n, tuple(m)) for p, n, m in expected))
    assert not unexpected, f"Unexpected public routes ({len(unexpected)}): {unexpected[:20]}"
    return {"runtime": type(application).__name__, "routes": sorted(actual), "expected_count": len(expected)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--flask", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = inspect_contract(native=not args.flask)
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"{result['runtime']}: {len(result['routes'])} routes; {result['expected_count']} baseline contracts preserved")
