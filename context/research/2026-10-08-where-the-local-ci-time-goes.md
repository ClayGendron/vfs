# Where the local CI time goes: the `scripts/ci.sh` matrix, step by step, and the test suite, test by test

- **Status:** research memo. Commits us to nothing. Input to any decision about speeding up the local CI loop (parallel test execution, concurrent matrix legs, coverage tracing mode, fixture scope in the ranking harness).
- **Date:** 2026-10-08
- **Owner:** Clay Gendron
- **Question:** `scripts/ci.sh` is the gate before every commit that touches `src/`, `tests/`, `crates/` or `pyproject.toml`. It feels slow. Two questions: (1) which steps of the matrix cost the time; (2) inside the test suite, which tests, files and phases cost the time, and why.
- **Method:** two executed runs on 2026-10-08 at commit `06e14b0` (tree clean for `src/`, `tests/`, `scripts/`), on an Apple M1 Pro (10 cores, 32 GB, macOS 26.5.2) with the four `.venv-ci/<version>` environments already built, so every install step is a warm re-sync. Python 3.13.11, pytest 9.0.2, coverage 7.13.3, SQLAlchemy 2.0.52, SQLite 3.50.4.
  1. **The matrix**: a scratch copy of `scripts/ci.sh` patched so the `step` function stamps elapsed wall-clock seconds on every step and prints a summary. All four legs, in the script's own order.
  2. **The suite**: one run on the 3.13 environment without coverage, `pytest --durations=0 --durations-min=0`, which records every test's setup, call and teardown time. Summed by phase, directory, file, test function (parameters merged) and single test.
- **Sources:** `studies/2026-10-08-local-ci-timing/` (the patch, the aggregation script, both raw logs and the aggregate), `scripts/ci.sh`, `.github/workflows/test.yml`, `pyproject.toml` (`[tool.coverage.run]`, `[tool.pytest.ini_options]`), `tests/ranking/test_harness.py`, `tests/storage/test_conformance.py`, `tests/storage/database/test_rights.py`.

Wall-clock numbers here describe one laptop on one day. They are a research measurement, not a test pin; the project's rule that tests count operations rather than seconds stands.

## 1. The matrix, step by step

| Step | 3.11 | 3.12 | 3.13 | 3.14 |
|---|---|---|---|---|
| install (warm re-sync) | 1s | 0s | 0s | 0s |
| lint (`ruff check`) | 0s | 0s | 0s | 0s |
| format (`ruff format --check`) | 0s | 0s | 0s | 0s |
| types (`ty check`) | — | — | 0s | — |
| tests (`pytest`) | 283s | 284s | — | 286s |
| tests + coverage (`pytest --cov`, 100% gate) | — | — | 549s | — |
| docs examples (Sybil over `docs/`) | — | — | 1s | — |
| wheel size (`uv build --wheel`, 50 MB gate) | — | — | 3s | — |

- **Total:** 1,408s (23.5 min). All four legs green.
- **Tests are 1,402 of the 1,408 seconds.** Every other step is a rounding error once the environments are warm. A cold install, which builds the Rust extension, is a different story and was not measured here.
- **The suite runs four times in series**, once per Python. Three plain runs are within 3s of each other (283, 284, 286), so the interpreter version does not matter; the count of runs does.
- **Coverage roughly doubles the 3.13 leg**: 549s against ~284s for a plain run, a 1.93× penalty. The coverage config pins `concurrency = ["greenlet", "thread"]`, which SQLAlchemy's asyncio layer needs so lines after a greenlet switch are not dropped. That tracer is the slow one.

## 2. The suite, one plain run on 3.13

The run collected 5,266 tests, ran 3,919 and skipped 1,347. Every skip is a real-engine leg (Postgres, MariaDB, SQL Server, Oracle, MySQL) whose `VFS_TEST_*_URL` is unset, so skips cost nothing locally. Wall clock 253s; 244s of it inside tests, the rest is collection and session start.

### 2.1 By phase: the test bodies are the cost

| Phase | Time | Share |
|---|---|---|
| call (the test body) | 224.5s | 92.1% |
| setup (fixtures) | 15.9s | 6.5% |
| teardown | 3.2s | 1.3% |

Fixture setup is not the problem. Whatever is slow is slow inside the test function itself.

### 2.2 Concentration: a few dozen tests carry half the time

| Slice | Share of suite time |
|---|---|
| slowest 49 tests (0.9% of tests) | 50% |
| slowest 575 tests (10.9%) | 80% |
| slowest 968 tests (18.4%) | 90% |

44 tests take over one second each. 277 take over 0.1s. The other ~5,000 are effectively free.

### 2.3 By file: three files are 59%, one directory is 38%

| File | Tests run | Time | Share | Mean |
|---|---|---|---|---|
| `tests/ranking/test_harness.py` | 25 | 63.1s | 25.9% | 2.5s |
| `tests/storage/test_conformance.py` | 600 | 50.2s | 20.6% | 0.08s |
| `tests/storage/database/test_rights.py` | 36 | 31.4s | 12.9% | 0.87s |
| rest of `tests/storage/database/` (~25 files) | — | 61.3s | 25.2% | small |
| everything else (~3,200 tests) | — | 37.6s | 15.4% | tiny |

Next in line after the top three: `test_dialects.py` 9.1s, `test_grep.py` 7.7s, `tests/storage/test_grants.py` 7.3s, `test_indexing.py` 5.9s, `tests/base/test_glob_namespace.py` 5.5s, `tests/base/test_dispatch.py` 5.1s.

These are three different cost shapes.

