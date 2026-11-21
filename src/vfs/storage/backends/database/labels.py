"""The everyone level on the row — stamped at every mint, rewritten when a posture changes.

``entries.everyone_level`` holds, for each row, the level the deepest
covering posture row (principal ``*``) gives everyone at the row's path,
as its rank on the ladder: ``0`` none, ``1`` list, ``2`` read, ``3``
add, ``4`` contribute, ``5`` read_write. It is derived, never
authoritative: the posture rows stay the truth, and every function here
computes from them. A partial caller's read seeks it through the
``(everyone_level, path)`` index instead of carrying every other
principal's posture in its predicate.

Three moments write it. A write or a mkdir, with every parent it
creates, asks :func:`labels_for` once per batch: one chunked read of the
posture rows among the batch's distinct ancestor prefixes, then a
dictionary walk per path. A transfer (move, copy) asks
:func:`posture_beneath` for the posture in force at its destination and
every posture row under it, and stamps each row it rewrites or creates
from that map. A delete and a restore stamp nothing: the row keeps its
label, which a relabel reaches where the row sits. A posture change
marks its row as *in flight*
(:func:`mark_relabel`, in the transaction that writes the posture row)
and the :class:`Relabeller` then rewrites the subtree under the path
minus the subtrees of every deeper posture row, one bounded chunk per
transaction, as sorted path ranges joined to the ``path`` index in the
spelling each engine was measured to seek on; the last chunk clears the
mark. While the mark stands, every reader compiles that posture row as a
cover or a hole over the region (:func:`inflight_marks`,
:func:`inflight_postures`), so the new posture is in force from the
moment it is written and a relabel that dies leaves nothing wrong, only
work for the next ``set_posture`` call to finish. The marks key every
compile made while they stand: a mark carries the revision it was
planted under, so clearing it retires those compiles and the ones made
before it stand again — a settled relabel changed labels, not rights.
:func:`rebuild_labels` recomputes every row from the posture rows, for
maintenance and for tests.

A mint proves the label it stamps. The posture rows it read can be
overtaken by a posture change that commits while it runs, and nothing
rewrites a row the relabel never saw. So an attempt reads the everyone
stamp before its first label read (:func:`watch_postures`) and again
as its last statement, under a shared lock held to the commit
(:func:`hold_postures`): a stamp that moved redrives the attempt, and a
posture write that arrives later waits for the mint's commit, so its
relabel finds the mint's rows. That is two statements for a call that
creates a row, at any batch size; a call that reads a
label and is then refused pays the first alone, and a call that reads
no label pays neither. Mints share the lock and never wait for each
other. A posture write waits for the holds in flight when it arrives
and for no later one (:func:`open_relabel`; on Postgres it locks the
stamps table first, or later mints would pass it). While a posture
write is open, calls that create a row and other rights changes wait
for that one transaction; a read, a search and an edit of an existing
file do not. A waiting create holds its parent's row, so a delete,
move, copy or restore beneath that parent waits with it, and through
the topology row every other topology verb waits behind that one.
The stamp is one for the mount, so every posture write redrives every
mint in flight, at the posture writer's own rate: a batch that meets one
in each of its attempts lands nothing and answers a retryable conflict,
so a host that sets many postures does it outside its ingest window.
On Postgres two mints holding the row at once make a multixact, as every
foreign-key check does.

A deleted row stays at its path with a tombstone and keeps its label,
so a posture change after the delete reaches it exactly as it reaches
its live neighbours: every relabel statement runs once, over ``path``.

    labels = await labels_for(session, tables, profile, budget, ["/eng/new.md"])
    labels["/eng/new.md"]      # 5 under a read_write root
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final, NamedTuple, cast

from sqlalchemy import and_, delete, func, insert, or_, select, text, update

from vfs.authority import EVERYONE_NAME
from vfs.paths import ROOT
from vfs.storage.backends.database.descent import LIKE_ESCAPE, escape_like
from vfs.storage.backends.database.dialects import StaleSnapshot, chunked, lock_rows
from vfs.storage.backends.database.membership import membership
from vfs.storage.backends.database.ranges import open_rows, range_counts
from vfs.storage.backends.database.revision import bump_revision, hold_revision, stamp_principals
from vfs.storage.backends.database.seams import seam
from vfs.storage.grants import (
    FULL,
    LEVEL_RANK,
    NO_SPANS,
    RangeSet,
    above,
    ancestors_and_self,
    cover,
    cover_all,
    end,
    level_at,
    minimise,
    pieces,
    posture_regions,
    subtract,
    through,
    union,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from sqlalchemy import Executable, Table, TextClause, Update
    from sqlalchemy.engine import CursorResult
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.deadline import Deadline
    from vfs.models.rows import VFSTables
    from vfs.storage.backends.database.dialects import DialectProfile
    from vfs.storage.grants import GrantLevel, Open, PostureRows, Span


class Relabel(NamedTuple):
    """What a relabel did: rows rewritten, update statements run, and chunk transactions committed."""

    rows: int
    statements: int
    transactions: int = 0

    def plus(self, other: Relabel) -> Relabel:
        return Relabel(
            self.rows + other.rows, self.statements + other.statements, self.transactions + other.transactions
        )


# ---------------------------------------------------------------------------
# Labels for new rows
# ---------------------------------------------------------------------------


async def posture_rows(
    session: AsyncSession, tables: VFSTables, profile: DialectProfile, membership_budget: int, prefixes: Iterable[str]
) -> dict[str, GrantLevel]:
    """The posture rows among *prefixes*: ``prefix → level``, one chunked read."""
    grants = tables.grants
    postures: dict[str, GrantLevel] = {}
    for chunk in chunked(sorted(set(prefixes)), membership_budget):
        stmt = select(grants.c.path_prefix, grants.c.level).where(
            grants.c.principal_id == EVERYONE_NAME, membership(grants.c.path_prefix, chunk, profile)
        )
        postures.update({row.path_prefix: row.level for row in await session.execute(stmt)})
    return postures


async def posture_rows_for_chunks(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    chunks: Sequence[Sequence[str]],
    *,
    deadline: Deadline,
) -> dict[str, GrantLevel] | None:
    """The posture rows among pre-sorted, pre-chunked *chunks*, issued as given; ``None`` past *deadline*.

    The read half of an off-loop posture gate: the chain was deduplicated,
    sorted and cut on a worker, so the loop holds one statement's build
    at a time and never the chain's sort. The deadline is read before
    each chunk, and a read that reaches it stops whole.
    """
    grants = tables.grants
    postures: dict[str, GrantLevel] = {}
    for chunk in chunks:
        if deadline.expired():
            return None
        stmt = select(grants.c.path_prefix, grants.c.level).where(
            grants.c.principal_id == EVERYONE_NAME, membership(grants.c.path_prefix, chunk, profile)
        )
        postures.update({row.path_prefix: row.level for row in await session.execute(stmt)})
    return postures


async def labels_for(
    session: AsyncSession, tables: VFSTables, profile: DialectProfile, membership_budget: int, paths: Iterable[str]
) -> dict[str, int]:
    """Each of *paths*' everyone level, from the posture rows on its ancestor chain.

    One read for the whole batch: the distinct ancestors of every path
    (a batch of 10,000 files under one folder shares most of them),
    chunked under the membership budget.
    """
    wanted = list(dict.fromkeys(paths))
    if wanted:
        await watch_postures(session, tables)
    prefixes = {ancestor for path in wanted for ancestor in ancestors_and_self(path)}
    postures = await posture_rows(session, tables, profile, membership_budget, prefixes)
    labels = {path: label_of(postures, path) for path in wanted}
    # Where a test stages a rival posture change: the labels are read and no row is stamped yet.
    await seam("write:after-labels")
    return labels


async def posture_beneath(
    session: AsyncSession, tables: VFSTables, profile: DialectProfile, membership_budget: int, root: str
) -> dict[str, GrantLevel]:
    """The posture in force at *root* and every posture row beneath it.

    What a transfer labels its rows from: the destination's own level,
    collapsed onto *root* from its ancestor chain, plus the deeper rows
    that decide beneath it. :func:`label_of` over this map answers for
    any path under *root* as the whole table would.
    """
    await watch_postures(session, tables)
    above_root = await posture_rows(session, tables, profile, membership_budget, ancestors_and_self(root))
    postures: dict[str, GrantLevel] = {root: level_at(above_root, root)}
    postures.update(await _deeper_postures(session, tables, profile, root))
    return postures


def label_of(postures: PostureRows, path: str) -> int:
    """The stored label for *path* under *postures*."""
    return LEVEL_RANK[level_at(postures, path)]


# ---------------------------------------------------------------------------
# The proof — a label against a posture change committed inside a mint's window
# ---------------------------------------------------------------------------

# What a mint answers when a posture changed under every attempt it had; it names no path.
POSTURE_MOVED: Final = "a posture changed while it ran"

# Where an attempt keeps the everyone stamp its labels were read under.
_WATCHED_KEY: Final = "vfs_posture_stamp"


async def watch_postures(session: AsyncSession, tables: VFSTables) -> None:
    """Read the everyone stamp once an attempt, before its first read of the posture rows.

    Every posture write moves that stamp, so the value read here names
    the posture rows the attempt's labels come from. A row that is
    missing reads as zero; :func:`hold_postures` is what refuses it.
    """
    if _WATCHED_KEY in session.info:
        return
    revisions = tables.principal_revisions
    stamp = select(revisions.c.revision).where(revisions.c.principal_id == EVERYONE_NAME)
    session.info[_WATCHED_KEY] = int((await session.execute(stamp)).scalar_one_or_none() or 0)


async def hold_postures(session: AsyncSession, tables: VFSTables, profile: DialectProfile) -> None:
    """Raise :class:`StaleSnapshot` when a posture write committed since the watch, and hold the next one out.

    The last statement a minting attempt issues: the stamp read again
    under the profile's shared lock, held to the commit. Mints share
    it, so none waits for another; a posture write takes the row whole
    and waits behind it, so its relabel starts after the mint's rows
    are visible. An attempt that read no label returns at once. A
    missing row is refused too: a lock on no row holds nothing.
    """
    watched = session.info.get(_WATCHED_KEY)
    if watched is None:
        return
    if await _stamp_under_share(session, tables, profile) != watched:
        raise StaleSnapshot(POSTURE_MOVED)


async def open_relabel(
    session: AsyncSession, tables: VFSTables, profile: DialectProfile, path: str, revision: int
) -> None:
    """A posture write's first acts: queue later mints behind it, stamp everyone, mark the relabel in flight.

    Where the profile declares a door, the stamps table is locked
    first in a mode that holds back a mint's shared read and lets a
    plain read through: without it a mint that arrives while this
    write waits is granted beside the mints already there, and mints
    that keep arriving could hold a posture change off. The lock is
    held for this one short transaction; calls that create a row and
    other rights changes wait behind it, and no read does.
    """
    if profile.share_lock.door:
        await session.execute(_lock_stamps(session, tables, "EXCLUSIVE"))
    await stamp_principals(session, tables, [EVERYONE_NAME], revision)
    await mark_relabel(session, tables, path, revision)
    # Where a test holds a posture write open with its locks taken.
    await seam("posture:after-stamp")


# ---------------------------------------------------------------------------
# In flight — the posture rows whose relabel has not settled
# ---------------------------------------------------------------------------


class Mark(NamedTuple):
    """One pending relabel: the posture row's path and the revision its mark was planted under."""

    path: str
    revision: int


