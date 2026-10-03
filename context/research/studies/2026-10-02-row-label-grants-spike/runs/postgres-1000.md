## postgres — N=1,000 users: 23,113 entries, 66,000 chunks (3/file), 1,140 grant rows, 1,101 posture rows, 1,111 domains

Load: rows in 0.2s.

### Indexes

| index | build s | size |
|---|---|---|
| path | 0.0 | 0.9 MB |
| owner | 0.0 | 0.2 MB |
| public | 0.0 | 0.2 MB |
| public_path | 0.0 | 0.9 MB |
| domain | 0.0 | 0.2 MB |
| entry | 0.0 | 1.1 MB |
| score | 0.0 | 1.5 MB |
| path | 0.0 | 0.1 MB |
| public | 0.0 | 0.0 MB |
| principal | 0.0 | 0.0 MB |
| principal | 0.0 | 0.1 MB |
| (entries table itself) | | 2.2 MB |

### Callers

| caller | subjects | grants held | visible entries | shipped `Rights.admits` on a sample |
|---|---|---|---|---|
| ordinary | u000042 | 41 | 2,034 | 5,000 rows, 0 disagreements; shipped resolve 3 ms (2 arms, 1,100 holes), admits 11 us/row |
| heavy group | u000000 | 41 | 2,034 | 5,000 rows, 0 disagreements; shipped resolve 3 ms (2 arms, 1,100 holes), admits 11 us/row |
| two subjects | u000042, u000000 | 82 | 2,013 | 5,000 rows, 0 disagreements; shipped resolve 4 ms (1 arms, 1,100 holes), admits 11 us/row |
| anonymous | — | 0 | 2,013 | 5,000 rows, 0 disagreements; shipped resolve 1 ms (1 arms, 1,100 holes), admits 11 us/row |
| system | — | 0 | 23,113 | skipped (system) |

### Compile per caller (the caller's own grants → sorted pieces)

| caller | level | points | opens | owner pieces | bind bytes | compile us (median of 200) | grants fetch cold ms | warm ms |
|---|---|---|---|---|---|---|---|---|
| ordinary | read | 11 | 11 | 0 | 630 | 22 | 11.7 | 6.9 |
| ordinary | read_write | 11 | 11 | 0 | 630 | 8 | 10.0 | 4.5 |
| heavy group | read | 11 | 11 | 0 | 630 | 23 | 3.5 | 2.3 |
| heavy group | read_write | 11 | 11 | 0 | 630 | 8 | 7.0 | 4.7 |
| two subjects | read | 10 | 10 | 44 | 1,804 | 56 | 9.2 | 4.7 |
| two subjects | read_write | 10 | 10 | 44 | 1,804 | 25 | 3.1 | 1.6 |

### Domain lists (the `domain_id` variant's compile, one SQL statement)

| caller | domains in list | bind bytes | cold ms | warm ms |
|---|---|---|---|---|
| ordinary | 12 | 67 | 7.9 | 2.1 |
| heavy group | 12 | 66 | 3.1 | 1.6 |
| two subjects | 11 | 63 | 3.4 | 1.5 |
| anonymous | 11 | 63 | 3.0 | 1.2 |

### Statements — cold = fresh connection, warm = median of 2 (ms); recall against the Python truth

