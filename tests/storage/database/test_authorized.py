"""What a mutation proves between its gate and its commit: the fence, its costs, and the windows SQLite keeps shut.

The fence is the attempt's last statement: the stamps of the caller's
ids and the everyone principal, compared with the mount revision the
gate opened under. A rival's admin write is staged on the attempt's own
session at a seam, the SQLite and in-memory idiom, so each row here
counts attempts and statements, never a clock. The closed windows are
pinned with a genuine second handle: on SQLite and in memory it waits
for the attempt to commit, so it is ordered after the verb.
"""

from __future__ import annotations

import asyncio
import inspect
import sqlite3
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import event

from tests.support.commit_worlds import (
    ALICE,
    BOB,
    EVE,
    SYSTEM,
    attempts,
    clearing,
    drop_world,
    grant_world,
    label_world,
    land,
    paths_under,
    row_at,
    stamp,
)
from tests.support.database_helpers import _url
from tests.support.statements import is_statistics_statement
from vfs.authority import Authority, Principal
from vfs.models import Edge, Entry
from vfs.ops import MUTATING_OPS
from vfs.paths import Path
from vfs.results import ErrorKind
from vfs.storage import ResolvedPair
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database import backend as backend_module
from vfs.storage.backends.database import rights as rights_module
from vfs.storage.backends.database import writes as writes_module
from vfs.storage.backends.database.seams import installed
from vfs.storage.backends.memory import InMemoryStorage
from vfs.storage.replace import EditOperation

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from vfs.results import Result

DAN = Authority.of(Principal("dan"))

# The one record an exhausted redrive leaves: a retryable conflict naming no path.
_CONFLICT = (ErrorKind.conflict, True, None)

# The grant world's edge, and the one bob's mkedge adds beside it.
_EDGE = Edge(source=Path("/g/d/sub/g.txt"), target=Path("/g/d/f.txt"), edge_type="ref")
_NEW_EDGE = Edge(source=Path("/g/d/f.txt"), target=Path("/g/d/sub/g.txt"), edge_type="ref")
_EDGES_AFTER = {
    "mkedge": {("/g/d/sub/g.txt", "/g/d/f.txt"), ("/g/d/f.txt", "/g/d/sub/g.txt")},
    "rmedge": set(),
}
# The row each verb's effect is read at, the source tree's file where none is named.
_EFFECT_AT = {"write": "/g/new.txt", "mkdir": "/g/m", "restore": "/g/old.txt"}


def _verbs(storage: DatabaseStorage) -> dict[str, tuple[str, Callable[[], Awaitable[Result]]]]:
    """Each verb bob runs in the grant world, and the seam its rival waits at."""
    written = [Entry(path=Path("/g/new.txt"), content="n")]
    edit = [EditOperation(old="alpha", new="beta")]
    moved = [ResolvedPair(src=Path("/g/d"), dest=Path("/g/e"))]
    copied = [ResolvedPair(src=Path("/g/d"), dest=Path("/g/c"))]
    return {
        "write": ("write:before-apply", lambda: storage.write(entries=written, authority=BOB)),
        "edit": ("write:before-apply", lambda: storage.edit(edits=edit, path=Path("/g/d/f.txt"), authority=BOB)),
        "mkdir": ("write:before-apply", lambda: storage.mkdir(path=Path("/g/m"), authority=BOB)),
        "mkedge": ("mkedge:before-insert", lambda: storage.mkedge(edges=[_NEW_EDGE], authority=BOB)),
        "rmedge": ("rmedge:before-resolve", lambda: storage.rmedge(edges=[_EDGE], authority=BOB)),
        "delete": ("delete:post-collect", lambda: storage.delete(path=Path("/g/d"), authority=BOB)),
        "restore": ("restore:post-resolve", lambda: storage.restore(path=Path("/g/old.txt"), authority=BOB)),
        "move": ("transfer:post-collect", lambda: storage.move(operations=moved, authority=BOB)),
        "copy": ("transfer:post-collect", lambda: storage.copy(operations=copied, authority=BOB)),
        "sweep": ("purge:post-collect", lambda: storage.sweep(path=Path("/g/d"), authority=BOB)),
    }


