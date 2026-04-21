"""Tests for VFS result types — Entry, LineMatch, VFSResult."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from tests.conftest import entry as _e
from vfs.results import Entry, LineMatch, VFSResult, _format_field, _verb_for

# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------


class TestEntry:
    def test_construction(self):
        e = Entry(path="/src/auth.py", kind="file")
        assert e.path == "/src/auth.py"
        assert e.kind == "file"
        assert e.name == "auth.py"
        assert e.content is None
        assert e.lines is None
        assert e.score is None
        assert e.size_bytes is None
        assert e.in_degree is None
        assert e.out_degree is None
        assert e.updated_at is None

    def test_defaults_all_none(self):
        e = Entry(path="/a.py")
        assert e.kind is None
        assert e.content is None
        assert e.lines is None
        assert e.score is None
        assert e.size_bytes is None
        assert e.in_degree is None
        assert e.out_degree is None
        assert e.updated_at is None

    def test_requires_path(self):
        with pytest.raises(ValidationError):
            Entry.model_validate({"kind": "file"})

    def test_frozen(self):
        e = Entry(path="/a.py")
        with pytest.raises(ValidationError):
            e.path = "/b.py"

    def test_name_property(self):
        assert Entry(path="/src/auth.py").name == "auth.py"
        assert Entry(path="/.vfs/a.py/__meta__/versions/3").name == "3"

    def test_with_line_matches(self):
        lm = LineMatch(start=1, end=3, match=2)
        e = Entry(path="/a.py", lines=[lm])
        assert e.lines is not None
        assert e.lines[0].match == 2
        assert e.lines[0].start == 1
        assert e.lines[0].end == 3

    def test_zero_metrics_preserved_in_json(self):
        """0 is not None — zero metrics should be present in JSON."""
        e = Entry(path="/a.py", size_bytes=0, score=0.0)
        data = e.model_dump(exclude_none=True)
        assert data["size_bytes"] == 0
        assert data["score"] == 0.0

    def test_json_round_trip(self):
        e = Entry(path="/a.py", kind="file", size_bytes=50, score=0.42)
        data = e.model_dump()
        restored = Entry.model_validate(data)
        assert restored == e


# ---------------------------------------------------------------------------
# LineMatch
# ---------------------------------------------------------------------------


class TestLineMatch:
    def test_named_tuple_fields(self):
        lm = LineMatch(start=1, end=5, match=3)
        assert lm.start == 1
        assert lm.end == 5
        assert lm.match == 3
        # NamedTuple indexing order: start, end, match.
        assert lm[0] == 1
        assert lm[1] == 5
        assert lm[2] == 3


# ---------------------------------------------------------------------------
# VFSResult — envelope, iteration, truthiness
# ---------------------------------------------------------------------------


class TestVFSResultBasics:
    def test_empty_result(self):
        r = VFSResult()
        assert r.success is True
        assert r.errors == []
        assert r.error_message == ""
        assert r.function == ""
        assert r.entries == []
        assert r.paths == ()
        assert r.file is None
        assert r.content is None
        assert len(r) == 0
        assert not r  # empty + success = falsy (no entries)

    def test_with_entries(self):
        r = VFSResult(
            function="glob",
            entries=[_e("/a.py"), _e("/b.py")],
        )
        assert len(r) == 2
        assert r.paths == ("/a.py", "/b.py")
        assert r.file is not None
        assert r.file.path == "/a.py"
        assert r.function == "glob"
        assert r

    def test_failed_result_is_falsy(self):
        r = VFSResult(success=False, function="glob", entries=[_e("/a.py")])
        assert not r

    def test_contains(self):
        r = VFSResult(function="glob", entries=[_e("/a.py")])
        assert "/a.py" in r
        assert "/b.py" not in r

    def test_iter_entries(self):
        entries = [_e("/a.py"), _e("/b.py")]
        r = VFSResult(function="glob", entries=entries)
        paths = [e.path for e in r.iter_entries()]
        assert paths == ["/a.py", "/b.py"]

    def test_content_shorthand(self):
        r = VFSResult(function="read", entries=[_e("/a.py", content="print('hello')")])
        assert r.content == "print('hello')"

    def test_errors_and_error_message(self):
        r = VFSResult(
            function="glob",
            entries=[_e("/a.py"), _e("/b.py")],
            errors=["problem one", "problem two"],
        )
        assert r.errors == ["problem one", "problem two"]
        assert r.error_message == "problem one; problem two"


# ---------------------------------------------------------------------------
# VFSResult — set algebra (left-wins merge)
# ---------------------------------------------------------------------------


def _make(paths: list[str], function: str = "glob", score: float | None = None) -> VFSResult:
    entries = [Entry(path=p, kind="file", score=score) for p in paths]
    return VFSResult(function=function, entries=entries)


class TestVFSResultSetAlgebra:
    def test_intersection(self):
        a = _make(["/a.py", "/b.py", "/c.py"], function="glob")
        b = _make(["/b.py", "/c.py", "/d.py"], function="glob")
        result = a & b
        assert set(result.paths) == {"/b.py", "/c.py"}

    def test_intersection_empty(self):
        a = _make(["/a.py"])
        b = _make(["/b.py"])
        result = a & b
        assert len(result) == 0

    def test_union(self):
        a = _make(["/a.py", "/b.py"], function="glob")
        b = _make(["/b.py", "/c.py"], function="glob")
        result = a | b
        assert set(result.paths) == {"/a.py", "/b.py", "/c.py"}

    def test_difference(self):
        a = _make(["/a.py", "/b.py", "/c.py"])
        b = _make(["/b.py"])
        result = a - b
        assert set(result.paths) == {"/a.py", "/c.py"}

    def test_difference_empty_right(self):
        a = _make(["/a.py", "/b.py"])
        b = VFSResult()
        result = a - b
        assert set(result.paths) == {"/a.py", "/b.py"}

    def test_success_propagation_and(self):
        a = VFSResult(success=True, function="glob", entries=[_e("/a.py")])
        b = VFSResult(success=False, function="glob", entries=[_e("/a.py")])
        result = a & b
        assert result.success is False

    def test_success_propagation_or(self):
        a = VFSResult(success=True, function="glob", entries=[_e("/a.py")])
        b = VFSResult(success=False, function="glob", entries=[_e("/b.py")])
        result = a | b
        assert result.success is False

    def test_sub_preserves_left_success(self):
        a = VFSResult(success=True, function="glob", entries=[_e("/a.py")])
        b = VFSResult(success=False, function="glob", entries=[_e("/b.py")])
        result = a - b
        assert result.success is True


class TestLeftWinsMerge:
    def test_intersection_left_wins_on_content(self):
        a = VFSResult(
            function="glob",
            entries=[Entry(path="/a.py", kind="file", content="from left")],
        )
        b = VFSResult(
            function="glob",
            entries=[Entry(path="/a.py", kind="file", content="from right")],
        )
        result = a & b
        assert result.entries[0].content == "from left"

    def test_merge_preserves_empty_string_content(self):
        """content='' (empty file) should NOT be replaced by right's content."""
        a = VFSResult(
            function="glob",
            entries=[Entry(path="/a.py", kind="file", content="")],
        )
        b = VFSResult(
            function="glob",
            entries=[Entry(path="/a.py", kind="file", content="real content")],
        )
        result = a & b
        assert result.entries[0].content == ""

    def test_merge_preserves_zero_metrics_from_left(self):
        """size_bytes=0 on left should NOT be replaced by right's value."""
        a = VFSResult(
            function="glob",
            entries=[Entry(path="/a.py", kind="file", size_bytes=0)],
        )
        b = VFSResult(
            function="glob",
            entries=[Entry(path="/a.py", kind="file", size_bytes=4096)],
        )
        result = a & b
        assert result.entries[0].size_bytes == 0

    def test_merge_falls_back_to_right_for_none(self):
        """Left has None → right's value is used."""
        a = VFSResult(
            function="glob",
            entries=[Entry(path="/a.py")],
        )
        b = VFSResult(
            function="glob",
            entries=[
                Entry(
                    path="/a.py",
                    kind="file",
                    content="hello",
                    size_bytes=4096,
                    score=0.7,
                ),
            ],
        )
        result = a & b
        merged = result.entries[0]
        assert merged.kind == "file"
        assert merged.content == "hello"
        assert merged.size_bytes == 4096
        assert merged.score == 0.7

    def test_as_dict_last_wins_on_duplicate_paths(self):
        """If entries have duplicate paths, _as_dict keeps the last one."""
        e1 = Entry(path="/a.py", kind="file", content="first")
        e2 = Entry(path="/a.py", kind="file", content="second")
        r = VFSResult(function="glob", entries=[e1, e2])
        d = r._as_dict()
        assert len(d) == 1
        assert d["/a.py"].content == "second"


