# Mutant ledger — proven bugs the suite must keep killing

**Status:** live — founded 2026-08-25 (ADR 050); appended to by every
review campaign that lands pins.
**Purpose:** Each row is a one-line bug that once survived the whole
suite and was killed by a landed pin. Replaying a row re-proves the
pin still has teeth. Replays run **during review campaigns** — the
`test_review` skill owns the procedure — not as standing CI.

## Replay protocol

**Never mutate the live repo** — review agents run concurrently
against it, and a briefly-mutated `src/` poisons every neighbor's
reads and test runs. All replays happen in an isolated tree under the
session scratchpad: `git worktree add <scratchpad>/mutant-tree
<tip-sha>`, primed once with `uv sync`, removed when done (the
`test_review` skill carries the full protocol).

For each row in scope (target file touched by the review, plus any
row when time allows — the full ledger replays in ~2 minutes):

1. Apply the mutation **in the worktree**. Rows record **intent plus
   the best-known anchor**; if the anchor text has moved, re-derive
   the mutation from the intent before declaring anything.
2. Run the row's scope selection from the worktree. **Killed** = ≥1
   failure.
3. Restore the worktree file from its committed state
   (`git -C <worktree> checkout -- <file>`) and confirm the worktree
   is clean before the next row.

Statuses, all reported: **killed** (healthy), **survived** (a pin
regressed — a critical review finding), **stale** (the mutation's
concept no longer exists in the code — propose retiring the row, with
the reasoning; never silently skip). The *recorded killers* column is
advisory diagnosis only — which test kills a mutant drifts even when
protection holds (see M5, the founding example) — the assertion is
always "≥1 failure in scope", never a named test.

## Rows

