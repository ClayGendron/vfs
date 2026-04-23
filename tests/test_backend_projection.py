"""Per-impl SELECT-column assertions.

These tests use the ``sql_capture`` fixture to assert that each
``_*_impl`` only projects the model columns it actually needs.  The
biggest cost we're driving down is the ``embedding`` blob — it must
never appear in a default read.  ``content`` is allowed only for
``read`` and ``grep``, which legitimately need the text.

These tests are the Phase 4 acceptance gate — they will fail until
each impl is narrowed.  That's intentional: the failing assertion is
the spec for what each impl must do.
"""

from __future__ import annotations

from vfs.backends.database import DatabaseFileSystem
from vfs.columns import default_columns


class TestSqlCaptureFixture:
    """Smoke tests for the ``sql_capture`` fixture itself.

    These verify the fixture observes statements at all and exposes the
    helpers Phase 4 will rely on.  Not xfailed.
    """

    async def test_captures_select_against_objects(self, db, sql_capture):
        await _seed(db)
        sql_capture.reset()
        async with db._use_session() as s:
            await db._read_impl("/docs/intro.md", session=s)
        reads = sql_capture.reads_against_entries()
        assert reads, "expected at least one SELECT against vfs_entries"

    async def test_assert_no_column_passes_when_absent(self, db, sql_capture):
        await _seed(db)
        sql_capture.reset()
        async with db._use_session() as s:
            await db._read_impl("/docs/intro.md", session=s)
        sql_capture.assert_no_column("nonexistent_column")


class TestSelectColumnsValidation:
    """``_select_columns`` rejects unknown column names with a clear error.

    Without this guard a typo (``size`` for ``size_bytes``) surfaces as
    an ``AttributeError`` from SQLAlchemy's model metaclass, which is
    both cryptic and offers no hint about the valid set.
    """

    async def test_unknown_column_raises_value_error(self, db):
        import pytest

        async with db._use_session() as s:
            with pytest.raises(ValueError, match=r"unknown column\(s\): size"):
                await db._read_impl("/x", columns=frozenset({"path", "size"}), session=s)

    async def test_error_lists_valid_columns(self, db):
        import pytest

        async with db._use_session() as s:
            with pytest.raises(ValueError, match="size_bytes") as exc:
                await db._read_impl("/x", columns=frozenset({"size"}), session=s)
        assert "Valid columns" in str(exc.value)

    async def test_known_column_passes_through(self, db):
        """Sanity check: real columns don't trip the validator."""
        async with db._use_session() as s:
            await db._write_impl("/a.md", "hi", session=s)
            # No raise — size_bytes is the correct spelling.
            result = await db._read_impl(
                "/a.md",
                columns=frozenset({"path", "size_bytes"}),
                session=s,
            )
            assert result.candidates[0].size_bytes == 2


async def _seed(db: DatabaseFileSystem) -> None:
    """Seed a small namespace covering files, dirs, and chunks."""
    async with db._use_session() as s:
        await db._write_impl("/docs/intro.md", "# Intro\nhello world", session=s)
        await db._write_impl("/docs/guide.md", "# Guide\nhydrate the index", session=s)
        await db._write_impl("/src/auth.py", "def login(): pass", session=s)
        await db._write_impl("/.vfs/src/auth.py/__meta__/chunks/login", "def login(): pass", session=s)


class TestGlobProjection:
    async def test_default_glob_omits_embedding(self, db, sql_capture):
        await _seed(db)
        sql_capture.reset()
        async with db._use_session() as s:
            await db._glob_impl("**/*.md", session=s)
        sql_capture.assert_no_column("embedding")

    async def test_default_glob_omits_content(self, db, sql_capture):
        await _seed(db)
        sql_capture.reset()
        async with db._use_session() as s:
            await db._glob_impl("**/*.md", session=s)
        sql_capture.assert_no_column("content")


class TestStatProjection:
    async def test_default_stat_omits_embedding(self, db, sql_capture):
        await _seed(db)
        sql_capture.reset()
        async with db._use_session() as s:
            await db._stat_impl("/docs/intro.md", session=s)
        sql_capture.assert_no_column("embedding")

    async def test_default_stat_omits_content(self, db, sql_capture):
        await _seed(db)
        sql_capture.reset()
        async with db._use_session() as s:
            await db._stat_impl("/docs/intro.md", session=s)
        sql_capture.assert_no_column("content")


class TestLsProjection:
    async def test_default_ls_omits_embedding(self, db, sql_capture):
        await _seed(db)
        sql_capture.reset()
        async with db._use_session() as s:
            await db._ls_impl("/docs", session=s)
        sql_capture.assert_no_column("embedding")

    async def test_default_ls_omits_content(self, db, sql_capture):
        await _seed(db)
        sql_capture.reset()
        async with db._use_session() as s:
            await db._ls_impl("/docs", session=s)
        sql_capture.assert_no_column("content")


class TestTreeProjection:
    async def test_default_tree_omits_embedding(self, db, sql_capture):
        await _seed(db)
        sql_capture.reset()
        async with db._use_session() as s:
            await db._tree_impl("/", session=s)
        sql_capture.assert_no_column("embedding")

    async def test_default_tree_omits_content(self, db, sql_capture):
        await _seed(db)
        sql_capture.reset()
        async with db._use_session() as s:
            await db._tree_impl("/", session=s)
        sql_capture.assert_no_column("content")


