# Incremental index refresh for vfs — a design study (2026-10-31)

Design agent output for the shared brief at `../BRIEF.md`. Everything below was checked against the live tree at `/Users/claygendron/Git/Repos/vfs` (read-only). File paths are relative to `src/vfs/` unless they start with `crates/`, `tests/` or `context/`.

The one-line answer: build **delta segments on top of the epoch machinery** (option A), published through a generation counter on the meta row, read by union, absorbed by the existing full rebuild, with a fold-style compaction as the second slice. The other three options are either the same thing with a worse manifest (B), not viable on the production engines (C), or do not change the cost class (D).

## 1. What the code pins today, and what it means for every option

These are the facts the options rest on. Each is cited.

**The write path never touches the index.** `storage/backends/database/writes.py` `_material_values` sets `chunked=False, encoded=False, indexable=False` and nothing else index-related. Deletes demote `encoded` at the claim (`trash.py` `_claim_roots`, `_tombstone_descendants`). So "no extra write latency" is already the baseline, and every option below keeps the write path byte-identical. Confirmed for all four options.

**The dirty set is a flag partition, with an index.** `rows.py` declares `ix_vfs_entries_encoded_kind (encoded, kind)`. The refresh's input is `WHERE NOT encoded AND chunked AND indexable AND deleted_at IS NULL` — the same predicate `indexing.py` `_pending_probe` uses. It is a seek, not a scan.

**`chunk_dirty` already operates only on dirty rows.** `indexing.py` lines 309–326: the select is `~entry.c.chunked ∧ live ∧ content kind`, ordered by `entry.c.id`. Its memory profile is ~6.1× dirty content (docstring). It can be reused verbatim as the refresh's phase A. It deletes and re-inserts chunk rows for re-split entries (`delete(chunks).where(membership(chunks.c.entry_id, ids))`), so **old chunk ids of a re-split entry disappear from `vfs_chunks`** and new ids are minted (`sqlite_autoincrement=True`, `Identity()` elsewhere — never reused).

**`build_epoch` is whole-corpus by construction.** `indexing.py` lines 407–412: the scan is `chunked ∧ indexable ∧ live` with no `encoded` term. Doc ids are `entry.id` (the integer surrogate), which is **stable across content writes** (an overwrite is an UPDATE of the same row). The Rust `PostingsAccumulator` (`crates/vfs-core/src/postings.rs`) requires strictly increasing doc ids and allocates a fixed 16M-slot table (`GRAM_SPACE`, 64 MB of `i32`) per builder; its lists are bounded by the fed documents.

**Publish is one transaction: version-guarded flag flips plus a compare-and-set on `meta.current_gram_epoch`** (`publish_epoch`). The flip is set-based (`_flip_flags`, VALUES join or tuple-IN, chunked by budget; pinned by `tests/storage/database/test_indexing.py::TestPostingBatches::test_flag_flips_are_set_based_not_per_row`). A write between build and publish bumps `version`, the flip misses, the row stays scan-side (`test_a_write_racing_the_publish_window_stays_scan_side`). **This is exactly the guard an incremental publish needs for "refresh racing a write to a covered entry"; nothing new is required there.**

**Reclaim sweeps `epoch < current`** over `tables.epoch_scoped()` (posting_list, lex_docs, lex_postings, lex_df, lex_stats, gram_epochs), re-reading the pointer in its own transaction (`reclaim_epochs`; pinned by `test_reclaim_never_destroys_a_rivals_newer_published_epoch`).

**Readers run a two-read protocol on the pointer.** `reads.py` `pointer_with_overlay` reads the pointer and an overlay-emptiness EXISTS in one statement. `grep.py` re-reads after the candidate fetch and raises `StaleSnapshot` on movement (line 308); `glean.py` the same (line 386). `tests/storage/database/test_races.py::TestGrepEpochConsistency` pins both on every engine leg. The coherence token is a single integer compared for equality — any design that changes what "the live index" means must give the readers a new single token to compare.

**grep ghosts are harmless.** `grep.py` `_entries_for_docs` resolves doc ids to entry rows filtered by `entry.c.encoded`; `content_for_entries` fetches the current body; `VerifyOffload` runs the real matcher. A stale posting that nominates an entry whose body changed either still matches (true positive) or is rejected (verify). A deleted entry's doc id is dropped at the `encoded` filter (deletes demote). The only cost is one candidate fetch and verify (~75 µs, `_CANDIDATE_COST_US`), and the ghost counts against `CANDIDATE_BUDGET`.

**glean ghosts are NOT harmless today — this is a finding the brief did not have.** `glean.py` `_entries_for_chunks` joins `lex_docs` to `entry` on `entry_id`, filtered by `entry.c.encoded`, and then `_observe` does `sources.chunks[chunk_id]` (line 1036) where `sources.chunks` came from `_chunk_texts`, a plain membership select over `vfs_chunks`. If a chunk id in a live `lex_postings` block names a chunk row `chunk_dirty` has deleted, **and** the owning entry is `encoded=True`, the hit survives `_entries_for_chunks`, `_chunk_texts` returns nothing for it, and `_observe` raises `KeyError`. `backend.py` `_execute` catches only `StaleSnapshot`, `SQLAlchemyError` and `OSError`, so the call fails raw. Today this is unreachable in steady state because a re-split entry is `NOT encoded` until the whole-epoch publish, whose `lex_docs` only name chunk ids current at build time. Any delta design that flips `encoded=True` for a re-posted entry while the base epoch's `lex_docs`/`lex_postings` still name its old chunk ids makes it reachable. Section 3 says how A closes it. (Side note: the generation law at `chunk_dirty` line 306–308 re-dirties `chunked` without demoting `encoded` and then deletes the chunk rows, so the same crash is reachable today during the build window after an engine/grammar bump. Low priority, but worth its own small fix.)

