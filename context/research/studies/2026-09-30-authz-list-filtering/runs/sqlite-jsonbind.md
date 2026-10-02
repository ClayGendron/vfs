## sqlite — 50,000 entries, the count statement end to end, median of 5 warm runs (ms)

| caller | ranges | values (statements) | json_each (1 statement) |
|---|---|---|---|
| 1 folders (0.1%) | 2 | 0.5 (1) | 0.2 |
| 10 folders (1.0%) | 20 | 0.9 (1) | 0.3 |
| 100 folders (10.0%) | 200 | 4.6 (1) | 1.2 |
| 500 folders (50.0%) | 1,000 | 22.7 (1) | 5.6 |
| 10% via 1 top | 2 | 1.4 (1) | 1.0 |
| 10% via 5000 files | 10,000 | 181.5 (10) | 11.2 |

Plan:

```
5 | 0 | 0 | SCAN c VIRTUAL TABLE INDEX 1:
10 | 0 | 156 | SEARCH e USING COVERING INDEX ix_azj_434c9497_entry_path (path>? AND path<?)
21 | 0 | 54 | SEARCH d USING COVERING INDEX ix_azj_434c9497_docs_entry_id (entry_id=?)
```
