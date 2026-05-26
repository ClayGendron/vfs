# 030 — Incremental Chunk Indexing & Deferred `index()`

- **Status:** draft
- **Date:** 2026-05-25
- **Owner:** Clay Gendron
- **Kind:** feature + backend
- **Builds on:** [013](../013-database-agnostic-code-trigram-index/spec.md)
  (the trigram index this maintains), [014](../014-auto-chunk-and-auto-index-on-write/spec.md)
  (the auto-chunk / auto-index write pipeline this refines).

## 1. Summary

Two changes to the write/index pipeline, sharing one new column:

1. **Incremental re-chunk (content-hash diffing).** Today a write to a changed
   file deletes *all* its chunk rows and inserts a fresh set, re-indexing every
   chunk. This story diffs the freshly-computed chunk set against the existing
   chunk rows **by `content_hash`**: a chunk whose content is unchanged is
   *carried forward* — its existing row is kept (preserving `id`/`doc_id`,
   `entry_id`, `embedding`, and its grams), with only its **path / line range**
   rewritten to the new position. Only genuinely new chunks are inserted and
   indexed; only genuinely gone chunks are deleted and de-indexed. Editing the
   middle of a document no longer re-indexes the unchanged tail.

2. **Deferred indexing via `dbfs.index()`.** A new nullable
   `vfs_entries.indexed_content_hash` records the `content_hash` that is
   currently reflected in the durable index (posting blocks **and** embedding)
   for that row. With `auto_index=False`, writes leave it stale (or null); a new
   public **`index()`** method later finds every `index_content=True` row whose
   `indexed_content_hash` is null or ≠ `content_hash`, brings the durable index
   current (stages gram deltas, computes embeddings, flushes to posting blocks),
   and stamps `indexed_content_hash = content_hash`.

   **`index()` never chunks.** Chunk rows are produced solely by the write path
   (`auto_chunk`); `index()` consumes whatever chunk set the last write left.

Both features rest on one observation: **the durable index is derived state**,
and `content_hash` vs `indexed_content_hash` is the watermark that says which
rows the index is out of date for.

## 2. Goals / Non-Goals

**Goals**

- Carry forward unchanged chunks across a re-chunk by content match: no
  re-embedding, no gram churn, only a positional (path / line) rewrite.
- A `indexed_content_hash` watermark column distinguishing *indexed-and-current*
  from *needs-indexing* per row.
- A public `index()` that reconciles the durable index to the live
  `index_content=True` rows and flushes staged grams into posting blocks.
- Identical inline (`auto_index=True`) vs deferred (`index()`) index *contents* —
  same delta-log, same posting blocks, same no-false-negative guarantee
  ([013 §4.2](../013-database-agnostic-code-trigram-index/spec.md)).

**Non-Goals**

- **Chunking inside `index()`.** Out of scope by design — chunk production is a
  write-path concern.
- Query execution (still out of scope per 013 §2).
- Changing the chunk *naming* scheme. Paths stay `<line_start>_<line_end>`
  (+`@<offset>` disambiguator); we rewrite them on carry-forward, we don't
  redesign them.
