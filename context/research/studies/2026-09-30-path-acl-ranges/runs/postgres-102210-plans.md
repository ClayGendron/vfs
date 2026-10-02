# Plans — postgres-102210, the 100-spread rights

### entries · a_like · 100 spread

```
Aggregate  (cost=1757.20..1757.21 rows=1 width=8) (actual time=9.876..9.915 rows=1 loops=1)
  Buffers: shared hit=765
  ->  Bitmap Heap Scan on acl_ae3f5e6a_entries e  (cost=1378.30..1732.55 rows=9861 width=0) (actual time=0.450..9.618 rows=5100 loops=1)
        Recheck Cond: ((path = '/t00/f000'::text) OR (path ~~ '/t00/f000/%'::text) OR (path = '/t00/f020'::text) OR (path ~~ '/t00/f020/%'::text) OR (path = '/t00/f040'::text) OR (path ~~ '/t00/f040/%'::text) OR (path =  …
        Filter: ((path = '/t00/f000'::text) OR (path ~~ '/t00/f000/%'::text) OR (path = '/t00/f020'::text) OR (path ~~ '/t00/f020/%'::text) OR (path = '/t00/f040'::text) OR (path ~~ '/t00/f040/%'::text) OR (path = '/t00/ …
        Heap Blocks: exact=142
        Buffers: shared hit=765
        ->  BitmapOr  (cost=1378.30..1378.30 rows=107 width=0) (actual time=0.426..0.465 rows=0 loops=1)
              Buffers: shared hit=623
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.009..0.009 rows=1 loops=1)
                    Index Cond: (path = '/t00/f000'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((path >= '/t00/f000/'::text) AND (path < '/t00/f0000'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t00/f020'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((path >= '/t00/f020/'::text) AND (path < '/t00/f0200'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t00/f040'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.003 rows=50 loops=1)
                    Index Cond: ((path >= '/t00/f040/'::text) AND (path < '/t00/f0400'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t00/f060'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((path >= '/t00/f060/'::text) AND (path < '/t00/f0600'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t00/f080'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((path >= '/t00/f080/'::text) AND (path < '/t00/f0800'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t00/f100'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((path >= '/t00/f100/'::text) AND (path < '/t00/f1000'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t00/f120'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t00/f120/'::text) AND (path < '/t00/f1200'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t00/f140'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.003 rows=50 loops=1)
                    Index Cond: ((path >= '/t00/f140/'::text) AND (path < '/t00/f1400'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t00/f160'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t00/f160/'::text) AND (path < '/t00/f1600'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t00/f180'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t00/f180/'::text) AND (path < '/t00/f1800'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t01/f000'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((path >= '/t01/f000/'::text) AND (path < '/t01/f0000'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t01/f020'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t01/f020/'::text) AND (path < '/t01/f0200'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                    Index Cond: (path = '/t01/f040'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t01/f040/'::text) AND (path < '/t01/f0400'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t01/f060'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t01/f060/'::text) AND (path < '/t01/f0600'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t01/f080'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t01/f080/'::text) AND (path < '/t01/f0800'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t01/f100'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t01/f100/'::text) AND (path < '/t01/f1000'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t01/f120'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t01/f120/'::text) AND (path < '/t01/f1200'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t01/f140'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t01/f140/'::text) AND (path < '/t01/f1400'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t01/f160'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t01/f160/'::text) AND (path < '/t01/f1600'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t01/f180'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.003 rows=50 loops=1)
                    Index Cond: ((path >= '/t01/f180/'::text) AND (path < '/t01/f1800'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t02/f000'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t02/f000/'::text) AND (path < '/t02/f0000'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t02/f020'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t02/f020/'::text) AND (path < '/t02/f0200'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t02/f040'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t02/f040/'::text) AND (path < '/t02/f0400'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t02/f060'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t02/f060/'::text) AND (path < '/t02/f0600'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t02/f080'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t02/f080/'::text) AND (path < '/t02/f0800'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t02/f100'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.003 rows=50 loops=1)
                    Index Cond: ((path >= '/t02/f100/'::text) AND (path < '/t02/f1000'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t02/f120'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t02/f120/'::text) AND (path < '/t02/f1200'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                    Index Cond: (path = '/t02/f140'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t02/f140/'::text) AND (path < '/t02/f1400'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t02/f160'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t02/f160/'::text) AND (path < '/t02/f1600'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t02/f180'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t02/f180/'::text) AND (path < '/t02/f1800'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t03/f000'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t03/f000/'::text) AND (path < '/t03/f0000'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t03/f020'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t03/f020/'::text) AND (path < '/t03/f0200'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t03/f040'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t03/f040/'::text) AND (path < '/t03/f0400'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t03/f060'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.003 rows=50 loops=1)
                    Index Cond: ((path >= '/t03/f060/'::text) AND (path < '/t03/f0600'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t03/f080'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t03/f080/'::text) AND (path < '/t03/f0800'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t03/f100'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t03/f100/'::text) AND (path < '/t03/f1000'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t03/f120'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t03/f120/'::text) AND (path < '/t03/f1200'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                    Index Cond: (path = '/t03/f140'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t03/f140/'::text) AND (path < '/t03/f1400'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t03/f160'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t03/f160/'::text) AND (path < '/t03/f1600'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t03/f180'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t03/f180/'::text) AND (path < '/t03/f1800'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t04/f000'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=50 loops=1)
                    Index Cond: ((path >= '/t04/f000/'::text) AND (path < '/t04/f0000'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t04/f020'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t04/f020/'::text) AND (path < '/t04/f0200'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t04/f040'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t04/f040/'::text) AND (path < '/t04/f0400'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t04/f060'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t04/f060/'::text) AND (path < '/t04/f0600'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t04/f080'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t04/f080/'::text) AND (path < '/t04/f0800'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t04/f100'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t04/f100/'::text) AND (path < '/t04/f1000'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                    Index Cond: (path = '/t04/f120'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.003 rows=50 loops=1)
                    Index Cond: ((path >= '/t04/f120/'::text) AND (path < '/t04/f1200'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t04/f140'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t04/f140/'::text) AND (path < '/t04/f1400'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                    Index Cond: (path = '/t04/f160'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t04/f160/'::text) AND (path < '/t04/f1600'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                    Index Cond: (path = '/t04/f180'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t04/f180/'::text) AND (path < '/t04/f1800'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                    Index Cond: (path = '/t05/f000'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((path >= '/t05/f000/'::text) AND (path < '/t05/f0000'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                    Index Cond: (path = '/t05/f020'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((path >= '/t05/f020/'::text) AND (path < '/t05/f0200'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t05/f040'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t05/f040/'::text) AND (path < '/t05/f0400'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t05/f060'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t05/f060/'::text) AND (path < '/t05/f0600'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t05/f080'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t05/f080/'::text) AND (path < '/t05/f0800'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t05/f100'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t05/f100/'::text) AND (path < '/t05/f1000'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t05/f120'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t05/f120/'::text) AND (path < '/t05/f1200'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t05/f140'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.003 rows=50 loops=1)
                    Index Cond: ((path >= '/t05/f140/'::text) AND (path < '/t05/f1400'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t05/f160'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t05/f160/'::text) AND (path < '/t05/f1600'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t05/f180'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t05/f180/'::text) AND (path < '/t05/f1800'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t06/f000'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t06/f000/'::text) AND (path < '/t06/f0000'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t06/f020'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t06/f020/'::text) AND (path < '/t06/f0200'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                    Index Cond: (path = '/t06/f040'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t06/f040/'::text) AND (path < '/t06/f0400'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t06/f060'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t06/f060/'::text) AND (path < '/t06/f0600'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t06/f080'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t06/f080/'::text) AND (path < '/t06/f0800'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t06/f100'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t06/f100/'::text) AND (path < '/t06/f1000'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t06/f120'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t06/f120/'::text) AND (path < '/t06/f1200'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t06/f140'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.003 rows=50 loops=1)
                    Index Cond: ((path >= '/t06/f140/'::text) AND (path < '/t06/f1400'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t06/f160'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t06/f160/'::text) AND (path < '/t06/f1600'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t06/f180'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t06/f180/'::text) AND (path < '/t06/f1800'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t07/f000'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t07/f000/'::text) AND (path < '/t07/f0000'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t07/f020'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t07/f020/'::text) AND (path < '/t07/f0200'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t07/f040'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t07/f040/'::text) AND (path < '/t07/f0400'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t07/f060'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t07/f060/'::text) AND (path < '/t07/f0600'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t07/f080'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=50 loops=1)
                    Index Cond: ((path >= '/t07/f080/'::text) AND (path < '/t07/f0800'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t07/f100'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t07/f100/'::text) AND (path < '/t07/f1000'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                    Index Cond: (path = '/t07/f120'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((path >= '/t07/f120/'::text) AND (path < '/t07/f1200'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t07/f140'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=50 loops=1)
                    Index Cond: ((path >= '/t07/f140/'::text) AND (path < '/t07/f1400'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t07/f160'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((path >= '/t07/f160/'::text) AND (path < '/t07/f1600'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t07/f180'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((path >= '/t07/f180/'::text) AND (path < '/t07/f1800'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t08/f000'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((path >= '/t08/f000/'::text) AND (path < '/t08/f0000'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                    Index Cond: (path = '/t08/f020'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((path >= '/t08/f020/'::text) AND (path < '/t08/f0200'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                    Index Cond: (path = '/t08/f040'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=50 loops=1)
                    Index Cond: ((path >= '/t08/f040/'::text) AND (path < '/t08/f0400'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                    Index Cond: (path = '/t08/f060'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((path >= '/t08/f060/'::text) AND (path < '/t08/f0600'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t08/f080'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=50 loops=1)
                    Index Cond: ((path >= '/t08/f080/'::text) AND (path < '/t08/f0800'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t08/f100'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((path >= '/t08/f100/'::text) AND (path < '/t08/f1000'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t08/f120'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((path >= '/t08/f120/'::text) AND (path < '/t08/f1200'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                    Index Cond: (path = '/t08/f140'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((path >= '/t08/f140/'::text) AND (path < '/t08/f1400'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                    Index Cond: (path = '/t08/f160'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=50 loops=1)
                    Index Cond: ((path >= '/t08/f160/'::text) AND (path < '/t08/f1600'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t08/f180'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=50 loops=1)
                    Index Cond: ((path >= '/t08/f180/'::text) AND (path < '/t08/f1800'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t09/f000'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=50 loops=1)
                    Index Cond: ((path >= '/t09/f000/'::text) AND (path < '/t09/f0000'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t09/f020'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((path >= '/t09/f020/'::text) AND (path < '/t09/f0200'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t09/f040'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((path >= '/t09/f040/'::text) AND (path < '/t09/f0400'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                    Index Cond: (path = '/t09/f060'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((path >= '/t09/f060/'::text) AND (path < '/t09/f0600'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t09/f080'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((path >= '/t09/f080/'::text) AND (path < '/t09/f0800'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                    Index Cond: (path = '/t09/f100'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((path >= '/t09/f100/'::text) AND (path < '/t09/f1000'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t09/f120'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((path >= '/t09/f120/'::text) AND (path < '/t09/f1200'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                    Index Cond: (path = '/t09/f140'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((path >= '/t09/f140/'::text) AND (path < '/t09/f1400'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                    Index Cond: (path = '/t09/f160'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((path >= '/t09/f160/'::text) AND (path < '/t09/f1600'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                    Index Cond: (path = '/t09/f180'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((path >= '/t09/f180/'::text) AND (path < '/t09/f1800'::text))
                    Buffers: shared hit=4
Planning:
  Buffers: shared hit=28
Planning Time: 3.430 ms
Execution Time: 10.610 ms
```

### entries · b_range · 100 spread

```
Aggregate  (cost=1271.86..1271.87 rows=1 width=8) (actual time=2.836..2.908 rows=1 loops=1)
  Buffers: shared hit=765
  ->  Bitmap Heap Scan on acl_ae3f5e6a_entries e  (cost=890.60..1271.60 rows=107 width=0) (actual time=1.156..2.361 rows=5100 loops=1)
        Recheck Cond: ((path = '/t00/f000'::text) OR ((path >= '/t00/f000/'::text) AND (path < '/t00/f0000'::text)) OR (path = '/t00/f020'::text) OR ((path >= '/t00/f020/'::text) AND (path < '/t00/f0200'::text)) OR (path …
        Heap Blocks: exact=142
        Buffers: shared hit=765
        ->  BitmapOr  (cost=890.60..890.60 rows=107 width=0) (actual time=1.123..1.194 rows=0 loops=1)
              Buffers: shared hit=623
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.010..0.011 rows=1 loops=1)
                    Index Cond: (path = '/t00/f000'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.007 rows=50 loops=1)
                    Index Cond: ((path >= '/t00/f000/'::text) AND (path < '/t00/f0000'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.005..0.005 rows=1 loops=1)
                    Index Cond: (path = '/t00/f020'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t00/f020/'::text) AND (path < '/t00/f0200'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                    Index Cond: (path = '/t00/f040'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t00/f040/'::text) AND (path < '/t00/f0400'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t00/f060'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t00/f060/'::text) AND (path < '/t00/f0600'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t00/f080'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t00/f080/'::text) AND (path < '/t00/f0800'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t00/f100'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t00/f100/'::text) AND (path < '/t00/f1000'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t00/f120'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t00/f120/'::text) AND (path < '/t00/f1200'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t00/f140'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t00/f140/'::text) AND (path < '/t00/f1400'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.029..0.029 rows=1 loops=1)
                    Index Cond: (path = '/t00/f160'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                    Index Cond: ((path >= '/t00/f160/'::text) AND (path < '/t00/f1600'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t00/f180'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t00/f180/'::text) AND (path < '/t00/f1800'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t01/f000'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t01/f000/'::text) AND (path < '/t01/f0000'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t01/f020'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t01/f020/'::text) AND (path < '/t01/f0200'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t01/f040'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t01/f040/'::text) AND (path < '/t01/f0400'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                    Index Cond: (path = '/t01/f060'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t01/f060/'::text) AND (path < '/t01/f0600'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                    Index Cond: (path = '/t01/f080'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t01/f080/'::text) AND (path < '/t01/f0800'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t01/f100'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t01/f100/'::text) AND (path < '/t01/f1000'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                    Index Cond: (path = '/t01/f120'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t01/f120/'::text) AND (path < '/t01/f1200'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t01/f140'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t01/f140/'::text) AND (path < '/t01/f1400'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t01/f160'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t01/f160/'::text) AND (path < '/t01/f1600'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t01/f180'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.007 rows=50 loops=1)
                    Index Cond: ((path >= '/t01/f180/'::text) AND (path < '/t01/f1800'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t02/f000'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t02/f000/'::text) AND (path < '/t02/f0000'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t02/f020'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t02/f020/'::text) AND (path < '/t02/f0200'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                    Index Cond: (path = '/t02/f040'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t02/f040/'::text) AND (path < '/t02/f0400'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t02/f060'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t02/f060/'::text) AND (path < '/t02/f0600'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t02/f080'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t02/f080/'::text) AND (path < '/t02/f0800'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                    Index Cond: (path = '/t02/f100'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                    Index Cond: ((path >= '/t02/f100/'::text) AND (path < '/t02/f1000'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t02/f120'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t02/f120/'::text) AND (path < '/t02/f1200'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t02/f140'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t02/f140/'::text) AND (path < '/t02/f1400'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t02/f160'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t02/f160/'::text) AND (path < '/t02/f1600'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t02/f180'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t02/f180/'::text) AND (path < '/t02/f1800'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t03/f000'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t03/f000/'::text) AND (path < '/t03/f0000'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t03/f020'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.009..0.010 rows=50 loops=1)
                    Index Cond: ((path >= '/t03/f020/'::text) AND (path < '/t03/f0200'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.005..0.005 rows=1 loops=1)
                    Index Cond: (path = '/t03/f040'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t03/f040/'::text) AND (path < '/t03/f0400'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                    Index Cond: (path = '/t03/f060'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t03/f060/'::text) AND (path < '/t03/f0600'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                    Index Cond: (path = '/t03/f080'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t03/f080/'::text) AND (path < '/t03/f0800'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t03/f100'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t03/f100/'::text) AND (path < '/t03/f1000'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                    Index Cond: (path = '/t03/f120'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t03/f120/'::text) AND (path < '/t03/f1200'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t03/f140'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t03/f140/'::text) AND (path < '/t03/f1400'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t03/f160'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t03/f160/'::text) AND (path < '/t03/f1600'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t03/f180'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t03/f180/'::text) AND (path < '/t03/f1800'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t04/f000'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t04/f000/'::text) AND (path < '/t04/f0000'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t04/f020'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t04/f020/'::text) AND (path < '/t04/f0200'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t04/f040'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t04/f040/'::text) AND (path < '/t04/f0400'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t04/f060'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t04/f060/'::text) AND (path < '/t04/f0600'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                    Index Cond: (path = '/t04/f080'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t04/f080/'::text) AND (path < '/t04/f0800'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t04/f100'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t04/f100/'::text) AND (path < '/t04/f1000'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t04/f120'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t04/f120/'::text) AND (path < '/t04/f1200'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t04/f140'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t04/f140/'::text) AND (path < '/t04/f1400'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                    Index Cond: (path = '/t04/f160'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t04/f160/'::text) AND (path < '/t04/f1600'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t04/f180'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t04/f180/'::text) AND (path < '/t04/f1800'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t05/f000'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t05/f000/'::text) AND (path < '/t05/f0000'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t05/f020'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t05/f020/'::text) AND (path < '/t05/f0200'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t05/f040'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t05/f040/'::text) AND (path < '/t05/f0400'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t05/f060'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t05/f060/'::text) AND (path < '/t05/f0600'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t05/f080'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t05/f080/'::text) AND (path < '/t05/f0800'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t05/f100'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t05/f100/'::text) AND (path < '/t05/f1000'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t05/f120'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t05/f120/'::text) AND (path < '/t05/f1200'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t05/f140'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t05/f140/'::text) AND (path < '/t05/f1400'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                    Index Cond: (path = '/t05/f160'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t05/f160/'::text) AND (path < '/t05/f1600'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t05/f180'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t05/f180/'::text) AND (path < '/t05/f1800'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t06/f000'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t06/f000/'::text) AND (path < '/t06/f0000'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t06/f020'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t06/f020/'::text) AND (path < '/t06/f0200'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t06/f040'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t06/f040/'::text) AND (path < '/t06/f0400'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                    Index Cond: (path = '/t06/f060'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t06/f060/'::text) AND (path < '/t06/f0600'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                    Index Cond: (path = '/t06/f080'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t06/f080/'::text) AND (path < '/t06/f0800'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t06/f100'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t06/f100/'::text) AND (path < '/t06/f1000'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t06/f120'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t06/f120/'::text) AND (path < '/t06/f1200'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t06/f140'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t06/f140/'::text) AND (path < '/t06/f1400'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                    Index Cond: (path = '/t06/f160'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t06/f160/'::text) AND (path < '/t06/f1600'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t06/f180'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t06/f180/'::text) AND (path < '/t06/f1800'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                    Index Cond: (path = '/t07/f000'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t07/f000/'::text) AND (path < '/t07/f0000'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t07/f020'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t07/f020/'::text) AND (path < '/t07/f0200'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                    Index Cond: (path = '/t07/f040'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t07/f040/'::text) AND (path < '/t07/f0400'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                    Index Cond: (path = '/t07/f060'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.014..0.015 rows=50 loops=1)
                    Index Cond: ((path >= '/t07/f060/'::text) AND (path < '/t07/f0600'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t07/f080'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t07/f080/'::text) AND (path < '/t07/f0800'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                    Index Cond: (path = '/t07/f100'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t07/f100/'::text) AND (path < '/t07/f1000'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                    Index Cond: (path = '/t07/f120'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                    Index Cond: ((path >= '/t07/f120/'::text) AND (path < '/t07/f1200'::text))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t07/f140'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                    Index Cond: ((path >= '/t07/f140/'::text) AND (path < '/t07/f1400'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                    Index Cond: (path = '/t07/f160'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                    Index Cond: ((path >= '/t07/f160/'::text) AND (path < '/t07/f1600'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t07/f180'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                    Index Cond: ((path >= '/t07/f180/'::text) AND (path < '/t07/f1800'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                    Index Cond: (path = '/t08/f000'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                    Index Cond: ((path >= '/t08/f000/'::text) AND (path < '/t08/f0000'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t08/f020'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                    Index Cond: ((path >= '/t08/f020/'::text) AND (path < '/t08/f0200'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t08/f040'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.008 rows=50 loops=1)
                    Index Cond: ((path >= '/t08/f040/'::text) AND (path < '/t08/f0400'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t08/f060'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                    Index Cond: ((path >= '/t08/f060/'::text) AND (path < '/t08/f0600'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t08/f080'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                    Index Cond: ((path >= '/t08/f080/'::text) AND (path < '/t08/f0800'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t08/f100'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.080..0.081 rows=50 loops=1)
                    Index Cond: ((path >= '/t08/f100/'::text) AND (path < '/t08/f1000'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=1 loops=1)
                    Index Cond: (path = '/t08/f120'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                    Index Cond: ((path >= '/t08/f120/'::text) AND (path < '/t08/f1200'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                    Index Cond: (path = '/t08/f140'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.008 rows=50 loops=1)
                    Index Cond: ((path >= '/t08/f140/'::text) AND (path < '/t08/f1400'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t08/f160'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                    Index Cond: ((path >= '/t08/f160/'::text) AND (path < '/t08/f1600'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t08/f180'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                    Index Cond: ((path >= '/t08/f180/'::text) AND (path < '/t08/f1800'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t09/f000'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.009..0.009 rows=50 loops=1)
                    Index Cond: ((path >= '/t09/f000/'::text) AND (path < '/t09/f0000'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                    Index Cond: (path = '/t09/f020'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.008 rows=50 loops=1)
                    Index Cond: ((path >= '/t09/f020/'::text) AND (path < '/t09/f0200'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                    Index Cond: (path = '/t09/f040'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                    Index Cond: ((path >= '/t09/f040/'::text) AND (path < '/t09/f0400'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t09/f060'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                    Index Cond: ((path >= '/t09/f060/'::text) AND (path < '/t09/f0600'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                    Index Cond: (path = '/t09/f080'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                    Index Cond: ((path >= '/t09/f080/'::text) AND (path < '/t09/f0800'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t09/f100'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                    Index Cond: ((path >= '/t09/f100/'::text) AND (path < '/t09/f1000'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                    Index Cond: (path = '/t09/f120'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                    Index Cond: ((path >= '/t09/f120/'::text) AND (path < '/t09/f1200'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=1 loops=1)
                    Index Cond: (path = '/t09/f140'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                    Index Cond: ((path >= '/t09/f140/'::text) AND (path < '/t09/f1400'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t09/f160'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.008 rows=50 loops=1)
                    Index Cond: ((path >= '/t09/f160/'::text) AND (path < '/t09/f1600'::text))
                    Buffers: shared hit=4
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                    Index Cond: (path = '/t09/f180'::text)
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.038..0.038 rows=50 loops=1)
                    Index Cond: ((path >= '/t09/f180/'::text) AND (path < '/t09/f1800'::text))
                    Buffers: shared hit=4
Planning:
  Buffers: shared hit=28
Planning Time: 2.044 ms
Execution Time: 4.009 ms
```

