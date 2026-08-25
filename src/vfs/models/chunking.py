"""Chunking — split file content into indexable pieces.

Two splitters cover every file type:

- **Recursive character splitter** (LangChain-style): split content into
  chunks no larger than *chunk_size* by trying separators in priority order —
  paragraph, line, word, then a fixed-size fallback for runs with no
  separator. The separator is kept attached to the piece preceding it,
  adjacent pieces are greedily merged up to the budget, and any single piece
  still over budget recurses into the next separator. With no overlap, the
  concatenation of the emitted chunks reconstructs the input exactly.
- **Structure-aware splitter** (tree-sitter, in the native engine): the
  Rust core parses and walks every supported file type — code, markup,
  config, data, markdown — and returns chunk spans on real syntax-tree
  boundaries; this module slices the text, drops whitespace-only chunks,
  and re-splits oversized indivisible leaves with the recursive splitter.
  The grammar for a file is resolved from its extension by
  :func:`grammar_for_extension`; the recursive splitter remains the
  fallback for extensions with no grammar. ``split_notebook`` routes each
  Jupyter cell to the grammar its cell type and kernel imply.

Any content of at least ``GRAM_SIZE`` bytes (the smallest indexable unit)
yields at least one chunk — except on the structure path, where an
over-budget whitespace-only body yields none by design (every span is
strip-filtered); shorter content yields none. ``split_code`` and
``split_notebook`` route their fits-in-one-chunk and fallback cases through
``split_with_line_ranges`` so small files and cells chunk under the same rule.

Unit: ``chunk_size`` is measured in characters for ``recursive_text_split`` /
``split_with_line_ranges``; ``split_code`` measures UTF-8 bytes on the
structure path and delegates oversized leaves to the character splitter
(where a byte budget bounds a character budget for ASCII-dominant code,
which is the regime that matters).

Engine note: structure-aware splitting is a **native-engine capability by
contract**. A pure-Python install carries no tree-sitter at all, so every
extension takes the recursive character splitter there — a declared,
tested degradation, not an equivalent engine.
"""

from __future__ import annotations

import json
from bisect import bisect_left
from typing import Final

from vfs.models.code_grams import GRAM_SIZE, normalize_content
from vfs.native import active_core, chunk_spans

# Separator priority for the recursive character splitter.
DEFAULT_SEPARATORS: tuple[str, ...] = ("\n\n", "\n", " ", "")

# Extension (no leading dot) → grammar name. The markdown grammar is heading-
# hierarchical, so markdown rides the same walker as code.
EXTENSION_TO_GRAMMAR: dict[str, str] = {
    # docs / literate
    "md": "markdown",
    "mdx": "markdown",
    "markdown": "markdown",
    "rmd": "markdown",
    "qmd": "markdown",
    # python
    "py": "python",
    "pyi": "python",
    # systems / compiled
    "rs": "rust",
    "go": "go",
    "c": "c",
    "h": "c",
    "cc": "cpp",
    "cpp": "cpp",
    "cxx": "cpp",
    "hpp": "cpp",
    "hh": "cpp",
    "hxx": "cpp",
    "cu": "cuda",
    "zig": "zig",
    "d": "d",
    "nim": "nim",
    "v": "v",
    "odin": "odin",
    # jvm / .net
    "java": "java",
    "kt": "kotlin",
    "kts": "kotlin",
    "scala": "scala",
    "groovy": "groovy",
    "cs": "csharp",
    "fs": "fsharp",
    "vb": "vb",
    # web / scripting
    "js": "javascript",
    "mjs": "javascript",
    "cjs": "javascript",
    "jsx": "javascript",
    "ts": "typescript",
    "mts": "typescript",
    "cts": "typescript",
    "tsx": "tsx",
    "vue": "vue",
    "svelte": "svelte",
    "astro": "astro",
    "php": "php",
    "rb": "ruby",
    "lua": "lua",
    "pl": "perl",
    "pm": "perl",
    "r": "r",
    "jl": "julia",
    "dart": "dart",
    "ex": "elixir",
    "exs": "elixir",
    "erl": "erlang",
    "clj": "clojure",
    "cljs": "clojure",
    "hs": "haskell",
    "ml": "ocaml",
    "swift": "swift",
    "elm": "elm",
    "gleam": "gleam",
    "sol": "solidity",
    "tcl": "tcl",
    # shell
    "sh": "bash",
    "bash": "bash",
    "zsh": "bash",
    "fish": "fish",
    "ps1": "powershell",
    "psm1": "powershell",
    # markup / config / data
    "html": "html",
    "htm": "html",
    "xml": "xml",
    "css": "css",
    "scss": "scss",
    "less": "less",
    "json": "json",
    "json5": "json5",
    "yaml": "yaml",
    "yml": "yaml",
    "toml": "toml",
    "ini": "ini",
    "rst": "rst",
    "tex": "latex",
    "sql": "sql",
    "graphql": "graphql",
    "gql": "graphql",
    "proto": "proto",
    "tf": "terraform",
    "hcl": "hcl",
    "cmake": "cmake",
    "mk": "make",
    "nix": "nix",
    "vim": "vim",
    "csv": "csv",
    "tsv": "tsv",
}

