"""Recursive text splitter — region-aware rfind walker.

LangChain-compatible split: try each separator in priority order; oversized
pieces recurse into the next separator. Boundaries match the OLD ``str.split``
baseline for typical text/code at the bench config (2048/256). Pathological
char-fallback inputs (long runs without any separator) chunk with sliding
overlap rather than OLD's interleaved overlap-tail emissions.
"""
from __future__ import annotations

import json
import typing
from bisect import bisect_left, bisect_right

from tree_sitter_language_pack import SupportedLanguage, get_parser

DEFAULT_SEPARATORS: tuple[str, ...] = ("\n\n", "\n", " ", "")


def recursive_text_split(
    content: str,
    *,
    chunk_size: int = 2048,
    overlap: int = 256,
    separators: tuple[str, ...] = DEFAULT_SEPARATORS,
) -> list[str]:
    """Split *content* into pieces no larger than *chunk_size* characters."""
    offsets = _chunk_offsets(content, chunk_size=chunk_size, overlap=overlap, separators=separators)
    return [content[s:e] for s, e in offsets]


def split_with_line_ranges(
    content: str,
    *,
    chunk_size: int = 2048,
    overlap: int = 256,
    separators: tuple[str, ...] = DEFAULT_SEPARATORS,
) -> list[tuple[str, int, int]]:
    """Return ``(chunk_text, line_start, line_end)`` for each emitted chunk.

    Lines are 1-indexed; ``line_end`` is the line containing the chunk's last
    character. A chunk that lives entirely inside a single oversized line has
    ``line_start == line_end``.
    """
    offsets = _chunk_offsets(content, chunk_size=chunk_size, overlap=overlap, separators=separators)
    if not offsets:
        return []
    newlines: list[int] = []
    nl_append = newlines.append
    for i, c in enumerate(content):
        if c == "\n":
            nl_append(i)
    bisect = bisect_left
    out: list[tuple[str, int, int]] = []
    for s, e in offsets:
        line_start = bisect(newlines, s) + 1
        line_end = bisect(newlines, e - 1) + 1 if e > s else line_start
        out.append((content[s:e], line_start, line_end))
    return out


