"""The enforcement spine's storage half — rights read, cached, compiled, and gated.

Every verb resolves its authority here, inside its own transaction: the
stamps of the subjects and the groups the cache knows them to be in (one
chunked read) and the relabels in flight (one read of a table that is
normally empty), then — only when the cache misses — the subjects' group
closures (one chunked statement per nesting level), every grant row
naming a subject or one of its groups, the root posture row, and the
posture rows whose relabel is still in flight. A cached compile is good
while no write has stamped one of its ids and the same relabels stand:
a grant retires its grantee's compile, a membership write its member's,
and a posture change nobody's — the labels decide — except for the span
of its relabel, which every reader compiles as a cover or a hole. The
pure resolver (:mod:`vfs.storage.grants`) turns the caller's own
rows into :class:`~vfs.storage.grants.Rights` at every rung a verb can
need — one compile per rung a row sits at, the rungs between restated
on the same pieces — caller-sized, never a word about other principals. What
everyone holds is not compiled at all — it sits on every entry row as
``everyone_level``, written with the row
(:mod:`~vfs.storage.backends.database.labels`) — except inside a region
a posture change is still rewriting, which the rights carry as a cover
or a hole until it settles. The system actor skips all of it and holds
everything.

The grant verbs lock before they decide: the revision bump is the first
statement of their transaction, the caller's rights are resolved under
it, uncached, and only then is the write gated — so a right revoked a
moment earlier is gone by the time the verb looks.

Reads filter through a :class:`Visibility`; mutations are checked by a
:class:`WriteGate`. Both read the verb's rungs from the one table in
:mod:`vfs.ops` and treat :meth:`Rights.admits` — Python, exact for any
number of grants, reading the row's label and bisecting the caller's
pieces — as the authority every row passes: a row the caller holds
``list`` on is named, one it holds ``read`` on is shown whole, and a
mutation compares the rung it holds with the slot the verb's entry
names. An anonymous caller is judged at the path it addresses, by the
posture rows on that path's chain. SQL predicates are pushdowns
that narrow toward it where a statement's shape needs one (a ``LIMIT``,
an aggregate, a subtree scan). Where the dialect declares a range
source, the pushdown is the three-seek join to the visible entries: the
everyone leg through the ``(everyone_level, path)`` index, the caller's
pieces as sorted path ranges in one bound value joined to the ``path``
index, and the owner floor through ``owner_id``
(:mod:`~vfs.storage.backends.database.ranges`). Elsewhere, and on the
vector leg, it is a literal OR of the same terms — the everyone level,
``path = p`` for an exact path, ``lo < path < hi`` for an open range,
each bound through the path column's type so every engine compares
bytewise; a fan too wide for a statement splits into clauses the way
glob's pattern fan does, each inside the dialect's bind and depth
budgets, and a caller runs its statement once per clause and merges.

A directory is *on the road* when a row the caller can see lies beneath
it: it shows as a bare name — path and kind, nothing else — so an agent
can walk down to what it may read, and it learns nothing its visible
rows' own paths do not already print. A write under a road-only
directory is refused on the directory, before the target name is
looked up, so the refusal never depends on what hides there.

A deleted row stays at its path with a tombstone, so permissions never
notice a delete: the row is judged at its own path by the label and the
pieces it already has. A row nobody but its owner could see stays that
way in the trash, the holder of a grant on its folder can still restore
it, and nothing reaches a tombstoned row through the ``/.vfs/trash``
view that could not reach it live. A read of a tombstoned row the
caller may see answers ``not_found`` with the trashed hint, and any
other verb at it is judged as at an occupied path; a tombstoned row the
caller may not see answers as any hidden row does — absent, with no
hint.
"""

from __future__ import annotations

import sys
from collections import OrderedDict
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final, Literal, NamedTuple, cast

from sqlalchemy import and_, delete, insert, or_, select, text, update

