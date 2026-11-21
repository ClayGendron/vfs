"""``DatabaseStorage`` — the portable SQL backend (reads, glob, mutation core).

Runs on any SQLAlchemy-compatible database: known dialects carry tuned
policy, everything else serves on the generic floor (``dialects.py``).
Point reads with projection push-down, ``parent_id`` listings and glob's
batched pattern fan are in ``reads.py``, on the descent ladder of
``descent.py``; grep's indexed pipeline in ``grep.py``; write, edit and
mkdir batches, each planned and executed as one transaction, in
``writes.py``; move and copy in ``topology.py`` and delete, restore and
sweep in ``trash.py``, over the kit in ``serialized.py``; and
``mkedge``/``rmedge``, over the table of the fs mirror, in ``edges.py``.

    storage = DatabaseStorage(url="sqlite+aiosqlite:///vfs.sqlite")

A storage builds and owns its engine, and ``close()`` disposes it. First
touch runs at the first routed op or at ``first_touch``, on the caller's
loop. Each protocol method runs in one session under retry: a retryable
outcome restarts it from its first read, and a driver failure that
escapes retry returns a classified ``Result``, never an exception.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from functools import partial
from typing import TYPE_CHECKING, Any, Literal, NamedTuple, TypeVar

from sqlalchemy.exc import SQLAlchemyError

from vfs.authority import Authority
from vfs.deadline import WALL_TIME_BUDGET, Deadline
from vfs.models.rows import PGVECTOR_INDEX_MAX_DIMENSION
from vfs.offload import call_offloaded, offload_pool
from vfs.ops import TRAVERSE_DEPTH_DEFAULT, TRAVERSE_LIMIT_DEFAULT, VERB_RUNGS
from vfs.paths import TRASH_ROOT, Path, address_of
from vfs.pattern_matching import PatternError, ScopeChannel
from vfs.rendering.registry import RendererRegistry
from vfs.rendering.seam import RenderLimits
from vfs.results import ErrorKind, Result, ResultError, Severity, classified
from vfs.storage.backends.database.addressing import addressed_by, scope_judged
from vfs.storage.backends.database.authorized import admit_destinations, fenced, opening, remember
from vfs.storage.backends.database.descent import ROOT
from vfs.storage.backends.database.dialects import (
    PROFILES,
    StaleSnapshot,
    op_execution_options,
    topology_execution_options,
)
from vfs.storage.backends.database.edges import mkedge_rows, rmedge_rows
from vfs.storage.backends.database.embed import EMBED_CONCURRENCY, EMBED_TIMEOUT_SECONDS, unit_vector
from vfs.storage.backends.database.engine import EngineHost
from vfs.storage.backends.database.grep import grep_rows
from vfs.storage.backends.database.labels import Relabel, Relabeller, posture_rows_for_chunks
from vfs.storage.backends.database.maintenance import MaintenanceContext, rebuild, refresh
from vfs.storage.backends.database.reads import (
    AdmittedScope,
    admit_scope,
    effective_columns,
    glob_rows,
    ls_rows,
    read_rows,
    stat_rows,
    tree_rows,
)
from vfs.storage.backends.database.revision import bump_revision
from vfs.storage.backends.database.rights import (
    RightsCache,
    Visibility,
    WriteGate,
    add_member_rows,
    denied,
    grant_rows,
    posture_chain,
    posture_refusals,
    posture_wall_refusal,
    remove_member_rows,
    resolve_authority,
    revoke_rows,
    set_posture,
    unauthenticated_refusals,
)
from vfs.storage.backends.database.rights_reads import held, listed_grants
from vfs.storage.backends.database.seams import seam
from vfs.storage.backends.database.search import VectorLeg, search_rows
from vfs.storage.backends.database.topology import transfer_rows
from vfs.storage.backends.database.trash import delete_rows, restore_rows, sweep_rows
from vfs.storage.backends.database.traverse import GraphRequest, Site, traverse_rows
from vfs.storage.backends.database.writes import edit_rows, measured_entries, mkdir_rows, write_rows
from vfs.storage.protocol import HOLDS, storage_ops, targets_of
from vfs.storage.ranking import Ranker

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterable, Mapping

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from vfs.embedding import EmbeddingProvider
    from vfs.models import Edge, Entry, Observation
    from vfs.models.vector import NativeEmbeddingConfig
    from vfs.ops import CaseMode, GrepOutputMode, Needs, Op, Rung
    from vfs.paths import ObjectKind
    from vfs.storage import ResolvedPair
    from vfs.storage.backends.database.rights import Resolution
    from vfs.storage.grants import GrantLevel, Posture
    from vfs.storage.replace import EditOperation

T = TypeVar("T")

_SYSTEM = Authority.system()

QUERY_VECTOR_CACHE = 256
"""Embedded queries remembered per mount — a re-asked question costs no provider call."""

PGVECTOR_ITERATIVE_SCAN = "SET LOCAL hnsw.iterative_scan = relaxed_order"
"""pgvector 0.8+: keep scanning the HNSW index until a scoped query's window fills."""


class _ScopedGate(NamedTuple):
    """An anonymous scoped call's posture gate: what composition would have judged, and the verb's wall.

    ``patterns`` is the entry-wide channel, ``scope`` the admitted scope
    (roots in entry coordinates, arms expanded), ``piped`` the paths of
    rows piped into the call, judged after the patterns' paths.
    """

    patterns: tuple[str, ...]
    scope: ScopeChannel
    piped: tuple[str, ...]
    wall_seconds: float


