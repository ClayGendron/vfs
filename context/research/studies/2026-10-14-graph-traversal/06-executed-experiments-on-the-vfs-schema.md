# R6 — Executed experiments: a depth-bounded directional walk over `vfs_edges` on the real vfs schema and backend

Date: 2026-10-14. Researcher R6 (executed experiments only). Everything below comes from scripts that ran against a `DatabaseStorage` over SQLite (SQLite 3.50.4, SQLAlchemy 2.0.52, Python 3.13) built through the public API, except where a line is marked `[READ]` (engine documentation) or `[NOT VERIFIED]`. Wall-clock figures are side notes only; the evidence is statement counts and row counts.

**Summary.** One recursive CTE per seed chunk does the job: anchor = the live seeds at depth 0, recursive member = one hop in the chosen direction joined to `vfs_entries` on the far endpoint with the liveness term and the rights predicate, `UNION` to bound the working table, `GROUP BY node, MIN(depth)` to get BFS distance. On the cyclic 2,000-node / 8,000-edge graph it agreed with a pure-Python BFS in 480 of 480 trials (3 directions × depths 1–4 × 20 seed sets × 2 type filters). With the rights predicate *inside* the member the walk cannot pass through a hidden node (placement A); with it only on the final result (placement B) a visible node reachable only through a hidden one leaks — A is what ADR 065 and Clay's rule require, and SQLite executes vfs's own three-seek `visible` CTE inside the recursive member. At 10,000 seeds the statement count is `ceil(seeds / membership_budget)` and does not grow with depth (1 on SQLite/Postgres/MariaDB, 5 on SQL Server, 10 on Oracle), versus `Σ_hops ceil(|frontier_h| / budget)` for an app-side frontier loop (2–3, 6–7, 12–13). Two cautions survived the runs: `UNION` dedups `(node, depth)` pairs, not nodes, so it is a polynomial bound (≤ N × (depth+1) rows), not a visited set, and plain `UNION ALL` explodes exponentially on a dense cycle (7.9 M rows at depth 3 on a 200-clique; 1.58 B at depth 4, not runnable). Engine docs `[READ]` say SQL Server and Oracle refuse `UNION` between the anchor and the recursive member, so the `UNION` bound is not available there; the frontier loop is the only form with a true visited set on every engine.

## Results table

| # | Experiment (script) | What it proves | Key numbers |
|---|---|---|---|
| 1 | Build graph (`r6_build_graph.py`) | The public API builds a cyclic graph at contract size in one call each | 2,000 files written in one `write`; 8,000 authored edges in one `mkedge` (all `created`); `vfs_edges` = 2,005 `fs` + 4,692 `imports` + 2,492 `references` + 816 `calls` = 10,005; one SCC of 1,914 nodes (cyclic) |
| 2 | CTE walk (`r6_cte_walk.py`) | One recursive CTE per direction is correct on cycles; `UNION` bounds rows but is not a visited set; `MIN(depth)` gives BFS distance | 480/480 agree with Python BFS (UNION); 108/108 (UNION ALL subset); out/4/UNION: 1,583 CTE rows for 1,253 distinct nodes, 310 nodes have rows at >1 depth; UNION ALL: 2,186 rows, 435 duplicate `(node,depth)` pairs; `both`: 3,774 (UNION) vs 34,539 (UNION ALL) |
| 3 | Rights (`r6_cte_rights.py`) | Predicate inside the member (A) differs from predicate on the result (B); A is required; SQLite runs the three-seek join in the member; all 5 dialects compile | A reaches {x:0, z:1}; B reaches {x:0, z:1, **y:2**} (y only via hidden node); `visible_entries` rows 504 == `Rights.admits` rows 504; literal-OR form == A; `WITH RECURSIVE` on sqlite/postgresql/mariadb, `WITH` on mssql/oracle; no compile refusals |
| 4 | 10,000 seeds (`r6_seed_chunking.py`) | Chunking by `membership_budget`; CTE statements = chunks, depth-independent; frontier loop = Σ hops' chunks | chunks for 10k: sqlite 1, postgresql 1, mariadb 1, mssql 5, oracle 10; CTE depth 2: 1 / 5 / 10 statements, rows 12,003 / 31,535 / 43,557; frontier depth 2: 2 / 6 / 12 statements, rows 10,316 / 17,352 / 20,830; depth 4: CTE 1 / 5 / 10 vs frontier 3 / 7 / 13; temp-table anchor: 4 statements (CREATE, INSERT, WITH, DROP) |
| 5 | Cycle bomb (`r6_cycle_bomb.py`) | `UNION ALL` is exponential on a dense cycle; `UNION` is polynomial; the frontier loop is linear and stops | 200-clique depth 3: UNION ALL 7,920,400 rows (4.77 s) vs UNION 600 rows vs frontier 399 rows / 2 statements; depth 4: UNION ALL 1,576,159,601 (predicted, not run), UNION 800 rows with 119,400 join rows, frontier 399 rows / 2 statements |
| probe | IN-list planner (`r6_probe_in_list.py`) | A per-hop non-recursive statement with an IN list needs the profile's `range_join` (or `ANALYZE`) on SQLite; the recursive member does not | 1,000-seed hop: 8.2 s plain `JOIN` (planner drives from `ix_vfs_entries_deleted_at`) vs 0.013 s with `CROSS JOIN`; 10,000-seed hop 0.088 s; after `ANALYZE` plain `JOIN` = 0.011 s |

