# Quality rubric

- **Status:** draft (v0.1) — seeded 2026-07-16
- **Owner:** Clay Gendron
- **Purpose:** How we objectively score the quality of this repo — the
  dimensions, the maturity scale, and the split between checks a machine can
  run and reviews that need judgment.

## Why this repo can be scored objectively

Most repo-quality talk is vibes. This repo hands us two instruments that make
it measurable:

1. **The [constitution](constitution.md) is a latent rubric.** Every MUST
   is a checkable claim about the code. "Bounded output by default" either
   holds on every enumeration verb or it doesn't. Quality here partly *means*
   constitutional compliance.
2. **Context-fidelity is measurable.** [`context/README.md`](../README.md)
   declares that code is a build artifact of this context. That makes *drift*
   between `context/` (and the README) and the actual tree a first-class
   defect, and drift can be detected mechanically.

## The two layers

Every dimension is scored from two kinds of evidence:

- **Mechanical checks** — computable facts (lint counts, coverage, import
  graphs, doc claims vs. reality). These can gate CI: a regression on a
  mechanical check is a red build, not a discussion.
- **Judgment checks** — questions that need a reviewer (human or agent)
  reading code and citing evidence. These run on a cadence, never in CI.

The split is the Goodhart defense: the mechanical layer catches regressions;
the judgment layer catches gaming the mechanical layer.

## Maturity scale

Each dimension scores 0–4. Half points are allowed.

| Score | Anchor |
|---|---|
| 0 | Absent — nothing addresses the dimension |
| 1 | Ad hoc — addressed occasionally, no system |
| 2 | Present but leaky — a real system exists, with known holes |
| 3 | Systematic — the system covers the dimension; gaps are exceptions |
| 4 | Systematic + enforced + verified — gaps can't land silently |

A score without cited evidence is invalid. Every score in a review must name
the files, commands, or numbers it rests on.

## Dimensions and weights

Weights sum to 100 and are tuned to the current phase (mid-rebuild, backend
port in flight). Reweighting guidance follows the table.

**This file is the single source of truth for weights.** Grade files under
[`grades/`](grades/) record raw 0–4 scores only; weighted totals are
computed by joining a grade file against this block, so a reweight never
requires rewriting history. Machine-readable:

```json
{
  "rubric_version": "0.1",
  "scale": {"min": 0, "max": 4},
  "weights": [
    {"id": 1, "name": "correctness-and-verification", "weight": 20},
    {"id": 2, "name": "constitutional-compliance", "weight": 15},
    {"id": 3, "name": "architecture-integrity", "weight": 15},
    {"id": 4, "name": "code-health", "weight": 10},
    {"id": 5, "name": "context-fidelity", "weight": 15},
    {"id": 6, "name": "fitness-for-purpose", "weight": 15},
    {"id": 7, "name": "performance-and-scale", "weight": 5},
    {"id": 8, "name": "repo-hygiene-and-delivery", "weight": 5}
  ]
}
```

### 1. Correctness & verification — weight 20

Does the code do what it claims, provably?

- **Mechanical:** `uv run pytest` green; coverage ≥ 99 (`fail_under` in
  `pyproject.toml` is the floor, CI enforces it); the storage conformance
  suite (`tests/storage_conformance.py`) binds every shipped backend; result
  law tests (`tests/test_result_laws.py`) pass.
- **Judgment:** do tests assert *behavior* or implementation details? Are
  invariant-shaped modules (path grammar, result algebra) covered by
  property-based tests? Occasional mutation-testing spot checks: does killing
  a line actually fail a test?

### 2. Constitutional compliance — weight 15

Are the constitution's MUSTs true in the live tree?

- **Mechanical:** every enumeration/search verb accepts a limit and reports
  truncation (Article 2 §3); every public error belongs to the closed
  taxonomy (`results/kinds.py`); `capabilities()` answers without executing
  the op (Article 2 §2); every Entry and Candidate carries a revision
  (Article 1 §1.5).
- **Judgment:** Plan 9 / Unix deviations recorded in `decisions/`
  (Article 3); no silent cross-mount behavior (Article 1 §1.4); error-kind
  vocabulary has no dead entries (a defined-but-unused kind means a promised
  behavior is unimplemented).

### 3. Architecture integrity — weight 15

Layering, seams, and chokepoints.

- **Mechanical:** the `src/vfs` import graph is acyclic; nothing imports
  `base.py` except `__init__.py`; single-source vocabularies (`ops.py`) have
  no duplicated copies; drift tests (e.g. Entry↔Observation lockstep) pass;
  module size stays within budget (soft ceiling 1,200 lines; `base.py` is
  the one tracked exception).
