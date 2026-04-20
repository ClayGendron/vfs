"""Tests that method chaining routes candidates through the dispatch layer.

Every public method that accepts ``candidates`` routes through
``_dispatch_candidates`` which filters the result set by the incoming
candidate paths.  These tests verify that contract end-to-end — after
the new ``Entry`` / ``VFSResult(function=, entries=)`` refactor, the
per-step ``Detail`` chain is gone; instead we assert on the result's
``function`` envelope and the surviving paths.
"""

from __future__ import annotations

import pytest

from vfs.backends.database import DatabaseFileSystem
from vfs.results import Entry, VFSResult

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _cands(*paths: str, function: str = "") -> VFSResult:
    """Build a result with plain path entries."""
    return VFSResult(function=function, entries=[Entry(path=p) for p in paths])


def _node_result(result: VFSResult) -> VFSResult:
    """Filter out edge entries from a subgraph result."""
    return VFSResult(
        function=result.function,
        entries=[e for e in result.entries if "/__meta__/edges/" not in e.path],
        success=result.success,
        errors=list(result.errors),
    )


# ------------------------------------------------------------------
# Fixture: files + edges
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
            await db._mkedge_impl(src, tgt, typ, session=s)

    return db


# ------------------------------------------------------------------
# CRUD chaining
# ------------------------------------------------------------------


class TestReadChaining:
    async def test_filters_by_candidates(self, fs: DatabaseFileSystem):
        cands = _cands("/src/auth.py")
        result = await fs.read(candidates=cands)
        assert len(result) == 1
        entry = result.entries[0]
        assert entry.path == "/src/auth.py"
        assert entry.content is not None
        assert result.function == "read"

    async def test_multi_candidate_read(self, fs: DatabaseFileSystem):
        cands = _cands("/src/auth.py", "/src/utils.py")
        result = await fs.read(candidates=cands)
        assert len(result) == 2
        assert {e.path for e in result.entries} == {"/src/auth.py", "/src/utils.py"}


class TestStatChaining:
    async def test_filters_by_candidates(self, fs: DatabaseFileSystem):
        cands = _cands("/src/utils.py")
        result = await fs.stat(candidates=cands)
        assert len(result) == 1
        assert result.entries[0].path == "/src/utils.py"


class TestEditChaining:
    async def test_edits_candidate(self, fs: DatabaseFileSystem):
        cands = _cands("/src/config.py")
        result = await fs.edit(
            candidates=cands,
            old="DEBUG = True",
            new="DEBUG = False",
        )
        assert result.success
        assert len(result) == 1
        assert result.entries[0].path == "/src/config.py"


class TestDeleteChaining:
    async def test_deletes_candidate(self, fs: DatabaseFileSystem):
        cands = _cands("/src/config.py")
        result = await fs.delete(candidates=cands)
        assert result.success
        assert any(e.path == "/src/config.py" for e in result.entries)


class TestLsChaining:
    async def test_returns_children(self, fs: DatabaseFileSystem):
        """ls returns children — different paths from the seed."""
        cands = VFSResult(
            entries=[Entry(path="/src", kind="directory")],
        )
        result = await fs.ls(candidates=cands)
        assert len(result) > 0
        assert result.function == "ls"


# ------------------------------------------------------------------
# Search chaining
# ------------------------------------------------------------------


class TestGlobChaining:
    async def test_filters_by_candidates(self, fs: DatabaseFileSystem):
        cands = _cands("/src/auth.py", "/src/utils.py", "/src/config.py")
        result = await fs.glob("**/*.py", candidates=cands)
        assert len(result) >= 1
        assert result.function == "glob"
        # All surviving entries must be in the candidate set
        surviving = {e.path for e in result.entries}
        assert surviving <= {"/src/auth.py", "/src/utils.py", "/src/config.py"}

    async def test_filtered_out_candidates_do_not_appear(self, fs: DatabaseFileSystem):
        cands = _cands("/src/auth.py", "/src/config.py")
        result = await fs.glob("/src/auth*", candidates=cands)
        assert len(result) == 1
        assert result.entries[0].path == "/src/auth.py"