Scripts (all under `./experiments/`): `r6_common.py` (shared helpers: storage open, statement counter, CTE builder, BFS, frontier loop), `r6_build_graph.py`, `r6_cte_walk.py`, `r6_cte_rights.py`, `r6_seed_chunking.py`, `r6_cycle_bomb.py`, `r6_probe_in_list.py`. Outputs are beside them as `*.out`. Databases: `r6_graph.sqlite` (experiments 1–3), `r6_graph_10k.sqlite` (4), `r6_cycle.sqlite` (5). Run with `uv run python <script>` from the vfs repo root.

## Setup learned from the tree `[READ, cited]`

- Tests build a mount as `DatabaseStorage(url=_url(tmp_path))` where `_url` is `sqlite+aiosqlite:///<tmp>/vfs.sqlite` (`tests/support/database_helpers.py:39-50`); first touch provisions the schema (`:66-75`, `storage.first_touch()`). The scripts do the same on a scratchpad file, with the constructor's `posture="private"` (`src/vfs/storage/backends/database/backend.py:195`) so everyone holds nothing.
- Files and edges go in through the verbs: `storage.write(entries=[Entry(path=Path(...), content=...)], parents=True)` and `storage.mkedge(edges=[Edge(source=Path, target=Path, edge_type=...)], provenance="user")` (`tests/storage/database/test_edges.py:321-327` `_fan_out`; signatures `backend.py:614-621`, `:852-858`).
- A test borrows the engine host: `storage._host.tables` and `async with storage._host.session_factory() as session` (`test_edges.py:56-60`), and counts statements with `event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")` (`test_edges.py:335-337`). `EngineHost.engine` / `.profile` / `.parameter_budget` (`= dialect.insertmanyvalues_max_parameters`) / `.membership_budget` live at `src/vfs/storage/backends/database/engine.py:204-223`. Read-only custom statements through the session are exactly what the scripts run.
- Tables: `vfs_edges(id, source_id, target_id, edge_type, weight, distance, provenance, context)` with the unique `(source_id, target_id, edge_type)` and indexes `ix_vfs_edges_fwd (source_id, edge_type)`, `ix_vfs_edges_rev (target_id, edge_type)` (`src/vfs/models/rows.py:600-615`); `vfs_entries` has `entry_id`, `path`, `kind`, `deleted_at`, `owner_id`, `everyone_level` (`rows.py:421-497`). `ULIDKey` is stored as BINARY(16) (`rows.py:296-316`) — a temp-table anchor must use the same type or the join matches nothing (observed: `String(26)` column → 0 rows).
- Liveness: `liveness_filters(entry, profile, include_meta=False)` = `deleted_at IS NULL AND path != '/.vfs' AND path NOT LIKE '/.vfs/%'` (`src/vfs/storage/backends/database/descent.py:223-234`).
- Rights: a verb resolves `resolve_authority(session, tables, profile, membership_budget, authority, cache)` and, unless `resolution.read.whole`, builds `Visibility(resolution.read, tables, profile, membership_budget, parameter_budget)` and calls `view.prepare(session)` (`backend.py:1416-1447` `_resolution`/`_viewed`); `tree_rows` narrows its statement with `view.narrow(stmt, scope)` and still passes every row through `view.admits` (`reads.py:224-275`, `:715-724`). `view.entries()` is the three-seek `visible_entries` derived table (`ranges.py:96-134`; a `MATERIALIZED` CTE on SQLite because `range_fence` is set, a subquery elsewhere); `view.clauses()` is the literal-OR fan (`rights.py:340-366`).
- Budgets: `membership_budget(profile, parameter_budget) = max(1, min(in_list_budget, parameter_budget - 32))` and `chunked(items, size)` (`dialects.py:651-658`, `:683-687`); `in_list_budget` is 32,766 (sqlite), 65,535 (postgresql, mariadb), 2,000 (mssql), 1,000 (oracle, generic) (`dialects.py:390-556`). `range_join` is `CROSS JOIN` on SQLite, `STRAIGHT_JOIN` on MariaDB, `INNER LOOP JOIN` on SQL Server, plain `JOIN` on Postgres and Oracle, with the measured reasons in the field docstring (`dialects.py:238-258`).
- The backend never issues `ANALYZE` (grep over `src/vfs/storage/backends/database/*.py`: no hit).

