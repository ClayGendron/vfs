# 013 — Database-Agnostic Code Trigram Index

- **Status:** draft
- **Date:** 2026-04-24 (restructured 2026-05-25)
- **Owner:** Clay Gendron
- **Kind:** feature + backend + research

## 1. Summary

Build the **production side** of a database-agnostic code-gram index for chunked
source content: define the canonical grams, provision the index tables portably
across backends, and maintain them transactionally as chunks are written,
edited, and deleted. **Querying the index — turning a grep pattern into candidate
chunks — is out of scope** (provider-specific, decided elsewhere).

Why: code search needs punctuation-, operator-, and whitespace-sensitive
substring/regex filtering that `pg_trgm`'s word-oriented model cannot provide.
Production code-search systems converge on inverted **trigram** indexes used as a
*filter*: the index narrows the corpus to candidate documents, then a real regex
verifies them. This story delivers a portable, correct, current such index; it
deliberately stops short of reading it back.

Design and constants here were validated against the cloned source of the
reference implementations — see [`analysis-codesearch.md`](./analysis-codesearch.md),
[`analysis-zoekt.md`](./analysis-zoekt.md), [`analysis-fts5.md`](./analysis-fts5.md),
[`analysis-pg_trgm-gin.md`](./analysis-pg_trgm-gin.md), and [`research.md`](./research.md).
This spec carries the **contract**; those docs carry the evidence (`file:line`
citations).

## 2. Goals / Non-Goals

**Goals**

- A shared, code-oriented gram tokenizer (raw byte trigrams, single lowercase
  stream).
- A portable inverted-index storage model: `staging → flush → posting blocks`,
  minted once on the base `DatabaseFileSystem` so every backend inherits it.
- Transactional index maintenance on insert / edit / delete / re-chunk.
- Concrete per-document indexing limits.
- One index everywhere — **no `pg_trgm` as the index**.

**Non-Goals (out of scope)**

- The query path: candidate generation, regex→gram compilation, intersection
  SQL, content fetch, the Python final-match step, `_grep_impl` wiring, and
  removing/replacing any backend's existing query path. Read-time freshness
  *strategy* (when to flush vs. scan staging) is decided there too — but the
  minimal *read fold* a correct reader must compute is a storage contract (§4.5).
- A grep benchmark harness; replacing ripgrep/Python as the final authority.
- Fuzzy search, similarity, typo tolerance, ranking beyond candidate generation.
- Lexical/BM25/FTS token search; a custom search server.
- Indexing binary or invalid-text content as searchable code.
- Forcing identical physical SQL across backends.

## 3. Concepts & Glossary

| Term | Meaning |
|---|---|
| **gram** | A lowercase raw UTF-8 **byte trigram** (3-byte window), packed into a 24-bit `gram_key = (b0<<16)|(b1<<8)|b2`. |
| **doc_id** | A stable database auto-increment integer per `vfs_entries` row; the **integer key inside posting lists**. Distinct from the entity's `uuid`. |
| **entry_id** | The entry `uuid` (`vfs_entries.id`), carried on **every** staging row. Staging references this (known at write time); `doc_id` is resolved later. |
| **index_exclusion_reason** | Nullable marker on a `vfs_entries` row: `too_large \| binary \| high_cardinality \| null`. Non-null ⇒ the row's content is *not* in the index and a reader must fallback-scan it. Distinct from `index_content`, which a *chunked parent* also sets false (but with a `null` reason — skip, don't scan). |
| **staging (delta-log)** | An append-only log of `(gram, entry_id, action)` pending changes (`action ∈ {add, delete}`). The shipped MVP store. |
| **latest-action-wins (LAW)** | The fold of staging by the latest `seq` per `(gram_key, entry_id)` — the rule that resolves repeated changes to one current truth. |
| **posting block** | An immutable, compressed, sorted list of `doc_id`s for one gram. The durable index unit. |
| **flush** | Turning a closed staging batch into posting blocks. |
| **compaction** | Background, copy-on-write merge/re-encode of blocks that also applies pending deletes. |
| **filter-then-verify** | The index yields a candidate *superset*; the real regex verifies. False positives OK; false negatives forbidden. |

## 4. The Contract (normative)

### 4.1 Tokenizer

- The tokenizer MUST normalize before extraction:
  `CRLF/CR → \n`, then **NFC**, then Unicode **`casefold()`**, then UTF-8 encode,
  then emit **every 3-byte window**.
