## postgres (jit off) — N=10,000 users: 230,203 entries, 660,000 chunks (3/file), 11,400 grant rows, 10,101 posture rows, 10,201 domains

Load: rows in 1.4s.

### Indexes

| index | build s | size |
|---|---|---|
| e_path | 0.1 | 9.3 MB |
| e_owner | 0.2 | 1.8 MB |
| e_public | 0.1 | 1.6 MB |
| e_public_path | 0.2 | 9.3 MB |
| e_domain | 0.1 | 1.8 MB |
| c_entry | 0.2 | 10.9 MB |
| c_score | 0.2 | 14.9 MB |
| d_path | 0.0 | 0.3 MB |
| d_public | 0.0 | 0.1 MB |
| g_principal | 0.0 | 0.3 MB |
| m_principal | 0.0 | 0.6 MB |
| (entries table itself) | | 18.0 MB |

### Callers

| caller | subjects | grants held | visible entries | shipped `Rights.admits` on a sample |
|---|---|---|---|---|
| ordinary | u000042 | 49 | 20,124 | 500 rows, 0 disagreements; shipped resolve 213 ms (2 arms, 10,100 holes), admits 112 us/row |
| heavy group | u000003 | 46 | 20,124 | 500 rows, 0 disagreements; shipped resolve 211 ms (2 arms, 10,100 holes), admits 97 us/row |
| two subjects | u000042, u000032 | 104 | 20,103 | 500 rows, 0 disagreements; shipped resolve 92 ms (1 arms, 10,100 holes), admits 98 us/row |
| anonymous | — | 0 | 20,103 | 500 rows, 0 disagreements; shipped resolve 29 ms (1 arms, 10,100 holes), admits 202 us/row |
| system | — | 0 | 230,203 | skipped (system) |

### Compile per caller (the caller's own grants → sorted pieces)

| caller | level | points | opens | owner pieces | bind bytes | compile us (median of 200) | grants fetch cold ms | warm ms |
|---|---|---|---|---|---|---|---|---|
| ordinary | read | 44 | 44 | 0 | 2,445 | 30 | 11.2 | 6.0 |
| ordinary | read_write | 11 | 11 | 0 | 630 | 8 | 14.2 | 8.9 |
| heavy group | read | 44 | 44 | 0 | 2,445 | 27 | 9.1 | 9.1 |
| heavy group | read_write | 5 | 5 | 0 | 300 | 5 | 9.2 | 7.8 |
| two subjects | read | 21 | 21 | 178 | 6,094 | 96 | 10.3 | 10.1 |
| two subjects | read_write | 0 | 0 | 40 | 1,148 | 21 | 19.1 | 12.4 |

### Domain lists (the `domain_id` variant's compile, one SQL statement)

| caller | domains in list | bind bytes | cold ms | warm ms |
|---|---|---|---|---|
| ordinary | 102 | 707 | 10.5 | 7.3 |
| heavy group | 102 | 706 | 11.6 | 6.3 |
| two subjects | 101 | 703 | 7.2 | 6.9 |
| anonymous | 101 | 703 | 6.8 | 3.4 |

### Statements — cold = fresh connection, warm = median of 3 (ms); recall against the Python truth

