"""Tests for PostgresFileSystem.

Pure helper tests run in the default suite. Integration tests are gated on
``--postgres`` and require a local PostgreSQL instance plus the optional
``pgvector`` dependency.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text as sql_text

from vfs.backends.database import DatabaseFileSystem
from vfs.backends.postgres import (
    PostgresFileSystem,
    _build_plainto_tsquery,
    _build_tsquery,
    _contains_unescaped_anchor,
    _parse_vector_dimension,
    _pgvector_distance_operator,
    _pgvector_distance_to_score,
    _python_regex_to_postgres,
    _quote_tsquery_term,
)
from vfs.models import _build_entry_table_class, postgres_vector_column_spec
from vfs.paths import decompose_edge, edge_out_path
from vfs.results import Entry, VFSResult
from vfs.vector import NativeEmbeddingConfig, Vector


class _MockEmbeddingProvider:
    def __init__(self, vector: list[float]) -> None:
        self._vector = vector

    async def embed(self, text: str) -> Vector:
        return Vector[len(self._vector)](self._vector)

    async def embed_batch(self, texts: list[str]) -> list[Vector]:
        return [Vector[len(self._vector)](self._vector) for _ in texts]

    @property
    def dimensions(self) -> int:
        return len(self._vector)

    @property
    def model_name(self) -> str:
        return "mock-postgres-provider"


class _MockVectorStore:
    def __init__(self) -> None:
        self.last_vector: list[float] | None = None

    async def query(self, vector, *, k=10, paths=None, user_id=None):
        self.last_vector = list(vector)
        return [type("Hit", (), {"path": "/override.py", "score": 0.9})()]

    async def upsert(self, items):
        return None

    async def delete(self, paths):
        return None


def _normalize_sql(statement: str) -> str:
    return " ".join(statement.split()).lower()


def _read_statements_against_objects(statements: list[str]) -> list[str]:
    return [
        _normalize_sql(statement)
        for statement in statements
        if statement.lstrip().upper().startswith(("SELECT", "WITH")) and "from vfs_entries" in statement.lower()
    ]


def _parse_vector_text(value: str) -> list[float]:
    return [float(part) for part in value.strip("[]").split(",") if part]


async def _seed_native_embeddings(db: PostgresFileSystem, rows: dict[str, list[float]]) -> None:
    async with db._use_session() as session:
        await db._write_impl(
            entries=[
                db._model(path=path, content=path, embedding=Vector[len(vector)](vector))
                for path, vector in rows.items()
            ],
            session=session,
        )


async def _make_native_metric_db(engine, *, operator_class: str) -> PostgresFileSystem:
    if engine.dialect.name != "postgresql":
        pytest.skip("requires --postgres flag and a running PostgreSQL instance")
    native_embedding = NativeEmbeddingConfig(dimension=4, operator_class=operator_class)
    model = _build_entry_table_class(table_name="vfs_entries", native_embedding=native_embedding)
    spec = postgres_vector_column_spec(model)
    async with engine.begin() as conn:
        await conn.execute(sql_text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(sql_text(f"DROP TABLE IF EXISTS {model.__tablename__} CASCADE"))
        await conn.run_sync(model.metadata.create_all)
        await conn.execute(
            sql_text(
                f"""
                ALTER TABLE {model.__tablename__}
                ADD COLUMN IF NOT EXISTS search_tsv tsvector GENERATED ALWAYS AS (
                    to_tsvector('simple', coalesce(content, ''))
                ) STORED
                """
            )
        )
        await conn.execute(
            sql_text(
                f"""
                CREATE INDEX IF NOT EXISTS ix_{model.__tablename__}_search_tsv_gin
                ON {model.__tablename__} USING GIN (search_tsv)
                WHERE content IS NOT NULL
                  AND deleted_at IS NULL
                  AND kind != 'version'
                """
            )
        )
        await conn.execute(sql_text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.execute(
            sql_text(
                f"""
                CREATE INDEX IF NOT EXISTS ix_{model.__tablename__}_path_pattern
                ON {model.__tablename__} (path text_pattern_ops)
                WHERE deleted_at IS NULL
                """
            )
        )
        await conn.execute(
            sql_text(
                f"""
                CREATE INDEX IF NOT EXISTS ix_{model.__tablename__}_path_trgm_gin
                ON {model.__tablename__} USING GIN (path gin_trgm_ops)
                WHERE deleted_at IS NULL
                """
            )
        )
        await conn.execute(
            sql_text(
                f"""
                CREATE INDEX IF NOT EXISTS ix_{model.__tablename__}_content_trgm_gin
                ON {model.__tablename__} USING GIN (content gin_trgm_ops)
                WHERE kind = 'file'
                  AND content IS NOT NULL
                  AND deleted_at IS NULL
                """
            )
        )
        await conn.execute(
            sql_text(
                f"""
                CREATE INDEX IF NOT EXISTS {spec.index_name}
                ON {model.__tablename__} USING {spec.index_method}
                ({spec.column_name} {spec.operator_class})
                WHERE {spec.column_name} IS NOT NULL
                """
            )
        )
    return PostgresFileSystem(engine=engine, native_embedding=native_embedding)


async def _seed_graph(
    db: PostgresFileSystem,
    *,
    nodes: tuple[str, ...],
    edges: tuple[tuple[str, str, str], ...],
) -> None:
    async with db._use_session() as session:
        for path in nodes:
            await db._write_impl(path, path, session=session)
        for source, target, edge_type in edges:
            await db._mkedge_impl(source, target, edge_type, session=session)


def _node_paths(result: VFSResult) -> set[str]:
    return {entry.path for entry in result.entries if not _is_connection_path(entry.path)}


def _edge_paths(result: VFSResult) -> set[str]:
    return {entry.path for entry in result.entries if _is_connection_path(entry.path)}


def _is_connection_path(path: str) -> bool:
    return decompose_edge(path) is not None


def _connection_path(source: str, target: str, edge_type: str) -> str:
    return edge_out_path(source, target, edge_type)


def _collect_index_names(plan_node: object) -> set[str]:
    names: set[str] = set()
    if isinstance(plan_node, dict):
        index_name = plan_node.get("Index Name")
        if isinstance(index_name, str):
            names.add(index_name)
        for value in plan_node.values():
            names |= _collect_index_names(value)
    elif isinstance(plan_node, list):
        for item in plan_node:
            names |= _collect_index_names(item)
    return names


async def _explain_index_names(
    engine,
    sql: str,
    params: dict[str, object] | None = None,
    *,
    prefer_bitmap: bool = False,
) -> set[str]:
    params = params or {}
    async with engine.connect() as conn:
        await conn.execute(sql_text("SET enable_seqscan = off"))
        if prefer_bitmap:
            await conn.execute(sql_text("SET enable_indexscan = off"))
            await conn.execute(sql_text("SET enable_indexonlyscan = off"))
        plan_row = (await conn.execute(sql_text(f"EXPLAIN (FORMAT JSON) {sql}"), params)).scalar_one()
    return _collect_index_names(plan_row)


class TestTsqueryHelpers:
    def test_quote_tsquery_term_escapes_single_quote(self):
        assert _quote_tsquery_term("don't") == "'don''t'"

    def test_build_tsquery_or(self):
        assert _build_tsquery(["auth", "timeout"], operator="|") == "'auth' | 'timeout'"

    def test_build_tsquery_and(self):
        assert _build_tsquery(("auth", "timeout"), operator="&") == "'auth' & 'timeout'"

    def test_build_plainto_tsquery_single_term(self):
        sql, params = _build_plainto_tsquery(["auth"], config="simple")
        assert sql == "plainto_tsquery('simple', :t0)"
        assert params == {"t0": "auth"}

    def test_build_plainto_tsquery_multiple_terms(self):
        sql, params = _build_plainto_tsquery(["auth", "timeout"], config="simple")
        assert sql == "plainto_tsquery('simple', :t0) || plainto_tsquery('simple', :t1)"
        assert params == {"t0": "auth", "t1": "timeout"}


class TestResolveTable:
    def test_qualifies_schema(self):
        fs = PostgresFileSystem.__new__(PostgresFileSystem)
        fs._schema = "vfs"
        fs._model = _build_entry_table_class(
            table_name="vfs_entries",
            native_embedding=NativeEmbeddingConfig(dimension=4),
        )
        assert fs._resolve_table() == "vfs.vfs_entries"

    def test_bare_name_without_schema(self):
        fs = PostgresFileSystem.__new__(PostgresFileSystem)
        fs._schema = None
        fs._model = _build_entry_table_class(
            table_name="vfs_entries",
            native_embedding=NativeEmbeddingConfig(dimension=4),
        )
        assert fs._resolve_table() == "vfs_entries"


class TestRegexTranslation:
    def test_word_boundary_maps_to_postgres_are(self):
        assert _python_regex_to_postgres(r"\bfoo\b") == r"\yfoo\y"

    def test_non_capturing_group_downgraded_to_plain_group(self):
        assert _python_regex_to_postgres(r"(?:foo|bar)") == r"(foo|bar)"


class TestRegexPushdownSafety:
    def test_detects_line_anchor_tokens(self):
        assert _contains_unescaped_anchor("^todo")
        assert _contains_unescaped_anchor(r"todo$")
        assert _contains_unescaped_anchor(r"\A.todo")
        assert _contains_unescaped_anchor(r"todo\Z")

    def test_ignores_escaped_and_character_class_tokens(self):
        assert not _contains_unescaped_anchor(r"\^todo\$")
        assert not _contains_unescaped_anchor(r"[$^]")
        assert not _contains_unescaped_anchor(r"\bTODO\b")


class TestParseVectorDimension:
    def test_accepts_dimensioned_vector(self):
        assert _parse_vector_dimension("vector(1536)") == 1536

    def test_rejects_non_vector(self):
        assert _parse_vector_dimension("text") is None


class TestPgvectorMetricHelpers:
    @pytest.mark.parametrize(
        ("operator_class", "sql_operator"),
        [
            ("vector_cosine_ops", "<=>"),
            ("vector_ip_ops", "<#>"),
            ("vector_l2_ops", "<->"),
        ],
    )
    def test_distance_operator_matches_operator_class(self, operator_class: str, sql_operator: str):
        assert _pgvector_distance_operator(operator_class) == sql_operator

    @pytest.mark.parametrize(
        ("operator_class", "distance", "score"),
        [
            ("vector_cosine_ops", 0.0, 1.0),
            ("vector_ip_ops", -2.5, 2.5),
            ("vector_l2_ops", 3.0, 0.25),
        ],
    )
    def test_distance_to_score_matches_metric(self, operator_class: str, distance: float, score: float):
        assert _pgvector_distance_to_score(operator_class, distance) == pytest.approx(score)

    def test_unknown_operator_class_rejected(self):
        with pytest.raises(RuntimeError, match="only supports pgvector operator classes"):
            _pgvector_distance_operator("vector_weird_ops")


class TestVerifyNativeSearchSchema:
    async def test_success(self, postgres_native_db):
        await postgres_native_db.verify_native_search_schema()

    async def test_missing_pg_trgm_extension(self, postgres_native_db, engine):
        async with engine.begin() as conn:
            await conn.execute(sql_text("DROP EXTENSION IF EXISTS pg_trgm CASCADE"))
        with pytest.raises(RuntimeError, match="pg_trgm extension"):
            await postgres_native_db.verify_native_search_schema()

    async def test_missing_vector_extension(self, postgres_legacy_db):
        engine = postgres_legacy_db._engine
        assert engine is not None
        async with engine.begin() as conn:
            await conn.execute(sql_text("DROP EXTENSION IF EXISTS vector"))

        fs = PostgresFileSystem(
            engine=engine,
            native_embedding=NativeEmbeddingConfig(dimension=4),
        )
        with pytest.raises(RuntimeError, match="pgvector extension"):
            await fs.verify_native_search_schema()

    async def test_rejects_non_native_embedding_column(self, postgres_legacy_db):
        engine = postgres_legacy_db._engine
        assert engine is not None
        fs = PostgresFileSystem(
            engine=engine,
            native_embedding=NativeEmbeddingConfig(dimension=4),
        )
        with pytest.raises(RuntimeError, match="non-native embedding column"):
            await fs.verify_native_search_schema()

    async def test_dimension_mismatch(self, postgres_native_db, engine):
        fs = PostgresFileSystem(
            engine=engine,
            native_embedding=NativeEmbeddingConfig(dimension=8),
        )
        with pytest.raises(RuntimeError, match="dimension mismatch"):
            await fs.verify_native_search_schema()

    async def test_missing_search_tsv_column(self, postgres_native_db, engine):
        async with engine.begin() as conn:
            await conn.execute(sql_text("ALTER TABLE vfs_entries DROP COLUMN IF EXISTS search_tsv CASCADE"))
        with pytest.raises(RuntimeError, match="search_tsv"):
            await postgres_native_db.verify_native_search_schema()

    async def test_missing_fts_index(self, postgres_native_db, engine):
        async with engine.begin() as conn:
            await conn.execute(sql_text("DROP INDEX IF EXISTS ix_vfs_entries_search_tsv_gin"))
        with pytest.raises(RuntimeError, match=r"GIN index on 'vfs_entries\.search_tsv'"):
            await postgres_native_db.verify_native_search_schema()

    async def test_missing_path_pattern_index(self, postgres_native_db, engine):
        async with engine.begin() as conn:
            await conn.execute(sql_text("DROP INDEX IF EXISTS ix_vfs_entries_path_pattern"))
        with pytest.raises(RuntimeError, match=r"text_pattern_ops index on 'vfs_entries\.path'"):
            await postgres_native_db.verify_native_search_schema()

    async def test_missing_path_trgm_index(self, postgres_native_db, engine):
        async with engine.begin() as conn:
            await conn.execute(sql_text("DROP INDEX IF EXISTS ix_vfs_entries_path_trgm_gin"))
        with pytest.raises(RuntimeError, match=r"trigram GIN index on 'vfs_entries\.path'"):
            await postgres_native_db.verify_native_search_schema()

    async def test_missing_content_trgm_index(self, postgres_native_db, engine):
        async with engine.begin() as conn:
            await conn.execute(sql_text("DROP INDEX IF EXISTS ix_vfs_entries_content_trgm_gin"))
        with pytest.raises(RuntimeError, match=r"trigram GIN index on 'vfs_entries\.content'"):
            await postgres_native_db.verify_native_search_schema()

    async def test_rejects_wrong_partial_predicate(self, postgres_native_db, engine):
        async with engine.begin() as conn:
            await conn.execute(sql_text("DROP INDEX IF EXISTS ix_vfs_entries_search_tsv_gin"))
            await conn.execute(
                sql_text("""
                    CREATE INDEX ix_vfs_entries_search_tsv_gin
                    ON vfs_entries USING GIN (search_tsv)
                    WHERE deleted_at IS NULL
                """)
            )
        with pytest.raises(RuntimeError, match="live-search predicate"):
            await postgres_native_db.verify_native_search_schema()

    async def test_rejects_non_generated_search_tsv_column(self, postgres_native_db, engine):
        async with engine.begin() as conn:
            await conn.execute(sql_text("DROP INDEX IF EXISTS ix_vfs_entries_search_tsv_gin"))
            await conn.execute(sql_text("ALTER TABLE vfs_entries DROP COLUMN IF EXISTS search_tsv CASCADE"))
            await conn.execute(sql_text("ALTER TABLE vfs_entries ADD COLUMN search_tsv tsvector"))
            await conn.execute(
                sql_text("""
                    CREATE INDEX ix_vfs_entries_search_tsv_gin
                    ON vfs_entries USING GIN (search_tsv)
                    WHERE content IS NOT NULL
                      AND deleted_at IS NULL
                      AND kind != 'version'
                """)
            )
        with pytest.raises(RuntimeError, match="GENERATED ALWAYS"):
            await postgres_native_db.verify_native_search_schema()

    async def test_missing_vector_index(self, postgres_native_db, engine):
        spec = postgres_vector_column_spec(postgres_native_db._model)
        async with engine.begin() as conn:
            await conn.execute(sql_text(f"DROP INDEX IF EXISTS {spec.index_name}"))
        with pytest.raises(RuntimeError, match="ANN index"):
            await postgres_native_db.verify_native_search_schema()

    async def test_vector_store_override_skips_vector_requirements(self, postgres_legacy_db):
        engine = postgres_legacy_db._engine
        assert engine is not None
        fs = PostgresFileSystem(engine=engine, vector_store=_MockVectorStore())
        await fs.verify_native_search_schema()


class TestLexicalSearch:
    async def test_uses_single_native_fts_query_with_bounded_scores(self, postgres_native_db, sql_capture):
        async with postgres_native_db._use_session() as session:
            await postgres_native_db._write_impl("/dense.py", "authentication timeout", session=session)
            await postgres_native_db._write_impl(
                "/bm25.py",
                "authentication authentication authentication timeout handler",
                session=session,
            )
            await postgres_native_db._write_impl("/none.py", "unrelated", session=session)

        sql_capture.reset()
        async with postgres_native_db._use_session() as session:
            result = await postgres_native_db._lexical_search_impl("authentication timeout", k=2, session=session)

        assert result.paths == ("/bm25.py", "/dense.py")
        assert result.entries[0].content == "authentication authentication authentication timeout handler"
        assert all(entry.score is not None and 0.0 <= entry.score < 1.0 for entry in result.entries)
        assert result.entries[0].score is not None
        assert result.entries[1].score is not None
        assert result.entries[0].score >= result.entries[1].score
        selects = _read_statements_against_objects(sql_capture.statements)
        assert any("search_tsv" in statement and "@@" in statement for statement in selects)
        assert any("ts_rank_cd(" in statement and "as score" in statement for statement in selects)
        assert len(selects) == 1

    async def test_multi_term_query_uses_bound_plainto_tsquery_or(self, postgres_native_db, sql_capture):
        async with postgres_native_db._use_session() as session:
            await postgres_native_db._write_impl("/focus.py", "authentication timeout", session=session)

        sql_capture.reset()
        async with postgres_native_db._use_session() as session:
            await postgres_native_db._lexical_search_impl("authentication timeout", k=1, session=session)

        selects = _read_statements_against_objects(sql_capture.statements)
        assert any(
            statement.count("plainto_tsquery('simple',") == 2 and "||" in statement.partition("as q")[0]
            for statement in selects
        )

    async def test_single_term_query_uses_single_plainto_tsquery(self, postgres_native_db, sql_capture):
        async with postgres_native_db._use_session() as session:
            await postgres_native_db._write_impl("/focus.py", "authentication timeout", session=session)

        sql_capture.reset()
        async with postgres_native_db._use_session() as session:
            await postgres_native_db._lexical_search_impl("authentication", k=1, session=session)

        selects = _read_statements_against_objects(sql_capture.statements)
        assert any(
            statement.count("plainto_tsquery('simple',") == 1 and "||" not in statement.partition("as q")[0]
            for statement in selects
        )

    async def test_candidates_path_stays_on_base_python_bm25(self, postgres_native_db, sql_capture):
        candidates = VFSResult(
            function="grep",
            entries=[
                Entry(path="/a.py", kind="file", content="authentication timeout"),
                Entry(path="/b.py", kind="file", content="authentication"),
            ],
        )

        sql_capture.reset()
        async with postgres_native_db._use_session() as session:
            result = await postgres_native_db._lexical_search_impl(
                "authentication timeout",
                k=1,
                candidates=candidates,
                session=session,
            )

        assert result.paths == ("/a.py",)
        assert all("search_tsv @@ query.q" not in _normalize_sql(statement) for statement in sql_capture.statements)


class TestGrep:
    async def test_regex_pushdown_preserves_line_matches(self, postgres_native_db):
        async with postgres_native_db._use_session() as session:
            await postgres_native_db._write_impl("/a.py", "TODO\nok\nTODO", session=session)

        async with postgres_native_db._use_session() as session:
            result = await postgres_native_db._grep_impl("TODO", session=session)
        assert result.paths == ("/a.py",)
        assert result.entries[0].score == 2.0
        assert result.entries[0].lines is not None
        assert [line.match for line in result.entries[0].lines] == [1, 3]

    async def test_invert_match_stays_python_authoritative(self, postgres_native_db, sql_capture):
        async with postgres_native_db._use_session() as session:
            await postgres_native_db._write_impl("/a.py", "alpha\nbeta\ngamma", session=session)

        sql_capture.reset()
        async with postgres_native_db._use_session() as session:
            result = await postgres_native_db._grep_impl("beta", invert_match=True, session=session)
        assert result.entries[0].score == 2.0
        assert all("regexp_split_to_table" not in _normalize_sql(statement) for statement in sql_capture.statements)
        assert all(" o.content ~ " not in _normalize_sql(statement) for statement in sql_capture.statements)

    async def test_anchored_regex_skips_whole_content_regex_pushdown(self, postgres_native_db, sql_capture):
        async with postgres_native_db._use_session() as session:
            await postgres_native_db._write_impl("/a.py", "skip\nTODO now\nlater", session=session)

        sql_capture.reset()
        async with postgres_native_db._use_session() as session:
            result = await postgres_native_db._grep_impl("^TODO", session=session)

        assert result.paths == ("/a.py",)
        assert result.entries[0].lines is not None
        assert [line.match for line in result.entries[0].lines] == [2]
        assert all(" o.content ~ " not in _normalize_sql(statement) for statement in sql_capture.statements)
        assert all(" o.content ~* " not in _normalize_sql(statement) for statement in sql_capture.statements)

    async def test_fixed_string_uses_content_like_narrowing(self, postgres_native_db, sql_capture):
        async with postgres_native_db._use_session() as session:
            await postgres_native_db._write_impl("/a.py", "100% ready", session=session)

        sql_capture.reset()
        async with postgres_native_db._use_session() as session:
            result = await postgres_native_db._grep_impl("100%", fixed_strings=True, session=session)

        assert result.paths == ("/a.py",)
        assert any("o.content like" in _normalize_sql(statement) for statement in sql_capture.statements)

    async def test_hard_regex_matches_database_authoritative_python_result(self, postgres_native_db):
        async with postgres_native_db._use_session() as session:
            await postgres_native_db._write_impl("/src/foo.py", "alpha\nbeta\ngamma", session=session)
            await postgres_native_db._write_impl("/src/bar.py", "delta\nepsilon", session=session)
            native = await postgres_native_db._grep_impl(r"^(alpha|beta)$", paths=("/src",), session=session)
            baseline = await DatabaseFileSystem._grep_impl(
                postgres_native_db,
                r"^(alpha|beta)$",
                paths=("/src",),
                session=session,
            )

        assert native.paths == baseline.paths
        assert [entry.score for entry in native.entries] == [entry.score for entry in baseline.entries]
        assert [entry.lines for entry in native.entries] == [entry.lines for entry in baseline.entries]


class TestGlob:
    async def test_pushdown_matches_path_regex(self, postgres_native_db):
        async with postgres_native_db._use_session() as session:
            await postgres_native_db._write_impl("/src/foo.py", "x", session=session)
            await postgres_native_db._write_impl("/src/bar.ts", "y", session=session)
            await postgres_native_db._write_impl("/tests/baz.py", "z", session=session)

        async with postgres_native_db._use_session() as session:
            result = await postgres_native_db._glob_impl("**/*.py", session=session)
        assert set(result.paths) == {"/src/foo.py", "/tests/baz.py"}

    async def test_pushdown_is_case_sensitive(self, postgres_native_db):
        async with postgres_native_db._use_session() as session:
            await postgres_native_db._write_impl("/src/lower.py", "x", session=session)
            await postgres_native_db._write_impl("/src/upper.PY", "y", session=session)

        async with postgres_native_db._use_session() as session:
            result = await postgres_native_db._glob_impl("**/*.py", session=session)
        assert "/src/lower.py" in result.paths
        assert "/src/upper.PY" not in result.paths

    async def test_character_class_glob_matches_database_authoritative_python_result(self, postgres_native_db):
        async with postgres_native_db._use_session() as session:
            await postgres_native_db._write_impl("/src/foo.py", "x", session=session)
            await postgres_native_db._write_impl("/src/boo.py", "y", session=session)
            await postgres_native_db._write_impl("/src/zoo.py", "z", session=session)
            native = await postgres_native_db._glob_impl("/src/[fb]oo.py", session=session)
            baseline = await DatabaseFileSystem._glob_impl(postgres_native_db, "/src/[fb]oo.py", session=session)

        assert native.paths == baseline.paths

    async def test_max_count_applies_after_authoritative_filter(self, postgres_native_db):
        async with postgres_native_db._use_session() as session:
            await postgres_native_db._write_impl("/src/foo.py", "x", session=session)
            await postgres_native_db._write_impl("/src/bar.py", "y", session=session)
            await postgres_native_db._write_impl("/src/baz.ts", "z", session=session)

        async with postgres_native_db._use_session() as session:
            result = await postgres_native_db._glob_impl("/src/[fb]*.py", max_count=1, session=session)

        assert result.paths == ("/src/bar.py",)


class TestPatternSearchPlans:
    async def test_prefix_path_like_uses_path_pattern_index(self, postgres_native_db, engine):
        async with postgres_native_db._use_session() as session:
            await postgres_native_db._write_impl("/src/foo.py", "x", session=session)

        index_names = await _explain_index_names(
            engine,
            """
            SELECT path
            FROM vfs_entries
            WHERE deleted_at IS NULL
              AND path LIKE :pattern ESCAPE '\\'
            ORDER BY path
            """,
            {"pattern": "/src/%"},
        )
        assert "ix_vfs_entries_path_pattern" in index_names

    async def test_path_ilike_gets_an_indexed_plan(self, postgres_native_db, engine):
        async with postgres_native_db._use_session() as session:
            await postgres_native_db._write_impl("/src/foo.py", "x", session=session)
            await postgres_native_db._write_impl("/tests/bar.py", "y", session=session)

        index_names = await _explain_index_names(
            engine,
            """
            SELECT path
            FROM vfs_entries
            WHERE deleted_at IS NULL
              AND path ILIKE :pattern ESCAPE '\\'
            """,
            {"pattern": "%FOO.PY"},
        )
        assert index_names

    async def test_content_ilike_gets_an_indexed_plan(self, postgres_native_db, engine):
        async with postgres_native_db._use_session() as session:
            await postgres_native_db._write_impl("/a.py", "TODO item", session=session)
            await postgres_native_db._write_impl("/b.py", "unrelated", session=session)

        index_names = await _explain_index_names(
            engine,
            """
            SELECT content
            FROM vfs_entries
            WHERE kind = 'file'
              AND content IS NOT NULL
              AND deleted_at IS NULL
              AND content ILIKE :pattern ESCAPE '\\'
            """,
            {"pattern": "%todo%"},
        )
        assert index_names


class TestVectorSearch:
    async def test_uses_native_pgvector_by_default(self, postgres_native_db, postgres_vector_dimension):
        await _seed_native_embeddings(
            postgres_native_db,
            {
                "/a.py": [1.0, 0.0, 0.0, 0.0],
                "/b.py": [0.0, 1.0, 0.0, 0.0],
            },
        )

        result = await postgres_native_db.vector_search([1.0, 0.0, 0.0, 0.0], k=2)
        assert result.success
        assert result.paths[0] == "/a.py"
        assert len(result.entries) == 2

    async def test_candidates_filter_with_native_pgvector(self, postgres_native_db):
        await _seed_native_embeddings(
            postgres_native_db,
            {
                "/a.py": [1.0, 0.0, 0.0, 0.0],
                "/b.py": [0.0, 1.0, 0.0, 0.0],
            },
        )

        candidates = VFSResult(entries=[Entry(path="/b.py")])
        result = await postgres_native_db.vector_search([1.0, 0.0, 0.0, 0.0], k=5, candidates=candidates)
        assert result.paths == ("/b.py",)

    async def test_reads_from_vfs_entries_embedding(self, postgres_native_db, engine):
        await _seed_native_embeddings(
            postgres_native_db,
            {
                "/a.py": [1.0, 0.0, 0.0, 0.0],
            },
        )

        async with engine.connect() as conn:
            row = (await conn.execute(sql_text("SELECT embedding::text FROM vfs_entries WHERE path = '/a.py'"))).first()
        assert row is not None
        assert _parse_vector_text(row[0]) == [1.0, 0.0, 0.0, 0.0]

        result = await postgres_native_db.vector_search([1.0, 0.0, 0.0, 0.0], k=1)
        assert result.paths == ("/a.py",)

    async def test_semantic_search_uses_embedding_provider_plus_pgvector(self, postgres_native_db):
        await _seed_native_embeddings(
            postgres_native_db,
            {
                "/a.py": [1.0, 0.0, 0.0, 0.0],
                "/b.py": [0.0, 1.0, 0.0, 0.0],
            },
        )
        postgres_native_db._embedding_provider = _MockEmbeddingProvider([1.0, 0.0, 0.0, 0.0])

        result = await postgres_native_db.semantic_search("auth", k=2)
        assert result.success
        assert result.function == "semantic_search"
        assert result.paths[0] == "/a.py"

    async def test_user_scope_with_native_pgvector(self, postgres_native_db, engine):
        model = postgres_native_db._model
        scoped_fs = PostgresFileSystem(engine=engine, model=model, user_scoped=True)
        async with scoped_fs._use_session() as session:
            await scoped_fs._write_impl(
                entries=[model(path="/doc.txt", content="alice", embedding=[1.0, 0.0, 0.0, 0.0])],
                user_id="alice",
                session=session,
            )
            await scoped_fs._write_impl(
                entries=[model(path="/doc.txt", content="bob", embedding=[0.0, 1.0, 0.0, 0.0])],
                user_id="bob",
                session=session,
            )

        result = await scoped_fs.vector_search([1.0, 0.0, 0.0, 0.0], k=5, user_id="alice")
        assert result.paths == ("/doc.txt",)

    @pytest.mark.parametrize(
        ("operator_class", "query_vector", "rows", "expected_operator", "expected_score"),
        [
            (
                "vector_cosine_ops",
                [1.0, 0.0, 0.0, 0.0],
                {
                    "/a.py": [1.0, 0.0, 0.0, 0.0],
                    "/b.py": [0.0, 1.0, 0.0, 0.0],
                },
                "<=>",
                1.0,
            ),
            (
                "vector_ip_ops",
                [1.0, 0.0, 0.0, 0.0],
                {
                    "/a.py": [1.0, 0.0, 0.0, 0.0],
                    "/b.py": [0.4, 0.0, 0.0, 0.0],
                },
                "<#>",
                1.0,
            ),
            (
                "vector_l2_ops",
                [1.0, 0.0, 0.0, 0.0],
                {
                    "/a.py": [1.0, 0.0, 0.0, 0.0],
                    "/b.py": [4.0, 0.0, 0.0, 0.0],
                },
                "<->",
                1.0,
            ),
        ],
    )
    async def test_honors_model_declared_operator_class(
        self,
        engine,
        sql_capture,
        operator_class: str,
        query_vector: list[float],
        rows: dict[str, list[float]],
        expected_operator: str,
        expected_score: float,
    ):
        fs = await _make_native_metric_db(engine, operator_class=operator_class)
        await fs.verify_native_search_schema()
        await _seed_native_embeddings(fs, rows)

        sql_capture.reset()
        async with fs._use_session() as session:
            result = await fs._vector_search_impl(vector=query_vector, k=2, session=session)

        assert result.paths[0] == "/a.py"
        assert result.entries[0].score == pytest.approx(expected_score)
        selects = [
            _normalize_sql(statement)
            for statement in sql_capture.statements
            if statement.lstrip().upper().startswith("SELECT") and "from vfs_entries" in statement.lower()
        ]
        assert any(f"o.embedding {expected_operator}" in stmt and "as distance" in stmt for stmt in selects)


class TestWriteAndDelete:
    async def test_write_with_embedding_persists_native_vector_column(self, postgres_native_db, engine):
        async with postgres_native_db._use_session() as session:
            await postgres_native_db._write_impl(
                entries=[postgres_native_db._model(path="/a.py", content="v1", embedding=[0.1, 0.2, 0.3, 0.4])],
                session=session,
            )

        async with engine.connect() as conn:
            row = (await conn.execute(sql_text("SELECT embedding::text FROM vfs_entries WHERE path = '/a.py'"))).first()
        assert row is not None
        assert _parse_vector_text(row[0]) == [0.1, 0.2, 0.3, 0.4]

    async def test_update_embedding_rewrites_native_vector_column(self, postgres_native_db, engine):
        async with postgres_native_db._use_session() as session:
            await postgres_native_db._write_impl(
                entries=[postgres_native_db._model(path="/a.py", content="v1", embedding=[0.1, 0.2, 0.3, 0.4])],
                session=session,
            )
        async with postgres_native_db._use_session() as session:
            await postgres_native_db._write_impl(
                entries=[postgres_native_db._model(path="/a.py", content="v2", embedding=[0.4, 0.3, 0.2, 0.1])],
                session=session,
            )

        async with engine.connect() as conn:
            row = (await conn.execute(sql_text("SELECT embedding::text FROM vfs_entries WHERE path = '/a.py'"))).first()
        assert row is not None
        assert _parse_vector_text(row[0]) == [0.4, 0.3, 0.2, 0.1]

    async def test_write_without_embedding_preserves_existing_embedding(self, postgres_native_db, engine):
        async with postgres_native_db._use_session() as session:
            await postgres_native_db._write_impl(
                entries=[postgres_native_db._model(path="/a.py", content="v1", embedding=[0.1, 0.2, 0.3, 0.4])],
                session=session,
            )
        async with postgres_native_db._use_session() as session:
            await postgres_native_db._write_impl("/a.py", "v2", session=session)

        async with engine.connect() as conn:
            row = (await conn.execute(sql_text("SELECT embedding::text FROM vfs_entries WHERE path = '/a.py'"))).first()
        assert row is not None
        assert _parse_vector_text(row[0]) == [0.1, 0.2, 0.3, 0.4]

    async def test_soft_deleted_rows_are_excluded_from_native_vector_search(self, postgres_native_db):
        await _seed_native_embeddings(postgres_native_db, {"/a.py": [1.0, 0.0, 0.0, 0.0]})
        await postgres_native_db.delete("/a.py")

        result = await postgres_native_db.vector_search([1.0, 0.0, 0.0, 0.0], k=5)
        assert result.paths == ()


class TestLegacyMigrationPath:
    async def test_explicit_migration_path_preserves_existing_embeddings(self, postgres_legacy_db, engine):
        async with postgres_legacy_db._use_session() as session:
            await postgres_legacy_db._write_impl(
                entries=[
                    postgres_legacy_db._model(
                        path="/legacy.py",
                        content="legacy",
                        embedding=[1.0, 0.0, 0.0, 0.0],
                    )
                ],
                session=session,
            )

        native_embedding = NativeEmbeddingConfig(dimension=4)
        native_model = _build_entry_table_class(table_name="vfs_entries", native_embedding=native_embedding)
        spec = postgres_vector_column_spec(native_model)
        async with engine.begin() as conn:
            await conn.execute(sql_text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.execute(sql_text("ALTER TABLE vfs_entries ADD COLUMN embedding_native vector(4)"))
            await conn.execute(
                sql_text("UPDATE vfs_entries SET embedding_native = embedding::vector(4) WHERE embedding IS NOT NULL")
            )
            await conn.execute(sql_text("ALTER TABLE vfs_entries DROP COLUMN embedding"))
            await conn.execute(sql_text("ALTER TABLE vfs_entries RENAME COLUMN embedding_native TO embedding"))
            await conn.execute(
                sql_text(
                    f"""
                    CREATE INDEX IF NOT EXISTS {spec.index_name}
                    ON vfs_entries USING {spec.index_method}
                    ({spec.column_name} {spec.operator_class})
                    WHERE {spec.column_name} IS NOT NULL
                    """
                )
            )

        migrated = PostgresFileSystem(engine=engine, native_embedding=native_embedding)
        await migrated.verify_native_search_schema()
        result = await migrated.vector_search([1.0, 0.0, 0.0, 0.0], k=1)
        assert result.paths == ("/legacy.py",)


class TestMeetingSubgraphSpecCompatibility:
    async def test_current_database_backed_path_already_strips_dangling_spurs(self, postgres_legacy_db):
        await _seed_graph(
            postgres_legacy_db,
            nodes=("/a.py", "/b.py", "/c.py", "/d.py"),
            edges=(
                ("/a.py", "/b.py", "imports"),
                ("/b.py", "/c.py", "imports"),
                ("/a.py", "/d.py", "imports"),
            ),
        )

        result = await postgres_legacy_db.meeting_subgraph(
            VFSResult(entries=[Entry(path="/a.py"), Entry(path="/c.py")])
        )

        assert result.success
        assert _node_paths(result) == {"/a.py", "/b.py", "/c.py"}
        assert "/d.py" not in _node_paths(result)

    async def test_live_connection_rows_remain_authoritative_for_graph_topology(self, postgres_legacy_db):
        conn = postgres_legacy_db._model(
            path=edge_out_path("/ghost/a.py", "/ghost/b.py", "imports"),
            kind="edge",
            source_path="/ghost/a.py",
            target_path="/ghost/b.py",
            edge_type="imports",
        )

        async with postgres_legacy_db._use_session() as session:
            session.add(conn)

        result = await postgres_legacy_db.meeting_subgraph(
            VFSResult(entries=[Entry(path="/ghost/a.py"), Entry(path="/ghost/b.py")])
        )

        assert result.success
        assert _node_paths(result) == {"/ghost/a.py", "/ghost/b.py"}
        assert _connection_path("/ghost/a.py", "/ghost/b.py", "imports") in result.paths


class TestVerifyNativeGraphSchema:
    async def test_success(self, postgres_legacy_db):
        await postgres_legacy_db.verify_native_graph_schema()

    async def test_missing_function(self, postgres_legacy_db, engine):
        async with engine.begin() as conn:
            await conn.execute(sql_text("DROP FUNCTION IF EXISTS grover_meeting_subgraph(text[], text)"))
        with pytest.raises(RuntimeError, match="native graph traversal function"):
            await postgres_legacy_db.verify_native_graph_schema()


class TestNativeGraphTraversal:
    async def test_predecessors_successors_ancestors_and_descendants(self, postgres_legacy_db):
        await _seed_graph(
            postgres_legacy_db,
            nodes=("/a.py", "/b.py", "/c.py", "/d.py", "/isolated.py"),
            edges=(
                ("/a.py", "/b.py", "imports"),
                ("/b.py", "/c.py", "imports"),
                ("/d.py", "/b.py", "calls"),
            ),
        )

        assert (await postgres_legacy_db.predecessors(path="/b.py")).paths == ("/a.py", "/d.py")
        assert (await postgres_legacy_db.successors(path="/b.py")).paths == ("/c.py",)
        assert (await postgres_legacy_db.ancestors(path="/c.py")).paths == ("/a.py", "/b.py", "/d.py")
        assert (await postgres_legacy_db.descendants(path="/a.py")).paths == ("/b.py", "/c.py")
        assert (await postgres_legacy_db.neighborhood(path="/isolated.py", depth=2)).paths == ()

    async def test_neighborhood_returns_nodes_only_with_bounded_undirected_expansion(self, postgres_legacy_db):
        await _seed_graph(
            postgres_legacy_db,
            nodes=("/a.py", "/b.py", "/c.py", "/d.py", "/e.py"),
            edges=(
                ("/a.py", "/b.py", "imports"),
                ("/b.py", "/c.py", "imports"),
                ("/d.py", "/b.py", "calls"),
                ("/c.py", "/e.py", "imports"),
            ),
        )

        result = await postgres_legacy_db.neighborhood(
            candidates=VFSResult(entries=[Entry(path="/b.py")]),
            depth=1,
        )

        assert result.success
        assert _node_paths(result) == {"/a.py", "/b.py", "/c.py", "/d.py"}
        assert not _edge_paths(result)

    async def test_meeting_subgraph_returns_nodes_and_edge_entries(self, postgres_legacy_db):
        await _seed_graph(
            postgres_legacy_db,
            nodes=("/a.py", "/b.py", "/c.py", "/d.py"),
            edges=(
                ("/a.py", "/b.py", "imports"),
                ("/b.py", "/c.py", "imports"),
                ("/a.py", "/d.py", "imports"),
            ),
        )

        result = await postgres_legacy_db.meeting_subgraph(
            VFSResult(entries=[Entry(path="/a.py"), Entry(path="/c.py")])
        )

        assert result.success
        assert _node_paths(result) == {"/a.py", "/b.py", "/c.py"}
        assert _edge_paths(result) == {
            _connection_path("/a.py", "/b.py", "imports"),
            _connection_path("/b.py", "/c.py", "imports"),
        }

    async def test_meeting_subgraph_is_deterministic_for_tie_case(self, postgres_legacy_db):
        await _seed_graph(
            postgres_legacy_db,
            nodes=("/a.py", "/b.py", "/c.py", "/d.py"),
            edges=(
                ("/a.py", "/b.py", "imports"),
                ("/b.py", "/d.py", "imports"),
                ("/a.py", "/c.py", "imports"),
                ("/c.py", "/d.py", "imports"),
            ),
        )

        result = await postgres_legacy_db.meeting_subgraph(
            VFSResult(entries=[Entry(path="/a.py"), Entry(path="/d.py")])
        )

        assert result.success
        assert _node_paths(result) == {"/a.py", "/b.py", "/d.py"}
        assert _edge_paths(result) == {
            _connection_path("/a.py", "/b.py", "imports"),
            _connection_path("/b.py", "/d.py", "imports"),
        }

    async def test_filters_other_users_in_native_graph_queries(self, postgres_legacy_db):
        engine = postgres_legacy_db._engine
        assert engine is not None
        scoped_fs = PostgresFileSystem(engine=engine, user_scoped=True)
        async with scoped_fs._use_session() as session:
            await scoped_fs._write_impl("/a.py", "alice", user_id="alice", session=session)
            await scoped_fs._write_impl("/b.py", "alice", user_id="alice", session=session)
            await scoped_fs._write_impl("/a.py", "bob", user_id="bob", session=session)
            await scoped_fs._write_impl("/b.py", "bob", user_id="bob", session=session)
            await scoped_fs._mkedge_impl("/a.py", "/b.py", "imports", user_id="alice", session=session)
            await scoped_fs._mkedge_impl("/a.py", "/b.py", "imports", user_id="bob", session=session)

        result = await scoped_fs.successors(path="/a.py", user_id="alice")
        assert result.paths == ("/b.py",)

        result = await scoped_fs.meeting_subgraph(
            VFSResult(entries=[Entry(path="/a.py"), Entry(path="/b.py")]),
            user_id="alice",
        )
        assert _node_paths(result) == {"/a.py", "/b.py"}
        assert _edge_paths(result) == {_connection_path("/a.py", "/b.py", "imports")}

    async def test_does_not_delegate_to_cached_rustworkx_graph(self, postgres_legacy_db, monkeypatch):
        await _seed_graph(
            postgres_legacy_db,
            nodes=("/a.py", "/b.py", "/c.py", "/d.py"),
            edges=(
                ("/a.py", "/b.py", "imports"),
                ("/b.py", "/c.py", "imports"),
                ("/d.py", "/b.py", "calls"),
            ),
        )

        async def _boom(*args, **kwargs):
            raise AssertionError("delegated to cached RustworkxGraph")

        for method_name in (
            "predecessors",
            "successors",
            "ancestors",
            "descendants",
            "neighborhood",
            "meeting_subgraph",
        ):
            monkeypatch.setattr(postgres_legacy_db._graph, method_name, _boom)

        assert (await postgres_legacy_db.predecessors(path="/b.py")).paths == ("/a.py", "/d.py")
        assert (await postgres_legacy_db.successors(path="/b.py")).paths == ("/c.py",)
        assert (await postgres_legacy_db.ancestors(path="/c.py")).paths == ("/a.py", "/b.py", "/d.py")
        assert (await postgres_legacy_db.descendants(path="/a.py")).paths == ("/b.py", "/c.py")
        assert set((await postgres_legacy_db.neighborhood(path="/b.py", depth=1)).paths) == {
            "/a.py",
            "/b.py",
            "/c.py",
            "/d.py",
        }
        assert _node_paths(
            await postgres_legacy_db.meeting_subgraph(VFSResult(entries=[Entry(path="/a.py"), Entry(path="/c.py")]))
        ) == {"/a.py", "/b.py", "/c.py"}