async def mark_relabel(session: AsyncSession, tables: VFSTables, path: str, revision: int) -> None:
    """Record that *path*'s relabel is pending under *revision* — from the top again if one already was.

    Written in the transaction that writes the posture row, under the
    admin lock, so the mark and the row land together or not at all.
    The mark's revision keys every compile made while it stands, so a
    second posture change on the same path retires the first's compiles.
    """
    relabels = tables.relabels
    reset = update(relabels).where(relabels.c.path_prefix == path).values(revision=revision, cursor=None)
    if cast("CursorResult[Any]", await session.execute(reset)).rowcount == 0:
        await session.execute(insert(relabels).values(path_prefix=path, revision=revision, cursor=None))


async def inflight_marks(session: AsyncSession, tables: VFSTables) -> tuple[Mark, ...]:
    """The pending relabels in path order — one read of a table that is normally empty."""
    relabels = tables.relabels
    rows = await session.execute(select(relabels.c.path_prefix, relabels.c.revision).order_by(relabels.c.path_prefix))
    return tuple(Mark(row.path_prefix, row.revision) for row in rows)


async def inflight_postures(
    session: AsyncSession, tables: VFSTables, profile: DialectProfile, membership_budget: int, marks: Sequence[Mark]
) -> dict[str, GrantLevel]:
    """Every posture row at or beneath a pending *marks* path — what a reader's window is compiled from.

    Nothing to read without marks. With marks standing, one read of the
    marked rows and one of the rows beneath each outermost mark: the cost
    follows the marks, which are the posture changes under way.
    """
    if not marks:
        return {}
    pending = [mark.path for mark in marks]
    postures = await posture_rows(session, tables, profile, membership_budget, pending)
    for root in minimise(pending):
        postures.update(await _deeper_postures(session, tables, profile, root))
    return postures


