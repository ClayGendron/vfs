## mssql — writes: 1,000-user world plus /mid (1,001 rows), /mv (10,001), /big (200,000); 234,115 entries

Load: 17s.

Forms: `join` = the UPDATE through the range source (`UPDATE … FROM unnest` / `UPDATE … FROM … JOIN OPENJSON` / `UPDATE … JOIN JSON_TABLE` / `MERGE … USING JSON_TABLE`); `literal` = `WHERE (path > :lo AND path < :hi) OR …`; `in_sub` = `WHERE id IN (SELECT … FROM source JOIN e)`. Points always travel as `path IN (…)`. At most 500 pieces per statement; every statement is its own transaction.

| operation | form | statements | rows touched | total ms (median of runs) | labels after |
|---|---|---|---|---|---|
| posture /mid → shared (1,000 rows) | join; 1 points + 1 ranges (0 deeper postures cut) | 2 | 1,001 | 65 | all correct |
| posture /mid → shared (1,000 rows) | literal; 1 points + 1 ranges (0 deeper postures cut) | 2 | 1,001 | 48 | all correct |
| posture /big → shared (200,000 rows), one statement | join; 1 points + 1 ranges (0 deeper postures cut) | 2 | 200,000 | 3,342 | all correct |
| posture /big → shared (200,000 rows), chunked | join; 1 points + 1 ranges (0 deeper postures cut); keyset chunks of 50,000 rows | 9 | 200,000 | 7,530 | all correct |
| posture / → shared (root minus every deeper posture) | join; 1103 points + 2205 ranges (1,102 deeper postures cut) | 8 | 12,014 | 956 | all correct |
| posture / → shared (root minus every deeper posture) | literal; 1103 points + 2205 ranges (1,102 deeper postures cut) | 8 | 12,014 | 4,440 | all correct |
| move /mv → /home/u000000/mv (10,001 rows, open → private) | one UPDATE: path rewrite + destination label | 1 | 10,001 | 741 | all take the destination label |

### Plans

**posture /mid → shared (1,000 rows) / join (1 ranges)**

```
Index Update (Update) [ts_18d396c1_e_lvlpath] est=468,230
  Sort (Sort) [PK__ts_18d39__3213E83FC98186AF] est=468,230
    Filter (Filter) [PK__ts_18d39__3213E83FC98186AF] est=468,230
      Split (Split) [PK__ts_18d39__3213E83FC98186AF] est=468,230
        Clustered Index Update (Update) [PK__ts_18d39__3213E83FC98186AF] est=234,115
          Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=234,115
            Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=234,115
              Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=234,115
                Parallelism (Gather Streams) [OPENJSON_EXPLICIT] est=234,115
                  Sort (Distinct Sort) [OPENJSON_EXPLICIT] est=234,115
                    Parallelism (Repartition Streams) [OPENJSON_EXPLICIT] est=234,115
                      Nested Loops (Inner Join) [OPENJSON_EXPLICIT] est=234,115
                        Nested Loops (Inner Join) [OPENJSON_EXPLICIT] est=234,115
                          Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=50
                            Parallelism (Distribute Streams) [OPENJSON_EXPLICIT] est=50
                              Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
                          Index Seek (Index Seek) seek [ts_18d396c1_e_path] est=4,682
                        Clustered Index Seek (Clustered Index Seek) seek [PK__ts_18d39__3213E83FC98186AF] est=1
```

**posture /mid → shared (1,000 rows) / literal (1 ranges)**

```
Clustered Index Update (Update) [PK__ts_18d39__3213E83FC98186AF] est=1
  Compute Scalar (Compute Scalar) [ts_18d396c1_e_path] est=1
    Compute Scalar (Compute Scalar) [ts_18d396c1_e_path] est=1
      Compute Scalar (Compute Scalar) [ts_18d396c1_e_path] est=1
        Nested Loops (Inner Join) [ts_18d396c1_e_path] est=1
          Index Seek (Index Seek) seek [ts_18d396c1_e_path] est=1
          Clustered Index Seek (Clustered Index Seek) seek [PK__ts_18d39__3213E83FC98186AF] est=1
```

