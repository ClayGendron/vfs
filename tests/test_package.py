"""The package face: what ``vfs`` exports, what importing it loads, and what the docs import."""

from __future__ import annotations

import inspect
import re
import subprocess
import sys
from pathlib import Path

import vfs
import vfs.models
import vfs.storage.backends
from vfs import (
    AsyncSession,
    AsyncVirtualFileSystem,
    DatabaseStorage,
    Entry,
    InMemoryStorage,
    Session,
    VirtualFileSystem,
)

ROOT = Path(__file__).resolve().parents[1]
# A fence that reaches past the package face for a name the face carries.
SUBMODULE_IMPORT = re.compile(r"from vfs\.(?:storage|models)\S* import .*\b(?:DatabaseStorage|InMemoryStorage|Entry)\b")
WRITE_FACES = (AsyncVirtualFileSystem, VirtualFileSystem, AsyncSession, Session)


def test_the_etl_names_are_exported_from_the_package() -> None:
    assert Entry is vfs.models.Entry
    assert DatabaseStorage is vfs.storage.backends.DatabaseStorage
    assert InMemoryStorage is vfs.storage.backends.InMemoryStorage
    assert {"Entry", "DatabaseStorage", "InMemoryStorage"} <= set(vfs.__all__)
    assert vfs.__all__ == sorted(vfs.__all__)


def test_importing_vfs_loads_no_numpy() -> None:
    """The package's own walk loads no numpy; where numpy is present, the optional Postgres extra is the importer."""
    blocked = "import sys; sys.modules['pgvector'] = None; import vfs; print('numpy' in sys.modules)"
    assert _fresh_interpreter_prints(blocked) == "False"
    installed = "import sys, vfs; print(('numpy' in sys.modules) == ('pgvector.bit' in sys.modules))"
    assert _fresh_interpreter_prints(installed) == "True"


def _fresh_interpreter_prints(probe: str) -> str:
    run = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, check=True)
    return run.stdout.strip()


def test_write_takes_any_iterable_of_entries() -> None:
    for face in WRITE_FACES:
        assert inspect.signature(face.write).parameters["entries"].annotation == "Iterable[Entry] | None", face


def test_the_docs_import_the_etl_names_from_the_package() -> None:
    pages = [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
    offending = [
        f"{page.relative_to(ROOT)}:{number}: {line}"
        for page in pages
        for number, line in enumerate(page.read_text().splitlines(), 1)
        if SUBMODULE_IMPORT.search(line)
    ]
    assert offending == []
    how_to = (ROOT / "docs/how-to/bulk-load-as-the-system-actor.md").read_text()
    assert "await etl.write((Entry(" in how_to and "for i in range(3)), parents=True)" in how_to
