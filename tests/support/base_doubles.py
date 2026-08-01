"""Shared test doubles for the base router test files.

Backend fakes satisfy the family protocols from ``vfs.storage`` (plus the
required identity members); the few FS doubles subclass
``vfs.base.VirtualFileSystem`` only to pre-wire a backend.  Mount-table
behavior is steered entirely through storage doubles — a mounted thing is
a storage, never a router.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from vfs.base import VirtualFileSystem
from vfs.models import Entry, Observation
from vfs.paths import ObjectKind, Path
from vfs.results import Result, ResultError, VFSErrorKind
from vfs.storage import TransportError, storage_ops

if TYPE_CHECKING:
    from vfs.ops import Op


def _failed(op: str, kind: VFSErrorKind, message: str, path: Path | None = None) -> Result:
    """A backend-composed failure — doubles have no router ``_error`` helper."""
    return Result(ops=(op,), errors=[ResultError(kind=kind, message=message, path=path)])


class RecorderStorage:
    """Full-family storage double: records every dispatch, answers success.

    The base backend double — one method per op, each two lines, so the
    object satisfies every family protocol.  Subclasses override an op's
    behavior or ``_answer`` for a different canned reply.  *caps* narrows
    the declared capability set below the (full) derived one — the
    declared-policy knob for read-only-mount and skip tests.
    """

    def __init__(
        self,
        *,
        name: str = "recorder",
        description: str = "Recorder storage double",
        caps: frozenset[Op] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self._caps = caps
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def capabilities(self) -> frozenset[Op]:
        return self._caps if self._caps is not None else storage_ops(self)

    def _answer(self, op: str, kwargs: dict[str, Any]) -> Result:
        self.calls.append((op, kwargs))
        return Result(ops=(op,), observations=[])

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

    async def restore(self, *, user_id: str | None = None, **kwargs: Any) -> Result:
        return self._answer("restore", kwargs)

    async def sweep(self, *, user_id: str | None = None, **kwargs: Any) -> Result:
        return self._answer("sweep", kwargs)

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
    """The minimum viable backend — the read family plus the identity members."""

    name = "read-family"
    description = "Read-family-only storage double"

    def capabilities(self) -> frozenset[Op]:
        return storage_ops(self)

    async def read(self, **kwargs: Any) -> Result:
        return Result(ops=("read",), observations=[])

    async def stat(self, **kwargs: Any) -> Result:
        return Result(ops=("stat",), observations=[])

    async def ls(self, **kwargs: Any) -> Result:
        return Result(ops=("ls",), observations=[])

    async def tree(self, **kwargs: Any) -> Result:
        return Result(ops=("tree",), observations=[])


class BindableStorage(RecorderStorage):
    """Recorder whose stat/ls answer the bind-site probe: empty directory.

    ``bind`` proves the site is an existing empty directory before it
    commits; this double says yes for every path, so mount tests can bind
    without arranging stored rows first.
    """

    async def stat(self, *, path: Path | None = None, user_id: str | None = None, **kwargs: Any) -> Result:
        self.calls.append(("stat", {"path": path, **kwargs}))
        target = path if path is not None else Path("/")
        return Result(ops=("stat",), observations=[Observation(path=target, kind="directory")])

    async def ls(self, *, path: Path | None = None, user_id: str | None = None, **kwargs: Any) -> Result:
        self.calls.append(("ls", {"path": path, **kwargs}))
        return Result(ops=("ls",), observations=[])


class CapCountingStorage(BindableStorage):
    """Bindable recorder counting ``capabilities()`` calls.

    ``.calls`` records op dispatches only, so the no-storage-I/O criteria
    need this separate spy to prove the snapshot is never re-taken.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.capabilities_calls = 0

    def capabilities(self) -> frozenset[Op]:
        self.capabilities_calls += 1
        return super().capabilities()


class SuspendingProbeStorage(BindableStorage):
    """Bindable parent whose probe reads suspend once per call.

    The suspension is what opens the race window: ``bind``'s site probe
    yields to the loop mid-sequence, so a gathered read can land in the
    gap an unbind+bind pair leaves open — the contrast that proves
    ``remount`` has no such gap.
    """

    async def stat(self, **kwargs: Any) -> Result:
        await asyncio.sleep(0)
        return await super().stat(**kwargs)

    async def ls(self, **kwargs: Any) -> Result:
        await asyncio.sleep(0)
        return await super().ls(**kwargs)