**The lexical builder fixes statistics from its own documents.** `crates/vfs-core/src/lexical.rs` `LexicalAccumulator::finish` computes `n_docs`, `avg_dl`, each term's `idf(df, n_docs)` and every block's true `max_weight` **from the documents it was fed**. A delta fed 5,000 chunks would compute idf over 5,000 documents and block bounds under that idf and that `avg_dl`. Those bounds are then wrong for the scorer's skipping when the query scores under the base statistics. A delta build therefore needs a builder variant that takes statistics in (section 3, kernel change K2). Note that `glean.py` `_overlay_blocks` already states the law for scoring un-indexed documents on the epoch's scale: `n_docs = base N + overlay count`, `avg_dl = base avg_dl`, idf = the base's where the term exists, else `idf(overlay df, n_docs)`. A delta is a materialised overlay and should use the same law.

**The candidate kernel ANDs blobs within a group** (`candidate_ids(groups: Vec<Vec<&[u8]>>, allow, cap)`, `postings.rs` line 289; pyo3 binding `crates/vfs-core/src/python.rs` line 484). There is no union-within-a-slot. A delta reader needs one (K1).

**The scorer concatenates blocks freely.** `lexical_score(blocks, idfs, avg_dl, k, candidates)` sums per chunk id over every block whose `term` index names an idf. Blocks from different segments can be concatenated as long as a chunk id appears in one segment only, which chunk-id non-reuse guarantees. `select_blocks` treats each summary as a term and takes the summed maxima of the others as lift; treating `(term, segment)` pairs as separate summaries only loosens the bound (more blocks fetched, never fewer).

**The lease is an arbiter, not a guard** (`indexing.py` module docstring, lines 39–47). Correctness rests on the epoch mint collision and the publish CAS. A refresh must inherit both.

**The embed step is already incremental** (`embed.py`; `backend.py` `_embed_step`, lines 1416–1483): keyset pages over `embedding IS NULL`, no transaction open across provider calls, idempotent `UPDATE … WHERE embedding IS NULL`, content-hash lending. The render step has the same shape (`_render_step`). Both are dirty-bounded phases that a refresh verb can run unchanged.

**One correction to the brief.** `rows.py` `vfs_versions` carries `content` (and `data`) — the full replaced body, written as a snapshot by the mint (spec 180 confirms, "What the code does today"). So the previous content is available, not just its hash. What is *not* recorded is which version the index last posted; see option C.

**Prior decisions.** Spec 030 (archived) proposed an `indexed_content_hash` watermark and incremental chunk carry-forward; its incremental-maintenance premise was superseded 2026-07-12 by the batch-only epoch rebuild "because zoekt treats incremental index maintenance as the hazardous half". Spec 014's auto-index-on-write was superseded the same day. The design below does not reopen either: it keeps the write path clean and keeps the epoch rebuild as the authority; it adds a bounded, lease-held, epoch-shaped batch between rebuilds.

## 2. The scenario in numbers

Assumptions for the arithmetic: ~1,000,000 files, 1–5 % edited per workday (10k–50k entries), edits concentrated in 8 h (20–100 edits/min), mean body ~4 KB, ~2,500 distinct trigrams per 4 KB body, ~8 chunks per entry, ~300 distinct terms per chunk. Full rebuilds at 08:00, 12:00, 16:00 → two 4 h daytime gaps and one 16 h overnight gap with little activity.

| Cadence | Dirty per window (1 % / 5 %) | Content per window | Gram posting rows per delta (≈ distinct grams) | Lexical rows per delta (docs + df + blocks) | Blob bytes per delta |
|---|---|---|---|---|---|
| 5 min | 100 / 500 | 0.4 / 2 MB | ~30k / ~100k | ~10k / ~70k | ~2 / ~10 MB |
| 15 min | 300 / 1,500 | 1.2 / 6 MB | ~70k / ~200k | ~25k / ~150k | ~6 / ~30 MB |
| 30 min | 600 / 3,000 | 2.4 / 12 MB | ~120k / ~350k | ~50k / ~250k | ~12 / ~60 MB |
| 60 min | 1,250 / 6,250 | 5 / 25 MB | ~200k / ~600k | ~100k / ~450k | ~25 / ~120 MB |

Row counts are dominated by the vocabulary of the window (one posting row per distinct gram, one summary and mostly one block per distinct term), not by the number of documents; they grow sub-linearly with the window. For comparison the full epoch of a 1M-file code corpus is a few million posting rows with gigabytes of blobs and ~10M+ lexical rows; a day of deltas adds on the order of 10–20 % of that between rebuilds.

Two numbers that bound the whole design: the full rebuild of 1M files is roughly an hour (spec 130 landing: 108 s of lexical build for 78k files, and gram build on the same order; scale ×13), and its residency is tens of gigabytes (~5 GB per 674k chunks, so ~60 GB at ~9M chunks). **Deltas fix the staleness window; they do not fix the full rebuild's residency.** That remains the "gram-range partitioned passes" direction the `build_epoch` docstring names.

## 3. Option A — delta segments on the epoch machinery

### 3.1 Data model

No new posting tables. A delta is **another epoch number** in the existing epoch-scoped tables; `tables.epoch_scoped()` is unchanged, so the sweep and the fingerprint logic keep working. Three additions:

