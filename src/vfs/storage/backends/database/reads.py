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

A deleted row stays at its path with a tombstone, and every read here
reads around it: a point read classifies a tombstoned row as absent
with the trashed hint, and every listing carries the liveness term.
The ``/.vfs/trash`` head is a view over the tombstoned rows: a target
or pattern under it is stripped to the path it names, the liveness
term flips, and each row answers at its own path with ``deleted_at``
projected. ``/.vfs/trash`` itself is a synthesized directory, never a
stored row — ``ls`` of it lists the tombstoned roots at every depth.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final, NamedTuple

from sqlalchemy import LargeBinary, and_, case, cast, func, or_, select

from vfs.models import CONTENT_KINDS, RENDERED_STATUSES, Observation
from vfs.models.media import FAILURE_STATUSES
from vfs.paths import (
    METADATA_ROOT,
    ROOT,
    TRASH_ROOT,
    Address,
    Path,
    _under_meta_root,
    address_of,
    normalize_ext_channel,
)
from vfs.pattern_matching import (
    GLOB_CHANNEL_LABELS,
    ROW_GATE_FIELDS,
    GlobFilter,
    PatternError,
    compile_filter,
    derive_ext,
    expand_channel,
    passes_row_filters,
)
from vfs.results import ErrorKind, Result, ResultError, Severity, classified, wrong_kind
from vfs.storage.backends.database.descent import (
    LIKE_ESCAPE,
    classify_miss,
    descendant_filter,
    escape_like,
    liveness_filters,
    rows_by_path,
    targets_with_ancestors,
    tombstoned_roots,
)
from vfs.storage.backends.database.dialects import arm_budget, chunked
from vfs.storage.backends.database.membership import membership
from vfs.storage.backends.database.rights import RIGHTS_FIELDS, denied

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy import Column, ColumnElement, FromClause, Select, Table
    from sqlalchemy.engine import RowMapping
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models.rows import EntryId, VFSTables
    from vfs.pattern_matching import Body, GlobChannel
    from vfs.storage.backends.database.dialects import DialectProfile
    from vfs.storage.backends.database.indexing import Epoch
    from vfs.storage.backends.database.rights import Visibility

# Observation fields served directly by entries-table columns (the two
# vocabularies share these names by construction). A file's current version
# label IS its version (one per-entry sequence); version_number surfaces
# only on Version rows, never from the entries table.
ENTRY_OBSERVATION_FIELDS: Final[frozenset[str]] = frozenset(
    {"path", "kind", "version", "content_hash", "mime_type", "size_bytes"}
    | {"source", "render_status", "created_at", "updated_at", "deleted_at"},
)

# The Observation fields homed in a body table, served only by the verbs
# that carry bodies: ``content`` by default, ``data`` only when projected.
BODY_FIELDS: Final[frozenset[str]] = frozenset({"content", "data"})

# Identity fields every observation carries regardless of projection.
ALWAYS_ON_FIELDS: Final[frozenset[str]] = frozenset({"path", "kind", "version"})

# What a row shows to a caller holding ``list`` on it — a granted ``list``
# row or a directory only on the road: its name and kind, nothing else.
LIST_FIELDS: Final[frozenset[str]] = frozenset({"path", "kind"})
ROAD_FIELDS: Final = LIST_FIELDS

# Glob character classes have no LIKE equivalent; those patterns fall
# back to a literal-prefix prefilter with the compiled glob as the filter.
_GLOB_TRANSLATED: Final[frozenset[str]] = frozenset("*?")

# The trash view's heads as the descent ladder sees them: synthesized
# directories, never stored rows, so neither is ever the missing component.
_VIEW_HEADS: Final[dict[str, str]] = {METADATA_ROOT: "directory", TRASH_ROOT: "directory"}


# ---------------------------------------------------------------------------
# Projection
# ---------------------------------------------------------------------------