class DatabaseStorage:
    """One mount's portable database backend over SQLAlchemy Core.

    *posture* is what everyone holds at the root of a freshly provisioned
    mount — ``open``, ``shared`` or ``private``. It is planted once, at
    first touch: a mount that already exists keeps its stored posture,
    and only the ``set_posture`` verb changes it.

    *engine_arguments* go to SQLAlchemy's ``create_async_engine`` beside
    the URL: the pool's class and size, ``pool_pre_ping``, ``connect_args``,
    ``async_creator``. One that VFS itself requires may not be changed.

    On SQLite a cancelled caller waits while its call ends the statement
    in flight, or its wait for a connection, and is rolled back: a
    cancelled write changes nothing unless its commit had begun.
    """

    def __init__(
        self,
        *,
        url: str,
        engine_arguments: Mapping[str, Any] | None = None,
        schema: str | None = None,
        name: str = "database",
        description: str | None = None,
        trash_days: int = 90,
        grep_wall_seconds: float = WALL_TIME_BUDGET,
        search_wall_seconds: float = WALL_TIME_BUDGET,
        glob_wall_seconds: float = WALL_TIME_BUDGET,
        embedder: EmbeddingProvider | None = None,
        native_embedding: NativeEmbeddingConfig | None = None,
        embed_concurrency: int = EMBED_CONCURRENCY,
        embed_timeout_seconds: float = EMBED_TIMEOUT_SECONDS,
        ranker: Ranker | None = None,
        renderers: RendererRegistry | None = None,
        render_limits: RenderLimits | None = None,
        posture: Posture = "read_write",
    ) -> None:
        if trash_days < 0:
            raise ValueError(f"trash_days must be non-negative, got {trash_days}")
        if grep_wall_seconds <= 0:
            raise ValueError(f"grep_wall_seconds must be positive, got {grep_wall_seconds}")
        if glob_wall_seconds <= 0:
            raise ValueError(f"glob_wall_seconds must be positive, got {glob_wall_seconds}")
        if embed_concurrency < 1:
            raise ValueError(f"embed_concurrency must be at least 1, got {embed_concurrency}")
        if embed_timeout_seconds <= 0:
            raise ValueError(f"embed_timeout_seconds must be positive, got {embed_timeout_seconds}")
        self._host = EngineHost(
            url=url,
            engine_arguments=engine_arguments,
            schema=schema,
            embedder=embedder,
            native_embedding=native_embedding,
            posture=posture,
        )
        # Resolved authorities, one per subject set, revalidated by their stamps and the relabels in flight.
        self._rights = RightsCache()
        self._trash_days = trash_days
        self._embed_concurrency = embed_concurrency
        self._embed_timeout = embed_timeout_seconds
        self._ranker = ranker if ranker is not None else Ranker()
        # The per-format renderers a bytes entry's text comes from, probed once here.
        self._renderers = renderers if renderers is not None else RendererRegistry.bundled()
        self._render_limits = render_limits if render_limits is not None else RenderLimits()
        # The last queries' vectors, keyed by space: a re-asked question costs no provider call.
        self._query_vectors: OrderedDict[tuple[str, str], list[float]] = OrderedDict()
        if search_wall_seconds <= 0:
            raise ValueError(f"search_wall_seconds must be positive, got {search_wall_seconds}")
        self._grep_wall_seconds = grep_wall_seconds
        self._search_wall_seconds = search_wall_seconds
        self._glob_wall_seconds = glob_wall_seconds
        self.name = name
        self.description = description or (f"Database storage ({schema})" if schema else "Database storage")

    @property
    def engine(self) -> AsyncEngine:
        """The storage's own engine, for a ``do_connect`` hook or tracing. ``close()`` disposes it, and no one else."""
        return self._host.engine

    @property
    def mount_identity(self) -> str | None:
        """The durable mount identity, known after first touch."""
        return self._host.mount_identity

    @property
    def embedder(self) -> EmbeddingProvider | None:
        """The configured embedding provider; ``None`` serves search lexical-only."""
        return self._host.embedder

    @property
    def ranker(self) -> Ranker:
        """The mount's ranking declaration: its fusion and its chunk aggregate.

        Settable: fusion and aggregation are query-time choices over the
        same index, so a mount may be re-ranked without a rebuild.
        """
        return self._ranker

    @ranker.setter
    def ranker(self, ranker: Ranker) -> None:
        self._ranker = ranker

    @property
    def renderers(self) -> RendererRegistry:
        """The renderers a bytes entry's text comes from, by media type."""
        return self._renderers

    def capabilities(self) -> frozenset[Op]:
        """The method surface, minus what this mount cannot vouch for.

        An unknown dialect serves the core verbs on the generic floor
        and withholds ``search``: ranked search needs a cosine distance
        in the engine, which only a tuned profile declares.
        """
        withheld: set[Op] = set()
        if self._host.profile.vector_distance == "none":
            withheld.add("search")
        return storage_ops(self) - withheld

    def traits(self) -> Mapping[str, str]:
        declared = {
            "version_encoding": "per_entry64",
            "arbitration": self._host.profile.arbitration,
            "grep_tier": "indexed",
            "grep_staleness": "overlay",
            "search_signals": "hybrid" if self._host.embedder is not None else "lexical",
            "search_staleness": "overlay",
        }
        # Tuned engines are the measured ones; only they may claim full
        # durability — unknown dialects resolve to GENERIC-renamed names.
        if self._host.profile.name in PROFILES:
            declared["durability"] = "full"
        return declared

    # -------------------------------------------------------------------
    # Read family
    # -------------------------------------------------------------------

    async def read(
        self,
        *,
        path: Path | None = None,
        observations: list[Observation] | None = None,
        columns: frozenset[str] | None = None,
        authority: Authority | None = None,
    ) -> Result:
        targets = targets_of(path, observations)
        host = self._host
        return await self._execute(
            "read",
            self._viewed(
                "read",
                authority,
                [str(target) for target in targets],
                lambda session, view: read_rows(
                    session, host.tables, host.profile, host.membership_budget, targets, columns, view
                ),
            ),
        )

    async def stat(
        self,
        *,
        path: Path | None = None,
        observations: list[Observation] | None = None,
        columns: frozenset[str] | None = None,
        authority: Authority | None = None,
    ) -> Result:
        targets = targets_of(path, observations)
        host = self._host
        return await self._execute(
            "stat",
            self._viewed(
                "stat",
                authority,
                [str(target) for target in targets],
                lambda session, view: stat_rows(
                    session, host.tables, host.profile, host.membership_budget, targets, columns, view
                ),
            ),
        )

    async def ls(
        self,
        *,
        path: Path | None = None,
        observations: list[Observation] | None = None,
        columns: frozenset[str] | None = None,
        authority: Authority | None = None,
    ) -> Result:
        targets = targets_of(path, observations, default=ROOT)
        host = self._host
        return await self._execute(
            "ls",
            self._viewed(
                "ls",
                authority,
                [str(target) for target in targets],
                lambda session, view: ls_rows(
                    session, host.tables, host.profile, host.membership_budget, targets, columns, view
                ),
            ),
        )

    async def tree(
        self,
        *,
        path: Path,
        max_depth: int | None = None,
        columns: frozenset[str] | None = None,
        authority: Authority | None = None,
    ) -> Result:
        if max_depth is not None and max_depth < 1:
            return Result(
                ops=("tree",),
                errors=[classified(ErrorKind.invalid, detail=f"max_depth must be >= 1, got {max_depth}")],
            )
        host = self._host
        return await self._execute(
            "tree",
            self._viewed(
                "tree",
                authority,
                [str(path)],
                lambda session, view: tree_rows(
                    session, host.tables, host.profile, host.membership_budget, path, max_depth, columns, view
                ),
            ),
        )

    # -------------------------------------------------------------------
    # Traversal family
    # -------------------------------------------------------------------

    async def traverse(
        self,
        *,
        method: str,
        path: Path | None = None,
        observations: list[Observation] | None = None,
        depth: int | None = TRAVERSE_DEPTH_DEFAULT,
        edge_types: tuple[str, ...] = (),
        edge_types_not: tuple[str, ...] = (),
        minimal: bool = False,
        limit: int | None = TRAVERSE_LIMIT_DEFAULT,
        columns: frozenset[str] | None = None,
        authority: Authority | None = None,
    ) -> Result:
        """The frontier walk from the seeds under the caller's view; see ``traverse.py``.

        The type lists are bound beside the frontier in every hop statement,
        so together they may not exceed half the membership budget.
        """
        for name, value in (("depth", depth), ("limit", limit)):
            if value is not None and value < 1:
                return Result(
                    ops=("traverse",),
                    errors=[classified(ErrorKind.invalid, detail=f"{name} must be >= 1, got {value}")],
                )
        host = self._host
        if len(edge_types) + len(edge_types_not) > host.membership_budget // 2:
            detail = (
                f"traverse names {len(edge_types) + len(edge_types_not)} edge types; "
                f"at most {host.membership_budget // 2}"
            )
            return Result(ops=("traverse",), errors=[classified(ErrorKind.invalid, detail=detail)])
        seeds = [path] if path is not None else [row.path for row in observations or []]
        request = GraphRequest(
            method,
            depth,
            tuple(edge_types),
            tuple(edge_types_not),
            minimal,
            limit,
            effective_columns(columns, content=False),
        )
        site = Site(host.tables, host.profile, host.membership_budget)
        return await self._execute(
            "traverse",
            self._viewed(
                "traverse",
                authority,
                [str(seed) for seed in seeds],
                lambda session, view: traverse_rows(session, site, request, seeds, view),
            ),
        )

    # -------------------------------------------------------------------
    # Pattern search
    # -------------------------------------------------------------------

    async def glob(
        self,
        *,
        patterns: tuple[str, ...],
        globs_not: tuple[str, ...] = (),
        ext: tuple[str, ...] = (),
        ext_not: tuple[str, ...] = (),
        kind: ObjectKind | None = None,
        max_count: int | None = None,
        columns: frozenset[str] | None = None,
        scope: ScopeChannel | None = None,
        authority: Authority | None = None,
    ) -> Result:
        try:
            admitted = admit_scope(scope, "pattern")
        except PatternError as exc:
            return Result(ops=("glob",), errors=[classified(ErrorKind.invalid, detail=str(exc))])
        host = self._host
        gate = self._scoped_gate(authority, patterns, admitted, (), self._glob_wall_seconds)
        return await self._execute(
            "glob",
            self._viewed(
                "glob",
                authority,
                addressed_by(patterns) if gate is None else (),
                lambda session, view: glob_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.parameter_budget,
                    host.membership_budget,
                    offload_pool(),
                    patterns=patterns,
                    globs_not=globs_not,
                    ext=ext,
                    ext_not=ext_not,
                    kind=kind,
                    max_count=max_count,
                    columns=columns,
                    wall_seconds=self._glob_wall_seconds,
                    view=view,
                    scope=admitted,
                ),
                scoped=gate,
            ),
        )

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
        scope: ScopeChannel | None = None,
        authority: Authority | None = None,
    ) -> Result:
        try:
            admitted = admit_scope(scope, "globs")
        except PatternError as exc:
            return Result(ops=("grep",), errors=[classified(ErrorKind.invalid, detail=str(exc))])
        host = self._host
        gate = self._scoped_gate(authority, globs, admitted, (), self._grep_wall_seconds)
        return await self._execute(
            "grep",
            self._viewed(
                "grep",
                authority,
                addressed_by(globs) if gate is None else (),
                lambda session, view: grep_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.parameter_budget,
                    host.membership_budget,
                    offload_pool(),
                    view=view,
                    pattern=pattern,
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
                    wall_seconds=self._grep_wall_seconds,
                    scope=admitted,
                ),
                scoped=gate,
            ),
        )

    # -------------------------------------------------------------------
    # Ranked search
    # -------------------------------------------------------------------

    async def search(
        self,
        *,
        query: str,
        limit: int = 10,
        ext: tuple[str, ...] = (),
        ext_not: tuple[str, ...] = (),
        globs: tuple[str, ...] = (),
        globs_not: tuple[str, ...] = (),
        observations: list[Observation] | None = None,
        columns: frozenset[str] | None = None,
        scope: ScopeChannel | None = None,
        authority: Authority | None = None,
    ) -> Result:
        try:
            admitted = admit_scope(scope, "globs")
        except PatternError as exc:
            return Result(ops=("search",), errors=[classified(ErrorKind.invalid, detail=str(exc))])
        refusal = await self._host.ensure_ready()
        if refusal is not None:
            return Result(ops=("search",), errors=[refusal])
        scoped = bool(ext or ext_not or globs or globs_not or observations or scope)
        vector, records = await self._vector_leg_for(query, scoped=scoped)
        host = self._host
        piped = tuple(str(row.path) for row in observations or ())
        gate = self._scoped_gate(authority, globs, admitted, piped, self._search_wall_seconds)
        return await self._execute(
            "search",
            self._viewed(
                "search",
                authority,
                [*addressed_by(globs), *piped] if gate is None else (),
                lambda session, view: search_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.parameter_budget,
                    host.membership_budget,
                    offload_pool(),
                    view=view,
                    query=query,
                    limit=limit,
                    ext=ext,
                    ext_not=ext_not,
                    globs=globs,
                    globs_not=globs_not,
                    observations=observations,
                    columns=columns,
                    wall_seconds=self._search_wall_seconds,
                    dialect_name=self._host.profile.name,
                    vector=vector,
                    ranker=self._ranker,
                    records=records,
                    scope=admitted,
                ),
                scoped=gate,
            ),
        )

    async def _vector_leg_for(self, query: str, *, scoped: bool) -> tuple[VectorLeg | None, list[ResultError]]:
        """Embed *query* in the mount's space and name the tier that will serve it.

        No provider, a stale stored space, or a provider that fails to
        embed the query each answer ``None`` with a record — the lexical
        leg alone serves, and the envelope says why. The tier is inferred
        from configuration: ``native_ann`` where the profile declares an
        index the planner may use, one is provisioned, and the scope does
        not defeat it; ``native_exact`` otherwise. pgvector 0.8+ gets the
        iterative scan so a scoped ANN pass fills its window.
        """
        provider = self._host.embedder
        if provider is None:
            note = classified(
                ErrorKind.unavailable,
                severity=Severity.info,
                detail="no embedding provider is configured; the lexical leg alone answered",
                data={"leg": "vector", "reason": "no_provider"},
            )
            return None, [note]
        stored = self._host.embedding_identity
        if self._host.embedding_stale and stored is not None:
            note = classified(
                ErrorKind.conflict,
                severity=Severity.warning,
                detail=(
                    f"the stored embeddings belong to {stored[0]!r} at {stored[1]} but the mount is configured for "
                    f"{provider.model_id!r}; the lexical leg alone answered; run rebuild to migrate"
                ),
                data={
                    "leg": "vector",
                    "reason": "stale_identity",
                    "stored": stored[0],
                    "configured": provider.model_id,
                },
            )
            return None, [note]
        try:
            embedded = await self._embed_query(provider, query)
        except Exception as exc:  # the provider's failure is an operating condition, never a raise
            note = classified(
                ErrorKind.unavailable,
                severity=Severity.warning,
                detail=f"embedding the query failed ({type(exc).__name__}: {exc}); the lexical leg alone answered",
                retryable=True,
                data={"leg": "vector", "reason": "embed_failed", "provider": provider.model_id},
            )
            return None, [note]
        profile = self._host.profile
        indexed = self._host.native_embedding is not None and self._ann_indexed()
        ann = profile.vector_distance == "ann" and indexed and (not scoped or profile.ann_honours_scope)
        prelude = None
        if ann and profile.name == "postgresql" and (self._host.vector_version or ()) >= (0, 8):
            prelude = PGVECTOR_ITERATIVE_SCAN
        return VectorLeg(embedded, provider.model_id, "native_ann" if ann else "native_exact", prelude), []

    def _ann_indexed(self) -> bool:
        """Whether the mount provisions an ANN index — pgvector's, within its width cap, today."""
        native = self._host.native_embedding
        return (
            self._host.profile.name == "postgresql"
            and native is not None
            and native.dimension <= PGVECTOR_INDEX_MAX_DIMENSION
        )

    async def _embed_query(self, provider: EmbeddingProvider, query: str) -> list[float]:
        """The query's unit vector, memoised per space under the search wall budget."""
        key = (provider.model_id, query)
        cached = self._query_vectors.get(key)
        if cached is not None:
            self._query_vectors.move_to_end(key)
            return cached
        vector = unit_vector(await asyncio.wait_for(provider.embed_query(query), self._search_wall_seconds))
        self._query_vectors[key] = vector
        while len(self._query_vectors) > QUERY_VECTOR_CACHE:
            self._query_vectors.popitem(last=False)
        return vector

    # -------------------------------------------------------------------
    # Mutation core — write / edit / mkdir and the topology verbs
    # -------------------------------------------------------------------

    async def write(
        self,
        *,
        entries: list[Entry],
        overwrite: bool = True,
        parents: bool = False,
        authority: Authority | None = None,
    ) -> Result:
        host = self._host
        entries, refused = await measured_entries(entries, offload_pool())
        if refused:
            return Result(ops=("write",), errors=refused)

        async def run(session: AsyncSession) -> Result:
            gate = await self._gate(session, authority, VERB_RUNGS["write"])
            if isinstance(gate, ResultError):
                return Result(ops=("write",), errors=[gate])
            if refused := await gate.targets(session, [e.path for e in entries], "upsert", parents=parents):
                return Result(ops=("write",), errors=refused)
            return await write_rows(
                session,
                host.tables,
                host.profile,
                host.parameter_budget,
                host.membership_budget,
                entries=entries,
                overwrite=overwrite,
                parents=parents,
                authority=self._named(authority),
                value_cap=host.value_cap,
            )

        return await self._execute_write("write", run)

    async def edit(
        self,
        *,
        edits: list[EditOperation],
        path: Path | None = None,
        observations: list[Observation] | None = None,
        authority: Authority | None = None,
    ) -> Result:
        targets = targets_of(path, observations)
        host = self._host

        async def run(session: AsyncSession) -> Result:
            gate = await self._gate(session, authority, VERB_RUNGS["edit"])
            if isinstance(gate, ResultError):
                return Result(ops=("edit",), errors=[gate])
            if refused := await gate.targets(session, targets, "modify"):
                return Result(ops=("edit",), errors=refused)
            return await edit_rows(
                session,
                host.tables,
                host.profile,
                host.parameter_budget,
                host.membership_budget,
                edits=edits,
                targets=targets,
                authority=self._named(authority),
                executor=offload_pool(),
            )

        return await self._execute_write("edit", run)

    async def delete(
        self,
        *,
        path: Path | None = None,
        observations: list[Observation] | None = None,
        cascade: bool = True,
        authority: Authority | None = None,
    ) -> Result:
        targets = targets_of(path, observations)

        async def gate(session: AsyncSession) -> list[ResultError]:
            checks = await self._gate(session, authority, VERB_RUNGS["delete"])
            if isinstance(checks, ResultError):
                return [checks]
            if refused := await checks.targets(session, targets, "modify"):
                return refused
            return await checks.subtrees(session, targets, checks.needs.primary) if cascade else []

        return await self._execute_topology(
            "delete",
            lambda session: delete_rows(
                session,
                self._host.tables,
                self._host.profile,
                self._host.parameter_budget,
                self._host.membership_budget,
                targets=targets,
                cascade=cascade,
                authority=authority,
                gate=gate,
            ),
        )

    async def restore(
        self,
        *,
        path: Path | None = None,
        observations: list[Observation] | None = None,
        authority: Authority | None = None,
    ) -> Result:
        targets = targets_of(path, observations)
        checks: WriteGate | None = None

        async def gate(session: AsyncSession) -> list[ResultError]:
            nonlocal checks
            resolved = await self._gate(session, authority, VERB_RUNGS["restore"])
            if isinstance(resolved, ResultError):
                return [resolved]
            checks = resolved
            return await checks.anonymous(session, targets)

        async def permit(
            session: AsyncSession, target: Path, row: Mapping[Any, Any] | None, verdict: ResultError | None
        ) -> ResultError | None:
            """The caller's verdict on one target, worded from the path it sent.

            The tombstoned row is judged at its own path with the label
            it kept, and a restore never mints an owner, so its owner may
            put back what it deleted. A row the caller cannot see is
            answered as the gate answers any target it cannot act on —
            absent, or denied when it is a directory on the road through
            the trash view. The ladder's own verdict stands only once the
            caller may see the row it names.
            """
            assert checks is not None
            if checks.whole:
                return None
            if row is None or not checks.view.shows(row):
                road = (
                    row is not None
                    and row["kind"] == "directory"
                    and await checks.view.road(session, [row["path"]], trashed=row["deleted_at"] is not None)
                )
                return denied(target) if road else await checks.missing(session, target)
            refused = checks.row(target, row["path"], row["owner_id"], row["everyone_level"], checks.needs.primary)
            if refused is None and row["kind"] == "directory":
                beneath = await checks.subtrees(session, [Path._brand(row["path"])], checks.needs.primary)
                refused = denied(target) if beneath else None
            if refused is None and verdict is not None and verdict.path != target:
                # The ladder named an ancestor: it is worded over what the caller may see.
                return await checks.missing(session, target)
            return refused

        return await self._execute_topology(
            "restore",
            lambda session: restore_rows(
                session,
                self._host.tables,
                self._host.profile,
                self._host.parameter_budget,
                self._host.membership_budget,
                targets=targets,
                authority=authority,
                gate=gate,
                permit=permit,
            ),
        )

    async def sweep(
        self,
        *,
        path: Path,
        authority: Authority | None = None,
    ) -> Result:
        async def gate(session: AsyncSession) -> list[ResultError]:
            checks = await self._gate(session, authority, VERB_RUNGS["sweep"])
            if isinstance(checks, ResultError):
                return [checks]
            if checks.whole:
                return []
            if path == TRASH_ROOT:
                # The retention arm may destroy a deleted row anywhere: it needs write over the whole mount.
                return [denied(path)] if await checks.subtrees(session, [ROOT], checks.needs.primary) else []
            if refused := await checks.targets(session, [path], "modify"):
                return refused
            return await checks.subtrees(session, [path], checks.needs.primary)

        return await self._execute_topology(
            "sweep",
            lambda session: sweep_rows(
                session,
                self._host.tables,
                self._host.profile,
                self._host.membership_budget,
                path=path,
                trash_days=self._trash_days,
                authority=authority,
                gate=gate,
            ),
        )

    async def mkdir(
        self,
        *,
        path: Path,
        parents: bool = False,
        exist_ok: bool = False,
        authority: Authority | None = None,
    ) -> Result:
        host = self._host

        async def run(session: AsyncSession) -> Result:
            gate = await self._gate(session, authority, VERB_RUNGS["mkdir"])
            if isinstance(gate, ResultError):
                return Result(ops=("mkdir",), errors=[gate])
            if refused := await gate.targets(session, [path], "create", parents=parents):
                return Result(ops=("mkdir",), errors=refused)
            return await mkdir_rows(
                session,
                host.tables,
                host.profile,
                host.parameter_budget,
                host.membership_budget,
                path=path,
                parents=parents,
                exist_ok=exist_ok,
                authority=authority,
            )

        return await self._execute_write("mkdir", run)

    async def move(
        self,
        *,
        operations: list[ResolvedPair],
        authority: Authority | None = None,
    ) -> Result:
        return await self._execute_transfer("move", operations, authority=authority)

    async def copy(
        self,
        *,
        operations: list[ResolvedPair],
        authority: Authority | None = None,
    ) -> Result:
        return await self._execute_transfer("copy", operations, authority=authority)

    async def mkedge(
        self,
        *,
        edges: list[Edge],
        provenance: str = "system",
        authority: Authority | None = None,
    ) -> Result:
        host = self._host

        async def run(session: AsyncSession) -> Result:
            gate = await self._gate(session, authority, VERB_RUNGS["mkedge"])
            if isinstance(gate, ResultError):
                return Result(ops=("mkedge",), errors=[gate])
            refused = await gate.targets(session, [edge.source for edge in edges], "modify")
            refused += await gate.targets(session, [edge.target for edge in edges], "read")
            if refused:
                return Result(ops=("mkedge",), errors=refused)
            return await mkedge_rows(
                session,
                host.tables,
                host.profile,
                host.parameter_budget,
                host.membership_budget,
                edges=edges,
                provenance=provenance,
                authority=authority,
            )

        return await self._execute_write("mkedge", run)

    async def rmedge(
        self,
        *,
        edges: list[Edge],
        authority: Authority | None = None,
    ) -> Result:
        host = self._host

        async def run(session: AsyncSession) -> Result:
            gate = await self._gate(session, authority, VERB_RUNGS["rmedge"])
            if isinstance(gate, ResultError):
                return Result(ops=("rmedge",), errors=[gate])
            if refused := await gate.targets(session, [edge.source for edge in edges], "modify"):
                return Result(ops=("rmedge",), errors=refused)
            # A target the caller cannot name is folded into the per-row record an absent one gets.
            targets = [edge.target for edge in edges]
            unnamed = {str(target) for target in targets} - await gate.named(session, targets)
            return await rmedge_rows(
                session,
                host.tables,
                host.profile,
                host.membership_budget,
                edges=edges,
                authority=authority,
                unnamed=unnamed,
            )

        return await self._execute_write("rmedge", run)

    # -------------------------------------------------------------------
    # Grants — the rows that decide who sees and writes what
    # -------------------------------------------------------------------

    async def grant(
        self, *, path: Path, principal: str, level: GrantLevel, authority: Authority | None = None
    ) -> Result:
        """Give *principal* (a ``sub`` or a ``group:`` id) *level* on *path* and below."""
        return await self._grant_write(
            "grant",
            authority,
            lambda session, gate, who, revision: grant_rows(
                session,
                self._host.tables,
                self._host.profile,
                self._host.membership_budget,
                gate,
                path=path,
                principal=principal,
                level=level,
                authority=who,
                revision=revision,
            ),
        )

    async def revoke(self, *, path: Path, principal: str, authority: Authority | None = None) -> Result:
        """Remove *principal*'s row on *path*; a missing row is a warning."""
        return await self._grant_write(
            "revoke",
            authority,
            lambda session, gate, who, revision: revoke_rows(
                session,
                self._host.tables,
                self._host.profile,
                self._host.membership_budget,
                gate,
                path=path,
                principal=principal,
                authority=who,
                revision=revision,
            ),
        )

    async def set_posture(self, *, path: Path, posture: Posture, authority: Authority | None = None) -> Result:
        """Set what everyone holds at *path* and below, named by the rung: ``none`` up to ``read_write``.

        The posture row commits first and is in force from then on; the
        verb then waits while the labels beneath it are rewritten, one
        bounded chunk per transaction, finishing any relabel an earlier
        call left pending on the way. The result reports the rows
        rewritten, the statements and the transactions it took.
        """
        written = await self._grant_write(
            "set_posture",
            authority,
            lambda session, gate, who, revision: set_posture(
                session,
                self._host.tables,
                self._host.profile,
                self._host.membership_budget,
                gate,
                path=path,
                posture=posture,
                authority=who,
                revision=revision,
            ),
        )
        if not written.success:
            return written
        return await self._settled(written)

    async def grants(self, *, path: Path, authority: Authority | None = None) -> Result:
        """The grant rows on *path* and its ancestors this authority may see."""
        who = self._named(authority)
        return await self._execute("grants", lambda session: listed_grants(session, self._host, self._gate, who, path))

    async def holds(self, *, path: Path, level: Rung, authority: Authority | None = None) -> Result:
        """Say whether ``authority`` holds ``level`` at ``path``. Nothing is written. A failed result says why not."""
        who = self._named(authority)
        return await self._execute(HOLDS, lambda session: held(session, self._host, self._gate, who, path, level))

    async def add_member(self, *, group: str, member: str, authority: Authority | None = None) -> Result:
        """Make *member* a direct member of *group* — the system actor only."""
        host = self._host
        who = self._named(authority)
        return await self._execute_write(
            "add_member",
            lambda session: add_member_rows(
                session, host.tables, host.profile, host.membership_budget, group=group, member=member, authority=who
            ),
        )

    async def remove_member(self, *, group: str, member: str, authority: Authority | None = None) -> Result:
        """Remove *member*'s direct membership of *group* — the system actor only."""
        who = self._named(authority)
        return await self._execute_write(
            "remove_member",
            lambda session: remove_member_rows(session, self._host.tables, group=group, member=member, authority=who),
        )

    # -------------------------------------------------------------------
    # Admin verbs — beside close(), outside the routed surface
    # -------------------------------------------------------------------

    async def first_touch(self) -> Result:
        """Provision-or-verify now instead of at the first routed op."""
        refusal = await self._host.ensure_ready()
        if refusal is not None:
            return Result(ops=("first_touch",), errors=[refusal])
        return Result(ops=("first_touch",))

    async def install_extensions(self) -> Result:
        """Install what this dialect requires and the connected role may — pgvector on PostgreSQL, nothing elsewhere.

        A developer-plane verb, opt-in and idempotent: first touch only
        proves the distance function is present and refuses naming the
        fix when it is not; this is the fix, from code, for a developer
        whose role may create extensions. It runs before first touch
        (the mount need not be provisioned) and proves the function
        afterwards, so a success here means first touch will not refuse
        on it. A role that may not install is answered
        ``permission_denied``; a dialect with nothing to install (SQLite's
        sqlite-vec ships with vfs; the other engines build the function
        in) succeeds with nothing done.
        """
        refusal = await self._host.install_extensions()
        if refusal is not None:
            return Result(ops=("install_extensions",), errors=[refusal])
        return Result(ops=("install_extensions",))

    async def rebuild(self) -> Result:
        """The full index pass; its contract is :class:`~vfs.storage.protocol.SupportsRebuild`'s."""
        return await rebuild(self._maintenance())

    async def refresh(self) -> Result:
        """The incremental index pass; its contract is :class:`~vfs.storage.protocol.SupportsRebuild`'s."""
        return await refresh(self._maintenance("refresh"))

    def _maintenance(self, verb: Literal["rebuild", "refresh"] = "rebuild") -> MaintenanceContext:
        """The pipeline's view of this backend, built per pass; the ranker is read when the signal phase starts."""
        return MaintenanceContext(
            host=self._host,
            renderers=self._renderers,
            render_limits=self._render_limits,
            ranker=lambda: self._ranker,
            embed_concurrency=self._embed_concurrency,
            embed_timeout=self._embed_timeout,
            execute=self._execute,
            execute_maintenance=self._execute_maintenance,
            execute_leased=self._execute_leased,
            rows=self._rows,
            verb=verb,
        )

    async def close(self) -> None:
        await self._host.close()

    # -------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------

    @staticmethod
    def _named(authority: Authority | None) -> Authority:
        """The authority a call acts under: a direct storage call naming none is trusted code, the system actor."""
        return _SYSTEM if authority is None else authority

    async def _resolution(
        self, session: AsyncSession, authority: Authority | None, *, cached: bool = True
    ) -> Resolution | ResultError:
        """The call's rights, resolved in its own transaction."""
        host = self._host
        return await resolve_authority(
            session,
            host.tables,
            host.profile,
            host.membership_budget,
            self._named(authority),
            self._rights if cached else None,
        )

    def _viewed(
        self,
        op: Op,
        authority: Authority | None,
        addressed: Iterable[str],
        build: Callable[[AsyncSession, Visibility | None], Awaitable[Result]],
        *,
        scoped: _ScopedGate | None = None,
    ) -> Callable[[AsyncSession], Awaitable[Result]]:
        """A read body run under the call's view — ``None`` when the view is the whole mount.

        *addressed* is every path the call names — its targets, or each
        pattern's literal prefix — where an anonymous caller is judged
        against the posture rows at the verb's rung before any row is
        read; a trash-view path is judged where its row sits. An
        anonymous call with a scope channel is judged by *scoped* instead,
        at the paths composition would have judged (:meth:`_scoped_refusals`).
        A verb that
        declares a ``passing`` rung (the graph walk) reads at that rung:
        the view narrows at it, the anonymous check judges at it, and the
        body projects a row whole only where the caller holds the primary.
        """
        host = self._host
        who = self._named(authority)
        needs = VERB_RUNGS[op]
        rung = needs.passing or needs.primary
        judged = [address_of(path).stored for path in addressed]

        async def run(session: AsyncSession) -> Result:
            resolution = await self._resolution(session, who)
            if isinstance(resolution, ResultError):
                return Result(ops=(op,), errors=[resolution])
            if scoped is not None:
                refused = await self._scoped_refusals(session, who, scoped, rung)
            else:
                refused = await unauthenticated_refusals(
                    session, host.tables, host.profile, host.membership_budget, who, judged, rung
                )
            if refused:
                return Result(ops=(op,), errors=refused)
            if resolution.at("read").whole:
                return await build(session, None)
            view = Visibility(
                resolution,
                rung,
                host.tables,
                host.profile,
                host.membership_budget,
                host.parameter_budget,
                road=not who.is_anonymous,
            )
            await view.prepare(session)
            return await build(session, view)

        return run

    def _scoped_gate(
        self,
        authority: Authority | None,
        patterns: tuple[str, ...],
        scope: AdmittedScope | None,
        piped: tuple[str, ...],
        wall_seconds: float,
    ) -> _ScopedGate | None:
        """The posture gate of an anonymous call with a scope channel; ``None`` for every other call.

        Only a caller judged by posture needs the scope's judged paths, so
        a named caller builds none and is judged, as ever, over the
        entry-wide patterns alone.
        """
        if scope is None or not self._named(authority).is_anonymous:
            return None
        return _ScopedGate(patterns, scope.channel, piped, wall_seconds)

    async def _scoped_refusals(
        self, session: AsyncSession, who: Authority, gate: _ScopedGate, rung: Rung
    ) -> list[ResultError]:
        """An anonymous scoped call's refusals, judged where composition judges, under the verb's wall.

        The judged paths are :func:`scope_judged`'s: the entry-wide patterns'
        beside each root's literal directory joined with each arm's. They are
        a product of the caller's inputs, so the pure work runs on the offload
        pool in two hops around the one chunked posture read: the judged paths
        and their sorted, chunked ancestor chain first, each path's refusal
        after. Each hop and the read check the wall, read when the gate
        starts; a gate that reaches it refuses the whole call as
        ``unauthenticated``, because a rights check never serves part of a
        call. The direction is judging each root once from the posture in
        force at it and the posture rows beneath it, linear in the roots.
        """
        host = self._host
        deadline = Deadline.after(gate.wall_seconds)
        budget = host.membership_budget

        def chained() -> tuple[list[str], list[list[str]]] | None:
            addressed = scope_judged(gate.patterns, gate.scope, deadline=deadline)
            if addressed is None:
                return None
            judged = list(dict.fromkeys(address_of(path).stored for path in (*addressed, *gate.piped)))
            chunks = posture_chain(judged, budget, deadline=deadline)
            return None if chunks is None else (judged, chunks)

        planned = await call_offloaded(offload_pool(), chained)
        if planned is None:
            return [posture_wall_refusal()]
        judged, chunks = planned
        postures = await posture_rows_for_chunks(session, host.tables, host.profile, chunks, deadline=deadline)
        if postures is None:
            return [posture_wall_refusal()]
        judge = partial(posture_refusals, who, postures, judged, rung, deadline=deadline)
        refusals = await call_offloaded(offload_pool(), judge)
        return [posture_wall_refusal()] if refusals is None else refusals

    async def _gate(
        self, session: AsyncSession, authority: Authority | None, needs: Needs, *, cached: bool = True
    ) -> WriteGate | ResultError:
        """The write gate for *needs*, kept on the attempt's session; an uncached one, an admin write's, is unfenced."""
        host = self._host
        opened = await opening(session, host.tables, self._named(authority), self._rights if cached else None)
        resolution = await self._resolution(session, authority, cached=cached)
        if isinstance(resolution, ResultError):
            return resolution
        gate = WriteGate(
            resolution,
            needs,
            host.tables,
            host.profile,
            host.membership_budget,
            host.parameter_budget,
            authority=self._named(authority),
        )
        return remember(session, gate, opened, self._rights)

    async def _grant_write(
        self,
        op: Op,
        authority: Authority | None,
        body: Callable[[AsyncSession, WriteGate, Authority, int], Awaitable[Result]],
    ) -> Result:
        """A grant-table write in one writer transaction: the lock, then the gate, then the body.

        The revision bump is the transaction's first statement, so rival
        admin writes serialize behind it; the gate is resolved under it,
        uncached, and judges what those rivals committed.
        """
        who = self._named(authority)
        tables = self._host.tables

        async def run(session: AsyncSession) -> Result:
            await seam("grants:before-lock")
            revision = await bump_revision(session, tables)
            gate = await self._gate(session, who, VERB_RUNGS[op], cached=False)
            if isinstance(gate, ResultError):
                return Result(ops=(op,), errors=[gate])
            await seam("grants:before-write")
            return await body(session, gate, who, revision)

        return await self._execute_write(op, run)

    async def _settled(self, written: Result) -> Result:
        """*written*, a posture verb's result, once every pending relabel has run to its end.

        One chunk per writer transaction, each bounded by the dialect's
        piece and row caps, so no transaction holds a subtree's worth of
        locks; a chunk that fails leaves its mark for the next call. The
        warnings *written* carried ride out on the final Result.
        """
        host = self._host
        relabeller = Relabeller(host.tables, host.profile, host.membership_budget)
        grants = (written.model_extra or {}).get("grants")
        done = Relabel(0, 0, 0)
        step: Relabel | None = None

        async def chunk(session: AsyncSession) -> Result:
            nonlocal step
            step = await relabeller.step(session)
            return Result(ops=("set_posture",))

        while True:
            outcome = await self._execute_maintenance("set_posture", chunk)
            if not outcome.success:
                return Result(ops=("set_posture",), grants=grants, errors=[*written.errors, *outcome.errors])
            if step is None:
                break
            done = done.plus(step)
            await seam("relabel:after-chunk")
        return Result(ops=("set_posture",), grants=grants, errors=list(written.errors), relabel=done._asdict())

    async def _execute(self, op: str, fn: Callable[[AsyncSession], Awaitable[Result]]) -> Result:
        """One op = one session under retry; failures come back classified.

        A declared op-isolation pin is stamped on the connection up front
        so every chunked statement observes one committed snapshot.
        """
        refusal = await self._host.ensure_ready()
        if refusal is not None:
            return Result(ops=(op,), errors=[refusal])
        try:
            return await self._rows(op, fn)
        except StaleSnapshot as exc:
            detail = f"{op} kept losing to concurrent changes: {exc.context}"
            return Result(ops=(op,), errors=[classified(ErrorKind.conflict, retryable=True, detail=detail)])
        except (SQLAlchemyError, OSError) as exc:
            # SQLAlchemyError, not just DBAPIError: pool exhaustion
            # (TimeoutError) is an operating condition, never a raise.
            return Result(ops=(op,), errors=[self._host.classify_failure(exc, context=op)])

    async def _rows(self, op: str, fn: Callable[[AsyncSession], Awaitable[T]]) -> T:
        """One read session under retry, answering whatever *fn* answers; driver failures escape raw.

        ``_execute`` wraps this with first touch and classification for
        the verbs; the embed step calls it bare, past first touch, for
        selects that answer rows rather than envelopes.
        """

        async def attempt() -> T:
            async with self._host.session_factory() as session:
                if options := op_execution_options(self._host.profile, writer=False):
                    await session.connection(execution_options=options)
                return await fn(session)

        return await self._host.with_retry(attempt)

    async def _execute_write(self, op: str, fn: Callable[[AsyncSession], Awaitable[Result]]) -> Result:
        """A public verb's batch = one writer transaction, committed iff the plan succeeded.

        The connection carries ``vfs_writer`` so SQLite opens the
        transaction ``BEGIN IMMEDIATE`` — the write lock is held from the
        plan's first read. This is the public verbs' runner, so the
        Result takes the host's held advisories at its one return; a
        maintenance commit, whose Result discards its errors, goes
        through :meth:`_execute_maintenance` and never does.
        """
        outcome = await self._mutate(op, fenced(fn, self._host), op_execution_options(self._host.profile, writer=True))
        return self._host.take_advisories(outcome)

    async def _execute_maintenance(self, op: str, fn: Callable[[AsyncSession], Awaitable[Result]]) -> Result:
        """An internal commit = one writer transaction whose Result is the caller's to fold or discard.

        The unfenced rebuild phases, in ``maintenance.py``, the lease's
        claim, beat and release, and the posture verb's relabel chunks
        commit here. Their Results never carry a held advisory: the phase
        folds or drops its errors, and a fact about the store's health
        must reach a caller, so it waits for the public verb that returns
        next.
        """
        return await self._mutate(op, fn, op_execution_options(self._host.profile, writer=True))

    async def _execute_leased(self, op: str, fn: Callable[[AsyncSession], Awaitable[Result]]) -> Result:
        """A lease-held commit under the topology pin, never the op snapshot: its fence and guards read the
        latest commit, so none fails against the run's own heartbeat."""
        return await self._mutate(op, fn, topology_execution_options(self._host.profile))

    async def _execute_transfer(
        self, op: Literal["move", "copy"], operations: list[ResolvedPair], *, authority: Authority | None
    ) -> Result:
        """Move or copy under the gate: a moved source is modified and a copied one read, whole
        subtrees included; every destination is a creation."""
        needs = VERB_RUNGS[op]
        passing: Rung = needs.primary if op == "move" else needs.passing or needs.primary

        async def gate(session: AsyncSession) -> list[ResultError]:
            checks = await self._gate(session, authority, needs)
            if isinstance(checks, ResultError):
                return [checks]
            sources = [pair.src for pair in operations]
            refused = await checks.targets(session, sources, "modify" if op == "move" else "read")
            refused += await checks.targets(
                session, [pair.dest for pair in operations if pair.dest != pair.src], "create"
            )
            refused = refused or await checks.subtrees(session, sources, passing)
            return refused or await admit_destinations(session, self._host, checks, op, operations)

        return await self._execute_topology(
            op,
            lambda session: transfer_rows(
                session,
                self._host.tables,
                self._host.profile,
                self._host.parameter_budget,
                self._host.membership_budget,
                op=op,
                operations=operations,
                authority=authority,
                gate=gate,
            ),
        )

    async def _execute_topology(self, op: str, fn: Callable[[AsyncSession], Awaitable[Result]]) -> Result:
        """One batch = one serialized transaction; the point is its first statement.

        Topology options trade the op snapshot for the serialization
        point: the writer marker plus the declared topology-isolation
        pin, never ``op_isolation``. Every topology verb is public, so
        its Result takes the host's held advisories here.
        """
        outcome = await self._mutate(op, fenced(fn, self._host), topology_execution_options(self._host.profile))
        return self._host.take_advisories(outcome)

    async def _mutate(
        self, op: str, fn: Callable[[AsyncSession], Awaitable[Result]], options: dict[str, str | bool]
    ) -> Result:
        """The shared mutation runner: commit iff the batch succeeded.

        A retryable outcome discards the session and restarts the whole
        method from its first read; a failed batch returns classified
        errors and the session rolls back on exit.

        Where the engine keeps planner statistics through vfs, a
        successful batch detects, inside this same transaction and
        before the commit, whether SQLite's growth listing names one of
        the mount's indexed tables; the analysis of a crossing runs
        after the write returns, in the host's own task, out of the
        caller's reach. The runner never reports a statistics failure;
        the public runner that returns next does, as an advisory.
        """
        refusal = await self._host.ensure_ready()
        if refusal is not None:
            return Result(ops=(op,), errors=[refusal])
        due: frozenset[str] | ResultError = frozenset()

        async def attempt() -> Result:
            nonlocal due
            due = frozenset()
            async with self._host.session_factory() as session:
                await session.connection(execution_options=options)
                result = await fn(session)
                if result.success:
                    if self._host.statistics_enabled:
                        due = await self._host.detect_due(await session.connection())
                    await session.commit()
                return result

        try:
            result = await self._host.with_retry(attempt)
        except StaleSnapshot as exc:
            # Guards kept proving the snapshot stale through every redrive:
            # an honest transient outcome, never a torn commit.
            detail = f"{op} kept losing to concurrent changes: {exc.context}"
            return Result(ops=(op,), errors=[classified(ErrorKind.conflict, retryable=True, detail=detail)])
        except (SQLAlchemyError, OSError) as exc:
            return Result(ops=(op,), errors=[self._host.classify_failure(exc, context=op)])
        if isinstance(due, frozenset) and due:
            self._host.request_analysis()
        return result