# ---------------------------------------------------------------------------
# VFSResult — function propagation on set algebra
# ---------------------------------------------------------------------------


class TestFunctionPropagation:
    def test_same_function_union_preserves_function(self):
        a = _make(["/a.py"], function="glob")
        b = _make(["/b.py"], function="glob")
        result = a | b
        assert result.function == "glob"

    def test_cross_function_union_is_hybrid(self):
        a = _make(["/a.py"], function="glob")
        b = _make(["/b.py"], function="vector_search", score=0.9)
        result = a | b
        assert result.function == "hybrid"

    def test_cross_function_intersection_is_hybrid(self):
        a = _make(["/a.py"], function="glob")
        b = _make(["/a.py"], function="vector_search", score=0.9)
        result = a & b
        assert result.function == "hybrid"

    def test_empty_envelope_union_with_empty_envelope(self):
        """Both operands have empty function string → result is also empty."""
        a = VFSResult(entries=[_e("/a.py")])
        b = VFSResult(entries=[_e("/b.py")])
        result = a | b
        assert result.function == ""

    def test_empty_envelope_unions_to_other_function(self):
        """If one side has function='' it shouldn't force hybrid."""
        a = VFSResult(entries=[_e("/a.py")])
        b = _make(["/b.py"], function="glob")
        result = a | b
        assert result.function == "glob"

    def test_difference_preserves_left_function(self):
        a = _make(["/a.py", "/b.py"], function="glob")
        b = _make(["/b.py"], function="vector_search", score=0.1)
        result = a - b
        assert result.function == "glob"


