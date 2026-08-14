---
name: test_suite
description: Test the full library end-to-end — the fast inner loop on one Python, the full CI-parity matrix (scripts/ci.sh, Python 3.11–3.14 with lint/format/types/coverage) to verify "this is green" before commit and push, and the real-engine database legs. Use when the user asks to "run the tests", "run the full suite", "run the matrix", "check CI parity", "verify this is green", or before any commit/push that touches src/, tests/, or pyproject.toml.
---

# Testing the library end-to-end

Three tiers, cheapest first. The rule: **tier 2 must be green before any
commit/push that touches `src/`, `tests/`, or `pyproject.toml`** — those
paths are exactly what triggers the CI Tests job.

| Tier | Command | Covers | When |
| --- | --- | --- | --- |
| 1 Inner loop | `uv run pytest --tb=short` (+ ruff/ty below) | one Python, sqlite | while iterating |
| 2 CI parity | `scripts/ci.sh` | Python 3.11–3.14, lint, format, types, 100% coverage | before commit/push |
| 3 Real engines | `db_test` skill | Postgres/MySQL/MSSQL/Oracle in Docker | database-touching changes |

## Tier 1 — inner loop (one Python, seconds to start)

Runs in the project's main `.venv` on the default interpreter:

```sh
uv run pytest --tb=short                    # full suite, sqlite backend
uv run pytest tests/pattern_matching/ -q    # one area while iterating
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run ty check src/ tests/
```

Green here is *not* "green in CI": it exercises one Python version, and
version-conditional behavior is real (e.g. the stdlib glob translators
emit `\Z` through 3.13 but `\z` on 3.14+, and the parity tests only run
on 3.13+). Always finish with tier 2.

## Tier 2 — CI parity matrix (`scripts/ci.sh`)

`scripts/ci.sh` is a local mirror of the CI **Tests** job
(`.github/workflows/test.yml`): the same steps with the same flags, in the
same order, per matrix leg —

1. `uv sync --all-extras --group dev` (tool versions come from `uv.lock`,
   so ruff/ty match CI exactly)
2. `ruff check src/ tests/`
3. `ruff format --check src/ tests/`
4. `ty check src/ tests/` — **3.13 leg only**
5. `pytest --tb=short` — on the **3.13 leg** with
   `--cov --cov-report=term-missing --cov-report=xml --cov-fail-under=100`

```sh
scripts/ci.sh              # full matrix: 3.11 3.12 3.13 3.14
scripts/ci.sh 3.14         # one leg (e.g. reproducing a CI failure)
scripts/ci.sh 3.13 3.14    # any subset
```

Behavior and housekeeping:

- Each leg lives in an isolated env under `.venv-ci/<version>`
  (gitignored); the main `.venv` is never touched. First run downloads
  four environments (minutes); warm re-runs go straight to the checks.
- Legs continue after a failure (CI sets `fail-fast: false`); within a
  leg, the first failing step ends the leg, exactly like CI steps. A
  matrix summary prints at the end; exit 0 means every leg passed.
- When the script changes a leg's verdict vs CI, suspect drift: diff
  `scripts/ci.sh` against `.github/workflows/test.yml` — **the workflow
  is the source of truth, and any workflow edit must be mirrored here.**

Known, accepted parity gaps: local runs macOS vs CI's ubuntu (the suite
is OS-independent; the race tests skip identically on both), and the
Codecov upload is CI-only. Everything else — versions, flags, tool pins,
the 100% coverage gate — is exact.

## Tier 3 — real database engines

The sqlite suite proves logic; the engine legs prove dialect behavior
(bind-parameter budgets, `IN`-list caps, index limits). They correspond
to the separate CI **Dialect tests** workflow and are driven by the
**`db_test` skill** — use it end-to-end (Docker up → legs → teardown)
before landing anything that touches the database backend, the schema
(`models/rows.py`), or a dialect profile. Without its
`VFS_TEST_<ENGINE>_URL` env vars those legs skip, which is why tiers 1–2
never need Docker.

## Reading results

- A healthy full-suite leg currently reports **~2276 passed, ~838
  skipped** (skips are the engine legs and race tests — identical in
  CI). A pass-count far below that means collection broke, not that the
  tree got smaller.
- Coverage below 100 on the 3.13 leg is a hard failure in CI — cover the
  lines or justify a `pragma: no cover`; version-conditional code should
  prefer shapes that stay covered on 3.13 (a one-line ternary over an
  `if`/`try` block whose other arm only runs on 3.14+).
- A leg failing on exactly one Python version usually means a stdlib
  behavior change on that version, not flakiness — reproduce with
  `scripts/ci.sh <version>`, then probe the stdlib delta in scratchpad
  scripts across versions (`uv run --no-project --python 3.X python
  probe.py`) before choosing a fix.
