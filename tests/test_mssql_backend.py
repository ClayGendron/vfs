"""Tests for MSSQLFileSystem.

Two layers:

1. **Pure-Python unit tests** for the regex literal-extraction helper
   and the CONTAINS-quoting helper.  These run on every invocation
   regardless of backend — they don't touch a database.

2. **Integration tests** gated on ``--mssql`` that exercise the
   CONTAINSTABLE / REGEXP_LIKE pushdown paths against a real SQL
   Server / Azure SQL instance.  Skipped by default.
"""

from __future__ import annotations

import asyncio
import re

import pytest
from sqlalchemy import text

from grover.backends.mssql import (
    MSSQLFileSystem,
    _extract_literal_terms,
    _quote_contains_term,
)
from grover.results import Candidate, GroverResult

# ---------------------------------------------------------------------------
# Unit tests — pure Python, no DB
# ---------------------------------------------------------------------------


class TestExtractLiteralTerms:
    """Coarse-pre-filter literal extraction must be sound (no false positives)."""

    def test_pure_literal(self):
        assert _extract_literal_terms("login") == ["login"]

    def test_short_literal_dropped(self):
        # Runs shorter than 3 chars are dropped
        assert _extract_literal_terms("if") == []
        assert _extract_literal_terms("ab") == []

    def test_escaped_metachar(self):
        # \( becomes a literal "(" but we strip it; the word "login" survives
        assert _extract_literal_terms(r"def login\(") == ["def", "login"]

    def test_dot_star_keeps_both_sides(self):
        # "login.*password" — the . is dropped, both literals survive
        assert _extract_literal_terms(r"login.*password") == ["login", "password"]

    def test_character_class_dropped(self):
        # [a-z] — bracket content stripped, no literals to extract
        assert _extract_literal_terms(r"[a-z]+") == []

    def test_pure_char_class_pattern(self):
        assert _extract_literal_terms(r"^[A-Z]{3,}$") == []

    def test_alternation_bails_out(self):
        # Alternation makes the literals non-mandatory; bail entirely.
        assert _extract_literal_terms(r"login|signin") == []
        assert _extract_literal_terms(r"(login|signin)") == []

    def test_quantified_group_bails_out(self):
        # (group)? makes the whole group optional; bail entirely.
        assert _extract_literal_terms(r"hello(world)?") == []
        assert _extract_literal_terms(r"prefix(infix)*suffix") == []
        assert _extract_literal_terms(r"a(bc){2,4}d") == []

    def test_non_alternating_group_kept(self):
        # (login) without alternation or quantifier — literal "login" survives
        assert _extract_literal_terms(r"hello(world)") == ["hello", "world"]

    def test_quantified_word_char_dropped(self):
        # "foo+" → the trailing "o" is quantified, drop it; "fo" too short.
        assert _extract_literal_terms(r"foo+") == []
        # "foobar+" → drop trailing "r", keep "fooba" (substring of all matches)
        assert _extract_literal_terms(r"foobar+") == ["fooba"]
        # "hello?world" → drop "o?", "hell" + "world" both >= 3
        assert _extract_literal_terms(r"hello?world") == ["hell", "world"]

    def test_word_class_escape(self):
        # \w is stripped; surrounding literals survive
        assert _extract_literal_terms(r"def \w+\(") == ["def"]

    def test_anchors_dropped(self):
        assert _extract_literal_terms(r"^foo$") == ["foo"]

    def test_de_dup_preserves_order(self):
        # Repeated terms appear once, in first-seen order
        assert _extract_literal_terms(r"foo bar foo") == ["foo", "bar"]

    def test_caps_at_eight_terms(self):
        pattern = " ".join(f"term{i}" for i in range(20))
        out = _extract_literal_terms(pattern)
        assert len(out) == 8
        assert out == [f"term{i}" for i in range(8)]

    def test_complex_real_world_pattern(self):
        # def <name>(<args>): style
        assert _extract_literal_terms(r"def \w+\(.*\):") == ["def"]


class TestQuoteContainsTerm:
    def test_plain_term(self):
        assert _quote_contains_term("login") == '"login"'

    def test_term_with_quote(self):
        # Embedded double quotes are doubled per CONTAINS quoting rules
        assert _quote_contains_term('say "hi"') == '"say ""hi"""'

    def test_empty_term(self):
        assert _quote_contains_term("") == '""'


class TestCollectLineMatchesIntegration:
    """The base-class _collect_line_matches helper still drives MSSQL grep."""

    def test_returns_per_line_metadata(self):
        from grover.backends.database import DatabaseFileSystem

        regex = re.compile(r"foo")
        content_map = {
            "/a.py": "foo bar\nbaz qux\nfoo again",
            "/b.py": "no match here",
        }
        matched = DatabaseFileSystem._collect_line_matches(content_map, regex, max_results=None)
        assert len(matched) == 1
        assert matched[0].path == "/a.py"
        assert matched[0].kind == "file"
        detail = matched[0].details[0]
        assert detail.operation == "grep"
        assert detail.score == 2.0
        assert detail.metadata is not None
        assert detail.metadata["match_count"] == 2
        assert detail.metadata["line_matches"] == [
            {"line": 1, "text": "foo bar"},
            {"line": 3, "text": "foo again"},
        ]

    def test_max_results_caps(self):
        from grover.backends.database import DatabaseFileSystem

        regex = re.compile(r"hit")
        content_map = {f"/f{i}.txt": "hit it" for i in range(5)}
        matched = DatabaseFileSystem._collect_line_matches(content_map, regex, max_results=2)
        assert len(matched) == 2


