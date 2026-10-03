## mariadb — N=10,000 users: 230,203 entries, 660,000 chunks (3/file), 11,400 grant rows, 10,101 posture rows, 100 sibling traps

Load (tables, rows, indexes, statistics): 12s.

### Indexes

| index | size |
|---|---|
| `path` | 10.0 MB |
| `owner` | 11.0 MB |
| `lvlpath` | 10.0 MB |
| (entries table) | 15.3 MB |

### Callers

| caller | subjects | pieces (arms + owner) | bind bytes | compile us | visible entries |
|---|---|---|---|---|---|
| ordinary | u000042 | 88 | 2,445 | 86 | 20,124 |
| heavy group | u000003 | 88 | 2,445 | 40 | 20,124 |
| two subjects | u000042, u000032 | 220 | 6,094 | 116 | 20,103 |
| anonymous | — | 0 | 0 | 0 | 20,103 |
| system | — | 0 | 0 | 0 | 230,203 |

### Statements — cold = fresh connection, warm = median of 3 (ms); recall against the Python truth

Shapes: union, unionall, literal, disjoint. A blank cell is a shape that does not apply to that caller.

| caller | statement | union: cold / warm / recall | unionall: cold / warm / recall | literal: cold / warm / recall | disjoint: cold / warm / recall |
|---|---|---|---|---|---|
| ordinary | entries | 135 / 98.9 / exact | 191 / 79.6 / exact | 276 / 311 / exact | 80.6 / 84.1 / exact |
| ordinary | scoped | 18.8 / 10.9 / exact | 7.6 / 9.9 / exact | 11.6 / 10.8 / exact | 15.2 / 6.5 / exact |
| ordinary | count | 190 / 128 / exact | 122 / 142 / exact | 252 / 347 / exact | 279 / 136 / exact |
| ordinary | top10 | 21.3 / 42.2 / exact | 38.6 / 39.5 / exact | 5.5 / 7.1 / exact | 49.5 / 19.6 / exact |
| heavy group | entries | 123 / 79.5 / exact | 83.5 / 165 / exact | 344 / 384 / exact | 63.8 / 51.8 / exact |
| heavy group | scoped | 14.0 / 17.3 / exact | 17.8 / 8.1 / exact | 21.8 / 6.3 / exact | 18.3 / 11.7 / exact |
| heavy group | count | 169 / 182 / exact | 157 / 171 / exact | 304 / 265 / exact | 108 / 105 / exact |
| heavy group | top10 | 17.4 / 30.6 / exact | 27.8 / 36.6 / exact | 9.9 / 20.2 / exact | 24.2 / 22.4 / exact |
| two subjects | entries | 95.5 / 97.1 / exact | 143 / 96.4 / exact | 266 / 275 / exact | 106 / 67.6 / exact |
| two subjects | scoped | 4.2 / 4.7 / exact | 7.3 / 4.5 / exact | 7.5 / 4.5 / exact | 7.3 / 4.8 / exact |
| two subjects | count | 136 / 111 / exact | 114 / 174 / exact | 176 / 203 / exact | 176 / 140 / exact |
| two subjects | top10 | 41.9 / 41.9 / exact | 40.7 / 40.3 / exact | 12.7 / 26.7 / exact | 39.4 / 42.6 / exact |
| anonymous | entries | 84.7 / 51.5 / exact |  |  |  |
| anonymous | scoped | 3.0 / 3.9 / exact |  |  |  |
| anonymous | count | 19.6 / 19.9 / exact |  |  |  |
| anonymous | top10 | 51.1 / 47.8 / exact |  |  |  |
| system | entries | 593 / 777 / exact |  |  |  |
| system | scoped | 13.6 / 6.1 / exact |  |  |  |
| system | count | 306 / 193 / exact |  |  |  |
| system | top10 | 1.1 / 1.0 / exact |  |  |  |

### Scoped read, branch 1 spelled `everyone_level >= :r` against `everyone_level IN (...)`

