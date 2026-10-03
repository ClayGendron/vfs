## oracle — N=10,000 users: 230,203 entries, 660,000 chunks (3/file), 11,400 grant rows, 10,101 posture rows, 100 sibling traps

Load (tables, rows, indexes, statistics): 54s.

### Indexes

| index | size |
|---|---|
| `path` | 15.7 MB |
| `owner` | 8.4 MB |
| `lvlpath` | 16.8 MB |
| (entries table) | 11.5 MB |

### Callers

| caller | subjects | pieces (arms + owner) | bind bytes | compile us | visible entries |
|---|---|---|---|---|---|
| ordinary | u000042 | 88 | 2,445 | 247 | 20,124 |
| heavy group | u000003 | 88 | 2,445 | 60 | 20,124 |
| two subjects | u000042, u000032 | 220 | 6,094 | 126 | 20,103 |
| anonymous | — | 0 | 0 | 0 | 20,103 |
| system | — | 0 | 0 | 0 | 230,203 |

### Statements — cold = fresh connection, warm = median of 3 (ms); recall against the Python truth

Shapes: union, unionall, literal, disjoint. A blank cell is a shape that does not apply to that caller.

| caller | statement | union: cold / warm / recall | unionall: cold / warm / recall | literal: cold / warm / recall | disjoint: cold / warm / recall |
|---|---|---|---|---|---|
| ordinary | entries | 377 / 508 / exact | 363 / 342 / exact | 646 / 617 / exact | 418 / 714 / exact |
| ordinary | scoped | 92.4 / 7.1 / exact | 12.0 / 4.6 / exact | 34.4 / 4.0 / exact | 11.3 / 5.5 / exact |
| ordinary | count | 60.6 / 23.9 / exact | 34.3 / 21.4 / exact | 220 / 121 / exact | 30.6 / 17.2 / exact |
| ordinary | top10 | 58.9 / 38.8 / exact | 54.5 / 34.3 / exact | 23.1 / 2.6 / exact | 33.2 / 22.3 / exact |
| heavy group | entries | 493 / 357 / exact | 384 / 406 / exact | 525 / 471 / exact | 2,071 / 404 / exact |
| heavy group | scoped | 6.9 / 9.4 / exact | 6.0 / 8.2 / exact | 8.7 / 3.9 / exact | 18.2 / 13.7 / exact |
| heavy group | count | 36.1 / 26.4 / exact | 21.4 / 20.3 / exact | 161 / 128 / exact | 15.7 / 14.9 / exact |
| heavy group | top10 | 33.0 / 35.5 / exact | 58.7 / 35.9 / exact | 15.1 / 4.9 / exact | 31.0 / 23.8 / exact |
| two subjects | entries | 410 / 484 / exact | 575 / 494 / exact | 592 / 479 / exact | 454 / 517 / exact |
| two subjects | scoped | 27.1 / 9.4 / exact | 18.5 / 6.7 / exact | 26.8 / 11.9 / exact | 22.1 / 6.0 / exact |
| two subjects | count | 37.2 / 22.2 / exact | 35.0 / 19.1 / exact | 136 / 92.7 / exact | 35.0 / 18.3 / exact |
| two subjects | top10 | 66.8 / 33.2 / exact | 58.2 / 36.0 / exact | 40.7 / 8.3 / exact | 70.4 / 29.7 / exact |
| anonymous | entries | 430 / 415 / exact |  |  |  |
| anonymous | scoped | 10.5 / 4.4 / exact |  |  |  |
| anonymous | count | 19.7 / 13.4 / exact |  |  |  |
| anonymous | top10 | 30.6 / 20.8 / exact |  |  |  |
| system | entries | 4,941 / 2,919 / exact |  |  |  |
| system | scoped | 7.8 / 3.6 / exact |  |  |  |
| system | count | 128 / 90.2 / exact |  |  |  |
| system | top10 | 196 / 162 / exact |  |  |  |

### Scoped read, branch 1 spelled `everyone_level >= :r` against `everyone_level IN (...)`

| caller | shape | `>=` cold / warm | `IN` cold / warm | recall |
|---|---|---|---|---|
| anonymous | union | 7.2 / 4.4 | 6.3 / 6.0 | exact |
| ordinary | union | 17.7 / 6.5 | 24.6 / 4.9 | exact |
| ordinary | unionall | 6.4 / 5.3 | 13.3 / 3.3 | exact |
| ordinary | literal | 10.3 / 3.7 | 5.6 / 4.8 | exact |
| ordinary | disjoint | 6.7 / 3.6 | 1,574 / 5.0 | exact |

### Plans

**ordinary / union / entries**

```
 
-------------------------------------------------------------------------------
| Id  | Operation                             | Name                  | Rows  |
-------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                      |                       |   127K|
|   1 |  HASH UNIQUE                          |                       |   127K|
|   2 |   UNION-ALL                           |                       |   127K|
|   3 |    TABLE ACCESS BY INDEX ROWID BATCHED| TS_D2C25D2F_E         |   115K|
|   4 |     INDEX RANGE SCAN                  | TS_D2C25D2F_E_LVLPATH |   115K|
|   5 |    NESTED LOOPS                       |                       |    22 |
|   6 |     NESTED LOOPS                      |                       |    44 |
|   7 |      JSONTABLE EVALUATION             |                       |       |
|   8 |      INDEX UNIQUE SCAN                | TS_D2C25D2F_E_PATH    |     1 |
|   9 |     TABLE ACCESS BY INDEX ROWID       | TS_D2C25D2F_E         |     1 |
|  10 |    NESTED LOOPS                       |                       | 12661 |
|  11 |     NESTED LOOPS                      |                       | 45584 |
|  12 |      JSONTABLE EVALUATION             |                       |       |
|  13 |      INDEX RANGE SCAN                 | TS_D2C25D2F_E_PATH    |  1036 |
|  14 |     TABLE ACCESS BY INDEX ROWID       | TS_D2C25D2F_E         |   288 |
|  15 |    TABLE ACCESS BY INDEX ROWID BATCHED| TS_D2C25D2F_E         |    11 |
|  16 |     INDEX RANGE SCAN                  | TS_D2C25D2F_E_OWNER   |    22 |
-------------------------------------------------------------------------------
```

**ordinary / unionall / entries**

