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
attributed from their own statements, content delete-then-insert, and
unconditional parent bumps. Every function takes the op's live ``AsyncSession`` and
never begins or commits — the protocol method in ``backend.py`` owns its
one transaction.

Concurrent create arbitration follows the dialect's declared mode:
``upsert`` rides ``ON CONFLICT`` on the ``(parent_id, name)`` index,
``catch_retry`` inserts each chunk under its own savepoint and re-runs
only a conflicted chunk row-by-row. Versions are per-entry monotone values —
creation mints 1, every material write adds exactly one, and a parent
bump adds one, all against the row's own current value. There is no
per-mount counter, and no two entries' versions are comparable.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final, cast

from sqlalchemy import bindparam, column, delete, insert, select, update, values
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError

from vfs.models import CONTENT_KINDS, Entry, Observation
from vfs.results import Result, ResultError, VFSErrorKind, already_exists, classified, wrong_kind
from vfs.storage.backends.database.descent import ancestor_chain, classify_misses
from vfs.storage.backends.database.dialects import chunked, rows_per_statement
from vfs.storage.backends.database.staging import StagedEntry, WritePlan
from vfs.storage.editing import edited_entry

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from sqlalchemy import Column, ColumnElement, FromClause, Table, Update
    from sqlalchemy.dialects.postgresql import Insert as PostgresInsert
    from sqlalchemy.dialects.sqlite import Insert as SQLiteInsert
    from sqlalchemy.engine import CursorResult, RowMapping
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models.rows import VFSTables
    from vfs.paths import Path
    from vfs.storage.backends.database.dialects import DialectProfile
    from vfs.storage.replace import EditOperation

# Columns an overwrite clobbers when arbitration lands on a rival's row:
# identity stays, version increments SQL-side, material state is ours.
_CLOBBER_COLUMNS: Final[tuple[str, ...]] = (
    "kind",
    "content_hash",
    "mime_type",
    "ext",
    "lines",
    "size_bytes",
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
    membership_budget: int,
    *,
    entries: list[Entry],
    overwrite: bool,
    parents: bool,
    user_id: str | None,
) -> Result:
    """Adjudicate and apply a batch of entry writes as a set.

    One snapshot read seeds the plan, then every entry runs the gate
    ladder — key-byte budget, POSIX parent rule, site check — against
    committed-plus-staged state, so entries may rely on parents minted
    earlier in the same batch. Directories route through ``put_dir``
    (an existing directory is "unchanged", a file at the site is
    ``wrong_kind``); files route through ``put_file`` (a directory at
    the site is ``wrong_kind``; an occupied site needs ``overwrite``).
    Any error fails the whole batch before a statement runs.
    """
    committed = await _fetch_committed(session, tables, membership_budget, {entry.path for entry in entries})
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
    return await _finish(
        session, tables, profile, parameter_budget, membership_budget, plan, op="write", overwrite=overwrite
    )


async def mkdir_rows(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    parameter_budget: int,
    membership_budget: int,
    *,
    path: Path,
    parents: bool,
    exist_ok: bool,
    user_id: str | None,
) -> Result:
    """Create one directory with POSIX mkdir semantics.

    An occupied site is ``exists`` whatever its kind — ``ENOTDIR`` is a
    path-prefix error, never the target's — and ``exist_ok`` forgives a
    directory occupant only, matching ``pathlib.Path.mkdir``. The forgiven
    arm still runs ``_finish`` so the observation equals a post-commit
    stat. With ``parents``, the minted ancestor chain reports alongside
    the target, shallowest first.
    """
    committed = await _fetch_committed(session, tables, membership_budget, {path})
    plan = WritePlan(committed, user_id=user_id, budget=profile.key_byte_budget)
    occupant = plan.kind_of(path)
    if occupant is not None:
        if exist_ok and occupant == "directory":
            plan.pending.append((path, "unchanged"))
            return await _finish(
                session, tables, profile, parameter_budget, membership_budget, plan, op="mkdir", overwrite=False
            )
        return Result(ops=("mkdir",), errors=[already_exists(path)])
    if not plan.within_budget(path) or not plan.parent_gate(path, parents=parents, target=path):
        return Result(ops=("mkdir",), errors=plan.errors)
    minted = plan.mint_chain(path)
    plan.stage_create(path, kind="directory")
    plan.pending.extend((p, "created") for p in (*minted, path))
    return await _finish(
        session, tables, profile, parameter_budget, membership_budget, plan, op="mkdir", overwrite=False
    )