async def _effect(storage: DatabaseStorage, verb: str) -> bool:
    """Whether *verb*'s one effect stands in the grant world, read as the system actor."""
    row = await row_at(storage, _EFFECT_AT.get(verb, "/g/d/f.txt"))
    if verb in ("write", "mkdir", "restore"):
        return row is not None and row["deleted_at"] is None
    if verb == "edit":
        return row is not None and row["content"] == "beta\n"
    if verb in _EDGES_AFTER:
        return await _authored(storage) == _EDGES_AFTER[verb]
    if verb == "delete":
        return row is not None and row["deleted_at"] is not None
    if verb == "copy":
        return await paths_under(storage, "/g/c") == {"/g/c", "/g/c/f.txt", "/g/c/sub", "/g/c/sub/g.txt"}
    moved = verb == "sweep" or await row_at(storage, "/g/e/f.txt") is not None
    return await paths_under(storage, "/g/d") == set() and moved


async def _authored(storage: DatabaseStorage) -> set[tuple[str, str]]:
    tables = storage._host.tables
    entry, edges = tables.entry, tables.edges
    async with storage._host.session_factory() as session:
        paths = {row.entry_id: row.path for row in await session.execute(entry.select())}
        found = await session.execute(edges.select().where(edges.c.edge_type == "ref"))
        return {(paths[row.source_id], paths[row.target_id]) for row in found}


def _statements(storage: DatabaseStorage, recorded: list[str] | None = None) -> list[str]:
    """Every statement *storage* issues from now on, into *recorded*, the planner-statistics step left out."""
    into: list[str] = [] if recorded is None else recorded

    @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
    def record(conn, cursor, statement, parameters, context, executemany) -> None:
        if not is_statistics_statement(statement):
            into.append(statement)

    return into


def _while(monkeypatch: pytest.MonkeyPatch, module: Any, name: str, statements: list[str]) -> list[int]:
    """Statements issued while *module*'s *name* runs, one count per call; *statements* is a live recording."""
    counts: list[int] = []
    original = getattr(module, name)

    async def counted(*args: Any, **kwargs: Any) -> Any:
        start = len(statements)
        try:
            return await original(*args, **kwargs)
        finally:
            counts.append(len(statements) - start)

    def counted_now(*args: Any, **kwargs: Any) -> Any:
        start = len(statements)
        try:
            return original(*args, **kwargs)
        finally:
            counts.append(len(statements) - start)

    monkeypatch.setattr(module, name, counted if inspect.iscoroutinefunction(original) else counted_now)
    return counts


def _naming(statements: list[str], table: str) -> int:
    return sum(1 for sql in statements if sql.lstrip().upper().startswith("SELECT") and table in sql)


# ---------------------------------------------------------------------------
# The fence
# ---------------------------------------------------------------------------


