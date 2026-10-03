# sqlite — N = 1,000

World: {'users': 1000, 'groups': 5, 'shared': 10, 'grant_rows': 2141, 'memberships': 5000, 'entries': 23213, 'files_per_home': 20, 'files_per_shared': 200}
Load: {'entries_s': 0.4832715829834342, 'grants_s': 0.030558125115931034, 'analyze_s': 0.011033667251467705}

## 1. Resolution (ms)

| caller | cold resolve_authority | warm hit | pure resolve(read) | everyone_arms | rows read | read arms | holes | owner arms |
|---|---|---|---|---|---|---|---|---|
| ordinary | 10.18 | 0.37 | 2.81 | 0.9 | 1043 | 2 | 1000 | 1 |
| heavy (u000986) | 10.15 | 0.37 | 2.72 | 0.98 | 1045 | 2 | 1000 | 1 |
| pair | 9.86 | 0.33 | 2.73 | 0.9 | 1044 | 1 | 1000 | 2 |
| anonymous | 6.09 | 0.26 | 1.04 | 0.92 | 1001 | 1 | 1000 | 0 |
| system | 0.01 | 0.0 | — | — | — | 1 | 0 | 0 |

## 2. ranges()/pieces (read rights)

| caller | shipped pieces ms | linear pieces ms | equal | points | opens | owner pieces | bind bytes |
|---|---|---|---|---|---|---|---|
| ordinary | 113.46 | 1.26 | True | 1000 | 1999 | 2 | 91,925 |
| heavy (u000986) | 113.2 | 1.25 | True | 1000 | 1999 | 2 | 91,925 |
| pair | 113.92 | 1.31 | True | 1001 | 2001 | 4 | 92,017 |
| anonymous | 111.54 | 1.29 | True | 1001 | 2001 | 0 | 92,017 |

## 3. Range join (visible_entries)

| caller | count cold ms | count warm ms | count | fetch cold ms | fetch warm ms | rows |
|---|---|---|---|---|---|---|
| ordinary | 6.49 | 4.47 | 2234 | 10.94 | 9.13 | 2234 |
| heavy (u000986) | 4.32 | 3.93 | 2234 | 8.8 | 9.34 | 2234 |
| pair | 5.22 | 3.82 | 2213 | 9.81 | 9.06 | 2213 |
| anonymous | 5.54 | 4.24 | 2213 | 9.21 | 8.79 | 2213 |

Recall (ordinary): {'sample_rows': 1221, 'oracle_agrees_with_admits': True, 'admits_sample_s': 0.02, 'exact_visible': 2234, 'stored': 23213, 'join_rows': 2234, 'recall': 1.0, 'extra': 0}

Plan of the ordinary caller's count statement:

```
CO-ROUTINE visible
COMPOUND QUERY
LEFT-MOST SUBQUERY
SCAN anon_1 VIRTUAL TABLE INDEX 1:
SEARCH bl_142c1ff4 USING INDEX ix_bl_142c1ff4_path (path=?)
UNION USING TEMP B-TREE
SCAN anon_2 VIRTUAL TABLE INDEX 1:
SEARCH bl_142c1ff4 USING INDEX ix_bl_142c1ff4_path (path>? AND path<?)
UNION USING TEMP B-TREE
SEARCH bl_142c1ff4 USING INDEX ix_bl_142c1ff4_owner_id (owner_id=?)
SCAN anon_3 VIRTUAL TABLE INDEX 1:
UNION USING TEMP B-TREE
SEARCH bl_142c1ff4 USING INDEX ix_bl_142c1ff4_owner_id (owner_id=?)
SCAN anon_4 VIRTUAL TABLE INDEX 1:
SCAN visible
SEARCH bl_142c1ff4 USING COVERING INDEX ix_bl_142c1ff4_entry_id (entry_id=?)
```

## 4. Clause fan (visibility_clauses)

| caller | clauses | build ms | clause binds | clause terms | cold ms | warm ms | result |
|---|---|---|---|---|---|---|---|
| ordinary | 1 | 19.51 | 2003 | 4007 | None | None | None |
| pair | 1 | 57.52 | 2006 | 4012 | None | None | None |
| anonymous | 1 | 20.9 | 2000 | 4000 | None | None | None |

Hole ladder (one root arm with H holes, one clause, count statement):

| holes | binds | cold ms | warm ms | result |
|---|---|---|---|---|
| 500 | 1001 | 439.05 | 421.57 | 12713 |
| 900 | 1801 | 614.52 | 583.37 | 4313 |
| 990 | 1981 | 644.87 | 641.35 | 2423 |
| 1000 | 2001 | None | None | None |
| 1010 | 2021 | None | None | None |
| 1100 | 2201 | None | None | None |
| 2000 | 4001 | None | None | None |

## 5. End to end through DatabaseStorage (ms; cold = first call in a fresh process, warm = second)

| caller | verb | cold ms | warm ms | rows | note |
|---|---|---|---|---|---|
| ordinary | tree / | 233.65 | 69.01 | 2233 |  |
| ordinary | glob /shared/*/*.md | 93.83 | 90.11 | 2000 |  |
| ordinary | ls /home | 56.5 | 45.66 | 101 |  |
| pair | tree / | 241.35 | 79.89 | 2212 |  |
| pair | glob /shared/*/*.md | 77.45 | 61.22 | 2000 |  |
| pair | ls /home | 47.46 | 34.74 | 100 |  |
| anonymous | tree / | 191.78 | 67.39 | 2212 |  |
| anonymous | glob /shared/*/*.md | 68.48 | 61.9 | 2000 |  |
| anonymous | ls /home | 30.85 | 21.27 | 100 |  |
| system | tree / | 135.38 | 227.41 | 23212 |  |
| system | glob /shared/*/*.md | 19.06 | 18.21 | 2000 |  |
| system | ls /home | 15.24 | 11.31 | 1100 |  |

## 6. Cache churn: {'cached_before': 20, 'callers': 20, 'misses_after_one_grant': 20, 'recompute_s_for_callers': 0.215, 'cache_capacity': 256}

## 7. Memory: {'resolution_bytes': 72491, 'with_read_ranges_bytes': 426845, 'x256_cache_mb': 109.3}

## 8. Rights.admits per row (ordinary)

- own home file: 1.0 µs (admitted=True)
- shared file (root arm): 21.0 µs (admitted=True)
- another user's home file (hidden): 12.4 µs (admitted=False)
- trap file: 18.9 µs (admitted=True)

Meet ladder (out of world): [{'grants': 1000, 'single_ms': 1.95, 'pair_ms': 248.67}, {'grants': 3000, 'single_ms': 6.72, 'pair_ms': 2256.59}, {'grants': 10000, 'single_ms': 18.82, 'pair_ms': 25680.39}]

Total wall time 44.4s.
