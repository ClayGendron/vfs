"""Evidence for story 038 — run with: uv run python context/stories/038-branded-rebase-and-path-length-policy/repro.py

Demonstrates, against base2 at 54462cf:
1. Rebase overflow: a child row valid in local coordinates raises a raw
   ValueError out of public glob() when the rebased global path exceeds 1024.
2. Rebase hot-path cost: with_mount pays the full gate per row vs a branded
   concat of the same two canonical parts.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from vfs.base2 import VirtualFileSystem
from vfs.models2 import Observation
from vfs.paths import Path
from vfs.results2 import Result


class GlobFS(VirtualFileSystem):
    def __init__(self, deep: str, **kw: Any) -> None:
        super().__init__(storage=True, **kw)
        self.deep = deep

    async def _glob_impl(self, *, paths=(), user_id=None, **kw) -> Result:
        return Result(function="glob", observations=[Observation(path=Path(self.deep), kind="file")])


async def case_rebase_overflow() -> None:
    print("=== rebase overflow escapes public glob (no-raise contract) ===")
    deep = "/" + "a" * 200 + "/" + "b" * 200 + "/" + "c" * 200 + "/" + "d" * 200 + "/" + "e" * 150
    root = VirtualFileSystem()
    child = GlobFS(deep)
    mount = "/m" + "/x" * 40
    await root.add_mount(child, mount)
    print(f"local row: {len(deep)} chars (valid); rebased: {len(mount) + len(deep)} chars (> 1024)")
    try:
        r = await root.glob("**/*")
        print("OK:", r.success, len(r))
    except Exception as exc:  # noqa: BLE001
        print(f"RAISED through public glob: {type(exc).__name__}: {str(exc)[:90]}")


def case_rebase_perf() -> None:
    print("\n=== rebase cost per row ===")
    p = Path("/some/deepish/path/to/a/file.py")
    mount = Path("/mnt/data")
    n = 20_000
    t0 = time.perf_counter()
    for _ in range(n):
        p.with_mount(mount)
    gate_us = (time.perf_counter() - t0) / n * 1e6
    t0 = time.perf_counter()
    for _ in range(n):
        Path._brand(mount + p)
    brand_us = (time.perf_counter() - t0) / n * 1e6
    print(f"Path.with_mount (full gate): {gate_us:.2f} us/row -> {gate_us * 10:.1f} ms per 10k-row merge")
    print(f"branded concat:              {brand_us:.2f} us/row ({gate_us / brand_us:.0f}x)")


async def main() -> None:
    await case_rebase_overflow()
    case_rebase_perf()


asyncio.run(main())
