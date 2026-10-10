# 163 — The one-minute test run: parallel workers, a `slow` tier, and 300,000 fewer statements

- **Status:** **built 2026-10-10, awaiting Clay's review** — all six
  slices landed as six commits the same day the spec was cut (2bf0138,
  740718e, cee25f8, 6c6f343, 21a9cad, b648082); the default run is 43 s
  quiet, the slow-tier coverage leg 103 s at 100%, and the four real-engine
  legs green. See *Landing notes* for the measurements, the deviations and
  the one acceptance item not met. The decisions below were taken inside
  the spec rather than in an ADR (Clay, 2026-10-10: "no need for an ADR")
  and are listed under *Decisions this spec takes* so they can be
  overturned in one place.
- **Date:** 2026-10-10
- **Owner:** Clay Gendron
- **Kind:** test infrastructure (pytest configuration, fixtures, the
  conformance and harness modules, `scripts/ci.sh`, the workflow) plus
  four small `src/` changes that the measurements surfaced: a
  provisioning guard, two caches and a leak fix. No verb changes
  semantics.
- **Depends on:** nothing lands first. Spec 157 (Postgres provisioning
  for host apps) touches the same `_verify_or_provision` and should land
  after item 4a or rebase onto it.
- **Research it stands on:**
  `../../../research/2026-10-10-the-test-suite-slice-by-slice.md` (every
  number below is measured there; its `studies/` directory holds the
  measured variants) and
  `../../../research/2026-10-08-where-the-local-ci-time-goes.md`.

## Intent

The default local run, `uv run pytest`, is the inner loop. Today it is
253 seconds serial on Clay's laptop and about 100 seconds under ten
parallel workers, and no single change gets it under a minute. The memo
found why: the suite crosses the async boundary about 300,000 times a
run, a quarter of those crossings provision schemas that are identical
every time, and parallel workers cap at 2.5× because the cores are busy
rather than idle. So the work is in three parts that compound: run the
suite in parallel, move the few deliberately heavy tests behind a tier
that CI still runs, and cut the statement count in the tests and in the
two `src/` paths every test goes through.

The rule that binds every item: a test asks the same questions and
checks the same answers after this spec as before. Where a strategy
shrinks a test's domain, the spec says so and CI keeps the full domain.

One line: the default run finishes in under a minute, CI still proves
everything it proves today, and the suite leaves 300,000 statements and
1.86 million leaked objects behind.

## What is wrong today (measured 2026-10-10 at `76ce536`)

1. **One serial run is 253s; ten workers reach 101s and stop.** 16 and
   20 workers do not help. The same tests burn 2.2 to 2.8× the CPU at
   ten workers that they burn at one, so the cores saturate. Memo §3.
2. **1,201 mounts are provisioned per run, 94 statements each.** 41 are
   DDL, 42 are `has_table` PRAGMAs from `create_all(checkfirst=True)`.
   The same DDL costs 0.7 ms through raw `sqlite3` and 15 to 26 ms
   through SQLAlchemy async, because each statement is two thread
   wake-ups. Fsync and in-memory versus file measured as noise. Memo §2.
3. **`build_vfs_tables` mints a fresh `MetaData` for every storage**, 8
   ms each, 493 times in `tests/base` alone; `RendererRegistry.bundled()`
   reads four dist-info files per storage. Memo §4.5.
4. **`_BULK_STATEMENTS` in `dialects.py` is a leak.** It is keyed by the
   `Table` object and never evicts, so every mount ever created stays
   alive with its metadata: 1.86 million objects after `tests/base`,
   ~4.5s of GC and interpreter shutdown per run, and a growing heap in
   any production process that mounts and unmounts. Memo §4.5.
5. **The ranking harness loads the golden corpus 19 times and each BEIR
   corpus twice**, then spends most of its time in the `glean` verb.
   The BEIR tests are already marked `slow`, and nothing deselects that
   marker anywhere. Memo §4.1.
6. **The conformance contract runs twice**, on an in-memory backend that
   is the same `DatabaseStorage` over `sqlite+aiosqlite:///:memory:`,
   with 100% overlap in the questions asked. 51,000 statements per
   class, 55% of them first touch. Memo §4.2.
