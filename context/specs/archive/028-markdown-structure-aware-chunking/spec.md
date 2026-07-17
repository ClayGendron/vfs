# 028 — Markdown Structure-Aware Chunking

> **Superseded by [029](../029-code-structure-aware-chunking/spec.md).**
> This story proposed a dedicated markdown chunker built on `markdown-it-py`
> (heading-boundary cuts). 029 instead chunks *every* file type — markdown
> included — with one generic tree-sitter byte-span walker: the pack's
> `markdown` grammar nests heading sections, so heading-aware, fence-safe
> markdown chunks fall out of the same engine with no markdown-specific code and
> no second parser. `markdown-it-py` is dropped. 028's intent and acceptance
> criteria (esp. code-fence integrity) are preserved in 029; keep this file for
> historical context only — do not implement it.

- **Status:** superseded
- **Date:** 2026-05-22
- **Owner:** Clay Gendron
- **Kind:** feature
- **Depends on:** 014 (auto-chunk write phase, `VFSEntry.chunk()` /
  `split_content` contract)

## Intent

Give markdown files a structure-aware default chunker. Today every file
type — prose, code, markdown — runs through one splitter
(`split_with_line_ranges`): a recursive separator walk over
`("\n\n", "\n", " ", "")` at a 2 KB budget. For markdown that produces a
real defect: the splitter cuts wherever the budget lands, including
*inside fenced code blocks*, because a `#` comment line inside a Python
fence is indistinguishable from an `# ATX heading` to a string matcher.

This story adds a markdown-specific splitter that:

1. Finds true heading boundaries via a markdown AST (so `#` inside a code
   fence is never mistaken for a heading).
2. Cuts hard at headings, packing adjacent sections up to the chunk-size
   budget.
3. Falls back to the existing recursive splitter *within* a section that
   is larger than the budget.

It is wired as the default for markdown files (`.md`, `.mdx`,
`.markdown`); all other file types keep their current behavior unchanged.

## Why

Three observations, from benchmarking the current splitter against the
157 markdown files in this repo (2.13 MB):

- **Pure separator splitting mis-cuts 7.5% of chunks** — they start
  inside a fenced code block. Concentrated in code-heavy docs: 13% of
  chunks in `everything_is_a_file.md`, 50% in
  `grover_implementation_plan.md`. A chunk that begins `    pass` with no
  preceding `\`\`\`python` is a poor retrieval target and an ugly
  citation.
- **Headings are the natural retrieval unit for prose.** Cutting at
  heading boundaries keeps a section's claim intact in one chunk instead
  of straddling two. This is the convergent practice across LangChain,
  LlamaIndex, Unstructured, and Azure AI Search.
- **The splitter is already pluggable but blind to type.**
  `VFSEntry.split_content` is the documented override hook, but it is a
  `@staticmethod` taking only `content` — it cannot see the file
  extension, so it cannot dispatch per type. Markdown is the first
  concrete per-type strategy; the dispatch seam this story adds is the
  template for code splitters (tree-sitter) later.

## Decisions (settled before implementation)

These were decided in design discussion and are not open for the
implementation to relitigate:

- **Markdown only.** No HTML, Python, JS/TS, Rust in this story. Those
  are follow-on per-type strategies that reuse the same dispatch seam.
- **No overlap.** Structural chunking replaces overlap; the recursive
  fallback inside oversized sections also runs at `overlap=0`. Overlap
  delivers marginal-to-no retrieval gains in published evaluations and
  costs storage + redundant index entries.
- **`markdown-it-py` is a core dependency**, not an optional extra.
  Markdown is the primary doc format; the parser is ~50 KB pure Python
  (plus `mdurl`), no native code. Graceful-degradation-if-absent is
  explicitly *not* wanted — the behavior must be deterministic regardless
  of which extras are installed.
- **`heading_path` metadata is deferred.** Persisting each chunk's
  heading breadcrumb (e.g. `["Architecture", "Mounts"]`) requires a new
  `VFSEntry` column and a change to the `(text, line_start, line_end)`
  split contract. That is a separate story. This story keeps the existing
  3-tuple contract; the AST walk computes heading boundaries but discards
  the heading text.
- **Char-based budget, default 2048**, matching the current splitter. No
  tokenizer in the cut path (benchmarking showed token counting is ~30×
  slower and produces worse boundaries for no retrieval win at our sizes).

## Scope

### In

