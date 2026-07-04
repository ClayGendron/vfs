"""Evidence for story 048 — run with: uv run python context/stories/048-mount-lock-reentrancy/repro.py

Demonstrates, against base2 post-042, that the non-reentrant mount lock
turns a re-entrant mutator call from inside the mountability probe into a
silent hang. Each case is wrapped in ``wait_for``; a timeout IS the
deadlock proof:

1. Self re-entrancy: an "auto-mount on first access" impl calls
   ``self.add_mount(...)`` mid-probe and deadlocks on its own lock.
2. Ancestor re-entrancy: a delegated add descends root->child holding
   root's lock; the child's impl calls ``root.add_mount(...)`` and
   re-enters the lock its own task holds up the stack.
"""

from __future__ import annotations

import asyncio
from typing import Any

from vfs.base2 import VirtualFileSystem
from vfs.results2 import Result, ResultError, VFSErrorKind


def _absent(op: str, kwargs: dict[str, Any]) -> Result:
    errs = [
        ResultError(kind=VFSErrorKind.not_found, message="nf", path=o.path)
        for o in kwargs.get("observations", [])
    ]
    return Result(function=op, success=False, errors=errs)


class ReentrantMountFS(VirtualFileSystem):
    """Storage fs that lazily mounts a sibling during its own stat probe."""

    def __init__(self, **kw: Any) -> None:
        super().__init__(storage=True, **kw)
        self.triggered = False

    async def _call_local_impl(self, op: str, *, user_id: str | None = None, **kwargs: Any) -> Result:
        if not self.triggered:
            self.triggered = True
            await self.add_mount(VirtualFileSystem(name="auto"), "/auto")
        return _absent(op, kwargs)


class ReentrantAncestorFS(VirtualFileSystem):
    """Child storage fs whose probe calls a mutator on its (held) ancestor."""

    def __init__(self, **kw: Any) -> None:
        super().__init__(storage=True, **kw)
        self.parent_ref: VirtualFileSystem | None = None
        self.triggered = False

    async def _call_local_impl(self, op: str, *, user_id: str | None = None, **kwargs: Any) -> Result:
        if not self.triggered and self.parent_ref is not None:
            self.triggered = True
            await self.parent_ref.add_mount(VirtualFileSystem(name="up"), "/up")
        return _absent(op, kwargs)


async def main() -> None:
    print("-- 1. self re-entrancy: impl calls self.add_mount mid-probe --")
    root = ReentrantMountFS(name="root")
    try:
        await asyncio.wait_for(root.add_mount(VirtualFileSystem(name="incoming"), "/a"), timeout=3)
        print("completed, table:", sorted(root._mounts))
    except TimeoutError:
        print("SELF-DEADLOCK: add_mount hung on its own non-reentrant lock")

    print("-- 2. ancestor re-entrancy: delegated child calls root.add_mount --")
    outer = VirtualFileSystem(name="outer")
    child = ReentrantAncestorFS(name="child")
    child.parent_ref = outer
    await outer.add_mount(child, "/child")
    try:
        await asyncio.wait_for(outer.add_mount(VirtualFileSystem(name="incoming"), "/child/deep"), timeout=3)
        print("completed, tables outer=%s child=%s" % (sorted(outer._mounts), sorted(child._mounts)))
    except TimeoutError:
        print("SELF-DEADLOCK: delegated add re-entered the held ancestor lock")


asyncio.run(main())
