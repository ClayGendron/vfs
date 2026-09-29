"""The structural scope every content search shares — grep's and glean's.

Scoping crosses the storage seam as pattern text on the ``globs``
channels (the router composes scope roots into them) plus the two
``ext`` channels. This module holds the pieces both verbs stand on:
the authoritative per-row gate (:func:`passes_gates`), the SQL terms a
candidate fetch may ride beside its id chunk (:func:`pushdown_terms`,
with true bind accounting), and the scan side's bounded, structurally
prefiltered fetch of the ``NOT encoded`` overlay (:func:`entries_for_scan`).
The gate is the law; every pushdown only narrows toward it.
"""

from __future__ import annotations

from time import monotonic
from typing import TYPE_CHECKING, Final, NamedTuple

from sqlalchemy import and_, or_, select

from vfs.paths import _under_meta_root
from vfs.pattern_matching import ROW_GATE_FIELDS, passes_row_filters
from vfs.storage.backends.database.descent import LIKE_ESCAPE, escape_like, liveness_filters
from vfs.storage.backends.database.dialects import arm_budget, chunked
from vfs.storage.backends.database.reads import (
    ARM_FIXED_BINDS,
    ext_membership,
    kind_membership,
    meta_scoped,
    pattern_arm,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy import ColumnElement, Table
    from sqlalchemy.engine import RowMapping
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models.rows import VFSTables
    from vfs.pattern_matching import GlobFilter
    from vfs.storage.backends.database.dialects import DialectProfile
    from vfs.storage.backends.database.pathterms import ChannelTerms

# Ceiling of one channel arm's bind slots: the ext pair and the name fact.
CHANNEL_ARM_BINDS: Final = 3

# Columns every candidate fetch rides beside the caller's mask: the row-gate
# facts, size_bytes (prices the content read), owner_id (the owner floor).
FETCH_RIDE: Final = ROW_GATE_FIELDS | {"size_bytes", "owner_id"}


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


# Ceiling of one channel arm's bind slots: the ext pair and the name fact.


# ---------------------------------------------------------------------------
# The gate — the authority every row passes
# ---------------------------------------------------------------------------


def passes_gates(
    mapping: RowMapping,
    gates: list[GlobFilter],
    not_gates: list[GlobFilter],
    wanted: frozenset[str],
    unwanted: frozenset[str],
) -> bool:
    """The authoritative structural gates, per candidate, off the row's own facts.

    Matches raw strings — the stored ``name`` and ``ext`` columns mirror
    the path by invariant, so no ``Path`` is minted per candidate. A
    meta row is admitted only by a gate whose literal prefix addresses
    the meta subtree — default enumeration hides ``/.vfs`` even when a
    wildcard gate would match it. The rest is the shared filter law.
    """
    path, name, ext = mapping["path"], mapping["name"], mapping["ext"]
    if _under_meta_root(path) and not any(gate.hits(path, name, ext) and meta_scoped(gate.pattern) for gate in gates):
        return False
    return passes_row_filters(path, name, ext, gates, not_gates, wanted, unwanted)


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
) -> Pushdown:
    """The SQL terms the candidate fetch may carry beside the id chunk.

    With no admission gates the meta scope moves into SQL — the string
    gate may then be skipped entirely. The caller's wanted-ext set rides
    under the membership rule, and the channel's compiled column facts
    ride as an OR over arms; both only ever narrow toward the authority,
    never past it. The whole ride is capped at half the membership
    budget so the id chunk always keeps room, and a channel wider than
    *fan_arms* (the caller's channel fan, one OR branch per arm) is
    dropped whole — narrowing is a convenience the statement may
    decline; ``passes_gates`` stays the authority.
    """
    terms: list[ColumnElement[bool]] = []
    binds = 0
    if hide_meta:
        liveness = liveness_filters(entry, profile, include_meta=False)
        terms.extend(liveness)
        binds += static_binds(liveness)
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


async def entries_for_scan(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    parameter_budget: int,
    membership_budget: int,
    gates: list[GlobFilter],
    wanted: frozenset[str],
    *,
    everything: bool,
    fetched: frozenset[str],
    limit: int,
    deadline: float,
) -> ScanNominees:
    """Scan-tier candidate entry rows in path order, capped at *limit*.

    Serves three callers with one executor: the permanent ``NOT
    encoded`` overlay (*everything* false), the ``allow_scan`` opt-out,
    and ``invert_match`` (*everything* true). Structural narrowing rides
    the same LIKE-superset arms as glob; the flag partition and the
    content-kind gate ride beside the fan — the id-bounded fetch, not
    the fan plan, is what the budget protects here. The merge is pruned
    to the lowest ``limit + 1`` paths as arm chunks arrive (per-chunk
    top-``limit + 1`` is a correct merge input), and the deadline is
    consulted between chunks — an expired loop stops, and the caller's
    post-scan check records the truncation loudly.
    """
    entry = tables.entry
    kinds = kind_membership(entry)
    base = [kinds.predicate]
    if not everything:
        base.append(~entry.c.encoded)
    columns = [entry.c.entry_id, *(entry.c[field] for field in sorted((fetched | FETCH_RIDE) - {"content"}))]
    merged: dict[str, RowMapping] = {}
    overflow = False
    if gates:
        built = (pattern_arm(entry, gate, wanted, profile, membership_budget) for gate in gates)
        arms = [arm for arm in built if arm is not None]
        if not arms:
            return ScanNominees([], False)
        ride = ext_membership(entry, wanted, membership_budget)
        chunk_size = arm_budget(profile, parameter_budget, ARM_FIXED_BINDS + ride.binds + kinds.binds)
        for chunk in chunked(arms, chunk_size):
            if monotonic() > deadline:
                break
            stmt = select(*columns).where(*base, or_(*chunk)).order_by(entry.c.path).limit(limit + 1)
            fetched_rows = list((await session.execute(stmt)).mappings())
            overflow = overflow or len(fetched_rows) > limit
            merged.update({mapping["path"]: mapping for mapping in fetched_rows})
            if len(merged) > limit + 1:
                merged = {path: merged[path] for path in sorted(merged)[: limit + 1]}
    else:
        terms = [*base, entry.c.path != "/", *liveness_filters(entry, profile, include_meta=False)]
        ride = ext_membership(entry, wanted, membership_budget)
        if ride.predicate is not None:
            terms.append(ride.predicate)
        stmt = select(*columns).where(*terms).order_by(entry.c.path).limit(limit + 1)
        merged = {mapping["path"]: mapping for mapping in (await session.execute(stmt)).mappings()}
    rows = [merged[path] for path in sorted(merged)]
    if len(rows) > limit:
        return ScanNominees(rows[:limit], True)
    return ScanNominees(rows, overflow)
