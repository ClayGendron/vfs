"""Read-family and glob statement builders for ``DatabaseStorage``.

Column selects narrowed by the caller's projection, reconstructed into
:class:`~vfs.models.Observation` rows with an explicit populated mask
(``populated == requested + {path, kind, version}``, fetched-and-null
included). Every function takes the op's live ``AsyncSession`` and only
executes SELECTs; none begins or commits — the protocol method in
``backend.py`` owns its one transaction.

The shapes: point reads are ``path IN`` column selects, content joined
from the content table; ``ls`` is ``parent_id`` equality only, never a
prefix scan; ``tree`` and glob prefilter with sargable escaped ``LIKE``
on the path cache, glob verified authoritatively by ``fnmatch`` over
the candidates. Listings order by the binary-collated ``name`` column
and subtrees by ``path`` — byte-identical across engines.
"""

from __future__ import annotations

import fnmatch
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import func, or_, select

from vfs.models import Observation
from vfs.paths import Path, extract_extension
from vfs.results import Result, ResultError, VFSErrorKind
from vfs.storage.backends.database.descent import (
    LIKE_ESCAPE,
    ROOT,
    classified,
    classify_misses,
    escape_like,
    in_meta,
    liveness_filters,
)
from vfs.storage.backends.database.dialects import chunked

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy import ColumnElement, Select, Table
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

# Stored kinds whose rows carry text content; everything else refuses
# content reads and surfaces no content metrics.
CONTENT_KINDS: Final[frozenset[str]] = frozenset({"file", "chunk", "version"})

# fnmatch character classes have no LIKE equivalent; those patterns fall
# back to a literal-prefix prefilter with fnmatch as the only filter.
_GLOB_TRANSLATED: Final[frozenset[str]] = frozenset("*?")


# ---------------------------------------------------------------------------
# Target shaping and projection
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
    membership: int,
    targets: Sequence[Path],
    columns: frozenset[str] | None,
) -> Result:
    fetched = effective_columns(columns, content=True)
    rows, errors = await _point_rows(session, tables, membership, targets, fetched, content_only=True)
    return Result(ops=("read",), observations=rows, errors=errors)


async def stat_rows(
    session: AsyncSession,
    tables: VFSTables,
    membership: int,
    targets: Sequence[Path],
    columns: frozenset[str] | None,
) -> Result:
    fetched = effective_columns(columns, content=False)
    rows, errors = await _point_rows(session, tables, membership, targets, fetched, content_only=False)
    return Result(ops=("stat",), observations=rows, errors=errors)


# ---------------------------------------------------------------------------
# Listings — ls and tree
# ---------------------------------------------------------------------------


async def ls_rows(
    session: AsyncSession,
    tables: VFSTables,
    membership: int,
    targets: Sequence[Path],
    columns: frozenset[str] | None,
) -> Result:
    fetched = effective_columns(columns, content=False)
    entry = tables.entry
    anchors = await _mappings_by_path(session, tables, membership, targets, fetched, with_id=True)
    miss_errors = await _miss_errors(session, tables, membership, targets, anchors)
    rows: list[Observation] = []
    errors: list[ResultError] = []
    for target in targets:
        anchor = anchors.get(target)
        if anchor is None:
            errors.append(miss_errors[target])
            continue
        if anchor["kind"] != "directory":
            rows.append(_observe(anchor, fetched))
            continue
        children = (
            select(*_entry_columns(entry, fetched))
            .where(entry.c.parent_id == anchor["id"], *liveness_filters(entry, include_meta=in_meta(target)))
            .order_by(entry.c.name)
        )
        rows.extend(_observe(child, fetched) for child in (await session.execute(children)).mappings())
    return Result(ops=("ls",), observations=rows, errors=errors)


async def tree_rows(
    session: AsyncSession,
    tables: VFSTables,
    membership: int,
    path: Path,
    max_depth: int | None,
    columns: frozenset[str] | None,
) -> Result:
    fetched = effective_columns(columns, content=False)
    entry = tables.entry
    anchors = await _mappings_by_path(session, tables, membership, [path], fetched, with_id=False)
    anchor = anchors.get(path)
    if anchor is None:
        return Result(ops=("tree",), errors=[(await classify_misses(session, entry, [path], membership))[0]])
    if anchor["kind"] != "directory":
        return Result(ops=("tree",), observations=[_observe(anchor, fetched)])
    prefix = "" if path == ROOT else escape_like(str(path))
    stmt = (
        select(*_entry_columns(entry, fetched))
        .where(
            entry.c.path.like(prefix + "/%", escape=LIKE_ESCAPE),
            entry.c.path != "/",
            *liveness_filters(entry, include_meta=in_meta(path)),
        )
        .order_by(entry.c.path)
    )
    if max_depth is not None:
        base_depth = 0 if path == ROOT else str(path).count("/")
        stmt = stmt.where(_slash_count(entry) <= base_depth + max_depth)
    rows = [_observe(mapping, fetched) for mapping in (await session.execute(stmt)).mappings()]
    return Result(ops=("tree",), observations=rows)


# ---------------------------------------------------------------------------
# Glob — sargable LIKE prefilter, fnmatch authority
# ---------------------------------------------------------------------------


