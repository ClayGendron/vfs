"""cProfile of a no-op reindex on corpus_N.db: which Python functions hold the wall the SQL does not explain."""

from __future__ import annotations

import asyncio
import cProfile
import io
import os
import pstats
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import open_store, timed  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


async def run(n: int) -> None:
    storage, _ = await open_store(os.path.join(HERE, f"corpus_{n}.db"))
    result, wall = await timed(storage.reindex())
    assert result.success
    print("noop wall", wall)
    await storage.close()


if __name__ == "__main__":
    n = int(sys.argv[1])
    prof = cProfile.Profile()
    prof.enable()
    asyncio.run(run(n))
    prof.disable()
    buf = io.StringIO()
    pstats.Stats(prof, stream=buf).sort_stats("cumulative").print_stats(r"vfs/(storage|models|paths)", 25)
    text = buf.getvalue()
    print(text)
    with open(os.path.join(HERE, f"results_noop_cprofile_{n}.txt"), "w") as f:
        f.write(text)
