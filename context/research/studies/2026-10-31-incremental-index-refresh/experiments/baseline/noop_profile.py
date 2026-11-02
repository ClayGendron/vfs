"""Where does a no-op reindex spend its time? Per-statement wall on the finished corpus_N.db."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import event  # noqa: E402

from harness import open_store, timed  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


async def main(n: int) -> None:
    storage, _ = await open_store(os.path.join(HERE, f"corpus_{n}.db"))
    rows: list[dict] = []
    start: dict = {}

    @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
    def before(conn, cursor, statement, parameters, context, executemany) -> None:
        start[id(cursor)] = time.perf_counter()

    @event.listens_for(storage._host.engine.sync_engine, "after_cursor_execute")
    def after(conn, cursor, statement, parameters, context, executemany) -> None:
        rows.append({"s": round(time.perf_counter() - start.pop(id(cursor), time.perf_counter()), 3), "sql": " ".join(statement.split())[:160]})

    result, wall = await timed(storage.reindex())
    assert result.success
    rows.sort(key=lambda r: -r["s"])
    out = {"n": n, "wall_s": wall, "statements": len(rows), "top": rows[:8]}
    print(json.dumps(out, indent=1))
    with open(os.path.join(HERE, f"results_noop_{n}.json"), "w") as f:
        json.dump(out, f, indent=1)
    await storage.close()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1])))
