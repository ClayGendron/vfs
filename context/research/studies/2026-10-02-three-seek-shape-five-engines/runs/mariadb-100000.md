## mariadb — N=100,000 users: 2,301,103 entries, 2,200,000 chunks (1/file), 114,000 grant rows, 100,101 posture rows, 100 sibling traps

Load (tables, rows, indexes, statistics): 58s.

### Indexes

| index | size |
|---|---|
| `path` | 86.7 MB |
| `owner` | 97.3 MB |
| `lvlpath` | 90.9 MB |
| (entries table) | 146.5 MB |

### Callers

| caller | subjects | pieces (arms + owner) | bind bytes | compile us | visible entries |
|---|---|---|---|---|---|
| ordinary | u000042 | 72 | 2,005 | 98 | 201,024 |
| heavy group | u000039 | 464 | 12,785 | 261 | 201,024 |
| two subjects | u000042, u000044 | 178 | 4,939 | 129 | 201,003 |
| anonymous | — | 0 | 0 | 0 | 201,003 |
| system | — | 0 | 0 | 0 | 2,301,103 |

### Statements — cold = fresh connection, warm = median of 2 (ms); recall against the Python truth

Shapes: union, unionall, literal, disjoint. A blank cell is a shape that does not apply to that caller.

| caller | statement | union: cold / warm / recall | unionall: cold / warm / recall | literal: cold / warm / recall | disjoint: cold / warm / recall |
|---|---|---|---|---|---|
| ordinary | entries | 1,090 / 1,036 / exact | 879 / 847 / exact | 2,604 / 2,922 / exact | 762 / 734 / exact |
| ordinary | scoped | 4.7 / 8.5 / exact | 6.5 / 6.0 / exact | 12.1 / 4.3 / exact | 8.2 / 8.8 / exact |
| ordinary | count | 2,348 / 1,118 / exact | 1,132 / 1,253 / exact | 4,182 / 3,584 / exact | 961 / 872 / exact |
| ordinary | top10 | 207 / 130 / exact | 142 / 125 / exact | 5.3 / 2.8 / exact | 77.7 / 75.9 / exact |
| heavy group | entries | 1,178 / 873 / exact | 736 / 748 / exact | 17,942 / 17,366 / exact | 397 / 664 / exact |
| heavy group | scoped | 6.8 / 4.7 / exact | 4.1 / 3.9 / exact | 9.9 / 4.1 / exact | 6.2 / 5.6 / exact |
| heavy group | count | 1,109 / 884 / exact | 883 / 780 / exact | 18,694 / 17,122 / exact | 800 / 583 / exact |
| heavy group | top10 | 132 / 120 / exact | 120 / 123 / exact | 9.1 / 4.2 / exact | 95.1 / 91.9 / exact |
| two subjects | entries | 942 / 802 / exact | 675 / 702 / exact | 1,448 / 1,597 / exact | 650 / 729 / exact |
| two subjects | scoped | 3.0 / 2.8 / exact | 4.0 / 2.6 / exact | 3.5 / 2.2 / exact | 3.1 / 2.7 / exact |
| two subjects | count | 716 / 662 / exact | 757 / 715 / exact | 2,272 / 2,280 / exact | 933 / 914 / exact |
| two subjects | top10 | 148 / 130 / exact | 148 / 144 / exact | 7.1 / 4.3 / exact | 86.1 / 90.0 / exact |
| anonymous | entries | 436 / 835 / exact |  |  |  |
| anonymous | scoped | 5.9 / 4.9 / exact |  |  |  |
| anonymous | count | 192 / 176 / exact |  |  |  |
| anonymous | top10 | 328 / 262 / exact |  |  |  |
| system | entries | 6,405 / 5,379 / exact |  |  |  |
| system | scoped | 1.6 / 1.3 / exact |  |  |  |
| system | count | 1,900 / 1,522 / exact |  |  |  |
| system | top10 | 1.5 / 0.9 / exact |  |  |  |

### Scoped read, branch 1 spelled `everyone_level >= :r` against `everyone_level IN (...)`

