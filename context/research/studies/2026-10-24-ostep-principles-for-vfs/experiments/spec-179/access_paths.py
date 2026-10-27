"""Spec 179 probe: the access path per kernel verb at HEAD, three authorities, counts only.

Statements come from before_cursor_execute (label: verb + first vfs_ table). Rows and fetched
payload bytes come from wrapping CursorResult's fetch implementations, which is the
driver-independent layer every dialect's rows pass through. Sent bytes are the str/bytes
parameter values. Nothing is timed.
"""

from __future__ import annotations

import asyncio
import re
import tempfile

from sqlalchemy import event
from sqlalchemy.engine.cursor import CursorResult

from vfs.authority import Authority, Principal
from vfs.models import Edge, Entry
from vfs.paths import Path
from vfs.storage import ResolvedPair
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database import rights as rights_mod
from vfs.storage.replace import EditOperation

CONTROL = ("BEGIN", "COMMIT", "PRAGMA", "SAVEPOINT", "RELEASE", "ROLLBACK")
LOG: list[dict] = []


def size(v: object) -> int:
    if isinstance(v, str):
        return len(v.encode())
    if isinstance(v, (bytes, bytearray, memoryview)):
        return len(v)
    return 0


def _wrap(name: str) -> None:
    orig = getattr(CursorResult, name)

    def wrapped(self, *a, **k):
        out = orig(self, *a, **k)
        if LOG:
            rows = [out] if name == "_fetchone_impl" else list(out or [])
            if name == "_fetchone_impl" and out is None:
                rows = []
            LOG[-1]["rows"] += len(rows)
            LOG[-1]["fetched"] += sum(size(v) for r in rows for v in r)
            if name in ("_fetchall_impl", "_fetchmany_impl"):
                return rows
        return out

    setattr(CursorResult, name, wrapped)


for _n in ("_fetchone_impl", "_fetchall_impl", "_fetchmany_impl"):
    _wrap(_n)

_orig_iter = CursorResult._fetchiter_impl


def _iter(self):
    for row in _orig_iter(self):
        if LOG:
            LOG[-1]["rows"] += 1
            LOG[-1]["fetched"] += sum(size(v) for v in row)
        yield row


CursorResult._fetchiter_impl = _iter


def label(statement: str) -> str:
    head = statement.split(None, 1)[0].upper()
    if head in CONTROL:
        return head
    tables = re.findall(r"\bvfs_[a-z_]+", statement)
    return f"{head} {tables[0] if tables else '?'}"


def sent(parameters, many) -> int:
    groups = parameters if many else [parameters]
    total = 0
    for g in groups:
        vals = g.values() if isinstance(g, dict) else (g or ())
        total += sum(size(v) for v in vals)
    return total