class TestGrepChaining:
    async def test_filters_by_candidates(self, fs: DatabaseFileSystem):
        cands = _cands("/src/auth.py", "/src/db.py")
        result = await fs.grep("import utils", candidates=cands)
        assert len(result) == 2
        assert result.function == "grep"

    async def test_filtered_out_candidates_do_not_appear(self, fs: DatabaseFileSystem):
        cands = _cands("/src/auth.py", "/src/config.py")
        result = await fs.grep("import", candidates=cands)
        assert len(result) == 1
        assert result.entries[0].path == "/src/auth.py"


# ------------------------------------------------------------------
# Graph traversal chaining
# ------------------------------------------------------------------


class TestNeighborhoodChaining:
    async def test_seeds_appear_in_neighborhood(self, fs: DatabaseFileSystem):
        cands = _cands("/src/auth.py")
        result = await fs.neighborhood(candidates=cands, depth=1)
        paths = {e.path for e in result.entries if "/__meta__/edges/" not in e.path}
        assert "/src/auth.py" in paths
        assert result.function == "neighborhood"

    async def test_discovers_neighbors(self, fs: DatabaseFileSystem):
        cands = _cands("/src/auth.py")
        result = await fs.neighborhood(candidates=cands, depth=1)
        non_seeds = [e for e in result.entries if e.path != "/src/auth.py" and "/__meta__/edges/" not in e.path]
        assert len(non_seeds) > 0


class TestMeetingSubgraphChaining:
    async def test_includes_seeds(self, fs: DatabaseFileSystem):
        cands = _cands("/src/auth.py", "/src/db.py")
        result = await fs.meeting_subgraph(candidates=cands)
        node_paths = {e.path for e in result.entries if "/__meta__/edges/" not in e.path}
        assert "/src/auth.py" in node_paths
        assert "/src/db.py" in node_paths
        assert result.function == "meeting_subgraph"


class TestMinMeetingSubgraphChaining:
    async def test_includes_seeds(self, fs: DatabaseFileSystem):
        cands = _cands("/src/api.py", "/src/db.py")
        result = await fs.min_meeting_subgraph(candidates=cands)
        node_paths = {e.path for e in result.entries if "/__meta__/edges/" not in e.path}
        assert "/src/api.py" in node_paths
        assert "/src/db.py" in node_paths
        assert result.function == "min_meeting_subgraph"


# ------------------------------------------------------------------
# Centrality chaining
# ------------------------------------------------------------------


class TestPageRankChaining:
    async def test_filters_by_candidates(self, fs: DatabaseFileSystem):
        cands = _cands("/src/auth.py", "/src/utils.py")
        result = await fs.pagerank(candidates=cands)
        assert len(result) == 2
        assert result.function == "pagerank"
        for e in result.entries:
            assert e.score is not None


class TestBetweennessCentralityChaining:
    async def test_filters_by_candidates(self, fs: DatabaseFileSystem):
        cands = _cands("/src/auth.py", "/src/utils.py")
        result = await fs.betweenness_centrality(candidates=cands)
        assert len(result) == 2
        assert result.function == "betweenness_centrality"


class TestClosenessCentralityChaining:
    async def test_filters_by_candidates(self, fs: DatabaseFileSystem):
        cands = _cands("/src/auth.py", "/src/utils.py")
        result = await fs.closeness_centrality(candidates=cands)
        assert len(result) == 2
        assert result.function == "closeness_centrality"


class TestDegreeCentralityChaining:
    async def test_filters_by_candidates(self, fs: DatabaseFileSystem):
        cands = _cands("/src/auth.py", "/src/utils.py")
        result = await fs.degree_centrality(candidates=cands)
        assert len(result) == 2
        assert result.function == "degree_centrality"


class TestInDegreeCentralityChaining:
    async def test_filters_by_candidates(self, fs: DatabaseFileSystem):
        cands = _cands("/src/auth.py", "/src/utils.py")
        result = await fs.in_degree_centrality(candidates=cands)
        assert len(result) == 2
        assert result.function == "in_degree_centrality"


class TestOutDegreeCentralityChaining:
    async def test_filters_by_candidates(self, fs: DatabaseFileSystem):
        cands = _cands("/src/auth.py", "/src/utils.py")
        result = await fs.out_degree_centrality(candidates=cands)
        assert len(result) == 2
        assert result.function == "out_degree_centrality"


