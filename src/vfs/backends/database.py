"""DatabaseFileSystem — SQL-backed implementation of VirtualFileSystem.

All entities (files, directories, chunks, versions, connections) live in a
single ``vfs_objects`` table.  Operations dispatch by kind — the path
determines the kind, and the kind determines the semantics.
"""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple, cast

from sqlalchemy import case, func, or_, select

from vfs.base import VirtualFileSystem
from vfs.bm25 import BM25Scorer, tokenize, tokenize_query
from vfs.graph import RustworkxGraph
from vfs.models import VFSObject, VFSObjectBase
from vfs.paths import connection_path, scope_path, validate_user_id, version_path
from vfs.paths import parent_path as compute_parent_path
from vfs.patterns import compile_glob, glob_to_sql_like
from vfs.permissions import check_writable
from vfs.replace import replace
from vfs.results import Candidate, Detail, EditOperation, TwoPathOperation, VFSResult
from vfs.versioning import SNAPSHOT_INTERVAL

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    from vfs.embedding import EmbeddingProvider
    from vfs.permissions import Permission, PermissionMap
    from vfs.query.ast import CaseMode, GrepOutputMode
    from vfs.vector_store import VectorStore


class _LexicalDoc(NamedTuple):
    """Per-document lexical stats used for BM25 scoring."""

    path: str
    kind: str | None
    term_freqs: dict[str, int]
    doc_length: int
    content: str


