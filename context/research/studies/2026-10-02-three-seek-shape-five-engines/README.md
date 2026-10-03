# Study: the three-seek shape and the relabel on five engines

- **Date:** 2026-10-02
- **Status:** executed study (spec 150 slice D); nothing here is imported
  by vfs
- **Engines:** SQLite 3.50, Postgres 17.11, MariaDB 11.8, SQL Server
  2025 (CU8), Oracle 23ai Free (26ai, 23.26)
- **Question:** spec 150 §5 makes visibility three index seeks: the
  everyone level on the row, the caller's own ranges, and the owner
  floor. The 2026-10-02 row-label spike measured that on SQLite and
  Postgres only. Does the same shape seek on SQL Server, MariaDB and
  Oracle, what statement shape does each planner need, what does the
  relabel `UPDATE` cost there, and does Postgres need the fence §5
  decided on?

See `results.md` for the findings. This file says what is here, how to
rerun it, and ends with the **chosen shape per dialect**.

## What is here

| file | what it does |
|---|---|
| `bench.py` | Imports the spike's `world.py` and `prototype.py` unchanged (the world, the compiler, the truth function, the relabel algebra). Read mode loads the world at N, compiles the five callers, and times four statements (visible entries; the same under one shared folder; the visible chunk count through a derived table; the top 10 chunks by score) in each predicate shape, cold and warm, every cell checked against the Python truth and the 100 sibling traps. Captures a plan per shape, times the scoped read with branch 1 spelled `>=` and `IN`, and measures the three indexes. Writes mode builds a 1,000-user world plus `/mid` (1,001 rows), `/mv` (10,001) and `/big` (200,000) and times the relabel in three forms per dialect, chunked by 500 pieces and by 50,000-row keyset, the root change across 1,102 deeper postures, and a 10,001-row move with the destination label in the same statement. Every table is `ts_<hex>_`-prefixed and dropped. |
| `probe.py` | The spelling probe. Builds the world once and times the ordinary caller's statements under each planner knob a dialect offers (SQL Server: `JOIN`, `INNER LOOP JOIN`, `CROSS APPLY`, `OPTION (FORCE ORDER)`, `+ 0`; MariaDB: `STRAIGHT_JOIN` + `FORCE INDEX`, `+ 0`; Oracle: `CARDINALITY`, the branch-1 index hint, the derived-table hint, `LEADING/USE_NL`; Postgres: the `LIKE` estimate nudge), with plans. This is where each dialect's chosen spelling came from. |
| `runs/<engine>-<N>.md` | The read grid at N=1,000 and 10,000 on all five, N=100,000 on Postgres and MariaDB, with plans. |
| `runs/<engine>-probe.md` | The spelling probes (SQL Server, MariaDB, Oracle at N=10,000; Postgres at N=100,000). |
| `runs/<engine>-writes.md` | The relabel and move per engine, with plans. |
| `results.md` | The result tables and what they mean. |

## The shapes

