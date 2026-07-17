"""Write-family statement builders for ``DatabaseStorage`` — write, edit, mkdir.

Plan-then-execute, mirroring the memory backend's stage-against-a-copy:
one ``path IN`` select fetches committed state for the batch's targets
and ancestors, a pure staging pass replays the POSIX parent/site gates
against committed-plus-staged state and accumulates classified per-entry
errors, and only an error-free plan executes — a failed batch runs no
mutation statement at all. Execution is a handful of bulk Core
statements in pinned order: revision allocation, entry inserts layered
parents-before-children (chunked by the dialect's parameter budget),
guarded material updates with a verification read, content
delete-then-insert, and unconditional parent bumps. Every function
takes the op's live ``AsyncSession`` and never begins or commits — the
protocol method in ``backend.py`` owns its one transaction.

Concurrent create arbitration follows the dialect's declared mode:
``upsert`` rides ``ON CONFLICT`` on the ``(parent_id, name)`` index,
``catch_retry`` wraps the bulk insert in a savepoint and resolves each
conflicting row individually. Revisions come from the durable per-mount
counter via :func:`allocate_revisions`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, Literal

from pydantic import ValidationError
from sqlalchemy import bindparam, delete, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from ulid import ULID

from vfs.models import Entry, Observation
from vfs.results import Result, ResultError, VFSErrorKind
from vfs.storage.backends.database.descent import (
    ancestor_chain,
    classified,
    classify_misses,
    in_trash,
    trash_filters,
)
from vfs.storage.backends.database.reads import CONTENT_KINDS
from vfs.storage.replace import replace

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from typing import Any

    from sqlalchemy import Table
    from sqlalchemy.engine import RowMapping
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models.rows import VFSTables
    from vfs.paths import ObjectKind, Path
    from vfs.storage.backends.database.dialects import DialectProfile
    from vfs.storage.replace import EditOperation

_Status = Literal["created", "updated", "unchanged"]

# Columns an overwrite clobbers when arbitration lands on a rival's row:
# the row keeps its identity (id, node_id, site, created_at) and takes
# our material state.
_CLOBBER_COLUMNS: Final[tuple[str, ...]] = (
    "kind",
    "revision",
    "content_hash",
    "mime_type",
    "ext",
    "lines",
    "size_bytes",
    "chunked",
    "encoded",
    "owner_id",
    "updated_at",
)


@dataclass
class _Staged:
    """One path's planned final state: a create or a material update."""

    path: Path
    parent: Path
    kind: ObjectKind
    created: bool
    content: str | None = None
    content_hash: str | None = None
    size_bytes: int = 0
    lines: int = 0
    ext: str | None = None
    mime_type: str | None = None
    entry_id: int | None = None  # committed id for updates; creates learn theirs at insert
    base_revision: int | None = None  # the update guard; None = unguarded (arbitration clobber)
    revision: int = 0  # assigned from the allocated range before execution


# ---------------------------------------------------------------------------
# Revision allocation — the per-mount monotone sequence
# ---------------------------------------------------------------------------


async def allocate_revisions(session: AsyncSession, meta: Table, count: int) -> int:
    """Claim *count* values from the mount's revision sequence; return the high end.

    The claimed values are ``high - count + 1 .. high``. The counter row's
    lock is held to commit, which serializes write transactions per mount
    and makes commit order equal allocation order — the property the index
    watermark leans on. A provider that needs concurrent writers per mount
    may replace this with a native sequence (``nextval`` range,
    ``sp_sequence_get_range``), provided reindex then captures its
    watermark under a writer fence instead of assuming ordered commits.
    """
    bump = update(meta).where(meta.c.id == 1).values(revision_counter=meta.c.revision_counter + count)
    await session.execute(bump)
    return (await session.execute(select(meta.c.revision_counter).where(meta.c.id == 1))).scalar_one()


# ---------------------------------------------------------------------------
# Write-family builders
# ---------------------------------------------------------------------------


