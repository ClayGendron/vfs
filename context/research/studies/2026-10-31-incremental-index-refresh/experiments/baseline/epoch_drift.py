"""Does a rebuild get slower with every epoch? Repeated 1%-dirty reindexes on the finished 10k store,
then VACUUM + WAL truncate, then two more. Separates 'the index grows' from 'SQLite file bloat'.

Usage: uv run python epoch_drift.py N ROUNDS_BEFORE ROUNDS_AFTER (uses corpus_N.db left by study.py; appends epochs).
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import study  # noqa: E402  (installs the phase timers at import)
from harness import db_parts_mb, open_store  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


async def main(n: int, before: int, after: int) -> None:
    db = os.path.join(HERE, f"corpus_{n}.db")
    storage, counter = await open_store(db)
    order = list(range(n))
    random.Random(7).shuffle(order)
    rows = []
    salt = 10
    for round_ in range(before):
        salt += 1
        await study.dirty(storage, order, 0, n // 100, salt=salt)
        rows.append(await study.reindex_measure(storage, counter, f"1% dirty, round {round_ + 1}, before VACUUM"))
    await storage.close()
    t0 = time.perf_counter()
    raw = sqlite3.connect(db, isolation_level=None)
    raw.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    raw.execute("VACUUM")
    raw.close()
    vacuum_s = round(time.perf_counter() - t0, 2)
    study.log(f"VACUUM took {vacuum_s}s db={db_parts_mb(db)}")
    storage, counter = await open_store(db)
    salt += 10
    for round_ in range(after):
        salt += 1
        await study.dirty(storage, order, 0, n // 100, salt=salt)
        rows.append(await study.reindex_measure(storage, counter, f"1% dirty, round {round_ + 1}, after VACUUM"))
    await storage.close()
    with open(os.path.join(HERE, f"results_drift_{n}_{before}_{after}.json"), "w") as f:
        json.dump({"vacuum_s": vacuum_s, "rounds": rows}, f, indent=1, default=str)


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])))
