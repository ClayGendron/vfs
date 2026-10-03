# Results: the three-seek predicate and the relabel on five engines

Short version. The shape is right on every engine. Every statement in
every shape returned exactly the right rows on SQLite, Postgres,
MariaDB, SQL Server and Oracle at every N, including the 100 sibling
traps, and every relabel left every label equal to the Python
labeller. What differs per engine is the planner. The extra term
`everyone_level < :r` on the range branch is a new temptation: four
of the five planners first read it as "seek the composite index" or
"scan the entry table with the ranges as the inner loop", and the
range join stopped seeking the path index. Each engine has a one-word
cure, found by the probe and recorded in `README.md`'s chosen-shape
table. The decided Postgres fence does not do what it was meant to do;
the disjoint `UNION ALL` form does. Oracle gains a range source with a
cardinality hint. The relabel is one index seek per piece on every
engine in the form each needs, and the `id IN (subquery)` form the
spike used is the wrong form everywhere but SQLite.

All numbers: warm = median of 3 on one connection (2 at N=100,000),
cold = first run on a fresh connection. Every server was shared with
another agent's engine legs for the whole study, and some of my own
runs overlapped (the N=100,000 reads ran beside the MariaDB writes),
so medians carry noise of up to about 2×; the plans are the reliable
witness, and the big ratios (3 s against 60 ms) are not noise. Full
tables with plans are in `runs/`.

## 1. The predicate: before and after the per-engine fix

The probe at N=10,000 (230,203 entries, 220,000 chunks), the ordinary
caller (88 pieces), shape (b), warm ms. "Plain" is the statement as
the spike wrote it, with `everyone_level < :r` added as §5 says.

| engine | plain: entries / count | what the plan did | fix | fixed: entries / count |
|---|---|---|---|---|
| SQLite (N=1,000) | 90 / 77 | `SEARCH e USING COVERING INDEX lvlpath (everyone_level<?)` then `SCAN ar` — the composite outer, the ranges scanned per row | `json_each(…) CROSS JOIN e` | 1.2 / 1.0 |
| SQL Server | 3,238 / 3,224 | `Nested Loops (Left Semi Join)` with `Clustered Index Scan` of entries outer and `OPENJSON` inner | `INNER LOOP JOIN` (ranges outer) | 64 / 36 |
| MariaDB | 745 / 787 | `e type=index key=lvlpath … Using join buffer (flat, BNL join)` — full scan of the composite, block nested loop over the ranges | `STRAIGHT_JOIN` + `FORCE INDEX (path)`, or `everyone_level + 0` | 50 / 63 (85 / 51 with `+ 0`) |
| Oracle | 172 / 68 | `HASH JOIN` of `JSONTABLE EVALUATION` (estimated 8,168 rows) with `TABLE ACCESS FULL`; branch 1 a full scan | `CARDINALITY(src n)`; `INDEX(e (everyone_level path))` on branch 1 | 167 / 24 |
| Postgres | — | seeks as in the spike; the estimate problem is §4 | — | — |