```
 
-------------------------------------------------------------------------------
| Id  | Operation                             | Name                  | Rows  |
-------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                      |                       |   127K|
|   1 |  HASH UNIQUE                          |                       |   127K|
|   2 |   UNION-ALL                           |                       |   127K|
|   3 |    TABLE ACCESS BY INDEX ROWID BATCHED| TS_D2C25D2F_E         |   115K|
|   4 |     INDEX RANGE SCAN                  | TS_D2C25D2F_E_LVLPATH |   115K|
|   5 |    NESTED LOOPS                       |                       |    22 |
|   6 |     NESTED LOOPS                      |                       |    44 |
|   7 |      JSONTABLE EVALUATION             |                       |       |
|   8 |      INDEX UNIQUE SCAN                | TS_D2C25D2F_E_PATH    |     1 |
|   9 |     TABLE ACCESS BY INDEX ROWID       | TS_D2C25D2F_E         |     1 |
|  10 |    NESTED LOOPS                       |                       | 12661 |
|  11 |     NESTED LOOPS                      |                       | 45584 |
|  12 |      JSONTABLE EVALUATION             |                       |       |
|  13 |      INDEX RANGE SCAN                 | TS_D2C25D2F_E_PATH    |  1036 |
|  14 |     TABLE ACCESS BY INDEX ROWID       | TS_D2C25D2F_E         |   288 |
|  15 |    TABLE ACCESS BY INDEX ROWID BATCHED| TS_D2C25D2F_E         |    11 |
|  16 |     INDEX RANGE SCAN                  | TS_D2C25D2F_E_OWNER   |    22 |
-------------------------------------------------------------------------------
```

**ordinary / literal / entries**

```
 
---------------------------------------------------
| Id  | Operation         | Name          | Rows  |
---------------------------------------------------
|   0 | SELECT STATEMENT  |               |   127K|
|   1 |  TABLE ACCESS FULL| TS_D2C25D2F_E |   127K|
---------------------------------------------------
```

**ordinary / disjoint / entries**

```
 
---------------------------------------------------------------------------------
| Id  | Operation                               | Name                  | Rows  |
---------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                        |                       |   127K|
|   1 |  UNION-ALL                              |                       |   127K|
|   2 |   TABLE ACCESS BY INDEX ROWID BATCHED   | TS_D2C25D2F_E         |   115K|
|   3 |    INDEX RANGE SCAN                     | TS_D2C25D2F_E_LVLPATH |   115K|
|   4 |   NESTED LOOPS                          |                       |    22 |
|   5 |    NESTED LOOPS                         |                       |    44 |
|   6 |     JSONTABLE EVALUATION                |                       |       |
|   7 |     INDEX UNIQUE SCAN                   | TS_D2C25D2F_E_PATH    |     1 |
|   8 |    TABLE ACCESS BY INDEX ROWID          | TS_D2C25D2F_E         |     1 |
|   9 |   NESTED LOOPS                          |                       | 12661 |
|  10 |    NESTED LOOPS                         |                       | 45584 |
|  11 |     JSONTABLE EVALUATION                |                       |       |
|  12 |     INDEX RANGE SCAN                    | TS_D2C25D2F_E_PATH    |  1036 |
|  13 |    TABLE ACCESS BY INDEX ROWID          | TS_D2C25D2F_E         |   288 |
|  14 |   MERGE JOIN ANTI                       |                       |    11 |
|  15 |    SORT JOIN                            |                       |    11 |
|  16 |     HASH JOIN ANTI                      |                       |    11 |
|  17 |      TABLE ACCESS BY INDEX ROWID BATCHED| TS_D2C25D2F_E         |    11 |
|  18 |       INDEX RANGE SCAN                  | TS_D2C25D2F_E_OWNER   |    22 |
|  19 |      JSONTABLE EVALUATION               |                       |       |
|  20 |    FILTER                               |                       |       |
|  21 |     SORT JOIN                           |                       |  8168 |
|  22 |      JSONTABLE EVALUATION               |                       |       |
---------------------------------------------------------------------------------
```

**ordinary / union / scoped**

```
 
----------------------------------------------------------------------------------
| Id  | Operation                                | Name                  | Rows  |
----------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                         |                       |   322 |
|   1 |  HASH UNIQUE                             |                       |   322 |
|   2 |   UNION-ALL                              |                       |   322 |
|   3 |    FILTER                                |                       |       |
|   4 |     TABLE ACCESS BY INDEX ROWID BATCHED  | TS_D2C25D2F_E         |   288 |
|   5 |      INDEX RANGE SCAN                    | TS_D2C25D2F_E_LVLPATH |   518 |
|   6 |    FILTER                                |                       |       |
|   7 |     HASH JOIN                            |                       |     1 |
|   8 |      JSONTABLE EVALUATION                |                       |       |
|   9 |      TABLE ACCESS BY INDEX ROWID BATCHED | TS_D2C25D2F_E         |   288 |
|  10 |       INDEX RANGE SCAN                   | TS_D2C25D2F_E_PATH    |  1036 |
|  11 |    FILTER                                |                       |       |
|  12 |     MERGE JOIN                           |                       |    32 |
|  13 |      SORT JOIN                           |                       |   288 |
|  14 |       TABLE ACCESS BY INDEX ROWID BATCHED| TS_D2C25D2F_E         |   288 |
|  15 |        INDEX RANGE SCAN                  | TS_D2C25D2F_E_PATH    |  1036 |
|  16 |      FILTER                              |                       |       |
|  17 |       SORT JOIN                          |                       |    44 |
|  18 |        JSONTABLE EVALUATION              |                       |       |
|  19 |    FILTER                                |                       |       |
|  20 |     TABLE ACCESS BY INDEX ROWID BATCHED  | TS_D2C25D2F_E         |     1 |
|  21 |      INDEX RANGE SCAN                    | TS_D2C25D2F_E_OWNER   |    22 |
----------------------------------------------------------------------------------
```

**ordinary / unionall / scoped**