class TestRightsFence:
    """A rights change committed after a verb's gate makes the verb run again from the later rights."""

    @pytest.mark.parametrize("verb", sorted(MUTATING_OPS))
    async def test_every_data_verb_redrives_when_the_callers_rights_move_after_its_gate(
        self, monkeypatch, verb: str
    ) -> None:
        """A stamp naming bob, staged at the verb's seam, redrives it once; its effect stands once.

        Guards ``fenced`` in ``_execute_write`` and ``_execute_topology``:
        with the fence's ``hold_rights`` dropped, every verb commits in one attempt.
        """
        storage = InMemoryStorage()
        await grant_world(storage)
        sessions = attempts(monkeypatch, storage)
        seam_name, call = _verbs(storage)[verb]
        with installed(seam_name, clearing(seam_name, lambda: stamp(sessions[-1], storage._host.tables, "bob"))):
            result = await call()
        assert result.success is True, result.errors
        assert len(sessions) == 2
        assert await _effect(storage, verb)

    async def test_a_compile_the_cache_would_not_keep_redrives_once(self, monkeypatch) -> None:
        """An admin write landing between a cold compile's two revision reads leaves the basis unsettled: one redrive.

        Guards the unsettled basis in ``hold_rights``: passed instead of
        redriven, bob's write commits on a compile that may mix two states.
        """
        storage = InMemoryStorage()
        await grant_world(storage)
        sessions = attempts(monkeypatch, storage)
        grant_rows = rights_module._grant_rows

        async def stamped_once(session: Any, *args: Any) -> Any:
            if len(sessions) == 1:
                await stamp(session, storage._host.tables, "carol")
            return await grant_rows(session, *args)

        monkeypatch.setattr(rights_module, "_grant_rows", stamped_once)
        result = await storage.write(entries=[Entry(path=Path("/g/new.txt"), content="n")], authority=BOB)
        assert result.success is True, result.errors
        assert len(sessions) == 2

    async def test_a_posture_write_moves_a_named_callers_basis(self, monkeypatch) -> None:
        """A posture write stamps everyone, and everyone is in a named caller's basis.

        Guards ``EVERYONE_NAME`` in the basis: left out, eve's write is never redriven by a posture write.
        """
        storage = InMemoryStorage()
        await label_world(storage)
        sessions = attempts(monkeypatch, storage)
        rival = clearing("write:before-apply", lambda: stamp(sessions[-1], storage._host.tables, "*"))
        with installed("write:before-apply", rival):
            result = await storage.write(entries=[Entry(path=Path("/p/new.txt"), content="n")], authority=EVE)
        assert result.success is True, result.errors
        assert len(sessions) == 2

    async def test_a_stamp_naming_another_principal_leaves_the_verb_alone(self, monkeypatch) -> None:
        """A stamp naming carol does not move bob's basis: a fence on the mount revision alone would redrive."""
        storage = InMemoryStorage()
        await grant_world(storage)
        sessions = attempts(monkeypatch, storage)
        seam_name, call = _verbs(storage)["write"]
        with installed(seam_name, clearing(seam_name, lambda: stamp(sessions[-1], storage._host.tables, "carol"))):
            result = await call()
        assert result.success is True, result.errors
        assert len(sessions) == 1

    async def test_a_caller_whose_own_grant_is_the_latest_admin_write_keeps_one_attempt(self, monkeypatch) -> None:
        """bob's stamp equals the revision his gate opens under, and the fence passes on equality.

        Guards the fence's strict comparison: ``>=`` redrives every attempt of bob's into a conflict.
        """
        storage = InMemoryStorage()
        await grant_world(storage)
        sessions = attempts(monkeypatch, storage)
        result = await storage.write(entries=[Entry(path=Path("/g/new.txt"), content="n")], authority=BOB)
        assert result.success is True, result.errors
        assert len(sessions) == 1

    async def test_an_admin_write_is_never_fenced(self, monkeypatch) -> None:
        """A grant by bob reads the revision and the stamps exactly as before, in one attempt.

        Guards the uncached gate's exemption: an admin write fenced reads
        ``vfs_meta`` 3 times and ``vfs_principal_revisions`` twice.
        """
        storage = InMemoryStorage()
        await grant_world(storage)
        assert (await storage.add_member(group="group:eng", member="bob", authority=SYSTEM)).success is True
        assert (await storage.stat(path=Path("/g/d"), authority=BOB)).success is True
        sessions = attempts(monkeypatch, storage)
        statements = _statements(storage)
        result = await storage.grant(path=Path("/g/d"), principal="group:eng", level="read", authority=BOB)
        assert result.success is True, result.errors
        assert len(sessions) == 1
        assert (_naming(statements, "vfs_meta"), _naming(statements, "vfs_principal_revisions")) == (2, 1)

    async def test_rights_that_keep_moving_end_in_one_retryable_conflict(self, monkeypatch) -> None:
        """A stamp naming bob inside every attempt exhausts the budget in the retryable conflict, nothing written."""
        storage = InMemoryStorage()
        await grant_world(storage)
        monkeypatch.setattr(storage._host, "_retry_base_delay", 0.0)
        sessions = attempts(monkeypatch, storage)
        seam_name, call = _verbs(storage)["write"]
        with installed(seam_name, lambda: stamp(sessions[-1], storage._host.tables, "bob")):
            result = await call()
        assert result.success is False
        assert [(error.kind, error.retryable, error.path) for error in result.errors] == [_CONFLICT]
        phrase = "write kept losing to concurrent changes: the caller's rights changed while it ran"
        assert result.errors[0].message.endswith(phrase)
        assert len(sessions) == 4
        assert await row_at(storage, "/g/new.txt") is None

    async def test_rows_that_keep_landing_end_in_one_retryable_conflict(self, monkeypatch) -> None:
        """A row beyond eve's rung landed in every attempt ends her delete in the retryable conflict, her rows live."""
        storage = InMemoryStorage()
        await drop_world(storage)
        monkeypatch.setattr(storage._host, "_retry_base_delay", 0.0)
        sessions = attempts(monkeypatch, storage)

        async def rival() -> None:
            await land(sessions[-1], storage._host.tables, f"/drop/e/sub/late{len(sessions)}.txt", "alice", "add")

        with installed("delete:post-collect", rival):
            result = await storage.delete(path=Path("/drop/e"), authority=EVE)
        assert result.success is False
        assert [(error.kind, error.retryable, error.path) for error in result.errors] == [_CONFLICT]
        phrase = "delete kept losing to concurrent changes: a row it acts on is beyond the caller's rights as it now"
        phrase += " stands"
        assert result.errors[0].message.endswith(phrase)
        assert len(sessions) == 4
        for path in ("/drop/e", "/drop/e/f.txt", "/drop/e/sub", "/drop/e/sub/g.txt"):
            row = await row_at(storage, path)
            assert row is not None and row["deleted_at"] is None


