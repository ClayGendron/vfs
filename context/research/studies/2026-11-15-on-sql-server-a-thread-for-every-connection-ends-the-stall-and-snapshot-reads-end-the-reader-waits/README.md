# The SQL Server remedies: the patch, the scripts and the results

The evidence behind [on SQL Server a thread for every connection ends the stall and snapshot reads end the reader waits](../../2026-11-15-on-sql-server-a-thread-for-every-connection-ends-the-stall-and-snapshot-reads-end-the-reader-waits.md). One researcher ran it on 2026-11-15 against vfs at `08c372af`, on the SQL Server engine of `docker/compose.test.yml`. Everything here is EXECUTED output or the script that produced it. The patch is research code: the spec that stands on the memo writes its own. The copies, the test file and `run.sh` are the label experiment's, in [its studies folder](../2026-11-14-a-mint-must-prove-its-label-against-a-posture-change-committed-inside-its-window/README.md); this folder holds only what was added.

## The files

| File | What it is |
|---|---|
| `experiments/executor.patch` | The one change over the label experiment's `base` and `candC` copies, making `baseX` and `candCX`: when vfs builds a SQL Server engine it passes the driver an executor of its own with 15 threads, one for each connection SQLAlchemy's default pool can hold. |
| `experiments/hang.sh` | The label experiment's script in its last form: it runs the contention node at a given size of the loop's default executor, and stops a run that hung, wrote nothing in 220 seconds, or ended without a result line, after reading the server's waiting sessions. |
| `experiments/out/` | The result files, one JSON object a line, named `<run>-mssql.jsonl`; for a run that was stopped, the server's counts as `<run>-mssql.server.txt`; for a run whose process died, the top of the system's crash report as `<run>-mssql.crash.txt`; and the closing lines of the two whole-leg runs. |

## The runs

| Run | Copy | What ran |
|---|---|---|
| `x1-candCX-14x16-r0` to `-r5`, `x1-baseX-14x16-r1` to `-r5` | `candCX`, `baseX` | The contention run, 16 writers, the loop's default executor at 14 threads, in `master`, where `READ_COMMITTED_SNAPSHOT` is off. |
| `x1-candCX-4x16-r1`, `-r2` | `candCX` | The same with the loop's default executor at 4 threads. |
| `x1-rcsi-candCX-14x16-r1` to `-r5`, `x1-rcsi-baseX-14x16-r1` to `-r3` | `candCX`, `baseX` | The same at 14 threads in the database `vfs_rcsi`, where the setting is on. |
| `leg-rcsi-mssql`, `leg-master-mssql` | the repository's own tree | `uv run pytest -m mssql`, the whole SQL Server leg, in `vfs_rcsi` and in `master`. |
| `d1-baseX-pool-r1` to `-r25`, `d1-baseX-nopool-…`, `d1-base-64-…` | `baseX`, `base` | The contention run 25 times each: with the patch; with the patch and `pyodbc.pooling` off; and without the patch on 64 shared threads. |

## To run it again

Make the label experiment's `base` and `candC` copies as its README says, copy each to `baseX` and `candCX`, and apply `executor.patch` in each. Then `./hang.sh <copy> <run> <threads> <writers>`, with `LABEL_EXPERIMENT_MSSQL_DB=vfs_rcsi` for the database with the setting on and `LABEL_EXPERIMENT_NOPOOL=1` to turn the driver manager's pooling off.

## One line

One patch that gives the SQL Server driver its own threads, the runs that show the stall gone with it, the two whole-leg runs, and the runs that count how often the driver itself dies.
