# 104 — Path terms in candidate nomination: the segment index and glob pushdown

- **Status: slices A and B landed 2026-08-17** (drafted earlier the
  same day) — slice A: the segment table (`{table}_segments`, schema
  format 4), §2 maintenance across write/mkdir/move/copy/trash/
  restore/delete/purge and the trash-chain mint, and the reindex
  re-convergence (running after the gram phases; the guard re-read
  locks the entry rows so a rival path rewrite serializes instead of
  interleaving), pinned by the mirror battery + phase-boundary tests
  in `tests/storage/database/test_segments.py` and per-engine
  cascade legs in `tests/storage/test_conformance.py` (skip without
  servers; not yet run against real engines). Slice B: the §3 term
  compiler and the allow-list seam
  (`storage/backends/database/pathterms.py` — `compile_terms` /
  `compile_channel` / `allow_list_ids`, plain int sets, ids in the
  surrogate doc-id space via one indexed join per term; an arm is
  allow-list-bounded only by segment terms, ext/name facts compile
  as pushdown predicates for slice C), pinned by the superset
  battery in `tests/storage/database/test_pathterms.py` (generated
  paths × generated globs: nomination ⊇ authority, exclusions
  structurally absent from the seam). Slice C: §4 in grep nomination
  (the allow-list intersects gram candidates *before* the budget —
  the recall fix, pinned by the saturated-budget regression test — a
  dead scope short-circuits the ladder, an unbounded arm falls back
  whole) and §5's pushdown + string gate (`GlobFilter.hits` /
  `passes_row_filters` over the stored `name`/`ext` columns, parity
  pinned; channel facts + wanted-ext + gateless meta liveness ride
  the candidate-fetch SQL, binds netted from the id chunks).
  Measured on the rebuilt linux store (write 53 s vs 45 s pre-104 —
  segment maintenance ≈ 85 µs/file at ETL scale; reindex 196 s vs
  191 s — the drift collect ≈ 5 s): the 25-row unscoped ladder shows
  **zero regressions, identical counts, and 11–19 % wins on
  saturated rows** (the gate skip + string gate); seven targeted
  scoped rows all match rg's positional-path counts line-for-line,
  with the headline `copyright -i` under `fs/ext4` at 25 ms vs
  1,182 ms (truncated) unscoped, and vfs 0.5–3.3× of rg positional
  across the set. Slice D (the recorded scoped study + budget
  re-derivation) pending.
  Born from the path-indexing research arc: the prior-art memo
  (`../../../research/2026-08-17-path-indexing-prior-art.md`, field
  study + fork evidence + usage mining, studies under
  `../../../research/studies/2026-08-17-path-indexing-prior-art/`),
  Clay's in-session resolutions of the four forks (term shape,
  maintenance mode, planner placement, multi-surface contract), and
  the decision set recorded as **ADR 040**.
- **Date:** 2026-08-17
- **Owner:** Clay Gendron
- **Kind:** a second posting family (path segments) beside the
  content grams, maintained transactionally by the write and
  topology verbs, consumed by grep nomination and the glob verb
  behind unchanged contracts — the verbs, the glob language, the
  Result shapes, and the match/glob authorities do not move.
- **Depends on:** ADR 040 (this story's decision set), ADR 031
  (pattern-only glob seam — preserved), ADR 033 (nomination/verify
  split, budgets, epoch lifecycle), ADR 039 / spec 103 (the landed
  Rust read path this composes with).
- **Relates to:** ADR 007 (`glean` — future consumer of the
  allow-list seam), ADR 036 (chunks keyed by entry identity — the
  join target for glean pre-filtering), the linux benchmark study
  (`../../../research/studies/2026-08-16-linux-grep-benchmark/`).

## Intent

Glob predicates today run after nomination and after truncation:
every saturated grep call fetches 25,000 candidates' entry rows,
builds a validated `Path` per row (~121 ms), and only then applies
the glob — and a scoped query on a wide pattern can silently lose
recall because the budget was spent on out-of-scope candidates. The
observed workload (10,519 mined agent searches) is 99.4% scoped,
with directory scope + extension ~86% of all glob use.

The laws that bind every slice:

1. **Nomination is a superset; the compiled glob stays the sole
   authority.** Segment terms may over-nominate (they are unordered
   ancestor facts); they must never under-nominate. Exclusion
   channels never prune nomination. Every survivor is re-checked by
   the compiled `GlobFilter` — the universal superset-then-recheck
   contract.
2. **Path postings belong to the path column's consistency
   domain.** They are maintained in the same transactions that
   write or rewrite `path`, never epoch-cycled: after every verb,
   at every commit boundary, the postings mirror the column. No
   flag, no overlay arm, no staleness window.
3. **Scoping still arrives as pattern text** (ADR 031). The
   allow-list is an internal storage-layer artifact compiled from
   the glob channels; no path channel crosses the seam.

## Shape

- **§1 The segment posting table.** One row per (segment,
  entry_id): `segment` is one ancestor directory name from the
  entry's path (the leaf is excluded — the `name` column serves
  it), deduped per entry; every entry row of every kind carries its
  postings, trash included (the invariant is mechanical, liveness
  stays a resolution-time concern as today). Primary key
  `(segment, entry_id)`; a secondary index on `entry_id` serves
  delete-by-entry and cascade deltas. Segment text is verbatim —
  glob matching is case-sensitive. Measured floor: 3.8 rows per
  file, 3,087-term vocabulary at linux scale (93,760 files).