# ---------------------------------------------------------------------------
# Agreement with the gate
# ---------------------------------------------------------------------------


async def _agreement_world(storage: DatabaseStorage) -> None:
    """The drop world with a road for eve at ``/drop/h``, alice's deleted file beside eve's tree, and an edge."""
    await drop_world(storage)
    written = await storage.write(entries=[Entry(path=Path("/drop/h/pub/f.txt"), content="p")], parents=True)
    assert written.success is True
    assert (await storage.posture(path=Path("/drop/h"), posture="none", authority=SYSTEM)).success is True
    assert (await storage.posture(path=Path("/drop/h/pub"), posture="list", authority=SYSTEM)).success is True
    assert (await storage.write(entries=[Entry(path=Path("/drop/a.txt"), content="a")], authority=ALICE)).success
    assert (await storage.delete(path=Path("/drop/a.txt"), authority=ALICE)).success is True
    road = Edge(source=Path("/drop/e/f.txt"), target=Path("/drop/h"), edge_type="in")
    assert (await storage.mkedge(edges=[road], authority=SYSTEM)).success is True


async def _eves(storage: DatabaseStorage, *calls: Callable[[], Awaitable[Result]]) -> None:
    for call in calls:
        assert (await call()).success is True


def _agreement_calls(storage: DatabaseStorage, case: str) -> tuple[list[Any], Callable[[], Awaitable[Result]]]:
    """For *case*: eve's setup calls, then the widest call her gate admits with nothing changing underneath."""
    s, f, sub = storage, Path("/drop/e/f.txt"), Path("/drop/e/sub")
    road = Edge(source=f, target=Path("/drop/h"), edge_type="in")
    new = Edge(source=Path("/drop/e/sub/g.txt"), target=Path("/drop/h"), edge_type="in")
    cases: dict[str, tuple[list[Any], Callable[[], Awaitable[Result]]]] = {
        "write-overwrite": ([], lambda: s.write(entries=[Entry(path=f, content="e2")], authority=EVE)),
        "write-new-no-overwrite": (
            [],
            lambda: s.write(entries=[Entry(path=Path("/drop/e/n.txt"), content="n")], overwrite=False, authority=EVE),
        ),
        "write-parents": (
            [],
            lambda: s.write(entries=[Entry(path=Path("/drop/e/x/y/z.txt"), content="z")], parents=True, authority=EVE),
        ),
        "write-revive": (
            [lambda: s.delete(path=f, authority=EVE)],
            lambda: s.write(entries=[Entry(path=f, content="back")], authority=EVE),
        ),
        "edit": ([], lambda: s.edit(edits=[EditOperation(old="eve", new="edited")], path=f, authority=EVE)),
        "mkdir-parents": ([], lambda: s.mkdir(path=Path("/drop/e/m/n"), parents=True, authority=EVE)),
        "mkdir-exist-ok": ([], lambda: s.mkdir(path=sub, exist_ok=True, authority=EVE)),
        "mkedge-live-road": ([], lambda: s.mkedge(edges=[new], authority=EVE)),
        "mkedge-trash-road": (
            [lambda: s.delete(path=Path("/drop/h/pub"), authority=SYSTEM)],
            lambda: s.mkedge(edges=[new], authority=EVE),
        ),
        "rmedge-road": ([], lambda: s.rmedge(edges=[road], authority=EVE)),
        "delete-cascade": (
            [lambda: s.delete(path=Path("/drop/e/sub/g.txt"), authority=EVE)],
            lambda: s.delete(path=Path("/drop/e"), authority=EVE),
        ),
        "delete-no-cascade-emptied": (
            [
                lambda: s.write(entries=[Entry(path=Path("/drop/e/a.txt"), content="a")], authority=ALICE),
                lambda: s.delete(path=Path("/drop/e/a.txt"), authority=ALICE),
                lambda: s.delete(path=f, authority=EVE),
                lambda: s.delete(path=sub, authority=EVE),
            ],
            lambda: s.delete(path=Path("/drop/e"), cascade=False, authority=EVE),
        ),
        "restore": ([lambda: s.delete(path=f, authority=EVE)], lambda: s.restore(path=f, authority=EVE)),
        "move-with-a-deleted-descendant": (
            [lambda: s.delete(path=Path("/drop/e/sub/g.txt"), authority=EVE)],
            lambda: s.move(operations=[ResolvedPair(src=Path("/drop/e"), dest=Path("/drop/m"))], authority=EVE),
        ),
        "copy-with-a-deleted-descendant": (
            [lambda: s.delete(path=Path("/drop/e/sub/g.txt"), authority=EVE)],
            lambda: s.copy(operations=[ResolvedPair(src=Path("/drop/e"), dest=Path("/drop/c"))], authority=EVE),
        ),
        "sweep-with-a-deleted-descendant": (
            [lambda: s.delete(path=Path("/drop/e/sub/g.txt"), authority=EVE)],
            lambda: s.sweep(path=Path("/drop/e"), authority=EVE),
        ),
    }
    return cases[case]


