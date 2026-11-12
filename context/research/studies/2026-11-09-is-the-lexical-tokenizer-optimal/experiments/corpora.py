"""Write the two corpora the tokenizer bench reads.

Corpus A: the 2,000 synthetic prose bodies of study 02's generator
(``corpus.py`` next to the dirty-row budgets study, imported by path),
one ``.txt`` file each under ``<scratch>/bodies_a/``.

Corpus B: a manifest of absolute paths to the repository's own text,
read from disk by the bench: every ``.py`` under ``src/vfs`` and
``tests/``, every ``.rs`` under ``crates/vfs-core/src`` except the
generated ``lexical_tables.rs``, and every ``.md`` under
``context/research`` and ``context/specifications/archive``.

Usage: uv run python corpora.py <scratch dir>
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
GENERATOR = REPO / "context/research/studies/2026-11-09-the-dirty-row-budgets-of-grep-and-glean/experiments/corpus.py"


def load_generator():
    spec = importlib.util.spec_from_file_location("corpus02", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_a(scratch: Path) -> None:
    corpus = load_generator()
    out = scratch / "bodies_a"
    out.mkdir(parents=True, exist_ok=True)
    total = 0
    for i, (_path, content) in enumerate(corpus.generate(2000)):
        data = content.encode("utf-8")
        total += len(data)
        (out / f"{i:06d}.txt").write_bytes(data)
    print(f"corpus A: 2000 bodies, {total} bytes, mean {total / 2000:.0f} bytes/body -> {out}")


def write_b(scratch: Path) -> None:
    files: list[Path] = []
    for root, suffix in (
        (REPO / "src/vfs", ".py"),
        (REPO / "tests", ".py"),
        (REPO / "crates/vfs-core/src", ".rs"),
        (REPO / "context/research", ".md"),
        (REPO / "context/specifications/archive", ".md"),
    ):
        for path in sorted(root.rglob(f"*{suffix}")):
            if path.name == "lexical_tables.rs":
                continue
            files.append(path)
    manifest = scratch / "manifest_b.txt"
    manifest.write_text("\n".join(str(p) for p in files) + "\n")
    total = sum(os.path.getsize(p) for p in files)
    print(f"corpus B: {len(files)} files, {total} bytes -> {manifest}")


if __name__ == "__main__":
    scratch = Path(sys.argv[1])
    write_a(scratch)
    write_b(scratch)
