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

from typing import TYPE_CHECKING, Any, Final, NamedTuple

from sqlalchemy import LargeBinary, and_, case, cast, func, or_, select

from vfs.models import CONTENT_KINDS, Observation
from vfs.paths import Path, _under_meta_root, normalize_ext_channel
from vfs.pattern_matching import (
    ROW_GATE_FIELDS,
    GlobFilter,
    PatternError,
    compile_filter,
    derive_ext,
    expand_channel,
    passes_row_filters,
)
from vfs.results import Result, ResultError, VFSErrorKind, wrong_kind
from vfs.storage.backends.database.descent import (
    LIKE_ESCAPE,
    classify_miss,
    descendant_filter,
    escape_like,
    liveness_filters,
    miss_errors,
    rows_by_path,
    targets_with_ancestors,
)
from vfs.storage.backends.database.dialects import arm_budget, chunked
from vfs.storage.backends.database.membership import membership

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy import Column, ColumnElement, FromClause, Select, Table
    from sqlalchemy.engine import RowMapping
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models.rows import EntryId, VFSTables
    from vfs.pattern_matching import Body
    from vfs.storage.backends.database.dialects import DialectProfile
    from vfs.storage.backends.database.indexing import Epoch
    from vfs.storage.backends.database.rights import Visibility

# Observation fields served directly by entries-table columns (the two
# vocabularies share these names by construction). A file's current version
# label IS its version (one per-entry sequence); version_number surfaces
# only on Version rows, never from the entries table.
ENTRY_OBSERVATION_FIELDS: Final[frozenset[str]] = frozenset(
    {"path", "kind", "version", "content_hash", "mime_type", "size_bytes"} | {"created_at", "updated_at"},
)

# Identity fields every observation carries regardless of projection.
ALWAYS_ON_FIELDS: Final[frozenset[str]] = frozenset({"path", "kind", "version"})

# What a directory shows when it is only on the road to a visible row:
# its name and kind, never a fact that moves when hidden children do.
ROAD_FIELDS: Final[frozenset[str]] = frozenset({"path", "kind"})

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
    profile: DialectProfile,
    membership_budget: int,
    targets: Sequence[Path],
    columns: frozenset[str] | None,
    view: Visibility | None = None,
) -> Result:
    fetched = effective_columns(columns, content=True)
    rows, errors = await _point_rows(
        session, tables, profile, membership_budget, targets, fetched, content_only=True, view=view
    )
    return Result(ops=("read",), observations=rows, errors=errors)


async def stat_rows(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    targets: Sequence[Path],
    columns: frozenset[str] | None,
    view: Visibility | None = None,
) -> Result:
    fetched = effective_columns(columns, content=False)
    rows, errors = await _point_rows(
        session, tables, profile, membership_budget, targets, fetched, content_only=False, view=view
    )
    return Result(ops=("stat",), observations=rows, errors=errors)


# ---------------------------------------------------------------------------
# Listings — ls and tree
# ---------------------------------------------------------------------------


async def ls_rows(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    targets: Sequence[Path],
    columns: frozenset[str] | None,
    view: Visibility | None = None,
) -> Result:
    """Each directory target's children, each file target itself.

    Under a partial view a road directory lists like any directory, and
    a hidden child directory shows as a bare name only when it is itself
    on the road; a hidden file never shows.
    """
    fetched = effective_columns(columns, content=False)
    found = await _mappings_by_path(
        session, tables, profile, membership_budget, targets, fetched, with_entry_id=True, with_owner=view is not None
    )
    shown, road, missing = await _screen(session, tables, profile, membership_budget, targets, found, view)
    directories = [t for t in targets if t in road or ((f := shown.get(t)) is not None and f["kind"] == "directory")]
    children = await _children_by_parent(
        session, tables.entry, profile, membership_budget, directories, found, fetched, view=view
    )
    rows: list[Observation] = []
    errors: list[ResultError] = []
    for target in targets:
        mapping = shown.get(target)
        if mapping is None and target not in road:
            errors.append(missing[target])
        elif mapping is not None and mapping["kind"] != "directory":
            rows.append(_observe(mapping, fetched))
        else:
            rows.extend(children.get(found[target]["entry_id"], ()))
    return Result(ops=("ls",), observations=rows, errors=errors)


