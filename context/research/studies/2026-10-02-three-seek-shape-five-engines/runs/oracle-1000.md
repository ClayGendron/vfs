## oracle — N=1,000 users: 23,113 entries, 66,000 chunks (3/file), 1,140 grant rows, 1,101 posture rows, 100 sibling traps

Load (tables, rows, indexes, statistics): 7s.

### Indexes

| index | size |
|---|---|
| `path` | 2.1 MB |
| `owner` | 1.0 MB |
| `lvlpath` | 2.1 MB |
| (entries table) | 2.1 MB |

### Callers

| caller | subjects | pieces (arms + owner) | bind bytes | compile us | visible entries |
|---|---|---|---|---|---|
| ordinary | u000042 | 22 | 630 | 111 | 2,034 |
| heavy group | u000000 | 22 | 630 | 76 | 2,034 |
| two subjects | u000042, u000000 | 64 | 1,804 | 169 | 2,013 |
| anonymous | — | 0 | 0 | 0 | 2,013 |
| system | — | 0 | 0 | 0 | 23,113 |

### Statements — cold = fresh connection, warm = median of 1 (ms); recall against the Python truth

Shapes: union, unionall, literal, disjoint. A blank cell is a shape that does not apply to that caller.

| caller | statement | union: cold / warm / recall | unionall: cold / warm / recall | literal: cold / warm / recall | disjoint: cold / warm / recall |
|---|---|---|---|---|---|
| ordinary | entries | 58.2 / 19.6 / exact | 34.9 / 20.7 / exact | 23.8 / 16.8 / exact | 24.7 / 17.5 / exact |
| ordinary | scoped | 23.7 / 2.7 / exact | 9.0 / 1.8 / exact | 8.3 / 3.2 / exact | 10.4 / 2.5 / exact |
| ordinary | count | 23.8 / 10.7 / exact | 24.5 / 11.0 / exact | 39.8 / 3.6 / exact | 1,987 / 1,973 / exact |
| ordinary | top10 | 22.8 / 12.1 / exact | 22.4 / 12.3 / exact | 42.0 / 4.0 / exact | 15.9 / 5.5 / exact |
| heavy group | entries | 24.3 / 20.6 / exact | 23.1 / 21.2 / exact | 20.4 / 19.0 / exact | 20.5 / 20.7 / exact |
| heavy group | scoped | 3.6 / 2.1 / exact | 3.3 / 2.2 / exact | 3.1 / 2.3 / exact | 2.5 / 1.7 / exact |
| heavy group | count | 13.7 / 11.8 / exact | 15.2 / 11.6 / exact | 5.8 / 3.1 / exact | 2,146 / 2,051 / exact |
| heavy group | top10 | 41.1 / 20.4 / exact | 45.8 / 20.6 / exact | 14.8 / 5.1 / exact | 8.5 / 7.0 / exact |
| two subjects | entries | 43.4 / 31.0 / exact | 57.7 / 22.6 / exact | 29.2 / 17.1 / exact | 28.0 / 18.6 / exact |
| two subjects | scoped | 11.3 / 2.4 / exact | 13.9 / 2.2 / exact | 13.9 / 2.3 / exact | 14.0 / 2.3 / exact |
| two subjects | count | 29.5 / 10.1 / exact | 25.6 / 9.8 / exact | 34.8 / 6.1 / exact | 7,396 / 4,698 / exact |
| two subjects | top10 | 49.4 / 20.0 / exact | 48.4 / 16.9 / exact | 37.6 / 4.4 / exact | 30.6 / 20.0 / exact |
| anonymous | entries | 37.0 / 30.9 / exact |  |  |  |
| anonymous | scoped | 10.2 / 4.9 / exact |  |  |  |
| anonymous | count | 8.7 / 8.4 / exact |  |  |  |
| anonymous | top10 | 8.2 / 3.4 / exact |  |  |  |
| system | entries | 323 / 246 / exact |  |  |  |
| system | scoped | 3.6 / 1.5 / exact |  |  |  |
| system | count | 11.7 / 8.5 / exact |  |  |  |
| system | top10 | 6.8 / 1.3 / exact |  |  |  |

### Scoped read, branch 1 spelled `everyone_level >= :r` against `everyone_level IN (...)`

| caller | shape | `>=` cold / warm | `IN` cold / warm | recall |
|---|---|---|---|---|
| anonymous | union | 5.8 / 2.9 | 11.0 / 4.7 | exact |
| ordinary | union | 5.5 / 5.5 | 11.4 / 5.0 | exact |
| ordinary | unionall | 3.5 / 2.3 | 15.6 / 5.9 | exact |
| ordinary | literal | 5.9 / 2.3 | 6.0 / 4.6 | exact |
| ordinary | disjoint | 6.5 / 4.7 | 27.1 / 5.1 | exact |

### Plans

**ordinary / union / entries**

```
 
-----------------------------------------------------------------------------
| Id  | Operation                             | Name                | Rows  |
-----------------------------------------------------------------------------
|   0 | SELECT STATEMENT                      |                     |   251K|
|   1 |  HASH UNIQUE                          |                     |   251K|
|   2 |   UNION-ALL                           |                     |   251K|
|   3 |    TABLE ACCESS FULL                  | TS_C2D297E5_E       | 11558 |
|   4 |    HASH JOIN                          |                     |  4088 |
|   5 |     JSONTABLE EVALUATION              |                     |       |
|   6 |     TABLE ACCESS FULL                 | TS_C2D297E5_E       | 11558 |
|   7 |    MERGE JOIN                         |                     |   236K|
|   8 |     SORT JOIN                         |                     |  8168 |
|   9 |      JSONTABLE EVALUATION             |                     |       |
|  10 |     FILTER                            |                     |       |
|  11 |      SORT JOIN                        |                     | 11558 |
|  12 |       TABLE ACCESS FULL               | TS_C2D297E5_E       | 11558 |
|  13 |    TABLE ACCESS BY INDEX ROWID BATCHED| TS_C2D297E5_E       |    11 |
|  14 |     INDEX RANGE SCAN                  | TS_C2D297E5_E_OWNER |    22 |
-----------------------------------------------------------------------------
```

