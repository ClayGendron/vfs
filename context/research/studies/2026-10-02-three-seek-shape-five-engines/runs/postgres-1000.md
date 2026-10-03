## postgres — N=1,000 users: 23,113 entries, 66,000 chunks (3/file), 1,140 grant rows, 1,101 posture rows, 100 sibling traps

Load (tables, rows, indexes, statistics): 1s.

### Indexes

| index | size |
|---|---|
| `path` | 0.9 MB |
| `owner` | 0.3 MB |
| `lvlpath` | 0.9 MB |
| (entries table) | 1.6 MB |

### Callers

| caller | subjects | pieces (arms + owner) | bind bytes | compile us | visible entries |
|---|---|---|---|---|---|
| ordinary | u000042 | 22 | 630 | 51 | 2,034 |
| heavy group | u000000 | 22 | 630 | 32 | 2,034 |
| two subjects | u000042, u000000 | 64 | 1,804 | 69 | 2,013 |
| anonymous | — | 0 | 0 | 0 | 2,013 |
| system | — | 0 | 0 | 0 | 23,113 |

### Statements — cold = fresh connection, warm = median of 1 (ms); recall against the Python truth

Shapes: union, unionall, literal, fenced, disjoint. A blank cell is a shape that does not apply to that caller.

| caller | statement | union: cold / warm / recall | unionall: cold / warm / recall | literal: cold / warm / recall | fenced: cold / warm / recall | disjoint: cold / warm / recall |
|---|---|---|---|---|---|---|
| ordinary | entries | 6.0 / 3.0 / exact | 5.3 / 3.4 / exact | 21.5 / 2.8 / exact | 7.0 / 3.6 / exact | 6.2 / 2.2 / exact |
| ordinary | scoped | 4.5 / 2.1 / exact | 4.3 / 1.3 / exact | 3.7 / 1.3 / exact | 5.8 / 3.1 / exact | 4.5 / 1.8 / exact |
| ordinary | count | 8.9 / 6.0 / exact | 9.1 / 6.2 / exact | 8.3 / 5.5 / exact | 9.9 / 7.0 / exact | 17.9 / 15.2 / exact |
| ordinary | top10 | 10.2 / 7.2 / exact | 10.5 / 6.5 / exact | 4.6 / 2.3 / exact | 11.4 / 8.1 / exact | 10.7 / 7.2 / exact |
| heavy group | entries | 8.2 / 4.2 / exact | 5.9 / 3.0 / exact | 4.3 / 2.4 / exact | 10.3 / 3.1 / exact | 4.1 / 2.4 / exact |
| heavy group | scoped | 4.3 / 1.6 / exact | 4.0 / 1.6 / exact | 3.6 / 1.4 / exact | 4.9 / 2.5 / exact | 3.9 / 2.4 / exact |
| heavy group | count | 9.8 / 6.0 / exact | 9.3 / 6.0 / exact | 7.8 / 5.5 / exact | 8.9 / 5.9 / exact | 14.3 / 13.7 / exact |
| heavy group | top10 | 9.8 / 7.1 / exact | 9.4 / 7.0 / exact | 4.7 / 2.0 / exact | 12.5 / 19.5 / exact | 21.5 / 16.0 / exact |
| two subjects | entries | 11.4 / 4.7 / exact | 11.4 / 4.0 / exact | 6.2 / 3.1 / exact | 11.2 / 10.8 / exact | 15.2 / 8.2 / exact |
| two subjects | scoped | 9.9 / 5.5 / exact | 9.1 / 5.0 / exact | 8.7 / 4.7 / exact | 15.0 / 8.2 / exact | 10.0 / 5.8 / exact |
| two subjects | count | 10.5 / 6.8 / exact | 16.4 / 12.8 / exact | 11.3 / 14.7 / exact | 13.8 / 7.6 / exact | 26.4 / 13.3 / exact |
| two subjects | top10 | 10.6 / 7.6 / exact | 22.0 / 12.5 / exact | 15.3 / 6.0 / exact | 12.3 / 18.6 / exact | 18.0 / 8.8 / exact |
| anonymous | entries | 9.7 / 6.6 / exact |  |  |  |  |
| anonymous | scoped | 8.7 / 6.3 / exact |  |  |  |  |
| anonymous | count | 10.1 / 5.3 / exact |  |  |  |  |
| anonymous | top10 | 8.5 / 2.2 / exact |  |  |  |  |
| system | entries | 20.7 / 28.5 / exact |  |  |  |  |
| system | scoped | 7.7 / 4.9 / exact |  |  |  |  |
| system | count | 17.3 / 12.0 / exact |  |  |  |  |
| system | top10 | 4.0 / 2.0 / exact |  |  |  |  |

### Scoped read, branch 1 spelled `everyone_level >= :r` against `everyone_level IN (...)`

| caller | shape | `>=` cold / warm | `IN` cold / warm | recall |
|---|---|---|---|---|
| anonymous | union | 3.6 / 3.8 | 8.5 / 4.4 | exact |
| ordinary | union | 11.2 / 3.9 | 12.3 / 6.8 | exact |
| ordinary | unionall | 13.4 / 4.8 | 11.1 / 6.2 | exact |
| ordinary | literal | 9.0 / 3.7 | 10.7 / 5.4 | exact |
| ordinary | disjoint | 11.9 / 4.4 | 11.7 / 6.4 | exact |

### Plans

**ordinary / union / entries**

```
HashAggregate  (cost=2469.56..2747.90 rows=27834 width=8) (actual time=0.897..1.114 rows=2034 loops=1)
  Group Key: e.id
  Batches: 1  Memory Usage: 913kB
  Buffers: shared hit=131
  ->  Append  (cost=59.89..2399.97 rows=27834 width=8) (actual time=0.052..0.632 rows=2054 loops=1)
        Buffers: shared hit=131
        ->  Bitmap Heap Scan on ts_df1cf724_e e  (cost=59.89..277.05 rows=2013 width=8) (actual time=0.052..0.219 rows=2013 loops=1)
              Recheck Cond: (everyone_level >= '1'::smallint)
              Heap Blocks: exact=19
              Buffers: shared hit=31
              ->  Bitmap Index Scan on ts_df1cf724_e_lvlpath  (cost=0.00..59.38 rows=2013 width=0) (actual time=0.042..0.042 rows=2013 loops=1)
                    Index Cond: (everyone_level >= '1'::smallint)
                    Buffers: shared hit=12
        ->  Nested Loop  (cost=0.29..91.50 rows=10 width=8) (actual time=0.022..0.037 rows=1 loops=1)
              Buffers: shared hit=33
              ->  Function Scan on unnest ap  (cost=0.00..0.11 rows=11 width=32) (actual time=0.010..0.010 rows=11 loops=1)
              ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_1  (cost=0.29..8.31 rows=1 width=29) (actual time=0.002..0.002 rows=0 loops=11)
                    Index Cond: ((path)::text = (ap.value)::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 1
                    Buffers: shared hit=33
        ->  Nested Loop  (cost=0.29..1855.40 rows=25789 width=8) (actual time=0.016..0.194 rows=20 loops=1)
              Buffers: shared hit=60
              ->  Function Scan on ar  (cost=0.01..0.12 rows=11 width=64) (actual time=0.012..0.013 rows=11 loops=1)
              ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_2  (cost=0.29..145.22 rows=2344 width=29) (actual time=0.016..0.016 rows=2 loops=11)
                    Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 182
                    Buffers: shared hit=60
        ->  Index Scan using ts_df1cf724_e_owner on ts_df1cf724_e e_3  (cost=0.29..36.85 rows=22 width=8) (actual time=0.010..0.013 rows=20 loops=1)
              Index Cond: ((owner_id)::text = 'u000042'::text)
              Filter: (everyone_level < '1'::smallint)
              Rows Removed by Filter: 4
              Buffers: shared hit=7
Planning Time: 0.126 ms
Execution Time: 1.242 ms
```

**ordinary / unionall / entries**

```
HashAggregate  (cost=2469.56..2747.90 rows=27834 width=8) (actual time=0.877..1.102 rows=2034 loops=1)
  Group Key: e.id
  Batches: 1  Memory Usage: 913kB
  Buffers: shared hit=131
  ->  Append  (cost=59.89..2399.97 rows=27834 width=8) (actual time=0.052..0.632 rows=2054 loops=1)
        Buffers: shared hit=131
        ->  Bitmap Heap Scan on ts_df1cf724_e e  (cost=59.89..277.05 rows=2013 width=8) (actual time=0.052..0.221 rows=2013 loops=1)
              Recheck Cond: (everyone_level >= '1'::smallint)
              Heap Blocks: exact=19
              Buffers: shared hit=31
              ->  Bitmap Index Scan on ts_df1cf724_e_lvlpath  (cost=0.00..59.38 rows=2013 width=0) (actual time=0.046..0.046 rows=2013 loops=1)
                    Index Cond: (everyone_level >= '1'::smallint)
                    Buffers: shared hit=12
        ->  Nested Loop  (cost=0.29..91.50 rows=10 width=8) (actual time=0.023..0.039 rows=1 loops=1)
              Buffers: shared hit=33
              ->  Function Scan on unnest ap  (cost=0.00..0.11 rows=11 width=32) (actual time=0.004..0.005 rows=11 loops=1)
              ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_1  (cost=0.29..8.31 rows=1 width=29) (actual time=0.003..0.003 rows=0 loops=11)
                    Index Cond: ((path)::text = (ap.value)::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 1
                    Buffers: shared hit=33
        ->  Nested Loop  (cost=0.29..1855.40 rows=25789 width=8) (actual time=0.020..0.199 rows=20 loops=1)
              Buffers: shared hit=60
              ->  Function Scan on ar  (cost=0.01..0.12 rows=11 width=64) (actual time=0.013..0.014 rows=11 loops=1)
              ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_2  (cost=0.29..145.22 rows=2344 width=29) (actual time=0.016..0.016 rows=2 loops=11)
                    Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 182
                    Buffers: shared hit=60
        ->  Index Scan using ts_df1cf724_e_owner on ts_df1cf724_e e_3  (cost=0.29..36.85 rows=22 width=8) (actual time=0.006..0.009 rows=20 loops=1)
              Index Cond: ((owner_id)::text = 'u000042'::text)
              Filter: (everyone_level < '1'::smallint)
              Rows Removed by Filter: 4
              Buffers: shared hit=7
Planning Time: 0.177 ms
Execution Time: 1.218 ms
```

**ordinary / literal / entries**

```
Bitmap Heap Scan on ts_df1cf724_e e  (cost=165.67..512.40 rows=2059 width=8) (actual time=0.178..0.355 rows=2034 loops=1)
  Recheck Cond: ((everyone_level >= '1'::smallint) OR ((path)::text = ANY ('{/home/u000042,/shared/s0000,/shared/s0001,/shared/s0002,/shared/s0003,/shared/s0004,/shared/s0005,/shared/s0006,/shared/s0007,/shared/s0008,/shared/s0009}'::text[])) OR (((path)::text > '/home/u000042/'::text) AND ((path)::text < '/home/u0000420'::text)) OR (((path)::text > '/shared/s0000/'::text) AND ((path)::text < '/shared/s00000'::text)) OR (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text)) OR (((path)::text > '/shared/s0002/'::text) AND ((path)::text < '/shared/s00020'::text)) OR (((path)::text > '/shared/s0003/'::text) AND ((path)::text < '/shared/s00030'::text)) OR (((path)::text > '/shared/s0004/'::text) AND ((path)::text < '/shared/s00040'::text)) OR (((path)::text > '/shared/s0005/'::text) AND ((path)::text < '/shared/s00050'::text)) OR (((path)::text > '/shared/s0006/'::text) AND ((path)::text < '/shared/s00060'::text)) OR (((path)::text > '/shared/s0007/'::text) AND ((path)::text < '/shared/s00070'::text)) OR (((path)::text > '/shared/s0008/'::text) AND ((path)::text < '/shared/s00080'::text)) OR (((path)::text > '/shared/s0009/'::text) AND ((path)::text < '/shared/s00090'::text)) OR ((owner_id)::text = 'u000042'::text))
  Heap Blocks: exact=20
  Buffers: shared hit=88
  ->  BitmapOr  (cost=165.65..165.65 rows=2063 width=0) (actual time=0.165..0.166 rows=0 loops=1)
        Buffers: shared hit=68
        ->  Bitmap Index Scan on ts_df1cf724_e_lvlpath  (cost=0.00..59.38 rows=2013 width=0) (actual time=0.069..0.069 rows=2013 loops=1)
              Index Cond: (everyone_level >= '1'::smallint)
              Buffers: shared hit=12
        ->  Bitmap Index Scan on ts_df1cf724_e_path  (cost=0.00..47.25 rows=11 width=0) (actual time=0.019..0.019 rows=11 loops=1)
              Index Cond: ((path)::text = ANY ('{/home/u000042,/shared/s0000,/shared/s0001,/shared/s0002,/shared/s0003,/shared/s0004,/shared/s0005,/shared/s0006,/shared/s0007,/shared/s0008,/shared/s0009}'::text[]))
              Buffers: shared hit=22
        ->  Bitmap Index Scan on ts_df1cf724_e_path  (cost=0.00..4.30 rows=1 width=0) (actual time=0.002..0.002 rows=20 loops=1)
              Index Cond: (((path)::text > '/home/u000042/'::text) AND ((path)::text < '/home/u0000420'::text))
              Buffers: shared hit=2
        ->  Bitmap Index Scan on ts_df1cf724_e_path  (cost=0.00..4.30 rows=1 width=0) (actual time=0.006..0.007 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0000/'::text) AND ((path)::text < '/shared/s00000'::text))
              Buffers: shared hit=3
        ->  Bitmap Index Scan on ts_df1cf724_e_path  (cost=0.00..4.31 rows=2 width=0) (actual time=0.007..0.007 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
              Buffers: shared hit=3
        ->  Bitmap Index Scan on ts_df1cf724_e_path  (cost=0.00..4.30 rows=1 width=0) (actual time=0.006..0.007 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0002/'::text) AND ((path)::text < '/shared/s00020'::text))
              Buffers: shared hit=3
        ->  Bitmap Index Scan on ts_df1cf724_e_path  (cost=0.00..4.30 rows=1 width=0) (actual time=0.006..0.007 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0003/'::text) AND ((path)::text < '/shared/s00030'::text))
              Buffers: shared hit=3
        ->  Bitmap Index Scan on ts_df1cf724_e_path  (cost=0.00..4.31 rows=2 width=0) (actual time=0.006..0.006 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0004/'::text) AND ((path)::text < '/shared/s00040'::text))
              Buffers: shared hit=3
        ->  Bitmap Index Scan on ts_df1cf724_e_path  (cost=0.00..4.31 rows=2 width=0) (actual time=0.012..0.012 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0005/'::text) AND ((path)::text < '/shared/s00050'::text))
              Buffers: shared hit=3
        ->  Bitmap Index Scan on ts_df1cf724_e_path  (cost=0.00..4.31 rows=2 width=0) (actual time=0.006..0.006 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0006/'::text) AND ((path)::text < '/shared/s00060'::text))
              Buffers: shared hit=3
        ->  Bitmap Index Scan on ts_df1cf724_e_path  (cost=0.00..4.31 rows=2 width=0) (actual time=0.007..0.007 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0007/'::text) AND ((path)::text < '/shared/s00070'::text))
              Buffers: shared hit=3
        ->  Bitmap Index Scan on ts_df1cf724_e_path  (cost=0.00..4.31 rows=2 width=0) (actual time=0.007..0.007 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0008/'::text) AND ((path)::text < '/shared/s00080'::text))
              Buffers: shared hit=3
        ->  Bitmap Index Scan on ts_df1cf724_e_path  (cost=0.00..4.31 rows=2 width=0) (actual time=0.006..0.006 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0009/'::text) AND ((path)::text < '/shared/s00090'::text))
              Buffers: shared hit=3
        ->  Bitmap Index Scan on ts_df1cf724_e_owner  (cost=0.00..4.47 rows=24 width=0) (actual time=0.005..0.005 rows=24 loops=1)
              Index Cond: ((owner_id)::text = 'u000042'::text)
              Buffers: shared hit=2
Planning:
  Buffers: shared hit=15
Planning Time: 0.165 ms
Execution Time: 0.495 ms
```

