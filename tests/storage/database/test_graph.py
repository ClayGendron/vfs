"""The graph walk against real sqlite rows: the rights cut on every hop under both predicate
forms, the ``list`` pass, the road probe, the anonymous seed, the statement counts the frontier walk
declares (10,000 seeds, the cycle bomb, the early stop), the join pin on the hop statement, and
parity with the readable oracles on random digraphs.
"""

from __future__ import annotations

import math
import random
from contextlib import contextmanager
from dataclasses import replace
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import event
from sqlalchemy.dialects import mssql, mysql, sqlite

from tests.support.oracles import graph_walk, meeting_subgraph
from vfs.authority import Authority, Principal
from vfs.models import Edge, Entry, Observation
from vfs.models.rows import build_vfs_tables
from vfs.paths import Path
from vfs.results import ErrorKind, Result, Severity
from vfs.storage.backends.database.dialects import PROFILES
from vfs.storage.backends.database.engine import EngineHost
from vfs.storage.backends.database.graph import GraphRequest, Site, hop_statement
from vfs.storage.backends.memory import InMemoryStorage

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

SYSTEM = Authority.system()
BOB = Authority.of(Principal("bob"))
ANON = Authority.anonymous()

CHAIN = ("/w/a.md", "/w/b.md", "/w/c.md")


@pytest.fixture
async def storage() -> AsyncIterator[InMemoryStorage]:
    storage = InMemoryStorage()
    yield storage
    await storage.close()


class Recorded:
    """Every statement one block issued, with its bind count."""

    def __init__(self) -> None:
        self.statements: list[tuple[str, int]] = []

    def edges(self) -> list[str]:
        return [text for text, _binds in self.statements if "vfs_edges" in text]

    def hops(self) -> list[str]:
        return [text for text in self.edges() if "vfs_entries" in text]

    def probes(self) -> list[str]:
        """The directories-only road probes: hop statements filtered on the far node's kind."""
        return [text for text in self.hops() if "vfs_entries.kind = " in text]

    def seeds(self) -> list[str]:
        return [
            text
            for text, _binds in self.statements
            if "vfs_edges" not in text and "vfs_entries" in text and " IN " in text
        ]


@contextmanager
def recording(storage: InMemoryStorage) -> Iterator[Recorded]:
    recorded = Recorded()

    def record(conn, cursor, statement, parameters, context, executemany) -> None:
        binds = len(parameters) if isinstance(parameters, (tuple, list, dict)) else 0
        recorded.statements.append((statement, binds))

    engine = storage._host.engine.sync_engine
    event.listen(engine, "before_cursor_execute", record)
    try:
        yield recorded
    finally:
        event.remove(engine, "before_cursor_execute", record)


async def _chain(storage: InMemoryStorage) -> None:
    """``a → b → c`` under ``/w``, written as the system actor, every edge weighted."""
    entries = [Entry(path=Path(path), content="x") for path in CHAIN]
    assert (await storage.write(entries=entries, parents=True, authority=SYSTEM)).success is True
    edges = [
        Edge(source=Path(CHAIN[0]), target=Path(CHAIN[1]), edge_type="imports", weight=1.0, distance=0.5),
        Edge(source=Path(CHAIN[1]), target=Path(CHAIN[2]), edge_type="imports", weight=2.0, distance=0.25),
    ]
    assert (await storage.mkedge(edges=edges, authority=SYSTEM)).success is True


def _nodes(result: Result) -> dict[str, int]:
    return {str(o.path): o.depth or 0 for o in result.observations if o.edge_target is None}


def _edges(result: Result) -> set[tuple[str, str, str]]:
    return {
        (str(o.path), str(o.edge_target), str(o.edge_type)) for o in result.observations if o.edge_target is not None
    }


# ---------------------------------------------------------------------------
# Rights on every hop
# ---------------------------------------------------------------------------


