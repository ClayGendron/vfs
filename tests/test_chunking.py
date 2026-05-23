"""Structure-aware chunking: ``split_code``, ``split_notebook``, dispatch."""

from __future__ import annotations

import json

from vfs.chunking import (
    EXTENSION_TO_GRAMMAR,
    NOTEBOOK_EXTENSION,
    grammar_for_extension,
    split_code,
    split_notebook,
)


def _reconstruct(chunks: list[tuple[str, int, int]]) -> str:
    """Non-whitespace content concatenated across chunks (boundary-agnostic)."""
    return "".join(text for text, _ls, _le in chunks).replace("\n", "").replace(" ", "")


class TestGrammarForExtension:
    def test_none_extension(self):
        assert grammar_for_extension(None) is None

    def test_empty_extension(self):
        assert grammar_for_extension("") is None

    def test_notebook_extension_is_none(self):
        # Notebooks are handled by split_notebook, not the grammar path.
        assert grammar_for_extension(NOTEBOOK_EXTENSION) is None

    def test_unmapped_extension(self):
        assert grammar_for_extension("txt") is None

    def test_python(self):
        assert grammar_for_extension("py") == "python"

    def test_markdown_family(self):
        assert grammar_for_extension("md") == "markdown"
        assert grammar_for_extension("rmd") == "markdown"

    def test_only_available_grammars_kept(self):
        # Every mapped grammar must resolve in the installed pack.
        from tree_sitter_language_pack import get_parser

        for grammar in set(EXTENSION_TO_GRAMMAR.values()):
            get_parser(grammar)  # raises if missing


class TestSplitCode:
    def test_short_content_returns_empty(self):
        assert split_code("def f():\n    return 1\n", language="python") == []

    def test_multi_function_python_splits_and_honors_budget(self):
        src = "\n\n".join(
            f"def func_{i}():\n" + "    x = 1\n" * 80 + "    return x" for i in range(6)
        )
        chunks = split_code(src, language="python", chunk_size=2048)
        assert len(chunks) > 1
        assert all(len(text.encode()) <= 2048 for text, _ls, _le in chunks)
        for _text, line_start, line_end in chunks:
            assert 1 <= line_start <= line_end

    def test_reconstruction_is_lossless(self):
        src = "\n\n".join(
            f"def func_{i}():\n" + "    x = 1\n" * 80 + "    return x" for i in range(6)
        )
        chunks = split_code(src, language="python", chunk_size=2048)
        assert _reconstruct(chunks) == src.replace("\n", "").replace(" ", "")

    def test_multibyte_content_byte_exact(self):
        # é is two UTF-8 bytes; line numbers must come from byte offsets.
        src = "\n\n".join(
            f"def café_{i}():\n" + "    e = 'héllo wörld'\n" * 60 + "    return e"
            for i in range(6)
        )
        chunks = split_code(src, language="python", chunk_size=2048)
        assert _reconstruct(chunks) == src.replace("\n", "").replace(" ", "")

    def test_invalid_grammar_falls_back(self):
        content = "x" * 5000
        chunks = split_code(content, language="not_a_real_language", chunk_size=2048)
        # Fallback to the recursive separator splitter still produces chunks.
        assert len(chunks) > 1
        assert all(len(text) <= 2048 for text, _ls, _le in chunks)

    def test_oversized_indivisible_leaf_fills(self):
        # A single string literal larger than the budget is one leaf node with
        # no named children — must be separator-filled, never emitted whole.
        src = 'x = "' + ("a" * 6000) + '"\n'
        chunks = split_code(src, language="python", chunk_size=2048)
        assert len(chunks) > 1
        assert all(len(text.encode()) <= 2048 for text, _ls, _le in chunks)

    def test_markdown_is_heading_aware_and_fence_safe(self):
        body = "\n\n".join(f"## Section {i}\n\n" + "prose line\n" * 40 for i in range(6))
        fence = "\n\n```python\n# this is not a heading\nx = 1\n```\n"
        src = body + fence
        chunks = split_code(src, language="markdown", chunk_size=2048)
        assert len(chunks) > 1
        # No chunk begins inside the fenced block (i.e. with the comment line).
        assert not any(text.lstrip().startswith("# this is not a heading") for text, _ls, _le in chunks)