**ordinary / fenced / entries**

```
HashAggregate  (cost=2469.56..2747.90 rows=27834 width=8) (actual time=0.905..1.119 rows=2034 loops=1)
  Group Key: e.id
  Batches: 1  Memory Usage: 913kB
  Buffers: shared hit=131
  ->  Append  (cost=59.89..2399.97 rows=27834 width=8) (actual time=0.058..0.645 rows=2054 loops=1)
        Buffers: shared hit=131
        ->  Bitmap Heap Scan on ts_df1cf724_e e  (cost=59.89..277.05 rows=2013 width=8) (actual time=0.057..0.234 rows=2013 loops=1)
              Recheck Cond: (everyone_level >= '1'::smallint)
              Heap Blocks: exact=19
              Buffers: shared hit=31
              ->  Bitmap Index Scan on ts_df1cf724_e_lvlpath  (cost=0.00..59.38 rows=2013 width=0) (actual time=0.052..0.052 rows=2013 loops=1)
                    Index Cond: (everyone_level >= '1'::smallint)
                    Buffers: shared hit=12
        ->  Nested Loop  (cost=0.29..91.50 rows=10 width=8) (actual time=0.017..0.035 rows=1 loops=1)
              Buffers: shared hit=33
              ->  Function Scan on unnest ap  (cost=0.00..0.11 rows=11 width=32) (actual time=0.009..0.009 rows=11 loops=1)
              ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_1  (cost=0.29..8.31 rows=1 width=29) (actual time=0.002..0.002 rows=0 loops=11)
                    Index Cond: ((path)::text = (ap.value)::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 1
                    Buffers: shared hit=33
        ->  Nested Loop  (cost=0.29..1855.40 rows=25789 width=8) (actual time=0.011..0.194 rows=20 loops=1)
              Buffers: shared hit=60
              ->  Function Scan on ar  (cost=0.01..0.12 rows=11 width=64) (actual time=0.003..0.004 rows=11 loops=1)
              ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_2  (cost=0.29..145.22 rows=2344 width=29) (actual time=0.017..0.017 rows=2 loops=11)
                    Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 182
                    Buffers: shared hit=60
        ->  Index Scan using ts_df1cf724_e_owner on ts_df1cf724_e e_3  (cost=0.29..36.85 rows=22 width=8) (actual time=0.008..0.011 rows=20 loops=1)
              Index Cond: ((owner_id)::text = 'u000042'::text)
              Filter: (everyone_level < '1'::smallint)
              Rows Removed by Filter: 4
              Buffers: shared hit=7
Planning Time: 0.158 ms
Execution Time: 1.244 ms
```

**ordinary / disjoint / entries**

```
Append  (cost=59.89..2406.06 rows=27832 width=8) (actual time=0.083..0.683 rows=2034 loops=1)
  Buffers: shared hit=131
  ->  Bitmap Heap Scan on ts_df1cf724_e e  (cost=59.89..277.05 rows=2013 width=8) (actual time=0.083..0.256 rows=2013 loops=1)
        Recheck Cond: (everyone_level >= '1'::smallint)
        Heap Blocks: exact=19
        Buffers: shared hit=31
        ->  Bitmap Index Scan on ts_df1cf724_e_lvlpath  (cost=0.00..59.38 rows=2013 width=0) (actual time=0.058..0.058 rows=2013 loops=1)
              Index Cond: (everyone_level >= '1'::smallint)
              Buffers: shared hit=12
  ->  Nested Loop  (cost=0.29..91.50 rows=10 width=8) (actual time=0.013..0.029 rows=1 loops=1)
        Buffers: shared hit=33
        ->  Function Scan on unnest ap  (cost=0.00..0.11 rows=11 width=32) (actual time=0.006..0.006 rows=11 loops=1)
        ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_1  (cost=0.29..8.31 rows=1 width=29) (actual time=0.002..0.002 rows=0 loops=11)
              Index Cond: ((path)::text = (ap.value)::text)
              Filter: (everyone_level < '1'::smallint)
              Rows Removed by Filter: 1
              Buffers: shared hit=33
  ->  Nested Loop  (cost=0.29..1855.40 rows=25789 width=8) (actual time=0.017..0.205 rows=20 loops=1)
        Buffers: shared hit=60
        ->  Function Scan on ar  (cost=0.01..0.12 rows=11 width=64) (actual time=0.009..0.010 rows=11 loops=1)
        ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_2  (cost=0.29..145.22 rows=2344 width=29) (actual time=0.017..0.017 rows=2 loops=11)
              Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
              Filter: (everyone_level < '1'::smallint)
              Rows Removed by Filter: 182
              Buffers: shared hit=60
  ->  Hash Anti Join  (cost=0.54..42.95 rows=20 width=8) (actual time=0.032..0.033 rows=0 loops=1)
        Hash Cond: ((e_3.path)::text = (x0p.value)::text)
        Buffers: shared hit=7
        ->  Nested Loop Anti Join  (cost=0.29..42.45 rows=20 width=29) (actual time=0.032..0.032 rows=0 loops=1)
              Join Filter: (((e_3.path)::text > (x0r.lo)::text) AND ((e_3.path)::text < (x0r.hi)::text))
              Buffers: shared hit=7
              ->  Index Scan using ts_df1cf724_e_owner on ts_df1cf724_e e_3  (cost=0.29..36.85 rows=22 width=29) (actual time=0.008..0.011 rows=20 loops=1)
                    Index Cond: ((owner_id)::text = 'u000042'::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 4
                    Buffers: shared hit=7
              ->  Function Scan on x0r  (cost=0.01..0.12 rows=11 width=64) (actual time=0.001..0.001 rows=1 loops=20)
        ->  Hash  (cost=0.11..0.11 rows=11 width=32) (never executed)
              ->  Function Scan on unnest x0p  (cost=0.00..0.11 rows=11 width=32) (never executed)
Planning Time: 0.202 ms
Execution Time: 0.791 ms
```

**ordinary / union / scoped**

```
Unique  (cost=34.45..34.47 rows=4 width=8) (actual time=0.170..0.209 rows=200 loops=1)
  Buffers: shared hit=24
  ->  Sort  (cost=34.45..34.46 rows=4 width=8) (actual time=0.170..0.181 rows=200 loops=1)
        Sort Key: e.id
        Sort Method: quicksort  Memory: 25kB
        Buffers: shared hit=24
        ->  Append  (cost=0.29..34.41 rows=4 width=8) (actual time=0.013..0.144 rows=200 loops=1)
              Buffers: shared hit=24
              ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e  (cost=0.29..8.49 rows=1 width=8) (actual time=0.012..0.040 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: (everyone_level >= '1'::smallint)
                    Buffers: shared hit=6
              ->  Hash Join  (cost=8.50..8.64 rows=1 width=8) (actual time=0.038..0.039 rows=0 loops=1)
                    Hash Cond: ((ap.value)::text = (e_1.path)::text)
                    Buffers: shared hit=6
                    ->  Function Scan on unnest ap  (cost=0.00..0.11 rows=11 width=32) (actual time=0.003..0.003 rows=1 loops=1)
                    ->  Hash  (cost=8.49..8.49 rows=1 width=29) (actual time=0.027..0.027 rows=0 loops=1)
                          Buckets: 1024  Batches: 1  Memory Usage: 8kB
                          Buffers: shared hit=6
                          ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_1  (cost=0.29..8.49 rows=1 width=29) (actual time=0.027..0.027 rows=0 loops=1)
                                Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 200
                                Buffers: shared hit=6
              ->  Nested Loop  (cost=0.29..8.77 rows=1 width=8) (actual time=0.019..0.019 rows=0 loops=1)
                    Join Filter: (((e_2.path)::text > (ar.lo)::text) AND ((e_2.path)::text < (ar.hi)::text))
                    Buffers: shared hit=6
                    ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_2  (cost=0.29..8.49 rows=1 width=29) (actual time=0.019..0.019 rows=0 loops=1)
                          Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                          Filter: (everyone_level < '1'::smallint)
                          Rows Removed by Filter: 200
                          Buffers: shared hit=6
                    ->  Function Scan on ar  (cost=0.01..0.12 rows=11 width=64) (never executed)
              ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_3  (cost=0.29..8.49 rows=1 width=8) (actual time=0.030..0.030 rows=0 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: ((everyone_level < '1'::smallint) AND ((owner_id)::text = 'u000042'::text))
                    Rows Removed by Filter: 200
                    Buffers: shared hit=6
Planning Time: 0.184 ms
Execution Time: 0.258 ms
```

**ordinary / unionall / scoped**

```
Unique  (cost=34.45..34.47 rows=4 width=8) (actual time=0.151..0.190 rows=200 loops=1)
  Buffers: shared hit=24
  ->  Sort  (cost=34.45..34.46 rows=4 width=8) (actual time=0.151..0.163 rows=200 loops=1)
        Sort Key: e.id
        Sort Method: quicksort  Memory: 25kB
        Buffers: shared hit=24
        ->  Append  (cost=0.29..34.41 rows=4 width=8) (actual time=0.015..0.140 rows=200 loops=1)
              Buffers: shared hit=24
              ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e  (cost=0.29..8.49 rows=1 width=8) (actual time=0.015..0.045 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: (everyone_level >= '1'::smallint)
                    Buffers: shared hit=6
              ->  Hash Join  (cost=8.50..8.64 rows=1 width=8) (actual time=0.030..0.031 rows=0 loops=1)
                    Hash Cond: ((ap.value)::text = (e_1.path)::text)
                    Buffers: shared hit=6
                    ->  Function Scan on unnest ap  (cost=0.00..0.11 rows=11 width=32) (actual time=0.003..0.003 rows=1 loops=1)
                    ->  Hash  (cost=8.49..8.49 rows=1 width=29) (actual time=0.022..0.022 rows=0 loops=1)
                          Buckets: 1024  Batches: 1  Memory Usage: 8kB
                          Buffers: shared hit=6
                          ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_1  (cost=0.29..8.49 rows=1 width=29) (actual time=0.022..0.022 rows=0 loops=1)
                                Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 200
                                Buffers: shared hit=6
              ->  Nested Loop  (cost=0.29..8.77 rows=1 width=8) (actual time=0.024..0.024 rows=0 loops=1)
                    Join Filter: (((e_2.path)::text > (ar.lo)::text) AND ((e_2.path)::text < (ar.hi)::text))
                    Buffers: shared hit=6
                    ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_2  (cost=0.29..8.49 rows=1 width=29) (actual time=0.024..0.024 rows=0 loops=1)
                          Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                          Filter: (everyone_level < '1'::smallint)
                          Rows Removed by Filter: 200
                          Buffers: shared hit=6
                    ->  Function Scan on ar  (cost=0.01..0.12 rows=11 width=64) (never executed)
              ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_3  (cost=0.29..8.49 rows=1 width=8) (actual time=0.024..0.024 rows=0 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: ((everyone_level < '1'::smallint) AND ((owner_id)::text = 'u000042'::text))
                    Rows Removed by Filter: 200
                    Buffers: shared hit=6
Planning Time: 0.166 ms
Execution Time: 0.231 ms
```

**ordinary / literal / scoped**

```
Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e  (cost=0.32..8.64 rows=1 width=8) (actual time=0.009..0.030 rows=200 loops=1)
  Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
  Buffers: shared hit=6
Planning:
  Buffers: shared hit=15
Planning Time: 0.194 ms
Execution Time: 0.042 ms
```

**ordinary / fenced / scoped**

```
Unique  (cost=34.45..34.47 rows=4 width=8) (actual time=0.202..0.243 rows=200 loops=1)
  Buffers: shared hit=24
  ->  Sort  (cost=34.45..34.46 rows=4 width=8) (actual time=0.202..0.215 rows=200 loops=1)
        Sort Key: e.id
        Sort Method: quicksort  Memory: 25kB
        Buffers: shared hit=24
        ->  Append  (cost=0.29..34.41 rows=4 width=8) (actual time=0.017..0.166 rows=200 loops=1)
              Buffers: shared hit=24
              ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e  (cost=0.29..8.49 rows=1 width=8) (actual time=0.017..0.047 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: (everyone_level >= '1'::smallint)
                    Buffers: shared hit=6
              ->  Hash Join  (cost=8.50..8.64 rows=1 width=8) (actual time=0.039..0.039 rows=0 loops=1)
                    Hash Cond: ((ap.value)::text = (e_1.path)::text)
                    Buffers: shared hit=6
                    ->  Function Scan on unnest ap  (cost=0.00..0.11 rows=11 width=32) (actual time=0.006..0.006 rows=1 loops=1)
                    ->  Hash  (cost=8.49..8.49 rows=1 width=29) (actual time=0.022..0.022 rows=0 loops=1)
                          Buckets: 1024  Batches: 1  Memory Usage: 8kB
                          Buffers: shared hit=6
                          ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_1  (cost=0.29..8.49 rows=1 width=29) (actual time=0.022..0.022 rows=0 loops=1)
                                Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 200
                                Buffers: shared hit=6
              ->  Nested Loop  (cost=0.29..8.77 rows=1 width=8) (actual time=0.033..0.033 rows=0 loops=1)
                    Join Filter: (((e_2.path)::text > (ar.lo)::text) AND ((e_2.path)::text < (ar.hi)::text))
                    Buffers: shared hit=6
                    ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_2  (cost=0.29..8.49 rows=1 width=29) (actual time=0.032..0.032 rows=0 loops=1)
                          Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                          Filter: (everyone_level < '1'::smallint)
                          Rows Removed by Filter: 200
                          Buffers: shared hit=6
                    ->  Function Scan on ar  (cost=0.01..0.12 rows=11 width=64) (never executed)
              ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_3  (cost=0.29..8.49 rows=1 width=8) (actual time=0.030..0.030 rows=0 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: ((everyone_level < '1'::smallint) AND ((owner_id)::text = 'u000042'::text))
                    Rows Removed by Filter: 200
                    Buffers: shared hit=6
Planning Time: 0.264 ms
Execution Time: 0.288 ms
```