| caller | shape | `>=` cold / warm | `IN` cold / warm | recall |
|---|---|---|---|---|
| anonymous | union | 1.8 / 1.4 | 1.4 / 1.2 | exact |
| ordinary | union | 3.1 / 1.9 | 2.1 / 1.8 | exact |
| ordinary | unionall | 2.1 / 2.1 | 1.9 / 2.0 | exact |
| ordinary | literal | 2.7 / 2.2 | 3.7 / 2.5 | exact |
| ordinary | disjoint | 2.8 / 2.6 | 2.5 / 2.5 | exact |

### Plans

**ordinary / union / entries**

```
PRIMARY e type=range key=ts_6637f6f3_e_lvlpath rows=415988 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_6637f6f3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=2292241 Range checked for each record (index map: 0x2)
UNION e type=ref key=ts_6637f6f3_e_owner rows=21 Using index condition; Using where
UNION RESULT <union1,2,3,4> type=ALL key=None rows=None
```

**ordinary / unionall / entries**

```
PRIMARY e type=range key=ts_6637f6f3_e_lvlpath rows=415988 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_6637f6f3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=2292241 Range checked for each record (index map: 0x2)
UNION e type=ref key=ts_6637f6f3_e_owner rows=21 Using index condition; Using where
UNION RESULT <union1,2,3,4> type=ALL key=None rows=None
```

**ordinary / literal / entries**

```
SIMPLE e type=ALL key=None rows=2292241 Using where
```

**ordinary / disjoint / entries**

```
PRIMARY e type=range key=ts_6637f6f3_e_lvlpath rows=415988 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_6637f6f3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=2292241 Range checked for each record (index map: 0x2)
UNION e type=ref key=ts_6637f6f3_e_owner rows=21 Using index condition; Using where
DEPENDENT SUBQUERY x0r type=ALL key=None rows=40 Table function: json_table; Using where
DEPENDENT SUBQUERY x0p type=ALL key=None rows=40 Table function: json_table; Using where
```

**ordinary / union / scoped**

```
PRIMARY e type=range key=ts_6637f6f3_e_path rows=200 Using index condition; Using where
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_6637f6f3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=range key=ts_6637f6f3_e_path rows=200 Using index condition; Using where; Using join buffer (flat, BNL join)
UNION e type=ref key=ts_6637f6f3_e_owner rows=21 Using index condition; Using where
UNION RESULT <union1,2,3,4> type=ALL key=None rows=None
```

**ordinary / unionall / scoped**

```
PRIMARY e type=range key=ts_6637f6f3_e_path rows=200 Using index condition; Using where
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_6637f6f3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=range key=ts_6637f6f3_e_path rows=200 Using index condition; Using where; Using join buffer (flat, BNL join)
UNION e type=ref key=ts_6637f6f3_e_owner rows=21 Using index condition; Using where
UNION RESULT <union1,2,3,4> type=ALL key=None rows=None
```

**ordinary / literal / scoped**

```
SIMPLE e type=range key=ts_6637f6f3_e_path rows=200 Using index condition; Using where
```

**ordinary / disjoint / scoped**

```
PRIMARY e type=range key=ts_6637f6f3_e_path rows=200 Using index condition; Using where
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_6637f6f3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=range key=ts_6637f6f3_e_path rows=200 Using index condition; Using where; Using join buffer (flat, BNL join)
UNION e type=ref key=ts_6637f6f3_e_owner rows=21 Using index condition; Using where
DEPENDENT SUBQUERY x0r type=ALL key=None rows=40 Table function: json_table; Using where
DEPENDENT SUBQUERY x0p type=ALL key=None rows=40 Table function: json_table; Using where
```

**ordinary / union / count**

```
PRIMARY c type=index key=ts_6637f6f3_c_entry rows=2194974 Using index
PRIMARY <derived2> type=eq_ref key=distinct_key rows=1
DERIVED e type=range key=ts_6637f6f3_e_lvlpath rows=415988 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_6637f6f3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=2292241 Range checked for each record (index map: 0x2)
UNION e type=ref key=ts_6637f6f3_e_owner rows=21 Using index condition; Using where
UNION RESULT <union2,3,4,5> type=ALL key=None rows=None
```

