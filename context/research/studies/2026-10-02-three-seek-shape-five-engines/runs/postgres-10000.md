## postgres — N=10,000 users: 230,203 entries, 660,000 chunks (3/file), 11,400 grant rows, 10,101 posture rows, 100 sibling traps

Load (tables, rows, indexes, statistics): 15s.

### Indexes

| index | size |
|---|---|
| `path` | 9.3 MB |
| `owner` | 2.9 MB |
| `lvlpath` | 9.3 MB |
| (entries table) | 15.6 MB |

### Callers

| caller | subjects | pieces (arms + owner) | bind bytes | compile us | visible entries |
|---|---|---|---|---|---|
| ordinary | u000042 | 88 | 2,445 | 127 | 20,124 |
| heavy group | u000003 | 88 | 2,445 | 39 | 20,124 |
| two subjects | u000042, u000032 | 220 | 6,094 | 120 | 20,103 |
| anonymous | — | 0 | 0 | 0 | 20,103 |
| system | — | 0 | 0 | 0 | 230,203 |

### Statements — cold = fresh connection, warm = median of 3 (ms); recall against the Python truth

Shapes: union, unionall, literal, fenced, disjoint. A blank cell is a shape that does not apply to that caller.

| caller | statement | union: cold / warm / recall | unionall: cold / warm / recall | literal: cold / warm / recall | fenced: cold / warm / recall | disjoint: cold / warm / recall |
|---|---|---|---|---|---|---|
| ordinary | entries | 62.1 / 127 / exact | 113 / 166 / exact | 38.2 / 43.6 / exact | 99.5 / 51.1 / exact | 58.1 / 74.7 / exact |
| ordinary | scoped | 50.6 / 16.3 / exact | 18.3 / 10.5 / exact | 8.6 / 12.4 / exact | 15.0 / 13.6 / exact | 12.2 / 8.6 / exact |
| ordinary | count | 155 / 215 / exact | 331 / 169 / exact | 113 / 81.5 / exact | 244 / 206 / exact | 202 / 100 / exact |
| ordinary | top10 | 82.4 / 77.4 / exact | 150 / 100 / exact | 35.7 / 7.5 / exact | 109 / 112 / exact | 68.5 / 65.2 / exact |
| heavy group | entries | 71.6 / 63.9 / exact | 86.6 / 22.8 / exact | 14.4 / 19.2 / exact | 18.9 / 16.9 / exact | 21.5 / 18.1 / exact |
| heavy group | scoped | 61.6 / 11.0 / exact | 10.0 / 12.1 / exact | 83.7 / 12.6 / exact | 36.3 / 19.4 / exact | 28.0 / 15.4 / exact |
| heavy group | count | 333 / 158 / exact | 258 / 171 / exact | 151 / 99.2 / exact | 151 / 107 / exact | 66.1 / 58.8 / exact |
| heavy group | top10 | 84.8 / 69.0 / exact | 94.9 / 101 / exact | 21.8 / 16.5 / exact | 238 / 90.1 / exact | 80.7 / 63.3 / exact |
| two subjects | entries | 120 / 54.9 / exact | 176 / 47.1 / exact | 98.1 / 80.8 / exact | 34.4 / 18.6 / exact | 20.4 / 22.7 / exact |
| two subjects | scoped | 8.6 / 3.2 / exact | 6.4 / 3.5 / exact | 7.8 / 5.6 / exact | 11.9 / 6.5 / exact | 6.6 / 3.3 / exact |
| two subjects | count | 64.2 / 57.6 / exact | 138 / 111 / exact | 69.1 / 76.8 / exact | 207 / 235 / exact | 211 / 141 / exact |
| two subjects | top10 | 133 / 65.2 / exact | 79.8 / 67.2 / exact | 9.0 / 3.7 / exact | 50.8 / 47.5 / exact | 110 / 114 / exact |
| anonymous | entries | 43.0 / 77.2 / exact |  |  |  |  |
| anonymous | scoped | 15.7 / 6.6 / exact |  |  |  |  |
| anonymous | count | 128 / 56.9 / exact |  |  |  |  |
| anonymous | top10 | 17.2 / 7.9 / exact |  |  |  |  |
| system | entries | 424 / 328 / exact |  |  |  |  |
| system | scoped | 5.2 / 2.2 / exact |  |  |  |  |
| system | count | 72.8 / 60.4 / exact |  |  |  |  |
| system | top10 | 9.0 / 3.5 / exact |  |  |  |  |

### Scoped read, branch 1 spelled `everyone_level >= :r` against `everyone_level IN (...)`

| caller | shape | `>=` cold / warm | `IN` cold / warm | recall |
|---|---|---|---|---|
| anonymous | union | 26.4 / 14.1 | 12.7 / 12.8 | exact |
| ordinary | union | 25.2 / 9.4 | 43.9 / 12.5 | exact |
| ordinary | unionall | 15.5 / 11.7 | 13.5 / 14.3 | exact |
| ordinary | literal | 24.2 / 12.4 | 20.8 / 49.1 | exact |
| ordinary | disjoint | 54.5 / 11.2 | 54.1 / 17.1 | exact |

### Plans

**ordinary / union / entries**

```
HashAggregate  (cost=112628.24..131348.37 rows=1050955 width=8) (actual time=14.101..16.199 rows=20124 loops=1)
  Group Key: e.id
  Planned Partitions: 16  Batches: 1  Memory Usage: 4113kB
  Buffers: shared hit=745
  ->  Append  (cost=528.97..56139.41 rows=1050955 width=8) (actual time=6.534..11.139 rows=20144 loops=1)
        Buffers: shared hit=745
        ->  Bitmap Heap Scan on ts_976f346d_e e  (cost=528.97..2672.57 rows=19168 width=8) (actual time=6.533..8.308 rows=20103 loops=1)
              Recheck Cond: (everyone_level >= '1'::smallint)
              Heap Blocks: exact=169
              Buffers: shared hit=271
              ->  Bitmap Index Scan on ts_976f346d_e_lvlpath  (cost=0.00..524.18 rows=19168 width=0) (actual time=0.459..0.459 rows=20103 loops=1)
                    Index Cond: (everyone_level >= '1'::smallint)
                    Buffers: shared hit=102
        ->  Nested Loop  (cost=0.42..371.80 rows=40 width=8) (actual time=0.052..0.196 rows=1 loops=1)
              Buffers: shared hit=176
              ->  Function Scan on unnest ap  (cost=0.00..0.44 rows=44 width=32) (actual time=0.025..0.027 rows=44 loops=1)
              ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_1  (cost=0.42..8.44 rows=1 width=29) (actual time=0.004..0.004 rows=0 loops=44)
                    Index Cond: ((path)::text = (ap.value)::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 1
                    Buffers: shared hit=176
        ->  Nested Loop  (cost=0.42..47806.27 rows=1031727 width=8) (actual time=0.030..1.031 rows=20 loops=1)
              Buffers: shared hit=291
              ->  Function Scan on ar  (cost=0.01..0.45 rows=44 width=64) (actual time=0.014..0.018 rows=44 loops=1)
              ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_2  (cost=0.42..852.02 rows=23448 width=29) (actual time=0.023..0.023 rows=0 loops=44)
                    Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 195
                    Buffers: shared hit=291
        ->  Index Scan using ts_976f346d_e_owner on ts_976f346d_e e_3  (cost=0.29..33.99 rows=20 width=8) (actual time=0.023..0.027 rows=20 loops=1)
              Index Cond: ((owner_id)::text = 'u000042'::text)
              Filter: (everyone_level < '1'::smallint)
              Rows Removed by Filter: 4
              Buffers: shared hit=7
Planning Time: 0.181 ms
JIT:
  Functions: 32
  Options: Inlining false, Optimization false, Expressions true, Deforming true
  Timing: Generation 1.701 ms (Deform 0.210 ms), Inlining 0.000 ms, Optimization 0.263 ms, Emission 5.827 ms, Total 7.791 ms
Execution Time: 18.648 ms
```

**ordinary / unionall / entries**

```
HashAggregate  (cost=112628.24..131348.37 rows=1050955 width=8) (actual time=23.766..28.978 rows=20124 loops=1)
  Group Key: e.id
  Planned Partitions: 16  Batches: 1  Memory Usage: 4113kB
  Buffers: shared hit=745
  ->  Append  (cost=528.97..56139.41 rows=1050955 width=8) (actual time=14.670..19.514 rows=20144 loops=1)
        Buffers: shared hit=745
        ->  Bitmap Heap Scan on ts_976f346d_e e  (cost=528.97..2672.57 rows=19168 width=8) (actual time=14.669..16.769 rows=20103 loops=1)
              Recheck Cond: (everyone_level >= '1'::smallint)
              Heap Blocks: exact=169
              Buffers: shared hit=271
              ->  Bitmap Index Scan on ts_976f346d_e_lvlpath  (cost=0.00..524.18 rows=19168 width=0) (actual time=0.466..0.466 rows=20103 loops=1)
                    Index Cond: (everyone_level >= '1'::smallint)
                    Buffers: shared hit=102
        ->  Nested Loop  (cost=0.42..371.80 rows=40 width=8) (actual time=0.048..0.141 rows=1 loops=1)
              Buffers: shared hit=176
              ->  Function Scan on unnest ap  (cost=0.00..0.44 rows=44 width=32) (actual time=0.026..0.028 rows=44 loops=1)
              ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_1  (cost=0.42..8.44 rows=1 width=29) (actual time=0.002..0.002 rows=0 loops=44)
                    Index Cond: ((path)::text = (ap.value)::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 1
                    Buffers: shared hit=176
        ->  Nested Loop  (cost=0.42..47806.27 rows=1031727 width=8) (actual time=0.015..0.916 rows=20 loops=1)
              Buffers: shared hit=291
              ->  Function Scan on ar  (cost=0.01..0.45 rows=44 width=64) (actual time=0.007..0.011 rows=44 loops=1)
              ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_2  (cost=0.42..852.02 rows=23448 width=29) (actual time=0.020..0.020 rows=0 loops=44)
                    Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 195
                    Buffers: shared hit=291
        ->  Index Scan using ts_976f346d_e_owner on ts_976f346d_e e_3  (cost=0.29..33.99 rows=20 width=8) (actual time=0.009..0.013 rows=20 loops=1)
              Index Cond: ((owner_id)::text = 'u000042'::text)
              Filter: (everyone_level < '1'::smallint)
              Rows Removed by Filter: 4
              Buffers: shared hit=7
Planning Time: 0.168 ms
JIT:
  Functions: 32
  Options: Inlining false, Optimization false, Expressions true, Deforming true
  Timing: Generation 0.501 ms (Deform 0.195 ms), Inlining 0.000 ms, Optimization 0.259 ms, Emission 13.963 ms, Total 14.723 ms
Execution Time: 30.238 ms
```

**ordinary / literal / entries**

```
Bitmap Heap Scan on ts_976f346d_e e  (cost=1144.42..7664.58 rows=19229 width=8) (actual time=0.915..2.681 rows=20124 loops=1)
  Recheck Cond: ((everyone_level >= '1'::smallint) OR ((path)::text = ANY ('{/home/u000042,/shared/s0001,/shared/s0004,/shared/s0005,/shared/s0006,/shared/s0008,/shared/s0012,/shared/s0013,/shared/s0016,/shared/s0021,/shared/s0022,/shared/s0030,/shared/s0031,/shared/s0033,/shared/s0036,/shared/s0037,/shared/s0041,/shared/s0043,/shared/s0045,/shared/s0048,/shared/s0053,/shared/s0055,/shared/s0056,/shared/s0058,/shared/s0059,/shared/s0061,/shared/s0062,/shared/s0063,/shared/s0066,/shared/s0067,/shared/s0071,/shared/s0075,/shared/s0077,/shared/s0078,/shared/s0082,/shared/s0085,/shared/s0088,/shared/s0089,/shared/s0091,/shared/s0092,/shared/s0094,/shared/s0097,/shared/s0098,/shared/s0099}'::text[])) OR (((path)::text > '/home/u000042/'::text) AND ((path)::text < '/home/u0000420'::text)) OR (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text)) OR (((path)::text > '/shared/s0004/'::text) AND ((path)::text < '/shared/s00040'::text)) OR (((path)::text > '/shared/s0005/'::text) AND ((path)::text < '/shared/s00050'::text)) OR (((path)::text > '/shared/s0006/'::text) AND ((path)::text < '/shared/s00060'::text)) OR (((path)::text > '/shared/s0008/'::text) AND ((path)::text < '/shared/s00080'::text)) OR (((path)::text > '/shared/s0012/'::text) AND ((path)::text < '/shared/s00120'::text)) OR (((path)::text > '/shared/s0013/'::text) AND ((path)::text < '/shared/s00130'::text)) OR (((path)::text > '/shared/s0016/'::text) AND ((path)::text < '/shared/s00160'::text)) OR (((path)::text > '/shared/s0021/'::text) AND ((path)::text < '/shared/s00210'::text)) OR (((path)::text > '/shared/s0022/'::text) AND ((path)::text < '/shared/s00220'::text)) OR (((path)::text > '/shared/s0030/'::text) AND ((path)::text < '/shared/s00300'::text)) OR (((path)::text > '/shared/s0031/'::text) AND ((path)::text < '/shared/s00310'::text)) OR (((path)::text > '/shared/s0033/'::text) AND ((path)::text < '/shared/s00330'::text)) OR (((path)::text > '/shared/s0036/'::text) AND ((path)::text < '/shared/s00360'::text)) OR (((path)::text > '/shared/s0037/'::text) AND ((path)::text < '/shared/s00370'::text)) OR (((path)::text > '/shared/s0041/'::text) AND ((path)::text < '/shared/s00410'::text)) OR (((path)::text > '/shared/s0043/'::text) AND ((path)::text < '/shared/s00430'::text)) OR (((path)::text > '/shared/s0045/'::text) AND ((path)::text < '/shared/s00450'::text)) OR (((path)::text > '/shared/s0048/'::text) AND ((path)::text < '/shared/s00480'::text)) OR (((path)::text > '/shared/s0053/'::text) AND ((path)::text < '/shared/s00530'::text)) OR (((path)::text > '/shared/s0055/'::text) AND ((path)::text < '/shared/s00550'::text)) OR (((path)::text > '/shared/s0056/'::text) AND ((path)::text < '/shared/s00560'::text)) OR (((path)::text > '/shared/s0058/'::text) AND ((path)::text < '/shared/s00580'::text)) OR (((path)::text > '/shared/s0059/'::text) AND ((path)::text < '/shared/s00590'::text)) OR (((path)::text > '/shared/s0061/'::text) AND ((path)::text < '/shared/s00610'::text)) OR (((path)::text > '/shared/s0062/'::text) AND ((path)::text < '/shared/s00620'::text)) OR (((path)::text > '/shared/s0063/'::text) AND ((path)::text < '/shared/s00630'::text)) OR (((path)::text > '/shared/s0066/'::text) AND ((path)::text < '/shared/s00660'::text)) OR (((path)::text > '/shared/s0067/'::text) AND ((path)::text < '/shared/s00670'::text)) OR (((path)::text > '/shared/s0071/'::text) AND ((path)::text < '/shared/s00710'::text)) OR (((path)::text > '/shared/s0075/'::text) AND ((path)::text < '/shared/s00750'::text)) OR (((path)::text > '/shared/s0077/'::text) AND ((path)::text < '/shared/s00770'::text)) OR (((path)::text > '/shared/s0078/'::text) AND ((path)::text < '/shared/s00780'::text)) OR (((path)::text > '/shared/s0082/'::text) AND ((path)::text < '/shared/s00820'::text)) OR (((path)::text > '/shared/s0085/'::text) AND ((path)::text < '/shared/s00850'::text)) OR (((path)::text > '/shared/s0088/'::text) AND ((path)::text < '/shared/s00880'::text)) OR (((path)::text > '/shared/s0089/'::text) AND ((path)::text < '/shared/s00890'::text)) OR (((path)::text > '/shared/s0091/'::text) AND ((path)::text < '/shared/s00910'::text)) OR (((path)::text > '/shared/s0092/'::text) AND ((path)::text < '/shared/s00920'::text)) OR (((path)::text > '/shared/s0094/'::text) AND ((path)::text < '/shared/s00940'::text)) OR (((path)::text > '/shared/s0097/'::text) AND ((path)::text < '/shared/s00970'::text)) OR (((path)::text > '/shared/s0098/'::text) AND ((path)::text < '/shared/s00980'::text)) OR (((path)::text > '/shared/s0099/'::text) AND ((path)::text < '/shared/s00990'::text)) OR ((owner_id)::text = 'u000042'::text))
  Heap Blocks: exact=170
  Buffers: shared hit=581
  ->  BitmapOr  (cost=1144.31..1144.31 rows=19234 width=0) (actual time=0.898..0.917 rows=0 loops=1)
        Buffers: shared hit=411
        ->  Bitmap Index Scan on ts_976f346d_e_lvlpath  (cost=0.00..524.18 rows=19168 width=0) (actual time=0.467..0.467 rows=20103 loops=1)
              Index Cond: (everyone_level >= '1'::smallint)
              Buffers: shared hit=102
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..194.81 rows=44 width=0) (actual time=0.076..0.076 rows=44 loops=1)
              Index Cond: ((path)::text = ANY ('{/home/u000042,/shared/s0001,/shared/s0004,/shared/s0005,/shared/s0006,/shared/s0008,/shared/s0012,/shared/s0013,/shared/s0016,/shared/s0021,/shared/s0022,/shared/s0030,/shared/s0031,/shared/s0033,/shared/s0036,/shared/s0037,/shared/s0041,/shared/s0043,/shared/s0045,/shared/s0048,/shared/s0053,/shared/s0055,/shared/s0056,/shared/s0058,/shared/s0059,/shared/s0061,/shared/s0062,/shared/s0063,/shared/s0066,/shared/s0067,/shared/s0071,/shared/s0075,/shared/s0077,/shared/s0078,/shared/s0082,/shared/s0085,/shared/s0088,/shared/s0089,/shared/s0091,/shared/s0092,/shared/s0094,/shared/s0097,/shared/s0098,/shared/s0099}'::text[]))
              Buffers: shared hit=132
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=20 loops=1)
              Index Cond: (((path)::text > '/home/u000042/'::text) AND ((path)::text < '/home/u0000420'::text))
              Buffers: shared hit=3
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.013..0.014 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0004/'::text) AND ((path)::text < '/shared/s00040'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0005/'::text) AND ((path)::text < '/shared/s00050'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0006/'::text) AND ((path)::text < '/shared/s00060'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0008/'::text) AND ((path)::text < '/shared/s00080'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0012/'::text) AND ((path)::text < '/shared/s00120'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0013/'::text) AND ((path)::text < '/shared/s00130'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0016/'::text) AND ((path)::text < '/shared/s00160'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0021/'::text) AND ((path)::text < '/shared/s00210'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0022/'::text) AND ((path)::text < '/shared/s00220'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0030/'::text) AND ((path)::text < '/shared/s00300'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0031/'::text) AND ((path)::text < '/shared/s00310'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0033/'::text) AND ((path)::text < '/shared/s00330'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0036/'::text) AND ((path)::text < '/shared/s00360'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0037/'::text) AND ((path)::text < '/shared/s00370'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0041/'::text) AND ((path)::text < '/shared/s00410'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.009 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0043/'::text) AND ((path)::text < '/shared/s00430'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.009..0.020 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0045/'::text) AND ((path)::text < '/shared/s00450'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0048/'::text) AND ((path)::text < '/shared/s00480'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0053/'::text) AND ((path)::text < '/shared/s00530'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0055/'::text) AND ((path)::text < '/shared/s00550'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0056/'::text) AND ((path)::text < '/shared/s00560'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0058/'::text) AND ((path)::text < '/shared/s00580'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.009..0.009 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0059/'::text) AND ((path)::text < '/shared/s00590'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0061/'::text) AND ((path)::text < '/shared/s00610'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.007 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0062/'::text) AND ((path)::text < '/shared/s00620'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0063/'::text) AND ((path)::text < '/shared/s00630'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0066/'::text) AND ((path)::text < '/shared/s00660'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0067/'::text) AND ((path)::text < '/shared/s00670'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.009..0.009 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0071/'::text) AND ((path)::text < '/shared/s00710'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0075/'::text) AND ((path)::text < '/shared/s00750'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0077/'::text) AND ((path)::text < '/shared/s00770'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0078/'::text) AND ((path)::text < '/shared/s00780'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.008 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0082/'::text) AND ((path)::text < '/shared/s00820'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.008 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0085/'::text) AND ((path)::text < '/shared/s00850'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0088/'::text) AND ((path)::text < '/shared/s00880'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0089/'::text) AND ((path)::text < '/shared/s00890'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.021..0.021 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0091/'::text) AND ((path)::text < '/shared/s00910'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0092/'::text) AND ((path)::text < '/shared/s00920'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.009..0.009 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0094/'::text) AND ((path)::text < '/shared/s00940'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0097/'::text) AND ((path)::text < '/shared/s00970'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0098/'::text) AND ((path)::text < '/shared/s00980'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
              Index Cond: (((path)::text > '/shared/s0099/'::text) AND ((path)::text < '/shared/s00990'::text))
              Buffers: shared hit=4
        ->  Bitmap Index Scan on ts_976f346d_e_owner  (cost=0.00..4.46 rows=22 width=0) (actual time=0.006..0.006 rows=24 loops=1)
              Index Cond: ((owner_id)::text = 'u000042'::text)
              Buffers: shared hit=2
Planning:
  Buffers: shared hit=104
Planning Time: 0.597 ms
Execution Time: 7.731 ms
```