**ordinary / disjoint / scoped**

```
Append  (cost=0.29..34.85 rows=4 width=8) (actual time=0.023..0.146 rows=200 loops=1)
  Buffers: shared hit=24
  ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e  (cost=0.29..8.49 rows=1 width=8) (actual time=0.023..0.050 rows=200 loops=1)
        Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
        Filter: (everyone_level >= '1'::smallint)
        Buffers: shared hit=6
  ->  Hash Join  (cost=8.50..8.64 rows=1 width=8) (actual time=0.035..0.035 rows=0 loops=1)
        Hash Cond: ((ap.value)::text = (e_1.path)::text)
        Buffers: shared hit=6
        ->  Function Scan on unnest ap  (cost=0.00..0.11 rows=11 width=32) (actual time=0.007..0.007 rows=1 loops=1)
        ->  Hash  (cost=8.49..8.49 rows=1 width=29) (actual time=0.024..0.024 rows=0 loops=1)
              Buckets: 1024  Batches: 1  Memory Usage: 8kB
              Buffers: shared hit=6
              ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_1  (cost=0.29..8.49 rows=1 width=29) (actual time=0.023..0.023 rows=0 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 200
                    Buffers: shared hit=6
  ->  Nested Loop  (cost=0.29..8.77 rows=1 width=8) (actual time=0.019..0.019 rows=0 loops=1)
        Join Filter: (((e_2.path)::text > (ar.lo)::text) AND ((e_2.path)::text < (ar.hi)::text))
        Buffers: shared hit=6
        ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_2  (cost=0.29..8.49 rows=1 width=29) (actual time=0.019..0.019 rows=0 loops=1)
              Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
              Filter: (everyone_level < '1'::smallint)
              Rows Removed by Filter: 200
              Buffers: shared hit=6
        ->  Function Scan on ar  (cost=0.01..0.12 rows=11 width=64) (never executed)
  ->  Nested Loop Anti Join  (cost=8.51..8.93 rows=1 width=8) (actual time=0.025..0.025 rows=0 loops=1)
        Join Filter: (((e_3.path)::text > (x0r.lo)::text) AND ((e_3.path)::text < (x0r.hi)::text))
        Buffers: shared hit=6
        ->  Hash Right Anti Join  (cost=8.51..8.65 rows=1 width=29) (actual time=0.025..0.025 rows=0 loops=1)
              Hash Cond: ((x0p.value)::text = (e_3.path)::text)
              Buffers: shared hit=6
              ->  Function Scan on unnest x0p  (cost=0.00..0.11 rows=11 width=32) (never executed)
              ->  Hash  (cost=8.49..8.49 rows=1 width=29) (actual time=0.021..0.022 rows=0 loops=1)
                    Buckets: 1024  Batches: 1  Memory Usage: 8kB
                    Buffers: shared hit=6
                    ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_3  (cost=0.29..8.49 rows=1 width=29) (actual time=0.021..0.021 rows=0 loops=1)
                          Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                          Filter: ((everyone_level < '1'::smallint) AND ((owner_id)::text = 'u000042'::text))
                          Rows Removed by Filter: 200
                          Buffers: shared hit=6
        ->  Function Scan on x0r  (cost=0.01..0.12 rows=11 width=64) (never executed)
Planning Time: 0.240 ms
Execution Time: 0.180 ms
```

**ordinary / union / count**

```
Aggregate  (cost=4558.75..4558.76 rows=1 width=8) (actual time=11.096..11.101 rows=1 loops=1)
  Buffers: shared hit=552
  ->  Hash Join  (cost=3095.82..4350.11 rows=83456 width=0) (actual time=1.666..10.791 rows=6060 loops=1)
        Hash Cond: (c.entry_id = e.id)
        Buffers: shared hit=552
        ->  Seq Scan on ts_df1cf724_c c  (cost=0.00..1081.00 rows=66000 width=8) (actual time=0.007..4.804 rows=66000 loops=1)
              Buffers: shared hit=421
        ->  Hash  (cost=2747.90..2747.90 rows=27834 width=8) (actual time=1.316..1.320 rows=2034 loops=1)
              Buckets: 32768  Batches: 1  Memory Usage: 336kB
              Buffers: shared hit=131
              ->  HashAggregate  (cost=2469.56..2747.90 rows=27834 width=8) (actual time=0.872..1.121 rows=2034 loops=1)
                    Group Key: e.id
                    Batches: 1  Memory Usage: 913kB
                    Buffers: shared hit=131
                    ->  Append  (cost=59.89..2399.97 rows=27834 width=8) (actual time=0.055..0.622 rows=2054 loops=1)
                          Buffers: shared hit=131
                          ->  Bitmap Heap Scan on ts_df1cf724_e e  (cost=59.89..277.05 rows=2013 width=8) (actual time=0.055..0.224 rows=2013 loops=1)
                                Recheck Cond: (everyone_level >= '1'::smallint)
                                Heap Blocks: exact=19
                                Buffers: shared hit=31
                                ->  Bitmap Index Scan on ts_df1cf724_e_lvlpath  (cost=0.00..59.38 rows=2013 width=0) (actual time=0.051..0.051 rows=2013 loops=1)
                                      Index Cond: (everyone_level >= '1'::smallint)
                                      Buffers: shared hit=12
                          ->  Nested Loop  (cost=0.29..91.50 rows=10 width=8) (actual time=0.012..0.027 rows=1 loops=1)
                                Buffers: shared hit=33
                                ->  Function Scan on unnest ap  (cost=0.00..0.11 rows=11 width=32) (actual time=0.004..0.005 rows=11 loops=1)
                                ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_1  (cost=0.29..8.31 rows=1 width=29) (actual time=0.002..0.002 rows=0 loops=11)
                                      Index Cond: ((path)::text = (ap.value)::text)
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 1
                                      Buffers: shared hit=33
                          ->  Nested Loop  (cost=0.29..1855.40 rows=25789 width=8) (actual time=0.016..0.193 rows=20 loops=1)
                                Buffers: shared hit=60
                                ->  Function Scan on ar  (cost=0.01..0.12 rows=11 width=64) (actual time=0.011..0.012 rows=11 loops=1)
                                ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_2  (cost=0.29..145.22 rows=2344 width=29) (actual time=0.016..0.016 rows=2 loops=11)
                                      Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 182
                                      Buffers: shared hit=60
                          ->  Index Scan using ts_df1cf724_e_owner on ts_df1cf724_e e_3  (cost=0.29..36.85 rows=22 width=8) (actual time=0.010..0.014 rows=20 loops=1)
                                Index Cond: ((owner_id)::text = 'u000042'::text)
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 4
                                Buffers: shared hit=7
Planning Time: 0.181 ms
Execution Time: 11.155 ms
```

**ordinary / unionall / count**

```
Aggregate  (cost=4558.75..4558.76 rows=1 width=8) (actual time=10.285..10.290 rows=1 loops=1)
  Buffers: shared hit=552
  ->  Hash Join  (cost=3095.82..4350.11 rows=83456 width=0) (actual time=1.784..9.990 rows=6060 loops=1)
        Hash Cond: (c.entry_id = e.id)
        Buffers: shared hit=552
        ->  Seq Scan on ts_df1cf724_c c  (cost=0.00..1081.00 rows=66000 width=8) (actual time=0.007..4.369 rows=66000 loops=1)
              Buffers: shared hit=421
        ->  Hash  (cost=2747.90..2747.90 rows=27834 width=8) (actual time=1.442..1.446 rows=2034 loops=1)
              Buckets: 32768  Batches: 1  Memory Usage: 336kB
              Buffers: shared hit=131
              ->  HashAggregate  (cost=2469.56..2747.90 rows=27834 width=8) (actual time=0.929..1.187 rows=2034 loops=1)
                    Group Key: e.id
                    Batches: 1  Memory Usage: 913kB
                    Buffers: shared hit=131
                    ->  Append  (cost=59.89..2399.97 rows=27834 width=8) (actual time=0.055..0.662 rows=2054 loops=1)
                          Buffers: shared hit=131
                          ->  Bitmap Heap Scan on ts_df1cf724_e e  (cost=59.89..277.05 rows=2013 width=8) (actual time=0.054..0.234 rows=2013 loops=1)
                                Recheck Cond: (everyone_level >= '1'::smallint)
                                Heap Blocks: exact=19
                                Buffers: shared hit=31
                                ->  Bitmap Index Scan on ts_df1cf724_e_lvlpath  (cost=0.00..59.38 rows=2013 width=0) (actual time=0.049..0.049 rows=2013 loops=1)
                                      Index Cond: (everyone_level >= '1'::smallint)
                                      Buffers: shared hit=12
                          ->  Nested Loop  (cost=0.29..91.50 rows=10 width=8) (actual time=0.022..0.042 rows=1 loops=1)
                                Buffers: shared hit=33
                                ->  Function Scan on unnest ap  (cost=0.00..0.11 rows=11 width=32) (actual time=0.011..0.012 rows=11 loops=1)
                                ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_1  (cost=0.29..8.31 rows=1 width=29) (actual time=0.002..0.002 rows=0 loops=11)
                                      Index Cond: ((path)::text = (ap.value)::text)
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 1
                                      Buffers: shared hit=33
                          ->  Nested Loop  (cost=0.29..1855.40 rows=25789 width=8) (actual time=0.017..0.197 rows=20 loops=1)
                                Buffers: shared hit=60
                                ->  Function Scan on ar  (cost=0.01..0.12 rows=11 width=64) (actual time=0.012..0.013 rows=11 loops=1)
                                ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_2  (cost=0.29..145.22 rows=2344 width=29) (actual time=0.016..0.016 rows=2 loops=11)
                                      Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 182
                                      Buffers: shared hit=60
                          ->  Index Scan using ts_df1cf724_e_owner on ts_df1cf724_e e_3  (cost=0.29..36.85 rows=22 width=8) (actual time=0.009..0.013 rows=20 loops=1)
                                Index Cond: ((owner_id)::text = 'u000042'::text)
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 4
                                Buffers: shared hit=7
Planning Time: 0.195 ms
Execution Time: 10.338 ms
```

**ordinary / literal / count**

```
Aggregate  (cost=1807.12..1807.13 rows=1 width=8) (actual time=10.191..10.197 rows=1 loops=1)
  Buffers: shared hit=509
  ->  Hash Join  (cost=538.14..1792.42 rows=5880 width=0) (actual time=0.870..9.888 rows=6060 loops=1)
        Hash Cond: (c.entry_id = e.id)
        Buffers: shared hit=509
        ->  Seq Scan on ts_df1cf724_c c  (cost=0.00..1081.00 rows=66000 width=8) (actual time=0.006..4.719 rows=66000 loops=1)
              Buffers: shared hit=421
        ->  Hash  (cost=512.40..512.40 rows=2059 width=8) (actual time=0.493..0.497 rows=2034 loops=1)
              Buckets: 4096  Batches: 1  Memory Usage: 112kB
              Buffers: shared hit=88
              ->  Bitmap Heap Scan on ts_df1cf724_e e  (cost=165.67..512.40 rows=2059 width=8) (actual time=0.144..0.318 rows=2034 loops=1)
                    Recheck Cond: ((everyone_level >= '1'::smallint) OR ((path)::text = ANY ('{/home/u000042,/shared/s0000,/shared/s0001,/shared/s0002,/shared/s0003,/shared/s0004,/shared/s0005,/shared/s0006,/shared/s0007,/shared/s0008,/shared/s0009}'::text[])) OR (((path)::text > '/home/u000042/'::text) AND ((path)::text < '/home/u0000420'::text)) OR (((path)::text > '/shared/s0000/'::text) AND ((path)::text < '/shared/s00000'::text)) OR (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text)) OR (((path)::text > '/shared/s0002/'::text) AND ((path)::text < '/shared/s00020'::text)) OR (((path)::text > '/shared/s0003/'::text) AND ((path)::text < '/shared/s00030'::text)) OR (((path)::text > '/shared/s0004/'::text) AND ((path)::text < '/shared/s00040'::text)) OR (((path)::text > '/shared/s0005/'::text) AND ((path)::text < '/shared/s00050'::text)) OR (((path)::text > '/shared/s0006/'::text) AND ((path)::text < '/shared/s00060'::text)) OR (((path)::text > '/shared/s0007/'::text) AND ((path)::text < '/shared/s00070'::text)) OR (((path)::text > '/shared/s0008/'::text) AND ((path)::text < '/shared/s00080'::text)) OR (((path)::text > '/shared/s0009/'::text) AND ((path)::text < '/shared/s00090'::text)) OR ((owner_id)::text = 'u000042'::text))
                    Heap Blocks: exact=20
                    Buffers: shared hit=88
                    ->  BitmapOr  (cost=165.65..165.65 rows=2063 width=0) (actual time=0.140..0.143 rows=0 loops=1)
                          Buffers: shared hit=68
                          ->  Bitmap Index Scan on ts_df1cf724_e_lvlpath  (cost=0.00..59.38 rows=2013 width=0) (actual time=0.047..0.047 rows=2013 loops=1)
                                Index Cond: (everyone_level >= '1'::smallint)
                                Buffers: shared hit=12
                          ->  Bitmap Index Scan on ts_df1cf724_e_path  (cost=0.00..47.25 rows=11 width=0) (actual time=0.017..0.017 rows=11 loops=1)
                                Index Cond: ((path)::text = ANY ('{/home/u000042,/shared/s0000,/shared/s0001,/shared/s0002,/shared/s0003,/shared/s0004,/shared/s0005,/shared/s0006,/shared/s0007,/shared/s0008,/shared/s0009}'::text[]))
                                Buffers: shared hit=22
                          ->  Bitmap Index Scan on ts_df1cf724_e_path  (cost=0.00..4.30 rows=1 width=0) (actual time=0.002..0.002 rows=20 loops=1)
                                Index Cond: (((path)::text > '/home/u000042/'::text) AND ((path)::text < '/home/u0000420'::text))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on ts_df1cf724_e_path  (cost=0.00..4.30 rows=1 width=0) (actual time=0.006..0.007 rows=200 loops=1)
                                Index Cond: (((path)::text > '/shared/s0000/'::text) AND ((path)::text < '/shared/s00000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on ts_df1cf724_e_path  (cost=0.00..4.31 rows=2 width=0) (actual time=0.007..0.007 rows=200 loops=1)
                                Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on ts_df1cf724_e_path  (cost=0.00..4.30 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
                                Index Cond: (((path)::text > '/shared/s0002/'::text) AND ((path)::text < '/shared/s00020'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on ts_df1cf724_e_path  (cost=0.00..4.30 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
                                Index Cond: (((path)::text > '/shared/s0003/'::text) AND ((path)::text < '/shared/s00030'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on ts_df1cf724_e_path  (cost=0.00..4.31 rows=2 width=0) (actual time=0.006..0.006 rows=200 loops=1)
                                Index Cond: (((path)::text > '/shared/s0004/'::text) AND ((path)::text < '/shared/s00040'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on ts_df1cf724_e_path  (cost=0.00..4.31 rows=2 width=0) (actual time=0.009..0.009 rows=200 loops=1)
                                Index Cond: (((path)::text > '/shared/s0005/'::text) AND ((path)::text < '/shared/s00050'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on ts_df1cf724_e_path  (cost=0.00..4.31 rows=2 width=0) (actual time=0.006..0.007 rows=200 loops=1)
                                Index Cond: (((path)::text > '/shared/s0006/'::text) AND ((path)::text < '/shared/s00060'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on ts_df1cf724_e_path  (cost=0.00..4.31 rows=2 width=0) (actual time=0.007..0.007 rows=200 loops=1)
                                Index Cond: (((path)::text > '/shared/s0007/'::text) AND ((path)::text < '/shared/s00070'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on ts_df1cf724_e_path  (cost=0.00..4.31 rows=2 width=0) (actual time=0.007..0.007 rows=200 loops=1)
                                Index Cond: (((path)::text > '/shared/s0008/'::text) AND ((path)::text < '/shared/s00080'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on ts_df1cf724_e_path  (cost=0.00..4.31 rows=2 width=0) (actual time=0.006..0.006 rows=200 loops=1)
                                Index Cond: (((path)::text > '/shared/s0009/'::text) AND ((path)::text < '/shared/s00090'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on ts_df1cf724_e_owner  (cost=0.00..4.47 rows=24 width=0) (actual time=0.005..0.005 rows=24 loops=1)
                                Index Cond: ((owner_id)::text = 'u000042'::text)
                                Buffers: shared hit=2
Planning:
  Buffers: shared hit=27
Planning Time: 0.267 ms
Execution Time: 10.303 ms
```