| Change | Where | Why |
|---|---|---|
| `gram_epochs.base_epoch INTEGER NULL` | `rows.py` | `NULL` (or equal to `epoch`) marks a full build; a delta names the base it was built against. The live set is derived from it. |
| `gram_epochs.published_at`, `gram_epochs.retired_at` (timestamps, NULL by default) | `rows.py` | A delta's rows are committed by the build transaction before publish (as a full build's are today). `published_at` is stamped in the publish transaction; `retired_at` by a compaction that superseded it. Readers take only published, unretired deltas; reclaim takes retired ones. |
| `meta.index_generation BIGINT NOT NULL DEFAULT 0` | `rows.py` | The readers' coherence token. Every publish — full, delta, compaction — increments it in its CAS. It replaces the pointer as the thing the two-read protocol compares. |
| `vfs_segment_members(epoch, entry_id)` PK | `rows.py` (slice 2) | The entries a delta covers, so a compaction can rebuild them from their bodies. Alternative: derive from `lex_docs.entry_id` under the delta epochs (the `ix_vfs_lex_docs_entry (epoch, entry_id)` index serves it). Members are more honest: an entry can be gram-posted and have no lexical rows only if `Chunk.split` yields nothing, which it never does for an indexable body, but the table says so without that reasoning. Decision 9. |

`SCHEMA_FORMAT_VERSION` bumps. `INDEX_FORMAT_VERSION` need not: the posting bytes are unchanged.

The live set at pointer `B` is: `{B} ∪ {e : base_epoch = B ∧ published_at IS NOT NULL ∧ retired_at IS NULL}`. It is bounded by the number of deltas since the last full (slice 1) or by the merge fan-in (slice 2).

### 3.2 Write path

Zero change. Confirmed by reading `_material_values`, `_entry_values`, `_update_params` (writes.py lines 1160–1211) and the delete claim (trash.py lines 454, 484).

### 3.3 The refresh procedure

A new verb `refresh()` beside `reindex()` (decision 1). It takes the **same lease** (`claim_reindex_lease`), heartbeats it, and runs these phases, each in its own writer transaction via `_execute_write`, checking `lost` between them exactly as `_gram_phases` does:

**R0 — render dirty bytes rows.** `_render_step` unchanged; it is already paged and dirty-bounded.

**R1 — chunk the dirty.** `chunk_dirty` unchanged.

**R2 — build the delta** (one transaction):
1. Read `current_gram_epoch = B` and `index_generation = G` from the meta row. If `B` is `None` there is no base; refresh delegates to the full build phases (decision 6). Read the live set `S`.
2. Reclaim any delta rows with `base_epoch = B ∧ published_at IS NULL` — a crashed earlier refresh's residue; safe because the lease says nobody else is building.
3. Mint `D = max(gram_epochs.epoch, B) + 1`, as `build_epoch` does.
4. Scan the dirty set: `select(entry.id, entry_id, version, content).where(chunked, indexable, ~encoded, deleted_at IS NULL, content IS NOT NULL).order_by(entry.id)` — `build_epoch`'s scan plus one `~encoded` term. Feed the `PostingsBuilder` in `_EXTRACT_BATCH_BYTES` batches through `call_offloaded`; drain into `posting_list` rows under `D` with `bulk_insert`. Record `covered = {(entry_id, version)}`.
5. Lexical: stream the covered entries' chunk rows with `_chunk_batches` plus the same `~entry.c.encoded` term (keyset-paged, no IN list). Feed the `LexicalBuilder`. Before finishing, ask the builder for its vocabulary, probe `lex_df` over `S` for those terms in `membership_budget` chunks, read `lex_stats` for `S` (one statement, `epoch IN (S)`), and call the new `finish_under(n_docs_total, avg_dl_base, idfs)` (K2) where `n_docs_total = Σ lex_stats.n_docs over S + n_delta` and `idfs` maps each term present in the base (or an earlier delta) to its stored idf; a term absent everywhere gets `idf(df_delta, n_docs_total)` inside the builder. Write `lex_docs`, `lex_df` (with `df = df_delta`, `idf` = the idf used, the true block maxima under it), `lex_postings`, and `lex_stats(D, n_docs = n_delta, avg_dl = avg_dl_base, k1, b)`.
6. Insert `gram_epochs(D, format_version, options_hash, base_epoch = B)`; `published_at` NULL. A PK collision anywhere is `StaleSnapshot`, as in `build_epoch`.
7. Commit.

**R3 — publish the delta** (one transaction):
1. `_flip_flags(covered, encoded=True)` — version-guarded, set-based, chunked.
2. `DELETE FROM lex_docs WHERE epoch IN (S) AND entry_id IN (chunk)` for the covered entry ids, chunked by `membership_budget − |S|`. This is the ghost closure from section 1: the old chunk ids of a re-posted entry can no longer resolve to an owner, so `_entries_for_chunks` drops them (`owner.get(chunk_id) is None → continue`) and `_chunk_ids_for` no longer nominates them. Served by `ix_vfs_lex_docs_entry`. Bounded by `|covered| × chunks per entry`.
3. `UPDATE gram_epochs SET published_at = now WHERE epoch = D`.
4. CAS: `UPDATE meta SET index_generation = G + 1 WHERE id = 1 AND current_gram_epoch = B AND index_generation = G`. `rowcount != 1` → classified `conflict`; the backend then runs `reclaim_built_epoch(D)` exactly as `_gram_phases` does for a lost full publish.
5. Commit.

**R4 — compaction** (slice 2; see 3.9).

**R5 — reclaim.** `reclaim_epochs` plus one more predicate: rows of epochs whose `gram_epochs` row has `retired_at IS NOT NULL`, or `base_epoch IS NOT NULL ∧ base_epoch ≠ current` (a delta on a base that is no longer the pointer). Both are per-epoch range deletes, as today.

