## oracle probe — N=10,000, ordinary caller (88 pieces), unionall shape; warm = median of 3

Load 60s.

| knobs | statement | cold / warm / recall |
|---|---|---|
| oracle_cardinality=False, oracle_one_index=False, oracle_derived_nl=False | entries | 982 / 1,111 / exact |
| oracle_cardinality=False, oracle_one_index=False, oracle_derived_nl=False | scoped | 20.5 / 13.9 / exact |
| oracle_cardinality=False, oracle_one_index=False, oracle_derived_nl=False | count | 102 / 67.7 / exact |
| oracle_cardinality=False, oracle_one_index=False, oracle_derived_nl=False | top10 | 102 / 112 / exact |
| oracle_cardinality=True, oracle_one_index=False, oracle_derived_nl=False | entries | 2,741 / 1,149 / exact |
| oracle_cardinality=True, oracle_one_index=False, oracle_derived_nl=False | scoped | 10.5 / 3.9 / exact |
| oracle_cardinality=True, oracle_one_index=False, oracle_derived_nl=False | count | 38.0 / 27.6 / exact |
| oracle_cardinality=True, oracle_one_index=False, oracle_derived_nl=False | top10 | 26.1 / 14.4 / exact |
| oracle_cardinality=True, oracle_one_index=True, oracle_derived_nl=False | entries | 177 / 167 / exact |
| oracle_cardinality=True, oracle_one_index=True, oracle_derived_nl=False | scoped | 8.1 / 2.8 / exact |
| oracle_cardinality=True, oracle_one_index=True, oracle_derived_nl=False | count | 34.8 / 23.9 / exact |
| oracle_cardinality=True, oracle_one_index=True, oracle_derived_nl=False | top10 | 23.6 / 14.5 / exact |
| oracle_cardinality=True, oracle_one_index=True, oracle_derived_nl=True | entries | 174 / 379 / exact |
| oracle_cardinality=True, oracle_one_index=True, oracle_derived_nl=True | scoped | 11.1 / 5.2 / exact |
| oracle_cardinality=True, oracle_one_index=True, oracle_derived_nl=True | count | 28.9 / 13.7 / exact |
| oracle_cardinality=True, oracle_one_index=True, oracle_derived_nl=True | top10 | 31.7 / 23.7 / exact |
| oracle_cardinality=False, oracle_one_index=False, oracle_derived_nl=False, oracle_leading=True | entries | 1,099 / 1,741 / exact |
| oracle_cardinality=False, oracle_one_index=False, oracle_derived_nl=False, oracle_leading=True | scoped | 17.8 / 5.0 / exact |
| oracle_cardinality=False, oracle_one_index=False, oracle_derived_nl=False, oracle_leading=True | count | 262 / 302 / exact |
| oracle_cardinality=False, oracle_one_index=False, oracle_derived_nl=False, oracle_leading=True | top10 | 269 / 238 / exact |

**oracle_cardinality=False, oracle_one_index=False, oracle_derived_nl=False / entries**

```
 
-----------------------------------------------------------------------------
| Id  | Operation                             | Name                | Rows  |
-----------------------------------------------------------------------------
|   0 | SELECT STATEMENT                      |                     |  2469K|
|   1 |  HASH UNIQUE                          |                     |  2469K|
|   2 |   UNION-ALL                           |                     |  2469K|
|   3 |    TABLE ACCESS FULL                  | TS_CDF20396_E       |   115K|
|   4 |    HASH JOIN                          |                     |  4084 |
|   5 |     JSONTABLE EVALUATION              |                     |       |
|   6 |     TABLE ACCESS FULL                 | TS_CDF20396_E       |   115K|
|   7 |    MERGE JOIN                         |                     |  2350K|
|   8 |     SORT JOIN                         |                     |  8168 |
|   9 |      JSONTABLE EVALUATION             |                     |       |
|  10 |     FILTER                            |                     |       |
|  11 |      SORT JOIN                        |                     |   115K|
|  12 |       TABLE ACCESS FULL               | TS_CDF20396_E       |   115K|
|  13 |    TABLE ACCESS BY INDEX ROWID BATCHED| TS_CDF20396_E       |    11 |
|  14 |     INDEX RANGE SCAN                  | TS_CDF20396_E_OWNER |    22 |
-----------------------------------------------------------------------------
```

