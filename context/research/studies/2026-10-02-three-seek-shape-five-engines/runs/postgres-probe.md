## postgres probe — N=100,000, ordinary caller (72 pieces), disjoint shape; warm = median of 3

Load 52s.

| knobs | statement | cold / warm / recall |
|---|---|---|
| pg_nudge=False | entries | 345 / 530 / exact |
| pg_nudge=False | scoped | 4.2 / 1.8 / exact |
| pg_nudge=False | count | 358 / 329 / exact |
| pg_nudge=False | top10 | 1,178 / 1,178 / exact |
| pg_nudge=True | entries | 528 / 530 / exact |
| pg_nudge=True | scoped | 4.5 / 1.8 / exact |
| pg_nudge=True | count | 200 / 184 / exact |
| pg_nudge=True | top10 | 1,149 / 1,142 / exact |

**pg_nudge=False / entries**

```
Append  (cost=5376.45..482951.22 rows=8616070 width=8) (actual time=12.756..47.707 rows=201024 loops=1)
  Buffers: shared hit=3061
  ->  Bitmap Heap Scan on ts_5af4f51e_e e  (cost=5376.45..26860.08 rows=196131 width=8) (actual time=12.755..31.058 rows=201003 loops=1)
        Recheck Cond: (everyone_level >= '1'::smallint)
        Heap Blocks: exact=1677
        Buffers: shared hit=2670
        ->  Bitmap Index Scan on ts_5af4f51e_e_lvlpath  (cost=0.00..5327.41 rows=196131 width=0) (actual time=4.595..4.596 rows=201003 loops=1)
              Index Cond: (everyone_level >= '1'::smallint)
              Buffers: shared hit=993
  ->  Nested Loop  (cost=0.43..304.56 rows=33 width=8) (actual time=0.086..0.184 rows=1 loops=1)
        Buffers: shared hit=144
        ->  Function Scan on unnest ap  (cost=0.00..0.36 rows=36 width=32) (actual time=0.060..0.062 rows=36 loops=1)
        ->  Index Scan using ts_5af4f51e_e_path on ts_5af4f51e_e e_1  (cost=0.43..8.45 rows=1 width=29) (actual time=0.003..0.003 rows=0 loops=36)
              Index Cond: ((path)::text = (ap.value)::text)
              Filter: (everyone_level < '1'::smallint)
              Rows Removed by Filter: 1
              Buffers: shared hit=144
  ->  Nested Loop  (cost=0.43..412653.99 rows=8419888 width=8) (actual time=0.015..0.789 rows=20 loops=1)
        Buffers: shared hit=242
        ->  Function Scan on ar  (cost=0.01..0.36 rows=36 width=64) (actual time=0.006..0.009 rows=36 loops=1)
        ->  Index Scan using ts_5af4f51e_e_path on ts_5af4f51e_e e_2  (cost=0.43..9123.74 rows=233886 width=29) (actual time=0.021..0.021 rows=1 loops=36)
              Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
              Filter: (everyone_level < '1'::smallint)
              Rows Removed by Filter: 194
              Buffers: shared hit=242
  ->  Hash Anti Join  (cost=1.25..52.24 rows=18 width=8) (actual time=0.029..0.030 rows=0 loops=1)
        Hash Cond: ((e_3.path)::text = (x0p.value)::text)
        Buffers: shared hit=5
        ->  Nested Loop Anti Join  (cost=0.43..51.20 rows=18 width=29) (actual time=0.028..0.028 rows=0 loops=1)
              Join Filter: (((e_3.path)::text > (x0r.lo)::text) AND ((e_3.path)::text < (x0r.hi)::text))
              Buffers: shared hit=5
              ->  Index Scan using ts_5af4f51e_e_owner on ts_5af4f51e_e e_3  (cost=0.43..34.90 rows=20 width=29) (actual time=0.011..0.015 rows=20 loops=1)
                    Index Cond: ((owner_id)::text = 'u000042'::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 1
                    Buffers: shared hit=5
              ->  Function Scan on x0r  (cost=0.01..0.36 rows=36 width=64) (actual time=0.000..0.000 rows=1 loops=20)
        ->  Hash  (cost=0.36..0.36 rows=36 width=32) (never executed)
              ->  Function Scan on unnest x0p  (cost=0.00..0.36 rows=36 width=32) (never executed)
Planning Time: 0.228 ms
JIT:
  Functions: 40
  Options: Inlining false, Optimization false, Expressions true, Deforming true
  Timing: Generation 0.578 ms (Deform 0.240 ms), Inlining 0.000 ms, Optimization 0.334 ms, Emission 7.738 ms, Total 8.650 ms
Execution Time: 54.451 ms
```