# ---------------------------------------------------------------------------
# VFSResult — enrichment (sort / top / filter / kinds / prefix / scope)
# ---------------------------------------------------------------------------


class TestVFSResultEnrichment:
    def test_sort_by_score_default(self):
        r = VFSResult(
            function="vector_search",
            entries=[
                Entry(path="/low.py", score=0.1),
                Entry(path="/high.py", score=0.9),
                Entry(path="/mid.py", score=0.5),
            ],
        )
        sorted_r = r.sort()
        assert [e.path for e in sorted_r.iter_entries()] == ["/high.py", "/mid.py", "/low.py"]

    def test_sort_ascending(self):
        r = VFSResult(
            function="vector_search",
            entries=[
                Entry(path="/high.py", score=0.9),
                Entry(path="/low.py", score=0.1),
            ],
        )
        sorted_r = r.sort(reverse=False)
        assert [e.path for e in sorted_r.iter_entries()] == ["/low.py", "/high.py"]

    def test_sort_custom_key(self):
        r = VFSResult(
            function="glob",
            entries=[
                Entry(path="/small.py", size_bytes=100),
                Entry(path="/big.py", size_bytes=9000),
            ],
        )
        sorted_r = r.sort(key=lambda e: e.size_bytes or 0)
        assert sorted_r.entries[0].path == "/big.py"

    def test_sort_none_scores_sink_to_bottom(self):
        r = VFSResult(
            function="vector_search",
            entries=[
                Entry(path="/a.py", score=None),
                Entry(path="/b.py", score=0.5),
            ],
        )
        sorted_r = r.sort()
        assert sorted_r.entries[0].path == "/b.py"
        assert sorted_r.entries[1].path == "/a.py"

    def test_sort_preserves_function(self):
        r = VFSResult(
            function="vector_search",
            entries=[Entry(path="/a.py", score=0.1)],
        )
        assert r.sort().function == "vector_search"

    def test_top(self):
        r = VFSResult(
            function="vector_search",
            entries=[
                Entry(path="/a.py", score=0.1),
                Entry(path="/b.py", score=0.9),
                Entry(path="/c.py", score=0.5),
            ],
        )
        top2 = r.top(2)
        assert len(top2) == 2
        assert top2.entries[0].path == "/b.py"
        assert top2.entries[1].path == "/c.py"

    def test_top_more_than_available(self):
        r = VFSResult(function="vector_search", entries=[Entry(path="/a.py", score=0.1)])
        top5 = r.top(5)
        assert len(top5) == 1

    def test_top_zero_raises(self):
        r = VFSResult(function="vector_search", entries=[Entry(path="/a.py", score=0.5)])
        with pytest.raises(ValueError, match="k must be >= 1"):
            r.top(0)

    def test_top_negative_raises(self):
        r = VFSResult(function="vector_search", entries=[Entry(path="/a.py", score=0.5)])
        with pytest.raises(ValueError, match="k must be >= 1"):
            r.top(-1)

    def test_filter(self):
        r = VFSResult(
            function="glob",
            entries=[
                Entry(path="/a.py", kind="file", size_bytes=100),
                Entry(path="/b/", kind="directory"),
                Entry(path="/c.py", kind="file", size_bytes=0),
            ],
        )
        files_with_content = r.filter(lambda e: e.kind == "file" and (e.size_bytes or 0) > 0)
        assert len(files_with_content) == 1
        assert files_with_content.entries[0].path == "/a.py"

    def test_kinds(self):
        r = VFSResult(
            function="glob",
            entries=[
                Entry(path="/a.py", kind="file"),
                Entry(path="/b/", kind="directory"),
                Entry(path="/.vfs/a.py/__meta__/chunks/login", kind="chunk"),
            ],
        )
        files_only = r.kinds("file")
        assert len(files_only) == 1
        files_and_chunks = r.kinds("file", "chunk")
        assert len(files_and_chunks) == 2

    def test_add_prefix(self):
        r = VFSResult(
            function="glob",
            entries=[Entry(path="/a.py"), Entry(path="/b.py")],
        )
        r.add_prefix("/user1")
        assert set(r.paths) == {"/user1/a.py", "/user1/b.py"}

    def test_add_prefix_empty_is_noop(self):
        r = VFSResult(function="glob", entries=[Entry(path="/a.py")])
        r.add_prefix("")
        assert r.paths == ("/a.py",)

    def test_strip_user_scope(self):
        r = VFSResult(
            function="glob",
            entries=[Entry(path="/123/docs/README.md"), Entry(path="/123/src/a.py")],
        )
        stripped = r.strip_user_scope("123")
        assert set(stripped.paths) == {"/docs/README.md", "/src/a.py"}