**ordinary / fenced / entries**

```
HashAggregate  (cost=112628.24..131348.37 rows=1050955 width=8) (actual time=12.906..22.968 rows=20124 loops=1)
  Group Key: e.id
  Planned Partitions: 16  Batches: 1  Memory Usage: 4113kB
  Buffers: shared hit=745
  ->  Append  (cost=528.97..56139.41 rows=1050955 width=8) (actual time=0.488..10.007 rows=20144 loops=1)
        Buffers: shared hit=745
        ->  Bitmap Heap Scan on ts_976f346d_e e  (cost=528.97..2672.57 rows=19168 width=8) (actual time=0.487..2.535 rows=20103 loops=1)
              Recheck Cond: (everyone_level >= '1'::smallint)
              Heap Blocks: exact=169
              Buffers: shared hit=271
              ->  Bitmap Index Scan on ts_976f346d_e_lvlpath  (cost=0.00..524.18 rows=19168 width=0) (actual time=0.472..0.472 rows=20103 loops=1)
                    Index Cond: (everyone_level >= '1'::smallint)
                    Buffers: shared hit=102
        ->  Nested Loop  (cost=0.42..371.80 rows=40 width=8) (actual time=0.042..0.151 rows=1 loops=1)
              Buffers: shared hit=176
              ->  Function Scan on unnest ap  (cost=0.00..0.44 rows=44 width=32) (actual time=0.011..0.014 rows=44 loops=1)
              ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_1  (cost=0.42..8.44 rows=1 width=29) (actual time=0.003..0.003 rows=0 loops=44)
                    Index Cond: ((path)::text = (ap.value)::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 1
                    Buffers: shared hit=176
        ->  Nested Loop  (cost=0.42..47806.27 rows=1031727 width=8) (actual time=0.016..5.574 rows=20 loops=1)
              Buffers: shared hit=291
              ->  Function Scan on ar  (cost=0.01..0.45 rows=44 width=64) (actual time=0.009..0.017 rows=44 loops=1)
              ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_2  (cost=0.42..852.02 rows=23448 width=29) (actual time=0.123..0.123 rows=0 loops=44)
                    Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 195
                    Buffers: shared hit=291
        ->  Index Scan using ts_976f346d_e_owner on ts_976f346d_e e_3  (cost=0.29..33.99 rows=20 width=8) (actual time=0.036..0.058 rows=20 loops=1)
              Index Cond: ((owner_id)::text = 'u000042'::text)
              Filter: (everyone_level < '1'::smallint)
              Rows Removed by Filter: 4
              Buffers: shared hit=7
Planning Time: 0.220 ms
Execution Time: 23.700 ms
```

**ordinary / disjoint / entries**

```
Append  (cost=528.97..56160.52 rows=1050953 width=8) (actual time=0.541..6.965 rows=20124 loops=1)
  Buffers: shared hit=745
  ->  Bitmap Heap Scan on ts_976f346d_e e  (cost=528.97..2672.57 rows=19168 width=8) (actual time=0.540..2.269 rows=20103 loops=1)
        Recheck Cond: (everyone_level >= '1'::smallint)
        Heap Blocks: exact=169
        Buffers: shared hit=271
        ->  Bitmap Index Scan on ts_976f346d_e_lvlpath  (cost=0.00..524.18 rows=19168 width=0) (actual time=0.488..0.488 rows=20103 loops=1)
              Index Cond: (everyone_level >= '1'::smallint)
              Buffers: shared hit=102
  ->  Nested Loop  (cost=0.42..371.80 rows=40 width=8) (actual time=0.098..0.204 rows=1 loops=1)
        Buffers: shared hit=176
        ->  Function Scan on unnest ap  (cost=0.00..0.44 rows=44 width=32) (actual time=0.084..0.086 rows=44 loops=1)
        ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_1  (cost=0.42..8.44 rows=1 width=29) (actual time=0.002..0.002 rows=0 loops=44)
              Index Cond: ((path)::text = (ap.value)::text)
              Filter: (everyone_level < '1'::smallint)
              Rows Removed by Filter: 1
              Buffers: shared hit=176
  ->  Nested Loop  (cost=0.42..47806.27 rows=1031727 width=8) (actual time=0.012..0.837 rows=20 loops=1)
        Buffers: shared hit=291
        ->  Function Scan on ar  (cost=0.01..0.45 rows=44 width=64) (actual time=0.006..0.010 rows=44 loops=1)
        ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_2  (cost=0.42..852.02 rows=23448 width=29) (actual time=0.018..0.019 rows=0 loops=44)
              Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
              Filter: (everyone_level < '1'::smallint)
              Rows Removed by Filter: 195
              Buffers: shared hit=291
  ->  Hash Anti Join  (cost=1.29..55.12 rows=18 width=8) (actual time=0.043..0.043 rows=0 loops=1)
        Hash Cond: ((e_3.path)::text = (x0p.value)::text)
        Buffers: shared hit=7
        ->  Nested Loop Anti Join  (cost=0.30..53.90 rows=18 width=29) (actual time=0.042..0.042 rows=0 loops=1)
              Join Filter: (((e_3.path)::text > (x0r.lo)::text) AND ((e_3.path)::text < (x0r.hi)::text))
              Buffers: shared hit=7
              ->  Index Scan using ts_976f346d_e_owner on ts_976f346d_e e_3  (cost=0.29..33.99 rows=20 width=29) (actual time=0.010..0.014 rows=20 loops=1)
                    Index Cond: ((owner_id)::text = 'u000042'::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 4
                    Buffers: shared hit=7
              ->  Function Scan on x0r  (cost=0.01..0.45 rows=44 width=64) (actual time=0.001..0.001 rows=1 loops=20)
        ->  Hash  (cost=0.44..0.44 rows=44 width=32) (never executed)
              ->  Function Scan on unnest x0p  (cost=0.00..0.44 rows=44 width=32) (never executed)
Planning Time: 0.214 ms
Execution Time: 7.595 ms
```

**ordinary / union / scoped**

```
Unique  (cost=35.61..35.65 rows=8 width=8) (actual time=0.160..0.202 rows=200 loops=1)
  Buffers: shared hit=28
  ->  Sort  (cost=35.61..35.63 rows=8 width=8) (actual time=0.160..0.172 rows=200 loops=1)
        Sort Key: e.id
        Sort Method: quicksort  Memory: 25kB
        Buffers: shared hit=28
        ->  Append  (cost=0.42..35.49 rows=8 width=8) (actual time=0.021..0.147 rows=200 loops=1)
              Buffers: shared hit=28
              ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e  (cost=0.42..8.44 rows=1 width=8) (actual time=0.021..0.050 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: (everyone_level >= '1'::smallint)
                    Buffers: shared hit=7
              ->  Hash Join  (cost=8.46..9.01 rows=1 width=8) (actual time=0.033..0.033 rows=0 loops=1)
                    Hash Cond: ((ap.value)::text = (e_1.path)::text)
                    Buffers: shared hit=7
                    ->  Function Scan on unnest ap  (cost=0.00..0.44 rows=44 width=32) (actual time=0.006..0.006 rows=1 loops=1)
                    ->  Hash  (cost=8.44..8.44 rows=1 width=29) (actual time=0.022..0.022 rows=0 loops=1)
                          Buckets: 1024  Batches: 1  Memory Usage: 8kB
                          Buffers: shared hit=7
                          ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_1  (cost=0.42..8.44 rows=1 width=29) (actual time=0.022..0.022 rows=0 loops=1)
                                Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 200
                                Buffers: shared hit=7
              ->  Nested Loop  (cost=0.42..9.55 rows=5 width=8) (actual time=0.025..0.025 rows=0 loops=1)
                    Join Filter: (((e_2.path)::text > (ar.lo)::text) AND ((e_2.path)::text < (ar.hi)::text))
                    Buffers: shared hit=7
                    ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_2  (cost=0.42..8.44 rows=1 width=29) (actual time=0.024..0.024 rows=0 loops=1)
                          Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                          Filter: (everyone_level < '1'::smallint)
                          Rows Removed by Filter: 200
                          Buffers: shared hit=7
                    ->  Function Scan on ar  (cost=0.01..0.45 rows=44 width=64) (never executed)
              ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_3  (cost=0.42..8.45 rows=1 width=8) (actual time=0.023..0.023 rows=0 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: ((everyone_level < '1'::smallint) AND ((owner_id)::text = 'u000042'::text))
                    Rows Removed by Filter: 200
                    Buffers: shared hit=7
Planning Time: 0.209 ms
Execution Time: 0.244 ms
```

**ordinary / unionall / scoped**

```
Unique  (cost=35.61..35.65 rows=8 width=8) (actual time=0.267..0.307 rows=200 loops=1)
  Buffers: shared hit=28
  ->  Sort  (cost=35.61..35.63 rows=8 width=8) (actual time=0.267..0.279 rows=200 loops=1)
        Sort Key: e.id
        Sort Method: quicksort  Memory: 25kB
        Buffers: shared hit=28
        ->  Append  (cost=0.42..35.49 rows=8 width=8) (actual time=0.031..0.254 rows=200 loops=1)
              Buffers: shared hit=28
              ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e  (cost=0.42..8.44 rows=1 width=8) (actual time=0.030..0.059 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: (everyone_level >= '1'::smallint)
                    Buffers: shared hit=7
              ->  Hash Join  (cost=8.46..9.01 rows=1 width=8) (actual time=0.034..0.035 rows=0 loops=1)
                    Hash Cond: ((ap.value)::text = (e_1.path)::text)
                    Buffers: shared hit=7
                    ->  Function Scan on unnest ap  (cost=0.00..0.44 rows=44 width=32) (actual time=0.008..0.008 rows=1 loops=1)
                    ->  Hash  (cost=8.44..8.44 rows=1 width=29) (actual time=0.021..0.022 rows=0 loops=1)
                          Buckets: 1024  Batches: 1  Memory Usage: 8kB
                          Buffers: shared hit=7
                          ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_1  (cost=0.42..8.44 rows=1 width=29) (actual time=0.021..0.021 rows=0 loops=1)
                                Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 200
                                Buffers: shared hit=7
              ->  Nested Loop  (cost=0.42..9.55 rows=5 width=8) (actual time=0.020..0.021 rows=0 loops=1)
                    Join Filter: (((e_2.path)::text > (ar.lo)::text) AND ((e_2.path)::text < (ar.hi)::text))
                    Buffers: shared hit=7
                    ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_2  (cost=0.42..8.44 rows=1 width=29) (actual time=0.020..0.020 rows=0 loops=1)
                          Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                          Filter: (everyone_level < '1'::smallint)
                          Rows Removed by Filter: 200
                          Buffers: shared hit=7
                    ->  Function Scan on ar  (cost=0.01..0.45 rows=44 width=64) (never executed)
              ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_3  (cost=0.42..8.45 rows=1 width=8) (actual time=0.122..0.122 rows=0 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: ((everyone_level < '1'::smallint) AND ((owner_id)::text = 'u000042'::text))
                    Rows Removed by Filter: 200
                    Buffers: shared hit=7
Planning Time: 0.639 ms
Execution Time: 0.349 ms
```

**ordinary / literal / scoped**

```
Index Scan using ts_976f346d_e_path on ts_976f346d_e e  (cost=0.53..8.78 rows=1 width=8) (actual time=0.011..0.033 rows=200 loops=1)
  Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
  Buffers: shared hit=7
Planning:
  Buffers: shared hit=104
Planning Time: 0.557 ms
Execution Time: 0.046 ms
```

**ordinary / fenced / scoped**

```
Unique  (cost=35.61..35.65 rows=8 width=8) (actual time=0.349..0.388 rows=200 loops=1)
  Buffers: shared hit=28
  ->  Sort  (cost=35.61..35.63 rows=8 width=8) (actual time=0.349..0.361 rows=200 loops=1)
        Sort Key: e.id
        Sort Method: quicksort  Memory: 25kB
        Buffers: shared hit=28
        ->  Append  (cost=0.42..35.49 rows=8 width=8) (actual time=0.022..0.330 rows=200 loops=1)
              Buffers: shared hit=28
              ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e  (cost=0.42..8.44 rows=1 width=8) (actual time=0.021..0.051 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: (everyone_level >= '1'::smallint)
                    Buffers: shared hit=7
              ->  Hash Join  (cost=8.46..9.01 rows=1 width=8) (actual time=0.222..0.222 rows=0 loops=1)
                    Hash Cond: ((ap.value)::text = (e_1.path)::text)
                    Buffers: shared hit=7
                    ->  Function Scan on unnest ap  (cost=0.00..0.44 rows=44 width=32) (actual time=0.194..0.194 rows=1 loops=1)
                    ->  Hash  (cost=8.44..8.44 rows=1 width=29) (actual time=0.023..0.024 rows=0 loops=1)
                          Buckets: 1024  Batches: 1  Memory Usage: 8kB
                          Buffers: shared hit=7
                          ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_1  (cost=0.42..8.44 rows=1 width=29) (actual time=0.023..0.023 rows=0 loops=1)
                                Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 200
                                Buffers: shared hit=7
              ->  Nested Loop  (cost=0.42..9.55 rows=5 width=8) (actual time=0.020..0.020 rows=0 loops=1)
                    Join Filter: (((e_2.path)::text > (ar.lo)::text) AND ((e_2.path)::text < (ar.hi)::text))
                    Buffers: shared hit=7
                    ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_2  (cost=0.42..8.44 rows=1 width=29) (actual time=0.020..0.020 rows=0 loops=1)
                          Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                          Filter: (everyone_level < '1'::smallint)
                          Rows Removed by Filter: 200
                          Buffers: shared hit=7
                    ->  Function Scan on ar  (cost=0.01..0.45 rows=44 width=64) (never executed)
              ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_3  (cost=0.42..8.45 rows=1 width=8) (actual time=0.021..0.021 rows=0 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: ((everyone_level < '1'::smallint) AND ((owner_id)::text = 'u000042'::text))
                    Rows Removed by Filter: 200
                    Buffers: shared hit=7
Planning Time: 0.518 ms
Execution Time: 0.434 ms
```

**ordinary / disjoint / scoped**

