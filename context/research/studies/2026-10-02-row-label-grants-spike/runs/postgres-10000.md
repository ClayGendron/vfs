## postgres — N=10,000 users: 230,203 entries, 660,000 chunks (3/file), 11,400 grant rows, 10,101 posture rows, 10,201 domains

Load: rows in 1.2s.

### Indexes

| index | build s | size |
|---|---|---|
| e_path | 0.1 | 9.3 MB |
| e_owner | 0.1 | 1.8 MB |
| e_public | 0.1 | 1.6 MB |
| e_public_path | 0.1 | 9.3 MB |
| e_domain | 0.1 | 1.8 MB |
| c_entry | 0.2 | 10.9 MB |
| c_score | 0.2 | 14.9 MB |
| d_path | 0.0 | 0.3 MB |
| d_public | 0.0 | 0.1 MB |
| g_principal | 0.0 | 0.3 MB |
| m_principal | 0.0 | 0.6 MB |
| (entries table itself) | | 18.0 MB |

Truth computed in Python in 1.5s.
### Callers

| caller | subjects | grants held | visible entries | shipped `Rights.admits` on a sample |
|---|---|---|---|---|
| ordinary | u000042 | 49 | 20,124 | 5,000 rows, 0 disagreements; shipped resolve 139 ms (2 arms, 10,100 holes), admits 114 us/row |
| heavy group | u000003 | 46 | 20,124 | 5,000 rows, 0 disagreements; shipped resolve 115 ms (2 arms, 10,100 holes), admits 114 us/row |
| two subjects | u000042, u000032 | 104 | 20,103 | 5,000 rows, 0 disagreements; shipped resolve 87 ms (1 arms, 10,100 holes), admits 102 us/row |
| anonymous | — | 0 | 20,103 | 5,000 rows, 0 disagreements; shipped resolve 17 ms (1 arms, 10,100 holes), admits 101 us/row |
| system | — | 0 | 230,203 | skipped (system) |

### Compile per caller (the caller's own grants → sorted pieces)

| caller | level | points | opens | owner pieces | bind bytes | compile us (median of 200) | grants fetch cold ms | warm ms |
|---|---|---|---|---|---|---|---|---|
| ordinary | read | 44 | 44 | 0 | 2,445 | 30 | 16.6 | 8.8 |
| ordinary | read_write | 11 | 11 | 0 | 630 | 23 | 5.9 | 4.0 |
| heavy group | read | 44 | 44 | 0 | 2,445 | 27 | 9.8 | 7.5 |
| heavy group | read_write | 5 | 5 | 0 | 300 | 5 | 11.6 | 9.2 |
| two subjects | read | 21 | 21 | 178 | 6,094 | 96 | 14.6 | 10.1 |
| two subjects | read_write | 0 | 0 | 40 | 1,148 | 21 | 11.9 | 9.2 |

### Domain lists (the `domain_id` variant's compile, one SQL statement)

| caller | domains in list | bind bytes | cold ms | warm ms |
|---|---|---|---|---|
| ordinary | 102 | 707 | 10.3 | 5.6 |
| heavy group | 102 | 706 | 10.7 | 4.7 |
| two subjects | 101 | 703 | 8.1 | 5.0 |
| anonymous | 101 | 703 | 3.5 | 1.7 |

### Statements — cold = fresh connection, warm = median of 3 (ms); recall against the Python truth

