## mssql probe — N=10,000, ordinary caller (88 pieces), unionall shape; warm = median of 3

Load 46s.

| knobs | statement | cold / warm / recall |
|---|---|---|
| apply=False, loop_join=False, force_order=False, plus_zero=False | entries | 3,464 / 4,512 / exact |
| apply=False, loop_join=False, force_order=False, plus_zero=False | scoped | 47.1 / 16.1 / exact |
| apply=False, loop_join=False, force_order=False, plus_zero=False | count | 4,399 / 4,312 / exact |
| apply=False, loop_join=False, force_order=False, plus_zero=False | top10 | 74.1 / 21.2 / exact |
| apply=False, loop_join=False, force_order=False, plus_zero=True | entries | 4,208 / 4,255 / exact |
| apply=False, loop_join=False, force_order=False, plus_zero=True | scoped | 27.2 / 6.2 / exact |
| apply=False, loop_join=False, force_order=False, plus_zero=True | count | 3,710 / 3,254 / exact |
| apply=False, loop_join=False, force_order=False, plus_zero=True | top10 | 62.1 / 13.1 / exact |
| apply=False, loop_join=True, force_order=False, plus_zero=False | entries | 83.6 / 83.0 / exact |
| apply=False, loop_join=True, force_order=False, plus_zero=False | scoped | 36.9 / 19.4 / exact |
| apply=False, loop_join=True, force_order=False, plus_zero=False | count | 177 / 104 / exact |
| apply=False, loop_join=True, force_order=False, plus_zero=False | top10 | 242 / 158 / exact |
| apply=True, loop_join=False, force_order=False, plus_zero=False | entries | 4,342 / 3,775 / exact |
| apply=True, loop_join=False, force_order=False, plus_zero=False | scoped | 34.4 / 6.4 / exact |
| apply=True, loop_join=False, force_order=False, plus_zero=False | count | 3,347 / 3,243 / exact |
| apply=True, loop_join=False, force_order=False, plus_zero=False | top10 | 51.0 / 11.2 / exact |
| apply=False, loop_join=False, force_order=True, plus_zero=False | entries | 82.6 / 63.8 / exact |
| apply=False, loop_join=False, force_order=True, plus_zero=False | scoped | 32.6 / 11.5 / exact |
| apply=False, loop_join=False, force_order=True, plus_zero=False | count | 105 / 61.4 / exact |
| apply=False, loop_join=False, force_order=True, plus_zero=False | top10 | 118 / 79.3 / exact |

**apply=False, loop_join=False, force_order=False, plus_zero=False / entries**

```
Parallelism (Gather Streams) [ts_9a626c7a_e_lvlpath] est=220,187
  Hash Match (Union) [ts_9a626c7a_e_lvlpath] est=220,187
    Concatenation (Concatenation) [ts_9a626c7a_e_lvlpath] est=230,249
      Parallelism (Distribute Streams) [ts_9a626c7a_e_lvlpath] est=20,103
        Nested Loops (Inner Join) [ts_9a626c7a_e_lvlpath] est=20,103
          Compute Scalar (Compute Scalar)  est=1
            Constant Scan (Constant Scan)  est=1
          Index Seek (Index Seek) seek [ts_9a626c7a_e_lvlpath] est=20,103
      Parallelism (Repartition Streams) [OPENJSON_DEFAULT] est=46
        Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=46
          Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=50
            Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=50
              Parallelism (Distribute Streams) [OPENJSON_DEFAULT] est=50
                Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=50
            Index Seek (Index Seek) seek [ts_9a626c7a_e_path] est=1
          Clustered Index Seek (Clustered Index Seek) seek [PK__ts_9a626__3213E83FCD6B2E86] est=1
      Parallelism (Repartition Streams) [PK__ts_9a626__3213E83FCD6B2E86] est=210,100
        Nested Loops (Inner Join) [PK__ts_9a626__3213E83FCD6B2E86] est=210,100
          Clustered Index Scan (Clustered Index Scan) [PK__ts_9a626__3213E83FCD6B2E86] est=210,100
          Filter (Filter) [OPENJSON_EXPLICIT] est=8
            Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
    Parallelism (Repartition Streams) [ts_9a626c7a_e_owner] est=21
      Nested Loops (Inner Join) [ts_9a626c7a_e_owner] est=21
        Parallelism (Distribute Streams) [ts_9a626c7a_e_owner] est=22
          Index Seek (Index Seek) seek [ts_9a626c7a_e_owner] est=22
        Clustered Index Seek (Clustered Index Seek) seek [PK__ts_9a626__3213E83FCD6B2E86] est=1
```