**oracle_cardinality=False, oracle_one_index=False, oracle_derived_nl=False / count**

```
 
--------------------------------------------------------------------------------
| Id  | Operation                                | Name                | Rows  |
--------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                         |                     |     1 |
|   1 |  SORT AGGREGATE                          |                     |     1 |
|   2 |   HASH JOIN                              |                     |  2469K|
|   3 |    INDEX FAST FULL SCAN                  | TS_CDF20396_C_ENTRY |   220K|
|   4 |    VIEW                                  |                     |  2469K|
|   5 |     HASH UNIQUE                          |                     |  2469K|
|   6 |      UNION-ALL                           |                     |  2469K|
|   7 |       TABLE ACCESS FULL                  | TS_CDF20396_E       |   115K|
|   8 |       HASH JOIN                          |                     |  4084 |
|   9 |        JSONTABLE EVALUATION              |                     |       |
|  10 |        TABLE ACCESS FULL                 | TS_CDF20396_E       |   115K|
|  11 |       MERGE JOIN                         |                     |  2350K|
|  12 |        SORT JOIN                         |                     |  8168 |
|  13 |         JSONTABLE EVALUATION             |                     |       |
|  14 |        FILTER                            |                     |       |
|  15 |         SORT JOIN                        |                     |   115K|
|  16 |          TABLE ACCESS FULL               | TS_CDF20396_E       |   115K|
|  17 |       TABLE ACCESS BY INDEX ROWID BATCHED| TS_CDF20396_E       |    11 |
|  18 |        INDEX RANGE SCAN                  | TS_CDF20396_E_OWNER |    22 |
--------------------------------------------------------------------------------
```

**oracle_cardinality=True, oracle_one_index=False, oracle_derived_nl=False / entries**

```
 
-----------------------------------------------------------------------------
| Id  | Operation                             | Name                | Rows  |
-----------------------------------------------------------------------------
|   0 | SELECT STATEMENT                      |                     |   127K|
|   1 |  HASH UNIQUE                          |                     |   127K|
|   2 |   UNION-ALL                           |                     |   127K|
|   3 |    TABLE ACCESS FULL                  | TS_CDF20396_E       |   115K|
|   4 |    NESTED LOOPS                       |                     |    22 |
|   5 |     NESTED LOOPS                      |                     |    44 |
|   6 |      JSONTABLE EVALUATION             |                     |       |
|   7 |      INDEX UNIQUE SCAN                | TS_CDF20396_E_PATH  |     1 |
|   8 |     TABLE ACCESS BY INDEX ROWID       | TS_CDF20396_E       |     1 |
|   9 |    NESTED LOOPS                       |                     | 12661 |
|  10 |     NESTED LOOPS                      |                     | 45584 |
|  11 |      JSONTABLE EVALUATION             |                     |       |
|  12 |      INDEX RANGE SCAN                 | TS_CDF20396_E_PATH  |  1036 |
|  13 |     TABLE ACCESS BY INDEX ROWID       | TS_CDF20396_E       |   288 |
|  14 |    TABLE ACCESS BY INDEX ROWID BATCHED| TS_CDF20396_E       |    11 |
|  15 |     INDEX RANGE SCAN                  | TS_CDF20396_E_OWNER |    22 |
-----------------------------------------------------------------------------
```

**oracle_cardinality=True, oracle_one_index=False, oracle_derived_nl=False / count**