| caller | statement | public: cold / warm / recall | domain: cold / warm / recall |
|---|---|---|---|
| ordinary | entries | 5.8 / 3.6 / exact | 13.5 / 2.9 / exact |
| ordinary | scoped | 4.2 / 1.9 / exact | 10.2 / 1.4 / exact |
| ordinary | count | 9.2 / 6.7 / exact | 17.1 / 7.6 / exact |
| ordinary | top10 | 10.9 / 7.9 / exact | 16.1 / 5.9 / exact |
| ordinary | top10 probe | 6.5 / 3.1 / exact | 17.2 / 1.8 / exact |
| heavy group | entries | 6.9 / 3.8 / exact | 11.9 / 2.4 / exact |
| heavy group | scoped | 4.6 / 2.2 / exact | 11.8 / 1.5 / exact |
| heavy group | count | 8.6 / 6.1 / exact | 16.3 / 5.7 / exact |
| heavy group | top10 | 10.4 / 7.7 / exact | 27.9 / 8.0 / exact |
| heavy group | top10 probe | 4.2 / 1.7 / exact | 12.6 / 1.8 / exact |
| two subjects | entries | 5.8 / 3.6 / exact | 14.9 / 2.5 / exact |
| two subjects | scoped | 4.4 / 2.1 / exact | 10.6 / 1.6 / exact |
| two subjects | count | 8.8 / 6.6 / exact | 17.0 / 6.0 / exact |
| two subjects | top10 | 11.6 / 7.8 / exact | 22.9 / 6.6 / exact |
| two subjects | top10 probe | 5.6 / 2.5 / exact | 15.6 / 1.8 / exact |
| anonymous | entries | 5.0 / 3.0 / exact | 15.5 / 2.9 / exact |
| anonymous | scoped | 4.3 / 2.3 / exact | 14.1 / 2.0 / exact |
| anonymous | count | 7.7 / 5.5 / exact | 17.2 / 5.8 / exact |
| anonymous | top10 | 5.0 / 2.4 / exact | 19.0 / 2.0 / exact |
| anonymous | top10 probe | 4.8 / 2.4 / exact | 15.9 / 2.3 / exact |
| system | entries | 12.6 / 10.4 / exact | — |
| system | scoped | 9.1 / 4.3 / exact | — |
| system | count | 19.4 / 12.3 / exact | — |
| system | top10 | 5.4 / 2.2 / exact | — |
| system | top10 probe | 3.5 / 1.6 / exact | — |

### Cache invalidation at this N

One cached caller recomputes by fetching its grant rows and merging them: about 1.91 ms warm here (fetch 1.9 ms + compile 22 us).

| write | global revision invalidates | per-principal / per-group / posture revisions invalidate | recompute at global (ms) | at granular (ms) |
|---|---|---|---|---|
| grant to one user | 1,000 | 1 | 1,912 | 2 |
| grant to a typical group | 1,000 | 1,000 | 1,912 | 1,912 |
| grant to the heavy group | 1,000 | 1,000 | 1,912 | 1,912 |
| posture change (any subtree) | 1,000 | 0 | 1,912 | 0 |

Under the row-label shape a posture change invalidates no compiled rights: the posture is on the rows, not in the caller's pieces. The relabel UPDATE is its cost (see the writes run).

### Plans (ordinary caller)

**public / entries**

```
HashAggregate  (cost=2483.77..2786.74 rows=30297 width=8) (actual time=1.642..1.933 rows=2034 loops=1)
  Group Key: e.id
  Batches: 1  Memory Usage: 1681kB
  Buffers: shared hit=127
  ->  Append  (cost=0.29..2408.02 rows=30297 width=8) (actual time=0.015..1.102 rows=4068 loops=1)
        Buffers: shared hit=127
        ->  Index Scan using rl_837dc906_e_public on rl_837dc906_e e  (cost=0.29..71.89 rows=2013 width=8) (actual time=0.014..0.234 rows=2013 loops=1)
              Index Cond: (public_level >= '1'::smallint)
              Buffers: shared hit=25
        ->  Nested Loop  (cost=0.29..91.47 rows=11 width=8) (actual time=0.087..0.115 rows=11 loops=1)
              Buffers: shared hit=33
              ->  Function Scan on unnest ap  (cost=0.00..0.11 rows=11 width=32) (actual time=0.006..0.007 rows=11 loops=1)
              ->  Index Scan using rl_837dc906_e_path on rl_837dc906_e e_1  (cost=0.29..8.30 rows=1 width=29) (actual time=0.009..0.009 rows=1 loops=11)
                    Index Cond: (path = (ap.value)::text)
                    Buffers: shared hit=33
        ->  Nested Loop  (cost=0.29..2056.39 rows=28249 width=8) (actual time=0.015..0.434 rows=2020 loops=1)
              Buffers: shared hit=62
              ->  Function Scan on ar  (cost=0.01..0.12 rows=11 width=64) (actual time=0.009..0.010 rows=11 loops=1)
              ->  Index Scan using rl_837dc906_e_path on rl_837dc906_e e_2  (cost=0.29..161.25 rows=2568 width=29) (actual time=0.002..0.022 rows=184 loops=11)
                    Index Cond: ((path > (ar.lo)::text) AND (path < (ar.hi)::text))
                    Buffers: shared hit=62
        ->  Index Scan using rl_837dc906_e_owner on rl_837dc906_e e_3  (cost=0.29..36.79 rows=24 width=8) (actual time=0.007..0.010 rows=24 loops=1)
              Index Cond: (owner_id = 'u000042'::text)
              Buffers: shared hit=7
Planning Time: 0.180 ms
Execution Time: 2.047 ms
```

