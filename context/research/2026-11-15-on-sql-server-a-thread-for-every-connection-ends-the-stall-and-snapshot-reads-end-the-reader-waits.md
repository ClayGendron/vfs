# On SQL Server a driver thread for every pooled connection ends the stall, and `READ_COMMITTED_SNAPSHOT` on ends the reader waits; the whole leg passes with the setting on and off

Clay wrote on 2026-11-15, while the label fix was being researched: "reminder, we need to keep vfs working in a multi user setup, and if we are locking tables we should make sure to not block all queires during that time". [The label memo](2026-11-14-a-mint-must-prove-its-label-against-a-posture-change-committed-inside-its-window.md) then found two things on SQL Server that are larger than the label fix for a mount many users share: every call waits behind an open write when `READ_COMMITTED_SNAPSHOT` is off (its section 10), and a process stalls for good when its blocked calls fill the loop's threads (its section 11). This memo asks what ends each. One researcher ran it the same day, in about an hour and a half of engine time on the SQL Server leg. The patch, the scripts and every result file are in [the studies folder](studies/2026-11-15-on-sql-server-a-thread-for-every-connection-ends-the-stall-and-snapshot-reads-end-the-reader-waits/README.md). No intention: the work is two properties on one engine. [The SQL Server spec](../specifications/active/2026-11-15-on-sql-server-a-read-never-waits-on-a-write.md) uses the answer.

Labels: EXECUTED means a command ran here on 2026-11-15 and the claim reports its output; READ means read in the file cited, at `08c372af` for vfs; INFERRED means reasoning from the two.

## Sources

vfs at `08c372af`: `src/vfs/storage/backends/database/engine.py` and `dialects.py`. The installed drivers, read in the project's environment: aioodbc 0.5.0 (`aioodbc/connection.py`), SQLAlchemy 2.0.52 (`sqlalchemy/connectors/aioodbc.py`), pyodbc 5.3.0, Microsoft ODBC Driver 18 for SQL Server 18.6.2.1 for arm64, unixODBC 2.3.14, and CPython 3.13's `concurrent/futures/thread.py`. The engine, from `docker/compose.test.yml`: SQL Server 2025 RTM-CU8, an x64 image run under emulation. The machine: ten cores, macOS, the engine in Docker Desktop. No reference clone was studied and no web page read.

## The answer

Two settings end the two findings, and neither breaks the suite. Giving the driver an executor of its own, with one thread for every connection the pool can hold, ended the stall: 19 runs of 19 that completed finished, on the unfixed tree and on the label mechanism, with the setting off and on, and with the loop's own executor as small as 4 threads; without it, 4 runs of 4 at 14 threads with the setting off had hung (EXECUTED, section 2). Turning `READ_COMMITTED_SNAPSHOT` on ends the reader waits (EXECUTED, the label memo's section 10), and the whole SQL Server leg passes in a database with the setting on, 438 tests, as it does with it off (EXECUTED, section 3). A first touch can read the setting in one statement (EXECUTED, section 4). One more finding stands beside these and is not explained: the process died inside Microsoft's ODBC driver three times in the day's first runs, each a memory fault, on the unfixed tree as on the others (EXECUTED, section 5). Seventy-five further runs show that an executor per engine does not make that likelier, and no run fell with the driver manager's own connection pooling turned off, which is too few runs to call the cause (EXECUTED, section 6).

## 1. What was run

EXECUTED. The label experiment's two copies of the tree, `base` (unfixed) and `candC` (the label mechanism), were copied to `baseX` and `candCX`, and one change was made in each: where vfs builds a SQL Server engine it now passes `connect_args={"executor": ThreadPoolExecutor(15)}`. SQLAlchemy hands connect arguments to `aioodbc.connect` (READ, `sqlalchemy/connectors/aioodbc.py:148-161`), which takes `executor` and runs every driver call of that connection on it (READ, `aioodbc/connection.py:41-68`, `:255-300`). Fifteen is the most connections SQLAlchemy's default pool holds, five and ten of overflow, and vfs sets no pool size (READ, `engine.py:219`, `:983-1000`). The contention run is the label memo's: sixteen writers of fifty files each, three posture changes with their relabels and a sweep, 804 calls, eighteen handles in one process. The loop's default executor was set to 14 threads, this machine's default, or to 4.

## 2. A thread for every connection ends the stall

EXECUTED, `experiments/hang.sh`.

| Database | The loop's own threads | `baseX`, unfixed with the patch | `candCX`, the mechanism with the patch | Without the patch (the label memo's section 11) |
|---|---|---|---|---|
| `master`, the setting off | 14 | finished 5 of 5 | finished 5 of 6; one died in the driver | hung 4 of 4 |
| the same | 4 | not run | finished 2 of 2 | not run |
| `vfs_rcsi`, the setting on | 14 | finished 2 of 3; one died in the driver | finished 5 of 5 | `base` finished 11 of 11; `candC` hung 4 of 11 |

No run stalled: no run was stopped with a request blocked on the server. Every finished run in `master` held 804 successes; the finished runs in `vfs_rcsi` held successes and at most three retryable conflicts; none left a stale label. The two runs that did not finish died as section 5 describes.

Why it works (INFERRED from the two READ facts above): a connection has at most one driver call in flight, so an executor with as many threads as the pool has connections always has a thread free for the next call of any connection. The session that holds a contended row can then always send its commit. The size of the loop's default executor stops mattering to the driver, which is why 4 threads finished.