# ---------------------------------------------------------------------------
# The relabel — a posture change rewrites its subtree, one chunk per transaction
# ---------------------------------------------------------------------------


class Relabeller:
    """Drives every pending relabel to its end, one bounded chunk per call.

    Each :meth:`step` is one transaction: take the admin lock, read the
    marks, and rewrite the next chunk of the first one — at most
    ``in_list_budget`` pieces in a statement and ``relabel_rows`` rows in
    the chunk — then move the mark's cursor past it, or clear the mark
    and bump the revision when the region is done. The region is the
    marked path's cover minus every deeper posture row's, sized by the
    posture rows under the path and never by the mount; the posture rows
    are read under the lock, so a chunk never writes a level a rival
    posture change has already replaced.

    The plan — the region's open ranges counted once, then grouped in
    path order so every chunk fits both caps, a range larger than a
    chunk walked by keyset — is kept across steps and remade whenever
    the revision or the cursor is not the one it was made under: a rival
    admin write, or another driver on the same mark, retires it. A step
    that dies leaves the mark and its cursor; the next driver resumes
    from there.
    """

    def __init__(self, tables: VFSTables, profile: DialectProfile, membership_budget: int) -> None:
        self._tables = tables
        self._profile = profile
        self._membership_budget = membership_budget
        self._plan: _Plan | None = None

    async def step(self, session: AsyncSession) -> Relabel | None:
        """Rewrite one chunk of the first pending relabel; ``None`` when no relabel is pending."""
        tables = self._tables
        relabels = tables.relabels
        revision = await hold_revision(session, tables)
        marks = select(relabels.c.path_prefix, relabels.c.cursor).order_by(relabels.c.path_prefix)
        mark = (await session.execute(marks)).first()
        if mark is None:
            return None
        plan = self._plan
        if plan is None or (plan.path, plan.revision, plan.cursor) != (mark.path_prefix, revision, mark.cursor):
            plan = await self._planned(session, mark.path_prefix, mark.cursor, revision)
        done = Relabel(0, 0, 1)
        if plan.batches:
            step, cursor = await self._advance(session, plan)
            done = done.plus(step)
            if plan.batches:
                settle = update(relabels).where(relabels.c.path_prefix == plan.path).values(cursor=cursor)
                await session.execute(settle)
                self._plan = plan._replace(cursor=cursor)
                return done
        await session.execute(delete(relabels).where(relabels.c.path_prefix == plan.path))
        await bump_revision(session, tables)
        self._plan = None
        return done

    async def _planned(self, session: AsyncSession, path: str, cursor: str | None, revision: int) -> _Plan:
        """The chunks left for *path*'s relabel past *cursor*, from the posture rows as they stand."""
        tables, profile, budget = self._tables, self._profile, self._membership_budget
        chain = await posture_rows(session, tables, profile, budget, ancestors_and_self(path))
        rank = LEVEL_RANK[level_at(chain, path)]
        deeper = await _deeper_postures(session, tables, profile, path)
        spans = subtract(cover(path), cover_all(deeper))
        if cursor is not None:
            spans = above(spans, cursor)
        counts = await self._counted(session, spans)
        return _Plan(
            path, revision, cursor, rank, _batched(spans, counts, profile.in_list_budget, profile.relabel_rows)
        )

    async def _counted(self, session: AsyncSession, spans: RangeSet) -> dict[Open, int]:
        """Rows inside each open range of *spans*: the ranges drive one count statement per budget of them."""
        entry, profile = self._tables.entry, self._profile
        opens = pieces(spans).opens
        counts: dict[Open, int] = {}
        if profile.range_source is None:
            for lo, hi in opens:
                stmt = select(func.count()).where(entry.c.path > lo, entry.c.path < hi)
                counts[lo, hi] = (await session.execute(stmt)).scalar_one()
            return counts
        for chunk in chunked(opens, profile.in_list_budget):
            for lo, hi, count in await session.execute(range_counts(entry, chunk, profile)):
                counts[lo, hi] = count
        return counts

    async def _advance(self, session: AsyncSession, plan: _Plan) -> tuple[Relabel, str]:
        """Rewrite the plan's next chunk; what it did and the last path it reached."""
        batch = plan.batches.pop(0)
        if batch.walked:
            boundary = await self._boundary(session, batch.spans)
            if boundary is not None:
                plan.batches.insert(0, _Batch(above(batch.spans, boundary), walked=True))
                batch = _Batch(through(batch.spans, boundary), walked=False)
        done = await relabel_spans(
            session, self._tables, self._profile, self._membership_budget, plan.rank, batch.spans
        )
        return done, end(batch.spans)

    async def _boundary(self, session: AsyncSession, spans: RangeSet) -> str | None:
        """The path a chunk of the one open range in *spans* may run through; ``None`` when the rest fits.

        The probe offsets past ``relabel_rows`` less the two edge points a
        span may add, so the chunk through the boundary never exceeds it.
        """
        entry = self._tables.entry
        [(lo, hi)] = pieces(spans).opens
        stmt = (
            select(entry.c.path)
            .where(entry.c.path > lo, entry.c.path < hi)
            .order_by(entry.c.path)
            .limit(1)
            .offset(max(0, self._profile.relabel_rows - 2))
        )
        return (await session.execute(stmt)).scalar_one_or_none()


