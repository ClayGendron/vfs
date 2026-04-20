"""Tests for PostgresFileSystem.

Pure helper tests run in the default suite. Integration tests are gated on
``--postgres`` and require a local PostgreSQL instance plus the optional
``pgvector`` dependency.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text as sql_text

from vfs.backends.postgres import (
    PostgresFileSystem,
    _build_tsquery,
    _parse_vector_dimension,
    _python_regex_to_postgres,
    _quote_tsquery_term,
)
from vfs.models import postgres_native_vfs_object_model, postgres_vector_column_spec
from vfs.results import Entry, VFSResult
from vfs.vector import Vector


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


def _parse_vector_text(value: str) -> list[float]:
    return [float(part) for part in value.strip("[]").split(",") if part]


async def _seed_native_embeddings(db: PostgresFileSystem, rows: dict[str, list[float]]) -> None:
    async with db._use_session() as session:
        await db._write_impl(
            objects=[
                db._model(path=path, content=path, embedding=Vector[len(vector)](vector))
                for path, vector in rows.items()
            ],
            session=session,
        )


class TestTsqueryHelpers:
    def test_quote_tsquery_term_escapes_single_quote(self):
        assert _quote_tsquery_term("don't") == "'don''t'"

    def test_build_tsquery_or(self):
        assert _build_tsquery(["auth", "timeout"], operator="|") == "'auth' | 'timeout'"

    def test_build_tsquery_and(self):
        assert _build_tsquery(("auth", "timeout"), operator="&") == "'auth' & 'timeout'"


class TestResolveTable:
    def test_qualifies_schema(self):
        fs = PostgresFileSystem.__new__(PostgresFileSystem)
        fs._schema = "vfs"
        fs._model = postgres_native_vfs_object_model(dimension=4)
        assert fs._resolve_table() == "vfs.vfs_objects"

    def test_bare_name_without_schema(self):
        fs = PostgresFileSystem.__new__(PostgresFileSystem)
        fs._schema = None
        fs._model = postgres_native_vfs_object_model(dimension=4)
        assert fs._resolve_table() == "vfs_objects"


class TestRegexTranslation:
    def test_word_boundary_maps_to_postgres_are(self):
        assert _python_regex_to_postgres(r"\bfoo\b") == r"\yfoo\y"

    def test_non_capturing_group_downgraded_to_plain_group(self):
        assert _python_regex_to_postgres(r"(?:foo|bar)") == r"(foo|bar)"


class TestParseVectorDimension:
    def test_accepts_dimensioned_vector(self):
        assert _parse_vector_dimension("vector(1536)") == 1536

    def test_rejects_non_vector(self):
        assert _parse_vector_dimension("text") is None


class TestVerifyNativeSearchSchema:
    async def test_success(self, postgres_native_db):
        await postgres_native_db.verify_native_search_schema()

    async def test_missing_vector_extension(self, postgres_legacy_db):
        engine = postgres_legacy_db._engine
        assert engine is not None
        async with engine.begin() as conn:
            await conn.execute(sql_text("DROP EXTENSION IF EXISTS vector"))

        fs = PostgresFileSystem(
            engine=engine,
            model=postgres_native_vfs_object_model(dimension=4),
        )
        with pytest.raises(RuntimeError, match="pgvector extension"):
            await fs.verify_native_search_schema()

    async def test_rejects_non_native_embedding_column(self, postgres_legacy_db):
        engine = postgres_legacy_db._engine
        assert engine is not None
        fs = PostgresFileSystem(
            engine=engine,
            model=postgres_native_vfs_object_model(dimension=4),
        )
        with pytest.raises(RuntimeError, match="non-native embedding column"):
            await fs.verify_native_search_schema()

    async def test_dimension_mismatch(self, postgres_native_db, engine):
        fs = PostgresFileSystem(
            engine=engine,
            model=postgres_native_vfs_object_model(dimension=8),
        )
        with pytest.raises(RuntimeError, match="dimension mismatch"):
            await fs.verify_native_search_schema()

    async def test_missing_fts_index(self, postgres_native_db, engine):
        async with engine.begin() as conn:
            await conn.execute(sql_text("DROP INDEX IF EXISTS ix_vfs_objects_content_tsv_gin"))
        with pytest.raises(RuntimeError, match="full-text index"):
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
    async def test_ranks_in_postgres_and_hydrates_top_k_only(self, postgres_native_db, sql_capture):
        async with postgres_native_db._use_session() as session:
            await postgres_native_db._write_impl("/both.py", "authentication timeout handler", session=session)
            await postgres_native_db._write_impl("/one.py", "authentication only", session=session)
            await postgres_native_db._write_impl("/none.py", "unrelated", session=session)

        sql_capture.reset()
        async with postgres_native_db._use_session() as session:
            result = await postgres_native_db._lexical_search_impl("authentication timeout", k=1, session=session)
        assert result.paths == ("/both.py",)
        assert result.entries[0].content == "authentication timeout handler"
        selects = [
            _normalize_sql(statement)
            for statement in sql_capture.statements
            if statement.lstrip().upper().startswith("SELECT") and "from vfs_objects" in statement.lower()
        ]
        assert any("select path, content from vfs_objects where path = any" in statement for statement in selects)


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

    async def test_reads_from_vfs_objects_embedding(self, postgres_native_db, engine):
        await _seed_native_embeddings(
            postgres_native_db,
            {
                "/a.py": [1.0, 0.0, 0.0, 0.0],
            },
        )

        async with engine.connect() as conn:
            row = (
                await conn.execute(sql_text("SELECT embedding::text FROM vfs_objects WHERE path = '/a.py'"))
            ).first()
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
                objects=[model(path="/doc.txt", content="alice", embedding=[1.0, 0.0, 0.0, 0.0])],
                user_id="alice",
                session=session,
            )
            await scoped_fs._write_impl(
                objects=[model(path="/doc.txt", content="bob", embedding=[0.0, 1.0, 0.0, 0.0])],
                user_id="bob",
                session=session,
            )

        result = await scoped_fs.vector_search([1.0, 0.0, 0.0, 0.0], k=5, user_id="alice")
        assert result.paths == ("/doc.txt",)


class TestWriteAndDelete:
    async def test_write_with_embedding_persists_native_vector_column(self, postgres_native_db, engine):
        async with postgres_native_db._use_session() as session:
            await postgres_native_db._write_impl(
                objects=[postgres_native_db._model(path="/a.py", content="v1", embedding=[0.1, 0.2, 0.3, 0.4])],
                session=session,
            )

        async with engine.connect() as conn:
            row = (
                await conn.execute(sql_text("SELECT embedding::text FROM vfs_objects WHERE path = '/a.py'"))
            ).first()
        assert row is not None
        assert _parse_vector_text(row[0]) == [0.1, 0.2, 0.3, 0.4]

    async def test_update_embedding_rewrites_native_vector_column(self, postgres_native_db, engine):
        async with postgres_native_db._use_session() as session:
            await postgres_native_db._write_impl(
                objects=[postgres_native_db._model(path="/a.py", content="v1", embedding=[0.1, 0.2, 0.3, 0.4])],
                session=session,
            )
        async with postgres_native_db._use_session() as session:
            await postgres_native_db._write_impl(
                objects=[postgres_native_db._model(path="/a.py", content="v2", embedding=[0.4, 0.3, 0.2, 0.1])],
                session=session,
            )

        async with engine.connect() as conn:
            row = (
                await conn.execute(sql_text("SELECT embedding::text FROM vfs_objects WHERE path = '/a.py'"))
            ).first()
        assert row is not None
        assert _parse_vector_text(row[0]) == [0.4, 0.3, 0.2, 0.1]

    async def test_write_without_embedding_preserves_existing_embedding(self, postgres_native_db, engine):
        async with postgres_native_db._use_session() as session:
            await postgres_native_db._write_impl(
                objects=[postgres_native_db._model(path="/a.py", content="v1", embedding=[0.1, 0.2, 0.3, 0.4])],
                session=session,
            )
        async with postgres_native_db._use_session() as session:
            await postgres_native_db._write_impl("/a.py", "v2", session=session)

        async with engine.connect() as conn:
            row = (
                await conn.execute(sql_text("SELECT embedding::text FROM vfs_objects WHERE path = '/a.py'"))
            ).first()
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
                objects=[
                    postgres_legacy_db._model(
                        path="/legacy.py",
                        content="legacy",
                        embedding=[1.0, 0.0, 0.0, 0.0],
                    )
                ],
                session=session,
            )

        native_model = postgres_native_vfs_object_model(dimension=4)
        spec = postgres_vector_column_spec(native_model)
        async with engine.begin() as conn:
            await conn.execute(sql_text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.execute(sql_text("ALTER TABLE vfs_objects ADD COLUMN embedding_native vector(4)"))
            await conn.execute(
                sql_text(
                    "UPDATE vfs_objects SET embedding_native = embedding::vector(4) WHERE embedding IS NOT NULL"
                )
            )
            await conn.execute(sql_text("ALTER TABLE vfs_objects DROP COLUMN embedding"))
            await conn.execute(sql_text("ALTER TABLE vfs_objects RENAME COLUMN embedding_native TO embedding"))
            await conn.execute(
                sql_text(
                    f"""
                    CREATE INDEX IF NOT EXISTS {spec.index_name}
                    ON vfs_objects USING {spec.index_method}
                    ({spec.column_name} {spec.operator_class})
                    WHERE {spec.column_name} IS NOT NULL
                    """
                )
            )

        migrated = PostgresFileSystem(engine=engine, model=native_model)
        await migrated.verify_native_search_schema()
        result = await migrated.vector_search([1.0, 0.0, 0.0, 0.0], k=1)
        assert result.paths == ("/legacy.py",)