- **Judgment:** is `base.py` still one coherent chokepoint or drifting toward
  a god module? Do new features land as composition (protocol families,
  mounts) rather than special cases?

### 4. Code health — weight 10

- **Mechanical:** `uv run ruff check` and `uv run ty check` at zero on
  `src/` + `tests/`; zero TODO/FIXME/HACK markers; every `noqa` /
  `type: ignore` carries a rationale.
- **Judgment:** duplication sweep (known watch item: POSIX-rule logic in
  `storage/backends/memory.py` vs. the database backend); dead-code sweep;
  docstring quality on new modules matches the existing bar.

### 5. Context fidelity — weight 15

Does `context/` + the README describe the tree that exists?

- **Mechanical:** README claims match computed facts (test count, coverage,
  Python versions); no stale project names (`grover`, `tests_old`) in live
  docs; no tracked generated artifacts (`coverage.json` and friends);
  `STATUS.md` review date is within its stated cadence.
- **Judgment:** per-spec `spec.md` status lines match the code (the
  `STATUS.md` true-up procedure); `open-questions.md` actually holds the
  open `[NEEDS CLARIFICATION]` items rather than sitting empty; superseded
  standards are updated, not left describing the previous generation.

### 6. Fitness for purpose — weight 15

Does the repo deliver the [mission](mission.md) — for agents?

- **Mechanical:** an agent-in-the-loop eval harness exists and its scores are
  tracked over time (task success rate, tokens spent, wrong-path retries on
  a fixed task set over a mounted namespace). Until it exists this dimension
  caps at 2.
- **Judgment:** the mission's testable promises hold ("mount and search in
  under an hour", "one MCP tool entry"); a runnable example app exists on the
  current core; the published package matches what the README sells, or the
  gap is labeled honestly.

### 7. Performance & scale — weight 5

Article 5 discipline, measured not asserted.

- **Mechanical:** a repeatable benchmark suite exists with tracked results
  (the spec 072 spikes are the seed; they must graduate from one-off
  research to a rerunnable harness before this scores above 2).
- **Judgment:** backends declare cost honestly (an O(tenants) op says so);
  regressions in benchmark trends get specs, not shrugs.

### 8. Repo hygiene & delivery — weight 5

- **Mechanical:** `git ls-files` shows no generated artifacts, scratch notes,
  or one-off documents at the root; lockfile committed; CI matrix covers all
  supported Python versions; publish and docs pipelines green.
- **Judgment:** versioning/deprecation story exists for the next release
  (constitution defers this to a pending `versioning.md`); archived trees
  (`src2/`, `tests2/`) are shrinking, not accreting.

### Reweighting

Weights track the roadmap, not a fixed ideal. As the backend port and MCP
surface land, shift weight from dimensions 1 and 3 (which are mature) toward
6 and 7 (which the mission stakes everything on) — on the order of
20/15/15 → 15/12/12 and 15/5 → 22/12. Reweighting is a rubric version bump,
recorded in this file's history.

## Scoring procedure

1. Run the mechanical checks and record raw outputs. (A consolidated check
   script is pending — see backlog below. Until then, run them by hand.)
2. Walk each dimension's judgment checks, citing evidence per score.
3. Compute the weighted total by joining the raw scores against this file's
   weights block: `Σ (score/4 × weight)`, reported as n/100.
4. Record the review as
   `context/standards/grades/YYYY-MM-DD-quality-review.md` with raw scores
   (JSON block + evidence), and note score deltas against the prior review.
   Baseline: [2026-07-16](grades/2026-07-16-quality-baseline-review.md).

**Cadence:** a scored review **weekly** (the `grades/` series), with a
deeper evidence pass at each roadmap inflection (a backend lands, the MCP
surface ships, a release cut) — a natural companion to `specs/STATUS.md`
true-ups, and reasonably done in the same sitting.

**Gating:** only the mechanical layer gates. Judgment scores inform
priorities; they never block a landing.

## Backlog for the rubric itself

- [ ] Consolidated mechanical-check script (`uv run` entry point) covering:
      import-DAG acyclicity, README-claims-vs-reality, stale-name grep,
      tracked-artifact check, module size budget.
- [ ] Agent-in-the-loop eval harness (unlocks dimension 6 above 2).
- [ ] Benchmark suite graduated from spec 072 spikes (unlocks dimension 7
      above 2).