# ---------------------------------------------------------------------------
# Glob in-memory candidate path (no DB needed)
# ---------------------------------------------------------------------------


class TestGlobInMemoryCandidates:
    """The in-memory candidate branch of _glob_impl is identical to the base
    class — no SQL is issued, so we can test it without a DB connection.
    """

    async def test_in_memory_glob_filters_candidates(self):
        # Construct an MSSQLFileSystem without an engine; the in-memory
        # candidate path of _glob_impl never touches the session.
        fs = MSSQLFileSystem.__new__(MSSQLFileSystem)
        # Minimum state needed by the method
        fs._user_scoped = False
        fs._raise_on_error = False

        candidates = GroverResult(
            candidates=[
                Candidate(path="/src/foo.py", kind="file"),
                Candidate(path="/src/bar.ts", kind="file"),
                Candidate(path="/tests/foo.py", kind="file"),
            ]
        )
        result = await fs._glob_impl(  # type: ignore[call-arg]
            "**/*.py",
            candidates=candidates,
            session=None,  # type: ignore[arg-type]
        )
        assert sorted(result.paths) == ["/src/foo.py", "/tests/foo.py"]
        for c in result.candidates:
            assert c.details[0].operation == "glob"


# ---------------------------------------------------------------------------
# Integration tests — gated on --mssql
# ---------------------------------------------------------------------------


def _mssql_required(request: pytest.FixtureRequest) -> None:
    """Skip the test if --mssql was not passed on the command line."""
    if not request.config.getoption("--mssql"):
        pytest.skip("requires --mssql flag and a running SQL Server / Azure SQL instance")


async def _wait_for_fts_ready(
    db: MSSQLFileSystem,
    expected_count: int,
    *,
    timeout_s: float = 15.0,
) -> None:
    """Block until the full-text index has caught up to the seeded rows.

    SQL Server's ``CHANGE_TRACKING AUTO`` propagates inserts to the
    full-text index asynchronously in a background crawl.  On fast
    native hardware the lag is sub-millisecond and tests get away with
    querying immediately; under Rosetta emulation on Apple Silicon the
    lag is routinely hundreds of milliseconds, which races every
    ``CONTAINSTABLE`` query in this file.

    We poll ``FULLTEXTCATALOGPROPERTY('ItemCount')`` until it reaches
    the expected document count, then a single idle check on
    ``PopulateStatus`` to confirm the crawl has drained.
    """
    deadline = asyncio.get_event_loop().time() + timeout_s
    catalog = "grover_test_ftcat"
    while True:
        async with db._use_session() as s:
            item_row = (await s.execute(text(f"SELECT FULLTEXTCATALOGPROPERTY('{catalog}', 'ItemCount')"))).first()
            status_row = (
                await s.execute(text(f"SELECT FULLTEXTCATALOGPROPERTY('{catalog}', 'PopulateStatus')"))
            ).first()
        item_count = int(item_row[0] or 0) if item_row is not None else 0
        populate_status = int(status_row[0] or 0) if status_row is not None else 0
        if item_count >= expected_count and populate_status == 0:
            return
        if asyncio.get_event_loop().time() > deadline:
            msg = (
                f"FTS population timed out: indexed {item_count}/{expected_count} "
                f"after {timeout_s}s (PopulateStatus={populate_status})"
            )
            raise TimeoutError(msg)
        await asyncio.sleep(0.1)


async def _seed(db: MSSQLFileSystem, files: dict[str, str]) -> None:
    """Write files into the database under test and wait for FTS to catch up."""
    async with db._use_session() as s:
        for path, content in files.items():
            await db._write_impl(path, content, session=s)
    indexable = sum(1 for content in files.values() if content)
    if indexable:
        await _wait_for_fts_ready(db, indexable)