| caller | statement | public: cold / warm / recall | domain: cold / warm / recall |
|---|---|---|---|
| ordinary | entries | 94.3 / 77.7 / exact | 50.0 / 27.5 / exact |
| ordinary | scoped | 11.1 / 5.6 / exact | 32.7 / 6.0 / exact |
| ordinary | count | 171 / 98.8 / exact | 65.0 / 46.7 / exact |
| ordinary | top10 | 88.2 / 59.9 / exact | 36.4 / 28.0 / exact |
| ordinary | top10 probe | 6.9 / 2.4 / exact | 14.8 / 1.9 / exact |
| heavy group | entries | 78.6 / 20.9 / exact | 20.6 / 12.3 / exact |
| heavy group | scoped | 4.0 / 2.3 / exact | 10.4 / 1.5 / exact |
| heavy group | count | 83.5 / 69.5 / exact | 36.2 / 26.1 / exact |
| heavy group | top10 | 65.5 / 54.1 / exact | 37.0 / 25.8 / exact |
| heavy group | top10 probe | 4.9 / 2.2 / exact | 12.4 / 1.7 / exact |
| two subjects | entries | 17.0 / 14.4 / exact | 22.6 / 12.1 / exact |
| two subjects | scoped | 4.8 / 2.5 / exact | 11.9 / 1.9 / exact |
| two subjects | count | 46.5 / 43.6 / exact | 37.3 / 25.9 / exact |
| two subjects | top10 | 76.4 / 60.6 / exact | 37.4 / 28.4 / exact |
| two subjects | top10 probe | 4.8 / 2.1 / exact | 12.8 / 2.0 / exact |
| anonymous | entries | 54.7 / 9.3 / exact | 19.3 / 10.3 / exact |
| anonymous | scoped | 3.2 / 1.9 / exact | 10.9 / 1.5 / exact |
| anonymous | count | 27.2 / 25.0 / exact | 36.0 / 22.9 / exact |
| anonymous | top10 | 5.2 / 1.7 / exact | 11.9 / 1.5 / exact |
| anonymous | top10 probe | 4.4 / 1.7 / exact | 12.8 / 2.0 / exact |
| system | entries | 220 / 233 / exact | — |
| system | scoped | 3.2 / 1.5 / exact | — |
| system | count | 56.4 / 52.2 / exact | — |
| system | top10 | 4.6 / 4.3 / exact | — |
| system | top10 probe | 9.1 / 4.3 / exact | — |

### Cache invalidation at this N

One cached caller recomputes by fetching its grant rows and merging them: about 6.03 ms warm here (fetch 6.0 ms + compile 30 us).

| write | global revision invalidates | per-principal / per-group / posture revisions invalidate | recompute at global (ms) | at granular (ms) |
|---|---|---|---|---|
| grant to one user | 10,000 | 1 | 60,266 | 6 |
| grant to a typical group | 10,000 | 1,007 | 60,266 | 6,069 |
| grant to the heavy group | 10,000 | 979 | 60,266 | 5,900 |
| posture change (any subtree) | 10,000 | 0 | 60,266 | 0 |

Under the row-label shape a posture change invalidates no compiled rights: the posture is on the rows, not in the caller's pieces. The relabel UPDATE is its cost (see the writes run).

### Plans (ordinary caller)

**public / entries**