### entries · c_values · 100 spread

```
Aggregate  (cost=39052.47..39052.48 rows=1 width=8) (actual time=1.769..1.769 rows=1 loops=1)
  Buffers: shared hit=324
  ->  Nested Loop  (cost=0.42..39038.25 rows=5689 width=0) (actual time=0.012..1.574 rows=5100 loops=1)
        Buffers: shared hit=324
        ->  Values Scan on "*VALUES*"  (cost=0.00..1.25 rows=100 width=64) (actual time=0.001..0.018 rows=100 loops=1)
        ->  Index Only Scan using acl_ae3f5e6a_ix_path on acl_ae3f5e6a_entries e  (cost=0.42..389.80 rows=57 width=19) (actual time=0.002..0.011 rows=51 loops=100)
              Index Cond: ((path >= "*VALUES*".column1) AND (path < "*VALUES*".column2))
              Filter: ((path = "*VALUES*".column1) OR (substr(path, (length("*VALUES*".column1) + 1), 1) = '/'::text))
              Rows Removed by Filter: 1
              Heap Fetches: 0
              Buffers: shared hit=324
Planning Time: 0.094 ms
Execution Time: 1.782 ms
```

### entries · c_temp · 100 spread

```
Aggregate  (cost=39053.22..39053.23 rows=1 width=8) (actual time=4.110..4.111 rows=1 loops=1)
  Buffers: shared hit=324, local hit=1
  ->  Nested Loop  (cost=0.42..39039.00 rows=5689 width=0) (actual time=0.032..3.644 rows=5100 loops=1)
        Buffers: shared hit=324, local hit=1
        ->  Seq Scan on g_tmp g  (cost=0.00..2.00 rows=100 width=21) (actual time=0.008..0.020 rows=100 loops=1)
              Buffers: local hit=1
        ->  Index Only Scan using acl_ae3f5e6a_ix_path on acl_ae3f5e6a_entries e  (cost=0.42..389.80 rows=57 width=19) (actual time=0.006..0.026 rows=51 loops=100)
              Index Cond: ((path >= g.p) AND (path < g.hi))
              Filter: ((path = g.p) OR (substr(path, (length(g.p) + 1), 1) = '/'::text))
              Rows Removed by Filter: 1
              Heap Fetches: 0
              Buffers: shared hit=324
Planning Time: 0.146 ms
Execution Time: 4.144 ms
```

### entries · d_or · 100 spread

```
Aggregate  (cost=4063.51..4063.52 rows=1 width=8) (actual time=2.013..2.048 rows=1 loops=1)
  Buffers: shared hit=357
  ->  Bitmap Heap Scan on acl_ae3f5e6a_entries e  (cost=604.22..4051.10 rows=4965 width=0) (actual time=0.715..1.647 rows=5100 loops=1)
        Recheck Cond: (((pre >= 1) AND (pre <= 51)) OR ((pre >= 1023) AND (pre <= 1073)) OR ((pre >= 2045) AND (pre <= 2095)) OR ((pre >= 3067) AND (pre <= 3117)) OR ((pre >= 4089) AND (pre <= 4139)) OR ((pre >= 5111) AN …
        Heap Blocks: exact=142
        Buffers: shared hit=357
        ->  BitmapOr  (cost=604.22..604.22 rows=5088 width=0) (actual time=0.683..0.717 rows=0 loops=1)
              Buffers: shared hit=215
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.015..0.015 rows=51 loops=1)
                    Index Cond: ((pre >= 1) AND (pre <= 51))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.008..0.008 rows=51 loops=1)
                    Index Cond: ((pre >= 1023) AND (pre <= 1073))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.82 rows=53 width=0) (actual time=0.007..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 2045) AND (pre <= 2095))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.79 rows=50 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 3067) AND (pre <= 3117))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.76 rows=47 width=0) (actual time=0.006..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 4089) AND (pre <= 4139))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.77 rows=48 width=0) (actual time=0.008..0.009 rows=51 loops=1)
                    Index Cond: ((pre >= 5111) AND (pre <= 5161))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.79 rows=50 width=0) (actual time=0.007..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 6133) AND (pre <= 6183))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.007..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 7155) AND (pre <= 7205))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.79 rows=50 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 8177) AND (pre <= 8227))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.84 rows=55 width=0) (actual time=0.007..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 9199) AND (pre <= 9249))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.77 rows=48 width=0) (actual time=0.008..0.009 rows=51 loops=1)
                    Index Cond: ((pre >= 10222) AND (pre <= 10272))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.77 rows=48 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 11244) AND (pre <= 11294))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.77 rows=48 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 12266) AND (pre <= 12316))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.79 rows=50 width=0) (actual time=0.007..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 13288) AND (pre <= 13338))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 14310) AND (pre <= 14360))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.79 rows=50 width=0) (actual time=0.008..0.008 rows=51 loops=1)
                    Index Cond: ((pre >= 15332) AND (pre <= 15382))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.79 rows=50 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 16354) AND (pre <= 16404))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.76 rows=47 width=0) (actual time=0.007..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 17376) AND (pre <= 17426))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 18398) AND (pre <= 18448))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.007..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 19420) AND (pre <= 19470))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.81 rows=52 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 20443) AND (pre <= 20493))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 21465) AND (pre <= 21515))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.75 rows=46 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 22487) AND (pre <= 22537))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.72 rows=43 width=0) (actual time=0.006..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 23509) AND (pre <= 23559))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 24531) AND (pre <= 24581))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.007..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 25553) AND (pre <= 25603))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.77 rows=48 width=0) (actual time=0.006..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 26575) AND (pre <= 26625))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.82 rows=53 width=0) (actual time=0.007..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 27597) AND (pre <= 27647))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.88 rows=59 width=0) (actual time=0.007..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 28619) AND (pre <= 28669))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.77 rows=48 width=0) (actual time=0.008..0.008 rows=51 loops=1)
                    Index Cond: ((pre >= 29641) AND (pre <= 29691))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.83 rows=54 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 30664) AND (pre <= 30714))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.81 rows=52 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 31686) AND (pre <= 31736))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.81 rows=52 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 32708) AND (pre <= 32758))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.82 rows=53 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 33730) AND (pre <= 33780))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.008..0.008 rows=51 loops=1)
                    Index Cond: ((pre >= 34752) AND (pre <= 34802))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.006..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 35774) AND (pre <= 35824))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 36796) AND (pre <= 36846))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 37818) AND (pre <= 37868))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 38840) AND (pre <= 38890))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.007..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 39862) AND (pre <= 39912))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.81 rows=52 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 40885) AND (pre <= 40935))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 41907) AND (pre <= 41957))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.79 rows=50 width=0) (actual time=0.006..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 42929) AND (pre <= 42979))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.84 rows=55 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 43951) AND (pre <= 44001))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.008..0.008 rows=51 loops=1)
                    Index Cond: ((pre >= 44973) AND (pre <= 45023))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.77 rows=48 width=0) (actual time=0.006..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 45995) AND (pre <= 46045))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 47017) AND (pre <= 47067))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 48039) AND (pre <= 48089))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.84 rows=55 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 49061) AND (pre <= 49111))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 50083) AND (pre <= 50133))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.82 rows=53 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 51106) AND (pre <= 51156))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.79 rows=50 width=0) (actual time=0.007..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 52128) AND (pre <= 52178))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.83 rows=54 width=0) (actual time=0.007..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 53150) AND (pre <= 53200))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.82 rows=53 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 54172) AND (pre <= 54222))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.83 rows=54 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 55194) AND (pre <= 55244))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.006..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 56216) AND (pre <= 56266))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.84 rows=55 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 57238) AND (pre <= 57288))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.79 rows=50 width=0) (actual time=0.007..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 58260) AND (pre <= 58310))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.007..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 59282) AND (pre <= 59332))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 60304) AND (pre <= 60354))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.87 rows=58 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 61327) AND (pre <= 61377))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.007..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 62349) AND (pre <= 62399))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.85 rows=56 width=0) (actual time=0.007..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 63371) AND (pre <= 63421))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.008..0.008 rows=51 loops=1)
                    Index Cond: ((pre >= 64393) AND (pre <= 64443))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.79 rows=50 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 65415) AND (pre <= 65465))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.81 rows=52 width=0) (actual time=0.007..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 66437) AND (pre <= 66487))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.82 rows=53 width=0) (actual time=0.006..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 67459) AND (pre <= 67509))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.81 rows=52 width=0) (actual time=0.007..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 68481) AND (pre <= 68531))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.82 rows=53 width=0) (actual time=0.008..0.008 rows=51 loops=1)
                    Index Cond: ((pre >= 69503) AND (pre <= 69553))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 70525) AND (pre <= 70575))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 71548) AND (pre <= 71598))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 72570) AND (pre <= 72620))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.83 rows=54 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 73592) AND (pre <= 73642))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.81 rows=52 width=0) (actual time=0.007..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 74614) AND (pre <= 74664))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 75636) AND (pre <= 75686))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.007..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 76658) AND (pre <= 76708))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.81 rows=52 width=0) (actual time=0.007..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 77680) AND (pre <= 77730))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.81 rows=52 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 78702) AND (pre <= 78752))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.82 rows=53 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 79724) AND (pre <= 79774))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.007..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 80746) AND (pre <= 80796))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.79 rows=50 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 81769) AND (pre <= 81819))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.007..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 82791) AND (pre <= 82841))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.79 rows=50 width=0) (actual time=0.009..0.009 rows=51 loops=1)
                    Index Cond: ((pre >= 83813) AND (pre <= 83863))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.81 rows=52 width=0) (actual time=0.007..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 84835) AND (pre <= 84885))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.81 rows=52 width=0) (actual time=0.007..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 85857) AND (pre <= 85907))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.81 rows=52 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 86879) AND (pre <= 86929))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.79 rows=50 width=0) (actual time=0.007..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 87901) AND (pre <= 87951))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.81 rows=52 width=0) (actual time=0.008..0.008 rows=51 loops=1)
                    Index Cond: ((pre >= 88923) AND (pre <= 88973))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.83 rows=54 width=0) (actual time=0.007..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 89945) AND (pre <= 89995))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.79 rows=50 width=0) (actual time=0.007..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 90967) AND (pre <= 91017))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.77 rows=48 width=0) (actual time=0.007..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 91990) AND (pre <= 92040))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 93012) AND (pre <= 93062))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.79 rows=50 width=0) (actual time=0.008..0.008 rows=51 loops=1)
                    Index Cond: ((pre >= 94034) AND (pre <= 94084))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                    Index Cond: ((pre >= 95056) AND (pre <= 95106))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.006..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 96078) AND (pre <= 96128))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.006..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 97100) AND (pre <= 97150))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.007..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 98122) AND (pre <= 98172))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.81 rows=52 width=0) (actual time=0.008..0.008 rows=51 loops=1)
                    Index Cond: ((pre >= 99144) AND (pre <= 99194))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.82 rows=53 width=0) (actual time=0.007..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 100166) AND (pre <= 100216))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.77 rows=48 width=0) (actual time=0.007..0.007 rows=51 loops=1)
                    Index Cond: ((pre >= 101188) AND (pre <= 101238))
                    Buffers: shared hit=2
Planning:
  Buffers: shared hit=21
Planning Time: 1.074 ms
Execution Time: 2.458 ms
```

### entries · d_values · 100 spread

```
Aggregate  (cost=38068.67..38068.68 rows=1 width=8) (actual time=1.492..1.494 rows=1 loops=1)
  Buffers: shared hit=216
  ->  Nested Loop  (cost=0.29..35229.50 rows=1135667 width=0) (actual time=0.012..1.245 rows=5100 loops=1)
        Buffers: shared hit=216
        ->  Values Scan on "*VALUES*"  (cost=0.00..1.25 rows=100 width=8) (actual time=0.001..0.026 rows=100 loops=1)
        ->  Index Only Scan using acl_ae3f5e6a_ix_pre on acl_ae3f5e6a_entries e  (cost=0.29..238.71 rows=11357 width=4) (actual time=0.003..0.007 rows=51 loops=100)
              Index Cond: ((pre >= "*VALUES*".column1) AND (pre <= "*VALUES*".column2))
              Heap Fetches: 0
              Buffers: shared hit=216
Planning Time: 0.100 ms
Execution Time: 1.513 ms
```

### entries · c_unnest · 100 spread

```
Aggregate  (cost=39052.23..39052.24 rows=1 width=8) (actual time=3.798..3.799 rows=1 loops=1)
  Buffers: shared hit=324
  ->  Nested Loop  (cost=0.42..39038.00 rows=5689 width=0) (actual time=0.049..3.377 rows=5100 loops=1)
        Buffers: shared hit=324
        ->  Function Scan on g  (cost=0.01..1.00 rows=100 width=64) (actual time=0.024..0.043 rows=100 loops=1)
        ->  Index Only Scan using acl_ae3f5e6a_ix_path on acl_ae3f5e6a_entries e  (cost=0.42..389.80 rows=57 width=19) (actual time=0.006..0.026 rows=51 loops=100)
              Index Cond: ((path >= g.p) AND (path < g.hi))
              Filter: ((path = g.p) OR (substr(path, (length(g.p) + 1), 1) = '/'::text))
              Rows Removed by Filter: 1
              Heap Fetches: 0
              Buffers: shared hit=324
Planning Time: 0.191 ms
Execution Time: 3.831 ms
```

### entries · d_unnest · 100 spread

```
Aggregate  (cost=38068.42..38068.43 rows=1 width=8) (actual time=2.215..2.216 rows=1 loops=1)
  Buffers: shared hit=216
  ->  Nested Loop  (cost=0.30..35229.26 rows=1135667 width=0) (actual time=0.040..1.796 rows=5100 loops=1)
        Buffers: shared hit=216
        ->  Function Scan on g  (cost=0.01..1.00 rows=100 width=8) (actual time=0.022..0.038 rows=100 loops=1)
        ->  Index Only Scan using acl_ae3f5e6a_ix_pre on acl_ae3f5e6a_entries e  (cost=0.29..238.71 rows=11357 width=4) (actual time=0.005..0.010 rows=51 loops=100)
              Index Cond: ((pre >= g.lo) AND (pre <= g.hi))
              Heap Fetches: 0
              Buffers: shared hit=216
Planning Time: 0.163 ms
Execution Time: 2.243 ms
```

