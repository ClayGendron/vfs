"""Review 165, check 3: what the write gate's `create` and `read` legs answer on a visible, barred target today.

Under today's ladder a `read` holder is the stand-in for tomorrow's `list` holder on the `create`/`read` legs
of `_decide` (rights.py:686-688), which pass any seen target without consulting a compile.
Also: the anonymous gate under a `none` root with an `open` posture beneath (today's behaviour).
Run from the vfs root:  uv run python <this file>
"""

from __future__ import annotations

import asyncio

from vfs.authority import Authority, Principal
from vfs.models import Edge, Entry
from vfs.storage.protocol import ResolvedPair
from vfs.paths import Path
from vfs.storage.backends.memory import InMemoryStorage

SYSTEM = Authority.system()
BOB = Authority.of(Principal("bob"))
NOBODY = Authority.anonymous()


def show(label: str, result) -> None:
    print(f"\n== {label} ==  success={result.success}")
    for o in result.observations:
        fields = {k: getattr(o, k) for k in sorted(o.populated) if k not in {"path", "kind"}}
        print(f"  OBS  {o.path} kind={o.kind} {fields}")
    for e in result.errors:
        print(f"  ERR  kind={e.kind.value} severity={e.severity.value} path={e.path} message={e.message!r}")


async def main() -> None:
    storage = InMemoryStorage()
    files = ["/team/plan.md", "/team/sub/x.md", "/mine/keep.md", "/scratch/old.md", "/notes.txt"]
    assert (await storage.write(entries=[Entry(path=Path(p), content="body " + p) for p in files], parents=True, authority=SYSTEM)).success
    assert (await storage.posture(path=Path("/"), posture="private", authority=SYSTEM)).success
    assert (await storage.grant(path=Path("/team"), principal="bob", level="read", authority=SYSTEM)).success
    assert (await storage.grant(path=Path("/mine"), principal="bob", level="read_write", authority=SYSTEM)).success

    print("#### A. the create leg on an occupied visible target (bob holds read on /team) ####")
    show("mkdir /team exist_ok=True as bob", await storage.mkdir(path=Path("/team"), exist_ok=True, authority=BOB))
    show("mkdir /team as bob", await storage.mkdir(path=Path("/team"), authority=BOB))
    show("mkdir /team/plan.md (a file) as bob", await storage.mkdir(path=Path("/team/plan.md"), authority=BOB))
    assert (await storage.delete(path=Path("/team/sub/x.md"), authority=SYSTEM)).success
    show("mkdir /team/sub/x.md (tombstoned, visible) as bob", await storage.mkdir(path=Path("/team/sub/x.md"), authority=BOB))
    show("write /team/sub/x.md (revive) as bob", await storage.write(entries=[Entry(path=Path("/team/sub/x.md"), content="z")], authority=BOB))

    print("\n#### B. the read leg: copy from a source the caller may only read into a prefix it may create in ####")
    show("copy /team/plan.md -> /mine/plan.md as bob", await storage.copy(operations=[ResolvedPair(Path("/team/plan.md"), Path("/mine/plan.md"))], authority=BOB))
    show("read /mine/plan.md as bob", await storage.read(path=Path("/mine/plan.md"), authority=BOB))
    print("   (today lawful: read >= read. Under the ladder the same leg passes a `list` source: no compile is consulted.)")

    print("\n#### C. anonymous under a `none` root with an `open` posture at /scratch (today) ####")
    assert (await storage.posture(path=Path("/scratch"), posture="open", authority=SYSTEM)).success
    show("anon write /scratch/hello.txt", await storage.write(entries=[Entry(path=Path("/scratch/hello.txt"), content="hi")], authority=NOBODY))
    show("anon ls /scratch", await storage.ls(path=Path("/scratch"), authority=NOBODY))
    show("anon ls /", await storage.ls(path=Path("/"), authority=NOBODY))
    show("anon glob /**", await storage.glob(patterns=("/**",), authority=NOBODY))
    print("\n-- the same calls as a named nobody (no grants) --")
    ZED = Authority.of(Principal("zed"))
    show("zed ls /", await storage.ls(path=Path("/"), authority=ZED))
    show("zed glob /**", await storage.glob(patterns=("/**",), authority=ZED))
    show("zed write /scratch/hello.txt", await storage.write(entries=[Entry(path=Path("/scratch/hello.txt"), content="hi")], authority=ZED))
    show("zed grants /scratch", await storage.grants(path=Path("/scratch"), authority=ZED))

    print("\n#### D. rmedge from a source the caller owns but holds no grant on (the floor on edges) ####")
    assert (await storage.posture(path=Path("/inbox"), posture="shared", authority=SYSTEM)).success
    assert (await storage.write(entries=[Entry(path=Path("/inbox/bob.md"), content="mine")], parents=True, authority=BOB)).success
    assert (await storage.mkedge(edges=[Edge(source=Path("/inbox/bob.md"), target=Path("/team/plan.md"), edge_type="r")], authority=SYSTEM)).success
    show("bob rmedge own -> /team/plan.md", await storage.rmedge(edges=[Edge(source=Path("/inbox/bob.md"), target=Path("/team/plan.md"), edge_type="r")], authority=BOB))


asyncio.run(main())
