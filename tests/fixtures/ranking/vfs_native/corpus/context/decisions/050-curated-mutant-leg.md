# 050. The Mutant Ledger Replays Inside Review — No Standing Harness

- **Status:** accepted 2026-08-25 — closes the standing-mutation-
  harness question specs 109 and 113 raised (archived from
  `../open-questions.md` against this ADR). Extends
  `../standards/testing.md`'s pins-land-with-their-mutant discipline
  with a replay stage owned by the review workflow. *Revised same
  day, pre-commit:* the first draft of this ADR adopted a standing
  scripted CI leg (with a drafted spec 119); Clay revised the
  mechanism in session — "have the code_review skill run checks
  instead of maintaining an additional system" — and added the
  isolation requirement below. This file records the decision as
  made; no separate supersession, since the draft never entered
  history.
- **Date:** 2026-08-25
- **Deciders:** Clay Gendron, on the research memo's evidence; the
  review-integrated mechanism and the isolated-tree requirement both
  Clay's, in session.
- **Context source:**
  `../research/2026-08-25-standing-mutation-harness.md` (executed
  ledger replays and the field study).

## Context

Review campaigns hand-prove mutants — one-line mutations that
survive the whole suite — and land pins that kill them; nothing
re-ran the ledger afterward. The replays showed why that is not
enough: one week after specs 109/113, all 13 recorded sites survive
and both replayed mutants still die, but one (M5) no longer dies to
its *recorded* killing test — the pins hold, the mapping rots, and
only a replay notices. The field offers no tool that replays a fixed
named-mutant ledger; SQLite's TH3 is the standing-harness precedent,
Google's diff-based review-time practice is the no-harness precedent,
and the long-standing-mutants literature endorses curated
evolution-robust suites. Measured cost: ~5 s per mutant at file
scope, ~2 minutes for the whole ledger.

## Decision

1. **The ledger is the durable artifact; the review workflow is the
   runner.** `standards/mutant-ledger.md` holds every proven-and-
   pinned mutation: intent plus best-known anchor, target, a scoped
   test selection, recorded killers as **advisory diagnosis only**
   (M5's drift is the founding example), and provenance. Campaigns
   append rows when they land pins. There is no standing script, CI
   leg, or nightly job to maintain.
2. **`test_review` executes, not just reasons.** Its
   think-in-mutations step now runs its strongest candidates — a
   surviving executed mutant is a finding with a repro — and a new
   step replays the ledger rows intersecting the review scope (the
   whole ledger when time allows). Statuses stay loud: killed
   (coverage), survived (a pin regressed — high-severity finding),
   stale (concept gone — propose retiring the row); never a silent
   skip. The assertion is always ≥1 failure in the row's scope,
   never a named test.
3. **Mutations never touch the live repo.** Review agents run
   concurrently against the working tree, so even a
   perfectly-restored in-place mutation poisons neighbors' reads and
   test runs during the window. All mutation work happens in an
   isolated `git worktree` under the session scratchpad, primed with
   `uv sync`, restored per-row from its own committed state, removed
   when done. The repo-read-only rule for review agents stands
   unqualified.
4. **An agent replays intent, not patches.** Rows are intent-first
   because the runner is an agent, not a script: a moved textual
   anchor is re-derived from the mutation's meaning rather than
   erroring — the staleness that would break a patch-replay harness
   becomes judgment, and only a genuinely vanished concept retires a
   row.

## Options considered

- **Review-integrated replay** (adopted): no second system; the
  checks run where the scrutiny and the appending already happen;
  agent execution absorbs anchor drift.
- **A standing scripted CI leg** (the first draft; SQLite's shape):
  catches regressions between campaigns rather than at the next one —
  at the cost of a bespoke runner, ledger format parsing, drift
  statuses as code, and nightly wiring. Rejected as a second system
  to maintain; the between-campaign window is acceptable at this
  repo's campaign cadence, and the option remains open if that
  cadence ever slows.
- **Diff-scoped general tools** (mutmut 3, cargo-mutants
  `--in-diff`): hunt *new* survivors — which the campaigns do with
  better judgment today; revisit only if campaign cadence slows.
- **Per-campaign discipline with no replay** (Google's model):
  accepts that pin regressions and mapping drift go unnoticed —
  refuted by the replays catching a drift within one week.

## Consequences

- The pins from every campaign land twice: as tests, and as ledger
  rows the next campaign's `test_review` re-arms.
- Pin regressions surface at the next review campaign touching the
  area, not nightly — the accepted window, priced by the repo's
  campaign cadence.
- `test_review` grows real execution (worktree, `uv sync`, scoped
  pytest runs) and its reviews take the ledger's ~2 minutes when run
  in full.
- The ledger's founding rows are specs 109/113's thirteen plus the
  designed-inert comparator-tie candidate (expected to survive;
  never a regression).
- Spec 119 (the scripted leg) is withdrawn unlanded; nothing
  implements a runner.
