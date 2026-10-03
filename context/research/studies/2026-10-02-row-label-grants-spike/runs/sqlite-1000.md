## sqlite — N=1,000 users: 23,113 entries, 66,000 chunks (3/file), 1,140 grant rows, 1,101 posture rows, 1,111 domains

Load: rows in 0.1s.

### Indexes

| index | build s | size |
|---|---|---|
| path | 0.0 | 0.7 MB |
| owner | 0.0 | 0.4 MB |
| public | 0.0 | 0.2 MB |
| public_path | 0.0 | 0.7 MB |
| domain | 0.0 | 0.3 MB |
| entry | 0.0 | 0.7 MB |
| score | 0.0 | 0.8 MB |
| path | 0.0 | 0.0 MB |
| public | 0.0 | 0.0 MB |
| principal | 0.0 | 0.0 MB |
| principal | 0.0 | 0.1 MB |
| (entries table itself) | | 1.0 MB |

Truth computed in Python in 0.1s.
### Callers

| caller | subjects | grants held | visible entries | shipped `Rights.admits` on a sample |
|---|---|---|---|---|
| ordinary | u000042 | 41 | 2,034 | 5,000 rows, 0 disagreements; shipped resolve 4 ms (2 arms, 1,100 holes), admits 11 us/row |
| heavy group | u000000 | 41 | 2,034 | 5,000 rows, 0 disagreements; shipped resolve 3 ms (2 arms, 1,100 holes), admits 11 us/row |
| two subjects | u000042, u000000 | 82 | 2,013 | 5,000 rows, 0 disagreements; shipped resolve 4 ms (1 arms, 1,100 holes), admits 11 us/row |
| anonymous | — | 0 | 2,013 | 5,000 rows, 0 disagreements; shipped resolve 1 ms (1 arms, 1,100 holes), admits 14 us/row |
| system | — | 0 | 23,113 | skipped (system) |

### Compile per caller (the caller's own grants → sorted pieces)

| caller | level | points | opens | owner pieces | bind bytes | compile us (median of 200) | grants fetch cold ms | warm ms |
|---|---|---|---|---|---|---|---|---|
| ordinary | read | 11 | 11 | 0 | 630 | 23 | 3.4 | 1.0 |
| ordinary | read_write | 11 | 11 | 0 | 630 | 8 | 1.7 | 1.0 |
| heavy group | read | 11 | 11 | 0 | 630 | 22 | 2.3 | 2.3 |
| heavy group | read_write | 11 | 11 | 0 | 630 | 8 | 0.7 | 0.5 |
| two subjects | read | 10 | 10 | 44 | 1,804 | 56 | 0.7 | 0.3 |
| two subjects | read_write | 10 | 10 | 44 | 1,804 | 25 | 0.6 | 0.7 |

### Domain lists (the `domain_id` variant's compile, one SQL statement)

| caller | domains in list | bind bytes | cold ms | warm ms |
|---|---|---|---|---|
| ordinary | 12 | 67 | 0.5 | 0.3 |
| heavy group | 12 | 66 | 0.4 | 0.3 |
| two subjects | 11 | 63 | 0.4 | 0.2 |
| anonymous | 11 | 63 | 0.7 | 0.3 |

### Statements — cold = fresh connection, warm = median of 2 (ms); recall against the Python truth

| caller | statement | public: cold / warm / recall | domain: cold / warm / recall |
|---|---|---|---|
| ordinary | entries | 3.3 / 1.8 / exact | 1.4 / 2.0 / exact |
| ordinary | scoped | 1.9 / 1.3 / exact | 1.1 / 0.3 / exact |
| ordinary | count | 2.3 / 1.1 / exact | 1.0 / 1.0 / exact |
| ordinary | top10 | 1.8 / 1.5 / exact | 1.6 / 1.7 / exact |
| ordinary | top10 probe | 1.3 / 1.2 / exact | 1.3 / 1.9 / exact |
| heavy group | entries | 1.6 / 2.2 / exact | 2.8 / 2.9 / exact |
| heavy group | scoped | 2.1 / 2.9 / exact | 0.5 / 0.7 / exact |
| heavy group | count | 3.0 / 2.2 / exact | 2.4 / 3.1 / exact |
| heavy group | top10 | 4.5 / 3.2 / exact | 3.2 / 2.8 / exact |
| heavy group | top10 probe | 4.2 / 4.9 / exact | 1.4 / 1.8 / exact |
| two subjects | entries | 2.1 / 1.7 / exact | 1.5 / 1.4 / exact |
| two subjects | scoped | 2.0 / 3.5 / exact | 1.7 / 1.6 / exact |
| two subjects | count | 5.8 / 3.1 / exact | 2.6 / 5.5 / exact |
| two subjects | top10 | 5.1 / 4.5 / exact | 4.5 / 3.3 / exact |
| two subjects | top10 probe | 5.2 / 3.5 / exact | 3.8 / 3.6 / exact |
| anonymous | entries | 2.7 / 1.7 / exact | 2.6 / 2.5 / exact |
| anonymous | scoped | 1.9 / 0.6 / exact | 2.6 / 0.5 / exact |
| anonymous | count | 0.8 / 0.7 / exact | 0.9 / 0.8 / exact |
| anonymous | top10 | 1.1 / 1.0 / exact | 1.4 / 1.7 / exact |
| anonymous | top10 probe | 1.1 / 1.2 / exact | 3.6 / 2.4 / exact |
| system | entries | 14.4 / 12.2 / exact | — |
| system | scoped | 1.1 / 0.6 / exact | — |
| system | count | 14.8 / 6.8 / exact | — |
| system | top10 | 1.5 / 1.4 / exact | — |
| system | top10 probe | 0.9 / 1.3 / exact | — |