**ordinary / unionall / entries**

```
 
-----------------------------------------------------------------------------
| Id  | Operation                             | Name                | Rows  |
-----------------------------------------------------------------------------
|   0 | SELECT STATEMENT                      |                     |   251K|
|   1 |  HASH UNIQUE                          |                     |   251K|
|   2 |   UNION-ALL                           |                     |   251K|
|   3 |    TABLE ACCESS FULL                  | TS_C2D297E5_E       | 11558 |
|   4 |    HASH JOIN                          |                     |  4088 |
|   5 |     JSONTABLE EVALUATION              |                     |       |
|   6 |     TABLE ACCESS FULL                 | TS_C2D297E5_E       | 11558 |
|   7 |    MERGE JOIN                         |                     |   236K|
|   8 |     SORT JOIN                         |                     |  8168 |
|   9 |      JSONTABLE EVALUATION             |                     |       |
|  10 |     FILTER                            |                     |       |
|  11 |      SORT JOIN                        |                     | 11558 |
|  12 |       TABLE ACCESS FULL               | TS_C2D297E5_E       | 11558 |
|  13 |    TABLE ACCESS BY INDEX ROWID BATCHED| TS_C2D297E5_E       |    11 |
|  14 |     INDEX RANGE SCAN                  | TS_C2D297E5_E_OWNER |    22 |
-----------------------------------------------------------------------------
```

**ordinary / literal / entries**

```
 
---------------------------------------------------
| Id  | Operation         | Name          | Rows  |
---------------------------------------------------
|   0 | SELECT STATEMENT  |               | 11887 |
|   1 |  TABLE ACCESS FULL| TS_C2D297E5_E | 11887 |
---------------------------------------------------
```

**ordinary / disjoint / entries**

```
 
-------------------------------------------------------------------------------
| Id  | Operation                               | Name                | Rows  |
-------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                        |                     |   251K|
|   1 |  UNION-ALL                              |                     |   251K|
|   2 |   TABLE ACCESS FULL                     | TS_C2D297E5_E       | 11558 |
|   3 |   HASH JOIN                             |                     |  4088 |
|   4 |    JSONTABLE EVALUATION                 |                     |       |
|   5 |    TABLE ACCESS FULL                    | TS_C2D297E5_E       | 11558 |
|   6 |   MERGE JOIN                            |                     |   236K|
|   7 |    SORT JOIN                            |                     |  8168 |
|   8 |     JSONTABLE EVALUATION                |                     |       |
|   9 |    FILTER                               |                     |       |
|  10 |     SORT JOIN                           |                     | 11558 |
|  11 |      TABLE ACCESS FULL                  | TS_C2D297E5_E       | 11558 |
|  12 |   HASH JOIN ANTI                        |                     |    11 |
|  13 |    MERGE JOIN ANTI                      |                     |    11 |
|  14 |     SORT JOIN                           |                     |    11 |
|  15 |      TABLE ACCESS BY INDEX ROWID BATCHED| TS_C2D297E5_E       |    11 |
|  16 |       INDEX RANGE SCAN                  | TS_C2D297E5_E_OWNER |    22 |
|  17 |     FILTER                              |                     |       |
|  18 |      SORT JOIN                          |                     |  8168 |
|  19 |       JSONTABLE EVALUATION              |                     |       |
|  20 |    JSONTABLE EVALUATION                 |                     |       |
-------------------------------------------------------------------------------
```

**ordinary / union / scoped**

```
 
--------------------------------------------------------------------------------
| Id  | Operation                                | Name                | Rows  |
--------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                         |                     |   630 |
|   1 |  HASH UNIQUE                             |                     |   630 |
|   2 |   UNION-ALL                              |                     |   630 |
|   3 |    FILTER                                |                     |       |
|   4 |     TABLE ACCESS BY INDEX ROWID BATCHED  | TS_C2D297E5_E       |    29 |
|   5 |      INDEX RANGE SCAN                    | TS_C2D297E5_E_PATH  |   104 |
|   6 |    FILTER                                |                     |       |
|   7 |     HASH JOIN                            |                     |    10 |
|   8 |      TABLE ACCESS BY INDEX ROWID BATCHED | TS_C2D297E5_E       |    29 |
|   9 |       INDEX RANGE SCAN                   | TS_C2D297E5_E_PATH  |   104 |
|  10 |      JSONTABLE EVALUATION                |                     |       |
|  11 |    FILTER                                |                     |       |
|  12 |     MERGE JOIN                           |                     |   590 |
|  13 |      SORT JOIN                           |                     |    29 |
|  14 |       TABLE ACCESS BY INDEX ROWID BATCHED| TS_C2D297E5_E       |    29 |
|  15 |        INDEX RANGE SCAN                  | TS_C2D297E5_E_PATH  |   104 |
|  16 |      FILTER                              |                     |       |
|  17 |       SORT JOIN                          |                     |  8168 |
|  18 |        JSONTABLE EVALUATION              |                     |       |
|  19 |    FILTER                                |                     |       |
|  20 |     TABLE ACCESS BY INDEX ROWID BATCHED  | TS_C2D297E5_E       |     1 |
|  21 |      INDEX RANGE SCAN                    | TS_C2D297E5_E_OWNER |    22 |
--------------------------------------------------------------------------------
```

**ordinary / unionall / scoped**

