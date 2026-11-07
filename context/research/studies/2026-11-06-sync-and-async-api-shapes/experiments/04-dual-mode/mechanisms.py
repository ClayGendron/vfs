"""Dual-mode prototypes: one object whose read() is meant to serve both `fs.read(p)` and `await fs.read(p)`.

Each class wraps the same stand-in coroutine, `_aread`, which awaits a short sleep and reports
which thread and which event loop actually ran it, so the harness can see loop affinity.
Written for this study; no code is copied from the libraries whose public APIs it calls.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine, Generator
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any

SLEEP = 0.05


@dataclass
class Result:
    path: str
    thread: str
    loop_id: int
    success: bool = True


async def _aread(path: str) -> Result:
    await asyncio.sleep(SLEEP)
    return Result(path, threading.current_thread().name, id(asyncio.get_running_loop()))


# ---------------------------------------------------------------------------
# A private loop on a daemon thread, the shape vfs.sync uses today
# ---------------------------------------------------------------------------


class _Portal:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, name="portal-loop", daemon=True)
        self.thread.start()

    def run(self, coro: Coroutine[Any, Any, Result]) -> Result:
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result()


# ---------------------------------------------------------------------------
# Mechanisms
# ---------------------------------------------------------------------------


class Detect:
    """Plain context detection: a coroutine when a loop runs on this thread, else asyncio.run."""

    def read(self, path: str) -> Any:
        coro = _aread(path)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        return coro


class Twins:
    """Control: class twins, the shape vfs ships today (async class, sync class on a portal)."""

    def __init__(self) -> None:
        self._portal = _Portal()

    def read(self, path: str) -> Result:
        return self._portal.run(_aread(path))

    async def aread(self, path: str) -> Result:
        return await _aread(path)


class PrefectSyncCompatible:
    """Prefect's sync_compatible decorator over the async method."""

    from prefect.utilities.asyncutils import sync_compatible as _sc

    @_sc
    async def read(self, path: str) -> Result:
        return await _aread(path)

    del _sc


class PrefectAsyncDispatch:
    """Prefect's async_dispatch: a real sync body, with the async body chosen by detection."""

    from prefect._internal.compatibility.async_dispatch import async_dispatch as _ad

    def __init__(self) -> None:
        self._portal = _Portal()

    async def aread(self, path: str) -> Result:
        return await _aread(path)

    @_ad(aread)
    def read(self, path: str) -> Result:
        return self._portal.run(_aread(path))

    del _ad


def _fsspec_class() -> type:
    from fsspec.asyn import AsyncFileSystem

    class StandInFS(AsyncFileSystem):
        async def _cat_file(self, path: str, start: Any = None, end: Any = None, **kwargs: Any) -> Result:
            return await _aread(path)

    return StandInFS


class FsspecSync:
    """fsspec with asynchronous=False: fs.cat_file blocks on the fsspec IO thread; fs._cat_file is the coroutine."""

    def __init__(self) -> None:
        self.fs = _fsspec_class()(asynchronous=False, skip_instance_cache=True)

    def read(self, path: str) -> Any:
        return self.fs.cat_file(path)

    def aread(self, path: str) -> Any:
        return self.fs._cat_file(path)


class FsspecAsync:
    """fsspec with asynchronous=True: the mode flag fixed at construction, inside the loop."""

    def __init__(self) -> None:
        self.fs = _fsspec_class()(asynchronous=True, skip_instance_cache=True)

    def read(self, path: str) -> Any:
        return self.fs.cat_file(path)

    def aread(self, path: str) -> Any:
        return self.fs._cat_file(path)


class SqlaAwaitOnly:
    """SQLAlchemy's bridge: a sync read() that await_only()s; works only under greenlet_spawn."""

    def read(self, path: str) -> Result:
        from sqlalchemy.util import await_only

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            from sqlalchemy.util import greenlet_spawn

            return asyncio.run(greenlet_spawn(lambda: await_only(_aread(path))))
        return await_only(_aread(path))


class Greenback:
    """greenback: a sync read() that, on a loop thread, reenters that loop through a portal."""

    def read(self, path: str) -> Result:
        import greenback

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(_aread(path))
        return greenback.await_(_aread(path))


class Asgiref:
    """asgiref: async_to_sync for the sync spelling, a coroutine when a loop runs."""

    def read(self, path: str) -> Any:
        from asgiref.sync import async_to_sync

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return async_to_sync(_aread)(path)
        return _aread(path)


class AsgirefPlain:
    """asgiref: async_to_sync always, no detection: what a sync-only wrapper would do."""

    def read(self, path: str) -> Result:
        from asgiref.sync import async_to_sync

        return async_to_sync(_aread)(path)


class LazyHandle:
    """A handle that is awaitable and also computes on first attribute access."""

    def __init__(self, path: str, force: Any) -> None:
        self._path = path
        self._force = force
        self._done: Result | None = None

    def __await__(self) -> Generator[Any, None, Result]:
        result = yield from _aread(self._path).__await__()
        self._done = result
        return result

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if self._done is None:
            self._done = self._force(_aread(self._path))
        return getattr(self._done, name)


class LazyPortal:
    """Lazy handle forced on a private loop thread when read synchronously."""

    def __init__(self) -> None:
        self._portal = _Portal()

    def read(self, path: str) -> LazyHandle:
        return LazyHandle(path, self._portal.run)


class LazyGreenback:
    """Lazy handle forced through greenback when on a loop thread, asyncio.run otherwise."""

    def read(self, path: str) -> LazyHandle:
        import greenback

        def force(coro: Coroutine[Any, Any, Result]) -> Result:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                return asyncio.run(coro)
            return greenback.await_(coro)

        return LazyHandle(path, force)


class Handle:
    """Dual-use handle: awaitable, with an explicit blocking .result() (no attribute magic)."""

    def __init__(self, path: str, portal: _Portal) -> None:
        self._path = path
        self._portal = portal

    def __await__(self) -> Generator[Any, None, Result]:
        return _aread(self._path).__await__()

    def result(self) -> Result:
        return self._portal.run(_aread(self._path))


class HandleResult:
    def __init__(self) -> None:
        self._portal = _Portal()

    def read(self, path: str) -> Handle:
        return Handle(path, self._portal)


MECHANISMS: dict[str, type] = {
    "detect": Detect,
    "twins": Twins,
    "prefect_sync_compatible": PrefectSyncCompatible,
    "prefect_async_dispatch": PrefectAsyncDispatch,
    "fsspec_sync_flag": FsspecSync,
    "fsspec_async_flag": FsspecAsync,
    "sqla_await_only": SqlaAwaitOnly,
    "greenback": Greenback,
    "asgiref_detect": Asgiref,
    "asgiref_plain": AsgirefPlain,
    "lazy_portal": LazyPortal,
    "lazy_greenback": LazyGreenback,
    "handle_result": HandleResult,
}
