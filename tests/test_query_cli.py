"""Tests for the CLI-style query parser, executor, and renderer."""

from __future__ import annotations

import pytest

from vfs.backends.database import DatabaseFileSystem
from vfs.query import QuerySyntaxError


@pytest.fixture
async def query_fs(db: DatabaseFileSystem):
    async with db._use_session() as session:
        await db._write_impl("/src/auth.py", "import utils\ndef login(): pass", session=session)
        await db._write_impl("/src/utils.py", "def helper(): pass", session=session)
        await db._write_impl("/src/db.py", "import utils\ndef connect(): pass", session=session)
        await db._write_impl("/src/api.py", "import auth\nimport utils", session=session)
        await db._write_impl("/src/config.py", "DEBUG = True", session=session)

    for source, target, edge_type in [
        ("/src/auth.py", "/src/utils.py", "imports"),
        ("/src/auth.py", "/src/db.py", "calls"),
        ("/src/utils.py", "/src/db.py", "imports"),
        ("/src/api.py", "/src/auth.py", "imports"),
        ("/src/api.py", "/src/utils.py", "imports"),
    ]:
        async with db._use_session() as session:
            await db._mkedge_impl(source, target, edge_type, session=session)

    return db


class TestParseQuery:
    def test_methods_follow_query_order(self, query_fs: DatabaseFileSystem):
        plan = query_fs.parse_query(
            'search "auth" | intersect (glob "/src/*.py" & grep "DEBUG") | meetinggraph --min | pagerank | top 3',
        )
        assert plan.methods == (
            "semantic_search",
            "glob",
            "grep",
            "min_meeting_subgraph",
            "pagerank",
            "top",
        )

    def test_unknown_flag_fails_fast(self, query_fs: DatabaseFileSystem):
        with pytest.raises(QuerySyntaxError, match="Unknown flag"):
            query_fs.parse_query('grep "import" --bogus')

    def test_stage_flags_are_parsed_through_registry(self, query_fs: DatabaseFileSystem):
        plan = query_fs.parse_query('search "auth" --k 5 | top 2')
        assert plan.methods == ("semantic_search", "top")


class TestRunQuery:
    async def test_glob_grep_read_pipeline(self, query_fs: DatabaseFileSystem):
        result = await query_fs.run_query('glob "/src/*.py" | grep "import" | read')
        assert set(result.paths) == {"/src/auth.py", "/src/db.py", "/src/api.py"}

    async def test_intersect_and_except(self, query_fs: DatabaseFileSystem):
        result = await query_fs.run_query('glob "/src/*.py" | intersect (grep "import") | except (grep "auth")')
        assert set(result.paths) == {"/src/auth.py", "/src/db.py"}

    async def test_union_keeps_both_branches(self, query_fs: DatabaseFileSystem):
        result = await query_fs.run_query('grep "import" & grep "DEBUG"')
        assert set(result.paths) == {"/src/auth.py", "/src/db.py", "/src/api.py", "/src/config.py"}

    async def test_pipeline_copy_preserves_relative_paths(self, query_fs: DatabaseFileSystem):
        result = await query_fs.run_query('grep "import utils" | cp /backup')
        assert result.success
        assert set(result.paths) == {"/backup/src/auth.py", "/backup/src/db.py", "/backup/src/api.py"}

        copied = await query_fs.read("/backup/src/auth.py")
        assert copied.content == "import utils\ndef login(): pass"

    async def test_local_transforms_apply_after_query(self, query_fs: DatabaseFileSystem):
        result = await query_fs.run_query('grep "import" | sort | top 2')
        assert len(result) == 2


class TestCliRendering:
    async def test_read_renders_content(self, query_fs: DatabaseFileSystem):
        text = await query_fs.cli("read /src/auth.py")
        assert text == "import utils\ndef login(): pass"

    async def test_write_renders_action_summary(self, query_fs: DatabaseFileSystem):
        text = await query_fs.cli('write /notes/todo.md "hello"')
        assert text == "Wrote /notes/todo.md"

    async def test_ls_renders_names(self, query_fs: DatabaseFileSystem):
        text = await query_fs.cli("ls /src")
        assert sorted(text.splitlines()) == sorted(
            ["/src/api.py", "/src/auth.py", "/src/config.py", "/src/db.py", "/src/utils.py"],
        )

    async def test_tree_renders_ascii_tree(self, query_fs: DatabaseFileSystem):
        text = await query_fs.cli("tree /src")
        assert "└── src" in text
        assert "auth.py" in text

    async def test_tree_with_visibility_still_renders_ascii_tree(self, query_fs: DatabaseFileSystem):
        text = await query_fs.cli("tree /src --all")
        assert "└── src" in text
        assert "auth.py" in text
        assert "/src/auth.py" not in text


class TestCliOutputFlag:
    """End-to-end checks for the top-level ``--output`` flag.

    These hit the real DatabaseFileSystem: parse → execute → render.
    """

    async def test_output_path_only(self, query_fs: DatabaseFileSystem):
        text = await query_fs.cli('glob "/src/*.py" --output path')
        # to_str picks the path-only arrangement when projection=("path",)
        lines = sorted(text.splitlines())
        assert lines == sorted(
            [
                "/src/api.py",
                "/src/auth.py",
                "/src/config.py",
                "/src/db.py",
                "/src/utils.py",
            ],
        )

    async def test_output_unknown_field_rejected(self, query_fs: DatabaseFileSystem):
        with pytest.raises(QuerySyntaxError, match="unknown field 'bogus'"):
            await query_fs.cli('glob "/src/*.py" --output bogus')

    async def test_run_query_threads_columns_through_glob(self, query_fs: DatabaseFileSystem):
        # A projection that includes a non-default column triggers the
        # widened SELECT and entries carry the field directly.
        result = await query_fs.run_query('glob "/src/*.py" --output path,kind,updated_at')
        assert result.entries
        for entry in result.entries:
            assert entry.updated_at is not None

    async def test_hydration_fills_grep_entries(self, query_fs: DatabaseFileSystem):
        # grep entries carry path+kind+content+score+lines by default;
        # asking for ``updated_at`` requires the hydration pass to backfill.
        result = await query_fs.run_query('grep "import" --output path,updated_at')
        assert result.entries
        for entry in result.entries:
            assert entry.updated_at is not None
