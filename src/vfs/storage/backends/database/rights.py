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
rows into :class:`~vfs.storage.grants.Rights` at the two levels a verb
can need: caller-sized, never a word about other principals. What
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
:class:`WriteGate`. Both treat :meth:`Rights.admits` — Python, exact for
any number of grants, reading the row's label and bisecting the caller's
pieces — as the authority every row passes; SQL predicates are pushdowns
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

A trashed row is judged by its origin. Delete reparents a row under the
trash root and records the path it was deleted from as ``origin_path``;
the row keeps its label, and the caller's own pieces and owner pieces
are matched against that origin instead of the trash address
(:func:`judged_path`). So a row nobody but its owner could see stays
that way in the trash, the holder of a grant on its old folder can
still restore it, and a grant on the trash subtree itself reaches no
trashed row. Only rows under the trash root carry an origin, so every
read scoped elsewhere is unchanged.
"""

from __future__ import annotations

import sys
from collections import OrderedDict
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final, Literal, NamedTuple, cast

from sqlalchemy import and_, delete, insert, or_, select, text, update

from vfs.authority import ANONYMOUS_NAME, EVERYONE_NAME, GROUP_NAME_PREFIX, SYSTEM_NAME
from vfs.models.rows import MAX_PRINCIPAL_ID_LENGTH
from vfs.paths import ROOT, Path, on_trash_chain
from vfs.results import Result, ResultError, Severity, VFSErrorKind, classified
from vfs.storage.backends.database.descent import (
    ancestor_chain,
    classify_miss,
    descendant_filter,
    rows_by_path,
    targets_with_ancestors,
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
from vfs.storage.backends.database.ranges import judged_hole_free, visible_entries
from vfs.storage.backends.database.revision import (
    bump_revision,
    principal_revision,
    read_revision,
    stamp_principals,
)
from vfs.storage.grants import (
    FULL,
    LEVEL_RANK,
    MAX_GROUP_DEPTH,
    POSTURE_LEVELS,
    GrantRow,
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
    from vfs.storage.backends.database.dialects import DialectProfile
    from vfs.storage.backends.database.labels import Mark
    from vfs.storage.grants import GrantLevel, Pieces, Posture, PostureRows

RIGHTS_CACHE: Final = 1_024
"""Resolved authorities remembered per mount at most, one per subject set."""

RIGHTS_CACHE_BYTES: Final = 64 * 2**20
"""The bytes the remembered authorities may hold together, by :func:`weight`.

An ordinary caller at a hundred thousand users weighs some 56 KB, so the
entry ceiling binds first for ordinary callers and the byte budget for
heavy ones.
"""

RIGHTS_FIELDS: Final[frozenset[str]] = frozenset({"owner_id", "everyone_level", "origin_path"})
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
it only reads (``read`` — an edge's target)."""


class Resolution(NamedTuple):
    """One authority's rights at both levels and the root's posture."""

    read: Rights
    write: Rights
    root_level: GrantLevel


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
    counts what a view will hold, not only what the compile made.
    """
    held = 0
    for rights in (resolution.read, resolution.write):
        arms = tuple((arm.owner, arm.prefixes) for arm in rights.owner_arms)
        held += _size((rights.spans, rights.roots, rights.holes, arms, rights.ranges()))
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
        return Resolution(Rights.everything("read"), Rights.everything("read_write"), "read_write")
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
    floor = not authority.is_anonymous
    resolution = Resolution(
        resolve(closures, rows, "read", owner_floor=floor, pending=pending),
        resolve(closures, rows, "read_write", owner_floor=floor, pending=pending),
        await _root_level(session, tables),
    )
    if cache is not None and await read_revision(session, tables) == opened:
        cache.put(RightsKey(subjects, stamp, marks), stamped, resolution)
    return resolution


def posture_refusal(authority: Authority, resolution: Resolution, level: GrantLevel) -> ResultError | None:
    """``unauthenticated`` when an anonymous call needs more than the mount root gives everyone."""
    if not authority.is_anonymous or LEVEL_RANK[resolution.root_level] >= LEVEL_RANK[level]:
        return None
    return ResultError(
        kind=VFSErrorKind.unauthenticated,
        message="this mount's posture needs a name: open a session, or configure default_authority",
    )


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


def judged_path(mapping: RowMapping) -> str:
    """The path a row's rights are judged by: its origin when it is trashed, else its own."""
    return mapping["origin_path"] or mapping["path"]