- **§2 Write-path maintenance.** Each verb extends statements it
  already runs, inside its existing transaction: writes bulk-insert
  postings beside entry inserts (overwrites are path-preserving
  no-ops); moves derive a postings delta from the descendant
  rewrite list they already compute — old/new segment sets per
  rewritten row, batched delete+insert — with the pure-rename fast
  path (one component renamed, ancestors unchanged) reduced to a
  single scoped `UPDATE`; copy inserts postings for the new rows;
  trash and restore are moves and ride the same cascade; hard
  delete removes postings by entry id. All statements chunk by the
  declared budgets (`membership_budget`, `rows_per_statement`) like
  their neighbors. Measured: ~174 ms per 10,000-file batch,
  ~0.6 ms per single-file write, ~50 ms for a 37,768-descendant
  rename via one `UPDATE`. **Reindex rebuilds the postings —
  wholesale in effect, guarded delta in application** (Clay,
  2026-08-17): a reindex phase converges the table to exactly the
  recomputed segments of every live path (a drop-and-rebuild's end
  state, so drift cannot accumulate — including from a future
  path-rewriting verb that forgets its postings), applied in
  budget-chunked transactions guarded by the path each delta was
  computed from; a guard miss skips the row — the concurrent
  writer's synchronous maintenance is the truth. Found drift is
  reported loudly (it is a §2 bug being surfaced). A literal
  drop-and-rebuild stays reserved for format changes: without
  epochs, which this table deliberately lacks, it would block every
  writer or revert concurrent commits from a stale snapshot.

- **§3 Term compilation — glob text to (segments, predicates).**
  From each admission glob's canonical anchored form, per brace
  expansion arm: literal path components in directory position
  (wildcard-free, class-free) each contribute one segment term; the
  existing `derive_ext` fact and basename-literal / stem-prefix
  tails contribute `ext` / `name` column predicates; wildcard and
  class components contribute nothing. Soundness: a path matched by
  the glob necessarily has every literal directory component among
  its ancestor segments, so the term conjunction over-approximates
  — position and order are the authority's job. The admissions
  channel is an OR: the allow-list is the union of per-glob sets,
  and it exists only if *every* admission glob yielded a bounded
  set (one unbounded arm voids pruning for the call). Exclusions
  compile to nothing, by law 1.

- **§4 Grep nomination integration.** The compiled terms' sorted
  entry-id postings (one indexed `SELECT` per term) enter the
  rarest-first intersection as peers of the gram postings — a
  scoped-wide query starts from the rarest posting of either kind
  (`copyright` under `ext4`: 80 ids, not 58,000; intersection
  measured 61–133 µs at any width). Segment postings are live truth
  while gram postings are epoch-scoped over `encoded` rows; the
  index tier already serves only `encoded` rows, so the
  intersection is sound, and the scan-tier overlay keeps its own
  glob arms. `CANDIDATE_BUDGET` applies after the intersection —
  the budget counts scoped candidates, which is the recall fix.

- **§5 Column pushdown and the string-based gate.** The `ext` and
  `name` predicates from §3 join the candidate entry fetch and the
  scan-tier arms as SQL `WHERE` terms (the `ext` column exists
  today and is read by nothing on this path). The per-candidate
  gate drops its `Path` construction (~121 ms per saturated call)
  and matches raw path strings; when all four channels are empty
  the gate is skipped entirely. The authority recheck of §3's
  supersets happens here, unconditionally.

- **§6 The scoped bench gate.** A new dated study extends the
  25-row linux benchmark with the usage-mined scope shapes —
  directory scope (shallow, 1–3 segments), bare extension,
  directory + extension, exclusion, stem wildcard — with rg
  compared in its **positional-path form** (walk pruning enabled;
  the hardest fair comparison) and a **recall column**: vfs row
  counts must match rg's, not merely beat its wall time. The
  unscoped 25 rows must not regress, the ladder re-runs (including
  write-batch timings to bound §2's overhead in context), and any
  budget re-derivation is recorded like spec 103's.

## Slices

- **A. Schema and maintenance.** The segment table in
  `models/rows.py`; §2 maintenance across write, move, copy, trash,
  restore, delete, plus the reindex rebuild phase (wholesale in
  effect, guarded delta in application, loud on found drift); the
  mirror invariant pinned by a property-style battery (after every
  verb sequence, postings == recomputed segments of every live
  path) plus `db_test` legs for the cascade statements on the real
  engines.
- **B. The term compiler and the allow-list seam.** The §3 compiler
  beside the glob module's consumers in the storage layer; the seam
  module yielding entry-id sets from the glob channels; a superset
  battery (generated paths × generated globs: term-set nomination ⊇
  authority matches, exclusions never consulted).
- **C. Grep integration and pushdown.** §4 in the planner's
  intersection, §5's SQL pushdown and string gate; ladder re-run
  and targeted scoped measurements; the recall defect's regression
  test (scoped-wide query whose in-scope rows exceed none of the
  budget — full recall required).
- **D. The scoped bench gate and the record.** The §6 study
  executed and recorded; budget consequences re-derived if the
  numbers move them; ADR 040 amended if any slice contradicted it;
  spec status updated for the mining pass.

## Open questions

- **Scan-tier segment join.** The overlay's SQL currently prefilters
  with LIKE arms; joining the segment table there too may help
  `allow_scan` sweeps. Measure in slice C; adopt only on evidence.
- **Glob-verb adoption.** The glob verb's LIKE-superset arms could
  consult the allow-list seam for its candidate nomination as well.
  Same posture: wire it in slice C if the seam makes it nearly
  free, else record as follow-up.
- **Cascade statement shapes per dialect.** The single-`UPDATE`
  rename fast path wants an UPDATE-with-join or IN-chunked form on
  MSSQL/Oracle; slice A picks shapes with `db_test` evidence, under
  the declared budgets.
- **Glean pre-filtering.** The seam is designed for it (ADR 007's
  `paths` scope; chunks keyed by entry identity), but glean has no
  live implementation; the hookup belongs to the glean story, not
  this one.
