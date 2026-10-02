"""``filter_shapes.py`` on Postgres 17 + pgvector: the same shapes, the same corpus.

Builds its tables in a throwaway schema ``dls_study`` (dropped at the end) on
the docker test container, then times the visible-corpus count and the
vector leg under OR'd LIKE arms, an inline ``VALUES`` range join, and the
ordinal seeks. Paths are ``COLLATE "C"`` as vfs pins them.

    PG=postgresql://vfs:vfs@localhost:54320/vfs uv run --no-sync python filter_shapes_pg.py

Study code only: nothing here is imported by vfs.
"""

from __future__ import annotations

import asyncio
import os
import random
import statistics
import time

import asyncpg

from filter_shapes import DIM, TOPS, callers, ranges

REPEATS = 5
FOLDERS, FILES = 100, 50
ARMS_PER_STATEMENT = 400


async def build(db: asyncpg.Connection) -> None:
    rng = random.Random(30)
    await db.execute(
        "DROP SCHEMA IF EXISTS dls_study CASCADE; CREATE SCHEMA dls_study; SET search_path = dls_study, public"
    )
    await db.execute(
        f"""
        CREATE TABLE entry (id bigserial PRIMARY KEY, entry_id text NOT NULL UNIQUE,
                            path varchar(4096) COLLATE "C" NOT NULL UNIQUE, owner_id text, kind text NOT NULL,
                            deleted_at timestamptz);
        CREATE TABLE lex_docs (epoch int, chunk_id bigint, entry_id text NOT NULL, dl int NOT NULL,
                               PRIMARY KEY (epoch, chunk_id));
        CREATE INDEX ix_docs_entry ON lex_docs(epoch, entry_id);
        CREATE TABLE chunks (id bigint PRIMARY KEY, entry_id text NOT NULL, embedding vector({DIM}));
        CREATE INDEX ix_chunks_entry ON chunks(entry_id);
        CREATE TABLE lex_order (epoch int, path varchar(4096) COLLATE "C", chunk_id bigint, ord int, cum_dl bigint,
                                PRIMARY KEY (epoch, path, chunk_id));
        """
    )
    paths = [f"/t{t:02d}/f{f:03d}/doc{n:03d}.md" for t in range(TOPS) for f in range(FOLDERS) for n in range(FILES)]
    order = list(range(len(paths)))
    rng.shuffle(order)
    dirs = [f"/t{t:02d}" for t in range(TOPS)] + [f"/t{t:02d}/f{f:03d}" for t in range(TOPS) for f in range(FOLDERS)]
    rows = [(f"d{i}", p, "owner", "directory") for i, p in enumerate(dirs)]
    rows += [(f"e{i}", paths[i], "owner", "file") for i in order]
    await db.copy_records_to_table("entry", records=rows, columns=["entry_id", "path", "owner_id", "kind"])
    docs, chunks = [], []
    for chunk_id, i in enumerate(order, start=1):
        docs.append((1, chunk_id, f"e{i}", rng.randint(80, 220)))
        vec = "[" + ",".join(f"{rng.gauss(0, 1):.5f}" for _ in range(DIM)) + "]"
        chunks.append((chunk_id, f"e{i}", vec))
    await db.copy_records_to_table("lex_docs", records=docs)
    await db.executemany("INSERT INTO chunks VALUES ($1, $2, $3::vector)", chunks)
    ordered = await db.fetch(
        "SELECT e.path, d.chunk_id, d.dl FROM lex_docs d JOIN entry e ON e.entry_id = d.entry_id "
        "WHERE d.epoch = 1 ORDER BY e.path, d.chunk_id"
    )
    cum, out = 0, []
    for ord_, row in enumerate(ordered):
        out.append((1, row["path"], row["chunk_id"], ord_, cum))
        cum += row["dl"]
    out.append((1, "\U0010ffff", 0, len(ordered), cum))
    await db.copy_records_to_table("lex_order", records=out)
    for table in ("entry", "lex_docs", "chunks", "lex_order"):
        await db.execute(f"VACUUM ANALYZE {table}")


