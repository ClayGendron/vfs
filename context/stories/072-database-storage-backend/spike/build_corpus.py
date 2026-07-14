"""Build the spike corpus: one SQLite DB of code docs from local OSS repos.

Walks the configured repos round-robin (one file per repo per turn, so any
id-prefix tier is a representative language mix), filters to UTF-8 text
files, normalizes newlines, splits large files into ~4K line-aligned chunks,
and writes docs(id, path, content). Tier N = the first N doc ids.

Run: uv run python context/stories/072-database-storage-backend/spike/build_corpus.py
"""

from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from spikelib import (  # noqa: E402
    CHUNK_TARGET_BYTES,
    CORPUS_REPOS,
    DATA_DIR,
    MAX_FILE_BYTES,
    MAX_LINE_BYTES,
    REPO_ROOT,
    TEXT_EXTENSIONS,
)

SKIP_DIRS = {".git", "node_modules", "vendor", "third_party", "testdata", "__pycache__"}


def iter_repo_files(repo: str) -> list[Path]:
    root = REPO_ROOT / repo
    files: list[Path] = []
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            entries = sorted(d.iterdir())
        except OSError:
            continue
        for p in entries:
            name = p.name
            if p.is_dir() and not p.is_symlink():
                if name not in SKIP_DIRS and not name.startswith("."):
                    stack.append(p)
            elif p.is_file() and not p.is_symlink() and p.suffix.lower() in TEXT_EXTENSIONS:
                files.append(p)
    return files


def read_chunks(path: Path) -> list[str]:
    try:
        raw = path.read_bytes()
    except OSError:
        return []
    if not raw or len(raw) > MAX_FILE_BYTES or b"\x00" in raw[:4096]:
        return []
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return []
    if "\r" in text:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.splitlines(keepends=True)
    if any(len(ln.encode("utf-8", "ignore")) > MAX_LINE_BYTES for ln in lines):
        return []  # probable minified/generated content (codesearch maxLineLen)
    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    for ln in lines:
        buf.append(ln)
        size += len(ln)
        if size >= CHUNK_TARGET_BYTES:
            chunks.append("".join(buf))
            buf, size = [], 0
    if buf:
        chunks.append("".join(buf))
    return [c for c in chunks if len(c) >= 3]


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db_path = DATA_DIR / "corpus.db"
    db_path.unlink(missing_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        PRAGMA journal_mode = OFF;
        PRAGMA synchronous = OFF;
        CREATE TABLE docs (id INTEGER PRIMARY KEY, path TEXT NOT NULL, content TEXT NOT NULL);
        """
    )
    t0 = time.monotonic()
    per_repo = {r: iter_repo_files(r) for r in CORPUS_REPOS}
    for repo, files in sorted(per_repo.items()):
        print(f"{repo}: {len(files)} candidate files", flush=True)

    doc_id = 0
    batch: list[tuple[int, str, str]] = []
    indices = dict.fromkeys(CORPUS_REPOS, 0)
    active = [r for r in CORPUS_REPOS if per_repo[r]]
    while active:
        next_active = []
        for repo in active:
            i = indices[repo]
            files = per_repo[repo]
            if i >= len(files):
                continue
            indices[repo] = i + 1
            f = files[i]
            rel = f"{repo}/{f.relative_to(REPO_ROOT / repo)}"
            for ci, chunk in enumerate(read_chunks(f)):
                batch.append((doc_id, f"{rel}#{ci}", chunk))
                doc_id += 1
            if indices[repo] < len(files):
                next_active.append(repo)
            if len(batch) >= 20_000:
                conn.executemany("INSERT INTO docs VALUES (?,?,?)", batch)
                conn.commit()
                batch.clear()
        active = next_active
        if doc_id and doc_id % 200_000 < 20_000:
            print(f"  ... {doc_id} docs, {time.monotonic() - t0:.0f}s", flush=True)

    if batch:
        conn.executemany("INSERT INTO docs VALUES (?,?,?)", batch)
        conn.commit()
    total_bytes = conn.execute("SELECT sum(length(content)) FROM docs").fetchone()[0]
    conn.close()
    print(
        f"DONE: {doc_id} docs, {total_bytes / 1e9:.2f} GB text, "
        f"{time.monotonic() - t0:.0f}s -> {db_path}",
        flush=True,
    )


if __name__ == "__main__":
    main()
