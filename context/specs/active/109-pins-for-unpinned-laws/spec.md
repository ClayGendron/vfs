# 109 — Pins for unpinned laws: the mutations the suite must start killing

- **Status: drafted 2026-08-18.**
  Born from the review campaign memo
  (`../../../research/2026-08-18-glob-grep-review-campaign.md`),
  findings 4 (test lens, major), 12, and 13 (test lens, minor) —
  three laws the suite exercises but never asserts on, each
  demonstrated by a mutation that passes all 2,516 tests. Every fix
  recipe below was already executed by the review's verifiers and
  shown to kill its mutant; this spec lands them as committed pins.
- **Date:** 2026-08-18
- **Owner:** Clay Gendron
- **Kind:** tests only — new rows in the grep/pathterms batteries
  and (at most) a test seam. No live-code behavior changes; if
  writing a pin reveals a live defect, that is a finding to
  surface, not to quietly fix here.
- **Depends on:** spec 104 (the compiled-terms and allow-list
  machinery under pin), ADR 041 (the priced-ladder constants whose
  drift §3 makes visible), the testing standard
  (`../../../standards/testing.md` — distinguishing rows, not
  coverage rows).
- **Relates to:** spec 107 (adds its own overlay-gate pins — no
  overlap: this spec owns nomination/pricing laws), spec 108 (whose
  restructure of `_channel_facts` must keep §1's pin green — land
  109 first so 108 refactors under pin).

## Intent

Three laws currently hold by authorship, not by test:

1. **The mixed-channel soundness law** (`_channel_facts`: an arm
   with no facts voids the whole pushdown — `if not facts: return
   None`). Mutating it to `continue` (emit the partial OR) silently
   drops in-scope rows with `success=True` and the whole suite
   green, while 14 existing suite calls compile the mixed shape —
   exercised, never asserted. Its regression mode is the forbidden
   silent false negative.
2. **The allow-list multi-term intersection** (`_arm_ids`' rarest-
   first self-join chain). Joining only the rarest term passes the
   suite: the corpus has no term-overlap decoy, the superset
   battery asserts one direction only, and no test arm exceeds four
   segment terms so `_INTERSECT_TERMS` never slices. The mutation
   reverts to an alternative ADR 041 measured and rejected; if it
   regressed, a wider allow-list can push scoped rows past
   `CANDIDATE_BUDGET` and drop in-scope results.
3. **The priced ladder-defer decision** (`_ladder_defers`). Both
   branches are lawful supersets with identical results, so nothing
   behavioral distinguishes them: order-of-magnitude errors in any
   pricing constant (75→7.5, 500→5000, 0.055→0.55) pass the suite
   and the 100% coverage gate — the likely mistake when the
   constants are re-derived, and a silent whole-scope-verify
   regression on every scoped call.

The law that binds the slices: **every pin lands with its mutant.**
A pin is proven by applying the mutation it exists to kill and
watching it fail — recorded in the test's docstring as the mutation
it guards (no spec/finding numbers, per the comments rule). Mutation
runs follow the safe-restore rule: copy the file to the scratchpad
first, restore from the copy, verify with ruff after.

## Shape

- **§1 The mixed-channel pin.** A grep through a channel mixing a
  fact-carrying arm and a fact-free arm asserts the row only the
  fact-free arm admits is served — `{/src/a.py, /docs/readme.md}`
  with `globs=("*.py", "docs/**")` must return both — in both
  worlds (pre- and post-reindex), at the storage seam and through
  the contract battery with the memory backend as oracle. Alongside
  it, `_channel_facts` gets direct unit rows (it currently has
  none), including the dialect-conditioned LIKE-escape branch.
- **§2 The intersection pins.** The pathterms corpus gains a
  term-overlap decoy (`/app/solo.txt` beside `/src/app/**` rows)
  and the superset battery asserts the decoy is *absent* from a
  `src/app/**` allow-list — the row that dies when the join chain
  is shortened. A 5+-literal-directory glob makes `_INTERSECT_TERMS`
  actually slice. The rarest-first *ordering* gets its own pin
  (statement-shape or seeded-counts assertion), closing the lead
  the review flagged beside the finding.
- **§3 The pricing pin.** The defer decision is pinned directly,
  since results cannot see it: a constructed crossover shape (posting
  bytes just above, then just below, the defer bill) asserts which
  branch runs — via a spy on the blob fetch or a seam equivalent —
  so any constant drifting an order of magnitude flips a test, not
  just a benchmark. The `laddered ∩ allow` branch gets a reachable
  row (today it is reached only via the never-indexed early return —
  no test intersects real laddered postings with an allow-list).
- **§4 The proof.** Each of the review's three mutations is applied
  once against the finished suite and shown to fail at least one
  new pin; the safe-restore discipline governs; results recorded in
  the status line (mutation → killing test).

## Slices

- **A. Soundness and intersection.** §1 and §2 with their mutant
  proofs.
- **B. Pricing.** §3 with its constant-drift proofs (three
  constants × one magnitude each way where meaningful).
- **C. The record.** §4's ledger into the status line; spec status
  updated for the mining pass.

## Open questions

- **Should mutation proofs become a standing harness?** Running
  curated mutants in CI would keep these laws pinned against future
  rewrites, at real suite-time cost. Out of scope here (pins land
  hand-proven); recorded for the testing-standard conversation.
