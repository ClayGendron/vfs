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
prefix scan; ``tree`` prefilters with one sargable escaped ``LIKE`` on
the path cache. Glob executes the batched pattern contract: every
pattern contributes one self-contained OR-arm (its sargable ``LIKE``
prefilter with all ext and liveness facts inside the arm), arms chunk
by the dialect's budgets in one snapshot, and the compiled
segment-aware patterns (``vfs.pattern_matching``) verify every candidate
authoritatively. Listings order by the binary-collated ``name`` column
and subtrees by ``path`` — byte-identical across engines.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from sqlalchemy import and_, func, or_, select

from vfs.models import CONTENT_KINDS, Observation
from vfs.paths import METADATA_ROOT, Path, extract_extension
from vfs.pattern_matching import GlobFilter, compile_filter, derive_ext, glob_defect
from vfs.results import Result, ResultError, VFSErrorKind, wrong_kind
from vfs.storage.backends.database.descent import (
    LIKE_ESCAPE,
    classify_misses,
    descendant_filter,
    escape_like,
    liveness_filters,
    miss_errors,
    rows_by_path,
)
from vfs.storage.backends.database.dialects import arm_budget, chunked

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy import Column, ColumnElement, FromClause, Table
    from sqlalchemy.engine import RowMapping
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models.rows import VFSTables
    from vfs.storage.backends.database.dialects import DialectProfile

# Observation fields served directly by entries-table columns (the two
# vocabularies share these names by construction). A file's current version
# label IS its version (one per-entry sequence); version_number surfaces
# only on Version rows, never from the entries table.
ENTRY_OBSERVATION_FIELDS: Final[frozenset[str]] = frozenset(
    {"path", "kind", "version", "content_hash", "mime_type", "size_bytes"} | {"created_at", "updated_at"},
)

# Identity fields every observation carries regardless of projection.
ALWAYS_ON_FIELDS: Final[frozenset[str]] = frozenset({"path", "kind", "version"})

# Glob character classes have no LIKE equivalent; those patterns fall
# back to a literal-prefix prefilter with the compiled glob as the filter.
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
    found = await _mappings_by_path(session, tables, membership_budget, targets, fetched, with_entry_id=True)
    missing = await miss_errors(session, tables.entry, targets, found, membership_budget)
    directories = [t for t in targets if (f := found.get(t)) is not None and f["kind"] == "directory"]
    children = await _children_by_parent(session, tables.entry, membership_budget, directories, found, fetched)
    rows: list[Observation] = []
    errors: list[ResultError] = []
    for target in targets:
        mapping = found.get(target)
        if mapping is None:
            errors.append(missing[target])
        elif mapping["kind"] != "directory":
            rows.append(_observe(mapping, fetched))
        else:
            rows.extend(children.get(mapping["entry_id"], ()))
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
    found = await _mappings_by_path(session, tables, membership_budget, [path], fetched, with_entry_id=False)
    target = found.get(path)
    if target is None:
        return Result(ops=("tree",), errors=await classify_misses(session, entry, [path], membership_budget))
    if target["kind"] != "directory":
        return Result(ops=("tree",), observations=[_observe(target, fetched)])
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
# Glob — one OR fan of self-contained pattern arms, compiled authority
# ---------------------------------------------------------------------------

# Ceiling of one arm's non-ext bind slots: the root-row exclusion, the
# prefilter LIKE, the derived-ext pair, the meta-liveness pair, and the
# kind fact.
ARM_FIXED_BINDS: Final = 7


async def glob_rows(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    parameter_budget: int,
    membership_budget: int,
    *,
    patterns: tuple[str, ...],
    globs_not: tuple[str, ...],
    ext: tuple[str, ...],
    ext_not: tuple[str, ...],
    kind: str | None,
    max_count: int | None,
    columns: frozenset[str] | None,
) -> Result:
    """Rows matching **any** pattern, one snapshot, statements chunked by budget.

    Scoping arrives purely as pattern text — the router composes and
    residuates scope upstream; no path channel crosses this seam. One
    refusable pattern refuses the whole call before any row is touched.
    Exclusions never prefilter in SQL — an over-approximating ``NOT
    LIKE`` would wrongly exclude, the forbidden false negative — so
    ``globs_not`` and ``ext_not`` gate candidates beside the compiled
    authority; ``kind`` is an exact fact and rides inside every arm.
    """
    for pattern in (*patterns, *globs_not):
        defect = glob_defect(pattern)
        if defect is not None:
            error = ResultError(kind=VFSErrorKind.invalid, message=f"glob pattern {pattern!r}: {defect}")
            return Result(ops=("glob",), errors=[error])
    fetched = effective_columns(columns, content=False)
    entry = tables.entry
    wanted = frozenset(e.lstrip(".").lower() for e in ext)
    unwanted = frozenset(e.lstrip(".").lower() for e in ext_not)
    matched: dict[str, RowMapping] = {}
    live = list(dict.fromkeys(patterns))
    gates = [compile_filter(pattern, ext) for pattern in live]
    not_gates = [compile_filter(pattern, ()) for pattern in dict.fromkeys(globs_not)]
    built = (pattern_arm(entry, glob, wanted, membership_budget, kind=kind) for glob in gates)
    arms = [arm for arm in built if arm is not None]
    ext_binds = len(wanted) if wanted and "" not in wanted and len(wanted) <= membership_budget else 0
    chunk = arm_budget(profile, parameter_budget, ARM_FIXED_BINDS + ext_binds)
    for mapping in await _pattern_candidates(session, entry, chunk, arms, fetched):
        path = Path(mapping["path"])
        if not any(glob.matches(path) for glob in gates):
            continue
        if any(gate.matches(path) for gate in not_gates):
            continue
        if unwanted and (extract_extension(path) or "") in unwanted:
            continue
        matched.setdefault(mapping["path"], mapping)
    rows = [_observe(matched[path], fetched) for path in sorted(matched)]
    if max_count is not None:
        rows = rows[:max_count]
    return Result(ops=("glob",), observations=rows)


