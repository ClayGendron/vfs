# 129 — prose trues and ledger hygiene: the close window said out loud

- **Status: landed 2026-08-25.**
  One slice: the close-window bound restated verb-sized at every
  site that claimed it (``offload.py``'s law bullet and
  ``call_offloaded``, ``chunk_dirty``/``build_epoch``'s carve-outs,
  ADR 048's occupancy amendment, spec 122's amendment note); the law
  count trued to four; the abandonment bullet scoped with the
  char-proxy qualifier; ``_audit`` restored to
  ``test_a_second_reindex_refuses_while_one_runs`` and the doubled
  trailing audit dropped; P13 re-worded to the proven both-appends
  mutation with the index-side-alone direction marked designed-inert
  (all three directions replayed); the reindex-racing-close pin
  landed on a new inert ``reindex:before-chunk-split`` seam and
  joined P9's killers. Details in the landing note below.
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

## Landing note (2026-08-25)

- **§1/§3 the prose.** Every site now says the same thing: a call
  that captured its pool before close serves every remaining hop it
  holds inline — grep its remaining verify batches; reindex its
  chunk pass's whole split or its build's remaining feeds and drains
  — never a raw escape, and only the next capture (the next verb, or
  reindex's next phase) re-mints. That last clause is a precision
  the review's "verb-sized" shorthand lacked: reindex reads the
  executor property per phase, so a close mid-chunk-pass leaves the
  build phase re-minting a live pool. The law count is four; the
  abandonment bullet carries the measured 3.00×/4.00× char-proxy
  overshoot beside ADR 049's byte-exact bound (mirrored, not
  forked).
- **§2 the race pin.** `test_a_reindex_racing_close_is_served_whole`
  stages close on a new `reindex:before-chunk-split` seam (inert in
  production, the house pattern) after the chunk pass captured its
  pool, traces `_assess_and_split`'s thread to prove the split ran
  inline rather than on a re-minted worker, and checks the epoch
  still published (grep finds every row). It joins P9's killers —
  the fallback-re-raises mutation now fails twice. No timing
  assertion, per the spec.
- **§4 the audit.** Restored and the double dropped; the MySQL leg
  is this spec's gate for it (see gates).
- **§5 P13.** Re-worded and replayed in all three directions under
  safe-restore: both guards deleted — killed (1); scan-side alone —
  killed (1); index-side alone — survived, as designed and now
  declared. The guard stays.
- **Lead, not taken up:** both racing-close rows (grep's and the
  new reindex one) surface a
  `PytestUnhandledThreadExceptionWarning` from an aiosqlite worker
  thread reporting after the test loop closed — the close-mid-verb
  dispose leaves the verb's checked-out connection to be closed at
  GC, past the loop. Pre-existing at spec 122's row, sqlite-only,
  harmless to results; worth a look if the zombie-pool question is
  ever taken up, since a drain-then-dispose close would close it.