```
HashAggregate  (cost=115405.40..135809.21 rows=1145477 width=8) (actual time=20.575..22.643 rows=20124 loops=1)
  Group Key: e.id
  Planned Partitions: 16  Batches: 1  Memory Usage: 4113kB
  Buffers: shared hit=695
  ->  Append  (cost=0.29..53836.01 rows=1145477 width=8) (actual time=9.081..15.770 rows=28791 loops=1)
        Buffers: shared hit=695
        ->  Index Scan using rl_362c6575_e_public on rl_362c6575_e e  (cost=0.29..615.84 rows=19974 width=8) (actual time=9.080..11.358 rows=20103 loops=1)
              Index Cond: (public_level >= '1'::smallint)
              Buffers: shared hit=209
        ->  Nested Loop  (cost=0.42..371.69 rows=44 width=8) (actual time=0.055..0.152 rows=44 loops=1)
              Buffers: shared hit=176
              ->  Function Scan on unnest ap  (cost=0.00..0.44 rows=44 width=32) (actual time=0.033..0.036 rows=44 loops=1)
              ->  Index Scan using rl_362c6575_e_path on rl_362c6575_e e_1  (cost=0.42..8.44 rows=1 width=29) (actual time=0.002..0.002 rows=1 loops=44)
                    Index Cond: (path = (ap.value)::text)
                    Buffers: shared hit=176
        ->  Nested Loop  (cost=0.42..47085.89 rows=1125437 width=8) (actual time=0.017..1.958 rows=8620 loops=1)
              Buffers: shared hit=303
              ->  Function Scan on ar  (cost=0.01..0.45 rows=44 width=64) (actual time=0.008..0.012 rows=44 loops=1)
              ->  Index Scan using rl_362c6575_e_path on rl_362c6575_e e_2  (cost=0.42..814.34 rows=25578 width=29) (actual time=0.003..0.024 rows=196 loops=44)
                    Index Cond: ((path > (ar.lo)::text) AND (path < (ar.hi)::text))
                    Buffers: shared hit=303
        ->  Index Scan using rl_362c6575_e_owner on rl_362c6575_e e_3  (cost=0.29..35.21 rows=22 width=8) (actual time=0.031..0.036 rows=24 loops=1)
              Index Cond: (owner_id = 'u000042'::text)
              Buffers: shared hit=7
Planning Time: 0.172 ms
JIT:
  Functions: 26
  Options: Inlining false, Optimization false, Expressions true, Deforming true
  Timing: Generation 0.377 ms (Deform 0.131 ms), Inlining 0.000 ms, Optimization 0.218 ms, Emission 8.886 ms, Total 9.481 ms
Execution Time: 23.780 ms
```

**domain / entries**

```
HashAggregate  (cost=1023.00..1223.38 rows=20038 width=8) (actual time=6.276..7.828 rows=20124 loops=1)
  Group Key: e.id
  Batches: 1  Memory Usage: 1809kB
  Buffers: shared hit=218
  ->  Append  (cost=0.29..972.91 rows=20038 width=8) (actual time=0.018..3.804 rows=20148 loops=1)
        Buffers: shared hit=218
        ->  Index Scan using rl_362c6575_e_domain on rl_362c6575_e e  (cost=0.29..837.51 rows=20016 width=8) (actual time=0.018..2.213 rows=20124 loops=1)
              Index Cond: (domain_id = ANY ('{1,86,10102,10103,10104,10105,10106,10107,10108,10109,10110,10111,10112,10113,10114,10115,10116,10117,10118,10119,10120,10121,10122,10123,10124,10125,10126,10127,10128,10129,10130,10131,10132,10133,10134,10135,10136,10137,10138,10139,10140,10141,10142,10143,10144,10145,10146,10147,10148,10149,10150,10151,10152,10153,10154,10155,10156,10157,10158,10159,10160,10161,10162,10163,10164,10165,10166,10167,10168,10169,10170,10171,10172,10173,10174,10175,10176,10177,10178,10179,10180,10181,10182,10183,10184,10185,10186,10187,10188,10189,10190,10191,10192,10193,10194,10195,10196,10197,10198,10199,10200,10201}'::bigint[]))
              Buffers: shared hit=211
        ->  Index Scan using rl_362c6575_e_owner on rl_362c6575_e e_1  (cost=0.29..35.21 rows=22 width=8) (actual time=0.013..0.019 rows=24 loops=1)
              Index Cond: (owner_id = 'u000042'::text)
              Buffers: shared hit=7
Planning Time: 0.191 ms
Execution Time: 8.548 ms
```

**public / count**