Branch 1 is `everyone_level >= :r`. Branch 2 is the range join on the
caller's pieces with `AND everyone_level < :r`. Branch 3 is
`owner_id = :me AND everyone_level < :r` (per member, joined to the
member's owner pieces when there are two subjects).

| shape | statement |
|---|---|
| `union` | (a) `b1 UNION b2 UNION b3` |
| `unionall` | (b) `b1 UNION ALL b2 UNION b3` |
| `literal` | (c) one inline predicate, every piece its own bind (`path IN (…)`, `(path > :lo AND path < :hi) OR …`) |
| `fenced` | (d) Postgres only: (b) with each range branch behind `OFFSET 0`, and `SET LOCAL jit = off` first |
| `disjoint` | (e) an extra probe: branch 3 also excludes the caller's own ranges with `NOT EXISTS`, so everything is `UNION ALL` and no engine plans a dedup |

The chunk-side statements join the visible set as a derived table
(ADR 072 rule 4). The `literal` shape instead puts the predicate on
the entry row inside the chunk join, which is the shape a top-k that
walks the score index wants.

## Rerun

Containers up; the URLs default to the test compose ports and can be
overridden with `TS_PG_URL`, `TS_MARIADB_URL`, `TS_MSSQL_URL`,
`TS_ORACLE_URL`. Scratch defaults to the job scratch (`TS_SCRATCH`).
From this directory:

    uv run --no-sync python bench.py --engine mssql --n 10000
    uv run --no-sync python bench.py --engine oracle --n 10000
    uv run --no-sync python bench.py --engine mariadb --n 100000 --chunks 1 --reps 2
    uv run --no-sync python bench.py --engine postgres --writes
    uv run --no-sync python bench.py --engine mariadb --writes --forms join,literal
    uv run --no-sync python probe.py --engine mssql --n 10000

`--shapes` and `--forms` take comma lists. The chosen spelling per
dialect is the default; the probe's other spellings are reachable
through environment knobs (`TS_MSSQL_LOOP=0`, `TS_MSSQL_APPLY=1`,
`TS_MSSQL_FORCE=1`, `TS_MARIADB_FORCE=0`, `TS_PLUS_ZERO=1`,
`TS_ORACLE_CARD=0`, `TS_ORACLE_ONE=0`, `TS_ORACLE_NL=0`,
`TS_ORACLE_LEADING=1`, `TS_PG_NUDGE=1`). The truth sets are cached
per N in scratch; the spike's cache is reused when present.

Wall time: N=10,000 two to four minutes per engine (SQL Server loads
in 84 s, Oracle in 54 s); N=100,000 with one chunk per file about ten
minutes; writes one to five minutes per engine. All five engines can
run at once. Every server was shared with another agent's engine
legs for the whole study, so warm medians carry noise; the plans do
not.

## Chosen shape per dialect

The spelling slice B should build. "Range source first" means the
table function that unpacks the caller's pieces is the outer side of
the join and the path index is sought once per piece.

| dialect | visibility statement | range source | branch 1 | relabel `UPDATE` (ranges, ≤ 500 per statement) | index for the scoped read | what `DialectProfile` needs that SQLAlchemy does not model |
|---|---|---|---|---|---|---|
| SQLite | (b) `UNION ALL` of 1 and 2, `UNION` onto 3. Range branches as `json_each(…) CROSS JOIN entries` — plain `JOIN` seeks `everyone_level < :r` on the composite and scans the ranges per row (90 ms against 1 ms at N=1,000). | `json_each` | `>=` (with `ANALYZE`, a skip-scan of the composite); `IN` gives an exact seek | `UPDATE entries AS e SET … FROM json_each(:r) AS r WHERE e.path > … AND e.path < …`; the literal `OR` form is a `MULTI-INDEX OR` and equally good | `(everyone_level, path)` | the join keyword for the range branch (`CROSS JOIN`) |
| Postgres | (e) all three branches disjoint, `UNION ALL` throughout, and `SET LOCAL jit = off` in the same transaction. The decided fence (d) does **not** change the plan: the range branch is still estimated at 8.4 M rows (actual 20), the `HashAggregate` still plans 128 partitions and spills 8 MB; only JIT-off's 100 ms is saved. (e) removes the aggregate entirely: `Append` only, 85 ms against 268 ms for (a) on the ordinary caller's entries at N=100,000. | `unnest` of two arrays, `COLLATE "C"` | `>=` | `UPDATE entries e SET … FROM unnest(…) AS r(lo, hi) WHERE e.path > r.lo COLLATE "C" AND …` (290 ms for the root's 3,308 pieces in 8 statements; the spike's `id IN (subquery)` form is 395, the literal 679) | the path index for a narrow scope; the composite for the unscoped everyone leg (`Bitmap Index Scan`) | the per-transaction `SET LOCAL jit = off`. The range-branch estimate stays wrong; `AND path LIKE (r.lo \|\| '%')` cuts it 200× and the count 1.8× (329 → 184 ms at N=100,000) and is lawful for read pieces, but is a hack and is **not** chosen |
| MariaDB | (b). Range branches as `JSON_TABLE(…) STRAIGHT_JOIN entries FORCE INDEX (path_index)`: without the pins the planner takes a full scan of the composite with a block nested loop over the ranges (745 ms against 50 at N=10,000). `everyone_level + 0 < :r` gives the identical plan (`Range checked for each record`) and is the portable fallback. | `JSON_TABLE`, `CAST(… AS BINARY)` | either; both seek the composite (`type=range key=lvlpath rows=201`) | `UPDATE entries e STRAIGHT_JOIN JSON_TABLE(…) r ON … SET e.everyone_level = :l` (158 ms for the root; the literal 330). The `id IN (SELECT …)` form **did not finish in 20 minutes** on the root's first 500-range statement and was killed. | `(everyone_level, path)` | the join keyword (`STRAIGHT_JOIN`) and the `FORCE INDEX` on the entry table in the range branch |
| SQL Server | (b). Range branches as `OPENJSON(…) INNER LOOP JOIN entries`: the plain `JOIN` is rewritten to a semi-join driven by a clustered index scan of entries with the ranges as the inner (3.2 s at N=10,000); `LOOP JOIN` pins the ranges outer and seeks `path` per range (64 ms). `CROSS APPLY` does not help (3.2 s), `OPTION (FORCE ORDER)` is a weaker 121 ms, `+ 0` does nothing (4.2 s). The literal form wins for callers under ~220 pieces (44 ms entries, 6.7 ms top-10 through the score index) and stays bounded by the 2,100-parameter budget: slice B may keep it as the small-rights shape on this dialect. | `OPENJSON … WITH (lo nvarchar(max), hi nvarchar(max))`, `CAST(… COLLATE Latin1_General_100_BIN2_UTF8 AS varchar(1024))` | either; the scoped branch 1 seeks the path index | `UPDATE e SET … FROM OPENJSON(…) r INNER LOOP JOIN entries e ON …`: `Index Seek` on `path` per range with the ranges outer, 956 ms for the root's 3,308 pieces in 8 statements, 65 ms for `/mid`. The plain `JOIN` form scanned entries per range and was stopped after 15 minutes on the root; the literal `OR` of 500 ranges is an index scan with a filter here (4,440 ms), so the literal is **not** the relabel form on this dialect. | path index for the scope, composite for the unscoped leg | the join keyword (`INNER LOOP JOIN`); the padded-comparison rule is unchanged: no bound ends in a byte below `/`, recall exact on every cell including the 100 traps |
| Oracle | (b) with three hints: `/*+ CARDINALITY(src n) */` on each range branch (n = the piece count, known at compile time; without it `JSON_TABLE` is estimated at 8,168 rows and the planner hash-joins a full scan), `/*+ INDEX(e (everyone_level path)) */` on branch 1 (a full scan otherwise), and `/*+ NO_MERGE(v) LEADING(v) USE_NL(c) INDEX(c (entry_id)) */` on the derived-table statements (otherwise the chunk index drives and the view is re-evaluated per chunk row: 2 to 7 s for the `disjoint` count at N=1,000). `LEADING/USE_NL/INDEX(path)` on the range branch is **worse** (index full scan + merge join). | `JSON_TABLE(:k, '$[*]' COLUMNS (lo VARCHAR2(1024) PATH '$[0]', hi …))`, the JSON bound as a CLOB — **Oracle gains a `range_source`** | hinted `>=`; `IN` seeks the same index | the literal `OR` of ranges with `/*+ USE_CONCAT */`: one `CONCATENATION` of `INDEX RANGE SCAN`s, 394 ms for the root in 8 statements. `MERGE … USING JSON_TABLE` seeks for one range (12 ms) but at 500 ranges plans a merge join over a full scan even with the cardinality hint (6.1 s); the `id IN` form 3.9 s. | `(everyone_level, path)` (`INDEX RANGE SCAN` under both spellings) | `range_source` for Oracle, and a hint template per statement kind (range branch, branch 1, derived join, relabel) — the only dialect whose spelling carries a number from the caller |

Two things hold on every engine and need no dialect fact: the
`everyone_level < :r` term never leaks a sibling trap (recall exact on
every cell, every N, every engine; the 100 `-x` rows never appear),
and the move takes the destination label in the same `UPDATE` as the
path rewrite (36 to 460 ms for 10,001 rows).
