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
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from tests.support.grant_worlds import DIRECTORIES, FILES, PATHS, SUBJECT_SETS, random_world
from tests.support.oracles.grants import GrantWorld, set_rank
from vfs.authority import EVERYONE_NAME, Authority, Principal
from vfs.models import Entry
from vfs.paths import Path
from vfs.results import VFSErrorKind
from vfs.storage.backends.database.engine import EngineHost
from vfs.storage.backends.database.ranges import visible_entries
from vfs.storage.backends.database.rights import Resolution, RightsCache, resolve_authority, visibility_clauses
from vfs.storage.backends.memory import InMemoryStorage
from vfs.storage.grants import LEVEL_RANK, POSTURE_LEVELS, GrantLevel, Posture, Rights, resolve

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

WORLDS = 30
SYSTEM = Authority.system()
_POSTURE_OF: dict[str, Posture] = {"read_write": "open", "read": "shared", "none": "private"}


@pytest.fixture
async def storage() -> AsyncIterator[InMemoryStorage]:
    storage = InMemoryStorage()
    yield storage
    await storage.close()


def test_the_posture_table_inverts_the_stored_levels() -> None:
    assert {POSTURE_LEVELS[posture]: posture for posture in _POSTURE_OF.values()} == _POSTURE_OF


async def _replay(world: GrantWorld) -> InMemoryStorage:
    """A fresh mount holding *world*'s rows, written as the system actor."""
    storage = InMemoryStorage()
    entries = [Entry(path=Path(path), content=path, owner_id=world.owners[path]) for path in FILES]
    assert (await storage.write(entries=entries, parents=True, authority=SYSTEM)).success is True
    for row in world.grants:
        if row.principal_id == EVERYONE_NAME:
            result = await storage.posture(path=Path(row.path_prefix), posture=_POSTURE_OF[row.level], authority=SYSTEM)
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
    """What glob should name: the admitted rows, and the directories on the road to one."""
    need = LEVEL_RANK[level]
    admitted = {path for path in PATHS if set_rank(world, subjects, path) >= need}
    road = {d for d in DIRECTORIES if d not in admitted and any(p.startswith(d + "/") for p in admitted)}
    return admitted | road


# ---------------------------------------------------------------------------
# The whole read path against the oracle
# ---------------------------------------------------------------------------


async def test_glob_names_exactly_the_visible_rows_and_their_road() -> None:
    rng = random.Random(58)
    for _ in range(WORLDS):
        world = random_world(rng)
        storage = await _replay(world)
        try:
            for subjects in SUBJECT_SETS:
                result = await storage.glob(patterns=("/**",), authority=_authority(subjects))
                assert result.success is True, (subjects, result.errors)
                named = {str(o.path) for o in result.observations} - {"/"}
                assert named == _expected(world, subjects, "read"), (world, subjects)
        finally:
            await storage.close()


async def test_a_road_row_carries_its_name_and_kind_only() -> None:
    rng = random.Random(59)
    checked = 0
    for _ in range(WORLDS):
        world = random_world(rng)
        storage = await _replay(world)
        try:
            for subjects in SUBJECT_SETS:
                visible = _expected(world, subjects, "read")
                admitted = {p for p in PATHS if set_rank(world, subjects, p) >= LEVEL_RANK["read"]}
                for road in sorted(visible - admitted):
                    row = (await storage.stat(path=Path(road), authority=_authority(subjects))).one()
                    assert row.kind == "directory" and row.populated == frozenset({"path", "kind"})
                    checked += 1
        finally:
            await storage.close()
    assert checked > 0