class DictStorage(RecorderStorage):
    """Minimal storage backend: a path -> kind dict behind stat, ls, and mkdir.

    ``mkdir`` applies the POSIX site rule over the dict — the site must be
    free and every existing ancestor a directory — so mount-site tests can
    steer ``add_mount`` and ``bind`` through storage contents.  ``ls``
    answers the bind probe's emptiness check from the same dict.
    """

    def __init__(self, entries: dict[str, ObjectKind]) -> None:
        super().__init__(name="dict", description="Dict storage double")
        self._entries = entries

    async def mkdir(self, *, path: Path | None = None, user_id: str | None = None, **kwargs: Any) -> Result:
        assert path is not None
        self.calls.append(("mkdir", {"path": path, **kwargs}))
        if self._entries.get(str(path)) == "directory" and kwargs.get("exist_ok"):
            return Result(ops=("mkdir",), observations=[Observation(path=path, kind="directory")])
        occupied = path in self._entries
        node = path.parent_dir
        while not occupied and node != "/":
            occupied = self._entries.get(node, "directory") != "directory"
            node = node.parent_dir
        if occupied:
            return _failed("mkdir", VFSErrorKind.exists, "storage contents conflict with that path", path=path)
        self._entries[str(path)] = "directory"
        return Result(ops=("mkdir",), observations=[Observation(path=path, kind="directory", status="created")])

    async def ls(
        self,
        *,
        path: Path | None = None,
        user_id: str | None = None,
        **kwargs: Any,
    ) -> Result:
        self.calls.append(("ls", {"path": path, **kwargs}))
        base = str(path) if path is not None else "/"
        prefix = base.rstrip("/") + "/"
        rows = [
            Observation(path=Path(p), kind=kind)
            for p, kind in self._entries.items()
            if p.startswith(prefix) and "/" not in p[len(prefix) :]
        ]
        return Result(ops=("ls",), observations=rows)

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
        return Result(ops=("stat",), observations=rows)


class DictStorageFS(VirtualFileSystem):
    """Node holding a :class:`DictStorage` root entry."""

    def __init__(self, entries: dict[str, ObjectKind], **kwargs: Any) -> None:
        super().__init__(storage=DictStorage(entries), **kwargs)


