"""Write-family statement builders for ``DatabaseStorage`` — write, edit, mkdir.

Plan-then-execute, mirroring the memory backend's stage-against-a-copy:
one ``path IN`` select fetches committed state for the batch's targets
and ancestors, a pure staging pass replays the POSIX parent/site gates
against committed-plus-staged state and accumulates classified per-entry
errors, and only an error-free plan executes — a failed batch runs no
mutation statement at all. The staging half lives in ``staging.py``
(``WritePlan`` and ``StagedEntry``); this module owns the read that seeds
it and the execution that drains it. Execution is a handful of bulk Core
statements in pinned order: entry inserts layered parents-before-children
(chunked by the dialect's parameter budget), guarded material updates
with a verification read, content delete-then-insert, and unconditional
parent bumps. Every function takes the op's live ``AsyncSession`` and
never begins or commits — the protocol method in ``backend.py`` owns its
one transaction.

Concurrent create arbitration follows the dialect's declared mode:
``upsert`` rides ``ON CONFLICT`` on the ``(parent_id, name)`` index,
``catch_retry`` wraps the bulk insert in a savepoint and resolves each
conflicting row individually. Revisions are per-entry monotone values —
creation mints 1, every material write adds exactly one, and a parent
bump adds one, all against the row's own current value. There is no
per-mount counter, and no two entries' revisions are comparable.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

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
    trash_filters,
)
from vfs.storage.backends.database.dialects import chunked
from vfs.storage.backends.database.reads import CONTENT_KINDS
from vfs.storage.backends.database.staging import StagedEntry, WritePlan
from vfs.storage.replace import replace

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any

    from sqlalchemy import Table
    from sqlalchemy.engine import RowMapping
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models.rows import VFSTables
    from vfs.paths import Path
    from vfs.storage.backends.database.dialects import DialectProfile
    from vfs.storage.replace import EditOperation

# Columns an overwrite clobbers when arbitration lands on a rival's row:
# identity stays, revision increments SQL-side, material state is ours.
_CLOBBER_COLUMNS: Final[tuple[str, ...]] = (
    "kind",
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


# ---------------------------------------------------------------------------
# Write-family builders
# ---------------------------------------------------------------------------


async def write_rows(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    parameter_budget: int,
    membership: int,
    *,
    entries: list[Entry],
    overwrite: bool,
    parents: bool,
    user_id: str | None,
) -> Result:
    committed = await _fetch_committed(session, tables, membership, {entry.path for entry in entries})
    plan = WritePlan(committed, user_id=user_id, budget=profile.key_byte_budget)
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
    return await _finish(session, tables, profile, parameter_budget, membership, plan, op="write", overwrite=overwrite)


async def mkdir_rows(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    parameter_budget: int,
    membership: int,
    *,
    path: Path,
    parents: bool,
    exist_ok: bool,
    user_id: str | None,
) -> Result:
    committed = await _fetch_committed(session, tables, membership, {path})
    plan = WritePlan(committed, user_id=user_id, budget=profile.key_byte_budget)
    if not plan.outside_trash(path):
        return Result(ops=("mkdir",), errors=plan.errors)
    occupant = plan.kind_of(path)
    if occupant is not None:
        if exist_ok and occupant == "directory":
            plan.pending.append((path, "unchanged"))
            return await _finish(
                session, tables, profile, parameter_budget, membership, plan, op="mkdir", overwrite=False
            )
        return Result(ops=("mkdir",), errors=[classified(VFSErrorKind.exists, f"Already exists: {path}", path)])
    if not plan.within_budget(path) or not plan.parent_gate(path, parents=parents, target=path):
        return Result(ops=("mkdir",), errors=plan.errors)
    minted = plan.mint_chain(path)
    plan.stage_create(path, kind="directory")
    plan.pending.extend((p, "created") for p in (*minted, path))
    return await _finish(session, tables, profile, parameter_budget, membership, plan, op="mkdir", overwrite=False)


async def edit_rows(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    parameter_budget: int,
    membership: int,
    *,
    edits: list[EditOperation],
    targets: Sequence[Path],
    user_id: str | None,
) -> Result:
    committed = await _fetch_committed(session, tables, membership, set(targets), with_content=True)
    misses = [t for t in dict.fromkeys(targets) if str(t) not in committed]
    miss_errors = dict(zip(misses, await classify_misses(session, tables.entry, misses, membership), strict=True))
    plan = WritePlan(committed, user_id=user_id, budget=profile.key_byte_budget)
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
    return await _finish(session, tables, profile, parameter_budget, membership, plan, op="edit", overwrite=True)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _fetch_committed(
    session: AsyncSession,
    tables: VFSTables,
    membership: int,
    targets: set[Path],
    *,
    with_content: bool = False,
) -> dict[str, RowMapping]:
    """Chunked ``path IN`` selects for the batch: targets, ancestors, the root."""
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
    committed: dict[str, RowMapping] = {}
    for chunk in chunked(sorted(paths), membership):
        stmt = select(*columns).select_from(source).where(entry.c.path.in_(chunk), *trash_filters(entry))
        committed.update({mapping["path"]: mapping for mapping in (await session.execute(stmt)).mappings()})
    return committed


async def _finish(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    parameter_budget: int,
    membership: int,
    plan: WritePlan,
    *,
    op: str,
    overwrite: bool,
) -> Result:
    """Execute an error-free plan and assemble the batch's observations."""
    if plan.errors:
        return Result(ops=(op,), errors=plan.errors)
    late = await _apply(session, tables, profile, parameter_budget, membership, plan, overwrite=overwrite)
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
    membership: int,
    plan: WritePlan,
    *,
    overwrite: bool,
) -> list[ResultError]:
    """Run the pinned statement sequence; a non-empty return fails the batch."""
    if not plan.staged and not plan.bumps:
        return []
    now = datetime.now(UTC)
    creates = [s for s in plan.staged.values() if s.created]
    errors = await _insert_creates(
        session, tables.entry, profile, parameter_budget, membership, creates, plan, overwrite=overwrite, now=now
    )
    if errors:
        return errors
    # Arbitration may convert a create into a clobbering update of the
    # rival's row, so the update set is collected only after inserts ran.
    updates = [s for s in plan.staged.values() if not s.created]
    errors = await _update_materials(session, tables.entry, membership, updates, user_id=plan.user_id, now=now)
    if errors:
        return errors
    await _replace_content(session, tables.content, membership, list(plan.staged.values()))
    await _bump_parents(session, tables.entry, membership, plan)
    return []


