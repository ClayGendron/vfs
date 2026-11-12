"""EXPLAIN (ANALYZE, BUFFERS) of the lexical build's page statement on the Postgres store.

Runs the shipped join page, the scalar-subquery page and the chunks-alone
page at several ``last`` offsets through the vfs engine's own connection
(asyncpg), and records the plans with their buffer counts and timings.
Usage: uv run python explain_postgres.py <url> <schema> <out json> <out text>
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.dialects import postgresql

from harness import exists_subquery_statement, joined_page_statement, scalar_subquery_statement
from vfs.storage.backends import DatabaseStorage


def render(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


async def main() -> None:
    url, schema, out_json, out_text = sys.argv[1], sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4])
    storage = DatabaseStorage(url=url, schema=schema)
    assert await storage._host.ensure_ready() is None
    t = storage._host.tables
    chunks = t.chunks
    lines: list[str] = []
    report: dict[str, object] = {"statements": {}}
    async with storage._host.engine.connect() as conn:
        report["version"] = (await conn.execute(text("SELECT version()"))).scalar_one()
        lines.append(report["version"])
        max_id = (await conn.execute(text(f"SELECT max(id) FROM {chunks.fullname}"))).scalar_one()
        shapes = {
            "shipped_join": lambda last, limit: joined_page_statement(t, limit).where(chunks.c.id > last),
            "scalar_subquery": lambda last, limit: scalar_subquery_statement(t, limit).where(chunks.c.id > last),
            "in_subquery": lambda last, limit: exists_subquery_statement(t, limit).where(chunks.c.id > last),
            "chunks_alone": lambda last, limit: (
                __import__("sqlalchemy").select(chunks.c.id, chunks.c.entry_id, chunks.c.content)
                .where(chunks.c.id > last)
                .order_by(chunks.c.id)
                .limit(limit)
            ),
        }
        for name, make in shapes.items():
            lines.append("")
            lines.append(f"== {name}")
            lines.append(render(make(0, 256)).replace("\n", " "))
            entry = {"sql": render(make(0, 256)), "runs": []}
            for last, limit in [(0, 256), (max_id // 2, 256), (max_id - 2000, 256), (max_id // 2, 4096)]:
                sql = render(make(last, limit))
                # Warm once, then explain.
                await conn.execute(text(sql))
                plan_rows = (await conn.execute(text("EXPLAIN (ANALYZE, BUFFERS) " + sql))).scalars().all()
                t0 = time.perf_counter()
                for _ in range(5):
                    rows = (await conn.execute(text(sql))).all()
                wall_ms = round(1000 * (time.perf_counter() - t0) / 5, 3)
                entry["runs"].append({"last": last, "limit": limit, "rows": len(rows), "driver_wall_ms_mean_of_5": wall_ms, "plan": plan_rows})
                lines.append(f"  last={last} limit={limit} rows={len(rows)} driver wall (mean of 5) {wall_ms} ms")
                lines.extend(f"    {p}" for p in plan_rows)
            report["statements"][name] = entry
    await storage.close()
    out_text.write_text("\n".join(lines) + "\n")
    out_json.write_text(json.dumps(report, indent=2, default=str) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(main())