**domain / entries**

```
HashAggregate  (cost=187.31..208.05 rows=2074 width=8) (actual time=0.647..0.791 rows=2034 loops=1)
  Group Key: e.id
  Batches: 1  Memory Usage: 241kB
  Buffers: shared hit=34
  ->  Append  (cost=0.29..182.12 rows=2074 width=8) (actual time=0.015..0.403 rows=2058 loops=1)
        Buffers: shared hit=34
        ->  Index Scan using rl_837dc906_e_domain on rl_837dc906_e e  (cost=0.29..134.96 rows=2050 width=8) (actual time=0.015..0.235 rows=2034 loops=1)
              Index Cond: (domain_id = ANY ('{1,86,1102,1103,1104,1105,1106,1107,1108,1109,1110,1111}'::bigint[]))
              Buffers: shared hit=27
        ->  Index Scan using rl_837dc906_e_owner on rl_837dc906_e e_1  (cost=0.29..36.79 rows=24 width=8) (actual time=0.005..0.008 rows=24 loops=1)
              Index Cond: (owner_id = 'u000042'::text)
              Buffers: shared hit=7
Planning Time: 0.129 ms
Execution Time: 0.878 ms
```

**public / count**

```
Aggregate  (cost=4658.16..4658.17 rows=1 width=8) (actual time=11.364..11.369 rows=1 loops=1)
  Buffers: shared hit=559
  ->  Hash Join  (cost=3165.45..4430.73 rows=90970 width=0) (actual time=2.535..11.059 rows=6060 loops=1)
        Hash Cond: (c.entry_id = e.id)
        Buffers: shared hit=559
        ->  Seq Scan on rl_837dc906_c c  (cost=0.00..1092.00 rows=66000 width=8) (actual time=0.009..4.567 rows=66000 loops=1)
              Buffers: shared hit=432
        ->  Hash  (cost=2786.74..2786.74 rows=30297 width=8) (actual time=2.193..2.197 rows=2034 loops=1)
              Buckets: 32768  Batches: 1  Memory Usage: 336kB
              Buffers: shared hit=127
              ->  HashAggregate  (cost=2483.77..2786.74 rows=30297 width=8) (actual time=1.575..1.888 rows=2034 loops=1)
                    Group Key: e.id
                    Batches: 1  Memory Usage: 1681kB
                    Buffers: shared hit=127
                    ->  Append  (cost=0.29..2408.02 rows=30297 width=8) (actual time=0.014..1.068 rows=4068 loops=1)
                          Buffers: shared hit=127
                          ->  Index Scan using rl_837dc906_e_public on rl_837dc906_e e  (cost=0.29..71.89 rows=2013 width=8) (actual time=0.014..0.244 rows=2013 loops=1)
                                Index Cond: (public_level >= '1'::smallint)
                                Buffers: shared hit=25
                          ->  Nested Loop  (cost=0.29..91.47 rows=11 width=8) (actual time=0.015..0.035 rows=11 loops=1)
                                Buffers: shared hit=33
                                ->  Function Scan on unnest ap  (cost=0.00..0.11 rows=11 width=32) (actual time=0.006..0.007 rows=11 loops=1)
                                ->  Index Scan using rl_837dc906_e_path on rl_837dc906_e e_1  (cost=0.29..8.30 rows=1 width=29) (actual time=0.002..0.002 rows=1 loops=11)
                                      Index Cond: (path = (ap.value)::text)
                                      Buffers: shared hit=33
                          ->  Nested Loop  (cost=0.29..2056.39 rows=28249 width=8) (actual time=0.021..0.450 rows=2020 loops=1)
                                Buffers: shared hit=62
                                ->  Function Scan on ar  (cost=0.01..0.12 rows=11 width=64) (actual time=0.016..0.017 rows=11 loops=1)
                                ->  Index Scan using rl_837dc906_e_path on rl_837dc906_e e_2  (cost=0.29..161.25 rows=2568 width=29) (actual time=0.002..0.023 rows=184 loops=11)
                                      Index Cond: ((path > (ar.lo)::text) AND (path < (ar.hi)::text))
                                      Buffers: shared hit=62
                          ->  Index Scan using rl_837dc906_e_owner on rl_837dc906_e e_3  (cost=0.29..36.79 rows=24 width=8) (actual time=0.017..0.020 rows=24 loops=1)
                                Index Cond: (owner_id = 'u000042'::text)
                                Buffers: shared hit=7
Planning Time: 0.217 ms
Execution Time: 11.451 ms
```

