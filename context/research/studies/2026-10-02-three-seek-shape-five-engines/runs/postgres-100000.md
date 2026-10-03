## postgres — N=100,000 users: 2,301,103 entries, 2,200,000 chunks (1/file), 114,000 grant rows, 100,101 posture rows, 100 sibling traps

Load (tables, rows, indexes, statistics): 64s.

### Indexes

| index | size |
|---|---|
| `path` | 92.6 MB |
| `owner` | 29.0 MB |
| `lvlpath` | 92.6 MB |
| (entries table) | 155.9 MB |

### Callers

| caller | subjects | pieces (arms + owner) | bind bytes | compile us | visible entries |
|---|---|---|---|---|---|
| ordinary | u000042 | 72 | 2,005 | 92 | 201,024 |
| heavy group | u000039 | 464 | 12,785 | 254 | 201,024 |
| two subjects | u000042, u000044 | 178 | 4,939 | 355 | 201,003 |
| anonymous | — | 0 | 0 | 0 | 201,003 |
| system | — | 0 | 0 | 0 | 2,301,103 |

### Statements — cold = fresh connection, warm = median of 2 (ms); recall against the Python truth

Shapes: union, unionall, literal, fenced, disjoint. A blank cell is a shape that does not apply to that caller.

| caller | statement | union: cold / warm / recall | unionall: cold / warm / recall | literal: cold / warm / recall | fenced: cold / warm / recall | disjoint: cold / warm / recall |
|---|---|---|---|---|---|---|
| ordinary | entries | 1,011 / 679 / exact | 839 / 655 / exact | 362 / 502 / exact | 623 / 566 / exact | 610 / 555 / exact |
| ordinary | scoped | 13.6 / 38.6 / exact | 10.5 / 5.8 / exact | 17.7 / 4.9 / exact | 19.1 / 6.7 / exact | 7.9 / 4.1 / exact |
| ordinary | count | 788 / 707 / exact | 798 / 667 / exact | 241 / 280 / exact | 796 / 575 / exact | 674 / 546 / exact |
| ordinary | top10 | 979 / 994 / exact | 956 / 1,015 / exact | 17.0 / 4.3 / exact | 977 / 896 / exact | 1,379 / 1,252 / exact |
| heavy group | entries | 1,387 / 846 / exact | 666 / 656 / exact | 762 / 661 / exact | 743 / 727 / exact | 756 / 591 / exact |
| heavy group | scoped | 5.6 / 3.2 / exact | 10.1 / 3.0 / exact | 12.7 / 5.9 / exact | 9.5 / 4.8 / exact | 6.5 / 3.3 / exact |
| heavy group | count | 902 / 745 / exact | 892 / 979 / exact | 458 / 326 / exact | 738 / 606 / exact | 441 / 376 / exact |
| heavy group | top10 | 915 / 872 / exact | 983 / 927 / exact | 16.0 / 6.5 / exact | 1,014 / 872 / exact | 1,214 / 1,221 / exact |
| two subjects | entries | 988 / 570 / exact | 686 / 563 / exact | 372 / 520 / exact | 655 / 559 / exact | 414 / 509 / exact |
| two subjects | scoped | 6.2 / 3.2 / exact | 6.0 / 5.0 / exact | 8.6 / 5.1 / exact | 11.0 / 3.2 / exact | 10.8 / 2.9 / exact |
| two subjects | count | 895 / 628 / exact | 705 / 602 / exact | 140 / 121 / exact | 450 / 585 / exact | 326 / 274 / exact |
| two subjects | top10 | 977 / 897 / exact | 882 / 848 / exact | 10.5 / 3.7 / exact | 550 / 548 / exact | 311 / 277 / exact |
| anonymous | entries | 588 / 473 / exact |  |  |  |  |
| anonymous | scoped | 3.7 / 1.6 / exact |  |  |  |  |
| anonymous | count | 136 / 127 / exact |  |  |  |  |
| anonymous | top10 | 3.8 / 1.5 / exact |  |  |  |  |
| system | entries | 3,532 / 3,175 / exact |  |  |  |  |
| system | scoped | 4.5 / 2.0 / exact |  |  |  |  |
| system | count | 409 / 332 / exact |  |  |  |  |
| system | top10 | 3.5 / 1.3 / exact |  |  |  |  |

### Scoped read, branch 1 spelled `everyone_level >= :r` against `everyone_level IN (...)`

| caller | shape | `>=` cold / warm | `IN` cold / warm | recall |
|---|---|---|---|---|
| anonymous | union | 3.5 / 1.7 | 3.1 / 1.3 | exact |
| ordinary | union | 4.3 / 1.6 | 4.3 / 1.9 | exact |
| ordinary | unionall | 4.3 / 1.9 | 4.1 / 1.7 | exact |
| ordinary | literal | 4.9 / 2.1 | 4.8 / 3.1 | exact |
| ordinary | disjoint | 4.5 / 2.1 | 4.1 / 1.9 | exact |

### Plans

**ordinary / union / entries**

```
HashAggregate  (cost=944301.27..1097246.34 rows=8586390 width=8) (actual time=178.862..259.846 rows=201024 loops=1)
  Group Key: e.id
  Planned Partitions: 128  Batches: 129  Memory Usage: 8209kB  Disk Usage: 8152kB
  Buffers: shared hit=3061, temp read=385 written=1396
  ->  Append  (cost=5645.12..482782.81 rows=8586390 width=8) (actual time=94.449..130.403 rows=201044 loops=1)
        Buffers: shared hit=3061
        ->  Bitmap Heap Scan on ts_1b272604_e e  (cost=5645.12..27252.44 rows=206025 width=8) (actual time=94.448..113.350 rows=201003 loops=1)
              Recheck Cond: (everyone_level >= '1'::smallint)
              Heap Blocks: exact=1677
              Buffers: shared hit=2670
              ->  Bitmap Index Scan on ts_1b272604_e_lvlpath  (cost=0.00..5593.62 rows=206025 width=0) (actual time=5.654..5.654 rows=201003 loops=1)
                    Index Cond: (everyone_level >= '1'::smallint)
                    Buffers: shared hit=993
        ->  Nested Loop  (cost=0.43..304.56 rows=33 width=8) (actual time=0.067..0.208 rows=1 loops=1)
              Buffers: shared hit=144
              ->  Function Scan on unnest ap  (cost=0.00..0.36 rows=36 width=32) (actual time=0.042..0.044 rows=36 loops=1)
              ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_1  (cost=0.43..8.45 rows=1 width=29) (actual time=0.004..0.004 rows=0 loops=36)
                    Index Cond: ((path)::text = (ap.value)::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 1
                    Buffers: shared hit=144
        ->  Nested Loop  (cost=0.43..412257.99 rows=8380312 width=8) (actual time=0.028..0.660 rows=20 loops=1)
              Buffers: shared hit=242
              ->  Function Scan on ar  (cost=0.01..0.36 rows=36 width=64) (actual time=0.017..0.021 rows=36 loops=1)
              ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_2  (cost=0.43..9123.74 rows=232786 width=29) (actual time=0.017..0.017 rows=1 loops=36)
                    Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 194
                    Buffers: shared hit=242
        ->  Index Scan using ts_1b272604_e_owner on ts_1b272604_e e_3  (cost=0.43..35.88 rows=20 width=8) (actual time=0.018..0.021 rows=20 loops=1)
              Index Cond: ((owner_id)::text = 'u000042'::text)
              Filter: (everyone_level < '1'::smallint)
              Rows Removed by Filter: 1
              Buffers: shared hit=5
Planning Time: 0.233 ms
JIT:
  Functions: 34
  Options: Inlining true, Optimization true, Expressions true, Deforming true
  Timing: Generation 0.879 ms (Deform 0.308 ms), Inlining 8.912 ms, Optimization 50.100 ms, Emission 33.617 ms, Total 93.508 ms
Execution Time: 268.461 ms
```

**ordinary / unionall / entries**

```
HashAggregate  (cost=944301.27..1097246.34 rows=8586390 width=8) (actual time=178.941..259.298 rows=201024 loops=1)
  Group Key: e.id
  Planned Partitions: 128  Batches: 129  Memory Usage: 8209kB  Disk Usage: 8152kB
  Buffers: shared hit=3061, temp read=385 written=1396
  ->  Append  (cost=5645.12..482782.81 rows=8586390 width=8) (actual time=89.187..126.418 rows=201044 loops=1)
        Buffers: shared hit=3061
        ->  Bitmap Heap Scan on ts_1b272604_e e  (cost=5645.12..27252.44 rows=206025 width=8) (actual time=89.186..108.967 rows=201003 loops=1)
              Recheck Cond: (everyone_level >= '1'::smallint)
              Heap Blocks: exact=1677
              Buffers: shared hit=2670
              ->  Bitmap Index Scan on ts_1b272604_e_lvlpath  (cost=0.00..5593.62 rows=206025 width=0) (actual time=6.574..6.575 rows=201003 loops=1)
                    Index Cond: (everyone_level >= '1'::smallint)
                    Buffers: shared hit=993
        ->  Nested Loop  (cost=0.43..304.56 rows=33 width=8) (actual time=0.077..0.234 rows=1 loops=1)
              Buffers: shared hit=144
              ->  Function Scan on unnest ap  (cost=0.00..0.36 rows=36 width=32) (actual time=0.048..0.050 rows=36 loops=1)
              ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_1  (cost=0.43..8.45 rows=1 width=29) (actual time=0.005..0.005 rows=0 loops=36)
                    Index Cond: ((path)::text = (ap.value)::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 1
                    Buffers: shared hit=144
        ->  Nested Loop  (cost=0.43..412257.99 rows=8380312 width=8) (actual time=0.032..0.689 rows=20 loops=1)
              Buffers: shared hit=242
              ->  Function Scan on ar  (cost=0.01..0.36 rows=36 width=64) (actual time=0.016..0.019 rows=36 loops=1)
              ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_2  (cost=0.43..9123.74 rows=232786 width=29) (actual time=0.018..0.018 rows=1 loops=36)
                    Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 194
                    Buffers: shared hit=242
        ->  Index Scan using ts_1b272604_e_owner on ts_1b272604_e e_3  (cost=0.43..35.88 rows=20 width=8) (actual time=0.019..0.023 rows=20 loops=1)
              Index Cond: ((owner_id)::text = 'u000042'::text)
              Filter: (everyone_level < '1'::smallint)
              Rows Removed by Filter: 1
              Buffers: shared hit=5
Planning Time: 0.240 ms
JIT:
  Functions: 34
  Options: Inlining true, Optimization true, Expressions true, Deforming true
  Timing: Generation 0.885 ms (Deform 0.330 ms), Inlining 8.287 ms, Optimization 43.709 ms, Emission 34.169 ms, Total 87.050 ms
Execution Time: 267.678 ms
```

**ordinary / literal / entries**

```
Gather  (cost=8927.15..65740.54 rows=206078 width=8) (actual time=8.226..38.713 rows=201024 loops=1)
  Workers Planned: 2
  Workers Launched: 2
  Buffers: shared hit=2925
  ->  Parallel Bitmap Heap Scan on ts_1b272604_e e  (cost=7927.15..44132.74 rows=85866 width=8) (actual time=5.071..13.980 rows=67008 loops=3)
        Recheck Cond: ((everyone_level >= '1'::smallint) OR ((path)::text = ANY ('{/home/u000042,/shared/s0007,/shared/s0035,/shared/s0038,/shared/s0055,/shared/s0079,/shared/s0103,/shared/s0133,/shared/s0144,/shared/s0173,/shared/s0333,/shared/s0380,/shared/s0387,/shared/s0400,/shared/s0445,/shared/s0459,/shared/s0495,/shared/s0522,/shared/s0540,/shared/s0546,/shared/s0547,/shared/s0587,/shared/s0673,/shared/s0675,/shared/s0694,/shared/s0697,/shared/s0721,/shared/s0741,/shared/s0774,/shared/s0793,/shared/s0805,/shared/s0840,/shared/s0848,/shared/s0854,/shared/s0901,/shared/s0973}'::text[])) OR (((path)::text > '/home/u000042/'::text) AND ((path)::text < '/home/u0000420'::text)) OR (((path)::text > '/shared/s0007/'::text) AND ((path)::text < '/shared/s00070'::text)) OR (((path)::text > '/shared/s0035/'::text) AND ((path)::text < '/shared/s00350'::text)) OR (((path)::text > '/shared/s0038/'::text) AND ((path)::text < '/shared/s00380'::text)) OR (((path)::text > '/shared/s0055/'::text) AND ((path)::text < '/shared/s00550'::text)) OR (((path)::text > '/shared/s0079/'::text) AND ((path)::text < '/shared/s00790'::text)) OR (((path)::text > '/shared/s0103/'::text) AND ((path)::text < '/shared/s01030'::text)) OR (((path)::text > '/shared/s0133/'::text) AND ((path)::text < '/shared/s01330'::text)) OR (((path)::text > '/shared/s0144/'::text) AND ((path)::text < '/shared/s01440'::text)) OR (((path)::text > '/shared/s0173/'::text) AND ((path)::text < '/shared/s01730'::text)) OR (((path)::text > '/shared/s0333/'::text) AND ((path)::text < '/shared/s03330'::text)) OR (((path)::text > '/shared/s0380/'::text) AND ((path)::text < '/shared/s03800'::text)) OR (((path)::text > '/shared/s0387/'::text) AND ((path)::text < '/shared/s03870'::text)) OR (((path)::text > '/shared/s0400/'::text) AND ((path)::text < '/shared/s04000'::text)) OR (((path)::text > '/shared/s0445/'::text) AND ((path)::text < '/shared/s04450'::text)) OR (((path)::text > '/shared/s0459/'::text) AND ((path)::text < '/shared/s04590'::text)) OR (((path)::text > '/shared/s0495/'::text) AND ((path)::text < '/shared/s04950'::text)) OR (((path)::text > '/shared/s0522/'::text) AND ((path)::text < '/shared/s05220'::text)) OR (((path)::text > '/shared/s0540/'::text) AND ((path)::text < '/shared/s05400'::text)) OR (((path)::text > '/shared/s0546/'::text) AND ((path)::text < '/shared/s05460'::text)) OR (((path)::text > '/shared/s0547/'::text) AND ((path)::text < '/shared/s05470'::text)) OR (((path)::text > '/shared/s0587/'::text) AND ((path)::text < '/shared/s05870'::text)) OR (((path)::text > '/shared/s0673/'::text) AND ((path)::text < '/shared/s06730'::text)) OR (((path)::text > '/shared/s0675/'::text) AND ((path)::text < '/shared/s06750'::text)) OR (((path)::text > '/shared/s0694/'::text) AND ((path)::text < '/shared/s06940'::text)) OR (((path)::text > '/shared/s0697/'::text) AND ((path)::text < '/shared/s06970'::text)) OR (((path)::text > '/shared/s0721/'::text) AND ((path)::text < '/shared/s07210'::text)) OR (((path)::text > '/shared/s0741/'::text) AND ((path)::text < '/shared/s07410'::text)) OR (((path)::text > '/shared/s0774/'::text) AND ((path)::text < '/shared/s07740'::text)) OR (((path)::text > '/shared/s0793/'::text) AND ((path)::text < '/shared/s07930'::text)) OR (((path)::text > '/shared/s0805/'::text) AND ((path)::text < '/shared/s08050'::text)) OR (((path)::text > '/shared/s0840/'::text) AND ((path)::text < '/shared/s08400'::text)) OR (((path)::text > '/shared/s0848/'::text) AND ((path)::text < '/shared/s08480'::text)) OR (((path)::text > '/shared/s0854/'::text) AND ((path)::text < '/shared/s08540'::text)) OR (((path)::text > '/shared/s0901/'::text) AND ((path)::text < '/shared/s09010'::text)) OR (((path)::text > '/shared/s0973/'::text) AND ((path)::text < '/shared/s09730'::text)) OR ((owner_id)::text = 'u000042'::text))
        Heap Blocks: exact=153
        Buffers: shared hit=2925
        ->  BitmapOr  (cost=7927.06..7927.06 rows=206083 width=0) (actual time=6.997..7.008 rows=0 loops=1)
              Buffers: shared hit=1247
              ->  Bitmap Index Scan on ts_1b272604_e_lvlpath  (cost=0.00..5593.62 rows=206025 width=0) (actual time=6.471..6.472 rows=201003 loops=1)
                    Index Cond: (everyone_level >= '1'::smallint)
                    Buffers: shared hit=993
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..159.75 rows=36 width=0) (actual time=0.106..0.106 rows=36 loops=1)
                    Index Cond: ((path)::text = ANY ('{/home/u000042,/shared/s0007,/shared/s0035,/shared/s0038,/shared/s0055,/shared/s0079,/shared/s0103,/shared/s0133,/shared/s0144,/shared/s0173,/shared/s0333,/shared/s0380,/shared/s0387,/shared/s0400,/shared/s0445,/shared/s0459,/shared/s0495,/shared/s0522,/shared/s0540,/shared/s0546,/shared/s0547,/shared/s0587,/shared/s0673,/shared/s0675,/shared/s0694,/shared/s0697,/shared/s0721,/shared/s0741,/shared/s0774,/shared/s0793,/shared/s0805,/shared/s0840,/shared/s0848,/shared/s0854,/shared/s0901,/shared/s0973}'::text[]))
                    Buffers: shared hit=108
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.003..0.003 rows=20 loops=1)
                    Index Cond: (((path)::text > '/home/u000042/'::text) AND ((path)::text < '/home/u0000420'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.010..0.011 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0007/'::text) AND ((path)::text < '/shared/s00070'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.009..0.009 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0035/'::text) AND ((path)::text < '/shared/s00350'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.012..0.013 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0038/'::text) AND ((path)::text < '/shared/s00380'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.009..0.009 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0055/'::text) AND ((path)::text < '/shared/s00550'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.011..0.011 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0079/'::text) AND ((path)::text < '/shared/s00790'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.009..0.010 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0103/'::text) AND ((path)::text < '/shared/s01030'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.010..0.010 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0133/'::text) AND ((path)::text < '/shared/s01330'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.009..0.010 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0144/'::text) AND ((path)::text < '/shared/s01440'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.009..0.009 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0173/'::text) AND ((path)::text < '/shared/s01730'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.010..0.010 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0333/'::text) AND ((path)::text < '/shared/s03330'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.009..0.009 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0380/'::text) AND ((path)::text < '/shared/s03800'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.010..0.010 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0387/'::text) AND ((path)::text < '/shared/s03870'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.017..0.017 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0400/'::text) AND ((path)::text < '/shared/s04000'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.010..0.010 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0445/'::text) AND ((path)::text < '/shared/s04450'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.009..0.009 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0459/'::text) AND ((path)::text < '/shared/s04590'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.014..0.014 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0495/'::text) AND ((path)::text < '/shared/s04950'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.011..0.011 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0522/'::text) AND ((path)::text < '/shared/s05220'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.011..0.011 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0540/'::text) AND ((path)::text < '/shared/s05400'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.010..0.010 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0546/'::text) AND ((path)::text < '/shared/s05460'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.013..0.013 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0547/'::text) AND ((path)::text < '/shared/s05470'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0587/'::text) AND ((path)::text < '/shared/s05870'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.009..0.009 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0673/'::text) AND ((path)::text < '/shared/s06730'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.011..0.011 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0675/'::text) AND ((path)::text < '/shared/s06750'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.009..0.009 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0694/'::text) AND ((path)::text < '/shared/s06940'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.011..0.011 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0697/'::text) AND ((path)::text < '/shared/s06970'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.012..0.012 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0721/'::text) AND ((path)::text < '/shared/s07210'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.009..0.009 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0741/'::text) AND ((path)::text < '/shared/s07410'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.010..0.010 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0774/'::text) AND ((path)::text < '/shared/s07740'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.013..0.013 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0793/'::text) AND ((path)::text < '/shared/s07930'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.013..0.013 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0805/'::text) AND ((path)::text < '/shared/s08050'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.011..0.012 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0840/'::text) AND ((path)::text < '/shared/s08400'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.013..0.013 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0848/'::text) AND ((path)::text < '/shared/s08480'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.011..0.011 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0854/'::text) AND ((path)::text < '/shared/s08540'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.010..0.010 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0901/'::text) AND ((path)::text < '/shared/s09010'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.018..0.018 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0973/'::text) AND ((path)::text < '/shared/s09730'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_owner  (cost=0.00..4.59 rows=22 width=0) (actual time=0.015..0.015 rows=21 loops=1)
                    Index Cond: ((owner_id)::text = 'u000042'::text)
                    Buffers: shared hit=3
Planning:
  Buffers: shared hit=64
Planning Time: 0.736 ms
Execution Time: 47.400 ms
```

