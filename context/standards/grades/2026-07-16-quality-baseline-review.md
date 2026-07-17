# Quality baseline review — 2026-07-16

- **Status:** recorded
- **Rubric:** [`standards/quality-rubric.md`](../quality-rubric.md) v0.1
- **Tree:** `main` at `445b2ef`
- **Method:** mechanical facts gathered by direct inspection (pytest
  collection, pyproject/CI config, `git ls-files`, line counts, import
  structure); judgment scores from a read of `src/vfs/`, `tests/`, and
  `context/` against the rubric's checks.

This is the baseline the rubric's first delta will be measured against.

## Score data

Machine-readable record of this review: raw scores on the rubric's 0–4
maturity scale. Weights live only in the
[rubric](../quality-rubric.md)'s weights block; compute weighted totals by
joining against it (`Σ score/4 × weight`).

```json
{
  "review_date": "2026-07-16",
  "rubric_version": "0.1",
  "tree": {"branch": "main", "commit": "445b2ef"},
  "scores": [
    {"id": 1, "name": "correctness-and-verification", "score": 3.5},
    {"id": 2, "name": "constitutional-compliance", "score": 3.0},
    {"id": 3, "name": "architecture-integrity", "score": 4.0},
    {"id": 4, "name": "code-health", "score": 3.5},
    {"id": 5, "name": "context-fidelity", "score": 2.5},
    {"id": 6, "name": "fitness-for-purpose", "score": 2.0},
    {"id": 7, "name": "performance-and-scale", "score": 2.5},
    {"id": 8, "name": "repo-hygiene-and-delivery", "score": 2.0}
  ]
}
```

## Scorecard

| # | Dimension | Score |
|---|---|---|
| 1 | Correctness & verification | 3.5 |
| 2 | Constitutional compliance | 3.0 |
| 3 | Architecture integrity | 4.0 |
| 4 | Code health | 3.5 |
| 5 | Context fidelity | 2.5 |
| 6 | Fitness for purpose | 2.0 |
| 7 | Performance & scale | 2.5 |
| 8 | Repo hygiene & delivery | 2.0 |

Weighted under rubric v0.1 weights: **75 / 100**.

Read: unusually strong bones — architecture, verification, and
self-documentation are near the top of the scale. Every weak spot is
periphery: docs drifted from code, root-directory cruft, and the
not-yet-built proof that the agent-ergonomics thesis holds.

## Evidence by dimension

### 1. Correctness & verification — 3.5

- 1,602 tests collected across 20 files; CI enforces `--cov-fail-under=99`
  on every run (test.yml, Python 3.12/3.13/3.14 matrix).
- Storage conformance suite (`tests/storage_conformance.py`, ~100 methods)
  with per-op `needs()` gating; bound to SQLite in
  `test_storage_conformance.py`. Result law tests (~60) in
  `test_result_laws.py`. Shared doubles in `base_doubles.py`.
- **Deductions:** no property-based testing anywhere (Hypothesis absent) —
  path grammar and result algebra are ideal candidates; no mutation-testing
  practice.

### 2. Constitutional compliance — 3.0

- One envelope, closed error taxonomy, and derived capabilities are real and
  tested for the landed core.
- **Deductions:** fan-out has no time budget (`_gather_settled` gathers with
  no deadline; spec 051 open) and the `timeout` error kind in
  `results/kinds.py` is defined but unused — a promised behavior with no
  implementation. Bounded-output semantics not yet uniformly verified across
  every verb.

### 3. Architecture integrity — 4.0

- Import graph is a clean acyclic DAG; `base.py` is the sole top-of-DAG
  consumer and nothing imports it except `__init__.py`. Anti-cycle layering
  is documented in module docstrings, not incidental.
- Single-source op vocabulary (`ops.py`) consumed by router, permissions,
  projection. Entry↔Observation lockstep held by a drift test. Zero
  TODO/FIXME/HACK in live code.
- **Watch items (not deductions yet):** `base.py` at 2,065 lines / ~40
  private methods; spec 070's Principal change (~87 `user_id` touch points)
  will test whether it stays one coherent chokepoint. `paths.py` at 1,125
  lines.

### 4. Code health — 3.5

- `ruff` (18 rule families, 2 ignores) and `ty` at zero across
  `src/` + `tests/`. Docstring bar is exceptional — every module opens with
  an intent-explaining docstring; sparse `noqa` / `type: ignore` each carry
  rationale.
- **Deductions:** POSIX-rule logic duplicated between
  `storage/backends/memory.py` (844 lines) and the database backend; two
  1,000+ line modules.

### 5. Context fidelity — 2.5

The context *system* is excellent; the *sync* is leaky. Drift found:

- `standards/testing.md` still references `grover`, `GroverResult`, and
  `tests_old/` — describes the previous generation.
- `CONTRIBUTING.md` is titled "Contributing to Grover".
- README claims a 1,094-test suite; the tree collects 1,602.
- `open-questions.md` is an empty placeholder while clarification markers
  live in spec files (e.g. 072 §4/§5/§8/§9/§12 per `specs/STATUS.md`).
- Tracked `coverage.json` is dated 2026-04-23 (~3 months stale).
- **Credit:** `specs/STATUS.md` true-up procedure is real and recent
  (2026-07-10/12); decisions and research memos are genuinely maintained.

### 6. Fitness for purpose — 2.0

- Capped at 2 by the rubric: no agent-in-the-loop eval harness exists, so
  the mission's central claims (agent ergonomics, "under an hour" setup) are
  untested end-to-end.
- No runnable example app on the v2 core; PyPI (`vfs-py 0.0.22`) still ships
  the previous-generation API.
- **Credit:** the gap is labeled honestly in the README's alpha disclaimer.

### 7. Performance & scale — 2.5

- Serious spike work exists (spec 072: SQLite + Postgres measured at ~1M
  docs, posting-encoding comparisons) but as one-off research, not a
  rerunnable harness with tracked trends.

### 8. Repo hygiene & delivery — 2.0

- **Credit:** CI matrix 3.12–3.14, trusted-publishing PyPI pipeline, mkdocs
  Material site with Diátaxis nav, real Keep-a-Changelog, `uv.lock`
  committed.
- **Deductions — tracked cruft (`git ls-files` confirmed):**
  `coverage.json` (351 KB artifact; `.gitignore` misses the `.json`
  variant), `pr_description.md`, `grep_glob research/` (directory name
  contains a space), `grover-lookbook.html`, `Grover_The_Agentic_File_System.md`,
  `ROADMAP-v0.1.0.md`, `Validate SQLModel on all Non-Database Sourced
  Data.md`.

## Cheapest points on the table

1. **Drift + cruft pass** (dimensions 5 and 8): fix the stale-name docs,
   true up the README test count, untrack the root cruft, extend
   `.gitignore`. Roughly +4 weighted points in an afternoon.
2. **Property-based tests** for `paths.py` and the result algebra
   (dimension 1 → 4.0).
3. **Wire the `timeout` kind** to a real fan-out deadline via spec 051
   (dimension 2 → 3.5).
4. **Agent eval harness** (dimension 6): highest-value, most work — the only
   dimension where nothing measurable exists, and the one the mission stakes
   everything on.
