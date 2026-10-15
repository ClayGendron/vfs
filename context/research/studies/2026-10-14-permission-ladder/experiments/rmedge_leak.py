"""Review 165, check 1: the rmedge leak and the three answer shapes a fix must reconcile.

bob holds read_write on /priv/deep/d.md only; posture private at /.
System-authored edge d.md -cites-> /priv/secret.md (hidden to bob).
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


def show(label: str, result) -> None:
    print(f"\n== {label} ==  success={result.success}")
    for o in result.observations:
        print(f"  OBS  path={o.path} target={o.edge_target} type={o.edge_type} status={o.status}")
    for e in result.errors:
        data = dict(e.data) if e.data else {}
        print(f"  ERR  kind={e.kind.value} severity={e.severity.value} path={e.path} message={e.message!r} data={data}")


async def main() -> None:
    storage = InMemoryStorage()
    files = ["/priv/deep/d.md", "/priv/secret.md", "/pub/readme.md"]
    assert (await storage.write(entries=[Entry(path=Path(p), content=p) for p in files], parents=True, authority=SYSTEM)).success
    assert (await storage.posture(path=Path("/"), posture="private", authority=SYSTEM)).success
    edges = [Edge(source=Path("/priv/deep/d.md"), target=Path("/priv/secret.md"), edge_type="cites")]
    assert (await storage.mkedge(edges=edges, authority=SYSTEM)).success
    r = await storage.grant(path=Path("/priv/deep/d.md"), principal="bob", level="read_write", authority=SYSTEM)
    assert r.success, r.errors

    show("stat /priv/secret.md as bob (hidden)", await storage.stat(path=Path("/priv/secret.md"), authority=BOB))
    show("rmedge d.md -> /priv/nope.md as bob (ABSENT target)", await storage.rmedge(
        edges=[Edge(source=Path("/priv/deep/d.md"), target=Path("/priv/nope.md"), edge_type="cites")], authority=BOB))
    show("rmedge d.md -> /priv/secret.md as bob (HIDDEN target, edge exists)", await storage.rmedge(edges=edges, authority=BOB))
    show("rmedge d.md -> /priv/secret.md as bob again", await storage.rmedge(edges=edges, authority=BOB))
    print("\n-- the gate's own miss shape, for comparison: mkedge to the hidden and to the absent target --")
    show("mkedge d.md -> /priv/secret.md as bob (gate 'read' leg on a hidden target)", await storage.mkedge(
        edges=[Edge(source=Path("/priv/deep/d.md"), target=Path("/priv/secret.md"), edge_type="x")], authority=BOB))
    show("mkedge d.md -> /priv/nope.md as bob (gate 'read' leg on an absent target)", await storage.mkedge(
        edges=[Edge(source=Path("/priv/deep/d.md"), target=Path("/priv/nope.md"), edge_type="x")], authority=BOB))
    print("\n-- a batch: one absent target beside one good edge --")
    assert (await storage.mkedge(edges=[Edge(source=Path("/priv/deep/d.md"), target=Path("/pub/readme.md"), edge_type="cites")], authority=SYSTEM)).success
    assert (await storage.grant(path=Path("/pub"), principal="bob", level="read", authority=SYSTEM)).success
    show("rmedge batch [d.md->/pub/readme.md (exists), d.md->/priv/nope.md (absent)] as bob", await storage.rmedge(edges=[
        Edge(source=Path("/priv/deep/d.md"), target=Path("/pub/readme.md"), edge_type="cites"),
        Edge(source=Path("/priv/deep/d.md"), target=Path("/priv/nope.md"), edge_type="cites"),
    ], authority=BOB))


asyncio.run(main())
