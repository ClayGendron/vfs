"""Shared test doubles for the base router test files.

Backend and node fakes built up alongside ``tests/test_base.py`` — storage
doubles satisfy the family protocols from ``vfs.storage``; FS doubles subclass
``vfs.base2.VirtualFileSystem`` to observe or steer router behavior.
"""

from __future__ import annotations

import asyncio
from typing import Any

from vfs.base2 import VirtualFileSystem
from vfs.models2 import Entry, Observation
from vfs.paths import ObjectKind, Path
from vfs.results2 import Result, ResultError, VFSErrorKind


def _failed(function: str, kind: VFSErrorKind, message: str, path: Path | None = None) -> Result:
    """A backend-composed failure — doubles have no router ``_error`` helper."""
    return Result(function=function, success=False, errors=[ResultError(kind=kind, message=message, path=path)])


class RecorderStorage:
    """Full-family storage double: records every dispatch, answers success.

    The base backend double — one method per op, each two lines, so the
    object satisfies every family protocol.  Subclasses override an op's
    behavior or ``_answer`` for a different canned reply.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _answer(self, op: str, kwargs: dict[str, Any]) -> Result:
        self.calls.append((op, kwargs))
        return Result(function=op, observations=[])

    async def read(self, *, user_id: str | None = None, **kwargs: Any) -> Result:
        return self._answer("read", kwargs)

    async def stat(self, *, user_id: str | None = None, **kwargs: Any) -> Result:
        return self._answer("stat", kwargs)

    async def ls(self, *, user_id: str | None = None, **kwargs: Any) -> Result:
        return self._answer("ls", kwargs)

    async def tree(self, *, user_id: str | None = None, **kwargs: Any) -> Result:
        return self._answer("tree", kwargs)

    async def glob(self, *, user_id: str | None = None, **kwargs: Any) -> Result:
        return self._answer("glob", kwargs)

    async def grep(self, *, user_id: str | None = None, **kwargs: Any) -> Result:
        return self._answer("grep", kwargs)

    async def glean(self, *, user_id: str | None = None, **kwargs: Any) -> Result:
        return self._answer("glean", kwargs)

    async def write(self, *, user_id: str | None = None, **kwargs: Any) -> Result:
        return self._answer("write", kwargs)

    async def edit(self, *, user_id: str | None = None, **kwargs: Any) -> Result:
        return self._answer("edit", kwargs)

    async def delete(self, *, user_id: str | None = None, **kwargs: Any) -> Result:
        return self._answer("delete", kwargs)

    async def mkdir(self, *, user_id: str | None = None, **kwargs: Any) -> Result:
        return self._answer("mkdir", kwargs)

    async def move(self, *, user_id: str | None = None, **kwargs: Any) -> Result:
        return self._answer("move", kwargs)

    async def copy(self, *, user_id: str | None = None, **kwargs: Any) -> Result:
        return self._answer("copy", kwargs)

    async def graph(self, *, user_id: str | None = None, **kwargs: Any) -> Result:
        return self._answer("graph", kwargs)

    async def mkedge(self, *, user_id: str | None = None, **kwargs: Any) -> Result:
        return self._answer("mkedge", kwargs)

    async def run(self, *, user_id: str | None = None, **kwargs: Any) -> Result:
        return self._answer("run", kwargs)


class ReadFamilyStorage:
    """Read family only — the minimum viable backend; nothing else exists."""

    async def read(self, **kwargs: Any) -> Result:
        return Result(function="read", observations=[])

    async def stat(self, **kwargs: Any) -> Result:
        return Result(function="stat", observations=[])

    async def ls(self, **kwargs: Any) -> Result:
        return Result(function="ls", observations=[])

    async def tree(self, **kwargs: Any) -> Result:
        return Result(function="tree", observations=[])


class SpyFS(VirtualFileSystem):
    """A mount that records how many times it was closed."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.close_count = 0

    async def close(self) -> None:
        self.close_count += 1
        await super().close()


