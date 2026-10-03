## mssql — N=1,000 users: 23,113 entries, 66,000 chunks (3/file), 1,140 grant rows, 1,101 posture rows, 100 sibling traps

Load (tables, rows, indexes, statistics): 9s.

### Indexes

| index | size |
|---|---|
| `path` | 1.4 MB |
| `owner` | 1.6 MB |
| `lvlpath` | 1.4 MB |
| (entries table) | 1.6 MB |

### Callers

| caller | subjects | pieces (arms + owner) | bind bytes | compile us | visible entries |
|---|---|---|---|---|---|
| ordinary | u000042 | 22 | 630 | 130 | 2,034 |
| heavy group | u000000 | 22 | 630 | 40 | 2,034 |
| two subjects | u000042, u000000 | 64 | 1,804 | 71 | 2,013 |
| anonymous | — | 0 | 0 | 0 | 2,013 |
| system | — | 0 | 0 | 0 | 23,113 |

### Statements — cold = fresh connection, warm = median of 1 (ms); recall against the Python truth

Shapes: union, unionall, literal, disjoint. A blank cell is a shape that does not apply to that caller.

| caller | statement | union: cold / warm / recall | unionall: cold / warm / recall | literal: cold / warm / recall | disjoint: cold / warm / recall |
|---|---|---|---|---|---|
| ordinary | entries | 487 / 460 / exact | 481 / 463 / exact | 26.9 / 5.8 / exact | 500 / 476 / exact |
| ordinary | scoped | 24.3 / 8.1 / exact | 21.2 / 7.4 / exact | 15.1 / 3.7 / exact | 25.6 / 8.3 / exact |
| ordinary | count | 485 / 461 / exact | 479 / 477 / exact | 28.0 / 11.9 / exact | 503 / 522 / exact |
| ordinary | top10 | 46.2 / 21.3 / exact | 49.1 / 15.0 / exact | 21.2 / 3.9 / exact | 119 / 93.3 / exact |
| heavy group | entries | 512 / 478 / exact | 486 / 496 / exact | 18.9 / 22.5 / exact | 501 / 492 / exact |
| heavy group | scoped | 9.0 / 8.3 / exact | 8.4 / 8.3 / exact | 7.2 / 3.6 / exact | 7.2 / 7.4 / exact |
| heavy group | count | 476 / 469 / exact | 475 / 466 / exact | 12.0 / 12.8 / exact | 473 / 473 / exact |
| heavy group | top10 | 8.1 / 7.4 / exact | 7.4 / 7.3 / exact | 3.4 / 3.1 / exact | 79.6 / 80.3 / exact |
| two subjects | entries | 466 / 419 / exact | 454 / 422 / exact | 31.9 / 8.2 / exact | 52.7 / 13.3 / exact |
| two subjects | scoped | 38.4 / 9.8 / exact | 36.4 / 9.5 / exact | 23.5 / 4.3 / exact | 49.7 / 7.8 / exact |
| two subjects | count | 492 / 431 / exact | 477 / 433 / exact | 38.3 / 12.8 / exact | 71.9 / 22.6 / exact |
| two subjects | top10 | 42.7 / 8.6 / exact | 41.4 / 8.4 / exact | 32.8 / 5.3 / exact | 120 / 80.8 / exact |
| anonymous | entries | 6.9 / 3.5 / exact |  |  |  |
| anonymous | scoped | 8.6 / 2.9 / exact |  |  |  |
| anonymous | count | 17.3 / 11.0 / exact |  |  |  |
| anonymous | top10 | 10.1 / 2.9 / exact |  |  |  |
| system | entries | 17.6 / 15.5 / exact |  |  |  |
| system | scoped | 5.6 / 2.4 / exact |  |  |  |
| system | count | 17.2 / 12.4 / exact |  |  |  |
| system | top10 | 5.4 / 1.3 / exact |  |  |  |

### Scoped read, branch 1 spelled `everyone_level >= :r` against `everyone_level IN (...)`

| caller | shape | `>=` cold / warm | `IN` cold / warm | recall |
|---|---|---|---|---|
| anonymous | union | 2.8 / 2.6 | 9.1 / 2.6 | exact |
| ordinary | union | 8.5 / 7.8 | 23.1 / 8.8 | exact |
| ordinary | unionall | 8.0 / 7.8 | 22.8 / 7.9 | exact |
| ordinary | literal | 3.4 / 3.8 | 4.3 / 3.6 | exact |
| ordinary | disjoint | 7.4 / 7.0 | 27.4 / 7.5 | exact |

### Plans

**ordinary / union / entries**

```
Merge Join (Union) [ts_a1b3c6cb_e_lvlpath] est=22,143
  Merge Join (Union) [ts_a1b3c6cb_e_lvlpath] est=22,143
    Merge Join (Union) [ts_a1b3c6cb_e_lvlpath] est=22,143
      Sort (Sort) [ts_a1b3c6cb_e_lvlpath] est=2,013
        Nested Loops (Inner Join) [ts_a1b3c6cb_e_lvlpath] est=2,013
          Compute Scalar (Compute Scalar)  est=1
            Constant Scan (Constant Scan)  est=1
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_lvlpath] est=2,013
      Sort (Sort) [OPENJSON_DEFAULT] est=6
        Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=6
          Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=7
            Sort (Distinct Sort) [OPENJSON_DEFAULT] est=7
              Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=50
                Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=50
            Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
          Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
    Nested Loops (Left Semi Join) [PK__ts_a1b3c__3213E83FA8D1A378] est=3,467
      Clustered Index Scan (Clustered Index Scan) [PK__ts_a1b3c__3213E83FA8D1A378] est=21,100
      Filter (Filter) [OPENJSON_EXPLICIT] est=7
        Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=42
          Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=42
  Nested Loops (Inner Join) [ts_a1b3c6cb_e_owner] est=23
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_owner] est=24
    Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
```

