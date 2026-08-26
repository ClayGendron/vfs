"""Spec 102 follow-up: the 10k-path snapshot fetch on MSSQL — IN list vs VALUES join.

The set-based prototype's MSSQL residual is the snapshot fetch the live
arm also pays: ``rows_by_path``'s chunked IN list. This measures that
shape against a VALUES-join fetch chunked by the same bind budget.

    VFS_TEST_MSSQL_URL=... uv run python mssql_snapshot_fetch.py
"""

from __future__ import annotations

import asyncio
import os
import time

from common import ENGINE_ENV, minted, save, scattered_corpus
from sqlalchemy import column, select, values

from vfs.storage.backends.database.descent import rows_by_path
from vfs.storage.backends.database.dialects import chunked


async def main() -> None:
    results = {}
    for engine in ("mssql", "postgres"):
        url = os.environ.get(ENGINE_ENV[engine])
        if not url:
            continue
        async with minted(url) as storage:
            entries, targets = scattered_corpus(10000, dirs_with_children=100)
            assert (await storage.write(entries=entries, parents=True)).success
            host = storage._host
            entry = host.tables.entry
            paths = [str(t) for t in targets]
            cols = [entry.c.entry_id, entry.c.parent_id, entry.c.name, entry.c.path, entry.c.version, entry.c.kind]
            runs = {}
            async with host.session_factory() as session:
                for label in ("in-list", "values-join", "in-list", "values-join"):
                    t0 = time.perf_counter()
                    if label == "in-list":
                        found = await rows_by_path(session, entry, paths, cols, host.membership_budget)
                        n, statements = len(found), -(-len(paths) // host.membership_budget)
                    else:
                        per = max(1, min(host.membership_budget, host.parameter_budget - 8))
                        n, statements = 0, 0
                        for chunk in chunked(paths, per):
                            v = values(column("v_path", entry.c.path.type), name="wanted").data([(p,) for p in chunk])
                            stmt = select(*cols).select_from(entry.join(v, entry.c.path == v.c.v_path))
                            n += len((await session.execute(stmt)).all())
                            statements += 1
                    runs.setdefault(label, []).append({"seconds": round(time.perf_counter() - t0, 3), "rows": n, "statements": statements})
            results[engine] = {"membership_budget": host.membership_budget, "parameter_budget": host.parameter_budget, "runs": runs}
            print(engine, runs)
    save("snapshot-fetch-10k", results)


if __name__ == "__main__":
    asyncio.run(main())
