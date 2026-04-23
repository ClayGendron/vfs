"""CLI projection — ``--output`` widens the SELECT.

Phase 8.3 acceptance: the top-level ``--output`` flag parsed at the
query-planner boundary flows into every stage's ``columns=`` kwarg, so
the backend SELECT list widens to cover the requested Entry fields.

Catches: the CLI flag reaching only the renderer (where it would render
nulls) while the SELECT stays narrow — a silent miss.
"""

from __future__ import annotations

import pytest

from vfs.backends.database import DatabaseFileSystem
from vfs.query.executor import execute_query
from vfs.query.parser import parse_query


async def _seed(db: DatabaseFileSystem) -> None:
    async with db._use_session() as s:
        await db._write_impl("/docs/intro.md", "# Intro", session=s)
        await db._write_impl("/docs/guide.md", "# Guide", session=s)
        await db._write_impl("/src/auth.py", "def login(): pass", session=s)


class TestOutputWidensGlob:
    async def test_glob_default_omits_updated_at(self, db, sql_capture):
        await _seed(db)
        sql_capture.reset()
        await execute_query(db, parse_query('glob "**/*.md"'))
        sql_capture.assert_no_column("embedding")
        # `glob` default already pulls metadata — assert it is here so the
        # next test's widen has something to compare against.
        assert any("vfs_entries.path" in s for s in sql_capture.reads_against_entries())

    async def test_glob_with_output_updated_at_projects_it(self, db, sql_capture):
        await _seed(db)
        sql_capture.reset()
        await execute_query(db, parse_query('glob "**/*.md" --output default,updated_at'))
        reads = sql_capture.reads_against_entries()
        assert any("vfs_entries.updated_at" in s for s in reads), (
            "Expected vfs_entries.updated_at in the compiled SELECT after --output widen. "
            "Statements observed:\n" + "\n---\n".join(reads)
        )
        # Widening must never pull the heavy columns unasked-for.
        sql_capture.assert_no_column("embedding")


class TestOutputWidensStat:
    async def test_stat_with_output_adds_content(self, db, sql_capture):
        await _seed(db)
        sql_capture.reset()
        await execute_query(db, parse_query("stat /docs/intro.md --output default,content"))
        reads = sql_capture.reads_against_entries()
        assert any("vfs_entries.content" in s for s in reads), (
            "Expected vfs_entries.content in the SELECT after --output content"
        )


class TestPostgresNativeProjection:
    async def test_native_glob_output_still_avoids_embedding(self, postgres_native_db, sql_capture):
        await _seed(postgres_native_db)
        sql_capture.reset()
        await execute_query(postgres_native_db, parse_query('glob "**/*.md" --output default,updated_at'))
        statements = [
            " ".join(statement.split()).lower()
            for statement in sql_capture.statements
            if statement.lstrip().upper().startswith("SELECT") and "from vfs_entries" in statement.lower()
        ]
        assert statements
        assert any("updated_at" in statement for statement in statements)
        assert all("embedding" not in statement for statement in statements)


class TestUnknownFieldRejectedAtParseTime:
    def test_unknown_field_raises(self):
        from vfs.query.parser import QuerySyntaxError

        with pytest.raises(QuerySyntaxError, match="unknown field 'bogus'"):
            parse_query("grep hydrate --output bogus")


class TestProjectionOrderPreserved:
    def test_projection_tuple_ordering_is_preserved(self):
        plan = parse_query("stat /a --output path,score,updated_at")
        assert plan.projection == ("path", "score", "updated_at")

        plan = parse_query("stat /a --output updated_at,score,path")
        assert plan.projection == ("updated_at", "score", "path")

    def test_default_sentinel_kept_symbolic(self):
        plan = parse_query("grep hydrate --output default,updated_at")
        assert plan.projection == ("default", "updated_at")

    def test_all_sentinel_kept_symbolic(self):
        plan = parse_query("stat /a --output all")
        assert plan.projection == ("all",)
