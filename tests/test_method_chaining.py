"""Tests that method chaining preserves prior details through the routing layer.

Every public method that accepts ``candidates`` routes through
``_dispatch_candidates`` which calls ``inject_details`` to prepend
prior details from the incoming candidates onto overlapping result
candidates.  These tests verify that contract end-to-end.
"""

from __future__ import annotations

import pytest

from grover.backends.database import DatabaseFileSystem
from grover.results import Candidate, Detail, GroverResult

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _prior(operation: str = "prior_op", score: float = 0.5) -> Detail:
    return Detail(operation=operation, score=score)


def _cands_with_prior(
    *paths: str,
    operation: str = "prior_op",
    score: float = 0.5,
) -> GroverResult:
    """Build candidates with a single prior detail on each."""
    d = _prior(operation, score)
    return GroverResult(candidates=[Candidate(path=p, details=(d,)) for p in paths])


def _detail_ops(candidate: Candidate) -> list[str]:
    """Extract operation names from a candidate's detail chain."""
    return [d.operation for d in candidate.details]


def _node_candidates(result: GroverResult) -> GroverResult:
    """Filter out connection candidates from a subgraph result."""
    return GroverResult(candidates=[
        c for c in result.candidates if "/.connections/" not in c.path
    ])


# ------------------------------------------------------------------
# Fixture: files + connections
# ------------------------------------------------------------------


@pytest.fixture
async def fs(db: DatabaseFileSystem):
    """DatabaseFileSystem with files, content, and connections.

    Files::

        /src/auth.py    — "import utils\\ndef login(): pass"
        /src/utils.py   — "def helper(): pass"
        /src/db.py      — "import utils\\ndef connect(): pass"
        /src/api.py     — "import auth\\nimport utils"
        /src/config.py  — "DEBUG = True"

    Graph topology::

        api  ──imports──▶  auth  ──imports──▶  utils  ──imports──▶  db
        api  ──imports──▶  utils                auth  ──calls───▶  db
    """
    async with db._use_session() as s:
        await db._write_impl("/src/auth.py", "import utils\ndef login(): pass", session=s)
        await db._write_impl("/src/utils.py", "def helper(): pass", session=s)
        await db._write_impl("/src/db.py", "import utils\ndef connect(): pass", session=s)
        await db._write_impl("/src/api.py", "import auth\nimport utils", session=s)
        await db._write_impl("/src/config.py", "DEBUG = True", session=s)

    for src, tgt, typ in [
        ("/src/auth.py", "/src/utils.py", "imports"),
        ("/src/auth.py", "/src/db.py", "calls"),
        ("/src/utils.py", "/src/db.py", "imports"),
        ("/src/api.py", "/src/auth.py", "imports"),
        ("/src/api.py", "/src/utils.py", "imports"),
    ]:
        async with db._use_session() as s:
            await db._mkconn_impl(src, tgt, typ, session=s)

    return db


# ------------------------------------------------------------------
# inject_details unit tests
# ------------------------------------------------------------------


class TestInjectDetails:
    def test_no_overlap_returns_unchanged(self):
        prior = GroverResult(candidates=[Candidate(path="/a", details=(_prior(),))])
        result = GroverResult(candidates=[Candidate(path="/b", details=(Detail(operation="op"),))])
        enriched = result.inject_details(prior)
        assert len(enriched) == 1
        assert _detail_ops(enriched.candidates[0]) == ["op"]

    def test_overlap_prepends_prior(self):
        prior = GroverResult(candidates=[Candidate(path="/a", details=(_prior(),))])
        result = GroverResult(candidates=[Candidate(path="/a", details=(Detail(operation="new"),))])
        enriched = result.inject_details(prior)
        assert _detail_ops(enriched.candidates[0]) == ["prior_op", "new"]

    def test_mixed_overlap_and_new(self):
        prior = GroverResult(candidates=[Candidate(path="/a", details=(_prior(),))])
        result = GroverResult(candidates=[
            Candidate(path="/a", details=(Detail(operation="new"),)),
            Candidate(path="/b", details=(Detail(operation="new"),)),
        ])
        enriched = result.inject_details(prior)
        assert _detail_ops(enriched.candidates[0]) == ["prior_op", "new"]
        assert _detail_ops(enriched.candidates[1]) == ["new"]

    def test_empty_prior_returns_unchanged(self):
        prior = GroverResult(candidates=[])
        result = GroverResult(candidates=[Candidate(path="/a", details=(Detail(operation="op"),))])
        enriched = result.inject_details(prior)
        assert enriched is result

    def test_multiple_prior_details_preserved_in_order(self):
        d1 = Detail(operation="step1", score=1.0)
        d2 = Detail(operation="step2", score=2.0)
        prior = GroverResult(candidates=[Candidate(path="/a", details=(d1, d2))])
        result = GroverResult(candidates=[Candidate(path="/a", details=(Detail(operation="step3"),))])
        enriched = result.inject_details(prior)
        assert _detail_ops(enriched.candidates[0]) == ["step1", "step2", "step3"]