**pg_nudge=False / count**

```
Finalize Aggregate  (cost=564278.45..564278.46 rows=1 width=8) (actual time=387.943..398.253 rows=1 loops=1)
  Buffers: shared hit=7948 read=9193, temp read=7795 written=7924
  ->  Gather  (cost=564278.24..564278.45 rows=2 width=8) (actual time=386.554..398.235 rows=3 loops=1)
        Workers Planned: 2
        Workers Launched: 2
        Buffers: shared hit=7948 read=9193, temp read=7795 written=7924
        ->  Partial Aggregate  (cost=563278.24..563278.25 rows=1 width=8) (actual time=376.476..376.481 rows=1 loops=3)
              Buffers: shared hit=7948 read=9193, temp read=7795 written=7924
              ->  Parallel Hash Join  (cost=38219.44..554303.16 rows=3590029 width=0) (actual time=325.470..373.662 rows=66673 loops=3)
                    Hash Cond: (e.id = c.entry_id)
                    Buffers: shared hit=7948 read=9193, temp read=7795 written=7924
                    ->  Parallel Append  (cost=0.43..456034.09 rows=3590029 width=8) (actual time=1.743..16.992 rows=67008 loops=3)
                          Buffers: shared hit=3064
                          ->  Nested Loop  (cost=0.43..412653.99 rows=8419888 width=8) (actual time=0.096..0.815 rows=20 loops=1)
                                Buffers: shared hit=243
                                ->  Function Scan on ar  (cost=0.01..0.36 rows=36 width=64) (actual time=0.056..0.060 rows=36 loops=1)
                                ->  Index Scan using ts_5af4f51e_e_path on ts_5af4f51e_e e  (cost=0.43..9123.74 rows=233886 width=29) (actual time=0.020..0.020 rows=1 loops=36)
                                      Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 194
                                      Buffers: shared hit=243
                          ->  Nested Loop  (cost=0.43..304.56 rows=33 width=8) (actual time=0.076..0.262 rows=1 loops=1)
                                Buffers: shared hit=145
                                ->  Function Scan on unnest ap  (cost=0.00..0.36 rows=36 width=32) (actual time=0.045..0.047 rows=36 loops=1)
                                ->  Index Scan using ts_5af4f51e_e_path on ts_5af4f51e_e e_1  (cost=0.43..8.45 rows=1 width=29) (actual time=0.006..0.006 rows=0 loops=36)
                                      Index Cond: ((path)::text = (ap.value)::text)
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 1
                                      Buffers: shared hit=145
                          ->  Hash Anti Join  (cost=1.25..52.24 rows=18 width=8) (actual time=0.045..0.046 rows=0 loops=1)
                                Hash Cond: ((e_2.path)::text = (x0p.value)::text)
                                Buffers: shared hit=6
                                ->  Nested Loop Anti Join  (cost=0.43..51.20 rows=18 width=29) (actual time=0.044..0.044 rows=0 loops=1)
                                      Join Filter: (((e_2.path)::text > (x0r.lo)::text) AND ((e_2.path)::text < (x0r.hi)::text))
                                      Buffers: shared hit=6
                                      ->  Index Scan using ts_5af4f51e_e_owner on ts_5af4f51e_e e_2  (cost=0.43..34.90 rows=20 width=29) (actual time=0.023..0.029 rows=20 loops=1)
                                            Index Cond: ((owner_id)::text = 'u000042'::text)
                                            Filter: (everyone_level < '1'::smallint)
                                            Rows Removed by Filter: 1
                                            Buffers: shared hit=6
                                      ->  Function Scan on x0r  (cost=0.01..0.36 rows=36 width=64) (actual time=0.000..0.000 rows=1 loops=20)
                                ->  Hash  (cost=0.36..0.36 rows=36 width=32) (never executed)
                                      ->  Function Scan on unnest x0p  (cost=0.00..0.36 rows=36 width=32) (never executed)
                          ->  Parallel Bitmap Heap Scan on ts_5af4f51e_e e_3  (cost=5376.45..25429.96 rows=81721 width=8) (actual time=4.610..11.232 rows=67001 loops=3)
                                Recheck Cond: (everyone_level >= '1'::smallint)
                                Heap Blocks: exact=560
                                Buffers: shared hit=2670
                                ->  Bitmap Index Scan on ts_5af4f51e_e_lvlpath  (cost=0.00..5327.41 rows=196131 width=0) (actual time=4.853..4.853 rows=201003 loops=1)
                                      Index Cond: (everyone_level >= '1'::smallint)
                                      Buffers: shared hit=993
                    ->  Parallel Hash  (cost=23179.67..23179.67 rows=916667 width=8) (actual time=291.971..291.971 rows=733333 loops=3)
                          Buckets: 262144  Batches: 16  Memory Usage: 7456kB
                          Buffers: shared hit=4820 read=9193, temp written=7156
                          ->  Parallel Seq Scan on ts_5af4f51e_c c  (cost=0.00..23179.67 rows=916667 width=8) (actual time=143.031..204.895 rows=733333 loops=3)
                                Buffers: shared hit=4820 read=9193
Planning Time: 0.276 ms
JIT:
  Functions: 149
  Options: Inlining true, Optimization true, Expressions true, Deforming true
  Timing: Generation 2.562 ms (Deform 0.932 ms), Inlining 104.843 ms, Optimization 176.505 ms, Emission 147.933 ms, Total 431.843 ms
Execution Time: 399.138 ms
```