7. **The rights sweeps spend 70 to 85% of their time building layouts**,
   and the oracle itself is free (0.03s a test). The clauses test
   replays 60 worlds to check three parameter budgets that could share
   worlds. Memo §4.3.
8. **Seven tests sleep for ~7s** to prove "the loop keeps ticking", and
   assert `max(gaps) < 0.25`, a wall-clock assertion the project rule
   forbids. Four exhaustion tests wait out real retry backoff. Memo §4.4.
9. **The 10k scale pins spend 38% of their time compiling INSERTs** and
   never chunk an `IN` list on SQLite (budget 32,734); the three
   `tiny_budget` tests already prove chunking. Memo §4.4.
10. **Two things are not worker-safe.** The harness's re-baseline mode
    read-modify-writes `baselines.json` per test, and one test in
    `test_reads.py` closes its loop before an aiosqlite thread reports
    back. Memo §3.

## Decisions this spec takes

Each is a choice the memo left to Clay. The spec takes the one the
numbers favour; overturn it here and the scope below follows.

- **D1. The `slow` tier is real and CI runs it.** `slow` deselects by
  default in every `pytest` invocation; the 3.13 coverage leg of
  `scripts/ci.sh` and the workflow pass `--slow` and run everything.
  Nothing a `slow` test proves leaves CI; it leaves the inner loop.
- **D2. The conformance contract runs once by default, on file-backed
  SQLite.** `TestMemoryConformance` moves under `slow`. The two classes
  differ only in pool and real file I/O, no contract test uses
  concurrency, and the in-memory backend is exercised by every
  `VirtualFileSystem()` test in `tests/base`. CI keeps both.
- **D3. The 10k pins stay 10k, under `slow`; the default run pins the
  same contract at 2,500 and 2,000.** 2,500 entries still page the bulk
  insert (7 statements); 2,000 patterns still fan into 10 statements.
  The declared 10k contract is proven on every CI leg that runs `slow`.
- **D4. The provisioning guard skips `create_all` only on an existing
  mount.** A fresh mount keeps `create_all(checkfirst=True)` exactly as
  today, so the designed rival-first-touch race is untouched. The
  behaviour change is confined to a mount whose meta table exists but
  whose other tables do not: it is no longer silently repaired; it
  fails at the first verb that touches the missing table, the same way a
  schema-version mismatch is refused. A production reopen of an existing
  mount saves 84 of 94 statements.

## Scope

Grouped by landing slice. Every slice leaves the tree green on its own.
Savings are the memo's measured numbers, serial, on the loaded laptop;
treat them as relative.

### 1. Parallel workers and the tier (the frame)

- 1a. `pytest-xdist` joins the `dev` dependency group;
  `[tool.pytest.ini_options] addopts` gains `-n auto`. Worker count
  comes from the machine, so a 2-core CI runner gets 2.
- 1b. A `--slow` option in `tests/conftest.py` (`pytest_addoption` plus
  `pytest_collection_modifyitems` deselecting `slow` items when it is
  absent). Deselection, not `skip`, so the summary line counts only what
  ran. `scripts/ci.sh` passes `--slow` on the 3.13 coverage leg and the
  workflow mirrors it; the three plain legs run the default tier.
- 1c. The engine legs are deselected by marker, not skipped at fixture
  time: the same hook deselects `postgres`, `mariadb`, `mssql` and
  `oracle` items unless their `VFS_TEST_*_URL` is set. Saves 1.25s and
  makes "1,347 skipped" disappear from a local run. The dialects
  workflow's `-m <dialect>` keeps working because it sets the URL.
- 1d. The docs fences (`pytest docs README.md`) run with `-n 0`
  in `scripts/ci.sh` and the workflow: Sybil changes directory per page
  and depends on document order.
- 1e. Worker safety: the harness module docstring says re-baseline and
  re-pin modes need `-n 0`, and `gate()` refuses to rewrite
  `baselines.json` when `PYTEST_XDIST_WORKER` is set; the
  `test_a_contradicted_arm_is_dead_before_sql` teardown closes its
  storage before the loop ends (the aiosqlite thread warning in memo
  §3). Any other `PytestUnhandledThreadExceptionWarning` under `-n auto`
  is a failure of this item.