async def glob_rows(
    session: AsyncSession,
    tables: VFSTables,
    membership: int,
    *,
    pattern: str,
    scope: tuple[Path, ...],
    ext: tuple[str, ...],
    max_count: int | None,
    columns: frozenset[str] | None,
) -> Result:
    fetched = effective_columns(columns, content=False)
    entry = tables.entry
    by_path = "/" in pattern
    subject_column = entry.c.path if by_path else entry.c.name
    filters: list[ColumnElement[bool]] = [
        entry.c.path != "/",
        *liveness_filters(entry, include_meta=any(in_meta(s) for s in scope)),
    ]
    like = _glob_like(pattern)
    if like is not None:
        filters.append(subject_column.like(like, escape=LIKE_ESCAPE))
    else:
        filters.append(subject_column.like(escape_like(_literal_prefix(pattern)) + "%", escape=LIKE_ESCAPE))
    candidates = await _glob_candidates(session, entry, membership, scope, filters, fetched)
    wanted_ext = frozenset(e.lstrip(".").lower() for e in ext)
    rows: list[Observation] = []
    for mapping in candidates:
        if max_count is not None and len(rows) >= max_count:
            break
        candidate = Path(mapping["path"])
        subject = str(candidate) if by_path else candidate.name
        if not fnmatch.fnmatchcase(subject, pattern):
            continue
        if wanted_ext and (extract_extension(candidate) or "") not in wanted_ext:
            continue
        rows.append(_observe(mapping, fetched))
    return Result(ops=("glob",), observations=rows)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _point_rows(
    session: AsyncSession,
    tables: VFSTables,
    membership: int,
    targets: Sequence[Path],
    fetched: frozenset[str],
    *,
    content_only: bool,
) -> tuple[list[Observation], list[ResultError]]:
    """Fetch, classify, and observe *targets* one row at a time, in order."""
    found = await _mappings_by_path(session, tables, membership, targets, fetched, with_id=False)
    miss_errors = await _miss_errors(session, tables, membership, targets, found)
    rows: list[Observation] = []
    errors: list[ResultError] = []
    for target in targets:
        mapping = found.get(target)
        if mapping is None:
            errors.append(miss_errors[target])
            continue
        kind = mapping["kind"]
        if content_only and kind not in CONTENT_KINDS:
            article = "an" if kind[0] in "aeiou" else "a"
            errors.append(classified(VFSErrorKind.wrong_kind, f"Is {article} {kind}: {target}", target))
            continue
        rows.append(_observe(mapping, fetched))
    return rows, errors


async def _mappings_by_path(
    session: AsyncSession,
    tables: VFSTables,
    membership: int,
    targets: Sequence[Path],
    fetched: frozenset[str],
    *,
    with_id: bool,
) -> dict[str, RowMapping]:
    """Chunked ``path IN`` selects for the batch, keyed by the stored path string."""
    if not targets:
        return {}
    entry = tables.entry
    found: dict[str, RowMapping] = {}
    for chunk in chunked(sorted({str(t) for t in targets}), membership):
        stmt = _entry_select(tables, fetched, with_id=with_id).where(entry.c.path.in_(chunk))
        found.update({mapping["path"]: mapping for mapping in (await session.execute(stmt)).mappings()})
    return found


async def _glob_candidates(
    session: AsyncSession,
    entry: Table,
    membership: int,
    scope: tuple[Path, ...],
    filters: list[ColumnElement[bool]],
    fetched: frozenset[str],
) -> list[RowMapping]:
    """Prefiltered candidate rows in path order; scope anchors fan out chunked.

    Each anchor costs two binds (equality + prefix LIKE), so chunks hold
    ``membership // 2`` anchors; the merge dict dedupes rows nested
    anchors both match, and one Python sort restores path order —
    codepoint order equals the binary-collated column's byte order.
    """
    columns = _entry_columns(entry, fetched)
    if not scope or ROOT in scope:
        stmt = select(*columns).where(*filters).order_by(entry.c.path)
        return list((await session.execute(stmt)).mappings())
    merged: dict[str, RowMapping] = {}
    for chunk in chunked(sorted({str(anchor) for anchor in scope}), max(1, membership // 2)):
        fan = or_(
            *(
                or_(
                    entry.c.path == anchor,
                    entry.c.path.like(escape_like(anchor) + "/%", escape=LIKE_ESCAPE),
                )
                for anchor in chunk
            ),
        )
        result = await session.execute(select(*columns).where(*filters, fan))
        merged.update({mapping["path"]: mapping for mapping in result.mappings()})
    return [merged[path] for path in sorted(merged)]


async def _miss_errors(
    session: AsyncSession,
    tables: VFSTables,
    membership: int,
    targets: Sequence[Path],
    found: dict[str, RowMapping],
) -> dict[Path, ResultError]:
    misses = [target for target in targets if target not in found]
    return dict(zip(misses, await classify_misses(session, tables.entry, misses, membership), strict=True))


def _entry_select(tables: VFSTables, fetched: frozenset[str], *, with_id: bool) -> Select[Any]:
    entry = tables.entry
    columns = _entry_columns(entry, fetched)
    if with_id:
        columns = [entry.c.id, *columns]
    if "content" not in fetched:
        return select(*columns)
    content = tables.content
    joined = entry.outerjoin(content, content.c.entry_id == entry.c.id)
    return select(*columns, content.c.content).select_from(joined)


def _entry_columns(entry: Table, fetched: frozenset[str]) -> list[Any]:
    return [entry.c[field] for field in sorted(fetched - {"content"})]


def _observe(mapping: RowMapping, fetched: frozenset[str]) -> Observation:
    values: dict[str, Any] = {field: mapping[field] for field in fetched}
    values["path"] = Path(mapping["path"])
    # Content metrics are meaningful only on content-bearing kinds; the
    # NOT NULL storage default of 0 must not read as a real size.
    if "size_bytes" in values and mapping["kind"] not in CONTENT_KINDS:
        values["size_bytes"] = None
    return Observation(**values, populated=fetched)


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