async def relabel_spans(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    rank: int,
    spans: RangeSet,
) -> Relabel:
    """Set every row judged inside *spans* to *rank*: exact paths by membership, open ranges by the dialect's seek.

    Points travel in membership chunks; open ranges in chunks of at most
    ``in_list_budget`` pairs, one bound value per statement where the
    dialect unpacks one. No statement grows with the number of rows it
    touches, and none carries more pairs than the tightest engine cap;
    the rows a statement touches are the caller's to bound.
    """
    found = pieces(spans)
    entry = tables.entry
    rows = statements = 0
    for chunk in chunked(found.points, membership_budget):
        stmt = update(entry).where(membership(entry.c.path, chunk, profile)).values(everyone_level=rank)
        rows += await _run(session, stmt, {})
        statements += 1
    for chunk in chunked(found.opens, profile.in_list_budget):
        rows += await _run(session, _relabel_opens(entry, profile, rank, chunk), {})
        statements += 1
    return Relabel(rows, statements)


async def rebuild_labels(
    session: AsyncSession, tables: VFSTables, profile: DialectProfile, membership_budget: int
) -> Relabel:
    """Every row's label recomputed from the posture rows — the maintenance rebuild.

    Reads the whole posture set once (one row per posture, in memory;
    the profile at a hundred thousand postures is a few megabytes) and
    rewrites each level's region, then the paths no posture row covers,
    each as chunked range statements in the caller's one transaction —
    a whole-corpus write, honest to its purpose. Every label is right
    afterwards, so every pending mark is cleared and the revision bumped.
    """
    grants = tables.grants
    stmt = select(grants.c.path_prefix, grants.c.level).where(grants.c.principal_id == EVERYONE_NAME)
    postures: dict[str, GrantLevel] = {row.path_prefix: row.level for row in await session.execute(stmt)}
    regions = posture_regions(postures)
    covered = NO_SPANS
    done = Relabel(0, 0)
    for level, spans in regions.items():
        done = done.plus(await relabel_spans(session, tables, profile, membership_budget, LEVEL_RANK[level], spans))
        covered = union(covered, spans)
    rest = subtract(FULL, covered)
    done = done.plus(await relabel_spans(session, tables, profile, membership_budget, LEVEL_RANK["none"], rest))
    await session.execute(delete(tables.relabels))
    await bump_revision(session, tables)
    return done


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _stamp_under_share(session: AsyncSession, tables: VFSTables, profile: DialectProfile) -> int | None:
    """The everyone stamp read under the profile's shared lock, ``None`` where the row is missing."""
    revisions = tables.principal_revisions
    stamp = select(revisions.c.revision).where(revisions.c.principal_id == EVERYONE_NAME)
    stamp = lock_rows(stamp) if profile.share_lock.form == "exclusive" else stamp.with_for_update(read=True)
    return (await session.execute(stamp)).scalar_one_or_none()


