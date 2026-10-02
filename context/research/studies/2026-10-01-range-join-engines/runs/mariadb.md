## mariadb — 41,421 entries, 121,200 chunks, loaded in 2s, median of 3 warm runs (ms)

| caller | pieces | arms: clauses | statement | arms | literal | join IN | join derived | recall arms / literal / join IN / join derived |
|---|---|---|---|---|---|---|---|---|
| 1 grant (10%) | 4 | 1 | entries | 16.9 | 24.4 | 19.7 | 16.3 | 1.00 / 1.00 / 1.00 / 1.00 |
| 1 grant (10%) | 4 | 1 | count | 33.2 | 8.8 | 599.9 | 20.3 | 1.00 / 1.00 / 1.00 / 1.00 |
| 1 grant (10%) | 4 | 1 | top10 | 12.9 | 12.9 | 3.9 | 2.6 | 1.00 / 1.00 / 1.00 / 1.00 |
| 10 grants (1%) | 22 | 1 | entries | 2.3 | 2.2 | 1.9 | 2.0 | 1.00 / 1.00 / 1.00 / 1.00 |
| 10 grants (1%) | 22 | 1 | count | 4.0 | 1.8 | 941.0 | 16.4 | 1.00 / 1.00 / 1.00 / 1.00 |
| 10 grants (1%) | 22 | 1 | top10 | 2.6 | 2.6 | 34.6 | 2.3 | 1.00 / 1.00 / 1.00 / 1.00 |
| 100 grants (10%) | 202 | 1 | entries | 206.5 | — | 11.3 | 11.4 | 1.00 / — / 1.00 / 1.00 |
| 100 grants (10%) | 202 | 1 | count | 219.3 | — | 4,952 (1 run) | 23.5 | 1.00 / — / 1.00 / 1.00 |
| 100 grants (10%) | 202 | 1 | top10 | 6.4 | — | 29.6 | 9.7 | 1.00 / — / 1.00 / 1.00 |
| 500 grants (50%) | 1002 | 3 | entries | 387.9 | — | 62.1 | 66.9 | 1.00 / — / 1.00 / 1.00 |
| 500 grants (50%) | 1002 | 3 | count | 403.8 | — | 21,626 (1 run) | 31.1 | 1.00 / — / 1.00 / 1.00 |
| 500 grants (50%) | 1002 | 3 | top10 | 124.5 | — | 16.5 | 15.2 | 1.00 / — / 1.00 / 1.00 |
| open root, 50 holes | 154 | 1 | entries | 129.1 | — | 91.8 | 107.6 | 1.00 / — / 1.00 / 1.00 |
| open root, 50 holes | 154 | 1 | count | 270.1 | — | 4,074 (1 run) | 35.7 | 1.00 / — / 1.00 / 1.00 |
| open root, 50 holes | 154 | 1 | top10 | 1.2 | — | 2.1 | 17.4 | 1.00 / — / 1.00 / 1.00 |
| 10 grants + owns 2% | 22 | 1 | entries | 4.4 | 4.6 | 4.4 | 4.3 | 1.00 / 1.00 / 1.00 / 1.00 |
| 10 grants + owns 2% | 22 | 1 | count | 10.3 | 3.3 | 930.0 | 17.5 | 1.00 / 1.00 / 1.00 / 1.00 |
| 10 grants + owns 2% | 22 | 1 | top10 | 5.7 | 5.7 | 9.5 | 3.2 | 1.00 / 1.00 / 1.00 / 1.00 |

Plan of the join's count statement, 100 grants:

```
PRIMARY c index key=ix_rj_03606080_ce rows=121352 Using where; Using index
DEPENDENT SUBQUERY ap ALL key=None rows=40 Table function: json_table
DEPENDENT SUBQUERY e eq_ref key=PRIMARY rows=1 Using where
DEPENDENT UNION ar ALL key=None rows=40 Table function: json_table
DEPENDENT UNION e eq_ref key=PRIMARY rows=1 Using where
DEPENDENT UNION o0p ALL key=None rows=40 Table function: json_table
DEPENDENT UNION e eq_ref key=PRIMARY rows=1 Using where
DEPENDENT UNION o0r ALL key=None rows=40 Table function: json_table
DEPENDENT UNION e eq_ref key=PRIMARY rows=1 Using where
UNION RESULT <union2,3,4,5> ALL key=None rows=None 
```

Total wall time 54s.