### corpus · a_like · 100 spread

```
Aggregate  (cost=4156.68..4156.69 rows=1 width=16) (actual time=21.047..21.082 rows=1 loops=1)
  Buffers: shared hit=1502
  ->  Hash Join  (cost=1855.81..4108.34 rows=9667 width=4) (actual time=7.658..20.875 rows=5000 loops=1)
        Hash Cond: (d.entry_id = e.id)
        Buffers: shared hit=1502
        ->  Seq Scan on acl_ae3f5e6a_docs d  (cost=0.00..1989.50 rows=100200 width=12) (actual time=0.006..6.930 rows=100200 loops=1)
              Filter: (epoch = 1)
              Buffers: shared hit=737
        ->  Hash  (cost=1732.55..1732.55 rows=9861 width=8) (actual time=7.617..7.651 rows=5100 loops=1)
              Buckets: 16384  Batches: 1  Memory Usage: 328kB
              Buffers: shared hit=765
              ->  Bitmap Heap Scan on acl_ae3f5e6a_entries e  (cost=1378.30..1732.55 rows=9861 width=8) (actual time=0.417..7.214 rows=5100 loops=1)
                    Recheck Cond: ((path = '/t00/f000'::text) OR (path ~~ '/t00/f000/%'::text) OR (path = '/t00/f020'::text) OR (path ~~ '/t00/f020/%'::text) OR (path = '/t00/f040'::text) OR (path ~~ '/t00/f040/%'::text) …
                    Filter: ((path = '/t00/f000'::text) OR (path ~~ '/t00/f000/%'::text) OR (path = '/t00/f020'::text) OR (path ~~ '/t00/f020/%'::text) OR (path = '/t00/f040'::text) OR (path ~~ '/t00/f040/%'::text) OR (p …
                    Heap Blocks: exact=142
                    Buffers: shared hit=765
                    ->  BitmapOr  (cost=1378.30..1378.30 rows=107 width=0) (actual time=0.398..0.432 rows=0 loops=1)
                          Buffers: shared hit=623
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t00/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f000/'::text) AND (path < '/t00/f0000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t00/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f020/'::text) AND (path < '/t00/f0200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t00/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f040/'::text) AND (path < '/t00/f0400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t00/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f060/'::text) AND (path < '/t00/f0600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t00/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f080/'::text) AND (path < '/t00/f0800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t00/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f100/'::text) AND (path < '/t00/f1000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t00/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f120/'::text) AND (path < '/t00/f1200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t00/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f140/'::text) AND (path < '/t00/f1400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t00/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f160/'::text) AND (path < '/t00/f1600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t00/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f180/'::text) AND (path < '/t00/f1800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t01/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f000/'::text) AND (path < '/t01/f0000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t01/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f020/'::text) AND (path < '/t01/f0200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t01/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f040/'::text) AND (path < '/t01/f0400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t01/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f060/'::text) AND (path < '/t01/f0600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t01/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f080/'::text) AND (path < '/t01/f0800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t01/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f100/'::text) AND (path < '/t01/f1000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t01/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f120/'::text) AND (path < '/t01/f1200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t01/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f140/'::text) AND (path < '/t01/f1400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t01/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f160/'::text) AND (path < '/t01/f1600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t01/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f180/'::text) AND (path < '/t01/f1800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t02/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f000/'::text) AND (path < '/t02/f0000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t02/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f020/'::text) AND (path < '/t02/f0200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t02/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f040/'::text) AND (path < '/t02/f0400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t02/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f060/'::text) AND (path < '/t02/f0600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t02/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f080/'::text) AND (path < '/t02/f0800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t02/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f100/'::text) AND (path < '/t02/f1000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t02/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f120/'::text) AND (path < '/t02/f1200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t02/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f140/'::text) AND (path < '/t02/f1400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t02/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f160/'::text) AND (path < '/t02/f1600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t02/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f180/'::text) AND (path < '/t02/f1800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t03/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f000/'::text) AND (path < '/t03/f0000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t03/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f020/'::text) AND (path < '/t03/f0200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t03/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f040/'::text) AND (path < '/t03/f0400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t03/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f060/'::text) AND (path < '/t03/f0600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t03/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f080/'::text) AND (path < '/t03/f0800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t03/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f100/'::text) AND (path < '/t03/f1000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t03/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f120/'::text) AND (path < '/t03/f1200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t03/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f140/'::text) AND (path < '/t03/f1400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t03/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f160/'::text) AND (path < '/t03/f1600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t03/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f180/'::text) AND (path < '/t03/f1800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t04/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f000/'::text) AND (path < '/t04/f0000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t04/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f020/'::text) AND (path < '/t04/f0200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t04/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f040/'::text) AND (path < '/t04/f0400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t04/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f060/'::text) AND (path < '/t04/f0600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t04/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f080/'::text) AND (path < '/t04/f0800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t04/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f100/'::text) AND (path < '/t04/f1000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t04/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f120/'::text) AND (path < '/t04/f1200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t04/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f140/'::text) AND (path < '/t04/f1400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t04/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f160/'::text) AND (path < '/t04/f1600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t04/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f180/'::text) AND (path < '/t04/f1800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t05/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.005 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f000/'::text) AND (path < '/t05/f0000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t05/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f020/'::text) AND (path < '/t05/f0200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t05/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f040/'::text) AND (path < '/t05/f0400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t05/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f060/'::text) AND (path < '/t05/f0600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.005..0.005 rows=1 loops=1)
                                Index Cond: (path = '/t05/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f080/'::text) AND (path < '/t05/f0800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t05/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f100/'::text) AND (path < '/t05/f1000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t05/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f120/'::text) AND (path < '/t05/f1200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t05/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f140/'::text) AND (path < '/t05/f1400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t05/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f160/'::text) AND (path < '/t05/f1600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t05/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f180/'::text) AND (path < '/t05/f1800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t06/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f000/'::text) AND (path < '/t06/f0000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t06/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f020/'::text) AND (path < '/t06/f0200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t06/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f040/'::text) AND (path < '/t06/f0400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t06/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f060/'::text) AND (path < '/t06/f0600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t06/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f080/'::text) AND (path < '/t06/f0800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t06/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f100/'::text) AND (path < '/t06/f1000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t06/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f120/'::text) AND (path < '/t06/f1200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t06/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f140/'::text) AND (path < '/t06/f1400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t06/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f160/'::text) AND (path < '/t06/f1600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t06/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f180/'::text) AND (path < '/t06/f1800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t07/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f000/'::text) AND (path < '/t07/f0000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t07/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f020/'::text) AND (path < '/t07/f0200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t07/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f040/'::text) AND (path < '/t07/f0400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t07/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f060/'::text) AND (path < '/t07/f0600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t07/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f080/'::text) AND (path < '/t07/f0800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t07/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f100/'::text) AND (path < '/t07/f1000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t07/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f120/'::text) AND (path < '/t07/f1200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t07/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f140/'::text) AND (path < '/t07/f1400'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t07/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f160/'::text) AND (path < '/t07/f1600'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t07/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f180/'::text) AND (path < '/t07/f1800'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t08/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f000/'::text) AND (path < '/t08/f0000'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t08/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f020/'::text) AND (path < '/t08/f0200'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t08/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f040/'::text) AND (path < '/t08/f0400'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t08/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f060/'::text) AND (path < '/t08/f0600'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t08/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f080/'::text) AND (path < '/t08/f0800'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t08/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f100/'::text) AND (path < '/t08/f1000'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t08/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f120/'::text) AND (path < '/t08/f1200'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t08/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f140/'::text) AND (path < '/t08/f1400'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t08/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f160/'::text) AND (path < '/t08/f1600'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t08/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f180/'::text) AND (path < '/t08/f1800'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t09/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f000/'::text) AND (path < '/t09/f0000'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t09/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f020/'::text) AND (path < '/t09/f0200'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t09/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.011..0.011 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f040/'::text) AND (path < '/t09/f0400'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t09/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f060/'::text) AND (path < '/t09/f0600'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t09/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f080/'::text) AND (path < '/t09/f0800'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t09/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f100/'::text) AND (path < '/t09/f1000'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t09/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f120/'::text) AND (path < '/t09/f1200'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t09/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f140/'::text) AND (path < '/t09/f1400'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t09/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f160/'::text) AND (path < '/t09/f1600'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t09/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f180/'::text) AND (path < '/t09/f1800'::text))
                                Buffers: shared hit=4
Planning:
  Buffers: shared hit=34
Planning Time: 1.272 ms
Execution Time: 21.692 ms
```

### corpus · b_range · 100 spread

```
Aggregate  (cost=2100.00..2100.01 rows=1 width=16) (actual time=6.952..6.974 rows=1 loops=1)
  Buffers: shared hit=21065
  ->  Nested Loop  (cost=891.02..2099.48 rows=105 width=4) (actual time=0.397..6.750 rows=5000 loops=1)
        Buffers: shared hit=21065
        ->  Bitmap Heap Scan on acl_ae3f5e6a_entries e  (cost=890.60..1271.60 rows=107 width=8) (actual time=0.387..0.838 rows=5100 loops=1)
              Recheck Cond: ((path = '/t00/f000'::text) OR ((path >= '/t00/f000/'::text) AND (path < '/t00/f0000'::text)) OR (path = '/t00/f020'::text) OR ((path >= '/t00/f020/'::text) AND (path < '/t00/f0200'::text)) OR …
              Heap Blocks: exact=142
              Buffers: shared hit=765
              ->  BitmapOr  (cost=890.60..890.60 rows=107 width=0) (actual time=0.374..0.396 rows=0 loops=1)
                    Buffers: shared hit=623
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                          Index Cond: (path = '/t00/f000'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t00/f000/'::text) AND (path < '/t00/f0000'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                          Index Cond: (path = '/t00/f020'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t00/f020/'::text) AND (path < '/t00/f0200'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t00/f040'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t00/f040/'::text) AND (path < '/t00/f0400'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t00/f060'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t00/f060/'::text) AND (path < '/t00/f0600'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t00/f080'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t00/f080/'::text) AND (path < '/t00/f0800'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t00/f100'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t00/f100/'::text) AND (path < '/t00/f1000'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t00/f120'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t00/f120/'::text) AND (path < '/t00/f1200'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t00/f140'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t00/f140/'::text) AND (path < '/t00/f1400'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t00/f160'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t00/f160/'::text) AND (path < '/t00/f1600'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t00/f180'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t00/f180/'::text) AND (path < '/t00/f1800'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t01/f000'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t01/f000/'::text) AND (path < '/t01/f0000'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t01/f020'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t01/f020/'::text) AND (path < '/t01/f0200'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t01/f040'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t01/f040/'::text) AND (path < '/t01/f0400'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t01/f060'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t01/f060/'::text) AND (path < '/t01/f0600'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t01/f080'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t01/f080/'::text) AND (path < '/t01/f0800'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t01/f100'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t01/f100/'::text) AND (path < '/t01/f1000'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t01/f120'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t01/f120/'::text) AND (path < '/t01/f1200'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t01/f140'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t01/f140/'::text) AND (path < '/t01/f1400'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t01/f160'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t01/f160/'::text) AND (path < '/t01/f1600'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t01/f180'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t01/f180/'::text) AND (path < '/t01/f1800'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t02/f000'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t02/f000/'::text) AND (path < '/t02/f0000'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t02/f020'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t02/f020/'::text) AND (path < '/t02/f0200'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t02/f040'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t02/f040/'::text) AND (path < '/t02/f0400'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t02/f060'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t02/f060/'::text) AND (path < '/t02/f0600'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t02/f080'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t02/f080/'::text) AND (path < '/t02/f0800'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t02/f100'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t02/f100/'::text) AND (path < '/t02/f1000'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t02/f120'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t02/f120/'::text) AND (path < '/t02/f1200'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t02/f140'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t02/f140/'::text) AND (path < '/t02/f1400'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t02/f160'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t02/f160/'::text) AND (path < '/t02/f1600'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t02/f180'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t02/f180/'::text) AND (path < '/t02/f1800'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t03/f000'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t03/f000/'::text) AND (path < '/t03/f0000'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t03/f020'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t03/f020/'::text) AND (path < '/t03/f0200'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                          Index Cond: (path = '/t03/f040'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t03/f040/'::text) AND (path < '/t03/f0400'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t03/f060'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t03/f060/'::text) AND (path < '/t03/f0600'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t03/f080'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t03/f080/'::text) AND (path < '/t03/f0800'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t03/f100'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t03/f100/'::text) AND (path < '/t03/f1000'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t03/f120'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t03/f120/'::text) AND (path < '/t03/f1200'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t03/f140'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t03/f140/'::text) AND (path < '/t03/f1400'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t03/f160'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t03/f160/'::text) AND (path < '/t03/f1600'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t03/f180'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t03/f180/'::text) AND (path < '/t03/f1800'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t04/f000'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t04/f000/'::text) AND (path < '/t04/f0000'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t04/f020'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t04/f020/'::text) AND (path < '/t04/f0200'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t04/f040'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t04/f040/'::text) AND (path < '/t04/f0400'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t04/f060'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t04/f060/'::text) AND (path < '/t04/f0600'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t04/f080'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t04/f080/'::text) AND (path < '/t04/f0800'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t04/f100'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t04/f100/'::text) AND (path < '/t04/f1000'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t04/f120'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t04/f120/'::text) AND (path < '/t04/f1200'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t04/f140'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t04/f140/'::text) AND (path < '/t04/f1400'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t04/f160'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t04/f160/'::text) AND (path < '/t04/f1600'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t04/f180'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t04/f180/'::text) AND (path < '/t04/f1800'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t05/f000'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t05/f000/'::text) AND (path < '/t05/f0000'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                          Index Cond: (path = '/t05/f020'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t05/f020/'::text) AND (path < '/t05/f0200'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t05/f040'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t05/f040/'::text) AND (path < '/t05/f0400'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t05/f060'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t05/f060/'::text) AND (path < '/t05/f0600'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t05/f080'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t05/f080/'::text) AND (path < '/t05/f0800'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t05/f100'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t05/f100/'::text) AND (path < '/t05/f1000'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t05/f120'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t05/f120/'::text) AND (path < '/t05/f1200'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t05/f140'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t05/f140/'::text) AND (path < '/t05/f1400'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t05/f160'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t05/f160/'::text) AND (path < '/t05/f1600'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t05/f180'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t05/f180/'::text) AND (path < '/t05/f1800'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t06/f000'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t06/f000/'::text) AND (path < '/t06/f0000'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t06/f020'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t06/f020/'::text) AND (path < '/t06/f0200'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t06/f040'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t06/f040/'::text) AND (path < '/t06/f0400'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t06/f060'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t06/f060/'::text) AND (path < '/t06/f0600'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                          Index Cond: (path = '/t06/f080'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t06/f080/'::text) AND (path < '/t06/f0800'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t06/f100'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t06/f100/'::text) AND (path < '/t06/f1000'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t06/f120'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t06/f120/'::text) AND (path < '/t06/f1200'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t06/f140'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t06/f140/'::text) AND (path < '/t06/f1400'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t06/f160'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t06/f160/'::text) AND (path < '/t06/f1600'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t06/f180'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t06/f180/'::text) AND (path < '/t06/f1800'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t07/f000'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t07/f000/'::text) AND (path < '/t07/f0000'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t07/f020'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t07/f020/'::text) AND (path < '/t07/f0200'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t07/f040'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t07/f040/'::text) AND (path < '/t07/f0400'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t07/f060'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t07/f060/'::text) AND (path < '/t07/f0600'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t07/f080'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t07/f080/'::text) AND (path < '/t07/f0800'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t07/f100'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t07/f100/'::text) AND (path < '/t07/f1000'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t07/f120'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t07/f120/'::text) AND (path < '/t07/f1200'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t07/f140'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t07/f140/'::text) AND (path < '/t07/f1400'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t07/f160'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t07/f160/'::text) AND (path < '/t07/f1600'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t07/f180'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t07/f180/'::text) AND (path < '/t07/f1800'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t08/f000'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t08/f000/'::text) AND (path < '/t08/f0000'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t08/f020'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t08/f020/'::text) AND (path < '/t08/f0200'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t08/f040'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t08/f040/'::text) AND (path < '/t08/f0400'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t08/f060'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t08/f060/'::text) AND (path < '/t08/f0600'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.013..0.013 rows=1 loops=1)
                          Index Cond: (path = '/t08/f080'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t08/f080/'::text) AND (path < '/t08/f0800'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t08/f100'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t08/f100/'::text) AND (path < '/t08/f1000'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t08/f120'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t08/f120/'::text) AND (path < '/t08/f1200'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t08/f140'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t08/f140/'::text) AND (path < '/t08/f1400'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t08/f160'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t08/f160/'::text) AND (path < '/t08/f1600'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t08/f180'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t08/f180/'::text) AND (path < '/t08/f1800'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t09/f000'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t09/f000/'::text) AND (path < '/t09/f0000'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t09/f020'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t09/f020/'::text) AND (path < '/t09/f0200'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t09/f040'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t09/f040/'::text) AND (path < '/t09/f0400'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t09/f060'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t09/f060/'::text) AND (path < '/t09/f0600'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t09/f080'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t09/f080/'::text) AND (path < '/t09/f0800'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t09/f100'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t09/f100/'::text) AND (path < '/t09/f1000'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t09/f120'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t09/f120/'::text) AND (path < '/t09/f1200'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t09/f140'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=50 loops=1)
                          Index Cond: ((path >= '/t09/f140/'::text) AND (path < '/t09/f1400'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t09/f160'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t09/f160/'::text) AND (path < '/t09/f1600'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t09/f180'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t09/f180/'::text) AND (path < '/t09/f1800'::text))
                          Buffers: shared hit=4
        ->  Index Scan using acl_ae3f5e6a_ix_docs_entry on acl_ae3f5e6a_docs d  (cost=0.42..7.73 rows=1 width=12) (actual time=0.001..0.001 rows=1 loops=5100)
              Index Cond: ((epoch = 1) AND (entry_id = e.id))
              Buffers: shared hit=20300
Planning:
  Buffers: shared hit=34
Planning Time: 0.901 ms
Execution Time: 7.600 ms
```

### corpus · a_like_semi · 100 spread