# Mapped grammar names with no usable crate in the native registry; their
# extensions take the character splitter, exactly like unmapped extensions.
# Pinned against the live registry by the coverage-contract test.
STRUCTURE_FALLBACK_GRAMMARS: Final = frozenset({"astro", "clojure", "csv", "json5", "latex", "tcl", "tsv", "vb", "vue"})

# Bumped deliberately when a grammar crate or walker change alters chunk
# shapes; the chunk fixtures regenerate in the same landing.
CHUNK_GENERATION: Final = 1

NOTEBOOK_EXTENSION = "ipynb"


def chunk_generation() -> str:
    """The engine + grammar generation stamped onto stored chunk state.

    Stored chunks derived under any other value are stale by law: an
    engine switch (pure ↔ native) or a declared generation bump re-dirties
    them, so shapes from different splitters never silently coexist.
    """
    return f"{active_core()}:{CHUNK_GENERATION}"


# ---------------------------------------------------------------------------
# Grammar resolution
# ---------------------------------------------------------------------------


def grammar_for_extension(ext: str | None) -> str | None:
    """Resolve a tree-sitter grammar name from a file extension (no leading dot).

    Returns ``None`` for the notebook extension (handled by
    :func:`split_notebook`) and for any extension with no mapped grammar.
    """
    if not ext or ext == NOTEBOOK_EXTENSION:
        return None
    return EXTENSION_TO_GRAMMAR.get(ext)


# ---------------------------------------------------------------------------
# Recursive character splitting
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Structure-aware splitting
# ---------------------------------------------------------------------------


def split_code(
    content: str,
    *,
    language: str,
    chunk_size: int = 2048,
) -> list[tuple[str, int, int]]:
    """Structure-aware split of *content* using its tree-sitter *language*.

    Returns ``(chunk_text, line_start, line_end)`` tuples (1-indexed lines).
    Content that fits one chunk yields a single whole-content piece;
    sub-trigram content yields ``[]``. Boundaries fall on syntax-tree node
    edges, computed by the native engine. A merged span that is itself an
    oversized indivisible leaf falls back to the recursive separator
    splitter per span; when the engine cannot serve the split at all —
    unknown grammar, language load failure, a body over 4 GiB, or the
    pure engine, where the structure path is absent by contract — the
    recursive splitter takes the whole file. *chunk_size* is measured
    in UTF-8 bytes on the structure path.
    """
    return split_code_batch([(content, language)], chunk_size=chunk_size)[0]


def split_code_batch(
    items: list[tuple[str, str]],
    *,
    chunk_size: int = 2048,
) -> list[list[tuple[str, int, int]]]:
    """:func:`split_code` for many ``(content, language)`` pairs at once.

    Every over-budget body crosses the engine seam in **one** call, so the
    native engine parses the whole batch in parallel; results are
    index-aligned with the input. Fits-in-one-chunk bodies and bodies the
    engine declines take the character splitter, per the single-item
    contract.
    """
    datas = [content.encode("utf-8") for content, _language in items]
    need = [i for i, data in enumerate(datas) if len(data) > chunk_size]
    rows_by_index: dict[int, list[tuple[int, int, int, int, bool]] | None] = {}
    if need:
        spans = chunk_spans([(datas[i], items[i][1]) for i in need], chunk_size=chunk_size)
        rows_by_index = dict(zip(need, spans, strict=True))

    out: list[list[tuple[str, int, int]]] = []
    for index, (content, _language) in enumerate(items):
        rows = rows_by_index.get(index)
        if rows is None:
            out.append(split_with_line_ranges(content, chunk_size=chunk_size))
        else:
            out.append(_assemble_spans(datas[index], rows, chunk_size))
    return out