**ordinary / unionall / entries**

```
Merge Join (Union) [ts_a1b3c6cb_e_lvlpath] est=22,143
  Stream Aggregate (Aggregate) [ts_a1b3c6cb_e_lvlpath] est=22,132
    Merge Join (Concatenation) [ts_a1b3c6cb_e_lvlpath] est=23,159
      Merge Join (Concatenation) [ts_a1b3c6cb_e_lvlpath] est=23,159
        Sort (Sort) [ts_a1b3c6cb_e_lvlpath] est=2,013
          Nested Loops (Inner Join) [ts_a1b3c6cb_e_lvlpath] est=2,013
            Compute Scalar (Compute Scalar)  est=1
              Constant Scan (Constant Scan)  est=1
            Index Seek (Index Seek) seek [ts_a1b3c6cb_e_lvlpath] est=2,013
        Sort (Sort) [OPENJSON_DEFAULT] est=46
          Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=46
            Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=50
              Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=50
                Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=50
              Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
            Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
      Nested Loops (Inner Join) [PK__ts_a1b3c__3213E83FA8D1A378] est=21,100
        Clustered Index Scan (Clustered Index Scan) [PK__ts_a1b3c__3213E83FA8D1A378] est=21,100
        Filter (Filter) [OPENJSON_EXPLICIT] est=8
          Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
  Nested Loops (Inner Join) [ts_a1b3c6cb_e_owner] est=23
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_owner] est=24
    Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
```

**ordinary / literal / entries**

```
Sort (Distinct Sort) [ts_a1b3c6cb_e_lvlpath] est=2,249
  Concatenation (Concatenation) [ts_a1b3c6cb_e_lvlpath] est=2,542
    Nested Loops (Inner Join) [ts_a1b3c6cb_e_lvlpath] est=2,013
      Compute Scalar (Compute Scalar)  est=1
        Constant Scan (Constant Scan)  est=1
      Index Seek (Index Seek) seek [ts_a1b3c6cb_e_lvlpath] est=2,013
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=130
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=162
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=194
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_owner] est=24
```

**ordinary / disjoint / entries**

```
Concatenation (Concatenation) [ts_a1b3c6cb_e_lvlpath] est=23,182
  Nested Loops (Inner Join) [ts_a1b3c6cb_e_lvlpath] est=2,013
    Compute Scalar (Compute Scalar)  est=1
      Constant Scan (Constant Scan)  est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_lvlpath] est=2,013
  Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=46
    Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=50
      Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=50
        Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=50
      Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
  Nested Loops (Inner Join) [ts_a1b3c6cb_e_lvlpath] est=21,100
    Nested Loops (Inner Join) [ts_a1b3c6cb_e_lvlpath] est=21,100
      Compute Scalar (Compute Scalar)  est=1
        Constant Scan (Constant Scan)  est=1
      Index Seek (Index Seek) seek [ts_a1b3c6cb_e_lvlpath] est=21,100
    Filter (Filter) [OPENJSON_EXPLICIT] est=8
      Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
  Nested Loops (Left Anti Semi Join) [ts_a1b3c6cb_e_owner] est=23
    Nested Loops (Left Anti Semi Join) [ts_a1b3c6cb_e_owner] est=23
      Nested Loops (Inner Join) [ts_a1b3c6cb_e_owner] est=23
        Index Seek (Index Seek) seek [ts_a1b3c6cb_e_owner] est=24
        Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
      Top (Top) [OPENJSON_DEFAULT] est=1
        Filter (Filter) [OPENJSON_DEFAULT] est=1
          Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=7
            Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=7
    Filter (Filter) [OPENJSON_EXPLICIT] est=8
      Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=50
        Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
```

**ordinary / union / scoped**

```
Hash Match (Union) [ts_a1b3c6cb_e_owner] est=169
  Hash Match (Union) [ts_a1b3c6cb_e_owner] est=169
    Hash Match (Union) [ts_a1b3c6cb_e_owner] est=169
      Nested Loops (Inner Join) [ts_a1b3c6cb_e_owner] est=2
        Hash Match (Inner Join) [ts_a1b3c6cb_e_owner] est=1
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_owner] est=24
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=130
        Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=2
      Nested Loops (Inner Join) [ts_a1b3c6cb_e_lvlpath] est=38
        Compute Scalar (Compute Scalar)  est=1
          Constant Scan (Constant Scan)  est=1
        Index Seek (Index Seek) seek [ts_a1b3c6cb_e_lvlpath] est=38
    Sort (Distinct Sort) [OPENJSON_DEFAULT] est=48
      Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=48
        Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=48
          Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=50
            Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=50
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
        Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
  Stream Aggregate (Aggregate) [ts_a1b3c6cb_e_lvlpath] est=124
    Nested Loops (Inner Join) [ts_a1b3c6cb_e_lvlpath] est=124
      Sort (Sort) [ts_a1b3c6cb_e_lvlpath] est=124
        Index Scan (Index Scan) [ts_a1b3c6cb_e_lvlpath] est=124
      Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=50
        Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
```