```
Aggregate  (cost=4156.68..4156.69 rows=1 width=16) (actual time=21.446..21.485 rows=1 loops=1)
  Buffers: shared hit=1502
  ->  Hash Join  (cost=1855.81..4108.34 rows=9667 width=4) (actual time=7.963..21.274 rows=5000 loops=1)
        Hash Cond: (d.entry_id = e.id)
        Buffers: shared hit=1502
        ->  Seq Scan on acl_ae3f5e6a_docs d  (cost=0.00..1989.50 rows=100200 width=12) (actual time=0.004..7.010 rows=100200 loops=1)
              Filter: (epoch = 1)
              Buffers: shared hit=737
        ->  Hash  (cost=1732.55..1732.55 rows=9861 width=8) (actual time=7.951..7.989 rows=5100 loops=1)
              Buckets: 16384  Batches: 1  Memory Usage: 328kB
              Buffers: shared hit=765
              ->  Bitmap Heap Scan on acl_ae3f5e6a_entries e  (cost=1378.30..1732.55 rows=9861 width=8) (actual time=0.478..7.508 rows=5100 loops=1)
                    Recheck Cond: ((path = '/t00/f000'::text) OR (path ~~ '/t00/f000/%'::text) OR (path = '/t00/f020'::text) OR (path ~~ '/t00/f020/%'::text) OR (path = '/t00/f040'::text) OR (path ~~ '/t00/f040/%'::text) …
                    Filter: ((path = '/t00/f000'::text) OR (path ~~ '/t00/f000/%'::text) OR (path = '/t00/f020'::text) OR (path ~~ '/t00/f020/%'::text) OR (path = '/t00/f040'::text) OR (path ~~ '/t00/f040/%'::text) OR (p …
                    Heap Blocks: exact=142
                    Buffers: shared hit=765
                    ->  BitmapOr  (cost=1378.30..1378.30 rows=107 width=0) (actual time=0.458..0.495 rows=0 loops=1)
                          Buffers: shared hit=623
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                                Index Cond: (path = '/t00/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f000/'::text) AND (path < '/t00/f0000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.005..0.005 rows=1 loops=1)
                                Index Cond: (path = '/t00/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f020/'::text) AND (path < '/t00/f0200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t00/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f040/'::text) AND (path < '/t00/f0400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t00/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f060/'::text) AND (path < '/t00/f0600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t00/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f080/'::text) AND (path < '/t00/f0800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t00/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f100/'::text) AND (path < '/t00/f1000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t00/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f120/'::text) AND (path < '/t00/f1200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t00/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f140/'::text) AND (path < '/t00/f1400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t00/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f160/'::text) AND (path < '/t00/f1600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t00/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f180/'::text) AND (path < '/t00/f1800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t01/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f000/'::text) AND (path < '/t01/f0000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t01/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f020/'::text) AND (path < '/t01/f0200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t01/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f040/'::text) AND (path < '/t01/f0400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t01/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f060/'::text) AND (path < '/t01/f0600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t01/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f080/'::text) AND (path < '/t01/f0800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t01/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f100/'::text) AND (path < '/t01/f1000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t01/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f120/'::text) AND (path < '/t01/f1200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t01/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f140/'::text) AND (path < '/t01/f1400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=1 loops=1)
                                Index Cond: (path = '/t01/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f160/'::text) AND (path < '/t01/f1600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t01/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f180/'::text) AND (path < '/t01/f1800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t02/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f000/'::text) AND (path < '/t02/f0000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t02/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f020/'::text) AND (path < '/t02/f0200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.005..0.005 rows=1 loops=1)
                                Index Cond: (path = '/t02/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f040/'::text) AND (path < '/t02/f0400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t02/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f060/'::text) AND (path < '/t02/f0600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t02/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f080/'::text) AND (path < '/t02/f0800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t02/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f100/'::text) AND (path < '/t02/f1000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t02/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f120/'::text) AND (path < '/t02/f1200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t02/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f140/'::text) AND (path < '/t02/f1400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t02/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f160/'::text) AND (path < '/t02/f1600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.005..0.006 rows=1 loops=1)
                                Index Cond: (path = '/t02/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f180/'::text) AND (path < '/t02/f1800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t03/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f000/'::text) AND (path < '/t03/f0000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t03/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f020/'::text) AND (path < '/t03/f0200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t03/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f040/'::text) AND (path < '/t03/f0400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t03/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f060/'::text) AND (path < '/t03/f0600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t03/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f080/'::text) AND (path < '/t03/f0800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t03/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f100/'::text) AND (path < '/t03/f1000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.005..0.005 rows=1 loops=1)
                                Index Cond: (path = '/t03/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f120/'::text) AND (path < '/t03/f1200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t03/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f140/'::text) AND (path < '/t03/f1400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t03/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f160/'::text) AND (path < '/t03/f1600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t03/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f180/'::text) AND (path < '/t03/f1800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.005..0.005 rows=1 loops=1)
                                Index Cond: (path = '/t04/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f000/'::text) AND (path < '/t04/f0000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t04/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f020/'::text) AND (path < '/t04/f0200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t04/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f040/'::text) AND (path < '/t04/f0400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t04/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f060/'::text) AND (path < '/t04/f0600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.005..0.005 rows=1 loops=1)
                                Index Cond: (path = '/t04/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f080/'::text) AND (path < '/t04/f0800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t04/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f100/'::text) AND (path < '/t04/f1000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t04/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f120/'::text) AND (path < '/t04/f1200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t04/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f140/'::text) AND (path < '/t04/f1400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.005..0.005 rows=1 loops=1)
                                Index Cond: (path = '/t04/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f160/'::text) AND (path < '/t04/f1600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t04/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f180/'::text) AND (path < '/t04/f1800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t05/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f000/'::text) AND (path < '/t05/f0000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t05/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f020/'::text) AND (path < '/t05/f0200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=1 loops=1)
                                Index Cond: (path = '/t05/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f040/'::text) AND (path < '/t05/f0400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t05/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f060/'::text) AND (path < '/t05/f0600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t05/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f080/'::text) AND (path < '/t05/f0800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t05/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f100/'::text) AND (path < '/t05/f1000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t05/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f120/'::text) AND (path < '/t05/f1200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t05/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f140/'::text) AND (path < '/t05/f1400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t05/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f160/'::text) AND (path < '/t05/f1600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t05/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f180/'::text) AND (path < '/t05/f1800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t06/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f000/'::text) AND (path < '/t06/f0000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t06/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f020/'::text) AND (path < '/t06/f0200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t06/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f040/'::text) AND (path < '/t06/f0400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.005..0.005 rows=1 loops=1)
                                Index Cond: (path = '/t06/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f060/'::text) AND (path < '/t06/f0600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                                Index Cond: (path = '/t06/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f080/'::text) AND (path < '/t06/f0800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t06/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f100/'::text) AND (path < '/t06/f1000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=1 loops=1)
                                Index Cond: (path = '/t06/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f120/'::text) AND (path < '/t06/f1200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t06/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f140/'::text) AND (path < '/t06/f1400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t06/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f160/'::text) AND (path < '/t06/f1600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t06/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f180/'::text) AND (path < '/t06/f1800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t07/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f000/'::text) AND (path < '/t07/f0000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t07/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f020/'::text) AND (path < '/t07/f0200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t07/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f040/'::text) AND (path < '/t07/f0400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t07/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f060/'::text) AND (path < '/t07/f0600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.005..0.005 rows=1 loops=1)
                                Index Cond: (path = '/t07/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f080/'::text) AND (path < '/t07/f0800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t07/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f100/'::text) AND (path < '/t07/f1000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t07/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f120/'::text) AND (path < '/t07/f1200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t07/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f140/'::text) AND (path < '/t07/f1400'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t07/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f160/'::text) AND (path < '/t07/f1600'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t07/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f180/'::text) AND (path < '/t07/f1800'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t08/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f000/'::text) AND (path < '/t08/f0000'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t08/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f020/'::text) AND (path < '/t08/f0200'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t08/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f040/'::text) AND (path < '/t08/f0400'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t08/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f060/'::text) AND (path < '/t08/f0600'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t08/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f080/'::text) AND (path < '/t08/f0800'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t08/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f100/'::text) AND (path < '/t08/f1000'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t08/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f120/'::text) AND (path < '/t08/f1200'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t08/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f140/'::text) AND (path < '/t08/f1400'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t08/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f160/'::text) AND (path < '/t08/f1600'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t08/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f180/'::text) AND (path < '/t08/f1800'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t09/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f000/'::text) AND (path < '/t09/f0000'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t09/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f020/'::text) AND (path < '/t09/f0200'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t09/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f040/'::text) AND (path < '/t09/f0400'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t09/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f060/'::text) AND (path < '/t09/f0600'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t09/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f080/'::text) AND (path < '/t09/f0800'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t09/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f100/'::text) AND (path < '/t09/f1000'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t09/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f120/'::text) AND (path < '/t09/f1200'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                                Index Cond: (path = '/t09/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f140/'::text) AND (path < '/t09/f1400'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=1 loops=1)
                                Index Cond: (path = '/t09/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f160/'::text) AND (path < '/t09/f1600'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                                Index Cond: (path = '/t09/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f180/'::text) AND (path < '/t09/f1800'::text))
                                Buffers: shared hit=4
Planning:
  Buffers: shared hit=34
Planning Time: 1.433 ms
Execution Time: 22.233 ms
```

### corpus · b_range_semi · 100 spread

```
Aggregate  (cost=2100.00..2100.01 rows=1 width=16) (actual time=7.904..7.948 rows=1 loops=1)
  Buffers: shared hit=21065
  ->  Nested Loop  (cost=891.02..2099.48 rows=105 width=4) (actual time=0.368..7.672 rows=5000 loops=1)
        Buffers: shared hit=21065
        ->  Bitmap Heap Scan on acl_ae3f5e6a_entries e  (cost=890.60..1271.60 rows=107 width=8) (actual time=0.358..0.867 rows=5100 loops=1)
              Recheck Cond: ((path = '/t00/f000'::text) OR ((path >= '/t00/f000/'::text) AND (path < '/t00/f0000'::text)) OR (path = '/t00/f020'::text) OR ((path >= '/t00/f020/'::text) AND (path < '/t00/f0200'::text)) OR …
              Heap Blocks: exact=142
              Buffers: shared hit=765
              ->  BitmapOr  (cost=890.60..890.60 rows=107 width=0) (actual time=0.345..0.389 rows=0 loops=1)
                    Buffers: shared hit=623
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.003 rows=1 loops=1)
                          Index Cond: (path = '/t00/f000'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t00/f000/'::text) AND (path < '/t00/f0000'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                          Index Cond: (path = '/t00/f020'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t00/f020/'::text) AND (path < '/t00/f0200'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t00/f040'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t00/f040/'::text) AND (path < '/t00/f0400'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t00/f060'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t00/f060/'::text) AND (path < '/t00/f0600'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t00/f080'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t00/f080/'::text) AND (path < '/t00/f0800'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t00/f100'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t00/f100/'::text) AND (path < '/t00/f1000'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t00/f120'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t00/f120/'::text) AND (path < '/t00/f1200'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t00/f140'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t00/f140/'::text) AND (path < '/t00/f1400'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t00/f160'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t00/f160/'::text) AND (path < '/t00/f1600'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t00/f180'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t00/f180/'::text) AND (path < '/t00/f1800'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t01/f000'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t01/f000/'::text) AND (path < '/t01/f0000'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t01/f020'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t01/f020/'::text) AND (path < '/t01/f0200'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t01/f040'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t01/f040/'::text) AND (path < '/t01/f0400'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t01/f060'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t01/f060/'::text) AND (path < '/t01/f0600'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                          Index Cond: (path = '/t01/f080'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t01/f080/'::text) AND (path < '/t01/f0800'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t01/f100'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t01/f100/'::text) AND (path < '/t01/f1000'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t01/f120'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t01/f120/'::text) AND (path < '/t01/f1200'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t01/f140'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t01/f140/'::text) AND (path < '/t01/f1400'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t01/f160'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t01/f160/'::text) AND (path < '/t01/f1600'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t01/f180'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t01/f180/'::text) AND (path < '/t01/f1800'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t02/f000'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t02/f000/'::text) AND (path < '/t02/f0000'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t02/f020'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t02/f020/'::text) AND (path < '/t02/f0200'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t02/f040'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t02/f040/'::text) AND (path < '/t02/f0400'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t02/f060'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t02/f060/'::text) AND (path < '/t02/f0600'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t02/f080'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t02/f080/'::text) AND (path < '/t02/f0800'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t02/f100'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t02/f100/'::text) AND (path < '/t02/f1000'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t02/f120'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t02/f120/'::text) AND (path < '/t02/f1200'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t02/f140'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t02/f140/'::text) AND (path < '/t02/f1400'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t02/f160'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t02/f160/'::text) AND (path < '/t02/f1600'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t02/f180'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t02/f180/'::text) AND (path < '/t02/f1800'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t03/f000'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t03/f000/'::text) AND (path < '/t03/f0000'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t03/f020'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t03/f020/'::text) AND (path < '/t03/f0200'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                          Index Cond: (path = '/t03/f040'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t03/f040/'::text) AND (path < '/t03/f0400'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t03/f060'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t03/f060/'::text) AND (path < '/t03/f0600'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t03/f080'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t03/f080/'::text) AND (path < '/t03/f0800'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t03/f100'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t03/f100/'::text) AND (path < '/t03/f1000'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t03/f120'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t03/f120/'::text) AND (path < '/t03/f1200'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t03/f140'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t03/f140/'::text) AND (path < '/t03/f1400'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t03/f160'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t03/f160/'::text) AND (path < '/t03/f1600'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t03/f180'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t03/f180/'::text) AND (path < '/t03/f1800'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t04/f000'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t04/f000/'::text) AND (path < '/t04/f0000'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t04/f020'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t04/f020/'::text) AND (path < '/t04/f0200'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t04/f040'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t04/f040/'::text) AND (path < '/t04/f0400'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t04/f060'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t04/f060/'::text) AND (path < '/t04/f0600'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t04/f080'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t04/f080/'::text) AND (path < '/t04/f0800'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t04/f100'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t04/f100/'::text) AND (path < '/t04/f1000'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t04/f120'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t04/f120/'::text) AND (path < '/t04/f1200'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t04/f140'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t04/f140/'::text) AND (path < '/t04/f1400'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t04/f160'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t04/f160/'::text) AND (path < '/t04/f1600'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t04/f180'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t04/f180/'::text) AND (path < '/t04/f1800'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t05/f000'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t05/f000/'::text) AND (path < '/t05/f0000'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t05/f020'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t05/f020/'::text) AND (path < '/t05/f0200'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t05/f040'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t05/f040/'::text) AND (path < '/t05/f0400'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t05/f060'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t05/f060/'::text) AND (path < '/t05/f0600'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t05/f080'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t05/f080/'::text) AND (path < '/t05/f0800'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t05/f100'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t05/f100/'::text) AND (path < '/t05/f1000'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t05/f120'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t05/f120/'::text) AND (path < '/t05/f1200'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t05/f140'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t05/f140/'::text) AND (path < '/t05/f1400'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t05/f160'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t05/f160/'::text) AND (path < '/t05/f1600'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t05/f180'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t05/f180/'::text) AND (path < '/t05/f1800'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t06/f000'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t06/f000/'::text) AND (path < '/t06/f0000'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                          Index Cond: (path = '/t06/f020'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t06/f020/'::text) AND (path < '/t06/f0200'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t06/f040'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t06/f040/'::text) AND (path < '/t06/f0400'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t06/f060'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t06/f060/'::text) AND (path < '/t06/f0600'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
                          Index Cond: (path = '/t06/f080'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t06/f080/'::text) AND (path < '/t06/f0800'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t06/f100'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t06/f100/'::text) AND (path < '/t06/f1000'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t06/f120'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t06/f120/'::text) AND (path < '/t06/f1200'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t06/f140'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t06/f140/'::text) AND (path < '/t06/f1400'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t06/f160'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t06/f160/'::text) AND (path < '/t06/f1600'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t06/f180'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t06/f180/'::text) AND (path < '/t06/f1800'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t07/f000'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t07/f000/'::text) AND (path < '/t07/f0000'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t07/f020'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t07/f020/'::text) AND (path < '/t07/f0200'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t07/f040'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t07/f040/'::text) AND (path < '/t07/f0400'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t07/f060'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t07/f060/'::text) AND (path < '/t07/f0600'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t07/f080'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t07/f080/'::text) AND (path < '/t07/f0800'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t07/f100'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t07/f100/'::text) AND (path < '/t07/f1000'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t07/f120'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t07/f120/'::text) AND (path < '/t07/f1200'::text))
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t07/f140'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t07/f140/'::text) AND (path < '/t07/f1400'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t07/f160'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t07/f160/'::text) AND (path < '/t07/f1600'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t07/f180'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t07/f180/'::text) AND (path < '/t07/f1800'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t08/f000'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=50 loops=1)
                          Index Cond: ((path >= '/t08/f000/'::text) AND (path < '/t08/f0000'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t08/f020'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t08/f020/'::text) AND (path < '/t08/f0200'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t08/f040'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t08/f040/'::text) AND (path < '/t08/f0400'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t08/f060'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t08/f060/'::text) AND (path < '/t08/f0600'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t08/f080'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t08/f080/'::text) AND (path < '/t08/f0800'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t08/f100'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                          Index Cond: ((path >= '/t08/f100/'::text) AND (path < '/t08/f1000'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t08/f120'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t08/f120/'::text) AND (path < '/t08/f1200'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t08/f140'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t08/f140/'::text) AND (path < '/t08/f1400'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t08/f160'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t08/f160/'::text) AND (path < '/t08/f1600'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t08/f180'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t08/f180/'::text) AND (path < '/t08/f1800'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t09/f000'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t09/f000/'::text) AND (path < '/t09/f0000'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t09/f020'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t09/f020/'::text) AND (path < '/t09/f0200'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t09/f040'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t09/f040/'::text) AND (path < '/t09/f0400'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t09/f060'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t09/f060/'::text) AND (path < '/t09/f0600'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t09/f080'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t09/f080/'::text) AND (path < '/t09/f0800'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t09/f100'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t09/f100/'::text) AND (path < '/t09/f1000'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t09/f120'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t09/f120/'::text) AND (path < '/t09/f1200'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t09/f140'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t09/f140/'::text) AND (path < '/t09/f1400'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t09/f160'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t09/f160/'::text) AND (path < '/t09/f1600'::text))
                          Buffers: shared hit=4
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
                          Index Cond: (path = '/t09/f180'::text)
                          Buffers: shared hit=3
                    ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.002..0.003 rows=50 loops=1)
                          Index Cond: ((path >= '/t09/f180/'::text) AND (path < '/t09/f1800'::text))
                          Buffers: shared hit=4
        ->  Index Scan using acl_ae3f5e6a_ix_docs_entry on acl_ae3f5e6a_docs d  (cost=0.42..7.73 rows=1 width=12) (actual time=0.001..0.001 rows=1 loops=5100)
              Index Cond: ((epoch = 1) AND (entry_id = e.id))
              Buffers: shared hit=20300
Planning:
  Buffers: shared hit=34
Planning Time: 0.922 ms
Execution Time: 8.770 ms
```