```
Finalize Aggregate  (cost=173463.79..173463.80 rows=1 width=8) (actual time=117.657..117.742 rows=1 loops=1)
  Buffers: shared hit=4861 read=1504, temp read=2171 written=2171
  ->  Gather  (cost=173463.57..173463.78 rows=2 width=8) (actual time=117.636..117.734 rows=3 loops=1)
        Workers Planned: 2
        Workers Launched: 2
        Buffers: shared hit=4861 read=1504, temp read=2171 written=2171
        ->  Partial Aggregate  (cost=172463.57..172463.58 rows=1 width=8) (actual time=89.486..89.492 rows=1 loops=3)
              Buffers: shared hit=4861 read=1504, temp read=2171 written=2171
              ->  Hash Join  (cost=154602.67..168907.56 rows=1422407 width=0) (actual time=47.214..88.344 rows=20020 loops=3)
                    Hash Cond: (c.entry_id = e.id)
                    Buffers: shared hit=4861 read=1504, temp read=2171 written=2171
                    ->  Parallel Seq Scan on rl_362c6575_c c  (cost=0.00..6958.00 rows=275000 width=8) (actual time=9.731..28.279 rows=220000 loops=3)
                          Buffers: shared hit=2704 read=1504
                    ->  Hash  (cost=135809.21..135809.21 rows=1145477 width=8) (actual time=17.700..17.704 rows=20124 loops=3)
                          Buckets: 262144  Batches: 8  Memory Usage: 2145kB
                          Buffers: shared hit=2091, temp written=168
                          ->  HashAggregate  (cost=115405.40..135809.21 rows=1145477 width=8) (actual time=12.870..15.011 rows=20124 loops=3)
                                Group Key: e.id
                                Planned Partitions: 16  Batches: 1  Memory Usage: 4113kB
                                Buffers: shared hit=2091
                                Worker 0:  Batches: 1  Memory Usage: 4113kB
                                Worker 1:  Batches: 1  Memory Usage: 4113kB
                                ->  Append  (cost=0.29..53836.01 rows=1145477 width=8) (actual time=0.039..6.966 rows=28791 loops=3)
                                      Buffers: shared hit=2091
                                      ->  Index Scan using rl_362c6575_e_public on rl_362c6575_e e  (cost=0.29..615.84 rows=19974 width=8) (actual time=0.038..2.381 rows=20103 loops=3)
                                            Index Cond: (public_level >= '1'::smallint)
                                            Buffers: shared hit=629
                                      ->  Nested Loop  (cost=0.42..371.69 rows=44 width=8) (actual time=0.069..0.185 rows=44 loops=3)
                                            Buffers: shared hit=530
                                            ->  Function Scan on unnest ap  (cost=0.00..0.44 rows=44 width=32) (actual time=0.039..0.041 rows=44 loops=3)
                                            ->  Index Scan using rl_362c6575_e_path on rl_362c6575_e e_1  (cost=0.42..8.44 rows=1 width=29) (actual time=0.003..0.003 rows=1 loops=132)
                                                  Index Cond: (path = (ap.value)::text)
                                                  Buffers: shared hit=530
                                      ->  Nested Loop  (cost=0.42..47085.89 rows=1125437 width=8) (actual time=0.042..2.069 rows=8620 loops=3)
                                            Buffers: shared hit=909
                                            ->  Function Scan on ar  (cost=0.01..0.45 rows=44 width=64) (actual time=0.030..0.035 rows=44 loops=3)
                                            ->  Index Scan using rl_362c6575_e_path on rl_362c6575_e e_2  (cost=0.42..814.34 rows=25578 width=29) (actual time=0.004..0.026 rows=196 loops=132)
                                                  Index Cond: ((path > (ar.lo)::text) AND (path < (ar.hi)::text))
                                                  Buffers: shared hit=909
                                      ->  Index Scan using rl_362c6575_e_owner on rl_362c6575_e e_3  (cost=0.29..35.21 rows=22 width=8) (actual time=0.056..0.063 rows=24 loops=3)
                                            Index Cond: (owner_id = 'u000042'::text)
                                            Buffers: shared hit=23
Planning Time: 0.424 ms
JIT:
  Functions: 107
  Options: Inlining false, Optimization false, Expressions true, Deforming true
  Timing: Generation 3.609 ms (Deform 1.019 ms), Inlining 0.000 ms, Optimization 2.043 ms, Emission 27.322 ms, Total 32.973 ms
Execution Time: 119.710 ms
```

**domain / count**

