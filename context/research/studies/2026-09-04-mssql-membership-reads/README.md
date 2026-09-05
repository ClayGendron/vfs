# Study: SQL Server membership reads — where `IN (...)` stops seeking, and what to do about it

Companion to the memo `../../2026-09-04-mssql-membership-reads.md`.

All probes run against the live SQL Server 2025 container from
`docker/compose.test.yml` (`VFS_TEST_MSSQL_URL`, the `master` database,
collation `SQL_Latin1_General_CP1_CI_AS`, compatibility level 170).
The container is amd64 emulated under Rosetta on Apple Silicon, so
absolute times are inflated; read the ratios and the plan shapes. Each
probe mints its own `vfs_<hex>` table namespace through
`DatabaseStorage`, writes three non-ASCII "canary" paths through the
vfs write verb (`/n/café.py`, `/n/日本語.py`, `/n/emoji-😀.py`), grows
the entry table with a raw `INSERT ... SELECT ... FROM GENERATE_SERIES`
of minimal rows (`common.py`), refreshes statistics and clears the plan
cache after each growth step, and drops everything at the end.

The prior-art half of the memo came from two delegated surveys whose
reports are summarised there: a web sweep (Microsoft docs, Kornelis,
White, Kehayias, Bertrand, Ozar, the EF Core `OPENJSON` regression,
pyodbc's wiki, SQLAlchemy's tracker) and a study of twelve refreshed,
licence-checked reference clones — only jackrabbit-oak (`IN` lists
chunked at 2,048 with an in-statement 1,000-per-list `OR` split for
Oracle; `varbinary(512)` keys on SQL Server) and sqlalchemy (ORM
selectin chunk of 500; `setinputsizes` on by default "allowing
indexes against VARCHAR columns to take effect") had anything to say
about SQL Server. Nothing was copied from either.

Rerun (container up, env exported):

    cd context/research/studies/2026-09-04-mssql-membership-reads
    uv run python flip_probe.py                  # ~25 min: 20k, 200k, 1M rows × 7 arms × 8 list sizes
    uv run python codepage_probe.py              # ~1 min
    uv run python forms_probe.py                 # ~15 min: 20k and 1M rows × 14 forms × K ∈ {2067, 10000}
    uv run python forms_probe.py --forms in-nvarchar-512,in-cast-fs-2067,openjson-2000,openjson-20000,temp-1000,values-fs-1000 --ks 2067,20000   # the lock-escalation cells
    uv run python tvp_probe.py                   # ~1 min

`codepage_probe.py` creates a `vfs_utf8` database (UTF-8 default collation) on the container if it is missing and leaves it in place, like the earlier `vfs_rcsi`.

Plans are read back from `sys.dm_exec_query_stats` + `sys.dm_exec_query_plan`
by a marker comment each statement carries; locks from
`sys.dm_tran_locks` for the probe's own SPID before rollback; escalations
from `sys.dm_db_index_operational_stats` (`index_lock_promotion_*`).
Every cell runs up to three times in fresh sessions: *cold* is the first
run (it includes the statement's compile), *warm* the best of the rest.

## `flip_probe.py` — the seek→scan flip by list size, table size, key and bind typing

Arms (all `WITH (UPDLOCK)`, the `lock_rows` spelling `mkedge` uses):

| arm | what it is |
|---|---|
| `nvarchar` | vfs as shipped (`use_setinputsizes=False`): `path IN (@P nvarchar, ...)`, list holds the three canaries |
| `nvarchar-ascii` | the same with an all-ASCII list |
| `varchar` | a stock SQLAlchemy engine (`setinputsizes` on): `path IN (@P varchar, ...)` — the lossy form |
| `cast` | raw SQL: `path IN (CAST(@P COLLATE Latin1_General_100_BIN2_UTF8 AS varchar(1024)), ...)` |
| `cast-forceseek` | the cast form under `WITH (UPDLOCK, FORCESEEK)` |
| `forceseek` | the shipped nvarchar form under `WITH (UPDLOCK, FORCESEEK)` |
| `entry_id` | `entry_id IN (@P varbinary(16), ...)` — the binary key, no conversion |

Columns: found = rows returned; canaries = how many of the three
non-ASCII paths were found (blank for `entry_id`); compile = the plan's
`CompileTime` (ms); convert = `CONVERT_IMPLICIT` present; abort =
`StatementOptmEarlyAbortReason`; locks = `sys.dm_tran_locks` for the SPID
(`OBJECT:X` = escalated to a table lock; `KEY:U` = per-key update locks).

Results 2026-09-04, tree at `c3903d7` + spec 144 working copy
(the 1,000,000-row block ran separately with the `forceseek` and
`varchar` arms dropped — both were already settled at 20k/200k):

| rows | arm | list | found | canaries | cold ms | warm ms | compile ms | convert | abort | plan | locks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 20,000 | nvarchar | 64 | 64 | 3 | 201 | 143 | 48 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:X: 1 |
| 20,000 | nvarchar | 256 | 256 | 3 | 741 | 542 | 182 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:X: 1 |
| 20,000 | nvarchar | 512 | 512 | 3 | 1404 | 1074 | 350 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:X: 1 |
| 20,000 | nvarchar | 768 | 768 | 3 | 2162 | 1586 | 553 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:X: 1 |
| 20,000 | nvarchar | 1024 | 1024 | 3 | 2786 | 2045 | 703 | yes | TimeOut | SCAN:Filter>Clustered Index Scan | OBJECT:X: 1 |
| 20,000 | nvarchar | 1280 | 1280 | 3 | 3432 | 2547 | 860 | yes | TimeOut | SCAN:Filter>Clustered Index Scan | OBJECT:X: 1 |
| 20,000 | nvarchar | 1536 | 1536 | 3 | 4109 | 3058 | 1044 | yes | TimeOut | SCAN:Filter>Clustered Index Scan | OBJECT:X: 1 |
| 20,000 | nvarchar | 2067 | 2067 | 3 | 5479 | 4051 | 1413 | yes | TimeOut | SCAN:Filter>Clustered Index Scan | OBJECT:X: 1 |
| 20,000 | nvarchar-ascii | 64 | 64 | 0 | 53 | 3 | 46 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 128 |
| 20,000 | nvarchar-ascii | 256 | 256 | 0 | 191 | 14 | 172 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 512 |
| 20,000 | nvarchar-ascii | 512 | 512 | 0 | 384 | 26 | 346 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 1024 |
| 20,000 | nvarchar-ascii | 768 | 768 | 0 | 599 | 48 | 535 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 1536 |
| 20,000 | nvarchar-ascii | 1024 | 1024 | 0 | 2762 | 2051 | 687 | yes | TimeOut | SCAN:Filter>Clustered Index Scan | OBJECT:X: 1 |
| 20,000 | nvarchar-ascii | 1280 | 1280 | 0 | 3432 | 2554 | 866 | yes | TimeOut | SCAN:Filter>Clustered Index Scan | OBJECT:X: 1 |
| 20,000 | nvarchar-ascii | 1536 | 1536 | 0 | 4109 | 3037 | 1039 | yes | TimeOut | SCAN:Filter>Clustered Index Scan | OBJECT:X: 1 |
| 20,000 | nvarchar-ascii | 2067 | 2067 | 0 | 5575 | 4122 | 1440 | yes | TimeOut | SCAN:Filter>Clustered Index Scan | OBJECT:X: 1 |
| 20,000 | varchar | 64 | 62 | 1 | 26 | 3 | 18 | yes | GoodEnoughPlanFound | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 124 |
| 20,000 | varchar | 256 | 254 | 1 | 57 | 11 | 40 | yes | GoodEnoughPlanFound | SCAN:Hash Match>Merge Interval>Sort>Index Seek>Index Scan | KEY:U: 254, OBJECT:X: 1 |
| 20,000 | varchar | 512 | 510 | 1 | 115 | 15 | 88 | yes | GoodEnoughPlanFound | SCAN:Hash Match>Merge Interval>Sort>Index Seek>Index Scan | KEY:U: 510, OBJECT:X: 1 |
| 20,000 | varchar | 768 | 766 | 1 | 160 | 16 | 132 | yes | GoodEnoughPlanFound | SCAN:Hash Match>Clustered Index Scan | OBJECT:X: 1 |
| 20,000 | varchar | 1024 | 1022 | 1 | 236 | 15 | 207 | yes | GoodEnoughPlanFound | SCAN:Hash Match>Clustered Index Scan | OBJECT:X: 1 |
| 20,000 | varchar | 1280 | 1278 | 1 | 332 | 16 | 292 | yes | GoodEnoughPlanFound | SCAN:Hash Match>Clustered Index Scan | OBJECT:X: 1 |
| 20,000 | varchar | 1536 | 1534 | 1 | 427 | 18 | 382 | yes | GoodEnoughPlanFound | SCAN:Hash Match>Clustered Index Scan | OBJECT:X: 1 |
| 20,000 | varchar | 2067 | 2065 | 1 | 672 | 21 | 624 | yes | GoodEnoughPlanFound | SCAN:Hash Match>Clustered Index Scan | OBJECT:X: 1 |
| 20,000 | cast | 64 | 64 | 3 | 20 | 3 | 13 | no | GoodEnoughPlanFound | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 128 |
| 20,000 | cast | 256 | 256 | 3 | 54 | 11 | 38 | no | GoodEnoughPlanFound | SCAN:Hash Match>Merge Interval>Sort>Index Seek>Index Scan | KEY:U: 256, OBJECT:X: 1 |
| 20,000 | cast | 512 | 512 | 3 | 113 | 17 | 88 | no | GoodEnoughPlanFound | SCAN:Hash Match>Merge Interval>Sort>Index Seek>Index Scan | KEY:U: 512, OBJECT:X: 1 |
| 20,000 | cast | 768 | 768 | 3 | 187 | 18 | 155 | no | GoodEnoughPlanFound | SCAN:Hash Match>Merge Interval>Sort>Index Seek>Index Scan | KEY:U: 768, OBJECT:X: 1 |
| 20,000 | cast | 1024 | 1024 | 3 | 252 | 16 | 220 | no | GoodEnoughPlanFound | SCAN:Hash Match>Clustered Index Scan | OBJECT:X: 1 |
| 20,000 | cast | 1280 | 1280 | 3 | 337 | 16 | 300 | no | TimeOut | SCAN:Hash Match>Clustered Index Scan | OBJECT:X: 1 |
| 20,000 | cast | 1536 | 1536 | 3 | 449 | 18 | 403 | no | TimeOut | SCAN:Hash Match>Clustered Index Scan | OBJECT:X: 1 |
| 20,000 | cast | 2067 | 2067 | 3 | 721 | 23 | 663 | no | TimeOut | SCAN:Hash Match>Clustered Index Scan | OBJECT:X: 1 |
| 20,000 | cast-forceseek | 64 | 64 | 3 | 21 | 3 | 14 | no | GoodEnoughPlanFound | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 128 |
| 20,000 | cast-forceseek | 256 | 256 | 3 | 73 | 5 | 59 | no | GoodEnoughPlanFound | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 512 |
| 20,000 | cast-forceseek | 512 | 512 | 3 | 155 | 9 | 135 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 1024 |
| 20,000 | cast-forceseek | 768 | 768 | 3 | 253 | 13 | 226 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 1536 |
| 20,000 | cast-forceseek | 1024 | 1024 | 3 | 366 | 17 | 330 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 2048 |
| 20,000 | cast-forceseek | 1280 | 1280 | 3 | 715 | 21 | 488 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 2560 |
| 20,000 | cast-forceseek | 1536 | 1536 | 3 | 648 | 24 | 593 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 3072 |
| 20,000 | cast-forceseek | 2067 | 2067 | 3 | 1216 | 32 | 1141 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 4134 |
| 20,000 | forceseek | 64 | 64 | 3 | 199 | 149 | 49 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:X: 1 |
| 20,000 | forceseek | 256 | 256 | 3 | 759 | 563 | 186 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:X: 1 |
| 20,000 | forceseek | 512 | 512 | 3 | 1515 | 1098 | 372 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:X: 1 |
| 20,000 | forceseek | 768 | 768 | 3 | 2190 | 1618 | 558 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:X: 1 |
| 20,000 | forceseek | 1024 | 1024 | 3 | 2979 | 2140 | 779 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:X: 1 |
| 20,000 | forceseek | 1280 | 1280 | 3 | 3683 | 2663 | 949 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:X: 1 |
| 20,000 | forceseek | 1536 | 1536 | 3 | 4419 | 3191 | 1157 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:X: 1 |
| 20,000 | forceseek | 2067 | 2067 | 3 | 5928 | 4277 | 1609 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:X: 1 |
| 20,000 | entry_id | 64 | 64 |  | 26 | 5 | 15 | no | GoodEnoughPlanFound | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 128 |
| 20,000 | entry_id | 256 | 256 |  | 54 | 18 | 30 | no | GoodEnoughPlanFound | SCAN:Hash Match>Merge Interval>Sort>Index Seek>Index Scan | KEY:U: 256, OBJECT:X: 1 |
| 20,000 | entry_id | 512 | 512 |  | 97 | 24 | 71 | no | GoodEnoughPlanFound | SCAN:Hash Match>Merge Interval>Sort>Index Seek>Index Scan | KEY:U: 512, OBJECT:X: 1 |
| 20,000 | entry_id | 768 | 768 |  | 162 | 27 | 129 | no | GoodEnoughPlanFound | SCAN:Hash Match>Merge Interval>Sort>Index Seek>Index Scan | KEY:U: 768, OBJECT:X: 1 |
| 20,000 | entry_id | 1024 | 1024 |  | 226 | 20 | 196 | no | GoodEnoughPlanFound | SCAN:Hash Match>Clustered Index Scan | OBJECT:X: 1 |
| 20,000 | entry_id | 1280 | 1280 |  | 325 | 22 | 280 | no | GoodEnoughPlanFound | SCAN:Hash Match>Clustered Index Scan | OBJECT:X: 1 |
| 20,000 | entry_id | 1536 | 1536 |  | 419 | 23 | 373 | no | GoodEnoughPlanFound | SCAN:Hash Match>Clustered Index Scan | OBJECT:X: 1 |
| 20,000 | entry_id | 2067 | 2067 |  | 674 | 27 | 623 | no | GoodEnoughPlanFound | SCAN:Hash Match>Clustered Index Scan | OBJECT:X: 1 |
| 200,000 | nvarchar | 64 | 64 | 3 | 1424 | 1381 | 35 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:X: 1 |
| 200,000 | nvarchar | 256 | 256 | 3 | 5543 | 5399 | 129 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:X: 1 |
| 200,000 | nvarchar | 512 | 512 | 3 | 11223 | 10781 | 260 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:X: 1 |
| 200,000 | nvarchar | 768 | 768 | 3 | 16556 | nan | 419 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:X: 1 |
| 200,000 | nvarchar | 1024 | 1024 | 3 | 22100 | nan | 528 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:X: 1 |
| 200,000 | nvarchar | 1280 | 1280 | 3 | 27816 | nan | 655 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:X: 1 |
| 200,000 | nvarchar | 1536 | 1536 | 3 | 33441 | nan | 809 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:X: 1 |
| 200,000 | nvarchar | 2067 | 2067 | 3 | 45135 | nan | ? | no | ? | None | OBJECT:X: 1 |
| 200,000 | nvarchar-ascii | 64 | 64 | 0 | 42 | 7 | 34 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 128 |
| 200,000 | nvarchar-ascii | 256 | 256 | 0 | 150 | 18 | 126 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 512 |
| 200,000 | nvarchar-ascii | 512 | 512 | 0 | 308 | 35 | 256 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 1024 |
| 200,000 | nvarchar-ascii | 768 | 768 | 0 | 476 | 66 | 387 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 1536 |
| 200,000 | nvarchar-ascii | 1024 | 1024 | 0 | 644 | 93 | 528 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 2048 |
| 200,000 | nvarchar-ascii | 1280 | 1280 | 0 | 829 | 131 | 669 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 2560 |
| 200,000 | nvarchar-ascii | 1536 | 1536 | 0 | 1036 | 178 | 817 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 3072 |
| 200,000 | nvarchar-ascii | 2067 | 2067 | 0 | 1493 | 289 | 1145 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 4134 |
| 200,000 | varchar | 64 | 62 | 1 | 23 | 3 | 15 | yes | GoodEnoughPlanFound | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 124 |
| 200,000 | varchar | 256 | 254 | 1 | 68 | 6 | 55 | yes | GoodEnoughPlanFound | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 508 |
| 200,000 | varchar | 512 | 510 | 1 | 137 | 12 | 116 | yes | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 1020 |
| 200,000 | varchar | 768 | 766 | 1 | 228 | 28 | 199 | yes | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 1532 |
| 200,000 | varchar | 1024 | 1022 | 1 | 334 | 22 | 289 | yes | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 2044 |
| 200,000 | varchar | 1280 | 1278 | 1 | 453 | 69 | 357 | yes | TimeOut | SCAN:Hash Match>Merge Interval>Sort>Index Seek>Index Scan | KEY:U: 1278, OBJECT:X: 1 |
| 200,000 | varchar | 1536 | 1534 | 1 | 573 | 69 | 487 | yes | TimeOut | SCAN:Hash Match>Merge Interval>Sort>Index Seek>Index Scan | KEY:U: 1534, OBJECT:X: 1 |
| 200,000 | varchar | 2067 | 2065 | 1 | 916 | 83 | 789 | yes | TimeOut | SCAN:Hash Match>Merge Interval>Sort>Index Seek>Index Scan | KEY:U: 2065, OBJECT:X: 1 |
| 200,000 | cast | 64 | 64 | 3 | 27 | 7 | 15 | no | GoodEnoughPlanFound | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 128 |
| 200,000 | cast | 256 | 256 | 3 | 57 | 14 | 41 | no | GoodEnoughPlanFound | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 512 |
| 200,000 | cast | 512 | 512 | 3 | 113 | 15 | 88 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 1024 |
| 200,000 | cast | 768 | 768 | 3 | 178 | 22 | 146 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 1536 |
| 200,000 | cast | 1024 | 1024 | 3 | 264 | 18 | 227 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 2048 |
| 200,000 | cast | 1280 | 1280 | 3 | 420 | 56 | 346 | no | TimeOut | SCAN:Hash Match>Merge Interval>Sort>Index Seek>Index Scan | KEY:U: 1280, OBJECT:X: 1 |
| 200,000 | cast | 1536 | 1536 | 3 | 565 | 57 | 472 | no | TimeOut | SCAN:Hash Match>Merge Interval>Sort>Index Seek>Index Scan | KEY:U: 1536, OBJECT:X: 1 |
| 200,000 | cast | 2067 | 2067 | 3 | 853 | 70 | 745 | no | TimeOut | SCAN:Hash Match>Merge Interval>Sort>Index Seek>Index Scan | KEY:U: 2067, OBJECT:X: 1 |
| 200,000 | cast-forceseek | 64 | 64 | 3 | 27 | 4 | 19 | no | GoodEnoughPlanFound | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 128 |
| 200,000 | cast-forceseek | 256 | 256 | 3 | 82 | 10 | 69 | no | GoodEnoughPlanFound | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 512 |
| 200,000 | cast-forceseek | 512 | 512 | 3 | 209 | 15 | 183 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 1024 |
| 200,000 | cast-forceseek | 768 | 768 | 3 | 345 | 16 | 310 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 1536 |
| 200,000 | cast-forceseek | 1024 | 1024 | 3 | 495 | 21 | 452 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 2048 |
| 200,000 | cast-forceseek | 1280 | 1280 | 3 | 678 | 22 | 630 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 2560 |
| 200,000 | cast-forceseek | 1536 | 1536 | 3 | 888 | 28 | 830 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 3072 |
| 200,000 | cast-forceseek | 2067 | 2067 | 3 | 1460 | 39 | 1382 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 4134 |
| 200,000 | forceseek | 64 | 64 | 3 | 1446 | 1374 | 36 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:X: 1 |
| 200,000 | forceseek | 256 | 256 | 3 | 5613 | 5459 | 141 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:X: 1 |
| 200,000 | forceseek | 512 | 512 | 3 | 11127 | 10835 | 279 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:X: 1 |
| 200,000 | forceseek | 768 | 768 | 3 | 16661 | nan | 416 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:X: 1 |
| 200,000 | forceseek | 1024 | 1024 | 3 | 22175 | nan | 559 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:X: 1 |
| 200,000 | forceseek | 1280 | 1280 | 3 | 27825 | nan | 692 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:X: 1 |
| 200,000 | forceseek | 1536 | 1536 | 3 | 33592 | nan | 842 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:X: 1 |
| 200,000 | forceseek | 2067 | 2067 | 3 | 45923 | nan | 1985 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:X: 1 |
| 200,000 | entry_id | 64 | 64 |  | 16 | 6 | 9 | no | GoodEnoughPlanFound | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 128 |
| 200,000 | entry_id | 256 | 256 |  | 46 | 16 | 31 | no | GoodEnoughPlanFound | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 512 |
| 200,000 | entry_id | 512 | 512 |  | 92 | 15 | 68 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 1024 |
| 200,000 | entry_id | 768 | 768 |  | 154 | 17 | 120 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 1536 |
| 200,000 | entry_id | 1024 | 1024 |  | 226 | 27 | 183 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 2048 |
| 200,000 | entry_id | 1280 | 1280 |  | 352 | 64 | 278 | no | TimeOut | SCAN:Hash Match>Merge Interval>Sort>Index Seek>Index Scan | KEY:U: 1280, OBJECT:X: 1 |
| 200,000 | entry_id | 1536 | 1536 |  | 470 | 69 | 384 | no | TimeOut | SCAN:Hash Match>Merge Interval>Sort>Index Seek>Index Scan | KEY:U: 1536, OBJECT:X: 1 |
| 200,000 | entry_id | 2067 | 2067 |  | 758 | 82 | 645 | no | TimeOut | SCAN:Hash Match>Merge Interval>Sort>Index Seek>Index Scan | KEY:U: 2067, OBJECT:X: 1 |
| 1,000,000 | nvarchar-ascii | 64 | 64 | 0 | 60 | 6 | 52 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 128 |
| 1,000,000 | nvarchar-ascii | 256 | 256 | 0 | 231 | 13 | 203 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 512 |
| 1,000,000 | nvarchar-ascii | 512 | 512 | 0 | 448 | 29 | 403 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 1024 |
| 1,000,000 | nvarchar-ascii | 768 | 768 | 0 | 687 | 52 | 609 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 1536 |
| 1,000,000 | nvarchar-ascii | 1024 | 1024 | 0 | 930 | 81 | 822 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 2048 |
| 1,000,000 | nvarchar-ascii | 1280 | 1280 | 0 | 1212 | 119 | 1054 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 2560 |
| 1,000,000 | nvarchar-ascii | 1536 | 1536 | 0 | 1471 | 164 | 1275 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 3072 |
| 1,000,000 | nvarchar-ascii | 2067 | 2067 | 0 | 2097 | 282 | 1763 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 4134 |
| 1,000,000 | cast | 64 | 64 | 3 | 19 | 6 | 12 | no | GoodEnoughPlanFound | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 128 |
| 1,000,000 | cast | 256 | 256 | 3 | 49 | 6 | 36 | no | GoodEnoughPlanFound | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 512 |
| 1,000,000 | cast | 512 | 512 | 3 | 107 | 10 | 86 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 1024 |
| 1,000,000 | cast | 768 | 768 | 3 | 171 | 15 | 142 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 1536 |
| 1,000,000 | cast | 1024 | 1024 | 3 | 260 | 17 | 220 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 2048 |
| 1,000,000 | cast | 1280 | 1280 | 3 | 361 | 22 | 316 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 2560 |
| 1,000,000 | cast | 1536 | 1536 | 3 | 495 | 28 | 440 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 3072 |
| 1,000,000 | cast | 2067 | 2067 | 3 | 849 | 33 | 772 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 4134 |
| 1,000,000 | cast-forceseek | 64 | 64 | 3 | 20 | 3 | 14 | no | GoodEnoughPlanFound | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 128 |
| 1,000,000 | cast-forceseek | 256 | 256 | 3 | 76 | 6 | 64 | no | GoodEnoughPlanFound | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 512 |
| 1,000,000 | cast-forceseek | 512 | 512 | 3 | 178 | 11 | 159 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 1024 |
| 1,000,000 | cast-forceseek | 768 | 768 | 3 | 322 | 14 | 290 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 1536 |
| 1,000,000 | cast-forceseek | 1024 | 1024 | 3 | 498 | 19 | 459 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 2048 |
| 1,000,000 | cast-forceseek | 1280 | 1280 | 3 | 688 | 21 | 643 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 2560 |
| 1,000,000 | cast-forceseek | 1536 | 1536 | 3 | 915 | 27 | 862 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 3072 |
| 1,000,000 | cast-forceseek | 2067 | 2067 | 3 | 1642 | 34 | 1567 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 4134 |
| 1,000,000 | entry_id | 64 | 64 |  | 17 | 4 | 9 | no | GoodEnoughPlanFound | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 128 |
| 1,000,000 | entry_id | 256 | 256 |  | 43 | 6 | 28 | no | GoodEnoughPlanFound | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 512 |
| 1,000,000 | entry_id | 512 | 512 |  | 83 | 12 | 65 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 1024 |
| 1,000,000 | entry_id | 768 | 768 |  | 138 | 16 | 114 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 1536 |
| 1,000,000 | entry_id | 1024 | 1024 |  | 214 | 20 | 181 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 2048 |
| 1,000,000 | entry_id | 1280 | 1280 |  | 307 | 24 | 266 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 2560 |
| 1,000,000 | entry_id | 1536 | 1536 |  | 414 | 29 | 367 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 3072 |
| 1,000,000 | entry_id | 2067 | 2067 |  | 671 | 36 | 611 | no | TimeOut | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 4134 |
| 1,000,000 | nvarchar | 64 | 64 | 3 | 6944 | 6845 | 54 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:X: 1 |
| 1,000,000 | nvarchar | 256 | 256 | 3 | 27049 | nan | 216 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:X: 1 |
| 1,000,000 | nvarchar | 512 | 512 | 3 | 53515 | nan | 398 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:X: 1 |
| 1,000,000 | nvarchar | 768 | 768 | 3 | 80126 | nan | 604 | yes | GoodEnoughPlanFound | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:X: 1 |
| 1,000,000 | nvarchar | >768 | skipped: SEEK already 80s |

## `codepage_probe.py` — which element costs the table, and where a `varchar` bind is lossless

Part 1: the shipped nvarchar form, a 64-element list on 20,000 rows, with
one non-ASCII path at a time.

| list | found | canaries | ms | plan | locks |
|---|---|---|---|---|---|
| 64 ascii                           |   64 | 0 |      60 | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek params=['nvarchar(26)'] | {'OBJECT:IX': 1, 'KEY:U': 128} |
| 63 ascii + '/n/café.py'            |   64 | 1 |      62 | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek params=['nvarchar(20)', 'nvarchar(26)'] | {'OBJECT:IX': 1, 'KEY:U': 128} |
| 63 ascii + '/n/日本語.py'             |   64 | 1 |     200 | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek params=['nvarchar(18)', 'nvarchar(26)'] | {'OBJECT:X': 1} |
| 63 ascii + '/n/emoji-😀.py'         |   64 | 1 |      59 | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek params=['nvarchar(26)', 'nvarchar(28)'] | {'OBJECT:IX': 1, 'KEY:U': 128} |
| 61 ascii + all three               |   64 | 3 |     202 | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek params=['nvarchar(18)', 'nvarchar(20)', 'nvarchar(26)', 'nvarchar(28)'] | {'OBJECT:X': 1} |

Part 2: a stock SQLAlchemy engine (`setinputsizes` on → `varchar` binds)
against `master` (CP-1252 default collation) and against a database
created `COLLATE Latin1_General_100_BIN2_UTF8`, 64-element list, 20,000 rows.

| database / arm | found | canaries | ms | plan | locks |
|---|---|---|---|---|---|
| master CP-1252 / varchar (setinputsizes) |   62 | 1 |      34 | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek params=['varchar(18)', 'varchar(20)', 'varchar(26)', 'varchar(28)'] | {'OBJECT:IX': 1, 'KEY:U': 124} |
| master CP-1252 / nvarchar (vfs)    |   64 | 3 |     201 | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek params=['nvarchar(18)', 'nvarchar(20)', 'nvarchar(26)', 'nvarchar(28)'] | {'OBJECT:X': 1} |
| vfs_utf8 / varchar (setinputsizes) |   64 | 3 |      27 | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek params=['varchar(18)', 'varchar(20)', 'varchar(26)', 'varchar(28)'] | {'OBJECT:IX': 1, 'KEY:U': 128} |
| vfs_utf8 / nvarchar (vfs)          |   64 | 3 |     203 | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek params=['nvarchar(18)', 'nvarchar(20)', 'nvarchar(26)', 'nvarchar(28)'] | {'OBJECT:X': 1} |

## `forms_probe.py` — alternative membership forms at K ∈ {2,067, 10,000, 20,000}

Every form resolves K sorted paths to `(path, entry_id)` in one
transaction under `WITH (UPDLOCK)`; the whole resolve is timed; locks
are read before rollback. `in-nvarchar-*` rows use all-ASCII lists
(one CJK element makes every shipped-form statement a table-range
seek — see `codepage_probe.py`); every other form carries the three
canaries. `plan` is the *last* statement's plan (a remainder chunk can
differ from the full chunks — e.g. `in-cast-1000` at K=2,067 shows the
67-element remainder's seek while the two 1,000-element statements
scanned and took the table lock). The `promotions` column is the delta
of `SUM(index_lock_promotion_attempt_count), SUM(index_lock_promotion_count)`
and is **not trustworthy here**: it went negative both when read
inside the transaction (first run) and from an independent autocommit
connection (second run), and a direct check (three reads with nothing
between, then a full-table `WITH (UPDLOCK)` scan that held `OBJECT:X`)
showed the counters unchanged. Use the `locks` column: `OBJECT:X` is a
table-level exclusive lock on the entry table; `KEY:U` counts are
two per row (path index key + clustered key).

First run (`--sizes 20000,1000000 --ks 2067,10000`, all forms; `tvp` and
`temp-2000` failed — see below):

| rows | form | K | found | canaries | stmts | cold ms | warm ms | compile ms | est rows | plan | locks | promotions |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 20,000 | in-nvarchar-512 | 2067 | 2067 | 0 | 5 | 519 | 124 | 15 | 1.87496 | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 4134 | (-4, 0) |
| 20,000 | in-nvarchar-2067 | 2067 | 2067 | 0 | 1 | 5549 | 4060 | 1452 | 3.74984 | SCAN:Filter>Clustered Index Scan | OBJECT:X: 1 | (-4, -1) |
| 20,000 | in-cast-512 | 2067 | 2067 | 3 | 5 | 149 | 53 | 7 | 19.0 | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | KEY:U: 512, OBJECT:X: 1 | (-4, -1) |
| 20,000 | in-cast-1000 | 2067 | 2067 | 3 | 3 | 263 | 32 | 17 | 67.0 | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:X: 1 | (-4, -1) |
| 20,000 | in-cast-2067 | 2067 | 2067 | 3 | 1 | 682 | 21 | 627 | 2067.0 | SCAN:Hash Match>Clustered Index Scan | OBJECT:X: 1 | (-4, -1) |
| 20,000 | in-cast-fs-2067 | 2067 | 2067 | 3 | 1 | 1133 | 29 | 1062 | 2067.0 | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 4134 | (-6, 0) |
| 20,000 | openjson-2067 | 2067 | 2067 | 3 | 1 | 24 | 13 | 6 | 7.07107 | SEEK:Sort>Table-valued function>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 4134 | (-4, 0) |
| 20,000 | openjson-10000 | 2067 | 2067 | 3 | 1 | 22 | 14 | 5 | 7.07107 | SEEK:Sort>Table-valued function>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 4134 | (-4, 0) |
| 20,000 | openjson-with | 2067 | 2065 | 1 | 1 | 22 | 16 | 3 | 50.0 | SEEK:Table-valued function>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 4130 | (-8, 0) |
| 20,000 | values-1000 | 2067 | 2067 | 3 | 3 | 77 | 28 | 5 | 67.0 | SEEK:Index Seek>Clustered Index Seek | OBJECT:X: 1 | (-4, -1) |
| 20,000 | values-2067 | 2067 | 2067 | 3 | 1 | 114 | 16 | 77 | 2067.0 | SCAN:Hash Match>Clustered Index Scan | OBJECT:X: 1 | (-4, -1) |
| 20,000 | values-fs-2067 | 2067 | 2067 | 3 | 1 | 121 | 13 | 84 | 2067.0 | SEEK:Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 4134 | (-8, 0) |
| 20,000 | tvp | 2067 | — | — | — | — | — | ERROR: (pyodbc.ProgrammingError) ("A TVP's rows must all be the same size.", 'HY000') | — | — |
| 20,000 | temp-2000 | 2067 | — | — | — | — | — | ERROR: (pyodbc.ProgrammingError) ('42000', '[42000] [Microsoft][ODBC Driver 18 for SQL Server][SQL Server]The number of row value expressions in the I | — | — |
| 20,000 | in-nvarchar-512 | 10000 | 10000 | 0 | 20 | 1161 | 597 | 194 | 3.74984 | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 20000 | (-30, 0) |
| 20,000 | in-nvarchar-2067 | 10000 | 10000 | 0 | 5 | 22560 | nan | 1178 | 3.74984 | SCAN:Filter>Clustered Index Scan | OBJECT:X: 1 | (4, 1) |
| 20,000 | in-cast-512 | 10000 | 10000 | 3 | 20 | 375 | 221 | 41 | 272.0 | SCAN:Hash Match>Merge Interval>Sort>Index Seek>Index Scan | KEY:U: 512, OBJECT:X: 1 | (-4, -1) |
| 20,000 | in-cast-1000 | 10000 | 10000 | 3 | 10 | 554 | 126 | 198 | 1000.0 | SCAN:Hash Match>Clustered Index Scan | OBJECT:X: 1 | (-4, -1) |
| 20,000 | in-cast-2067 | 10000 | 10000 | 3 | 5 | 1246 | 86 | 467 | 1732.0 | SCAN:Hash Match>Clustered Index Scan | OBJECT:X: 1 | (-4, -1) |
| 20,000 | in-cast-fs-2067 | 10000 | 10000 | 3 | 5 | 1966 | 154 | 667 | 1732.0 | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 20000 | (-45, 0) |
| 20,000 | openjson-2067 | 10000 | 10000 | 3 | 5 | 75 | 72 | 5 | 7.07107 | SEEK:Sort>Table-valued function>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 20000 | (-30, 0) |
| 20,000 | openjson-10000 | 10000 | 10000 | 3 | 1 | 61 | 56 | 5 | 7.07107 | SEEK:Sort>Table-valued function>Index Seek>Clustered Index Seek | OBJECT:X: 1 | (-13, -1) |
| 20,000 | values-1000 | 10000 | 10000 | 3 | 10 | 195 | 101 | 35 | 1000.0 | SCAN:Hash Match>Clustered Index Scan | OBJECT:X: 1 | (-4, -1) |
| 20,000 | values-2067 | 10000 | 10000 | 3 | 5 | 240 | 61 | 63 | 1731.01 | SCAN:Hash Match>Clustered Index Scan | OBJECT:X: 1 | (-4, -1) |
| 20,000 | values-fs-2067 | 10000 | 10000 | 3 | 5 | 248 | 66 | 62 | 1731.01 | SEEK:Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 20000 | (-60, 0) |
| 20,000 | tvp | 10000 | — | — | — | — | — | ERROR: (pyodbc.ProgrammingError) ("A TVP's rows must all be the same size.", 'HY000') | — | — |
| 20,000 | temp-2000 | 10000 | — | — | — | — | — | ERROR: (pyodbc.ProgrammingError) ('42000', '[42000] [Microsoft][ODBC Driver 18 for SQL Server][SQL Server]The number of row value expressions in the I | — | — |
| 1,000,000 | in-nvarchar-512 | 2067 | 2067 | 0 | 5 | 538 | 126 | 16 | 1.875 | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 4134 | (-4, 0) |
| 1,000,000 | in-nvarchar-2067 | 2067 | 2067 | 0 | 1 | 1930 | 267 | 1615 | 1.875 | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 4134 | (-4, 0) |
| 1,000,000 | in-cast-512 | 2067 | 2067 | 3 | 5 | 119 | 32 | 6 | 19.0 | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 4134 | (-6, 0) |
| 1,000,000 | in-cast-1000 | 2067 | 2067 | 3 | 3 | 247 | 25 | 16 | 67.0 | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 4134 | (-6, 0) |
| 1,000,000 | in-cast-2067 | 2067 | 2067 | 3 | 1 | 699 | 30 | 631 | 2067.0 | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 4134 | (-6, 0) |
| 1,000,000 | in-cast-fs-2067 | 2067 | 2067 | 3 | 1 | 1403 | 30 | 1337 | 2067.0 | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 4134 | (-6, 0) |
| 1,000,000 | openjson-2067 | 2067 | 2067 | 3 | 1 | 22 | 16 | 5 | 7.07107 | SEEK:Sort>Table-valued function>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 4134 | (-4, 0) |
| 1,000,000 | openjson-10000 | 2067 | 2067 | 3 | 1 | 25 | 19 | 5 | 7.07107 | SEEK:Sort>Table-valued function>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 4134 | (-4, 0) |
| 1,000,000 | openjson-with | 2067 | 2065 | 1 | 1 | 22 | 16 | 3 | 50.0 | SEEK:Table-valued function>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 4130 | (-8, 0) |
| 1,000,000 | values-1000 | 2067 | 2067 | 3 | 3 | 66 | 22 | 4 | 67.0 | SEEK:Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 4134 | (-6, 0) |
| 1,000,000 | values-2067 | 2067 | 2067 | 3 | 1 | 126 | 14 | 86 | 2067.0 | SEEK:Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 4134 | (-8, 0) |
| 1,000,000 | values-fs-2067 | 2067 | 2067 | 3 | 1 | 119 | 15 | 81 | 2067.0 | SEEK:Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 4134 | (-8, 0) |
| 1,000,000 | tvp | 2067 | — | — | — | — | — | ERROR: (pyodbc.ProgrammingError) ("A TVP's rows must all be the same size.", 'HY000') | — | — |
| 1,000,000 | temp-2000 | 2067 | — | — | — | — | — | ERROR: (pyodbc.ProgrammingError) ('42000', '[42000] [Microsoft][ODBC Driver 18 for SQL Server][SQL Server]The number of row value expressions in the I | — | — |
| 1,000,000 | in-nvarchar-512 | 10000 | 10000 | 0 | 20 | 1226 | 579 | 205 | 1.875 | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 20000 | (-30, 0) |
| 1,000,000 | in-nvarchar-2067 | 10000 | 10000 | 0 | 5 | 4339 | 1287 | 1354 | 1.875 | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 20000 | (-30, 0) |
| 1,000,000 | in-cast-512 | 10000 | 10000 | 3 | 20 | 278 | 143 | 36 | 272.0 | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 20000 | (-45, 0) |
| 1,000,000 | in-cast-1000 | 10000 | 10000 | 3 | 10 | 558 | 104 | 202 | 1000.0 | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 20000 | (-45, 0) |
| 1,000,000 | in-cast-2067 | 10000 | 10000 | 3 | 5 | 1280 | 99 | 479 | 1732.0 | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 20000 | (-44, 0) |
| 1,000,000 | in-cast-fs-2067 | 10000 | 10000 | 3 | 5 | 2464 | 103 | 978 | 1732.0 | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 20000 | (-44, 0) |
| 1,000,000 | openjson-2067 | 10000 | 10000 | 3 | 5 | 92 | 88 | 5 | 7.07107 | SEEK:Sort>Table-valued function>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 20000 | (-30, 0) |
| 1,000,000 | openjson-10000 | 10000 | 10000 | 3 | 1 | 90 | 61 | 5 | 7.07107 | SEEK:Sort>Table-valued function>Index Seek>Clustered Index Seek | OBJECT:X: 1 | (-12, -1) |
| 1,000,000 | values-1000 | 10000 | 10000 | 3 | 10 | 174 | 84 | 37 | 1000.0 | SEEK:Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 20000 | (-47, 0) |
| 1,000,000 | values-2067 | 10000 | 10000 | 3 | 5 | 260 | 78 | 64 | 1732.0 | SEEK:Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 20000 | (-48, 0) |
| 1,000,000 | values-fs-2067 | 10000 | 10000 | 3 | 5 | 258 | 71 | 63 | 1732.0 | SEEK:Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 20000 | (-48, 0) |
| 1,000,000 | tvp | 10000 | — | — | — | — | — | ERROR: (pyodbc.ProgrammingError) ("A TVP's rows must all be the same size.", 'HY000') | — | — |
| 1,000,000 | temp-2000 | 10000 | — | — | — | — | — | ERROR: (pyodbc.ProgrammingError) ('42000', '[42000] [Microsoft][ODBC Driver 18 for SQL Server][SQL Server]The number of row value expressions in the I | — | — |

Second run (`--forms in-nvarchar-512,in-cast-fs-2067,openjson-2000,openjson-20000,temp-1000,values-fs-1000 --ks 2067,20000 --sizes 20000,1000000`),
the K=20,000 cells being the lock-escalation question (10,000 edges →
up to 20,000 endpoint rows locked in one transaction):

| rows | form | K | found | canaries | stmts | cold ms | warm ms | compile ms | est rows | plan | locks | promotions |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 20,000 | in-nvarchar-512 | 2067 | 2067 | 0 | 5 | 516 | 118 | 16 | 1.87496 | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 4134 | (-4, 0) |
| 20,000 | in-cast-fs-2067 | 2067 | 2067 | 3 | 1 | 1194 | 43 | 1121 | 2067.0 | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 4134 | (-6, 0) |
| 20,000 | openjson-2000 | 2067 | 2067 | 3 | 2 | 40 | 21 | 6 | 7.07107 | SEEK:Sort>Table-valued function>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 4134 | (-4, 0) |
| 20,000 | openjson-20000 | 2067 | 2067 | 3 | 1 | 26 | 16 | 6 | 7.07107 | SEEK:Sort>Table-valued function>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 4134 | (-4, 0) |
| 20,000 | temp-1000 | 2067 | 2067 | 3 | 6 | 105 | 35 | 8 | 2067.0 | SCAN:Hash Match>Clustered Index Scan | OBJECT:IX: 9, OBJECT:Sch-M: 2, KEY:X: 21, OBJECT:X: 1 | (-4, -1) |
| 20,000 | values-fs-1000 | 2067 | 2067 | 3 | 3 | 74 | 17 | 5 | 67.0 | SEEK:Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 4134 | (-8, 0) |
| 20,000 | in-nvarchar-512 | 20000 | 20000 | 0 | 40 | 1672 | 1249 | 24 | 3.74984 | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 40000 | (-62, 0) |
| 20,000 | in-cast-fs-2067 | 20000 | 20000 | 3 | 10 | 2082 | 350 | 522 | 1397.0 | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 40000 | (-93, 0) |
| 20,000 | openjson-2000 | 20000 | 20000 | 3 | 10 | 156 | 157 | 8 | 7.07107 | SEEK:Sort>Table-valued function>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 40000 | (-62, 0) |
| 20,000 | openjson-20000 | 20000 | 20000 | 3 | 1 | 163 | 161 | 7 | 7.07107 | SEEK:Sort>Table-valued function>Index Seek>Clustered Index Seek | OBJECT:X: 1 | (-13, -1) |
| 20,000 | temp-1000 | 20000 | 20000 | 3 | 23 | 204 | 192 | 13 | 19958.0 | SCAN:Merge Join>Clustered Index Scan>Sort | OBJECT:IX: 9, OBJECT:Sch-M: 2, KEY:X: 21, OBJECT:X: 1 | (-4, -1) |
| 20,000 | values-fs-1000 | 20000 | 20000 | 3 | 20 | 285 | 183 | 38 | 959.008 | SEEK:Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 40000 | (-124, 0) |
| 1,000,000 | in-nvarchar-512 | 2067 | 2067 | 0 | 5 | 543 | 120 | 17 | 1.875 | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 4134 | (-4, 0) |
| 1,000,000 | in-cast-fs-2067 | 2067 | 2067 | 3 | 1 | 1393 | 34 | 1318 | 2067.0 | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 4134 | (-6, 0) |
| 1,000,000 | openjson-2000 | 2067 | 2067 | 3 | 2 | 35 | 20 | 5 | 7.07107 | SEEK:Sort>Table-valued function>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 4134 | (-4, 0) |
| 1,000,000 | openjson-20000 | 2067 | 2067 | 3 | 1 | 24 | 18 | 5 | 7.07107 | SEEK:Sort>Table-valued function>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 4134 | (-4, 0) |
| 1,000,000 | temp-1000 | 2067 | 2067 | 3 | 6 | 86 | 31 | 6 | 2067.0 | SCAN:Clustered Index Scan>Index Seek>Clustered Index Seek | OBJECT:IX: 10, OBJECT:Sch-M: 2, KEY:U: 4134, KEY:X: 21 | (-8, 0) |
| 1,000,000 | values-fs-1000 | 2067 | 2067 | 3 | 3 | 70 | 18 | 5 | 67.0 | SEEK:Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 4134 | (-6, 0) |
| 1,000,000 | in-nvarchar-512 | 20000 | 20000 | 0 | 40 | 1664 | 1175 | 26 | 1.875 | SEEK:Filter>Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 40000 | (-62, 0) |
| 1,000,000 | in-cast-fs-2067 | 20000 | 20000 | 3 | 10 | 2233 | 208 | 662 | 1397.0 | SEEK:Merge Interval>Sort>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 40000 | (-92, 0) |
| 1,000,000 | openjson-2000 | 20000 | 20000 | 3 | 10 | 194 | 173 | 7 | 7.07107 | SEEK:Sort>Table-valued function>Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 40000 | (-62, 0) |
| 1,000,000 | openjson-20000 | 20000 | 20000 | 3 | 1 | 174 | 168 | 7 | 7.07107 | SEEK:Sort>Table-valued function>Index Seek>Clustered Index Seek | OBJECT:X: 1 | (-12, -1) |
| 1,000,000 | temp-1000 | 20000 | 20000 | 3 | 23 | 275 | 187 | 15 | 20000.0 | SCAN:Hash Match>Clustered Index Scan | OBJECT:IX: 10, OBJECT:Sch-M: 2, KEY:X: 21 | (-5, 0) |
| 1,000,000 | values-fs-1000 | 20000 | 20000 | 3 | 20 | 283 | 180 | 37 | 1000.0 | SEEK:Index Seek>Clustered Index Seek | OBJECT:IX: 1, KEY:U: 40000 | (-95, 0) |

Failures worth their exact text: `temp-2000` — "The number of row value
expressions in the INSERT statement exceeds the maximum allowed number
of 1000 row values" (error 10738; the join over a 2,067-row `VALUES`
derived table was accepted); `tvp` from ad hoc SQL — see `tvp_probe.py`.

## `tvp_probe.py` — can a table-valued parameter be bound from aioodbc/pyodbc?

`CREATE TYPE <tn>_paths AS TABLE (path varchar(1024) COLLATE
Latin1_General_100_BIN2_UTF8 NOT NULL PRIMARY KEY)` plus a stored
procedure with a `READONLY` parameter, 2,067 paths (three canaries),
20,000 rows. A first run passed the type as a nested `("dbo", type)`
tuple and failed every ad hoc form ("A TVP's rows must all be the same
size"); pyodbc's documented convention is two leading *strings*,
`[type, schema, *rows]`, and with it the ad hoc join works:

| form | found | canaries | ms | plan | locks |
|---|---|---|---|---|---|
| ad hoc JOIN ?, rows only                 | ERROR: (pyodbc.ProgrammingError) ('42000', '[42000] [Microsoft][ODBC Driver 18 for SQL Server]
| ad hoc JOIN ?, [type, schema] + rows     | 2067 | 3 | 28 ms | SCAN:Clustered Index Scan>Index Seek>Clustered Index Seek est=1.0 compile=3 | {'OBJECT:IX': 1, 'KEY:U': 4134} |
| sp_executesql READONLY param, [type, schema] + rows | 2067 | 3 | 31 ms | SCAN:Hash Match>Clustered Index Scan est=2067.0 compile=2 | {'OBJECT:X': 1} |
| sp_executesql, rows only                 | ERROR: (pyodbc.ProgrammingError) ('42000', '[42000] [Microsoft][ODBC Driver 18 for SQL Server]
| stored procedure {CALL}                  | 2067 | 3 | 29 ms | SCAN:Hash Match>Clustered Index Scan est=2067.0 compile=3 | {'OBJECT:X': 1} |
| stored procedure EXEC                    | 2067 | 3 | 27 ms | SCAN:Hash Match>Clustered Index Scan est=2067.0 compile=3 | {'OBJECT:X': 1} |

The ad hoc `JOIN ? AS k` plan is a scan of the table variable driving
nested-loops seeks into the entry table (est 1 row for the TVP):
4,134 `KEY:U`, no table lock, 28 ms. The `sp_executesql`
`READONLY`-parameter spelling and the stored procedure see the TVP's
true cardinality (2,067) and choose `Hash Match → Clustered Index
Scan` under `OBJECT:X`. Rows-only forms fail: pyodbc cannot infer the
type for ad hoc SQL.