**ordinary / unionall / scoped**

```
Merge Join (Union) [ts_a1b3c6cb_e_lvlpath] est=169
  Stream Aggregate (Aggregate) [ts_a1b3c6cb_e_lvlpath] est=168
    Merge Join (Concatenation) [ts_a1b3c6cb_e_lvlpath] est=210
      Merge Join (Concatenation) [ts_a1b3c6cb_e_lvlpath] est=210
        Sort (Sort) [ts_a1b3c6cb_e_lvlpath] est=38
          Nested Loops (Inner Join) [ts_a1b3c6cb_e_lvlpath] est=38
            Compute Scalar (Compute Scalar)  est=1
              Constant Scan (Constant Scan)  est=1
            Index Seek (Index Seek) seek [ts_a1b3c6cb_e_lvlpath] est=38
        Sort (Sort) [OPENJSON_DEFAULT] est=48
          Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=48
            Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=48
              Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=50
                Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=50
              Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
            Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
      Nested Loops (Inner Join) [ts_a1b3c6cb_e_lvlpath] est=124
        Sort (Sort) [ts_a1b3c6cb_e_lvlpath] est=124
          Index Scan (Index Scan) [ts_a1b3c6cb_e_lvlpath] est=124
        Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=50
          Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
  Sort (Sort) [ts_a1b3c6cb_e_owner] est=2
    Nested Loops (Inner Join) [ts_a1b3c6cb_e_owner] est=2
      Hash Match (Inner Join) [ts_a1b3c6cb_e_owner] est=1
        Index Seek (Index Seek) seek [ts_a1b3c6cb_e_owner] est=24
        Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=130
      Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=2
```

**ordinary / literal / scoped**

```
Filter (Filter) [ts_a1b3c6cb_e_path] est=40
  Nested Loops (Inner Join) [ts_a1b3c6cb_e_path] est=130
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=130
    Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
```

**ordinary / disjoint / scoped**

```
Concatenation (Concatenation) [ts_a1b3c6cb_e_lvlpath] est=212
  Nested Loops (Inner Join) [ts_a1b3c6cb_e_lvlpath] est=38
    Compute Scalar (Compute Scalar)  est=1
      Constant Scan (Constant Scan)  est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_lvlpath] est=38
  Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=48
    Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=48
      Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=50
        Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=50
      Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
  Nested Loops (Inner Join) [ts_a1b3c6cb_e_lvlpath] est=124
    Index Scan (Index Scan) [ts_a1b3c6cb_e_lvlpath] est=124
    Filter (Filter) [OPENJSON_EXPLICIT] est=8
      Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
  Nested Loops (Left Anti Semi Join) [ts_a1b3c6cb_e_owner] est=2
    Nested Loops (Left Anti Semi Join) [ts_a1b3c6cb_e_owner] est=2
      Nested Loops (Inner Join) [ts_a1b3c6cb_e_owner] est=2
        Merge Join (Inner Join) [ts_a1b3c6cb_e_owner] est=1
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_owner] est=24
          Sort (Sort) [ts_a1b3c6cb_e_path] est=130
            Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=130
        Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=2
      Top (Top) [OPENJSON_DEFAULT] est=1
        Filter (Filter) [OPENJSON_DEFAULT] est=1
          Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=7
            Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=7
    Filter (Filter) [OPENJSON_EXPLICIT] est=8
      Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=50
        Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
```

**ordinary / union / count**

```
Compute Scalar (Compute Scalar) [ts_a1b3c6cb_e_lvlpath] est=1
  Stream Aggregate (Aggregate) [ts_a1b3c6cb_e_lvlpath] est=1
    Merge Join (Inner Join) [ts_a1b3c6cb_e_lvlpath] est=63,230
      Merge Join (Union) [ts_a1b3c6cb_e_lvlpath] est=22,143
        Merge Join (Union) [ts_a1b3c6cb_e_lvlpath] est=22,143
          Merge Join (Union) [ts_a1b3c6cb_e_lvlpath] est=22,143
            Sort (Sort) [ts_a1b3c6cb_e_lvlpath] est=2,013
              Nested Loops (Inner Join) [ts_a1b3c6cb_e_lvlpath] est=2,013
                Compute Scalar (Compute Scalar)  est=1
                  Constant Scan (Constant Scan)  est=1
                Index Seek (Index Seek) seek [ts_a1b3c6cb_e_lvlpath] est=2,013
            Sort (Sort) [OPENJSON_DEFAULT] est=6
              Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=6
                Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=7
                  Sort (Distinct Sort) [OPENJSON_DEFAULT] est=7
                    Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=50
                      Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=50
                  Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
                Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
          Nested Loops (Left Semi Join) [PK__ts_a1b3c__3213E83FA8D1A378] est=3,467
            Clustered Index Scan (Clustered Index Scan) [PK__ts_a1b3c__3213E83FA8D1A378] est=21,100
            Filter (Filter) [OPENJSON_EXPLICIT] est=7
              Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=42
                Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=42
        Nested Loops (Inner Join) [ts_a1b3c6cb_e_owner] est=23
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_owner] est=24
          Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
      Index Scan (Index Scan) [ts_a1b3c6cb_c_entry] est=66,000
```