| id | mutation (intent → anchor) | target | scope | recorded killers (advisory) | provenance |
|---|---|---|---|---|---|
| R1 | `_channel_facts` emits a partial OR instead of voiding the channel (the void `return None` arm becomes `continue`) | `src/vfs/storage/backends/database/grep.py` | `tests/storage/` | mixed-channel storage row; `_channel_facts` void unit row; contract battery mixed-channel row (memory leg) | spec 109 |
| R2 | `_arm_ids` intersects only the rarest term: `ranked[:_INTERSECT_TERMS]` → `ranked[:1]` | `src/vfs/storage/backends/database/pathterms.py` | `tests/storage/database/` | term-overlap decoy row; wide-arm slice row; `test_multi_term_arms_intersect` | spec 109 |
| R3 | `_CANDIDATE_COST_US` 75.0 → 7.5 | `src/vfs/storage/backends/database/grep.py` | `tests/storage/database/` | `_ladder_defers` boundary rows (4 failures re-verified 2026-08-25) | spec 109 |
| R4 | `_CANDIDATE_COST_US` 75.0 → 750.0 | same | same | ladder boundary rows (3) | spec 109 |
| R5 | `_GROUP_SETUP_US` 500.0 → 5000.0 | same | same | ladder boundary rows (4) | spec 109 |
| R6 | `_GROUP_SETUP_US` 500.0 → 50.0 | same | same | ladder boundary rows (3) | spec 109 |
| R7 | `_POSTING_COST_US_PER_BYTE` 0.055 → 0.55 | same | same | defer/ladder spy row (1) | spec 109 |
| R8 | `_POSTING_COST_US_PER_BYTE` 0.055 → 0.0055 | same | same | defer/ladder spy row (1) | spec 109 |
| M1 | delete flushes only its last root posting delta: the accumulated `segment_moves` batch → `segment_moves[-1:]` at the `move_postings` flush | `src/vfs/storage/backends/database/topology.py` | `tests/storage/` | batch delete row; batch restore row | spec 113 |
| M2 | `_execute_move` mirrors only the batch's last pair (identity at width 1) | same | same | batch move row; batch restore row | spec 113 |
| M3 | grep's hoisted projection or row-mask is widened by the ridden row-gate columns, at the `projected`/`row_mask` hoist above the assembly loop — **both directions are the mutation**: mask alone (a wire-mask leak) and projection alone (a valued field outside the mask) | `src/vfs/storage/backends/database/grep.py` | `tests/storage/` | mask direction: grep exact-mask row (`columns={"content"}`); projection direction: the same row's `size_bytes is None` value assert + the conformance mask law's narrow-columns grep rows (3 failures, proven 2026-08-25) | spec 113; projection direction pinned + anchor tightened by spec 124 |
| M4 | glob observes the queried mask instead of the requested one | `src/vfs/storage/backends/database/reads.py` | `tests/storage/database/` | glob exact-mask row (`columns={"path"}`) | spec 113 |
| M5 | the overlay-emptiness verdict is presumed verified: `skip_verified = False` → `True` | `src/vfs/storage/backends/database/grep.py` | `tests/storage/database/test_grep.py` | recorded: the epoch-spy rescued-verdict row — **drifted 2026-08-25**: that row now passes under the mutant; killed instead by two `TestEpochLadder` rows and the scan-path statement-count pin (3 failures). The row that made killers advisory-only. | spec 113 |
| C1 | ladder-defer comparator tie at the exact crossover (`allow_size=80`) — flip the comparator's strictness | `src/vfs/storage/backends/database/grep.py` | `tests/storage/database/` | **none — designed-inert**: the tie is observationally inert, so this row is *expected to survive*. Carried for visibility; it becomes a real row only if a comparator-strictness pin ever lands. Never report it as a regression. | remediation decision pass 2026-08-18 |
| P1 | fingerprint-skip ignores the chunk generation (drop `row.chunk_generation == generation` from the skip condition) | `src/vfs/storage/backends/database/indexing.py` | `tests/storage/database/test_indexing.py` | `TestChunkProvenance::test_generation_change_redirties_and_resplits` (1 failure, proven 2026-08-25) | spec 117 slice C |
| P2 | fingerprint-skip ignores the body hash (drop `row.content_hash == row.chunk_source_hash`; skip fires on any current-generation row) | `src/vfs/storage/backends/database/indexing.py` | `tests/storage/database/test_indexing.py` | `TestChunkProvenance::test_changed_body_still_resplits` (1 failure, proven 2026-08-25) | spec 117 slice C |
| P3 | the verify budget cut moves to submit time (`deadline - monotonic()` hoisted out of the worker fn in both arms) — queue wait silently extends the wall | `src/vfs/storage/backends/database/offload.py` | `tests/storage/database/test_offload.py` | the two queue-wait budget rows (2 failures, proven 2026-08-25) | spec 118 slice A |
| P4 | the one-in-flight guard is deleted (`if self._in_flight: raise` removed), letting a second batch race the first onto the pool | `src/vfs/storage/backends/database/offload.py` | `tests/storage/database/test_offload.py` | `TestVerifyOffload::test_overlapping_calls_are_refused` (1 failure, proven 2026-08-25) | spec 118 slice A |
| P5 | verify runs inline: `_run`'s `run_in_executor` call becomes `return guarded()`, holding the loop for the whole batch | `src/vfs/storage/backends/database/offload.py` | `tests/storage/database/test_offload.py` | the tick-gap responsiveness row; every `TestAbandonment` row (8 failures, proven 2026-08-25) | spec 118 slice C |
| P6 | the generation re-dirty runs unconditionally (probe deleted, the UPDATE issued on every pass) — RR engines scan-lock the whole entry table in the steady state | `src/vfs/storage/backends/database/indexing.py` | `tests/storage/database/test_indexing.py` | `test_flag_flips_are_set_based_not_per_row` + `test_steady_state_reindex_issues_no_entry_update` (2 failures, proven 2026-08-25); the MySQL lock-scope race row on the live leg | spec 121 |
| P7 | the probe's verdict is inverted (`is not None` → `is None`) — stale generations never re-dirty | `src/vfs/storage/backends/database/indexing.py` | `tests/storage/database/test_indexing.py` | `TestChunkProvenance::test_generation_change_redirties_and_resplits` (1 failure, proven 2026-08-25) | spec 121 |
| P8 | close shuts the verify pool but keeps the dead slot (`self._verify_executor = None` removed) — every later grep limps through the fallback forever | `src/vfs/storage/backends/database/engine.py` | `tests/storage/database/test_offload.py` | `test_close_shuts_the_pool_down_without_waiting`'s re-mint asserts (1 failure, proven 2026-08-25) | spec 122 |
| P9 | the close-window inline fallback re-raises instead of serving (`return guarded()` → `raise`) — a grep racing close escapes a raw RuntimeError | `src/vfs/storage/backends/database/offload.py` | `tests/storage/database/test_offload.py` | `test_a_grep_racing_close_is_served_whole` (1 failure, proven 2026-08-25) | spec 122 |
| P10 | the ready latch survives close (`self._ready = False` removed) — the first op after close serves a catalog miss off the stale latch | `src/vfs/storage/backends/database/engine.py` | `tests/storage/test_conformance.py` | `TestMemoryConformance::test_pattern_search_serves_after_close` (1 failure, proven 2026-08-25) | spec 122 |
| P11 | the kernel-metadata reads lose their isinstance guards (revert to `.get(...) or {}` / `.lower()` chains) — a valid .ipynb with non-string `kernelspec.language` raises raw AttributeError and wedges every reindex | `src/vfs/models/chunking.py` | `tests/models/` + `tests/storage/database/test_indexing.py` | metadata degradation battery, `test_split_batch_matches_per_file_splits_across_routes`, `test_a_malformed_notebook_never_wedges_the_reindex` (3 failures, proven 2026-08-25) | spec 123 |
| P12 | the whole-text slice-end zero-width discard loses a direction — over-serve: the guard deleted whole (phantom boundary matches, cap displacement); over-discard: the `and stop < len(text)` EOF qualifier deleted (genuine `$` matches at end of unterminated bodies silently lost, budgeted and unbudgeted). Anchor: the guard lives once, in the `_whole_matches` driver both whole-text consumers share (unified by spec 125; both directions replayed and killed there, 4 failures each) | `src/vfs/pattern_matching/grep.py` | `tests/pattern_matching/test_matcher_parity.py` | over-serve: fabrication/displacement/boundary rows (4, proven at spec 112); over-discard: `test_a_zero_width_match_at_eof_is_served` + the `$` CASE riding every sweep (4 failures, proven 2026-08-25) | specs 112 + 124; anchor re-derived by spec 125 |
| P13 | the candidate-budget truncation record duplicates at the storage seam: either dedupe guard deleted — the index-side cut and the scan-overflow append each emit, and only the facade's merge hides the twin | `src/vfs/storage/backends/database/grep.py` | `tests/storage/database/test_grep.py` | `TestBudgets::test_the_candidate_budget_record_is_emitted_at_most_once` (1 failure, proven 2026-08-25) | spec 125 |