async def _insert_creates(
    session: AsyncSession,
    entry: Table,
    profile: DialectProfile,
    parameter_budget: int,
    membership: int,
    creates: list[StagedEntry],
    plan: WritePlan,
    *,
    overwrite: bool,
    now: datetime,
) -> list[ResultError]:
    """Bulk-insert created rows, parents before children, arbitrating conflicts."""
    if not creates:
        return []
    by_depth: dict[int, list[StagedEntry]] = {}
    for staged in creates:
        by_depth.setdefault(str(staged.path).count("/"), []).append(staged)
    for depth in sorted(by_depth):
        layer = by_depth[depth]
        rows = [_entry_values(s, _parent_id(plan, s), plan.user_id, now) for s in layer]
        per_statement = max(1, parameter_budget // len(rows[0]))
        if profile.arbitration == "upsert":
            errors = await _upsert_layer(session, entry, profile, layer, rows, per_statement, overwrite=overwrite)
        else:
            errors = await _catch_retry_layer(
                session, entry, layer, rows, per_statement, membership, overwrite=overwrite
            )
        if errors:
            # Fail fast: children of an unresolved parent cannot be wired.
            return errors
    return []


async def _upsert_layer(
    session: AsyncSession,
    entry: Table,
    profile: DialectProfile,
    layer: list[StagedEntry],
    rows: list[dict[str, Any]],
    per_statement: int,
    *,
    overwrite: bool,
) -> list[ResultError]:
    """``ON CONFLICT`` arbitration on the ``(parent_id, name)`` index.

    Directory creates never clobber (``DO NOTHING``); file creates clobber
    a non-directory rival under ``overwrite``. RETURNING carries the final
    revision, so winners and clobberers stamp theirs without a read-back.
    A row missing from RETURNING lost arbitration and classifies — a
    definite outcome, never retried.
    """
    constructor = _upsert_constructor(profile)
    pairs = list(zip(layer, rows, strict=True))
    directories = [(s, r) for s, r in pairs if s.kind == "directory"]
    files = [(s, r) for s, r in pairs if s.kind != "directory"]
    errors: list[ResultError] = []
    for group, clobber in ((directories, False), (files, overwrite)):
        for chunk in chunked(group, per_statement):
            stmt = constructor(entry).values([r for _, r in chunk])
            if clobber:
                # A clobbered rival's revision increments off the target row,
                # not the excluded value, keeping its history monotone.
                set_: dict[str, Any] = {column: stmt.excluded[column] for column in _CLOBBER_COLUMNS}
                set_["revision"] = entry.c.revision + 1
                stmt = stmt.on_conflict_do_update(
                    index_elements=["parent_id", "name"],
                    set_=set_,
                    where=entry.c.kind != "directory",
                )
            else:
                stmt = stmt.on_conflict_do_nothing(index_elements=["parent_id", "name"])
            result = await session.execute(stmt.returning(entry.c.id, entry.c.path, entry.c.revision))
            returned = {mapping["path"]: mapping for mapping in result.mappings()}
            for staged, _ in chunk:
                won = returned.get(str(staged.path))
                if won is not None:
                    staged.entry_id = won["id"]
                    staged.revision = won["revision"]
                elif clobber:
                    errors.append(classified(VFSErrorKind.wrong_kind, f"Is a directory: {staged.path}", staged.path))
                else:
                    errors.append(classified(VFSErrorKind.exists, f"Already exists: {staged.path}", staged.path))
    return errors


async def _catch_retry_layer(
    session: AsyncSession,
    entry: Table,
    layer: list[StagedEntry],
    rows: list[dict[str, Any]],
    per_statement: int,
    membership: int,
    *,
    overwrite: bool,
) -> list[ResultError]:
    """Portable arbitration: savepointed bulk insert, per-row resolution on conflict.

    Engines whose live dialect declares multirow ``VALUES`` support take
    the chunked ``INSERT ... VALUES (...), (...) RETURNING`` fast path;
    the rest (Oracle among them) take driver executemany, and the ids
    come back through a chunked ``path IN`` read of the layer's rows.
    """
    multirow = session.get_bind().dialect.supports_multivalues_insert
    returned: dict[str, int] = {}
    try:
        async with session.begin_nested():
            if multirow:
                for chunk in chunked(rows, per_statement):
                    result = await session.execute(insert(entry).values(chunk).returning(entry.c.id, entry.c.path))
                    returned.update({mapping["path"]: mapping["id"] for mapping in result.mappings()})
            else:
                await session.execute(insert(entry), rows)
    except IntegrityError:
        return await _resolve_rows(session, entry, layer, rows, overwrite=overwrite)
    if not multirow:
        for chunk in chunked(sorted(row["path"] for row in rows), membership):
            result = await session.execute(select(entry.c.id, entry.c.path).where(entry.c.path.in_(chunk)))
            returned.update({mapping["path"]: mapping["id"] for mapping in result.mappings()})
    for staged in layer:
        staged.entry_id = returned[str(staged.path)]
    return []


async def _resolve_rows(
    session: AsyncSession,
    entry: Table,
    layer: list[StagedEntry],
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
    membership: int,
    updates: list[StagedEntry],
    *,
    user_id: str | None,
    now: datetime,
) -> list[ResultError]:
    """Material updates with the revision guard, verified by one read-back.

    The guarded arm writes ``base + 1`` under ``WHERE revision = base``;
    the guard's zero-rowcount arm is unreachable on SQLite (single writer)
    and on Postgres at REPEATABLE READ (rivals surface as 40001); it is
    load-bearing at READ COMMITTED — topology verbs, the generic-dialect
    floor — where a lost update is otherwise silent. The unguarded arm
    (arbitration clobbers) increments SQL-side, last-writer-wins by
    design. The read-back attributes conflicts portably instead of
    trusting per-driver executemany rowcounts: a guarded row must show
    exactly ``base + 1``; an unguarded row takes the observed value as
    truth and conflicts only if it vanished.
    """
    if not updates:
        return []
    guarded = [s for s in updates if s.base_revision is not None]
    unguarded = [s for s in updates if s.base_revision is None]
    material = {
        "kind": bindparam("b_kind"),
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
            .values(**material, revision=bindparam("b_rev"))
        )
        params = [_update_params(s, user_id, now) | {"b_base": s.base_revision, "b_rev": s.revision} for s in guarded]
        await session.execute(stmt, params)
    if unguarded:
        stmt = update(entry).where(entry.c.id == bindparam("b_id")).values(**material, revision=entry.c.revision + 1)
        await session.execute(stmt, [_update_params(s, user_id, now) for s in unguarded])
    actual: dict[int, int] = {}
    for chunk in chunked([s.entry_id for s in updates], membership):
        check = await session.execute(select(entry.c.id, entry.c.revision).where(entry.c.id.in_(chunk)))
        actual.update({row.id: row.revision for row in check})
    errors: list[ResultError] = []
    for staged in updates:
        observed = actual.get(staged.entry_id)
        if observed is None or (staged.base_revision is not None and observed != staged.revision):
            message = f"Concurrent modification: {staged.path}"
            errors.append(classified(VFSErrorKind.conflict, message, staged.path, target=staged.path))
        elif staged.base_revision is None:
            staged.revision = observed
    return errors


async def _replace_content(session: AsyncSession, content: Table, membership: int, staged: list[StagedEntry]) -> None:
    """Delete-then-insert the batch's content rows — portable, idempotent.

    The insert is driver executemany — SQLAlchemy batches it by its own
    parameter budget; only the membership delete needs chunking here.
    """
    bearing = [s for s in staged if s.content is not None and s.kind in CONTENT_KINDS]
    if not bearing:
        return
    for chunk in chunked([s.entry_id for s in bearing], membership):
        await session.execute(delete(content).where(content.c.entry_id.in_(chunk)))
    await session.execute(insert(content), [{"entry_id": s.entry_id, "content": s.content} for s in bearing])


async def _bump_parents(session: AsyncSession, entry: Table, membership: int, plan: WritePlan) -> None:
    """One SQL-side increment for every bumped directory, read back only on need.

    ``revision = revision + 1`` composes where a client-assigned value would
    overwrite a concurrent rival's bump. The read-back runs only when an
    "unchanged" pending row was bumped by a sibling in this batch — its
    observation must equal a post-commit stat of its path.
    """
    if not plan.bumps:
        return
    bump_ids = [plan.committed[path]["id"] for path in sorted(plan.bumps)]
    for chunk in chunked(bump_ids, membership):
        await session.execute(update(entry).where(entry.c.id.in_(chunk)).values(revision=entry.c.revision + 1))
    needed = {str(path) for path, _ in plan.pending if path not in plan.staged and str(path) in plan.bumps}
    if not needed:
        return
    ids = [plan.committed[path]["id"] for path in sorted(needed)]
    plan.bump_revisions = {}
    for chunk in chunked(ids, membership):
        result = await session.execute(select(entry.c.path, entry.c.revision).where(entry.c.id.in_(chunk)))
        plan.bump_revisions.update({row.path: row.revision for row in result})


def _upsert_constructor(profile: DialectProfile) -> Any:
    """The dialect's ``ON CONFLICT`` insert — only upsert-arbitration engines get here."""
    return sqlite_insert if profile.name == "sqlite" else pg_insert


def _parent_id(plan: WritePlan, staged: StagedEntry) -> int:
    parent = plan.staged.get(staged.parent)
    if parent is not None and parent.entry_id is not None:
        return parent.entry_id
    return plan.committed[str(staged.parent)]["id"]


def _entry_values(staged: StagedEntry, parent_id: int, user_id: str | None, now: datetime) -> dict[str, Any]:
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


def _update_params(staged: StagedEntry, user_id: str | None, now: datetime) -> dict[str, Any]:
    return {
        "b_id": staged.entry_id,
        "b_kind": staged.kind,
        "b_hash": staged.content_hash,
        "b_mime": staged.mime_type,
        "b_ext": staged.ext,
        "b_lines": staged.lines,
        "b_size": staged.size_bytes,
        "b_owner": user_id,
        "b_updated": now,
    }