```
Append  (cost=0.42..37.16 rows=8 width=8) (actual time=0.020..0.161 rows=200 loops=1)
  Buffers: shared hit=28
  ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e  (cost=0.42..8.44 rows=1 width=8) (actual time=0.020..0.060 rows=200 loops=1)
        Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
        Filter: (everyone_level >= '1'::smallint)
        Buffers: shared hit=7
  ->  Hash Join  (cost=8.46..9.01 rows=1 width=8) (actual time=0.032..0.032 rows=0 loops=1)
        Hash Cond: ((ap.value)::text = (e_1.path)::text)
        Buffers: shared hit=7
        ->  Function Scan on unnest ap  (cost=0.00..0.44 rows=44 width=32) (actual time=0.007..0.007 rows=1 loops=1)
        ->  Hash  (cost=8.44..8.44 rows=1 width=29) (actual time=0.021..0.021 rows=0 loops=1)
              Buckets: 1024  Batches: 1  Memory Usage: 8kB
              Buffers: shared hit=7
              ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_1  (cost=0.42..8.44 rows=1 width=29) (actual time=0.020..0.020 rows=0 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 200
                    Buffers: shared hit=7
  ->  Nested Loop  (cost=0.42..9.55 rows=5 width=8) (actual time=0.020..0.020 rows=0 loops=1)
        Join Filter: (((e_2.path)::text > (ar.lo)::text) AND ((e_2.path)::text < (ar.hi)::text))
        Buffers: shared hit=7
        ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_2  (cost=0.42..8.44 rows=1 width=29) (actual time=0.019..0.019 rows=0 loops=1)
              Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
              Filter: (everyone_level < '1'::smallint)
              Rows Removed by Filter: 200
              Buffers: shared hit=7
        ->  Function Scan on ar  (cost=0.01..0.45 rows=44 width=64) (never executed)
  ->  Nested Loop Anti Join  (cost=8.46..10.12 rows=1 width=8) (actual time=0.031..0.031 rows=0 loops=1)
        Join Filter: (((e_3.path)::text > (x0r.lo)::text) AND ((e_3.path)::text < (x0r.hi)::text))
        Buffers: shared hit=7
        ->  Hash Right Anti Join  (cost=8.46..9.02 rows=1 width=29) (actual time=0.031..0.031 rows=0 loops=1)
              Hash Cond: ((x0p.value)::text = (e_3.path)::text)
              Buffers: shared hit=7
              ->  Function Scan on unnest x0p  (cost=0.00..0.44 rows=44 width=32) (never executed)
              ->  Hash  (cost=8.45..8.45 rows=1 width=29) (actual time=0.022..0.022 rows=0 loops=1)
                    Buckets: 1024  Batches: 1  Memory Usage: 8kB
                    Buffers: shared hit=7
                    ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_3  (cost=0.42..8.45 rows=1 width=29) (actual time=0.022..0.022 rows=0 loops=1)
                          Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                          Filter: ((everyone_level < '1'::smallint) AND ((owner_id)::text = 'u000042'::text))
                          Rows Removed by Filter: 200
                          Buffers: shared hit=7
        ->  Function Scan on x0r  (cost=0.01..0.45 rows=44 width=64) (never executed)
Planning Time: 0.206 ms
Execution Time: 0.238 ms
```

**ordinary / union / count**

```
Finalize Aggregate  (cost=166846.53..166846.54 rows=1 width=8) (actual time=147.042..147.116 rows=1 loops=1)
  Buffers: shared hit=6511, temp read=2172 written=2172
  ->  Gather  (cost=166846.31..166846.52 rows=2 width=8) (actual time=147.029..147.108 rows=3 loops=1)
        Workers Planned: 2
        Workers Launched: 2
        Buffers: shared hit=6511, temp read=2172 written=2172
        ->  Partial Aggregate  (cost=165846.31..165846.32 rows=1 width=8) (actual time=114.016..114.021 rows=1 loops=3)
              Buffers: shared hit=6511, temp read=2172 written=2172
              ->  Hash Join  (cost=148591.31..162523.20 rows=1329246 width=0) (actual time=59.301..112.747 rows=20020 loops=3)
                    Hash Cond: (c.entry_id = e.id)
                    Buffers: shared hit=6511, temp read=2172 written=2172
                    ->  Parallel Seq Scan on ts_976f346d_c c  (cost=0.00..6954.00 rows=275000 width=8) (actual time=16.239..36.992 rows=220000 loops=3)
                          Buffers: shared hit=4204
                    ->  Hash  (cost=131348.37..131348.37 rows=1050955 width=8) (actual time=19.311..19.315 rows=20124 loops=3)
                          Buckets: 262144  Batches: 8  Memory Usage: 2145kB
                          Buffers: shared hit=2241, temp written=168
                          ->  HashAggregate  (cost=112628.24..131348.37 rows=1050955 width=8) (actual time=14.761..16.829 rows=20124 loops=3)
                                Group Key: e.id
                                Planned Partitions: 16  Batches: 1  Memory Usage: 4113kB
                                Buffers: shared hit=2241
                                Worker 0:  Batches: 1  Memory Usage: 4113kB
                                Worker 1:  Batches: 1  Memory Usage: 4113kB
                                ->  Append  (cost=528.97..56139.41 rows=1050955 width=8) (actual time=0.586..6.587 rows=20144 loops=3)
                                      Buffers: shared hit=2241
                                      ->  Bitmap Heap Scan on ts_976f346d_e e  (cost=528.97..2672.57 rows=19168 width=8) (actual time=0.585..3.350 rows=20103 loops=3)
                                            Recheck Cond: (everyone_level >= '1'::smallint)
                                            Heap Blocks: exact=169
                                            Buffers: shared hit=815
                                            ->  Bitmap Index Scan on ts_976f346d_e_lvlpath  (cost=0.00..524.18 rows=19168 width=0) (actual time=0.550..0.550 rows=20103 loops=3)
                                                  Index Cond: (everyone_level >= '1'::smallint)
                                                  Buffers: shared hit=308
                                      ->  Nested Loop  (cost=0.42..371.80 rows=40 width=8) (actual time=0.063..0.605 rows=1 loops=3)
                                            Buffers: shared hit=530
                                            ->  Function Scan on unnest ap  (cost=0.00..0.44 rows=44 width=32) (actual time=0.031..0.034 rows=44 loops=3)
                                            ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_1  (cost=0.42..8.44 rows=1 width=29) (actual time=0.013..0.013 rows=0 loops=132)
                                                  Index Cond: ((path)::text = (ap.value)::text)
                                                  Filter: (everyone_level < '1'::smallint)
                                                  Rows Removed by Filter: 1
                                                  Buffers: shared hit=530
                                      ->  Nested Loop  (cost=0.42..47806.27 rows=1031727 width=8) (actual time=0.033..0.964 rows=20 loops=3)
                                            Buffers: shared hit=873
                                            ->  Function Scan on ar  (cost=0.01..0.45 rows=44 width=64) (actual time=0.016..0.021 rows=44 loops=3)
                                            ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_2  (cost=0.42..852.02 rows=23448 width=29) (actual time=0.021..0.021 rows=0 loops=132)
                                                  Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                                                  Filter: (everyone_level < '1'::smallint)
                                                  Rows Removed by Filter: 195
                                                  Buffers: shared hit=873
                                      ->  Index Scan using ts_976f346d_e_owner on ts_976f346d_e e_3  (cost=0.29..33.99 rows=20 width=8) (actual time=0.025..0.030 rows=20 loops=3)
                                            Index Cond: ((owner_id)::text = 'u000042'::text)
                                            Filter: (everyone_level < '1'::smallint)
                                            Rows Removed by Filter: 4
                                            Buffers: shared hit=23
Planning Time: 0.200 ms
JIT:
  Functions: 125
  Options: Inlining false, Optimization false, Expressions true, Deforming true
  Timing: Generation 6.882 ms (Deform 4.660 ms), Inlining 0.000 ms, Optimization 1.472 ms, Emission 47.494 ms, Total 55.848 ms
Execution Time: 150.109 ms
```

**ordinary / unionall / count**

```
Finalize Aggregate  (cost=166846.53..166846.54 rows=1 width=8) (actual time=234.602..244.294 rows=1 loops=1)
  Buffers: shared hit=6511, temp read=2173 written=2173
  ->  Gather  (cost=166846.31..166846.52 rows=2 width=8) (actual time=223.669..244.266 rows=3 loops=1)
        Workers Planned: 2
        Workers Launched: 2
        Buffers: shared hit=6511, temp read=2173 written=2173
        ->  Partial Aggregate  (cost=165846.31..165846.32 rows=1 width=8) (actual time=212.092..212.098 rows=1 loops=3)
              Buffers: shared hit=6511, temp read=2173 written=2173
              ->  Hash Join  (cost=148591.31..162523.20 rows=1329246 width=0) (actual time=137.894..210.994 rows=20020 loops=3)
                    Hash Cond: (c.entry_id = e.id)
                    Buffers: shared hit=6511, temp read=2173 written=2173
                    ->  Parallel Seq Scan on ts_976f346d_c c  (cost=0.00..6954.00 rows=275000 width=8) (actual time=23.860..89.633 rows=220000 loops=3)
                          Buffers: shared hit=4204
                    ->  Hash  (cost=131348.37..131348.37 rows=1050955 width=8) (actual time=30.250..30.255 rows=20124 loops=3)
                          Buckets: 262144  Batches: 8  Memory Usage: 2145kB
                          Buffers: shared hit=2241, temp written=168
                          ->  HashAggregate  (cost=112628.24..131348.37 rows=1050955 width=8) (actual time=15.025..18.168 rows=20124 loops=3)
                                Group Key: e.id
                                Planned Partitions: 16  Batches: 1  Memory Usage: 4113kB
                                Buffers: shared hit=2241
                                Worker 0:  Batches: 1  Memory Usage: 4113kB
                                Worker 1:  Batches: 1  Memory Usage: 4113kB
                                ->  Append  (cost=528.97..56139.41 rows=1050955 width=8) (actual time=2.560..7.717 rows=20144 loops=3)
                                      Buffers: shared hit=2241
                                      ->  Bitmap Heap Scan on ts_976f346d_e e  (cost=528.97..2672.57 rows=19168 width=8) (actual time=2.559..4.437 rows=20103 loops=3)
                                            Recheck Cond: (everyone_level >= '1'::smallint)
                                            Heap Blocks: exact=169
                                            Buffers: shared hit=815
                                            ->  Bitmap Index Scan on ts_976f346d_e_lvlpath  (cost=0.00..524.18 rows=19168 width=0) (actual time=1.622..1.622 rows=20103 loops=3)
                                                  Index Cond: (everyone_level >= '1'::smallint)
                                                  Buffers: shared hit=308
                                      ->  Nested Loop  (cost=0.42..371.80 rows=40 width=8) (actual time=0.054..0.148 rows=1 loops=3)
                                            Buffers: shared hit=530
                                            ->  Function Scan on unnest ap  (cost=0.00..0.44 rows=44 width=32) (actual time=0.024..0.027 rows=44 loops=3)
                                            ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_1  (cost=0.42..8.44 rows=1 width=29) (actual time=0.002..0.002 rows=0 loops=132)
                                                  Index Cond: ((path)::text = (ap.value)::text)
                                                  Filter: (everyone_level < '1'::smallint)
                                                  Rows Removed by Filter: 1
                                                  Buffers: shared hit=530
                                      ->  Nested Loop  (cost=0.42..47806.27 rows=1031727 width=8) (actual time=0.019..1.257 rows=20 loops=3)
                                            Buffers: shared hit=873
                                            ->  Function Scan on ar  (cost=0.01..0.45 rows=44 width=64) (actual time=0.008..0.011 rows=44 loops=3)
                                            ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_2  (cost=0.42..852.02 rows=23448 width=29) (actual time=0.028..0.028 rows=0 loops=132)
                                                  Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                                                  Filter: (everyone_level < '1'::smallint)
                                                  Rows Removed by Filter: 195
                                                  Buffers: shared hit=873
                                      ->  Index Scan using ts_976f346d_e_owner on ts_976f346d_e e_3  (cost=0.29..33.99 rows=20 width=8) (actual time=0.019..0.023 rows=20 loops=3)
                                            Index Cond: ((owner_id)::text = 'u000042'::text)
                                            Filter: (everyone_level < '1'::smallint)
                                            Rows Removed by Filter: 4
                                            Buffers: shared hit=23
Planning Time: 0.208 ms
JIT:
  Functions: 125
  Options: Inlining false, Optimization false, Expressions true, Deforming true
  Timing: Generation 3.025 ms (Deform 0.808 ms), Inlining 0.000 ms, Optimization 0.972 ms, Emission 70.813 ms, Total 74.810 ms
Execution Time: 245.628 ms
```

**ordinary / literal / count**

```
Finalize Aggregate  (cost=14638.73..14638.74 rows=1 width=8) (actual time=92.163..94.900 rows=1 loops=1)
  Buffers: shared hit=4855
  ->  Gather  (cost=14638.51..14638.72 rows=2 width=8) (actual time=88.973..94.895 rows=3 loops=1)
        Workers Planned: 2
        Workers Launched: 2
        Buffers: shared hit=4855
        ->  Partial Aggregate  (cost=13638.51..13638.52 rows=1 width=8) (actual time=67.606..67.620 rows=1 loops=3)
              Buffers: shared hit=4855
              ->  Parallel Hash Join  (cost=5905.20..13581.08 rows=22971 width=0) (actual time=41.054..66.517 rows=20020 loops=3)
                    Hash Cond: (c.entry_id = e.id)
                    Buffers: shared hit=4855
                    ->  Parallel Seq Scan on ts_976f346d_c c  (cost=0.00..6954.00 rows=275000 width=8) (actual time=0.018..29.536 rows=220000 loops=3)
                          Buffers: shared hit=4204
                    ->  Parallel Hash  (cost=5763.81..5763.81 rows=11311 width=8) (actual time=5.889..5.901 rows=6708 loops=3)
                          Buckets: 32768  Batches: 1  Memory Usage: 1088kB
                          Buffers: shared hit=581
                          ->  Parallel Bitmap Heap Scan on ts_976f346d_e e  (cost=1144.42..5763.81 rows=11311 width=8) (actual time=0.466..1.912 rows=10062 loops=2)
                                Recheck Cond: ((everyone_level >= '1'::smallint) OR ((path)::text = ANY ('{/home/u000042,/shared/s0001,/shared/s0004,/shared/s0005,/shared/s0006,/shared/s0008,/shared/s0012,/shared/s0013,/shared/s0016,/shared/s0021,/shared/s0022,/shared/s0030,/shared/s0031,/shared/s0033,/shared/s0036,/shared/s0037,/shared/s0041,/shared/s0043,/shared/s0045,/shared/s0048,/shared/s0053,/shared/s0055,/shared/s0056,/shared/s0058,/shared/s0059,/shared/s0061,/shared/s0062,/shared/s0063,/shared/s0066,/shared/s0067,/shared/s0071,/shared/s0075,/shared/s0077,/shared/s0078,/shared/s0082,/shared/s0085,/shared/s0088,/shared/s0089,/shared/s0091,/shared/s0092,/shared/s0094,/shared/s0097,/shared/s0098,/shared/s0099}'::text[])) OR (((path)::text > '/home/u000042/'::text) AND ((path)::text < '/home/u0000420'::text)) OR (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text)) OR (((path)::text > '/shared/s0004/'::text) AND ((path)::text < '/shared/s00040'::text)) OR (((path)::text > '/shared/s0005/'::text) AND ((path)::text < '/shared/s00050'::text)) OR (((path)::text > '/shared/s0006/'::text) AND ((path)::text < '/shared/s00060'::text)) OR (((path)::text > '/shared/s0008/'::text) AND ((path)::text < '/shared/s00080'::text)) OR (((path)::text > '/shared/s0012/'::text) AND ((path)::text < '/shared/s00120'::text)) OR (((path)::text > '/shared/s0013/'::text) AND ((path)::text < '/shared/s00130'::text)) OR (((path)::text > '/shared/s0016/'::text) AND ((path)::text < '/shared/s00160'::text)) OR (((path)::text > '/shared/s0021/'::text) AND ((path)::text < '/shared/s00210'::text)) OR (((path)::text > '/shared/s0022/'::text) AND ((path)::text < '/shared/s00220'::text)) OR (((path)::text > '/shared/s0030/'::text) AND ((path)::text < '/shared/s00300'::text)) OR (((path)::text > '/shared/s0031/'::text) AND ((path)::text < '/shared/s00310'::text)) OR (((path)::text > '/shared/s0033/'::text) AND ((path)::text < '/shared/s00330'::text)) OR (((path)::text > '/shared/s0036/'::text) AND ((path)::text < '/shared/s00360'::text)) OR (((path)::text > '/shared/s0037/'::text) AND ((path)::text < '/shared/s00370'::text)) OR (((path)::text > '/shared/s0041/'::text) AND ((path)::text < '/shared/s00410'::text)) OR (((path)::text > '/shared/s0043/'::text) AND ((path)::text < '/shared/s00430'::text)) OR (((path)::text > '/shared/s0045/'::text) AND ((path)::text < '/shared/s00450'::text)) OR (((path)::text > '/shared/s0048/'::text) AND ((path)::text < '/shared/s00480'::text)) OR (((path)::text > '/shared/s0053/'::text) AND ((path)::text < '/shared/s00530'::text)) OR (((path)::text > '/shared/s0055/'::text) AND ((path)::text < '/shared/s00550'::text)) OR (((path)::text > '/shared/s0056/'::text) AND ((path)::text < '/shared/s00560'::text)) OR (((path)::text > '/shared/s0058/'::text) AND ((path)::text < '/shared/s00580'::text)) OR (((path)::text > '/shared/s0059/'::text) AND ((path)::text < '/shared/s00590'::text)) OR (((path)::text > '/shared/s0061/'::text) AND ((path)::text < '/shared/s00610'::text)) OR (((path)::text > '/shared/s0062/'::text) AND ((path)::text < '/shared/s00620'::text)) OR (((path)::text > '/shared/s0063/'::text) AND ((path)::text < '/shared/s00630'::text)) OR (((path)::text > '/shared/s0066/'::text) AND ((path)::text < '/shared/s00660'::text)) OR (((path)::text > '/shared/s0067/'::text) AND ((path)::text < '/shared/s00670'::text)) OR (((path)::text > '/shared/s0071/'::text) AND ((path)::text < '/shared/s00710'::text)) OR (((path)::text > '/shared/s0075/'::text) AND ((path)::text < '/shared/s00750'::text)) OR (((path)::text > '/shared/s0077/'::text) AND ((path)::text < '/shared/s00770'::text)) OR (((path)::text > '/shared/s0078/'::text) AND ((path)::text < '/shared/s00780'::text)) OR (((path)::text > '/shared/s0082/'::text) AND ((path)::text < '/shared/s00820'::text)) OR (((path)::text > '/shared/s0085/'::text) AND ((path)::text < '/shared/s00850'::text)) OR (((path)::text > '/shared/s0088/'::text) AND ((path)::text < '/shared/s00880'::text)) OR (((path)::text > '/shared/s0089/'::text) AND ((path)::text < '/shared/s00890'::text)) OR (((path)::text > '/shared/s0091/'::text) AND ((path)::text < '/shared/s00910'::text)) OR (((path)::text > '/shared/s0092/'::text) AND ((path)::text < '/shared/s00920'::text)) OR (((path)::text > '/shared/s0094/'::text) AND ((path)::text < '/shared/s00940'::text)) OR (((path)::text > '/shared/s0097/'::text) AND ((path)::text < '/shared/s00970'::text)) OR (((path)::text > '/shared/s0098/'::text) AND ((path)::text < '/shared/s00980'::text)) OR (((path)::text > '/shared/s0099/'::text) AND ((path)::text < '/shared/s00990'::text)) OR ((owner_id)::text = 'u000042'::text))
                                Heap Blocks: exact=81
                                Buffers: shared hit=581
                                ->  BitmapOr  (cost=1144.31..1144.31 rows=19234 width=0) (actual time=0.898..0.912 rows=0 loops=1)
                                      Buffers: shared hit=411
                                      ->  Bitmap Index Scan on ts_976f346d_e_lvlpath  (cost=0.00..524.18 rows=19168 width=0) (actual time=0.448..0.448 rows=20103 loops=1)
                                            Index Cond: (everyone_level >= '1'::smallint)
                                            Buffers: shared hit=102
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..194.81 rows=44 width=0) (actual time=0.089..0.089 rows=44 loops=1)
                                            Index Cond: ((path)::text = ANY ('{/home/u000042,/shared/s0001,/shared/s0004,/shared/s0005,/shared/s0006,/shared/s0008,/shared/s0012,/shared/s0013,/shared/s0016,/shared/s0021,/shared/s0022,/shared/s0030,/shared/s0031,/shared/s0033,/shared/s0036,/shared/s0037,/shared/s0041,/shared/s0043,/shared/s0045,/shared/s0048,/shared/s0053,/shared/s0055,/shared/s0056,/shared/s0058,/shared/s0059,/shared/s0061,/shared/s0062,/shared/s0063,/shared/s0066,/shared/s0067,/shared/s0071,/shared/s0075,/shared/s0077,/shared/s0078,/shared/s0082,/shared/s0085,/shared/s0088,/shared/s0089,/shared/s0091,/shared/s0092,/shared/s0094,/shared/s0097,/shared/s0098,/shared/s0099}'::text[]))
                                            Buffers: shared hit=132
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.003 rows=20 loops=1)
                                            Index Cond: (((path)::text > '/home/u000042/'::text) AND ((path)::text < '/home/u0000420'::text))
                                            Buffers: shared hit=3
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0004/'::text) AND ((path)::text < '/shared/s00040'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0005/'::text) AND ((path)::text < '/shared/s00050'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.009..0.009 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0006/'::text) AND ((path)::text < '/shared/s00060'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0008/'::text) AND ((path)::text < '/shared/s00080'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0012/'::text) AND ((path)::text < '/shared/s00120'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0013/'::text) AND ((path)::text < '/shared/s00130'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.008 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0016/'::text) AND ((path)::text < '/shared/s00160'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0021/'::text) AND ((path)::text < '/shared/s00210'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0022/'::text) AND ((path)::text < '/shared/s00220'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0030/'::text) AND ((path)::text < '/shared/s00300'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0031/'::text) AND ((path)::text < '/shared/s00310'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.009..0.009 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0033/'::text) AND ((path)::text < '/shared/s00330'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0036/'::text) AND ((path)::text < '/shared/s00360'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0037/'::text) AND ((path)::text < '/shared/s00370'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.009..0.009 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0041/'::text) AND ((path)::text < '/shared/s00410'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.009 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0043/'::text) AND ((path)::text < '/shared/s00430'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0045/'::text) AND ((path)::text < '/shared/s00450'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0048/'::text) AND ((path)::text < '/shared/s00480'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0053/'::text) AND ((path)::text < '/shared/s00530'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0055/'::text) AND ((path)::text < '/shared/s00550'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0056/'::text) AND ((path)::text < '/shared/s00560'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0058/'::text) AND ((path)::text < '/shared/s00580'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0059/'::text) AND ((path)::text < '/shared/s00590'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0061/'::text) AND ((path)::text < '/shared/s00610'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0062/'::text) AND ((path)::text < '/shared/s00620'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0063/'::text) AND ((path)::text < '/shared/s00630'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0066/'::text) AND ((path)::text < '/shared/s00660'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0067/'::text) AND ((path)::text < '/shared/s00670'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.009..0.009 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0071/'::text) AND ((path)::text < '/shared/s00710'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.008 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0075/'::text) AND ((path)::text < '/shared/s00750'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0077/'::text) AND ((path)::text < '/shared/s00770'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.009..0.009 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0078/'::text) AND ((path)::text < '/shared/s00780'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0082/'::text) AND ((path)::text < '/shared/s00820'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.008 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0085/'::text) AND ((path)::text < '/shared/s00850'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0088/'::text) AND ((path)::text < '/shared/s00880'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0089/'::text) AND ((path)::text < '/shared/s00890'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0091/'::text) AND ((path)::text < '/shared/s00910'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.009 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0092/'::text) AND ((path)::text < '/shared/s00920'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0094/'::text) AND ((path)::text < '/shared/s00940'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0097/'::text) AND ((path)::text < '/shared/s00970'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.030..0.030 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0098/'::text) AND ((path)::text < '/shared/s00980'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0099/'::text) AND ((path)::text < '/shared/s00990'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_976f346d_e_owner  (cost=0.00..4.46 rows=22 width=0) (actual time=0.005..0.006 rows=24 loops=1)
                                            Index Cond: ((owner_id)::text = 'u000042'::text)
                                            Buffers: shared hit=2
Planning:
  Buffers: shared hit=120
Planning Time: 0.794 ms
Execution Time: 96.093 ms
```