async def write_rows(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    parameter_budget: int,
    *,
    entries: list[Entry],
    overwrite: bool,
    parents: bool,
    user_id: str | None,
) -> Result:
    committed = await _fetch_committed(session, tables, {entry.path for entry in entries})
    plan = _Plan(committed, user_id=user_id, budget=profile.key_byte_budget)
    for entry in entries:
        if entry.kind == "directory":
            status = plan.put_dir(entry.path, parents=parents)
        else:
            status = plan.put_file(
                entry.path,
                kind=entry.kind,
                content=entry.content,
                content_hash=entry.content_hash,
                size_bytes=entry.size_bytes,
                lines=entry.lines,
                ext=entry.ext,
                mime_type=entry.mime_type,
                overwrite=overwrite,
                parents=parents,
            )
        if status is not None:
            plan.pending.append((entry.path, status))
    return await _finish(session, tables, profile, parameter_budget, plan, op="write", overwrite=overwrite)


async def mkdir_rows(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    parameter_budget: int,
    *,
    path: Path,
    parents: bool,
    exist_ok: bool,
    user_id: str | None,
) -> Result:
    committed = await _fetch_committed(session, tables, {path})
    plan = _Plan(committed, user_id=user_id, budget=profile.key_byte_budget)
    if not plan.outside_trash(path):
        return Result(ops=("mkdir",), errors=plan.errors)
    occupant = plan.kind_of(path)
    if occupant is not None:
        if exist_ok and occupant == "directory":
            plan.pending.append((path, "unchanged"))
            return await _finish(session, tables, profile, parameter_budget, plan, op="mkdir", overwrite=False)
        return Result(ops=("mkdir",), errors=[classified(VFSErrorKind.exists, f"Already exists: {path}", path)])
    if not plan.within_budget(path) or not plan.parent_gate(path, parents=parents, target=path):
        return Result(ops=("mkdir",), errors=plan.errors)
    minted = plan.mint_chain(path)
    plan.stage_create(path, kind="directory")
    plan.pending.extend((p, "created") for p in (*minted, path))
    return await _finish(session, tables, profile, parameter_budget, plan, op="mkdir", overwrite=False)