async def tree_rows(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    path: Path,
    max_depth: int | None,
    columns: frozenset[str] | None,
    view: Visibility | None = None,
) -> Result:
    """Every row beneath *path*, in path order, to *max_depth* levels.

    Under a partial view the subtree read carries the visibility clauses
    (once per clause, merged), every row still passes the view, and each
    visible row's hidden ancestors inside the tree show as bare names —
    the road down to it.
    """
    fetched = effective_columns(columns, content=False)
    entry = tables.entry
    found = await _mappings_by_path(
        session, tables, profile, membership_budget, [path], fetched, with_entry_id=False, with_owner=view is not None
    )
    shown, road, missing = await _screen(session, tables, profile, membership_budget, [path], found, view)
    target = shown.get(path)
    if target is None and path not in road:
        return Result(ops=("tree",), errors=[missing[path]])
    if target is not None and target["kind"] != "directory":
        return Result(ops=("tree",), observations=[_observe(target, fetched)])
    wanted = fetched | ({"owner_id"} if view is not None else frozenset())
    stmt = (
        select(*_entry_columns(entry, wanted))
        .where(
            descendant_filter(entry, str(path), profile),
            *liveness_filters(entry, profile, include_meta=path.is_meta),
        )
        .order_by(entry.c.path)
    )
    if max_depth is not None:
        stmt = stmt.where(_slash_count(entry) <= path.depth + max_depth)
    if view is None:
        rows = [_observe(mapping, fetched) for mapping in (await session.execute(stmt)).mappings()]
        return Result(ops=("tree",), observations=rows)
    visible = await _visible_rows(session, stmt, view)
    bare = {
        ancestor
        for mapping_path in visible
        for ancestor in _ancestors_below(mapping_path, str(path))
        if ancestor not in visible
    }
    observed = {p: _observe(m, fetched) for p, m in visible.items()} | {p: road_observation(p) for p in bare}
    return Result(ops=("tree",), observations=[observed[p] for p in sorted(observed)])


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
    view: Visibility | None = None,
) -> Result:
    """Rows matching **any** pattern, one snapshot, statements chunked by budget.

    Scoping arrives purely as pattern text — the router composes and
    residuates scope upstream; no path channel crosses this seam. The
    seam admits the full pattern language through the shared admission
    call (a brace pattern arriving unexpanded alternates, never a
    silent literal), and one refusable pattern refuses the whole call
    before any row is touched. Exclusions never prefilter in SQL — an over-approximating ``NOT
    LIKE`` would wrongly exclude, the forbidden false negative — so
    ``globs_not`` and ``ext_not`` gate candidates beside the compiled
    authority; ``kind`` is an exact fact and rides inside every arm. Under
    a partial *view* each candidate passes the view in app code — a clause
    beside the fan would demote its plan — and a hidden directory matches
    as a bare name only when it is on the road.
    """
    try:
        live = expand_channel("pattern", patterns)
        exclusions = expand_channel("globs_not", globs_not)
    except PatternError as exc:
        return Result(ops=("glob",), errors=[ResultError(kind=VFSErrorKind.invalid, message=str(exc))])
    fetched = effective_columns(columns, content=False)
    entry = tables.entry
    wanted = normalize_ext_channel(ext)
    unwanted = normalize_ext_channel(ext_not)
    matched: dict[str, RowMapping] = {}
    gates = [compile_filter(pattern, ext) for pattern in live]
    not_gates = [compile_filter(pattern, ()) for pattern in exclusions]
    built = (pattern_arm(entry, glob, wanted, profile, membership_budget, kind=kind) for glob in gates)
    arms = [arm for arm in built if arm is not None]
    ride = ext_membership(entry, wanted, membership_budget)
    chunk = arm_budget(profile, parameter_budget, ARM_FIXED_BINDS + ride.binds)
    # name and ext ride for the row-fact gate; the observation mask stays
    # the caller's `fetched`, so a narrow columns= never leaks the ride.
    queried = fetched | ROW_GATE_FIELDS | ({"owner_id"} if view is not None else frozenset())
    hidden: list[str] = []
    for mapping in await _pattern_candidates(session, entry, chunk, arms, queried):
        # Wanted-ext admission rides inside the gates (compiled with *ext*).
        path, name, row_ext = mapping["path"], mapping["name"], mapping["ext"]
        if not passes_row_filters(path, name, row_ext, gates, not_gates, frozenset(), unwanted):
            continue
        if view is None or view.admits(mapping):
            matched.setdefault(mapping["path"], mapping)
        elif mapping["kind"] == "directory":
            hidden.append(path)
    observed = {path: _observe(mapping, fetched) for path, mapping in matched.items()}
    if hidden and view is not None:
        observed |= {path: road_observation(path) for path in await view.road(session, hidden)}
    rows = [observed[path] for path in sorted(observed)]
    if max_count is not None:
        rows = rows[:max_count]
    return Result(ops=("glob",), observations=rows)


