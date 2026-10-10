---
name: test_suite
description: Test the full library end-to-end — the fast inner loop, the CI-parity gate (scripts/ci.sh: Python 3.13 with lint/format/types/100% coverage/docs fences/wheel budget, about a minute) to verify "this is green" before commit and push, and the real-engine database legs. Use when the user asks to "run the tests", "run the full suite", "run the matrix", "check CI parity", "verify this is green", or before any commit/push that touches src/, tests/, or pyproject.toml.
---

# Testing the library end-to-end

Three tiers, cheapest first. The rule: **tier 2 must be green before any
commit/push that touches `src/`, `tests/`, or `pyproject.toml`** — those
paths are exactly what triggers the CI Tests job.

| Tier | Command | Covers | When |
| --- | --- | --- | --- |
| 1 Inner loop | `uv run pytest --tb=short` (+ ruff/ty below) | one Python, sqlite, parallel workers, the whole suite | while iterating |
| 2 CI parity | `scripts/ci.sh` | Python 3.13: lint, format, types, 100% coverage, docs fences, wheel budget (~65 s) | before commit/push |
| 3 Real engines | `db_test` skill | Postgres/MariaDB/MSSQL/Oracle in Docker | database-touching changes |

## Tier 1 — inner loop (one Python, seconds to start)

Runs in the project's main `.venv` on the default interpreter:

```sh
uv run pytest --tb=short                    # the whole suite, sqlite, one worker per core (~55 s)
uv run pytest -m "not slow" --tb=short      # leave out the BEIR gates, 10k pins and memory conformance
uv run pytest tests/pattern_matching/ -q -n 0   # one area, serial: a few files are faster without workers
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run ty check src/ tests/
```

`addopts` carries `-n auto --dist worksteal` (pytest-xdist), so every
invocation is parallel unless you pass `-n 0`; work-stealing matters here
because a few tests run ten seconds and the plain scheduler leaves them on
one worker at the end (78 s against 57 s, measured 2026-10-10).
`tests/conftest.py` deselects each real-engine leg whose
`VFS_TEST_<ENGINE>_URL` is unset, so a local summary line counts only what
ran. Everything else runs by default; `slow` is an opt-out marker.
The harness rewrite modes (`VFS_RANKING_REBASELINE`, `VFS_RANKING_REPIN`)
refuse to run under workers; pass `-n 0` with them.

Green here is *not* "green in CI": it runs without the coverage gate,
the docs fences or the locked tool versions. Always finish with tier 2.

## Tier 2 — CI parity gate (`scripts/ci.sh`)

`scripts/ci.sh` is a local mirror of the CI **Tests** job
(`.github/workflows/test.yml`): the same steps with the same flags, in the
same order. By default it runs the one leg that carries every gate,
**Python 3.13** —

1. `uv sync --all-extras --group dev --group docs` (tool versions come
   from `uv.lock`, so ruff/ty match CI exactly)
2. `ruff check src/ tests/`
3. `ruff format --check src/ tests/`
4. `ty check src/ tests/`
5. `pytest --tb=short --cov --cov-report=term-missing --cov-report=xml
   --cov-fail-under=100` (coverage's `sys.monitoring` core, set in
   `pyproject.toml`; about 60 s against 100 s on the frame tracer)
6. the docs fences, `pytest docs README.md -p no:cov -n 0` (Sybil
   changes directory per page)
7. the wheel budget: a release wheel built in its own cargo target
   directory (`target/wheel-size`, 2 s warm, 30 s the first time)

The other matrix legs (3.11, 3.12, 3.14) rerun the same tests to catch
stdlib drift between Python versions. CI runs them on every push, so
locally they are opt-in (Clay, 2026-10-10: three identical runs cost
three minutes and slowed every commit):

```sh
scripts/ci.sh                        # the gate: Python 3.13, about 65 s warm
scripts/ci.sh 3.14                   # one other leg (reproducing a CI failure)
scripts/ci.sh 3.11 3.12 3.13 3.14    # the whole CI matrix (about 4.5 min)
```

Behavior and housekeeping:

- Each leg lives in an isolated env under `.venv-ci/<version>`
  (gitignored); the main `.venv` is never touched. The first run of a
  leg downloads its environment (minutes); warm re-runs go straight to
  the checks. After a `pyproject.toml` change, the first sync rebuilds
  the project wheel once (15–25 s).
- Legs continue after a failure (CI sets `fail-fast: false`); within a
  leg, the first failing step ends the leg, exactly like CI steps. A
  summary prints at the end; exit 0 means every leg that ran passed.
- When the script changes a leg's verdict vs CI, suspect drift: diff
  `scripts/ci.sh` against `.github/workflows/test.yml` — **the workflow
  is the source of truth, and any workflow edit must be mirrored here.**
- Legs do not benefit from running side by side: the suite already
  fills every core (measured 2026-10-10: three legs at once took as
  long as three in a row).

Known, accepted parity gaps: local runs macOS vs CI's ubuntu (the suite
is OS-independent; the race tests skip identically on both), the Codecov
upload is CI-only, and the 3.11/3.12/3.14 legs run only in CI unless
asked for. Everything else — flags, tool pins, the 100% coverage gate —
is exact.

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

- A healthy run reports **~3959 passed, 0 skipped** in about 55 s on a
  ten-core laptop; the engine legs are deselected, not
  skipped, so they never appear in the count (set a `VFS_TEST_<ENGINE>_URL`
  and they do). A pass-count far below that means collection broke, not
  that the tree got smaller.
- Coverage below 100 on the 3.13 leg is a hard failure in CI — cover the
  lines or justify a `pragma: no cover`; version-conditional code should
  prefer shapes that stay covered on 3.13 (a one-line ternary over an
  `if`/`try` block whose other arm only runs on 3.14+).
- A leg failing on exactly one Python version usually means a stdlib
  behavior change on that version, not flakiness — reproduce with
  `scripts/ci.sh <version>`, then probe the stdlib delta in scratchpad
  scripts across versions (`uv run --no-project --python 3.X python
  probe.py`) before choosing a fix.
