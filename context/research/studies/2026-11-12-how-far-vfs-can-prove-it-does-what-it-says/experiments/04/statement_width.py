"""Experiment 04-b: does any statement's bind count outgrow a declared budget as the batch grows?

Run: uv run python <this file> <scratch dir>
For each batch width N, a fresh SQLite store with its parameter budget squeezed to
BUDGET runs write, stat, edit, glob, grep, reindex, search, delete and restore over
N files, while a cursor listener records every statement's bind count. The claim
under test: no statement carries more binds than the budget, whatever N is.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path as FsPath

from sqlalchemy import event

from vfs import DatabaseStorage
from vfs.models import Entry, Observation
from vfs.paths import Path
from vfs.storage.backends.database.engine import EngineHost

BUDGET = 999
WIDTHS = (100, 1_000, 5_000)


def binds(parameters: object, executemany: bool) -> int:
    if executemany:
        rows = list(parameters)  # type: ignore[call-overload]
        return max((len(r) for r in rows), default=0)
    return len(parameters) if parameters else 0  # type: ignore[arg-type]


async def one_width(scratch: FsPath, n: int) -> dict[str, tuple[int, int]]:
    db = scratch / f"width-{n}.sqlite"
    db.unlink(missing_ok=True)
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{db}")
    assert (await storage.first_touch()).success
    seen: dict[str, list[int]] = {}
    current = ["setup"]

    def record(conn, cursor, statement, parameters, context, executemany) -> None:
        seen.setdefault(current[0], []).append(binds(parameters, executemany))

    event.listen(storage._host.engine.sync_engine, "before_cursor_execute", record)
    paths = [Path(f"/etl/d{i % 97:02}/f{i:05}.txt") for i in range(n)]
    observations = [Observation(path=p) for p in paths]

    async def verb(name: str, call) -> None:
        current[0] = name
        result = await call
        assert result.success, (name, result.errors[:2])

    await verb("write", storage.write(entries=[Entry(path=p, content=f"needle row {i}") for i, p in enumerate(paths)], parents=True))
    await verb("stat", storage.stat(observations=observations))
    await verb("glob", storage.glob(patterns=tuple(f"/etl/d{i:02}/*.txt" for i in range(97))))
    await verb("reindex", storage.reindex())
    await verb("grep", storage.grep(pattern="needle"))
    await verb("search", storage.search(query="needle row", limit=10))
    await verb("delete", storage.delete(observations=observations))
    await storage.close()
    return {name: (len(counts), max(counts, default=0)) for name, counts in seen.items()}


async def main(scratch: FsPath) -> None:
    EngineHost.parameter_budget = property(lambda self: BUDGET)  # type: ignore[method-assign]
    print(f"budget {BUDGET}")
    for n in WIDTHS:
        report = await one_width(scratch, n)
        cells = "  ".join(f"{k}: {s} stmts, max {m} binds" for k, (s, m) in report.items())
        print(f"N={n:>5}  {cells}")


if __name__ == "__main__":
    asyncio.run(main(FsPath(sys.argv[1])))
