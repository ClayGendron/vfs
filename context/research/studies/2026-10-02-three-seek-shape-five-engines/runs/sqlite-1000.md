## sqlite — N=1,000 users: 23,113 entries, 66,000 chunks (3/file), 1,140 grant rows, 1,101 posture rows, 100 sibling traps

Load (tables, rows, indexes, statistics): 0s.

### Indexes

| index | size |
|---|---|
| `path` | 0.8 MB |
| `owner` | 0.4 MB |
| `lvlpath` | 0.8 MB |
| (entries table) | 0.9 MB |

### Callers

| caller | subjects | pieces (arms + owner) | bind bytes | compile us | visible entries |
|---|---|---|---|---|---|
| ordinary | u000042 | 22 | 630 | 51 | 2,034 |
| heavy group | u000000 | 22 | 630 | 32 | 2,034 |
| two subjects | u000042, u000000 | 64 | 1,804 | 70 | 2,013 |
| anonymous | — | 0 | 0 | 0 | 2,013 |
| system | — | 0 | 0 | 0 | 23,113 |

### Statements — cold = fresh connection, warm = median of 1 (ms); recall against the Python truth

Shapes: union, unionall, literal, disjoint. A blank cell is a shape that does not apply to that caller.

| caller | statement | union: cold / warm / recall | unionall: cold / warm / recall | literal: cold / warm / recall | disjoint: cold / warm / recall |
|---|---|---|---|---|---|
| ordinary | entries | 2.0 / 1.1 / exact | 1.2 / 1.1 / exact | 7.9 / 7.5 / exact | 1.1 / 0.9 / exact |
| ordinary | scoped | 0.5 / 0.3 / exact | 0.5 / 0.4 / exact | 0.5 / 0.2 / exact | 0.5 / 0.3 / exact |
| ordinary | count | 0.9 / 0.7 / exact | 0.9 / 0.7 / exact | 7.3 / 7.0 / exact | 0.8 / 0.7 / exact |
| ordinary | top10 | 1.2 / 1.1 / exact | 1.2 / 1.0 / exact | 7.3 / 7.0 / exact | 1.2 / 1.0 / exact |
| heavy group | entries | 16.3 / 1.2 / exact | 1.2 / 1.1 / exact | 7.7 / 7.4 / exact | 1.0 / 1.0 / exact |
| heavy group | scoped | 0.4 / 0.3 / exact | 0.4 / 0.3 / exact | 0.3 / 0.2 / exact | 0.4 / 0.3 / exact |
| heavy group | count | 0.8 / 0.7 / exact | 0.8 / 0.8 / exact | 7.2 / 7.0 / exact | 0.7 / 0.6 / exact |
| heavy group | top10 | 1.1 / 1.0 / exact | 1.1 / 1.0 / exact | 7.0 / 6.8 / exact | 1.0 / 0.9 / exact |
| two subjects | entries | 1.4 / 1.1 / exact | 1.3 / 1.1 / exact | 7.4 / 6.9 / exact | 1.2 / 1.0 / exact |
| two subjects | scoped | 0.7 / 0.5 / exact | 0.7 / 0.5 / exact | 0.8 / 0.3 / exact | 0.8 / 0.4 / exact |
| two subjects | count | 1.1 / 0.9 / exact | 1.1 / 0.9 / exact | 7.4 / 6.8 / exact | 1.1 / 0.8 / exact |
| two subjects | top10 | 1.4 / 1.2 / exact | 1.4 / 1.2 / exact | 7.5 / 6.5 / exact | 1.3 / 1.1 / exact |
| anonymous | entries | 0.9 / 0.9 / exact |  |  |  |
| anonymous | scoped | 0.3 / 0.3 / exact |  |  |  |
| anonymous | count | 0.6 / 0.5 / exact |  |  |  |
| anonymous | top10 | 1.0 / 0.8 / exact |  |  |  |
| system | entries | 8.4 / 8.4 / exact |  |  |  |
| system | scoped | 0.4 / 0.2 / exact |  |  |  |
| system | count | 4.3 / 4.0 / exact |  |  |  |
| system | top10 | 0.3 / 0.2 / exact |  |  |  |

### Scoped read, branch 1 spelled `everyone_level >= :r` against `everyone_level IN (...)`

| caller | shape | `>=` cold / warm | `IN` cold / warm | recall |
|---|---|---|---|---|
| anonymous | union | 0.3 / 0.2 | 0.3 / 0.2 | exact |
| ordinary | union | 0.4 / 0.3 | 0.4 / 0.3 | exact |
| ordinary | unionall | 0.4 / 0.3 | 0.5 / 0.3 | exact |
| ordinary | literal | 0.3 / 0.2 | 0.5 / 0.2 | exact |
| ordinary | disjoint | 0.4 / 0.4 | 0.5 / 0.3 | exact |

