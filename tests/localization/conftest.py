"""Load the native IRIS modules under their real ``app.*`` import names.

The suite must exercise ``app/i18n.py``, the switch blueprint and
``app/web.py`` together without importing the real ``app/__init__.py`` (which
boots the database, Celery and Socket.IO).  We therefore register a bare
``app`` package whose ``__path__`` points at ``source/app`` and load only the
modules under test — the same isolation trick used by
``tests/migration/test_auth_forms.py``.
"""
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "source" / "app"

_MODULES = (
    ("app.web", "web.py"),
    ("app.auth_login", "auth_login.py"),
    ("app.web_forms", "web_forms.py"),
    ("app.i18n", "i18n.py"),
    ("app.blueprints.i18n.i18n_routes", "blueprints/i18n/i18n_routes.py"),
)


def _ensure_package(dotted, filesystem_path):
    if dotted in sys.modules:
        return sys.modules[dotted]
    parent_name, _, child = dotted.rpartition(".")
    if parent_name:
        _ensure_package(parent_name, filesystem_path.parent)
    module = types.ModuleType(dotted)
    module.__path__ = [str(filesystem_path)]
    sys.modules[dotted] = module
    if parent_name:
        setattr(sys.modules[parent_name], child, module)
    return module


def _load(dotted, relative_path):
    spec = importlib.util.spec_from_file_location(dotted, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[dotted] = module
    parent_name, _, child = dotted.rpartition(".")
    if parent_name and parent_name in sys.modules:
        setattr(sys.modules[parent_name], child, module)
    spec.loader.exec_module(module)
    return module


def load_modules():
    if "app.i18n" in sys.modules:
        return
    _ensure_package("app", ROOT)
    _ensure_package("app.blueprints", ROOT / "blueprints")
    _ensure_package("app.blueprints.i18n", ROOT / "blueprints" / "i18n")
    for dotted, relative in _MODULES:
        _load(dotted, relative)


load_modules()