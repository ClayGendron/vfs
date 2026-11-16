# A mint proves its label with a shared lock on the everyone stamp, taken as its last statement: every window closes on the four server engines for two more statements a mint

This memo was a placeholder and is now completed in place. It held one choice: how a mint proves the label it stamps against a posture change that commits while the mint runs. The developer asked for the fix on 2026-11-15 ("Work on the first fix"), and the research ran that day in one session of about two hours on the four server legs, inside its three-hour box. The experiment the placeholder named was run as written, with three differences stated under section 8. Sections 9 to 11 were added the same day, after the spec's first review and the developer's rule that a lock never holds up every query: they add a table lock a posture write takes first on Postgres, the list of calls that wait behind an open posture write, and the SQL Server runs at the loop's default thread count. The defect was a needs-validation lead of the release audit run `vfs-run-1-2026-11-07`, fingerprint `vfs/storage/database/labels:mint-reads-posture-outside-revision-lock-stale-everyone-level`. [A row minted across a posture change carries the label the standing posture gives](../specifications/active/2026-11-14-a-row-minted-across-a-posture-change-carries-the-label-the-standing-posture-gives.md) uses the answer. The scripts, the patches and every result file are in [the studies folder](studies/2026-11-14-a-mint-must-prove-its-label-against-a-posture-change-committed-inside-its-window/README.md). No intention: the work is one property across the mint paths.

Labels: EXECUTED means a command ran here on 2026-11-15 and the claim reports its output; READ means read in the file cited, at `08c372af` for vfs; INFERRED means reasoning from the two.

## Sources

vfs at `08c372af`: `src/vfs/storage/backends/database/labels.py`, `writes.py`, `topology.py`, `authorized.py`, `revision.py`, `rights.py`, `backend.py`, `engine.py`, `dialects.py`, `serialized.py`, and `src/vfs/storage/grants.py`. The commit `6644c60f`, reachable from no branch, whose only change is the reproducing node `tests/storage/database/test_races.py::TestRightsAtCommit::test_a_row_minted_across_a_posture_tightening_is_no_more_open_than_the_standing_posture`; its diff is kept as `experiments/reproducing-node.patch`. The engines, from `docker/compose.test.yml`: PostgreSQL 17.11 (`pgvector/pgvector:pg17`), MariaDB 11.8.9, SQL Server 2025 RTM-CU8 with `READ_COMMITTED_SNAPSHOT` off, and Oracle Free 23 (`gvenzl/oracle-free:23-slim`). The drivers: asyncpg 0.31.0, aiomysql 0.3.2, aioodbc 0.5.0, oracledb 4.0.2. The machine: ten cores, macOS, the engines in Docker Desktop. The archived spec [a mutation is authorized for the rows it acts on at its commit point](../specifications/archive/2026-11-14-a-mutation-is-authorized-for-the-rows-it-acts-on-at-its-commit-point.md), for the fence. No reference clone was studied.

## The answer

A mint proves its label in two statements. Before its first read of the posture rows it reads the stamp of the everyone principal, the row a posture write updates. As its last statement before the commit it reads that stamp again under a shared lock held to the commit, and runs again from the top when the value moved. Said simply: the mint checks that no posture changed since it read the postures, and holds the door shut on the next one until it has committed. A posture write waits behind the mints that hold the lock, mints never wait for each other, and the relabel that follows a posture write therefore sees every row those mints made. This closes every window the experiment could open, on all four server engines, for both minters and for write, move and copy (EXECUTED, section 3). It costs two statements for a call that mints and none for a call that does not, three on Oracle (EXECUTED, section 4). It added no deadlock and no unlawful outcome across sixteen concurrent writers, three posture changes and a sweep (EXECUTED, section 6). The other three candidate directions are rejected in section 7. Three things were added after the first review. On Postgres a posture write must take a table lock on the stamps table first, or mints that keep arriving can hold it off (EXECUTED, section 9). While a posture write is open, the mechanism makes one more kind of call wait, a call that creates a row; reads, searches and edits of existing files do not wait (EXECUTED, section 10). And on SQL Server with `READ_COMMITTED_SNAPSHOT` off, every call waits behind an open posture write and a process can stall for good, on the unfixed tree as on the fixed one; with the setting on, neither happens (EXECUTED, sections 10 and 11).

