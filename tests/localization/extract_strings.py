"""Extract translatable call sites and report Russian catalog coverage.

Run standalone for a report::

    python tests/localization/extract_strings.py --source source/app

It scans Jinja templates (``source/app/templates`` and every
``source/app/blueprints/*/templates``) and Python / native JavaScript modules for the explicit
translation calls the project uses —

    ``_("...")``  ``gettext("...")``  ``lazy_gettext("...")``
    ``pgettext("ctx", "...")``  ``ngettext("one", "many", n)``
    ``IRIS_I18N.t("...")``  ``IRIS_I18N.ngettext("one", "many", n)``

— and reports how many of the referenced msgids are present in the Russian
catalog.  It never guesses at untranslated prose: only explicit calls count, so
the coverage number is a *lower bound* on real UI coverage and cannot be gamed
by wrapping user data.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

# Longest function names first so ``gettext`` never matches the tail of
# ``pgettext`` / ``lazy_gettext``.
CALL_RE = re.compile(r"(?<![\w.])(?P<fn>IRIS_I18N\.ngettext|IRIS_I18N\.t|lazy_gettext|ngettext|pgettext|gettext|_)\s*\(")
LITERAL_RE = re.compile(r"""(?P<q>'|")(?P<body>(?:\\.|(?!\1).)*?)\1""")

# Functions whose first two literals are both translatable (context/plural).
_TWO_ARG = {"ngettext", "pgettext", "IRIS_I18N.ngettext"}

_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "'": "'", "\\": "\\"}


def _unescape(text: str) -> str:
    out: List[str] = []
    i = 0
    while i < len(text):
        char = text[i]
        if char == "\\" and i + 1 < len(text):
            out.append(_ESCAPES.get(text[i + 1], text[i + 1]))
            i += 2
        else:
            out.append(char)
            i += 1
    return "".join(out)


def extract_from_text(text: str, origin: str) -> List[Tuple[str, str, str]]:
    """Return ``(msgid, function, origin)`` for every explicit call site."""
    found: List[Tuple[str, str, str]] = []
    for match in CALL_RE.finditer(text):
        fn = match.group("fn")
        window = text[match.end(): match.end() + 800]
        literals = list(LITERAL_RE.finditer(window))
        if not literals:
            continue
        take = 2 if fn in _TWO_ARG else 1
        # Guard: the first literal must begin the argument list (allow spaces).
        prefix = window[: literals[0].start()]
        if prefix.strip() not in ("", "u"):
            continue
        for literal in literals[:take]:
            msgid = _unescape(literal.group("body"))
            # Skip punctuation-only placeholders such as the ``_("...")`` that
            # appears inside documentation examples — not a real message.
            if not any(char.isalnum() for char in msgid):
                continue
            found.append((msgid, fn, origin))
    return found


def iter_files(source_root: Path):
    templates = source_root / "templates"
    if templates.is_dir():
        yield from sorted(templates.rglob("*.html"))
    blueprints = source_root / "blueprints"
    if blueprints.is_dir():
        yield from sorted(blueprints.rglob("*.html"))
    for path in sorted(source_root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path
    yield from sorted((source_root / "static" / "assets" / "js" / "iris").rglob("*.js"))


def scan(source_root: Path) -> Dict[str, object]:
    per_file: Dict[str, List[str]] = {}
    per_function: Dict[str, int] = {}
    all_msgids: Set[str] = set()
    for path in iter_files(source_root):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = path.relative_to(source_root).as_posix()
        hits = extract_from_text(text, rel)
        if not hits:
            continue
        per_file[rel] = sorted({msgid for msgid, _fn, _o in hits})
        for msgid, fn, _o in hits:
            per_function[fn] = per_function.get(fn, 0) + 1
            all_msgids.add(msgid)
    return {
        "files": len(per_file),
        "per_file": per_file,
        "per_function": per_function,
        "msgids": sorted(all_msgids),
    }


def _load_i18n(source_root: Path):
    """Import ``i18n.py`` standalone (it only imports ``.web`` lazily)."""
    import importlib.util

    i18n_path = source_root / "i18n.py"
    spec = importlib.util.spec_from_file_location("_extract_i18n", i18n_path)
    module = importlib.util.module_from_spec(spec)
    # Bind as a top-level module so its lazy ``from .web import ...`` calls,
    # if ever triggered here, degrade gracefully instead of raising.
    sys.modules["_extract_i18n"] = module
    spec.loader.exec_module(module)
    return module


def coverage(source_root: Path, catalog_dir: Path) -> Dict[str, object]:
    report = scan(source_root)
    msgids: List[str] = report["msgids"]
    module = _load_i18n(source_root)

    translated: Set[str] = set()
    for locale in ("ru",):
        catalog = module.load_catalog(locale)
        translated |= set(catalog.messages())
        translated |= set(catalog.plurals())
        for entry in module.parse_po(Path(module.catalog_path(locale)).read_text(encoding="utf-8")):
            if not entry.fuzzy and entry.msgid_plural and len(entry.msgstr_plural) == 3 and all(entry.msgstr_plural.values()):
                translated.add(entry.msgid_plural)
    missing = [msgid for msgid in msgids if msgid not in translated]
    return {
        "referenced": len(msgids),
        "translated": len(msgids) - len(missing),
        "missing": missing,
        "report": report,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="source/app", type=Path)
    parser.add_argument("--json", action="store_true", help="emit machine readable output")
    args = parser.parse_args(argv)

    result = coverage(args.source.resolve(), args.source.resolve() / "locales")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(f"Explicit translation call sites: {result['report']['per_function']}")
    print(f"Distinct msgids referenced  : {result['referenced']}")
    print(f"Translated in ru catalog    : {result['translated']}")
    if result["missing"]:
        print(f"Missing translations ({len(result['missing'])}):")
        for msgid in result["missing"]:
            print(f"  - {msgid!r}")
    else:
        print("Missing translations        : none")
    return 0 if not result["missing"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