**apply=False, loop_join=False, force_order=False, plus_zero=False / count**

```
Compute Scalar (Compute Scalar) [ts_9a626c7a_c_entry] est=1
  Stream Aggregate (Aggregate) [ts_9a626c7a_c_entry] est=1
    Parallelism (Gather Streams) [ts_9a626c7a_c_entry] est=5
      Stream Aggregate (Aggregate) [ts_9a626c7a_c_entry] est=5
        Hash Match (Inner Join) [ts_9a626c7a_c_entry] est=210,428
          Parallelism (Repartition Streams) [ts_9a626c7a_c_entry] est=220,000
            Index Scan (Index Scan) [ts_9a626c7a_c_entry] est=220,000
          Hash Match (Union) [ts_9a626c7a_e_lvlpath] est=220,187
            Concatenation (Concatenation) [ts_9a626c7a_e_lvlpath] est=230,249
              Parallelism (Distribute Streams) [ts_9a626c7a_e_lvlpath] est=20,103
                Nested Loops (Inner Join) [ts_9a626c7a_e_lvlpath] est=20,103
                  Compute Scalar (Compute Scalar)  est=1
                    Constant Scan (Constant Scan)  est=1
                  Index Seek (Index Seek) seek [ts_9a626c7a_e_lvlpath] est=20,103
              Parallelism (Repartition Streams) [OPENJSON_DEFAULT] est=46
                Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=46
                  Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=50
                    Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=50
                      Parallelism (Distribute Streams) [OPENJSON_DEFAULT] est=50
                        Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=50
                    Index Seek (Index Seek) seek [ts_9a626c7a_e_path] est=1
                  Clustered Index Seek (Clustered Index Seek) seek [PK__ts_9a626__3213E83FCD6B2E86] est=1
              Parallelism (Repartition Streams) [PK__ts_9a626__3213E83FCD6B2E86] est=210,100
                Nested Loops (Inner Join) [PK__ts_9a626__3213E83FCD6B2E86] est=210,100
                  Clustered Index Scan (Clustered Index Scan) [PK__ts_9a626__3213E83FCD6B2E86] est=210,100
                  Filter (Filter) [OPENJSON_EXPLICIT] est=8
                    Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
            Parallelism (Repartition Streams) [ts_9a626c7a_e_owner] est=21
              Nested Loops (Inner Join) [ts_9a626c7a_e_owner] est=21
                Parallelism (Distribute Streams) [ts_9a626c7a_e_owner] est=22
                  Index Seek (Index Seek) seek [ts_9a626c7a_e_owner] est=22
                Clustered Index Seek (Clustered Index Seek) seek [PK__ts_9a626__3213E83FCD6B2E86] est=1
```

**apply=False, loop_join=False, force_order=False, plus_zero=True / entries**

```
Parallelism (Gather Streams) [ts_9a626c7a_e_lvlpath] est=220,187
  Hash Match (Union) [ts_9a626c7a_e_lvlpath] est=220,187
    Concatenation (Concatenation) [ts_9a626c7a_e_lvlpath] est=230,249
      Parallelism (Distribute Streams) [ts_9a626c7a_e_lvlpath] est=20,103
        Nested Loops (Inner Join) [ts_9a626c7a_e_lvlpath] est=20,103
          Compute Scalar (Compute Scalar)  est=1
            Constant Scan (Constant Scan)  est=1
          Index Seek (Index Seek) seek [ts_9a626c7a_e_lvlpath] est=20,103
      Parallelism (Repartition Streams) [OPENJSON_DEFAULT] est=46
        Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=46
          Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=50
            Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=50
              Parallelism (Distribute Streams) [OPENJSON_DEFAULT] est=50
                Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=50
            Index Seek (Index Seek) seek [ts_9a626c7a_e_path] est=1
          Clustered Index Seek (Clustered Index Seek) seek [PK__ts_9a626__3213E83FCD6B2E86] est=1
      Parallelism (Repartition Streams) [ts_9a626c7a_e_lvlpath] est=210,100
        Nested Loops (Inner Join) [ts_9a626c7a_e_lvlpath] est=210,100
          Index Scan (Index Scan) [ts_9a626c7a_e_lvlpath] est=210,100
          Filter (Filter) [OPENJSON_EXPLICIT] est=8
            Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
    Parallelism (Repartition Streams) [ts_9a626c7a_e_owner] est=21
      Nested Loops (Inner Join) [ts_9a626c7a_e_owner] est=21
        Parallelism (Distribute Streams) [ts_9a626c7a_e_owner] est=22
          Index Seek (Index Seek) seek [ts_9a626c7a_e_owner] est=22
        Clustered Index Seek (Clustered Index Seek) seek [PK__ts_9a626__3213E83FCD6B2E86] est=1
```

