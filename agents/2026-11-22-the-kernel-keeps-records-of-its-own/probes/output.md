# What the probes printed

Run on 2026-11-23 against `a-job-is-interrupted-and-resumed` at `1c10dca1`, with nothing under `src/` changed. One machine: an Apple M1 Pro of 10 cores and 32 GB, macOS 26.5.2, with the server, the client and the scripts on it together. Python 3.13.11, SQLite 3.50.4 through aiosqlite 0.22.1, SQLAlchemy 2.0.52, asyncpg 0.31.0, and PostgreSQL 19.0 with pgvector in the `docker/compose.test.yml` container (Docker 29.7.2), brought up and torn down as `.claude/skills/db_test/SKILL.md` says. Every timing is a size and never a pass or a fail. Each timing probe ran alone, one after another.

Nothing of the spec is built. Every probe measures `standin.py`, the smallest stand-in for the store, beside today's `src/vfs`: a second SQLAlchemy engine, `BEGIN IMMEDIATE` and `busy_timeout` 5,000 ms on SQLite, four tries, a buffer of 16,384 rows that drops its oldest, and one flusher that takes up to 1,024 rows and flushes as soon as it is free. `report.py` rendered the tables below from the JSON each probe printed. A figure over several repeats is the median of the repeats' figures, and a count is the sum over the repeats. The probes are scripts outside the gate and are not held to `ruff`.

In every table `none` is no store, `same` is the store on a second engine in the mount's own database (the spec's decisions 4 and 5), and `own-file` is the store in a second SQLite file, the shape the log cost study recommended and the ruling of 2026-11-23 gave up.

## 1. SQLite, one file: `probe_waits.py --engine sqlite --calls 13`

Eight readers that put one unkeyed fifteen-column row behind for each read, one one-file writer that records after each write, three repeats of each window; then 32 writing sessions, five repeats. 462 s in all.

#### Window `quiet`

| measure | none | same | own-file |
|---|---|---|---|
| window s | 3.0 | 3.0 | 3.0 |
| reads | 3,359 | 3,191 | 2,969 |
| reads a second | 377 | 360 | 340 |
| read median ms | 21.4 | 21.9 | 23.5 |
| read p95 ms | 24.4 | 27.5 | 27.5 |
| read max ms | 31 | 48 | 54 |
| reads failed | 0 | 0 | 0 |
| one-file writes | 185 | 146 | 137 |
| write median ms, verb | 49.1 | 52.0 | 54.3 |
| write median ms, verb and record | 49.1 | 60.7 | 64.7 |
| writes refused | 0 | 0 | 0 |
| record writes failed | — | 0 | 0 |
| flushes failed / all | — | 0 / 155 | 0 / 1035 |
| flushes that needed a second try | — | 0 | 0 |
| slowest flush s | — | 0.56 | 0.04 |
| store commit waited to begin, median ms | — | 4.5 | 4.7 |
| the longest such wait ms | — | 563 | 31 |
| buffer high water | — | 213 | 7 |
| rows dropped | — | 0 | 0 |

#### Window `batch`: while a 10,000-entry write runs

| measure | none | same | own-file |
|---|---|---|---|
| window s | 8.2 | 7.9 | 13.1 |
| reads | 4,891 | 4,789 | 9,189 |
| reads a second | 200 | 199 | 241 |
| read median ms | 22.8 | 22.6 | 23.8 |
| read p95 ms | 206 | 212 | 35.7 |
| read max ms | 925 | 895 | 979 |
| reads failed | 0 | 0 | 0 |
| one-file writes | 30 | 23 | 20 |
| write median ms, verb | 66.5 | 68.1 | 74.9 |
| write median ms, verb and record | 66.5 | 78.9 | 88.1 |
| writes refused | 0 | 0 | 0 |
| record writes failed | — | 0 | 0 |
| flushes failed / all | — | 0 / 38 | 0 / 3377 |
| flushes that needed a second try | — | 3 | 0 |
| slowest flush s | — | 7.75 | 0.61 |
| store commit waited to begin, median ms | — | 6.2 | 4.6 |
| the longest such wait ms | — | 2,387 | 608 |
| buffer high water | — | 1503 | 12 |
| rows dropped | — | 0 | 0 |

#### Window `held`: while a connection of no engine holds the file's writer for 30 s

This stands for a batch as long as the study's, which held the writer 28 s on its machine. A 10,000-entry write holds it about 8 s here.