```
 
--------------------------------------------------------------------------------
| Id  | Operation                                | Name                | Rows  |
--------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                         |                     |     1 |
|   1 |  SORT AGGREGATE                          |                     |     1 |
|   2 |   HASH JOIN                              |                     |   127K|
|   3 |    INDEX FAST FULL SCAN                  | TS_CDF20396_C_ENTRY |   220K|
|   4 |    VIEW                                  |                     |   127K|
|   5 |     HASH UNIQUE                          |                     |   127K|
|   6 |      UNION-ALL                           |                     |   127K|
|   7 |       TABLE ACCESS FULL                  | TS_CDF20396_E       |   115K|
|   8 |       NESTED LOOPS                       |                     |    22 |
|   9 |        NESTED LOOPS                      |                     |    44 |
|  10 |         JSONTABLE EVALUATION             |                     |       |
|  11 |         INDEX UNIQUE SCAN                | TS_CDF20396_E_PATH  |     1 |
|  12 |        TABLE ACCESS BY INDEX ROWID       | TS_CDF20396_E       |     1 |
|  13 |       NESTED LOOPS                       |                     | 12661 |
|  14 |        NESTED LOOPS                      |                     | 45584 |
|  15 |         JSONTABLE EVALUATION             |                     |       |
|  16 |         INDEX RANGE SCAN                 | TS_CDF20396_E_PATH  |  1036 |
|  17 |        TABLE ACCESS BY INDEX ROWID       | TS_CDF20396_E       |   288 |
|  18 |       TABLE ACCESS BY INDEX ROWID BATCHED| TS_CDF20396_E       |    11 |
|  19 |        INDEX RANGE SCAN                  | TS_CDF20396_E_OWNER |    22 |
--------------------------------------------------------------------------------
```

**oracle_cardinality=True, oracle_one_index=True, oracle_derived_nl=False / entries**

```
 
-------------------------------------------------------------------------------
| Id  | Operation                             | Name                  | Rows  |
-------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                      |                       |   127K|
|   1 |  HASH UNIQUE                          |                       |   127K|
|   2 |   UNION-ALL                           |                       |   127K|
|   3 |    TABLE ACCESS BY INDEX ROWID BATCHED| TS_CDF20396_E         |   115K|
|   4 |     INDEX RANGE SCAN                  | TS_CDF20396_E_LVLPATH |   115K|
|   5 |    NESTED LOOPS                       |                       |    22 |
|   6 |     NESTED LOOPS                      |                       |    44 |
|   7 |      JSONTABLE EVALUATION             |                       |       |
|   8 |      INDEX UNIQUE SCAN                | TS_CDF20396_E_PATH    |     1 |
|   9 |     TABLE ACCESS BY INDEX ROWID       | TS_CDF20396_E         |     1 |
|  10 |    NESTED LOOPS                       |                       | 12661 |
|  11 |     NESTED LOOPS                      |                       | 45584 |
|  12 |      JSONTABLE EVALUATION             |                       |       |
|  13 |      INDEX RANGE SCAN                 | TS_CDF20396_E_PATH    |  1036 |
|  14 |     TABLE ACCESS BY INDEX ROWID       | TS_CDF20396_E         |   288 |
|  15 |    TABLE ACCESS BY INDEX ROWID BATCHED| TS_CDF20396_E         |    11 |
|  16 |     INDEX RANGE SCAN                  | TS_CDF20396_E_OWNER   |    22 |
-------------------------------------------------------------------------------
```

**oracle_cardinality=True, oracle_one_index=True, oracle_derived_nl=False / count**

```
 
----------------------------------------------------------------------------------
| Id  | Operation                                | Name                  | Rows  |
----------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                         |                       |     1 |
|   1 |  SORT AGGREGATE                          |                       |     1 |
|   2 |   HASH JOIN                              |                       |   127K|
|   3 |    INDEX FAST FULL SCAN                  | TS_CDF20396_C_ENTRY   |   220K|
|   4 |    VIEW                                  |                       |   127K|
|   5 |     HASH UNIQUE                          |                       |   127K|
|   6 |      UNION-ALL                           |                       |   127K|
|   7 |       TABLE ACCESS BY INDEX ROWID BATCHED| TS_CDF20396_E         |   115K|
|   8 |        INDEX RANGE SCAN                  | TS_CDF20396_E_LVLPATH |   115K|
|   9 |       NESTED LOOPS                       |                       |    22 |
|  10 |        NESTED LOOPS                      |                       |    44 |
|  11 |         JSONTABLE EVALUATION             |                       |       |
|  12 |         INDEX UNIQUE SCAN                | TS_CDF20396_E_PATH    |     1 |
|  13 |        TABLE ACCESS BY INDEX ROWID       | TS_CDF20396_E         |     1 |
|  14 |       NESTED LOOPS                       |                       | 12661 |
|  15 |        NESTED LOOPS                      |                       | 45584 |
|  16 |         JSONTABLE EVALUATION             |                       |       |
|  17 |         INDEX RANGE SCAN                 | TS_CDF20396_E_PATH    |  1036 |
|  18 |        TABLE ACCESS BY INDEX ROWID       | TS_CDF20396_E         |   288 |
|  19 |       TABLE ACCESS BY INDEX ROWID BATCHED| TS_CDF20396_E         |    11 |
|  20 |        INDEX RANGE SCAN                  | TS_CDF20396_E_OWNER   |    22 |
----------------------------------------------------------------------------------
```