| caller | shape | `>=` cold / warm | `IN` cold / warm | recall |
|---|---|---|---|---|
| anonymous | union | 1.6 / 1.6 | 1.5 / 1.6 | exact |
| ordinary | union | 2.0 / 2.2 | 2.3 / 2.0 | exact |
| ordinary | unionall | 2.2 / 2.3 | 2.2 / 2.0 | exact |
| ordinary | literal | 2.8 / 2.7 | 3.5 / 2.7 | exact |
| ordinary | disjoint | 2.9 / 2.6 | 4.3 / 3.2 | exact |

### Plans

**ordinary / union / entries**

```
PRIMARY e type=range key=ts_ef1eb7a3_e_lvlpath rows=41136 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_ef1eb7a3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=229610 Range checked for each record (index map: 0x2)
UNION e type=ref key=ts_ef1eb7a3_e_owner rows=24 Using index condition; Using where
UNION RESULT <union1,2,3,4> type=ALL key=None rows=None
```

**ordinary / unionall / entries**

```
PRIMARY e type=range key=ts_ef1eb7a3_e_lvlpath rows=41136 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_ef1eb7a3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=229610 Range checked for each record (index map: 0x2)
UNION e type=ref key=ts_ef1eb7a3_e_owner rows=24 Using index condition; Using where
UNION RESULT <union1,2,3,4> type=ALL key=None rows=None
```

**ordinary / literal / entries**

```
SIMPLE e type=ALL key=None rows=229610 Using where
```

**ordinary / disjoint / entries**

```
PRIMARY e type=range key=ts_ef1eb7a3_e_lvlpath rows=41136 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_ef1eb7a3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=229610 Range checked for each record (index map: 0x2)
UNION e type=ref key=ts_ef1eb7a3_e_owner rows=24 Using index condition; Using where
DEPENDENT SUBQUERY x0r type=ALL key=None rows=40 Table function: json_table; Using where
DEPENDENT SUBQUERY x0p type=ALL key=None rows=40 Table function: json_table; Using where
```

**ordinary / union / scoped**

```
PRIMARY e type=range key=ts_ef1eb7a3_e_path rows=200 Using index condition; Using where
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_ef1eb7a3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=range key=ts_ef1eb7a3_e_path rows=200 Using index condition; Using where; Using join buffer (flat, BNL join)
UNION e type=ref key=ts_ef1eb7a3_e_owner rows=24 Using index condition; Using where
UNION RESULT <union1,2,3,4> type=ALL key=None rows=None
```

**ordinary / unionall / scoped**

```
PRIMARY e type=range key=ts_ef1eb7a3_e_path rows=200 Using index condition; Using where
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_ef1eb7a3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=range key=ts_ef1eb7a3_e_path rows=200 Using index condition; Using where; Using join buffer (flat, BNL join)
UNION e type=ref key=ts_ef1eb7a3_e_owner rows=24 Using index condition; Using where
UNION RESULT <union1,2,3,4> type=ALL key=None rows=None
```

**ordinary / literal / scoped**

```
SIMPLE e type=range key=ts_ef1eb7a3_e_path rows=200 Using index condition; Using where
```

**ordinary / disjoint / scoped**

```
PRIMARY e type=range key=ts_ef1eb7a3_e_path rows=200 Using index condition; Using where
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_ef1eb7a3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=range key=ts_ef1eb7a3_e_path rows=200 Using index condition; Using where; Using join buffer (flat, BNL join)
UNION e type=ref key=ts_ef1eb7a3_e_owner rows=24 Using index condition; Using where
DEPENDENT SUBQUERY x0r type=ALL key=None rows=40 Table function: json_table; Using where
DEPENDENT SUBQUERY x0p type=ALL key=None rows=40 Table function: json_table; Using where
```

**ordinary / union / count**

```
PRIMARY c type=index key=ts_ef1eb7a3_c_entry rows=658768 Using index
PRIMARY <derived2> type=eq_ref key=distinct_key rows=1
DERIVED e type=range key=ts_ef1eb7a3_e_lvlpath rows=41136 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_ef1eb7a3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=229610 Range checked for each record (index map: 0x2)
UNION e type=ref key=ts_ef1eb7a3_e_owner rows=24 Using index condition; Using where
UNION RESULT <union2,3,4,5> type=ALL key=None rows=None
```