| measure | none | same | own-file |
|---|---|---|---|
| window s | 30.0 | 30.0 | 30.1 |
| reads | 39,071 | 39,040 | 35,576 |
| reads a second | 435 | 437 | 396 |
| read median ms | 18.1 | 18.2 | 20.0 |
| read p95 ms | 20.9 | 20.8 | 23.4 |
| read max ms | 124 | 115 | 104 |
| reads failed | 0 | 0 | 0 |
| one-file writes | 7 | 7 | 9 |
| write median ms, verb | 15,035 | 10,378 | 9,044 |
| write median ms, verb and record | 15,035 | 15,028 | 9,046 |
| writes refused | 3 | 2 | 3 |
| record writes failed | — | 1 | 0 |
| flushes failed / all | — | 3 / 4 | 0 / 12674 |
| flushes that needed a second try | — | 4 | 0 |
| slowest flush s | — | 20.93 | 0.08 |
| store commit waited to begin, median ms | — | 0.0 | 3.9 |
| the longest such wait ms | — | 4,171 | 72 |
| buffer high water | — | 12210 | 10 |
| rows dropped | — | 0 | 0 |

#### 32 writing sessions, no reader and no batch

Each session writes 13 files one after another, the first 3 not counted, each write followed by its record.

| measure | none | same | own-file |
|---|---|---|---|
| repeats | 5 | 5 | 5 |
| writes counted | 1600 | 1600 | 1600 |
| verb median ms | 135 | 41.3 | 163 |
| verb p95 ms | 604 | 516 | 638 |
| verb and record median ms | 135 | 54.5 | 166 |
| verb and record p95 ms | 604 | 841 | 640 |
| slowest ms | 2,942 | 2,942 | 2,157 |
| writes refused | 0 | 0 | 0 |
| record writes failed | — | 0 | 0 |
| records that needed a second try | — | 0 | 0 |
| record waited to begin, median ms | — | 0.6 | 0.6 |
| the longest such wait ms | — | 3,410 | 2 |

- `none` at close: one file, `vfs.db`. `same` at close: one file, `vfs.db`, and no row left in the buffer. `own-file` at close: `kernel.db` and `vfs.db`.
- The lower median of `same` under 32 writers is not attributed. The study saw the same direction (321 ms with no log, 162 ms with the log in the file). The 95th percentile moved the other way.
- This run was made before the script was given the batch's own record of 20,000 rows, so its batch window ends when the batch does. Sections 4 and 12 were run with that record, and a run of this section today adds about a second to the batch window of `same` and `own-file`.
- An earlier run of the same script counted a flush in the window it ended in and not the one it was asked for in, so a backlog showed in the next quiet window. It was discarded, and the script now waits for the buffer to empty between windows.

## 2. SQLite, a writer held for 60 s: `probe_waits.py --engine sqlite --places same --repeats 1 --batch 0 --hold 60 --many-repeats 0`

| measure | same |
|---|---|
| window s | 60.0 |
| reads | 26,348 |
| reads a second | 439 |
| read median ms | 18.0 |
| reads failed | 0 |
| one-file writes | 3 |
| writes refused | 2 |
| record writes failed | 0 |
| flushes failed / all | 2 / 3 |
| slowest flush s | 20.94 |
| buffer high water | 16384 |
| rows dropped | 9047 |

At 439 reads a second the buffer fills in about 37 s of a held writer, and the oldest rows go from then on.

## 3. SQLite, a sweep pass of 600,000 rows: `probe_waits.py --engine sqlite --places same,own-file --repeats 1 --batch 0 --hold 0 --sweep-rows 600000 --many-repeats 0`

The pass is decision 17's: one bounded delete of 5,000 rows to a commit, back to back, until a call removes none.

| measure | same, quiet | own-file, quiet | same, during the pass | own-file, during the pass |
|---|---|---|---|---|
| window s | 3.0 | 3.0 | 9.2 | 9.8 |
| reads a second | 367 | 345 | 360 | 326 |
| read median ms | 21.7 | 23.3 | 21.7 | 24.0 |
| one-file writes | 50 | 48 | 17 | 102 |
| write median ms, verb | 51.4 | 54.1 | 130 | 59.3 |
| write median ms, verb and record | 59.6 | 63.6 | 408 | 79.6 |
| writes refused | 0 | 0 | 0 | 0 |
| flushes failed / all | 0 / 67 | 0 / 376 | 0 / 34 | 0 / 115 |
| the longest wait of a store commit to begin, ms | 365 | 10 | 1,709 | 1,501 |
| buffer high water | 148 | 7 | 630 | 498 |