| caller | statement | public: cold / warm / recall | domain: cold / warm / recall |
|---|---|---|---|
| ordinary | entries | 30.3 / 86.3 / exact | 51.4 / 19.4 / exact |
| ordinary | scoped | 12.0 / 3.6 / exact | 22.9 / 2.6 / exact |
| ordinary | count | 87.1 / 97.9 / exact | 67.8 / 48.1 / exact |
| ordinary | top10 | 72.9 / 72.8 / exact | 81.0 / 46.3 / exact |
| ordinary | top10 probe | 8.7 / 5.3 / exact | 15.4 / 2.7 / exact |
| heavy group | entries | 80.7 / 34.7 / exact | 38.6 / 20.7 / exact |
| heavy group | scoped | 5.0 / 2.3 / exact | 23.6 / 5.1 / exact |
| heavy group | count | 67.9 / 97.4 / exact | 59.7 / 43.2 / exact |
| heavy group | top10 | 63.2 / 68.4 / exact | 65.2 / 46.4 / exact |
| heavy group | top10 probe | 11.2 / 9.2 / exact | 29.7 / 7.1 / exact |
| two subjects | entries | 33.7 / 45.1 / exact | 25.7 / 16.0 / exact |
| two subjects | scoped | 5.7 / 3.2 / exact | 13.7 / 3.1 / exact |
| two subjects | count | 63.7 / 57.5 / exact | 42.4 / 33.6 / exact |
| two subjects | top10 | 51.9 / 67.1 / exact | 41.5 / 32.7 / exact |
| two subjects | top10 probe | 5.2 / 3.0 / exact | 14.4 / 2.2 / exact |
| anonymous | entries | 10.5 / 10.2 / exact | 18.0 / 10.4 / exact |
| anonymous | scoped | 2.6 / 1.9 / exact | 11.9 / 1.9 / exact |
| anonymous | count | 28.1 / 25.0 / exact | 35.7 / 26.6 / exact |
| anonymous | top10 | 5.3 / 2.5 / exact | 11.9 / 2.6 / exact |
| anonymous | top10 probe | 4.6 / 2.5 / exact | 13.2 / 2.7 / exact |
| system | entries | 224 / 246 / exact | — |
| system | scoped | 2.5 / 1.9 / exact | — |
| system | count | 56.9 / 57.5 / exact | — |
| system | top10 | 3.7 / 1.6 / exact | — |
| system | top10 probe | 3.2 / 2.3 / exact | — |

### Cache invalidation at this N

One cached caller recomputes by fetching its grant rows and merging them: about 3.70 ms warm here (fetch 3.7 ms + compile 30 us).

| write | global revision invalidates | per-principal / per-group / posture revisions invalidate | recompute at global (ms) | at granular (ms) |
|---|---|---|---|---|
| grant to one user | 10,000 | 1 | 36,985 | 4 |
| grant to a typical group | 10,000 | 1,007 | 36,985 | 3,724 |
| grant to the heavy group | 10,000 | 979 | 36,985 | 3,621 |
| posture change (any subtree) | 10,000 | 0 | 36,985 | 0 |

Under the row-label shape a posture change invalidates no compiled rights: the posture is on the rows, not in the caller's pieces. The relabel UPDATE is its cost (see the writes run).

### Plans (ordinary caller)

**public / entries**

```
HashAggregate  (cost=115437.76..135848.27 rows=1145853 width=8) (actual time=26.762..28.861 rows=20124 loops=1)
  Group Key: e.id
  Planned Partitions: 16  Batches: 1  Memory Usage: 4113kB
  Buffers: shared hit=695
  ->  Append  (cost=0.29..53848.16 rows=1145853 width=8) (actual time=10.587..18.754 rows=28791 loops=1)
        Buffers: shared hit=695
        ->  Index Scan using rl_f2715a89_e_public on rl_f2715a89_e e  (cost=0.29..625.42 rows=20350 width=8) (actual time=10.585..13.768 rows=20103 loops=1)
              Index Cond: (public_level >= '1'::smallint)
              Buffers: shared hit=209
        ->  Nested Loop  (cost=0.42..371.69 rows=44 width=8) (actual time=0.068..0.225 rows=44 loops=1)
              Buffers: shared hit=176
              ->  Function Scan on unnest ap  (cost=0.00..0.44 rows=44 width=32) (actual time=0.047..0.050 rows=44 loops=1)
              ->  Index Scan using rl_f2715a89_e_path on rl_f2715a89_e e_1  (cost=0.42..8.44 rows=1 width=29) (actual time=0.003..0.003 rows=1 loops=44)
                    Index Cond: (path = (ap.value)::text)
                    Buffers: shared hit=176
        ->  Nested Loop  (cost=0.42..47085.89 rows=1125437 width=8) (actual time=0.021..2.159 rows=8620 loops=1)
              Buffers: shared hit=303
              ->  Function Scan on ar  (cost=0.01..0.45 rows=44 width=64) (actual time=0.012..0.020 rows=44 loops=1)
              ->  Index Scan using rl_f2715a89_e_path on rl_f2715a89_e e_2  (cost=0.42..814.34 rows=25578 width=29) (actual time=0.004..0.028 rows=196 loops=44)
                    Index Cond: ((path > (ar.lo)::text) AND (path < (ar.hi)::text))
                    Buffers: shared hit=303
        ->  Index Scan using rl_f2715a89_e_owner on rl_f2715a89_e e_3  (cost=0.29..35.90 rows=22 width=8) (actual time=0.052..0.058 rows=24 loops=1)
              Index Cond: (owner_id = 'u000042'::text)
              Buffers: shared hit=7
Planning Time: 0.456 ms
JIT:
  Functions: 26
  Options: Inlining false, Optimization false, Expressions true, Deforming true
  Timing: Generation 1.088 ms (Deform 0.402 ms), Inlining 0.000 ms, Optimization 0.553 ms, Emission 10.159 ms, Total 11.800 ms
Execution Time: 30.963 ms
```

