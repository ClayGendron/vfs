"""Decision 5's plans under a view, the trash side and the meta subtree, on a writable copy.

Build: about 2,100 Linux files copied by raw SQL from the read-only sandbox into a fresh SQLite store, laid out as
  /pub/**     everyone reads (posture read; root posture none)
  /team/**    group:eng reads; alice is a member
  /alice/**   written by alice (owner floor)
  /secret/**  nobody but the system; bob holds read on /secret/security/selinux
then rebuilt, then: three subtrees deleted (tombstones), 40 files written and 20 overwritten after the rebuild (rows
awaiting the index), and files attempted under /.vfs.

Each grep runs five ways inside the storage, by replacing module functions in this process only:
  today       the pinned code
  in hand     the range ids are the candidates, fetched without the encoded term, gates and view judged, no scan side
  allow-range the range ids are the allow-list, ladder and scan side as today
  ranged      no allow-list, the range rides the candidate fetch as pushdown
Every body the plan fetches is checked against a layout oracle of what the caller may read.

    PYTHONPATH=<pinned src> uv run python r3_04_view_trash_meta.py linux.db out.db
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
from collections import Counter

from sqlalchemy import and_, or_, select

import vfs.storage.backends.database.backend as backend_module
import vfs.storage.backends.database.grep as g
from vfs import AsyncVirtualFileSystem, Authority, DatabaseStorage, Entry, Principal
from vfs.storage.backends.database.dialects import chunked
from vfs.storage.backends.database.membership import membership
from vfs.storage.backends.database.reads import kind_membership
from vfs.storage.backends.database.scope import FETCH_RIDE, ScanNominees

SRC, DB = sys.argv[1], sys.argv[2]
SYSTEM, ANON = Authority.system(), Authority.anonymous()
ALICE, BOB = Authority.of(Principal("alice")), Authority.of(Principal("bob"))
CALLERS = {"system": SYSTEM, "alice": ALICE, "bob": BOB, "anon": ANON}
LAYOUT = {"/kernel": "/pub/kernel", "/lib": "/team/lib", "/mm": "/alice/mm", "/security": "/secret/security"}


def readable(caller: str, path: str) -> bool:
    if caller == "system":
        return True
    under = lambda root: path == root or path.startswith(root + "/")  # noqa: E731
    if under("/pub"):
        return True
    if caller == "alice":
        return under("/team") or under("/alice")
    if caller == "bob":
        return under("/secret/security/selinux")
    return False


# ---------------------------------------------------------------------------
# Plan prototypes
# ---------------------------------------------------------------------------

MODE = ["today"]
ROOTS: list[str] = []
FETCHED: list = []
RAW: list = []
real_rows, real_push, real_entries, real_allow, real_defers = (
    backend_module.grep_rows,
    g.pushdown_terms,
    g._entries_for_docs,
    g.allow_list_ids,
    g._ladder_defers,
)
real_scan, real_content = g.entries_for_scan, g.content_for_entries


def maximal(roots):
    return [r for r in sorted(set(roots)) if not any(r.startswith(o + "/") for o in roots if o != r)]


def range_ids():
    ids = []
    for r in maximal(ROOTS):
        ids += [i for (i,) in RAW[0].execute("SELECT id FROM vfs_entries WHERE path > ? AND path < ?", (r + "/", r + "0"))]
        ids += [i for (i,) in RAW[0].execute("SELECT id FROM vfs_entries WHERE path = ?", (r,))]
    return sorted(set(ids))


async def grep_rows(*a, **k):
    scope = k.get("scope")
    ROOTS[:] = [] if scope is None else [str(r) for r in (scope.trashed or scope.live)]
    return await real_rows(*a, **k)


async def allow(*a, **k):
    if MODE[0] == "today" or not ROOTS:
        return await real_allow(*a, **k)
    return None if MODE[0] == "ranged" else range_ids()


def push(entry, *a, **k):
    pd = real_push(entry, *a, **k)
    if MODE[0] != "ranged" or not ROOTS:
        return pd
    rng = or_(*(or_(entry.c.path == r, and_(entry.c.path > r + "/", entry.c.path < r + "0")) for r in maximal(ROOTS)))
    return g.Pushdown((*pd.terms, rng), pd.binds + 3 * len(ROOTS))


async def entries(session, tables, profile, mb, doc_ids, fetched, pushdown):
    if MODE[0] != "inhand" or not ROOTS:
        return await real_entries(session, tables, profile, mb, doc_ids, fetched, pushdown)
    entry = tables.entry
    columns = [entry.c.entry_id, *(entry.c[f] for f in sorted((fetched | FETCH_RIDE) - {"content"}))]
    kinds = kind_membership(entry)
    rows = []
    for chunk in chunked(doc_ids, 1000):
        stmt = select(*columns).where(membership(entry.c.id, chunk, profile), kinds.predicate, *pushdown.terms)
        rows.extend((await session.execute(stmt)).mappings())
    return rows


async def scan(*a, **k):
    if MODE[0] == "inhand" and ROOTS and not k["everything"]:
        return ScanNominees([], False)
    return await real_scan(*a, **k)


async def content(session, tables, profile, mb, ids):
    out = await real_content(session, tables, profile, mb, ids)
    for chunk in chunked(list(ids), 500):
        stmt = select(tables.entry.c.path).where(membership(tables.entry.c.entry_id, chunk, profile))
        FETCHED.extend(p for (p,) in await session.execute(stmt))
    return out


backend_module.grep_rows, g.allow_list_ids, g.pushdown_terms, g._entries_for_docs = grep_rows, allow, push, entries
g._ladder_defers = lambda *a: (MODE[0] == "inhand" and bool(ROOTS)) or (MODE[0] == "today" and real_defers(*a))
g.entries_for_scan, g.content_for_entries = scan, content


def shape(r):
    return tuple((str(o.path), tuple((m.start, m.end, m.match) for m in (o.matches or ()))) for o in r.observations)


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


async def build(fs, storage):
    src = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True)
    batch, late = [], []
    for old, new in LAYOUT.items():
        rows = src.execute(
            "SELECT e.path, c.content FROM vfs_entries e JOIN vfs_content c ON c.entry_id = e.entry_id "
            "WHERE e.kind = 'file' AND e.deleted_at IS NULL AND e.path > ? AND e.path < ? AND e.size_bytes < 400000",
            (old + "/", old + "0"),
        ).fetchall()
        for path, body in rows:
            entry = Entry(path=new + path[len(old) :], content=body)
            (late if new == "/alice/mm" else batch).append(entry)
    ipc = src.execute(
        "SELECT e.path, c.content FROM vfs_entries e JOIN vfs_content c ON c.entry_id = e.entry_id "
        "WHERE e.kind = 'file' AND e.path > '/ipc/' AND e.path < '/ipc0'"
    ).fetchall()
    print("files", len(batch) + len(late))
    r = await fs.write(entries=batch, parents=True, authority=SYSTEM)
    print("system write", r.success, [e.message[:80] for e in r.errors][:2])
    r = await fs.write(entries=late, parents=True, authority=ALICE)
    print("alice write", r.success, [e.message[:80] for e in r.errors][:2])
    meta = [Entry(path="/.vfs/ipc" + p[len("/ipc") :], content=b) for p, b in ipc]
    r = await fs.write(entries=meta, parents=True, authority=SYSTEM)
    print("meta write under /.vfs", r.success, [e.message[:100] for e in r.errors][:1])
    for call in (
        fs.set_posture("/", "none", authority=SYSTEM),
        fs.set_posture("/pub", "read", authority=SYSTEM),
        fs.grant("/team", "group:eng", "read", authority=SYSTEM),
        fs.add_member("group:eng", "alice", authority=SYSTEM),
        fs.grant("/secret/security/selinux", "bob", "read", authority=SYSTEM),
    ):
        r = await call
        print("rights", r.success, [e.message[:80] for e in r.errors][:1])
    rb = await storage.rebuild()
    print("rebuild", rb.success)
    for path in ("/pub/kernel/sched", "/team/lib/zlib_inflate", "/secret/security/selinux/ss", "/alice/mm/kasan"):
        r = await fs.delete(path=path, authority=SYSTEM)
        print("delete", path, r.success, [e.message[:80] for e in r.errors][:1])
    kern = src.execute(
        "SELECT e.path, c.content FROM vfs_entries e JOIN vfs_content c ON c.entry_id = e.entry_id "
        "WHERE e.kind='file' AND e.path > '/kernel/locking/' AND e.path < '/kernel/locking0' LIMIT 40"
    ).fetchall()
    fresh = [Entry(path="/pub/late/" + p.rsplit("/", 1)[1], content=b) for p, b in kern]
    fresh += [Entry(path="/secret/late/" + p.rsplit("/", 1)[1], content=b) for p, b in kern[:20]]
    over = [Entry(path=e.path, content=e.content + "\n/* kmalloc TODO rewritten */\n") for e in batch[::100]]
    r = await fs.write(entries=fresh + over, parents=True, authority=SYSTEM)
    print("post-rebuild writes", r.success, len(fresh), len(over))


async def main() -> None:
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(DB + suffix):
            os.remove(DB + suffix)
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{DB}")
    fs = AsyncVirtualFileSystem(storage=storage)
    try:
        await build(fs, storage)
        RAW.append(sqlite3.connect(f"file:{DB}?mode=ro", uri=True))
        print(
            "rows by state",
            RAW[0].execute(
                "SELECT kind, encoded, deleted_at IS NOT NULL, count(*) FROM vfs_entries GROUP BY 1, 2, 3"
            ).fetchall(),
        )
        print("rows under /.vfs", RAW[0].execute("SELECT count(*) FROM vfs_entries WHERE path > '/.vfs/' AND path < '/.vfs0'").fetchone())
        # Oracle check: the layout oracle against read, on every live file.
        files = [p for (p,) in RAW[0].execute("SELECT path FROM vfs_entries WHERE kind='file' AND deleted_at IS NULL")]
        bad = Counter()
        for name, auth in CALLERS.items():
            for p in files[::7]:
                ok = (await fs.read(path=p, authority=auth)).success
                bad[name] += ok != readable(name, p)
        print("oracle disagreements with read, sampled 1 in 7:", dict(bad))
        scopes = [
            ("/pub",), ("/team",), ("/alice",), ("/secret",), ("/pub", "/secret"), ("/team/lib/string.c",),
            ("/secret/security/selinux",), ("/pub/late",), ("/secret/late",), ("/.vfs/ipc",),
            ("/.vfs/trash/pub",), ("/.vfs/trash/team", "/.vfs/trash/secret"), ("/.vfs/trash/alice/mm",),
        ]  # fmt: skip
        patterns = [
            ("static int", {}), ("kmalloc", {}), ("EXPORT_SYMBOL", {}), ("todo", {"case_mode": "insensitive"}),
            ("return 0;", {}), ("^#include", {}), ("kmalloc", {"invert_match": True, "output_mode": "files"}),
            ("[a-z]", {"allow_scan": True, "output_mode": "files"}),
        ]  # fmt: skip
        disagreements, leaks, calls, nonempty = [], [], 0, 0
        for cname, auth in CALLERS.items():
            for scope in scopes:
                for pattern, kw in patterns:
                    kw = {"output_mode": "lines", **kw}
                    shapes = {}
                    for mode in ("today", "inhand", "allowrange", "ranged"):
                        MODE[0] = mode
                        FETCHED.clear()
                        r = await fs.grep(pattern, paths=scope, authority=auth, **kw)
                        calls += 1
                        shapes[mode] = (shape(r), tuple(e.message[:40] for e in r.errors))
                        for p in FETCHED:
                            if not readable(cname, p):
                                leaks.append((cname, scope, pattern, mode, p))
                    nonempty += bool(shapes["today"][0])
                    if len({v for v in shapes.values()}) > 1:
                        disagreements.append((cname, scope, pattern, {m: (len(v[0]), v[1]) for m, v in shapes.items()}))
        print(f"grep calls {calls}; caller x scope x pattern cells {calls // 4}, non-empty under today {nonempty}")
        print("cells where plans disagree:", len(disagreements))
        for d in disagreements[:12]:
            print("  ", d)
        print("bodies fetched that the caller may not read:", len(leaks))
        for x in leaks[:8]:
            print("  ", x)
    finally:
        await fs.close()


if __name__ == "__main__":
    asyncio.run(main())