# ------------------------------------------------------------------
# CRUD chaining
# ------------------------------------------------------------------


class TestReadChaining:
    async def test_preserves_prior_details(self, fs: DatabaseFileSystem):
        cands = _cands_with_prior("/src/auth.py")
        result = await fs.read(candidates=cands)
        assert len(result) == 1
        c = result.candidates[0]
        assert _detail_ops(c) == ["prior_op", "read"]
        assert c.content is not None

    async def test_preserves_multiple_prior_details(self, fs: DatabaseFileSystem):
        d1 = Detail(operation="search", score=0.9)
        d2 = Detail(operation="rerank", score=0.8)
        cands = GroverResult(candidates=[Candidate(path="/src/auth.py", details=(d1, d2))])
        result = await fs.read(candidates=cands)
        assert _detail_ops(result.candidates[0]) == ["search", "rerank", "read"]

    async def test_multi_candidate_read(self, fs: DatabaseFileSystem):
        cands = _cands_with_prior("/src/auth.py", "/src/utils.py")
        result = await fs.read(candidates=cands)
        assert len(result) == 2
        for c in result.candidates:
            assert _detail_ops(c) == ["prior_op", "read"]


class TestStatChaining:
    async def test_preserves_prior_details(self, fs: DatabaseFileSystem):
        cands = _cands_with_prior("/src/utils.py")
        result = await fs.stat(candidates=cands)
        assert len(result) == 1
        # stat delegates to read_impl, so the detail says "read"
        assert _detail_ops(result.candidates[0]) == ["prior_op", "read"]


class TestEditChaining:
    async def test_preserves_prior_details(self, fs: DatabaseFileSystem):
        cands = _cands_with_prior("/src/config.py")
        result = await fs.edit(
            candidates=cands,
            old="DEBUG = True",
            new="DEBUG = False",
        )
        assert result.success
        assert len(result) == 1
        assert _detail_ops(result.candidates[0]) == ["prior_op", "write"]


class TestDeleteChaining:
    async def test_preserves_prior_details(self, fs: DatabaseFileSystem):
        cands = _cands_with_prior("/src/config.py")
        result = await fs.delete(candidates=cands)
        assert result.success
        config = next(c for c in result.candidates if c.path == "/src/config.py")
        assert _detail_ops(config) == ["prior_op", "delete"]


class TestLsChaining:
    async def test_children_have_no_injected_prior(self, fs: DatabaseFileSystem):
        """ls returns children — different paths, so no prior injection."""
        cands = GroverResult(candidates=[
            Candidate(path="/src", kind="directory", details=(_prior(),)),
        ])
        result = await fs.ls(candidates=cands)
        assert len(result) > 0
        for c in result.candidates:
            assert _detail_ops(c) == ["ls"]


# ------------------------------------------------------------------
# Search chaining
# ------------------------------------------------------------------


class TestGlobChaining:
    async def test_preserves_prior_details(self, fs: DatabaseFileSystem):
        cands = _cands_with_prior("/src/auth.py", "/src/utils.py", "/src/config.py")
        result = await fs.glob("**/*.py", candidates=cands)
        assert len(result) >= 1
        for c in result.candidates:
            assert _detail_ops(c) == ["prior_op", "glob"]

    async def test_filtered_out_candidates_do_not_appear(self, fs: DatabaseFileSystem):
        cands = _cands_with_prior("/src/auth.py", "/src/config.py")
        result = await fs.glob("/src/auth*", candidates=cands)
        assert len(result) == 1
        assert result.candidates[0].path == "/src/auth.py"
        assert _detail_ops(result.candidates[0]) == ["prior_op", "glob"]


class TestGrepChaining:
    async def test_preserves_prior_details(self, fs: DatabaseFileSystem):
        cands = _cands_with_prior("/src/auth.py", "/src/db.py")
        result = await fs.grep("import utils", candidates=cands)
        assert len(result) == 2
        for c in result.candidates:
            assert _detail_ops(c) == ["prior_op", "grep"]

    async def test_filtered_out_candidates_do_not_appear(self, fs: DatabaseFileSystem):
        cands = _cands_with_prior("/src/auth.py", "/src/config.py")
        result = await fs.grep("import", candidates=cands)
        assert len(result) == 1
        assert result.candidates[0].path == "/src/auth.py"
        assert _detail_ops(result.candidates[0]) == ["prior_op", "grep"]


