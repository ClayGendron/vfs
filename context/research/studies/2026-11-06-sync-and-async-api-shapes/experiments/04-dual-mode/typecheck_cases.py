"""Setting 4: what ty and mypy say about the dual call, and whether a forgotten await is caught.

Each mechanism is declared with the annotations its library really gives it (Prefect's decorators are
imported for real; fsspec ships no annotations on cat_file; greenback and asgiref are typed). For each
one there are three callers: a sync caller, an async caller that awaits, and an async caller that forgot.
"""

from __future__ import annotations

from collections.abc import Coroutine, Generator
from typing import Any, reveal_type

import fsspec.asyn
from asgiref.sync import async_to_sync
from prefect._internal.compatibility.async_dispatch import async_dispatch
from prefect.utilities.asyncutils import sync_compatible


class Result:
    success: bool = True


async def _aread(path: str) -> Result:
    return Result()


# ---------------------------------------------------------------------------
# Declarations
# ---------------------------------------------------------------------------


class Detect:
    def read(self, path: str) -> Result | Coroutine[Any, Any, Result]: ...


class Twins:
    def read(self, path: str) -> Result: ...
    async def aread(self, path: str) -> Result: ...


class PrefectSC:
    @sync_compatible
    async def read(self, path: str) -> Result: ...


class PrefectAD:
    async def aread(self, path: str) -> Result: ...

    @async_dispatch(aread)
    def read(self, path: str) -> Result: ...


class Lazy:
    def __await__(self) -> Generator[Any, None, Result]: ...
    def __getattr__(self, name: str) -> Any: ...


class LazyFS:
    def read(self, path: str) -> Lazy: ...


class Handle:
    def __await__(self) -> Generator[Any, None, Result]: ...
    def result(self) -> Result: ...


class HandleFS:
    def read(self, path: str) -> Handle: ...


fsspec_fs = fsspec.asyn.AsyncFileSystem()
asgiref_read = async_to_sync(_aread)


# ---------------------------------------------------------------------------
# Callers
# ---------------------------------------------------------------------------


def sync_callers() -> None:
    reveal_type(Detect().read("a"))
    reveal_type(PrefectSC().read("a"))
    reveal_type(PrefectAD().read("a"))
    reveal_type(LazyFS().read("a").success)
    reveal_type(HandleFS().read("a").result())
    reveal_type(Twins().read("a"))
    reveal_type(fsspec_fs.cat_file("a"))
    reveal_type(asgiref_read("a"))
    Detect().read("a").success  # union member Coroutine has no .success
    PrefectSC().read("a").success


async def awaiting_callers() -> None:
    reveal_type(await Detect().read("a"))  # awaiting a union that includes Result
    reveal_type(await PrefectSC().read("a"))
    reveal_type(await PrefectAD().read("a"))
    reveal_type(await LazyFS().read("a"))
    reveal_type(await HandleFS().read("a"))
    reveal_type(await Twins().aread("a"))
    reveal_type(await fsspec_fs._cat_file("a"))


async def forgot_the_await() -> None:
    r1 = LazyFS().read("a")
    r1.success  # no await: silently blocks the loop thread, or raises at runtime
    Twins().aread("a")  # bare coroutine statement
    r2 = Twins().aread("a")
    r2.success
    HandleFS().read("a")  # handle dropped unawaited
    Detect().read("a")  # union dropped unused
    PrefectSC().read("a")
