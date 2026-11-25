"""E3: on a corpus-wide grep, how many candidates does the trigram ladder nominate, how many match, and what would
longer grams have nominated?

For each pattern, a corpus-wide ``grep`` runs with the engine's ``candidate_ids`` and the module's ``_choose_grams``
wrapped, recording the uncapped candidate count and the chosen grams' ``doc_count``. The candidates' bodies are then
read on a read-only connection and three filters are applied to them:

- ``match``: the pattern itself (Python ``re``), the files a grep returns;
- ``4gram``: every 4-gram of some branch's required literal occurs in the body, what a 4-gram index would nominate;
- ``literal``: some branch's required literal occurs in the body, the ceiling of any n-gram index.

Each pattern also reports the call's wall time, statements, and the time inside content fetch and verify.

    uv run python agents/2026-11-21-grep-query-planner/experiments/e3_corpus_precision.py linux.db out.json
"""

from __future__ import annotations

import asyncio
import functools
import json
import re
import sqlite3
import sys
import time
from typing import Any

from sqlalchemy import event

import vfs.storage.backends.database.grep as grep_module
from vfs import AsyncVirtualFileSystem, DatabaseStorage

# (pattern, the literal each alternation branch requires); the literals are read off the pattern by hand.
PATTERNS: list[tuple[str, list[str]]] = [
    ("i_count", ["i_count"]),
    ("f_ref|f_count", ["f_ref", "f_count"]),
    ("return 0;", ["return 0;"]),
    ("EXPORT_SYMBOL_GPL", ["EXPORT_SYMBOL_GPL"]),
    ("kmalloc", ["kmalloc"]),
    ("spin_lock_irqsave", ["spin_lock_irqsave"]),
    ("copy_from_user", ["copy_from_user"]),
    ("pr_debug", ["pr_debug"]),
    ("-EINVAL", ["-EINVAL"]),
    ("MODULE_LICENSE", ["MODULE_LICENSE"]),
    ("TODO", ["TODO"]),
    ("#include <linux/slab\\.h>", ["#include <linux/slab.h>"]),
    ("struct page \\*", ["struct page *"]),
    ("^static int __init", ["static int __init"]),
    ("\\.read_iter|\\.write_iter|\\.mmap", [".read_iter", ".write_iter", ".mmap"]),
    ("^struct dentry \\{", ["struct dentry {"]),
    ("^struct inode \\{", ["struct inode {"]),
    ("dentry_lru_isolate", ["dentry_lru_isolate"]),
    ("__follow_mount_rcu", ["__follow_mount_rcu"]),
    ("ramfs_get_inode|ramfs_fs_type", ["ramfs_get_inode", "ramfs_fs_type"]),
    ("alloc_page", ["alloc_page"]),
    ("xyzzy_no_such_symbol_42", ["xyzzy_no_such_symbol_42"]),
    ("int ret", ["int ret"]),
    ("unsigned long flags", ["unsigned long flags"]),
]

recorded: dict[str, Any] = {}


class RecordingExtension:
    def __init__(self, real: Any) -> None:
        self._real = real

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)

    def candidate_ids(self, fed: Any, allow: Any, cap: int) -> Any:
        ids, count = self._real.candidate_ids(fed, allow, cap)
        recorded["candidate_ids"] = list(ids)
        recorded["candidate_count"] = count
        return ids, count


real_extension = grep_module.extension
grep_module.extension = lambda: RecordingExtension(real_extension())
real_choose = grep_module._choose_grams


@functools.wraps(real_choose)
def choose(groups: Any, meta: Any) -> Any:
    chosen = real_choose(groups, meta)
    recorded["groups"] = [
        None if group is None else [meta[gram].doc_count for gram in group] for group in chosen
    ]
    return chosen


grep_module._choose_grams = choose
phase_ms: dict[str, float] = {}