- `same`: the pass removed 600,000 rows in 121 commits, 0 failed; a commit's median 69.6 ms and longest 302.0 ms; its longest wait to begin 238.2 ms.
- `own-file`: the pass removed 600,000 rows in 121 commits, 0 failed; a commit's median 76.6 ms and longest 177.4 ms; its longest wait to begin 69.2 ms.
- In one file the one-file writer got 17 writes through in the pass's 9.2 s, where it got 102 in 9.8 s beside a pass on another file.

## 4. SQLite, keyed rows and a batch's own record: `probe_waits.py --engine sqlite --rows stamp --places same,own-file --repeats 1 --many-repeats 0`

Each read puts one row keyed by its session and path, over 2,000 paths. After the 10,000-entry write the session records 10,000 stamps and 10,000 fifteen-column change rows in one transaction.

| measure | same, quiet | own-file, quiet | same, batch | own-file, batch | same, held 30 s | own-file, held 30 s |
|---|---|---|---|---|---|---|
| reads a second | 367 | 335 | 183 | 197 | 441 | 398 |
| read median ms | 21.9 | 23.5 | 22.7 | 24.4 | 18.0 | 19.9 |
| write median ms, verb and record | 60.9 | 64.5 | 74.8 | 85.2 | 15,171 | 15,020 |
| writes refused | 0 | 0 | 0 | 0 | 0 | 1 |
| record writes failed | 0 | 0 | 0 | 0 | 1 | 0 |
| flushes failed / all | 0 / 76 | 0 / 380 | 0 / 14 | 0 / 882 | 1 / 2 | 0 / 4430 |
| slowest flush s | 0.47 | 0.01 | 8.88 | 0.65 | 20.95 | 0.04 |
| buffer high water | 177 | 7 | 1595 | 24 | 12241 | 7 |
| rows dropped | 0 | 0 | 0 | 0 | 0 | 0 |

- `same`: the batch took 8.33 s; its record of 20,000 rows waited 0.048 s to begin and held the writer 1.17 s; it did not fail.
- `own-file`: the batch took 10.51 s; its record of 20,000 rows waited 0.011 s to begin and held the writer 1.187 s; it did not fail.

## 5. The study's own waits run on this machine: `measure_waits.py --engine sqlite`

The script of `agents/2026-11-21-what-a-log-row-per-call-costs/scripts/`, run from a copy in the scratch directory so that it wrote no file in the repository. Its log gives up after one wait of five seconds and flushes at 256 rows. Three repeats; counts are sums.

| mode | batch s | read median quiet → during | read p95 quiet → during | one-file writes refused | log writes failed | flushes failed / all | slowest flush s | buffer high water |
|---|---|---|---|---|---|---|---|---|
| none | 8.5 | 21.5 → 22.7 | 24.7 → 211.4 | 0 | 0 | 0 / 0 | 0.0 | 0 |
| sync | 4.1 | 15.1 → 28.9 | 362.7 → 4408.0 | 0 | 0 | 0 / 0 | 0.0 | 0 |
| leaned, log in the mount's file | 8.5 | 21.7 → 22.8 | 28.2 → 211.5 | 1 | 2 | 1 / 14 | 5.33 | 1665 |
| leaned, log in its own file | 8.7 | 21.8 → 23.7 | 26.2 → 212.3 | 0 | 0 | 0 / 20 | 0.22 | 256 |

The two log writes that failed were `database is locked`. On the study's machine the same script gave 12 of 19 flushes failed, 10 log writes failed and a buffer of 2,360 in the mount's file, and 0 of 24, 0 and 257 in a file of its own; its batch took 28 s there and 8.5 s here.

## 6. SQLite, two engines at close: `probe_sqlite_close.py`

| case | step | files in the directory |
|---|---|---|
| store-first | both open, both written | `knowledge.db`, `-shm`, `-wal` |
| | store closed | `knowledge.db`, `-shm`, `-wal` |
| | kernel closed | `knowledge.db` |
| mount-first | kernel closed | `knowledge.db`, `-shm`, `-wal` |
| | store closed | `knowledge.db` |
| together | both closed in one gather | `knowledge.db` |
| store-never | kernel closed, store left open | `knowledge.db`, `-shm`, `-wal` |
| | store closed afterwards | `knowledge.db` |
| store-connection-out | both disposed, one store connection still out | `knowledge.db`, `-shm`, `-wal` |
| | that connection returned | `knowledge.db`, `-shm`, `-wal` |
| other-process | both closed, another process still open | `knowledge.db`, `-shm`, `-wal` |
| | the other process closed | `knowledge.db` |