## 1. What the experiment ran

EXECUTED. A scratch copy of the tree made with `git archive HEAD`, outside the repository, with the built extension copied in and the reproducing node applied. Three copies were made from it. `base` is the unfixed tree plus two seams: `write:after-labels`, one line after `labels_for` in `_apply` (`writes.py:412`), and `transfer:after-postures`, one line after `destination_postures` in `transfer_rows` (`topology.py:207`). `candA` is `base` plus the mechanism of the answer. `candB` is `candA` with the last read taking no lock, and a third seam after it. A fourth copy, `candC`, was made after the first review and is described in section 9. One test file, `experiments/test_label_experiment.py`, ran in each copy against each engine, in a schema of its own per test. Each window node stages a rival posture change on a second handle at a seam, drives the rival's relabel to its end, lets the mint finish, and compares every minted row's stored label with the label the standing posture rows give it. A node records `OPEN` when a stored label differs with no relabel mark standing, `closed` when every label agrees, and `refused` when the call left no row.

## 2. Which windows are open on the unfixed tree

EXECUTED on `base`, 132 window nodes, 33 an engine. The posture is tightened to `none`.

| Seam, shape, minter | Postgres | MariaDB | SQL Server | Oracle |
|---|---|---|---|---|
| `write:before-apply`, at the path or at a minted parent, either minter | OPEN | OPEN | closed | closed |
| `write:after-labels`, at the path or at a minted parent, granted | OPEN | OPEN | closed | closed |
| `write:after-labels`, at the path or at a minted parent, system | OPEN | OPEN | OPEN | OPEN |
| `write:after-labels`, at the existing parent, system | closed | closed | OPEN | OPEN |
| every other write node at the existing parent | closed | closed | closed | closed |
| `transfer:after-postures`, move or copy, system | OPEN | OPEN | OPEN | OPEN |
| `transfer:after-postures`, move or copy, granted | closed | closed | closed | closed |
| `transfer:post-collect`, move or copy, either minter | closed | closed | closed | closed |
| restore after a tightening | closed | closed | closed | closed |

The loosening direction, `none` to `read_write`, gave the same table cell for cell: where the tightening leaves a row too open, the loosening leaves it too closed. So the eight legs the session lead found on 2026-11-14 reproduce, and the placeholder's three predictions hold: the system actor's window is open on SQL Server and Oracle once a seam sits after the label read; the transfer path is open on all four engines for the system actor; restore is no mint. Postgres and MariaDB fail 18 of 33 nodes each, SQL Server and Oracle 8 of 33 each.

The `closed` cells for the granted caller on SQL Server and Oracle are the commit-point fence at work: it reads the everyone stamp at the end and redrives. They are not proof for that caller, because the fence takes no lock, and section 7 shows a posture committed after an unlocked read is missed.

## 3. The mechanism closes every window

EXECUTED on `candA`, the same 132 nodes plus four lock probes: 136 of 136 pass, and every window node records `closed`. Under the loosening, a caller holding nothing but the posture read the minted file in all 48 nodes. A call that met a rival ran two attempts and succeeded; a system write on SQL Server or Oracle whose rival committed before its label read ran one, because its label read already saw the new posture (three nodes an engine).

Why it closes, per engine. On Postgres and MariaDB a write runs at `REPEATABLE READ` (READ, `dialects.py:512`, `:582`). The first stamp read comes from the write's snapshot. The last one is a locking read: Postgres refuses it with a serialization failure when the row was updated after the snapshot, and MariaDB reads the newest committed value, which then differs from the first. Either way the attempt runs again, from a snapshot that holds the new posture (EXECUTED: two attempts in all 12 tightening nodes on each; which of the two MariaDB did was not separated). On SQL Server and Oracle, and for move and copy on every engine, each statement reads the latest commit, so the two reads differ when a posture write committed between them. In every case a posture write that begins after the last read waits for the mint's commit, so its relabel starts after the mint's rows are visible and rewrites them (INFERRED from the lock probes of section 5).

The stamp row has to exist for the lock to hold anything. Today it is first written by the first posture verb (READ, `revision.py:96-107`), and provisioning writes the root posture row without it (READ, `engine.py:715`). `candA` seeds it at provisioning with revision 0.

## 4. What it costs in statements

