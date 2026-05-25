# 013 — Implementation notes

- **Status:** in-progress (Phase 1 + 1.5 + chunker + model chunking surface complete; Phase 2 **redirected 2026-05-24** from Postgres-first to base-class-universal — delta-log gram store + maintenance + grep now target `DatabaseFileSystem`; landed Postgres DDL/provisioning to be lifted into a minted model)
- **Date:** 2026-05-01 (last updated 2026-05-24)
- **Spec:** [spec.md](./spec.md) (phasing is spec.md §6; the standalone plan.md
  was dropped 2026-05-25 — its work items live in this file's §"What's next
  inside Phase 2")

## Summary

Pure-Python primitives for the database-agnostic code-gram index are
landed: byte-trigram tokenizer with NFC + casefold normalization, a
soundness-first regex-to-`GramQuery` planner built on Python's `sre_parse`
AST, a LangChain-compatible recursive text splitter, and the
`VFSEntry`-side chunking surface (`index_content` field, `split_content`
override seam, `chunk()` method). No DB schema, no write-path gram
maintenance, no `_grep_impl` changes yet.

Commits on `main`:

- `f840ce5` — code grams + tests + walkthrough notebook
- `f6d22f5` — text splitter + benchmarks
- `172310b` — earlier implementation snapshot
- `0c4f7d6` — `VFSEntry.chunk()`, `index_content`, `split_content`,
  chunking offset refactor, 19 new tests

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
- `split_with_line_ranges(content, *, chunk_size=2048, overlap=256, separators=DEFAULT_SEPARATORS) -> list[tuple[str, int, int]]`
  — emits `(text, line_start, line_end)` per chunk; lines are 1-indexed
  and `line_end` is the line containing the chunk's last character. A
  chunk that lives entirely inside a single oversized line has
  `line_start == line_end`.
- `DEFAULT_SEPARATORS = ("\n\n", "\n", " ", "")`

Returns `[]` when content fits in one chunk so the caller can detect
"no split required" without re-counting.

Algorithm: region-aware `rfind` walker. Pre-compute oversized regions per
separator level once via `str.split` plus `_find_oversized`, then walk
left-to-right; at each candidate cut take the rightmost separator inside
`[lo, target+sep_len]` with `bisect_right` against the active-region
table to decide which separator levels apply at that offset. Two
specialized fast paths: char-fallback when no real separators are
present, and a single-separator path that skips the region tables.

Implementation note: `recursive_text_split` is a thin slicing wrapper over
an internal `_chunk_offsets` helper that returns the `(start, end)` integer
pairs the algorithm tracks anyway. `split_with_line_ranges` consumes those
offsets directly plus a single `O(n)` newline scan and `O(log k)` bisect
per chunk — no second pass, no `str.find` re-locating.

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

### `src/vfs/models.py` — `index_content` field, `chunk()`, `split_content()`

New on `VFSEntry`:

- `index_content: bool = Field(default=False, index=True)` — boolean flag
  controlling whether this row's content feeds content-side indexes (vector,
  text-search, code-gram trigrams). Path-side indexes ignore it. Validator
  default in `_normalize_and_derive`: `kind in {"file", "chunk"}` → True,
  everything else → False. Explicit values in input data are respected.
- `VFSEntry.split_content(content: str) -> list[tuple[str, int, int]]` —
  staticmethod, the override seam. Default delegates to
  `split_with_line_ranges` with `chunk_size=2048` / `overlap=256`. Devs
  plug in tree-sitter / token-aware / semantic chunkers by overriding
  this on a subclass.
- `VFSEntry.chunk() -> list[VFSEntry]` — instance method, no parameters.
  Calls `self.split_content(self.content)`, composes new `kind="chunk"`
  entries via `vfs.paths.chunk_path(self.path, name)` where `name` is
  `<line_start>_<line_end>`, with `@<char_offset>` appended only when
  multiple chunks share a line range (single oversized line case).
  Mutates `self.index_content = False` on success. Empty-list short-circuit
  when content fits in one chunk leaves the flag alone. Raises
  `ValueError` for non-file kinds.

