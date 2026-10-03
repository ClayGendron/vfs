# postgres — N = 1,000

World: {'users': 1000, 'groups': 5, 'shared': 10, 'grant_rows': 2141, 'memberships': 5000, 'entries': 23213, 'files_per_home': 20, 'files_per_shared': 200}
Load: {'entries_s': 0.7098724590614438, 'grants_s': 0.05844979174435139, 'analyze_s': 0.05845116684213281}

## 1. Resolution (ms)

| caller | cold resolve_authority | warm hit | pure resolve(read) | everyone_arms | rows read | read arms | holes | owner arms |
|---|---|---|---|---|---|---|---|---|
| ordinary | 13.44 | 1.6 | 2.79 | 0.97 | 1043 | 2 | 1000 | 1 |
| heavy (u000986) | 12.57 | 1.39 | 2.97 | 0.99 | 1045 | 2 | 1000 | 1 |
| pair | 12.81 | 1.24 | 3.3 | 1.08 | 1044 | 1 | 1000 | 2 |
| anonymous | 7.62 | 1.36 | 1.1 | 0.96 | 1001 | 1 | 1000 | 0 |
| system | 0.02 | 0.0 | — | — | — | 1 | 0 | 0 |

## 2. ranges()/pieces (read rights)

| caller | shipped pieces ms | linear pieces ms | equal | points | opens | owner pieces | bind bytes |
|---|---|---|---|---|---|---|---|
| ordinary | 111.16 | 1.32 | True | 1000 | 1999 | 2 | 91,925 |
| heavy (u000986) | 113.49 | 1.56 | True | 1000 | 1999 | 2 | 91,925 |
| pair | 116.68 | 1.31 | True | 1001 | 2001 | 4 | 92,017 |
| anonymous | 114.07 | 1.35 | True | 1001 | 2001 | 0 | 92,017 |

## 3. Range join (visible_entries)

| caller | count cold ms | count warm ms | count | fetch cold ms | fetch warm ms | rows |
|---|---|---|---|---|---|---|
| ordinary | 320.58 | 233.64 | 2234 | 218.33 | 219.76 | 2234 |
| heavy (u000986) | 241.1 | 9.85 | 2234 | 266.05 | 20.47 | 2234 |
| pair | 424.01 | 361.91 | 2213 | 340.64 | 357.25 | 2213 |
| anonymous | 99.66 | 96.84 | 2213 | 112.98 | 100.58 | 2213 |

Recall (ordinary): {'sample_rows': 1221, 'oracle_agrees_with_admits': True, 'admits_sample_s': 0.02, 'exact_visible': 2234, 'stored': 23213, 'join_rows': 2234, 'recall': 1.0, 'extra': 0}

Plan of the ordinary caller's count statement:

```
Aggregate  (cost=631488.41..631488.42 rows=1 width=8) (actual time=243.841..243.849 rows=1 loops=1)
  Buffers: shared hit=5156
  ->  Hash Join  (cost=503128.28..618596.24 rows=5156868 width=0) (actual time=242.737..243.727 rows=2234 loops=1)
        Hash Cond: (bl_947a3101_1.entry_id = bl_947a3101.entry_id)
        Buffers: shared hit=5156
        ->  HashAggregate  (cost=502106.98..604035.70 rows=5156868 width=16) (actual time=9.629..10.053 rows=2234 loops=1)
              Group Key: bl_947a3101_1.entry_id
              Planned Partitions: 128  Batches: 1  Memory Usage: 1681kB
              Buffers: shared hit=4657
              ->  Append  (cost=1021.30..184637.30 rows=5156868 width=16) (actual time=5.345..8.938 rows=2254 loops=1)
                    Buffers: shared hit=4657
                    ->  Hash Join  (cost=1021.30..1033.92 rows=1000 width=16) (actual time=5.342..5.553 rows=1 loops=1)
                          Hash Cond: ((anon_1.value)::text = (bl_947a3101_1.path)::text)
                          Buffers: shared hit=499
                          ->  Function Scan on unnest anon_1  (cost=0.00..10.00 rows=1000 width=32) (actual time=0.067..0.123 rows=1000 loops=1)
                          ->  Hash  (cost=731.13..731.13 rows=23213 width=40) (actual time=5.219..5.220 rows=23213 loops=1)
                                Buckets: 32768  Batches: 1  Memory Usage: 1897kB
                                Buffers: shared hit=499
                                ->  Seq Scan on bl_947a3101 bl_947a3101_1  (cost=0.00..731.13 rows=23213 width=40) (actual time=0.016..2.195 rows=23213 loops=1)
                                      Buffers: shared hit=499
                    ->  Nested Loop  (cost=0.29..157801.34 rows=5155865 width=16) (actual time=0.194..3.045 rows=2233 loops=1)
                          Buffers: shared hit=4152
                          ->  Function Scan on anon_2  (cost=0.01..20.00 rows=1999 width=64) (actual time=0.168..0.357 rows=1999 loops=1)
                          ->  Index Scan using ix_bl_947a3101_path on bl_947a3101 bl_947a3101_2  (cost=0.29..53.14 rows=2579 width=40) (actual time=0.001..0.001 rows=1 loops=1999)
                                Index Cond: (((path)::text > (anon_2.lo)::text) AND ((path)::text < (anon_2.hi)::text))
                                Buffers: shared hit=4152
                    ->  Hash Join  (cost=0.31..8.75 rows=1 width=16) (actual time=0.077..0.078 rows=0 loops=1)
                          Hash Cond: ((bl_947a3101_3.path)::text = (anon_3.value)::text)
                          Buffers: shared hit=3
                          ->  Index Scan using ix_bl_947a3101_owner_id on bl_947a3101 bl_947a3101_3  (cost=0.29..8.64 rows=20 width=40) (actual time=0.013..0.015 rows=20 loops=1)
                                Index Cond: ((owner_id)::text = 'u000007'::text)
                                Buffers: shared hit=3
                          ->  Hash  (cost=0.01..0.01 rows=1 width=32) (actual time=0.043..0.044 rows=1 loops=1)
                                Buckets: 1024  Batches: 1  Memory Usage: 9kB
                                ->  Function Scan on unnest anon_3  (cost=0.00..0.01 rows=1 width=32) (actual time=0.039..0.039 rows=1 loops=1)
                    ->  Nested Loop  (cost=0.29..8.95 rows=2 width=16) (actual time=0.014..0.019 rows=20 loops=1)
                          Join Filter: (((bl_947a3101_4.path)::text > (anon_4.lo)::text) AND ((bl_947a3101_4.path)::text < (anon_4.hi)::text))
                          Buffers: shared hit=3
                          ->  Function Scan on anon_4  (cost=0.01..0.01 rows=1 width=64) (actual time=0.005..0.005 rows=1 loops=1)
                          ->  Index Scan using ix_bl_947a3101_owner_id on bl_947a3101 bl_947a3101_4  (cost=0.29..8.64 rows=20 width=40) (actual time=0.004..0.006 rows=20 loops=1)
                                Index Cond: ((owner_id)::text = 'u000007'::text)
                                Buffers: shared hit=3
        ->  Hash  (cost=731.13..731.13 rows=23213 width=16) (actual time=233.096..233.097 rows=23213 loops=1)
              Buckets: 32768  Batches: 1  Memory Usage: 1345kB
              Buffers: shared hit=499
              ->  Seq Scan on bl_947a3101  (cost=0.00..731.13 rows=23213 width=16) (actual time=228.660..230.680 rows=23213 loops=1)
                    Buffers: shared hit=499
Planning Time: 0.281 ms
JIT:
  Functions: 53
  Options: Inlining true, Optimization true, Expressions true, Deforming true
  Timing: Generation 0.977 ms (Deform 0.510 ms), Inlining 6.764 ms, Optimization 132.523 ms, Emission 89.485 ms, Total 229.749 ms
Execution Time: 245.023 ms
```

## 4. Clause fan (visibility_clauses)

| caller | clauses | build ms | clause binds | clause terms | cold ms | warm ms | result |
|---|---|---|---|---|---|---|---|
| ordinary | 1 | 19.99 | 2003 | 4007 | 1444.3 | 1297.2 | 2234 |
| pair | 1 | 21.11 | 2006 | 4012 | 1417.22 | 1320.7 | 2213 |
| anonymous | 1 | 22.07 | 2000 | 4000 | 311.75 | 242.86 | 2213 |

## 5. End to end through DatabaseStorage (ms; cold = first call in a fresh process, warm = second)

| caller | verb | cold ms | warm ms | rows | note |
|---|---|---|---|---|---|
| ordinary | tree / | 606.67 | 398.77 | 2233 |  |
| ordinary | glob /shared/*/*.md | 81.95 | 60.01 | 2000 |  |
| ordinary | ls /home | 61.0 | 31.06 | 101 |  |
| pair | tree / | 717.76 | 508.87 | 2212 |  |
| pair | glob /shared/*/*.md | 80.26 | 59.58 | 2000 |  |
| pair | ls /home | 61.22 | 33.67 | 100 |  |
| anonymous | tree / | 425.7 | 250.11 | 2212 |  |
| anonymous | glob /shared/*/*.md | 68.99 | 58.08 | 2000 |  |
| anonymous | ls /home | 37.59 | 22.83 | 100 |  |
| system | tree / | 208.17 | 160.44 | 23212 |  |
| system | glob /shared/*/*.md | 20.56 | 21.45 | 2000 |  |
| system | ls /home | 20.96 | 15.07 | 1100 |  |

## 6. Cache churn: {'cached_before': 20, 'callers': 20, 'misses_after_one_grant': 20, 'recompute_s_for_callers': 0.277, 'cache_capacity': 256}

## 7. Memory: {'resolution_bytes': 72491, 'with_read_ranges_bytes': 426845, 'x256_cache_mb': 109.3}

## 8. Rights.admits per row (ordinary)

- own home file: 0.9 µs (admitted=True)
- shared file (root arm): 20.4 µs (admitted=True)
- another user's home file (hidden): 12.1 µs (admitted=False)
- trap file: 18.4 µs (admitted=True)

Total wall time 26.2s.
