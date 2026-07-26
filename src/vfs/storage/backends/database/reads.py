"""Read-family and glob statement builders for ``DatabaseStorage``.

Column selects narrowed by the caller's projection, reconstructed into
:class:`~vfs.models.Observation` rows with an explicit populated mask
(``populated == (requested and servable) + {path, kind, version}``,
fetched-and-null included; a requested field with no backing column is
dropped from the mask, never reported as fetched). Every function takes
the op's live ``AsyncSession`` and only executes SELECTs; none begins
or commits — the protocol method in ``backend.py`` owns its one
transaction.

The shapes: point reads are ``path IN`` column selects, content joined
from the content table; ``ls`` is ``parent_id`` equality only, never a
prefix scan; ``tree`` and glob prefilter with sargable escaped ``LIKE``
on the path cache, glob verified authoritatively by ``fnmatch`` over
the candidates. Listings order by the binary-collated ``name`` column
and subtrees by ``path`` — byte-identical across engines.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from sqlalchemy import func, or_, select

from vfs.models import CONTENT_KINDS, Observation
from vfs.paths import ROOT, Path
from vfs.results import Result, ResultError, wrong_kind
from vfs.storage.backends.database.descent import (
    LIKE_ESCAPE,
    classify_misses,
    descendant_filter,
    escape_like,
    liveness_filters,
    miss_errors,
    rows_by_path,
    subtree_filter,
)
from vfs.storage.backends.database.dialects import chunked
from vfs.storage.globbing import compile_glob

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy import Column, ColumnElement, FromClause, Table
    from sqlalchemy.engine import RowMapping
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models.rows import VFSTables

# Observation fields served directly by entries-table columns (the two
# vocabularies share these names by construction). A file's current version
# label IS its version (one per-entry sequence); version_number surfaces
# only on Version rows, never from the entries table.
ENTRY_OBSERVATION_FIELDS: Final[frozenset[str]] = frozenset(
    {"path", "kind", "version", "content_hash", "mime_type", "size_bytes"} | {"created_at", "updated_at"},
)

# Identity fields every observation carries regardless of projection.
ALWAYS_ON_FIELDS: Final[frozenset[str]] = frozenset({"path", "kind", "version"})

# fnmatch character classes have no LIKE equivalent; those patterns fall
# back to a literal-prefix prefilter with fnmatch as the only filter.
_GLOB_TRANSLATED: Final[frozenset[str]] = frozenset("*?")


# ---------------------------------------------------------------------------
# Projection
# ---------------------------------------------------------------------------


def effective_columns(columns: frozenset[str] | None, *, content: bool) -> frozenset[str]:
    """The Observation fields this op fetches — also the populated mask.

    ``None`` means no push-down: every entry-backed field (plus content
    when the verb carries it). A concrete projection narrows to the
    requested ∩ servable fields, identity fields always on; a requested
    field with no backing column yet is simply not in the mask.
    """
    if columns is None:
        fetched = set(ENTRY_OBSERVATION_FIELDS)
        if content:
            fetched.add("content")
        return frozenset(fetched)
    fetched = set((columns & ENTRY_OBSERVATION_FIELDS) | ALWAYS_ON_FIELDS)
    if content and "content" in columns:
        fetched.add("content")
    return frozenset(fetched)


# ---------------------------------------------------------------------------
# Point reads — read and stat
# ---------------------------------------------------------------------------


async def read_rows(
    session: AsyncSession,
    tables: VFSTables,
    membership_budget: int,
    targets: Sequence[Path],
    columns: frozenset[str] | None,
) -> Result:
    fetched = effective_columns(columns, content=True)
    rows, errors = await _point_rows(session, tables, membership_budget, targets, fetched, content_only=True)
    return Result(ops=("read",), observations=rows, errors=errors)


async def stat_rows(
    session: AsyncSession,
    tables: VFSTables,
    membership_budget: int,
    targets: Sequence[Path],
    columns: frozenset[str] | None,
) -> Result:
    fetched = effective_columns(columns, content=False)
    rows, errors = await _point_rows(session, tables, membership_budget, targets, fetched, content_only=False)
    return Result(ops=("stat",), observations=rows, errors=errors)


# ---------------------------------------------------------------------------
# Listings — ls and tree
# ---------------------------------------------------------------------------


async def ls_rows(
    session: AsyncSession,
    tables: VFSTables,
    membership_budget: int,
    targets: Sequence[Path],
    columns: frozenset[str] | None,
) -> Result:
    fetched = effective_columns(columns, content=False)
    anchors = await _mappings_by_path(session, tables, membership_budget, targets, fetched, with_entry_id=True)
    missing = await miss_errors(session, tables.entry, targets, anchors, membership_budget)
    directories = [t for t in targets if (a := anchors.get(t)) is not None and a["kind"] == "directory"]
    children = await _children_by_parent(session, tables.entry, membership_budget, directories, anchors, fetched)
    rows: list[Observation] = []
    errors: list[ResultError] = []
    for target in targets:
        anchor = anchors.get(target)
        if anchor is None:
            errors.append(missing[target])
        elif anchor["kind"] != "directory":
            rows.append(_observe(anchor, fetched))
        else:
            rows.extend(children.get(anchor["entry_id"], ()))
    return Result(ops=("ls",), observations=rows, errors=errors)


async def tree_rows(
    session: AsyncSession,
    tables: VFSTables,
    membership_budget: int,
    path: Path,
    max_depth: int | None,
    columns: frozenset[str] | None,
) -> Result:
    fetched = effective_columns(columns, content=False)
    entry = tables.entry
    anchors = await _mappings_by_path(session, tables, membership_budget, [path], fetched, with_entry_id=False)
    anchor = anchors.get(path)
    if anchor is None:
        return Result(ops=("tree",), errors=await classify_misses(session, entry, [path], membership_budget))
    if anchor["kind"] != "directory":
        return Result(ops=("tree",), observations=[_observe(anchor, fetched)])
    stmt = (
        select(*_entry_columns(entry, fetched))
        .where(
            descendant_filter(entry, str(path)),
            *liveness_filters(entry, include_meta=path.is_meta),
        )
        .order_by(entry.c.path)
    )
    if max_depth is not None:
        stmt = stmt.where(_slash_count(entry) <= path.depth + max_depth)
    rows = [_observe(mapping, fetched) for mapping in (await session.execute(stmt)).mappings()]
    return Result(ops=("tree",), observations=rows)


# ---------------------------------------------------------------------------
# Glob — sargable LIKE prefilter, fnmatch authority
# ---------------------------------------------------------------------------


async def glob_rows(
    session: AsyncSession,
    tables: VFSTables,
    membership_budget: int,
    fan_budget: int,
    *,
    pattern: str,
    scope: tuple[Path, ...],
    ext: tuple[str, ...],
    max_count: int | None,
    columns: frozenset[str] | None,
) -> Result:
    """Glob under *scope*, anchors behaving like POSIX ``find`` operands.

    A missing anchor classifies through the descent ladder beside the
    healthy anchors' rows — partial results with per-anchor errors; an
    existing file anchor is matched itself against the pattern.
    """
    fetched = effective_columns(columns, content=False)
    entry = tables.entry
    glob = compile_glob(pattern, ext)
    subject_column = entry.c.path if glob.by_path else entry.c.name
    # Liveness is per scope arm, not per query: _glob_candidates applies
    # the meta exclusion to every anchor except the meta-addressed ones.
    filters: list[ColumnElement[bool]] = [entry.c.path != "/"]
    like = _glob_like(pattern)
    if like is not None:
        filters.append(subject_column.like(like, escape=LIKE_ESCAPE))
    else:
        filters.append(subject_column.like(escape_like(_literal_prefix(pattern)) + "%", escape=LIKE_ESCAPE))
    errors: list[ResultError] = []
    if scope:
        anchors = await _mappings_by_path(
            session, tables, membership_budget, scope, frozenset({"path", "kind"}), with_entry_id=False
        )
        errors = list((await miss_errors(session, tables.entry, scope, anchors, membership_budget)).values())
    candidates = await _glob_candidates(session, entry, fan_budget, scope, filters, fetched)
    rows: list[Observation] = []
    for mapping in candidates:
        if max_count is not None and len(rows) >= max_count:
            break
        if not glob.matches(Path(mapping["path"])):
            continue
        rows.append(_observe(mapping, fetched))
    return Result(ops=("glob",), observations=rows, errors=errors)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _point_rows(
    session: AsyncSession,
    tables: VFSTables,
    membership_budget: int,
    targets: Sequence[Path],
    fetched: frozenset[str],
    *,
    content_only: bool,
) -> tuple[list[Observation], list[ResultError]]:
    """Fetch, classify, and observe *targets* one row at a time, in order."""
    found = await _mappings_by_path(session, tables, membership_budget, targets, fetched, with_entry_id=False)
    missing = await miss_errors(session, tables.entry, targets, found, membership_budget)
    rows: list[Observation] = []
    errors: list[ResultError] = []
    for target in targets:
        mapping = found.get(target)
        if mapping is None:
            errors.append(missing[target])
            continue
        kind = mapping["kind"]
        if content_only and kind not in CONTENT_KINDS:
            errors.append(wrong_kind(kind, target))
            continue
        rows.append(_observe(mapping, fetched))
    return rows, errors


async def _mappings_by_path(
    session: AsyncSession,
    tables: VFSTables,
    membership_budget: int,
    targets: Sequence[Path],
    fetched: frozenset[str],
    *,
    with_entry_id: bool,
) -> dict[str, RowMapping]:
    """One bounded fetch for the batch, keyed by the stored path string."""
    columns, source = _entry_projection(tables, fetched, with_entry_id=with_entry_id)
    paths = (str(target) for target in targets)
    return await rows_by_path(session, tables.entry, paths, columns, membership_budget, source=source)


async def _glob_candidates(
    session: AsyncSession,
    entry: Table,
    fan_budget: int,
    scope: tuple[Path, ...],
    filters: list[ColumnElement[bool]],
    fetched: frozenset[str],
) -> list[RowMapping]:
    """Prefiltered candidate rows in path order, one scope arm per liveness class.

    The meta bypass is per-anchor: a meta-addressed anchor fans with the
    exclusion lifted, while the default scope and every other anchor
    (ROOT included) keep the ``/.vfs`` subtree hidden. The merge dict
    dedupes rows nested anchors both match, and one Python sort restores
    path order — codepoint order equals the binary-collated byte order.
    """
    columns = _entry_columns(entry, fetched)
    live = [anchor for anchor in scope if not anchor.is_meta]
    meta = [anchor for anchor in scope if anchor.is_meta]
    hidden = [*filters, *liveness_filters(entry, include_meta=False)]
    merged: dict[str, RowMapping] = {}
    if not scope or ROOT in live:
        stmt = select(*columns).where(*hidden)
        merged.update({mapping["path"]: mapping for mapping in (await session.execute(stmt)).mappings()})
    elif live:
        await _anchor_fan(session, entry, fan_budget, columns, hidden, live, merged)
    if meta:
        await _anchor_fan(session, entry, fan_budget, columns, filters, meta, merged)
    return [merged[path] for path in sorted(merged)]


async def _anchor_fan(
    session: AsyncSession,
    entry: Table,
    fan_budget: int,
    columns: list[Column[object]],
    filters: list[ColumnElement[bool]],
    anchors: Sequence[Path],
    merged: dict[str, RowMapping],
) -> None:
    """One liveness class's chunked anchor fan, merged into *merged*.

    Chunks hold ``fan_budget`` anchors — the dialect's declared cap on
    the tighter of bind count and ``OR``-chain expression depth. Simple
    planners may scan the table once per chunk (Postgres builds a
    bitmap-OR); bounded and correct either way.
    """
    for chunk in chunked(sorted({str(anchor) for anchor in anchors}), fan_budget):
        fan = or_(*(subtree_filter(entry, anchor) for anchor in chunk))
        result = await session.execute(select(*columns).where(*filters, fan))
        merged.update({mapping["path"]: mapping for mapping in result.mappings()})


async def _children_by_parent(
    session: AsyncSession,
    entry: Table,
    membership_budget: int,
    directories: Sequence[Path],
    anchors: dict[str, RowMapping],
    fetched: frozenset[str],
) -> dict[str, list[Observation]]:
    """Chunked ``parent_id IN`` children selects, regrouped per parent.

    One scope per liveness class (meta-anchored targets see meta rows).
    Chunks partition parents, so each parent's children arrive whole and
    name-ordered; the dict preserves that order per parent.
    """
    children: dict[str, list[Observation]] = {}
    for include_meta in (False, True):
        scope = sorted({anchors[target]["entry_id"] for target in directories if target.is_meta == include_meta})
        for chunk in chunked(scope, membership_budget):
            stmt = (
                select(entry.c.parent_id, *_entry_columns(entry, fetched))
                .where(entry.c.parent_id.in_(chunk), *liveness_filters(entry, include_meta=include_meta))
                .order_by(entry.c.parent_id, entry.c.name)
            )
            for mapping in (await session.execute(stmt)).mappings():
                children.setdefault(mapping["parent_id"], []).append(_observe(mapping, fetched))
    return children


def _entry_projection(
    tables: VFSTables, fetched: frozenset[str], *, with_entry_id: bool
) -> tuple[list[Column[object]], FromClause | None]:
    """The select list serving *fetched*, plus the FROM override when content joins."""
    entry = tables.entry
    columns = _entry_columns(entry, fetched)
    if with_entry_id:
        columns = [entry.c.entry_id, *columns]
    if "content" not in fetched:
        return columns, None
    return [*columns, tables.content.c.content], tables.content_joined()


def _entry_columns(entry: Table, fetched: frozenset[str]) -> list[Column[object]]:
    return [entry.c[field] for field in sorted(fetched - {"content"})]


def _observe(mapping: RowMapping, fetched: frozenset[str]) -> Observation:
    values: dict[str, object] = {field: mapping[field] for field in fetched}
    values["path"] = Path(mapping["path"])
    values["populated"] = fetched
    return Observation.model_validate(values)


def _slash_count(entry: Table) -> ColumnElement[int]:
    """Portable segment-depth expression: slashes in the path column."""
    return func.char_length(entry.c.path) - func.char_length(func.replace(entry.c.path, "/", ""))


def _glob_like(pattern: str) -> str | None:
    """Exact LIKE translation of a ``*``/``?`` glob; ``None`` when inexpressible."""
    if "[" in pattern:
        return None
    out: list[str] = []
    for ch in pattern:
        if ch in _GLOB_TRANSLATED:
            out.append("%" if ch == "*" else "_")
        elif ch in ("%", "_", LIKE_ESCAPE):
            out.append(LIKE_ESCAPE + ch)
        else:
            out.append(ch)
    return "".join(out)


def _literal_prefix(pattern: str) -> str:
    index = min((i for i, ch in enumerate(pattern) if ch in "*?["), default=len(pattern))
    return pattern[:index]