def judged_columns(entry: Table) -> list[Column[Any]]:
    """The columns a row the descent ladder judges carries: its path and kind, and the rights fields."""
    return [entry.c.path, entry.c.kind, *(entry.c[field] for field in sorted(RIGHTS_FIELDS))]


class Visibility:
    """What one read call may see: its rights, the road beneath them, and their pushdown.

    ``whole`` callers skip every filter. For the rest, :meth:`admits` is
    the authority on each row (it needs the row's ``path``, ``owner_id``,
    ``everyone_level`` and ``origin_path`` — :data:`RIGHTS_FIELDS`) and
    :meth:`road` names the hidden directories that lead to a visible row.
    """

    def __init__(
        self, rights: Rights, tables: VFSTables, profile: DialectProfile, membership_budget: int, parameter_budget: int
    ) -> None:
        self.rights = rights
        self._tables = tables
        self._profile = profile
        self._membership_budget = membership_budget
        self._parameter_budget = parameter_budget
        self._roots: set[str] | None = None

    def admits(self, mapping: RowMapping) -> bool:
        return self.rights.admits(judged_path(mapping), mapping["owner_id"], mapping["everyone_level"])

    async def prepare(self, session: AsyncSession) -> None:
        """Issue the dialect's range-join settings in *session*'s transaction, before the first read."""
        for statement in self._profile.range_settings:
            await session.execute(text(statement))

    def clauses(self, entry: Table | None = None) -> list[Clause] | None:
        """This view's predicate on *entry* (the entries table by default)."""
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
        passes. Fetched rows still pass :meth:`admits`.
        """
        visible = self.entries(scope)
        if visible is not None:
            return [stmt.join(visible, visible.c.entry_id == self._tables.entry.c.entry_id)]
        clauses = self.clauses()
        return [stmt] if clauses is None else [stmt.where(clause.predicate) for clause in clauses]

    async def road(self, session: AsyncSession, candidates: Iterable[str]) -> set[str]:
        """The *candidates* (directory paths) a visible row lies beneath; the root always.

        Four sources: every existing root prefix is visible, so its
        ancestors are on the road; a member's owned rows are visible
        wherever its owner arm reaches, so a candidate holding one is
        too; a candidate holding a row everyone may see at this level is
        on the road to it; and a candidate on the trash chain holding a
        trashed row whose origin the caller's pieces cover leads to it.
        """
        wanted = set(candidates)
        found = wanted & {ROOT}
        wanted -= found
        if not wanted:
            return found
        entry, budget = self._tables.entry, self._membership_budget
        for root in await self._existing_roots(session):
            found.update(ancestor for ancestor in ancestors_and_self(root)[1:] if ancestor in wanted)
        rest = wanted - found
        for owner, held in self.rights.ranges().owners:
            if not rest:
                break
            owned = await _owned_beneath(session, entry, self._profile, budget, owner, held, rest)
            found |= owned
            rest -= owned
        if rest:
            opened = await _open_beneath(session, entry, self._profile, budget, self.rights, rest)
            found |= opened
            rest -= opened
        if chain := {candidate for candidate in rest if on_trash_chain(candidate)}:
            found |= await _origin_beneath(session, entry, self._profile, budget, self.rights.ranges().arms, chain)
        return found

    async def seen_kinds(self, session: AsyncSession, rows: Mapping[str, RowMapping]) -> dict[str, str]:
        """``path → kind`` over the rows this view shows: visible ones, road directories, the root.

        The descent ladder classifies against this map, so a hidden
        ancestor reads exactly as a missing one.
        """
        visible = {path: row["kind"] for path, row in rows.items() if self.admits(row)}
        hidden = [path for path, row in rows.items() if path not in visible and row["kind"] == "directory"]
        for path in await self.road(session, hidden):
            visible[path] = "directory"
        visible[ROOT] = "directory"
        return visible

    async def _existing_roots(self, session: AsyncSession) -> set[str]:
        if self._roots is None:
            entry = self._tables.entry
            roots = [prefix for prefix in self.rights.roots if prefix != ROOT]
            found = await rows_by_path(session, entry, roots, [entry.c.path], self._profile, self._membership_budget)
            self._roots = set(found)
        return self._roots


# ---------------------------------------------------------------------------
# The write gate
# ---------------------------------------------------------------------------


def denied(path: Path, *, target: Path | None = None) -> ResultError:
    """The ``permission_denied`` refusal for a path the caller can see but may not act on."""
    return classified(VFSErrorKind.permission_denied, f"Permission denied: {path}", path, target=target)


class WriteGate:
    """The point checks a mutation passes before its first write statement.

    One batched fetch of the targets and their ancestors, decided in app
    code: a batch of any size is one resolver call and a handful of
    chunked reads, never a statement per path. Any refusal fails the
    batch whole. The kinds keep hidden and missing indistinguishable: a
    target or ancestor the caller cannot see answers ``not_found``
    exactly as an absent one does, and a creation is judged by coverage
    alone, never by what occupies the name.
    """

    def __init__(
        self,
        resolution: Resolution,
        tables: VFSTables,
        profile: DialectProfile,
        membership_budget: int,
        parameter_budget: int,
    ) -> None:
        self.resolution = resolution
        self._tables = tables
        self._profile = profile
        self._membership_budget = membership_budget
        self._parameter_budget = parameter_budget
        self.view = Visibility(resolution.read, tables, profile, membership_budget, parameter_budget)
        # Rows the target checks fetched, so a subtree check skips known files.
        self._known: dict[str, RowMapping] = {}

    @property
    def whole(self) -> bool:
        return self.resolution.write.whole

    async def targets(
        self, session: AsyncSession, targets: Sequence[Path], mode: GateMode, *, parents: bool = False
    ) -> list[ResultError]:
        """Refusals for *targets* under *mode*; empty when every target may proceed."""
        rights = self.resolution.read if mode == "read" else self.resolution.write
        if rights.whole or not targets:
            return []
        entry, tables, profile, budget = self._tables.entry, self._tables, self._profile, self._membership_budget
        prefixes = targets_with_ancestors(targets)
        rows = await rows_by_path(session, entry, prefixes, judged_columns(entry), profile, budget)
        self._known.update(rows)
        seen = await self.view.seen_kinds(session, rows)
        road = {path for path in seen if path in rows and not self.view.admits(rows[path])}
        # A creation has no row to read the level from: the posture rows on its chain decide.
        postures = await posture_rows(session, tables, profile, budget, prefixes) if mode != "read" else {}
        batch = {str(target) for target in targets}
        errors: list[ResultError] = []
        for target in dict.fromkeys(targets):
            refusal = self._decide(target, rows, seen, road, postures, batch, mode, parents=parents)
            if refusal is not None:
                errors.append(refusal)
        return errors

    async def subtrees(self, session: AsyncSession, roots: Sequence[Path], level: GrantLevel) -> list[ResultError]:
        """``permission_denied`` for each root with a row beneath it this authority may not act on.

        A root the caller's own pieces cover whole passes without a
        read; otherwise the rows beneath it that everyone does not hold
        at *level* are read in pages — one seek of the composite index,
        empty under an open posture — and each is checked, stopping at
        the first refusal. The read is proportional to the rows below
        the level, and only a caller whose rights are partial there pays
        it. Inside a hole the label decides nothing, so the rows there
        the label would have passed are paged too, a chunk of the hole's
        pieces at a time.
        """
        rights = self.resolution.read if level == "read" else self.resolution.write
        errors: list[ResultError] = []
        entry = self._tables.entry
        per_chunk = arm_budget(self._profile, self._parameter_budget, 2)
        unlabelled = [entry.c.everyone_level < rights.need]
        unlabelled += [
            and_(entry.c.everyone_level >= rights.need, or_(*(unit.predicate for unit in chunk)))
            for chunk in chunked(_judged_units(entry, rights.ranges().holes), per_chunk)
        ]
        for root in dict.fromkeys(roots):
            known = self._known.get(str(root))
            # A trashed row beneath the root is judged elsewhere, so cover of the root's paths proves nothing.
            covered = rights.whole or (rights.covers_subtree(str(root)) and not on_trash_chain(str(root)))
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
            if any(not rights.admits(judged_path(row), row["owner_id"], row["everyone_level"]) for row in page):
                return True
            if len(page) < _SUBTREE_PAGE:
                return False
            last = page[-1]["path"]

    def row(
        self, named: Path, judged: str, owner_id: str | None, everyone_level: int, level: GrantLevel
    ) -> ResultError | None:
        """The check for one row already in hand, judged at *judged* and refused as *named*.

        Hidden is absent, visible-but-barred is denied; the refusal names
        *named*, the path the caller sent, never the one the row sits at.
        """
        if not self.resolution.read.admits(judged, owner_id, everyone_level):
            return classified(VFSErrorKind.not_found, f"Not found: {named}", named)
        if level == "read_write" and not self.resolution.write.admits(judged, owner_id, everyone_level):
            return denied(named)
        return None

    async def missing(self, session: AsyncSession, target: Path) -> ResultError:
        """The refusal for a *target* this call cannot act on: hidden reads exactly as absent.

        The descent ladder runs over what the view shows — a hidden
        ancestor is a missing one — so the payload names only a prefix
        of the path the caller sent, and never what hides at it.
        """
        entry, profile, budget = self._tables.entry, self._profile, self._membership_budget
        rows = await rows_by_path(
            session, entry, targets_with_ancestors([target]), judged_columns(entry), profile, budget
        )
        return classify_miss(target, await self.view.seen_kinds(session, rows))

    def _decide(
        self,
        target: Path,
        rows: Mapping[str, RowMapping],
        seen: Mapping[str, str],
        road: set[str],
        postures: PostureRows,
        batch: set[str],
        mode: GateMode,
        *,
        parents: bool,
    ) -> ResultError | None:
        """One target's verdict; a missing ancestor the batch itself supplies is judged as its own target."""
        write = self.resolution.write
        creating = mode in ("create", "upsert")
        for ancestor in ancestor_chain(target):
            if str(ancestor) in seen:
                continue
            minted = creating and (parents or str(ancestor) in batch)
            if minted and write.reaches(str(ancestor), label_of(postures, str(ancestor))):
                continue
            if minted:
                return denied(ancestor, target=target)
            return classify_miss(target, seen)
        key = str(target)
        parent = str(target.parent_dir)
        if key in road:
            # A road directory shows only its name, so no verb may act on it.
            return denied(target)
        if key in seen:
            if mode in ("create", "read"):
                return None
            row = rows[key]
            return None if write.admits(judged_path(row), row["owner_id"], row["everyone_level"]) else denied(target)
        if mode in ("modify", "read"):
            return classify_miss(target, seen)
        if parent in road or not write.reaches(key, label_of(postures, key)):
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
        message = f"no grant for {principal} on {path}"
        return Result(
            ops=("revoke",),
            errors=[ResultError(kind=VFSErrorKind.not_found, message=message, severity=Severity.warning)],
        )
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
    its groups', and the everyone rows. A path it cannot see answers
    ``not_found``, as any hidden path does. "See" here is what the
    everyone level and the caller's own pieces reach, not rows: a path
    reached only through the owner floor or as a road directory answers
    ``not_found`` too.
    """
    grants = tables.grants
    prefixes = [str(p) for p in reversed(ancestors_and_self(str(path)))]
    stmt = select(
        grants.c.principal_id, grants.c.path_prefix, grants.c.level, grants.c.granted_by, grants.c.granted_at
    ).where(membership(grants.c.path_prefix, prefixes, profile))
    rows = (await session.execute(stmt)).mappings().all()
    postures = postures_of(GrantRow(r["principal_id"], r["path_prefix"], r["level"]) for r in rows)
    label = label_of(postures, str(path))
    if not gate.resolution.read.reaches(str(path), label):
        return Result(ops=("grants",), errors=[classified(VFSErrorKind.not_found, f"Not found: {path}", path)])
    if not gate.resolution.write.reaches(str(path), label):
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
    """Write the everyone row at *path*: ``open``, ``shared``, or ``private`` from here down.

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
    level = POSTURE_LEVELS[posture]
    await stamp_principals(session, tables, [EVERYONE_NAME], revision)
    written = await _upsert_grant(session, tables, path, EVERYONE_NAME, level, authority, revision)
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
        message = f"adding {member} to {group} would make the group nesting cyclic"
        return Result(ops=("add_member",), errors=[ResultError(kind=VFSErrorKind.authority_budget, message=message)])
    if below.depth + 1 + above.depth > MAX_GROUP_DEPTH:
        message = f"adding {member} to {group} would nest groups deeper than {MAX_GROUP_DEPTH}"
        return Result(ops=("add_member",), errors=[ResultError(kind=VFSErrorKind.authority_budget, message=message)])
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
        message = f"{member} is not a direct member of {group}"
        return Result(
            ops=("remove_member",),
            errors=[ResultError(kind=VFSErrorKind.not_found, message=message, severity=Severity.warning)],
        )
    await stamp_principals(session, tables, [member], revision)
    return Result(ops=("remove_member",), members=[{"principal_id": member, "group_id": group}])


