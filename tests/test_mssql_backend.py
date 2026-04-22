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
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from vfs.backends.mssql import (
    MSSQLFileSystem,
    _extract_literal_terms,
    _quote_contains_term,
)
from vfs.paths import decompose_edge, edge_out_path
from vfs.results import Entry, VFSResult


def _node_paths(result: VFSResult) -> set[str]:
    return {e.path for e in result.entries if decompose_edge(e.path) is None}


def _edge_paths(result: VFSResult) -> set[str]:
    return {e.path for e in result.entries if decompose_edge(e.path) is not None}


async def _seed_graph(
    db: MSSQLFileSystem,
    *,
    nodes: tuple[str, ...],
    edges: tuple[tuple[str, str, str], ...],
) -> None:
    async with db._use_session() as session:
        for path in nodes:
            await db._write_impl(path, path, session=session)
        for source, target, edge_type in edges:
            await db._mkedge_impl(source, target, edge_type, session=session)

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


class TestResolveTable:
    """``_resolve_table`` qualifies the bare ``__tablename__`` with
    the configured schema for raw ``text()`` SQL.  The ORM's
    ``schema_translate_map`` rewrites compiled ``Table`` references but
    not opaque string SQL, so this helper is how MSSQL raw queries
    match the schema the ORM would hit.
    """

    def _fs(self, schema: str | None) -> MSSQLFileSystem:
        from vfs.models import VFSObject

        fs = MSSQLFileSystem.__new__(MSSQLFileSystem)
        fs._schema = schema
        fs._model = VFSObject
        return fs

    def test_qualifies_with_schema(self):
        fs = self._fs("vfs")
        assert fs._resolve_table() == "vfs.vfs_objects"

    def test_bare_name_when_schema_none(self):
        fs = self._fs(None)
        assert fs._resolve_table() == "vfs_objects"

    def test_bare_name_when_schema_empty_string(self):
        # Empty string is falsy — fall through to bare table name.
        fs = self._fs("")
        assert fs._resolve_table() == "vfs_objects"

    def test_independent_instances_have_independent_schemas(self):
        fs_a = self._fs("tenant_a")
        fs_b = self._fs("tenant_b")
        assert fs_a._resolve_table() == "tenant_a.vfs_objects"
        assert fs_b._resolve_table() == "tenant_b.vfs_objects"


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

    @staticmethod
    def _row(path: str, content: str, kind: str = "file") -> SimpleNamespace:
        """Build a pseudo-row matching the narrow-SELECT row interface."""
        return SimpleNamespace(
            path=path,
            kind=kind,
            content=content,
            size_bytes=len(content),
            updated_at=None,
            in_degree=None,
            out_degree=None,
        )

    def test_returns_per_line_metadata(self):
        from vfs.backends.database import DatabaseFileSystem

        regex = re.compile(r"foo")
        rows = {
            "/a.py": self._row("/a.py", "foo bar\nbaz qux\nfoo again"),
            "/b.py": self._row("/b.py", "no match here"),
        }
        cols = frozenset({"path", "kind", "content"})
        db = DatabaseFileSystem.__new__(DatabaseFileSystem)
        matched = db._collect_line_matches(rows, cols, regex, max_count=None)
        assert len(matched) == 1
        assert matched[0].path == "/a.py"
        assert matched[0].kind == "file"
        assert matched[0].score == 2.0
        assert matched[0].lines is not None
        assert [lm.match for lm in matched[0].lines] == [1, 3]

    def test_max_count_caps(self):
        from vfs.backends.database import DatabaseFileSystem

        regex = re.compile(r"hit")
        rows = {f"/f{i}.txt": self._row(f"/f{i}.txt", "hit it") for i in range(5)}
        cols = frozenset({"path", "kind", "content"})
        db = DatabaseFileSystem.__new__(DatabaseFileSystem)
        matched = db._collect_line_matches(rows, cols, regex, max_count=2)
        assert len(matched) == 2


# ---------------------------------------------------------------------------
# Glob in-memory candidate path (no DB needed)
# ---------------------------------------------------------------------------


