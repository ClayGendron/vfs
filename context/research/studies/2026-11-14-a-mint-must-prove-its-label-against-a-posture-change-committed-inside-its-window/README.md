# The label-mint experiment: scripts, patches and results

The evidence behind [a mint proves its label with a shared lock on the everyone stamp](../../2026-11-14-a-mint-must-prove-its-label-against-a-posture-change-committed-inside-its-window.md). One researcher ran it on 2026-11-15 against vfs at `08c372af`, on the four server engines of `docker/compose.test.yml`. Everything here is EXECUTED output or the script that produced it. The patches are research code: the spec that stands on the memo writes its own.

## The files

| File | What it is |
|---|---|
| `experiments/reproducing-node.patch` | The diff of commit `6644c60f`, the node that first reproduced the defect. That commit is reachable from no branch. |
| `experiments/base.patch` | The unfixed tree plus three seams: `write:after-labels`, `transfer:after-postures`, and `posture:before-commit` at the end of the posture write. |
| `experiments/candA.patch` | `base` without the third seam, plus the mechanism: the stamp read before the labels, the shared locking read last, the stamp row seeded at provisioning. |
| `experiments/candB.patch` | `candA` with the last read taking no lock, and the seam `mint:after-hold` after it. |
| `experiments/candC.patch` | `candA` plus the third seam, the table lock a posture write takes first on Postgres, the hold refusing on a missing row, and the SQL Server hint written `REPEATABLEREAD, FORCESEEK`. |
| `experiments/test_label_experiment.py` | The one test file run in every copy: the window nodes, the lock probes, the statement counts, the contention run and the node that records which calls wait while a posture write is open. |
| `experiments/probe_door.py` | Three sessions on Postgres: whether a waiting posture write is passed by later mints, without and with the table lock. |
| `experiments/run.sh` | Runs the test file in one copy on one engine and writes one result file. |
| `experiments/hang.sh` | Runs the contention node on the SQL Server leg at a given thread count. When the node records a hang, or writes no line in 220 seconds, it reads the server's waiting sessions and stops the run. Its first form stopped a run only when the node recorded the hang; the unfixed tree's run in `master` could not record it, and that run was stopped by hand after 54 minutes. |
| `experiments/tab.py` | Prints the result files of one run as tables. |
| `experiments/out/` | The result files, one JSON object a line, named `<run>-<engine>.jsonl`, and for a hung run the server's counts as `<run>-mssql.server.txt`. |

## The runs

| Run | Copy | What ran |
|---|---|---|
| `base` | `base` | The 33 window nodes an engine. |
| `base2` | `base` | The statement counts. Its contention node ran on 14 threads and is superseded by `base3`; the SQL Server leg of it hung and was stopped, so `base2-mssql.jsonl` holds counts only. |
| `base3` | `base` | The contention run on 64 threads. |
| `candA` | `candA` | The 33 window nodes and the lock probe, an engine. |
| `candA2` | `candA` | The statement counts and the lock probe on Postgres, MariaDB and Oracle. Its contention node is superseded by `candA3`. |
| `candA3` | `candA` | The contention run on 64 threads. |
| `candA4` | `candA` | The statement counts and the lock probe on SQL Server. |
| `candB` | `candB` | The tightening nodes with the third seam. The nodes that hung, named in the memo's section 7, wrote no line. |
| `candC` | `candC` | The 33 window nodes and the lock probe, an engine. |
| `candC3` | `candC` | The contention run on 64 threads, Postgres. |
| `candC-rcsi` | `candC` | The window nodes and the lock probe on SQL Server in a database with `READ_COMMITTED_SNAPSHOT` on. |
| `probe-door` | none | `probe_door.py` on Postgres. |
| `who-base`, `who-candC` | `base`, `candC` | Which calls wait while a posture write is open, an engine. |
| `who-rcsi-base`, `who-rcsi-candC` | `base`, `candC` | The same on SQL Server with `READ_COMMITTED_SNAPSHOT` on. |
| `m1-…-14x16` | `base`, `candC` | The contention run on SQL Server with 14 threads and 16 writers, in `master` and, as `m1-rcsi-…`, in the database with `READ_COMMITTED_SNAPSHOT` on. `m1-base-14x16` wrote no line: it hung, and its `server.txt` was read by hand before it was stopped. |
| `m2-rcsi-…-14x16-r1` to `-r10` | `base`, `candC` | The same run ten more times a copy with the setting on, each answer that is neither a success nor a retryable conflict recorded with its detail. A run with a `server.txt` hung. |
| `m2-rcsi-candC-64x16-r1` to `-r3` | `candC` | The same on 64 threads with the setting on. |
| `m3-…-18x16-r1` to `-r3` | `base`, `candC` | The same in `master` on 18 threads, one for each handle. `m3-base-18x16-r3` wrote no line: the process died inside the ODBC driver, and `m3-base-18x16-r3-mssql.crash.txt` holds the top of the system's crash report. |

## To run it again

Make a copy of the tree beside `run.sh` with `git archive HEAD | tar -x`, copy the built extension `src/vfs/_native.abi3.so` into the copy's `src/vfs/`, apply `reproducing-node.patch` and then one of the four patches, start the engines as the `db_test` skill says, and set `VFS_REPO` to the checkout whose environment holds the drivers. Then `./run.sh <copy> <engine> <run>` with any pytest arguments after it, and `python3 tab.py <run>`. The SQL Server database with the setting on is made with `CREATE DATABASE vfs_rcsi` and `ALTER DATABASE vfs_rcsi SET READ_COMMITTED_SNAPSHOT ON`, and named to `run.sh` as `LABEL_EXPERIMENT_MSSQL_DB`.

## One line

Four patched copies of the tree, one test file and its result files: the unfixed tree's open windows, the mechanism that closes them, the no-lock variant that does not, and which calls wait behind a posture write on each engine.
