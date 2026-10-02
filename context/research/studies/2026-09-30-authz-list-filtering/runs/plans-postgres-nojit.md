## postgres — 50,000 entries, 500 folder grants, the count statement, jit=off

### like (first 400 arms) (134 ms with EXPLAIN)

```
Aggregate (actual rows=1 loops=1)
  ->  Hash Join (actual rows=20000 loops=1)
        Hash Cond: (azq_c5d99249_docs.entry_id = azq_c5d99249_entry.entry_id)
        ->  Seq Scan on azq_c5d99249_docs (actual rows=50000 loops=1)
        ->  Hash (actual rows=20000 loops=1)
              Buckets: 32768  Batches: 1  Memory Usage: 960kB
              ->  Bitmap Heap Scan on azq_c5d99249_entry (actual rows=20000 loops=1)
                    Recheck Cond: (((path)::text = '/t00/f000'::text) OR ((path)::text ~~ '/t00/f000/%'::text) OR ((path)::text = '/t00/f002'::text) OR ((path):
                    Filter: (((path)::text = '/t00/f000'::text) OR ((path)::text ~~ '/t00/f000/%'::text) OR ((path)::text = '/t00/f002'::text) OR ((path)::text 
                    Heap Blocks: exact=247
                    ->  BitmapOr (actual rows=0 loops=1)
                          ... 800 Bitmap Index Scan children elided by the study (one per `=` and one per range) ...
Planning Time: 5.971 ms
Execution Time: 117.254 ms
```

### tree (first 1,000 ranges) (47 ms with EXPLAIN)

```
Aggregate (actual rows=1 loops=1)
  ->  Nested Loop (actual rows=25000 loops=1)
        ->  Seq Scan on azq_c5d99249_entry (actual rows=25000 loops=1)
              Filter: (CASE WHEN ((path)::text < '/t05/f010'::text) THEN CASE WHEN ((path)::text < '/t02/f048'::text) THEN CASE WHEN ((path)::text < '/t01/f017/
              Rows Removed by Filter: 25000
        ->  Index Scan using ix_azq_c5d99249_docs_entry_id on azq_c5d99249_docs (actual rows=1 loops=25000)
              Index Cond: (entry_id = azq_c5d99249_entry.entry_id)
Planning Time: 2.862 ms
Execution Time: 27.385 ms
```

### drive (13 ms with EXPLAIN)

```
Aggregate (actual rows=1 loops=1)
  ->  Hash Join (actual rows=25000 loops=1)
        Hash Cond: (azq_c5d99249_entry.entry_id = azq_c5d99249_docs.entry_id)
        ->  Nested Loop (actual rows=25000 loops=1)
              ->  Seq Scan on azq_c5d99249_cover (actual rows=1000 loops=1)
                    Filter: (set_id = 0)
              ->  Index Scan using ix_azq_c5d99249_entry_path on azq_c5d99249_entry (actual rows=25 loops=1000)
        ->  Hash (actual rows=50000 loops=1)
              Buckets: 65536  Batches: 1  Memory Usage: 2466kB
              ->  Seq Scan on azq_c5d99249_docs (actual rows=50000 loops=1)
Planning Time: 0.281 ms
Execution Time: 10.502 ms
```

### values (first 1,000 ranges) (14 ms with EXPLAIN)

```
Aggregate (actual rows=1 loops=1)
  ->  Hash Join (actual rows=25000 loops=1)
        Hash Cond: (azq_c5d99249_entry.entry_id = azq_c5d99249_docs.entry_id)
        ->  Nested Loop (actual rows=25000 loops=1)
              ->  Values Scan on "*VALUES*" (actual rows=1000 loops=1)
              ->  Index Scan using ix_azq_c5d99249_entry_path on azq_c5d99249_entry (actual rows=25 loops=1000)
        ->  Hash (actual rows=50000 loops=1)
              Buckets: 65536  Batches: 1  Memory Usage: 2466kB
              ->  Seq Scan on azq_c5d99249_docs (actual rows=50000 loops=1)
Planning Time: 0.414 ms
Execution Time: 10.595 ms
```