class TestVerifyFulltextSchema:
    async def test_passes_when_schema_ok(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        # The conftest fixture provisions the full-text index, so verify
        # should succeed without raising.
        await db.verify_fulltext_schema()

    async def test_idempotent(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await db.verify_fulltext_schema()
        await db.verify_fulltext_schema()


class TestLexicalSearchPushdown:
    async def test_single_term_match(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await _seed(db, {"/a.py": "authentication is important"})
        async with db._use_session() as s:
            r = await db._lexical_search_impl("authentication", session=s)
        assert r.success
        assert "/a.py" in r.paths

    async def test_excludes_chunks_and_versions(self, request, db: MSSQLFileSystem):
        """Lexical search returns only kind='file' rows."""
        _mssql_required(request)
        await _seed(
            db,
            {
                "/with_chunks.py": "alpha beta gamma " * 50,
                "/plain.py": "alpha beta",
            },
        )
        async with db._use_session() as s:
            r = await db._lexical_search_impl("alpha", session=s)
        # Even if chunk rows exist for /with_chunks.py, only file rows return.
        for c in r.candidates:
            assert c.kind == "file"

    async def test_multi_term_ranking(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await _seed(
            db,
            {
                "/both.py": "authentication timeout handler",
                "/one.py": "authentication module",
                "/none.py": "unrelated",
            },
        )
        async with db._use_session() as s:
            r = await db._lexical_search_impl("authentication timeout", session=s)
        # /both.py should outrank /one.py
        paths = list(r.paths)
        assert "/both.py" in paths
        assert "/one.py" in paths
        assert paths.index("/both.py") < paths.index("/one.py")

    async def test_with_candidate_intersection(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await _seed(
            db,
            {
                "/a.py": "auth login",
                "/b.py": "auth signup",
                "/c.py": "auth logout",
            },
        )
        candidates = GroverResult(candidates=[Candidate(path="/a.py"), Candidate(path="/c.py")])
        async with db._use_session() as s:
            r = await db._lexical_search_impl("auth", candidates=candidates, session=s)
        assert set(r.paths) == {"/a.py", "/c.py"}

    async def test_top_k_caps(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await _seed(db, {f"/f{i}.py": f"shared term file{i}" for i in range(20)})
        async with db._use_session() as s:
            r = await db._lexical_search_impl("shared", k=5, session=s)
        assert len(r) <= 5


class TestGrepPushdown:
    async def test_with_literal_term(self, request, db: MSSQLFileSystem):
        """Patterns with literal terms use the CONTAINS pre-filter."""
        _mssql_required(request)
        await _seed(
            db,
            {
                "/a.py": "def login(user):\n    pass\n",
                "/b.py": "def logout(user):\n    pass\n",
                "/c.py": "import os\n",
            },
        )
        async with db._use_session() as s:
            r = await db._grep_impl(r"def login\(", session=s)
        assert r.success
        assert set(r.paths) == {"/a.py"}
        detail = r.candidates[0].details[0]
        assert detail.metadata is not None
        assert detail.metadata["match_count"] == 1

    async def test_pure_regex(self, request, db: MSSQLFileSystem):
        """Patterns with no literals fall through to direct REGEXP_LIKE."""
        _mssql_required(request)
        await _seed(
            db,
            {
                "/upper.txt": "ABC\n",
                "/mixed.txt": "Abc\n",
                "/lower.txt": "abc\n",
            },
        )
        async with db._use_session() as s:
            r = await db._grep_impl(r"^[A-Z]{3,}$", session=s)
        assert set(r.paths) == {"/upper.txt"}

    async def test_case_insensitive(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await _seed(db, {"/a.py": "LOGIN happens here"})
        async with db._use_session() as s:
            r = await db._grep_impl("login", case_sensitive=False, session=s)
        assert "/a.py" in r.paths

    async def test_max_results_caps(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await _seed(db, {f"/f{i}.txt": "needle" for i in range(10)})
        async with db._use_session() as s:
            r = await db._grep_impl("needle", max_results=3, session=s)
        assert len(r) <= 3

    async def test_excludes_chunks(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await _seed(db, {"/source.py": "needle in a haystack"})
        async with db._use_session() as s:
            r = await db._grep_impl("needle", session=s)
        for c in r.candidates:
            assert c.kind == "file"

    async def test_with_candidate_filter(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await _seed(
            db,
            {
                "/a.py": "needle a",
                "/b.py": "needle b",
                "/c.py": "needle c",
            },
        )
        candidates = GroverResult(candidates=[Candidate(path="/a.py"), Candidate(path="/c.py")])
        async with db._use_session() as s:
            r = await db._grep_impl("needle", candidates=candidates, session=s)
        assert set(r.paths) == {"/a.py", "/c.py"}


class TestGlobPushdown:
    async def test_extension_glob(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await _seed(
            db,
            {
                "/src/foo.py": "x",
                "/src/bar.ts": "y",
                "/tests/baz.py": "z",
            },
        )
        async with db._use_session() as s:
            r = await db._glob_impl("**/*.py", session=s)
        assert set(r.paths) == {"/src/foo.py", "/tests/baz.py"}

    async def test_regex_pushdown_excludes_partial_match(self, request, db: MSSQLFileSystem):
        """LIKE-coarse matches that don't satisfy the glob are filtered server-side."""
        _mssql_required(request)
        await _seed(
            db,
            {
                "/test_foo.py": "x",
                "/foo_test_bar.py": "y",
                "/tests_dir/x.py": "z",
            },
        )
        async with db._use_session() as s:
            r = await db._glob_impl("test_*.py", session=s)
        # Only /test_foo.py satisfies the glob's "test_" prefix at root level
        assert "/test_foo.py" in r.paths
        assert "/foo_test_bar.py" not in r.paths

    async def test_results_sorted_by_path(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await _seed(db, {f"/dir/f{i}.txt": "x" for i in (3, 1, 2)})
        async with db._use_session() as s:
            r = await db._glob_impl("**/*.txt", session=s)
        assert r.paths == tuple(sorted(r.paths))