from vfs.authority import ANONYMOUS_NAME, EVERYONE_NAME, GROUP_NAME_PREFIX, SYSTEM_NAME
from vfs.models.rows import MAX_PRINCIPAL_ID_LENGTH
from vfs.ops import VERB_RUNGS, Needs
from vfs.paths import ROOT, Path
from vfs.results import ErrorKind, Result, ResultError, Severity, classified
from vfs.storage.backends.database.descent import (
    ancestor_chain,
    classify_miss,
    descendant_filter,
    rows_by_path,
    targets_with_ancestors,
    tombstone_side,
)
from vfs.storage.backends.database.dialects import arm_budget, chunked, membership_budget
from vfs.storage.backends.database.labels import (
    inflight_marks,
    inflight_postures,
    label_of,
    mark_relabel,
    posture_rows,
)
from vfs.storage.backends.database.membership import membership
from vfs.storage.backends.database.ranges import hole_free, visible_entries
from vfs.storage.backends.database.revision import (
    bump_revision,
    principal_revision,
    read_revision,
    stamp_principals,
)
from vfs.storage.grants import (
    FULL,
    GRANTABLE_LEVELS,
    LEVEL_RANK,
    MAX_GROUP_DEPTH,
    GrantRow,
    GroupClosures,
    Rights,
    ancestors_and_self,
    pieces,
    postures_of,
    resolve,
    subtract,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from sqlalchemy import CTE, Column, ColumnElement, FromClause, Select, Subquery, Table
    from sqlalchemy.engine import CursorResult, RowMapping
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.authority import Authority
    from vfs.models.rows import VFSTables
    from vfs.ops import Rung
    from vfs.storage.backends.database.dialects import DialectProfile
    from vfs.storage.backends.database.labels import Mark
    from vfs.storage.grants import GrantLevel, Pieces, Posture, PostureRows

RIGHTS_CACHE: Final = 1_024
"""Resolved authorities remembered per mount at most, one per subject set."""

RIGHTS_CACHE_BYTES: Final = 64 * 2**20
"""The bytes the remembered authorities may hold together, by :func:`weight`.

An ordinary caller holds rows at one or two rungs, so its compiles at the
other rungs share pieces and weigh nothing extra: the entry ceiling binds
first for ordinary callers and the byte budget for heavy ones.
"""

RIGHTS_FIELDS: Final[frozenset[str]] = frozenset({"owner_id", "everyone_level"})
"""The entry columns every row a view judges must carry beside its path."""

RESERVED_PRINCIPALS: Final[frozenset[str]] = frozenset({EVERYONE_NAME, SYSTEM_NAME, ANONYMOUS_NAME})
"""Ids no grant or membership may name: posture belongs to ``posture``,
the system actor needs no grant, and anonymous holds only the posture."""

# Pieces per owner-arm unit: each is at most two binds and one OR level deep.
_OWNER_PIECES_PER_UNIT: Final = 50

# Subtree rows read per page when a subtree mutation must check each row.
_SUBTREE_PAGE: Final = 1_000

GateMode = Literal["modify", "upsert", "create", "read"]
"""What a mutation needs at a target: an existing row to change (``modify``),
change-or-create (``upsert``), a new row (``create``), or an existing row
it only reads (``read`` — an edge's target, a copy's source)."""


class Resolution:
    """One authority's rights at every rung a verb can need.

    One :class:`Rights` per grantable rung. Where no row of the caller's
    and no pending posture row sits at exactly a rung, the rows at or
    above it are the rows at or above the rung over it, so that compile
    is the one above restated at the lower rank on the same pieces
    (:meth:`Rights.at_level`): the object differs, because a ``Rights``
    admits by its own level, and the pieces are shared, so the cache
    weighs them once.
    """

    __slots__ = ("_by_rung",)

    def __init__(self, by_rung: Mapping[GrantLevel, Rights]) -> None:
        self._by_rung: dict[GrantLevel, Rights] = dict(by_rung)

    @classmethod
    def compile(
        cls, closures: GroupClosures, rows: Sequence[GrantRow], *, owner_floor: bool, pending: Sequence[str]
    ) -> Resolution:
        """The rungs compiled from ``read_write`` down, each lower rung aliased unless a row sits at it."""
        present = {row.level for row in rows if row.principal_id != EVERYONE_NAME or row.path_prefix in pending}
        by_rung: dict[GrantLevel, Rights] = {}
        above: Rights | None = None
        for level in reversed(GRANTABLE_LEVELS):
            if above is None or level in present:
                above = resolve(closures, rows, level, owner_floor=owner_floor, pending=pending)
            else:
                above = above.at_level(level)
            by_rung[level] = above
        return cls(by_rung)

    @classmethod
    def everything(cls) -> Resolution:
        """Every row at every rung — the system actor."""
        return cls({level: Rights.everything(level) for level in GRANTABLE_LEVELS})

    def at(self, rung: GrantLevel) -> Rights:
        """The rights at *rung*."""
        return self._by_rung[rung]

    @property
    def whole(self) -> bool:
        """Whether the grants alone admit every row at every rung, so no row needs judging."""
        return self._by_rung["read_write"].whole

    def compiled(self) -> tuple[Rights, ...]:
        """Every compile, highest rung first."""
        return tuple(self._by_rung[level] for level in reversed(GRANTABLE_LEVELS))


class RightsKey(NamedTuple):
    """What a cached resolution is good for: its subjects, the greatest stamp over their ids, the relabels in flight."""

    subjects: tuple[str, ...]
    stamp: int
    marks: tuple[Mark, ...]


class Clause(NamedTuple):
    """One statement's share of a visibility predicate and the binds it spends."""

    predicate: ColumnElement[bool]
    binds: int


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


class _Cached(NamedTuple):
    """One remembered resolution: the ids whose stamps its key reads, the key, the value, its weight."""

    ids: tuple[str, ...]
    key: RightsKey
    resolution: Resolution
    weight: int


class RightsCache:
    """Resolved authorities, one per subject set, least recently used first out past either bound.

    An entry stays good while its key holds: no write has stamped one of
    its ids — the subjects and the groups they were in when it was made,
    which every grant, revoke or membership write that could change
    what they hold stamps — and the same relabels stand. A write never
    touches the entries; the key stops matching and the next call
    replaces the entry. *entries* caps how many are held and *budget*
    how many bytes, by :func:`weight`; the newest entry always stays.
    """

    def __init__(self, entries: int = RIGHTS_CACHE, budget: int = RIGHTS_CACHE_BYTES) -> None:
        self._entries = entries
        self._budget = budget
        self._held = 0
        self._cached: OrderedDict[tuple[str, ...], _Cached] = OrderedDict()

    @property
    def held(self) -> int:
        """The bytes the entries weigh together."""
        return self._held

    def ids(self, subjects: tuple[str, ...]) -> tuple[str, ...] | None:
        """The ids whose stamps decide whether *subjects*' entry still holds; ``None`` when none is held."""
        found = self._cached.get(subjects)
        return None if found is None else found.ids

    def get(self, key: RightsKey) -> Resolution | None:
        """The resolution held under exactly *key*; an entry held under another key for its subjects is dropped."""
        found = self._cached.get(key.subjects)
        if found is None:
            return None
        if found.key != key:
            self._drop(key.subjects)
            return None
        self._cached.move_to_end(key.subjects)
        return found.resolution

    def put(self, key: RightsKey, ids: Iterable[str], resolution: Resolution) -> None:
        """Remember *resolution* under *key*, keyed for revalidation on the stamps of *ids*."""
        self._drop(key.subjects)
        entry = _Cached(tuple(ids), key, resolution, weight(resolution))
        self._cached[key.subjects] = entry
        self._held += entry.weight
        while len(self._cached) > 1 and (len(self._cached) > self._entries or self._held > self._budget):
            self._drop(next(iter(self._cached)))

    def _drop(self, subjects: tuple[str, ...]) -> None:
        gone = self._cached.pop(subjects, None)
        if gone is not None:
            self._held -= gone.weight


def weight(resolution: Resolution) -> int:
    """A byte estimate of *resolution*: its rights' spans, roots, holes, owner arms and pieces, strings included.

    The pieces are computed here if they were not yet, so the estimate
    counts what a view will hold, not only what the compile made. A
    tuple two compiles share — an aliased rung's spans or pieces — is
    counted once.
    """
    held = 0
    seen: set[int] = set()
    # The arm tuples are built here; holding them keeps their ids from being reused mid-count.
    kept = [tuple((arm.owner, arm.prefixes) for arm in rights.owner_arms) for rights in resolution.compiled()]
    for rights, arms in zip(resolution.compiled(), kept, strict=True):
        for part in (rights.spans, rights.roots, rights.holes, arms, rights.ranges()):
            held += _size(part, seen)
    return held


async def resolve_authority(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    authority: Authority,
    cache: RightsCache | None,
) -> Resolution | ResultError:
    """*authority*'s rights, from the cache or from the rows; a refusal when the walk breaks its bound.

    A held entry is revalidated by its own ids' stamps, read before the
    relabel marks so a write that lands between the two is one the next
    call sees whole. On a miss the subjects' closures are walked per
    member and never pooled: a member's groups are that member's own,
    and the meet across members runs after each member's union is
    finished. Only the rows naming the subjects and their groups are
    read — the everyone rows live on the entry rows — plus the root
    posture row, which the anonymous refusal judges, and the posture
    rows still being relabelled, which compile as covers and holes until
    they settle. Anonymous holds the posture alone, so its key reads the
    everyone principal's stamp too. The mount revision is read first and
    last, and a compile the two reads disagree over is answered but not
    remembered: an admin write landed between its statements, and the
    next call reads settled state. *cache* is ``None`` for a resolution
    made inside an admin write: its transaction may yet roll back, and a
    compile keyed on stamps that never committed would serve rights
    that never held.
    """
    if authority.is_system:
        return Resolution.everything()
    subjects = authority.subject_names
    known = cache.ids(subjects) if cache is not None else None
    if cache is not None and known is not None:
        stamp = await principal_revision(session, tables, profile, membership_budget, known)
        cached = cache.get(RightsKey(subjects, stamp, await inflight_marks(session, tables)))
        if cached is not None:
            return cached
    opened = await read_revision(session, tables)
    if authority.is_anonymous:
        closures: dict[str, frozenset[str]] = {sub: frozenset() for sub in subjects}
    else:
        walked = await _closures(session, tables, profile, membership_budget, subjects)
        if isinstance(walked, ResultError):
            return walked
        closures = walked
    ids = sorted({*subjects, *(group for groups in closures.values() for group in groups)})
    stamped = [*ids, EVERYONE_NAME] if authority.is_anonymous else ids
    stamp = await principal_revision(session, tables, profile, membership_budget, stamped)
    marks = await inflight_marks(session, tables)
    rows = await _grant_rows(session, tables, profile, membership_budget, ids)
    postures = await inflight_postures(session, tables, profile, membership_budget, marks)
    rows += [GrantRow(EVERYONE_NAME, prefix, level) for prefix, level in postures.items()]
    pending = [mark.path for mark in marks]
    resolution = Resolution.compile(closures, rows, owner_floor=not authority.is_anonymous, pending=pending)
    if cache is not None and await read_revision(session, tables) == opened:
        cache.put(RightsKey(subjects, stamp, marks), stamped, resolution)
    return resolution


def unauthenticated_at(authority: Authority, postures: PostureRows, path: str, rung: Rung) -> ResultError | None:
    """``unauthenticated`` when an anonymous call needs *rung* at *path* and the posture rows give everyone less.

    Judged at the addressed path: the deepest posture row on its chain,
    read from the posture rows (*postures* holds the chain's) and never
    from a stored label, which lags while a relabel runs. A named caller
    is never refused here; its rows decide.
    """
    if not authority.is_anonymous or label_of(postures, path) >= LEVEL_RANK[rung]:
        return None
    return classified(ErrorKind.unauthenticated, Path._brand(path))


async def unauthenticated_refusals(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    authority: Authority,
    paths: Iterable[str],
    rung: Rung,
) -> list[ResultError]:
    """The anonymous refusals for a read addressing *paths* at *rung* — one chunked read of the posture rows."""
    wanted = list(dict.fromkeys(paths))
    if not authority.is_anonymous or not wanted:
        return []
    chain = {ancestor for path in wanted for ancestor in ancestors_and_self(path)}
    postures = await posture_rows(session, tables, profile, membership_budget, chain)
    found = (unauthenticated_at(authority, postures, path, rung) for path in wanted)
    return [refusal for refusal in found if refusal is not None]


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------


def visibility_clauses(
    entry: Table, rights: Rights, profile: DialectProfile, parameter_budget: int
) -> list[Clause] | None:
    """*rights* as OR-clauses on *entry*, each inside the budgets; ``None`` when every row passes.

    An empty list means no row passes. Clauses are disjunctive: a row is
    admitted when any clause admits it, so a caller runs once per clause
    and merges. Each clause spends at most half the membership budget,
    leaving the rest for the statement's own id list.
    """
    if rights.whole:
        return None
    bind_cap = max(1, membership_budget(profile, parameter_budget) // 2)
    count_cap = arm_budget(profile, parameter_budget, 1)
    units = _units(entry, rights, bind_cap)
    clauses: list[Clause] = []
    pending: list[Clause] = []
    spend = 0
    for unit in units:
        if pending and (spend + unit.binds > bind_cap or len(pending) >= count_cap):
            clauses.append(Clause(or_(*(p.predicate for p in pending)), spend))
            pending, spend = [], 0
        pending.append(unit)
        spend += unit.binds
    if pending:
        clauses.append(Clause(or_(*(p.predicate for p in pending)), spend))
    return clauses


# ---------------------------------------------------------------------------
# The read view
# ---------------------------------------------------------------------------


def judged_columns(entry: Table) -> list[Column[Any]]:
    """The columns a row the descent ladder judges carries: its path, kind and tombstone, and the rights fields."""
    return [entry.c.path, entry.c.kind, entry.c.deleted_at, *(entry.c[field] for field in sorted(RIGHTS_FIELDS))]


class Visibility:
    """What one read call may see: its rights at the verb's rung, the road beneath them, and their pushdown.

    *need* is the rung the verb's statements fetch at — ``list`` for the
    listing verbs, ``read`` for the ones that carry bodies — and
    :attr:`rights` is that compile. :meth:`holds` is the authority on
    each row (it needs the row's ``path``, ``owner_id`` and
    ``everyone_level`` — :data:`RIGHTS_FIELDS`): a row the caller
    :meth:`shows` is named, one it :meth:`reads` is shown whole, and
    :meth:`admits` answers the rung it holds. :meth:`road` names the
    hidden directories that lead to a row the caller may name; it runs
    at the ``list`` compile and is never derived for anonymous.
    """

    def __init__(
        self,
        resolution: Resolution,
        need: Rung,
        tables: VFSTables,
        profile: DialectProfile,
        membership_budget: int,
        parameter_budget: int,
        *,
        road: bool = True,
    ) -> None:
        self.resolution = resolution
        self.need: Rung = need
        self.rights = resolution.at(need)
        self._listing = resolution.at("list")
        self._tables = tables
        self._profile = profile
        self._membership_budget = membership_budget
        self._parameter_budget = parameter_budget
        self._road = road
        self._roots: set[str] | None = None

    @property
    def derives_road(self) -> bool:
        """Whether this view names hidden directories on the road to a nameable row — never for anonymous."""
        return self._road

    def admits(self, mapping: Mapping[Any, Any]) -> Rung:
        """The highest rung the caller holds on the row — ``none`` when it may not even name it."""
        for rights in self.resolution.compiled():
            if rights.admits(mapping["path"], mapping["owner_id"], mapping["everyone_level"]):
                return rights.level
        return "none"

    def holds(self, mapping: Mapping[Any, Any], rung: Rung) -> bool:
        """Whether the caller holds *rung* on the row — one compile's verdict."""
        return self.resolution.at(rung).admits(mapping["path"], mapping["owner_id"], mapping["everyone_level"])

    def shows(self, mapping: Mapping[Any, Any]) -> bool:
        """Whether the row may be named: its path and kind shown."""
        return self.holds(mapping, "list")

    def reads(self, mapping: Mapping[Any, Any]) -> bool:
        """Whether the row may be shown whole: every field, its body included."""
        return self.holds(mapping, "read")

    async def prepare(self, session: AsyncSession) -> None:
        """Issue the dialect's range-join settings in *session*'s transaction, before the first read."""
        for statement in self._profile.range_settings:
            await session.execute(text(statement))

    def clauses(self, entry: Table | None = None) -> list[Clause] | None:
        """This view's predicate on *entry* (the entries table by default), at the view's rung."""
        target = self._tables.entry if entry is None else entry
        return visibility_clauses(target, self.rights, self._profile, self._parameter_budget)

    def entries(self, scope: str | None = None) -> Subquery | CTE | None:
        """The admitted entries as a derived table of ``entry_id``, one statement for any rights.

        ``None`` where every row passes, where the dialect declares no
        range source, or where the caller holds no pieces of its own and
        the everyone level alone decides — the caller then takes
        :meth:`clauses`, which is one term there. *scope* narrows every
        branch to that path's strict descendants.
        """
        if self.rights.whole or self._profile.range_source is None or self.rights.empty:
            return None
        return visible_entries(self._tables.entry, self.rights.ranges(), self.rights.need, self._profile, scope)

    def narrow(self, stmt: Select[Any], scope: str | None = None) -> list[Select[Any]]:
        """*stmt*, which reads the entries table, as the statements that fetch only admitted rows.

        One statement joined to :meth:`entries` where the dialect can;
        otherwise one per clause, to be merged; ``[stmt]`` when every row
        passes. Fetched rows still pass :meth:`holds` at the view's rung.
        """
        visible = self.entries(scope)
        if visible is not None:
            return [stmt.join(visible, visible.c.entry_id == self._tables.entry.c.entry_id)]
        clauses = self.clauses()
        return [stmt] if clauses is None else [stmt.where(clause.predicate) for clause in clauses]

    async def road(self, session: AsyncSession, candidates: Iterable[str], *, trashed: bool = False) -> set[str]:
        """The *candidates* (directory paths) a row the caller may name lies beneath; the root always.

        Three sources, each at the ``list`` compile: every existing root
        prefix is named, so its ancestors are on the road; a member's
        owned rows are named wherever its owner arm reaches, so a
        candidate holding one is too; and a candidate holding a row
        everyone may name is on the road to it. Live rows lead the way,
        or the tombstoned ones under the trash view (*trashed*). An
        anonymous caller derives no road: only the root.
        """
        wanted = set(candidates)
        found = wanted & {ROOT}
        wanted -= found
        if not wanted or not self._road:
            return found
        entry, budget, listing = self._tables.entry, self._membership_budget, self._listing
        for root in await self._existing_roots(session):
            found.update(ancestor for ancestor in ancestors_and_self(root)[1:] if ancestor in wanted)
        rest = wanted - found
        for owner, held in listing.ranges().owners:
            if not rest:
                break
            owned = await _owned_beneath(session, entry, self._profile, budget, owner, held, rest, trashed=trashed)
            found |= owned
            rest -= owned
        if rest:
            found |= await _open_beneath(session, entry, self._profile, budget, listing, rest, trashed=trashed)
        return found

    async def seen_kinds(self, session: AsyncSession, rows: Mapping[str, RowMapping]) -> dict[str, str]:
        """``path → kind`` over the live rows this view names: shown ones, road directories, the root.

        The descent ladder classifies against this map, so a hidden
        ancestor reads exactly as a missing one, and a tombstoned
        ancestor as an absent one.
        """
        live = {path: row for path, row in rows.items() if row["deleted_at"] is None}
        visible = {path: row["kind"] for path, row in live.items() if self.shows(row)}
        hidden = [path for path, row in live.items() if path not in visible and row["kind"] == "directory"]
        for path in await self.road(session, hidden):
            visible[path] = "directory"
        visible[ROOT] = "directory"
        return visible

    def tombstones(self, rows: Mapping[str, RowMapping], need: Rung) -> dict[str, datetime]:
        """``path → deleted_at`` over the tombstoned rows the caller holds *need* on.

        The gate asks at ``list``: an occupied path is judged. The
        descent ladder asks at ``read``: the trashed hint and its time
        ride only on a tombstone the caller may read.
        """
        return {
            path: row["deleted_at"]
            for path, row in rows.items()
            if row["deleted_at"] is not None and self.holds(row, need)
        }

    async def _existing_roots(self, session: AsyncSession) -> set[str]:
        if self._roots is None:
            entry = self._tables.entry
            roots = [prefix for prefix in self._listing.roots if prefix != ROOT]
            found = await rows_by_path(session, entry, roots, [entry.c.path], self._profile, self._membership_budget)
            self._roots = set(found)
        return self._roots


# ---------------------------------------------------------------------------
# The write gate
# ---------------------------------------------------------------------------


def denied(path: Path, *, target: Path | None = None) -> ResultError:
    """The ``permission_denied`` refusal for a path the caller can see but may not act on."""
    return classified(ErrorKind.permission_denied, path, target=target)


class WriteGate:
    """The point checks a mutation passes before its first write statement.

    One batched fetch of the targets and their ancestors, decided in app
    code: a batch of any size is one resolver call and a handful of
    chunked reads, never a statement per path. Any refusal fails the
    batch whole. The kinds keep hidden and missing indistinguishable: a
    target or ancestor the caller cannot name answers ``not_found``
    exactly as an absent one does, and a creation is judged by coverage
    alone, never by what occupies the name. *needs* is the verb's entry
    in the table: every leg that passes a row it has seen compares the
    rung the caller holds on it with the leg's slot.
    """

    def __init__(
        self,
        resolution: Resolution,
        needs: Needs,
        tables: VFSTables,
        profile: DialectProfile,
        membership_budget: int,
        parameter_budget: int,
        *,
        authority: Authority,
    ) -> None:
        self.resolution = resolution
        self.needs = needs
        self.authority = authority
        self._tables = tables
        self._profile = profile
        self._membership_budget = membership_budget
        self._parameter_budget = parameter_budget
        self.view = Visibility(
            resolution, "list", tables, profile, membership_budget, parameter_budget, road=not authority.is_anonymous
        )
        # Rows the target checks fetched, so a subtree check skips known files.
        self._known: dict[str, RowMapping] = {}

    @property
    def whole(self) -> bool:
        return self.resolution.whole

    async def targets(
        self, session: AsyncSession, targets: Sequence[Path], mode: GateMode, *, parents: bool = False
    ) -> list[ResultError]:
        """Refusals for *targets* under *mode*; empty when every target may proceed."""
        if self.whole or not targets:
            return []
        entry, tables, profile, budget = self._tables.entry, self._tables, self._profile, self._membership_budget
        prefixes = targets_with_ancestors(targets)
        rows = await rows_by_path(session, entry, prefixes, judged_columns(entry), profile, budget)
        self._known.update(rows)
        seen = await self.view.seen_kinds(session, rows)
        judged = self.view.tombstones(rows, "list")
        hinted = self.view.tombstones(rows, "read")
        # A hidden directory, live or deleted, is on the road when a deleted
        # row the caller names lies beneath it — the trash view shows it so.
        hidden = [p for p, r in rows.items() if r["kind"] == "directory" and p not in seen and p not in judged]
        for path in await self.view.road(session, hidden, trashed=True) if hidden else ():
            seen[path] = "directory"
        road = {path for path in seen if path in rows and not self.view.shows(rows[path])}
        # A creation has no row to read the level from, and anonymous is
        # judged at the path it addresses: the posture rows on its chain decide.
        wants_postures = mode != "read" or self.authority.is_anonymous
        postures = await posture_rows(session, tables, profile, budget, prefixes) if wants_postures else {}
        batch = {str(target) for target in targets}
        errors: list[ResultError] = []
        for target in dict.fromkeys(targets):
            refusal = self._decide(target, rows, seen, judged, hinted, road, postures, batch, mode, parents=parents)
            if refusal is not None:
                errors.append(refusal)
        return errors

    async def anonymous(self, session: AsyncSession, targets: Sequence[Path]) -> list[ResultError]:
        """The anonymous refusals for *targets* at the verb's primary rung — for a verb with a ladder of its own."""
        tables, profile, budget = self._tables, self._profile, self._membership_budget
        paths = [str(target) for target in targets]
        return await unauthenticated_refusals(
            session, tables, profile, budget, self.authority, paths, self.needs.primary
        )

    async def named(self, session: AsyncSession, targets: Sequence[Path]) -> set[str]:
        """The *targets* the caller may name — a row it holds ``list`` on, or a road directory — with no ladder.

        One point fetch of the targets alone: an ancestor's name never
        surfaces, so a target the caller cannot name answers exactly as
        an absent one wherever this set is consulted.
        """
        entry, profile, budget = self._tables.entry, self._profile, self._membership_budget
        wanted = {str(target) for target in targets}
        if self.whole:
            return wanted
        rows = await rows_by_path(session, entry, wanted, judged_columns(entry), profile, budget)
        live = {path: row for path, row in rows.items() if row["deleted_at"] is None}
        found = {path for path, row in live.items() if self.view.shows(row)}
        doors = [path for path, row in live.items() if path not in found and row["kind"] == "directory"]
        if doors:
            found |= await self.view.road(session, doors)
        return found

    async def subtrees(self, session: AsyncSession, roots: Sequence[Path], rung: Rung) -> list[ResultError]:
        """``permission_denied`` for each root with a row beneath it this authority does not hold *rung* on.

        A root the caller's own pieces cover whole passes without a
        read; otherwise the rows beneath it that everyone does not hold
        at *rung* are read in pages — one seek of the composite index,
        empty under an open posture — and each is checked, stopping at
        the first refusal. The read is proportional to the rows below
        the rung, and only a caller whose rights are partial there pays
        it. Inside a hole the label decides nothing, so the rows there
        the label would have passed are paged too, a chunk of the hole's
        pieces at a time.
        """
        rights = self.resolution.at(rung)
        errors: list[ResultError] = []
        entry = self._tables.entry
        per_chunk = arm_budget(self._profile, self._parameter_budget, 2)
        unlabelled = [entry.c.everyone_level < rights.need]
        unlabelled += [
            and_(entry.c.everyone_level >= rights.need, or_(*(unit.predicate for unit in chunk)))
            for chunk in chunked(_piece_units(entry.c.path, rights.ranges().holes), per_chunk)
        ]
        for root in dict.fromkeys(roots):
            known = self._known.get(str(root))
            covered = rights.whole or rights.covers_subtree(str(root))
            if covered or (known is not None and known["kind"] != "directory"):
                continue
            for filtered in unlabelled:
                if await self._refused_beneath(session, root, rights, filtered):
                    errors.append(denied(root))
                    break
        return errors

    async def _refused_beneath(
        self, session: AsyncSession, root: Path, rights: Rights, filtered: ColumnElement[bool]
    ) -> bool:
        """Whether a row under *root* passing *filtered*, read in pages, fails *rights*."""
        entry = self._tables.entry
        last = str(root)
        while True:
            stmt = (
                select(*judged_columns(entry))
                .where(descendant_filter(entry, str(root), self._profile), filtered, entry.c.path > last)
                .order_by(entry.c.path)
                .limit(_SUBTREE_PAGE)
            )
            page = (await session.execute(stmt)).mappings().all()
            if any(not rights.admits(row["path"], row["owner_id"], row["everyone_level"]) for row in page):
                return True
            if len(page) < _SUBTREE_PAGE:
                return False
            last = page[-1]["path"]

    def row(
        self, named: Path, judged: str, owner_id: str | None, everyone_level: int, rung: Rung
    ) -> ResultError | None:
        """The check for one row the view already names, judged at its own path *judged* and refused as *named*.

        Visible-but-barred is denied; the refusal names *named*, the path
        the caller sent, never the one the row sits at.
        """
        if not self.resolution.at(rung).admits(judged, owner_id, everyone_level):
            return denied(named)
        return None

    async def missing(self, session: AsyncSession, target: Path) -> ResultError:
        """The refusal for a *target* this call cannot act on: hidden reads exactly as absent.

        The descent ladder runs over what the view names — a hidden
        ancestor is a missing one — so the payload names only a prefix
        of the path the caller sent, and never what hides at it; a
        tombstone the caller may read carries its hint.
        """
        entry, profile, budget = self._tables.entry, self._profile, self._membership_budget
        rows = await rows_by_path(
            session, entry, targets_with_ancestors([target]), judged_columns(entry), profile, budget
        )
        return classify_miss(target, await self.view.seen_kinds(session, rows), self.view.tombstones(rows, "read"))

    def _slot(self, mode: GateMode) -> Rung:
        """The rung this leg needs on a row it has seen: the verb's slot for *mode*."""
        if mode == "read":
            assert self.needs.traverse is not None, "a read leg belongs to a verb with a traverse slot"
            return self.needs.traverse
        if mode == "modify":
            return self.needs.primary
        assert self.needs.create is not None, "a creation belongs to a verb with a create slot"
        return self.needs.create

    def _lowest(self, key: str, rows: Mapping[str, RowMapping], mode: GateMode) -> Rung:
        """The lowest rung the verb can need at *key* — what anonymous is judged against there."""
        if mode == "read":
            return self._slot(mode)
        if mode in ("create", "upsert") and key not in rows:
            return self._slot(mode)
        return self.needs.primary

    def _decide(
        self,
        target: Path,
        rows: Mapping[str, RowMapping],
        seen: Mapping[str, str],
        judged: Mapping[str, datetime],
        hinted: Mapping[str, datetime],
        road: set[str],
        postures: PostureRows,
        batch: set[str],
        mode: GateMode,
        *,
        parents: bool,
    ) -> ResultError | None:
        """One target's verdict; a missing ancestor the batch itself supplies is judged as its own target.

        A tombstoned ancestor is absent — never minted, with or without
        *parents*. A tombstoned target the caller may name is absent to a
        read, with the trashed hint when it may read it; a mutation at it
        is judged as a restore of the row — ``read_write`` or own — so a
        caller who may name but not revive a deleted row is denied, never
        told it is absent; a creation at it answers as the verb's own
        ladder does. An occupied, named target is judged at the leg's
        slot: a read leg at the traverse rung, a creation at the create
        rung, a change at the primary rung with the owner floor riding.
        A road directory passes only a leg whose slot is ``list``.
        """
        key = str(target)
        refusal = unauthenticated_at(self.authority, postures, key, self._lowest(key, rows, mode))
        if refusal is not None:
            return refusal
        creating = mode in ("create", "upsert")
        minting = self.resolution.at(self._slot(mode)) if creating else None
        for ancestor in ancestor_chain(target):
            if str(ancestor) in seen:
                continue
            minted = minting is not None and (parents or str(ancestor) in batch) and str(ancestor) not in judged
            if minted and minting is not None and minting.reaches(str(ancestor), label_of(postures, str(ancestor))):
                continue
            if minted:
                return denied(ancestor, target=target)
            return classify_miss(target, seen, hinted)
        slot = self._slot(mode)
        if key in road:
            # A road directory shows only its name: a leg wanting more may not act on it.
            return None if slot == "list" else denied(target)
        if key in seen:
            held = self.needs.primary if mode in ("modify", "upsert") else slot
            return None if self.view.holds(rows[key], held) else denied(target)
        if key in judged and mode != "read":
            if mode == "create":
                return None if key in hinted else classify_miss(target, seen, hinted)
            revive = VERB_RUNGS["restore"].primary
            return None if self.view.holds(rows[key], revive) else denied(target)
        if mode in ("modify", "read") or key in judged:
            return classify_miss(target, seen, hinted)
        assert minting is not None
        if str(target.parent_dir) in road or not minting.reaches(key, label_of(postures, key)):
            return denied(target)
        return None


# ---------------------------------------------------------------------------
# The grant verbs
# ---------------------------------------------------------------------------


async def grant_rows(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    gate: WriteGate,
    *,
    path: Path,
    principal: str,
    level: GrantLevel,
    authority: Authority,
    revision: int,
) -> Result:
    """Write or replace *principal*'s row on *path*, stamped with *revision*; *principal* is stamped too.

    The granting authority must hold ``read_write`` on *path* for every
    subject, so what it grants never exceeds its own level there. *gate*
    was resolved under the admin lock, which *revision* came from, so
    what it holds is what the committed rows say now. The stamp retires
    every cached compile *principal* is a subject or a group of.
    """
    refusal = await _grant_refusal(session, tables, profile, membership_budget, "grant", gate, path, principal, level)
    if refusal is not None:
        return Result(ops=("grant",), errors=[refusal])
    await stamp_principals(session, tables, [principal], revision)
    written = await _upsert_grant(session, tables, path, principal, level, authority, revision)
    return Result(ops=("grant",), grants=[written])


async def revoke_rows(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    gate: WriteGate,
    *,
    path: Path,
    principal: str,
    authority: Authority,
    revision: int,
) -> Result:
    """Remove *principal*'s row on *path*, under the same gate as ``grant``; a missing row is a warning.

    A removed row stamps *principal* with *revision*, retiring every
    cached compile it reaches. *authority* is accepted for signature
    parity: the gate already judged it.
    """
    del authority
    refusal = await _grant_refusal(session, tables, profile, membership_budget, "revoke", gate, path, principal, "read")
    if refusal is not None:
        return Result(ops=("revoke",), errors=[refusal])
    grants = tables.grants
    removed = cast(
        "CursorResult[Any]",
        await session.execute(
            delete(grants).where(grants.c.principal_id == principal, grants.c.path_prefix == str(path))
        ),
    )
    if removed.rowcount == 0:
        fact = classified(
            ErrorKind.not_found,
            path,
            severity=Severity.warning,
            detail=f"no grant held by {principal}",
            data={"principal_id": principal},
        )
        return Result(ops=("revoke",), errors=[fact])
    await stamp_principals(session, tables, [principal], revision)
    return Result(ops=("revoke",), grants=[{"principal_id": principal, "path_prefix": str(path), "level": None}])


async def list_grants(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    gate: WriteGate,
    *,
    path: Path,
    authority: Authority,
) -> Result:
    """The rows on *path* and its ancestors this authority may see.

    Every row when it holds ``read_write`` on *path*; otherwise its own,
    its groups', and the everyone rows. A path it cannot read answers
    ``not_found``, as any hidden path does — a path it holds only
    ``list`` on included. "Read" here is what the everyone level and the
    caller's own pieces reach, not rows: a path reached only through the
    owner floor or as a road directory answers ``not_found`` too.
    """
    grants = tables.grants
    prefixes = [str(p) for p in reversed(ancestors_and_self(str(path)))]
    stmt = select(
        grants.c.principal_id, grants.c.path_prefix, grants.c.level, grants.c.granted_by, grants.c.granted_at
    ).where(membership(grants.c.path_prefix, prefixes, profile))
    rows = (await session.execute(stmt)).mappings().all()
    postures = postures_of(GrantRow(r["principal_id"], r["path_prefix"], r["level"]) for r in rows)
    label = label_of(postures, str(path))
    refusal = unauthenticated_at(authority, postures, str(path), gate.needs.primary)
    if refusal is not None:
        return Result(ops=("grants",), errors=[refusal])
    if not gate.resolution.at(gate.needs.primary).reaches(str(path), label):
        return Result(ops=("grants",), errors=[classified(ErrorKind.not_found, path)])
    if not gate.resolution.at("read_write").reaches(str(path), label):
        own = await _own_ids(session, tables, profile, membership_budget, authority)
        rows = [row for row in rows if row["principal_id"] in own]
    listed = [dict(row) for row in sorted(rows, key=lambda r: (r["path_prefix"], r["principal_id"]))]
    return Result(ops=("grants",), grants=listed)


async def set_posture(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    gate: WriteGate,
    *,
    path: Path,
    posture: Posture,
    authority: Authority,
    revision: int,
) -> Result:
    """Write the everyone row at *path*: the rung everyone holds from here down.

    The deepest everyone row covering a path decides what everyone holds
    there; principal and group rows still widen on top. The row lands
    marked in flight under *revision*, in force for every reader from
    this commit on; the labels beneath it are rewritten afterwards,
    chunk by chunk, by the verb that called this. No named caller's
    compile is retired — the labels and the mark decide — only the
    everyone principal is stamped, for the caller that holds the
    posture alone.
    """
    refusal = await _grant_refusal(
        session, tables, profile, membership_budget, "posture", gate, path, None, "read_write"
    )
    if refusal is not None:
        return Result(ops=("posture",), errors=[refusal])
    await stamp_principals(session, tables, [EVERYONE_NAME], revision)
    written = await _upsert_grant(session, tables, path, EVERYONE_NAME, posture, authority, revision)
    await mark_relabel(session, tables, str(path), revision)
    return Result(ops=("posture",), grants=[written])


async def add_member_rows(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    *,
    group: str,
    member: str,
    authority: Authority,
) -> Result:
    """Make *member* a direct member of *group* — the system actor only.

    The revision row is bumped first, so rival membership writes
    serialize behind it and the depth and cycle checks judge settled
    state. A nesting that would be cyclic or deeper than the declared
    bound is refused, never stored. A new row stamps *member*: its
    closure is what changed, and every caller whose closure holds it
    reads its stamp, so nested members are retired through it too.
    """
    refusal = _membership_refusal("add_member", group, member, authority)
    if refusal is not None:
        return Result(ops=("add_member",), errors=[refusal])
    revision = await bump_revision(session, tables)
    above = await _walk(session, tables, profile, membership_budget, group, upward=True)
    below = await _walk(session, tables, profile, membership_budget, member, upward=False)
    if member == group or member in above.reached:
        detail = f"adding {member} to {group} would make the group nesting cyclic"
        return Result(ops=("add_member",), errors=[classified(ErrorKind.authority_budget, detail=detail)])
    if below.depth + 1 + above.depth > MAX_GROUP_DEPTH:
        detail = f"adding {member} to {group} would nest groups deeper than {MAX_GROUP_DEPTH}"
        return Result(ops=("add_member",), errors=[classified(ErrorKind.authority_budget, detail=detail)])
    memberships = tables.memberships
    exists = await session.execute(
        select(memberships.c.group_id).where(memberships.c.principal_id == member, memberships.c.group_id == group)
    )
    row = {
        "principal_id": member,
        "group_id": group,
        "granted_by": authority.actor.sub,
        "granted_at": datetime.now(UTC),
    }
    if exists.first() is None:
        await stamp_principals(session, tables, [member], revision)
        await session.execute(insert(memberships).values(**row))
    return Result(ops=("add_member",), members=[row])


async def remove_member_rows(
    session: AsyncSession, tables: VFSTables, *, group: str, member: str, authority: Authority
) -> Result:
    """Remove *member*'s direct membership of *group* — the system actor only; a missing row is a warning.

    A removed row stamps *member*, as ``add_member`` does.
    """
    refusal = _membership_refusal("remove_member", group, member, authority)
    if refusal is not None:
        return Result(ops=("remove_member",), errors=[refusal])
    revision = await bump_revision(session, tables)
    memberships = tables.memberships
    removed = cast(
        "CursorResult[Any]",
        await session.execute(
            delete(memberships).where(memberships.c.principal_id == member, memberships.c.group_id == group)
        ),
    )
    if removed.rowcount == 0:
        fact = classified(
            ErrorKind.not_found,
            severity=Severity.warning,
            detail=f"{member} is not a direct member of {group}",
            data={"group_id": group, "principal_id": member},
        )
        return Result(ops=("remove_member",), errors=[fact])
    await stamp_principals(session, tables, [member], revision)
    return Result(ops=("remove_member",), members=[{"principal_id": member, "group_id": group}])


def posture_row(posture: Posture, now: datetime) -> dict[str, object]:
    """The everyone row first touch plants at the mount root."""
    return {
        "principal_id": EVERYONE_NAME,
        "path_prefix": ROOT,
        "level": posture,
        "granted_by": "system",
        "granted_at": now,
        "revision": 0,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _closures(
    session: AsyncSession, tables: VFSTables, profile: DialectProfile, membership_budget: int, subjects: Sequence[str]
) -> dict[str, frozenset[str]] | ResultError:
    """Each subject's full group set: one chunked statement per nesting level, refused past the bound."""
    member_of: dict[str, set[str]] = {}
    frontier, seen, depth = set(subjects), set(subjects), 0
    while frontier:
        found = await _groups_of(session, tables, profile, membership_budget, frontier)
        for principal, groups in found.items():
            member_of.setdefault(principal, set()).update(groups)
        reached = {group for principal in frontier for group in found.get(principal, ())} - seen
        if reached and depth >= MAX_GROUP_DEPTH:
            detail = f"group nesting deeper than {MAX_GROUP_DEPTH}; the membership rows break their bound"
            return classified(ErrorKind.authority_budget, detail=detail)
        depth += 1
        seen |= reached
        frontier = reached
    return {sub: frozenset(_reach(member_of, sub)) for sub in subjects}


async def _groups_of(
    session: AsyncSession, tables: VFSTables, profile: DialectProfile, membership_budget: int, principals: set[str]
) -> dict[str, set[str]]:
    memberships = tables.memberships
    found: dict[str, set[str]] = {}
    for chunk in chunked(sorted(principals), membership_budget):
        stmt = select(memberships.c.principal_id, memberships.c.group_id).where(
            membership(memberships.c.principal_id, chunk, profile)
        )
        for row in await session.execute(stmt):
            found.setdefault(row.principal_id, set()).add(row.group_id)
    return found


def _reach(member_of: Mapping[str, set[str]], start: str) -> set[str]:
    """Every group *start* belongs to, directly or through nesting; a visited set ends any cycle."""
    out: set[str] = set()
    frontier = set(member_of.get(start, ()))
    while frontier:
        out |= frontier
        frontier = {group for principal in frontier for group in member_of.get(principal, ())} - out - {start}
    return out


async def _grant_rows(
    session: AsyncSession, tables: VFSTables, profile: DialectProfile, membership_budget: int, ids: Sequence[str]
) -> list[GrantRow]:
    grants = tables.grants
    rows: list[GrantRow] = []
    for chunk in chunked(list(ids), membership_budget):
        stmt = select(grants.c.principal_id, grants.c.path_prefix, grants.c.level).where(
            membership(grants.c.principal_id, chunk, profile)
        )
        rows.extend(GrantRow(row.principal_id, row.path_prefix, row.level) for row in await session.execute(stmt))
    return rows


def _size(value: object, seen: set[int]) -> int:
    """*value*'s own bytes plus, through every tuple, its items' — strings and ints are the leaves.

    A tuple already in *seen* counts nothing: the compiles at aliased
    rungs share their tuples, and the cache weighs a shared one once.
    """
    if isinstance(value, tuple):
        if id(value) in seen:
            return 0
        seen.add(id(value))
        return sys.getsizeof(value) + sum(_size(item, seen) for item in value)
    return sys.getsizeof(value)


def _units(entry: Table, rights: Rights, bind_cap: int) -> list[Clause]:
    """The everyone units, one unit per piece of the spans, and per slice of each owner arm's pieces under *bind_cap*.

    The everyone unit is the level alone; with holes in the rights it is
    the level on each piece of the mount outside them, so the fan still
    splits it across statements. Every piece is judged on ``path``.
    """
    ranges = rights.ranges()
    everyone = entry.c.everyone_level >= rights.need
    units = [Clause(everyone, 1)]
    if rights.holes:
        outside = _piece_units(entry.c.path, pieces(subtract(FULL, rights.holes)))
        units = [Clause(and_(unit.predicate, everyone), unit.binds + 1) for unit in outside]
    units += _piece_units(entry.c.path, ranges.arms)
    per_unit = max(1, min(_OWNER_PIECES_PER_UNIT, (bind_cap - 1) // 2))
    for owner, found in ranges.owners:
        for group in chunked(_piece_units(entry.c.path, found), per_unit):
            predicate = and_(entry.c.owner_id == owner, or_(*(unit.predicate for unit in group)))
            units.append(Clause(predicate, 1 + sum(unit.binds for unit in group)))
    return units


def _piece_units(column: ColumnElement[Any], found: Pieces) -> list[Clause]:
    """One clause per piece on *column*: an exact path spends one bind, an open range two.

    Each bound binds through the column's own type, so the mysql family
    compares bytes and SQL Server keeps the UTF-8 collation.
    """
    points = [Clause(column == point, 1) for point in found.points]
    opens = [Clause(and_(column > lo, column < hi), 2) for lo, hi in found.opens]
    return [*points, *opens]


async def _owned_beneath(
    session: AsyncSession,
    entry: Table,
    profile: DialectProfile,
    membership_budget: int,
    owner: str,
    found: Pieces,
    candidates: set[str],
    *,
    trashed: bool,
) -> set[str]:
    """The *candidates* holding a row *owner* owns whose path lies within the pieces *found*."""
    row = entry.alias("r")
    tests = [
        and_(row.c.owner_id == owner, tombstone_side(row, trashed=trashed), or_(*(unit.predicate for unit in group)))
        for group in chunked(_piece_units(row.c.path, found), _OWNER_PIECES_PER_UNIT)
    ]
    per_chunk = max(1, membership_budget - 3 - 2 * _OWNER_PIECES_PER_UNIT)
    return await _beneath(session, entry, profile, per_chunk, row, tests, candidates)


async def _open_beneath(
    session: AsyncSession,
    entry: Table,
    profile: DialectProfile,
    membership_budget: int,
    rights: Rights,
    candidates: set[str],
    *,
    trashed: bool,
) -> set[str]:
    """The *candidates* holding a row everyone may see at the rights' level — one composite-index seek each.

    A row inside a hole does not count: its label is not yet the truth.
    """
    row = entry.alias("r")
    unholed = hole_free(row.c.path, rights.ranges().holes, profile)
    test = and_(row.c.everyone_level >= rights.need, tombstone_side(row, trashed=trashed), unholed)
    return await _beneath(session, entry, profile, max(1, membership_budget - 3), row, [test], candidates)


async def _beneath(
    session: AsyncSession,
    entry: Table,
    profile: DialectProfile,
    per_chunk: int,
    row: FromClause,
    tests: Sequence[ColumnElement[bool]],
    candidates: set[str],
) -> set[str]:
    """The *candidates* (directory paths) with a *row* beneath them passing any one of *tests*.

    One ``EXISTS`` per test per chunk of candidates. The byte range
    ``(d/, d0)`` is every path under ``d`` in bytewise order — sargable
    where a LIKE on a joined column is not.
    """
    directory = entry.alias("d")
    hits: set[str] = set()
    for chunk in chunked(sorted(candidates), per_chunk):
        for test in tests:
            beneath = and_(row.c.path > directory.c.path.concat("/"), row.c.path < directory.c.path.concat("0"), test)
            stmt = select(directory.c.path).where(
                membership(cast("Column[Any]", directory.c.path), chunk, profile),
                select(row.c.id).where(beneath).exists(),
            )
            hits.update((await session.execute(stmt)).scalars())
    return hits


async def _grant_refusal(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    op: str,
    gate: WriteGate,
    path: Path,
    principal: str | None,
    level: GrantLevel,
) -> ResultError | None:
    """The shared gate of the grant verbs: a lawful principal and level, and ``read_write`` on *path*.

    *path* need not hold a row, so its everyone level comes from the
    posture rows on its chain, as a creation's does; anonymous is judged
    there too.
    """
    if principal is not None and not _lawful_principal(principal):
        return classified(ErrorKind.invalid, detail=f"{op}: {principal!r} is not a grantable principal id")
    if level not in GRANTABLE_LEVELS and principal is not None:
        lawful = ", ".join(repr(rung) for rung in GRANTABLE_LEVELS)
        return classified(ErrorKind.invalid, detail=f"{op}: level must be one of {lawful}")
    postures = await posture_rows(session, tables, profile, membership_budget, ancestors_and_self(str(path)))
    label = label_of(postures, str(path))
    refusal = unauthenticated_at(gate.authority, postures, str(path), gate.needs.primary)
    if refusal is not None:
        return refusal
    if gate.resolution.at(gate.needs.primary).reaches(str(path), label):
        return None
    if gate.resolution.at("list").reaches(str(path), label):
        return denied(path)
    return classified(ErrorKind.not_found, path)


def _membership_refusal(op: str, group: str, member: str, authority: Authority) -> ResultError | None:
    if not authority.is_system:
        return classified(ErrorKind.permission_denied, detail=f"{op} is reserved to the system actor")
    if not group.startswith(GROUP_NAME_PREFIX) or len(group) == len(GROUP_NAME_PREFIX) or not _lawful_principal(group):
        return classified(ErrorKind.invalid, detail=f"{op}: a group id starts with {GROUP_NAME_PREFIX!r}")
    if not _lawful_principal(member):
        return classified(ErrorKind.invalid, detail=f"{op}: {member!r} cannot be a member")
    return None


def _lawful_principal(principal: str) -> bool:
    """Whether *principal* may be named on a row: not reserved, not blank, within the column."""
    return (
        principal not in RESERVED_PRINCIPALS and bool(principal.strip()) and len(principal) <= MAX_PRINCIPAL_ID_LENGTH
    )


async def _upsert_grant(
    session: AsyncSession,
    tables: VFSTables,
    path: Path,
    principal: str,
    level: GrantLevel,
    authority: Authority,
    revision: int,
) -> dict[str, object]:
    """Replace the one row for *(principal, path)*; the admin writes are serialized, so no race arbitrates."""
    grants = tables.grants
    row: dict[str, object] = {
        "principal_id": principal,
        "path_prefix": str(path),
        "level": level,
        "granted_by": authority.actor.sub,
        "granted_at": datetime.now(UTC),
        "revision": revision,
    }
    key = and_(grants.c.principal_id == principal, grants.c.path_prefix == str(path))
    updated = cast("CursorResult[Any]", await session.execute(update(grants).where(key).values(**row)))
    if updated.rowcount == 0:
        await session.execute(insert(grants).values(**row))
    return row


async def _own_ids(
    session: AsyncSession, tables: VFSTables, profile: DialectProfile, membership_budget: int, authority: Authority
) -> set[str]:
    """Every principal id the authority's rows may name: its subjects, their groups, everyone."""
    subjects = authority.subject_names
    walked = await _closures(session, tables, profile, membership_budget, subjects)
    groups = set() if isinstance(walked, ResultError) else {g for gs in walked.values() for g in gs}
    return {*subjects, *groups, EVERYONE_NAME}


class _Walk(NamedTuple):
    """A bounded membership walk from one principal: what it reached and how deep it went."""

    reached: set[str]
    depth: int


async def _walk(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    start: str,
    *,
    upward: bool,
) -> _Walk:
    """Walk memberships up (the groups *start* is in) or down (the members *start* has), one level per statement."""
    memberships = tables.memberships
    source, target = (
        (memberships.c.principal_id, memberships.c.group_id)
        if upward
        else (memberships.c.group_id, memberships.c.principal_id)
    )
    reached: set[str] = set()
    frontier, depth = {start}, 0
    while frontier and depth <= MAX_GROUP_DEPTH:
        nxt: set[str] = set()
        for chunk in chunked(sorted(frontier), membership_budget):
            nxt.update((await session.execute(select(target).where(membership(source, chunk, profile)))).scalars())
        nxt -= reached | {start}
        if not nxt:
            break
        depth += 1
        reached |= nxt
        frontier = nxt
    return _Walk(reached, depth)