- 1f. The `test_suite` skill, CLAUDE.md's tooling section and the
  2026-10-08 skill numbers ("~2276 passed") are updated to the new
  commands and the new healthy counts.

### 2. Provisioning once per process (the template databases)

- 2a. `tests/support/database_helpers.py::_url` returns a copy of a
  once-per-process provisioned `vfs.sqlite` in `tmp_path`
  (`tempfile.mkdtemp` per process, built via first touch on a private
  thread so async callers can mint it; copy is 0.2 ms). The one test
  that builds its own half-provisioned schema takes a pristine URL
  through a sibling helper. First touch across `tests/storage/database`
  drops from 19.9s to 9.1s; cold provisioning stays proven by the
  template build and by `test_engine.py`'s first-touch tests. Memo §4.4 A.
- 2b. `tests/storage/test_conformance.py`: the file-backed class copies
  a per-session template from `tmp_path_factory` per test; the memory
  class restores a `sqlite3` template into the StaticPool connection
  through the `backup` API before first touch. 51.0k statements per
  class become 31.0k; −3s memory, −9s file. All tests in a class share
  one `mount_identity`, which no contract test reads. Memo §4.2 A.
- 2c. The real-engine classes keep `server_schemas` untouched.

### 3. The harness, the oracles, the sleeps (test-side, nothing lost)

- 3a. Ranking harness: module-scoped `golden_loaded`, a parametrized
  `beir_loaded` that carries its driver run, and `golden_mounts` for the
  two-mount tests, with module loop scope on the async classes and the
  `sqlite` fixture. The sqlite top-10 pin and the merge pin take an
  optional loaded corpus. One embedded mount per hybrid embedder, the
  ranker swapped between arms through a public seam on the storage (not
  `_ranker`). An `xdist_group` per corpus so the BEIR loads do not
  serialise on one worker. 67s to ~53s. Memo §4.1 A, A2.
- 3b. `tests/support/oracles/grants.py`: `GrantWorld.closure` memoised
  per world (`member_of` never mutates after construction).
  `test_grants.py` 8.0s to 5.4s. Memo §4.3 S4.
- 3c. `test_rights.py`: the clauses test replays each world once and
  checks all three parameter budgets on it (60 replays to 20); the
  road-row stat check runs on the glob test's worlds (60 to 30). Each
  budget still sees ten worlds per layout and the road check still sees
  30 worlds × 5 subject sets; what changes is that the budgets no longer
  see independent random worlds. −9s. Memo §4.3 S2, S3.
- 3d. The seven "loop keeps ticking" tests count the ticks observed
  during each blocking hop and assert on the count, with the doubles'
  sleeps cut to 0.1 to 0.2s; the `max(gaps) < x` assertions go. The four
  exhaustion-classification tests set the host's retry base delay to
  zero. 8.6s to 3.1s. Memo §4.4 C, D.
- 3e. The two immutable-world tests in `test_glob_namespace.py` and
  `test_grep_namespace.py` take module-scoped, module-loop worlds that
  close in the fixture. ~3.5s. Memo §4.5.

### 4. The `src/` changes

- 4a. `engine.py::_verify_or_provision`: one `has_table(meta)` inspect
  first; when the meta table exists, skip `create_all` and go straight to
  the version row; when it does not, `create_all(checkfirst=True)` as
  today. Decision D4. With 2a and 2b, memory conformance 28s to 21s and
  file 33s to 24s; ≈12s and 48k statements across a serial run. Lands
  only after the `db_test` legs (Postgres, MariaDB, MSSQL, Oracle) are
  green on it. Memo §4.2 B, §4.3 S5.
- 4b. `models/rows.py::build_vfs_tables` is cached per
  `(schema, native_embedding)`: the `VFSTables` it returns is immutable
  after build and carries no engine binding. `__init__` 4.4s to 0.8s
  across the database slice; `tests/base` 31s to 21s together with 4c.
  Memo §4.4 B, §4.5.
- 4c. `rendering/registry.py`: `generation_of` reads
  `importlib.metadata.version()` once per renderer class, not per
  registry. Memo §4.5.
- 4d. `dialects.py::_BULK_STATEMENTS` moves off the module onto the
  engine host, keyed by `(table.name, keys)`; dialect facts are constant
  per host, and the cache dies with the storage. The comment's claim,
  "bounded by live mounts", becomes true. A test pins that closing a
  storage releases its tables (`gc` and a weakref). Memo §4.5.