**R6 — embed.** `_embed_step` unchanged. This is what makes the **vector leg** fresh too: new chunk rows have no vector until this runs (`glean.py` module docstring). A refresh that skipped it would leave glean's vector leg blind to the window.

**R7 — release the lease.**

What refresh does **not** run: the whole-corpus phases — segment and edge re-convergence, signals, pack (spec 180). Those are `reindex`'s.

### 3.4 Reader changes

**Coherence token.** `pointer_with_overlay` adds `meta.c.index_generation` to its single-row select and returns `(pointer, generation, overlay_empty)`. The post-fetch re-read compares `generation`, not the pointer. One statement count unchanged. `StaleSnapshot` and the redrive are the existing machinery (`_execute`, `with_retry`); the glean pin `test_a_rival_publish_between_the_reads_is_redriven` becomes a pin on the generation.

**Live set.** One new statement per call after the preamble: `SELECT epoch FROM gram_epochs WHERE epoch = :B OR (base_epoch = :B AND published_at IS NOT NULL AND retired_at IS NULL)`. If this read straddles a publish, the generation compare at the end catches it. (Alternative: a denormalised `meta.live_epochs` text column written in the publish CAS, read in the same statement as the generation — zero extra statements and no straddle, at the cost of a list in a column. Decision 4.)

**grep.** `_posting_meta` becomes `WHERE epoch IN (S) AND gram_key IN (chunk)` with chunk size `membership_budget − |S|`, summing `doc_count` and `byte_size` per gram (pricing in `_choose_grams` and `_ladder_defers` then prices the union's bytes, which is what the fetch will cost). `_posting_blobs` returns `gram → list[bytes]`. The kernel call becomes K1. Nothing else in `grep_rows` changes; `_entries_for_docs`, the gates, verification and the scan tier are untouched.

**K1 — kernel: union within a slot.** `candidate_ids(groups: list[list[list[bytes]]], allow, cap)`: a group is a list of slots (one per gram, rarest-first as the planner chose), a slot is a list of blobs to union. Implementation in `postings.rs`: the first slot's blobs are k-way merged into the survivor list (bounded by the sum of its blob sizes — the rarest gram's base blob plus a few small delta blobs); each later slot streams a k-way merge of its blobs against the survivors (`intersect_stream` with a merge iterator in place of one `Postings`). Every blob is still fully validated. The pyo3 signature changes shape; the oracle in `tests/support/oracles/` gains the union. A one-blob slot is exactly today's path, so the parity suite's existing cases still hold.

**glean.** `lexical_stats(session, tables, S, terms, …)` probes `lex_df` with `epoch IN (S) AND term IN (probe)` and returns per-`(term, epoch)` summaries; `lex_stats` over `S`: `avg_dl` from the base row, `n_docs = Σ`. The scorer's "term" index becomes a slot index over `(term, epoch)` pairs present, each with its stored idf (identical to the base's for terms the base has; the delta's own for new terms). `_chunk_ranking` fetches heads with `epoch IN (S)`; round two selects per slot and packs arms as today (`_packed_arms` already budgets binds; each arm gains nothing since `epoch == :e` was already in it). `_entries_for_chunks` and `_chunk_ids_for` use `docs.c.epoch IN (S)`. `_visible_lexicon` (partial views) does the same over `S`; its disclosed cost profile (every block of every query term) multiplies by the number of segments the term appears in. `_overlay_blocks` is unchanged except that `stats.n_docs` is the summed N.

### 3.5 Full rebuild interaction