**apply=False, loop_join=False, force_order=False, plus_zero=True / count**

```
Compute Scalar (Compute Scalar) [ts_9a626c7a_c_entry] est=1
  Stream Aggregate (Aggregate) [ts_9a626c7a_c_entry] est=1
    Parallelism (Gather Streams) [ts_9a626c7a_c_entry] est=5
      Stream Aggregate (Aggregate) [ts_9a626c7a_c_entry] est=5
        Hash Match (Inner Join) [ts_9a626c7a_c_entry] est=210,428
          Parallelism (Repartition Streams) [ts_9a626c7a_c_entry] est=220,000
            Index Scan (Index Scan) [ts_9a626c7a_c_entry] est=220,000
          Hash Match (Union) [ts_9a626c7a_e_lvlpath] est=220,187
            Concatenation (Concatenation) [ts_9a626c7a_e_lvlpath] est=230,249
              Parallelism (Distribute Streams) [ts_9a626c7a_e_lvlpath] est=20,103
                Nested Loops (Inner Join) [ts_9a626c7a_e_lvlpath] est=20,103
                  Compute Scalar (Compute Scalar)  est=1
                    Constant Scan (Constant Scan)  est=1
                  Index Seek (Index Seek) seek [ts_9a626c7a_e_lvlpath] est=20,103
              Parallelism (Repartition Streams) [OPENJSON_DEFAULT] est=46
                Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=46
                  Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=50
                    Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=50
                      Parallelism (Distribute Streams) [OPENJSON_DEFAULT] est=50
                        Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=50
                    Index Seek (Index Seek) seek [ts_9a626c7a_e_path] est=1
                  Clustered Index Seek (Clustered Index Seek) seek [PK__ts_9a626__3213E83FCD6B2E86] est=1
              Parallelism (Repartition Streams) [ts_9a626c7a_e_lvlpath] est=210,100
                Nested Loops (Inner Join) [ts_9a626c7a_e_lvlpath] est=210,100
                  Index Scan (Index Scan) [ts_9a626c7a_e_lvlpath] est=210,100
                  Filter (Filter) [OPENJSON_EXPLICIT] est=8
                    Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
            Parallelism (Repartition Streams) [ts_9a626c7a_e_owner] est=21
              Nested Loops (Inner Join) [ts_9a626c7a_e_owner] est=21
                Parallelism (Distribute Streams) [ts_9a626c7a_e_owner] est=22
                  Index Seek (Index Seek) seek [ts_9a626c7a_e_owner] est=22
                Clustered Index Seek (Clustered Index Seek) seek [PK__ts_9a626__3213E83FCD6B2E86] est=1
```

**apply=False, loop_join=True, force_order=False, plus_zero=False / entries**

```
Parallelism (Gather Streams) [ts_9a626c7a_e_lvlpath] est=220,187
  Hash Match (Union) [ts_9a626c7a_e_lvlpath] est=220,187
    Concatenation (Concatenation) [ts_9a626c7a_e_lvlpath] est=230,249
      Parallelism (Distribute Streams) [ts_9a626c7a_e_lvlpath] est=20,103
        Nested Loops (Inner Join) [ts_9a626c7a_e_lvlpath] est=20,103
          Compute Scalar (Compute Scalar)  est=1
            Constant Scan (Constant Scan)  est=1
          Index Seek (Index Seek) seek [ts_9a626c7a_e_lvlpath] est=20,103
      Parallelism (Repartition Streams) [OPENJSON_DEFAULT] est=46
        Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=46
          Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=50
            Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=50
              Parallelism (Distribute Streams) [OPENJSON_DEFAULT] est=50
                Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=50
            Index Seek (Index Seek) seek [ts_9a626c7a_e_path] est=1
          Clustered Index Seek (Clustered Index Seek) seek [PK__ts_9a626__3213E83FCD6B2E86] est=1
      Parallelism (Repartition Streams) [OPENJSON_EXPLICIT] est=210,100
        Nested Loops (Inner Join) [OPENJSON_EXPLICIT] est=210,100
          Nested Loops (Inner Join) [OPENJSON_EXPLICIT] est=230,203
            Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=50
              Parallelism (Distribute Streams) [OPENJSON_EXPLICIT] est=50
                Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
            Index Seek (Index Seek) seek [ts_9a626c7a_e_path] est=4,604
          Clustered Index Seek (Clustered Index Seek) seek [PK__ts_9a626__3213E83FCD6B2E86] est=1
    Parallelism (Repartition Streams) [ts_9a626c7a_e_owner] est=21
      Nested Loops (Inner Join) [ts_9a626c7a_e_owner] est=21
        Parallelism (Distribute Streams) [ts_9a626c7a_e_owner] est=22
          Index Seek (Index Seek) seek [ts_9a626c7a_e_owner] est=22
        Clustered Index Seek (Clustered Index Seek) seek [PK__ts_9a626__3213E83FCD6B2E86] est=1
```