# ---------------------------------------------------------------------------
# Pattern-arm machinery — shared by the glob fan and grep's scan side
# ---------------------------------------------------------------------------


def pattern_arm(
    entry: Table, glob: GlobFilter, wanted: frozenset[str], membership_budget: int, *, kind: str | None = None
) -> ColumnElement[bool] | None:
    """One pattern's self-contained OR-arm, or ``None`` when provably empty.

    Every fact rides inside the arm — the root-row exclusion, the
    prefilter LIKE, both ext facts, the meta liveness scope, the kind
    fact — because the fan's plan survives only as a pure OR of
    self-contained arms: one conjunct beside the fan demotes every
    engine's multi-index OR to a scan. The caller's ext membership
    stands down when the empty extension (stored NULL) is wanted or
    the set outgrows one chunk; a derived ext contradicting the
    caller's set makes the arm dead.
    """
    subject = entry.c.path if glob.by_path else entry.c.name
    like = _glob_like(glob.pattern)
    prefilter = like if like is not None else escape_like(_literal_prefix(glob.pattern)) + "%"
    terms: list[ColumnElement[bool]] = [entry.c.path != "/", subject.like(prefilter, escape=LIKE_ESCAPE)]
    if kind is not None:
        terms.append(entry.c.kind == kind)
    if wanted and "" not in wanted and len(wanted) <= membership_budget:
        terms.append(entry.c.ext.in_(sorted(wanted)))
    derived = derive_ext(glob.pattern)
    if derived is not None:
        if wanted and "" not in wanted and derived.ext not in wanted:
            return None
        # The dotfile arm rescues names like ".txt", whose stored ext is NULL.
        terms.append(or_(entry.c.ext == derived.ext, entry.c.name == derived.dot_suffix))
    terms.extend(liveness_filters(entry, include_meta=meta_scoped(glob.pattern)))
    return and_(*terms)


def meta_scoped(pattern: str) -> bool:
    """Whether the pattern's literal prefix addresses the meta subtree.

    Only a literal ``/.vfs`` head lifts the exclusion — a wildcard-headed
    prefix (``/.v*``, ``/.vfs*``) never does.
    """
    return pattern == METADATA_ROOT or pattern.startswith(METADATA_ROOT + "/")


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


async def _pattern_candidates(
    session: AsyncSession,
    entry: Table,
    chunk_size: int,
    arms: Sequence[ColumnElement[bool]],
    fetched: frozenset[str],
) -> list[RowMapping]:
    """Prefiltered candidates from the chunked OR fan, in path order.

    Each chunk's WHERE is the pure OR of its arms — nothing rides
    beside the fan. Overlapping arms yield a row once per statement;
    the merge dict dedups across chunks, and one Python sort restores
    path order — codepoint order equals the binary-collated byte order.
    """
    columns = _entry_columns(entry, fetched)
    merged: dict[str, RowMapping] = {}
    for chunk in chunked(list(arms), chunk_size):
        result = await session.execute(select(*columns).where(or_(*chunk)))
        merged.update({mapping["path"]: mapping for mapping in result.mappings()})
    return [merged[path] for path in sorted(merged)]


async def _children_by_parent(
    session: AsyncSession,
    entry: Table,
    membership_budget: int,
    directories: Sequence[Path],
    found: dict[str, RowMapping],
    fetched: frozenset[str],
) -> dict[str, list[Observation]]:
    """Chunked ``parent_id IN`` children selects, regrouped per parent.

    One scope per liveness class (meta-addressed targets see meta rows).
    Chunks partition parents, so each parent's children arrive whole and
    name-ordered; the dict preserves that order per parent.
    """
    children: dict[str, list[Observation]] = {}
    for include_meta in (False, True):
        scope = sorted({found[target]["entry_id"] for target in directories if target.is_meta == include_meta})
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
    """Superset LIKE translation of the glob; ``None`` when inexpressible.

    A whole ``**`` component fuses with its trailing separator into one
    ``%`` (zero-or-more components — a separate ``/`` would demand a
    depth the glob does not); ``*`` -> ``%`` and ``?`` -> ``_`` stay
    deliberately loose (both cross ``/``). ``[`` classes and
    mid-component ``**`` are inexpressible: callers fall back to the
    escaped literal-prefix LIKE.
    """
    if "[" in pattern:
        return None
    segments = pattern.split("/")
    if any("**" in segment and segment != "**" for segment in segments):
        return None
    out: list[str] = []
    for index, segment in enumerate(segments):
        if segment == "**":
            out.append("%")
            continue  # fuse: the following separator lives inside the %
        for ch in segment:
            if ch in _GLOB_TRANSLATED:
                out.append("%" if ch == "*" else "_")
            elif ch in ("%", "_", LIKE_ESCAPE):
                out.append(LIKE_ESCAPE + ch)
            else:
                out.append(ch)
        if index < len(segments) - 1:
            out.append("/")
    return "".join(out)


def _literal_prefix(pattern: str) -> str:
    index = min((i for i, ch in enumerate(pattern) if ch in "*?["), default=len(pattern))
    return pattern[:index]