**ordinary / unionall / count**

```
PRIMARY c type=index key=ts_ef1eb7a3_c_entry rows=658768 Using index
PRIMARY <derived2> type=eq_ref key=distinct_key rows=1
DERIVED e type=range key=ts_ef1eb7a3_e_lvlpath rows=41136 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_ef1eb7a3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=229610 Range checked for each record (index map: 0x2)
UNION e type=ref key=ts_ef1eb7a3_e_owner rows=24 Using index condition; Using where
UNION RESULT <union2,3,4,5> type=ALL key=None rows=None
```

**ordinary / literal / count**

```
SIMPLE e type=ALL key=None rows=229610 Using where
SIMPLE c type=ref key=ts_ef1eb7a3_c_entry rows=2 Using index
```

**ordinary / disjoint / count**

```
PRIMARY c type=index key=ts_ef1eb7a3_c_entry rows=658768 Using index
PRIMARY <derived2> type=ref key=key0 rows=14
DERIVED e type=range key=ts_ef1eb7a3_e_lvlpath rows=41136 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_ef1eb7a3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=229610 Range checked for each record (index map: 0x2)
UNION e type=ref key=ts_ef1eb7a3_e_owner rows=24 Using index condition; Using where
DEPENDENT SUBQUERY x0r type=ALL key=None rows=40 Table function: json_table; Using where
DEPENDENT SUBQUERY x0p type=ALL key=None rows=40 Table function: json_table; Using where
```

**ordinary / union / top10**

```
PRIMARY c type=index key=ts_ef1eb7a3_c_score rows=10
PRIMARY <derived2> type=eq_ref key=distinct_key rows=1
DERIVED e type=range key=ts_ef1eb7a3_e_lvlpath rows=41136 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_ef1eb7a3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=229610 Range checked for each record (index map: 0x2)
UNION e type=ref key=ts_ef1eb7a3_e_owner rows=24 Using index condition; Using where
UNION RESULT <union2,3,4,5> type=ALL key=None rows=None
```

**ordinary / unionall / top10**

```
PRIMARY c type=index key=ts_ef1eb7a3_c_score rows=10
PRIMARY <derived2> type=eq_ref key=distinct_key rows=1
DERIVED e type=range key=ts_ef1eb7a3_e_lvlpath rows=41136 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_ef1eb7a3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=229610 Range checked for each record (index map: 0x2)
UNION e type=ref key=ts_ef1eb7a3_e_owner rows=24 Using index condition; Using where
UNION RESULT <union2,3,4,5> type=ALL key=None rows=None
```

**ordinary / literal / top10**

```
SIMPLE c type=index key=ts_ef1eb7a3_c_score rows=10
SIMPLE e type=eq_ref key=PRIMARY rows=1 Using where
```

**ordinary / disjoint / top10**

```
PRIMARY c type=index key=ts_ef1eb7a3_c_score rows=1
PRIMARY <derived2> type=ref key=key0 rows=14
DERIVED e type=range key=ts_ef1eb7a3_e_lvlpath rows=41136 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_ef1eb7a3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=229610 Range checked for each record (index map: 0x2)
UNION e type=ref key=ts_ef1eb7a3_e_owner rows=24 Using index condition; Using where
DEPENDENT SUBQUERY x0r type=ALL key=None rows=40 Table function: json_table; Using where
DEPENDENT SUBQUERY x0p type=ALL key=None rows=40 Table function: json_table; Using where
```

**two subjects / union / entries**

```
PRIMARY e type=range key=ts_ef1eb7a3_e_lvlpath rows=41136 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_ef1eb7a3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=229610 Range checked for each record (index map: 0x2)
UNION o0p type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_ef1eb7a3_e_path rows=1 Using index condition; Using where
UNION o0r type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=229610 Range checked for each record (index map: 0x2)
UNION o1p type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_ef1eb7a3_e_path rows=1 Using index condition; Using where
UNION o1r type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=229610 Range checked for each record (index map: 0x2)
UNION RESULT <union1,2,3,4,5,6,7> type=ALL key=None rows=None
```

**two subjects / unionall / entries**