class MountPolicyFS(VirtualFileSystem):
    """A storage-bearing fs that refuses mounts at the given paths."""

    def __init__(self, blocked: set[str]) -> None:
        super().__init__(storage=RecorderStorage())
        self._blocked = set(blocked)

    async def _is_path_mountable(self, path: Path) -> tuple[bool, str]:
        if path in self._blocked:
            return False, "storage contents conflict with that mount point"
        return True, ""


class DictStorage(RecorderStorage):
    """Minimal storage backend: a path -> kind dict behind stat."""

    def __init__(self, entries: dict[str, ObjectKind]) -> None:
        super().__init__()
        self._entries = entries

    async def stat(
        self,
        *,
        path: Path | None = None,
        observations: list[Observation] | None = None,
        user_id: str | None = None,
        **_: Any,
    ) -> Result:
        wanted = [path] if path is not None else [o.path for o in observations or []]
        rows = [Observation(path=Path(p), kind=self._entries[p]) for p in wanted if p in self._entries]
        if path is not None and not rows:
            return _failed("stat", VFSErrorKind.not_found, f"Not found: {path}", path=Path(path))
        return Result(function="stat", observations=rows)


class DictStorageFS(VirtualFileSystem):
    """Node holding a :class:`DictStorage` terminal."""

    def __init__(self, entries: dict[str, ObjectKind], **kwargs: Any) -> None:
        super().__init__(storage=DictStorage(entries), **kwargs)


class BadCloseFS(VirtualFileSystem):
    """A mount whose close always fails."""

    async def close(self) -> None:
        raise RuntimeError("boom")


class SuspendingStorage(RecorderStorage):
    """Backend whose round-trip suspends, like a real DB stat.

    Every probed path reports absent (``not_found``), so any mount path is
    mountable — the point is the suspension, which is what opens the race
    window the mount lock closes.  An optional *gate* holds the probe open
    until the test releases it.
    """

    def __init__(self, gate: asyncio.Event | None = None) -> None:
        super().__init__()
        self._gate = gate

    def _answer(self, op: str, kwargs: dict[str, Any]) -> Result:
        self.calls.append((op, kwargs))
        errors = [
            ResultError(kind=VFSErrorKind.not_found, message="not found", path=o.path)
            for o in kwargs.get("observations") or []
        ]
        return Result(function=op, success=False, errors=errors)

    async def stat(self, *, user_id: str | None = None, **kwargs: Any) -> Result:
        if self._gate is not None:
            await self._gate.wait()
        else:
            await asyncio.sleep(0)
        return self._answer("stat", kwargs)


class SuspendingStorageFS(VirtualFileSystem):
    """Node holding a :class:`SuspendingStorage` backend."""

    def __init__(self, *, gate: asyncio.Event | None = None, **kwargs: Any) -> None:
        super().__init__(storage=SuspendingStorage(gate), **kwargs)


class SlowCloseFS(VirtualFileSystem):
    """A mount whose close suspends, opening the close loop's race window."""

    async def close(self) -> None:
        # Enough yields for a racing add_mount to pass its probe and commit
        # while the close loop is still suspended in here.
        for _ in range(20):
            await asyncio.sleep(0)
        await super().close()