### 2.4 The ranking harness: few tests, each heavy (26%)

Each test loads a whole retrieval corpus into a fresh SQLite mount, builds the index, runs every query and scores the result with nDCG against `baselines.json`. The two BEIR corpora, scifact and nfcorpus, dominate:

| Test (parameters summed) | Time |
|---|---|
| `TestBaseline::test_glean_equals_the_bm25_baseline_on_beir` (scifact 11.0s, nfcorpus 7.4s) | 18.4s |
| `TestHybridArms::test_vector_only_and_fused_are_recorded` (hash 5.2s, potion 4.9s) | 10.2s |
| `TestBaseline::test_bm25_holds_the_gate_on_beir` (scifact 5.1s, nfcorpus 4.2s) | 9.3s |
| `TestArms::test_the_router_merge_beats_the_floors` | 3.9s |
| `TestDeterminism::test_the_merge_ordered_top10_pin_holds_on_two_sqlite_mounts` | 2.9s |

The `sqlite` fixture is function-scoped, and `beir(name)` is called inside each test, so the BM25 gate and the glean-equals-BM25 test each load and index the same corpus from scratch. Each BEIR corpus is loaded at least twice per run. The hybrid arms embed the corpus with two embedders (hash, potion) on top of loading it.

### 2.5 Conformance: many tests, each cheap (21%)

The storage contract (`StorageContract` + `GrantsContract`) is 300 tests, run once against the in-memory backend and once against file-backed SQLite.

| Class | Tests | Total | Mean | Setup | Call | Teardown |
|---|---|---|---|---|---|---|
| `TestSqliteConformance` | 300 | 29.3s | 0.098s | 7.4s | 19.6s | 2.3s |
| `TestMemoryConformance` | 300 | 20.9s | 0.070s | 2.1s | 18.8s | 0.0s |

No single test is slow; the slowest is `test_anonymous_is_unauthenticated_on_every_verb_of_a_private_mount` at 3.6s summed across both backends. The count is the cost. The SQLite class spends 7.4s in setup alone because every test opens a fresh database file and creates the schema. The in-memory backend is a SQLite engine too, which is why its call time is nearly the same.

### 2.6 Rights: exhaustive oracle checks (13%)

Each test builds a layout of mounts, grants and postures, then asks the pure-Python grants oracle and the real SQL read path the same question for every path and every caller, and compares. Parametrizing over layouts and parameter budgets multiplies the work.

| Test (parameters summed) | Time |
|---|---|
| `test_the_clauses_admit_exactly_what_the_rights_admit` (layout × parameter_budget) | 6.4s |
| `test_the_trash_is_judged_by_its_origin_against_the_oracle` (base, siblings) | 4.5s |
| `test_glob_names_exactly_the_visible_rows_and_their_road` | 4.5s |
| `test_reads_match_the_oracle_while_a_posture_relabel_is_held_midway` | 4.0s |
| `test_every_row_carries_the_oracles_everyone_level_after_every_mutation` | 3.6s |
| `test_a_road_row_carries_its_name_and_kind_only` | 3.0s |

`tests/storage/test_grants.py` is the same shape at 7.3s, led by `test_the_resolver_agrees_with_the_oracle_on_every_path` at 4.8s.

### 2.7 Deliberate scale pins

Two tests in `test_dialects.py::TestMembershipChunking` round-trip 10,000-element batches: the edge batch at 4.4s and the entry batch at 3.3s. They pin the declared contract that 10k batches are supported, so their cost is earned, and they are the only place a single scale-shaped test shows up in the top 20.

## 3. Findings

1. **Tooling is free; tests are everything.** Lint, format, types, docs examples and the wheel gate together cost ~5s of a 1,408s matrix. There is nothing to win outside `pytest`.
2. **The matrix is 4 serial suite runs plus a 2× coverage penalty.** One plain run is ~284s; the matrix is 3 × 284 + 549. Any change to the suite is multiplied by five effective runs.
3. **Inside a run the cost is in test bodies, not fixtures**, and it is concentrated: 49 tests are half the time.
4. **Three cost shapes, three files.** Heavy corpus tests (ranking harness), a wide cheap contract run twice (conformance), and exhaustive oracle comparison (rights, grants).
5. **The suite is parallel-shaped.** Nearly every test isolates itself in `tmp_path` or an in-memory engine, and the autouse fixture in `tests/conftest.py` disposes memory storages per test. Nothing observed depends on test order or shared on-disk state.

## 4. Levers, in order of expected payoff (not applied)

1. **Run tests in parallel** (pytest-xdist). Several-fold on a 10-core laptop, touches no test logic. The 1,347 skips and the few `monkeypatch`-on-class tests need a look for worker safety.
2. **Run the four matrix legs concurrently** in `scripts/ci.sh`. Each leg already has its own `.venv-ci/<version>`; only the terminal output interleaves.
3. **Load each BEIR corpus once per run** by giving the ranking harness a module-scoped loaded corpus the gate and the glean test share. Roughly 10–15s per run, ~60s across the matrix.
4. **Try coverage's `sys.monitoring` core on 3.12+** (`COVERAGE_CORE=sysmon`). It may not honour greenlet concurrency, which the config needs; test on the 3.13 leg and compare line counts before trusting it.

## 5. Not measured

- A cold install (Rust extension build via maturin) on any leg.
- The real-engine legs; all were skipped here.
- Variance: each number is one run. The three plain legs agreeing within 3s suggests the suite is stable, but no repeat was made.
- Memory or CPU saturation; a 10-core machine ran one process.
