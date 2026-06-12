"""Tests for chunking: recursive splitter, structure-aware splits, notebooks."""

from __future__ import annotations

import json
from itertools import pairwise

import pytest

from vfs.chunking import (
    DEFAULT_SEPARATORS,
    EXTENSION_TO_GRAMMAR,
    _call,
    _merge_spans,
    _parser,
    _recursive_split,
    grammar_for_extension,
    recursive_text_split,
    split_code,
    split_notebook,
    split_with_line_ranges,
)


def assert_true_line_ranges(content: str, chunks: list[tuple[str, int, int]]) -> None:
    """Every chunk's (line_start, line_end) must match its true location in *content*.

    Chunks must appear in order; gaps (dropped whitespace spans) are allowed.
    """
    assert chunks
    pos = 0
    for text, line_start, line_end in chunks:
        idx = content.index(text, pos)
        assert line_start == content.count("\n", 0, idx) + 1, f"line_start wrong for {text!r}"
        last = idx + len(text) - 1
        assert line_end == content.count("\n", 0, last) + 1, f"line_end wrong for {text!r}"
        pos = idx + len(text)


# ---------------------------------------------------------------------------
# Recursive character splitter
# ---------------------------------------------------------------------------


class TestRecursiveTextSplit:
    def test_reconstruction_and_budget(self) -> None:
        content = "First paragraph here.\n\nSecond one, a bit longer.\n\nshort\nlines\nnow"
        pieces = recursive_text_split(content, chunk_size=20)
        assert "".join(pieces) == content
        assert all(len(p) <= 20 for p in pieces)

    def test_sub_trigram_content_yields_nothing(self) -> None:
        assert recursive_text_split("hi") == []

    def test_content_within_budget_is_one_piece(self) -> None:
        assert recursive_text_split("hello world", chunk_size=64) == ["hello world"]

    def test_separator_stays_attached_to_preceding_piece(self) -> None:
        pieces = recursive_text_split("aaa\n\nbbb\nccc", chunk_size=6)
        assert pieces == ["aaa\n\n", "bbb\n", "ccc"]

    def test_separatorless_run_falls_back_to_fixed_size(self) -> None:
        assert recursive_text_split("x" * 10, chunk_size=4) == ["xxxx", "xxxx", "xx"]

    def test_unmatched_custom_separators_fall_back_to_fixed_size(self) -> None:
        pieces = recursive_text_split("aaaabbbb", chunk_size=2, separators=("X",))
        assert pieces == ["aa", "aa", "bb", "bb"]

    def test_matched_custom_separator_recurses_into_fixed_size(self) -> None:
        assert recursive_text_split("aaXbb", chunk_size=2, separators=("X",)) == ["aa", "X", "bb"]

    def test_chunk_size_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="chunk_size must be positive"):
            recursive_text_split("hello world", chunk_size=0)

    def test_separators_must_not_be_empty(self) -> None:
        with pytest.raises(ValueError, match="separators must not be empty"):
            recursive_text_split("hello world", chunk_size=4, separators=())

    def test_empty_content_splits_to_nothing(self) -> None:
        assert _recursive_split("", 4, DEFAULT_SEPARATORS) == []

    def test_buffer_flushes_before_oversized_piece_recurses(self) -> None:
        pieces = recursive_text_split("aa bbbbbbbbbb", chunk_size=4)
        assert pieces == ["aa ", "bbbb", "bbbb", "bb"]
        assert "".join(pieces) == "aa bbbbbbbbbb"


class TestSplitWithLineRanges:
    def test_line_ranges_match_ground_truth(self) -> None:
        content = "alpha beta\ngamma\n\ndelta epsilon zeta\neta theta\n"
        chunks = split_with_line_ranges(content, chunk_size=12)
        assert "".join(text for text, _ls, _le in chunks) == content
        assert_true_line_ranges(content, chunks)

    def test_chunks_inside_an_oversized_line_share_it(self) -> None:
        chunks = split_with_line_ranges("x" * 100, chunk_size=10)
        assert len(chunks) == 10
        assert all((ls, le) == (1, 1) for _text, ls, le in chunks)

    def test_trailing_newline_does_not_open_a_phantom_line(self) -> None:
        chunks = split_with_line_ranges("abc\ndef\n", chunk_size=4)
        assert chunks == [("abc\n", 1, 1), ("def\n", 2, 2)]

    def test_sub_trigram_content_yields_nothing(self) -> None:
        assert split_with_line_ranges("hi") == []