async def edit_rows(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    parameter_budget: int,
    *,
    edits: list[EditOperation],
    targets: Sequence[Path],
    user_id: str | None,
) -> Result:
    committed = await _fetch_committed(session, tables, set(targets), with_content=True)
    misses = [t for t in dict.fromkeys(targets) if str(t) not in committed]
    miss_errors = dict(zip(misses, await classify_misses(session, tables.entry, misses), strict=True))
    plan = _Plan(committed, user_id=user_id, budget=profile.key_byte_budget)
    for target in targets:
        row = committed.get(str(target))
        if row is None:
            plan.errors.append(miss_errors[target])
            continue
        staged = plan.staged.get(target)
        kind = staged.kind if staged is not None else row["kind"]
        current = staged.content if staged is not None else row["content"]
        if kind not in CONTENT_KINDS or current is None:
            plan.errors.append(classified(VFSErrorKind.wrong_kind, f"No editable content: {target}", target))
            continue
        failed: ResultError | None = None
        for op in edits:
            outcome = replace(current, op.old, op.new, replace_all=op.replace_all)
            if not outcome.success or outcome.content is None:
                failed = classified(VFSErrorKind.invalid, outcome.error or "edit failed", target)
                break
            current = outcome.content
        if failed is not None:
            plan.errors.append(failed)
            continue
        try:
            # Edits synthesize content, so the result re-enters the same
            # gate writes pass: Entry owns every content invariant.
            edited = Entry(path=target, kind=kind, content=current)
        except ValidationError as exc:
            plan.errors.append(classified(VFSErrorKind.invalid, exc.errors()[0]["msg"], target))
            continue
        plan.stage_update(
            target,
            kind=kind,
            content=edited.content,
            content_hash=edited.content_hash,
            size_bytes=edited.size_bytes,
            lines=edited.lines,
            ext=row["ext"],
            mime_type=row["mime_type"],
        )
        plan.pending.append((target, "updated"))
    return await _finish(session, tables, profile, parameter_budget, plan, op="edit", overwrite=True)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class _Plan:
    """Staged batch state: the committed snapshot, staged rows, bumps, errors.

    ``staged`` overlays ``committed`` for every gate, so entries in one
    batch see the parents earlier entries minted; ``bumps`` collects the
    committed directories whose membership changed. Any error fails the
    batch whole — an errored plan is never executed.
    """

    def __init__(self, committed: dict[str, RowMapping], *, user_id: str | None, budget: int) -> None:
        self.committed = committed
        self.user_id = user_id
        self.budget = budget
        self.staged: dict[Path, _Staged] = {}
        self.bumps: set[str] = set()
        self.bump_revisions: dict[str, int] = {}
        self.errors: list[ResultError] = []
        self.pending: list[tuple[Path, _Status]] = []

    def kind_of(self, path: Path) -> str | None:
        staged = self.staged.get(path)
        if staged is not None:
            return staged.kind
        row = self.committed.get(str(path))
        return row["kind"] if row is not None else None

    def outside_trash(self, path: Path) -> bool:
        """Refuse the reserved trash subtree as a write target.

        Rows minted there would be invisible to every read verb — a
        write-only hole, since the liveness filter hides the trash scope.
        """
        if not in_trash(path):
            return True
        self.errors.append(
            classified(
                VFSErrorKind.invalid,
                f"Cannot write into the reserved trash namespace: {path}",
                path,
                target=path,
            )
        )
        return False

    def within_budget(self, path: Path) -> bool:
        """A lawful path can still exceed an engine's index-key byte cap."""
        if len(str(path).encode()) <= self.budget:
            return True
        self.errors.append(
            classified(
                VFSErrorKind.unaddressable,
                f"Path exceeds this engine's {self.budget}-byte key budget: {path}",
                path,
                target=path,
            )
        )
        return False

    def parent_gate(self, path: Path, *, parents: bool, target: Path) -> bool:
        """The POSIX parent rule: wrong_kind is unconditional; absence needs the flag."""
        for ancestor in ancestor_chain(path):
            kind = self.kind_of(ancestor)
            if kind is None:
                if parents:
                    return True
                self.errors.append(
                    classified(VFSErrorKind.not_found, f"Not found: {ancestor}", ancestor, target=target)
                )
                return False
            if kind != "directory":
                self.errors.append(
                    classified(VFSErrorKind.wrong_kind, f"Not a directory: {ancestor}", ancestor, target=target)
                )
                return False
        return True

    def put_file(
        self,
        target: Path,
        *,
        kind: ObjectKind,
        content: str | None,
        content_hash: str | None,
        size_bytes: int,
        lines: int,
        ext: str | None,
        mime_type: str | None,
        overwrite: bool,
        parents: bool,
    ) -> _Status | None:
        """Gate and stage one content-bearing row; ``None`` means an error was appended."""
        if not self.outside_trash(target) or not self.within_budget(target):
            return None
        if not self.parent_gate(target, parents=parents, target=target):
            return None
        occupant = self.kind_of(target)
        if occupant is not None:
            if occupant == "directory":
                self.errors.append(classified(VFSErrorKind.wrong_kind, f"Is a directory: {target}", target))
                return None
            if not overwrite:
                self.errors.append(classified(VFSErrorKind.exists, f"Already exists: {target}", target))
                return None
        self.mint_chain(target)
        stage = self.stage_create if occupant is None else self.stage_update
        stage(
            target,
            kind=kind,
            content=content,
            content_hash=content_hash,
            size_bytes=size_bytes,
            lines=lines,
            ext=ext,
            mime_type=mime_type,
        )
        return "created" if occupant is None else "updated"

    def put_dir(self, target: Path, *, parents: bool) -> _Status | None:
        if not self.outside_trash(target):
            return None
        occupant = self.kind_of(target)
        if occupant is not None:
            if occupant != "directory":
                self.errors.append(classified(VFSErrorKind.wrong_kind, f"Not a directory: {target}", target))
                return None
            return "unchanged"
        if not self.within_budget(target) or not self.parent_gate(target, parents=parents, target=target):
            return None
        self.mint_chain(target)
        self.stage_create(target, kind="directory")
        return "created"

    def mint_chain(self, path: Path) -> list[Path]:
        """Stage the missing ancestor directories of *path*, shallowest first."""
        minted: list[Path] = []
        for ancestor in ancestor_chain(path):
            if self.kind_of(ancestor) is None:
                self.stage_create(ancestor, kind="directory")
                minted.append(ancestor)
        return minted

    def stage_create(
        self,
        path: Path,
        *,
        kind: ObjectKind,
        content: str | None = None,
        content_hash: str | None = None,
        size_bytes: int = 0,
        lines: int = 0,
        ext: str | None = None,
        mime_type: str | None = None,
    ) -> None:
        prior = self.staged.get(path)
        if prior is not None:  # a repeat target folds into the one staged row
            self._refresh(prior, kind, content, content_hash, size_bytes, lines, ext, mime_type)
            return
        self.staged[path] = _Staged(
            path=path,
            parent=path.parent_dir,
            kind=kind,
            created=True,
            content=content,
            content_hash=content_hash,
            size_bytes=size_bytes,
            lines=lines,
            ext=ext,
            mime_type=mime_type,
        )
        self.bump_parent(path)

    def stage_update(
        self,
        path: Path,
        *,
        kind: ObjectKind,
        content: str | None,
        content_hash: str | None,
        size_bytes: int,
        lines: int,
        ext: str | None,
        mime_type: str | None,
    ) -> None:
        prior = self.staged.get(path)
        if prior is not None:
            self._refresh(prior, kind, content, content_hash, size_bytes, lines, ext, mime_type)
            return
        row = self.committed[str(path)]
        self.staged[path] = _Staged(
            path=path,
            parent=path.parent_dir,
            kind=kind,
            created=False,
            content=content,
            content_hash=content_hash,
            size_bytes=size_bytes,
            lines=lines,
            ext=ext,
            mime_type=mime_type,
            entry_id=row["id"],
            base_revision=row["revision"],
        )

    def bump_parent(self, path: Path) -> None:
        """Mark a namespace mutation at *path*: its committed parent gets a bump.

        A batch-minted parent is skipped — its single fresh revision already
        reflects the membership it was created with.
        """
        parent = path.parent_dir
        if parent not in self.staged and str(parent) in self.committed:
            self.bumps.add(str(parent))

    def _refresh(
        self,
        prior: _Staged,
        kind: ObjectKind,
        content: str | None,
        content_hash: str | None,
        size_bytes: int,
        lines: int,
        ext: str | None,
        mime_type: str | None,
    ) -> None:
        prior.kind = kind
        prior.content = content
        prior.content_hash = content_hash
        prior.size_bytes = size_bytes
        prior.lines = lines
        prior.ext = ext
        prior.mime_type = mime_type