**ordinary / fenced / count**

```
Aggregate  (cost=178367.32..178367.33 rows=1 width=8) (actual time=270.378..270.382 rows=1 loops=1)
  Buffers: shared hit=4949, temp read=2039 written=2039
  ->  Hash Join  (cost=148591.31..170391.85 rows=3190190 width=0) (actual time=35.536..267.118 rows=60060 loops=1)
        Hash Cond: (c.entry_id = e.id)
        Buffers: shared hit=4949, temp read=2039 written=2039
        ->  Seq Scan on ts_976f346d_c c  (cost=0.00..10804.00 rows=660000 width=8) (actual time=0.012..57.729 rows=660000 loops=1)
              Buffers: shared hit=4204
        ->  Hash  (cost=131348.37..131348.37 rows=1050955 width=8) (actual time=34.342..34.346 rows=20124 loops=1)
              Buckets: 262144  Batches: 8  Memory Usage: 2145kB
              Buffers: shared hit=745, temp written=56
              ->  HashAggregate  (cost=112628.24..131348.37 rows=1050955 width=8) (actual time=22.803..31.841 rows=20124 loops=1)
                    Group Key: e.id
                    Planned Partitions: 16  Batches: 1  Memory Usage: 4113kB
                    Buffers: shared hit=745
                    ->  Append  (cost=528.97..56139.41 rows=1050955 width=8) (actual time=0.609..10.374 rows=20144 loops=1)
                          Buffers: shared hit=745
                          ->  Bitmap Heap Scan on ts_976f346d_e e  (cost=528.97..2672.57 rows=19168 width=8) (actual time=0.608..4.572 rows=20103 loops=1)
                                Recheck Cond: (everyone_level >= '1'::smallint)
                                Heap Blocks: exact=169
                                Buffers: shared hit=271
                                ->  Bitmap Index Scan on ts_976f346d_e_lvlpath  (cost=0.00..524.18 rows=19168 width=0) (actual time=0.469..0.469 rows=20103 loops=1)
                                      Index Cond: (everyone_level >= '1'::smallint)
                                      Buffers: shared hit=102
                          ->  Nested Loop  (cost=0.42..371.80 rows=40 width=8) (actual time=0.053..0.344 rows=1 loops=1)
                                Buffers: shared hit=176
                                ->  Function Scan on unnest ap  (cost=0.00..0.44 rows=44 width=32) (actual time=0.020..0.024 rows=44 loops=1)
                                ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_1  (cost=0.42..8.44 rows=1 width=29) (actual time=0.007..0.007 rows=0 loops=44)
                                      Index Cond: ((path)::text = (ap.value)::text)
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 1
                                      Buffers: shared hit=176
                          ->  Nested Loop  (cost=0.42..47806.27 rows=1031727 width=8) (actual time=0.033..3.033 rows=20 loops=1)
                                Buffers: shared hit=291
                                ->  Function Scan on ar  (cost=0.01..0.45 rows=44 width=64) (actual time=0.019..0.029 rows=44 loops=1)
                                ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_2  (cost=0.42..852.02 rows=23448 width=29) (actual time=0.068..0.068 rows=0 loops=44)
                                      Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 195
                                      Buffers: shared hit=291
                          ->  Index Scan using ts_976f346d_e_owner on ts_976f346d_e e_3  (cost=0.29..33.99 rows=20 width=8) (actual time=0.027..0.037 rows=20 loops=1)
                                Index Cond: ((owner_id)::text = 'u000042'::text)
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 4
                                Buffers: shared hit=7
Planning Time: 0.210 ms
Execution Time: 271.322 ms
```

**ordinary / disjoint / count**

```
Finalize Aggregate  (cost=80037.09..80037.10 rows=1 width=8) (actual time=110.674..115.175 rows=1 loops=1)
  Buffers: shared hit=5022, temp read=2062 written=2108
  ->  Gather  (cost=80036.88..80037.09 rows=2 width=8) (actual time=110.667..115.171 rows=3 loops=1)
        Workers Planned: 2
        Workers Launched: 2
        Buffers: shared hit=5022, temp read=2062 written=2108
        ->  Partial Aggregate  (cost=79036.88..79036.89 rows=1 width=8) (actual time=102.817..102.822 rows=1 loops=3)
              Buffers: shared hit=5022, temp read=2062 written=2108
              ->  Parallel Hash Join  (cost=11466.92..75713.77 rows=1329243 width=0) (actual time=82.805..100.998 rows=20020 loops=3)
                    Hash Cond: (e.id = c.entry_id)
                    Buffers: shared hit=5022, temp read=2062 written=2108
                    ->  Parallel Append  (cost=0.42..52569.66 rows=437896 width=8) (actual time=0.339..2.483 rows=6708 loops=3)
                          Buffers: shared hit=748
                          ->  Nested Loop  (cost=0.42..47806.27 rows=1031727 width=8) (actual time=0.058..1.090 rows=20 loops=1)
                                Buffers: shared hit=292
                                ->  Function Scan on ar  (cost=0.01..0.45 rows=44 width=64) (actual time=0.017..0.023 rows=44 loops=1)
                                ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e  (cost=0.42..852.02 rows=23448 width=29) (actual time=0.024..0.024 rows=0 loops=44)
                                      Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 195
                                      Buffers: shared hit=292
                          ->  Nested Loop  (cost=0.42..371.80 rows=40 width=8) (actual time=0.049..0.273 rows=1 loops=1)
                                Buffers: shared hit=177
                                ->  Function Scan on unnest ap  (cost=0.00..0.44 rows=44 width=32) (actual time=0.014..0.017 rows=44 loops=1)
                                ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_1  (cost=0.42..8.44 rows=1 width=29) (actual time=0.006..0.006 rows=0 loops=44)
                                      Index Cond: ((path)::text = (ap.value)::text)
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 1
                                      Buffers: shared hit=177
                          ->  Hash Anti Join  (cost=1.29..55.12 rows=18 width=8) (actual time=0.043..0.045 rows=0 loops=1)
                                Hash Cond: ((e_2.path)::text = (x0p.value)::text)
                                Buffers: shared hit=8
                                ->  Nested Loop Anti Join  (cost=0.30..53.90 rows=18 width=29) (actual time=0.043..0.043 rows=0 loops=1)
                                      Join Filter: (((e_2.path)::text > (x0r.lo)::text) AND ((e_2.path)::text < (x0r.hi)::text))
                                      Buffers: shared hit=8
                                      ->  Index Scan using ts_976f346d_e_owner on ts_976f346d_e e_2  (cost=0.29..33.99 rows=20 width=29) (actual time=0.018..0.023 rows=20 loops=1)
                                            Index Cond: ((owner_id)::text = 'u000042'::text)
                                            Filter: (everyone_level < '1'::smallint)
                                            Rows Removed by Filter: 4
                                            Buffers: shared hit=8
                                      ->  Function Scan on x0r  (cost=0.01..0.45 rows=44 width=64) (actual time=0.001..0.001 rows=1 loops=20)
                                ->  Hash  (cost=0.44..0.44 rows=44 width=32) (never executed)
                                      ->  Function Scan on unnest x0p  (cost=0.00..0.44 rows=44 width=32) (never executed)
                          ->  Parallel Bitmap Heap Scan on ts_976f346d_e e_3  (cost=528.97..2573.91 rows=11275 width=8) (actual time=0.751..1.419 rows=6701 loops=3)
                                Recheck Cond: (everyone_level >= '1'::smallint)
                                Heap Blocks: exact=48
                                Buffers: shared hit=271
                                ->  Bitmap Index Scan on ts_976f346d_e_lvlpath  (cost=0.00..524.18 rows=19168 width=0) (actual time=0.863..0.863 rows=20103 loops=1)
                                      Index Cond: (everyone_level >= '1'::smallint)
                                      Buffers: shared hit=102
                    ->  Parallel Hash  (cost=6954.00..6954.00 rows=275000 width=8) (actual time=65.223..65.224 rows=220000 loops=3)
                          Buckets: 262144  Batches: 8  Memory Usage: 5344kB
                          Buffers: shared hit=4204, temp written=2012
                          ->  Parallel Seq Scan on ts_976f346d_c c  (cost=0.00..6954.00 rows=275000 width=8) (actual time=0.013..27.690 rows=220000 loops=3)
                                Buffers: shared hit=4204
Planning Time: 0.261 ms
Execution Time: 115.243 ms
```

**ordinary / union / top10**

```
Limit  (cost=112628.66..153737.23 rows=10 width=12) (actual time=38.328..293.985 rows=10 loops=1)
  Buffers: shared hit=836
  ->  Nested Loop  (cost=112628.66..13114524889.12 rows=3190190 width=12) (actual time=30.797..286.449 rows=10 loops=1)
        Join Filter: (c.entry_id = e.id)
        Rows Removed by Join Filter: 1703595
        Buffers: shared hit=836
        ->  Index Scan using ts_976f346d_c_score on ts_976f346d_c c  (cost=0.42..36024.22 rows=660000 width=20) (actual time=2.590..2.901 rows=88 loops=1)
              Buffers: shared hit=91
        ->  Materialize  (cost=112628.24..140709.15 rows=1050955 width=8) (actual time=0.132..1.560 rows=19359 loops=88)
              Buffers: shared hit=745
              ->  HashAggregate  (cost=112628.24..131348.37 rows=1050955 width=8) (actual time=11.584..13.562 rows=20124 loops=1)
                    Group Key: e.id
                    Planned Partitions: 16  Batches: 1  Memory Usage: 4113kB
                    Buffers: shared hit=745
                    ->  Append  (cost=528.97..56139.41 rows=1050955 width=8) (actual time=2.551..7.635 rows=20144 loops=1)
                          Buffers: shared hit=745
                          ->  Bitmap Heap Scan on ts_976f346d_e e  (cost=528.97..2672.57 rows=19168 width=8) (actual time=2.549..4.921 rows=20103 loops=1)
                                Recheck Cond: (everyone_level >= '1'::smallint)
                                Heap Blocks: exact=169
                                Buffers: shared hit=271
                                ->  Bitmap Index Scan on ts_976f346d_e_lvlpath  (cost=0.00..524.18 rows=19168 width=0) (actual time=2.319..2.320 rows=20103 loops=1)
                                      Index Cond: (everyone_level >= '1'::smallint)
                                      Buffers: shared hit=102
                          ->  Nested Loop  (cost=0.42..371.80 rows=40 width=8) (actual time=0.049..0.148 rows=1 loops=1)
                                Buffers: shared hit=176
                                ->  Function Scan on unnest ap  (cost=0.00..0.44 rows=44 width=32) (actual time=0.030..0.033 rows=44 loops=1)
                                ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_1  (cost=0.42..8.44 rows=1 width=29) (actual time=0.002..0.002 rows=0 loops=44)
                                      Index Cond: ((path)::text = (ap.value)::text)
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 1
                                      Buffers: shared hit=176
                          ->  Nested Loop  (cost=0.42..47806.27 rows=1031727 width=8) (actual time=0.015..0.920 rows=20 loops=1)
                                Buffers: shared hit=291
                                ->  Function Scan on ar  (cost=0.01..0.45 rows=44 width=64) (actual time=0.007..0.011 rows=44 loops=1)
                                ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_2  (cost=0.42..852.02 rows=23448 width=29) (actual time=0.020..0.020 rows=0 loops=44)
                                      Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 195
                                      Buffers: shared hit=291
                          ->  Index Scan using ts_976f346d_e_owner on ts_976f346d_e e_3  (cost=0.29..33.99 rows=20 width=8) (actual time=0.010..0.014 rows=20 loops=1)
                                Index Cond: ((owner_id)::text = 'u000042'::text)
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 4
                                Buffers: shared hit=7
Planning Time: 1.513 ms
JIT:
  Functions: 38
  Options: Inlining false, Optimization false, Expressions true, Deforming true
  Timing: Generation 2.005 ms (Deform 0.586 ms), Inlining 0.000 ms, Optimization 0.334 ms, Emission 7.388 ms, Total 9.727 ms
Execution Time: 298.254 ms
```

**ordinary / unionall / top10**

```
Limit  (cost=112628.66..153737.23 rows=10 width=12) (actual time=45.038..314.322 rows=10 loops=1)
  Buffers: shared hit=836
  ->  Nested Loop  (cost=112628.66..13114524889.12 rows=3190190 width=12) (actual time=35.808..305.086 rows=10 loops=1)
        Join Filter: (c.entry_id = e.id)
        Rows Removed by Join Filter: 1703595
        Buffers: shared hit=836
        ->  Index Scan using ts_976f346d_c_score on ts_976f346d_c c  (cost=0.42..36024.22 rows=660000 width=20) (actual time=0.022..0.395 rows=88 loops=1)
              Buffers: shared hit=91
        ->  Materialize  (cost=112628.24..140709.15 rows=1050955 width=8) (actual time=0.142..1.750 rows=19359 loops=88)
              Buffers: shared hit=745
              ->  HashAggregate  (cost=112628.24..131348.37 rows=1050955 width=8) (actual time=12.448..20.684 rows=20124 loops=1)
                    Group Key: e.id
                    Planned Partitions: 16  Batches: 1  Memory Usage: 4113kB
                    Buffers: shared hit=745
                    ->  Append  (cost=528.97..56139.41 rows=1050955 width=8) (actual time=4.192..8.689 rows=20144 loops=1)
                          Buffers: shared hit=745
                          ->  Bitmap Heap Scan on ts_976f346d_e e  (cost=528.97..2672.57 rows=19168 width=8) (actual time=4.191..5.985 rows=20103 loops=1)
                                Recheck Cond: (everyone_level >= '1'::smallint)
                                Heap Blocks: exact=169
                                Buffers: shared hit=271
                                ->  Bitmap Index Scan on ts_976f346d_e_lvlpath  (cost=0.00..524.18 rows=19168 width=0) (actual time=4.155..4.155 rows=20103 loops=1)
                                      Index Cond: (everyone_level >= '1'::smallint)
                                      Buffers: shared hit=102
                          ->  Nested Loop  (cost=0.42..371.80 rows=40 width=8) (actual time=0.044..0.150 rows=1 loops=1)
                                Buffers: shared hit=176
                                ->  Function Scan on unnest ap  (cost=0.00..0.44 rows=44 width=32) (actual time=0.026..0.029 rows=44 loops=1)
                                ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_1  (cost=0.42..8.44 rows=1 width=29) (actual time=0.002..0.002 rows=0 loops=44)
                                      Index Cond: ((path)::text = (ap.value)::text)
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 1
                                      Buffers: shared hit=176
                          ->  Nested Loop  (cost=0.42..47806.27 rows=1031727 width=8) (actual time=0.016..0.921 rows=20 loops=1)
                                Buffers: shared hit=291
                                ->  Function Scan on ar  (cost=0.01..0.45 rows=44 width=64) (actual time=0.007..0.011 rows=44 loops=1)
                                ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_2  (cost=0.42..852.02 rows=23448 width=29) (actual time=0.020..0.020 rows=0 loops=44)
                                      Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 195
                                      Buffers: shared hit=291
                          ->  Index Scan using ts_976f346d_e_owner on ts_976f346d_e e_3  (cost=0.29..33.99 rows=20 width=8) (actual time=0.010..0.015 rows=20 loops=1)
                                Index Cond: ((owner_id)::text = 'u000042'::text)
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 4
                                Buffers: shared hit=7
Planning Time: 0.236 ms
JIT:
  Functions: 38
  Options: Inlining false, Optimization false, Expressions true, Deforming true
  Timing: Generation 0.608 ms (Deform 0.242 ms), Inlining 0.000 ms, Optimization 0.308 ms, Emission 8.995 ms, Total 9.911 ms
Execution Time: 315.117 ms
```