**pg_nudge=True / entries**

```
Append  (cost=5376.45..403306.20 rows=238281 width=8) (actual time=12.493..47.534 rows=201024 loops=1)
  Buffers: shared hit=3061
  ->  Bitmap Heap Scan on ts_5af4f51e_e e  (cost=5376.45..26860.08 rows=196131 width=8) (actual time=12.493..30.814 rows=201003 loops=1)
        Recheck Cond: (everyone_level >= '1'::smallint)
        Heap Blocks: exact=1677
        Buffers: shared hit=2670
        ->  Bitmap Index Scan on ts_5af4f51e_e_lvlpath  (cost=0.00..5327.41 rows=196131 width=0) (actual time=4.557..4.557 rows=201003 loops=1)
              Index Cond: (everyone_level >= '1'::smallint)
              Buffers: shared hit=993
  ->  Nested Loop  (cost=0.43..304.56 rows=33 width=8) (actual time=0.065..0.160 rows=1 loops=1)
        Buffers: shared hit=144
        ->  Function Scan on unnest ap  (cost=0.00..0.36 rows=36 width=32) (actual time=0.046..0.048 rows=36 loops=1)
        ->  Index Scan using ts_5af4f51e_e_path on ts_5af4f51e_e e_1  (cost=0.43..8.45 rows=1 width=29) (actual time=0.003..0.003 rows=0 loops=36)
              Index Cond: ((path)::text = (ap.value)::text)
              Filter: (everyone_level < '1'::smallint)
              Rows Removed by Filter: 1
              Buffers: shared hit=144
  ->  Nested Loop  (cost=0.43..374897.91 rows=42099 width=8) (actual time=0.016..0.767 rows=20 loops=1)
        Buffers: shared hit=242
        ->  Function Scan on ar  (cost=0.01..0.36 rows=36 width=64) (actual time=0.006..0.009 rows=36 loops=1)
        ->  Index Scan using ts_5af4f51e_e_path on ts_5af4f51e_e e_2  (cost=0.43..10402.13 rows=1169 width=29) (actual time=0.021..0.021 rows=1 loops=36)
              Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
              Filter: ((everyone_level < '1'::smallint) AND ((path)::text ~~ ((ar.lo)::text || '%'::text)))
              Rows Removed by Filter: 194
              Buffers: shared hit=242
  ->  Hash Anti Join  (cost=1.25..52.24 rows=18 width=8) (actual time=0.025..0.026 rows=0 loops=1)
        Hash Cond: ((e_3.path)::text = (x0p.value)::text)
        Buffers: shared hit=5
        ->  Nested Loop Anti Join  (cost=0.43..51.20 rows=18 width=29) (actual time=0.024..0.025 rows=0 loops=1)
              Join Filter: (((e_3.path)::text > (x0r.lo)::text) AND ((e_3.path)::text < (x0r.hi)::text))
              Buffers: shared hit=5
              ->  Index Scan using ts_5af4f51e_e_owner on ts_5af4f51e_e e_3  (cost=0.43..34.90 rows=20 width=29) (actual time=0.009..0.012 rows=20 loops=1)
                    Index Cond: ((owner_id)::text = 'u000042'::text)
                    Filter: (everyone_level < '1'::smallint)
                    Rows Removed by Filter: 1
                    Buffers: shared hit=5
              ->  Function Scan on x0r  (cost=0.01..0.36 rows=36 width=64) (actual time=0.000..0.000 rows=1 loops=20)
        ->  Hash  (cost=0.36..0.36 rows=36 width=32) (never executed)
              ->  Function Scan on unnest x0p  (cost=0.00..0.36 rows=36 width=32) (never executed)
Planning Time: 0.203 ms
JIT:
  Functions: 40
  Options: Inlining false, Optimization false, Expressions true, Deforming true
  Timing: Generation 0.636 ms (Deform 0.243 ms), Inlining 0.000 ms, Optimization 0.322 ms, Emission 7.519 ms, Total 8.477 ms
Execution Time: 54.302 ms
```

