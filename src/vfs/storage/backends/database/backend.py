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

from vfs.authority import Authority
from vfs.models.rows import PGVECTOR_INDEX_MAX_DIMENSION
from vfs.paths import Path, is_trash_path
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
    with_notes,
)
from vfs.storage.backends.database.labels import Relabel, Relabeller, labels_for
from vfs.storage.backends.database.reads import glob_rows, ls_rows, read_rows, stat_rows, tree_rows
from vfs.storage.backends.database.revision import bump_revision
from vfs.storage.backends.database.rights import (
    RightsCache,
    Visibility,
    WriteGate,
    add_member_rows,
    denied,
    grant_rows,
    judged_path,
    list_grants,
    posture_refusal,
    remove_member_rows,
    resolve_authority,
    revoke_rows,
    set_posture,
)
from vfs.storage.backends.database.seams import seam
from vfs.storage.backends.database.segments import (
    SegmentRebuildState,
    collect_segment_drift,
    repair_segment_drift,
)
from vfs.storage.backends.database.signals import (
    collect_graph,
    compute_signal,
    publish_signal,
    sweep_undeclared_signals,
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
    from vfs.paths import ObjectKind
    from vfs.storage import ResolvedPair
    from vfs.storage.backends.database.rights import Resolution
    from vfs.storage.backends.database.topology import RestoreLookup, RestoreSource
    from vfs.storage.grants import GrantLevel, Posture
    from vfs.storage.replace import EditOperation

T = TypeVar("T")

_SYSTEM = Authority.system()

QUERY_VECTOR_CACHE = 256
"""Embedded queries remembered per mount — a re-asked question costs no provider call."""

PGVECTOR_ITERATIVE_SCAN = "SET LOCAL hnsw.iterative_scan = relaxed_order"
"""pgvector 0.8+: keep scanning the HNSW index until a scoped query's window fills."""


class DatabaseStorage:
    """One mount's portable database backend over SQLAlchemy Core.

    *posture* is what everyone holds at the root of a freshly provisioned
    mount — ``open``, ``shared`` or ``private``. It is planted once, at
    first touch: a mount that already exists keeps its stored posture,
    and only the ``posture`` verb changes it.
    """

    def __init__(
        self,
        *,
        url: str | None = None,
        session_factory: Callable[[], AsyncSession] | None = None,
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
        posture: Posture = "open",
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
        # The last queries' vectors, keyed by space: a re-asked question costs no provider call.
        self._query_vectors: OrderedDict[tuple[str, str], list[float]] = OrderedDict()
        if glean_wall_seconds <= 0:
            msg = f"glean_wall_seconds must be positive, got {glean_wall_seconds}"
            raise ValueError(msg)
        self._grep_wall_seconds = grep_wall_seconds
        self._glean_wall_seconds = glean_wall_seconds
        self.name = name
        # Construction stays dialect-free: a borrowed host knows its
        # dialect only at first use, so the default names the schema.
        self.description = description or (f"Database storage ({schema})" if schema else "Database storage")

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
        authority: Authority | None = None,
    ) -> Result:
        targets = targets_of(path, observations)
        host = self._host
        return await self._execute(
            "read",
            self._viewed(
                "read",
                authority,
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
                errors=[ResultError(kind=VFSErrorKind.invalid, message=f"max_depth must be >= 1, got {max_depth}")],
            )
        host = self._host
        return await self._execute(
            "tree",
            self._viewed(
                "tree",
                authority,
                lambda session, view: tree_rows(
                    session, host.tables, host.profile, host.membership_budget, path, max_depth, columns, view
                ),
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
        authority: Authority | None = None,
    ) -> Result:
        host = self._host
        return await self._execute(
            "glob",
            self._viewed(
                "glob",
                authority,
                lambda session, view: glob_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.parameter_budget,
                    host.membership_budget,
                    patterns=patterns,
                    globs_not=globs_not,
                    ext=ext,
                    ext_not=ext_not,
                    kind=kind,
                    max_count=max_count,
                    columns=columns,
                    view=view,
                ),
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
        authority: Authority | None = None,
    ) -> Result:
        host = self._host
        return await self._execute(
            "grep",
            self._viewed(
                "grep",
                authority,
                lambda session, view: grep_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.parameter_budget,
                    host.membership_budget,
                    host.offload_executor,
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
                ),
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
        authority: Authority | None = None,
    ) -> Result:
        refusal = await self._host.ensure_ready()
        if refusal is not None:
            return Result(ops=("glean",), errors=[refusal])
        scoped = bool(ext or ext_not or globs or globs_not or observations)
        vector, records = await self._vector_leg_for(query, scoped=scoped)
        host = self._host
        return await self._execute(
            "glean",
            self._viewed(
                "glean",
                authority,
                lambda session, view: glean_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.parameter_budget,
                    host.membership_budget,
                    host.offload_executor,
                    view=view,
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
        authority: Authority | None = None,
    ) -> Result:
        host = self._host

        async def run(session: AsyncSession) -> Result:
            gate = await self._gate(session, authority)
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
                authority=authority,
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
            gate = await self._gate(session, authority)
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
                authority=authority,
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
            checks = await self._gate(session, authority)
            if isinstance(checks, ResultError):
                return [checks]
            if refused := await checks.targets(session, targets, "modify"):
                return refused
            return await checks.subtrees(session, targets, "read_write") if cascade else []

        return await self._execute_topology(
            "delete",
            lambda session: delete_rows(
                session,
                self._host.tables,
                self._host.profile,
                self._host.membership_budget,
                targets=targets,
                cascade=cascade,
                authority=authority,
                lock_key=self._host.topology_key,
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
            resolved = await self._gate(session, authority)
            if isinstance(resolved, ResultError):
                return [resolved]
            checks = resolved
            return []

        async def permit(
            session: AsyncSession, target: Path, lookup: RestoreLookup, resolved: RestoreSource | ResultError
        ) -> ResultError | None:
            """The caller's verdict on one target, worded from the path it sent.

            The trash row is judged by its origin with the label it kept,
            and a restore never mints an owner, so its owner may put back
            what it deleted. A row the caller cannot see is answered as
            the gate answers any target it cannot act on — absent, or
            denied when it is a directory on the road; a trash-side
            address whose original parent it cannot see is absent too.
            The ladder's own refusals stand only once the caller may see
            everything they name. The destination is judged under the
            posture rows, as a creation there would be.
            """
            assert checks is not None
            if checks.whole:
                return None
            row = lookup.row
            if row is None or not checks.view.admits(row):
                road = row is not None and row["kind"] == "directory" and await checks.view.road(session, [row["path"]])
                return denied(target) if road else await checks.missing(session, target)
            refused = checks.row(target, judged_path(row), row["owner_id"], row["everyone_level"], "read_write")
            if refused is None and row["kind"] == "directory":
                beneath = await checks.subtrees(session, [Path._brand(row["path"])], "read_write")
                refused = denied(target) if beneath else None
            if refused is not None:
                return refused
            parent = lookup.parent
            unseen = parent is None or not checks.view.admits(parent)
            if is_trash_path(target) and row["original_parent_id"] is not None and unseen:
                return await checks.missing(session, target)
            if isinstance(resolved, ResultError):
                return None
            host = self._host
            dest = str(resolved.dest)
            labels = await labels_for(session, host.tables, host.profile, host.membership_budget, [dest])
            return checks.row(resolved.dest, dest, row["owner_id"], labels[dest], "read_write")

        return await self._execute_topology(
            "restore",
            lambda session: restore_rows(
                session,
                self._host.tables,
                self._host.profile,
                self._host.membership_budget,
                targets=targets,
                authority=authority,
                lock_key=self._host.topology_key,
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
            checks = await self._gate(session, authority)
            if isinstance(checks, ResultError):
                return [checks]
            if checks.whole:
                return []
            if refused := await checks.targets(session, [path], "modify"):
                return refused
            return await checks.subtrees(session, [path], "read_write")

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
                lock_key=self._host.topology_key,
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
            gate = await self._gate(session, authority)
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
            gate = await self._gate(session, authority)
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
            gate = await self._gate(session, authority)
            if isinstance(gate, ResultError):
                return Result(ops=("rmedge",), errors=[gate])
            if refused := await gate.targets(session, [edge.source for edge in edges], "modify"):
                return Result(ops=("rmedge",), errors=refused)
            return await rmedge_rows(
                session, host.tables, host.profile, host.membership_budget, edges=edges, authority=authority
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

    async def posture(self, *, path: Path, posture: Posture, authority: Authority | None = None) -> Result:
        """Set what everyone holds at *path* and below: ``open``, ``shared``, or ``private``.

        The posture row commits first and is in force from then on; the
        verb then waits while the labels beneath it are rewritten, one
        bounded chunk per transaction, finishing any relabel an earlier
        call left pending on the way. The result reports the rows
        rewritten, the statements and the transactions it took.
        """
        written = await self._grant_write(
            "posture",
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
        host = self._host
        who = self._named(authority)

        async def run(session: AsyncSession) -> Result:
            gate = await self._gate(session, who, level="read")
            if isinstance(gate, ResultError):
                return Result(ops=("grants",), errors=[gate])
            return await list_grants(
                session, host.tables, host.profile, host.membership_budget, gate, path=path, authority=who
            )

        return await self._execute("grants", run)

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
        outcome = await self._signal_phase(tables, lost)
        if isinstance(outcome, Result):
            return outcome
        if not warnings:
            return result
        return Result(ops=result.ops, observations=result.observations, errors=[*result.errors, *warnings])

    async def _signal_phase(self, tables: VFSTables, lost: asyncio.Event) -> Result | None:
        """Store every declared prior under a fresh generation; signals no longer declared are swept.

        The graph is collected once in a read transaction; each signal
        computes off the event loop and publishes in its own write
        transaction, the lease's ``lost`` flag checked between them.
        """
        ranker = self._ranker
        if ranker.signals:
            graph = await self._rows("reindex", partial(collect_graph, tables=tables))
            for signal in ranker.signals:
                if lost.is_set():
                    return lease_lost_result()
                values = await compute_signal(self._host.offload_executor, graph, signal)
                generation = str(ULID())
                publish = partial(publish_signal, tables=tables, signal=signal, generation=generation, values=values)
                published = await self._execute_write("reindex", publish)
                if not published.success:
                    return published
        declared = [signal.name for signal in ranker.signals]
        swept = await self._execute_write(
            "reindex", partial(sweep_undeclared_signals, tables=tables, profile=self._host.profile, declared=declared)
        )
        return None if swept.success else swept

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
        """The gram-index phases; a lost lease stops at the next boundary.

        The chunk pass's advisory records (the extractor's unresolved
        count) ride out on whatever Result the phases end with.
        """
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
        notes = list(result.errors)
        if lost.is_set():
            return lease_lost_result()
        result = await self._execute_write(
            "reindex", lambda session: build_epoch(session, tables, state, self._host.offload_executor)
        )
        if not result.success or state.epoch is None:
            return with_notes(result, notes)
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
        reclaimed = await self._execute_write("reindex", lambda session: reclaim_epochs(session, tables))
        return with_notes(reclaimed, notes)

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

    @staticmethod
    def _named(authority: Authority | None) -> Authority:
        """The authority a call acts under: a direct storage call naming none is trusted code, the system actor."""
        return _SYSTEM if authority is None else authority

    async def _resolution(
        self, session: AsyncSession, authority: Authority | None, level: GrantLevel, *, cached: bool = True
    ) -> Resolution | ResultError:
        """The call's rights, resolved in its own transaction; ``unauthenticated`` when posture wants a name."""
        who = self._named(authority)
        host = self._host
        resolution = await resolve_authority(
            session, host.tables, host.profile, host.membership_budget, who, self._rights if cached else None
        )
        if isinstance(resolution, ResultError):
            return resolution
        refusal = posture_refusal(who, resolution, level)
        return resolution if refusal is None else refusal

    def _viewed(
        self,
        op: str,
        authority: Authority | None,
        build: Callable[[AsyncSession, Visibility | None], Awaitable[Result]],
    ) -> Callable[[AsyncSession], Awaitable[Result]]:
        """A read body run under the call's view — ``None`` when the view is the whole mount."""
        host = self._host

        async def run(session: AsyncSession) -> Result:
            resolution = await self._resolution(session, authority, "read")
            if isinstance(resolution, ResultError):
                return Result(ops=(op,), errors=[resolution])
            if resolution.read.whole:
                return await build(session, None)
            view = Visibility(resolution.read, host.tables, host.profile, host.membership_budget, host.parameter_budget)
            await view.prepare(session)
            return await build(session, view)

        return run

    async def _gate(
        self,
        session: AsyncSession,
        authority: Authority | None,
        *,
        level: GrantLevel = "read_write",
        cached: bool = True,
    ) -> WriteGate | ResultError:
        """The call's write gate; ``unauthenticated`` when posture wants a name for *level*."""
        resolution = await self._resolution(session, authority, level, cached=cached)
        if isinstance(resolution, ResultError):
            return resolution
        host = self._host
        return WriteGate(resolution, host.tables, host.profile, host.membership_budget, host.parameter_budget)

    async def _grant_write(
        self,
        op: str,
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
            gate = await self._gate(session, who, cached=False)
            if isinstance(gate, ResultError):
                return Result(ops=(op,), errors=[gate])
            await seam("grants:before-write")
            return await body(session, gate, who, revision)

        return await self._execute_write(op, run)

    async def _settled(self, written: Result) -> Result:
        """*written*, a posture verb's result, once every pending relabel has run to its end.

        One chunk per writer transaction, each bounded by the dialect's
        piece and row caps, so no transaction holds a subtree's worth of
        locks; a chunk that fails leaves its mark for the next call.
        """
        host = self._host
        relabeller = Relabeller(host.tables, host.profile, host.membership_budget)
        grants = (written.model_extra or {}).get("grants")
        done = Relabel(0, 0, 0)
        step: Relabel | None = None

        async def chunk(session: AsyncSession) -> Result:
            nonlocal step
            step = await relabeller.step(session)
            return Result(ops=("posture",))

        while True:
            outcome = await self._execute_write("posture", chunk)
            if not outcome.success:
                return Result(ops=("posture",), grants=grants, errors=outcome.errors)
            if step is None:
                break
            done = done.plus(step)
            await seam("relabel:after-chunk")
        return Result(ops=("posture",), grants=grants, relabel=done._asdict())

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
        self, op: Literal["move", "copy"], operations: list[ResolvedPair], *, authority: Authority | None
    ) -> Result:
        """Move or copy under the gate: a moved source is modified and a copied one read, whole
        subtrees included; every destination is a creation."""
        need: GrantLevel = "read_write" if op == "move" else "read"

        async def gate(session: AsyncSession) -> list[ResultError]:
            checks = await self._gate(session, authority)
            if isinstance(checks, ResultError):
                return [checks]
            sources = [pair.src for pair in operations]
            refused = await checks.targets(session, sources, "modify" if op == "move" else "read")
            refused += await checks.targets(
                session, [pair.dest for pair in operations if pair.dest != pair.src], "create"
            )
            return refused or await checks.subtrees(session, sources, need)

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
                lock_key=self._host.topology_key,
                gate=gate,
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