_AGREEMENT_CASES = [
    "write-overwrite",
    "write-new-no-overwrite",
    "write-parents",
    "write-revive",
    "edit",
    "mkdir-parents",
    "mkdir-exist-ok",
    "mkedge-live-road",
    "mkedge-trash-road",
    "rmedge-road",
    "delete-cascade",
    "delete-no-cascade-emptied",
    "restore",
    "move-with-a-deleted-descendant",
    "copy-with-a-deleted-descendant",
    "sweep-with-a-deleted-descendant",
]


class TestGateAgreement:
    """A call the gate admits, with nothing changing underneath, is never refused by a judgment after the gate."""

    @pytest.mark.parametrize("case", _AGREEMENT_CASES)
    async def test_a_call_the_gate_admits_succeeds_in_one_attempt(self, monkeypatch, case: str) -> None:
        """A partial caller's widest admitted call of each verb, flags, a trashed neighbour, a road, runs once.

        Guards every judgment after the gate against disagreeing with it: a
        disagreement redrives the call into a retryable conflict that never clears.
        """
        storage = InMemoryStorage()
        await _agreement_world(storage)
        setup, call = _agreement_calls(storage, case)
        await _eves(storage, *setup)
        sessions = attempts(monkeypatch, storage)
        result = await call()
        assert result.success is True, result.errors
        assert len(sessions) == 1

    def test_every_mutating_verb_has_an_agreement_case(self) -> None:
        """Each data verb is named by at least one agreement case, so a new verb gains one."""
        assert {case.split("-")[0] for case in _AGREEMENT_CASES} == set(MUTATING_OPS)


# ---------------------------------------------------------------------------
# What it costs
# ---------------------------------------------------------------------------