**ordinary / unionall / count**

```
PRIMARY c type=index key=ts_6637f6f3_c_entry rows=2194974 Using index
PRIMARY <derived2> type=eq_ref key=distinct_key rows=1
DERIVED e type=range key=ts_6637f6f3_e_lvlpath rows=415988 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_6637f6f3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=2292241 Range checked for each record (index map: 0x2)
UNION e type=ref key=ts_6637f6f3_e_owner rows=21 Using index condition; Using where
UNION RESULT <union2,3,4,5> type=ALL key=None rows=None
```

**ordinary / literal / count**

```
SIMPLE c type=index key=ts_6637f6f3_c_entry rows=2194974 Using index
SIMPLE e type=eq_ref key=PRIMARY rows=1 Using where
```

**ordinary / disjoint / count**

```
PRIMARY c type=index key=ts_6637f6f3_c_entry rows=2194974 Using index
PRIMARY <derived2> type=ref key=key0 rows=41
DERIVED e type=range key=ts_6637f6f3_e_lvlpath rows=415988 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_6637f6f3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=2292241 Range checked for each record (index map: 0x2)
UNION e type=ref key=ts_6637f6f3_e_owner rows=21 Using index condition; Using where
DEPENDENT SUBQUERY x0r type=ALL key=None rows=40 Table function: json_table; Using where
DEPENDENT SUBQUERY x0p type=ALL key=None rows=40 Table function: json_table; Using where
```

**ordinary / union / top10**

```
PRIMARY c type=index key=ts_6637f6f3_c_score rows=10
PRIMARY <derived2> type=eq_ref key=distinct_key rows=1
DERIVED e type=range key=ts_6637f6f3_e_lvlpath rows=415988 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_6637f6f3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=2292241 Range checked for each record (index map: 0x2)
UNION e type=ref key=ts_6637f6f3_e_owner rows=21 Using index condition; Using where
UNION RESULT <union2,3,4,5> type=ALL key=None rows=None
```

**ordinary / unionall / top10**

```
PRIMARY c type=index key=ts_6637f6f3_c_score rows=10
PRIMARY <derived2> type=eq_ref key=distinct_key rows=1
DERIVED e type=range key=ts_6637f6f3_e_lvlpath rows=415988 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_6637f6f3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=2292241 Range checked for each record (index map: 0x2)
UNION e type=ref key=ts_6637f6f3_e_owner rows=21 Using index condition; Using where
UNION RESULT <union2,3,4,5> type=ALL key=None rows=None
```

**ordinary / literal / top10**

```
SIMPLE c type=index key=ts_6637f6f3_c_score rows=10
SIMPLE e type=eq_ref key=PRIMARY rows=1 Using where
```

**ordinary / disjoint / top10**

```
PRIMARY c type=index key=ts_6637f6f3_c_score rows=1
PRIMARY <derived2> type=ref key=key0 rows=41
DERIVED e type=range key=ts_6637f6f3_e_lvlpath rows=415988 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_6637f6f3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=2292241 Range checked for each record (index map: 0x2)
UNION e type=ref key=ts_6637f6f3_e_owner rows=21 Using index condition; Using where
DEPENDENT SUBQUERY x0r type=ALL key=None rows=40 Table function: json_table; Using where
DEPENDENT SUBQUERY x0p type=ALL key=None rows=40 Table function: json_table; Using where
```

**two subjects / union / entries**

```
PRIMARY e type=range key=ts_6637f6f3_e_lvlpath rows=415988 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_6637f6f3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=2292241 Range checked for each record (index map: 0x2)
UNION o0p type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_6637f6f3_e_path rows=1 Using index condition; Using where
UNION o0r type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=2292241 Range checked for each record (index map: 0x2)
UNION o1p type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_6637f6f3_e_path rows=1 Using index condition; Using where
UNION o1r type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=2292241 Range checked for each record (index map: 0x2)
UNION RESULT <union1,2,3,4,5,6,7> type=ALL key=None rows=None
```

**two subjects / unionall / entries**

