"""Spec 080 research: guarded batch UPDATE shapes on the MySQL family, live.

Q1 rowcount semantics (FOUND_ROWS vs affected rows), Q2 the set-based
statement shapes SQLAlchemy renders for the family and their bind width,
Q3 attribution on an aggregate mismatch (savepoint rollback + per-row
redrive), Q4 both members — run against every family URL in the
environment (VFS_TEST_MYSQL_URL, VFS_TEST_MARIADB_URL).

    uv run python context/research/studies/2026-08-25-set-based-topology-statements/mysql_update_shapes.py 1000 10000
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from datetime import UTC, datetime
from urllib.parse import urlsplit

import aiomysql
from common import minted, save, scattered_corpus
from pymysql.constants import CLIENT
from sqlalchemy import bindparam, case, literal, select, text, union_all, update

from vfs.storage.backends.database.dialects import chunked, op_execution_options

FAMILY = {"mysql": "VFS_TEST_MYSQL_URL", "mariadb": "VFS_TEST_MARIADB_URL"}


def per_row_stmt(entry):
    """Today's guarded shape: one row per statement, executemany-driven."""
    return (
        update(entry)
        .where(
            entry.c.entry_id == bindparam("b_id"),
            entry.c.version == bindparam("b_base"),
            entry.c.path == bindparam("b_path"),
        )
        .values(version=bindparam("b_new"), updated_at=bindparam("b_now"))
    )


def union_stmt(entry, chunk, now):
    """Multi-table UPDATE over a UNION ALL derived table — the family's join spelling."""
    selects = [
        select(
            literal(r.entry_id, entry.c.entry_id.type).label("v_id"),
            literal(r.version, entry.c.version.type).label("v_base"),
            literal(r.path, entry.c.path.type).label("v_path"),
        )
        for r in chunk
    ]
    v = union_all(*selects).subquery("v")
    return (
        update(entry)
        .where(entry.c.entry_id == v.c.v_id, entry.c.version == v.c.v_base, entry.c.path == v.c.v_path)
        .values(version=v.c.v_base + 1, updated_at=now)
    )


def case_stmt(entry, chunk, now):
    """Single-table UPDATE with a CASE-keyed guard over an IN list."""
    base = case(*[(literal(r.entry_id, entry.c.entry_id.type), r.version) for r in chunk], value=entry.c.entry_id)
    return (
        update(entry)
        .where(entry.c.entry_id.in_([r.entry_id for r in chunk]), entry.c.version == base)
        .values(version=entry.c.version + 1, updated_at=now)
    )


async def current_rows(session, entry, n):
    stmt = (
        select(entry.c.entry_id, entry.c.version, entry.c.path)
        .where(entry.c.kind == "file")
        .order_by(entry.c.path)
        .limit(n)
    )
    return (await session.execute(stmt)).all()


