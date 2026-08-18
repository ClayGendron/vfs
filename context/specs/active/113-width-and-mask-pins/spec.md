# 113 — Width and mask pins: killing tests for the arc's unpinned laws

- **Drafted 2026-08-18.**
  Born from the remediation-landing review
  (`../../../research/2026-08-18-remediation-landing-review.md`),
  findings 3 (delete's batched flush — the arc's one major coverage
  gap), 8 (the rescued-scan epoch recheck), 9 (the glob and grep
  mask promises), and lead L2 (move/restore mirror width). Spec
  109's sequel: tests only, each pin landed against its proven
  mutant, no production code changes.
- **Date:** 2026-08-18
- **Owner:** Clay Gendron
- **Kind:** test-only. Every law here already holds by authorship;
  the review proved each one unpinned by running a mutant that
  breaks the law through the entire suite green. Each slice lands
  the test that kills its mutant, and shows the kill.
- **Depends on:** spec 111 (the delete batching and mask discipline
  under pin), spec 107 (the rescued-scan path under pin), spec 104 /
  ADR 040 (`move_postings` and the mirror battery this widens).
- **Relates to:** spec 109 (the discipline this follows: mutant
  applied, shown surviving, test landed, mutant shown killed, under
  the safe-restore rules), spec 112 (owns the matcher-level pins;
  this spec owns the storage-seam ones), spec 114 (its harness
  change touches the same conformance fixtures — land in either
  order, the seams are disjoint).

## Intent

1. **Batch width is invisible to every referee.** Two independent
   mutants proved the same blind spot on two verbs:
   - *Delete:* flushing only the last accumulated posting delta
     survives 2,558 sqlite tests and the 187-test live Postgres leg
     — including the cascade battery — while silently corrupting the
     postings mirror on any multi-target delete (stale postings feed
     `allow_list_ids` → missed grep/glob hits on the flagship
     10k-target contract). Every mirror-refereed delete row is
     single-target; the multi-target rows assert Result shape only.
   - *Move/restore:* running `move_postings` on only the last pair
     of a batch survives the full suite, including a 20-pair move
     test (asserts observations only) and the mirror battery (drives
     move/restore exclusively single-pair). The per-pair code is
     correct and intentional; its width is simply unwitnessed.
2. **The mask discipline is unpinned on both verbs.** Widening
   mutants — glob's `_observe` fed the queried mask, grep's hoisted
   projection/row-mask block widened by the ride — survive
   everything, because every `columns=`-passing test asserts subset
   (`<=`, satisfied by a wider mask) and no glob test passes
   `columns=` at all. Phantom `name`/`ext`/`size_bytes` tokens reach
   `populated` on the wire.
3. **The rescued-scan path's post-scan epoch recheck is unpinned.**
   `skip_verified = True` survives the suite and the Postgres race
   leg (whose rival is a write — it never moves the epoch pointer);
   on per-statement-snapshot engines a rival `reindex()` in the
   window makes the mutant silently drop a row where baseline
   redrives.

Laws that bind the slices:

1. **Every pin lands with its mutant shown killed** — mutant
   applied under the safe-restore discipline (scratchpad backup,
   cp-based restore, restoration verified), suite run, the new
   test's failure recorded in the spec status ledger, exactly as
   spec 109 did.
2. **Pins live where the law lives.** Width pins go in the mirror
   battery and the conformance helper (so all four engine legs
   referee them); mask pins beside the existing mask rows of their
   verb; the cadence spy beside the rescued-path test it extends.
3. **Exact equality, not subset.** A mask pin that asserts `<=` is
   the blind spot, not the fix.

## Shape

- **§1 Width rows.** A delete of two files under distinct roots in a
  single call, followed by the mirror audit, in
  `tests/storage/database/test_segments.py`; the same shape in the
  conformance helper (`tests/support/storage_contract.py`) so every
  engine leg referees it. A multi-pair move row and a multi-
  observation restore row beside it. The seeded verb sequence widens
  to sometimes issue 2-pair move batches and multi-observation
  restores — pinning the width dimension across all verbs for free.
- **§2 Mask rows.** Grep: `grep(pattern=..., columns=
  frozenset({"content"}))` asserting `populated ==
  {"path", "kind", "version", "content", "matches"}` — exact — which
  pins both fetchers through the one hoisted strip site; a scan-tier
  twin (`allow_scan=True`) for the second path. Glob:
  `glob(patterns=..., columns=frozenset({"path"}))` asserting
  `populated == {"path", "kind", "version"}`. Both verified against
  their widening mutants.
- **§3 The cadence spy.** The rescued-path test
  (`test_a_false_empty_verdict_is_rescued_at_the_recheck`) gains a
  `current_epoch` counting spy asserting the post-scan pointer read
  happened exactly once — the `skip_verified = True` mutant reads
  zero times and dies. While there, confirm the statement-cadence
  spies pin the rescued arm's three pointer reads, not just the two
  common arms (review design note; cheap to assert in the same
  test).

## Slices

- **A. Width.** §1 with both mutants' kill ledger.
- **B. Masks and cadence.** §2 and §3 with their kill ledger; spec
  status updated with the full mutant→test table.

## Open questions

- **A standing mutation harness** (spec 109's open question, now
  with four more hand-run mutants as evidence) — the pattern of
  "law held by authorship, proven unpinned by a hand mutant" has
  recurred in every review; whether to automate it is a decision for
  its own pass, not this spec.
