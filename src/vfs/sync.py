"""The synchronous face of the kernel and its session, for callers without a loop.

``VirtualFileSystem`` owns one asyncio loop on one daemon thread and
forwards every verb of :class:`~vfs.base.AsyncVirtualFileSystem` through it,
so a notebook cell, a plain script or a pipeline worker calls a verb and
gets its ``Result`` back with no ``asyncio.run`` and no running-loop
error. ``Session`` does the same for :class:`~vfs.session.AsyncSession`.

    from vfs import VirtualFileSystem
    from vfs.storage.backends.memory import InMemoryStorage

    with VirtualFileSystem(storage=InMemoryStorage()) as fs:
        fs.write(path="/a.txt", content="x")
        result = fs.read("/a.txt")

Every twin has the original's exact parameters and returns what the
original returns; a management method's exception is raised unchanged.
The facade's loop is the only loop its storage ever sees, which is what
makes an asyncpg engine safe inside a notebook whose own loop is running.
A verb called on a thread whose own event loop is running blocks that
loop until it returns; the first such call on a facade says so once, as
a ``RuntimeWarning`` pointed at the caller's line, and is served.
"""

from __future__ import annotations

import asyncio
import sys
import threading
import warnings
from typing import TYPE_CHECKING, Any, Final, Literal

from vfs.base import AsyncVirtualFileSystem
from vfs.ops import GRAPH_DEPTH_DEFAULT, GRAPH_LIMIT_DEFAULT
from vfs.rerank import BM25Rerank
from vfs.results import ErrorKind, Result, classified
from vfs.session import CLOSED_SESSION_DETAIL, AsyncSession, closed_refusal

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Iterable, Sequence
    from concurrent.futures import Future
    from types import TracebackType

    from vfs.authority import Authority
    from vfs.base import Binding, EdgeLocation, Location, MountInfo
    from vfs.models import Edge, Entry, Observation
    from vfs.ops import CaseMode, GrepOutputMode, Op, TwoPathOperation
    from vfs.paths import ObjectKind
    from vfs.permissions import Permission, PermissionMap
    from vfs.rerank import Reranker
    from vfs.storage import StorageBackend
    from vfs.storage.grants import GrantLevel, Posture
    from vfs.storage.replace import EditOperation

LOOP_THREAD_NAME: Final = "vfs-sync-loop"
"""The name of every facade's loop thread, so a leak shows in ``threading.enumerate()``."""

LOOP_THREAD_DETAIL: Final = (
    "called from the facade's own loop thread; a callback running on the loop uses AsyncVirtualFileSystem"
)
"""The deadlock refusal: a call that would block the loop on a future the same loop must finish."""

CLOSED_DETAIL: Final = "the filesystem is closed"
"""The closed refusal, the same words the router mints after its own close."""

CLOSED_MANAGEMENT_DETAIL: Final = "the filesystem is closed; the loop thread has stopped"
"""The closed refusal for a management method, which raises by contract."""

FOREIGN_LOOP_WARNING: Final = (
    "VirtualFileSystem.{op} called on a thread whose event loop is running; the call blocks that loop until"
    " it returns. In a notebook cell that is expected and this is the one notice; inside async code use"
    " AsyncVirtualFileSystem."
)
"""The once-per-facade notice: the one mistake no type checker sees, named at the caller's line."""


# ---------------------------------------------------------------------------
# The filesystem twin
# ---------------------------------------------------------------------------