**oracle_cardinality=True, oracle_one_index=True, oracle_derived_nl=True / entries**

```
 
-------------------------------------------------------------------------------
| Id  | Operation                             | Name                  | Rows  |
-------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                      |                       |   127K|
|   1 |  HASH UNIQUE                          |                       |   127K|
|   2 |   UNION-ALL                           |                       |   127K|
|   3 |    TABLE ACCESS BY INDEX ROWID BATCHED| TS_CDF20396_E         |   115K|
|   4 |     INDEX RANGE SCAN                  | TS_CDF20396_E_LVLPATH |   115K|
|   5 |    NESTED LOOPS                       |                       |    22 |
|   6 |     NESTED LOOPS                      |                       |    44 |
|   7 |      JSONTABLE EVALUATION             |                       |       |
|   8 |      INDEX UNIQUE SCAN                | TS_CDF20396_E_PATH    |     1 |
|   9 |     TABLE ACCESS BY INDEX ROWID       | TS_CDF20396_E         |     1 |
|  10 |    NESTED LOOPS                       |                       | 12661 |
|  11 |     NESTED LOOPS                      |                       | 45584 |
|  12 |      JSONTABLE EVALUATION             |                       |       |
|  13 |      INDEX RANGE SCAN                 | TS_CDF20396_E_PATH    |  1036 |
|  14 |     TABLE ACCESS BY INDEX ROWID       | TS_CDF20396_E         |   288 |
|  15 |    TABLE ACCESS BY INDEX ROWID BATCHED| TS_CDF20396_E         |    11 |
|  16 |     INDEX RANGE SCAN                  | TS_CDF20396_E_OWNER   |    22 |
-------------------------------------------------------------------------------
```

**oracle_cardinality=True, oracle_one_index=True, oracle_derived_nl=True / count**

```
 
----------------------------------------------------------------------------------
| Id  | Operation                                | Name                  | Rows  |
----------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                         |                       |     1 |
|   1 |  SORT AGGREGATE                          |                       |     1 |
|   2 |   NESTED LOOPS                           |                       |   127K|
|   3 |    VIEW                                  |                       |   127K|
|   4 |     HASH UNIQUE                          |                       |   127K|
|   5 |      UNION-ALL                           |                       |   127K|
|   6 |       TABLE ACCESS BY INDEX ROWID BATCHED| TS_CDF20396_E         |   115K|
|   7 |        INDEX RANGE SCAN                  | TS_CDF20396_E_LVLPATH |   115K|
|   8 |       NESTED LOOPS                       |                       |    22 |
|   9 |        NESTED LOOPS                      |                       |    44 |
|  10 |         JSONTABLE EVALUATION             |                       |       |
|  11 |         INDEX UNIQUE SCAN                | TS_CDF20396_E_PATH    |     1 |
|  12 |        TABLE ACCESS BY INDEX ROWID       | TS_CDF20396_E         |     1 |
|  13 |       NESTED LOOPS                       |                       | 12661 |
|  14 |        NESTED LOOPS                      |                       | 45584 |
|  15 |         JSONTABLE EVALUATION             |                       |       |
|  16 |         INDEX RANGE SCAN                 | TS_CDF20396_E_PATH    |  1036 |
|  17 |        TABLE ACCESS BY INDEX ROWID       | TS_CDF20396_E         |   288 |
|  18 |       TABLE ACCESS BY INDEX ROWID BATCHED| TS_CDF20396_E         |    11 |
|  19 |        INDEX RANGE SCAN                  | TS_CDF20396_E_OWNER   |    22 |
|  20 |    INDEX RANGE SCAN                      | TS_CDF20396_C_ENTRY   |     1 |
----------------------------------------------------------------------------------
```