def like_arms(prefixes: list[str], start: int) -> tuple[str, list[str]]:
    parts, binds = [], []
    for k, p in enumerate(prefixes):
        a, b = start + 2 * k, start + 2 * k + 1
        parts.append(f"(e.path = ${a} OR e.path LIKE ${b})")
        binds += [p, p + "/%"]
    return "(" + " OR ".join(parts) + ")", binds


def values_table(spans: list[tuple[str, str]], start: int) -> tuple[str, list[str]]:
    rows = ", ".join(
        f'(${start + 2 * k}::text COLLATE "C", ${start + 2 * k + 1}::text COLLATE "C")' for k in range(len(spans))
    )
    return f"(VALUES {rows}) AS r(lo, hi)", [b for span in spans for b in span]


async def corpus_like(db: asyncpg.Connection, prefixes: list[str]) -> tuple[int, int]:
    if len(prefixes) <= ARMS_PER_STATEMENT:
        where, binds = like_arms(prefixes, 1)
        row = await db.fetchrow(
            "SELECT count(*), coalesce(sum(d.dl),0) FROM lex_docs d JOIN entry e ON e.entry_id = d.entry_id "
            f"WHERE d.epoch = 1 AND {where}",
            *binds,
        )
        return int(row[0]), int(row[1])
    seen: dict[int, int] = {}
    for i in range(0, len(prefixes), ARMS_PER_STATEMENT):
        where, binds = like_arms(prefixes[i : i + ARMS_PER_STATEMENT], 1)
        for row in await db.fetch(
            "SELECT d.chunk_id, d.dl FROM lex_docs d JOIN entry e ON e.entry_id = d.entry_id "
            f"WHERE d.epoch = 1 AND {where}",
            *binds,
        ):
            seen[row[0]] = row[1]
    return len(seen), sum(seen.values())


SLICE = 500  # ranges per statement: 1,000 binds, inside SQL Server's ~2,100


async def corpus_values(db: asyncpg.Connection, prefixes: list[str]) -> tuple[int, int]:
    spans = ranges(prefixes)
    count = total = 0
    for i in range(0, len(spans), SLICE):
        table, binds = values_table(spans[i : i + SLICE], 1)
        row = await db.fetchrow(
            f"SELECT count(*), coalesce(sum(d.dl),0) FROM {table} "
            "JOIN entry e ON e.path >= r.lo AND e.path < r.hi "
            "JOIN lex_docs d ON d.epoch = 1 AND d.entry_id = e.entry_id",
            *binds,
        )
        count, total = count + int(row[0]), total + int(row[1])
    return count, total


async def corpus_ordinal(db: asyncpg.Connection, prefixes: list[str]) -> tuple[int, int]:
    spans = ranges(prefixes)
    count = total = 0
    seek = (
        "(SELECT o.{col} FROM lex_order o WHERE o.epoch = 1 AND o.path >= r.{end} ORDER BY o.path, o.chunk_id LIMIT 1)"
    )
    for i in range(0, len(spans), SLICE):
        table, binds = values_table(spans[i : i + SLICE], 1)
        row = await db.fetchrow(
            f"SELECT sum({seek.format(col='ord', end='hi')} - {seek.format(col='ord', end='lo')}), "
            f"sum({seek.format(col='cum_dl', end='hi')} - {seek.format(col='cum_dl', end='lo')}) FROM {table}",
            *binds,
        )
        count, total = count + int(row[0]), total + int(row[1])
    return count, total


QUERY = "[" + ",".join(f"{random.Random(7).gauss(0, 1):.5f}" for _ in range(DIM)) + "]"