**ordinary / fenced / count**

```
Aggregate  (cost=4558.75..4558.76 rows=1 width=8) (actual time=11.046..11.049 rows=1 loops=1)
  Buffers: shared hit=552
  ->  Hash Join  (cost=3095.82..4350.11 rows=83456 width=0) (actual time=1.770..10.731 rows=6060 loops=1)
        Hash Cond: (c.entry_id = e.id)
        Buffers: shared hit=552
        ->  Seq Scan on ts_df1cf724_c c  (cost=0.00..1081.00 rows=66000 width=8) (actual time=0.008..4.680 rows=66000 loops=1)
              Buffers: shared hit=421
        ->  Hash  (cost=2747.90..2747.90 rows=27834 width=8) (actual time=1.402..1.404 rows=2034 loops=1)
              Buckets: 32768  Batches: 1  Memory Usage: 336kB
              Buffers: shared hit=131
              ->  HashAggregate  (cost=2469.56..2747.90 rows=27834 width=8) (actual time=0.955..1.183 rows=2034 loops=1)
                    Group Key: e.id
                    Batches: 1  Memory Usage: 913kB
                    Buffers: shared hit=131
                    ->  Append  (cost=59.89..2399.97 rows=27834 width=8) (actual time=0.061..0.685 rows=2054 loops=1)
                          Buffers: shared hit=131
                          ->  Bitmap Heap Scan on ts_df1cf724_e e  (cost=59.89..277.05 rows=2013 width=8) (actual time=0.060..0.240 rows=2013 loops=1)
                                Recheck Cond: (everyone_level >= '1'::smallint)
                                Heap Blocks: exact=19
                                Buffers: shared hit=31
                                ->  Bitmap Index Scan on ts_df1cf724_e_lvlpath  (cost=0.00..59.38 rows=2013 width=0) (actual time=0.054..0.054 rows=2013 loops=1)
                                      Index Cond: (everyone_level >= '1'::smallint)
                                      Buffers: shared hit=12
                          ->  Nested Loop  (cost=0.29..91.50 rows=10 width=8) (actual time=0.024..0.043 rows=1 loops=1)
                                Buffers: shared hit=33
                                ->  Function Scan on unnest ap  (cost=0.00..0.11 rows=11 width=32) (actual time=0.012..0.013 rows=11 loops=1)
                                ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_1  (cost=0.29..8.31 rows=1 width=29) (actual time=0.002..0.002 rows=0 loops=11)
                                      Index Cond: ((path)::text = (ap.value)::text)
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 1
                                      Buffers: shared hit=33
                          ->  Nested Loop  (cost=0.29..1855.40 rows=25789 width=8) (actual time=0.028..0.211 rows=20 loops=1)
                                Buffers: shared hit=60
                                ->  Function Scan on ar  (cost=0.01..0.12 rows=11 width=64) (actual time=0.017..0.018 rows=11 loops=1)
                                ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_2  (cost=0.29..145.22 rows=2344 width=29) (actual time=0.017..0.017 rows=2 loops=11)
                                      Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 182
                                      Buffers: shared hit=60
                          ->  Index Scan using ts_df1cf724_e_owner on ts_df1cf724_e e_3  (cost=0.29..36.85 rows=22 width=8) (actual time=0.013..0.016 rows=20 loops=1)
                                Index Cond: ((owner_id)::text = 'u000042'::text)
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 4
                                Buffers: shared hit=7
Planning Time: 0.211 ms
Execution Time: 11.112 ms
```

**ordinary / disjoint / count**

```
Finalize Aggregate  (cost=5326.69..5326.70 rows=1 width=8) (actual time=22.729..24.186 rows=1 loops=1)
  Buffers: shared hit=1466
  ->  Gather  (cost=5326.48..5326.69 rows=2 width=8) (actual time=12.322..24.176 rows=3 loops=1)
        Workers Planned: 2
        Workers Launched: 2
        Buffers: shared hit=1466
        ->  Partial Aggregate  (cost=4326.48..4326.49 rows=1 width=8) (actual time=14.883..14.886 rows=1 loops=3)
              Buffers: shared hit=1466
              ->  Hash Join  (cost=1906.29..4239.55 rows=34771 width=0) (actual time=14.316..14.773 rows=2020 loops=3)
                    Hash Cond: (e.id = c.entry_id)
                    Buffers: shared hit=1466
                    ->  Parallel Append  (cost=0.29..1913.38 rows=11596 width=8) (actual time=0.059..0.272 rows=678 loops=3)
                          Buffers: shared hit=133
                          ->  Nested Loop  (cost=0.29..1855.40 rows=25789 width=8) (actual time=0.026..0.252 rows=20 loops=1)
                                Buffers: shared hit=61
                                ->  Function Scan on ar  (cost=0.01..0.12 rows=11 width=64) (actual time=0.007..0.009 rows=11 loops=1)
                                ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e  (cost=0.29..145.22 rows=2344 width=29) (actual time=0.021..0.021 rows=2 loops=11)
                                      Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 182
                                      Buffers: shared hit=61
                          ->  Bitmap Heap Scan on ts_df1cf724_e e_1  (cost=59.89..277.05 rows=2013 width=8) (actual time=0.115..0.314 rows=2013 loops=1)
                                Recheck Cond: (everyone_level >= '1'::smallint)
                                Buffers: shared hit=32
                                ->  Bitmap Index Scan on ts_df1cf724_e_lvlpath  (cost=0.00..59.38 rows=2013 width=0) (actual time=0.096..0.096 rows=2013 loops=1)
                                      Index Cond: (everyone_level >= '1'::smallint)
                                      Buffers: shared hit=13
                          ->  Nested Loop  (cost=0.29..91.50 rows=10 width=8) (actual time=0.006..0.048 rows=1 loops=1)
                                Buffers: shared hit=33
                                ->  Function Scan on unnest ap  (cost=0.00..0.11 rows=11 width=32) (actual time=0.001..0.002 rows=11 loops=1)
                                ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_2  (cost=0.29..8.31 rows=1 width=29) (actual time=0.003..0.003 rows=0 loops=11)
                                      Index Cond: ((path)::text = (ap.value)::text)
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 1
                                      Buffers: shared hit=33
                          ->  Hash Anti Join  (cost=0.54..42.95 rows=20 width=8) (actual time=0.031..0.033 rows=0 loops=1)
                                Hash Cond: ((e_3.path)::text = (x0p.value)::text)
                                Buffers: shared hit=7
                                ->  Nested Loop Anti Join  (cost=0.29..42.45 rows=20 width=29) (actual time=0.030..0.031 rows=0 loops=1)
                                      Join Filter: (((e_3.path)::text > (x0r.lo)::text) AND ((e_3.path)::text < (x0r.hi)::text))
                                      Buffers: shared hit=7
                                      ->  Index Scan using ts_df1cf724_e_owner on ts_df1cf724_e e_3  (cost=0.29..36.85 rows=22 width=29) (actual time=0.013..0.020 rows=20 loops=1)
                                            Index Cond: ((owner_id)::text = 'u000042'::text)
                                            Filter: (everyone_level < '1'::smallint)
                                            Rows Removed by Filter: 4
                                            Buffers: shared hit=7
                                      ->  Function Scan on x0r  (cost=0.01..0.12 rows=11 width=64) (actual time=0.000..0.000 rows=1 loops=20)
                                ->  Hash  (cost=0.11..0.11 rows=11 width=32) (never executed)
                                      ->  Function Scan on unnest x0p  (cost=0.00..0.11 rows=11 width=32) (never executed)
                    ->  Hash  (cost=1081.00..1081.00 rows=66000 width=8) (actual time=13.899..13.900 rows=66000 loops=3)
                          Buckets: 131072  Batches: 1  Memory Usage: 3603kB
                          Buffers: shared hit=1263
                          ->  Seq Scan on ts_df1cf724_c c  (cost=0.00..1081.00 rows=66000 width=8) (actual time=0.009..5.725 rows=66000 loops=3)
                                Buffers: shared hit=1263
Planning Time: 0.210 ms
Execution Time: 24.265 ms
```

**ordinary / union / top10**

```
Limit  (cost=2469.85..5772.01 rows=10 width=12) (actual time=2.810..21.033 rows=10 loops=1)
  Buffers: shared hit=237
  ->  Nested Loop  (cost=2469.85..27560935.28 rows=83456 width=12) (actual time=2.809..21.031 rows=10 loops=1)
        Join Filter: (c.entry_id = e.id)
        Rows Removed by Join Filter: 202991
        Buffers: shared hit=237
        ->  Index Scan using ts_df1cf724_c_score on ts_df1cf724_c c  (cost=0.29..3710.24 rows=66000 width=20) (actual time=0.013..0.164 rows=104 loops=1)
              Buffers: shared hit=106
        ->  Materialize  (cost=2469.56..2887.07 rows=27834 width=8) (actual time=0.009..0.117 rows=1952 loops=104)
              Buffers: shared hit=131
              ->  HashAggregate  (cost=2469.56..2747.90 rows=27834 width=8) (actual time=0.957..1.181 rows=2034 loops=1)
                    Group Key: e.id
                    Batches: 1  Memory Usage: 913kB
                    Buffers: shared hit=131
                    ->  Append  (cost=59.89..2399.97 rows=27834 width=8) (actual time=0.059..0.675 rows=2054 loops=1)
                          Buffers: shared hit=131
                          ->  Bitmap Heap Scan on ts_df1cf724_e e  (cost=59.89..277.05 rows=2013 width=8) (actual time=0.058..0.237 rows=2013 loops=1)
                                Recheck Cond: (everyone_level >= '1'::smallint)
                                Heap Blocks: exact=19
                                Buffers: shared hit=31
                                ->  Bitmap Index Scan on ts_df1cf724_e_lvlpath  (cost=0.00..59.38 rows=2013 width=0) (actual time=0.052..0.053 rows=2013 loops=1)
                                      Index Cond: (everyone_level >= '1'::smallint)
                                      Buffers: shared hit=12
                          ->  Nested Loop  (cost=0.29..91.50 rows=10 width=8) (actual time=0.033..0.053 rows=1 loops=1)
                                Buffers: shared hit=33
                                ->  Function Scan on unnest ap  (cost=0.00..0.11 rows=11 width=32) (actual time=0.004..0.005 rows=11 loops=1)
                                ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_1  (cost=0.29..8.31 rows=1 width=29) (actual time=0.004..0.004 rows=0 loops=11)
                                      Index Cond: ((path)::text = (ap.value)::text)
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 1
                                      Buffers: shared hit=33
                          ->  Nested Loop  (cost=0.29..1855.40 rows=25789 width=8) (actual time=0.026..0.210 rows=20 loops=1)
                                Buffers: shared hit=60
                                ->  Function Scan on ar  (cost=0.01..0.12 rows=11 width=64) (actual time=0.014..0.016 rows=11 loops=1)
                                ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_2  (cost=0.29..145.22 rows=2344 width=29) (actual time=0.017..0.017 rows=2 loops=11)
                                      Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 182
                                      Buffers: shared hit=60
                          ->  Index Scan using ts_df1cf724_e_owner on ts_df1cf724_e e_3  (cost=0.29..36.85 rows=22 width=8) (actual time=0.008..0.011 rows=20 loops=1)
                                Index Cond: ((owner_id)::text = 'u000042'::text)
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 4
                                Buffers: shared hit=7
Planning Time: 0.211 ms
Execution Time: 21.108 ms
```

**ordinary / unionall / top10**