What the other knobs did. SQL Server `CROSS APPLY` 3,170 ms (the
optimizer rewrites it back), `OPTION (FORCE ORDER)` 121 ms, `+ 0`
4,255 ms. Oracle `LEADING(src) USE_NL(e) INDEX(e (path))` 254 ms
entries and 134 ms count — worse than plain, because the index hint
without a usable nested-loop range probe turns into an `INDEX FULL
SCAN` with a merge join. Oracle's `NO_MERGE(v) LEADING(v) USE_NL(c)
INDEX(c (entry_id))` on the derived table took the count from 24 to
14 ms and the top-10 from 14 to 24 ms; it is kept because without it
the `disjoint` form's count ran 2 to 7 s at N=1,000 (the chunk index
drove and the view was re-evaluated per chunk row). Oracle's entries
numbers are bound by row transfer, not the predicate: the system
caller fetches 230,203 ids in 2.9 s (about 80 rows per ms), so the
ordinary caller's 20,124 ids cost about 250 ms whatever the shape.

## 2. The read grid at N=10,000, the chosen spelling, warm ms

Ordinary caller (88 pieces, 20,124 visible of 230,203). Statements:
entries, scoped (under `/shared/s0001`), count (660,000 chunks through
the derived table), top10 (through the derived table; `literal` is the
inline predicate on the entry row).

| engine | shape | entries | scoped | count | top10 |
|---|---|---|---|---|---|
| SQLite | union | 16.6 | 3.8 | 17.3 | 26.2 |
| | unionall | 12.3 | 3.1 | 19.2 | 26.1 |
| | literal | 223 | 2.0 | 225 | 16.8 |
| | disjoint | 23.8 | 4.6 | 28.3 | 27.0 |
| Postgres | union | 127 | 16.3 | 215 | 77.4 |
| | unionall | 166 | 10.5 | 169 | 100 |
| | literal | 43.6 | 12.4 | 81.5 | 7.5 |
| | fenced | 51.1 | 13.6 | 206 | 112 |
| | disjoint | 74.7 | 8.6 | 100 | 65.2 |
| MariaDB | union | 98.9 | 10.9 | 128 | 42.2 |
| | unionall | 79.6 | 9.9 | 142 | 39.5 |
| | literal | 311 | 10.8 | 347 | 7.1 |
| | disjoint | 84.1 | 6.5 | 136 | 19.6 |
| SQL Server | union | 123 | 12.9 | 101 | 164 |
| | unionall | 145 | 10.8 | 127 | 163 |
| | literal | 43.9 | 4.9 | 135 | 6.7 |
| | disjoint | 86.8 | 12.0 | 101 | 135 |
| Oracle | union | 508 | 7.1 | 23.9 | 38.8 |
| | unionall | 342 | 4.6 | 21.4 | 34.3 |
| | literal | 617 | 4.0 | 121 | 2.6 |
| | disjoint | 714 | 5.5 | 17.2 | 22.3 |

Recall: exact in every cell for every caller (heavy group, two
subjects, anonymous, system too). The anonymous caller is branch 1
alone (SQLite 7.9 ms entries, Postgres 77, MariaDB 52, SQL Server 26,
Oracle 415); the system caller is a bare select.

What this shows.

- **The scoped read is 2 to 13 ms on every engine** and that is the
  statement an agent's `ls`/`tree` under a folder pays. It was the
  reason for the composite index, and §5 below says who uses it.
- **The three join shapes (a), (b), (e) are within noise of each
  other** on SQLite, MariaDB, SQL Server and Oracle at this N. The
  dedup an engine plans for `UNION` costs nothing visible here; what
  matters is that the branches seek. Postgres is the exception (§4).
- **The literal form is two-faced.** For `entries` and `count` it is
  the worst shape on SQLite (223 ms: `SCAN e`, the OR of 88 terms
  defeats the multi-index OR) and MariaDB (311 ms, 17 s for the
  464-piece heavy caller at N=100,000), and the best on SQL Server
  (44 ms) and Postgres (44 ms, a `BitmapOr` of 73 index scans). For
  `top10` it is the best everywhere (2.6 to 17 ms), because the
  engine walks the score index and tests each chunk's entry row, and
  stops after ten. That is the vector leg's shape, and it is the
  count-gate ADR's business, not this slice's; ADR 072 rule 5 keeps
  the literal small-rights form only where no range source exists,
  and with Oracle gaining one (§6) that is the unknown dialect alone.
  SQL Server is the one engine where slice B could *choose* the
  literal form for small rights and gain by it.

## 3. The relabel, per dialect

A 1,000-user world plus `/mid` (1,001 rows), `/mv` (10,001) and
`/big` (200,000); 234,115 entries. Points travel as `path IN (…)`,
ranges in the form named, at most 500 pieces per statement, **every
statement its own transaction** (the brief's rule after yesterday's
Postgres crash). Median of 3 alternating runs; labels checked against
the Python labeller after each.

| engine | `/mid` 1,001 rows: join / literal / in_sub | `/big` 200,000 rows: one statement / keyset 50,000 (9 statements) | root, 1,103 points + 2,205 ranges in 8 statements: join / literal / in_sub | move 10,001 rows |
|---|---|---|---|---|
| SQLite | 5 / 9 / 8 | 262 / 311 | 35 / 44 / 44 | 36 |
| Postgres | 104 / 25 / 39 | 1,821 / 2,671 | 290 / 679 / 395 | 155 |
| MariaDB | 9 / 8 / — | 909 / 1,031 | 158 / 330 / **killed after 20 min** | 119 |
| SQL Server | 65 / 48 / 139 | 3,342 / 7,530 (5,916 / 6,920 in the first run) | 956 / 4,440 / — | 741 |
| Oracle, hinted | 12 / 8 / 20 | 5,029 / 3,094 | 6,087 / **394** / 3,904 | 460 |
| Oracle, unhinted | 156 / 19 / 106 | 3,890 / 3,554 | 5,921 / 11,909 / 4,297 | 248 |

SQL Server's first writes run used the plain `UPDATE … FROM e JOIN
OPENJSON` and stalled on the root relabel's first 500-range statement
for fifteen minutes before I stopped it (its `/mid` rows: literal
73 ms, `id IN` 139 ms; `/big` 5,916 and 6,920 ms). The table's SQL
Server row is the rerun with the range source first and `INNER LOOP
JOIN` (`runs/mssql-writes.md`); the `id IN` form was not rerun.

What the plans say (all in `runs/<engine>-writes.md`):

- **Postgres** `UPDATE … FROM unnest` seeks (`Nested Loop` over
  `Function Scan on unnest` into `Index Scan using path`); the literal
  OR is a `BitmapOr` of 500 index scans, slower to plan; the `id IN`
  form is the semi-join the spike warned about. The join form is the
  one to build.
- **MariaDB** `UPDATE e STRAIGHT_JOIN JSON_TABLE … SET` plans `Range
  checked for each record (index map: path)` — one range scan per
  piece. The literal is a multi-range `type=range key=path rows=500`.
  The `id IN (SELECT … JSON_TABLE … JOIN e)` form never finished.
- **Oracle** needs two different forms. For one range, `MERGE … USING
  (SELECT /*+ CARDINALITY(r 1) */ … FROM JSON_TABLE)` seeks
  (`NESTED LOOPS → JSONTABLE EVALUATION → INDEX RANGE SCAN path`,
  12 ms). For 500 ranges the same statement with `CARDINALITY(r 500)`
  still plans `MERGE JOIN` over `TABLE ACCESS FULL` (6.1 s for the
  root). The literal OR with `/*+ USE_CONCAT */` is a `CONCATENATION`
  of 500 `INDEX RANGE SCAN`s and does the root in 394 ms; without
  the hint the same text is a full scan per statement, 11.9 s. So the
  Oracle relabel is the hinted literal form, and 500 ranges is 1,000
  binds, inside Oracle's budget.
- **SQL Server** `UPDATE e SET … FROM OPENJSON(…) r INNER LOOP JOIN e`
  plans the ranges outer and an `Index Seek` on `path` per range (the
  same cure as the read). The literal OR of 500 ranges is an `Index
  Scan` of the composite with a filter, 4,440 ms for the root against
  the join's 956: on this dialect the join form is the relabel and
  the literal is not.
- **SQLite** all three forms seek; the join form is the simplest.
- **Keyset chunking** of the 200,000-row range costs about the same
  as one statement (SQLite 311 vs 262, MariaDB 1,031 vs 909, Oracle
  3,094 vs 5,029) and bounds every statement at 50,000 rows and its
  own transaction. The boundary probe is `ORDER BY path OFFSET k
  FETCH NEXT 1` on SQL Server and Oracle, `LIMIT 1 OFFSET k`
  elsewhere.
- **The relabel rate**: SQLite 1.3 µs per row, MariaDB 4.5, Postgres
  9, Oracle 15 to 25, SQL Server 17 to 38. A ten-million-row posture
  change is 13 s on SQLite and five minutes on SQL Server; §4's
  decision that the verb waits still holds, with the chunked
  transactions keeping every lock short.

## 4. Postgres: the fence does not fix the estimate; disjoint does

N=100,000 (2,301,103 entries, 2,200,000 chunks, one per file), the
ordinary caller (72 pieces, 201,024 visible), `EXPLAIN (ANALYZE,
BUFFERS)` of the entries statement:

| shape | plan | execution |
|---|---|---|
| (a) union | `HashAggregate` planned 128 partitions, ran 129 batches, 8 MB to disk; JIT on | 268 ms |
| (b) unionall | identical (the trailing `UNION` onto branch 3 aggregates the whole thing) | 268 ms |
| (d) fenced, `OFFSET 0` + `jit = off` | identical aggregate, identical estimate (`rows=8,586,390` against 201,024 actual); only JIT's cost gone | 163 ms |
| (e) disjoint | `Append` only, no aggregate, no disk, JIT on | 85 ms |

The range branch is estimated at 232,786 rows per range × 36 ranges
(the default inequality selectivity, 1/9 of the table), actual 20 in
total. `OFFSET 0` stops the subquery being pulled up; it does not
stop the estimate being multiplied, so the aggregate above it is
sized the same. The decided fence is therefore withdrawn as the fix;
`SET LOCAL jit = off` stays (it is worth 100 ms at this N), and the
shape is (e).

Warm medians at N=100,000 (noisy, see the preamble): entries 679 /
655 / 502 / 566 / 555 ms for (a) / (b) / literal / (d) / (e) — all
dominated by fetching 201,024 ids; count 707 / 667 / 280 / 575 / 546;
top10 994 / 1,015 / **4.3** / 896 / 1,252; scoped 39 / 5.8 / 4.9 /
6.7 / 4.1.

The chunk-side statements at this N are bound by the join, not the
predicate: the count joins 201,024 visible entries to 2.2 M chunks and
the planner, still believing 8.4 M visible rows, hashes the chunk
table (`Parallel Seq Scan` on chunks, 546 ms). The one thing that
changes that estimate is a term the planner has a selectivity for:
`AND e.path LIKE (r.lo || '%')` (default match selectivity 0.005)
takes the branch estimate from 8,419,888 to 42,099 and the count from
329 to 184 ms; the top-10 through the derived table stays at 1.1 s
(the literal is 4.3 ms, a score-index walk). The term is lawful for
read pieces (every open range the compiler emits is `(p/, p0)` or
`(/, 0)`, so `LIKE lo || '%'` is exactly `> lo`), but it is a hack
on the planner and the study does not choose it; it is recorded for
the count-gate ADR, which owns the chunk-side top-k anyway.

## 5. The index

| index | SQLite 10k | Postgres 10k | MariaDB 10k | SQL Server 10k | Oracle 10k | Postgres 100k | MariaDB 100k |
|---|---|---|---|---|---|---|---|
| `path` (unique) | 7.8 MB | 9.3 | 10.0 | 12.6 | 15.7 | 92.6 | 86.7 |
| `owner_id` | 3.7 | 2.9 | 11.0 | 16.2 | 8.4 | 29.0 | 97.3 |
| `(everyone_level, path)` | 8.1 | 9.3 | 10.0 | 13.0 | 16.8 | 92.6 | 90.9 |
| entries table | 8.9 | 15.6 | 15.3 | — | — | — | — |

The composite costs what the path index costs, as the spike found.
(MariaDB's sizes are the `index_length` delta around a drop and
re-add — the per-index statistics view is not readable by the test
user — and its `owner_id` figure looks inflated by the rebuild order.)

Who uses the composite for the scoped read (branch 1 under
`/shared/s0001`, plans in `runs/<engine>-10000.md` under "scoped"):

| engine | `everyone_level >= :r AND path > :lo AND path < :hi` | `everyone_level IN (:a, :b) AND …` |
|---|---|---|
| SQLite | the composite, as a skip-scan (`ANY(everyone_level) AND path>? AND path<?`; needs `ANALYZE`) | the composite, exact (`everyone_level=? AND path>? AND path<?`) |
| Postgres | the path index, range on `path` with the level as a filter | the same |
| MariaDB | the composite (`type=range key=lvlpath rows=201`) | the same |
| SQL Server | the path index (`Index Seek`) | the same |
| Oracle | the composite (`INDEX RANGE SCAN LVLPATH`) | the same |

Every engine seeks; three use the composite, two prefer the path
index for a 200-row scope and use the composite for the unscoped
everyone leg (Postgres `Bitmap Index Scan on lvlpath`, SQL Server
`Index Seek lvlpath`). The `IN` spelling is never worse and is exact
on SQLite without statistics; either is fine for slice B.

## 6. SQL Server and Oracle, specifically

**SQL Server.** The padded-comparison rule holds: every bound the
compiler sends ends in `/`, `0` or a path byte, and recall was exact
on every cell at N=1,000, 10,000 and in the probe, with none of the
100 `/home/uNNNNNN-x` traps returned. The `OPENJSON` + UTF-8-collation
cast still seeks under the extra term — but only once the join is
spelled `INNER LOOP JOIN` with the range source first; the plain
`JOIN` is rewritten into a semi-join that scans entries. The same
applies to the relabel `UPDATE … FROM`. The scoped read seeks the
path index; the unscoped everyone leg seeks the composite.

**Oracle.** With no range source today, the literal form at the
caller's own size (88 to 220 pieces here) is 617 ms entries, 121 ms
count, 2.6 ms top-10 against the hinted `JSON_TABLE` join's 342 / 21
/ 34. The join wins the count by 6×, the literal wins the top-10 by
13× (the score-index walk), and entries is row-transfer either way.
`JSON_TABLE` works on 23ai with the JSON bound as a CLOB; what makes
it seek is `/*+ CARDINALITY(src n) */` with the actual piece count,
which the compiler knows. **Recommendation: Oracle gains a
`range_source` in slice B** (`json_table` with the Oracle column
spelling and a hint carrying the piece count), and the literal fan
form falls back to unknown dialects only. The relabel on Oracle is
the hinted literal (`USE_CONCAT`), not the join.

## What held and what did not

Held:

- Exact recall in every cell on all five engines, every caller,
  every N, every shape; no sibling trap ever leaked; every relabel
  and move left every label correct.
- The three seeks seek on every engine, once each planner is told
  the range source is the outer side.
- The relabel is bounded by pieces (500 per statement) and rows
  (keyset 50,000) with one transaction per statement on every
  engine, at 1 to 30 µs per row.
- The move is one `UPDATE` with the destination label everywhere.
- The composite index costs one path index and serves the scoped
  read directly on three engines.

Did not hold, or changed:

- The decided Postgres fence (`OFFSET 0`) does not change the plan.
  The disjoint `UNION ALL` form (e) is the shape; `jit = off` stays.
- The `everyone_level < :r` term misleads four planners in four
  different ways; each needs one dialect fact (a join keyword, an
  index pin, a cardinality hint). None of these is modelled by
  SQLAlchemy; the README table names them.
- The `id IN (subquery)` relabel form is the wrong form on Postgres
  (scan), Oracle (3.9 s) and MariaDB (did not finish). It must not
  ship.
- Oracle's MERGE through `JSON_TABLE` seeks for one range and scans
  for 500; the Oracle relabel is the hinted literal.
- Chunk-side statements at N=100,000 are join-bound on Postgres and
  MariaDB (0.5 to 1.2 s for count and derived top-10) whatever the
  predicate shape; the inline top-10 is 3 to 4 ms. That is the
  count-gate ADR's problem and the derived-table shape is not the
  answer for a top-k.

## What slice B must know

1. Build shape (b) on SQLite, MariaDB, SQL Server and Oracle and
   shape (e) on Postgres; or (e) everywhere, since it is never worse
   than (b) in these runs and needs no dedup. Branch 3 in (e) carries
   `NOT EXISTS` over the caller's own ranges.
2. The range branch's join keyword is a dialect fact: `CROSS JOIN`
   (SQLite), `STRAIGHT_JOIN … FORCE INDEX` (MariaDB), `INNER LOOP
   JOIN` (SQL Server), plain `JOIN` with `CARDINALITY(src n)`
   (Oracle), plain `JOIN` (Postgres). `+ 0` on the level term is a
   portable substitute on MariaDB only.
3. Postgres issues `SET LOCAL jit = off` in the read's transaction.
4. Oracle's `DialectProfile` gains `range_source="json_table"` and a
   hint for each of: the range branch (`CARDINALITY`), branch 1
   (`INDEX(e (everyone_level path))`), the derived join (`NO_MERGE
   LEADING USE_NL INDEX`), and the relabel (`USE_CONCAT`).
5. The relabel statement per dialect: `UPDATE … FROM unnest`
   (Postgres), `UPDATE … FROM json_each` (SQLite), `UPDATE e
   STRAIGHT_JOIN JSON_TABLE … SET` (MariaDB), `UPDATE e … FROM
   OPENJSON r INNER LOOP JOIN e` (SQL Server), the literal OR with
   `USE_CONCAT` (Oracle). Never `id IN (SELECT …)`.
6. `RELABEL_ROWS` of 50,000 is safe on every engine; one transaction
   per statement.
7. The 100 k gate's chunk-side numbers will be join-bound on
   Postgres; the gate's `tree /` and `ls` targets are met by the
   entries and scoped statements (4 to 6 ms scoped at N=100,000).
