# 105 — The overlay probe's fixed cost: composite index and the emptiness gate

- **Status: all slices landed 2026-08-17** (drafted the same day) —
  slice A: the composite `(encoded, kind)` index, schema format 5,
  shape-pinned with per-engine `db_test` reflection legs; the real
  write path measured unchanged (10k-file batches −0.96%, within
  noise). Slice B: `_pointer_with_overlay` — the epoch pointer and
  the overlay-EXISTS verdict in one statement (CASE-wrapped for
  MSSQL), the scan tier skipped only on a same-snapshot empty
  verdict; pinned by a scan spy over all five behaviors, the
  epoch-redrive pin moved to the one-re-read-per-attempt cadence.
  Slice C: store rebuilt on format 5 — **write 47 s (53 s prior),
  reindex 175 s (196 s)**, so the flip overhead is invisible
  end-to-end — and both ladders re-ran with identical counts on
  every row: unscoped rows all faster (zero-hit floor 68.8 →
  55.4 ms warm; `copyright -i` 712 → 665 ms; `kfree` 456 → 417 ms),
  scoped rows all faster with recall exact (`copyright -i @
  fs/ext4` 8.0 → 5.4 ms vs rg 8.9; `obj- @ Makefile` 130.8 →
  79.4 ms vs rg 149.7; `spin_lock` 23.4 → 18.6 vs rg 17.3;
  `GFP_KERNEL @ mm` 15.6 → 11.9 vs rg 11.2 — the last two inside
  rg's own run-to-run variance, which also moved between sessions).
  **Ready for the mining pass.**
  Born from the overlay-probe research memo
  (`../../../research/2026-08-17-overlay-probe-cost.md`, studies
  under `../../../research/studies/2026-08-17-overlay-probe-index/`),
  which decomposed the ~1.6–2.5 ms scan-tier probe paid on every grep
  call, refuted the partial-index hypothesis by measurement, and
  landed on the two mechanisms this spec adopts.
- **Date:** 2026-08-17
- **Owner:** Clay Gendron
- **Kind:** one index swap in the entry-table schema plus one query
  change in grep's per-call preamble. No contract, verb, or Result
  shape moves; no new posting family; no write-path statement
  changes beyond what the index itself implies.
- **Depends on:** the overlay-probe research memo (measured
  constants below), spec 093/097 (the grep pipeline and its scan
  tier), spec 095 (reindex phases — the index rides the existing
  rebuild machinery), spec 104 (the current grep preamble this
  extends).
- **Relates to:** the trash-pollution design fork (open question
  below — deliberately *not* resolved by this spec).

## Intent

Every grep call probes the scan tier for `NOT encoded` rows so index
staleness can never lose a match. The research measured the probe at
~1.7 ms and located the cost precisely: the existing single-column
`encoded` index serves the seek, but its `encoded = 0` set is
polluted — 6,160 directories at linux scale, each paying a rowid
lookup into the 3.4 GB table only to be rejected by the `kind`
filter (~1.2 ms of the probe). A further ~300–400 µs is statement
build plus driver hop, removable only by not issuing the statement.

Two mechanisms, both measured on store clones:

1. **A composite `(encoded, kind)` index** replacing the
   single-column one: probe DB time 1,070 → 5.5 µs on an empty
   overlay, 1,340 → 180 µs steady-state; maintenance +2.2% on a
   10k-row `encoded=0` insert, +5.5% on the 103k-row reindex flip;
   +640 KiB at linux scale. Plain B-tree — identical on every
   engine, no dialect forks, no `DialectProfile` field.
2. **An overlay-emptiness gate riding the epoch read**: a scalar
   `EXISTS` subquery on the epoch-pointer statement grep already
   executes — measured marginal cost ≈ 0 (pointer read alone
   186–223 µs; pointer + EXISTS 165–187 µs) — skipping the scan
   statement entirely when the overlay is empty.

Laws that bind the slices:

1. **The scan tier's semantics do not move.** The overlay query,
   its LIKE arms, its ordering, and its truncation reporting stay
   exactly as they are; this spec only makes the probe cheap and
   skippable-when-empty. Recall is the contract.
2. **The emptiness gate must be coherent with the call's snapshot.**
   The EXISTS rides the same statement (same transaction, same
   round trip) as the epoch-pointer read; a non-empty verdict runs
   the scan tier exactly as today. False non-empty is harmless
   (wasted probe); false empty must be impossible within the
   snapshot the call already trusts.
3. **The gate predicate is ORM-built, never raw text.** SQLAlchemy
   renders `~entry.c.encoded` as an inline literal on every dialect
   (`encoded = 0` / `NOT encoded`), which is what makes the seek
   reachable under SQLite's textual matching and MSSQL's
   parameterization rules. A hand-written `NOT encoded` text clause
   measured as a full-table scan.

## Shape

- **§1 The composite index.** In `models/rows.py`, replace
  `ix_{table_name}_encoded` (single-column) with
  `ix_{table_name}_encoded_kind` on `(encoded, kind)`, and bump
  `SCHEMA_FORMAT_VERSION`. Rewrite the comment beside it: the old
  text ("measured faster than an (encoded, kind) composite") is
  contradicted by the 2026-08-17 measurements at current scale —
  state the pollution rationale instead, without citing the memo.
  Identifier-length budget: the new name must stay within the
  63-char derived-identifier bound the existing tight-bound test
  pins.
- **§2 The emptiness gate.** Extend the epoch-pointer read in the
  grep preamble with a scalar
  `EXISTS(SELECT 1 WHERE encoded = 0 AND kind IN CONTENT_KINDS)`
  subquery (ORM-built, inline-literal by construction). When it
  returns false, `grep_rows` skips `_entries_for_scan` for the
  overlay caller only — `allow_scan` and `invert_match` callers
  are unaffected (they scan by request, not by staleness). When
  true, behavior is byte-identical to today.
- **§3 What the gate tolerates.** The overlay is legitimately
  non-empty on real corpora — the linux store carries 96
  index-ineligible files (`chunk_dirty`'s `indexable=0` rows) that
  ride the scan tier forever by design, and trashed files sit at
  `encoded = 0` until swept. Both make the gate return true and the
  call pay today's (now-cheap) probe; neither is a correctness
  problem. Reducing that steady-state set is the open fork below,
  not this spec.
- **§4 The bench gate.** Re-run the scoped 12-row study and the
  unscoped 25-row ladder: expect ~1.3 ms off every row, identical
  counts everywhere, `GFP_KERNEL @ mm/**` moving at-or-ahead of
  rg's positional form. Per-engine `db_test` legs pin the index's
  create/use shape on the real engines (skip without
  `VFS_TEST_*_URL`, like spec 104's cascade legs).

## Slices

- **A. The index swap.** §1: schema, format bump, comment rewrite,
  tight-bound identifier test updated, reindex/build compatibility
  confirmed (the index rides existing DDL machinery), `db_test`
  legs.
- **B. The gate.** §2/§3: the widened epoch read, the skip, and
  tests — a gateless call on an empty overlay issues no scan
  statement (statement-shape pin); a call with unencoded rows
  scans identically to today; trash and ineligible rows keep the
  gate honest (non-empty → probe runs).
- **C. The record.** §4's numbers into the study record; spec
  status updated for the mining pass.

## Open questions

- **Trash pollution (deliberate non-resolution).** Delete demotes
  `encoded = 0`, so trashed files match the gate and the probe's
  seek set until swept, filtered only by the liveness arms after
  row fetch. The research sketched the fix — delete stamps
  `encoded = True`, restore demotes — which would make
  `encoded = 0 ∧ kind ∈ CONTENT_KINDS` exactly the overlay and the
  gate exact. It touches trash/restore semantics and the
  `chunk_dirty` re-cover rules, so it is its own decision, taken
  with the trash-lifecycle context in view, not smuggled in here.
- **The 96 ineligible rows.** `indexable = 0` files ride the scan
  tier on every call by design. If their probe cost ever matters
  post-§1 (measured ~180 µs steady-state), the candidate design is
  a third flag state rather than a kind filter — recorded here so
  the idea is not lost; no evidence currently justifies it.