```
 
--------------------------------------------------------------------------------
| Id  | Operation                                | Name                | Rows  |
--------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                         |                     |   630 |
|   1 |  HASH UNIQUE                             |                     |   630 |
|   2 |   UNION-ALL                              |                     |   630 |
|   3 |    FILTER                                |                     |       |
|   4 |     TABLE ACCESS BY INDEX ROWID BATCHED  | TS_C2D297E5_E       |    29 |
|   5 |      INDEX RANGE SCAN                    | TS_C2D297E5_E_PATH  |   104 |
|   6 |    FILTER                                |                     |       |
|   7 |     HASH JOIN                            |                     |    10 |
|   8 |      TABLE ACCESS BY INDEX ROWID BATCHED | TS_C2D297E5_E       |    29 |
|   9 |       INDEX RANGE SCAN                   | TS_C2D297E5_E_PATH  |   104 |
|  10 |      JSONTABLE EVALUATION                |                     |       |
|  11 |    FILTER                                |                     |       |
|  12 |     MERGE JOIN                           |                     |   590 |
|  13 |      SORT JOIN                           |                     |    29 |
|  14 |       TABLE ACCESS BY INDEX ROWID BATCHED| TS_C2D297E5_E       |    29 |
|  15 |        INDEX RANGE SCAN                  | TS_C2D297E5_E_PATH  |   104 |
|  16 |      FILTER                              |                     |       |
|  17 |       SORT JOIN                          |                     |  8168 |
|  18 |        JSONTABLE EVALUATION              |                     |       |
|  19 |    FILTER                                |                     |       |
|  20 |     TABLE ACCESS BY INDEX ROWID BATCHED  | TS_C2D297E5_E       |     1 |
|  21 |      INDEX RANGE SCAN                    | TS_C2D297E5_E_OWNER |    22 |
--------------------------------------------------------------------------------
```

**ordinary / literal / scoped**

```
 
---------------------------------------------------------------------------
| Id  | Operation                            | Name               | Rows  |
---------------------------------------------------------------------------
|   0 | SELECT STATEMENT                     |                    |    30 |
|   1 |  FILTER                              |                    |       |
|   2 |   TABLE ACCESS BY INDEX ROWID BATCHED| TS_C2D297E5_E      |    30 |
|   3 |    INDEX RANGE SCAN                  | TS_C2D297E5_E_PATH |   104 |
---------------------------------------------------------------------------
```

**ordinary / disjoint / scoped**

```
 
-------------------------------------------------------------------------------
| Id  | Operation                               | Name                | Rows  |
-------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                        |                     |   630 |
|   1 |  UNION-ALL                              |                     |   630 |
|   2 |   FILTER                                |                     |       |
|   3 |    TABLE ACCESS BY INDEX ROWID BATCHED  | TS_C2D297E5_E       |    29 |
|   4 |     INDEX RANGE SCAN                    | TS_C2D297E5_E_PATH  |   104 |
|   5 |   FILTER                                |                     |       |
|   6 |    HASH JOIN                            |                     |    10 |
|   7 |     TABLE ACCESS BY INDEX ROWID BATCHED | TS_C2D297E5_E       |    29 |
|   8 |      INDEX RANGE SCAN                   | TS_C2D297E5_E_PATH  |   104 |
|   9 |     JSONTABLE EVALUATION                |                     |       |
|  10 |   FILTER                                |                     |       |
|  11 |    MERGE JOIN                           |                     |   590 |
|  12 |     SORT JOIN                           |                     |    29 |
|  13 |      TABLE ACCESS BY INDEX ROWID BATCHED| TS_C2D297E5_E       |    29 |
|  14 |       INDEX RANGE SCAN                  | TS_C2D297E5_E_PATH  |   104 |
|  15 |     FILTER                              |                     |       |
|  16 |      SORT JOIN                          |                     |  8168 |
|  17 |       JSONTABLE EVALUATION              |                     |       |
|  18 |   FILTER                                |                     |       |
|  19 |    HASH JOIN ANTI                       |                     |     1 |
|  20 |     NESTED LOOPS ANTI                   |                     |     1 |
|  21 |      TABLE ACCESS BY INDEX ROWID BATCHED| TS_C2D297E5_E       |     1 |
|  22 |       INDEX RANGE SCAN                  | TS_C2D297E5_E_OWNER |    22 |
|  23 |      JSONTABLE EVALUATION               |                     |       |
|  24 |     JSONTABLE EVALUATION                |                     |       |
-------------------------------------------------------------------------------
```

**ordinary / union / count**

```
 
--------------------------------------------------------------------------------
| Id  | Operation                                | Name                | Rows  |
--------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                         |                     |     1 |
|   1 |  SORT AGGREGATE                          |                     |     1 |
|   2 |   HASH JOIN                              |                     |   751K|
|   3 |    INDEX FAST FULL SCAN                  | TS_C2D297E5_C_ENTRY | 66000 |
|   4 |    VIEW                                  |                     |   251K|
|   5 |     HASH UNIQUE                          |                     |   251K|
|   6 |      UNION-ALL                           |                     |   251K|
|   7 |       TABLE ACCESS FULL                  | TS_C2D297E5_E       | 11558 |
|   8 |       HASH JOIN                          |                     |  4088 |
|   9 |        JSONTABLE EVALUATION              |                     |       |
|  10 |        TABLE ACCESS FULL                 | TS_C2D297E5_E       | 11558 |
|  11 |       MERGE JOIN                         |                     |   236K|
|  12 |        SORT JOIN                         |                     |  8168 |
|  13 |         JSONTABLE EVALUATION             |                     |       |
|  14 |        FILTER                            |                     |       |
|  15 |         SORT JOIN                        |                     | 11558 |
|  16 |          TABLE ACCESS FULL               | TS_C2D297E5_E       | 11558 |
|  17 |       TABLE ACCESS BY INDEX ROWID BATCHED| TS_C2D297E5_E       |    11 |
|  18 |        INDEX RANGE SCAN                  | TS_C2D297E5_E_OWNER |    22 |
--------------------------------------------------------------------------------
```