- It MUST include punctuation, whitespace, operators, path separators, and the
  bytes inside multibyte code points; it MUST dedupe grams per chunk.
- The index MUST be a **single lowercase stream** — no `gram_kind`, no raw-case
  stream. Case sensitivity is enforced by the final regex verify, never by the
  index.
- The tokenizer **API** MAY remain dual-mode (a `folded` parameter) so the query
  planner can fold a search *pattern*, but **index maintenance MUST extract with
  `folded=True`** — the stored index is folded-only. (The `code_grams.py`
  module docstring still describing a `gram_kind` raw+folded pair is stale and
  predates this contract; it should be corrected.)

### 4.2 Correctness invariants

- For every committed, **indexed** chunk, every distinct gram MUST be
  represented: the LAW fold over staging + posting blocks MUST equal the exact
  set of grams in the chunks currently present.
- False positives are allowed; a committed, indexed chunk's gram MUST NOT be
  missing (no false negatives).
- Chunks excluded by §4.3 MUST set a non-null **`index_exclusion_reason`** so a
  reader can distinguish them (fallback-scan) from *chunked parents* (skip —
  their content is covered by their chunk rows); both have `index_content =
  false`, so `index_content` alone is insufficient. This preserves the *overall*
  no-false-negative guarantee even though excluded chunks are not in the index
  (see §4.5).
- Maintenance MUST run in the **same transaction** as the chunk rows it
  describes.

### 4.3 Indexing limits

Content that is not worth indexing as code MUST be **excluded from the index
(not truncated) and marked with a non-null `index_exclusion_reason`**. Defaults
(benchmarked knobs):

| Limit | Default | Action on hit |
|---|---|---|
| Content size per file/chunk | **2 MiB** | exclude; `index_exclusion_reason = too_large` |
| Distinct grams per document | **20,000** | exclude; `index_exclusion_reason = high_cardinality` |
| NUL byte present (binary) | — | exclude; `index_exclusion_reason = binary` |
| Content < 3 bytes | — | not indexable (no trigram) |

### 4.4 Maintenance operations

- **Insert:** stage `add` for every distinct gram of the chunk.
- **Edit (path-stable file):** diff old/new grams; stage `old − new` deletes and
  `new − old` adds; the row's `doc_id` is unchanged.
- **Delete / re-chunk:** recompute the current grams **before** the row
  disappears, then stage `delete` deltas (carrying `doc_id`).
- Every backend MUST produce this one portable index through the shared path and
  MUST NOT produce or maintain a `pg_trgm`/FTS artifact *as* this index.

### 4.5 Storage-read contract

Query *execution* is out of scope (§2), but the no-false-negative guarantee
(§4.2) is only real if a reader folds staging over blocks. The storage therefore
exposes one minimal, normative read rule — distinct from query execution:

- A reader MUST resolve a gram's current doc-set as
  **`(∪ active posting blocks) ∪ (unapplied staged adds) − (unapplied staged
  deletes)`**, applying LAW per `(gram_key, entry_id)`.
- A reader MUST treat rows with a non-null `index_exclusion_reason` as **not
  represented** in the index, and fallback-scan them.

Everything above the candidate doc-set — regex→gram compilation, intersection,
ranking, content fetch, and the final regex verify — remains out of scope.

## 5. Design

Terse mechanism; rationale is in §7, evidence in the analysis docs.

### 5.1 Data model

All physical types are per-backend (§6); these are logical columns.

- **`vfs_entries.doc_id`** — auto-increment (`bigserial`/`IDENTITY`/rowid),
  assigned at insert, stable for the row's life; files and chunks share one space.
- **`vfs_entries.index_exclusion_reason`** — nullable enum
  (`too_large | binary | high_cardinality | null`). Non-null ⇒ excluded from the
  index, fallback-scan (§4.3, §4.5). Orthogonal to `index_content`: a chunked
  parent has `index_content = false` with a **null** reason (skip), an excluded
  chunk has a **non-null** reason (scan).
- **Staging:** `seq` (monotonic), `batch_id`, `gram_key`, `entry_id` (uuid, on
  **every** row), `doc_id` (nullable: resolved by join at flush for adds, carried
  at stage time for deletes — see §5.3), `action`, `applied_at`. **Folded by LAW
  per `(gram_key, entry_id)`** — `entry_id` is 1:1 with `doc_id`, so the fold is
  unambiguous and works before `doc_id` is resolved; `doc_id` is the block
  encoding key after resolution.
