"""What a mutation proves between its gate and its commit: its rows judged where it finds them, its rights fenced.

A data verb's gate judges the rows it reads and the paths it names. The
verb then reads again — the write plan its targets, an edge verb its
endpoints, a topology verb the rows beneath its roots — and acts on what
that read returns, which can be a row the gate never saw. Each such read
is judged here, in memory over the columns it already fetches, at the
rung the gate's own rule gives that row's role; and the attempt's last
statement before its commit reads the stamps of the caller's ids and of
the everyone principal, the fence, and compares them with the mount
revision the gate read first. A stamp newer than that revision is an
admin write committed while the verb ran that names the caller. A body
that created a row then proves that row's label, as the last statement
of all and for the system actor too: the everyone stamp, read again
under a shared lock (:func:`~vfs.storage.backends.database.labels.hold_postures`).

The commit point, per engine: where each statement reads the latest
commit (every SQL Server and Oracle verb, and the topology verbs on
Postgres and MariaDB), it is the fence; where vfs pins a repeatable
snapshot for writes (Postgres and MariaDB, with MariaDB's
``innodb_snapshot_isolation`` on), it is that snapshot, and the fence
agrees by construction; on SQLite, whose writers take the write lock at
their first statement, it is that statement. The same code runs on every
engine with no branch.

A move or copy also creates every mapped path beneath its destination,
and is judged at its gate by the rule a direct write of each of those
paths meets: the closed region — the paths beneath the destination
whose governing posture gives everyone less than the create rung and
the caller's own spans do not cover — is read from the posture rows and
shifted onto the source, and the least source row inside it is sought
with one ordered, limited seek per range piece. Its cost follows the
destination's rules, never the rows moved or copied.

Every judgment after the gate that fails, and a fence that finds the
rights moved, raises :class:`StaleSnapshot`: the attempt redrives, and
its fresh gate answers from one later state in the ladder's own words.
The one exception is a mapped path in a closed region carried by rows
the same call made or moved in an earlier pair, which no later state
can clear: it refuses in place once the fence has held. An exhausted
redrive is the existing retryable ``conflict`` with one of two fixed
phrases, neither naming a path.

    run = fenced(fn, host)                # the fence after a successful body
    gate = remember(session, gate, await opening(session, tables, who, cache), cache)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final, NamedTuple, cast

from sqlalchemy import and_, case, select, union_all

from vfs.authority import EVERYONE_NAME
from vfs.ops import VERB_RUNGS
from vfs.paths import ROOT, Path
from vfs.storage.backends.database.dialects import StaleSnapshot, arm_budget, chunked
from vfs.storage.backends.database.labels import hold_postures, label_of, posture_beneath
from vfs.storage.backends.database.membership import membership
from vfs.storage.backends.database.revision import principal_revision, read_revision
from vfs.storage.backends.database.rights import RIGHTS_FIELDS, denied, unauthenticated_at
from vfs.storage.backends.database.seams import seam
from vfs.storage.grants import LEVEL_RANK, RangeSet, normalise, pieces, posture_regions, subtract, union

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence

    from sqlalchemy import ColumnElement, Table
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.authority import Authority
    from vfs.models.rows import VFSTables
    from vfs.ops import Op, Rung
    from vfs.results import Result, ResultError
    from vfs.storage import ResolvedPair
    from vfs.storage.backends.database.dialects import DialectProfile
    from vfs.storage.backends.database.engine import EngineHost
    from vfs.storage.backends.database.rights import RightsCache, WriteGate
    from vfs.storage.backends.database.staging import StagedEntry, WritePlan
    from vfs.storage.grants import PostureRows, Rights

ATTEMPT_KEY: Final = "vfs_attempt"
"""The ``session.info`` key the attempt's gate and basis ride under; a session lives for one attempt."""

RIGHTS_MOVED: Final = "the caller's rights changed while it ran"
"""Why an attempt redrove when the fence found an admin write naming the caller."""

BEYOND_RIGHTS: Final = "a row it acts on is beyond the caller's rights as it now stands"
"""Why an attempt redrove when a row it acts on failed the caller's rights."""

# The ``session.info`` key that marks an attempt the fence runs over; an unmarked gate reads no opening revision.
_FENCED_KEY: Final = "vfs_fenced"

# Binds one probe arm spends at most: a range piece's two bounds, its limit,
# and the offset SQLite's compiler renders beside a limit (measured on each profile).
_PROBE_ARM_BINDS: Final = 4


