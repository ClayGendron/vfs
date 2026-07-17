"""Evidence for story 041 — run with: uv run python context/stories/041-mount-spine-visibility/repro.py

Demonstrates, against base2 at 06cf551, that paths the router owns by
virtue of its mount table are invisible:

1. On a pure router with mounts, ls/stat/tree on '/' (and any mount
   ancestor) fail not_found — the namespace cannot be discovered top-down.
2. A scoped fan-out whose scope is a mount ancestor fails on a pure
   router, and on a storage root it SUCCEEDS while silently omitting
   every mount under the scope — narrowing a scope silently shrinks
   coverage.
3. A pure-router child mounted mid-tree cannot answer stat of its own
   mount point (the parent routes rel '/' into it; same defect one level
   down) — fixing spine answers at every node fixes this by composition.
"""

from __future__ import annotations

import asyncio
from typing import Any

from vfs.base2 import VirtualFileSystem
from vfs.models2 import Observation
from vfs.results2 import Result, ResultError, VFSErrorKind


class Store(VirtualFileSystem):
    """Storage terminal: stat reports absence (mountability), reads return one row."""

    def __init__(self, hit: str, **kw: Any) -> None:
        super().__init__(storage=True, **kw)
        self.hit = hit

    async def _call_local_impl(self, op: str, *, user_id: str | None = None, **kwargs: Any) -> Result:
        if op == "stat":
            errs = [
                ResultError(kind=VFSErrorKind.not_found, message="nf", path=o.path)
                for o in kwargs.get("observations", [])
            ]
            return Result(function=op, success=False, errors=errs)
        return Result(function=op, observations=[Observation(path=self.hit)])


def show(label: str, result: Result) -> None:
    if result.success:
        print(f"{label:<38} success rows={sorted(result.paths)}")
    else:
        print(f"{label:<38} FAILED  {result.errors[0].message}")


async def main() -> None:
    print("-- 1. pure router with mounts at /data/a and /data/b --")
    root = VirtualFileSystem()
    await root.add_mount(Store("/x.txt", name="a"), "/data/a")
    await root.add_mount(Store("/y.txt", name="b"), "/data/b")
    show("ls('/')", await root.ls("/"))
    show("stat('/data')", await root.stat("/data"))
    show("tree('/')", await root.tree("/"))
    show("grep scoped to '/data'", await root.grep("g", paths=("/data",)))
    show("grep unscoped (for contrast)", await root.grep("g"))

    print("-- 2. storage root with a row under /data plus a mount at /data/a --")
    sroot = Store("/data/local.txt")
    await sroot.add_mount(Store("/inside.txt", name="a"), "/data/a")
    show("grep unscoped", await sroot.grep("g"))
    show("grep scoped to '/data'", await sroot.grep("g", paths=("/data",)))

    print("-- 3. pure-router child mounted mid-tree --")
    outer = VirtualFileSystem()
    inner = VirtualFileSystem(name="hub")  # a pure router as an intermediate node
    await outer.add_mount(inner, "/hub")
    await inner.add_mount(Store("/z.txt", name="leaf"), "/leaf")
    show("outer.stat('/hub')", await outer.stat("/hub"))
    show("outer.ls('/hub')", await outer.ls("/hub"))


asyncio.run(main())