### corpus · c_values · 100 spread

```
Aggregate  (cost=45270.43..45270.44 rows=1 width=16) (actual time=8.180..8.180 rows=1 loops=1)
  Buffers: shared hit=20765
  ->  Nested Loop  (cost=0.83..45242.55 rows=5577 width=4) (actual time=0.012..7.951 rows=5000 loops=1)
        Buffers: shared hit=20765
        ->  Nested Loop  (cost=0.42..42446.25 rows=5689 width=8) (actual time=0.006..1.904 rows=5100 loops=1)
              Buffers: shared hit=465
              ->  Values Scan on "*VALUES*"  (cost=0.00..1.25 rows=100 width=64) (actual time=0.001..0.019 rows=100 loops=1)
              ->  Index Scan using acl_ae3f5e6a_ix_path on acl_ae3f5e6a_entries e  (cost=0.42..423.88 rows=57 width=27) (actual time=0.003..0.014 rows=51 loops=100)
                    Index Cond: ((path >= "*VALUES*".column1) AND (path < "*VALUES*".column2))
                    Filter: ((path = "*VALUES*".column1) OR (substr(path, (length("*VALUES*".column1) + 1), 1) = '/'::text))
                    Rows Removed by Filter: 1
                    Buffers: shared hit=465
        ->  Index Scan using acl_ae3f5e6a_ix_docs_entry on acl_ae3f5e6a_docs d  (cost=0.42..0.48 rows=1 width=12) (actual time=0.001..0.001 rows=1 loops=5100)
              Index Cond: ((epoch = 1) AND (entry_id = e.id))
              Buffers: shared hit=20300
Planning:
  Buffers: shared hit=6
Planning Time: 0.130 ms
Execution Time: 8.192 ms
```

### corpus · c_temp · 100 spread

```
Aggregate  (cost=45271.18..45271.19 rows=1 width=16) (actual time=8.308..8.309 rows=1 loops=1)
  Buffers: shared hit=20765, local hit=1
  ->  Nested Loop  (cost=0.83..45243.30 rows=5577 width=4) (actual time=0.014..8.083 rows=5000 loops=1)
        Buffers: shared hit=20765, local hit=1
        ->  Nested Loop  (cost=0.42..42447.00 rows=5689 width=8) (actual time=0.008..1.883 rows=5100 loops=1)
              Buffers: shared hit=465, local hit=1
              ->  Seq Scan on g_tmp g  (cost=0.00..2.00 rows=100 width=21) (actual time=0.003..0.009 rows=100 loops=1)
                    Buffers: local hit=1
              ->  Index Scan using acl_ae3f5e6a_ix_path on acl_ae3f5e6a_entries e  (cost=0.42..423.88 rows=57 width=27) (actual time=0.003..0.014 rows=51 loops=100)
                    Index Cond: ((path >= g.p) AND (path < g.hi))
                    Filter: ((path = g.p) OR (substr(path, (length(g.p) + 1), 1) = '/'::text))
                    Rows Removed by Filter: 1
                    Buffers: shared hit=465
        ->  Index Scan using acl_ae3f5e6a_ix_docs_entry on acl_ae3f5e6a_docs d  (cost=0.42..0.48 rows=1 width=12) (actual time=0.001..0.001 rows=1 loops=5100)
              Index Cond: ((epoch = 1) AND (entry_id = e.id))
              Buffers: shared hit=20300
Planning:
  Buffers: shared hit=6
Planning Time: 0.092 ms
Execution Time: 8.321 ms
```

### corpus · d_or · 100 spread

```
Aggregate  (cost=6390.03..6390.04 rows=1 width=16) (actual time=15.160..15.181 rows=1 loops=1)
  Buffers: shared hit=1094
  ->  Hash Join  (cost=4113.16..6365.69 rows=4867 width=4) (actual time=1.170..14.968 rows=5000 loops=1)
        Hash Cond: (d.entry_id = e.id)
        Buffers: shared hit=1094
        ->  Seq Scan on acl_ae3f5e6a_docs d  (cost=0.00..1989.50 rows=100200 width=12) (actual time=0.004..7.107 rows=100200 loops=1)
              Filter: (epoch = 1)
              Buffers: shared hit=737
        ->  Hash  (cost=4051.10..4051.10 rows=4965 width=8) (actual time=1.162..1.182 rows=5100 loops=1)
              Buckets: 8192  Batches: 1  Memory Usage: 264kB
              Buffers: shared hit=357
              ->  Bitmap Heap Scan on acl_ae3f5e6a_entries e  (cost=604.22..4051.10 rows=4965 width=8) (actual time=0.277..0.796 rows=5100 loops=1)
                    Recheck Cond: (((pre >= 1) AND (pre <= 51)) OR ((pre >= 1023) AND (pre <= 1073)) OR ((pre >= 2045) AND (pre <= 2095)) OR ((pre >= 3067) AND (pre <= 3117)) OR ((pre >= 4089) AND (pre <= 4139)) OR ((pre …
                    Heap Blocks: exact=142
                    Buffers: shared hit=357
                    ->  BitmapOr  (cost=604.22..604.22 rows=5088 width=0) (actual time=0.268..0.287 rows=0 loops=1)
                          Buffers: shared hit=215
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.003..0.004 rows=51 loops=1)
                                Index Cond: ((pre >= 1) AND (pre <= 51))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.002..0.003 rows=51 loops=1)
                                Index Cond: ((pre >= 1023) AND (pre <= 1073))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.82 rows=53 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 2045) AND (pre <= 2095))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.79 rows=50 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 3067) AND (pre <= 3117))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.76 rows=47 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 4089) AND (pre <= 4139))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.77 rows=48 width=0) (actual time=0.003..0.003 rows=51 loops=1)
                                Index Cond: ((pre >= 5111) AND (pre <= 5161))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.79 rows=50 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 6133) AND (pre <= 6183))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 7155) AND (pre <= 7205))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.79 rows=50 width=0) (actual time=0.005..0.005 rows=51 loops=1)
                                Index Cond: ((pre >= 8177) AND (pre <= 8227))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.84 rows=55 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 9199) AND (pre <= 9249))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.77 rows=48 width=0) (actual time=0.003..0.003 rows=51 loops=1)
                                Index Cond: ((pre >= 10222) AND (pre <= 10272))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.77 rows=48 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 11244) AND (pre <= 11294))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.77 rows=48 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 12266) AND (pre <= 12316))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.79 rows=50 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 13288) AND (pre <= 13338))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 14310) AND (pre <= 14360))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.79 rows=50 width=0) (actual time=0.002..0.003 rows=51 loops=1)
                                Index Cond: ((pre >= 15332) AND (pre <= 15382))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.79 rows=50 width=0) (actual time=0.005..0.005 rows=51 loops=1)
                                Index Cond: ((pre >= 16354) AND (pre <= 16404))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.76 rows=47 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 17376) AND (pre <= 17426))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 18398) AND (pre <= 18448))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 19420) AND (pre <= 19470))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.81 rows=52 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 20443) AND (pre <= 20493))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 21465) AND (pre <= 21515))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.75 rows=46 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 22487) AND (pre <= 22537))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.72 rows=43 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                                Index Cond: ((pre >= 23509) AND (pre <= 23559))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 24531) AND (pre <= 24581))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 25553) AND (pre <= 25603))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.77 rows=48 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 26575) AND (pre <= 26625))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.82 rows=53 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 27597) AND (pre <= 27647))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.88 rows=59 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 28619) AND (pre <= 28669))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.77 rows=48 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 29641) AND (pre <= 29691))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.83 rows=54 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 30664) AND (pre <= 30714))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.81 rows=52 width=0) (actual time=0.005..0.005 rows=51 loops=1)
                                Index Cond: ((pre >= 31686) AND (pre <= 31736))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.81 rows=52 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 32708) AND (pre <= 32758))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.82 rows=53 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 33730) AND (pre <= 33780))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.003..0.003 rows=51 loops=1)
                                Index Cond: ((pre >= 34752) AND (pre <= 34802))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 35774) AND (pre <= 35824))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 36796) AND (pre <= 36846))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 37818) AND (pre <= 37868))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.005..0.005 rows=51 loops=1)
                                Index Cond: ((pre >= 38840) AND (pre <= 38890))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 39862) AND (pre <= 39912))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.81 rows=52 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 40885) AND (pre <= 40935))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 41907) AND (pre <= 41957))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.79 rows=50 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 42929) AND (pre <= 42979))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.84 rows=55 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 43951) AND (pre <= 44001))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                                Index Cond: ((pre >= 44973) AND (pre <= 45023))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.77 rows=48 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 45995) AND (pre <= 46045))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 47017) AND (pre <= 47067))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 48039) AND (pre <= 48089))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.84 rows=55 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 49061) AND (pre <= 49111))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 50083) AND (pre <= 50133))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.82 rows=53 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 51106) AND (pre <= 51156))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.79 rows=50 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 52128) AND (pre <= 52178))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.83 rows=54 width=0) (actual time=0.005..0.005 rows=51 loops=1)
                                Index Cond: ((pre >= 53150) AND (pre <= 53200))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.82 rows=53 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 54172) AND (pre <= 54222))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.83 rows=54 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 55194) AND (pre <= 55244))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 56216) AND (pre <= 56266))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.84 rows=55 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 57238) AND (pre <= 57288))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.79 rows=50 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 58260) AND (pre <= 58310))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.003..0.003 rows=51 loops=1)
                                Index Cond: ((pre >= 59282) AND (pre <= 59332))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 60304) AND (pre <= 60354))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.87 rows=58 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 61327) AND (pre <= 61377))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 62349) AND (pre <= 62399))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.85 rows=56 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 63371) AND (pre <= 63421))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.003..0.003 rows=51 loops=1)
                                Index Cond: ((pre >= 64393) AND (pre <= 64443))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.79 rows=50 width=0) (actual time=0.014..0.014 rows=51 loops=1)
                                Index Cond: ((pre >= 65415) AND (pre <= 65465))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.81 rows=52 width=0) (actual time=0.002..0.003 rows=51 loops=1)
                                Index Cond: ((pre >= 66437) AND (pre <= 66487))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.82 rows=53 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 67459) AND (pre <= 67509))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.81 rows=52 width=0) (actual time=0.006..0.006 rows=51 loops=1)
                                Index Cond: ((pre >= 68481) AND (pre <= 68531))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.82 rows=53 width=0) (actual time=0.003..0.003 rows=51 loops=1)
                                Index Cond: ((pre >= 69503) AND (pre <= 69553))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 70525) AND (pre <= 70575))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 71548) AND (pre <= 71598))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 72570) AND (pre <= 72620))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.83 rows=54 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 73592) AND (pre <= 73642))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.81 rows=52 width=0) (actual time=0.007..0.007 rows=51 loops=1)
                                Index Cond: ((pre >= 74614) AND (pre <= 74664))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 75636) AND (pre <= 75686))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 76658) AND (pre <= 76708))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.81 rows=52 width=0) (actual time=0.002..0.003 rows=51 loops=1)
                                Index Cond: ((pre >= 77680) AND (pre <= 77730))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.81 rows=52 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 78702) AND (pre <= 78752))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.82 rows=53 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 79724) AND (pre <= 79774))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 80746) AND (pre <= 80796))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.79 rows=50 width=0) (actual time=0.003..0.003 rows=51 loops=1)
                                Index Cond: ((pre >= 81769) AND (pre <= 81819))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 82791) AND (pre <= 82841))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.79 rows=50 width=0) (actual time=0.003..0.003 rows=51 loops=1)
                                Index Cond: ((pre >= 83813) AND (pre <= 83863))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.81 rows=52 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 84835) AND (pre <= 84885))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.81 rows=52 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 85857) AND (pre <= 85907))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.81 rows=52 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 86879) AND (pre <= 86929))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.79 rows=50 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 87901) AND (pre <= 87951))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.81 rows=52 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 88923) AND (pre <= 88973))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.83 rows=54 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 89945) AND (pre <= 89995))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.79 rows=50 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 90967) AND (pre <= 91017))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.77 rows=48 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 91990) AND (pre <= 92040))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 93012) AND (pre <= 93062))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.79 rows=50 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 94034) AND (pre <= 94084))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.78 rows=49 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 95056) AND (pre <= 95106))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 96078) AND (pre <= 96128))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 97100) AND (pre <= 97150))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.80 rows=51 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 98122) AND (pre <= 98172))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.81 rows=52 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 99144) AND (pre <= 99194))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.82 rows=53 width=0) (actual time=0.004..0.004 rows=51 loops=1)
                                Index Cond: ((pre >= 100166) AND (pre <= 100216))
                                Buffers: shared hit=2
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_pre  (cost=0.00..4.77 rows=48 width=0) (actual time=0.002..0.002 rows=51 loops=1)
                                Index Cond: ((pre >= 101188) AND (pre <= 101238))
                                Buffers: shared hit=2
Planning:
  Buffers: shared hit=27
Planning Time: 0.474 ms
Execution Time: 15.444 ms
```

### corpus · d_values · 100 spread

```
Aggregate  (cost=62838.26..62838.27 rows=1 width=16) (actual time=20.101..20.102 rows=1 loops=1)
  Buffers: shared hit=1094
  ->  Hash Join  (cost=3242.29..57271.59 rows=1113334 width=4) (actual time=17.609..19.894 rows=5000 loops=1)
        Hash Cond: (e.id = d.entry_id)
        Buffers: shared hit=1094
        ->  Nested Loop  (cost=0.29..38637.50 rows=1135667 width=8) (actual time=0.006..1.175 rows=5100 loops=1)
              Buffers: shared hit=357
              ->  Values Scan on "*VALUES*"  (cost=0.00..1.25 rows=100 width=8) (actual time=0.001..0.020 rows=100 loops=1)
              ->  Index Scan using acl_ae3f5e6a_ix_pre on acl_ae3f5e6a_entries e  (cost=0.29..272.79 rows=11357 width=12) (actual time=0.002..0.007 rows=51 loops=100)
                    Index Cond: ((pre >= "*VALUES*".column1) AND (pre <= "*VALUES*".column2))
                    Buffers: shared hit=357
        ->  Hash  (cost=1989.50..1989.50 rows=100200 width=12) (actual time=17.583..17.583 rows=100200 loops=1)
              Buckets: 131072  Batches: 1  Memory Usage: 5721kB
              Buffers: shared hit=737
              ->  Seq Scan on acl_ae3f5e6a_docs d  (cost=0.00..1989.50 rows=100200 width=12) (actual time=0.003..7.874 rows=100200 loops=1)
                    Filter: (epoch = 1)
                    Buffers: shared hit=737
Planning:
  Buffers: shared hit=6
Planning Time: 0.122 ms
Execution Time: 20.124 ms
```

### corpus · e_or · 100 spread

