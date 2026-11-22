"""The verbs a line can reach: every request of the machine and every program vfs runs is one call
of one of these, as the caller.

The router (:class:`~vfs.AsyncVirtualFileSystem`) is one; the shell names only the verbs, so it
sits beneath the router and imports nothing above it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from vfs.authority import Authority
    from vfs.models import Observation
    from vfs.ops import CaseMode, GrepOutputMode, Rung
    from vfs.paths import ObjectKind
    from vfs.results import Result


class Router(Protocol):
    """The public verbs of the router that the shell calls, each with the caller's authority."""

    async def read(self, path: str, /, *, columns: frozenset[str], authority: Authority | None) -> Result: ...

    async def stat(self, path: str, /, *, authority: Authority | None) -> Result: ...

    async def ls(self, path: str, /, *, authority: Authority | None) -> Result: ...

    async def glob(
        self,
        pattern: str,
        /,
        *,
        paths: tuple[str, ...],
        kind: ObjectKind | None,
        max_count: int | None,
        authority: Authority | None,
    ) -> Result: ...

    async def grep(
        self,
        pattern: str,
        /,
        *,
        paths: tuple[str, ...],
        globs: tuple[str, ...],
        globs_not: tuple[str, ...],
        case_mode: CaseMode,
        fixed_strings: bool,
        word_regexp: bool,
        output_mode: GrepOutputMode,
        allow_scan: bool,
        authority: Authority | None,
    ) -> Result: ...

    async def search(
        self, query: str, /, *, limit: int, paths: tuple[str, ...], authority: Authority | None
    ) -> Result: ...

    async def traverse(
        self,
        method: str,
        path: str | None = ...,
        observations: list[Observation] | None = ...,
        *,
        depth: int | None,
        edge_types: tuple[str, ...],
        edge_types_not: tuple[str, ...],
        minimal: bool,
        limit: int | None,
        authority: Authority | None,
    ) -> Result: ...

    async def write(
        self,
        *,
        path: str,
        authority: Authority | None,
        content: str | None = ...,
        data: bytes | None = ...,
        if_absent: bool = ...,
        append: bool = ...,
    ) -> Result: ...

    async def edit(
        self, path: str, old: str, new: str, /, *, replace_all: bool, authority: Authority | None
    ) -> Result: ...

    async def mkdir(self, path: str, /, *, parents: bool, exist_ok: bool, authority: Authority | None) -> Result: ...

    async def delete(self, path: str, /, *, cascade: bool, authority: Authority | None) -> Result: ...

    async def copy(self, src: str, dest: str, /, *, authority: Authority | None) -> Result: ...

    async def move(self, src: str, dest: str, /, *, authority: Authority | None) -> Result: ...

    async def mkedge(self, *, source: str, target: str, edge_type: str, authority: Authority | None) -> Result: ...

    async def rmedge(self, *, source: str, target: str, edge_type: str, authority: Authority | None) -> Result: ...

    async def grant(self, path: str, principal: str, level: Rung, /, *, authority: Authority | None) -> Result: ...

    async def revoke(self, path: str, principal: str, /, *, authority: Authority | None) -> Result: ...

    async def grants(self, path: str, /, *, authority: Authority | None) -> Result: ...