**ordinary / literal / top10**

```
Limit  (cost=0.97..82.57 rows=10 width=12) (actual time=0.124..0.507 rows=10 loops=1)
  Buffers: shared hit=443
  ->  Nested Loop  (cost=0.97..449900.69 rows=55130 width=12) (actual time=0.123..0.505 rows=10 loops=1)
        Buffers: shared hit=443
        ->  Index Scan using ts_976f346d_c_score on ts_976f346d_c c  (cost=0.42..36024.22 rows=660000 width=20) (actual time=0.009..0.102 rows=88 loops=1)
              Buffers: shared hit=91
        ->  Memoize  (cost=0.54..0.80 rows=1 width=8) (actual time=0.004..0.004 rows=0 loops=88)
              Cache Key: c.entry_id
              Cache Mode: logical
              Hits: 0  Misses: 88  Evictions: 0  Overflows: 0  Memory Usage: 7kB
              Buffers: shared hit=352
              ->  Index Scan using ts_976f346d_e_pkey on ts_976f346d_e e  (cost=0.53..0.79 rows=1 width=8) (actual time=0.003..0.003 rows=0 loops=88)
                    Index Cond: (id = c.entry_id)
                    Filter: ((everyone_level >= '1'::smallint) OR ((path)::text = ANY ('{/home/u000042,/shared/s0001,/shared/s0004,/shared/s0005,/shared/s0006,/shared/s0008,/shared/s0012,/shared/s0013,/shared/s0016,/shared/s0021,/shared/s0022,/shared/s0030,/shared/s0031,/shared/s0033,/shared/s0036,/shared/s0037,/shared/s0041,/shared/s0043,/shared/s0045,/shared/s0048,/shared/s0053,/shared/s0055,/shared/s0056,/shared/s0058,/shared/s0059,/shared/s0061,/shared/s0062,/shared/s0063,/shared/s0066,/shared/s0067,/shared/s0071,/shared/s0075,/shared/s0077,/shared/s0078,/shared/s0082,/shared/s0085,/shared/s0088,/shared/s0089,/shared/s0091,/shared/s0092,/shared/s0094,/shared/s0097,/shared/s0098,/shared/s0099}'::text[])) OR (((path)::text > '/home/u000042/'::text) AND ((path)::text < '/home/u0000420'::text)) OR (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text)) OR (((path)::text > '/shared/s0004/'::text) AND ((path)::text < '/shared/s00040'::text)) OR (((path)::text > '/shared/s0005/'::text) AND ((path)::text < '/shared/s00050'::text)) OR (((path)::text > '/shared/s0006/'::text) AND ((path)::text < '/shared/s00060'::text)) OR (((path)::text > '/shared/s0008/'::text) AND ((path)::text < '/shared/s00080'::text)) OR (((path)::text > '/shared/s0012/'::text) AND ((path)::text < '/shared/s00120'::text)) OR (((path)::text > '/shared/s0013/'::text) AND ((path)::text < '/shared/s00130'::text)) OR (((path)::text > '/shared/s0016/'::text) AND ((path)::text < '/shared/s00160'::text)) OR (((path)::text > '/shared/s0021/'::text) AND ((path)::text < '/shared/s00210'::text)) OR (((path)::text > '/shared/s0022/'::text) AND ((path)::text < '/shared/s00220'::text)) OR (((path)::text > '/shared/s0030/'::text) AND ((path)::text < '/shared/s00300'::text)) OR (((path)::text > '/shared/s0031/'::text) AND ((path)::text < '/shared/s00310'::text)) OR (((path)::text > '/shared/s0033/'::text) AND ((path)::text < '/shared/s00330'::text)) OR (((path)::text > '/shared/s0036/'::text) AND ((path)::text < '/shared/s00360'::text)) OR (((path)::text > '/shared/s0037/'::text) AND ((path)::text < '/shared/s00370'::text)) OR (((path)::text > '/shared/s0041/'::text) AND ((path)::text < '/shared/s00410'::text)) OR (((path)::text > '/shared/s0043/'::text) AND ((path)::text < '/shared/s00430'::text)) OR (((path)::text > '/shared/s0045/'::text) AND ((path)::text < '/shared/s00450'::text)) OR (((path)::text > '/shared/s0048/'::text) AND ((path)::text < '/shared/s00480'::text)) OR (((path)::text > '/shared/s0053/'::text) AND ((path)::text < '/shared/s00530'::text)) OR (((path)::text > '/shared/s0055/'::text) AND ((path)::text < '/shared/s00550'::text)) OR (((path)::text > '/shared/s0056/'::text) AND ((path)::text < '/shared/s00560'::text)) OR (((path)::text > '/shared/s0058/'::text) AND ((path)::text < '/shared/s00580'::text)) OR (((path)::text > '/shared/s0059/'::text) AND ((path)::text < '/shared/s00590'::text)) OR (((path)::text > '/shared/s0061/'::text) AND ((path)::text < '/shared/s00610'::text)) OR (((path)::text > '/shared/s0062/'::text) AND ((path)::text < '/shared/s00620'::text)) OR (((path)::text > '/shared/s0063/'::text) AND ((path)::text < '/shared/s00630'::text)) OR (((path)::text > '/shared/s0066/'::text) AND ((path)::text < '/shared/s00660'::text)) OR (((path)::text > '/shared/s0067/'::text) AND ((path)::text < '/shared/s00670'::text)) OR (((path)::text > '/shared/s0071/'::text) AND ((path)::text < '/shared/s00710'::text)) OR (((path)::text > '/shared/s0075/'::text) AND ((path)::text < '/shared/s00750'::text)) OR (((path)::text > '/shared/s0077/'::text) AND ((path)::text < '/shared/s00770'::text)) OR (((path)::text > '/shared/s0078/'::text) AND ((path)::text < '/shared/s00780'::text)) OR (((path)::text > '/shared/s0082/'::text) AND ((path)::text < '/shared/s00820'::text)) OR (((path)::text > '/shared/s0085/'::text) AND ((path)::text < '/shared/s00850'::text)) OR (((path)::text > '/shared/s0088/'::text) AND ((path)::text < '/shared/s00880'::text)) OR (((path)::text > '/shared/s0089/'::text) AND ((path)::text < '/shared/s00890'::text)) OR (((path)::text > '/shared/s0091/'::text) AND ((path)::text < '/shared/s00910'::text)) OR (((path)::text > '/shared/s0092/'::text) AND ((path)::text < '/shared/s00920'::text)) OR (((path)::text > '/shared/s0094/'::text) AND ((path)::text < '/shared/s00940'::text)) OR (((path)::text > '/shared/s0097/'::text) AND ((path)::text < '/shared/s00970'::text)) OR (((path)::text > '/shared/s0098/'::text) AND ((path)::text < '/shared/s00980'::text)) OR (((path)::text > '/shared/s0099/'::text) AND ((path)::text < '/shared/s00990'::text)) OR ((owner_id)::text = 'u000042'::text))
                    Rows Removed by Filter: 1
                    Buffers: shared hit=352
Planning:
  Buffers: shared hit=120
Planning Time: 5.693 ms
Execution Time: 0.541 ms
```

**ordinary / fenced / top10**

```
Limit  (cost=112628.66..153737.23 rows=10 width=12) (actual time=48.940..299.209 rows=10 loops=1)
  Buffers: shared hit=836
  ->  Nested Loop  (cost=112628.66..13114524889.12 rows=3190190 width=12) (actual time=48.939..299.201 rows=10 loops=1)
        Join Filter: (c.entry_id = e.id)
        Rows Removed by Join Filter: 1703595
        Buffers: shared hit=836
        ->  Index Scan using ts_976f346d_c_score on ts_976f346d_c c  (cost=0.42..36024.22 rows=660000 width=20) (actual time=0.015..1.606 rows=88 loops=1)
              Buffers: shared hit=91
        ->  Materialize  (cost=112628.24..140709.15 rows=1050955 width=8) (actual time=0.147..1.850 rows=19359 loops=88)
              Buffers: shared hit=745
              ->  HashAggregate  (cost=112628.24..131348.37 rows=1050955 width=8) (actual time=12.942..14.673 rows=20124 loops=1)
                    Group Key: e.id
                    Planned Partitions: 16  Batches: 1  Memory Usage: 4113kB
                    Buffers: shared hit=745
                    ->  Append  (cost=528.97..56139.41 rows=1050955 width=8) (actual time=0.510..7.886 rows=20144 loops=1)
                          Buffers: shared hit=745
                          ->  Bitmap Heap Scan on ts_976f346d_e e  (cost=528.97..2672.57 rows=19168 width=8) (actual time=0.509..3.432 rows=20103 loops=1)
                                Recheck Cond: (everyone_level >= '1'::smallint)
                                Heap Blocks: exact=169
                                Buffers: shared hit=271
                                ->  Bitmap Index Scan on ts_976f346d_e_lvlpath  (cost=0.00..524.18 rows=19168 width=0) (actual time=0.493..0.493 rows=20103 loops=1)
                                      Index Cond: (everyone_level >= '1'::smallint)
                                      Buffers: shared hit=102
                          ->  Nested Loop  (cost=0.42..371.80 rows=40 width=8) (actual time=0.025..0.134 rows=1 loops=1)
                                Buffers: shared hit=176
                                ->  Function Scan on unnest ap  (cost=0.00..0.44 rows=44 width=32) (actual time=0.009..0.011 rows=44 loops=1)
                                ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_1  (cost=0.42..8.44 rows=1 width=29) (actual time=0.003..0.003 rows=0 loops=44)
                                      Index Cond: ((path)::text = (ap.value)::text)
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 1
                                      Buffers: shared hit=176
                          ->  Nested Loop  (cost=0.42..47806.27 rows=1031727 width=8) (actual time=0.008..1.186 rows=20 loops=1)
                                Buffers: shared hit=291
                                ->  Function Scan on ar  (cost=0.01..0.45 rows=44 width=64) (actual time=0.004..0.009 rows=44 loops=1)
                                ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_2  (cost=0.42..852.02 rows=23448 width=29) (actual time=0.026..0.026 rows=0 loops=44)
                                      Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 195
                                      Buffers: shared hit=291
                          ->  Index Scan using ts_976f346d_e_owner on ts_976f346d_e e_3  (cost=0.29..33.99 rows=20 width=8) (actual time=0.007..0.011 rows=20 loops=1)
                                Index Cond: ((owner_id)::text = 'u000042'::text)
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 4
                                Buffers: shared hit=7
Planning Time: 0.206 ms
Execution Time: 299.342 ms
```

**ordinary / disjoint / top10**

```
Limit  (cost=529.40..41638.28 rows=10 width=12) (actual time=17.503..221.061 rows=10 loops=1)
  Buffers: shared hit=836
  ->  Nested Loop  (cost=529.40..13114489512.13 rows=3190184 width=12) (actual time=17.502..221.056 rows=10 loops=1)
        Join Filter: (c.entry_id = e.id)
        Rows Removed by Join Filter: 1759983
        Buffers: shared hit=836
        ->  Index Scan using ts_976f346d_c_score on ts_976f346d_c c  (cost=0.42..36024.22 rows=660000 width=20) (actual time=0.015..0.251 rows=88 loops=1)
              Buffers: shared hit=91
        ->  Materialize  (cost=528.97..65521.29 rows=1050953 width=8) (actual time=0.005..1.445 rows=20000 loops=88)
              Buffers: shared hit=745
              ->  Append  (cost=528.97..56160.52 rows=1050953 width=8) (actual time=0.458..4.707 rows=20124 loops=1)
                    Buffers: shared hit=745
                    ->  Bitmap Heap Scan on ts_976f346d_e e  (cost=528.97..2672.57 rows=19168 width=8) (actual time=0.458..2.215 rows=20103 loops=1)
                          Recheck Cond: (everyone_level >= '1'::smallint)
                          Heap Blocks: exact=169
                          Buffers: shared hit=271
                          ->  Bitmap Index Scan on ts_976f346d_e_lvlpath  (cost=0.00..524.18 rows=19168 width=0) (actual time=0.444..0.444 rows=20103 loops=1)
                                Index Cond: (everyone_level >= '1'::smallint)
                                Buffers: shared hit=102
                    ->  Nested Loop  (cost=0.42..371.80 rows=40 width=8) (actual time=0.019..0.098 rows=1 loops=1)
                          Buffers: shared hit=176
                          ->  Function Scan on unnest ap  (cost=0.00..0.44 rows=44 width=32) (actual time=0.010..0.013 rows=44 loops=1)
                          ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_1  (cost=0.42..8.44 rows=1 width=29) (actual time=0.002..0.002 rows=0 loops=44)
                                Index Cond: ((path)::text = (ap.value)::text)
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 1
                                Buffers: shared hit=176
                    ->  Nested Loop  (cost=0.42..47806.27 rows=1031727 width=8) (actual time=0.008..0.797 rows=20 loops=1)
                          Buffers: shared hit=291
                          ->  Function Scan on ar  (cost=0.01..0.45 rows=44 width=64) (actual time=0.005..0.009 rows=44 loops=1)
                          ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_2  (cost=0.42..852.02 rows=23448 width=29) (actual time=0.018..0.018 rows=0 loops=44)
                                Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 195
                                Buffers: shared hit=291
                    ->  Hash Anti Join  (cost=1.29..55.12 rows=18 width=8) (actual time=0.020..0.023 rows=0 loops=1)
                          Hash Cond: ((e_3.path)::text = (x0p.value)::text)
                          Buffers: shared hit=7
                          ->  Nested Loop Anti Join  (cost=0.30..53.90 rows=18 width=29) (actual time=0.020..0.021 rows=0 loops=1)
                                Join Filter: (((e_3.path)::text > (x0r.lo)::text) AND ((e_3.path)::text < (x0r.hi)::text))
                                Buffers: shared hit=7
                                ->  Index Scan using ts_976f346d_e_owner on ts_976f346d_e e_3  (cost=0.29..33.99 rows=20 width=29) (actual time=0.007..0.010 rows=20 loops=1)
                                      Index Cond: ((owner_id)::text = 'u000042'::text)
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 4
                                      Buffers: shared hit=7
                                ->  Function Scan on x0r  (cost=0.01..0.45 rows=44 width=64) (actual time=0.000..0.000 rows=1 loops=20)
                          ->  Hash  (cost=0.44..0.44 rows=44 width=32) (never executed)
                                ->  Function Scan on unnest x0p  (cost=0.00..0.44 rows=44 width=32) (never executed)
Planning Time: 0.235 ms
Execution Time: 221.151 ms
```

**two subjects / union / entries**

