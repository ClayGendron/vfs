# 013 — Implementation notes

- **Status:** in-progress (Phase 1 + 1.5 + chunker complete; DB integration not started)
- **Date:** 2026-04-30
- **Spec:** [spec.md](./spec.md)
- **Plan:** [plan.md](./plan.md)

## Summary

Pure-Python primitives for the database-agnostic code-gram index are
landed: byte-trigram tokenizer with NFC + casefold normalization, a
soundness-first regex-to-`GramQuery` planner built on Python's `sre_parse`
AST, and a fast LangChain-compatible recursive text splitter for the
upcoming chunk write path. No DB writes, no schema, no `_grep_impl`
changes yet.

Two commits on `main`:

- `f840ce5` — code grams + tests + walkthrough notebook
- `f6d22f5` — text splitter + benchmarks

## What's done

### `src/vfs/code_grams.py` — tokenizer + regex AST query planner

Public surface:

- `iter_code_grams(content, *, folded=False)` / `unique_code_grams(...)` —
  sliding 3-byte UTF-8 trigrams over NFC-normalized content. Punctuation,
  whitespace, operators, path separators, and bytes inside multibyte
  code points all participate. CRLF/CR collapse to LF before encoding.
- `grams_for_fixed_string(pattern, *, folded=False)` — required grams for
  fixed-string grep.
- `pack_gram(b0, b1, b2)` / `unpack_gram(gram)` — 24-bit packing.
- `build_code_gram_query(pattern, *, fixed_strings=False, folded=False)` —
  returns `GramAny | GramAnd | GramOr`. Implementation walks
  `sre_parse.parse(pattern).data` rather than scanning the raw pattern,
  which is what gives the planner soundness for constructs the
  hand-rolled tokenizer mishandled in v1: `(?P<name>...)`, `(?i:...)`,
  `(?#...)`, `(?x)`, `\xNN`, `\NNN`, `(foo)?`, `(abc){0,3}`, scoped flag
  toggles under outer `(?i)`, lookarounds, atomic groups, and invalid
  patterns.

Soundness contract: false positives OK; false negatives forbidden. Every
code path that can't prove its emitted grams are required by every match
collapses to `GramAny`.

Unicode: both indexer and query planner apply
`unicodedata.normalize("NFC", ...)` before encoding so canonically
equivalent inputs (`café` NFC vs NFD) produce identical gram sets.
Casefold uses `str.casefold()` so German `ß` correctly folds to `ss`.

### `tests/test_code_grams.py` — 61 tests

Covers tokenizer behavior (newlines, multi-byte UTF-8, NFC/NFD, casefold),
all four `GramQuery` tiers, every adversarial case the audit surfaced
(named groups, scoped inline flags, comments, verbose mode, hex escapes,
optional groups, lookarounds, NFC/NFD divergence, lone surrogates),
three-way alternation, escaped pipes, pipes inside character classes,
and invalid-regex degradation.

### `src/vfs/chunking.py` — recursive text splitter

Public surface:

- `recursive_text_split(content, *, chunk_size=2048, overlap=256, separators=DEFAULT_SEPARATORS) -> list[str]`
- `DEFAULT_SEPARATORS = ("\n\n", "\n", " ", "")`

Returns `[]` when content fits in one chunk so the caller (`split_content`
on `VFSEntry` once Phase 2 lands) can detect "no split required" without
re-counting.

Algorithm: region-aware `rfind` walker. Pre-compute oversized regions per
separator level once via `str.split` plus `_find_oversized`, then walk
left-to-right; at each candidate cut take the rightmost separator inside
`[lo, target+sep_len]` with `bisect_right` against the active-region
table to decide which separator levels apply at that offset. Two
specialized fast paths: char-fallback when no real separators are
present, and a single-separator path that skips the region tables.

Performance vs LangChain `RecursiveCharacterTextSplitter` on the 120
markdown files in this repo (1.75 MB total), config `2048/256`:

| | aggregate | throughput |
|---|---:|---:|
| ours | 8.34 ms | 200 MB/s |
| LangChain | 12.07 ms | 138 MB/s |
| **speedup** | | **1.4×** |

Per-file 1.2–1.9× on files larger than 10 KB. Boundaries match the
`str.split`-based baseline at the default config across diverse inputs.

Documented divergences from LangChain:

- We apply the configured `overlap` consistently between adjacent chunks.
  LangChain's `chunk_overlap` is a *ceiling*, not a floor — verified in
  `langchain_text_splitters/base.py:180-188`. For prose with paragraphs
  bigger than the overlap, LangChain emits non-overlapping chunks.
- We pack chunks tighter (median 1,915 vs LC 1,720 chars at 2,048 limit).
  LangChain biases toward semantic break points even at smaller chunk
  sizes.
- We return `[]` for content `<= chunk_size`; LangChain always returns
  `>= 1` chunk.

### Benchmarks

- `grep_glob research/bench_text_splitter.py` — 5 largest text files in
  the repo, best-of-5 wall time + tracemalloc allocation deltas.
- `grep_glob research/bench_vs_langchain.py` — head-to-head against
  LangChain on every markdown file in the repo. Run via
  `uv run --with langchain-text-splitters python "grep_glob research/bench_vs_langchain.py"`.