EXECUTED, counted by a `before_cursor_execute` listener on the calling handle, after one warming write by each minter. `base` then `candA`.

| Call | Minter | Postgres | MariaDB | SQL Server | Oracle |
|---|---|---|---|---|---|
| one new file | system | 9 → 11 | 9 → 11 | 9 → 11 | 8 → 11 |
| one new file | granted | 15 → 17 | 15 → 17 | 15 → 17 | 14 → 17 |
| the same file again, no mint | system | 7 → 7 | 9 → 9 | 7 → 7 | 8 → 8 |
| the same file again, no mint | granted | 13 → 13 | 15 → 15 | 13 → 13 | 14 → 14 |
| 10,000 files with parents | system | 39 → 41 | 41 → 43 | 496 → 498 | 48 → 51 |
| 10,000 files with parents | granted | 45 → 47 | 47 → 49 | 512 → 514 | 74 → 77 |
| move one file | system | 16 → 18 | 16 → 18 | 16 → 18 | 15 → 18 |
| move one file | granted | 24 → 26 | 24 → 26 | 24 → 26 | 23 → 26 |
| copy one file | system | 16 → 18 | 16 → 18 | 16 → 18 | 15 → 18 |
| copy one file | granted | 23 → 25 | 23 → 25 | 23 → 25 | 22 → 25 |

So the cost is a constant two statements for an attempt that reads labels, whatever the batch, and nothing for one that does not. Oracle pays three, because it has no shared row lock and takes a shared table lock in a statement of its own (section 5). At the reference deployment's 1,050,000 file writes a day that is about 2,100,000 single-row reads a day by primary key, and 200 a night for the hundred batches (INFERRED from the table and `AGENTS.md`).

The same two statements run on SQLite, where the writer's lock already closes the window and the shared form renders as a plain read. EXECUTED: the suite run in the `candA` copy, the lint and scripts tiers left out, gave 5,202 passed, 11 skipped and 11 failed, and each of the 11 is a pin of a statement count or a statement sequence that the two statements moved: three in `tests/storage/database/test_writes.py`, five in `tests/storage/database/test_authorized.py::TestCost` and three in `tests/base/test_write_at_scale.py`.

## 5. Who waits for whom

EXECUTED, the four lock probes on `candA`: a first session takes the shared lock, a second takes it beside the first, and a third runs the posture write's stamp statement in the engine's no-wait form.

| Engine | The shared form | A second sharer | The posture write's stamp |
|---|---|---|---|
| Postgres | `FOR SHARE` on the stamp row | granted at once | waits: `LockNotAvailableError` under `lock_timeout` |
| MariaDB | `LOCK IN SHARE MODE` on the stamp row | granted at once | waits: error 1205, lock wait timeout |
| SQL Server | the `REPEATABLEREAD` table hint on the stamp row | granted at once | waits: lock request time out under `LOCK_TIMEOUT` |
| Oracle | `LOCK TABLE … IN SHARE MODE` on the stamps table, then a plain read | granted at once | waits: `ORA-00054` on `FOR UPDATE NOWAIT` |

So a mint never waits for another mint, and a posture write waits for the mints that hold the lock. The lock is a mint's last statement, so it is held for the commit only, and a posture write waits for commits and never for a batch's body (READ, the patch). On Oracle the lock is on the whole stamps table, so a grant, revoke or membership write, which stamp other principals, also waits for those commits, and a mint's last statement waits for any such write that has stamped and not yet committed (INFERRED from Oracle's table-lock modes; not staged).

SQLAlchemy renders `with_for_update(read=True)` as `FOR SHARE` on Postgres and `LOCK IN SHARE MODE` on MariaDB, as `FOR UPDATE` on Oracle, and as nothing on SQL Server and SQLite (EXECUTED, the statement compiled against each of the five dialects). So the SQL Server and Oracle forms are facts a `DialectProfile` must declare. An unknown dialect gets whatever its compiler renders, and one that has no `FOR SHARE` would refuse the statement (INFERRED); `FOR UPDATE`, which the topology verbs' serialization point already asks of every dialect (READ, `dialects.py:704-719`), is the form no unknown dialect is newly asked for.

## 6. Contention: sixteen writers, three posture changes and a sweep

