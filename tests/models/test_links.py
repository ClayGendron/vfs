"""Tests for the markdown reference extractor behind ``vfs.models.links``.

The engine's kernel reads the tree-sitter-markdown block and inline
trees; the oracle in ``tests/support/oracles/links.py`` reads the same
shapes line by line and referees the kernel over the golden corpus.
The corners a line reader cannot see — indented code, a code span
across a line break — are pinned on the kernel alone.
"""

from __future__ import annotations

import pytest

from tests.ranking.corpora import VFS_NATIVE
from tests.support.oracles.links import markdown_refs as oracle_refs
from vfs import native
from vfs.models.links import (
    LINK_EDGE_TYPE,
    MAX_LINK_CONTEXT_LENGTH,
    LinkRef,
    clean_dest,
    extract_links,
    link_candidates,
    link_generation,
)
from vfs.paths import Path

SAMPLE = """# Title

See [the spec](../specs/138/spec.md "title") and `base.py`, then ![diagram](img/flow.png).
A [web link](https://example.com/x.md) and [an anchor](#section) are not references.

```python
[fenced](a.md)  # code
```

    [indented](b.md)

`[in a code span](c.md)` is code; `` `d.md` `` holds literal backticks.

[full][ref] and [ref] resolve through their definition.

[ref]: ../decisions/053.md
[spaced]: <e f.md> 'title'
"""


def _dests(content: str) -> list[str]:
    [refs] = extract_links([content])
    return [ref.dest for ref in refs]


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


class TestExtractLinks:
    def test_the_sample_yields_only_in_mount_shapes_in_document_order(self) -> None:
        assert _dests(SAMPLE) == ["../specs/138/spec.md", "base.py", "img/flow.png", "../decisions/053.md", "e f.md"]

    def test_the_referring_line_rides_along_folded(self) -> None:
        [refs] = extract_links(["\n  a   [x](y.md)\t\tb  \n"])
        assert refs == [LinkRef("y.md", "a [x](y.md) b")]
        [refs] = extract_links([f"[x](y.md) {'z' * 400}"])
        assert len(refs[0].context) == MAX_LINK_CONTEXT_LENGTH

    def test_fragments_and_queries_come_off_and_urls_are_dropped(self) -> None:
        assert clean_dest("a/b.md#section") == "a/b.md"
        assert clean_dest("a/b.md?v=2#s") == "a/b.md"
        assert clean_dest("  spaced.md ") == "spaced.md"
        for url in ("https://x.y/z.md", "mailto:a@b.c", "//cdn/x.md", "#anchor", "", "   "):
            assert clean_dest(url) is None

    def test_code_spans_count_only_when_path_shaped(self) -> None:
        body = "`base.py` `storage/backends` `not a path` `word` `a.toolongext` `.md` `vfs.storage` `x.md#frag`"
        assert _dests(body) == ["base.py", "storage/backends", "vfs.storage"]

    def test_a_code_span_across_a_line_break_is_one_span(self) -> None:
        # A line reader sees two stray backticks; the tree sees one span.
        assert _dests("`a\nb`\n`c.md`") == ["c.md"]

    def test_batches_align_with_their_bodies(self) -> None:
        batch = extract_links(["[a](a.md)", "plain prose", "`b.md`", ""])
        assert [[ref.dest for ref in refs] for refs in batch] == [["a.md"], [], ["b.md"], []]

    def test_the_generation_names_the_extractor(self) -> None:
        assert link_generation() == "md:1"
        assert LINK_EDGE_TYPE == "links"


# ---------------------------------------------------------------------------
# Resolution candidates
# ---------------------------------------------------------------------------


class TestLinkCandidates:
    def test_relative_destinations_try_the_document_directory_then_the_root(self) -> None:
        doc = Path("/context/research/memo.md")
        assert link_candidates(doc, "../specs/138/spec.md") == ("/context/specs/138/spec.md", "/specs/138/spec.md")
        assert link_candidates(doc, "base.py") == ("/context/research/base.py", "/base.py")
        assert link_candidates(doc, "src/vfs/base.py") == ("/context/research/src/vfs/base.py", "/src/vfs/base.py")

    def test_a_root_anchored_destination_has_one_candidate(self) -> None:
        assert link_candidates(Path("/a/b.md"), "/x/y.md") == ("/x/y.md",)

    def test_a_trailing_slash_names_the_same_entry(self) -> None:
        assert link_candidates(Path("/a/b.md"), "docs/") == ("/a/docs", "/docs")

    def test_escapes_clamp_at_the_root_and_reserved_targets_drop(self) -> None:
        assert link_candidates(Path("/a.md"), "../../x.md") == ("/x.md",)
        assert link_candidates(Path("/a.md"), "..") == ()
        assert link_candidates(Path("/a.md"), "/") == ()
        assert link_candidates(Path("/a.md"), ".vfs/trash/x.md") == ()

    def test_a_structurally_invalid_destination_yields_nothing(self) -> None:
        assert link_candidates(Path("/a.md"), "bad\x00name.md") == ()

    def test_a_destination_at_the_root_document_yields_one_candidate(self) -> None:
        assert link_candidates(Path("/README.md"), "docs/x.md") == ("/docs/x.md",)


# ---------------------------------------------------------------------------
# Parity with the oracle
# ---------------------------------------------------------------------------


def _line_bound(body: str) -> bool:
    """Whether every code span closes on its own line — the oracle's reach."""
    return all(line.count("`") % 2 == 0 for line in body.splitlines() if not line.lstrip().startswith("```"))


class TestKernelParity:
    def test_the_kernel_matches_the_oracle_on_the_golden_corpus(self) -> None:
        docs = sorted((VFS_NATIVE / "corpus").rglob("*.md"))
        bodies = [doc.read_text(encoding="utf-8") for doc in docs]
        kept = [body for body in bodies if _line_bound(body)]
        assert len(kept) >= 100
        engine = native.markdown_refs([body.encode() for body in kept])
        for body, rows in zip(kept, engine, strict=True):
            assert rows == [tuple(ref) for ref in oracle_refs(body)]

    @pytest.mark.parametrize(
        "body",
        [
            "| a | b |\n|---|---|\n| [t](h.md) | `i.md` |\n\n- item [j](k.md)\n> quote [l](m.md)\n",
            "[`code/in/text.md`](target.md) and [plain](other.md)\n",
            "See [balanced](https://x.y/a_(b)) and [x](y.md)\n",
            "`.hidden.json` and `.md` and ` spaced.md ` and `` tick ``\n",
        ],
    )
    def test_the_kernel_matches_the_oracle_on_the_shapes(self, body: str) -> None:
        [rows] = native.markdown_refs([body.encode()])
        assert rows == [tuple(ref) for ref in oracle_refs(body)]