In every case the file kept 1 stamp row and 1 file row, read afterwards by a plain connection.

## 7. SQLite, first touch: `probe_sqlite_first_touch.py`

| case | mount's first touch | store's first touch | page size | journal | mount tables | store tables | other tables | mount write and read, store commit | files after close |
|---|---|---|---|---|---|---|---|---|---|
| store-then-mount | ok | ok | 16384 | wal | 24 | 3 | 0 | all served | `knowledge.db` |
| mount-then-store | ok | ok | 16384 | wal | 24 | 3 | 0 | all served | `knowledge.db` |
| at-once, 8 runs | ok in all | ok in all | 16384 | wal | 24 | 3 | 0 | all served | `knowledge.db` |
| foreign-table | ok | ok | 4096 | wal | 25, one of them `vfs_session_notes`, which neither made | 3 | `app_orders` | all served | `knowledge.db` |
| statistics | ok | ok | 16384 | wal | 24 | 3 | 0 | all served | `knowledge.db` |

- `store-then-mount`: after the store's first touch alone the file held the store's 3 tables at page size 16,384 in WAL, and the mount then made its 24 beside them with format 28.
- `foreign-table`: the file was made by a plain connection, with a table `vfs_session_notes` and a table `app_orders`, at page size 4,096. Both first touches succeeded and neither table was touched.
- `statistics`: after a 3,000-entry write on the mount and 3,000 rows in the store's stamp table, `sqlite_stat1` named `vfs_content`, `vfs_edges`, `vfs_entries`, `vfs_grants`, `vfs_principal_revisions` and `vfs_segments`, and no table of the store.
- `read-only`: with the file made read-only after both had written to it, the mount served a `read`. The store's first touch raised `OperationalError: attempt to write a readonly database` (SQLite code 8) after 1 try. Today's classifier says it is not retryable and not a permanent defect, so `classify_failure` answers `vfs.unavailable`, retryable. After the close the directory held `knowledge.db`, `knowledge.db-shm` and `knowledge.db-wal`.

## 8. Today's kernel and a close that is cut short: `probe_close_timeout.py`

| case | first `close()` | storage's `close` entered by the first | second `close()` | storage's `close` entered in all | storage's `close` finished |
|---|---|---|---|---|---|
| the storage's close outlives `close_timeout` | `TimeoutError` | 1 | returned | 1 | 0 |
| the kernel's close is cancelled | `CancelledError` | 1 | returned | 2 | 1 |

The default `close_timeout` is 10 s. A flush behind a held SQLite writer waits four tries of 5 s, 20 s and up to 0.35 s between tries: 20.9 s as measured above.

## 9. The statements, SQLite: `probe_statements.py --engine sqlite`

| check | what it showed |
|---|---|
| counter, two engines, 50 each | 100 numbers, exactly 1 to 100, no repeat, no error, interleaved; 2 binds |
| a block of five after 100 | returns 105 |
| a number taken and rolled back | 106 taken, 106 taken again |
| no row matches | returns no row |
| bounded delete, 12,000 expired, 100 live, 3 with no expiry | 5,000, 5,000, 2,000, 0; 103 rows left; 3 binds |
| two passes at once, 40,000 expired | the first pass removed 5,000 eight times and then 0; the second pass's first call removed 0; 40,000 removed in all, 100 left |
| three-column key, limit 5 of 8 | removed 5; 3 binds |
| upsert that keeps the newest | 4 new: 4; 4 older: 0; 4 of the same turn: 4; 4 newer: 4; the stored value is the newest |
| insert that does nothing | 8 new: 8; 4 of which 3 exist: 1 |
| one statement names a key twice | accepted: 2 rows counted, and the later value stored |
| first touch, 8 connections, under `BEGIN IMMEDIATE` | 8 ok, 1 meta row |
| first touch, 8 connections, under a plain `BEGIN` | 1 ok, 7 refused `database is locked`, 1 meta row |
| today's `bulk_insert` from a session of no storage | 10,000 sent, 10,000 stored, mode `driver` |

The second pass got no turn at the file's writer until the first had removed everything: a waiter polls with sleeps of up to 100 ms, and the pass that holds the writer takes it again as soon as it commits.

