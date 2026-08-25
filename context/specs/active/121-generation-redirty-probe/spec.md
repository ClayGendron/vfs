# 121 — A probe before the generation re-dirty: no zero-match table lock

- **Status: draft, 2026-08-25.**
- **Born from** the chunking-arc landing review
  (`../../../research/2026-08-25-chunking-arc-landing-review.md`),
  finding F2 — raised minor → major in verification when the lock
  scope, not the scan cost, turned out to be the live defect.
- **Date:** 2026-08-25
- **Owner:** Clay Gendron
- **Kind:** query-shape fix in the database backend's chunk pass.
  Semantics unchanged: the same entries end up re-dirtied; only the
  lock and scan behavior of the steady-state no-op changes.
- **Depends on:** spec 117 (the generation law whose statement this
  bounds), spec 080 / the dialect profiles (the REPEATABLE READ pin
  that makes MySQL the victim).
- **Relates to:** spec 120 (same function — sequence the two
  landings), the unverified lead on `repair_segment_drift`'s
  `with_for_update()` re-read (the *other* suspected reindex-vs-
  writer lock holder, out of scope here, recorded in the memo).

## Intent

**The generation re-dirty UPDATE write-locks the whole entry table
on MySQL — even when it matches nothing.** The unconditional first
statement of every `chunk_dirty` (`UPDATE entry SET chunked=false
WHERE chunked AND (chunk_generation IS NULL OR chunk_generation !=
gen)`) has no supporting index (`rows.py` indexes neither column),
and the dialect profile pins MySQL/MariaDB at REPEATABLE READ for
write ops. Under RR, an unindexed UPDATE takes next-key locks on
every scanned row with no semi-consistent-read release — so the
steady-state statement, which matches **zero** rows on every reindex
after the first, locks the entire entry table for the duration of
the whole reindex transaction.

Executed evidence (live MySQL, 20k entries): the zero-match statement
alone in an open RR transaction blocked a rival single-row UPDATE for
3,009 ms until lock-wait timeout — errno 1205, which the profile
classifies retryable, so a saturated deployment turns this into a
retry storm. End-to-end with a counterfactual arm (the one line
removed): concurrent write throughput during reindex drops ~3×
(9 vs 29 writes; single-write stall 3.5 s vs 1.5 s). The scan-cost
half of the original filing was the weak half — Postgres pays 63 ms
at 500k rows — and is not the motivation.

The decision pass ruled for the probe and against the index: an
index on `chunk_generation` alone is the weaker fix because
`IS NULL OR !=` is not a selective range, so RR would still lock
broadly; and the steady state should not pay the UPDATE at all.

Laws that bind the slice:

1. **The generation law is untouched.** Any entry whose stored
   chunks derive from a different engine or grammar generation is
   still re-dirtied by one set-based statement before the chunk pass
   reads the dirty set. The probe may only *skip* the statement when
   it can prove the statement would match nothing.
2. **The probe takes no locks.** It is a plain consistent read
   (LIMIT-1 existence shape, the `_pending_probe` pattern already in
   the module) — never `FOR UPDATE`, never a scan that InnoDB locks.
3. **Charged equals executed** (ADR 045's convention): if statement
   cadence is pinned anywhere for this pass, the pins name the probe
   and the conditional UPDATE honestly on both paths.

## Shape

- **§1 The probe.** A LIMIT-1 existence read for a stale-generation
  row runs first; only a hit issues the UPDATE. The steady state
  (every reindex after the first under one generation) costs one
  indexed-or-not consistent read and zero locks; the transition
  state (generation bump, engine switch) pays the UPDATE it always
  paid, now scoped to a run where it has work.
- **§2 The pins.** The lock-scope repro from the review becomes a
  test: on live MySQL, a rival single-row UPDATE during a
  steady-state reindex completes without lock-wait (the reverted
  shape is the proven mutant — it blocks). The generation law's
  existing pins (skip-ignores-generation and friends) must stay
  green; the flip-shape statement-cadence pin is updated to name the
  probe. sqlite and all four engine legs green.

## Slices

One slice — the probe, its pins, and the cadence true-up land
together.

## Open questions

- None held open here. Whether `chunk_generation` deserves an index
  for the *transition* state's scan is deliberately not taken up:
  the transition is rare, corpus-wide by definition, and already
  paid inside a maintenance verb.
