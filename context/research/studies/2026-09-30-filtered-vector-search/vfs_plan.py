"""What vfs's own vector-leg statement costs under a partial view, and how SQLite plans it.

Builds the partial-glean bench's 50,000-file mount through ``DatabaseStorage``,
runs ``glean`` as callers with 1, 10, 100 and 500 folder grants, captures the
vector-leg statement (the one calling ``vec_distance_cosine``), and prints its
query plan and its own time, re-run alone on a raw connection.

    uv run --no-sync python vfs_plan.py [--analyze]

``--analyze`` runs ``ANALYZE`` on the raw connection first, to see whether
planner statistics alone move SQLite off the ``kind`` index.

Study code only: nothing here is imported by vfs.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import statistics
import sys
import tempfile
import time
from typing import Any
from uuid import uuid4

import sqlite_vec
from sqlalchemy import event

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "2026-09-29-partial-glean-latency"))

from bench import SYSTEM, corpus  # noqa: E402

from vfs.authority import Authority, Principal  # noqa: E402
from vfs.embedding import HashEmbeddingProvider  # noqa: E402
from vfs.paths import Path  # noqa: E402
from vfs.storage.backends.database import DatabaseStorage  # noqa: E402

GRANTS = {"1 grant": 1, "10 grants": 10, "100 grants": 100, "500 grants": 500}


def admitted_first(
    raw: sqlite3.Connection, storage: DatabaseStorage, statement: str, params: Any, prefixes: list[str], who: str
) -> list[str]:
    """The same leg with the admitted entries found first through the path index, then the distance."""
    entry = storage._host.tables.entry.name
    chunks = storage._host.tables.chunks.name
    query = params[0]
    arms = " OR ".join("(path = ? OR path LIKE ? ESCAPE '\\')" for _ in prefixes)
    args = [x for p in prefixes for x in (p, p + "/%")]
    tail = (
        f" SELECT c.id, vec_distance_cosine(c.embedding, ?) AS distance, e.* FROM v"
        f" CROSS JOIN {entry} e CROSS JOIN {chunks} c"
        f" WHERE e.entry_id = v.entry_id AND c.entry_id = v.entry_id AND c.embedding IS NOT NULL AND e.chunked = 1 AND e.deleted_at IS NULL"
        f" AND e.kind IN ('chunk', 'file', 'version') ORDER BY distance, c.id LIMIT 10"
    )
    shapes = {
        "path arms only": (f"WITH v AS MATERIALIZED (SELECT entry_id FROM {entry} WHERE {arms})" + tail, [*args, query]),
        "path arms UNION owner arm": (
            f"WITH v AS MATERIALIZED (SELECT entry_id FROM {entry} WHERE {arms}"
            f" UNION SELECT entry_id FROM {entry} WHERE owner_id = ?)" + tail,
            [*args, who, query],
        ),
    }
    out = []
    for label, (sql, bound) in shapes.items():
        samples = []
        for _ in range(5):
            t0 = time.perf_counter()
            raw.execute(sql, bound).fetchall()
            samples.append((time.perf_counter() - t0) * 1000)
        plan = [row[3] for row in raw.execute("EXPLAIN QUERY PLAN " + sql, bound)]
        out.append(f"    admitted-first, {label}: {statistics.median(samples):.0f} ms — plan: {'; '.join(plan[:4])}")
    return [*out, ""]


async def main() -> None:
    tmp = tempfile.mkdtemp(prefix="vfs-fvs-plan-")
    db = f"{tmp}/vfs.sqlite"
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{db}", table_name=f"vfs_{uuid4().hex[:8]}",
                              embedder=HashEmbeddingProvider())
    entries = corpus(10, 100, 50)
    for start in range(0, len(entries), 5_000):
        assert (await storage.write(entries=entries[start : start + 5_000], parents=True, authority=SYSTEM)).success
    assert (await storage.reindex()).success
    assert (await storage.posture(path=Path("/"), posture="private", authority=SYSTEM)).success
    folders = [f"/t{t:02d}/f{f:03d}" for t in range(10) for f in range(100)]
    captured: list[tuple[str, Any]] = []

    def grab(_c: Any, _cur: Any, statement: str, parameters: Any, _ctx: Any, _many: bool) -> None:
        if "vec_distance_cosine" in statement:
            captured.append((statement, parameters))

    event.listen(storage._host.engine.sync_engine, "before_cursor_execute", grab)
    raw = sqlite3.connect(db)
    raw.enable_load_extension(True)
    sqlite_vec.load(raw)
    raw.execute("PRAGMA case_sensitive_like = ON")
    if "--analyze" in sys.argv:
        raw.execute("ANALYZE")
    lines = ["## vfs's own vector-leg statement on SQLite, 50,000 files, dim 64, 5 runs each\n"]
    for n, (label, count) in enumerate(GRANTS.items()):
        principal = f"p{n}"
        step = len(folders) // count
        for prefix in folders[::step][:count]:
            assert (await storage.grant(path=Path(prefix), principal=principal, level="read", authority=SYSTEM)).success
        captured.clear()
        result = await storage.glean(query="zmid", limit=10, authority=Authority.of(Principal(principal)))
        assert result.success
        for statement, params in captured[:1]:
            plan = [row[3] for row in raw.execute("EXPLAIN QUERY PLAN " + statement, params)]
            samples = []
            for _ in range(5):
                t0 = time.perf_counter()
                raw.execute(statement, params).fetchall()
                samples.append((time.perf_counter() - t0) * 1000)
            lines.append(f"### {label} ({len(captured)} vector statement(s)); first: {statistics.median(samples):.0f} ms")
            lines += [f"    {step_}" for step_ in plan] + [""]
            lines += admitted_first(raw, storage, statement, params, folders[::step][:count], principal)
        print("\n".join(lines[-len(plan) - 2 :]), flush=True)
    await storage.close()
    name = "vfs-vector-leg-plan-analyzed.md" if "--analyze" in sys.argv else "vfs-vector-leg-plan.md"
    with open(os.path.join(HERE, "runs", name), "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
