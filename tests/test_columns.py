"""Unit tests for the per-function column map."""

from __future__ import annotations

import pytest

from vfs.columns import (
    DEFAULT_COLUMNS,
    ENTRY_FIELD_TO_MODEL_COLUMNS,
    default_columns,
    entry_field_columns,
    required_model_columns,
)
from vfs.results import ENTRY_FIELDS


class TestEntryFieldMap:
    def test_covers_every_entry_field(self):
        assert set(ENTRY_FIELD_TO_MODEL_COLUMNS.keys()) == set(ENTRY_FIELDS)

    def test_score_is_computed(self):
        assert entry_field_columns("score") == frozenset()

    def test_lines_is_computed(self):
        assert entry_field_columns("lines") == frozenset()

    def test_row_fields_map_to_matching_column(self):
        for field in ("path", "kind", "content", "size_bytes", "updated_at"):
            assert entry_field_columns(field) == frozenset({field})

    def test_degree_fields_are_computed(self):
        assert entry_field_columns("in_degree") == frozenset()
        assert entry_field_columns("out_degree") == frozenset()

    def test_unknown_field_raises(self):
        with pytest.raises(KeyError):
            entry_field_columns("bogus")


class TestDefaultColumns:
    def test_covers_every_function_name_users_can_write(self):
        # Every function that shows up as a VFSResult.function in the codebase should have a default.
        required = {
            "read", "stat", "ls", "tree",
            "glob", "grep",
            "vector_search", "semantic_search", "lexical_search",
            "pagerank", "betweenness_centrality", "closeness_centrality",
            "degree_centrality", "in_degree_centrality", "out_degree_centrality", "hits",
            "write", "delete", "edit", "move", "copy", "mkdir", "mkconn",
            "predecessors", "successors", "ancestors", "descendants", "neighborhood",
            "meeting_subgraph", "min_meeting_subgraph",
            "hybrid",
        }  # fmt: skip
        assert required <= set(DEFAULT_COLUMNS.keys())

    def test_path_always_in_default(self):
        for function, cols in DEFAULT_COLUMNS.items():
            assert "path" in cols, f"{function} default missing 'path'"

    def test_read_includes_content(self):
        assert "content" in default_columns("read")

    def test_grep_includes_content(self):
        # Grep renders sliced content — content must be in the SELECT.
        assert "content" in default_columns("grep")

    def test_stat_excludes_content(self):
        assert "content" not in default_columns("stat")

    def test_ls_is_minimal(self):
        assert default_columns("ls") == frozenset({"path", "kind"})

    def test_ranked_search_pulls_row_metadata(self):
        for fn in ("vector_search", "semantic_search", "lexical_search", "bm25"):
            cols = default_columns(fn)
            assert "path" in cols
            assert "updated_at" in cols

    def test_unknown_function_falls_back_to_path_only(self):
        assert default_columns("nonsense_function") == frozenset({"path"})


class TestRequiredModelColumns:
    def test_no_projection_is_default(self):
        assert required_model_columns("glob") == default_columns("glob")
        assert required_model_columns("glob", None) == default_columns("glob")

    def test_default_sentinel_is_noop(self):
        assert required_model_columns("glob", ("default",)) == default_columns("glob")

    def test_all_sentinel_widens_to_every_row_backed_field(self):
        cols = required_model_columns("glob", ("all",))
        # score and lines are computed — not in model columns
        assert cols >= {"path", "kind", "content", "size_bytes", "updated_at"}

    def test_projection_adds_column(self):
        # ls default is {path, kind}; asking for updated_at must widen the SELECT.
        cols = required_model_columns("ls", ("path", "updated_at"))
        assert "updated_at" in cols
        assert "path" in cols
        assert "kind" in cols  # still in default

    def test_projection_score_does_not_widen(self):
        # score is computed; asking for it doesn't add any model columns.
        before = default_columns("vector_search")
        after = required_model_columns("vector_search", ("path", "score"))
        assert after == before

    def test_projection_lines_does_not_widen(self):
        # lines is computed by grep; listing it in projection doesn't add model columns.
        before = default_columns("grep")
        after = required_model_columns("grep", ("path", "lines"))
        assert after == before

    def test_unknown_projection_field_raises(self):
        with pytest.raises(ValueError, match="unknown field 'bogus'"):
            required_model_columns("glob", ("path", "bogus"))

    def test_default_plus_field_combines(self):
        cols = required_model_columns("ls", ("default", "updated_at"))
        assert cols == default_columns("ls") | {"updated_at"}

    def test_returns_frozenset(self):
        cols = required_model_columns("glob")
        assert isinstance(cols, frozenset)