### Cache invalidation at this N

One cached caller recomputes by fetching its grant rows and merging them: about 1.30 ms warm here (fetch 1.3 ms + compile 23 us).

| write | global revision invalidates | per-principal / per-group / posture revisions invalidate | recompute at global (ms) | at granular (ms) |
|---|---|---|---|---|
| grant to one user | 1,000 | 1 | 1,303 | 1 |
| grant to a typical group | 1,000 | 1,000 | 1,303 | 1,303 |
| grant to the heavy group | 1,000 | 1,000 | 1,303 | 1,303 |
| posture change (any subtree) | 1,000 | 0 | 1,303 | 0 |

Under the row-label shape a posture change invalidates no compiled rights: the posture is on the rows, not in the caller's pieces. The relabel UPDATE is its cost (see the writes run).

### Plans (ordinary caller)

**public / entries**

```
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX rl_5594071e_e_public (public_level>?)
UNION USING TEMP B-TREE
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX rl_5594071e_e_path (path=?)
UNION USING TEMP B-TREE
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX rl_5594071e_e_path (path>? AND path<?)
UNION USING TEMP B-TREE
SEARCH e USING COVERING INDEX rl_5594071e_e_owner (owner_id=?)
```

**domain / entries**

```
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX rl_5594071e_e_domain (domain_id=?)
LIST SUBQUERY 1
SCAN json_each VIRTUAL TABLE INDEX 1:
CREATE BLOOM FILTER
UNION USING TEMP B-TREE
SEARCH e USING COVERING INDEX rl_5594071e_e_owner (owner_id=?)
```

**public / count**

```
CO-ROUTINE v
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX rl_5594071e_e_public (public_level>?)
UNION USING TEMP B-TREE
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX rl_5594071e_e_path (path=?)
UNION USING TEMP B-TREE
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX rl_5594071e_e_path (path>? AND path<?)
UNION USING TEMP B-TREE
SEARCH e USING COVERING INDEX rl_5594071e_e_owner (owner_id=?)
SCAN v
SEARCH c USING COVERING INDEX rl_5594071e_c_entry (entry_id=?)
```

**domain / count**

```
CO-ROUTINE v
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX rl_5594071e_e_domain (domain_id=?)
LIST SUBQUERY 1
SCAN json_each VIRTUAL TABLE INDEX 1:
CREATE BLOOM FILTER
UNION USING TEMP B-TREE
SEARCH e USING COVERING INDEX rl_5594071e_e_owner (owner_id=?)
SCAN v
SEARCH c USING COVERING INDEX rl_5594071e_c_entry (entry_id=?)
```

**public / top10**

```
CO-ROUTINE v
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX rl_5594071e_e_public (public_level>?)
UNION USING TEMP B-TREE
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX rl_5594071e_e_path (path=?)
UNION USING TEMP B-TREE
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX rl_5594071e_e_path (path>? AND path<?)
UNION USING TEMP B-TREE
SEARCH e USING COVERING INDEX rl_5594071e_e_owner (owner_id=?)
SCAN v
SEARCH c USING INDEX rl_5594071e_c_entry (entry_id=?)
USE TEMP B-TREE FOR ORDER BY
```

**domain / top10**

```
CO-ROUTINE v
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX rl_5594071e_e_domain (domain_id=?)
LIST SUBQUERY 1
SCAN json_each VIRTUAL TABLE INDEX 1:
CREATE BLOOM FILTER
UNION USING TEMP B-TREE
SEARCH e USING COVERING INDEX rl_5594071e_e_owner (owner_id=?)
SCAN v
SEARCH c USING INDEX rl_5594071e_c_entry (entry_id=?)
USE TEMP B-TREE FOR ORDER BY
```

**public / top10 probe**

```
SCAN c USING INDEX rl_5594071e_c_score
BLOOM FILTER ON e (id=?)
SEARCH e USING INTEGER PRIMARY KEY (rowid=?)
LIST SUBQUERY 1
SCAN json_each VIRTUAL TABLE INDEX 1:
CREATE BLOOM FILTER
CORRELATED SCALAR SUBQUERY 2
SCAN ar VIRTUAL TABLE INDEX 1:
```

**domain / top10 probe**

```
MULTI-INDEX OR
INDEX 1
LIST SUBQUERY 1
SCAN json_each VIRTUAL TABLE INDEX 1:
CREATE BLOOM FILTER
SEARCH e USING INDEX rl_5594071e_e_domain (domain_id=?)
INDEX 2
SEARCH e USING INDEX rl_5594071e_e_owner (owner_id=?)
REUSE LIST SUBQUERY 1
SEARCH c USING INDEX rl_5594071e_c_entry (entry_id=?)
USE TEMP B-TREE FOR ORDER BY
```

Total wall time 1s.