**apply=False, loop_join=True, force_order=False, plus_zero=False / count**

```
Parallelism (Gather Streams) [ts_9a626c7a_e_lvlpath] est=1
  Compute Scalar (Compute Scalar) [ts_9a626c7a_e_lvlpath] est=1
    Hash Match (Aggregate) [ts_9a626c7a_e_lvlpath] est=1
      Hash Match (Inner Join) [ts_9a626c7a_e_lvlpath] est=210,428
        Hash Match (Aggregate) [ts_9a626c7a_e_lvlpath] est=220,187
          Concatenation (Concatenation) [ts_9a626c7a_e_lvlpath] est=230,270
            Concatenation (Concatenation) [ts_9a626c7a_e_lvlpath] est=230,249
              Parallelism (Distribute Streams) [ts_9a626c7a_e_lvlpath] est=20,103
                Nested Loops (Inner Join) [ts_9a626c7a_e_lvlpath] est=20,103
                  Compute Scalar (Compute Scalar)  est=1
                    Constant Scan (Constant Scan)  est=1
                  Index Seek (Index Seek) seek [ts_9a626c7a_e_lvlpath] est=20,103
              Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=46
                Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=50
                  Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=50
                    Parallelism (Distribute Streams) [OPENJSON_DEFAULT] est=50
                      Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=50
                  Index Seek (Index Seek) seek [ts_9a626c7a_e_path] est=1
                Clustered Index Seek (Clustered Index Seek) seek [PK__ts_9a626__3213E83FCD6B2E86] est=1
              Nested Loops (Inner Join) [OPENJSON_EXPLICIT] est=210,100
                Nested Loops (Inner Join) [OPENJSON_EXPLICIT] est=230,203
                  Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=50
                    Parallelism (Distribute Streams) [OPENJSON_EXPLICIT] est=50
                      Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
                  Index Seek (Index Seek) seek [ts_9a626c7a_e_path] est=4,604
                Clustered Index Seek (Clustered Index Seek) seek [PK__ts_9a626__3213E83FCD6B2E86] est=1
            Nested Loops (Inner Join) [ts_9a626c7a_e_owner] est=21
              Parallelism (Repartition Streams) [ts_9a626c7a_e_owner] est=22
                Index Seek (Index Seek) seek [ts_9a626c7a_e_owner] est=22
              Clustered Index Seek (Clustered Index Seek) seek [PK__ts_9a626__3213E83FCD6B2E86] est=1
        Index Scan (Index Scan) [ts_9a626c7a_c_entry] est=220,000
```

**apply=True, loop_join=False, force_order=False, plus_zero=False / entries**