- **Posting block:** `gram_key`, `block_id`, `batch_id`, `doc_count`,
  `min_doc_id`, `max_doc_id`, `encoding`, `postings` (compressed sorted-doc_id
  blob), `is_active`.
- **Batch metadata:** `batch_id`, `status` (`Open→Closed→Flushing→Flushed/Failed`),
  timestamps.
- **Gram statistics:** `gram_key`, `doc_freq`, `block_count` (for rarest-first
  reads; consumed by the out-of-scope query path).

### 5.2 Write pipeline

```text
chunk write ──▶ staging deltas ──▶ flush ──▶ immutable posting blocks
   (txn)         (append-only)              ◀── compaction (background, CoW)
```

- **Stage** (in the chunk-write transaction): append `(gram_key, entry_id,
  action)` rows. Cheap, append-only, no ordering dependency on `doc_id`.
- **Flush** (background, size-triggered): close the batch; resolve `doc_id`
  (join `entry_id → vfs_entries` for adds; deletes already carry it); fold LAW;
  sort doc_ids; split into blocks bounded by **N doc_ids OR a byte budget,
  whichever first**; compress; write new blocks; retire superseded blocks
  (`is_active = false`). Mark delete deltas applied only once every block that
  could contain them is rewritten/retired.
- **Compaction** (background, single-flight, idempotent): merge a gram's blocks,
  apply pending deletes, re-encode, retire old. Triggered by block count or
  stale-doc_id ratio (§7 for defaults). Never inline with a write.

### 5.3 doc_id resolution, deletes, and edits

- Every staging row carries `entry_id`. **Adds** leave `doc_id` null and resolve
  it by join at flush (the row persists). **Deletes** carry **both** `entry_id`
  and the `doc_id` captured at stage time (a hard-deleted row is gone by
  compaction, so the join would fail). LAW folds by `(gram_key, entry_id)`,
  applied **at read** for the MVP delta-log and **at flush** for the
  posting-block target.
- `doc_id`s are **stable and never renumbered**. Deletes/re-chunks leave gaps;
  delta encoding only needs *sorted* ids, so gaps are tolerated. The only
  renumbering event is a rare **full reindex**.
- Blocks are **re-encoded at compaction, never patched in place**. Worked
  example — `def` in docs `[10,20,30]`, then doc 20 removed:

  ```text
  block (immutable): def → encode([10,20,30])
  stage delete:      (def, doc_id=20)                  ← pending
  read:              {10,20,30} − pending {20} = {10,30}   ✓
  compaction:        decode → drop 20 → re-encode [10,30]; retire old block
  ```

  Cost is O(grams changed) at write time; one bounded block re-encoded at
  compaction — never the whole index.

### 5.4 Posting-block compression

```text
sorted doc_ids → min_doc_id stored uncompressed (anchor)
              → delta (gap) encode the rest
              → varint (7-bit continuation)
              → optional zstd/gzip
```

The per-block `encoding` field lets the format evolve (Roaring / FOR / EWAH)
without migrating existing blocks. Start with delta+varint.

## 6. Phasing

| Phase | What ships | Status |
|---|---|---|
| **MVP (row store)** | A `{entries}_chunk_grams` delta-log keyed by `(gram_key, chunk_id)`; direct add/delete rows; proves tokenizer, maintenance, and no-false-negatives. | shipped (implementation.md) |
| **Target (posting blocks)** | `doc_id` column; `staging → flush → posting blocks`; background compaction; gram statistics. Minted on base `DatabaseFileSystem`; all backends inherit. | Phase 5 |

Backend physical-type mapping (behind the shared tokenizer + maintenance API):

| Backend | gram key | doc / entry ids |
|---|---|---|
| PostgreSQL | `bytea(3)` or `integer` | `bigserial` doc_id, `uuid` entry_id |
| MSSQL | `binary(3)` or packed `int` | `IDENTITY` doc_id, `uniqueidentifier`/`nvarchar(36)` entry_id |
| SQLite | `blob(3)` or `integer` | rowid doc_id, `text` entry_id |

## 7. Rationale & Alternatives

Each decision states the choice, the one-line why, and where it's validated.

- **Doc-level, not positional (vs. Zoekt).** Zoekt stores rune offsets so a
  substring needs only two list intersections, but that needs offset arithmetic
  over an mmap'd byte stream and costs ~3× size + a uint32 4 GB shard cap. A
  relational doc-set engine has no carrier for offset math. *(analysis-zoekt.md)*
