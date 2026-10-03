## sqlite — N=10,000 users: 230,203 entries, 660,000 chunks (3/file), 11,400 grant rows, 10,101 posture rows, 100 sibling traps

Load (tables, rows, indexes, statistics): 6s.

### Indexes

| index | size |
|---|---|
| `path` | 7.8 MB |
| `owner` | 3.7 MB |
| `lvlpath` | 8.1 MB |
| (entries table) | 8.9 MB |

### Callers

| caller | subjects | pieces (arms + owner) | bind bytes | compile us | visible entries |
|---|---|---|---|---|---|
| ordinary | u000042 | 88 | 2,445 | 80 | 20,124 |
| heavy group | u000003 | 88 | 2,445 | 40 | 20,124 |
| two subjects | u000042, u000032 | 220 | 6,094 | 121 | 20,103 |
| anonymous | — | 0 | 0 | 0 | 20,103 |
| system | — | 0 | 0 | 0 | 230,203 |

### Statements — cold = fresh connection, warm = median of 3 (ms); recall against the Python truth

Shapes: union, unionall, literal, disjoint. A blank cell is a shape that does not apply to that caller.

| caller | statement | union: cold / warm / recall | unionall: cold / warm / recall | literal: cold / warm / recall | disjoint: cold / warm / recall |
|---|---|---|---|---|---|
| ordinary | entries | 17.9 / 16.6 / exact | 13.2 / 12.3 / exact | 274 / 223 / exact | 24.6 / 23.8 / exact |
| ordinary | scoped | 6.6 / 3.8 / exact | 6.5 / 3.1 / exact | 8.1 / 2.0 / exact | 15.3 / 4.6 / exact |
| ordinary | count | 20.0 / 17.3 / exact | 24.6 / 19.2 / exact | 244 / 225 / exact | 19.4 / 28.3 / exact |
| ordinary | top10 | 17.1 / 26.2 / exact | 17.9 / 26.1 / exact | 20.1 / 16.8 / exact | 11.1 / 27.0 / exact |
| heavy group | entries | 21.8 / 18.8 / exact | 71.9 / 24.5 / exact | 237 / 210 / exact | 10.2 / 9.6 / exact |
| heavy group | scoped | 1.6 / 5.7 / exact | 4.2 / 3.4 / exact | 3.9 / 1.2 / exact | 1.9 / 1.7 / exact |
| heavy group | count | 9.4 / 8.7 / exact | 10.0 / 8.9 / exact | 201 / 228 / exact | 17.3 / 13.9 / exact |
| heavy group | top10 | 48.0 / 25.8 / exact | 29.2 / 12.2 / exact | 21.6 / 17.7 / exact | 19.6 / 20.9 / exact |
| two subjects | entries | 72.8 / 30.2 / exact | 29.6 / 29.1 / exact | 144 / 150 / exact | 70.6 / 20.9 / exact |
| two subjects | scoped | 4.1 / 4.2 / exact | 5.8 / 9.8 / exact | 18.6 / 3.9 / exact | 8.6 / 7.7 / exact |
| two subjects | count | 37.5 / 18.3 / exact | 19.4 / 22.6 / exact | 144 / 131 / exact | 21.0 / 22.8 / exact |
| two subjects | top10 | 35.7 / 20.3 / exact | 16.4 / 12.2 / exact | 18.7 / 15.0 / exact | 12.7 / 9.3 / exact |
| anonymous | entries | 9.9 / 7.9 / exact |  |  |  |
| anonymous | scoped | 0.8 / 0.6 / exact |  |  |  |
| anonymous | count | 5.5 / 5.1 / exact |  |  |  |
| anonymous | top10 | 8.9 / 9.3 / exact |  |  |  |
| system | entries | 180 / 192 / exact |  |  |  |
| system | scoped | 20.5 / 16.5 / exact |  |  |  |
| system | count | 67.3 / 94.3 / exact |  |  |  |
| system | top10 | 2.1 / 1.7 / exact |  |  |  |

### Scoped read, branch 1 spelled `everyone_level >= :r` against `everyone_level IN (...)`

| caller | shape | `>=` cold / warm | `IN` cold / warm | recall |
|---|---|---|---|---|
| anonymous | union | 10.5 / 4.2 | 9.2 / 8.4 | exact |
| ordinary | union | 2.1 / 14.1 | 9.5 / 3.8 | exact |
| ordinary | unionall | 13.7 / 21.4 | 12.4 / 8.7 | exact |
| ordinary | literal | 1.4 / 1.6 | 1.6 / 0.7 | exact |
| ordinary | disjoint | 1.3 / 4.3 | 4.5 / 6.1 | exact |

### Plans

**ordinary / union / entries**

```
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (everyone_level>?)
UNION USING TEMP B-TREE
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_3bc78559_e_path (path=?)
UNION USING TEMP B-TREE
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION USING TEMP B-TREE
SEARCH e USING INDEX ts_3bc78559_e_owner (owner_id=?)
```

**ordinary / unionall / entries**