**ordinary / unionall / count**

```
Compute Scalar (Compute Scalar) [ts_a1b3c6cb_e_lvlpath] est=1
  Stream Aggregate (Aggregate) [ts_a1b3c6cb_e_lvlpath] est=1
    Merge Join (Inner Join) [ts_a1b3c6cb_e_lvlpath] est=63,230
      Merge Join (Union) [ts_a1b3c6cb_e_lvlpath] est=22,143
        Stream Aggregate (Aggregate) [ts_a1b3c6cb_e_lvlpath] est=22,132
          Merge Join (Concatenation) [ts_a1b3c6cb_e_lvlpath] est=23,159
            Merge Join (Concatenation) [ts_a1b3c6cb_e_lvlpath] est=23,159
              Sort (Sort) [ts_a1b3c6cb_e_lvlpath] est=2,013
                Nested Loops (Inner Join) [ts_a1b3c6cb_e_lvlpath] est=2,013
                  Compute Scalar (Compute Scalar)  est=1
                    Constant Scan (Constant Scan)  est=1
                  Index Seek (Index Seek) seek [ts_a1b3c6cb_e_lvlpath] est=2,013
              Sort (Sort) [OPENJSON_DEFAULT] est=46
                Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=46
                  Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=50
                    Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=50
                      Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=50
                    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
                  Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
            Nested Loops (Inner Join) [PK__ts_a1b3c__3213E83FA8D1A378] est=21,100
              Clustered Index Scan (Clustered Index Scan) [PK__ts_a1b3c__3213E83FA8D1A378] est=21,100
              Filter (Filter) [OPENJSON_EXPLICIT] est=8
                Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
        Nested Loops (Inner Join) [ts_a1b3c6cb_e_owner] est=23
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_owner] est=24
          Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
      Index Scan (Index Scan) [ts_a1b3c6cb_c_entry] est=66,000
```

**ordinary / literal / count**

```
Compute Scalar (Compute Scalar) [ts_a1b3c6cb_e_lvlpath] est=1
  Stream Aggregate (Aggregate) [ts_a1b3c6cb_e_lvlpath] est=1
    Merge Join (Inner Join) [ts_a1b3c6cb_e_lvlpath] est=6,747
      Sort (Distinct Sort) [ts_a1b3c6cb_e_lvlpath] est=2,249
        Concatenation (Concatenation) [ts_a1b3c6cb_e_lvlpath] est=2,542
          Nested Loops (Inner Join) [ts_a1b3c6cb_e_lvlpath] est=2,013
            Compute Scalar (Compute Scalar)  est=1
              Constant Scan (Constant Scan)  est=1
            Index Seek (Index Seek) seek [ts_a1b3c6cb_e_lvlpath] est=2,013
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=130
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=162
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=194
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_owner] est=24
      Index Scan (Index Scan) [ts_a1b3c6cb_c_entry] est=66,000
```

**ordinary / disjoint / count**

```
Compute Scalar (Compute Scalar) [ts_a1b3c6cb_e_lvlpath] est=1
  Stream Aggregate (Aggregate) [ts_a1b3c6cb_e_lvlpath] est=1
    Hash Match (Inner Join) [ts_a1b3c6cb_e_lvlpath] est=66,196
      Concatenation (Concatenation) [ts_a1b3c6cb_e_lvlpath] est=23,182
        Nested Loops (Inner Join) [ts_a1b3c6cb_e_lvlpath] est=2,013
          Compute Scalar (Compute Scalar)  est=1
            Constant Scan (Constant Scan)  est=1
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_lvlpath] est=2,013
        Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=46
          Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=50
            Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=50
              Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=50
            Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
          Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
        Nested Loops (Inner Join) [ts_a1b3c6cb_e_lvlpath] est=21,100
          Nested Loops (Inner Join) [ts_a1b3c6cb_e_lvlpath] est=21,100
            Compute Scalar (Compute Scalar)  est=1
              Constant Scan (Constant Scan)  est=1
            Index Seek (Index Seek) seek [ts_a1b3c6cb_e_lvlpath] est=21,100
          Filter (Filter) [OPENJSON_EXPLICIT] est=8
            Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
        Nested Loops (Left Anti Semi Join) [ts_a1b3c6cb_e_owner] est=23
          Nested Loops (Left Anti Semi Join) [ts_a1b3c6cb_e_owner] est=23
            Nested Loops (Inner Join) [ts_a1b3c6cb_e_owner] est=23
              Index Seek (Index Seek) seek [ts_a1b3c6cb_e_owner] est=24
              Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
            Top (Top) [OPENJSON_DEFAULT] est=1
              Filter (Filter) [OPENJSON_DEFAULT] est=1
                Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=7
                  Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=7
          Filter (Filter) [OPENJSON_EXPLICIT] est=8
            Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=50
              Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
      Index Scan (Index Scan) [ts_a1b3c6cb_c_entry] est=66,000
```

**ordinary / union / top10**