**ordinary / unionall / count**

```
 
--------------------------------------------------------------------------------
| Id  | Operation                                | Name                | Rows  |
--------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                         |                     |     1 |
|   1 |  SORT AGGREGATE                          |                     |     1 |
|   2 |   HASH JOIN                              |                     |   751K|
|   3 |    INDEX FAST FULL SCAN                  | TS_C2D297E5_C_ENTRY | 66000 |
|   4 |    VIEW                                  |                     |   251K|
|   5 |     HASH UNIQUE                          |                     |   251K|
|   6 |      UNION-ALL                           |                     |   251K|
|   7 |       TABLE ACCESS FULL                  | TS_C2D297E5_E       | 11558 |
|   8 |       HASH JOIN                          |                     |  4088 |
|   9 |        JSONTABLE EVALUATION              |                     |       |
|  10 |        TABLE ACCESS FULL                 | TS_C2D297E5_E       | 11558 |
|  11 |       MERGE JOIN                         |                     |   236K|
|  12 |        SORT JOIN                         |                     |  8168 |
|  13 |         JSONTABLE EVALUATION             |                     |       |
|  14 |        FILTER                            |                     |       |
|  15 |         SORT JOIN                        |                     | 11558 |
|  16 |          TABLE ACCESS FULL               | TS_C2D297E5_E       | 11558 |
|  17 |       TABLE ACCESS BY INDEX ROWID BATCHED| TS_C2D297E5_E       |    11 |
|  18 |        INDEX RANGE SCAN                  | TS_C2D297E5_E_OWNER |    22 |
--------------------------------------------------------------------------------
```

**ordinary / literal / count**

```
 
--------------------------------------------------------------
| Id  | Operation              | Name                | Rows  |
--------------------------------------------------------------
|   0 | SELECT STATEMENT       |                     |     1 |
|   1 |  SORT AGGREGATE        |                     |     1 |
|   2 |   HASH JOIN            |                     | 35501 |
|   3 |    TABLE ACCESS FULL   | TS_C2D297E5_E       | 11887 |
|   4 |    INDEX FAST FULL SCAN| TS_C2D297E5_C_ENTRY | 66000 |
--------------------------------------------------------------
```

**ordinary / disjoint / count**

```
 
-------------------------------------------------------------------------
| Id  | Operation                         | Name                | Rows  |
-------------------------------------------------------------------------
|   0 | SELECT STATEMENT                  |                     |     1 |
|   1 |  SORT AGGREGATE                   |                     |     1 |
|   2 |   NESTED LOOPS                    |                     |   718K|
|   3 |    INDEX FAST FULL SCAN           | TS_C2D297E5_C_ENTRY | 66000 |
|   4 |    VIEW                           |                     |    11 |
|   5 |     UNION-ALL PARTITION           |                     |       |
|   6 |      TABLE ACCESS BY INDEX ROWID  | TS_C2D297E5_E       |     1 |
|   7 |       INDEX UNIQUE SCAN           | SYS_C00120042       |     1 |
|   8 |      HASH JOIN                    |                     |     1 |
|   9 |       TABLE ACCESS BY INDEX ROWID | TS_C2D297E5_E       |     1 |
|  10 |        INDEX UNIQUE SCAN          | SYS_C00120042       |     1 |
|  11 |       JSONTABLE EVALUATION        |                     |       |
|  12 |      NESTED LOOPS                 |                     |    20 |
|  13 |       TABLE ACCESS BY INDEX ROWID | TS_C2D297E5_E       |     1 |
|  14 |        INDEX UNIQUE SCAN          | SYS_C00120042       |     1 |
|  15 |       JSONTABLE EVALUATION        |                     |       |
|  16 |      HASH JOIN ANTI               |                     |     1 |
|  17 |       NESTED LOOPS ANTI           |                     |     1 |
|  18 |        TABLE ACCESS BY INDEX ROWID| TS_C2D297E5_E       |     1 |
|  19 |         INDEX UNIQUE SCAN         | SYS_C00120042       |     1 |
|  20 |        JSONTABLE EVALUATION       |                     |       |
|  21 |       JSONTABLE EVALUATION        |                     |       |
-------------------------------------------------------------------------
```

**ordinary / union / top10**

```
 
-------------------------------------------------------------------------
| Id  | Operation                         | Name                | Rows  |
-------------------------------------------------------------------------
|   0 | SELECT STATEMENT                  |                     |    10 |
|   1 |  COUNT STOPKEY                    |                     |       |
|   2 |   VIEW                            |                     |    10 |
|   3 |    NESTED LOOPS                   |                     |    10 |
|   4 |     TABLE ACCESS BY INDEX ROWID   | TS_C2D297E5_C       | 66000 |
|   5 |      INDEX FULL SCAN              | TS_C2D297E5_C_SCORE |     1 |
|   6 |     VIEW                          |                     |    10 |
|   7 |      SORT UNIQUE                  |                     |   251K|
|   8 |       UNION-ALL                   |                     |   251K|
|   9 |        TABLE ACCESS FULL          | TS_C2D297E5_E       | 11558 |
|  10 |        HASH JOIN                  |                     |  4088 |
|  11 |         JSONTABLE EVALUATION      |                     |       |
|  12 |         TABLE ACCESS FULL         | TS_C2D297E5_E       | 11558 |
|  13 |        MERGE JOIN                 |                     |   236K|
|  14 |         SORT JOIN                 |                     |  8168 |
|  15 |          JSONTABLE EVALUATION     |                     |       |
|  16 |         FILTER                    |                     |       |
|  17 |          SORT JOIN                |                     | 11558 |
|  18 |           TABLE ACCESS FULL       | TS_C2D297E5_E       | 11558 |
|  19 |        TABLE ACCESS BY INDEX ROWID| TS_C2D297E5_E       |    11 |
|  20 |         INDEX RANGE SCAN          | TS_C2D297E5_E_OWNER |    22 |
-------------------------------------------------------------------------
```

