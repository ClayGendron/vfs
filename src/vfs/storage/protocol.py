"""Storage backend protocols — the composed seam beneath the router.

A :class:`~vfs.base.VirtualFileSystem` mounts storage rather than other
routers: every mount-table entry binds a :class:`StorageBackend` object,
and the router's one dispatch funnel calls these methods and nothing else.
Protocols are grouped by op family so a partial backend implements only
what it genuinely supports, and every backend *declares* its op set
through ``capabilities()`` — self-declaration, never structural sniffing,
so an adapter or wire client answers with its real set rather than its
method surface.

    class SnapshotStorage:          # the read family = the verb minimum
        name = "snapshot"
        description = "Read-only rows from a frozen snapshot"

        def capabilities(self): return frozenset({"read", "stat", "ls", "tree"})
        async def read(self, *, path=None, observations=None, columns=None, user_id=None): ...
        async def stat(self, ...): ...
        async def ls(self, ...): ...
        async def tree(self, ...): ...

    fs = VirtualFileSystem(storage=SnapshotStorage())

Every path a backend method receives is already gated and terminal-relative
(the router resolves, gates, and rebases first); every path a backend
*returns* is likewise terminal-relative and normalized — the funnel
validates and rebases on the way out.  Every op method returns a ``Result``
— the single classified failure channel.  A raw exception from an
in-process backend is a bug and propagates as one; a *wire* backend
raises :class:`TransportError` for a dead or unreachable peer, which the
funnel normalizes to a ``backend_unavailable`` classification.
Transactions are backend-internal: a backend opens and commits its own
session inside these methods, and the router never sees it.

Two read semantics every backend implements identically: **enumeration
liveness** — default-scope enumeration (``ls``, ``tree``, ``glob``,
``grep``) hides the reserved ``/.vfs`` meta subtree, and direct meta
addressing (a target inside it; for the pattern-search verbs, a meta
literal prefix in a pattern) serves its own subtree, never the whole
scope; and **per-target
classification** — a missing target in a batch classifies through the
descent ladder beside the healthy targets' rows (partial results,
per-target errors, never all-or-nothing).  Scope never crosses this
seam as paths: the pattern-search verbs receive scope only as
composed pattern text, and chained rows are filtered by the router
without reaching storage at all.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final, Literal, NamedTuple, Protocol, get_args, runtime_checkable

from vfs.ops import MUTATING_OPS

if TYPE_CHECKING:
    from collections.abc import Mapping

    from vfs.models import Entry, Observation
    from vfs.ops import CaseMode, GrepOutputMode, Op
    from vfs.paths import Path
    from vfs.results import Result
    from vfs.storage.replace import EditOperation


# Declared operating-quality traits — how a backend serves its verbs, not
# which verbs it serves (that is ``capabilities()``). An absent key means
# the trait is not declared, never a default.
TraitKey = Literal["grep_tier", "grep_staleness", "version_encoding", "durability", "arbitration"]
TRAIT_KEYS: Final[frozenset[str]] = frozenset(get_args(TraitKey))

TRAIT_VALUES: Final[dict[str, frozenset[str]]] = {
    "grep_tier": frozenset({"indexed", "scan"}),
    "grep_staleness": frozenset({"none", "overlay"}),
    "version_encoding": frozenset({"per_entry64"}),
    "durability": frozenset({"full", "relaxed"}),
    "arbitration": frozenset({"upsert", "catch_retry"}),
}
"""Per-key value vocabulary; the traits drift test pins declarations to it."""


class TransportError(Exception):
    """A wire backend's peer is dead or unreachable — an operating condition.

    Raised (or subclassed) only by backends whose storage lives across a
    process or network boundary; the router's funnel normalizes it into a
    ``backend_unavailable`` classification.  In-process backends never
    raise it — for them a raw exception remains a bug and propagates.
    """


class ResolvedPair(NamedTuple):
    """A gated, terminal-relative src/dest pair — what move/copy receive.

    Distinct from the caller-facing ``TwoPathOperation`` in ``vfs.ops`` so the
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
class SupportsMutation(Protocol):
    """The mutation family: exactly the write-gated ops (``MUTATING_OPS``).

    ``mkedge`` lives here, not in the graph family — it writes the edge
    projection, and the family boundary follows the write gate.
    """

    async def write(
        self,
        *,
        entries: list[Entry],
        overwrite: bool = True,
        parents: bool = False,
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
        cascade: bool = True,
        user_id: str | None = None,
    ) -> Result: ...

    async def restore(
        self,
        *,
        path: Path | None = None,
        observations: list[Observation] | None = None,
        overwrite: bool = False,
        user_id: str | None = None,
    ) -> Result: ...

    async def sweep(
        self,
        *,
        path: Path,
        user_id: str | None = None,
    ) -> Result: ...

    async def mkdir(
        self,
        *,
        path: Path,
        parents: bool = False,
        exist_ok: bool = False,
        user_id: str | None = None,
    ) -> Result: ...

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
class SupportsPatternSearch(Protocol):
    """The pattern-search family: literal/regex matching over names and content.

    Namespace-wide queries.  Scoping crosses this seam only as pattern
    text: the router composes scope roots into glob's *patterns* batch
    and into grep's ``globs``/``globs_not`` channels, answered in one
    transaction and one snapshot per call.  Glob returns rows matching
    **any** pattern, one refusable pattern refusing the call whole;
    grep's ``pattern`` is content-only and never a path.  Split from
    ranked search (:class:`SupportsGlean`) because a lexical scan needs
    no retrieval index: partial backends routinely have one without the
    other.
    """

    async def glob(
        self,
        *,
        patterns: tuple[str, ...],
        ext: tuple[str, ...] = (),
        max_count: int | None = None,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result: ...

    async def grep(
        self,
        *,
        pattern: str,
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
    """What a mount-table entry binds: identity, declared capability, read verbs.

    The read family is the *verb* minimum — a backend that cannot even be
    read is not a storage backend — and three identity members are required
    besides: ``name`` and ``description`` say what this backend is (mount
    administration reads the live ``description``), and
    ``capabilities()`` declares the ops it honestly answers.  Declaration
    beats inference: an adapter's method surface says nothing about what
    its wrapped namespace supports, and a wire client's set is whatever
    the far side advertises.  Site legality has no probe — ``mkdir`` and
    the other mutation verbs check and act in one call.
    """

    name: str
    description: str

    def capabilities(self) -> frozenset[Op]: ...


@runtime_checkable
class SupportsTraits(Protocol):
    """Optional declared operating qualities — how the verbs are served.

    ``capabilities()`` says which ops a backend answers; ``traits()`` says
    with what qualities — grep's tier and staleness window, the version
    encoding, the durability tier, the create-arbitration mode. Keys come
    from :data:`TRAIT_KEYS`, values from :data:`TRAIT_VALUES`; an absent
    key is "not declared," never an implied default. Declaration beats
    discovery: staleness and durability are contracts a caller must be
    able to read, not surprises to probe for.
    """

    def traits(self) -> Mapping[str, str]: ...


@runtime_checkable
class SupportsClose(Protocol):
    """Optional disposal: a backend that owns an engine or session exposes ``close``.

    The router's ``close()`` walks its table and disposes each bound
    backend through this (identity-deduped, ``owned``-gated).  The
    contract: ``close`` is idempotent — a second call is a no-op, not an
    error — and dead-peer-tolerant — a wire backend whose peer is already
    gone swallows the transport failure and completes its own teardown.
    """

    async def close(self) -> None: ...


# ---------------------------------------------------------------------------
# Target shaping — the protocol-level addressing rules every backend shares
# ---------------------------------------------------------------------------


def targets_of(
    path: Path | None,
    observations: list[Observation] | None,
    *,
    default: Path | None = None,
) -> list[Path]:
    """The paths an op addresses: the single path, the rows', or *default*."""
    if path is not None:
        return [path]
    if observations is not None:
        return [o.path for o in observations]
    return [default] if default is not None else []


# ---------------------------------------------------------------------------
# Capability self-derivation
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
    """Derive an op set from the ``Supports*`` families *storage* satisfies.

    A convenience for *implementing* ``capabilities()`` on an in-process
    backend whose method surface is its truth — ``return storage_ops(self)``
    stays in sync as families are added.  The router never calls this: the
    gate consults only the declared ``capabilities()``.  Indirection must
    not use it — an adapter or wire client defines every verb method
    regardless of what its far side supports, so its surface lies; those
    backends forward the wrapped router's set or derive from the peer's
    advertised tools instead.
    """
    ops: set[Op] = set()
    for family, family_ops in _FAMILY_OPS:
        if isinstance(storage, family):
            ops |= family_ops
    return frozenset(ops)