```
Aggregate  (cost=3818.03..3818.04 rows=1 width=16) (actual time=0.899..0.908 rows=1 loops=1)
  Buffers: shared hit=345
  ->  Bitmap Heap Scan on acl_ae3f5e6a_docs2 d  (cost=612.31..3793.83 rows=4841 width=4) (actual time=0.254..0.643 rows=5000 loops=1)
        Recheck Cond: (((epoch = 1) AND (doc_no >= 0) AND (doc_no <= 49)) OR ((epoch = 1) AND (doc_no >= 1002) AND (doc_no <= 1051)) OR ((epoch = 1) AND (doc_no >= 2004) AND (doc_no <= 2053)) OR ((epoch = 1) AND (doc_no  …
        Heap Blocks: exact=132
        Buffers: shared hit=345
        ->  BitmapOr  (cost=612.31..612.31 rows=4961 width=0) (actual time=0.245..0.254 rows=0 loops=1)
              Buffers: shared hit=213
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.77 rows=38 width=0) (actual time=0.004..0.004 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 0) AND (doc_no <= 49))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.96 rows=53 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 1002) AND (doc_no <= 1051))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.89 rows=48 width=0) (actual time=0.002..0.003 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 2004) AND (doc_no <= 2053))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.98 rows=55 width=0) (actual time=0.002..0.003 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 3006) AND (doc_no <= 3055))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.92 rows=50 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 4008) AND (doc_no <= 4057))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.91 rows=49 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 5010) AND (doc_no <= 5059))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.91 rows=49 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 6012) AND (doc_no <= 6061))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.88 rows=47 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 7014) AND (doc_no <= 7063))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.91 rows=49 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 8016) AND (doc_no <= 8065))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.87 rows=46 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 9018) AND (doc_no <= 9067))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.87 rows=46 width=0) (actual time=0.002..0.003 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 10020) AND (doc_no <= 10069))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.91 rows=49 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 11022) AND (doc_no <= 11071))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.91 rows=49 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 12024) AND (doc_no <= 12073))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.94 rows=52 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 13026) AND (doc_no <= 13075))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.91 rows=49 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 14028) AND (doc_no <= 14077))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.91 rows=49 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 15030) AND (doc_no <= 15079))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.94 rows=52 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 16032) AND (doc_no <= 16081))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.92 rows=50 width=0) (actual time=0.002..0.003 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 17034) AND (doc_no <= 17083))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.94 rows=52 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 18036) AND (doc_no <= 18085))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.93 rows=51 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 19038) AND (doc_no <= 19087))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.87 rows=46 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 20040) AND (doc_no <= 20089))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.94 rows=52 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 21042) AND (doc_no <= 21091))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.93 rows=51 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 22044) AND (doc_no <= 22093))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.87 rows=46 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 23046) AND (doc_no <= 23095))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.89 rows=48 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 24048) AND (doc_no <= 24097))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.91 rows=49 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 25050) AND (doc_no <= 25099))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.94 rows=52 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 26052) AND (doc_no <= 26101))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.89 rows=48 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 27054) AND (doc_no <= 27103))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.93 rows=51 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 28056) AND (doc_no <= 28105))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.92 rows=50 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 29058) AND (doc_no <= 29107))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.88 rows=47 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 30060) AND (doc_no <= 30109))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.88 rows=47 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 31062) AND (doc_no <= 31111))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.88 rows=47 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 32064) AND (doc_no <= 32113))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.93 rows=51 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 33066) AND (doc_no <= 33115))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.89 rows=48 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 34068) AND (doc_no <= 34117))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.88 rows=47 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 35070) AND (doc_no <= 35119))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.91 rows=49 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 36072) AND (doc_no <= 36121))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.88 rows=47 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 37074) AND (doc_no <= 37123))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.97 rows=54 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 38076) AND (doc_no <= 38125))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.88 rows=47 width=0) (actual time=0.002..0.003 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 39078) AND (doc_no <= 39127))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.91 rows=49 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 40080) AND (doc_no <= 40129))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.97 rows=54 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 41082) AND (doc_no <= 41131))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.93 rows=51 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 42084) AND (doc_no <= 42133))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.98 rows=55 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 43086) AND (doc_no <= 43135))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.94 rows=52 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 44088) AND (doc_no <= 44137))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.93 rows=51 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 45090) AND (doc_no <= 45139))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.91 rows=49 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 46092) AND (doc_no <= 46141))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.88 rows=47 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 47094) AND (doc_no <= 47143))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.89 rows=48 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 48096) AND (doc_no <= 48145))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.94 rows=52 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 49098) AND (doc_no <= 49147))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.94 rows=52 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 50100) AND (doc_no <= 50149))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.93 rows=51 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 51102) AND (doc_no <= 51151))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.91 rows=49 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 52104) AND (doc_no <= 52153))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.87 rows=46 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 53106) AND (doc_no <= 53155))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.93 rows=51 width=0) (actual time=0.002..0.003 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 54108) AND (doc_no <= 54157))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.92 rows=50 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 55110) AND (doc_no <= 55159))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.91 rows=49 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 56112) AND (doc_no <= 56161))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.92 rows=50 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 57114) AND (doc_no <= 57163))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.96 rows=53 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 58116) AND (doc_no <= 58165))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.92 rows=50 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 59118) AND (doc_no <= 59167))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.94 rows=52 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 60120) AND (doc_no <= 60169))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.88 rows=47 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 61122) AND (doc_no <= 61171))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.97 rows=54 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 62124) AND (doc_no <= 62173))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.91 rows=49 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 63126) AND (doc_no <= 63175))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.93 rows=51 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 64128) AND (doc_no <= 64177))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.88 rows=47 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 65130) AND (doc_no <= 65179))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.93 rows=51 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 66132) AND (doc_no <= 66181))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.94 rows=52 width=0) (actual time=0.002..0.003 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 67134) AND (doc_no <= 67183))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.91 rows=49 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 68136) AND (doc_no <= 68185))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.91 rows=49 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 69138) AND (doc_no <= 69187))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.92 rows=50 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 70140) AND (doc_no <= 70189))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.88 rows=47 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 71142) AND (doc_no <= 71191))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.88 rows=47 width=0) (actual time=0.002..0.003 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 72144) AND (doc_no <= 72193))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.87 rows=46 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 73146) AND (doc_no <= 73195))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.98 rows=55 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 74148) AND (doc_no <= 74197))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.92 rows=50 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 75150) AND (doc_no <= 75199))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.87 rows=46 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 76152) AND (doc_no <= 76201))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.93 rows=51 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 77154) AND (doc_no <= 77203))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.89 rows=48 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 78156) AND (doc_no <= 78205))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.93 rows=51 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 79158) AND (doc_no <= 79207))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.91 rows=49 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 80160) AND (doc_no <= 80209))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.99 rows=56 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 81162) AND (doc_no <= 81211))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.93 rows=51 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 82164) AND (doc_no <= 82213))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.92 rows=50 width=0) (actual time=0.002..0.003 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 83166) AND (doc_no <= 83215))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.96 rows=53 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 84168) AND (doc_no <= 84217))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.89 rows=48 width=0) (actual time=0.002..0.003 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 85170) AND (doc_no <= 85219))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.89 rows=48 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 86172) AND (doc_no <= 86221))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.89 rows=48 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 87174) AND (doc_no <= 87223))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.93 rows=51 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 88176) AND (doc_no <= 88225))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.94 rows=52 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 89178) AND (doc_no <= 89227))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.91 rows=49 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 90180) AND (doc_no <= 90229))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.92 rows=50 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 91182) AND (doc_no <= 91231))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.92 rows=50 width=0) (actual time=0.003..0.003 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 92184) AND (doc_no <= 92233))
                    Buffers: shared hit=3
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.89 rows=48 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 93186) AND (doc_no <= 93235))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.88 rows=47 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 94188) AND (doc_no <= 94237))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.91 rows=49 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 95190) AND (doc_no <= 95239))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.94 rows=52 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 96192) AND (doc_no <= 96241))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.92 rows=50 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 97194) AND (doc_no <= 97243))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.92 rows=50 width=0) (actual time=0.002..0.002 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 98196) AND (doc_no <= 98245))
                    Buffers: shared hit=2
              ->  Bitmap Index Scan on acl_ae3f5e6a_docs2_pkey  (cost=0.00..4.93 rows=51 width=0) (actual time=0.002..0.003 rows=50 loops=1)
                    Index Cond: ((epoch = 1) AND (doc_no >= 99198) AND (doc_no <= 99247))
                    Buffers: shared hit=2
Planning Time: 3.154 ms
Execution Time: 1.044 ms
```

### corpus · e_values · 100 spread

```
Aggregate  (cost=45439.42..45439.43 rows=1 width=16) (actual time=1.345..1.346 rows=1 loops=1)
  Buffers: shared hit=345
  ->  Nested Loop  (cost=0.29..39872.75 rows=1113333 width=4) (actual time=0.005..1.149 rows=5000 loops=1)
        Buffers: shared hit=345
        ->  Values Scan on "*VALUES*"  (cost=0.00..1.25 rows=100 width=8) (actual time=0.000..0.016 rows=100 loops=1)
        ->  Index Scan using acl_ae3f5e6a_docs2_pkey on acl_ae3f5e6a_docs2 d  (cost=0.29..287.39 rows=11133 width=8) (actual time=0.002..0.006 rows=50 loops=100)
              Index Cond: ((epoch = 1) AND (doc_no >= "*VALUES*".column1) AND (doc_no <= "*VALUES*".column2))
              Buffers: shared hit=345
Planning Time: 0.054 ms
Execution Time: 1.352 ms
```

### corpus · c_unnest · 100 spread

```
Aggregate  (cost=45270.19..45270.20 rows=1 width=16) (actual time=8.258..8.259 rows=1 loops=1)
  Buffers: shared hit=20765
  ->  Nested Loop  (cost=0.84..45242.30 rows=5577 width=4) (actual time=0.021..8.038 rows=5000 loops=1)
        Buffers: shared hit=20765
        ->  Nested Loop  (cost=0.42..42446.00 rows=5689 width=8) (actual time=0.015..1.945 rows=5100 loops=1)
              Buffers: shared hit=465
              ->  Function Scan on g  (cost=0.01..1.00 rows=100 width=64) (actual time=0.009..0.019 rows=100 loops=1)
              ->  Index Scan using acl_ae3f5e6a_ix_path on acl_ae3f5e6a_entries e  (cost=0.42..423.88 rows=57 width=27) (actual time=0.003..0.015 rows=51 loops=100)
                    Index Cond: ((path >= g.p) AND (path < g.hi))
                    Filter: ((path = g.p) OR (substr(path, (length(g.p) + 1), 1) = '/'::text))
                    Rows Removed by Filter: 1
                    Buffers: shared hit=465
        ->  Index Scan using acl_ae3f5e6a_ix_docs_entry on acl_ae3f5e6a_docs d  (cost=0.42..0.48 rows=1 width=12) (actual time=0.001..0.001 rows=1 loops=5100)
              Index Cond: ((epoch = 1) AND (entry_id = e.id))
              Buffers: shared hit=20300
Planning:
  Buffers: shared hit=6
Planning Time: 0.153 ms
Execution Time: 8.275 ms
```

### corpus · d_unnest · 100 spread

```
Aggregate  (cost=62838.02..62838.03 rows=1 width=16) (actual time=20.074..20.075 rows=1 loops=1)
  Buffers: shared hit=1094
  ->  Hash Join  (cost=3242.30..57271.35 rows=1113334 width=4) (actual time=17.565..19.866 rows=5000 loops=1)
        Hash Cond: (e.id = d.entry_id)
        Buffers: shared hit=1094
        ->  Nested Loop  (cost=0.30..38637.26 rows=1135667 width=8) (actual time=0.012..1.178 rows=5100 loops=1)
              Buffers: shared hit=357
              ->  Function Scan on g  (cost=0.01..1.00 rows=100 width=8) (actual time=0.008..0.026 rows=100 loops=1)
              ->  Index Scan using acl_ae3f5e6a_ix_pre on acl_ae3f5e6a_entries e  (cost=0.29..272.79 rows=11357 width=12) (actual time=0.002..0.007 rows=51 loops=100)
                    Index Cond: ((pre >= g.lo) AND (pre <= g.hi))
                    Buffers: shared hit=357
        ->  Hash  (cost=1989.50..1989.50 rows=100200 width=12) (actual time=17.536..17.537 rows=100200 loops=1)
              Buckets: 131072  Batches: 1  Memory Usage: 5721kB
              Buffers: shared hit=737
              ->  Seq Scan on acl_ae3f5e6a_docs d  (cost=0.00..1989.50 rows=100200 width=12) (actual time=0.003..7.819 rows=100200 loops=1)
                    Filter: (epoch = 1)
                    Buffers: shared hit=737
Planning:
  Buffers: shared hit=6
Planning Time: 0.131 ms
Execution Time: 20.097 ms
```

### corpus · e_unnest · 100 spread

```
Aggregate  (cost=45439.17..45439.18 rows=1 width=16) (actual time=1.583..1.583 rows=1 loops=1)
  Buffers: shared hit=345
  ->  Nested Loop  (cost=0.30..39872.51 rows=1113333 width=4) (actual time=0.015..1.368 rows=5000 loops=1)
        Buffers: shared hit=345
        ->  Function Scan on g  (cost=0.01..1.00 rows=100 width=8) (actual time=0.008..0.017 rows=100 loops=1)
        ->  Index Scan using acl_ae3f5e6a_docs2_pkey on acl_ae3f5e6a_docs2 d  (cost=0.29..287.39 rows=11133 width=8) (actual time=0.004..0.009 rows=50 loops=100)
              Index Cond: ((epoch = 1) AND (doc_no >= g.lo) AND (doc_no <= g.hi))
              Buffers: shared hit=345
Planning Time: 0.069 ms
Execution Time: 1.593 ms
```

### topk · a_like · 100 spread

```
Limit  (cost=4413.92..4413.94 rows=10 width=16) (actual time=25.328..25.397 rows=10 loops=1)
  Buffers: shared hit=1502
  ->  Sort  (cost=4413.92..4438.08 rows=9667 width=16) (actual time=25.326..25.394 rows=10 loops=1)
        Sort Key: ((((d.dl * 7919) + (d.chunk_id * 104729)) % '100003'::bigint)), d.chunk_id
        Sort Method: top-N heapsort  Memory: 25kB
        Buffers: shared hit=1502
        ->  Hash Join  (cost=1855.81..4205.01 rows=9667 width=16) (actual time=11.355..25.088 rows=5000 loops=1)
              Hash Cond: (d.entry_id = e.id)
              Buffers: shared hit=1502
              ->  Seq Scan on acl_ae3f5e6a_docs d  (cost=0.00..1989.50 rows=100200 width=20) (actual time=0.016..7.143 rows=100200 loops=1)
                    Filter: (epoch = 1)
                    Buffers: shared hit=737
              ->  Hash  (cost=1732.55..1732.55 rows=9861 width=8) (actual time=11.317..11.383 rows=5100 loops=1)
                    Buckets: 16384  Batches: 1  Memory Usage: 328kB
                    Buffers: shared hit=765
                    ->  Bitmap Heap Scan on acl_ae3f5e6a_entries e  (cost=1378.30..1732.55 rows=9861 width=8) (actual time=1.145..10.565 rows=5100 loops=1)
                          Recheck Cond: ((path = '/t00/f000'::text) OR (path ~~ '/t00/f000/%'::text) OR (path = '/t00/f020'::text) OR (path ~~ '/t00/f020/%'::text) OR (path = '/t00/f040'::text) OR (path ~~ '/t00/f040/%': …
                          Filter: ((path = '/t00/f000'::text) OR (path ~~ '/t00/f000/%'::text) OR (path = '/t00/f020'::text) OR (path ~~ '/t00/f020/%'::text) OR (path = '/t00/f040'::text) OR (path ~~ '/t00/f040/%'::text) …
                          Heap Blocks: exact=142
                          Buffers: shared hit=765
                          ->  BitmapOr  (cost=1378.30..1378.30 rows=107 width=0) (actual time=1.102..1.167 rows=0 loops=1)
                                Buffers: shared hit=623
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.012..0.012 rows=1 loops=1)
                                      Index Cond: (path = '/t00/f000'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t00/f000/'::text) AND (path < '/t00/f0000'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.005..0.005 rows=1 loops=1)
                                      Index Cond: (path = '/t00/f020'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t00/f020/'::text) AND (path < '/t00/f0200'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t00/f040'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t00/f040/'::text) AND (path < '/t00/f0400'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t00/f060'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t00/f060/'::text) AND (path < '/t00/f0600'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t00/f080'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t00/f080/'::text) AND (path < '/t00/f0800'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t00/f100'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t00/f100/'::text) AND (path < '/t00/f1000'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t00/f120'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t00/f120/'::text) AND (path < '/t00/f1200'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t00/f140'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.012..0.012 rows=50 loops=1)
                                      Index Cond: ((path >= '/t00/f140/'::text) AND (path < '/t00/f1400'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t00/f160'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t00/f160/'::text) AND (path < '/t00/f1600'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t00/f180'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t00/f180/'::text) AND (path < '/t00/f1800'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t01/f000'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t01/f000/'::text) AND (path < '/t01/f0000'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t01/f020'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t01/f020/'::text) AND (path < '/t01/f0200'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t01/f040'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t01/f040/'::text) AND (path < '/t01/f0400'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                                      Index Cond: (path = '/t01/f060'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t01/f060/'::text) AND (path < '/t01/f0600'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t01/f080'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t01/f080/'::text) AND (path < '/t01/f0800'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t01/f100'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t01/f100/'::text) AND (path < '/t01/f1000'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.005..0.005 rows=1 loops=1)
                                      Index Cond: (path = '/t01/f120'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t01/f120/'::text) AND (path < '/t01/f1200'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t01/f140'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t01/f140/'::text) AND (path < '/t01/f1400'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t01/f160'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t01/f160/'::text) AND (path < '/t01/f1600'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t01/f180'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t01/f180/'::text) AND (path < '/t01/f1800'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t02/f000'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t02/f000/'::text) AND (path < '/t02/f0000'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t02/f020'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t02/f020/'::text) AND (path < '/t02/f0200'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t02/f040'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t02/f040/'::text) AND (path < '/t02/f0400'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t02/f060'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t02/f060/'::text) AND (path < '/t02/f0600'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t02/f080'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t02/f080/'::text) AND (path < '/t02/f0800'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t02/f100'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t02/f100/'::text) AND (path < '/t02/f1000'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t02/f120'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t02/f120/'::text) AND (path < '/t02/f1200'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t02/f140'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t02/f140/'::text) AND (path < '/t02/f1400'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t02/f160'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t02/f160/'::text) AND (path < '/t02/f1600'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t02/f180'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t02/f180/'::text) AND (path < '/t02/f1800'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t03/f000'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t03/f000/'::text) AND (path < '/t03/f0000'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t03/f020'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t03/f020/'::text) AND (path < '/t03/f0200'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.005..0.005 rows=1 loops=1)
                                      Index Cond: (path = '/t03/f040'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t03/f040/'::text) AND (path < '/t03/f0400'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t03/f060'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t03/f060/'::text) AND (path < '/t03/f0600'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t03/f080'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t03/f080/'::text) AND (path < '/t03/f0800'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t03/f100'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t03/f100/'::text) AND (path < '/t03/f1000'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t03/f120'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t03/f120/'::text) AND (path < '/t03/f1200'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t03/f140'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t03/f140/'::text) AND (path < '/t03/f1400'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t03/f160'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t03/f160/'::text) AND (path < '/t03/f1600'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t03/f180'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t03/f180/'::text) AND (path < '/t03/f1800'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t04/f000'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t04/f000/'::text) AND (path < '/t04/f0000'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t04/f020'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t04/f020/'::text) AND (path < '/t04/f0200'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t04/f040'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t04/f040/'::text) AND (path < '/t04/f0400'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t04/f060'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t04/f060/'::text) AND (path < '/t04/f0600'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t04/f080'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t04/f080/'::text) AND (path < '/t04/f0800'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t04/f100'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t04/f100/'::text) AND (path < '/t04/f1000'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t04/f120'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t04/f120/'::text) AND (path < '/t04/f1200'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t04/f140'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t04/f140/'::text) AND (path < '/t04/f1400'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.005..0.005 rows=1 loops=1)
                                      Index Cond: (path = '/t04/f160'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t04/f160/'::text) AND (path < '/t04/f1600'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t04/f180'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t04/f180/'::text) AND (path < '/t04/f1800'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t05/f000'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t05/f000/'::text) AND (path < '/t05/f0000'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t05/f020'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t05/f020/'::text) AND (path < '/t05/f0200'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t05/f040'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t05/f040/'::text) AND (path < '/t05/f0400'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.005 rows=1 loops=1)
                                      Index Cond: (path = '/t05/f060'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t05/f060/'::text) AND (path < '/t05/f0600'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t05/f080'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t05/f080/'::text) AND (path < '/t05/f0800'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t05/f100'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t05/f100/'::text) AND (path < '/t05/f1000'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t05/f120'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t05/f120/'::text) AND (path < '/t05/f1200'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t05/f140'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t05/f140/'::text) AND (path < '/t05/f1400'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t05/f160'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t05/f160/'::text) AND (path < '/t05/f1600'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t05/f180'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t05/f180/'::text) AND (path < '/t05/f1800'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t06/f000'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t06/f000/'::text) AND (path < '/t06/f0000'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t06/f020'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t06/f020/'::text) AND (path < '/t06/f0200'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t06/f040'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t06/f040/'::text) AND (path < '/t06/f0400'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t06/f060'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t06/f060/'::text) AND (path < '/t06/f0600'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.005..0.005 rows=1 loops=1)
                                      Index Cond: (path = '/t06/f080'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t06/f080/'::text) AND (path < '/t06/f0800'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t06/f100'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t06/f100/'::text) AND (path < '/t06/f1000'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t06/f120'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t06/f120/'::text) AND (path < '/t06/f1200'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t06/f140'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t06/f140/'::text) AND (path < '/t06/f1400'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t06/f160'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t06/f160/'::text) AND (path < '/t06/f1600'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t06/f180'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t06/f180/'::text) AND (path < '/t06/f1800'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t07/f000'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t07/f000/'::text) AND (path < '/t07/f0000'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t07/f020'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t07/f020/'::text) AND (path < '/t07/f0200'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t07/f040'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t07/f040/'::text) AND (path < '/t07/f0400'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t07/f060'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.033..0.034 rows=50 loops=1)
                                      Index Cond: ((path >= '/t07/f060/'::text) AND (path < '/t07/f0600'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=1 loops=1)
                                      Index Cond: (path = '/t07/f080'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t07/f080/'::text) AND (path < '/t07/f0800'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t07/f100'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t07/f100/'::text) AND (path < '/t07/f1000'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t07/f120'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t07/f120/'::text) AND (path < '/t07/f1200'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t07/f140'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t07/f140/'::text) AND (path < '/t07/f1400'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t07/f160'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t07/f160/'::text) AND (path < '/t07/f1600'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t07/f180'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t07/f180/'::text) AND (path < '/t07/f1800'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.005 rows=1 loops=1)
                                      Index Cond: (path = '/t08/f000'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t08/f000/'::text) AND (path < '/t08/f0000'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t08/f020'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t08/f020/'::text) AND (path < '/t08/f0200'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t08/f040'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t08/f040/'::text) AND (path < '/t08/f0400'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t08/f060'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t08/f060/'::text) AND (path < '/t08/f0600'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t08/f080'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t08/f080/'::text) AND (path < '/t08/f0800'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t08/f100'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t08/f100/'::text) AND (path < '/t08/f1000'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t08/f120'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t08/f120/'::text) AND (path < '/t08/f1200'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=1 loops=1)
                                      Index Cond: (path = '/t08/f140'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t08/f140/'::text) AND (path < '/t08/f1400'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t08/f160'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t08/f160/'::text) AND (path < '/t08/f1600'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t08/f180'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t08/f180/'::text) AND (path < '/t08/f1800'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t09/f000'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t09/f000/'::text) AND (path < '/t09/f0000'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t09/f020'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t09/f020/'::text) AND (path < '/t09/f0200'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t09/f040'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t09/f040/'::text) AND (path < '/t09/f0400'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t09/f060'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t09/f060/'::text) AND (path < '/t09/f0600'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t09/f080'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t09/f080/'::text) AND (path < '/t09/f0800'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t09/f100'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t09/f100/'::text) AND (path < '/t09/f1000'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t09/f120'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t09/f120/'::text) AND (path < '/t09/f1200'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t09/f140'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t09/f140/'::text) AND (path < '/t09/f1400'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t09/f160'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t09/f160/'::text) AND (path < '/t09/f1600'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t09/f180'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t09/f180/'::text) AND (path < '/t09/f1800'::text))
                                      Buffers: shared hit=4
Planning:
  Buffers: shared hit=34
Planning Time: 3.317 ms
Execution Time: 26.157 ms
```