class TestCost:
    """Two point reads per non-system mutation; no statement per row; the destination's rules, never its rows."""

    async def test_a_fenced_mutation_reads_the_revision_first_and_the_stamps_once_more(self) -> None:
        """bob's write reads ``vfs_meta`` once, first, and the stamps twice for his rights and twice for its label.

        A call that creates a row reads the everyone stamp before its label
        and again as its last statement, whoever makes it: four reads of
        the stamps for bob, two for the system actor, which the fence skips.

        Guards the opening read's place: moved after the resolve, an admin
        write could commit between what the compile read and what the fence compares.
        """
        storage = InMemoryStorage()
        await grant_world(storage)
        assert (await storage.stat(path=Path("/g/d"), authority=BOB)).success is True
        statements = _statements(storage)
        assert (await storage.write(entries=[Entry(path=Path("/g/new.txt"), content="n")], authority=BOB)).success
        assert (_naming(statements, "vfs_principal_revisions"), _naming(statements, "vfs_meta")) == (4, 1)
        begun = next(n for n, sql in enumerate(statements) if sql.startswith("BEGIN IMMEDIATE"))
        assert "vfs_meta" in statements[begun + 1]
        statements.clear()
        assert (await storage.write(entries=[Entry(path=Path("/g/sys.txt"), content="n")], authority=SYSTEM)).success
        assert (_naming(statements, "vfs_principal_revisions"), _naming(statements, "vfs_meta")) == (2, 0)
        statements.clear()
        assert (await storage.read(path=Path("/g/d/f.txt"), authority=BOB)).success is True
        assert (_naming(statements, "vfs_principal_revisions"), _naming(statements, "vfs_meta")) == (1, 0)

    @pytest.mark.slow
    async def test_a_ten_thousand_file_batch_pays_the_same_two_reads(self) -> None:
        """bob's 10,000-file write with parents reads ``vfs_meta`` once and the stamps four times, as one file does."""
        storage = InMemoryStorage()
        await grant_world(storage)
        assert (await storage.stat(path=Path("/g/d"), authority=BOB)).success is True
        entries = [Entry(path=Path(f"/g/bulk/d{n // 100:03}/f{n:05}.txt"), content="n") for n in range(10_000)]
        statements = _statements(storage)
        assert (await storage.write(entries=entries, parents=True, authority=BOB)).success is True
        assert (_naming(statements, "vfs_principal_revisions"), _naming(statements, "vfs_meta")) == (4, 1)

    async def test_the_judgments_issue_no_statement_where_nothing_landed(self, monkeypatch) -> None:
        """The landing read runs only for a landed create; delete's second subtree read costs what its gate's does."""
        storage, drop, labels = InMemoryStorage(), InMemoryStorage(), InMemoryStorage()
        await grant_world(storage)
        await drop_world(drop)
        await label_world(labels)
        statements = _statements(drop, _statements(storage))
        landed = _while(monkeypatch, writes_module, "admit_landed", statements)
        staged = _while(monkeypatch, writes_module, "admit_staged", statements)
        assert (await storage.write(entries=[Entry(path=Path("/g/new.txt"), content="n")], authority=BOB)).success
        assert (landed, staged) == ([0], [0])
        sessions = attempts(monkeypatch, drop)
        tables = drop._host.tables
        rival = clearing("write:before-apply", lambda: land(sessions[-1], tables, "/drop/x.txt", "alice", "add"))
        with installed("write:before-apply", rival):
            assert (await drop.write(entries=[Entry(path=Path("/drop/x.txt"), content="bob")], authority=BOB)).success
        assert (landed[1], staged[1]) == (1, 0)
        for store, who, path, expected in ((labels, EVE, "/p/d", 2), (storage, BOB, "/g/d", 0)):
            recorded = _statements(store)
            assert (await store.delete(path=Path(path), authority=who)).success is True
            paged = [sql for sql in recorded if "FROM vfs_entries" in sql and "ORDER BY vfs_entries.path" in sql]
            assert sum(1 for sql in paged if "LIMIT" in sql) == expected

    async def test_the_grants_listing_pays_no_opening_read(self) -> None:
        """A read of the grant rows is never fenced, so it reads no mount revision: the cached resolve alone.

        Guards the fence's mark on the session: without it, every cached gate
        reads ``vfs_meta`` first, the listing verb included.
        """
        storage = InMemoryStorage()
        await grant_world(storage)
        assert (await storage.grants(path=Path("/g"), authority=BOB)).success is True
        statements = _statements(storage)
        assert (await storage.grants(path=Path("/g"), authority=BOB)).success is True
        assert _naming(statements, "vfs_meta") == 0

    async def test_a_transfer_reads_each_destinations_posture_once(self) -> None:
        """A partial caller's transfer reads a pair's destination posture rows once, at its gate, never again.

        Guards the posture rows the gate carries on the attempt: dropped, each
        pair re-reads them, two more statements a pair of the batch.
        """
        storage = InMemoryStorage()
        files = [Entry(path=Path(f"/src/f{n}.txt"), content="f") for n in range(10)]
        files.append(Entry(path=Path("/dst"), kind="directory"))
        assert (await storage.write(entries=files, parents=True, authority=SYSTEM)).success is True
        await _postures(storage, [("/", "none"), ("/src", "read_write"), ("/dst", "add")])
        reads: list[int] = []
        for width in (1, 10):
            pairs = [ResolvedPair(src=Path(f"/src/f{n}.txt"), dest=Path(f"/dst/w{width}/{n}")) for n in range(width)]
            assert (await storage.mkdir(path=Path(f"/dst/w{width}"), authority=EVE)).success is True
            statements = _statements(storage)
            assert (await storage.copy(operations=pairs, authority=EVE)).success is True
            reads.append(_naming(statements, "vfs_grants"))
        assert reads[1] - reads[0] == 2 * 9

    @pytest.mark.parametrize("size", [10, 1000, pytest.param(10_000, marks=pytest.mark.slow)])
    async def test_the_destination_judgment_reads_rules_never_rows(self, monkeypatch, size: int) -> None:
        """The destination judgment's statements follow the rules beneath the destination, never the rows copied.

        Guards the shape of ``admit_destinations``: the stamp watch and two
        posture reads, then one probe per chunk of the closed region's
        pieces, or none at all.
        """
        storage = await _gate_world(size)
        statements = _statements(storage)
        counts = _while(monkeypatch, backend_module, "admit_destinations", statements)

        async def calls(who: Authority) -> list[Result]:
            pair = [ResolvedPair(src=Path("/src"), dest=Path("/dst/c"))]
            copied = await storage.copy(operations=pair, authority=who)
            return [copied, await storage.move(operations=pair, authority=who)]

        await calls(EVE)
        assert counts == [3, 3]
        await _postures(storage, [("/dst/c/x001", "none")])
        await calls(EVE)
        assert counts[2:] == [4, 4]
        await _postures(storage, [*((f"/dst/c/x{n:03}", "none") for n in range(2, 100)), ("/dst/c/d0", "none")])
        refused = await calls(EVE)
        assert counts[4:] == [4, 4]
        assert [[(error.kind, error.path) for error in result.errors] for result in refused] == [
            [(ErrorKind.permission_denied, "/dst/c/d0")]
        ] * 2
        await _postures(storage, [("/dst/c/d0", "add")])
        await calls(EVE)
        assert counts[6:] == [4, 4]
        granted = await storage.grant(path=Path("/dst"), principal="dan", level="add", authority=SYSTEM)
        assert granted.success is True
        await calls(SYSTEM)
        await calls(DAN)
        assert counts[8:] == [0, 0, 0, 0]

    @pytest.mark.slow
    async def test_the_destination_probe_seeks_each_piece_and_never_passes_over_the_source(self, tmp_path) -> None:
        """Each arm of the probe is one seek of the path index; its work is the same at 10,000 and 20,000 rows.

        Guards the per-piece form: one statement ORing the pieces over the
        source's range plans as a single seek and filters every source row.
        Measured with planner statistics and with none, as in memory or on an
        old SQLite: a bare tombstone term there plans each arm on the
        ``deleted_at`` index, a pass over every live row of the mount.
        """
        storage = await _gate_world(10_000, url=_url(tmp_path))
        await _postures(storage, [(f"/dst/c/x{n:03}", "none") for n in range(100)])
        database = storage._host.engine.url.database
        assert database is not None
        steps: dict[str, list[dict[str, int]]] = {"analysed": [], "none": []}
        # Off the loop: the backend's own statistics pass may hold the file's writer, and must run to release it.
        await asyncio.to_thread(_on_file, database, "ANALYZE")
        for _ in range(2):
            probes = await _probes(storage)
            for state in ("analysed", "none"):
                if state == "none":
                    await asyncio.to_thread(_on_file, database, "DROP TABLE IF EXISTS sqlite_stat1")
                measured: dict[str, int] = {}
                for verb, (sql, parameters) in probes.items():
                    plan = await asyncio.to_thread(_plan, database, sql, parameters)
                    seeks = [line for line in plan if line.startswith("SEARCH vfs_entries USING")]
                    assert sum(1 for line in seeks if "ix_vfs_entries_path" in line) == 200, (state, verb)
                    assert not any(line.startswith("SCAN vfs_entries") for line in plan)
                    measured[verb] = await asyncio.to_thread(_steps, database, sql, parameters)
                steps[state].append(measured)
            more = [Entry(path=Path(f"/src/e{n % 10}/f{n}.txt"), content="f") for n in range(10_000)]
            assert (await storage.write(entries=more, parents=True, authority=SYSTEM)).success is True
            await asyncio.to_thread(_on_file, database, "ANALYZE")
        assert steps["analysed"][0] == steps["analysed"][1]
        assert steps["none"][0] == steps["none"][1]
        await storage.close()