What it costs (INFERRED): up to fifteen threads an engine, made as they are first needed and idle otherwise, where today the driver borrows the loop's threads and competes for them with every other use of `run_in_executor` in the host.

## 3. The whole SQL Server leg passes with the setting on

EXECUTED on the repository's own tree, unfixed, with `uv run pytest -m mssql` and the default executor. In `vfs_rcsi`, made with `CREATE DATABASE vfs_rcsi` and `ALTER DATABASE vfs_rcsi SET READ_COMMITTED_SNAPSHOT ON`: 438 passed. In `master`, where the leg runs today: 438 passed. So no test depends on a reader waiting for a writer, and nothing the leg pins changes with the setting.

The setting changes what a plain read does, not what a write does. With it off a plain read takes a shared lock and waits for an uncommitted write of the row; with it on the read returns the last committed version. EXECUTED in the label memo's section 10: with it off, all eleven calls made while a posture write stood open waited, reads, a glob, a grep and rewrites included; with it on, only the calls that wait on the other three engines did.

## 4. What a first touch can read

EXECUTED with `sqlcmd` in each database: `SELECT is_read_committed_snapshot_on FROM sys.databases WHERE database_id = DB_ID()` returns 0 in `master` and 1 in `vfs_rcsi`. `ALTER DATABASE master SET READ_COMMITTED_SNAPSHOT ON` is refused by the server, error 5058, so the test leg cannot stay in `master` once the setting is required. The statement that turns it on in another database needs the database to itself for a moment and the right to alter it (INFERRED from the engine's documented behaviour, not run against a busy database).

## 5. The process died in the ODBC driver three times

EXECUTED, the system's crash reports, whose top frames are kept beside the runs. Three runs ended with the test's worker process killed: `m3-base-18x16-r3` (the unfixed tree, 18 shared threads, the label memo's section 11), `x1-candCX-14x16-r5` and `x1-rcsi-baseX-14x16-r2`. Two reports say `BUG IN CLIENT OF LIBMALLOC: memory corruption of free block` and one is a segmentation fault; in all three the crashed thread is inside `libmsodbcsql.18.dylib`, beneath pyodbc's `execute`. In the two that recorded answers first, a call had just returned SQLSTATE `08S01` from the driver's TLS layer: "decryption failed or bad record mac" in one, "wrong version number" in the other. The server showed no blocked session in any of the three. One earlier run returned a single retryable `backend unavailable` answer whose detail was not recorded.

Where they fell: one in 6 runs at 18 shared threads; two in 21 runs with an executor per engine; none in 24 runs at 14 shared threads; none in 5 runs at 64 shared threads; none in the two whole-leg runs. These counts do not say whether more threads make it likelier (INFERRED). The settings in force: `pyodbc.pooling` is `True`, its default, and `/opt/homebrew/etc/odbcinst.ini` sets no pooling and no threading level for the driver.

## 6. Seventy-five more runs: an executor per engine does not make the deaths likelier, and none fell with the driver manager's pooling off

EXECUTED, the contention run 25 times in each of three settings, in `master`, with each answer that was neither a success nor a retryable conflict recorded with its detail. Another project's test run loaded the machine through the last third of these runs.

| Setting | Finished | Died or hung on a driver fault |
|---|---|---|
| the patch, an executor of 15 threads an engine; `pyodbc.pooling` on, its default | 23 of 25 | 2: the process died, both with the same heap-corruption report inside the driver |
| the patch, with `pyodbc.pooling = False` set before the first connection | 25 of 25 | none |
| no patch, 64 shared threads; `pyodbc.pooling` on | 24 of 25 | 1: four calls returned `08S01` from the driver's TLS layer and the run then hung with no session blocked on the server |

So an executor per engine fell as often as 64 shared threads did, two against one in 25, and the fault is in the unpatched tree too. With pooling off no run fell. Twenty-five clean runs do not establish that pooling is the cause: at the rate seen with it on, about one run in twenty, 25 clean runs come by chance about one time in three (INFERRED). READ, SQLAlchemy's own documentation for this driver, `sqlalchemy/dialects/mssql/pyodbc.py:254-270`: pyodbc pools connections itself by default, "it is often preferable to disable this behavior", and it "can only be disabled globally at the PyODBC module level, **before** any connections are made".

## What this memo does not settle

- What makes the driver die. Section 6 points at the driver manager's pooling and does not establish it. The experiment: the contention run 100 times with `pyodbc.pooling` on and 100 with it off, on a quiet machine, counting deaths and `08S01` answers; then the same on a Linux host with the x64 driver, where the CI leg runs.
- Whether the stall can still be reached with an executor per engine when a host sets a larger pool than the executor has threads. The experiment: the contention run with `pool_size=20` on one handle and twenty writers on it.
- What vfs can see of an engine a host built itself, where vfs cannot pass the executor. The experiment: a read of the pool's size and of the driver connection's executor from a host-built engine at first touch.
- Whether the setting can be turned on in a database that is in use. The experiment: `ALTER DATABASE … SET READ_COMMITTED_SNAPSHOT ON`, with and without `WITH ROLLBACK IMMEDIATE`, against a database with open sessions.
- Whether snapshot reads change any plan pin or any race node's meaning on SQL Server beyond passing. The experiment: the race nodes of `tests/storage/database/test_races.py` on the SQL Server leg with each seam's rival staged in both databases, and their recorded states compared.

## One line

Give the SQL Server driver a thread for every pooled connection and require snapshot reads: the stall and the reader waits both end and the leg still passes, and the driver's own crashes under many threads are a separate thing still to explain.