```
Top (Top) [ts_a1b3c6cb_c_score] est=10
  Nested Loops (Inner Join) [ts_a1b3c6cb_c_score] est=10
    Nested Loops (Inner Join) [ts_a1b3c6cb_c_score] est=10
      Index Scan (Index Scan) [ts_a1b3c6cb_c_score] est=10
      Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FB561AECC] est=1
    Top (Top) [PK__ts_a1b3c__3213E83FA8D1A378] est=1
      Concatenation (Concatenation) [PK__ts_a1b3c__3213E83FA8D1A378] est=1
        Top (Top) [PK__ts_a1b3c__3213E83FA8D1A378] est=1
          Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
        Top (Top) [PK__ts_a1b3c__3213E83FA8D1A378] est=1
          Nested Loops (Inner Join) [PK__ts_a1b3c__3213E83FA8D1A378] est=1
            Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
            Filter (Filter) [OPENJSON_DEFAULT] est=5
              Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=50
        Top (Top) [PK__ts_a1b3c__3213E83FA8D1A378] est=1
          Nested Loops (Inner Join) [PK__ts_a1b3c__3213E83FA8D1A378] est=1
            Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
            Filter (Filter) [OPENJSON_EXPLICIT] est=8
              Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
        Top (Top) [PK__ts_a1b3c__3213E83FA8D1A378] est=1
          Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
```

**ordinary / unionall / top10**

```
Top (Top) [ts_a1b3c6cb_c_score] est=10
  Nested Loops (Inner Join) [ts_a1b3c6cb_c_score] est=10
    Nested Loops (Inner Join) [ts_a1b3c6cb_c_score] est=10
      Index Scan (Index Scan) [ts_a1b3c6cb_c_score] est=10
      Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FB561AECC] est=1
    Top (Top) [PK__ts_a1b3c__3213E83FA8D1A378] est=1
      Concatenation (Concatenation) [PK__ts_a1b3c__3213E83FA8D1A378] est=1
        Top (Top) [PK__ts_a1b3c__3213E83FA8D1A378] est=1
          Concatenation (Concatenation) [PK__ts_a1b3c__3213E83FA8D1A378] est=1
            Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
            Nested Loops (Inner Join) [PK__ts_a1b3c__3213E83FA8D1A378] est=1
              Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
              Filter (Filter) [OPENJSON_DEFAULT] est=5
                Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=50
            Nested Loops (Inner Join) [PK__ts_a1b3c__3213E83FA8D1A378] est=1
              Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
              Filter (Filter) [OPENJSON_EXPLICIT] est=8
                Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
        Top (Top) [PK__ts_a1b3c__3213E83FA8D1A378] est=1
          Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
```

**ordinary / literal / top10**

```
Top (Top) [ts_a1b3c6cb_c_score] est=10
  Nested Loops (Inner Join) [ts_a1b3c6cb_c_score] est=10
    Nested Loops (Inner Join) [ts_a1b3c6cb_c_score] est=98
      Index Scan (Index Scan) [ts_a1b3c6cb_c_score] est=98
      Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FB561AECC] est=1
    Filter (Filter) [PK__ts_a1b3c__3213E83FA8D1A378] est=1
      Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
```

**ordinary / disjoint / top10**

```
Top (Top) [ts_a1b3c6cb_c_score] est=10
  Nested Loops (Inner Join) [ts_a1b3c6cb_c_score] est=10
    Nested Loops (Inner Join) [ts_a1b3c6cb_c_score] est=10
      Index Scan (Index Scan) [ts_a1b3c6cb_c_score] est=10
      Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FB561AECC] est=1
    Concatenation (Concatenation) [PK__ts_a1b3c__3213E83FA8D1A378] est=10
      Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
      Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=7
        Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=7
          Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=50
            Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=50
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
        Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
      Nested Loops (Inner Join) [OPENJSON_EXPLICIT] est=1
        Nested Loops (Inner Join) [OPENJSON_EXPLICIT] est=1
          Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=50
            Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
        Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
      Nested Loops (Left Anti Semi Join) [PK__ts_a1b3c__3213E83FA8D1A378] est=1
        Nested Loops (Left Anti Semi Join) [PK__ts_a1b3c__3213E83FA8D1A378] est=1
          Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
          Filter (Filter) [OPENJSON_DEFAULT] est=7
            Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=50
              Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=50
        Filter (Filter) [OPENJSON_EXPLICIT] est=8
          Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=50
            Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
```

**two subjects / union / entries**