## 10. The statements, Postgres 19: `probe_statements.py --engine postgres`

The server's default isolation was `read committed`.

| check | what it showed |
|---|---|
| counter, two engines, 50 each | 100 numbers, exactly 1 to 100, no repeat, no error, interleaved; 2 binds |
| a block of five after 100 | returns 105 |
| a number taken and rolled back | 106 taken, 106 taken again |
| counter under a server default of REPEATABLE READ | 50 statements refused `40001`, "could not serialize access due to concurrent update", which today's classifier retries; with 20 tries each and no wait between them, 98 of 100 numbers were handed out |
| bounded delete, 12,000 expired, 100 live, 3 with no expiry | 5,000, 5,000, 2,000, 0; 103 rows left; 2 binds |
| two passes at once, 40,000 expired | one pass: 5,000, 5,000, 0; the other: 5,000 six times and then 0; 40,000 removed in all, 100 left; one pass ended while 20,000 expired rows were still there |
| three-column key, limit 5 of 8 | removed 5; 2 binds |
| upsert that keeps the newest | 4 new: 4; 4 older: 0; 4 of the same turn: 4; 4 newer: 4 |
| insert that does nothing | 8 new: 8; 4 of which 3 exist: 1 |
| one statement names a key twice | refused `21000`, "ON CONFLICT DO UPDATE command cannot affect row a second time"; not retryable |
| first touch, 8 connections, under `pg_advisory_xact_lock` | 8 ok, 1 meta row |
| first touch, 8 connections, without it | 1 ok, 7 refused: a unique violation in the catalog, or "relation already exists" |
| the mount's advisory key and the store's | differ |
| two flushes that write two keys in opposite orders | one committed; the other `40P01`, deadlock detected, which today's classifier retries |
| two flushes that write them in one order | both committed |
| a transaction that touches two rows against a sweep chunk that meets them the other way round | one committed; the other `40P01`, deadlock detected |
| today's `bulk_insert` from a session of no storage | 10,000 sent, 10,000 stored, mode `copy` |

## 11. Postgres, a store that will not be written: `probe_postgres_refusals.py`

| case | what first touch raised | tries | today's `classify_failure` | a flush, by decision 15 |
|---|---|---|---|---|
| a role with no CREATE on the schema, before the tables exist | `42501`, permission denied for schema | 1 | `vfs.internal`, not retryable | a statement defect: the batch is dropped |
| the same role once the tables exist, with no rights on them | `42501`, permission denied for table | 1 | `vfs.internal`, not retryable | the batch is dropped |
| a session whose transactions are read-only | `25006`, cannot execute INSERT in a read-only transaction | 1 | `vfs.unavailable`, retryable | the rows are kept |

## 12. Postgres, the store beside readers, a writer, a batch and a sweep: `probe_waits.py --engine postgres --calls 13 --sweep-rows 300000`

| measure | none, quiet | same, quiet | none, batch | same, batch | same, during a sweep pass |
|---|---|---|---|---|---|
| window s | 3.0 | 3.0 | 5.5 | 7.4 | 2.0 |
| reads a second | 785 | 669 | 174 | 151 | 692 |
| read median ms | 9.5 | 11.6 | 12.3 | 14.6 | 11.2 |
| read p95 ms | 12.7 | 13.7 | 272 | 282 | 13.2 |
| reads failed | 0 | 0 | 0 | 0 | 0 |
| write median ms, verb | 43.8 | 53.0 | 148 | 273 | 51.2 |
| write median ms, verb and record | 43.8 | 61.1 | 148 | 298 | 59.3 |
| writes refused | 0 | 0 | 0 | 0 | 0 |
| record writes failed | — | 0 | — | 0 | 0 |
| flushes failed / all | — | 0 / 1302 | — | 0 / 711 | 0 / 870 |
| slowest flush s | — | 0.02 | — | 0.59 | 0.04 |
| buffer high water | — | 14 | — | 21 | 11 |
| rows dropped | — | 0 | — | 0 | 0 |

- The batch took 5.6 s; its record of 20,000 rows held its transaction 1.72 to 1.81 s in the three repeats and waited for nothing. The batch window of `same` includes that record.
- A pass removed 300,000 rows in 61 commits, a commit's median 26 to 39 ms, with no wait to begin.
- 32 writing sessions, 1,600 writes counted: verb and record median 150 ms with no store and 185 ms with it; 95th percentile 272 and 307 ms; 3 and 1 writes refused `vfs.conflict`; no record failed.