**ordinary / unionall / top10**

```
 
-------------------------------------------------------------------------
| Id  | Operation                         | Name                | Rows  |
-------------------------------------------------------------------------
|   0 | SELECT STATEMENT                  |                     |    10 |
|   1 |  COUNT STOPKEY                    |                     |       |
|   2 |   VIEW                            |                     |    10 |
|   3 |    NESTED LOOPS                   |                     |    10 |
|   4 |     TABLE ACCESS BY INDEX ROWID   | TS_C2D297E5_C       | 66000 |
|   5 |      INDEX FULL SCAN              | TS_C2D297E5_C_SCORE |     1 |
|   6 |     VIEW                          |                     |    10 |
|   7 |      SORT UNIQUE                  |                     |   251K|
|   8 |       UNION-ALL                   |                     |   251K|
|   9 |        TABLE ACCESS FULL          | TS_C2D297E5_E       | 11558 |
|  10 |        HASH JOIN                  |                     |  4088 |
|  11 |         JSONTABLE EVALUATION      |                     |       |
|  12 |         TABLE ACCESS FULL         | TS_C2D297E5_E       | 11558 |
|  13 |        MERGE JOIN                 |                     |   236K|
|  14 |         SORT JOIN                 |                     |  8168 |
|  15 |          JSONTABLE EVALUATION     |                     |       |
|  16 |         FILTER                    |                     |       |
|  17 |          SORT JOIN                |                     | 11558 |
|  18 |           TABLE ACCESS FULL       | TS_C2D297E5_E       | 11558 |
|  19 |        TABLE ACCESS BY INDEX ROWID| TS_C2D297E5_E       |    11 |
|  20 |         INDEX RANGE SCAN          | TS_C2D297E5_E_OWNER |    22 |
-------------------------------------------------------------------------
```

**ordinary / literal / top10**

```
 
-----------------------------------------------------------------------
| Id  | Operation                       | Name                | Rows  |
-----------------------------------------------------------------------
|   0 | SELECT STATEMENT                |                     |    10 |
|   1 |  COUNT STOPKEY                  |                     |       |
|   2 |   VIEW                          |                     |    10 |
|   3 |    NESTED LOOPS                 |                     |    10 |
|   4 |     NESTED LOOPS                |                     |    20 |
|   5 |      TABLE ACCESS BY INDEX ROWID| TS_C2D297E5_C       | 66000 |
|   6 |       INDEX FULL SCAN           | TS_C2D297E5_C_SCORE |    20 |
|   7 |      INDEX UNIQUE SCAN          | SYS_C00120042       |     1 |
|   8 |     TABLE ACCESS BY INDEX ROWID | TS_C2D297E5_E       |     1 |
-----------------------------------------------------------------------
```

**ordinary / disjoint / top10**

```
 
--------------------------------------------------------------------------
| Id  | Operation                          | Name                | Rows  |
--------------------------------------------------------------------------
|   0 | SELECT STATEMENT                   |                     |    10 |
|   1 |  COUNT STOPKEY                     |                     |       |
|   2 |   VIEW                             |                     |    10 |
|   3 |    NESTED LOOPS                    |                     |    10 |
|   4 |     TABLE ACCESS BY INDEX ROWID    | TS_C2D297E5_C       | 66000 |
|   5 |      INDEX FULL SCAN               | TS_C2D297E5_C_SCORE |     2 |
|   6 |     VIEW                           |                     |     6 |
|   7 |      UNION-ALL PARTITION           |                     |       |
|   8 |       TABLE ACCESS BY INDEX ROWID  | TS_C2D297E5_E       |     1 |
|   9 |        INDEX UNIQUE SCAN           | SYS_C00120042       |     1 |
|  10 |       HASH JOIN                    |                     |     1 |
|  11 |        TABLE ACCESS BY INDEX ROWID | TS_C2D297E5_E       |     1 |
|  12 |         INDEX UNIQUE SCAN          | SYS_C00120042       |     1 |
|  13 |        JSONTABLE EVALUATION        |                     |       |
|  14 |       NESTED LOOPS                 |                     |    20 |
|  15 |        TABLE ACCESS BY INDEX ROWID | TS_C2D297E5_E       |     1 |
|  16 |         INDEX UNIQUE SCAN          | SYS_C00120042       |     1 |
|  17 |        JSONTABLE EVALUATION        |                     |       |
|  18 |       HASH JOIN ANTI               |                     |     1 |
|  19 |        NESTED LOOPS ANTI           |                     |     1 |
|  20 |         TABLE ACCESS BY INDEX ROWID| TS_C2D297E5_E       |     1 |
|  21 |          INDEX UNIQUE SCAN         | SYS_C00120042       |     1 |
|  22 |         JSONTABLE EVALUATION       |                     |       |
|  23 |        JSONTABLE EVALUATION        |                     |       |
--------------------------------------------------------------------------
```

**two subjects / union / entries**