### `grep_glob research/code_grams_walkthrough.ipynb`

Six-section runnable demonstration of the code-gram primitive: tokenizer
behavior, NFC/casefold normalization, the four `GramQuery` tiers, every
audit-surfaced edge case with sound subset assertions, an end-to-end
candidate-generation pipeline using a `defaultdict(set)` posting index,
and a 30-case soundness sweep. Every cell asserts that the candidate
path doesn't drop a chunk the full scan finds.

## What is NOT done yet

The remainder of [plan.md](./plan.md) phases 2-7 is open work:

### Phase 2 (started, not landed) — Postgres row-store adapter

- `index_content: int` field on `VFSEntry` with derivation in
  `_normalize_and_derive`: `chunk` → 1, `file` → 1, everything else → 0.
  An earlier attempt was reverted; the field name is settled but the
  validator wiring isn't in.
- `VFSEntry.split_content(content: str) -> list[str]` — the dev-overridable
  hook that defaults to `recursive_text_split(content, chunk_size=2048,
  overlap=256)`.
- `VFSEntry.chunk(...) -> list[VFSEntry]` — calls `split_content`,
  composes new `kind="chunk"` entries with sequential `chunk_no` paths
  via `vfs.paths.chunk_path`, mutates `self.index_content = 0`.
  Empty-list return leaves `index_content` alone.
- DDL for `vfs_entry_chunk_grams(gram_kind, gram_key, chunk_id)` plus
  the reverse-lookup index by `chunk_id` for delete/update maintenance.
- Provisioning + `_verify_pattern_schema` extension on
  `PostgresFileSystem` to demand the new artifacts.
- Backend write path: extract grams from chunk content on insert, delete
  grams when a chunk is deleted, cascade old chunks when a file is
  re-chunked. Atomic with chunk row writes.

### Phase 2 (not started) — `_grep_impl` rewrite

- `PostgresFileSystem._grep_impl` swaps `pg_trgm` for the code-gram path:
  build `GramQuery` → SQL intersection → fetch chunk content → fetch
  owner-file paths → run authoritative Python regex via the existing
  `_collect_line_matches`.
- No-false-negative integration test against the in-memory backend
  across fixed strings, regexes, punctuation, path-like strings, and
  case-sensitive vs case-insensitive grep.

### Later phases — out of scope for this story slice

- Phase 3 (glob via grams) — explicitly deferred; the user said no glob
  for now.
- Phase 4 (MSSQL adapter) — same row-store contract, different physical
  types.
- Phase 5 (posting-block storage) — staged immutable blocks per
  `mssql-trigram-inverted-index-design.md`.
- Phase 6 (benchmark harness in the live grep notebook).
- Phase 7 (optional native adapters: SQLite FTS5 trigram, MySQL ngram).

## Decisions captured along the way

- **Default case mode is folded.** The Postgres adapter will maintain
  both raw and folded gram streams; grep queries always emit folded
  grams. The `gram_kind` dimension is in the schema regardless so
  case-sensitive search remains possible without a schema change.
- **Field name is `index_content`, not `indexable`.** Captures the
  state ("include this row's content in the content-side indexes")
  rather than the capability ("can be indexed"). Path-side indexes are
  unconditional and ignore the flag.
- **`split_content` is the override seam, not `chunk`.** Devs override
  `split_content(content: str) -> list[str]` to plug in tree-sitter or
  semantic chunkers; the path/line-range bookkeeping in `chunk()` stays
  in the model. Empty list = "no split required" = `index_content`
  flag is left alone.
- **Re-chunk cascade is the backend's responsibility.** When a file is
  re-chunked, the backend deletes pre-existing chunk rows for that
  file before persisting new ones. The model is dumb; the writer
  handles the transaction.
- **The regex query planner traverses `sre_parse` AST** rather than
  hand-rolling a tokenizer. Eliminated every false-negative bug
  surfaced by the audit in one shot. `sre_parse` was deprecated in
  3.11 but still re-exports from `re._parser` and is the only
  supported access path for regex AST inspection.
- **NFC normalization is the indexer + planner contract.** Without it,
  `café` (NFC) and `café` (NFD) produce disjoint gram sets and
  matching content is silently dropped. ASCII inputs short-circuit
  the normalize call.

## Files touched

```
context/stories/013-database-agnostic-code-trigram-index/
  spec.md                                       (modified, prior commit)
  plan.md                                       (modified, prior commit)
  research.md                                   (modified, prior commit)
  mssql-trigram-inverted-index-design.md       (new, prior commit)
  implementation.md                             (this file)
src/vfs/code_grams.py                           (new, f840ce5)
src/vfs/chunking.py                             (new, f6d22f5)
tests/test_code_grams.py                        (new, f840ce5)
grep_glob research/code_grams_walkthrough.ipynb (new, f840ce5)
grep_glob research/bench_text_splitter.py       (new, f6d22f5)
grep_glob research/bench_vs_langchain.py        (new, f6d22f5)
```

No backend, model, or public API changes have landed yet. The work is
purely additive standalone modules + tests + research artifacts.