**oracle_cardinality=False, oracle_one_index=False, oracle_derived_nl=False, oracle_leading=True / entries**

```
 
-------------------------------------------------------------------------------
| Id  | Operation                               | Name                | Rows  |
-------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                        |                     |  2469K|
|   1 |  HASH UNIQUE                            |                     |  2469K|
|   2 |   UNION-ALL                             |                     |  2469K|
|   3 |    TABLE ACCESS FULL                    | TS_CDF20396_E       |   115K|
|   4 |    MERGE JOIN                           |                     |  4084 |
|   5 |     TABLE ACCESS BY INDEX ROWID         | TS_CDF20396_E       |   115K|
|   6 |      INDEX FULL SCAN                    | TS_CDF20396_E_PATH  |   230K|
|   7 |     SORT JOIN                           |                     |  8168 |
|   8 |      JSONTABLE EVALUATION               |                     |       |
|   9 |    MERGE JOIN                           |                     |  2350K|
|  10 |     SORT JOIN                           |                     |   115K|
|  11 |      TABLE ACCESS BY INDEX ROWID BATCHED| TS_CDF20396_E       |   115K|
|  12 |       INDEX FULL SCAN                   | TS_CDF20396_E_PATH  |   230K|
|  13 |     FILTER                              |                     |       |
|  14 |      SORT JOIN                          |                     |  8168 |
|  15 |       JSONTABLE EVALUATION              |                     |       |
|  16 |    TABLE ACCESS BY INDEX ROWID BATCHED  | TS_CDF20396_E       |    11 |
|  17 |     INDEX RANGE SCAN                    | TS_CDF20396_E_OWNER |    22 |
-------------------------------------------------------------------------------
```

**oracle_cardinality=False, oracle_one_index=False, oracle_derived_nl=False, oracle_leading=True / count**

```
 
----------------------------------------------------------------------------------
| Id  | Operation                                  | Name                | Rows  |
----------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                           |                     |     1 |
|   1 |  SORT AGGREGATE                            |                     |     1 |
|   2 |   HASH JOIN                                |                     |  2469K|
|   3 |    INDEX FAST FULL SCAN                    | TS_CDF20396_C_ENTRY |   220K|
|   4 |    VIEW                                    |                     |  2469K|
|   5 |     HASH UNIQUE                            |                     |  2469K|
|   6 |      UNION-ALL                             |                     |  2469K|
|   7 |       TABLE ACCESS FULL                    | TS_CDF20396_E       |   115K|
|   8 |       MERGE JOIN                           |                     |  4084 |
|   9 |        TABLE ACCESS BY INDEX ROWID         | TS_CDF20396_E       |   115K|
|  10 |         INDEX FULL SCAN                    | TS_CDF20396_E_PATH  |   230K|
|  11 |        SORT JOIN                           |                     |  8168 |
|  12 |         JSONTABLE EVALUATION               |                     |       |
|  13 |       MERGE JOIN                           |                     |  2350K|
|  14 |        SORT JOIN                           |                     |   115K|
|  15 |         TABLE ACCESS BY INDEX ROWID BATCHED| TS_CDF20396_E       |   115K|
|  16 |          INDEX FULL SCAN                   | TS_CDF20396_E_PATH  |   230K|
|  17 |        FILTER                              |                     |       |
|  18 |         SORT JOIN                          |                     |  8168 |
|  19 |          JSONTABLE EVALUATION              |                     |       |
|  20 |       TABLE ACCESS BY INDEX ROWID BATCHED  | TS_CDF20396_E       |    11 |
|  21 |        INDEX RANGE SCAN                    | TS_CDF20396_E_OWNER |    22 |
----------------------------------------------------------------------------------
```

