"""Probe 2: every statement one caller's verb issues at each N, with its bind count and bound bytes.

usage: probe_statements.py DATA_DIR <caller> <verb-key> N [N ...]
"""

from __future__ import annotations

import asyncio
import os
import re
import sys

from probe_compile import verbs  # noqa: F401  (argv parsing below runs before its main)
from world import DATA, Recorder

from vfs.storage.backends.database import DatabaseStorage

HERE = DATA


async def one(n: int, caller: str, key: str) -> list[tuple[str, int, int]]:
    url = f"sqlite+aiosqlite:///{os.path.join(HERE, f'world-{n}.sqlite')}"
    storage = DatabaseStorage(url=url, posture="read")
    rec = Recorder(storage)
    try:
        call = verbs(caller)[key]
        await call(storage)
        _, rows = await rec.run(call(storage))
    finally:
        await storage.close()
    return rows


async def main() -> None:
    caller, key, *sizes = sys.argv[2:]
    for n in map(int, sizes):
        rows = await one(n, caller, key)
        print(f"===== {caller} {key} N={n}: {len(rows)} statements")
        for i, (text, binds, size) in enumerate(rows):
            squeezed = re.sub(r"(\?, )+\?", "?,…,?", re.sub(r"\s+", " ", text))
            print(f"[{i}] binds={binds} bytes={size} :: {squeezed[:400]}")


asyncio.run(main())