**ordinary / fenced / entries**

```
HashAggregate  (cost=944301.27..1097246.34 rows=8586390 width=8) (actual time=84.829..155.465 rows=201024 loops=1)
  Group Key: e.id
  Planned Partitions: 128  Batches: 129  Memory Usage: 8209kB  Disk Usage: 8152kB
  Buffers: shared hit=3061, temp read=385 written=1396
  ->  Append  (cost=5645.12..482782.81 rows=8586390 width=8) (actual time=5.015..42.383 rows=201044 loops=1)
        Buffers: shared hit=3061
        ->  Bitmap Heap Scan on ts_1b272604_e e  (cost=5645.12..27252.44 rows=206025 width=8) (actual time=5.014..24.141 rows=201003 loops=1)
              Recheck Cond: (everyone_level >= '1'::smallint)
              Heap Blocks: exact=1677
              Buffers: shared hit=2670
              ->  Bitmap Index Scan on ts_1b272604_e_lvlpath  (cost=0.00..5593.62 rows=206025 width=0) (actual time=4.875..4.875 rows=201003 loops=1)
                    Index Cond: (everyone_level >= '1'::smallint)
                    Buffers: shared hit=993
        ->  Nested Loop  (cost=0.43..304.56 rows=33 width=8) (actual time=0.066..0.410 rows=1 loops=1)
              Buffers: shared hit=144
              ->  Function Scan on unnest ap  (cost=0.00..0.36 rows=36 width=32) (actual time=0.027..0.030 rows=36 loops=1)
              ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_1  (cost=0.43..8.45 rows=1 width=29) (actual time=0.010..0.010 rows=0 loops=36)
                    Index Cond: ((path)::text = (ap.value)::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 1
                    Buffers: shared hit=144
        ->  Nested Loop  (cost=0.43..412257.99 rows=8380312 width=8) (actual time=0.046..1.581 rows=20 loops=1)
              Buffers: shared hit=242
              ->  Function Scan on ar  (cost=0.01..0.36 rows=36 width=64) (actual time=0.027..0.034 rows=36 loops=1)
              ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_2  (cost=0.43..9123.74 rows=232786 width=29) (actual time=0.042..0.042 rows=1 loops=36)
                    Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 194
                    Buffers: shared hit=242
        ->  Index Scan using ts_1b272604_e_owner on ts_1b272604_e e_3  (cost=0.43..35.88 rows=20 width=8) (actual time=0.017..0.021 rows=20 loops=1)
              Index Cond: ((owner_id)::text = 'u000042'::text)
              Filter: (everyone_level < '1'::smallint)
              Rows Removed by Filter: 1
              Buffers: shared hit=5
Planning Time: 0.180 ms
Execution Time: 162.575 ms
```

**ordinary / disjoint / entries**

```
Append  (cost=5645.12..482800.14 rows=8586388 width=8) (actual time=30.760..74.450 rows=201024 loops=1)
  Buffers: shared hit=3061
  ->  Bitmap Heap Scan on ts_1b272604_e e  (cost=5645.12..27252.44 rows=206025 width=8) (actual time=30.758..55.366 rows=201003 loops=1)
        Recheck Cond: (everyone_level >= '1'::smallint)
        Heap Blocks: exact=1677
        Buffers: shared hit=2670
        ->  Bitmap Index Scan on ts_1b272604_e_lvlpath  (cost=0.00..5593.62 rows=206025 width=0) (actual time=9.965..9.965 rows=201003 loops=1)
              Index Cond: (everyone_level >= '1'::smallint)
              Buffers: shared hit=993
  ->  Nested Loop  (cost=0.43..304.56 rows=33 width=8) (actual time=0.154..0.333 rows=1 loops=1)
        Buffers: shared hit=144
        ->  Function Scan on unnest ap  (cost=0.00..0.36 rows=36 width=32) (actual time=0.088..0.090 rows=36 loops=1)
        ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_1  (cost=0.43..8.45 rows=1 width=29) (actual time=0.006..0.006 rows=0 loops=36)
              Index Cond: ((path)::text = (ap.value)::text)
              Filter: (everyone_level < '1'::smallint)
              Rows Removed by Filter: 1
              Buffers: shared hit=144
  ->  Nested Loop  (cost=0.43..412257.99 rows=8380312 width=8) (actual time=0.021..0.948 rows=20 loops=1)
        Buffers: shared hit=242
        ->  Function Scan on ar  (cost=0.01..0.36 rows=36 width=64) (actual time=0.010..0.016 rows=36 loops=1)
        ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_2  (cost=0.43..9123.74 rows=232786 width=29) (actual time=0.025..0.025 rows=1 loops=36)
              Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
              Filter: (everyone_level < '1'::smallint)
              Rows Removed by Filter: 194
              Buffers: shared hit=242
  ->  Hash Anti Join  (cost=1.25..53.22 rows=18 width=8) (actual time=0.049..0.054 rows=0 loops=1)
        Hash Cond: ((e_3.path)::text = (x0p.value)::text)
        Buffers: shared hit=5
        ->  Nested Loop Anti Join  (cost=0.43..52.18 rows=18 width=29) (actual time=0.048..0.049 rows=0 loops=1)
              Join Filter: (((e_3.path)::text > (x0r.lo)::text) AND ((e_3.path)::text < (x0r.hi)::text))
              Buffers: shared hit=5
              ->  Index Scan using ts_1b272604_e_owner on ts_1b272604_e e_3  (cost=0.43..35.88 rows=20 width=29) (actual time=0.028..0.032 rows=20 loops=1)
                    Index Cond: ((owner_id)::text = 'u000042'::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 1
                    Buffers: shared hit=5
              ->  Function Scan on x0r  (cost=0.01..0.36 rows=36 width=64) (actual time=0.001..0.001 rows=1 loops=20)
        ->  Hash  (cost=0.36..0.36 rows=36 width=32) (never executed)
              ->  Function Scan on unnest x0p  (cost=0.00..0.36 rows=36 width=32) (never executed)
Planning Time: 0.853 ms
JIT:
  Functions: 40
  Options: Inlining false, Optimization false, Expressions true, Deforming true
  Timing: Generation 2.382 ms (Deform 1.207 ms), Inlining 0.000 ms, Optimization 0.673 ms, Emission 20.033 ms, Total 23.087 ms
Execution Time: 84.765 ms
```

**ordinary / union / scoped**

```
Unique  (cost=35.32..35.36 rows=7 width=8) (actual time=0.834..0.875 rows=200 loops=1)
  Buffers: shared hit=28
  ->  Sort  (cost=35.32..35.34 rows=7 width=8) (actual time=0.834..0.847 rows=200 loops=1)
        Sort Key: e.id
        Sort Method: quicksort  Memory: 25kB
        Buffers: shared hit=28
        ->  Append  (cost=0.43..35.22 rows=7 width=8) (actual time=0.029..0.819 rows=200 loops=1)
              Buffers: shared hit=28
              ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e  (cost=0.43..8.45 rows=1 width=8) (actual time=0.028..0.068 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: (everyone_level >= '1'::smallint)
                    Buffers: shared hit=7
              ->  Hash Join  (cost=8.47..8.92 rows=1 width=8) (actual time=0.682..0.683 rows=0 loops=1)
                    Hash Cond: ((ap.value)::text = (e_1.path)::text)
                    Buffers: shared hit=7
                    ->  Function Scan on unnest ap  (cost=0.00..0.36 rows=36 width=32) (actual time=0.626..0.626 rows=1 loops=1)
                    ->  Hash  (cost=8.45..8.45 rows=1 width=29) (actual time=0.041..0.042 rows=0 loops=1)
                          Buckets: 1024  Batches: 1  Memory Usage: 8kB
                          Buffers: shared hit=7
                          ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_1  (cost=0.43..8.45 rows=1 width=29) (actual time=0.041..0.041 rows=0 loops=1)
                                Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 200
                                Buffers: shared hit=7
              ->  Nested Loop  (cost=0.43..9.36 rows=4 width=8) (actual time=0.027..0.028 rows=0 loops=1)
                    Join Filter: (((e_2.path)::text > (ar.lo)::text) AND ((e_2.path)::text < (ar.hi)::text))
                    Buffers: shared hit=7
                    ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_2  (cost=0.43..8.45 rows=1 width=29) (actual time=0.027..0.027 rows=0 loops=1)
                          Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                          Filter: (everyone_level < '1'::smallint)
                          Rows Removed by Filter: 200
                          Buffers: shared hit=7
                    ->  Function Scan on ar  (cost=0.01..0.36 rows=36 width=64) (never executed)
              ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_3  (cost=0.43..8.46 rows=1 width=8) (actual time=0.020..0.020 rows=0 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: ((everyone_level < '1'::smallint) AND ((owner_id)::text = 'u000042'::text))
                    Rows Removed by Filter: 200
                    Buffers: shared hit=7
Planning Time: 1.260 ms
Execution Time: 0.932 ms
```

**ordinary / unionall / scoped**

```
Unique  (cost=35.32..35.36 rows=7 width=8) (actual time=0.197..0.239 rows=200 loops=1)
  Buffers: shared hit=28
  ->  Sort  (cost=35.32..35.34 rows=7 width=8) (actual time=0.196..0.209 rows=200 loops=1)
        Sort Key: e.id
        Sort Method: quicksort  Memory: 25kB
        Buffers: shared hit=28
        ->  Append  (cost=0.43..35.22 rows=7 width=8) (actual time=0.027..0.176 rows=200 loops=1)
              Buffers: shared hit=28
              ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e  (cost=0.43..8.45 rows=1 width=8) (actual time=0.027..0.065 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: (everyone_level >= '1'::smallint)
                    Buffers: shared hit=7
              ->  Hash Join  (cost=8.47..8.92 rows=1 width=8) (actual time=0.044..0.045 rows=0 loops=1)
                    Hash Cond: ((ap.value)::text = (e_1.path)::text)
                    Buffers: shared hit=7
                    ->  Function Scan on unnest ap  (cost=0.00..0.36 rows=36 width=32) (actual time=0.009..0.009 rows=1 loops=1)
                    ->  Hash  (cost=8.45..8.45 rows=1 width=29) (actual time=0.030..0.030 rows=0 loops=1)
                          Buckets: 1024  Batches: 1  Memory Usage: 8kB
                          Buffers: shared hit=7
                          ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_1  (cost=0.43..8.45 rows=1 width=29) (actual time=0.030..0.030 rows=0 loops=1)
                                Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 200
                                Buffers: shared hit=7
              ->  Nested Loop  (cost=0.43..9.36 rows=4 width=8) (actual time=0.024..0.024 rows=0 loops=1)
                    Join Filter: (((e_2.path)::text > (ar.lo)::text) AND ((e_2.path)::text < (ar.hi)::text))
                    Buffers: shared hit=7
                    ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_2  (cost=0.43..8.45 rows=1 width=29) (actual time=0.023..0.023 rows=0 loops=1)
                          Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                          Filter: (everyone_level < '1'::smallint)
                          Rows Removed by Filter: 200
                          Buffers: shared hit=7
                    ->  Function Scan on ar  (cost=0.01..0.36 rows=36 width=64) (never executed)
              ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_3  (cost=0.43..8.46 rows=1 width=8) (actual time=0.023..0.023 rows=0 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: ((everyone_level < '1'::smallint) AND ((owner_id)::text = 'u000042'::text))
                    Rows Removed by Filter: 200
                    Buffers: shared hit=7
Planning Time: 0.315 ms
Execution Time: 0.279 ms
```

**ordinary / literal / scoped**

```
Index Scan using ts_1b272604_e_path on ts_1b272604_e e  (cost=0.52..8.73 rows=1 width=8) (actual time=0.018..0.076 rows=200 loops=1)
  Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
  Filter: ((everyone_level >= '1'::smallint) OR ((path)::text = ANY ('{/home/u000042,/shared/s0007,/shared/s0035,/shared/s0038,/shared/s0055,/shared/s0079,/shared/s0103,/shared/s0133,/shared/s0144,/shared/s0173,/shared/s0333,/shared/s0380,/shared/s0387,/shared/s0400,/shared/s0445,/shared/s0459,/shared/s0495,/shared/s0522,/shared/s0540,/shared/s0546,/shared/s0547,/shared/s0587,/shared/s0673,/shared/s0675,/shared/s0694,/shared/s0697,/shared/s0721,/shared/s0741,/shared/s0774,/shared/s0793,/shared/s0805,/shared/s0840,/shared/s0848,/shared/s0854,/shared/s0901,/shared/s0973}'::text[])) OR (((path)::text > '/home/u000042/'::text) AND ((path)::text < '/home/u0000420'::text)) OR (((path)::text > '/shared/s0007/'::text) AND ((path)::text < '/shared/s00070'::text)) OR (((path)::text > '/shared/s0035/'::text) AND ((path)::text < '/shared/s00350'::text)) OR (((path)::text > '/shared/s0038/'::text) AND ((path)::text < '/shared/s00380'::text)) OR (((path)::text > '/shared/s0055/'::text) AND ((path)::text < '/shared/s00550'::text)) OR (((path)::text > '/shared/s0079/'::text) AND ((path)::text < '/shared/s00790'::text)) OR (((path)::text > '/shared/s0103/'::text) AND ((path)::text < '/shared/s01030'::text)) OR (((path)::text > '/shared/s0133/'::text) AND ((path)::text < '/shared/s01330'::text)) OR (((path)::text > '/shared/s0144/'::text) AND ((path)::text < '/shared/s01440'::text)) OR (((path)::text > '/shared/s0173/'::text) AND ((path)::text < '/shared/s01730'::text)) OR (((path)::text > '/shared/s0333/'::text) AND ((path)::text < '/shared/s03330'::text)) OR (((path)::text > '/shared/s0380/'::text) AND ((path)::text < '/shared/s03800'::text)) OR (((path)::text > '/shared/s0387/'::text) AND ((path)::text < '/shared/s03870'::text)) OR (((path)::text > '/shared/s0400/'::text) AND ((path)::text < '/shared/s04000'::text)) OR (((path)::text > '/shared/s0445/'::text) AND ((path)::text < '/shared/s04450'::text)) OR (((path)::text > '/shared/s0459/'::text) AND ((path)::text < '/shared/s04590'::text)) OR (((path)::text > '/shared/s0495/'::text) AND ((path)::text < '/shared/s04950'::text)) OR (((path)::text > '/shared/s0522/'::text) AND ((path)::text < '/shared/s05220'::text)) OR (((path)::text > '/shared/s0540/'::text) AND ((path)::text < '/shared/s05400'::text)) OR (((path)::text > '/shared/s0546/'::text) AND ((path)::text < '/shared/s05460'::text)) OR (((path)::text > '/shared/s0547/'::text) AND ((path)::text < '/shared/s05470'::text)) OR (((path)::text > '/shared/s0587/'::text) AND ((path)::text < '/shared/s05870'::text)) OR (((path)::text > '/shared/s0673/'::text) AND ((path)::text < '/shared/s06730'::text)) OR (((path)::text > '/shared/s0675/'::text) AND ((path)::text < '/shared/s06750'::text)) OR (((path)::text > '/shared/s0694/'::text) AND ((path)::text < '/shared/s06940'::text)) OR (((path)::text > '/shared/s0697/'::text) AND ((path)::text < '/shared/s06970'::text)) OR (((path)::text > '/shared/s0721/'::text) AND ((path)::text < '/shared/s07210'::text)) OR (((path)::text > '/shared/s0741/'::text) AND ((path)::text < '/shared/s07410'::text)) OR (((path)::text > '/shared/s0774/'::text) AND ((path)::text < '/shared/s07740'::text)) OR (((path)::text > '/shared/s0793/'::text) AND ((path)::text < '/shared/s07930'::text)) OR (((path)::text > '/shared/s0805/'::text) AND ((path)::text < '/shared/s08050'::text)) OR (((path)::text > '/shared/s0840/'::text) AND ((path)::text < '/shared/s08400'::text)) OR (((path)::text > '/shared/s0848/'::text) AND ((path)::text < '/shared/s08480'::text)) OR (((path)::text > '/shared/s0854/'::text) AND ((path)::text < '/shared/s08540'::text)) OR (((path)::text > '/shared/s0901/'::text) AND ((path)::text < '/shared/s09010'::text)) OR (((path)::text > '/shared/s0973/'::text) AND ((path)::text < '/shared/s09730'::text)) OR ((owner_id)::text = 'u000042'::text))
  Buffers: shared hit=7
Planning:
  Buffers: shared hit=64
Planning Time: 1.349 ms
Execution Time: 0.182 ms
```

**ordinary / fenced / scoped**

```
Unique  (cost=35.32..35.36 rows=7 width=8) (actual time=0.189..0.231 rows=200 loops=1)
  Buffers: shared hit=28
  ->  Sort  (cost=35.32..35.34 rows=7 width=8) (actual time=0.188..0.202 rows=200 loops=1)
        Sort Key: e.id
        Sort Method: quicksort  Memory: 25kB
        Buffers: shared hit=28
        ->  Append  (cost=0.43..35.22 rows=7 width=8) (actual time=0.022..0.162 rows=200 loops=1)
              Buffers: shared hit=28
              ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e  (cost=0.43..8.45 rows=1 width=8) (actual time=0.021..0.055 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: (everyone_level >= '1'::smallint)
                    Buffers: shared hit=7
              ->  Hash Join  (cost=8.47..8.92 rows=1 width=8) (actual time=0.037..0.038 rows=0 loops=1)
                    Hash Cond: ((ap.value)::text = (e_1.path)::text)
                    Buffers: shared hit=7
                    ->  Function Scan on unnest ap  (cost=0.00..0.36 rows=36 width=32) (actual time=0.008..0.008 rows=1 loops=1)
                    ->  Hash  (cost=8.45..8.45 rows=1 width=29) (actual time=0.024..0.025 rows=0 loops=1)
                          Buckets: 1024  Batches: 1  Memory Usage: 8kB
                          Buffers: shared hit=7
                          ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_1  (cost=0.43..8.45 rows=1 width=29) (actual time=0.024..0.024 rows=0 loops=1)
                                Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 200
                                Buffers: shared hit=7
              ->  Nested Loop  (cost=0.43..9.36 rows=4 width=8) (actual time=0.024..0.024 rows=0 loops=1)
                    Join Filter: (((e_2.path)::text > (ar.lo)::text) AND ((e_2.path)::text < (ar.hi)::text))
                    Buffers: shared hit=7
                    ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_2  (cost=0.43..8.45 rows=1 width=29) (actual time=0.024..0.024 rows=0 loops=1)
                          Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                          Filter: (everyone_level < '1'::smallint)
                          Rows Removed by Filter: 200
                          Buffers: shared hit=7
                    ->  Function Scan on ar  (cost=0.01..0.36 rows=36 width=64) (never executed)
              ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_3  (cost=0.43..8.46 rows=1 width=8) (actual time=0.027..0.027 rows=0 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: ((everyone_level < '1'::smallint) AND ((owner_id)::text = 'u000042'::text))
                    Rows Removed by Filter: 200
                    Buffers: shared hit=7
Planning Time: 0.263 ms
Execution Time: 0.276 ms
```