**domain / count**

```
Aggregate  (cost=1514.82..1514.83 rows=1 width=8) (actual time=10.045..10.049 rows=1 loops=1)
  Buffers: shared hit=466
  ->  Hash Join  (cost=233.97..1499.25 rows=6227 width=0) (actual time=1.346..9.737 rows=6060 loops=1)
        Hash Cond: (c.entry_id = e.id)
        Buffers: shared hit=466
        ->  Seq Scan on rl_837dc906_c c  (cost=0.00..1092.00 rows=66000 width=8) (actual time=0.009..4.451 rows=66000 loops=1)
              Buffers: shared hit=432
        ->  Hash  (cost=208.05..208.05 rows=2074 width=8) (actual time=0.985..0.988 rows=2034 loops=1)
              Buckets: 4096  Batches: 1  Memory Usage: 112kB
              Buffers: shared hit=34
              ->  HashAggregate  (cost=187.31..208.05 rows=2074 width=8) (actual time=0.635..0.798 rows=2034 loops=1)
                    Group Key: e.id
                    Batches: 1  Memory Usage: 241kB
                    Buffers: shared hit=34
                    ->  Append  (cost=0.29..182.12 rows=2074 width=8) (actual time=0.014..0.417 rows=2058 loops=1)
                          Buffers: shared hit=34
                          ->  Index Scan using rl_837dc906_e_domain on rl_837dc906_e e  (cost=0.29..134.96 rows=2050 width=8) (actual time=0.014..0.246 rows=2034 loops=1)
                                Index Cond: (domain_id = ANY ('{1,86,1102,1103,1104,1105,1106,1107,1108,1109,1110,1111}'::bigint[]))
                                Buffers: shared hit=27
                          ->  Index Scan using rl_837dc906_e_owner on rl_837dc906_e e_1  (cost=0.29..36.79 rows=24 width=8) (actual time=0.006..0.009 rows=24 loops=1)
                                Index Cond: (owner_id = 'u000042'::text)
                                Buffers: shared hit=7
Planning Time: 0.161 ms
Execution Time: 10.089 ms
```

**public / top10**