async def vector_whole(db: asyncpg.Connection, _prefixes: list[str]) -> list[int]:
    rows = await db.fetch(
        "SELECT c.id, c.embedding <=> $1::vector AS dist FROM chunks c JOIN entry e ON e.entry_id = c.entry_id "
        "WHERE e.deleted_at IS NULL ORDER BY dist, c.id LIMIT 10",
        QUERY,
    )
    return [r[0] for r in rows]


async def vector_like(db: asyncpg.Connection, prefixes: list[str]) -> list[int]:
    found = []
    for i in range(0, len(prefixes), ARMS_PER_STATEMENT):
        where, binds = like_arms(prefixes[i : i + ARMS_PER_STATEMENT], 2)
        found += await db.fetch(
            "SELECT c.id, c.embedding <=> $1::vector AS dist FROM chunks c JOIN entry e ON e.entry_id = c.entry_id "
            f"WHERE e.deleted_at IS NULL AND {where} ORDER BY dist, c.id LIMIT 10",
            QUERY,
            *binds,
        )
    return [r[0] for r in sorted(found, key=lambda r: (r[1], r[0]))[:10]]


async def vector_values(db: asyncpg.Connection, prefixes: list[str]) -> list[int]:
    spans = ranges(prefixes)
    found = []
    for i in range(0, len(spans), SLICE):
        table, binds = values_table(spans[i : i + SLICE], 2)
        found += await db.fetch(
            f"SELECT c.id, c.embedding <=> $1::vector AS dist FROM {table} "
            "JOIN entry e ON e.path >= r.lo AND e.path < r.hi JOIN chunks c ON c.entry_id = e.entry_id "
            "WHERE e.deleted_at IS NULL ORDER BY dist, c.id LIMIT 10",
            QUERY,
            *binds,
        )
    return [r[0] for r in sorted(found, key=lambda r: (r[1], r[0]))[:10]]


async def timed(fn, *args) -> tuple[float, object]:
    await fn(*args)
    samples, out = [], None
    for _ in range(REPEATS):
        start = time.perf_counter()
        out = await fn(*args)
        samples.append((time.perf_counter() - start) * 1000)
    return statistics.median(samples), out


async def main() -> None:
    db = await asyncpg.connect(os.environ.get("PG", "postgresql://vfs:vfs@localhost:54320/vfs"))
    try:
        await build(db)
        version = await db.fetchval("SHOW server_version")
        whole, _ = await timed(vector_whole, db, [])
        print(f"## postgres {version} + pgvector — 50,000 chunks, dim {DIM}, median of {REPEATS} warm runs\n")
        print(f"whole-mount vector leg (no filter): {whole:.1f} ms\n")
        print("| caller | corpus: like | corpus: values join | corpus: ordinal | vector: like | vector: values join |")
        print("|---|---|---|---|---|---|")
        for label, prefixes in callers(FOLDERS, FILES).items():
            c_like, a = await timed(corpus_like, db, prefixes)
            c_values, b = await timed(corpus_values, db, prefixes)
            c_ord, c = await timed(corpus_ordinal, db, prefixes)
            assert a == b == c, (label, a, b, c)
            v_like, x = await timed(vector_like, db, prefixes)
            v_values, y = await timed(vector_values, db, prefixes)
            assert x == y, (label, x, y)
            print(
                f"| {label} ({a[0]:,} visible) | {c_like:.1f} | {c_values:.1f} | {c_ord:.2f} | {v_like:.1f} | {v_values:.1f} |"
            )
        prefixes = callers(FOLDERS, FILES)["100 grants (10%)"]
        where, binds = like_arms(prefixes, 1)
        plan = await db.fetch(
            "EXPLAIN SELECT count(*) FROM lex_docs d JOIN entry e ON e.entry_id = d.entry_id "
            f"WHERE d.epoch = 1 AND {where}",
            *binds,
        )
        print("\nlike plan (100 grants), top nodes: " + " | ".join(r[0].strip()[:90] for r in plan[:4]))
    finally:
        await db.execute("DROP SCHEMA IF EXISTS dls_study CASCADE")
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
