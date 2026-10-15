"""R6 probe: why does `adj.frm IN (<10k binds>)` stall on SQLite when the CTE anchor's IN list does not?

Run: cd /Users/claygendron/Git/Repos/vfs && uv run python -u <scratch>/experiments/r6_probe_in_list.py
"""

from __future__ import annotations

import time

from sqlalchemy import select, text

from r6_common import AUTHORED, DB_10K, adjacency, literal_sql, live_entries, open_storage, rows, run
from vfs.storage.backends.database.descent import liveness_filters
from vfs.storage.backends.database.ranges import _RangeJoin


async def main() -> None:
    storage = await open_storage(DB_10K)
    tables, profile, dialect = storage._host.tables, storage._host.profile, storage._host.engine.dialect
    entry, edges = tables.entry, tables.edges
    entries = await live_entries(storage)
    seeds = sorted(i for i, m in entries.items() if m["path"].startswith("/bulk/") and m["kind"] == "file")
    far = entry.alias("far")

    def frontier_stmt(chunk, *, distinct: bool, flat: bool):
        if flat:
            stmt = (
                select(edges.c.target_id)
                .select_from(edges.join(far, far.c.entry_id == edges.c.target_id))
                .where(edges.c.source_id.in_(chunk), edges.c.edge_type.in_(list(AUTHORED)),
                       *liveness_filters(far, profile, include_meta=False))
            )
        else:
            adj = adjacency(tables, "out", AUTHORED)
            stmt = (
                select(adj.c.to)
                .select_from(adj.join(far, far.c.entry_id == adj.c.to))
                .where(adj.c.frm.in_(chunk), *liveness_filters(far, profile, include_meta=False))
            )
        return stmt.distinct() if distinct else stmt

    def pinned_stmt(chunk):
        """The profile's own range-join keyword (CROSS JOIN on SQLite) forces the IN-list side to drive."""
        on = far.c.entry_id == edges.c.target_id
        joined = _RangeJoin(edges, far, on, profile.range_join)
        return (
            select(edges.c.target_id)
            .select_from(joined)
            .where(edges.c.source_id.in_(chunk), edges.c.edge_type.in_(list(AUTHORED)),
                   *liveness_filters(far, profile, include_meta=False))
            .distinct()
        )

    print(f"\nedges {profile.range_join} far (the profile's range_join keyword), DISTINCT:")
    for n in (100, 1_000, 3_000, len(seeds)):
        t0 = time.perf_counter()
        got = await rows(storage, pinned_stmt(seeds[:n]))
        print(f"    IN-list of {n:>5}: {len(got):>6} rows in {time.perf_counter() - t0:.3f}s")
    for r in await rows(storage, text("EXPLAIN QUERY PLAN " + literal_sql(pinned_stmt(seeds[:1000]), dialect))):
        print("        plan:", r[3])

    for flat in (True,):
        for distinct in (True,):
            label = f"{'edges table directly' if flat else 'adjacency subquery'}, {'DISTINCT' if distinct else 'no DISTINCT'}"
            print(f"\n{label}:")
            for n in (100, 1_000, 3_000):
                chunk = seeds[:n]
                t0 = time.perf_counter()
                got = await rows(storage, frontier_stmt(chunk, distinct=distinct, flat=flat))
                dt = time.perf_counter() - t0
                print(f"    IN-list of {n:>5}: {len(got):>6} rows in {dt:.3f}s")
                if dt > 20:
                    break
            plan = await rows(storage, text("EXPLAIN QUERY PLAN " + literal_sql(frontier_stmt(seeds[:1000], distinct=distinct, flat=flat), dialect)))
            for r in plan:
                print("        plan:", r[3])
    print("\nafter ANALYZE (planner statistics), plain JOIN form, DISTINCT:")
    async with storage._host.session_factory() as session:
        await session.execute(text("ANALYZE"))
        await session.commit()
    for n in (100, 1_000, 3_000):
        t0 = time.perf_counter()
        got = await rows(storage, frontier_stmt(seeds[:n], distinct=True, flat=True))
        print(f"    IN-list of {n:>5}: {len(got):>6} rows in {time.perf_counter() - t0:.3f}s")
    for r in await rows(storage, text("EXPLAIN QUERY PLAN " + literal_sql(frontier_stmt(seeds[:1000], distinct=True, flat=True), dialect))):
        print("        plan:", r[3])
    await storage.close()


if __name__ == "__main__":
    run(main)