**domain / entries**

```
HashAggregate  (cost=1051.02..1255.16 rows=20414 width=8) (actual time=7.479..9.246 rows=20124 loops=1)
  Group Key: e.id
  Batches: 1  Memory Usage: 1809kB
  Buffers: shared hit=218
  ->  Append  (cost=0.29..999.98 rows=20414 width=8) (actual time=0.020..4.229 rows=20148 loops=1)
        Buffers: shared hit=218
        ->  Index Scan using rl_f2715a89_e_domain on rl_f2715a89_e e  (cost=0.29..862.01 rows=20392 width=8) (actual time=0.019..2.532 rows=20124 loops=1)
              Index Cond: (domain_id = ANY ('{1,86,10102,10103,10104,10105,10106,10107,10108,10109,10110,10111,10112,10113,10114,10115,10116,10117,10118,10119,10120,10121,10122,10123,10124,10125,10126,10127,10128,10129,10130,10131,10132,10133,10134,10135,10136,10137,10138,10139,10140,10141,10142,10143,10144,10145,10146,10147,10148,10149,10150,10151,10152,10153,10154,10155,10156,10157,10158,10159,10160,10161,10162,10163,10164,10165,10166,10167,10168,10169,10170,10171,10172,10173,10174,10175,10176,10177,10178,10179,10180,10181,10182,10183,10184,10185,10186,10187,10188,10189,10190,10191,10192,10193,10194,10195,10196,10197,10198,10199,10200,10201}'::bigint[]))
              Buffers: shared hit=211
        ->  Index Scan using rl_f2715a89_e_owner on rl_f2715a89_e e_1  (cost=0.29..35.90 rows=22 width=8) (actual time=0.022..0.031 rows=24 loops=1)
              Index Cond: (owner_id = 'u000042'::text)
              Buffers: shared hit=7
Planning Time: 0.206 ms
Execution Time: 9.905 ms
```

**public / count**

