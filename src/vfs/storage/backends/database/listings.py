"""The listings ``ls`` and ``tree`` for ``DatabaseStorage``: whole, or a page at a time from a key.

``ls`` lists a directory by ``parent_id`` equality, never a prefix scan.
``tree`` lists a subtree by one sargable escaped ``LIKE`` on the path
cache, and a page of it adds the explicit half-open range ``(key,
root + "0")``, ``0`` being the byte after ``/``. Children order by the
binary-collated ``name`` column and subtrees by ``path``, byte-identical
across engines, and for siblings the two orders agree.

A page reads strictly after its key and fetches ``limit + 1`` rows to
know whether more follow, by the fill rule of
:mod:`~vfs.storage.backends.database.keyset`. The live side seeks the
partial indexes that hold live rows alone, so a page reads about
``limit`` rows however many tombstones lie in its range. Two listings
are not bounded that way and say so: the trash view's, whose rows are
the tombstones themselves, and a ``tree`` under ``max_depth``, whose
depth term filters the rows deeper than the bound after they are read.

Every function takes the op's live ``AsyncSession`` and only executes
SELECTs; none begins or commits.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NamedTuple

from sqlalchemy import func, select

from vfs.models.rows import LIVE_CHILDREN_INDEX, LIVE_PATH_INDEX
from vfs.paths import METADATA_ROOT, TRASH_ROOT, Path, address_of
from vfs.results import Result
from vfs.storage.backends.database.descent import (
    descendant_filter,
    liveness_filters,
    rows_by_path,
    tombstoned_roots,
)
from vfs.storage.backends.database.dialects import chunked
from vfs.storage.backends.database.keyset import filled, keyed
from vfs.storage.backends.database.membership import membership
from vfs.storage.backends.database.reads import (
    effective_columns,
    entry_columns,
    mappings_by_path,
    observe,
    observe_for,
    road_observation,
    screen,
)
from vfs.storage.backends.database.rights import RIGHTS_FIELDS

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from sqlalchemy import ColumnElement, Select, Table
    from sqlalchemy.engine import RowMapping
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models import Observation
    from vfs.models.rows import EntryId, VFSTables
    from vfs.paths import Address
    from vfs.storage.backends.database.dialects import DialectProfile
    from vfs.storage.backends.database.keyset import Emit, Fetch
    from vfs.storage.backends.database.rights import Visibility

    # The statement of one stream, read strictly after a path and at most a batch of rows.
    Build = Callable[[str | None, int | None], Select[Any]]

# ---------------------------------------------------------------------------
# ls
# ---------------------------------------------------------------------------


async def ls_rows(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    targets: Sequence[Path],
    columns: frozenset[str] | None,
    view: Visibility | None = None,
    *,
    after: Path | None = None,
    limit: int | None = None,
) -> Result:
    """Each directory target's children, each file target itself; or one page of one directory.

    Under a partial view a road directory lists like any directory, a
    row the caller holds only ``list`` on shows bare, and a hidden child
    directory shows as a bare name only when it is itself on the road; a
    hidden file never shows.

    A batch costs a fixed number of chunked statements and returns every
    child of every directory it names. With ``after`` or ``limit`` the
    call lists one page of one target, in name order, which is path
    order: the children strictly after the key, ``limit`` of them, and
    ``next_after`` set while more follow. The storage has refused,
    before any read, a key that names no child of the target and no row
    of the trash view's head, whose listing holds the tombstoned roots
    at every depth (:func:`~vfs.storage.backends.database.keyset.page_refused`).
    A page of that head is not bounded by its limit: it reads every
    tombstone of the mount, roots and their descendants alike, and sorts
    the roots among them by path, a set ``sweep`` bounds.
    """
    if after is not None or limit is not None:
        return await _ls_page(session, tables, profile, membership_budget, targets[0], columns, view, after, limit)
    fetched = effective_columns(columns, content=False)
    found = await mappings_by_path(
        session, tables, profile, membership_budget, targets, fetched, with_entry_id=True, judged=view is not None
    )
    shown, road, missing = await screen(session, tables, profile, membership_budget, targets, found, view)
    directories = [t for t in targets if t in road or ((f := shown.get(t)) is not None and f["kind"] == "directory")]
    children = await _children_by_parent(
        session, tables.entry, profile, membership_budget, directories, found.by_target, fetched, view=view
    )
    roots: list[Observation] | None = None
    rows: list[Observation] = []
    errors = []
    for target in targets:
        mapping = shown.get(target)
        if target == TRASH_ROOT:
            if roots is None:
                roots = await _trash_roots(session, tables, profile, fetched, view)
            rows.extend(roots)
        elif mapping is None and target not in road:
            errors.append(missing[target])
        elif mapping is not None and mapping["kind"] != "directory":
            rows.append(observe_for(view, mapping, fetched))
        else:
            listed = list(children.get(found.by_target[target]["entry_id"], ()))
            if target == METADATA_ROOT:
                listed = _with_trash_view(listed)
            rows.extend(listed)
    return Result(ops=("ls",), observations=rows, errors=errors)


# ---------------------------------------------------------------------------
# tree
# ---------------------------------------------------------------------------


async def tree_rows(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    path: Path,
    max_depth: int | None,
    columns: frozenset[str] | None,
    view: Visibility | None = None,
    *,
    after: Path | None = None,
    limit: int | None = None,
) -> Result:
    """Every row beneath *path*, in path order, to *max_depth* levels; or one page of them.

    Under a partial view the subtree read carries the visibility clauses
    at ``list`` (once per clause, merged), every row still passes the
    view — bare where the caller holds only ``list`` — and each named
    row's hidden ancestors inside the tree show as bare names, the road
    down to it.

    With ``after`` or ``limit`` the call lists one page: the rows
    strictly after the key, which lies beneath *path*, and ``next_after``
    set while more follow. Each clause of a view's pushdown pages as a
    stream of its own, and a page shows a road directory exactly once,
    on the page whose path range holds it. A road directory is a row of
    the page like any other: it counts toward ``limit`` and can be the
    key, which names only what the caller was shown. Under ``max_depth`` a page
    still reads the rows deeper than the bound in its range and drops
    them, so a shallow listing of a deep tree reads more rows than it
    returns.
    """
    fetched = effective_columns(columns, content=False)
    found = await mappings_by_path(
        session, tables, profile, membership_budget, [path], fetched, with_entry_id=False, judged=view is not None
    )
    shown, road, missing = await screen(session, tables, profile, membership_budget, [path], found, view)
    target = shown.get(path)
    if target is None and path not in road and path != TRASH_ROOT:
        return Result(ops=("tree",), errors=[missing[path]])
    if target is not None and target["kind"] != "directory":
        rows = [observe_for(view, target, fetched)]
        page = rows if after is None and limit is None else keyed(rows, None, after=after, limit=limit)[0]
        return Result(ops=("tree",), observations=page)
    address = address_of(str(path))
    wanted = fetched | {"deleted_at"} | (RIGHTS_FIELDS if view is not None else frozenset())

    def subtree(position: str | None, batch: int | None) -> Select[Any]:
        stmt = _subtree(tables.entry, profile, address, wanted, max_depth)
        if position is None and batch is None:
            return stmt
        return _pinned(
            _ranged(stmt, tables.entry, address, position, batch), tables.entry, profile, address, LIVE_PATH_INDEX
        )

    if after is not None or limit is not None:
        page = _TreePage(session, tables.entry, profile, membership_budget, fetched, view, address)
        return await page.read(subtree, after, limit)
    stmt = subtree(None, None)
    if view is None:
        rows = [observe(mapping, fetched) for mapping in (await session.execute(stmt)).mappings()]
        return Result(ops=("tree",), observations=rows)
    visible = await _visible_rows(session, stmt, view, address.stored)
    bare = {
        ancestor
        for mapping_path in visible
        for ancestor in _ancestors_below(mapping_path, address.stored)
        if ancestor not in visible
    }
    observed = {p: observe_for(view, m, fetched) for p, m in visible.items()}
    observed |= {p: road_observation(p) for p in bare}
    return Result(ops=("tree",), observations=[observed[p] for p in sorted(observed)])


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _ls_page(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    target: Path,
    columns: frozenset[str] | None,
    view: Visibility | None,
    after: Path | None,
    limit: int | None,
) -> Result:
    """One page of ``ls`` of one target: its children, the trash view's roots, or a file's own row."""
    fetched = effective_columns(columns, content=False)
    found = await mappings_by_path(
        session, tables, profile, membership_budget, [target], fetched, with_entry_id=True, judged=view is not None
    )
    shown, road, missing = await screen(session, tables, profile, membership_budget, [target], found, view)
    mapping = shown.get(target)
    entry = tables.entry
    wanted = fetched | {"deleted_at"} | (RIGHTS_FIELDS if view is not None else frozenset())
    if target == TRASH_ROOT:
        roots = _trash_roots_statement(entry, profile, wanted)
        streams = _narrowed(session, lambda position, batch: _after(roots, entry, position, batch), view, None)
        found_rows = await filled(streams, _shown_by(view, fetched), after=after, limit=limit)
        rows, key = keyed(found_rows.rows, found_rows.frontier, after=after, limit=limit)
    elif mapping is None and target not in road:
        return Result(ops=("ls",), errors=[missing[target]])
    elif mapping is not None and mapping["kind"] != "directory":
        rows, key = keyed([observe_for(view, mapping, fetched)], None, after=after, limit=limit)
    else:
        address = address_of(str(target))
        parent = found.by_target[str(target)]["entry_id"]
        children = _children_page(session, entry, profile, parent, address, wanted)
        emit = _children_shown(session, view, fetched, trashed=address.trashed)
        found_rows = await filled([children], emit, after=after, limit=limit)
        extras = [road_observation(TRASH_ROOT)] if target == METADATA_ROOT else []
        rows, key = keyed([*found_rows.rows, *extras], found_rows.frontier, after=after, limit=limit)
    return Result(ops=("ls",), observations=rows, next_after=key)


def _children_page(
    session: AsyncSession,
    entry: Table,
    profile: DialectProfile,
    parent: EntryId,
    address: Address,
    wanted: frozenset[str],
) -> Fetch:
    """The children of one directory as a stream: ``parent_id`` equality, the live index, name order.

    The key's last segment is the bound, because siblings sort by name as
    they sort by path, so one index serves the equality, the bound and the
    order. Its binds are the parent, the bound, the two meta-exclusion
    literals and the limit, whatever the directory holds.
    """

    async def fetch(position: str | None, batch: int | None) -> Sequence[RowMapping]:
        stmt = select(*entry_columns(entry, wanted)).where(
            entry.c.parent_id == parent,
            *liveness_filters(entry, profile, include_meta=address.meta, trashed=address.trashed),
        )
        if position is not None:
            stmt = stmt.where(entry.c.name > position.rsplit("/", 1)[1])
        stmt = _pinned(stmt.order_by(entry.c.name), entry, profile, address, LIVE_CHILDREN_INDEX)
        return (await session.execute(stmt if batch is None else stmt.limit(batch))).mappings().all()

    return fetch


def _children_shown(session: AsyncSession, view: Visibility | None, fetched: frozenset[str], *, trashed: bool) -> Emit:
    """The children a caller is shown from one fetched batch, as :func:`_children_by_parent` shows them."""

    async def emit(mappings: Sequence[RowMapping]) -> list[Observation]:
        if view is None:
            return [observe(mapping, fetched) for mapping in mappings]
        hidden = [m["path"] for m in mappings if m["kind"] == "directory" and not view.shows(m)]
        road = await view.road(session, hidden, trashed=trashed) if hidden else set()
        return [
            observe_for(view, m, fetched) if view.shows(m) else road_observation(m["path"])
            for m in mappings
            if view.shows(m) or m["path"] in road
        ]

    return emit


class _TreePage(NamedTuple):
    """What one page of a subtree reads with: the session, the entries table and its budget, the view, the root."""

    session: AsyncSession
    entry: Table
    profile: DialectProfile
    membership_budget: int
    fetched: frozenset[str]
    view: Visibility | None
    address: Address

    async def read(self, subtree: Build, after: Path | None, limit: int | None) -> Result:
        """One page of the subtree: its rows after the key, and under a view the road directories in its range.

        A hidden directory shows on the page that holds its own path. It is
        the ancestor of a shown row in hand, or it holds no row in hand and
        the page's key lies between it and its first child, as ``/d/a.txt``
        lies between ``/d/a`` and ``/d/a/x``. The second kind is a prefix of
        the key, so the prefixes stored as directories are asked of the
        view by name, and the key moves back over what it finds until no
        such directory is left. A key with no such prefix costs nothing more.
        """
        view, stored = self.view, self.address.stored
        streams = _narrowed(self.session, subtree, view, stored)
        found = await filled(streams, _shown_by(view, self.fetched), after=after, limit=limit)
        rows, key = keyed(found.rows, found.frontier, after=after, limit=limit)
        if view is None:
            return Result(ops=("tree",), observations=rows, next_after=key)
        have = {row.path for row in found.rows}
        roads = {
            ancestor
            for row in found.rows
            for ancestor in _ancestors_below(row.path, stored)
            if ancestor not in have and (after is None or ancestor > after)
        }
        asked: set[str] = set()
        while True:
            everything = [*found.rows, *(road_observation(path) for path in sorted(roads))]
            rows, key = keyed(everything, found.frontier, after=after, limit=limit)
            candidates = [
                prefix
                for prefix in _doors_before(key, stored)
                if prefix not in have | roads | asked and (after is None or prefix > after)
            ]
            if not candidates:
                return Result(ops=("tree",), observations=rows, next_after=key)
            asked |= set(candidates)
            roads |= await self._roads_among(subtree, candidates)

    async def _roads_among(self, subtree: Build, candidates: list[str]) -> set[str]:
        """The candidates the whole ``tree`` shows as road directories: each holds a row of the subtree shown here.

        One bounded fetch finds the candidates stored as directories on the
        root's side of the tombstone. Each of those then reads the subtree's
        own statement within its range, through the view, until one row is
        shown or none is left: the rule the whole listing applies, an
        ancestor of a row it returns, and no wider one.
        """
        entry, view = self.entry, self.view
        assert view is not None
        columns = [entry.c.path, entry.c.kind, entry.c.deleted_at]
        found = await rows_by_path(self.session, entry, candidates, columns, self.profile, self.membership_budget)
        trashed = self.address.trashed
        doors = [
            p for p, row in found.items() if row["kind"] == "directory" and (row["deleted_at"] is not None) == trashed
        ]
        roads: set[str] = set()
        for door in doors:

            def beneath(position: str | None, batch: int | None, door: str = door) -> Select[Any]:
                stmt = subtree(None, None).where(entry.c.path > (position or door + "/"), entry.c.path < door + "0")
                return stmt if batch is None else stmt.limit(batch)

            streams = _narrowed(self.session, beneath, view, door)
            if (await filled(streams, _shown_by(view, self.fetched), after=None, limit=1)).rows:
                roads.add(door)
        return roads


def _doors_before(key: str | None, root: str) -> list[str]:
    """The prefixes of ``key`` beneath ``root`` that sort at or before it and hold no path at or before it.

    Each is a prefix followed in ``key`` by a byte below ``/``: ``/d/a``
    for ``/d/a.txt``. Such a directory's first child sorts after the key.
    """
    if key is None:
        return []
    start = 1 if root == "/" else len(root) + 1
    return [key[:index] for index in range(start + 1, len(key)) if key[index] < "/" and key[index - 1] != "/"]


def _subtree(
    entry: Table, profile: DialectProfile, address: Address, wanted: frozenset[str], max_depth: int | None
) -> Select[Any]:
    """Every row strictly beneath the stored root, on its side of the tombstone, in path order."""
    stmt = (
        select(*entry_columns(entry, wanted))
        .where(
            descendant_filter(entry, address.stored, profile),
            *liveness_filters(entry, profile, include_meta=address.meta, trashed=address.trashed),
        )
        .order_by(entry.c.path)
    )
    if max_depth is not None:
        stmt = stmt.where(_slash_count(entry) <= _depth(address.stored) + max_depth)
    return stmt


def _ranged(stmt: Select[Any], entry: Table, address: Address, position: str | None, batch: int | None) -> Select[Any]:
    """``stmt`` read strictly after ``position`` within its root's half-open range, at most ``batch`` rows.

    The explicit bounds make the range sargable on every engine, beside
    the ``LIKE`` that stays as the correctness term.
    """
    stmt = stmt.where(entry.c.path > (address.stored if position is None else position))
    if address.stored != "/":
        stmt = stmt.where(entry.c.path < address.stored + "0")
    return stmt if batch is None else stmt.limit(batch)


def _pinned(stmt: Select[Any], entry: Table, profile: DialectProfile, address: Address, index: str) -> Select[Any]:
    """``stmt`` held to ``index``, a partial index over the live rows, where the profile declares a hint for it.

    Only a live page carries the pin: the index holds no tombstone, so a
    trash-view page could not be served by it.
    """
    if profile.live_index_hint is None or address.trashed:
        return stmt
    return stmt.with_hint(entry, profile.live_index_hint.format(index=index), profile.name)


def _after(stmt: Select[Any], entry: Table, position: str | None, batch: int | None) -> Select[Any]:
    """``stmt`` read strictly after ``position``, at most ``batch`` rows."""
    stmt = stmt if position is None else stmt.where(entry.c.path > position)
    return stmt if batch is None else stmt.limit(batch)


def _narrowed(session: AsyncSession, build: Build, view: Visibility | None, scope: str | None) -> list[Fetch]:
    """One stream for each statement a view's pushdown turns the built statement into; one with no view."""
    count = 1 if view is None else len(view.narrow(build(None, None), scope))

    def stream(index: int) -> Fetch:
        async def fetch(position: str | None, batch: int | None) -> Sequence[RowMapping]:
            stmt = build(position, batch)
            statement = stmt if view is None else view.narrow(stmt, scope)[index]
            return (await session.execute(statement)).mappings().all()

        return fetch

    return [stream(index) for index in range(count)]


