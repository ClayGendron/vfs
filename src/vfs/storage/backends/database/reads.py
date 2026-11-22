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
from the content table, and the fetch and verdict they share with the
listings of ``listings.py`` live here. Glob executes the batched pattern contract: every
pattern contributes one self-contained OR-arm (its sargable ``LIKE``
prefilter with all ext and liveness facts inside the arm), every scope
root one root clause (its strict-descendant ``LIKE``), arms and clauses
chunk by the dialect's budgets in one snapshot, and the compiled
segment-aware patterns (``vfs.pattern_matching``) verify every candidate
authoritatively, in path order on the binary-collated ``path`` column,
byte-identical across engines; a page of it seeks strictly after a key.

A deleted row stays at its path with a tombstone, and every read here
reads around it: a point read classifies a tombstoned row as absent
with the trashed hint, and every glob carries the liveness term.
The ``/.vfs/trash`` head is a view over the tombstoned rows: a target
or pattern under it is stripped to the path it names, the liveness
term flips, and each row answers at its own path with ``deleted_at``
projected. ``/.vfs/trash`` itself is a synthesized directory, never a
stored row.
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any, Final, NamedTuple

from sqlalchemy import LargeBinary, and_, cast, or_, select

from vfs.deadline import WALL_TIME_BUDGET, Deadline
from vfs.models import CONTENT_KINDS, RENDERED_STATUSES, Observation
from vfs.models.media import FAILURE_STATUSES
from vfs.offload import judge_rows, wall_truncation
from vfs.paths import (
    METADATA_ROOT,
    TRASH_ROOT,
    Address,
    Path,
    _under_meta_root,
    address_of,
    normalize_ext_channel,
)
from vfs.pattern_matching import (
    ROW_GATE_FIELDS,
    GlobFilter,
    GlobGates,
    PatternError,
    ScopeChannel,
    compile_filter,
    compile_gates,
    composed_pattern,
    derive_ext,
    expand_channel,
)
from vfs.results import ErrorKind, Result, ResultError, Severity, classified, wrong_kind
from vfs.storage.backends.database.addressing import address_channel, literal_prefix
from vfs.storage.backends.database.descent import (
    LIKE_ESCAPE,
    classify_miss,
    descendant_filter,
    escape_like,
    liveness_filters,
    rows_by_path,
    targets_with_ancestors,
)
from vfs.storage.backends.database.dialects import arm_budget, chunked
from vfs.storage.backends.database.keyset import filled, first_unjudged, keyed
from vfs.storage.backends.database.membership import membership
from vfs.storage.backends.database.pathterms import ChannelTerms, compile_channel
from vfs.storage.backends.database.rights import RIGHTS_FIELDS, denied

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from concurrent.futures import Executor

    from sqlalchemy import Column, ColumnElement, FromClause, Table
    from sqlalchemy.engine import RowMapping
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models.rows import EntryId, VFSTables
    from vfs.pattern_matching import Body, GlobChannel
    from vfs.storage.backends.database.dialects import DialectProfile
    from vfs.storage.backends.database.keyset import Fetch
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
# Row screening — the fetch and the verdict point reads and listings share
# ---------------------------------------------------------------------------


class Fetched(NamedTuple):
    """The point fetch: the row each target addresses, keyed by the target, and every row fetched, by stored path."""

    by_target: dict[str, RowMapping]
    rows: dict[str, RowMapping]


async def mappings_by_path(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    targets: Sequence[Path],
    fetched: frozenset[str],
    *,
    with_entry_id: bool,
    judged: bool = False,
) -> Fetched:
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
    return Fetched(by_target, rows)