# ---------------------------------------------------------------------------
# The compiled clauses, fanned under a starved budget
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("parameter_budget", [4, 9, 2_099])
async def test_the_clauses_admit_exactly_what_the_rights_admit(parameter_budget: int) -> None:
    rng = random.Random(60 + parameter_budget)
    for _ in range(WORLDS // 3):
        world = random_world(rng)
        storage = await _replay(world)
        host = storage._host
        entry = host.tables.entry
        try:
            async with host.session_factory() as session:
                stored = (await session.execute(select(entry.c.path, entry.c.owner_id))).mappings().all()
                for subjects in SUBJECT_SETS:
                    for level in ("read", "read_write"):
                        rights = resolve(world.closures(subjects), world.grants, level)
                        clauses = visibility_clauses(entry, rights, host.profile, parameter_budget)
                        wanted = {row["path"] for row in stored if rights.admits(row["path"], row["owner_id"])}
                        if clauses is None:
                            assert wanted == {row["path"] for row in stored}
                            continue
                        got: set[str] = set()
                        for clause in clauses:
                            got |= set((await session.execute(select(entry.c.path).where(clause.predicate))).scalars())
                        assert got == wanted, (world, subjects, level, parameter_budget)
        finally:
            await storage.close()


async def test_the_range_join_admits_exactly_what_the_rights_admit() -> None:
    # Unlike a verb, the join alone has no row check behind it: an extra row
    # here is a row an aggregate would count. The traps sort beside the prefixes.
    rng = random.Random(72)
    traps = [Entry(path=Path(p), content=p) for p in ("/a-b.md", "/a0.md", "/a/b-c.md", "/a/b0.md", "/e0.md")]
    for _ in range(WORLDS // 3):
        world = random_world(rng)
        storage = await _replay(world)
        assert (await storage.write(entries=traps, authority=SYSTEM)).success is True
        host = storage._host
        entry = host.tables.entry
        assert host.profile.range_source is not None
        try:
            async with host.session_factory() as session:
                stored = (await session.execute(select(entry.c.path, entry.c.owner_id))).mappings().all()
                for subjects in SUBJECT_SETS:
                    for level in ("read", "read_write"):
                        rights = resolve(world.closures(subjects), world.grants, level)
                        wanted = {row["path"] for row in stored if rights.admits(row["path"], row["owner_id"])}
                        visible = visible_entries(entry, rights.ranges(), host.profile.range_source)
                        stmt = select(entry.c.path).join(visible, visible.c.entry_id == entry.c.entry_id)
                        got = list((await session.execute(stmt)).scalars())
                        assert sorted(got) == sorted(wanted), (world, subjects, level)
        finally:
            await storage.close()


@pytest.mark.parametrize("starved", [False, True], ids=["one clause", "fanned"])
async def test_without_a_range_source_the_arms_answer_as_the_join_did(
    monkeypatch: pytest.MonkeyPatch, starved: bool
) -> None:
    # bob reads twenty separate folders. Without a range source his predicate
    # is literal arms — one clause, or under a starved bind budget many — and
    # every verb must answer as the range join did.
    storage = InMemoryStorage()
    try:
        folders = [f"/f{n:02}" for n in range(20)]
        entries = [Entry(path=Path(f"{folder}/doc.md"), content=f"lantern {folder}") for folder in folders]
        entries += [Entry(path=Path(f"/hidden/{n}.md"), content="lantern lantern") for n in range(5)]
        assert (await storage.write(entries=entries, parents=True, authority=SYSTEM)).success is True
        assert (await storage.posture(path=Path("/"), posture="private", authority=SYSTEM)).success is True
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
        rights = (await _resolution(storage, bob)).read
        clauses = visibility_clauses(host.tables.entry, rights, host.profile, host.parameter_budget) or []
        assert (len(clauses) > 1) is starved
        assert await _answers(storage, bob) == joined
    finally:
        await storage.close()


# ---------------------------------------------------------------------------
# The rights cache and the resolution budget
# ---------------------------------------------------------------------------


async def test_a_grant_write_invalidates_every_cached_resolution(storage: InMemoryStorage) -> None:
    ann = Authority.of(Principal("ann"))
    await storage.write(entries=[Entry(path=Path("/d/f.md"), content="x")], parents=True, authority=SYSTEM)
    assert (await storage.posture(path=Path("/"), posture="private", authority=SYSTEM)).success is True
    assert (await storage.read(path=Path("/d/f.md"), authority=ann)).success is False
    assert (await storage.grant(path=Path("/d"), principal="ann", level="read", authority=SYSTEM)).success is True
    assert (await storage.read(path=Path("/d/f.md"), authority=ann)).success is True


def test_the_rights_cache_evicts_its_least_recent_entry() -> None:
    cache = RightsCache(size=2)
    value = Resolution(Rights.nothing("read"), Rights.nothing("read_write"), "none", 1)
    cache.put((("a",), 1), value)
    cache.put((("b",), 1), value)
    assert cache.get((("a",), 1)) is value
    cache.put((("c",), 1), value)
    assert cache.get((("b",), 1)) is None
    assert cache.get((("a",), 1)) is value
    assert cache.get((("a",), 2)) is None


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
    assert result.errors[0].kind == VFSErrorKind.authority_budget


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


async def _resolution(storage: InMemoryStorage, authority: Authority) -> Resolution:
    host = storage._host
    async with host.session_factory() as session:
        resolved = await resolve_authority(
            session, host.tables, host.profile, host.membership_budget, authority, RightsCache()
        )
    assert isinstance(resolved, Resolution)
    return resolved
