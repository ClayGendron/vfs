"""Tests for chunking: recursive splitter, structure-aware splits, notebooks.

Structure-aware splitting is a native-engine capability by contract, so
the tree-boundary cases carry ``needs_structure``; the pure engine's
declared degradation (character splitter for everything) has its own pin,
exercised on the coverage leg by disabling the seam directly.
"""

from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path

import pytest

import vfs.native
from vfs.models.chunking import (
    CHUNK_GENERATION,
    DEFAULT_SEPARATORS,
    EXTENSION_TO_GRAMMAR,
    STRUCTURE_FALLBACK_GRAMMARS,
    _recursive_split,
    chunk_generation,
    grammar_for_extension,
    recursive_text_split,
    split_code,
    split_code_batch,
    split_notebook,
    split_with_line_ranges,
)
from vfs.native import active_core, structure_grammars

needs_structure = pytest.mark.skipif(
    active_core() == "python",
    reason="structure-aware chunking is native-only; the pure engine character-splits by contract",
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
# Grammar resolution and the native coverage contract
# ---------------------------------------------------------------------------


class TestGrammarResolution:
    def test_common_extensions_are_mapped(self) -> None:
        assert EXTENSION_TO_GRAMMAR["py"] == "python"
        assert EXTENSION_TO_GRAMMAR["md"] == "markdown"

    @pytest.mark.parametrize("ext", [None, "", "ipynb", "definitely_not_an_ext"])
    def test_unresolvable_extensions_return_none(self, ext: str | None) -> None:
        assert grammar_for_extension(ext) is None

    def test_mapped_extension_resolves(self) -> None:
        assert grammar_for_extension("py") == "python"

    @needs_structure
    def test_native_registry_covers_the_map_minus_declared_fallbacks(self) -> None:
        # The coverage contract: every mapped grammar is either served by
        # the native registry or on the declared character-splitter list —
        # and the declared list never shadows a grammar the registry serves.
        mapped = set(EXTENSION_TO_GRAMMAR.values())
        served = structure_grammars()
        assert mapped - served == STRUCTURE_FALLBACK_GRAMMARS
        assert STRUCTURE_FALLBACK_GRAMMARS.isdisjoint(served)


# ---------------------------------------------------------------------------
# Structure-aware splitting
# ---------------------------------------------------------------------------


class TestSplitCode:
    def test_content_within_budget_is_one_piece(self) -> None:
        content = "def f():\n    return 1\n"
        assert split_code(content, language="python") == split_with_line_ranges(content)

    @needs_structure
    def test_python_splits_on_structure_with_true_line_ranges(self) -> None:
        content = "".join(f"def f{i}():\n    return {i}\n\n\n" for i in range(8))
        chunks = split_code(content, language="python", chunk_size=48)
        assert len(chunks) > 1
        assert all(len(text.encode()) <= 48 for text, _ls, _le in chunks)
        assert_true_line_ranges(content, chunks)

    @needs_structure
    def test_adjacent_chunks_never_overlap_lines(self) -> None:
        content = "".join(f"def f{i}():\n    return {i}\n" for i in range(8))
        chunks = split_code(content, language="python", chunk_size=48)
        for (_t1, _ls1, le1), (_t2, ls2, _le2) in pairwise(chunks):
            assert le1 < ls2

    @needs_structure
    def test_oversized_indivisible_leaf_falls_back_with_true_ranges(self) -> None:
        body = "\n".join(f"line {i} of the long docstring text" for i in range(12))
        content = f'doc = """\n{body}\n"""\n\nx = 1\n'
        chunks = split_code(content, language="python", chunk_size=64)
        assert len(chunks) > 2
        assert_true_line_ranges(content, chunks)

    @needs_structure
    def test_gap_spans_between_nodes_are_covered(self) -> None:
        content = "{" + ", ".join(f'"k{i}": "{"v" * 20}"' for i in range(20)) + "}"
        chunks = split_code(content, language="json", chunk_size=64)
        assert len(chunks) > 1
        assert_true_line_ranges(content, chunks)

    @needs_structure
    def test_whitespace_only_spans_are_dropped(self) -> None:
        content = "x = 1\n" + "\n" * 120 + "y = 2\n"
        chunks = split_code(content, language="python", chunk_size=8)
        assert all(text.strip() for text, _ls, _le in chunks)
        assert_true_line_ranges(content, chunks)
        (y_chunk,) = [c for c in chunks if "y = 2" in c[0]]
        assert y_chunk[1] == 122

    @needs_structure
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

    def test_pure_engine_degrades_to_the_character_splitter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The ADR-declared divergence: with no native engine there is no
        # tree-sitter at all, and a mapped grammar character-splits.
        monkeypatch.setattr(vfs.native, "_active", None)
        content = "".join(f"def f{i}():\n    return {i}\n\n\n" for i in range(8))
        expected = split_with_line_ranges(content, chunk_size=48)
        assert split_code(content, language="python", chunk_size=48) == expected


class TestSplitCodeBatch:
    def test_batch_matches_single_splits_across_mixed_routes(self) -> None:
        items = [
            ("tiny = 1\n", "python"),  # fits one chunk
            ("".join(f"def f{i}():\n    return {i}\n\n\n" for i in range(40)), "python"),  # structure path
            ("plain text line\n" * 60, "no_such_grammar"),  # engine declines
        ]
        batch = split_code_batch(items, chunk_size=128)
        assert batch == [split_code(content, language=grammar, chunk_size=128) for content, grammar in items]

    def test_empty_batch_is_empty(self) -> None:
        assert split_code_batch([], chunk_size=128) == []


class TestChunkGeneration:
    def test_generation_names_the_engine_and_the_declared_constant(self) -> None:
        assert chunk_generation() == f"{active_core()}:{CHUNK_GENERATION}"

    def test_pure_engine_yields_a_distinct_generation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(vfs.native, "_active", None)
        assert chunk_generation() == f"python:{CHUNK_GENERATION}"


class TestChunkFixtures:
    """Committed engine-behavior pins: the fixtures split exactly as recorded.

    ``fixtures/chunking/expected.json`` is regenerated deliberately (see
    ``fixtures/chunking/regen.py``) when a grammar crate or the walker
    changes — never silently; a mismatch here is a chunk-shape change
    that must ride a declared generation bump.
    """

    FIXTURES = Path(__file__).parent / "fixtures" / "chunking"

    @needs_structure
    @pytest.mark.parametrize(
        ("name", "grammar"),
        [("sample.py", "python"), ("sample.c", "c"), ("sample.md", "markdown")],
    )
    def test_fixture_chunks_match_the_committed_expectation(self, name: str, grammar: str) -> None:
        content = (self.FIXTURES / name).read_text()
        expected = [tuple(row) for row in json.loads((self.FIXTURES / "expected.json").read_text())[name]]
        got = split_code(content, language=grammar, chunk_size=256)
        assert got == expected
        assert_true_line_ranges(content, got)


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

    def test_malformed_metadata_degrades_to_the_default_grammar(self) -> None:
        # The kernel fields are advisory: every junk shape selects the
        # default grammar rather than raising or voiding the cells.
        cell = {"cell_type": "code", "source": "aaa = 1"}
        for metadata in (
            ["not", "a", "mapping"],
            "kernelspec",
            {"kernelspec": "python"},
            {"kernelspec": ["python"]},
            {"kernelspec": {"language": 42}},
            {"kernelspec": {"language": ["python"]}},
            {"kernelspec": {"language": ""}},
        ):
            notebook = json.dumps({"cells": [cell], "metadata": metadata})
            assert split_notebook(notebook) == [("aaa = 1", 1, 1)], metadata

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


# ---------------------------------------------------------------------------
# The exception floor — deep nesting and unstorable characters
# ---------------------------------------------------------------------------


class TestExceptionFloor:
    @pytest.mark.parametrize("depth", [10_000, 100_000])
    def test_deep_nested_json_degrades_to_the_text_split(self, depth: int) -> None:
        # json.loads overruns its recursion budget on this body; the parse
        # guard must route it to the fallback, never let the raise escape.
        body = "[" * depth + "]" * depth
        assert split_notebook(body, chunk_size=64) == split_with_line_ranges(body, chunk_size=64)

    def test_a_manufactured_surrogate_in_a_code_cell_is_scrubbed(self) -> None:
        # The notebook JSON is pure ASCII — the write gate admits it — and
        # json.loads manufactures the lone surrogate from the escape.
        source = "needle_value = 1  # \ud800 marker\n" * 4
        notebook = make_notebook([{"cell_type": "code", "source": source}])
        assert "\ud800" not in notebook and "\\ud800" in notebook
        pieces = split_notebook(notebook, chunk_size=64)
        assert pieces
        joined = "".join(text for text, _start, _end in pieces)
        assert "\ud800" not in joined and "�" in joined
        # One character for one: the scrub moves no boundary or line range.
        assert pieces == split_notebook(notebook.replace("\\ud800", "\\ufffd"), chunk_size=64)

    def test_a_manufactured_surrogate_in_a_markdown_cell_is_scrubbed(self) -> None:
        source = "# Title\nprose \udfff prose continues on this line\n" * 3
        notebook = make_notebook([{"cell_type": "markdown", "source": source}])
        pieces = split_notebook(notebook, chunk_size=64)
        assert pieces
        assert all("\udfff" not in text for text, _start, _end in pieces)

    def test_a_manufactured_null_byte_never_reaches_a_chunk(self) -> None:
        source = "hello \x00 world, padded well enough to chunk\n" * 3
        notebook = make_notebook([{"cell_type": "markdown", "source": source}])
        assert "\x00" not in notebook
        pieces = split_notebook(notebook, chunk_size=64)
        assert pieces
        joined = "".join(text for text, _start, _end in pieces)
        assert "\x00" not in joined and "�" in joined

    def test_the_splitter_takes_a_raw_surrogate_string_directly(self) -> None:
        content = "alpha \ud800 beta gamma delta epsilon\n" * 20
        pieces = split_code(content, language="python", chunk_size=64)
        assert pieces
        texts = [text for text, _start, _end in pieces]
        assert all("\ud800" not in text for text in texts)
        assert any("�" in text for text in texts)

    def test_batch_and_single_agree_on_pathological_bodies(self) -> None:
        items = [
            ("clean = 1\n" * 30, "python"),
            ("dirty = 1  # \ud800\n" * 30, "python"),
            ("nul \x00 text on this line\n" * 30, "no_such_grammar"),
        ]
        batch = split_code_batch(items, chunk_size=64)
        assert batch == [split_code(content, language=grammar, chunk_size=64) for content, grammar in items]

    def test_the_recursive_splitter_never_raises_on_a_surrogate(self) -> None:
        # The character splitter passes text through untouched; totality
        # comes from the byte-domain surrogatepass in normalize_content.
        content = "abc \ud800 def\n" * 10
        pieces = recursive_text_split(content, chunk_size=16)
        assert "".join(pieces) == content

    def test_pure_engine_scrubs_identically(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The scrub is pre-seam Python: the pure engine's character split
        # sees the same scrubbed body the native structure path sees.
        monkeypatch.setattr(vfs.native, "_active", None)
        content = "dirty = 1  # \ud800 padded line here\n" * 20
        pieces = split_code(content, language="python", chunk_size=64)
        assert pieces == split_with_line_ranges(content.replace("\ud800", "�"), chunk_size=64)

    @needs_structure
    def test_structure_path_chunks_carry_the_scrub_with_true_ranges(self) -> None:
        content = "".join(f"def f{i}():\n    return '\ud800{i}'\n\n\n" for i in range(20))
        pieces = split_code(content, language="python", chunk_size=128)
        scrubbed = content.replace("\ud800", "�")
        assert_true_line_ranges(scrubbed, pieces)
        assert all("\ud800" not in text for text, _start, _end in pieces)
