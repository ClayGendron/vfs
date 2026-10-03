## sqlite — N=10,000 users: 230,203 entries, 660,000 chunks (3/file), 11,400 grant rows, 10,101 posture rows, 10,201 domains

Load: rows in 0.6s.

### Indexes

| index | build s | size |
|---|---|---|
| e_path | 0.1 | 6.8 MB |
| e_owner | 0.1 | 3.6 MB |
| e_public | 0.0 | 2.1 MB |
| e_public_path | 0.1 | 7.1 MB |
| e_domain | 0.0 | 2.5 MB |
| c_entry | 0.1 | 7.8 MB |
| c_score | 0.4 | 7.9 MB |
| d_path | 0.0 | 0.2 MB |
| d_public | 0.0 | 0.1 MB |
| g_principal | 0.0 | 0.3 MB |
| m_principal | 0.0 | 0.8 MB |
| (entries table itself) | | 9.6 MB |

Truth computed in Python in 1.4s.
### Callers

| caller | subjects | grants held | visible entries | shipped `Rights.admits` on a sample |
|---|---|---|---|---|
| ordinary | u000042 | 49 | 20,124 | 5,000 rows, 0 disagreements; shipped resolve 204 ms (2 arms, 10,100 holes), admits 115 us/row |
| heavy group | u000003 | 46 | 20,124 | 5,000 rows, 0 disagreements; shipped resolve 132 ms (2 arms, 10,100 holes), admits 106 us/row |
| two subjects | u000042, u000032 | 104 | 20,103 | 5,000 rows, 0 disagreements; shipped resolve 70 ms (1 arms, 10,100 holes), admits 121 us/row |
| anonymous | — | 0 | 20,103 | 5,000 rows, 0 disagreements; shipped resolve 18 ms (1 arms, 10,100 holes), admits 113 us/row |
| system | — | 0 | 230,203 | skipped (system) |

### Compile per caller (the caller's own grants → sorted pieces)

| caller | level | points | opens | owner pieces | bind bytes | compile us (median of 200) | grants fetch cold ms | warm ms |
|---|---|---|---|---|---|---|---|---|
| ordinary | read | 44 | 44 | 0 | 2,445 | 31 | 1.9 | 1.0 |
| ordinary | read_write | 11 | 11 | 0 | 630 | 23 | 1.0 | 0.7 |
| heavy group | read | 44 | 44 | 0 | 2,445 | 27 | 1.1 | 0.6 |
| heavy group | read_write | 5 | 5 | 0 | 300 | 13 | 1.1 | 0.6 |
| two subjects | read | 21 | 21 | 178 | 6,094 | 96 | 3.4 | 1.0 |
| two subjects | read_write | 0 | 0 | 40 | 1,148 | 58 | 1.3 | 0.7 |

### Domain lists (the `domain_id` variant's compile, one SQL statement)

| caller | domains in list | bind bytes | cold ms | warm ms |
|---|---|---|---|---|
| ordinary | 102 | 707 | 1.2 | 0.8 |
| heavy group | 102 | 706 | 1.4 | 0.7 |
| two subjects | 101 | 703 | 0.9 | 0.8 |
| anonymous | 101 | 703 | 3.6 | 0.9 |

### Statements — cold = fresh connection, warm = median of 3 (ms); recall against the Python truth

| caller | statement | public: cold / warm / recall | domain: cold / warm / recall |
|---|---|---|---|
| ordinary | entries | 28.8 / 28.0 / exact | 17.6 / 23.6 / exact |
| ordinary | scoped | 9.5 / 7.7 / exact | 9.8 / 4.9 / exact |
| ordinary | count | 10.6 / 13.9 / exact | 14.1 / 14.3 / exact |
| ordinary | top10 | 18.3 / 18.0 / exact | 16.6 / 16.7 / exact |
| ordinary | top10 probe | 11.1 / 12.4 / exact | 12.7 / 9.1 / exact |
| heavy group | entries | 69.3 / 18.5 / exact | 19.0 / 18.5 / exact |
| heavy group | scoped | 9.7 / 8.0 / exact | 5.7 / 5.2 / exact |
| heavy group | count | 11.2 / 7.5 / exact | 7.1 / 11.4 / exact |
| heavy group | top10 | 14.7 / 16.8 / exact | 11.0 / 20.2 / exact |
| heavy group | top10 probe | 13.2 / 5.4 / exact | 9.5 / 18.9 / exact |
| two subjects | entries | 27.9 / 13.5 / exact | 65.8 / 17.3 / exact |
| two subjects | scoped | 4.1 / 4.7 / exact | 4.5 / 3.7 / exact |
| two subjects | count | 14.0 / 15.4 / exact | 16.6 / 13.9 / exact |
| two subjects | top10 | 18.5 / 19.6 / exact | 21.0 / 11.6 / exact |
| two subjects | top10 probe | 10.6 / 12.9 / exact | 17.7 / 20.4 / exact |
| anonymous | entries | 21.7 / 8.6 / exact | 8.4 / 13.6 / exact |
| anonymous | scoped | 1.2 / 0.7 / exact | 5.2 / 5.3 / exact |
| anonymous | count | 9.2 / 4.7 / exact | 7.5 / 12.8 / exact |
| anonymous | top10 | 15.7 / 11.2 / exact | 15.8 / 7.4 / exact |
| anonymous | top10 probe | 14.5 / 10.9 / exact | 14.8 / 14.6 / exact |
| system | entries | 156 / 163 / exact | — |
| system | scoped | 0.4 / 0.2 / exact | — |
| system | count | 42.0 / 42.6 / exact | — |
| system | top10 | 0.6 / 0.6 / exact | — |
| system | top10 probe | 0.4 / 0.2 / exact | — |