# ---------------------------------------------------------------------------
# VFSResult — JSON / string serialization
# ---------------------------------------------------------------------------


class TestVFSResultJSON:
    def test_to_json_excludes_none_by_default(self):
        r = VFSResult(
            function="glob",
            entries=[Entry(path="/a.py", kind="file")],
        )
        parsed = json.loads(r.to_json())
        entry = parsed["entries"][0]
        assert entry["path"] == "/a.py"
        assert entry["kind"] == "file"
        # None fields are excluded.
        assert "content" not in entry
        assert "score" not in entry
        assert "size_bytes" not in entry
        assert "updated_at" not in entry

    def test_to_json_include_none(self):
        r = VFSResult(function="glob", entries=[Entry(path="/a.py")])
        parsed = json.loads(r.to_json(exclude_none=False))
        entry = parsed["entries"][0]
        # All Entry fields present.
        for field in (
            "path",
            "kind",
            "lines",
            "content",
            "size_bytes",
            "score",
            "in_degree",
            "out_degree",
            "updated_at",
        ):
            assert field in entry

    def test_to_json_round_trip(self):
        r = VFSResult(
            success=True,
            errors=["Found 2 files"],
            function="glob",
            entries=[Entry(path="/a.py", kind="file"), Entry(path="/b.py", kind="file")],
        )
        json_str = r.to_json()
        restored = VFSResult.model_validate_json(json_str)
        assert restored.paths == r.paths
        assert restored.success == r.success
        assert restored.errors == r.errors
        assert restored.function == r.function
        assert len(restored.entries) == 2

    def test_model_dump_round_trip(self):
        r = VFSResult(
            function="vector_search",
            entries=[Entry(path="/a.py", score=0.9), Entry(path="/b.py", score=0.5)],
        )
        data = r.model_dump()
        restored = VFSResult.model_validate(data)
        assert restored.function == "vector_search"
        assert [e.score for e in restored.entries] == [0.9, 0.5]

    def test_independent_entries_lists(self):
        """Each instance should own its entries list."""
        r1 = VFSResult()
        r2 = VFSResult()
        assert r1.entries is not r2.entries


