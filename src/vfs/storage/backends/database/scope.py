"""The structural scope every content search shares — grep's and search's.

Scoping crosses the storage seam in one shape: the ``globs`` channels
are entry-wide, every root strictly beneath the entry rides beside the
arms (an admitted scope channel), and the two ``ext`` channels ride
beside both. How a scope prefilters is storage's own choice, made per
call (:func:`scope_channels`): its roots composed with its arms up to
the composed prefilter's limit, its root clauses past it. This module
holds the pieces both verbs stand on:
the authoritative per-row gate (:func:`passes_gates`), the SQL terms a
candidate fetch may ride beside its id chunk (:func:`pushdown_terms`,
with true bind accounting), and the scan side's bounded, structurally
prefiltered fetch of the ``NOT encoded`` overlay (:func:`entries_for_scan`)
with the laws that bound it: the count at which both verbs cut the
path-ordered dirty rows (:data:`SCAN_TIER_BUDGET`) and the metering
that prices a row (:func:`stored_size`) for the bytes of bodies either
verb holds at once, a budget that lives beside the worker pool as
:data:`vfs.offload.CONTENT_BYTE_BUDGET`.
The gate is the law; every pushdown only narrows toward it. A scope
under the ``/.vfs/trash`` head searches the tombstoned rows at the
paths beneath it (:func:`trash_scope`): the head is stripped before
the patterns compile, and the liveness term flips on every tier.
"""

from __future__ import annotations

from itertools import product
from typing import TYPE_CHECKING, Final, NamedTuple

from sqlalchemy import and_, or_, select

from vfs.paths import TRASH_ROOT, _under_meta_root
from vfs.pattern_matching import ROW_GATE_FIELDS, PatternError, compile_filter, escape_glob
from vfs.storage.backends.database import dialects
from vfs.storage.backends.database.addressing import address_channel
from vfs.storage.backends.database.descent import liveness_filters
from vfs.storage.backends.database.dialects import EXPRESSION_DEPTH_RESERVE, arm_budget, chunked
from vfs.storage.backends.database.membership import rare
from vfs.storage.backends.database.pathterms import ChannelTerms, compile_channel
from vfs.storage.backends.database.reads import (
    ARM_FIXED_BINDS,
    NO_SCOPE_FACTS,
    ScopeFacts,
    channel_facts,
    ext_membership,
    kind_membership,
    pattern_arm,
    scope_fan,
)
from vfs.storage.backends.database.rights import RIGHTS_FIELDS, Clause

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy import ColumnElement, Table
    from sqlalchemy.engine import RowMapping
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.deadline import Deadline
    from vfs.models.rows import VFSTables
    from vfs.paths import Path
    from vfs.pattern_matching import GlobFilter, GlobGates, ScopeChannel
    from vfs.storage.backends.database.dialects import DialectProfile
    from vfs.storage.backends.database.reads import AdmittedScope
    from vfs.storage.backends.database.rights import Visibility

# Columns every candidate fetch rides beside the caller's mask: the row-gate
# facts, size_bytes (prices the content read), the tombstone, and what a
# view judges by.
FETCH_RIDE: Final = ROW_GATE_FIELDS | {"size_bytes", "deleted_at"} | RIGHTS_FIELDS

# The count at which both verbs cut the path-ordered scan tier: grep's
# pool of index candidates plus scan rows, search's overlay whole. Re-derived
# from the linux-scale sweep: a candidate costs ~75 µs (fetch-dominated), so
# 25,000 bounds a saturated call near ~2 s while un-truncating every
# benchmark row search semantics can justify. A tripped budget truncates
# with a warning that says what each tier took.
SCAN_TIER_BUDGET: Final = 25_000


class ScanNominees(NamedTuple):
    """Scan-tier entry rows in path order, and whether the cap cut them."""

    rows: list[RowMapping]
    overflow: bool


class Pushdown(NamedTuple):
    """The candidate fetch's rideable predicates and their true bind spend.

    Every predicate is charged at its executed width — an expanding
    membership at its element count, not its compiled placeholder count
    — so the id-chunk arithmetic can never overdraw an engine's
    parameter budget.
    """

    terms: tuple[ColumnElement[bool], ...]
    binds: int


# ---------------------------------------------------------------------------
# The gate — the authority every row passes
# ---------------------------------------------------------------------------


