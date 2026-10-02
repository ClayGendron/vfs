## postgres — 41,421 entries, 121,200 chunks, loaded in 2s, median of 3 warm runs (ms)

| caller | pieces | arms: clauses | statement | arms | literal | join IN | join derived | recall arms / literal / join IN / join derived |
|---|---|---|---|---|---|---|---|---|
| 1 grant (10%) | 4 | 1 | entries | 11.0 | 7.3 | 4.2 | 4.6 | 1.00 / 1.00 / 1.00 / 1.00 |
| 1 grant (10%) | 4 | 1 | count | 13.2 | 9.2 | 8.6 | 9.0 | 1.00 / 1.00 / 1.00 / 1.00 |
| 1 grant (10%) | 4 | 1 | top10 | 1.6 | 2.0 | 8.8 | 8.8 | 1.00 / 1.00 / 1.00 / 1.00 |
| 10 grants (1%) | 22 | 1 | entries | 1.5 | 1.6 | 1.8 | 1.9 | 1.00 / 1.00 / 1.00 / 1.00 |
| 10 grants (1%) | 22 | 1 | count | 7.0 | 2.0 | 7.9 | 7.8 | 1.00 / 1.00 / 1.00 / 1.00 |
| 10 grants (1%) | 22 | 1 | top10 | 4.1 | 2.2 | 15.3 | 15.4 | 1.00 / 1.00 / 1.00 / 1.00 |
| 100 grants (10%) | 202 | 1 | entries | 10.3 | — | 4.6 | 4.4 | 1.00 / — / 1.00 / 1.00 |
| 100 grants (10%) | 202 | 1 | count | 20.2 | — | 9.8 | 10.1 | 1.00 / — / 1.00 / 1.00 |
| 100 grants (10%) | 202 | 1 | top10 | 3.5 | — | 16.9 | 17.2 | 1.00 / — / 1.00 / 1.00 |
| 500 grants (50%) | 1002 | 3 | entries | 81.6 | — | 15.2 | 16.0 | 1.00 / — / 1.00 / 1.00 |
| 500 grants (50%) | 1002 | 3 | count | 140.1 | — | 19.8 | 18.8 | 1.00 / — / 1.00 / 1.00 |
| 500 grants (50%) | 1002 | 3 | top10 | 11.2 | — | 16.0 | 16.1 | 1.00 / — / 1.00 / 1.00 |
| open root, 50 holes | 154 | 1 | entries | 67.4 | — | 25.3 | 33.0 | 1.00 / — / 1.00 / 1.00 |
| open root, 50 holes | 154 | 1 | count | 145.6 | — | 24.4 | 25.8 | 1.00 / — / 1.00 / 1.00 |
| open root, 50 holes | 154 | 1 | top10 | 1.9 | — | 13.8 | 14.8 | 1.00 / — / 1.00 / 1.00 |
| 10 grants + owns 2% | 22 | 1 | entries | 2.3 | 3.1 | 2.5 | 3.0 | 1.00 / 1.00 / 1.00 / 1.00 |
| 10 grants + owns 2% | 22 | 1 | count | 9.4 | 8.2 | 8.2 | 7.9 | 1.00 / 1.00 / 1.00 / 1.00 |
| 10 grants + owns 2% | 22 | 1 | top10 | 2.1 | 2.2 | 10.4 | 10.2 | 1.00 / 1.00 / 1.00 / 1.00 |

Plan of the join's count statement, 100 grants:

```
Finalize Aggregate  (cost=67054.00..67054.01 rows=1 width=8) (actual time=17.781..19.826 rows=1 loops=1)
  ->  Gather  (cost=67053.78..67053.99 rows=2 width=8) (actual time=17.777..19.824 rows=3 loops=1)
        Workers Planned: 2
        Workers Launched: 2
        ->  Partial Aggregate  (cost=66053.78..66053.79 rows=1 width=8) (actual time=14.664..14.669 rows=1 loops=3)
              ->  Hash Join  (cost=59422.31..64619.88 rows=573559 width=0) (actual time=4.332..14.476 rows=4000 loops=3)
                    Hash Cond: (c.entry_id = e.id)
                    ->  Parallel Index Only Scan using ix_rj_91fb7dc4_ce on rj_91fb7dc4_c c  (cost=0.29..2870.29 rows=50500 width=8) (actual time=0.021..4.267 rows=40400 loops=3)
                          Heap Fetches: 121200
                    ->  Hash  (cost=51868.83..51868.83 rows=460335 width=8) (actual time=3.181..3.185 rows=4100 loops=3)
                          Buckets: 262144  Batches: 4  Memory Usage: 2089kB
                          ->  HashAggregate  (cost=43669.11..51868.83 rows=460335 width=8) (actual time=2.055..2.705 rows=4100 loops=3)
                                Group Key: e.id
                                Planned Partitions: 8  Batches: 1  Memory Usage: 3345kB
                                Worker 0:  Batches: 1  Memory Usage: 3345kB
                                Worker 1:  Batches: 1  Memory Usage: 3345kB
                                ->  Append  (cost=0.29..18926.11 rows=460335 width=8) (actual time=0.037..1.318 rows=4100 loops=3)
                                      ->  Nested Loop  (cost=0.29..699.76 rows=100 width=8) (actual time=0.037..0.320 rows=100 loops=3)
                                            ->  Function Scan on ap  (cost=0.01..1.00 rows=100 width=32) (actual time=0.022..0.029 rows=100 loops=3)
                                            ->  Index Scan using ux_rj_91fb7dc4_path on rj_91fb7dc4_e e  (cost=0.29..6.99 rows=1 width=27) (actual time=0.003..0.003 rows=1 loops=300)
                                                  Index Cond: ((path)::text = (ap.lo)::text)
                                      ->  Nested Loop  (cost=0.29..15908.00 rows=460233 width=8) (actual time=0.016..0.773 rows=4000 loops=3)
                                            ->  Function Scan on ar  (cost=0.01..1.00 rows=100 width=64) (actual time=0.011..0.018 rows=100 loops=3)
                                            ->  Index Scan using ux_rj_91fb7dc4_path on rj_91fb7dc4_e e_1  (cost=0.29..113.05 rows=4602 width=27) (actual time=0.002..0.005 rows=40 loops=300)
                                                  Index Cond: (((path)::text > (ar.lo)::text) AND ((path)::text < (ar.hi)::text))
                                      ->  Nested Loop  (cost=0.29..8.33 rows=1 width=8) (actual time=0.017..0.017 rows=0 loops=3)
                                            Join Filter: ((e_2.path)::text = (o0p.lo)::text)
                                            ->  Function Scan on o0p  (cost=0.01..0.01 rows=1 width=32) (actual time=0.007..0.007 rows=1 loops=3)
                                            ->  Index Scan using ix_rj_91fb7dc4_owner on rj_91fb7dc4_e e_2  (cost=0.29..8.31 rows=1 width=27) (actual time=0.010..0.010 rows=0 loops=3)
                                                  Index Cond: ((owner_id)::text = 'c'::text)
                                      ->  Nested Loop  (cost=0.29..8.34 rows=1 width=8) (actual time=0.007..0.008 rows=0 loops=3)
                                            Join Filter: (((e_3.path)::text > (o0r.lo)::text) AND ((e_3.path)::text < (o0r.hi)::text))
                                            ->  Function Scan on o0r  (cost=0.01..0.01 rows=1 width=64) (actual time=0.004..0.004 rows=1 loops=3)
                                            ->  Index Scan using ix_rj_91fb7dc4_owner on rj_91fb7dc4_e e_3  (cost=0.29..8.31 rows=1 width=27) (actual time=0.003..0.003 rows=0 loops=3)
                                                  Index Cond: ((owner_id)::text = 'c'::text)
Planning Time: 0.224 ms
Execution Time: 19.948 ms
```

Total wall time 7s.