```
PRIMARY e type=range key=ts_ef1eb7a3_e_lvlpath rows=41136 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_ef1eb7a3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=229610 Range checked for each record (index map: 0x2)
UNION o0p type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_ef1eb7a3_e_path rows=1 Using index condition; Using where
UNION o0r type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=229610 Range checked for each record (index map: 0x2)
UNION o1p type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_ef1eb7a3_e_path rows=1 Using index condition; Using where
UNION o1r type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=229610 Range checked for each record (index map: 0x2)
UNION RESULT <union1,2,3,4,5,6,7> type=ALL key=None rows=None
```

**two subjects / literal / entries**

```
SIMPLE e type=ALL key=None rows=229610 Using where
```

**two subjects / disjoint / entries**

```
PRIMARY e type=range key=ts_ef1eb7a3_e_lvlpath rows=41136 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_ef1eb7a3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=229610 Range checked for each record (index map: 0x2)
UNION o0p type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_ef1eb7a3_e_path rows=1 Using index condition; Using where
DEPENDENT SUBQUERY x0r type=ALL key=None rows=40 Table function: json_table; Using where
DEPENDENT SUBQUERY x0p type=ALL key=None rows=40 Table function: json_table; Using where
UNION o0r type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=229610 Range checked for each record (index map: 0x2)
DEPENDENT SUBQUERY x0r type=ALL key=None rows=40 Table function: json_table; Using where
DEPENDENT SUBQUERY x0p type=ALL key=None rows=40 Table function: json_table; Using where
UNION o1p type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_ef1eb7a3_e_path rows=1 Using index condition; Using where
DEPENDENT SUBQUERY x1r type=ALL key=None rows=40 Table function: json_table; Using where
DEPENDENT SUBQUERY x1p type=ALL key=None rows=40 Table function: json_table; Using where
UNION o1r type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=229610 Range checked for each record (index map: 0x2)
DEPENDENT SUBQUERY x1r type=ALL key=None rows=40 Table function: json_table; Using where
DEPENDENT SUBQUERY x1p type=ALL key=None rows=40 Table function: json_table; Using where
```

**scoped / anonymous / union / IN**

```
SIMPLE e type=range key=ts_ef1eb7a3_e_lvlpath rows=201 Using where; Using index
```

**scoped / anonymous / union / >=**

```
SIMPLE e type=range key=ts_ef1eb7a3_e_path rows=200 Using index condition; Using where
```

**scoped / ordinary / union / IN**

```
PRIMARY e type=range key=ts_ef1eb7a3_e_lvlpath rows=201 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_ef1eb7a3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=range key=ts_ef1eb7a3_e_path rows=200 Using index condition; Using where; Using join buffer (flat, BNL join)
UNION e type=ref key=ts_ef1eb7a3_e_owner rows=24 Using index condition; Using where
UNION RESULT <union1,2,3,4> type=ALL key=None rows=None
```

**scoped / ordinary / unionall / IN**

```
PRIMARY e type=range key=ts_ef1eb7a3_e_lvlpath rows=201 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_ef1eb7a3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=range key=ts_ef1eb7a3_e_path rows=200 Using index condition; Using where; Using join buffer (flat, BNL join)
UNION e type=ref key=ts_ef1eb7a3_e_owner rows=24 Using index condition; Using where
UNION RESULT <union1,2,3,4> type=ALL key=None rows=None
```

**scoped / ordinary / literal / IN**

```
SIMPLE e type=range key=ts_ef1eb7a3_e_path rows=200 Using index condition; Using where
```

**scoped / ordinary / disjoint / IN**

```
PRIMARY e type=range key=ts_ef1eb7a3_e_lvlpath rows=201 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_ef1eb7a3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=range key=ts_ef1eb7a3_e_path rows=200 Using index condition; Using where; Using join buffer (flat, BNL join)
UNION e type=ref key=ts_ef1eb7a3_e_owner rows=24 Using index condition; Using where
DEPENDENT SUBQUERY x0r type=ALL key=None rows=40 Table function: json_table; Using where
DEPENDENT SUBQUERY x0p type=ALL key=None rows=40 Table function: json_table; Using where
```

Total wall time 43s.
