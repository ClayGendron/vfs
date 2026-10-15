"""The storage half of grants — random worlds replayed through the verbs.

Each world from ``tests.support.grant_worlds`` is written into a fresh
SQLite mount through the public verbs, then asked the oracle's question
two ways: through ``glob`` (the whole read path — pushdown, the Python
authority, and the road), and through the compiled clauses alone under
a starved bind budget, so the chunked fan splits every predicate.
"""

from __future__ import annotations

import random
from dataclasses import replace
from datetime import UTC, datetime
from itertools import pairwise
from typing import TYPE_CHECKING, Any, Literal, cast, get_args

import pytest
from sqlalchemy import and_, delete, event, insert, select, update
from sqlalchemy.exc import OperationalError

from tests.support.grant_worlds import DIRECTORIES, LAYOUTS, PATHS, SUBJECT_SETS, Layout, random_world
from tests.support.oracles.grants import GrantWorld, everyone_rank, set_rank
from vfs.authority import ANONYMOUS_NAME, EVERYONE_NAME, Authority, Principal
from vfs.models import Entry
from vfs.models.rows import build_vfs_tables
from vfs.ops import VERB_RUNGS
from vfs.paths import Path
from vfs.results import ErrorKind, Result
from vfs.storage import ResolvedPair
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database import backend as backend_module
from vfs.storage.backends.database import rights as rights_module
from vfs.storage.backends.database.dialects import SQLITE
from vfs.storage.backends.database.engine import EngineHost
from vfs.storage.backends.database.labels import Mark, Relabeller, mark_relabel
from vfs.storage.backends.database.ranges import visible_entries
from vfs.storage.backends.database.revision import bump_revision
from vfs.storage.backends.database.rights import (
    Resolution,
    RightsCache,
    RightsKey,
    WriteGate,
    grant_rows,
    resolve_authority,
    set_posture,
    visibility_clauses,
    weight,
)
from vfs.storage.backends.memory import InMemoryStorage
from vfs.storage.grants import (
    LEVEL_RANK,
    GrantLevel,
    GrantRow,
    OwnerArm,
    Posture,
    Rights,
    cover,
    cover_all,
    resolve,
    subtract,
    union,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping, Sequence

    from sqlalchemy.engine import CursorResult, RowMapping

WORLDS = 30
SYSTEM = Authority.system()
_POSTURES: tuple[Posture, ...] = get_args(Posture)
_GRANTABLE: tuple[GrantLevel, ...] = tuple(level for level in _POSTURES if level != "none")


@pytest.fixture
async def storage() -> AsyncIterator[InMemoryStorage]:
    storage = InMemoryStorage()
    yield storage
    await storage.close()


async def _replay(world: GrantWorld) -> InMemoryStorage:
    """A fresh mount holding *world*'s rows, written as the system actor."""
    storage = InMemoryStorage()
    entries = [Entry(path=Path(path), content=path, owner_id=owner) for path, owner in sorted(world.owners.items())]
    assert (await storage.write(entries=entries, parents=True, authority=SYSTEM)).success is True
    for row in world.grants:
        if row.principal_id == EVERYONE_NAME:
            result = await storage.posture(path=Path(row.path_prefix), posture=row.level, authority=SYSTEM)
        else:
            result = await storage.grant(
                path=Path(row.path_prefix), principal=row.principal_id, level=row.level, authority=SYSTEM
            )
        assert result.success is True, result.errors
    for member, groups in world.member_of.items():
        for group in sorted(groups):
            assert (await storage.add_member(group=group, member=member, authority=SYSTEM)).success is True
    return storage


def _authority(subjects: tuple[str, ...]) -> Authority:
    principals = {Principal(sub) for sub in subjects}
    if len(principals) == 1:
        return Authority.of(next(iter(principals)))
    return Authority.on_behalf_of(principals, actor=Principal("agent", kind="service"))


def _expected(world: GrantWorld, subjects: tuple[str, ...], level: GrantLevel) -> set[str]:
    """What glob should name: the rows held at *level*, and the directories on the road to one."""
    need = LEVEL_RANK[level]
    admitted = {path for path in PATHS if set_rank(world, subjects, path) >= need}
    road = {d for d in DIRECTORIES if d not in admitted and any(p.startswith(d + "/") for p in admitted)}
    return admitted | road


# ---------------------------------------------------------------------------
# The whole read path against the oracle
# ---------------------------------------------------------------------------


async def test_glob_names_exactly_the_visible_rows_and_their_road() -> None:
    rng = random.Random(58)
    checked = 0
    for _ in range(WORLDS):
        world = random_world(rng)
        storage = await _replay(world)
        try:
            for subjects in SUBJECT_SETS:
                result = await storage.glob(patterns=("/**",), authority=_authority(subjects))
                assert result.success is True, (subjects, result.errors)
                named = {str(o.path) for o in result.observations} - {"/"}
                visible = _expected(world, subjects, "list")
                assert named == visible, (world, subjects)
                # A row held at list, and a road directory, show bare; a readable row shows whole.
                readable = {p for p in PATHS if set_rank(world, subjects, p) >= LEVEL_RANK["read"]}
                bare = {str(o.path): o.populated for o in result.observations if str(o.path) in visible - readable}
                assert all(populated == frozenset({"path", "kind"}) for populated in bare.values()), (world, subjects)
                for road in sorted(visible - readable):
                    row = (await storage.stat(path=Path(road), authority=_authority(subjects))).one()
                    assert row.populated == frozenset({"path", "kind"})
                    checked += 1
        finally:
            await storage.close()
    assert checked > 0


# ---------------------------------------------------------------------------
# The compiled clauses, fanned under a starved budget
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("layout", LAYOUTS, ids=["base", "siblings"])
async def test_the_clauses_admit_exactly_what_the_rights_admit(layout: Layout) -> None:
    rng = random.Random(60)
    for _ in range(WORLDS // 3):
        world = random_world(rng, layout)
        storage = await _replay(world)
        host = storage._host
        entry = host.tables.entry
        try:
            async with host.session_factory() as session:
                judged = select(entry.c.path, entry.c.owner_id, entry.c.everyone_level)
                stored = (await session.execute(judged)).mappings().all()
                for subjects in SUBJECT_SETS:
                    for level in _GRANTABLE:
                        rights = resolve(world.closures(subjects), world.grants, level)
                        wanted = {row["path"] for row in stored if _admits(rights, row)}
                        for parameter_budget in (4, 9, 2_099):
                            clauses = visibility_clauses(entry, rights, host.profile, parameter_budget)
                            if clauses is None:
                                assert wanted == {row["path"] for row in stored}
                                continue
                            got: set[str] = set()
                            for clause in clauses:
                                admitted = await session.execute(select(entry.c.path).where(clause.predicate))
                                got |= set(admitted.scalars())
                            assert got == wanted, (world, subjects, level, parameter_budget)
        finally:
            await storage.close()


@pytest.mark.parametrize("layout", LAYOUTS, ids=["base", "siblings"])
async def test_the_range_join_admits_exactly_what_the_rights_admit(layout: Layout) -> None:
    # Unlike a verb, the join alone has no row check behind it: an extra row
    # here is a row an aggregate would count. The traps sort beside the prefixes.
    rng = random.Random(72)
    traps = [Entry(path=Path(f"{p}.md"), content=p) for p in layout.traps]
    for _ in range(WORLDS // 3):
        world = random_world(rng, layout)
        storage = await _replay(world)
        assert (await storage.write(entries=traps, authority=SYSTEM)).success is True
        host = storage._host
        entry = host.tables.entry
        assert host.profile.range_source is not None
        try:
            async with host.session_factory() as session:
                judged = select(entry.c.path, entry.c.owner_id, entry.c.everyone_level)
                stored = (await session.execute(judged)).mappings().all()
                for subjects in SUBJECT_SETS:
                    for level in _GRANTABLE:
                        rights = resolve(world.closures(subjects), world.grants, level)
                        wanted = {row["path"] for row in stored if _admits(rights, row)}
                        visible = visible_entries(entry, rights.ranges(), rights.need, host.profile)
                        stmt = select(entry.c.path).join(visible, visible.c.entry_id == entry.c.entry_id)
                        got = list((await session.execute(stmt)).scalars())
                        assert sorted(got) == sorted(wanted), (world, subjects, level)
        finally:
            await storage.close()


def test_the_fan_spends_one_bind_per_exact_path_and_two_per_open_range() -> None:
    # bob reads /a less /a/b, and /v1 beside /v10; ann owns rows under /hr.
    spans = union(subtract(cover("/a"), cover("/a/b")), cover_all(("/v1", "/v10")))
    rights = Rights("read", spans, (OwnerArm("ann", ("/hr",)),), ("/a", "/v1", "/v10"))
    found = rights.ranges()
    assert found.arms.points == ("/a", "/a/b0", "/v1", "/v10")
    assert found.arms.opens == (
        ("/a/", "/a/b"),
        ("/a/b", "/a/b/"),
        ("/a/b0", "/a0"),
        ("/v1/", "/v10"),
        ("/v10/", "/v100"),
    )
    entry = build_vfs_tables().entry
    clauses = visibility_clauses(entry, rights, SQLITE, 2_099)
    assert clauses is not None and len(clauses) == 1
    # The everyone level, then four points and five ranges on path, and
    # ann's unit: her id plus /hr's point and range.
    assert clauses[0].binds == 1 + (4 + 2 * 5) + (1 + (1 + 2))
    sql = str(clauses[0].predicate.compile(compile_kwargs={"literal_binds": True}))
    assert "LIKE" not in sql and "\x00" not in sql and "origin_path" not in sql
    assert sql.startswith(f"vfs_entries.everyone_level >= {LEVEL_RANK['read']} OR ")
    assert (
        sql.count("vfs_entries.path = ") == 5
        and sql.count("vfs_entries.path > ") == 6
        and sql.count("vfs_entries.path < ") == 6
    )
    assert "vfs_entries.owner_id = 'ann'" in sql
    # Starved to one bind per clause, every term is its own statement.
    starved = visibility_clauses(entry, rights, SQLITE, 4)
    expected = [1, *[1] * 4, *[2] * 5, 2, 3]
    assert starved is not None and [clause.binds for clause in starved] == expected


@pytest.mark.parametrize("starved", [False, True], ids=["one clause", "fanned"])
async def test_without_a_range_source_the_arms_answer_as_the_join_did(
    monkeypatch: pytest.MonkeyPatch, starved: bool
) -> None:
    # bob reads twenty separate folders. Without a range source his predicate
    # is a literal OR of pieces — one clause, or under a starved bind budget
    # many — and every verb must answer as the range join did.
    storage = InMemoryStorage()
    try:
        folders = [f"/f{n:02}" for n in range(20)]
        entries = [Entry(path=Path(f"{folder}/doc.md"), content=f"lantern {folder}") for folder in folders]
        entries += [Entry(path=Path(f"/hidden/{n}.md"), content="lantern lantern") for n in range(5)]
        assert (await storage.write(entries=entries, parents=True, authority=SYSTEM)).success is True
        assert (await storage.posture(path=Path("/"), posture="none", authority=SYSTEM)).success is True
        for folder in folders:
            assert (await storage.grant(path=Path(folder), principal="bob", level="read", authority=SYSTEM)).success
        assert (await storage.reindex()).success is True
        bob = Authority.of(Principal("bob"))
        joined = await _answers(storage, bob)
        host = storage._host
        unjoined = replace(host.profile, range_source=None)
        monkeypatch.setattr(EngineHost, "profile", property(lambda _self: unjoined))
        if starved:
            monkeypatch.setattr(EngineHost, "parameter_budget", property(lambda _self: 56))
        rights = (await _resolution(storage, bob)).at("read")
        clauses = visibility_clauses(host.tables.entry, rights, host.profile, host.parameter_budget) or []
        assert (len(clauses) > 1) is starved
        assert await _answers(storage, bob) == joined
    finally:
        await storage.close()


async def test_a_partial_read_issues_the_profiles_range_settings_and_derived_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The settings run once per partial read, in its transaction; the hint
    # rides the visible-corpus count. Both spelled so SQLite accepts them.
    storage = InMemoryStorage()
    try:
        entries = [Entry(path=Path(f"/d/{n}.md"), content="lantern") for n in range(3)]
        assert (await storage.write(entries=entries, parents=True, authority=SYSTEM)).success is True
        assert (await storage.posture(path=Path("/"), posture="none", authority=SYSTEM)).success is True
        assert (await storage.grant(path=Path("/d"), principal="bob", level="read", authority=SYSTEM)).success
        assert (await storage.reindex()).success is True
        host = storage._host
        hints = host.profile.range_hints._replace(derived="/* {visible} {table} {index} */")
        pinned = replace(host.profile, range_settings=("PRAGMA query_only = 0",), range_hints=hints)
        monkeypatch.setattr(EngineHost, "profile", property(lambda _self: pinned))
        bob = Authority.of(Principal("bob"))
        gleaned = await storage.glean(query="lantern", authority=bob)
        assert gleaned.success is True and len(gleaned.observations) == 3
        assert {str(o.path) for o in (await storage.tree(path=Path("/"), authority=bob)).observations} >= {"/d"}
    finally:
        await storage.close()


# ---------------------------------------------------------------------------
# The everyone level on every row
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("layout", LAYOUTS, ids=["base", "siblings"])
async def test_every_row_carries_the_oracles_everyone_level_after_every_mutation(layout: Layout) -> None:
    # Every mint, transfer and posture change must leave each live row's
    # label equal to what the oracle computes from the posture rows alone.
    rng = random.Random(61)
    for _ in range(WORLDS // 3):
        world = random_world(rng, layout)
        storage = await _replay(world)
        try:
            await _assert_labels(storage, world)
            first, second = layout.directories[0], layout.directories[1]
            copied = await storage.copy(operations=[ResolvedPair(Path(first), Path("/c1"))], authority=SYSTEM)
            assert copied.success is True, copied.errors
            await _assert_labels(storage, world)
            moved = await storage.move(operations=[ResolvedPair(Path(second), Path("/m1"))], authority=SYSTEM)
            assert moved.success is True, moved.errors
            await _assert_labels(storage, world)
            assert (await storage.mkdir(path=Path("/c1/deep/er"), parents=True, authority=SYSTEM)).success is True
            await _assert_labels(storage, world)
            for _change in range(3):
                target = rng.choice(("/", "/c1", "/m1", "/c1/deep", *layout.paths))
                level = rng.choice(_POSTURES)
                changed = await storage.posture(path=Path(target), posture=level, authority=SYSTEM)
                assert changed.success is True, changed.errors
                assert set((changed.model_extra or {})["relabel"]) == {"rows", "statements", "transactions"}
                _set_posture(world, target, level)
                await _assert_labels(storage, world)
            assert (await storage.delete(path=Path("/m1"), authority=SYSTEM)).success is True
            await _assert_labels(storage, world)
            # A posture change while /m1 is deleted reaches its rows where they sit.
            target = rng.choice(("/", "/m1", *layout.paths))
            level = rng.choice(_POSTURES)
            assert (await storage.posture(path=Path(target), posture=level, authority=SYSTEM)).success
            _set_posture(world, target, level)
            await _assert_labels(storage, world)
            assert (await storage.restore(path=Path("/m1"), authority=SYSTEM)).success is True
            await _assert_labels(storage, world)
        finally:
            await storage.close()


@pytest.mark.parametrize("layout", LAYOUTS, ids=["base", "siblings"])
async def test_the_trash_view_shows_each_caller_its_own_deleted_rows_against_the_oracle(layout: Layout) -> None:
    # A directory is deleted as the system actor. For every subject set the
    # trash view must name exactly the rows the oracle admits at their own
    # paths (plus the directories on the road to one), and restore and sweep
    # must be allowed exactly when the oracle writes every row of the subtree.
    rng = random.Random(63)
    for _ in range(WORLDS // 3):
        world = random_world(rng, layout)
        storage = await _replay(world)
        try:
            root = rng.choice(layout.directories)
            subtree = [p for p in layout.paths if p == root or p.startswith(root + "/")]
            for subjects in SUBJECT_SETS:
                assert (await storage.delete(path=Path(root), authority=SYSTEM)).success is True
                authority = _authority(subjects)
                globbed = await storage.glob(patterns=("/.vfs/trash/**",), authority=authority)
                assert globbed.success is True, (subjects, globbed.errors)
                named = {str(o.path) for o in globbed.observations}
                shown = _expected_trash(world, subjects, subtree, layout)
                assert named == shown, (world.grants, subjects, root)
                writable = all(set_rank(world, subjects, t) >= LEVEL_RANK["read_write"] for t in subtree)
                restored = await storage.restore(path=Path(root), authority=authority)
                if writable:
                    assert restored.success is True, (subjects, restored.errors)
                else:
                    # A deleted root the caller sees, or walks through to a row it sees, is denied; else absent.
                    kind = ErrorKind.permission_denied if root in shown else ErrorKind.not_found
                    assert _kind(restored) == kind, (world.grants, subjects, root)
                    swept = await storage.sweep(path=Path(root), authority=authority)
                    assert _kind(swept) == kind, (world.grants, subjects, root, shown, swept.errors)
                    assert (await storage.stat(path=Path(f"/.vfs/trash{root}"), authority=SYSTEM)).success is True
                    assert (await storage.restore(path=Path(root), authority=SYSTEM)).success is True
                await _assert_labels(storage, world)
        finally:
            await storage.close()


async def test_reads_match_the_oracle_while_a_posture_relabel_is_held_midway() -> None:
    # A posture change is written and marked in flight, then held before
    # its labels are rewritten. Every read must already see the new
    # posture — through the in-flight compile — and still match the
    # oracle, whose labels the row store has not yet caught up to.
    rng = random.Random(77)
    for _ in range(WORLDS):
        world = random_world(rng)
        storage = await _replay(world)
        try:
            target = rng.choice(("/", *DIRECTORIES))
            level = rng.choice(_POSTURES)
            await _hold_posture(storage, target, level)
            _set_posture(world, target, level)
            for subjects in SUBJECT_SETS:
                result = await storage.glob(patterns=("/**",), authority=_authority(subjects))
                assert result.success is True, (subjects, result.errors)
                named = {str(o.path) for o in result.observations} - {"/"}
                assert named == _expected(world, subjects, "list"), (world.grants, target, level, subjects)
            await _finish_relabels(storage)
            await _assert_labels(storage, world)
        finally:
            await storage.close()


def test_the_clause_fan_fences_a_hole_out_of_the_everyone_leg() -> None:
    # Without a range source the fan carries the holes as literal negations:
    # the everyone unit becomes the level on each piece of the mount outside
    # the hole, so a stale label inside it never admits through this leg.
    entry = build_vfs_tables().entry
    rows = [GrantRow("*", "/", "none"), GrantRow("*", "/h", "none"), GrantRow("ann", "/g", "read")]
    rights = resolve({"ann": frozenset()}, rows, "read", pending={"/h"})
    assert rights.holes == cover("/h")
    clauses = visibility_clauses(entry, rights, replace(SQLITE, range_source=None), 2_099)
    assert clauses is not None and len(clauses) == 1
    sql = str(clauses[0].predicate.compile(compile_kwargs={"literal_binds": True}))
    # The everyone level rides each piece outside the hole, never the hole itself.
    assert f"everyone_level >= {LEVEL_RANK['read']}" in sql and "'/h'" in sql and "'/h/'" in sql
    assert "\x00" not in sql


async def test_a_failed_relabel_chunk_returns_the_posture_with_its_grant(tmp_path, monkeypatch) -> None:
    # The posture row commits; a later relabel chunk then fails. The verb
    # returns the failure with the grant it wrote, and the mark stands for
    # the next call to finish.
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp_path}/fail.sqlite", posture="read_write")
    try:
        entries = [Entry(path=Path(f"/d/{n}.md"), content="x") for n in range(3)]
        assert (await storage.write(entries=entries, parents=True, authority=SYSTEM)).success is True

        async def boom(self, session):
            raise OperationalError("relabel", {}, Exception("disk full"))

        monkeypatch.setattr(backend_module.Relabeller, "step", boom)
        result = await storage.posture(path=Path("/d"), posture="none", authority=SYSTEM)
        assert result.success is False
        assert _granted(result)[0]["path_prefix"] == "/d"
        host = storage._host
        async with host.session_factory() as session:
            pending = (await session.execute(select(host.tables.relabels.c.path_prefix))).scalars().all()
        assert pending == ["/d"]
    finally:
        await storage.close()


@pytest.mark.parametrize("op", ["grant", "posture"])
async def test_an_admin_write_decides_after_it_takes_the_lock(tmp_path, op: Literal["grant", "posture"]) -> None:
    # The lock-before-decide pin. A rival revoke of ann's right lands in
    # the gap before the admin write takes the lock — staged on the
    # verb's own writer session, the repo's SQLite race idiom, since a
    # genuine second writer cannot coexist under SQLite's write lock. The
    # write bumps the revision, then resolves ann's rights, so it reads
    # the revoke and refuses — before the fix it decided first and lost it.
    url = f"sqlite+aiosqlite:///{tmp_path}/race.sqlite"
    storage = DatabaseStorage(url=url, posture="none")
    try:
        assert (await storage.mkdir(path=Path("/x"), authority=SYSTEM)).success is True
        assert (await storage.grant(path=Path("/x"), principal="ann", level="read_write", authority=SYSTEM)).success
        host = storage._host
        grants, ann = host.tables.grants, Authority.of(Principal("ann"))
        refused = await _locked_admin_write(host, op, ann, revoke_in_gap=grants)
        assert _kind(refused) in (ErrorKind.permission_denied, ErrorKind.not_found)
        rows = {(g["principal_id"], g["path_prefix"]) for g in _granted(await storage.grants(path=Path("/x")))}
        assert ("bob", "/x") not in rows and ("ann", "/x") in rows
    finally:
        await storage.close()


# ---------------------------------------------------------------------------
# The rights cache and the resolution budget
# ---------------------------------------------------------------------------


async def test_a_grant_write_invalidates_its_grantees_cached_resolution(storage: InMemoryStorage) -> None:
    ann = Authority.of(Principal("ann"))
    await storage.write(entries=[Entry(path=Path("/d/f.md"), content="x")], parents=True, authority=SYSTEM)
    assert (await storage.posture(path=Path("/"), posture="none", authority=SYSTEM)).success is True
    assert (await storage.read(path=Path("/d/f.md"), authority=ann)).success is False
    assert (await storage.grant(path=Path("/d"), principal="ann", level="read", authority=SYSTEM)).success is True
    assert (await storage.read(path=Path("/d/f.md"), authority=ann)).success is True


async def test_a_grant_to_one_user_retires_that_users_compile_and_nobody_elses(
    storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Three callers cached by a read each; a grant to ann recompiles ann
    # on her next read and leaves bob's and carol's compiles serving.
    compiled = _recompiles(monkeypatch)
    callers = await _three_cached_callers(storage)
    assert compiled == [("ann",), ("bob",), ("carol",)]
    assert (await storage.grant(path=Path("/d"), principal="ann", level="read", authority=SYSTEM)).success is True
    for who in callers:
        assert (await storage.read(path=Path("/d/f.md"), authority=who)).success is (who is callers[0])
    assert compiled[3:] == [("ann",)]
    assert (await storage.revoke(path=Path("/d"), principal="ann", authority=SYSTEM)).success is True
    for who in callers:
        assert (await storage.read(path=Path("/d/f.md"), authority=who)).success is False
    assert compiled[4:] == [("ann",)]


async def test_a_grant_to_a_group_retires_its_members_only(
    storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    compiled = _recompiles(monkeypatch)
    assert (await storage.add_member(group="group:g", member="ann", authority=SYSTEM)).success is True
    assert (await storage.add_member(group="group:g", member="bob", authority=SYSTEM)).success is True
    callers = await _three_cached_callers(storage)
    granted = await storage.grant(path=Path("/d"), principal="group:g", level="read", authority=SYSTEM)
    assert granted.success is True
    for who in callers:
        assert (await storage.read(path=Path("/d/f.md"), authority=who)).success is (who is not callers[2])
    assert compiled[3:] == [("ann",), ("bob",)]


async def test_a_membership_change_retires_the_member_and_not_its_fellow_members(
    storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    # ann is in group:g already; adding bob changes bob's closure alone,
    # so ann's compile keeps serving — a nested member would be retired
    # through its own stamp the same way.
    compiled = _recompiles(monkeypatch)
    assert (await storage.add_member(group="group:g", member="ann", authority=SYSTEM)).success is True
    assert (await storage.grant(path=Path("/d"), principal="group:g", level="read", authority=SYSTEM)).success is True
    callers = await _three_cached_callers(storage)
    assert (await storage.add_member(group="group:g", member="bob", authority=SYSTEM)).success is True
    for who in callers:
        assert (await storage.read(path=Path("/d/f.md"), authority=who)).success is (who is not callers[2])
    assert compiled[3:] == [("bob",)]
    assert (await storage.remove_member(group="group:g", member="bob", authority=SYSTEM)).success is True
    for who in callers:
        assert (await storage.read(path=Path("/d/f.md"), authority=who)).success is (who is callers[0])
    assert compiled[4:] == [("bob",)]


async def test_a_posture_change_retires_no_compile_but_its_window_and_its_settling_do(
    storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    compiled = _recompiles(monkeypatch)
    callers = await _three_cached_callers(storage)
    # A posture change that has settled by the time anyone reads: the
    # labels decide, and every compile made before it serves again.
    assert (await storage.posture(path=Path("/d"), posture="read", authority=SYSTEM)).success is True
    for who in callers:
        assert (await storage.read(path=Path("/d/f.md"), authority=who)).success is True
    assert compiled[3:] == []
    # A posture row held in flight: every reader compiles the window once.
    await _hold_posture(storage, "/d", "none")
    for who in callers:
        assert (await storage.read(path=Path("/d/f.md"), authority=who)).success is False
        assert (await storage.read(path=Path("/d/f.md"), authority=who)).success is False
    assert compiled[3:] == [("ann",), ("bob",), ("carol",)]
    # The relabel settles: the window's compiles are retired, one more compile each.
    await _finish_relabels(storage)
    for who in callers:
        assert (await storage.read(path=Path("/d/f.md"), authority=who)).success is False
        assert (await storage.read(path=Path("/d/f.md"), authority=who)).success is False
    assert compiled[6:] == [("ann",), ("bob",), ("carol",)]


async def test_a_posture_change_retires_the_anonymous_compile(
    storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Anonymous holds the posture alone, so the root posture it carries
    # must follow every posture write — through the everyone stamp.
    compiled = _recompiles(monkeypatch)
    anon = Authority.anonymous()
    await storage.write(entries=[Entry(path=Path("/d/f.md"), content="x")], parents=True, authority=SYSTEM)
    assert (await storage.read(path=Path("/d/f.md"), authority=anon)).success is True
    assert (await storage.read(path=Path("/d/f.md"), authority=anon)).success is True
    assert compiled == [(ANONYMOUS_NAME,)]
    assert (await storage.posture(path=Path("/"), posture="none", authority=SYSTEM)).success is True
    refused = await storage.read(path=Path("/d/f.md"), authority=anon)
    assert _kind(refused) == ErrorKind.unauthenticated
    assert compiled == [(ANONYMOUS_NAME,), (ANONYMOUS_NAME,)]


async def test_a_cached_caller_costs_its_stamps_and_the_marks_per_call(storage: InMemoryStorage) -> None:
    # The hit path: one read of the subjects' and groups' stamps, one of
    # the relabel marks, then the row read itself — never the closures.
    ann = Authority.of(Principal("ann"))
    await storage.write(entries=[Entry(path=Path("/d/f.md"), content="x")], parents=True, authority=SYSTEM)
    assert (await storage.add_member(group="group:g", member="ann", authority=SYSTEM)).success is True
    assert (await storage.stat(path=Path("/d/f.md"), authority=ann)).success is True
    statements: list[str] = []

    @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
    def record(conn, cursor, statement, parameters, context, executemany) -> None:
        statements.append(statement)

    assert (await storage.stat(path=Path("/d/f.md"), authority=ann)).success is True
    selects = [s for s in statements if s.startswith("SELECT")]
    tables = storage._host.tables
    assert len(selects) == 3, selects
    assert tables.principal_revisions.name in selects[0] and tables.relabels.name in selects[1]
    assert tables.memberships.name not in "".join(selects)


async def test_a_compile_an_admin_write_landed_inside_is_answered_but_not_remembered(
    storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The mount revision is read first and last around a miss; when the
    # two disagree an admin write committed between the compile's
    # statements, so the compile serves this call and the next one reads
    # settled state instead of a torn entry.
    ann = Authority.of(Principal("ann"))
    await storage.write(entries=[Entry(path=Path("/d/f.md"), content="x")], parents=True, authority=SYSTEM)
    host = storage._host
    revisions = iter(range(100))
    real = rights_module.read_revision

    async def drifting(session: Any, tables: Any) -> int:
        return await real(session, tables) + next(revisions)

    monkeypatch.setattr(rights_module, "read_revision", drifting)
    cache = RightsCache()
    async with host.session_factory() as session:
        first = await resolve_authority(session, host.tables, host.profile, host.membership_budget, ann, cache)
        assert isinstance(first, Resolution) and cache.ids(ann.subject_names) is None
    monkeypatch.setattr(rights_module, "read_revision", real)
    async with host.session_factory() as session:
        second = await resolve_authority(session, host.tables, host.profile, host.membership_budget, ann, cache)
        assert second is not first and cache.ids(ann.subject_names) == ("ann",)
        third = await resolve_authority(session, host.tables, host.profile, host.membership_budget, ann, cache)
        assert third is second


def test_the_rights_cache_evicts_its_least_recent_entry() -> None:
    cache = RightsCache(entries=2)
    value = _nothing()
    cache.put(RightsKey(("a",), 1, ()), ["a"], value)
    cache.put(RightsKey(("b",), 1, ()), ["b"], value)
    assert cache.get(RightsKey(("a",), 1, ())) is value
    cache.put(RightsKey(("c",), 1, ()), ["c"], value)
    assert cache.get(RightsKey(("b",), 1, ())) is None
    assert cache.get(RightsKey(("a",), 1, ())) is value
    assert cache.ids(("a",)) == ("a",) and cache.ids(("b",)) is None
    # A newer stamp, or a mark standing, is another key: the held entry is dropped, not served.
    assert cache.get(RightsKey(("a",), 2, ())) is None
    assert cache.ids(("a",)) is None
    cache.put(RightsKey(("c",), 1, (Mark("/x", 1),)), ["c"], value)
    assert cache.get(RightsKey(("c",), 1, ())) is None


def test_the_rights_cache_evicts_by_bytes_past_its_budget() -> None:
    light = _nothing()
    heavy = _resolution_over([f"/p{n:05d}" for n in range(200)])
    assert 4 * weight(light) < weight(heavy)
    cache = RightsCache(entries=100, budget=2 * weight(heavy) + weight(light))
    cache.put(RightsKey(("a",), 1, ()), ["a"], heavy)
    cache.put(RightsKey(("b",), 1, ()), ["b"], light)
    cache.put(RightsKey(("c",), 1, ()), ["c"], heavy)
    assert cache.held == 2 * weight(heavy) + weight(light)
    assert cache.get(RightsKey(("a",), 1, ())) is heavy
    cache.put(RightsKey(("d",), 1, ()), ["d"], heavy)
    assert cache.ids(("b",)) is None and cache.ids(("c",)) is None
    assert cache.ids(("a",)) == ("a",) and cache.ids(("d",)) == ("d",)
    assert cache.held == 2 * weight(heavy)
    # An entry heavier than the whole budget is held alone: the newest always stays.
    small = RightsCache(entries=100, budget=1)
    small.put(RightsKey(("a",), 1, ()), ["a"], heavy)
    small.put(RightsKey(("b",), 1, ()), ["b"], light)
    assert small.ids(("a",)) is None and small.ids(("b",)) == ("b",) and small.held == weight(light)


def test_weight_counts_the_pieces_a_view_will_hold() -> None:
    narrow = _resolution_over(["/a"])
    wide = _resolution_over([f"/a/{n:04d}" for n in range(50)])
    assert weight(narrow) < weight(wide)
    assert weight(wide) == weight(wide)


async def test_nesting_past_the_cap_on_read_is_an_authority_budget_refusal(storage: InMemoryStorage) -> None:
    # Rows planted beneath the write-side check: the read walk refuses
    # rather than truncating a closure it cannot finish.
    assert (await storage.first_touch()).success is True
    host = storage._host
    chain = ["ann", *(f"group:g{n}" for n in range(12))]
    async with host.session_factory() as session, session.begin():
        await session.execute(
            host.tables.memberships.insert(),
            [
                {"principal_id": inner, "group_id": outer, "granted_by": "system", "granted_at": datetime.now(UTC)}
                for inner, outer in pairwise(chain)
            ],
        )
    result = await storage.read(path=Path("/"), authority=Authority.of(Principal("ann")))
    assert result.errors[0].kind == ErrorKind.authority_budget


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _answers(storage: InMemoryStorage, authority: Authority) -> list[object]:
    """What every partial read verb answers *authority*, in a comparable shape."""
    listed = await storage.ls(path=Path("/"), authority=authority)
    globbed = await storage.glob(patterns=("/**",), authority=authority)
    walked = await storage.tree(path=Path("/"), authority=authority)
    grepped = await storage.grep(pattern="lantern", output_mode="files", allow_scan=True, authority=authority)
    gleaned = await storage.glean(query="lantern", limit=30, authority=authority)
    read = await storage.read(path=Path("/f03/doc.md"), authority=authority)
    hidden = await storage.stat(path=Path("/hidden/0.md"), authority=authority)
    return [
        sorted(str(o.path) for o in listed.observations),
        sorted(str(o.path) for o in globbed.observations),
        sorted(str(o.path) for o in walked.observations),
        sorted(str(o.path) for o in grepped.observations),
        [(str(o.path), o.score) for o in gleaned.observations],
        read.one().content,
        [error.kind for error in hidden.errors],
    ]


def _kind(result: Result) -> ErrorKind | str | None:
    assert result.success is False, result
    return result.errors[0].kind


def _admits(rights: Rights, row: RowMapping) -> bool:
    return rights.admits(row["path"], row["owner_id"], row["everyone_level"])


def _granted(result: object) -> list[dict[str, object]]:
    rows = (getattr(result, "model_extra", None) or {}).get("grants")
    assert isinstance(rows, list), result
    return rows


async def _hold_posture(storage: InMemoryStorage, path: str, level: GrantLevel) -> None:
    """Write the ``*`` row at *path* and mark its relabel pending, without rewriting a label.

    The revision bumps, so the in-flight compile replaces any cached one;
    the labels beneath stay stale until a :class:`Relabeller` runs.
    """
    host = storage._host
    grants = host.tables.grants
    async with host.session_factory() as session, session.begin():
        revision = await bump_revision(session, host.tables)
        key = and_(grants.c.principal_id == EVERYONE_NAME, grants.c.path_prefix == path)
        updated = cast(
            "CursorResult[Any]", await session.execute(update(grants).where(key).values(level=level, revision=revision))
        )
        if updated.rowcount == 0:
            await session.execute(
                insert(grants).values(
                    principal_id=EVERYONE_NAME,
                    path_prefix=path,
                    level=level,
                    granted_by="system",
                    granted_at=datetime.now(UTC),
                    revision=revision,
                )
            )
        await mark_relabel(session, host.tables, path, revision)


async def _finish_relabels(storage: InMemoryStorage) -> None:
    """Run every pending relabel to its end, one chunk per transaction."""
    host = storage._host
    relabeller = Relabeller(host.tables, host.profile, host.membership_budget)
    while True:
        async with host.session_factory() as session, session.begin():
            if await relabeller.step(session) is None:
                return


async def _locked_admin_write(
    host: EngineHost, op: Literal["grant", "posture"], authority: Authority, *, revoke_in_gap: object
) -> Result:
    """One admin write in the backend's order, a revoke of ann staged in the gap before the lock.

    Mirrors ``_grant_write``: take the admin lock, resolve the caller
    uncached under it, build the gate, then write. The staged revoke is
    committed on the verb's own writer session before the lock — SQLite
    permits no second writer — so the resolution under the lock reads it.
    """
    grants = cast("Any", revoke_in_gap)
    tables, profile, budget = host.tables, host.profile, host.membership_budget
    async with host.session_factory() as session:
        await session.connection(execution_options={"vfs_writer": True})
        await session.execute(delete(grants).where(grants.c.principal_id == "ann", grants.c.path_prefix == "/x"))
        revision = await bump_revision(session, tables)
        resolution = await resolve_authority(session, tables, profile, budget, authority, None)
        assert isinstance(resolution, Resolution)
        gate = WriteGate(
            resolution, VERB_RUNGS[op], tables, profile, budget, host.parameter_budget, authority=authority
        )
        if op == "grant":
            result = await grant_rows(
                session,
                tables,
                profile,
                budget,
                gate,
                path=Path("/x"),
                principal="bob",
                level="read",
                authority=authority,
                revision=revision,
            )
        else:
            result = await set_posture(
                session,
                tables,
                profile,
                budget,
                gate,
                path=Path("/x"),
                posture="read_write",
                authority=authority,
                revision=revision,
            )
        await session.rollback()
        return result


async def _assert_labels(storage: InMemoryStorage, world: GrantWorld) -> None:
    """Every row's stored label equals the oracle's everyone level at its path — deleted rows included."""
    entry = storage._host.tables.entry
    async with storage._host.session_factory() as session:
        stmt = select(entry.c.path, entry.c.everyone_level)
        stored = (await session.execute(stmt)).all()
    assert stored
    wrong = {row.path: (row.everyone_level, everyone_rank(world, row.path)) for row in stored}
    assert {p: pair for p, pair in wrong.items() if pair[0] != pair[1]} == {}, world.grants


def _expected_trash(world: GrantWorld, subjects: tuple[str, ...], subtree: list[str], layout: Layout) -> set[str]:
    """What a glob of the trash view should name: the deleted rows the caller may name and the road to one."""
    admitted = {t for t in subtree if set_rank(world, subjects, t) >= LEVEL_RANK["list"]}
    directories = {t for t in subtree if t in layout.directories}
    road = {d for d in directories if d not in admitted and any(a.startswith(d + "/") for a in admitted)}
    return admitted | road


def _set_posture(world: GrantWorld, path: str, level: GrantLevel) -> None:
    world.grants = [row for row in world.grants if not (row.principal_id == EVERYONE_NAME and row.path_prefix == path)]
    world.grants.append(GrantRow(EVERYONE_NAME, path, level))


def _recompiles(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, ...]]:
    """The subject sets the resolver compiles from here on, in order — one entry per cache miss."""
    compiled: list[tuple[str, ...]] = []
    real = rights_module.resolve

    def counting(
        closures: Mapping[str, frozenset[str]], rows: Sequence[GrantRow], level: GrantLevel, **kw: Any
    ) -> Rights:
        # The read_write compile is never aliased, so it is the one call per miss.
        if level == "read_write":
            compiled.append(tuple(sorted(closures)))
        return real(closures, rows, level, **kw)

    monkeypatch.setattr(rights_module, "resolve", counting)
    return compiled


async def _three_cached_callers(storage: InMemoryStorage) -> tuple[Authority, Authority, Authority]:
    """ann, bob and carol, each cached by one read of a private mount's ``/d/f.md``."""
    await storage.write(entries=[Entry(path=Path("/d/f.md"), content="x")], parents=True, authority=SYSTEM)
    assert (await storage.posture(path=Path("/"), posture="none", authority=SYSTEM)).success is True
    callers = (Authority.of(Principal("ann")), Authority.of(Principal("bob")), Authority.of(Principal("carol")))
    for who in callers:
        await storage.read(path=Path("/d/f.md"), authority=who)
    return callers


def _resolution_over(prefixes: list[str]) -> Resolution:
    rows = [GrantRow("a", prefix, "read_write") for prefix in prefixes]
    return Resolution.compile({"a": frozenset()}, rows, owner_floor=True, pending=())


def _nothing() -> Resolution:
    return Resolution({level: Rights.nothing(level) for level in _GRANTABLE})


async def _resolution(storage: InMemoryStorage, authority: Authority) -> Resolution:
    host = storage._host
    async with host.session_factory() as session:
        resolved = await resolve_authority(
            session, host.tables, host.profile, host.membership_budget, authority, RightsCache()
        )
    assert isinstance(resolved, Resolution)
    return resolved