## Experiment 1 — the graph `[EXECUTED]`

```
profile=sqlite parameter_budget=32700 membership_budget=32668
write 2000 files in one call: 0.52s            write: success=True observations=2000
mkedge 8000 authored edges in one call: 0.20s  mkedge: success=True statuses={'created': 8000}
vfs_edges rows by edge_type:
    calls        816
    fs           2005
    imports      4692
    references   2492
    TOTAL        10005
vfs_entries rows by kind: {'directory': 6, 'file': 2000}
cycles: 8000 authored edges over 2000 nodes; SCCs of size>1: 1, largest SCC = 1914 nodes
```

2,005 `fs` rows = one per non-root entry (2,000 files + 5 non-root directories: `/src`, `/src/a`, `/src/b`, `/lib`, `/docs`), exactly the mirror invariant `edges.py` describes. Authored rows = 8,000. The random graph plus ten planted rings has one strongly connected component of 1,914 nodes, so nearly every node lies on a cycle.

## Experiment 2 — one recursive CTE per direction `[EXECUTED]`

The statement (rendered by SQLAlchemy for SQLite; `out`, depth 3, two seeds; the `in` form swaps the two edge columns in `adj`, `both` is discussed below):

```sql
WITH RECURSIVE walk(node, depth) AS
(SELECT seed.entry_id AS node, 0 AS depth
 FROM vfs_entries AS seed
 WHERE seed.deleted_at IS NULL AND seed.path != '/.vfs' AND seed.path NOT LIKE '/.vfs/%' ESCAPE '\'
   AND seed.entry_id IN ('01M4X1D2P9S24XE5PT4NN6D5ZH', '01M4X1D2NVMXT9WXSKKJNS092G')
 UNION
 SELECT adj."to" AS node, w.depth + 1 AS depth
 FROM walk AS w
 JOIN (SELECT vfs_edges.source_id AS frm, vfs_edges.target_id AS "to", vfs_edges.edge_type AS edge_type
       FROM vfs_edges WHERE vfs_edges.edge_type IN ('imports', 'references', 'calls')) AS adj ON adj.frm = w.node
 JOIN vfs_entries AS far ON far.entry_id = adj."to"
 WHERE w.depth < 3 AND far.deleted_at IS NULL AND far.path != '/.vfs' AND far.path NOT LIKE '/.vfs/%' ESCAPE '\')
SELECT walk.node, min(walk.depth) AS depth FROM walk GROUP BY walk.node
```

(a) Rows per depth, max_depth 4, authored types, five seeds, on the cyclic graph:

```
direction form         d0     d1      d2       d3       d4  CTE rows distinct nodes
out       UNION         5     22     100      378     1078      1583           1253
out       UNION ALL     5     22     100      414     1645      2186           1253
in        UNION         5     19      72      278      837      1211            970
in        UNION ALL     5     19      74      299     1196      1593            970
both      UNION         5     41     311     1421     1996      3774           1997
both      UNION ALL     5     41     376     3339    30778     34539           1997
```

(b) `UNION` dedups `(node, depth)` pairs, not nodes — it is **not** a visited set when depth is a column:

```
CTE rows=1583 distinct nodes=1253 nodes with >1 depth row=310
e.g. /src/a/f0468.py: 4 rows at depths [1, 2, 3, 4] (min 1, max 4)
e.g. /src/a/f0143.py: 3 rows at depths [2, 3, 4] (min 2, max 4)
under UNION ALL, (node, depth) pairs that occur more than once: 435 (UNION removes exactly these and nothing else)
```

(c) BFS distance = `GROUP BY node, MIN(depth)` over the CTE; the working table it materialised beside it:

```
UNION     CTE rows=  1583 min-depth rows= 1253 == python BFS: True
UNION ALL CTE rows=  2186 min-depth rows= 1253 == python BFS: True
```

Validation against the pure-Python BFS (`r6_common.bfs`) over the same edge list read back from the database:

```
20 random seed sets (1-8 seeds) x depths 1..4 x 3 directions x (authored types, all types incl. fs)
UNION form: 480 agree / 0 disagree; UNION ALL form (subset: depth<=3, <=3 seeds): 108 agree
```

Both the node sets and the min depths agreed in every trial, including the "all types" runs where the `fs` edges make directories reachable.