# ---------------------------------------------------------------------------
# Grammar resolution and the tree-sitter binding shims
# ---------------------------------------------------------------------------


class TestGrammarResolution:
    def test_common_extensions_survive_the_available_filter(self) -> None:
        assert EXTENSION_TO_GRAMMAR["py"] == "python"
        assert EXTENSION_TO_GRAMMAR["md"] == "markdown"

    @pytest.mark.parametrize("ext", [None, "", "ipynb", "definitely_not_an_ext"])
    def test_unresolvable_extensions_return_none(self, ext: str | None) -> None:
        assert grammar_for_extension(ext) is None

    def test_mapped_extension_resolves(self) -> None:
        assert grammar_for_extension("py") == "python"

    def test_parser_instances_are_cached(self) -> None:
        assert _parser("python") is _parser("python")

    def test_call_resolves_methods_and_properties(self) -> None:
        assert _call(lambda: 7) == 7  # method-style accessor
        assert _call(7) == 7  # property-style accessor


# ---------------------------------------------------------------------------
# Structure-aware splitting
# ---------------------------------------------------------------------------


class TestMergeSpans:
    def test_empty_input(self) -> None:
        assert _merge_spans([], 10) == []

    def test_greedy_merge_up_to_budget(self) -> None:
        assert _merge_spans([(0, 10), (10, 20), (20, 40)], 25) == [(0, 20), (20, 40)]

    def test_oversized_first_span_emitted_alone(self) -> None:
        assert _merge_spans([(0, 50), (50, 60)], 25) == [(0, 50), (50, 60)]


class TestSplitCode:
    def test_content_within_budget_is_one_piece(self) -> None:
        content = "def f():\n    return 1\n"
        assert split_code(content, language="python") == split_with_line_ranges(content)

    def test_python_splits_on_structure_with_true_line_ranges(self) -> None:
        content = "".join(f"def f{i}():\n    return {i}\n\n\n" for i in range(8))
        chunks = split_code(content, language="python", chunk_size=48)
        assert len(chunks) > 1
        assert all(len(text.encode()) <= 48 for text, _ls, _le in chunks)
        assert_true_line_ranges(content, chunks)

    def test_adjacent_chunks_never_overlap_lines(self) -> None:
        content = "".join(f"def f{i}():\n    return {i}\n" for i in range(8))
        chunks = split_code(content, language="python", chunk_size=48)
        for (_t1, _ls1, le1), (_t2, ls2, _le2) in pairwise(chunks):
            assert le1 < ls2

    def test_oversized_indivisible_leaf_falls_back_with_true_ranges(self) -> None:
        body = "\n".join(f"line {i} of the long docstring text" for i in range(12))
        content = f'doc = """\n{body}\n"""\n\nx = 1\n'
        chunks = split_code(content, language="python", chunk_size=64)
        assert len(chunks) > 2
        assert_true_line_ranges(content, chunks)

    def test_gap_spans_between_nodes_are_covered(self) -> None:
        content = "{" + ", ".join(f'"k{i}": "{"v" * 20}"' for i in range(20)) + "}"
        chunks = split_code(content, language="json", chunk_size=64)
        assert len(chunks) > 1
        assert_true_line_ranges(content, chunks)

    def test_whitespace_only_spans_are_dropped(self) -> None:
        content = "x = 1\n" + "\n" * 120 + "y = 2\n"
        chunks = split_code(content, language="python", chunk_size=8)
        assert all(text.strip() for text, _ls, _le in chunks)
        assert_true_line_ranges(content, chunks)
        (y_chunk,) = [c for c in chunks if "y = 2" in c[0]]
        assert y_chunk[1] == 122

    def test_multibyte_content_keeps_lines_and_loses_nothing(self) -> None:
        content = "".join(f'w{i} = "🎉🎉🎉"\n' for i in range(10))
        chunks = split_code(content, language="python", chunk_size=64)
        assert len(chunks) > 1
        assert all("�" not in text for text, _ls, _le in chunks)
        assert_true_line_ranges(content, chunks)

    def test_unknown_grammar_falls_back_wholesale(self) -> None:
        content = "some plain text\n" * 8
        expected = split_with_line_ranges(content, chunk_size=32)
        assert split_code(content, language="no_such_grammar", chunk_size=32) == expected