# ---------------------------------------------------------------------------
# Pattern-arm machinery — shared by the glob fan and grep's scan side
# ---------------------------------------------------------------------------


class ExtMembership(NamedTuple):
    """The rideable half of the caller's ext facts: predicate paired with its binds."""

    predicate: ColumnElement[bool] | None
    binds: int


def ext_membership(entry: Table, wanted: frozenset[str], membership_budget: int) -> ExtMembership:
    """The wanted-ext set as one SQL membership fact, or ``(None, 0)``.

    Membership rides only when every member is a stored value — the
    empty extension is stored ``NULL``, which ``IN`` can never admit —
    and the set fits one membership chunk. Predicate and bind count
    travel together so the fan's budget arithmetic can never drift from
    the SQL the arms actually carry.
    """
    if wanted and "" not in wanted and len(wanted) <= membership_budget:
        return ExtMembership(entry.c.ext.in_(sorted(wanted)), len(wanted))
    return ExtMembership(None, 0)


class KindMembership(NamedTuple):
    """The content-kind gate: predicate paired with its bind charge."""

    predicate: ColumnElement[bool]
    binds: int


def kind_membership(entry: Table) -> KindMembership:
    """The content-bearing kinds as one sorted SQL membership fact.

    The one spelling every content-scoped statement rides — predicate
    and bind charge travel together, exactly as :func:`ext_membership`,
    so no consumer re-spells the set or re-counts its price.
    """
    return KindMembership(entry.c.kind.in_(sorted(CONTENT_KINDS)), len(CONTENT_KINDS))


# ---------------------------------------------------------------------------
# The index-side reads every content search shares
# ---------------------------------------------------------------------------


async def pointer_with_overlay(session: AsyncSession, tables: VFSTables) -> tuple[Epoch | None, bool]:
    """The epoch pointer plus an overlay-emptiness verdict, one statement.

    Issued twice on the skip path, once when the preamble verdict is
    non-empty: the preamble read is advisory (non-empty settles it —
    the scan tier will run, and no second combined read is issued),
    while the authoritative post-fetch read's empty verdict alone
    permits skipping the scan — with results identical to scanning —
    and doubles as the epoch recheck. The predicate stays ORM-built — the
    negation renders as an inline literal on every dialect, which keeps
    the seek on the composite (encoded, kind) index reachable; the CASE
    wrapper is what lets engines without boolean select-list expressions
    (SQL Server) carry the EXISTS.
    """
    entry = tables.entry
    pending = select(entry.c.id).where(~entry.c.encoded, kind_membership(entry).predicate).exists()
    stmt = select(tables.meta.c.current_gram_epoch, case((pending, 1), else_=0)).where(tables.meta.c.id == 1)
    row = (await session.execute(stmt)).one_or_none()
    if row is None:
        return None, False
    pointer, has_pending = row
    return pointer, not has_pending