```
 
----------------------------------------------------------------------------------
| Id  | Operation                                | Name                  | Rows  |
----------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                         |                       |   322 |
|   1 |  HASH UNIQUE                             |                       |   322 |
|   2 |   UNION-ALL                              |                       |   322 |
|   3 |    FILTER                                |                       |       |
|   4 |     TABLE ACCESS BY INDEX ROWID BATCHED  | TS_D2C25D2F_E         |   288 |
|   5 |      INDEX RANGE SCAN                    | TS_D2C25D2F_E_LVLPATH |   518 |
|   6 |    FILTER                                |                       |       |
|   7 |     HASH JOIN                            |                       |     1 |
|   8 |      JSONTABLE EVALUATION                |                       |       |
|   9 |      TABLE ACCESS BY INDEX ROWID BATCHED | TS_D2C25D2F_E         |   288 |
|  10 |       INDEX RANGE SCAN                   | TS_D2C25D2F_E_PATH    |  1036 |
|  11 |    FILTER                                |                       |       |
|  12 |     MERGE JOIN                           |                       |    32 |
|  13 |      SORT JOIN                           |                       |   288 |
|  14 |       TABLE ACCESS BY INDEX ROWID BATCHED| TS_D2C25D2F_E         |   288 |
|  15 |        INDEX RANGE SCAN                  | TS_D2C25D2F_E_PATH    |  1036 |
|  16 |      FILTER                              |                       |       |
|  17 |       SORT JOIN                          |                       |    44 |
|  18 |        JSONTABLE EVALUATION              |                       |       |
|  19 |    FILTER                                |                       |       |
|  20 |     TABLE ACCESS BY INDEX ROWID BATCHED  | TS_D2C25D2F_E         |     1 |
|  21 |      INDEX RANGE SCAN                    | TS_D2C25D2F_E_OWNER   |    22 |
----------------------------------------------------------------------------------
```

**ordinary / literal / scoped**

```
 
---------------------------------------------------------------------------
| Id  | Operation                            | Name               | Rows  |
---------------------------------------------------------------------------
|   0 | SELECT STATEMENT                     |                    |   318 |
|   1 |  FILTER                              |                    |       |
|   2 |   TABLE ACCESS BY INDEX ROWID BATCHED| TS_D2C25D2F_E      |   318 |
|   3 |    INDEX RANGE SCAN                  | TS_D2C25D2F_E_PATH |  1036 |
---------------------------------------------------------------------------
```

**ordinary / disjoint / scoped**

```
 
---------------------------------------------------------------------------------
| Id  | Operation                               | Name                  | Rows  |
---------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                        |                       |   322 |
|   1 |  UNION-ALL                              |                       |   322 |
|   2 |   FILTER                                |                       |       |
|   3 |    TABLE ACCESS BY INDEX ROWID BATCHED  | TS_D2C25D2F_E         |   288 |
|   4 |     INDEX RANGE SCAN                    | TS_D2C25D2F_E_LVLPATH |   518 |
|   5 |   FILTER                                |                       |       |
|   6 |    HASH JOIN                            |                       |     1 |
|   7 |     JSONTABLE EVALUATION                |                       |       |
|   8 |     TABLE ACCESS BY INDEX ROWID BATCHED | TS_D2C25D2F_E         |   288 |
|   9 |      INDEX RANGE SCAN                   | TS_D2C25D2F_E_PATH    |  1036 |
|  10 |   FILTER                                |                       |       |
|  11 |    MERGE JOIN                           |                       |    32 |
|  12 |     SORT JOIN                           |                       |   288 |
|  13 |      TABLE ACCESS BY INDEX ROWID BATCHED| TS_D2C25D2F_E         |   288 |
|  14 |       INDEX RANGE SCAN                  | TS_D2C25D2F_E_PATH    |  1036 |
|  15 |     FILTER                              |                       |       |
|  16 |      SORT JOIN                          |                       |    44 |
|  17 |       JSONTABLE EVALUATION              |                       |       |
|  18 |   FILTER                                |                       |       |
|  19 |    HASH JOIN ANTI                       |                       |     1 |
|  20 |     NESTED LOOPS ANTI                   |                       |     1 |
|  21 |      TABLE ACCESS BY INDEX ROWID BATCHED| TS_D2C25D2F_E         |     1 |
|  22 |       INDEX RANGE SCAN                  | TS_D2C25D2F_E_OWNER   |    22 |
|  23 |      JSONTABLE EVALUATION               |                       |       |
|  24 |     JSONTABLE EVALUATION                |                       |       |
---------------------------------------------------------------------------------
```

**ordinary / union / count**

```
 
----------------------------------------------------------------------------------
| Id  | Operation                                | Name                  | Rows  |
----------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                         |                       |     1 |
|   1 |  SORT AGGREGATE                          |                       |     1 |
|   2 |   NESTED LOOPS                           |                       |   379K|
|   3 |    VIEW                                  |                       |   127K|
|   4 |     HASH UNIQUE                          |                       |   127K|
|   5 |      UNION-ALL                           |                       |   127K|
|   6 |       TABLE ACCESS BY INDEX ROWID BATCHED| TS_D2C25D2F_E         |   115K|
|   7 |        INDEX RANGE SCAN                  | TS_D2C25D2F_E_LVLPATH |   115K|
|   8 |       NESTED LOOPS                       |                       |    22 |
|   9 |        NESTED LOOPS                      |                       |    44 |
|  10 |         JSONTABLE EVALUATION             |                       |       |
|  11 |         INDEX UNIQUE SCAN                | TS_D2C25D2F_E_PATH    |     1 |
|  12 |        TABLE ACCESS BY INDEX ROWID       | TS_D2C25D2F_E         |     1 |
|  13 |       NESTED LOOPS                       |                       | 12661 |
|  14 |        NESTED LOOPS                      |                       | 45584 |
|  15 |         JSONTABLE EVALUATION             |                       |       |
|  16 |         INDEX RANGE SCAN                 | TS_D2C25D2F_E_PATH    |  1036 |
|  17 |        TABLE ACCESS BY INDEX ROWID       | TS_D2C25D2F_E         |   288 |
|  18 |       TABLE ACCESS BY INDEX ROWID BATCHED| TS_D2C25D2F_E         |    11 |
|  19 |        INDEX RANGE SCAN                  | TS_D2C25D2F_E_OWNER   |    22 |
|  20 |    INDEX RANGE SCAN                      | TS_D2C25D2F_C_ENTRY   |     3 |
----------------------------------------------------------------------------------
```

**ordinary / unionall / count**