The chunking parameters live on `split_content`, not `chunk()` —
overrides are the only way to tune chunk size, which keeps the public
`chunk()` signature stable.

### `tests/test_models.py` — 19 new tests

Covers `index_content` derivation across all kinds, explicit field
overrides, `split_content` shape (short content → empty list, long
content → tuples with valid line numbers, oversized single line keeps
chunks inside one line), `chunk()` flow (no-op on short content, flips
flag on long, path uses line-range form, single-line collisions get
`@offset` suffix while unique ranges stay clean, `owner_id` propagates,
non-file kinds raise, subclass override of `split_content` propagates
through `chunk()`).

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

## Phase 2 — in flight (story 014 slice 3)

> **Redirected & rescoped 2026-05-24.** Phase 2 originally targeted
> `PostgresFileSystem` and covered both maintenance *and* grep (the
> "Landed so far" / "What's next" items below were Postgres-scoped).
> Three confirmed decisions reshape it: **(a)** keep the append-only
> **delta-log** store (already chosen — see §"Schema deviation");
> **(b)** move index production + maintenance into the base
> `DatabaseFileSystem` so SQLite, MSSQL, and Postgres inherit **one**
> implementation, with **no `pg_trgm`** as the index anywhere; and
> **(c)** scope this story to **producing and maintaining** the index —
> **querying it is provider-specific and out of scope** (the `_grep_impl`
> read path, regex→gram predicates, intersection SQL, Python match, and
> removing the Postgres `pg_trgm` grep path all move to a separate query
> effort; see spec.md §Out). The maintenance is already backend-neutral;
> the only Postgres-specific piece is the table DDL, replaced by a minted
> SQLAlchemy gram model. See §"What's next inside Phase 2" below for the
> work items, including the load-bearing abort/rollback fix. The §"Landed so far"
> Postgres DDL below is retained as history but will be lifted into the
> minted model.