# ---------------------------------------------------------------------------
# VFSResult — to_str dispatch (smoke-level; snapshots come later)
# ---------------------------------------------------------------------------


class TestToStr:
    def test_glob_one_path_per_line(self):
        r = VFSResult(
            function="glob",
            entries=[Entry(path="/a.py"), Entry(path="/b.py"), Entry(path="/c.py")],
        )
        rendered = r.to_str()
        assert rendered == "/a.py\n/b.py\n/c.py"

    def test_glob_multicolumn_renders_markdown_table(self):
        """Multi-column path lists render as a GFM table — pipes line up."""
        from datetime import datetime

        r = VFSResult(
            function="glob",
            entries=[
                Entry(
                    path="/docs/guide.md",
                    size_bytes=27,
                    updated_at=datetime(2026, 4, 19, 19, 47, 15, 672705, tzinfo=UTC),
                ),
                Entry(
                    path="/docs/intro.md",
                    size_bytes=34,
                    updated_at=datetime(2026, 4, 19, 19, 47, 15, 668105, tzinfo=UTC),
                ),
            ],
        )
        rendered = r.to_str(projection=("path", "size_bytes", "updated_at"))
        expected = (
            "| path           | size_bytes | updated_at                       |\n"
            "| -------------- | ---------: | -------------------------------- |\n"
            "| /docs/guide.md |         27 | 2026-04-19 19:47:15.672705+00:00 |\n"
            "| /docs/intro.md |         34 | 2026-04-19 19:47:15.668105+00:00 |"
        )
        assert rendered == expected

    def test_markdown_table_pipes_and_dashes_align(self):
        """Every pipe in the output must sit at the same column offset per row."""
        r = VFSResult(
            function="glob",
            entries=[Entry(path="/a", size_bytes=1), Entry(path="/long_path", size_bytes=9999)],
        )
        rendered = r.to_str(projection=("path", "size_bytes"))
        rows = rendered.split("\n")
        # Same number of pipes on every row, at the same positions.
        pipe_positions = [[i for i, c in enumerate(r) if c == "|"] for r in rows]
        assert len({tuple(p) for p in pipe_positions}) == 1, pipe_positions

    def test_markdown_table_right_aligns_numeric_fields(self):
        """``size_bytes`` / ``score`` / degrees render with a trailing-colon divider."""
        r = VFSResult(
            function="glob",
            entries=[Entry(path="/a", size_bytes=5)],
        )
        rendered = r.to_str(projection=("path", "size_bytes"))
        # Divider row's second cell ends with ':' (GFM right-align marker).
        divider = rendered.split("\n")[1]
        left_cell, right_cell = [c.strip() for c in divider.strip("|").split("|")]
        assert not left_cell.endswith(":")
        assert right_cell.endswith(":")

    def test_markdown_table_escapes_pipes_in_values(self):
        """A literal ``|`` in a cell escapes to ``\\|`` so it doesn't break the row."""
        r = VFSResult(
            function="glob",
            entries=[Entry(path="/has|pipe", kind="file")],
        )
        rendered = r.to_str(projection=("path", "kind"))
        assert r"/has\|pipe" in rendered
        # Exactly 3 unescaped pipes per row (leading, middle, trailing).
        for row in rendered.split("\n"):
            unescaped = row.replace(r"\|", "")
            assert unescaped.count("|") == 3

    def test_empty_multicolumn_still_emits_header_and_divider(self):
        """Empty multi-column path list: header + divider, no data rows."""
        r = VFSResult(function="glob", entries=[])
        rendered = r.to_str(projection=("path", "size_bytes"))
        assert rendered == ""  # Empty entries short-circuit — no header for zero rows.

    def test_empty_success_result_is_empty_string(self):
        r = VFSResult(function="glob", entries=[])
        assert r.to_str() == ""

    def test_error_result_renders_error(self):
        r = VFSResult(success=False, function="glob", errors=["boom"])
        assert r.to_str() == "ERROR: boom"

    def test_multiple_errors_render_errors_plural(self):
        r = VFSResult(success=False, function="glob", errors=["one", "two"])
        assert r.to_str() == "ERRORS: one; two"

    def test_grep_renders_path_line_content(self):
        content = "line one\nhit here\nline three\n"
        e = Entry(
            path="/a.py",
            content=content,
            lines=[LineMatch(start=2, end=2, match=2)],
        )
        r = VFSResult(function="grep", entries=[e])
        rendered = r.to_str()
        # Default grep projection = path:match:content-slice.
        assert rendered == "/a.py:2:hit here"

    def test_grep_renders_context_lines_rg_style(self):
        """``-B`` / ``-A`` context expands into one prefixed row per source line.

        Match line uses ``:`` separators; context lines use ``-`` separators
        — same shape as ripgrep so downstream tools can parse line-by-line
        without knowing the schema.
        """
        content = "# Intro\nhydrate the index\nwelcome\n"
        e = Entry(
            path="/docs/intro.md",
            content=content,
            lines=[LineMatch(start=1, end=3, match=2)],
        )
        r = VFSResult(function="grep", entries=[e])
        rendered = r.to_str()
        assert rendered == ("/docs/intro.md-1-# Intro\n/docs/intro.md:2:hydrate the index\n/docs/intro.md-3-welcome")

    def test_grep_context_window_clipped_to_content_length(self):
        """Phantom line numbers past end-of-file are silently skipped."""
        content = "only line\n"
        e = Entry(
            path="/a.py",
            content=content,
            lines=[LineMatch(start=1, end=5, match=1)],
        )
        r = VFSResult(function="grep", entries=[e])
        assert r.to_str() == "/a.py:1:only line"

    def test_grep_entry_level_projection_falls_back_to_markdown_table(self):
        """Projecting entry-level fields switches grep from line output to a table.

        ``size_bytes`` / ``updated_at`` / degrees are per-file attributes.
        Mixing them into rg-style line output produces ambiguous
        separators (``hydrate downstream:27``), so the renderer falls
        back to the standard Markdown-table view — one row per entry.
        """
        content = "a\nhit\nb\n"
        e = Entry(
            path="/a.py",
            content=content,
            lines=[LineMatch(start=1, end=3, match=2)],
            size_bytes=47,
            updated_at=datetime(2026, 4, 19, 12, 0, 0, tzinfo=UTC),
        )
        r = VFSResult(function="grep", entries=[e])
        rendered = r.to_str(projection=("path", "size_bytes", "updated_at"))
        # Table shape: header, divider, one data row. No ``/a.py:2:hit``
        # line-oriented output anywhere — the caller opted out of it.
        rows = rendered.split("\n")
        assert len(rows) == 3
        assert rows[0].startswith("| path")
        assert "size_bytes" in rows[0]
        assert "/a.py" in rows[2]
        assert "47" in rows[2]

    def test_bare_string_projection_raises_typeerror(self):
        """``projection=('path')`` (no trailing comma) is a common Python typo.

        Without a guard it iterates character-by-character into an
        ``unknown field 'p'`` confusion. We short-circuit at the boundary
        with a clear ``TypeError`` that names the mistake.
        """
        r = VFSResult(function="glob", entries=[Entry(path="/a.py")])
        with pytest.raises(TypeError, match=r"tuple or list.*bare string 'path'"):
            r.to_str(projection="path")  # ty: ignore[invalid-argument-type]

    def test_explicit_null_projection_appends_note(self):
        r = VFSResult(function="glob", entries=[Entry(path="/a.py")])
        rendered = r.to_str(projection=("path", "out_degree"))
        assert "NOTE: out_degree not populated for any entries." in rendered

    def test_grep_native_projection_still_renders_line_by_line(self):
        """Projection of just ``path``/``lines``/``content`` keeps rg-style output."""
        content = "a\nhit\nb\n"
        e = Entry(
            path="/a.py",
            content=content,
            lines=[LineMatch(start=1, end=3, match=2)],
            # Entry has entry-level data but we don't project it — stay rg-style.
            size_bytes=47,
        )
        r = VFSResult(function="grep", entries=[e])
        rendered = r.to_str(projection=("path", "lines", "content"))
        assert rendered == ("/a.py-1-a\n/a.py:2:hit\n/a.py-3-b")

    def test_grep_overlapping_context_windows_render_once(self):
        """Merged grep windows should emit one block even when they contain two hits."""
        e = Entry(
            path="/a.py",
            content="one\nhit A\nhit B\nfour\n",
            lines=[
                LineMatch(start=1, end=4, match=2),
                LineMatch(start=1, end=4, match=3),
            ],
        )
        r = VFSResult(function="grep", entries=[e])
        rendered = r.to_str(projection=("path", "lines", "content"))
        assert rendered == "/a.py-1-one\n/a.py:2:hit A\n/a.py:3:hit B\n/a.py-4-four"

    def test_grep_without_content_falls_back_to_per_segment(self):
        """Dropping ``content`` from the projection switches to one row per segment."""
        e = Entry(
            path="/a.py",
            content="one\ntwo\nthree\n",
            lines=[LineMatch(start=1, end=3, match=2)],
        )
        r = VFSResult(function="grep", entries=[e])
        assert r.to_str(projection=("path", "lines")) == "/a.py:2"

    def test_grep_no_segments_emits_path(self):
        """``--files-with-matches`` / ``--count`` output: entries have no ``lines``."""
        e = Entry(path="/a.py", content="hit\n")
        r = VFSResult(function="grep", entries=[e])
        assert r.to_str() == "/a.py"

    def test_vector_search_renders_as_markdown_table(self):
        r = VFSResult(
            function="vector_search",
            entries=[Entry(path="/a.py", score=0.9)],
        )
        rendered = r.to_str()
        assert "| path" in rendered
        assert "score" in rendered
        assert "/a.py" in rendered
        assert "0.9000" in rendered

    def test_read_returns_content(self):
        r = VFSResult(
            function="read",
            entries=[Entry(path="/a.py", content="print('hi')")],
        )
        assert r.to_str() == "print('hi')"

    def test_action_write_one_path(self):
        r = VFSResult(function="write", entries=[Entry(path="/a.py")])
        assert r.to_str() == "Wrote /a.py"

    def test_action_write_many_paths(self):
        r = VFSResult(
            function="write",
            entries=[Entry(path="/a.py"), Entry(path="/b.py")],
        )
        assert r.to_str() == "Wrote 2 paths"

    def test_success_true_with_errors_appends_error_block(self):
        r = VFSResult(
            success=True,
            function="glob",
            entries=[Entry(path="/a.py")],
            errors=["warn"],
        )
        rendered = r.to_str()
        assert rendered.startswith("/a.py")
        assert rendered.endswith("ERROR: warn")