```
 
-------------------------------------------------------------------------------
| Id  | Operation                               | Name                | Rows  |
-------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                        |                     |   252K|
|   1 |  HASH UNIQUE                            |                     |   252K|
|   2 |   UNION-ALL                             |                     |   252K|
|   3 |    TABLE ACCESS FULL                    | TS_C2D297E5_E       | 11558 |
|   4 |    HASH JOIN                            |                     |  4088 |
|   5 |     JSONTABLE EVALUATION                |                     |       |
|   6 |     TABLE ACCESS FULL                   | TS_C2D297E5_E       | 11558 |
|   7 |    MERGE JOIN                           |                     |   236K|
|   8 |     SORT JOIN                           |                     |  8168 |
|   9 |      JSONTABLE EVALUATION               |                     |       |
|  10 |     FILTER                              |                     |       |
|  11 |      SORT JOIN                          |                     | 11558 |
|  12 |       TABLE ACCESS FULL                 | TS_C2D297E5_E       | 11558 |
|  13 |    HASH JOIN                            |                     |     4 |
|  14 |     TABLE ACCESS BY INDEX ROWID BATCHED | TS_C2D297E5_E       |    11 |
|  15 |      INDEX RANGE SCAN                   | TS_C2D297E5_E_OWNER |    22 |
|  16 |     JSONTABLE EVALUATION                |                     |       |
|  17 |    MERGE JOIN                           |                     |   225 |
|  18 |     SORT JOIN                           |                     |    11 |
|  19 |      TABLE ACCESS BY INDEX ROWID BATCHED| TS_C2D297E5_E       |    11 |
|  20 |       INDEX RANGE SCAN                  | TS_C2D297E5_E_OWNER |    22 |
|  21 |     FILTER                              |                     |       |
|  22 |      SORT JOIN                          |                     |  8168 |
|  23 |       JSONTABLE EVALUATION              |                     |       |
|  24 |    HASH JOIN                            |                     |     4 |
|  25 |     TABLE ACCESS BY INDEX ROWID BATCHED | TS_C2D297E5_E       |    11 |
|  26 |      INDEX RANGE SCAN                   | TS_C2D297E5_E_OWNER |    22 |
|  27 |     JSONTABLE EVALUATION                |                     |       |
|  28 |    MERGE JOIN                           |                     |   225 |
|  29 |     SORT JOIN                           |                     |    11 |
|  30 |      TABLE ACCESS BY INDEX ROWID BATCHED| TS_C2D297E5_E       |    11 |
|  31 |       INDEX RANGE SCAN                  | TS_C2D297E5_E_OWNER |    22 |
|  32 |     FILTER                              |                     |       |
|  33 |      SORT JOIN                          |                     |  8168 |
|  34 |       JSONTABLE EVALUATION              |                     |       |
-------------------------------------------------------------------------------
```

**two subjects / unionall / entries**

```
 
-------------------------------------------------------------------------------
| Id  | Operation                               | Name                | Rows  |
-------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                        |                     |   252K|
|   1 |  HASH UNIQUE                            |                     |   252K|
|   2 |   UNION-ALL                             |                     |   252K|
|   3 |    TABLE ACCESS FULL                    | TS_C2D297E5_E       | 11558 |
|   4 |    HASH JOIN                            |                     |  4088 |
|   5 |     JSONTABLE EVALUATION                |                     |       |
|   6 |     TABLE ACCESS FULL                   | TS_C2D297E5_E       | 11558 |
|   7 |    MERGE JOIN                           |                     |   236K|
|   8 |     SORT JOIN                           |                     |  8168 |
|   9 |      JSONTABLE EVALUATION               |                     |       |
|  10 |     FILTER                              |                     |       |
|  11 |      SORT JOIN                          |                     | 11558 |
|  12 |       TABLE ACCESS FULL                 | TS_C2D297E5_E       | 11558 |
|  13 |    HASH JOIN                            |                     |     4 |
|  14 |     TABLE ACCESS BY INDEX ROWID BATCHED | TS_C2D297E5_E       |    11 |
|  15 |      INDEX RANGE SCAN                   | TS_C2D297E5_E_OWNER |    22 |
|  16 |     JSONTABLE EVALUATION                |                     |       |
|  17 |    MERGE JOIN                           |                     |   225 |
|  18 |     SORT JOIN                           |                     |    11 |
|  19 |      TABLE ACCESS BY INDEX ROWID BATCHED| TS_C2D297E5_E       |    11 |
|  20 |       INDEX RANGE SCAN                  | TS_C2D297E5_E_OWNER |    22 |
|  21 |     FILTER                              |                     |       |
|  22 |      SORT JOIN                          |                     |  8168 |
|  23 |       JSONTABLE EVALUATION              |                     |       |
|  24 |    HASH JOIN                            |                     |     4 |
|  25 |     TABLE ACCESS BY INDEX ROWID BATCHED | TS_C2D297E5_E       |    11 |
|  26 |      INDEX RANGE SCAN                   | TS_C2D297E5_E_OWNER |    22 |
|  27 |     JSONTABLE EVALUATION                |                     |       |
|  28 |    MERGE JOIN                           |                     |   225 |
|  29 |     SORT JOIN                           |                     |    11 |
|  30 |      TABLE ACCESS BY INDEX ROWID BATCHED| TS_C2D297E5_E       |    11 |
|  31 |       INDEX RANGE SCAN                  | TS_C2D297E5_E_OWNER |    22 |
|  32 |     FILTER                              |                     |       |
|  33 |      SORT JOIN                          |                     |  8168 |
|  34 |       JSONTABLE EVALUATION              |                     |       |
-------------------------------------------------------------------------------
```

**two subjects / literal / entries**

```
 
---------------------------------------------------
| Id  | Operation         | Name          | Rows  |
---------------------------------------------------
|   0 | SELECT STATEMENT  |               | 11849 |
|   1 |  TABLE ACCESS FULL| TS_C2D297E5_E | 11849 |
---------------------------------------------------
```

**two subjects / disjoint / entries**