```
Merge Join (Union) [ts_a1b3c6cb_e_lvlpath] est=22,176
  Merge Join (Union) [ts_a1b3c6cb_e_lvlpath] est=22,176
    Merge Join (Union) [ts_a1b3c6cb_e_lvlpath] est=22,176
      Merge Join (Union) [ts_a1b3c6cb_e_lvlpath] est=22,176
        Merge Join (Union) [ts_a1b3c6cb_e_lvlpath] est=22,176
          Merge Join (Union) [ts_a1b3c6cb_e_lvlpath] est=22,176
            Sort (Sort) [ts_a1b3c6cb_e_lvlpath] est=2,013
              Nested Loops (Inner Join) [ts_a1b3c6cb_e_lvlpath] est=2,013
                Compute Scalar (Compute Scalar)  est=1
                  Constant Scan (Constant Scan)  est=1
                Index Seek (Index Seek) seek [ts_a1b3c6cb_e_lvlpath] est=2,013
            Sort (Sort) [OPENJSON_DEFAULT] est=6
              Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=6
                Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=7
                  Sort (Distinct Sort) [OPENJSON_DEFAULT] est=7
                    Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=50
                      Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=50
                  Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
                Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
          Nested Loops (Left Semi Join) [PK__ts_a1b3c__3213E83FA8D1A378] est=3,467
            Clustered Index Scan (Clustered Index Scan) [PK__ts_a1b3c__3213E83FA8D1A378] est=21,100
            Filter (Filter) [OPENJSON_EXPLICIT] est=7
              Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=42
                Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=42
        Sort (Sort) [OPENJSON_DEFAULT] est=1
          Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=1
            Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=7
              Sort (Distinct Sort) [OPENJSON_DEFAULT] est=7
                Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=50
                  Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=50
              Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
            Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=0
      Nested Loops (Left Semi Join) [ts_a1b3c6cb_e_owner] est=4
        Nested Loops (Inner Join) [ts_a1b3c6cb_e_owner] est=23
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_owner] est=24
          Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
        Filter (Filter) [OPENJSON_EXPLICIT] est=7
          Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=42
            Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=42
    Sort (Sort) [OPENJSON_DEFAULT] est=1
      Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=1
        Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=7
          Sort (Distinct Sort) [OPENJSON_DEFAULT] est=7
            Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=50
              Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=50
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
        Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=0
  Nested Loops (Left Semi Join) [ts_a1b3c6cb_e_owner] est=4
    Nested Loops (Inner Join) [ts_a1b3c6cb_e_owner] est=22
      Index Seek (Index Seek) seek [ts_a1b3c6cb_e_owner] est=23
      Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
    Filter (Filter) [OPENJSON_EXPLICIT] est=7
      Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=42
        Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=42
```

**two subjects / unionall / entries**

```
Merge Join (Union) [ts_a1b3c6cb_e_lvlpath] est=22,176
  Merge Join (Union) [ts_a1b3c6cb_e_lvlpath] est=22,176
    Merge Join (Union) [ts_a1b3c6cb_e_lvlpath] est=22,176
      Merge Join (Union) [ts_a1b3c6cb_e_lvlpath] est=22,176
        Stream Aggregate (Aggregate) [ts_a1b3c6cb_e_lvlpath] est=22,132
          Merge Join (Concatenation) [ts_a1b3c6cb_e_lvlpath] est=23,159
            Merge Join (Concatenation) [ts_a1b3c6cb_e_lvlpath] est=23,159
              Sort (Sort) [ts_a1b3c6cb_e_lvlpath] est=2,013
                Nested Loops (Inner Join) [ts_a1b3c6cb_e_lvlpath] est=2,013
                  Compute Scalar (Compute Scalar)  est=1
                    Constant Scan (Constant Scan)  est=1
                  Index Seek (Index Seek) seek [ts_a1b3c6cb_e_lvlpath] est=2,013
              Sort (Sort) [OPENJSON_DEFAULT] est=46
                Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=46
                  Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=50
                    Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=50
                      Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=50
                    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
                  Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
            Nested Loops (Inner Join) [PK__ts_a1b3c__3213E83FA8D1A378] est=21,100
              Clustered Index Scan (Clustered Index Scan) [PK__ts_a1b3c__3213E83FA8D1A378] est=21,100
              Filter (Filter) [OPENJSON_EXPLICIT] est=8
                Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
        Sort (Sort) [OPENJSON_DEFAULT] est=1
          Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=1
            Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=7
              Sort (Distinct Sort) [OPENJSON_DEFAULT] est=7
                Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=50
                  Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=50
              Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
            Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=0
      Nested Loops (Left Semi Join) [ts_a1b3c6cb_e_owner] est=4
        Nested Loops (Inner Join) [ts_a1b3c6cb_e_owner] est=23
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_owner] est=24
          Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
        Filter (Filter) [OPENJSON_EXPLICIT] est=7
          Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=42
            Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=42
    Sort (Sort) [OPENJSON_DEFAULT] est=1
      Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=1
        Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=7
          Sort (Distinct Sort) [OPENJSON_DEFAULT] est=7
            Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=50
              Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=50
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
        Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=0
  Nested Loops (Left Semi Join) [ts_a1b3c6cb_e_owner] est=4
    Nested Loops (Inner Join) [ts_a1b3c6cb_e_owner] est=22
      Index Seek (Index Seek) seek [ts_a1b3c6cb_e_owner] est=23
      Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
    Filter (Filter) [OPENJSON_EXPLICIT] est=7
      Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=42
        Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=42
```

**two subjects / literal / entries**

```
Sort (Distinct Sort) [ts_a1b3c6cb_e_lvlpath] est=2,244
  Concatenation (Concatenation) [ts_a1b3c6cb_e_lvlpath] est=2,523
    Nested Loops (Inner Join) [ts_a1b3c6cb_e_lvlpath] est=2,013
      Compute Scalar (Compute Scalar)  est=1
        Constant Scan (Constant Scan)  est=1
      Index Seek (Index Seek) seek [ts_a1b3c6cb_e_lvlpath] est=2,013
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=130
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=162
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=194
    Filter (Filter) [ts_a1b3c6cb_e_owner] est=4
      Nested Loops (Inner Join) [ts_a1b3c6cb_e_owner] est=24
        Index Seek (Index Seek) seek [ts_a1b3c6cb_e_owner] est=24
        Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
    Filter (Filter) [ts_a1b3c6cb_e_owner] est=3
      Nested Loops (Inner Join) [ts_a1b3c6cb_e_owner] est=23
        Index Seek (Index Seek) seek [ts_a1b3c6cb_e_owner] est=23
        Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
```

