# A standing mutation harness — ledger replays, field practice, costs

- **Date:** 2026-08-25
- **Provenance:** commissioned by Clay ("let's research this") against
  the open question specs 109 and 113 raised: should the hand-proven
  mutants from review campaigns run as a standing harness so the pins
  stay armed against future rewrites? Two investigations, run
  2026-08-25: executed replays of the recorded ledger against today's
  tree (under the safe-restore discipline — backup copy, mutate, run,
  restore from backup, verify with ruff and a green re-run), and a
  field study of mutation-testing practice (mutmut 3 / cosmic-ray /
  mutatest, cargo-mutants, Google's diff-based practice, pitest,
  StrykerJS, SQLite's TH3 branch-mutation harness, and the
  long-standing-mutants literature).
- **Headline:** the ledger is **already proving its worth and already
  drifting**. One week and four refactor landings after specs 109/113,
  all 13 recorded mutation sites still exist and both replayed
  mutants still die — but one of the two no longer dies to its
  *recorded* killing test (M5's epoch-spy killer now passes; three
  other tests catch it). So the pins hold, the mapping rots, and only
  a harness would have noticed. Field practice splits cleanly: no
  existing tool replays a fixed named-mutant ledger (it would be a
  small bespoke leg), but SQLite runs exactly this shape as
  infrastructure policy, the long-standing-mutants research endorses
  curated evolution-robust mutant suites over per-version
  recomputation, and the measured cost is trivial — ~5 s per mutant
  at file scope, ~70 s serial for the whole ledger, against a 52 s
  suite. General mutation tools are a *complement* (they find new
  survivors; the ledger keeps proven ones dead), best run diff-scoped
  and report-only per the universal field cadence.

## 1. The ledger as it stands

Specs 109 and 113 recorded 13 hand-proven mutants (each shown
surviving the whole pre-existing suite, then killed by landed pins):
109's `_channel_facts` partial-OR, the `_arm_ids` rarest-term
shortening, and six pricing-constant magnitude drifts; 113's M1–M5
(batch-width flushes, projection masks, the `skip_verified` flip).
`open-questions.md` holds one candidate row a harness would carry
that no pin can: the ladder-defer comparator tie at the exact
crossover (`allow_size=80`, observationally inert).
`standards/testing.md` states the pins-land-with-their-mutant
discipline; nothing re-runs the ledger after landing.

## 2. Replays (executed)

- **Site survival: 13/13.** Every recorded mutation site still
  exists verbatim in today's tree (`ranked[:_INTERSECT_TERMS]` at
  `pathterms.py:275`, the pricing constants at `grep.py:128–130`,
  `_channel_facts`, the `segment_moves` batch flush, `skip_verified`)
  — despite the week's landings including two refactors that
  touched `grep.py` directly. One week of heavy refactoring produced
  zero patch-level drift.
- **M5 (`skip_verified = False → True`): still killed — by the wrong
  tests.** 3 failures in `tests/storage/database/test_grep.py`
  (two `TestEpochLadder` rows and the scan-path statement-count
  pin); the *recorded* killer ("the epoch spy" in the
  rescued-verdict test) now **passes** under the mutant. The law is
  pinned; the mutant→killer mapping drifted in one week.
- **Pricing drift (`_CANDIDATE_COST_US` 75.0 → 7.5): still killed,
  mapping intact** — 4 failures, matching the ledger's recorded "4
  pins fail".
- **Costs (Apple Silicon laptop):** one named test ~0.8 s; the
  containing test file (89 tests) ~4.7 s; the full suite ~52 s. A
  14-row ledger replayed at file scope is ~70 s serial (and
  embarrassingly parallel); full-suite-per-mutant is ~12 min.
- A general-tool probe (mutmut 3 on one module) was not completed:
  its configuration now lives in `pyproject.toml` and the experiment
  wasn't worth mutating the project file mid-session; its cost model
  is taken from the field study instead.

The mapping-drift observation is the design-shaping finding: a
harness must assert **"this mutant dies under a scoped test
selection"**, treating the recorded killer as advisory diagnosis,
not contract — otherwise the harness fails red on a healthy suite.

## 3. What the field does

- **No tool replays a fixed named-mutant list.** pitest's
  `fullMutationMatrix` and StrykerJS's incremental JSON record
  killer-per-mutant data, but as caches/reports, not assertable
  contracts. A curated leg is a small bespoke harness by necessity.
- **SQLite is the engineering precedent** for exactly this shape:
  TH3's `mutation-test.tcl` flips branch instructions and requires
  the suite to notice, with in-source suppression annotations
  (`/*OPTIMIZATION-IF-TRUE*/`) as an equivalent-mutant ledger. Their
  argument: not cost-effective for a typical application, justified
  for widely deployed infrastructure that must survive refactors —
  the same posture vfs's production stance takes.
- **Google runs the opposite model** (diff-based, report-only,
  curated at review time, never re-run, never gated) — which is
  vfs's existing per-campaign discipline, and at 2B LOC the only
  possibility. The long-standing-mutants research (arXiv 2212.11762)
  quantifies what that model loses: ~52 % of mutants degrade in
  relevance as code evolves, and curated evolution-robust suites
  gave ~10× better mutant relevance than per-version recomputation.
- **Live general tools:** Python — mutmut 3 (rebuilt on mutant
  schemata + a trampoline dispatch; stats pass runs only covering
  tests per mutant; incremental by function-source hash;
  `mutate_only_covered_lines`) and cosmic-ray (whole-suite per
  mutant, git-diff filters, Celery distribution); mutatest is
  dormant. Rust — cargo-mutants (incremental build + test per
  mutant, `--in-diff` for PRs, `--shard` for CI, GitHub annotations).
- **Universal cadence:** diff-scoped on PRs, full runs
  nightly/weekly, report-only rather than score-gated. The one case
  where hard gating is sound is a curated leg — every mutant is
  hand-proven non-equivalent with a known killer, so every red is
  actionable by construction.
- **Known failure modes to design for:** flakiness amplifies N-fold
  (re-run or quarantine flaky killers); equivalent mutants are
  handled by suppression ledgers, not detection; and **drift is a
  feature when explicit** — a patch that no longer applies should
  surface as a distinct "re-prove or retire" status (Stryker's
  culprit-test invalidation, SQLite's annotations), never a silent
  skip or an undifferentiated red.

## 4. Shape of a curated leg, if adopted (the lean)

The evidence leans **option (a) — a curated-mutant leg — plus
diff-scoped general runs as a later, separate complement**:

- One ledger file per mutant (or one table): target file, the exact
  textual mutation, a scoped test selection (file or directory), and
  the advisory recorded killers. Applied under the safe-restore
  discipline the standards already state; assert ≥1 failure in the
  scope; restore; verify.
- Three statuses, all loud: **killed** (green), **survived** (a pin
  regressed — the one red worth gating on), **stale** (the mutation
  no longer applies textually — re-prove or retire, the M5-style
  mapping drift caught early).
- Run it outside the coverage gate: nightly or on-demand
  (`scripts/` leg beside `ci.sh`), ~70 s serial today, gate-worthy
  because every red is actionable.
- Carry the rows pins can't: the comparator-tie candidate enters
  the ledger as its first observationally-inert row.
- The Rust crate's mutants (if any accumulate) run under
  cargo-mutants' cost model — incremental build per mutant — so
  keep them few or nightly-only.
- General-tool runs (mutmut 3 diff-scoped on PRs, cargo-mutants
  `--in-diff`) are a separate, later decision: they hunt *new*
  unpinned laws, which today the review campaigns do with better
  judgment; adopt only if campaign cadence slows.