Plans (`EXPLAIN QUERY PLAN`, SQLite). The `out` member seeks the unique-constraint covering index on `source_id` and the far entry by `entry_id`; `both` written as a `UNION ALL` adjacency derived table makes SQLite build an **automatic index per recursive step**, while `both` as an OR-join on `vfs_edges` (`ON e.source_id = w.node OR e.target_id = w.node`, far = `CASE`) uses `MULTI-INDEX OR` over the two edge indexes. Both forms matched the BFS; the OR-join is the shape to keep.

```
out:   RECURSIVE STEP / SCAN w / SEARCH vfs_edges USING COVERING INDEX sqlite_autoindex_vfs_edges_1 (source_id=?)
       / SEARCH far USING INDEX ix_vfs_entries_entry_id (entry_id=?)
both (UNION ALL adjacency): RECURSIVE STEP / CO-ROUTINE adj / COMPOUND QUERY ... / SCAN w
       / BLOOM FILTER ON adj (frm=?) / SEARCH adj USING AUTOMATIC COVERING INDEX (frm=?)
both (OR-join): RECURSIVE STEP / SCAN w / MULTI-INDEX OR / INDEX 1 SEARCH vfs_edges USING COVERING INDEX
       sqlite_autoindex_vfs_edges_1 (source_id=?) / INDEX 2 SEARCH vfs_edges USING INDEX ix_vfs_edges_rev
       (target_id=? AND edge_type=?) / SEARCH far USING INDEX ix_vfs_entries_entry_id (entry_id=?)
```

## Experiment 3 — the rights predicate rides every hop `[EXECUTED; compile-only for four dialects]`

Mount posture private; `ann` granted `read` on `/src/a` through `storage.grant(..., authority=SYSTEM)`. Planted chain `/src/a/r6_x.py → /src/b/r6_hidden.py → /src/a/r6_y.py` and a control edge `/src/a/r6_x.py → /src/a/r6_z.py`. The view was built exactly as `backend._viewed` does (`resolve_authority` → `Visibility` → `prepare`).

```
ann's read rights: level=read spans=(('/src/a', '/src/a\x00'), ('/src/a/', '/src/a0')) roots=('/src/a',) whole=False empty=False need=1
view.entries() -> CTE named 'visible' (profile range_source=json_each, range_fence=MATERIALIZED)
view.clauses() -> 1 clause(s), binds=[13]
visible_entries rows=504 == rows Rights.admits passes=504: True

Placement A: predicate inside the recursive member (and the anchor)
    reached: {'/src/a/r6_x.py': 0, '/src/a/r6_z.py': 1}
Placement B: no predicate in the walk; the final result joined to the visible set
    reached: {'/src/a/r6_x.py': 0, '/src/a/r6_z.py': 1, '/src/a/r6_y.py': 2}
    visible nodes B reports that A does not: ['/src/a/r6_y.py']  <- reachable only THROUGH the hidden /src/b/r6_hidden.py

Placement A with the literal-OR form (visibility_clauses on the far alias), one statement
    reached: {'/src/a/r6_x.py': 0, '/src/a/r6_z.py': 1}  == A: True
```

Findings:

- **A and B differ, and A is required.** ADR 065 pin 1: "A hidden row is absent ... not in listings, globs, greps, glean results, edge traversals" (`context/decisions/065-*.md:44-49`). B reports `/src/a/r6_y.py` at depth 2, which tells ann that something she cannot see links `x` to `y` — an existence leak through a hidden row. Clay's direction (2) "rights enforced through the traversal" is placement A.
- **The SQL pushdown is exact for traversal use.** `visible_entries` returned the same 504 `entry_id`s as `Rights.admits` over every row. That matters because inside recursion there is no Python `admits` pass: the pushdown *is* the authority there. (`[NOT VERIFIED: holes]` — this was measured with no relabel in flight; the holed branches exist in the statement but carried empty piece sets.)
- **SQLite executes the three-seek join inside the recursive member**: the `visible` `MATERIALIZED` CTE (`json_each` unpacking, `CROSS JOIN` pinned) is referenced from both the anchor and the recursive member and SQLite ran it (placement A above). No error, no rewrite needed.
- **The literal-OR fan must be one statement.** `visibility_clauses` is designed to be run "once per clause and merged" (`rights.py:343-348`). That merge is wrong for a traversal: a path admitted by clause 1 then clause 2 is found by neither statement. For the walk, the clauses have to be `OR`-ed into one predicate inside the member (done above: `or_(*clauses)`), which means the clause count cap, not only the bind cap, binds the design where the dialect has no range source (the `GENERIC` floor).

Rendered SQL, placement A, SQLite (the shape the spec would ship on SQLite):