```
Limit  (cost=2469.85..5772.01 rows=10 width=12) (actual time=2.706..20.747 rows=10 loops=1)
  Buffers: shared hit=237
  ->  Nested Loop  (cost=2469.85..27560935.28 rows=83456 width=12) (actual time=2.706..20.745 rows=10 loops=1)
        Join Filter: (c.entry_id = e.id)
        Rows Removed by Join Filter: 202991
        Buffers: shared hit=237
        ->  Index Scan using ts_df1cf724_c_score on ts_df1cf724_c c  (cost=0.29..3710.24 rows=66000 width=20) (actual time=0.009..0.165 rows=104 loops=1)
              Buffers: shared hit=106
        ->  Materialize  (cost=2469.56..2887.07 rows=27834 width=8) (actual time=0.009..0.116 rows=1952 loops=104)
              Buffers: shared hit=131
              ->  HashAggregate  (cost=2469.56..2747.90 rows=27834 width=8) (actual time=0.876..1.094 rows=2034 loops=1)
                    Group Key: e.id
                    Batches: 1  Memory Usage: 913kB
                    Buffers: shared hit=131
                    ->  Append  (cost=59.89..2399.97 rows=27834 width=8) (actual time=0.051..0.637 rows=2054 loops=1)
                          Buffers: shared hit=131
                          ->  Bitmap Heap Scan on ts_df1cf724_e e  (cost=59.89..277.05 rows=2013 width=8) (actual time=0.050..0.229 rows=2013 loops=1)
                                Recheck Cond: (everyone_level >= '1'::smallint)
                                Heap Blocks: exact=19
                                Buffers: shared hit=31
                                ->  Bitmap Index Scan on ts_df1cf724_e_lvlpath  (cost=0.00..59.38 rows=2013 width=0) (actual time=0.046..0.046 rows=2013 loops=1)
                                      Index Cond: (everyone_level >= '1'::smallint)
                                      Buffers: shared hit=12
                          ->  Nested Loop  (cost=0.29..91.50 rows=10 width=8) (actual time=0.022..0.040 rows=1 loops=1)
                                Buffers: shared hit=33
                                ->  Function Scan on unnest ap  (cost=0.00..0.11 rows=11 width=32) (actual time=0.004..0.005 rows=11 loops=1)
                                ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_1  (cost=0.29..8.31 rows=1 width=29) (actual time=0.003..0.003 rows=0 loops=11)
                                      Index Cond: ((path)::text = (ap.value)::text)
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 1
                                      Buffers: shared hit=33
                          ->  Nested Loop  (cost=0.29..1855.40 rows=25789 width=8) (actual time=0.009..0.191 rows=20 loops=1)
                                Buffers: shared hit=60
                                ->  Function Scan on ar  (cost=0.01..0.12 rows=11 width=64) (actual time=0.005..0.006 rows=11 loops=1)
                                ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_2  (cost=0.29..145.22 rows=2344 width=29) (actual time=0.016..0.016 rows=2 loops=11)
                                      Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 182
                                      Buffers: shared hit=60
                          ->  Index Scan using ts_df1cf724_e_owner on ts_df1cf724_e e_3  (cost=0.29..36.85 rows=22 width=8) (actual time=0.011..0.014 rows=20 loops=1)
                                Index Cond: ((owner_id)::text = 'u000042'::text)
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 4
                                Buffers: shared hit=7
Planning Time: 0.167 ms
Execution Time: 20.819 ms
```

**ordinary / literal / top10**

```
Limit  (cost=0.62..25.20 rows=10 width=12) (actual time=0.052..0.271 rows=10 loops=1)
  Buffers: shared hit=418
  ->  Nested Loop  (cost=0.62..14454.33 rows=5880 width=12) (actual time=0.051..0.270 rows=10 loops=1)
        Buffers: shared hit=418
        ->  Index Scan using ts_df1cf724_c_score on ts_df1cf724_c c  (cost=0.29..3710.24 rows=66000 width=20) (actual time=0.006..0.061 rows=104 loops=1)
              Buffers: shared hit=106
        ->  Memoize  (cost=0.33..0.42 rows=1 width=8) (actual time=0.002..0.002 rows=0 loops=104)
              Cache Key: c.entry_id
              Cache Mode: logical
              Hits: 0  Misses: 104  Evictions: 0  Overflows: 0  Memory Usage: 8kB
              Buffers: shared hit=312
              ->  Index Scan using ts_df1cf724_e_pkey on ts_df1cf724_e e  (cost=0.32..0.41 rows=1 width=8) (actual time=0.002..0.002 rows=0 loops=104)
                    Index Cond: (id = c.entry_id)
                    Filter: ((everyone_level >= '1'::smallint) OR ((path)::text = ANY ('{/home/u000042,/shared/s0000,/shared/s0001,/shared/s0002,/shared/s0003,/shared/s0004,/shared/s0005,/shared/s0006,/shared/s0007,/shared/s0008,/shared/s0009}'::text[])) OR (((path)::text > '/home/u000042/'::text) AND ((path)::text < '/home/u0000420'::text)) OR (((path)::text > '/shared/s0000/'::text) AND ((path)::text < '/shared/s00000'::text)) OR (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text)) OR (((path)::text > '/shared/s0002/'::text) AND ((path)::text < '/shared/s00020'::text)) OR (((path)::text > '/shared/s0003/'::text) AND ((path)::text < '/shared/s00030'::text)) OR (((path)::text > '/shared/s0004/'::text) AND ((path)::text < '/shared/s00040'::text)) OR (((path)::text > '/shared/s0005/'::text) AND ((path)::text < '/shared/s00050'::text)) OR (((path)::text > '/shared/s0006/'::text) AND ((path)::text < '/shared/s00060'::text)) OR (((path)::text > '/shared/s0007/'::text) AND ((path)::text < '/shared/s00070'::text)) OR (((path)::text > '/shared/s0008/'::text) AND ((path)::text < '/shared/s00080'::text)) OR (((path)::text > '/shared/s0009/'::text) AND ((path)::text < '/shared/s00090'::text)) OR ((owner_id)::text = 'u000042'::text))
                    Rows Removed by Filter: 1
                    Buffers: shared hit=312
Planning:
  Buffers: shared hit=27
Planning Time: 0.245 ms
Execution Time: 0.289 ms
```

**ordinary / fenced / top10**

```
Limit  (cost=2469.85..5772.01 rows=10 width=12) (actual time=2.765..20.837 rows=10 loops=1)
  Buffers: shared hit=237
  ->  Nested Loop  (cost=2469.85..27560935.28 rows=83456 width=12) (actual time=2.764..20.834 rows=10 loops=1)
        Join Filter: (c.entry_id = e.id)
        Rows Removed by Join Filter: 202991
        Buffers: shared hit=237
        ->  Index Scan using ts_df1cf724_c_score on ts_df1cf724_c c  (cost=0.29..3710.24 rows=66000 width=20) (actual time=0.008..0.165 rows=104 loops=1)
              Buffers: shared hit=106
        ->  Materialize  (cost=2469.56..2887.07 rows=27834 width=8) (actual time=0.009..0.115 rows=1952 loops=104)
              Buffers: shared hit=131
              ->  HashAggregate  (cost=2469.56..2747.90 rows=27834 width=8) (actual time=0.922..1.152 rows=2034 loops=1)
                    Group Key: e.id
                    Batches: 1  Memory Usage: 913kB
                    Buffers: shared hit=131
                    ->  Append  (cost=59.89..2399.97 rows=27834 width=8) (actual time=0.052..0.656 rows=2054 loops=1)
                          Buffers: shared hit=131
                          ->  Bitmap Heap Scan on ts_df1cf724_e e  (cost=59.89..277.05 rows=2013 width=8) (actual time=0.051..0.240 rows=2013 loops=1)
                                Recheck Cond: (everyone_level >= '1'::smallint)
                                Heap Blocks: exact=19
                                Buffers: shared hit=31
                                ->  Bitmap Index Scan on ts_df1cf724_e_lvlpath  (cost=0.00..59.38 rows=2013 width=0) (actual time=0.047..0.047 rows=2013 loops=1)
                                      Index Cond: (everyone_level >= '1'::smallint)
                                      Buffers: shared hit=12
                          ->  Nested Loop  (cost=0.29..91.50 rows=10 width=8) (actual time=0.025..0.044 rows=1 loops=1)
                                Buffers: shared hit=33
                                ->  Function Scan on unnest ap  (cost=0.00..0.11 rows=11 width=32) (actual time=0.016..0.016 rows=11 loops=1)
                                ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_1  (cost=0.29..8.31 rows=1 width=29) (actual time=0.002..0.002 rows=0 loops=11)
                                      Index Cond: ((path)::text = (ap.value)::text)
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 1
                                      Buffers: shared hit=33
                          ->  Nested Loop  (cost=0.29..1855.40 rows=25789 width=8) (actual time=0.009..0.197 rows=20 loops=1)
                                Buffers: shared hit=60
                                ->  Function Scan on ar  (cost=0.01..0.12 rows=11 width=64) (actual time=0.004..0.005 rows=11 loops=1)
                                ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_2  (cost=0.29..145.22 rows=2344 width=29) (actual time=0.017..0.017 rows=2 loops=11)
                                      Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 182
                                      Buffers: shared hit=60
                          ->  Index Scan using ts_df1cf724_e_owner on ts_df1cf724_e e_3  (cost=0.29..36.85 rows=22 width=8) (actual time=0.010..0.013 rows=20 loops=1)
                                Index Cond: ((owner_id)::text = 'u000042'::text)
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 4
                                Buffers: shared hit=7
Planning Time: 0.186 ms
Execution Time: 20.901 ms
```

**ordinary / disjoint / top10**

```
Limit  (cost=60.18..3362.73 rows=10 width=12) (actual time=2.256..21.913 rows=10 loops=1)
  Buffers: shared hit=237
  ->  Nested Loop  (cost=60.18..27559865.88 rows=83450 width=12) (actual time=2.255..21.910 rows=10 loops=1)
        Join Filter: (c.entry_id = e.id)
        Rows Removed by Join Filter: 210729
        Buffers: shared hit=237
        ->  Index Scan using ts_df1cf724_c_score on ts_df1cf724_c c  (cost=0.29..3710.24 rows=66000 width=20) (actual time=0.015..0.237 rows=104 loops=1)
              Buffers: shared hit=106
        ->  Materialize  (cost=59.89..2545.22 rows=27832 width=8) (actual time=0.001..0.118 rows=2026 loops=104)
              Buffers: shared hit=131
              ->  Append  (cost=59.89..2406.06 rows=27832 width=8) (actual time=0.059..0.657 rows=2034 loops=1)
                    Buffers: shared hit=131
                    ->  Bitmap Heap Scan on ts_df1cf724_e e  (cost=59.89..277.05 rows=2013 width=8) (actual time=0.059..0.237 rows=2013 loops=1)
                          Recheck Cond: (everyone_level >= '1'::smallint)
                          Heap Blocks: exact=19
                          Buffers: shared hit=31
                          ->  Bitmap Index Scan on ts_df1cf724_e_lvlpath  (cost=0.00..59.38 rows=2013 width=0) (actual time=0.054..0.054 rows=2013 loops=1)
                                Index Cond: (everyone_level >= '1'::smallint)
                                Buffers: shared hit=12
                    ->  Nested Loop  (cost=0.29..91.50 rows=10 width=8) (actual time=0.012..0.032 rows=1 loops=1)
                          Buffers: shared hit=33
                          ->  Function Scan on unnest ap  (cost=0.00..0.11 rows=11 width=32) (actual time=0.004..0.004 rows=11 loops=1)
                          ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_1  (cost=0.29..8.31 rows=1 width=29) (actual time=0.002..0.002 rows=0 loops=11)
                                Index Cond: ((path)::text = (ap.value)::text)
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 1
                                Buffers: shared hit=33
                    ->  Nested Loop  (cost=0.29..1855.40 rows=25789 width=8) (actual time=0.013..0.192 rows=20 loops=1)
                          Buffers: shared hit=60
                          ->  Function Scan on ar  (cost=0.01..0.12 rows=11 width=64) (actual time=0.008..0.009 rows=11 loops=1)
                          ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_2  (cost=0.29..145.22 rows=2344 width=29) (actual time=0.016..0.016 rows=2 loops=11)
                                Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 182
                                Buffers: shared hit=60
                    ->  Hash Anti Join  (cost=0.54..42.95 rows=20 width=8) (actual time=0.021..0.024 rows=0 loops=1)
                          Hash Cond: ((e_3.path)::text = (x0p.value)::text)
                          Buffers: shared hit=7
                          ->  Nested Loop Anti Join  (cost=0.29..42.45 rows=20 width=29) (actual time=0.021..0.021 rows=0 loops=1)
                                Join Filter: (((e_3.path)::text > (x0r.lo)::text) AND ((e_3.path)::text < (x0r.hi)::text))
                                Buffers: shared hit=7
                                ->  Index Scan using ts_df1cf724_e_owner on ts_df1cf724_e e_3  (cost=0.29..36.85 rows=22 width=29) (actual time=0.008..0.012 rows=20 loops=1)
                                      Index Cond: ((owner_id)::text = 'u000042'::text)
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 4
                                      Buffers: shared hit=7
                                ->  Function Scan on x0r  (cost=0.01..0.12 rows=11 width=64) (actual time=0.000..0.000 rows=1 loops=20)
                          ->  Hash  (cost=0.11..0.11 rows=11 width=32) (never executed)
                                ->  Function Scan on unnest x0p  (cost=0.00..0.11 rows=11 width=32) (never executed)
Planning Time: 0.230 ms
Execution Time: 21.972 ms
```

**two subjects / union / entries**