### topk · b_range · 100 spread

```
Limit  (cost=2102.80..2102.82 rows=10 width=16) (actual time=12.269..12.330 rows=10 loops=1)
  Buffers: shared hit=21065
  ->  Sort  (cost=2102.80..2103.06 rows=105 width=16) (actual time=12.268..12.327 rows=10 loops=1)
        Sort Key: ((((d.dl * 7919) + (d.chunk_id * 104729)) % '100003'::bigint)), d.chunk_id
        Sort Method: top-N heapsort  Memory: 25kB
        Buffers: shared hit=21065
        ->  Nested Loop  (cost=891.02..2100.53 rows=105 width=16) (actual time=1.252..11.845 rows=5000 loops=1)
              Buffers: shared hit=21065
              ->  Bitmap Heap Scan on acl_ae3f5e6a_entries e  (cost=890.60..1271.60 rows=107 width=8) (actual time=1.220..1.868 rows=5100 loops=1)
                    Recheck Cond: ((path = '/t00/f000'::text) OR ((path >= '/t00/f000/'::text) AND (path < '/t00/f0000'::text)) OR (path = '/t00/f020'::text) OR ((path >= '/t00/f020/'::text) AND (path < '/t00/f0200'::tex …
                    Heap Blocks: exact=142
                    Buffers: shared hit=765
                    ->  BitmapOr  (cost=890.60..890.60 rows=107 width=0) (actual time=1.190..1.248 rows=0 loops=1)
                          Buffers: shared hit=623
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.013..0.013 rows=1 loops=1)
                                Index Cond: (path = '/t00/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f000/'::text) AND (path < '/t00/f0000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.014..0.014 rows=1 loops=1)
                                Index Cond: (path = '/t00/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f020/'::text) AND (path < '/t00/f0200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t00/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f040/'::text) AND (path < '/t00/f0400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                                Index Cond: (path = '/t00/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f060/'::text) AND (path < '/t00/f0600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t00/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f080/'::text) AND (path < '/t00/f0800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t00/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f100/'::text) AND (path < '/t00/f1000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                                Index Cond: (path = '/t00/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f120/'::text) AND (path < '/t00/f1200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                                Index Cond: (path = '/t00/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f140/'::text) AND (path < '/t00/f1400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t00/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f160/'::text) AND (path < '/t00/f1600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t00/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f180/'::text) AND (path < '/t00/f1800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t01/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f000/'::text) AND (path < '/t01/f0000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                                Index Cond: (path = '/t01/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f020/'::text) AND (path < '/t01/f0200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t01/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f040/'::text) AND (path < '/t01/f0400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t01/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f060/'::text) AND (path < '/t01/f0600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t01/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f080/'::text) AND (path < '/t01/f0800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                                Index Cond: (path = '/t01/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f100/'::text) AND (path < '/t01/f1000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t01/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f120/'::text) AND (path < '/t01/f1200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t01/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f140/'::text) AND (path < '/t01/f1400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                                Index Cond: (path = '/t01/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f160/'::text) AND (path < '/t01/f1600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t01/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f180/'::text) AND (path < '/t01/f1800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t02/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f000/'::text) AND (path < '/t02/f0000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t02/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f020/'::text) AND (path < '/t02/f0200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t02/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f040/'::text) AND (path < '/t02/f0400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t02/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f060/'::text) AND (path < '/t02/f0600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t02/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f080/'::text) AND (path < '/t02/f0800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t02/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f100/'::text) AND (path < '/t02/f1000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t02/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f120/'::text) AND (path < '/t02/f1200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t02/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f140/'::text) AND (path < '/t02/f1400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t02/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f160/'::text) AND (path < '/t02/f1600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t02/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.013..0.013 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f180/'::text) AND (path < '/t02/f1800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t03/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f000/'::text) AND (path < '/t03/f0000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t03/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f020/'::text) AND (path < '/t03/f0200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.023..0.024 rows=1 loops=1)
                                Index Cond: (path = '/t03/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.009..0.009 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f040/'::text) AND (path < '/t03/f0400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.005 rows=1 loops=1)
                                Index Cond: (path = '/t03/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f060/'::text) AND (path < '/t03/f0600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t03/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f080/'::text) AND (path < '/t03/f0800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t03/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.042..0.042 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f100/'::text) AND (path < '/t03/f1000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.005..0.005 rows=1 loops=1)
                                Index Cond: (path = '/t03/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f120/'::text) AND (path < '/t03/f1200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t03/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f140/'::text) AND (path < '/t03/f1400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t03/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.013..0.013 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f160/'::text) AND (path < '/t03/f1600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t03/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f180/'::text) AND (path < '/t03/f1800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t04/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f000/'::text) AND (path < '/t04/f0000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t04/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f020/'::text) AND (path < '/t04/f0200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t04/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f040/'::text) AND (path < '/t04/f0400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t04/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f060/'::text) AND (path < '/t04/f0600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=1 loops=1)
                                Index Cond: (path = '/t04/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f080/'::text) AND (path < '/t04/f0800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t04/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f100/'::text) AND (path < '/t04/f1000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t04/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.011..0.011 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f120/'::text) AND (path < '/t04/f1200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t04/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f140/'::text) AND (path < '/t04/f1400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.005 rows=1 loops=1)
                                Index Cond: (path = '/t04/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f160/'::text) AND (path < '/t04/f1600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t04/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f180/'::text) AND (path < '/t04/f1800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t05/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f000/'::text) AND (path < '/t05/f0000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t05/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.009..0.009 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f020/'::text) AND (path < '/t05/f0200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t05/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f040/'::text) AND (path < '/t05/f0400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t05/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.048..0.048 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f060/'::text) AND (path < '/t05/f0600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.005..0.005 rows=1 loops=1)
                                Index Cond: (path = '/t05/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f080/'::text) AND (path < '/t05/f0800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t05/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f100/'::text) AND (path < '/t05/f1000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t05/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f120/'::text) AND (path < '/t05/f1200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t05/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f140/'::text) AND (path < '/t05/f1400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t05/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f160/'::text) AND (path < '/t05/f1600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t05/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.009..0.009 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f180/'::text) AND (path < '/t05/f1800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t06/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f000/'::text) AND (path < '/t06/f0000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t06/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f020/'::text) AND (path < '/t06/f0200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t06/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f040/'::text) AND (path < '/t06/f0400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t06/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f060/'::text) AND (path < '/t06/f0600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.005..0.005 rows=1 loops=1)
                                Index Cond: (path = '/t06/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f080/'::text) AND (path < '/t06/f0800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t06/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f100/'::text) AND (path < '/t06/f1000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t06/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.009..0.009 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f120/'::text) AND (path < '/t06/f1200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t06/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f140/'::text) AND (path < '/t06/f1400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t06/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f160/'::text) AND (path < '/t06/f1600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t06/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f180/'::text) AND (path < '/t06/f1800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t07/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f000/'::text) AND (path < '/t07/f0000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t07/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f020/'::text) AND (path < '/t07/f0200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t07/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f040/'::text) AND (path < '/t07/f0400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t07/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f060/'::text) AND (path < '/t07/f0600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t07/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f080/'::text) AND (path < '/t07/f0800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t07/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f100/'::text) AND (path < '/t07/f1000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t07/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f120/'::text) AND (path < '/t07/f1200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t07/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f140/'::text) AND (path < '/t07/f1400'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t07/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f160/'::text) AND (path < '/t07/f1600'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                                Index Cond: (path = '/t07/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f180/'::text) AND (path < '/t07/f1800'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t08/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f000/'::text) AND (path < '/t08/f0000'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t08/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f020/'::text) AND (path < '/t08/f0200'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t08/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f040/'::text) AND (path < '/t08/f0400'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t08/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f060/'::text) AND (path < '/t08/f0600'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.005 rows=1 loops=1)
                                Index Cond: (path = '/t08/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f080/'::text) AND (path < '/t08/f0800'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t08/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f100/'::text) AND (path < '/t08/f1000'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t08/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f120/'::text) AND (path < '/t08/f1200'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t08/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f140/'::text) AND (path < '/t08/f1400'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t08/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f160/'::text) AND (path < '/t08/f1600'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t08/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f180/'::text) AND (path < '/t08/f1800'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t09/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f000/'::text) AND (path < '/t09/f0000'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t09/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f020/'::text) AND (path < '/t09/f0200'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t09/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f040/'::text) AND (path < '/t09/f0400'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                                Index Cond: (path = '/t09/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f060/'::text) AND (path < '/t09/f0600'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t09/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f080/'::text) AND (path < '/t09/f0800'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t09/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f100/'::text) AND (path < '/t09/f1000'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t09/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f120/'::text) AND (path < '/t09/f1200'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t09/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f140/'::text) AND (path < '/t09/f1400'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t09/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.010..0.010 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f160/'::text) AND (path < '/t09/f1600'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                                Index Cond: (path = '/t09/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f180/'::text) AND (path < '/t09/f1800'::text))
                                Buffers: shared hit=4
              ->  Index Scan using acl_ae3f5e6a_ix_docs_entry on acl_ae3f5e6a_docs d  (cost=0.42..7.73 rows=1 width=20) (actual time=0.002..0.002 rows=1 loops=5100)
                    Index Cond: ((epoch = 1) AND (entry_id = e.id))
                    Buffers: shared hit=20300
Planning:
  Buffers: shared hit=34
Planning Time: 2.428 ms
Execution Time: 13.435 ms
```

### topk · a_like_semi · 100 spread

```
Limit  (cost=4413.92..4413.94 rows=10 width=16) (actual time=25.169..25.228 rows=10 loops=1)
  Buffers: shared hit=1502
  ->  Sort  (cost=4413.92..4438.08 rows=9667 width=16) (actual time=25.167..25.225 rows=10 loops=1)
        Sort Key: ((((d.dl * 7919) + (d.chunk_id * 104729)) % '100003'::bigint)), d.chunk_id
        Sort Method: top-N heapsort  Memory: 25kB
        Buffers: shared hit=1502
        ->  Hash Join  (cost=1855.81..4205.01 rows=9667 width=16) (actual time=11.137..24.917 rows=5000 loops=1)
              Hash Cond: (d.entry_id = e.id)
              Buffers: shared hit=1502
              ->  Seq Scan on acl_ae3f5e6a_docs d  (cost=0.00..1989.50 rows=100200 width=20) (actual time=0.018..7.116 rows=100200 loops=1)
                    Filter: (epoch = 1)
                    Buffers: shared hit=737
              ->  Hash  (cost=1732.55..1732.55 rows=9861 width=8) (actual time=11.097..11.154 rows=5100 loops=1)
                    Buckets: 16384  Batches: 1  Memory Usage: 328kB
                    Buffers: shared hit=765
                    ->  Bitmap Heap Scan on acl_ae3f5e6a_entries e  (cost=1378.30..1732.55 rows=9861 width=8) (actual time=1.167..10.181 rows=5100 loops=1)
                          Recheck Cond: ((path = '/t00/f000'::text) OR (path ~~ '/t00/f000/%'::text) OR (path = '/t00/f020'::text) OR (path ~~ '/t00/f020/%'::text) OR (path = '/t00/f040'::text) OR (path ~~ '/t00/f040/%': …
                          Filter: ((path = '/t00/f000'::text) OR (path ~~ '/t00/f000/%'::text) OR (path = '/t00/f020'::text) OR (path ~~ '/t00/f020/%'::text) OR (path = '/t00/f040'::text) OR (path ~~ '/t00/f040/%'::text) …
                          Heap Blocks: exact=142
                          Buffers: shared hit=765
                          ->  BitmapOr  (cost=1378.30..1378.30 rows=107 width=0) (actual time=1.124..1.179 rows=0 loops=1)
                                Buffers: shared hit=623
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.013..0.013 rows=1 loops=1)
                                      Index Cond: (path = '/t00/f000'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t00/f000/'::text) AND (path < '/t00/f0000'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.009..0.009 rows=1 loops=1)
                                      Index Cond: (path = '/t00/f020'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t00/f020/'::text) AND (path < '/t00/f0200'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t00/f040'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t00/f040/'::text) AND (path < '/t00/f0400'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t00/f060'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t00/f060/'::text) AND (path < '/t00/f0600'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t00/f080'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t00/f080/'::text) AND (path < '/t00/f0800'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t00/f100'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t00/f100/'::text) AND (path < '/t00/f1000'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                                      Index Cond: (path = '/t00/f120'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t00/f120/'::text) AND (path < '/t00/f1200'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t00/f140'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t00/f140/'::text) AND (path < '/t00/f1400'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t00/f160'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t00/f160/'::text) AND (path < '/t00/f1600'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t00/f180'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t00/f180/'::text) AND (path < '/t00/f1800'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t01/f000'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t01/f000/'::text) AND (path < '/t01/f0000'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                                      Index Cond: (path = '/t01/f020'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t01/f020/'::text) AND (path < '/t01/f0200'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t01/f040'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t01/f040/'::text) AND (path < '/t01/f0400'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t01/f060'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t01/f060/'::text) AND (path < '/t01/f0600'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t01/f080'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t01/f080/'::text) AND (path < '/t01/f0800'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t01/f100'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t01/f100/'::text) AND (path < '/t01/f1000'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t01/f120'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t01/f120/'::text) AND (path < '/t01/f1200'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t01/f140'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t01/f140/'::text) AND (path < '/t01/f1400'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t01/f160'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t01/f160/'::text) AND (path < '/t01/f1600'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t01/f180'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t01/f180/'::text) AND (path < '/t01/f1800'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t02/f000'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t02/f000/'::text) AND (path < '/t02/f0000'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t02/f020'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t02/f020/'::text) AND (path < '/t02/f0200'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t02/f040'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t02/f040/'::text) AND (path < '/t02/f0400'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t02/f060'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t02/f060/'::text) AND (path < '/t02/f0600'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t02/f080'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t02/f080/'::text) AND (path < '/t02/f0800'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t02/f100'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t02/f100/'::text) AND (path < '/t02/f1000'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t02/f120'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t02/f120/'::text) AND (path < '/t02/f1200'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t02/f140'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t02/f140/'::text) AND (path < '/t02/f1400'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t02/f160'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t02/f160/'::text) AND (path < '/t02/f1600'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t02/f180'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t02/f180/'::text) AND (path < '/t02/f1800'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t03/f000'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t03/f000/'::text) AND (path < '/t03/f0000'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t03/f020'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t03/f020/'::text) AND (path < '/t03/f0200'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.005..0.005 rows=1 loops=1)
                                      Index Cond: (path = '/t03/f040'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t03/f040/'::text) AND (path < '/t03/f0400'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t03/f060'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t03/f060/'::text) AND (path < '/t03/f0600'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t03/f080'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t03/f080/'::text) AND (path < '/t03/f0800'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t03/f100'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t03/f100/'::text) AND (path < '/t03/f1000'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t03/f120'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t03/f120/'::text) AND (path < '/t03/f1200'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t03/f140'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t03/f140/'::text) AND (path < '/t03/f1400'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t03/f160'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t03/f160/'::text) AND (path < '/t03/f1600'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t03/f180'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t03/f180/'::text) AND (path < '/t03/f1800'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t04/f000'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t04/f000/'::text) AND (path < '/t04/f0000'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t04/f020'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t04/f020/'::text) AND (path < '/t04/f0200'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.005 rows=1 loops=1)
                                      Index Cond: (path = '/t04/f040'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t04/f040/'::text) AND (path < '/t04/f0400'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t04/f060'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t04/f060/'::text) AND (path < '/t04/f0600'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t04/f080'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t04/f080/'::text) AND (path < '/t04/f0800'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t04/f100'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t04/f100/'::text) AND (path < '/t04/f1000'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t04/f120'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t04/f120/'::text) AND (path < '/t04/f1200'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t04/f140'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t04/f140/'::text) AND (path < '/t04/f1400'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.005 rows=1 loops=1)
                                      Index Cond: (path = '/t04/f160'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t04/f160/'::text) AND (path < '/t04/f1600'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t04/f180'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t04/f180/'::text) AND (path < '/t04/f1800'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t05/f000'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t05/f000/'::text) AND (path < '/t05/f0000'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t05/f020'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t05/f020/'::text) AND (path < '/t05/f0200'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t05/f040'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t05/f040/'::text) AND (path < '/t05/f0400'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t05/f060'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t05/f060/'::text) AND (path < '/t05/f0600'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t05/f080'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t05/f080/'::text) AND (path < '/t05/f0800'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t05/f100'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t05/f100/'::text) AND (path < '/t05/f1000'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t05/f120'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t05/f120/'::text) AND (path < '/t05/f1200'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t05/f140'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t05/f140/'::text) AND (path < '/t05/f1400'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t05/f160'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t05/f160/'::text) AND (path < '/t05/f1600'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t05/f180'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t05/f180/'::text) AND (path < '/t05/f1800'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t06/f000'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t06/f000/'::text) AND (path < '/t06/f0000'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t06/f020'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t06/f020/'::text) AND (path < '/t06/f0200'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t06/f040'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t06/f040/'::text) AND (path < '/t06/f0400'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t06/f060'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t06/f060/'::text) AND (path < '/t06/f0600'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.027..0.027 rows=1 loops=1)
                                      Index Cond: (path = '/t06/f080'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.011..0.012 rows=50 loops=1)
                                      Index Cond: ((path >= '/t06/f080/'::text) AND (path < '/t06/f0800'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t06/f100'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t06/f100/'::text) AND (path < '/t06/f1000'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t06/f120'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t06/f120/'::text) AND (path < '/t06/f1200'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t06/f140'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t06/f140/'::text) AND (path < '/t06/f1400'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t06/f160'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t06/f160/'::text) AND (path < '/t06/f1600'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t06/f180'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t06/f180/'::text) AND (path < '/t06/f1800'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t07/f000'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t07/f000/'::text) AND (path < '/t07/f0000'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t07/f020'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t07/f020/'::text) AND (path < '/t07/f0200'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t07/f040'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t07/f040/'::text) AND (path < '/t07/f0400'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t07/f060'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t07/f060/'::text) AND (path < '/t07/f0600'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t07/f080'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                      Index Cond: ((path >= '/t07/f080/'::text) AND (path < '/t07/f0800'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t07/f100'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t07/f100/'::text) AND (path < '/t07/f1000'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t07/f120'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t07/f120/'::text) AND (path < '/t07/f1200'::text))
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t07/f140'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.009..0.009 rows=50 loops=1)
                                      Index Cond: ((path >= '/t07/f140/'::text) AND (path < '/t07/f1400'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t07/f160'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t07/f160/'::text) AND (path < '/t07/f1600'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t07/f180'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t07/f180/'::text) AND (path < '/t07/f1800'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.005..0.005 rows=1 loops=1)
                                      Index Cond: (path = '/t08/f000'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t08/f000/'::text) AND (path < '/t08/f0000'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t08/f020'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t08/f020/'::text) AND (path < '/t08/f0200'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t08/f040'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t08/f040/'::text) AND (path < '/t08/f0400'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t08/f060'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t08/f060/'::text) AND (path < '/t08/f0600'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t08/f080'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t08/f080/'::text) AND (path < '/t08/f0800'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t08/f100'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t08/f100/'::text) AND (path < '/t08/f1000'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t08/f120'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                      Index Cond: ((path >= '/t08/f120/'::text) AND (path < '/t08/f1200'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t08/f140'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t08/f140/'::text) AND (path < '/t08/f1400'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t08/f160'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t08/f160/'::text) AND (path < '/t08/f1600'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t08/f180'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t08/f180/'::text) AND (path < '/t08/f1800'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t09/f000'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.020..0.020 rows=50 loops=1)
                                      Index Cond: ((path >= '/t09/f000/'::text) AND (path < '/t09/f0000'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t09/f020'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t09/f020/'::text) AND (path < '/t09/f0200'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t09/f040'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t09/f040/'::text) AND (path < '/t09/f0400'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t09/f060'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t09/f060/'::text) AND (path < '/t09/f0600'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t09/f080'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t09/f080/'::text) AND (path < '/t09/f0800'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t09/f100'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t09/f100/'::text) AND (path < '/t09/f1000'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.005 rows=1 loops=1)
                                      Index Cond: (path = '/t09/f120'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t09/f120/'::text) AND (path < '/t09/f1200'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                                      Index Cond: (path = '/t09/f140'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t09/f140/'::text) AND (path < '/t09/f1400'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                      Index Cond: (path = '/t09/f160'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t09/f160/'::text) AND (path < '/t09/f1600'::text))
                                      Buffers: shared hit=4
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                                      Index Cond: (path = '/t09/f180'::text)
                                      Buffers: shared hit=3
                                ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                      Index Cond: ((path >= '/t09/f180/'::text) AND (path < '/t09/f1800'::text))
                                      Buffers: shared hit=4
Planning:
  Buffers: shared hit=34
Planning Time: 3.397 ms
Execution Time: 26.626 ms
```