class RightsBasis(NamedTuple):
    """What an attempt's gate decided under: the ids whose stamps can move it, and the revision read first.

    ``ids`` is sorted and holds the everyone principal; it is ``None``
    when the compile may mix two states, and the fence then redrives.
    """

    ids: tuple[str, ...] | None
    revision: int


class Opening(NamedTuple):
    """The gate's first read: the mount revision, and the ids the cache held for the caller before its resolve."""

    revision: int
    before: tuple[str, ...] | None


class Attempt(NamedTuple):
    """One attempt's gate, the basis its fence compares, and the destination posture rows the gate read.

    ``postures`` holds what a transfer's gate read at and beneath each
    destination it probed, so the pair that creates there reads them once:
    a posture written after the gate stamps everyone, and the fence redrives.
    """

    gate: WriteGate
    basis: RightsBasis | None
    postures: dict[str, PostureRows]


# ---------------------------------------------------------------------------
# The gate's record
# ---------------------------------------------------------------------------


async def opening(
    session: AsyncSession, tables: VFSTables, authority: Authority, cache: RightsCache | None
) -> Opening | None:
    """The revision a fenced gate opens under, read before anything else it reads; ``None`` where nothing is fenced.

    The system actor's rights never change, and a gate resolved without
    the cache is an admin write's, which holds the admin lock it took
    first: neither is fenced, and neither pays this read.
    """
    if authority.is_system or cache is None or not session.info.get(_FENCED_KEY):
        return None
    return Opening(await read_revision(session, tables), cache.ids(authority.subject_names))


def remember(session: AsyncSession, gate: WriteGate, opened: Opening | None, cache: RightsCache) -> WriteGate:
    """Put *gate* and its basis on *session*, replacing any record there, and return *gate*.

    The ids are the cache's for the caller before and after the resolve,
    with everyone: a posture write stamps everyone and narrows a named
    caller without stamping one of its ids. A resolve the cache did not
    keep leaves no ids after it, and its basis is unsettled.
    """
    basis: RightsBasis | None = None
    if opened is not None:
        after = cache.ids(gate.authority.subject_names)
        ids = None if after is None else tuple(sorted({*(opened.before or ()), *after, EVERYONE_NAME}))
        basis = RightsBasis(ids, opened.revision)
    session.info[ATTEMPT_KEY] = Attempt(gate, basis, {})
    return gate


async def admit_destinations(
    session: AsyncSession, host: EngineHost, gate: WriteGate, op: str, operations: Sequence[ResolvedPair]
) -> list[ResultError]:
    """One refusal per pair whose destination holds a mapped path a direct write by this caller could not create.

    Per pair: none when the caller's spans at the create rung cover the
    destination's subtree or its rights are whole; otherwise the posture
    rows at and beneath the destination (two statements) give the closed
    region, and with one, the region shifted onto the source is probed
    for its least row, one ordered seek per piece joined by ``UNION ALL``
    in chunks under the arm budget. A copy's arms read live rows only; a
    move carries its tombstoned descendants too. The least row over
    every chunk has no ancestor inside the region, so its mapped path is
    the component a direct write of it is refused at.
    """
    rung = gate.needs.create
    assert rung is not None
    rights = gate.resolution.at(rung)
    refusals: list[ResultError] = []
    for pair in operations:
        src, dest = str(pair.src), str(pair.dest)
        if dest == src or ROOT in (src, dest) or gate.whole or rights.covers_subtree(dest):
            continue
        postures = await posture_beneath(session, host.tables, host.profile, host.membership_budget, dest)
        session.info[ATTEMPT_KEY].postures[dest] = postures
        closed = _closed_region(postures, rights, dest)
        if not closed:
            continue
        shifted = RangeSet(tuple((src + lo[len(dest) :], src + hi[len(dest) :]) for lo, hi in closed))
        least = await _least_inside(session, host, shifted, live=op == "copy")
        if least is not None:
            mapped = dest + least[len(src) :]
            refused = unauthenticated_at(gate.authority, postures, mapped, rung)
            refusals.append(refused or denied(Path._brand(mapped), target=pair.dest))
    return refusals


async def destination_postures(
    session: AsyncSession, tables: VFSTables, profile: DialectProfile, membership_budget: int, dest: str
) -> PostureRows:
    """The posture in force at *dest* and every posture row beneath it: the gate's read when it made one."""
    attempt: Attempt | None = session.info.get(ATTEMPT_KEY)
    held = None if attempt is None else attempt.postures.get(dest)
    postures = held if held is not None else await posture_beneath(session, tables, profile, membership_budget, dest)
    # Where a test stages a rival posture change: the postures are read and no row is stamped yet.
    await seam("transfer:after-postures")
    return postures


