"""The road baseline a `list` rung must preserve — run from the vfs repo root with `uv run python`.

World: posture `private` at `/`; files under `/projects/alpha`, `/projects/beta`, `/pub`.
`ann` holds `read` on exactly one file deep in the private tree: `/projects/alpha/notes.md`.
Prints what ls, tree, stat and glob show her today (ADR 070: road directories as bare names).
"""

from __future__ import annotations

import asyncio

from vfs.authority import Authority, Principal
from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends.memory import InMemoryStorage

SYSTEM = Authority.system()
ANN = Authority.of(Principal("ann"))

FILES = {
    "/projects/alpha/notes.md": "alpha notes",
    "/projects/alpha/other.md": "alpha other",
    "/projects/beta/secret.md": "beta secret",
    "/pub/readme.md": "public readme",
}


def show(label: str, result) -> None:
    print(f"\n== {label}: success={result.success}")
    for obs in result.observations:
        print(f"   {str(obs.path):32} kind={obs.kind:10} populated={sorted(obs.populated)}")
    for err in result.errors:
        dumped = err.model_dump(exclude_none=True)
        print(f"   error kind={err.kind} path={dumped.get('path')} message={dumped.get('message') or dumped.get('detail')!r} data={dumped.get('data')}")


async def main() -> None:
    storage = InMemoryStorage()
    entries = [Entry(path=Path(p), content=c) for p, c in FILES.items()]
    assert (await storage.write(entries=entries, parents=True, authority=SYSTEM)).success
    assert (await storage.posture(path=Path("/"), posture="private", authority=SYSTEM)).success
    assert (await storage.grant(path=Path("/projects/alpha/notes.md"), principal="ann", level="read", authority=SYSTEM)).success

    show("ls / as ann", await storage.ls(path=Path("/"), authority=ANN))
    show("ls /projects as ann", await storage.ls(path=Path("/projects"), authority=ANN))
    show("ls /projects/alpha as ann", await storage.ls(path=Path("/projects/alpha"), authority=ANN))
    show("tree / as ann", await storage.tree(path=Path("/"), authority=ANN))
    show("stat /projects (road dir) as ann", await storage.stat(path=Path("/projects"), authority=ANN))
    show("stat /projects/beta (hidden dir) as ann", await storage.stat(path=Path("/projects/beta"), authority=ANN))
    show("stat /projects/alpha/other.md (hidden file) as ann", await storage.stat(path=Path("/projects/alpha/other.md"), authority=ANN))
    show("read /projects (road dir) as ann", await storage.read(path=Path("/projects"), authority=ANN))
    show("glob ** as ann", await storage.glob(patterns=("**",), authority=ANN))
    show("grep 'alpha' as ann", await storage.grep(pattern="alpha", authority=ANN))
    show("mkdir /projects/gamma as ann (road parent)", await storage.mkdir(path=Path("/projects/gamma"), authority=ANN))
    show("write /projects/alpha/notes.md as ann (read-only grant)", await storage.write(entries=[Entry(path=Path("/projects/alpha/notes.md"), content="x")], authority=ANN))
    show("ls / as system (for contrast)", await storage.ls(path=Path("/"), authority=SYSTEM))
    await storage.close()


asyncio.run(main())