async def edit_rows(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    parameter_budget: int,
    membership_budget: int,
    *,
    edits: list[EditOperation],
    targets: Sequence[Path],
    user_id: str | None,
) -> Result:
    """Apply the same edit sequence to every target's content.

    The snapshot read joins content; each target reads its current state
    through the staged overlay — a repeated target edits its own staged
    output — and runs the shared edit semantics (``edited_entry``): the
    editable gate, sequential replacement, ``Entry`` revalidation.
    Misses are classified by a descent probe (``not_found`` vs
    ``wrong_kind``); a failed or invalid edit fails the whole batch.
    Every update is version-guarded — edits never create and never
    clobber, so a concurrent rival surfaces as ``conflict``.
    """
    committed = await _fetch_committed(session, tables, membership_budget, set(targets), with_content=True)
    misses = [t for t in dict.fromkeys(targets) if str(t) not in committed]
    miss_errors = dict(
        zip(misses, await classify_misses(session, tables.entry, misses, membership_budget), strict=True)
    )
    plan = WritePlan(committed, user_id=user_id, budget=profile.key_byte_budget)
    for target in targets:
        row = committed.get(str(target))
        if row is None:
            plan.errors.append(miss_errors[target])
            continue
        kind, current = plan.material_of(target)
        edited = edited_entry(target, kind=kind, content=current, edits=edits)
        if isinstance(edited, ResultError):
            plan.errors.append(edited)
            continue
        plan.stage_update(
            target,
            kind=edited.kind,
            content=edited.content,
            content_hash=edited.content_hash,
            size_bytes=edited.size_bytes,
            lines=edited.lines,
            ext=row["ext"],
            mime_type=row["mime_type"],
        )
        plan.pending.append((target, "updated"))
    return await _finish(session, tables, profile, parameter_budget, membership_budget, plan, op="edit", overwrite=True)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _fetch_committed(
    session: AsyncSession,
    tables: VFSTables,
    membership_budget: int,
    targets: set[Path],
    *,
    with_content: bool = False,
) -> dict[str, RowMapping]:
    """Chunked ``path IN`` selects for the batch: targets, ancestors, the root."""
    entry = tables.entry
    paths = {str(t) for t in targets} | {str(a) for t in targets for a in ancestor_chain(t)} | {"/"}
    columns: list[Column[object]] = [
        entry.c.entry_id,
        entry.c.path,
        entry.c.kind,
        entry.c.version,
        entry.c.ext,
        entry.c.mime_type,
    ]
    source: FromClause = entry
    if with_content:
        columns.append(tables.content.c.content)
        source = tables.content_joined()
    committed: dict[str, RowMapping] = {}
    for chunk in chunked(sorted(paths), membership_budget):
        stmt = select(*columns).select_from(source).where(entry.c.path.in_(chunk))
        committed.update({mapping["path"]: mapping for mapping in (await session.execute(stmt)).mappings()})
    return committed


async def _finish(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    parameter_budget: int,
    membership_budget: int,
    plan: WritePlan,
    *,
    op: str,
    overwrite: bool,
) -> Result:
    """Execute an error-free plan and assemble the batch's observations."""
    if plan.errors:
        return Result(ops=(op,), errors=plan.errors)
    late = await _apply(session, tables, profile, parameter_budget, membership_budget, plan, overwrite=overwrite)
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
                    size_bytes=staged.size_bytes,
                    version=staged.version,
                    status=status,
                )
            )
        else:
            # A later entry may have bumped this unchanged row; the
            # observation must equal a post-commit stat of its path.
            row = plan.committed[str(path)]
            version = plan.bump_versions.get(str(path), row["version"])
            rows.append(Observation(path=path, kind=row["kind"], version=version, status=status))
    return Result(ops=(op,), observations=rows)


