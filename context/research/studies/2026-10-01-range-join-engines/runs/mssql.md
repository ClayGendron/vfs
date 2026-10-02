## mssql — 41,421 entries, 121,200 chunks, loaded in 17s, median of 3 warm runs (ms)

| caller | pieces | arms: clauses | statement | arms | literal | join IN | join derived | recall arms / literal / join IN / join derived |
|---|---|---|---|---|---|---|---|---|
| 1 grant (10%) | 4 | 1 | entries | 37.4 | 8.2 | 26.7 | 24.2 | 1.00 / 1.00 / 1.00 / 1.00 |
| 1 grant (10%) | 4 | 1 | count | 33.0 | 10.8 | 37.9 | 40.4 | 1.00 / 1.00 / 1.00 / 1.00 |
| 1 grant (10%) | 4 | 1 | top10 | 11.7 | 9.4 | 1,401 (1 run) | 6.0 | 1.00 / 1.00 / 1.00 / 1.00 |
| 10 grants (1%) | 22 | 1 | entries | 126.7 | 139.1 | 4.4 | 5.3 | 1.00 / 1.00 / 1.00 / 1.00 |
| 10 grants (1%) | 22 | 1 | count | 130.2 | 154.4 | 21.7 | 21.9 | 1.00 / 1.00 / 1.00 / 1.00 |
| 10 grants (1%) | 22 | 1 | top10 | 128.9 | 13.8 | 8,328 (1 run) | 59.6 | 1.00 / 1.00 / 1.00 / 1.00 |
| 100 grants (10%) | 202 | 1 | entries | 1,299 (1 run) | — | 16.6 | 14.9 | 1.00 / — / 1.00 / 1.00 |
| 100 grants (10%) | 202 | 1 | count | 1,321 (1 run) | — | 30.5 | 30.5 | 1.00 / — / 1.00 / 1.00 |
| 100 grants (10%) | 202 | 1 | top10 | 1,339 (1 run) | — | 1,147 (1 run) | 45.2 | 1.00 / — / 1.00 / 1.00 |
| 500 grants (50%) | 1002 | 3 | entries | 2,107 (1 run) | — | 36.8 | 35.0 | 1.00 / — / 1.00 / 1.00 |
| 500 grants (50%) | 1002 | 3 | count | 2,199 (1 run) | — | 48.9 | 46.5 | 1.00 / — / 1.00 / 1.00 |
| 500 grants (50%) | 1002 | 3 | top10 | 2,295 (1 run) | — | 209.4 | 27.9 | 1.00 / — / 1.00 / 1.00 |
| open root, 50 holes | 154 | 1 | entries | 624.0 | — | 47.3 | 48.7 | 1.00 / — / 1.00 / 1.00 |
| open root, 50 holes | 154 | 1 | count | 713.9 | — | 54.5 | 52.0 | 1.00 / — / 1.00 / 1.00 |
| open root, 50 holes | 154 | 1 | top10 | 4.7 | — | 29.6 | 8.0 | 1.00 / — / 1.00 / 1.00 |
| 10 grants + owns 2% | 22 | 1 | entries | 126.1 | 143.7 | 14.1 | 13.5 | 1.00 / 1.00 / 1.00 / 1.00 |
| 10 grants + owns 2% | 22 | 1 | count | 152.1 | 159.3 | 27.5 | 32.0 | 1.00 / 1.00 / 1.00 / 1.00 |
| 10 grants + owns 2% | 22 | 1 | top10 | 6.9 | 6.2 | 2,160 (1 run) | 18.4 | 1.00 / 1.00 / 1.00 / 1.00 |

Plan of the join's count statement, 100 grants:

```
plan unavailable: ResourceClosedError: This result object does not return rows. It has been closed automatically.
```

Total wall time 59s.