class TestHitsChaining:
    async def test_filters_by_candidates(self, fs: DatabaseFileSystem):
        cands = _cands("/src/auth.py", "/src/utils.py")
        result = await fs.hits(candidates=cands)
        assert len(result) == 2
        assert result.function == "hits"


# ------------------------------------------------------------------
# Multi-step pipeline chains
# ------------------------------------------------------------------


class TestMultiStepChains:
    async def test_glob_grep_read(self, fs: DatabaseFileSystem):
        """glob → grep → read: surviving paths narrow at each step."""
        r1 = await fs.glob("/src/*.py")
        assert len(r1) >= 3
        assert r1.function == "glob"

        r2 = await fs.grep("import", candidates=r1)
        assert len(r2) >= 1
        assert r2.function == "grep"
        # All grep survivors must have been in the glob set
        assert {e.path for e in r2.entries} <= set(r1.paths)

        r3 = await fs.read(candidates=r2)
        assert r3.function == "read"
        assert {e.path for e in r3.entries} <= set(r2.paths)
        for e in r3.entries:
            assert e.content is not None

    async def test_glob_pagerank(self, fs: DatabaseFileSystem):
        """glob → pagerank: pagerank filters to the glob set."""
        r1 = await fs.glob("/src/*.py")
        r2 = await fs.pagerank(candidates=r1)
        assert len(r2) >= 1
        assert r2.function == "pagerank"
        assert {e.path for e in r2.entries} <= set(r1.paths)
        for e in r2.entries:
            assert e.score is not None

    async def test_search_min_meeting_subgraph_pagerank(self, fs: DatabaseFileSystem):
        """Simulated search → min_meeting_subgraph → pagerank.

        Seeds must survive through the subgraph and carry scores at the end.
        """
        seeds = _cands("/src/api.py", "/src/db.py", function="lexical_search")
        seed_paths = {"/src/api.py", "/src/db.py"}

        # Step 2: min_meeting_subgraph
        subgraph = await fs.min_meeting_subgraph(candidates=seeds)
        assert subgraph.success
        assert subgraph.function == "min_meeting_subgraph"
        subgraph_nodes = _node_result(subgraph)
        node_paths = set(subgraph_nodes.paths)
        assert seed_paths <= node_paths, "Seeds must survive in subgraph"

        # Step 3: pagerank
        ranked = await fs.pagerank(candidates=subgraph_nodes)
        assert ranked.success
        assert ranked.function == "pagerank"

        ranked_paths = {e.path for e in ranked.entries}
        assert ranked_paths <= node_paths
        for e in ranked.entries:
            assert e.score is not None

    async def test_grep_meeting_subgraph_hits(self, fs: DatabaseFileSystem):
        """grep → meeting_subgraph → hits: seeds survive the whole pipeline."""
        r1 = await fs.grep("import")
        seed_paths = set(r1.paths)
        assert len(r1) >= 2

        r2 = await fs.meeting_subgraph(candidates=r1)
        assert r2.function == "meeting_subgraph"
        r2_nodes = _node_result(r2)
        # Every grep seed should still be in the subgraph node set
        assert seed_paths <= {e.path for e in r2_nodes.entries}

        r3 = await fs.hits(candidates=r2_nodes)
        assert r3.function == "hits"
        # All hits survivors were subgraph nodes
        assert {e.path for e in r3.entries} <= {e.path for e in r2_nodes.entries}

    async def test_four_step_chain(self, fs: DatabaseFileSystem):
        """glob → grep → read → pagerank: each step narrows the set."""
        r1 = await fs.glob("/src/*.py")
        r2 = await fs.grep("import", candidates=r1)
        r3 = await fs.read(candidates=r2)
        r4 = await fs.pagerank(candidates=r3)
        assert len(r4) >= 1
        assert r4.function == "pagerank"
        # Final survivors were present at every prior stage
        final_paths = {e.path for e in r4.entries}
        assert final_paths <= set(r3.paths)
        assert final_paths <= set(r2.paths)
        assert final_paths <= set(r1.paths)