```
HashAggregate  (cost=2422.23..2677.42 rows=25519 width=8) (actual time=1.041..1.258 rows=2013 loops=1)
  Group Key: e.id
  Batches: 1  Memory Usage: 913kB
  Buffers: shared hit=144
  ->  Append  (cost=59.89..2358.44 rows=25519 width=8) (actual time=0.067..0.780 rows=2013 loops=1)
        Buffers: shared hit=144
        ->  Bitmap Heap Scan on ts_df1cf724_e e  (cost=59.89..277.05 rows=2013 width=8) (actual time=0.067..0.249 rows=2013 loops=1)
              Recheck Cond: (everyone_level >= '1'::smallint)
              Heap Blocks: exact=19
              Buffers: shared hit=31
              ->  Bitmap Index Scan on ts_df1cf724_e_lvlpath  (cost=0.00..59.38 rows=2013 width=0) (actual time=0.059..0.059 rows=2013 loops=1)
                    Index Cond: (everyone_level >= '1'::smallint)
                    Buffers: shared hit=12
        ->  Nested Loop  (cost=0.29..83.18 rows=9 width=8) (actual time=0.035..0.036 rows=0 loops=1)
              Buffers: shared hit=30
              ->  Function Scan on unnest ap  (cost=0.00..0.10 rows=10 width=32) (actual time=0.005..0.006 rows=10 loops=1)
              ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_1  (cost=0.29..8.31 rows=1 width=29) (actual time=0.003..0.003 rows=0 loops=10)
                    Index Cond: ((path)::text = (ap.value)::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 1
                    Buffers: shared hit=30
        ->  Nested Loop  (cost=0.29..1719.29 rows=23444 width=8) (actual time=0.185..0.186 rows=0 loops=1)
              Buffers: shared hit=57
              ->  Function Scan on ar  (cost=0.01..0.11 rows=10 width=64) (actual time=0.002..0.003 rows=10 loops=1)
              ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_2  (cost=0.29..148.48 rows=2344 width=29) (actual time=0.018..0.018 rows=0 loops=10)
                    Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 200
                    Buffers: shared hit=57
        ->  Hash Join  (cost=0.54..37.20 rows=1 width=8) (actual time=0.027..0.028 rows=0 loops=1)
              Hash Cond: ((e_3.path)::text = (o0p.value)::text)
              Buffers: shared hit=7
              ->  Index Scan using ts_df1cf724_e_owner on ts_df1cf724_e e_3  (cost=0.29..36.85 rows=22 width=29) (actual time=0.010..0.013 rows=20 loops=1)
                    Index Cond: ((owner_id)::text = 'u000042'::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 4
                    Buffers: shared hit=7
              ->  Hash  (cost=0.11..0.11 rows=11 width=32) (actual time=0.006..0.007 rows=11 loops=1)
                    Buckets: 1024  Batches: 1  Memory Usage: 9kB
                    ->  Function Scan on unnest o0p  (cost=0.00..0.11 rows=11 width=32) (actual time=0.002..0.003 rows=11 loops=1)
        ->  Nested Loop  (cost=0.29..41.26 rows=27 width=8) (actual time=0.061..0.061 rows=0 loops=1)
              Join Filter: (((e_4.path)::text > (o0r.lo)::text) AND ((e_4.path)::text < (o0r.hi)::text))
              Rows Removed by Join Filter: 220
              Buffers: shared hit=7
              ->  Function Scan on o0r  (cost=0.01..0.12 rows=11 width=64) (actual time=0.018..0.019 rows=11 loops=1)
              ->  Materialize  (cost=0.29..36.96 rows=22 width=29) (actual time=0.001..0.003 rows=20 loops=11)
                    Buffers: shared hit=7
                    ->  Index Scan using ts_df1cf724_e_owner on ts_df1cf724_e e_4  (cost=0.29..36.85 rows=22 width=29) (actual time=0.005..0.008 rows=20 loops=1)
                          Index Cond: ((owner_id)::text = 'u000042'::text)
                          Filter: (everyone_level < '1'::smallint)
                          Rows Removed by Filter: 4
                          Buffers: shared hit=7
        ->  Hash Join  (cost=0.54..34.59 rows=1 width=8) (actual time=0.020..0.021 rows=0 loops=1)
              Hash Cond: ((e_5.path)::text = (o1p.value)::text)
              Buffers: shared hit=6
              ->  Index Scan using ts_df1cf724_e_owner on ts_df1cf724_e e_5  (cost=0.29..34.26 rows=20 width=29) (actual time=0.006..0.009 rows=20 loops=1)
                    Index Cond: ((owner_id)::text = 'u000000'::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 3
                    Buffers: shared hit=6
              ->  Hash  (cost=0.11..0.11 rows=11 width=32) (actual time=0.006..0.006 rows=11 loops=1)
                    Buckets: 1024  Batches: 1  Memory Usage: 9kB
                    ->  Function Scan on unnest o1p  (cost=0.00..0.11 rows=11 width=32) (actual time=0.002..0.003 rows=11 loops=1)
        ->  Nested Loop  (cost=0.29..38.27 rows=24 width=8) (actual time=0.041..0.041 rows=0 loops=1)
              Join Filter: (((e_6.path)::text > (o1r.lo)::text) AND ((e_6.path)::text < (o1r.hi)::text))
              Rows Removed by Join Filter: 220
              Buffers: shared hit=6
              ->  Function Scan on o1r  (cost=0.01..0.12 rows=11 width=64) (actual time=0.004..0.005 rows=11 loops=1)
              ->  Materialize  (cost=0.29..34.36 rows=20 width=29) (actual time=0.001..0.002 rows=20 loops=11)
                    Buffers: shared hit=6
                    ->  Index Scan using ts_df1cf724_e_owner on ts_df1cf724_e e_6  (cost=0.29..34.26 rows=20 width=29) (actual time=0.004..0.007 rows=20 loops=1)
                          Index Cond: ((owner_id)::text = 'u000000'::text)
                          Filter: (everyone_level < '1'::smallint)
                          Rows Removed by Filter: 3
                          Buffers: shared hit=6
Planning Time: 0.267 ms
Execution Time: 1.441 ms
```

**two subjects / unionall / entries**

```
HashAggregate  (cost=2422.23..2677.42 rows=25519 width=8) (actual time=1.077..1.295 rows=2013 loops=1)
  Group Key: e.id
  Batches: 1  Memory Usage: 913kB
  Buffers: shared hit=144
  ->  Append  (cost=59.89..2358.44 rows=25519 width=8) (actual time=0.067..0.832 rows=2013 loops=1)
        Buffers: shared hit=144
        ->  Bitmap Heap Scan on ts_df1cf724_e e  (cost=59.89..277.05 rows=2013 width=8) (actual time=0.067..0.250 rows=2013 loops=1)
              Recheck Cond: (everyone_level >= '1'::smallint)
              Heap Blocks: exact=19
              Buffers: shared hit=31
              ->  Bitmap Index Scan on ts_df1cf724_e_lvlpath  (cost=0.00..59.38 rows=2013 width=0) (actual time=0.060..0.060 rows=2013 loops=1)
                    Index Cond: (everyone_level >= '1'::smallint)
                    Buffers: shared hit=12
        ->  Nested Loop  (cost=0.29..83.18 rows=9 width=8) (actual time=0.034..0.035 rows=0 loops=1)
              Buffers: shared hit=30
              ->  Function Scan on unnest ap  (cost=0.00..0.10 rows=10 width=32) (actual time=0.005..0.006 rows=10 loops=1)
              ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_1  (cost=0.29..8.31 rows=1 width=29) (actual time=0.002..0.002 rows=0 loops=10)
                    Index Cond: ((path)::text = (ap.value)::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 1
                    Buffers: shared hit=30
        ->  Nested Loop  (cost=0.29..1719.29 rows=23444 width=8) (actual time=0.201..0.201 rows=0 loops=1)
              Buffers: shared hit=57
              ->  Function Scan on ar  (cost=0.01..0.11 rows=10 width=64) (actual time=0.010..0.011 rows=10 loops=1)
              ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_2  (cost=0.29..148.48 rows=2344 width=29) (actual time=0.019..0.019 rows=0 loops=10)
                    Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 200
                    Buffers: shared hit=57
        ->  Hash Join  (cost=0.54..37.20 rows=1 width=8) (actual time=0.034..0.035 rows=0 loops=1)
              Hash Cond: ((e_3.path)::text = (o0p.value)::text)
              Buffers: shared hit=7
              ->  Index Scan using ts_df1cf724_e_owner on ts_df1cf724_e e_3  (cost=0.29..36.85 rows=22 width=29) (actual time=0.012..0.015 rows=20 loops=1)
                    Index Cond: ((owner_id)::text = 'u000042'::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 4
                    Buffers: shared hit=7
              ->  Hash  (cost=0.11..0.11 rows=11 width=32) (actual time=0.005..0.006 rows=11 loops=1)
                    Buckets: 1024  Batches: 1  Memory Usage: 9kB
                    ->  Function Scan on unnest o0p  (cost=0.00..0.11 rows=11 width=32) (actual time=0.002..0.002 rows=11 loops=1)
        ->  Nested Loop  (cost=0.29..41.26 rows=27 width=8) (actual time=0.058..0.058 rows=0 loops=1)
              Join Filter: (((e_4.path)::text > (o0r.lo)::text) AND ((e_4.path)::text < (o0r.hi)::text))
              Rows Removed by Join Filter: 220
              Buffers: shared hit=7
              ->  Function Scan on o0r  (cost=0.01..0.12 rows=11 width=64) (actual time=0.013..0.014 rows=11 loops=1)
              ->  Materialize  (cost=0.29..36.96 rows=22 width=29) (actual time=0.001..0.003 rows=20 loops=11)
                    Buffers: shared hit=7
                    ->  Index Scan using ts_df1cf724_e_owner on ts_df1cf724_e e_4  (cost=0.29..36.85 rows=22 width=29) (actual time=0.005..0.008 rows=20 loops=1)
                          Index Cond: ((owner_id)::text = 'u000042'::text)
                          Filter: (everyone_level < '1'::smallint)
                          Rows Removed by Filter: 4
                          Buffers: shared hit=7
        ->  Hash Join  (cost=0.54..34.59 rows=1 width=8) (actual time=0.034..0.034 rows=0 loops=1)
              Hash Cond: ((e_5.path)::text = (o1p.value)::text)
              Buffers: shared hit=6
              ->  Index Scan using ts_df1cf724_e_owner on ts_df1cf724_e e_5  (cost=0.29..34.26 rows=20 width=29) (actual time=0.014..0.016 rows=20 loops=1)
                    Index Cond: ((owner_id)::text = 'u000000'::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 3
                    Buffers: shared hit=6
              ->  Hash  (cost=0.11..0.11 rows=11 width=32) (actual time=0.004..0.005 rows=11 loops=1)
                    Buckets: 1024  Batches: 1  Memory Usage: 9kB
                    ->  Function Scan on unnest o1p  (cost=0.00..0.11 rows=11 width=32) (actual time=0.002..0.002 rows=11 loops=1)
        ->  Nested Loop  (cost=0.29..38.27 rows=24 width=8) (actual time=0.060..0.060 rows=0 loops=1)
              Join Filter: (((e_6.path)::text > (o1r.lo)::text) AND ((e_6.path)::text < (o1r.hi)::text))
              Rows Removed by Join Filter: 220
              Buffers: shared hit=6
              ->  Function Scan on o1r  (cost=0.01..0.12 rows=11 width=64) (actual time=0.003..0.004 rows=11 loops=1)
              ->  Materialize  (cost=0.29..34.36 rows=20 width=29) (actual time=0.002..0.004 rows=20 loops=11)
                    Buffers: shared hit=6
                    ->  Index Scan using ts_df1cf724_e_owner on ts_df1cf724_e e_6  (cost=0.29..34.26 rows=20 width=29) (actual time=0.005..0.008 rows=20 loops=1)
                          Index Cond: ((owner_id)::text = 'u000000'::text)
                          Filter: (everyone_level < '1'::smallint)
                          Rows Removed by Filter: 3
                          Buffers: shared hit=6
Planning Time: 0.294 ms
Execution Time: 1.490 ms
```

**two subjects / literal / entries**

```
Bitmap Heap Scan on ts_df1cf724_e e  (cost=161.51..754.68 rows=2036 width=8) (actual time=0.165..0.389 rows=2013 loops=1)
  Recheck Cond: ((everyone_level >= '1'::smallint) OR ((path)::text = ANY ('{/shared/s0000,/shared/s0001,/shared/s0002,/shared/s0003,/shared/s0004,/shared/s0005,/shared/s0006,/shared/s0007,/shared/s0008,/shared/s0009}'::text[])) OR (((path)::text > '/shared/s0000/'::text) AND ((path)::text < '/shared/s00000'::text)) OR (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text)) OR (((path)::text > '/shared/s0002/'::text) AND ((path)::text < '/shared/s00020'::text)) OR (((path)::text > '/shared/s0003/'::text) AND ((path)::text < '/shared/s00030'::text)) OR (((path)::text > '/shared/s0004/'::text) AND ((path)::text < '/shared/s00040'::text)) OR (((path)::text > '/shared/s0005/'::text) AND ((path)::text < '/shared/s00050'::text)) OR (((path)::text > '/shared/s0006/'::text) AND ((path)::text < '/shared/s00060'::text)) OR (((path)::text > '/shared/s0007/'::text) AND ((path)::text < '/shared/s00070'::text)) OR (((path)::text > '/shared/s0008/'::text) AND ((path)::text < '/shared/s00080'::text)) OR (((path)::text > '/shared/s0009/'::text) AND ((path)::text < '/shared/s00090'::text)) OR ((owner_id)::text = 'u000042'::text) OR ((owner_id)::text = 'u000000'::text))
  Filter: ((everyone_level >= '1'::smallint) OR ((path)::text = ANY ('{/shared/s0000,/shared/s0001,/shared/s0002,/shared/s0003,/shared/s0004,/shared/s0005,/shared/s0006,/shared/s0007,/shared/s0008,/shared/s0009}'::text[])) OR (((path)::text > '/shared/s0000/'::text) AND ((path)::text < '/shared/s00000'::text)) OR (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text)) OR (((path)::text > '/shared/s0002/'::text) AND ((path)::text < '/shared/s00020'::text)) OR (((path)::text > '/shared/s0003/'::text) AND ((path)::text < '/shared/s00030'::text)) OR (((path)::text > '/shared/s0004/'::text) AND ((path)::text < '/shared/s00040'::text)) OR (((path)::text > '/shared/s0005/'::text) AND ((path)::text < '/shared/s00050'::text)) OR (((path)::text > '/shared/s0006/'::text) AND ((path)::text < '/shared/s00060'::text)) OR (((path)::text > '/shared/s0007/'::text) AND ((path)::text < '/shared/s00070'::text)) OR (((path)::text > '/shared/s0008/'::text) AND ((path)::text < '/shared/s00080'::text)) OR (((path)::text > '/shared/s0009/'::text) AND ((path)::text < '/shared/s00090'::text)) OR (((owner_id)::text = 'u000042'::text) AND (((path)::text = ANY ('{/home/u000000,/shared/s0000,/shared/s0001,/shared/s0002,/shared/s0003,/shared/s0004,/shared/s0005,/shared/s0006,/shared/s0007,/shared/s0008,/shared/s0009}'::text[])) OR (((path)::text > '/home/u000000/'::text) AND ((path)::text < '/home/u0000000'::text)) OR (((path)::text > '/shared/s0000/'::text) AND ((path)::text < '/shared/s00000'::text)) OR (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text)) OR (((path)::text > '/shared/s0002/'::text) AND ((path)::text < '/shared/s00020'::text)) OR (((path)::text > '/shared/s0003/'::text) AND ((path)::text < '/shared/s00030'::text)) OR (((path)::text > '/shared/s0004/'::text) AND ((path)::text < '/shared/s00040'::text)) OR (((path)::text > '/shared/s0005/'::text) AND ((path)::text < '/shared/s00050'::text)) OR (((path)::text > '/shared/s0006/'::text) AND ((path)::text < '/shared/s00060'::text)) OR (((path)::text > '/shared/s0007/'::text) AND ((path)::text < '/shared/s00070'::text)) OR (((path)::text > '/shared/s0008/'::text) AND ((path)::text < '/shared/s00080'::text)) OR (((path)::text > '/shared/s0009/'::text) AND ((path)::text < '/shared/s00090'::text)))) OR (((owner_id)::text = 'u000000'::text) AND (((path)::text = ANY ('{/home/u000042,/shared/s0000,/shared/s0001,/shared/s0002,/shared/s0003,/shared/s0004,/shared/s0005,/shared/s0006,/shared/s0007,/shared/s0008,/shared/s0009}'::text[])) OR (((path)::text > '/home/u000042/'::text) AND ((path)::text < '/home/u0000420'::text)) OR (((path)::text > '/shared/s0000/'::text) AND ((path)::text < '/shared/s00000'::text)) OR (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text)) OR (((path)::text > '/shared/s0002/'::text) AND ((path)::text < '/shared/s00020'::text)) OR (((path)::text > '/shared/s0003/'::text) AND ((path)::text < '/shared/s00030'::text)) OR (((path)::text > '/shared/s0004/'::text) AND ((path)::text < '/shared/s00040'::text)) OR (((path)::text > '/shared/s0005/'::text) AND ((path)::text < '/shared/s00050'::text)) OR (((path)::text > '/shared/s0006/'::text) AND ((path)::text < '/shared/s00060'::text)) OR (((path)::text > '/shared/s0007/'::text) AND ((path)::text < '/shared/s00070'::text)) OR (((path)::text > '/shared/s0008/'::text) AND ((path)::text < '/shared/s00080'::text)) OR (((path)::text > '/shared/s0009/'::text) AND ((path)::text < '/shared/s00090'::text)))))
  Rows Removed by Filter: 40
  Heap Blocks: exact=20
  Buffers: shared hit=86
  ->  BitmapOr  (cost=161.43..161.43 rows=2084 width=0) (actual time=0.153..0.155 rows=0 loops=1)
        Buffers: shared hit=66
        ->  Bitmap Index Scan on ts_df1cf724_e_lvlpath  (cost=0.00..59.38 rows=2013 width=0) (actual time=0.053..0.053 rows=2013 loops=1)
              Index Cond: (everyone_level >= '1'::smallint)
              Buffers: shared hit=12
        ->  Bitmap Index Scan on ts_df1cf724_e_path  (cost=0.00..42.95 rows=10 width=0) (actual time=0.020..0.020 rows=10 loops=1)
              Index Cond: ((path)::text = ANY ('{/shared/s0000,/shared/s0001,/shared/s0002,/shared/s0003,/shared/s0004,/shared/s0005,/shared/s0006,/shared/s0007,/shared/s0008,/shared/s0009}'::text[]))
              Buffers: shared hit=20
        ->  Bitmap Index Scan on ts_df1cf724_e_path  (cost=0.00..4.30 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0000/'::text) AND ((path)::text < '/shared/s00000'::text))
              Buffers: shared hit=3
        ->  Bitmap Index Scan on ts_df1cf724_e_path  (cost=0.00..4.31 rows=2 width=0) (actual time=0.006..0.006 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
              Buffers: shared hit=3
        ->  Bitmap Index Scan on ts_df1cf724_e_path  (cost=0.00..4.30 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0002/'::text) AND ((path)::text < '/shared/s00020'::text))
              Buffers: shared hit=3
        ->  Bitmap Index Scan on ts_df1cf724_e_path  (cost=0.00..4.30 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0003/'::text) AND ((path)::text < '/shared/s00030'::text))
              Buffers: shared hit=3
        ->  Bitmap Index Scan on ts_df1cf724_e_path  (cost=0.00..4.31 rows=2 width=0) (actual time=0.006..0.006 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0004/'::text) AND ((path)::text < '/shared/s00040'::text))
              Buffers: shared hit=3
        ->  Bitmap Index Scan on ts_df1cf724_e_path  (cost=0.00..4.31 rows=2 width=0) (actual time=0.006..0.006 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0005/'::text) AND ((path)::text < '/shared/s00050'::text))
              Buffers: shared hit=3
        ->  Bitmap Index Scan on ts_df1cf724_e_path  (cost=0.00..4.31 rows=2 width=0) (actual time=0.007..0.007 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0006/'::text) AND ((path)::text < '/shared/s00060'::text))
              Buffers: shared hit=3
        ->  Bitmap Index Scan on ts_df1cf724_e_path  (cost=0.00..4.31 rows=2 width=0) (actual time=0.007..0.007 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0007/'::text) AND ((path)::text < '/shared/s00070'::text))
              Buffers: shared hit=3
        ->  Bitmap Index Scan on ts_df1cf724_e_path  (cost=0.00..4.31 rows=2 width=0) (actual time=0.006..0.006 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0008/'::text) AND ((path)::text < '/shared/s00080'::text))
              Buffers: shared hit=3
        ->  Bitmap Index Scan on ts_df1cf724_e_path  (cost=0.00..4.31 rows=2 width=0) (actual time=0.010..0.010 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0009/'::text) AND ((path)::text < '/shared/s00090'::text))
              Buffers: shared hit=3
        ->  Bitmap Index Scan on ts_df1cf724_e_owner  (cost=0.00..4.47 rows=24 width=0) (actual time=0.006..0.006 rows=24 loops=1)
              Index Cond: ((owner_id)::text = 'u000042'::text)
              Buffers: shared hit=2
        ->  Bitmap Index Scan on ts_df1cf724_e_owner  (cost=0.00..4.45 rows=22 width=0) (actual time=0.002..0.002 rows=23 loops=1)
              Index Cond: ((owner_id)::text = 'u000000'::text)
              Buffers: shared hit=2
Planning:
  Buffers: shared hit=51
Planning Time: 0.486 ms
Execution Time: 0.526 ms
```