class VirtualFileSystem:
    """One kernel, one loop, one thread: the kernel's verbs as plain calls.

    Construct it with the router's own parameters, or :meth:`wrap` a router
    already built. Open it with ``with`` or call :meth:`close` yourself;
    closed is final, and closing stops the thread. Each call runs its task
    in a copy of the caller's context taken at submit time, so a context
    variable the caller set is visible to the verb, and the hop budget is
    per task and starts fresh for every call, as for a top-level ``await``.
    A verb called from the facade's own loop thread is refused with an
    ``invalid`` row rather than waited on, because that wait never ends.
    A verb called on a thread whose own loop is running is served and,
    once per facade, warned about, because it blocks that loop meanwhile.
    """

    __slots__ = ("_closed", "_fs", "_loop", "_thread", "_warned")

    def __init__(
        self,
        *,
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        storage: StorageBackend | None = None,
        permissions: Permission | PermissionMap = "read_write",
        deny_ops: Iterable[Op] = (),
        no_overlay: bool = False,
        hop_budget: int = 16,
        close_timeout: float = 10.0,
        rerankers: Iterable[Reranker] = (BM25Rerank(),),
        default_authority: Authority | None = None,
    ) -> None:
        # Construction binds nothing to a loop, so it runs here and a refused
        # argument raises the router's own error with no thread left behind.
        router = AsyncVirtualFileSystem(
            name=name,
            title=title,
            description=description,
            storage=storage,
            permissions=permissions,
            deny_ops=deny_ops,
            no_overlay=no_overlay,
            hop_budget=hop_budget,
            close_timeout=close_timeout,
            rerankers=rerankers,
            default_authority=default_authority,
        )
        self._attach(router)

    @classmethod
    def wrap(cls, fs: AsyncVirtualFileSystem) -> VirtualFileSystem:
        """The facade over a router the caller already built, and may already have awaited.

        Pinned on SQLite, whose driver tolerates a change of loop. Unproven
        on asyncpg, which binds an engine to the loop that first touched it:
        a router already touched on the notebook's loop is the hazard the
        constructor exists to avoid, so prefer constructing the facade.
        """
        facade = cls.__new__(cls)
        facade._attach(fs)
        return facade

    # -------------------------------------------------------------------
    # lifecycle
    # -------------------------------------------------------------------

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        """Cancel what is in flight, close the router on the loop, stop the loop, join the thread.

        Idempotent and final. The in-flight calls of other threads are
        cancelled and gathered on the loop before the router closes, so the
        engine never disposes a pool a verb is still drawing on; the loop
        thread then shuts itself down in its runner, so nothing here runs a
        loop on the caller's thread (which may be running a loop of its own).
        """
        self._refuse_loop_thread()
        if self._closed:
            return
        self._closed = True
        try:
            _wait(asyncio.run_coroutine_threadsafe(self._drain_and_close(), self._loop))
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join()

    def __enter__(self) -> VirtualFileSystem:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # -------------------------------------------------------------------
    # mount administration
    # -------------------------------------------------------------------

    def bind(
        self,
        storage: StorageBackend,
        path: str,
        *,
        permissions: Permission | PermissionMap | None = None,
        deny_ops: Iterable[Op] = (),
        no_overlay: bool = False,
        owned: bool = True,
    ) -> None:
        return self._await(
            "bind",
            self._fs.bind,
            storage,
            path,
            permissions=permissions,
            deny_ops=deny_ops,
            no_overlay=no_overlay,
            owned=owned,
        )

    def unbind(self, path: str) -> Binding:
        return self._await("unbind", self._fs.unbind, path)

    def add_mount(
        self,
        storage: StorageBackend,
        path: str | None = None,
        *,
        parents: bool = False,
        permissions: Permission | PermissionMap | None = None,
        deny_ops: Iterable[Op] = (),
        no_overlay: bool = False,
        owned: bool = True,
    ) -> None:
        return self._await(
            "add_mount",
            self._fs.add_mount,
            storage,
            path,
            parents=parents,
            permissions=permissions,
            deny_ops=deny_ops,
            no_overlay=no_overlay,
            owned=owned,
        )

    def remove_mount(self, path: str) -> None:
        return self._await("remove_mount", self._fs.remove_mount, path)

    def remount(
        self,
        path: str,
        *,
        permissions: Permission | PermissionMap | None = None,
        deny_ops: Iterable[Op] | None = None,
        no_overlay: bool | None = None,
        refresh_caps: bool = False,
    ) -> None:
        return self._await(
            "remount",
            self._fs.remount,
            path,
            permissions=permissions,
            deny_ops=deny_ops,
            no_overlay=no_overlay,
            refresh_caps=refresh_caps,
        )

    def mounts(self) -> tuple[MountInfo, ...]:
        return self._fs.mounts()

    def locate(self, path: str, *, exists: bool = False, authority: Authority | None = None) -> Location:
        return self._await("locate", self._fs.locate, path, exists=exists, authority=authority)

    def locate_edge(
        self, source: str, target: str, *, exists: bool = False, authority: Authority | None = None
    ) -> EdgeLocation:
        return self._await("locate_edge", self._fs.locate_edge, source, target, exists=exists, authority=authority)

    def session(self, authority: Authority) -> Session:
        """An authority-scoped twin of the router's session: the verbs without the identity argument."""
        return Session(self, authority)

    def capabilities(self) -> frozenset[str]:
        return self._fs.capabilities()

    # -------------------------------------------------------------------
    # reads
    # -------------------------------------------------------------------

    def read(
        self,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        columns: frozenset[str] | None = None,
        authority: Authority | None = None,
    ) -> Result:
        return self._result("read", self._fs.read, path, observations, columns=columns, authority=authority)

    def stat(
        self,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        columns: frozenset[str] | None = None,
        authority: Authority | None = None,
    ) -> Result:
        return self._result("stat", self._fs.stat, path, observations, columns=columns, authority=authority)

    def ls(
        self,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        columns: frozenset[str] | None = None,
        authority: Authority | None = None,
    ) -> Result:
        return self._result("ls", self._fs.ls, path, observations, columns=columns, authority=authority)

    def tree(
        self,
        path: str,
        max_depth: int | None = None,
        *,
        columns: frozenset[str] | None = None,
        authority: Authority | None = None,
    ) -> Result:
        return self._result("tree", self._fs.tree, path, max_depth, columns=columns, authority=authority)

    # -------------------------------------------------------------------
    # mutations
    # -------------------------------------------------------------------

    def write(
        self,
        entries: Sequence[Entry] | None = None,
        *,
        path: str | None = None,
        content: str | None = None,
        data: bytes | None = None,
        overwrite: bool = True,
        parents: bool = False,
        authority: Authority | None = None,
    ) -> Result:
        return self._result(
            "write",
            self._fs.write,
            entries,
            path=path,
            content=content,
            data=data,
            overwrite=overwrite,
            parents=parents,
            authority=authority,
        )

    def edit(
        self,
        path: str | None = None,
        old: str | None = None,
        new: str | None = None,
        edits: list[EditOperation] | None = None,
        observations: list[Observation] | None = None,
        replace_all: bool = False,
        *,
        authority: Authority | None = None,
    ) -> Result:
        return self._result(
            "edit", self._fs.edit, path, old, new, edits, observations, replace_all, authority=authority
        )

    def delete(
        self,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        cascade: bool = True,
        authority: Authority | None = None,
    ) -> Result:
        return self._result("delete", self._fs.delete, path, observations, cascade=cascade, authority=authority)

    def restore(
        self,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        authority: Authority | None = None,
    ) -> Result:
        return self._result("restore", self._fs.restore, path, observations, authority=authority)

    def sweep(
        self,
        path: str = "/.vfs/trash",
        *,
        authority: Authority | None = None,
    ) -> Result:
        return self._result("sweep", self._fs.sweep, path, authority=authority)

    def mkdir(
        self,
        path: str,
        *,
        parents: bool = False,
        exist_ok: bool = False,
        authority: Authority | None = None,
    ) -> Result:
        return self._result("mkdir", self._fs.mkdir, path, parents=parents, exist_ok=exist_ok, authority=authority)

    def mkedge(
        self,
        edges: Sequence[Edge] | None = None,
        *,
        source: str | None = None,
        target: str | None = None,
        edge_type: str | None = None,
        provenance: Literal["user", "agent", "system"] = "system",
        authority: Authority | None = None,
    ) -> Result:
        return self._result(
            "mkedge",
            self._fs.mkedge,
            edges,
            source=source,
            target=target,
            edge_type=edge_type,
            provenance=provenance,
            authority=authority,
        )

    def rmedge(
        self,
        edges: Sequence[Edge] | None = None,
        *,
        source: str | None = None,
        target: str | None = None,
        edge_type: str | None = None,
        authority: Authority | None = None,
    ) -> Result:
        return self._result(
            "rmedge", self._fs.rmedge, edges, source=source, target=target, edge_type=edge_type, authority=authority
        )

    def move(
        self,
        src: str | None = None,
        dest: str | None = None,
        moves: Sequence[TwoPathOperation | tuple[str, str]] | None = None,
        *,
        authority: Authority | None = None,
    ) -> Result:
        return self._result("move", self._fs.move, src, dest, moves, authority=authority)

    def copy(
        self,
        src: str | None = None,
        dest: str | None = None,
        copies: Sequence[TwoPathOperation | tuple[str, str]] | None = None,
        *,
        authority: Authority | None = None,
    ) -> Result:
        return self._result("copy", self._fs.copy, src, dest, copies, authority=authority)

    # -------------------------------------------------------------------
    # search, graph, execution
    # -------------------------------------------------------------------

    def glob(
        self,
        pattern: str,
        *,
        paths: tuple[str, ...] = (),
        observations: list[Observation] | None = None,
        ext: tuple[str, ...] = (),
        ext_not: tuple[str, ...] = (),
        globs_not: tuple[str, ...] = (),
        kind: ObjectKind | None = None,
        max_count: int | None = None,
        columns: frozenset[str] | None = None,
        authority: Authority | None = None,
    ) -> Result:
        return self._result(
            "glob",
            self._fs.glob,
            pattern,
            paths=paths,
            observations=observations,
            ext=ext,
            ext_not=ext_not,
            globs_not=globs_not,
            kind=kind,
            max_count=max_count,
            columns=columns,
            authority=authority,
        )

    def grep(
        self,
        pattern: str,
        *,
        paths: tuple[str, ...] = (),
        observations: list[Observation] | None = None,
        ext: tuple[str, ...] = (),
        ext_not: tuple[str, ...] = (),
        globs: tuple[str, ...] = (),
        globs_not: tuple[str, ...] = (),
        case_mode: CaseMode = "sensitive",
        fixed_strings: bool = False,
        word_regexp: bool = False,
        invert_match: bool = False,
        before_context: int = 0,
        after_context: int = 0,
        output_mode: GrepOutputMode = "lines",
        max_count: int | None = None,
        allow_scan: bool = False,
        columns: frozenset[str] | None = None,
        authority: Authority | None = None,
    ) -> Result:
        return self._result(
            "grep",
            self._fs.grep,
            pattern,
            paths=paths,
            observations=observations,
            ext=ext,
            ext_not=ext_not,
            globs=globs,
            globs_not=globs_not,
            case_mode=case_mode,
            fixed_strings=fixed_strings,
            word_regexp=word_regexp,
            invert_match=invert_match,
            before_context=before_context,
            after_context=after_context,
            output_mode=output_mode,
            max_count=max_count,
            allow_scan=allow_scan,
            columns=columns,
            authority=authority,
        )

    def glean(
        self,
        query: str,
        *,
        limit: int = 10,
        paths: tuple[str, ...] = (),
        observations: list[Observation] | None = None,
        ext: tuple[str, ...] = (),
        ext_not: tuple[str, ...] = (),
        globs: tuple[str, ...] = (),
        globs_not: tuple[str, ...] = (),
        columns: frozenset[str] | None = None,
        authority: Authority | None = None,
    ) -> Result:
        return self._result(
            "glean",
            self._fs.glean,
            query,
            limit=limit,
            paths=paths,
            observations=observations,
            ext=ext,
            ext_not=ext_not,
            globs=globs,
            globs_not=globs_not,
            columns=columns,
            authority=authority,
        )

    def graph(
        self,
        method: str,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        depth: int | None = GRAPH_DEPTH_DEFAULT,
        edge_types: tuple[str, ...] = (),
        edge_types_not: tuple[str, ...] = (),
        minimal: bool = False,
        limit: int | None = GRAPH_LIMIT_DEFAULT,
        columns: frozenset[str] | None = None,
        authority: Authority | None = None,
    ) -> Result:
        return self._result(
            "graph",
            self._fs.graph,
            method,
            path,
            observations,
            depth=depth,
            edge_types=edge_types,
            edge_types_not=edge_types_not,
            minimal=minimal,
            limit=limit,
            columns=columns,
            authority=authority,
        )

    def run(
        self,
        path: str,
        *,
        arguments: dict[str, Any] | None = None,
        authority: Authority | None = None,
    ) -> Result:
        return self._result("run", self._fs.run, path, arguments=arguments, authority=authority)

    # -------------------------------------------------------------------
    # grants
    # -------------------------------------------------------------------

    def grant(
        self,
        path: str,
        principal: str,
        level: GrantLevel,
        *,
        authority: Authority | None = None,
    ) -> Result:
        return self._result("grant", self._fs.grant, path, principal, level, authority=authority)

    def revoke(self, path: str, principal: str, *, authority: Authority | None = None) -> Result:
        return self._result("revoke", self._fs.revoke, path, principal, authority=authority)

    def grants(self, path: str, *, authority: Authority | None = None) -> Result:
        return self._result("grants", self._fs.grants, path, authority=authority)

    def posture(self, path: str, posture: Posture, *, authority: Authority | None = None) -> Result:
        return self._result("posture", self._fs.posture, path, posture, authority=authority)

    def add_member(
        self,
        group: str,
        member: str,
        *,
        path: str = "/",
        authority: Authority | None = None,
    ) -> Result:
        return self._result("add_member", self._fs.add_member, group, member, path=path, authority=authority)

    def remove_member(
        self,
        group: str,
        member: str,
        *,
        path: str = "/",
        authority: Authority | None = None,
    ) -> Result:
        return self._result("remove_member", self._fs.remove_member, group, member, path=path, authority=authority)

    # -------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------

    def _attach(self, fs: AsyncVirtualFileSystem) -> None:
        """Take the router and start the loop thread that will serve it."""
        self._fs = fs
        self._closed = False
        self._warned = False
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._serve, name=LOOP_THREAD_NAME, daemon=True)
        self._thread.start()

    async def _drain_and_close(self) -> None:
        """On the loop: cancel every other task and wait for it, then close the router with nothing in flight."""
        current = asyncio.current_task()
        others = [task for task in asyncio.all_tasks() if task is not current]
        for task in others:
            task.cancel()
        await asyncio.gather(*others, return_exceptions=True)
        await self._fs.close()

    def _serve(self) -> None:
        """The loop thread: run until stopped, then shut the loop down here, never on a caller's thread."""
        loop = self._loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_forever()
        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.run_until_complete(loop.shutdown_default_executor())
            loop.close()

    def _result(self, op: Op, call: Callable[..., Coroutine[Any, Any, Result]], *args: Any, **kwargs: Any) -> Result:
        """The verb hop: refuse as a classified row, else run the coroutine on the loop and wait."""
        if self._closed:
            return Result(ops=(op,), errors=[classified(ErrorKind.backend_unavailable, detail=CLOSED_DETAIL)])
        if threading.get_ident() == self._thread.ident:
            return Result(ops=(op,), errors=[classified(ErrorKind.invalid, detail=LOOP_THREAD_DETAIL)])
        self._warn_if_blocking_a_foreign_loop(op)
        return self._submit(call(*args, **kwargs))

    def _await(self, name: str, call: Callable[..., Coroutine[Any, Any, Any]], *args: Any, **kwargs: Any) -> Any:
        """The management hop: refuse by raising, else run the coroutine on the loop and wait."""
        if self._closed:
            raise RuntimeError(CLOSED_MANAGEMENT_DETAIL)
        self._refuse_loop_thread()
        self._warn_if_blocking_a_foreign_loop(name)
        return self._submit(call(*args, **kwargs))

    def _refuse_loop_thread(self) -> None:
        if threading.get_ident() == self._thread.ident:
            raise RuntimeError(LOOP_THREAD_DETAIL)

    def _warn_if_blocking_a_foreign_loop(self, op: str) -> None:
        """After the own-thread check, so any running loop seen here is one this call will block."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._warned:
            return
        self._warned = True
        warnings.warn(FOREIGN_LOOP_WARNING.format(op=op), RuntimeWarning, stacklevel=_caller_stacklevel())

    def _submit(self, coroutine: Coroutine[Any, Any, Any]) -> Any:
        """Run one coroutine on the loop and block; an escaping exception cancels what is in flight."""
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        try:
            return _wait(future)
        except BaseException:
            future.cancel()
            raise


# ---------------------------------------------------------------------------
# The session twin
# ---------------------------------------------------------------------------


class Session:
    """One authority, one facade, one lifecycle: the session's verbs as plain calls.

    Wraps a :class:`~vfs.session.AsyncSession` over the facade's kernel, so the
    closed fact and everything a session comes to hold live in one place;
    the twin forwards each verb through the facade's loop. Open it with
    ``with`` or call :meth:`close`; closed is final.
    """

    __slots__ = ("_facade", "_session")

    def __init__(self, fs: VirtualFileSystem, authority: Authority) -> None:
        self._facade = fs
        self._session = AsyncSession(fs._fs, authority)

    @property
    def authority(self) -> Authority:
        return self._session.authority

    @property
    def closed(self) -> bool:
        return self._session.closed

    def close(self) -> None:
        """Close the session — idempotent, and final; no hop, the flag is the wrapped session's."""
        self._session._close_now()

    def __enter__(self) -> Session:
        if self._session.closed:
            raise ValueError(CLOSED_SESSION_DETAIL)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # -------------------------------------------------------------------
    # reads
    # -------------------------------------------------------------------

    def read(
        self,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        columns: frozenset[str] | None = None,
    ) -> Result:
        return self._result("read", self._session.read, path, observations, columns=columns)

    def stat(
        self,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        columns: frozenset[str] | None = None,
    ) -> Result:
        return self._result("stat", self._session.stat, path, observations, columns=columns)

    def ls(
        self,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        columns: frozenset[str] | None = None,
    ) -> Result:
        return self._result("ls", self._session.ls, path, observations, columns=columns)

    def tree(
        self,
        path: str,
        max_depth: int | None = None,
        *,
        columns: frozenset[str] | None = None,
    ) -> Result:
        return self._result("tree", self._session.tree, path, max_depth, columns=columns)

    # -------------------------------------------------------------------
    # mutations
    # -------------------------------------------------------------------

    def write(
        self,
        entries: Sequence[Entry] | None = None,
        *,
        path: str | None = None,
        content: str | None = None,
        data: bytes | None = None,
        overwrite: bool = True,
        parents: bool = False,
    ) -> Result:
        return self._result(
            "write",
            self._session.write,
            entries,
            path=path,
            content=content,
            data=data,
            overwrite=overwrite,
            parents=parents,
        )

    def edit(
        self,
        path: str | None = None,
        old: str | None = None,
        new: str | None = None,
        edits: list[EditOperation] | None = None,
        observations: list[Observation] | None = None,
        replace_all: bool = False,
    ) -> Result:
        return self._result("edit", self._session.edit, path, old, new, edits, observations, replace_all)

    def delete(
        self,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        cascade: bool = True,
    ) -> Result:
        return self._result("delete", self._session.delete, path, observations, cascade=cascade)

    def restore(
        self,
        path: str | None = None,
        observations: list[Observation] | None = None,
    ) -> Result:
        return self._result("restore", self._session.restore, path, observations)

    def sweep(self, path: str = "/.vfs/trash") -> Result:
        return self._result("sweep", self._session.sweep, path)

    def mkdir(self, path: str, *, parents: bool = False, exist_ok: bool = False) -> Result:
        return self._result("mkdir", self._session.mkdir, path, parents=parents, exist_ok=exist_ok)

    def mkedge(
        self,
        edges: Sequence[Edge] | None = None,
        *,
        source: str | None = None,
        target: str | None = None,
        edge_type: str | None = None,
        provenance: Literal["user", "agent", "system"] = "system",
    ) -> Result:
        return self._result(
            "mkedge",
            self._session.mkedge,
            edges,
            source=source,
            target=target,
            edge_type=edge_type,
            provenance=provenance,
        )

    def rmedge(
        self,
        edges: Sequence[Edge] | None = None,
        *,
        source: str | None = None,
        target: str | None = None,
        edge_type: str | None = None,
    ) -> Result:
        return self._result("rmedge", self._session.rmedge, edges, source=source, target=target, edge_type=edge_type)

    def move(
        self,
        src: str | None = None,
        dest: str | None = None,
        moves: Sequence[TwoPathOperation | tuple[str, str]] | None = None,
    ) -> Result:
        return self._result("move", self._session.move, src, dest, moves)

    def copy(
        self,
        src: str | None = None,
        dest: str | None = None,
        copies: Sequence[TwoPathOperation | tuple[str, str]] | None = None,
    ) -> Result:
        return self._result("copy", self._session.copy, src, dest, copies)

    # -------------------------------------------------------------------
    # search, graph, execution
    # -------------------------------------------------------------------

    def glob(
        self,
        pattern: str,
        *,
        paths: tuple[str, ...] = (),
        observations: list[Observation] | None = None,
        ext: tuple[str, ...] = (),
        ext_not: tuple[str, ...] = (),
        globs_not: tuple[str, ...] = (),
        kind: ObjectKind | None = None,
        max_count: int | None = None,
        columns: frozenset[str] | None = None,
    ) -> Result:
        return self._result(
            "glob",
            self._session.glob,
            pattern,
            paths=paths,
            observations=observations,
            ext=ext,
            ext_not=ext_not,
            globs_not=globs_not,
            kind=kind,
            max_count=max_count,
            columns=columns,
        )

    def grep(
        self,
        pattern: str,
        *,
        paths: tuple[str, ...] = (),
        observations: list[Observation] | None = None,
        ext: tuple[str, ...] = (),
        ext_not: tuple[str, ...] = (),
        globs: tuple[str, ...] = (),
        globs_not: tuple[str, ...] = (),
        case_mode: CaseMode = "sensitive",
        fixed_strings: bool = False,
        word_regexp: bool = False,
        invert_match: bool = False,
        before_context: int = 0,
        after_context: int = 0,
        output_mode: GrepOutputMode = "lines",
        max_count: int | None = None,
        allow_scan: bool = False,
        columns: frozenset[str] | None = None,
    ) -> Result:
        return self._result(
            "grep",
            self._session.grep,
            pattern,
            paths=paths,
            observations=observations,
            ext=ext,
            ext_not=ext_not,
            globs=globs,
            globs_not=globs_not,
            case_mode=case_mode,
            fixed_strings=fixed_strings,
            word_regexp=word_regexp,
            invert_match=invert_match,
            before_context=before_context,
            after_context=after_context,
            output_mode=output_mode,
            max_count=max_count,
            allow_scan=allow_scan,
            columns=columns,
        )

    def glean(
        self,
        query: str,
        *,
        limit: int = 10,
        paths: tuple[str, ...] = (),
        observations: list[Observation] | None = None,
        ext: tuple[str, ...] = (),
        ext_not: tuple[str, ...] = (),
        globs: tuple[str, ...] = (),
        globs_not: tuple[str, ...] = (),
        columns: frozenset[str] | None = None,
    ) -> Result:
        return self._result(
            "glean",
            self._session.glean,
            query,
            limit=limit,
            paths=paths,
            observations=observations,
            ext=ext,
            ext_not=ext_not,
            globs=globs,
            globs_not=globs_not,
            columns=columns,
        )

    def graph(
        self,
        method: str,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        depth: int | None = GRAPH_DEPTH_DEFAULT,
        edge_types: tuple[str, ...] = (),
        edge_types_not: tuple[str, ...] = (),
        minimal: bool = False,
        limit: int | None = GRAPH_LIMIT_DEFAULT,
        columns: frozenset[str] | None = None,
    ) -> Result:
        return self._result(
            "graph",
            self._session.graph,
            method,
            path,
            observations,
            depth=depth,
            edge_types=edge_types,
            edge_types_not=edge_types_not,
            minimal=minimal,
            limit=limit,
            columns=columns,
        )

    def run(self, path: str, *, arguments: dict[str, Any] | None = None) -> Result:
        return self._result("run", self._session.run, path, arguments=arguments)

    # -------------------------------------------------------------------
    # grants
    # -------------------------------------------------------------------

    def grant(self, path: str, principal: str, level: GrantLevel) -> Result:
        return self._result("grant", self._session.grant, path, principal, level)

    def revoke(self, path: str, principal: str) -> Result:
        return self._result("revoke", self._session.revoke, path, principal)

    def grants(self, path: str) -> Result:
        return self._result("grants", self._session.grants, path)

    def posture(self, path: str, posture: Posture) -> Result:
        return self._result("posture", self._session.posture, path, posture)

    def add_member(self, group: str, member: str, *, path: str = "/") -> Result:
        return self._result("add_member", self._session.add_member, group, member, path=path)

    def remove_member(self, group: str, member: str, *, path: str = "/") -> Result:
        return self._result("remove_member", self._session.remove_member, group, member, path=path)

    # -------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------

    def _result(self, op: Op, call: Callable[..., Coroutine[Any, Any, Result]], *args: Any, **kwargs: Any) -> Result:
        """The closed fact first, then the facade's own hop."""
        if self._session.closed:
            return closed_refusal(op)
        return self._facade._result(op, call, *args, **kwargs)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _wait(future: Future[Any]) -> Any:
    """Block the calling thread on the loop's answer; the one seam an interrupt test replaces."""
    return future.result()


def _caller_stacklevel() -> int:
    """The ``stacklevel`` that names the first frame outside this module: the caller's own line."""
    depth = 1
    frame = sys._getframe(1)
    while frame is not None and frame.f_globals.get("__name__") == __name__:
        depth += 1
        frame = frame.f_back
    return depth