```
Finalize Aggregate  (cost=10216.16..10216.17 rows=1 width=8) (actual time=60.381..63.087 rows=1 loops=1)
  Buffers: shared hit=3820 read=1052
  ->  Gather  (cost=10215.95..10216.16 rows=2 width=8) (actual time=59.751..63.080 rows=3 loops=1)
        Workers Planned: 2
        Workers Launched: 2
        Buffers: shared hit=3820 read=1052
        ->  Partial Aggregate  (cost=9215.95..9215.96 rows=1 width=8) (actual time=57.246..57.250 rows=1 loops=3)
              Buffers: shared hit=3820 read=1052
              ->  Hash Join  (cost=1473.86..9153.74 rows=24882 width=0) (actual time=38.499..56.248 rows=20020 loops=3)
                    Hash Cond: (c.entry_id = e.id)
                    Buffers: shared hit=3820 read=1052
                    ->  Parallel Seq Scan on rl_362c6575_c c  (cost=0.00..6958.00 rows=275000 width=8) (actual time=0.024..18.105 rows=220000 loops=3)
                          Buffers: shared hit=3156 read=1052
                    ->  Hash  (cost=1223.38..1223.38 rows=20038 width=8) (actual time=14.694..14.697 rows=20124 loops=3)
                          Buckets: 32768  Batches: 1  Memory Usage: 1043kB
                          Buffers: shared hit=658
                          ->  HashAggregate  (cost=1023.00..1223.38 rows=20038 width=8) (actual time=9.332..11.947 rows=20124 loops=3)
                                Group Key: e.id
                                Batches: 1  Memory Usage: 1809kB
                                Buffers: shared hit=658
                                Worker 0:  Batches: 1  Memory Usage: 1809kB
                                Worker 1:  Batches: 1  Memory Usage: 1809kB
                                ->  Append  (cost=0.29..972.91 rows=20038 width=8) (actual time=0.033..5.677 rows=20148 loops=3)
                                      Buffers: shared hit=658
                                      ->  Index Scan using rl_362c6575_e_domain on rl_362c6575_e e  (cost=0.29..837.51 rows=20016 width=8) (actual time=0.032..2.762 rows=20124 loops=3)
                                            Index Cond: (domain_id = ANY ('{1,86,10102,10103,10104,10105,10106,10107,10108,10109,10110,10111,10112,10113,10114,10115,10116,10117,10118,10119,10120,10121,10122,10123,10124,10125,10126,10127,10128,10129,10130,10131,10132,10133,10134,10135,10136,10137,10138,10139,10140,10141,10142,10143,10144,10145,10146,10147,10148,10149,10150,10151,10152,10153,10154,10155,10156,10157,10158,10159,10160,10161,10162,10163,10164,10165,10166,10167,10168,10169,10170,10171,10172,10173,10174,10175,10176,10177,10178,10179,10180,10181,10182,10183,10184,10185,10186,10187,10188,10189,10190,10191,10192,10193,10194,10195,10196,10197,10198,10199,10200,10201}'::bigint[]))
                                            Buffers: shared hit=635
                                      ->  Index Scan using rl_362c6575_e_owner on rl_362c6575_e e_1  (cost=0.29..35.21 rows=22 width=8) (actual time=0.023..0.029 rows=24 loops=3)
                                            Index Cond: (owner_id = 'u000042'::text)
                                            Buffers: shared hit=23
Planning Time: 0.495 ms
Execution Time: 63.217 ms
```

**public / top10**