**ordinary / disjoint / scoped**

```
Append  (cost=0.43..36.60 rows=7 width=8) (actual time=0.040..0.385 rows=200 loops=1)
  Buffers: shared hit=28
  ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e  (cost=0.43..8.45 rows=1 width=8) (actual time=0.039..0.108 rows=200 loops=1)
        Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
        Filter: (everyone_level >= '1'::smallint)
        Buffers: shared hit=7
  ->  Hash Join  (cost=8.47..8.92 rows=1 width=8) (actual time=0.129..0.130 rows=0 loops=1)
        Hash Cond: ((ap.value)::text = (e_1.path)::text)
        Buffers: shared hit=7
        ->  Function Scan on unnest ap  (cost=0.00..0.36 rows=36 width=32) (actual time=0.042..0.042 rows=1 loops=1)
        ->  Hash  (cost=8.45..8.45 rows=1 width=29) (actual time=0.067..0.067 rows=0 loops=1)
              Buckets: 1024  Batches: 1  Memory Usage: 8kB
              Buffers: shared hit=7
              ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_1  (cost=0.43..8.45 rows=1 width=29) (actual time=0.066..0.066 rows=0 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 200
                    Buffers: shared hit=7
  ->  Nested Loop  (cost=0.43..9.36 rows=4 width=8) (actual time=0.058..0.058 rows=0 loops=1)
        Join Filter: (((e_2.path)::text > (ar.lo)::text) AND ((e_2.path)::text < (ar.hi)::text))
        Buffers: shared hit=7
        ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_2  (cost=0.43..8.45 rows=1 width=29) (actual time=0.057..0.057 rows=0 loops=1)
              Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
              Filter: (everyone_level < '1'::smallint)
              Rows Removed by Filter: 200
              Buffers: shared hit=7
        ->  Function Scan on ar  (cost=0.01..0.36 rows=36 width=64) (never executed)
  ->  Nested Loop Anti Join  (cost=8.47..9.83 rows=1 width=8) (actual time=0.065..0.066 rows=0 loops=1)
        Join Filter: (((e_3.path)::text > (x0r.lo)::text) AND ((e_3.path)::text < (x0r.hi)::text))
        Buffers: shared hit=7
        ->  Hash Right Anti Join  (cost=8.47..8.92 rows=1 width=29) (actual time=0.065..0.065 rows=0 loops=1)
              Hash Cond: ((x0p.value)::text = (e_3.path)::text)
              Buffers: shared hit=7
              ->  Function Scan on unnest x0p  (cost=0.00..0.36 rows=36 width=32) (never executed)
              ->  Hash  (cost=8.46..8.46 rows=1 width=29) (actual time=0.057..0.058 rows=0 loops=1)
                    Buckets: 1024  Batches: 1  Memory Usage: 8kB
                    Buffers: shared hit=7
                    ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_3  (cost=0.43..8.46 rows=1 width=29) (actual time=0.057..0.057 rows=0 loops=1)
                          Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                          Filter: ((everyone_level < '1'::smallint) AND ((owner_id)::text = 'u000042'::text))
                          Rows Removed by Filter: 200
                          Buffers: shared hit=7
        ->  Function Scan on x0r  (cost=0.01..0.36 rows=36 width=64) (never executed)
Planning Time: 0.691 ms
Execution Time: 0.495 ms
```

**ordinary / union / count**

```
Finalize Aggregate  (cost=1314350.51..1314350.52 rows=1 width=8) (actual time=905.173..913.883 rows=1 loops=1)
  Buffers: shared hit=12608 read=10660, temp read=10741 written=13774
  ->  Gather  (cost=1314350.29..1314350.50 rows=2 width=8) (actual time=905.157..913.869 rows=3 loops=1)
        Workers Planned: 2
        Workers Launched: 2
        Buffers: shared hit=12608 read=10660, temp read=10741 written=13774
        ->  Partial Aggregate  (cost=1313350.29..1313350.30 rows=1 width=8) (actual time=869.370..869.380 rows=1 loops=3)
              Buffers: shared hit=12608 read=10660, temp read=10741 written=13774
              ->  Hash Join  (cost=1238117.22..1304406.14 rows=3577662 width=0) (actual time=626.912..865.705 rows=66673 loops=3)
                    Hash Cond: (c.entry_id = e.id)
                    Buffers: shared hit=12608 read=10660, temp read=10741 written=13774
                    ->  Parallel Seq Scan on ts_1b272604_c c  (cost=0.00..23179.67 rows=916667 width=8) (actual time=184.972..300.774 rows=733333 loops=3)
                          Buffers: shared hit=3353 read=10660
                    ->  Hash  (cost=1097246.34..1097246.34 rows=8586390 width=8) (actual time=274.483..274.491 rows=201024 loops=3)
                          Buckets: 262144  Batches: 64  Memory Usage: 2174kB
                          Buffers: shared hit=9189, temp read=1155 written=6087
                          ->  HashAggregate  (cost=944301.27..1097246.34 rows=8586390 width=8) (actual time=147.235..243.280 rows=201024 loops=3)
                                Group Key: e.id
                                Planned Partitions: 128  Batches: 129  Memory Usage: 8209kB  Disk Usage: 8152kB
                                Buffers: shared hit=9189, temp read=1155 written=4188
                                Worker 0:  Batches: 129  Memory Usage: 8209kB  Disk Usage: 8152kB
                                Worker 1:  Batches: 129  Memory Usage: 8209kB  Disk Usage: 8152kB
                                ->  Append  (cost=5645.12..482782.81 rows=8586390 width=8) (actual time=7.359..64.032 rows=201044 loops=3)
                                      Buffers: shared hit=9189
                                      ->  Bitmap Heap Scan on ts_1b272604_e e  (cost=5645.12..27252.44 rows=206025 width=8) (actual time=7.357..39.553 rows=201003 loops=3)
                                            Recheck Cond: (everyone_level >= '1'::smallint)
                                            Heap Blocks: exact=1677
                                            Buffers: shared hit=8012
                                            ->  Bitmap Index Scan on ts_1b272604_e_lvlpath  (cost=0.00..5593.62 rows=206025 width=0) (actual time=7.155..7.155 rows=201003 loops=3)
                                                  Index Cond: (everyone_level >= '1'::smallint)
                                                  Buffers: shared hit=2981
                                      ->  Nested Loop  (cost=0.43..304.56 rows=33 width=8) (actual time=0.089..0.276 rows=1 loops=3)
                                            Buffers: shared hit=434
                                            ->  Function Scan on unnest ap  (cost=0.00..0.36 rows=36 width=32) (actual time=0.049..0.051 rows=36 loops=3)
                                            ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_1  (cost=0.43..8.45 rows=1 width=29) (actual time=0.006..0.006 rows=0 loops=108)
                                                  Index Cond: ((path)::text = (ap.value)::text)
                                                  Filter: (everyone_level < '1'::smallint)
                                                  Rows Removed by Filter: 1
                                                  Buffers: shared hit=434
                                      ->  Nested Loop  (cost=0.43..412257.99 rows=8380312 width=8) (actual time=0.035..0.764 rows=20 loops=3)
                                            Buffers: shared hit=726
                                            ->  Function Scan on ar  (cost=0.01..0.36 rows=36 width=64) (actual time=0.019..0.024 rows=36 loops=3)
                                            ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_2  (cost=0.43..9123.74 rows=232786 width=29) (actual time=0.020..0.020 rows=1 loops=108)
                                                  Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                                                  Filter: (everyone_level < '1'::smallint)
                                                  Rows Removed by Filter: 194
                                                  Buffers: shared hit=726
                                      ->  Index Scan using ts_1b272604_e_owner on ts_1b272604_e e_3  (cost=0.43..35.88 rows=20 width=8) (actual time=0.033..0.036 rows=20 loops=3)
                                            Index Cond: ((owner_id)::text = 'u000042'::text)
                                            Filter: (everyone_level < '1'::smallint)
                                            Rows Removed by Filter: 1
                                            Buffers: shared hit=17
Planning Time: 0.399 ms
JIT:
  Functions: 131
  Options: Inlining true, Optimization true, Expressions true, Deforming true
  Timing: Generation 4.784 ms (Deform 1.271 ms), Inlining 193.316 ms, Optimization 223.934 ms, Emission 157.007 ms, Total 579.041 ms
Execution Time: 917.487 ms
```

**ordinary / unionall / count**

```
Finalize Aggregate  (cost=1314350.51..1314350.52 rows=1 width=8) (actual time=696.347..696.441 rows=1 loops=1)
  Buffers: shared hit=12992 read=10276, temp read=10730 written=13763
  ->  Gather  (cost=1314350.29..1314350.50 rows=2 width=8) (actual time=696.326..696.424 rows=3 loops=1)
        Workers Planned: 2
        Workers Launched: 2
        Buffers: shared hit=12992 read=10276, temp read=10730 written=13763
        ->  Partial Aggregate  (cost=1313350.29..1313350.30 rows=1 width=8) (actual time=661.862..661.870 rows=1 loops=3)
              Buffers: shared hit=12992 read=10276, temp read=10730 written=13763
              ->  Hash Join  (cost=1238117.22..1304406.14 rows=3577662 width=0) (actual time=493.139..658.762 rows=66673 loops=3)
                    Hash Cond: (c.entry_id = e.id)
                    Buffers: shared hit=12992 read=10276, temp read=10730 written=13763
                    ->  Parallel Seq Scan on ts_1b272604_c c  (cost=0.00..23179.67 rows=916667 width=8) (actual time=140.580..213.394 rows=733333 loops=3)
                          Buffers: shared hit=3737 read=10276
                    ->  Hash  (cost=1097246.34..1097246.34 rows=8586390 width=8) (actual time=266.304..266.311 rows=201024 loops=3)
                          Buckets: 262144  Batches: 64  Memory Usage: 2174kB
                          Buffers: shared hit=9189, temp read=1155 written=6087
                          ->  HashAggregate  (cost=944301.27..1097246.34 rows=8586390 width=8) (actual time=107.833..224.456 rows=201024 loops=3)
                                Group Key: e.id
                                Planned Partitions: 128  Batches: 129  Memory Usage: 8209kB  Disk Usage: 8152kB
                                Buffers: shared hit=9189, temp read=1155 written=4188
                                Worker 0:  Batches: 129  Memory Usage: 8209kB  Disk Usage: 8152kB
                                Worker 1:  Batches: 129  Memory Usage: 8209kB  Disk Usage: 8152kB
                                ->  Append  (cost=5645.12..482782.81 rows=8586390 width=8) (actual time=6.907..45.695 rows=201044 loops=3)
                                      Buffers: shared hit=9189
                                      ->  Bitmap Heap Scan on ts_1b272604_e e  (cost=5645.12..27252.44 rows=206025 width=8) (actual time=6.905..27.597 rows=201003 loops=3)
                                            Recheck Cond: (everyone_level >= '1'::smallint)
                                            Heap Blocks: exact=1677
                                            Buffers: shared hit=8012
                                            ->  Bitmap Index Scan on ts_1b272604_e_lvlpath  (cost=0.00..5593.62 rows=206025 width=0) (actual time=6.719..6.719 rows=201003 loops=3)
                                                  Index Cond: (everyone_level >= '1'::smallint)
                                                  Buffers: shared hit=2981
                                      ->  Nested Loop  (cost=0.43..304.56 rows=33 width=8) (actual time=0.084..0.270 rows=1 loops=3)
                                            Buffers: shared hit=434
                                            ->  Function Scan on unnest ap  (cost=0.00..0.36 rows=36 width=32) (actual time=0.053..0.055 rows=36 loops=3)
                                            ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_1  (cost=0.43..8.45 rows=1 width=29) (actual time=0.006..0.006 rows=0 loops=108)
                                                  Index Cond: ((path)::text = (ap.value)::text)
                                                  Filter: (everyone_level < '1'::smallint)
                                                  Rows Removed by Filter: 1
                                                  Buffers: shared hit=434
                                      ->  Nested Loop  (cost=0.43..412257.99 rows=8380312 width=8) (actual time=0.024..0.711 rows=20 loops=3)
                                            Buffers: shared hit=726
                                            ->  Function Scan on ar  (cost=0.01..0.36 rows=36 width=64) (actual time=0.012..0.016 rows=36 loops=3)
                                            ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_2  (cost=0.43..9123.74 rows=232786 width=29) (actual time=0.019..0.019 rows=1 loops=108)
                                                  Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                                                  Filter: (everyone_level < '1'::smallint)
                                                  Rows Removed by Filter: 194
                                                  Buffers: shared hit=726
                                      ->  Index Scan using ts_1b272604_e_owner on ts_1b272604_e e_3  (cost=0.43..35.88 rows=20 width=8) (actual time=0.028..0.031 rows=20 loops=3)
                                            Index Cond: ((owner_id)::text = 'u000042'::text)
                                            Filter: (everyone_level < '1'::smallint)
                                            Rows Removed by Filter: 1
                                            Buffers: shared hit=17
Planning Time: 0.277 ms
JIT:
  Functions: 131
  Options: Inlining true, Optimization true, Expressions true, Deforming true
  Timing: Generation 3.333 ms (Deform 1.002 ms), Inlining 145.683 ms, Optimization 170.983 ms, Emission 119.004 ms, Total 439.003 ms
Execution Time: 699.372 ms
```

**ordinary / literal / count**

