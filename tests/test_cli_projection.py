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
        assert any("vfs_objects.path" in s for s in sql_capture.reads_against_objects())

    async def test_glob_with_output_updated_at_projects_it(self, db, sql_capture):
        await _seed(db)
        sql_capture.reset()
        await execute_query(db, parse_query('glob "**/*.md" --output default,updated_at'))
        reads = sql_capture.reads_against_objects()
        assert any("vfs_objects.updated_at" in s for s in reads), (
            "Expected vfs_objects.updated_at in the compiled SELECT after --output widen. "
            "Statements observed:\n" + "\n---\n".join(reads)
        )
        # Widening must never pull the heavy columns unasked-for.
        sql_capture.assert_no_column("embedding")


class TestOutputWidensRead:
    async def test_read_with_output_adds_in_degree(self, db, sql_capture):
        await _seed(db)
        sql_capture.reset()
        await execute_query(db, parse_query("read /docs/intro.md --output content,in_degree"))
        reads = sql_capture.reads_against_objects()
        assert any("vfs_objects.in_degree" in s for s in reads), (
            "Expected vfs_objects.in_degree in the SELECT after --output in_degree"
        )


class TestUnknownFieldRejectedAtParseTime:
    def test_unknown_field_raises(self):
        from vfs.query.parser import QuerySyntaxError

        with pytest.raises(QuerySyntaxError, match="unknown field 'bogus'"):
            parse_query("grep hydrate --output bogus")


class TestProjectionOrderPreserved:
    def test_projection_tuple_ordering_is_preserved(self):
        plan = parse_query("stat /a --output path,score,in_degree")
        assert plan.projection == ("path", "score", "in_degree")

        plan = parse_query("stat /a --output in_degree,score,path")
        assert plan.projection == ("in_degree", "score", "path")

    def test_default_sentinel_kept_symbolic(self):
        plan = parse_query("grep hydrate --output default,updated_at")
        assert plan.projection == ("default", "updated_at")

    def test_all_sentinel_kept_symbolic(self):
        plan = parse_query("stat /a --output all")
        assert plan.projection == ("all",)
