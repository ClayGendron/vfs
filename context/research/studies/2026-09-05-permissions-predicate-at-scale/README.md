# Study: the row-grant predicate at scale — what enforcement costs on each engine, and which shape wins

Companion to the memo `../../2026-09-05-permissions-predicate-at-scale.md`
(study S1 of the principals-and-permissions research programme,
`../../2026-09-05-principals-and-permissions-research-plan.md` §4 Phase 2).

The question: for ADR 021's additive prefix-grant model (grant rows
`(principal_id, path_prefix, level)`, coverage
`path = prefix OR path LIKE prefix || '/%'`, compiled into the query at
one chokepoint), what does the read predicate cost on SQLite, Postgres,
MariaDB, SQL Server and Oracle at 100k and 1M entry rows, which
predicate shape wins, what the write point check and a materialised
visibility table cost, how groups and the multiplayer subject-set
predicate behave, and whether any shape breaks a bind or `IN`-list
budget at a 10k batch.

## What is here

| file | what it does |
|---|---|
| `corpus.py` | The deterministic synthetic corpus (one seed, identical on every engine): ~200 top-level directories with Zipf-skewed row counts, paths 2–8 segments deep, 10,000 principals with Zipf-skewed ownership assigned per depth-2 directory, ~5 direct grants per principal at mixed depths, five "everyone" grants on top-level directories, 300 groups with Zipf-skewed membership plus a `g_all` group, 3,000 grants that name a group. Also the app-side helpers the memo measures: `minimise` (drop covered prefixes), `intersect_prefixes` (the subject-set intersection), `ancestors` and `resolve_level` (the write point check). |
| `common.py` | `Bench`: one async SQLAlchemy engine per study URL, a fresh `vfs_s1_<hex>` namespace holding a **lean copy of the vfs entry table** (`id`, `path`, `owner_id`, `kind`, `ext`, `size_bytes`, `deleted_at`; unique index on `path`, index on `owner_id`, index on `(ext, kind)` — the columns the predicate reads, with vfs's index shape and key types: `COLLATE "C"` on Postgres, `Latin1_General_100_BIN2_UTF8` on SQL Server, `VARBINARY` on MariaDB), three grant tables (`grant` flat, `grantg` naming groups, `grantgx` the expansion), `member`, and a `vis` sample. Loads through Core's executemany pages, builds indexes after the load, refreshes statistics, exposes `timeit` (warm, median of n) and `plan` (EXPLAIN ANALYZE / plan-cache XML by marker / `DBMS_XPLAN` / `EXPLAIN` / `EXPLAIN QUERY PLAN`, compressed to an operator skeleton). Drops every table on exit and drops any `vfs_s1_%` leftovers from a crashed run on entry. |
| `probe.py` | The measurements, in the brief's order: (1) the read predicate under list / glob / grep filters and the ranked join-back (`IN` chunked by `membership_budget`, and a `VALUES` join) in five shapes — none, correlated `EXISTS`, literal prefixes as `LIKE` arms, literal prefixes as range arms, materialised `EXISTS`; (2) the write point check per path, per 10k batch as chunked `IN`, and as one fetch of the caller's grants resolved in app; (3) the materialised table's exhaustive size (computed from the corpus) and the cost of inserting one grant's rows; (4) groups as flat expansion, membership subquery, and literal group ids; (5) the subject set for n = 2, 5, 20 as AND of `EXISTS`, grouped `HAVING COUNT(DISTINCT) = n`, and the app-side prefix intersection shipped as literals; (6) the bind-budget table. Writes `runs/<engine>-<rows>.md` and `.json`. |
| `report.py` | Assembles `results.md` from `runs/*.md` (patching the join-back bind counts of runs made before that column was corrected) and prints the memo's cross-engine tables. |
| `results.md` | The raw per-engine tables, assembled from `runs/`. |
| `runs/` | One `.md` and one `.json` per engine and size, as measured on 2026-09-05. |

Key typing matters on SQL Server: principal-id and path binds are cast
through the column's UTF-8 collation and length (`Bench.sbind`,
`Bench.pbind`), which is what vfs ships since spec 145. Without the
cast the nvarchar bind forces a scan of the grant table per outer row
and the correlated `EXISTS` costs ~10 ms per row (observed in the
first smoke run; kept out of the results because vfs never issues that
form).

## Rerun

Containers up (`docker/compose.test.yml`), env exported
(`VFS_TEST_POSTGRES_URL`, `VFS_TEST_MSSQL_URL`, `VFS_TEST_ORACLE_URL`,
`VFS_TEST_MARIADB_URL`; SQLite needs nothing — it writes
`vfs_s1_corpus.sqlite` beside the scripts and removes it). From the
repo root or this directory:

    cd context/research/studies/2026-09-05-permissions-predicate-at-scale
    uv run --no-sync python probe.py --engine sqlite   --files 75000            # 12 s
    uv run --no-sync python probe.py --engine postgres --files 75000 --reps 3   # 4.6 min
    uv run --no-sync python probe.py --engine mariadb  --files 75000 --reps 3   # 5.4 min
    uv run --no-sync python probe.py --engine mssql    --files 75000 --reps 3   # 11 min, Rosetta
    uv run --no-sync python probe.py --engine oracle   --files 75000 --reps 3   # 16 min, Rosetta
    uv run --no-sync python probe.py --engine sqlite   --files 800000 --reps 3  # 1.2 min
    uv run --no-sync python probe.py --engine postgres --files 800000 --reps 3  # 17 min
    uv run --no-sync python report.py                                           # results.md + memo tables

Most of the wall clock is the membership-subquery groups cell and the
grouped `HAVING` subject-set cell, the two shapes the memo disqualifies;
a statement that exceeds 60 s is run once and marked `capped`.

`--files N` is the file-row count; directory rows are added on top
(about a third as many), so `--files 75000` is ~100k entry rows and
`--files 800000` is ~1M. `--no-plans` skips the plan capture. Every
run mints its own namespace and drops it; a run killed mid-way leaves
`vfs_s1_<hex>_*` tables that the next run on that engine drops first.
