# sqlite — N = 10,000

World: {'users': 10000, 'groups': 50, 'shared': 100, 'grant_rows': 21401, 'memberships': 50000, 'entries': 230303, 'files_per_home': 20, 'files_per_shared': 200}
Load: {'entries_s': 4.76831958303228, 'grants_s': 0.3056695410050452, 'analyze_s': 0.08357545826584101}

## 1. Resolution (ms)

| caller | cold resolve_authority | warm hit | pure resolve(read) | everyone_arms | rows read | read arms | holes | owner arms |
|---|---|---|---|---|---|---|---|---|
| ordinary | 118.03 | 0.59 | 66.55 | 11.89 | 10037 | 2 | 10000 | 1 |
| heavy (u005437) | 151.37 | 1.09 | 88.36 | 12.28 | 10063 | 2 | 10000 | 1 |
| pair | 77.97 | 0.51 | 36.22 | 13.36 | 10085 | 1 | 10000 | 2 |
| anonymous | 68.57 | 1.73 | 14.51 | 12.39 | 10001 | 1 | 10000 | 0 |
| system | 0.02 | 0.01 | — | — | — | 1 | 0 | 0 |

## 2. ranges()/pieces (read rights)

| caller | shipped pieces ms | linear pieces ms | equal | points | opens | owner pieces | bind bytes |
|---|---|---|---|---|---|---|---|
| ordinary | 18355.13 | 17.48 | True | 10000 | 19999 | 2 | 919,925 |
| heavy (u005437) | 20323.31 | 16.76 | True | 10000 | 19999 | 2 | 919,925 |
| pair | 20839.66 | 18.69 | True | 10001 | 20001 | 98 | 920,017 |
| anonymous | 22061.08 | 21.83 | True | 10001 | 20001 | 0 | 920,017 |

## 3. Range join (visible_entries)

| caller | count cold ms | count warm ms | count | fetch cold ms | fetch warm ms | rows |
|---|---|---|---|---|---|---|
| ordinary | 33.62 | 30.81 | 20324 | 84.54 | 83.3 | 20324 |
| heavy (u005437) | 56.23 | 31.18 | 20324 | 89.36 | 78.71 | 20324 |
| pair | 31.7 | 31.43 | 20303 | 85.03 | 77.15 | 20303 |
| anonymous | 31.36 | 29.36 | 20303 | 79.87 | 76.72 | 20303 |

Recall (ordinary): {'sample_rows': 1221, 'oracle_agrees_with_admits': True, 'admits_sample_s': 0.12, 'exact_visible': 20324, 'stored': 230303, 'join_rows': 20324, 'recall': 1.0, 'extra': 0}

Plan of the ordinary caller's count statement:

```
CO-ROUTINE visible
COMPOUND QUERY
LEFT-MOST SUBQUERY
SCAN anon_1 VIRTUAL TABLE INDEX 1:
SEARCH bl_9b130e59 USING INDEX ix_bl_9b130e59_path (path=?)
UNION USING TEMP B-TREE
SCAN anon_2 VIRTUAL TABLE INDEX 1:
SEARCH bl_9b130e59 USING INDEX ix_bl_9b130e59_path (path>? AND path<?)
UNION USING TEMP B-TREE
SEARCH bl_9b130e59 USING INDEX ix_bl_9b130e59_owner_id (owner_id=?)
SCAN anon_3 VIRTUAL TABLE INDEX 1:
UNION USING TEMP B-TREE
SEARCH bl_9b130e59 USING INDEX ix_bl_9b130e59_owner_id (owner_id=?)
SCAN anon_4 VIRTUAL TABLE INDEX 1:
SCAN visible
SEARCH bl_9b130e59 USING COVERING INDEX ix_bl_9b130e59_entry_id (entry_id=?)
```

## 4. Clause fan (visibility_clauses)

| caller | clauses | build ms | clause binds | clause terms | cold ms | warm ms | result |
|---|---|---|---|---|---|---|---|
| ordinary | 2 | 212.72 | 20000 | 40000 | None | None | None |
| ordinary | 2 | 212.72 | 3 | 7 | 1.92 | 1.1 | 21 |
| pair | 2 | 394.07 | 20000 | 40000 | None | None | None |
| pair | 2 | 394.07 | 100 | 200 | 7.49 | 1.66 | 0 |
| anonymous | 1 | 415.36 | 20000 | 40000 | None | None | None |

## 5. End to end through DatabaseStorage (ms; cold = first call in a fresh process, warm = second)

| caller | verb | cold ms | warm ms | rows | note |
|---|---|---|---|---|---|
| ordinary | tree / | 21183.66 | 4170.42 | 20323 |  |
| ordinary | glob /shared/*/*.md | 4237.95 | 4094.49 | 20000 |  |
| ordinary | ls /home | 938.05 | 824.96 | 101 |  |
| pair | tree / | 21980.58 | 4217.18 | 20302 |  |
| pair | glob /shared/*/*.md | 4182.23 | 4064.68 | 20000 |  |
| pair | ls /home | 940.12 | 861.39 | 100 |  |
| anonymous | tree / | 21913.28 | 4238.42 | 20302 |  |
| anonymous | glob /shared/*/*.md | 4164.14 | 4204.75 | 20000 |  |
| anonymous | ls /home | 883.27 | 818.65 | 100 |  |
| system | tree / | 2001.27 | 3094.18 | 230302 |  |
| system | glob /shared/*/*.md | 177.4 | 147.79 | 20000 |  |
| system | ls /home | 86.44 | 132.57 | 10100 |  |

## 6. Cache churn: {'cached_before': 20, 'callers': 20, 'misses_after_one_grant': 20, 'recompute_s_for_callers': 2.718, 'cache_capacity': 256}

## 7. Memory: {'resolution_bytes': 702491, 'with_read_ranges_bytes': 4242845, 'x256_cache_mb': 1086.2}

## 8. Rights.admits per row (ordinary)

- own home file: 1.0 µs (admitted=True)
- shared file (root arm): 199.8 µs (admitted=True)
- another user's home file (hidden): 113.7 µs (admitted=False)
- trap file: 181.0 µs (admitted=True)

Total wall time 220.2s.