async def main() -> None:
    tmp = tempfile.mkdtemp()
    s = DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp}/a.sqlite")
    await s.first_touch()

    @event.listens_for(s._host.engine.sync_engine, "before_cursor_execute")
    def rec(conn, cursor, statement, parameters, context, many):
        LOG.append({"label": label(statement), "sent": sent(parameters, many), "rows": 0, "fetched": 0})

    system, alice, anon = Authority.system(), Authority.of(Principal("alice")), Authority.anonymous()
    deep = "/" + "/".join(f"d{i}" for i in range(1, 20)) + "/f.md"
    assert (await s.write(entries=[Entry(path=Path("/docs/a.md"), content="hello\n" * 10)], parents=True)).success
    assert (await s.write(entries=[Entry(path=Path("/docs/x.md"), content="x\n")], parents=True)).success
    assert (await s.write(entries=[Entry(path=Path(deep), content="hello\n" * 10)], parents=True)).success
    assert (await s.grant(path=Path("/"), principal="alice", level="read_write")).success

    async def trace(title, coro, detail=False):
        LOG.clear()
        r = await coro
        sql = [e for e in LOG if e["label"] not in CONTROL]
        print(
            f"{title:<44} ok={str(r.success):<5} stmts={len(sql):>2} rows={sum(e['rows'] for e in sql):>3} "
            f"sent={sum(e['sent'] for e in sql):>5}B fetched={sum(e['fetched'] for e in sql):>5}B"
        )
        if detail:
            for i, e in enumerate(sql, 1):
                print(f"     {i:2d}. {e['label']:<36} rows={e['rows']:<4} sent={e['sent']:>5}B fetched={e['fetched']:>5}B")
        return r

    n = 0
    for who_name, who in (("system", system), ("alice", alice), ("anon", anon)):
        print(f"\n# authority = {who_name}")
        # warm the rights cache once
        await s.stat(path=Path("/docs/a.md"), authority=who)
        await trace(f"stat /docs/a.md", s.stat(path=Path("/docs/a.md"), authority=who), detail=True)
        await trace(f"stat depth 20", s.stat(path=Path(deep), authority=who))
        await trace(f"read /docs/a.md", s.read(path=Path("/docs/a.md"), authority=who), detail=True)
        await trace(f"ls /docs", s.ls(path=Path("/docs"), authority=who))
        await trace(f"tree /docs", s.tree(path=Path("/docs"), authority=who))
        await trace(f"glob **/*.md", s.glob(patterns=("/**/*.md",), authority=who))
        await trace(f"grep hello (scan side)", s.grep(pattern="hello", authority=who))
        n += 1
        await trace(f"write create /docs/c{n}.md", s.write(entries=[Entry(path=Path(f"/docs/c{n}.md"), content="c")], authority=who), detail=True)
        await trace(f"write create depth 20", s.write(entries=[Entry(path=Path(deep.replace("f.md", f"g{n}.md")), content="g")], authority=who))
        await trace(f"write overwrite /docs/c{n}.md", s.write(entries=[Entry(path=Path(f"/docs/c{n}.md"), content="cc")], authority=who), detail=True)
        await trace(f"edit /docs/c{n}.md", s.edit(path=Path(f"/docs/c{n}.md"), edits=[EditOperation(old="cc", new="cd")], authority=who), detail=True)
        await trace(f"mkdir /m{n}", s.mkdir(path=Path(f"/m{n}"), authority=who))
        await trace(f"move /m{n} -> /mv{n}", s.move(operations=[ResolvedPair(Path(f"/m{n}"), Path(f"/mv{n}"))], authority=who), detail=True)
        await trace(f"copy /docs/c{n}.md -> /cp{n}.md", s.copy(operations=[ResolvedPair(Path(f"/docs/c{n}.md"), Path(f"/cp{n}.md"))], authority=who))
        await trace(f"delete /cp{n}.md", s.delete(path=Path(f"/cp{n}.md"), authority=who), detail=True)
        await trace(f"restore /cp{n}.md", s.restore(path=Path(f"/cp{n}.md"), authority=who))
        await trace(f"mkedge", s.mkedge(edges=[Edge(source=Path(f"/docs/c{n}.md"), target=Path("/docs/a.md"), edge_type="refs")], authority=who))
        await trace(f"rmedge", s.rmedge(edges=[Edge(source=Path(f"/docs/c{n}.md"), target=Path("/docs/a.md"), edge_type="refs")], authority=who))
        await trace(f"grants /docs", s.grants(path=Path("/docs"), authority=who))

    print("\n# rights cache, alice")
    s._rights = rights_mod.RightsCache()
    await trace("read cold cache", s.read(path=Path("/docs/a.md"), authority=alice), detail=True)
    await trace("read warm cache", s.read(path=Path("/docs/a.md"), authority=alice), detail=True)
    print("\n# body size dimension, system")
    big = "x" * (4 * 1024 * 1024)
    await trace("write create 4 MiB", s.write(entries=[Entry(path=Path("/big.txt"), content=big)]))
    await trace("read 4 MiB", s.read(path=Path("/big.txt")))
    await trace("stat 4 MiB", s.stat(path=Path("/big.txt")))
    await trace("overwrite 4 MiB (1 byte differs)", s.write(entries=[Entry(path=Path("/big.txt"), content=big[:-1] + "y")]))
    await trace("edit 4 MiB (1 byte)", s.edit(path=Path("/big.txt"), edits=[EditOperation(old="y", new="z")]))
    print("\n# batch dimension, system")
    await s.mkdir(path=Path("/etl"))
    await trace("write create 10,000", s.write(entries=[Entry(path=Path(f"/etl/f{i:05d}"), content="r") for i in range(10_000)]))
    await trace("write overwrite 10,000", s.write(entries=[Entry(path=Path(f"/etl/f{i:05d}"), content="s") for i in range(10_000)]))
    await trace("ls 10,000", s.ls(path=Path("/etl")))
    await s.close()


asyncio.run(main())