EXECUTED on `base` and `candA`. Sixteen handles each write 50 new files under a folder of their own beneath `/p`, half as the system actor and half as a granted caller; a seventeenth handle changes the posture at `/p` three times, each with its relabel; an eighteenth sweeps a deleted tree of 200 files. 804 calls a run.

| Engine | `base` outcomes | `candA` outcomes | Stale labels after, `candA` | Postgres multixacts, `candA` |
|---|---|---|---|---|
| Postgres | 787 success, 17 retryable conflict | 771 success, 33 retryable conflict | 0 of 783 rows | 272 |
| MariaDB | 790 success, 14 retryable conflict | 782 success, 22 retryable conflict | 0 of 797 rows | |
| SQL Server | 804 success | 804 success | 0 of 816 rows | |
| Oracle | 804 success | 804 success | 0 of 816 rows | |

No deadlock error and no other outcome reached a caller on either copy. The retryable conflicts on Postgres and MariaDB are there on `base` too: a relabel rewrites the folders the writers bump, and a write that loses its redrives answers `conflict`. `candA` adds the redrives a posture write now causes; one run a copy does not separate the two (INFERRED). On `base` the run's labels were also right after the relabels settled, so this workload did not reach the window by chance; the seams of section 2 are what open it.

Postgres made 272 multixacts over the run where `base` made none (EXECUTED, `next_multixact_id` read after a `CHECKPOINT` before and after). A multixact is made when two transactions hold a shared lock on one row at once. At the reference deployment's peak of about 20 calls a second the lock is held for a commit's length, so most mints hold it alone (INFERRED); the same mechanism runs under every foreign-key check Postgres makes.

One finding beside the question. With the loop's default executor, 14 threads on this machine, the SQL Server leg of this run hung on `base`: aioodbc runs each call on an executor thread, all 14 were blocked on row locks, and the two sessions that held those locks sat idle in their transactions with no thread to send their next statement (EXECUTED, `sys.dm_exec_requests` and `sys.dm_exec_sessions` during the hang). With 64 threads the same run finished on both copies. It is not the label defect, and the unfixed tree has it. Section 11 ran it again at the default thread count on both trees and found that the mechanism makes it likelier.

## 7. The other candidates

Candidate 2, a re-read with no lock: rejected on evidence. EXECUTED on `candB`, the tightening nodes. On Postgres and MariaDB a plain re-read cannot see past the write's snapshot, so the eight nodes of each engine that were open at the two seams stay open, 16 in all. On SQL Server and Oracle it closes those two seams, and a rival that commits after the re-read leaves the row open again: `OPEN` at the third seam on Oracle and on Postgres, both shapes and both minters. On MariaDB and SQL Server the nodes at the third seam did not finish, because there a relabel waits behind the mint's uncommitted rows and the node's rival runs inside the mint; they were stopped and are not counted.

Candidate 1 in its wide form, the mount revision row: rejected by reading. Every admin write bumps that row and every relabel chunk holds it (READ, `revision.py:53-70`, `labels.py:276`), so each mint would redrive across any grant anywhere and wait behind each chunk. Candidate 1 with the stamp lock held from before the label read: rejected by reading. It would hold the lock through a batch's whole body, so a posture write would wait for the longest batch, and on an engine that queues lock requests in order every later mint would queue behind that posture write. Taken last, the lock is held for the commit.

Candidate 3, the admin side waiting out older mints: not built. No engine-portable way to know which transactions are older was found, and the engine-specific forms need privileges a host app may not grant (INFERRED, as the placeholder said).

Candidate 4, readers distrusting a label that could be stale: not built. It moves the cost onto every read and changes `Rights.admits`, the one authority, where the answer above costs two statements on the calls that mint (INFERRED).

## 8. Where the run differed from the placeholder's plan

Three differences. The plan asked for each candidate built and measured; candidates 3 and 4 were rejected without a build, as section 7 says. The plan asked for the purge beside the writers; the run used `sweep` of the trash root by the system actor, the verb that destroys a deleted tree. The plan asked for multixacts counted on Postgres and got them; it did not ask for the thread count, which the SQL Server hang made necessary.

## 9. On Postgres a waiting posture write is passed by later mints, until it takes a table lock first