### Cache invalidation at this N

One cached caller recomputes by fetching its grant rows and merging them: about 0.31 ms warm here (fetch 0.3 ms + compile 31 us).

| write | global revision invalidates | per-principal / per-group / posture revisions invalidate | recompute at global (ms) | at granular (ms) |
|---|---|---|---|---|
| grant to one user | 10,000 | 1 | 3,141 | 0 |
| grant to a typical group | 10,000 | 1,007 | 3,141 | 316 |
| grant to the heavy group | 10,000 | 979 | 3,141 | 308 |
| posture change (any subtree) | 10,000 | 0 | 3,141 | 0 |

Under the row-label shape a posture change invalidates no compiled rights: the posture is on the rows, not in the caller's pieces. The relabel UPDATE is its cost (see the writes run).

### Plans (ordinary caller)

**public / entries**

```
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX rl_a9f0cb77_e_public (public_level>?)
UNION USING TEMP B-TREE
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX rl_a9f0cb77_e_path (path=?)
UNION USING TEMP B-TREE
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX rl_a9f0cb77_e_path (path>? AND path<?)
UNION USING TEMP B-TREE
SEARCH e USING COVERING INDEX rl_a9f0cb77_e_owner (owner_id=?)
```

**domain / entries**

```
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX rl_a9f0cb77_e_domain (domain_id=?)
LIST SUBQUERY 1
SCAN json_each VIRTUAL TABLE INDEX 1:
CREATE BLOOM FILTER
UNION USING TEMP B-TREE
SEARCH e USING COVERING INDEX rl_a9f0cb77_e_owner (owner_id=?)
```

**public / count**

```
CO-ROUTINE v
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX rl_a9f0cb77_e_public (public_level>?)
UNION USING TEMP B-TREE
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX rl_a9f0cb77_e_path (path=?)
UNION USING TEMP B-TREE
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX rl_a9f0cb77_e_path (path>? AND path<?)
UNION USING TEMP B-TREE
SEARCH e USING COVERING INDEX rl_a9f0cb77_e_owner (owner_id=?)
SCAN v
SEARCH c USING COVERING INDEX rl_a9f0cb77_c_entry (entry_id=?)
```

**domain / count**

```
CO-ROUTINE v
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX rl_a9f0cb77_e_domain (domain_id=?)
LIST SUBQUERY 1
SCAN json_each VIRTUAL TABLE INDEX 1:
CREATE BLOOM FILTER
UNION USING TEMP B-TREE
SEARCH e USING COVERING INDEX rl_a9f0cb77_e_owner (owner_id=?)
SCAN v
SEARCH c USING COVERING INDEX rl_a9f0cb77_c_entry (entry_id=?)
```

**public / top10**

```
CO-ROUTINE v
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX rl_a9f0cb77_e_public (public_level>?)
UNION USING TEMP B-TREE
SCAN ap VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX rl_a9f0cb77_e_path (path=?)
UNION USING TEMP B-TREE
SCAN ar VIRTUAL TABLE INDEX 1:
SEARCH e USING COVERING INDEX rl_a9f0cb77_e_path (path>? AND path<?)
UNION USING TEMP B-TREE
SEARCH e USING COVERING INDEX rl_a9f0cb77_e_owner (owner_id=?)
SCAN v
SEARCH c USING INDEX rl_a9f0cb77_c_entry (entry_id=?)
USE TEMP B-TREE FOR ORDER BY
```

**domain / top10**

```
CO-ROUTINE v
COMPOUND QUERY
LEFT-MOST SUBQUERY
SEARCH e USING COVERING INDEX rl_a9f0cb77_e_domain (domain_id=?)
LIST SUBQUERY 1
SCAN json_each VIRTUAL TABLE INDEX 1:
CREATE BLOOM FILTER
UNION USING TEMP B-TREE
SEARCH e USING COVERING INDEX rl_a9f0cb77_e_owner (owner_id=?)
SCAN v
SEARCH c USING INDEX rl_a9f0cb77_c_entry (entry_id=?)
USE TEMP B-TREE FOR ORDER BY
```

**public / top10 probe**

```
SCAN c USING INDEX rl_a9f0cb77_c_score
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
SEARCH e USING INDEX rl_a9f0cb77_e_domain (domain_id=?)
INDEX 2
SEARCH e USING INDEX rl_a9f0cb77_e_owner (owner_id=?)
REUSE LIST SUBQUERY 1
SEARCH c USING INDEX rl_a9f0cb77_c_entry (entry_id=?)
USE TEMP B-TREE FOR ORDER BY
```

Total wall time 11s.