```
Limit  (cost=115405.82..157276.51 rows=10 width=12) (actual time=42.706..216.586 rows=10 loops=1)
  Buffers: shared hit=786
  ->  Nested Loop  (cost=115405.82..14293829985.77 rows=3413776 width=12) (actual time=29.705..203.576 rows=10 loops=1)
        Join Filter: (c.entry_id = e.id)
        Rows Removed by Join Filter: 1703595
        Buffers: shared hit=786
        ->  Index Scan using rl_362c6575_c_score on rl_362c6575_c c  (cost=0.42..33984.22 rows=660000 width=20) (actual time=0.031..0.419 rows=88 loops=1)
              Buffers: shared hit=91
        ->  Materialize  (cost=115405.40..146011.59 rows=1145477 width=8) (actual time=0.149..1.209 rows=19359 loops=88)
              Buffers: shared hit=695
              ->  HashAggregate  (cost=115405.40..135809.21 rows=1145477 width=8) (actual time=13.082..15.286 rows=20124 loops=1)
                    Group Key: e.id
                    Planned Partitions: 16  Batches: 1  Memory Usage: 4113kB
                    Buffers: shared hit=695
                    ->  Append  (cost=0.29..53836.01 rows=1145477 width=8) (actual time=0.017..6.883 rows=28791 loops=1)
                          Buffers: shared hit=695
                          ->  Index Scan using rl_362c6575_e_public on rl_362c6575_e e  (cost=0.29..615.84 rows=19974 width=8) (actual time=0.015..2.392 rows=20103 loops=1)
                                Index Cond: (public_level >= '1'::smallint)
                                Buffers: shared hit=209
                          ->  Nested Loop  (cost=0.42..371.69 rows=44 width=8) (actual time=0.053..0.170 rows=44 loops=1)
                                Buffers: shared hit=176
                                ->  Function Scan on unnest ap  (cost=0.00..0.44 rows=44 width=32) (actual time=0.033..0.036 rows=44 loops=1)
                                ->  Index Scan using rl_362c6575_e_path on rl_362c6575_e e_1  (cost=0.42..8.44 rows=1 width=29) (actual time=0.003..0.003 rows=1 loops=44)
                                      Index Cond: (path = (ap.value)::text)
                                      Buffers: shared hit=176
                          ->  Nested Loop  (cost=0.42..47085.89 rows=1125437 width=8) (actual time=0.016..2.042 rows=8620 loops=1)
                                Buffers: shared hit=303
                                ->  Function Scan on ar  (cost=0.01..0.45 rows=44 width=64) (actual time=0.008..0.014 rows=44 loops=1)
                                ->  Index Scan using rl_362c6575_e_path on rl_362c6575_e e_2  (cost=0.42..814.34 rows=25578 width=29) (actual time=0.004..0.026 rows=196 loops=44)
                                      Index Cond: ((path > (ar.lo)::text) AND (path < (ar.hi)::text))
                                      Buffers: shared hit=303
                          ->  Index Scan using rl_362c6575_e_owner on rl_362c6575_e e_3  (cost=0.29..35.21 rows=22 width=8) (actual time=0.026..0.032 rows=24 loops=1)
                                Index Cond: (owner_id = 'u000042'::text)
                                Buffers: shared hit=7
Planning Time: 0.465 ms
JIT:
  Functions: 32
  Options: Inlining false, Optimization false, Expressions true, Deforming true
  Timing: Generation 1.149 ms (Deform 0.423 ms), Inlining 0.000 ms, Optimization 0.660 ms, Emission 12.401 ms, Total 14.210 ms
Execution Time: 218.009 ms
```

**domain / top10**

