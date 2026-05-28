# 013 — Implementation notes

- **Status:** in-progress (Phase 1 + 1.5 + chunker + model chunking surface complete; Phase 2 **redirected 2026-05-24** to base-class-universal. **Landed 2026-05-25:** the identity reshape (`id` → integer auto-increment PK == posting-list `doc_id`; uuid → new `entry_id` column), the minted `VFSGram` delta-log model + `_build_gram_table_class`, and `self._gram_model` wired into `DatabaseFileSystem`; then a working `_apply_trigram_maintenance`, the Phase 5 durable-store schema (`posting_blocks` / `gram_batches` / `gram_stats` tables + staging `batch_id`) minted on the shared `MetaData`, and the `entry_id` write-path load-only fix; then the chunk-cascade rework (capture old chunks in fetch-existing, de-index them in the index phase, DELETE before persist) and the abort/rollback fix. **Pending:** the `code_grams.py` docstring cleanup and the integration test.) **2026-05-27:** the four-table block model was collapsed to the two-table target (Core `Table`s), the write-path maintenance rewritten to reconciliation-driven bulk staging, and chunk-all adopted — see §"2026-05-27 — Phase 5 two-table rewrite" below. Durable flush + gamma codec remain.
- **Date:** 2026-05-01 (last updated 2026-05-27)
- **Spec:** [spec.md](./spec.md) (phasing is spec.md §6; the standalone plan.md
  was dropped 2026-05-25 — its work items live in this file's §"What's next
  inside Phase 2")

## 2026-05-27 — Phase 5 two-table rewrite (this session)

Reconciled the landed four-table block model to the spec's two-table target and
rewrote the write-path maintenance. **The durable flush and the gamma codec are
the remaining Phase-5 work.**

### Done

- **Two-table durable model.** Removed `VFSPostingBlock` / `VFSGramBatch` /
  `VFSGramStat` and the staging `batch_id`. The gram tables are now plain
  SQLAlchemy **Core `Table`s** (internal index machinery, never validated
  through Pydantic — per the bulk-insert learning's table-modeling note):
  `{table}_grams_staging` (`seq` PK, `gram_key`, `entry_id`, `doc_id`, `action`)
  and `{table}_grams_posting_list` (`gram_key` PK, `postings`, `encoding`,
  `doc_count`, `byte_size`). Action/encoding codes are module-level constants
  (`GRAM_ACTION_ADD/DELETE`, `ENCODING_DELTA_VARINT/GAMMA/ROARING`).
- **`_build_vfs_tables`** (models.py) replaces the three `_build_*` helpers: one
  function mints the entry model + both gram tables on a shared `MetaData`.
  Entry PK is now `sqlite_autoincrement=True` (bars rowid reuse). Minted entry
  class gets a **unique name** (`name` + random token) to avoid the SQLAlchemy
  declarative-registry collision warning across mounts.
- **`code_grams.py`** docstring corrected to the single lowercase (folded)
  stream; removed the unused `GRAM_KIND_*` constants.
- **`setup()`** now runs `create_all` (idempotent DDL). New **`ensure_schema()`**
  reflects the live DB and diffs it against the in-memory tables (columns,
  nullability, PK, coarse type family), raising `SchemaMismatchError` with a
  per-difference message; read-only, for migration-owning callers.
- **`VirtualFileSystem`** gained MCP-aligned `name` / `title` / `description`
  (public); the old `self._name = class name` became `self._class_name`.
- **chunk-all.** `split_with_line_ranges` now emits a whole-file piece for
  content ≥ `GRAM_SIZE` bytes (else `[]`); `split_code` / `split_notebook` route
  their fits-in-one-chunk and fallback cases through it. Every ≥3-byte document
  becomes ≥1 chunk; the file row's `index_content` flips `False`. Verified by a
  throwaway harness: reconstruction, ≤`chunk_size`, valid line ranges, and speed
  parity with the old splitter.
- **Maintenance rewrite.** `_stage_gram_deltas` replaces `_apply_trigram_maintenance`
  + `_stage_chunk_delete_deltas`: **reconciliation-driven, no gram diff** —
  de-indexed rows (stale chunks + flag-flipped files) all-delete carrying
  `doc_id`; path-stable edits all-delete old + all-add new (LAW resolves the
  overlap); new rows all-add (`doc_id` NULL). All deltas land in **one Core bulk
  `insert`** (the ~50× win). `index()` simplified accordingly.
- **Dropped `index_exclusion_reason` + §4.3 per-chunk limits.** With chunk-all
  and size-bounded chunks, neither limit (2 MiB / 20k grams) can fire, so the
  column, validator, and exclusion branch are dead. **The code now diverges from
  spec §4.3 and the 4-state truth table — the spec needs updating** (or the
  limits reintroduced if an unsplittable oversized chunk is a real concern).

### Open questions

- **chunk-all `write()` shape (undecided).** A small file now produces a chunk
  row, so `write()` returns file + chunk candidates (2N for N small files), and
  embeddings + the `indexed_content_hash` watermark attach to the **chunk**, not
  the file. Options on the table: (A) accept; (B) keep chunk-all internally but
  hide chunk rows from `write()` candidates; (C) don't chunk single-piece files
  (revert to self-index — `_stage_gram_deltas` already supports indexing a file
  row). 8 existing tests encode the old single-row behavior and are red pending
  this decision.
- Duplicate-content chunk `occurrence` tie-break (spec §10 item 7) still open.

### Remaining work

1. **`delta+gamma` posting codec** — encode/decode ported from codesearch's exact
   byte format (gap-from-−1, trailing-zero terminator, `deltaZeroEnc=16`,
   LSB-first), count-bounded decode + terminator assert.
2. **Watermarked single-flight flush** — `seq` watermark, LAW fold, resolve
   surviving adds via `entry_id`→`id` join (drop join-misses), idempotent
   set-merge into posting rows (UPDATE, or DELETE when emptied), delete the exact
   folded `seq` set; one transaction. Wire into `index(compile_post_list=True)`.
3. **Tests** — update the 8 chunk-all behavior tests once (A/B/C) is decided; add
   codec round-trip, flush fold, and §4.5 read-fold tests.
4. **Test migration** — ~15 call sites use the removed `_build_entry_table_class`
   (test_models / test_postgres_backend / test_mssql_backend / test_graph);
   redirect to `_build_vfs_tables`, then inline/remove the old helper.
5. **Spec update** — record the dropped exclusion model in spec §4.3 / §9.

### Pre-existing breakage (not this story)

64 tests fail on a pristine `main` (verified in a HEAD worktree): `_move_impl` /
`_copy_impl` / `_delete_impl` call `self._error(result)` on a **success**
`VFSResult`, which pydantic 2.12 rejects (errors must be `list[str]`). Move /
copy / delete are broken on `main`. Out of 013 scope; flagged for a separate fix
(likely `return result` when `success`).

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

Final schema (minted portably by `_build_gram_table_class`; the logical
shape, shown as Postgres DDL):

```sql
CREATE TABLE {entries_table}_chunk_grams (
    seq      bigserial PRIMARY KEY,
    gram_key integer   NOT NULL,
    entry_id varchar(36) NOT NULL,   -- vfs_entries.entry_id (uuid)
    doc_id   bigint,                 -- vfs_entries.id; null on adds, set on deletes
    action   smallint  NOT NULL,     -- 1=add, 0=delete
    batch_id bigint                  -- flush batch folding this row; null while pending
);
CREATE INDEX ix_..._gram_entry_seq
    ON {table} (gram_key, entry_id, seq);
CREATE INDEX ix_..._entry_id ON {table} (entry_id);
```

The MVP folds by latest-action-wins per `(gram_key, entry_id)` — `entry_id`
(the uuid) is known at write time, so the fold is unambiguous before
`doc_id` is resolved. `doc_id` (= `vfs_entries.id`, the integer PK) is the
posting-list key carried forward for Phase 5: **null on adds** (resolved by
join `entry_id → vfs_entries.id` at flush), **captured at stage time on
deletes** (the entry row may be gone before flush). Other simplifications
vs. spec §4:

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
  cascade is application-level via the chunk-cascade helpers
  (`_fetch_existing_chunks` / `_stage_chunk_delete_deltas` /
  `_delete_stale_chunks`).
- **No `user_id`** — `vfs_entries` is already path-scoped; the
  scope filter applies on the join.

### Landed so far (2026-05-25)

`src/vfs/models.py`:

- **Identity reshape.** `id` is now the auto-increment **integer** PK
  (`BigInteger().with_variant(Integer, "sqlite")`) — which *is* the
  posting-list `doc_id`: dense, sorted, stable, mapped to the native
  per-backend auto-increment (rowid / `BIGSERIAL` / `BIGINT IDENTITY`), so
  no second auto-increment column or trigger is needed. The client-side
  `uuid4` moved to a new unique, indexed `entry_id` column. `id` is `None`
  until flush; pre-persist identity uses `entry_id`.
- **`VFSGram` + `_build_gram_table_class`.** A `table=False` delta-log base
  (`seq` PK, `gram_key`, `entry_id`, nullable `doc_id`, `action`, with
  `ACTION_ADD=1` / `ACTION_DELETE=0`) and a minter that mirrors
  `_build_entry_table_class` — **but binds to the entry table's `MetaData`**
  (not its own) so one `create_all` provisions both tables. Indexes:
  `(gram_key, entry_id, seq)` and `(entry_id)`. Staging now also carries a
  nullable `batch_id` (the flush batch folding it); the table is a transient
  buffer — rows are deleted once durable (an add when a flush folds it into a
  block, a delete when compaction rewrites the block holding its `doc_id`), so
  there is no `applied_at` tombstone and it does not grow without bound.
- **Phase 5 durable-store schema** (minted alongside `VFSGram` on the same
  `MetaData`, via a shared `_mint_table_class` helper; flush/compaction
  *logic* is still future work — only the tables landed):
  - `VFSPostingBlock` → `{entries}_posting_blocks`: one immutable, compressed
    posting block (`block_id` PK, `gram_key`, `batch_id`, `doc_count`,
    `min_doc_id`, `max_doc_id`, `encoding` (`ENCODING_DELTA_VARINT=1`),
    `postings` blob, `is_active`). Indexes `(gram_key, is_active, min_doc_id)`
    for the read fold and `(batch_id)` for flush/compaction.
  - `VFSGramBatch` → `{entries}_gram_batches`: flush batch lifecycle
    (`batch_id` PK, `status` Open/Closed/Flushing/Flushed/Failed, timestamps),
    indexed by `status`.
  - `VFSGramStat` → `{entries}_gram_stats`: per-gram `doc_freq` / `block_count`
    for rarest-first reads (PK `gram_key`).

`src/vfs/backends/database.py`:

- **`_apply_trigram_maintenance` implemented** (was a no-op). Extracts
  folded-only grams (`unique_code_grams(..., folded=True)`); for a path-stable
  file edit it diffs old vs. new and stages `old − new` deletes + `new − old`
  adds, **both keyed on the surviving `old.entry_id` / `old.id`** (the persist
  phase updates `existing` in place, discarding the incoming uuid, so keying on
  the incoming row would break the `(gram_key, entry_id)` fold); a new file or
  any chunk stages all-adds (chunk deletes are the cascade's job, never
  diffed); `delete_only` stages every current gram as a delete. Deltas are
  staged with `session.add` and emitted by the single persist flush — **no
  statement is issued inside the helper** (chosen over a bulk `insert()` for
  consistency with the rest of the write path and one all-or-nothing
  transaction boundary).
- `self._gram_model`, `self._posting_block_model`, `self._gram_batch_model`,
  `self._gram_stat_model` all minted in `__init__` on `self._model.metadata`.

`src/vfs/columns.py`:

- Added `entry_id` to the `_fetch_existing` `load_only` set. Without it,
  gram maintenance's read of `old.entry_id` on a narrowed existing row fired a
  deferred-column refresh in a sync context → `MissingGreenlet`. (The PK `id`
  is always loaded by `load_only`; `content` was already in the set.)

Chunk-cascade rework + abort rollback (`src/vfs/backends/database.py`):

- **Cascade moved out of persist into the fetch-existing phase**, split three
  ways. `_fetch_existing_chunks` captures the old chunk rows for re-chunked
  files via a **column SELECT** (`id` / `entry_id` / `content`) keyed on the
  indexed `kind = 'chunk' AND parent_path IN (...)` — an equality/IN match, not
  a `LIKE` prefix scan — returning plain `_StaleChunk` tuples. Capturing as
  tuples (not ORM rows) means the later cascade `DELETE` can't expire them, so
  their content stays readable when the index phase reads it. The capture only
  runs when `_auto_index` is on (nothing else consumes it).
- **De-indexing happens in the index phase**, not the cascade: `auto_index`
  calls `_stage_chunk_delete_deltas(ctx.existing_chunks)`, which queues each
  captured chunk's folded grams as delete deltas (carrying its `doc_id` /
  `entry_id`). Because the content was captured up front, this no longer depends
  on the rows still existing — dissolving the read-before-delete ordering knot.
- **`_delete_stale_chunks`** issues the row `DELETE` (same `parent_path IN`
  match) before persist inserts the new chunks — chunk paths collide on
  re-chunk and `path` is unique, so the stale rows must be gone first. It runs
  whether or not indexing is on (chunk cleanup is not gated on the index).
- **Abort/rollback fix landed.** `_write_impl` now `await session.rollback()`s
  in the `_WriteAbort` handler. Since the early `DELETE` executes before the
  abort-prone phases (`auto_chunk`, embeddings), a swallowed abort would
  otherwise commit a partial write (chunks deleted, new ones never inserted).
  Whole-session rollback is correct because **each write owns its own session**
  (verified: `_route_write_batch`, copy, edit, mkdir each call `_write_impl`
  once per session; move/delete don't go through it) — so it drops only this
  write's staged work.

`src/vfs/backends/postgres.py`:

- **Removed** the now-dead `install_native_chunk_grams_schema` /
  `verify_native_chunk_grams_schema` / `_verify_chunk_grams_schema` /
  `_chunk_grams_*` helpers and the `_native_chunk_grams_verified` flag — the
  minted model + shared `MetaData` supersede the hand-written Postgres DDL.

`src/vfs/code_grams.py`:

- Bound to `re._parser` / `re._constants` directly instead of the deprecated
  `sre_parse` / `sre_constants` shims (drops the `warnings.catch_warnings`
  suppression block).

### What's next inside Phase 2 (base-class-universal, production-only)

All items land in `src/vfs/` base modules so every backend inherits
them. The story is scoped to **producing and maintaining** the index;
querying it is provider-specific and out of scope (spec.md §Out). The
full work-item list follows.

- **[done] `models.py` — `_build_gram_table_class`** mirroring
  `_build_entry_table_class`: minted `table=True` gram model (`seq` PK,
  `gram_key`, `entry_id`, nullable `doc_id`, `action`) and `Index()`
  objects. Binds to the entry table's `MetaData` (not its own) so a single
  `create_all` provisions both. Replaces the raw Postgres DDL.
- **[done] `DatabaseFileSystem.__init__`** — mint `self._gram_model` on
  `self._model.metadata`. No `setup()` change needed: provisioning rides the
  existing `create_all`. The Postgres `install_*`/`verify_*` helpers were
  removed outright (not thin-shimmed).
- **[done] Base `_apply_trigram_maintenance`** — diff gram sets for
  path-stable files (deletes carry `entry_id` + `doc_id = existing.id`; adds
  carry the **same surviving `entry_id`**, `doc_id = None`), all-adds for
  chunks/new files (no persistent id; cascade handles their deletes),
  `delete_only` for flag-flips. Staged via `session.add` (not a bulk
  `insert()`); emitted by the single persist flush. Forced the `columns.py`
  `entry_id` load-only fix.
- **[done, ahead of schedule] Phase 5 durable-store schema** — `posting_blocks`
  / `gram_batches` / `gram_stats` tables + staging `batch_id` minted on the
  shared `MetaData` (see "Landed so far"). Only the *schema* landed; flush,
  compaction, and stats maintenance logic remain Phase 5.
- **[done] Chunk cascade (reworked)** — split into `_fetch_existing_chunks`
  (capture old chunks as `_StaleChunk` tuples in the fetch-existing phase,
  keyed on indexed `parent_path IN (...)`), `_stage_chunk_delete_deltas`
  (de-index them in the index phase off the captured tuples), and
  `_delete_stale_chunks` (the row `DELETE` before persist). Replaces the old
  `_stage_chunk_cascade` that lived in persist.
- **[done] Abort/rollback fix** — `_write_impl` now `await session.rollback()`s
  on `_WriteAbort`, so the early stale-chunk `DELETE` can't commit a partial
  write. Correct under one-session-per-write. Integration coverage still
  pending (see below).
- **[pending] `code_grams.py` docstring cleanup** — the module docstring
  still describes a `gram_kind` raw+folded pair (spec §4.1: stale); correct
  it and drop the unused `GramKind`/`GRAM_KIND_*` constants.
- **[pending] Maintenance-correctness integration test** on SQLite (and
  Postgres when run): after writes/edits/deletes, the folded index contains
  exactly the grams of the currently-committed chunks (storage completeness,
  no committed gram missing); an aborted write commits no gram rows.

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
  upgrade that benefits all backends at once. **Schema landed early
  2026-05-25** (`posting_blocks` / `gram_batches` / `gram_stats` + staging
  `batch_id`); the flush, copy-on-write compaction, and stats-maintenance
  *logic* remain.
- Phases 6–7 — benchmarks and optional native read accelerators; both
  read-path concerns, out of scope.

## Decisions captured along the way

- **`id` becomes the integer auto-increment PK; uuid moves to `entry_id`
  (2026-05-25) — reverses the earlier "keep `uuid4` PK" decision.** Posting-list
  compression (delta/varint, Roaring, Elias-Fano) needs *sorted integer* doc
  IDs. The earlier plan kept `uuid4` as the PK and added a *separate*
  auto-increment `doc_id` — but a second auto-increment column is not portable:
  SQLite only auto-increments the `INTEGER PRIMARY KEY` (rowid), and MSSQL allows
  one `IDENTITY` per table. Making the **single primary key** the auto-increment
  integer sidesteps that entirely — every backend auto-increments its PK
  natively (rowid / `BIGSERIAL` / `BIGINT IDENTITY`), with no trigger or second
  sequence. So `vfs_entries.id` is now that integer and *is* the posting `doc_id`;
  the client-side `uuid4` moves to a new unique `entry_id` column, which
  preserves the client-side identity the earlier decision was protecting (VFS
  relationships key on `path`, so the uuid carried no FK weight — confirmed: no
  FKs/relationships reference it). Gram staging references `entry_id` (known at
  write time, no ordering dependency); `doc_id` (= `id`) is resolved by join at
  flush for **adds** and captured at stage time for **deletes** (a hard-deleted
  row is gone by compaction, so the join would fail). `id`/`doc_id` is **stable
  and never renumbered** — deletes/re-chunks leave gaps, which delta encoding
  tolerates (sorted is the requirement, dense is a bonus). *Caveat:* SQLite may
  reuse the largest `rowid` after a delete; that only matters for Phase 5
  posting-block compaction (which applies deletes), not the `entry_id`-folded
  delta-log. Posting blocks (Phase 5) are **re-encoded at compaction, never
  patched in place** (see spec.md §5.3, §5.4).

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
- **Pre-persist staging forces an abort/rollback fix (2026-05-24; landed
  2026-05-25).** Making `_apply_trigram_maintenance` real means it
  `session.add`s gram rows *before* `_write_phase_persist`; the
  reworked cascade also issues a stale-chunk `DELETE` in the fetch-existing
  phase, *before* the abort-prone `auto_chunk` / embedding phases. Because
  `_write_impl` catches `_WriteAbort` and early-returns an error result (it
  does **not** re-raise), the per-batch session would otherwise commit that
  partial work (deltas staged, chunks deleted) even though the write failed.
  **Fix: `await session.rollback()` in the abort handler.** A *whole-session*
  rollback is correct because **each write owns its own session** — no
  production path issues two writes on one session (`_route_write_batch`
  passes a whole group as one `_write_impl` call; copy/edit do read-only work
  before their single `_write_impl`; move/delete bypass `_write_impl`). The
  savepoint alternative was considered and rejected: it only matters if a
  session is shared across writes, which the architecture forbids. (Tests that
  chained multiple `_write_impl` calls into one `_use_session` block were
  violating that rule; they get one session per write.)
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
- **The regex query planner traverses the regex AST** rather than
  hand-rolling a tokenizer. Eliminated every false-negative bug
  surfaced by the audit in one shot. It binds `re._parser` /
  `re._constants` directly (the modules the deprecated `sre_parse` /
  `sre_constants` shims re-export); there is no public AST access path,
  so the underscore-private import is intentional (2026-05-25).
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
  analysis-{codesearch,zoekt,fts5,pg_trgm-gin}.md (new 2026-05-25; reference-impl evidence)
  implementation.md                             (this file)
src/vfs/code_grams.py                           (new f840ce5; re._parser import 98b5cf6)
src/vfs/chunking.py                             (new f6d22f5; refactored 0c4f7d6)
src/vfs/models.py                               (id→int PK + entry_id + VFSGram, 98b5cf6; staging batch_id + posting_blocks/gram_batches/gram_stats + _mint_table_class)
src/vfs/backends/database.py                    (mint _gram_model, 98b5cf6; _apply_trigram_maintenance impl + mint posting/batch/stat models; chunk-cascade rework + abort rollback, 357de52)
src/vfs/columns.py                              (entry_id added to _fetch_existing load-only set)
src/vfs/backends/postgres.py                    (removed dead chunk_grams DDL helpers, 98b5cf6)
tests/test_code_grams.py                        (new, f840ce5)
tests/test_models.py                            (TestId → int PK + entry_id, ae9d54b)
grep_glob research/code_grams_walkthrough.ipynb (new, f840ce5)
grep_glob research/bench_text_splitter.py       (new, f6d22f5)
grep_glob research/bench_vs_langchain.py        (new, f6d22f5)
```

The model now exposes the chunking surface (`index_content` field +
`split_content` override seam + `chunk()` method). The DB schema and
write-path gram maintenance (add/delete diffing, chunk-cascade de-indexing,
abort rollback) are landed; the `code_grams.py` docstring cleanup, the
maintenance-correctness integration test, and the grep read path remain open.