```
 
----------------------------------------------------------------------------------
| Id  | Operation                                | Name                  | Rows  |
----------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                         |                       |     1 |
|   1 |  SORT AGGREGATE                          |                       |     1 |
|   2 |   NESTED LOOPS                           |                       |   379K|
|   3 |    VIEW                                  |                       |   127K|
|   4 |     HASH UNIQUE                          |                       |   127K|
|   5 |      UNION-ALL                           |                       |   127K|
|   6 |       TABLE ACCESS BY INDEX ROWID BATCHED| TS_D2C25D2F_E         |   115K|
|   7 |        INDEX RANGE SCAN                  | TS_D2C25D2F_E_LVLPATH |   115K|
|   8 |       NESTED LOOPS                       |                       |    22 |
|   9 |        NESTED LOOPS                      |                       |    44 |
|  10 |         JSONTABLE EVALUATION             |                       |       |
|  11 |         INDEX UNIQUE SCAN                | TS_D2C25D2F_E_PATH    |     1 |
|  12 |        TABLE ACCESS BY INDEX ROWID       | TS_D2C25D2F_E         |     1 |
|  13 |       NESTED LOOPS                       |                       | 12661 |
|  14 |        NESTED LOOPS                      |                       | 45584 |
|  15 |         JSONTABLE EVALUATION             |                       |       |
|  16 |         INDEX RANGE SCAN                 | TS_D2C25D2F_E_PATH    |  1036 |
|  17 |        TABLE ACCESS BY INDEX ROWID       | TS_D2C25D2F_E         |   288 |
|  18 |       TABLE ACCESS BY INDEX ROWID BATCHED| TS_D2C25D2F_E         |    11 |
|  19 |        INDEX RANGE SCAN                  | TS_D2C25D2F_E_OWNER   |    22 |
|  20 |    INDEX RANGE SCAN                      | TS_D2C25D2F_C_ENTRY   |     3 |
----------------------------------------------------------------------------------
```

**ordinary / literal / count**

```
 
--------------------------------------------------------------
| Id  | Operation              | Name                | Rows  |
--------------------------------------------------------------
|   0 | SELECT STATEMENT       |                     |     1 |
|   1 |  SORT AGGREGATE        |                     |     1 |
|   2 |   HASH JOIN            |                     |   377K|
|   3 |    INDEX FAST FULL SCAN| TS_D2C25D2F_C_ENTRY |   660K|
|   4 |    TABLE ACCESS FULL   | TS_D2C25D2F_E       |   127K|
--------------------------------------------------------------
```

**ordinary / disjoint / count**

```
 
------------------------------------------------------------------------------------
| Id  | Operation                                  | Name                  | Rows  |
------------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                           |                       |     1 |
|   1 |  SORT AGGREGATE                            |                       |     1 |
|   2 |   NESTED LOOPS                             |                       |   379K|
|   3 |    VIEW                                    |                       |   127K|
|   4 |     UNION-ALL                              |                       |   127K|
|   5 |      TABLE ACCESS BY INDEX ROWID BATCHED   | TS_D2C25D2F_E         |   115K|
|   6 |       INDEX RANGE SCAN                     | TS_D2C25D2F_E_LVLPATH |   115K|
|   7 |      NESTED LOOPS                          |                       |    22 |
|   8 |       NESTED LOOPS                         |                       |    44 |
|   9 |        JSONTABLE EVALUATION                |                       |       |
|  10 |        INDEX UNIQUE SCAN                   | TS_D2C25D2F_E_PATH    |     1 |
|  11 |       TABLE ACCESS BY INDEX ROWID          | TS_D2C25D2F_E         |     1 |
|  12 |      NESTED LOOPS                          |                       | 12661 |
|  13 |       NESTED LOOPS                         |                       | 45584 |
|  14 |        JSONTABLE EVALUATION                |                       |       |
|  15 |        INDEX RANGE SCAN                    | TS_D2C25D2F_E_PATH    |  1036 |
|  16 |       TABLE ACCESS BY INDEX ROWID          | TS_D2C25D2F_E         |   288 |
|  17 |      MERGE JOIN ANTI                       |                       |    11 |
|  18 |       SORT JOIN                            |                       |    11 |
|  19 |        HASH JOIN ANTI                      |                       |    11 |
|  20 |         TABLE ACCESS BY INDEX ROWID BATCHED| TS_D2C25D2F_E         |    11 |
|  21 |          INDEX RANGE SCAN                  | TS_D2C25D2F_E_OWNER   |    22 |
|  22 |         JSONTABLE EVALUATION               |                       |       |
|  23 |       FILTER                               |                       |       |
|  24 |        SORT JOIN                           |                       |  8168 |
|  25 |         JSONTABLE EVALUATION               |                       |       |
|  26 |    INDEX RANGE SCAN                        | TS_D2C25D2F_C_ENTRY   |     3 |
------------------------------------------------------------------------------------
```

**ordinary / union / top10**

```
 
-------------------------------------------------------------------------------------
| Id  | Operation                                   | Name                  | Rows  |
-------------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                            |                       |    10 |
|   1 |  COUNT STOPKEY                              |                       |       |
|   2 |   VIEW                                      |                       |   379K|
|   3 |    SORT ORDER BY STOPKEY                    |                       |   379K|
|   4 |     NESTED LOOPS                            |                       |   379K|
|   5 |      NESTED LOOPS                           |                       |   383K|
|   6 |       VIEW                                  |                       |   127K|
|   7 |        HASH UNIQUE                          |                       |   127K|
|   8 |         UNION-ALL                           |                       |   127K|
|   9 |          TABLE ACCESS BY INDEX ROWID BATCHED| TS_D2C25D2F_E         |   115K|
|  10 |           INDEX RANGE SCAN                  | TS_D2C25D2F_E_LVLPATH |   115K|
|  11 |          NESTED LOOPS                       |                       |    22 |
|  12 |           NESTED LOOPS                      |                       |    44 |
|  13 |            JSONTABLE EVALUATION             |                       |       |
|  14 |            INDEX UNIQUE SCAN                | TS_D2C25D2F_E_PATH    |     1 |
|  15 |           TABLE ACCESS BY INDEX ROWID       | TS_D2C25D2F_E         |     1 |
|  16 |          NESTED LOOPS                       |                       | 12661 |
|  17 |           NESTED LOOPS                      |                       | 45584 |
|  18 |            JSONTABLE EVALUATION             |                       |       |
|  19 |            INDEX RANGE SCAN                 | TS_D2C25D2F_E_PATH    |  1036 |
|  20 |           TABLE ACCESS BY INDEX ROWID       | TS_D2C25D2F_E         |   288 |
|  21 |          TABLE ACCESS BY INDEX ROWID BATCHED| TS_D2C25D2F_E         |    11 |
|  22 |           INDEX RANGE SCAN                  | TS_D2C25D2F_E_OWNER   |    22 |
|  23 |       INDEX RANGE SCAN                      | TS_D2C25D2F_C_ENTRY   |     3 |
|  24 |      TABLE ACCESS BY INDEX ROWID            | TS_D2C25D2F_C         |     3 |
-------------------------------------------------------------------------------------
```