```
Limit  (cost=2484.06..5781.46 rows=10 width=12) (actual time=3.544..23.364 rows=10 loops=1)
  Buffers: shared hit=233
  ->  Nested Loop  (cost=2484.06..29998979.48 rows=90970 width=12) (actual time=3.543..23.360 rows=10 loops=1)
        Join Filter: (c.entry_id = e.id)
        Rows Removed by Join Filter: 203141
        Buffers: shared hit=233
        ->  Index Scan using rl_837dc906_c_score on rl_837dc906_c c  (cost=0.29..3450.27 rows=66000 width=20) (actual time=0.014..0.183 rows=104 loops=1)
              Buffers: shared hit=106
        ->  Materialize  (cost=2483.77..2938.22 rows=30297 width=8) (actual time=0.014..0.142 rows=1953 loops=104)
              Buffers: shared hit=127
              ->  HashAggregate  (cost=2483.77..2786.74 rows=30297 width=8) (actual time=1.442..1.761 rows=2034 loops=1)
                    Group Key: e.id
                    Batches: 1  Memory Usage: 1681kB
                    Buffers: shared hit=127
                    ->  Append  (cost=0.29..2408.02 rows=30297 width=8) (actual time=0.008..1.013 rows=4068 loops=1)
                          Buffers: shared hit=127
                          ->  Index Scan using rl_837dc906_e_public on rl_837dc906_e e  (cost=0.29..71.89 rows=2013 width=8) (actual time=0.007..0.226 rows=2013 loops=1)
                                Index Cond: (public_level >= '1'::smallint)
                                Buffers: shared hit=25
                          ->  Nested Loop  (cost=0.29..91.47 rows=11 width=8) (actual time=0.011..0.030 rows=11 loops=1)
                                Buffers: shared hit=33
                                ->  Function Scan on unnest ap  (cost=0.00..0.11 rows=11 width=32) (actual time=0.004..0.005 rows=11 loops=1)
                                ->  Index Scan using rl_837dc906_e_path on rl_837dc906_e e_1  (cost=0.29..8.30 rows=1 width=29) (actual time=0.002..0.002 rows=1 loops=11)
                                      Index Cond: (path = (ap.value)::text)
                                      Buffers: shared hit=33
                          ->  Nested Loop  (cost=0.29..2056.39 rows=28249 width=8) (actual time=0.016..0.425 rows=2020 loops=1)
                                Buffers: shared hit=62
                                ->  Function Scan on ar  (cost=0.01..0.12 rows=11 width=64) (actual time=0.004..0.005 rows=11 loops=1)
                                ->  Index Scan using rl_837dc906_e_path on rl_837dc906_e e_2  (cost=0.29..161.25 rows=2568 width=29) (actual time=0.003..0.022 rows=184 loops=11)
                                      Index Cond: ((path > (ar.lo)::text) AND (path < (ar.hi)::text))
                                      Buffers: shared hit=62
                          ->  Index Scan using rl_837dc906_e_owner on rl_837dc906_e e_3  (cost=0.29..36.79 rows=24 width=8) (actual time=0.008..0.011 rows=24 loops=1)
                                Index Cond: (owner_id = 'u000042'::text)
                                Buffers: shared hit=7
Planning Time: 0.182 ms
Execution Time: 23.459 ms
```

**domain / top10**

```
Limit  (cost=1633.82..1633.84 rows=10 width=12) (actual time=10.945..10.950 rows=10 loops=1)
  Buffers: shared hit=466
  ->  Sort  (cost=1633.82..1649.38 rows=6227 width=12) (actual time=10.943..10.947 rows=10 loops=1)
        Sort Key: c.score
        Sort Method: top-N heapsort  Memory: 25kB
        Buffers: shared hit=466
        ->  Hash Join  (cost=233.97..1499.25 rows=6227 width=12) (actual time=1.334..10.580 rows=6060 loops=1)
              Hash Cond: (c.entry_id = e.id)
              Buffers: shared hit=466
              ->  Seq Scan on rl_837dc906_c c  (cost=0.00..1092.00 rows=66000 width=20) (actual time=0.009..4.695 rows=66000 loops=1)
                    Buffers: shared hit=432
              ->  Hash  (cost=208.05..208.05 rows=2074 width=8) (actual time=0.948..0.950 rows=2034 loops=1)
                    Buckets: 4096  Batches: 1  Memory Usage: 112kB
                    Buffers: shared hit=34
                    ->  HashAggregate  (cost=187.31..208.05 rows=2074 width=8) (actual time=0.634..0.803 rows=2034 loops=1)
                          Group Key: e.id
                          Batches: 1  Memory Usage: 241kB
                          Buffers: shared hit=34
                          ->  Append  (cost=0.29..182.12 rows=2074 width=8) (actual time=0.014..0.410 rows=2058 loops=1)
                                Buffers: shared hit=34
                                ->  Index Scan using rl_837dc906_e_domain on rl_837dc906_e e  (cost=0.29..134.96 rows=2050 width=8) (actual time=0.013..0.240 rows=2034 loops=1)
                                      Index Cond: (domain_id = ANY ('{1,86,1102,1103,1104,1105,1106,1107,1108,1109,1110,1111}'::bigint[]))
                                      Buffers: shared hit=27
                                ->  Index Scan using rl_837dc906_e_owner on rl_837dc906_e e_1  (cost=0.29..36.79 rows=24 width=8) (actual time=0.007..0.010 rows=24 loops=1)
                                      Index Cond: (owner_id = 'u000042'::text)
                                      Buffers: shared hit=7
Planning Time: 0.173 ms
Execution Time: 10.987 ms
```

