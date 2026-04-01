"""Tests for BM25-backed lexical search (_lexical_search_impl)."""

from __future__ import annotations

from typing import Any, cast

from grover.backends.database import DatabaseFileSystem
from grover.results import Candidate, GroverResult
from tests.conftest import require_file

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


async def _seed(db: DatabaseFileSystem, files: dict[str, str]) -> None:
    """Write multiple files into the database."""
    async with db._use_session() as s:
        for path, content in files.items():
            await db._write_impl(path, content, session=s)


# ------------------------------------------------------------------
# Basic scoring
# ------------------------------------------------------------------


class TestBasicBM25:
    async def test_single_term_match(self, db: DatabaseFileSystem):
        await _seed(db, {"/a.py": "authentication is important"})
        async with db._use_session() as s:
            r = await db._lexical_search_impl("authentication", session=s)
        assert r.success
        assert len(r) == 1
        file = require_file(r)
        assert file.path == "/a.py"
        assert file.score > 0

    async def test_no_match_returns_empty(self, db: DatabaseFileSystem):
        await _seed(db, {"/a.py": "hello world"})
        async with db._use_session() as s:
            r = await db._lexical_search_impl("authentication", session=s)
        assert r.success
        assert len(r) == 0

    async def test_multi_term_query(self, db: DatabaseFileSystem):
        await _seed(db, {
            "/a.py": "authentication timeout handler",
            "/b.py": "authentication module",
            "/c.py": "unrelated content here",
        })
        async with db._use_session() as s:
            r = await db._lexical_search_impl(
                "authentication timeout", session=s,
            )
        # a.py matches both terms, b.py matches one, c.py matches none
        assert len(r) == 2
        assert r.candidates[0].path == "/a.py"
        assert r.candidates[1].path == "/b.py"
        assert r.candidates[0].score > r.candidates[1].score

    async def test_term_frequency_boosts_score(self, db: DatabaseFileSystem):
        await _seed(db, {
            "/many.py": "timeout timeout timeout timeout timeout",
            "/once.py": "timeout happens once",
        })
        async with db._use_session() as s:
            r = await db._lexical_search_impl("timeout", session=s)
        assert len(r) == 2
        assert r.candidates[0].path == "/many.py"
        assert r.candidates[0].score > r.candidates[1].score

    async def test_shorter_doc_ranks_higher_with_equal_tf(
        self, db: DatabaseFileSystem,
    ):
        """BM25 length normalization: shorter docs score higher at equal TF."""
        await _seed(db, {
            "/short.py": "timeout error",
            "/long.py": (
                "timeout error " + "padding word " * 100
            ),
        })
        async with db._use_session() as s:
            r = await db._lexical_search_impl("timeout", session=s)
        assert len(r) == 2
        assert r.candidates[0].path == "/short.py"

    async def test_idf_weighting(self, db: DatabaseFileSystem):
        """Rare terms contribute more to the score than common terms."""
        files = {f"/common{i}.py": "the common word" for i in range(10)}
        files["/rare.py"] = "the rare authentication"
        files["/common_only.py"] = "the common word again"
        await _seed(db, files)

        async with db._use_session() as s:
            r = await db._lexical_search_impl("authentication the", session=s)
        # /rare.py should rank first because "authentication" has high IDF
        assert r.candidates[0].path == "/rare.py"


# ------------------------------------------------------------------
# Version exclusion
# ------------------------------------------------------------------


class TestVersionExclusion:
    async def test_excludes_version_rows(self, db: DatabaseFileSystem):
        """Version snapshots should not appear in lexical search results."""
        await _seed(db, {"/a.py": "authentication handler"})
        async with db._use_session() as s:
            r = await db._lexical_search_impl("authentication", session=s)
        result_paths = {c.path for c in r.candidates}
        assert "/a.py" in result_paths
        assert not any("/.versions/" in p for p in result_paths)

    async def test_excludes_version_candidates(self, db: DatabaseFileSystem):
        """Version candidates passed in should be skipped."""
        cands = GroverResult(candidates=[
            Candidate(
                path="/a.py/.versions/1",
                kind="version",
                content="authentication handler",
            ),
            Candidate(
                path="/a.py",
                kind="file",
                content="authentication handler",
            ),
        ])
        async with db._use_session() as s:
            r = await db._lexical_search_impl(
                "authentication", candidates=cands, session=s,
            )
        assert len(r) == 1
        assert require_file(r).path == "/a.py"