**ordinary / unionall / top10**

```
 
-------------------------------------------------------------------------------------
| Id  | Operation                                   | Name                  | Rows  |
-------------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                            |                       |    10 |
|   1 |  COUNT STOPKEY                              |                       |       |
|   2 |   VIEW                                      |                       |   379K|
|   3 |    SORT ORDER BY STOPKEY                    |                       |   379K|
|   4 |     NESTED LOOPS                            |                       |   379K|
|   5 |      NESTED LOOPS                           |                       |   383K|
|   6 |       VIEW                                  |                       |   127K|
|   7 |        HASH UNIQUE                          |                       |   127K|
|   8 |         UNION-ALL                           |                       |   127K|
|   9 |          TABLE ACCESS BY INDEX ROWID BATCHED| TS_D2C25D2F_E         |   115K|
|  10 |           INDEX RANGE SCAN                  | TS_D2C25D2F_E_LVLPATH |   115K|
|  11 |          NESTED LOOPS                       |                       |    22 |
|  12 |           NESTED LOOPS                      |                       |    44 |
|  13 |            JSONTABLE EVALUATION             |                       |       |
|  14 |            INDEX UNIQUE SCAN                | TS_D2C25D2F_E_PATH    |     1 |
|  15 |           TABLE ACCESS BY INDEX ROWID       | TS_D2C25D2F_E         |     1 |
|  16 |          NESTED LOOPS                       |                       | 12661 |
|  17 |           NESTED LOOPS                      |                       | 45584 |
|  18 |            JSONTABLE EVALUATION             |                       |       |
|  19 |            INDEX RANGE SCAN                 | TS_D2C25D2F_E_PATH    |  1036 |
|  20 |           TABLE ACCESS BY INDEX ROWID       | TS_D2C25D2F_E         |   288 |
|  21 |          TABLE ACCESS BY INDEX ROWID BATCHED| TS_D2C25D2F_E         |    11 |
|  22 |           INDEX RANGE SCAN                  | TS_D2C25D2F_E_OWNER   |    22 |
|  23 |       INDEX RANGE SCAN                      | TS_D2C25D2F_C_ENTRY   |     3 |
|  24 |      TABLE ACCESS BY INDEX ROWID            | TS_D2C25D2F_C         |     3 |
-------------------------------------------------------------------------------------
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
|   4 |     NESTED LOOPS                |                     |    19 |
|   5 |      TABLE ACCESS BY INDEX ROWID| TS_D2C25D2F_C       |   660K|
|   6 |       INDEX FULL SCAN           | TS_D2C25D2F_C_SCORE |    19 |
|   7 |      INDEX UNIQUE SCAN          | SYS_C00129784       |     1 |
|   8 |     TABLE ACCESS BY INDEX ROWID | TS_D2C25D2F_E       |     1 |
-----------------------------------------------------------------------
```

**ordinary / disjoint / top10**

```
 
---------------------------------------------------------------------------------------
| Id  | Operation                                     | Name                  | Rows  |
---------------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                              |                       |    10 |
|   1 |  COUNT STOPKEY                                |                       |       |
|   2 |   VIEW                                        |                       |   122 |
|   3 |    SORT ORDER BY STOPKEY                      |                       |   122 |
|   4 |     NESTED LOOPS                              |                       |   122 |
|   5 |      NESTED LOOPS                             |                       |   123 |
|   6 |       VIEW                                    |                       |    41 |
|   7 |        UNION-ALL                              |                       |   127K|
|   8 |         TABLE ACCESS BY INDEX ROWID BATCHED   | TS_D2C25D2F_E         |    11 |
|   9 |          INDEX RANGE SCAN                     | TS_D2C25D2F_E_LVLPATH |   115K|
|  10 |         NESTED LOOPS                          |                       |    10 |
|  11 |          NESTED LOOPS                         |                       |    44 |
|  12 |           JSONTABLE EVALUATION                |                       |       |
|  13 |           INDEX UNIQUE SCAN                   | TS_D2C25D2F_E_PATH    |     1 |
|  14 |          TABLE ACCESS BY INDEX ROWID          | TS_D2C25D2F_E         |     1 |
|  15 |         NESTED LOOPS                          |                       |    10 |
|  16 |          NESTED LOOPS                         |                       |  1760 |
|  17 |           JSONTABLE EVALUATION                |                       |       |
|  18 |           INDEX RANGE SCAN                    | TS_D2C25D2F_E_PATH    |    40 |
|  19 |          TABLE ACCESS BY INDEX ROWID          | TS_D2C25D2F_E         |    11 |
|  20 |         MERGE JOIN ANTI                       |                       |    10 |
|  21 |          SORT JOIN                            |                       |    11 |
|  22 |           HASH JOIN ANTI                      |                       |    11 |
|  23 |            TABLE ACCESS BY INDEX ROWID BATCHED| TS_D2C25D2F_E         |    11 |
|  24 |             INDEX RANGE SCAN                  | TS_D2C25D2F_E_OWNER   |    22 |
|  25 |            JSONTABLE EVALUATION               |                       |       |
|  26 |          FILTER                               |                       |       |
|  27 |           SORT JOIN                           |                       |  7445 |
|  28 |            JSONTABLE EVALUATION               |                       |       |
|  29 |       INDEX RANGE SCAN                        | TS_D2C25D2F_C_ENTRY   |     3 |
|  30 |      TABLE ACCESS BY INDEX ROWID              | TS_D2C25D2F_C         |     3 |
---------------------------------------------------------------------------------------
```

**two subjects / union / entries**

