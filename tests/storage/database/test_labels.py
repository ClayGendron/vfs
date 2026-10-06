"""The everyone level on the row — the labeller, the relabel's spellings, and the rebuild.

Row-exact parity after every mutation is ``test_rights.py``'s random-world
test; these pin the pieces: what a batch's labels are read from, the
relabel ``UPDATE`` each dialect renders, and that the rebuild repairs any
label from the posture rows alone.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select, update
from sqlalchemy.dialects import mssql, oracle, postgresql, sqlite
from sqlalchemy.dialects.mysql import mariadb

from tests.support.oracles.grants import GrantWorld, everyone_rank
from vfs.authority import Authority
from vfs.models import Entry
from vfs.models.rows import build_vfs_tables
from vfs.paths import Path
from vfs.storage.backends.database.dialects import GENERIC, MARIADB, MSSQL, ORACLE, POSTGRESQL, SQLITE
from vfs.storage.backends.database.labels import (
    Mark,
    Relabel,
    Relabeller,
    _Batch,
    _batched,
    _relabel_opens,
    inflight_marks,
    inflight_postures,
    labels_for,
    mark_relabel,
    posture_beneath,
    rebuild_labels,
)
from vfs.storage.backends.database.revision import bump_revision, hold_revision, read_revision
from vfs.storage.backends.memory import InMemoryStorage
from vfs.storage.grants import GrantLevel, GrantRow, Posture, normalise

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.engine import Dialect

    from vfs.storage.backends.database.dialects import DialectProfile

SYSTEM = Authority.system()
ENTRY = build_vfs_tables().entry
OPENS = (("/a/", "/a0"), ("/b/", "/b0"))

# Each profile, the dialect that renders it, and what its relabel must spell.
SPELLINGS: list[tuple[DialectProfile, Dialect, tuple[str, ...]]] = [
    (SQLITE, sqlite.dialect(), ("UPDATE vfs_entries SET everyone_level", "FROM json_each(", "json_extract(")),
    (POSTGRESQL, postgresql.dialect(), ("UPDATE vfs_entries SET everyone_level", "FROM unnest(", 'COLLATE "C"')),
    (MSSQL, mssql.dialect(), ("UPDATE e SET everyone_level", "OPENJSON(", "INNER LOOP JOIN vfs_entries AS e")),
    (
        MARIADB,
        mariadb.MariaDBDialect(),
        ("UPDATE vfs_entries AS e JOIN JSON_TABLE(", "AS BINARY", "SET e.everyone_level"),
    ),
    (ORACLE, oracle.dialect(), ("UPDATE /*+ USE_CONCAT */ vfs_entries", "vfs_entries.path > ", " OR ")),
    (GENERIC, sqlite.dialect(), ("UPDATE vfs_entries SET everyone_level", " OR ", "vfs_entries.path < ")),
]


@pytest.fixture
async def storage() -> AsyncIterator[InMemoryStorage]:
    storage = InMemoryStorage()
    assert (await storage.posture(path=Path("/"), posture="shared", authority=SYSTEM)).success is True
    yield storage
    await storage.close()


@pytest.mark.parametrize(("profile", "dialect", "fragments"), SPELLINGS, ids=[s[0].name for s in SPELLINGS])
def test_the_relabel_renders_each_dialects_measured_form(
    profile: DialectProfile, dialect: Dialect, fragments: tuple[str, ...]
) -> None:
    stmt, params = _relabel_opens(ENTRY, profile, 1, OPENS)
    sql = str(stmt.compile(dialect=dialect))
    for fragment in fragments:
        assert fragment in sql, sql
    assert "LIKE" not in sql
    # The text spellings carry the ranges as one bound value; the rest bind through Core.
    assert set(params) == ({"rank", "pairs"} if profile.name in ("mssql", "mariadb") else set())
    # The live form keeps to rows with no origin; the trashed form seeks the origin alone.
    assert "origin_path IS NULL" in sql and sql.count("origin_path") == 1
    trashed = str(_relabel_opens(ENTRY, profile, 1, OPENS, trashed=True)[0].compile(dialect=dialect))
    assert "IS NULL" not in trashed and "origin_path > " in trashed and "origin_path < " in trashed


async def test_a_batch_takes_its_labels_from_the_deepest_covering_posture(storage: InMemoryStorage) -> None:
    await storage.mkdir(path=Path("/a/b"), parents=True, authority=SYSTEM)
    assert (await storage.posture(path=Path("/a"), posture="private", authority=SYSTEM)).success is True
    assert (await storage.posture(path=Path("/a/b"), posture="open", authority=SYSTEM)).success is True
    host = storage._host
    async with host.session_factory() as session:
        labels = await labels_for(
            session, host.tables, host.profile, host.membership_budget, ["/x.md", "/a/x.md", "/a/b/x.md", "/a/b"]
        )
        postures = await posture_beneath(session, host.tables, host.profile, host.membership_budget, "/a")
    assert labels == {"/x.md": 1, "/a/x.md": 0, "/a/b/x.md": 2, "/a/b": 2}
    assert postures == {"/a": "none", "/a/b": "read_write"}


async def test_a_posture_change_reports_what_it_relabelled(storage: InMemoryStorage) -> None:
    entries = [Entry(path=Path(f"/d/{n}.md"), content="x") for n in range(5)]
    entries.append(Entry(path=Path("/d/sub/k.md"), content="x"))
    assert (await storage.write(entries=entries, parents=True, authority=SYSTEM)).success is True
    assert (await storage.posture(path=Path("/d/sub"), posture="private", authority=SYSTEM)).success is True
    result = await storage.posture(path=Path("/d"), posture="open", authority=SYSTEM)
    assert result.success is True
    # /d itself, its five files, and nothing under the deeper posture: one
    # point, one range, each in its live and trashed form, one chunk after
    # the transaction that wrote the row.
    assert (result.model_extra or {})["relabel"] == {"rows": 6, "statements": 4, "transactions": 1}
    host = storage._host
    relabeller = Relabeller(host.tables, host.profile, host.membership_budget)
    async with host.session_factory() as session:
        assert await relabeller.step(session) is None


async def test_the_rebuild_repairs_every_label_from_the_posture_rows(storage: InMemoryStorage) -> None:
    paths = ["/a/x.md", "/a/b/y.md", "/a-b/z.md", "/a0/w.md", "/c/v.md"]
    assert (await storage.write(entries=[Entry(path=Path(p), content="x") for p in paths], parents=True)).success
    postures: list[tuple[str, Posture]] = [("/a", "private"), ("/a/b", "open"), ("/c", "private")]
    for path, posture in postures:
        assert (await storage.posture(path=Path(path), posture=posture, authority=SYSTEM)).success is True
    host = storage._host
    entry = host.tables.entry
    async with host.session_factory() as session, session.begin():
        await session.execute(update(entry).values(everyone_level=2))
        done = await rebuild_labels(session, host.tables, host.profile, host.membership_budget)
    assert done.rows >= len(paths) and done.statements >= 3
    levels: dict[str, GrantLevel] = {"private": "none", "open": "read_write"}
    world = GrantWorld([GrantRow("*", "/", "read"), *(GrantRow("*", p, levels[posture]) for p, posture in postures)])
    async with host.session_factory() as session:
        stored = (await session.execute(select(entry.c.path, entry.c.everyone_level))).all()
    assert {row.path: row.everyone_level for row in stored} == {
        row.path: everyone_rank(world, row.path) for row in stored
    }


async def test_a_relabel_walks_a_large_subtree_in_bounded_chunks(storage: InMemoryStorage) -> None:
    # A 50-row subtree with the row cap lowered to seven: no chunk rewrites
    # more than seven rows, the ranges are walked by keyset past the cap,
    # and every label is right when the walk settles.
    entries = [Entry(path=Path(f"/d/{n:03}.md"), content="x") for n in range(50)]
    assert (await storage.write(entries=entries, parents=True, authority=SYSTEM)).success is True
    host = storage._host
    profile = replace(host.profile, relabel_rows=7)
    async with host.session_factory() as session, session.begin():
        revision = await bump_revision(session, host.tables)
        await session.execute(
            host.tables.grants.update()
            .where(host.tables.grants.c.principal_id == "*", host.tables.grants.c.path_prefix == "/")
            .values(level="none", revision=revision)
        )
        await mark_relabel(session, host.tables, "/", revision)
    relabeller = Relabeller(host.tables, profile, host.membership_budget)
    steps: list[Relabel] = []
    while True:
        async with host.session_factory() as session, session.begin():
            done = await relabeller.step(session)
        if done is None:
            break
        steps.append(done)
    assert all(step.rows <= 7 for step in steps), steps
    assert sum(step.rows for step in steps) >= 51 and len(steps) >= 8
    assert all(step.transactions == 1 for step in steps)
    entry = host.tables.entry
    async with host.session_factory() as session:
        levels = set((await session.execute(select(entry.c.everyone_level))).scalars())
        pending = (await session.execute(select(host.tables.relabels.c.path_prefix))).all()
    assert levels == {0} and pending == []


async def test_a_dead_relabel_resumes_and_reads_stay_exact_meanwhile(storage: InMemoryStorage) -> None:
    # A root posture drops to private, then the relabel dies after its
    # first chunk. The labels beneath are still stale, but the in-flight
    # compile already hides the subtree; a fresh driver finishes it.
    entries = [Entry(path=Path(f"/d/{n:03}.md"), content="x") for n in range(30)]
    assert (await storage.write(entries=entries, parents=True, authority=SYSTEM)).success is True
    host = storage._host
    profile = replace(host.profile, relabel_rows=7)
    async with host.session_factory() as session, session.begin():
        revision = await bump_revision(session, host.tables)
        await session.execute(
            host.tables.grants.update()
            .where(host.tables.grants.c.principal_id == "*", host.tables.grants.c.path_prefix == "/")
            .values(level="none", revision=revision)
        )
        await mark_relabel(session, host.tables, "/", revision)
    dying = Relabeller(host.tables, profile, host.membership_budget)
    async with host.session_factory() as session, session.begin():
        assert await dying.step(session) is not None
    entry = host.tables.entry
    async with host.session_factory() as session:
        stale = set((await session.execute(select(entry.c.everyone_level))).scalars())
        marks = await inflight_marks(session, host.tables)
        postures = await inflight_postures(session, host.tables, host.profile, host.membership_budget, marks)
    # A chunk ran, so some labels are stale and some already rewritten; the
    # mark still stands, so the in-flight compile covers the whole subtree.
    assert stale == {0, 1} and marks == (Mark("/", revision),) and postures == {"/": "none"}
    # A fresh driver resumes from the cursor and clears the mark.
    resumed = Relabeller(host.tables, host.profile, host.membership_budget)
    while True:
        async with host.session_factory() as session, session.begin():
            if await resumed.step(session) is None:
                break
    world = GrantWorld([GrantRow("*", "/", "none")])
    async with host.session_factory() as session:
        rows = (await session.execute(select(entry.c.path, entry.c.everyone_level))).all()
        left = (await session.execute(select(host.tables.relabels.c.path_prefix))).all()
    assert left == []
    assert {row.path: row.everyone_level for row in rows} == {row.path: everyone_rank(world, row.path) for row in rows}


async def test_the_marks_and_the_pending_postures_follow_the_table(storage: InMemoryStorage) -> None:
    await storage.mkdir(path=Path("/a/b"), parents=True, authority=SYSTEM)
    assert (await storage.posture(path=Path("/a"), posture="shared", authority=SYSTEM)).success is True
    assert (await storage.posture(path=Path("/a/b"), posture="private", authority=SYSTEM)).success is True
    host = storage._host
    async with host.session_factory() as session:
        none = await inflight_marks(session, host.tables)
        empty = await inflight_postures(session, host.tables, host.profile, host.membership_budget, none)
    assert none == () and empty == {}
    async with host.session_factory() as session, session.begin():
        await mark_relabel(session, host.tables, "/a", 7)
        # A second mark on the same path resets the cursor and restamps, never doubles the row.
        await session.execute(host.tables.relabels.update().values(cursor="/a/x"))
        await mark_relabel(session, host.tables, "/a", 9)
        marks = await inflight_marks(session, host.tables)
        postures = await inflight_postures(session, host.tables, host.profile, host.membership_budget, marks)
    assert marks == (Mark("/a", 9),) and postures == {"/a": "read", "/a/b": "none"}
    async with host.session_factory() as session:
        row = (await session.execute(select(host.tables.relabels))).one()
    assert row.path_prefix == "/a" and row.cursor is None and row.revision == 9


def test_batched_flushes_before_a_walked_span_and_when_a_chunk_fills() -> None:
    # A small span accumulates, then one over the row cap forces a flush and
    # becomes a walked batch of its own; the points after it fill a chunk and
    # flush again when the next would overflow. Piece and row caps both bind.
    spans = normalise([("/a", "/a\x00"), ("/b/", "/b0"), *((f"/c{n}", f"/c{n}\x00") for n in range(12))])
    counts = {("/b/", "/b0"): 50}
    batches = _batched(spans, counts, piece_cap=100, row_cap=10)
    walked = [b for b in batches if b.walked]
    assert walked == [_Batch(normalise([("/b/", "/b0")]), walked=True)]
    assert batches[0] == _Batch(normalise([("/a", "/a\x00")]), walked=False)
    # The twelve points after the walked span split across chunks at the row cap.
    point_batches = [b for b in batches[2:] if not b.walked]
    assert len(point_batches) >= 2 and all(len(b.spans) <= 10 for b in point_batches)
    # The piece cap also splits: two points per chunk when it is two.
    tight = _batched(normalise((f"/p{n}", f"/p{n}\x00") for n in range(5)), {}, piece_cap=2, row_cap=100)
    assert [len(b.spans) for b in tight] == [2, 2, 1]


async def test_the_generic_floor_relabels_with_literal_ranges_and_counts_one_at_a_time(
    storage: InMemoryStorage,
) -> None:
    # No range source: the relabel counts each open range with its own
    # SELECT and rewrites with a literal OR of ranges. A deeper posture
    # carves the region into points and open ranges, so both legs run.
    paths = [f"/d/{n}.md" for n in range(4)] + ["/d/sub/k.md", "/e.md"]
    assert (await storage.write(entries=[Entry(path=Path(p), content="x") for p in paths], parents=True)).success
    assert (await storage.posture(path=Path("/d/sub"), posture="open", authority=SYSTEM)).success is True
    host = storage._host
    profile = replace(host.profile, range_source=None)
    async with host.session_factory() as session, session.begin():
        revision = await bump_revision(session, host.tables)
        await session.execute(
            host.tables.grants.update()
            .where(host.tables.grants.c.principal_id == "*", host.tables.grants.c.path_prefix == "/")
            .values(level="none", revision=revision)
        )
        await mark_relabel(session, host.tables, "/", revision)
    relabeller = Relabeller(host.tables, profile, host.membership_budget)
    while True:
        async with host.session_factory() as session, session.begin():
            if await relabeller.step(session) is None:
                break
    world = GrantWorld([GrantRow("*", "/", "none"), GrantRow("*", "/d/sub", "read_write")])
    entry = host.tables.entry
    async with host.session_factory() as session:
        rows = (await session.execute(select(entry.c.path, entry.c.everyone_level))).all()
    assert {row.path: row.everyone_level for row in rows} == {row.path: everyone_rank(world, row.path) for row in rows}


async def test_hold_revision_locks_without_advancing(storage: InMemoryStorage) -> None:
    await storage.first_touch()
    host = storage._host
    async with host.session_factory() as session, session.begin():
        before = await read_revision(session, host.tables)
        held = await hold_revision(session, host.tables)
        bumped = await bump_revision(session, host.tables)
    assert held == before and bumped == before + 1


async def test_a_mount_with_no_root_posture_rebuilds_to_none(storage: InMemoryStorage) -> None:
    assert (await storage.write(entries=[Entry(path=Path("/k.md"), content="x")])).success is True
    host = storage._host
    grants, entry = host.tables.grants, host.tables.entry
    async with host.session_factory() as session, session.begin():
        await session.execute(grants.delete())
        await rebuild_labels(session, host.tables, host.profile, host.membership_budget)
    async with host.session_factory() as session:
        levels = set((await session.execute(select(entry.c.everyone_level))).scalars())
    assert levels == {0}