# ------------------------------------------------------------------
# Graph traversal chaining
# ------------------------------------------------------------------


class TestNeighborhoodChaining:
    async def test_seeds_preserve_prior_details(self, fs: DatabaseFileSystem):
        cands = _cands_with_prior("/src/auth.py")
        result = await fs.neighborhood(candidates=cands, depth=1)
        auth = next(c for c in result.candidates if c.path == "/src/auth.py")
        assert _detail_ops(auth) == ["prior_op", "neighborhood"]

    async def test_discoveries_have_no_prior(self, fs: DatabaseFileSystem):
        cands = _cands_with_prior("/src/auth.py")
        result = await fs.neighborhood(candidates=cands, depth=1)
        non_seeds = [
            c for c in result.candidates
            if c.path != "/src/auth.py" and "/.connections/" not in c.path
        ]
        assert len(non_seeds) > 0
        for c in non_seeds:
            assert _detail_ops(c) == ["neighborhood"]


class TestMeetingSubgraphChaining:
    async def test_seeds_preserve_prior_details(self, fs: DatabaseFileSystem):
        cands = _cands_with_prior("/src/auth.py", "/src/db.py")
        result = await fs.meeting_subgraph(candidates=cands)
        for seed_path in ["/src/auth.py", "/src/db.py"]:
            seed = next(c for c in result.candidates if c.path == seed_path)
            assert seed.details[0].operation == "prior_op"
            assert seed.details[-1].operation == "meeting_subgraph"


class TestMinMeetingSubgraphChaining:
    async def test_seeds_preserve_prior_details(self, fs: DatabaseFileSystem):
        cands = _cands_with_prior("/src/api.py", "/src/db.py")
        result = await fs.min_meeting_subgraph(candidates=cands)
        for seed_path in ["/src/api.py", "/src/db.py"]:
            seed = next(c for c in result.candidates if c.path == seed_path)
            assert seed.details[0].operation == "prior_op"
            assert seed.details[-1].operation == "min_meeting_subgraph"


# ------------------------------------------------------------------
# Centrality chaining
# ------------------------------------------------------------------


class TestPageRankChaining:
    async def test_preserves_prior_details(self, fs: DatabaseFileSystem):
        cands = _cands_with_prior("/src/auth.py", "/src/utils.py")
        result = await fs.pagerank(candidates=cands)
        assert len(result) == 2
        for c in result.candidates:
            assert _detail_ops(c) == ["prior_op", "pagerank"]
            assert c.details[-1].score is not None


class TestBetweennessCentralityChaining:
    async def test_preserves_prior_details(self, fs: DatabaseFileSystem):
        cands = _cands_with_prior("/src/auth.py", "/src/utils.py")
        result = await fs.betweenness_centrality(candidates=cands)
        assert len(result) == 2
        for c in result.candidates:
            assert _detail_ops(c) == ["prior_op", "betweenness_centrality"]


class TestClosenessCentralityChaining:
    async def test_preserves_prior_details(self, fs: DatabaseFileSystem):
        cands = _cands_with_prior("/src/auth.py", "/src/utils.py")
        result = await fs.closeness_centrality(candidates=cands)
        assert len(result) == 2
        for c in result.candidates:
            assert _detail_ops(c) == ["prior_op", "closeness_centrality"]


class TestDegreeCentralityChaining:
    async def test_preserves_prior_details(self, fs: DatabaseFileSystem):
        cands = _cands_with_prior("/src/auth.py", "/src/utils.py")
        result = await fs.degree_centrality(candidates=cands)
        assert len(result) == 2
        for c in result.candidates:
            assert _detail_ops(c) == ["prior_op", "degree_centrality"]


class TestInDegreeCentralityChaining:
    async def test_preserves_prior_details(self, fs: DatabaseFileSystem):
        cands = _cands_with_prior("/src/auth.py", "/src/utils.py")
        result = await fs.in_degree_centrality(candidates=cands)
        assert len(result) == 2
        for c in result.candidates:
            assert _detail_ops(c) == ["prior_op", "in_degree_centrality"]


class TestOutDegreeCentralityChaining:
    async def test_preserves_prior_details(self, fs: DatabaseFileSystem):
        cands = _cands_with_prior("/src/auth.py", "/src/utils.py")
        result = await fs.out_degree_centrality(candidates=cands)
        assert len(result) == 2
        for c in result.candidates:
            assert _detail_ops(c) == ["prior_op", "out_degree_centrality"]


class TestHitsChaining:
    async def test_preserves_prior_details(self, fs: DatabaseFileSystem):
        cands = _cands_with_prior("/src/auth.py", "/src/utils.py")
        result = await fs.hits(candidates=cands)
        assert len(result) == 2
        for c in result.candidates:
            assert _detail_ops(c) == ["prior_op", "hits"]