1. **`split_markdown(content, *, chunk_size=2048, separators=...)` in
   `vfs.chunking`.** Returns `list[tuple[str, int, int]]` —
   `(chunk_text, line_start, line_end)`, 1-indexed lines — identical in
   shape to `split_with_line_ranges`. Returns `[]` when the whole content
   fits in one chunk (the "no split needed" signal the `chunk()` contract
   already relies on).

   Algorithm:
   - Parse `content` with a module-level `MarkdownIt("commonmark")`.
   - Collect the start line of every `heading_open` token. These are the
     only structural cut points.
   - Build sections: the text between consecutive heading starts (the
     pre-first-heading preamble is its own section). Blank/whitespace-only
     sections are dropped.
   - Pack sections sequentially: accumulate into the current chunk while
     `len(current) + len(next) + 1 <= chunk_size`; otherwise emit the
     current chunk and start a new one.
   - A section larger than `chunk_size` on its own is filled with
     `split_with_line_ranges(section, chunk_size=chunk_size, overlap=0)`,
     with the returned relative line numbers offset to absolute.

2. **Extension dispatch in `VFSEntry.chunk()`.** For files whose `ext` is
   in `{"md", "mdx", "markdown"}` (note: `extract_extension` returns the
   ext *without* a leading dot), `chunk()` routes to `split_markdown`.
   All other files continue to use the `split_content` hook.

3. **`markdown-it-py` added to core `dependencies` in `pyproject.toml`.**

4. **Tests** covering: heading-boundary cuts, code-fence integrity (no
   chunk starts inside a fence), section packing (small adjacent sections
   merge; chunk count stays near the separator splitter, not the
   one-chunk-per-heading explosion), oversized-section fallback, the
   `[]` no-split case, line-range accuracy, and the dispatch (a `.md`
   file uses `split_markdown`; a `.py` file does not).

### Out

- `heading_path` persistence (separate story).
- Any non-markdown per-type splitter (HTML, code).
- Token-based sizing.
- Overlap.
- Changes to the `split_content` staticmethod signature or its override
  semantics for non-markdown types.
- Re-chunking / migration of already-chunked markdown in existing
  databases. This changes *future* chunk output only.

## Behavior contract

- **`split_content` is unchanged.** It remains a `@staticmethod(content)`
  returning the recursive-split result, and remains the override hook for
  non-markdown types. Existing subclass overrides and the
  `staticmethod(chunker)` test-patch pattern keep working untouched.
- **Markdown dispatch is in `chunk()`, not `split_content`.** Rationale:
  `split_content` cannot see the extension. `chunk()` has `self.ext`.
  Markdown files therefore use the dedicated `split_markdown` strategy;
  `split_content` is the fallback splitter for types without a dedicated
  strategy. This is the seam future per-type strategies plug into.
- **Empty / heading-light content.** A markdown file under the budget
  returns `[]` (no chunking, file keeps `index_content=True`), exactly
  as today.
- **Determinism.** Output depends only on `content` and `chunk_size`,
  never on installed extras (the parser is always present).

## Acceptance criteria

1. A markdown file containing a fenced code block with `#`-comment lines,
   sized so the block spans a chunk boundary, produces **zero** chunks
   whose first line falls inside the fence. (The current splitter fails
   this.)
2. `split_markdown` returns `[]` for content `<= chunk_size`.
3. For a multi-section markdown document larger than the budget, chunk
   count is within ~10% of the pure-separator splitter (i.e. small
   sections are packed, not emitted one-per-heading).
4. Every returned tuple has `1 <= line_start <= line_end`, and
   `line_end` does not exceed the document's line count.
5. A section larger than `chunk_size` is split into multiple chunks whose
   line ranges are contiguous and absolute (offset correctly from the
   section start).
6. `VFSEntry(path="/x.md", ...).chunk()` routes through `split_markdown`;
   `VFSEntry(path="/x.py", ...).chunk()` routes through `split_content`.
7. All pre-existing `split_content` / `chunk()` tests pass unchanged.
8. `markdown-it-py` resolves as a core dependency (importable without any
   extra installed).
9. Coverage stays at or above the 99% gate.

## Notes / measurements

- Benchmark (157 files, 2.13 MB): pure separator split 19 ms total
  (117 MB/s); AST-packed 510 ms total (4.4 MB/s). Per single largest file
  (148 KB): 1.5 ms vs 31 ms. The ~25× ratio is invisible at write time
  (one file per write); it matters only for bulk re-index, which is out
  of scope here.
- The visualizer used to validate this strategy lives at
  `scripts/chunk_viz.py` (exploratory tool, not shipped behavior).