async def _gate_world(size: int, *, url: str | None = None) -> DatabaseStorage:
    """The destination world at *size* source rows: eve reaches ``/src`` and ``/dst`` by the posture alone.

    ``/dst/c`` stands, so every transfer into it ends at the ladder's
    ``exists`` once the gate has judged it and copies no row.
    """
    storage = InMemoryStorage() if url is None else DatabaseStorage(url=url)
    entries = [Entry(path=Path(f"/src/d{n % 10}/f{n}.txt"), content="f") for n in range(size)]
    entries.append(Entry(path=Path("/dst/c"), kind="directory"))
    assert (await storage.write(entries=entries, parents=True, authority=SYSTEM)).success is True
    await _postures(storage, [("/", "none"), ("/src", "read_write"), ("/dst", "add")])
    return storage


async def _postures(storage: DatabaseStorage, rows: list[tuple[str, Any]]) -> None:
    for path, level in rows:
        assert (await storage.posture(path=Path(path), posture=level, authority=SYSTEM)).success is True


async def _probes(storage: DatabaseStorage) -> dict[str, tuple[str, tuple[Any, ...]]]:
    """The probe statement eve's copy and her move each issue, as the driver received it."""
    seen: list[tuple[str, tuple[Any, ...]]] = []
    pair = [ResolvedPair(src=Path("/src"), dest=Path("/dst/c"))]

    def record(conn, cursor, statement, parameters, context, executemany) -> None:
        if "UNION ALL" in statement:
            seen.append((statement, tuple(parameters)))

    event.listen(storage._host.engine.sync_engine, "before_cursor_execute", record)
    try:
        await storage.copy(operations=pair, authority=EVE)
        await storage.move(operations=pair, authority=EVE)
    finally:
        event.remove(storage._host.engine.sync_engine, "before_cursor_execute", record)
    assert len(seen) == 2
    return dict(zip(("copy", "move"), seen, strict=True))


