# 115 — Bind accounting and docstring trues: the record matches the code

- **Status: all slices landed 2026-08-18.** §1: `base_binds` is
  `len(CONTENT_KINDS)` — the `+ 1` for the encoded flag dropped,
  the comment now naming what is charged (kind membership at element
  width; the flag renders inline and binds nothing) — and the charge
  is pinned directly:
  `test_the_base_facts_charge_equals_their_executed_width` compiles
  the base facts with `render_postcompile` on all five bundled
  dialects and asserts executed == charged. The alternative (derive
  the base charge through `_static_binds`) was declined: the base
  facts include an expanding membership, which `_static_binds`
  deliberately refuses — routing them through it would bend its
  contract, a worse trade than one directly-pinned constant. §2:
  both docstring sites reworded from spec 107's accurate language —
  the module paragraph now says a non-empty preamble verdict settles
  the decision (the scan tier will run after the index tier, no
  second combined read), and `_pointer_with_overlay` says "issued
  twice on the skip path, once when the preamble verdict is
  non-empty". §3: `test_static_bind_counts_are_dialect_invariant`
  compiles `liveness_filters` output for every profile (the five
  named plus GENERIC) on all five bundled dialect compilers and
  asserts each count equals `_static_binds`' default-compiler
  answer; the `_static_binds` docstring states the invariant
  (dialect-count-invariant inputs required). §4: ladder referee on
  the linux store — all seven rows' line/file counts byte-identical
  before/after (e.g. 3,938/1,437 · 19,210/2,549 · 20,800/3,599 ·
  zero-hit 0), wall times in noise (zero-hit 45.0 → 42.6 ms); full
  3.13 CI leg green; MSSQL leg green at 211 (the saturated 40-ext
  boundary and bind-budget rows on the tightest engine, one db_test
  cycle, machine restored).
- **Drafted 2026-08-18.**
  Born from the remediation-landing review
  (`../../../research/2026-08-18-remediation-landing-review.md`),
  findings 4 (the overcharging hand count and its wrong comment),
  5 (the grep docstring's false routing and cadence claims), and
  lead Q1 (the `_static_binds` default-dialect invariant, elevated
  to a design question). Small, surgical, all in
  `storage/backends/database/grep.py` and its tests.
- **Date:** 2026-08-18
- **Owner:** Clay Gendron
- **Kind:** hygiene — one one-line arithmetic true-up in the safe
  direction, docstring corrections, and one invariant pin. No
  behavior change is expected on any engine; the bench ladders and
  engine legs are the no-regression referee.
- **Depends on:** spec 108 (the bind accounting this trues), spec
  107 (the two-read protocol the docstrings describe).
- **Relates to:** spec 108's mining pass (its §1 "one bind-counting
  mechanism, not two" narrative vs the four counting sites that
  landed — the reconciliation belongs to the mining record, not to
  code), spec 112 (owns the matcher-side docstring trues; this spec
  owns the storage-side ones).

## Intent

1. **One hand count disagrees with the executed count — safely.**
   `base_binds = len(CONTENT_KINDS) + 1` charges 4 where every
   dialect executes 3: the `encoded` flag renders as an inline
   literal on all six compilers checked and all four live engines,
   so the `+ 1` buys nothing and the inline comment beside it ("and
   the encoded flag") asserts a bind that does not exist. An
   overcount can never overdraw (the review verified MSSQL lands 33
   parameters under cap at the maximum chunk), so this is waste and
   a wrong comment, not a defect — but the 07002 class was born from
   exactly this kind of charged-vs-executed drift, and the review's
   charged-equals-executed pin now watches it.
2. **The module docstring misstates the two-read protocol.** Probed:
   on a non-empty preamble verdict the full index tier still runs
   before the scan tier ("routes straight to the scan tier" routes
   nothing), and the combined pointer+overlay read is issued exactly
   once on that path ("issued twice per gated call" is false on the
   common path). Spec 107 words both correctly; the docstrings
   compressed them wrongly. Maintainer-model drift with a correct
   implementation underneath.
3. **`_static_binds` counts on the default compiler; statements
   execute on the live one.** Verified count-identical for every
   reachable input (the two liveness terms) across all six profiles
   × five bundled dialects, and across six plausible future
   predicate shapes — but the invariant is nowhere stated, and if a
   future dialect-sensitive predicate ever diverged, the error
   direction is undercount → `per_chunk` inflation → the ORA-01795
   class. The chunk arithmetic silently relies on an invariant
   nothing pins.

Laws that bind the work:

1. **Charged equals executed, on every dialect.** The accounting
   true-up must keep the existing charged-equals-executed pin green
   and extend it to the corrected base charge.
2. **Docstrings describe the code that runs.** Corrections use spec
   107's accurate wording as the source: the preamble verdict
   *settles* the scan decision — "non-empty settles it: the scan
   tier will run and no second combined read is issued"; the
   combined read is "issued twice on the skip path, once when the
   preamble verdict is non-empty".
3. **Behavior identical everywhere.** The base-charge change alters
   chunk arithmetic by one bind per chunk in the caller-favorable
   direction; the grep ladders (identical counts) and the saturated
   MSSQL boundary row are the referee that nothing regressed.

## Shape

- **§1 The base charge.** `base_binds` drops the `+ 1`
  (`len(CONTENT_KINDS)`), the comment beside it names what is
  actually charged, and the charged-equals-executed pin is confirmed
  to cover the corrected value. Alternative considered: deriving the
  base charge through `_static_binds` so it is measured rather than
  hand-mirrored — adopt it only if it does not add a fifth counting
  spelling; the point is fewer conventions, not more.
- **§2 The docstring trues.** Both storage-grep sites reworded per
  law 2. No matcher-side edits here (spec 112 owns those).
- **§3 The invariant pin.** A regression test compiling
  `liveness_filters` output with `render_postcompile` on every
  bundled dialect object (constructed locally, no servers) and
  asserting each count equals `_static_binds`' default-compiler
  result — pinning the invariant the chunk arithmetic relies on —
  plus one `_static_binds` docstring line stating it counts on the
  default compiler and requires dialect-count-invariant inputs.
  The alternative (threading the session's live dialect through
  `grep_rows` → `_pushdown_terms` → `_static_binds`) is recorded
  for the day grep gains a dialect-sensitive static predicate; today
  it would thread a parameter to defend against no reachable input.
- **§4 The gate.** Full suite and coverage; both grep ladders
  identical counts; the saturated 40-ext MSSQL boundary row green on
  the live engine (the one engine leg this spec's arithmetic could
  conceivably touch).

## Slices

- **A.** §1–§3 in one landing with §4's sqlite-side gates.
- **B.** §4's MSSQL leg (one db_test cycle), spec status updated.

## Open questions

- **The remaining bind-count conventions** (review design note): the
  four counting sites (`base_binds`, `_channel_facts`' as-built
  increments, `_CHANNEL_ARM_BINDS`, `_static_binds`) each own a
  different kind of term, which is defensible — but if a fifth ever
  appears, consolidation stops being optional. No action here.
- Review design questions 1 (fan budget derived at two sites, with
  its unit wrinkle) and 3 (the row-gate ride literal) touch this
  file and remain open for the decision pass; neither lands here
  uninvited.