### Plans

**ordinary / union / entries**

```
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (everyone_level>?)
UNION USING TEMP B-TREE
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_da66db93_e_path (path=?)
UNION USING TEMP B-TREE
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION USING TEMP B-TREE
SEARCH e USING INDEX ts_da66db93_e_owner (owner_id=?)
```

**ordinary / unionall / entries**

```
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (everyone_level>?)
UNION ALL
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_da66db93_e_path (path=?)
UNION ALL
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION USING TEMP B-TREE
SEARCH e USING INDEX ts_da66db93_e_owner (owner_id=?)
```

**ordinary / literal / entries**

```
SCAN e
```

**ordinary / disjoint / entries**

```
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (everyone_level>?)
UNION ALL
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_da66db93_e_path (path=?)
UNION ALL
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION ALL
SEARCH e USING INDEX ts_da66db93_e_owner (owner_id=?)
CORRELATED SCALAR SUBQUERY 4
SCAN x0p VIRTUAL TABLE INDEX 1:
CORRELATED SCALAR SUBQUERY 5
SCAN x0r VIRTUAL TABLE INDEX 1:
```

**ordinary / union / scoped**

```
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION USING TEMP B-TREE
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_da66db93_e_path (path=?)
UNION USING TEMP B-TREE
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION USING TEMP B-TREE
SEARCH e USING INDEX ts_da66db93_e_owner (owner_id=?)
```

**ordinary / unionall / scoped**

```
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION ALL
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_da66db93_e_path (path=?)
UNION ALL
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION USING TEMP B-TREE
SEARCH e USING INDEX ts_da66db93_e_owner (owner_id=?)
```

**ordinary / literal / scoped**

```
SEARCH e USING INDEX ts_da66db93_e_path (path>? AND path<?)
```

**ordinary / disjoint / scoped**

```
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION ALL
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_da66db93_e_path (path=?)
UNION ALL
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION ALL
SEARCH e USING INDEX ts_da66db93_e_owner (owner_id=?)
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
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (everyone_level>?)
UNION USING TEMP B-TREE
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_da66db93_e_path (path=?)
UNION USING TEMP B-TREE
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION USING TEMP B-TREE
SEARCH e USING INDEX ts_da66db93_e_owner (owner_id=?)
SCAN v
SEARCH c USING COVERING INDEX ts_da66db93_c_entry (entry_id=?)
```

**ordinary / unionall / count**

```
CO-ROUTINE v
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (everyone_level>?)
UNION ALL
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_da66db93_e_path (path=?)
UNION ALL
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION USING TEMP B-TREE
SEARCH e USING INDEX ts_da66db93_e_owner (owner_id=?)
SCAN v
SEARCH c USING COVERING INDEX ts_da66db93_c_entry (entry_id=?)
```

**ordinary / literal / count**

```
SCAN e
SEARCH c USING COVERING INDEX ts_da66db93_c_entry (entry_id=?)
```

**ordinary / disjoint / count**

```
CO-ROUTINE v
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (everyone_level>?)
UNION ALL
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_da66db93_e_path (path=?)
UNION ALL
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION ALL
SEARCH e USING INDEX ts_da66db93_e_owner (owner_id=?)
CORRELATED SCALAR SUBQUERY 4
SCAN x0p VIRTUAL TABLE INDEX 1:
CORRELATED SCALAR SUBQUERY 5
SCAN x0r VIRTUAL TABLE INDEX 1:
SCAN v
SEARCH c USING COVERING INDEX ts_da66db93_c_entry (entry_id=?)
```

**ordinary / union / top10**

```
CO-ROUTINE v
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (everyone_level>?)
UNION USING TEMP B-TREE
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_da66db93_e_path (path=?)
UNION USING TEMP B-TREE
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION USING TEMP B-TREE
SEARCH e USING INDEX ts_da66db93_e_owner (owner_id=?)
SCAN v
SEARCH c USING INDEX ts_da66db93_c_entry (entry_id=?)
USE TEMP B-TREE FOR ORDER BY
```

**ordinary / unionall / top10**

```
CO-ROUTINE v
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (everyone_level>?)
UNION ALL
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_da66db93_e_path (path=?)
UNION ALL
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION USING TEMP B-TREE
SEARCH e USING INDEX ts_da66db93_e_owner (owner_id=?)
SCAN v
SEARCH c USING INDEX ts_da66db93_c_entry (entry_id=?)
USE TEMP B-TREE FOR ORDER BY
```

**ordinary / literal / top10**

```
SCAN c USING INDEX ts_da66db93_c_score
BLOOM FILTER ON e (id=?)
SEARCH e USING INTEGER PRIMARY KEY (rowid=?)
```

**ordinary / disjoint / top10**

