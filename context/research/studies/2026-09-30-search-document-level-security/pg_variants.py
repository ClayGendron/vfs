"""Follow-up to ``filter_shapes_pg.py``: shapes that keep one statement whatever the grant count.

- ``unnest``: the caller's ranges ride as two array binds, ``unnest($1, $2)``,
  so the statement and its bind count are the same at 1 grant or 10,000.
- ``ordinal, unnest``: the ordinal seeks, fed the same way.
- ``post-filter``: the vector leg runs unfiltered (the whole-mount statement),
  and the caller's ranges are checked in Python on the rows it returns,
  deepening the window 4x until ``k`` visible rows arrive — the way vector
  engines switch between pre- and post-filtering by filter selectivity.

    uv run --no-sync python pg_variants.py

Study code only: nothing here is imported by vfs.
"""

from __future__ import annotations

import asyncio
import bisect
import os

import asyncpg

from filter_shapes import callers, ranges
from filter_shapes_pg import FILES, FOLDERS, QUERY, build, timed, vector_whole

K = 10


async def corpus_unnest(db: asyncpg.Connection, prefixes: list[str]) -> tuple[int, int]:
    spans = ranges(prefixes)
    row = await db.fetchrow(
        "SELECT count(*), coalesce(sum(d.dl),0) FROM unnest($1::text[], $2::text[]) AS r(lo, hi) "
        'JOIN entry e ON e.path >= r.lo COLLATE "C" AND e.path < r.hi COLLATE "C" '
        "JOIN lex_docs d ON d.epoch = 1 AND d.entry_id = e.entry_id",
        [s[0] for s in spans],
        [s[1] for s in spans],
    )
    return int(row[0]), int(row[1])


async def corpus_ordinal_unnest(db: asyncpg.Connection, prefixes: list[str]) -> tuple[int, int]:
    spans = ranges(prefixes)
    seek = (
        '(SELECT o.{col} FROM lex_order o WHERE o.epoch = 1 AND o.path >= r.{end} COLLATE "C" '
        "ORDER BY o.path, o.chunk_id LIMIT 1)"
    )
    row = await db.fetchrow(
        f"SELECT sum({seek.format(col='ord', end='hi')} - {seek.format(col='ord', end='lo')}), "
        f"sum({seek.format(col='cum_dl', end='hi')} - {seek.format(col='cum_dl', end='lo')}) "
        "FROM unnest($1::text[], $2::text[]) AS r(lo, hi)",
        [s[0] for s in spans],
        [s[1] for s in spans],
    )
    return int(row[0]), int(row[1])


async def vector_unnest(db: asyncpg.Connection, prefixes: list[str]) -> list[int]:
    spans = ranges(prefixes)
    rows = await db.fetch(
        "SELECT c.id, c.embedding <=> $1::vector AS dist FROM unnest($2::text[], $3::text[]) AS r(lo, hi) "
        'JOIN entry e ON e.path >= r.lo COLLATE "C" AND e.path < r.hi COLLATE "C" '
        "JOIN chunks c ON c.entry_id = e.entry_id WHERE e.deleted_at IS NULL ORDER BY dist, c.id LIMIT 10",
        QUERY,
        [s[0] for s in spans],
        [s[1] for s in spans],
    )
    return [r[0] for r in rows]


def admits(los: list[str], his: list[str], path: str) -> bool:
    i = bisect.bisect_right(los, path) - 1
    return i >= 0 and path < his[i]


async def vector_post_filter(db: asyncpg.Connection, prefixes: list[str]) -> tuple[list[int], int]:
    spans = ranges(prefixes)  # sorted and disjoint for these callers
    los, his = [s[0] for s in spans], [s[1] for s in spans]
    window, total = K * 4, await db.fetchval("SELECT count(*) FROM chunks")
    while True:
        rows = await db.fetch(
            "SELECT c.id, c.embedding <=> $1::vector AS dist, e.path FROM chunks c "
            "JOIN entry e ON e.entry_id = c.entry_id WHERE e.deleted_at IS NULL ORDER BY dist, c.id LIMIT $2",
            QUERY,
            window,
        )
        kept = [r[0] for r in rows if admits(los, his, r[2])]
        if len(kept) >= K or len(rows) < window or window >= total:
            return kept[:K], window
        window *= 4


async def main() -> None:
    db = await asyncpg.connect(os.environ.get("PG", "postgresql://vfs:vfs@localhost:54320/vfs"))
    try:
        await build(db)
        whole, _ = await timed(vector_whole, db, [])
        print(f"whole-mount vector leg: {whole:.1f} ms\n")
        print(
            "| caller | corpus: unnest | corpus: ordinal, unnest | vector: unnest | vector: post-filter (final window) |"
        )
        print("|---|---|---|---|---|")
        for label, prefixes in callers(FOLDERS, FILES).items():
            t_u, a = await timed(corpus_unnest, db, prefixes)
            t_o, b = await timed(corpus_ordinal_unnest, db, prefixes)
            assert a == b, (label, a, b)
            t_v, x = await timed(vector_unnest, db, prefixes)
            t_p, (y, window) = await timed(vector_post_filter, db, prefixes)
            assert x == y, (label, x, y)
            print(f"| {label} ({a[0]:,} visible) | {t_u:.1f} | {t_o:.2f} | {t_v:.1f} | {t_p:.1f} ({window:,}) |")
        spans = ranges(callers(FOLDERS, FILES)["5000 file grants (10%)"])
        plan = await db.fetch(
            "EXPLAIN SELECT c.id FROM unnest($1::text[], $2::text[]) AS r(lo, hi) "
            'JOIN entry e ON e.path >= r.lo COLLATE "C" AND e.path < r.hi COLLATE "C" '
            "JOIN chunks c ON c.entry_id = e.entry_id",
            [s[0] for s in spans],
            [s[1] for s in spans],
        )
        print("\nunnest plan (5000 file grants): " + " | ".join(r[0].strip()[:80] for r in plan[:5]))
    finally:
        await db.execute("DROP SCHEMA IF EXISTS dls_study CASCADE")
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