async def _fetch_committed(
    session: AsyncSession,
    tables: VFSTables,
    targets: set[Path],
    *,
    with_content: bool = False,
) -> dict[str, RowMapping]:
    """One ``path IN`` select for the batch: targets, their ancestors, the root."""
    entry = tables.entry
    paths = {str(t) for t in targets} | {str(a) for t in targets for a in ancestor_chain(t)} | {"/"}
    columns: list[Any] = [
        entry.c.id,
        entry.c.path,
        entry.c.kind,
        entry.c.revision,
        entry.c.ext,
        entry.c.mime_type,
    ]
    source: Any = entry
    if with_content:
        columns.append(tables.content.c.content)
        source = entry.outerjoin(tables.content, tables.content.c.entry_id == entry.c.id)
    stmt = select(*columns).select_from(source).where(entry.c.path.in_(sorted(paths)), *trash_filters(entry))
    return {mapping["path"]: mapping for mapping in (await session.execute(stmt)).mappings()}


async def _finish(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    parameter_budget: int,
    plan: _Plan,
    *,
    op: str,
    overwrite: bool,
) -> Result:
    """Execute an error-free plan and assemble the batch's observations."""
    if plan.errors:
        return Result(ops=(op,), errors=plan.errors)
    late = await _apply(session, tables, profile, parameter_budget, plan, overwrite=overwrite)
    if late:
        return Result(ops=(op,), errors=late)
    rows: list[Observation] = []
    for path, status in plan.pending:
        staged = plan.staged.get(path)
        if staged is not None:
            rows.append(
                Observation(
                    path=path,
                    kind=staged.kind,
                    size_bytes=staged.size_bytes if staged.content is not None else None,
                    revision=staged.revision,
                    status=status,
                )
            )
        else:
            # A later entry may have bumped this unchanged row; the
            # observation must equal a post-commit stat of its path.
            row = plan.committed[str(path)]
            revision = plan.bump_revisions.get(str(path), row["revision"])
            rows.append(Observation(path=path, kind=row["kind"], revision=revision, status=status))
    return Result(ops=(op,), observations=rows)