async def screen(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    targets: Sequence[Path],
    found: Fetched,
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


def observe_for(view: Visibility | None, mapping: RowMapping, fetched: frozenset[str]) -> Observation:
    """The row whole when *view* reads it (or there is no view), else bare: path and kind, no ``deleted_at``."""
    if view is None or view.reads(mapping):
        return observe(mapping, fetched)
    return bare_observation(mapping["path"], mapping["kind"])


def observe(mapping: RowMapping, fetched: frozenset[str]) -> Observation:
    """The fetched row as an observation, its mask the fields fetched; a tombstoned row adds ``deleted_at``."""
    # A tombstoned row reaches here only through the trash view, which projects when it was deleted.
    if mapping.get("deleted_at") is not None:
        fetched = fetched | {"deleted_at"}
    # Stored paths are canonical by invariant: re-brand, never re-gate.
    values: dict[str, object] = {field: mapping[field] for field in fetched}
    values["path"] = Path._brand(mapping["path"])
    values["populated"] = fetched
    return Observation.model_validate(values)


def entry_columns(entry: Table, fetched: frozenset[str]) -> list[Column[object]]:
    """The entries-table columns that serve the fields in *fetched*, the body fields left to their own tables."""
    return [entry.c[field] for field in sorted(fetched - BODY_FIELDS)]


# ---------------------------------------------------------------------------
# Glob — one OR fan of self-contained pattern arms, compiled authority
# ---------------------------------------------------------------------------

# Ceiling of one arm's non-ext bind slots: the root-row exclusion, the
# prefilter LIKE, the derived-ext pair, the meta-liveness pair, and the
# kind fact.
ARM_FIXED_BINDS: Final = 7

# Ceiling of one scope root clause's fixed bind slots: the root-row
# exclusion, the strict-descendant LIKE, the kind fact, the meta-liveness pair.
ROOT_ARM_BINDS: Final = 5

# The bind a page's key adds to each arm and each root clause; charged only on a paged call.
PAGE_KEY_BINDS: Final = 1

# At most this many composed patterns on a side, a scope prefilters as composition did:
# within one statement's measured OR-fan sweet spot, and a tighter fetch than the roots alone.
COMPOSED_PREFILTER_LIMIT: Final = 200

# Ceiling of one channel arm's bind slots: the ext pair and the name fact.
CHANNEL_ARM_BINDS: Final = 3

# What shrinks a storage glob that reached its wall.
GLOB_REFINE_GUIDANCE: Final = "narrow the pattern or its exclusions, add ext filters, or scope with paths"


async def glob_rows(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    parameter_budget: int,
    membership_budget: int,
    executor: Executor,
    *,
    patterns: tuple[str, ...],
    globs_not: tuple[str, ...],
    ext: tuple[str, ...],
    ext_not: tuple[str, ...],
    kind: str | None,
    max_count: int | None,
    columns: frozenset[str] | None,
    wall_seconds: float = WALL_TIME_BUDGET,
    view: Visibility | None = None,
    scope: AdmittedScope | None = None,
    after: Path | None = None,
    limit: int | None = None,
) -> Result:
    """Rows matching **any** pattern, one snapshot, statements chunked by budget; or one page of them.

    Scoping arrives in one shape. *patterns* and *globs_not* are the
    entry-wide channel, and every root strictly beneath the entry rides
    beside the arms as *scope*, already admitted at the seam (see
    :func:`admit_scope`). The law is the scope's: the arms are judged
    once against each row's remainder under every covering root. The
    prefilter that fetches the candidates is this call's own choice,
    made per side of the tombstone by :meth:`AdmittedScope.composed`.
    Up to the composed prefilter's limit, the side's roots composed with
    the arms join the pattern fan, the tighter fetch. Past it, or with
    no arm, one root clause per root, chunked, fetches the rows strictly
    beneath its root, with the arms' leaf facts beside the OR where the
    profile declares ``scope_facts_beside_fan``. Either plan runs in
    this one call and snapshot beside the entry-wide arms, the
    candidates merged by path, and neither changes an answer that is
    not truncated. So the rule that hides ``/.vfs`` is the law's as well
    as each arm's: a row beneath the meta root is admitted only by a
    pattern or a root that names the meta subtree, whichever arm or
    clause fetched it. Root assertions stay the router's. The
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

    The candidates of each side of the tombstone are judged in one hop
    on *executor*, under a wall of *wall_seconds* read when the call
    starts, so the candidate fetch counts against it. A row the engine
    did not judge before the wall is dropped, since it may match an
    exclusion, and the call carries one ``truncated`` warning; which
    rows are missing then depends on scheduling. *max_count* cuts the
    judged rows by path order, and the warning stays whatever it cuts.

    With *after* or *limit* the call serves one page in path order; the
    storage has refused a page beside *max_count* before any read. The key rides inside every arm and every root
    clause as ``path > :after``, never beside the fan, and each chunk
    statement is a stream ordered by path with its own limit, filled as
    :mod:`~vfs.storage.backends.database.keyset` says. The ``LIKE``
    prefilter over-admits and a pattern with no literal prefix has no
    path range, so a page visits the candidates in its path range, not
    ``limit + 1`` rows: a sparse pattern over a large corpus reads many
    rows per page, as one whole call does, and each candidate about once
    across a listing. One branch per arm, each with its own limit, would
    bound a prefixed arm, and waits for a measured need.
    """
    paged = after is not None or limit is not None
    try:
        addresses = address_channel("pattern", patterns)
        excluded = address_channel("globs_not", globs_not)
    except PatternError as exc:
        return Result(ops=("glob",), errors=[classified(ErrorKind.invalid, detail=str(exc))])
    deadline = Deadline.after(wall_seconds)
    fetched = effective_columns(columns, content=False)
    entry = tables.entry
    wanted = normalize_ext_channel(ext)
    # A pattern under the trash head gates the tombstoned rows at the paths
    # beneath it, every other the live rows; exclusions side the same way.
    sides = {
        trashed: _side_gates(
            addresses, excluded, ext, ext_not, trashed=trashed, scope=side_scope(scope, trashed=trashed)
        )
        for trashed in (False, True)
    }
    facts = NO_SCOPE_FACTS
    if scope is not None and (scope.live or scope.trashed):
        facts = scope_facts(entry, profile, parameter_budget, membership_budget, scope.channel.arms)
    ride = ext_membership(entry, wanted, membership_budget)
    keyed_binds = PAGE_KEY_BINDS if paged else 0
    chunk = arm_budget(profile, parameter_budget, ARM_FIXED_BINDS + ride.binds + keyed_binds)

    # One builder per statement of the fan, so a stream rebuilds its own arms alone at each position it reads from.
    builders: list[Callable[[str | None], ColumnElement[bool]]] = []
    live_arms: list[tuple[GlobFilter, bool, ColumnElement[bool]]] = []
    for trashed, gates in sides.items():
        prefilter = list(gates.admissions)
        composed = None if scope is None else scope.composed(trashed=trashed)
        if composed is not None:
            prefilter += [compile_filter(pattern) for pattern in composed]
        elif scope is not None:
            roots = scope.roots(trashed=trashed)
            per_statement = scope_chunk(entry, profile, parameter_budget, membership_budget, facts, wanted, keyed=paged)
            budgets = (parameter_budget, membership_budget)
            builders += [
                partial(_scope_where, entry, profile, budgets, part, facts, wanted, kind, trashed, paged)
                for part in chunked(list(roots), per_statement)
            ]
        for glob in prefilter:
            arm = pattern_arm(entry, glob, wanted, profile, membership_budget, kind=kind, trashed=trashed)
            if arm is not None:
                live_arms.append((glob, trashed, arm))
    arm_builders = [
        partial(_arms_where, entry, part, wanted, profile, membership_budget, kind)
        for part in chunked(live_arms, chunk)
    ]
    builders = [*arm_builders, *builders]

    # name and ext ride for the row-fact gate; the observation mask stays
    # the caller's `fetched`, so a narrow columns= never leaks the ride.
    queried = fetched | ROW_GATE_FIELDS | {"deleted_at"} | (RIGHTS_FIELDS if view is not None else frozenset())
    finished = [True]
    # The first path the batch judged last left unjudged at the wall, on either side: where a page's fill stops.
    cut: list[str | None] = [None]

    async def judged(candidates: Sequence[RowMapping]) -> list[Observation]:
        """The candidates the compiled patterns and the view admit, in path order, roads included."""
        cut[0] = None
        matched: dict[str, RowMapping] = {}
        hidden: dict[bool, list[str]] = {False: [], True: []}
        for trashed, gates in sides.items():
            side = [mapping for mapping in candidates if (mapping["deleted_at"] is not None) == trashed]
            if not side or not (gates.admissions or gates.scoped):
                continue
            rows = [(mapping["path"], mapping["name"]) for mapping in side]
            verdicts, completed = await judge_rows(executor, gates, rows, deadline=deadline)
            finished[0] = finished[0] and completed
            cut[0] = first_unjudged(cut[0], side, verdicts)
            for mapping, verdict in zip(side, verdicts, strict=True):
                if not gates.admits(verdict, mapping["ext"], marked_only=_under_meta_root(mapping["path"])):
                    continue
                if view is None or view.shows(mapping):
                    matched.setdefault(mapping["path"], mapping)
                elif mapping["kind"] == "directory":
                    hidden[trashed].append(mapping["path"])
        observed = {path: observe_for(view, mapping, fetched) for path, mapping in matched.items()}
        for trashed, paths in hidden.items():
            if view is not None and paths:
                observed |= {path: road_observation(path) for path in await view.road(session, paths, trashed=trashed)}
        return [observed[path] for path in sorted(observed)]

    key: Path | None = None
    if paged:
        streams = _candidate_streams(session, entry, queried, builders)
        found = await filled(streams, judged, after=after, limit=limit, cut=lambda: cut[0])
        served, key = keyed(found.rows, found.frontier, after=after, limit=limit)
    else:
        served = await judged(await _pattern_candidates(session, entry, queried, [build(None) for build in builders]))
        served = served if max_count is None else served[:max_count]
    errors = [] if finished[0] else [wall_truncation(GLOB_REFINE_GUIDANCE)]
    return Result(ops=("glob",), observations=served, errors=errors, next_after=key)


# ---------------------------------------------------------------------------
# The scope channel — roots beside the arms, admitted at the seam
# ---------------------------------------------------------------------------


class AdmittedScope(NamedTuple):
    """A scope admitted at the seam: its arms expanded, its roots addressed to their side of the tombstone.

    ``channel`` keeps the roots in entry coordinates, the trash head
    included, with the expanded arms; ``live`` and ``trashed`` hold the
    stored roots of each side, distinct, in the caller's order.
    """

    channel: ScopeChannel
    live: tuple[Path, ...]
    trashed: tuple[Path, ...]

    def roots(self, *, trashed: bool) -> tuple[Path, ...]:
        """The stored roots on one side of the tombstone."""
        return self.trashed if trashed else self.live

    def composed(self, *, trashed: bool) -> tuple[str, ...] | None:
        """One side's prefilter plan: its roots composed with the arms, or ``None`` to fetch by the roots.

        The one plan choice glob, grep and search share. While the
        side's roots times the arms number from one to
        :data:`COMPOSED_PREFILTER_LIMIT`, read when the call is made,
        the answer is each stored root composed with each arm, distinct,
        in root order then arm order: pattern text for the pattern fan.
        ``None`` (no root on the side, no arm, or a product past the
        limit) keeps the root clauses, so a scope with no arm never
        fetches unrestricted; exclusion arms never prefilter in SQL and
        do not count. The choice changes what is fetched, never what is
        admitted: the verb's law judges every candidate under either.
        """
        roots = self.roots(trashed=trashed)
        arms = self.channel.arms
        if not 0 < len(roots) * len(arms) <= COMPOSED_PREFILTER_LIMIT:
            return None
        return tuple(dict.fromkeys(composed_pattern(root, arm) for root in roots for arm in arms))


def admit_scope(scope: ScopeChannel | None, arms_channel: GlobChannel) -> AdmittedScope | None:
    """*scope* admitted whole, or :class:`PatternError`: the arms gated, every root strictly beneath its side.

    The arms pass the same admission as the caller's entry-wide channel
    (*arms_channel*), the exclusion arms the ``globs_not`` one. A root
    the trash view's head lies at or beneath is refused, by the one test
    the router's planner reads, because its patterns belong on the
    entry-wide channel, composed. A root whose stored form is ``/`` (the
    entry's root, or the head itself) has nothing beneath it to cut a
    remainder from. A live root above the head (``/.vfs``) joins with an
    arm into text the view can claim, a meaning the root and the arm
    read apart do not carry.
    """
    if scope is None:
        return None
    arms = expand_channel(arms_channel, scope.arms)
    arms_not = expand_channel("globs_not", scope.arms_not)
    roots = tuple(dict.fromkeys(scope.roots))
    sides: dict[bool, list[Path]] = {False: [], True: []}
    for root in roots:
        address = address_of(str(root))
        if address.holds_trash_head:
            reason = "addresses the whole entry" if address.stored == "/" else "holds the trash view's head"
            raise PatternError(f"scope root {str(root)!r} {reason}; send its patterns on the entry-wide channel")
        sides[address.trashed].append(root.without_mount(TRASH_ROOT) if address.trashed else root)
    channel = ScopeChannel(roots=roots, arms=arms, arms_not=arms_not)
    return AdmittedScope(channel, tuple(dict.fromkeys(sides[False])), tuple(dict.fromkeys(sides[True])))


def side_scope(scope: AdmittedScope | None, *, trashed: bool) -> ScopeChannel | None:
    """The scope's channel on one side of the tombstone, its roots stored; ``None`` where no root sits there."""
    if scope is None:
        return None
    roots = scope.roots(trashed=trashed)
    if not roots:
        return None
    return ScopeChannel(roots, scope.channel.arms, scope.channel.arms_not)


class ScopeFacts(NamedTuple):
    """The arms' root-independent facts beside the root OR, paired with their binds; ``(None, 0)`` when declined."""

    predicate: ColumnElement[bool] | None
    binds: int


NO_SCOPE_FACTS: Final = ScopeFacts(None, 0)


def scope_facts(
    entry: Table, profile: DialectProfile, parameter_budget: int, membership_budget: int, arms: Sequence[str]
) -> ScopeFacts:
    """The arms' leaf-name and derived-extension facts as one OR, built once per call, or declined.

    A composed pattern's last component is its arm's, so these facts
    hold under any root. They ride only where the profile declares
    ``scope_facts_beside_fan`` (its plan pin proved the root OR keeps its
    index access with them beside it), when every arm pins a fact, when
    the arms number at most the channel fan, and when their binds fit
    half the membership budget. A declined statement fetches more
    candidates, never different rows.
    """
    if not profile.scope_facts_beside_fan or not arms:
        return NO_SCOPE_FACTS
    channel = compile_channel(arms)
    if len(channel.arms) > arm_budget(profile, parameter_budget, CHANNEL_ARM_BINDS):
        return NO_SCOPE_FACTS
    predicate, binds = channel_facts(entry, profile, channel)
    if predicate is None or binds > membership_budget // 2:
        return NO_SCOPE_FACTS
    return ScopeFacts(predicate, binds)


def scope_root_arm(
    entry: Table,
    root: str,
    wanted: frozenset[str],
    profile: DialectProfile,
    membership_budget: int,
    *,
    kind: str | None = None,
    trashed: bool = False,
    after: str | None = None,
) -> ColumnElement[bool]:
    """One scope root's clause: the rows strictly beneath *root*, with the call's per-row facts.

    The root-row exclusion, the strict-descendant ``LIKE`` on the
    escaped root, the kind fact, the caller's wanted-ext membership and
    the liveness terms, the meta exclusion lifted when the root names
    the meta subtree: :func:`pattern_arm`'s facts without a pattern to
    translate. The ``LIKE`` prefix, not a byte range, because bytewise
    order is not a contract on every engine.
    """
    terms: list[ColumnElement[bool]] = [entry.c.path != "/", descendant_filter(entry, root, profile)]
    if after is not None:
        terms.append(entry.c.path > after)
    if kind is not None:
        terms.append(entry.c.kind == kind)
    ride = ext_membership(entry, wanted, membership_budget)
    if ride.predicate is not None:
        terms.append(ride.predicate)
    terms.extend(liveness_filters(entry, profile, include_meta=meta_scoped(root), trashed=trashed))
    return and_(*terms)


def scope_fan(
    entry: Table,
    profile: DialectProfile,
    parameter_budget: int,
    membership_budget: int,
    roots: Sequence[str],
    facts: ScopeFacts,
    wanted: frozenset[str],
    *,
    kind: str | None = None,
    trashed: bool = False,
    reserved: int = 0,
    after: str | None = None,
    keyed: bool = False,
) -> list[ColumnElement[bool]]:
    """One WHERE per statement: an OR of root clauses, chunked by budget, the arms' facts beside each OR.

    The facts' binds are charged once per statement and the root
    clause's per root, so the chunk is the arm budget over what the
    facts and the caller's *reserved* binds leave: no statement grows
    with the roots, on the least generous engine. *after* puts a page's
    key in every root clause, and *keyed* charges its bind on every page
    of a paged call, the first included, so the chunks never move.
    """
    if not roots:
        return []
    chunk = scope_chunk(
        entry, profile, parameter_budget, membership_budget, facts, wanted, reserved=reserved, keyed=keyed
    )
    built = [
        scope_root_arm(entry, root, wanted, profile, membership_budget, kind=kind, trashed=trashed, after=after)
        for root in roots
    ]
    fans = [or_(*part) for part in chunked(built, chunk)]
    if facts.predicate is None:
        return fans
    return [and_(fan, facts.predicate) for fan in fans]


def scope_chunk(
    entry: Table,
    profile: DialectProfile,
    parameter_budget: int,
    membership_budget: int,
    facts: ScopeFacts,
    wanted: frozenset[str],
    *,
    reserved: int = 0,
    keyed: bool = False,
) -> int:
    """The most root clauses one statement of :func:`scope_fan` holds, on what the facts and *reserved* leave."""
    ride = ext_membership(entry, wanted, membership_budget)
    per_root = ROOT_ARM_BINDS + ride.binds + (PAGE_KEY_BINDS if keyed else 0)
    return arm_budget(profile, parameter_budget - facts.binds - reserved, per_root)


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
    after: str | None = None,
) -> ColumnElement[bool] | None:
    """One pattern's self-contained OR-arm, or ``None`` when provably empty.

    Every fact rides inside the arm — the root-row exclusion, the
    prefilter LIKE, both ext facts, the liveness scope (the tombstone
    term, flipped under the trash view by *trashed*, and the meta
    exclusion), the kind fact — because the fan's plan survives only as
    a pure OR of self-contained arms: on SQLite, the engine the field
    study measured, one ``ext IN`` conjunct beside the fan demoted the
    multi-index OR to a scan (the scope fan's facts conjunct is a
    different shape, admitted per engine by its own plan pin). The caller's ext
    membership stands down when the empty extension (stored NULL) is
    wanted or the set outgrows one chunk; a derived ext contradicting
    the caller's set makes the arm dead.
    """
    subject = entry.c.path if glob.by_path else entry.c.name
    like = _glob_like(glob.pattern)
    prefilter = like if like is not None else escape_like(literal_prefix(glob.pattern), profile) + "%"
    terms: list[ColumnElement[bool]] = [entry.c.path != "/", subject.like(prefilter, escape=LIKE_ESCAPE)]
    if after is not None:
        terms.append(entry.c.path > after)
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