```
Finalize Aggregate  (cost=173466.05..173466.06 rows=1 width=8) (actual time=181.313..185.831 rows=1 loops=1)
  Buffers: shared hit=4911 read=1454, temp read=2172 written=2172
  ->  Gather  (cost=173465.84..173466.05 rows=2 width=8) (actual time=181.297..185.822 rows=3 loops=1)
        Workers Planned: 2
        Workers Launched: 2
        Buffers: shared hit=4911 read=1454, temp read=2172 written=2172
        ->  Partial Aggregate  (cost=172465.84..172465.85 rows=1 width=8) (actual time=153.305..153.313 rows=1 loops=3)
              Buffers: shared hit=4911 read=1454, temp read=2172 written=2172
              ->  Hash Join  (cost=154647.43..168953.32 rows=1405008 width=0) (actual time=69.339..149.178 rows=20020 loops=3)
                    Hash Cond: (c.entry_id = e.id)
                    Buffers: shared hit=4911 read=1454, temp read=2172 written=2172
                    ->  Parallel Seq Scan on rl_f2715a89_c c  (cost=0.00..6958.00 rows=275000 width=8) (actual time=13.535..50.370 rows=220000 loops=3)
                          Buffers: shared hit=2754 read=1454
                    ->  Hash  (cost=135848.27..135848.27 rows=1145853 width=8) (actual time=25.149..25.156 rows=20124 loops=3)
                          Buckets: 262144  Batches: 8  Memory Usage: 2145kB
                          Buffers: shared hit=2091, temp written=168
                          ->  HashAggregate  (cost=115437.76..135848.27 rows=1145853 width=8) (actual time=19.255..21.910 rows=20124 loops=3)
                                Group Key: e.id
                                Planned Partitions: 16  Batches: 1  Memory Usage: 4113kB
                                Buffers: shared hit=2091
                                Worker 0:  Batches: 1  Memory Usage: 4113kB
                                Worker 1:  Batches: 1  Memory Usage: 4113kB
                                ->  Append  (cost=0.29..53848.16 rows=1145853 width=8) (actual time=0.037..8.656 rows=28791 loops=3)
                                      Buffers: shared hit=2091
                                      ->  Index Scan using rl_f2715a89_e_public on rl_f2715a89_e e  (cost=0.29..625.42 rows=20350 width=8) (actual time=0.036..3.581 rows=20103 loops=3)
                                            Index Cond: (public_level >= '1'::smallint)
                                            Buffers: shared hit=629
                                      ->  Nested Loop  (cost=0.42..371.69 rows=44 width=8) (actual time=0.075..0.230 rows=44 loops=3)
                                            Buffers: shared hit=530
                                            ->  Function Scan on unnest ap  (cost=0.00..0.44 rows=44 width=32) (actual time=0.044..0.046 rows=44 loops=3)
                                            ->  Index Scan using rl_f2715a89_e_path on rl_f2715a89_e e_1  (cost=0.42..8.44 rows=1 width=29) (actual time=0.004..0.004 rows=1 loops=132)
                                                  Index Cond: (path = (ap.value)::text)
                                                  Buffers: shared hit=530
                                      ->  Nested Loop  (cost=0.42..47085.89 rows=1125437 width=8) (actual time=0.025..2.280 rows=8620 loops=3)
                                            Buffers: shared hit=909
                                            ->  Function Scan on ar  (cost=0.01..0.45 rows=44 width=64) (actual time=0.015..0.024 rows=44 loops=3)
                                            ->  Index Scan using rl_f2715a89_e_path on rl_f2715a89_e e_2  (cost=0.42..814.34 rows=25578 width=29) (actual time=0.005..0.030 rows=196 loops=132)
                                                  Index Cond: ((path > (ar.lo)::text) AND (path < (ar.hi)::text))
                                                  Buffers: shared hit=909
                                      ->  Index Scan using rl_f2715a89_e_owner on rl_f2715a89_e e_3  (cost=0.29..35.90 rows=22 width=8) (actual time=0.050..0.058 rows=24 loops=3)
                                            Index Cond: (owner_id = 'u000042'::text)
                                            Buffers: shared hit=23
Planning Time: 0.449 ms
JIT:
  Functions: 107
  Options: Inlining false, Optimization false, Expressions true, Deforming true
  Timing: Generation 3.050 ms (Deform 0.983 ms), Inlining 0.000 ms, Optimization 2.044 ms, Emission 38.832 ms, Total 43.926 ms
Execution Time: 187.871 ms
```

**domain / count**