class SpyCloseStorage(BindableStorage):
    """Backend counting how many times it was closed."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.close_count = 0

    async def close(self) -> None:
        self.close_count += 1


class BadCloseStorage(SpyCloseStorage):
    """Backend whose close always fails."""

    async def close(self) -> None:
        self.close_count += 1
        raise RuntimeError("boom")


class GatedCloseStorage(SpyCloseStorage):
    """Backend whose close parks on an event — a dispose the test can hold open."""

    def __init__(self, gate: asyncio.Event, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._gate = gate

    async def close(self) -> None:
        await self._gate.wait()
        await super().close()


class TransportFailStorage(RecorderStorage):
    """Wire-backend double whose every op raises ``TransportError`` — a dead peer."""

    def _answer(self, op: str, kwargs: dict[str, Any]) -> Result:
        self.calls.append((op, kwargs))
        msg = "peer is gone"
        raise TransportError(msg)


class SuspendingStorage(RecorderStorage):
    """Backend whose mkdir suspends, like a real DB round-trip.

    Every site accepts — the point is the suspension, which is what opens
    the race window the mount lock closes.  An optional *gate* holds the
    mkdir open until the test releases it.
    """

    def __init__(self, gate: asyncio.Event | None = None) -> None:
        super().__init__(name="suspending", description="Suspending storage double")
        self._gate = gate

    async def mkdir(self, *, user_id: str | None = None, **kwargs: Any) -> Result:
        if self._gate is not None:
            await self._gate.wait()
        else:
            await asyncio.sleep(0)
        return self._answer("mkdir", kwargs)


class SuspendingStorageFS(VirtualFileSystem):
    """Node holding a :class:`SuspendingStorage` backend."""

    def __init__(self, *, gate: asyncio.Event | None = None, **kwargs: Any) -> None:
        super().__init__(storage=SuspendingStorage(gate), **kwargs)


class RunnerStorage(RecorderStorage):
    """Tool-catalog double: the read family plus ``run``, recording calls.

    The generic-MCP-mount shape — declared capabilities pin the honest set
    (reads + run) unless *caps* narrows it further.
    """

    def __init__(self, *, caps: frozenset[Op] | None = None, **kwargs: Any) -> None:
        wanted: frozenset[Op] = caps if caps is not None else frozenset({"read", "stat", "ls", "tree", "run"})
        super().__init__(name=kwargs.pop("name", "runner"), caps=wanted, **kwargs)

    async def read(self, *, path: Path | None = None, user_id: str | None = None, **kwargs: Any) -> Result:
        self.calls.append(("read", {"path": path, **kwargs}))
        target = path if path is not None else Path("/")
        return Result(ops=("read",), observations=[Observation(path=target, kind="directory")])

    async def run(
        self,
        *,
        path: Path | None = None,
        arguments: dict[str, Any] | None = None,
        user_id: str | None = None,
        **kwargs: Any,
    ) -> Result:
        assert path is not None
        self.calls.append(("run", {"path": path, "arguments": arguments}))
        return Result(ops=("run",), observations=[Observation(path=path, kind="directory")])


class EchoStorage(RecorderStorage):
    """Recorder whose ops answer with one observation at a fixed local path."""

    def __init__(self, echo_path: str = "/hit.md", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._echo_path = echo_path

    def _answer(self, op: str, kwargs: dict[str, Any]) -> Result:
        self.calls.append((op, kwargs))
        return Result(ops=(op,), observations=[Observation(path=Path(self._echo_path))])


class BindableEchoStorage(EchoStorage, BindableStorage):
    """Echo whose stat answers the bind probe — hosts nested mounts in tests."""


class ScopeSpyStorage(EchoStorage):
    """Echo backend recording the scope its grep receives."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.scopes: list[tuple[str, ...]] = []

    async def grep(self, *, paths: tuple[Path, ...] = (), user_id: str | None = None, **kwargs: Any) -> Result:
        self.scopes.append(tuple(str(p) for p in paths))
        return self._answer("grep", {"paths": paths, **kwargs})


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


def _mutate(fs: VirtualFileSystem, op: str, base: str):
    """Invoke the mutating *op* against targets under *base* (no trailing slash)."""
    calls = {
        "write": lambda: fs.write(path=f"{base}/f.txt", content="x"),
        "edit": lambda: fs.edit(path=f"{base}/f.txt", old="a", new="b"),
        "delete": lambda: fs.delete(path=f"{base}/f.txt"),
        "restore": lambda: fs.restore(path=f"{base}/f.txt"),
        "sweep": lambda: fs.sweep(f"{base}/.vfs/trash"),
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
        "restore": lambda: fs.restore(path=target),
        "sweep": lambda: fs.sweep(target),
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
        return Result(ops=(op,), observations=rows)


class SlowWriteStorage(RecorderStorage):
    """Backend whose write is slow and logged — for settle-order proof."""

    def __init__(self) -> None:
        super().__init__(name="slow-write")
        self.write_log: list[str] = []

    async def write(self, *, entries: list[Entry] | None = None, user_id: str | None = None, **_: Any) -> Result:
        await asyncio.sleep(0.02)
        rows = []
        for entry in entries or []:
            self.write_log.append(entry.path)
            rows.append(Observation(path=entry.path, kind="file", status="created"))
        return Result(ops=("write",), observations=rows)


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

    def __init__(self, answers: dict[str, Result] | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.answers = answers or {}

    def _answer(self, op: str, kwargs: dict[str, Any]) -> Result:
        self.calls.append((op, kwargs))
        return self.answers.get(op, Result(ops=(op,), observations=[]))


class CannedFS(RecorderFS):
    """Node over a :class:`CannedStorage` root entry."""

    def __init__(self, answers: dict[str, Result] | None = None, **kwargs: Any) -> None:
        super().__init__(storage=CannedStorage(answers), **kwargs)
