"""L3 baseline: what today's ladder (none < read < read_write) answers on a road directory.

Tree (posture private at /):
    /pub/readme.md
    /team/plan.md, /team/notes.md
    /priv/deep/d.md          <- bob holds `read` here (one deep file)
    /priv/secret.md
Authored edges:
    d.md -cites-> secret.md, secret.md -cites-> readme.md, d.md -cites-> plan.md,
    secret.md -mentions-> /priv  (hidden file -> road directory: the leak probe)
Run from the vfs root:  uv run python <this file>
"""

from __future__ import annotations

import asyncio

from vfs.authority import Authority, Principal
from vfs.models import Edge, Entry
from vfs.paths import Path
from vfs.storage.backends.memory import InMemoryStorage

SYSTEM = Authority.system()
BOB = Authority.of(Principal("bob"))
NOBODY = Authority.anonymous()

FILES = ["/pub/readme.md", "/team/plan.md", "/team/notes.md", "/priv/deep/d.md", "/priv/secret.md"]
EDGES = [
    ("/priv/deep/d.md", "/priv/secret.md", "cites"),
    ("/priv/secret.md", "/pub/readme.md", "cites"),
    ("/priv/deep/d.md", "/team/plan.md", "cites"),
    ("/priv/secret.md", "/priv", "mentions"),
]


def show(label: str, result) -> None:
    print(f"\n== {label} ==  success={result.success}")
    for o in result.observations:
        fields = {k: getattr(o, k) for k in sorted(o.populated) if k not in {"path", "kind"}}
        extra = f"  {fields}" if fields else ""
        print(f"  {o.path!s:28} kind={o.kind!s:<10}{extra}")
    for e in result.errors:
        print(f"  ERROR {e.kind.value:18} path={e.path}  data={dict(e.data) if e.data else {}}")