**two subjects / disjoint / entries**

```
Concatenation (Concatenation) [ts_a1b3c6cb_e_lvlpath] est=23,206
  Nested Loops (Inner Join) [ts_a1b3c6cb_e_lvlpath] est=2,013
    Compute Scalar (Compute Scalar)  est=1
      Constant Scan (Constant Scan)  est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_lvlpath] est=2,013
  Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=46
    Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=50
      Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=50
        Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=50
      Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
  Nested Loops (Inner Join) [OPENJSON_EXPLICIT] est=21,100
    Nested Loops (Inner Join) [OPENJSON_EXPLICIT] est=23,113
      Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=50
        Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
      Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=462
    Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
  Nested Loops (Left Anti Semi Join) [ts_a1b3c6cb_e_owner] est=1
    Nested Loops (Left Anti Semi Join) [ts_a1b3c6cb_e_owner] est=1
      Hash Match (Inner Join) [ts_a1b3c6cb_e_owner] est=1
        Nested Loops (Inner Join) [ts_a1b3c6cb_e_owner] est=23
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_owner] est=24
          Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
        Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=50
          Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=50
      Top (Top) [OPENJSON_DEFAULT] est=1
        Filter (Filter) [OPENJSON_DEFAULT] est=1
          Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=7
            Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=7
    Filter (Filter) [OPENJSON_EXPLICIT] est=8
      Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=50
        Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
  Nested Loops (Inner Join) [ts_a1b3c6cb_e_owner] est=23
    Nested Loops (Left Anti Semi Join) [ts_a1b3c6cb_e_owner] est=23
      Nested Loops (Left Anti Semi Join) [ts_a1b3c6cb_e_owner] est=23
        Nested Loops (Inner Join) [ts_a1b3c6cb_e_owner] est=23
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_owner] est=24
          Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
        Top (Top) [OPENJSON_DEFAULT] est=1
          Filter (Filter) [OPENJSON_DEFAULT] est=1
            Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=7
              Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=7
      Filter (Filter) [OPENJSON_EXPLICIT] est=8
        Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=50
          Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
    Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=50
      Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
  Nested Loops (Left Anti Semi Join) [ts_a1b3c6cb_e_owner] est=1
    Nested Loops (Left Anti Semi Join) [ts_a1b3c6cb_e_owner] est=1
      Hash Match (Inner Join) [ts_a1b3c6cb_e_owner] est=1
        Nested Loops (Inner Join) [ts_a1b3c6cb_e_owner] est=22
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_owner] est=23
          Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
        Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=50
          Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=50
      Top (Top) [OPENJSON_DEFAULT] est=1
        Filter (Filter) [OPENJSON_DEFAULT] est=1
          Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=7
            Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=7
    Filter (Filter) [OPENJSON_EXPLICIT] est=8
      Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=50
        Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
  Nested Loops (Inner Join) [ts_a1b3c6cb_e_owner] est=22
    Nested Loops (Left Anti Semi Join) [ts_a1b3c6cb_e_owner] est=22
      Nested Loops (Left Anti Semi Join) [ts_a1b3c6cb_e_owner] est=22
        Nested Loops (Inner Join) [ts_a1b3c6cb_e_owner] est=22
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_owner] est=23
          Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
        Top (Top) [OPENJSON_DEFAULT] est=1
          Filter (Filter) [OPENJSON_DEFAULT] est=1
            Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=7
              Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=7
      Filter (Filter) [OPENJSON_EXPLICIT] est=8
        Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=50
          Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
    Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=50
      Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
```

**scoped / anonymous / union / IN**

```
Nested Loops (Inner Join) [ts_a1b3c6cb_e_lvlpath] est=38
  Merge Interval (Merge Interval)  est=2
    Sort (TopN Sort)  est=2
      Compute Scalar (Compute Scalar)  est=2
        Concatenation (Concatenation)  est=2
          Compute Scalar (Compute Scalar)  est=1
            Constant Scan (Constant Scan)  est=1
          Compute Scalar (Compute Scalar)  est=1
            Constant Scan (Constant Scan)  est=1
  Index Seek (Index Seek) seek [ts_a1b3c6cb_e_lvlpath] est=38
```

**scoped / anonymous / union / >=**

```
Nested Loops (Inner Join) [ts_a1b3c6cb_e_lvlpath] est=38
  Compute Scalar (Compute Scalar)  est=1
    Constant Scan (Constant Scan)  est=1
  Index Seek (Index Seek) seek [ts_a1b3c6cb_e_lvlpath] est=38
```

**scoped / ordinary / union / IN**

