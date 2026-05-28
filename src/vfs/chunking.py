"""Recursive character text splitter (LangChain-style).

Split content into chunks no larger than *chunk_size* by trying separators in
priority order — paragraph, line, word, then a fixed-size fallback for runs
with no separator. The separator is kept attached to the piece preceding it,
adjacent pieces are greedily merged up to the budget, and any single piece
still over budget recurses into the next separator. With no overlap, the
concatenation of the emitted chunks reconstructs the input exactly.

Any content of at least ``GRAM_SIZE`` bytes (the smallest indexable unit)
yields at least one chunk; shorter content yields none. ``split_code`` and
``split_notebook`` route their fits-in-one-chunk and fallback cases through
``split_with_line_ranges`` so small files and cells chunk under the same rule.

Unit: ``chunk_size`` is measured in characters for ``recursive_text_split`` /
``split_with_line_ranges``; ``split_code`` measures UTF-8 bytes internally for
its tree-sitter span logic and delegates oversized leaves to the character
splitter (where a byte budget bounds a character budget for ASCII-dominant
code, which is the regime that matters).
"""
from __future__ import annotations

import json
import typing
from bisect import bisect_left

from tree_sitter_language_pack import SupportedLanguage, get_parser

from vfs.code_grams import GRAM_SIZE, normalize_content

DEFAULT_SEPARATORS: tuple[str, ...] = ("\n\n", "\n", " ", "")


def recursive_text_split(
    content: str,
    *,
    chunk_size: int = 2048,
    separators: tuple[str, ...] = DEFAULT_SEPARATORS,
) -> list[str]:
    """Split *content* into pieces no larger than *chunk_size* characters.

    Returns ``[]`` for sub-trigram content, otherwise a non-empty list whose
    concatenation equals *content*.
    """
    if len(normalize_content(content)) < GRAM_SIZE:
        return []
    return _recursive_split(content, chunk_size, separators)


def split_with_line_ranges(
    content: str,
    *,
    chunk_size: int = 2048,
    separators: tuple[str, ...] = DEFAULT_SEPARATORS,
) -> list[tuple[str, int, int]]:
    """Return ``(chunk_text, line_start, line_end)`` for each emitted chunk.

    Lines are 1-indexed; ``line_end`` is the line containing the chunk's last
    character. A chunk that lives entirely inside a single oversized line has
    ``line_start == line_end``. Returns ``[]`` only for sub-trigram content.
    """
    pieces = recursive_text_split(content, chunk_size=chunk_size, separators=separators)
    if not pieces:
        return []
    newlines: list[int] = [i for i, c in enumerate(content) if c == "\n"]
    out: list[tuple[str, int, int]] = []
    pos = 0
    for piece in pieces:
        start = pos
        end = pos + len(piece)
        line_start = bisect_left(newlines, start) + 1
        line_end = bisect_left(newlines, end - 1) + 1 if end > start else line_start
        out.append((piece, line_start, line_end))
        pos = end
    return out


def _recursive_split(content: str, chunk_size: int, separators: tuple[str, ...]) -> list[str]:
    """Recursive character splitter; returns pieces that concatenate to *content*.

    Splits on the highest-priority separator present in *content*, keeping the
    separator attached to the preceding piece, then greedily merges adjacent
    pieces up to *chunk_size*. Any merged piece still over budget recurses into
    the next separator; the empty-string separator is the fixed-size fallback.
    """
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be positive, got {chunk_size}")
    if not separators:
        raise ValueError("separators must not be empty")
    if not content:
        return []
    if len(content) <= chunk_size:
        return [content]

    # Pick the first separator that appears in the content; "" always matches.
    sep = separators[-1]
    rest = separators[1:]
    for i, candidate in enumerate(separators):
        if candidate == "" or candidate in content:
            sep = candidate
            rest = separators[i + 1 :] or ("",)
            break

    pieces = _split_keep_separator(content, sep, chunk_size)

    out: list[str] = []
    buf = ""
    for piece in pieces:
        if len(piece) > chunk_size:
            if buf:
                out.append(buf)
                buf = ""
            out.extend(_recursive_split(piece, chunk_size, rest))
        elif len(buf) + len(piece) <= chunk_size:
            buf += piece
        else:
            if buf:
                out.append(buf)
            buf = piece
    if buf:
        out.append(buf)
    return out


def _split_keep_separator(content: str, sep: str, chunk_size: int) -> list[str]:
    """Split *content* on *sep*, keeping each separator attached to its piece.

    The empty separator falls back to fixed-size slicing of *chunk_size*.
    """
    if sep == "":
        return [content[i : i + chunk_size] for i in range(0, len(content), chunk_size)]
    pieces: list[str] = []
    start = 0
    sep_len = len(sep)
    find = content.find
    while True:
        hit = find(sep, start)
        if hit == -1:
            break
        pieces.append(content[start : hit + sep_len])
        start = hit + sep_len
    if start < len(content):
        pieces.append(content[start:])
    return pieces


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

    Returns ``(chunk_text, line_start, line_end)`` tuples (1-indexed lines).
    Content that fits one chunk yields a single whole-content piece; sub-trigram
    content yields ``[]``. Boundaries fall on syntax-tree node edges. A merged
    span that is itself an oversized indivisible leaf falls back to the recursive
    separator splitter; an unparseable file (or any binding error) falls back
    wholesale. *chunk_size* is measured in UTF-8 bytes.
    """
    data = content.encode("utf-8")
    if len(data) <= chunk_size:
        # Fits one chunk — emit a whole-content piece (or [] for sub-trigram).
        return split_with_line_ranges(content, chunk_size=chunk_size)
    try:
        spans = _atomic_spans(content, language, chunk_size)
    except Exception:
        return split_with_line_ranges(content, chunk_size=chunk_size)

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
                text, chunk_size=chunk_size
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
        return split_with_line_ranges(content, chunk_size=chunk_size)

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
            out.extend(
                (text, line_base + ls, line_base + le) for text, ls, le in pieces
            )
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
