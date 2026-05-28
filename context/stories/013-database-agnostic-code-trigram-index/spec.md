# 013 — Database-Agnostic Code Trigram Index

- **Status:** draft
- **Date:** 2026-04-24 (restructured 2026-05-25; posting-list model simplified
  2026-05-27; triage pass 2026-05-27; index-pipeline reframe 2026-05-28)
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
- A portable inverted-index storage model: `staging → compile → one posting-list
  row per gram`, minted once on the base `DatabaseFileSystem` so every backend
  inherits it.
- A **three-phase index pipeline** — **chunk → encode → compile** (§4.6) — run as
  a server-side reconciliation, each phase idempotent and independently runnable.
  Index maintenance on insert / edit / delete / re-chunk is content-addressed
  **chunk reconciliation** (grams are never diffed); inline phases share the
  write transaction.
- Index maintenance exposed through a server-side **capability** (a
  `SupportsIndexMaintenance` protocol), never a client/MCP verb — a client cannot
  trigger indexing.
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
- **Full reindex** (renumbering doc_ids / rebuilding every posting row from
  source): named here as the only doc_id-renumbering event, but its procedure is
  deferred — see §10.

## 3. Concepts & Glossary

| Term | Meaning |
|---|---|
| **gram** | A lowercase raw UTF-8 **byte trigram** (3-byte window), packed into a 24-bit `gram_key = (b0<<16)|(b1<<8)|b2`, stored as a signed `integer` (range 0–16,777,215). |
| **doc_id** | `vfs_entries.id` — the row's **integer auto-increment primary key**, which *is* the posting-list key (dense, sorted, stable). Distinct from the entity's `uuid`, which lives in `entry_id`. |
| **entry_id** | The entry `uuid` (`vfs_entries.entry_id`), carried on **every** staging row. Known at write time; `doc_id` is resolved later (§5.3). |
| **chunk** | The index unit. **Every** indexed document is chunked (even into a single chunk); only `kind="chunk"` rows are content-indexed. |
| **index_exclusion_reason** | *(Removed 2026-05-28, §4.3.)* A former chunk-row marker for content excluded by per-chunk limits. Chunk-all + size-bounded chunks make those limits unreachable, so the column and the excluded/fallback-scan state are gone; `index_content` alone classifies a row (§4.2). |
| **staging (delta-log)** | A **transient**, append-only log of `(gram_key, entry_id, doc_id?, action)` pending changes (`action ∈ {add, delete}`). Rows are deleted once a flush folds them, so "present in staging" == "not yet flushed". |
| **latest-action-wins (LAW)** | The fold of staging by the latest `seq` per `(gram_key, entry_id)` — resolves repeated changes to one current truth. `seq` is a monotonic, insertion-ordered autoincrement (verified across SQLite/Postgres/MSSQL). |
| **posting list** | **One row per gram**: the gram's complete sorted `doc_id` set in a single `postings` blob. The durable index unit. A gram with no docs has **no row** (a missing row ≡ the empty set). |
| **flush** | The fold of staged deltas into the per-gram posting-list rows — capture a `seq` watermark, LAW-fold rows ≤ it, apply to each touched row with idempotent set semantics, then delete the folded staged rows. This is the **compile** phase (§4.6); global single-flight, one transaction; run deferred (off the write path) or inline post-persist on the shared write session. |
| **index pipeline** | The three-phase, server-side maintenance reconciliation (§4.6): **chunk** (split files), **encode** (chunk grams → staging + embedding), **compile** (fold staging → posting list). `index()` runs all three; each is independently runnable and idempotent. Not a client/MCP verb. |
| **chunk watermark** | A durable per-file marker (the file's `content_hash` recorded at last chunking) that drives the **chunk** phase: a file whose current `content_hash` differs is (re)chunked. Mirrors `indexed_content_hash` for the **encode** phase. |
| **encoding** | The per-row tag naming how `postings` is packed (`delta+varint`, `delta+gamma`, `roaring`). v1 implements `delta+gamma` only; the tag lets the format evolve per gram without migration. |
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
  represented: the LAW fold over staging + the posting list MUST equal the exact
  set of grams in the chunks currently present.
- False positives are allowed; a committed, indexed chunk's gram MUST NOT be
  missing (no false negatives).
- Under chunk-all (§4.3, §4.4) every indexable row is a size-bounded chunk, so
  there is **no excluded-chunk state** and `index_content` alone is sufficient:

  | `index_content` | meaning | reader does |
  |---|---|---|
  | true | indexed chunk | use the index |
  | false | chunked parent (covered by its chunk rows) | skip |

  The earlier `index_exclusion_reason` column and its 4-state truth table were
  dropped (§4.3, decision log) because bounded chunks make the per-chunk limits
  unreachable. No row is ever both committed-indexed and absent from the index,
  so the no-false-negative guarantee holds without a fallback-scan case.
- Maintenance MUST run in the **same transaction** as the chunk rows it
  describes — in particular, a staged **add** and the `vfs_entries` row it
  references MUST commit together.
- **Single-session / single-writer execution model (v1).** All reads, writes,
  and the flush execute in a **single session**, serialized — there is no
  concurrent second writer and never a second flush in flight. This makes the
  §4.5 read fold snapshot-consistent and satisfies the flush's single-flight
  premise (§5.2) without an explicit cross-process lock. Concurrent multi-worker
  flush/write is **out of scope** and deferred (§10); the reopening trigger is a
  multi-process deployment, at which point a cross-process flush lock becomes
  load-bearing (the exact-folded-`seq` deletion of §5.2 already covers the rest).
- `seq` MUST be insertion-order-monotonic on every backend (verified for
  SQLite / Postgres / MSSQL under the Core bulk-insert path); LAW relies on it.

### 4.3 Indexing limits

The index unit is the **chunk** (§4.4). Under chunk-all every indexable document
is split into **size-bounded** chunks by the splitter (default ≤ 2048 chars,
char-fallback hard-cuts even an unsplittable oversized line), so the original
per-chunk limits — 2 MiB content, 20,000 distinct grams — **can never fire**.
They, the `index_exclusion_reason` column, the 4-state truth table, and the
exclusion branch have therefore been **dropped** (decision log; landed in code).
A chunk is always either indexed or carried forward; there is no excluded,
fallback-scanned chunk. (A custom `split_content` override that emits oversized
chunks is the override's responsibility; v1's default splitter cannot.)

Two limit-like rules remain, enforced at write time rather than as exclusions:

- **NUL / binary content is rejected at write time** by the model validator
  (`models.py`), so it never reaches the index — there is no `binary` state to
  represent.
- **Sub-3-byte content** produces no trigram, so VFS **does not create a chunk
  for it**. This is not a false-negative hole: a grep *pattern* under 3 bytes
  cannot use the index either and MUST full-scan content (where it finds such
  files), and a pattern ≥3 bytes cannot match a <3-byte file.

### 4.4 Maintenance operations — chunk reconciliation

This is the **chunk** and **encode** phases (§4.6) at the data level: the chunk
phase reconciles a document's chunk set, the encode phase stages the resulting
gram adds/deletes.

**Every indexable (≥3-byte) document is chunked; only `kind="chunk"` rows are
content-indexed; grams are never diffed.** Content under 3 bytes produces no
chunk and is not content-indexed at all (§4.3). A write reconciles the document's
*new* chunk set against its *existing* chunk set by **content hash** (the
tie-break for duplicate-content chunks within one file is a deferred detail):

- **Matched** (a new chunk's content equals an existing chunk's): **carry the
  existing chunk forward** — keep its `entry_id` and `doc_id`, stage **no** gram
  deltas (identical content ⇒ identical grams). Carry-forward is an `UPDATE` of
  the existing row's positional metadata (`path`, line range); its
  `id`/`entry_id`/grams survive. Chunk paths are version-namespaced and
  stale-version rows are deleted before new-version rows insert, so paths never
  collide during the reconcile.
- **New** (no existing chunk matches): create a new chunk entry (fresh
  `entry_id`; `doc_id` assigned at persist) and stage **all-adds** for its grams.
- **Unmatched existing** (an existing chunk has no match in the new set): delete
  the chunk entry and stage **all-deletes** (carrying its `doc_id`).

There is no per-chunk exclusion step: chunks are size-bounded (§4.3), so every
new chunk is indexed and every carried-forward chunk keeps its grams. A content
change always produces a *new* chunk (new `entry_id`, fresh grams) reconciled
against the old, so there is no separate "edit" transition to special-case.

Consequences:

- **Insert / edit / re-chunk** are all the same reconciliation; there is no
  gram-level diff and no "path-stable edit" special case.
- **Delete** a document ⇒ delete all its chunks ⇒ stage all-deletes for each.
- **Move / rename** ⇒ content and grams unchanged, `doc_id` stable ⇒ **no gram
  maintenance** (positional metadata only).
- **Copy** ⇒ a new entity with new chunk entries ⇒ stage **all-adds** (like
  insert).
- The old chunks' grams MUST be captured **before** their rows disappear: the
  reconcile snapshots existing chunk content up front, so staging the deletes
  does not depend on the rows still existing.
- Every backend MUST produce this one portable index through the shared path and
  MUST NOT produce or maintain a `pg_trgm`/FTS artifact *as* this index.

### 4.5 Storage-read contract

Query *execution* is out of scope (§2), but the no-false-negative guarantee
(§4.2) is only real if a reader folds staging over the posting list. The storage
therefore exposes one minimal, normative read rule — distinct from query
execution:

- A reader MUST resolve a gram's current doc-set as
  **`(the gram's posting-list row, or ∅ if no row exists) ∪ (unflushed staged
  adds) − (unflushed staged deletes)`**, applying LAW per `(gram_key,
  entry_id)`. "Unflushed" means staging rows visible in the reader's snapshot
  (rows are deleted by the flush that folds them, §5.2).
- A reader uses `index_content` to decide coverage (§4.2): `true` ⇒ an indexed
  chunk, use the index; `false` ⇒ a chunked parent, skip (its chunk rows cover
  it). There is no excluded/fallback-scan case under chunk-all.

Everything above the candidate doc-set — regex→gram compilation, intersection,
ranking, content fetch, and the final regex verify — remains out of scope.

### 4.6 The index pipeline & server boundary

Index maintenance is a **server-side reconciliation**, not a client operation.
It decomposes into three idempotent, independently-runnable phases, each driven
by comparing a durable marker against current state:

| Phase | Driver (compare → act) | Output |
|---|---|---|
| **chunk** | a file's `content_hash` ≠ its chunk watermark → (re)chunk | `kind="chunk"` rows; the file's `index_content` flips false |
| **encode** | a chunk's `indexed_content_hash` ≠ its `content_hash` → extract folded grams + embedding | staging delta-log rows (`doc_id` null on adds) + `embedding`; sets the chunk's watermark |
| **compile** | staging rows ≤ a `seq` watermark → LAW-fold into posting rows | one posting-list row per touched gram; the folded staging rows are deleted |

`index()` = run **chunk → encode → compile** over a scope. Each phase is also
callable alone. The phases are idempotent because each re-derives its work from
durable state (watermarks, the delta-log), so a re-run after a crash or a
partial pass converges — there is no batch state machine.

**Server boundary.** `index` and its phases are **not** part of the
client-facing surface (the verbs that become MCP tools: read/write/ls/grep/…). A
client never triggers indexing; the **server or an ETL pipeline** drives it.
Index-bearing backends expose the phases through a narrow maintenance capability
(a `SupportsIndexMaintenance` protocol) that the base `VirtualFileSystem` does
**not** define; backends without an index simply do not implement it. This keeps
the client contract clean and makes "maintains an index" an explicit, checkable
capability rather than an inherited no-op.

**Inline vs. deferred is policy, not structure.** A `DatabaseFileSystem` carries
three independent switches — `auto_chunk`, `auto_encode`, `auto_compile` — that
select which phases run **inline on `write()`** versus deferred to a server/ETL
reconcile pass. There is deliberately **no `auto_index` flag**: `index` names the
whole pipeline, so a per-phase flag must not share the name. (`encode` here means
"encode a chunk's content into its index representations — grams and vector"; it
is a different layer from the posting codec's byte encoding in §5.4.)

**Atomicity of inline phases.** When a phase runs inline it **shares the write's
session and transaction**, so the whole write commits or rolls back as a unit.
The inline order is:

```text
chunk → encode (deltas, doc_id null) → persist (flush assigns vfs_entries.id)
      → compile (fold; resolves doc_id via entry_id→id join) → single commit
```

`compile` runs **after** persist on purpose: the fold's add-resolution join
needs the auto-increment `id`s that the persist flush assigns (§5.3). Keeping it
in the same transaction preserves the no-false-negative guarantee (§4.2) across a
crash — a failed compile rolls back the whole write, never a half-folded index.
The deferred/batch path runs the same phases over watermark-dirty rows in their
own sessions when the corresponding inline flag is off.

## 5. Design

Terse mechanism; rationale is in §7, evidence in the analysis docs.

### 5.1 Data model

Two tables (`GramStaging` + `GramPostingList`) plus identity and index-state
columns on `vfs_entries`. Physical types are pinned below and per-backend in §6.

- **`vfs_entries.id` (= `doc_id`)** — the integer auto-increment **primary key**,
  mapped to each backend's native auto-increment (rowid / `BIGSERIAL` /
  `BIGINT IDENTITY`); it *is* the posting-list `doc_id`. On **SQLite the PK MUST
  be declared `AUTOINCREMENT`** (`sqlite_autoincrement=True`) to prevent rowid
  **reuse** after deletes (Postgres/MSSQL never reuse). `id` is `None` until the
  persist flush; pre-persist identity uses `entry_id`.
- **`vfs_entries.entry_id`** — the client-generated `uuid4`, unique, indexed
  (`varchar(36)`). Carries identity before `id` exists.
- **`vfs_entries.index_content`** — boolean; `true` ⇒ this row's content is
  indexed (a chunk), `false` ⇒ chunked parent, skip (§4.2).
- **Phase watermarks** — `indexed_content_hash` drives the **encode** phase (a
  chunk re-encodes when its `content_hash` differs), and a **chunk watermark**
  (the file's `content_hash` at last chunking) drives the **chunk** phase (§4.6).
  The dropped `index_exclusion_reason` column is gone (§4.3).

```python
class GramStaging:
    seq       # bigint autoincrement PRIMARY KEY; monotonic; orders the LAW fold
    gram_key  # integer (packed 24-bit trigram), NOT NULL
    entry_id  # varchar(36) — vfs_entries.entry_id (uuid), NOT NULL
    doc_id    # bigint — vfs_entries.id; NULL on adds (joined at flush), set on deletes
    action    # smallint — 1 = add, 0 = delete; NOT NULL
    # indexes: (gram_key, entry_id, seq) for the fold; (entry_id) for delete-cascade

class GramPostingList:
    gram_key   # integer PRIMARY KEY — one row per gram; a gram with 0 docs has NO row
    postings   # blob — the gram's full sorted doc_id set, delta+gamma encoded (§5.4)
    encoding   # smallint — 1=delta+varint, 2=delta+gamma, 3=roaring; v1 writes only 2
    doc_count  # integer — number of doc_ids in postings; INVARIANT: == count(decode(postings))
    byte_size  # integer — len(postings); storage view + §10 hot-gram trigger signal
```

- **Staging is transient** — the flush deletes rows once folded, so there is no
  batch-lifecycle table; "present in staging" == "not yet flushed". `action`
  uses `1=add / 0=delete`.
- **`postings` physical type** is `bytea` (PG) / `varbinary(max)` (MSSQL) /
  `blob` (SQLite). There is **no MVP size ceiling**: the row uses **default
  storage** (PG TOAST / MSSQL LOB off-row / SQLite overflow) — *not*
  `STORAGE PLAIN` — so a hot gram's blob may grow large; `byte_size` is the
  signal that triggers the deferred §10 hot-gram paging.
- **Gram tables are un-scoped** (no `owner_id`/tenant column). One posting row
  per gram is **global**; tenant/path scope is enforced solely by the
  post-candidate **join to `vfs_entries`** (which is mandatory for content fetch
  anyway). A posting row therefore carries no tenant boundary — a deliberate,
  stated assumption.

This is **two tables**, not the earlier four (`posting_blocks` / `gram_batches` /
`gram_stats`): transient staging removes the batch table, `doc_count` folds in
the only needed statistic, and one row per gram removes the block/segment
machinery. Hot-gram paging (§10) reintroduces multiple rows per gram only for
the grams that need it.

### 5.2 Write pipeline

These are the **encode** and **compile** phases of §4.6 at the storage level;
whether they run inline (one shared transaction) or deferred (server/ETL) is the
policy decided there.

```text
chunk ──▶ encode ──────────────▶ compile ──▶ one posting-list row per gram
(phase 1) (phase 2: staging       (phase 3: the flush)
           deltas + embedding)
```

- **Encode** (phase 2; in the chunk-write transaction when inline): bulk-insert
  `(gram_key, entry_id, action)` rows for the reconciliation's adds/deletes
  (§4.4) and compute the chunk's embedding. Cheap, append-only, no ordering
  dependency on `doc_id`. Use a Core bulk `insert()`, not per-row ORM `add`
  (~50× faster on SQLite — see implementation notes).
- **Compile** (phase 3 — the flush; **global single-flight**, **one
  transaction**, size/time-triggered when deferred, or post-persist on the
  shared session when inline):
  1. Capture a `seq` **watermark** = `max(seq)` of current staging.
  2. Read staging rows with `seq ≤ watermark`; **LAW-fold first** (latest action
     per `(gram_key, entry_id)`), then resolve `doc_id` only for the surviving
     **adds** (join `entry_id → vfs_entries.id`; deletes already carry it). If a
     surviving add's join **misses** — the entry was hard-deleted after its add
     was staged but before this flush (a normal add-then-delete across two flush
     windows) — **drop the add**: the doc is gone, and its later delete delta is a
     harmless no-op, so the net result is correct.
  3. For each touched gram: decode its `postings` (or start empty if no row),
     apply the folded adds/deletes with **idempotent set semantics**
     (delete-of-absent and add-of-present are both no-ops), re-encode, refresh
     `doc_count`/`byte_size`, and `UPDATE` the row — asserting
     `doc_count == len(decode(postings))` as a free invariant check — or
     **DELETE the row** if the gram now has zero docs.
  4. `DELETE` the **exact set of staged rows folded** in step 2 (by their `seq`
     values) — not a `seq ≤ watermark` range. Under the single-session model
     (§4.2) the two coincide, but deleting only the folded `seq`s keeps the flush
     correct even if a future multi-writer deployment lets a lower `seq` commit
     after the watermark read.

  Rows not folded by this flush survive to the next one, so a write is never
  lost. Because steps 3–4 share one transaction and the fold is set-idempotent, a
  crashed/re-run flush re-derives the same result — there is no separate
  compaction step; with one row per gram the flush *is* the rebuild. Single-flight
  follows from the §4.2 single-session model (never a second concurrent flush, so
  no two writers race a read-modify-write on one row); a cross-process lock is
  deferred to the multi-worker case (§10).

### 5.3 doc_id resolution, deletes, and edits

- Every staging row carries `entry_id`. **Adds** leave `doc_id` null and resolve
  it by join at flush (the `vfs_entries` row persists, committed in the same
  transaction as the add — §4.2). **Deletes** carry **both** `entry_id` and the
  `doc_id` captured at stage time (a hard-deleted row is gone by flush, so the
  join would fail). LAW folds by `(gram_key, entry_id)`, applied **at read** for
  staging and **at flush** into the posting-list row.
- `doc_id`s are **stable and never renumbered**. Deletes/re-chunks leave gaps;
  delta encoding only needs *sorted* ids, so gaps are tolerated. SQLite's
  `AUTOINCREMENT` PK (§5.1) prevents rowid reuse, so a stale staged delete can
  never collide with a re-handed-out id. The only renumbering event is a **full
  reindex** (deferred, §10).
- The posting-list row is **re-encoded by the flush, never patched in place**.
  Worked example — `def` in docs `[10,20,30]`, then doc 20 removed:

  ```text
  posting row:   def → encode([10,20,30])
  stage delete:  (def, doc_id=20)                      ← pending in staging
  read:          {10,20,30} − pending {20} = {10,30}   ✓
  flush:         decode → drop 20 → re-encode [10,30]; UPDATE the def row
                 (if the gram emptied, DELETE the row instead)
  ```

  Cost is O(grams changed) at write time (staged deltas only); the flush rewrites
  one row per touched gram — never the whole index.

### 5.4 Posting-list encoding

v1 implements **`delta+gamma` only**, applied to every gram, **ported from Google
`codesearch`'s exact byte format** (`index/delta.go`, `index/read.go`). The
posting blob is the delta-list portion of codesearch's posting list (the
`gram_key` is the row key, not in the blob):

```text
doc_ids sorted ascending → gamma-coded gaps:
  • first gap = firstID − (−1)  (i.e. firstID + 1); lastID starts at −1
  • each subsequent gap = id − prevID
  • terminate with a trailing ZERO delta
  • Elias-γ cannot encode 0, so remap EVERY value (gaps AND the terminator):
    0 → 16, and any v ≥ 16 → v+1 (deltaZeroEnc = 16, index/delta.go:31 —
    NOTE index/read.go's "31" comment is STALE; follow delta.go)
  • bits are LSB-first within each byte; flush the partial byte at end-of-blob
```

There is **no separate `min_doc_id` anchor** — codesearch frames the whole list
as one gamma gap-stream from −1 with a trailing zero terminator, and VFS adopts
that verbatim (so `delta.go`'s `writeBits`/`next64` and the zero-remap port
directly). **Decode is count-bounded with a terminator assert:** read exactly
`doc_count` ids, then assert the trailing remapped-zero terminator (detects
truncation/corruption), matching codesearch's reader (`index/read.go`). Empty
list ⇒ no row (§5.1). Worked examples:
- codesearch's, **0-based** fileids: delta list `[2,5,1,1,0]` → `1,6,7,8`.
- VFS, **1-based** doc_ids `[10,20,30]`: from `lastID=−1` the gaps are
  `[11,10,10,0]` (the trailing `0` is the terminator, remapped to `16` before
  γ-coding).

The per-row `encoding` tag lets the format evolve **per gram** without a
migration: each row stays readable under its own tag. `delta+varint` and
`roaring` are **defined but unimplemented** values:

- `delta+varint` — byte-aligned, easy-to-debug fallback, available if a gram ever
  needs it.
- `roaring` — the intended **hot-gram, query-path** encoding. Its win is
  compressed-bitmap *intersection at query time* (out of scope here), not
  storage, so it is built and measured with the query story (§10), not now.

Evidence the upgrade path is real: `codesearch` shipped delta+varint (v1) then
moved to Elias-γ (v2), measuring a **>40% total index-size cut** on the Linux
kernel and a posting-list reduction of **132.7 GB → 80.3 GB** on 1.6 TB of Go
modules (`index/read.go:110-144`).

## 6. Phasing

| Phase | What ships | Status |
|---|---|---|
| **MVP (row store)** | A `{entries}_chunk_grams` delta-log keyed by `(gram_key, entry_id)`; direct add/delete rows; proves tokenizer, maintenance, and no-false-negatives. | shipped |
| **Target (posting list)** | Two-table `staging → compile → one posting-list row per gram` (`gram_key`, `postings`, `encoding`, `doc_count`, `byte_size`); `delta+gamma` codec; chunk-reconciliation maintenance. Minted on base `DatabaseFileSystem`; all backends inherit. | tables + codec landed |
| **Pipeline (this work)** | The three-phase `index()` (§4.6): the **compile** fold; `auto_chunk`/`auto_encode`/`auto_compile`; inline phases on the shared write session (compile post-persist); the `SupportsIndexMaintenance` capability + batch phases; the file chunk watermark. | in progress |

> **Implementation note:** the four-table block model and the
> `index_exclusion_reason` exclusion model have been **dropped** (collapsed to two
> tables; chunk-all makes the §4.3 limits unreachable). The `delta+gamma` codec is
> landed (`src/vfs/postings.py`, byte-verified against codesearch). Remaining: the
> compile fold, the three `auto_*` flags + inline session wiring, and the
> capability protocol (§4.6).

Backend physical-type mapping (behind the shared tokenizer + maintenance API):

| Column | PostgreSQL | MSSQL | SQLite |
|---|---|---|---|
| `gram_key` | `integer` | `int` | `integer` |
| `doc_id` (`vfs_entries.id`) | `bigserial` PK | `bigint IDENTITY` PK | `integer PRIMARY KEY AUTOINCREMENT` |
| `entry_id` | `uuid` or `varchar(36)` | `varchar(36)` | `text` |
| `seq` (staging) | `bigserial` | `bigint IDENTITY` | `integer` (rowid) |
| `postings` | `bytea` (default/TOAST storage) | `varbinary(max)` | `blob` |

`entry_id` MUST match the type used on `vfs_entries` (`varchar(36)`) so the flush
join is an index seek, not a per-row coercion. `seq` monotonicity under the Core
bulk-insert path is **verified** on all three (SQLite/Postgres via the bulk-insert
learning; MSSQL via a 50,000-row `IDENTITY` check, zero inversions).

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
- **`doc_id` IS the integer auto-increment PK; `uuid` moved to `entry_id`.**
  Posting-list compression needs compact *sorted integers*; a second
  auto-increment column is not portable (SQLite auto-increments only the
  `INTEGER PRIMARY KEY`; MSSQL allows one `IDENTITY` per table). Making the single
  PK that integer sidesteps both, and the client-side `uuid4` (which carries no
  FK weight — VFS keys on `path`) moves to `entry_id`. *(reverses the earlier
  "keep uuid4 PK + add a separate doc_id" plan.)*
- **Stable `doc_id`, never renumbered (vs. codesearch, which renumbers every
  merge).** codesearch can renumber because it rewrites the whole file offline;
  VFS is a live, mutable, multi-backend store. Sorted is mandatory; dense is only
  a compression bonus. SQLite `AUTOINCREMENT` closes the rowid-reuse gap so
  "stable" holds literally. *(analysis-codesearch.md)*
- **One posting-list row per gram, rebuilt in place by the flush (vs. multiple
  immutable blocks per gram).** Staging absorbs all write traffic, so the durable
  row is rewritten only at flush time, off the write path; the backend's MVCC
  hands readers a consistent prior version during the rewrite, and global
  single-flight means no two writers race one row — so no `is_active` flag or
  block-level concurrency protocol is needed. This matches `codesearch`'s
  one-list-per-gram shape (`index/read.go:31-44` — it never splits a gram's list;
  its 256-byte "blocks" index the *lookup table*, not the lists) without
  codesearch's offline whole-file rebuild — staging is VFS's mutable substitute.
  The one cost it accepts — rewriting a gram's whole row even for a small change —
  is bounded for normal grams and deferred to the hot-gram optimization (§10) for
  the rest. *(analysis-codesearch.md, analysis-pg_trgm-gin.md)*
- **Content-addressed chunk reconciliation; grams never diffed.** All docs are
  chunked and only chunks are indexed, so re-chunk is a set reconciliation by
  content: matched chunks carry `entry_id`/`doc_id` forward (zero gram work),
  new chunks all-add, unmatched old chunks all-delete. This makes a carried chunk
  cost nothing, keeps every staged `(gram_key, entry_id)` to a single action
  direction (so LAW never has to merge an add and a delete under one entry_id),
  and removes the fragile gram-diff path entirely.
- **`staging → flush` in front of the durable store (vs. row-per-`(gram,doc)`
  forever, or maintaining the posting list inline on every write).** The
  append-only delta-log is GIN's `fastupdate` pending list and FTS5's level-0
  segments — the proven log-structured model that decouples write cost from index
  size. It is also what makes one mutable row per gram affordable: the classic
  objection to that shape is the per-write rewrite cost, and staging removes it by
  deferring the rewrite to a batched background flush.
  *(analysis-fts5.md, analysis-pg_trgm-gin.md)*
- **Flush is transactional, watermarked, single-flight, set-idempotent.** Capture
  a `seq` ceiling, fold/apply/clear ≤ it in one transaction; rows staged during
  the flush survive. Idempotent set semantics (delete-of-absent / add-of-present
  are no-ops) plus the single transaction make a re-run after a crash safe with no
  batch state machine.
- **No `pg_trgm` as the index.** Its tokenizer is word-oriented: pads words,
  drops punctuation, CRC-hashes multibyte grams — so `foo|bar` indexes as words
  `foo`,`bar`. *(analysis-pg_trgm-gin.md)*
- **Fixed 3-byte trigrams (vs. sparse/variable n-grams).** Trigrams are the
  proven default; sparse n-grams (Blackbird, Cursor) are the escape hatch if hot
  grams dominate storage. Deferred. *(research.md)*
- **`delta+gamma` only for v1, ported from codesearch exactly (vs. selecting per
  gram, or shipping varint first).** codesearch's v2 is "gamma everywhere" and
  still won >40%; per-gram selection buys little because cold grams are negligible
  bytes. Porting the exact byte format (zero-remap 16, trailing-zero terminator,
  gap-from-−1) reuses `delta.go` directly and avoids two implementers producing
  incompatible blobs. *(analysis-codesearch.md, `index/delta.go`, `index/read.go`)*
- **Flush cadence, grounded in FTS5/GIN (benchmarked knobs, not invariants):**
  size- or time-trigger the background flush (GIN's pending-list limit is 4 MB);
  run it single-flight and idempotent, **off the write path** — FTS5's inline
  `crisismerge` is the multi-hundred-ms-to-second stall this avoids. With one row
  per gram there is no block fan-in or block-count threshold to tune.
  *(analysis-fts5.md, analysis-pg_trgm-gin.md)*
- **Query latency over build/flush cost.** The background flush absorbs build work
  off the user-facing write, so the durable format may be chosen for query speed
  (e.g. `roaring` for hot grams) rather than cheapest build.

## 8. Risks

- **Storage growth / hot grams.** Raw byte grams (esp. whitespace/punctuation)
  produce huge posting lists, and one row per gram means a hot gram is one large
  blob. Mitigation: per-chunk dedup, the §4.3 unique-gram ceiling, `encoding`
  (gamma collapses a near-universal gram's run of 1-gaps to a fraction of varint
  size), and default TOAST/LOB storage. The deferred hot-gram paging optimization
  (§10, triggered off `byte_size`) and sparse n-grams are the future escape
  hatches if a few grams still dominate.
- **Case-sensitive candidate breadth.** The single lowercase stream broadens
  case-sensitive candidates. Mitigation: the regex verify enforces case; a
  raw stream can be added later via `index_id` namespacing if benchmarks demand.
- **Write amplification.** The flush rewrites a gram's whole posting-list row even
  when only a few of its doc_ids changed. Mitigation: it is batched and runs in
  the background (staging absorbs the writes), and `encoding` keeps the rewritten
  blob small; for grams hot enough that the rewrite cost dominates, the §10
  hot-gram paging optimization switches them to bounded append-only pages.
- **Flush stall / staging growth.** Staging is transient only while the flush
  keeps up; if it stalls, staging grows and the §4.5 read-fold cost rises with
  depth. v1 exposes a **staging-depth / `max(seq) − last-flushed` lag gauge** so a
  stalled single-flight flush is observable, not silent; an enforced backpressure
  bound is a deferred operability item (§10).
- **doc_id density decay.** Gaps from deletes/re-chunks slowly worsen
  compression. Mitigation: graceful (sorted still holds); a rare full reindex
  (§10) re-densifies.
- **Write latency.** Per-write gram maintenance costs work. Mitigation:
  append-only staging; O(grams changed) per write, independent of corpus size.

## 9. Decision Log

- **2026-05-13** — Single lowercase (casefold) stream; no `gram_kind`, no
  raw-case stream.
- **2026-05-24** — Index production + maintenance live on the base
  `DatabaseFileSystem`; all backends inherit; no per-backend adapter sequence.
- **2026-05-24** — Story scoped to *producing* the index; querying it is
  out of scope.
- **2026-05-24** — `pg_trgm` is not the index (word-oriented model wrong for
  code).
- **2026-05-25** — Adopt concrete indexing limits; excluded chunks are flagged
  for query-path fallback.
- **2026-05-25** — Contract tightenings: a dedicated `index_exclusion_reason`
  (chunked-parent vs. excluded now distinguishable); staging carries `entry_id`
  on every row and LAW folds by `(gram_key, entry_id)` (deletes also carry
  `doc_id`); index maintenance extracts folded-only; a minimal §4.5 storage-read
  contract.
- **2026-05-25** — Versions/snapshots are not content-indexed.
- **2026-05-25** — Fixed 3-byte trigrams for v1; sparse n-grams deferred,
  benchmark-gated.
- **2026-05-27** — **Durable store is one posting-list row per gram, not multiple
  immutable blocks.** `staging → flush → a single (gram_key, postings, encoding,
  doc_count, byte_size) row per gram`, rewritten in place by the background flush
  (MVCC + global single-flight cover concurrency). Collapses the four-table shape:
  transient staging (no `gram_batches`), `doc_count` (no `gram_stats`), flush
  absorbs compaction. Matches `codesearch`'s one-list-per-gram shape.
- **2026-05-27** — **Encodings: three values defined, `delta+gamma` implemented
  for v1, ported from codesearch's exact byte format** (gap-from-−1, trailing-zero
  terminator, `deltaZeroEnc=16` per `index/delta.go:31`; `index/read.go`'s "31"
  comment is stale). `delta+varint` reserved as a debug fallback; `roaring`
  reserved for the query path (compressed-bitmap intersection). Per-row tag makes
  adding either later migration-free.
- **2026-05-27** — **Priority: optimize query latency over index build/flush
  cost.** The background flush absorbs build work; the durable format may favor
  query speed (e.g. `roaring` for hot grams).
- **2026-05-27 (triage)** — Resolutions from the spec-underspecification audit:
  - **Identity text corrected.** `doc_id` IS `vfs_entries.id` (integer
    auto-increment PK); `uuid` lives in `entry_id`. (Removes the stale "keep
    uuid4 PK + separate doc_id column" description.)
  - **All ≥3-byte docs chunked; only chunks indexed; grams never diffed** —
    re-chunk is content-addressed reconciliation (carry-forward matched / all-add
    new / all-delete unmatched), matched by content hash. Reverses the "small file
    stays a single indexed file row" decision.
  - **Flush protocol pinned:** `seq` watermark, LAW-fold-first then resolve
    surviving adds, idempotent set application, posting-row UPDATE + staging
    DELETE in **one transaction**, **global single-flight**; a gram that empties
    has its row **deleted**; rows staged past the watermark survive.
  - **`gram_key` = `integer` everywhere** (resolves the `bytea(3)/integer` "or").
  - **Tiny content:** chunks under 3 bytes are **not created**; <3-byte patterns
    full-scan, so no false negative.
  - **NUL/binary:** rejected at write by the validator, so **no `binary`
    exclusion reason** exists.
  - **No posting-blob ceiling** in v1; **default storage** (TOAST/LOB), never
    `STORAGE PLAIN`; `byte_size` is the §10 hot-gram trigger.
  - **Gram tables un-scoped;** tenant/path scope enforced by the join to
    `vfs_entries`.
  - **SQLite PK `AUTOINCREMENT`** to bar rowid reuse (verified: a non-AUTOINCREMENT
    rowid reuses a deleted top id; AUTOINCREMENT does not). Postgres/MSSQL never
    reuse.
  - **`seq` monotonicity verified on MSSQL** (50,000-row `IDENTITY` bulk insert,
    dense `1..N`, zero inversions) in addition to SQLite/Postgres.
  - **Full reindex** moved to an explicit deferred item (§10), not a dangling
    procedure.
- **2026-05-27 (re-audit)** — A second blind four-lens audit of the rewrite
  confirmed the first-round resolutions and surfaced a concurrency cluster,
  resolved by stating a **single-session / single-writer execution model** (§4.2):
  reads/writes/flush are serialized in one session, so the §4.5 fold is
  snapshot-consistent and single-flight needs no cross-process lock (deferred to
  multi-worker, §10). Also pinned: the flush deletes the **exact folded `seq`
  set** (not `≤ watermark`); a flush **join-miss drops the add** (normal
  add-then-delete race), not an "invariant violation"; **encoding codes**
  `1=varint, 2=gamma, 3=roaring`; gamma **decode is count-bounded + terminator
  assert** with the terminator itself zero-remapped; `index_exclusion_reason` is
  **set/cleared per new chunk at reconcile** with a 4-state truth table + a
  validator barring the invalid combo; carry-forward collisions are prevented by
  **version-namespaced chunk paths**; the flush asserts `doc_count ==
  len(decode(postings))` and v1 exposes a staging-lag gauge. Left open for
  discussion: the duplicate-content-chunk `occurrence` tie-break (§10 item 7).
- **2026-05-28** — **`index()` reframed as a three-phase server-side pipeline**
  (§4.6): **chunk → encode → compile**, each watermark-driven, idempotent, and
  independently runnable. The flush is the **compile** phase.
  - **Index is not a client/MCP verb.** Indexing is a server/ETL responsibility,
    exposed through a `SupportsIndexMaintenance` capability that the base
    `VirtualFileSystem` does not define — only index-bearing backends implement
    it. Keeps the MCP client surface (read/write/ls/grep/…) clean.
  - **Three per-phase flags `auto_chunk` / `auto_encode` / `auto_compile`**
    replace the conflated `auto_index`. `encode` = "encode a chunk's content into
    its index representations (grams + vector)"; a different layer from the
    posting codec's byte encoding (§5.4). No `auto_index` flag — `index` names the
    whole pipeline.
  - **Inline phases share the write session/transaction.** Order:
    chunk → encode (deltas, `doc_id` null) → persist (assigns `id`) → compile
    (post-persist fold, resolves `doc_id` by `entry_id→id` join) → one commit.
    Compile runs after persist so the join sees the assigned ids; a failure rolls
    back the whole write. Retires the `compile_post_list` boolean.
  - **A file `chunk watermark`** (the file `content_hash` at last chunking) is
    added to drive the chunk phase; chunking previously had no durable marker.
- **2026-05-28** — **Per-chunk indexing limits + `index_exclusion_reason`
  dropped.** Chunk-all + the size-bounded splitter make the 2 MiB / 20k-gram
  limits unreachable, so the column, its validator, the 4-state truth table, and
  the exclusion/fallback-scan branch are removed (§4.2, §4.3, §4.5). Every chunk
  is indexed or carried forward; `index_content` alone classifies a row.
- **2026-05-28** — **`delta+gamma` codec landed and byte-verified.**
  `src/vfs/postings.py` (`encode_postings` / `decode_postings`, public
  `GammaWriter` / `GammaReader`) ports codesearch's exact format; output is
  byte-identical to a Go harness running `delta.go`'s writer across the
  zero-remap boundary, a 10⁶ gap, and a 200-id run. Decode is count-bounded with a
  terminator assert.

## 10. Deferred Options

One small detail is open (item 7, flagged for discussion); the rest are decided
deferrals, each with a clear reopening trigger:

1. **Sparse / variable-length n-grams** — reopen if benchmarks show hot-gram
   storage or selectivity is the bottleneck (Blackbird, Cursor).
2. **A second raw-case gram stream** — reopen if case-sensitive candidate breadth
   dominates; addable via `index_id` namespacing without a schema migration.
3. **Multi-version / snapshot dedup** (Zoekt branch-mask style) — reopen only if
   `kind="version"` rows are ever made content-indexed.
4. **Hot-gram paging + `roaring` encoding** — for the grams in more than ~N% of
   documents (identified by a `hot_grams` table; `byte_size` is the trigger
   signal), two related **query-driven** upgrades built with the query path:
   (a) split them into bounded, append-only posting *pages* (exploiting monotonic
   doc_ids: append a new page, never rewriting existing data) instead of one
   rewritten-in-place row; (b) encode them as `roaring` for compressed-bitmap
   intersection at query time. Both are addable per-gram without a migration.
   This is where the `experiment-linux-posting-pages-2026-05-27` work
   (byte-budgeted pages, backend-specific targets ~1–2 KB on Postgres) applies.
5. **Full reindex / re-densify** — the only doc_id-renumbering operation; rewrites
   every posting row from current chunk content and necessarily runs as an offline
   whole-index rebuild. Procedure deferred; reopen if doc_id density decay or a
   corruption-recovery need makes it necessary.
6. **Operability: enforced flush-stall backpressure + a per-gram "rebuild from
   source" recovery/audit op** — deferred (v1 already exposes a staging-lag gauge
   and a flush-time `doc_count` self-check, §5.2/§8); reopen when the index runs
   in production and the §4.2 invariant needs a stronger runtime guard.
7. **Duplicate-content chunk `occurrence` tie-break** *(open — to discuss)* — when
   one file has multiple chunks of identical content, the rule pairing old↔new for
   carry-forward isn't pinned (the landed code uses FIFO within the owning file).
   It only affects which `doc_id`/line-range binds to which position (grams are
   identical either way), so it is index-correctness-safe; pin it before the query
   path relies on that binding.

## 11. References

**Source repos reviewed (cloned 2026-05-25), with this story's analyses:**

- `google/codesearch` — doc-level trigram index (closest match) —
  [`analysis-codesearch.md`](./analysis-codesearch.md). Posting-list byte format
  and gamma encoding ported from `index/delta.go` + `index/read.go`.
- `sourcegraph/zoekt` — positional, sharded trigram search —
  [`analysis-zoekt.md`](./analysis-zoekt.md)
- SQLite `ext/fts5/` — LSM segments + trigram tokenizer (a target backend) —
  [`analysis-fts5.md`](./analysis-fts5.md)
- PostgreSQL `pg_trgm` + GIN — pending-list staging + posting model —
  [`analysis-pg_trgm-gin.md`](./analysis-pg_trgm-gin.md)

**Experiments / learnings:**

- [`experiment-linux-posting-pages-2026-05-27.md`](./experiment-linux-posting-pages-2026-05-27.md)
  — real-corpus posting sizing (informs §10 paging; superseded for the v1
  one-row-per-gram store).
- `context/learnings/2026-05-26-bulk-insert-vs-orm-per-row.md` — Core bulk insert
  vs ORM per-row; `seq` monotonicity on SQLite/Postgres.

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