class TestReadProjection:
    async def test_default_read_omits_embedding(self, db, sql_capture):
        await _seed(db)
        sql_capture.reset()
        async with db._use_session() as s:
            await db._read_impl("/docs/intro.md", session=s)
        sql_capture.assert_no_column("embedding")


class TestGrepProjection:
    async def test_default_grep_omits_embedding(self, db, sql_capture):
        await _seed(db)
        sql_capture.reset()
        async with db._use_session() as s:
            await db._grep_impl("hydrate", session=s)
        sql_capture.assert_no_column("embedding")


class TestVectorSearchProjection:
    async def test_default_vector_search_omits_embedding_in_projection(self, db, sql_capture):
        """Vector search uses the embedding column for ranking but must not
        return the raw blob in its projected row set — the SELECT list itself
        must omit ``vfs_entries.embedding``.

        DatabaseFileSystem in tests has no ``vector_store`` configured, so the
        impl returns an error envelope without issuing any SELECT — the
        assertion is satisfied vacuously.  Once a real vector store is wired
        up, this test guards that the followup row-fetch (if any) doesn't
        re-introduce ``embedding`` into the projection.
        """
        await _seed(db)
        sql_capture.reset()
        async with db._use_session() as s:
            await db._vector_search_impl(vector=[0.1] * 4, k=5, session=s)
        sql_capture.assert_no_column("embedding")

    async def test_default_vector_search_omits_content(self, db, sql_capture):
        await _seed(db)
        sql_capture.reset()
        async with db._use_session() as s:
            await db._vector_search_impl(vector=[0.1] * 4, k=5, session=s)
        sql_capture.assert_no_column("content")


class TestPostgresNativeVectorSearchProjection:
    async def test_native_projection_keeps_embedding_out_of_select_list(
        self,
        postgres_native_db,
        postgres_vector_dimension,
        sql_capture,
    ):
        async with postgres_native_db._use_session() as s:
            await postgres_native_db._write_impl(
                entries=[
                    postgres_native_db._model(
                        path="/vec.py",
                        content="vector row",
                        embedding=[0.1] * postgres_vector_dimension,
                    )
                ],
                session=s,
            )

        sql_capture.reset()
        async with postgres_native_db._use_session() as s:
            await postgres_native_db._vector_search_impl(
                vector=[0.1] * postgres_vector_dimension,
                k=5,
                session=s,
            )

        selects = [
            " ".join(statement.split())
            for statement in sql_capture.statements
            if statement.lstrip().upper().startswith("SELECT") and "FROM vfs_entries" in statement
        ]
        assert selects, "expected vector search to issue at least one SELECT against vfs_entries"
        assert any("o.embedding <=>" in stmt and "AS distance" in stmt for stmt in selects)
        assert all("SELECT o.embedding" not in stmt for stmt in selects)


class TestLexicalSearchProjection:
    async def test_default_lexical_search_omits_embedding(self, db, sql_capture):
        await _seed(db)
        sql_capture.reset()
        async with db._use_session() as s:
            await db._lexical_search_impl("hydrate", k=5, session=s)
        sql_capture.assert_no_column("embedding")


class TestPublicSurfaceColumnsKwarg:
    """End-to-end checks that ``columns`` flows from the public methods
    through the routers and lands as the actual SELECT projection."""

    async def test_public_read_with_explicit_columns(self, db, sql_capture):
        await _seed(db)
        sql_capture.reset()
        result = await db.read("/docs/intro.md", columns=frozenset({"path", "kind", "size_bytes"}))
        assert result.success
        entry = result.file
        assert entry is not None
        assert entry.path == "/docs/intro.md"
        assert entry.kind == "file"
        assert entry.size_bytes is not None
        # content was not requested — must stay None
        assert entry.content is None
        # SELECT must omit content + embedding
        sql_capture.assert_no_column("content")
        sql_capture.assert_no_column("embedding")

    async def test_public_glob_with_columns_widens_select(self, db, sql_capture):
        await _seed(db)
        sql_capture.reset()
        # Default glob doesn't pull updated_at — wait, it does (metadata cols).
        # Pick a column outside the default set: content.
        result = await db.glob("**/*.md", columns=frozenset({"path", "kind", "content"}))
        assert result.success
        for entry in result.candidates:
            assert entry.content is not None, f"{entry.path} missing content"

    async def test_public_stat_default_excludes_content(self, db, sql_capture):
        await _seed(db)
        sql_capture.reset()
        result = await db.stat("/docs/intro.md")
        assert result.success
        entry = result.file
        assert entry is not None
        assert entry.content is None
        sql_capture.assert_no_column("content")
        sql_capture.assert_no_column("embedding")

    async def test_public_stat_with_columns_pulls_content(self, db, sql_capture):
        await _seed(db)
        sql_capture.reset()
        result = await db.stat(
            "/docs/intro.md",
            columns=default_columns("stat") | {"content"},
        )
        assert result.success
        entry = result.file
        assert entry is not None
        assert entry.content == "# Intro\nhello world"


class TestPagerankProjection:
    async def test_default_pagerank_omits_embedding(self, db, sql_capture):
        await _seed(db)
        sql_capture.reset()
        async with db._use_session() as s:
            await db._pagerank_impl(session=s)
        sql_capture.assert_no_column("embedding")

    async def test_default_pagerank_omits_content(self, db, sql_capture):
        await _seed(db)
        sql_capture.reset()
        async with db._use_session() as s:
            await db._pagerank_impl(session=s)
        sql_capture.assert_no_column("content")