async def main() -> None:
    storage = InMemoryStorage()
    entries = [Entry(path=Path(p), content=f"body of {p}") for p in FILES]
    assert (await storage.write(entries=entries, parents=True, authority=SYSTEM)).success
    assert (await storage.posture(path=Path("/"), posture="private", authority=SYSTEM)).success
    edges = [Edge(source=Path(s), target=Path(t), edge_type=k) for s, t, k in EDGES]
    assert (await storage.mkedge(edges=edges, authority=SYSTEM)).success
    r = await storage.grant(path=Path("/priv/deep/d.md"), principal="bob", level="read", authority=SYSTEM)
    assert r.success, r.errors

    print("#### A. the road as bob sees it (read on /priv/deep/d.md only) ####")
    show("stat /priv (road)", await storage.stat(path=Path("/priv"), authority=BOB))
    show("stat /priv/deep (road)", await storage.stat(path=Path("/priv/deep"), authority=BOB))
    show("stat /priv/secret.md (hidden sibling)", await storage.stat(path=Path("/priv/secret.md"), authority=BOB))
    show("stat /priv/nope (absent)", await storage.stat(path=Path("/priv/nope"), authority=BOB))
    show("ls /", await storage.ls(path=Path("/"), authority=BOB))
    show("ls /priv (road: trimmed)", await storage.ls(path=Path("/priv"), authority=BOB))
    show("tree /", await storage.tree(path=Path("/"), authority=BOB))
    show("glob /**", await storage.glob(patterns=("/**",), authority=BOB))
    show("read /priv/deep/d.md", await storage.read(path=Path("/priv/deep/d.md"), authority=BOB))

    print("\n#### B. edge verbs touching the road, bob at read ####")
    e_vis_to_road = [Edge(source=Path("/priv/deep/d.md"), target=Path("/priv"), edge_type="part_of")]
    show("mkedge d.md -> /priv (read-only source)", await storage.mkedge(edges=e_vis_to_road, authority=BOB))

    print("\n#### C. same, bob raised to read_write on the file, to isolate the target answer ####")
    r = await storage.grant(path=Path("/priv/deep/d.md"), principal="bob", level="read_write", authority=SYSTEM)
    assert r.success, r.errors
    show("mkedge d.md -> /priv (road target)", await storage.mkedge(edges=e_vis_to_road, authority=BOB))
    e_to_hidden = [Edge(source=Path("/priv/deep/d.md"), target=Path("/priv/secret.md"), edge_type="cites")]
    show("mkedge d.md -> /priv/secret.md (hidden target)", await storage.mkedge(edges=e_to_hidden, authority=BOB))
    e_to_absent = [Edge(source=Path("/priv/deep/d.md"), target=Path("/priv/nope.md"), edge_type="cites")]
    show("mkedge d.md -> /priv/nope.md (absent target)", await storage.mkedge(edges=e_to_absent, authority=BOB))
    show("rmedge d.md -> secret.md (system-authored, bob writes source)", await storage.rmedge(edges=e_to_hidden, authority=BOB))
    show("rmedge d.md -> /priv/nope.md (no such edge)", await storage.rmedge(edges=e_to_absent, authority=BOB))
    show("rmedge d.md -> secret.md again (now gone)", await storage.rmedge(edges=e_to_hidden, authority=BOB))
    show("mkdir /priv/new (under the road)", await storage.mkdir(path=Path("/priv/new"), authority=BOB))

    print("\n#### D. the stored edge rows as the system sees them ####")
    show("stat /priv/secret.md (system)", await storage.stat(path=Path("/priv/secret.md"), authority=SYSTEM))

    print("\n#### E. anonymous under posture private ####")
    show("ls / (anonymous)", await storage.ls(path=Path("/"), authority=NOBODY))

    print("\n#### F. 'alter only your own rows' already rides on the owner floor ####")
    assert (await storage.mkdir(path=Path("/inbox"), authority=SYSTEM)).success
    assert (await storage.write(entries=[Entry(path=Path("/inbox/sys.md"), content="system's")], authority=SYSTEM)).success
    assert (await storage.posture(path=Path("/inbox"), posture="open", authority=SYSTEM)).success
    show("bob writes /inbox/bob.md under open", await storage.write(entries=[Entry(path=Path("/inbox/bob.md"), content="bob's")], authority=BOB))
    assert (await storage.posture(path=Path("/inbox"), posture="shared", authority=SYSTEM)).success
    show("stat /inbox/bob.md (owner_id)", await storage.stat(path=Path("/inbox/bob.md"), columns=frozenset({"owner_id"}), authority=BOB))
    show("bob overwrites own row under shared (floor)", await storage.write(entries=[Entry(path=Path("/inbox/bob.md"), content="bob's v2")], authority=BOB))
    show("bob overwrites system's row under shared", await storage.write(entries=[Entry(path=Path("/inbox/sys.md"), content="x")], authority=BOB))
    show("bob creates /inbox/new.md under shared", await storage.write(entries=[Entry(path=Path("/inbox/new.md"), content="x")], authority=BOB))
    show("bob deletes own row under shared", await storage.delete(path=Path("/inbox/bob.md"), authority=BOB))
    show("bob restores own row under shared", await storage.restore(path=Path("/inbox/bob.md"), authority=BOB))
    show("bob mkedge own -> sys.md under shared", await storage.mkedge(edges=[Edge(source=Path("/inbox/bob.md"), target=Path("/inbox/sys.md"), edge_type="replies_to")], authority=BOB))
    show("bob mkedge sys.md -> own under shared", await storage.mkedge(edges=[Edge(source=Path("/inbox/sys.md"), target=Path("/inbox/bob.md"), edge_type="replies_to")], authority=BOB))

    print("\n#### G. anonymous under posture shared / open ####")
    show("ls /inbox (anonymous, shared)", await storage.ls(path=Path("/inbox"), authority=NOBODY))
    show("anonymous writes /inbox/anon.md (shared)", await storage.write(entries=[Entry(path=Path("/inbox/anon.md"), content="x")], authority=NOBODY))
    assert (await storage.posture(path=Path("/inbox"), posture="open", authority=SYSTEM)).success
    show("anonymous writes /inbox/anon.md (open)", await storage.write(entries=[Entry(path=Path("/inbox/anon.md"), content="x")], authority=NOBODY))
    show("stat /inbox/anon.md owner (system)", await storage.stat(path=Path("/inbox/anon.md"), columns=frozenset({"owner_id"}), authority=SYSTEM))
    await storage.close()


asyncio.run(main())