```
 
---------------------------------------------------------------------------------
| Id  | Operation                               | Name                  | Rows  |
---------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                        |                       |   121K|
|   1 |  HASH UNIQUE                            |                       |   121K|
|   2 |   UNION-ALL                             |                       |   121K|
|   3 |    TABLE ACCESS BY INDEX ROWID BATCHED  | TS_D2C25D2F_E         |   115K|
|   4 |     INDEX RANGE SCAN                    | TS_D2C25D2F_E_LVLPATH |   115K|
|   5 |    NESTED LOOPS                         |                       |    11 |
|   6 |     NESTED LOOPS                        |                       |    21 |
|   7 |      JSONTABLE EVALUATION               |                       |       |
|   8 |      INDEX UNIQUE SCAN                  | TS_D2C25D2F_E_PATH    |     1 |
|   9 |     TABLE ACCESS BY INDEX ROWID         | TS_D2C25D2F_E         |     1 |
|  10 |    NESTED LOOPS                         |                       |  6043 |
|  11 |     NESTED LOOPS                        |                       | 21756 |
|  12 |      JSONTABLE EVALUATION               |                       |       |
|  13 |      INDEX RANGE SCAN                   | TS_D2C25D2F_E_PATH    |  1036 |
|  14 |     TABLE ACCESS BY INDEX ROWID         | TS_D2C25D2F_E         |   288 |
|  15 |    HASH JOIN                            |                       |     1 |
|  16 |     TABLE ACCESS BY INDEX ROWID BATCHED | TS_D2C25D2F_E         |    11 |
|  17 |      INDEX RANGE SCAN                   | TS_D2C25D2F_E_OWNER   |    22 |
|  18 |     JSONTABLE EVALUATION                |                       |       |
|  19 |    MERGE JOIN                           |                       |     1 |
|  20 |     SORT JOIN                           |                       |    11 |
|  21 |      TABLE ACCESS BY INDEX ROWID BATCHED| TS_D2C25D2F_E         |    11 |
|  22 |       INDEX RANGE SCAN                  | TS_D2C25D2F_E_OWNER   |    22 |
|  23 |     FILTER                              |                       |       |
|  24 |      SORT JOIN                          |                       |    45 |
|  25 |       JSONTABLE EVALUATION              |                       |       |
|  26 |    HASH JOIN                            |                       |     1 |
|  27 |     TABLE ACCESS BY INDEX ROWID BATCHED | TS_D2C25D2F_E         |    11 |
|  28 |      INDEX RANGE SCAN                   | TS_D2C25D2F_E_OWNER   |    22 |
|  29 |     JSONTABLE EVALUATION                |                       |       |
|  30 |    MERGE JOIN                           |                       |     1 |
|  31 |     SORT JOIN                           |                       |    11 |
|  32 |      TABLE ACCESS BY INDEX ROWID BATCHED| TS_D2C25D2F_E         |    11 |
|  33 |       INDEX RANGE SCAN                  | TS_D2C25D2F_E_OWNER   |    22 |
|  34 |     FILTER                              |                       |       |
|  35 |      SORT JOIN                          |                       |    44 |
|  36 |       JSONTABLE EVALUATION              |                       |       |
---------------------------------------------------------------------------------
```

**two subjects / unionall / entries**

```
 
---------------------------------------------------------------------------------
| Id  | Operation                               | Name                  | Rows  |
---------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                        |                       |   121K|
|   1 |  HASH UNIQUE                            |                       |   121K|
|   2 |   UNION-ALL                             |                       |   121K|
|   3 |    TABLE ACCESS BY INDEX ROWID BATCHED  | TS_D2C25D2F_E         |   115K|
|   4 |     INDEX RANGE SCAN                    | TS_D2C25D2F_E_LVLPATH |   115K|
|   5 |    NESTED LOOPS                         |                       |    11 |
|   6 |     NESTED LOOPS                        |                       |    21 |
|   7 |      JSONTABLE EVALUATION               |                       |       |
|   8 |      INDEX UNIQUE SCAN                  | TS_D2C25D2F_E_PATH    |     1 |
|   9 |     TABLE ACCESS BY INDEX ROWID         | TS_D2C25D2F_E         |     1 |
|  10 |    NESTED LOOPS                         |                       |  6043 |
|  11 |     NESTED LOOPS                        |                       | 21756 |
|  12 |      JSONTABLE EVALUATION               |                       |       |
|  13 |      INDEX RANGE SCAN                   | TS_D2C25D2F_E_PATH    |  1036 |
|  14 |     TABLE ACCESS BY INDEX ROWID         | TS_D2C25D2F_E         |   288 |
|  15 |    HASH JOIN                            |                       |     1 |
|  16 |     TABLE ACCESS BY INDEX ROWID BATCHED | TS_D2C25D2F_E         |    11 |
|  17 |      INDEX RANGE SCAN                   | TS_D2C25D2F_E_OWNER   |    22 |
|  18 |     JSONTABLE EVALUATION                |                       |       |
|  19 |    MERGE JOIN                           |                       |     1 |
|  20 |     SORT JOIN                           |                       |    11 |
|  21 |      TABLE ACCESS BY INDEX ROWID BATCHED| TS_D2C25D2F_E         |    11 |
|  22 |       INDEX RANGE SCAN                  | TS_D2C25D2F_E_OWNER   |    22 |
|  23 |     FILTER                              |                       |       |
|  24 |      SORT JOIN                          |                       |    45 |
|  25 |       JSONTABLE EVALUATION              |                       |       |
|  26 |    HASH JOIN                            |                       |     1 |
|  27 |     TABLE ACCESS BY INDEX ROWID BATCHED | TS_D2C25D2F_E         |    11 |
|  28 |      INDEX RANGE SCAN                   | TS_D2C25D2F_E_OWNER   |    22 |
|  29 |     JSONTABLE EVALUATION                |                       |       |
|  30 |    MERGE JOIN                           |                       |     1 |
|  31 |     SORT JOIN                           |                       |    11 |
|  32 |      TABLE ACCESS BY INDEX ROWID BATCHED| TS_D2C25D2F_E         |    11 |
|  33 |       INDEX RANGE SCAN                  | TS_D2C25D2F_E_OWNER   |    22 |
|  34 |     FILTER                              |                       |       |
|  35 |      SORT JOIN                          |                       |    44 |
|  36 |       JSONTABLE EVALUATION              |                       |       |
---------------------------------------------------------------------------------
```