```
 
--------------------------------------------------------------------------------
| Id  | Operation                                | Name                | Rows  |
--------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                         |                     |   252K|
|   1 |  UNION-ALL                               |                     |   252K|
|   2 |   TABLE ACCESS FULL                      | TS_C2D297E5_E       | 11558 |
|   3 |   HASH JOIN                              |                     |  4088 |
|   4 |    JSONTABLE EVALUATION                  |                     |       |
|   5 |    TABLE ACCESS FULL                     | TS_C2D297E5_E       | 11558 |
|   6 |   MERGE JOIN                             |                     |   236K|
|   7 |    SORT JOIN                             |                     |  8168 |
|   8 |     JSONTABLE EVALUATION                 |                     |       |
|   9 |    FILTER                                |                     |       |
|  10 |     SORT JOIN                            |                     | 11558 |
|  11 |      TABLE ACCESS FULL                   | TS_C2D297E5_E       | 11558 |
|  12 |   MERGE JOIN ANTI                        |                     |     4 |
|  13 |    SORT JOIN                             |                     |     4 |
|  14 |     HASH JOIN ANTI                       |                     |     4 |
|  15 |      HASH JOIN                           |                     |     4 |
|  16 |       TABLE ACCESS BY INDEX ROWID BATCHED| TS_C2D297E5_E       |    11 |
|  17 |        INDEX RANGE SCAN                  | TS_C2D297E5_E_OWNER |    22 |
|  18 |       JSONTABLE EVALUATION               |                     |       |
|  19 |      JSONTABLE EVALUATION                |                     |       |
|  20 |    FILTER                                |                     |       |
|  21 |     SORT JOIN                            |                     |  8168 |
|  22 |      JSONTABLE EVALUATION                |                     |       |
|  23 |   MERGE JOIN                             |                     |   224 |
|  24 |    MERGE JOIN ANTI                       |                     |    11 |
|  25 |     SORT JOIN                            |                     |    11 |
|  26 |      HASH JOIN ANTI                      |                     |    11 |
|  27 |       TABLE ACCESS BY INDEX ROWID BATCHED| TS_C2D297E5_E       |    11 |
|  28 |        INDEX RANGE SCAN                  | TS_C2D297E5_E_OWNER |    22 |
|  29 |       JSONTABLE EVALUATION               |                     |       |
|  30 |     FILTER                               |                     |       |
|  31 |      SORT JOIN                           |                     |  8168 |
|  32 |       JSONTABLE EVALUATION               |                     |       |
|  33 |    FILTER                                |                     |       |
|  34 |     SORT JOIN                            |                     |  8168 |
|  35 |      JSONTABLE EVALUATION                |                     |       |
|  36 |   MERGE JOIN ANTI                        |                     |     4 |
|  37 |    SORT JOIN                             |                     |     4 |
|  38 |     HASH JOIN ANTI                       |                     |     4 |
|  39 |      HASH JOIN                           |                     |     4 |
|  40 |       TABLE ACCESS BY INDEX ROWID BATCHED| TS_C2D297E5_E       |    11 |
|  41 |        INDEX RANGE SCAN                  | TS_C2D297E5_E_OWNER |    22 |
|  42 |       JSONTABLE EVALUATION               |                     |       |
|  43 |      JSONTABLE EVALUATION                |                     |       |
|  44 |    FILTER                                |                     |       |
|  45 |     SORT JOIN                            |                     |  8168 |
|  46 |      JSONTABLE EVALUATION                |                     |       |
|  47 |   MERGE JOIN                             |                     |   224 |
|  48 |    MERGE JOIN ANTI                       |                     |    11 |
|  49 |     SORT JOIN                            |                     |    11 |
|  50 |      HASH JOIN ANTI                      |                     |    11 |
|  51 |       TABLE ACCESS BY INDEX ROWID BATCHED| TS_C2D297E5_E       |    11 |
|  52 |        INDEX RANGE SCAN                  | TS_C2D297E5_E_OWNER |    22 |
|  53 |       JSONTABLE EVALUATION               |                     |       |
|  54 |     FILTER                               |                     |       |
|  55 |      SORT JOIN                           |                     |  8168 |
|  56 |       JSONTABLE EVALUATION               |                     |       |
|  57 |    FILTER                                |                     |       |
|  58 |     SORT JOIN                            |                     |  8168 |
|  59 |      JSONTABLE EVALUATION                |                     |       |
--------------------------------------------------------------------------------
```

**scoped / anonymous / union / IN**

```
 
-------------------------------------------------------------------------------
| Id  | Operation                             | Name                  | Rows  |
-------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                      |                       |    58 |
|   1 |  FILTER                               |                       |       |
|   2 |   INLIST ITERATOR                     |                       |       |
|   3 |    TABLE ACCESS BY INDEX ROWID BATCHED| TS_C2D297E5_E         |    58 |
|   4 |     INDEX RANGE SCAN                  | TS_C2D297E5_E_LVLPATH |   104 |
-------------------------------------------------------------------------------
```

**scoped / anonymous / union / >=**

```
 
---------------------------------------------------------------------------
| Id  | Operation                            | Name               | Rows  |
---------------------------------------------------------------------------
|   0 | SELECT STATEMENT                     |                    |    29 |
|   1 |  FILTER                              |                    |       |
|   2 |   TABLE ACCESS BY INDEX ROWID BATCHED| TS_C2D297E5_E      |    29 |
|   3 |    INDEX RANGE SCAN                  | TS_C2D297E5_E_PATH |   104 |
---------------------------------------------------------------------------
```

**scoped / ordinary / union / IN**