`reindex()` is unchanged in shape and absorbs everything: `build_epoch` scans `chunked ∧ indexable ∧ live` regardless of `encoded`, so every entry a delta covered is re-posted in the new base (its version guard protects a later write exactly as today). Its publish CAS stays on the pointer alone (a full built from base `B` never needs to know about deltas on `B`, because it covers a superset) but also sets `index_generation = index_generation + 1` SQL-side so readers redrive. `reclaim_epochs` then deletes `epoch < new base`, which includes every delta (all minted before the new base's number), and the `base_epoch ≠ current` rule catches any delta minted after the base started building.

Two consequences to record. First, `_work_pending` should also return true when live deltas exist and nothing is dirty, so a scheduled full rebuild still folds the deltas back into one epoch instead of no-oping (decision 7). Second, while `reindex()` holds the lease (about an hour at 1M files), `refresh()` is refused with the existing "already running" conflict; staleness during that hour is the rebuild's duration plus one cadence. Slice 3 lifts that.

### 3.6 Correctness

The invariant moves one word: **`encoded=True` ⇒ the entry's grams and terms are in the live set (the base or a published, unretired delta on it).**

Why it holds. The flip to `True` happens only in R3, in the same transaction that marks `D` published and bumps the generation, after `D`'s rows committed in R2. Every coverage exit still demotes (writes, deletes — unchanged). A full publish moves the pointer, which removes every delta from the live set in the same instant, and the new base covers a superset of what the deltas covered under the same version guard; an entry that stays `encoded=True` across that publish has its current grams in the new base. A compaction retires old deltas in the same transaction that publishes the delta that re-covers their members (3.9).

No lost match. An entry is either `NOT encoded` — the scan tier serves it, as today — or `encoded` with its current gram set in some live segment. The reader's per-gram union over the live set is a superset of that segment's postings, so the AND over the pattern's grams keeps the entry. Stale postings for the same doc id in older segments can only add candidates. grep verifies every candidate against the current body (`VerifyOffload`), so a stale nomination is rejected or confirmed, never wrong. glean's stale chunk ids are unresolvable after R3 step 2, so they are dropped at the join; the delta's chunks resolve through `D`'s `lex_docs`. A ghost that was ranked inside the `FUSION_K` window costs window depth, and the existing short-probe (`depth *= PROBE_DEEPEN` when `len(hits) < limit`) recovers it.

Statistics. Deltas score under the base's `avg_dl` and, for terms the base knows, the base's idf — the same law the overlay uses today, so the index side and the overlay stay on one scale. Where that is **acceptable**: between full rebuilds with ≤ 5 % churn, `N` moves by ≤ 5 % and `df` of a common term by about the same; `ln(1 + (N − df + 0.5)/(df + 0.5))` moves in the third significant figure. Where df **must be summed**: the exported `lexical_stats` (`df`, `n_docs`) should report the sum over the live set so the envelope is honest, and the overlay's `n_docs` should use the summed N. Where the law is **weakest**: a term new to the corpus that appears in several deltas gets a slightly different idf in each (each computed under the N at its build); each delta's blocks carry bounds under their own idf, so skipping stays sound per slot, but the scale across those deltas differs by the ratio of their Ns — a few parts in a thousand at this churn. Ghost chunks inflate base df and N until the full rebuild, as the overlay inflates them today. All of this is reset three times a day.

### 3.7 Bounded statements and memory

Every new predicate is chunked: `gram_key IN`, `term IN`, `chunk_id IN`, `entry_id IN` by `membership_budget` **minus `|S|`** for the statements that also carry `epoch IN (S)` (the 32-bind `_FILTER_BIND_RESERVE` is not sized for a 49-element list; subtract `|S|` explicitly). `epoch IN (S)` itself is bounded by the live-set size: the delta count between full rebuilds in slice 1 (≤ 49 at 5 min, well under Oracle's 1,000), and by the merge fan-in in slice 2. Bulk inserts ride `bulk_insert` as today. `_flip_flags` and the `lex_docs` delete chunk by the budget. The members table insert is one bulk insert per delta.

Memory is the dirty set: `chunk_dirty` at ~6.1× dirty content; the `PostingsAccumulator`'s fixed 64 MB slot table plus posting lists over the window's documents; the `LexicalAccumulator`'s vocabulary over the window's chunks; the reader's union bounded by the rarest gram's base blob plus small delta blobs. Nothing scales with the corpus except the one fixed table.

### 3.8 Concurrency and failure modes

| Situation | What happens | Why it is safe |
|---|---|---|
| Crash after R2, before R3 | Rows under `D` exist, `published_at` NULL, generation unchanged. Readers ignore `D` (not in the live set). Next refresh's R2 step 2 reclaims them; a full's `epoch < new base` also would. Entries stay `NOT encoded`, scan-side. | Unpublished rows are inert, as today's unpublished full epoch is. |
| Crash mid-R3 | The transaction rolls back whole: no flips, no `lex_docs` deletes, no publish mark, no generation bump. | One transaction. |
| Rival refresh (lease lapsed) | Both build on `(B, G)`. The second to reach the CAS fails on `index_generation = G`, classifies `conflict`, reclaims its own `D'`. | The generation CAS is the guard the lease is not. Without it both deltas would carry the same chunk ids and the scorer would double-count them. |
| Rival full build racing a refresh (lease lapsed) | Mint collision on the posting PK if both mint the same number → `StaleSnapshot` → the refresh redrives and, because the full's `gram_epochs` row is not yet inserted, collides again until exhausted → clean `conflict`. If the delta publishes first, the full's pointer CAS still succeeds (it is on the pointer alone), and the delta is swept by `base_epoch ≠ current`. | The lease normally prevents this; the CAS and the sweep rule make the lapse harmless. Slice 3 (early epoch reservation) removes the collision. |
| Refresh racing a write to a covered entry | The flip's version guard misses; the entry stays `NOT encoded`; its postings in `D` are ghosts (harmless). | Existing behaviour, pinned by `test_a_write_racing_the_publish_window_stays_scan_side`. |
| Reader straddles a publish | The live-set read or the blob fetches see a mix; the generation re-read differs → `StaleSnapshot` → redrive. | The existing two-read protocol, token swapped. |
| Refresh with nothing dirty | R2 finds no rows; no epoch is minted, no generation bump. | A refresh never creates an empty segment. |
| Options/format drift | `_work_pending`-style fingerprint check at R2: if the base's fingerprint differs from the running code, refresh refuses with a record naming `reindex`. | A delta built with different options against an old base would mix formats. |

### 3.9 Compaction (slice 2)

Not a blob-level merge. When the live delta count reaches `MERGE_FAN_IN` (a merge trigger, not a scale cap — the corpus and the dirty volume are uncapped), R2's scan predicate becomes `dirty ∨ entry_id IN members(live deltas)`, read in `membership_budget` chunks from `vfs_segment_members`. The new delta re-posts those entries **from their current bodies**, so ghosts inside the retired deltas vanish without any tombstone set; R3 stamps `retired_at` on the old deltas in the same transaction as the publish; R5 sweeps them. Cost per merge: re-read of `fan_in × delta` bodies (8 × 500 docs ≈ 16 MB) — trivial. This keeps the live set at ≤ `fan_in + 1` and the per-refresh insert volume at one delta, instead of the "rebuild one ever-growing pending list every time" shape, which would write ~70 MB of blobs every 5 minutes by the end of a 4 h window.

A true Lucene-style tiered merge (union and re-encode per gram across deltas, dropping ids in a tombstone set) is possible later with a `union_postings` kernel, but the fold is simpler, needs no tombstones, and is cheap at these sizes.

## 4. Option B — a flat "pending postings" table

Shape: `vfs_pending_postings(gram_key, batch_id, postings, doc_count, byte_size)` PK `(gram_key, batch_id)`, plus lexical twins, plus a batch registry; the refresh fills a batch from the dirty set, readers union every batch with the base, the full rebuild truncates the table.

Read against A it is A with the key order reversed and the manifest flattened. What it **buys**: a gram's batches are contiguous in the PK, so `_posting_blobs` reads one range per gram instead of `|S|` point lookups; the full rebuild drains it with one `DELETE`; there is no base/delta distinction to reason about. What it **costs**: the same row volume per refresh (one row per distinct gram per batch — the "per-gram row proliferation" is identical to A, because both key on gram); batches accumulate until the next full (48 at 5 min) with no identity to retire a subset, so read fan-out grows linearly with cadence and there is no clean place to hang a compaction; it still needs the generation token and a published mark per batch for coherence; and it duplicates every epoch-scoped table rather than reusing them (`epoch_scoped()`, the sweep and the fingerprint logic would have to learn a second family).

Two honesty notes. First, unpublished rows are harmless for readers in both A and B: grep's extra candidates verify, and glean's chunks for a `NOT encoded` entry drop at the `encoded` filter. The published mark is for a deterministic live set and tidy reclaim, not for correctness. Second, Postgres GIN's real pending list is not an inverted table at all: it is a forward, per-heap-tuple list capped at `gin_pending_list_limit` (4 MB) and flushed by inserts or autovacuum. The lesson GIN actually teaches is "keep the unmerged part small and flush it on a trigger", which is A's fold, not B's flat table.

Verdict: take A's manifest. If the per-gram contiguity ever shows up in a measurement, add an index `(gram_key, epoch)` on `posting_list` rather than a second table.

## 5. Option C — in-place patching of the base epoch's blobs

Per 4 KB document ~2,500 distinct trigrams; a 500-document window touches ~1.25M (gram, doc) pairs over ~100k distinct grams. Each touched gram's base blob must be read, decoded (`decode_postings`), merged, re-encoded and rewritten. Blob sizes in a 1M-entry corpus: a gram in 10 % of entries holds ~100k ids at roughly one byte per delta-coded id (ids are dense surrogates) → ~100–200 KB; a gram in half the corpus ~500 KB; the few hundred most common ~1 MB. Touched grams skew heavily to the common ones (a window of 500 files touches almost every gram in the top tens of thousands), and those grams hold most of the index's bytes. A single 500-document patch therefore rewrites on the order of **a third to two thirds of the base posting bytes — roughly 1–3 GB — every refresh.**

On the engines: Postgres rewrites a TOASTed `bytea` as a new row version and a new TOAST chain, so each refresh leaves 1–3 GB of dead tuples for autovacuum and writes as much WAL (plus full-page images) — hundreds of gigabytes of WAL per day at 5 min. SQL Server rewrites the LOB and takes a row lock per updated row; ~100k row updates in one transaction crosses the 5,000-lock escalation threshold (`dialects.py` records this: the `in_list_budget` of 2,000 "doubles as the lock budget … under the 5,000-lock escalation trigger"), so the statement escalates to a table lock on `posting_list` and every concurrent grep blocks for the duration. Oracle versions LOBs through undo/retention; 1–3 GB of undo per refresh and `ORA-01555` exposure for long readers. Bind budgets are the least of it; the problem is bytes and lock time.

Atomicity forces the long transaction. Patching g then g' in separate transactions is fine *while the entry stays `NOT encoded`* (the AND cannot lose it — it is scan-side), so the only coherent shape is "patch every touched gram, then flip" — all in one transaction, which is exactly the one that escalates and bloats. The lexical side is worse: tf and dl blobs are blocked at 128 postings in id order; inserting ids shifts block boundaries, so the term's block rows and its summary row (`lex_df.blocks`) are rewritten, and every block's `max_weight` must be recomputed.

Removing old ids: the previously indexed body is in `vfs_versions.content` (brief corrected, section 1), but nothing records which version the index posted, and spec 180's pack will turn cold rows into diffs. Removal needs an `indexed_version` stamp per entry and a reconstruct per dirty entry. Without removal, ghosts accumulate in the base — harmless for grep, a crash for glean (section 1) unless `lex_docs` is pruned as in A.

Verdict: not viable on Postgres, SQL Server or Oracle at this corpus size. It is viable only for tens of documents on SQLite, which is not the target.

## 6. Option D — make the overlay cheaper instead

**D1 — a complete, paged overlay.** Replace the silent 500-entry ceiling (`OVERLAY_BUDGET`; `test_the_overlay_budget_truncates_loudly` pins the warning) with paged scoring until the wall budget, then a loud record. Against the scenario without any refresh, the `NOT encoded` set is 10k–50k by the end of the day: 40–200 MB of body fetch per glean call, tokenised at ~75 MB/s in Rust (spec 130 landing: 14.4 s for the linux checkout) → 0.5–3 s of CPU and I/O **per query**, on top of a 10k–50k-row path-ordered scan. Agents issue many queries concurrently; this is O(dirty × QPS) against the database. It cannot be the answer to the scenario. It **is** worth doing on its own merits: today glean serves 500 of 10k dirty entries with a warning, which is a correctness gap, and "page until the wall, then say so" is the honest shape (grep already pages its scan tier by `CONTENT_BYTE_BUDGET` and consults the deadline).

**D2 — per-entry mini posting sets written at refresh time.** A forward index: one blob per dirty entry holding its distinct gram set, written by a lease-held refresh so the scan tier can pre-filter by gram instead of reading bodies. Two problems. A 4 KB body has ~2,500 distinct trigrams at ≥ 3 bytes each — the gram set is **larger than the body**; for grep the mini set saves nothing. For the lexical leg a `(term, tf)` vector is smaller than the body and skips tokenising, but every query still reads every dirty entry's vector: the cost class is unchanged, O(dirty) per query. And the moment a lease-held pass over the dirty bodies exists, building a real inverted delta (A) costs the same pass and turns the per-query cost into O(query).

Verdict: D1 as hygiene, independent of refresh; D2 no.

## 7. What the embed step and the path-segment postings teach

The **embed step** (`embed.py`) is incremental because its unit of work is a row with its own dirty state (`embedding IS NULL`) and its landing is idempotent (`UPDATE … WHERE embedding IS NULL`). It pages by keyset, holds no transaction across provider calls, and resumes from the first NULL after a crash. The gram and lexical indexes have no per-row unit — the unit is a per-gram blob over many entries — which is exactly why they cannot land per row and need a segment (a batch with its own identity) as the incremental unit. The embed step also shows that a refresh verb should run the dirty-bounded phases that already exist (render, chunk, embed): they cost nothing extra and they are what makes the vector leg fresh.

The **path-segment postings** (`segments.py`) are maintained synchronously inside the writing transaction because the per-entry delta is small (3–10 `(segment, entry_id)` rows) and is set arithmetic on names. Trigrams are ~2,500 rows per entry — two to three orders of magnitude more — which is why they are blobs, and why a synchronous write-path maintenance was never on the table under the no-extra-write-latency rule. Their reindex re-convergence — compute drift from a plain read, apply each delta under a per-row guard, skip a guard miss because the concurrent writer is the truth — is the pattern for any future repair of the segment manifest, and the model the compaction follows (rebuild from the bodies, which are the truth).

## 8. The cadence table

Slice 1 (append-only deltas, no compaction), daytime 4 h gap between full rebuilds, 1 %–5 % daily churn. "Rows per gram" is the `_posting_meta` fan-out for one gram; "head rows per term" is round one's worst case for a term present in every segment (`HEAD_BLOCKS = 8`).

| Cadence | Dirty per delta | Deltas per 4 h gap | Live segments `|S|` | grep: rows per gram | glean: head rows per term | `NOT encoded` at query time vs `OVERLAY_BUDGET = 500` | Tiering (slice 2) |
|---|---|---|---|---|---|---|---|
| 5 min | 100–500 | 48 | 49 | 49 | ≤ 392 | 100–500: within budget | Needed; fan-in 8 keeps `|S|` ≤ 9 |
| 15 min | 300–1,500 | 16 | 17 | 17 | ≤ 136 | 300–1,500: exceeds at 5 % | Recommended |
| 30 min | 600–3,000 | 8 | 9 | 9 | ≤ 72 | exceeds | Optional |
| 60 min | 1,250–6,250 | 4 | 5 | 5 | ≤ 40 | exceeds | Not needed |

Readings. Statement counts per grep and glean call are unchanged except the one live-set read; row counts multiply by `|S|`; blob bytes stay dominated by the base (delta blobs are hundreds of bytes to a few KB). grep is comfortable at every cadence. glean's round one at 49 segments is where tiering pays. The overnight gap mostly produces no-op refreshes (nothing dirty, no segment minted). The cadence also governs glean's overlay today: at 5 minutes the un-refreshed remainder sits inside the 500-entry overlay budget, so glean's lexical leg becomes complete without D1; at 30–60 minutes D1 still matters. During a full rebuild (about an hour at 1M files) refreshes are refused by the lease in slices 1–2.

## 9. Recommendation

Option A, in three slices plus one independent hygiene slice.

**Slice 1 — `refresh()` with append-only deltas.** The verb; `gram_epochs.base_epoch`/`published_at`/`retired_at`; `meta.index_generation`; `pointer_with_overlay` returning the generation; the live-set read; `_posting_meta`/`_posting_blobs` over the set with summed meta; kernel K1 (slot union); `lexical_stats` and `_chunk_ranking` over the set with `(term, epoch)` slots; kernel K2 (`finish_under`); the `lex_docs` ghost delete at publish; the generation CAS; the extended reclaim rule; `_work_pending` counting live deltas; the full rebuild bumping the generation. Tests first at each layer: a delta publish flips exactly the covered pairs; grep finds a fresh body through the delta with no scan; glean ranks a delta chunk and never `KeyError`s on a re-split entry; the two-read protocol redrives on a delta publish; rival refresh loses the generation CAS cleanly; a full rebuild reclaims every delta; no statement grows with the dirty set (the `before_cursor_execute` bind-count pin, as `test_no_reindex_statement_grows_with_entry_count` does). Target: 30–60 minute cadence in production from day one.

**Slice 2 — the fold compaction.** `vfs_segment_members`; `MERGE_FAN_IN`; R4; `retired_at` sweep. Enables 5–15 minute cadence.

**Slice 3 — refresh during a full rebuild.** Insert the `gram_epochs` row at the *start* of a build (a reservation; `published_at` NULL) so a rival mint sees it; split the lease into two kinds (one full, one refresh) with the CAS rules above arbitrating; the delta on the old base is swept when the full publishes. Removes the hour-long refresh blackout.

**Hygiene, independent of the above.** D1 (page the overlay to the wall budget, then record); demote `encoded` in the generation-law re-dirty so the glean `KeyError` is unreachable in the full path too.

The first slice is slice 1, and inside it the first landing is the smallest coherent unit: schema columns + generation token + readers comparing the generation (no behaviour change yet), then the delta build and publish for grep only (K1), then the lexical half (K2 and the `lex_docs` delete). Each leaves the tree green and the full rebuild authoritative.

## 10. Decisions a spec would record

1. **A new verb `refresh()`, not a mode of `reindex()`.** Reason: the constitution's Article 2 (declared capabilities) and Article 5 ("cost is part of the contract") — `reindex` is O(corpus) and holds the lease for an hour at 1M files; `refresh` is O(dirty). A caller must be able to tell them apart without executing either. `protocol.py` gains the op beside `reindex`.
2. **A delta is an epoch number in the existing epoch-scoped tables, marked by `gram_epochs.base_epoch`.** Reason: `epoch_scoped()`, `bulk_insert`, the PK-collision arbitration and the range-delete reclaim all keep working; no second table family.
3. **The readers' coherence token is `meta.index_generation`, bumped by every publish.** Reason: the two-read protocol compares one integer; the pointer alone cannot see a delta publish.
4. **The live set is derived from `gram_epochs` by one statement per call** (not denormalised onto the meta row). Reason: a normalised set is the data model's honest shape, and the generation compare already closes the straddle. Recorded as a deliberate choice with the one-statement cost named; the denormalised column is the fallback if the statement ever shows in a measurement.
5. **Deltas score under the base's `avg_dl` and the base's idf where the term exists, else their own idf under the summed N — the overlay's law.** Reason: one scale for index side, deltas and overlay; the drift is bounded by the churn (≤ 5 %) and reset by every full rebuild.
6. **A refresh with no base runs the full build.** Reason: the first index of a corpus is the corpus; a delta against nothing is a full build with a worse name.
7. **`_work_pending` is true when live deltas exist.** Reason: a scheduled full rebuild must fold deltas back even when nothing is dirty, or they persist until the next dirty write.
8. **The publish of a delta deletes `lex_docs` rows of the covered entries in the live set.** Reason: the ghost-chunk `KeyError` in `glean._observe` (section 1); a bounded delete at publish beats a per-query existence join.
9. **Compaction members live in `vfs_segment_members`** rather than being derived from `lex_docs`. Reason: the gram and lexical coverage sets coincide only by an argument about `Chunk.split`; a members table says what a delta covers without that argument.
10. **Compaction is a fold from bodies, not a blob merge.** Reason: no tombstone set, ghosts vanish, and the cost (`fan_in × delta` bodies) is trivial at these sizes; a blob-merge kernel can come later if ever measured to matter.
11. **`MERGE_FAN_IN` is a merge trigger, not a scale cap.** Reason: CLAUDE.md's never-design-a-cap rule; the value bounds read fan-out, never corpus or dirty volume.
12. **The refresh runs render, chunk and embed; it does not run segments, edges, signals or pack.** Reason: the first three are already dirty-bounded; the others are whole-corpus by nature and belong to `reindex`.
13. **The two kernel changes** — K1 `candidate_ids` with per-slot union, K2 `LexicalBuilder.finish_under(n_docs, avg_dl, idfs)` plus a vocabulary accessor — **land in `crates/vfs-core` with oracle parity**, per the Rust-engine rule.
14. **The lease stays shared in slices 1–2; slice 3 splits it with an early epoch reservation.** Reason: shipping the simple arbiter first; the generation CAS and the `base_epoch ≠ current` sweep already make a lease lapse harmless.
15. **A refresh refuses on fingerprint drift and names `reindex`.** Reason: a delta built under different options against an old base mixes formats; the full rebuild is the migration path, as today.

## 11. Risks

- **Row volume between rebuilds on the real engines.** ~5–7M delta rows per 4 h at 5 min; the full rebuild's reclaim already deletes an old epoch of millions of rows, so the order is familiar, but Postgres autovacuum and SQL Server LOB churn should be measured on the Docker legs before the cadence is advertised.
- **glean round-one fan-out before slice 2.** At 49 segments a common term fetches up to 392 head rows; the scorer is linear in postings and delta blocks are small, but the row count is new. Slice 2 is the mitigation; until it lands, recommend ≥ 30 minutes.
- **The `|S|` bind reserve.** Every statement that carries `epoch IN (S)` must subtract `|S|` from its membership chunk, not rely on `_FILTER_BIND_RESERVE`. A pin with a tightened budget (as `test_no_reindex_statement_grows_with_entry_count` does) should hold `|S|` at the slice-1 maximum.
- **Ghost cost in grep's candidate budget.** Stale nominations count against `CANDIDATE_BUDGET`; at ≤ 5 % churn the ghost share is small, and the truncation record stays honest.
- **Statistics drift for brand-new terms across deltas.** A few parts in a thousand in idf; reset by the full rebuild. The export must report summed df so the envelope does not under-state.
- **The hour-long refresh blackout during a full rebuild** (slices 1–2). Known and bounded; slice 3 removes it.
- **The full rebuild's residency is untouched.** Tens of gigabytes at 1M files. This study does not fix it and says so; the partitioned build remains the named direction.
- **Doc-id stability assumption.** `entry.id` is stable across overwrites and revives; a purge followed by a new write at the same path mints a new id, which is correct (the old id's postings are swept with the epoch). If a future change ever re-keyed postings on something that moves with content, the ghost argument would need revisiting.
- **The `_visible_lexicon` path for partial views** multiplies its already-disclosed cost by segments the term appears in. Acceptable for the same reason the current profile is; worth a sentence in its docstring.