- A new posting-block format. This story consumes 013's `staging → flush →
  posting blocks` model; it does not alter the encoding.

## 3. Concepts & Glossary

- **Carry-forward chunk** — a freshly-computed chunk whose `content_hash` matches
  an existing chunk row. The existing row is reused in place; only its
  positional metadata (`path`, `line_start`, `line_end`) is rewritten.
- **New chunk** — a freshly-computed chunk with no content match among existing
  rows. Inserted and indexed.
- **Stale chunk** — an existing chunk row with no content match among the
  freshly-computed set. Deleted and de-indexed.
- **`indexed_content_hash`** — the `content_hash` last folded into the durable
  index (grams **and** embedding) for a row. `null` = never indexed;
  `== content_hash` = index current; `≠ content_hash` = index stale.
- **Inline path** — indexing performed in the write transaction
  (`auto_index=True`), diffing old/new content captured in-memory (013's model).
- **Deferred path** — indexing performed later by `index()` (`auto_index=False`),
  driven by the `indexed_content_hash` watermark, with no old content in hand.

## 4. The Contract (normative)

### 4.1 `indexed_content_hash` semantics

- `indexed_content_hash` MUST equal the `content_hash` value that is currently
  represented in the durable index — i.e. after a row's grams are folded into
  posting blocks **and** (if an embedding provider is configured) its embedding
  is computed and stored.
- A row is **index-current** iff `index_content = True` and
  `indexed_content_hash == content_hash`. A row is **index-stale** iff
  `index_content = True` and (`indexed_content_hash IS NULL` OR
  `indexed_content_hash <> content_hash`).
- A row with `index_content = False` is never index-current/stale; it is simply
  not part of the index input set (a chunked parent, or a non-indexable row).
- Rows excluded by the [013 §4.3](../013-database-agnostic-code-trigram-index/spec.md)
  limits (non-null `index_exclusion_reason`) MUST have `indexed_content_hash`
  stamped to `content_hash` once the exclusion is recorded, so they are not
  retried until their content changes.

### 4.2 Carry-forward correctness

- A carry-forward MUST preserve the existing row's `id` (== `doc_id`),
  `entry_id`, `embedding`, `indexed_content_hash`, and `index_exclusion_reason`.
  Its grams in the durable index are therefore untouched and remain correct
  (grams are content-derived; line position is not a gram input).
- A carry-forward MUST rewrite only `path`, `name`, `line_start`, `line_end`
  (and `updated_at`). `parent_path` is unchanged (same file, same chunk dir).
- Carry-forward matching is **by `content_hash`, with multiplicity**: if a hash
  appears *k* times among new chunks and *m* times among existing rows, exactly
  `min(k, m)` carry forward; the surplus new chunks are *new*, the surplus
  existing rows are *stale*. Which specific rows pair is unobservable (content is
  identical), so any 1:1 assignment is correct.
- The overall post-write chunk set (by content) MUST be identical whether or not
  carry-forward fires — incrementalism is an optimization, never a semantic.

### 4.3 `index()` contract

- `index()` MUST NOT chunk, embed unchanged rows, re-stage grams for
  index-current rows, or touch rows with `index_content = False`.
- `index()` MUST process exactly the index-stale set (plus, under `force=True`,
  the index-current set as well — a full reindex of the scope).
- For each processed row, `index()` MUST: stage its current grams as adds,
  compute its embedding (if a provider is configured), fold the staged deltas
  into posting blocks (flush), and stamp `indexed_content_hash = content_hash`.
- `index()` MUST also **garbage-collect orphan index entries**: durable-index
  membership for an `entry_id`/`doc_id` whose row no longer exists (deleted, or
  superseded by a new chunk under `auto_index=False`) MUST be removed so the
  index does not retain unbounded dead postings (false positives are permitted
  by 013 §4.2, but must not accumulate unbounded). See §5.4.
- `index()` MUST be **idempotent**: a second call over a scope with no stale rows
  and no orphans is a no-op.

### 4.4 Path-collision safety (carry-forward rename)

- Applying carry-forward renames MUST NOT transiently violate the
  `vfs_entries.path` unique constraint. Because chunk paths shift (a middle edit
  pushes the tail's `<line_start>_<line_end>` up or down), a rename target may
  collide with another row pending its own rename or delete. The write MUST
  sequence row operations so no two live rows ever share a path (see §5.3).

## 5. Design

### 5.1 Data model

- **New column `vfs_entries.indexed_content_hash`** — `str | None`,
  `max_length=64` (same shape as `content_hash`), default `None`, **not
  indexed** by default (scanned via the `index_content` index + a hash compare;
  add an index only if `index()` scan cost demands it — see §8). Internal: never
  exposed as a projectable Candidate field; added to the write-path /
  index-path `load_only` sets only.

No other schema change. The carry-forward and `index()` logic ride entirely on
existing columns plus this watermark.

### 5.2 Write pipeline — incremental re-chunk

The current pipeline (013 rework) deletes all stale chunks in
`_write_phase_fetch_existing` *before* chunking, then inserts all new chunks.
This story reorders so the **diff happens after chunking**, since we cannot
classify a chunk as carry-forward / new / stale until the new set exists.

New phase ordering inside `_write_impl` for a changed, indexable file:

```text
fetch_existing      capture existing chunk rows (NOT a delete) as tuples:
                      (doc_id, entry_id, content_hash, path, line_start,
                       line_end, indexed_content_hash)