**public / top10 probe**

```
Limit  (cost=0.62..5.30 rows=10 width=12) (actual time=1.008..1.638 rows=10 loops=1)
  Buffers: shared hit=418
  ->  Nested Loop  (cost=0.62..16815.90 rows=35920 width=12) (actual time=1.008..1.635 rows=10 loops=1)
        Buffers: shared hit=418
        ->  Index Scan using rl_837dc906_c_score on rl_837dc906_c c  (cost=0.29..3450.27 rows=66000 width=20) (actual time=0.009..0.127 rows=104 loops=1)
              Buffers: shared hit=106
        ->  Memoize  (cost=0.33..0.54 rows=1 width=8) (actual time=0.014..0.014 rows=0 loops=104)
              Cache Key: c.entry_id
              Cache Mode: logical
              Hits: 0  Misses: 104  Evictions: 0  Overflows: 0  Memory Usage: 8kB
              Buffers: shared hit=312
              ->  Index Scan using rl_837dc906_e_pkey on rl_837dc906_e e  (cost=0.32..0.53 rows=1 width=8) (actual time=0.008..0.008 rows=0 loops=104)
                    Index Cond: (id = c.entry_id)
                    Filter: ((public_level >= '1'::smallint) OR (path = ANY ('{/home/u000042,/shared/s0000,/shared/s0001,/shared/s0002,/shared/s0003,/shared/s0004,/shared/s0005,/shared/s0006,/shared/s0007,/shared/s0008,/shared/s0009}'::text[])) OR EXISTS(SubPlan 1) OR (owner_id = 'u000042'::text))
                    Rows Removed by Filter: 1
                    Buffers: shared hit=312
                    SubPlan 1
                      ->  Function Scan on ar  (cost=0.01..0.17 rows=1 width=0) (actual time=0.001..0.001 rows=0 loops=94)
                            Filter: ((e.path > (lo)::text) AND (e.path < (hi)::text))
                            Rows Removed by Filter: 11
Planning:
  Buffers: shared hit=12
Planning Time: 0.236 ms
Execution Time: 1.662 ms
```

**domain / top10 probe**

```
Limit  (cost=0.62..22.72 rows=10 width=12) (actual time=0.072..0.331 rows=10 loops=1)
  Buffers: shared hit=418
  ->  Nested Loop  (cost=0.62..13079.19 rows=5917 width=12) (actual time=0.071..0.329 rows=10 loops=1)
        Buffers: shared hit=418
        ->  Index Scan using rl_837dc906_c_score on rl_837dc906_c c  (cost=0.29..3450.27 rows=66000 width=20) (actual time=0.007..0.089 rows=104 loops=1)
              Buffers: shared hit=106
        ->  Memoize  (cost=0.33..0.37 rows=1 width=8) (actual time=0.002..0.002 rows=0 loops=104)
              Cache Key: c.entry_id
              Cache Mode: logical
              Hits: 0  Misses: 104  Evictions: 0  Overflows: 0  Memory Usage: 8kB
              Buffers: shared hit=312
              ->  Index Scan using rl_837dc906_e_pkey on rl_837dc906_e e  (cost=0.32..0.36 rows=1 width=8) (actual time=0.002..0.002 rows=0 loops=104)
                    Index Cond: (id = c.entry_id)
                    Filter: ((domain_id = ANY ('{1,86,1102,1103,1104,1105,1106,1107,1108,1109,1110,1111}'::bigint[])) OR (owner_id = 'u000042'::text))
                    Rows Removed by Filter: 1
                    Buffers: shared hit=312
Planning:
  Buffers: shared hit=12
Planning Time: 0.204 ms
Execution Time: 0.349 ms
```

Total wall time 4s.