class TestSchemaConstructorPassthrough:
    """The ``schema`` kwarg must flow all the way from
    ``MSSQLFileSystem.__init__`` → ``DatabaseFileSystem.__init__`` →
    ``VirtualFileSystem.__init__`` so ``self._schema`` is set on a fully
    constructed instance, not just when manually patched in.
    """

    def test_schema_kwarg_reaches_base_class(self):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def factory():
            yield None  # never actually used — constructor-only test

        fs = MSSQLFileSystem(session_factory=factory, schema="vfs")
        assert fs._schema == "vfs"
        assert fs._resolve_table() == "vfs.vfs_objects"

    def test_schema_defaults_to_none(self):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def factory():
            yield None

        fs = MSSQLFileSystem(session_factory=factory)
        assert fs._schema is None
        assert fs._resolve_table() == "vfs_objects"


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

        candidates = VFSResult(
            entries=[
                Entry(path="/src/foo.py", kind="file"),
                Entry(path="/src/bar.ts", kind="file"),
                Entry(path="/tests/foo.py", kind="file"),
            ]
        )
        result = await fs._glob_impl(
            "**/*.py",
            candidates=candidates,
            session=None,
        )
        assert sorted(result.paths) == ["/src/foo.py", "/tests/foo.py"]
        assert result.function == "glob"