def channel_facts(
    entry: Table, profile: DialectProfile, channel: ChannelTerms
) -> tuple[ColumnElement[bool] | None, int]:
    """The channel's ``ext``/``name`` facts as one OR over arms, with binds.

    The channel is an OR, so the predicate is sound only when *every*
    arm pins at least one fact — an arm with none admits everything and
    makes the disjunction vacuous; the void returns ``(None, 0)``. Each
    ext fact carries the dotfile rescue (a stored NULL ext with the
    dot-suffix name), mirroring the scan tier's arm law.
    """
    arms: list[ColumnElement[bool]] = []
    binds = 0
    for arm in channel.arms:
        facts: list[ColumnElement[bool]] = []
        if arm.ext is not None:
            facts.append(or_(entry.c.ext == arm.ext.ext, entry.c.name == arm.ext.dot_suffix))
            binds += 2
        if arm.name is not None:
            if arm.name.prefix:
                prefix = escape_like(arm.name.text, profile) + "%"
                facts.append(entry.c.name.like(prefix, escape=LIKE_ESCAPE))
            else:
                facts.append(entry.c.name == arm.name.text)
            binds += 1
        if not facts:
            return None, 0
        arms.append(and_(*facts))
    if not arms:
        return None, 0
    return or_(*arms), binds


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