Phase 2 ships inside [story 014 slice 3](../014-auto-chunk-and-auto-index-on-write/implementation.md#slice-3--in-progress)
because the gram-store maintenance is the same write-pipeline hook
(`_apply_trigram_maintenance`) that auto-index defines. Reading the
slice 3 section is the load-bearing context for what's actually
shipped.

### Schema deviation from spec §4

Spec §4 described the row-store MVP as "adds insert rows and deletes
remove rows" — the table at any point holds current truth. The
implementation ships the **append-only delta** shape instead, which
matches the posting-block model (spec §3, phase 5) collapsed onto the
row store. The staging stream IS the future posting-block compaction
input, so we skip a migration when phase 5 lands.

Final schema:

```sql
CREATE TABLE {entries_table}_chunk_grams (
    seq      bigserial PRIMARY KEY,
    gram_key integer   NOT NULL,
    chunk_id text      NOT NULL,
    action   smallint  NOT NULL    -- 1=add, 0=delete
);
CREATE INDEX ix_..._gram_chunk_seq
    ON {table} (gram_key, chunk_id, seq DESC);
CREATE INDEX ix_..._chunk_id ON {table} (chunk_id);
```

Reads use latest-action-wins per `(gram_key, chunk_id)` via
`DISTINCT ON ... ORDER BY seq DESC`. Other simplifications vs.
spec §4:

- **No `gram_kind` column.** Single normalization (folded);
  case-sensitive grep gets a less selective candidate set with
  Python verification enforcing case. A raw-gram stream is a
  separate slice if benchmarks demand it. This deviates from the
  earlier "maintain both raw and folded streams" decision below
  — slice 3 chose the simpler single-stream path.
- **No `owner_path`, `line_start`, `line_end`.** Spec marked these
  optional; the join to `vfs_entries` is mandatory anyway for
  content fetch, and denormalizing inflated gram-row storage
  roughly 5–10× for no correctness win.
- **No FK** to the entries table — write-order independent;
  cascade is application-level via `_stage_chunk_cascade`.
- **No `user_id`** — `vfs_entries` is already path-scoped; the
  scope filter applies on the join.

### Landed so far

`src/vfs/backends/postgres.py`:

- `_native_chunk_grams_verified` flag.
- `_chunk_grams_bare_name()`, `_chunk_grams_table()`,
  `_chunk_grams_schema_hint()` helpers.
- `install_native_chunk_grams_schema()` — idempotent
  `CREATE TABLE IF NOT EXISTS` + both indexes.
- `verify_native_chunk_grams_schema()` and
  `_verify_chunk_grams_schema(session)` — fail-fast with a hint
  pointing at the installer. Cached after first pass.

`src/vfs/backends/database.py`:

- Base hook renamed from `_apply_index_maintenance` to
  `_apply_trigram_maintenance` — the orchestrator already ran
  embeddings directly, so the old name was wider than the
  responsibility. Docstring now spells out the chunk-vs-file
  identity contract.

### What's next inside Phase 2 (base-class-universal, production-only)

All items land in `src/vfs/` base modules so every backend inherits
them. The story is scoped to **producing and maintaining** the index;
querying it is provider-specific and out of scope (spec.md §Out). The
full work-item list follows.

- **`models.py` — `_build_gram_table_class`** mirroring
  `_build_entry_table_class`: minted `table=True` gram model with own
  `MetaData()`, portable types (`BigInteger` autoincrement `seq`,
  `Integer` `gram_key`, `String` `chunk_id`, `SmallInteger` `action`),
  and `Index()` objects. Replaces the raw Postgres DDL.
- **`DatabaseFileSystem.__init__` / `setup()`** — mint
  `self._gram_model`; provision via metadata `create_all`. Retire (or
  thin-shim) `install_native_chunk_grams_schema` / `verify_*`.
- **Base `_apply_trigram_maintenance`** — diff gram sets for files
  (persistent id via `existing.id`), all-adds for chunks (no persistent
  id; cascade handles their deletes). Stage via
  `session.add(self._gram_model(...))`.
- **Base `_stage_chunk_cascade`** — read existing chunks, recompute
  their grams, stage delete deltas using old chunk ids, then `super()`
  to issue the DELETE.
- **Abort/rollback fix** — `_write_impl` must `await session.rollback()`
  on `_WriteAbort` (or reorder embeddings before gram staging) so an
  embedding failure mid-batch can't commit orphan gram deltas. Test it.
- **Maintenance-correctness integration test** on SQLite **and**
  Postgres: after writes/edits/deletes, the folded index contains
  exactly the grams of the currently-committed chunks (storage
  completeness, no committed gram missing); an aborted write commits no
  gram rows.

*Out of scope here (query path, provider-specific):* the `_grep_impl`
code-gram read query (`GramQuery` → intersection → content fetch →
Python verification), removing the Postgres `pg_trgm` grep path, and any
grep-vs-ripgrep benchmark.

### Later phases — out of scope for this story slice

- Phase 3 — querying the index (candidate generation, regex→gram
  predicates, intersection, Python match, `_grep_impl` wiring,
  `pg_trgm` removal). Provider-specific; tracked separately.
- Phase 4 (MSSQL) — largely subsumed: MSSQL inherits the base index
  production + maintenance. Remaining work is confirming the minted
  model emits valid T-SQL.
- Phase 5 (posting-block storage) — staged immutable blocks per
  spec.md §"Durable Storage Model" (backend-neutral); a base-class storage
  upgrade that benefits all backends at once.
- Phases 6–7 — benchmarks and optional native read accelerators; both
  read-path concerns, out of scope.

## Decisions captured along the way

- **Integer `doc_id` for posting compression; keep `uuid4` PK (2026-05-25).**
  Posting-list compression (delta/varint, Roaring, Elias-Fano) needs *sorted
  integer* doc IDs, which a `uuid`/`text` chunk id cannot provide. Resolution:
  add an auto-increment `doc_id` column to `vfs_entries` (stable per row, shared
  by files and chunks) and keep `uuid4` as the entity primary key — do **not**
  switch the global PK (it would forfeit client-side id generation, and VFS
  relationships key on `path` not `id`). Gram staging references the entry
  `uuid` (known at write time, no ordering dependency); `doc_id` is resolved by
  join at flush for **adds**, and captured at stage time for **deletes** (a
  hard-deleted row is gone by compaction, so the join would fail). `doc_id`s are
  **stable and never renumbered** — deletes/re-chunks leave gaps, which delta
  encoding tolerates (sorted is the requirement, dense is a bonus); a rare full
  reindex is the only dense renumber. Posting blocks are **re-encoded at
  compaction, never patched in place**, and a file edit rewrites only the changed
  grams' affected blocks (O(changed grams) at write time, compaction amortized
  and localized) — not the whole index. This is the Phase 5 evolution of the
  shipped `chunk_id text` delta-log (see spec.md §Data Model → Doc IDs and
  §"Durable Storage Model").