def _lock_stamps(session: AsyncSession, tables: VFSTables, mode: str) -> TextClause:
    """``LOCK TABLE`` on the stamps table in *mode*, the table named as the session's dialect quotes it."""
    name = session.get_bind().dialect.identifier_preparer.format_table(tables.principal_revisions)
    return text(f"LOCK TABLE {name} IN {mode} MODE")


class _Batch(NamedTuple):
    """One chunk's spans; *walked* means one open range too large for a chunk, to be split by keyset."""

    spans: RangeSet
    walked: bool


class _Plan(NamedTuple):
    """A relabel's remaining chunks, valid for one mark under one revision and cursor."""

    path: str
    revision: int
    cursor: str | None
    rank: int
    batches: list[_Batch]


def _batched(spans: RangeSet, counts: Mapping[Open, int], piece_cap: int, row_cap: int) -> list[_Batch]:
    """*spans* grouped in path order so no chunk carries more pieces or rows than its cap.

    A span's rows are its open ranges' counts plus one per edge point.
    A span alone over the row cap is walked by keyset at execution; the
    rest fill chunks greedily.
    """
    batches: list[_Batch] = []
    current: list[Span] = []
    rows = size = 0
    for span in spans:
        found = pieces((span,))
        n_pieces = len(found.points) + len(found.opens)
        n_rows = len(found.points) + sum(counts.get(open_range, 0) for open_range in found.opens)
        if n_rows > row_cap:
            if current:
                batches.append(_Batch(RangeSet(tuple(current)), walked=False))
                current, rows, size = [], 0, 0
            batches.append(_Batch(RangeSet((span,)), walked=True))
            continue
        if current and (rows + n_rows > row_cap or size + n_pieces > piece_cap):
            batches.append(_Batch(RangeSet(tuple(current)), walked=False))
            current, rows, size = [], 0, 0
        current.append(span)
        rows += n_rows
        size += n_pieces
    if current:
        batches.append(_Batch(RangeSet(tuple(current)), walked=False))
    return batches