- 4e. **Not in scope, recorded for their own specs**: `glean` fetching
  entry rows for all 1,000 fusion candidates per query with an
  unconditional preview (memo §5 item 4), and bulk insert compiling
  once per page rather than once per page shape (memo §5 item 5). Both
  are product performance work.

### 5. The scale pins and the second conformance class (decisions D2, D3)

- 5a. `test_dialects.py::TestMembershipChunking` and
  `test_reads.py::TestPatternFan`: the 10k round-trips and the 10k
  pattern fan are marked `slow`; a sibling at 2,500 entries and 2,000
  patterns runs by default and asserts the same paging and fan counts
  (7 INSERT statements, 10 fan statements). −6.5s default. Memo §4.4 E′.
- 5b. `TestMemoryConformance` is marked `slow`. −21 to −29s default.
  Memo §4.2 F.
- 5c. The BEIR harness tests stay `slow` and now actually deselect.
  −16s default on top of 3a. Memo §4.1 B.

## Non-goals

- Running the real-engine legs in parallel; they keep `-n 0` in the
  dialects workflow and the `db_test` skill until each leg has its own
  schema per worker.
- Running the four `scripts/ci.sh` legs concurrently (memo 2026-10-08
  lever 2); a separate, smaller change.
- A pre-indexed SQLite fixture for the harness or a smaller golden
  corpus; both measured as bad trades (memo §1).
- `PRAGMA synchronous`, in-memory substitution, `--import-mode`, plugin
  trims; all measured within noise.
- Explaining why per-test CPU inflates 2× under ten workers (memo §7);
  it changes which later fix helps xdist most, not this spec.

## Acceptance criteria

1. `uv run pytest` on Clay's laptop, quiet, finishes in **under 60
   seconds wall** with every selected test passing and no
   `PytestUnhandledThreadExceptionWarning`. Recorded in the landing notes
   as a measurement, not pinned by a test.
2. `uv run pytest --slow` selects every test the suite selects today
   minus nothing: the BEIR gates, the 10k pins, `TestMemoryConformance`
   all run and pass. `scripts/ci.sh 3.13` is green at 100% coverage with
   `--slow` and `-n auto` together.
3. A local run with no `VFS_TEST_*_URL` reports zero skips from the
   engine legs; `-m postgres` with the URL set still selects the Postgres
   leg.
4. The suite issues fewer than **120,000 statements** in a default run
   and provisions fewer than **200 mounts** from scratch (the
   statement-counting plugin from the study is the measure; recorded in
   landing notes, not pinned).
5. After the suite, no `MetaData` is reachable from
   `vfs.storage.backends.database.dialects`; a test pins that closing a
   storage releases its tables.
6. No test asserts on elapsed time; the `max(gaps)` assertions are gone
   and the tick tests assert counts.
7. The `db_test` legs are green on 4a before it lands, and a mount whose
   meta table exists with a missing sibling table fails at first use with
   a classified `unavailable`, pinned by a test on SQLite.
8. Every nDCG baseline and top-10 pin in `tests/fixtures/ranking/` is
   byte-identical before and after 3a.
9. `pytest docs README.md -n 0 -p no:cov` is green.
10. ruff, format and ty at zero; the `test_suite` skill and CLAUDE.md
    name the new commands and counts.

## Tasks

Landing order. Each numbered task is one green commit; a slice may be
several.

1. **Frame**: 1a, 1b, 1c, 1d, 1e, 1f. Run the suite three times under
   `-n auto` and record the wall and any thread warnings. Then 5c, which
   is only a consequence of 1b.
2. **Templates**: 2a, 2b, 2c. Record the statement count before and
   after with the study's counting plugin.
3. **Test-side levers**: 3a, 3b, 3c, 3d, 3e, in that order; 3a and 3c
   are the two with a proof-shape change and get their own commits.
4. **`src/` caches and the leak**: 4b, 4c, 4d. No behaviour change;
   suite and `db_test` legs green.
5. **The guard**: 4a behind the `db_test` legs; the missing-table test
   of acceptance 7.
