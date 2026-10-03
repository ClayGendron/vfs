# postgres — N = 10,000

World: {'users': 10000, 'groups': 50, 'shared': 100, 'grant_rows': 21401, 'memberships': 50000, 'entries': 230303, 'files_per_home': 20, 'files_per_shared': 200}
Load: {'entries_s': 5.767232541926205, 'grants_s': 0.43577633425593376, 'analyze_s': 0.14364133309572935}

## 1. Resolution (ms)

| caller | cold resolve_authority | warm hit | pure resolve(read) | everyone_arms | rows read | read arms | holes | owner arms |
|---|---|---|---|---|---|---|---|---|
| ordinary | 121.76 | 1.4 | 66.71 | 11.51 | 10037 | 2 | 10000 | 1 |
| heavy (u005437) | 144.68 | 1.28 | 87.21 | 11.92 | 10063 | 2 | 10000 | 1 |
| pair | 70.96 | 1.27 | 34.2 | 11.53 | 10085 | 1 | 10000 | 2 |
| anonymous | 46.74 | 1.26 | 12.38 | 11.49 | 10001 | 1 | 10000 | 0 |
| system | 0.01 | 0.0 | — | — | — | 1 | 0 | 0 |

## 2. ranges()/pieces (read rights)

| caller | shipped pieces ms | linear pieces ms | equal | points | opens | owner pieces | bind bytes |
|---|---|---|---|---|---|---|---|
| ordinary | 17892.2 | 17.47 | True | 10000 | 19999 | 2 | 919,925 |
| heavy (u005437) | 17347.46 | 14.17 | True | 10000 | 19999 | 2 | 919,925 |
| pair | 17670.19 | 14.81 | True | 10001 | 20001 | 98 | 920,017 |
| anonymous | 17519.92 | 17.6 | True | 10001 | 20001 | 0 | 920,017 |

## 3. Range join (visible_entries)

| caller | count cold ms | count warm ms | count | fetch cold ms | fetch warm ms | rows |
|---|---|---|---|---|---|---|
| ordinary | 387.14 | 313.48 | 20324 | 407.64 | 384.34 | 20324 |
| heavy (u005437) | 341.44 | 113.8 | 20324 | 406.33 | 154.1 | 20324 |
| pair | 484.2 | 505.89 | 20303 | 556.09 | 544.29 | 20303 |
| anonymous | 253.06 | 256.96 | 20303 | 358.17 | 302.2 | 20303 |

Recall (ordinary): {'sample_rows': 1221, 'oracle_agrees_with_admits': True, 'admits_sample_s': 0.11, 'exact_visible': 20324, 'stored': 230303, 'join_rows': 20324, 'recall': 1.0, 'extra': 0}

Plan of the ordinary caller's count statement:

```
Aggregate  (cost=102436871.43..102436871.44 rows=1 width=8) (actual time=340.752..340.761 rows=1 loops=1)
  Buffers: shared hit=62100 read=4242, temp read=1859 written=1859
  ->  Hash Join  (cost=79701988.23..101157449.29 rows=511768858 width=0) (actual time=327.291..339.906 rows=20324 loops=1)
        Hash Cond: (bl_2d8153d2_1.entry_id = bl_2d8153d2.entry_id)
        Buffers: shared hit=62100 read=4242, temp read=1859 written=1859
        ->  HashAggregate  (cost=79690973.48..94804147.56 rows=511768858 width=16) (actual time=103.455..105.494 rows=20324 loops=1)
              Group Key: bl_2d8153d2_1.entry_id
              Planned Partitions: 256  Batches: 1  Memory Usage: 2577kB
              Buffers: shared hit=61214 read=4242, temp read=1308 written=1308
              ->  Append  (cost=11840.82..17958854.98 rows=511768858 width=16) (actual time=63.577..100.369 rows=20344 loops=1)
                    Buffers: shared hit=61214 read=4242, temp read=1308 written=1308
                    ->  Hash Join  (cost=11840.82..13905.07 rows=10000 width=16) (actual time=63.575..71.733 rows=1 loops=1)
                          Hash Cond: ((anon_1.value)::text = (bl_2d8153d2_1.path)::text)
                          Buffers: shared hit=617 read=4242, temp read=1308 written=1308
                          ->  Function Scan on unnest anon_1  (cost=0.00..100.00 rows=10000 width=32) (actual time=0.392..0.928 rows=10000 loops=1)
                          ->  Hash  (cost=7162.03..7162.03 rows=230303 width=40) (actual time=57.920..57.921 rows=230303 loops=1)
                                Buckets: 131072  Batches: 4  Memory Usage: 5106kB
                                Buffers: shared hit=617 read=4242, temp written=1272
                                ->  Seq Scan on bl_2d8153d2 bl_2d8153d2_1  (cost=0.00..7162.03 rows=230303 width=40) (actual time=0.015..24.010 rows=230303 loops=1)
                                      Buffers: shared hit=617 read=4242
                    ->  Nested Loop  (cost=0.42..15386087.91 rows=511758855 width=16) (actual time=1.718..26.967 rows=20323 loops=1)
                          Buffers: shared hit=60591
                          ->  Function Scan on anon_2  (cost=0.01..200.00 rows=19999 width=64) (actual time=1.675..3.201 rows=19999 loops=1)
                          ->  Index Scan using ix_bl_2d8153d2_path on bl_2d8153d2 bl_2d8153d2_2  (cost=0.42..513.44 rows=25589 width=40) (actual time=0.001..0.001 rows=1 loops=19999)
                                Index Cond: (((path)::text > (anon_2.lo)::text) AND ((path)::text < (anon_2.hi)::text))
                                Buffers: shared hit=60591
                    ->  Hash Join  (cost=0.32..8.76 rows=1 width=16) (actual time=0.065..0.066 rows=0 loops=1)
                          Hash Cond: ((bl_2d8153d2_3.path)::text = (anon_3.value)::text)
                          Buffers: shared hit=3
                          ->  Index Scan using ix_bl_2d8153d2_owner_id on bl_2d8153d2 bl_2d8153d2_3  (cost=0.29..8.64 rows=20 width=40) (actual time=0.016..0.018 rows=20 loops=1)
                                Index Cond: ((owner_id)::text = 'u000007'::text)
                                Buffers: shared hit=3
                          ->  Hash  (cost=0.01..0.01 rows=1 width=32) (actual time=0.034..0.035 rows=1 loops=1)
                                Buckets: 1024  Batches: 1  Memory Usage: 9kB
                                ->  Function Scan on unnest anon_3  (cost=0.00..0.01 rows=1 width=32) (actual time=0.027..0.028 rows=1 loops=1)
                    ->  Nested Loop  (cost=0.30..8.96 rows=2 width=16) (actual time=0.017..0.031 rows=20 loops=1)
                          Join Filter: (((bl_2d8153d2_4.path)::text > (anon_4.lo)::text) AND ((bl_2d8153d2_4.path)::text < (anon_4.hi)::text))
                          Buffers: shared hit=3
                          ->  Function Scan on anon_4  (cost=0.01..0.01 rows=1 width=64) (actual time=0.005..0.005 rows=1 loops=1)
                          ->  Index Scan using ix_bl_2d8153d2_owner_id on bl_2d8153d2 bl_2d8153d2_4  (cost=0.29..8.64 rows=20 width=40) (actual time=0.003..0.013 rows=20 loops=1)
                                Index Cond: ((owner_id)::text = 'u000007'::text)
                                Buffers: shared hit=3
        ->  Hash  (cost=7010.97..7010.97 rows=230303 width=16) (actual time=223.756..223.757 rows=230303 loops=1)
              Buckets: 262144  Batches: 2  Memory Usage: 7453kB
              Buffers: shared hit=886, temp written=505
              ->  Index Only Scan using ix_bl_2d8153d2_entry_id on bl_2d8153d2  (cost=0.42..7010.97 rows=230303 width=16) (actual time=0.016..15.988 rows=230303 loops=1)
                    Heap Fetches: 0
                    Buffers: shared hit=886
Planning Time: 0.643 ms
JIT:
  Functions: 51
  Options: Inlining true, Optimization true, Expressions true, Deforming true
  Timing: Generation 1.219 ms (Deform 0.679 ms), Inlining 8.362 ms, Optimization 98.853 ms, Emission 72.499 ms, Total 180.934 ms
Execution Time: 342.909 ms
```

## 4. Clause fan (visibility_clauses)

| caller | clauses | build ms | clause binds | clause terms | cold ms | warm ms | result |
|---|---|---|---|---|---|---|---|
| ordinary | 2 | 239.17 | 20000 | 40000 | None | None | None |
| ordinary | 2 | 239.17 | 3 | 7 | None | None | None |
| pair | 2 | 282.04 | 20000 | 40000 | None | None | None |
| pair | 2 | 282.04 | 100 | 200 | None | None | None |
| anonymous | 1 | 191.73 | 20000 | 40000 | None | None | None |

## 5. End to end through DatabaseStorage (ms; cold = first call in a fresh process, warm = second)

| caller | verb | cold ms | warm ms | rows | note |
|---|---|---|---|---|---|
| ordinary | tree / | 21115.43 | 5021.24 | 20323 |  |
| ordinary | glob /shared/*/*.md | 4086.5 | 3967.35 | 20000 |  |
| ordinary | ls /home | 1053.94 | 914.56 | 101 |  |
| pair | tree / | 21320.16 | 4837.21 | 20302 |  |
| pair | glob /shared/*/*.md | 4019.52 | 3956.38 | 20000 |  |
| pair | ls /home | 932.8 | 857.23 | 100 |  |
| anonymous | tree / | 20690.37 | 4622.96 | 20302 |  |
| anonymous | glob /shared/*/*.md | 4006.92 | 3924.32 | 20000 |  |
| anonymous | ls /home | 800.88 | 776.45 | 100 |  |
| system | tree / | 1870.37 | 3214.29 | 230302 |  |
| system | glob /shared/*/*.md | 171.02 | 151.22 | 20000 |  |
| system | ls /home | 89.14 | 126.53 | 10100 |  |

## 6. Cache churn: {'cached_before': 20, 'callers': 20, 'misses_after_one_grant': 20, 'recompute_s_for_callers': 2.611, 'cache_capacity': 256}

## 7. Memory: {'resolution_bytes': 702491, 'with_read_ranges_bytes': 4242845, 'x256_cache_mb': 1086.2}

## 8. Rights.admits per row (ordinary)

- own home file: 0.8 µs (admitted=True)
- shared file (root arm): 187.7 µs (admitted=True)
- another user's home file (hidden): 109.8 µs (admitted=False)
- trap file: 169.0 µs (admitted=True)

Total wall time 217.5s.