### topk · b_range_semi · 100 spread

```
Limit  (cost=2102.80..2102.82 rows=10 width=16) (actual time=11.948..12.007 rows=10 loops=1)
  Buffers: shared hit=21065
  ->  Sort  (cost=2102.80..2103.06 rows=105 width=16) (actual time=11.946..12.004 rows=10 loops=1)
        Sort Key: ((((d.dl * 7919) + (d.chunk_id * 104729)) % '100003'::bigint)), d.chunk_id
        Sort Method: top-N heapsort  Memory: 25kB
        Buffers: shared hit=21065
        ->  Nested Loop  (cost=891.02..2100.53 rows=105 width=16) (actual time=1.236..11.551 rows=5000 loops=1)
              Buffers: shared hit=21065
              ->  Bitmap Heap Scan on acl_ae3f5e6a_entries e  (cost=890.60..1271.60 rows=107 width=8) (actual time=1.199..1.851 rows=5100 loops=1)
                    Recheck Cond: ((path = '/t00/f000'::text) OR ((path >= '/t00/f000/'::text) AND (path < '/t00/f0000'::text)) OR (path = '/t00/f020'::text) OR ((path >= '/t00/f020/'::text) AND (path < '/t00/f0200'::tex …
                    Heap Blocks: exact=142
                    Buffers: shared hit=765
                    ->  BitmapOr  (cost=890.60..890.60 rows=107 width=0) (actual time=1.163..1.220 rows=0 loops=1)
                          Buffers: shared hit=623
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.015..0.016 rows=1 loops=1)
                                Index Cond: (path = '/t00/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f000/'::text) AND (path < '/t00/f0000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=1 loops=1)
                                Index Cond: (path = '/t00/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f020/'::text) AND (path < '/t00/f0200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t00/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f040/'::text) AND (path < '/t00/f0400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t00/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f060/'::text) AND (path < '/t00/f0600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t00/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f080/'::text) AND (path < '/t00/f0800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t00/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f100/'::text) AND (path < '/t00/f1000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t00/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f120/'::text) AND (path < '/t00/f1200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t00/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f140/'::text) AND (path < '/t00/f1400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t00/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f160/'::text) AND (path < '/t00/f1600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t00/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t00/f180/'::text) AND (path < '/t00/f1800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t01/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f000/'::text) AND (path < '/t01/f0000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                                Index Cond: (path = '/t01/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f020/'::text) AND (path < '/t01/f0200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t01/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f040/'::text) AND (path < '/t01/f0400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t01/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f060/'::text) AND (path < '/t01/f0600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t01/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f080/'::text) AND (path < '/t01/f0800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t01/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f100/'::text) AND (path < '/t01/f1000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.005..0.005 rows=1 loops=1)
                                Index Cond: (path = '/t01/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f120/'::text) AND (path < '/t01/f1200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t01/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f140/'::text) AND (path < '/t01/f1400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t01/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f160/'::text) AND (path < '/t01/f1600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t01/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t01/f180/'::text) AND (path < '/t01/f1800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t02/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f000/'::text) AND (path < '/t02/f0000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t02/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f020/'::text) AND (path < '/t02/f0200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t02/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.027..0.027 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f040/'::text) AND (path < '/t02/f0400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.005..0.005 rows=1 loops=1)
                                Index Cond: (path = '/t02/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f060/'::text) AND (path < '/t02/f0600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t02/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f080/'::text) AND (path < '/t02/f0800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t02/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f100/'::text) AND (path < '/t02/f1000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t02/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f120/'::text) AND (path < '/t02/f1200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t02/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f140/'::text) AND (path < '/t02/f1400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.005..0.005 rows=1 loops=1)
                                Index Cond: (path = '/t02/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f160/'::text) AND (path < '/t02/f1600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t02/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t02/f180/'::text) AND (path < '/t02/f1800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t03/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f000/'::text) AND (path < '/t03/f0000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t03/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f020/'::text) AND (path < '/t03/f0200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.005..0.005 rows=1 loops=1)
                                Index Cond: (path = '/t03/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f040/'::text) AND (path < '/t03/f0400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t03/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f060/'::text) AND (path < '/t03/f0600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t03/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.014..0.014 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f080/'::text) AND (path < '/t03/f0800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t03/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f100/'::text) AND (path < '/t03/f1000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t03/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f120/'::text) AND (path < '/t03/f1200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t03/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f140/'::text) AND (path < '/t03/f1400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t03/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f160/'::text) AND (path < '/t03/f1600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t03/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t03/f180/'::text) AND (path < '/t03/f1800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t04/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f000/'::text) AND (path < '/t04/f0000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t04/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f020/'::text) AND (path < '/t04/f0200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t04/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f040/'::text) AND (path < '/t04/f0400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t04/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f060/'::text) AND (path < '/t04/f0600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t04/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f080/'::text) AND (path < '/t04/f0800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t04/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f100/'::text) AND (path < '/t04/f1000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t04/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f120/'::text) AND (path < '/t04/f1200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t04/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f140/'::text) AND (path < '/t04/f1400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.005..0.005 rows=1 loops=1)
                                Index Cond: (path = '/t04/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f160/'::text) AND (path < '/t04/f1600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t04/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t04/f180/'::text) AND (path < '/t04/f1800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t05/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f000/'::text) AND (path < '/t05/f0000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t05/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f020/'::text) AND (path < '/t05/f0200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.005 rows=1 loops=1)
                                Index Cond: (path = '/t05/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f040/'::text) AND (path < '/t05/f0400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t05/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f060/'::text) AND (path < '/t05/f0600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t05/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f080/'::text) AND (path < '/t05/f0800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t05/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f100/'::text) AND (path < '/t05/f1000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.005..0.005 rows=1 loops=1)
                                Index Cond: (path = '/t05/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f120/'::text) AND (path < '/t05/f1200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t05/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f140/'::text) AND (path < '/t05/f1400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t05/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f160/'::text) AND (path < '/t05/f1600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t05/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t05/f180/'::text) AND (path < '/t05/f1800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t06/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f000/'::text) AND (path < '/t06/f0000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t06/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f020/'::text) AND (path < '/t06/f0200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t06/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f040/'::text) AND (path < '/t06/f0400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t06/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f060/'::text) AND (path < '/t06/f0600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.005..0.005 rows=1 loops=1)
                                Index Cond: (path = '/t06/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f080/'::text) AND (path < '/t06/f0800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t06/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f100/'::text) AND (path < '/t06/f1000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t06/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f120/'::text) AND (path < '/t06/f1200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t06/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f140/'::text) AND (path < '/t06/f1400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t06/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f160/'::text) AND (path < '/t06/f1600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t06/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t06/f180/'::text) AND (path < '/t06/f1800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t07/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f000/'::text) AND (path < '/t07/f0000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t07/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f020/'::text) AND (path < '/t07/f0200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t07/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f040/'::text) AND (path < '/t07/f0400'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t07/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f060/'::text) AND (path < '/t07/f0600'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t07/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.006 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f080/'::text) AND (path < '/t07/f0800'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t07/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.006..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f100/'::text) AND (path < '/t07/f1000'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t07/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f120/'::text) AND (path < '/t07/f1200'::text))
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t07/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f140/'::text) AND (path < '/t07/f1400'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t07/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f160/'::text) AND (path < '/t07/f1600'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t07/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t07/f180/'::text) AND (path < '/t07/f1800'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.005..0.005 rows=1 loops=1)
                                Index Cond: (path = '/t08/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f000/'::text) AND (path < '/t08/f0000'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=1)
                                Index Cond: (path = '/t08/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f020/'::text) AND (path < '/t08/f0200'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t08/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f040/'::text) AND (path < '/t08/f0400'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t08/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f060/'::text) AND (path < '/t08/f0600'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t08/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f080/'::text) AND (path < '/t08/f0800'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t08/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f100/'::text) AND (path < '/t08/f1000'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t08/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f120/'::text) AND (path < '/t08/f1200'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t08/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f140/'::text) AND (path < '/t08/f1400'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t08/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f160/'::text) AND (path < '/t08/f1600'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t08/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.010..0.010 rows=50 loops=1)
                                Index Cond: ((path >= '/t08/f180/'::text) AND (path < '/t08/f1800'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t09/f000'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.009 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f000/'::text) AND (path < '/t09/f0000'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t09/f020'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.016..0.016 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f020/'::text) AND (path < '/t09/f0200'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t09/f040'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f040/'::text) AND (path < '/t09/f0400'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t09/f060'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.007..0.007 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f060/'::text) AND (path < '/t09/f0600'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t09/f080'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f080/'::text) AND (path < '/t09/f0800'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.003..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t09/f100'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f100/'::text) AND (path < '/t09/f1000'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.005 rows=1 loops=1)
                                Index Cond: (path = '/t09/f120'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f120/'::text) AND (path < '/t09/f1200'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.027..0.027 rows=1 loops=1)
                                Index Cond: (path = '/t09/f140'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.011..0.011 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f140/'::text) AND (path < '/t09/f1400'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t09/f160'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f160/'::text) AND (path < '/t09/f1600'::text))
                                Buffers: shared hit=4
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.004..0.004 rows=1 loops=1)
                                Index Cond: (path = '/t09/f180'::text)
                                Buffers: shared hit=3
                          ->  Bitmap Index Scan on acl_ae3f5e6a_ix_path  (cost=0.00..4.43 rows=1 width=0) (actual time=0.008..0.008 rows=50 loops=1)
                                Index Cond: ((path >= '/t09/f180/'::text) AND (path < '/t09/f1800'::text))
                                Buffers: shared hit=4
              ->  Index Scan using acl_ae3f5e6a_ix_docs_entry on acl_ae3f5e6a_docs d  (cost=0.42..7.73 rows=1 width=20) (actual time=0.002..0.002 rows=1 loops=5100)
                    Index Cond: ((epoch = 1) AND (entry_id = e.id))
                    Buffers: shared hit=20300
Planning:
  Buffers: shared hit=34
Planning Time: 2.618 ms
Execution Time: 13.648 ms
```

### topk · c_values · 100 spread

```
Limit  (cost=45418.83..45418.86 rows=10 width=16) (actual time=14.131..14.133 rows=10 loops=1)
  Buffers: shared hit=20765
  ->  Sort  (cost=45418.83..45432.78 rows=5577 width=16) (actual time=14.129..14.130 rows=10 loops=1)
        Sort Key: ((((d.dl * 7919) + (d.chunk_id * 104729)) % '100003'::bigint)), d.chunk_id
        Sort Method: top-N heapsort  Memory: 25kB
        Buffers: shared hit=20765
        ->  Nested Loop  (cost=0.83..45298.32 rows=5577 width=16) (actual time=0.050..13.609 rows=5000 loops=1)
              Buffers: shared hit=20765
              ->  Nested Loop  (cost=0.42..42446.25 rows=5689 width=8) (actual time=0.025..2.843 rows=5100 loops=1)
                    Buffers: shared hit=465
                    ->  Values Scan on "*VALUES*"  (cost=0.00..1.25 rows=100 width=64) (actual time=0.002..0.037 rows=100 loops=1)
                    ->  Index Scan using acl_ae3f5e6a_ix_path on acl_ae3f5e6a_entries e  (cost=0.42..423.88 rows=57 width=27) (actual time=0.005..0.023 rows=51 loops=100)
                          Index Cond: ((path >= "*VALUES*".column1) AND (path < "*VALUES*".column2))
                          Filter: ((path = "*VALUES*".column1) OR (substr(path, (length("*VALUES*".column1) + 1), 1) = '/'::text))
                          Rows Removed by Filter: 1
                          Buffers: shared hit=465
              ->  Index Scan using acl_ae3f5e6a_ix_docs_entry on acl_ae3f5e6a_docs d  (cost=0.42..0.48 rows=1 width=20) (actual time=0.002..0.002 rows=1 loops=5100)
                    Index Cond: ((epoch = 1) AND (entry_id = e.id))
                    Buffers: shared hit=20300
Planning:
  Buffers: shared hit=6
Planning Time: 0.432 ms
Execution Time: 14.167 ms
```

### topk · e_values · 100 spread

```
Limit  (cost=75064.81..75064.83 rows=10 width=16) (actual time=2.443..2.445 rows=10 loops=1)
  Buffers: shared hit=345
  ->  Sort  (cost=75064.81..77848.14 rows=1113333 width=16) (actual time=2.442..2.442 rows=10 loops=1)
        Sort Key: ((((d.dl * 7919) + (d.chunk_id * 104729)) % '100003'::bigint)), d.chunk_id
        Sort Method: top-N heapsort  Memory: 25kB
        Buffers: shared hit=345
        ->  Nested Loop  (cost=0.29..51006.08 rows=1113333 width=16) (actual time=0.036..1.998 rows=5000 loops=1)
              Buffers: shared hit=345
              ->  Values Scan on "*VALUES*"  (cost=0.00..1.25 rows=100 width=8) (actual time=0.002..0.028 rows=100 loops=1)
              ->  Index Scan using acl_ae3f5e6a_docs2_pkey on acl_ae3f5e6a_docs2 d  (cost=0.29..287.39 rows=11133 width=16) (actual time=0.006..0.012 rows=50 loops=100)
                    Index Cond: ((epoch = 1) AND (doc_no >= "*VALUES*".column1) AND (doc_no <= "*VALUES*".column2))
                    Buffers: shared hit=345
Planning Time: 0.268 ms
Execution Time: 2.475 ms
```