**two subjects / fenced / entries**

```
HashAggregate  (cost=2422.23..2677.42 rows=25519 width=8) (actual time=1.075..1.295 rows=2013 loops=1)
  Group Key: e.id
  Batches: 1  Memory Usage: 913kB
  Buffers: shared hit=144
  ->  Append  (cost=59.89..2358.44 rows=25519 width=8) (actual time=0.070..0.814 rows=2013 loops=1)
        Buffers: shared hit=144
        ->  Bitmap Heap Scan on ts_df1cf724_e e  (cost=59.89..277.05 rows=2013 width=8) (actual time=0.070..0.258 rows=2013 loops=1)
              Recheck Cond: (everyone_level >= '1'::smallint)
              Heap Blocks: exact=19
              Buffers: shared hit=31
              ->  Bitmap Index Scan on ts_df1cf724_e_lvlpath  (cost=0.00..59.38 rows=2013 width=0) (actual time=0.062..0.062 rows=2013 loops=1)
                    Index Cond: (everyone_level >= '1'::smallint)
                    Buffers: shared hit=12
        ->  Nested Loop  (cost=0.29..83.18 rows=9 width=8) (actual time=0.035..0.035 rows=0 loops=1)
              Buffers: shared hit=30
              ->  Function Scan on unnest ap  (cost=0.00..0.10 rows=10 width=32) (actual time=0.005..0.006 rows=10 loops=1)
              ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_1  (cost=0.29..8.31 rows=1 width=29) (actual time=0.003..0.003 rows=0 loops=10)
                    Index Cond: ((path)::text = (ap.value)::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 1
                    Buffers: shared hit=30
        ->  Nested Loop  (cost=0.29..1719.29 rows=23444 width=8) (actual time=0.213..0.214 rows=0 loops=1)
              Buffers: shared hit=57
              ->  Function Scan on ar  (cost=0.01..0.11 rows=10 width=64) (actual time=0.004..0.005 rows=10 loops=1)
              ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_2  (cost=0.29..148.48 rows=2344 width=29) (actual time=0.020..0.020 rows=0 loops=10)
                    Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 200
                    Buffers: shared hit=57
        ->  Hash Join  (cost=0.54..37.20 rows=1 width=8) (actual time=0.036..0.037 rows=0 loops=1)
              Hash Cond: ((e_3.path)::text = (o0p.value)::text)
              Buffers: shared hit=7
              ->  Index Scan using ts_df1cf724_e_owner on ts_df1cf724_e e_3  (cost=0.29..36.85 rows=22 width=29) (actual time=0.018..0.021 rows=20 loops=1)
                    Index Cond: ((owner_id)::text = 'u000042'::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 4
                    Buffers: shared hit=7
              ->  Hash  (cost=0.11..0.11 rows=11 width=32) (actual time=0.006..0.006 rows=11 loops=1)
                    Buckets: 1024  Batches: 1  Memory Usage: 9kB
                    ->  Function Scan on unnest o0p  (cost=0.00..0.11 rows=11 width=32) (actual time=0.002..0.003 rows=11 loops=1)
        ->  Nested Loop  (cost=0.29..41.26 rows=27 width=8) (actual time=0.044..0.044 rows=0 loops=1)
              Join Filter: (((e_4.path)::text > (o0r.lo)::text) AND ((e_4.path)::text < (o0r.hi)::text))
              Rows Removed by Join Filter: 220
              Buffers: shared hit=7
              ->  Function Scan on o0r  (cost=0.01..0.12 rows=11 width=64) (actual time=0.004..0.005 rows=11 loops=1)
              ->  Materialize  (cost=0.29..36.96 rows=22 width=29) (actual time=0.001..0.002 rows=20 loops=11)
                    Buffers: shared hit=7
                    ->  Index Scan using ts_df1cf724_e_owner on ts_df1cf724_e e_4  (cost=0.29..36.85 rows=22 width=29) (actual time=0.005..0.008 rows=20 loops=1)
                          Index Cond: ((owner_id)::text = 'u000042'::text)
                          Filter: (everyone_level < '1'::smallint)
                          Rows Removed by Filter: 4
                          Buffers: shared hit=7
        ->  Hash Join  (cost=0.54..34.59 rows=1 width=8) (actual time=0.018..0.019 rows=0 loops=1)
              Hash Cond: ((e_5.path)::text = (o1p.value)::text)
              Buffers: shared hit=6
              ->  Index Scan using ts_df1cf724_e_owner on ts_df1cf724_e e_5  (cost=0.29..34.26 rows=20 width=29) (actual time=0.004..0.007 rows=20 loops=1)
                    Index Cond: ((owner_id)::text = 'u000000'::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 3
                    Buffers: shared hit=6
              ->  Hash  (cost=0.11..0.11 rows=11 width=32) (actual time=0.005..0.005 rows=11 loops=1)
                    Buckets: 1024  Batches: 1  Memory Usage: 9kB
                    ->  Function Scan on unnest o1p  (cost=0.00..0.11 rows=11 width=32) (actual time=0.002..0.002 rows=11 loops=1)
        ->  Nested Loop  (cost=0.29..38.27 rows=24 width=8) (actual time=0.047..0.047 rows=0 loops=1)
              Join Filter: (((e_6.path)::text > (o1r.lo)::text) AND ((e_6.path)::text < (o1r.hi)::text))
              Rows Removed by Join Filter: 220
              Buffers: shared hit=6
              ->  Function Scan on o1r  (cost=0.01..0.12 rows=11 width=64) (actual time=0.004..0.005 rows=11 loops=1)
              ->  Materialize  (cost=0.29..34.36 rows=20 width=29) (actual time=0.001..0.003 rows=20 loops=11)
                    Buffers: shared hit=6
                    ->  Index Scan using ts_df1cf724_e_owner on ts_df1cf724_e e_6  (cost=0.29..34.26 rows=20 width=29) (actual time=0.005..0.008 rows=20 loops=1)
                          Index Cond: ((owner_id)::text = 'u000000'::text)
                          Filter: (everyone_level < '1'::smallint)
                          Rows Removed by Filter: 3
                          Buffers: shared hit=6
Planning Time: 0.331 ms
Execution Time: 1.447 ms
```

**two subjects / disjoint / entries**