# ---------------------------------------------------------------------------
# The fence
# ---------------------------------------------------------------------------


def fenced(
    fn: Callable[[AsyncSession], Awaitable[Result]], host: EngineHost
) -> Callable[[AsyncSession], Awaitable[Result]]:
    """*fn* with the fence after it: a successful body proves its caller's rights still stand before it commits.

    A body that minted a row then proves that row's label the same
    way, last: the system actor's too, since a label is not its rights
    but what every other caller's read is judged by.
    """

    async def run(session: AsyncSession) -> Result:
        session.info[_FENCED_KEY] = True
        result = await fn(session)
        if result.success:
            await hold_rights(session, host.tables, host.profile, host.membership_budget)
            await hold_postures(session, host.tables, host.profile)
        return result

    return run


async def hold_rights(
    session: AsyncSession, tables: VFSTables, profile: DialectProfile, membership_budget: int
) -> None:
    """Raise :class:`StaleSnapshot` when an admin write naming the caller committed after its gate opened.

    One chunked read of the stamps over the basis's ids, taking no lock;
    an attempt with no fenced gate returns at once, and an unsettled
    basis redrives without a read.
    """
    attempt: Attempt | None = session.info.get(ATTEMPT_KEY)
    if attempt is None or attempt.basis is None:
        return
    basis = attempt.basis
    if basis.ids is None:
        raise StaleSnapshot(RIGHTS_MOVED)
    if await principal_revision(session, tables, profile, membership_budget, basis.ids) > basis.revision:
        raise StaleSnapshot(RIGHTS_MOVED)


# ---------------------------------------------------------------------------
# The rows a verb finds after its gate
# ---------------------------------------------------------------------------


def judging(session: AsyncSession, rung: Rung) -> Rights | None:
    """The attempt gate's rights at *rung*; ``None`` with no gate on *session* or rights that are whole."""
    attempt: Attempt | None = session.info.get(ATTEMPT_KEY)
    if attempt is None or attempt.gate.whole:
        return None
    return attempt.gate.resolution.at(rung)


def admit(rights: Rights | None, rows: Iterable[Mapping[Any, Any]]) -> None:
    """Raise :class:`StaleSnapshot` when *rights* fail any of *rows*, each judged at its own path, owner and label."""
    if rights is None:
        return
    if any(not rights.admits(row["path"], row["owner_id"], row["everyone_level"]) for row in rows):
        raise StaleSnapshot(BEYOND_RIGHTS)


async def admit_passed(session: AsyncSession, rung: Rung, rows: Sequence[Mapping[Any, Any]], *, trashed: bool) -> None:
    """Judge live rows a verb only passes, at its passing *rung*, as the gate judged them.

    The gate's rule for a live, named target at a passing slot, term by
    term: the row passes when the caller holds *rung* on it; failing that,
    at a ``list`` slot a directory passes when it is on the caller's road,
    the live road and, with *trashed* (mkedge's ``targets`` leg, never
    rmedge's ``named``), the road through the trash view. The target's
    ancestors are not judged again: a row resolved at the same path keeps
    the chain the gate judged. The road is read only for a directory the
    rights alone refuse: one statement for the rows everyone may name and
    one per owner arm, per road read, never per row.
    """
    rights = judging(session, rung)
    if rights is None:
        return
    barred = [row for row in rows if not rights.admits(row["path"], row["owner_id"], row["everyone_level"])]
    if not barred:
        return
    attempt: Attempt = session.info[ATTEMPT_KEY]
    doors = [row["path"] for row in barred if row["kind"] == "directory"] if rung == "list" else []
    road = await attempt.gate.view.road(session, doors) if doors else set()
    rest = [door for door in doors if door not in road] if trashed else []
    road |= await attempt.gate.view.road(session, rest, trashed=True) if rest else set()
    if any(row["path"] not in road for row in barred):
        raise StaleSnapshot(BEYOND_RIGHTS)


def admit_targets(session: AsyncSession, op: str, live: Mapping[str, Any], targets: Sequence[Path]) -> None:
    """Judge every live target row the plan read at the verb's primary rung, before any is matched or answered from."""
    rows = [live[str(target)] for target in targets if str(target) in live]
    admit(judging(session, VERB_RUNGS[cast("Op", op)].primary), rows)