```sql
WITH RECURSIVE visible AS MATERIALIZED
(SELECT vfs_entries.entry_id AS entry_id FROM vfs_entries WHERE vfs_entries.everyone_level >= ?
 UNION ALL SELECT vfs_entries.entry_id FROM json_each(?) AS pts CROSS JOIN vfs_entries
   ON vfs_entries.path = pts.value AND vfs_entries.everyone_level < ?
 UNION ALL SELECT vfs_entries.entry_id FROM json_each(?) AS rng CROSS JOIN vfs_entries
   ON vfs_entries.path > json_extract(rng.value, ?) AND vfs_entries.path < json_extract(rng.value, ?) AND vfs_entries.everyone_level < ?
 UNION ALL ... owner branches ...),
walk(node, depth) AS
(SELECT seed.entry_id AS node, ? AS depth FROM vfs_entries AS seed
 WHERE seed.deleted_at IS NULL AND seed.path != ? AND seed.path NOT LIKE ? ESCAPE '\'
   AND seed.entry_id IN (__[POSTCOMPILE_entry_id_1]) AND seed.entry_id IN (SELECT visible.entry_id FROM visible)
 UNION SELECT adj."to" AS node, w.depth + ? AS depth
 FROM walk AS w JOIN (SELECT ... FROM vfs_edges WHERE vfs_edges.edge_type IN (__[POSTCOMPILE_edge_type_1])) AS adj ON adj.frm = w.node
 JOIN vfs_entries AS far ON far.entry_id = adj."to"
 JOIN visible ON visible.entry_id = far.entry_id
 WHERE w.depth < ? AND far.deleted_at IS NULL AND far.path != ? AND far.path NOT LIKE ? ESCAPE '\')
SELECT walk.node, min(walk.depth) AS depth FROM walk GROUP BY walk.node
```

