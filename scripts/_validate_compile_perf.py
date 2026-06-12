"""Throwaway perf/round-trip probe for compile_postings.

Captures the exact SQL issued by one compile (to count round trips and check
for Python-built IN-lists over key sets) and micro-benchmarks compile time as a
function of touched grams vs corpus size.

Run: uv run python scripts/_validate_compile_perf.py
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from sqlalchemy import event

from tests.conftest import make_sqlite_db

USER = "u1"


def attach_capture(fs):
    stmts: list[str] = []

    def _on_exec(_conn, _cursor, statement, _params, _ctx, _many):
        stmts.append(statement)

    event.listen(fs._engine.sync_engine, "before_cursor_execute", _on_exec)
    return stmts


async def main() -> None:
    # ---- Round-trip / SQL-shape capture ---------------------------------
    fs = await make_sqlite_db(auto_chunk=True, auto_index=True, user_scoped=True)
    await fs.setup()
    for i in range(5):
        await fs.write(path=f"/{USER}/f{i}.py", content=f"def f{i}():\n    return {i} + foo\n", user_id=USER)

    stmts = attach_capture(fs)
    async with fs._session_factory() as session:
        await fs.compile_postings(session)
        await session.commit()

    print("==== SQL issued during one compile_postings ====")
    for i, s in enumerate(stmts):
        oneline = " ".join(s.split())
        print(f"{i}: {oneline[:200]}")

    selects = [s for s in stmts if s.lstrip().upper().startswith("SELECT")]
    deletes = [s for s in stmts if s.lstrip().upper().startswith("DELETE")]
    inserts = [s for s in stmts if s.lstrip().upper().startswith("INSERT")]
    updates = [s for s in stmts if s.lstrip().upper().startswith("UPDATE")]
    print(
        f"\nCounts: SELECT={len(selects)} INSERT={len(inserts)} "
        f"UPDATE={len(updates)} DELETE={len(deletes)} total={len(stmts)}"
    )

    # ---- Micro-benchmark: compile time vs touched grams vs corpus -------
    # Build a large pre-existing posting index (big corpus), then time a
    # compile that touches only a few grams (one tiny new file). If compile is
    # O(touched grams) not O(corpus), the second compile is fast and roughly
    # constant regardless of corpus size.
    async def build(n_files: int):
        f = await make_sqlite_db(auto_chunk=True, auto_index=True, user_scoped=True)
        await f.setup()
        for i in range(n_files):
            body = "\n".join(f"line_{i}_{j} = compute({j})" for j in range(8))
            await f.write(path=f"/{USER}/big{i}.py", content=body + "\n", user_id=USER)
        async with f._session_factory() as s:
            await f.compile_postings(s)
            await s.commit()
        return f

    timings = {}
    for n in (50, 400):
        f = await build(n)
        # one tiny new file -> few touched grams
        await f.write(path=f"/{USER}/tiny.py", content="zq = 1\n", user_id=USER)
        async with f._session_factory() as s:
            t0 = time.perf_counter()
            folded = await f.compile_postings(s)
            await s.commit()
            dt = time.perf_counter() - t0
        # count posting rows = corpus gram cardinality
        from sqlalchemy import func, select as sel

        async with f._session_factory() as s:
            rows = (await s.execute(sel(func.count()).select_from(f._posting_table))).scalar()
        timings[n] = (dt, folded, rows)
        print(f"corpus={n} files: posting_rows={rows}, tiny-file compile folded={folded} in {dt*1000:.2f} ms")

    t50 = timings[50][0]
    t400 = timings[400][0]
    print(
        f"\nScaling: 8x corpus -> compile time ratio {t400 / t50:.2f}x "
        f"(near-constant => O(touched grams), not O(corpus))"
    )


if __name__ == "__main__":
    asyncio.run(main())