def admit_staged(session: AsyncSession, op: str, plan: WritePlan, primary: Rung | None = None) -> None:
    """Judge every update or revive the plan staged, by the row its own read returned for it.

    A revive at restore's primary rung, every other update at the
    verb's, the owner floor riding: the rule the gate gives a tombstoned
    and an occupied target. The undisturbed plan judges the rows the
    gate judged and passes. *primary* names the rung of an update whose
    gate judged it below the verb's own, as an append's did.
    """
    staged = [entry for entry in plan.staged.values() if entry.persistence == "update"]
    revived = [plan.committed[str(entry.path)] for entry in staged if entry.revive]
    changed = [plan.committed[str(entry.path)] for entry in staged if not entry.revive]
    admit(judging(session, VERB_RUNGS["restore"].primary), revived)
    admit(judging(session, primary or VERB_RUNGS[cast("Op", op)].primary), changed)


async def admit_landed(
    session: AsyncSession,
    entry: Table,
    profile: DialectProfile,
    membership_budget: int,
    creates: Sequence[StagedEntry],
    minted: frozenset[str],
) -> None:
    """Judge every row a create landed on — an absorb or a clobber — at the primary rung, the owner floor riding.

    Read after the statement that changed them, so the attempt holds
    their row locks and sees its own change at any isolation; a batch
    where no create landed issues no statement.
    """
    rights = judging(session, VERB_RUNGS["write"].primary)
    landed = [s.entry_id for s in creates if s.entry_id not in minted and s.persistence != "adopt"]
    if rights is None or not landed:
        return
    columns = [entry.c.path, *(entry.c[name] for name in sorted(RIGHTS_FIELDS))]
    for chunk in chunked(landed, membership_budget):
        found = await session.execute(select(*columns).where(membership(entry.c.entry_id, chunk, profile)))
        admit(rights, found.mappings())


async def admit_beneath(session: AsyncSession, roots: Sequence[Path]) -> None:
    """Run the gate's subtree judgment over *roots* again at its primary rung; a refusal redrives."""
    attempt: Attempt | None = session.info.get(ATTEMPT_KEY)
    if attempt is None or attempt.gate.whole or not roots:
        return
    gate = attempt.gate
    if await gate.subtrees(session, roots, gate.needs.primary):
        raise StaleSnapshot(BEYOND_RIGHTS)


async def admit_created(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    rung: Rung,
    postures: PostureRows,
    rows: Iterable[tuple[str, str]],
    own: set[str],
) -> ResultError | None:
    """Judge each mapped path a transfer is about to create, by the label it stamps there; ``None`` when all pass.

    *rows* are ``(mapped path, source entry id)``. A failure on rows
    this call made or moved in an earlier pair (*own*) is no race and is
    refused in place at the least failing path, once the fence has
    held; any other failure redrives.
    """
    rights = judging(session, rung)
    if rights is None:
        return None
    failing = [(path, entry_id) for path, entry_id in rows if not rights.reaches(path, label_of(postures, path))]
    if not failing:
        return None
    if any(entry_id not in own for _, entry_id in failing):
        raise StaleSnapshot(BEYOND_RIGHTS)
    await hold_rights(session, tables, profile, membership_budget)
    least = min(path for path, _ in failing)
    attempt: Attempt = session.info[ATTEMPT_KEY]
    return unauthenticated_at(attempt.gate.authority, postures, least, rung) or denied(Path._brand(least))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _closed_region(postures: PostureRows, rights: Rights, dest: str) -> RangeSet:
    """The paths strictly beneath *dest* a creation by *rights* is refused at: posture below the rung, no span."""
    regions = posture_regions(postures)
    reached = [region for level, region in regions.items() if LEVEL_RANK[level] >= rights.need]
    opened = rights.spans
    for region in reached:
        opened = union(opened, region)
    return subtract(normalise([(dest + "/", dest + "0")]), opened)


async def _least_inside(session: AsyncSession, host: EngineHost, region: RangeSet, *, live: bool) -> str | None:
    """The least path of a row inside *region*: one ordered, limited seek per piece, chunked under the arm budget."""
    entry = host.tables.entry
    found = pieces(region)
    terms: list[ColumnElement[bool]] = [entry.c.path == point for point in found.points]
    terms += [and_(entry.c.path > lo, entry.c.path < hi) for lo, hi in found.opens]
    # A liveness term no index serves: bare, a planner with no statistics seeks the tombstone index instead.
    alive = [case((entry.c.deleted_at.is_(None), 1), else_=0) == 1] if live else []
    least: str | None = None
    for chunk in chunked(terms, arm_budget(host.profile, host.parameter_budget, _PROBE_ARM_BINDS)):
        arms = [
            select(entry.c.path).where(term, *alive).order_by(entry.c.path).limit(1).subquery().select()
            for term in chunk
        ]
        for path in (await session.execute(union_all(*arms))).scalars():
            least = path if least is None or path < least else least
    return least