```
HashAggregate  (cost=62255.41..71371.88 rows=511802 width=8) (actual time=6.972..8.627 rows=20103 loops=1)
  Group Key: e.id
  Planned Partitions: 8  Batches: 1  Memory Usage: 4113kB
  Buffers: shared hit=514
  ->  Append  (cost=528.97..34746.05 rows=511802 width=8) (actual time=0.494..4.649 rows=20103 loops=1)
        Buffers: shared hit=514
        ->  Bitmap Heap Scan on ts_976f346d_e e  (cost=528.97..2672.57 rows=19168 width=8) (actual time=0.493..2.275 rows=20103 loops=1)
              Recheck Cond: (everyone_level >= '1'::smallint)
              Heap Blocks: exact=169
              Buffers: shared hit=271
              ->  Bitmap Index Scan on ts_976f346d_e_lvlpath  (cost=0.00..524.18 rows=19168 width=0) (actual time=0.453..0.453 rows=20103 loops=1)
                    Index Cond: (everyone_level >= '1'::smallint)
                    Buffers: shared hit=102
        ->  Nested Loop  (cost=0.42..177.45 rows=19 width=8) (actual time=0.056..0.056 rows=0 loops=1)
              Buffers: shared hit=84
              ->  Function Scan on unnest ap  (cost=0.00..0.21 rows=21 width=32) (actual time=0.006..0.007 rows=21 loops=1)
              ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_1  (cost=0.42..8.44 rows=1 width=29) (actual time=0.002..0.002 rows=0 loops=21)
                    Index Cond: ((path)::text = (ap.value)::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 1
                    Buffers: shared hit=84
        ->  Nested Loop  (cost=0.42..29166.72 rows=492415 width=8) (actual time=0.421..0.422 rows=0 loops=1)
              Buffers: shared hit=139
              ->  Function Scan on ar  (cost=0.01..0.21 rows=21 width=64) (actual time=0.008..0.010 rows=21 loops=1)
              ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_2  (cost=0.42..1154.40 rows=23448 width=29) (actual time=0.019..0.019 rows=0 loops=21)
                    Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 200
                    Buffers: shared hit=139
        ->  Hash Join  (cost=1.31..35.09 rows=1 width=8) (actual time=0.030..0.031 rows=0 loops=1)
              Hash Cond: ((e_3.path)::text = (o0p.value)::text)
              Buffers: shared hit=7
              ->  Index Scan using ts_976f346d_e_owner on ts_976f346d_e e_3  (cost=0.29..33.99 rows=20 width=29) (actual time=0.008..0.012 rows=20 loops=1)
                    Index Cond: ((owner_id)::text = 'u000042'::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 4
                    Buffers: shared hit=7
              ->  Hash  (cost=0.45..0.45 rows=45 width=32) (actual time=0.011..0.011 rows=45 loops=1)
                    Buckets: 1024  Batches: 1  Memory Usage: 11kB
                    ->  Function Scan on unnest o0p  (cost=0.00..0.45 rows=45 width=32) (actual time=0.003..0.006 rows=45 loops=1)
        ->  Nested Loop  (cost=0.30..50.25 rows=100 width=8) (actual time=0.141..0.141 rows=0 loops=1)
              Join Filter: (((e_4.path)::text > (o0r.lo)::text) AND ((e_4.path)::text < (o0r.hi)::text))
              Rows Removed by Join Filter: 900
              Buffers: shared hit=7
              ->  Function Scan on o0r  (cost=0.01..0.46 rows=45 width=64) (actual time=0.005..0.009 rows=45 loops=1)
              ->  Materialize  (cost=0.29..34.09 rows=20 width=29) (actual time=0.001..0.002 rows=20 loops=45)
                    Buffers: shared hit=7
                    ->  Index Scan using ts_976f346d_e_owner on ts_976f346d_e e_4  (cost=0.29..33.99 rows=20 width=29) (actual time=0.004..0.007 rows=20 loops=1)
                          Index Cond: ((owner_id)::text = 'u000042'::text)
                          Filter: (everyone_level < '1'::smallint)
                          Rows Removed by Filter: 4
                          Buffers: shared hit=7
        ->  Hash Join  (cost=1.29..35.07 rows=1 width=8) (actual time=0.025..0.025 rows=0 loops=1)
              Hash Cond: ((e_5.path)::text = (o1p.value)::text)
              Buffers: shared hit=3
              ->  Index Scan using ts_976f346d_e_owner on ts_976f346d_e e_5  (cost=0.29..33.99 rows=20 width=29) (actual time=0.006..0.008 rows=20 loops=1)
                    Index Cond: ((owner_id)::text = 'u000032'::text)
                    Filter: (everyone_level < '1'::smallint)
                    Buffers: shared hit=3
              ->  Hash  (cost=0.44..0.44 rows=44 width=32) (actual time=0.012..0.012 rows=44 loops=1)
                    Buckets: 1024  Batches: 1  Memory Usage: 10kB
                    ->  Function Scan on unnest o1p  (cost=0.00..0.44 rows=44 width=32) (actual time=0.004..0.006 rows=44 loops=1)
        ->  Nested Loop  (cost=0.30..49.89 rows=98 width=8) (actual time=0.120..0.121 rows=0 loops=1)
              Join Filter: (((e_6.path)::text > (o1r.lo)::text) AND ((e_6.path)::text < (o1r.hi)::text))
              Rows Removed by Join Filter: 880
              Buffers: shared hit=3
              ->  Function Scan on o1r  (cost=0.01..0.45 rows=44 width=64) (actual time=0.009..0.012 rows=44 loops=1)
              ->  Materialize  (cost=0.29..34.09 rows=20 width=29) (actual time=0.000..0.001 rows=20 loops=44)
                    Buffers: shared hit=3
                    ->  Index Scan using ts_976f346d_e_owner on ts_976f346d_e e_6  (cost=0.29..33.99 rows=20 width=29) (actual time=0.004..0.007 rows=20 loops=1)
                          Index Cond: ((owner_id)::text = 'u000032'::text)
                          Filter: (everyone_level < '1'::smallint)
                          Buffers: shared hit=3
Planning Time: 0.268 ms
Execution Time: 9.355 ms
```

**two subjects / unionall / entries**

```
HashAggregate  (cost=62255.41..71371.88 rows=511802 width=8) (actual time=8.965..10.682 rows=20103 loops=1)
  Group Key: e.id
  Planned Partitions: 8  Batches: 1  Memory Usage: 4113kB
  Buffers: shared hit=514
  ->  Append  (cost=528.97..34746.05 rows=511802 width=8) (actual time=0.481..5.493 rows=20103 loops=1)
        Buffers: shared hit=514
        ->  Bitmap Heap Scan on ts_976f346d_e e  (cost=528.97..2672.57 rows=19168 width=8) (actual time=0.480..2.655 rows=20103 loops=1)
              Recheck Cond: (everyone_level >= '1'::smallint)
              Heap Blocks: exact=169
              Buffers: shared hit=271
              ->  Bitmap Index Scan on ts_976f346d_e_lvlpath  (cost=0.00..524.18 rows=19168 width=0) (actual time=0.464..0.465 rows=20103 loops=1)
                    Index Cond: (everyone_level >= '1'::smallint)
                    Buffers: shared hit=102
        ->  Nested Loop  (cost=0.42..177.45 rows=19 width=8) (actual time=0.078..0.078 rows=0 loops=1)
              Buffers: shared hit=84
              ->  Function Scan on unnest ap  (cost=0.00..0.21 rows=21 width=32) (actual time=0.010..0.011 rows=21 loops=1)
              ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_1  (cost=0.42..8.44 rows=1 width=29) (actual time=0.003..0.003 rows=0 loops=21)
                    Index Cond: ((path)::text = (ap.value)::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 1
                    Buffers: shared hit=84
        ->  Nested Loop  (cost=0.42..29166.72 rows=492415 width=8) (actual time=0.444..0.445 rows=0 loops=1)
              Buffers: shared hit=139
              ->  Function Scan on ar  (cost=0.01..0.21 rows=21 width=64) (actual time=0.005..0.007 rows=21 loops=1)
              ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_2  (cost=0.42..1154.40 rows=23448 width=29) (actual time=0.020..0.020 rows=0 loops=21)
                    Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 200
                    Buffers: shared hit=139
        ->  Hash Join  (cost=1.31..35.09 rows=1 width=8) (actual time=0.038..0.040 rows=0 loops=1)
              Hash Cond: ((e_3.path)::text = (o0p.value)::text)
              Buffers: shared hit=7
              ->  Index Scan using ts_976f346d_e_owner on ts_976f346d_e e_3  (cost=0.29..33.99 rows=20 width=29) (actual time=0.012..0.016 rows=20 loops=1)
                    Index Cond: ((owner_id)::text = 'u000042'::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 4
                    Buffers: shared hit=7
              ->  Hash  (cost=0.45..0.45 rows=45 width=32) (actual time=0.012..0.012 rows=45 loops=1)
                    Buckets: 1024  Batches: 1  Memory Usage: 11kB
                    ->  Function Scan on unnest o0p  (cost=0.00..0.45 rows=45 width=32) (actual time=0.004..0.007 rows=45 loops=1)
        ->  Nested Loop  (cost=0.30..50.25 rows=100 width=8) (actual time=0.130..0.130 rows=0 loops=1)
              Join Filter: (((e_4.path)::text > (o0r.lo)::text) AND ((e_4.path)::text < (o0r.hi)::text))
              Rows Removed by Join Filter: 900
              Buffers: shared hit=7
              ->  Function Scan on o0r  (cost=0.01..0.46 rows=45 width=64) (actual time=0.005..0.009 rows=45 loops=1)
              ->  Materialize  (cost=0.29..34.09 rows=20 width=29) (actual time=0.000..0.002 rows=20 loops=45)
                    Buffers: shared hit=7
                    ->  Index Scan using ts_976f346d_e_owner on ts_976f346d_e e_4  (cost=0.29..33.99 rows=20 width=29) (actual time=0.008..0.011 rows=20 loops=1)
                          Index Cond: ((owner_id)::text = 'u000042'::text)
                          Filter: (everyone_level < '1'::smallint)
                          Rows Removed by Filter: 4
                          Buffers: shared hit=7
        ->  Hash Join  (cost=1.29..35.07 rows=1 width=8) (actual time=0.025..0.026 rows=0 loops=1)
              Hash Cond: ((e_5.path)::text = (o1p.value)::text)
              Buffers: shared hit=3
              ->  Index Scan using ts_976f346d_e_owner on ts_976f346d_e e_5  (cost=0.29..33.99 rows=20 width=29) (actual time=0.005..0.007 rows=20 loops=1)
                    Index Cond: ((owner_id)::text = 'u000032'::text)
                    Filter: (everyone_level < '1'::smallint)
                    Buffers: shared hit=3
              ->  Hash  (cost=0.44..0.44 rows=44 width=32) (actual time=0.012..0.012 rows=44 loops=1)
                    Buckets: 1024  Batches: 1  Memory Usage: 10kB
                    ->  Function Scan on unnest o1p  (cost=0.00..0.44 rows=44 width=32) (actual time=0.004..0.007 rows=44 loops=1)
        ->  Nested Loop  (cost=0.30..49.89 rows=98 width=8) (actual time=0.123..0.124 rows=0 loops=1)
              Join Filter: (((e_6.path)::text > (o1r.lo)::text) AND ((e_6.path)::text < (o1r.hi)::text))
              Rows Removed by Join Filter: 880
              Buffers: shared hit=3
              ->  Function Scan on o1r  (cost=0.01..0.45 rows=44 width=64) (actual time=0.009..0.012 rows=44 loops=1)
              ->  Materialize  (cost=0.29..34.09 rows=20 width=29) (actual time=0.000..0.001 rows=20 loops=44)
                    Buffers: shared hit=3
                    ->  Index Scan using ts_976f346d_e_owner on ts_976f346d_e e_6  (cost=0.29..33.99 rows=20 width=29) (actual time=0.005..0.008 rows=20 loops=1)
                          Index Cond: ((owner_id)::text = 'u000032'::text)
                          Filter: (everyone_level < '1'::smallint)
                          Buffers: shared hit=3
Planning Time: 0.264 ms
Execution Time: 11.410 ms
```

**two subjects / literal / entries**