def _chunk_offsets(
    content: str,
    *,
    chunk_size: int,
    overlap: int,
    separators: tuple[str, ...],
) -> list[tuple[int, int]]:
    """Return the ``(start, end)`` offset pairs the splitter would emit.

    ``recursive_text_split`` slices ``content`` once per pair; callers that
    need positional metadata (line numbers, byte offsets) consume the pairs
    directly to avoid re-locating chunks.
    """
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be positive, got {chunk_size}")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError(f"overlap must be in [0, chunk_size); got {overlap}")
    if not separators:
        raise ValueError("separators must not be empty")
    n = len(content)
    if n <= chunk_size:
        return []

    # Drop seps not present in content; avoids per-chunk rfind for absent seps.
    seps_non_empty: list[str] = [s for s in separators if s != "" and s in content]

    # Per separator level, the active regions are oversized pieces of the prior
    # level. Sep 0 is active everywhere; sep i (i>0) is active only inside an
    # oversized sep-(i-1) piece. Bisect on starts gives O(log) "is active here".
    region_starts: list[tuple[int, ...]] = [()]
    region_ends: list[tuple[int, ...]] = [()]
    prev_regions: list[tuple[int, int]] = [(0, n)]
    for sep in seps_non_empty[:-1]:
        new_regions: list[tuple[int, int]] = []
        for s, e in prev_regions:
            new_regions.extend(_find_oversized(content, s, e, sep, chunk_size))
        if new_regions:
            starts, ends = zip(*new_regions, strict=True)
            region_starts.append(starts)
            region_ends.append(ends)
        else:
            region_starts.append(())
            region_ends.append(())
        prev_regions = new_regions

    # Drop trailing seps with no active region — they can never produce a cut.
    while len(seps_non_empty) > 1 and not region_starts[-1]:
        seps_non_empty.pop()
        region_starts.pop()
        region_ends.pop()

    n_seps = len(seps_non_empty)
    sep_lens = [len(s) for s in seps_non_empty]

    offsets: list[tuple[int, int]] = []
    offsets_append = offsets.append
    if n_seps == 0:
        base = 0
        step = chunk_size - overlap
        while True:
            target = base + chunk_size
            if target >= n:
                offsets_append((base, n))
                break
            offsets_append((base, target))
            base += step
        return offsets

    if n_seps == 1:
        sep = seps_non_empty[0]
        sep_len = sep_lens[0]
        repeat_char = sep[0] if sep_len > 1 and sep[0] == sep[1] else ""
        base = 0
        last_cut = -1
        rfind = str.rfind
        if not repeat_char:
            while True:
                target = base + chunk_size
                if target >= n:
                    offsets_append((base, n))
                    break
                lo = last_cut + 1 if last_cut >= base else base + 1
                cut = rfind(content, sep, lo, target + sep_len)
                if cut == -1:
                    cut = target
                offsets_append((base, cut))
                last_cut = cut
                base = cut - overlap if overlap > 0 and cut > overlap else cut
            return offsets

        while True:
            target = base + chunk_size
            if target >= n:
                offsets_append((base, n))
                break
            lo = last_cut + 1 if last_cut >= base else base + 1
            cut = rfind(content, sep, lo, target + sep_len)
            if cut != -1 and repeat_char:
                run_start = cut
                while run_start > 0 and content[run_start - 1] == repeat_char:
                    run_start -= 1
                cut = run_start + (cut - run_start) // sep_len * sep_len
                if cut < lo:
                    cut = -1
            if cut == -1:
                cut = target
            offsets_append((base, cut))
            last_cut = cut
            base = cut - overlap if overlap > 0 and cut > overlap else cut
        return offsets

    base = 0
    last_cut = -1
    rfind = str.rfind
    bisect = bisect_right
    repeat_chars = [s[0] if len(s) > 1 and s[0] == s[1] else "" for s in seps_non_empty]
    while True:
        target = base + chunk_size
        if target >= n:
            offsets_append((base, n))
            break
        lo = last_cut + 1 if last_cut >= base else base + 1
        cut = -1
        for sep_idx in range(n_seps):
            sep = seps_non_empty[sep_idx]
            sep_len = sep_lens[sep_idx]
            p = rfind(content, sep, lo, target + sep_len)
            if p == -1 or p <= cut:
                continue
            repeat_char = repeat_chars[sep_idx]
            if repeat_char:
                # rfind gives rightmost match; greedy str.split skips ahead by
                # sep_len after each hit, so adjust to the earliest aligned start
                # within the current run of identical chars.
                run_start = p
                while run_start > 0 and content[run_start - 1] == repeat_char:
                    run_start -= 1
                p = run_start + (p - run_start) // sep_len * sep_len
                if p < lo or p <= cut:
                    continue
            if sep_idx == 0:
                cut = p
                continue
            starts = region_starts[sep_idx]
            if not starts:
                continue
            j = bisect(starts, p) - 1
            if j >= 0 and p < region_ends[sep_idx][j]:
                cut = p
        if cut == -1:
            cut = target
        offsets_append((base, cut))
        last_cut = cut
        base = cut - overlap if overlap > 0 and cut > overlap else cut
    return offsets


def _find_oversized(
    content: str, start: int, end: int, sep: str, chunk_size: int
) -> list[tuple[int, int]]:
    """Return ranges of *sep*-bounded pieces in [start, end] exceeding chunk_size."""
    sep_len = len(sep)
    out: list[tuple[int, int]] = []
    if sep_len == 1:
        _find_oversized_single_char(content, start, end, sep, chunk_size, out)
        return out

    # Match the old split-based semantics without materializing ``content[start:end]``
    # or the full list of separator-bounded pieces.
    piece_start = start
    search_from = start
    find = str.find

    while True:
        sep_start = find(content, sep, search_from, end)
        if sep_start == -1:
            break

        piece_end = sep_start
        plen = piece_end - piece_start
        if plen > chunk_size:
            out.append((piece_start, piece_end))

        piece_start = sep_start
        search_from = sep_start + sep_len

    plen = end - piece_start
    if plen > chunk_size:
        out.append((piece_start, end))
    return out