```
Finalize Aggregate  (cost=10253.01..10253.02 rows=1 width=8) (actual time=72.976..75.883 rows=1 loops=1)
  Buffers: shared hit=3854 read=1018
  ->  Gather  (cost=10252.80..10253.01 rows=2 width=8) (actual time=72.550..75.874 rows=3 loops=1)
        Workers Planned: 2
        Workers Launched: 2
        Buffers: shared hit=3854 read=1018
        ->  Partial Aggregate  (cost=9252.80..9252.81 rows=1 width=8) (actual time=68.092..68.095 rows=1 loops=3)
              Buffers: shared hit=3854 read=1018
              ->  Hash Join  (cost=1510.33..9190.22 rows=25031 width=0) (actual time=41.843..66.800 rows=20020 loops=3)
                    Hash Cond: (c.entry_id = e.id)
                    Buffers: shared hit=3854 read=1018
                    ->  Parallel Seq Scan on rl_f2715a89_c c  (cost=0.00..6958.00 rows=275000 width=8) (actual time=0.037..21.599 rows=220000 loops=3)
                          Buffers: shared hit=3190 read=1018
                    ->  Hash  (cost=1255.16..1255.16 rows=20414 width=8) (actual time=14.143..14.146 rows=20124 loops=3)
                          Buckets: 32768  Batches: 1  Memory Usage: 1043kB
                          Buffers: shared hit=658
                          ->  HashAggregate  (cost=1051.02..1255.16 rows=20414 width=8) (actual time=9.946..11.994 rows=20124 loops=3)
                                Group Key: e.id
                                Batches: 1  Memory Usage: 1809kB
                                Buffers: shared hit=658
                                Worker 0:  Batches: 1  Memory Usage: 1809kB
                                Worker 1:  Batches: 1  Memory Usage: 1809kB
                                ->  Append  (cost=0.29..999.98 rows=20414 width=8) (actual time=0.026..4.293 rows=20148 loops=3)
                                      Buffers: shared hit=658
                                      ->  Index Scan using rl_f2715a89_e_domain on rl_f2715a89_e e  (cost=0.29..862.01 rows=20392 width=8) (actual time=0.025..2.598 rows=20124 loops=3)
                                            Index Cond: (domain_id = ANY ('{1,86,10102,10103,10104,10105,10106,10107,10108,10109,10110,10111,10112,10113,10114,10115,10116,10117,10118,10119,10120,10121,10122,10123,10124,10125,10126,10127,10128,10129,10130,10131,10132,10133,10134,10135,10136,10137,10138,10139,10140,10141,10142,10143,10144,10145,10146,10147,10148,10149,10150,10151,10152,10153,10154,10155,10156,10157,10158,10159,10160,10161,10162,10163,10164,10165,10166,10167,10168,10169,10170,10171,10172,10173,10174,10175,10176,10177,10178,10179,10180,10181,10182,10183,10184,10185,10186,10187,10188,10189,10190,10191,10192,10193,10194,10195,10196,10197,10198,10199,10200,10201}'::bigint[]))
                                            Buffers: shared hit=635
                                      ->  Index Scan using rl_f2715a89_e_owner on rl_f2715a89_e e_1  (cost=0.29..35.90 rows=22 width=8) (actual time=0.047..0.055 rows=24 loops=3)
                                            Index Cond: (owner_id = 'u000042'::text)
                                            Buffers: shared hit=23
Planning Time: 0.268 ms
Execution Time: 75.965 ms
```

**public / top10**

