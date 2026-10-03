## mariadb — writes: 1,000-user world plus /mid (1,001 rows), /mv (10,001), /big (200,000); 234,115 entries

Load: 2s.

Forms: `join` = the UPDATE through the range source (`UPDATE … FROM unnest` / `UPDATE … FROM … JOIN OPENJSON` / `UPDATE … JOIN JSON_TABLE` / `MERGE … USING JSON_TABLE`); `literal` = `WHERE (path > :lo AND path < :hi) OR …`; `in_sub` = `WHERE id IN (SELECT … FROM source JOIN e)`. Points always travel as `path IN (…)`. At most 500 pieces per statement; every statement is its own transaction.

| operation | form | statements | rows touched | total ms (median of runs) | labels after |
|---|---|---|---|---|---|
| posture /mid → shared (1,000 rows) | join; 1 points + 1 ranges (0 deeper postures cut) | 2 | 1,001 | 9 | all correct |
| posture /mid → shared (1,000 rows) | literal; 1 points + 1 ranges (0 deeper postures cut) | 2 | 1,001 | 8 | all correct |
| posture /big → shared (200,000 rows), one statement | join; 1 points + 1 ranges (0 deeper postures cut) | 2 | 200,000 | 909 | all correct |
| posture /big → shared (200,000 rows), chunked | join; 1 points + 1 ranges (0 deeper postures cut); keyset chunks of 50,000 rows | 9 | 200,000 | 1,031 | all correct |
| posture / → shared (root minus every deeper posture) | join; 1103 points + 2205 ranges (1,102 deeper postures cut) | 8 | 12,014 | 158 | all correct |
| posture / → shared (root minus every deeper posture) | literal; 1103 points + 2205 ranges (1,102 deeper postures cut) | 8 | 12,014 | 330 | all correct |
| move /mv → /home/u000000/mv (10,001 rows, open → private) | one UPDATE: path rewrite + destination label | 1 | 10,001 | 119 | all take the destination label |

### Plans

**posture /mid → shared (1,000 rows) / join (1 ranges)**

```
SIMPLE r type=ALL key=None rows=40 Table function: json_table
SIMPLE e type=ALL key=None rows=233496 Range checked for each record (index map: 0x2)
```

**posture /mid → shared (1,000 rows) / literal (1 ranges)**

```
SIMPLE ts_73f1d2f1_e type=range key=ts_73f1d2f1_e_path rows=1000 Using where
```

**posture / → shared (root minus every deeper posture) / join (500 ranges)**

```
SIMPLE r type=ALL key=None rows=40 Table function: json_table
SIMPLE e type=ALL key=None rows=233496 Range checked for each record (index map: 0x2)
```

**posture / → shared (root minus every deeper posture) / literal (500 ranges)**

```
SIMPLE ts_73f1d2f1_e type=range key=ts_73f1d2f1_e_path rows=500 Using where
```

**move /mv → /home/u000000/mv**

```
SIMPLE ts_73f1d2f1_e type=range key=ts_73f1d2f1_e_path rows=20639 Using where; Using buffer
```

Total wall time 15s.