def _side_gates(
    addresses: Sequence[Address],
    excluded: Sequence[Address],
    ext: tuple[str, ...],
    ext_not: tuple[str, ...],
    *,
    trashed: bool,
    scope: ScopeChannel | None = None,
) -> GlobGates:
    """One side's gates: its addressed patterns and exclusions, its scope, the ext channels, the meta heads marked."""
    return compile_gates(
        [address.stored for address in addresses if address.trashed == trashed],
        [address.stored for address in excluded if address.trashed == trashed],
        ext=ext,
        ext_not=ext_not,
        marked=meta_scoped,
        scope=scope,
    )


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
    found = await mappings_by_path(
        session, tables, profile, membership_budget, targets, fetched, with_entry_id=False, judged=view is not None
    )
    shown, road, missing = await screen(session, tables, profile, membership_budget, targets, found, view)
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
        rows.append(observe_for(view, mapping, fetched))
    return rows, errors


def render_notes(rows: Sequence[Observation]) -> tuple[list[Observation], list[ResultError]]:
    """What a read says about a bytes-sourced row's text, by its render status.

    The text is a rendering, so a status that left no content row is
    reported beside the row rather than invented: pending is a
    transient absence (run ``rebuild``), a failure is a permanent one
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
            detail = "the binary awaits a rendering; run rebuild"
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


async def _pattern_candidates(
    session: AsyncSession, entry: Table, fetched: frozenset[str], wheres: Sequence[ColumnElement[bool]]
) -> list[RowMapping]:
    """Prefiltered candidates from the chunked OR fan and the scope's root fan, in path order.

    Each pattern chunk's WHERE is the pure OR of its arms — nothing
    rides beside that fan; each scope statement's WHERE is one of the
    scope's clauses, already chunked. Overlapping arms yield a row once
    per statement; the merge dict dedups across statements, and one
    Python sort restores path order — codepoint order equals the
    binary-collated byte order.
    """
    columns = entry_columns(entry, fetched)
    merged: dict[str, RowMapping] = {}
    for where in wheres:
        result = await session.execute(select(*columns).where(where))
        merged.update({mapping["path"]: mapping for mapping in result.mappings()})
    return [merged[path] for path in sorted(merged)]


def _candidate_streams(
    session: AsyncSession,
    entry: Table,
    fetched: frozenset[str],
    builders: Sequence[Callable[[str | None], ColumnElement[bool]]],
) -> list[Fetch]:
    """One stream for each statement of the fan, in path order, its key inside every arm of that statement alone."""
    columns = entry_columns(entry, fetched)

    def stream(build: Callable[[str | None], ColumnElement[bool]]) -> Fetch:
        async def fetch(position: str | None, batch: int | None) -> Sequence[RowMapping]:
            stmt = select(*columns).where(build(position)).order_by(entry.c.path)
            return (await session.execute(stmt if batch is None else stmt.limit(batch))).mappings().all()

        return fetch

    return [stream(build) for build in builders]


def _arms_where(
    entry: Table,
    arms: Sequence[tuple[GlobFilter, bool, ColumnElement[bool]]],
    wanted: frozenset[str],
    profile: DialectProfile,
    membership_budget: int,
    kind: str | None,
    position: str | None,
) -> ColumnElement[bool]:
    """One statement's OR of pattern arms, each on its side of the tombstone, the key inside each; none is dead.

    Each arm comes built with no key, which serves a read from the start; a read from a key builds them again.
    """
    if position is None:
        return or_(*(arm for _glob, _trashed, arm in arms))
    built = [
        pattern_arm(entry, glob, wanted, profile, membership_budget, kind=kind, trashed=trashed, after=position)
        for glob, trashed, _arm in arms
    ]
    return or_(*(arm for arm in built if arm is not None))


def _scope_where(
    entry: Table,
    profile: DialectProfile,
    budgets: tuple[int, int],
    roots: Sequence[str],
    facts: ScopeFacts,
    wanted: frozenset[str],
    kind: str | None,
    trashed: bool,
    keyed: bool,
    position: str | None,
) -> ColumnElement[bool]:
    """One statement's root clauses: ``roots`` fit one statement of the scope fan, so it builds exactly one.

    ``budgets`` is the parameter budget and the membership budget, in that order.
    """
    parameter_budget, membership_budget = budgets
    [where] = scope_fan(
        entry,
        profile,
        parameter_budget,
        membership_budget,
        roots,
        facts,
        wanted,
        kind=kind,
        trashed=trashed,
        after=position,
        keyed=keyed,
    )
    return where


def _entry_projection(
    tables: VFSTables, fetched: frozenset[str], *, with_entry_id: bool
) -> tuple[list[ColumnElement[Any]], FromClause | None]:
    """The select list serving *fetched*, plus the FROM override when a body joins."""
    entry = tables.entry
    columns: list[ColumnElement[Any]] = list(entry_columns(entry, fetched))
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