- **Index production + maintenance live in the base class, not per
  backend (2026-05-24).** The posting list is conceptually
  backend-neutral — gram computation, the old/new diff, and
  `session.add` staging are all dialect-free. Only the table DDL was
  Postgres-shaped, and it has a portable equivalent (a minted SQLAlchemy
  gram model). Landing one implementation in `DatabaseFileSystem` means
  SQLite, MSSQL, and Postgres inherit it, collapsing the old MSSQL-first
  / Postgres-follow-up adapter sequence into a single deliverable.
- **Story scoped to producing the index, not querying it (2026-05-24).**
  Querying — candidate generation, regex→gram predicates, the
  latest-action-wins intersection query, content fetch, Python final
  match, `_grep_impl` wiring — is provider-specific and out of scope.
  The shared work stops at a correct, current index.
- **`pg_trgm` is not the index (2026-05-24).** No backend produces or
  maintains a `pg_trgm` artifact as this index: its word-oriented,
  punctuation-insensitive trigram model is the wrong semantics for code
  search. (Removing any existing `pg_trgm` *query* path on Postgres is
  part of the out-of-scope query work, not this story.)
- **Pre-persist staging forces an abort/rollback fix (2026-05-24).**
  Making `_apply_trigram_maintenance` real means it `session.add`s gram
  rows *before* `_write_phase_persist`. Because `_write_impl` catches
  `_WriteAbort` and early-returns an error result (it does **not**
  re-raise), the per-batch session would otherwise commit those staged
  deltas even though their chunk rows never persisted. The fix —
  `await session.rollback()` in the abort handler (or reorder embeddings
  before gram staging) — is part of Phase 2, not a follow-up.
- **Default case mode is folded.** ~~The Postgres adapter will
  maintain both raw and folded gram streams; grep queries always emit
  folded grams. The `gram_kind` dimension is in the schema regardless
  so case-sensitive search remains possible without a schema change.~~
  **Superseded 2026-05-13 (slice 3):** the dual-stream plan was
  dropped during slice 3 design. The implementation ships
  **folded only** with no `gram_kind` column; case-sensitive grep
  gets a less selective candidate set than a dedicated raw index
  would, but Python verification enforces case correctness. A raw
  stream is a follow-up slice if benchmarks call for it. The
  posting-block design (phase 5) can re-introduce per-stream
  separation without a schema migration by namespacing inside
  `index_id`.
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
  spec.md                                       (rewritten 2026-05-25; contract-first, analyses folded in)
  plan.md                                       (removed 2026-05-25; phasing → spec.md §6, work items → this file)
  research.md                                   (modified, prior commit)
  mssql-trigram-inverted-index-design.md       (removed 2026-05-24; folded into spec.md, db-agnostic)
  implementation.md                             (this file)
src/vfs/code_grams.py                           (new, f840ce5)
src/vfs/chunking.py                             (new f6d22f5; refactored 0c4f7d6)
src/vfs/models.py                               (modified, 0c4f7d6)
tests/test_code_grams.py                        (new, f840ce5)
tests/test_models.py                            (modified, 0c4f7d6)
grep_glob research/code_grams_walkthrough.ipynb (new, f840ce5)
grep_glob research/bench_text_splitter.py       (new, f6d22f5)
grep_glob research/bench_vs_langchain.py        (new, f6d22f5)
```

The model now exposes the chunking surface (`index_content` field +
`split_content` override seam + `chunk()` method). DB schema, write-path
gram maintenance, and grep rewrite are still open.
