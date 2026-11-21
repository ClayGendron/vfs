"""The synchronous twin of :class:`~vfs.session.AsyncSession`: one authority's verbs as plain calls.

A :class:`~vfs.sync.VirtualFileSystem` opens it with ``open_session``,
and each verb goes through the facade's own loop thread, as the facade's
own verbs do. The twin has the session's exact parameters, without the
identity argument the session already holds.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from vfs.ops import TRAVERSE_DEPTH_DEFAULT, TRAVERSE_LIMIT_DEFAULT
from vfs.session import CLOSED_SESSION_DETAIL, AsyncSession, closed_refusal

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Iterable, Mapping, Sequence
    from types import TracebackType

    from vfs.authority import Authority
    from vfs.models import Edge, Entry, Observation
    from vfs.ops import CaseMode, GrepOutputMode, Op, TwoPathOperation
    from vfs.paths import ObjectKind
    from vfs.results import Result
    from vfs.storage.grants import GrantLevel, Posture
    from vfs.storage.replace import EditOperation
    from vfs.sync import VirtualFileSystem

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
        after: str | None = None,
        limit: int | None = None,
        columns: frozenset[str] | None = None,
    ) -> Result:
        return self._result("ls", self._session.ls, path, observations, after=after, limit=limit, columns=columns)

    def tree(
        self,
        path: str,
        max_depth: int | None = None,
        *,
        after: str | None = None,
        limit: int | None = None,
        columns: frozenset[str] | None = None,
    ) -> Result:
        return self._result("tree", self._session.tree, path, max_depth, after=after, limit=limit, columns=columns)

    # -------------------------------------------------------------------
    # mutations
    # -------------------------------------------------------------------

    def write(
        self,
        entries: Iterable[Entry] | None = None,
        *,
        path: str | None = None,
        content: str | None = None,
        data: bytes | None = None,
        if_version: int | None = None,
        if_versions: Mapping[str, int] | None = None,
        if_absent: bool = False,
        append: bool = False,
        parents: bool = False,
    ) -> Result:
        return self._result(
            "write",
            self._session.write,
            entries,
            path=path,
            content=content,
            data=data,
            if_version=if_version,
            if_versions=if_versions,
            if_absent=if_absent,
            append=append,
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
    # find, execution
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
        after: str | None = None,
        limit: int | None = None,
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
            after=after,
            limit=limit,
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

    def search(
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
            "search",
            self._session.search,
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

    def traverse(
        self,
        method: str,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        depth: int | None = TRAVERSE_DEPTH_DEFAULT,
        edge_types: tuple[str, ...] = (),
        edge_types_not: tuple[str, ...] = (),
        minimal: bool = False,
        limit: int | None = TRAVERSE_LIMIT_DEFAULT,
        columns: frozenset[str] | None = None,
    ) -> Result:
        return self._result(
            "traverse",
            self._session.traverse,
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

    def set_posture(self, path: str, posture: Posture) -> Result:
        return self._result("set_posture", self._session.set_posture, path, posture)

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
