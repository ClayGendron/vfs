"""The everyone level on the row — the labeller, the relabel's spellings, and the rebuild.

Row-exact parity after every mutation is ``test_rights.py``'s random-world
test; these pin the pieces: what a batch's labels are read from, the
relabel ``UPDATE`` each dialect renders, and that the rebuild repairs any
label from the posture rows alone.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import event, select, text, update
from sqlalchemy.dialects import mssql, oracle, postgresql, sqlite
from sqlalchemy.dialects.mysql import mariadb
from sqlalchemy.exc import DBAPIError

from tests.support.commit_worlds import ANONYMOUS, BOB, CAROL, attempts, clearing, label_world, row_at, stamp
from tests.support.oracles.grants import GrantWorld, everyone_rank
from tests.support.server_schemas import ENGINE_LEGS, server_storage
from vfs.authority import EVERYONE_NAME, Authority
from vfs.models import Entry
from vfs.models.rows import build_vfs_tables
from vfs.paths import Path
from vfs.results import ErrorKind
from vfs.storage import ResolvedPair
from vfs.storage.backends.database import authorized as authorized_module
from vfs.storage.backends.database.dialects import GENERIC, MARIADB, MSSQL, ORACLE, POSTGRESQL, SQLITE, StaleSnapshot
from vfs.storage.backends.database.labels import (
    POSTURE_MOVED,
    Mark,
    Relabel,
    Relabeller,
    _Batch,
    _batched,
    _relabel_opens,
    hold_postures,
    inflight_marks,
    inflight_postures,
    labels_for,
    mark_relabel,
    open_relabel,
    posture_beneath,
    rebuild_labels,
    watch_postures,
)
from vfs.storage.backends.database.revision import bump_revision, hold_revision, read_revision
from vfs.storage.backends.database.seams import installed
from vfs.storage.backends.memory import InMemoryStorage
from vfs.storage.grants import LEVEL_RANK, GrantRow, Posture, normalise
from vfs.storage.replace import EditOperation

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.engine import Dialect
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models.rows import VFSTables
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
    assert (await storage.set_posture(path=Path("/"), posture="read", authority=SYSTEM)).success is True
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
    # One form: a deleted row is relabelled where it sits.
    assert "origin_path" not in sql and "deleted_at" not in sql


async def test_a_batch_takes_its_labels_from_the_deepest_covering_posture(storage: InMemoryStorage) -> None:
    await storage.mkdir(path=Path("/a/b"), parents=True, authority=SYSTEM)
    assert (await storage.set_posture(path=Path("/a"), posture="none", authority=SYSTEM)).success is True
    assert (await storage.set_posture(path=Path("/a/b"), posture="read_write", authority=SYSTEM)).success is True
    host = storage._host
    async with host.session_factory() as session:
        labels = await labels_for(
            session, host.tables, host.profile, host.membership_budget, ["/x.md", "/a/x.md", "/a/b/x.md", "/a/b"]
        )
        postures = await posture_beneath(session, host.tables, host.profile, host.membership_budget, "/a")
    read, none, read_write = LEVEL_RANK["read"], LEVEL_RANK["none"], LEVEL_RANK["read_write"]
    assert labels == {"/x.md": read, "/a/x.md": none, "/a/b/x.md": read_write, "/a/b": read_write}
    assert postures == {"/a": "none", "/a/b": "read_write"}


async def test_a_posture_change_reports_what_it_relabelled(storage: InMemoryStorage) -> None:
    entries = [Entry(path=Path(f"/d/{n}.md"), content="x") for n in range(5)]
    entries.append(Entry(path=Path("/d/sub/k.md"), content="x"))
    assert (await storage.write(entries=entries, parents=True, authority=SYSTEM)).success is True
    assert (await storage.set_posture(path=Path("/d/sub"), posture="none", authority=SYSTEM)).success is True
    result = await storage.set_posture(path=Path("/d"), posture="read_write", authority=SYSTEM)
    assert result.success is True
    # /d itself, its five files, and nothing under the deeper posture: one
    # point, one range, one chunk after the transaction that wrote the row.
    assert (result.model_extra or {})["relabel"] == {"rows": 6, "statements": 2, "transactions": 1}
    host = storage._host
    relabeller = Relabeller(host.tables, host.profile, host.membership_budget)
    async with host.session_factory() as session:
        assert await relabeller.step(session) is None


async def test_the_rebuild_repairs_every_label_from_the_posture_rows(storage: InMemoryStorage) -> None:
    paths = ["/a/x.md", "/a/b/y.md", "/a-b/z.md", "/a0/w.md", "/c/v.md"]
    assert (await storage.write(entries=[Entry(path=Path(p), content="x") for p in paths], parents=True)).success
    postures: list[tuple[str, Posture]] = [("/a", "none"), ("/a/b", "read_write"), ("/c", "none")]
    for path, posture in postures:
        assert (await storage.set_posture(path=Path(path), posture=posture, authority=SYSTEM)).success is True
    host = storage._host
    entry = host.tables.entry
    async with host.session_factory() as session, session.begin():
        await session.execute(update(entry).values(everyone_level=LEVEL_RANK["read_write"]))
        done = await rebuild_labels(session, host.tables, host.profile, host.membership_budget)
    assert done.rows >= len(paths) and done.statements >= 3
    world = GrantWorld([GrantRow("*", "/", "read"), *(GrantRow("*", p, posture) for p, posture in postures)])
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
    assert (
        stale == {LEVEL_RANK["none"], LEVEL_RANK["read"]}
        and marks == (Mark("/", revision),)
        and postures == {"/": "none"}
    )
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
    assert (await storage.set_posture(path=Path("/a"), posture="read", authority=SYSTEM)).success is True
    assert (await storage.set_posture(path=Path("/a/b"), posture="none", authority=SYSTEM)).success is True
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
    assert (await storage.set_posture(path=Path("/d/sub"), posture="read_write", authority=SYSTEM)).success is True
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


# ---------------------------------------------------------------------------
# The proof — a mint's label against a posture change inside its window
# ---------------------------------------------------------------------------

# What a mint that arrives behind a waiting posture write sets before its hold, so the engine refuses it at once.
_NO_WAIT = {
    "postgresql": "SET LOCAL lock_timeout = '300ms'",
    "mariadb": "SET SESSION innodb_lock_wait_timeout = 1",
    "mssql": "SET LOCK_TIMEOUT 300",
}


def _statements(storage: InMemoryStorage) -> list[str]:
    """Every statement *storage*'s engine issues from now on."""
    seen: list[str] = []
    engine = storage._host.engine.sync_engine
    event.listen(engine, "before_cursor_execute", lambda conn, cursor, statement, *rest: seen.append(statement))
    return seen