```
PRIMARY e type=range key=ts_6637f6f3_e_lvlpath rows=415988 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_6637f6f3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=2292241 Range checked for each record (index map: 0x2)
UNION o0p type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_6637f6f3_e_path rows=1 Using index condition; Using where
UNION o0r type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=2292241 Range checked for each record (index map: 0x2)
UNION o1p type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_6637f6f3_e_path rows=1 Using index condition; Using where
UNION o1r type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=2292241 Range checked for each record (index map: 0x2)
UNION RESULT <union1,2,3,4,5,6,7> type=ALL key=None rows=None
```

**two subjects / literal / entries**

```
SIMPLE e type=ALL key=None rows=2292241 Using where
```

**two subjects / disjoint / entries**

```
PRIMARY e type=range key=ts_6637f6f3_e_lvlpath rows=415988 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_6637f6f3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=2292241 Range checked for each record (index map: 0x2)
UNION o0p type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_6637f6f3_e_path rows=1 Using index condition; Using where
DEPENDENT SUBQUERY x0r type=ALL key=None rows=40 Table function: json_table; Using where
DEPENDENT SUBQUERY x0p type=ALL key=None rows=40 Table function: json_table; Using where
UNION o0r type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=2292241 Range checked for each record (index map: 0x2)
DEPENDENT SUBQUERY x0r type=ALL key=None rows=40 Table function: json_table; Using where
DEPENDENT SUBQUERY x0p type=ALL key=None rows=40 Table function: json_table; Using where
UNION o1p type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_6637f6f3_e_path rows=1 Using index condition; Using where
DEPENDENT SUBQUERY x1r type=ALL key=None rows=40 Table function: json_table; Using where
DEPENDENT SUBQUERY x1p type=ALL key=None rows=40 Table function: json_table; Using where
UNION o1r type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=2292241 Range checked for each record (index map: 0x2)
DEPENDENT SUBQUERY x1r type=ALL key=None rows=40 Table function: json_table; Using where
DEPENDENT SUBQUERY x1p type=ALL key=None rows=40 Table function: json_table; Using where
```

**scoped / anonymous / union / IN**

```
SIMPLE e type=range key=ts_6637f6f3_e_lvlpath rows=201 Using where; Using index
```

**scoped / anonymous / union / >=**

```
SIMPLE e type=range key=ts_6637f6f3_e_path rows=200 Using index condition; Using where
```

**scoped / ordinary / union / IN**

```
PRIMARY e type=range key=ts_6637f6f3_e_lvlpath rows=201 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_6637f6f3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=range key=ts_6637f6f3_e_path rows=200 Using index condition; Using where; Using join buffer (flat, BNL join)
UNION e type=ref key=ts_6637f6f3_e_owner rows=21 Using index condition; Using where
UNION RESULT <union1,2,3,4> type=ALL key=None rows=None
```

**scoped / ordinary / unionall / IN**

```
PRIMARY e type=range key=ts_6637f6f3_e_lvlpath rows=201 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_6637f6f3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=range key=ts_6637f6f3_e_path rows=200 Using index condition; Using where; Using join buffer (flat, BNL join)
UNION e type=ref key=ts_6637f6f3_e_owner rows=21 Using index condition; Using where
UNION RESULT <union1,2,3,4> type=ALL key=None rows=None
```

**scoped / ordinary / literal / IN**

```
SIMPLE e type=range key=ts_6637f6f3_e_path rows=200 Using index condition; Using where
```

**scoped / ordinary / disjoint / IN**

```
PRIMARY e type=range key=ts_6637f6f3_e_lvlpath rows=201 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_6637f6f3_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=range key=ts_6637f6f3_e_path rows=200 Using index condition; Using where; Using join buffer (flat, BNL join)
UNION e type=ref key=ts_6637f6f3_e_owner rows=21 Using index condition; Using where
DEPENDENT SUBQUERY x0r type=ALL key=None rows=40 Table function: json_table; Using where
DEPENDENT SUBQUERY x0p type=ALL key=None rows=40 Table function: json_table; Using where
```

Total wall time 287s.