# ------------------------------------------------------------------
# k parameter
# ------------------------------------------------------------------


class TestKParameter:
    async def test_k_limits_results(self, db: DatabaseFileSystem):
        await _seed(db, {f"/f{i}.py": f"match term {i}" for i in range(10)})
        async with db._use_session() as s:
            r = await db._lexical_search_impl("match", k=3, session=s)
        assert len(r) == 3

    async def test_k_larger_than_matches(self, db: DatabaseFileSystem):
        await _seed(db, {"/a.py": "match here", "/b.py": "no luck"})
        async with db._use_session() as s:
            r = await db._lexical_search_impl("match", k=100, session=s)
        assert len(r) == 1


# ------------------------------------------------------------------
# Error handling
# ------------------------------------------------------------------


class TestErrorHandling:
    async def test_empty_query_errors(self, db: DatabaseFileSystem):
        async with db._use_session() as s:
            r = await db._lexical_search_impl("", session=s)
        assert not r.success

    async def test_whitespace_query_errors(self, db: DatabaseFileSystem):
        async with db._use_session() as s:
            r = await db._lexical_search_impl("   ", session=s)
        assert not r.success

    async def test_punctuation_only_query_errors(self, db: DatabaseFileSystem):
        async with db._use_session() as s:
            r = await db._lexical_search_impl("!@#$%", session=s)
        assert not r.success


# ------------------------------------------------------------------
# Searches all content (not just files)
# ------------------------------------------------------------------


class TestSearchesAllContent:
    async def test_finds_chunks(self, db: DatabaseFileSystem):
        """Lexical search should find chunk content, not just files."""
        await _seed(db, {"/a.py": "file content here"})
        async with db._use_session() as s:
            await db._write_impl(
                "/a.py/.chunks/login",
                "authentication timeout handler",
                session=s,
            )
        async with db._use_session() as s:
            r = await db._lexical_search_impl("authentication", session=s)
        assert len(r) >= 1
        chunk_paths = [c.path for c in r.candidates]
        assert "/a.py/.chunks/login" in chunk_paths

    async def test_finds_files_and_chunks(self, db: DatabaseFileSystem):
        await _seed(db, {"/a.py": "authentication in file"})
        async with db._use_session() as s:
            await db._write_impl(
                "/a.py/.chunks/login",
                "authentication in chunk",
                session=s,
            )
        async with db._use_session() as s:
            r = await db._lexical_search_impl("authentication", session=s)
        result_paths = {c.path for c in r.candidates}
        assert "/a.py" in result_paths
        assert "/a.py/.chunks/login" in result_paths


# ------------------------------------------------------------------
# Candidate chaining
# ------------------------------------------------------------------


class TestCandidateChaining:
    async def test_with_candidates_scores_only_provided_paths(
        self, db: DatabaseFileSystem,
    ):
        await _seed(db, {
            "/a.py": "authentication handler",
            "/b.py": "authentication module",
            "/c.py": "authentication service",
        })
        cands = GroverResult(candidates=[
            Candidate(path="/a.py", content="authentication handler"),
            Candidate(path="/b.py", content="authentication module"),
        ])
        async with db._use_session() as s:
            r = await db._lexical_search_impl(
                "authentication", candidates=cands, session=s,
            )
        result_paths = {c.path for c in r.candidates}
        assert "/a.py" in result_paths
        assert "/b.py" in result_paths
        assert "/c.py" not in result_paths

    async def test_with_candidates_hydrates_missing_content(
        self, db: DatabaseFileSystem,
    ):
        """Candidates without content get hydrated from DB."""
        await _seed(db, {"/a.py": "authentication handler"})
        cands = GroverResult(candidates=[
            Candidate(path="/a.py"),
        ])
        async with db._use_session() as s:
            r = await db._lexical_search_impl(
                "authentication", candidates=cands, session=s,
            )
        assert len(r) == 1
        assert require_file(r).path == "/a.py"

    async def test_with_candidates_preserves_kind(
        self, db: DatabaseFileSystem,
    ):
        cands = GroverResult(candidates=[
            Candidate(
                path="/a.py", kind="file", content="authentication handler",
            ),
        ])
        async with db._use_session() as s:
            r = await db._lexical_search_impl(
                "authentication", candidates=cands, session=s,
            )
        assert require_file(r).kind == "file"