```
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (everyone_level>?)
UNION ALL
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_3bc78559_e_path (path=?)
UNION ALL
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION USING TEMP B-TREE
SEARCH e USING INDEX ts_3bc78559_e_owner (owner_id=?)
```

**ordinary / literal / entries**

```
SCAN e
```

**ordinary / disjoint / entries**

```
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (everyone_level>?)
UNION ALL
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_3bc78559_e_path (path=?)
UNION ALL
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION ALL
SEARCH e USING INDEX ts_3bc78559_e_owner (owner_id=?)
CORRELATED SCALAR SUBQUERY 4
SCAN x0p VIRTUAL TABLE INDEX 1:
CORRELATED SCALAR SUBQUERY 5
SCAN x0r VIRTUAL TABLE INDEX 1:
```

**ordinary / union / scoped**

```
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION USING TEMP B-TREE
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_3bc78559_e_path (path=?)
UNION USING TEMP B-TREE
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION USING TEMP B-TREE
SEARCH e USING INDEX ts_3bc78559_e_owner (owner_id=?)
```

**ordinary / unionall / scoped**

```
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION ALL
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_3bc78559_e_path (path=?)
UNION ALL
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION USING TEMP B-TREE
SEARCH e USING INDEX ts_3bc78559_e_owner (owner_id=?)
```

**ordinary / literal / scoped**

```
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
```

**ordinary / disjoint / scoped**

```
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION ALL
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_3bc78559_e_path (path=?)
UNION ALL
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION ALL
SEARCH e USING INDEX ts_3bc78559_e_owner (owner_id=?)
CORRELATED SCALAR SUBQUERY 4
SCAN x0p VIRTUAL TABLE INDEX 1:
CORRELATED SCALAR SUBQUERY 5
SCAN x0r VIRTUAL TABLE INDEX 1:
```

**ordinary / union / count**

```
CO-ROUTINE v
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (everyone_level>?)
UNION USING TEMP B-TREE
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_3bc78559_e_path (path=?)
UNION USING TEMP B-TREE
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION USING TEMP B-TREE
SEARCH e USING INDEX ts_3bc78559_e_owner (owner_id=?)
SCAN v
SEARCH c USING COVERING INDEX ts_3bc78559_c_entry (entry_id=?)
```

**ordinary / unionall / count**

```
CO-ROUTINE v
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (everyone_level>?)
UNION ALL
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_3bc78559_e_path (path=?)
UNION ALL
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION USING TEMP B-TREE
SEARCH e USING INDEX ts_3bc78559_e_owner (owner_id=?)
SCAN v
SEARCH c USING COVERING INDEX ts_3bc78559_c_entry (entry_id=?)
```

**ordinary / literal / count**

```
SCAN e
SEARCH c USING COVERING INDEX ts_3bc78559_c_entry (entry_id=?)
```

**ordinary / disjoint / count**

```
CO-ROUTINE v
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (everyone_level>?)
UNION ALL
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_3bc78559_e_path (path=?)
UNION ALL
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION ALL
SEARCH e USING INDEX ts_3bc78559_e_owner (owner_id=?)
CORRELATED SCALAR SUBQUERY 4
SCAN x0p VIRTUAL TABLE INDEX 1:
CORRELATED SCALAR SUBQUERY 5
SCAN x0r VIRTUAL TABLE INDEX 1:
SCAN v
SEARCH c USING COVERING INDEX ts_3bc78559_c_entry (entry_id=?)
```

**ordinary / union / top10**

```
CO-ROUTINE v
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (everyone_level>?)
UNION USING TEMP B-TREE
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_3bc78559_e_path (path=?)
UNION USING TEMP B-TREE
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION USING TEMP B-TREE
SEARCH e USING INDEX ts_3bc78559_e_owner (owner_id=?)
SCAN v
SEARCH c USING INDEX ts_3bc78559_c_entry (entry_id=?)
USE TEMP B-TREE FOR ORDER BY
```

**ordinary / unionall / top10**

```
CO-ROUTINE v
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (everyone_level>?)
UNION ALL
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_3bc78559_e_path (path=?)
UNION ALL
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION USING TEMP B-TREE
SEARCH e USING INDEX ts_3bc78559_e_owner (owner_id=?)
SCAN v
SEARCH c USING INDEX ts_3bc78559_c_entry (entry_id=?)
USE TEMP B-TREE FOR ORDER BY
```

**ordinary / literal / top10**

```
MULTI-INDEX OR
INDEX 1
SEARCH e USING INDEX ts_3bc78559_e_lvlpath (everyone_level>?)
INDEX 2
SEARCH e USING INDEX ts_3bc78559_e_path (path=?)
INDEX 3
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 4
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 5
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 6
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 7
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 8
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 9
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 10
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 11
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 12
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 13
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 14
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 15
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 16
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 17
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 18
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 19
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 20
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 21
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 22
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 23
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 24
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 25
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 26
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 27
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 28
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 29
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 30
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 31
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 32
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 33
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 34
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 35
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 36
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 37
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 38
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 39
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 40
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 41
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 42
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 43
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 44
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 45
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 46
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
INDEX 47
SEARCH e USING INDEX ts_3bc78559_e_owner (owner_id=?)
SEARCH c USING INDEX ts_3bc78559_c_entry (entry_id=?)
USE TEMP B-TREE FOR ORDER BY
```