def passes_gates(mapping: RowMapping, gates: GlobGates, verdict: int | None, *, trashed: bool = False) -> bool:
    """The authoritative structural gates, per candidate, off the row's own facts and its verdict.

    *verdict* is the row's judgement against *gates* (``judge_rows``),
    taken over the stored ``path`` and ``name`` columns, which mirror the
    path by invariant, so no ``Path`` is minted per candidate. A row
    passes only on the side of the tombstone the scope searches: live
    rows, or the tombstoned ones under the trash view (*trashed*). A
    meta row is admitted only by a marked admission, one whose literal
    head addresses the meta subtree — default enumeration hides
    ``/.vfs`` even when a wildcard gate would match it. The rest is the
    shared filter law, :meth:`GlobGates.admits`.
    """
    if (mapping["deleted_at"] is not None) != trashed:
        return False
    return gates.admits(verdict, mapping["ext"], marked_only=_under_meta_root(mapping["path"]))


def trash_scope(globs: Sequence[str], scope: AdmittedScope | None = None) -> tuple[tuple[str, ...], bool]:
    """The admitted ``globs`` channel with the trash head stripped, and whether the search addresses the trash view.

    Every pattern under ``/.vfs/trash`` names the tombstoned rows at the
    path beneath the head, and so does every *scope* root beneath it; a
    search whose patterns and roots, across both channels, mix the view
    with live ones refuses, because one search runs on one side of the
    tombstone. An empty channel and no scope search the live namespace.
    """
    addresses = address_channel("globs", globs)
    sides = {address.trashed for address in addresses}
    if scope is not None:
        sides |= {trashed for trashed in (False, True) if scope.roots(trashed=trashed)}
    if len(sides) > 1:
        raise PatternError(f"a scope under {TRASH_ROOT!r} cannot mix with live paths")
    return tuple(address.stored for address in addresses), sides == {True}


class SearchChannels(NamedTuple):
    """A content search's compiled channels: what nominates, what narrows the fetch, and the scope's prefilter.

    A scope prefilters by one of two plans, and the fields hold
    whichever the call chose. Under the root plan, ``allowed`` feeds the
    segment allow-list the ``globs`` plus one ``root/**`` arm per scope
    root, a superset of every admitted row, linear in the roots, and
    void past the channel fan like any channel; the arms' own segment
    terms are relative to the roots, so they never join it. ``facts``
    feeds the pushdown the ``globs`` and the scope's arms together,
    sound because every admitted row matches a glob or an arm's leaf.
    ``roots`` and ``arms`` are the scope's on the search's side, for the
    scan side's root fan. Under the composed plan, ``allowed`` and
    ``facts`` are both the ``globs`` beside the scope's roots composed
    with its arms, ``prefilter`` holds those composed patterns compiled
    for the scan side's pattern fan, and ``roots`` and ``arms`` are
    empty. Either way the fields only narrow a fetch: the gates compiled
    from the scope decide every row.
    """

    allowed: ChannelTerms
    facts: ChannelTerms
    roots: tuple[Path, ...]
    arms: tuple[str, ...]
    prefilter: tuple[GlobFilter, ...] = ()


def scope_channels(
    admissions: Sequence[str], scope: ScopeChannel | None, composed: tuple[str, ...] | None = None
) -> SearchChannels:
    """The search's channels over its admitted ``globs`` and its side's *scope* (stored roots).

    *composed* is the side's answer from ``AdmittedScope.composed``: a
    tuple takes the composed plan over those patterns, ``None`` the root
    plan.
    """
    if scope is None:
        channel = compile_channel(admissions)
        return SearchChannels(channel, channel, (), ())
    if composed is not None:
        channel = compile_channel([*admissions, *composed])
        return SearchChannels(channel, channel, (), (), tuple(compile_filter(pattern) for pattern in composed))
    allowed = compile_channel([*admissions, *(escape_glob(str(root)) + "/**" for root in scope.roots)])
    facts = compile_channel([*admissions, *scope.arms])
    return SearchChannels(allowed, facts, scope.roots, scope.arms)


def scope_exclusions(globs_not: Sequence[str], *, trashed: bool) -> tuple[str, ...]:
    """The admitted ``globs_not`` channel's arms on the side the search runs, head stripped.

    An exclusion addressed into the view excludes tombstoned rows alone,
    one with no head live rows alone; the arms on the other side of the
    tombstone have nothing to exclude from this search and drop.
    """
    addresses = address_channel("globs_not", globs_not)
    return tuple(address.stored for address in addresses if address.trashed == trashed)