async def timed_shape(host, name, n, build, width):
    """Run one shape over n fresh rows in its own transaction; return the numbers."""
    entry = host.tables.entry
    async with host.session_factory() as session:
        await session.connection(execution_options=op_execution_options(host.profile, writer=True))
        rows = await current_rows(session, entry, n)
        now = datetime.now(UTC)
        chunk_size = max(1, min(host.membership_budget, host.parameter_budget // width))
        t0 = time.perf_counter()
        matched = 0
        statements = 0
        if name == "per-row executemany":
            params = [
                {"b_id": r.entry_id, "b_base": r.version, "b_path": r.path, "b_new": r.version + 1, "b_now": now}
                for r in rows
            ]
            result = await session.execute(per_row_stmt(entry), params)
            matched, statements = result.rowcount, 1
        else:
            for chunk in chunked(rows, chunk_size):
                result = await session.execute(build(entry, chunk, now))
                matched += result.rowcount
                statements += 1
        elapsed = time.perf_counter() - t0
        after = await current_rows(session, entry, n)
        bumped = sum(1 for a, b in zip(rows, after, strict=True) if b.version == a.version + 1)
        await session.commit()
    return {
        "shape": name,
        "rows": n,
        "seconds": round(elapsed, 3),
        "matched": matched,
        "bumped": bumped,
        "sqlalchemy_statements": statements,
        "chunk_rows": None if name == "per-row executemany" else chunk_size,
        "binds_per_row": width,
    }


async def rowcount_semantics(host, url):
    """Q1: a matched-but-unchanged UPDATE under SQLAlchemy's flag vs a raw driver connection."""
    entry = host.tables.entry
    async with host.session_factory() as session:
        await session.connection(execution_options=op_execution_options(host.profile, writer=True))
        (row,) = (await current_rows(session, entry, 1))
        unchanged = await session.execute(
            update(entry).where(entry.c.entry_id == row.entry_id).values(version=entry.c.version)
        )
        sqlalchemy_rowcount = unchanged.rowcount
        await session.rollback()
    parts = urlsplit(url)
    raw = {}
    for label, flag in (("default client_flag", 0), ("CLIENT.FOUND_ROWS", CLIENT.FOUND_ROWS)):
        conn = await aiomysql.connect(
            host=parts.hostname, port=parts.port, user=parts.username, password=parts.password,
            db=parts.path.lstrip("/"), client_flag=flag, autocommit=False,
        )
        try:
            async with conn.cursor() as cur:
                # Keyed on path: entry_id is a 16-byte ULID the raw driver cannot bind from text.
                await cur.execute(f"UPDATE `{entry.name}` SET version = version WHERE path = %s", (row.path,))
                raw[label] = cur.rowcount
            await conn.rollback()
        finally:
            conn.close()
    dialect = host.engine.sync_engine.dialect
    return {
        "dialect_name": dialect.name,
        "is_mariadb": bool(getattr(dialect, "is_mariadb", False)),
        "server_version": ".".join(str(p) for p in (dialect.server_version_info or ())),
        "profile": host.profile.name,
        "sqlalchemy_found_rows_flag": dialect._found_rows_client_flag(),
        "matched_unchanged_rowcount_via_sqlalchemy": sqlalchemy_rowcount,
        "matched_unchanged_rowcount_raw": raw,
    }


async def mismatch_attribution(host, n):
    """Q3: one stale guard in a set-based chunk — aggregate miss, savepoint rollback, per-row blame."""
    entry = host.tables.entry
    async with host.session_factory() as session:
        await session.connection(execution_options=op_execution_options(host.profile, writer=True))
        rows = await current_rows(session, entry, n)
        stale = rows[n // 2]
        await session.execute(update(entry).where(entry.c.entry_id == stale.entry_id).values(version=entry.c.version + 1))
        now = datetime.now(UTC)
        nested = await session.begin_nested()
        result = await session.execute(union_stmt(entry, rows, now))
        aggregate = result.rowcount
        await nested.rollback()
        after_rollback = await current_rows(session, entry, n)
        untouched = all(b.version == a.version for a, b in zip(rows, after_rollback, strict=True) if a.entry_id != stale.entry_id)
        missed = []
        for r in rows:
            single = await session.execute(
                per_row_stmt(entry),
                {"b_id": r.entry_id, "b_base": r.version, "b_path": r.path, "b_new": r.version + 1, "b_now": now},
            )
            if single.rowcount == 0:
                missed.append(r.path)
        await session.rollback()
    return {
        "rows": n,
        "aggregate_rowcount": aggregate,
        "expected_if_all_matched": n,
        "savepoint_rollback_left_others_untouched": untouched,
        "per_row_redrive_blamed": missed,
        "stale_row": stale.path,
    }


async def run(member, url, sizes):
    async with minted(url) as storage:
        entries, _ = scattered_corpus(max(sizes))
        written = await storage.write(entries=entries, parents=True)
        assert written.success, written.errors[:3]
        host = storage._host
        payload = {"member": member, "url_scheme": url.split("://")[0], "semantics": await rowcount_semantics(host, url), "shapes": []}
        rendered = union_stmt(host.tables.entry, await _peek(host, 2), datetime.now(UTC))
        payload["rendered_union_shape"] = str(rendered.compile(dialect=host.engine.sync_engine.dialect))[:600]
        for n in sizes:
            payload["shapes"].append(await timed_shape(host, "per-row executemany", n, None, 5))
            payload["shapes"].append(await timed_shape(host, "UNION ALL derived-table join", n, union_stmt, 3))
            payload["shapes"].append(await timed_shape(host, "CASE-keyed guard over IN", n, case_stmt, 3))
        payload["mismatch"] = await mismatch_attribution(host, min(sizes))
        save(f"mysql-shapes-{member}", payload)
        for s in payload["shapes"]:
            print(f"{member} {s['rows']:>6} {s['shape']:<30} {s['seconds']:>8.3f}s matched={s['matched']} bumped={s['bumped']}")
        print(member, "semantics:", payload["semantics"])
        print(member, "mismatch:", payload["mismatch"])


async def _peek(host, n):
    async with host.session_factory() as session:
        return await current_rows(session, host.tables.entry, n)


async def main():
    sizes = [int(a) for a in sys.argv[1:]] or [1000, 10000]
    for member, env in FAMILY.items():
        url = os.environ.get(env)
        if url:
            await run(member, url, sizes)


if __name__ == "__main__":
    asyncio.run(main())