def _escape_like(term: str) -> str:
    """Escape special characters for a SQL LIKE pattern."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _regex_flags_for_mode(case_mode: CaseMode, pattern: str) -> int:
    """Map an rg-style case mode to Python ``re`` flags.

    ``smart`` matches rg's smart-case: case-insensitive iff the pattern
    contains no uppercase characters.
    """
    if case_mode == "insensitive":
        return re.IGNORECASE
    if case_mode == "smart":
        return re.IGNORECASE if pattern == pattern.lower() else 0
    return 0


def _compile_grep_regex(
    pattern: str,
    *,
    case_mode: CaseMode,
    fixed_strings: bool,
    word_regexp: bool,
) -> re.Pattern[str]:
    """Build the effective grep regex from rg-style modifiers.

    Applies, in order: ``-F`` (escape), ``-w`` (word boundary wrap),
    and case-mode flag resolution.  Smart-case is evaluated against the
    user's raw pattern, not the post-escape form, so ``-F "Foo"`` stays
    case-sensitive under smart-case just like rg.
    """
    effective = re.escape(pattern) if fixed_strings else pattern
    if word_regexp:
        effective = rf"\b(?:{effective})\b"
    flags = _regex_flags_for_mode(case_mode, pattern)
    return re.compile(effective, flags)


def _build_line_matches_with_context(
    lines: list[str],
    match_indices: list[int],
    before: int,
    after: int,
) -> list[dict[str, object]]:
    """Emit line_matches entries covering matches plus rg-style context.

    Overlapping or adjacent context windows are merged so a single span
    contributes exactly one entry per line.  Context lines are marked
    with ``"context": True`` in the returned dicts; match lines are not.
    With ``before == after == 0`` the output degrades to a flat list of
    match-only entries preserving the original shape.
    """
    if not match_indices:
        return []
    total = len(lines)
    windows: list[list[int]] = []  # each: [start, end] inclusive
    for mi in match_indices:
        start = max(0, mi - before)
        end = min(total - 1, mi + after)
        if windows and start <= windows[-1][1] + 1:
            if end > windows[-1][1]:
                windows[-1][1] = end
        else:
            windows.append([start, end])

    match_set = set(match_indices)
    result: list[dict[str, object]] = []
    for start, end in windows:
        for idx in range(start, end + 1):
            entry: dict[str, object] = {"line": idx + 1, "text": lines[idx]}
            if idx not in match_set:
                entry["context"] = True
            result.append(entry)
    return result


def _unchecked_select(*entities: Any) -> Any:
    """Call SQLAlchemy select() through Any to sidestep stub precision gaps."""
    return cast("Any", select)(*entities)


class DatabaseFileSystem(VirtualFileSystem):
    """SQL-backed filesystem — portable baseline using SQLAlchemy.

    Stores everything in ``vfs_objects``.  Glob, grep, and lexical search
    use SQL LIKE for pre-filtering and Python for authoritative matching/scoring.
    Graph operations delegate to an internal ``RustworkxGraph``.
    """

    DIALECT_PARAMETER_BUDGETS: ClassVar[dict[str, int]] = {
        "sqlite": 900,
        "mssql": 2000,
        "postgresql": 32700,
    }
    PARAMETER_BUDGET_FALLBACK: int = 900
    PARAMETER_RESERVE: int = 100
    BM25_PRE_FILTER_LIMIT: ClassVar[int] = 1_000

    def __init__(
        self,
        *,
        engine: AsyncEngine | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        model: type[VFSObjectBase] = VFSObject,
        embedding_provider: EmbeddingProvider | None = None,
        vector_store: VectorStore | None = None,
        user_scoped: bool = False,
        permissions: Permission | PermissionMap = "read_write",
        schema: str | None = None,
    ) -> None:
        super().__init__(
            engine=engine,
            session_factory=session_factory,
            permissions=permissions,
            schema=schema,
        )
        self._model = model
        self._user_scoped = user_scoped
        self._graph = RustworkxGraph(model=model, user_scoped=user_scoped)
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store

    # ------------------------------------------------------------------
    # User-scoping helpers
    # ------------------------------------------------------------------

    def _scope_path(self, path: str | None, user_id: str | None) -> str | None:
        """Scope a single path if user_scoped is enabled."""
        if path is None or not self._user_scoped or user_id is None:
            return path
        return scope_path(path, user_id)

    def _scope_candidates(self, candidates: VFSResult | None, user_id: str | None) -> VFSResult | None:
        """Scope all candidate paths if user_scoped is enabled."""
        if candidates is None or not self._user_scoped or user_id is None:
            return candidates
        scoped = [c.model_copy(update={"path": scope_path(c.path, user_id)}) for c in candidates.candidates]
        return candidates._with_candidates(scoped)

    def _scope_objects(self, objects: Sequence[VFSObjectBase], user_id: str | None) -> None:
        """Scope object paths in place if user_scoped is enabled.

        For connection objects, rebuilds the connection ``path`` from
        the scoped ``source_path`` and ``target_path`` so all three
        fields are consistently scoped.
        """
        if not self._user_scoped or user_id is None:
            return
        for obj in objects:
            if obj.source_path:
                obj.source_path = scope_path(obj.source_path, user_id)
            if obj.target_path:
                obj.target_path = scope_path(obj.target_path, user_id)
            # Rebuild connection path from scoped endpoints
            if obj.kind == "connection" and obj.source_path and obj.target_path and obj.connection_type:
                obj.path = connection_path(obj.source_path, obj.target_path, obj.connection_type)
            else:
                obj.path = scope_path(obj.path, user_id)
            obj.owner_id = user_id
            obj._rederive_path_fields()

    def _unscope_result(self, result: VFSResult, user_id: str | None) -> VFSResult:
        """Unscope all result paths if user_scoped is enabled."""
        if not self._user_scoped or user_id is None:
            return result
        return result.strip_user_scope(user_id)

    def _require_user_id(self, user_id: str | None) -> None:
        """Raise if user_scoped is enabled but no user_id provided."""
        if not self._user_scoped:
            return
        if user_id is None:
            raise ValueError("user_id is required for user-scoped filesystem operations")
        valid, err = validate_user_id(user_id)
        if not valid:
            raise ValueError(f"Invalid user_id: {err}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_object(
        self,
        path: str,
        session: AsyncSession,
        include_deleted: bool = False,
    ) -> VFSObjectBase | None:
        """Fetch a single object by exact path."""
        stmt = select(self._model).where(self._model.path == path)  # ty: ignore[invalid-argument-type]
        if not include_deleted:
            stmt = stmt.where(self._model.deleted_at.is_(None))  # ty: ignore[unresolved-attribute]
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    def _parameter_budget(self, session: AsyncSession) -> int:
        """Return a conservative parameter budget for the current SQL dialect."""
        bind = session.get_bind()
        dialect_name = bind.dialect.name if bind is not None else ""
        return self.DIALECT_PARAMETER_BUDGETS.get(dialect_name, self.PARAMETER_BUDGET_FALLBACK)

    def _query_chunk_size(
        self,
        session: AsyncSession,
        *,
        binds_per_item: int,
    ) -> int:
        """Compute a safe internal query chunk size for this session."""
        usable_budget = max(1, self._parameter_budget(session) - self.PARAMETER_RESERVE)
        per_item = max(1, binds_per_item)
        return max(1, usable_budget // per_item)

    def _chunk_paths(
        self,
        session: AsyncSession,
        paths: list[str],
        *,
        binds_per_item: int,
    ) -> list[list[str]]:
        """Chunk path lists for internal SQL queries without changing semantics."""
        if not paths:
            return []
        chunk_size = self._query_chunk_size(session, binds_per_item=binds_per_item)
        return [paths[i : i + chunk_size] for i in range(0, len(paths), chunk_size)]

    @staticmethod
    def _tokenize_doc(
        content: str,
        lexical_tokens: int,
        term_set: frozenset[str],
    ) -> tuple[dict[str, int], int, set[str]]:
        """Tokenize content once, returning query-term TFs and lexical stats."""
        doc_tokens = tokenize(content)
        doc_length = lexical_tokens or len(doc_tokens)

        term_freqs: dict[str, int] = {}
        get_freq = term_freqs.get
        seen_tokens: set[str] = set()
        for token in doc_tokens:
            if token in term_set:
                term_freqs[token] = get_freq(token, 0) + 1
            seen_tokens.add(token)

        return term_freqs, doc_length, seen_tokens

    @staticmethod
    def _estimate_average_idf(
        candidate_vocab_doc_freqs: dict[str, int],
        corpus_size: int,
    ) -> float | None:
        """Estimate average IDF for BM25 epsilon-flooring from candidate vocab."""
        if not candidate_vocab_doc_freqs:
            return None

        average_idf = sum(BM25Scorer.idf(df, corpus_size) for df in candidate_vocab_doc_freqs.values()) / len(
            candidate_vocab_doc_freqs,
        )
        return average_idf if average_idf > 0 else None

    async def _fetch_lexical_docs(
        self,
        *,
        unique_terms: tuple[str, ...],
        term_set: frozenset[str],
        candidates: VFSResult | None,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> tuple[list[_LexicalDoc], bool, dict[str, int], dict[str, int]]:
        """Fetch candidate docs and convert them directly into lexical stats."""
        docs: list[_LexicalDoc] = []
        local_doc_freqs: dict[str, int] = dict.fromkeys(unique_terms, 0)
        candidate_vocab_doc_freqs: dict[str, int] = {}
        prefilter_truncated = False

        def append_doc(
            path: str,
            kind: str | None,
            content: str | None,
            lexical_tokens: int,
        ) -> None:
            if not content:
                return

            term_freqs, doc_length, seen_tokens = self._tokenize_doc(
                content,
                lexical_tokens,
                term_set,
            )
            docs.append(
                _LexicalDoc(
                    path=path,
                    kind=kind,
                    term_freqs=term_freqs,
                    doc_length=doc_length,
                    content=content,
                )
            )
            for term in term_freqs:
                local_doc_freqs[term] += 1
            for token in seen_tokens:
                candidate_vocab_doc_freqs[token] = candidate_vocab_doc_freqs.get(token, 0) + 1

        if candidates is not None:
            need_hydration: list[str] = []
            for candidate in candidates.candidates:
                if candidate.kind == "version":
                    continue
                if candidate.content is not None:
                    append_doc(
                        candidate.path,
                        candidate.kind,
                        candidate.content,
                        0,
                    )
                else:
                    need_hydration.append(candidate.path)

            if need_hydration:
                for batch in self._chunk_paths(
                    session,
                    need_hydration,
                    binds_per_item=1,
                ):
                    doc_columns: tuple[Any, Any, Any, Any] = (
                        self._model.path,
                        self._model.kind,
                        self._model.content,
                        self._model.lexical_tokens,
                    )
                    stmt = _unchecked_select(
                        *doc_columns,
                    ).where(
                        self._model.path.in_(batch),  # ty: ignore[unresolved-attribute]
                        self._model.kind != "version",
                        self._model.deleted_at.is_(None),  # ty: ignore[unresolved-attribute]
                        self._model.content.isnot(None),  # ty: ignore[unresolved-attribute]
                    )
                    if self._user_scoped and user_id:
                        stmt = stmt.where(self._model.path.like(f"/{user_id}/%"))  # ty: ignore[unresolved-attribute]
                    result = await session.execute(stmt)
                    for obj_path, kind, content, lexical_tokens in result.all():
                        append_doc(obj_path, kind, content, lexical_tokens or 0)

            return docs, prefilter_truncated, local_doc_freqs, candidate_vocab_doc_freqs

        like_filters = []
        term_score_expr = None
        for term in unique_terms:
            escaped = _escape_like(term)
            like_expr = self._model.content.ilike(  # ty: ignore[unresolved-attribute]
                f"%{escaped}%",
                escape="\\",
            )
            like_filters.append(like_expr)
            score_expr = case((like_expr, 1), else_=0)
            term_score_expr = score_expr if term_score_expr is None else term_score_expr + score_expr

        doc_columns: tuple[Any, Any, Any, Any] = (
            self._model.path,
            self._model.kind,
            self._model.content,
            self._model.lexical_tokens,
        )
        lexical_tokens_column = cast("Any", self._model.lexical_tokens)
        stmt = (
            _unchecked_select(*doc_columns)
            .where(
                self._model.kind != "version",
                self._model.deleted_at.is_(None),  # ty: ignore[unresolved-attribute]
                self._model.content.isnot(None),  # ty: ignore[unresolved-attribute]
                or_(*like_filters),
            )
            .order_by(
                cast("Any", term_score_expr).desc(),
                lexical_tokens_column.asc(),
            )
            .limit(self.BM25_PRE_FILTER_LIMIT + 1)
        )
        if self._user_scoped and user_id:
            stmt = stmt.where(self._model.path.like(f"/{user_id}/%"))  # ty: ignore[unresolved-attribute]

        result = await session.execute(stmt)
        rows = result.all()
        if len(rows) > self.BM25_PRE_FILTER_LIMIT:
            prefilter_truncated = True
            rows = rows[: self.BM25_PRE_FILTER_LIMIT]

        for obj_path, kind, content, lexical_tokens in rows:
            append_doc(obj_path, kind, content, lexical_tokens or 0)

        return docs, prefilter_truncated, local_doc_freqs, candidate_vocab_doc_freqs

    async def _fetch_corpus_stats(
        self,
        *,
        unique_terms: tuple[str, ...],
        doc_lengths: list[int],
        local_doc_freqs: dict[str, int],
        prefilter_truncated: bool,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> tuple[int, float, dict[str, int]]:
        """Fetch corpus_size, avgdl, and authoritative query-term DF counts."""
        base_where: list[Any] = [
            self._model.kind != "version",
            self._model.deleted_at.is_(None),  # ty: ignore[unresolved-attribute]
            self._model.content.isnot(None),  # ty: ignore[unresolved-attribute]
        ]
        if self._user_scoped and user_id:
            base_where.append(self._model.path.like(f"/{user_id}/%"))  # ty: ignore[unresolved-attribute]

        aggregate_columns: list[Any] = [
            func.count(),
            func.coalesce(func.sum(self._model.lexical_tokens), 0),
        ]

        if prefilter_truncated:
            for term in unique_terms:
                like_expr = self._model.content.ilike(  # ty: ignore[unresolved-attribute]
                    f"%{_escape_like(term)}%",
                    escape="\\",
                )
                aggregate_columns.append(
                    func.sum(case((like_expr, 1), else_=0)),
                )

        stats_stmt = (
            select(*aggregate_columns)
            .select_from(
                self._model,
            )
            .where(*base_where)
        )
        stats_row = (await session.execute(stats_stmt)).one()

        corpus_size = stats_row[0]
        total_corpus_tokens = stats_row[1]
        avgdl = (
            float(total_corpus_tokens) / corpus_size
            if corpus_size > 0 and total_corpus_tokens > 0
            else (sum(doc_lengths) / len(doc_lengths) if doc_lengths else 1.0)
        )

        if prefilter_truncated:
            doc_freqs = {term: stats_row[idx + 2] or 0 for idx, term in enumerate(unique_terms)}
        else:
            doc_freqs = local_doc_freqs

        return corpus_size, avgdl, doc_freqs

    async def _resolve_required_parents(
        self,
        paths: list[str],
        session: AsyncSession,
        *,
        required_kind: str,
        include_deleted: bool,
    ) -> dict[str, VFSObjectBase]:
        """Load required parent objects using a kind-specific policy."""
        resolved: dict[str, VFSObjectBase] = {}
        for batch in self._chunk_paths(session, paths, binds_per_item=1):
            stmt = select(self._model).where(
                self._model.path.in_(batch),  # ty: ignore[unresolved-attribute]
                self._model.kind == required_kind,  # ty: ignore[invalid-argument-type]
            )
            if not include_deleted:
                stmt = stmt.where(self._model.deleted_at.is_(None))  # ty: ignore[unresolved-attribute]
            result = await session.execute(stmt)
            resolved.update({obj.path: obj for obj in result.scalars().all()})
        return resolved

    async def _resolve_parent_dirs(
        self,
        paths: list[str],
        session: AsyncSession,
    ) -> tuple[list[VFSObjectBase], list[str]]:
        """Identify ancestor directories that need creation or revival.

        Returns ``(dirs, errors)`` where *dirs* are directory objects
        **without mutating or adding them to the session**.  Revived dirs
        still carry their original ``deleted_at`` value — the caller
        clears it in step 6 inside a savepoint so that a failed write
        batch does not leave revived dirs committed.

        New dirs are fresh model instances (``deleted_at is None``).
        The caller distinguishes the two via ``d.deleted_at is not None``.

        Queries ancestor paths **without** a kind filter so that
        non-directory ancestors (e.g. an existing file at ``/a.txt``)
        are detected and rejected rather than silently shadowed.
        """
        all_ancestors: set[str] = set()
        for path in paths:
            current = compute_parent_path(path)
            while current != "/":
                if current in all_ancestors:
                    break
                all_ancestors.add(current)
                current = compute_parent_path(current)

        if not all_ancestors:
            return [], []

        # Load ALL existing objects at ancestor paths (any kind, including
        # soft-deleted) so we can detect non-directory ancestors.
        existing: dict[str, VFSObjectBase] = {}
        for batch in self._chunk_paths(session, sorted(all_ancestors), binds_per_item=1):
            stmt = select(self._model).where(self._model.path.in_(batch))  # ty: ignore[unresolved-attribute]
            result = await session.execute(stmt)
            existing.update({obj.path: obj for obj in result.scalars().all()})

        # Reject non-directory ancestors
        errors: list[str] = []
        for p, obj in existing.items():
            if obj.kind != "directory":
                errors.append(f"Ancestor path exists as {obj.kind}, not directory: {p}")

        if errors:
            return [], errors

        # Collect soft-deleted dirs for revival (not mutated yet)
        dirs: list[VFSObjectBase] = [
            existing[p] for p in sorted(existing, key=lambda p: p.count("/")) if existing[p].deleted_at is not None
        ]

        # Create missing directories (shallowest first)
        missing = sorted(all_ancestors - set(existing), key=lambda p: p.count("/"))
        dirs.extend(self._model(path=ancestor, kind="directory") for ancestor in missing)

        return dirs, []

    async def _validate_chunk_parents(
        self,
        write_map: dict[str, VFSObjectBase],
        session: AsyncSession,
    ) -> tuple[set[str], list[str]]:
        """Reject chunk writes whose companion file is absent from DB and batch."""
        chunk_writes = [obj for obj in write_map.values() if obj.kind == "chunk" and obj.parent_path not in write_map]
        if not chunk_writes:
            return set(), []

        parent_paths = sorted({obj.parent_path for obj in chunk_writes})
        existing_parents = set(
            await self._resolve_required_parents(
                parent_paths,
                session,
                required_kind="file",
                include_deleted=False,
            )
        )

        invalid_paths: set[str] = set()
        errors: list[str] = []
        for obj in chunk_writes:
            if obj.parent_path not in existing_parents:
                invalid_paths.add(obj.path)
                errors.append(f"Chunk parent file not found: {obj.parent_path} (for {obj.path})")

        return invalid_paths, errors

    async def _fetch_children_batched(
        self,
        objs: dict[str, VFSObjectBase],
        session: AsyncSession,
        *,
        include_deleted: bool = False,
    ) -> dict[str, list[VFSObjectBase]]:
        """Batch-fetch children for multiple objects in two queries.

        Directories use ``LIKE path/%`` (all descendants).
        Non-directories use ``parent_path IN (...)`` (direct metadata children).

        Returns ``{parent_path: [children]}`` grouped by owning parent.
        """
        dirs = {p: o for p, o in objs.items() if o.kind == "directory"}
        files = {p: o for p, o in objs.items() if o.kind != "directory"}
        result_map: dict[str, list[VFSObjectBase]] = {p: [] for p in objs}

        # Directory cascade — batched OR of LIKE conditions
        if dirs:
            dir_paths = list(dirs.keys())
            for batch in self._chunk_paths(session, dir_paths, binds_per_item=1):
                conditions = [
                    self._model.path.like(_escape_like(p) + "/%", escape="\\")  # ty: ignore[unresolved-attribute]
                    for p in batch
                ]
                stmt = select(self._model).where(or_(*conditions))
                if not include_deleted:
                    stmt = stmt.where(self._model.deleted_at.is_(None))  # ty: ignore[unresolved-attribute]
                rows = await session.execute(stmt)
                for child in rows.scalars().all():
                    # Match child to its owning directory (longest prefix)
                    for dp in batch:
                        if child.path.startswith(dp + "/"):
                            result_map[dp].append(child)
                            break

        # File/chunk/connection cascade — batched parent_path IN
        if files:
            file_paths = list(files.keys())
            for batch in self._chunk_paths(session, file_paths, binds_per_item=1):
                stmt = select(self._model).where(
                    self._model.parent_path.in_(batch),  # ty: ignore[unresolved-attribute]
                )
                if not include_deleted:
                    stmt = stmt.where(self._model.deleted_at.is_(None))  # ty: ignore[unresolved-attribute]
                rows = await session.execute(stmt)
                for child in rows.scalars().all():
                    if child.parent_path in result_map:
                        result_map[child.parent_path].append(child)

        return result_map

    # ------------------------------------------------------------------
    # Per-item write helpers
    # ------------------------------------------------------------------

    async def _update_existing(
        self,
        existing: VFSObjectBase,
        incoming: VFSObjectBase,
        new_content: str,
        latest_version_hash: str | None,
        session: AsyncSession,
    ) -> Candidate:
        """Update an existing (or soft-deleted) object with new content.

        Fast path: when the file hash and latest version hash agree,
        ``plan_file_write`` skips reconstruction — no version rows needed.

        Slow path: when hashes disagree (external edit or broken chain),
        fetches the version chain from the DB for reconstruction.
        """
        if existing.deleted_at is not None:
            existing.deleted_at = None

        if incoming.kind == "file" and existing.content is not None:
            plan = await asyncio.to_thread(
                existing.plan_file_write,
                new_content,
                latest_version_hash=latest_version_hash,
            )

            # Slow path: plan detected an integrity issue but had no
            # version rows to diagnose it. Fetch the chain and re-plan.
            if not plan.chain_verified and existing.version_number:
                version_rows = await self._fetch_version_chain(
                    existing.path,
                    existing.version_number,
                    session,
                )
                plan = await asyncio.to_thread(
                    existing.plan_file_write,
                    new_content,
                    version_rows=version_rows,
                    latest_version_hash=latest_version_hash,
                )

            existing.apply_write_plan(plan)
            for version_row in plan.version_rows:
                session.add(version_row)
        else:
            existing.update_content(new_content)  # pragma: no cover — defensive: files always have content

        return existing.to_candidate(operation="write")

    async def _fetch_version_chain(
        self,
        file_path: str,
        current_version: int,
        session: AsyncSession,
    ) -> list[VFSObjectBase]:
        """Fetch the version chain needed for reconstruction.

        Loads versions from the nearest snapshot boundary (within
        ``SNAPSHOT_INTERVAL``) up to *current_version*.
        """
        lower_bound = max(1, current_version - SNAPSHOT_INTERVAL + 1)
        version_paths = [version_path(file_path, v) for v in range(lower_bound, current_version + 1)]
        rows: list[VFSObjectBase] = []
        for batch in self._chunk_paths(session, version_paths, binds_per_item=1):
            stmt = select(self._model).where(
                self._model.path.in_(batch),  # ty: ignore[unresolved-attribute]
            )
            result = await session.execute(stmt)
            rows.extend(result.scalars().all())
        return rows

    async def _insert_new(
        self,
        incoming: VFSObjectBase,
        new_content: str,
        session: AsyncSession,
    ) -> Candidate:
        """Insert a new file or chunk.

        New files get an initial v1 snapshot.  Chunks are added directly.
        """
        if incoming.kind == "file" and incoming.content is not None:
            version_obj = type(incoming).create_version_row(
                file_path=incoming.path,
                version_number=1,
                version_content=new_content,
                prev_content=None,
                created_by="auto",
                force_snapshot=True,
            )
            incoming.version_number = 1
            incoming.update_content(new_content)
            session.add(version_obj)
        session.add(incoming)
        return incoming.to_candidate(operation="write")

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def _read_impl(
        self,
        path: str | None = None,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        """Read content for one or more objects.

        Accepts either a single ``path`` or a ``VFSResult`` of candidates.

        - *Single path*: fetch the object by exact path, return with content.
        - *Candidates*: batch-fetch all candidate paths in one query,
          preserve prior details from the incoming candidates, and report
          errors for any paths not found.
        """
        self._require_user_id(user_id)
        path = self._scope_path(path, user_id)
        candidates = self._scope_candidates(candidates, user_id)
        if candidates is None:
            if path is None:
                return self._error("read requires a path or candidates")
            candidates = VFSResult(candidates=[Candidate(path=path)])
        elif path is not None:
            return self._error("read requires a path or candidates, not both")

        incoming = {c.path: c for c in candidates.candidates}
        if not incoming:
            return VFSResult(candidates=[])

        # Pre-hydrated candidates pass straight through; only fetch the gaps.
        out: list[Candidate] = []
        errors: list[str] = []
        gap_paths: list[str] = []
        for p, c in incoming.items():
            if c.content is not None:
                out.append(
                    Candidate(
                        id=c.id,
                        path=c.path,
                        kind=c.kind,
                        content=c.content,
                        lines=c.lines,
                        size_bytes=c.size_bytes,
                        tokens=c.tokens,
                        mime_type=c.mime_type,
                        weight=c.weight,
                        distance=c.distance,
                        details=(Detail(operation="read"),),
                        created_at=c.created_at,
                        updated_at=c.updated_at,
                    )
                )
            else:
                gap_paths.append(p)

        for batch in self._chunk_paths(session, gap_paths, binds_per_item=1):
            stmt = select(self._model).where(
                self._model.path.in_(batch),  # ty: ignore[unresolved-attribute]
                self._model.deleted_at.is_(None),  # ty: ignore[unresolved-attribute]
            )
            result = await session.execute(stmt)
            objs = {obj.path: obj for obj in result.scalars().all()}
            for p in batch:
                if p in objs:
                    out.append(objs[p].to_candidate(operation="read"))
                else:
                    errors.append(f"Not found: {p}")

        return self._error(
            self._unscope_result(
                VFSResult(
                    candidates=out,
                    errors=errors,
                    success=len(errors) == 0,
                ),
                user_id,
            )
        )

    async def _stat_impl(
        self,
        path: str | None = None,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        """Return metadata for one or more objects.

        Delegates to ``_read_impl`` — returns the same result including
        content.  Callers that need metadata-only should strip content
        from the returned candidates.
        """
        return await self._read_impl(path=path, candidates=candidates, user_id=user_id, session=session)

    async def _write_impl(
        self,
        path: str | None = None,
        content: str | None = None,
        objects: Sequence[VFSObjectBase] | None = None,
        overwrite: bool = True,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        """Write one or more file/chunk objects to the database.

        Accepts either a single ``path``/``content`` pair or a list of
        ``objects``.  Single writes are wrapped into a one-element list
        so all writes follow the same batch path.

        Process:

        1.  **Validate** — reject non-file/chunk kinds, reject duplicate paths,
            build a path→object map.
        2.  **Validate chunk parents** — chunk writes whose companion file is
            not already in the database must include that file in the same batch.
            Fail fast if not.
        3.  **Ensure parent dirs** — identify ancestor directories for all
            file paths, reviving any soft-deleted directories instead and
            creating new objects if they don't exist. These parent dir updates
            are not added to session, they are only created as objects.
        4.  **Fetch** — batch query retrieves existing objects (including
            soft-deleted) and the bounded version chains needed for file writes.
        5.  **Process each write**:
            - *Soft-deleted file*: clear ``deleted_at`` to undelete.
            - *Existing file, content unchanged*: refresh ``updated_at``.
            - *Existing file*: plan any external/repair snapshots and normal
              version rows via ``plan_file_write``.
            - *Existing chunk*: update content directly (no versioning).
            - *New file/chunk*: add to session.
            - *Flush Session*: session is flushed per batch.
        6.  **Create Parent Dirs** — if file creation was successful, parent
            dirs are added to session and created at this time.

        It is important that the session is managed properly to not overload
        the db passed its parameter threshold.
        """
        self._require_user_id(user_id)
        # ── Step 1: Validate ──────────────────────────────────────────
        if objects is None:
            if path is None:
                return self._error("Write requires a path or objects")
            scoped_path = self._scope_path(path, user_id)
            obj = self._model(path=scoped_path or path, content=content or "")
            if self._user_scoped and user_id:
                obj.owner_id = user_id
            objects = [obj]

        elif path is not None:
            return self._error("Write requires a path or objects, not both")
        else:
            self._scope_objects(objects, user_id)

        write_map: dict[str, VFSObjectBase] = {}
        errors: list[str] = []
        for obj in objects:
            if obj.path == "/":
                errors.append("Cannot write to root path")
                continue
            if obj.kind not in ("file", "chunk", "connection", "directory"):
                errors.append(f"Cannot write to {obj.kind} path: {obj.path}")
                continue
            if obj.path in write_map:
                return self._error(f"Duplicate path in write batch: {obj.path}")
            write_map[obj.path] = obj

        if not write_map:
            return self._error(VFSResult(success=len(errors) == 0, errors=errors))

        # ── Step 2: Validate chunk parents ────────────────────────────
        invalid_chunk_paths, chunk_errors = await self._validate_chunk_parents(write_map, session)
        errors.extend(chunk_errors)
        if len(invalid_chunk_paths) == len(write_map):
            return self._error(errors)

        # ── Step 3: Resolve parent dirs (deferred) ────────────────────
        file_paths = [p for p, obj in write_map.items() if obj.kind in ("file", "directory")]
        parent_dirs: list[VFSObjectBase] = []
        if file_paths:
            parent_dirs, dir_errors = await self._resolve_parent_dirs(file_paths, session)
            if dir_errors:
                errors.extend(dir_errors)
                return self._error(errors)
            # Brand-new ancestor directories are created without a
            # permission check — a writable carve-out (e.g. /a/b/c) inside
            # a read-only mount needs reachable ancestors, so we let them
            # be created on demand.  But REVIVAL of a previously
            # soft-deleted ancestor in a read-only region must be blocked:
            # the user explicitly deleted that path, then made it
            # read-only, so silently un-deleting it as a side-effect of a
            # nested write would violate both intentions.
            for d in parent_dirs:
                if d.deleted_at is None:
                    continue  # creation — accepted
                err = check_writable(self, "write", d.path)
                if err is not None:
                    return err

        # ── Step 4a: Fetch existing objects ──────────────────────────
        all_paths = list(write_map.keys())
        existing_map: dict[str, VFSObjectBase] = {}

        for batch in self._chunk_paths(session, all_paths, binds_per_item=1):
            stmt = select(self._model).where(
                self._model.path.in_(batch),  # ty: ignore[unresolved-attribute]
            )
            result = await session.execute(stmt)
            for row in result.scalars().all():
                existing_map[row.path] = row

        # ── Step 4b: Fetch latest version hash per file ───────────────
        # Construct the exact version path for each existing file and
        # fetch just those rows via the unique path index.
        latest_version_hash: dict[str, str | None] = {}
        version_path_to_file: dict[str, str] = {}
        for obj_path, existing in existing_map.items():
            if existing.kind == "file" and existing.version_number is not None and existing.version_number > 0:
                vp = version_path(obj_path, existing.version_number)
                version_path_to_file[vp] = obj_path

        if version_path_to_file:
            vp_list = list(version_path_to_file.keys())
            for batch in self._chunk_paths(session, vp_list, binds_per_item=1):
                stmt = select(self._model.path, self._model.content_hash).where(  # ty: ignore[no-matching-overload]
                    self._model.path.in_(batch),  # ty: ignore[unresolved-attribute]
                )
                result = await session.execute(stmt)
                for vp, content_hash in result.all():
                    file_path = version_path_to_file[vp]
                    latest_version_hash[file_path] = content_hash

        # ── Step 5: Process each write ─────────────────────────────────
        out: list[Candidate] = []
        for obj_path, incoming in ((p, obj) for p, obj in write_map.items() if p not in invalid_chunk_paths):
            new_content = incoming.content or ""
            existing = existing_map.get(obj_path)

            try:
                if incoming.kind != "file":
                    if existing is not None:
                        if existing.deleted_at is not None:
                            existing.deleted_at = None
                        if existing.kind != "directory":
                            existing.update_content(new_content)
                        else:
                            existing.updated_at = datetime.now(UTC)
                        candidate = existing.to_candidate(operation="write")
                    else:
                        session.add(incoming)
                        candidate = incoming.to_candidate(operation="write")
                elif existing is not None:
                    if existing.deleted_at is None and not overwrite:
                        errors.append(f"Already exists (overwrite=False): {obj_path}")
                        continue
                    candidate = await self._update_existing(
                        existing,
                        incoming,
                        new_content,
                        latest_version_hash.get(obj_path),
                        session,
                    )
                else:
                    candidate = await self._insert_new(incoming, new_content, session)
                out.append(candidate)
            except Exception as exc:
                if existing is not None:
                    session.expire(existing)
                errors.append(f"Write failed for {obj_path}: {exc}")

        await session.flush()

        # ── Step 6: Commit parent dirs ────────────────────────────────
        if out:
            now = datetime.now(UTC)
            for d in parent_dirs:
                if d.deleted_at is not None:
                    d.deleted_at = None
                    d.updated_at = now
                else:
                    session.add(d)
            await session.flush()

        # Invalidate graph if any connections were written — their
        # source/target edges need to appear on the next query.
        if out and any(c.kind == "connection" for c in out):
            self._graph.invalidate()

        result = self._unscope_result(
            VFSResult(candidates=out, errors=errors, success=len(errors) == 0),
            user_id,
        )
        return self._error(result)

    async def _ls_impl(
        self,
        path: str | None = None,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        """List direct children of a path.

        Kind-aware visibility (§5.2, §5.4 of design doc):

        - **Directory** → returns ``file`` and ``directory`` children only.
          Metadata kinds (chunk, version, connection, api) are hidden,
          matching the Unix ``ls`` convention for dot-prefixed entries.
        - **File** → returns *all* metadata children (chunks, versions,
          connections) since those are the only children a file has.

        When called with *candidates*, the candidate's ``kind`` field is
        used directly if populated.  Only candidates with ``kind is None``
        trigger a DB lookup to resolve the kind, avoiding an extra
        round-trip for results that already carry type information from
        a prior operation (read, glob, write, etc.).
        """
        self._require_user_id(user_id)
        path = self._scope_path(path, user_id)
        candidates = self._scope_candidates(candidates, user_id)
        if candidates is None:
            if path is None:
                return self._error("ls requires a path or candidates")
            candidates = VFSResult(candidates=[Candidate(path=path)])
        elif path is not None:
            return self._error("ls requires a path or candidates, not both")

        if not candidates.candidates:
            return VFSResult(candidates=[])

        # Classify using candidate kind; query only unknowns
        dir_paths: list[str] = []
        file_paths: list[str] = []
        unknown_paths: list[str] = []
        for c in candidates.candidates:
            if c.path == "/" or c.kind == "directory":
                dir_paths.append(c.path)
            elif c.kind is not None:
                file_paths.append(c.path)
            else:
                unknown_paths.append(c.path)

        if unknown_paths:
            for batch in self._chunk_paths(session, unknown_paths, binds_per_item=1):
                stmt = select(self._model).where(
                    self._model.path.in_(batch),  # ty: ignore[unresolved-attribute]
                    self._model.deleted_at.is_(None),  # ty: ignore[unresolved-attribute]
                )
                result = await session.execute(stmt)
                for obj in result.scalars().all():
                    if obj.kind == "directory":
                        dir_paths.append(obj.path)
                    elif obj.kind == "file":
                        file_paths.append(obj.path)

        # Single query — filter directory metadata children in Python
        all_paths = dir_paths + file_paths
        if not all_paths:
            return VFSResult(candidates=[])

        dir_set = set(dir_paths)
        out: list[Candidate] = []
        for batch in self._chunk_paths(session, all_paths, binds_per_item=1):
            stmt = select(self._model).where(
                self._model.parent_path.in_(batch),  # ty: ignore[unresolved-attribute]
                self._model.deleted_at.is_(None),  # ty: ignore[unresolved-attribute]
            )
            result = await session.execute(stmt)
            for child in result.scalars().all():
                if child.parent_path in dir_set and child.kind not in ("file", "directory"):
                    continue
                out.append(child.to_candidate(operation="ls"))

        return self._unscope_result(VFSResult(candidates=out), user_id)

    async def _delete_impl(
        self,
        path: str | None = None,
        candidates: VFSResult | None = None,
        permanent: bool = False,
        cascade: bool = True,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        """Delete one or more objects.

        Soft-delete (default): sets ``deleted_at``, cascades to children.
        Permanent: removes from the database entirely, including children.

        When ``cascade=False``, objects with children are rejected rather
        than cascading.  This is analogous to POSIX ``rmdir`` which refuses
        to remove non-empty directories.
        """
        self._require_user_id(user_id)
        path = self._scope_path(path, user_id)
        candidates = self._scope_candidates(candidates, user_id)
        if candidates is None:
            if path is None:
                return self._error("delete requires a path or candidates")
            candidates = VFSResult(candidates=[Candidate(path=path)])
        elif path is not None:
            return self._error("delete requires a path or candidates, not both")

        paths = [c.path for c in candidates.candidates]
        if not paths:
            return VFSResult(candidates=[])

        if "/" in paths:
            return self._error("Cannot delete root path")

        # ── Fetch targets ────────────────────────────────────────────
        objs: dict[str, VFSObjectBase] = {}
        for batch in self._chunk_paths(session, paths, binds_per_item=1):
            stmt = select(self._model).where(
                self._model.path.in_(batch),  # ty: ignore[unresolved-attribute]
            )
            if not permanent:
                stmt = stmt.where(self._model.deleted_at.is_(None))  # ty: ignore[unresolved-attribute]
            result = await session.execute(stmt)
            objs.update({obj.path: obj for obj in result.scalars().all()})

        out: list[Candidate] = []
        errors: list[str] = []

        # Separate not-found errors
        found: dict[str, VFSObjectBase] = {}
        for p in paths:
            if p in objs:
                found[p] = objs[p]
            else:
                errors.append(f"Not found: {p}")

        if not found:
            return self._error(VFSResult(errors=errors, success=len(errors) == 0))

        # ── Batch-fetch children ─────────────────────────────────────
        children_map = await self._fetch_children_batched(
            found,
            session,
            include_deleted=permanent,
        )

        # ── Non-cascade guard ────────────────────────────────────────
        if not cascade:
            blocked: set[str] = set()
            for p, children in children_map.items():
                if children:
                    errors.append(f"Not empty (use cascade=True): {p}")
                    blocked.add(p)
            found = {p: o for p, o in found.items() if p not in blocked}
            if not found:
                return self._error(VFSResult(errors=errors, success=len(errors) == 0))

        # ── Per-child permission check (cascade fail-fast) ───────────
        # The router's chokepoint only saw the top-level paths.  When a
        # delete cascades into children, each child must independently
        # satisfy the permission map — otherwise a delete on a writable
        # parent would silently swallow children protected by a stricter
        # nested rule (e.g. PermissionMap default=read_write with
        # ("/a/b", "read") would let `delete("/a")` cascade through
        # `/a/b/protected.md`).
        for parent_path, children in children_map.items():
            if parent_path not in found:
                continue
            for child in children:
                err = check_writable(self, "delete", child.path)
                if err is not None:
                    return err

        # ── Apply deletes ────────────────────────────────────────────
        now = datetime.now(UTC)
        for p, obj in found.items():
            children = children_map.get(p, [])
            try:
                if permanent:
                    out.append(obj.to_candidate(operation="delete"))
                    for child in children:
                        out.append(child.to_candidate(operation="delete"))
                        await session.delete(child)
                    await session.delete(obj)
                else:
                    obj.deleted_at = now
                    out.append(obj.to_candidate(operation="delete"))
                    for child in children:
                        child.deleted_at = now
                        out.append(child.to_candidate(operation="delete"))
            except Exception as e:
                errors.append(f"Delete failed for {p}: {e}")

        await session.flush()
        # Invalidate graph — deleted objects may include connections or
        # files that are graph nodes.
        self._graph.invalidate()
        result = self._unscope_result(
            VFSResult(candidates=out, errors=errors, success=len(errors) == 0),
            user_id,
        )
        return self._error(result)

    async def _mkdir_impl(
        self,
        path: str,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        """Create a directory. Delegates to ``_write_impl``."""
        self._require_user_id(user_id)
        # Pass unscoped path — _write_impl handles scoping
        result = await self._write_impl(
            objects=[self._model(path=path, kind="directory")],
            overwrite=False,
            user_id=user_id,
            session=session,
        )
        return result

    async def _mkconn_impl(
        self,
        source: str | None = None,
        target: str | None = None,
        connection_type: str | None = None,
        objects: Sequence[VFSObjectBase] | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        """Create connection edges.

        Accepts either ``source``/``target``/``connection_type`` for a
        single connection, or ``objects`` for a batch of pre-built
        connection objects.  Validates that each source exists, then
        delegates to ``_write_impl``.

        All paths are unscoped.  Scoping is applied only for the DB
        validation query; ``_write_impl`` handles its own scope cycle.
        """
        self._require_user_id(user_id)
        if objects is None:
            if not source or not target or not connection_type:
                return self._error("mkconn requires source/target/connection_type or objects")
            objects = [
                self._model(
                    path=connection_path(source, target, connection_type),
                    kind="connection",
                    source_path=source,
                    target_path=target,
                    connection_type=connection_type,
                )
            ]
        elif source is not None or target is not None or connection_type is not None:
            return self._error("mkconn requires source/target/connection_type or objects, not both")

        # Validate all sources exist (query uses scoped paths)
        unscoped_sources = sorted({obj.source_path for obj in objects if obj.source_path})
        if unscoped_sources:
            scoped_sources = [self._scope_path(p, user_id) or p for p in unscoped_sources]
            existing_sources: set[str] = set()
            for batch in self._chunk_paths(session, scoped_sources, binds_per_item=1):
                stmt = select(self._model.path).where(  # ty: ignore[no-matching-overload]
                    self._model.path.in_(batch),  # ty: ignore[unresolved-attribute]
                    self._model.deleted_at.is_(None),  # ty: ignore[unresolved-attribute]
                )
                result = await session.execute(stmt)
                existing_sources.update(row[0] for row in result.all())

            missing = [p for p in scoped_sources if p not in existing_sources]
            if missing:
                return self._error([f"Source not found: {p}" for p in missing])

        # _write_impl scopes internally, returns unscoped
        result = await self._write_impl(objects=objects, user_id=user_id, session=session)
        if result.success:
            self._graph.invalidate()
        return result

    async def _edit_impl(
        self,
        path: str | None = None,
        candidates: VFSResult | None = None,
        edits: list[EditOperation] | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        """Apply find-and-replace edits: read → replace → write.

        Paths are unscoped.  Each inner call does its own scope cycle,
        so intermediate results (candidate paths in ``read_result``)
        are unscoped throughout.
        """
        self._require_user_id(user_id)
        if not edits:
            return self._error("edit requires at least one EditOperation")

        # _read_impl scopes internally, returns unscoped paths
        read_result = await self._read_impl(path=path, candidates=candidates, user_id=user_id, session=session)
        if not read_result.success:
            return read_result

        to_write: list[VFSObjectBase] = []
        errors: list[str] = []
        for c in read_result.candidates:
            content = c.content
            if content is None:
                errors.append(f"No content to edit: {c.path}")
                continue

            updated_content = content
            for edit in edits:
                r = replace(updated_content, edit.old, edit.new, edit.replace_all)
                if not r.success:
                    errors.append(f"{c.path}: {r.error}")
                    break
                replacement_content = r.content
                if replacement_content is None:
                    errors.append(f"{c.path}: replace returned no content")
                    break
                updated_content = replacement_content
            else:
                # c.path is unscoped — _write_impl will scope it
                to_write.append(self._model(path=c.path, content=updated_content))

        if to_write:
            # _write_impl scopes internally, returns unscoped
            write_result = await self._write_impl(objects=to_write, user_id=user_id, session=session)
            if not write_result.success:
                errors.extend(write_result.errors)
            return self._error(
                VFSResult(
                    candidates=write_result.candidates,
                    errors=errors,
                    success=len(errors) == 0,
                )
            )

        return self._error(VFSResult(errors=errors, success=len(errors) == 0))

    async def _copy_impl(
        self,
        ops: Sequence[TwoPathOperation] | None = None,
        overwrite: bool = True,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        """Copy objects: read sources → write to destinations.

        Paths in *ops* are unscoped.  Each inner ``_read_impl`` /
        ``_write_impl`` call does its own scope-in / unscope-out cycle,
        so intermediate results use unscoped paths throughout.
        """
        self._require_user_id(user_id)
        if not ops:
            return self._error("copy requires at least one operation")

        # Read sources — _read_impl scopes internally, returns unscoped
        src_paths = [op.src for op in ops]
        src_result = await self._read_impl(
            candidates=VFSResult(candidates=[Candidate(path=p) for p in src_paths]),
            user_id=user_id,
            session=session,
        )

        src_by_path = {c.path: c for c in src_result.candidates}
        errors: list[str] = list(src_result.errors)

        # Build write objects with unscoped dest paths
        to_write: list[VFSObjectBase] = []
        for op in ops:
            src = src_by_path.get(op.src)
            if src is None:
                continue
            to_write.append(self._model(path=op.dest, content=src.content or ""))

        if not to_write:
            return self._error(VFSResult(errors=errors, success=len(errors) == 0))

        # Write — _write_impl scopes internally, returns unscoped
        write_result = await self._write_impl(
            objects=to_write,
            overwrite=overwrite,
            user_id=user_id,
            session=session,
        )
        errors.extend(write_result.errors)
        return self._error(
            VFSResult(
                candidates=write_result.candidates,
                errors=errors,
                success=len(errors) == 0,
            )
        )

    async def _move_impl(
        self,
        ops: Sequence[TwoPathOperation] | None = None,
        overwrite: bool = True,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        """Atomic same-mount rename.

        For each operation:
        1. Validate source exists, dest available
        2. Fetch all descendants (children, metadata)
        3. Rewrite paths: replace source prefix with dest
        4. Re-derive parent_path / name on all affected rows
        5. Update connection source_path / target_path references
        """
        self._require_user_id(user_id)
        if not ops:
            return self._error("move requires at least one operation")

        if self._user_scoped and user_id:
            ops = [
                TwoPathOperation(
                    src=self._scope_path(op.src, user_id) or op.src,
                    dest=self._scope_path(op.dest, user_id) or op.dest,
                )
                for op in ops
            ]

        out: list[Candidate] = []
        errors: list[str] = []

        for op in ops:
            # ── 1. Validate ──────────────────────────────────────────
            src_obj = await self._get_object(op.src, session)
            if src_obj is None:
                errors.append(f"Source not found: {op.src}")
                continue

            dest_obj = await self._get_object(op.dest, session)
            if dest_obj is not None:
                errors.append(f"Destination path occupied: {op.dest} — move or delete it first")
                continue

            # ── 2. Fetch descendants ─────────────────────────────────
            descendants: list[VFSObjectBase] = []
            if src_obj.kind == "directory":
                stmt = select(self._model).where(
                    self._model.path.like(_escape_like(op.src) + "/%", escape="\\"),  # ty: ignore[unresolved-attribute]
                    self._model.deleted_at.is_(None),  # ty: ignore[unresolved-attribute]
                )
                result = await session.execute(stmt)
                descendants = list(result.scalars().all())
            else:
                stmt = select(self._model).where(
                    self._model.parent_path == op.src,  # ty: ignore[invalid-argument-type]
                    self._model.deleted_at.is_(None),  # ty: ignore[unresolved-attribute]
                )
                result = await session.execute(stmt)
                descendants = list(result.scalars().all())

            # ── 3-4. Rewrite paths ────────────────────────────────────
            src_obj.path = op.dest
            src_obj._rederive_path_fields()

            for desc in descendants:
                desc.path = op.dest + desc.path[len(op.src) :]
                desc._rederive_path_fields()

            # ── 5a. Fix descendants that are connections ────────────
            # Step 3 prefix-swapped their path, but source_path and
            # the connection path encoding are stale.  Rebuild them.
            for desc in descendants:
                if desc.kind == "connection" and desc.source_path:
                    desc.source_path = op.dest + desc.source_path[len(op.src) :]
                    if desc.target_path and desc.connection_type:
                        desc.path = connection_path(
                            desc.source_path,
                            desc.target_path,
                            desc.connection_type,
                        )
                        desc._rederive_path_fields()

            # ── 5b. Fix connections elsewhere whose target moved ──────
            # Connections live under their source (/.connections/), so
            # outgoing connections already moved with descendants.  We
            # only need to find *incoming* connections from other files
            # whose target_path points into the moved subtree.
            conn_stmt = select(self._model).where(
                self._model.kind == "connection",  # ty: ignore[invalid-argument-type]
                self._model.deleted_at.is_(None),  # ty: ignore[unresolved-attribute]
                or_(
                    self._model.target_path == op.src,  # ty: ignore[invalid-argument-type]
                    self._model.target_path.like(_escape_like(op.src) + "/%", escape="\\"),  # ty: ignore[unresolved-attribute]
                ),
            )
            conn_result = await session.execute(conn_stmt)
            for conn in conn_result.scalars().all():
                conn.target_path = op.dest + conn.target_path[len(op.src) :]  # ty: ignore[not-subscriptable]
                conn.path = connection_path(
                    conn.source_path,  # ty: ignore[invalid-argument-type]
                    conn.target_path,
                    conn.connection_type,  # ty: ignore[invalid-argument-type]
                )
                conn._rederive_path_fields()

            out.append(src_obj.to_candidate(operation="move"))

        await session.flush()
        # Moves may rename connections or rewrite target_path references.
        self._graph.invalidate()
        result = self._unscope_result(
            VFSResult(candidates=out, errors=errors, success=len(errors) == 0),
            user_id,
        )
        return self._error(result)

    # ------------------------------------------------------------------
    # Search / query
    # ------------------------------------------------------------------

    def _scope_filter_prefix(self, prefix: str, user_id: str | None) -> str:
        """Apply user-scoping to a path/glob prefix supplied by the caller.

        Scopes absolute prefixes via :func:`scope_path`; prepends
        ``/user_id`` to relative prefixes.  When not user-scoped, just
        normalises to absolute form.
        """
        if self._user_scoped and user_id:
            if prefix.startswith("/"):
                return scope_path(prefix, user_id)
            return f"/{user_id}/{prefix.lstrip('/')}"
        return prefix if prefix.startswith("/") else "/" + prefix.lstrip("/")

    def _apply_structural_filters(
        self,
        stmt: Any,
        *,
        ext: tuple[str, ...],
        ext_not: tuple[str, ...],
        paths: tuple[str, ...],
        globs: tuple[str, ...],
        globs_not: tuple[str, ...],
        user_id: str | None,
    ) -> Any:
        """Push ext / path-prefix / glob filters into a select statement.

        All filters are AND'd together; within ``paths`` and ``globs``
        the clauses are OR'd (any of the supplied prefixes may match).
        ``globs_not`` is pre-filtered here via ``NOT LIKE``; the caller
        still post-filters with :func:`compile_glob` for correctness on
        patterns LIKE cannot represent precisely.
        """
        if ext:
            stmt = stmt.where(self._model.ext.in_(list(ext)))  # ty: ignore[unresolved-attribute]
        if ext_not:
            stmt = stmt.where(self._model.ext.notin_(list(ext_not)))  # ty: ignore[unresolved-attribute]

        if paths:
            clauses = []
            for raw in paths:
                prefix = self._scope_filter_prefix(raw, user_id).rstrip("/") or "/"
                escaped = _escape_like(prefix)
                clauses.append(self._model.path == prefix)
                clauses.append(self._model.path.like(escaped + "/%", escape="\\"))  # ty: ignore[unresolved-attribute]
            stmt = stmt.where(or_(*clauses))

        if globs:
            clauses = []
            for raw in globs:
                scoped = self._scope_filter_prefix(raw, user_id)
                like = glob_to_sql_like(scoped)
                if like is not None:
                    clauses.append(self._model.path.like(like, escape="\\"))  # ty: ignore[unresolved-attribute]
            if clauses:
                stmt = stmt.where(or_(*clauses))

        if globs_not:
            for raw in globs_not:
                scoped = self._scope_filter_prefix(raw, user_id)
                like = glob_to_sql_like(scoped)
                if like is not None:
                    stmt = stmt.where(~self._model.path.like(like, escape="\\"))  # ty: ignore[unresolved-attribute]

        return stmt

    async def _glob_impl(
        self,
        pattern: str,
        *,
        paths: tuple[str, ...] = (),
        ext: tuple[str, ...] = (),
        max_count: int | None = None,
        candidates: VFSResult | None = None,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        """Glob pattern matching against the namespace.

        Two-layer approach: SQL LIKE pre-filter (coarse, fast) then
        Python regex post-filter (authoritative).  Files and directories
        only by default (§5.4).
        """
        self._require_user_id(user_id)
        candidates = self._scope_candidates(candidates, user_id)
        if candidates is None and self._user_scoped and user_id:
            pattern = scope_path(pattern, user_id) if pattern.startswith("/") else f"/{user_id}/{pattern}"
        if not pattern:
            return self._error("glob requires a pattern")

        regex = compile_glob(pattern)
        if regex is None:
            return self._error(f"Invalid glob pattern: {pattern}")

        # ── With candidates: filter in-memory ─────────────────────────
        if candidates is not None:
            matched = [
                c.model_copy(update={"details": (Detail(operation="glob"),)})
                for c in candidates.candidates
                if regex.match(c.path) is not None
            ]
            if max_count is not None:
                matched = matched[:max_count]
            return self._unscope_result(VFSResult(candidates=matched), user_id)

        # ── Without candidates: query DB ──────────────────────────────
        like_pattern = glob_to_sql_like(pattern)

        stmt = select(self._model).where(
            self._model.kind.in_(["file", "directory"]),  # ty: ignore[unresolved-attribute]
            self._model.deleted_at.is_(None),  # ty: ignore[unresolved-attribute]
        )

        if like_pattern is not None:
            stmt = stmt.where(
                self._model.path.like(like_pattern, escape="\\"),  # ty: ignore[unresolved-attribute]
            )

        stmt = self._apply_structural_filters(
            stmt,
            ext=ext,
            ext_not=(),
            paths=paths,
            globs=(),
            globs_not=(),
            user_id=user_id,
        )

        result = await session.execute(stmt)

        matched = [
            obj.to_candidate(operation="glob") for obj in result.scalars().all() if regex.match(obj.path) is not None
        ]
        matched.sort(key=lambda c: c.path)
        if max_count is not None:
            matched = matched[:max_count]
        return self._unscope_result(VFSResult(candidates=matched), user_id)

    async def _grep_impl(
        self,
        pattern: str,
        *,
        paths: tuple[str, ...] = (),
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
        candidates: VFSResult | None = None,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        """Regex content search across files.

        Pushes structural filters (``ext``, ``paths``, ``globs``) into
        SQL and compiles *pattern* into a Python regex (wrapped for
        ``fixed_strings`` / ``word_regexp``) that scans per line on the
        narrowed candidate set.  Files only by default (§5.4).
        """
        self._require_user_id(user_id)
        candidates = self._scope_candidates(candidates, user_id)
        if not pattern:
            return self._error("grep requires a pattern")

        try:
            regex = _compile_grep_regex(
                pattern,
                case_mode=case_mode,
                fixed_strings=fixed_strings,
                word_regexp=word_regexp,
            )
        except re.error as exc:
            return self._error(f"Invalid regex pattern: {exc}")

        # ── Build path → content map ─────────────────────────────────
        content_map: dict[str, str] = {}

        if candidates is not None:
            # Reuse content already on candidates; hydrate only the gaps
            need_hydration: list[str] = []
            for c in candidates.candidates:
                if c.content is not None:
                    content_map[c.path] = c.content
                else:
                    need_hydration.append(c.path)

            if need_hydration:
                for batch in self._chunk_paths(session, need_hydration, binds_per_item=1):
                    stmt = select(self._model).where(
                        self._model.path.in_(batch),  # ty: ignore[unresolved-attribute]
                        self._model.kind == "file",  # ty: ignore[invalid-argument-type]
                        self._model.deleted_at.is_(None),  # ty: ignore[unresolved-attribute]
                    )
                    stmt = self._apply_structural_filters(
                        stmt,
                        ext=ext,
                        ext_not=ext_not,
                        paths=paths,
                        globs=globs,
                        globs_not=globs_not,
                        user_id=user_id,
                    )
                    result = await session.execute(stmt)
                    for obj in result.scalars().all():
                        if obj.content:
                            content_map[obj.path] = obj.content
        else:
            stmt = select(self._model).where(
                self._model.kind == "file",  # ty: ignore[invalid-argument-type]
                self._model.deleted_at.is_(None),  # ty: ignore[unresolved-attribute]
                self._model.content.isnot(None),  # ty: ignore[unresolved-attribute]
            )
            if self._user_scoped and user_id:
                stmt = stmt.where(self._model.path.like(f"/{user_id}/%"))  # ty: ignore[unresolved-attribute]
            stmt = self._apply_structural_filters(
                stmt,
                ext=ext,
                ext_not=ext_not,
                paths=paths,
                globs=globs,
                globs_not=globs_not,
                user_id=user_id,
            )
            result = await session.execute(stmt)
            for obj in result.scalars().all():
                if obj.content:
                    content_map[obj.path] = obj.content

        # ── Authoritative glob post-filter ───────────────────────────
        # LIKE is a pre-filter; compile_glob is the source of truth.
        if globs or globs_not:
            pos_regexes = [
                r for r in (compile_glob(self._scope_filter_prefix(g, user_id)) for g in globs) if r is not None
            ]
            neg_regexes = [
                r for r in (compile_glob(self._scope_filter_prefix(g, user_id)) for g in globs_not) if r is not None
            ]
            filtered: dict[str, str] = {}
            for p, c in content_map.items():
                if pos_regexes and not any(r.match(p) for r in pos_regexes):
                    continue
                if neg_regexes and any(r.match(p) for r in neg_regexes):
                    continue
                filtered[p] = c
            content_map = filtered

        matched = self._collect_line_matches(
            content_map,
            regex,
            max_count,
            output_mode=output_mode,
            before_context=before_context,
            after_context=after_context,
            invert_match=invert_match,
        )
        return self._unscope_result(VFSResult(candidates=matched), user_id)

    @staticmethod
    def _collect_line_matches(
        content_map: dict[str, str],
        regex: re.Pattern[str],
        max_count: int | None = None,
        *,
        output_mode: GrepOutputMode = "lines",
        before_context: int = 0,
        after_context: int = 0,
        invert_match: bool = False,
    ) -> list[Candidate]:
        """Build grep candidates from a ``{path: content}`` mapping.

        Iterates ``content_map`` in sorted-path order and runs
        ``regex.search`` per line.  ``output_mode`` controls the shape of
        the returned detail metadata:

        * ``"lines"`` — attach per-line matches with merged context
          windows driven by ``before_context`` / ``after_context``.
          Context lines carry ``"context": True`` in the metadata entry.
        * ``"files"`` / ``"count"`` — no line-level detail, just a
          per-file match count.

        ``invert_match`` flips the per-line predicate (``-v``).  Stops at
        *max_count* matched files when set.
        """
        matched: list[Candidate] = []
        for path in sorted(content_map):
            content = content_map[path]
            lines = content.split("\n")
            match_indices: list[int] = []
            for idx, line_text in enumerate(lines):
                hit = regex.search(line_text) is not None
                if hit != invert_match:
                    match_indices.append(idx)
            if not match_indices:
                continue

            match_count = len(match_indices)
            metadata: dict[str, object] = {"match_count": match_count}
            if output_mode == "lines":
                metadata["line_matches"] = _build_line_matches_with_context(
                    lines,
                    match_indices,
                    before_context,
                    after_context,
                )

            matched.append(
                Candidate(
                    path=path,
                    kind="file",
                    details=(
                        Detail(
                            operation="grep",
                            score=float(match_count),
                            metadata=metadata,
                        ),
                    ),
                )
            )
            if max_count is not None and len(matched) >= max_count:
                break
        return matched

    async def _semantic_search_impl(
        self,
        query: str,
        k: int = 15,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        """Embed *query* text, then delegate to vector search."""
        self._require_user_id(user_id)
        if self._embedding_provider is None:
            return self._error("semantic_search requires an embedding provider")
        if self._vector_store is None:
            return self._error("semantic_search requires a vector store")
        if not query or not query.strip():
            return self._error("semantic_search requires a query")

        vector = await self._embedding_provider.embed(query)

        return await self._vector_search_impl(
            vector=list(vector),
            k=k,
            candidates=candidates,
            user_id=user_id,
            session=session,
        )

    async def _vector_search_impl(
        self,
        vector: list[float] | None = None,
        k: int = 15,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        """Query the vector store for nearest neighbours."""
        self._require_user_id(user_id)
        candidates = self._scope_candidates(candidates, user_id)
        if self._vector_store is None:
            return self._error("vector_search requires a vector store")
        if vector is None:
            return self._error("vector_search requires a vector")

        paths = [c.path for c in candidates.candidates] if candidates else None
        hits = await self._vector_store.query(
            vector,
            k=k,
            paths=paths,
            user_id=user_id if self._user_scoped and user_id else None,
        )

        matched = [
            Candidate(
                path=hit.path,
                details=(Detail(operation="vector_search", score=hit.score),),
            )
            for hit in hits
        ]
        return self._unscope_result(VFSResult(candidates=matched), user_id)

    async def _lexical_search_impl(
        self,
        query: str,
        k: int = 15,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        """BM25-scored keyword search across all content.

        Tokenizes *query* (capped at 50 terms), computes IDF against
        the full corpus via COUNT queries, pre-filters candidates with
        SQL LIKE + term-count sort (capped at ``BM25_PRE_FILTER_LIMIT``),
        then scores with ``BM25Scorer`` (Lucene IDF fix, k1=1.5, b=0.75).

        Searches anything with content (files, chunks) — versions are
        excluded (they duplicate file content).
        """
        self._require_user_id(user_id)
        candidates = self._scope_candidates(candidates, user_id)
        if not query or not query.strip():
            return self._error("lexical_search requires a query")

        terms = tokenize_query(query)
        if not terms:
            return self._error("lexical_search: no searchable terms in query")
        unique_terms = tuple(dict.fromkeys(terms))
        term_set = frozenset(unique_terms)

        docs, prefilter_truncated, local_doc_freqs, candidate_vocab_doc_freqs = await self._fetch_lexical_docs(
            unique_terms=unique_terms,
            term_set=term_set,
            candidates=candidates,
            user_id=user_id,
            session=session,
        )
        if not docs:
            return VFSResult(candidates=[])

        doc_lengths = [doc.doc_length for doc in docs]
        term_frequency_docs = [doc.term_freqs for doc in docs]

        if candidates is not None:
            corpus_size = len(docs)
            avgdl = sum(doc_lengths) / corpus_size if corpus_size > 0 else 1.0
            doc_freqs = local_doc_freqs
        else:
            corpus_size, avgdl, doc_freqs = await self._fetch_corpus_stats(
                unique_terms=unique_terms,
                doc_lengths=doc_lengths,
                local_doc_freqs=local_doc_freqs,
                prefilter_truncated=prefilter_truncated,
                user_id=user_id,
                session=session,
            )

        scorer = BM25Scorer(corpus_size=corpus_size, avg_doc_length=avgdl)
        scorer.set_idf(
            doc_freqs,
            average_idf=self._estimate_average_idf(
                candidate_vocab_doc_freqs,
                corpus_size,
            ),
        )
        scores = scorer.score_batch_term_frequencies(terms, term_frequency_docs, doc_lengths)

        scored = sorted(
            ((doc, score) for doc, score in zip(docs, scores, strict=True) if score > 0),
            key=lambda x: x[1],
            reverse=True,
        )[:k]

        matched = [
            Candidate(
                path=doc.path,
                kind=doc.kind,
                content=doc.content,
                details=(Detail(operation="lexical_search", score=score),),
            )
            for doc, score in scored
        ]

        return self._unscope_result(VFSResult(candidates=matched), user_id)

    async def _tree_impl(
        self,
        path: str,
        max_depth: int | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        """Recursive directory listing.

        Returns all descendant files and directories under *path*,
        sorted by path.  ``max_depth`` limits how many levels deep
        the traversal goes (1 = direct children only).
        Metadata kinds are excluded (§5.4).
        """
        self._require_user_id(user_id)
        path = self._scope_path(path, user_id) or path
        # Default to root
        if not path:
            path = "/"

        if max_depth is not None and max_depth < 1:
            return self._error(f"max_depth must be >= 1, got {max_depth}")

        # Validate path exists and is a directory (skip for root)
        if path != "/":
            obj = await self._get_object(path, session)
            if obj is None:
                return self._error(f"Not found: {path}")
            if obj.kind != "directory":
                return self._error(f"Not a directory: {path}")

        # ── Query descendants ─────────────────────────────────────────
        stmt = select(self._model).where(
            self._model.kind.in_(["file", "directory"]),  # ty: ignore[unresolved-attribute]
            self._model.deleted_at.is_(None),  # ty: ignore[unresolved-attribute]
        )

        if path == "/":
            stmt = stmt.where(self._model.path != "/")  # ty: ignore[invalid-argument-type]
        else:
            stmt = stmt.where(
                self._model.path.like(path + "/%", escape="\\"),  # ty: ignore[unresolved-attribute]
            )

        # Depth limiting via slash counting
        if max_depth is not None:
            slash_count = func.length(self._model.path) - func.length(
                func.replace(self._model.path, "/", ""),
            )
            max_slashes = max_depth if path == "/" else path.count("/") + max_depth
            stmt = stmt.where(slash_count <= max_slashes)

        result = await session.execute(stmt)
        objects = sorted(result.scalars().all(), key=lambda o: o.path)

        tree_candidates = [obj.to_candidate(operation="tree") for obj in objects]
        return self._unscope_result(VFSResult(candidates=tree_candidates), user_id)

    # ------------------------------------------------------------------
    # Graph — delegate to self._graph (RustworkxGraph)
    # ------------------------------------------------------------------

    def _to_candidates(
        self,
        path: str | None,
        candidates: VFSResult | None,
    ) -> VFSResult:
        """Normalize path/candidates into a VFSResult for the graph."""
        if candidates is not None:
            return candidates
        if path is not None:
            return VFSResult(candidates=[Candidate(path=path)])
        return VFSResult(candidates=[])

    async def _predecessors_impl(
        self,
        path: str | None = None,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        self._require_user_id(user_id)
        path = self._scope_path(path, user_id)
        candidates = self._scope_candidates(candidates, user_id)
        result = await self._graph.predecessors(
            self._to_candidates(path, candidates),
            user_id=user_id,
            session=session,
        )
        return self._unscope_result(result, user_id)

    async def _successors_impl(
        self,
        path: str | None = None,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        self._require_user_id(user_id)
        path = self._scope_path(path, user_id)
        candidates = self._scope_candidates(candidates, user_id)
        result = await self._graph.successors(
            self._to_candidates(path, candidates),
            user_id=user_id,
            session=session,
        )
        return self._unscope_result(result, user_id)

    async def _ancestors_impl(
        self,
        path: str | None = None,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        self._require_user_id(user_id)
        path = self._scope_path(path, user_id)
        candidates = self._scope_candidates(candidates, user_id)
        result = await self._graph.ancestors(
            self._to_candidates(path, candidates),
            user_id=user_id,
            session=session,
        )
        return self._unscope_result(result, user_id)

    async def _descendants_impl(
        self,
        path: str | None = None,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        self._require_user_id(user_id)
        path = self._scope_path(path, user_id)
        candidates = self._scope_candidates(candidates, user_id)
        result = await self._graph.descendants(
            self._to_candidates(path, candidates),
            user_id=user_id,
            session=session,
        )
        return self._unscope_result(result, user_id)

    async def _neighborhood_impl(
        self,
        path: str | None = None,
        candidates: VFSResult | None = None,
        *,
        depth: int = 2,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        self._require_user_id(user_id)
        path = self._scope_path(path, user_id)
        candidates = self._scope_candidates(candidates, user_id)
        result = await self._graph.neighborhood(
            self._to_candidates(path, candidates),
            depth=depth,
            user_id=user_id,
            session=session,
        )
        return self._unscope_result(result, user_id)

    async def _meeting_subgraph_impl(
        self,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        self._require_user_id(user_id)
        candidates = self._scope_candidates(candidates, user_id)
        result = await self._graph.meeting_subgraph(
            self._to_candidates(None, candidates),
            user_id=user_id,
            session=session,
        )
        return self._unscope_result(result, user_id)

    async def _min_meeting_subgraph_impl(
        self,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        self._require_user_id(user_id)
        candidates = self._scope_candidates(candidates, user_id)
        result = await self._graph.min_meeting_subgraph(
            self._to_candidates(None, candidates),
            user_id=user_id,
            session=session,
        )
        return self._unscope_result(result, user_id)

    async def _pagerank_impl(
        self,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        self._require_user_id(user_id)
        candidates = self._scope_candidates(candidates, user_id)
        result = await self._graph.pagerank(
            self._to_candidates(None, candidates),
            user_id=user_id,
            session=session,
        )
        return self._unscope_result(result, user_id)

    async def _betweenness_centrality_impl(
        self,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        self._require_user_id(user_id)
        candidates = self._scope_candidates(candidates, user_id)
        result = await self._graph.betweenness_centrality(
            self._to_candidates(None, candidates),
            user_id=user_id,
            session=session,
        )
        return self._unscope_result(result, user_id)

    async def _closeness_centrality_impl(
        self,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        self._require_user_id(user_id)
        candidates = self._scope_candidates(candidates, user_id)
        result = await self._graph.closeness_centrality(
            self._to_candidates(None, candidates),
            user_id=user_id,
            session=session,
        )
        return self._unscope_result(result, user_id)

    async def _degree_centrality_impl(
        self,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        self._require_user_id(user_id)
        candidates = self._scope_candidates(candidates, user_id)
        result = await self._graph.degree_centrality(
            self._to_candidates(None, candidates),
            user_id=user_id,
            session=session,
        )
        return self._unscope_result(result, user_id)

    async def _in_degree_centrality_impl(
        self,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        self._require_user_id(user_id)
        candidates = self._scope_candidates(candidates, user_id)
        result = await self._graph.in_degree_centrality(
            self._to_candidates(None, candidates),
            user_id=user_id,
            session=session,
        )
        return self._unscope_result(result, user_id)

    async def _out_degree_centrality_impl(
        self,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        self._require_user_id(user_id)
        candidates = self._scope_candidates(candidates, user_id)
        result = await self._graph.out_degree_centrality(
            self._to_candidates(None, candidates),
            user_id=user_id,
            session=session,
        )
        return self._unscope_result(result, user_id)

    async def _hits_impl(
        self,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        self._require_user_id(user_id)
        candidates = self._scope_candidates(candidates, user_id)
        result = await self._graph.hits(
            self._to_candidates(None, candidates),
            user_id=user_id,
            session=session,
        )
        return self._unscope_result(result, user_id)