```
Limit  (cost=115438.19..157840.37 rows=10 width=12) (actual time=47.755..239.334 rows=10 loops=1)
  Buffers: shared hit=786
  ->  Nested Loop  (cost=115438.19..14298212406.01 rows=3372019 width=12) (actual time=38.628..230.199 rows=10 loops=1)
        Join Filter: (c.entry_id = e.id)
        Rows Removed by Join Filter: 1703595
        Buffers: shared hit=786
        ->  Index Scan using rl_f2715a89_c_score on rl_f2715a89_c c  (cost=0.42..33984.39 rows=660000 width=20) (actual time=0.031..0.746 rows=88 loops=1)
              Buffers: shared hit=91
        ->  Materialize  (cost=115437.76..146053.53 rows=1145853 width=8) (actual time=0.192..1.375 rows=19359 loops=88)
              Buffers: shared hit=695
              ->  HashAggregate  (cost=115437.76..135848.27 rows=1145853 width=8) (actual time=16.821..19.739 rows=20124 loops=1)
                    Group Key: e.id
                    Planned Partitions: 16  Batches: 1  Memory Usage: 4113kB
                    Buffers: shared hit=695
                    ->  Append  (cost=0.29..53848.16 rows=1145853 width=8) (actual time=0.015..8.934 rows=28791 loops=1)
                          Buffers: shared hit=695
                          ->  Index Scan using rl_f2715a89_e_public on rl_f2715a89_e e  (cost=0.29..625.42 rows=20350 width=8) (actual time=0.015..3.300 rows=20103 loops=1)
                                Index Cond: (public_level >= '1'::smallint)
                                Buffers: shared hit=209
                          ->  Nested Loop  (cost=0.42..371.69 rows=44 width=8) (actual time=0.067..0.289 rows=44 loops=1)
                                Buffers: shared hit=176
                                ->  Function Scan on unnest ap  (cost=0.00..0.44 rows=44 width=32) (actual time=0.045..0.048 rows=44 loops=1)
                                ->  Index Scan using rl_f2715a89_e_path on rl_f2715a89_e e_1  (cost=0.42..8.44 rows=1 width=29) (actual time=0.005..0.005 rows=1 loops=44)
                                      Index Cond: (path = (ap.value)::text)
                                      Buffers: shared hit=176
                          ->  Nested Loop  (cost=0.42..47085.89 rows=1125437 width=8) (actual time=0.027..2.641 rows=8620 loops=1)
                                Buffers: shared hit=303
                                ->  Function Scan on ar  (cost=0.01..0.45 rows=44 width=64) (actual time=0.017..0.029 rows=44 loops=1)
                                ->  Index Scan using rl_f2715a89_e_path on rl_f2715a89_e e_2  (cost=0.42..814.34 rows=25578 width=29) (actual time=0.005..0.035 rows=196 loops=44)
                                      Index Cond: ((path > (ar.lo)::text) AND (path < (ar.hi)::text))
                                      Buffers: shared hit=303
                          ->  Index Scan using rl_f2715a89_e_owner on rl_f2715a89_e e_3  (cost=0.29..35.90 rows=22 width=8) (actual time=0.055..0.064 rows=24 loops=1)
                                Index Cond: (owner_id = 'u000042'::text)
                                Buffers: shared hit=7
Planning Time: 0.249 ms
JIT:
  Functions: 32
  Options: Inlining false, Optimization false, Expressions true, Deforming true
  Timing: Generation 0.605 ms (Deform 0.281 ms), Inlining 0.000 ms, Optimization 0.387 ms, Emission 8.844 ms, Total 9.835 ms
Execution Time: 240.258 ms
```

**domain / top10**