6. **Tiers**: 5a, 5b. Re-measure acceptance 1 and 4; write the landing
   notes with the before/after table; update `STATUS.md`.

## Landing notes (2026-10-10)

Six commits, one per slice, each green on its own (ruff, format, ty, the
default run, the `--slow` coverage leg at 100%); the real-engine legs ran
on slices 4 and 5 together. Every number is from Clay's M1 Pro, quiet.

| Measure | Before | After |
|---|---|---|
| default run, wall | 253 s serial; 101 s at ten workers | **42.8 / 43.1 / 51.9 s** (three runs, the first after a venv sync) |
| tests in the default run | 3,957 (plus 1,347 engine-leg skips) | 3,650 selected, 0 skipped |
| `--slow` coverage leg | 549 s serial | 103 s, 3,959 passed, 100% |
| CPU per default run | 244 s | 258 s across 7 cores |
| SQL statements per serial run | ~303,000 | 180,962 |
| mounts provisioned from nothing | 1,201 | 519 |
| aiosqlite threads leaked | intermittent warning | 0 (thread-watch plugin over the whole suite) |
| real-engine legs | — | Postgres 335, MariaDB 327 (+8 capability skips), MSSQL 336, Oracle 331 passed |

**What the memo had wrong.** Work-stealing is not a no-op: the memo's
97 s reading was taken under investigator load. Sampling a quiet
ten-worker run showed the last twenty seconds on one worker, and
`--dist worksteal` took 78–82 s to 57–59 s on the slice-1 tree. It is in
the default options.

**Deviations from the scope.**

- *2b, the memory conformance template.* Not applied. The measured
  variant reached into aiosqlite's private connection attributes to run
  the `backup` API, and the class moved to the slow tier in slice 6, so
  it bought three seconds of CI time. The file-backed template landed.
- *1d.* `-p no:xdist` makes the `-n auto` default an unrecognised option;
  the serial form is `-n 0`, used in `scripts/ci.sh`, the workflow and
  the skill.
- *1e.* The thread warning's cause was three executor-ownership tests
  that race a verb against `close()`; the connection the verb re-minted
  belonged to the disposed pool and was collected after the loop closed.
  They now close, collect and yield while the loop lives. The autouse
  disposer also widened from `InMemoryStorage` to every
  `DatabaseStorage`.
- *3d.* The tick tests are stricter than "count ticks during a hop": the
  blocking double waits from its worker thread until the loop's turn
  counter moves, so a hop that ran inline cannot pass, and the test
  asserts the hop count. The two queue-wait budget tests drive the
  offload module's clock from the job that holds the pool, so the budget
  is an exact expected number rather than a bound.
- *4b.* The family cache is a bounded LRU (64 shapes), not an unbounded
  `cache`: a host placing tenants in their own schemas would otherwise
  hold every family forever. The pin that two mounts never share schema
  objects, from the original row definitions, became a cross-schema pin.
- *4d.* The bulk-statement cache stays on the module; its key is now the
  table's schema, name and column-type signature (strings only), which
  bounds it by distinct shapes and retains no metadata. A pin asserts
  two mounts of one shape add nothing and that no key holds a table.
- *A spec-154 leftover.* The hot-row storm race test on MSSQL and Oracle
  still matched message templates spec 154 retired; it asserts the kind
  and retry class now. It skips on SQLite, which is why 154's landing
  did not see it.

**Acceptance.** Items 1, 2, 3, 5, 6, 7, 8, 9 and 10 are met as written.
**Item 4 is not met**: 180,962 statements and 519 cold mounts against
the 120,000 and 200 the spec projected. Every remaining cold mount is an
`InMemoryStorage` (`:memory:`), which no file copy can serve: 155 in the
rights replays, 107 in `test_dispatch.py`, 63 in `test_glob_namespace.py`,
and the rest across `tests/base`. The lever is a process-level template
restored through SQLite's `backup` API into the memory connection at
first touch, inside `InMemoryStorage`, which means touching aiosqlite's
connection internals or adding a seam for it; it is a src design choice
and is left for Clay. The wall-clock goal does not need it.

**Still open.** Why per-test CPU inflates under ten workers
(`open-questions.md`); the MariaDB leg's 48 pooled-connection warnings
in the hot-row storm test, which predate this spec.
