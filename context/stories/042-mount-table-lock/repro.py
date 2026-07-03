"""Evidence for story 042 — run with: uv run python context/stories/042-mount-table-lock/repro.py

Demonstrates, against base2 at 06cf551, three TOCTOU races in mount-table
mutation. ``add_mount`` runs its guards, suspends in the awaited
mountability probe (a real backend stat), then commits — and every fact
the guards established can change during the suspension:

1. Same path, same parent: both calls commit; the second silently
   overwrites the first in the table, leaving the first filesystem
   orphaned (``_parent`` set, in no table — unmountable forever).
2. Same child, two parents: the child lands in BOTH tables (the mount
   graph is no longer a tree); ``_parent`` points at whichever committed
   last.
3. Ancestor and descendant paths: ``/a`` and ``/a/b`` both mount at the
   same level, defeating the deeper-mount ownership check.
"""

from __future__ import annotations

import asyncio
from typing import Any

from vfs.base2 import VirtualFileSystem
from vfs.results2 import Result, ResultError, VFSErrorKind


class DBLikeFS(VirtualFileSystem):
    """Storage FS whose stat suspends like a real DB round-trip and reports absence."""

    def __init__(self, **kw: Any) -> None:
        super().__init__(storage=True, **kw)

    async def _call_local_impl(self, op: str, *, user_id: str | None = None, **kwargs: Any) -> Result:
        await asyncio.sleep(0.01)  # the suspension that opens the race window
        errs = [
            ResultError(kind=VFSErrorKind.not_found, message="nf", path=o.path)
            for o in kwargs.get("observations", [])
        ]
        return Result(function=op, success=False, errors=errs)


def errors(settled: list[Any]) -> list[str]:
    return [type(e).__name__ for e in settled if isinstance(e, Exception)]


async def main() -> None:
    print("-- 1. same path, same parent --")
    root = DBLikeFS()
    c1, c2 = DBLikeFS(name="c1"), DBLikeFS(name="c2")
    res = await asyncio.gather(
        root.add_mount(c1, "/same"), root.add_mount(c2, "/same"), return_exceptions=True
    )
    mounted = root._mounts.get("/same")
    print("errors raised:", errors(res))
    print("mount table holds:", mounted.name if mounted else None)
    print("orphaned (parent set, in no table):",
          [fs.name for fs in (c1, c2) if fs._parent is root and fs is not mounted])

    print("-- 2. same child, two parents --")
    p1, p2 = DBLikeFS(name="p1"), DBLikeFS(name="p2")
    child = DBLikeFS(name="child")
    res = await asyncio.gather(
        p1.add_mount(child, "/c"), p2.add_mount(child, "/c"), return_exceptions=True
    )
    print("errors raised:", errors(res))
    print("in p1 table:", "/c" in p1._mounts, "| in p2 table:", "/c" in p2._mounts,
          "| child._parent:", child._parent.name if child._parent else None)

    print("-- 3. ancestor and descendant paths --")
    root2 = DBLikeFS()
    a, ab = DBLikeFS(name="a"), DBLikeFS(name="ab")
    res = await asyncio.gather(
        root2.add_mount(a, "/a"), root2.add_mount(ab, "/a/b"), return_exceptions=True
    )
    print("errors raised:", errors(res))
    print("table (both at one level — deeper-mount check defeated):", sorted(root2._mounts))


asyncio.run(main())