def _find_oversized_single_char(
    content: str,
    start: int,
    end: int,
    sep: str,
    chunk_size: int,
    out: list[tuple[int, int]],
) -> None:
    """Single-character variant that skips separator hits inside small pieces."""
    piece_start = start
    search_from = start
    find = str.find
    rfind = str.rfind

    while search_from < end:
        last_safe = rfind(content, sep, search_from, min(end, piece_start + chunk_size + 1))
        if last_safe != -1:
            piece_start = last_safe
            search_from = last_safe + 1
            continue

        sep_start = find(content, sep, search_from, end)
        if sep_start == -1:
            break
        out.append((piece_start, sep_start))
        piece_start = sep_start
        search_from = sep_start + 1

    if end - piece_start > chunk_size:
        out.append((piece_start, end))


# ===========================================================================
# Structure-aware chunking (tree-sitter)
# ===========================================================================
#
# One language-agnostic walker chunks every supported file type — code, markup,
# config, data, markdown, Python — on real syntax-tree boundaries. The grammar
# for a file is resolved from its extension by :func:`grammar_for_extension`;
# the recursive separator splitter above remains the fallback for extensions
# with no grammar.
#
# Implementation note — the binding: ``tree-sitter-language-pack`` ships a
# Rust-native binding, *not* the ``tree_sitter`` PyO3 binding. ``parse`` takes a
# ``str`` (not ``bytes``); ``tree.root_node`` and every Node accessor
# (``kind``, ``named_child_count``, ``start_byte``, ``end_byte``) are *methods*;
# there is no ``named_children`` list; and byte offsets index the UTF-8 encoding
# of the source. ``_call`` tolerates either method-or-property so a future pack
# version that switches back does not break us.

# Extension (no leading dot) → grammar name. The markdown grammar is heading-
# hierarchical, so markdown rides the same walker as code.
EXTENSION_TO_GRAMMAR: dict[str, str] = {
    # docs / literate
    "md": "markdown", "mdx": "markdown", "markdown": "markdown",
    "rmd": "markdown", "qmd": "markdown",
    # python
    "py": "python", "pyi": "python",
    # systems / compiled
    "rs": "rust", "go": "go", "c": "c", "h": "c", "cc": "cpp", "cpp": "cpp",
    "cxx": "cpp", "hpp": "cpp", "hh": "cpp", "hxx": "cpp", "cu": "cuda",
    "zig": "zig", "d": "d", "nim": "nim", "v": "v", "odin": "odin",
    # jvm / .net
    "java": "java", "kt": "kotlin", "kts": "kotlin", "scala": "scala",
    "groovy": "groovy", "cs": "csharp", "fs": "fsharp", "vb": "vb",
    # web / scripting
    "js": "javascript", "mjs": "javascript", "cjs": "javascript",
    "jsx": "javascript", "ts": "typescript", "mts": "typescript",
    "cts": "typescript", "tsx": "tsx", "vue": "vue", "svelte": "svelte",
    "astro": "astro", "php": "php", "rb": "ruby", "lua": "lua",
    "pl": "perl", "pm": "perl", "r": "r", "jl": "julia", "dart": "dart",
    "ex": "elixir", "exs": "elixir", "erl": "erlang", "clj": "clojure",
    "cljs": "clojure", "hs": "haskell", "ml": "ocaml", "swift": "swift",
    "elm": "elm", "gleam": "gleam", "sol": "solidity", "tcl": "tcl",
    # shell
    "sh": "bash", "bash": "bash", "zsh": "bash", "fish": "fish",
    "ps1": "powershell", "psm1": "powershell",
    # markup / config / data
    "html": "html", "htm": "html", "xml": "xml", "css": "css",
    "scss": "scss", "less": "less", "json": "json", "json5": "json5",
    "yaml": "yaml", "yml": "yaml", "toml": "toml", "ini": "ini",
    "rst": "rst", "tex": "latex", "sql": "sql", "graphql": "graphql",
    "gql": "graphql", "proto": "proto", "tf": "terraform",
    "hcl": "hcl", "cmake": "cmake", "mk": "make", "nix": "nix", "vim": "vim",
    "csv": "csv", "tsv": "tsv",
}

