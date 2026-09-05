"""``DatabaseStorage`` — the portable SQL backend (reads, glob, mutation core).

Runs on any SQLAlchemy-compatible database: known dialects carry tuned
policy, everything else serves on the generic floor (``dialects.py``).
The read family and both pattern verbs are live — point reads with
projection push-down, ``parent_id`` listings, glob's batched pattern
fan, grep's indexed pipeline (``grep.py``), and the descent-ladder
classification chokepoint (``descent.py`` / ``reads.py``) — as are the
mutation core (write/edit/mkdir batches planned and executed as one
transaction each, ``writes.py``), the serialized topology verbs
delete/restore/move/copy (``topology.py``), and the edge pair
``mkedge``/``rmedge`` over the same table as the storage-minted fs
mirror (``edges.py``).

    storage = DatabaseStorage(url="sqlite+aiosqlite:///vfs.sqlite")     # built
    storage = DatabaseStorage(session_factory=app_sessionmaker)         # borrowed

Built or borrowed, never a bare engine: a backend builds its engine or
borrows sessions — it never holds an engine it didn't make. First touch
happens at the first routed op (or the ``first_touch`` admin verb) on
the caller's loop; ``close()`` disposes the engine iff built and never
touches a borrowed pool. Each protocol method runs in one session under
the retry discipline: a retryable outcome restarts the whole method
from its first read, and a driver failure that escapes retry returns a
classified ``Result`` — never a raw exception.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from contextlib import asynccontextmanager, suppress
from functools import partial
from typing import TYPE_CHECKING, Literal, TypeVar

from sqlalchemy.exc import SQLAlchemyError
from ulid import ULID

from vfs.models.rows import PGVECTOR_INDEX_MAX_DIMENSION
from vfs.results import Result, ResultError, Severity, VFSErrorKind
from vfs.storage.backends.database.descent import ROOT
from vfs.storage.backends.database.dialects import (
    PROFILES,
    StaleSnapshot,
    op_execution_options,
    topology_execution_options,
)
from vfs.storage.backends.database.edges import (
    EdgeRebuildState,
    collect_edge_drift,
    mkedge_rows,
    repair_edge_drift,
    rmedge_rows,
)
from vfs.storage.backends.database.embed import (
    EMBED_CONCURRENCY,
    EMBED_PAGE_ROWS,
    EMBED_TIMEOUT_SECONDS,
    EmbedReport,
    cached_vectors,
    clear_embeddings,
    count_unembedded,
    embed_page,
    read_identity,
    select_unembedded,
    unit_vector,
    write_vectors,
)
from vfs.storage.backends.database.engine import EngineHost
from vfs.storage.backends.database.glean import VectorLeg, glean_rows
from vfs.storage.backends.database.grep import WALL_TIME_BUDGET, grep_rows
from vfs.storage.backends.database.indexing import (
    REINDEX_HEARTBEAT_SECONDS,
    ReindexState,
    build_epoch,
    chunk_dirty,
    claim_reindex_lease,
    heartbeat_reindex_lease,
    lease_lost,
    lease_lost_result,
    publish_epoch,
    reclaim_built_epoch,
    reclaim_epochs,
    release_reindex_lease,
)
from vfs.storage.backends.database.reads import glob_rows, ls_rows, read_rows, stat_rows, tree_rows
from vfs.storage.backends.database.seams import seam
from vfs.storage.backends.database.segments import (
    SegmentRebuildState,
    collect_segment_drift,
    repair_segment_drift,
)
from vfs.storage.backends.database.topology import delete_rows, restore_rows, sweep_rows, transfer_rows
from vfs.storage.backends.database.writes import edit_rows, mkdir_rows, write_rows
from vfs.storage.protocol import storage_ops, targets_of
from vfs.storage.ranking import Ranker

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Mapping

    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.embedding import EmbeddingProvider
    from vfs.models import Edge, Entry, Observation
    from vfs.models.rows import VFSTables
    from vfs.models.vector import NativeEmbeddingConfig
    from vfs.ops import CaseMode, GrepOutputMode, Op
    from vfs.paths import ObjectKind, Path
    from vfs.storage import ResolvedPair
    from vfs.storage.replace import EditOperation

T = TypeVar("T")

QUERY_VECTOR_CACHE = 256
"""Embedded queries remembered per mount — a re-asked question costs no provider call."""

PGVECTOR_ITERATIVE_SCAN = "SET LOCAL hnsw.iterative_scan = relaxed_order"
"""pgvector 0.8+: keep scanning the HNSW index until a scoped query's window fills."""