```
Gather  (cost=1839.30..12252.13 rows=19187 width=8) (actual time=2.498..9.037 rows=20103 loops=1)
  Workers Planned: 1
  Workers Launched: 1
  Buffers: shared hit=424
  ->  Parallel Bitmap Heap Scan on ts_976f346d_e e  (cost=839.30..9333.43 rows=11286 width=8) (actual time=0.452..1.501 rows=10052 loops=2)
        Recheck Cond: ((everyone_level >= '1'::smallint) OR ((path)::text = ANY ('{/shared/s0001,/shared/s0004,/shared/s0005,/shared/s0008,/shared/s0012,/shared/s0016,/shared/s0021,/shared/s0022,/shared/s0030,/shared/s0031,/shared/s0045,/shared/s0048,/shared/s0053,/shared/s0055,/shared/s0056,/shared/s0058,/shared/s0059,/shared/s0071,/shared/s0075,/shared/s0082,/shared/s0085}'::text[])) OR (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text)) OR (((path)::text > '/shared/s0004/'::text) AND ((path)::text < '/shared/s00040'::text)) OR (((path)::text > '/shared/s0005/'::text) AND ((path)::text < '/shared/s00050'::text)) OR (((path)::text > '/shared/s0008/'::text) AND ((path)::text < '/shared/s00080'::text)) OR (((path)::text > '/shared/s0012/'::text) AND ((path)::text < '/shared/s00120'::text)) OR (((path)::text > '/shared/s0016/'::text) AND ((path)::text < '/shared/s00160'::text)) OR (((path)::text > '/shared/s0021/'::text) AND ((path)::text < '/shared/s00210'::text)) OR (((path)::text > '/shared/s0022/'::text) AND ((path)::text < '/shared/s00220'::text)) OR (((path)::text > '/shared/s0030/'::text) AND ((path)::text < '/shared/s00300'::text)) OR (((path)::text > '/shared/s0031/'::text) AND ((path)::text < '/shared/s00310'::text)) OR (((path)::text > '/shared/s0045/'::text) AND ((path)::text < '/shared/s00450'::text)) OR (((path)::text > '/shared/s0048/'::text) AND ((path)::text < '/shared/s00480'::text)) OR (((path)::text > '/shared/s0053/'::text) AND ((path)::text < '/shared/s00530'::text)) OR (((path)::text > '/shared/s0055/'::text) AND ((path)::text < '/shared/s00550'::text)) OR (((path)::text > '/shared/s0056/'::text) AND ((path)::text < '/shared/s00560'::text)) OR (((path)::text > '/shared/s0058/'::text) AND ((path)::text < '/shared/s00580'::text)) OR (((path)::text > '/shared/s0059/'::text) AND ((path)::text < '/shared/s00590'::text)) OR (((path)::text > '/shared/s0071/'::text) AND ((path)::text < '/shared/s00710'::text)) OR (((path)::text > '/shared/s0075/'::text) AND ((path)::text < '/shared/s00750'::text)) OR (((path)::text > '/shared/s0082/'::text) AND ((path)::text < '/shared/s00820'::text)) OR (((path)::text > '/shared/s0085/'::text) AND ((path)::text < '/shared/s00850'::text)) OR ((owner_id)::text = 'u000042'::text) OR ((owner_id)::text = 'u000032'::text))
        Filter: ((everyone_level >= '1'::smallint) OR ((path)::text = ANY ('{/shared/s0001,/shared/s0004,/shared/s0005,/shared/s0008,/shared/s0012,/shared/s0016,/shared/s0021,/shared/s0022,/shared/s0030,/shared/s0031,/shared/s0045,/shared/s0048,/shared/s0053,/shared/s0055,/shared/s0056,/shared/s0058,/shared/s0059,/shared/s0071,/shared/s0075,/shared/s0082,/shared/s0085}'::text[])) OR (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text)) OR (((path)::text > '/shared/s0004/'::text) AND ((path)::text < '/shared/s00040'::text)) OR (((path)::text > '/shared/s0005/'::text) AND ((path)::text < '/shared/s00050'::text)) OR (((path)::text > '/shared/s0008/'::text) AND ((path)::text < '/shared/s00080'::text)) OR (((path)::text > '/shared/s0012/'::text) AND ((path)::text < '/shared/s00120'::text)) OR (((path)::text > '/shared/s0016/'::text) AND ((path)::text < '/shared/s00160'::text)) OR (((path)::text > '/shared/s0021/'::text) AND ((path)::text < '/shared/s00210'::text)) OR (((path)::text > '/shared/s0022/'::text) AND ((path)::text < '/shared/s00220'::text)) OR (((path)::text > '/shared/s0030/'::text) AND ((path)::text < '/shared/s00300'::text)) OR (((path)::text > '/shared/s0031/'::text) AND ((path)::text < '/shared/s00310'::text)) OR (((path)::text > '/shared/s0045/'::text) AND ((path)::text < '/shared/s00450'::text)) OR (((path)::text > '/shared/s0048/'::text) AND ((path)::text < '/shared/s00480'::text)) OR (((path)::text > '/shared/s0053/'::text) AND ((path)::text < '/shared/s00530'::text)) OR (((path)::text > '/shared/s0055/'::text) AND ((path)::text < '/shared/s00550'::text)) OR (((path)::text > '/shared/s0056/'::text) AND ((path)::text < '/shared/s00560'::text)) OR (((path)::text > '/shared/s0058/'::text) AND ((path)::text < '/shared/s00580'::text)) OR (((path)::text > '/shared/s0059/'::text) AND ((path)::text < '/shared/s00590'::text)) OR (((path)::text > '/shared/s0071/'::text) AND ((path)::text < '/shared/s00710'::text)) OR (((path)::text > '/shared/s0075/'::text) AND ((path)::text < '/shared/s00750'::text)) OR (((path)::text > '/shared/s0082/'::text) AND ((path)::text < '/shared/s00820'::text)) OR (((path)::text > '/shared/s0085/'::text) AND ((path)::text < '/shared/s00850'::text)) OR (((owner_id)::text = 'u000042'::text) AND (((path)::text = ANY ('{/home/u000032,/shared/s0000,/shared/s0001,/shared/s0002,/shared/s0004,/shared/s0005,/shared/s0008,/shared/s0010,/shared/s0012,/shared/s0014,/shared/s0015,/shared/s0016,/shared/s0020,/shared/s0021,/shared/s0022,/shared/s0025,/shared/s0030,/shared/s0031,/shared/s0034,/shared/s0035,/shared/s0040,/shared/s0042,/shared/s0045,/shared/s0048,/shared/s0049,/shared/s0050,/shared/s0053,/shared/s0054,/shared/s0055,/shared/s0056,/shared/s0058,/shared/s0059,/shared/s0060,/shared/s0065,/shared/s0070,/shared/s0071,/shared/s0075,/shared/s0076,/shared/s0080,/shared/s0082,/shared/s0083,/shared/s0085,/shared/s0087,/shared/s0090,/shared/s0095}'::text[])) OR (((path)::text > '/home/u000032/'::text) AND ((path)::text < '/home/u0000320'::text)) OR (((path)::text > '/shared/s0000/'::text) AND ((path)::text < '/shared/s00000'::text)) OR (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text)) OR (((path)::text > '/shared/s0002/'::text) AND ((path)::text < '/shared/s00020'::text)) OR (((path)::text > '/shared/s0004/'::text) AND ((path)::text < '/shared/s00040'::text)) OR (((path)::text > '/shared/s0005/'::text) AND ((path)::text < '/shared/s00050'::text)) OR (((path)::text > '/shared/s0008/'::text) AND ((path)::text < '/shared/s00080'::text)) OR (((path)::text > '/shared/s0010/'::text) AND ((path)::text < '/shared/s00100'::text)) OR (((path)::text > '/shared/s0012/'::text) AND ((path)::text < '/shared/s00120'::text)) OR (((path)::text > '/shared/s0014/'::text) AND ((path)::text < '/shared/s00140'::text)) OR (((path)::text > '/shared/s0015/'::text) AND ((path)::text < '/shared/s00150'::text)) OR (((path)::text > '/shared/s0016/'::text) AND ((path)::text < '/shared/s00160'::text)) OR (((path)::text > '/shared/s0020/'::text) AND ((path)::text < '/shared/s00200'::text)) OR (((path)::text > '/shared/s0021/'::text) AND ((path)::text < '/shared/s00210'::text)) OR (((path)::text > '/shared/s0022/'::text) AND ((path)::text < '/shared/s00220'::text)) OR (((path)::text > '/shared/s0025/'::text) AND ((path)::text < '/shared/s00250'::text)) OR (((path)::text > '/shared/s0030/'::text) AND ((path)::text < '/shared/s00300'::text)) OR (((path)::text > '/shared/s0031/'::text) AND ((path)::text < '/shared/s00310'::text)) OR (((path)::text > '/shared/s0034/'::text) AND ((path)::text < '/shared/s00340'::text)) OR (((path)::text > '/shared/s0035/'::text) AND ((path)::text < '/shared/s00350'::text)) OR (((path)::text > '/shared/s0040/'::text) AND ((path)::text < '/shared/s00400'::text)) OR (((path)::text > '/shared/s0042/'::text) AND ((path)::text < '/shared/s00420'::text)) OR (((path)::text > '/shared/s0045/'::text) AND ((path)::text < '/shared/s00450'::text)) OR (((path)::text > '/shared/s0048/'::text) AND ((path)::text < '/shared/s00480'::text)) OR (((path)::text > '/shared/s0049/'::text) AND ((path)::text < '/shared/s00490'::text)) OR (((path)::text > '/shared/s0050/'::text) AND ((path)::text < '/shared/s00500'::text)) OR (((path)::text > '/shared/s0053/'::text) AND ((path)::text < '/shared/s00530'::text)) OR (((path)::text > '/shared/s0054/'::text) AND ((path)::text < '/shared/s00540'::text)) OR (((path)::text > '/shared/s0055/'::text) AND ((path)::text < '/shared/s00550'::text)) OR (((path)::text > '/shared/s0056/'::text) AND ((path)::text < '/shared/s00560'::text)) OR (((path)::text > '/shared/s0058/'::text) AND ((path)::text < '/shared/s00580'::text)) OR (((path)::text > '/shared/s0059/'::text) AND ((path)::text < '/shared/s00590'::text)) OR (((path)::text > '/shared/s0060/'::text) AND ((path)::text < '/shared/s00600'::text)) OR (((path)::text > '/shared/s0065/'::text) AND ((path)::text < '/shared/s00650'::text)) OR (((path)::text > '/shared/s0070/'::text) AND ((path)::text < '/shared/s00700'::text)) OR (((path)::text > '/shared/s0071/'::text) AND ((path)::text < '/shared/s00710'::text)) OR (((path)::text > '/shared/s0075/'::text) AND ((path)::text < '/shared/s00750'::text)) OR (((path)::text > '/shared/s0076/'::text) AND ((path)::text < '/shared/s00760'::text)) OR (((path)::text > '/shared/s0080/'::text) AND ((path)::text < '/shared/s00800'::text)) OR (((path)::text > '/shared/s0082/'::text) AND ((path)::text < '/shared/s00820'::text)) OR (((path)::text > '/shared/s0083/'::text) AND ((path)::text < '/shared/s00830'::text)) OR (((path)::text > '/shared/s0085/'::text) AND ((path)::text < '/shared/s00850'::text)) OR (((path)::text > '/shared/s0087/'::text) AND ((path)::text < '/shared/s00870'::text)) OR (((path)::text > '/shared/s0090/'::text) AND ((path)::text < '/shared/s00900'::text)) OR (((path)::text > '/shared/s0095/'::text) AND ((path)::text < '/shared/s00950'::text)))) OR (((owner_id)::text = 'u000032'::text) AND (((path)::text = ANY ('{/home/u000042,/shared/s0001,/shared/s0004,/shared/s0005,/shared/s0006,/shared/s0008,/shared/s0012,/shared/s0013,/shared/s0016,/shared/s0021,/shared/s0022,/shared/s0030,/shared/s0031,/shared/s0033,/shared/s0036,/shared/s0037,/shared/s0041,/shared/s0043,/shared/s0045,/shared/s0048,/shared/s0053,/shared/s0055,/shared/s0056,/shared/s0058,/shared/s0059,/shared/s0061,/shared/s0062,/shared/s0063,/shared/s0066,/shared/s0067,/shared/s0071,/shared/s0075,/shared/s0077,/shared/s0078,/shared/s0082,/shared/s0085,/shared/s0088,/shared/s0089,/shared/s0091,/shared/s0092,/shared/s0094,/shared/s0097,/shared/s0098,/shared/s0099}'::text[])) OR (((path)::text > '/home/u000042/'::text) AND ((path)::text < '/home/u0000420'::text)) OR (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text)) OR (((path)::text > '/shared/s0004/'::text) AND ((path)::text < '/shared/s00040'::text)) OR (((path)::text > '/shared/s0005/'::text) AND ((path)::text < '/shared/s00050'::text)) OR (((path)::text > '/shared/s0006/'::text) AND ((path)::text < '/shared/s00060'::text)) OR (((path)::text > '/shared/s0008/'::text) AND ((path)::text < '/shared/s00080'::text)) OR (((path)::text > '/shared/s0012/'::text) AND ((path)::text < '/shared/s00120'::text)) OR (((path)::text > '/shared/s0013/'::text) AND ((path)::text < '/shared/s00130'::text)) OR (((path)::text > '/shared/s0016/'::text) AND ((path)::text < '/shared/s00160'::text)) OR (((path)::text > '/shared/s0021/'::text) AND ((path)::text < '/shared/s00210'::text)) OR (((path)::text > '/shared/s0022/'::text) AND ((path)::text < '/shared/s00220'::text)) OR (((path)::text > '/shared/s0030/'::text) AND ((path)::text < '/shared/s00300'::text)) OR (((path)::text > '/shared/s0031/'::text) AND ((path)::text < '/shared/s00310'::text)) OR (((path)::text > '/shared/s0033/'::text) AND ((path)::text < '/shared/s00330'::text)) OR (((path)::text > '/shared/s0036/'::text) AND ((path)::text < '/shared/s00360'::text)) OR (((path)::text > '/shared/s0037/'::text) AND ((path)::text < '/shared/s00370'::text)) OR (((path)::text > '/shared/s0041/'::text) AND ((path)::text < '/shared/s00410'::text)) OR (((path)::text > '/shared/s0043/'::text) AND ((path)::text < '/shared/s00430'::text)) OR (((path)::text > '/shared/s0045/'::text) AND ((path)::text < '/shared/s00450'::text)) OR (((path)::text > '/shared/s0048/'::text) AND ((path)::text < '/shared/s00480'::text)) OR (((path)::text > '/shared/s0053/'::text) AND ((path)::text < '/shared/s00530'::text)) OR (((path)::text > '/shared/s0055/'::text) AND ((path)::text < '/shared/s00550'::text)) OR (((path)::text > '/shared/s0056/'::text) AND ((path)::text < '/shared/s00560'::text)) OR (((path)::text > '/shared/s0058/'::text) AND ((path)::text < '/shared/s00580'::text)) OR (((path)::text > '/shared/s0059/'::text) AND ((path)::text < '/shared/s00590'::text)) OR (((path)::text > '/shared/s0061/'::text) AND ((path)::text < '/shared/s00610'::text)) OR (((path)::text > '/shared/s0062/'::text) AND ((path)::text < '/shared/s00620'::text)) OR (((path)::text > '/shared/s0063/'::text) AND ((path)::text < '/shared/s00630'::text)) OR (((path)::text > '/shared/s0066/'::text) AND ((path)::text < '/shared/s00660'::text)) OR (((path)::text > '/shared/s0067/'::text) AND ((path)::text < '/shared/s00670'::text)) OR (((path)::text > '/shared/s0071/'::text) AND ((path)::text < '/shared/s00710'::text)) OR (((path)::text > '/shared/s0075/'::text) AND ((path)::text < '/shared/s00750'::text)) OR (((path)::text > '/shared/s0077/'::text) AND ((path)::text < '/shared/s00770'::text)) OR (((path)::text > '/shared/s0078/'::text) AND ((path)::text < '/shared/s00780'::text)) OR (((path)::text > '/shared/s0082/'::text) AND ((path)::text < '/shared/s00820'::text)) OR (((path)::text > '/shared/s0085/'::text) AND ((path)::text < '/shared/s00850'::text)) OR (((path)::text > '/shared/s0088/'::text) AND ((path)::text < '/shared/s00880'::text)) OR (((path)::text > '/shared/s0089/'::text) AND ((path)::text < '/shared/s00890'::text)) OR (((path)::text > '/shared/s0091/'::text) AND ((path)::text < '/shared/s00910'::text)) OR (((path)::text > '/shared/s0092/'::text) AND ((path)::text < '/shared/s00920'::text)) OR (((path)::text > '/shared/s0094/'::text) AND ((path)::text < '/shared/s00940'::text)) OR (((path)::text > '/shared/s0097/'::text) AND ((path)::text < '/shared/s00970'::text)) OR (((path)::text > '/shared/s0098/'::text) AND ((path)::text < '/shared/s00980'::text)) OR (((path)::text > '/shared/s0099/'::text) AND ((path)::text < '/shared/s00990'::text)))))
        Rows Removed by Filter: 20
        Heap Blocks: exact=171
        Buffers: shared hit=424
        ->  BitmapOr  (cost=839.03..839.03 rows=19233 width=0) (actual time=0.863..0.870 rows=0 loops=1)
              Buffers: shared hit=253
              ->  Bitmap Index Scan on ts_976f346d_e_lvlpath  (cost=0.00..524.18 rows=19168 width=0) (actual time=0.649..0.650 rows=20103 loops=1)
                    Index Cond: (everyone_level >= '1'::smallint)
                    Buffers: shared hit=102
              ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..92.98 rows=21 width=0) (actual time=0.038..0.038 rows=21 loops=1)
                    Index Cond: ((path)::text = ANY ('{/shared/s0001,/shared/s0004,/shared/s0005,/shared/s0008,/shared/s0012,/shared/s0016,/shared/s0021,/shared/s0022,/shared/s0030,/shared/s0031,/shared/s0045,/shared/s0048,/shared/s0053,/shared/s0055,/shared/s0056,/shared/s0058,/shared/s0059,/shared/s0071,/shared/s0075,/shared/s0082,/shared/s0085}'::text[]))
                    Buffers: shared hit=63
              ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0004/'::text) AND ((path)::text < '/shared/s00040'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.008 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0005/'::text) AND ((path)::text < '/shared/s00050'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0008/'::text) AND ((path)::text < '/shared/s00080'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0012/'::text) AND ((path)::text < '/shared/s00120'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0016/'::text) AND ((path)::text < '/shared/s00160'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0021/'::text) AND ((path)::text < '/shared/s00210'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.009 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0022/'::text) AND ((path)::text < '/shared/s00220'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0030/'::text) AND ((path)::text < '/shared/s00300'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0031/'::text) AND ((path)::text < '/shared/s00310'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.009 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0045/'::text) AND ((path)::text < '/shared/s00450'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0048/'::text) AND ((path)::text < '/shared/s00480'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0053/'::text) AND ((path)::text < '/shared/s00530'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0055/'::text) AND ((path)::text < '/shared/s00550'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0056/'::text) AND ((path)::text < '/shared/s00560'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0058/'::text) AND ((path)::text < '/shared/s00580'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0059/'::text) AND ((path)::text < '/shared/s00590'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.012..0.012 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0071/'::text) AND ((path)::text < '/shared/s00710'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.008 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0075/'::text) AND ((path)::text < '/shared/s00750'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0082/'::text) AND ((path)::text < '/shared/s00820'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_976f346d_e_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.009..0.009 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0085/'::text) AND ((path)::text < '/shared/s00850'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_976f346d_e_owner  (cost=0.00..4.46 rows=22 width=0) (actual time=0.005..0.005 rows=24 loops=1)
                    Index Cond: ((owner_id)::text = 'u000042'::text)
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on ts_976f346d_e_owner  (cost=0.00..4.46 rows=22 width=0) (actual time=0.002..0.002 rows=20 loops=1)
                    Index Cond: ((owner_id)::text = 'u000032'::text)
                    Buffers: shared hit=2
Planning:
  Buffers: shared hit=188
Planning Time: 2.761 ms
Execution Time: 9.832 ms
```

**two subjects / fenced / entries**

```
HashAggregate  (cost=62255.41..71371.88 rows=511802 width=8) (actual time=7.793..9.610 rows=20103 loops=1)
  Group Key: e.id
  Planned Partitions: 8  Batches: 1  Memory Usage: 4113kB
  Buffers: shared hit=514
  ->  Append  (cost=528.97..34746.05 rows=511802 width=8) (actual time=0.480..4.751 rows=20103 loops=1)
        Buffers: shared hit=514
        ->  Bitmap Heap Scan on ts_976f346d_e e  (cost=528.97..2672.57 rows=19168 width=8) (actual time=0.479..2.275 rows=20103 loops=1)
              Recheck Cond: (everyone_level >= '1'::smallint)
              Heap Blocks: exact=169
              Buffers: shared hit=271
              ->  Bitmap Index Scan on ts_976f346d_e_lvlpath  (cost=0.00..524.18 rows=19168 width=0) (actual time=0.463..0.463 rows=20103 loops=1)
                    Index Cond: (everyone_level >= '1'::smallint)
                    Buffers: shared hit=102
        ->  Nested Loop  (cost=0.42..177.45 rows=19 width=8) (actual time=0.096..0.098 rows=0 loops=1)
              Buffers: shared hit=84
              ->  Function Scan on unnest ap  (cost=0.00..0.21 rows=21 width=32) (actual time=0.009..0.010 rows=21 loops=1)
              ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_1  (cost=0.42..8.44 rows=1 width=29) (actual time=0.004..0.004 rows=0 loops=21)
                    Index Cond: ((path)::text = (ap.value)::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 1
                    Buffers: shared hit=84
        ->  Nested Loop  (cost=0.42..29166.72 rows=492415 width=8) (actual time=0.454..0.455 rows=0 loops=1)
              Buffers: shared hit=139
              ->  Function Scan on ar  (cost=0.01..0.21 rows=21 width=64) (actual time=0.013..0.015 rows=21 loops=1)
              ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_2  (cost=0.42..1154.40 rows=23448 width=29) (actual time=0.021..0.021 rows=0 loops=21)
                    Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 200
                    Buffers: shared hit=139
        ->  Hash Join  (cost=1.31..35.09 rows=1 width=8) (actual time=0.046..0.048 rows=0 loops=1)
              Hash Cond: ((e_3.path)::text = (o0p.value)::text)
              Buffers: shared hit=7
              ->  Index Scan using ts_976f346d_e_owner on ts_976f346d_e e_3  (cost=0.29..33.99 rows=20 width=29) (actual time=0.012..0.017 rows=20 loops=1)
                    Index Cond: ((owner_id)::text = 'u000042'::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 4
                    Buffers: shared hit=7
              ->  Hash  (cost=0.45..0.45 rows=45 width=32) (actual time=0.015..0.016 rows=45 loops=1)
                    Buckets: 1024  Batches: 1  Memory Usage: 11kB
                    ->  Function Scan on unnest o0p  (cost=0.00..0.45 rows=45 width=32) (actual time=0.004..0.007 rows=45 loops=1)
        ->  Nested Loop  (cost=0.30..50.25 rows=100 width=8) (actual time=0.124..0.125 rows=0 loops=1)
              Join Filter: (((e_4.path)::text > (o0r.lo)::text) AND ((e_4.path)::text < (o0r.hi)::text))
              Rows Removed by Join Filter: 900
              Buffers: shared hit=7
              ->  Function Scan on o0r  (cost=0.01..0.46 rows=45 width=64) (actual time=0.006..0.009 rows=45 loops=1)
              ->  Materialize  (cost=0.29..34.09 rows=20 width=29) (actual time=0.000..0.001 rows=20 loops=45)
                    Buffers: shared hit=7
                    ->  Index Scan using ts_976f346d_e_owner on ts_976f346d_e e_4  (cost=0.29..33.99 rows=20 width=29) (actual time=0.005..0.008 rows=20 loops=1)
                          Index Cond: ((owner_id)::text = 'u000042'::text)
                          Filter: (everyone_level < '1'::smallint)
                          Rows Removed by Filter: 4
                          Buffers: shared hit=7
        ->  Hash Join  (cost=1.29..35.07 rows=1 width=8) (actual time=0.025..0.026 rows=0 loops=1)
              Hash Cond: ((e_5.path)::text = (o1p.value)::text)
              Buffers: shared hit=3
              ->  Index Scan using ts_976f346d_e_owner on ts_976f346d_e e_5  (cost=0.29..33.99 rows=20 width=29) (actual time=0.005..0.007 rows=20 loops=1)
                    Index Cond: ((owner_id)::text = 'u000032'::text)
                    Filter: (everyone_level < '1'::smallint)
                    Buffers: shared hit=3
              ->  Hash  (cost=0.44..0.44 rows=44 width=32) (actual time=0.012..0.013 rows=44 loops=1)
                    Buckets: 1024  Batches: 1  Memory Usage: 10kB
                    ->  Function Scan on unnest o1p  (cost=0.00..0.44 rows=44 width=32) (actual time=0.004..0.007 rows=44 loops=1)
        ->  Nested Loop  (cost=0.30..49.89 rows=98 width=8) (actual time=0.124..0.125 rows=0 loops=1)
              Join Filter: (((e_6.path)::text > (o1r.lo)::text) AND ((e_6.path)::text < (o1r.hi)::text))
              Rows Removed by Join Filter: 880
              Buffers: shared hit=3
              ->  Function Scan on o1r  (cost=0.01..0.45 rows=44 width=64) (actual time=0.009..0.012 rows=44 loops=1)
              ->  Materialize  (cost=0.29..34.09 rows=20 width=29) (actual time=0.000..0.001 rows=20 loops=44)
                    Buffers: shared hit=3
                    ->  Index Scan using ts_976f346d_e_owner on ts_976f346d_e e_6  (cost=0.29..33.99 rows=20 width=29) (actual time=0.005..0.008 rows=20 loops=1)
                          Index Cond: ((owner_id)::text = 'u000032'::text)
                          Filter: (everyone_level < '1'::smallint)
                          Buffers: shared hit=3
Planning Time: 0.263 ms
Execution Time: 10.451 ms
```

**two subjects / disjoint / entries**