# Notebook kernel display language → grammar, when it differs from the grammar
# name. Unmapped kernels are used as-is and fall back if no such grammar exists.
_KERNEL_TO_GRAMMAR: dict[str, str] = {
    "python3": "python", "ipython": "python", "c++": "cpp", "c#": "csharp",
}


_AVAILABLE_GRAMMARS = frozenset(typing.get_args(SupportedLanguage))

# Keep only entries whose grammar exists in the installed pack.
EXTENSION_TO_GRAMMAR = {k: v for k, v in EXTENSION_TO_GRAMMAR.items() if v in _AVAILABLE_GRAMMARS}

NOTEBOOK_EXTENSION = "ipynb"

_PARSERS: dict[str, object] = {}


def _call(attr):  # noqa: ANN001 - duck-typed Node accessor
    """Resolve a tree-sitter-language-pack Node accessor (method-or-property)."""
    return attr() if callable(attr) else attr


def _parser(grammar: str):  # noqa: ANN202 - opaque pack Parser
    parser = _PARSERS.get(grammar)
    if parser is None:
        parser = get_parser(grammar)  # type: ignore[arg-type]
        _PARSERS[grammar] = parser
    return parser


def grammar_for_extension(ext: str | None) -> str | None:
    """Resolve a tree-sitter grammar name from a file extension (no leading dot).

    Returns ``None`` for the notebook extension (handled by
    :func:`split_notebook`) and for any extension with no mapped grammar.
    """
    if not ext or ext == NOTEBOOK_EXTENSION:
        return None
    return EXTENSION_TO_GRAMMAR.get(ext)


def _atomic_spans(content: str, grammar: str, chunk_size: int) -> list[tuple[int, int]]:
    """Contiguous, file-covering UTF-8 byte spans, each as coarse as fits budget.

    Iterative in-order descent (no recursion limit): a node is emitted whole if
    it fits the budget or has no named children; otherwise its named children
    are walked, with interstitial gaps (punctuation, comments) emitted as their
    own spans.
    """
    root = _call(_parser(grammar).parse(content).root_node)
    spans: list[tuple[int, int]] = []
    stack: list[tuple[bool, object]] = [(False, root)]
    while stack:
        is_span, payload = stack.pop()
        if is_span:
            spans.append(payload)  # type: ignore[arg-type]
            continue
        node = payload
        start, end = _call(node.start_byte), _call(node.end_byte)
        count = _call(node.named_child_count)
        if end - start <= chunk_size or count == 0:
            spans.append((start, end))
            continue
        items: list[tuple[bool, object]] = []
        cursor = start
        for i in range(count):
            child = node.named_child(i)
            child_start = _call(child.start_byte)
            if child_start > cursor:
                items.append((True, (cursor, child_start)))
            items.append((False, child))
            cursor = _call(child.end_byte)
        if cursor < end:
            items.append((True, (cursor, end)))
        stack.extend(reversed(items))
    return spans


