"""Spec 179 probe: crash at every mutating statement of each whole-batch verb, SQLite file, HEAD.

For each scenario: seed a fresh file, snapshot every table of VFSTables, run the verb with a
before_cursor_execute hook that raises the dialect's own DBAPI OperationalError at the Nth
INSERT/UPDATE/DELETE, close, reopen with a fresh DatabaseStorage, snapshot again, compare.
Counts only. Also records how the injected failure surfaced (Result kind or raw raise).
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from collections.abc import Awaitable, Callable

from sqlalchemy import event, select

from vfs.authority import Authority, Principal
from vfs.models import Edge, Entry
from vfs.paths import Path
from vfs.storage import ResolvedPair
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.replace import EditOperation

MUT = ("INSERT", "UPDATE", "DELETE")
ALICE = Authority.of(Principal("alice"))


async def snapshot(s: DatabaseStorage) -> dict[str, list[tuple]]:
    t = s._host.tables
    out: dict[str, list[tuple]] = {}
    async with s._host.engine.connect() as c:
        for name in t._fields:
            if name == "metadata":
                continue
            tab = getattr(t, name)
            rows = (await c.execute(select(tab))).all()
            out[name] = sorted((tuple(repr(v) for v in r) for r in rows))
    return out


async def seed_basic(s: DatabaseStorage) -> None:
    assert (await s.write(entries=[Entry(path=Path("/d/a.txt"), content="old a")], parents=True)).success
    assert (await s.write(entries=[Entry(path=Path("/d/x.txt"), content="x body")], parents=True)).success
    assert (await s.mkdir(path=Path("/t"))).success
    assert (await s.write(entries=[Entry(path=Path("/t/gone.txt"), content="gone")])).success
    assert (await s.delete(path=Path("/t/gone.txt"))).success
    assert (await s.mkedge(edges=[Edge(source=Path("/d/a.txt"), target=Path("/d/x.txt"), edge_type="refs")])).success
    assert (await s.grant(path=Path("/"), principal="alice", level="read_write")).success


Verb = Callable[[DatabaseStorage], Awaitable[object]]

SCENARIOS: dict[str, Verb] = {
    "write batch (overwrite, create, create+parent)": lambda s: s.write(
        entries=[
            Entry(path=Path("/d/a.txt"), content="new a"),
            Entry(path=Path("/d/b.txt"), content="new b"),
            Entry(path=Path("/e/c.txt"), content="new c"),
        ],
        parents=True,
    ),
    "write batch as alice": lambda s: s.write(
        entries=[Entry(path=Path("/d/a.txt"), content="alice a"), Entry(path=Path("/d/n.txt"), content="n")],
        authority=ALICE,
    ),
    "edit": lambda s: s.edit(path=Path("/d/a.txt"), edits=[EditOperation(old="old", new="OLD")]),
    "mkdir parents": lambda s: s.mkdir(path=Path("/m/n/o"), parents=True),
    "move": lambda s: s.move(operations=[ResolvedPair(Path("/d"), Path("/d2"))]),
    "copy": lambda s: s.copy(operations=[ResolvedPair(Path("/d"), Path("/d3"))]),
    "delete cascade": lambda s: s.delete(path=Path("/d")),
    "restore": lambda s: s.restore(path=Path("/t/gone.txt")),
    "mkedge": lambda s: s.mkedge(edges=[Edge(source=Path("/d/x.txt"), target=Path("/d/a.txt"), edge_type="refs")]),
    "rmedge": lambda s: s.rmedge(edges=[Edge(source=Path("/d/a.txt"), target=Path("/d/x.txt"), edge_type="refs")]),
    "grant": lambda s: s.grant(path=Path("/d"), principal="bob", level="read"),
}


async def run(verb: Verb, k: int, tmp: str, tag: str) -> tuple[object, dict, dict, list[str]]:
    url = f"sqlite+aiosqlite:///{tmp}/{tag}-{k}.sqlite"
    s = DatabaseStorage(url=url)
    await seed_basic(s)
    before = await snapshot(s)
    state = {"i": 0, "fired": False, "stmts": []}
    dbapi = s._host.engine.sync_engine.dialect.loaded_dbapi

    def hook(conn, cursor, statement, params, context, many):
        head = statement.lstrip().split(None, 1)[0].upper()
        if head in MUT:
            state["i"] += 1
            state["stmts"].append(" ".join(statement.split()[:3]))
            if state["i"] == k and not state["fired"]:
                state["fired"] = True
                raise dbapi.OperationalError("disk I/O error (injected)")

    event.listen(s._host.engine.sync_engine, "before_cursor_execute", hook)
    try:
        r: object = await verb(s)
    except Exception as exc:  # noqa: BLE001
        r = exc
    event.remove(s._host.engine.sync_engine, "before_cursor_execute", hook)
    await s.close()
    s2 = DatabaseStorage(url=url)
    await s2.first_touch()
    after = await snapshot(s2)
    await s2.close()
    return r, before, after, state["stmts"]


def outcome(r: object) -> str:
    if isinstance(r, Exception):
        return f"RAISED {type(r).__name__}"
    errs = getattr(r, "errors", [])
    return f"success={r.success} kinds={sorted({str(e.kind) for e in errs})} retryable={[e.retryable for e in errs]}"


async def main() -> None:
    tmp = tempfile.mkdtemp()
    for tag_i, (name, verb) in enumerate(SCENARIOS.items()):
        tag = f"s{tag_i}"
        r, before, ref, stmts = await run(verb, 10**9, tmp, tag)
        assert not isinstance(r, Exception) and r.success, (name, r)
        changed = sorted(t for t in before if before[t] != ref[t])
        print(f"\n## {name}: {len(stmts)} mutating statements; tables changed: {changed}")
        for i, st in enumerate(stmts, 1):
            print(f"   {i:2d} {st}")
        verdict = {"all-old": 0, "all-new": 0, "TORN": 0}
        outcomes = set()
        for k in range(1, len(stmts) + 1):
            r, before, after, _ = await run(verb, k, tmp, tag)
            state = "all-old" if after == before else "all-new" if after == ref else "TORN"
            verdict[state] += 1
            outcomes.add(outcome(r))
        print(f"   verdicts: {verdict}; outcomes: {sorted(outcomes)}")
    sys.stdout.flush()


asyncio.run(main())
