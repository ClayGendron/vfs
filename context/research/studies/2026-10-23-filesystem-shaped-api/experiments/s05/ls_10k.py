"""10,000 children under one directory: write them, then ls the parent (study 05, Q4b).

Counts rows returned and SQL statements issued; never times. Reports
whether any limit or cursor rides on the result (extras, warnings).

Run: uv run python context/research/studies/2026-10-23-filesystem-shaped-api/experiments/s05/ls_10k.py
"""

from __future__ import annotations

import asyncio
from collections import Counter
from pathlib import Path as FsPath

from sqlalchemy import event

from vfs.authority import Authority
from vfs.base import VirtualFileSystem
from vfs.models import Entry, Observation
from vfs.storage.backends.memory import InMemoryStorage

OUT = FsPath(__file__).with_suffix(".out")
N = 10_000


async def main() -> None:
    storage = InMemoryStorage()
    fs = VirtualFileSystem(storage=storage)
    system = Authority.system()
    await storage.first_touch()
    statements: list[str] = []

    @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
    def record(conn, cursor, statement, parameters, context, executemany) -> None:  # noqa: ANN001
        statements.append(statement)

    lines: list[str] = []

    entries = [Entry(path=f"/big/f{i:05}.txt", content=f"row {i}\n") for i in range(N)]
    statements.clear()
    written = await fs.write(entries, parents=True, authority=system)
    lines.append(
        f"write(entries={N}, parents=True): success={written.success} rows={len(written.observations)} "
        f"statements={len(statements)}"
    )
    lines.append("  heads: " + ", ".join(f"{k}={v}" for k, v in sorted(Counter(s.split(None, 1)[0] for s in statements).items())))

    for label, columns in (("ls(/big)", None), ("ls(/big, columns={kind})", frozenset({"kind"}))):
        statements.clear()
        listed = await fs.ls("/big", columns=columns, authority=system)
        obs_count = sum(1 for o in listed.observations if isinstance(o, Observation))
        extras = sorted((listed.model_extra or {}).keys())
        lines.append(
            f"{label}: success={listed.success} rows={len(listed.observations)} observations={obs_count} "
            f"statements={len(statements)} errors={len(listed.errors)} extras={extras}"
        )
        lines.append("  heads: " + ", ".join(f"{k}={v}" for k, v in sorted(Counter(s.split(None, 1)[0] for s in statements).items())))
        first = listed.observations[0]
        lines.append(f"  first row populated={sorted(first.populated)}")
        lines.append(f"  any limit/cursor field on the envelope: {[k for k in extras if 'cursor' in k or 'limit' in k or 'next' in k]}")

    # The same listing through a named principal, so the view machinery is on the path.
    from vfs.authority import Principal  # noqa: PLC0415 - scratch script

    alice = Authority.of(Principal("alice"))
    await fs.grant("/big", "alice", "read", authority=system)
    await fs.posture("/", "none", authority=system)
    await fs.ls("/big", authority=alice)  # warm the rights cache
    statements.clear()
    listed = await fs.ls("/big", authority=alice)
    lines.append(
        f"ls(/big) as alice (read grant on /big, posture none at /): rows={len(listed.observations)} "
        f"statements={len(statements)} errors={[e.kind for e in listed.errors]}"
    )
    lines.append("  heads: " + ", ".join(f"{k}={v}" for k, v in sorted(Counter(s.split(None, 1)[0] for s in statements).items())))

    await fs.close()
    OUT.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(main())