```
Finalize Aggregate  (cost=71997.43..71997.44 rows=1 width=8) (actual time=389.330..393.259 rows=1 loops=1)
  Buffers: shared hit=7116 read=9892
  ->  Gather  (cost=71997.21..71997.42 rows=2 width=8) (actual time=388.189..393.251 rows=3 loops=1)
        Workers Planned: 2
        Workers Launched: 2
        Buffers: shared hit=7116 read=9892
        ->  Partial Aggregate  (cost=70997.21..70997.22 rows=1 width=8) (actual time=384.127..384.139 rows=1 loops=3)
              Buffers: shared hit=7116 read=9892
              ->  Parallel Hash Join  (cost=45206.06..70791.98 rows=82093 width=0) (actual time=253.703..380.627 rows=66673 loops=3)
                    Hash Cond: (c.entry_id = e.id)
                    Buffers: shared hit=7116 read=9892
                    ->  Parallel Seq Scan on ts_1b272604_c c  (cost=0.00..23179.67 rows=916667 width=8) (actual time=0.053..87.700 rows=733333 loops=3)
                          Buffers: shared hit=4121 read=9892
                    ->  Parallel Hash  (cost=44132.74..44132.74 rows=85866 width=8) (actual time=45.781..45.791 rows=67008 loops=3)
                          Buckets: 262144  Batches: 1  Memory Usage: 9984kB
                          Buffers: shared hit=2925
                          ->  Parallel Bitmap Heap Scan on ts_1b272604_e e  (cost=7927.15..44132.74 rows=85866 width=8) (actual time=10.315..19.699 rows=67008 loops=3)
                                Recheck Cond: ((everyone_level >= '1'::smallint) OR ((path)::text = ANY ('{/home/u000042,/shared/s0007,/shared/s0035,/shared/s0038,/shared/s0055,/shared/s0079,/shared/s0103,/shared/s0133,/shared/s0144,/shared/s0173,/shared/s0333,/shared/s0380,/shared/s0387,/shared/s0400,/shared/s0445,/shared/s0459,/shared/s0495,/shared/s0522,/shared/s0540,/shared/s0546,/shared/s0547,/shared/s0587,/shared/s0673,/shared/s0675,/shared/s0694,/shared/s0697,/shared/s0721,/shared/s0741,/shared/s0774,/shared/s0793,/shared/s0805,/shared/s0840,/shared/s0848,/shared/s0854,/shared/s0901,/shared/s0973}'::text[])) OR (((path)::text > '/home/u000042/'::text) AND ((path)::text < '/home/u0000420'::text)) OR (((path)::text > '/shared/s0007/'::text) AND ((path)::text < '/shared/s00070'::text)) OR (((path)::text > '/shared/s0035/'::text) AND ((path)::text < '/shared/s00350'::text)) OR (((path)::text > '/shared/s0038/'::text) AND ((path)::text < '/shared/s00380'::text)) OR (((path)::text > '/shared/s0055/'::text) AND ((path)::text < '/shared/s00550'::text)) OR (((path)::text > '/shared/s0079/'::text) AND ((path)::text < '/shared/s00790'::text)) OR (((path)::text > '/shared/s0103/'::text) AND ((path)::text < '/shared/s01030'::text)) OR (((path)::text > '/shared/s0133/'::text) AND ((path)::text < '/shared/s01330'::text)) OR (((path)::text > '/shared/s0144/'::text) AND ((path)::text < '/shared/s01440'::text)) OR (((path)::text > '/shared/s0173/'::text) AND ((path)::text < '/shared/s01730'::text)) OR (((path)::text > '/shared/s0333/'::text) AND ((path)::text < '/shared/s03330'::text)) OR (((path)::text > '/shared/s0380/'::text) AND ((path)::text < '/shared/s03800'::text)) OR (((path)::text > '/shared/s0387/'::text) AND ((path)::text < '/shared/s03870'::text)) OR (((path)::text > '/shared/s0400/'::text) AND ((path)::text < '/shared/s04000'::text)) OR (((path)::text > '/shared/s0445/'::text) AND ((path)::text < '/shared/s04450'::text)) OR (((path)::text > '/shared/s0459/'::text) AND ((path)::text < '/shared/s04590'::text)) OR (((path)::text > '/shared/s0495/'::text) AND ((path)::text < '/shared/s04950'::text)) OR (((path)::text > '/shared/s0522/'::text) AND ((path)::text < '/shared/s05220'::text)) OR (((path)::text > '/shared/s0540/'::text) AND ((path)::text < '/shared/s05400'::text)) OR (((path)::text > '/shared/s0546/'::text) AND ((path)::text < '/shared/s05460'::text)) OR (((path)::text > '/shared/s0547/'::text) AND ((path)::text < '/shared/s05470'::text)) OR (((path)::text > '/shared/s0587/'::text) AND ((path)::text < '/shared/s05870'::text)) OR (((path)::text > '/shared/s0673/'::text) AND ((path)::text < '/shared/s06730'::text)) OR (((path)::text > '/shared/s0675/'::text) AND ((path)::text < '/shared/s06750'::text)) OR (((path)::text > '/shared/s0694/'::text) AND ((path)::text < '/shared/s06940'::text)) OR (((path)::text > '/shared/s0697/'::text) AND ((path)::text < '/shared/s06970'::text)) OR (((path)::text > '/shared/s0721/'::text) AND ((path)::text < '/shared/s07210'::text)) OR (((path)::text > '/shared/s0741/'::text) AND ((path)::text < '/shared/s07410'::text)) OR (((path)::text > '/shared/s0774/'::text) AND ((path)::text < '/shared/s07740'::text)) OR (((path)::text > '/shared/s0793/'::text) AND ((path)::text < '/shared/s07930'::text)) OR (((path)::text > '/shared/s0805/'::text) AND ((path)::text < '/shared/s08050'::text)) OR (((path)::text > '/shared/s0840/'::text) AND ((path)::text < '/shared/s08400'::text)) OR (((path)::text > '/shared/s0848/'::text) AND ((path)::text < '/shared/s08480'::text)) OR (((path)::text > '/shared/s0854/'::text) AND ((path)::text < '/shared/s08540'::text)) OR (((path)::text > '/shared/s0901/'::text) AND ((path)::text < '/shared/s09010'::text)) OR (((path)::text > '/shared/s0973/'::text) AND ((path)::text < '/shared/s09730'::text)) OR ((owner_id)::text = 'u000042'::text))
                                Heap Blocks: exact=715
                                Buffers: shared hit=2925
                                ->  BitmapOr  (cost=7927.06..7927.06 rows=206083 width=0) (actual time=7.917..7.932 rows=0 loops=1)
                                      Buffers: shared hit=1247
                                      ->  Bitmap Index Scan on ts_1b272604_e_lvlpath  (cost=0.00..5593.62 rows=206025 width=0) (actual time=6.553..6.553 rows=201003 loops=1)
                                            Index Cond: (everyone_level >= '1'::smallint)
                                            Buffers: shared hit=993
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..159.75 rows=36 width=0) (actual time=0.129..0.130 rows=36 loops=1)
                                            Index Cond: ((path)::text = ANY ('{/home/u000042,/shared/s0007,/shared/s0035,/shared/s0038,/shared/s0055,/shared/s0079,/shared/s0103,/shared/s0133,/shared/s0144,/shared/s0173,/shared/s0333,/shared/s0380,/shared/s0387,/shared/s0400,/shared/s0445,/shared/s0459,/shared/s0495,/shared/s0522,/shared/s0540,/shared/s0546,/shared/s0547,/shared/s0587,/shared/s0673,/shared/s0675,/shared/s0694,/shared/s0697,/shared/s0721,/shared/s0741,/shared/s0774,/shared/s0793,/shared/s0805,/shared/s0840,/shared/s0848,/shared/s0854,/shared/s0901,/shared/s0973}'::text[]))
                                            Buffers: shared hit=108
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.003..0.003 rows=20 loops=1)
                                            Index Cond: (((path)::text > '/home/u000042/'::text) AND ((path)::text < '/home/u0000420'::text))
                                            Buffers: shared hit=3
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.010..0.010 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0007/'::text) AND ((path)::text < '/shared/s00070'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.009..0.009 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0035/'::text) AND ((path)::text < '/shared/s00350'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.009..0.009 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0038/'::text) AND ((path)::text < '/shared/s00380'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.009..0.009 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0055/'::text) AND ((path)::text < '/shared/s00550'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.011..0.011 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0079/'::text) AND ((path)::text < '/shared/s00790'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.016..0.016 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0103/'::text) AND ((path)::text < '/shared/s01030'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.010..0.010 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0133/'::text) AND ((path)::text < '/shared/s01330'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.009..0.009 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0144/'::text) AND ((path)::text < '/shared/s01440'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.010..0.010 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0173/'::text) AND ((path)::text < '/shared/s01730'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.009..0.009 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0333/'::text) AND ((path)::text < '/shared/s03330'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.009..0.009 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0380/'::text) AND ((path)::text < '/shared/s03800'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.010..0.011 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0387/'::text) AND ((path)::text < '/shared/s03870'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.019..0.019 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0400/'::text) AND ((path)::text < '/shared/s04000'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.010..0.011 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0445/'::text) AND ((path)::text < '/shared/s04450'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0459/'::text) AND ((path)::text < '/shared/s04590'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.010..0.010 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0495/'::text) AND ((path)::text < '/shared/s04950'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0522/'::text) AND ((path)::text < '/shared/s05220'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.009..0.009 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0540/'::text) AND ((path)::text < '/shared/s05400'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.008..0.009 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0546/'::text) AND ((path)::text < '/shared/s05460'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.012..0.012 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0547/'::text) AND ((path)::text < '/shared/s05470'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0587/'::text) AND ((path)::text < '/shared/s05870'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.010..0.010 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0673/'::text) AND ((path)::text < '/shared/s06730'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.009..0.010 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0675/'::text) AND ((path)::text < '/shared/s06750'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.009..0.009 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0694/'::text) AND ((path)::text < '/shared/s06940'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.012..0.012 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0697/'::text) AND ((path)::text < '/shared/s06970'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.841..0.841 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0721/'::text) AND ((path)::text < '/shared/s07210'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.016..0.016 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0741/'::text) AND ((path)::text < '/shared/s07410'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.011..0.011 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0774/'::text) AND ((path)::text < '/shared/s07740'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.021..0.021 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0793/'::text) AND ((path)::text < '/shared/s07930'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.009..0.010 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0805/'::text) AND ((path)::text < '/shared/s08050'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.010..0.010 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0840/'::text) AND ((path)::text < '/shared/s08400'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.018..0.019 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0848/'::text) AND ((path)::text < '/shared/s08480'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.011..0.011 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0854/'::text) AND ((path)::text < '/shared/s08540'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.009..0.010 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0901/'::text) AND ((path)::text < '/shared/s09010'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.015..0.015 rows=200 loops=1)
                                            Index Cond: (((path)::text > '/shared/s0973/'::text) AND ((path)::text < '/shared/s09730'::text))
                                            Buffers: shared hit=4
                                      ->  Bitmap Index Scan on ts_1b272604_e_owner  (cost=0.00..4.59 rows=22 width=0) (actual time=0.010..0.010 rows=21 loops=1)
                                            Index Cond: ((owner_id)::text = 'u000042'::text)
                                            Buffers: shared hit=3
Planning:
  Buffers: shared hit=81
Planning Time: 0.836 ms
Execution Time: 393.505 ms
```

**ordinary / fenced / count**

```
Aggregate  (cost=1352100.20..1352100.21 rows=1 width=8) (actual time=797.092..797.098 rows=1 loops=1)
  Buffers: shared hit=7374 read=9700, temp read=8515 written=9526
  ->  Hash Join  (cost=1238117.22..1330634.23 rows=8586390 width=0) (actual time=176.678..788.917 rows=200020 loops=1)
        Hash Cond: (c.entry_id = e.id)
        Buffers: shared hit=7374 read=9700, temp read=8515 written=9526
        ->  Seq Scan on ts_1b272604_c c  (cost=0.00..36013.00 rows=2200000 width=8) (actual time=0.033..205.115 rows=2200000 loops=1)
              Buffers: shared hit=4313 read=9700
        ->  Hash  (cost=1097246.34..1097246.34 rows=8586390 width=8) (actual time=175.534..175.538 rows=201024 loops=1)
              Buckets: 262144  Batches: 64  Memory Usage: 2174kB
              Buffers: shared hit=3061, temp read=385 written=2029
              ->  HashAggregate  (cost=944301.27..1097246.34 rows=8586390 width=8) (actual time=83.757..155.038 rows=201024 loops=1)
                    Group Key: e.id
                    Planned Partitions: 128  Batches: 129  Memory Usage: 8209kB  Disk Usage: 8152kB
                    Buffers: shared hit=3061, temp read=385 written=1396
                    ->  Append  (cost=5645.12..482782.81 rows=8586390 width=8) (actual time=5.881..41.756 rows=201044 loops=1)
                          Buffers: shared hit=3061
                          ->  Bitmap Heap Scan on ts_1b272604_e e  (cost=5645.12..27252.44 rows=206025 width=8) (actual time=5.880..24.689 rows=201003 loops=1)
                                Recheck Cond: (everyone_level >= '1'::smallint)
                                Heap Blocks: exact=1677
                                Buffers: shared hit=2670
                                ->  Bitmap Index Scan on ts_1b272604_e_lvlpath  (cost=0.00..5593.62 rows=206025 width=0) (actual time=5.737..5.737 rows=201003 loops=1)
                                      Index Cond: (everyone_level >= '1'::smallint)
                                      Buffers: shared hit=993
                          ->  Nested Loop  (cost=0.43..304.56 rows=33 width=8) (actual time=0.058..0.217 rows=1 loops=1)
                                Buffers: shared hit=144
                                ->  Function Scan on unnest ap  (cost=0.00..0.36 rows=36 width=32) (actual time=0.032..0.035 rows=36 loops=1)
                                ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_1  (cost=0.43..8.45 rows=1 width=29) (actual time=0.005..0.005 rows=0 loops=36)
                                      Index Cond: ((path)::text = (ap.value)::text)
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 1
                                      Buffers: shared hit=144
                          ->  Nested Loop  (cost=0.43..412257.99 rows=8380312 width=8) (actual time=0.016..0.792 rows=20 loops=1)
                                Buffers: shared hit=242
                                ->  Function Scan on ar  (cost=0.01..0.36 rows=36 width=64) (actual time=0.007..0.011 rows=36 loops=1)
                                ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_2  (cost=0.43..9123.74 rows=232786 width=29) (actual time=0.021..0.021 rows=1 loops=36)
                                      Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 194
                                      Buffers: shared hit=242
                          ->  Index Scan using ts_1b272604_e_owner on ts_1b272604_e e_3  (cost=0.43..35.88 rows=20 width=8) (actual time=0.010..0.014 rows=20 loops=1)
                                Index Cond: ((owner_id)::text = 'u000042'::text)
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 1
                                Buffers: shared hit=5
Planning Time: 0.239 ms
Execution Time: 798.422 ms
```

**ordinary / disjoint / count**

```
Finalize Aggregate  (cost=563916.00..563916.01 rows=1 width=8) (actual time=676.980..690.503 rows=1 loops=1)
  Buffers: shared hit=7761 read=9380, temp read=7784 written=7932
  ->  Gather  (cost=563915.79..563916.00 rows=2 width=8) (actual time=669.150..690.417 rows=3 loops=1)
        Workers Planned: 2
        Workers Launched: 2
        Buffers: shared hit=7761 read=9380, temp read=7784 written=7932
        ->  Partial Aggregate  (cost=562915.79..562915.80 rows=1 width=8) (actual time=651.111..651.120 rows=1 loops=3)
              Buffers: shared hit=7761 read=9380, temp read=7784 written=7932
              ->  Parallel Hash Join  (cost=38219.44..553971.63 rows=3577662 width=0) (actual time=535.600..647.433 rows=66673 loops=3)
                    Hash Cond: (e.id = c.entry_id)
                    Buffers: shared hit=7761 read=9380, temp read=7784 written=7932
                    ->  Parallel Append  (cost=0.43..455896.47 rows=3577662 width=8) (actual time=2.982..23.672 rows=67008 loops=3)
                          Buffers: shared hit=3064
                          ->  Nested Loop  (cost=0.43..412257.99 rows=8380312 width=8) (actual time=0.138..1.038 rows=20 loops=1)
                                Buffers: shared hit=243
                                ->  Function Scan on ar  (cost=0.01..0.36 rows=36 width=64) (actual time=0.079..0.086 rows=36 loops=1)
                                ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e  (cost=0.43..9123.74 rows=232786 width=29) (actual time=0.025..0.026 rows=1 loops=36)
                                      Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 194
                                      Buffers: shared hit=243
                          ->  Nested Loop  (cost=0.43..304.56 rows=33 width=8) (actual time=0.068..0.353 rows=1 loops=1)
                                Buffers: shared hit=145
                                ->  Function Scan on unnest ap  (cost=0.00..0.36 rows=36 width=32) (actual time=0.039..0.043 rows=36 loops=1)
                                ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_1  (cost=0.43..8.45 rows=1 width=29) (actual time=0.008..0.008 rows=0 loops=36)
                                      Index Cond: ((path)::text = (ap.value)::text)
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 1
                                      Buffers: shared hit=145
                          ->  Hash Anti Join  (cost=1.25..53.22 rows=18 width=8) (actual time=0.055..0.057 rows=0 loops=1)
                                Hash Cond: ((e_2.path)::text = (x0p.value)::text)
                                Buffers: shared hit=6
                                ->  Nested Loop Anti Join  (cost=0.43..52.18 rows=18 width=29) (actual time=0.054..0.055 rows=0 loops=1)
                                      Join Filter: (((e_2.path)::text > (x0r.lo)::text) AND ((e_2.path)::text < (x0r.hi)::text))
                                      Buffers: shared hit=6
                                      ->  Index Scan using ts_1b272604_e_owner on ts_1b272604_e e_2  (cost=0.43..35.88 rows=20 width=29) (actual time=0.032..0.039 rows=20 loops=1)
                                            Index Cond: ((owner_id)::text = 'u000042'::text)
                                            Filter: (everyone_level < '1'::smallint)
                                            Rows Removed by Filter: 1
                                            Buffers: shared hit=6
                                      ->  Function Scan on x0r  (cost=0.01..0.36 rows=36 width=64) (actual time=0.001..0.001 rows=1 loops=20)
                                ->  Hash  (cost=0.36..0.36 rows=36 width=32) (never executed)
                                      ->  Function Scan on unnest x0p  (cost=0.00..0.36 rows=36 width=32) (never executed)
                          ->  Parallel Bitmap Heap Scan on ts_1b272604_e e_3  (cost=5645.12..25750.17 rows=85844 width=8) (actual time=8.149..17.623 rows=67001 loops=3)
                                Recheck Cond: (everyone_level >= '1'::smallint)
                                Heap Blocks: exact=564
                                Buffers: shared hit=2670
                                ->  Bitmap Index Scan on ts_1b272604_e_lvlpath  (cost=0.00..5593.62 rows=206025 width=0) (actual time=8.497..8.497 rows=201003 loops=1)
                                      Index Cond: (everyone_level >= '1'::smallint)
                                      Buffers: shared hit=993
                    ->  Parallel Hash  (cost=23179.67..23179.67 rows=916667 width=8) (actual time=484.246..484.247 rows=733333 loops=3)
                          Buckets: 262144  Batches: 16  Memory Usage: 7488kB
                          Buffers: shared hit=4633 read=9380, temp written=7140
                          ->  Parallel Seq Scan on ts_1b272604_c c  (cost=0.00..23179.67 rows=916667 width=8) (actual time=256.731..345.904 rows=733333 loops=3)
                                Buffers: shared hit=4633 read=9380
Planning Time: 0.346 ms
JIT:
  Functions: 149
  Options: Inlining true, Optimization true, Expressions true, Deforming true
  Timing: Generation 4.251 ms (Deform 1.465 ms), Inlining 184.246 ms, Optimization 310.322 ms, Emission 275.943 ms, Total 774.762 ms
Execution Time: 692.554 ms
```

**ordinary / union / top10**

```
Limit  (cost=944301.70..1360240.42 rows=10 width=12) (actual time=1164.054..2716.165 rows=10 loops=1)
  Buffers: shared hit=3159, temp read=39518 written=1838
  ->  Nested Loop  (cost=944301.70..357142148033.09 rows=8586390 width=12) (actual time=1048.318..2600.423 rows=10 loops=1)
        Join Filter: (c.entry_id = e.id)
        Rows Removed by Join Filter: 17997435
        Buffers: shared hit=3159, temp read=39518 written=1838
        ->  Index Scan using ts_1b272604_c_score on ts_1b272604_c c  (cost=0.43..121657.58 rows=2200000 width=20) (actual time=0.033..1.479 rows=95 loops=1)
              Buffers: shared hit=98
        ->  Materialize  (cost=944301.27..1173719.29 rows=8586390 width=8) (actual time=0.991..15.831 rows=189447 loops=95)
              Buffers: shared hit=3061, temp read=39518 written=1838
              ->  HashAggregate  (cost=944301.27..1097246.34 rows=8586390 width=8) (actual time=93.893..176.510 rows=201024 loops=1)
                    Group Key: e.id
                    Planned Partitions: 128  Batches: 129  Memory Usage: 8209kB  Disk Usage: 8152kB
                    Buffers: shared hit=3061, temp read=385 written=1396
                    ->  Append  (cost=5645.12..482782.81 rows=8586390 width=8) (actual time=5.317..43.983 rows=201044 loops=1)
                          Buffers: shared hit=3061
                          ->  Bitmap Heap Scan on ts_1b272604_e e  (cost=5645.12..27252.44 rows=206025 width=8) (actual time=5.315..24.692 rows=201003 loops=1)
                                Recheck Cond: (everyone_level >= '1'::smallint)
                                Heap Blocks: exact=1677
                                Buffers: shared hit=2670
                                ->  Bitmap Index Scan on ts_1b272604_e_lvlpath  (cost=0.00..5593.62 rows=206025 width=0) (actual time=5.149..5.149 rows=201003 loops=1)
                                      Index Cond: (everyone_level >= '1'::smallint)
                                      Buffers: shared hit=993
                          ->  Nested Loop  (cost=0.43..304.56 rows=33 width=8) (actual time=0.075..0.233 rows=1 loops=1)
                                Buffers: shared hit=144
                                ->  Function Scan on unnest ap  (cost=0.00..0.36 rows=36 width=32) (actual time=0.048..0.050 rows=36 loops=1)
                                ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_1  (cost=0.43..8.45 rows=1 width=29) (actual time=0.005..0.005 rows=0 loops=36)
                                      Index Cond: ((path)::text = (ap.value)::text)
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 1
                                      Buffers: shared hit=144
                          ->  Nested Loop  (cost=0.43..412257.99 rows=8380312 width=8) (actual time=0.033..0.674 rows=20 loops=1)
                                Buffers: shared hit=242
                                ->  Function Scan on ar  (cost=0.01..0.36 rows=36 width=64) (actual time=0.021..0.024 rows=36 loops=1)
                                ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_2  (cost=0.43..9123.74 rows=232786 width=29) (actual time=0.018..0.018 rows=1 loops=36)
                                      Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 194
                                      Buffers: shared hit=242
                          ->  Index Scan using ts_1b272604_e_owner on ts_1b272604_e e_3  (cost=0.43..35.88 rows=20 width=8) (actual time=0.021..0.025 rows=20 loops=1)
                                Index Cond: ((owner_id)::text = 'u000042'::text)
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 1
                                Buffers: shared hit=5
Planning Time: 0.257 ms
JIT:
  Functions: 40
  Options: Inlining true, Optimization true, Expressions true, Deforming true
  Timing: Generation 0.906 ms (Deform 0.326 ms), Inlining 8.071 ms, Optimization 72.651 ms, Emission 39.039 ms, Total 120.667 ms
Execution Time: 2718.548 ms
```

**ordinary / unionall / top10**