async def _apply(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    parameter_budget: int,
    plan: _Plan,
    *,
    overwrite: bool,
) -> list[ResultError]:
    """Run the pinned statement sequence; a non-empty return fails the batch."""
    creates = [s for s in plan.staged.values() if s.created]
    updates = [s for s in plan.staged.values() if not s.created]
    total = len(creates) + len(updates) + len(plan.bumps)
    if total == 0:
        return []
    now = datetime.now(UTC)
    high = await allocate_revisions(session, tables.meta, total)
    values = iter(range(high - total + 1, high + 1))
    for staged in (*creates, *updates):
        staged.revision = next(values)
    # Kept on the plan: an "unchanged" observation of a bumped directory
    # must report the bump, not its pre-batch revision.
    plan.bump_revisions = {path: next(values) for path in sorted(plan.bumps)}

    errors = await _insert_creates(
        session, tables.entry, profile, parameter_budget, creates, plan, overwrite=overwrite, now=now
    )
    if errors:
        return errors
    # Arbitration may convert a create into a clobbering update of the
    # rival's row, so the update set is collected only after inserts ran.
    updates = [s for s in plan.staged.values() if not s.created]
    errors = await _update_materials(session, tables.entry, updates, user_id=plan.user_id, now=now)
    if errors:
        return errors
    await _replace_content(session, tables.content, list(plan.staged.values()))
    if plan.bump_revisions:
        entry = tables.entry
        rows = [
            {"b_id": plan.committed[path]["id"], "b_rev": revision}
            for path, revision in plan.bump_revisions.items()
        ]
        await session.execute(
            update(entry).where(entry.c.id == bindparam("b_id")).values(revision=bindparam("b_rev")), rows
        )
    return []