async def _apply(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    parameter_budget: int,
    membership_budget: int,
    plan: WritePlan,
    *,
    overwrite: bool,
) -> list[ResultError]:
    """Run the pinned statement sequence; a non-empty return fails the batch."""
    if not plan.staged and not plan.bumps:
        return []
    now = datetime.now(UTC)
    creates = [s for s in plan.staged.values() if s.persistence == "insert"]
    if errors := await _insert_creates(
        session, tables.entry, profile, parameter_budget, creates, plan, overwrite=overwrite, now=now
    ):
        return errors
    # After the insert pass on purpose: arbitration may re-route a losing
    # create to "absorb", which must be picked up by this pass.
    updates = [s for s in plan.staged.values() if s.persistence != "insert"]
    if errors := await _update_materials(
        session, tables.entry, profile, parameter_budget, membership_budget, updates, user_id=plan.user_id, now=now
    ):
        return errors
    await _replace_content(session, tables.content, membership_budget, list(plan.staged.values()))
    await _bump_parents(session, tables.entry, membership_budget, plan)
    return []


async def _insert_creates(
    session: AsyncSession,
    entry: Table,
    profile: DialectProfile,
    parameter_budget: int,
    creates: list[StagedEntry],
    plan: WritePlan,
    *,
    overwrite: bool,
    now: datetime,
) -> list[ResultError]:
    """Bulk-insert created rows, parents before children, arbitrating conflicts.

    Identity is minted at staging, so rows are fully wired client-side;
    the layers exist to learn each depth's arbitration outcome before its
    children commit to a parent that may have lost.
    """
    if not creates:
        return []
    by_depth: dict[int, list[StagedEntry]] = {}
    for staged in creates:
        by_depth.setdefault(staged.path.depth, []).append(staged)
    for depth in sorted(by_depth):
        layer = by_depth[depth]
        rows = [_entry_values(s, plan.parent_id_of(s), plan.user_id, now) for s in layer]
        per_statement = rows_per_statement(parameter_budget, rows)
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
    layer: list[StagedEntry],
    rows: list[dict[str, object]],
    per_statement: int,
    *,
    overwrite: bool,
) -> list[ResultError]:
    """``ON CONFLICT`` arbitration on the ``(parent_id, name)`` index.

    Directory creates never clobber (``DO NOTHING``); file creates clobber
    a non-directory rival under ``overwrite``. RETURNING carries the
    surviving identity and final version: a clobber lands on the rival's
    row, which keeps its ``entry_id``, so the staged entry adopts it —
    its content rows must wire to the row that exists. A row missing
    from RETURNING lost arbitration and classifies — a definite outcome,
    never retried.
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
                # A clobbered rival's version increments off the target row,
                # not the excluded value, keeping its history monotone.
                set_: dict[str, ColumnElement[Any]] = {column: stmt.excluded[column] for column in _CLOBBER_COLUMNS}
                set_["version"] = entry.c.version + 1
                stmt = stmt.on_conflict_do_update(
                    index_elements=["parent_id", "name"],
                    set_=set_,
                    where=entry.c.kind != "directory",
                )
            else:
                stmt = stmt.on_conflict_do_nothing(index_elements=["parent_id", "name"])
            result = await session.execute(stmt.returning(entry.c.entry_id, entry.c.path, entry.c.version))
            returned = {mapping["path"]: mapping for mapping in result.mappings()}
            for staged, _ in chunk:
                won = returned.get(str(staged.path))
                if won is not None:
                    staged.entry_id = won["entry_id"]
                    staged.version = won["version"]
                elif clobber:
                    errors.append(wrong_kind("directory", staged.path))
                else:
                    errors.append(already_exists(staged.path))
    return errors


async def _catch_retry_layer(
    session: AsyncSession,
    entry: Table,
    layer: list[StagedEntry],
    rows: list[dict[str, object]],
    per_statement: int,
    *,
    overwrite: bool,
) -> list[ResultError]:
    """Portable arbitration: savepoint per chunk, conflicted chunks re-run row-wise.

    Engines whose live dialect declares multirow ``VALUES`` support the
    ``INSERT ... VALUES (...), (...)`` fast path; the rest (Oracle among
    them) take driver executemany. Each budget-sized chunk inserts under
    its own savepoint, so a conflict rolls back and re-drives only its
    chunk — O(conflicted chunks), never O(layer). Identity is minted at
    staging, so a clean insert learns nothing back.
    """
    multirow = session.get_bind().dialect.supports_multivalues_insert
    errors: list[ResultError] = []
    for chunk in chunked(list(zip(layer, rows, strict=True)), per_statement):
        chunk_rows = [values for _, values in chunk]
        try:
            async with session.begin_nested():
                if multirow:
                    await session.execute(insert(entry).values(chunk_rows))
                else:
                    await session.execute(insert(entry), chunk_rows)
        except IntegrityError:
            resolved = await _resolve_rows(session, entry, [s for s, _ in chunk], chunk_rows, overwrite=overwrite)
            errors.extend(resolved)
    return errors


async def _resolve_rows(
    session: AsyncSession,
    entry: Table,
    layer: list[StagedEntry],
    rows: list[dict[str, object]],
    *,
    overwrite: bool,
) -> list[ResultError]:
    """Re-run a conflicted chunk row-at-a-time, each insert in its own savepoint."""
    errors: list[ResultError] = []
    for staged, row_values in zip(layer, rows, strict=True):
        try:
            async with session.begin_nested():
                await session.execute(insert(entry).values(**row_values))
            continue
        except IntegrityError:
            pass
        occupant_query = select(entry.c.entry_id, entry.c.kind).where(
            entry.c.parent_id == row_values["parent_id"], entry.c.name == row_values["name"]
        )
        occupant = (await session.execute(occupant_query)).one_or_none()
        if occupant is None:
            errors.append(
                classified(VFSErrorKind.conflict, f"Concurrent write lost arbitration: {staged.path}", staged.path)
            )
        elif staged.kind != "directory" and overwrite and occupant.kind != "directory":
            # The rival's row absorbs our write: an unguarded clobbering update.
            staged.absorb(occupant.entry_id)
        elif staged.kind != "directory" and overwrite:
            errors.append(wrong_kind("directory", staged.path))
        else:
            errors.append(already_exists(staged.path))
    return errors


async def _update_materials(
    session: AsyncSession,
    entry: Table,
    profile: DialectProfile,
    parameter_budget: int,
    membership_budget: int,
    updates: list[StagedEntry],
    *,
    user_id: str | None,
    now: datetime,
) -> list[ResultError]:
    """Material updates with the version guard, attributed from the statement.

    The guarded arm writes ``base + 1`` under ``WHERE version = base`` and
    learns which rows its own statement matched — never from a re-read of
    the post-image, which cannot tell our one increment from a rival's at
    READ COMMITTED. The ladder, selected from what the live dialect
    models: a set-based VALUES join whose RETURNING set is the success
    set; an executemany whose sane aggregate rowcount proves every guard
    matched (each statement matches at most one row via the unique
    ``entry_id`` index — the upstream staging layer stages one row per
    entry_id, never duplicates within a batch),
    rolled back to a savepoint and re-driven row-by-row on mismatch;
    per-row execution attributed by each statement's own rowcount; or a
    classified refusal — an unverifiable guarded write never proceeds.
    The unguarded arm (arbitration clobbers) increments SQL-side,
    last-writer-wins by design; it only *learns* its assigned versions —
    from RETURNING, or a select of its own ids — and a vanished row
    classifies ``conflict``.
    """
    if not updates:
        return []
    guarded = [s for s in updates if s.persistence == "update"]
    unguarded = [s for s in updates if s.persistence == "absorb"]
    dialect = session.get_bind().dialect
    set_based = profile.values_join and dialect.update_returning and dialect.update_returning_multifrom
    errors: list[ResultError] = []
    if guarded:
        if set_based:
            matched = await _values_update(
                session, entry, parameter_budget, membership_budget, guarded, user_id=user_id, now=now, guard=True
            )
            errors.extend(_conflict(s) for s in guarded if s.entry_id not in matched)
        elif dialect.supports_sane_multi_rowcount:
            errors.extend(await _guarded_by_aggregate(session, entry, guarded, user_id=user_id, now=now))
        elif dialect.supports_sane_rowcount:
            errors.extend(await _guarded_by_rowcount(session, entry, guarded, user_id=user_id, now=now))
        else:
            message = f"Guarded updates cannot be verified on {profile.name}: no UPDATE RETURNING, no sane rowcount"
            return [ResultError(kind=VFSErrorKind.unsupported, message=message)]
    if unguarded:
        if set_based:
            learned = await _values_update(
                session, entry, parameter_budget, membership_budget, unguarded, user_id=user_id, now=now, guard=False
            )
        else:
            material = {name: bindparam(f"b_{name}") for name in _CLOBBER_COLUMNS}
            stmt = (
                update(entry)
                .where(entry.c.entry_id == bindparam("b_id"))
                .values(**material, version=entry.c.version + 1)
            )
            await session.execute(stmt, [_update_params(s, user_id, now) for s in unguarded])
            learned = {}
            for chunk in chunked([s.entry_id for s in unguarded], membership_budget):
                found = await session.execute(
                    select(entry.c.entry_id, entry.c.version).where(entry.c.entry_id.in_(chunk))
                )
                learned.update({row.entry_id: row.version for row in found})
        for staged in unguarded:
            version = learned.get(staged.entry_id)
            if version is None:
                errors.append(_conflict(staged))
            else:
                staged.version = version
    return errors


async def _values_update(
    session: AsyncSession,
    entry: Table,
    parameter_budget: int,
    membership_budget: int,
    staged: list[StagedEntry],
    *,
    user_id: str | None,
    now: datetime,
    guard: bool,
) -> dict[str, int]:
    """Set-based material update over a VALUES join, RETURNING what it matched.

    One tuple per staged row joins the entry table on ``entry_id`` (and,
    guarded, on ``version = base``); the returned ``entry_id`` set is
    exactly the rows this statement touched. Chunked by the tighter of
    the membership budget and the per-tuple bind cost, so a 10,000-entry
    batch stays batch-native and bounded on every engine.
    """
    rows = []
    for entry_row in staged:
        material = _material_values(entry_row, user_id, now)
        ordered = tuple(material[name] for name in _CLOBBER_COLUMNS)
        rows.append((entry_row.entry_id, entry_row.base_version, entry_row.version, *ordered))
    width = len(_CLOBBER_COLUMNS) + 3
    per_statement = max(1, min(membership_budget, parameter_budget // width))
    matched: dict[str, int] = {}
    for chunk in chunked(rows, per_statement):
        incoming = values(
            column("v_id", entry.c.entry_id.type),
            column("v_base", entry.c.version.type),
            column("v_ver", entry.c.version.type),
            *(column(f"v_{name}", entry.c[name].type) for name in _CLOBBER_COLUMNS),
            name="incoming",
        ).data(list(chunk))
        set_: dict[str, Any] = {name: incoming.c[f"v_{name}"] for name in _CLOBBER_COLUMNS}
        where = [entry.c.entry_id == incoming.c.v_id]
        if guard:
            set_["version"] = incoming.c.v_ver
            where.append(entry.c.version == incoming.c.v_base)
        else:
            set_["version"] = entry.c.version + 1
        stmt = update(entry).where(*where).values(**set_).returning(entry.c.entry_id, entry.c.version)
        result = await session.execute(stmt)
        matched.update({mapping["entry_id"]: mapping["version"] for mapping in result.mappings()})
    return matched


async def _guarded_by_aggregate(
    session: AsyncSession,
    entry: Table,
    guarded: list[StagedEntry],
    *,
    user_id: str | None,
    now: datetime,
) -> list[ResultError]:
    """Executemany fast path: an aggregate rowcount of N proves N guards matched.

    On mismatch the savepoint rolls back — guarded updates are not
    idempotent, so attribution must not re-run them over applied state —
    and the per-row floor re-drives for exact blame.
    """
    params = [_guarded_params(s, user_id, now) for s in guarded]
    nested = await session.begin_nested()
    result = cast("CursorResult[Any]", await session.execute(_guarded_stmt(entry), params))
    if result.rowcount == len(params):
        await nested.commit()
        return []
    await nested.rollback()
    return await _guarded_by_rowcount(session, entry, guarded, user_id=user_id, now=now)


async def _guarded_by_rowcount(
    session: AsyncSession,
    entry: Table,
    guarded: list[StagedEntry],
    *,
    user_id: str | None,
    now: datetime,
) -> list[ResultError]:
    """The per-row floor: each statement's own rowcount is the evidence.

    SQLAlchemy's own choice when a version guard must be verified without
    RETURNING — one row per statement, bounded trivially.
    """
    stmt = _guarded_stmt(entry)
    errors: list[ResultError] = []
    for staged in guarded:
        result = cast("CursorResult[Any]", await session.execute(stmt, _guarded_params(staged, user_id, now)))
        if result.rowcount == 0:
            errors.append(_conflict(staged))
    return errors


def _guarded_stmt(entry: Table) -> Update:
    material = {name: bindparam(f"b_{name}") for name in _CLOBBER_COLUMNS}
    return (
        update(entry)
        .where(entry.c.entry_id == bindparam("b_id"), entry.c.version == bindparam("b_base"))
        .values(**material, version=bindparam("b_ver"))
    )


def _guarded_params(staged: StagedEntry, user_id: str | None, now: datetime) -> dict[str, object]:
    return _update_params(staged, user_id, now) | {"b_base": staged.base_version, "b_ver": staged.version}


def _conflict(staged: StagedEntry) -> ResultError:
    message = f"Concurrent modification: {staged.path}"
    return classified(VFSErrorKind.conflict, message, staged.path, target=staged.path)


async def _replace_content(
    session: AsyncSession, content: Table, membership_budget: int, staged: list[StagedEntry]
) -> None:
    """Delete-then-insert the batch's content rows — portable, idempotent.

    The insert is driver executemany — SQLAlchemy batches it by its own
    parameter budget; only the membership-predicate delete chunks here.
    """
    bearing = [s for s in staged if s.content is not None and s.kind in CONTENT_KINDS]
    if not bearing:
        return
    for chunk in chunked([s.entry_id for s in bearing], membership_budget):
        await session.execute(delete(content).where(content.c.entry_id.in_(chunk)))
    await session.execute(insert(content), [{"entry_id": s.entry_id, "content": s.content} for s in bearing])


async def _bump_parents(session: AsyncSession, entry: Table, membership_budget: int, plan: WritePlan) -> None:
    """One SQL-side increment for every bumped directory, read back only on need.

    ``version = version + 1`` composes where a client-assigned value would
    overwrite a concurrent rival's bump. The read-back runs only when an
    "unchanged" pending row was bumped by a sibling in this batch — its
    observation must equal a post-commit stat of its path.
    """
    if not plan.bumps:
        return
    bump_ids = [plan.committed[path]["entry_id"] for path in sorted(plan.bumps)]
    for chunk in chunked(bump_ids, membership_budget):
        await session.execute(update(entry).where(entry.c.entry_id.in_(chunk)).values(version=entry.c.version + 1))
    needed = {str(path) for path, _ in plan.pending if path not in plan.staged and str(path) in plan.bumps}
    if not needed:
        return
    ids = [plan.committed[path]["entry_id"] for path in sorted(needed)]
    plan.bump_versions = {}
    for chunk in chunked(ids, membership_budget):
        result = await session.execute(select(entry.c.path, entry.c.version).where(entry.c.entry_id.in_(chunk)))
        plan.bump_versions.update({row.path: row.version for row in result})


def _upsert_constructor(profile: DialectProfile) -> Callable[[Table], SQLiteInsert | PostgresInsert]:
    """The dialect's ``ON CONFLICT`` insert — only upsert-arbitration engines get here."""
    return sqlite_insert if profile.name == "sqlite" else pg_insert


def _material_values(staged: StagedEntry, user_id: str | None, now: datetime) -> dict[str, object]:
    """The clobber-column values for *staged*; ownership follows the writer."""
    return {
        "kind": staged.kind,
        "content_hash": staged.content_hash,
        "mime_type": staged.mime_type,
        "ext": staged.ext,
        "lines": staged.lines,
        "size_bytes": staged.size_bytes,
        "owner_id": user_id,
        "updated_at": now,
    }


def _entry_values(staged: StagedEntry, parent_id: str, user_id: str | None, now: datetime) -> dict[str, object]:
    return {
        "entry_id": staged.entry_id,
        "parent_id": parent_id,
        "path": str(staged.path),
        "name": staged.path.name,
        "version": staged.version,
        "created_at": now,
    } | _material_values(staged, user_id, now)


def _update_params(staged: StagedEntry, user_id: str | None, now: datetime) -> dict[str, object]:
    material = _material_values(staged, user_id, now)
    return {"b_id": staged.entry_id} | {f"b_{column}": material[column] for column in _CLOBBER_COLUMNS}