def _on_file(database: str, sql: str) -> None:
    """Run one statement on the store's file beside the backend, waiting out the backend's own writer."""
    with sqlite3.connect(database, timeout=30) as connection:
        connection.execute(sql)


def _plan(database: str, sql: str, parameters: tuple[Any, ...]) -> list[str]:
    with sqlite3.connect(database, timeout=30) as connection:
        return [row[3] for row in connection.execute(f"EXPLAIN QUERY PLAN {sql}", parameters)]


def _steps(database: str, sql: str, parameters: tuple[Any, ...]) -> int:
    """Hundreds of SQLite virtual-machine steps the statement takes: an operation count, never a clock."""
    ticks = [0]

    def tick() -> int:
        ticks[0] += 1
        return 0

    with sqlite3.connect(database, timeout=30) as connection:
        connection.set_progress_handler(tick, 100)
        connection.execute(sql, parameters).fetchall()
    return ticks[0]


# ---------------------------------------------------------------------------
# The windows SQLite and the in-memory host keep shut
# ---------------------------------------------------------------------------


class TestClosedWindows:
    """A genuine rival started inside the window commits after the verb, so the verb's attempt holds alone."""

    @pytest.mark.parametrize("backend", ["memory", "sqlite"])
    @pytest.mark.parametrize("window", ["landing", "late-row", "revoke"])
    async def test_a_rival_inside_the_window_commits_after_the_verb(
        self, tmp_path, monkeypatch, backend: str, window: str
    ) -> None:
        """The write lock and the host lock keep every rival out of an attempt: it is ordered after the verb."""
        url = _url(tmp_path)
        storage = InMemoryStorage() if backend == "memory" else DatabaseStorage(url=url)
        second = storage if backend == "memory" else DatabaseStorage(url=url)
        world = {"landing": drop_world, "late-row": drop_world, "revoke": grant_world}[window]
        await world(storage)
        sessions = attempts(monkeypatch, storage)
        tasks: list[asyncio.Future[Result]] = []
        x, late, new = Path("/drop/x.txt"), Path("/drop/e/sub/late.txt"), Path("/g/new.txt")
        windows: dict[str, tuple[str, Callable[[], Awaitable[Result]], Callable[[], Awaitable[Result]]]] = {
            "landing": (
                "write:before-snapshot",
                lambda: second.write(entries=[Entry(path=x, content="alice")], authority=ALICE),
                lambda: storage.write(entries=[Entry(path=x, content="bob")], authority=BOB),
            ),
            "late-row": (
                "delete:post-collect",
                lambda: second.write(entries=[Entry(path=late, content="a")], authority=ALICE),
                lambda: storage.delete(path=Path("/drop/e"), authority=EVE),
            ),
            "revoke": (
                "write:before-apply",
                lambda: second.revoke(path=Path("/g"), principal="bob", authority=SYSTEM),
                lambda: storage.write(entries=[Entry(path=new, content="n")], authority=BOB),
            ),
        }
        seam_name, rival, verb = windows[window]

        async def start() -> None:
            tasks.append(asyncio.ensure_future(rival()))

        with installed(seam_name, clearing(seam_name, start)):
            result = await verb()
        assert result.success is True, result.errors
        assert len(sessions) == 1
        later = await tasks[0]
        if window == "landing":
            row = await row_at(storage, "/drop/x.txt")
            assert row is not None and (row["owner_id"], row["version"]) == ("bob", 1)
            assert [(error.kind, str(error.path)) for error in later.errors] == [(ErrorKind.permission_denied, x)]
        elif window == "late-row":
            assert [error.kind for error in later.errors] == [ErrorKind.not_found]
        else:
            assert later.success is True, later.errors
            assert await row_at(storage, "/g/new.txt") is not None
        if second is not storage:
            await second.close()
        await storage.close()