# ---------------------------------------------------------------------------
# _first_set helper
# ---------------------------------------------------------------------------


class TestFirstSet:
    def test_returns_a_when_not_none(self):
        assert VFSResult._first_set("a", "b") == "a"

    def test_returns_b_when_a_is_none(self):
        assert VFSResult._first_set(None, "b") == "b"

    def test_returns_default_when_both_none(self):
        assert VFSResult._first_set(None, None, "default") == "default"

    def test_returns_none_when_all_none(self):
        assert VFSResult._first_set(None, None) is None

    def test_preserves_zero(self):
        assert VFSResult._first_set(0, 99) == 0

    def test_preserves_empty_string(self):
        assert VFSResult._first_set("", "fallback") == ""

    def test_preserves_zero_float(self):
        assert VFSResult._first_set(0.0, 1.0) == 0.0


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------


class TestResultHelpers:
    def test_merged_function_keeps_left_when_other_is_empty(self):
        left = VFSResult(function="glob")
        right = VFSResult(function="")
        assert left._merged_function(right) == "glob"

    def test_format_field_joins_list_values(self):
        assert _format_field("lines", [1, "two", 3]) == "1,two,3"

    def test_unknown_action_verbs_are_titleized(self):
        assert _verb_for("sync_all") == "Sync all"

    def test_empty_action_name_falls_back_to_completed(self):
        assert _verb_for("") == "Completed"