```
Limit  (cost=944301.70..1360240.42 rows=10 width=12) (actual time=1154.415..2772.200 rows=10 loops=1)
  Buffers: shared hit=3159, temp read=39518 written=1838
  ->  Nested Loop  (cost=944301.70..357142148033.09 rows=8586390 width=12) (actual time=1041.424..2659.199 rows=10 loops=1)
        Join Filter: (c.entry_id = e.id)
        Rows Removed by Join Filter: 17997435
        Buffers: shared hit=3159, temp read=39518 written=1838
        ->  Index Scan using ts_1b272604_c_score on ts_1b272604_c c  (cost=0.43..121657.58 rows=2200000 width=20) (actual time=0.081..1.839 rows=95 loops=1)
              Buffers: shared hit=98
        ->  Materialize  (cost=944301.27..1173719.29 rows=8586390 width=8) (actual time=1.034..16.592 rows=189447 loops=95)
              Buffers: shared hit=3061, temp read=39518 written=1838
              ->  HashAggregate  (cost=944301.27..1097246.34 rows=8586390 width=8) (actual time=97.847..186.311 rows=201024 loops=1)
                    Group Key: e.id
                    Planned Partitions: 128  Batches: 129  Memory Usage: 8209kB  Disk Usage: 8152kB
                    Buffers: shared hit=3061, temp read=385 written=1396
                    ->  Append  (cost=5645.12..482782.81 rows=8586390 width=8) (actual time=9.464..47.905 rows=201044 loops=1)
                          Buffers: shared hit=3061
                          ->  Bitmap Heap Scan on ts_1b272604_e e  (cost=5645.12..27252.44 rows=206025 width=8) (actual time=9.456..29.878 rows=201003 loops=1)
                                Recheck Cond: (everyone_level >= '1'::smallint)
                                Heap Blocks: exact=1677
                                Buffers: shared hit=2670
                                ->  Bitmap Index Scan on ts_1b272604_e_lvlpath  (cost=0.00..5593.62 rows=206025 width=0) (actual time=9.275..9.276 rows=201003 loops=1)
                                      Index Cond: (everyone_level >= '1'::smallint)
                                      Buffers: shared hit=993
                          ->  Nested Loop  (cost=0.43..304.56 rows=33 width=8) (actual time=0.095..0.278 rows=1 loops=1)
                                Buffers: shared hit=144
                                ->  Function Scan on unnest ap  (cost=0.00..0.36 rows=36 width=32) (actual time=0.059..0.063 rows=36 loops=1)
                                ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_1  (cost=0.43..8.45 rows=1 width=29) (actual time=0.005..0.005 rows=0 loops=36)
                                      Index Cond: ((path)::text = (ap.value)::text)
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 1
                                      Buffers: shared hit=144
                          ->  Nested Loop  (cost=0.43..412257.99 rows=8380312 width=8) (actual time=0.026..0.902 rows=20 loops=1)
                                Buffers: shared hit=242
                                ->  Function Scan on ar  (cost=0.01..0.36 rows=36 width=64) (actual time=0.015..0.021 rows=36 loops=1)
                                ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_2  (cost=0.43..9123.74 rows=232786 width=29) (actual time=0.024..0.024 rows=1 loops=36)
                                      Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 194
                                      Buffers: shared hit=242
                          ->  Index Scan using ts_1b272604_e_owner on ts_1b272604_e e_3  (cost=0.43..35.88 rows=20 width=8) (actual time=0.064..0.071 rows=20 loops=1)
                                Index Cond: ((owner_id)::text = 'u000042'::text)
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 1
                                Buffers: shared hit=5
Planning Time: 0.320 ms
JIT:
  Functions: 40
  Options: Inlining true, Optimization true, Expressions true, Deforming true
  Timing: Generation 0.899 ms (Deform 0.307 ms), Inlining 9.096 ms, Optimization 58.025 ms, Emission 50.305 ms, Total 118.325 ms
Execution Time: 2775.168 ms
```

**ordinary / literal / top10**

```
Limit  (cost=0.95..93.50 rows=10 width=12) (actual time=0.206..0.505 rows=10 loops=1)
  Buffers: shared hit=478
  ->  Nested Loop  (cost=0.95..1823533.33 rows=197024 width=12) (actual time=0.205..0.503 rows=10 loops=1)
        Buffers: shared hit=478
        ->  Index Scan using ts_1b272604_c_score on ts_1b272604_c c  (cost=0.43..121657.58 rows=2200000 width=20) (actual time=0.013..0.107 rows=95 loops=1)
              Buffers: shared hit=98
        ->  Index Scan using ts_1b272604_e_pkey on ts_1b272604_e e  (cost=0.52..0.77 rows=1 width=8) (actual time=0.004..0.004 rows=0 loops=95)
              Index Cond: (id = c.entry_id)
              Filter: ((everyone_level >= '1'::smallint) OR ((path)::text = ANY ('{/home/u000042,/shared/s0007,/shared/s0035,/shared/s0038,/shared/s0055,/shared/s0079,/shared/s0103,/shared/s0133,/shared/s0144,/shared/s0173,/shared/s0333,/shared/s0380,/shared/s0387,/shared/s0400,/shared/s0445,/shared/s0459,/shared/s0495,/shared/s0522,/shared/s0540,/shared/s0546,/shared/s0547,/shared/s0587,/shared/s0673,/shared/s0675,/shared/s0694,/shared/s0697,/shared/s0721,/shared/s0741,/shared/s0774,/shared/s0793,/shared/s0805,/shared/s0840,/shared/s0848,/shared/s0854,/shared/s0901,/shared/s0973}'::text[])) OR (((path)::text > '/home/u000042/'::text) AND ((path)::text < '/home/u0000420'::text)) OR (((path)::text > '/shared/s0007/'::text) AND ((path)::text < '/shared/s00070'::text)) OR (((path)::text > '/shared/s0035/'::text) AND ((path)::text < '/shared/s00350'::text)) OR (((path)::text > '/shared/s0038/'::text) AND ((path)::text < '/shared/s00380'::text)) OR (((path)::text > '/shared/s0055/'::text) AND ((path)::text < '/shared/s00550'::text)) OR (((path)::text > '/shared/s0079/'::text) AND ((path)::text < '/shared/s00790'::text)) OR (((path)::text > '/shared/s0103/'::text) AND ((path)::text < '/shared/s01030'::text)) OR (((path)::text > '/shared/s0133/'::text) AND ((path)::text < '/shared/s01330'::text)) OR (((path)::text > '/shared/s0144/'::text) AND ((path)::text < '/shared/s01440'::text)) OR (((path)::text > '/shared/s0173/'::text) AND ((path)::text < '/shared/s01730'::text)) OR (((path)::text > '/shared/s0333/'::text) AND ((path)::text < '/shared/s03330'::text)) OR (((path)::text > '/shared/s0380/'::text) AND ((path)::text < '/shared/s03800'::text)) OR (((path)::text > '/shared/s0387/'::text) AND ((path)::text < '/shared/s03870'::text)) OR (((path)::text > '/shared/s0400/'::text) AND ((path)::text < '/shared/s04000'::text)) OR (((path)::text > '/shared/s0445/'::text) AND ((path)::text < '/shared/s04450'::text)) OR (((path)::text > '/shared/s0459/'::text) AND ((path)::text < '/shared/s04590'::text)) OR (((path)::text > '/shared/s0495/'::text) AND ((path)::text < '/shared/s04950'::text)) OR (((path)::text > '/shared/s0522/'::text) AND ((path)::text < '/shared/s05220'::text)) OR (((path)::text > '/shared/s0540/'::text) AND ((path)::text < '/shared/s05400'::text)) OR (((path)::text > '/shared/s0546/'::text) AND ((path)::text < '/shared/s05460'::text)) OR (((path)::text > '/shared/s0547/'::text) AND ((path)::text < '/shared/s05470'::text)) OR (((path)::text > '/shared/s0587/'::text) AND ((path)::text < '/shared/s05870'::text)) OR (((path)::text > '/shared/s0673/'::text) AND ((path)::text < '/shared/s06730'::text)) OR (((path)::text > '/shared/s0675/'::text) AND ((path)::text < '/shared/s06750'::text)) OR (((path)::text > '/shared/s0694/'::text) AND ((path)::text < '/shared/s06940'::text)) OR (((path)::text > '/shared/s0697/'::text) AND ((path)::text < '/shared/s06970'::text)) OR (((path)::text > '/shared/s0721/'::text) AND ((path)::text < '/shared/s07210'::text)) OR (((path)::text > '/shared/s0741/'::text) AND ((path)::text < '/shared/s07410'::text)) OR (((path)::text > '/shared/s0774/'::text) AND ((path)::text < '/shared/s07740'::text)) OR (((path)::text > '/shared/s0793/'::text) AND ((path)::text < '/shared/s07930'::text)) OR (((path)::text > '/shared/s0805/'::text) AND ((path)::text < '/shared/s08050'::text)) OR (((path)::text > '/shared/s0840/'::text) AND ((path)::text < '/shared/s08400'::text)) OR (((path)::text > '/shared/s0848/'::text) AND ((path)::text < '/shared/s08480'::text)) OR (((path)::text > '/shared/s0854/'::text) AND ((path)::text < '/shared/s08540'::text)) OR (((path)::text > '/shared/s0901/'::text) AND ((path)::text < '/shared/s09010'::text)) OR (((path)::text > '/shared/s0973/'::text) AND ((path)::text < '/shared/s09730'::text)) OR ((owner_id)::text = 'u000042'::text))
              Rows Removed by Filter: 1
              Buffers: shared hit=380
Planning:
  Buffers: shared hit=81
Planning Time: 0.672 ms
Execution Time: 0.557 ms
```

**ordinary / fenced / top10**

```
Limit  (cost=944301.70..1360240.42 rows=10 width=12) (actual time=1144.263..2619.389 rows=10 loops=1)
  Buffers: shared hit=3159, temp read=39518 written=1838
  ->  Nested Loop  (cost=944301.70..357142148033.09 rows=8586390 width=12) (actual time=1144.262..2619.381 rows=10 loops=1)
        Join Filter: (c.entry_id = e.id)
        Rows Removed by Join Filter: 17997435
        Buffers: shared hit=3159, temp read=39518 written=1838
        ->  Index Scan using ts_1b272604_c_score on ts_1b272604_c c  (cost=0.43..121657.58 rows=2200000 width=20) (actual time=0.038..1.363 rows=95 loops=1)
              Buffers: shared hit=98
        ->  Materialize  (cost=944301.27..1173719.29 rows=8586390 width=8) (actual time=1.601..17.546 rows=189447 loops=95)
              Buffers: shared hit=3061, temp read=39518 written=1838
              ->  HashAggregate  (cost=944301.27..1097246.34 rows=8586390 width=8) (actual time=151.712..242.900 rows=201024 loops=1)
                    Group Key: e.id
                    Planned Partitions: 128  Batches: 129  Memory Usage: 8209kB  Disk Usage: 8152kB
                    Buffers: shared hit=3061, temp read=385 written=1396
                    ->  Append  (cost=5645.12..482782.81 rows=8586390 width=8) (actual time=7.302..64.639 rows=201044 loops=1)
                          Buffers: shared hit=3061
                          ->  Bitmap Heap Scan on ts_1b272604_e e  (cost=5645.12..27252.44 rows=206025 width=8) (actual time=7.301..39.613 rows=201003 loops=1)
                                Recheck Cond: (everyone_level >= '1'::smallint)
                                Heap Blocks: exact=1677
                                Buffers: shared hit=2670
                                ->  Bitmap Index Scan on ts_1b272604_e_lvlpath  (cost=0.00..5593.62 rows=206025 width=0) (actual time=7.156..7.156 rows=201003 loops=1)
                                      Index Cond: (everyone_level >= '1'::smallint)
                                      Buffers: shared hit=993
                          ->  Nested Loop  (cost=0.43..304.56 rows=33 width=8) (actual time=0.708..1.323 rows=1 loops=1)
                                Buffers: shared hit=144
                                ->  Function Scan on unnest ap  (cost=0.00..0.36 rows=36 width=32) (actual time=0.671..0.676 rows=36 loops=1)
                                ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_1  (cost=0.43..8.45 rows=1 width=29) (actual time=0.017..0.017 rows=0 loops=36)
                                      Index Cond: ((path)::text = (ap.value)::text)
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 1
                                      Buffers: shared hit=144
                          ->  Nested Loop  (cost=0.43..412257.99 rows=8380312 width=8) (actual time=0.025..1.201 rows=20 loops=1)
                                Buffers: shared hit=242
                                ->  Function Scan on ar  (cost=0.01..0.36 rows=36 width=64) (actual time=0.015..0.024 rows=36 loops=1)
                                ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_2  (cost=0.43..9123.74 rows=232786 width=29) (actual time=0.032..0.032 rows=1 loops=36)
                                      Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 194
                                      Buffers: shared hit=242
                          ->  Index Scan using ts_1b272604_e_owner on ts_1b272604_e e_3  (cost=0.43..35.88 rows=20 width=8) (actual time=1.753..1.758 rows=20 loops=1)
                                Index Cond: ((owner_id)::text = 'u000042'::text)
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 1
                                Buffers: shared hit=5
Planning Time: 0.297 ms
Execution Time: 2626.933 ms
```

**ordinary / disjoint / top10**

```
Limit  (cost=5645.55..421584.86 rows=10 width=12) (actual time=862.648..2458.085 rows=10 loops=1)
  Buffers: shared hit=3159, temp read=41365 written=442
  ->  Nested Loop  (cost=5645.55..357141629923.69 rows=8586388 width=12) (actual time=853.170..2448.600 rows=10 loops=1)
        Join Filter: (c.entry_id = e.id)
        Rows Removed by Join Filter: 19013958
        Buffers: shared hit=3159, temp read=41365 written=442
        ->  Index Scan using ts_1b272604_c_score on ts_1b272604_c c  (cost=0.43..121657.58 rows=2200000 width=20) (actual time=0.034..1.504 rows=95 loops=1)
              Buffers: shared hit=98
        ->  Materialize  (cost=5645.12..559273.08 rows=8586388 width=8) (actual time=0.059..13.919 rows=200147 loops=95)
              Buffers: shared hit=3061, temp read=41365 written=442
              ->  Append  (cost=5645.12..482800.14 rows=8586388 width=8) (actual time=5.355..44.444 rows=201024 loops=1)
                    Buffers: shared hit=3061
                    ->  Bitmap Heap Scan on ts_1b272604_e e  (cost=5645.12..27252.44 rows=206025 width=8) (actual time=5.354..26.657 rows=201003 loops=1)
                          Recheck Cond: (everyone_level >= '1'::smallint)
                          Heap Blocks: exact=1677
                          Buffers: shared hit=2670
                          ->  Bitmap Index Scan on ts_1b272604_e_lvlpath  (cost=0.00..5593.62 rows=206025 width=0) (actual time=5.188..5.188 rows=201003 loops=1)
                                Index Cond: (everyone_level >= '1'::smallint)
                                Buffers: shared hit=993
                    ->  Nested Loop  (cost=0.43..304.56 rows=33 width=8) (actual time=0.073..0.345 rows=1 loops=1)
                          Buffers: shared hit=144
                          ->  Function Scan on unnest ap  (cost=0.00..0.36 rows=36 width=32) (actual time=0.039..0.043 rows=36 loops=1)
                          ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_1  (cost=0.43..8.45 rows=1 width=29) (actual time=0.008..0.008 rows=0 loops=36)
                                Index Cond: ((path)::text = (ap.value)::text)
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 1
                                Buffers: shared hit=144
                    ->  Nested Loop  (cost=0.43..412257.99 rows=8380312 width=8) (actual time=0.034..0.990 rows=20 loops=1)
                          Buffers: shared hit=242
                          ->  Function Scan on ar  (cost=0.01..0.36 rows=36 width=64) (actual time=0.011..0.018 rows=36 loops=1)
                          ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_2  (cost=0.43..9123.74 rows=232786 width=29) (actual time=0.026..0.026 rows=1 loops=36)
                                Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 194
                                Buffers: shared hit=242
                    ->  Hash Anti Join  (cost=1.25..53.22 rows=18 width=8) (actual time=0.043..0.046 rows=0 loops=1)
                          Hash Cond: ((e_3.path)::text = (x0p.value)::text)
                          Buffers: shared hit=5
                          ->  Nested Loop Anti Join  (cost=0.43..52.18 rows=18 width=29) (actual time=0.042..0.043 rows=0 loops=1)
                                Join Filter: (((e_3.path)::text > (x0r.lo)::text) AND ((e_3.path)::text < (x0r.hi)::text))
                                Buffers: shared hit=5
                                ->  Index Scan using ts_1b272604_e_owner on ts_1b272604_e e_3  (cost=0.43..35.88 rows=20 width=29) (actual time=0.024..0.028 rows=20 loops=1)
                                      Index Cond: ((owner_id)::text = 'u000042'::text)
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 1
                                      Buffers: shared hit=5
                                ->  Function Scan on x0r  (cost=0.01..0.36 rows=36 width=64) (actual time=0.000..0.000 rows=1 loops=20)
                          ->  Hash  (cost=0.36..0.36 rows=36 width=32) (never executed)
                                ->  Function Scan on unnest x0p  (cost=0.00..0.36 rows=36 width=32) (never executed)
Planning Time: 0.303 ms
JIT:
  Functions: 46
  Options: Inlining false, Optimization false, Expressions true, Deforming true
  Timing: Generation 0.824 ms (Deform 0.362 ms), Inlining 0.000 ms, Optimization 0.398 ms, Emission 9.165 ms, Total 10.387 ms
Execution Time: 2459.650 ms
```

**two subjects / union / entries**