class TestSplitNotebook:
    def _nb(self, cells, **metadata) -> str:
        return json.dumps({"cells": cells, "metadata": metadata})

    def test_basic_markdown_and_code_cells(self):
        nb = self._nb(
            [
                {"cell_type": "markdown", "source": ["# Title\n", "intro\n"]},
                {"cell_type": "code", "source": ["import os\n", "x = 1\n"]},
            ],
            kernelspec={"language": "python"},
        )
        chunks = split_notebook(nb)
        texts = [t for t, _ls, _le in chunks]
        assert any("# Title" in t for t in texts)
        assert any("import os" in t for t in texts)
        # Outputs/metadata/JSON keys never leak into chunk content.
        assert not any('"cell_type"' in t for t in texts)

    def test_line_numbers_are_monotonic_across_cells(self):
        nb = self._nb(
            [
                {"cell_type": "markdown", "source": "# A\nbody\n"},
                {"cell_type": "code", "source": "y = 2\n"},
            ]
        )
        chunks = split_notebook(nb)
        starts = [ls for _t, ls, _le in chunks]
        assert starts == sorted(starts)
        assert all(1 <= ls <= le for _t, ls, le in chunks)

    def test_string_source_and_list_source_equivalent(self):
        as_list = split_notebook(self._nb([{"cell_type": "code", "source": ["a = 1\n", "b = 2\n"]}]))
        as_str = split_notebook(self._nb([{"cell_type": "code", "source": "a = 1\nb = 2\n"}]))
        assert [t for t, *_ in as_list] == [t for t, *_ in as_str]

    def test_large_code_cell_splits_into_pieces(self):
        big = "def f():\n" + "    x = 1\n" * 400 + "    return x\n"
        chunks = split_notebook(self._nb([{"cell_type": "code", "source": big}]))
        assert len(chunks) > 1
        assert all(len(text.encode()) <= 2048 for text, _ls, _le in chunks)

    def test_raw_and_unknown_cells_skipped(self):
        nb = self._nb(
            [
                {"cell_type": "raw", "source": "raw stuff\n"},
                {"cell_type": "code", "source": "kept = 1\n"},
                {"cell_type": "weird", "source": "ignored\n"},
            ]
        )
        texts = [t for t, _ls, _le in split_notebook(nb)]
        assert texts == ["kept = 1\n"]

    def test_non_dict_cell_skipped(self):
        nb = json.dumps({"cells": [42, {"cell_type": "code", "source": "ok = 1\n"}]})
        texts = [t for t, _ls, _le in split_notebook(nb)]
        assert texts == ["ok = 1\n"]

    def test_default_kernel_is_python(self):
        # No kernelspec → code cells chunk as python without error.
        nb = self._nb([{"cell_type": "code", "source": "z = 3\n"}])
        assert [t for t, *_ in split_notebook(nb)] == ["z = 3\n"]

    def test_kernel_alias_mapped(self):
        nb = self._nb(
            [{"cell_type": "code", "source": "q = 1\n"}],
            kernelspec={"language": "python3"},
        )
        assert [t for t, *_ in split_notebook(nb)] == ["q = 1\n"]

    def test_empty_cells_returns_empty(self):
        assert split_notebook(json.dumps({"cells": []})) == []

    def test_malformed_json_falls_back(self):
        # Long non-JSON content falls back to the recursive splitter.
        content = "{ this is not valid json " * 400
        chunks = split_notebook(content)
        assert len(chunks) > 1

    def test_cells_not_a_list_falls_back(self):
        chunks = split_notebook(json.dumps({"cells": "nope"}))
        assert chunks == []  # short content → recursive splitter returns []
