# 129 — prose trues and ledger hygiene: the close window said out loud

- **Status: draft, 2026-08-25.**
- **Born from** the remediation-round landing review
  (`../../../research/2026-08-25-remediation-round-landing-review.md`),
  findings F5 (the three-laws count), F6 (the lost `_audit`), F7
  (the close-window bound is verb-sized, not batch-sized) and F8
  (ledger row P13 overclaims), plus design question Q4 (the
  residency law's char-proxy scoping). F7's posture ruled in the
  2026-08-25 decision pass **conditional on prior-art
  verification**, delivered as
  `2026-08-25-close-lifecycle-and-shutdown-race-prior-art.md`:
  prose + pin — the code's serve-to-completion shape matches the
  universal drain idiom and stays; the zombie-pool alternative is
  recorded as an open question, not ruled.
- **Date:** 2026-08-25
- **Owner:** Clay Gendron
- **Kind:** record corrections (docstrings, one ADR amendment, one
  archived-spec amendment note, one ledger row), one restored test
  assert, and one new race pin. No live-path behavior changes.
- **Depends on:** specs 120/122 (whose close-window prose this
  trues), spec 125 (whose P13 row and truncation guards F8
  adjudicates), ADR 048/049 (amendment sites).
- **Relates to:** spec 126 (the close teardown fix — this spec's
  race pin exercises the same window from the racing verb's side).

## Intent

The round's records drifted from its code in five places; each true
here is severity-minor and evidence-backed.

1. **F7 — the close-window bound is verb-sized.** `offload.py`,
   spec 122's record, and its commit bound the close window at "one
   on-loop batch." In fact a verb that captured the pool before
   close serves *all* its remaining hops inline — and spec 120's
   whole-verb chunk hop makes the exposure verb-sized. Executed: a
   reindex racing close at 20,000 files ran `_assess_and_split`
   1.56 s on the event loop (1,714 ms worst gap vs ~242 ms
   offloaded) while correctly reporting success. The code is right
   (classified Results, zero raw escapes; prior art: in-flight work
   finishing on what it captured is the universal drain idiom, and
   any bound is the closer's to impose); the prose is wrong, and
   the reindex-racing-close path has no pin.
2. **F5** — `offload.py`'s module docstring counts "Three laws"
   over four bullets.
3. **Q4** — `offload.py`'s abandonment bullet states the residency
   bound in grep's byte-exact terms, while the reindex batchers it
   now also covers meter chars by a declared ASCII-dominant proxy
   (measured 3.00×/4.00× folded-byte overshoot on CJK/emoji
   corpora).
4. **F6** — spec 121's appended MySQL race test absorbed the
   trailing `await _audit(storage)` from
   `test_a_second_reindex_refuses_while_one_runs` (AST-verified:
   base 1/0 → tip 0/2). The restored audit passes on live MySQL —
   nothing was masked; the pin was silently weakened.
5. **F8** — ledger row P13 claims "either dedupe guard deleted …
   killed," but the index-side guard is constant-true
   (`truncations` provably empty at that cut; probe-assert never
   fired across 2,661 tests plus a live-Postgres leg) and deleting
   it alone survives P13's full scope — a literal replayer would
   file a false survived-regression. The guard itself stays: spec
   125's defensive-symmetry ruling stands (re-ruled in this round's
   decision pass — reversing a same-round ruling without new
   evidence is churn).

## Shape

- **§1 The close-window trues (F7).** Restate the bound per racing
  verb at every site that claims it: `offload.py`'s two prose sites
  ("an in-flight call that finds its pool shut serves all its
  remaining work inline; only the next verb re-mints");
  `chunk_dirty`'s and `build_epoch`'s "the loop keeps serving"
  docstrings gain the close-window carve-out; ADR 048's occupancy
  amendment gains the same carve-out; archived spec 122 takes an
  amendment note (the ADR-amendment pattern — the record is
  corrected in place, dated, never rewritten silently).
- **§2 The race pin (F7).** A reindex-racing-close row: close lands
  mid-reindex with the pool captured; the verb completes with a
  classified success and zero raw escapes. This pins the correct
  behavior the review found untested; it makes no timing assertion
  (the inline cost is disclosed prose, not a bound to referee).
- **§3 The small trues (F5, Q4).** The law count; the abandonment
  bullet scoped to grep's byte-exact batcher with the char-proxy
  qualifier where reindex is covered (ADR 049's F5 amendment
  already carries the content-byte bound — mirror, don't fork).
- **§4 The audit restore (F6).** `await _audit(storage)` back at
  the end of `test_a_second_reindex_refuses_while_one_runs`; the
  doubled trailing audit in the new race test drops to one.
  Verified on the live MySQL leg.
- **§5 The P13 re-word (F8).** The row's mutation becomes the
  proven shape — both candidate-budget appends reverted to
  unguarded — with a C1-style designed-inert note for the
  index-side-alone direction ("expected to survive; never report as
  regression"). Replay the re-worded row as written to prove it
  kills (the review already proved the both-deleted direction: 1
  failure in scope).

## Slices

One slice — trues, restore, re-word, and the race pin together.

Gates: `scripts/ci.sh 3.13` at 100 % coverage; the MySQL leg for
§4's restored audit; other engine legs only if touched files
require them by the house cadence.