```
HashAggregate  (cost=424282.50..481860.20 rows=3232432 width=8) (actual time=113.514..193.676 rows=201003 loops=1)
  Group Key: e.id
  Planned Partitions: 64  Batches: 65  Memory Usage: 10769kB  Disk Usage: 4080kB
  Buffers: shared hit=2840, temp read=380 written=881
  ->  Append  (cost=5645.12..250539.28 rows=3232432 width=8) (actual time=21.845..59.250 rows=201003 loops=1)
        Buffers: shared hit=2840
        ->  Bitmap Heap Scan on ts_1b272604_e e  (cost=5645.12..27252.44 rows=206025 width=8) (actual time=21.844..42.184 rows=201003 loops=1)
              Recheck Cond: (everyone_level >= '1'::smallint)
              Heap Blocks: exact=1677
              Buffers: shared hit=2670
              ->  Bitmap Index Scan on ts_1b272604_e_lvlpath  (cost=0.00..5593.62 rows=206025 width=0) (actual time=5.008..5.009 rows=201003 loops=1)
                    Index Cond: (everyone_level >= '1'::smallint)
                    Buffers: shared hit=993
        ->  Nested Loop  (cost=0.43..109.98 rows=12 width=8) (actual time=0.157..0.157 rows=0 loops=1)
              Buffers: shared hit=52
              ->  Function Scan on unnest ap  (cost=0.00..0.13 rows=13 width=32) (actual time=0.047..0.048 rows=13 loops=1)
              ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_1  (cost=0.43..8.45 rows=1 width=29) (actual time=0.007..0.007 rows=0 loops=13)
                    Index Cond: ((path)::text = (ap.value)::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 1
                    Buffers: shared hit=52
        ->  Nested Loop  (cost=0.43..206841.85 rows=3026224 width=8) (actual time=0.346..0.347 rows=0 loops=1)
              Buffers: shared hit=88
              ->  Function Scan on ar  (cost=0.01..0.14 rows=13 width=64) (actual time=0.010..0.012 rows=13 loops=1)
              ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_2  (cost=0.43..13583.04 rows=232786 width=29) (actual time=0.025..0.025 rows=0 loops=13)
                    Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 200
                    Buffers: shared hit=88
        ->  Hash Join  (cost=1.33..36.86 rows=1 width=8) (actual time=0.046..0.048 rows=0 loops=1)
              Hash Cond: ((e_3.path)::text = (o0p.value)::text)
              Buffers: shared hit=5
              ->  Index Scan using ts_1b272604_e_owner on ts_1b272604_e e_3  (cost=0.43..35.88 rows=20 width=29) (actual time=0.015..0.019 rows=20 loops=1)
                    Index Cond: ((owner_id)::text = 'u000042'::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 1
                    Buffers: shared hit=5
              ->  Hash  (cost=0.40..0.40 rows=40 width=32) (actual time=0.017..0.018 rows=40 loops=1)
                    Buckets: 1024  Batches: 1  Memory Usage: 10kB
                    ->  Function Scan on unnest o0p  (cost=0.00..0.40 rows=40 width=32) (actual time=0.008..0.011 rows=40 loops=1)
        ->  Nested Loop  (cost=0.43..50.33 rows=89 width=8) (actual time=0.135..0.137 rows=0 loops=1)
              Join Filter: (((e_4.path)::text > (o0r.lo)::text) AND ((e_4.path)::text < (o0r.hi)::text))
              Rows Removed by Join Filter: 800
              Buffers: shared hit=5
              ->  Function Scan on o0r  (cost=0.01..0.41 rows=40 width=64) (actual time=0.007..0.010 rows=40 loops=1)
              ->  Materialize  (cost=0.43..35.98 rows=20 width=29) (actual time=0.000..0.001 rows=20 loops=40)
                    Buffers: shared hit=5
                    ->  Index Scan using ts_1b272604_e_owner on ts_1b272604_e e_4  (cost=0.43..35.88 rows=20 width=29) (actual time=0.006..0.009 rows=20 loops=1)
                          Index Cond: ((owner_id)::text = 'u000042'::text)
                          Filter: (everyone_level < '1'::smallint)
                          Rows Removed by Filter: 1
                          Buffers: shared hit=5
        ->  Hash Join  (cost=1.24..36.77 rows=1 width=8) (actual time=0.030..0.032 rows=0 loops=1)
              Hash Cond: ((e_5.path)::text = (o1p.value)::text)
              Buffers: shared hit=10
              ->  Index Scan using ts_1b272604_e_owner on ts_1b272604_e e_5  (cost=0.43..35.88 rows=20 width=29) (actual time=0.005..0.015 rows=20 loops=1)
                    Index Cond: ((owner_id)::text = 'u000044'::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 6
                    Buffers: shared hit=10
              ->  Hash  (cost=0.36..0.36 rows=36 width=32) (actual time=0.011..0.012 rows=36 loops=1)
                    Buckets: 1024  Batches: 1  Memory Usage: 10kB
                    ->  Function Scan on unnest o1p  (cost=0.00..0.36 rows=36 width=32) (actual time=0.004..0.006 rows=36 loops=1)
        ->  Nested Loop  (cost=0.43..48.89 rows=80 width=8) (actual time=0.130..0.131 rows=0 loops=1)
              Join Filter: (((e_6.path)::text > (o1r.lo)::text) AND ((e_6.path)::text < (o1r.hi)::text))
              Rows Removed by Join Filter: 720
              Buffers: shared hit=10
              ->  Function Scan on o1r  (cost=0.01..0.36 rows=36 width=64) (actual time=0.006..0.009 rows=36 loops=1)
              ->  Materialize  (cost=0.43..35.98 rows=20 width=29) (actual time=0.000..0.002 rows=20 loops=36)
                    Buffers: shared hit=10
                    ->  Index Scan using ts_1b272604_e_owner on ts_1b272604_e e_6  (cost=0.43..35.88 rows=20 width=29) (actual time=0.009..0.015 rows=20 loops=1)
                          Index Cond: ((owner_id)::text = 'u000044'::text)
                          Filter: (everyone_level < '1'::smallint)
                          Rows Removed by Filter: 6
                          Buffers: shared hit=10
Planning Time: 0.319 ms
JIT:
  Functions: 82
  Options: Inlining false, Optimization false, Expressions true, Deforming true
  Timing: Generation 1.792 ms (Deform 0.757 ms), Inlining 0.000 ms, Optimization 0.876 ms, Emission 17.477 ms, Total 20.145 ms
Execution Time: 203.390 ms
```

**two subjects / unionall / entries**

```
HashAggregate  (cost=424282.50..481860.20 rows=3232432 width=8) (actual time=118.812..206.524 rows=201003 loops=1)
  Group Key: e.id
  Planned Partitions: 64  Batches: 65  Memory Usage: 10769kB  Disk Usage: 4080kB
  Buffers: shared hit=2840, temp read=380 written=881
  ->  Append  (cost=5645.12..250539.28 rows=3232432 width=8) (actual time=24.597..62.989 rows=201003 loops=1)
        Buffers: shared hit=2840
        ->  Bitmap Heap Scan on ts_1b272604_e e  (cost=5645.12..27252.44 rows=206025 width=8) (actual time=24.596..45.484 rows=201003 loops=1)
              Recheck Cond: (everyone_level >= '1'::smallint)
              Heap Blocks: exact=1677
              Buffers: shared hit=2670
              ->  Bitmap Index Scan on ts_1b272604_e_lvlpath  (cost=0.00..5593.62 rows=206025 width=0) (actual time=5.140..5.140 rows=201003 loops=1)
                    Index Cond: (everyone_level >= '1'::smallint)
                    Buffers: shared hit=993
        ->  Nested Loop  (cost=0.43..109.98 rows=12 width=8) (actual time=0.124..0.124 rows=0 loops=1)
              Buffers: shared hit=52
              ->  Function Scan on unnest ap  (cost=0.00..0.13 rows=13 width=32) (actual time=0.044..0.045 rows=13 loops=1)
              ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_1  (cost=0.43..8.45 rows=1 width=29) (actual time=0.005..0.005 rows=0 loops=13)
                    Index Cond: ((path)::text = (ap.value)::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 1
                    Buffers: shared hit=52
        ->  Nested Loop  (cost=0.43..206841.85 rows=3026224 width=8) (actual time=0.365..0.366 rows=0 loops=1)
              Buffers: shared hit=88
              ->  Function Scan on ar  (cost=0.01..0.14 rows=13 width=64) (actual time=0.006..0.008 rows=13 loops=1)
              ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_2  (cost=0.43..13583.04 rows=232786 width=29) (actual time=0.027..0.027 rows=0 loops=13)
                    Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 200
                    Buffers: shared hit=88
        ->  Hash Join  (cost=1.33..36.86 rows=1 width=8) (actual time=0.048..0.050 rows=0 loops=1)
              Hash Cond: ((e_3.path)::text = (o0p.value)::text)
              Buffers: shared hit=5
              ->  Index Scan using ts_1b272604_e_owner on ts_1b272604_e e_3  (cost=0.43..35.88 rows=20 width=29) (actual time=0.017..0.022 rows=20 loops=1)
                    Index Cond: ((owner_id)::text = 'u000042'::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 1
                    Buffers: shared hit=5
              ->  Hash  (cost=0.40..0.40 rows=40 width=32) (actual time=0.017..0.018 rows=40 loops=1)
                    Buckets: 1024  Batches: 1  Memory Usage: 10kB
                    ->  Function Scan on unnest o0p  (cost=0.00..0.40 rows=40 width=32) (actual time=0.007..0.010 rows=40 loops=1)
        ->  Nested Loop  (cost=0.43..50.33 rows=89 width=8) (actual time=0.158..0.159 rows=0 loops=1)
              Join Filter: (((e_4.path)::text > (o0r.lo)::text) AND ((e_4.path)::text < (o0r.hi)::text))
              Rows Removed by Join Filter: 800
              Buffers: shared hit=5
              ->  Function Scan on o0r  (cost=0.01..0.41 rows=40 width=64) (actual time=0.008..0.011 rows=40 loops=1)
              ->  Materialize  (cost=0.43..35.98 rows=20 width=29) (actual time=0.000..0.002 rows=20 loops=40)
                    Buffers: shared hit=5
                    ->  Index Scan using ts_1b272604_e_owner on ts_1b272604_e e_4  (cost=0.43..35.88 rows=20 width=29) (actual time=0.006..0.009 rows=20 loops=1)
                          Index Cond: ((owner_id)::text = 'u000042'::text)
                          Filter: (everyone_level < '1'::smallint)
                          Rows Removed by Filter: 1
                          Buffers: shared hit=5
        ->  Hash Join  (cost=1.24..36.77 rows=1 width=8) (actual time=0.031..0.032 rows=0 loops=1)
              Hash Cond: ((e_5.path)::text = (o1p.value)::text)
              Buffers: shared hit=10
              ->  Index Scan using ts_1b272604_e_owner on ts_1b272604_e e_5  (cost=0.43..35.88 rows=20 width=29) (actual time=0.005..0.015 rows=20 loops=1)
                    Index Cond: ((owner_id)::text = 'u000044'::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 6
                    Buffers: shared hit=10
              ->  Hash  (cost=0.36..0.36 rows=36 width=32) (actual time=0.011..0.011 rows=36 loops=1)
                    Buckets: 1024  Batches: 1  Memory Usage: 10kB
                    ->  Function Scan on unnest o1p  (cost=0.00..0.36 rows=36 width=32) (actual time=0.004..0.006 rows=36 loops=1)
        ->  Nested Loop  (cost=0.43..48.89 rows=80 width=8) (actual time=0.151..0.151 rows=0 loops=1)
              Join Filter: (((e_6.path)::text > (o1r.lo)::text) AND ((e_6.path)::text < (o1r.hi)::text))
              Rows Removed by Join Filter: 720
              Buffers: shared hit=10
              ->  Function Scan on o1r  (cost=0.01..0.36 rows=36 width=64) (actual time=0.005..0.009 rows=36 loops=1)
              ->  Materialize  (cost=0.43..35.98 rows=20 width=29) (actual time=0.000..0.002 rows=20 loops=36)
                    Buffers: shared hit=10
                    ->  Index Scan using ts_1b272604_e_owner on ts_1b272604_e e_6  (cost=0.43..35.88 rows=20 width=29) (actual time=0.005..0.012 rows=20 loops=1)
                          Index Cond: ((owner_id)::text = 'u000044'::text)
                          Filter: (everyone_level < '1'::smallint)
                          Rows Removed by Filter: 6
                          Buffers: shared hit=10
Planning Time: 0.293 ms
JIT:
  Functions: 82
  Options: Inlining false, Optimization false, Expressions true, Deforming true
  Timing: Generation 1.291 ms (Deform 0.513 ms), Inlining 0.000 ms, Optimization 1.047 ms, Emission 19.836 ms, Total 22.175 ms
Execution Time: 216.592 ms
```

**two subjects / literal / entries**

```
Gather  (cost=7594.09..88231.53 rows=206037 width=8) (actual time=12.969..31.849 rows=201003 loops=1)
  Workers Planned: 2
  Workers Launched: 2
  Buffers: shared hit=2771
  ->  Parallel Bitmap Heap Scan on ts_1b272604_e e  (cost=6594.09..66627.83 rows=85849 width=8) (actual time=6.950..16.585 rows=67001 loops=3)
        Recheck Cond: ((everyone_level >= '1'::smallint) OR ((path)::text = ANY ('{/shared/s0038,/shared/s0079,/shared/s0173,/shared/s0522,/shared/s0546,/shared/s0694,/shared/s0697,/shared/s0741,/shared/s0774,/shared/s0840,/shared/s0848,/shared/s0854,/shared/s0901}'::text[])) OR (((path)::text > '/shared/s0038/'::text) AND ((path)::text < '/shared/s00380'::text)) OR (((path)::text > '/shared/s0079/'::text) AND ((path)::text < '/shared/s00790'::text)) OR (((path)::text > '/shared/s0173/'::text) AND ((path)::text < '/shared/s01730'::text)) OR (((path)::text > '/shared/s0522/'::text) AND ((path)::text < '/shared/s05220'::text)) OR (((path)::text > '/shared/s0546/'::text) AND ((path)::text < '/shared/s05460'::text)) OR (((path)::text > '/shared/s0694/'::text) AND ((path)::text < '/shared/s06940'::text)) OR (((path)::text > '/shared/s0697/'::text) AND ((path)::text < '/shared/s06970'::text)) OR (((path)::text > '/shared/s0741/'::text) AND ((path)::text < '/shared/s07410'::text)) OR (((path)::text > '/shared/s0774/'::text) AND ((path)::text < '/shared/s07740'::text)) OR (((path)::text > '/shared/s0840/'::text) AND ((path)::text < '/shared/s08400'::text)) OR (((path)::text > '/shared/s0848/'::text) AND ((path)::text < '/shared/s08480'::text)) OR (((path)::text > '/shared/s0854/'::text) AND ((path)::text < '/shared/s08540'::text)) OR (((path)::text > '/shared/s0901/'::text) AND ((path)::text < '/shared/s09010'::text)) OR ((owner_id)::text = 'u000042'::text) OR ((owner_id)::text = 'u000044'::text))
        Filter: ((everyone_level >= '1'::smallint) OR ((path)::text = ANY ('{/shared/s0038,/shared/s0079,/shared/s0173,/shared/s0522,/shared/s0546,/shared/s0694,/shared/s0697,/shared/s0741,/shared/s0774,/shared/s0840,/shared/s0848,/shared/s0854,/shared/s0901}'::text[])) OR (((path)::text > '/shared/s0038/'::text) AND ((path)::text < '/shared/s00380'::text)) OR (((path)::text > '/shared/s0079/'::text) AND ((path)::text < '/shared/s00790'::text)) OR (((path)::text > '/shared/s0173/'::text) AND ((path)::text < '/shared/s01730'::text)) OR (((path)::text > '/shared/s0522/'::text) AND ((path)::text < '/shared/s05220'::text)) OR (((path)::text > '/shared/s0546/'::text) AND ((path)::text < '/shared/s05460'::text)) OR (((path)::text > '/shared/s0694/'::text) AND ((path)::text < '/shared/s06940'::text)) OR (((path)::text > '/shared/s0697/'::text) AND ((path)::text < '/shared/s06970'::text)) OR (((path)::text > '/shared/s0741/'::text) AND ((path)::text < '/shared/s07410'::text)) OR (((path)::text > '/shared/s0774/'::text) AND ((path)::text < '/shared/s07740'::text)) OR (((path)::text > '/shared/s0840/'::text) AND ((path)::text < '/shared/s08400'::text)) OR (((path)::text > '/shared/s0848/'::text) AND ((path)::text < '/shared/s08480'::text)) OR (((path)::text > '/shared/s0854/'::text) AND ((path)::text < '/shared/s08540'::text)) OR (((path)::text > '/shared/s0901/'::text) AND ((path)::text < '/shared/s09010'::text)) OR (((owner_id)::text = 'u000042'::text) AND (((path)::text = ANY ('{/home/u000044,/shared/s0022,/shared/s0025,/shared/s0028,/shared/s0038,/shared/s0048,/shared/s0079,/shared/s0099,/shared/s0100,/shared/s0108,/shared/s0173,/shared/s0174,/shared/s0341,/shared/s0342,/shared/s0416,/shared/s0422,/shared/s0431,/shared/s0511,/shared/s0522,/shared/s0537,/shared/s0546,/shared/s0566,/shared/s0573,/shared/s0585,/shared/s0618,/shared/s0667,/shared/s0679,/shared/s0694,/shared/s0697,/shared/s0724,/shared/s0739,/shared/s0741,/shared/s0774,/shared/s0810,/shared/s0840,/shared/s0848,/shared/s0854,/shared/s0898,/shared/s0901,/shared/s0910}'::text[])) OR (((path)::text > '/home/u000044/'::text) AND ((path)::text < '/home/u0000440'::text)) OR (((path)::text > '/shared/s0022/'::text) AND ((path)::text < '/shared/s00220'::text)) OR (((path)::text > '/shared/s0025/'::text) AND ((path)::text < '/shared/s00250'::text)) OR (((path)::text > '/shared/s0028/'::text) AND ((path)::text < '/shared/s00280'::text)) OR (((path)::text > '/shared/s0038/'::text) AND ((path)::text < '/shared/s00380'::text)) OR (((path)::text > '/shared/s0048/'::text) AND ((path)::text < '/shared/s00480'::text)) OR (((path)::text > '/shared/s0079/'::text) AND ((path)::text < '/shared/s00790'::text)) OR (((path)::text > '/shared/s0099/'::text) AND ((path)::text < '/shared/s00990'::text)) OR (((path)::text > '/shared/s0100/'::text) AND ((path)::text < '/shared/s01000'::text)) OR (((path)::text > '/shared/s0108/'::text) AND ((path)::text < '/shared/s01080'::text)) OR (((path)::text > '/shared/s0173/'::text) AND ((path)::text < '/shared/s01730'::text)) OR (((path)::text > '/shared/s0174/'::text) AND ((path)::text < '/shared/s01740'::text)) OR (((path)::text > '/shared/s0341/'::text) AND ((path)::text < '/shared/s03410'::text)) OR (((path)::text > '/shared/s0342/'::text) AND ((path)::text < '/shared/s03420'::text)) OR (((path)::text > '/shared/s0416/'::text) AND ((path)::text < '/shared/s04160'::text)) OR (((path)::text > '/shared/s0422/'::text) AND ((path)::text < '/shared/s04220'::text)) OR (((path)::text > '/shared/s0431/'::text) AND ((path)::text < '/shared/s04310'::text)) OR (((path)::text > '/shared/s0511/'::text) AND ((path)::text < '/shared/s05110'::text)) OR (((path)::text > '/shared/s0522/'::text) AND ((path)::text < '/shared/s05220'::text)) OR (((path)::text > '/shared/s0537/'::text) AND ((path)::text < '/shared/s05370'::text)) OR (((path)::text > '/shared/s0546/'::text) AND ((path)::text < '/shared/s05460'::text)) OR (((path)::text > '/shared/s0566/'::text) AND ((path)::text < '/shared/s05660'::text)) OR (((path)::text > '/shared/s0573/'::text) AND ((path)::text < '/shared/s05730'::text)) OR (((path)::text > '/shared/s0585/'::text) AND ((path)::text < '/shared/s05850'::text)) OR (((path)::text > '/shared/s0618/'::text) AND ((path)::text < '/shared/s06180'::text)) OR (((path)::text > '/shared/s0667/'::text) AND ((path)::text < '/shared/s06670'::text)) OR (((path)::text > '/shared/s0679/'::text) AND ((path)::text < '/shared/s06790'::text)) OR (((path)::text > '/shared/s0694/'::text) AND ((path)::text < '/shared/s06940'::text)) OR (((path)::text > '/shared/s0697/'::text) AND ((path)::text < '/shared/s06970'::text)) OR (((path)::text > '/shared/s0724/'::text) AND ((path)::text < '/shared/s07240'::text)) OR (((path)::text > '/shared/s0739/'::text) AND ((path)::text < '/shared/s07390'::text)) OR (((path)::text > '/shared/s0741/'::text) AND ((path)::text < '/shared/s07410'::text)) OR (((path)::text > '/shared/s0774/'::text) AND ((path)::text < '/shared/s07740'::text)) OR (((path)::text > '/shared/s0810/'::text) AND ((path)::text < '/shared/s08100'::text)) OR (((path)::text > '/shared/s0840/'::text) AND ((path)::text < '/shared/s08400'::text)) OR (((path)::text > '/shared/s0848/'::text) AND ((path)::text < '/shared/s08480'::text)) OR (((path)::text > '/shared/s0854/'::text) AND ((path)::text < '/shared/s08540'::text)) OR (((path)::text > '/shared/s0898/'::text) AND ((path)::text < '/shared/s08980'::text)) OR (((path)::text > '/shared/s0901/'::text) AND ((path)::text < '/shared/s09010'::text)) OR (((path)::text > '/shared/s0910/'::text) AND ((path)::text < '/shared/s09100'::text)))) OR (((owner_id)::text = 'u000044'::text) AND (((path)::text = ANY ('{/home/u000042,/shared/s0007,/shared/s0035,/shared/s0038,/shared/s0055,/shared/s0079,/shared/s0103,/shared/s0133,/shared/s0144,/shared/s0173,/shared/s0333,/shared/s0380,/shared/s0387,/shared/s0400,/shared/s0445,/shared/s0459,/shared/s0495,/shared/s0522,/shared/s0540,/shared/s0546,/shared/s0547,/shared/s0587,/shared/s0673,/shared/s0675,/shared/s0694,/shared/s0697,/shared/s0721,/shared/s0741,/shared/s0774,/shared/s0793,/shared/s0805,/shared/s0840,/shared/s0848,/shared/s0854,/shared/s0901,/shared/s0973}'::text[])) OR (((path)::text > '/home/u000042/'::text) AND ((path)::text < '/home/u0000420'::text)) OR (((path)::text > '/shared/s0007/'::text) AND ((path)::text < '/shared/s00070'::text)) OR (((path)::text > '/shared/s0035/'::text) AND ((path)::text < '/shared/s00350'::text)) OR (((path)::text > '/shared/s0038/'::text) AND ((path)::text < '/shared/s00380'::text)) OR (((path)::text > '/shared/s0055/'::text) AND ((path)::text < '/shared/s00550'::text)) OR (((path)::text > '/shared/s0079/'::text) AND ((path)::text < '/shared/s00790'::text)) OR (((path)::text > '/shared/s0103/'::text) AND ((path)::text < '/shared/s01030'::text)) OR (((path)::text > '/shared/s0133/'::text) AND ((path)::text < '/shared/s01330'::text)) OR (((path)::text > '/shared/s0144/'::text) AND ((path)::text < '/shared/s01440'::text)) OR (((path)::text > '/shared/s0173/'::text) AND ((path)::text < '/shared/s01730'::text)) OR (((path)::text > '/shared/s0333/'::text) AND ((path)::text < '/shared/s03330'::text)) OR (((path)::text > '/shared/s0380/'::text) AND ((path)::text < '/shared/s03800'::text)) OR (((path)::text > '/shared/s0387/'::text) AND ((path)::text < '/shared/s03870'::text)) OR (((path)::text > '/shared/s0400/'::text) AND ((path)::text < '/shared/s04000'::text)) OR (((path)::text > '/shared/s0445/'::text) AND ((path)::text < '/shared/s04450'::text)) OR (((path)::text > '/shared/s0459/'::text) AND ((path)::text < '/shared/s04590'::text)) OR (((path)::text > '/shared/s0495/'::text) AND ((path)::text < '/shared/s04950'::text)) OR (((path)::text > '/shared/s0522/'::text) AND ((path)::text < '/shared/s05220'::text)) OR (((path)::text > '/shared/s0540/'::text) AND ((path)::text < '/shared/s05400'::text)) OR (((path)::text > '/shared/s0546/'::text) AND ((path)::text < '/shared/s05460'::text)) OR (((path)::text > '/shared/s0547/'::text) AND ((path)::text < '/shared/s05470'::text)) OR (((path)::text > '/shared/s0587/'::text) AND ((path)::text < '/shared/s05870'::text)) OR (((path)::text > '/shared/s0673/'::text) AND ((path)::text < '/shared/s06730'::text)) OR (((path)::text > '/shared/s0675/'::text) AND ((path)::text < '/shared/s06750'::text)) OR (((path)::text > '/shared/s0694/'::text) AND ((path)::text < '/shared/s06940'::text)) OR (((path)::text > '/shared/s0697/'::text) AND ((path)::text < '/shared/s06970'::text)) OR (((path)::text > '/shared/s0721/'::text) AND ((path)::text < '/shared/s07210'::text)) OR (((path)::text > '/shared/s0741/'::text) AND ((path)::text < '/shared/s07410'::text)) OR (((path)::text > '/shared/s0774/'::text) AND ((path)::text < '/shared/s07740'::text)) OR (((path)::text > '/shared/s0793/'::text) AND ((path)::text < '/shared/s07930'::text)) OR (((path)::text > '/shared/s0805/'::text) AND ((path)::text < '/shared/s08050'::text)) OR (((path)::text > '/shared/s0840/'::text) AND ((path)::text < '/shared/s08400'::text)) OR (((path)::text > '/shared/s0848/'::text) AND ((path)::text < '/shared/s08480'::text)) OR (((path)::text > '/shared/s0854/'::text) AND ((path)::text < '/shared/s08540'::text)) OR (((path)::text > '/shared/s0901/'::text) AND ((path)::text < '/shared/s09010'::text)) OR (((path)::text > '/shared/s0973/'::text) AND ((path)::text < '/shared/s09730'::text)))))
        Rows Removed by Filter: 13
        Heap Blocks: exact=189
        Buffers: shared hit=2771
        ->  BitmapOr  (cost=6593.87..6593.87 rows=206082 width=0) (actual time=8.890..8.896 rows=0 loops=1)
              Buffers: shared hit=1090
              ->  Bitmap Index Scan on ts_1b272604_e_lvlpath  (cost=0.00..5593.62 rows=206025 width=0) (actual time=8.683..8.683 rows=201003 loops=1)
                    Index Cond: (everyone_level >= '1'::smallint)
                    Buffers: shared hit=993
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..57.69 rows=13 width=0) (actual time=0.050..0.050 rows=13 loops=1)
                    Index Cond: ((path)::text = ANY ('{/shared/s0038,/shared/s0079,/shared/s0173,/shared/s0522,/shared/s0546,/shared/s0694,/shared/s0697,/shared/s0741,/shared/s0774,/shared/s0840,/shared/s0848,/shared/s0854,/shared/s0901}'::text[]))
                    Buffers: shared hit=39
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.010..0.010 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0038/'::text) AND ((path)::text < '/shared/s00380'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.011..0.011 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0079/'::text) AND ((path)::text < '/shared/s00790'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.008..0.008 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0173/'::text) AND ((path)::text < '/shared/s01730'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.025..0.025 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0522/'::text) AND ((path)::text < '/shared/s05220'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.009..0.009 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0546/'::text) AND ((path)::text < '/shared/s05460'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.009..0.009 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0694/'::text) AND ((path)::text < '/shared/s06940'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.012..0.012 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0697/'::text) AND ((path)::text < '/shared/s06970'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.009..0.009 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0741/'::text) AND ((path)::text < '/shared/s07410'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.009..0.009 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0774/'::text) AND ((path)::text < '/shared/s07740'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.011..0.011 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0840/'::text) AND ((path)::text < '/shared/s08400'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.009..0.009 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0848/'::text) AND ((path)::text < '/shared/s08480'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.009..0.010 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0854/'::text) AND ((path)::text < '/shared/s08540'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_path  (cost=0.00..4.44 rows=1 width=0) (actual time=0.009..0.009 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0901/'::text) AND ((path)::text < '/shared/s09010'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on ts_1b272604_e_owner  (cost=0.00..4.59 rows=22 width=0) (actual time=0.010..0.010 rows=21 loops=1)
                    Index Cond: ((owner_id)::text = 'u000042'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on ts_1b272604_e_owner  (cost=0.00..4.59 rows=22 width=0) (actual time=0.003..0.003 rows=26 loops=1)
                    Index Cond: ((owner_id)::text = 'u000044'::text)
                    Buffers: shared hit=3
Planning:
  Buffers: shared hit=160
Planning Time: 1.228 ms
Execution Time: 40.530 ms
```

