"""Session — an authority-scoped facade over one ``VirtualFileSystem``.

A session holds exactly one :class:`~vfs.authority.Authority` and its own
lifecycle, nothing more. Every verb delegates into the router's ordinary
funnel with ``authority=`` filled in, so a session-mediated call and the
direct call with the same authority return the same result — there is no
second dispatch path. The session is sugar; the funnel is the gate.

    async with vfs.session(Authority.of(Principal("alice"))) as s:
        result = await s.read("/reports/q2.md")      # no identity argument

Closed is final: a verb on a closed session refuses with a structured
error, and the session never reopens.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from vfs.results import Result, ResultError, VFSErrorKind

if TYPE_CHECKING:
    from collections.abc import Sequence
    from types import TracebackType

    from vfs.authority import Authority
    from vfs.base import VirtualFileSystem
    from vfs.models import Edge, Entry, Observation
    from vfs.ops import CaseMode, GrepOutputMode, Op, TwoPathOperation
    from vfs.paths import ObjectKind
    from vfs.storage.grants import GrantLevel, Posture
    from vfs.storage.replace import EditOperation


class Session:
    """One authority, one filesystem, one lifecycle.

    Open it as an async context manager or call :meth:`close` yourself;
    either way a closed session stays closed. The held authority is a
    value — rights are re-derived by the funnel on every call, never
    cached here.
    """

    __slots__ = ("_authority", "_closed", "_fs")

    def __init__(self, fs: VirtualFileSystem, authority: Authority) -> None:
        self._fs = fs
        self._authority = authority
        self._closed = False

    @property
    def authority(self) -> Authority:
        return self._authority

    @property
    def closed(self) -> bool:
        return self._closed

    async def close(self) -> None:
        """Close the session — idempotent, and final."""
        self._closed = True

    async def __aenter__(self) -> Session:
        if self._closed:
            msg = "the session is closed and cannot reopen; open a new one"
            raise ValueError(msg)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    # -------------------------------------------------------------------
    # reads
    # -------------------------------------------------------------------

    async def read(
        self,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        columns: frozenset[str] | None = None,
    ) -> Result:
        if (refusal := self._refuse_closed("read")) is not None:
            return refusal
        return await self._fs.read(path, observations, columns=columns, authority=self._authority)

    async def stat(
        self,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        columns: frozenset[str] | None = None,
    ) -> Result:
        if (refusal := self._refuse_closed("stat")) is not None:
            return refusal
        return await self._fs.stat(path, observations, columns=columns, authority=self._authority)

    async def ls(
        self,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        columns: frozenset[str] | None = None,
    ) -> Result:
        if (refusal := self._refuse_closed("ls")) is not None:
            return refusal
        return await self._fs.ls(path, observations, columns=columns, authority=self._authority)

    async def tree(
        self,
        path: str,
        max_depth: int | None = None,
        *,
        columns: frozenset[str] | None = None,
    ) -> Result:
        if (refusal := self._refuse_closed("tree")) is not None:
            return refusal
        return await self._fs.tree(path, max_depth, columns=columns, authority=self._authority)

    # -------------------------------------------------------------------
    # mutations
    # -------------------------------------------------------------------

    async def write(
        self,
        entries: Sequence[Entry] | None = None,
        *,
        path: str | None = None,
        content: str | None = None,
        data: bytes | None = None,
        overwrite: bool = True,
        parents: bool = False,
    ) -> Result:
        if (refusal := self._refuse_closed("write")) is not None:
            return refusal
        return await self._fs.write(
            entries,
            path=path,
            content=content,
            data=data,
            overwrite=overwrite,
            parents=parents,
            authority=self._authority,
        )

    async def edit(
        self,
        path: str | None = None,
        old: str | None = None,
        new: str | None = None,
        edits: list[EditOperation] | None = None,
        observations: list[Observation] | None = None,
        replace_all: bool = False,
    ) -> Result:
        if (refusal := self._refuse_closed("edit")) is not None:
            return refusal
        return await self._fs.edit(path, old, new, edits, observations, replace_all, authority=self._authority)

    async def delete(
        self,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        cascade: bool = True,
    ) -> Result:
        if (refusal := self._refuse_closed("delete")) is not None:
            return refusal
        return await self._fs.delete(path, observations, cascade=cascade, authority=self._authority)

    async def restore(
        self,
        path: str | None = None,
        observations: list[Observation] | None = None,
    ) -> Result:
        if (refusal := self._refuse_closed("restore")) is not None:
            return refusal
        return await self._fs.restore(path, observations, authority=self._authority)

    async def sweep(self, path: str = "/.vfs/trash") -> Result:
        if (refusal := self._refuse_closed("sweep")) is not None:
            return refusal
        return await self._fs.sweep(path, authority=self._authority)

    async def mkdir(self, path: str, *, parents: bool = False, exist_ok: bool = False) -> Result:
        if (refusal := self._refuse_closed("mkdir")) is not None:
            return refusal
        return await self._fs.mkdir(path, parents=parents, exist_ok=exist_ok, authority=self._authority)

    async def mkedge(
        self,
        edges: Sequence[Edge] | None = None,
        *,
        source: str | None = None,
        target: str | None = None,
        edge_type: str | None = None,
        provenance: Literal["user", "agent", "system"] = "system",
    ) -> Result:
        if (refusal := self._refuse_closed("mkedge")) is not None:
            return refusal
        return await self._fs.mkedge(
            edges,
            source=source,
            target=target,
            edge_type=edge_type,
            provenance=provenance,
            authority=self._authority,
        )

    async def rmedge(
        self,
        edges: Sequence[Edge] | None = None,
        *,
        source: str | None = None,
        target: str | None = None,
        edge_type: str | None = None,
    ) -> Result:
        if (refusal := self._refuse_closed("rmedge")) is not None:
            return refusal
        return await self._fs.rmedge(
            edges, source=source, target=target, edge_type=edge_type, authority=self._authority
        )

    async def move(
        self,
        src: str | None = None,
        dest: str | None = None,
        moves: Sequence[TwoPathOperation | tuple[str, str]] | None = None,
    ) -> Result:
        if (refusal := self._refuse_closed("move")) is not None:
            return refusal
        return await self._fs.move(src, dest, moves, authority=self._authority)

    async def copy(
        self,
        src: str | None = None,
        dest: str | None = None,
        copies: Sequence[TwoPathOperation | tuple[str, str]] | None = None,
    ) -> Result:
        if (refusal := self._refuse_closed("copy")) is not None:
            return refusal
        return await self._fs.copy(src, dest, copies, authority=self._authority)

    # -------------------------------------------------------------------
    # search, graph, execution
    # -------------------------------------------------------------------

    async def glob(
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
        if (refusal := self._refuse_closed("glob")) is not None:
            return refusal
        return await self._fs.glob(
            pattern,
            paths=paths,
            observations=observations,
            ext=ext,
            ext_not=ext_not,
            globs_not=globs_not,
            kind=kind,
            max_count=max_count,
            columns=columns,
            authority=self._authority,
        )

    async def grep(
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
        if (refusal := self._refuse_closed("grep")) is not None:
            return refusal
        return await self._fs.grep(
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
            authority=self._authority,
        )

    async def glean(
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
        if (refusal := self._refuse_closed("glean")) is not None:
            return refusal
        return await self._fs.glean(
            query,
            limit=limit,
            paths=paths,
            observations=observations,
            ext=ext,
            ext_not=ext_not,
            globs=globs,
            globs_not=globs_not,
            columns=columns,
            authority=self._authority,
        )

    async def graph(
        self,
        method: str,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        depth: int | None = None,
    ) -> Result:
        if (refusal := self._refuse_closed("graph")) is not None:
            return refusal
        return await self._fs.graph(method, path, observations, depth=depth, authority=self._authority)

    async def run(self, path: str, *, arguments: dict[str, Any] | None = None) -> Result:
        if (refusal := self._refuse_closed("run")) is not None:
            return refusal
        return await self._fs.run(path, arguments=arguments, authority=self._authority)

    # -------------------------------------------------------------------
    # grants
    # -------------------------------------------------------------------

    async def grant(self, path: str, principal: str, level: GrantLevel) -> Result:
        if (refusal := self._refuse_closed("grant")) is not None:
            return refusal
        return await self._fs.grant(path, principal, level, authority=self._authority)

    async def revoke(self, path: str, principal: str) -> Result:
        if (refusal := self._refuse_closed("revoke")) is not None:
            return refusal
        return await self._fs.revoke(path, principal, authority=self._authority)

    async def grants(self, path: str) -> Result:
        if (refusal := self._refuse_closed("grants")) is not None:
            return refusal
        return await self._fs.grants(path, authority=self._authority)

    async def posture(self, path: str, posture: Posture) -> Result:
        if (refusal := self._refuse_closed("posture")) is not None:
            return refusal
        return await self._fs.posture(path, posture, authority=self._authority)

    async def add_member(self, group: str, member: str, *, path: str = "/") -> Result:
        if (refusal := self._refuse_closed("add_member")) is not None:
            return refusal
        return await self._fs.add_member(group, member, path=path, authority=self._authority)

    async def remove_member(self, group: str, member: str, *, path: str = "/") -> Result:
        if (refusal := self._refuse_closed("remove_member")) is not None:
            return refusal
        return await self._fs.remove_member(group, member, path=path, authority=self._authority)

    # -------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------

    def _refuse_closed(self, op: Op) -> Result | None:
        """The structured refusal a closed session answers every verb with."""
        if not self._closed:
            return None
        return Result(
            ops=(op,),
            errors=[
                ResultError(
                    kind=VFSErrorKind.invalid,
                    message="the session is closed and cannot reopen; open a new one",
                )
            ],
        )