# ---------------------------------------------------------------------------
# Notebooks
# ---------------------------------------------------------------------------


def make_notebook(cells: list[object], language: str | None = "python") -> str:
    metadata = {"kernelspec": {"language": language}} if language is not None else {}
    return json.dumps({"cells": cells, "metadata": metadata, "nbformat": 4})


class TestSplitNotebook:
    def test_cells_route_by_type_with_absolute_lines(self) -> None:
        notebook = make_notebook(
            [
                {"cell_type": "markdown", "source": "# Title\nSome prose here."},
                {"cell_type": "code", "source": "aaa = 1\nbbb = 2"},
            ],
        )
        assert split_notebook(notebook) == [
            ("# Title\nSome prose here.", 1, 2),
            ("aaa = 1\nbbb = 2", 3, 4),
        ]

    def test_nbformat_list_sources_are_joined(self) -> None:
        notebook = make_notebook([{"cell_type": "code", "source": ["aaa = 1\n", "bbb = 2"]}])
        assert split_notebook(notebook) == [("aaa = 1\nbbb = 2", 1, 2)]

    def test_kernel_display_language_maps_to_grammar(self) -> None:
        notebook = make_notebook([{"cell_type": "code", "source": "aaa = 1"}], language="python3")
        assert split_notebook(notebook) == [("aaa = 1", 1, 1)]

    def test_unknown_kernel_still_chunks_via_fallback(self) -> None:
        notebook = make_notebook([{"cell_type": "code", "source": "aaa = 1"}], language="klingon")
        assert split_notebook(notebook) == [("aaa = 1", 1, 1)]

    def test_missing_kernelspec_defaults_to_python(self) -> None:
        notebook = json.dumps({"cells": [{"cell_type": "code", "source": "aaa = 1"}], "metadata": None})
        assert split_notebook(notebook) == [("aaa = 1", 1, 1)]

    def test_raw_cells_yield_nothing_but_advance_lines(self) -> None:
        notebook = make_notebook(
            [
                {"cell_type": "raw", "source": "r1\nr2"},
                {"cell_type": "code", "source": "ccc = 3"},
            ],
        )
        assert split_notebook(notebook) == [("ccc = 3", 3, 3)]

    def test_non_dict_cells_are_ignored(self) -> None:
        notebook = make_notebook(["junk", {"cell_type": "code", "source": "eee = 5"}])
        assert split_notebook(notebook) == [("eee = 5", 1, 1)]

    def test_whitespace_only_sources_are_skipped_but_counted(self) -> None:
        notebook = make_notebook(
            [
                {"cell_type": "code", "source": "   \n"},
                {"cell_type": "code", "source": "ddd = 4"},
            ],
        )
        assert split_notebook(notebook) == [("ddd = 4", 3, 3)]

    def test_malformed_sources_degrade_instead_of_crashing(self) -> None:
        notebook = make_notebook(
            [
                {"cell_type": "code", "source": None},
                {"cell_type": "raw", "source": 7},
                {"cell_type": "code", "source": [1, 2]},
                {"cell_type": "code", "source": ["okay\n", 3]},
                {"cell_type": "code", "source": "fff = 6"},
            ],
        )
        assert split_notebook(notebook) == [("okay\n", 4, 4), ("fff = 6", 6, 6)]

    @pytest.mark.parametrize(
        "content",
        [
            "not json { definitely not parseable as a notebook",  # invalid JSON
            json.dumps({"no_cells": 1, "pad": "padding " * 8}),  # missing cells
            json.dumps({"cells": "not a list", "pad": "padding " * 8}),  # cells wrong type
            json.dumps([1, 2, 3, "padding padding padding"]),  # list["cells"]: TypeError
            "42",  # bare scalar (sub-trigram: both sides yield [])
        ],
    )
    def test_malformed_notebooks_fall_back_to_text_split(self, content: str) -> None:
        assert split_notebook(content, chunk_size=16) == split_with_line_ranges(content, chunk_size=16)