**posture / → shared (root minus every deeper posture) / join (500 ranges)**

```
Index Update (Update) [ts_18d396c1_e_lvlpath] est=312,153
  Sort (Sort) [PK__ts_18d39__3213E83FC98186AF] est=312,153
    Filter (Filter) [PK__ts_18d39__3213E83FC98186AF] est=312,153
      Split (Split) [PK__ts_18d39__3213E83FC98186AF] est=468,230
        Clustered Index Update (Update) [PK__ts_18d39__3213E83FC98186AF] est=234,115
          Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=234,115
            Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=234,115
              Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=234,115
                Parallelism (Gather Streams) [OPENJSON_EXPLICIT] est=234,115
                  Sort (Distinct Sort) [OPENJSON_EXPLICIT] est=234,115
                    Parallelism (Repartition Streams) [OPENJSON_EXPLICIT] est=234,115
                      Nested Loops (Inner Join) [OPENJSON_EXPLICIT] est=234,115
                        Nested Loops (Inner Join) [OPENJSON_EXPLICIT] est=234,115
                          Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=50
                            Parallelism (Distribute Streams) [OPENJSON_EXPLICIT] est=50
                              Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
                          Index Seek (Index Seek) seek [ts_18d396c1_e_path] est=4,682
                        Clustered Index Seek (Clustered Index Seek) seek [PK__ts_18d39__3213E83FC98186AF] est=1
```

**posture / → shared (root minus every deeper posture) / literal (500 ranges)**

```
Index Update (Update) [ts_18d396c1_e_lvlpath] est=1,400
  Sort (Sort) [PK__ts_18d39__3213E83FC98186AF] est=1,400
    Filter (Filter) [PK__ts_18d39__3213E83FC98186AF] est=1,400
      Split (Split) [PK__ts_18d39__3213E83FC98186AF] est=9,434
        Clustered Index Update (Update) [PK__ts_18d39__3213E83FC98186AF] est=4,717
          Compute Scalar (Compute Scalar) [ts_18d396c1_e_lvlpath] est=4,717
            Parallelism (Gather Streams) [ts_18d396c1_e_lvlpath] est=4,717
              Sort (Sort) [ts_18d396c1_e_lvlpath] est=4,717
                Compute Scalar (Compute Scalar) [ts_18d396c1_e_lvlpath] est=4,717
                  Compute Scalar (Compute Scalar) [ts_18d396c1_e_lvlpath] est=4,717
                    Filter (Filter) [ts_18d396c1_e_lvlpath] est=4,717
                      Index Scan (Index Scan) [ts_18d396c1_e_lvlpath] est=234,115
```

**move /mv → /home/u000000/mv**

```
Sequence (Sequence) [ts_18d396c1_e_lvlpath] est=11,062
  Index Update (Update) [ts_18d396c1_e_lvlpath] est=15,915
    Sort (Sort) [PK__ts_18d39__3213E83FC98186AF] est=15,915
      Filter (Filter) [PK__ts_18d39__3213E83FC98186AF] est=15,915
        Table Spool (Eager Spool) [PK__ts_18d39__3213E83FC98186AF] est=16,388
          Split (Split) [PK__ts_18d39__3213E83FC98186AF] est=16,388
            Clustered Index Update (Update) [PK__ts_18d39__3213E83FC98186AF] est=8,194
              Compute Scalar (Compute Scalar) [ts_18d396c1_e_lvlpath] est=8,194
                Compute Scalar (Compute Scalar) [ts_18d396c1_e_lvlpath] est=8,194
                  Compute Scalar (Compute Scalar) [ts_18d396c1_e_lvlpath] est=8,194
                    Parallelism (Gather Streams) [ts_18d396c1_e_lvlpath] est=8,194
                      Sort (Sort) [ts_18d396c1_e_lvlpath] est=8,194
                        Index Scan (Index Scan) [ts_18d396c1_e_lvlpath] est=8,194
  Index Update (Update) [ts_18d396c1_e_path] est=11,062
    Collapse (Collapse)  est=11,062
      Sort (Sort)  est=14,749
        Filter (Filter)  est=14,749
          Table Spool (Eager Spool)  est=16,388
```

Total wall time 71s.
