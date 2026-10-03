## mariadb — N=1,000 users: 23,113 entries, 66,000 chunks (3/file), 1,140 grant rows, 1,101 posture rows, 100 sibling traps

Load (tables, rows, indexes, statistics): 1s.

### Indexes

| index | size |
|---|---|
| `path` | 1.6 MB |
| `owner` | 1.6 MB |
| `lvlpath` | 1.6 MB |
| (entries table) | 1.6 MB |

### Callers

| caller | subjects | pieces (arms + owner) | bind bytes | compile us | visible entries |
|---|---|---|---|---|---|
| ordinary | u000042 | 22 | 630 | 53 | 2,034 |
| heavy group | u000000 | 22 | 630 | 34 | 2,034 |
| two subjects | u000042, u000000 | 64 | 1,804 | 71 | 2,013 |
| anonymous | — | 0 | 0 | 0 | 2,013 |
| system | — | 0 | 0 | 0 | 23,113 |

### Statements — cold = fresh connection, warm = median of 1 (ms); recall against the Python truth

Shapes: union, unionall, literal, disjoint. A blank cell is a shape that does not apply to that caller.

| caller | statement | union: cold / warm / recall | unionall: cold / warm / recall | literal: cold / warm / recall | disjoint: cold / warm / recall |
|---|---|---|---|---|---|
| ordinary | entries | 27.5 / 27.2 / exact | 39.0 / 23.0 / exact | 13.5 / 13.2 / exact | 20.9 / 20.8 / exact |
| ordinary | scoped | 1.9 / 1.6 / exact | 1.8 / 1.6 / exact | 2.0 / 2.0 / exact | 2.3 / 2.0 / exact |
| ordinary | count | 27.7 / 27.6 / exact | 28.8 / 29.6 / exact | 10.4 / 10.8 / exact | 28.8 / 28.1 / exact |
| ordinary | top10 | 19.2 / 19.7 / exact | 19.7 / 24.3 / exact | 1.8 / 1.0 / exact | 19.7 / 20.1 / exact |
| heavy group | entries | 27.0 / 30.0 / exact | 22.7 / 27.0 / exact | 16.7 / 20.3 / exact | 19.9 / 21.9 / exact |
| heavy group | scoped | 1.9 / 2.3 / exact | 1.9 / 1.6 / exact | 3.6 / 1.7 / exact | 3.2 / 2.6 / exact |
| heavy group | count | 28.9 / 28.9 / exact | 28.5 / 27.9 / exact | 11.8 / 11.7 / exact | 28.7 / 29.2 / exact |
| heavy group | top10 | 21.0 / 22.7 / exact | 19.7 / 19.4 / exact | 1.5 / 1.2 / exact | 19.7 / 20.2 / exact |
| two subjects | entries | 21.5 / 21.5 / exact | 21.3 / 20.6 / exact | 13.8 / 13.1 / exact | 19.1 / 18.5 / exact |
| two subjects | scoped | 2.3 / 1.9 / exact | 2.2 / 2.0 / exact | 2.3 / 1.6 / exact | 3.7 / 3.4 / exact |
| two subjects | count | 28.3 / 26.1 / exact | 25.9 / 26.1 / exact | 12.7 / 11.0 / exact | 28.6 / 28.1 / exact |
| two subjects | top10 | 18.8 / 18.3 / exact | 18.4 / 17.8 / exact | 4.3 / 2.1 / exact | 19.7 / 18.2 / exact |
| anonymous | entries | 5.0 / 5.2 / exact |  |  |  |
| anonymous | scoped | 1.5 / 1.2 / exact |  |  |  |
| anonymous | count | 2.7 / 2.2 / exact |  |  |  |
| anonymous | top10 | 4.9 / 4.9 / exact |  |  |  |
| system | entries | 44.6 / 44.4 / exact |  |  |  |
| system | scoped | 1.4 / 1.1 / exact |  |  |  |
| system | count | 18.3 / 18.6 / exact |  |  |  |
| system | top10 | 1.1 / 0.9 / exact |  |  |  |

### Scoped read, branch 1 spelled `everyone_level >= :r` against `everyone_level IN (...)`

| caller | shape | `>=` cold / warm | `IN` cold / warm | recall |
|---|---|---|---|---|
| anonymous | union | 1.4 / 1.3 | 1.1 / 0.9 | exact |
| ordinary | union | 2.1 / 1.6 | 2.0 / 1.5 | exact |
| ordinary | unionall | 2.0 / 1.8 | 1.8 / 1.7 | exact |
| ordinary | literal | 1.6 / 1.5 | 1.7 / 1.5 | exact |
| ordinary | disjoint | 2.1 / 2.1 | 2.4 / 2.1 | exact |