**two subjects / literal / entries**

```
 
---------------------------------------------------
| Id  | Operation         | Name          | Rows  |
---------------------------------------------------
|   0 | SELECT STATEMENT  |               |   121K|
|   1 |  TABLE ACCESS FULL| TS_D2C25D2F_E |   121K|
---------------------------------------------------
```

**two subjects / disjoint / entries**

```
 
----------------------------------------------------------------------------------
| Id  | Operation                                | Name                  | Rows  |
----------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                         |                       |   121K|
|   1 |  UNION-ALL                               |                       |   121K|
|   2 |   TABLE ACCESS BY INDEX ROWID BATCHED    | TS_D2C25D2F_E         |   115K|
|   3 |    INDEX RANGE SCAN                      | TS_D2C25D2F_E_LVLPATH |   115K|
|   4 |   NESTED LOOPS                           |                       |    11 |
|   5 |    NESTED LOOPS                          |                       |    21 |
|   6 |     JSONTABLE EVALUATION                 |                       |       |
|   7 |     INDEX UNIQUE SCAN                    | TS_D2C25D2F_E_PATH    |     1 |
|   8 |    TABLE ACCESS BY INDEX ROWID           | TS_D2C25D2F_E         |     1 |
|   9 |   NESTED LOOPS                           |                       |  6043 |
|  10 |    NESTED LOOPS                          |                       | 21756 |
|  11 |     JSONTABLE EVALUATION                 |                       |       |
|  12 |     INDEX RANGE SCAN                     | TS_D2C25D2F_E_PATH    |  1036 |
|  13 |    TABLE ACCESS BY INDEX ROWID           | TS_D2C25D2F_E         |   288 |
|  14 |   HASH JOIN ANTI                         |                       |     1 |
|  15 |    NESTED LOOPS ANTI                     |                       |     1 |
|  16 |     HASH JOIN                            |                       |     1 |
|  17 |      TABLE ACCESS BY INDEX ROWID BATCHED | TS_D2C25D2F_E         |    11 |
|  18 |       INDEX RANGE SCAN                   | TS_D2C25D2F_E_OWNER   |    22 |
|  19 |      JSONTABLE EVALUATION                |                       |       |
|  20 |     JSONTABLE EVALUATION                 |                       |       |
|  21 |    JSONTABLE EVALUATION                  |                       |       |
|  22 |   HASH JOIN ANTI                         |                       |     1 |
|  23 |    NESTED LOOPS ANTI                     |                       |     1 |
|  24 |     MERGE JOIN                           |                       |     1 |
|  25 |      SORT JOIN                           |                       |    11 |
|  26 |       TABLE ACCESS BY INDEX ROWID BATCHED| TS_D2C25D2F_E         |    11 |
|  27 |        INDEX RANGE SCAN                  | TS_D2C25D2F_E_OWNER   |    22 |
|  28 |      FILTER                              |                       |       |
|  29 |       SORT JOIN                          |                       |    45 |
|  30 |        JSONTABLE EVALUATION              |                       |       |
|  31 |     JSONTABLE EVALUATION                 |                       |       |
|  32 |    JSONTABLE EVALUATION                  |                       |       |
|  33 |   HASH JOIN ANTI                         |                       |     1 |
|  34 |    NESTED LOOPS ANTI                     |                       |     1 |
|  35 |     HASH JOIN                            |                       |     1 |
|  36 |      TABLE ACCESS BY INDEX ROWID BATCHED | TS_D2C25D2F_E         |    11 |
|  37 |       INDEX RANGE SCAN                   | TS_D2C25D2F_E_OWNER   |    22 |
|  38 |      JSONTABLE EVALUATION                |                       |       |
|  39 |     JSONTABLE EVALUATION                 |                       |       |
|  40 |    JSONTABLE EVALUATION                  |                       |       |
|  41 |   HASH JOIN ANTI                         |                       |     1 |
|  42 |    NESTED LOOPS ANTI                     |                       |     1 |
|  43 |     MERGE JOIN                           |                       |     1 |
|  44 |      SORT JOIN                           |                       |    11 |
|  45 |       TABLE ACCESS BY INDEX ROWID BATCHED| TS_D2C25D2F_E         |    11 |
|  46 |        INDEX RANGE SCAN                  | TS_D2C25D2F_E_OWNER   |    22 |
|  47 |      FILTER                              |                       |       |
|  48 |       SORT JOIN                          |                       |    44 |
|  49 |        JSONTABLE EVALUATION              |                       |       |
|  50 |     JSONTABLE EVALUATION                 |                       |       |
|  51 |    JSONTABLE EVALUATION                  |                       |       |
----------------------------------------------------------------------------------
```

**scoped / anonymous / union / IN**

```
 
-------------------------------------------------------------------------------
| Id  | Operation                             | Name                  | Rows  |
-------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                      |                       |   576 |
|   1 |  FILTER                               |                       |       |
|   2 |   INLIST ITERATOR                     |                       |       |
|   3 |    TABLE ACCESS BY INDEX ROWID BATCHED| TS_D2C25D2F_E         |   576 |
|   4 |     INDEX RANGE SCAN                  | TS_D2C25D2F_E_LVLPATH |  1036 |
-------------------------------------------------------------------------------
```

**scoped / anonymous / union / >=**

```
 
------------------------------------------------------------------------------
| Id  | Operation                            | Name                  | Rows  |
------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                     |                       |   288 |
|   1 |  FILTER                              |                       |       |
|   2 |   TABLE ACCESS BY INDEX ROWID BATCHED| TS_D2C25D2F_E         |   288 |
|   3 |    INDEX RANGE SCAN                  | TS_D2C25D2F_E_LVLPATH |   518 |
------------------------------------------------------------------------------
```

**scoped / ordinary / union / IN**