```
CO-ROUTINE v
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (everyone_level>?)
UNION ALL
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_da66db93_e_path (path=?)
UNION ALL
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION ALL
SEARCH e USING INDEX ts_da66db93_e_owner (owner_id=?)
CORRELATED SCALAR SUBQUERY 4
SCAN x0p VIRTUAL TABLE INDEX 1:
CORRELATED SCALAR SUBQUERY 5
SCAN x0r VIRTUAL TABLE INDEX 1:
SCAN v
SEARCH c USING INDEX ts_da66db93_c_entry (entry_id=?)
USE TEMP B-TREE FOR ORDER BY
```

**two subjects / union / entries**

```
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (everyone_level>?)
UNION USING TEMP B-TREE
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_da66db93_e_path (path=?)
UNION USING TEMP B-TREE
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION USING TEMP B-TREE
SCAN o0p VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_da66db93_e_path (path=?)
UNION USING TEMP B-TREE
SCAN o0r VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_da66db93_e_owner (owner_id=?)
UNION USING TEMP B-TREE
SCAN o1p VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_da66db93_e_path (path=?)
UNION USING TEMP B-TREE
SCAN o1r VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_da66db93_e_owner (owner_id=?)
```

**two subjects / unionall / entries**

```
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (everyone_level>?)
UNION ALL
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_da66db93_e_path (path=?)
UNION ALL
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION USING TEMP B-TREE
SCAN o0p VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_da66db93_e_path (path=?)
UNION USING TEMP B-TREE
SCAN o0r VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_da66db93_e_owner (owner_id=?)
UNION USING TEMP B-TREE
SCAN o1p VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_da66db93_e_path (path=?)
UNION USING TEMP B-TREE
SCAN o1r VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_da66db93_e_owner (owner_id=?)
```

**two subjects / literal / entries**

```
SCAN e
```

**two subjects / disjoint / entries**

```
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (everyone_level>?)
UNION ALL
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_da66db93_e_path (path=?)
UNION ALL
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION ALL
SCAN o0p VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_da66db93_e_path (path=?)
CORRELATED SCALAR SUBQUERY 4
SCAN x0p VIRTUAL TABLE INDEX 1:
CORRELATED SCALAR SUBQUERY 5
SCAN x0r VIRTUAL TABLE INDEX 1:
UNION ALL
SCAN o0r VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_da66db93_e_owner (owner_id=?)
CORRELATED SCALAR SUBQUERY 7
SCAN x0p VIRTUAL TABLE INDEX 1:
CORRELATED SCALAR SUBQUERY 8
SCAN x0r VIRTUAL TABLE INDEX 1:
UNION ALL
SCAN o1p VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_da66db93_e_path (path=?)
CORRELATED SCALAR SUBQUERY 10
SCAN x1p VIRTUAL TABLE INDEX 1:
CORRELATED SCALAR SUBQUERY 11
SCAN x1r VIRTUAL TABLE INDEX 1:
UNION ALL
SCAN o1r VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_da66db93_e_owner (owner_id=?)
CORRELATED SCALAR SUBQUERY 13
SCAN x1p VIRTUAL TABLE INDEX 1:
CORRELATED SCALAR SUBQUERY 14
SCAN x1r VIRTUAL TABLE INDEX 1:
```

**scoped / anonymous / union / IN**

```
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (everyone_level=? AND path>? AND path<?)
```

**scoped / anonymous / union / >=**

```
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
```

**scoped / ordinary / union / IN**

```
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (everyone_level=? AND path>? AND path<?)
UNION USING TEMP B-TREE
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_da66db93_e_path (path=?)
UNION USING TEMP B-TREE
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION USING TEMP B-TREE
SEARCH e USING INDEX ts_da66db93_e_owner (owner_id=?)
```

**scoped / ordinary / unionall / IN**

```
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (everyone_level=? AND path>? AND path<?)
UNION ALL
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_da66db93_e_path (path=?)
UNION ALL
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION USING TEMP B-TREE
SEARCH e USING INDEX ts_da66db93_e_owner (owner_id=?)
```

**scoped / ordinary / literal / IN**

```
SEARCH e USING INDEX ts_da66db93_e_path (path>? AND path<?)
```

**scoped / ordinary / disjoint / IN**

```
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (everyone_level=? AND path>? AND path<?)
UNION ALL
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING INDEX ts_da66db93_e_path (path=?)
UNION ALL
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX ts_da66db93_e_lvlpath (ANY(everyone_level) AND path>? AND path<?)
UNION ALL
SEARCH e USING INDEX ts_da66db93_e_owner (owner_id=?)
CORRELATED SCALAR SUBQUERY 4
SCAN x0p VIRTUAL TABLE INDEX 1:
CORRELATED SCALAR SUBQUERY 5
SCAN x0r VIRTUAL TABLE INDEX 1:
```

Total wall time 1s.
