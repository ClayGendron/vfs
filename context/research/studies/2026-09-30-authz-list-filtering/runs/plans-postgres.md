## postgres — 50,000 entries, 500 folder grants, the count statement, jit=on

### like (first 400 arms) (135 ms with EXPLAIN)

```
Aggregate (actual rows=1 loops=1)
  ->  Hash Join (actual rows=20000 loops=1)
        Hash Cond: (azq_fc264cbd_docs.entry_id = azq_fc264cbd_entry.entry_id)
        ->  Seq Scan on azq_fc264cbd_docs (actual rows=50000 loops=1)
        ->  Hash (actual rows=20000 loops=1)
              Buckets: 32768  Batches: 1  Memory Usage: 960kB
              ->  Bitmap Heap Scan on azq_fc264cbd_entry (actual rows=20000 loops=1)
                    Recheck Cond: (((path)::text = '/t00/f000'::text) OR ((path)::text ~~ '/t00/f000/%'::text) OR ((path)::text = '/t00/f002'::text) OR ((path):
                    Filter: (((path)::text = '/t00/f000'::text) OR ((path)::text ~~ '/t00/f000/%'::text) OR ((path)::text = '/t00/f002'::text) OR ((path)::text 
                    Heap Blocks: exact=247
                    ->  BitmapOr (actual rows=0 loops=1)
                          ... 800 Bitmap Index Scan children elided by the study (one per `=` and one per range) ...
Planning Time: 5.786 ms
Execution Time: 116.047 ms
```

### tree (first 1,000 ranges) (1388 ms with EXPLAIN)

```
Aggregate (actual rows=1 loops=1)
  ->  Nested Loop (actual rows=25000 loops=1)
        ->  Seq Scan on azq_fc264cbd_entry (actual rows=25000 loops=1)
              Filter: (CASE WHEN ((path)::text < '/t05/f010'::text) THEN CASE WHEN ((path)::text < '/t02/f048'::text) THEN CASE WHEN ((path)::text < '/t01/f017/
              Rows Removed by Filter: 25000
        ->  Index Scan using ix_azq_fc264cbd_docs_entry_id on azq_fc264cbd_docs (actual rows=1 loops=25000)
              Index Cond: (entry_id = azq_fc264cbd_entry.entry_id)
Planning Time: 2.754 ms
Execution Time: 1366.085 ms
```

### drive (21 ms with EXPLAIN)

```
Aggregate (actual rows=1 loops=1)
  ->  Hash Join (actual rows=25000 loops=1)
        Hash Cond: (azq_fc264cbd_entry.entry_id = azq_fc264cbd_docs.entry_id)
        ->  Nested Loop (actual rows=25000 loops=1)
              ->  Seq Scan on azq_fc264cbd_cover (actual rows=1000 loops=1)
                    Filter: (set_id = 0)
              ->  Index Scan using ix_azq_fc264cbd_entry_path on azq_fc264cbd_entry (actual rows=25 loops=1000)
        ->  Hash (actual rows=50000 loops=1)
              Buckets: 65536  Batches: 1  Memory Usage: 2466kB
              ->  Seq Scan on azq_fc264cbd_docs (actual rows=50000 loops=1)
Planning Time: 0.303 ms
Execution Time: 16.443 ms
```

### values (first 1,000 ranges) (22 ms with EXPLAIN)

```
Aggregate (actual rows=1 loops=1)
  ->  Hash Join (actual rows=25000 loops=1)
        Hash Cond: (azq_fc264cbd_entry.entry_id = azq_fc264cbd_docs.entry_id)
        ->  Nested Loop (actual rows=25000 loops=1)
              ->  Values Scan on "*VALUES*" (actual rows=1000 loops=1)
              ->  Index Scan using ix_azq_fc264cbd_entry_path on azq_fc264cbd_entry (actual rows=25 loops=1000)
        ->  Hash (actual rows=50000 loops=1)
              Buckets: 65536  Batches: 1  Memory Usage: 2466kB
              ->  Seq Scan on azq_fc264cbd_docs (actual rows=50000 loops=1)
Planning Time: 0.422 ms
Execution Time: 17.799 ms
```
