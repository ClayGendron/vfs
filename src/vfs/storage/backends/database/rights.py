"""The enforcement spine's storage half — rights read, cached, compiled, and gated.

Every verb resolves its authority here, inside its own transaction: the
grant revision first (one row), then — only when the cache misses — the
subjects' group closures (one chunked statement per nesting level) and
every grant row naming a subject, one of its groups, or everyone. The
pure resolver (:mod:`vfs.storage.grants`) turns those into
:class:`~vfs.storage.grants.Rights` at the two levels a verb can need.
The system actor skips all of it and holds everything.

Reads filter through a :class:`Visibility`; mutations are checked by a
:class:`WriteGate`. Both treat :meth:`Rights.admits` — Python, exact for
any number of arms — as the authority every row passes; SQL predicates
are pushdowns that narrow toward it where a statement's shape needs one
(a ``LIMIT``, an aggregate, a subtree scan). A predicate too wide for
one statement splits into clauses the way glob's pattern fan does, each
inside the dialect's bind and depth budgets; a caller runs its statement
once per clause and merges.

A directory is *on the road* when a row the caller can see lies beneath
it: it shows as a bare name — path and kind, nothing else — so an agent
can walk down to what it may read, and it learns nothing its visible
rows' own paths do not already print. A write under a road-only
directory is refused on the directory, before the target name is
looked up, so the refusal never depends on what hides there.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final, Literal, NamedTuple, cast

from sqlalchemy import and_, delete, insert, not_, or_, select, true, update

from vfs.paths import ROOT, Path
from vfs.results import Result, ResultError, Severity, VFSErrorKind, classified
from vfs.storage.backends.database.descent import (
    LIKE_ESCAPE,
    ancestor_chain,
    classify_miss,
    descendant_filter,
    escape_like,
    rows_by_path,
    targets_with_ancestors,
)
from vfs.storage.backends.database.dialects import arm_budget, chunked, membership_budget
from vfs.storage.backends.database.membership import membership
from vfs.storage.grants import (
    EVERYONE,
    GROUP_PREFIX,
    LEVEL_RANK,
    MAX_GROUP_DEPTH,
    POSTURE_LEVELS,
    GrantRow,
    Rights,
    ancestors_and_self,
    resolve,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from sqlalchemy import Column, ColumnElement, Table
    from sqlalchemy.engine import CursorResult, RowMapping
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.authority import Authority
    from vfs.models.rows import VFSTables
    from vfs.storage.backends.database.dialects import DialectProfile
    from vfs.storage.grants import GrantLevel, OwnerArm, Posture

RIGHTS_CACHE: Final = 256
"""Resolved authorities remembered per mount, keyed by subjects and grant revision."""

RESERVED_PRINCIPALS: Final[frozenset[str]] = frozenset({EVERYONE, "system", "anon"})
"""Ids no grant or membership may name: posture belongs to ``posture``,
the system actor needs no grant, and anonymous holds only the posture."""

# Prefixes per owner-arm unit: each is two binds and one OR level deep.
_OWNER_PREFIXES_PER_UNIT: Final = 50

# Subtree rows read per page when a subtree mutation must check each row.
_SUBTREE_PAGE: Final = 1_000

GateMode = Literal["modify", "upsert", "create", "read"]
"""What a mutation needs at a target: an existing row to change (``modify``),
change-or-create (``upsert``), a new row (``create``), or an existing row
it only reads (``read`` — an edge's target)."""


class Resolution(NamedTuple):
    """One authority's rights at both levels, the root's posture, and the revision read."""

    read: Rights
    write: Rights
    root_level: GrantLevel
    revision: int


class Clause(NamedTuple):
    """One statement's share of a visibility predicate and the binds it spends."""

    predicate: ColumnElement[bool]
    binds: int


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


class RightsCache:
    """A small LRU of resolved authorities; a grant write bumps the key, never the entries."""

    def __init__(self, size: int = RIGHTS_CACHE) -> None:
        self._size = size
        self._entries: OrderedDict[tuple[tuple[str, ...], int], Resolution] = OrderedDict()

    def get(self, key: tuple[tuple[str, ...], int]) -> Resolution | None:
        found = self._entries.get(key)
        if found is not None:
            self._entries.move_to_end(key)
        return found

    def put(self, key: tuple[tuple[str, ...], int], value: Resolution) -> None:
        self._entries[key] = value
        while len(self._entries) > self._size:
            self._entries.popitem(last=False)


async def read_revision(session: AsyncSession, tables: VFSTables) -> int:
    """The grant spine's current revision — one single-row read."""
    meta = tables.meta
    value = (await session.execute(select(meta.c.grant_revision).where(meta.c.id == 1))).scalar_one_or_none()
    return int(value or 0)


async def resolve_authority(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    authority: Authority,
    cache: RightsCache,
) -> Resolution | ResultError:
    """*authority*'s rights, from the cache or from the rows; a refusal when the walk breaks its bound.

    The subjects' closures are walked per member and never pooled: a
    member's groups are that member's own, and the meet across members
    runs after each member's union is finished.
    """
    if authority.is_system:
        return Resolution(Rights.everything("read"), Rights.everything("read_write"), "read_write", -1)
    revision = await read_revision(session, tables)
    subjects = authority.subject_names
    key = (subjects, revision)
    cached = cache.get(key)
    if cached is not None:
        return cached
    if authority.is_anonymous:
        closures: dict[str, frozenset[str]] = {sub: frozenset() for sub in subjects}
    else:
        walked = await _closures(session, tables, profile, membership_budget, subjects)
        if isinstance(walked, ResultError):
            return walked
        closures = walked
    ids = {*subjects, EVERYONE, *(group for groups in closures.values() for group in groups)}
    rows = await _grant_rows(session, tables, profile, membership_budget, sorted(ids))
    floor = not authority.is_anonymous
    resolution = Resolution(
        resolve(closures, rows, "read", owner_floor=floor),
        resolve(closures, rows, "read_write", owner_floor=floor),
        next((row.level for row in rows if row.principal_id == EVERYONE and row.path_prefix == ROOT), "none"),
        revision,
    )
    cache.put(key, resolution)
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


def cover_clause(column: Any, prefix: str, profile: DialectProfile) -> ColumnElement[bool]:
    """*column* is *prefix* or lies beneath it; the root covers every row."""
    if prefix == ROOT:
        return true()
    return or_(column == prefix, column.like(escape_like(prefix, profile) + "/%", escape=LIKE_ESCAPE))


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
    units = _units(entry, rights, profile)
    bind_cap = max(1, membership_budget(profile, parameter_budget) // 2)
    count_cap = arm_budget(profile, parameter_budget, 1)
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


class Visibility:
    """What one read call may see: its rights, the road beneath them, and their pushdown.

    ``whole`` callers skip every filter. For the rest, :meth:`admits` is
    the authority on each row (it needs the row's ``path`` and
    ``owner_id``) and :meth:`road` names the hidden directories that lead
    to a visible row.
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

    @property
    def whole(self) -> bool:
        return self.rights.whole

    def admits(self, mapping: RowMapping) -> bool:
        return self.rights.admits(mapping["path"], mapping["owner_id"])

    def clauses(self, entry: Table | None = None) -> list[Clause] | None:
        """This view's predicate on *entry* (the entries table by default)."""
        target = self._tables.entry if entry is None else entry
        return visibility_clauses(target, self.rights, self._profile, self._parameter_budget)

    async def road(self, session: AsyncSession, candidates: Iterable[str]) -> set[str]:
        """The *candidates* (directory paths) a visible row lies beneath; the root always.

        Two sources: every existing arm root is visible, so its ancestors
        are on the road; and a member's owned rows are visible wherever
        its owner arm reaches, so a candidate holding one is too.
        """
        wanted = set(candidates)
        found = wanted & {ROOT}
        wanted -= found
        if not wanted or self.rights.empty:
            return found
        for root in await self._existing_roots(session):
            found.update(ancestor for ancestor in ancestors_and_self(root)[1:] if ancestor in wanted)
        rest = wanted - found
        for arm in self.rights.owner_arms:
            if not rest:
                break
            owned = await _owned_beneath(session, self._tables.entry, self._profile, self._membership_budget, arm, rest)
            found |= owned
            rest -= owned
        return found

    async def seen_kinds(self, session: AsyncSession, rows: Mapping[str, RowMapping]) -> dict[str, str]:
        """``path → kind`` over the rows this view shows: visible ones, road directories, the root.

        The descent ladder classifies against this map, so a hidden
        ancestor reads exactly as a missing one.
        """
        visible = {path: row["kind"] for path, row in rows.items() if self.rights.admits(path, row["owner_id"])}
        hidden = [path for path, row in rows.items() if path not in visible and row["kind"] == "directory"]
        for path in await self.road(session, hidden):
            visible[path] = "directory"
        visible[ROOT] = "directory"
        return visible

    async def _existing_roots(self, session: AsyncSession) -> set[str]:
        if self._roots is None:
            entry = self._tables.entry
            roots = [prefix for prefix in self.rights.roots() if prefix != ROOT]
            found = await rows_by_path(session, entry, roots, [entry.c.path], self._profile, self._membership_budget)
            self._roots = set(found)
        return self._roots


# ---------------------------------------------------------------------------
# The write gate
# ---------------------------------------------------------------------------


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
        entry = self._tables.entry
        columns = [entry.c.path, entry.c.kind, entry.c.owner_id]
        rows = await rows_by_path(
            session, entry, targets_with_ancestors(targets), columns, self._profile, self._membership_budget
        )
        self._known.update(rows)
        seen = await self.view.seen_kinds(session, rows)
        road = {path for path in seen if path in rows and not self.view.rights.admits(path, rows[path]["owner_id"])}
        errors: list[ResultError] = []
        for target in dict.fromkeys(targets):
            refusal = self._decide(target, rows, seen, road, mode, parents=parents)
            if refusal is not None:
                errors.append(refusal)
        return errors

    async def subtrees(self, session: AsyncSession, roots: Sequence[Path], level: GrantLevel) -> list[ResultError]:
        """``permission_denied`` for each root with a row beneath it this authority may not act on.

        A root one arm covers whole, no hole inside, passes without a
        read; otherwise its subtree is read in pages and each row checked,
        stopping at the first refusal. The read is proportional to the
        subtree, and only a caller whose rights are partial there pays it.
        """
        rights = self.resolution.read if level == "read" else self.resolution.write
        errors: list[ResultError] = []
        entry = self._tables.entry
        for root in dict.fromkeys(roots):
            known = self._known.get(str(root))
            if rights.covers_subtree(str(root)) or (known is not None and known["kind"] != "directory"):
                continue
            last = str(root)
            while True:
                stmt = (
                    select(entry.c.path, entry.c.owner_id)
                    .where(descendant_filter(entry, str(root), self._profile), entry.c.path > last)
                    .order_by(entry.c.path)
                    .limit(_SUBTREE_PAGE)
                )
                page = (await session.execute(stmt)).all()
                if any(not rights.admits(row.path, row.owner_id) for row in page):
                    errors.append(_denied(root))
                    break
                if len(page) < _SUBTREE_PAGE:
                    break
                last = page[-1].path
        return errors

    def row(self, path: Path, owner_id: str | None, level: GrantLevel) -> ResultError | None:
        """The check for one row already in hand: hidden is absent, visible-but-barred is denied."""
        if not self.resolution.read.admits(str(path), owner_id):
            return classified(VFSErrorKind.not_found, f"Not found: {path}", path)
        if level == "read_write" and not self.resolution.write.admits(str(path), owner_id):
            return _denied(path)
        return None

    def creatable(self, path: Path) -> ResultError | None:
        """Whether a new row may appear at *path*: coverage alone decides."""
        if self.resolution.write.covers(str(path)):
            return None
        return _denied(path)

    def _decide(
        self,
        target: Path,
        rows: Mapping[str, RowMapping],
        seen: Mapping[str, str],
        road: set[str],
        mode: GateMode,
        *,
        parents: bool,
    ) -> ResultError | None:
        write = self.resolution.write
        creating = mode in ("create", "upsert")
        for ancestor in ancestor_chain(target):
            if str(ancestor) in seen:
                continue
            if creating and parents and write.covers(str(ancestor)):
                continue
            if creating and parents:
                return _denied(ancestor, target=target)
            return classify_miss(target, seen)
        key = str(target)
        parent = str(target.parent_dir)
        if key in road:
            return None if mode == "create" else _denied(target)
        if key in seen:
            if mode in ("create", "read"):
                return None
            return None if write.admits(key, rows[key]["owner_id"]) else _denied(target)
        if mode in ("modify", "read"):
            return classify_miss(target, seen)
        if parent in road or not write.covers(key):
            return _denied(target)
        return None


# ---------------------------------------------------------------------------
# The grant verbs
# ---------------------------------------------------------------------------


async def grant_rows(
    session: AsyncSession,
    tables: VFSTables,
    gate: WriteGate,
    *,
    path: Path,
    principal: str,
    level: GrantLevel,
    authority: Authority,
) -> Result:
    """Write or replace *principal*'s row on *path*; the revision bumps first.

    The granting authority must hold ``read_write`` on *path* for every
    subject, so what it grants never exceeds its own level there.
    """
    refusal = _grant_refusal("grant", gate, path, principal, level)
    if refusal is not None:
        return Result(ops=("grant",), errors=[refusal])
    revision = await bump_revision(session, tables)
    written = await _upsert_grant(session, tables, path, principal, level, authority, revision)
    return Result(ops=("grant",), grants=[written])


async def revoke_rows(
    session: AsyncSession, tables: VFSTables, gate: WriteGate, *, path: Path, principal: str, authority: Authority
) -> Result:
    """Remove *principal*'s row on *path*, under the same gate as ``grant``; a missing row is a warning.

    *authority* is accepted for signature parity; the gate already judged it.
    """
    del authority
    refusal = _grant_refusal("revoke", gate, path, principal, "read")
    if refusal is not None:
        return Result(ops=("revoke",), errors=[refusal])
    await bump_revision(session, tables)
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
    ``not_found``, as any hidden path does.
    """
    if not gate.resolution.read.covers(str(path)) and not gate.resolution.read.whole:
        return Result(ops=("grants",), errors=[classified(VFSErrorKind.not_found, f"Not found: {path}", path)])
    grants = tables.grants
    prefixes = [str(p) for p in reversed(ancestors_and_self(str(path)))]
    stmt = select(
        grants.c.principal_id, grants.c.path_prefix, grants.c.level, grants.c.granted_by, grants.c.granted_at
    ).where(membership(grants.c.path_prefix, prefixes, profile))
    rows = (await session.execute(stmt)).mappings().all()
    if not gate.resolution.write.covers(str(path)):
        own = await _own_ids(session, tables, profile, membership_budget, authority)
        rows = [row for row in rows if row["principal_id"] in own]
    listed = [dict(row) for row in sorted(rows, key=lambda r: (r["path_prefix"], r["principal_id"]))]
    return Result(ops=("grants",), grants=listed)


async def set_posture(
    session: AsyncSession, tables: VFSTables, gate: WriteGate, *, path: Path, posture: Posture, authority: Authority
) -> Result:
    """Write the everyone row at *path*: ``open``, ``shared``, or ``private`` from here down.

    The deepest everyone row covering a path decides what everyone holds
    there; principal and group rows still widen on top.
    """
    refusal = _grant_refusal("posture", gate, path, None, "read_write")
    if refusal is not None:
        return Result(ops=("posture",), errors=[refusal])
    revision = await bump_revision(session, tables)
    written = await _upsert_grant(session, tables, path, EVERYONE, POSTURE_LEVELS[posture], authority, revision)
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
    bound is refused, never stored.
    """
    refusal = _membership_refusal("add_member", group, member, authority)
    if refusal is not None:
        return Result(ops=("add_member",), errors=[refusal])
    await bump_revision(session, tables)
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
        await session.execute(insert(memberships).values(**row))
    return Result(ops=("add_member",), members=[row])


async def remove_member_rows(
    session: AsyncSession, tables: VFSTables, *, group: str, member: str, authority: Authority
) -> Result:
    """Remove *member*'s direct membership of *group* — the system actor only; a missing row is a warning."""
    refusal = _membership_refusal("remove_member", group, member, authority)
    if refusal is not None:
        return Result(ops=("remove_member",), errors=[refusal])
    await bump_revision(session, tables)
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
    return Result(ops=("remove_member",), members=[{"principal_id": member, "group_id": group}])


async def bump_revision(session: AsyncSession, tables: VFSTables) -> int:
    """Advance the grant revision — the first statement of every grant or membership write."""
    meta = tables.meta
    await session.execute(update(meta).where(meta.c.id == 1).values(grant_revision=meta.c.grant_revision + 1))
    return await read_revision(session, tables)


def posture_row(posture: Posture, now: datetime) -> dict[str, object]:
    """The everyone row first touch plants at the mount root."""
    return {
        "principal_id": EVERYONE,
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


def _units(entry: Table, rights: Rights, profile: DialectProfile) -> list[Clause]:
    """One clause per arm and per owner-arm slice, each carrying its bind spend."""
    units: list[Clause] = []
    for arm in rights.arms:
        predicate = and_(
            cover_clause(entry.c.path, arm.prefix, profile),
            *(not_(cover_clause(entry.c.path, hole, profile)) for hole in arm.holes),
        )
        units.append(Clause(predicate, _cover_binds(arm.prefix) + sum(_cover_binds(hole) for hole in arm.holes)))
    for owner_arm in rights.owner_arms:
        for group in chunked(list(owner_arm.prefixes), _OWNER_PREFIXES_PER_UNIT):
            covered = or_(*(cover_clause(entry.c.path, prefix, profile) for prefix in group))
            spend = 1 + sum(_cover_binds(prefix) for prefix in group)
            units.append(Clause(and_(entry.c.owner_id == owner_arm.owner, covered), spend))
    return units


def _cover_binds(prefix: str) -> int:
    return 0 if prefix == ROOT else 2


async def _owned_beneath(
    session: AsyncSession,
    entry: Table,
    profile: DialectProfile,
    membership_budget: int,
    arm: OwnerArm,
    candidates: set[str],
) -> set[str]:
    """The *candidates* holding a row *arm*'s owner owns within its reach.

    The byte range ``(d/, d0)`` is every path under ``d`` in bytewise
    order — sargable where a LIKE on a joined column is not.
    """
    directory, row = entry.alias("d"), entry.alias("r")
    found: set[str] = set()
    per_chunk = max(1, membership_budget - 3 - 2 * _OWNER_PREFIXES_PER_UNIT)
    for chunk in chunked(sorted(candidates), per_chunk):
        for group in chunked(list(arm.prefixes), _OWNER_PREFIXES_PER_UNIT):
            beneath = and_(
                row.c.owner_id == arm.owner,
                row.c.path > directory.c.path.concat("/"),
                row.c.path < directory.c.path.concat("0"),
                or_(*(cover_clause(row.c.path, prefix, profile) for prefix in group)),
            )
            stmt = select(directory.c.path).where(
                membership(cast("Column[Any]", directory.c.path), chunk, profile),
                select(row.c.id).where(beneath).exists(),
            )
            found.update((await session.execute(stmt)).scalars())
    return found


def _denied(path: Path, *, target: Path | None = None) -> ResultError:
    return classified(VFSErrorKind.permission_denied, f"Permission denied: {path}", path, target=target)


def _grant_refusal(
    op: str, gate: WriteGate, path: Path, principal: str | None, level: GrantLevel
) -> ResultError | None:
    """The shared gate of the grant verbs: a lawful principal and level, and ``read_write`` on *path*."""
    if principal is not None and (principal in RESERVED_PRINCIPALS or not principal.strip()):
        return ResultError(kind=VFSErrorKind.invalid, message=f"{op}: {principal!r} is a reserved principal id")
    if level not in ("read", "read_write") and principal is not None:
        return ResultError(kind=VFSErrorKind.invalid, message=f"{op}: level must be 'read' or 'read_write'")
    if gate.resolution.write.covers(str(path)):
        return None
    if gate.resolution.read.covers(str(path)):
        return _denied(path)
    return classified(VFSErrorKind.not_found, f"Not found: {path}", path)


def _membership_refusal(op: str, group: str, member: str, authority: Authority) -> ResultError | None:
    if not authority.is_system:
        return ResultError(kind=VFSErrorKind.permission_denied, message=f"{op} is reserved to the system actor")
    if not group.startswith(GROUP_PREFIX) or len(group) == len(GROUP_PREFIX):
        return ResultError(kind=VFSErrorKind.invalid, message=f"{op}: a group id starts with {GROUP_PREFIX!r}")
    if member in RESERVED_PRINCIPALS or not member.strip():
        return ResultError(kind=VFSErrorKind.invalid, message=f"{op}: {member!r} cannot be a member")
    return None


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
    return {*subjects, *groups, EVERYONE}


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
