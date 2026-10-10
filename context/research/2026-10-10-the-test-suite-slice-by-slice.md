# The test suite, slice by slice: what each strategy measurably buys on the road to a one-minute default run

- **Status:** research memo. Commits us to nothing. Input to a decision
  about the shape of the default local test run (parallel workers, a
  `slow` tier, shared fixtures, and three `src/` changes the measurements
  point at).
- **Date:** 2026-10-10
- **Owner:** Clay Gendron
- **Question:** The memo of 2026-10-08 (`2026-10-08-where-the-local-ci-time-goes.md`)
  measured one serial run at 253s and named the slices. Clay's target is a
  default local run (unit tests plus SQLite) under **one minute**. Two
  ideas were on the table: run only SQLite by default, and pre-build the
  BM25 test data. Are those the right levers, and what does each slice
  need?
- **Method:** five parallel investigations on 2026-10-10 at commit
  `76ce536`, one per slice of the 2026-10-08 breakdown, each allowed to
  apply temporary edits to the live tree (backed up and restored by copy,
  never by git) and required to measure every strategy before/after on the
  real tests. Plus three whole-suite runs under `pytest-xdist` (`-n auto`,
  ten workers) by the coordinating session. Apple M1 Pro, Python 3.13,
  pytest 9, SQLAlchemy 2.0, SQLite 3.50.
- **Sources:** `studies/2026-10-10-test-suite-slices/` (every profiling
  script, the drop-in variants that were measured, and the paired-run
  logs, by slice), the 2026-10-08 memo and its raw durations log,
  `tests/ranking/test_harness.py`, `tests/storage/test_conformance.py`,
  `tests/storage/database/test_rights.py`, `tests/storage/test_grants.py`,
  `tests/support/database_helpers.py`, `tests/support/oracles/grants.py`,
  `src/vfs/storage/backends/database/engine.py`,
  `src/vfs/storage/backends/database/dialects.py`,
  `src/vfs/storage/backends/memory.py`.

**A caveat on every wall-clock number below.** The five investigations ran
at the same time on one laptop (load average 5 to 25). Absolute seconds
inside the slice sections are 15 to 30 percent above the quiet 2026-10-08
figures. Every before/after pair was run back to back under the same load,
and wherever a count was available (statements issued, mounts opened,
objects retained) it is the number to trust. Wall-clock is a research
measurement here, never a test pin.

## 1. The two ideas, answered with numbers

**Run only SQLite by default.** Already true in effect. The 1,347 skips
are the Postgres, MariaDB, SQL Server, Oracle and MySQL legs, and they skip
inside the `server_storage()` fixture when `VFS_TEST_*_URL` is unset. The
real-engine legs are a separate CI workflow and the `db_test` skill. What
the skips cost locally: **1.25s** (5.49s run-only against 4.25s
collect-only), because `pytest.skip` inside a fixture still pays the
autouse monkeypatch and the event loop. A marker expression,
`-m "not (postgres or mariadb or mssql or oracle)"`, selects exactly those
1,347 and makes the summary line honest. Worth doing, worth about one
second.

**Pre-build the BM25 test data.** Targets the right file, the wrong cost.
Inside a ranking-harness test the corpus load (write plus reindex) is
3.4s of a 15s scifact test; the `glean` verb is 7.8s. A pre-indexed SQLite
file does reopen in 0.2s instead of 3.3s, but the files are 10.8 MB
(golden) and 35 MB (scifact), too big to check in, and 45 of the 184
commits since 2026-08-01 touched a file that defines the on-disk index, so
the cache would go stale about every fourth commit with no machine check
cheaper than rebuilding it. Shrinking the golden corpus moves every nDCG
baseline (0.759 at 200 docs, 0.732 at half, 0.701 at a quarter, where 7 of
40 queries lose every positive) and forces a re-record of 13 arms and 3
top-10 pins for a saving of 6 to 8s. **Neither is recommended.** The
harness has a better lever (section 4.1).