### Plans

**ordinary / union / entries**

```
PRIMARY e type=range key=ts_9b757ff5_e_lvlpath rows=2013 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_9b757ff5_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=index key=ts_9b757ff5_e_lvlpath rows=22612 Using where; Using index; Using join buffer (flat, BNL join)
UNION e type=ref key=ts_9b757ff5_e_owner rows=24 Using index condition; Using where
UNION RESULT <union1,2,3,4> type=ALL key=None rows=None
```

**ordinary / unionall / entries**

```
PRIMARY e type=range key=ts_9b757ff5_e_lvlpath rows=2013 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_9b757ff5_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=index key=ts_9b757ff5_e_lvlpath rows=22612 Using where; Using index; Using join buffer (flat, BNL join)
UNION e type=ref key=ts_9b757ff5_e_owner rows=24 Using index condition; Using where
UNION RESULT <union1,2,3,4> type=ALL key=None rows=None
```

**ordinary / literal / entries**

```
SIMPLE e type=ALL key=None rows=22612 Using where
```

**ordinary / disjoint / entries**

```
PRIMARY e type=range key=ts_9b757ff5_e_lvlpath rows=2013 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_9b757ff5_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=index key=ts_9b757ff5_e_lvlpath rows=22612 Using where; Using index; Using join buffer (flat, BNL join)
UNION e type=ref key=ts_9b757ff5_e_owner rows=24 Using index condition; Using where
DEPENDENT SUBQUERY x0r type=ALL key=None rows=40 Table function: json_table; Using where
DEPENDENT SUBQUERY x0p type=ALL key=None rows=40 Table function: json_table; Using where
```

**ordinary / union / scoped**

```
PRIMARY e type=range key=ts_9b757ff5_e_path rows=200 Using index condition; Using where
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_9b757ff5_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=range key=ts_9b757ff5_e_path rows=200 Using index condition; Using where; Using join buffer (flat, BNL join)
UNION e type=ref key=ts_9b757ff5_e_owner rows=24 Using index condition; Using where
UNION RESULT <union1,2,3,4> type=ALL key=None rows=None
```

**ordinary / unionall / scoped**

```
PRIMARY e type=range key=ts_9b757ff5_e_path rows=200 Using index condition; Using where
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_9b757ff5_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=range key=ts_9b757ff5_e_path rows=200 Using index condition; Using where; Using join buffer (flat, BNL join)
UNION e type=ref key=ts_9b757ff5_e_owner rows=24 Using index condition; Using where
UNION RESULT <union1,2,3,4> type=ALL key=None rows=None
```

**ordinary / literal / scoped**

```
SIMPLE e type=range key=ts_9b757ff5_e_path rows=200 Using index condition; Using where
```

**ordinary / disjoint / scoped**

```
PRIMARY e type=range key=ts_9b757ff5_e_path rows=200 Using index condition; Using where
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_9b757ff5_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=range key=ts_9b757ff5_e_path rows=200 Using index condition; Using where; Using join buffer (flat, BNL join)
UNION e type=ref key=ts_9b757ff5_e_owner rows=24 Using index condition; Using where
DEPENDENT SUBQUERY x0r type=ALL key=None rows=40 Table function: json_table; Using where
DEPENDENT SUBQUERY x0p type=ALL key=None rows=40 Table function: json_table; Using where
```

**ordinary / union / count**

```
PRIMARY c type=index key=ts_9b757ff5_c_entry rows=66192 Using index
PRIMARY <derived2> type=eq_ref key=distinct_key rows=1
DERIVED e type=range key=ts_9b757ff5_e_lvlpath rows=2013 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_9b757ff5_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=index key=ts_9b757ff5_e_lvlpath rows=22612 Using where; Using index; Using join buffer (flat, BNL join)
UNION e type=ref key=ts_9b757ff5_e_owner rows=24 Using index condition; Using where
UNION RESULT <union2,3,4,5> type=ALL key=None rows=None
```

**ordinary / unionall / count**

```
PRIMARY c type=index key=ts_9b757ff5_c_entry rows=66192 Using index
PRIMARY <derived2> type=eq_ref key=distinct_key rows=1
DERIVED e type=range key=ts_9b757ff5_e_lvlpath rows=2013 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_9b757ff5_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=index key=ts_9b757ff5_e_lvlpath rows=22612 Using where; Using index; Using join buffer (flat, BNL join)
UNION e type=ref key=ts_9b757ff5_e_owner rows=24 Using index condition; Using where
UNION RESULT <union2,3,4,5> type=ALL key=None rows=None
```

**ordinary / literal / count**