```
Limit  (cost=10691.46..10692.63 rows=10 width=12) (actual time=52.304..55.435 rows=10 loops=1)
  Buffers: shared hit=4359 read=559
  ->  Gather Merge  (cost=10691.46..16497.66 rows=49764 width=12) (actual time=52.303..55.432 rows=10 loops=1)
        Workers Planned: 2
        Workers Launched: 2
        Buffers: shared hit=4359 read=559
        ->  Sort  (cost=9691.44..9753.64 rows=24882 width=12) (actual time=50.284..50.287 rows=9 loops=3)
              Sort Key: c.score
              Sort Method: top-N heapsort  Memory: 25kB
              Buffers: shared hit=4359 read=559
              Worker 0:  Sort Method: top-N heapsort  Memory: 25kB
              Worker 1:  Sort Method: top-N heapsort  Memory: 25kB
              ->  Hash Join  (cost=1473.86..9153.74 rows=24882 width=12) (actual time=32.265..49.072 rows=20020 loops=3)
                    Hash Cond: (c.entry_id = e.id)
                    Buffers: shared hit=4345 read=559
                    ->  Parallel Seq Scan on rl_362c6575_c c  (cost=0.00..6958.00 rows=275000 width=20) (actual time=0.028..17.529 rows=220000 loops=3)
                          Buffers: shared hit=3649 read=559
                    ->  Hash  (cost=1223.38..1223.38 rows=20038 width=8) (actual time=10.319..10.321 rows=20124 loops=3)
                          Buckets: 32768  Batches: 1  Memory Usage: 1043kB
                          Buffers: shared hit=658
                          ->  HashAggregate  (cost=1023.00..1223.38 rows=20038 width=8) (actual time=6.705..8.402 rows=20124 loops=3)
                                Group Key: e.id
                                Batches: 1  Memory Usage: 1809kB
                                Buffers: shared hit=658
                                Worker 0:  Batches: 1  Memory Usage: 1809kB
                                Worker 1:  Batches: 1  Memory Usage: 1809kB
                                ->  Append  (cost=0.29..972.91 rows=20038 width=8) (actual time=0.019..3.977 rows=20148 loops=3)
                                      Buffers: shared hit=658
                                      ->  Index Scan using rl_362c6575_e_domain on rl_362c6575_e e  (cost=0.29..837.51 rows=20016 width=8) (actual time=0.019..2.378 rows=20124 loops=3)
                                            Index Cond: (domain_id = ANY ('{1,86,10102,10103,10104,10105,10106,10107,10108,10109,10110,10111,10112,10113,10114,10115,10116,10117,10118,10119,10120,10121,10122,10123,10124,10125,10126,10127,10128,10129,10130,10131,10132,10133,10134,10135,10136,10137,10138,10139,10140,10141,10142,10143,10144,10145,10146,10147,10148,10149,10150,10151,10152,10153,10154,10155,10156,10157,10158,10159,10160,10161,10162,10163,10164,10165,10166,10167,10168,10169,10170,10171,10172,10173,10174,10175,10176,10177,10178,10179,10180,10181,10182,10183,10184,10185,10186,10187,10188,10189,10190,10191,10192,10193,10194,10195,10196,10197,10198,10199,10200,10201}'::bigint[]))
                                            Buffers: shared hit=635
                                      ->  Index Scan using rl_362c6575_e_owner on rl_362c6575_e e_1  (cost=0.29..35.21 rows=22 width=8) (actual time=0.019..0.023 rows=24 loops=3)
                                            Index Cond: (owner_id = 'u000042'::text)
                                            Buffers: shared hit=23
Planning Time: 0.255 ms
Execution Time: 55.520 ms
```

**public / top10 probe**

