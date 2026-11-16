"""Probe 08: which tables a rebuild and a refresh read, and three small checks the earlier probes left."""

from __future__ import annotations

import asyncio
import re
from collections import Counter

from sqlalchemy import select, update

from lint_common import SYSTEM, StatementCounter, attempt, fetch, make, run_sql
from vfs.models import Entry

TABLE = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE)\s+(vfs_[a-z_]+)")


def by_table(samples: list[str]) -> dict[str, int]:
    seen: Counter[str] = Counter()
    for sample in samples:
        verb = sample.split(None, 1)[0].upper()
        for table in sorted(set(TABLE.findall(sample))) or ["(none)"]:
            seen[f"{verb} {table}"] += 1
    return dict(sorted(seen.items()))


async def main() -> None:
    fs, storage = make()
    batch = [Entry(path=f"/data/d{i // 100:02d}/f{i:04d}.md", content=f"# file {i}\nbody of file number {i}\n") for i in range(2_000)]
    assert not (await fs.write(batch, parents=True, authority=SYSTEM)).errors

    print("== R1. The first rebuild over 2,000 new files: statements by verb and table")
    with StatementCounter(storage) as counter:
        await storage.rebuild()
    print(f"    statements={counter.statements}")
    for key, count in by_table(counter.samples).items():
        print(f"      {count:5d}  {key}")

    print("== R2. A second rebuild with nothing changed")
    with StatementCounter(storage) as counter:
        await storage.rebuild()
    print(f"    statements={counter.statements}")
    for key, count in by_table(counter.samples).items():
        print(f"      {count:5d}  {key}")
    for sample in counter.samples:
        if "vfs_entries" in sample and sample.upper().startswith("SELECT"):
            print(f"      entries read: {sample[:150]}")

    print("== R3. A rebuild after one file changed")
    await fs.write(path="/data/d00/f0000.md", content="# file 0\nchanged\n", authority=SYSTEM)
    with StatementCounter(storage) as counter:
        await storage.rebuild()
    print(f"    statements={counter.statements}")
    for key, count in by_table(counter.samples).items():
        print(f"      {count:5d}  {key}")
    for sample in counter.samples:
        if ("vfs_content" in sample or "vfs_chunks" in sample) and sample.upper().startswith("SELECT"):
            print(f"      body or chunk read: {sample[:160]}")

    print("== R4. A refresh after one file changed")
    await fs.write(path="/data/d00/f0001.md", content="# file 1\nchanged\n", authority=SYSTEM)
    with StatementCounter(storage) as counter:
        await storage.refresh()
    print(f"    statements={counter.statements}")
    for key, count in by_table(counter.samples).items():
        print(f"      {count:5d}  {key}")
    await fs.close()

    print("== R5. traverse on a clean store, for comparison with the store whose fs edge was deleted")
    fs, storage = make()
    await fs.write(path="/a/b/c.txt", content="x\n", parents=True, authority=SYSTEM)
    await attempt("traverse inbound /a/b/c.txt", fs.traverse("inbound", "/a/b/c.txt", authority=SYSTEM))
    await attempt("traverse outbound /a/b", fs.traverse("outbound", "/a/b", authority=SYSTEM))
    await attempt("traverse outbound /a/b edge_types=fs", fs.traverse("outbound", "/a/b", edge_types=("fs",), authority=SYSTEM))
    await fs.close()

    print("== R6. An entry's version reset below its version rows, then two overwrites")
    fs, storage = make()
    for body in ("one\n", "two\n", "three\n"):
        await fs.write(path="/v.txt", content=body, authority=SYSTEM)
    t = storage._host.tables
    await run_sql(storage, update(t.entry).where(t.entry.c.path == "/v.txt").values(version=1))
    await attempt("overwrite 1", fs.write(path="/v.txt", content="four\n", authority=SYSTEM))
    await attempt("overwrite 2", fs.write(path="/v.txt", content="five\n", authority=SYSTEM))
    await attempt("read", fs.read("/v.txt", authority=SYSTEM))
    print("    entry.version:", await fetch(storage, select(t.entry.c.version).where(t.entry.c.path == "/v.txt")))
    print("    version rows:", await fetch(storage, select(t.versions.c.version_number, t.versions.c.content).order_by(t.versions.c.version_number)))
    await fs.close()


asyncio.run(main())