The spec review of 2026-11-15 found this, and it was run again here. EXECUTED, `experiments/probe_door.py` on Postgres 17, three sessions on a table shaped like the stamps table. With the posture write issuing only its `UPDATE`: a mint that arrives while the posture write waits is granted `FOR SHARE` at once, the posture write still waits after the first mint commits, a third mint is granted at once too, and the posture write proceeds only when no mint holds the row. So on Postgres mints that keep arriving can hold a posture write off. With the posture write issuing `LOCK TABLE … IN EXCLUSIVE MODE` on the stamps table first: the mint that arrives while it waits queues behind it, and the posture write proceeds as soon as the first mint commits. A plain read of the row, the watch's form, returned at once in both runs. So that table lock holds back a `FOR SHARE` and lets a plain read through (EXECUTED). That it also holds back writes to the table, which are the stamps of other rights changes and already queue on the admin lock, is INFERRED from Postgres's documented lock modes and was not run.

The copy `candC` is `candA` with that statement as the first act of a posture write on Postgres, the hold refusing when its locked read finds no row, and the SQL Server hint written `REPEATABLEREAD, FORCESEEK`. EXECUTED: its window nodes and lock probe pass on all four engines, 34 of 34 each with every window `closed`, and on SQL Server both in `master` and in a database with `READ_COMMITTED_SNAPSHOT` on; its Postgres contention run gave 789 successes and 15 retryable conflicts of 804, no stale label in 801 rows and 325 multixacts. The reviewer ran the three-session order on the other engines: on MariaDB, SQL Server and Oracle a later sharer already queues behind a waiting posture write (EXECUTED by the reviewer, recorded in [the spec review](../reviews/2026-11-15-a-row-minted-across-a-posture-change-carries-the-label-the-standing-posture-gives-spec-review.md)).

## 10. Which calls wait while a posture write is open

The developer asked on 2026-11-15 that a lock never hold up every query on a mount many users share. EXECUTED on `base` and `candC`, the node `test_who_waits_while_a_posture_write_is_open`: a posture write is stopped at a seam after its last statement and before its commit, eleven calls are made one after another on a second handle, and a call that has not returned in 2.5 seconds is recorded as waiting. Every call finished with success once the posture write committed, on every leg.

| Call, while a posture write is open | Postgres, MariaDB, Oracle: `base` | Postgres, MariaDB, Oracle: `candC` | SQL Server: `base` and `candC` | SQL Server with `READ_COMMITTED_SNAPSHOT` on: `base` | the same: `candC` |
|---|---|---|---|---|---|
| read, by the system actor, a granted caller, a caller with the posture only, anonymous | returns | returns | waits | returns | returns |
| glob and grep by a granted caller | returns | returns | waits | returns | returns |
| rewrite an existing file, system or granted | returns | returns | waits | returns | returns |
| create a file, system or granted | returns | waits | waits | returns | waits |
| grant by the system actor | waits | waits | waits | waits | waits |

Three things follow. On Postgres, MariaDB and Oracle the mechanism makes exactly one more kind of call wait for an open posture write: a call that creates a row, which is the call whose label the posture write is about to change. Reads, searches and edits of existing files do not wait, the table lock on Postgres included. A rights change already waited, behind the admin lock.

On SQL Server as the test leg runs it, in `master` with `READ_COMMITTED_SNAPSHOT` off, every call waits for an open posture write, on the unfixed tree: a plain read there takes a shared lock and queues behind the posture write's uncommitted rows. That is not caused by the mechanism and is the larger finding for a mount many users share: any open write transaction holds up the readers of the rows it wrote. In a database with `READ_COMMITTED_SNAPSHOT` on, SQL Server gives the same column as the other three engines (EXECUTED, the database `vfs_rcsi` made for this run; `master` cannot have the setting turned on).

## 11. On SQL Server a process stalls when its blocked calls fill its driver threads, and the mechanism makes that likelier

The spec review asked for the contention run of section 6 on SQL Server at the loop's default thread count, which is 14 on this machine. EXECUTED, `experiments/hang.sh`: 16 writers, each run in a schema of its own. A run is counted hung when it has not finished in 150 seconds or has written no line in 220; a hung run was stopped by the script, and the first one by hand after 54 minutes.