```
SIMPLE e type=ALL key=None rows=22612 Using where
SIMPLE c type=ref key=ts_9b757ff5_c_entry rows=2 Using index
```

**ordinary / disjoint / count**

```
PRIMARY c type=index key=ts_9b757ff5_c_entry rows=66192 Using index
PRIMARY <derived2> type=ref key=key0 rows=13
DERIVED e type=range key=ts_9b757ff5_e_lvlpath rows=2013 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_9b757ff5_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=index key=ts_9b757ff5_e_lvlpath rows=22612 Using where; Using index; Using join buffer (flat, BNL join)
UNION e type=ref key=ts_9b757ff5_e_owner rows=24 Using index condition; Using where
DEPENDENT SUBQUERY x0r type=ALL key=None rows=40 Table function: json_table; Using where
DEPENDENT SUBQUERY x0p type=ALL key=None rows=40 Table function: json_table; Using where
```

**ordinary / union / top10**

```
PRIMARY c type=index key=ts_9b757ff5_c_score rows=10
PRIMARY <derived2> type=eq_ref key=distinct_key rows=1
DERIVED e type=range key=ts_9b757ff5_e_lvlpath rows=2013 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_9b757ff5_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=index key=ts_9b757ff5_e_lvlpath rows=22612 Using where; Using index; Using join buffer (flat, BNL join)
UNION e type=ref key=ts_9b757ff5_e_owner rows=24 Using index condition; Using where
UNION RESULT <union2,3,4,5> type=ALL key=None rows=None
```

**ordinary / unionall / top10**

```
PRIMARY c type=index key=ts_9b757ff5_c_score rows=10
PRIMARY <derived2> type=eq_ref key=distinct_key rows=1
DERIVED e type=range key=ts_9b757ff5_e_lvlpath rows=2013 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_9b757ff5_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=index key=ts_9b757ff5_e_lvlpath rows=22612 Using where; Using index; Using join buffer (flat, BNL join)
UNION e type=ref key=ts_9b757ff5_e_owner rows=24 Using index condition; Using where
UNION RESULT <union2,3,4,5> type=ALL key=None rows=None
```

**ordinary / literal / top10**

```
SIMPLE c type=index key=ts_9b757ff5_c_score rows=10
SIMPLE e type=eq_ref key=PRIMARY rows=1 Using where
```

**ordinary / disjoint / top10**

```
PRIMARY c type=index key=ts_9b757ff5_c_score rows=1
PRIMARY <derived2> type=ref key=key0 rows=13
DERIVED e type=range key=ts_9b757ff5_e_lvlpath rows=2013 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_9b757ff5_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=index key=ts_9b757ff5_e_lvlpath rows=22612 Using where; Using index; Using join buffer (flat, BNL join)
UNION e type=ref key=ts_9b757ff5_e_owner rows=24 Using index condition; Using where
DEPENDENT SUBQUERY x0r type=ALL key=None rows=40 Table function: json_table; Using where
DEPENDENT SUBQUERY x0p type=ALL key=None rows=40 Table function: json_table; Using where
```

**two subjects / union / entries**

```
PRIMARY e type=range key=ts_9b757ff5_e_lvlpath rows=2013 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_9b757ff5_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=index key=ts_9b757ff5_e_lvlpath rows=22612 Using where; Using index; Using join buffer (flat, BNL join)
UNION o0p type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref|filter key=ts_9b757ff5_e_path|ts_9b757ff5_e_owner rows=1 (0%) Using index condition; Using where; Using rowid filter
UNION e type=ref key=ts_9b757ff5_e_owner rows=24 Using index condition; Using where
UNION o0r type=ALL key=None rows=40 Table function: json_table; Using where; Using join buffer (flat, BNL join)
UNION o1p type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref|filter key=ts_9b757ff5_e_path|ts_9b757ff5_e_owner rows=1 (0%) Using index condition; Using where; Using rowid filter
UNION e type=ref key=ts_9b757ff5_e_owner rows=23 Using index condition; Using where
UNION o1r type=ALL key=None rows=40 Table function: json_table; Using where; Using join buffer (flat, BNL join)
UNION RESULT <union1,2,3,4,5,6,7> type=ALL key=None rows=None
```

**two subjects / unionall / entries**

