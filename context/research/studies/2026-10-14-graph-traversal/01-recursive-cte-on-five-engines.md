# R1 — Recursive traversal in SQL on the five vfs engines, and how SQLAlchemy renders it

Date: 2026-10-14. Researcher R1. Sources: `~/Git/Repos/sqlalchemy` @ cc5822a8 (2026-10-12),
`~/Git/Repos/postgres` @ b128e75e (2026-10-14), `~/Git/Repos/sqlite` @ 3d17c3f9e (2026-08-04),
vfs live tree; engine docs via WebFetch/WebSearch (URLs inline). Evidence is labelled
**EXECUTED** (I ran it), **READ** (source or doc text), **INFERRED** (my reasoning), or
`[NOT VERIFIED: why]`.

## Summary

One recursive-CTE shape serves all five engines. SQLAlchemy already emits the right preamble
per dialect (`WITH RECURSIVE` on PostgreSQL/SQLite/MySQL/MariaDB, bare `WITH` on SQL Server
and Oracle) and always renders the column list `walk(id, depth)`, which Oracle requires. Both
`.union_all()` and `.union()` compile on every dialect, but only `UNION ALL` is *legal* on
every engine: SQL Server and Oracle reject plain `UNION` between anchor and recursive member.
So the portable form is `UNION ALL` plus a hard depth bound (`WHERE walk.depth < :max_depth`)
inside the recursive member. Every engine evaluates the recursive member against only the rows
produced in the previous round (PostgreSQL, MariaDB, Oracle: whole working table per round;
SQLite and SQL Server: one row at a time off a queue/stack), so `depth` is always the
path-length at which the row was produced — never the shortest distance, and a node reachable
by two paths appears once per path. No engine dedups "visited" by `id` alone inside the CTE
when a `depth` column is carried; the portable floor is the depth bound (guaranteed
termination, bounded output growth by max fan-out^depth), with app-side `DISTINCT ON id` /
`MIN(depth)` in the outer query or in Python. PostgreSQL 14+, Oracle and MariaDB 10.5.2+ offer
a `CYCLE` clause that stops a *path* from revisiting a node, but it is not an id-dedup either.
The recursive member may join a `UNION ALL` derived table (the three-seek visibility shape) on
PostgreSQL, SQLite, MariaDB and Oracle; SQL Server forbids subqueries in the recursive member,
so there the visibility set must be a sibling CTE (allowed: "a CTE can reference ... previously
defined CTEs") or a temp table. Seeds feed the anchor through the same per-dialect range
sources vfs already has (`json_each`, `unnest`, `OPENJSON`, `JSON_TABLE`), one bind for any
count — and the fallback `IN (...)` anchor chunks by `membership_budget`.

## Findings table

| # | Fact | PostgreSQL | SQLite | MariaDB | SQL Server 2025 | Oracle 23ai |
|---|------|-----------|--------|---------|-----------------|-------------|
| 1 | Preamble SQLAlchemy emits for `cte(recursive=True)` (**EXECUTED**) | `WITH RECURSIVE` | `WITH RECURSIVE` | `WITH RECURSIVE` (mysql and mariadb dialects alike) | `WITH` (override) | `WITH` (override) |
| 1 | Column list rendered | yes `walk(id, depth)` | yes | yes | yes | yes (required by Oracle) |
| 2 | `UNION` between anchor and recursive member | allowed; dedups vs all prior result rows (**READ** executor) | allowed; dedups vs all rows ever queued (**READ** select.c; **EXECUTED**) | allowed (`UNION [DISTINCT]`) (**READ** docs) | **forbidden** — only `UNION ALL` (**READ** docs) | **forbidden** — only `UNION ALL` (**READ** docs) |
| 2 | Aggregates / GROUP BY / DISTINCT in recursive member | aggregate: not via subquery rule; (no explicit ban on GROUP BY found) `[NOT VERIFIED]` | aggregate forbidden (**EXECUTED**) | aggregate forbidden (error 4008) `[NOT VERIFIED: doc page lists no rules]` | DISTINCT, GROUP BY, HAVING, scalar aggregation, TOP forbidden | DISTINCT, GROUP BY, aggregate forbidden; analytic OK |
| 2 | Outer join | ref must not be on nullable side (**READ** parse_cte.c) | LEFT JOIN with CTE on left works (**EXECUTED**) | LEFT JOIN with ref on left fixed 10.2.5 (MDEV-12360) | **no LEFT/RIGHT/OUTER JOIN at all** | outer join with query_name as right table forbidden |
| 2 | Subquery / derived table referencing the CTE | forbidden | forbidden (**EXECUTED**) | forbidden (4008) | **all subqueries forbidden** | subquery referring to query_name forbidden |
| 2 | Derived table NOT referencing the CTE (three-seek `UNION ALL` subquery) | OK (compiles; legal per parse_cte rules) | OK (**EXECUTED**) | OK `[INFERRED]` | **not allowed** (subqueries banned) → use a sibling CTE | OK (**INFERRED** from rule text) |
| 2 | Multiple references to CTE in recursive member | forbidden | forbidden (**EXECUTED**) | `[NOT VERIFIED]` | "must refer only one time" | "exactly once" |
| 2 | ORDER BY / LIMIT inside the CTE body | forbidden | allowed (priority queue + stop) (**EXECUTED**) | `[NOT VERIFIED]` | TOP forbidden in recursive member | `[NOT VERIFIED]` |
| 3 | Cycle clause | `CYCLE col SET mark USING path` (14+), `SEARCH BREADTH FIRST BY col SET ord` | none | `CYCLE col RESTRICT` (10.5.2+, non-standard) | none; `OPTION (MAXRECURSION n)` | `CYCLE col SET mark TO v DEFAULT d`; `SEARCH BREADTH FIRST BY col SET ord`; error ORA-32044 on a cycle without it |
| 3 | Recursion cap | none | none | `max_recursive_iterations` default **1000** since 10.6; stops silently (MDEV-31214, fixed in 10.6.15 line) | default 100; error 530 at limit; `MAXRECURSION 0..32767` | none (cycle error instead) |
| 4 | Evaluation unit | whole working table per round (**READ** nodeRecursiveunion.c) | one row at a time, FIFO queue (**READ** select.c) | whole table per step (temp table of previous step) (**READ** MDEV-23406 commit) | one row at a time, **LIFO** stack spool (**READ** Kornelis) | per step `[NOT VERIFIED: docs silent]` |
| 4 | `depth` = BFS level? | yes, = round number | = path length; FIFO gives level order | = step number | = path length; emission order is depth-first | = step number |
| 4 | Node reached at depth 2 and 3 appears twice? | yes (rows differ) | yes (**EXECUTED**) | yes | yes | yes |
| 5 | Seed row source in anchor | `unnest(:array)` | `json_each(:json)` (**EXECUTED**) | `JSON_TABLE` | `OPENJSON` or `VALUES` | `JSON_TABLE` over CLOB |
| 5 | `IN (...)` anchor cap | bind budget 65,535 | 32,766 | 65,535 | 2,000 (profile) | **1,000** (ORA-01795) |
| 6 | Native hierarchical alternative | none | none | none | graph `MATCH`/`SHORTEST_PATH` — **needs `AS NODE`/`AS EDGE` tables**, not applicable | `CONNECT BY NOCYCLE ... LEVEL` — works but no advantage |
| 7 | fwd index `(source_id, edge_type)` usable in the step | yes (nested loop per working row) | yes (**EXECUTED** EXPLAIN) | yes, hash/ref join from temp table | yes, Nested Loops seek per row | yes `[INFERRED]` |

## 1. Syntax and what SQLAlchemy emits

**READ** `sqlalchemy:lib/sqlalchemy/sql/compiler.py:5533-5553` — `_render_cte_clause` computes
`ctes_recursive = any(cte.recursive for cte in ctes)` and calls `get_cte_preamble(recursive)`,
which returns `"WITH RECURSIVE"` or `"WITH"` (lines 5550-5553). `visit_cte` at lines
4499-4525 renders the column list `name(col, ...)` whenever `cte.recursive` is true (or
`name_cte_columns` is set).

**READ** overrides: `sqlalchemy:lib/sqlalchemy/dialects/mssql/base.py:2401-2406` and
`sqlalchemy:lib/sqlalchemy/dialects/oracle/base.py:1368-1369` — both return `"WITH"`
unconditionally. The MySQL dialect has no override; MariaDB is `MariaDBDialect(MySQLDialect)`
with `name = "mariadb"` (`sqlalchemy:lib/sqlalchemy/dialects/mysql/mariadb.py:34-41`), so it
inherits `WITH RECURSIVE`. SQLAlchemy models no recursion cap or cycle clause anywhere
(`grep -rn max_recursion lib/sqlalchemy` is empty — **EXECUTED**).

**EXECUTED** `experiments/r1_compile_cte.py` (full output appended below): all six dialects
compile `.union_all(step)` and `.union(step)` and the derived-table join shape without any
refusal. The only differences are the preamble, the `JOIN` vs `INNER JOIN` keyword (MySQL
family), and Oracle dropping `AS` before the derived-table alias.

## 2. Restrictions on the recursive member

PostgreSQL — **READ** `postgres:src/backend/parser/parse_cte.c:46-54` (the five
`recursion_errormsgs`: ref must not appear in the non-recursive term, within a subquery, within
an outer join, within INTERSECT, within EXCEPT); `:938-944` (must be `non-recursive-term UNION
[ALL] recursive-term`); `:975-995` (ORDER BY / OFFSET / LIMIT / FOR UPDATE on the recursive
query not implemented); `:1072-1076` (reference must not appear more than once);
`:1153-1176` (for LEFT JOIN only the right arg enters `RECURSION_OUTERJOIN` context, for
RIGHT only the left arg, for FULL both) — so `walk LEFT JOIN x` is legal, `x LEFT JOIN walk` is
not. A derived table that does not mention `walk` is fine; the SubLink rule only fires on a
self-reference inside it (`:1183-1190`).

SQLite — **READ** `sqlite:src/select.c:2677-2708` (algorithm comment), `:2815-2827` (recursive
aggregate not supported; terms are forced to `TK_ALL` and distinctness is enforced by the
`iDistinct` table), `:5815-5842` ("multiple references to recursive table"), `:5887-5889`
("multiple recursive references", "recursive reference in a subquery"). **EXECUTED**
`experiments/r1_sqlite_exec.py`: subquery reference → `circular reference: walk`; two
references → `multiple references to recursive table: walk`; aggregate → `recursive aggregate
queries not supported`; `walk LEFT JOIN vfs_edges` → works; a `UNION ALL` derived table
joined in the step → works; a sibling non-recursive CTE `visible` joined in the step → works;
`ORDER BY 2 LIMIT 6` inside the CTE → works (SQLite extension).

MariaDB — **READ** https://mariadb.com/docs/server/reference/sql-statements/data-manipulation/selecting-data/common-table-expressions/recursive-common-table-expressions-overview.md
and https://mariadb.com/kb/en/with/ : both `UNION` and `UNION ALL` are accepted; the overview
page lists no restriction table. Violations raise `ERROR 4008 (HY000): Restrictions imposed on
recursive definitions are violated for table '...'` (https://jira.mariadb.org/browse/MDEV-12360,
a `LEFT JOIN` with the recursive reference on the *left*, fixed 10.2.5;
https://jira.mariadb.org/browse/MDEV-15894, aggregates in the anchor, fixed 10.2). The MySQL
8.0 rule list (no GROUP BY, aggregates, ORDER BY, LIMIT, DISTINCT in the recursive SELECT) is
MySQL's, not MariaDB's `[NOT VERIFIED: MariaDB publishes no equivalent list; needs the engine
leg]`.

SQL Server — **READ** https://learn.microsoft.com/en-us/sql/t-sql/queries/with-common-table-expression-transact-sql
(verbatim): "`UNION ALL` is the only set operator allowed between the last anchor member and
first recursive member"; "The `FROM` clause of a recursive member must refer only one time to
the CTE *expression_name*"; not allowed in the recursive member: "`SELECT DISTINCT`, `GROUP
BY`, `PIVOT`, `HAVING`, Scalar aggregation, `TOP`, `LEFT`, `RIGHT`, `OUTER JOIN` (`INNER JOIN`
is allowed), Subqueries, A hint applied to a recursive reference". Also: "A CTE can reference
itself and previously defined CTEs in the same `WITH` clause. Forward referencing isn't
allowed." and "Query results from common table expressions aren't materialized. Each outer
reference to the named result set requires the defined query to be re-executed."
**Consequence for vfs:** the three-seek `union_all(...).subquery()` cannot sit inside the
recursive member on SQL Server (it is a subquery). The allowed form is a *sibling CTE* declared
before `walk` in the same `WITH` — but because CTEs are not materialized on SQL Server, the
visibility union is re-executed per Nested Loops probe unless it is spooled; measure, and keep
a `#temp`/table-variable arm as the fallback `[INFERRED]`.

Oracle — **READ** https://docs.oracle.com/en/database/oracle/oracle-database/23/sqlrf/SELECT.html
(verbatim): "The recursive member must follow the anchor member and must reference query_name
exactly once. You must combine the recursive member with the anchor member using the `UNION
ALL` set operator."; "The recursive member cannot contain any of the following elements: The
`DISTINCT` keyword or a `GROUP BY` clause; The model_clause; An aggregate function. However,
analytic functions are permitted in the select list; Subqueries that refer to query_name;
Outer joins that refer to query_name as the right table."; "Any query_name defined in the
subquery_factoring_clause can be used in any subsequent named query block" (sibling CTEs are
referenceable). "The number of column aliases following WITH query_name and the number of
columns in the SELECT lists of the anchor and recursive query blocks must be the same" — the
column list is mandatory, and SQLAlchemy renders it (**EXECUTED**).

## 3. Cycle and depth control

PostgreSQL — **READ** `postgres:doc/src/sgml/queries.sgml:2355-2383`: "Because we require a
'depth' output, just changing UNION ALL to UNION would not eliminate the looping." The doc's
answer is a visited array (`path`) with `is_cycle`, or the `CYCLE id SET is_cycle USING path`
clause (`:2442-2460`) and `SEARCH BREADTH FIRST BY id SET ordercol` (`:2334-2341`); the parser
handles them in `parse_cte.c:246-262` (`search_clause`, `cycle_clause`). Introduced in
PostgreSQL 14 `[READ from memory of the 14 release notes; the in-repo parser proves current
support]`.

SQLite — no `CYCLE`; `UNION` dedups full rows against the `iDistinct` table of everything ever
queued (`select.c:2691-2694`). **EXECUTED**: on a 1→2→3→1 cycle, `UNION` with no depth column
terminates (`[(1,),(2,),(4,),(3,),(5,),(6,)]`); with a depth column and bound 3, row `(1, 3)`
is emitted — the cycle row survives because the depth differs — and the bound is what stops it.

MariaDB — `CYCLE col RESTRICT` since 10.5.2 (https://mariadb.com/kb/en/with/: "With the use of
`CYCLE ... RESTRICT` it makes no difference whether the CTE uses `UNION ALL` or `UNION
DISTINCT` anymore"). `max_recursive_iterations` defaults to 1000 since 10.6 and at the limit
"it just stops execution and returns a result set without an error or a warning"
(https://jira.mariadb.org/browse/MDEV-31214; https://mariadb.com/kb/en/with-recursive-limited-to-1001-records).
This is a **silent truncation hazard**: a walk deeper than 1000 rounds would be cut without
notice. vfs's depth argument is far below that; the spec should still issue
`SET SESSION max_recursive_iterations = <max_depth + 1>` or at least assert the depth is under
the setting (`range_settings` already models per-read session statements).

SQL Server — server-wide default 100; `OPTION (MAXRECURSION 0..32767)` on the *outermost*
statement only ("The `OPTION` clause can't be used inside a CTE definition"). At the limit the
statement fails with error 530 "The statement terminated. The maximum recursion 100 has been
exhausted before statement completion." (https://mssqltips.com/sqlservertip/5111/fix-sql-server-cte-maximum-recursion-exhausted-error;
https://learn.microsoft.com/en-us/answers/a/105821). Per Kornelis the Assert fires only after a
match at level 101, so a walk whose depth bound is < 100 never trips it; a bound ≥ 100 needs
`OPTION (MAXRECURSION n)` appended — SQLAlchemy renders it with `.suffix_with(...)`
or `with_hint`; no dialect models it.

Oracle — without `CYCLE`, cyclic data raises `ORA-32044: cycle detected while executing
recursive WITH query` (https://oracle-base.com/articles/11g/recursive-subquery-factoring-11gr2;
https://docs.oracle.com/en/error-help/db/ora-32044). The doc's cycle definition: "a row forms a
cycle if one of its ancestor rows has the same values for all the columns in the column alias
list for query_name that are referenced in the WHERE clause of the recursive member."
**Consequence:** with `depth` in the WHERE clause (`walk.depth < :max_depth`) the compared
columns are `(id, depth)` — a revisit at a greater depth is *not* the same tuple, so no
ORA-32044 fires and the depth bound terminates the walk `[INFERRED from the doc sentence;
verify on the Oracle leg]`. Adding `CYCLE id SET is_cycle TO '1' DEFAULT '0'` is a cheap
belt-and-braces on Oracle.

**Portable floor.** A hard depth bound in the recursive member is the only termination
mechanism all five accept. Three patterns, strongest-portable first:
1. `WHERE walk.depth < :max_depth` — every engine; output bounded by Σ fan-out^k; duplicates
   by path. Outer `SELECT id, MIN(depth) ... GROUP BY id` (aggregation *outside* the CTE is
   legal everywhere) collapses to one row per node with its shortest depth.
2. Path-string visited check (`instr(trail, ',' || id || ',') = 0`, **EXECUTED** on SQLite)
   — cuts cycles per path on every engine (PostgreSQL arrays, MariaDB `FIND_IN_SET`, SQL
   Server/Oracle string concat); still one row per simple path, and the string grows with
   depth (`VARCHAR` caps on Oracle/SQL Server).
3. App-side frontier loop — one statement per level (`SELECT target_id FROM edges JOIN
   visible WHERE source_id IN (frontier)`), Python holds the visited set. True id-dedup, true
   BFS level, chunked by `membership_budget`; costs `depth` round trips.
Engines that can push visited-dedup into the CTE: **none** when a depth column is carried
(the standard `CYCLE` clause and PostgreSQL/SQLite `UNION` compare the path or the full row,
not the id). Without a depth column, PostgreSQL, SQLite and MariaDB `UNION` do dedup by id.

## 4. Breadth-first semantics

PostgreSQL — **READ** `postgres:src/backend/executor/nodeRecursiveunion.c:81-170`: the
non-recursive term fills `working_table`; each recursive pass reads the working table, writes
`intermediate_table`, then swaps them (`:137-141`); for `UNION`, every candidate is checked
against one `hashtable` that holds *all* rows ever emitted (`:102-108`, `:156-162`), so dedup is
against the whole result so far. `depth` = round number. A node reached at depth 2 and 3 is two
distinct tuples and appears twice. Working tables are `tuplestore`s under `work_mem` (`:205-206`).

SQLite — **READ** `select.c:2683-2700`: "Rows are extracted from the Queue table one by one.
... the single extracted row ... becomes the content of the recursive-table for a
recursive-query run. ... Without an ORDER BY, the Queue table is just a FIFO." So the step runs
once per row, not per level; FIFO still yields level order (**EXECUTED**: `(1,0),(2,0)` then all
depth-1 rows then depth-2). `UNION` dedups against the `iDistinct` set of all rows ever queued.
Duplicate `(5, 2)` appeared twice via two paths (**EXECUTED**).

MariaDB — **READ** commit message of MDEV-23406 (Babaev, 2020): "For each recursive table
reference a temporary table is created that contains all rows generated for the corresponding
recursive CTE table on the previous step of recursion." → per-step evaluation, `depth` = step.
`UNION DISTINCT` dedup scope: the docs say "UNION excludes nodes that are already present"
(overview page) — **INFERRED** whole-result scope from the materialized temp table with a
unique index `[NOT VERIFIED: needs the MariaDB leg]`.

SQL Server — **READ** https://sqlserverfast.com/blog/hugo/2018/12/plansplaining-part-9-recursive-ctes/:
stack spool = Index Spool (lazy, With Stack) + Table Spool (With Stack); the Table Spool
"remove[s] the previously read row from the worktable and then read[s] the row with the
highest key value" — LIFO, one row per Nested Loops probe. The doc's own note says "each
iteration using the previous iteration's output as its input" and "UNION ALL doesn't
deduplicate rows during each recursive step". So `depth` is path length; the emission order is
depth-first; the result set is identical to the others, only the order differs.

Oracle — docs do not describe the executor; `SEARCH BREADTH FIRST BY ... SET ord` gives a
BFS *ordering column*; `depth` carried by hand is still path length `[NOT VERIFIED]`.

**Conclusion for the spec:** on every engine, the same node can appear once per distinct path
and per depth. Normalize in the outer query (`GROUP BY id` with `MIN(depth)`), or in Python.

## 5. Seeds as bind parameters

**READ** `vfs:src/vfs/storage/backends/database/ranges.py:278-320` — `point_rows` turns a
bound list into rows per `RangeSource`: `unnest(ARRAY bind)` (Postgres), `json_each(json)`
(SQLite), `openjson(json)` (SQL Server), `JSON_TABLE` (MariaDB, cast to bytes), `JSON_TABLE`
over a CLOB bind (Oracle, "so any number of ranges travels"). `dialects.py:366` declares
`range_source` per profile; `membership.py:56-60` is the other form (`IN` list, or on SQL
Server `IN (SELECT v FROM (VALUES ...) keys)` because `membership="values"`).

The anchor is an ordinary SELECT on every engine, so **the same row source feeds it**:
`SELECT e.id, 0 FROM <points rows> s JOIN vfs_entries e ON e.id = s.value WHERE e.deleted_at
IS NULL AND <visible>` — **EXECUTED** on SQLite with `json_each(?)` (`[(1,0),(2,0),...]`). The
seed value is an integer id here rather than a path; `point_rows` types the column as text
(`collate(..., "C")`, `cast(..., LargeBinary)`), so the spec needs an integer-typed sibling
(`seed_rows`) or seeds by path through the existing `point_rows` joined on `path`. The JSON
and array forms are **one bind parameter regardless of seed count**, so a 10,000-seed anchor
does not touch the Oracle 1,000-element cap or the SQL Server 2,100-parameter cap. On SQL
Server the `VALUES` derived table is also legal in the *anchor* (subqueries are banned only in
the recursive member).

Fallback (`range_source is None`, the GENERIC floor): `id IN (:s1..:sn)` chunked by
`membership_budget(profile, parameter_budget)` (`dialects.py:651-658`; Oracle 1,000). Run the
whole CTE once per chunk and merge in Python with a `(id → min depth)` dict. Correctness is
unaffected (the walk from a seed subset is a subset of the walk from all seeds; the union over
chunks equals the walk from all seeds; only depths need `min`). Cost is k statements, each
re-walking shared neighbourhoods — acceptable for the floor, which no supported engine uses.

## 6. Native hierarchical alternatives

SQL Server graph: **READ** https://learn.microsoft.com/en-us/sql/t-sql/queries/match-sql-graph:
"MATCH can be used only with graph node and edge tables" (tables created `AS NODE` / `AS
EDGE` with `$node_id`); `SHORTEST_PATH` (2019+) "returns only one shortest path", unweighted,
quantifiers `+` and `{1,n}` only. Not applicable to `vfs_edges`; a graph-table mirror would be
a second schema. **Not worth an arm.**

Oracle `CONNECT BY`: **READ** https://docs.oracle.com/en/database/oracle/oracle-database/23/sqlrf/Hierarchical-Queries.html:
`START WITH ... CONNECT BY NOCYCLE PRIOR ... AND LEVEL <= n`, loop without NOCYCLE →
`ORA-01436`; "A join, if present, is evaluated first" — the rights join would be evaluated
before the walk, which is fine semantically. Oracle itself says recursive WITH is "more
powerful than CONNECT BY". No advantage; **one shape serves all five.**

PostgreSQL: none. SQLite: none. MariaDB: none.

## 7. Performance facts

- PostgreSQL: working/intermediate tables are `tuplestore`s bounded by `work_mem`, spilling
  to disk (`nodeRecursiveunion.c:205-206`); the recursive term is re-planned per round via
  `chgParam` (`:146-147`) and joins `WorkTableScan → vfs_edges` — an index nested loop on
  `(source_id, edge_type)` when the working table is small, hash join when large; the planner
  has no row estimate for the work table (constant guess), a known pitfall `[READ from memory
  of planner behaviour; NOT VERIFIED here]`.
- SQLite: **EXECUTED** EXPLAIN QUERY PLAN — `RECURSIVE STEP: SCAN walk; SEARCH g USING
  COVERING INDEX ... (source_id=?); SEARCH e USING INTEGER PRIMARY KEY`. The fwd index drives
  per queued row.
- MariaDB: per-step temp table materialization (MDEV-23406 commit text); `UNION DISTINCT`
  costs a unique-index probe per candidate row; the dedicated `range_join="STRAIGHT_JOIN"` /
  `FORCE INDEX` findings for the visibility join (`dialects.py:233-250`) will apply inside the
  step too `[INFERRED]`.
- SQL Server: row-at-a-time stack spool with Nested Loops; "The stack spool does not support
  parallel execution" (search summary); CTEs are not materialized, so a sibling visibility CTE
  is re-run per probe unless spooled. A SQLServerCentral measurement reports recursive CTEs
  "more than 50% slower than the traditional loop method" for multi-child descents
  (https://www.sqlservercentral.com/articles/cte-performance) — the app-side frontier loop is
  a credible arm there.
- Oracle: recursive member can run in parallel since 12.2 (doc); `CARDINALITY` hints on the
  JSON_TABLE seed source are already a profile fact (`range_hints`) and will be needed in the
  anchor `[INFERRED]`.

## Open questions

1. MariaDB's exact restriction list for the recursive part (ORDER BY, LIMIT, DISTINCT) —
   run on the MariaDB leg. 2. Oracle: confirm that `(id, depth)` in the WHERE clause means no
   ORA-32044 on a cycle under a depth bound. 3. SQL Server: sibling visibility CTE vs
   `#temp` cost per probe. 4. Whether `SEARCH BREADTH FIRST` / `CYCLE` are worth emitting on
   PostgreSQL/Oracle given the outer `GROUP BY id` normalization already needed everywhere.

## What the spec should pin

Facts SQLAlchemy does **not** model (candidates for `DialectProfile`):

| Field | Values | Why |
|-------|--------|-----|
| `recursive_set_op` | `"union_all"` everywhere | SQL Server and Oracle refuse `UNION`; pin one form, no field needed. |
| `recursion_cap` | `None` (PG, SQLite, Oracle), `("session", "max_recursive_iterations")` (MariaDB), `("statement", "OPTION (MAXRECURSION {n})")` (SQL Server) | the statement must set the cap ≥ max_depth+1 or the engine truncates (MariaDB, silently) or errors (SQL Server 530). |
| `recursive_subquery` | `True` except SQL Server | decides whether the three-seek union is inlined as a derived table or hoisted to a sibling CTE (`range_fence` already makes Postgres a CTE). |
| `cycle_clause` | `None` / `"pg"` / `"oracle"` / `"mariadb_restrict"` | optional belt-and-braces; not required for termination. |
| seed source | reuse `range_source` | one bind for any seed count; integer-typed variant of `point_rows`. |

Already modelled by SQLAlchemy (do not duplicate): the preamble keyword, the column list,
the bind-parameter budget (`insertmanyvalues_max_parameters`), join keywords.

**The one portable statement shape:**

```
WITH [RECURSIVE] [visible AS (<three-seek UNION ALL>),]      -- sibling CTE where subqueries are banned
walk(id, depth) AS (
  SELECT e.id, 0 FROM <seed rows: range_source> s
    JOIN vfs_entries e ON e.id = s.value
    JOIN visible v ON v.entry_id = e.id              -- rights on the seeds too
  WHERE e.deleted_at IS NULL
  UNION ALL
  SELECT e.id, walk.depth + 1
  FROM walk
    JOIN vfs_edges g ON g.source_id = walk.id AND g.edge_type = :t   -- or target_id for the reverse direction
    JOIN vfs_entries e ON e.id = g.target_id
    JOIN visible v ON v.entry_id = e.id              -- a hidden node is absent and nothing is reached through it
  WHERE e.deleted_at IS NULL AND walk.depth < :max_depth
)
SELECT id, MIN(depth) AS depth FROM walk GROUP BY id   -- one row per node, shortest depth
[OPTION (MAXRECURSION n)]                              -- SQL Server only, when max_depth >= 100
```

Inner joins only, one reference to `walk`, no aggregates/DISTINCT/ORDER BY/LIMIT inside,
depth bound inside the step, normalization outside. This compiles on all six SQLAlchemy
dialects today (**EXECUTED**) and is legal under every restriction list above (**READ**).

---

## Appendix A — `experiments/r1_compile_cte.py` output (verbatim, EXECUTED)

```
SQLAlchemy 2.0.52
==============================================================================
SHAPE: UNION ALL
------------------------------------------------------------------------------
[postgresql] (dialect.name='postgresql')
WITH RECURSIVE walk(id, depth) AS 
(SELECT vfs_entries.id AS id, %(param_1)s AS depth 
FROM vfs_entries 
WHERE vfs_entries.id IN (%(seeds_1)s, %(seeds_2)s, %(seeds_3)s) AND vfs_entries.deleted_at IS NULL UNION ALL SELECT vfs_entries.id AS id, walk.depth + %(depth_1)s AS depth 
FROM walk JOIN vfs_edges ON vfs_edges.source_id = walk.id JOIN vfs_entries ON vfs_entries.id = vfs_edges.target_id 
WHERE vfs_edges.edge_type = %(edge_type)s AND vfs_entries.deleted_at IS NULL AND walk.depth < %(max_depth)s)
 SELECT walk.id, walk.depth 
FROM walk
------------------------------------------------------------------------------
[sqlite] (dialect.name='sqlite')
WITH RECURSIVE walk(id, depth) AS 
(SELECT vfs_entries.id AS id, ? AS depth 
FROM vfs_entries 
WHERE vfs_entries.id IN (?, ?, ?) AND vfs_entries.deleted_at IS NULL UNION ALL SELECT vfs_entries.id AS id, walk.depth + ? AS depth 
FROM walk JOIN vfs_edges ON vfs_edges.source_id = walk.id JOIN vfs_entries ON vfs_entries.id = vfs_edges.target_id 
WHERE vfs_edges.edge_type = ? AND vfs_entries.deleted_at IS NULL AND walk.depth < ?)
 SELECT walk.id, walk.depth 
FROM walk
------------------------------------------------------------------------------
[mysql] (dialect.name='mysql')
WITH RECURSIVE walk(id, depth) AS 
(SELECT vfs_entries.id AS id, %s AS depth 
FROM vfs_entries 
WHERE vfs_entries.id IN (%s, %s, %s) AND vfs_entries.deleted_at IS NULL UNION ALL SELECT vfs_entries.id AS id, walk.depth + %s AS depth 
FROM walk INNER JOIN vfs_edges ON vfs_edges.source_id = walk.id INNER JOIN vfs_entries ON vfs_entries.id = vfs_edges.target_id 
WHERE vfs_edges.edge_type = %s AND vfs_entries.deleted_at IS NULL AND walk.depth < %s)
 SELECT walk.id, walk.depth 
FROM walk
------------------------------------------------------------------------------
[mariadb] (dialect.name='mariadb')
WITH RECURSIVE walk(id, depth) AS 
(SELECT vfs_entries.id AS id, %s AS depth 
FROM vfs_entries 
WHERE vfs_entries.id IN (%s, %s, %s) AND vfs_entries.deleted_at IS NULL UNION ALL SELECT vfs_entries.id AS id, walk.depth + %s AS depth 
FROM walk INNER JOIN vfs_edges ON vfs_edges.source_id = walk.id INNER JOIN vfs_entries ON vfs_entries.id = vfs_edges.target_id 
WHERE vfs_edges.edge_type = %s AND vfs_entries.deleted_at IS NULL AND walk.depth < %s)
 SELECT walk.id, walk.depth 
FROM walk
------------------------------------------------------------------------------
[mssql] (dialect.name='mssql')
WITH walk(id, depth) AS 
(SELECT vfs_entries.id AS id, :param_1 AS depth 
FROM vfs_entries 
WHERE vfs_entries.id IN (:seeds_1, :seeds_2, :seeds_3) AND vfs_entries.deleted_at IS NULL UNION ALL SELECT vfs_entries.id AS id, walk.depth + :depth_1 AS depth 
FROM walk JOIN vfs_edges ON vfs_edges.source_id = walk.id JOIN vfs_entries ON vfs_entries.id = vfs_edges.target_id 
WHERE vfs_edges.edge_type = :edge_type AND vfs_entries.deleted_at IS NULL AND walk.depth < :max_depth)
 SELECT walk.id, walk.depth 
FROM walk
------------------------------------------------------------------------------
[oracle] (dialect.name='oracle')
WITH walk(id, depth) AS 
(SELECT vfs_entries.id AS id, :param_1 AS depth 
FROM vfs_entries 
WHERE vfs_entries.id IN (:seeds_1, :seeds_2, :seeds_3) AND vfs_entries.deleted_at IS NULL UNION ALL SELECT vfs_entries.id AS id, walk.depth + :depth_1 AS depth 
FROM walk JOIN vfs_edges ON vfs_edges.source_id = walk.id JOIN vfs_entries ON vfs_entries.id = vfs_edges.target_id 
WHERE vfs_edges.edge_type = :edge_type AND vfs_entries.deleted_at IS NULL AND walk.depth < :max_depth)
 SELECT walk.id, walk.depth 
FROM walk
==============================================================================
SHAPE: UNION
------------------------------------------------------------------------------
[postgresql] (dialect.name='postgresql')
WITH RECURSIVE walk(id, depth) AS 
(SELECT vfs_entries.id AS id, %(param_1)s AS depth 
FROM vfs_entries 
WHERE vfs_entries.id IN (%(seeds_1)s, %(seeds_2)s, %(seeds_3)s) AND vfs_entries.deleted_at IS NULL UNION SELECT vfs_entries.id AS id, walk.depth + %(depth_1)s AS depth 
FROM walk JOIN vfs_edges ON vfs_edges.source_id = walk.id JOIN vfs_entries ON vfs_entries.id = vfs_edges.target_id 
WHERE vfs_edges.edge_type = %(edge_type)s AND vfs_entries.deleted_at IS NULL AND walk.depth < %(max_depth)s)
 SELECT walk.id, walk.depth 
FROM walk
------------------------------------------------------------------------------
[sqlite] (dialect.name='sqlite')
WITH RECURSIVE walk(id, depth) AS 
(SELECT vfs_entries.id AS id, ? AS depth 
FROM vfs_entries 
WHERE vfs_entries.id IN (?, ?, ?) AND vfs_entries.deleted_at IS NULL UNION SELECT vfs_entries.id AS id, walk.depth + ? AS depth 
FROM walk JOIN vfs_edges ON vfs_edges.source_id = walk.id JOIN vfs_entries ON vfs_entries.id = vfs_edges.target_id 
WHERE vfs_edges.edge_type = ? AND vfs_entries.deleted_at IS NULL AND walk.depth < ?)
 SELECT walk.id, walk.depth 
FROM walk
------------------------------------------------------------------------------
[mysql] (dialect.name='mysql')
WITH RECURSIVE walk(id, depth) AS 
(SELECT vfs_entries.id AS id, %s AS depth 
FROM vfs_entries 
WHERE vfs_entries.id IN (%s, %s, %s) AND vfs_entries.deleted_at IS NULL UNION SELECT vfs_entries.id AS id, walk.depth + %s AS depth 
FROM walk INNER JOIN vfs_edges ON vfs_edges.source_id = walk.id INNER JOIN vfs_entries ON vfs_entries.id = vfs_edges.target_id 
WHERE vfs_edges.edge_type = %s AND vfs_entries.deleted_at IS NULL AND walk.depth < %s)
 SELECT walk.id, walk.depth 
FROM walk
------------------------------------------------------------------------------
[mariadb] (dialect.name='mariadb')
WITH RECURSIVE walk(id, depth) AS 
(SELECT vfs_entries.id AS id, %s AS depth 
FROM vfs_entries 
WHERE vfs_entries.id IN (%s, %s, %s) AND vfs_entries.deleted_at IS NULL UNION SELECT vfs_entries.id AS id, walk.depth + %s AS depth 
FROM walk INNER JOIN vfs_edges ON vfs_edges.source_id = walk.id INNER JOIN vfs_entries ON vfs_entries.id = vfs_edges.target_id 
WHERE vfs_edges.edge_type = %s AND vfs_entries.deleted_at IS NULL AND walk.depth < %s)
 SELECT walk.id, walk.depth 
FROM walk
------------------------------------------------------------------------------
[mssql] (dialect.name='mssql')
WITH walk(id, depth) AS 
(SELECT vfs_entries.id AS id, :param_1 AS depth 
FROM vfs_entries 
WHERE vfs_entries.id IN (:seeds_1, :seeds_2, :seeds_3) AND vfs_entries.deleted_at IS NULL UNION SELECT vfs_entries.id AS id, walk.depth + :depth_1 AS depth 
FROM walk JOIN vfs_edges ON vfs_edges.source_id = walk.id JOIN vfs_entries ON vfs_entries.id = vfs_edges.target_id 
WHERE vfs_edges.edge_type = :edge_type AND vfs_entries.deleted_at IS NULL AND walk.depth < :max_depth)
 SELECT walk.id, walk.depth 
FROM walk
------------------------------------------------------------------------------
[oracle] (dialect.name='oracle')
WITH walk(id, depth) AS 
(SELECT vfs_entries.id AS id, :param_1 AS depth 
FROM vfs_entries 
WHERE vfs_entries.id IN (:seeds_1, :seeds_2, :seeds_3) AND vfs_entries.deleted_at IS NULL UNION SELECT vfs_entries.id AS id, walk.depth + :depth_1 AS depth 
FROM walk JOIN vfs_edges ON vfs_edges.source_id = walk.id JOIN vfs_entries ON vfs_entries.id = vfs_edges.target_id 
WHERE vfs_edges.edge_type = :edge_type AND vfs_entries.deleted_at IS NULL AND walk.depth < :max_depth)
 SELECT walk.id, walk.depth 
FROM walk
==============================================================================
SHAPE: UNION ALL + join to union_all(...).subquery() derived table
------------------------------------------------------------------------------
[postgresql] (dialect.name='postgresql')
WITH RECURSIVE walk(id, depth) AS 
(SELECT vfs_entries.id AS id, %(param_1)s AS depth 
FROM vfs_entries 
WHERE vfs_entries.id IN (%(seeds_1)s, %(seeds_2)s, %(seeds_3)s) AND vfs_entries.deleted_at IS NULL UNION ALL SELECT vfs_entries.id AS id, walk.depth + %(depth_1)s AS depth 
FROM walk JOIN vfs_edges ON vfs_edges.source_id = walk.id JOIN vfs_entries ON vfs_entries.id = vfs_edges.target_id JOIN (SELECT vfs_entries.id AS entry_id 
FROM vfs_entries 
WHERE vfs_entries.everyone_level >= %(need)s UNION ALL SELECT vfs_entries.id AS entry_id 
FROM vfs_entries 
WHERE vfs_entries.path = %(point)s) AS visible ON visible.entry_id = vfs_entries.id 
WHERE vfs_edges.edge_type = %(edge_type)s AND vfs_entries.deleted_at IS NULL AND walk.depth < %(max_depth)s)
 SELECT walk.id, walk.depth 
FROM walk
------------------------------------------------------------------------------
[sqlite] (dialect.name='sqlite')
WITH RECURSIVE walk(id, depth) AS 
(SELECT vfs_entries.id AS id, ? AS depth 
FROM vfs_entries 
WHERE vfs_entries.id IN (?, ?, ?) AND vfs_entries.deleted_at IS NULL UNION ALL SELECT vfs_entries.id AS id, walk.depth + ? AS depth 
FROM walk JOIN vfs_edges ON vfs_edges.source_id = walk.id JOIN vfs_entries ON vfs_entries.id = vfs_edges.target_id JOIN (SELECT vfs_entries.id AS entry_id 
FROM vfs_entries 
WHERE vfs_entries.everyone_level >= ? UNION ALL SELECT vfs_entries.id AS entry_id 
FROM vfs_entries 
WHERE vfs_entries.path = ?) AS visible ON visible.entry_id = vfs_entries.id 
WHERE vfs_edges.edge_type = ? AND vfs_entries.deleted_at IS NULL AND walk.depth < ?)
 SELECT walk.id, walk.depth 
FROM walk
------------------------------------------------------------------------------
[mysql] (dialect.name='mysql')
WITH RECURSIVE walk(id, depth) AS 
(SELECT vfs_entries.id AS id, %s AS depth 
FROM vfs_entries 
WHERE vfs_entries.id IN (%s, %s, %s) AND vfs_entries.deleted_at IS NULL UNION ALL SELECT vfs_entries.id AS id, walk.depth + %s AS depth 
FROM walk INNER JOIN vfs_edges ON vfs_edges.source_id = walk.id INNER JOIN vfs_entries ON vfs_entries.id = vfs_edges.target_id INNER JOIN (SELECT vfs_entries.id AS entry_id 
FROM vfs_entries 
WHERE vfs_entries.everyone_level >= %s UNION ALL SELECT vfs_entries.id AS entry_id 
FROM vfs_entries 
WHERE vfs_entries.path = %s) AS visible ON visible.entry_id = vfs_entries.id 
WHERE vfs_edges.edge_type = %s AND vfs_entries.deleted_at IS NULL AND walk.depth < %s)
 SELECT walk.id, walk.depth 
FROM walk
------------------------------------------------------------------------------
[mariadb] (dialect.name='mariadb')
WITH RECURSIVE walk(id, depth) AS 
(SELECT vfs_entries.id AS id, %s AS depth 
FROM vfs_entries 
WHERE vfs_entries.id IN (%s, %s, %s) AND vfs_entries.deleted_at IS NULL UNION ALL SELECT vfs_entries.id AS id, walk.depth + %s AS depth 
FROM walk INNER JOIN vfs_edges ON vfs_edges.source_id = walk.id INNER JOIN vfs_entries ON vfs_entries.id = vfs_edges.target_id INNER JOIN (SELECT vfs_entries.id AS entry_id 
FROM vfs_entries 
WHERE vfs_entries.everyone_level >= %s UNION ALL SELECT vfs_entries.id AS entry_id 
FROM vfs_entries 
WHERE vfs_entries.path = %s) AS visible ON visible.entry_id = vfs_entries.id 
WHERE vfs_edges.edge_type = %s AND vfs_entries.deleted_at IS NULL AND walk.depth < %s)
 SELECT walk.id, walk.depth 
FROM walk
------------------------------------------------------------------------------
[mssql] (dialect.name='mssql')
WITH walk(id, depth) AS 
(SELECT vfs_entries.id AS id, :param_1 AS depth 
FROM vfs_entries 
WHERE vfs_entries.id IN (:seeds_1, :seeds_2, :seeds_3) AND vfs_entries.deleted_at IS NULL UNION ALL SELECT vfs_entries.id AS id, walk.depth + :depth_1 AS depth 
FROM walk JOIN vfs_edges ON vfs_edges.source_id = walk.id JOIN vfs_entries ON vfs_entries.id = vfs_edges.target_id JOIN (SELECT vfs_entries.id AS entry_id 
FROM vfs_entries 
WHERE vfs_entries.everyone_level >= :need UNION ALL SELECT vfs_entries.id AS entry_id 
FROM vfs_entries 
WHERE vfs_entries.path = :point) AS visible ON visible.entry_id = vfs_entries.id 
WHERE vfs_edges.edge_type = :edge_type AND vfs_entries.deleted_at IS NULL AND walk.depth < :max_depth)
 SELECT walk.id, walk.depth 
FROM walk
------------------------------------------------------------------------------
[oracle] (dialect.name='oracle')
WITH walk(id, depth) AS 
(SELECT vfs_entries.id AS id, :param_1 AS depth 
FROM vfs_entries 
WHERE vfs_entries.id IN (:seeds_1, :seeds_2, :seeds_3) AND vfs_entries.deleted_at IS NULL UNION ALL SELECT vfs_entries.id AS id, walk.depth + :depth_1 AS depth 
FROM walk JOIN vfs_edges ON vfs_edges.source_id = walk.id JOIN vfs_entries ON vfs_entries.id = vfs_edges.target_id JOIN (SELECT vfs_entries.id AS entry_id 
FROM vfs_entries 
WHERE vfs_entries.everyone_level >= :need UNION ALL SELECT vfs_entries.id AS entry_id 
FROM vfs_entries 
WHERE vfs_entries.path = :point) visible ON visible.entry_id = vfs_entries.id 
WHERE vfs_edges.edge_type = :edge_type AND vfs_entries.deleted_at IS NULL AND walk.depth < :max_depth)
 SELECT walk.id, walk.depth 
FROM walk
```

## Appendix B — `experiments/r1_sqlite_exec.py` output (verbatim, EXECUTED)

```
sqlite 3.50.4

## UNION + depth, hard bound 3 (depth makes cycle rows distinct)
WITH RECURSIVE walk(id, depth) AS (
  SELECT id, 0 FROM vfs_entries WHERE id IN (1) AND deleted_at IS NULL
  UNION
  SELECT e.id, walk.depth + 1 FROM walk JOIN vfs_edges g ON g.source_id = walk.id AND g.edge_type = 'x'
  JOIN vfs_entries e ON e.id = g.target_id WHERE e.deleted_at IS NULL AND e.everyone_level >= 1 AND walk.depth < 3)
SELECT id, depth FROM walk
-> [(1, 0), (2, 1), (3, 2), (5, 2), (1, 3)]

## UNION, no depth column, no bound: UNION dedup terminates the cycle
WITH RECURSIVE walk(id) AS (
  SELECT id FROM vfs_entries WHERE id IN (1)
  UNION
  SELECT g.target_id FROM walk JOIN vfs_edges g ON g.source_id = walk.id)
SELECT id FROM walk
-> [(1,), (2,), (4,), (3,), (5,), (6,)]

## UNION ALL + depth bound 2: output order (FIFO queue = BFS by level?)
WITH RECURSIVE walk(id, depth) AS (
  SELECT id, 0 FROM vfs_entries WHERE id IN (1, 2)
  UNION ALL
  SELECT g.target_id, walk.depth + 1 FROM walk JOIN vfs_edges g ON g.source_id = walk.id WHERE walk.depth < 2)
SELECT id, depth FROM walk
-> [(1, 0), (2, 0), (2, 1), (4, 1), (3, 1), (5, 1), (3, 2), (5, 2), (5, 2), (1, 2), (6, 2)]

## Visited check via path string (portable floor): node 5 once per distinct path, cycle cut
WITH RECURSIVE walk(id, depth, trail) AS (
  SELECT id, 0, ',' || id || ',' FROM vfs_entries WHERE id IN (1)
  UNION ALL
  SELECT g.target_id, walk.depth + 1, walk.trail || g.target_id || ','
  FROM walk JOIN vfs_edges g ON g.source_id = walk.id
  WHERE walk.depth < 10 AND instr(walk.trail, ',' || g.target_id || ',') = 0)
SELECT id, depth, trail FROM walk
-> [(1, 0, ',1,'), (2, 1, ',1,2,'), (4, 1, ',1,4,'), (3, 2, ',1,2,3,'), (5, 2, ',1,2,5,'), (5, 2, ',1,4,5,'), (6, 3, ',1,2,3,6,')]

## Recursive member joins a UNION ALL derived table (three-seek shape)
WITH RECURSIVE walk(id, depth) AS (
  SELECT id, 0 FROM vfs_entries WHERE id IN (1)
  UNION ALL
  SELECT e.id, walk.depth + 1 FROM walk JOIN vfs_edges g ON g.source_id = walk.id
  JOIN vfs_entries e ON e.id = g.target_id
  JOIN (SELECT id AS entry_id FROM vfs_entries WHERE everyone_level >= 1
        UNION ALL SELECT id FROM vfs_entries WHERE path = '/zzz') v ON v.entry_id = e.id
  WHERE e.deleted_at IS NULL AND walk.depth < 2)
SELECT id, depth FROM walk
-> [(1, 0), (2, 1), (3, 2), (5, 2)]

## Recursive member joins a second (non-recursive) CTE 'visible'
WITH RECURSIVE visible(entry_id) AS (SELECT id FROM vfs_entries WHERE everyone_level >= 1),
walk(id, depth) AS (
  SELECT id, 0 FROM vfs_entries WHERE id IN (1)
  UNION ALL
  SELECT e.id, walk.depth + 1 FROM walk JOIN vfs_edges g ON g.source_id = walk.id
  JOIN vfs_entries e ON e.id = g.target_id JOIN visible v ON v.entry_id = e.id
  WHERE e.deleted_at IS NULL AND walk.depth < 2)
SELECT id, depth FROM walk
-> [(1, 0), (2, 1), (3, 2), (5, 2)]

## Recursive reference inside a subquery (expect error)
WITH RECURSIVE walk(id) AS (
  SELECT 1 UNION SELECT target_id FROM vfs_edges WHERE source_id IN (SELECT id FROM walk))
SELECT * FROM walk
-> ERROR: circular reference: walk

## Two references to the recursive table (expect error)
WITH RECURSIVE walk(id) AS (
  SELECT 1 UNION SELECT g.target_id FROM walk w1 JOIN vfs_edges g ON g.source_id = w1.id JOIN walk w2 ON w2.id = g.target_id)
SELECT * FROM walk
-> ERROR: multiple references to recursive table: walk

## Aggregate in recursive member (expect error)
WITH RECURSIVE walk(id) AS (
  SELECT 1 UNION SELECT max(g.target_id) FROM walk JOIN vfs_edges g ON g.source_id = walk.id)
SELECT * FROM walk
-> ERROR: recursive aggregate queries not supported

## LEFT JOIN with the CTE on the left (allowed?)
WITH RECURSIVE walk(id, depth) AS (
  SELECT 1, 0 UNION ALL SELECT g.target_id, walk.depth+1 FROM walk LEFT JOIN vfs_edges g ON g.source_id = walk.id WHERE walk.depth < 1)
SELECT * FROM walk
-> [(1, 0), (2, 1), (4, 1)]

## ORDER BY depth + LIMIT inside the recursive CTE (SQLite extension)
WITH RECURSIVE walk(id, depth) AS (
  SELECT 1, 0 UNION ALL SELECT g.target_id, walk.depth+1 FROM walk JOIN vfs_edges g ON g.source_id = walk.id WHERE walk.depth < 5
  ORDER BY 2 LIMIT 6)
SELECT * FROM walk
-> [(1, 0), (2, 1), (4, 1), (3, 2), (5, 2), (5, 2)]

## Anchor from json_each (bound seed list unpacked)
WITH RECURSIVE walk(id, depth) AS (
  SELECT e.id, 0 FROM json_each(?) s JOIN vfs_entries e ON e.id = s.value
  UNION ALL SELECT g.target_id, walk.depth+1 FROM walk JOIN vfs_edges g ON g.source_id = walk.id WHERE walk.depth < 1)
SELECT * FROM walk
-> [(1, 0), (2, 0), (2, 1), (4, 1), (3, 1), (5, 1)]

## EXPLAIN QUERY PLAN: is fwd index used inside the recursive step?
EXPLAIN QUERY PLAN WITH RECURSIVE walk(id, depth) AS (
  SELECT id, 0 FROM vfs_entries WHERE id IN (1)
  UNION ALL
  SELECT e.id, walk.depth + 1 FROM walk JOIN vfs_edges g ON g.source_id = walk.id AND g.edge_type = 'x'
  JOIN vfs_entries e ON e.id = g.target_id WHERE e.deleted_at IS NULL AND walk.depth < 3)
SELECT id, depth FROM walk
-> [(2, 0, 0, 'CO-ROUTINE walk'), (5, 2, 0, 'SETUP'), (7, 5, 33, 'SEARCH vfs_entries USING INTEGER PRIMARY KEY (rowid=?)'), (22, 2, 0, 'RECURSIVE STEP'), (25, 22, 216, 'SCAN walk'), (28, 22, 56, 'SEARCH g USING COVERING INDEX sqlite_autoindex_vfs_edges_1 (source_id=?)'), (36, 22, 45, 'SEARCH e USING INTEGER PRIMARY KEY (rowid=?)'), (50, 0, 246, 'SCAN walk')]
```
