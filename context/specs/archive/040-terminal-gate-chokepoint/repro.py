"""Evidence for story 040 — run with: uv run python context/stories/040-terminal-gate-chokepoint/repro.py

Demonstrates, against base2 at 06cf551: the routability → capability →
permission gate is hand-copied at five chokepoints and has drifted on the
error payload. Capability errors carry a structured ``path`` at some sites
and ``None`` at others; permission and no-mount errors never carry one, so
an agent must parse prose to learn which path was refused.
"""

from __future__ import annotations

import asyncio
from typing import Any

from vfs.base2 import VirtualFileSystem
from vfs.models2 import Entry, Observation
from vfs.results2 import Result, ResultError, VFSErrorKind


class Store(VirtualFileSystem):
    """Storage terminal with configurable capabilities; stat reports absence."""

    def __init__(self, caps: frozenset[str] | None = None, **kw: Any) -> None:
        super().__init__(storage=True, **kw)
        self._caps = caps

    def capabilities(self) -> frozenset[str] | None:
        return self._caps

    async def _call_local_impl(self, op: str, *, user_id: str | None = None, **kwargs: Any) -> Result:
        if op == "stat":
            errs = [
                ResultError(kind=VFSErrorKind.not_found, message="nf", path=o.path)
                for o in kwargs.get("observations", [])
            ]
            return Result(function=op, success=False, errors=errs)
        return Result(function=op, observations=[])


def show(label: str, result: Result) -> None:
    error = result.errors[0]
    kind = str(error.kind).split(".")[-1]
    print(f"{label:<42} kind={kind:<18} path={error.path!r}")


async def main() -> None:
    root = VirtualFileSystem()
    await root.add_mount(Store(permissions="read", name="ro"), "/ro")
    await root.add_mount(Store(caps=frozenset({"read"}), name="dim"), "/dim")

    show("no-mount (single write)", await root.write(path="/nowhere/x.txt", content="c"))
    show("permission (single write)", await root.write(path="/ro/x.txt", content="c"))
    show("permission (entry batch)", await root.write(entries=[Entry(path="/ro/y.txt", content="c")]))
    show("permission (move pair)", await root.move("/ro/a.txt", "/ro/b.txt"))
    show("capability (single grep scoped)", await root.grep("x", paths=("/dim/sub",)))
    show("capability (grouped stat)", await root.stat(observations=[Observation(path="/dim/f.txt")]))


asyncio.run(main())