```
Limit  (cost=10731.15..10732.32 rows=10 width=12) (actual time=70.539..74.105 rows=10 loops=1)
  Buffers: shared hit=4395 read=523
  ->  Gather Merge  (cost=10731.15..16572.13 rows=50062 width=12) (actual time=70.537..74.100 rows=10 loops=1)
        Workers Planned: 2
        Workers Launched: 2
        Buffers: shared hit=4395 read=523
        ->  Sort  (cost=9731.13..9793.71 rows=25031 width=12) (actual time=66.307..66.313 rows=8 loops=3)
              Sort Key: c.score
              Sort Method: top-N heapsort  Memory: 25kB
              Buffers: shared hit=4395 read=523
              Worker 0:  Sort Method: top-N heapsort  Memory: 25kB
              Worker 1:  Sort Method: top-N heapsort  Memory: 25kB
              ->  Hash Join  (cost=1510.33..9190.22 rows=25031 width=12) (actual time=40.771..64.411 rows=20020 loops=3)
                    Hash Cond: (c.entry_id = e.id)
                    Buffers: shared hit=4381 read=523
                    ->  Parallel Seq Scan on rl_f2715a89_c c  (cost=0.00..6958.00 rows=275000 width=20) (actual time=0.032..19.805 rows=220000 loops=3)
                          Buffers: shared hit=3685 read=523
                    ->  Hash  (cost=1255.16..1255.16 rows=20414 width=8) (actual time=14.192..14.195 rows=20124 loops=3)
                          Buckets: 32768  Batches: 1  Memory Usage: 1043kB
                          Buffers: shared hit=658
                          ->  HashAggregate  (cost=1051.02..1255.16 rows=20414 width=8) (actual time=8.888..11.778 rows=20124 loops=3)
                                Group Key: e.id
                                Batches: 1  Memory Usage: 1809kB
                                Buffers: shared hit=658
                                Worker 0:  Batches: 1  Memory Usage: 1809kB
                                Worker 1:  Batches: 1  Memory Usage: 1809kB
                                ->  Append  (cost=0.29..999.98 rows=20414 width=8) (actual time=0.023..4.506 rows=20148 loops=3)
                                      Buffers: shared hit=658
                                      ->  Index Scan using rl_f2715a89_e_domain on rl_f2715a89_e e  (cost=0.29..862.01 rows=20392 width=8) (actual time=0.023..2.627 rows=20124 loops=3)
                                            Index Cond: (domain_id = ANY ('{1,86,10102,10103,10104,10105,10106,10107,10108,10109,10110,10111,10112,10113,10114,10115,10116,10117,10118,10119,10120,10121,10122,10123,10124,10125,10126,10127,10128,10129,10130,10131,10132,10133,10134,10135,10136,10137,10138,10139,10140,10141,10142,10143,10144,10145,10146,10147,10148,10149,10150,10151,10152,10153,10154,10155,10156,10157,10158,10159,10160,10161,10162,10163,10164,10165,10166,10167,10168,10169,10170,10171,10172,10173,10174,10175,10176,10177,10178,10179,10180,10181,10182,10183,10184,10185,10186,10187,10188,10189,10190,10191,10192,10193,10194,10195,10196,10197,10198,10199,10200,10201}'::bigint[]))
                                            Buffers: shared hit=635
                                      ->  Index Scan using rl_f2715a89_e_owner on rl_f2715a89_e e_1  (cost=0.29..35.90 rows=22 width=8) (actual time=0.031..0.038 rows=24 loops=3)
                                            Index Cond: (owner_id = 'u000042'::text)
                                            Buffers: shared hit=23
Planning Time: 0.474 ms
Execution Time: 74.214 ms
```

**public / top10 probe**

