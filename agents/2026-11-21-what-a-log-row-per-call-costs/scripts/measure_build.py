"""How long the harness itself takes to build one 10,000-entry batch on the event loop, with no database.

``do_batch`` builds its entries on the caller's loop before the verb is called, so this time is inside the
window in which ``measure_waits.py`` counts a read as *during* the batch. It is the harness's share of a
read's stall there, not vfs's.

    uv run python scripts/measure_build.py

The script writes ``results/build.json``.
"""

from __future__ import annotations

import sys
import time

from harness import BATCH_SIZE, body, environment, summary_ms, write_results

from vfs import Entry

REPEATS = 5


def main() -> None:
    seconds = []
    for _ in range(REPEATS):
        start = time.perf_counter()
        entries = [
            Entry(path=f"/batch/b/{i // 100:03d}/f{i:05d}.md", content=body(f"/batch/b-{i}")) for i in range(BATCH_SIZE)
        ]
        seconds.append(time.perf_counter() - start)
        del entries
    payload = {
        "script": "scripts/measure_build.py",
        "environment": environment(),
        "entries": BATCH_SIZE,
        "repeats_ms": [round(s * 1000, 1) for s in seconds],
        **summary_ms(seconds),
    }
    out = write_results("build.json", payload)
    print(f"wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