**two subjects / fenced / entries**

```
HashAggregate  (cost=424282.50..481860.20 rows=3232432 width=8) (actual time=79.517..150.718 rows=201003 loops=1)
  Group Key: e.id
  Planned Partitions: 64  Batches: 65  Memory Usage: 10769kB  Disk Usage: 4080kB
  Buffers: shared hit=2840, temp read=380 written=881
  ->  Append  (cost=5645.12..250539.28 rows=3232432 width=8) (actual time=5.104..40.769 rows=201003 loops=1)
        Buffers: shared hit=2840
        ->  Bitmap Heap Scan on ts_1b272604_e e  (cost=5645.12..27252.44 rows=206025 width=8) (actual time=5.103..23.977 rows=201003 loops=1)
              Recheck Cond: (everyone_level >= '1'::smallint)
              Heap Blocks: exact=1677
              Buffers: shared hit=2670
              ->  Bitmap Index Scan on ts_1b272604_e_lvlpath  (cost=0.00..5593.62 rows=206025 width=0) (actual time=4.967..4.967 rows=201003 loops=1)
                    Index Cond: (everyone_level >= '1'::smallint)
                    Buffers: shared hit=993
        ->  Nested Loop  (cost=0.43..109.98 rows=12 width=8) (actual time=0.090..0.091 rows=0 loops=1)
              Buffers: shared hit=52
              ->  Function Scan on unnest ap  (cost=0.00..0.13 rows=13 width=32) (actual time=0.014..0.015 rows=13 loops=1)
              ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_1  (cost=0.43..8.45 rows=1 width=29) (actual time=0.005..0.005 rows=0 loops=13)
                    Index Cond: ((path)::text = (ap.value)::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 1
                    Buffers: shared hit=52
        ->  Nested Loop  (cost=0.43..206841.85 rows=3026224 width=8) (actual time=0.287..0.287 rows=0 loops=1)
              Buffers: shared hit=88
              ->  Function Scan on ar  (cost=0.01..0.14 rows=13 width=64) (actual time=0.003..0.005 rows=13 loops=1)
              ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_2  (cost=0.43..13583.04 rows=232786 width=29) (actual time=0.021..0.021 rows=0 loops=13)
                    Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 200
                    Buffers: shared hit=88
        ->  Hash Join  (cost=1.33..36.86 rows=1 width=8) (actual time=0.032..0.033 rows=0 loops=1)
              Hash Cond: ((e_3.path)::text = (o0p.value)::text)
              Buffers: shared hit=5
              ->  Index Scan using ts_1b272604_e_owner on ts_1b272604_e e_3  (cost=0.43..35.88 rows=20 width=29) (actual time=0.011..0.014 rows=20 loops=1)
                    Index Cond: ((owner_id)::text = 'u000042'::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 1
                    Buffers: shared hit=5
              ->  Hash  (cost=0.40..0.40 rows=40 width=32) (actual time=0.009..0.010 rows=40 loops=1)
                    Buckets: 1024  Batches: 1  Memory Usage: 10kB
                    ->  Function Scan on unnest o0p  (cost=0.00..0.40 rows=40 width=32) (actual time=0.003..0.005 rows=40 loops=1)
        ->  Nested Loop  (cost=0.43..50.33 rows=89 width=8) (actual time=0.115..0.116 rows=0 loops=1)
              Join Filter: (((e_4.path)::text > (o0r.lo)::text) AND ((e_4.path)::text < (o0r.hi)::text))
              Rows Removed by Join Filter: 800
              Buffers: shared hit=5
              ->  Function Scan on o0r  (cost=0.01..0.41 rows=40 width=64) (actual time=0.004..0.008 rows=40 loops=1)
              ->  Materialize  (cost=0.43..35.98 rows=20 width=29) (actual time=0.000..0.001 rows=20 loops=40)
                    Buffers: shared hit=5
                    ->  Index Scan using ts_1b272604_e_owner on ts_1b272604_e e_4  (cost=0.43..35.88 rows=20 width=29) (actual time=0.003..0.006 rows=20 loops=1)
                          Index Cond: ((owner_id)::text = 'u000042'::text)
                          Filter: (everyone_level < '1'::smallint)
                          Rows Removed by Filter: 1
                          Buffers: shared hit=5
        ->  Hash Join  (cost=1.24..36.77 rows=1 width=8) (actual time=0.025..0.026 rows=0 loops=1)
              Hash Cond: ((e_5.path)::text = (o1p.value)::text)
              Buffers: shared hit=10
              ->  Index Scan using ts_1b272604_e_owner on ts_1b272604_e e_5  (cost=0.43..35.88 rows=20 width=29) (actual time=0.003..0.013 rows=20 loops=1)
                    Index Cond: ((owner_id)::text = 'u000044'::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 6
                    Buffers: shared hit=10
              ->  Hash  (cost=0.36..0.36 rows=36 width=32) (actual time=0.009..0.010 rows=36 loops=1)
                    Buckets: 1024  Batches: 1  Memory Usage: 10kB
                    ->  Function Scan on unnest o1p  (cost=0.00..0.36 rows=36 width=32) (actual time=0.003..0.005 rows=36 loops=1)
        ->  Nested Loop  (cost=0.43..48.89 rows=80 width=8) (actual time=0.097..0.098 rows=0 loops=1)
              Join Filter: (((e_6.path)::text > (o1r.lo)::text) AND ((e_6.path)::text < (o1r.hi)::text))
              Rows Removed by Join Filter: 720
              Buffers: shared hit=10
              ->  Function Scan on o1r  (cost=0.01..0.36 rows=36 width=64) (actual time=0.004..0.006 rows=36 loops=1)
              ->  Materialize  (cost=0.43..35.98 rows=20 width=29) (actual time=0.000..0.001 rows=20 loops=36)
                    Buffers: shared hit=10
                    ->  Index Scan using ts_1b272604_e_owner on ts_1b272604_e e_6  (cost=0.43..35.88 rows=20 width=29) (actual time=0.003..0.007 rows=20 loops=1)
                          Index Cond: ((owner_id)::text = 'u000044'::text)
                          Filter: (everyone_level < '1'::smallint)
                          Rows Removed by Filter: 6
                          Buffers: shared hit=10
Planning Time: 0.279 ms
Execution Time: 157.589 ms
```

**two subjects / disjoint / entries**

```
Append  (cost=5645.12..250550.71 rows=3232413 width=8) (actual time=31.147..67.708 rows=201003 loops=1)
  Buffers: shared hit=2840
  ->  Bitmap Heap Scan on ts_1b272604_e e  (cost=5645.12..27252.44 rows=206025 width=8) (actual time=31.145..50.306 rows=201003 loops=1)
        Recheck Cond: (everyone_level >= '1'::smallint)
        Heap Blocks: exact=1677
        Buffers: shared hit=2670
        ->  Bitmap Index Scan on ts_1b272604_e_lvlpath  (cost=0.00..5593.62 rows=206025 width=0) (actual time=4.819..4.819 rows=201003 loops=1)
              Index Cond: (everyone_level >= '1'::smallint)
              Buffers: shared hit=993
  ->  Nested Loop  (cost=0.43..109.98 rows=12 width=8) (actual time=0.168..0.169 rows=0 loops=1)
        Buffers: shared hit=52
        ->  Function Scan on unnest ap  (cost=0.00..0.13 rows=13 width=32) (actual time=0.084..0.085 rows=13 loops=1)
        ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_1  (cost=0.43..8.45 rows=1 width=29) (actual time=0.006..0.006 rows=0 loops=13)
              Index Cond: ((path)::text = (ap.value)::text)
              Filter: (everyone_level < '1'::smallint)
              Rows Removed by Filter: 1
              Buffers: shared hit=52
  ->  Nested Loop  (cost=0.43..206841.85 rows=3026224 width=8) (actual time=0.317..0.317 rows=0 loops=1)
        Buffers: shared hit=88
        ->  Function Scan on ar  (cost=0.01..0.14 rows=13 width=64) (actual time=0.006..0.007 rows=13 loops=1)
        ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_2  (cost=0.43..13583.04 rows=232786 width=29) (actual time=0.023..0.023 rows=0 loops=13)
              Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
              Filter: (everyone_level < '1'::smallint)
              Rows Removed by Filter: 200
              Buffers: shared hit=88
  ->  Nested Loop Anti Join  (cost=1.34..37.49 rows=1 width=8) (actual time=0.056..0.057 rows=0 loops=1)
        Join Filter: (((e_3.path)::text > (x0r.lo)::text) AND ((e_3.path)::text < (x0r.hi)::text))
        Buffers: shared hit=5
        ->  Nested Loop Anti Join  (cost=1.33..37.16 rows=1 width=29) (actual time=0.056..0.057 rows=0 loops=1)
              Join Filter: ((e_3.path)::text = (x0p.value)::text)
              Buffers: shared hit=5
              ->  Hash Join  (cost=1.33..36.86 rows=1 width=29) (actual time=0.056..0.056 rows=0 loops=1)
                    Hash Cond: ((e_3.path)::text = (o0p.value)::text)
                    Buffers: shared hit=5
                    ->  Index Scan using ts_1b272604_e_owner on ts_1b272604_e e_3  (cost=0.43..35.88 rows=20 width=29) (actual time=0.013..0.017 rows=20 loops=1)
                          Index Cond: ((owner_id)::text = 'u000042'::text)
                          Filter: (everyone_level < '1'::smallint)
                          Rows Removed by Filter: 1
                          Buffers: shared hit=5
                    ->  Hash  (cost=0.40..0.40 rows=40 width=32) (actual time=0.015..0.015 rows=40 loops=1)
                          Buckets: 1024  Batches: 1  Memory Usage: 10kB
                          ->  Function Scan on unnest o0p  (cost=0.00..0.40 rows=40 width=32) (actual time=0.005..0.007 rows=40 loops=1)
              ->  Function Scan on unnest x0p  (cost=0.00..0.13 rows=13 width=32) (never executed)
        ->  Function Scan on x0r  (cost=0.01..0.14 rows=13 width=64) (never executed)
  ->  Nested Loop  (cost=0.73..55.40 rows=79 width=8) (actual time=0.198..0.199 rows=0 loops=1)
        Join Filter: (((e_4.path)::text > (o0r.lo)::text) AND ((e_4.path)::text < (o0r.hi)::text))
        Rows Removed by Join Filter: 800
        Buffers: shared hit=5
        ->  Function Scan on o0r  (cost=0.01..0.41 rows=40 width=64) (actual time=0.006..0.009 rows=40 loops=1)
        ->  Materialize  (cost=0.73..42.44 rows=18 width=29) (actual time=0.001..0.003 rows=20 loops=40)
              Buffers: shared hit=5
              ->  Hash Anti Join  (cost=0.73..42.35 rows=18 width=29) (actual time=0.024..0.072 rows=20 loops=1)
                    Hash Cond: ((e_4.path)::text = (x0p_1.value)::text)
                    Buffers: shared hit=5
                    ->  Nested Loop Anti Join  (cost=0.43..41.82 rows=18 width=29) (actual time=0.014..0.058 rows=20 loops=1)
                          Join Filter: (((e_4.path)::text > (x0r_1.lo)::text) AND ((e_4.path)::text < (x0r_1.hi)::text))
                          Rows Removed by Join Filter: 260
                          Buffers: shared hit=5
                          ->  Index Scan using ts_1b272604_e_owner on ts_1b272604_e e_4  (cost=0.43..35.88 rows=20 width=29) (actual time=0.005..0.009 rows=20 loops=1)
                                Index Cond: ((owner_id)::text = 'u000042'::text)
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 1
                                Buffers: shared hit=5
                          ->  Function Scan on x0r_1  (cost=0.01..0.14 rows=13 width=64) (actual time=0.000..0.001 rows=13 loops=20)
                    ->  Hash  (cost=0.13..0.13 rows=13 width=32) (actual time=0.006..0.007 rows=13 loops=1)
                          Buckets: 1024  Batches: 1  Memory Usage: 9kB
                          ->  Function Scan on unnest x0p_1  (cost=0.00..0.13 rows=13 width=32) (actual time=0.002..0.003 rows=13 loops=1)
  ->  Nested Loop Anti Join  (cost=1.25..37.40 rows=1 width=8) (actual time=0.034..0.035 rows=0 loops=1)
        Join Filter: (((e_5.path)::text > (x1r.lo)::text) AND ((e_5.path)::text < (x1r.hi)::text))
        Buffers: shared hit=10
        ->  Nested Loop Anti Join  (cost=1.24..37.07 rows=1 width=29) (actual time=0.034..0.035 rows=0 loops=1)
              Join Filter: ((e_5.path)::text = (x1p.value)::text)
              Buffers: shared hit=10
              ->  Hash Join  (cost=1.24..36.77 rows=1 width=29) (actual time=0.034..0.034 rows=0 loops=1)
                    Hash Cond: ((e_5.path)::text = (o1p.value)::text)
                    Buffers: shared hit=10
                    ->  Index Scan using ts_1b272604_e_owner on ts_1b272604_e e_5  (cost=0.43..35.88 rows=20 width=29) (actual time=0.006..0.016 rows=20 loops=1)
                          Index Cond: ((owner_id)::text = 'u000044'::text)
                          Filter: (everyone_level < '1'::smallint)
                          Rows Removed by Filter: 6
                          Buffers: shared hit=10
                    ->  Hash  (cost=0.36..0.36 rows=36 width=32) (actual time=0.013..0.013 rows=36 loops=1)
                          Buckets: 1024  Batches: 1  Memory Usage: 10kB
                          ->  Function Scan on unnest o1p  (cost=0.00..0.36 rows=36 width=32) (actual time=0.006..0.009 rows=36 loops=1)
              ->  Function Scan on unnest x1p  (cost=0.00..0.13 rows=13 width=32) (never executed)
        ->  Function Scan on x1r  (cost=0.01..0.14 rows=13 width=64) (never executed)
  ->  Nested Loop  (cost=0.73..54.10 rows=71 width=8) (actual time=0.185..0.186 rows=0 loops=1)
        Join Filter: (((e_6.path)::text > (o1r.lo)::text) AND ((e_6.path)::text < (o1r.hi)::text))
        Rows Removed by Join Filter: 720
        Buffers: shared hit=10
        ->  Function Scan on o1r  (cost=0.01..0.36 rows=36 width=64) (actual time=0.006..0.008 rows=36 loops=1)
        ->  Materialize  (cost=0.73..42.44 rows=18 width=29) (actual time=0.001..0.003 rows=20 loops=36)
              Buffers: shared hit=10
              ->  Hash Anti Join  (cost=0.73..42.35 rows=18 width=29) (actual time=0.023..0.070 rows=20 loops=1)
                    Hash Cond: ((e_6.path)::text = (x1p_1.value)::text)
                    Buffers: shared hit=10
                    ->  Nested Loop Anti Join  (cost=0.43..41.82 rows=18 width=29) (actual time=0.014..0.058 rows=20 loops=1)
                          Join Filter: (((e_6.path)::text > (x1r_1.lo)::text) AND ((e_6.path)::text < (x1r_1.hi)::text))
                          Rows Removed by Join Filter: 260
                          Buffers: shared hit=10
                          ->  Index Scan using ts_1b272604_e_owner on ts_1b272604_e e_6  (cost=0.43..35.88 rows=20 width=29) (actual time=0.004..0.008 rows=20 loops=1)
                                Index Cond: ((owner_id)::text = 'u000044'::text)
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 6
                                Buffers: shared hit=10
                          ->  Function Scan on x1r_1  (cost=0.01..0.14 rows=13 width=64) (actual time=0.000..0.001 rows=13 loops=20)
                    ->  Hash  (cost=0.13..0.13 rows=13 width=32) (actual time=0.006..0.006 rows=13 loops=1)
                          Buckets: 1024  Batches: 1  Memory Usage: 9kB
                          ->  Function Scan on unnest x1p_1  (cost=0.00..0.13 rows=13 width=32) (actual time=0.002..0.003 rows=13 loops=1)
Planning Time: 0.447 ms
JIT:
  Functions: 118
  Options: Inlining false, Optimization false, Expressions true, Deforming true
  Timing: Generation 1.776 ms (Deform 0.729 ms), Inlining 0.000 ms, Optimization 0.901 ms, Emission 25.373 ms, Total 28.050 ms
Execution Time: 75.813 ms
```