```
Append  (cost=59.89..2369.22 rows=25513 width=8) (actual time=0.071..0.850 rows=2013 loops=1)
  Buffers: shared hit=144
  ->  Bitmap Heap Scan on ts_df1cf724_e e  (cost=59.89..277.05 rows=2013 width=8) (actual time=0.071..0.271 rows=2013 loops=1)
        Recheck Cond: (everyone_level >= '1'::smallint)
        Heap Blocks: exact=19
        Buffers: shared hit=31
        ->  Bitmap Index Scan on ts_df1cf724_e_lvlpath  (cost=0.00..59.38 rows=2013 width=0) (actual time=0.063..0.063 rows=2013 loops=1)
              Index Cond: (everyone_level >= '1'::smallint)
              Buffers: shared hit=12
  ->  Nested Loop  (cost=0.29..83.18 rows=9 width=8) (actual time=0.030..0.030 rows=0 loops=1)
        Buffers: shared hit=30
        ->  Function Scan on unnest ap  (cost=0.00..0.10 rows=10 width=32) (actual time=0.005..0.006 rows=10 loops=1)
        ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_1  (cost=0.29..8.31 rows=1 width=29) (actual time=0.002..0.002 rows=0 loops=10)
              Index Cond: ((path)::text = (ap.value)::text)
              Filter: (everyone_level < '1'::smallint)
              Rows Removed by Filter: 1
              Buffers: shared hit=30
  ->  Nested Loop  (cost=0.29..1719.29 rows=23444 width=8) (actual time=0.178..0.178 rows=0 loops=1)
        Buffers: shared hit=57
        ->  Function Scan on ar  (cost=0.01..0.11 rows=10 width=64) (actual time=0.002..0.003 rows=10 loops=1)
        ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_2  (cost=0.29..148.48 rows=2344 width=29) (actual time=0.017..0.017 rows=0 loops=10)
              Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
              Filter: (everyone_level < '1'::smallint)
              Rows Removed by Filter: 200
              Buffers: shared hit=57
  ->  Nested Loop Anti Join  (cost=0.54..37.68 rows=1 width=8) (actual time=0.023..0.024 rows=0 loops=1)
        Join Filter: (((e_3.path)::text > (x0r.lo)::text) AND ((e_3.path)::text < (x0r.hi)::text))
        Buffers: shared hit=7
        ->  Nested Loop Anti Join  (cost=0.54..37.42 rows=1 width=29) (actual time=0.023..0.023 rows=0 loops=1)
              Join Filter: ((e_3.path)::text = (x0p.value)::text)
              Buffers: shared hit=7
              ->  Hash Join  (cost=0.54..37.20 rows=1 width=29) (actual time=0.022..0.023 rows=0 loops=1)
                    Hash Cond: ((e_3.path)::text = (o0p.value)::text)
                    Buffers: shared hit=7
                    ->  Index Scan using ts_df1cf724_e_owner on ts_df1cf724_e e_3  (cost=0.29..36.85 rows=22 width=29) (actual time=0.009..0.012 rows=20 loops=1)
                          Index Cond: ((owner_id)::text = 'u000042'::text)
                          Filter: (everyone_level < '1'::smallint)
                          Rows Removed by Filter: 4
                          Buffers: shared hit=7
                    ->  Hash  (cost=0.11..0.11 rows=11 width=32) (actual time=0.006..0.006 rows=11 loops=1)
                          Buckets: 1024  Batches: 1  Memory Usage: 9kB
                          ->  Function Scan on unnest o0p  (cost=0.00..0.11 rows=11 width=32) (actual time=0.002..0.003 rows=11 loops=1)
              ->  Function Scan on unnest x0p  (cost=0.00..0.10 rows=10 width=32) (never executed)
        ->  Function Scan on x0r  (cost=0.01..0.11 rows=10 width=64) (never executed)
  ->  Nested Loop  (cost=0.53..46.44 rows=24 width=8) (actual time=0.089..0.089 rows=0 loops=1)
        Join Filter: (((e_4.path)::text > (o0r.lo)::text) AND ((e_4.path)::text < (o0r.hi)::text))
        Rows Removed by Join Filter: 220
        Buffers: shared hit=7
        ->  Function Scan on o0r  (cost=0.01..0.12 rows=11 width=64) (actual time=0.007..0.007 rows=11 loops=1)
        ->  Materialize  (cost=0.52..42.53 rows=20 width=29) (actual time=0.002..0.006 rows=20 loops=11)
              Buffers: shared hit=7
              ->  Hash Anti Join  (cost=0.52..42.43 rows=20 width=29) (actual time=0.021..0.053 rows=20 loops=1)
                    Hash Cond: ((e_4.path)::text = (x0p_1.value)::text)
                    Buffers: shared hit=7
                    ->  Nested Loop Anti Join  (cost=0.29..41.95 rows=20 width=29) (actual time=0.012..0.041 rows=20 loops=1)
                          Join Filter: (((e_4.path)::text > (x0r_1.lo)::text) AND ((e_4.path)::text < (x0r_1.hi)::text))
                          Rows Removed by Join Filter: 200
                          Buffers: shared hit=7
                          ->  Index Scan using ts_df1cf724_e_owner on ts_df1cf724_e e_4  (cost=0.29..36.85 rows=22 width=29) (actual time=0.006..0.009 rows=20 loops=1)
                                Index Cond: ((owner_id)::text = 'u000042'::text)
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 4
                                Buffers: shared hit=7
                          ->  Function Scan on x0r_1  (cost=0.01..0.11 rows=10 width=64) (actual time=0.000..0.001 rows=10 loops=20)
                    ->  Hash  (cost=0.10..0.10 rows=10 width=32) (actual time=0.004..0.005 rows=10 loops=1)
                          Buckets: 1024  Batches: 1  Memory Usage: 9kB
                          ->  Function Scan on unnest x0p_1  (cost=0.00..0.10 rows=10 width=32) (actual time=0.002..0.002 rows=10 loops=1)
  ->  Nested Loop Anti Join  (cost=0.54..35.08 rows=1 width=8) (actual time=0.018..0.019 rows=0 loops=1)
        Join Filter: (((e_5.path)::text > (x1r.lo)::text) AND ((e_5.path)::text < (x1r.hi)::text))
        Buffers: shared hit=6
        ->  Nested Loop Anti Join  (cost=0.54..34.82 rows=1 width=29) (actual time=0.018..0.018 rows=0 loops=1)
              Join Filter: ((e_5.path)::text = (x1p.value)::text)
              Buffers: shared hit=6
              ->  Hash Join  (cost=0.54..34.59 rows=1 width=29) (actual time=0.018..0.018 rows=0 loops=1)
                    Hash Cond: ((e_5.path)::text = (o1p.value)::text)
                    Buffers: shared hit=6
                    ->  Index Scan using ts_df1cf724_e_owner on ts_df1cf724_e e_5  (cost=0.29..34.26 rows=20 width=29) (actual time=0.004..0.007 rows=20 loops=1)
                          Index Cond: ((owner_id)::text = 'u000000'::text)
                          Filter: (everyone_level < '1'::smallint)
                          Rows Removed by Filter: 3
                          Buffers: shared hit=6
                    ->  Hash  (cost=0.11..0.11 rows=11 width=32) (actual time=0.005..0.005 rows=11 loops=1)
                          Buckets: 1024  Batches: 1  Memory Usage: 9kB
                          ->  Function Scan on unnest o1p  (cost=0.00..0.11 rows=11 width=32) (actual time=0.002..0.003 rows=11 loops=1)
              ->  Function Scan on unnest x1p  (cost=0.00..0.10 rows=10 width=32) (never executed)
        ->  Function Scan on x1r  (cost=0.01..0.11 rows=10 width=64) (never executed)
  ->  Nested Loop  (cost=0.53..42.94 rows=21 width=8) (actual time=0.084..0.084 rows=0 loops=1)
        Join Filter: (((e_6.path)::text > (o1r.lo)::text) AND ((e_6.path)::text < (o1r.hi)::text))
        Rows Removed by Join Filter: 220
        Buffers: shared hit=6
        ->  Function Scan on o1r  (cost=0.01..0.12 rows=11 width=64) (actual time=0.003..0.004 rows=11 loops=1)
        ->  Materialize  (cost=0.52..39.40 rows=18 width=29) (actual time=0.002..0.006 rows=20 loops=11)
              Buffers: shared hit=6
              ->  Hash Anti Join  (cost=0.52..39.31 rows=18 width=29) (actual time=0.020..0.052 rows=20 loops=1)
                    Hash Cond: ((e_6.path)::text = (x1p_1.value)::text)
                    Buffers: shared hit=6
                    ->  Nested Loop Anti Join  (cost=0.29..38.86 rows=18 width=29) (actual time=0.009..0.038 rows=20 loops=1)
                          Join Filter: (((e_6.path)::text > (x1r_1.lo)::text) AND ((e_6.path)::text < (x1r_1.hi)::text))
                          Rows Removed by Join Filter: 200
                          Buffers: shared hit=6
                          ->  Index Scan using ts_df1cf724_e_owner on ts_df1cf724_e e_6  (cost=0.29..34.26 rows=20 width=29) (actual time=0.004..0.007 rows=20 loops=1)
                                Index Cond: ((owner_id)::text = 'u000000'::text)
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 3
                                Buffers: shared hit=6
                          ->  Function Scan on x1r_1  (cost=0.01..0.11 rows=10 width=64) (actual time=0.000..0.001 rows=10 loops=20)
                    ->  Hash  (cost=0.10..0.10 rows=10 width=32) (actual time=0.004..0.004 rows=10 loops=1)
                          Buckets: 1024  Batches: 1  Memory Usage: 9kB
                          ->  Function Scan on unnest x1p_1  (cost=0.00..0.10 rows=10 width=32) (actual time=0.002..0.002 rows=10 loops=1)
Planning Time: 0.599 ms
Execution Time: 0.992 ms
```

**scoped / anonymous / union / IN**

```
Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e  (cost=0.29..8.49 rows=1 width=8) (actual time=0.060..0.135 rows=200 loops=1)
  Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
  Filter: (everyone_level = ANY ('{1,2}'::smallint[]))
  Buffers: shared hit=6
Planning Time: 0.178 ms
Execution Time: 0.164 ms
```

**scoped / anonymous / union / >=**

```
Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e  (cost=0.29..8.49 rows=1 width=8) (actual time=0.023..0.079 rows=200 loops=1)
  Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
  Filter: (everyone_level >= '1'::smallint)
  Buffers: shared hit=6
Planning:
  Buffers: shared hit=3
Planning Time: 0.175 ms
Execution Time: 0.109 ms
```

**scoped / ordinary / union / IN**

```
Unique  (cost=34.45..34.47 rows=4 width=8) (actual time=0.405..0.473 rows=200 loops=1)
  Buffers: shared hit=24
  ->  Sort  (cost=34.45..34.46 rows=4 width=8) (actual time=0.404..0.421 rows=200 loops=1)
        Sort Key: e.id
        Sort Method: quicksort  Memory: 25kB
        Buffers: shared hit=24
        ->  Append  (cost=0.29..34.41 rows=4 width=8) (actual time=0.041..0.379 rows=200 loops=1)
              Buffers: shared hit=24
              ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e  (cost=0.29..8.49 rows=1 width=8) (actual time=0.040..0.124 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: (everyone_level = ANY ('{1,2}'::smallint[]))
                    Buffers: shared hit=6
              ->  Hash Join  (cost=8.50..8.64 rows=1 width=8) (actual time=0.076..0.077 rows=0 loops=1)
                    Hash Cond: ((ap.value)::text = (e_1.path)::text)
                    Buffers: shared hit=6
                    ->  Function Scan on unnest ap  (cost=0.00..0.11 rows=11 width=32) (actual time=0.010..0.010 rows=1 loops=1)
                    ->  Hash  (cost=8.49..8.49 rows=1 width=29) (actual time=0.057..0.057 rows=0 loops=1)
                          Buckets: 1024  Batches: 1  Memory Usage: 8kB
                          Buffers: shared hit=6
                          ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_1  (cost=0.29..8.49 rows=1 width=29) (actual time=0.056..0.056 rows=0 loops=1)
                                Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 200
                                Buffers: shared hit=6
              ->  Nested Loop  (cost=0.29..8.77 rows=1 width=8) (actual time=0.100..0.101 rows=0 loops=1)
                    Join Filter: (((e_2.path)::text > (ar.lo)::text) AND ((e_2.path)::text < (ar.hi)::text))
                    Buffers: shared hit=6
                    ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_2  (cost=0.29..8.49 rows=1 width=29) (actual time=0.100..0.100 rows=0 loops=1)
                          Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                          Filter: (everyone_level < '1'::smallint)
                          Rows Removed by Filter: 200
                          Buffers: shared hit=6
                    ->  Function Scan on ar  (cost=0.01..0.12 rows=11 width=64) (never executed)
              ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_3  (cost=0.29..8.49 rows=1 width=8) (actual time=0.055..0.055 rows=0 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: ((everyone_level < '1'::smallint) AND ((owner_id)::text = 'u000042'::text))
                    Rows Removed by Filter: 200
                    Buffers: shared hit=6
Planning Time: 0.502 ms
Execution Time: 0.576 ms
```

**scoped / ordinary / unionall / IN**

```
Unique  (cost=34.45..34.47 rows=4 width=8) (actual time=0.373..0.436 rows=200 loops=1)
  Buffers: shared hit=24
  ->  Sort  (cost=34.45..34.46 rows=4 width=8) (actual time=0.372..0.388 rows=200 loops=1)
        Sort Key: e.id
        Sort Method: quicksort  Memory: 25kB
        Buffers: shared hit=24
        ->  Append  (cost=0.29..34.41 rows=4 width=8) (actual time=0.053..0.348 rows=200 loops=1)
              Buffers: shared hit=24
              ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e  (cost=0.29..8.49 rows=1 width=8) (actual time=0.052..0.137 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: (everyone_level = ANY ('{1,2}'::smallint[]))
                    Buffers: shared hit=6
              ->  Hash Join  (cost=8.50..8.64 rows=1 width=8) (actual time=0.085..0.086 rows=0 loops=1)
                    Hash Cond: ((ap.value)::text = (e_1.path)::text)
                    Buffers: shared hit=6
                    ->  Function Scan on unnest ap  (cost=0.00..0.11 rows=11 width=32) (actual time=0.019..0.019 rows=1 loops=1)
                    ->  Hash  (cost=8.49..8.49 rows=1 width=29) (actual time=0.058..0.058 rows=0 loops=1)
                          Buckets: 1024  Batches: 1  Memory Usage: 8kB
                          Buffers: shared hit=6
                          ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_1  (cost=0.29..8.49 rows=1 width=29) (actual time=0.057..0.057 rows=0 loops=1)
                                Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 200
                                Buffers: shared hit=6
              ->  Nested Loop  (cost=0.29..8.77 rows=1 width=8) (actual time=0.052..0.052 rows=0 loops=1)
                    Join Filter: (((e_2.path)::text > (ar.lo)::text) AND ((e_2.path)::text < (ar.hi)::text))
                    Buffers: shared hit=6
                    ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_2  (cost=0.29..8.49 rows=1 width=29) (actual time=0.051..0.051 rows=0 loops=1)
                          Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                          Filter: (everyone_level < '1'::smallint)
                          Rows Removed by Filter: 200
                          Buffers: shared hit=6
                    ->  Function Scan on ar  (cost=0.01..0.12 rows=11 width=64) (never executed)
              ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_3  (cost=0.29..8.49 rows=1 width=8) (actual time=0.051..0.051 rows=0 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: ((everyone_level < '1'::smallint) AND ((owner_id)::text = 'u000042'::text))
                    Rows Removed by Filter: 200
                    Buffers: shared hit=6
Planning Time: 0.542 ms
Execution Time: 0.510 ms
```

**scoped / ordinary / literal / IN**

```
Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e  (cost=0.32..8.64 rows=1 width=8) (actual time=0.022..0.076 rows=200 loops=1)
  Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
  Buffers: shared hit=6
Planning:
  Buffers: shared hit=15
Planning Time: 0.508 ms
Execution Time: 0.102 ms
```

**scoped / ordinary / disjoint / IN**

```
Append  (cost=0.29..34.85 rows=4 width=8) (actual time=0.041..0.366 rows=200 loops=1)
  Buffers: shared hit=24
  ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e  (cost=0.29..8.49 rows=1 width=8) (actual time=0.040..0.108 rows=200 loops=1)
        Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
        Filter: (everyone_level = ANY ('{1,2}'::smallint[]))
        Buffers: shared hit=6
  ->  Hash Join  (cost=8.50..8.64 rows=1 width=8) (actual time=0.076..0.077 rows=0 loops=1)
        Hash Cond: ((ap.value)::text = (e_1.path)::text)
        Buffers: shared hit=6
        ->  Function Scan on unnest ap  (cost=0.00..0.11 rows=11 width=32) (actual time=0.012..0.012 rows=1 loops=1)
        ->  Hash  (cost=8.49..8.49 rows=1 width=29) (actual time=0.054..0.055 rows=0 loops=1)
              Buckets: 1024  Batches: 1  Memory Usage: 8kB
              Buffers: shared hit=6
              ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_1  (cost=0.29..8.49 rows=1 width=29) (actual time=0.054..0.054 rows=0 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 200
                    Buffers: shared hit=6
  ->  Nested Loop  (cost=0.29..8.77 rows=1 width=8) (actual time=0.095..0.095 rows=0 loops=1)
        Join Filter: (((e_2.path)::text > (ar.lo)::text) AND ((e_2.path)::text < (ar.hi)::text))
        Buffers: shared hit=6
        ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_2  (cost=0.29..8.49 rows=1 width=29) (actual time=0.094..0.094 rows=0 loops=1)
              Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
              Filter: (everyone_level < '1'::smallint)
              Rows Removed by Filter: 200
              Buffers: shared hit=6
        ->  Function Scan on ar  (cost=0.01..0.12 rows=11 width=64) (never executed)
  ->  Nested Loop Anti Join  (cost=8.51..8.93 rows=1 width=8) (actual time=0.063..0.063 rows=0 loops=1)
        Join Filter: (((e_3.path)::text > (x0r.lo)::text) AND ((e_3.path)::text < (x0r.hi)::text))
        Buffers: shared hit=6
        ->  Hash Right Anti Join  (cost=8.51..8.65 rows=1 width=29) (actual time=0.063..0.063 rows=0 loops=1)
              Hash Cond: ((x0p.value)::text = (e_3.path)::text)
              Buffers: shared hit=6
              ->  Function Scan on unnest x0p  (cost=0.00..0.11 rows=11 width=32) (never executed)
              ->  Hash  (cost=8.49..8.49 rows=1 width=29) (actual time=0.055..0.056 rows=0 loops=1)
                    Buckets: 1024  Batches: 1  Memory Usage: 8kB
                    Buffers: shared hit=6
                    ->  Index Scan using ts_df1cf724_e_path on ts_df1cf724_e e_3  (cost=0.29..8.49 rows=1 width=29) (actual time=0.055..0.055 rows=0 loops=1)
                          Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                          Filter: ((everyone_level < '1'::smallint) AND ((owner_id)::text = 'u000042'::text))
                          Rows Removed by Filter: 200
                          Buffers: shared hit=6
        ->  Function Scan on x0r  (cost=0.01..0.12 rows=11 width=64) (never executed)
Planning Time: 0.600 ms
Execution Time: 0.467 ms
```

Total wall time 5s.