async def content_for_entries(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    entry_ids: Sequence[EntryId],
) -> dict[EntryId, Body]:
    """``entry_id → full body`` for one batch of the scan side.

    Where the profile declares ``content_bytes`` the body comes back as
    the column's UTF-8 bytes — the driver skips its decode and the
    consumer takes them as-is; only rows that answer ever decode.
    """
    content = tables.content
    body = cast(content.c.content, LargeBinary).label("content") if profile.content_bytes else content.c.content
    out: dict[EntryId, Body] = {}
    for chunk in chunked(sorted(set(entry_ids)), membership_budget):
        stmt = select(content.c.entry_id, body).where(membership(content.c.entry_id, chunk, profile))
        out.update({row.entry_id: row.content for row in await session.execute(stmt)})
    return out


def pattern_arm(
    entry: Table,
    glob: GlobFilter,
    wanted: frozenset[str],
    profile: DialectProfile,
    membership_budget: int,
    *,
    kind: str | None = None,
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
    prefilter = like if like is not None else escape_like(_literal_prefix(glob.pattern), profile) + "%"
    terms: list[ColumnElement[bool]] = [entry.c.path != "/", subject.like(prefilter, escape=LIKE_ESCAPE)]
    if kind is not None:
        terms.append(entry.c.kind == kind)
    ride = ext_membership(entry, wanted, membership_budget)
    if ride.predicate is not None:
        terms.append(ride.predicate)
    derived = derive_ext(glob.pattern)
    if derived is not None:
        if wanted and "" not in wanted and derived.ext not in wanted:
            return None
        # The dotfile arm rescues names like ".txt", whose stored ext is NULL.
        terms.append(or_(entry.c.ext == derived.ext, entry.c.name == derived.dot_suffix))
    terms.extend(liveness_filters(entry, profile, include_meta=meta_scoped(glob.pattern)))
    return and_(*terms)


def meta_scoped(pattern: str) -> bool:
    """Whether the pattern's own head literally names the meta subtree.

    Only a whole literal ``/.vfs`` head lifts the exclusion — a
    wildcard-headed prefix (``/.v*``, ``/.vfs*``) never does, even
    though its extracted literal prefix reaches the meta root. The
    string law is the path layer's: a pattern with that head confines
    itself exactly as a meta path does.
    """
    return _under_meta_root(pattern)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _point_rows(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    targets: Sequence[Path],
    fetched: frozenset[str],
    *,
    content_only: bool,
    view: Visibility | None = None,
) -> tuple[list[Observation], list[ResultError]]:
    """Fetch, classify, and observe *targets* one row at a time, in order.

    A road directory answers as a bare name to ``stat`` and as a
    directory to ``read`` (``wrong_kind``, as any directory would).
    """
    found = await _mappings_by_path(
        session, tables, profile, membership_budget, targets, fetched, with_entry_id=False, with_owner=view is not None
    )
    shown, road, missing = await _screen(session, tables, profile, membership_budget, targets, found, view)
    rows: list[Observation] = []
    errors: list[ResultError] = []
    for target in targets:
        mapping = shown.get(target)
        if mapping is None:
            if target in road:
                if content_only:
                    errors.append(wrong_kind("directory", target))
                else:
                    rows.append(road_observation(target))
                continue
            errors.append(missing[target])
            continue
        kind = mapping["kind"]
        if content_only and kind not in CONTENT_KINDS:
            errors.append(wrong_kind(kind, target))
            continue
        rows.append(_observe(mapping, fetched))
    return rows, errors


def road_observation(path: str) -> Observation:
    """A directory shown only because a visible row lies beneath it: path and kind."""
    return Observation.model_validate({"path": Path._brand(path), "kind": "directory", "populated": ROAD_FIELDS})


async def _screen(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    targets: Sequence[Path],
    found: dict[str, RowMapping],
    view: Visibility | None,
) -> tuple[dict[str, RowMapping], set[str], dict[Path, ResultError]]:
    """Split fetched targets into shown rows and road directories, and classify the rest.

    With no view every found row shows and misses classify as they
    always have. Under a view a hidden row is a miss, and the descent
    ladder runs against what the view shows, so a hidden ancestor reads
    exactly as a missing one.
    """
    if view is None:
        return found, set(), await miss_errors(session, tables.entry, targets, found, profile, membership_budget)
    shown = {path: mapping for path, mapping in found.items() if view.admits(mapping)}
    hidden = [path for path, mapping in found.items() if path not in shown and mapping["kind"] == "directory"]
    road = await view.road(session, hidden)
    misses = [target for target in dict.fromkeys(targets) if str(target) not in shown and str(target) not in road]
    if not misses:
        return shown, road, {}
    entry = tables.entry
    columns = [entry.c.path, entry.c.kind, entry.c.owner_id]
    chain = await rows_by_path(session, entry, targets_with_ancestors(misses), columns, profile, membership_budget)
    seen = await view.seen_kinds(session, chain)
    return shown, road, {target: classify_miss(target, seen) for target in misses}


async def _visible_rows(session: AsyncSession, stmt: Select[Any], view: Visibility) -> dict[str, RowMapping]:
    """*stmt* run once per visibility clause, merged by path, every row passing the view."""
    clauses = view.clauses()
    statements = [stmt] if clauses is None else [stmt.where(clause.predicate) for clause in clauses]
    merged: dict[str, RowMapping] = {}
    for statement in statements:
        for mapping in (await session.execute(statement)).mappings():
            if view.admits(mapping):
                merged[mapping["path"]] = mapping
    return merged


def _ancestors_below(path: str, root: str) -> list[str]:
    """*path*'s proper ancestors strictly beneath *root*."""
    out: list[str] = []
    node = path.rsplit("/", 1)[0] or "/"
    while node != root and node != "/" and (root == "/" or node.startswith(root + "/")):
        out.append(node)
        node = node.rsplit("/", 1)[0] or "/"
    return out


async def _mappings_by_path(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    targets: Sequence[Path],
    fetched: frozenset[str],
    *,
    with_entry_id: bool,
    with_owner: bool = False,
) -> dict[str, RowMapping]:
    """One bounded fetch for the batch, keyed by the stored path string."""
    columns, source = _entry_projection(tables, fetched, with_entry_id=with_entry_id)
    if with_owner:
        columns = [*columns, tables.entry.c.owner_id]
    paths = (str(target) for target in targets)
    return await rows_by_path(session, tables.entry, paths, columns, profile, membership_budget, source=source)


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
    profile: DialectProfile,
    membership_budget: int,
    directories: Sequence[Path],
    found: dict[str, RowMapping],
    fetched: frozenset[str],
    *,
    view: Visibility | None = None,
) -> dict[str, list[Observation]]:
    """Chunked ``parent_id IN`` children selects, regrouped per parent.

    One scope per liveness class (meta-addressed targets see meta rows).
    Chunks partition parents, so each parent's children arrive whole and
    name-ordered; the dict preserves that order per parent. Under a view
    a hidden child directory stays in its place as a bare name when it
    is on the road, and every other hidden child drops.
    """
    listed: dict[str, list[RowMapping]] = {}
    wanted = fetched | ({"owner_id"} if view is not None else frozenset())
    for include_meta in (False, True):
        scope = sorted({found[target]["entry_id"] for target in directories if target.is_meta == include_meta})
        for chunk in chunked(scope, membership_budget):
            stmt = (
                select(entry.c.parent_id, *_entry_columns(entry, wanted))
                .where(
                    membership(entry.c.parent_id, chunk, profile),
                    *liveness_filters(entry, profile, include_meta=include_meta),
                )
                .order_by(entry.c.parent_id, entry.c.name)
            )
            for mapping in (await session.execute(stmt)).mappings():
                listed.setdefault(mapping["parent_id"], []).append(mapping)
    if view is None:
        return {parent: [_observe(m, fetched) for m in rows] for parent, rows in listed.items()}
    hidden = [m["path"] for rows in listed.values() for m in rows if not view.admits(m) and m["kind"] == "directory"]
    road = await view.road(session, hidden)
    children: dict[str, list[Observation]] = {}
    for parent, rows in listed.items():
        for mapping in rows:
            if view.admits(mapping):
                children.setdefault(parent, []).append(_observe(mapping, fetched))
            elif mapping["path"] in road:
                children.setdefault(parent, []).append(road_observation(mapping["path"]))
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
    # Stored paths are canonical by invariant: re-brand, never re-gate.
    values: dict[str, object] = {field: mapping[field] for field in fetched}
    values["path"] = Path._brand(mapping["path"])
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