**ordinary / disjoint / top10**

```
CO-ROUTINE v
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (everyone_level>?)
UNION ALL
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_3bc78559_e_path (path=?)
UNION ALL
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION ALL
SEARCH e USING INDEX ts_3bc78559_e_owner (owner_id=?)
CORRELATED SCALAR SUBQUERY 4
SCAN x0p VIRTUAL TABLE INDEX 1:
CORRELATED SCALAR SUBQUERY 5
SCAN x0r VIRTUAL TABLE INDEX 1:
SCAN v
SEARCH c USING INDEX ts_3bc78559_c_entry (entry_id=?)
USE TEMP B-TREE FOR ORDER BY
```

**two subjects / union / entries**

```
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (everyone_level>?)
UNION USING TEMP B-TREE
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_3bc78559_e_path (path=?)
UNION USING TEMP B-TREE
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION USING TEMP B-TREE
SCAN o0p VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_3bc78559_e_path (path=?)
UNION USING TEMP B-TREE
SCAN o0r VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_3bc78559_e_owner (owner_id=?)
UNION USING TEMP B-TREE
SCAN o1p VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_3bc78559_e_path (path=?)
UNION USING TEMP B-TREE
SCAN o1r VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_3bc78559_e_owner (owner_id=?)
```

**two subjects / unionall / entries**

```
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (everyone_level>?)
UNION ALL
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_3bc78559_e_path (path=?)
UNION ALL
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION USING TEMP B-TREE
SCAN o0p VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_3bc78559_e_path (path=?)
UNION USING TEMP B-TREE
SCAN o0r VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_3bc78559_e_owner (owner_id=?)
UNION USING TEMP B-TREE
SCAN o1p VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_3bc78559_e_path (path=?)
UNION USING TEMP B-TREE
SCAN o1r VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_3bc78559_e_owner (owner_id=?)
```

**two subjects / literal / entries**

```
SCAN e
```

**two subjects / disjoint / entries**

```
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (everyone_level>?)
UNION ALL
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_3bc78559_e_path (path=?)
UNION ALL
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION ALL
SCAN o0p VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_3bc78559_e_path (path=?)
CORRELATED SCALAR SUBQUERY 4
SCAN x0p VIRTUAL TABLE INDEX 1:
CORRELATED SCALAR SUBQUERY 5
SCAN x0r VIRTUAL TABLE INDEX 1:
UNION ALL
SCAN o0r VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_3bc78559_e_owner (owner_id=?)
CORRELATED SCALAR SUBQUERY 7
SCAN x0p VIRTUAL TABLE INDEX 1:
CORRELATED SCALAR SUBQUERY 8
SCAN x0r VIRTUAL TABLE INDEX 1:
UNION ALL
SCAN o1p VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_3bc78559_e_path (path=?)
CORRELATED SCALAR SUBQUERY 10
SCAN x1p VIRTUAL TABLE INDEX 1:
CORRELATED SCALAR SUBQUERY 11
SCAN x1r VIRTUAL TABLE INDEX 1:
UNION ALL
SCAN o1r VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_3bc78559_e_owner (owner_id=?)
CORRELATED SCALAR SUBQUERY 13
SCAN x1p VIRTUAL TABLE INDEX 1:
CORRELATED SCALAR SUBQUERY 14
SCAN x1r VIRTUAL TABLE INDEX 1:
```

**scoped / anonymous / union / IN**

```
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (everyone_level=? AND path>? AND path<?)
```

**scoped / anonymous / union / >=**

```
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
```

**scoped / ordinary / union / IN**

```
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (everyone_level=? AND path>? AND path<?)
UNION USING TEMP B-TREE
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_3bc78559_e_path (path=?)
UNION USING TEMP B-TREE
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION USING TEMP B-TREE
SEARCH e USING INDEX ts_3bc78559_e_owner (owner_id=?)
```

**scoped / ordinary / unionall / IN**

```
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (everyone_level=? AND path>? AND path<?)
UNION ALL
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_3bc78559_e_path (path=?)
UNION ALL
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION USING TEMP B-TREE
SEARCH e USING INDEX ts_3bc78559_e_owner (owner_id=?)
```

**scoped / ordinary / literal / IN**

```
SEARCH e USING INDEX ts_3bc78559_e_path (path>? AND path<?)
```

**scoped / ordinary / disjoint / IN**

```
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (everyone_level=? AND path>? AND path<?)
UNION ALL
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_3bc78559_e_path (path=?)
UNION ALL
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_3bc78559_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION ALL
SEARCH e USING INDEX ts_3bc78559_e_owner (owner_id=?)
CORRELATED SCALAR SUBQUERY 4
SCAN x0p VIRTUAL TABLE INDEX 1:
CORRELATED SCALAR SUBQUERY 5
SCAN x0r VIRTUAL TABLE INDEX 1:
```

Total wall time 19s.
