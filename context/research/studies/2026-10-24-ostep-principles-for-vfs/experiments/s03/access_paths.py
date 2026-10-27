"""Study 03: the vsfs access-path tables, rebuilt for vfs. Counts only, never times.

For each verb, prints the ordered statement sequence: verb, first vfs table,
rows returned, bytes bound as parameters (what the call sends), bytes fetched
(str/bytes values in returned rows). Also: path depth 1 vs 20, body 1 KiB vs
4 MiB (read, stat, overwrite, a one-byte edit), 10,000 overwrites in one call
vs 200 one-file calls, and create-then-delete residue.
"""

from __future__ import annotations

import asyncio
import re
from collections import Counter

from sqlalchemy import event, func, select
from sqlalchemy.connectors.asyncio import AsyncAdapt_dbapi_cursor
from sqlalchemy.dialects.sqlite.aiosqlite import AsyncAdapt_aiosqlite_cursor

from vfs.authority import Authority, Principal
from vfs.base import VirtualFileSystem
from vfs.models import Entry
from vfs.storage.backends.memory import InMemoryStorage

CONTROL = ("BEGIN", "COMMIT", "PRAGMA", "SAVEPOINT", "RELEASE", "ROLLBACK")
LOG: list[dict] = []


def _size(value: object) -> int:
    if isinstance(value, str):
        return len(value.encode())
    if isinstance(value, (bytes, bytearray, memoryview)):
        return len(value)
    return 0


def _rows_bytes(rows) -> int:
    return sum(_size(v) for row in rows for v in row)


for name in ("fetchall", "fetchone", "fetchmany"):
    original = getattr(AsyncAdapt_aiosqlite_cursor, name)

    def make(orig, name=name):
        def wrapped(self, *a, **k):
            out = orig(self, *a, **k)
            if LOG:
                rows = out if name != "fetchone" else ([out] if out is not None else [])
                LOG[-1]["rows"] += len(rows)
                LOG[-1]["fetched"] += _rows_bytes(rows)
            return out
        return wrapped

    setattr(AsyncAdapt_aiosqlite_cursor, name, make(original))


def label(statement: str) -> str:
    head = statement.split(None, 1)[0].upper()
    if head in CONTROL:
        return head
    tables = re.findall(r"\bvfs_[a-z_]+", statement)
    joined = " JOIN content" if "vfs_content" in tables[1:] and head == "SELECT" and tables[0] == "vfs_entries" else ""
    return f"{head} {tables[0] if tables else '?'}{joined}"


def bound(parameters, executemany) -> tuple[int, int]:
    groups = parameters if executemany else [parameters]
    total, rows = 0, 0
    for group in groups:
        rows += 1
        values = group.values() if isinstance(group, dict) else (group or ())
        total += sum(_size(v) for v in values)
    return total, rows


