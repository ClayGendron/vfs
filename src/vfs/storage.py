"""Storage backend protocols — the composed seam beneath the router.

A :class:`~vfs.base2.VirtualFileSystem` node *holds* its storage rather
than *being* it: the constructor accepts a :class:`StorageBackend` object,
and the router's one local-dispatch funnel calls these methods and nothing
else.  Protocols are grouped by op family so a partial backend claims only
what it genuinely supports — the router derives its default
``capabilities()`` from which families the object satisfies, so the
declared set cannot drift from reality.

    class MemoryStorage:            # read family = minimum viable backend
        async def read(self, *, path=None, observations=None, columns=None, user_id=None): ...
        async def stat(self, ...): ...
        async def ls(self, ...): ...
        async def tree(self, ...): ...

    fs = VirtualFileSystem(storage=MemoryStorage())

Every path a backend method receives is already gated and terminal-relative
(the router resolves, gates, and rebases first); every method returns a
``Result`` — the single classified failure channel.  A raw exception from a
backend is a bug and propagates as one.  Transactions are backend-internal:
a backend opens and commits its own session inside these methods, and the
router never sees it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final, NamedTuple, Protocol, runtime_checkable

from vfs.ops import MUTATING_OPS

if TYPE_CHECKING:
    from vfs.models2 import Entry, Observation
    from vfs.ops import CaseMode, GrepOutputMode, Op
    from vfs.paths import Path
    from vfs.replace import EditOperation
    from vfs.results2 import Result


class ResolvedPair(NamedTuple):
    """A gated, terminal-relative src/dest pair — what move/copy receive.

    Distinct from the router's caller-facing ``TwoPathOperation`` so the
    annotation says which side of the resolve gate a pair is on: raw caller
    strings in, minted paths out.
    """

    src: Path
    dest: Path


# ---------------------------------------------------------------------------
# Op-family protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class SupportsRead(Protocol):
    """The read family: point reads and listings."""

    async def read(
        self,
        *,
        path: Path | None = None,
        observations: list[Observation] | None = None,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result: ...

    async def stat(
        self,
        *,
        path: Path | None = None,
        observations: list[Observation] | None = None,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result: ...

    async def ls(
        self,
        *,
        path: Path | None = None,
        observations: list[Observation] | None = None,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result: ...

    async def tree(
        self,
        *,
        path: Path,
        max_depth: int | None = None,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result: ...


@runtime_checkable
class SupportsPatternSearch(Protocol):
    """The pattern-search family: literal/regex matching over names and content.

    Namespace-wide queries — empty ``paths`` means unscoped.  Split from
    ranked search (:class:`SupportsGlean`) because a lexical scan needs no
    retrieval index: partial backends routinely have one without the other.
    """

    async def glob(
        self,
        *,
        pattern: str,
        paths: tuple[Path, ...] = (),
        observations: list[Observation] | None = None,
        ext: tuple[str, ...] = (),
        max_count: int | None = None,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result: ...

    async def grep(
        self,
        *,
        pattern: str,
        paths: tuple[Path, ...] = (),
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
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result: ...


@runtime_checkable
class SupportsGlean(Protocol):
    """The ranked-search family: text in, one fused ranked list out.

    Its own family because it rides on retrieval indexes (vector, lexical,
    graph) a backend may not have even when it can glob/grep.
    """

    async def glean(
        self,
        *,
        query: str,
        limit: int = 10,
        paths: tuple[Path, ...] = (),
        observations: list[Observation] | None = None,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result: ...


@runtime_checkable
class SupportsMutation(Protocol):
    """The mutation family: exactly the write-gated ops (``MUTATING_OPS``).

    ``mkedge`` lives here, not in the graph family — it writes the edge
    projection, and the family boundary follows the write gate.
    """

    async def write(
        self,
        *,
        path: Path | None = None,
        content: str | None = None,
        entries: list[Entry] | None = None,
        overwrite: bool = True,
        user_id: str | None = None,
    ) -> Result: ...

    async def edit(
        self,
        *,
        edits: list[EditOperation],
        path: Path | None = None,
        observations: list[Observation] | None = None,
        user_id: str | None = None,
    ) -> Result: ...

    async def delete(
        self,
        *,
        path: Path | None = None,
        observations: list[Observation] | None = None,
        permanent: bool = False,
        cascade: bool = True,
        user_id: str | None = None,
    ) -> Result: ...

    async def mkdir(self, *, path: Path, user_id: str | None = None) -> Result: ...

    async def move(
        self,
        *,
        operations: list[ResolvedPair],
        overwrite: bool = True,
        user_id: str | None = None,
    ) -> Result: ...

    async def copy(
        self,
        *,
        operations: list[ResolvedPair],
        overwrite: bool = True,
        user_id: str | None = None,
    ) -> Result: ...

    async def mkedge(
        self,
        *,
        source: Path,
        target: Path,
        edge_type: str,
        user_id: str | None = None,
    ) -> Result: ...


@runtime_checkable
class SupportsGraph(Protocol):
    """The graph family: read-side traversals over the backend's own subgraph."""

    async def graph(
        self,
        *,
        method: str,
        path: Path | None = None,
        observations: list[Observation] | None = None,
        depth: int | None = None,
        user_id: str | None = None,
    ) -> Result: ...


@runtime_checkable
class SupportsRun(Protocol):
    """The execution family: run the tool at a path."""

    async def run(
        self,
        *,
        path: Path,
        arguments: dict[str, Any] | None = None,
        user_id: str | None = None,
    ) -> Result: ...


@runtime_checkable
class StorageBackend(SupportsRead, Protocol):
    """The constructor's accepted type: the read family is the minimum.

    The mountability probe needs ``stat``, and a backend that cannot even
    be read is not a storage backend.  Implement the further families the
    backend genuinely supports; the router derives capability from them.
    """


@runtime_checkable
class SupportsClose(Protocol):
    """Optional disposal: a backend that owns an engine exposes ``close``.

    The router's ``close()`` disposes its own backend through this after
    closing its mounts; repeated disposal is the backend's concern.
    """

    async def close(self) -> None: ...


# ---------------------------------------------------------------------------
# Capability derivation
# ---------------------------------------------------------------------------

_FAMILY_OPS: Final[tuple[tuple[type, frozenset[Op]], ...]] = (
    (SupportsRead, frozenset({"read", "stat", "ls", "tree"})),
    (SupportsPatternSearch, frozenset({"glob", "grep"})),
    (SupportsGlean, frozenset({"glean"})),
    (SupportsMutation, MUTATING_OPS),
    (SupportsGraph, frozenset({"graph"})),
    (SupportsRun, frozenset({"run"})),
)


def storage_ops(storage: object) -> frozenset[Op]:
    """The ops *storage* honestly answers — derived from the families it satisfies.

    Presence-based (``runtime_checkable`` checks members exist, not their
    signatures).  ``ty`` checks signatures where a family is *expressed* in a
    type: the read family at the constructor hand-off, further families where
    a backend annotates them (a backend's own tests should).  A present but
    mis-signed method is a backend bug and raises on the bug channel.
    ``None`` or a non-backend derives the empty set.
    """
    ops: set[Op] = set()
    for family, family_ops in _FAMILY_OPS:
        if isinstance(storage, family):
            ops |= family_ops
    return frozenset(ops)