```
PRIMARY e type=range key=ts_9b757ff5_e_lvlpath rows=2013 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_9b757ff5_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=index key=ts_9b757ff5_e_lvlpath rows=22612 Using where; Using index; Using join buffer (flat, BNL join)
UNION o0p type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref|filter key=ts_9b757ff5_e_path|ts_9b757ff5_e_owner rows=1 (0%) Using index condition; Using where; Using rowid filter
UNION e type=ref key=ts_9b757ff5_e_owner rows=24 Using index condition; Using where
UNION o0r type=ALL key=None rows=40 Table function: json_table; Using where; Using join buffer (flat, BNL join)
UNION o1p type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref|filter key=ts_9b757ff5_e_path|ts_9b757ff5_e_owner rows=1 (0%) Using index condition; Using where; Using rowid filter
UNION e type=ref key=ts_9b757ff5_e_owner rows=23 Using index condition; Using where
UNION o1r type=ALL key=None rows=40 Table function: json_table; Using where; Using join buffer (flat, BNL join)
UNION RESULT <union1,2,3,4,5,6,7> type=ALL key=None rows=None
```

**two subjects / literal / entries**

```
SIMPLE e type=ALL key=None rows=22612 Using where
```

**two subjects / disjoint / entries**

```
PRIMARY e type=range key=ts_9b757ff5_e_lvlpath rows=2013 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_9b757ff5_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=index key=ts_9b757ff5_e_lvlpath rows=22612 Using where; Using index; Using join buffer (flat, BNL join)
UNION o0p type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref|filter key=ts_9b757ff5_e_path|ts_9b757ff5_e_owner rows=1 (0%) Using index condition; Using where; Using rowid filter
DEPENDENT SUBQUERY x0r type=ALL key=None rows=40 Table function: json_table; Using where
DEPENDENT SUBQUERY x0p type=ALL key=None rows=40 Table function: json_table; Using where
UNION e type=ref key=ts_9b757ff5_e_owner rows=24 Using index condition; Using where
UNION o0r type=ALL key=None rows=40 Table function: json_table; Using where; Using join buffer (flat, BNL join)
DEPENDENT SUBQUERY x0r type=ALL key=None rows=40 Table function: json_table; Using where
DEPENDENT SUBQUERY x0p type=ALL key=None rows=40 Table function: json_table; Using where
UNION o1p type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref|filter key=ts_9b757ff5_e_path|ts_9b757ff5_e_owner rows=1 (0%) Using index condition; Using where; Using rowid filter
DEPENDENT SUBQUERY x1r type=ALL key=None rows=40 Table function: json_table; Using where
DEPENDENT SUBQUERY x1p type=ALL key=None rows=40 Table function: json_table; Using where
UNION e type=ref key=ts_9b757ff5_e_owner rows=23 Using index condition; Using where
UNION o1r type=ALL key=None rows=40 Table function: json_table; Using where; Using join buffer (flat, BNL join)
DEPENDENT SUBQUERY x1r type=ALL key=None rows=40 Table function: json_table; Using where
DEPENDENT SUBQUERY x1p type=ALL key=None rows=40 Table function: json_table; Using where
```

**scoped / anonymous / union / IN**

```
SIMPLE e type=range key=ts_9b757ff5_e_lvlpath rows=201 Using where; Using index
```

**scoped / anonymous / union / >=**

```
SIMPLE e type=range key=ts_9b757ff5_e_path rows=200 Using index condition; Using where
```

**scoped / ordinary / union / IN**

```
PRIMARY e type=range key=ts_9b757ff5_e_lvlpath rows=201 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_9b757ff5_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=range key=ts_9b757ff5_e_path rows=200 Using index condition; Using where; Using join buffer (flat, BNL join)
UNION e type=ref key=ts_9b757ff5_e_owner rows=24 Using index condition; Using where
UNION RESULT <union1,2,3,4> type=ALL key=None rows=None
```

**scoped / ordinary / unionall / IN**

```
PRIMARY e type=range key=ts_9b757ff5_e_lvlpath rows=201 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_9b757ff5_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=range key=ts_9b757ff5_e_path rows=200 Using index condition; Using where; Using join buffer (flat, BNL join)
UNION e type=ref key=ts_9b757ff5_e_owner rows=24 Using index condition; Using where
UNION RESULT <union1,2,3,4> type=ALL key=None rows=None
```

**scoped / ordinary / literal / IN**

```
SIMPLE e type=range key=ts_9b757ff5_e_path rows=200 Using index condition; Using where
```

**scoped / ordinary / disjoint / IN**

```
PRIMARY e type=range key=ts_9b757ff5_e_lvlpath rows=201 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_9b757ff5_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=range key=ts_9b757ff5_e_path rows=200 Using index condition; Using where; Using join buffer (flat, BNL join)
UNION e type=ref key=ts_9b757ff5_e_owner rows=24 Using index condition; Using where
DEPENDENT SUBQUERY x0r type=ALL key=None rows=40 Table function: json_table; Using where
DEPENDENT SUBQUERY x0p type=ALL key=None rows=40 Table function: json_table; Using where
```

Total wall time 3s.
