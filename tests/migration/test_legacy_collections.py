"""Legacy document/image dependencies retain their Python 3.9 imports."""
import importlib.util
from pathlib import Path


def test_legacy_dependency_collection_imports():
    path = Path(__file__).parents[2] / "source/app/legacy_collections.py"
    spec = importlib.util.spec_from_file_location("legacy_collections", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from collections import Iterator, Sequence
    from collections.abc import Iterator as ABCIterator, Sequence as ABCSequence
    assert Iterator is ABCIterator
    assert Sequence is ABCSequence