# ---------------------------------------------------------------------------
# Pushdown — what a candidate fetch may ride
# ---------------------------------------------------------------------------


def pushdown_terms(
    entry: Table,
    profile: DialectProfile,
    fan_arms: int,
    membership_budget: int,
    channel: ChannelTerms,
    wanted: frozenset[str],
    *,
    hide_meta: bool,
    trashed: bool = False,
) -> Pushdown:
    """The SQL terms the candidate fetch may carry beside the id chunk.

    The liveness term always rides — the tombstone side the scope
    searches binds nothing — and with no admission gates the meta
    exclusion moves into SQL with it, so the string gate may then be
    skipped entirely. The caller's wanted-ext set rides
    under the membership rule, and the channel's compiled column facts
    ride as an OR over arms; both only ever narrow toward the authority,
    never past it. The whole ride is capped at half the membership
    budget so the id chunk always keeps room, and a channel wider than
    *fan_arms* (the caller's channel fan, one OR branch per arm) is
    dropped whole — narrowing is a convenience the statement may
    decline; ``passes_gates`` stays the authority.
    """
    liveness = liveness_filters(entry, profile, include_meta=not hide_meta, trashed=trashed)
    terms: list[ColumnElement[bool]] = [*liveness]
    binds = static_binds(liveness)
    ceiling = membership_budget // 2
    ride = ext_membership(entry, wanted, membership_budget)
    if ride.predicate is not None and binds + ride.binds <= ceiling:
        terms.append(ride.predicate)
        binds += ride.binds
    facts, fact_binds = channel_facts(entry, profile, channel)
    if facts is not None and len(channel.arms) <= fan_arms and binds + fact_binds <= ceiling:
        terms.append(facts)
        binds += fact_binds
    return Pushdown(tuple(terms), binds)


def static_binds(terms: Sequence[ColumnElement[bool]]) -> int:
    """Executed parameter count of non-expanding predicates.

    Post-compile rendering yields the parameters the engine is actually
    asked to bind (``binds`` overcounts bookkeeping entries). Expanding
    memberships never pass through here — they charge their declared
    element width instead (``ExtMembership.binds``). Counting compiles
    on the default dialect: inputs must be dialect-count-invariant — a
    predicate whose bind cardinality varied by dialect would be
    mischarged here, and the pinned invariant is that none does.
    """
    return sum(len(term.compile(compile_kwargs={"render_postcompile": True}).params) for term in terms)


# ---------------------------------------------------------------------------
# The scan side — structural prefilter, bounded fetch, permanent overlay
# ---------------------------------------------------------------------------


def stored_size(mapping: RowMapping) -> int:
    """The byte batcher's exact metering for a scan-tier row: its stored byte size."""
    return mapping["size_bytes"] or 0


