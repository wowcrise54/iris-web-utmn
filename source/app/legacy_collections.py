"""Python 3.12 compatibility for the release's image and docx libraries.

SQLAlchemy-ImageAttach 1.1.0 and python-docx 0.8.10 import these aliases
from collections, as supported by the original Python 3.9 runtime.
"""
import collections
import collections.abc

for _name in ("Iterator", "Sequence"):
    if not hasattr(collections, _name):
        setattr(collections, _name, getattr(collections.abc, _name))