def _merge_spans(spans: list[tuple[int, int]], chunk_size: int) -> list[tuple[int, int]]:
    """Greedily merge contiguous spans while the merged byte length fits budget."""
    out: list[tuple[int, int]] = []
    cur_start: int | None = None
    cur_end = 0
    for start, end in spans:
        if cur_start is None:
            cur_start, cur_end = start, end
        elif end - cur_start <= chunk_size:
            cur_end = end
        else:
            out.append((cur_start, cur_end))
            cur_start, cur_end = start, end
    if cur_start is not None:
        out.append((cur_start, cur_end))
    return out


def split_code(
    content: str,
    *,
    language: str,
    chunk_size: int = 2048,
) -> list[tuple[str, int, int]]:
    """Structure-aware split of *content* using its tree-sitter *grammar*.

    Returns ``(chunk_text, line_start, line_end)`` tuples (1-indexed lines), or
    ``[]`` when the whole content fits one chunk. Boundaries fall on syntax-tree
    node edges. A merged span that is itself an oversized indivisible leaf falls
    back to the recursive separator splitter; an unparseable file (or any
    binding error) falls back wholesale. *chunk_size* is measured in UTF-8 bytes.
    """
    data = content.encode("utf-8")
    if len(data) <= chunk_size:
        return []
    try:
        spans = _atomic_spans(content, language, chunk_size)
    except Exception:
        return split_with_line_ranges(content, chunk_size=chunk_size, overlap=0)

    newlines = [i for i, byte in enumerate(data) if byte == 0x0A]
    out: list[tuple[str, int, int]] = []
    for start, end in _merge_spans(spans, chunk_size):
        text = data[start:end].decode("utf-8", "replace")
        if not text.strip():
            continue
        line_start = bisect_left(newlines, start) + 1
        if end - start > chunk_size:  # oversized indivisible leaf
            base = line_start - 1
            for piece, rel_start, _rel_end in split_with_line_ranges(
                text, chunk_size=chunk_size, overlap=0
            ):
                out.append((piece, base + rel_start, base + rel_start + piece.count("\n")))
        else:
            out.append((text, line_start, line_start + text.count("\n")))
    return out


def split_notebook(
    content: str,
    *,
    chunk_size: int = 2048,
) -> list[tuple[str, int, int]]:
    """Chunk a Jupyter notebook by cell *source* (outputs/metadata discarded).

    Markdown cells use the ``markdown`` grammar, code cells the notebook's kernel
    language (default ``python``). Line ranges are absolute over the concatenated
    cell sources. Malformed notebooks fall back to the recursive splitter.
    """
    try:
        notebook = json.loads(content)
        cells = notebook["cells"]
        if not isinstance(cells, list):
            raise TypeError
    except (ValueError, KeyError, TypeError):
        return split_with_line_ranges(content, chunk_size=chunk_size, overlap=0)

    metadata = notebook.get("metadata") or {}
    kernelspec = metadata.get("kernelspec") or {}
    kernel = (kernelspec.get("language") or "python").lower()
    code_grammar = _KERNEL_TO_GRAMMAR.get(kernel, kernel)

    out: list[tuple[str, int, int]] = []
    line_base = 0
    for cell in cells:
        if not isinstance(cell, dict):
            continue
        source = cell.get("source", "")
        if isinstance(source, list):
            source = "".join(source)
        cell_type = cell.get("cell_type")
        if cell_type == "markdown":
            grammar = "markdown"
        elif cell_type == "code":
            grammar = code_grammar
        else:
            grammar = None

        if grammar is not None and source.strip():
            pieces = split_code(source, language=grammar, chunk_size=chunk_size)
            if pieces:
                out.extend(
                    (text, line_base + ls, line_base + le) for text, ls, le in pieces
                )
            else:
                out.append((source, line_base + 1, line_base + 1 + source.count("\n")))
        line_base += source.count("\n") + 1
    return out


__all__ = [
    "DEFAULT_SEPARATORS",
    "EXTENSION_TO_GRAMMAR",
    "NOTEBOOK_EXTENSION",
    "grammar_for_extension",
    "recursive_text_split",
    "split_code",
    "split_notebook",
    "split_with_line_ranges",
]