async def entries_for_scan(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    parameter_budget: int,
    membership_budget: int,
    gates: Sequence[GlobFilter],
    wanted: frozenset[str],
    *,
    everything: bool,
    fetched: frozenset[str],
    limit: int,
    deadline: Deadline,
    trashed: bool = False,
    scope_roots: Sequence[str] = (),
    scope_facts: ScopeFacts = NO_SCOPE_FACTS,
    view: Visibility | None = None,
) -> ScanNominees:
    """Scan-tier candidate entry rows in path order, capped at *limit*.

    Serves three callers with one executor: the permanent ``NOT
    encoded`` overlay (*everything* false), the ``allow_scan`` opt-out,
    and ``invert_match`` (*everything* true). Structural narrowing rides
    the same LIKE-superset arms as glob, and a scope's stored
    *scope_roots* ride glob's root fan beside them, with *scope_facts*
    beside each root OR; the flag partition and the content-kind gate
    ride beside the fan — the id-bounded fetch, not the fan plan, is
    what the budget protects here. The merge is pruned
    to the lowest ``limit + 1`` paths as arm chunks arrive (per-chunk
    top-``limit + 1`` is a correct merge input), and the deadline is
    consulted between chunks — an expired loop stops, and the caller's
    post-scan check records the truncation loudly. The ``NOT encoded``
    term wears the profile's rarity hint where one is declared, so a
    planner whose statistics average the column keeps the seek on the
    (encoded, kind) index rather than walking the path index for the
    few content rows awaiting the index; a directory never awaits it,
    and is created ``encoded``. Under a partial *view* every statement
    carries one packed group of the caller's compiled visibility
    clauses, merged within half the parameter budget and the depth
    budget, one statement per arm chunk per group, merged by path; the
    clauses are exact, so the cut counts only rows the caller may read,
    and every merged row still passes the view before the cut as a
    backstop. The statement's shape lets an engine start from the rows
    awaiting the index; on SQLite the rarity hint holds that seek, and
    another engine's planner may serve a group from the caller's own
    ranges or owner rows when its statistics say those are fewer. Each
    row the seek visits evaluates its statement's whole group, so a
    statement's engine work is the rows awaiting the index times the
    group's terms, and the deadline, read before each statement, does
    not interrupt one in flight; a predicate over a bound list of the
    caller's spans is the direction that stops that work growing with
    the caller's grants.
    """
    entry = tables.entry
    kinds = kind_membership(entry)
    base = [kinds.predicate]
    if not everything:
        base.append(rare(profile, ~entry.c.encoded))
    columns = [entry.c.entry_id, *(entry.c[field] for field in sorted((fetched | FETCH_RIDE) - {"content", "vid"}))]
    clauses = None if view is None else view.clauses()
    cap = min(parameter_budget // 2, profile.expression_depth_budget - EXPRESSION_DEPTH_RESERVE)
    groups = [] if clauses is None else _packed(clauses, cap)
    spend = max((group.binds for group in groups), default=0)
    rights: list[tuple[ColumnElement[bool], ...]] = [()] if clauses is None else [(g.predicate,) for g in groups]
    # The ext ride fits what the widest group leaves; wider, it drops to the gate.
    room = min(membership_budget, dialects.membership_budget(profile, parameter_budget - spend))
    ride = ext_membership(entry, wanted, room)
    if gates or scope_roots:
        built = (pattern_arm(entry, gate, wanted, profile, room, trashed=trashed) for gate in gates)
        arms = [arm for arm in built if arm is not None]
        chunk_size = arm_budget(profile, parameter_budget - spend, ARM_FIXED_BINDS + ride.binds + kinds.binds)
        wheres = [or_(*chunk) for chunk in chunked(arms, chunk_size)]
        wheres += scope_fan(
            entry,
            profile,
            parameter_budget,
            room,
            scope_roots,
            scope_facts,
            wanted,
            trashed=trashed,
            reserved=kinds.binds + spend,
        )
        if not wheres:
            return ScanNominees([], False)
    else:
        liveness = liveness_filters(entry, profile, include_meta=False, trashed=trashed)
        ridden = () if ride.predicate is None else (ride.predicate,)
        wheres = [and_(entry.c.path != "/", *liveness, *ridden)]
    merged: dict[str, RowMapping] = {}
    overflow = False
    for where, group in product(wheres, rights):
        if deadline.expired():
            break
        stmt = select(*columns).where(*base, where, *group).order_by(entry.c.path).limit(limit + 1)
        fetched_rows = list((await session.execute(stmt)).mappings())
        overflow = overflow or len(fetched_rows) > limit
        merged.update({mapping["path"]: mapping for mapping in fetched_rows})
        if len(merged) > limit + 1:
            merged = {path: merged[path] for path in sorted(merged)[: limit + 1]}
    rows = [merged[path] for path in sorted(merged) if view is None or view.holds(merged[path], view.need)]
    if len(rows) > limit:
        return ScanNominees(rows[:limit], True)
    return ScanNominees(rows, overflow)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _packed(clauses: Sequence[Clause], cap: int) -> list[Clause]:
    """Consecutive *clauses* merged into groups whose summed binds stay within *cap*.

    A clause wider than *cap* is a group of its own. Every unit of a
    clause spends at least one bind, so a group within the cap is at
    most that many terms deep.
    """
    groups: list[Clause] = []
    pending: list[Clause] = []
    spend = 0
    for clause in clauses:
        if pending and spend + clause.binds > cap:
            groups.append(Clause(or_(*(p.predicate for p in pending)), spend))
            pending, spend = [], 0
        pending.append(clause)
        spend += clause.binds
    if pending:
        groups.append(Clause(or_(*(p.predicate for p in pending)), spend))
    return groups
