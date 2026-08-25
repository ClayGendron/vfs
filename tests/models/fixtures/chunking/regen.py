"""Regenerate expected.json — the committed chunk shapes of the fixtures.

Run after a deliberate grammar or engine change (a grammar-crate bump, a
walker change), on the native engine, and commit the diff with it::

    uv run python tests/models/fixtures/chunking/regen.py

The expectations are the full assembled chunks at a 256-byte budget —
small enough to force real structure boundaries in every fixture.
"""

from __future__ import annotations

import json
from pathlib import Path

from vfs.models.chunking import split_code
from vfs.native import active_core

HERE = Path(__file__).parent
CHUNK_SIZE = 256
FIXTURES = {"sample.py": "python", "sample.c": "c", "sample.md": "markdown"}


def expectations() -> dict[str, list[list[object]]]:
    out: dict[str, list[list[object]]] = {}
    for name, grammar in FIXTURES.items():
        chunks = split_code((HERE / name).read_text(), language=grammar, chunk_size=CHUNK_SIZE)
        out[name] = [[text, ls, le] for text, ls, le in chunks]
    return out


if __name__ == "__main__":
    if active_core() != "rust":
        raise SystemExit("fixtures pin the native engine; run with the extension installed")
    (HERE / "expected.json").write_text(json.dumps(expectations(), indent=1) + "\n")
    print(f"wrote {HERE / 'expected.json'}")  # noqa: T201 - operator-facing script output