def _shown_by(view: Visibility | None, fetched: frozenset[str]) -> Emit:
    """The rows of a pushed-down batch the caller is shown: each that passes the view's own verdict."""

    async def emit(mappings: Sequence[RowMapping]) -> list[Observation]:
        return [observe_for(view, m, fetched) for m in mappings if view is None or view.holds(m, view.need)]

    return emit


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
                select(entry.c.parent_id, *entry_columns(entry, wanted))
                .where(
                    membership(entry.c.parent_id, chunk, profile),
                    *liveness_filters(entry, profile, include_meta=include_meta, trashed=trashed),
                )
                .order_by(entry.c.parent_id, entry.c.name)
            )
            for mapping in (await session.execute(stmt)).mappings():
                listed.setdefault(mapping["parent_id"], []).append(mapping)
        if view is None:
            children |= {parent: [observe(m, fetched) for m in rows] for parent, rows in listed.items()}
            continue
        mappings = [m for rows in listed.values() for m in rows]
        hidden = [m["path"] for m in mappings if m["kind"] == "directory" and not view.shows(m)]
        road = await view.road(session, hidden, trashed=trashed) if hidden else set()
        for parent, rows in listed.items():
            for mapping in rows:
                if view.shows(mapping):
                    children.setdefault(parent, []).append(observe_for(view, mapping, fetched))
                elif mapping["path"] in road:
                    children.setdefault(parent, []).append(road_observation(mapping["path"]))
    return children


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