Compile-only for the other dialects (placement A, `out`, depth 3; each with its own `DialectProfile` so the `visible` derived table takes that engine's range source). Nothing was refused. First lines:

```
postgresql: 'WITH RECURSIVE walk(node, depth) AS '   visible=Subquery (unnest(...::TEXT[]) JOIN ... COLLATE "C")
mariadb:    'WITH RECURSIVE walk(node, depth) AS '   visible=Subquery (JSON_TABLE ... STRAIGHT_JOIN vfs_entries FORCE INDEX (ix_vfs_entries_path))
mssql:      'WITH walk(node, depth) AS '             visible=Subquery (openjson(...) INNER LOOP JOIN ...; adj.[to])
oracle:     'WITH walk(node, depth) AS '             visible=Subquery (JSON_TABLE(...) with /*+ INDEX */ and /*+ CARDINALITY */ hints)
```

The SQL Server rendering, `out` direction, trimmed to the walk (the `visible` subquery is the one printed in `r6_cte_rights.out`; it is inlined **twice**, once in the anchor and once in the member, because the MSSQL profile has no `range_fence`):

```sql
WITH walk(node, depth) AS
(SELECT seed.entry_id AS node, :param_1 AS depth FROM vfs_entries AS seed
 WHERE seed.deleted_at IS NULL AND seed.path != :path_1 AND seed.path NOT LIKE :path_2 ESCAPE '\'
   AND seed.entry_id IN (__[POSTCOMPILE_entry_id_1])
   AND seed.entry_id IN (SELECT visible.entry_id FROM (SELECT ... openjson(:openjson_1) AS pts INNER LOOP JOIN vfs_entries ... ) AS visible)
 UNION SELECT adj.[to] AS node, w.depth + :depth_1 AS depth
 FROM walk AS w JOIN (SELECT ... FROM vfs_edges WHERE vfs_edges.edge_type IN (__[POSTCOMPILE_edge_type_1])) AS adj ON adj.frm = w.node
 JOIN vfs_entries AS far ON far.entry_id = adj.[to]
 JOIN (SELECT ... AS visible) ON visible.entry_id = far.entry_id
 WHERE w.depth < :depth_2 AND far.deleted_at IS NULL AND far.path != :path_3 AND far.path NOT LIKE :path_4 ESCAPE '\')
SELECT walk.node, min(walk.depth) AS depth FROM walk GROUP BY walk.node
```

Two things the compiler does **not** catch, from the engine docs `[READ]`:

- SQL Server: "UNION ALL is the only set operator allowed between the last anchor member and first recursive member" ([WITH common_table_expression, SQL Server 2008 R2 page](https://learn.microsoft.com/en-us/previous-versions/sql/sql-server-2008-r2/ms175972(v=sql.105)); the current page states the same operator rule and notes `UNION ALL` does not deduplicate per step: [WITH common_table_expression (Transact-SQL)](https://learn.microsoft.com/en-us/sql/t-sql/queries/with-common-table-expression-transact-sql?view=sql-server-ver17)). Recursion depth is capped by `OPTION (MAXRECURSION n)`, default 100 ([Recursive Queries Using Common Table Expressions](https://learn.microsoft.com/en-us/sql/t-sql/queries/recursive-common-table-expression-transact-sql?view=sql-server-ver17)). So the `UNION` rendered above is **invalid T-SQL**; only the `UNION ALL` form runs there.
- Oracle: "You must combine the recursive member with the anchor member using the UNION ALL set operator" and the recursive member must reference the query name exactly once ([Oracle 21c SQL Reference, SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/21/sqlrf/SELECT.html)). Without a `CYCLE` clause a detected cycle raises ORA-32044 ([Red Gate, recursive subquery factoring](https://www.red-gate.com/simple-talk/databases/oracle-databases/anatomy-of-a-select-statement-part-3-recursive-subquery-factoring/)). Oracle's cycle detection is per path (an ancestor row on the same path), not a global visited set `[NOT VERIFIED: not run on Oracle]`.
- MariaDB accepts `UNION` (`UNION DISTINCT`) in a recursive CTE, and from 10.5.2 offers `CYCLE <cols> RESTRICT`, which applies uniqueness to the named columns only — the ticket that motivated it is exactly our case: "UNION DISTINCT works for graph traversal when the CTE carries only edge columns, but fails once a depth column is added" ([MariaDB WITH](https://mariadb.com/kb/en/with/), [MDEV-20632](https://jira.mariadb.org/browse/MDEV-20632)).
- PostgreSQL accepts `UNION` or `UNION ALL` in the recursive term and (14+) a `CYCLE` clause `[NOT VERIFIED by search in this session; from the PostgreSQL manual's WITH Queries chapter]`.
- SQLite: both forms executed above.

Bind budget note for SQL Server: the anchor's seed `IN` list (≤ 2,000 by `membership_budget`) plus two inlined copies of the `visible` subquery (13 binds each here) plus the fixed binds fit in 2,099 for this rights shape, but the 32-bind reserve in `membership_budget` is not sized for two predicate copies; a `range_fence` for MSSQL (a CTE) or chunking seeds by `membership_budget - 2 × predicate binds` would be needed in the spec.

## Experiment 4 — 10,000 seeds in one call `[EXECUTED]`

Graph: the experiment-1 file copied and extended with 10,000 `/bulk/..` files (one `write` call, 2.8 s) and 20,000 edges (one `mkedge` call, 0.57 s): each bulk file `imports` a random core file and `references` a random bulk file. Seeds = the 10,000 bulk files; 12,031 live entries in all.

```
Seed chunking by membership_budget(profile, parameter_budget) = min(in_list_budget, binds - 32):
    dialect     binds (SQLAlchemy)  in_list_budget  membership_budget  chunks for 10k
    sqlite (live)              32700           32766              32668               1
    postgresql               32700           65535              32668               1
    mariadb                  32700           65535              32668               1
    mssql                     2099            2000               2000               5
    oracle                   32700            1000               1000              10
```

Recursive CTE per seed chunk, `out`, depth 2, authored types; statements counted with `before_cursor_execute` (the session's `BEGIN` excluded); merge = min depth per node across chunks:

```
    budget                 chunks statements rows returned distinct nodes
    sqlite 32,668               1          1         12003          12003
    mssql 2,000                 5          5         31535          12003
    oracle 1,000               10         10         43557          12003
    merged results identical across chunkings: True
```

Rows returned grow with the chunk count (12,003 → 31,535 → 43,557 for the same 12,003-node answer) because every chunk re-walks the neighbourhood the other chunks also reach; the merge is cheap but the engine work is repeated per chunk.

Temp-table anchor on SQLite through the backend's session (`CREATE TEMPORARY TABLE r6_seeds(node ULIDKey)`, one bulk `INSERT` — SQLAlchemy's insertmanyvalues put all 10,000 rows in one statement under the 32,700-bind budget — then ONE walk anchored on `JOIN r6_seeds ON node = entry_id`, then `DROP`):

```
    statements=4 (CREATE, INSERT, WITH, DROP); rows returned=12003; == chunked CTE: True
```

`[NOT RUN: other engines]` Postgres and MariaDB have per-session `CREATE TEMPORARY TABLE`; SQL Server `#temp` tables likewise; Oracle DDL commits the transaction and global temporary tables must be pre-created (18c+ private temporary tables exist). The seeds still cost one bind each on the `INSERT`, chunked by the bind budget, so the count is `1 + ceil(S / bind_budget) + 1 + 1` — never fewer round trips than the IN-list form, and it adds DDL to a read verb.

Frontier loop (one non-recursive statement per hop per frontier chunk, visited set in Python; the hop statement uses the profile's `range_join` — see the probe):

```
    budget                 depth statements rows returned distinct nodes  == CTE
    sqlite 32,668              2          2         10316          12003    True
    sqlite 32,668              4          3         10358          12003       -
    mssql 2,000                2          6         17352          12003    True
    mssql 2,000                4          7         17394          12003       -
    oracle 1,000               2         12         20830          12003    True
    oracle 1,000               4         13         20872          12003       -

Recursive CTE per chunk at depth 4 (statement count is depth-independent):
    sqlite 32,668          depth 4: statements=1  rows returned=12003 distinct nodes=12003
    mssql 2,000            depth 4: statements=5  rows returned=35362 distinct nodes=12003
    oracle 1,000           depth 4: statements=10 rows returned=53388 distinct nodes=12003
```

The frontier loop's rows stay near the answer size because hop *h* only asks about nodes first seen at hop *h-1*; its statement count is `Σ_h ceil(|F_h| / budget)` (hop 1 = the seed chunks, later hops small). The CTE's count is `ceil(S / budget)` whatever the depth.

### The probe: why the frontier loop stalled before the fix `[EXECUTED]`

The first frontier run was killed after 10 CPU-minutes. The non-recursive hop statement `SELECT DISTINCT e.target_id FROM vfs_edges e JOIN vfs_entries far ON far.entry_id = e.target_id WHERE e.source_id IN (...) AND e.edge_type IN (...) AND far.deleted_at IS NULL ...` plans, on a stat-less SQLite file, as a scan of **every live entry** through `ix_vfs_entries_deleted_at (deleted_at=?)` followed by an edge-index probe per (entry × seed × type):

```
plain JOIN:        IN-list of 100: 0.81s   1,000: 8.2s   3,000: 24.6s   (linear in the IN list × all entries)
    plan: SEARCH far USING INDEX ix_vfs_entries_deleted_at (deleted_at=?)
          SEARCH vfs_edges USING COVERING INDEX sqlite_autoindex_vfs_edges_1 (source_id=? AND target_id=? AND edge_type=?)
edges CROSS JOIN far (profile.range_join): 100: 0.009s   1,000: 0.013s   3,000: 0.033s   10,000: 0.088s
    plan: SEARCH vfs_edges USING COVERING INDEX sqlite_autoindex_vfs_edges_1 (source_id=?)
          SEARCH far USING INDEX ix_vfs_entries_entry_id (entry_id=?)
after ANALYZE, plain JOIN:                 100: 0.003s   1,000: 0.011s   3,000: 0.029s   (same good plan)
```

The recursive member never hit this: a recursive CTE's working table is a co-routine and must be the outer loop, so the edge index is always probed from `w.node`. Any **non-recursive** per-hop statement (the frontier loop, or a one-hop `neighbours` verb) needs the dialect's join pin — vfs already models this planner misread as `DialectProfile.range_join` for the ranges join, and reusing it fixed the hop. The backend runs no `ANALYZE`.

## Experiment 5 — the cycle bomb `[EXECUTED]`

Two fully connected clusters (every ordered pair an edge): 200 nodes (39,800 edges) and 50 nodes (2,450 edges), 42,250 edges in one `mkedge` call (0.80 s). One seed, direction `out`. "UNION join work" is the number of rows the recursive member's join evaluates under `UNION`, measured as `(distinct (node, depth-1) rows) × out-degree` summed over levels; "frontier rows" are rows returned by the loop's statements (budget 1,000).

```
200-node cluster:
    depth  UNION ALL rows  (predicted) UNION rows UNION join work frontier rows frontier stmts
        1             200          200        200             199           199              1
        2           39801        39801        400           39800           399              2
        3         7920400      7920400        600           79600           399              2      (UNION ALL: 4.77s)
        4         not run   1576159601        800          119400           399              2
50-node cluster:
        1              50           50         50              49            49              1
        2            2451         2451        100            2450            99              2
        3          120100       120100        150            4900            99              2
        4         5884901      5884901        200            7350            99              2      (UNION ALL: 3.64s)
```

- `UNION ALL` with a depth column enumerates **paths**: `Σ_{d≤D} (N-1)^d`. The prediction matched the engine exactly at every runnable point; depth 4 on 200 nodes is 1.58 billion rows and was not attempted. A dense cyclic cluster (a hub module everyone imports and that imports everyone) is an ordinary shape in a code graph.
- `UNION` on `(node, depth)` bounds the working table to `≤ N × (D+1)` rows (800) but the member still re-expands every node at every level: `N × deg × D` join rows (119,400 at depth 4). Polynomial, not exponential; the per-level work is the whole cluster's edge count.
- The frontier loop with an app-side visited set returns `≤ 2N` rows, issues 2 statements (hop 2 finds no new node and the loop stops), and its in-engine join work is `Σ_h |new_h| × deg` = 199 × 199 at hop 2 and nothing after.

## Open questions

1. Oracle's and SQL Server's refusal of `UNION` in the recursive member is from documentation, not execution. The db_test legs (Postgres, MariaDB, MSSQL, Oracle) should run `r6_cte_walk.py`'s UNION and UNION ALL forms once the spec picks a shape. `[NOT VERIFIED: no engine legs here]`
2. Whether MariaDB's `CYCLE (node) RESTRICT` and Postgres 14's `CYCLE node SET ... USING path` give a min-depth visited set in breadth-first evaluation order (if so, they are a per-dialect `UNION`-free bound). Not run.
3. The visible subquery is inlined twice on the four profiles without `range_fence`; the bind cost and the plan cost (the three-seek join evaluated per recursive step, or once?) on real engines is unmeasured.
4. `both` through the OR-join form vs two separate `out`/`in` walks merged in Python — not compared at scale.

## What the numbers say for the spec

**Statement shape per chunk** (one statement per seed chunk, any direction, any depth):

```
WITH [RECURSIVE] visible AS (<three-seek union, or the OR-ed clause fan where the dialect has no range source>),
walk(node, depth) AS (
  SELECT seed.entry_id, 0 FROM vfs_entries seed
   WHERE <liveness(seed)> AND seed.entry_id IN (<chunk ≤ membership_budget>) AND seed.entry_id IN (SELECT entry_id FROM visible)
  UNION [ALL]
  SELECT far_id, w.depth + 1
    FROM walk w JOIN vfs_edges e ON <out: e.source_id = w.node | in: e.target_id = w.node | both: OR of the two, far_id = CASE>
    JOIN vfs_entries far ON far.entry_id = far_id JOIN visible ON visible.entry_id = far.entry_id
   WHERE w.depth < :max_depth AND <liveness(far)> [AND e.edge_type IN (<types>)])
SELECT node, MIN(depth) FROM walk GROUP BY node
```

The liveness term and the rights predicate sit on the far endpoint **inside** the member (placement A) and on the seed. The rights predicate is the whole predicate in one statement — the clause-fan "run per clause and merge" of the readers does not apply to a traversal. `both` is the OR-join, not a UNION ALL adjacency.

**Statement count per call:**

| form | statements | row work | bound on cycles |
|---|---|---|---|
| recursive CTE per seed chunk | `ceil(S / membership_budget)` — 1 / 1 / 1 / 5 / 10 for 10k seeds on sqlite / postgresql / mariadb / mssql / oracle; independent of depth | rows returned grow with chunk count (12k → 31k → 44k for the same answer) | `UNION`: `≤ N × (D+1)` rows, `N × deg × D` join rows; `UNION ALL`: `Σ (N-1)^d` rows — unbounded in practice |
| frontier loop (one non-recursive statement per hop per chunk) | `Σ_h ceil(|F_h| / membership_budget)` — 2–3 / 6–7 / 12–13 at depth 2–4 | rows ≈ answer size (10k–21k) | app-side visited set: `≤ 2N` rows, `Σ |new_h| × deg` join rows, stops when nothing is new |
| temp-table anchor + one CTE | `3 + ceil(S / bind_budget)` plus DDL in a read | as the CTE | as the CTE |

**Which cycle policy survived.** `UNION ALL` did not: the depth column turns it into a path enumerator (7.9 M rows at depth 3 on a 200-clique, 1.58 B at depth 4). `UNION` on `(node, depth)` survived on SQLite (executed) and, per the docs, on Postgres and MariaDB: a polynomial bound, correct min-depths, 480/480 agreement — but it is **not** a visited set (310 of 1,253 nodes carried rows at several depths) and the engine docs say SQL Server and Oracle refuse `UNION` in the recursive member, so on those two the single-statement form is `UNION ALL` with its blow-up (Oracle's `CYCLE` only prunes repeats within one path). The frontier loop survived everywhere: it is the only form with a true visited set on all five engines, its statement count is `hops × chunks` rather than `chunks`, and its per-hop statement needs the profile's `range_join` pin (a planner fact vfs already declares). The honest reading: on SQLite/Postgres/MariaDB the recursive CTE with `UNION` is one statement per chunk and bounded; on SQL Server/Oracle the bounded shape is the frontier loop (or a `UNION ALL` CTE with an engine-side recursion cap and the blow-up accepted), so "one recursive statement per chunk on every dialect" is not achievable with one portable cycle policy — the walk shape, like the ranges join, is a `DialectProfile` fact.
