# The row-grant predicate at scale: what enforcement costs on each engine, and which shape wins

- **Status:** research memo (study S1 of the principals-and-permissions programme)
- **Date:** 2026-09-05
- **Owner:** Clay Gendron
- **Question:** ADR 021 proposes additive grant rows `(principal_id, path_prefix, level)`, prefix coverage `path = prefix OR path LIKE prefix || '/%'`, and the predicate compiled into every query at one chokepoint. What does that predicate cost at 100k and 1M entry rows on each production engine, which shape of the predicate wins, what do the write point check, a materialised visibility table, groups, and the multiplayer subject-set predicate cost, and does any shape break a bind or `IN`-list budget at a 10k batch? Numbers decide ADR 021 D2 (prefixes as the grant coordinate) and D3 (app-level compilation), the groups fork, and the multiplayer predicate.
- **Method:** executed experiments, rerunnable from `studies/2026-09-05-permissions-predicate-at-scale/` (`README.md` there). One deterministic synthetic corpus (seeded, identical on every engine): ~200 top-level directories with Zipf-skewed sizes (the largest holds 14% of rows), paths 2 to 8 segments deep, 10,000 principals with Zipf-skewed ownership, 9.7 grant rows per principal (about 5 direct grants at mixed depths plus five "everyone" grants on top-level directories), 300 groups with skewed membership, 3,000 grants naming a group. A lean copy of the vfs entry table (the columns the predicate reads, vfs's index shape and key types) in a fresh `vfs_s1_<hex>` namespace, dropped on exit. 111,569 entry rows on SQLite, Postgres 17, MariaDB 11.8, SQL Server 2025 and Oracle 23ai (26ai Free); 994,923 rows on SQLite and Postgres. Medians over 3 to 5 warm runs; plans from `EXPLAIN ANALYZE`, the SQL Server plan cache, `DBMS_XPLAN`, `EXPLAIN`. SQL Server and Oracle run amd64-emulated under Rosetta, so their absolute times are inflated; read their ratios and plan shapes.
- **Sources:** the study directory above (`corpus.py`, `common.py`, `probe.py`, `report.py`, `results.md`, `runs/*.json`); ADR 021; `src/vfs/storage/backends/database/dialects.py` (`membership_budget`, `in_list_budget`); spec 145 (the SQL Server bind-typing rule the study had to reproduce). No reference repos were consulted; this is measurement, not prior art.

## Bottom line

1. **The prefix-grant model is cheap enough everywhere, and the winning shape is not the one ADR 021 sketches.** ADR 021 leans on a correlated `EXISTS` over the grants table. That shape works on every engine but it is the slowest of the three read shapes measured. Resolving the caller's covering prefixes first (one indexed read of about 10 rows) and shipping them as literal `LIKE` arms is 3 to 18 times faster on Postgres (5 to 14x at 1M rows) and never slower elsewhere, because the predicate becomes a plain filter with no per-row subquery.
2. **The correlated `EXISTS` costs one grant-index probe per candidate row.** On Postgres a grep-shaped pass over 7,072 rows goes from 10 ms to 94 ms (9x); the literal form stays at 5 ms. The heavy owner pays the same. At 1M rows the ratios hold.
3. **The ranked join-back is bounded and fast in every shape.** 1,000 candidate ids filtered by the predicate cost 3 to 20 ms on every engine, chunked by `membership_budget` (1,000 on Oracle, 2,000 on SQL Server, ~32k elsewhere). `IN` and `VALUES` are within noise of each other except on SQL Server, where `VALUES` is what vfs already ships for other reasons.
4. **The write point check should not query per path.** One path costs 0.2 to 3.5 ms as an `IN (ancestors)` lookup; a 10k batch as chunked `IN` is 50 to 145 ms; fetching the caller's grants once (about 10 rows, 0.2 to 2 ms) and resolving the longest prefix in app code is 11 ms for 10k paths and issues one statement regardless of batch size.
5. **An exhaustive materialised `visible(principal, entry)` table is disqualified by the everyone grants.** Five top-level grants to 10,000 principals cost 205 million rows at 111k entries and 1.95 billion rows at 995k, 1,850x the entry table; one new everyone grant on the largest directory is 155 million to 1.5 billion inserted rows. Direct grants alone are 12 to 17x the entry table. And it does not read faster than the literal form.
6. **Groups: resolve the caller's groups first and ship them as literals.** A membership subquery inside the correlated `EXISTS` is catastrophic on Postgres (35 s for the grep pass, 4.3 s for a 1,000-id join-back) and MariaDB (188 s, 28 s); the same rights as a literal `principal_id IN (:p, :g1, ...)` cost 13 to 110 ms. Expanding group grants into flat rows ahead of time is slightly faster still but multiplies the grant table (2.4x here).
7. **Multiplayer: the app-side prefix intersection is the only shape that stays flat as the set grows.** For a set of 20 principals on Postgres, AND of 20 `EXISTS` costs 314 ms, the grouped `HAVING COUNT(DISTINCT) = n` 130 ms, and the pre-resolved intersection 22 ms, the same as a single principal. The intersection shrinks the prefix set (20 members share 5 prefixes), so binds fall with n rather than rise.
8. **No shape breaks a budget, but two need a rule.** The literal forms bind 2 to 3 slots per prefix, so they are bounded by the caller's grant count, not the batch; vfs needs a declared per-principal prefix cap (or the `EXISTS` fallback past it). The grouped `HAVING` form repeats the candidate list three times and must chunk at a third of the budget. Everything else is one bind plus the chunked candidate list.

**In one line:** compile the caller's rights to a bounded literal predicate in app code (prefix set, group set, subject-set intersection), keep `EXISTS` as the fallback for a caller with more prefixes than the budget allows, never materialise, and resolve write levels from the caller's grant rows in app code.

## Findings

All tables: medians in ms over warm runs, the whole result fetched to the client. Columns are engine and entry-row count. `†` marks a cell that exceeded the 60 s cap and was run once. `(2s)` means the batch needed two statements under that engine's `membership_budget`. The full per-engine tables, plan skeletons and budget tables are in `studies/2026-09-05-permissions-predicate-at-scale/results.md`.

The corpus at 111,569 rows: 75,000 files and 36,569 directories; `/t000` (the largest top-level directory, an everyone grant) holds 15,481 rows. The typical principal owns 398 rows, holds 8 grant rows (8 minimal prefixes) and sees 20,471 rows by grant. The heavy principal `p00000` owns 10,961 rows. At 994,923 rows the same shapes scale by about 9x.

### 1. The read predicate: `EXISTS` versus resolved literal prefixes

Five predicate shapes on three query filters. `none` is the filter alone, the floor. `exists` is ADR 021's correlated `EXISTS` over the grants table. `literal_like` resolves the caller's minimal prefix set first (one indexed read, 8 rows) and ships `path = :q OR path LIKE :q/%` arms. `literal_range` is the same with `path = :q OR (path >= :q/ AND path < :q0)` arms. `materialised` is an `EXISTS` against a precomputed `visible(principal_id, entry_id)` table. The list filter is one directory's 2,037 children (20,704 at 1M); glob is `ext = 'md'` under `/t000` (3,782 and 40,003 rows); grep is a `size_bytes` band over the whole corpus (7,072 and 73,675 candidate rows, of which the predicate keeps 1,588 and 16,066).

| shape | sqlite 111k | postgres 111k | mariadb 111k | mssql 111k | oracle 111k | sqlite 994k | postgres 994k |
|---|---|---|---|---|---|---|---|
| list · none | 2.0 | 4.0 | 18 | 11 | 15 | 19 | 31 |
| list · exists | 2.8 | 16 | 22 | 18 | 16 | 28 | 155 |
| list · literal_like | 2.2 | 4.7 | 20 | 12 | 16 | 28 | 33 |
| list · literal_range | 2.2 | 5.1 | 21 | 12 | 16 | 29 | 32 |
| list · materialised | 2.7 | 8.3 | 28 | 15 | 19 | 33 | 129 |
| glob · none | 5.3 | 5.5 | 26 | 31 | 38 | 94 | 46 |
| glob · exists | 7.2 | 19 | 31 | 46 | 40 | 96 | 234 |
| glob · literal_like | 5.9 | 4.8 | 28 | 33 | 39 | 80 | 38 |
| glob · literal_range | 5.8 | 4.5 | 28 | 34 | 36 | 80 | 75 |
| glob · materialised | 6.9 | 9.0 | 35 | 40 | 41 | 104 | 103 |
| grep · none | 8.6 | 10 | 29 | 20 | 47 | 81 | 93 |
| grep · exists | 16 | 94 | 37 | 53 | 24 | 160 | 519 |
| grep · literal_like | 8.6 | 5.1 | 23 | 28 | 19 | 124 | 36 |
| grep · literal_range | 8.5 | 5.2 | 24 | 25 | 18 | 122 | 35 |
| grep · materialised | 8.6 | 71 | 28 | 28 | 17 | 87 | 239 |
| heavy list · none | 1.9 | 3.8 | 18 | 11 | 15 | 19 | 30 |
| heavy list · exists | 2.6 | 18 | 21 | 19 | 17 | 27 | 170 |
| heavy list · materialised | 2.7 | 8.3 | 27 | 16 | 17 | 28 | 126 |
| heavy grep · none | 8.3 | 11 | 28 | 17 | 46 | 80 | 105 |
| heavy grep · exists | 21 | 100 | 43 | 59 | 29 | 233 | 578 |
| heavy grep · materialised | 8.7 | 25 | 28 | 27 | 22 | 88 | 247 |

What the plans say. On Postgres the `EXISTS` is a SubPlan executed once per candidate row: `Index Only Scan on grant_pp` with `loops=73657` on the 1M grep pass, 362 ms of the 519 ms. The literal form adds no node at all: it is a filter on the rows the index already produced (2.4 ms of EXPLAIN time versus 10.5 ms for the `EXISTS` on the glob filter at 100k). SQLite and Oracle plan the correlated subquery as a cheap covering-index probe and pay 1.3 to 2x; MariaDB and SQL Server pay 1.3 to 2.7x. The two literal forms are within noise of each other everywhere, so the `LIKE` form (2 binds per prefix, and the escaping vfs already owns) is the one to ship. The materialised table never beats the literal form and on Postgres at 1M costs 239 ms on grep against 36 ms, because its `EXISTS` is one unique-index probe per row exactly like the grant `EXISTS`.

### 2. The ranked join-back

A candidate set of 256, 1,000 and 3,000 file ids (the shape `glean` produces), filtered by the predicate, chunked by `membership_budget` (32,668 on SQLite, Postgres and MariaDB; 2,000 on SQL Server; 1,000 on Oracle), as an `IN` list and as a `VALUES` derived table joined to the entry table. K = 256 rows are omitted here; they are 1 to 10 ms everywhere.

| shape | sqlite 111k | postgres 111k | mariadb 111k | mssql 111k | oracle 111k | sqlite 994k | postgres 994k |
|---|---|---|---|---|---|---|---|
| K=1000 IN · none | 2.5 | 4.5 | 6.2 | 11 | 16 | 2.8 | 5.3 |
| K=1000 IN · exists | 3.7 | 9.3 | 7.2 | 17 | 9.3 | 4.1 | 9.6 |
| K=1000 IN · literal_like | 3.1 | 5.1 | 5.1 | 13 | 13 | 3.0 | 5.4 |
| K=1000 IN · materialised | 2.6 | 8.5 | 5.4 | 15 | 8.4 | 3.2 | 48 |
| K=1000 VALUES · none | 2.4 | 11 | 6.1 | 39 | 11 | 2.8 | 5.6 |
| K=1000 VALUES · exists | 3.7 | 11 | 7.1 | 42 | 10 | 4.0 | 11 |
| K=1000 VALUES · literal_like | 3.3 | 8.6 | 4.8 | 20 | 15 | 3.5 | 6.8 |
| K=1000 VALUES · materialised | 2.8 | 6.2 | 6.2 | 24 | 10 | 3.2 | 8.4 |
| K=3000 IN · none | 8.2 | 12 | 17 | 29 (2s) | 45 (3s) | 9.4 | 14 |
| K=3000 IN · exists | 11 | 30 | 19 | 49 (2s) | 23 (3s) | 12 | 33 |
| K=3000 IN · literal_like | 8.8 | 14 | 13 | 36 (2s) | 49 (3s) | 9.9 | 14 |
| K=3000 IN · materialised | 8.1 | 15 | 15 | 42 (2s) | 22 (3s) | 9.9 | 53 |
| K=3000 VALUES · none | 7.7 | 18 | 17 | 53 (2s) | 55 (3s) | 9.4 | 48 |
| K=3000 VALUES · exists | 11 | 34 | 18 | 61 (2s) | 35 (3s) | 13 | 35 |
| K=3000 VALUES · literal_like | 10 | 16 | 13 | 44 (2s) | 51 (3s) | 11 | 16 |
| K=3000 VALUES · materialised | 8.1 | 16 | 14 | 57 (2s) | 28 (3s) | 9.5 | 18 |

Every cell is bounded and small. The predicate adds 1 to 5 ms per 1,000 candidates over the unfiltered join-back in its literal form and 2 to 18 ms as `EXISTS`. `IN` and `VALUES` are within noise on SQLite, Postgres, MariaDB and Oracle. On SQL Server the `VALUES` join was planned as a merge join over a clustered index scan (`abort=TimeOut`) and costs 3.6x the `IN` form for a read that takes no lock; spec 145 chose `VALUES` for the locking membership reads, where the seek matters more than this, so the profile field stands but the read-only join-back could keep `IN`. On Oracle the first execution of each distinct statement text pays a hard parse of 0.1 to 2 s on the emulated box (`first` in the raw tables); warm runs are what the cells show.

### 3. The write point check

Resolving the caller's level for one path by longest matching prefix. Three forms: one query per path (`principal_id = :p AND path_prefix IN (path and its ancestors)`, at most 10 binds); a 10k-path batch as the distinct ancestors (18,526 prefixes) chunked by `membership_budget`; and one read of the caller's grant rows (8 rows) with the longest-prefix walk done in Python for all 10k paths.

| shape | sqlite 111k | postgres 111k | mariadb 111k | mssql 111k | oracle 111k | sqlite 994k | postgres 994k |
|---|---|---|---|---|---|---|---|
| one path, ms | 0.18 | 0.63 | 0.76 | 3.46 | 0.67 | 0.17 | 0.61 |
| 10k paths chunked IN, ms (stmts) | 49 (1) | 85 (1) | 111 (1) | 145 (10) | 86 (19) | 49 (1) | 65 (1) |
| grants once + app, ms | 0.2 + 11 | 1.5 + 11 | 1.4 + 11 | 1.8 + 11 | 2.0 + 11 | 0.2 + 11 | 1.0 + 11 |

The third form is one statement of one bind regardless of batch size and 11 ms of Python for 10k paths (a dictionary lookup per ancestor). The chunked form needs 10 statements on SQL Server and 19 on Oracle for the same answer. The per-path form is fine for a single write (0.2 to 3.5 ms) but is 10,000 round trips for the batch contract.

### 4. The materialised visibility table

Row counts are computed exactly from the corpus (sum over grant rows of the covered subtree size). The read cost is in the tables above (`materialised` column). Maintenance is measured: inserting one grant's rows for one principal with `INSERT ... SELECT` over the covered subtree.

| shape | sqlite 111k | postgres 111k | mariadb 111k | mssql 111k | oracle 111k | sqlite 994k | postgres 994k |
|---|---|---|---|---|---|---|---|
| exhaustive rows | 206,669,891 | 206,669,891 | 206,669,891 | 206,669,891 | 206,669,891 | 1,959,014,205 | 1,959,014,205 |
| direct grants only | 1,868,697 | 1,868,697 | 1,868,697 | 1,868,697 | 1,868,697 | 11,696,281 | 11,696,281 |
| wide grant, one principal, ms (rows) | 9 (15,481) | 29 (15,481) | 21 (15,481) | 179 (15,481) | 14 (15,481) | 93 (149,339) | 291 (149,339) |

Five everyone grants on top-level directories to 10,000 principals are 204.8 million of the 206.7 million rows at 111k entries and 1.95 billion at 995k. A new everyone grant on `/t000` alone is 15,481 x 10,000 = 155 million rows (1.49 billion at 1M), at the measured per-principal insert rate 90 to 1,800 s on the engines here. Direct grants only are 12 to 17x the entry table. The table is disqualified on size and write amplification before its read numbers are weighed, and its read numbers do not save it.

### 5. Groups

Three encodings of the same rights for a principal in 2 groups. `flat expanded` pre-expands every group grant into per-principal rows (232,993 grant rows instead of 49,777 + 23,415 memberships) and uses the plain `EXISTS`. `membership subquery` keeps the groups form and writes `g.principal_id = :p OR g.principal_id IN (SELECT group_id FROM member WHERE principal_id = :p)` inside the `EXISTS`. `groups literal` resolves the caller's group ids first and writes `g.principal_id IN (:p, :g1, :g2, :g_all)`.

| shape | sqlite 111k | postgres 111k | mariadb 111k | mssql 111k | oracle 111k | sqlite 994k | postgres 994k |
|---|---|---|---|---|---|---|---|
| glob · flat expanded (exists over grantgx) | 7.5 | 14 | 31 | 46 | 37 | 96 | 192 |
| glob · membership subquery | 17 | 15905 | 32 | 82927 † | 1625 | 287 | 196485 † |
| glob · groups literal | 12 | 31 | 34 | 130 | 41 | 235 | 358 |
| grep · flat expanded (exists over grantgx) | 24 | 43 | 47 | 65 | 24 | 349 | 513 |
| grep · membership subquery | 31 | 35476 | 188437 † | 157749 † | 37536 | 500 | 373563 † |
| grep · groups literal | 28 | 109 | 58 | 223 | 39 | 448 | 873 |
| back1000 · flat expanded (exists over grantgx) | 5.0 | 8.8 | 8.7 | 24 | 13 | 7.7 | 9.5 |
| back1000 · membership subquery | 6.0 | 4305 | 27655 | 22372 | 5488 | 9.2 | 4244 |
| back1000 · groups literal | 5.8 | 13 | 10 | 48 | 15 | 8.4 | 19 |

The membership subquery is the one shape in this study that is catastrophic: on Postgres the plan is `Seq Scan on grantg` with `loops=73657`, a full scan of the grant table per candidate row, 358 s at 1M; MariaDB, SQL Server and Oracle degrade the same way (SQLite alone plans it well with a bloom filter). The literal form costs 1.2 to 2.8x the flat expansion and needs 4 binds; the flat expansion costs a 2.4x grant table and a write of every member's rows on every group change.

### 6. The subject set (multiplayer)

A right held by every principal in a set of n = 2, 5 and 20 principals (non-owners chosen at random; each holds 8 to 12 grant rows including the 5 everyone grants). Three forms. (a) AND of n `owner OR EXISTS` predicates, n binds. (b) The grouped form: `e.id IN (SELECT eid FROM (grants join UNION owner rows) GROUP BY eid HAVING COUNT(DISTINCT principal_id) = n)`, scoped by the same filter, n + 1 binds plus the filter's binds repeated per copy. (c) App-side: intersect the members' minimal prefix sets (the deeper of each nested pair), plus one owner disjunct per member with the intersection of the other members' sets, shipped as `LIKE` arms; 57 binds at n = 2, 68 at n = 5, 233 at n = 20 on this corpus. The glob rows are omitted here (same ranking; see `results.md`).

| shape | sqlite 111k | postgres 111k | mariadb 111k | mssql 111k | oracle 111k | sqlite 994k | postgres 994k |
|---|---|---|---|---|---|---|---|
| n=2 grep · set_and_exists | 24 | 97 | 47 | 73 | 25 | 206 | 435 |
| n=2 grep · set_having | 39 | 23 | 60 | 98 | 38 | 396 | 174 |
| n=2 grep · set_app_prefixes | 8.5 | 5.6 | 24 | 25 | 25 | 117 | 40 |
| n=2 back1000 · set_and_exists | 5.1 | 9.8 | 9.8 | 25 | 8.3 | 4.9 | 9.7 |
| n=2 back1000 · set_having | 8.9 | 12 | 13 | 473 (2s) | 13 | 9.4 | 11 |
| n=2 back1000 · set_app_prefixes | 3.0 | 5.8 | 6.8 | 17 | 21 | 3.2 | 5.4 |
| n=5 grep · set_and_exists | 23 | 130 | 47 | 70 | 31 | 288 | 596 |
| n=5 grep · set_having | 88 | 36 | 87 | 199 | 71 | 813 | 337 |
| n=5 grep · set_app_prefixes | 8.6 | 16 | 24 | 25 | 34 | 118 | 40 |
| n=5 back1000 · set_and_exists | 4.0 | 11 | 9.6 | 24 | 8.0 | 5.8 | 10 |
| n=5 back1000 · set_having | 14 | 15 | 16 | 1183 (2s) | 22 | 15 | 12 |
| n=5 back1000 · set_app_prefixes | 3.2 | 5.7 | 5.1 | 16 | 30 | 3.3 | 5.8 |
| n=20 grep · set_and_exists | 31 | 314 | 76 | 146 | 42 | 324 | 1264 |
| n=20 grep · set_having | 276 | 130 | 583 | 733 | 205 | 2989 | 1555 |
| n=20 grep · set_app_prefixes | 9.3 | 21 | 31 | 15 | 33 | 117 | 48 |
| n=20 back1000 · set_and_exists | 6.0 | 19 | 17 | 35 | 10 | 6.8 | 17 |
| n=20 back1000 · set_having | 43 | 25 | 37 | 1659 (2s) | 45 | 45 | 25 |
| n=20 back1000 · set_app_prefixes | 4.0 | 7.7 | 6.4 | 21 | 7.9 | 4.7 | 7.2 |

Form (c) costs the same at n = 20 as at n = 2 on every engine, and the same as a single principal's literal predicate, because the intersection of 20 prefix sets is 5 shared prefixes and the owner disjuncts are tiny. Form (a) grows linearly with n (Postgres grep: 97, 130, 314 ms at 100k; 1,264 ms at n = 20 and 1M). Form (b) is unbounded in the worst case: on Oracle the glob variant took 98 s at n = 2 and 499 s at n = 20 (a hash-unique over the whole grants-join before the group by); on SQL Server the join-back variant needs two statements because the candidate list is repeated three times under the 2,100-bind cap and costs 1.7 s at n = 20.

### 7. Budgets at a 10k batch

Binds per statement as a function of batch size K, set size n, and the caller's grant count G (17 at most in this corpus), with the tightest engine caps: Oracle's 1,000-element `IN` list and SQL Server's 2,100 binds.

| shape | binds per statement | bounded by | verdict |
|---|---|---|---|
| read: `owner OR EXISTS` | 1 | nothing | ok |
| read: literal prefixes, `LIKE` | 1 + 2G | the caller's grant count | ok while 1 + 2G is under `membership_budget`; needs a declared cap or the `EXISTS` fallback past it |
| read: literal prefixes, range | 1 + 3G | same | same, one bind more per prefix for no gain |
| join-back, `IN` or `VALUES`, any predicate | chunk + predicate binds | `membership_budget`, chunked | ok: 10k candidates are 1 statement on SQLite/Postgres/MariaDB, 5 on SQL Server, 10 on Oracle |
| write check, per path | 1 + depth (at most 10) | path depth | ok, but 10k round trips for a batch |
| write check, 10k batch as chunked `IN` | 1 + chunk | chunked | ok, 1 to 19 statements |
| write check, grants read once | 1 | nothing | ok, and the only form that is one statement per batch |
| groups: membership subquery | 1 | nothing | bounded, but disqualified on cost |
| groups: literal group ids | 1 + groups(p) | the caller's group count | ok while under the budget (3 to 4 here) |
| set (a): AND of n `EXISTS` | n | set size | ok |
| set (b): grouped `HAVING` | n + 1 + 3 x chunk | must chunk the candidate list at a third of the budget (682 on SQL Server) | bounded only with a shape-specific chunk rule; disqualified on Oracle's cost |
| set (c): app-side intersection | 2 x shared prefixes + sum over members of (1 + 2 x prefixes shared by the others) | (n + 1) x 2G worst case, 233 measured at n = 20 | ok; shrinks with n in practice; needs the same cap-or-fallback rule as the single-principal literal |

No shape grows with batch size once the candidate list is chunked. Two shapes grow with the caller's rights (the literal forms) and one with the set size times the filter (the grouped form).

## What this decides

| finding | decision it feeds | what the numbers say |
|---|---|---|
| The prefix predicate holds at 1M rows on every engine, and the literal-prefix form is the cheapest | ADR 021 D2 (grants attach to path prefixes) | **Ratify.** The indexed prefix range scan holds at 10k-row batches and 1M rows on every engine; the recorded fallback (`traversal_ids`) is not needed. Add one rule: the prefix set a caller holds is resolved once per request and minimised (drop prefixes covered by a shallower one). |
| A per-row `EXISTS` costs one index probe per candidate row; a literal predicate costs nothing per row | ADR 021 D3 (app-level compilation at one chokepoint) | **Ratify, and make the chokepoint do more.** The chokepoint should resolve the caller's rights to a bounded literal predicate (prefixes, groups, set intersection) and only fall back to the correlated `EXISTS` when the literal form would exceed the dialect's bind budget. That fallback threshold is `membership_budget` divided by binds per prefix (2 for `LIKE`, 3 for the range form). |
| Membership subquery inside the predicate is catastrophic on Postgres and MariaDB; literal group ids are fine | ADR 021's open groups fork | **Groups can ship in v1 at no read cost**, provided the caller's group ids are resolved at session start (or per request) and shipped as a literal list, never as a subquery. The flat-expansion alternative buys 10 to 30% on reads and costs a 2.4x grant table plus the write amplification of every group change. Groups-as-indirection with literal resolution is the recorded choice. |
| One statement of about 10 rows resolves the write level for any batch | the write point check in spec 058 | The point check reads the caller's grants once per request and resolves the longest prefix in app code; 10k paths cost 11 ms of Python and one query. No per-path query, no chunked `IN` of ancestors. |
| Exhaustive materialisation is 1,850x the entry table and a single wide grant is a 10^8 to 10^9 row write | the Zanzibar-shaped alternative | **Rejected.** Not as a cache either: the materialised `EXISTS` never beat the literal form on reads. |
| The app-side intersection is flat in n; the SQL forms grow linearly (AND) or worse (HAVING) | the multiplayer predicate (plan §1.1, Q13) | The session's subject set compiles to one intersected prefix set plus an owner term per member, computed in app code from n grant reads (about 10 rows each). Binds are bounded by (n + 1) x 2G in the worst case and shrink in practice; at n = 20 the predicate cost the same as n = 1 on every engine. The `HAVING` form is the one shape that needs a special chunk rule, and it is also the slowest at n = 20; it is not needed. |
| SQL Server needs the key binds cast through the column's collation | spec 145's rule, extended to the grant tables | Without the cast (`CAST(:p COLLATE Latin1_General_100_BIN2_UTF8 AS varchar(255))`) the nvarchar bind forces a scan of the grant table per outer row and the `EXISTS` costs about 10 ms per candidate (12.5 s for a 1,000-id join-back in the first smoke run). With it the same cell is 17 ms. The grant and membership tables must use vfs's `_string`/`BytewiseString` key types and the spec 145 bind treatment. |

## Limits

- One synthetic corpus, one seed. The shape (Zipf-skewed top-level directories, per-directory ownership, five everyone grants) is plausible, not measured from a real deployment. A corpus with no wide grants would make the materialised table smaller (12 to 17x the entry table on direct grants alone) but would not change the read-shape ranking.
- SQL Server and Oracle are amd64 under Rosetta. Their absolute times are 2 to 5x inflated; the memo reads their ratios and plan shapes only. Neither was run at 1M rows in the time box.
- The 1M runs are on SQLite and Postgres only, as briefed. MariaDB, SQL Server and Oracle at 1M are a rerun of `probe.py --files 800000` away (load is about 10 s per 100k rows on the emulated engines).
- Timings include fetching every result row to the client, which floors the small cells (a 20k-row listing at 1M is 19 ms of fetch before any predicate). Ratios between predicate shapes on the same filter are the evidence, not the absolute cells.
- The subject-set semantics measured are "visible to the set if every member is owner or holds a covering grant". Who owns a row the set writes, and how the audit records a set, are Q13 questions this study does not touch.
- The write point check resolves the level from grant rows only; it does not model the "owner may always write" rule or the level ladder's ordering. Those are constant-time app-side additions to the same 10-row read.
- Grants per principal are capped at 17 in this corpus. A deployment where one principal holds thousands of prefixes would push the literal form past the bind budget on Oracle (1,000 elements) and SQL Server (2,100 binds) first; the `EXISTS` fallback covers that caller at the measured per-row cost.
