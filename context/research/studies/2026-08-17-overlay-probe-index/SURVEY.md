# Survey: partial/filtered index for the `NOT encoded` emptiness probe

Date: 2026-08-17. Scope: vfs `vfs` entries table, 10^5–10^8 rows, nearly all
`encoded = true`; every-call probe asks "does any row with `NOT encoded`
exist?" and must stay effectively O(1). Bulk ETL flips `encoded` false→true in
10k+ batches. Sources: official engine docs, engine source checkouts
(`~/Git/Repos/postgres`, `~/Git/Repos/sqlite`), and the SQLAlchemy checkout
(`~/Git/Repos/sqlalchemy`). One executed experiment (SQLAlchemy compile across
all five dialects) is reproduced in §2.3.

---

## 0. Per-engine summary table

| Engine | Partial index | Syntax / floor | Key caveats | Recommended probe shape |
|---|---|---|---|---|
| SQLite | Yes | `CREATE INDEX … WHERE`, since 3.8.0 (2013) | Planner matches predicate **terms textually** — no algebra; query term with a bound parameter never matches; index predicate may not contain bound parameters | Index `WHERE encoded = 0`; probe `WHERE encoded = 0` (inline literal — SQLAlchemy `~col` renders exactly this) |
| PostgreSQL | Yes | `CREATE INDEX … WHERE` (all supported versions) | Planner proves implication (`predtest.c`): exact expression match + simple btree-operator implications; **parameterized clauses never prove the predicate**; `x = true` ≡ `x` handled; predicate columns block HOT updates | Index `WHERE NOT encoded`; probe `WHERE NOT encoded` (no binds on the filter column) |
| SQL Server | Yes ("filtered index") | `CREATE INDEX … WHERE`, since 2008 | Plan for `encoded = @p` must be valid for **all** `@p` → filtered index illegal for parameterized comparisons; forced parameterization converts even literals to `@0` and breaks it; 7 required `SET` options | Filtered index `WHERE encoded = 0`; probe `SELECT TOP 1 … WHERE encoded = 0` with the comparison as an **inline literal**; document the forced-parameterization hazard |
| Oracle | No (through 23ai) | FBI NULL trick: index `CASE WHEN encoded = 0 THEN 1 END` — all-NULL keys are not stored | Probe must reference the **same expression** (tree-matched, case/space-insensitive); `INDEXING PARTIAL` (12.1+) is partition-scoped only; the shared `Index` object degrades to a full index on `encoded` | Either FBI + `WHERE CASE WHEN encoded = 0 THEN 1 END = 1 FETCH FIRST 1 ROWS ONLY` (bind-safe), or plain index on `encoded` (O(log n) seek) |
| MySQL / MariaDB | No (MariaDB: open MDEV-15140) | "Partial index" in MySQL docs means *prefix* index | Plain index on the boolean stores **all** rows; optimizer still picks it for `encoded = 0` via index dives (accurate even with stale stats); generated-column index gains nothing (InnoDB stores NULL entries) | Plain index on `encoded`; probe `WHERE encoded = 0 LIMIT 1` — O(log n) seek |
| GENERIC floor | Unknown → assume no | — | — | Plain index on `encoded`; same probe; O(log n) |

---

## 1. Per-engine detail

### 1.1 SQLite — partial indexes since 3.8.0