```
 
----------------------------------------------------------------------------------
| Id  | Operation                                | Name                  | Rows  |
----------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                         |                       |   610 |
|   1 |  HASH UNIQUE                             |                       |   610 |
|   2 |   UNION-ALL                              |                       |   610 |
|   3 |    FILTER                                |                       |       |
|   4 |     INLIST ITERATOR                      |                       |       |
|   5 |      TABLE ACCESS BY INDEX ROWID BATCHED | TS_D2C25D2F_E         |   576 |
|   6 |       INDEX RANGE SCAN                   | TS_D2C25D2F_E_LVLPATH |  1036 |
|   7 |    FILTER                                |                       |       |
|   8 |     HASH JOIN                            |                       |     1 |
|   9 |      JSONTABLE EVALUATION                |                       |       |
|  10 |      TABLE ACCESS BY INDEX ROWID BATCHED | TS_D2C25D2F_E         |   288 |
|  11 |       INDEX RANGE SCAN                   | TS_D2C25D2F_E_PATH    |  1036 |
|  12 |    FILTER                                |                       |       |
|  13 |     MERGE JOIN                           |                       |    32 |
|  14 |      SORT JOIN                           |                       |   288 |
|  15 |       TABLE ACCESS BY INDEX ROWID BATCHED| TS_D2C25D2F_E         |   288 |
|  16 |        INDEX RANGE SCAN                  | TS_D2C25D2F_E_PATH    |  1036 |
|  17 |      FILTER                              |                       |       |
|  18 |       SORT JOIN                          |                       |    44 |
|  19 |        JSONTABLE EVALUATION              |                       |       |
|  20 |    FILTER                                |                       |       |
|  21 |     TABLE ACCESS BY INDEX ROWID BATCHED  | TS_D2C25D2F_E         |     1 |
|  22 |      INDEX RANGE SCAN                    | TS_D2C25D2F_E_OWNER   |    22 |
----------------------------------------------------------------------------------
```

**scoped / ordinary / unionall / IN**

```
 
----------------------------------------------------------------------------------
| Id  | Operation                                | Name                  | Rows  |
----------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                         |                       |   610 |
|   1 |  HASH UNIQUE                             |                       |   610 |
|   2 |   UNION-ALL                              |                       |   610 |
|   3 |    FILTER                                |                       |       |
|   4 |     INLIST ITERATOR                      |                       |       |
|   5 |      TABLE ACCESS BY INDEX ROWID BATCHED | TS_D2C25D2F_E         |   576 |
|   6 |       INDEX RANGE SCAN                   | TS_D2C25D2F_E_LVLPATH |  1036 |
|   7 |    FILTER                                |                       |       |
|   8 |     HASH JOIN                            |                       |     1 |
|   9 |      JSONTABLE EVALUATION                |                       |       |
|  10 |      TABLE ACCESS BY INDEX ROWID BATCHED | TS_D2C25D2F_E         |   288 |
|  11 |       INDEX RANGE SCAN                   | TS_D2C25D2F_E_PATH    |  1036 |
|  12 |    FILTER                                |                       |       |
|  13 |     MERGE JOIN                           |                       |    32 |
|  14 |      SORT JOIN                           |                       |   288 |
|  15 |       TABLE ACCESS BY INDEX ROWID BATCHED| TS_D2C25D2F_E         |   288 |
|  16 |        INDEX RANGE SCAN                  | TS_D2C25D2F_E_PATH    |  1036 |
|  17 |      FILTER                              |                       |       |
|  18 |       SORT JOIN                          |                       |    44 |
|  19 |        JSONTABLE EVALUATION              |                       |       |
|  20 |    FILTER                                |                       |       |
|  21 |     TABLE ACCESS BY INDEX ROWID BATCHED  | TS_D2C25D2F_E         |     1 |
|  22 |      INDEX RANGE SCAN                    | TS_D2C25D2F_E_OWNER   |    22 |
----------------------------------------------------------------------------------
```

**scoped / ordinary / literal / IN**

```
 
---------------------------------------------------------------------------
| Id  | Operation                            | Name               | Rows  |
---------------------------------------------------------------------------
|   0 | SELECT STATEMENT                     |                    |   318 |
|   1 |  FILTER                              |                    |       |
|   2 |   TABLE ACCESS BY INDEX ROWID BATCHED| TS_D2C25D2F_E      |   318 |
|   3 |    INDEX RANGE SCAN                  | TS_D2C25D2F_E_PATH |  1036 |
---------------------------------------------------------------------------
```

**scoped / ordinary / disjoint / IN**

```
 
---------------------------------------------------------------------------------
| Id  | Operation                               | Name                  | Rows  |
---------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                        |                       |   610 |
|   1 |  UNION-ALL                              |                       |   610 |
|   2 |   FILTER                                |                       |       |
|   3 |    INLIST ITERATOR                      |                       |       |
|   4 |     TABLE ACCESS BY INDEX ROWID BATCHED | TS_D2C25D2F_E         |   576 |
|   5 |      INDEX RANGE SCAN                   | TS_D2C25D2F_E_LVLPATH |  1036 |
|   6 |   FILTER                                |                       |       |
|   7 |    HASH JOIN                            |                       |     1 |
|   8 |     JSONTABLE EVALUATION                |                       |       |
|   9 |     TABLE ACCESS BY INDEX ROWID BATCHED | TS_D2C25D2F_E         |   288 |
|  10 |      INDEX RANGE SCAN                   | TS_D2C25D2F_E_PATH    |  1036 |
|  11 |   FILTER                                |                       |       |
|  12 |    MERGE JOIN                           |                       |    32 |
|  13 |     SORT JOIN                           |                       |   288 |
|  14 |      TABLE ACCESS BY INDEX ROWID BATCHED| TS_D2C25D2F_E         |   288 |
|  15 |       INDEX RANGE SCAN                  | TS_D2C25D2F_E_PATH    |  1036 |
|  16 |     FILTER                              |                       |       |
|  17 |      SORT JOIN                          |                       |    44 |
|  18 |       JSONTABLE EVALUATION              |                       |       |
|  19 |   FILTER                                |                       |       |
|  20 |    HASH JOIN ANTI                       |                       |     1 |
|  21 |     NESTED LOOPS ANTI                   |                       |     1 |
|  22 |      TABLE ACCESS BY INDEX ROWID BATCHED| TS_D2C25D2F_E         |     1 |
|  23 |       INDEX RANGE SCAN                  | TS_D2C25D2F_E_OWNER   |    22 |
|  24 |      JSONTABLE EVALUATION               |                       |       |
|  25 |     JSONTABLE EVALUATION                |                       |       |
---------------------------------------------------------------------------------
```

Total wall time 116s.