**pg_nudge=True / count**

```
Finalize Aggregate  (cost=445434.70..445434.71 rows=1 width=8) (actual time=233.057..242.960 rows=1 loops=1)
  Buffers: shared hit=8751 read=8390, temp read=7785 written=7904
  ->  Gather  (cost=445434.49..445434.70 rows=2 width=8) (actual time=232.614..242.946 rows=3 loops=1)
        Workers Planned: 2
        Workers Launched: 2
        Buffers: shared hit=8751 read=8390, temp read=7785 written=7904
        ->  Partial Aggregate  (cost=444434.49..444434.50 rows=1 width=8) (actual time=223.092..223.097 rows=1 loops=3)
              Buffers: shared hit=8751 read=8390, temp read=7785 written=7904
              ->  Parallel Hash Join  (cost=38219.44..444186.28 rows=99284 width=0) (actual time=180.467..219.592 rows=66673 loops=3)
                    Hash Cond: (e.id = c.entry_id)
                    Buffers: shared hit=8751 read=8390, temp read=7785 written=7904
                    ->  Parallel Append  (cost=0.43..400824.28 rows=99283 width=8) (actual time=1.611..16.291 rows=67008 loops=3)
                          Buffers: shared hit=3064
                          ->  Nested Loop  (cost=0.43..374897.91 rows=42099 width=8) (actual time=0.082..1.011 rows=20 loops=1)
                                Buffers: shared hit=243
                                ->  Function Scan on ar  (cost=0.01..0.36 rows=36 width=64) (actual time=0.046..0.050 rows=36 loops=1)
                                ->  Index Scan using ts_5af4f51e_e_path on ts_5af4f51e_e e  (cost=0.43..10402.13 rows=1169 width=29) (actual time=0.026..0.026 rows=1 loops=36)
                                      Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                                      Filter: ((everyone_level < '1'::smallint) AND ((path)::text ~~ ((ar.lo)::text || '%'::text)))
                                      Rows Removed by Filter: 194
                                      Buffers: shared hit=243
                          ->  Nested Loop  (cost=0.43..304.56 rows=33 width=8) (actual time=0.066..0.255 rows=1 loops=1)
                                Buffers: shared hit=145
                                ->  Function Scan on unnest ap  (cost=0.00..0.36 rows=36 width=32) (actual time=0.037..0.040 rows=36 loops=1)
                                ->  Index Scan using ts_5af4f51e_e_path on ts_5af4f51e_e e_1  (cost=0.43..8.45 rows=1 width=29) (actual time=0.006..0.006 rows=0 loops=36)
                                      Index Cond: ((path)::text = (ap.value)::text)
                                      Filter: (everyone_level < '1'::smallint)
                                      Rows Removed by Filter: 1
                                      Buffers: shared hit=145
                          ->  Hash Anti Join  (cost=1.25..52.24 rows=18 width=8) (actual time=0.046..0.048 rows=0 loops=1)
                                Hash Cond: ((e_2.path)::text = (x0p.value)::text)
                                Buffers: shared hit=6
                                ->  Nested Loop Anti Join  (cost=0.43..51.20 rows=18 width=29) (actual time=0.045..0.046 rows=0 loops=1)
                                      Join Filter: (((e_2.path)::text > (x0r.lo)::text) AND ((e_2.path)::text < (x0r.hi)::text))
                                      Buffers: shared hit=6
                                      ->  Index Scan using ts_5af4f51e_e_owner on ts_5af4f51e_e e_2  (cost=0.43..34.90 rows=20 width=29) (actual time=0.026..0.029 rows=20 loops=1)
                                            Index Cond: ((owner_id)::text = 'u000042'::text)
                                            Filter: (everyone_level < '1'::smallint)
                                            Rows Removed by Filter: 1
                                            Buffers: shared hit=6
                                      ->  Function Scan on x0r  (cost=0.01..0.36 rows=36 width=64) (actual time=0.001..0.001 rows=1 loops=20)
                                ->  Hash  (cost=0.36..0.36 rows=36 width=32) (never executed)
                                      ->  Function Scan on unnest x0p  (cost=0.00..0.36 rows=36 width=32) (never executed)
                          ->  Parallel Bitmap Heap Scan on ts_5af4f51e_e e_3  (cost=5376.45..25429.96 rows=81721 width=8) (actual time=4.172..10.615 rows=67001 loops=3)
                                Recheck Cond: (everyone_level >= '1'::smallint)
                                Heap Blocks: exact=564
                                Buffers: shared hit=2670
                                ->  Bitmap Index Scan on ts_5af4f51e_e_lvlpath  (cost=0.00..5327.41 rows=196131 width=0) (actual time=4.501..4.501 rows=201003 loops=1)
                                      Index Cond: (everyone_level >= '1'::smallint)
                                      Buffers: shared hit=993
                    ->  Parallel Hash  (cost=23179.67..23179.67 rows=916667 width=8) (actual time=149.750..149.750 rows=733333 loops=3)
                          Buckets: 262144  Batches: 16  Memory Usage: 7456kB
                          Buffers: shared hit=5623 read=8390, temp written=7136
                          ->  Parallel Seq Scan on ts_5af4f51e_c c  (cost=0.00..23179.67 rows=916667 width=8) (actual time=9.663..66.888 rows=733333 loops=3)
                                Buffers: shared hit=5623 read=8390
Planning:
  Buffers: shared hit=5
Planning Time: 0.252 ms
JIT:
  Functions: 149
  Options: Inlining false, Optimization false, Expressions true, Deforming true
  Timing: Generation 2.738 ms (Deform 0.966 ms), Inlining 0.000 ms, Optimization 1.061 ms, Emission 28.069 ms, Total 31.868 ms
Execution Time: 243.858 ms
```

