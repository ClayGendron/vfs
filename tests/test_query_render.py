"""Tests for query/render.py — render_query_result public API across modes."""

from __future__ import annotations

from vfs.query.ast import QueryPlan, ReadCommand
from vfs.query.render import render_query_result
from vfs.results import Entry, VFSResult


def _plan(projection: tuple[str, ...] | None = None) -> QueryPlan:
    """Build a minimal QueryPlan for renderer tests.

    The renderer only reads ``plan.projection``; the AST and methods are
    immaterial here, so we hand it a placeholder ``ReadCommand`` to
    satisfy the dataclass contract.
    """
    return QueryPlan(
        ast=ReadCommand(),
        methods=(),
        projection=projection,
    )


def _entry(
    path: str,
    *,
    content: str | None = None,
    kind: str | None = None,
    score: float | None = None,
    size_bytes: int | None = None,
    updated_at=None,
    in_degree: int | None = None,
    out_degree: int | None = None,
) -> Entry:
    return Entry(
        path=path,
        content=content,
        kind=kind,
        score=score,
        size_bytes=size_bytes,
        updated_at=updated_at,
        in_degree=in_degree,
        out_degree=out_degree,
    )


# ===========================================================================
# Error rendering
# ===========================================================================


class TestErrorRendering:
    def test_errors_only(self):
        result = VFSResult(
            success=False,
            errors=["file not found", "bad path"],
            function="read",
        )
        output = render_query_result(result, _plan())
        # Multi-error uses the "ERRORS:" prefix
        assert "file not found" in output
        assert "bad path" in output
        assert output.startswith("ERRORS")

    def test_body_with_errors(self):
        result = VFSResult(
            success=True,
            function="read",
            entries=[_entry("/a.py", content="hello")],
            errors=["warning: deprecated"],
        )
        output = render_query_result(result, _plan())
        assert "hello" in output
        assert "warning: deprecated" in output
        assert "ERROR" in output


# ===========================================================================
# Content mode
# ===========================================================================


class TestContentMode:
    def test_single_file(self):
        result = VFSResult(
            function="read",
            entries=[_entry("/a.py", content="hello")],
        )
        output = render_query_result(result, _plan())
        assert output == "hello"

    def test_empty_candidates(self):
        result = VFSResult(function="read", entries=[])
        output = render_query_result(result, _plan())
        assert output == ""

    def test_multi_file_sorted_with_headers(self):
        result = VFSResult(
            function="read",
            entries=[
                _entry("/b.py", content="bravo"),
                _entry("/a.py", content="alpha"),
            ],
        )
        output = render_query_result(result, _plan())
        assert "==> /a.py <==" in output
        assert "==> /b.py <==" in output
        # a.py should come before b.py (sorted)
        assert output.index("/a.py") < output.index("/b.py")


# ===========================================================================
# Action mode
# ===========================================================================


class TestActionMode:
    def test_no_changes(self):
        result = VFSResult(function="write", entries=[])
        output = render_query_result(result, _plan())
        assert output == "No changes"

    def test_single_path(self):
        result = VFSResult(
            function="write",
            entries=[_entry("/a.py")],
        )
        output = render_query_result(result, _plan())
        assert output == "Wrote /a.py"

    def test_multi_path(self):
        result = VFSResult(
            function="delete",
            entries=[
                _entry("/a.py"),
                _entry("/b.py"),
            ],
        )
        output = render_query_result(result, _plan())
        assert output == "Deleted 2 paths"

    def test_errors_only_action(self):
        # success=True with errors but no entries → action renders "No changes" + error block
        result = VFSResult(
            success=True,
            function="write",
            errors=["permission denied"],
            entries=[],
        )
        output = render_query_result(result, _plan())
        assert "permission denied" in output
        assert "ERROR" in output

    def test_all_verbs(self):
        for op, verb in [
            ("write", "Wrote"),
            ("edit", "Edited"),
            ("delete", "Deleted"),
            ("move", "Moved"),
            ("copy", "Copied"),
            ("mkdir", "Created"),
            ("mkconn", "Connected"),
        ]:
            result = VFSResult(function=op, entries=[_entry("/x")])
            output = render_query_result(result, _plan())
            assert verb in output


# ===========================================================================
# Stat mode
# ===========================================================================


class TestStatMode:
    def test_stat_with_metadata(self):
        result = VFSResult(
            function="stat",
            entries=[
                _entry(
                    "/a.py",
                    kind="file",
                    size_bytes=1024,
                    in_degree=3,
                    out_degree=5,
                ),
            ],
        )
        output = render_query_result(result, _plan())
        assert "/a.py" in output
        assert "kind: file" in output
        assert "size_bytes: 1024" in output

    def test_stat_with_none_values(self):
        result = VFSResult(
            function="stat",
            entries=[_entry("/a.py", kind="file")],
        )
        output = render_query_result(result, _plan())
        assert "/a.py" in output
        assert "kind: file" in output
        # Null fields shouldn't appear in the block rendering
        assert "size_bytes:" not in output


# ===========================================================================
# Query list mode
# ===========================================================================


class TestQueryListMode:
    def test_unranked(self):
        result = VFSResult(
            function="glob",
            entries=[
                _entry("/b.py"),
                _entry("/a.py"),
            ],
        )
        output = render_query_result(result, _plan())
        assert "/a.py" in output
        assert "/b.py" in output

    def test_ranked(self):
        # Ranked-search function uses block rendering with score sub-line
        result = VFSResult(
            function="lexical_search",
            entries=[
                _entry("/a.py", score=0.95),
                _entry("/b.py", score=0.80),
            ],
        )
        output = render_query_result(result, _plan())
        assert "/a.py" in output
        assert "/b.py" in output
        assert "0.9500" in output
        assert "0.8000" in output