```
Limit  (cost=0.97..12.42 rows=10 width=12) (actual time=0.142..0.597 rows=10 loops=1)
  Buffers: shared hit=443
  ->  Nested Loop  (cost=0.97..410792.91 rows=358721 width=12) (actual time=0.142..0.596 rows=10 loops=1)
        Buffers: shared hit=443
        ->  Index Scan using rl_362c6575_c_score on rl_362c6575_c c  (cost=0.42..33984.22 rows=660000 width=20) (actual time=0.007..0.080 rows=88 loops=1)
              Buffers: shared hit=91
        ->  Memoize  (cost=0.54..0.72 rows=1 width=8) (actual time=0.006..0.006 rows=0 loops=88)
              Cache Key: c.entry_id
              Cache Mode: logical
              Hits: 0  Misses: 88  Evictions: 0  Overflows: 0  Memory Usage: 7kB
              Buffers: shared hit=352
              ->  Index Scan using rl_362c6575_e_pkey on rl_362c6575_e e  (cost=0.53..0.71 rows=1 width=8) (actual time=0.005..0.005 rows=0 loops=88)
                    Index Cond: (id = c.entry_id)
                    Filter: ((public_level >= '1'::smallint) OR (path = ANY ('{/home/u000042,/shared/s0001,/shared/s0004,/shared/s0005,/shared/s0006,/shared/s0008,/shared/s0012,/shared/s0013,/shared/s0016,/shared/s0021,/shared/s0022,/shared/s0030,/shared/s0031,/shared/s0033,/shared/s0036,/shared/s0037,/shared/s0041,/shared/s0043,/shared/s0045,/shared/s0048,/shared/s0053,/shared/s0055,/shared/s0056,/shared/s0058,/shared/s0059,/shared/s0061,/shared/s0062,/shared/s0063,/shared/s0066,/shared/s0067,/shared/s0071,/shared/s0075,/shared/s0077,/shared/s0078,/shared/s0082,/shared/s0085,/shared/s0088,/shared/s0089,/shared/s0091,/shared/s0092,/shared/s0094,/shared/s0097,/shared/s0098,/shared/s0099}'::text[])) OR EXISTS(SubPlan 1) OR (owner_id = 'u000042'::text))
                    Rows Removed by Filter: 1
                    Buffers: shared hit=352
                    SubPlan 1
                      ->  Function Scan on ar  (cost=0.01..0.66 rows=5 width=0) (actual time=0.002..0.002 rows=0 loops=78)
                            Filter: ((e.path > (lo)::text) AND (e.path < (hi)::text))
                            Rows Removed by Filter: 44
Planning:
  Buffers: shared hit=16
Planning Time: 0.169 ms
Execution Time: 0.612 ms
```

**domain / top10 probe**

```
Limit  (cost=1.11..73.10 rows=10 width=12) (actual time=0.081..0.362 rows=10 loops=1)
  Buffers: shared hit=443
  ->  Nested Loop  (cost=1.11..413544.75 rows=57444 width=12) (actual time=0.081..0.361 rows=10 loops=1)
        Buffers: shared hit=443
        ->  Index Scan using rl_362c6575_c_score on rl_362c6575_c c  (cost=0.42..33984.22 rows=660000 width=20) (actual time=0.008..0.080 rows=88 loops=1)
              Buffers: shared hit=91
        ->  Memoize  (cost=0.69..0.73 rows=1 width=8) (actual time=0.003..0.003 rows=0 loops=88)
              Cache Key: c.entry_id
              Cache Mode: logical
              Hits: 0  Misses: 88  Evictions: 0  Overflows: 0  Memory Usage: 7kB
              Buffers: shared hit=352
              ->  Index Scan using rl_362c6575_e_pkey on rl_362c6575_e e  (cost=0.68..0.72 rows=1 width=8) (actual time=0.002..0.002 rows=0 loops=88)
                    Index Cond: (id = c.entry_id)
                    Filter: ((domain_id = ANY ('{1,86,10102,10103,10104,10105,10106,10107,10108,10109,10110,10111,10112,10113,10114,10115,10116,10117,10118,10119,10120,10121,10122,10123,10124,10125,10126,10127,10128,10129,10130,10131,10132,10133,10134,10135,10136,10137,10138,10139,10140,10141,10142,10143,10144,10145,10146,10147,10148,10149,10150,10151,10152,10153,10154,10155,10156,10157,10158,10159,10160,10161,10162,10163,10164,10165,10166,10167,10168,10169,10170,10171,10172,10173,10174,10175,10176,10177,10178,10179,10180,10181,10182,10183,10184,10185,10186,10187,10188,10189,10190,10191,10192,10193,10194,10195,10196,10197,10198,10199,10200,10201}'::bigint[])) OR (owner_id = 'u000042'::text))
                    Rows Removed by Filter: 1
                    Buffers: shared hit=352
Planning:
  Buffers: shared hit=16
Planning Time: 0.212 ms
Execution Time: 0.374 ms
```

Total wall time 16s.