## 2. One root cause under four of the five slices

The 2026-10-08 memo said the cost is in test bodies, not fixtures. That is
true of where pytest files it and false of what it is. Nearly every test
builds its `DatabaseStorage` inside the body, and the first verb on a fresh
storage runs the provisioning path. Measured across the suite:

| Fact | Number |
|---|---|
| mounts provisioned per run | 1,201 |
| SQL statements per run | ~303,000 |
| statements per fresh mount's first touch | 94 (41 DDL, 42 `has_table` PRAGMAs from `create_all(checkfirst=True)`, pragmas, probe, provision rows) |
| the same 41 DDL statements through raw `sqlite3.executescript` | 0.7 ms |
| the same 41 through SQLAlchemy async | 15 to 26 ms |
| cost per statement across the async hop (main thread, greenlet, aiosqlite thread) | 0.3 to 0.5 ms |
| `PRAGMA synchronous = OFF` | no measurable change, in two slices |
| in-memory instead of file | about 1 ms per commit; breaks every two-mounts-one-file test |

So the suite is not slow because SQLite is slow, and not because of fsync.
It is slow because it crosses the async boundary 300,000 times, and a
quarter of those crossings provision schemas that are identical every
time. The in-memory backend is the same `DatabaseStorage` on
`sqlite+aiosqlite:///:memory:`, which is why the 2026-10-08 memo saw
nearly equal call time on both conformance classes.

The ranking harness is the exception. Its cost is the `glean` verb itself
(section 4.1), a product cost rather than a fixture cost.

## 3. What `pytest-xdist` alone buys

Whole suite, all runs green (3,957 passed, 1,347 skipped):

| Run | Wall | CPU busy | Note |
|---|---|---|---|
| serial, 2026-10-08 | 253s | 1 core | quiet machine |
| `-n auto` (10 workers), `--dist load` | 96.9s | 4.9 cores | under investigator load |
| `-n auto`, `--dist worksteal` | 97.3s | 5.5 cores | same load; scheduling is not the cap |
| `-n auto`, quiet machine | 101.6s | 4.8 cores | |
| `-n 16`, quiet | 100.3s | 5.2 cores | oversubscription buys nothing |
| `-n 20`, quiet | 107.6s | 5.0 cores | and then costs |

So xdist is a **2.5× lever on this laptop, not a 10× one**, and the
scheduler is not why. Two subtrees at 1, 5 and 10 workers, quiet, with
CPU time (`user + sys`) alongside wall:

| Subtree | Workers | Wall | CPU time | Speed-up |
|---|---|---|---|---|
| `tests/storage/database` minus rights (829 tests) | 1 | 68.0s | 54.8s | 1× |
| | 5 | 20.5s | 81.6s | 3.3× |
| | 10 | 16.7s | 121.7s | 4.1× |
| `tests/base` (636 tests, in-memory storages) | 1 | 24.7s | 22.1s | 1× |
| | 5 | 9.8s | 40.2s | 2.5× |
| | 10 | 8.9s | 62.7s | 2.8× |

