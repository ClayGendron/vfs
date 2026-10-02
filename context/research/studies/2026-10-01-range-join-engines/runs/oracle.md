## oracle — 41,421 entries, 121,200 chunks, loaded in 4s, median of 3 warm runs (ms)

| caller | pieces | arms: clauses | statement | arms | literal | join IN | join derived | recall arms / literal / join IN / join derived |
|---|---|---|---|---|---|---|---|---|
| 1 grant (10%) | 4 | 1 | entries | 28.0 | 27.5 | 48.4 | 47.7 | 1.00 / 1.00 / 1.00 / 1.00 |
| 1 grant (10%) | 4 | 1 | count | 95.0 | 5.9 | 3,689 (1 run) | 27.4 | 1.00 / 1.00 / 1.00 / 1.00 |
| 1 grant (10%) | 4 | 1 | top10 | 6.7 | 7.4 | 7.6 | 44.1 | 1.00 / 1.00 / 1.00 / 1.00 |
| 10 grants (1%) | 22 | 1 | entries | 4.5 | 3.7 | 35.5 | 35.3 | 1.00 / 1.00 / 1.00 / 1.00 |
| 10 grants (1%) | 22 | 1 | count | 12.0 | 1.5 | 4,175 (1 run) | 44.1 | 1.00 / 1.00 / 1.00 / 1.00 |
| 10 grants (1%) | 22 | 1 | top10 | 2.6 | 9.0 | 69.6 | 56.4 | 1.00 / 1.00 / 1.00 / 1.00 |
| 100 grants (10%) | 202 | 1 | entries | 230.4 | — | 206.4 | 196.4 | 1.00 / — / 1.00 / 1.00 |
| 100 grants (10%) | 202 | 1 | count | 193.7 | — | 13,761 (1 run) | 183.2 | 1.00 / — / 1.00 / 1.00 |
| 100 grants (10%) | 202 | 1 | top10 | 106.1 | — | 17.7 | 194.6 | 1.00 / — / 1.00 / 1.00 |
| 500 grants (50%) | 1002 | 3 | entries | 720.8 | — | 2,766 (1 run) | 960.3 | 1.00 / — / 1.00 / 1.00 |
| 500 grants (50%) | 1002 | 3 | count | 1,175 (1 run) | — | 54,807 (1 run) | 793.2 | 1.00 / — / 1.00 / 1.00 |
| 500 grants (50%) | 1002 | 3 | top10 | 508.9 | — | 12.8 | 786.9 | 1.00 / — / 1.00 / 1.00 |
| open root, 50 holes | 154 | 1 | entries | 451.4 | — | 569.2 | 563.6 | 1.00 / — / 1.00 / 1.00 |
| open root, 50 holes | 154 | 1 | count | 1,280 (1 run) | — | 12,007 (1 run) | 188.9 | 1.00 / — / 1.00 / 1.00 |
| open root, 50 holes | 154 | 1 | top10 | 2.4 | — | 2.8 | 194.6 | 1.00 / — / 1.00 / 1.00 |
| 10 grants + owns 2% | 22 | 1 | entries | 8.7 | 9.0 | 46.5 | 46.1 | 1.00 / 1.00 / 1.00 / 1.00 |
| 10 grants + owns 2% | 22 | 1 | count | 28.1 | 3.0 | 36,841 (1 run) | 41.0 | 1.00 / 1.00 / 1.00 / 1.00 |
| 10 grants + owns 2% | 22 | 1 | top10 | 4.2 | 4.2 | 85.3 | 46.6 | 1.00 / 1.00 / 1.00 / 1.00 |

Plan of the join's count statement, 100 grants:

```
Plan hash value: 872625534
 
-----------------------------------------------------------------------
| Id  | Operation                         | Name              | Rows  |
-----------------------------------------------------------------------
|   0 | SELECT STATEMENT                  |                   |     1 |
|   1 |  SORT AGGREGATE                   |                   |     1 |
|   2 |   NESTED LOOPS                    |                   |  2592K|
|   3 |    INDEX FAST FULL SCAN           | IX_RJ_2E91F556_CE |   121K|
|   4 |    VIEW                           | VW_NSO_1          |    21 |
|   5 |     SORT UNIQUE                   |                   |       |
|   6 |      UNION-ALL PARTITION          |                   |       |
|   7 |       HASH JOIN                   |                   |     1 |
|   8 |        TABLE ACCESS BY INDEX ROWID| RJ_2E91F556_E     |     1 |
|   9 |         INDEX UNIQUE SCAN         | SYS_C00101380     |     1 |
|  10 |        JSONTABLE EVALUATION       |                   |       |
|  11 |       NESTED LOOPS                |                   |    20 |
|  12 |        TABLE ACCESS BY INDEX ROWID| RJ_2E91F556_E     |     1 |
|  13 |         INDEX UNIQUE SCAN         | SYS_C00101380     |     1 |
|  14 |        JSONTABLE EVALUATION       |                   |       |
|  15 |       HASH JOIN                   |                   |     1 |
|  16 |        TABLE ACCESS BY INDEX ROWID| RJ_2E91F556_E     |     1 |
|  17 |         INDEX UNIQUE SCAN         | SYS_C00101380     |     1 |
|  18 |        JSONTABLE EVALUATION       |                   |       |
|  19 |       NESTED LOOPS                |                   |    20 |
|  20 |        TABLE ACCESS BY INDEX ROWID| RJ_2E91F556_E     |     1 |
|  21 |         INDEX UNIQUE SCAN         | SYS_C00101380     |     1 |
|  22 |        JSONTABLE EVALUATION       |                   |       |
-----------------------------------------------------------------------
```

Total wall time 173s.