```
Limit  (cost=0.97..12.46 rows=10 width=12) (actual time=0.280..0.853 rows=10 loops=1)
  Buffers: shared hit=443
  ->  Nested Loop  (cost=0.97..412971.83 rows=359260 width=12) (actual time=0.279..0.851 rows=10 loops=1)
        Buffers: shared hit=443
        ->  Index Scan using rl_f2715a89_c_score on rl_f2715a89_c c  (cost=0.42..33984.39 rows=660000 width=20) (actual time=0.009..0.116 rows=88 loops=1)
              Buffers: shared hit=91
        ->  Memoize  (cost=0.54..0.72 rows=1 width=8) (actual time=0.008..0.008 rows=0 loops=88)
              Cache Key: c.entry_id
              Cache Mode: logical
              Hits: 0  Misses: 88  Evictions: 0  Overflows: 0  Memory Usage: 7kB
              Buffers: shared hit=352
              ->  Index Scan using rl_f2715a89_e_pkey on rl_f2715a89_e e  (cost=0.53..0.71 rows=1 width=8) (actual time=0.006..0.006 rows=0 loops=88)
                    Index Cond: (id = c.entry_id)
                    Filter: ((public_level >= '1'::smallint) OR (path = ANY ('{/home/u000042,/shared/s0001,/shared/s0004,/shared/s0005,/shared/s0006,/shared/s0008,/shared/s0012,/shared/s0013,/shared/s0016,/shared/s0021,/shared/s0022,/shared/s0030,/shared/s0031,/shared/s0033,/shared/s0036,/shared/s0037,/shared/s0041,/shared/s0043,/shared/s0045,/shared/s0048,/shared/s0053,/shared/s0055,/shared/s0056,/shared/s0058,/shared/s0059,/shared/s0061,/shared/s0062,/shared/s0063,/shared/s0066,/shared/s0067,/shared/s0071,/shared/s0075,/shared/s0077,/shared/s0078,/shared/s0082,/shared/s0085,/shared/s0088,/shared/s0089,/shared/s0091,/shared/s0092,/shared/s0094,/shared/s0097,/shared/s0098,/shared/s0099}'::text[])) OR EXISTS(SubPlan 1) OR (owner_id = 'u000042'::text))
                    Rows Removed by Filter: 1
                    Buffers: shared hit=352
                    SubPlan 1
                      ->  Function Scan on ar  (cost=0.01..0.66 rows=5 width=0) (actual time=0.003..0.003 rows=0 loops=78)
                            Filter: ((e.path > (lo)::text) AND (e.path < (hi)::text))
                            Rows Removed by Filter: 44
Planning:
  Buffers: shared hit=16
Planning Time: 0.229 ms
Execution Time: 0.873 ms
```

**domain / top10 probe**

```
Limit  (cost=1.11..72.15 rows=10 width=12) (actual time=0.151..0.618 rows=10 loops=1)
  Buffers: shared hit=443
  ->  Nested Loop  (cost=1.11..415740.27 rows=58522 width=12) (actual time=0.150..0.616 rows=10 loops=1)
        Buffers: shared hit=443
        ->  Index Scan using rl_f2715a89_c_score on rl_f2715a89_c c  (cost=0.42..33984.39 rows=660000 width=20) (actual time=0.019..0.163 rows=88 loops=1)
              Buffers: shared hit=91
        ->  Memoize  (cost=0.69..0.73 rows=1 width=8) (actual time=0.005..0.005 rows=0 loops=88)
              Cache Key: c.entry_id
              Cache Mode: logical
              Hits: 0  Misses: 88  Evictions: 0  Overflows: 0  Memory Usage: 7kB
              Buffers: shared hit=352
              ->  Index Scan using rl_f2715a89_e_pkey on rl_f2715a89_e e  (cost=0.68..0.72 rows=1 width=8) (actual time=0.004..0.004 rows=0 loops=88)
                    Index Cond: (id = c.entry_id)
                    Filter: ((domain_id = ANY ('{1,86,10102,10103,10104,10105,10106,10107,10108,10109,10110,10111,10112,10113,10114,10115,10116,10117,10118,10119,10120,10121,10122,10123,10124,10125,10126,10127,10128,10129,10130,10131,10132,10133,10134,10135,10136,10137,10138,10139,10140,10141,10142,10143,10144,10145,10146,10147,10148,10149,10150,10151,10152,10153,10154,10155,10156,10157,10158,10159,10160,10161,10162,10163,10164,10165,10166,10167,10168,10169,10170,10171,10172,10173,10174,10175,10176,10177,10178,10179,10180,10181,10182,10183,10184,10185,10186,10187,10188,10189,10190,10191,10192,10193,10194,10195,10196,10197,10198,10199,10200,10201}'::bigint[])) OR (owner_id = 'u000042'::text))
                    Rows Removed by Filter: 1
                    Buffers: shared hit=352
Planning:
  Buffers: shared hit=16
Planning Time: 0.322 ms
Execution Time: 0.900 ms
```

Total wall time 15s.