| Database | Threads | `base`, the unfixed tree | `candC`, the mechanism |
|---|---|---|---|
| `master`, `READ_COMMITTED_SNAPSHOT` off | 14 | hung 2 of 2 | hung 1 of 1, and `candA` 1 of 1 |
| the same | 18 | finished 2 of 2, 804 successes each; a third run died, see below | finished 3 of 3, 804 successes each |
| the same | 64 | finished (section 6) | `candA` finished (section 6) |
| `vfs_rcsi`, the setting on | 14 | finished 11 of 11 | finished 7 of 11, hung 4 |
| the same | 64 | not run | finished 3 of 3 |

Every finished run held only successes and retryable conflicts and left no stale label, with one exception named below.

What a hang is. EXECUTED, `sys.dm_exec_requests`, `sys.dm_exec_sessions` and `sys.dm_tran_locks` read during the hangs: 14 requests are blocked, as many as there are threads, and four or five sessions sit idle inside a transaction. With the setting on, all 14 wait for an update lock on an entry row and none waits on the stamps table. In the hang read statement by statement (`m2-rcsi-candC-14x16-r3`), all 14 are the same statement, the guarded version bump of one entry row; the session at the head of the chain is idle, its last statement was the hold, and it holds 48 exclusive key locks and one shared one. Its next act is its commit. aioodbc runs every driver call on the loop's default executor (READ, `aioodbc/connection.py:68`), so the commit needs a thread, and every thread is inside a call that waits for that commit. SQL Server's lock wait has no limit by default, so nothing ends it. Said simply: the writer that could unblock everyone cannot get a thread to say so. The row is the folder `/p`, which each writer's first call bumps when it creates its own folder there (INFERRED from the length of the bound path).

It exists on the unfixed tree: with the setting off, where a plain read waits too, `base` hung both times at 14 threads. vfs gives the driver no executor of its own and builds its engine with SQLAlchemy's default pool of up to 15 connections (READ, `engine.py:219`, `:983-1000`), and the loop's default executor has the processor count plus four threads, 32 at most (READ, CPython's `concurrent/futures/thread.py`). So a host with two processors has six threads, and six calls blocked behind one idle transaction stall it.

The mechanism makes it likelier. With the setting on, `base` finished all 11 runs and `candC` hung in 4 of 11. A split that lopsided comes by chance about once in 22 (INFERRED, 330 of the 7,315 ways to place four hangs among 22 runs). The cause is one more driver call (INFERRED): the hold sits between a mint's row locks and its commit, so a mint that holds a contended row must find a free thread once more than it does today, for the system actor twice where it was once.

With a thread for every call in flight there is no stall. At 18 threads, one for each of the 18 handles, both trees finished every valid run with the setting off: 2 of 2 and 3 of 3, 804 successes each, with no conflict at all.

Two things beside the question. One `base` run at 18 threads died 14 seconds in: the process was killed for heap corruption inside Microsoft's ODBC driver (`BUG IN CLIENT OF LIBMALLOC: memory corruption of free block`, the crashed thread inside `libmsodbcsql.18.dylib`, EXECUTED, the system's crash report), and the server showed no blocked session. It is not a stall and it is on the unfixed tree. And one `candC` run with the setting on, which finished, returned one retryable `backend unavailable` answer beside its successes; the detail was not recorded, and none of the nine later `candC` runs that finished, which did record details, returned one.

## What this memo does not settle

- Whether MariaDB answers the last read with error 1020 or with the newer value. Both redrive. The experiment: log the driver error of the first attempt in one tightening node on the MariaDB leg.
- How many extra redrives a posture write causes under load, apart from the redrives a relabel already causes. The experiment: the contention run of section 6 with the attempts counted per call, ten runs a copy.
- What ends the SQL Server stall and the reader waits of section 10. [The SQL Server memo](2026-11-15-on-sql-server-a-thread-for-every-connection-ends-the-stall-and-snapshot-reads-end-the-reader-waits.md) carries both.
- Why the ODBC driver corrupted the heap once and what the one `backend unavailable` answer was. The experiment: the contention run of section 11 fifty times at 18 threads on `base`, each answer's detail recorded and the crash reports kept.
- The wait a grant or membership write and a mint's last statement impose on each other on Oracle. The experiment: the lock probe of section 5 with a grant write as the third session, and the contention run with a grant a second beside the writers.

## One line

Read the everyone stamp before the labels and again under a shared lock as the last statement: no window stays open on any of the four engines, for two statements a minting call.