class DatabaseStorage:
    """One mount's portable database backend over SQLAlchemy Core."""

    def __init__(
        self,
        *,
        url: str | None = None,
        session_factory: Callable[[], AsyncSession] | None = None,
        table_name: str = "vfs",
        schema: str | None = None,
        name: str = "database",
        description: str | None = None,
        trash_days: int = 90,
        grep_wall_seconds: float = WALL_TIME_BUDGET,
        glean_wall_seconds: float = WALL_TIME_BUDGET,
        embedder: EmbeddingProvider | None = None,
        native_embedding: NativeEmbeddingConfig | None = None,
        embed_concurrency: int = EMBED_CONCURRENCY,
        embed_timeout_seconds: float = EMBED_TIMEOUT_SECONDS,
        ranker: Ranker | None = None,
    ) -> None:
        if trash_days < 0:
            msg = f"trash_days must be non-negative, got {trash_days}"
            raise ValueError(msg)
        if grep_wall_seconds <= 0:
            msg = f"grep_wall_seconds must be positive, got {grep_wall_seconds}"
            raise ValueError(msg)
        if embed_concurrency < 1:
            msg = f"embed_concurrency must be at least 1, got {embed_concurrency}"
            raise ValueError(msg)
        if embed_timeout_seconds <= 0:
            msg = f"embed_timeout_seconds must be positive, got {embed_timeout_seconds}"
            raise ValueError(msg)
        self._host = EngineHost(
            url=url,
            session_factory=session_factory,
            table_name=table_name,
            schema=schema,
            embedder=embedder,
            native_embedding=native_embedding,
        )
        self._trash_days = trash_days
        self._embed_concurrency = embed_concurrency
        self._embed_timeout = embed_timeout_seconds
        self._ranker = ranker if ranker is not None else Ranker()
        # The last queries' vectors, keyed by space: a re-asked question costs no provider call.
        self._query_vectors: OrderedDict[tuple[str, str], list[float]] = OrderedDict()
        if glean_wall_seconds <= 0:
            msg = f"glean_wall_seconds must be positive, got {glean_wall_seconds}"
            raise ValueError(msg)
        self._grep_wall_seconds = grep_wall_seconds
        self._glean_wall_seconds = glean_wall_seconds
        self.name = name
        # Construction stays dialect-free: a borrowed host knows its
        # dialect only at first use, so the default names the tables.
        self.description = description or f"Database storage ({table_name})"

    @property
    def mount_identity(self) -> str | None:
        """The durable mount identity, known after first touch."""
        return self._host.mount_identity

    @property
    def embedder(self) -> EmbeddingProvider | None:
        """The configured embedding provider; ``None`` serves glean lexical-only."""
        return self._host.embedder

    @property
    def ranker(self) -> Ranker:
        """The mount's ranking declaration: its fusion and its chunk aggregate."""
        return self._ranker

    def capabilities(self) -> frozenset[Op]:
        """The method surface, minus what this mount cannot vouch for.

        An unknown dialect serves the core verbs on the generic floor
        and withholds ``glean``: ranked search needs a cosine distance
        in the engine, which only a tuned profile declares.
        """
        withheld: set[Op] = set()
        if self._host.profile.vector_distance == "none":
            withheld.add("glean")
        return storage_ops(self) - withheld

    def traits(self) -> Mapping[str, str]:
        declared = {
            "version_encoding": "per_entry64",
            "arbitration": self._host.profile.arbitration,
            "grep_tier": "indexed",
            "grep_staleness": "overlay",
            "glean_signals": "hybrid" if self._host.embedder is not None else "lexical",
            "glean_staleness": "overlay",
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
        user_id: str | None = None,
    ) -> Result:
        targets = targets_of(path, observations)
        return await self._execute(
            "read",
            lambda session: read_rows(
                session, self._host.tables, self._host.profile, self._host.membership_budget, targets, columns
            ),
        )

    async def stat(
        self,
        *,
        path: Path | None = None,
        observations: list[Observation] | None = None,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        targets = targets_of(path, observations)
        return await self._execute(
            "stat",
            lambda session: stat_rows(
                session, self._host.tables, self._host.profile, self._host.membership_budget, targets, columns
            ),
        )

    async def ls(
        self,
        *,
        path: Path | None = None,
        observations: list[Observation] | None = None,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        targets = targets_of(path, observations, default=ROOT)
        return await self._execute(
            "ls",
            lambda session: ls_rows(
                session,
                self._host.tables,
                self._host.profile,
                self._host.membership_budget,
                targets,
                columns,
            ),
        )

    async def tree(
        self,
        *,
        path: Path,
        max_depth: int | None = None,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        if max_depth is not None and max_depth < 1:
            return Result(
                ops=("tree",),
                errors=[ResultError(kind=VFSErrorKind.invalid, message=f"max_depth must be >= 1, got {max_depth}")],
            )
        return await self._execute(
            "tree",
            lambda session: tree_rows(
                session,
                self._host.tables,
                self._host.profile,
                self._host.membership_budget,
                path,
                max_depth,
                columns,
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
        user_id: str | None = None,
    ) -> Result:
        return await self._execute(
            "glob",
            lambda session: glob_rows(
                session,
                self._host.tables,
                self._host.profile,
                self._host.parameter_budget,
                self._host.membership_budget,
                patterns=patterns,
                globs_not=globs_not,
                ext=ext,
                ext_not=ext_not,
                kind=kind,
                max_count=max_count,
                columns=columns,
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
        user_id: str | None = None,
    ) -> Result:
        return await self._execute(
            "grep",
            lambda session: grep_rows(
                session,
                self._host.tables,
                self._host.profile,
                self._host.parameter_budget,
                self._host.membership_budget,
                self._host.offload_executor,
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
            ),
        )

    # -------------------------------------------------------------------
    # Ranked search
    # -------------------------------------------------------------------

    async def glean(
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
        user_id: str | None = None,
    ) -> Result:
        refusal = await self._host.ensure_ready()
        if refusal is not None:
            return Result(ops=("glean",), errors=[refusal])
        scoped = bool(ext or ext_not or globs or globs_not or observations)
        vector, records = await self._vector_leg_for(query, scoped=scoped)
        return await self._execute(
            "glean",
            lambda session: glean_rows(
                session,
                self._host.tables,
                self._host.profile,
                self._host.parameter_budget,
                self._host.membership_budget,
                self._host.offload_executor,
                query=query,
                limit=limit,
                ext=ext,
                ext_not=ext_not,
                globs=globs,
                globs_not=globs_not,
                observations=observations,
                columns=columns,
                wall_seconds=self._glean_wall_seconds,
                dialect_name=self._host.profile.name,
                vector=vector,
                ranker=self._ranker,
                records=records,
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
            note = ResultError(
                kind=VFSErrorKind.unavailable,
                severity=Severity.info,
                message="no embedding provider is configured; the lexical leg alone answered",
                data={"leg": "vector", "reason": "no_provider"},
            )
            return None, [note]
        stored = self._host.embedding_identity
        if self._host.embedding_stale and stored is not None:
            note = ResultError(
                kind=VFSErrorKind.conflict,
                severity=Severity.warning,
                message=(
                    f"the stored embeddings belong to {stored[0]!r} at {stored[1]} but the mount is configured for "
                    f"{provider.model_id!r}; the lexical leg alone answered — run reindex to migrate"
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
            note = ResultError(
                kind=VFSErrorKind.unavailable,
                severity=Severity.warning,
                message=f"embedding the query failed ({type(exc).__name__}: {exc}); the lexical leg alone answered",
                retryable=True,
                data={"leg": "vector", "reason": "embed_failed", "provider": provider.model_id},
            )
            return None, [note]
        profile = self._host.profile
        indexed = self._host.native_embedding is not None and self._ann_indexed()
        ann = profile.vector_distance == "ann" and indexed and (not scoped or profile.ann_honours_scope)
        prelude = None
        if ann and profile.name == "postgresql" and (self._host.pgvector_version or ()) >= (0, 8):
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
        """The query's unit vector, memoised per space under the glean wall budget."""
        key = (provider.model_id, query)
        cached = self._query_vectors.get(key)
        if cached is not None:
            self._query_vectors.move_to_end(key)
            return cached
        vector = unit_vector(await asyncio.wait_for(provider.embed_query(query), self._glean_wall_seconds))
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
        user_id: str | None = None,
    ) -> Result:
        return await self._execute_write(
            "write",
            lambda session: write_rows(
                session,
                self._host.tables,
                self._host.profile,
                self._host.parameter_budget,
                self._host.membership_budget,
                entries=entries,
                overwrite=overwrite,
                parents=parents,
                user_id=user_id,
            ),
        )

    async def edit(
        self,
        *,
        edits: list[EditOperation],
        path: Path | None = None,
        observations: list[Observation] | None = None,
        user_id: str | None = None,
    ) -> Result:
        targets = targets_of(path, observations)
        return await self._execute_write(
            "edit",
            lambda session: edit_rows(
                session,
                self._host.tables,
                self._host.profile,
                self._host.parameter_budget,
                self._host.membership_budget,
                edits=edits,
                targets=targets,
                user_id=user_id,
            ),
        )

    async def delete(
        self,
        *,
        path: Path | None = None,
        observations: list[Observation] | None = None,
        cascade: bool = True,
        user_id: str | None = None,
    ) -> Result:
        targets = targets_of(path, observations)
        return await self._execute_topology(
            "delete",
            lambda session: delete_rows(
                session,
                self._host.tables,
                self._host.profile,
                self._host.membership_budget,
                targets=targets,
                cascade=cascade,
                user_id=user_id,
                lock_key=self._host.topology_key,
            ),
        )

    async def restore(
        self,
        *,
        path: Path | None = None,
        observations: list[Observation] | None = None,
        user_id: str | None = None,
    ) -> Result:
        targets = targets_of(path, observations)
        return await self._execute_topology(
            "restore",
            lambda session: restore_rows(
                session,
                self._host.tables,
                self._host.profile,
                self._host.membership_budget,
                targets=targets,
                user_id=user_id,
                lock_key=self._host.topology_key,
            ),
        )

    async def sweep(
        self,
        *,
        path: Path,
        user_id: str | None = None,
    ) -> Result:
        return await self._execute_topology(
            "sweep",
            lambda session: sweep_rows(
                session,
                self._host.tables,
                self._host.profile,
                self._host.membership_budget,
                path=path,
                trash_days=self._trash_days,
                user_id=user_id,
                lock_key=self._host.topology_key,
            ),
        )

    async def mkdir(
        self,
        *,
        path: Path,
        parents: bool = False,
        exist_ok: bool = False,
        user_id: str | None = None,
    ) -> Result:
        return await self._execute_write(
            "mkdir",
            lambda session: mkdir_rows(
                session,
                self._host.tables,
                self._host.profile,
                self._host.parameter_budget,
                self._host.membership_budget,
                path=path,
                parents=parents,
                exist_ok=exist_ok,
                user_id=user_id,
            ),
        )

    async def move(
        self,
        *,
        operations: list[ResolvedPair],
        user_id: str | None = None,
    ) -> Result:
        return await self._execute_transfer("move", operations, user_id=user_id)

    async def copy(
        self,
        *,
        operations: list[ResolvedPair],
        user_id: str | None = None,
    ) -> Result:
        return await self._execute_transfer("copy", operations, user_id=user_id)

    async def mkedge(
        self,
        *,
        edges: list[Edge],
        provenance: str = "system",
        user_id: str | None = None,
    ) -> Result:
        return await self._execute_write(
            "mkedge",
            lambda session: mkedge_rows(
                session,
                self._host.tables,
                self._host.profile,
                self._host.membership_budget,
                edges=edges,
                provenance=provenance,
                user_id=user_id,
            ),
        )

    async def rmedge(
        self,
        *,
        edges: list[Edge],
        user_id: str | None = None,
    ) -> Result:
        return await self._execute_write(
            "rmedge",
            lambda session: rmedge_rows(
                session,
                self._host.tables,
                self._host.profile,
                self._host.membership_budget,
                edges=edges,
                user_id=user_id,
            ),
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

    async def reindex(self) -> Result:
        """Batch index maintenance: segments re-converged, gram epochs rebuilt.

        One runner at a time: the verb claims the single-runner lease up
        front — a live rival refuses loudly with a retryable conflict —
        and releases it best-effort at the end; a crashed run frees the
        lease by heartbeat expiry. The segment pass re-converges the
        path-segment postings to the recomputed truth under per-row path
        guards, reporting any found drift loudly. The gram side is
        idempotent-cheap when nothing is dirty and the epoch fingerprint
        matches; each phase runs in its own writer transaction, and
        posting rows are invisible until the publish transaction flips
        the ``encoded`` flags and the epoch pointer together.
        """
        tables = self._host.tables
        token = str(ULID())
        claimed = await self._execute_write("reindex", lambda session: claim_reindex_lease(session, tables, token))
        if not claimed.success:
            return claimed
        async with self._held_reindex_lease(tables, token) as lost:
            result = await self._reindex_phases(tables, lost)
            if not result.success or self._host.embedder is None:
                return result
            embedded = await self._embed_step(tables, lost)
            errors = [*result.errors, *embedded.errors]
            extras = dict(embedded.model_extra or {})
            return Result(ops=result.ops, observations=result.observations, errors=errors, **extras)

    @asynccontextmanager
    async def _held_reindex_lease(self, tables: VFSTables, token: str) -> AsyncIterator[asyncio.Event]:
        """Hold a claimed lease: beat underneath, then cancel and release.

        The beat task is cancelled and awaited *before* the best-effort
        release, so a stray beat can never resurrect a released lease.
        The yielded event is set when a beat proves the lease taken.
        """
        lost = asyncio.Event()
        beat = asyncio.create_task(self._beat_reindex_lease(tables, token, lost))
        try:
            yield lost
        finally:
            beat.cancel()
            with suppress(asyncio.CancelledError):
                await beat
            await self._execute_write("reindex", lambda session: release_reindex_lease(session, tables, token))

    async def _beat_reindex_lease(self, tables: VFSTables, token: str, lost: asyncio.Event) -> None:
        """Pulse the lease heartbeat until cancelled or proven taken.

        A transient beat failure is not a lost lease — the TTL absorbs
        missed pulses, including a beat that never reaches its UPDATE
        because the build phase holds SQLite's write lock for longer
        than the beat's retries (that exhaustion is a ``conflict`` too);
        only the zero-row refresh, the marked lease-lost verdict, means
        a rival claimed through, and then the run must stop.
        """
        while True:
            await asyncio.sleep(REINDEX_HEARTBEAT_SECONDS)
            beat = await self._execute_write("reindex", lambda session: heartbeat_reindex_lease(session, tables, token))
            if lease_lost(beat):
                lost.set()
                return

    async def _reindex_phases(self, tables: VFSTables, lost: asyncio.Event) -> Result:
        """The lease-held phases: the gram epochs, then the re-convergence passes.

        The segment pass rebuilds the path-segment postings and the edge
        pass re-converges the fs mirror to ``parent_id`` — each wholesale
        in effect, guarded delta in application: a plain read diffs the
        table against the recomputed truth, and only found drift opens a
        writer transaction, applied under per-row guards. Their warnings
        (drift is a maintenance bug surfacing) ride on the verb's final
        Result.
        """
        result = await self._gram_phases(tables, lost)
        if not result.success:
            return result
        warnings: list[ResultError] = []
        segment_state = SegmentRebuildState()
        outcome = await self._reconverge(
            lost,
            lambda session: collect_segment_drift(session, tables, segment_state),
            lambda session: repair_segment_drift(
                session, tables, self._host.profile, self._host.membership_budget, segment_state
            ),
            lambda: segment_state.clean,
        )
        if isinstance(outcome, Result):
            return outcome
        warnings.extend(outcome)
        edge_state = EdgeRebuildState()
        outcome = await self._reconverge(
            lost,
            lambda session: collect_edge_drift(session, tables, edge_state),
            lambda session: repair_edge_drift(
                session, tables, self._host.profile, self._host.membership_budget, edge_state
            ),
            lambda: edge_state.clean,
        )
        if isinstance(outcome, Result):
            return outcome
        warnings.extend(outcome)
        if not warnings:
            return result
        return Result(ops=result.ops, observations=result.observations, errors=[*result.errors, *warnings])

    async def _reconverge(
        self,
        lost: asyncio.Event,
        collect: Callable[[AsyncSession], Awaitable[Result]],
        repair: Callable[[AsyncSession], Awaitable[Result]],
        clean: Callable[[], bool],
    ) -> Result | list[ResultError]:
        """One collect/repair pass: its warnings on success, the failing Result otherwise."""
        collected = await self._execute("reindex", collect)
        if not collected.success:
            return collected
        if clean():
            return []
        if lost.is_set():
            return lease_lost_result()
        repaired = await self._execute_write("reindex", repair)
        if not repaired.success:
            return repaired
        return list(repaired.errors)

    async def _gram_phases(self, tables: VFSTables, lost: asyncio.Event) -> Result:
        """The gram-index phases; a lost lease stops at the next boundary."""
        state = ReindexState()
        result = await self._execute_write(
            "reindex",
            lambda session: chunk_dirty(
                session,
                tables,
                self._host.profile,
                self._host.parameter_budget,
                self._host.membership_budget,
                self._host.offload_executor,
                carry_embeddings=not self._host.embedding_stale,
            ),
        )
        if not result.success:
            return result
        if lost.is_set():
            return lease_lost_result()
        result = await self._execute_write(
            "reindex", lambda session: build_epoch(session, tables, state, self._host.offload_executor)
        )
        if not result.success or state.epoch is None:
            return result
        await seam("reindex:before-publish")
        if lost.is_set():
            return lease_lost_result()
        epoch = state.epoch
        result = await self._execute_write(
            "reindex",
            lambda session: publish_epoch(
                session, tables, self._host.profile, self._host.parameter_budget, self._host.membership_budget, state
            ),
        )
        if not result.success:
            # The lost build's rows are unpublished residue — reclaim them
            # so a rival's next mint is not forced past a dead number.
            await self._execute_write("reindex", lambda session: reclaim_built_epoch(session, tables, epoch))
            return result
        await seam("reindex:before-reclaim")
        return await self._execute_write("reindex", lambda session: reclaim_epochs(session, tables))

    async def _embed_step(self, tables: VFSTables, lost: asyncio.Event) -> Result:
        """Fill every NULL embedding in short, resumable batches under the held lease.

        A stale stored identity is migrated first — every vector
        cleared, the pair unstamped — so the first batch written stamps
        the configured space. Pages advance by keyset; each page's
        batches embed with no transaction open and land in one short
        write; the lease's ``lost`` flag is checked between pages. A
        provider failure ends the step with a warning and leaves the
        rest NULL for the next run; the result's ``embedding`` extra
        reports the counts, at warning severity when rows remain.
        """
        provider = self._host.embedder
        assert provider is not None
        identity = (provider.model_id, provider.dimension)
        # Re-read, never trusted from first touch: a rival's run may have stamped or migrated since.
        self._host.embedding_identity = await self._rows("reindex", partial(read_identity, tables=tables))
        if self._host.embedding_identity is not None and self._host.embedding_identity != identity:
            cleared = await self._execute_write("reindex", lambda session: clear_embeddings(session, tables))
            if not cleared.success:
                return cleared
            self._host.embedding_identity = None
        report = EmbedReport()
        semaphore = asyncio.Semaphore(self._embed_concurrency)
        known: dict[str, list[float]] = {}
        budget = self._host.membership_budget
        last = 0
        while not lost.is_set():
            page = await self._rows(
                "reindex", partial(select_unembedded, tables=tables, after=last, limit=EMBED_PAGE_ROWS)
            )
            if not page:
                break
            last = page[-1].id
            hashes = [
                row.content_hash for row in page if row.content_hash is not None and row.content_hash not in known
            ]
            lend = partial(
                cached_vectors, tables=tables, profile=self._host.profile, hashes=hashes, membership_budget=budget
            )
            known.update(await self._rows("reindex", lend))
            await seam("reindex:before-embed")
            outcome = await embed_page(page, provider, known, report, semaphore, timeout=self._embed_timeout)
            stamp = identity if outcome.vectors and self._host.embedding_identity is None else None
            land = partial(write_vectors, tables=tables, pairs=outcome.vectors, stamp=stamp)
            written = await self._execute_write("reindex", land)
            if not written.success:
                return written
            if outcome.vectors:
                self._host.embedding_identity = identity
            if outcome.failure is not None:
                report.stopped_by = f"{type(outcome.failure).__name__}: {outcome.failure}"
                break
        if lost.is_set():
            return lease_lost_result()
        report.unembedded = await self._rows("reindex", lambda session: count_unembedded(session, tables))
        errors: list[ResultError] = []
        if report.stopped_by is not None:
            errors.append(
                ResultError(
                    kind=VFSErrorKind.unavailable,
                    severity=Severity.warning,
                    message=f"embedding stopped after {report.requests} requests: {report.stopped_by}",
                    retryable=True,
                    data={"provider": provider.model_id},
                )
            )
        return Result(ops=("reindex",), errors=errors, embedding=report.as_extra(provider.model_id))

    async def close(self) -> None:
        await self._host.close()

    # -------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------

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
            message = f"{op} kept losing to concurrent changes: {exc.context}"
            return Result(ops=(op,), errors=[ResultError(kind=VFSErrorKind.conflict, message=message, retryable=True)])
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
        """One batch = one writer transaction, committed iff the plan succeeded.

        The connection carries ``vfs_writer`` so SQLite opens the
        transaction ``BEGIN IMMEDIATE`` — the write lock is held from the
        plan's first read.
        """
        return await self._mutate(op, fn, op_execution_options(self._host.profile, writer=True))

    async def _execute_transfer(
        self, op: Literal["move", "copy"], operations: list[ResolvedPair], *, user_id: str | None
    ) -> Result:
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
                user_id=user_id,
                lock_key=self._host.topology_key,
            ),
        )

    async def _execute_topology(self, op: str, fn: Callable[[AsyncSession], Awaitable[Result]]) -> Result:
        """One batch = one serialized transaction; the point is its first statement.

        Topology options trade the op snapshot for the serialization
        point: the writer marker plus the declared topology-isolation
        pin, never ``op_isolation``.
        """
        return await self._mutate(op, fn, topology_execution_options(self._host.profile))

    async def _mutate(
        self, op: str, fn: Callable[[AsyncSession], Awaitable[Result]], options: dict[str, str | bool]
    ) -> Result:
        """The shared mutation runner: commit iff the batch succeeded.

        A retryable outcome discards the session and restarts the whole
        method from its first read; a failed batch returns classified
        errors and the session rolls back on exit.
        """
        refusal = await self._host.ensure_ready()
        if refusal is not None:
            return Result(ops=(op,), errors=[refusal])

        async def attempt() -> Result:
            async with self._host.session_factory() as session:
                await session.connection(execution_options=options)
                result = await fn(session)
                if result.success:
                    await session.commit()
                return result

        try:
            return await self._host.with_retry(attempt)
        except StaleSnapshot as exc:
            # Guards kept proving the snapshot stale through every redrive:
            # an honest transient outcome, never a torn commit.
            message = f"{op} kept losing to concurrent changes: {exc.context}"
            return Result(ops=(op,), errors=[ResultError(kind=VFSErrorKind.conflict, message=message, retryable=True)])
        except (SQLAlchemyError, OSError) as exc:
            return Result(ops=(op,), errors=[self._host.classify_failure(exc, context=op)])