# ------------------------------------------------------------------
# Detail metadata
# ------------------------------------------------------------------


class TestDetailMetadata:
    async def test_detail_operation_is_lexical_search(
        self, db: DatabaseFileSystem,
    ):
        await _seed(db, {"/a.py": "match me"})
        async with db._use_session() as s:
            r = await db._lexical_search_impl("match", session=s)
        assert require_file(r).details[0].operation == "lexical_search"

    async def test_detail_score_is_positive(self, db: DatabaseFileSystem):
        await _seed(db, {"/a.py": "keyword present"})
        async with db._use_session() as s:
            r = await db._lexical_search_impl("keyword", session=s)
        score = require_file(r).details[0].score
        assert score is not None
        assert score > 0


# ------------------------------------------------------------------
# Pre-filter limit
# ------------------------------------------------------------------


class TestPreFilterLimit:
    async def test_respects_pre_filter_limit(self, db: DatabaseFileSystem):
        """Even with many matching docs, only BM25_PRE_FILTER_LIMIT are scored."""
        original = db.BM25_PRE_FILTER_LIMIT
        cast("Any", db).BM25_PRE_FILTER_LIMIT = 5
        try:
            await _seed(
                db,
                {f"/f{i}.py": f"keyword content {i}" for i in range(20)},
            )
            async with db._use_session() as s:
                r = await db._lexical_search_impl("keyword", k=100, session=s)
            assert len(r) <= 5
        finally:
            cast("Any", db).BM25_PRE_FILTER_LIMIT = original


# ------------------------------------------------------------------
# SQL special characters in query
# ------------------------------------------------------------------


class TestSpecialCharacters:
    async def test_percent_in_query(self, db: DatabaseFileSystem):
        await _seed(db, {"/a.py": "100% complete"})
        async with db._use_session() as s:
            r = await db._lexical_search_impl("100% complete", session=s)
        assert r.success

    async def test_underscore_in_query(self, db: DatabaseFileSystem):
        await _seed(db, {"/a.py": "my_variable = 1"})
        async with db._use_session() as s:
            r = await db._lexical_search_impl("my_variable", session=s)
        assert r.success


# ------------------------------------------------------------------
# Soft-deleted exclusion
# ------------------------------------------------------------------


class TestSoftDeleteExclusion:
    async def test_excludes_soft_deleted(self, db: DatabaseFileSystem):
        await _seed(db, {"/a.py": "authentication handler"})
        async with db._use_session() as s:
            await db._delete_impl("/a.py", permanent=False, session=s)
        async with db._use_session() as s:
            r = await db._lexical_search_impl("authentication", session=s)
        assert len(r) == 0


# ------------------------------------------------------------------
# Public API routing
# ------------------------------------------------------------------


class TestPublicAPI:
    async def test_lexical_search_through_public_method(
        self, db: DatabaseFileSystem, engine,
    ):
        root = DatabaseFileSystem(engine=engine)
        await root.add_mount("/code", db)
        await _seed(db, {"/a.py": "authentication handler"})
        r = await root.lexical_search("authentication")
        assert r.success
        assert len(r) >= 1
        assert any(c.path == "/code/a.py" for c in r.candidates)