def _proof_reads(statements: list[str]) -> list[str]:
    """The watch and the hold among *statements*: a read of one stamp row, never the fence's maximum over many."""
    return [s for s in statements if "principal_revisions.revision" in s and "max(" not in s.lower()]


def _stamp_then_postures(statements: list[str]) -> bool:
    """Whether the first read of the stamps table among *statements* comes before the first read of the posture rows."""
    order = [s for s in statements if "principal_revisions" in s or "vfs_grants" in s]
    return len(order) >= 2 and "principal_revisions" in order[0] and "vfs_grants" in order[1]


class TestProof:
    """A mint reads the everyone stamp before its labels and again, under a shared lock, as its last statement."""

    async def test_a_call_that_reads_no_label_holds_nothing(self, storage: InMemoryStorage) -> None:
        """The hold is paid by the calls that mint, and by no other.

        Guards the early return in ``hold_postures``: a hold that read the
        stamp with no watch would add a statement to every mutation.
        """
        host = storage._host
        seen = _statements(storage)
        async with host.session_factory() as session:
            await hold_postures(session, host.tables, host.profile)
            assert await labels_for(session, host.tables, host.profile, host.membership_budget, []) == {}
        assert _proof_reads(seen) == []
        target = Path("/a/new.txt")
        created = await storage.write(entries=[Entry(path=target, content="alpha\n")], parents=True, authority=SYSTEM)
        assert created.success is True, created.errors
        assert len(_proof_reads(seen)) == 2
        seen.clear()
        assert (await storage.write(entries=[Entry(path=target, content="alpha beta\n")], authority=SYSTEM)).success
        edit = [EditOperation(old="alpha", new="gamma")]
        assert (await storage.edit(edits=edit, path=target, authority=SYSTEM)).success is True
        assert (await storage.delete(path=target, authority=SYSTEM)).success is True
        assert (await storage.restore(path=target, authority=SYSTEM)).success is True
        assert _proof_reads(seen) == []

    async def test_the_watch_reads_once_an_attempt(self, storage: InMemoryStorage) -> None:
        """Two label reads in one attempt share one watch: the stamp is the one read before the first of them."""
        host = storage._host
        seen = _statements(storage)
        async with host.session_factory() as session:
            await labels_for(session, host.tables, host.profile, host.membership_budget, ["/a/x.md"])
            assert _stamp_then_postures(seen)
            await labels_for(session, host.tables, host.profile, host.membership_budget, ["/b/y.md"])
            await posture_beneath(session, host.tables, host.profile, host.membership_budget, "/a")
            assert len(_proof_reads(seen)) == 1
            await hold_postures(session, host.tables, host.profile)
        assert len(_proof_reads(seen)) == 2

    async def test_a_transfer_watches_before_it_reads_the_destinations_postures(self, storage: InMemoryStorage) -> None:
        """``posture_beneath`` reads the stamp first: a posture read ahead of the watch could be older than it."""
        host = storage._host
        seen = _statements(storage)
        async with host.session_factory() as session:
            await posture_beneath(session, host.tables, host.profile, host.membership_budget, "/a")
        assert _stamp_then_postures(seen)

    @pytest.mark.parametrize("verb", ["write", "move", "copy"])
    async def test_a_stamp_moved_since_the_watch_redrives(self, monkeypatch: pytest.MonkeyPatch, verb: str) -> None:
        """A posture stamp that moves after a mint's label read makes the mint run again, for the system actor too.

        Guards ``hold_postures`` in ``fenced`` and its comparison: with the
        hold dropped or its test inverted, the call commits in one attempt
        on the labels it read before the stamp moved.
        """
        storage = InMemoryStorage()
        await label_world(storage)
        sessions = attempts(monkeypatch, storage)
        raised: list[str] = []
        hold = authorized_module.hold_postures

        async def spied(session: AsyncSession, tables: VFSTables, profile: DialectProfile) -> None:
            try:
                await hold(session, tables, profile)
            except StaleSnapshot as moved:
                raised.append(moved.context)
                raise

        monkeypatch.setattr(authorized_module, "hold_postures", spied)
        moved = [ResolvedPair(src=Path("/p/d"), dest=Path("/p/m"))]
        copied = [ResolvedPair(src=Path("/p/d"), dest=Path("/p/c"))]
        seam_name, call, minted = {
            "write": (
                "write:after-labels",
                lambda: storage.write(entries=[Entry(path=Path("/p/n.txt"), content="n")]),
                "/p/n.txt",
            ),
            "move": ("transfer:after-postures", lambda: storage.move(operations=moved), "/p/m/f.txt"),
            "copy": ("transfer:after-postures", lambda: storage.copy(operations=copied), "/p/c/f.txt"),
        }[verb]
        rival = clearing(seam_name, lambda: stamp(sessions[-1], storage._host.tables, EVERYONE_NAME))
        with installed(seam_name, rival):
            result = await call()
        assert result.success is True, result.errors
        assert len(sessions) == 2
        assert raised == [POSTURE_MOVED]
        assert await row_at(storage, minted) is not None
        await storage.close()

    async def test_a_mint_that_loses_every_attempt_answers_a_retryable_conflict(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A posture stamp that moves under every attempt ends the call in one retryable conflict, naming no path."""
        storage = InMemoryStorage()
        await label_world(storage)
        sessions = attempts(monkeypatch, storage)

        async def moved() -> None:
            await stamp(sessions[-1], storage._host.tables, EVERYONE_NAME)

        with installed("write:after-labels", moved):
            result = await storage.write(entries=[Entry(path=Path("/p/n.txt"), content="n")])
        assert len(sessions) == 4
        assert [(error.kind, error.retryable) for error in result.errors] == [(ErrorKind.conflict, True)]
        assert POSTURE_MOVED in result.errors[0].message and "/p" not in result.errors[0].message
        assert await row_at(storage, "/p/n.txt") is None
        await storage.close()

    async def test_a_hold_that_finds_no_stamp_row_refuses(self, storage: InMemoryStorage) -> None:
        """A store whose everyone stamp is gone has nothing to lock: a mint there does not commit.

        Guards the missing-row arm of ``hold_postures``: read as zero, the
        hold would pass on a lock that holds nothing.
        """
        host = storage._host
        async with host.session_factory() as session, session.begin():
            await session.execute(host.tables.principal_revisions.delete())
        result = await storage.write(entries=[Entry(path=Path("/new.txt"), content="x")], authority=SYSTEM)
        assert [(error.kind, error.retryable) for error in result.errors] == [(ErrorKind.conflict, True)]
        assert await row_at(storage, "/new.txt") is None

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_a_posture_write_waits_for_the_holds_in_flight_and_no_later_one(self, env_var: str) -> None:
        """Mints share the stamp lock; a posture write waits for the holders it found and queues every later one.

        Outcomes are counted: the engine's own lock error on a no-wait hold
        is the signal that a later mint queued, within a bounded number of tries.
        """
        async with server_storage(env_var, posture="none") as storage:
            await label_world(storage)
            assert (await storage.grant(path=Path("/p"), principal="bob", level="read_write")).success is True
            host = storage._host
            tables, profile = host.tables, host.profile
            revisions = tables.principal_revisions
            stamp_of_everyone = select(revisions.c.revision).where(revisions.c.principal_id == EVERYONE_NAME)

            async def hold(session: AsyncSession) -> None:
                await watch_postures(session, tables)
                await hold_postures(session, tables, profile)

            factory = host.session_factory
            async with factory() as session:
                standing = (await session.execute(stamp_of_everyone)).scalar_one()
            async with factory() as first, factory() as second, factory() as third, factory() as fifth:
                await hold(first)
                await hold(second)
                await second.rollback()
                existing = Path("/p/d/f.txt")
                assert (await storage.read(path=existing)).success is True
                assert (await storage.glob(patterns=("/p/**",))).success is True
                assert (await storage.write(entries=[Entry(path=existing, content="f2")])).success is True
                # Beside a held hold every kind of caller reads, a named one searches and rewrites.
                for reader in (BOB, CAROL, ANONYMOUS):
                    assert (await storage.read(path=existing, authority=reader)).success is True
                assert (await storage.search(query="held hold probe", authority=BOB)).success is True
                rewrite = [Entry(path=existing, content="f3")]
                assert (await storage.write(entries=rewrite, authority=BOB)).success is True
                revision = await bump_revision(third, tables)
                posture_write = asyncio.ensure_future(open_relabel(third, tables, profile, "/p", revision))
                try:
                    refused = False
                    for _ in range(200):
                        async with factory() as fourth:
                            try:
                                if profile.name == "oracle":
                                    name = fourth.get_bind().dialect.identifier_preparer.format_table(revisions)
                                    await fourth.execute(text(f"LOCK TABLE {name} IN SHARE MODE NOWAIT"))
                                else:
                                    await fourth.execute(text(_NO_WAIT[profile.name]))
                                    await hold(fourth)
                            except DBAPIError:
                                refused = True
                                break
                            await fourth.rollback()
                    assert refused, f"{profile.name}: a later hold was granted 200 times beside a waiting posture write"
                    assert not posture_write.done()
                    # The posture write has committed nothing, so a plain read still returns the standing stamp.
                    if profile.name != "mssql":
                        assert (await fifth.execute(stamp_of_everyone)).scalar_one() == standing
                    await first.commit()
                    await posture_write
                    await third.commit()
                finally:
                    # A failed check must not leave the posture write waiting on a session the block is closing.
                    posture_write.cancel()
            async with factory() as session:
                assert (await session.execute(stamp_of_everyone)).scalar_one() == revision