Read the CPU column: the same tests burn **2.2 to 2.8 times the CPU at
ten workers** that they burn at one. About 25s of that is fixed (each
worker pays ~2.5s of startup: collection, conftest, `import vfs`; a
worker that draws a harness test pays a further 1.4 to 2.6s loading
`ranx`'s numba kernels). The rest is per-test inflation under all-core
load: the M1 Pro has 8 performance and 2 efficiency cores, drops its
clock when every core is busy, and the workers share one cache
hierarchy. Whether the in-memory tests also contend on something
in-kernel (the aiosqlite thread hand-off is two wakeups per statement)
was not separated out. The consequence is the same either way: the cores
are busy, not idle, so the levers that compound with xdist are the ones
that remove CPU work, which is the statement-count reductions in
section 4. Two worker-safety items surfaced:

- `tests/storage/database/test_reads.py::TestPatternFan::test_a_contradicted_arm_is_dead_before_sql`
  raised an unhandled exception in an aiosqlite connection thread (loop
  closed before the worker thread reported back) in one of three runs. An
  order-dependent teardown race; it did not fail the test.
- The harness's re-baseline and re-pin modes (`VFS_RANKING_REBASELINE=1`)
  do read-modify-write on `baselines.json` and `top10*.json` per test;
  two workers in that mode would drop each other's arms. Those modes need
  `-n 0`, documented in the module docstring.

## 4. The slices, with every strategy measured

Each table lists what the strategy is, the measured before/after, what the
tests would stop proving, and a recommendation. "Nothing" in the proof
column means the same questions are asked and the same answers checked.

### 4.1 Ranking harness (`tests/ranking/test_harness.py`, 63s)

Where one test's time goes (seconds, wall):

| Phase | vfs_native (200 docs, 40 q) | scifact (5,183 docs, 300 q) | nfcorpus (3,633 docs, 323 q) |
|---|---|---|---|
| corpus parse | 0.02 | 0.02 | 0.03 |
| `storage.write` | 0.15 | 1.42 | 0.93 |
| `storage.reindex` | 0.85 | 2.03 | 1.37 |
| `bm25_run` (the driver) | 0.15 | 2.22 | 1.27 |
| `glean_run` (the verb) | 0.97 | **7.78** | **4.39** |
| `evaluate`, first call per process (ranx numba cache load) | 2.56 | 1.43 | 1.57 |
| `evaluate`, warm | 0.05 | 0.02 | 0.02 |

The golden corpus is loaded 19 times per run in some shape, each BEIR
corpus twice. Embedder choice (hash versus potion) and write batch size
(250 to 20,000) measured as dead levers: both 1.42s reindex, 1.21 to
1.30s write regardless of batch.

| Strategy | Measured | Stops proving | Recommendation |
|---|---|---|---|
| **A.** Module-scoped loaded corpora (`golden_loaded`, parametrized `beir_loaded` carrying its driver run, `golden_mounts`; module loop scope on the async classes) | 67.3s to 54.9s; scifact glean 12.4 to 7.0, nfcorpus 7.8 to 4.0 | Nothing: every sharer reads only | **Do.** Fold the sqlite top-10 pin and the merge pin in for another ~2.5s |
| **A2.** One embedded mount per hybrid embedder, ranker swapped between arms | hash 5.33 to 4.34, potion 4.95 to 4.01 | Nothing for the gate; fusion is query-time | Do, through a public ranker seam rather than `_ranker` |
| **B.** Deselect the `slow`-marked BEIR tests by default | 67.3s to 39.3s alone; −16s on top of A | The BEIR gates (nDCG 0.658 / 0.305) stop running locally. They are the only out-of-domain BM25 regression check and the only `glean == driver` check on corpora with block overflow | Acceptable for the default local run only if CI keeps them |
| C. Smaller golden corpus | ~0.5s per load, ~0.3s per glean | Every baseline moves; 13 arms and 3 pins re-recorded | Don't |
| D. Pre-indexed SQLite file | ~1s per golden load, ~3s per BEIR load | Load stops exercising write+reindex, which the determinism pins pin | Don't (section 1) |
| G. `glean` per-query cost in `src/` | preview stub: golden glean 0.78 to 0.40s, scifact 7.4 to 6.4s; entry fetch for the 1,000 fusion candidates ≈ 5s on scifact | Nothing; product performance | Record as a product finding (section 5) |

Floor after A and A2: ~55s serial under load, of which one scifact test is
7s. With B: ~35s. Under xdist, group the module per corpus
(`xdist_group`) so the BEIR loads do not serialise on one worker.

### 4.2 Storage conformance (`tests/storage/test_conformance.py`, 50s)

Per class of 300 tests (memory / file):

| Phase | Memory | File |
|---|---|---|
| construct (`build_vfs_tables`, 21 tables) | 1.5s | 1.2s |
| first touch (inside the test's first verb) | 9.1s (32%) | 11.1s (34%) |
| verbs before the verb under test (the arrange writes) | ~12.1s | ~13s |
| the verb under test itself | 1.15s (4%) | — |
| close / dispose | 0.4s | 0.7s |
| statements per class | 51,026, of which 27,918 are first touch | |

| Strategy | Measured | Stops proving | Recommendation |
|---|---|---|---|
| **A.** Per-session template DB (file: one provisioned `vfs.sqlite` from `tmp_path_factory`, copied per test at 0.2 ms; memory: a `sqlite3` template restored through the `backup` API before first touch) | memory −3s, file −9s; 51.0k to 31.0k statements | Fresh provisioning is proven once per session instead of 300 times; all tests share one `mount_identity`, which nothing in the contract reads | **Do** |
| **B.** A plus a `src/` guard: skip `create_all` when the meta table exists (one `has_table` inspect in `_verify_or_provision`) | memory −6.6s, file −11.5s against base; 25.1k statements (−51%) | On an existing mount, first touch no longer silently adds a missing table; it verifies only, consistent with the schema-version refusal | Propose; needs the `db_test` legs before landing (section 5) |
| C. `synchronous = OFF` | within noise | durability posture | No |
| D. Class-scoped storage with delete-all reset | ≤ A+B | fresh backend per test; per-instance caches would leak across tests | No |
| **F.** Run the contract once, not on both backends | halves the slice (~21 to 29s) | The two classes overlap 100% in questions asked; they differ only in pool (QueuePool vs StaticPool plus the serialised-sessions hook) and real file I/O, and no contract test uses concurrency | The biggest single lever. A design decision, not a tuning |

Projection: A plus B takes the two classes from ~61s to ~45s under load
(about −13s at quiet numbers). The ~12s of arrange writes per class is the
floor without changing the contract or the per-statement hop.

### 4.3 Rights and grants oracles (`test_rights.py` 31s, `test_grants.py` 7s)

The oracle is free: 0.03s per test. Layout replay is 70 to 85 percent of
every rights test; the per-mount fixed overhead (first touch 23 ms, 94
statements) is a third of replay. `test_rights.py` alone provisions 225
mounts and issues 77,800 statements, 26 percent of the suite's total.

| Test | Worlds | Replay | Questions | Oracle |
|---|---|---|---|---|
| glob names exactly the visible rows | 30 | 4.5s (78%), 7,677 stmts | 150 globs, 8.3 ms each | 0.03s |
| road row carries name and kind only | 30 | 3.9s (87%) | 89 stats | 0.03s |
| reads match the oracle with a relabel held | 30 | 3.9s (70%) | 150 globs + 30 holds | 0.03s |
| the clauses admit exactly what the rights admit (×6 params) | 10 each | 1.1 to 1.3s (82 to 93%) | 100 × ~8 clauses | ~0 |
| resolver parity in `test_grants.py` | 400 (no DB) | — | 288,000 `admits` | 4.3s, all in `closure` BFS |

Same proof, less work:

| Strategy | Measured | Recommendation |
|---|---|---|
| **S4.** Memoise `GrantWorld.closure` per world in the oracle (`member_of` never mutates after construction) | `test_grants.py` 8.0 to 5.4s | **Do** |
| **S5.** `src/`: fresh-mount first touch skips per-table `checkfirst` | 94 to 54 statements per mount, −10 ms per mount; ≈ −12s and 48k statements suite-wide | Do, as the cross-slice `src/` lever (same decision as 4.2 B) |
| S1. `gather` the replays within a test | −17% at width 4, nothing at width 30 | Low value under xdist; skip |
| Batching questions; module-scoped layouts | already batched; blocked by per-test loops and the autouse disposer | n/a |

Smaller domain, named honestly:

| Strategy | Measured | Stops proving | Recommendation |
|---|---|---|---|
| **S2.** Clauses test: one replay per world, all three `parameter_budget`s checked on it | 9.0 to 3.7s (−5.5s); 60 to 20 replays | Each budget still sees 10 worlds per layout; the budgets no longer see independent random worlds | Yes |
| **S3.** Fold the road-row stat check into the glob test's worlds | two tests 9.0s to one 5.4s (−3.5s) | The road check runs on the glob test's 30 worlds instead of 30 others | Yes |
| S7. `WORLDS` 30 to 10 | ~−9s, linear | A third of the random worlds | Only if the above are not enough |

Combined S2+S3+S4 on the slice: 48 to 51s down to 34.7s under load.

### 4.4 The rest of `tests/storage/database/` (61s, 923 tests, 21 files)

Setup shows as 2.5s because ~300 call sites build the storage inside the
body. The slice opens **614 mounts**; opening them is ~26s of the 61s
(`__init__` 4.4s, first touch 19.9s of which `create_all` 11.9s, close
1.4s). Then three shapes:

- **Wall-clock sleeps, ~7s.** `time.sleep` in doubles that prove "the
  loop keeps ticking" (indexing 4×0.5s, offload 2×1.0s plus 2×0.5s budget
  tests, lexical 0.3s, embed 0.3s), and `with_retry` backoff in four
  exhaustion tests (0.35s each). These assert `max(gaps) < 0.25`, which
  is a wall-clock assertion the project rule already forbids.
- **The 10k pins are SQLAlchemy compile cost, not chunking.** 38% of the
  10k entry write is `_extend_values_for_multiparams` compiling ten
  multi-VALUES INSERT pages of ~26k binds each; 18% path parsing; 12%
  ULID decode. On SQLite `membership_budget` is 32,734, so a 10k batch
  never chunks an `IN` list here; the three `tiny_budget` tests (budget
  48) already prove chunking. What 10k proves on SQLite is bulk-insert
  paging plus end-to-end scale. Paging is still exercised at N=2,500
  (7 INSERTs) and the pattern fan at N=2,000 (10 statements).
- The long tail of ~900 tests at 0.04s each is ~39s of genuine statement
  work.

| Strategy | Measured | Stops proving | Recommendation |
|---|---|---|---|
| **A.** Template DB copy in `tests/support/database_helpers.py::_url` | first touch 19.9 to 9.1s; CPU 50.0 to 40.8s | Cold provisioning is proven by the template build and `test_engine.py`'s first-touch tests; one half-provisioned-schema test needs a pristine URL | **Do** |
| **B.** Cache `build_vfs_tables` per (schema, native_embedding) | `__init__` 4.4 to 0.8s; with A, CPU 40.8 to 34.8s | Nothing: MetaData is immutable after build and carries no engine binding | Do in `src/`; a production win per mount too |
| **C.** Sleep doubles rewritten to count ticks observed during each blocking hop | 6.74 to 2.30s over 7 tests | Nothing, and it removes a forbidden wall-clock assertion | Do |
| **D.** Zero retry backoff in the four exhaustion-classification tests | 1.84 to 0.77s | Nothing; they pin the classification, not the delay | Do |
| **E′.** Keep the scale pins in the default run at N=2,500 / 2,000; N=10k under `slow` | ~−6.5s | Default run proves paging and the fan at a size that still pages; 10k stays in CI | Do |
| F. `synchronous=OFF` or in-memory | ≤1 ms per commit; breaks file-sharing tests | | Reject |

All-in paired run on the slice: **59.9s to 34.7s wall, 46.6s to 27.3s
CPU**. Side finding for `src/`: SQLAlchemy's `insertmanyvalues`
executemany path compiles once per page shape rather than once per page
and would likely halve the 10k write and every bulk ingest.

### 4.5 The long tail and the fixed overhead (38s + ~9s)

Fixed overhead, measured quiet:

| Item | Cost |
|---|---|
| interpreter, plugins, root conftest, `import vfs` (312 ms) | 0.43s |
| collection of 5,304 tests | 3.7 to 4.6s, of which `test_harness.py` ~1.7s (it imports `ranx`, which imports scipy, numba, matplotlib, pandas) |
| engine-leg skips at fixture time | 1.25s |
| Sybil doc fences | not in the default run (`testpaths = ["tests"]`); `ci.sh` runs them as their own command, 1.7s |
| `--import-mode=importlib`, `-p no:cacheprovider`, `-p no:anyio`, `-p no:langsmith` | ≤0.1s each |
| **interpreter shutdown after `tests/base`** | **~4.5s** |

The shutdown cost is a `src/` finding. After `tests/base`, 1.86 million
objects stay alive with no storage or engine open: 350 `MetaData`, 7,333
`Table`, 347 SQLite dialects. The referrer chain ends at
`_BULK_STATEMENTS` in `dialects.py`, a module-level cache keyed by the
`Table` object. SQLite's profile is `bulk_insert="driver"`, so it fills on
every mount, and dead mounts never leave; the comment says it is bounded
by live mounts, and it is bounded by mounts ever created. Clearing it per
test took tracked objects from 1.86M to 240k, gen-2 GC from 2.0s to 1.0s,
and shutdown from 2.4s to 0.3s. This is a production leak in a
long-running process that mounts and unmounts.

What a base test does: `VirtualFileSystem()` with no storage builds an
`InMemoryStorage`, which is a real `DatabaseStorage` on
`sqlite+aiosqlite:///:memory:`. Construct is 9.8 ms (`build_vfs_tables`
~8 ms rebuilt per instance, plus `RendererRegistry.bundled()` ~5 ms,
which calls `importlib.metadata.version()` four times, four dist-info
reads) and first touch ~26 ms. `add_mount` is a real gated `mkdir`, so even
a doubles-only dispatch test pays the root's first touch: ~36 ms × 636
base tests ≈ 23s of the 24s `tests/base` costs.

| Strategy | Measured | Stops proving | Recommendation |
|---|---|---|---|
| `-m "not (postgres or mariadb or mssql or oracle)"` as the default local expression | 1.25s | nothing locally | Do |
| `--ignore=tests/ranking/test_harness.py` in the default local run (harness as its own command, like docs) | ~1.7s of collection, plus its tests | nothing, if the harness command runs in CI | Do, if the `slow` tier is adopted anyway |
| `src/`: cache `build_vfs_tables` and a process-level bundled renderer registry (cached `metadata.version`) | `tests/base` 30.8 to 21.0s wall | nothing | Do (same lever as 4.4 B) |
| `src/`: key `_BULK_STATEMENTS` by table identity or bound to storage lifetime | ~3s on base (GC and shutdown); more across the suite; fixes a leak | nothing | **Do** |
| Module-scoped, module-loop immutable worlds for `test_mount_placement_is_invisible_to_patterns` and its grep twin | glob file 7.5 to 5.1s; ~1s on grep | nothing: those tests only read | Do; close in the fixture, since the autouse disposer does not see module fixtures |
| A stand-in storage for all of `test_dispatch.py` | 101 of 211 fail | the root's real semantics are what those tests pin | Reject as a blanket |
| xdist on this slice alone | 47.9s to 20.0s at `-n 8` | nothing | Do |

## 5. The `src/` findings

Four of the five investigations arrived at changes to `src/`, which the
test suite surfaced but which are product facts:

1. **Fresh-mount provisioning skips `checkfirst` and an existing mount
   skips `create_all`.** One `has_table(meta)` inspect decides. Saves 40
   to 68 statements per mount, ≈ 12s per serial suite run, and makes
   first touch on a production Postgres mount cheaper by the same count.
   The behaviour change: a partially provisioned mount on an engine
   without transactional DDL no longer gets its missing tables created
   silently; it is verified and refused like a schema-version mismatch.
   That needs an ADR, and the `db_test` legs before landing.
2. **`build_vfs_tables` cached per (schema, native_embedding).** The
   MetaData is immutable after build and has no engine binding. Saves
   ~8 ms per storage construction everywhere, and makes the
   `_BULK_STATEMENTS` cache dedupe naturally.
3. **`_BULK_STATEMENTS` is a leak.** Key it by table identity, or bound it
   to the storage's lifetime. Production-relevant for any process that
   mounts and unmounts.
4. **`glean` fetches entry rows for all 1,000 fusion candidates per query
   and always renders a preview.** On scifact that is ~318k SQLAlchemy
   rows and ~296k ULID decodes over 300 queries, about 5s, plus ~1s of
   preview that never affects order or score. A lazy preview or a
   `columns`-driven toggle, and a cheaper candidate-to-entry join, are
   product work with their own spec.
5. **Bulk insert compiles once per page.** SQLAlchemy's `insertmanyvalues`
   executemany path would compile once per page shape. Likely halves the
   10k write and every bulk ingest. Product work, not a test change.

## 6. Where the arithmetic lands

Serial, at the quiet 2026-10-08 baseline, applying the "same proof, less
work" levers plus the two tier decisions (BEIR and 10k under `slow`):

| Slice | Today | After | Levers |
|---|---|---|---|
| ranking harness | 63s | ~33s | A, A2, B |
| conformance | 50s | ~37s | A, B (both classes kept) |
| rights + grants | 38s | ~22s | S2, S3, S4, S5 |
| rest of database | 61s | ~36s | A, B, C, D, E′ |
| long tail + overhead | 47s | ~30s | src caches, leak fix, module worlds, marker deselect |
| **serial total** | **253s** | **~160s** | |

With the conformance contract run once (4.2 F): ~140s serial. Section 3
measured xdist at 2.5× on the whole suite and 2.8 to 4.1× on a subtree,
so a serial 140 to 160s lands at **roughly 45 to 60s wall** under ten
workers. That is the minute, with no margin at the top of the range. The
two tier decisions (BEIR and the 10k pins under `slow`) and the
conformance-once decision are each worth about 10s of that wall, so the
margin is theirs to grant. Serial alone cannot reach the minute: the
floor of genuine statement work (the arrange writes in conformance, the
~900 small database tests) is above 60s by itself, and xdist alone
cannot either: it caps near 100s today.

The order that buys the most for the least risk:

1. `pytest-xdist` as a dev dependency, `-n auto` in the default local
   command, with the two worker-safety fixes from section 3 and a
   per-corpus `xdist_group` on the harness.
2. The `slow` tier made real: `-m "not slow"` in the default run, BEIR and
   the N=10k pins tagged, `scripts/ci.sh` and the workflow running the
   tier on the 3.13 leg.
3. The template databases (conformance 4.2 A, helpers 4.4 A), the
   module-scoped corpora (4.1 A, A2), the oracle memo (4.3 S4), the
   module worlds (4.5), the sleep-double rewrite (4.4 C) and zero backoff
   (4.4 D). All test-side, all "nothing stops being proven".
4. The `src/` changes in section 5, items 2 and 3 first (no behaviour
   change), item 1 behind an ADR.
5. The two domain decisions, each its own call: run the conformance
   contract once (4.2 F), and fewer distinct rights worlds (4.3 S2, S3).

## 7. Not measured

- A quiet-machine run of any slice variant; every slice number was taken
  under load and paired. The suite-level xdist runs were repeated quiet
  (section 3).
- Why per-test CPU inflates 2× under ten workers: performance versus
  efficiency cores, clock, cache, or kernel wake-ups on the aiosqlite
  hand-off. A `py-spy` of one worker at `-n 1` against `-n 10`, or the
  same probe on a Linux box, would separate them. It changes which fix
  helps xdist most, not whether the statement-count work is needed.
- The coverage leg under xdist (`pytest-cov` supports it; the greenlet
  tracer's cost per worker was not measured).
- The real-engine legs under any of the `src/` changes.
- Variance beyond two paired rounds per strategy.