auto_chunk          compute new chunk rows in memory (final unique names)
reconcile_chunks    diff new vs existing by content_hash → carry / new / stale  [NEW]
auto_index          (inline path) stage gram adds for NEW chunks; stage gram
                      deletes for STALE chunks (from captured content); embed
                      NEW chunks; stamp indexed_content_hash on indexed rows
persist             DELETE stale rows; apply carry-forward renames (collision-
                      safe, §5.3); INSERT new chunk rows; flush
```

`reconcile_chunks` (new helper, base `DatabaseFileSystem`):

1. Build `existing_by_hash: dict[str, deque[_ExistingChunk]]` from the captured
   rows.
2. Walk the new chunks in order. For each, pop a same-hash existing row if one
   remains → **carry-forward pair**; else → **new chunk**.
3. Remaining existing rows → **stale chunks**.
4. For each carry-forward pair: drop the new chunk from `write_map` (it will not
   be inserted) and record an in-place rename of the existing row to the new
   chunk's `path` / `name` / `line_start` / `line_end`. A pair whose path is
   already identical is a pure no-op (skip even the rename).
5. New chunks stay in `write_map` / `changed_paths` for insert + index. Stale
   chunks are recorded for delete + de-index.

The existing single-chunk-file case (a file small enough to stay one indexed
`file` row, 013 decision 2026-05-25) is unaffected: such files never produce
chunk rows, and the file row's own change is handled by the existing
content-hash change detection in `fetch_existing`.

### 5.3 Carry-forward rename — collision safety

Carry-forward targets are the *new* chunk paths; the rows being renamed hold the
*old* chunk paths. The two sets overlap arbitrarily (a tail shift maps
`11_20 → 16_25`, which may be another surviving chunk's old path). The
`vfs_entries.path` unique constraint is enforced per-statement, so a naive
sequence of `UPDATE`s can collide mid-flight.

Sequence in `persist`:

1. **DELETE stale rows first** — frees any paths only stale rows held.
2. **Rename in two phases** over the carry-forwards whose path changed:
   - Phase A: `UPDATE` each to a guaranteed-unique **temp path**
     (`<chunk_dir>/<entry_id>` — the `entry_id` uuid is unique and a valid name
     segment), then flush. This vacates every old chunk path.
   - Phase B: `UPDATE` each from its temp path to its **final** new path, then
     flush. No final path can collide now: stale rows are gone, and every
     carry-forward currently sits on a temp path.
3. **INSERT new chunks** — their paths are guaranteed free (vacated above).

A fast path skips Phase A/B entirely when no carry-forward's path changed (e.g.
an append-only edit, where the tail keeps its line ranges).

### 5.4 Deferred indexing — `index()`

Public surface (mirrors `write` routing): `VirtualFileSystem.index(...)` →
`DatabaseFileSystem._index_impl(...)`.

```python
async def index(
    self,
    path: str | None = None,   # scope to a subtree; None = whole fs (user-scoped)
    *,
    force: bool = False,       # reindex index-current rows too (full reindex)
    user_id: str | None = None,
) -> VFSResult:                # summary: counts of indexed / skipped / gc'd
```

Behavior:

1. **Find work.** `SELECT` (narrowed) the index-stale rows in scope:
   `index_content = True AND deleted_at IS NULL AND (force OR
   indexed_content_hash IS NULL OR indexed_content_hash <> content_hash)`,
   batched. Excluded rows (non-null `index_exclusion_reason`) are *not*
   re-indexed but ARE stamped (§4.1) so they stop showing as stale.
2. **Stage grams.** For each stale row, stage its current folded grams as adds
   (`_apply_trigram_maintenance`, new-content form — no diff, since the deferred
   path has no old content). For chunked content this is the *only* shape needed:
   a content change to a chunk produces a *new chunk row* at write (its old row
   is a stale chunk, deleted at write), so a chunk row's content never mutates in
   place — `index()` only ever sees brand-new chunk rows to add.
3. **Embed.** One bulk embedding call over the stale rows (if a provider is
   configured), same as the inline path.
4. **Flush.** Fold staging into posting blocks (013 §5.2 flush). This is the
   "update the posting block index" step.
5. **Garbage-collect orphans.** Index membership whose backing row is gone
   (stale chunks deleted at write under `auto_index=False`, or any deleted row)
   must be removed. In the **MVP delta-log** this is tractable directly: the
   `{entries}_chunk_grams` log retains an `entry_id`'s add-deltas until flush, so
   `index()` anti-joins distinct log `entry_id`s against live
   `index_content=True` rows and stages delete deltas for the orphans' current
   grams. In the **posting-block target**, orphan doc_ids are dropped during the
   flush/compaction rewrite (compaction already decodes and re-encodes blocks;
   it filters out doc_ids not present in the live set). See 013 §5.3.
6. **Stamp.** Set `indexed_content_hash = content_hash` on every processed row in
   the same transaction as the flush.

`index()` runs in its own session, one transaction (or batched transactions for
large scopes), and reuses the `_WriteAbort` → `rollback` discipline so a partial
index never commits a half-updated watermark.

### 5.5 Interaction matrix

| `auto_chunk` | `auto_index` | write does | `index()` does |
|---|---|---|---|
| on | on | chunk + reconcile + stage/flush/embed + stamp | nothing stale (no-op) |
| on | off | chunk + reconcile; **no** stage/embed/stamp | stage/flush/embed stale rows + GC orphans + stamp |
| off | on | no chunk; index file rows inline | nothing stale |
| off | off | no chunk; no index | stage/flush/embed the indexable file rows + stamp |

Carry-forward (§5.2) runs in both `auto_chunk=on` rows regardless of
`auto_index`, because it is a write-path chunk-row operation, not an index
operation — it only *avoids* index churn as a side effect of reusing the row.

## 6. Phasing

| Phase | What ships |
|---|---|
| **1 — watermark column** | `indexed_content_hash` on `VFSEntry`; load_only wiring; set it at the end of the inline `auto_index` path (and on excluded rows). No behavior change beyond the stamp. |
| **2 — incremental re-chunk** | `reconcile_chunks` + carry-forward in-place rename (collision-safe, §5.3); inline gram/embed work narrows to new chunks; stale chunks deleted + de-indexed as today. |
| **3 — `index()` (delta-log MVP)** | Public `index()`; stale-row scan; stage grams + embed + stamp; orphan GC via the delta-log anti-join (§5.4 step 5, MVP form). Depends on 013 MVP (shipped). |
| **4 — `index()` flush + GC on posting blocks** | Wire `index()`'s flush/GC onto 013's `staging → flush → posting blocks` once that lands (013 Phase 5). |

Phases 1–3 stand alone on the shipped 013 MVP delta-log. Phase 4 is gated on
013 Phase 5.

## 7. Rationale & Alternatives

- **Match by `content_hash`, not by path or line range.** A middle edit changes
  every later chunk's path (line ranges shift) but not its content; content hash
  is the only stable identity across the shift. Matching by path would carry
  forward nothing after a middle insert.
- **Reuse the row in place (rename), not delete+reinsert.** The whole point is to
  avoid re-indexing. Grams reference the chunk's `doc_id`/`entry_id`; delete +
  reinsert mints a new `doc_id`, orphaning the old postings and forcing a full
  re-add (= re-indexing). In-place rename keeps `doc_id`/`entry_id`/`embedding`,
  so the index is literally untouched for carried chunks. (Decided 2026-05-25.)
- **Diff after chunking, not before.** Carry/new/stale can't be classified until
  the new chunk set exists. This reorders the 013 cascade (which deleted before
  chunking) but preserves its invariants: stale de-index still captures content
  before the row goes (now via the reconcile output rather than a blind
  prefix-delete).
- **`indexed_content_hash` is one hash covering grams + embedding together.** A
  row's grams and embedding are produced in the same `auto_index` step and both
  derive from `content`; they move as a unit, so one watermark suffices. Splitting
  into two columns would only matter if grams and embeddings could be current at
  different contents, which the pipeline never produces.
- **`index()` does not chunk.** Chunk boundaries are a write-time decision
  (chunker config, structure-aware splitting per 028/029); making `index()` chunk
  would duplicate that surface and let the chunk set drift from the last write.
  Keeping chunking write-only means `index()` is a pure index reconciler over a
  fixed row set. (User decision 2026-05-25.)
- **`index()` as reconciler (watermark-driven), not a replay log.** The deferred
  path has no old content to diff. Treating the index as derived state to be
  reconciled to the live rows (stale → add; orphan → GC) needs no per-row history
  and is naturally idempotent.
- **Two-phase temp rename over a sorted single-pass.** Per-statement unique
  enforcement means even a carefully ordered single pass can collide on a cyclic
  shift. Routing every changed path through a unique temp (`entry_id`) is
  unconditionally safe and costs at most 2 UPDATEs per shifted chunk; the
  no-shift fast path skips it.

## 8. Risks

- **`index()` scan cost.** Finding stale rows scans `index_content=True` rows and
  compares two hashes. On large corpora this is a wide scan. Mitigation: the
  existing `index_content` index narrows the candidate set; add a composite or
  partial index on `(index_content, indexed_content_hash, content_hash)` if
  profiling demands. Scope (`path` subtree) bounds it in the common case.
- **Orphan GC cost on the MVP delta-log.** The anti-join of distinct log
  `entry_id`s against live rows can be heavy if the log is large. Mitigation:
  it only runs in `index()` (deferred, not on the write path) and shrinks as the
  log is flushed; on the posting-block target it folds into compaction.
- **Rename amplification.** A single-line insert near the top of a huge file
  shifts every subsequent chunk's path → 2 UPDATEs each. Mitigation: this is
  still strictly cheaper than re-embedding + re-gramming every shifted chunk
  (the status quo); UPDATEs are local and index-free vs. embedding network calls.
- **Hash collision (false carry-forward).** Two different chunk contents sharing
  a `content_hash` (sha256) would carry forward incorrectly. Mitigation:
  sha256's collision probability is negligible; this is the same assumption the
  existing file-level change detection already makes.
- **Watermark drift on crash.** If a flush commits but the stamp does not (or
  vice versa), a row could read as current while stale, or stale while current.
  Mitigation: stamp in the **same transaction** as the flush (§5.4); a re-run of
  `index()` re-converges (idempotent), and `force=True` forces reconciliation.

## 9. Decision Log

- **2026-05-25** — New standalone story (030); cross-references 013/014.
- **2026-05-25** — Carry-forward unchanged chunks by `content_hash`, reusing the
  existing row in place (rename only), preserving `doc_id`/`entry_id`/`embedding`
  and its grams. Chunking already mints the new unique names in memory, so a
  content match just rewrites the existing row's path/name.
- **2026-05-25** — Add `indexed_content_hash` watermark (one hash covering grams
  + embedding); index-stale = null or ≠ `content_hash`.
- **2026-05-25** — `index()` is **index-only**: it finds stale rows and updates
  the posting-block index (stage → flush) + embeddings; it **never chunks**.
  Chunk production stays write-path-only.
- **2026-05-25** — Carry-forward rename uses a two-phase temp-path sequence
  (delete stale → temp-rename → final-rename → insert new) to stay within the
  `path` unique constraint; no-shift edits take a fast path.
- **2026-05-25** — Deferred de-index of stale/deleted chunks is reconciled by
  `index()` (orphan GC), not captured at write time, when `auto_index=False`.

## 10. References

- [013 — Database-Agnostic Code Trigram Index](../013-database-agnostic-code-trigram-index/spec.md)
  — the index this maintains; §4.2 (no-false-negatives), §5.2 (staging→flush→
  blocks), §5.3 (doc_id resolution / deletes), §4.3 (indexing limits / exclusion).
- [014 — Auto-chunk and Auto-index on Write](../014-auto-chunk-and-auto-index-on-write/spec.md)
  — the write pipeline phases (`auto_chunk` / `auto_index`) this refines.
- `src/vfs/backends/database.py` — `_write_impl` + `_write_phase_*`; the 013
  rework (`_fetch_existing_chunks` / `_stage_chunk_delete_deltas` /
  `_delete_stale_chunks`) this story generalizes into carry/new/stale.
- `src/vfs/models.py` — `VFSEntry` (new `indexed_content_hash`), `chunk()`
  (names computed in memory), `VFSGram` delta-log.