def wrap_phase(name: str) -> None:
    original = getattr(grep_module, name)

    @functools.wraps(original)
    async def timed(*args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        try:
            return await original(*args, **kwargs)
        finally:
            phase_ms[name] = phase_ms.get(name, 0.0) + (time.perf_counter() - started) * 1000

    setattr(grep_module, name, timed)


for phase in ("content_for_entries", "_entries_for_docs", "entries_for_scan"):
    wrap_phase(phase)


def quadgrams(literal: str) -> set[str]:
    return {literal[i : i + 4] for i in range(len(literal) - 3)} or {literal}


def trigrams(literal: str) -> set[str]:
    folded = literal.lower()
    return {folded[i : i + 3] for i in range(len(folded) - 2)} or {folded}


def server_prefilter(raw: sqlite3.Connection, ids: list[int], literals: list[str]) -> tuple[float, float, int]:
    """Time fetching the candidates' bodies against having the engine keep only bodies holding a literal."""
    if not ids:
        return 0.0, 0.0, 0
    fetch_ms = prefilter_ms = 0.0
    survivors = 0
    any_literal = " OR ".join("instr(c.content, ?) > 0" for _ in literals)
    for start in range(0, len(ids), 30000):
        chunk = ids[start : start + 30000]
        marks = ",".join("?" * len(chunk))
        base = "FROM vfs_content c JOIN vfs_entries e ON e.entry_id = c.entry_id WHERE e.id IN (" + marks + ")"
        started = time.perf_counter()
        raw.execute("SELECT c.entry_id, c.content " + base, chunk).fetchall()
        fetch_ms += (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        survivors += len(raw.execute(f"SELECT c.entry_id {base} AND ({any_literal})", [*chunk, *literals]).fetchall())
        prefilter_ms += (time.perf_counter() - started) * 1000
    return fetch_ms, prefilter_ms, survivors


async def main() -> None:
    db, out = sys.argv[1], sys.argv[2]
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{db}")
    kernel = AsyncVirtualFileSystem(storage=storage)
    statements = [0]
    event.listen(storage.engine.sync_engine, "before_cursor_execute", lambda *_: statements.__setitem__(0, statements[0] + 1))
    raw = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows: list[dict[str, Any]] = []
    try:
        await kernel.stat("/fs")
        for pattern, literals in PATTERNS:
            for _ in range(2):
                recorded.clear()
                phase_ms.clear()
                before = statements[0]
                started = time.perf_counter()
                result = await kernel.grep(pattern)
                wall = (time.perf_counter() - started) * 1000
            ids = recorded.get("candidate_ids", [])
            bodies: list[str] = []
            for start in range(0, len(ids), 30000):
                chunk = ids[start : start + 30000]
                marks = ",".join("?" * len(chunk))
                bodies.extend(
                    body for (body,) in raw.execute(
                        "SELECT c.content FROM vfs_content c JOIN vfs_entries e ON e.entry_id = c.entry_id "
                        f"WHERE e.id IN ({marks})", chunk
                    )
                )  # fmt: skip
            matcher = re.compile(pattern, re.MULTILINE)
            grams = [quadgrams(literal) for literal in literals]
            tri = [trigrams(literal) for literal in literals]
            match = sum(1 for body in bodies if matcher.search(body))
            three = sum(1 for folded in map(str.lower, bodies) if any(all(g in folded for g in b) for b in tri))
            four = sum(1 for body in bodies if any(all(g in body for g in branch) for branch in grams))
            literal = sum(1 for body in bodies if any(lit in body for lit in literals))
            fetch_ms, prefilter_ms, survivors = server_prefilter(raw, ids, literals)
            row = {
                "pattern": pattern,
                "groups_doc_counts": recorded.get("groups"),
                "candidates": recorded.get("candidate_count"),
                "candidates_fetched": len(bodies),
                "candidate_bytes": sum(len(body) for body in bodies),
                "match_files_among_fetched": match,
                "all_3gram_files_among_fetched": three,
                "4gram_files_among_fetched": four,
                "raw_fetch_ms": fetch_ms,
                "server_instr_prefilter_ms": prefilter_ms,
                "server_instr_survivors": survivors,
                "literal_files_among_fetched": literal,
                "files_returned": len(result.observations),
                "warnings": [error.message[:80] for error in result.errors],
                "wall_ms": wall,
                "statements": statements[0] - before,
                "phase_ms": dict(phase_ms),
            }
            rows.append(row)
            print(json.dumps(row), flush=True)
    finally:
        raw.close()
        await kernel.close()
    with open(out, "w") as handle:
        json.dump(rows, handle, indent=2)


asyncio.run(main())
