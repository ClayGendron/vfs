"""Tests for text rendering of Result — per-function arrangements."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from vfs.models2 import Match, Observation
from vfs.render import _verb_for
from vfs.results2 import Result, ResultError, VFSErrorKind


def obs(path: str, **kwargs: object) -> Observation:
    return Observation(path=path, **kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Errors and notes
# ---------------------------------------------------------------------------


class TestErrorRendering:
    def test_failed_result_renders_error_block_only(self) -> None:
        result = Result(
            function="read",
            success=False,
            errors=[ResultError(kind=VFSErrorKind.not_found, message="no such path: /a.md")],
        )
        assert str(result) == "ERROR: no such path: /a.md"

    def test_multiple_errors_pluralize(self) -> None:
        result = Result(
            function="ls",
            success=False,
            errors=[
                ResultError(kind=VFSErrorKind.not_found, message="first"),
                ResultError(kind=VFSErrorKind.timeout, message="second"),
            ],
        )
        assert str(result) == "ERRORS: first; second"

    def test_errors_append_after_body_on_partial_success(self) -> None:
        result = Result(
            function="glob",
            observations=[obs("/a.md")],
            errors=[ResultError(kind=VFSErrorKind.unavailable, message="one mount down")],
        )
        assert str(result) == "/a.md\n\nERROR: one mount down"

    def test_unpopulated_projection_note(self) -> None:
        result = Result(function="glob", observations=[obs("/a.md")])
        out = result.to_str(projection=("path", "score"))
        assert "NOTE: score not populated for any observations." in out

    def test_note_suppressed_when_grep_content_lives_on_matches(self) -> None:
        # grep draws path/matches/content from the match regions, so a null
        # Observation.content must not trigger a "not populated" note.
        result = Result(
            function="grep",
            observations=[obs("/a.py", matches=[Match(start=1, end=1, match=1, content="hit")])],
        )
        out = result.to_str(projection=("path", "matches", "content"))
        assert "NOTE:" not in out

    def test_note_fires_for_grep_when_matches_and_content_absent(self) -> None:
        result = Result(function="grep", observations=[obs("/a.py")])
        out = result.to_str(projection=("matches", "content"))
        assert out == "NOTE: matches, content not populated for any observations."

    def test_note_suppressed_for_renderers_that_ignore_projection(self) -> None:
        tree = Result(function="tree", observations=[obs("/d/a.py")])
        assert "NOTE:" not in tree.to_str(projection=("path", "score"))
        action = Result(function="delete", observations=[obs("/d/a.py")])
        assert "NOTE:" not in action.to_str(projection=("path", "score"))


# ---------------------------------------------------------------------------
# Path lists and tables
# ---------------------------------------------------------------------------


class TestPathListAndTable:
    def test_path_only_projection_is_sorted_lines(self) -> None:
        result = Result(function="ls", observations=[obs("/b.md"), obs("/a.md")])
        assert str(result) == "/a.md\n/b.md"

    def test_wider_projection_renders_markdown_table(self) -> None:
        result = Result(
            function="glean",
            observations=[obs("/a.md", score=0.5), obs("/b.md", score=0.25)],
        )
        assert str(result) == ("| path  |  score |\n| ----- | -----: |\n| /a.md | 0.5000 |\n| /b.md | 0.2500 |")

    def test_unknown_function_falls_back_to_path_list(self) -> None:
        result = Result(function="future_op", observations=[obs("/a.md")])
        assert str(result) == "/a.md"

    def test_table_renders_match_list_as_spans(self) -> None:
        # A list-valued field (matches) rendered in a table formats each Match
        # as a start-end span via _format_field's list branch.
        result = Result(
            function="ls",
            observations=[obs("/a.py", matches=[Match(start=1, end=3, match=1)])],
        )
        out = result.to_str(projection=("path", "matches"))
        assert "1-3" in out

    def test_table_cells_escape_pipes_and_newlines(self) -> None:
        result = Result(
            function="ls",
            observations=[obs("/a.md", kind="file", description="x|y\nz")],
        )
        out = result.to_str(projection=("path", "description"))
        assert r"x\|y z" in out

    def test_table_cells_strip_carriage_returns(self) -> None:
        result = Result(
            function="ls",
            observations=[obs("/a.md", kind="file", description="one\r\ntwo\rthree")],
        )
        out = result.to_str(projection=("path", "description"))
        assert "one two three" in out
        assert "\r" not in out


# ---------------------------------------------------------------------------
# Grep
# ---------------------------------------------------------------------------


class TestGrepRendering:
    def test_default_projection_renders_region_text_from_match(self) -> None:
        result = Result(
            function="grep",
            observations=[
                obs("/a.py", matches=[Match(start=3, end=5, match=4, content="ctx1\nhit\nctx2")]),
            ],
        )
        assert str(result) == "/a.py-3-ctx1\n/a.py:4:hit\n/a.py-5-ctx2"

    def test_whole_region_match_marks_every_line(self) -> None:
        result = Result(
            function="grep",
            observations=[obs("/a.py", matches=[Match(start=1, end=2, content="one\ntwo")])],
        )
        assert str(result) == "/a.py:1:one\n/a.py:2:two"

    def test_falls_back_to_slicing_full_content(self) -> None:
        result = Result(
            function="grep",
            observations=[
                obs("/a.py", content="l1\nl2\nl3", matches=[Match(start=2, end=3, match=2)]),
            ],
        )
        out = result.to_str(projection=("path", "matches", "content"))
        assert out == "/a.py:2:l2\n/a.py-3-l3"

    def test_no_text_available_renders_path_and_line(self) -> None:
        result = Result(
            function="grep",
            observations=[obs("/a.py", matches=[Match(start=7, end=7, match=7)])],
        )
        assert str(result) == "/a.py:7"

    def test_empty_observation_content_does_not_swallow_the_match(self) -> None:
        # content="" must not be mistaken for "content available to slice" and
        # render nothing; the match still surfaces as a path:line.
        result = Result(
            function="grep",
            observations=[obs("/x.py", content="", matches=[Match(start=1, end=1, match=1)])],
        )
        assert str(result) == "/x.py:1"

    def test_files_with_matches_mode_renders_paths(self) -> None:
        result = Result(function="grep", observations=[obs("/a.py"), obs("/b.py")])
        assert str(result) == "/a.py\n/b.py"

    def test_duplicate_spans_merge_their_hits(self) -> None:
        result = Result(
            function="grep",
            observations=[
                obs(
                    "/a.py",
                    matches=[
                        Match(start=1, end=3, match=1, content="a\nb\nc"),
                        Match(start=1, end=3, match=3),
                    ],
                ),
            ],
        )
        assert str(result) == "/a.py:1:a\n/a.py-2-b\n/a.py:3:c"

    def test_row_level_projection_switches_to_table(self) -> None:
        result = Result(
            function="grep",
            observations=[obs("/a.py", size_bytes=10, matches=[Match(start=1, end=1, match=1)])],
        )
        out = result.to_str(projection=("path", "size_bytes"))
        assert out.startswith("| path")

    def test_path_only_projection_is_one_line_per_file(self) -> None:
        result = Result(
            function="grep",
            observations=[
                obs("/b.py", matches=[Match(start=1, end=1, match=1), Match(start=5, end=5, match=5)]),
                obs("/a.py"),
            ],
        )
        assert result.to_str(projection=("path",)) == "/a.py\n/b.py"

    def test_empty_region_text_falls_back_to_full_content(self) -> None:
        result = Result(
            function="grep",
            observations=[
                obs("/a.py", content="l1\nl2\nl3", matches=[Match(start=2, end=2, match=2, content="")]),
            ],
        )
        assert str(result) == "/a.py:2:l2"

    def test_empty_region_text_without_fallback_renders_empty_lines(self) -> None:
        result = Result(
            function="grep",
            observations=[obs("/a.py", matches=[Match(start=2, end=2, match=2, content="")])],
        )
        assert str(result) == "/a.py:2:"

    def test_nonempty_region_text_wins_over_empty_duplicate(self) -> None:
        result = Result(
            function="grep",
            observations=[
                obs(
                    "/a.py",
                    matches=[
                        Match(start=2, end=2, match=2, content=""),
                        Match(start=2, end=2, match=2, content="real"),
                    ],
                ),
            ],
        )
        assert str(result) == "/a.py:2:real"

    def test_whole_region_without_text_renders_full_span(self) -> None:
        result = Result(
            function="grep",
            observations=[obs("/a.py", matches=[Match(start=1, end=3), Match(start=1, end=3, match=2)])],
        )
        assert str(result) == "/a.py:1\n/a.py:2\n/a.py:3"


# ---------------------------------------------------------------------------
# Read, stat, tree
# ---------------------------------------------------------------------------


class TestReadStatTree:
    def test_read_single_renders_content_verbatim(self) -> None:
        result = Result(function="read", observations=[obs("/a.md", content="# Title\nbody")])
        assert str(result) == "# Title\nbody"

    def test_read_multi_uses_headers(self) -> None:
        result = Result(
            function="read",
            observations=[obs("/b.md", content="bee"), obs("/a.md", content="ay")],
        )
        assert str(result) == "==> /a.md <==\nay\n\n==> /b.md <==\nbee"

    def test_stat_renders_block(self) -> None:
        result = Result(
            function="stat",
            observations=[
                obs(
                    "/a.md",
                    kind="file",
                    size_bytes=12,
                    updated_at=datetime(2026, 6, 1, tzinfo=UTC),
                ),
            ],
        )
        assert str(result) == ("/a.md\n  kind: file\n  size_bytes: 12\n  updated_at: 2026-06-01 00:00:00+00:00")

    def test_block_indents_multiline_field_value(self) -> None:
        result = Result(
            function="stat",
            observations=[obs("/a", content="alpha\nbeta\ngamma", size_bytes=10)],
        )
        out = result.to_str(projection=("path", "content", "size_bytes"))
        assert out == "/a\n  content: alpha\n    beta\n    gamma\n  size_bytes: 10"

    def test_tree(self) -> None:
        result = Result(
            function="tree",
            observations=[obs("/docs"), obs("/docs/a.md"), obs("/src/m.py")],
        )
        assert str(result) == ("├── docs\n│   └── a.md\n└── src\n    └── m.py")


# ---------------------------------------------------------------------------
# Actions and write
# ---------------------------------------------------------------------------


class TestActionRendering:
    def test_single_path_action(self) -> None:
        result = Result(function="delete", observations=[obs("/a.md")])
        assert str(result) == "Deleted /a.md"

    def test_multi_path_action(self) -> None:
        result = Result(function="move", observations=[obs("/a.md"), obs("/b.md")])
        assert str(result) == "Moved 2 paths"

    def test_remaining_action_verbs(self) -> None:
        assert str(Result(function="copy", observations=[obs("/a.md")])) == "Copied /a.md"
        assert str(Result(function="mkdir", observations=[obs("/d")])) == "Created /d"
        assert str(Result(function="mkedge", observations=[obs("/a.md")])) == "Connected /a.md"

    def test_verb_for_write_and_unmapped_fallback(self) -> None:
        # ``write`` is intercepted by the write formatter before _verb_for, and
        # the generic fallback only fires for an action verb not yet mapped;
        # both are covered directly here as defensive paths.
        assert _verb_for("write") == "Wrote"
        assert _verb_for("custom_op") == "Custom op"
        assert _verb_for("") == "Completed"

    def test_empty_action(self) -> None:
        assert str(Result(function="edit")) == "No changes"

    def test_write_empty_is_nothing_to_do(self) -> None:
        assert str(Result(function="write")) == "write: nothing to do"

    def test_write_summary_counts_kinds_and_excludes_versions(self) -> None:
        result = Result(
            function="write",
            observations=[
                obs("/a.md", kind="file", status="created"),
                obs("/a.md/.vfs/chunks/1/1_5", kind="chunk"),
                obs("/a.md/.vfs/versions/1", kind="version"),
            ],
        )
        assert str(result) == "write success: 1 file, 1 chunk\n\n  created /a.md"

    def test_write_breakdown_reconciles_with_file_count(self) -> None:
        # A file with no status reads as created; the buckets must sum to 3.
        result = Result(
            function="write",
            observations=[
                obs("/a.md", kind="file", status="created"),
                obs("/b.md", kind="file", status="updated"),
                obs("/c.md", kind="file"),
            ],
        )
        assert str(result) == "write success: 3 files (2 created, 1 updated)"

    def test_write_reports_unchanged_files(self) -> None:
        result = Result(
            function="write",
            observations=[
                obs("/a.md", kind="file", status="created"),
                obs("/b.md", kind="file", status="unchanged"),
            ],
        )
        assert str(result) == "write success: 2 files (1 created, 1 unchanged)"

    def test_write_single_file_detail_line_uses_status(self) -> None:
        result = Result(function="write", observations=[obs("/b.md", kind="file", status="updated")])
        assert str(result) == "write success: 1 file\n\n  updated /b.md"

    def test_write_single_file_without_status_reads_as_created(self) -> None:
        result = Result(function="write", observations=[obs("/a.md", kind="file")])
        assert str(result) == "write success: 1 file\n\n  created /a.md"

    def test_write_chunks_only_has_no_file_part(self) -> None:
        result = Result(
            function="write",
            observations=[obs("/a.md/.vfs/chunks/1/1_5", kind="chunk"), obs("/a.md/.vfs/chunks/2/6_9", kind="chunk")],
        )
        assert str(result) == "write success: 2 chunks"

    def test_write_results_still_validate_projection(self) -> None:
        result = Result(function="write", observations=[obs("/a.md", kind="file")])
        with pytest.raises(ValueError, match="unknown field"):
            result.to_str(projection=("bogus",))

    def test_write_errors_block_comes_first(self) -> None:
        result = Result(
            function="write",
            observations=[obs("/a.md", kind="file", status="updated"), obs("/b.md", kind="file", status="created")],
            errors=[ResultError(kind=VFSErrorKind.invalid, message="bad path: /x")],
        )
        assert str(result) == ("write errors:\n  bad path: /x\n\nwrite success: 2 files (1 created, 1 updated)")