**scoped / anonymous / union / IN**

```
Index Scan using ts_1b272604_e_path on ts_1b272604_e e  (cost=0.43..8.45 rows=1 width=8) (actual time=0.012..0.043 rows=200 loops=1)
  Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
  Filter: (everyone_level = ANY ('{1,2}'::smallint[]))
  Buffers: shared hit=7
Planning Time: 0.058 ms
Execution Time: 0.055 ms
```

**scoped / anonymous / union / >=**

```
Index Scan using ts_1b272604_e_path on ts_1b272604_e e  (cost=0.43..8.45 rows=1 width=8) (actual time=0.009..0.036 rows=200 loops=1)
  Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
  Filter: (everyone_level >= '1'::smallint)
  Buffers: shared hit=7
Planning:
  Buffers: shared hit=3
Planning Time: 0.081 ms
Execution Time: 0.049 ms
```

**scoped / ordinary / union / IN**

```
Unique  (cost=35.32..35.36 rows=7 width=8) (actual time=0.157..0.196 rows=200 loops=1)
  Buffers: shared hit=28
  ->  Sort  (cost=35.32..35.34 rows=7 width=8) (actual time=0.156..0.169 rows=200 loops=1)
        Sort Key: e.id
        Sort Method: quicksort  Memory: 25kB
        Buffers: shared hit=28
        ->  Append  (cost=0.43..35.22 rows=7 width=8) (actual time=0.014..0.139 rows=200 loops=1)
              Buffers: shared hit=28
              ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e  (cost=0.43..8.45 rows=1 width=8) (actual time=0.013..0.045 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: (everyone_level = ANY ('{1,2}'::smallint[]))
                    Buffers: shared hit=7
              ->  Hash Join  (cost=8.47..8.92 rows=1 width=8) (actual time=0.031..0.032 rows=0 loops=1)
                    Hash Cond: ((ap.value)::text = (e_1.path)::text)
                    Buffers: shared hit=7
                    ->  Function Scan on unnest ap  (cost=0.00..0.36 rows=36 width=32) (actual time=0.005..0.005 rows=1 loops=1)
                    ->  Hash  (cost=8.45..8.45 rows=1 width=29) (actual time=0.021..0.022 rows=0 loops=1)
                          Buckets: 1024  Batches: 1  Memory Usage: 8kB
                          Buffers: shared hit=7
                          ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_1  (cost=0.43..8.45 rows=1 width=29) (actual time=0.021..0.021 rows=0 loops=1)
                                Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 200
                                Buffers: shared hit=7
              ->  Nested Loop  (cost=0.43..9.36 rows=4 width=8) (actual time=0.026..0.026 rows=0 loops=1)
                    Join Filter: (((e_2.path)::text > (ar.lo)::text) AND ((e_2.path)::text < (ar.hi)::text))
                    Buffers: shared hit=7
                    ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_2  (cost=0.43..8.45 rows=1 width=29) (actual time=0.025..0.025 rows=0 loops=1)
                          Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                          Filter: (everyone_level < '1'::smallint)
                          Rows Removed by Filter: 200
                          Buffers: shared hit=7
                    ->  Function Scan on ar  (cost=0.01..0.36 rows=36 width=64) (never executed)
              ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_3  (cost=0.43..8.46 rows=1 width=8) (actual time=0.020..0.020 rows=0 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: ((everyone_level < '1'::smallint) AND ((owner_id)::text = 'u000042'::text))
                    Rows Removed by Filter: 200
                    Buffers: shared hit=7
Planning Time: 0.174 ms
Execution Time: 0.236 ms
```

**scoped / ordinary / unionall / IN**

```
Unique  (cost=35.32..35.36 rows=7 width=8) (actual time=0.160..0.199 rows=200 loops=1)
  Buffers: shared hit=28
  ->  Sort  (cost=35.32..35.34 rows=7 width=8) (actual time=0.159..0.171 rows=200 loops=1)
        Sort Key: e.id
        Sort Method: quicksort  Memory: 25kB
        Buffers: shared hit=28
        ->  Append  (cost=0.43..35.22 rows=7 width=8) (actual time=0.015..0.147 rows=200 loops=1)
              Buffers: shared hit=28
              ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e  (cost=0.43..8.45 rows=1 width=8) (actual time=0.015..0.048 rows=200 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: (everyone_level = ANY ('{1,2}'::smallint[]))
                    Buffers: shared hit=7
              ->  Hash Join  (cost=8.47..8.92 rows=1 width=8) (actual time=0.038..0.039 rows=0 loops=1)
                    Hash Cond: ((ap.value)::text = (e_1.path)::text)
                    Buffers: shared hit=7
                    ->  Function Scan on unnest ap  (cost=0.00..0.36 rows=36 width=32) (actual time=0.007..0.007 rows=1 loops=1)
                    ->  Hash  (cost=8.45..8.45 rows=1 width=29) (actual time=0.026..0.027 rows=0 loops=1)
                          Buckets: 1024  Batches: 1  Memory Usage: 8kB
                          Buffers: shared hit=7
                          ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_1  (cost=0.43..8.45 rows=1 width=29) (actual time=0.026..0.026 rows=0 loops=1)
                                Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                                Filter: (everyone_level < '1'::smallint)
                                Rows Removed by Filter: 200
                                Buffers: shared hit=7
              ->  Nested Loop  (cost=0.43..9.36 rows=4 width=8) (actual time=0.021..0.021 rows=0 loops=1)
                    Join Filter: (((e_2.path)::text > (ar.lo)::text) AND ((e_2.path)::text < (ar.hi)::text))
                    Buffers: shared hit=7
                    ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_2  (cost=0.43..8.45 rows=1 width=29) (actual time=0.021..0.021 rows=0 loops=1)
                          Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                          Filter: (everyone_level < '1'::smallint)
                          Rows Removed by Filter: 200
                          Buffers: shared hit=7
                    ->  Function Scan on ar  (cost=0.01..0.36 rows=36 width=64) (never executed)
              ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_3  (cost=0.43..8.46 rows=1 width=8) (actual time=0.023..0.023 rows=0 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: ((everyone_level < '1'::smallint) AND ((owner_id)::text = 'u000042'::text))
                    Rows Removed by Filter: 200
                    Buffers: shared hit=7
Planning Time: 0.198 ms
Execution Time: 0.231 ms
```

**scoped / ordinary / literal / IN**

```
Index Scan using ts_1b272604_e_path on ts_1b272604_e e  (cost=0.52..8.73 rows=1 width=8) (actual time=0.013..0.043 rows=200 loops=1)
  Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
  Filter: ((everyone_level >= '1'::smallint) OR ((path)::text = ANY ('{/home/u000042,/shared/s0007,/shared/s0035,/shared/s0038,/shared/s0055,/shared/s0079,/shared/s0103,/shared/s0133,/shared/s0144,/shared/s0173,/shared/s0333,/shared/s0380,/shared/s0387,/shared/s0400,/shared/s0445,/shared/s0459,/shared/s0495,/shared/s0522,/shared/s0540,/shared/s0546,/shared/s0547,/shared/s0587,/shared/s0673,/shared/s0675,/shared/s0694,/shared/s0697,/shared/s0721,/shared/s0741,/shared/s0774,/shared/s0793,/shared/s0805,/shared/s0840,/shared/s0848,/shared/s0854,/shared/s0901,/shared/s0973}'::text[])) OR (((path)::text > '/home/u000042/'::text) AND ((path)::text < '/home/u0000420'::text)) OR (((path)::text > '/shared/s0007/'::text) AND ((path)::text < '/shared/s00070'::text)) OR (((path)::text > '/shared/s0035/'::text) AND ((path)::text < '/shared/s00350'::text)) OR (((path)::text > '/shared/s0038/'::text) AND ((path)::text < '/shared/s00380'::text)) OR (((path)::text > '/shared/s0055/'::text) AND ((path)::text < '/shared/s00550'::text)) OR (((path)::text > '/shared/s0079/'::text) AND ((path)::text < '/shared/s00790'::text)) OR (((path)::text > '/shared/s0103/'::text) AND ((path)::text < '/shared/s01030'::text)) OR (((path)::text > '/shared/s0133/'::text) AND ((path)::text < '/shared/s01330'::text)) OR (((path)::text > '/shared/s0144/'::text) AND ((path)::text < '/shared/s01440'::text)) OR (((path)::text > '/shared/s0173/'::text) AND ((path)::text < '/shared/s01730'::text)) OR (((path)::text > '/shared/s0333/'::text) AND ((path)::text < '/shared/s03330'::text)) OR (((path)::text > '/shared/s0380/'::text) AND ((path)::text < '/shared/s03800'::text)) OR (((path)::text > '/shared/s0387/'::text) AND ((path)::text < '/shared/s03870'::text)) OR (((path)::text > '/shared/s0400/'::text) AND ((path)::text < '/shared/s04000'::text)) OR (((path)::text > '/shared/s0445/'::text) AND ((path)::text < '/shared/s04450'::text)) OR (((path)::text > '/shared/s0459/'::text) AND ((path)::text < '/shared/s04590'::text)) OR (((path)::text > '/shared/s0495/'::text) AND ((path)::text < '/shared/s04950'::text)) OR (((path)::text > '/shared/s0522/'::text) AND ((path)::text < '/shared/s05220'::text)) OR (((path)::text > '/shared/s0540/'::text) AND ((path)::text < '/shared/s05400'::text)) OR (((path)::text > '/shared/s0546/'::text) AND ((path)::text < '/shared/s05460'::text)) OR (((path)::text > '/shared/s0547/'::text) AND ((path)::text < '/shared/s05470'::text)) OR (((path)::text > '/shared/s0587/'::text) AND ((path)::text < '/shared/s05870'::text)) OR (((path)::text > '/shared/s0673/'::text) AND ((path)::text < '/shared/s06730'::text)) OR (((path)::text > '/shared/s0675/'::text) AND ((path)::text < '/shared/s06750'::text)) OR (((path)::text > '/shared/s0694/'::text) AND ((path)::text < '/shared/s06940'::text)) OR (((path)::text > '/shared/s0697/'::text) AND ((path)::text < '/shared/s06970'::text)) OR (((path)::text > '/shared/s0721/'::text) AND ((path)::text < '/shared/s07210'::text)) OR (((path)::text > '/shared/s0741/'::text) AND ((path)::text < '/shared/s07410'::text)) OR (((path)::text > '/shared/s0774/'::text) AND ((path)::text < '/shared/s07740'::text)) OR (((path)::text > '/shared/s0793/'::text) AND ((path)::text < '/shared/s07930'::text)) OR (((path)::text > '/shared/s0805/'::text) AND ((path)::text < '/shared/s08050'::text)) OR (((path)::text > '/shared/s0840/'::text) AND ((path)::text < '/shared/s08400'::text)) OR (((path)::text > '/shared/s0848/'::text) AND ((path)::text < '/shared/s08480'::text)) OR (((path)::text > '/shared/s0854/'::text) AND ((path)::text < '/shared/s08540'::text)) OR (((path)::text > '/shared/s0901/'::text) AND ((path)::text < '/shared/s09010'::text)) OR (((path)::text > '/shared/s0973/'::text) AND ((path)::text < '/shared/s09730'::text)) OR ((owner_id)::text = 'u000042'::text))
  Buffers: shared hit=7
Planning:
  Buffers: shared hit=64
Planning Time: 0.559 ms
Execution Time: 0.095 ms
```

**scoped / ordinary / disjoint / IN**

```
Append  (cost=0.43..36.60 rows=7 width=8) (actual time=0.012..0.152 rows=200 loops=1)
  Buffers: shared hit=28
  ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e  (cost=0.43..8.45 rows=1 width=8) (actual time=0.012..0.045 rows=200 loops=1)
        Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
        Filter: (everyone_level = ANY ('{1,2}'::smallint[]))
        Buffers: shared hit=7
  ->  Hash Join  (cost=8.47..8.92 rows=1 width=8) (actual time=0.030..0.031 rows=0 loops=1)
        Hash Cond: ((ap.value)::text = (e_1.path)::text)
        Buffers: shared hit=7
        ->  Function Scan on unnest ap  (cost=0.00..0.36 rows=36 width=32) (actual time=0.006..0.006 rows=1 loops=1)
        ->  Hash  (cost=8.45..8.45 rows=1 width=29) (actual time=0.020..0.020 rows=0 loops=1)
              Buckets: 1024  Batches: 1  Memory Usage: 8kB
              Buffers: shared hit=7
              ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_1  (cost=0.43..8.45 rows=1 width=29) (actual time=0.020..0.020 rows=0 loops=1)
                    Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 200
                    Buffers: shared hit=7
  ->  Nested Loop  (cost=0.43..9.36 rows=4 width=8) (actual time=0.021..0.021 rows=0 loops=1)
        Join Filter: (((e_2.path)::text > (ar.lo)::text) AND ((e_2.path)::text < (ar.hi)::text))
        Buffers: shared hit=7
        ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_2  (cost=0.43..8.45 rows=1 width=29) (actual time=0.020..0.021 rows=0 loops=1)
              Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
              Filter: (everyone_level < '1'::smallint)
              Rows Removed by Filter: 200
              Buffers: shared hit=7
        ->  Function Scan on ar  (cost=0.01..0.36 rows=36 width=64) (never executed)
  ->  Nested Loop Anti Join  (cost=8.47..9.83 rows=1 width=8) (actual time=0.030..0.031 rows=0 loops=1)
        Join Filter: (((e_3.path)::text > (x0r.lo)::text) AND ((e_3.path)::text < (x0r.hi)::text))
        Buffers: shared hit=7
        ->  Hash Right Anti Join  (cost=8.47..8.92 rows=1 width=29) (actual time=0.030..0.031 rows=0 loops=1)
              Hash Cond: ((x0p.value)::text = (e_3.path)::text)
              Buffers: shared hit=7
              ->  Function Scan on unnest x0p  (cost=0.00..0.36 rows=36 width=32) (never executed)
              ->  Hash  (cost=8.46..8.46 rows=1 width=29) (actual time=0.027..0.027 rows=0 loops=1)
                    Buckets: 1024  Batches: 1  Memory Usage: 8kB
                    Buffers: shared hit=7
                    ->  Index Scan using ts_1b272604_e_path on ts_1b272604_e e_3  (cost=0.43..8.46 rows=1 width=29) (actual time=0.027..0.027 rows=0 loops=1)
                          Index Cond: (((path)::text > '/shared/s0001/'::text) AND ((path)::text < '/shared/s00010'::text))
                          Filter: ((everyone_level < '1'::smallint) AND ((owner_id)::text = 'u000042'::text))
                          Rows Removed by Filter: 200
                          Buffers: shared hit=7
        ->  Function Scan on x0r  (cost=0.01..0.36 rows=36 width=64) (never executed)
Planning Time: 0.182 ms
Execution Time: 0.200 ms
```

Total wall time 193s.