```
Append  (cost=528.97..34765.33 rows=511780 width=8) (actual time=0.481..5.087 rows=20103 loops=1)
  Buffers: shared hit=514
  ->  Bitmap Heap Scan on ts_976f346d_e e  (cost=528.97..2672.57 rows=19168 width=8) (actual time=0.480..2.458 rows=20103 loops=1)
        Recheck Cond: (everyone_level >= '1'::smallint)
        Heap Blocks: exact=169
        Buffers: shared hit=271
        ->  Bitmap Index Scan on ts_976f346d_e_lvlpath  (cost=0.00..524.18 rows=19168 width=0) (actual time=0.463..0.464 rows=20103 loops=1)
              Index Cond: (everyone_level >= '1'::smallint)
              Buffers: shared hit=102
  ->  Nested Loop  (cost=0.42..177.45 rows=19 width=8) (actual time=0.078..0.079 rows=0 loops=1)
        Buffers: shared hit=84
        ->  Function Scan on unnest ap  (cost=0.00..0.21 rows=21 width=32) (actual time=0.010..0.011 rows=21 loops=1)
        ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_1  (cost=0.42..8.44 rows=1 width=29) (actual time=0.003..0.003 rows=0 loops=21)
              Index Cond: ((path)::text = (ap.value)::text)
              Filter: (everyone_level < '1'::smallint)
              Rows Removed by Filter: 1
              Buffers: shared hit=84
  ->  Nested Loop  (cost=0.42..29166.72 rows=492415 width=8) (actual time=0.410..0.411 rows=0 loops=1)
        Buffers: shared hit=139
        ->  Function Scan on ar  (cost=0.01..0.21 rows=21 width=64) (actual time=0.003..0.005 rows=21 loops=1)
        ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_2  (cost=0.42..1154.40 rows=23448 width=29) (actual time=0.019..0.019 rows=0 loops=21)
              Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
              Filter: (everyone_level < '1'::smallint)
              Rows Removed by Filter: 200
              Buffers: shared hit=139
  ->  Nested Loop Anti Join  (cost=1.32..36.10 rows=1 width=8) (actual time=0.059..0.061 rows=0 loops=1)
        Join Filter: (((e_3.path)::text > (x0r.lo)::text) AND ((e_3.path)::text < (x0r.hi)::text))
        Buffers: shared hit=7
        ->  Nested Loop Anti Join  (cost=1.31..35.57 rows=1 width=29) (actual time=0.058..0.060 rows=0 loops=1)
              Join Filter: ((e_3.path)::text = (x0p.value)::text)
              Buffers: shared hit=7
              ->  Hash Join  (cost=1.31..35.09 rows=1 width=29) (actual time=0.058..0.059 rows=0 loops=1)
                    Hash Cond: ((e_3.path)::text = (o0p.value)::text)
                    Buffers: shared hit=7
                    ->  Index Scan using ts_976f346d_e_owner on ts_976f346d_e e_3  (cost=0.29..33.99 rows=20 width=29) (actual time=0.011..0.018 rows=20 loops=1)
                          Index Cond: ((owner_id)::text = 'u000042'::text)
                          Filter: (everyone_level < '1'::smallint)
                          Rows Removed by Filter: 4
                          Buffers: shared hit=7
                    ->  Hash  (cost=0.45..0.45 rows=45 width=32) (actual time=0.030..0.030 rows=45 loops=1)
                          Buckets: 1024  Batches: 1  Memory Usage: 11kB
                          ->  Function Scan on unnest o0p  (cost=0.00..0.45 rows=45 width=32) (actual time=0.019..0.022 rows=45 loops=1)
              ->  Function Scan on unnest x0p  (cost=0.00..0.21 rows=21 width=32) (never executed)
        ->  Function Scan on x0r  (cost=0.01..0.21 rows=21 width=64) (never executed)
  ->  Nested Loop  (cost=0.78..58.92 rows=89 width=8) (actual time=0.224..0.225 rows=0 loops=1)
        Join Filter: (((e_4.path)::text > (o0r.lo)::text) AND ((e_4.path)::text < (o0r.hi)::text))
        Rows Removed by Join Filter: 900
        Buffers: shared hit=7
        ->  Function Scan on o0r  (cost=0.01..0.46 rows=45 width=64) (actual time=0.008..0.011 rows=45 loops=1)
        ->  Materialize  (cost=0.78..44.34 rows=18 width=29) (actual time=0.001..0.004 rows=20 loops=45)
              Buffers: shared hit=7
              ->  Hash Anti Join  (cost=0.78..44.25 rows=18 width=29) (actual time=0.043..0.109 rows=20 loops=1)
                    Hash Cond: ((e_4.path)::text = (x0p_1.value)::text)
                    Buffers: shared hit=7
                    ->  Nested Loop Anti Join  (cost=0.30..43.54 rows=18 width=29) (actual time=0.024..0.087 rows=20 loops=1)
                          Join Filter: (((e_4.path)::text > (x0r_1.lo)::text) AND ((e_4.path)::text < (x0r_1.hi)::text))
                          Rows Removed by Join Filter: 420
                          Buffers: shared hit=7
                          ->  Index Scan using ts_976f346d_e_owner on ts_976f346d_e e_4  (cost=0.29..33.99 rows=20 width=29) (actual time=0.015..0.020 rows=20 loops=1)
                                Index Cond: ((owner_id)::text = 'u000042'::text)
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 4
                                Buffers: shared hit=7
                          ->  Function Scan on x0r_1  (cost=0.01..0.21 rows=21 width=64) (actual time=0.000..0.002 rows=21 loops=20)
                    ->  Hash  (cost=0.21..0.21 rows=21 width=32) (actual time=0.014..0.015 rows=21 loops=1)
                          Buckets: 1024  Batches: 1  Memory Usage: 9kB
                          ->  Function Scan on unnest x0p_1  (cost=0.00..0.21 rows=21 width=32) (actual time=0.009..0.011 rows=21 loops=1)
  ->  Nested Loop Anti Join  (cost=1.29..36.08 rows=1 width=8) (actual time=0.028..0.029 rows=0 loops=1)
        Join Filter: (((e_5.path)::text > (x1r.lo)::text) AND ((e_5.path)::text < (x1r.hi)::text))
        Buffers: shared hit=3
        ->  Nested Loop Anti Join  (cost=1.29..35.55 rows=1 width=29) (actual time=0.028..0.028 rows=0 loops=1)
              Join Filter: ((e_5.path)::text = (x1p.value)::text)
              Buffers: shared hit=3
              ->  Hash Join  (cost=1.29..35.07 rows=1 width=29) (actual time=0.028..0.028 rows=0 loops=1)
                    Hash Cond: ((e_5.path)::text = (o1p.value)::text)
                    Buffers: shared hit=3
                    ->  Index Scan using ts_976f346d_e_owner on ts_976f346d_e e_5  (cost=0.29..33.99 rows=20 width=29) (actual time=0.006..0.008 rows=20 loops=1)
                          Index Cond: ((owner_id)::text = 'u000032'::text)
                          Filter: (everyone_level < '1'::smallint)
                          Buffers: shared hit=3
                    ->  Hash  (cost=0.44..0.44 rows=44 width=32) (actual time=0.013..0.014 rows=44 loops=1)
                          Buckets: 1024  Batches: 1  Memory Usage: 10kB
                          ->  Function Scan on unnest o1p  (cost=0.00..0.44 rows=44 width=32) (actual time=0.003..0.006 rows=44 loops=1)
              ->  Function Scan on unnest x1p  (cost=0.00..0.21 rows=21 width=32) (never executed)
        ->  Function Scan on x1r  (cost=0.01..0.21 rows=21 width=64) (never executed)
  ->  Nested Loop  (cost=0.78..58.60 rows=87 width=8) (actual time=0.235..0.236 rows=0 loops=1)
        Join Filter: (((e_6.path)::text > (o1r.lo)::text) AND ((e_6.path)::text < (o1r.hi)::text))
        Rows Removed by Join Filter: 880
        Buffers: shared hit=3
        ->  Function Scan on o1r  (cost=0.01..0.45 rows=44 width=64) (actual time=0.005..0.009 rows=44 loops=1)
        ->  Materialize  (cost=0.78..44.34 rows=18 width=29) (actual time=0.001..0.004 rows=20 loops=44)
              Buffers: shared hit=3
              ->  Hash Anti Join  (cost=0.78..44.25 rows=18 width=29) (actual time=0.041..0.099 rows=20 loops=1)
                    Hash Cond: ((e_6.path)::text = (x1p_1.value)::text)
                    Buffers: shared hit=3
                    ->  Nested Loop Anti Join  (cost=0.30..43.54 rows=18 width=29) (actual time=0.030..0.085 rows=20 loops=1)
                          Join Filter: (((e_6.path)::text > (x1r_1.lo)::text) AND ((e_6.path)::text < (x1r_1.hi)::text))
                          Rows Removed by Join Filter: 420
                          Buffers: shared hit=3
                          ->  Index Scan using ts_976f346d_e_owner on ts_976f346d_e e_6  (cost=0.29..33.99 rows=20 width=29) (actual time=0.014..0.018 rows=20 loops=1)
                                Index Cond: ((owner_id)::text = 'u000032'::text)
                                Filter: (everyone_level < '1'::smallint)
                                Buffers: shared hit=3
                          ->  Function Scan on x1r_1  (cost=0.01..0.21 rows=21 width=64) (actual time=0.001..0.002 rows=21 loops=20)
                    ->  Hash  (cost=0.21..0.21 rows=21 width=32) (actual time=0.006..0.006 rows=21 loops=1)
                          Buckets: 1024  Batches: 1  Memory Usage: 9kB
                          ->  Function Scan on unnest x1p_1  (cost=0.00..0.21 rows=21 width=32) (actual time=0.002..0.003 rows=21 loops=1)
Planning Time: 0.431 ms
Execution Time: 5.817 ms
```

**scoped / anonymous / union / IN**

```
Index Scan using ts_976f346d_e_path on ts_976f346d_e e  (cost=0.42..8.44 rows=1 width=8) (actual time=0.016..0.044 rows=200 loops=1)
  Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
  Filter: (everyone_level = ANY ('{1,2}'::smallint[]))
  Buffers: shared hit=7
Planning Time: 0.074 ms
Execution Time: 0.055 ms
```

**scoped / anonymous / union / >=**

```
Index Scan using ts_976f346d_e_path on ts_976f346d_e e  (cost=0.42..8.44 rows=1 width=8) (actual time=0.014..0.040 rows=200 loops=1)
  Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
  Filter: (everyone_level >= '1'::smallint)
  Buffers: shared hit=7
Planning:
  Buffers: shared hit=3
Planning Time: 0.094 ms
Execution Time: 0.056 ms
```

**scoped / ordinary / union / IN**

```
Unique  (cost=35.61..35.65 rows=8 width=8) (actual time=0.156..0.194 rows=200 loops=1)
  Buffers: shared hit=28
  ->  Sort  (cost=35.61..35.63 rows=8 width=8) (actual time=0.156..0.168 rows=200 loops=1)
        Sort Key: e.id
        Sort Method: quicksort  Memory: 25kB
        Buffers: shared hit=28
        ->  Append  (cost=0.42..35.49 rows=8 width=8) (actual time=0.015..0.136 rows=200 loops=1)
              Buffers: shared hit=28
              ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e  (cost=0.42..8.44 rows=1 width=8) (actual time=0.015..0.045 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: (everyone_level = ANY ('{1,2}'::smallint[]))
                    Buffers: shared hit=7
              ->  Hash Join  (cost=8.46..9.01 rows=1 width=8) (actual time=0.030..0.031 rows=0 loops=1)
                    Hash Cond: ((ap.value)::text = (e_1.path)::text)
                    Buffers: shared hit=7
                    ->  Function Scan on unnest ap  (cost=0.00..0.44 rows=44 width=32) (actual time=0.005..0.005 rows=1 loops=1)
                    ->  Hash  (cost=8.44..8.44 rows=1 width=29) (actual time=0.021..0.021 rows=0 loops=1)
                          Buckets: 1024  Batches: 1  Memory Usage: 8kB
                          Buffers: shared hit=7
                          ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_1  (cost=0.42..8.44 rows=1 width=29) (actual time=0.021..0.021 rows=0 loops=1)
                                Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 200
                                Buffers: shared hit=7
              ->  Nested Loop  (cost=0.42..9.55 rows=5 width=8) (actual time=0.024..0.024 rows=0 loops=1)
                    Join Filter: (((e_2.path)::text > (ar.lo)::text) AND ((e_2.path)::text < (ar.hi)::text))
                    Buffers: shared hit=7
                    ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_2  (cost=0.42..8.44 rows=1 width=29) (actual time=0.024..0.024 rows=0 loops=1)
                          Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                          Filter: (everyone_level < '1'::smallint)
                          Rows Removed by Filter: 200
                          Buffers: shared hit=7
                    ->  Function Scan on ar  (cost=0.01..0.45 rows=44 width=64) (never executed)
              ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_3  (cost=0.42..8.45 rows=1 width=8) (actual time=0.020..0.020 rows=0 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: ((everyone_level < '1'::smallint) AND ((owner_id)::text = 'u000042'::text))
                    Rows Removed by Filter: 200
                    Buffers: shared hit=7
Planning Time: 0.139 ms
Execution Time: 0.231 ms
```

**scoped / ordinary / unionall / IN**

```
Unique  (cost=35.61..35.65 rows=8 width=8) (actual time=0.150..0.192 rows=200 loops=1)
  Buffers: shared hit=28
  ->  Sort  (cost=35.61..35.63 rows=8 width=8) (actual time=0.149..0.162 rows=200 loops=1)
        Sort Key: e.id
        Sort Method: quicksort  Memory: 25kB
        Buffers: shared hit=28
        ->  Append  (cost=0.42..35.49 rows=8 width=8) (actual time=0.018..0.137 rows=200 loops=1)
              Buffers: shared hit=28
              ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e  (cost=0.42..8.44 rows=1 width=8) (actual time=0.018..0.049 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: (everyone_level = ANY ('{1,2}'::smallint[]))
                    Buffers: shared hit=7
              ->  Hash Join  (cost=8.46..9.01 rows=1 width=8) (actual time=0.031..0.032 rows=0 loops=1)
                    Hash Cond: ((ap.value)::text = (e_1.path)::text)
                    Buffers: shared hit=7
                    ->  Function Scan on unnest ap  (cost=0.00..0.44 rows=44 width=32) (actual time=0.006..0.006 rows=1 loops=1)
                    ->  Hash  (cost=8.44..8.44 rows=1 width=29) (actual time=0.021..0.021 rows=0 loops=1)
                          Buckets: 1024  Batches: 1  Memory Usage: 8kB
                          Buffers: shared hit=7
                          ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_1  (cost=0.42..8.44 rows=1 width=29) (actual time=0.021..0.021 rows=0 loops=1)
                                Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 200
                                Buffers: shared hit=7
              ->  Nested Loop  (cost=0.42..9.55 rows=5 width=8) (actual time=0.020..0.020 rows=0 loops=1)
                    Join Filter: (((e_2.path)::text > (ar.lo)::text) AND ((e_2.path)::text < (ar.hi)::text))
                    Buffers: shared hit=7
                    ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_2  (cost=0.42..8.44 rows=1 width=29) (actual time=0.020..0.020 rows=0 loops=1)
                          Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                          Filter: (everyone_level < '1'::smallint)
                          Rows Removed by Filter: 200
                          Buffers: shared hit=7
                    ->  Function Scan on ar  (cost=0.01..0.45 rows=44 width=64) (never executed)
              ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_3  (cost=0.42..8.45 rows=1 width=8) (actual time=0.019..0.019 rows=0 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: ((everyone_level < '1'::smallint) AND ((owner_id)::text = 'u000042'::text))
                    Rows Removed by Filter: 200
                    Buffers: shared hit=7
Planning Time: 0.204 ms
Execution Time: 0.231 ms
```

**scoped / ordinary / literal / IN**

```
Index Scan using ts_976f346d_e_path on ts_976f346d_e e  (cost=0.53..8.78 rows=1 width=8) (actual time=0.011..0.035 rows=200 loops=1)
  Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
  Buffers: shared hit=7
Planning:
  Buffers: shared hit=104
Planning Time: 0.612 ms
Execution Time: 0.049 ms
```

**scoped / ordinary / disjoint / IN**

```
Append  (cost=0.42..37.16 rows=8 width=8) (actual time=0.015..0.137 rows=200 loops=1)
  Buffers: shared hit=28
  ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e  (cost=0.42..8.44 rows=1 width=8) (actual time=0.015..0.045 rows=200 loops=1)
        Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
        Filter: (everyone_level = ANY ('{1,2}'::smallint[]))
        Buffers: shared hit=7
  ->  Hash Join  (cost=8.46..9.01 rows=1 width=8) (actual time=0.030..0.030 rows=0 loops=1)
        Hash Cond: ((ap.value)::text = (e_1.path)::text)
        Buffers: shared hit=7
        ->  Function Scan on unnest ap  (cost=0.00..0.44 rows=44 width=32) (actual time=0.006..0.006 rows=1 loops=1)
        ->  Hash  (cost=8.44..8.44 rows=1 width=29) (actual time=0.020..0.020 rows=0 loops=1)
              Buckets: 1024  Batches: 1  Memory Usage: 8kB
              Buffers: shared hit=7
              ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_1  (cost=0.42..8.44 rows=1 width=29) (actual time=0.019..0.019 rows=0 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 200
                    Buffers: shared hit=7
  ->  Nested Loop  (cost=0.42..9.55 rows=5 width=8) (actual time=0.020..0.020 rows=0 loops=1)
        Join Filter: (((e_2.path)::text > (ar.lo)::text) AND ((e_2.path)::text < (ar.hi)::text))
        Buffers: shared hit=7
        ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_2  (cost=0.42..8.44 rows=1 width=29) (actual time=0.020..0.020 rows=0 loops=1)
              Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
              Filter: (everyone_level < '1'::smallint)
              Rows Removed by Filter: 200
              Buffers: shared hit=7
        ->  Function Scan on ar  (cost=0.01..0.45 rows=44 width=64) (never executed)
  ->  Nested Loop Anti Join  (cost=8.46..10.12 rows=1 width=8) (actual time=0.025..0.025 rows=0 loops=1)
        Join Filter: (((e_3.path)::text > (x0r.lo)::text) AND ((e_3.path)::text < (x0r.hi)::text))
        Buffers: shared hit=7
        ->  Hash Right Anti Join  (cost=8.46..9.02 rows=1 width=29) (actual time=0.024..0.025 rows=0 loops=1)
              Hash Cond: ((x0p.value)::text = (e_3.path)::text)
              Buffers: shared hit=7
              ->  Function Scan on unnest x0p  (cost=0.00..0.44 rows=44 width=32) (never executed)
              ->  Hash  (cost=8.45..8.45 rows=1 width=29) (actual time=0.021..0.022 rows=0 loops=1)
                    Buckets: 1024  Batches: 1  Memory Usage: 8kB
                    Buffers: shared hit=7
                    ->  Index Scan using ts_976f346d_e_path on ts_976f346d_e e_3  (cost=0.42..8.45 rows=1 width=29) (actual time=0.021..0.021 rows=0 loops=1)
                          Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                          Filter: ((everyone_level < '1'::smallint) AND ((owner_id)::text = 'u000042'::text))
                          Rows Removed by Filter: 200
                          Buffers: shared hit=7
        ->  Function Scan on x0r  (cost=0.01..0.45 rows=44 width=64) (never executed)
Planning Time: 0.220 ms
Execution Time: 0.198 ms
```

Total wall time 49s.