async def _deeper_postures(
    session: AsyncSession, tables: VFSTables, profile: DialectProfile, root: str
) -> dict[str, GrantLevel]:
    """The posture rows strictly beneath *root*, through the ``(principal_id, path_prefix)`` key."""
    grants = tables.grants
    beneath = (
        grants.c.path_prefix != ROOT
        if root == ROOT
        else grants.c.path_prefix.like(escape_like(root, profile) + "/%", escape=LIKE_ESCAPE)
    )
    stmt = select(grants.c.path_prefix, grants.c.level).where(grants.c.principal_id == EVERYONE_NAME, beneath)
    return {row.path_prefix: row.level for row in await session.execute(stmt)}


async def _run(session: AsyncSession, stmt: Executable, params: dict[str, Any]) -> int:
    result = cast("CursorResult[Any]", await session.execute(stmt, params))
    return max(0, result.rowcount)


def _relabel_opens(entry: Table, profile: DialectProfile, rank: int, opens: Sequence[Open]) -> Update:
    """One ``UPDATE`` setting *rank* inside every open range of *opens*, in the dialect's measured form.

    SQLite and Postgres join the unpacked ranges as ``UPDATE … FROM``;
    the generic floor takes the literal ``OR`` of ranges. The ranges
    bound ``path``.
    """
    source = profile.range_source
    column = entry.c.path
    if source is not None:
        _rows, lo, hi = open_rows(opens, source)
        return update(entry).values(everyone_level=rank).where(column > lo, column < hi)
    return update(entry).values(everyone_level=rank).where(or_(*(and_(column > lo, column < hi) for lo, hi in opens)))