```
Hash Match (Union) [ts_a1b3c6cb_e_owner] est=169
  Hash Match (Union) [ts_a1b3c6cb_e_owner] est=169
    Hash Match (Union) [ts_a1b3c6cb_e_owner] est=169
      Nested Loops (Inner Join) [ts_a1b3c6cb_e_owner] est=2
        Hash Match (Inner Join) [ts_a1b3c6cb_e_owner] est=1
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_owner] est=24
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=130
        Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=2
      Nested Loops (Inner Join) [ts_a1b3c6cb_e_lvlpath] est=38
        Merge Interval (Merge Interval)  est=2
          Sort (TopN Sort)  est=2
            Compute Scalar (Compute Scalar)  est=2
              Concatenation (Concatenation)  est=2
                Compute Scalar (Compute Scalar)  est=1
                  Constant Scan (Constant Scan)  est=1
                Compute Scalar (Compute Scalar)  est=1
                  Constant Scan (Constant Scan)  est=1
        Index Seek (Index Seek) seek [ts_a1b3c6cb_e_lvlpath] est=38
    Sort (Distinct Sort) [OPENJSON_DEFAULT] est=48
      Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=48
        Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=48
          Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=50
            Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=50
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
        Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
  Stream Aggregate (Aggregate) [ts_a1b3c6cb_e_lvlpath] est=124
    Nested Loops (Inner Join) [ts_a1b3c6cb_e_lvlpath] est=124
      Sort (Sort) [ts_a1b3c6cb_e_lvlpath] est=124
        Index Scan (Index Scan) [ts_a1b3c6cb_e_lvlpath] est=124
      Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=50
        Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
```

**scoped / ordinary / unionall / IN**

```
Merge Join (Union) [ts_a1b3c6cb_e_lvlpath] est=169
  Stream Aggregate (Aggregate) [ts_a1b3c6cb_e_lvlpath] est=168
    Merge Join (Concatenation) [ts_a1b3c6cb_e_lvlpath] est=210
      Merge Join (Concatenation) [ts_a1b3c6cb_e_lvlpath] est=210
        Sort (Sort) [ts_a1b3c6cb_e_lvlpath] est=38
          Nested Loops (Inner Join) [ts_a1b3c6cb_e_lvlpath] est=38
            Merge Interval (Merge Interval)  est=2
              Sort (TopN Sort)  est=2
                Compute Scalar (Compute Scalar)  est=2
                  Concatenation (Concatenation)  est=2
                    Compute Scalar (Compute Scalar)  est=1
                      Constant Scan (Constant Scan)  est=1
                    Compute Scalar (Compute Scalar)  est=1
                      Constant Scan (Constant Scan)  est=1
            Index Seek (Index Seek) seek [ts_a1b3c6cb_e_lvlpath] est=38
        Sort (Sort) [OPENJSON_DEFAULT] est=48
          Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=48
            Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=48
              Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=50
                Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=50
              Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
            Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
      Nested Loops (Inner Join) [ts_a1b3c6cb_e_lvlpath] est=124
        Sort (Sort) [ts_a1b3c6cb_e_lvlpath] est=124
          Index Scan (Index Scan) [ts_a1b3c6cb_e_lvlpath] est=124
        Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=50
          Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
  Sort (Sort) [ts_a1b3c6cb_e_owner] est=2
    Nested Loops (Inner Join) [ts_a1b3c6cb_e_owner] est=2
      Hash Match (Inner Join) [ts_a1b3c6cb_e_owner] est=1
        Index Seek (Index Seek) seek [ts_a1b3c6cb_e_owner] est=24
        Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=130
      Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=2
```

**scoped / ordinary / literal / IN**

```
Filter (Filter) [ts_a1b3c6cb_e_path] est=40
  Nested Loops (Inner Join) [ts_a1b3c6cb_e_path] est=130
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=130
    Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
```

**scoped / ordinary / disjoint / IN**

```
Concatenation (Concatenation) [ts_a1b3c6cb_e_lvlpath] est=212
  Nested Loops (Inner Join) [ts_a1b3c6cb_e_lvlpath] est=38
    Merge Interval (Merge Interval)  est=2
      Sort (TopN Sort)  est=2
        Compute Scalar (Compute Scalar)  est=2
          Concatenation (Concatenation)  est=2
            Compute Scalar (Compute Scalar)  est=1
              Constant Scan (Constant Scan)  est=1
            Compute Scalar (Compute Scalar)  est=1
              Constant Scan (Constant Scan)  est=1
    Index Seek (Index Seek) seek [ts_a1b3c6cb_e_lvlpath] est=38
  Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=48
    Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=48
      Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=50
        Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=50
      Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=1
    Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=1
  Nested Loops (Inner Join) [ts_a1b3c6cb_e_lvlpath] est=124
    Index Scan (Index Scan) [ts_a1b3c6cb_e_lvlpath] est=124
    Filter (Filter) [OPENJSON_EXPLICIT] est=8
      Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
  Nested Loops (Left Anti Semi Join) [ts_a1b3c6cb_e_owner] est=2
    Nested Loops (Left Anti Semi Join) [ts_a1b3c6cb_e_owner] est=2
      Nested Loops (Inner Join) [ts_a1b3c6cb_e_owner] est=2
        Merge Join (Inner Join) [ts_a1b3c6cb_e_owner] est=1
          Index Seek (Index Seek) seek [ts_a1b3c6cb_e_owner] est=24
          Sort (Sort) [ts_a1b3c6cb_e_path] est=130
            Index Seek (Index Seek) seek [ts_a1b3c6cb_e_path] est=130
        Clustered Index Seek (Clustered Index Seek) seek [PK__ts_a1b3c__3213E83FA8D1A378] est=2
      Top (Top) [OPENJSON_DEFAULT] est=1
        Filter (Filter) [OPENJSON_DEFAULT] est=1
          Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=7
            Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=7
    Filter (Filter) [OPENJSON_EXPLICIT] est=8
      Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=50
        Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
```

Total wall time 31s.