class TestRights:
    async def test_a_hidden_middle_node_cuts_the_walk_under_the_join(self, storage: InMemoryStorage) -> None:
        # Mutant: judge rows after the loop — c would be reached through b.
        await _chain(storage)
        assert (await storage.posture(path=Path("/"), posture="none", authority=SYSTEM)).success is True
        for path in (CHAIN[0], CHAIN[2]):
            assert (await storage.grant(path=Path(path), principal="bob", level="read", authority=SYSTEM)).success
        cut = await storage.graph(method="outbound", path=Path(CHAIN[0]), depth=None, authority=BOB)
        assert cut.success is True and _nodes(cut) == {CHAIN[0]: 0} and _edges(cut) == set()
        whole = await storage.graph(method="outbound", path=Path(CHAIN[0]), depth=None, authority=SYSTEM)
        assert _nodes(whole) == {CHAIN[0]: 0, CHAIN[1]: 1, CHAIN[2]: 2}

    async def test_a_hidden_middle_node_cuts_the_walk_under_the_clause_fan(
        self, storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The generic floor: no range source and a starved bind budget, so
        # the view is several clauses merged per hop. Same answer.
        await _chain(storage)
        assert (await storage.posture(path=Path("/"), posture="none", authority=SYSTEM)).success is True
        for path in (CHAIN[0], CHAIN[2], "/w/other.md"):
            assert (await storage.write(entries=[Entry(path=Path(path), content="x")], authority=SYSTEM)).success
            assert (await storage.grant(path=Path(path), principal="bob", level="read", authority=SYSTEM)).success
        with recording(storage) as joined:
            assert _nodes(await storage.graph(method="outbound", path=Path(CHAIN[0]), authority=BOB)) == {CHAIN[0]: 0}
        unjoined = replace(storage._host.profile, range_source=None)
        monkeypatch.setattr(EngineHost, "profile", property(lambda _self: unjoined))
        monkeypatch.setattr(EngineHost, "parameter_budget", property(lambda _self: 56))
        with recording(storage) as fanned:
            cut = await storage.graph(method="outbound", path=Path(CHAIN[0]), depth=None, authority=BOB)
        assert cut.success is True and _nodes(cut) == {CHAIN[0]: 0}
        assert len(fanned.hops()) > len(joined.hops())
        whole = await storage.graph(method="outbound", path=Path(CHAIN[0]), depth=None, authority=SYSTEM)
        assert _nodes(whole) == {CHAIN[0]: 0, CHAIN[1]: 1, CHAIN[2]: 2}

    async def test_a_list_node_is_passed_and_returned_bare(self, storage: InMemoryStorage) -> None:
        # Mutant: build the view at read — b would be dropped in SQL and c
        # never reached, while the leak test above still passed.
        await _chain(storage)
        assert (await storage.posture(path=Path("/"), posture="none", authority=SYSTEM)).success is True
        for path, level in ((CHAIN[0], "read"), (CHAIN[1], "list"), (CHAIN[2], "read")):
            assert (await storage.grant(path=Path(path), principal="bob", level=level, authority=SYSTEM)).success
        result = await storage.graph(method="outbound", path=Path(CHAIN[0]), depth=None, authority=BOB)
        assert _nodes(result) == {CHAIN[0]: 0, CHAIN[1]: 1, CHAIN[2]: 2}
        rows = {str(o.path): o for o in result.observations if o.edge_target is None}
        assert rows[CHAIN[1]].populated == {"path", "kind", "depth"} and rows[CHAIN[1]].kind == "file"
        assert rows[CHAIN[0]].populated > {"path", "kind", "depth", "version"}
        edges = {(str(o.path), str(o.edge_target)): o for o in result.observations if o.edge_target is not None}
        for key in ((CHAIN[0], CHAIN[1]), (CHAIN[1], CHAIN[2])):
            assert edges[key].edge_weight is None and edges[key].edge_distance is None
            assert edges[key].populated == {"path", "edge_target", "edge_type"}
        whole = await storage.graph(method="outbound", path=Path(CHAIN[0]), depth=None, authority=SYSTEM)
        measured = next(o for o in whole.observations if o.edge_target == CHAIN[1])
        assert measured.edge_weight == 1.0 and measured.edge_distance == 0.5

    async def test_a_road_directory_is_passed_as_a_bare_node(self, storage: InMemoryStorage) -> None:
        # Mutant: skip the road probe — the walk over fs would stop at the
        # root while tree reaches the granted file.
        entries = [Entry(path=Path("/r/deep/file.md"), content="x"), Entry(path=Path("/r/other.md"), content="x")]
        assert (await storage.write(entries=entries, parents=True, authority=SYSTEM)).success is True
        assert (await storage.posture(path=Path("/"), posture="none", authority=SYSTEM)).success is True
        assert (
            await storage.grant(path=Path("/r/deep/file.md"), principal="bob", level="read", authority=SYSTEM)
        ).success
        with recording(storage) as recorded:
            walked = await storage.graph(
                method="outbound", path=Path("/"), edge_types=("fs",), depth=None, authority=BOB
            )
        assert _nodes(walked) == {"/": 0, "/r": 1, "/r/deep": 2, "/r/deep/file.md": 3}
        rows = {str(o.path): o for o in walked.observations if o.edge_target is None}
        assert rows["/r"].populated == rows["/r/deep"].populated == {"path", "kind", "depth"}
        assert rows["/r/deep/file.md"].populated > {"path", "kind", "depth"}
        assert _edges(walked) == {("/", "/r", "fs"), ("/r", "/r/deep", "fs"), ("/r/deep", "/r/deep/file.md", "fs")}
        treed = await storage.tree(path=Path("/"), authority=BOB)
        assert {str(o.path) for o in treed.observations} | {"/"} == set(_nodes(walked))
        # one directories-only probe rides each of the four hops under the partial named view
        assert len(recorded.probes()) == 4 and len(recorded.hops()) == 8

    async def test_anonymous_is_judged_at_the_seed_at_list(self, storage: InMemoryStorage) -> None:
        # A list posture lets anonymous walk and see bare nodes; a none
        # posture refuses the seed before any row is read.
        await _chain(storage)
        assert (await storage.posture(path=Path("/"), posture="none", authority=SYSTEM)).success is True
        assert (await storage.posture(path=Path("/w"), posture="list", authority=SYSTEM)).success is True
        with recording(storage) as recorded:
            bare = await storage.graph(method="outbound", path=Path(CHAIN[0]), depth=None, authority=ANON)
        assert _nodes(bare) == {CHAIN[0]: 0, CHAIN[1]: 1, CHAIN[2]: 2}
        assert all(o.populated == {"path", "kind", "depth"} for o in bare.observations if o.edge_target is None)
        assert recorded.probes() == [] and len(recorded.hops()) == 3  # anonymous derives no road: no probe
        assert (await storage.write(entries=[Entry(path=Path("/x.md"), content="x")], authority=SYSTEM)).success
        refused = await storage.graph(method="outbound", path=Path("/x.md"), authority=ANON)
        assert refused.success is False and refused.errors[0].kind == ErrorKind.unauthenticated


# ---------------------------------------------------------------------------
# Statements — what the walk issues, never how long it takes
# ---------------------------------------------------------------------------


class TestStatements:
    def test_the_hop_statement_carries_the_profiles_join_keyword(self) -> None:
        # The planner pin: a plain JOIN let SQLite drive from the tombstone
        # index (8.2 s for 1,000 seeds); the profile's keyword fixes it.
        tables = build_vfs_tables()
        request = GraphRequest("outbound", 1, (), (), False, None, frozenset({"path", "kind"}))
        for name, dialect, keyword in (
            ("sqlite", sqlite.dialect(), "CROSS JOIN"),
            ("mssql", mssql.dialect(), "INNER LOOP JOIN"),
            ("mariadb", mysql.dialect(), "STRAIGHT_JOIN"),
        ):
            site = Site(tables, PROFILES[name], 1_000)
            stmt = hop_statement(site, request, "outbound", ["x", "y"], [tables.entry.c.path, tables.entry.c.kind])
            text = str(stmt.compile(dialect=dialect))
            assert f"vfs_edges {keyword} vfs_entries ON vfs_entries.entry_id = vfs_edges.target_id" in text
            assert "vfs_edges.edge_type != " in text  # the default never follows fs

    async def test_a_type_list_beyond_half_the_budget_is_invalid(self, storage: InMemoryStorage) -> None:
        await _chain(storage)
        budget = storage._host.membership_budget
        too_many = tuple(f"t{n}" for n in range(budget // 2 + 1))
        refused = await storage.graph(method="outbound", path=Path(CHAIN[0]), edge_types=too_many)
        assert refused.success is False and refused.errors[0].kind == ErrorKind.invalid
        fine = await storage.graph(method="outbound", path=Path(CHAIN[0]), edge_types=too_many[:-1])
        assert fine.success is True

    async def test_the_walk_stops_at_limit_before_the_next_hop(self, storage: InMemoryStorage) -> None:
        # Mutant: drop the early stop — a second hop statement would run.
        await _chain(storage)
        with recording(storage) as recorded:
            result = await storage.graph(method="outbound", path=Path(CHAIN[0]), depth=None, limit=2)
        assert _nodes(result) == {CHAIN[0]: 0, CHAIN[1]: 1}
        assert len(recorded.hops()) == 1
        assert result.errors[0].data == {"limit": 2, "nodes_found": 2, "depth_reached": 1}

    @pytest.mark.slow
    @pytest.mark.parametrize("budget", [None, 1_000], ids=["sqlite", "in_list_budget=1000"])
    async def test_ten_thousand_seeds_issue_the_declared_statement_count(
        self, storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch, budget: int | None
    ) -> None:
        # ceil(S / B) seed statements, Σ_h ceil(|F_h| / B) hop statements,
        # ceil(|U| / B) induced statements; no statement over the bind cap.
        # Mutant: fetch the induced edges unchunked.
        count = 10_000
        seeds = [f"/s/{n:05}.md" for n in range(count)]
        targets = [f"/t/{n:05}.md" for n in range(count)]
        entries = [Entry(path=Path(path), content="x") for path in (*seeds, *targets)]
        assert (await storage.write(entries=entries, parents=True)).success is True
        edges = [Edge(source=Path(seeds[n]), target=Path(targets[n]), edge_type="imports") for n in range(count)]
        edges += [
            Edge(source=Path(targets[n]), target=Path(targets[n + 1]), edge_type="imports") for n in range(count - 1)
        ]
        assert (await storage.mkedge(edges=edges)).success is True
        if budget is not None:
            narrowed = replace(storage._host.profile, in_list_budget=budget)
            monkeypatch.setattr(EngineHost, "profile", property(lambda _self: narrowed))
        chunk = storage._host.membership_budget
        cap = storage._host.parameter_budget
        rows = [Observation(path=Path(path)) for path in seeds]
        for depth, frontiers, unexpanded in ((1, [count], count), (2, [count, count], 0)):
            with recording(storage) as recorded:
                result = await storage.graph(method="outbound", observations=rows, depth=depth, limit=None)
            assert result.success is True and len(_nodes(result)) == 2 * count
            expected_hops = sum(math.ceil(size / chunk) for size in frontiers) + math.ceil(unexpanded / chunk)
            assert len(recorded.seeds()) == math.ceil(count / chunk)
            assert len(recorded.edges()) == expected_hops
            assert all(binds <= cap for _text, binds in recorded.statements)

    @pytest.mark.slow
    async def test_the_cycle_bomb_issues_two_hop_statements_at_any_depth(self, storage: InMemoryStorage) -> None:
        # A 200-node fully connected cluster: the second hop finds nothing
        # new and the walk stops; every node was expanded, so no induced
        # fetch runs. The recursive statement would enumerate 1.58 billion paths.
        nodes = [f"/k/{n:03}.md" for n in range(200)]
        assert (await storage.write(entries=[Entry(path=Path(p), content="x") for p in nodes], parents=True)).success
        edges = [Edge(source=Path(a), target=Path(b), edge_type="calls") for a in nodes for b in nodes if a != b]
        assert (await storage.mkedge(edges=edges)).success is True
        with recording(storage) as recorded:
            result = await storage.graph(method="outbound", path=Path(nodes[0]), depth=4, limit=None)
        assert len(_nodes(result)) == 200 and len(_edges(result)) == 199 * 200
        assert len(recorded.seeds()) == 1 and len(recorded.edges()) == 2

    @pytest.mark.slow
    async def test_meet_stops_when_the_seeds_join(self, storage: InMemoryStorage) -> None:
        # 1,000 seeds, each two hops from one hub: the hub is claimed on the
        # second hop and every other seed meets it there; no third hop runs.
        # Mutant: drop the connected check.
        count = 1_000
        seeds = [f"/q/s{n:04}.md" for n in range(count)]
        middles = [f"/q/m{n:04}.md" for n in range(count)]
        entries = [Entry(path=Path(p), content="x") for p in (*seeds, *middles, "/q/hub.md")]
        assert (await storage.write(entries=entries, parents=True)).success is True
        edges = [Edge(source=Path(seeds[n]), target=Path(middles[n]), edge_type="r") for n in range(count)]
        edges += [Edge(source=Path(middles[n]), target=Path("/q/hub.md"), edge_type="r") for n in range(count)]
        assert (await storage.mkedge(edges=edges)).success is True
        rows = [Observation(path=Path(path)) for path in seeds]
        with recording(storage) as recorded:
            result = await storage.graph(method="meet", observations=rows, depth=None, limit=None)
        assert result.success is True and result.errors == []
        assert len(_nodes(result)) == 2 * count + 1 and len(_edges(result)) == 2 * count
        # two hops by two directions by one chunk, plus the induced fetch of the one unexpanded node (two directions)
        assert len(recorded.hops()) == 4 and len(recorded.edges()) == 6


# ---------------------------------------------------------------------------
# Parity with the oracles on random digraphs
# ---------------------------------------------------------------------------


def _random_graph(rng: random.Random, size: int = 12) -> tuple[list[str], list[tuple[str, str, str]]]:
    nodes = [f"/n/{n:02}.md" for n in range(size)]
    edges: set[tuple[str, str, str]] = set()
    for _ in range(2 * size):
        source, target = rng.sample(nodes, 2)
        edges.add((source, target, rng.choice(("imports", "refs"))))
    return nodes, sorted(edges)


async def _agree(seed: int) -> None:
    rng = random.Random(seed)
    nodes, edges = _random_graph(rng)
    storage = InMemoryStorage()
    try:
        assert (await storage.write(entries=[Entry(path=Path(p), content="x") for p in nodes], parents=True)).success
        rows = [Edge(source=Path(s), target=Path(t), edge_type=k) for s, t, k in edges]
        assert (await storage.mkedge(edges=rows)).success is True
        method = rng.choice(("outbound", "inbound", "neighborhood"))
        depth = rng.choice((1, 2, 3, None))
        start = rng.sample(nodes, rng.choice((1, 2)))
        walked = await storage.graph(
            method=method, observations=[Observation(path=Path(p)) for p in start], depth=depth, limit=None
        )
        expected = graph_walk.walk(edges, start, method, depth)
        assert _nodes(walked) == expected, (seed, method, depth, start)
        assert _edges(walked) == graph_walk.induced(edges, expected), (seed, method, depth, start)
        meeters = rng.sample(nodes, rng.choice((2, 3)))
        for minimal in (False, True):
            met = await storage.graph(
                method="meet",
                observations=[Observation(path=Path(p)) for p in meeters],
                depth=None,
                limit=None,
                minimal=minimal,
            )
            reference = meeting_subgraph.meet(edges, meeters, minimal=minimal)
            assert _nodes(met) == reference.depths, (seed, meeters, minimal)
            assert _edges(met) == graph_walk.induced(edges, reference.depths), (seed, meeters, minimal)
            records = [e for e in met.errors if e.severity == Severity.info]
            assert bool(records) == (reference.components > 1), (seed, meeters)
    finally:
        await storage.close()


@pytest.mark.parametrize("seed", range(12))
async def test_the_walk_and_the_meeting_agree_with_the_oracles(seed: int) -> None:
    await _agree(seed)


@pytest.mark.slow
@pytest.mark.parametrize("seed", range(12, 200))
async def test_two_hundred_random_digraphs_agree_with_the_oracles(seed: int) -> None:
    await _agree(seed)


# ---------------------------------------------------------------------------
# Pruning
# ---------------------------------------------------------------------------


async def test_minimal_strips_the_leaf_a_removal_leaves_behind(storage: InMemoryStorage) -> None:
    # a→n→o→m→b and a→x→m join a and b twice; x→c makes x a bridge too.
    # n is the lowest-path non-articulation node: dropping it leaves o
    # hanging off m alone, and the strip takes o with it.
    # Mutant: strip once instead of to the fixed point.
    nodes = {name: f"/z/{name}.md" for name in "abcnomx"}
    assert (
        await storage.write(entries=[Entry(path=Path(p), content="x") for p in nodes.values()], parents=True)
    ).success
    edges = [("a", "n"), ("n", "o"), ("o", "m"), ("m", "b"), ("a", "x"), ("x", "c"), ("x", "m")]
    rows = [Edge(source=Path(nodes[s]), target=Path(nodes[t]), edge_type="r") for s, t in edges]
    assert (await storage.mkedge(edges=rows)).success is True
    seeds = [Observation(path=Path(nodes[name])) for name in "abc"]
    both = await storage.graph(method="meet", observations=seeds, depth=None, limit=None)
    minimal = await storage.graph(method="meet", observations=seeds, depth=None, limit=None, minimal=True)
    assert set(_nodes(both)) == set(nodes.values())
    assert set(_nodes(minimal)) == {nodes[name] for name in "abcmx"}
    triples = [(nodes[s], nodes[t], "r") for s, t in edges]
    names = [nodes[name] for name in "abc"]
    assert _nodes(both) == meeting_subgraph.meet(triples, names).depths
    assert _nodes(minimal) == meeting_subgraph.meet(triples, names, minimal=True).depths


# ---------------------------------------------------------------------------
# Seeds and columns
# ---------------------------------------------------------------------------


async def test_an_observation_seed_contributes_its_path_and_columns_narrow_the_rows(storage: InMemoryStorage) -> None:
    # An edge row from a previous answer seeds from its source; columns
    # select the fields a whole node carries, never a body.
    await _chain(storage)
    seed = Observation(path=Path(CHAIN[0]), edge_target=Path(CHAIN[1]), edge_type="imports")
    result = await storage.graph(method="outbound", observations=[seed], columns=frozenset({"size_bytes", "content"}))
    assert _nodes(result) == {CHAIN[0]: 0, CHAIN[1]: 1}
    rows = [o for o in result.observations if o.edge_target is None]
    assert all(o.populated == {"path", "kind", "version", "size_bytes", "depth"} for o in rows)
    assert all(o.content is None and o.size_bytes == 1 for o in rows)