## 13. Postgres, the pool: `probe_postgres_pool.py --repeats 5`

32 sessions each write 23 files, the first 3 not counted, each write followed by one record in a second transaction. Five repeats, the order rotated.

| measure | none | mount-pool | own-15 | own-32 |
|---|---|---|---|---|
| repeats | 5 | 5 | 5 | 5 |
| writes counted | 3200 | 3200 | 3200 | 3200 |
| verb and record median ms | 192 | 214 | 217 | 217 |
| each repeat's median | 188 193 192 196 189 | 213 211 215 214 214 | 217 221 224 216 213 | 216 217 217 220 216 |
| verb and record p95 ms | 297 | 344 | 317 | 316 |
| verb alone median ms | 192 | 152 | 201 | 202 |
| record median ms | — | 61.1 | 15.7 | 15.6 |
| record p95 ms | — | 141 | 21.3 | 20.3 |
| writes refused | 0 | 7 | 1 | 1 |
| record writes failed | — | 0 | 0 | 0 |
| connections open at the peak | 16 | 15 | 21 | 23 |
| mount pool: most out | 15 | 15 | 15 | 15 |
| mount pool: most callers waiting | 17 | 17 | 17 | 17 |
| store pool: most out | — | — | 6 | 8 |
| store pool: most callers waiting | — | — | 0 | 0 |
| record writes that found their pool exhausted | — | 2459 | 0 | 0 |

The refused writes were `vfs.conflict`. No record and no flush failed.

## 14. Postgres, the pool beside 32 batches: `probe_postgres_pool.py --batches 32 --window 90 --repeats 1`

The same 32 writing sessions, eight readers that put a row behind, and 32 writes of 10,000 entries started at once. One window of 90 s for each way; batches still running then were cancelled.

| measure | none | mount-pool | own-15 | own-32 |
|---|---|---|---|---|
| writes counted | 26 | 9 | 25 | 30 |
| verb and record median ms | 18,962 | 19,015 | 15,483 | 18,135 |
| verb and record p95 ms | 33,417 | 49,152 | 42,212 | 33,366 |
| verb alone median ms | 18,962 | 16,280 | 15,469 | 17,088 |
| record median ms | — | 74.3 | 34.2 | 15.2 |
| record p95 ms | — | 21,968 | 2,340 | 2,967 |
| writes refused | 6 | 2 | 1 | 4 |
| record writes failed | — | 5 | 0 | 0 |
| connections open at the peak | 15 | 16 | 19 | 20 |
| mount pool: most out | 15 | 15 | 15 | 15 |
| mount pool: most callers waiting | 54 | 56 | 56 | 56 |
| store pool: most out | — | — | 3 | 4 |
| store pool: most callers waiting | — | — | 0 | 0 |
| record writes that found their pool exhausted | — | 36 | 0 | 0 |
| read median ms | 4,292 | 2,740 | 3,307 | 4,678 |
| read p95 ms | 31,377 | 31,189 | 30,859 | 31,146 |
| flushes failed / all | — | 1 / 12 | 0 / 42 | 0 / 47 |
| flush median ms | — | 942 | 40.5 | 43.5 |
| slowest flush ms | — | 30,016 | 2,206 | 4,100 |
| buffer high water | — | 16 | 6 | 5 |
| batches served / refused / cancelled at the window | 2 / 15 / 15 | 2 / 18 / 12 | 2 / 12 / 18 | 2 / 17 / 13 |

- The refused writes and the refused batches were `vfs.unavailable`: the mount's pool gave no connection in 30 s. That is today's behaviour with no store, and `agents/2026-11-21-concurrent-writes-on-postgres-outlive-their-retries/spec.md` has it.
- The five record writes and the one flush that failed on the mount's pool were `TimeoutError: QueuePool limit of size 5 overflow 10 reached, connection timed out, timeout 30.00`.
- A read's median of seconds is the read waiting for a connection of the mount's pool, in every way and with no store.

## Not run

- Postgres 15 to 18. One container, Postgres 19, was run.
- Decision 26's `expiry_sweeper` with a dependent table, on either engine.
- A statement of fixed binds at the sizes specs 3 and 4 allow: a rewind over 16 MiB of stamps, a fork of 100,000 turns.
- A loss of power, and a disk that honours `fsync`: `synchronous = FULL` does not force this machine's disk.
- A store transaction on a loop other than the one its engine first ran on.