async def main() -> None:
    storage = InMemoryStorage()
    fs = VirtualFileSystem(storage=storage)
    system = Authority.system()
    alice = Authority.of(Principal("alice"))
    await storage.first_touch()

    @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
    def record(conn, cursor, statement, parameters, context, executemany):
        sent, param_rows = bound(parameters, executemany)
        LOG.append({"label": label(statement), "sent": sent, "rows": 0, "fetched": 0, "param_rows": param_rows, "sql": statement})

    async def trace(title: str, coro, *, detail: bool = True) -> None:
        LOG.clear()
        result = await coro
        sql = [e for e in LOG if e["label"] not in CONTROL]
        print(f"\n## {title}: success={result.success} rows_out={len(result.observations)} "
              f"statements={len(LOG)} non_control={len(sql)} "
              f"sent={sum(e['sent'] for e in LOG):,}B fetched={sum(e['fetched'] for e in LOG):,}B")
        if detail:
            for i, e in enumerate(LOG, 1):
                print(f"  {i:2d}. {e['label']:<38} rows_back={e['rows']:<5} sent={e['sent']:>10,}B fetched={e['fetched']:>10,}B")
        else:
            c = Counter(e["label"] for e in LOG)
            print("   ", ", ".join(f"{k}={v}" for k, v in sorted(c.items())))
        if result.errors:
            print("   errors:", [x.kind for x in result.errors])

    # Fixtures (unmeasured).
    await fs.mkdir("/docs", authority=system)
    await fs.write(path="/docs/a.md", content="hello\n" * 10, authority=system)
    deep = "/" + "/".join(f"d{i}" for i in range(1, 20)) + "/f.md"
    await fs.write(path=deep, content="hello\n" * 10, parents=True, authority=system)
    await fs.grant("/", "alice", "read_write", authority=system)
    await fs.stat("/docs/a.md", authority=system)
    await fs.stat("/docs/a.md", authority=alice)

    print("# A. The five access paths, system actor, depth-2 file, 60-byte body")
    await trace("read /docs/a.md", fs.read("/docs/a.md", authority=system))
    await trace("stat /docs/a.md", fs.stat("/docs/a.md", authority=system))
    await trace("ls /docs", fs.ls("/docs", authority=system))
    await trace("write-create /docs/b.md", fs.write(path="/docs/b.md", content="x\n", authority=system))
    await trace("write-update /docs/b.md", fs.write(path="/docs/b.md", content="y\n", authority=system))
    await trace("edit /docs/b.md", fs.edit("/docs/b.md", "y", "z", authority=system))

    print("\n# B. Same paths as a named principal (rights stamps on the path)")
    await trace("alice read /docs/a.md", fs.read("/docs/a.md", authority=alice))
    await trace("alice write-update /docs/b.md", fs.write(path="/docs/b.md", content="w\n", authority=alice))

    print("\n# C. Path depth: depth 2 vs depth 20 (the vsfs walk is 2 I/Os per level)")
    await trace("stat depth-20 file", fs.stat(deep, authority=system))
    await trace("read depth-20 file", fs.read(deep, authority=system))
    await trace("write-create depth-20 sibling", fs.write(path=deep.replace("f.md", "g.md"), content="x", authority=system))

    print("\n# D. Body size: 4 MiB text body")
    big = "MARKER\n" + ("y" * 63 + "\n") * (4 * 1024 * 1024 // 64)
    await trace("write-create /docs/big.txt (4 MiB)", fs.write(path="/docs/big.txt", content=big, authority=system))
    await trace("stat /docs/big.txt", fs.stat("/docs/big.txt", authority=system))
    await trace("read /docs/big.txt", fs.read("/docs/big.txt", authority=system))
    await trace("ls /docs (big.txt is a child)", fs.ls("/docs", authority=system))
    await trace("edit one byte of /docs/big.txt", fs.edit("/docs/big.txt", "MARKER", "MARKEr", authority=system))
    big2 = "Q" + big[1:]
    await trace("write-update /docs/big.txt (one byte differs)", fs.write(path="/docs/big.txt", content=big2, authority=system))

    print("\n# E. Write buffering by the caller: 10,000 overwrites in one call vs 200 one-file calls")
    files = [Entry(path=f"/bulk/f{i:05}.md", content=f"v1 {i}\n") for i in range(10_000)]
    await fs.write(files, parents=True, authority=system)
    await trace("write 10,000 overwrites, one call", fs.write([Entry(path=f"/bulk/f{i:05}.md", content=f"v2 {i}\n") for i in range(10_000)], authority=system), detail=False)
    LOG.clear()
    total = 0
    for i in range(200):
        await fs.write(path=f"/bulk/f{i:05}.md", content=f"v3 {i}\n", authority=system)
        total += len(LOG)
        LOG.clear()
    print(f"\n## 200 one-file overwrites, 200 calls: statements={total} ({total/200:.1f} per file)")

    print("\n# F. Create then delete: what a delayed write would have avoided")
    async with storage._host.session_factory() as s:
        t = storage._host.tables
        async def counts():
            out = {}
            for name in ("entry", "content", "segments", "edges", "versions"):
                tbl = getattr(t, name)
                out[name] = (await s.execute(select(func.count()).select_from(tbl))).scalar_one()
            return out
        before = await counts()
    await trace("write-create /docs/tmp.md", fs.write(path="/docs/tmp.md", content="scratch\n", authority=system), detail=False)
    await trace("delete /docs/tmp.md", fs.delete("/docs/tmp.md", authority=system), detail=False)
    async with storage._host.session_factory() as s:
        t = storage._host.tables
        after = {}
        for name in ("entry", "content", "segments", "edges", "versions"):
            tbl = getattr(t, name)
            after[name] = (await s.execute(select(func.count()).select_from(tbl))).scalar_one()
    print("  rows left behind by create+delete:", {k: after[k] - before[k] for k in after})

    await fs.close()


if __name__ == "__main__":
    asyncio.run(main())
