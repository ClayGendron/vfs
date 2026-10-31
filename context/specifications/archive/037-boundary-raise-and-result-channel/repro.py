"""Historical evidence for story 037 — reproduces the PRE-037 defects at 54462cf.

Demonstrates, against base2 at 54462cf:
1. Fire-and-forget mutations: under raise_on_error=True, a grouped write's
   healthy sibling lands AFTER the caller has already seen the exception.
2. Result.__bool__ conflates success with non-emptiness.

This script no longer runs once 037 lands: the raise_on_error kwarg it
depends on was deleted (a TypeError here is itself the fix). To run it,
check out 54462cf. The living regressions are in tests/test_base.py
(test_sibling_writes_settle_before_failure_is_reported and friends) and
tests/test_results.py.
"""

from __future__ import annotations

import asyncio
from typing import Any

from vfs.base2 import VirtualFileSystem
from vfs.models2 import Entry, Observation
from vfs.results2 import Result, ResultError, VFSErrorKind


class DictFS(VirtualFileSystem):
    def __init__(self, **kw: Any) -> None:
        super().__init__(storage=True, **kw)
        self.files: dict[str, str] = {}
        self.write_log: list[str] = []

    async def _write_impl(self, *, path=None, entries=None, content=None, user_id=None, **kw) -> Result:
        rows = [(e.path, e.content or "") for e in entries] if entries is not None else [(path, content or "")]
        out = []
        for p, c in rows:
            self.files[p] = c
            self.write_log.append(p)
            out.append(Observation(path=p, kind="file", status="created"))
        return Result(function="write", observations=out)


class FailFS(DictFS):
    async def _write_impl(self, **kw) -> Result:
        return self._error("boom", kind=VFSErrorKind.unavailable)


class SlowOkFS(DictFS):
    async def _write_impl(self, **kw) -> Result:
        await asyncio.sleep(0.05)
        return await super()._write_impl(**kw)


async def case_fire_and_forget() -> None:
    print("=== grouped mutation + raise_on_error: sibling write lands after the raise ===")
    root = VirtualFileSystem(raise_on_error=True)
    ok, bad = SlowOkFS(), FailFS()
    await root.add_mount(ok, "/ok")
    await root.add_mount(bad, "/bad")
    entries = [Entry(path="/ok/a.txt", content="A"), Entry(path="/bad/b.txt", content="B")]
    try:
        await root.write(entries=entries)
        print("no raise?")
    except Exception as exc:  # noqa: BLE001
        print(f"write raised: {type(exc).__name__}: {exc}")
    print(f"ok.write_log immediately after raise: {ok.write_log}")
    await asyncio.sleep(0.1)
    print(f"ok.write_log 100ms later:             {ok.write_log}   <- landed after the caller saw the exception")


def case_bool_semantics() -> None:
    print("\n=== Result.__bool__ on successful-but-empty result ===")
    r = Result(function="glob", observations=[], success=True)
    print(f"success={r.success}, len={len(r)}, bool={bool(r)}   <- empty success is falsy")


async def main() -> None:
    await case_fire_and_forget()
    case_bool_semantics()


asyncio.run(main())