```
Parallelism (Gather Streams) [ts_9a626c7a_e_lvlpath] est=220,187
  Hash Match (Union) [ts_9a626c7a_e_lvlpath] est=220,187
    Concatenation (Concatenation) [ts_9a626c7a_e_lvlpath] est=230,249
      Parallelism (Distribute Streams) [ts_9a626c7a_e_lvlpath] est=20,103
        Nested Loops (Inner Join) [ts_9a626c7a_e_lvlpath] est=20,103
          Compute Scalar (Compute Scalar)  est=1
            Constant Scan (Constant Scan)  est=1
          Index Seek (Index Seek) seek [ts_9a626c7a_e_lvlpath] est=20,103
      Parallelism (Repartition Streams) [OPENJSON_DEFAULT] est=46
        Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=46
          Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=50
            Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=50
              Parallelism (Distribute Streams) [OPENJSON_DEFAULT] est=50
                Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=50
            Index Seek (Index Seek) seek [ts_9a626c7a_e_path] est=1
          Clustered Index Seek (Clustered Index Seek) seek [PK__ts_9a626__3213E83FCD6B2E86] est=1
      Parallelism (Repartition Streams) [PK__ts_9a626__3213E83FCD6B2E86] est=210,100
        Nested Loops (Inner Join) [PK__ts_9a626__3213E83FCD6B2E86] est=210,100
          Clustered Index Scan (Clustered Index Scan) [PK__ts_9a626__3213E83FCD6B2E86] est=210,100
          Filter (Filter) [OPENJSON_EXPLICIT] est=8
            Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
    Parallelism (Repartition Streams) [ts_9a626c7a_e_owner] est=21
      Nested Loops (Inner Join) [ts_9a626c7a_e_owner] est=21
        Parallelism (Distribute Streams) [ts_9a626c7a_e_owner] est=22
          Index Seek (Index Seek) seek [ts_9a626c7a_e_owner] est=22
        Clustered Index Seek (Clustered Index Seek) seek [PK__ts_9a626__3213E83FCD6B2E86] est=1
```

**apply=True, loop_join=False, force_order=False, plus_zero=False / count**

```
Compute Scalar (Compute Scalar) [ts_9a626c7a_c_entry] est=1
  Stream Aggregate (Aggregate) [ts_9a626c7a_c_entry] est=1
    Parallelism (Gather Streams) [ts_9a626c7a_c_entry] est=5
      Stream Aggregate (Aggregate) [ts_9a626c7a_c_entry] est=5
        Hash Match (Inner Join) [ts_9a626c7a_c_entry] est=210,428
          Parallelism (Repartition Streams) [ts_9a626c7a_c_entry] est=220,000
            Index Scan (Index Scan) [ts_9a626c7a_c_entry] est=220,000
          Hash Match (Union) [ts_9a626c7a_e_lvlpath] est=220,187
            Concatenation (Concatenation) [ts_9a626c7a_e_lvlpath] est=230,249
              Parallelism (Distribute Streams) [ts_9a626c7a_e_lvlpath] est=20,103
                Nested Loops (Inner Join) [ts_9a626c7a_e_lvlpath] est=20,103
                  Compute Scalar (Compute Scalar)  est=1
                    Constant Scan (Constant Scan)  est=1
                  Index Seek (Index Seek) seek [ts_9a626c7a_e_lvlpath] est=20,103
              Parallelism (Repartition Streams) [OPENJSON_DEFAULT] est=46
                Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=46
                  Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=50
                    Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=50
                      Parallelism (Distribute Streams) [OPENJSON_DEFAULT] est=50
                        Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=50
                    Index Seek (Index Seek) seek [ts_9a626c7a_e_path] est=1
                  Clustered Index Seek (Clustered Index Seek) seek [PK__ts_9a626__3213E83FCD6B2E86] est=1
              Parallelism (Repartition Streams) [PK__ts_9a626__3213E83FCD6B2E86] est=210,100
                Nested Loops (Inner Join) [PK__ts_9a626__3213E83FCD6B2E86] est=210,100
                  Clustered Index Scan (Clustered Index Scan) [PK__ts_9a626__3213E83FCD6B2E86] est=210,100
                  Filter (Filter) [OPENJSON_EXPLICIT] est=8
                    Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
            Parallelism (Repartition Streams) [ts_9a626c7a_e_owner] est=21
              Nested Loops (Inner Join) [ts_9a626c7a_e_owner] est=21
                Parallelism (Distribute Streams) [ts_9a626c7a_e_owner] est=22
                  Index Seek (Index Seek) seek [ts_9a626c7a_e_owner] est=22
                Clustered Index Seek (Clustered Index Seek) seek [PK__ts_9a626__3213E83FCD6B2E86] est=1
```

**apply=False, loop_join=False, force_order=True, plus_zero=False / entries**