- **Single lowercase stream, fold the index (vs. codesearch/Zoekt, which index
  raw case and fold the query).** Query-side case expansion is cheap only for
  positional ~2-list lookups; for VFS's doc-level many-trigram AND it would
  multiply the candidate set. Folding the index halves storage; the final regex
  enforces case. A two-sided trade; raw-case is worse for *this* engine.
  *(analysis-codesearch.md)*
- **Keep `uuid4` PK; add a local integer `doc_id`.** `uuid4` is client-generated
  and VFS relationships key on `path`, so the uuid carries little FK weight;
  posting lists need compact sorted integers only internally. Switching the
  global PK would forfeit client-side id generation for one subsystem's benefit.
- **Stable `doc_id`, never renumbered (vs. codesearch, which renumbers every
  merge).** codesearch can renumber because it rewrites the whole file offline;
  VFS is a live, mutable, multi-backend store. Sorted is mandatory; dense is only
  a compression bonus. *(analysis-codesearch.md)*
- **Immutable copy-on-write blocks (vs. GIN's in-place posting-tree deletion).**
  CoW avoids GIN's xid-marking/right-link concurrency protocol and metapage
  interlock; readers stay correct, recovery is trivial. *(analysis-pg_trgm-gin.md)*
- **`staging → flush → blocks` (vs. row-per-`(gram,doc)` forever or one mutable
  row per gram).** This is GIN's `fastupdate` pending list and FTS5's level-0
  segments — the proven log-structured model that decouples write cost from index
  size. *(analysis-fts5.md, analysis-pg_trgm-gin.md)*
- **No `pg_trgm` as the index.** Its tokenizer is word-oriented: pads words,
  drops punctuation, CRC-hashes multibyte grams — so `foo|bar` indexes as words
  `foo`,`bar`. *(analysis-pg_trgm-gin.md)*
- **Fixed 3-byte trigrams (vs. sparse/variable n-grams).** Trigrams are the
  proven default; sparse n-grams (Blackbird, Cursor) are the escape hatch if hot
  grams dominate storage. Deferred. *(research.md)*
- **Compaction defaults, grounded in FTS5/GIN (benchmarked knobs, not
  invariants):** merge fan-in **4**; compact a gram at **~16** active blocks or
  **~10%** stale doc_ids; bound a block by N doc_ids **or** a byte budget
  (~4 KB); size-trigger the flush (GIN's pending-list limit is 4 MB). Run
  everything **off the write path** — FTS5's inline `crisismerge` is the
  multi-hundred-ms-to-second stall this avoids. *(analysis-fts5.md,
  analysis-pg_trgm-gin.md)*

## 8. Risks

- **Storage growth / hot grams.** Raw byte grams (esp. whitespace/punctuation)
  produce huge posting lists. Mitigation: per-chunk dedup, the §4.3 unique-gram
  ceiling, byte-budgeted compressed blocks; sparse n-grams as the future escape
  hatch.
- **Case-sensitive candidate breadth.** The single lowercase stream broadens
  case-sensitive candidates. Mitigation: the regex verify enforces case; a
  raw stream can be added later via `index_id` namespacing if benchmarks demand.
- **Write amplification.** Compaction rewrites a doc's blocks when it folds in
  changes touching them. Mitigation: tune cadence/block size; keep it background.
- **doc_id density decay.** Gaps from deletes/re-chunks slowly worsen
  compression. Mitigation: graceful (sorted still holds); rare full reindex
  re-densifies.
- **Write latency.** Per-write gram maintenance costs work. Mitigation:
  append-only staging; O(grams changed) per edit, independent of corpus size.

## 9. Decision Log

- **2026-05-13** — Single lowercase (casefold) stream; no `gram_kind`, no
  raw-case stream.
- **2026-05-24** — Index production + maintenance live on the base
  `DatabaseFileSystem`; all backends inherit; no per-backend adapter sequence.
- **2026-05-24** — Story scoped to *producing* the index; querying it is
  out of scope.
- **2026-05-24** — `pg_trgm` is not the index (word-oriented model wrong for
  code).
- **2026-05-25** — Keep `uuid4` as the entity PK; add a separate auto-increment
  `doc_id` as the posting-list key; stage by `uuid`, resolve `doc_id` at flush
  for adds and at stage time for deletes; `doc_id` stable, never renumbered.
- **2026-05-25** — Adopt concrete indexing limits (2 MiB / 20,000 grams / NUL /
  <3 B); excluded chunks are flagged for query-path fallback.
- **2026-05-25** — Compaction/flush defaults grounded in FTS5/GIN; jobs are
  background, single-flight, idempotent; blocks re-encoded, never patched.
- **2026-05-25** — Contract tightenings from review: (a) a dedicated
  `index_exclusion_reason` replaces the overloaded `index_content` flag for
  exclusion (chunked-parent vs. excluded are now distinguishable); (b) staging
  carries `entry_id` on every row and LAW folds by `(gram_key, entry_id)`
  (deletes also carry `doc_id`); (c) index maintenance extracts folded-only even
  though the tokenizer API stays dual-mode; (d) added a minimal §4.5
  storage-read contract so the no-false-negative guarantee is well-defined while
  query execution stays out of scope.
- **2026-05-25** — **Index unit is the chunk.** A file small enough to fit one
  chunk stays a single indexed `file` row; a larger file flips
  `index_content=False` on chunking (`models.py:595`) and is indexed via its
  `chunk` rows. Bounds verify-fetch and shares the `index_content` row set with
  the vector index. (Resolves former Open Question 1.)
- **2026-05-25** — **Versions/snapshots are not content-indexed.**
  `index_content` defaults `True` only for `kind ∈ {file, chunk}`
  (`models.py:689-690`); `kind="version"` rows default `False`. So there is no
  redundant-version posting bloat and no need for Zoekt branch-mask dedup —
  reopens only if version rows ever become content-indexed. (Resolves former
  Open Question 3.)
- **2026-05-25** — **Fixed 3-byte trigrams for v1.** Sparse/variable-length
  n-grams (Blackbird, Cursor) are deferred, benchmark-gated on hot-gram storage
  pressure — a decision-with-a-trigger, not an open fork.

## 10. Deferred Options (decided, non-blocking)

No design questions are currently open. The following are decided deferrals,
each with a clear reopening trigger:

1. **Sparse / variable-length n-grams** — reopen if benchmarks show hot-gram
   storage or selectivity is the bottleneck (Blackbird, Cursor).
2. **A second raw-case gram stream** — reopen if case-sensitive candidate breadth
   dominates; addable via `index_id` namespacing without a schema migration.
3. **Multi-version / snapshot dedup** (Zoekt branch-mask style) — reopen only if
   `kind="version"` rows are ever made content-indexed.

## 11. References

**Source repos reviewed (cloned 2026-05-25), with this story's analyses:**

- `google/codesearch` — doc-level trigram index (closest match) —
  [`analysis-codesearch.md`](./analysis-codesearch.md)
- `sourcegraph/zoekt` — positional, sharded trigram search —
  [`analysis-zoekt.md`](./analysis-zoekt.md)
- SQLite `ext/fts5/` — LSM segments + trigram tokenizer (a target backend) —
  [`analysis-fts5.md`](./analysis-fts5.md)
- PostgreSQL `pg_trgm` + GIN — pending-list staging + posting model —
  [`analysis-pg_trgm-gin.md`](./analysis-pg_trgm-gin.md)

**External:**

- Russ Cox, *Regex Matching with a Trigram Index*:
  https://swtch.com/~rsc/regexp/regexp4.html
- Sourcegraph Zoekt: https://github.com/sourcegraph/zoekt
- GitHub Blackbird:
  https://github.blog/2023-02-06-the-technology-behind-githubs-new-code-search/
- PostgreSQL `pg_trgm`: https://www.postgresql.org/docs/current/pgtrgm.html
- SQLite FTS5: https://sqlite.org/fts5.html
- SQL Server Full-Text Search:
  https://learn.microsoft.com/en-us/sql/relational-databases/search/full-text-search
- Cursor, *Fast regex search* (sparse n-grams):
  https://cursor.com/blog/fast-regex-search
- Manning, Raghavan & Schütze, *Introduction to Information Retrieval*, ch. 4
  (SPIMI/BSBI) & §2.3 (skip pointers): https://nlp.stanford.edu/IR-book/
- Apache Lucene segment management & merging:
  https://deepwiki.com/apache/lucene/2.4-segment-management-and-merging
- hexops, empirical `pg_trgm` at scale:
  https://github.com/hexops-graveyard/pgtrgm_emperical_measurements