```
 
----------------------------------------------------------------------------------
| Id  | Operation                                | Name                  | Rows  |
----------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                         |                       |   659 |
|   1 |  HASH UNIQUE                             |                       |   659 |
|   2 |   UNION-ALL                              |                       |   659 |
|   3 |    FILTER                                |                       |       |
|   4 |     INLIST ITERATOR                      |                       |       |
|   5 |      TABLE ACCESS BY INDEX ROWID BATCHED | TS_C2D297E5_E         |    58 |
|   6 |       INDEX RANGE SCAN                   | TS_C2D297E5_E_LVLPATH |   104 |
|   7 |    FILTER                                |                       |       |
|   8 |     HASH JOIN                            |                       |    10 |
|   9 |      TABLE ACCESS BY INDEX ROWID BATCHED | TS_C2D297E5_E         |    29 |
|  10 |       INDEX RANGE SCAN                   | TS_C2D297E5_E_PATH    |   104 |
|  11 |      JSONTABLE EVALUATION                |                       |       |
|  12 |    FILTER                                |                       |       |
|  13 |     MERGE JOIN                           |                       |   590 |
|  14 |      SORT JOIN                           |                       |    29 |
|  15 |       TABLE ACCESS BY INDEX ROWID BATCHED| TS_C2D297E5_E         |    29 |
|  16 |        INDEX RANGE SCAN                  | TS_C2D297E5_E_PATH    |   104 |
|  17 |      FILTER                              |                       |       |
|  18 |       SORT JOIN                          |                       |  8168 |
|  19 |        JSONTABLE EVALUATION              |                       |       |
|  20 |    FILTER                                |                       |       |
|  21 |     TABLE ACCESS BY INDEX ROWID BATCHED  | TS_C2D297E5_E         |     1 |
|  22 |      INDEX RANGE SCAN                    | TS_C2D297E5_E_OWNER   |    22 |
----------------------------------------------------------------------------------
```

**scoped / ordinary / unionall / IN**

```
 
----------------------------------------------------------------------------------
| Id  | Operation                                | Name                  | Rows  |
----------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                         |                       |   659 |
|   1 |  HASH UNIQUE                             |                       |   659 |
|   2 |   UNION-ALL                              |                       |   659 |
|   3 |    FILTER                                |                       |       |
|   4 |     INLIST ITERATOR                      |                       |       |
|   5 |      TABLE ACCESS BY INDEX ROWID BATCHED | TS_C2D297E5_E         |    58 |
|   6 |       INDEX RANGE SCAN                   | TS_C2D297E5_E_LVLPATH |   104 |
|   7 |    FILTER                                |                       |       |
|   8 |     HASH JOIN                            |                       |    10 |
|   9 |      TABLE ACCESS BY INDEX ROWID BATCHED | TS_C2D297E5_E         |    29 |
|  10 |       INDEX RANGE SCAN                   | TS_C2D297E5_E_PATH    |   104 |
|  11 |      JSONTABLE EVALUATION                |                       |       |
|  12 |    FILTER                                |                       |       |
|  13 |     MERGE JOIN                           |                       |   590 |
|  14 |      SORT JOIN                           |                       |    29 |
|  15 |       TABLE ACCESS BY INDEX ROWID BATCHED| TS_C2D297E5_E         |    29 |
|  16 |        INDEX RANGE SCAN                  | TS_C2D297E5_E_PATH    |   104 |
|  17 |      FILTER                              |                       |       |
|  18 |       SORT JOIN                          |                       |  8168 |
|  19 |        JSONTABLE EVALUATION              |                       |       |
|  20 |    FILTER                                |                       |       |
|  21 |     TABLE ACCESS BY INDEX ROWID BATCHED  | TS_C2D297E5_E         |     1 |
|  22 |      INDEX RANGE SCAN                    | TS_C2D297E5_E_OWNER   |    22 |
----------------------------------------------------------------------------------
```

**scoped / ordinary / literal / IN**

```
 
---------------------------------------------------------------------------
| Id  | Operation                            | Name               | Rows  |
---------------------------------------------------------------------------
|   0 | SELECT STATEMENT                     |                    |    30 |
|   1 |  FILTER                              |                    |       |
|   2 |   TABLE ACCESS BY INDEX ROWID BATCHED| TS_C2D297E5_E      |    30 |
|   3 |    INDEX RANGE SCAN                  | TS_C2D297E5_E_PATH |   104 |
---------------------------------------------------------------------------
```

**scoped / ordinary / disjoint / IN**

```
 
---------------------------------------------------------------------------------
| Id  | Operation                               | Name                  | Rows  |
---------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                        |                       |   659 |
|   1 |  UNION-ALL                              |                       |   659 |
|   2 |   FILTER                                |                       |       |
|   3 |    INLIST ITERATOR                      |                       |       |
|   4 |     TABLE ACCESS BY INDEX ROWID BATCHED | TS_C2D297E5_E         |    58 |
|   5 |      INDEX RANGE SCAN                   | TS_C2D297E5_E_LVLPATH |   104 |
|   6 |   FILTER                                |                       |       |
|   7 |    HASH JOIN                            |                       |    10 |
|   8 |     TABLE ACCESS BY INDEX ROWID BATCHED | TS_C2D297E5_E         |    29 |
|   9 |      INDEX RANGE SCAN                   | TS_C2D297E5_E_PATH    |   104 |
|  10 |     JSONTABLE EVALUATION                |                       |       |
|  11 |   FILTER                                |                       |       |
|  12 |    MERGE JOIN                           |                       |   590 |
|  13 |     SORT JOIN                           |                       |    29 |
|  14 |      TABLE ACCESS BY INDEX ROWID BATCHED| TS_C2D297E5_E         |    29 |
|  15 |       INDEX RANGE SCAN                  | TS_C2D297E5_E_PATH    |   104 |
|  16 |     FILTER                              |                       |       |
|  17 |      SORT JOIN                          |                       |  8168 |
|  18 |       JSONTABLE EVALUATION              |                       |       |
|  19 |   FILTER                                |                       |       |
|  20 |    HASH JOIN ANTI                       |                       |     1 |
|  21 |     NESTED LOOPS ANTI                   |                       |     1 |
|  22 |      TABLE ACCESS BY INDEX ROWID BATCHED| TS_C2D297E5_E         |     1 |
|  23 |       INDEX RANGE SCAN                  | TS_C2D297E5_E_OWNER   |    22 |
|  24 |      JSONTABLE EVALUATION               |                       |       |
|  25 |     JSONTABLE EVALUATION                |                       |       |
---------------------------------------------------------------------------------
```

Total wall time 37s.