```
Parallelism (Gather Streams) [ts_9a626c7a_e_lvlpath] est=220,187
  Hash Match (Union) [ts_9a626c7a_e_lvlpath] est=220,187
    Concatenation (Concatenation) [ts_9a626c7a_e_lvlpath] est=230,249
      Parallelism (Distribute Streams) [ts_9a626c7a_e_lvlpath] est=20,103
        Nested Loops (Inner Join) [ts_9a626c7a_e_lvlpath] est=20,103
          Compute Scalar (Compute Scalar)  est=1
            Constant Scan (Constant Scan)  est=1
          Index Seek (Index Seek) seek [ts_9a626c7a_e_lvlpath] est=20,103
      Parallelism (Repartition Streams) [OPENJSON_DEFAULT] est=46
        Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=46
          Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=50
            Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=50
              Parallelism (Distribute Streams) [OPENJSON_DEFAULT] est=50
                Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=50
            Index Seek (Index Seek) seek [ts_9a626c7a_e_path] est=1
          Clustered Index Seek (Clustered Index Seek) seek [PK__ts_9a626__3213E83FCD6B2E86] est=1
      Parallelism (Repartition Streams) [OPENJSON_EXPLICIT] est=210,100
        Nested Loops (Inner Join) [OPENJSON_EXPLICIT] est=210,100
          Nested Loops (Inner Join) [OPENJSON_EXPLICIT] est=230,203
            Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=50
              Parallelism (Distribute Streams) [OPENJSON_EXPLICIT] est=50
                Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
            Index Seek (Index Seek) seek [ts_9a626c7a_e_path] est=4,604
          Clustered Index Seek (Clustered Index Seek) seek [PK__ts_9a626__3213E83FCD6B2E86] est=1
    Parallelism (Repartition Streams) [ts_9a626c7a_e_owner] est=21
      Nested Loops (Inner Join) [ts_9a626c7a_e_owner] est=21
        Parallelism (Distribute Streams) [ts_9a626c7a_e_owner] est=22
          Index Seek (Index Seek) seek [ts_9a626c7a_e_owner] est=22
        Clustered Index Seek (Clustered Index Seek) seek [PK__ts_9a626__3213E83FCD6B2E86] est=1
```

**apply=False, loop_join=False, force_order=True, plus_zero=False / count**

```
Parallelism (Gather Streams) [ts_9a626c7a_e_lvlpath] est=1
  Compute Scalar (Compute Scalar) [ts_9a626c7a_e_lvlpath] est=1
    Hash Match (Aggregate) [ts_9a626c7a_e_lvlpath] est=1
      Hash Match (Inner Join) [ts_9a626c7a_e_lvlpath] est=210,428
        Hash Match (Aggregate) [ts_9a626c7a_e_lvlpath] est=220,187
          Concatenation (Concatenation) [ts_9a626c7a_e_lvlpath] est=230,270
            Concatenation (Concatenation) [ts_9a626c7a_e_lvlpath] est=230,249
              Parallelism (Distribute Streams) [ts_9a626c7a_e_lvlpath] est=20,103
                Nested Loops (Inner Join) [ts_9a626c7a_e_lvlpath] est=20,103
                  Compute Scalar (Compute Scalar)  est=1
                    Constant Scan (Constant Scan)  est=1
                  Index Seek (Index Seek) seek [ts_9a626c7a_e_lvlpath] est=20,103
              Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=46
                Nested Loops (Inner Join) [OPENJSON_DEFAULT] est=50
                  Compute Scalar (Compute Scalar) [OPENJSON_DEFAULT] est=50
                    Parallelism (Distribute Streams) [OPENJSON_DEFAULT] est=50
                      Table-valued function (Table-valued function) [OPENJSON_DEFAULT] est=50
                  Index Seek (Index Seek) seek [ts_9a626c7a_e_path] est=1
                Clustered Index Seek (Clustered Index Seek) seek [PK__ts_9a626__3213E83FCD6B2E86] est=1
              Nested Loops (Inner Join) [OPENJSON_EXPLICIT] est=210,100
                Nested Loops (Inner Join) [OPENJSON_EXPLICIT] est=230,203
                  Compute Scalar (Compute Scalar) [OPENJSON_EXPLICIT] est=50
                    Parallelism (Distribute Streams) [OPENJSON_EXPLICIT] est=50
                      Table-valued function (Table-valued function) [OPENJSON_EXPLICIT] est=50
                  Index Seek (Index Seek) seek [ts_9a626c7a_e_path] est=4,604
                Clustered Index Seek (Clustered Index Seek) seek [PK__ts_9a626__3213E83FCD6B2E86] est=1
            Nested Loops (Inner Join) [ts_9a626c7a_e_owner] est=21
              Parallelism (Repartition Streams) [ts_9a626c7a_e_owner] est=22
                Index Seek (Index Seek) seek [ts_9a626c7a_e_owner] est=22
              Clustered Index Seek (Clustered Index Seek) seek [PK__ts_9a626__3213E83FCD6B2E86] est=1
        Index Scan (Index Scan) [ts_9a626c7a_c_entry] est=220,000
```