def _trash_roots_statement(entry: Table, profile: DialectProfile, wanted: frozenset[str]) -> Select[Any]:
    """The tombstoned roots, at their own paths, in path order."""
    return (
        select(*entry_columns(entry, wanted))
        .where(tombstoned_roots(entry), *liveness_filters(entry, profile, include_meta=False, trashed=True))
        .order_by(entry.c.path)
    )


async def _trash_roots(
    session: AsyncSession, tables: VFSTables, profile: DialectProfile, fetched: frozenset[str], view: Visibility | None
) -> list[Observation]:
    """``ls`` of the trash view's head: every tombstoned root, at its own path, in path order."""
    wanted = fetched | {"deleted_at"} | (RIGHTS_FIELDS if view is not None else frozenset())
    stmt = _trash_roots_statement(tables.entry, profile, wanted)
    if view is None:
        return [observe(mapping, fetched) for mapping in (await session.execute(stmt)).mappings()]
    visible = await _visible_rows(session, stmt, view, None)
    return [observe_for(view, visible[path], fetched) for path in sorted(visible)]


def _with_trash_view(listed: list[Observation]) -> list[Observation]:
    """The meta root's listing with the synthesized trash view in its name order — no row is ever stored there."""
    return sorted([*listed, road_observation(TRASH_ROOT)], key=lambda row: row.path.name)


def _depth(stored: str) -> int:
    """Segment depth of a stored path string: 0 for the root."""
    return 0 if stored == "/" else stored.count("/")


def _slash_count(entry: Table) -> ColumnElement[int]:
    """Portable segment-depth expression: slashes in the path column."""
    return func.char_length(entry.c.path) - func.char_length(func.replace(entry.c.path, "/", ""))