# Notebook kernel display language → grammar, when it differs from the grammar
# name. Unmapped kernels are used as-is and fall back if no such grammar exists.
_KERNEL_TO_GRAMMAR: dict[str, str] = {
    "python3": "python",
    "ipython": "python",
    "c++": "cpp",
    "c#": "csharp",
}


def split_notebook(
    content: str,
    *,
    chunk_size: int = 2048,
) -> list[tuple[str, int, int]]:
    """Chunk a Jupyter notebook by cell *source* (outputs/metadata discarded).

    Markdown cells use the ``markdown`` grammar, code cells the notebook's kernel
    language (default ``python``). Line ranges are absolute over the concatenated
    cell sources. A body without a well-formed cell list falls back to the
    recursive splitter; malformed cell or kernelspec fields degrade in place
    (empty source, default grammar) — no shape the JSON parse admits raises.
    """
    try:
        notebook = json.loads(content)
        cells = notebook["cells"]
        if not isinstance(cells, list):
            raise TypeError
    except (ValueError, KeyError, TypeError):
        return split_with_line_ranges(content, chunk_size=chunk_size)

    # The kernel fields are advisory grammar selection: junk shapes take
    # the default, they never crash the split or void well-formed cells.
    metadata = notebook.get("metadata")
    kernelspec = metadata.get("kernelspec") if isinstance(metadata, dict) else None
    language = kernelspec.get("language") if isinstance(kernelspec, dict) else None
    kernel = language.lower() if isinstance(language, str) and language else "python"
    code_grammar = _KERNEL_TO_GRAMMAR.get(kernel, kernel)

    out: list[tuple[str, int, int]] = []
    line_base = 0
    for cell in cells:
        if not isinstance(cell, dict):
            continue
        # nbformat sources are str or list of str; anything else is a malformed
        # cell and degrades to "" rather than crashing the split.
        source = cell.get("source", "")
        if isinstance(source, list):
            source = "".join(s for s in source if isinstance(s, str))
        elif not isinstance(source, str):
            source = ""
        cell_type = cell.get("cell_type")
        if cell_type == "markdown":
            grammar = "markdown"
        elif cell_type == "code":
            grammar = code_grammar
        else:
            grammar = None

        if grammar is not None and source.strip():
            pieces = split_code(source, language=grammar, chunk_size=chunk_size)
            out.extend((text, line_base + ls, line_base + le) for text, ls, le in pieces)
        line_base += source.count("\n") + 1
    return out


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _assemble_spans(
    data: bytes,
    rows: list[tuple[int, int, int, int, bool]],
    chunk_size: int,
) -> list[tuple[str, int, int]]:
    """Assemble engine span rows into chunks: slice, strip-filter, re-split.

    Whitespace-only spans are dropped; an oversized indivisible leaf is
    character-split in place with its line numbers rebased.
    """
    out: list[tuple[str, int, int]] = []
    for start, end, line_start, line_end, oversized in rows:
        text = data[start:end].decode("utf-8", "replace")
        if not text.strip():
            continue
        if oversized:
            base = line_start - 1
            for piece, rel_start, rel_end in split_with_line_ranges(text, chunk_size=chunk_size):
                out.append((piece, base + rel_start, base + rel_end))
        else:
            out.append((text, line_start, line_end))
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
    # When none does, go straight to the fixed-size fallback rather than
    # re-trying separators that already failed.
    sep, rest = "", ("",)
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


__all__ = [
    "CHUNK_GENERATION",
    "DEFAULT_SEPARATORS",
    "EXTENSION_TO_GRAMMAR",
    "NOTEBOOK_EXTENSION",
    "STRUCTURE_FALLBACK_GRAMMARS",
    "chunk_generation",
    "grammar_for_extension",
    "recursive_text_split",
    "split_code",
    "split_code_batch",
    "split_notebook",
    "split_with_line_ranges",
]
