"""Write-family statement builders for ``DatabaseStorage`` — write, edit, mkdir.

Plan-then-execute — stage against a copy, commit only a clean plan:
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
guarded parent bumps — every bump proves its parent still lives at the
snapshot's address, so a create under a concurrently relocated or
destroyed directory aborts whole and redrives instead of committing a
torn path cache. Every function takes the op's live ``AsyncSession`` and
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
from vfs.storage.backends.database.descent import miss_errors, rows_by_path, targets_with_ancestors
from vfs.storage.backends.database.dialects import (
    StaleSnapshot,
    bulk_insert,
    chunked,
    rows_per_statement,
    statement_budget,
    supports_values_update,
)
from vfs.storage.backends.database.seams import seam
from vfs.storage.backends.database.segments import insert_postings
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
    "chunked",
    "encoded",
    "indexable",
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
    missing = await miss_errors(session, tables.entry, targets, committed, membership_budget)
    plan = WritePlan(committed, user_id=user_id, budget=profile.key_byte_budget)
    for target in targets:
        row = committed.get(str(target))
        if row is None:
            plan.errors.append(missing[target])
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
    """One bounded fetch seeds the plan: targets, ancestors, the root."""
    entry = tables.entry
    columns: list[Column[object]] = [
        entry.c.entry_id,
        entry.c.path,
        entry.c.kind,
        entry.c.version,
        entry.c.ext,
        entry.c.mime_type,
    ]
    source: FromClause | None = None
    if with_content:
        columns.append(tables.content.c.content)
        source = tables.content_joined()
    paths = targets_with_ancestors(targets)
    return await rows_by_path(session, entry, paths, columns, membership_budget, source=source)


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
    # The guard's window: snapshot read and staging behind us, no
    # mutation statement run yet. Tests stage rival commits here.
    await seam("write:before-apply")
    late = await _apply(session, tables, profile, parameter_budget, membership_budget, plan, overwrite=overwrite)
    if late:
        return Result(ops=(op,), errors=late)
    rows: list[Observation] = []
    for path, status in plan.pending:
        staged = plan.staged.get(path)
        if staged is not None:
            # An adopted row's create resolved to a standing equivalent.
            if staged.persistence == "adopt":
                status = "unchanged"
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
    if not plan.staged:
        return []
    now = datetime.now(UTC)
    creates = [s for s in plan.staged.values() if s.persistence == "insert"]
    minted = frozenset(staged.entry_id for staged in creates)
    if errors := await _insert_creates(
        session, tables.entry, profile, parameter_budget, creates, plan, overwrite=overwrite, now=now
    ):
        return errors
    # Segment postings ride beside fresh inserts only: a create that
    # adopted or clobbered a rival's row found its postings already true.
    fresh = [staged for staged in creates if staged.entry_id in minted]
    await insert_postings(session, tables.segments, [(staged.entry_id, str(staged.path)) for staged in fresh])
    # After the insert pass on purpose: arbitration may re-route a losing
    # create to "absorb", which must be picked up by this pass. "adopt"
    # rows stood down entirely — nothing left to write.
    updates = [s for s in plan.staged.values() if s.persistence in ("update", "absorb")]
    if errors := await _update_materials(
        session, tables.entry, profile, parameter_budget, membership_budget, updates, user_id=plan.user_id, now=now
    ):
        return errors
    await _replace_content(session, tables.content, membership_budget, list(plan.staged.values()), now)
    return await _bump_parents(session, tables.entry, profile, parameter_budget, membership_budget, plan)


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
    a non-directory rival under ``overwrite`` — and only a rival whose
    stored path equals the requested path: an incoherent row (a legacy
    torn ghost squatting the address) is never adopted. RETURNING
    carries the surviving identity and final version: a clobber lands on
    the rival's row, which keeps its ``entry_id``, so the staged entry
    adopts it — its content rows must wire to the row that exists. A row
    missing from RETURNING lost arbitration; a live probe of the
    occupant classifies it. A unique violation escaping ``ON CONFLICT``
    (the path index — arbitration declares only ``(parent_id, name)``)
    rolls back to the chunk's savepoint and re-drives row-by-row for
    exact, classified blame.
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
                    where=(entry.c.kind != "directory") & (entry.c.path == stmt.excluded["path"]),
                )
            else:
                stmt = stmt.on_conflict_do_nothing(index_elements=["parent_id", "name"])
            try:
                async with session.begin_nested():
                    result = await session.execute(stmt.returning(entry.c.entry_id, entry.c.path, entry.c.version))
                    returned = {mapping["path"]: mapping for mapping in result.mappings()}
            except IntegrityError:
                errors.extend(
                    await _resolve_rows(
                        session, entry, [s for s, _ in chunk], [r for _, r in chunk], overwrite=overwrite
                    )
                )
                continue
            for staged, row_values in chunk:
                won = returned.get(str(staged.path))
                if won is not None:
                    staged.entry_id = won["entry_id"]
                    staged.version = won["version"]
                else:
                    loss = await _classify_arbitration_loss(session, entry, staged, row_values, clobber=clobber)
                    if loss is not None:
                        errors.append(loss)
    return errors


async def _classify_arbitration_loss(
    session: AsyncSession,
    entry: Table,
    staged: StagedEntry,
    row_values: dict[str, object],
    *,
    clobber: bool,
) -> ResultError | None:
    """Probe the occupant that beat *staged*; classify, adopt, or redrive.

    A vanished occupant raises :class:`StaleSnapshot`: the probe may be
    snapshot-blinded (REPEATABLE READ cannot see the rival), and even an
    honest vanishing is exactly what a fresh snapshot resolves. A
    directory losing to a directory at the matching address adopts it —
    the mkdir-p forgiveness the sequential gates grant — and returns no
    error.
    """
    occupant_query = select(entry.c.entry_id, entry.c.kind, entry.c.path, entry.c.version).where(
        entry.c.parent_id == row_values["parent_id"], entry.c.name == row_values["name"]
    )
    occupant = (await session.execute(occupant_query)).one_or_none()
    if occupant is None:
        raise StaleSnapshot(f"the rival that beat {staged.path} is not observable from this snapshot")
    if occupant.path != str(staged.path):
        return _incoherent_row(staged.path)
    if staged.kind == "directory" and occupant.kind == "directory":
        staged.adopt(occupant.entry_id, occupant.version)
        return None
    if clobber:
        return wrong_kind("directory", staged.path, target=staged.path)
    return already_exists(staged.path, target=staged.path)


def _incoherent_row(path: Path) -> ResultError:
    """The arbitration refusal for a row whose stored address contradicts the request.

    Retryable by declaration: the caller raced ordinary traffic as far as
    it can know; the squatting row is a defect decisions upstream repair.
    """
    message = f"Address is held by a row this write may not adopt: {path}"
    return classified(VFSErrorKind.conflict, message, path, target=path, retryable=True)


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

    Each budget-sized chunk goes through ``bulk_insert`` (the dialect's
    declared bulk mode) under its own savepoint, so a conflict rolls
    back and re-drives only its chunk — O(conflicted chunks), never
    O(layer); the driver's executemany and Core's pages fail the chunk
    the same way. Identity is minted at
    staging, so a clean insert learns nothing back.
    """
    errors: list[ResultError] = []
    for chunk in chunked(list(zip(layer, rows, strict=True)), per_statement):
        chunk_rows = [values for _, values in chunk]
        try:
            async with session.begin_nested():
                await bulk_insert(session, entry, chunk_rows)
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
    """Re-run a conflicted chunk row-at-a-time, each insert in its own savepoint.

    The occupant probe compares the matched row's stored path to the
    requested path before any adoption: an incoherent row (a legacy torn
    ghost squatting the address) classifies a retryable ``conflict`` and
    is never absorbed into. A vanished occupant raises
    :class:`StaleSnapshot` — the probe may be snapshot-blinded, and a
    fresh snapshot resolves the race honestly either way. A directory
    losing to a directory at the matching address adopts it silently.
    """
    errors: list[ResultError] = []
    for staged, row_values in zip(layer, rows, strict=True):
        try:
            async with session.begin_nested():
                await session.execute(insert(entry).values(**row_values))
            continue
        except IntegrityError:
            pass
        occupant_query = select(entry.c.entry_id, entry.c.kind, entry.c.path, entry.c.version).where(
            entry.c.parent_id == row_values["parent_id"], entry.c.name == row_values["name"]
        )
        occupant = (await session.execute(occupant_query)).one_or_none()
        if occupant is None:
            raise StaleSnapshot(f"the rival that beat {staged.path} is not observable from this snapshot")
        if occupant.path != str(staged.path):
            errors.append(_incoherent_row(staged.path))
        elif staged.kind == "directory" and occupant.kind == "directory":
            staged.adopt(occupant.entry_id, occupant.version)
        elif staged.kind != "directory" and overwrite and occupant.kind != "directory":
            # The rival's row absorbs our write: a clobbering update that
            # still proves its address (relocations must miss it).
            staged.absorb(occupant.entry_id)
        elif staged.kind != "directory" and overwrite:
            errors.append(wrong_kind("directory", staged.path, target=staged.path))
        else:
            errors.append(already_exists(staged.path, target=staged.path))
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
    """Material updates with the version-and-path guard, attributed from the statement.

    The guarded arm writes ``base + 1`` under ``WHERE version = base AND
    path = path-at-snapshot`` and learns which rows its own statement
    matched — never from a re-read of the post-image, which cannot tell
    our one increment from a rival's at READ COMMITTED. The path
    predicate closes the ancestor-relocation escape: subtree rewrites
    bump no descendant versions, so a version guard alone reports
    success at an address that no longer exists. The ladder, selected
    from what the live dialect models: a set-based VALUES join whose
    RETURNING set is the success set; an executemany whose sane
    aggregate rowcount proves every guard matched (each statement
    matches at most one row via the unique ``entry_id`` index — the
    upstream staging layer stages one row per entry_id, never
    duplicates within a batch), rolled back to a savepoint and
    re-driven row-by-row on mismatch; per-row execution attributed by
    each statement's own rowcount; or a classified refusal — an
    unverifiable guarded write never proceeds. A guard miss classifies
    per the dialect's declared ``guard_miss`` mode: an honest re-probe
    (``not_found`` vs ``conflict``), or a whole-method redrive where the
    probe would lie. The absorb arm (arbitration clobbers) increments
    SQL-side, last-writer-wins between writes by design — but it still
    proves its address: the update carries the path at probe time (a
    topology relocation always rewrites the path, so a row trashed or
    moved mid-window misses), and application is verified from
    RETURNING or a read-back comparing the stored path; a miss raises
    :class:`StaleSnapshot` and the whole method redrives.
    """
    if not updates:
        return []
    guarded = [s for s in updates if s.persistence == "update"]
    unguarded = [s for s in updates if s.persistence == "absorb"]
    dialect = session.get_bind().dialect
    set_based = supports_values_update(profile, dialect)
    errors: list[ResultError] = []
    if guarded:
        if set_based:
            matched = await _values_update(
                session, entry, parameter_budget, membership_budget, guarded, user_id=user_id, now=now, guard=True
            )
            missed = [s for s in guarded if s.entry_id not in matched]
            errors.extend(await _classify_guard_misses(session, entry, profile, membership_budget, missed))
        elif dialect.supports_sane_multi_rowcount:
            errors.extend(
                await _guarded_by_aggregate(
                    session, entry, profile, membership_budget, guarded, user_id=user_id, now=now
                )
            )
        elif dialect.supports_sane_rowcount:
            errors.extend(
                await _guarded_by_rowcount(
                    session, entry, profile, membership_budget, guarded, user_id=user_id, now=now
                )
            )
        else:
            message = f"Guarded updates cannot be verified on {profile.name}: no UPDATE RETURNING, no sane rowcount"
            return [ResultError(kind=VFSErrorKind.unsupported, message=message)]
    if unguarded:
        if set_based:
            learned = await _values_update(
                session, entry, parameter_budget, membership_budget, unguarded, user_id=user_id, now=now, guard=False
            )
            for staged in unguarded:
                version = learned.get(staged.entry_id)
                if version is None:
                    raise StaleSnapshot(f"the occupant absorbing {staged.path} moved past this write's snapshot")
                staged.version = version
        else:
            material = {name: bindparam(f"b_{name}") for name in _CLOBBER_COLUMNS}
            stmt = (
                update(entry)
                .where(entry.c.entry_id == bindparam("b_id"), entry.c.path == bindparam("b_path"))
                .values(**material, version=entry.c.version + 1)
            )
            params = [_update_params(s, user_id, now) | {"b_path": str(s.path)} for s in unguarded]
            await session.execute(stmt, params)
            # The read-back proves application: the updated row holds its
            # X-lock, so a stored path disagreeing means the guard missed.
            found_rows: dict[str, Any] = {}
            for chunk in chunked([s.entry_id for s in unguarded], membership_budget):
                found = await session.execute(
                    select(entry.c.entry_id, entry.c.version, entry.c.path).where(entry.c.entry_id.in_(chunk))
                )
                found_rows.update({row.entry_id: row for row in found})
            for staged in unguarded:
                row = found_rows.get(staged.entry_id)
                if row is None or row.path != str(staged.path):
                    raise StaleSnapshot(f"the occupant absorbing {staged.path} moved past this write's snapshot")
                staged.version = row.version
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
    guarded, on ``version = base`` and ``path`` at snapshot); the
    returned ``entry_id`` set is exactly the rows this statement
    touched. Chunked by the tighter of the membership budget and the
    per-tuple bind cost, so a 10,000-entry batch stays batch-native and
    bounded on every engine.
    """
    rows = []
    for entry_row in staged:
        material = _material_values(entry_row, user_id, now)
        ordered = tuple(material[name] for name in _CLOBBER_COLUMNS)
        rows.append((entry_row.entry_id, entry_row.base_version, entry_row.version, str(entry_row.path), *ordered))
    per_statement = statement_budget(
        lambda probe: _values_update_stmt(entry, probe, guard=guard),
        rows[0],
        session.get_bind().dialect,
        parameter_budget=parameter_budget,
        row_width=len(rows[0]),
        row_cap=membership_budget,
    )
    matched: dict[str, int] = {}
    for chunk in chunked(rows, per_statement):
        result = await session.execute(_values_update_stmt(entry, chunk, guard=guard))
        matched.update({mapping["entry_id"]: mapping["version"] for mapping in result.mappings()})
    return matched


def _values_update_stmt(entry: Table, rows: Sequence[tuple[object, ...]], *, guard: bool) -> Update:
    """One material-update VALUES join over staged *rows*.

    Both arms prove the address; only the guarded arm pins the version —
    the unguarded arm increments SQL-side, a fixed bind the budget helper
    measures off this construction.
    """
    incoming = values(
        column("v_id", entry.c.entry_id.type),
        column("v_base", entry.c.version.type),
        column("v_ver", entry.c.version.type),
        column("v_path", entry.c.path.type),
        *(column(f"v_{name}", entry.c[name].type) for name in _CLOBBER_COLUMNS),
        name="incoming",
    ).data(list(rows))
    set_: dict[str, Any] = {name: incoming.c[f"v_{name}"] for name in _CLOBBER_COLUMNS}
    where = [entry.c.entry_id == incoming.c.v_id, entry.c.path == incoming.c.v_path]
    if guard:
        set_["version"] = incoming.c.v_ver
        where.append(entry.c.version == incoming.c.v_base)
    else:
        set_["version"] = entry.c.version + 1
    return update(entry).where(*where).values(**set_).returning(entry.c.entry_id, entry.c.version)


async def _guarded_by_aggregate(
    session: AsyncSession,
    entry: Table,
    profile: DialectProfile,
    membership_budget: int,
    guarded: list[StagedEntry],
    *,
    user_id: str | None,
    now: datetime,
) -> list[ResultError]:
    """Executemany fast path: an aggregate rowcount of N proves N guards matched.

    On mismatch the savepoint rolls back — guarded updates are not
    idempotent, so attribution must not re-run them over applied state.
    A redrive-mode dialect raises :class:`StaleSnapshot` right here (per-row
    blame would be built on an unreliable probe); everywhere else the
    per-row floor re-drives for exact blame.
    """
    params = [_guarded_params(s, user_id, now) for s in guarded]
    nested = await session.begin_nested()
    result = cast("CursorResult[Any]", await session.execute(_guarded_stmt(entry), params))
    if result.rowcount == len(params):
        await nested.commit()
        return []
    await nested.rollback()
    if profile.guard_miss == "redrive":
        raise StaleSnapshot(f"{len(params) - result.rowcount} guarded update(s) missed their snapshot")
    return await _guarded_by_rowcount(session, entry, profile, membership_budget, guarded, user_id=user_id, now=now)


async def _guarded_by_rowcount(
    session: AsyncSession,
    entry: Table,
    profile: DialectProfile,
    membership_budget: int,
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
    missed: list[StagedEntry] = []
    for staged in guarded:
        result = cast("CursorResult[Any]", await session.execute(stmt, _guarded_params(staged, user_id, now)))
        if result.rowcount == 0:
            missed.append(staged)
    return await _classify_guard_misses(session, entry, profile, membership_budget, missed)


async def _classify_guard_misses(
    session: AsyncSession,
    entry: Table,
    profile: DialectProfile,
    membership_budget: int,
    missed: list[StagedEntry],
) -> list[ResultError]:
    """Interpret zero-row guard outcomes per the dialect's declared mode.

    ``redrive``: the probe would lie about current state, so the whole
    method retries from a fresh snapshot. ``reprobe``: one chunked
    re-probe by id splits honest ``not_found`` (the row is gone) from
    ``conflict`` (the row moved past the snapshot — version or address).
    """
    if not missed:
        return []
    if profile.guard_miss == "redrive":
        raise StaleSnapshot(f"{len(missed)} guarded update(s) missed their snapshot")
    present: set[str] = set()
    for chunk in chunked([s.entry_id for s in missed], membership_budget):
        found = await session.execute(select(entry.c.entry_id).where(entry.c.entry_id.in_(chunk)))
        present.update(row.entry_id for row in found)
    errors: list[ResultError] = []
    for staged in missed:
        if staged.entry_id in present:
            errors.append(_conflict(staged))
        else:
            errors.append(
                classified(VFSErrorKind.not_found, f"Not found: {staged.path}", staged.path, target=staged.path)
            )
    return errors


def _guarded_stmt(entry: Table) -> Update:
    material = {name: bindparam(f"b_{name}") for name in _CLOBBER_COLUMNS}
    return (
        update(entry)
        .where(
            entry.c.entry_id == bindparam("b_id"),
            entry.c.version == bindparam("b_base"),
            entry.c.path == bindparam("b_path"),
        )
        .values(**material, version=bindparam("b_ver"))
    )


def _guarded_params(staged: StagedEntry, user_id: str | None, now: datetime) -> dict[str, object]:
    guard = {"b_base": staged.base_version, "b_ver": staged.version, "b_path": str(staged.path)}
    return _update_params(staged, user_id, now) | guard


def _conflict(staged: StagedEntry) -> ResultError:
    # Retryable by declaration: an identical immediate retry adjudicates
    # against the rival's committed state and resolves honestly.
    message = f"Concurrent modification: {staged.path}"
    return classified(VFSErrorKind.conflict, message, staged.path, target=staged.path, retryable=True)


async def _replace_content(
    session: AsyncSession, content: Table, membership_budget: int, staged: list[StagedEntry], now: datetime
) -> None:
    """Delete-then-insert the batch's content rows — portable, idempotent.

    The insert is ``bulk_insert`` — paged under the dialect's parameter
    budget there; only the membership-predicate delete chunks here.
    """
    bearing = [s for s in staged if s.content is not None and s.kind in CONTENT_KINDS]
    if not bearing:
        return
    for chunk in chunked([s.entry_id for s in bearing], membership_budget):
        await session.execute(delete(content).where(content.c.entry_id.in_(chunk)))
    rows = [{"entry_id": s.entry_id, "created_at": now, "content": s.content} for s in bearing]
    await bulk_insert(session, content, rows)


async def _bump_parents(
    session: AsyncSession,
    entry: Table,
    profile: DialectProfile,
    parameter_budget: int,
    membership_budget: int,
    plan: WritePlan,
) -> list[ResultError]:
    """Guarded SQL-side increments: every bump proves its parent's address.

    The bump set is derived here, from the staged rows' final states —
    never at staging, where arbitration (absorb, adopt) can silently
    invalidate it — so a parent acquired by adoption is affirmed like any
    committed parent, from the identity the staged entry carries.
    ``version = version + 1`` under ``WHERE entry_id AND path-at-snapshot``
    still composes with rival bumps, while a parent a rival relocated or
    destroyed mid-window — delete, move, restore, and purge are one
    failure mode here — misses the guard. The predicate is the path, not
    ``parent_id``: a grandparent's relocation rewrites only descendant
    paths, and must miss too. Rowcount is verified per chunk against the
    chunk's pair count; any shortfall raises :class:`StaleSnapshot`, so
    the whole batch — the torn creates are uncommitted inserts in this
    same transaction — rolls back and the method redrives from a fresh
    snapshot. The read-back covers every pending row this pass bumped —
    "unchanged" occupants and adopted parents alike — because their
    observations must equal a post-commit stat of their paths.
    """
    bumps = plan.derive_bumps()
    if not bumps:
        return []
    pairs = [(bumps[path], path) for path in sorted(bumps)]
    dialect = session.get_bind().dialect
    if supports_values_update(profile, dialect):
        await _bump_by_values(session, entry, parameter_budget, membership_budget, pairs)
    elif dialect.supports_sane_multi_rowcount or dialect.supports_sane_rowcount:
        per_row = not dialect.supports_sane_multi_rowcount
        await _bump_by_rowcount(session, entry, membership_budget, pairs, per_row=per_row)
    else:
        message = f"Guarded parent bumps cannot be verified on {profile.name}: no UPDATE RETURNING, no sane rowcount"
        return [ResultError(kind=VFSErrorKind.unsupported, message=message)]
    needed: set[str] = set()
    for path, _ in plan.pending:
        staged = plan.staged.get(path)
        if staged is None:
            if str(path) in bumps:
                needed.add(str(path))
        elif staged.persistence == "adopt" and str(staged.path) in bumps:
            needed.add(str(staged.path))
    if not needed:
        return []
    ids = [bumps[path] for path in sorted(needed)]
    plan.bump_versions = {}
    for chunk in chunked(ids, membership_budget):
        result = await session.execute(select(entry.c.path, entry.c.version).where(entry.c.entry_id.in_(chunk)))
        plan.bump_versions.update({row.path: row.version for row in result})
    for staged in plan.staged.values():
        if staged.persistence == "adopt" and (bumped := plan.bump_versions.get(str(staged.path))) is not None:
            staged.version = bumped
    return []


async def _bump_by_values(
    session: AsyncSession,
    entry: Table,
    parameter_budget: int,
    membership_budget: int,
    pairs: list[tuple[str, str]],
) -> None:
    """Set-based guarded bump over a VALUES join; RETURNING is the proof."""
    per_statement = statement_budget(
        lambda probe: _bump_values_stmt(entry, probe),
        pairs[0],
        session.get_bind().dialect,
        parameter_budget=parameter_budget,
        row_width=len(pairs[0]),
        row_cap=membership_budget,
    )
    for chunk in chunked(pairs, per_statement):
        stmt = _bump_values_stmt(entry, chunk)
        matched = len((await session.execute(stmt)).all())
        if matched != len(chunk):
            raise StaleSnapshot(f"{len(chunk) - matched} parent(s) were relocated or destroyed mid-batch")


def _bump_values_stmt(entry: Table, pairs: Sequence[tuple[str, str]]) -> Update:
    """One guarded-bump VALUES join over *pairs* of ``(entry_id, path)``."""
    incoming = values(
        column("v_id", entry.c.entry_id.type),
        column("v_path", entry.c.path.type),
        name="incoming",
    ).data(list(pairs))
    return (
        update(entry)
        .where(entry.c.entry_id == incoming.c.v_id, entry.c.path == incoming.c.v_path)
        .values(version=entry.c.version + 1)
        .returning(entry.c.entry_id)
    )


async def _bump_by_rowcount(
    session: AsyncSession,
    entry: Table,
    membership_budget: int,
    pairs: list[tuple[str, str]],
    *,
    per_row: bool,
) -> None:
    """Guarded bump verified by rowcount — executemany aggregate, or the per-row floor."""
    stmt = (
        update(entry)
        .where(entry.c.entry_id == bindparam("b_id"), entry.c.path == bindparam("b_path"))
        .values(version=entry.c.version + 1)
    )
    for chunk in chunked(pairs, membership_budget):
        params = [{"b_id": entry_id, "b_path": path} for entry_id, path in chunk]
        if per_row:
            matched = 0
            for row_params in params:
                result = cast("CursorResult[Any]", await session.execute(stmt, row_params))
                matched += result.rowcount
        else:
            matched = cast("CursorResult[Any]", await session.execute(stmt, params)).rowcount
        if matched != len(params):
            raise StaleSnapshot(f"{len(params) - matched} parent(s) were relocated or destroyed mid-batch")


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
        "chunked": False,
        "encoded": False,
        "indexable": False,
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
