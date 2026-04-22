# Porting meeting_subgraph from Postgres PL/pgSQL to SQL Server T-SQL

- **Date:** 2026-04-22
- **Trigger:** wanted MSSQL parity for the native `meeting_subgraph` traversal that Postgres already does in a PL/pgSQL function. The portable `rustworkx` fallback was fine functionally but we wanted the same in-database pushdown on SQL Server.
- **Status:** port shipped in commit adding the T-SQL proc + TVP wiring. This memo captures the research and gotchas so future ports (or regressions) don't have to rediscover them.

## Version target

**SQL Server 2019 is the theoretical floor. Grover targets 2025 RTM** (see `docker/mssql/`), so we have the full 2022+ feature set:

- `LEAST(a, b)` / `GREATEST(a, b)` — natively (2022+). No `CASE` shim.
- `LTRIM(str, chars)` — natively (2022+). Pre-2022 requires `STUFF(..., PATINDEX(...), ...)`.
- `CREATE OR ALTER PROCEDURE` — 2016+. Safe everywhere.
- `STRING_SPLIT` with `enable_ordinal` — 2022+. Not used; TVP is the right tool (see below).

We decided against `SHORTEST_PATH` / `MATCH` graph tables. `SHORTEST_PATH` (2019+) solves one shortest path between endpoint pairs; it has no Steiner-tree or multi-source-BFS-with-component-merging primitive. Migrating the data model to `AS NODE` / `AS EDGE` would be a huge change for no algorithmic gain.

## Primitive translation table

