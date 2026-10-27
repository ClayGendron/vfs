"""Count SQL statements per public verb on InMemoryStorage (study 05, Q7).

Counts, never times. One VirtualFileSystem over one InMemoryStorage; a
SQLAlchemy ``before_cursor_execute`` listener records every statement the
engine issues. Each verb runs once per authority class (system, a named
principal, anonymous) and the statements are bucketed by the table they
touch, so the "essential" statements of a verb separate from the ones the
shape adds (rights resolution, posture reads, version minting, parent
bumps, the trash/liveness predicate rides inside the entry select).

Run: uv run python context/research/studies/2026-10-23-filesystem-shaped-api/experiments/s05/statements.py
"""

from __future__ import annotations

import asyncio
import re
from collections import Counter
from pathlib import Path as FsPath

from sqlalchemy import event

from vfs.authority import Authority, Principal
from vfs.base import VirtualFileSystem
from vfs.models import Entry
from vfs.storage.backends.memory import InMemoryStorage

OUT = FsPath(__file__).with_suffix(".out")

CONTROL = ("BEGIN", "COMMIT", "PRAGMA", "SAVEPOINT", "RELEASE", "ROLLBACK")


def bucket(statement: str) -> str:
    """Name the statement by its verb and the first vfs table it names."""
    head = statement.split(None, 1)[0].upper()
    if head in CONTROL:
        return f"control:{head}"
    tables = re.findall(r"\bvfs_[a-z_]+", statement)
    first = tables[0] if tables else "?"
    return f"{head}:{first}"


async def main() -> None:
    storage = InMemoryStorage()
    fs = VirtualFileSystem(storage=storage)
    system = Authority.system()
    alice = Authority.of(Principal("alice"))
    anon = Authority.anonymous()

    # First touch (schema, extensions) happens once; keep it out of the per-verb counts.
    await storage.first_touch()
    statements: list[str] = []

    @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
    def record(conn, cursor, statement, parameters, context, executemany) -> None:  # noqa: ANN001
        statements.append(statement)

    lines: list[str] = []

    async def measure(label: str, coro) -> None:  # noqa: ANN001
        statements.clear()
        result = await coro
        buckets = Counter(bucket(s) for s in statements)
        essential = [s for s in statements if not s.split(None, 1)[0].upper() in CONTROL]
        lines.append(
            f"{label}: success={result.success} rows={len(result.observations)} "
            f"statements={len(statements)} (non-control={len(essential)})"
        )
        for name, count in sorted(buckets.items()):
            lines.append(f"    {count:2d}  {name}")

    # Fixture rows: one directory, one file, written by the system actor (not measured).
    await fs.mkdir("/docs", authority=system)
    await fs.write(path="/docs/a.md", content="hello\n" * 10, authority=system)
    await fs.grant("/", "alice", "read_write", authority=system)

    for who, name in ((system, "system"), (alice, "alice(named)"), (anon, "anonymous")):
        lines.append(f"\n== authority: {name} ==")
        # Warm the rights cache the way a second call in a session would see it.
        await fs.stat("/docs/a.md", authority=who)
        await measure(f"{name} read(/docs/a.md)", fs.read("/docs/a.md", authority=who))
        await measure(f"{name} stat(/docs/a.md)", fs.stat("/docs/a.md", authority=who))
        await measure(f"{name} ls(/docs)", fs.ls("/docs", authority=who))
        await measure(
            f"{name} write create (/docs/new-{name}.md)",
            fs.write(path=f"/docs/new-{name}.md", content="x", authority=who),
        )
        await measure(
            f"{name} write overwrite (/docs/new-{name}.md)",
            fs.write(path=f"/docs/new-{name}.md", content="y", authority=who),
        )
        await measure(f"{name} mkdir (/docs/d-{name})", fs.mkdir(f"/docs/d-{name}", authority=who))
        await measure(
            f"{name} move (/docs/new-{name}.md -> /docs/moved-{name}.md)",
            fs.move(f"/docs/new-{name}.md", f"/docs/moved-{name}.md", authority=who),
        )
        await measure(f"{name} delete (/docs/moved-{name}.md)", fs.delete(f"/docs/moved-{name}.md", authority=who))

    # The cold path: how much first touch costs, for the record.
    cold = InMemoryStorage()
    cold_statements: list[str] = []

    @event.listens_for(cold._host.engine.sync_engine, "before_cursor_execute")
    def record_cold(conn, cursor, statement, parameters, context, executemany) -> None:  # noqa: ANN001
        cold_statements.append(statement)

    await cold.first_touch()
    lines.append(f"\nfirst_touch on a fresh InMemoryStorage: {len(cold_statements)} statements")
    await cold.close()

    # Batch write of 100 entries by the system actor: statements vs rows.
    batch = [Entry(path=f"/batch/f{i:03}.md", content=f"body {i}") for i in range(100)]
    await measure("system write(entries=100, parents=True)", fs.write(batch, parents=True, authority=system))

    await fs.close()
    OUT.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(main())
