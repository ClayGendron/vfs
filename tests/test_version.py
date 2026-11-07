"""``vfs.__version__`` is the installed distribution's version, read from metadata, never a literal in the tree."""

from __future__ import annotations

import importlib.metadata
import re
from pathlib import Path

import vfs


def test_version_is_read_from_distribution_metadata() -> None:
    """A hand-kept copy that drifts from pyproject.toml fails here on the next sync."""
    assert vfs.__version__ == importlib.metadata.version("vfs-py")


def test_the_package_states_no_version_literal() -> None:
    """A restored `__version__ = "0.0.22"` literal passes the first test until the next bump; this one fails at once."""
    text = Path(vfs.__file__).read_text()
    assert re.search(r"^__version__\s*=\s*[\"']", text, re.M) is None
