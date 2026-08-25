# 124 — Pins for the round's surviving mutants: the EOF discard and the grep mask

- **Status: draft, 2026-08-25.**
- **Born from** the chunking-arc landing review
  (`../../../research/2026-08-25-chunking-arc-landing-review.md`),
  findings F7 (EOF discard guard unpinned — downgraded major → minor
  because the shipped code is correct) and F8 (grep mask law
  unpinned; ledger row M3's anchor ambiguous), plus their attached
  ledger leads.
- **Date:** 2026-08-25
- **Owner:** Clay Gendron
- **Kind:** tests and ledger only — no `src/` change. Both mutants
  were *executed and survived the full suite* during the review;
  each pin lands with its proven mutant per
  `../../../standards/testing.md` and the mutant-ledger discipline
  (ADR 050).
- **Depends on:** spec 112 (whose zero-width discard guard F7
  half-pins), spec 113 / ledger row M3 (whose mask pins F8
  completes), `../../../standards/mutant-ledger.md`.
- **Relates to:** spec 125 (which touches the same whole-text loops
  for the skeleton unification — land this spec's pins first so the
  unification is refereed by them).

## Intent

1. **The over-discard direction of the slice-end guard has no
   killer.** Deleting `and stop < len(text)` from both whole-text
   loops survives the entire suite (2,646 native, 2,633 pure) while
   observably breaking matching: pure-engine `grep("$")` on `"abc"`
   returns 0 counts instead of 1, budgeted *and* unbudgeted, and
   end-to-end `fs.grep("$")` silently drops every file without a
   trailing newline. The qualifier is declared law and testing.md's
   "pins land with their mutant" names exactly this shape — yet the
   proven mutant from the original landing was the *opposite*
   (over-serving) direction. Exposure: pure fallback engine only;
   pattern class `$`, `\b$`, and scan-admitted shapes like
   `[ \t]*$`.
2. **The mutant ledger has no row for the slice-end guard in either
   direction** — the replay protocol would never re-prove the
   original fix or this one.
3. **Values outside the populated mask are unpinned for grep.**
   Widening only the hoisted projection (not the mask) survives all
   2,646 tests while setting `size_bytes` on grep rows whose mask
   excludes it — a valued field reaching the caller and the wire
   (`model_dump(exclude_none=True)`). The conformance law that
   forbids exactly this loops over stat/read/ls/glob but not grep,
   and passes no `columns=`.
4. **Ledger row M3's wording admits two readings** ("projection/
   row-mask widened") — the mask reading dies, the projection
   reading survives silently: the same intent-ambiguity failure mode
   row M5 already recorded, in a live row.

Laws that bind the slices:

1. **A pin lands with its mutant** — each new test is proven against
   the executed surviving mutation under the safe-restore
   discipline, and the kill is recorded.
2. **Intent-first ledger rows** (ADR 050): rows name the law and the
   mutation; recorded killers are advisory, the assertion is ≥1
   scoped failure.

## Shape

- **§1 The EOF rows.** An unterminated-body row joins BODIES and a
  zero-width-EOF CASE joins `test_matcher_parity.py`, so both
  existing sweeps (budgeted-equals-unbudgeted, pure-equals-
  authority) cover the corner for free — plus one targeted row:
  `$` on a body with no trailing newline serves the final line,
  pure engine, both spellings. Proven against the executed
  over-discard mutant (guard qualifier deleted from both loops).
- **§2 The ledger row.** One intent-first row for the slice-end
  discard guard covering *both* directions (over-serve: phantom
  matches; over-discard: lost EOF matches), each direction's
  mutation named, killers advisory.
- **§3 The mask rows.** The conformance mask law
  (`test_the_mask_never_omits_a_populated_field` and its
  never-exceeds twin) gains grep with a narrow `columns=` — refereed
  on the memory leg and all four engine legs — and/or the exact-mask
  grep row asserts `size_bytes is None` directly. Proven against the
  executed projection-widening mutant (the `fetched` hoist widened
  at its definition).
- **§4 The M3 true-up.** Ledger row M3's anchor tightened to name
  the `fetched` hoist and both mutation directions explicitly, per
  the intent-first convention.

## Slices

One slice — four sections, all tests and ledger, one landing.