def effective_columns(columns: frozenset[str] | None, *, content: bool) -> frozenset[str]:
    """The Observation fields this op fetches — also the populated mask.

    ``None`` means no push-down: every entry-backed field (plus content
    when the verb carries it; never the bytes, which only an explicit
    projection fetches). A concrete projection narrows to the
    requested ∩ servable fields, identity fields always on; a requested
    field with no backing column yet is simply not in the mask.
    """
    if columns is None:
        fetched = set(ENTRY_OBSERVATION_FIELDS)
        if content:
            fetched.add("content")
        return frozenset(fetched)
    fetched = set((columns & ENTRY_OBSERVATION_FIELDS) | ALWAYS_ON_FIELDS)
    if content:
        fetched |= columns & BODY_FIELDS
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
    if "content" in fetched:
        rows, notes = render_notes(rows)
        errors = [*errors, *notes]
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

    Under a partial view a road directory lists like any directory, a
    row the caller holds only ``list`` on shows bare, and a hidden child
    directory shows as a bare name only when it is itself on the road; a
    hidden file never shows.
    """
    fetched = effective_columns(columns, content=False)
    found = await _mappings_by_path(
        session, tables, profile, membership_budget, targets, fetched, with_entry_id=True, judged=view is not None
    )
    shown, road, missing = await _screen(session, tables, profile, membership_budget, targets, found, view)
    directories = [t for t in targets if t in road or ((f := shown.get(t)) is not None and f["kind"] == "directory")]
    children = await _children_by_parent(
        session, tables.entry, profile, membership_budget, directories, found.by_target, fetched, view=view
    )
    roots: list[Observation] | None = None
    rows: list[Observation] = []
    errors: list[ResultError] = []
    for target in targets:
        mapping = shown.get(target)
        if target == TRASH_ROOT:
            if roots is None:
                roots = await _trash_roots(session, tables, profile, fetched, view)
            rows.extend(roots)
        elif mapping is None and target not in road:
            errors.append(missing[target])
        elif mapping is not None and mapping["kind"] != "directory":
            rows.append(_observe_for(view, mapping, fetched))
        else:
            listed = list(children.get(found.by_target[target]["entry_id"], ()))
            if target == METADATA_ROOT:
                listed = _with_trash_view(listed)
            rows.extend(listed)
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
    at ``list`` (once per clause, merged), every row still passes the
    view — bare where the caller holds only ``list`` — and each named
    row's hidden ancestors inside the tree show as bare names, the road
    down to it.
    """
    fetched = effective_columns(columns, content=False)
    entry = tables.entry
    found = await _mappings_by_path(
        session, tables, profile, membership_budget, [path], fetched, with_entry_id=False, judged=view is not None
    )
    shown, road, missing = await _screen(session, tables, profile, membership_budget, [path], found, view)
    target = shown.get(path)
    if target is None and path not in road and path != TRASH_ROOT:
        return Result(ops=("tree",), errors=[missing[path]])
    if target is not None and target["kind"] != "directory":
        return Result(ops=("tree",), observations=[_observe_for(view, target, fetched)])
    address = address_of(str(path))
    wanted = fetched | {"deleted_at"} | (RIGHTS_FIELDS if view is not None else frozenset())
    stmt = (
        select(*_entry_columns(entry, wanted))
        .where(
            descendant_filter(entry, address.stored, profile),
            *liveness_filters(entry, profile, include_meta=address.meta, trashed=address.trashed),
        )
        .order_by(entry.c.path)
    )
    if max_depth is not None:
        stmt = stmt.where(_slash_count(entry) <= _depth(address.stored) + max_depth)
    if view is None:
        rows = [_observe(mapping, fetched) for mapping in (await session.execute(stmt)).mappings()]
        return Result(ops=("tree",), observations=rows)
    visible = await _visible_rows(session, stmt, view, address.stored)
    bare = {
        ancestor
        for mapping_path in visible
        for ancestor in _ancestors_below(mapping_path, address.stored)
        if ancestor not in visible
    }
    observed = {p: _observe_for(view, m, fetched) for p, m in visible.items()}
    observed |= {p: road_observation(p) for p in bare}
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
    beside the fan would demote its plan — bare where the caller holds
    only ``list``, and a hidden directory matches as a bare name only
    when it is on the road.
    """
    try:
        addresses = address_channel("pattern", patterns)
        excluded = address_channel("globs_not", globs_not)
    except PatternError as exc:
        return Result(ops=("glob",), errors=[classified(ErrorKind.invalid, detail=str(exc))])
    fetched = effective_columns(columns, content=False)
    entry = tables.entry
    wanted = normalize_ext_channel(ext)
    unwanted = normalize_ext_channel(ext_not)
    matched: dict[str, RowMapping] = {}
    # A pattern under the trash head gates the tombstoned rows at the paths
    # beneath it, every other the live rows; exclusions side the same way.
    gates = [compile_filter(address.stored, ext) for address in addresses]
    sided: dict[bool, list[GlobFilter]] = {False: [], True: []}
    for gate, address in zip(gates, addresses, strict=True):
        sided[address.trashed].append(gate)
    not_gates: dict[bool, list[GlobFilter]] = {False: [], True: []}
    for address in excluded:
        not_gates[address.trashed].append(compile_filter(address.stored, ()))
    built = (
        pattern_arm(entry, glob, wanted, profile, membership_budget, kind=kind, trashed=address.trashed)
        for glob, address in zip(gates, addresses, strict=True)
    )
    arms = [arm for arm in built if arm is not None]
    ride = ext_membership(entry, wanted, membership_budget)
    chunk = arm_budget(profile, parameter_budget, ARM_FIXED_BINDS + ride.binds)
    # name and ext ride for the row-fact gate; the observation mask stays
    # the caller's `fetched`, so a narrow columns= never leaks the ride.
    queried = fetched | ROW_GATE_FIELDS | {"deleted_at"} | (RIGHTS_FIELDS if view is not None else frozenset())
    hidden: dict[bool, list[str]] = {False: [], True: []}
    for mapping in await _pattern_candidates(session, entry, chunk, arms, queried):
        # Wanted-ext admission rides inside the gates (compiled with *ext*).
        path, name, row_ext = mapping["path"], mapping["name"], mapping["ext"]
        tombstoned = mapping["deleted_at"] is not None
        side = sided[tombstoned]
        if not side or not passes_row_filters(path, name, row_ext, side, not_gates[tombstoned], frozenset(), unwanted):
            continue
        if view is None or view.shows(mapping):
            matched.setdefault(mapping["path"], mapping)
        elif mapping["kind"] == "directory":
            hidden[tombstoned].append(path)
    observed = {path: _observe_for(view, mapping, fetched) for path, mapping in matched.items()}
    if view is not None:
        for trashed, candidates in hidden.items():
            if candidates:
                road = await view.road(session, candidates, trashed=trashed)
                observed |= {path: road_observation(path) for path in road}
    rows = [observed[path] for path in sorted(observed)]
    if max_count is not None:
        rows = rows[:max_count]
    return Result(ops=("glob",), observations=rows)


def address_channel(channel: GlobChannel, patterns: Sequence[str]) -> tuple[Address, ...]:
    """One glob channel's arms, each addressed to the side of the tombstone it searches.

    The one pattern-side resolution of the trash view, shared by glob,
    grep and glean: the channel is admitted whole, then every arm under
    the head is stripped to the pattern it names. The bare head is a
    directory, not a pattern — it is refused as the bare root is, naming
    the channel, so no verb ever compiles the stripped ``/``.
    """
    addresses: list[Address] = []
    for pattern in expand_channel(channel, patterns):
        address = address_of(pattern)
        if address.trashed and address.stored == "/":
            label = GLOB_CHANNEL_LABELS[channel]
            detail = f"the view's head is a directory, not a pattern; scope beneath it with {TRASH_ROOT + '/**'!r}"
            raise PatternError(f"{label} {pattern!r}: {detail}")
        addresses.append(address)
    return tuple(addresses)


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
    trashed: bool = False,
) -> ColumnElement[bool] | None:
    """One pattern's self-contained OR-arm, or ``None`` when provably empty.

    Every fact rides inside the arm — the root-row exclusion, the
    prefilter LIKE, both ext facts, the liveness scope (the tombstone
    term, flipped under the trash view by *trashed*, and the meta
    exclusion), the kind fact — because the fan's plan survives only as
    a pure OR of self-contained arms: one conjunct beside the fan
    demotes every engine's multi-index OR to a scan. The caller's ext
    membership stands down when the empty extension (stored NULL) is
    wanted or the set outgrows one chunk; a derived ext contradicting
    the caller's set makes the arm dead.
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
    terms.extend(liveness_filters(entry, profile, include_meta=meta_scoped(glob.pattern), trashed=trashed))
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
    directory to ``read`` (``wrong_kind``, as any directory would); a
    row the caller holds only ``list`` on answers bare to ``stat`` and
    ``permission_denied`` to ``read``.
    """
    found = await _mappings_by_path(
        session, tables, profile, membership_budget, targets, fetched, with_entry_id=False, judged=view is not None
    )
    shown, road, missing = await _screen(session, tables, profile, membership_budget, targets, found, view)
    rows: list[Observation] = []
    errors: list[ResultError] = []
    for target in targets:
        mapping = shown.get(target)
        if mapping is None:
            # The trash view's head is a directory by synthesis, as a road directory is.
            if target in road or target == TRASH_ROOT:
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
        if content_only and view is not None and not view.reads(mapping):
            # A row the caller may name but not read: the refusal confirms only what a listing shows.
            errors.append(denied(target))
            continue
        rows.append(_observe_for(view, mapping, fetched))
    return rows, errors


def render_notes(rows: Sequence[Observation]) -> tuple[list[Observation], list[ResultError]]:
    """What a read says about a bytes-sourced row's text, by its render status.

    The text is a rendering, so a status that left no content row is
    reported beside the row rather than invented: pending is a
    transient absence (run ``reindex``), a failure is a permanent one
    naming its reason, and an empty rendering is the empty string. A
    cut rendering is served with an info note. Text rows pass untouched.
    """
    shown: list[Observation] = []
    notes: list[ResultError] = []
    for row in rows:
        status = row.render_status
        if row.source != "bytes" or status in (None, "ok"):
            shown.append(row)
            continue
        if status == "empty":
            shown.append(row.model_copy(update={"content": ""}))
            continue
        shown.append(row)
        if status == "pending":
            detail = "the binary awaits a rendering; run reindex"
            kind, severity, retryable = ErrorKind.unavailable, Severity.warning, True
        elif status in RENDERED_STATUSES:
            detail = f"the rendering was cut short ({status})"
            kind, severity, retryable = ErrorKind.truncated, Severity.info, False
        else:
            assert status in FAILURE_STATUSES
            detail = f"no text rendering ({status})"
            kind, severity, retryable = ErrorKind.unsupported, Severity.warning, False
        notes.append(
            classified(
                kind, row.path, severity=severity, retryable=retryable, detail=detail, data={"render_status": status}
            )
        )
    return shown, notes


def road_observation(path: str) -> Observation:
    """A directory shown only because a row the caller may name lies beneath it: path and kind."""
    return bare_observation(path, "directory")


def bare_observation(path: str, kind: str) -> Observation:
    """A row the caller holds ``list`` on: its path and kind, nothing else populated."""
    return Observation.model_validate({"path": Path._brand(path), "kind": kind, "populated": LIST_FIELDS})


def addressed_by(patterns: Sequence[str]) -> list[str]:
    """The path each pattern addresses — the directory its literal prefix names — where anonymous is judged.

    A pattern's scope is the deepest directory its literal prefix names
    once braces are expanded: ``/scratch/**`` and ``/scratch/a*`` are
    judged at ``/scratch``, a bare ``**`` at the root, a trash-view
    pattern at the path beneath the head. No pattern at all is the
    whole mount, judged at the root. A pattern the fan will refuse is
    judged at the root: the refusal, not the posture, answers it.
    """
    if not patterns:
        return [ROOT]
    try:
        addresses = address_channel("pattern", patterns)
    except PatternError:
        return [ROOT]
    addressed: list[str] = []
    for address in addresses:
        prefix = _literal_prefix(address.stored)
        scope = prefix if prefix.endswith("/") else prefix.rsplit("/", 1)[0] + "/"
        addressed.append(scope.rstrip("/") if scope.startswith("/") and scope != "/" else ROOT)
    return list(dict.fromkeys(addressed))


async def _screen(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    targets: Sequence[Path],
    found: _Fetched,
    view: Visibility | None,
) -> tuple[dict[str, RowMapping], set[str], dict[Path, ResultError]]:
    """Split fetched targets into shown rows and road directories, and classify the rest.

    A row shows only on the side of the tombstone its target addresses:
    a live target's tombstoned row is a miss, a trash-view target's live
    row a plain one. With no view every row on its side shows; under a
    view a hidden row is a miss too, and a hidden directory shows as a
    bare name when it is on the road. Every miss then climbs the descent
    ladder on its own side, so a hidden row and an absent one answer at
    the same component and the hint rides only on a tombstone the view
    admits. The view's head is synthesized, never fetched: the callers
    answer it themselves.
    """
    candidates: dict[Path, RowMapping] = {}
    unresolved: list[Path] = []
    for target in dict.fromkeys(targets):
        key = str(target)
        if key == TRASH_ROOT:
            continue
        mapping = found.by_target.get(key)
        if mapping is not None and (mapping["deleted_at"] is not None) == address_of(key).trashed:
            candidates[target] = mapping
        else:
            unresolved.append(target)
    road: set[str] = set()
    if view is None:
        shown = {str(target): mapping for target, mapping in candidates.items()}
    else:
        shown = {str(target): mapping for target, mapping in candidates.items() if view.shows(mapping)}
        hidden = {target: address_of(str(target)) for target in candidates if str(target) not in shown}
        for trashed in (False, True):
            stored = {address.stored: target for target, address in hidden.items() if address.trashed == trashed}
            doors = [path for path, target in stored.items() if candidates[target]["kind"] == "directory"]
            if doors:
                road |= {str(stored[path]) for path in await view.road(session, doors, trashed=trashed)}
        unresolved.extend(target for target in hidden if str(target) not in road)
    misses = await _classify_unresolved(session, found.rows, unresolved, view)
    return shown, road, misses


async def _classify_unresolved(
    session: AsyncSession, chain: dict[str, RowMapping], targets: Sequence[Path], view: Visibility | None
) -> dict[Path, ResultError]:
    """The descent ladder for every target no row answered, walked on the side each addresses.

    *chain* is the point fetch — the targets' stored rows and their
    ancestors, with what a view judges by — so no second query is
    issued. The live side climbs the live rows the view shows and hints
    at the tombstones it admits. The trash side climbs the tombstoned
    rows it shows — admitted, or a directory on the road to one — keyed
    at their view addresses beneath the synthesized heads, so the first
    missing component is named in the caller's own coordinates and a
    hidden row reads as an absent one.
    """
    if not targets:
        return {}
    gone = {path: row for path, row in chain.items() if row["deleted_at"] is not None}
    if view is None:
        kinds = {path: row["kind"] for path, row in chain.items() if path not in gone}
        tombstones = {path: row["deleted_at"] for path, row in gone.items()}
        viewed = {path: row["kind"] for path, row in gone.items()}
    else:
        kinds = await view.seen_kinds(session, chain)
        tombstones = view.tombstones(chain, "read")
        viewed = {path: row["kind"] for path, row in gone.items() if view.shows(row)}
        doors = [path for path, row in gone.items() if path not in viewed and row["kind"] == "directory"]
        if doors:
            viewed |= dict.fromkeys(await view.road(session, doors, trashed=True), "directory")
    trash_kinds = _VIEW_HEADS | {TRASH_ROOT + path: kind for path, kind in viewed.items()}
    misses: dict[Path, ResultError] = {}
    for target in targets:
        if address_of(str(target)).trashed:
            misses[target] = classify_miss(target, trash_kinds)
        else:
            misses[target] = classify_miss(target, kinds, tombstones)
    return misses


async def _visible_rows(
    session: AsyncSession, stmt: Select[Any], view: Visibility, scope: str | None
) -> dict[str, RowMapping]:
    """*stmt* narrowed by the view (one statement, or one per clause), merged by path, every row passing it."""
    merged: dict[str, RowMapping] = {}
    for statement in view.narrow(stmt, scope):
        for mapping in (await session.execute(statement)).mappings():
            if view.holds(mapping, view.need):
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


class _Fetched(NamedTuple):
    """The point fetch: the row each target addresses, keyed by the target, and every row fetched, by stored path."""

    by_target: dict[str, RowMapping]
    rows: dict[str, RowMapping]


async def _mappings_by_path(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    targets: Sequence[Path],
    fetched: frozenset[str],
    *,
    with_entry_id: bool,
    judged: bool = False,
) -> _Fetched:
    """One bounded fetch for the batch and its ancestor chain; *judged* rows carry the rights fields.

    Every row carries its tombstone beside *fetched*, so the caller can
    tell which side of it the row sits on; a trash-view target fetches
    the row at the path beneath the head. The targets' ancestors ride in
    the same membership, so the descent ladder classifies every miss from
    this one fetch — a tombstoned or hidden target costs no second query.
    """
    columns, source = _entry_projection(tables, fetched | {"deleted_at"}, with_entry_id=with_entry_id)
    if judged:
        columns = [*columns, *(tables.entry.c[field] for field in sorted(RIGHTS_FIELDS))]
    addresses = {str(target): address_of(str(target)) for target in targets}
    stored = targets_with_ancestors(Path._brand(address.stored) for address in addresses.values())
    rows = await rows_by_path(session, tables.entry, stored, columns, profile, membership_budget, source=source)
    by_target = {key: rows[address.stored] for key, address in addresses.items() if address.stored in rows}
    return _Fetched(by_target, rows)


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

    One scope per liveness class: meta-addressed targets see meta rows,
    and trash-view targets see the tombstoned children of the tombstoned
    directory beneath the head. Chunks partition parents, so each
    parent's children arrive whole and name-ordered; the dict preserves
    that order per parent. Under a view a child the caller holds only
    ``list`` on shows bare, a hidden child directory stays in its place
    as a bare name when it is on the road, and every other hidden child
    drops.
    """
    wanted = fetched | {"deleted_at"} | (RIGHTS_FIELDS if view is not None else frozenset())
    scopes: dict[tuple[bool, bool], set[str]] = {}
    for target in directories:
        address = address_of(str(target))
        scopes.setdefault((address.meta, address.trashed), set()).add(found[str(target)]["entry_id"])
    children: dict[str, list[Observation]] = {}
    for (include_meta, trashed), parents in sorted(scopes.items()):
        listed: dict[str, list[RowMapping]] = {}
        for chunk in chunked(sorted(parents), membership_budget):
            stmt = (
                select(entry.c.parent_id, *_entry_columns(entry, wanted))
                .where(
                    membership(entry.c.parent_id, chunk, profile),
                    *liveness_filters(entry, profile, include_meta=include_meta, trashed=trashed),
                )
                .order_by(entry.c.parent_id, entry.c.name)
            )
            for mapping in (await session.execute(stmt)).mappings():
                listed.setdefault(mapping["parent_id"], []).append(mapping)
        if view is None:
            children |= {parent: [_observe(m, fetched) for m in rows] for parent, rows in listed.items()}
            continue
        mappings = [m for rows in listed.values() for m in rows]
        hidden = [m["path"] for m in mappings if m["kind"] == "directory" and not view.shows(m)]
        road = await view.road(session, hidden, trashed=trashed) if hidden else set()
        for parent, rows in listed.items():
            for mapping in rows:
                if view.shows(mapping):
                    children.setdefault(parent, []).append(_observe_for(view, mapping, fetched))
                elif mapping["path"] in road:
                    children.setdefault(parent, []).append(road_observation(mapping["path"]))
    return children


def _entry_projection(
    tables: VFSTables, fetched: frozenset[str], *, with_entry_id: bool
) -> tuple[list[ColumnElement[Any]], FromClause | None]:
    """The select list serving *fetched*, plus the FROM override when a body joins."""
    entry = tables.entry
    columns: list[ColumnElement[Any]] = list(_entry_columns(entry, fetched))
    if with_entry_id:
        columns = [entry.c.entry_id, *columns]
    bodies = fetched & BODY_FIELDS
    if not bodies:
        return columns, None
    if "content" in bodies:
        columns.append(tables.content.c.content)
    if "data" in bodies:
        columns.append(tables.blobs.c.data)
    return columns, tables.bodies_joined(content="content" in bodies, data="data" in bodies)


def _entry_columns(entry: Table, fetched: frozenset[str]) -> list[Column[object]]:
    return [entry.c[field] for field in sorted(fetched - BODY_FIELDS)]


def _observe_for(view: Visibility | None, mapping: RowMapping, fetched: frozenset[str]) -> Observation:
    """The row whole when *view* reads it (or there is no view), else bare: path and kind, no ``deleted_at``."""
    if view is None or view.reads(mapping):
        return _observe(mapping, fetched)
    return bare_observation(mapping["path"], mapping["kind"])


def _observe(mapping: RowMapping, fetched: frozenset[str]) -> Observation:
    # A tombstoned row reaches here only through the trash view, which projects when it was deleted.
    if mapping.get("deleted_at") is not None:
        fetched = fetched | {"deleted_at"}
    # Stored paths are canonical by invariant: re-brand, never re-gate.
    values: dict[str, object] = {field: mapping[field] for field in fetched}
    values["path"] = Path._brand(mapping["path"])
    values["populated"] = fetched
    return Observation.model_validate(values)


async def _trash_roots(
    session: AsyncSession, tables: VFSTables, profile: DialectProfile, fetched: frozenset[str], view: Visibility | None
) -> list[Observation]:
    """``ls`` of the trash view's head: every tombstoned root, at its own path, in path order."""
    entry = tables.entry
    wanted = fetched | {"deleted_at"} | (RIGHTS_FIELDS if view is not None else frozenset())
    stmt = (
        select(*_entry_columns(entry, wanted))
        .where(
            tombstoned_roots(entry),
            *liveness_filters(entry, profile, include_meta=False, trashed=True),
        )
        .order_by(entry.c.path)
    )
    if view is None:
        return [_observe(mapping, fetched) for mapping in (await session.execute(stmt)).mappings()]
    visible = await _visible_rows(session, stmt, view, None)
    return [_observe_for(view, visible[path], fetched) for path in sorted(visible)]


def _with_trash_view(listed: list[Observation]) -> list[Observation]:
    """The meta root's listing with the synthesized trash view in its name order — no row is ever stored there."""
    return sorted([*listed, road_observation(TRASH_ROOT)], key=lambda row: row.path.name)


def _depth(stored: str) -> int:
    """Segment depth of a stored path string: 0 for the root."""
    return 0 if stored == "/" else stored.count("/")


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