| Postgres | T-SQL equivalent |
|---|---|
| `text[]` param | TVP (`CREATE TYPE ... AS TABLE`, `READONLY` param) |
| `unnest(arr WITH ORDINALITY)` | direct `SELECT seed, ord FROM @tvp` |
| `ON CONFLICT (k) DO NOTHING` | `INSERT ... WHERE NOT EXISTS (SELECT 1 FROM t WHERE t.k = src.k)` — avoid `MERGE` ([Michael Swart on MERGE pitfalls](https://michaeljswart.com/2017/07/sql-server-upsert-patterns-and-antipatterns/)) |
| `LEAST(a, b)` / `GREATEST(a, b)` | native (2022+) |
| `GET DIAGNOSTICS v = ROW_COUNT` | `SET @v = @@ROWCOUNT;` on the **very next** statement — anything in between (even `IF`) clobbers it |
| `LOOP ... EXIT WHEN ... END LOOP` | `WHILE 1 = 1 BEGIN ... IF ... BREAK; END` |
| `FOR v IN SELECT ... LOOP` | **set-based rewrite** for performance; cursor only if inherently sequential |
| `CREATE TEMP TABLE ... ON COMMIT DROP` | `CREATE TABLE #t (...)` inside the proc — dropped when proc returns |
| `WITH x AS (...) DELETE FROM t USING x WHERE ...` | `;WITH x AS (...) DELETE target FROM t target INNER JOIN x ON x.k = target.k;` — single-target only |
| `RETURN QUERY SELECT ...` | stored procedure returning a rowset (not TVF; imperative loops disqualify inline TVFs, multi-statement TVFs are a perf footgun) |
| `a \|\| b` | `CONCAT(a, b, ...)` — **not `+`**. `+` propagates NULLs and turns the whole expression NULL; `CONCAT` coerces NULLs to empty string |
| `bigserial` | `BIGINT IDENTITY(1, 1)` — recreate the table per call instead of `TRUNCATE ... RESTART IDENTITY` |
| `ltrim(s, '/')` | native `LTRIM(s, '/')` (2022+) |

## Algorithm: the one real semantic decision

The Postgres version iterates each frontier node's neighbors one-by-one (`FOR v_neighbor IN SELECT ... LOOP`). Translating that as a T-SQL cursor would work, but cursors are expensive per-fetch and the iteration isn't fundamentally sequential.

**Set-based rewrite:** each outer BFS step becomes a small fixed sequence of set ops:

1. **Insert all newly-discovered neighbors** into `#_gm_visited` in one `INSERT ... SELECT ... LEFT JOIN #_gm_visited v ON ... WHERE v.node IS NULL`.
2. **Insert those same new nodes** into `#_gm_queue` (same `LEFT JOIN` pattern to skip already-queued), `ORDER BY a.neighbor` so the `IDENTITY` column assigns BFS order deterministically.
3. **Bridge detection with parity to the sequential version.** The sequential loop only records *one* bridge per cross-component encountered per frontier step — subsequent iterations see the already-merged component. A naïve set-based `INSERT INTO #_gm_bridge SELECT DISTINCT ... WHERE co.component <> @v_origin_component` would over-record. Fix: `ROW_NUMBER() OVER (PARTITION BY co.component ORDER BY a.neighbor)` + `WHERE rk = 1`. This matches the sequential loop's bridge count exactly.
4. **Component union** in one shot: `@v_winner = MIN(component)` over `{@v_origin_component} ∪ {distinct non-equal neighbor components}`, then one `UPDATE #_gm_component SET component = @v_winner WHERE component IN (that set)`. The sequential Postgres chain of `UPDATE ... WHERE component IN (pair)` converges to the same minimum, so this set-based form is equivalent.

We verified bug-for-bug parity via the test suite (matches the Postgres test outputs on the same seeded graphs, including the tie-case and deterministic topology tests).

## Python-side wiring: TVP via SQLAlchemy async + aioodbc

SQLAlchemy's `text()` cannot bind a TVP. You have to drop to the raw pyodbc cursor. The sanctioned pattern for "raw async cursor from an `AsyncSession`" is confirmed by Mike Bayer in [SQLAlchemy discussion #11447](https://github.com/sqlalchemy/sqlalchemy/discussions/11447):

```python
conn = await session.connection()              # AsyncConnection
dbapi_conn = (await conn.get_raw_connection()).driver_connection  # aioodbc connection
async with dbapi_conn.cursor() as cursor:
    await cursor.execute(
        "{CALL dbo.grover_meeting_subgraph(?, ?)}",
        (seed_tvp, scope_prefix),
    )
    rows = await cursor.fetchall()
    while await cursor.nextset():
        pass
```

### Why `await session.connection()` and not `engine.connect()`

Using `session.connection()` enlists the raw cursor in the session's transaction. `engine.connect()` would give you a detached connection — separate transaction, defeats the point of using the session.

### TVP shape

pyodbc 4.0.25+ accepts a list of tuples directly — **no** `pyodbc.SQL_SS_TABLE` wrapping, **no** `[type_name, schema, *rows]` prefix (that's a much older recipe). `(seeds_list_of_tuples, scalar_param)` as the params argument is correct. Verified in a spike and in the integration tests.

### MARS / shared connection safety

Without MARS (`MARS_Connection=Yes` in the ODBC connection string), SQL Server rejects a *second concurrently active* cursor on one connection with `HY010 "Connection is busy"`. SQLAlchemy eagerly closes cursors after `session.execute(...)`, so in practice sequential-use is safe — but if anyone later introduces streaming (`stream_results`, `yield_per`, `.scalars().partitions()`) in the same transaction before the raw-cursor call, this will deadlock silently on certain plans. Worth documenting if we ever add streaming reads.

### `SET NOCOUNT ON` is load-bearing

Without `SET NOCOUNT ON` at the top of the proc, pyodbc's first `fetchall()` raises `"No results. Previous SQL was not a query"` because the leading result set is an informational rowcount. `SET NOCOUNT ON` prevents this for the proc itself. It does **not** suppress counts from nested procs or triggers that re-enable counts, hence the defensive `while await cursor.nextset(): pass` drain after `fetchall()`.

### "No results" when the proc returns nothing

If the proc exits without emitting a result set (e.g. early `RETURN` on empty seeds), pyodbc still raises `"No results. Previous SQL was not a query"` — because there's no result set to fetch, not a row count. Our fix: emit an empty-but-valid result set in the empty branch:

```sql
SELECT CAST(NULL AS NVARCHAR(450)) AS path WHERE 1 = 0;
RETURN;
```

The `WHERE 1 = 0` guarantees zero rows while keeping pyodbc happy.

### aioodbc threading

aioodbc dispatches every ODBC call via `loop.run_in_executor`. SQLAlchemy's async layer goes through greenlet adaptation over the same aioodbc connection, ultimately the same executor. No cross-executor thread-affinity issue. Sequential is fine.

## Why not fold this into a TVF

Two reasons:

1. **Inline TVFs** can't have imperative logic (no `WHILE`, no temp tables).
2. **Multi-statement TVFs** accept imperative logic but the optimizer treats them as returning one row regardless of cardinality, and they can't parallelize. SQL Server 2019 interleaved execution helps, but the canonical advice for imperative logic with app-code callers remains: stored procedure returning a rowset.

## Path-length tradeoff surfaced by this work

Unrelated to the algorithm itself, but the MSSQL test harness revealed that `VFSObject.path` had been bumped from `max_length=4096` to `8192` in story 002 to accommodate synthesized sidecar paths (`/.vfs/<src>/__meta__/edges/out/<type>/<target>`). But `VARCHAR(8192)` exceeds SQL Server's 8000-byte limit for non-`MAX` varchar, so `create_all` couldn't target MSSQL at all.

Resolution: reverted to `max_length=4096` and tightened `test_path_at_exact_limit` to reserve headroom for the deepest auto-synthesized sidecar (`/.vfs` + path + `/__meta__/versions` = 23 chars of overhead). Users get 4073 usable path chars after sidecar math. This is the accepted product tradeoff: path + max sidecar suffix ≤ 4096.

## Sources

- [SQLAlchemy discussion #11447 — raw cursor from AsyncConnection](https://github.com/sqlalchemy/sqlalchemy/discussions/11447)
- [pyodbc wiki — Calling Stored Procedures](https://github.com/mkleehammer/pyodbc/wiki/Calling-Stored-Procedures)
- [pyodbc wiki — Working with TVPs](https://github.com/mkleehammer/pyodbc/wiki/Working-with-Table-Valued-Parameters-(TVPs))
- [pyodbc issue #290 — TVP shape / wrapping](https://github.com/mkleehammer/pyodbc/issues/290)
- [pyodbc issues #946 / #935 — "Previous SQL was not a query" and SET NOCOUNT](https://github.com/mkleehammer/pyodbc/issues/946)
- [MS Learn — Use Table-Valued Parameters (ODBC)](https://learn.microsoft.com/en-us/sql/relational-databases/native-client-odbc-how-to/use-table-valued-parameters-odbc)
- [MS Learn — LEAST (T-SQL)](https://learn.microsoft.com/en-us/sql/t-sql/functions/logical-functions-least-transact-sql)
- [MS Learn — STRING_SPLIT (T-SQL)](https://learn.microsoft.com/en-us/sql/t-sql/functions/string-split-transact-sql)
- [MS Learn — SHORTEST_PATH (SQL Graph)](https://learn.microsoft.com/en-us/sql/relational-databases/graphs/sql-graph-shortest-path)
- [MS Learn — CONCAT (T-SQL)](https://learn.microsoft.com/en-us/sql/t-sql/functions/concat-transact-sql)
- [MS Learn — DELETE with CTE](https://learn.microsoft.com/en-us/sql/t-sql/statements/delete-transact-sql)
- [Simple Talk — Alternatives to SQL 2022 GREATEST](https://www.red-gate.com/simple-talk/databases/sql-server/t-sql-programming-sql-server/alternatives-to-sql-2022-built-in-function-greatest/)
- [Simple Talk — Temporary Tables in SQL Server](https://www.red-gate.com/simple-talk/databases/sql-server/t-sql-programming-sql-server/temporary-tables-in-sql-server/)
- [Michael Swart — UPSERT patterns and antipatterns](https://michaeljswart.com/2017/07/sql-server-upsert-patterns-and-antipatterns/)
- [sqlblog.org — So, you want to use MERGE](https://sqlblog.org/merge)
- [mssqltips — Multi-Statement vs Inline TVF performance](https://www.mssqltips.com/sqlservertip/11632/sql-server-table-valued-function-performance-multi-statement-vs-inline/)
- [mssqltips — Graph Minimum Spanning Tree in SQL Server](https://www.mssqltips.com/sqlservertip/8275/graph-minimum-spanning-tree-in-sql-server/) — closest T-SQL prior art to Steiner; iterative `WHILE` + working-table pattern maps 1:1 onto our approach
- [Hans Olav — Graphs and Graph Algorithms in T-SQL](http://www.hansolav.net/sql/graphs.html)