class GatedCloseFS(SpyFS):
    """A mount whose close parks on an event — a dispose the test can hold open."""

    def __init__(self, gate: asyncio.Event, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._gate = gate

    async def close(self) -> None:
        await self._gate.wait()
        await super().close()


class RunnerFS(VirtualFileSystem):
    """A storage-less leaf that answers read/run and records the calls it gets."""

    def __init__(self, *, caps: frozenset[str] | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._caps = caps
        self.calls: list[tuple[str, str, object]] = []

    def capabilities(self) -> frozenset[str] | None:
        return self._caps

    async def read(
        self,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        assert path is not None  # the router always dispatches here with a path
        self.calls.append(("read", path, columns))
        return Result(function="read", observations=[Observation(path=Path(path), kind="tool")])

    async def run(
        self,
        path: str,
        *,
        arguments: dict[str, Any] | None = None,
        user_id: str | None = None,
    ) -> Result:
        self.calls.append(("run", path, arguments))
        return Result(function="run", observations=[Observation(path=Path(path), kind="tool")])


class EchoStorage(RecorderStorage):
    """Recorder whose ops answer with one observation at a fixed local path."""

    def __init__(self, echo_path: str = "/hit.md") -> None:
        super().__init__()
        self._echo_path = echo_path

    def _answer(self, op: str, kwargs: dict[str, Any]) -> Result:
        self.calls.append((op, kwargs))
        return Result(function=op, observations=[Observation(path=Path(self._echo_path))])


class RecorderFS(VirtualFileSystem):
    """Node holding a recording backend; ``calls`` reads through to it."""

    def __init__(self, storage: RecorderStorage | None = None, **kwargs: Any) -> None:
        self.backend = storage if storage is not None else RecorderStorage()
        super().__init__(storage=self.backend, **kwargs)

    @property
    def calls(self) -> list[tuple[str, dict[str, Any]]]:
        return self.backend.calls


class EchoFS(RecorderFS):
    """Recorder node whose backend echoes one observation per dispatch."""

    def __init__(self, echo_path: str = "/hit.md", storage: RecorderStorage | None = None, **kwargs: Any) -> None:
        super().__init__(storage=storage if storage is not None else EchoStorage(echo_path), **kwargs)

    async def _is_path_mountable(self, path: Path) -> tuple[bool, str]:
        # Echoed rows are not namespace truth — always accept mounts.
        return True, ""


class LimitedEchoFS(EchoFS):
    """Echo mount that advertises only the given capability set (policy)."""

    def __init__(self, caps: frozenset[str], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._caps = caps

    def capabilities(self) -> frozenset[str] | None:
        return self._caps


def _mutate(fs: VirtualFileSystem, op: str, base: str):
    """Invoke the mutating *op* against targets under *base* (no trailing slash)."""
    calls = {
        "write": lambda: fs.write(path=f"{base}/f.txt", content="x"),
        "edit": lambda: fs.edit(path=f"{base}/f.txt", old="a", new="b"),
        "delete": lambda: fs.delete(path=f"{base}/f.txt"),
        "mkdir": lambda: fs.mkdir(f"{base}/d"),
        "mkedge": lambda: fs.mkedge(f"{base}/a.py", f"{base}/b.py", "imports"),
        "move": lambda: fs.move(src=f"{base}/a.txt", dest=f"{base}/b.txt"),
        "copy": lambda: fs.copy(src=f"{base}/a.txt", dest=f"{base}/b.txt"),
    }
    return calls[op]()


def _mutate_at_root(fs: VirtualFileSystem, op: str, target: str):
    """Invoke the mutating *op* with *target* (root or reserved) as its write target."""
    calls = {
        "write": lambda: fs.write(path=target, content="x"),
        "edit": lambda: fs.edit(path=target, old="a", new="b"),
        "delete": lambda: fs.delete(path=target),
        "mkdir": lambda: fs.mkdir(target),
        "mkedge": lambda: fs.mkedge(target, "/b.py", "imports"),
        "move": lambda: fs.move(src="/a.txt", dest=target),
        "copy": lambda: fs.copy(src="/a.txt", dest=target),
    }
    return calls[op]()


def _fan(fs: VirtualFileSystem, op: str, **kwargs: Any):
    """Invoke the fan-out verb *op* with its required query argument."""
    calls = {
        "glob": lambda: fs.glob("*.py", **kwargs),
        "grep": lambda: fs.grep("needle", **kwargs),
        "glean": lambda: fs.glean("how does auth work", **kwargs),
    }
    return calls[op]()


class DeepRowStorage(RecorderStorage):
    """Backend answering a deep row plus an ordinary sibling."""

    DEEP = "/" + "/".join(["a" * 250] * 4)  # 1004 chars — valid locally

    def _answer(self, op: str, kwargs: dict[str, Any]) -> Result:
        self.calls.append((op, kwargs))
        rows = [Observation(path=Path(self.DEEP)), Observation(path=Path("/ok.py"))]
        return Result(function=op, observations=rows)


class DeepRowFS(EchoFS):
    """Echo mount whose backend answers a deep row plus an ordinary sibling."""

    DEEP = DeepRowStorage.DEEP

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(storage=DeepRowStorage(), **kwargs)


class SlowWriteStorage(RecorderStorage):
    """Backend whose write is slow and logged — for settle-order proof."""

    def __init__(self) -> None:
        super().__init__()
        self.write_log: list[str] = []

    async def write(self, *, entries: list[Entry] | None = None, user_id: str | None = None, **_: Any) -> Result:
        await asyncio.sleep(0.02)
        rows = []
        for entry in entries or []:
            self.write_log.append(entry.path)
            rows.append(Observation(path=entry.path, kind="file", status="created"))
        return Result(function="write", observations=rows)


class SlowWriteFS(VirtualFileSystem):
    """Node over a :class:`SlowWriteStorage`; ``write_log`` reads through."""

    def __init__(self, **kwargs: Any) -> None:
        backend = SlowWriteStorage()
        super().__init__(storage=backend, **kwargs)
        self.write_log = backend.write_log


class FailingWriteStorage(RecorderStorage):
    """Backend whose write fails fast with a classified Result."""

    async def write(self, **_: Any) -> Result:
        return _failed("write", VFSErrorKind.unavailable, "boom")


class FailingWriteFS(VirtualFileSystem):
    """Node over a :class:`FailingWriteStorage`."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(storage=FailingWriteStorage(), **kwargs)


class BuggyWriteStorage(RecorderStorage):
    """Backend whose write raises a raw exception — a backend bug."""

    async def write(self, **_: Any) -> Result:
        msg = "impl bug"
        raise RuntimeError(msg)


class BuggyWriteFS(VirtualFileSystem):
    """Node over a :class:`BuggyWriteStorage`."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(storage=BuggyWriteStorage(), **kwargs)


class CannedStorage(RecorderStorage):
    """Backend answering each op from a canned Result, recording calls."""

    def __init__(self, answers: dict[str, Result] | None = None) -> None:
        super().__init__()
        self.answers = answers or {}

    def _answer(self, op: str, kwargs: dict[str, Any]) -> Result:
        self.calls.append((op, kwargs))
        return self.answers.get(op, Result(function=op, observations=[]))


class CannedFS(RecorderFS):
    """Node over a :class:`CannedStorage` terminal."""

    def __init__(self, answers: dict[str, Result] | None = None, **kwargs: Any) -> None:
        super().__init__(storage=CannedStorage(answers), **kwargs)

    async def _is_path_mountable(self, path: Path) -> tuple[bool, str]:
        # Canned rows are not namespace truth — always accept mounts.
        return True, ""


class SpyRouterFS(VirtualFileSystem):
    """Pure router recording its public read calls — proves a parent dispatched to it."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.reads: list[tuple[str, str | None]] = []

    async def stat(self, path=None, observations=None, *, columns=None, user_id=None) -> Result:  # type: ignore[override]
        self.reads.append(("stat", path))
        return await super().stat(path, observations, columns=columns, user_id=user_id)

    async def ls(self, path=None, observations=None, *, columns=None, user_id=None) -> Result:  # type: ignore[override]
        self.reads.append(("ls", path))
        return await super().ls(path, observations, columns=columns, user_id=user_id)


class ScopeSpyFS(EchoFS):
    """Echo mount recording the scope its public grep receives."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.scopes: list[tuple[str, ...]] = []

    async def grep(self, pattern: str, *, paths: tuple[str, ...] = (), **kwargs: Any) -> Result:  # type: ignore[override]
        self.scopes.append(tuple(paths))
        return await super().grep(pattern, paths=paths, **kwargs)
