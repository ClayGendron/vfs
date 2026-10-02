## sqlite — 41,421 entries, 121,200 chunks, loaded in 1s, median of 3 warm runs (ms)

| caller | pieces | arms: clauses | statement | arms | literal | join IN | join derived | recall arms / literal / join IN / join derived |
|---|---|---|---|---|---|---|---|---|
| 1 grant (10%) | 4 | 1 | entries | 2.7 | 7.2 | 10.0 | 12.8 | 1.00 / 1.00 / 1.00 / 1.00 |
| 1 grant (10%) | 4 | 1 | count | 16.4 | 6.2 | 8.1 | 5.5 | 1.00 / 1.00 / 1.00 / 1.00 |
| 1 grant (10%) | 4 | 1 | top10 | 2.4 | 5.9 | 6.7 | 6.5 | 1.00 / 1.00 / 1.00 / 1.00 |
| 10 grants (1%) | 22 | 1 | entries | 24.0 | 6.3 | 5.4 | 7.4 | 1.00 / 1.00 / 1.00 / 1.00 |
| 10 grants (1%) | 22 | 1 | count | 25.5 | 3.3 | 3.0 | 5.1 | 1.00 / 1.00 / 1.00 / 1.00 |
| 10 grants (1%) | 22 | 1 | top10 | 3.7 | 11.8 | 5.2 | 4.2 | 1.00 / 1.00 / 1.00 / 1.00 |
| 100 grants (10%) | 202 | 1 | entries | 176.1 | — | 5.4 | 5.1 | 1.00 / — / 1.00 / 1.00 |
| 100 grants (10%) | 202 | 1 | count | 173.8 | — | 5.2 | 4.8 | 1.00 / — / 1.00 / 1.00 |
| 100 grants (10%) | 202 | 1 | top10 | 2.5 | — | 6.0 | 5.3 | 1.00 / — / 1.00 / 1.00 |
| 500 grants (50%) | 1002 | 3 | entries | 179.2 | — | 15.1 | 15.5 | 1.00 / — / 1.00 / 1.00 |
| 500 grants (50%) | 1002 | 3 | count | 274.1 | — | 13.8 | 12.6 | 1.00 / — / 1.00 / 1.00 |
| 500 grants (50%) | 1002 | 3 | top10 | 89.5 | — | 17.5 | 20.2 | 1.00 / — / 1.00 / 1.00 |
| open root, 50 holes | 154 | 1 | entries | 101.4 | — | 23.7 | 23.7 | 1.00 / — / 1.00 / 1.00 |
| open root, 50 holes | 154 | 1 | count | 163.4 | — | 20.5 | 17.5 | 1.00 / — / 1.00 / 1.00 |
| open root, 50 holes | 154 | 1 | top10 | 1.0 | — | 26.0 | 23.1 | 1.00 / — / 1.00 / 1.00 |
| 10 grants + owns 2% | 22 | 1 | entries | 19.3 | 3.4 | 3.3 | 3.5 | 1.00 / 1.00 / 1.00 / 1.00 |
| 10 grants + owns 2% | 22 | 1 | count | 21.5 | 4.1 | 3.6 | 3.5 | 1.00 / 1.00 / 1.00 / 1.00 |
| 10 grants + owns 2% | 22 | 1 | top10 | 1.3 | 4.9 | 4.3 | 4.4 | 1.00 / 1.00 / 1.00 / 1.00 |

Plan of the join's count statement, 100 grants:

```
SEARCH c USING COVERING INDEX ix_rj_f5b1ee30_ce (entry_id=?)
LIST SUBQUERY 4
COMPOUND QUERY
LEFT-MOST SUBQUERY
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ux_rj_f5b1ee30_path (path=?)
UNION USING TEMP B-TREE
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ux_rj_f5b1ee30_path (path>? AND path<?)
UNION USING TEMP B-TREE
SCAN o0p VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ux_rj_f5b1ee30_path (path=?)
UNION USING TEMP B-TREE
SCAN o0r VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ux_rj_f5b1ee30_path (path>? AND path<?)
CREATE BLOOM FILTER
```

Total wall time 8s.