# ------------------------------------------------------------------
# Multi-step pipeline chains
# ------------------------------------------------------------------


class TestMultiStepChains:
    async def test_glob_grep_read(self, fs: DatabaseFileSystem):
        """glob → grep → read: 3 details on survivors."""
        r1 = await fs.glob("/src/*.py")
        assert len(r1) >= 3

        r2 = await fs.grep("import", candidates=r1)
        assert len(r2) >= 1
        for c in r2.candidates:
            assert _detail_ops(c) == ["glob", "grep"]

        r3 = await fs.read(candidates=r2)
        for c in r3.candidates:
            assert _detail_ops(c) == ["glob", "grep", "read"]
            assert c.content is not None

    async def test_glob_pagerank(self, fs: DatabaseFileSystem):
        """glob → pagerank: 2 details on survivors."""
        r1 = await fs.glob("/src/*.py")
        r2 = await fs.pagerank(candidates=r1)
        assert len(r2) >= 1
        for c in r2.candidates:
            assert _detail_ops(c) == ["glob", "pagerank"]
            assert c.details[-1].score is not None

    async def test_search_min_meeting_subgraph_pagerank(self, fs: DatabaseFileSystem):
        """Simulated search → min_meeting_subgraph → pagerank.

        Seeds accumulate 3 details.  Intermediary nodes introduced
        by the subgraph get 2 details.
        """
        seeds = GroverResult(candidates=[
            Candidate(
                path="/src/api.py",
                details=(Detail(operation="search", score=0.9),),
            ),
            Candidate(
                path="/src/db.py",
                details=(Detail(operation="search", score=0.7),),
            ),
        ])
        seed_paths = {"/src/api.py", "/src/db.py"}

        # Step 2: min_meeting_subgraph
        subgraph = await fs.min_meeting_subgraph(candidates=seeds)
        assert subgraph.success
        subgraph_nodes = _node_candidates(subgraph)
        node_paths = set(subgraph_nodes.paths)
        assert seed_paths <= node_paths, "Seeds must survive in subgraph"

        for c in subgraph_nodes.candidates:
            if c.path in seed_paths:
                assert c.details[0].operation == "search"
                assert c.details[-1].operation == "min_meeting_subgraph"
            else:
                assert _detail_ops(c) == ["min_meeting_subgraph"]

        # Step 3: pagerank
        ranked = await fs.pagerank(candidates=subgraph_nodes)
        assert ranked.success

        for c in ranked.candidates:
            if c.path in seed_paths:
                assert _detail_ops(c) == ["search", "min_meeting_subgraph", "pagerank"]
            else:
                assert _detail_ops(c) == ["min_meeting_subgraph", "pagerank"]
            assert c.details[-1].score is not None

    async def test_grep_meeting_subgraph_hits(self, fs: DatabaseFileSystem):
        """grep → meeting_subgraph → hits: 3 details on seeds."""
        r1 = await fs.grep("import")
        seed_paths = set(r1.paths)
        assert len(r1) >= 2

        r2 = await fs.meeting_subgraph(candidates=r1)
        r2_nodes = _node_candidates(r2)
        for c in r2_nodes.candidates:
            if c.path in seed_paths:
                assert c.details[0].operation == "grep"
                assert c.details[-1].operation == "meeting_subgraph"

        r3 = await fs.hits(candidates=r2_nodes)
        for c in r3.candidates:
            if c.path in seed_paths:
                assert _detail_ops(c) == ["grep", "meeting_subgraph", "hits"]
            else:
                assert _detail_ops(c) == ["meeting_subgraph", "hits"]

    async def test_four_step_chain(self, fs: DatabaseFileSystem):
        """glob → grep → read → pagerank: 4 details."""
        r1 = await fs.glob("/src/*.py")
        r2 = await fs.grep("import", candidates=r1)
        r3 = await fs.read(candidates=r2)
        r4 = await fs.pagerank(candidates=r3)
        assert len(r4) >= 1
        for c in r4.candidates:
            assert _detail_ops(c) == ["glob", "grep", "read", "pagerank"]

    async def test_score_for_retrieves_any_step(self, fs: DatabaseFileSystem):
        """After chaining, score_for() can retrieve scores from any step."""
        cands = GroverResult(candidates=[
            Candidate(
                path="/src/auth.py",
                details=(Detail(operation="search", score=0.9),),
            ),
            Candidate(
                path="/src/utils.py",
                details=(Detail(operation="search", score=0.7),),
            ),
        ])
        result = await fs.pagerank(candidates=cands)
        for c in result.candidates:
            assert c.score_for("search") > 0
            assert c.score_for("pagerank") >= 0