async def _insert_creates(
    session: AsyncSession,
    entry: Table,
    profile: DialectProfile,
    parameter_budget: int,
    creates: list[_Staged],
    plan: _Plan,
    *,
    overwrite: bool,
    now: datetime,
) -> list[ResultError]:
    """Bulk-insert created rows, parents before children, arbitrating conflicts."""
    if not creates:
        return []
    by_depth: dict[int, list[_Staged]] = {}
    for staged in creates:
        by_depth.setdefault(str(staged.path).count("/"), []).append(staged)
    for depth in sorted(by_depth):
        layer = by_depth[depth]
        rows = [_entry_values(s, _parent_id(plan, s), plan.user_id, now) for s in layer]
        per_statement = max(1, parameter_budget // len(rows[0]))
        if profile.arbitration == "upsert":
            errors = await _upsert_layer(session, entry, profile, layer, rows, per_statement, overwrite=overwrite)
        else:
            errors = await _catch_retry_layer(session, entry, layer, rows, per_statement, overwrite=overwrite)
        if errors:
            # Fail fast: children of an unresolved parent cannot be wired.
            return errors
    return []


async def _upsert_layer(
    session: AsyncSession,
    entry: Table,
    profile: DialectProfile,
    layer: list[_Staged],
    rows: list[dict[str, Any]],
    per_statement: int,
    *,
    overwrite: bool,
) -> list[ResultError]:
    """``ON CONFLICT`` arbitration on the ``(parent_id, name)`` index.

    Directory creates never clobber (``DO NOTHING``); file creates clobber
    a non-directory rival under ``overwrite``. A row missing from RETURNING
    lost arbitration and classifies — a definite outcome, never retried.
    """
    constructor = _upsert_constructor(profile)
    pairs = list(zip(layer, rows, strict=True))
    directories = [(s, r) for s, r in pairs if s.kind == "directory"]
    files = [(s, r) for s, r in pairs if s.kind != "directory"]
    errors: list[ResultError] = []
    for group, clobber in ((directories, False), (files, overwrite)):
        for chunk in _chunked(group, per_statement):
            stmt = constructor(entry).values([r for _, r in chunk])
            if clobber:
                stmt = stmt.on_conflict_do_update(
                    index_elements=["parent_id", "name"],
                    set_={column: stmt.excluded[column] for column in _CLOBBER_COLUMNS},
                    where=entry.c.kind != "directory",
                )
            else:
                stmt = stmt.on_conflict_do_nothing(index_elements=["parent_id", "name"])
            result = await session.execute(stmt.returning(entry.c.id, entry.c.path))
            returned = {mapping["path"]: mapping["id"] for mapping in result.mappings()}
            for staged, _ in chunk:
                won = returned.get(str(staged.path))
                if won is not None:
                    staged.entry_id = won
                elif clobber:
                    errors.append(classified(VFSErrorKind.wrong_kind, f"Is a directory: {staged.path}", staged.path))
                else:
                    errors.append(classified(VFSErrorKind.exists, f"Already exists: {staged.path}", staged.path))
    return errors


async def _catch_retry_layer(
    session: AsyncSession,
    entry: Table,
    layer: list[_Staged],
    rows: list[dict[str, Any]],
    per_statement: int,
    *,
    overwrite: bool,
) -> list[ResultError]:
    """Portable arbitration: savepointed bulk insert, per-row resolution on conflict."""
    try:
        async with session.begin_nested():
            returned: dict[str, int] = {}
            for chunk in _chunked(rows, per_statement):
                result = await session.execute(insert(entry).values(chunk).returning(entry.c.id, entry.c.path))
                returned.update({mapping["path"]: mapping["id"] for mapping in result.mappings()})
    except IntegrityError:
        return await _resolve_rows(session, entry, layer, rows, overwrite=overwrite)
    for staged in layer:
        staged.entry_id = returned[str(staged.path)]
    return []


async def _resolve_rows(
    session: AsyncSession,
    entry: Table,
    layer: list[_Staged],
    rows: list[dict[str, Any]],
    *,
    overwrite: bool,
) -> list[ResultError]:
    """Re-run a conflicted layer row-at-a-time, each insert in its own savepoint."""
    errors: list[ResultError] = []
    for staged, values in zip(layer, rows, strict=True):
        try:
            async with session.begin_nested():
                result = await session.execute(insert(entry).values(**values).returning(entry.c.id))
                staged.entry_id = result.scalar_one()
            continue
        except IntegrityError:
            pass
        occupant_query = select(entry.c.id, entry.c.kind).where(
            entry.c.parent_id == values["parent_id"], entry.c.name == values["name"]
        )
        occupant = (await session.execute(occupant_query)).one_or_none()
        if occupant is None:
            errors.append(
                classified(VFSErrorKind.conflict, f"Concurrent write lost arbitration: {staged.path}", staged.path)
            )
        elif staged.kind != "directory" and overwrite and occupant.kind != "directory":
            # The rival's row absorbs our write: an unguarded clobbering update.
            staged.created = False
            staged.entry_id = occupant.id
            staged.base_revision = None
        elif staged.kind != "directory" and overwrite:
            errors.append(classified(VFSErrorKind.wrong_kind, f"Is a directory: {staged.path}", staged.path))
        else:
            errors.append(classified(VFSErrorKind.exists, f"Already exists: {staged.path}", staged.path))
    return errors


async def _update_materials(
    session: AsyncSession,
    entry: Table,
    updates: list[_Staged],
    *,
    user_id: str | None,
    now: datetime,
) -> list[ResultError]:
    """Material updates with the revision guard, verified by one read-back.

    The guard's zero-rowcount arm is unreachable on SQLite (single writer)
    and on Postgres at REPEATABLE READ (rivals surface as 40001); it is
    load-bearing at READ COMMITTED — topology verbs, the generic-dialect
    floor — where a lost update is otherwise silent. The read-back
    attributes conflicts portably instead of trusting per-driver
    executemany rowcounts.
    """
    if not updates:
        return []
    guarded = [s for s in updates if s.base_revision is not None]
    unguarded = [s for s in updates if s.base_revision is None]
    material = {
        "kind": bindparam("b_kind"),
        "revision": bindparam("b_rev"),
        "content_hash": bindparam("b_hash"),
        "mime_type": bindparam("b_mime"),
        "ext": bindparam("b_ext"),
        "lines": bindparam("b_lines"),
        "size_bytes": bindparam("b_size"),
        "chunked": False,
        "encoded": False,
        # Ownership follows the writer, matching _CLOBBER_COLUMNS — the
        # two arbitration arms must leave identical observable state.
        "owner_id": bindparam("b_owner"),
        "updated_at": bindparam("b_updated"),
    }
    if guarded:
        stmt = (
            update(entry)
            .where(entry.c.id == bindparam("b_id"), entry.c.revision == bindparam("b_base"))
            .values(**material)
        )
        await session.execute(stmt, [_update_params(s, user_id, now) | {"b_base": s.base_revision} for s in guarded])
    if unguarded:
        stmt = update(entry).where(entry.c.id == bindparam("b_id")).values(**material)
        await session.execute(stmt, [_update_params(s, user_id, now) for s in unguarded])
    check = await session.execute(
        select(entry.c.id, entry.c.revision).where(entry.c.id.in_([s.entry_id for s in updates]))
    )
    actual = {row.id: row.revision for row in check}
    return [
        classified(VFSErrorKind.conflict, f"Concurrent modification: {s.path}", s.path, target=s.path)
        for s in updates
        if actual.get(s.entry_id) != s.revision
    ]


async def _replace_content(session: AsyncSession, content: Table, staged: list[_Staged]) -> None:
    """Delete-then-insert the batch's content rows — portable, idempotent."""
    bearing = [s for s in staged if s.content is not None and s.kind in CONTENT_KINDS]
    if not bearing:
        return
    await session.execute(delete(content).where(content.c.entry_id.in_([s.entry_id for s in bearing])))
    await session.execute(insert(content), [{"entry_id": s.entry_id, "content": s.content} for s in bearing])


def _upsert_constructor(profile: DialectProfile) -> Any:
    """The dialect's ``ON CONFLICT`` insert — only upsert-arbitration engines get here."""
    return sqlite_insert if profile.name == "sqlite" else pg_insert


def _parent_id(plan: _Plan, staged: _Staged) -> int:
    parent = plan.staged.get(staged.parent)
    if parent is not None and parent.entry_id is not None:
        return parent.entry_id
    return plan.committed[str(staged.parent)]["id"]


def _entry_values(staged: _Staged, parent_id: int, user_id: str | None, now: datetime) -> dict[str, Any]:
    return {
        "node_id": str(ULID()),
        "parent_id": parent_id,
        "path": str(staged.path),
        "name": staged.path.name,
        "kind": staged.kind,
        "revision": staged.revision,
        "content_hash": staged.content_hash,
        "mime_type": staged.mime_type,
        "ext": staged.ext,
        "lines": staged.lines,
        "size_bytes": staged.size_bytes,
        "chunked": False,
        "encoded": False,
        "owner_id": user_id,
        "created_at": now,
        "updated_at": now,
    }


def _update_params(staged: _Staged, user_id: str | None, now: datetime) -> dict[str, Any]:
    return {
        "b_id": staged.entry_id,
        "b_kind": staged.kind,
        "b_rev": staged.revision,
        "b_hash": staged.content_hash,
        "b_mime": staged.mime_type,
        "b_ext": staged.ext,
        "b_lines": staged.lines,
        "b_size": staged.size_bytes,
        "b_owner": user_id,
        "b_updated": now,
    }


def _chunked[T](items: list[T], per_statement: int) -> Iterator[list[T]]:
    for index in range(0, len(items), per_statement):
        yield items[index : index + per_statement]