def posture_row(posture: Posture, now: datetime) -> dict[str, object]:
    """The everyone row first touch plants at the mount root."""
    return {
        "principal_id": EVERYONE_NAME,
        "path_prefix": ROOT,
        "level": POSTURE_LEVELS[posture],
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
            message = f"group nesting deeper than {MAX_GROUP_DEPTH}; the membership rows break their bound"
            return ResultError(kind=VFSErrorKind.authority_budget, message=message)
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


async def _root_level(session: AsyncSession, tables: VFSTables) -> GrantLevel:
    """What the mount root gives everyone — one row, read beside the caller's own."""
    grants = tables.grants
    stmt = select(grants.c.level).where(grants.c.principal_id == EVERYONE_NAME, grants.c.path_prefix == ROOT)
    found = (await session.execute(stmt)).scalar_one_or_none()
    return cast("GrantLevel", found) if found is not None else "none"


def _size(value: object) -> int:
    """*value*'s own bytes plus, through every tuple, its items' — strings and ints are the leaves."""
    size = sys.getsizeof(value)
    if isinstance(value, tuple):
        size += sum(_size(item) for item in value)
    return size


def _units(entry: Table, rights: Rights, bind_cap: int) -> list[Clause]:
    """The everyone units, one unit per piece of the spans, and per slice of each owner arm's pieces under *bind_cap*.

    The everyone unit is the level alone; with holes in the rights it is
    the level on each piece of the mount outside them, so the fan still
    splits it across statements. Every piece is judged (:func:`_judged_units`).
    """
    ranges = rights.ranges()
    everyone = entry.c.everyone_level >= rights.need
    units = [Clause(everyone, 1)]
    if rights.holes:
        outside = _judged_units(entry, pieces(subtract(FULL, rights.holes)))
        units = [Clause(and_(unit.predicate, everyone), unit.binds + 1) for unit in outside]
    units += _judged_units(entry, ranges.arms)
    per_unit = max(1, min(_OWNER_PIECES_PER_UNIT, (bind_cap - 1) // 2))
    for owner, found in ranges.owners:
        for group in chunked(_judged_units(entry, found), per_unit):
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


def _judged_units(entry: FromClause, found: Pieces) -> list[Clause]:
    """One clause per piece on the judged path: ``path`` for a live row, ``origin_path`` for a trashed one.

    A live row carries no origin, so its units add ``origin_path IS
    NULL`` at no bind; a trashed row's units seek the origin index alone.
    """
    live = [
        Clause(and_(unit.predicate, entry.c.origin_path.is_(None)), unit.binds)
        for unit in _piece_units(entry.c.path, found)
    ]
    return [*live, *_piece_units(entry.c.origin_path, found)]


async def _owned_beneath(
    session: AsyncSession,
    entry: Table,
    profile: DialectProfile,
    membership_budget: int,
    owner: str,
    found: Pieces,
    candidates: set[str],
) -> set[str]:
    """The *candidates* holding a row *owner* owns whose judged path lies within the pieces *found*."""
    row = entry.alias("r")
    tests = [
        and_(row.c.owner_id == owner, or_(*(unit.predicate for unit in group)))
        for group in chunked(_judged_units(row, found), _OWNER_PIECES_PER_UNIT)
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
) -> set[str]:
    """The *candidates* holding a row everyone may see at the rights' level — one composite-index seek each.

    A row inside a hole does not count: its label is not yet the truth.
    """
    row = entry.alias("r")
    test = and_(row.c.everyone_level >= rights.need, judged_hole_free(row, rights.ranges().holes, profile))
    return await _beneath(session, entry, profile, max(1, membership_budget - 3), row, [test], candidates)


async def _origin_beneath(
    session: AsyncSession,
    entry: Table,
    profile: DialectProfile,
    membership_budget: int,
    found: Pieces,
    candidates: set[str],
) -> set[str]:
    """The *candidates* holding a trashed row whose origin lies within the pieces *found* — the road into the trash."""
    if not found.points and not found.opens:
        return set()
    row = entry.alias("r")
    tests = [
        or_(*(unit.predicate for unit in group))
        for group in chunked(_piece_units(row.c.origin_path, found), _OWNER_PIECES_PER_UNIT)
    ]
    per_chunk = max(1, membership_budget - 2 - 2 * _OWNER_PIECES_PER_UNIT)
    return await _beneath(session, entry, profile, per_chunk, row, tests, candidates)


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
    posture rows on its chain, as a creation's does.
    """
    if principal is not None and not _lawful_principal(principal):
        return ResultError(kind=VFSErrorKind.invalid, message=f"{op}: {principal!r} is not a grantable principal id")
    if level not in ("read", "read_write") and principal is not None:
        return ResultError(kind=VFSErrorKind.invalid, message=f"{op}: level must be 'read' or 'read_write'")
    postures = await posture_rows(session, tables, profile, membership_budget, ancestors_and_self(str(path)))
    label = label_of(postures, str(path))
    if gate.resolution.write.reaches(str(path), label):
        return None
    if gate.resolution.read.reaches(str(path), label):
        return denied(path)
    return classified(VFSErrorKind.not_found, f"Not found: {path}", path)


def _membership_refusal(op: str, group: str, member: str, authority: Authority) -> ResultError | None:
    if not authority.is_system:
        return ResultError(kind=VFSErrorKind.permission_denied, message=f"{op} is reserved to the system actor")
    if not group.startswith(GROUP_NAME_PREFIX) or len(group) == len(GROUP_NAME_PREFIX) or not _lawful_principal(group):
        return ResultError(kind=VFSErrorKind.invalid, message=f"{op}: a group id starts with {GROUP_NAME_PREFIX!r}")
    if not _lawful_principal(member):
        return ResultError(kind=VFSErrorKind.invalid, message=f"{op}: {member!r} cannot be a member")
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