- Available since **3.8.0 (2013-08-26)**. The index `WHERE` clause may not
  contain subqueries, references to other tables, non-deterministic functions,
  or **bound parameters**.
  ([sqlite.org/partialindex.html](https://sqlite.org/partialindex.html))
- Planner-use conditions (W = query WHERE as AND-connected terms, X = index
  WHERE as OR-connected terms): the index is usable iff **some term of W
  appears as a term of X** — terms must match *exactly*; SQLite performs no
  algebraic transformation. The one extra rule: an X term `z IS NOT NULL` is
  implied by any W comparison on `z` other than `IS` (`=`, `<`, `IN`, `LIKE`,
  `GLOB`, …).
- Consequence for the probe: a query term carrying a bound parameter
  (`encoded = ?`) can never match an index predicate term (`encoded = 0`).
  The probe's filter comparison must be **inline and textually identical** to
  the index predicate. Building both the index `WHERE` and the query `WHERE`
  from the *same SQLAlchemy expression* guarantees this: DDL compiles the
  predicate with `literal_binds=True`
  (`sqlalchemy/dialects/sqlite/base.py:1881-1886`), and the query compiler
  renders `~col` as inline `encoded = 0` (§2.3). LIMIT is a bind on SQLite but
  is not a WHERE term, so it does not participate in matching.

### 1.2 PostgreSQL — partial indexes, `predtest.c`, HOT

- Planner rule ([indexes-partial docs](https://www.postgresql.org/docs/current/indexes-partial.html)):
  "a partial index can be used in a query only if the system can recognize
  that the WHERE condition of the query **mathematically implies** the
  predicate of the index." PostgreSQL "does not have a sophisticated theorem
  prover"; it recognizes simple inequality implications ("x < 1" implies
  "x < 2"); otherwise "the predicate condition must exactly match part of the
  query's WHERE condition."
- **Bound parameters never prove the predicate** — docs, verbatim: "As a
  result, parameterized query clauses do not work with a partial index. For
  example a prepared query with a parameter might specify `x < ?` which will
  never imply `x < 2` for all possible values of the parameter." A
  parameter-free `WHERE NOT encoded` probe carries no such risk: it is the
  identical expression and always matches.
- Implementation (`postgres/src/backend/optimizer/util/predtest.c`):
  `predicate_implied_by` walks AND/OR structure and proves atoms via btree
  operator-family semantics. Boolean columns are special-cased — "For boolean
  x, `x = TRUE` is equivalent to `x`" (predtest.c ~line 1124, using
  `BooleanEqualOperator`), so `WHERE NOT encoded`, `WHERE encoded = false`,
  and `WHERE encoded IS FALSE`-adjacent spellings interoperate with the index
  predicate. Note `MAX_SAOP_ARRAY_SIZE = 100`: `IN`-lists over 100 elements
  are not expanded for implication proofs (irrelevant to this probe, relevant
  if other queries are ever expected to hit the partial index).
- **HOT updates**: a column used in a partial-index predicate counts as an
  indexed column for HOT purposes —
  `postgres/src/backend/access/heap/README.HOT` (~lines 495-499): a column can
  be "used in a partial index predicate. HOT treats all these cases alike."
  So every `false→true` flip is a **non-HOT update**: the new tuple version
  gets entries in every index it qualifies for (it leaves the partial index,
  so no new entry *there*, but the update touches all other indexes on the
  table). The dead entries in the tiny partial index are reclaimed by
  autovacuum / btree bottom-up deletion (PG 14+); a 10k-row ETL flip leaves at
  most 10k dead entries in an otherwise near-empty index — bounded and
  routinely vacuumed, not a bloat hazard at this shape. Rows *entering* the
  predicate (inserts with `encoded = false`) insert one entry each.

### 1.3 SQL Server — filtered indexes and the parameterization caveat

- Filtered indexes are the documented tool for exactly this shape — the
  [create-filtered-indexes docs](https://learn.microsoft.com/en-us/sql/relational-databases/indexes/create-filtered-indexes)
  name it: "When rows in a table are marked as processed by a recurring
  workflow or queue process … A filtered index on rows that aren't yet
  processed would benefit the recurring query."
- **Required SET options** ([CREATE INDEX docs](https://learn.microsoft.com/en-us/sql/t-sql/statements/create-index-transact-sql)),
  required for creating the index, for any DML touching its data, and for the
  optimizer to use it: `ANSI_NULLS ON`, `ANSI_PADDING ON`, `ANSI_WARNINGS ON`,
  `ARITHABORT ON`, `CONCAT_NULL_YIELDS_NULL ON`, `NUMERIC_ROUNDABORT OFF`,
  `QUOTED_IDENTIFIER ON`. Wrong settings ⇒ create fails, DML errors and rolls
  back, or the optimizer silently ignores the index. ODBC connection defaults
  satisfy all of these except `ARITHABORT` (default OFF at the driver), but
  `ANSI_WARNINGS ON` implicitly sets `ARITHABORT ON` at compatibility level
  ≥ 90 (docs, footnote 1) — so stock pyodbc connections qualify; vfs
  `session_settings` must simply never switch any of these off.
- **Parameterization caveat** — the core hazard. A cached plan for
  `WHERE encoded = @p` must be valid for *every* value of `@p`; a filtered
  index can only serve `encoded = 0`, so any plan using it is illegal for a
  parameterized comparison — the optimizer refuses it, and forcing it raises
  error 8622. Microsoft's engineering writeup
  ([Filtered Indexes and Forced Parameterization](https://learn.microsoft.com/en-us/archive/blogs/bartd/filtered-indexes-and-forced-parameterization))
  shows the full failure: enabling forced parameterization turned
  `WHERE ProjectToCluster = 1` into `WHERE ProjectToCluster = @0` and a
  125M-row table went from an index seek to full clustered scans. "The query
  plan that is generated and cached for this query needs to be able to work
  for any possible value of @0 … Any plan that relies on this index could
  never be used for arbitrary values of the parameter."
- **Does a literal-only predicate avoid it?** Yes, under the default
  `PARAMETERIZATION SIMPLE` — provided the literal actually reaches the
  server as a literal (SQLAlchemy does render it inline, §2.3). Residual
  risks: (a) *forced parameterization* at the database level converts the
  literal to `@0` anyway — documented workarounds are `OPTION (RECOMPILE)` on
  the query (side effect: disables forced param for that statement) or a
  TEMPLATE plan guide with `OPTION (PARAMETERIZATION SIMPLE)` (bartd, above);
  the [query-processing architecture guide](https://learn.microsoft.com/en-us/sql/relational-databases/query-processing-architecture-guide)
  warns generally that forced parameterization makes the optimizer "less
  likely to match the query to an indexed view or an index on a computed
  column" — filtered indexes are the same plan-safety family. (b) *simple
  parameterization* auto-parameterizes only "a relatively small class" of
  trivial queries; if the probe were auto-parameterized the same illegality
  applies. The fully robust escapes are `OPTION (RECOMPILE)` on the probe
  (cheap for a `TOP 1` statement, but recompiles every call) or falling back
  to a plain index on `encoded` (parameterization-proof O(log n) seek).
- Secondary quirk ([KB 3051225](https://learn.microsoft.com/en-us/troubleshoot/sql/database-engine/performance/filtered-index-with-column-is-null)):
  when the filter column is neither a key nor an included column and the
  query touches it beyond the exact filter expression, the index is skipped.
  Keying the filtered index on `encoded` itself (which the shared `Index`
  definition does) and probing with exactly the filter expression avoids
  this; per the design guide, a filter column need not even be key/included
  when the query predicate is *equivalent* to the filter expression and the
  column is not in the result set.

### 1.4 Oracle — no native partial index; the FBI NULL trick

- No filtered/partial index for ordinary tables in any release through 23ai.
  `CREATE INDEX … INDEXING PARTIAL` (12.1+) selects which *partitions* of a
  partitioned table are indexed
  ([VLDB guide](https://docs.oracle.com/database/121/VLDBG/GUID-256BA7EE-BF49-42DE-9B38-CD2480A73129.htm))
  — partition-granular, not row-predicate-granular, and not applicable here.
  Nothing in 21c/23ai changes this (23ai adds a SQL `BOOLEAN` type but no
  filtered indexes).
- The standard emulation rides Oracle's NULL rule
  ([Concepts, Indexes chapter](https://docs.oracle.com/en/database/oracle/oracle-database/23/cncpt/indexes-and-index-organized-tables.html)):
  "Oracle … does not index table rows in which all key columns are null"
  (B-tree; bitmap indexes are the exception). A function-based index whose
  expression is NULL for the common case therefore stores only the rare rows:

  ```sql
  CREATE INDEX vfs_pending_ix ON vfs (CASE WHEN encoded = 0 THEN 1 END);
  -- probe:
  SELECT 1 FROM vfs WHERE CASE WHEN encoded = 0 THEN 1 END = 1
  FETCH FIRST 1 ROWS ONLY;
  ```

- Use conditions: "The database only uses the function-based index when the
  function is included in a query"; the optimizer matches by parsing and
  comparing expression trees, case-insensitively and ignoring whitespace
  (Concepts, ibid.). Unlike SQLite/PG/MSSQL, this trick is **bind-safe**: the
  partiality lives in the indexed expression, not in a predicate the planner
  must prove, so `expr = :b` still seeks the index for any bind value.
- Cost note: every INSERT/UPDATE evaluates the expression (Concepts, ibid.) —
  trivial for a CASE on one column. The alternative if the FBI is not
  adopted: a plain index on `encoded` (all non-NULL rows indexed, full-size),
  probe seeks `encoded = 0` in O(log n).

### 1.5 MySQL / MariaDB — no partial indexes; what actually works

- Neither supports a `WHERE` clause on `CREATE INDEX`
  ([MySQL 8.4 CREATE INDEX](https://dev.mysql.com/doc/refman/8.4/en/create-index.html) —
  in MySQL vocabulary "partial index" means a *column-prefix* index).
  MariaDB tracks filtered indexes as open feature request
  [MDEV-15140](https://jira.mariadb.org/browse/MDEV-15140).
- **Plain index on the boolean — and yes, the optimizer will use it for the
  rare value.** `WHERE encoded = 0` is an equality range; for up to
  `eq_range_index_dive_limit` (default 200) equality ranges the optimizer
  estimates rows by **index dives**, not table statistics: "With index dives,
  the optimizer makes a dive at each end of a range and uses the number of
  rows in the range as the estimate"
  ([range optimization docs](https://dev.mysql.com/doc/refman/8.4/en/range-optimization.html)).
  Index dives read the actual B-tree, so the skew (rare `0` among 10^8 `1`s)
  is seen accurately even when InnoDB's sampled persistent statistics
  (`innodb_stats_persistent_sample_pages`, default 20 pages) would badly
  misestimate a 99.99/0.01 boolean. With `LIMIT 1` the probe is one index
  descent — O(log n), ~4-5 page touches at 10^8 rows.
- **Generated column + index buys nothing**: InnoDB secondary indexes store
  NULL entries (that is why `IS NULL` can use an index —
  [IS NULL optimization](https://dev.mysql.com/doc/refman/8.4/en/is-null-optimization.html)),
  so an index on a nullable generated column (`NULL` when encoded) is still
  full-size. Skip it.
- **Side table** (a `vfs_pending` one-row-per-pending-entry table, or a
  counter row): the only truly O(1)-and-tiny option on this family; probe is
  `SELECT 1 FROM vfs_pending LIMIT 1`. Cost: dual-write discipline inside the
  same transaction on every encode/flip path, on *every* engine, to keep the
  signal truthful. Not recommended while an O(log n) seek satisfies the
  latency budget.

---

## 2. SQLAlchemy modeling

### 2.1 Kwargs, since-versions, one Index for all dialects

All from the checkout at `~/Git/Repos/sqlalchemy`:

- `postgresql_where` — long-standing; already present (renamed from
  `postgres_where`) in the 0.6 series (`doc/build/changelog/changelog_06.rst:4845-4854`).
- `sqlite_where` — added for 1.0.0 (doc/changelog commit `6ac0555ea`,
  2015-03-10, tagged `rel_1_0_0`).
- `mssql_where` — added in **1.3.4** (released 2019-05-27), ticket #4657
  (`doc/build/changelog/changelog_13.rst:2763-2783`).

**One `Index` object can carry all three simultaneously** and be a plain
index everywhere else. The kwargs are dialect-namespaced (`DialectKWArgs`);
each dialect's DDL compiler consults only its own slot:
`index.dialect_options["sqlite"]["where"]`
(`lib/sqlalchemy/dialects/sqlite/base.py:1881-1886`),
`…["mssql"]["where"]` (`lib/sqlalchemy/dialects/mssql/base.py:2712-2722`),
and the postgresql compiler likewise. The default `DDLCompiler.visit_create_index`
(`lib/sqlalchemy/sql/compiler.py:7226+`) — used by Oracle, MySQL, and any
unknown dialect — has no WHERE handling at all, so `CreateIndex` renders a
plain `CREATE INDEX name ON table (cols)`; the foreign kwargs are simply
inert. In every dialect the predicate is compiled with `literal_binds=True`
at DDL time, so the same Python expression object produces the literal
predicate text.

### 2.2 Reflection round-trip

- PostgreSQL + SQL Server: partial/filtered predicates reflected since
  **1.4.0** (ticket #4966) — surfaced both in `Inspector.get_indexes()`
  (`dialect_options` entry) and on reflected `Index` objects
  (`changelog_14.rst:8040-8048`; mssql reads `filter_definition`,
  `mssql/base.py:3527-3528`; postgresql reads `pg_get_expr` output,
  `postgresql/base.py:5324`).
- SQLite: reflected since **1.4.45** (ticket #8804; commit `ed39e846c`),
  with a follow-up fix in 1.4.46/2.0.0b5 for pre-3.8.9 SQLite `index_list`
  pragma output (ticket #8969, `changelog_14.rst:576-583`);
  `sqlite/base.py:2973` stores it as `text(...)`.
- Caveat for reindex/migration tooling: the reflected predicate comes back as
  **raw SQL text** (string / `text()`), not as the original expression tree —
  it round-trips through `CreateIndex` fine, but comparing a reflected
  predicate to a metadata-declared expression requires string normalization
  (Alembic autogenerate historically does not diff index WHERE clauses).

### 2.3 Executed experiment — how the probe actually renders

`uv run python` compiling `select(t.c.id).where(~t.c.encoded).limit(1)`
(Boolean column) on all five built-in dialects:

| Dialect | Rendered WHERE | Binds on filter column? |
|---|---|---|
| sqlite (`native_boolean=False`) | `WHERE vfs.encoded = 0` | **No** (LIMIT is a bind; not a WHERE term) |
| postgresql (`native_boolean=True`) | `WHERE NOT vfs.encoded` | **No** |
| mssql | `WHERE vfs.encoded = 0`, `TOP` postcompiled inline | **No** |
| mysql | `WHERE vfs.encoded = 0` | **No** |
| oracle | `WHERE vfs.encoded = 0`, `FETCH FIRST` postcompiled | **No** |

(`t.c.encoded == False` renders identically on sqlite/mssql/oracle and as
`encoded = false` on pg/mysql; prefer `~t.c.encoded`.)

This is the load-bearing fact: SQLAlchemy's boolean negation renders as an
**inline literal comparison on every dialect**, so the same expression object
used as the index predicate and as the probe WHERE satisfies SQLite's
textual-term rule, PostgreSQL's implication proof, and SQL Server's
literal-not-parameter requirement — with zero dialect-conditional query code.

## 3. SQLAlchemy compiled-statement cache

Facts from `doc/build/core/connections.rst` (§"SQL Compilation Caching",
`sql_caching`), `doc/build/faq/performance.rst`, and
`doc/build/changelog/migration_14.rst`
(rendered: [docs.sqlalchemy.org/en/20/core/connections.html#sql-compilation-caching](https://docs.sqlalchemy.org/en/20/core/connections.html#sql-compilation-caching)):

- **Mechanism** (1.4+): a transparent per-engine `LRUCache`, default
  `create_engine(query_cache_size=500)`; may grow to 150% before pruning to
  target. Cache value = compiled SQL string plus result-fetching mechanics.
- **Keying**: a structural cache key (`stmt._generate_cache_key()`) covering
  "everything that may vary about what's being rendered" — bound parameter
  *values* are excluded. The key is computed **on every execution**; the docs
  note that "even for an extremely short query the cache key is pretty
  verbose", i.e. key-generation cost grows with statement size — for large
  statements the documented mitigation is the **lambda** system
  (`lambda_stmt`), whose key is the Python code object: "vastly shorter",
  and it also skips re-building the construct itself.
- **`.in_()` does not disable caching**: since 1.4 every IN renders one
  "expanding" (`__[POSTCOMPILE_…]`) bind parameter; the cached SQL string is
  patched per execution for the current list length, so varying list
  contents/sizes hit the same cache entry
  (`migration_14.rst:1068-1131`).
- **What does disable/skip caching**: DDL (`[no key]`); the `Values`
  construct and multi-valued `Insert.values()` (arbitrarily long,
  non-reproducible strings); custom constructs/types without
  `inherit_cache = True` (emits `SAWarning`, logs `[no key]`); third-party
  dialects that don't set `Dialect.supports_statement_cache` on their own
  class (1.4.5+; logs `dialect does not support caching`); and explicit
  opt-out via `execution_options(compiled_cache=None)`. (`literal_binds` is a
  stringification-time flag, not an execution path — statements executed
  normally never use it; postcompile/`literal_execute` params render inline
  per execution while remaining cacheable.)
- **Explicit pre-compiling/caching**: yes — any dict can serve as the cache
  for a statement/connection/engine via
  `execution_options(compiled_cache=my_cache)` (the ORM itself uses
  per-mapper dicts for flush statements), and `lambda_stmt` gives the
  cheapest steady-state key. For this probe the right shape is simply a
  **module-level singleton `select()`**: construction cost paid once, cache
  key tiny, cache hit every call.

## 4. Prior art

The "partial index over the pending minority" is a first-class documented
pattern in both ecosystems, not an exotic trick. PostgreSQL's own partial-index
chapter builds Example 11.2 around it: an orders table where "in the great
majority" rows are billed and the working queries seek `WHERE NOT billed` via
`CREATE INDEX orders_unbilled_index ON orders (order_nr) WHERE billed is not true`
([indexes-partial](https://www.postgresql.org/docs/current/indexes-partial.html)).
SQL Server's filtered-index docs list the identical scenario as a design
motivation — "rows marked as processed by a recurring workflow or queue
process … a filtered index on rows that aren't yet processed"
([create-filtered-indexes](https://learn.microsoft.com/en-us/sql/relational-databases/indexes/create-filtered-indexes)).
Production job-queue systems on Postgres are built on exactly this: GitLab's
database guidelines push partial indexes for state-scoped queries over large
tables ([GitLab: adding database indexes](https://docs.gitlab.com/ee/development/database/adding_database_indexes/)),
and Ruby's GoodJob/Que-family queue tables ship partial indexes on unfinished
jobs so the poll ("any runnable job?") stays a seek of a near-empty index.

The "dirty set" side-signal — externalizing "what is not yet indexed" into a
tiny separate structure — is the standard move in search-index systems.
Sphinx/Manticore's documented **main+delta** scheme keeps a `sph_counter`
helper table recording the boundary of the last full index build; the delta
index and freshness checks read that one-row table instead of scanning the
corpus for un-indexed documents
([Manticore: main+delta](https://manual.manticoresearch.com/Creating_a_table/Local_tables/Plain_and_real-time_table_settings)).
Same shape, same trade: an O(1) probe on any engine, paid for with dual-write
discipline on every mutation path. That is the fallback if an engine family
ever makes the index-based probe unacceptable; the partial index is preferable
where available because the signal is maintained by the engine itself and can
never drift from the data.

## 5. Recommended portable design

Declare **one** index in the models:

```python
PENDING = ~vfs_table.c.encoded          # the single shared predicate expression

Index(
    "ix_vfs_pending",
    vfs_table.c.encoded,
    sqlite_where=PENDING,
    postgresql_where=PENDING,
    mssql_where=PENDING,
)
```

and **one** module-level probe statement,
`select(literal(1)).where(PENDING).limit(1)`. On SQLite/PostgreSQL/SQL Server
this renders a partial/filtered index plus a probe whose filter comparison is
an inline literal built from the same expression — textually identical terms
for SQLite, the identical (parameter-free) expression for Postgres's prover,
and a literal (never a bind) for SQL Server. On Oracle, MySQL/MariaDB, and any
GENERIC-floor dialect the foreign kwargs are inert and the same DDL renders a
**plain full index on `encoded`**: the probe degrades from "descend a
near-empty B-tree" to "descend a full B-tree to the rare edge" — O(log n),
~4-5 page reads at 10^8 rows, still effectively constant per call — at the
cost of a full-size index to store and maintain through ETL flips. No
DialectProfile field is needed for the index itself (the per-dialect `Index`
kwargs *are* the declared-per-dialect mechanism, and unknown dialects safely
render the plain form); a profile field becomes justified only if the Oracle
FBI upgrade below is adopted, since that changes both DDL and probe SQL.

Flags:

- **Oracle** is the engine where the *small* index cannot come from the
  shared definition: the tiny-index option is a function-based index on
  `CASE WHEN encoded = 0 THEN 1 END` with an expression-matched probe —
  different DDL *and* different query text, i.e. a genuine per-dialect fork
  (declare it in the profile if the full-index maintenance cost ever measures
  as a problem; the plain-index fallback is correct and O(log n) meanwhile).
- **MySQL/MariaDB and the GENERIC floor** cannot get a partial index at all;
  the plain-index probe is O(log n), which satisfies "effectively O(1) per
  call" but not "index size proportional to pending set". Only a maintained
  side table gives strict O(1) there, and it is not worth the dual-write
  contract today.
- **SQL Server operational caveat to document** (and worth a db_test leg):
  `PARAMETERIZATION FORCED` at the database level converts even literal
  predicates to parameters and makes the filtered index unusable (plans fall
  back to scans; forcing raises 8622). Mitigations if a deployment runs
  forced parameterization: `OPTION (RECOMPILE)` on the probe, a TEMPLATE plan
  guide with `OPTION (PARAMETERIZATION SIMPLE)`, or dropping `mssql_where` to
  fall back to the plain-index seek. Also: the filtered index requires the
  seven standard SET options (ANSI_NULLS/ANSI_PADDING/ANSI_WARNINGS/
  ARITHABORT/CONCAT_NULL_YIELDS_NULL/QUOTED_IDENTIFIER ON,
  NUMERIC_ROUNDABORT OFF) on every connection that creates it, modifies its
  rows, or wants the optimizer to use it — stock pyodbc defaults qualify;
  vfs session settings must never unset them.
- **PostgreSQL write-path note**: because `encoded` appears in an index
  predicate, flips are non-HOT updates (README.HOT) — every flip touches all
  the table's indexes, not just this one. Bounded and vacuum-recovered at the
  declared batch sizes; worth one docstring sentence on the flip path, not a
  design change.