class TestBuildGrepStructuralSql:
    """Unit-test the clause composer — no DB connection required.

    The helper is pure SQL-string construction, so we can exercise it
    by ``__new__``-ing a filesystem and calling it directly.  Assertions
    focus on: presence of expected fragments, parameter binding names,
    and composition with an empty alias for the glob code path.
    """

    @staticmethod
    def _fs(*, user_scoped: bool = False) -> MSSQLFileSystem:
        fs = MSSQLFileSystem.__new__(MSSQLFileSystem)
        fs._user_scoped = user_scoped
        fs._raise_on_error = False
        return fs

    def test_empty_returns_empty_clause(self):
        fs = self._fs()
        sql, params = fs._build_structural_sql(ext=(), ext_not=(), paths=(), globs=(), globs_not=(), user_id=None)
        assert sql == ""
        assert params == {}

    def test_ext_pushdown_uses_in_list(self):
        fs = self._fs()
        sql, params = fs._build_structural_sql(
            ext=("py", "pyi"), ext_not=(), paths=(), globs=(), globs_not=(), user_id=None
        )
        assert "o.ext IN (:gext0, :gext1)" in sql
        assert params == {"gext0": "py", "gext1": "pyi"}

    def test_ext_not_pushdown(self):
        fs = self._fs()
        sql, params = fs._build_structural_sql(ext=(), ext_not=("md",), paths=(), globs=(), globs_not=(), user_id=None)
        assert "o.ext NOT IN (:gextn0)" in sql
        assert params == {"gextn0": "md"}

    def test_positional_paths_eq_or_prefix(self):
        fs = self._fs()
        sql, params = fs._build_structural_sql(
            ext=(),
            ext_not=(),
            paths=("/src", "lib"),
            globs=(),
            globs_not=(),
            user_id=None,
        )
        assert "o.path = :gpeq0" in sql
        assert "o.path LIKE :gppre0 ESCAPE '\\'" in sql
        assert params["gpeq0"] == "/src"
        assert params["gppre0"] == "/src/%"
        # Relative "lib" normalises to absolute "/lib"
        assert params["gpeq1"] == "/lib"
        assert params["gppre1"] == "/lib/%"

    def test_glob_positive_has_like_and_regex(self):
        fs = self._fs()
        sql, params = fs._build_structural_sql(
            ext=(),
            ext_not=(),
            paths=(),
            globs=("**/test_*.py",),
            globs_not=(),
            user_id=None,
        )
        assert "o.path LIKE :ggl0 ESCAPE '\\'" in sql
        assert "REGEXP_LIKE(o.path, :ggr0, 'c')" in sql
        assert "ggl0" in params
        assert "ggr0" in params

    def test_glob_negative_is_not_regexp_like(self):
        fs = self._fs()
        sql, params = fs._build_structural_sql(
            ext=(),
            ext_not=(),
            paths=(),
            globs=(),
            globs_not=("**/vendor/**",),
            user_id=None,
        )
        assert "NOT (REGEXP_LIKE(o.path, :ggnr0, 'c'))" in sql
        assert "ggnr0" in params

    def test_user_scope_appends_like_clause(self):
        fs = self._fs(user_scoped=True)
        sql, params = fs._build_structural_sql(ext=(), ext_not=(), paths=(), globs=(), globs_not=(), user_id="alice")
        assert "o.path LIKE :user_scope ESCAPE '\\'" in sql
        assert params["user_scope"] == "/alice/%"

    def test_user_scope_scopes_positional_paths(self):
        fs = self._fs(user_scoped=True)
        _sql, params = fs._build_structural_sql(
            ext=(),
            ext_not=(),
            paths=("/src",),
            globs=(),
            globs_not=(),
            user_id="alice",
        )
        assert params["gpeq0"] == "/alice/src"
        assert params["gppre0"] == "/alice/src/%"

    def test_empty_alias_drops_table_prefix(self):
        """``_glob_impl`` passes ``alias=""`` since its SQL has no table alias."""
        fs = self._fs()
        sql, params = fs._build_structural_sql(
            ext=("py",),
            ext_not=(),
            paths=("/src",),
            globs=(),
            globs_not=(),
            user_id=None,
            alias="",
        )
        assert "ext IN (:gext0)" in sql
        assert "o.ext" not in sql
        assert "path = :gpeq0" in sql
        assert "o.path" not in sql
        assert params["gext0"] == "py"
        assert params["gpeq0"] == "/src"

    def test_clauses_joined_with_leading_and(self):
        fs = self._fs()
        sql, _ = fs._build_structural_sql(ext=("py",), ext_not=(), paths=(), globs=(), globs_not=(), user_id=None)
        assert sql.startswith(" AND ")

    def test_all_filters_compose_with_and(self):
        fs = self._fs()
        sql, _ = fs._build_structural_sql(
            ext=("py",),
            ext_not=("pyc",),
            paths=("/src",),
            globs=("**/*.py",),
            globs_not=("**/test_*.py",),
            user_id=None,
        )
        assert sql.count(" AND ") >= 5


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
    catalog = "vfs_test_ftcat"
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
        for c in r.entries:
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
        candidates = VFSResult(entries=[Entry(path="/a.py"), Entry(path="/c.py")])
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
        assert r.entries[0].score == 1.0

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
            r = await db._grep_impl("login", case_mode="insensitive", session=s)
        assert "/a.py" in r.paths

    async def test_max_count_caps(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await _seed(db, {f"/f{i}.txt": "needle" for i in range(10)})
        async with db._use_session() as s:
            r = await db._grep_impl("needle", max_count=3, session=s)
        assert len(r) <= 3

    async def test_excludes_chunks(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await _seed(db, {"/source.py": "needle in a haystack"})
        async with db._use_session() as s:
            r = await db._grep_impl("needle", session=s)
        for c in r.entries:
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
        candidates = VFSResult(entries=[Entry(path="/a.py"), Entry(path="/c.py")])
        async with db._use_session() as s:
            r = await db._grep_impl("needle", candidates=candidates, session=s)
        assert set(r.paths) == {"/a.py", "/c.py"}


class TestGrepRipgrepFiltersMssql:
    """Integration tests for the rg-style structural filter pushdown.

    Exercises the four SQL templates (CONTAINSTABLE/Direct x lines/files)
    plus ``ext`` / positional ``paths`` / ``globs`` filters, context
    windows, the ``fixed_strings`` / ``word_regexp`` / ``invert_match``
    modifiers, and smart-case behaviour — all against real SQL Server.

    Corpus note: SQL Server Full-Text word-breaks content into tokens,
    so ``CONTAINS "grep"`` matches the word "grep" but not "grepper".
    The seed uses standalone "grep" tokens where cross-file matches
    are asserted, to stay independent of FTS tokenization quirks.
    """

    async def _seed_corpus(self, db: MSSQLFileSystem) -> None:
        await _seed(
            db,
            {
                "/src/a.py": "def grep():\n    pass\n",
                "/src/b.py": "class Grep:\n    pass\n",
                "/src/sub/c.py": "grep = None\n",
                "/src/README.md": "# grep docs\n",
                "/lib/d.py": "def helper():\n    pass\n",
                "/lib/e.js": "function grep() {}\n",
                "/test_grep.py": "def test_grep():\n    pass\n",
            },
        )

    async def test_ext_filter_narrows_to_python(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await self._seed_corpus(db)
        async with db._use_session() as s:
            r = await db._grep_impl("grep", ext=("py",), session=s)
        assert "/lib/e.js" not in r.paths
        assert "/src/README.md" not in r.paths
        assert "/src/a.py" in r.paths

    async def test_ext_multi_accepts_py_and_md(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await self._seed_corpus(db)
        async with db._use_session() as s:
            r = await db._grep_impl("grep", ext=("py", "md"), session=s)
        assert "/src/README.md" in r.paths
        assert "/src/a.py" in r.paths
        assert "/lib/e.js" not in r.paths

    async def test_ext_not_excludes_python(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await self._seed_corpus(db)
        async with db._use_session() as s:
            r = await db._grep_impl("grep", ext_not=("py",), session=s)
        assert "/src/a.py" not in r.paths
        assert "/lib/e.js" in r.paths

    async def test_positional_path_prefix(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await self._seed_corpus(db)
        async with db._use_session() as s:
            r = await db._grep_impl("grep", paths=("/src",), session=s)
        assert all(p.startswith("/src/") for p in r.paths)
        assert "/lib/e.js" not in r.paths

    async def test_multiple_positional_paths_ored(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await self._seed_corpus(db)
        async with db._use_session() as s:
            r = await db._grep_impl("grep", paths=("/src/sub", "/lib"), session=s)
        assert set(r.paths) == {"/src/sub/c.py", "/lib/e.js"}

    async def test_positive_glob_filter(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await self._seed_corpus(db)
        async with db._use_session() as s:
            r = await db._grep_impl("grep", globs=("**/test_*.py",), session=s)
        assert r.paths == ("/test_grep.py",)

    async def test_negative_glob_excludes_matches(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await self._seed_corpus(db)
        async with db._use_session() as s:
            r = await db._grep_impl(
                "grep",
                ext=("py",),
                globs_not=("**/test_*.py",),
                session=s,
            )
        assert "/test_grep.py" not in r.paths
        assert "/src/a.py" in r.paths

    async def test_output_mode_files_path_only(self, request, db: MSSQLFileSystem):
        """``output_mode='files'`` uses the path-only SELECT — metadata
        carries no line_matches because content was never fetched."""
        _mssql_required(request)
        await self._seed_corpus(db)
        async with db._use_session() as s:
            r = await db._grep_impl("grep", ext=("py",), output_mode="files", session=s)
        assert "/src/a.py" in r.paths
        entry = r.entries[0]
        assert entry.lines is None

    async def test_output_mode_count_returns_counts(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await _seed(db, {"/a.py": "TODO\nok\nTODO\nTODO"})
        async with db._use_session() as s:
            r = await db._grep_impl("TODO", output_mode="count", session=s)
        entry = r.entries[0]
        assert entry.score == 3.0
        assert entry.lines is None

    async def test_context_window_after(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await _seed(db, {"/a.py": "l1\nl2 MATCH\nl3\nl4\nl5"})
        async with db._use_session() as s:
            r = await db._grep_impl("MATCH", after_context=2, session=s)
        entry = r.entries[0]
        assert entry.lines is not None
        assert entry.lines[0].match == 2
        assert entry.lines[0].start == 2
        assert entry.lines[0].end == 4

    async def test_fixed_strings_treats_regex_as_literal(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await _seed(db, {"/a.py": "foo.bar\nfooxbar"})
        async with db._use_session() as s:
            r = await db._grep_impl("foo.bar", fixed_strings=True, session=s)
        assert r.entries[0].score == 1.0

    async def test_word_regexp_boundaries(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await _seed(db, {"/a.py": "grep\ngrepper\nregrep"})
        async with db._use_session() as s:
            r = await db._grep_impl("grep", word_regexp=True, session=s)
        assert r.entries[0].score == 1.0

    async def test_invert_match_returns_non_matching_lines(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await _seed(db, {"/a.py": "alpha\nbeta\ngamma"})
        async with db._use_session() as s:
            r = await db._grep_impl("beta", invert_match=True, session=s)
        assert r.entries[0].score == 2.0

    async def test_smart_case_lowercase_matches_upper(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await _seed(db, {"/a.py": "FOO\nfoo"})
        async with db._use_session() as s:
            r = await db._grep_impl("foo", case_mode="smart", session=s)
        assert r.entries[0].score == 2.0

    async def test_combined_filters_and_together(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await self._seed_corpus(db)
        async with db._use_session() as s:
            r = await db._grep_impl(
                "grep",
                paths=("/src",),
                ext=("py",),
                globs_not=("**/b.py",),
                session=s,
            )
        assert set(r.paths) == {"/src/a.py", "/src/sub/c.py"}


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

    async def test_glob_ext_filter_narrows(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await _seed(db, {"/src/a.py": "x", "/src/b.ts": "y"})
        async with db._use_session() as s:
            r = await db._glob_impl("**/*", ext=("py",), session=s)
        assert "/src/a.py" in r.paths
        assert "/src/b.ts" not in r.paths

    async def test_glob_positional_path_prefix(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await _seed(db, {"/src/a.py": "x", "/lib/b.py": "y"})
        async with db._use_session() as s:
            r = await db._glob_impl("**/*.py", paths=("/src",), session=s)
        assert "/src/a.py" in r.paths
        assert "/lib/b.py" not in r.paths

    async def test_glob_max_count_caps(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await _seed(db, {f"/f{i}.py": "x" for i in range(5)})
        async with db._use_session() as s:
            r = await db._glob_impl("/*.py", max_count=2, session=s)
        assert len(r) == 2

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

    async def test_glob_extension_pattern_matches_files_only(self, request, db: MSSQLFileSystem):
        """`**/*.py` should index-seek on ext and return only files."""
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

    async def test_glob_prefix_and_extension_narrows(self, request, db: MSSQLFileSystem):
        """`src/**/*.py` should push both the prefix and the ext."""
        _mssql_required(request)
        await _seed(
            db,
            {
                "/src/a.py": "x",
                "/src/sub/b.py": "y",
                "/lib/c.py": "z",
            },
        )
        async with db._use_session() as s:
            r = await db._glob_impl("src/**/*.py", session=s)
        assert set(r.paths) == {"/src/a.py", "/src/sub/b.py"}

    async def test_glob_user_ext_intersects_with_decomposed_ext(self, request, db: MSSQLFileSystem):
        """Caller ext is authoritative: empty intersection → empty result."""
        _mssql_required(request)
        await _seed(db, {"/src/a.py": "x", "/src/b.py": "y"})
        async with db._use_session() as s:
            r = await db._glob_impl("**/*.py", ext=("js",), session=s)
        assert r.paths == ()

    async def test_glob_user_paths_not_broadened_by_glob_prefix(self, request, db: MSSQLFileSystem):
        """Caller-supplied paths are not broadened by the glob's prefix."""
        _mssql_required(request)
        await _seed(db, {"/src/a.py": "x", "/docs/b.py": "y"})
        async with db._use_session() as s:
            r = await db._glob_impl("src/**/*.py", paths=("/docs",), session=s)
        assert r.paths == ()

    async def test_glob_prefix_only_keeps_semantics_against_self(self, request, db: MSSQLFileSystem):
        """`tests/**` must match children but not `/tests` itself."""
        _mssql_required(request)
        await _seed(db, {"/tests/a.py": "x"})
        async with db._use_session() as s:
            r = await db._glob_impl("tests/**", session=s)
        assert "/tests/a.py" in r.paths
        assert "/tests" not in r.paths

    async def test_glob_bounded_depth_not_over_matched(self, request, db: MSSQLFileSystem):
        """`src/*.py` must not match `src/sub/b.py` — residual regex gates depth."""
        _mssql_required(request)
        await _seed(db, {"/src/a.py": "x", "/src/sub/b.py": "y"})
        async with db._use_session() as s:
            r = await db._glob_impl("src/*.py", session=s)
        assert set(r.paths) == {"/src/a.py"}


class TestVerifyNativeGraphSchema:
    async def test_passes_when_installed(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await db.verify_native_graph_schema()

    async def test_missing_proc(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        async with db._use_session() as s:
            await s.execute(
                text(f"DROP PROCEDURE IF EXISTS {db._native_graph_proc_name()}")
            )
        db._native_graph_verified = False
        with pytest.raises(RuntimeError, match="native graph traversal procedure"):
            await db.verify_native_graph_schema()


class TestMeetingSubgraphNative:
    async def test_empty_seeds_returns_empty(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        result = await db.meeting_subgraph(VFSResult(entries=[]))
        assert result.success
        assert result.entries == []

    async def test_single_seed_returns_seed_only(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await _seed_graph(
            db,
            nodes=("/a.py", "/b.py"),
            edges=(("/a.py", "/b.py", "imports"),),
        )
        result = await db.meeting_subgraph(VFSResult(entries=[Entry(path="/a.py")]))
        assert result.success
        assert _node_paths(result) == {"/a.py"}
        assert _edge_paths(result) == set()

    async def test_returns_nodes_and_edge_entries(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await _seed_graph(
            db,
            nodes=("/a.py", "/b.py", "/c.py", "/d.py"),
            edges=(
                ("/a.py", "/b.py", "imports"),
                ("/b.py", "/c.py", "imports"),
                ("/a.py", "/d.py", "imports"),
            ),
        )
        result = await db.meeting_subgraph(
            VFSResult(entries=[Entry(path="/a.py"), Entry(path="/c.py")])
        )
        assert result.success
        assert _node_paths(result) == {"/a.py", "/b.py", "/c.py"}
        assert _edge_paths(result) == {
            edge_out_path("/a.py", "/b.py", "imports"),
            edge_out_path("/b.py", "/c.py", "imports"),
        }

    async def test_strips_dangling_spurs(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await _seed_graph(
            db,
            nodes=("/a.py", "/b.py", "/c.py", "/d.py", "/e.py"),
            edges=(
                ("/a.py", "/b.py", "imports"),
                ("/b.py", "/c.py", "imports"),
                ("/a.py", "/d.py", "imports"),
                ("/c.py", "/e.py", "imports"),
            ),
        )
        result = await db.meeting_subgraph(
            VFSResult(entries=[Entry(path="/a.py"), Entry(path="/c.py")])
        )
        assert _node_paths(result) == {"/a.py", "/b.py", "/c.py"}

    async def test_seeds_not_in_graph_yield_empty(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await _seed_graph(
            db,
            nodes=("/a.py", "/b.py"),
            edges=(("/a.py", "/b.py", "imports"),),
        )
        result = await db.meeting_subgraph(
            VFSResult(entries=[Entry(path="/ghost.py"), Entry(path="/phantom.py")])
        )
        assert result.success
        assert result.entries == []

    async def test_deterministic_for_tie_case(self, request, db: MSSQLFileSystem):
        _mssql_required(request)
        await _seed_graph(
            db,
            nodes=("/a.py", "/b.py", "/c.py", "/d.py"),
            edges=(
                ("/a.py", "/b.py", "imports"),
                ("/b.py", "/d.py", "imports"),
                ("/a.py", "/c.py", "imports"),
                ("/c.py", "/d.py", "imports"),
            ),
        )
        result = await db.meeting_subgraph(
            VFSResult(entries=[Entry(path="/a.py"), Entry(path="/d.py")])
        )
        assert result.success
        assert _node_paths(result) == {"/a.py", "/b.py", "/d.py"}
        assert _edge_paths(result) == {
            edge_out_path("/a.py", "/b.py", "imports"),
            edge_out_path("/b.py", "/d.py", "imports"),
        }
