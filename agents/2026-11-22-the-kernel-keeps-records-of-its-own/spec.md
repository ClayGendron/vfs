# The kernel keeps records of its own

A draft, written on 2026-11-22 and read against `a-job-is-interrupted-and-resumed` at `6dae6a1d`. It was reviewed on 2026-11-23 (`reviews/2026-11-23-spec-review.md`), and nothing is built. It is spec 0 of the nine that `agents/2026-11-22-the-specs-for-jobs-and-sessions/overview.md` maps. It rests on the study `agents/2026-11-21-what-a-log-row-per-call-costs/research.md`, on roadmap decision D67 (`context/standards/roadmap.md:1278`), whose SQLite half the ruling of 2026-11-23 reversed, and on five probe scripts run on 2026-11-22 against SQLite 3.50.4 and SQLAlchemy 2.0.52 on Python 3.13.11, which are named where they are used. Probes ran on SQLite and on Postgres 19.0 on 2026-11-23, in the spec review. They are kept in `probes/`, and `probes/output.md` holds what they printed. It was reconciled on 2026-11-22 with the eight other drafts as they stood at `59946f0d`: decisions 24 to 27 are that round's, a sixth probe was run for them, and no decision was renumbered. A last round on 2026-11-22 read the eight again at `7c383f32`, where every name is frozen, and changed what decisions 3, 13, 22, 24, 26 and 27 say without renaming anything.

## The outcome wanted

The kernel has one place to keep rows about calls, and one small private interface to it. A session, a turn, a stamp, a change, a job and a line's journal are kept there by the eight specs that follow, and the action log later. Each of those specs names its table and its statements and invents nothing about storage: where the rows live on each engine, how the tables come to exist, how a row is written without a read waiting for it, how a row is written with a change, how a number is handed out, how expired rows leave, and what `close` does.

This spec builds no session and no job. It builds the place and the interface.

## Builds on

- **The log cost study**, `agents/2026-11-21-what-a-log-row-per-call-costs/research.md`. Run on 2026-11-21. It is the measured basis: written behind, a read adds zero synchronous statements; on SQLite the kernel's rows queue behind the mount's writes when they share its file, which decision 4 takes as its price; one buffer for each router with one flusher held at most 258 rows.
- **Roadmap decision D67**, decided on 2026-11-22 and reversed for SQLite by the ruling of 2026-11-23: it put the log on SQLite in a database file of its own beside the mount's file. The records are now in the mount's own file (decision 4). Its Postgres half stands: the root mount's schema.
- **`agents/2026-11-20-vfs-serves-sqlite-and-postgres-only/spec.md`**, landed as pull request 30. Two engines, and a generic floor fit for testing only.
- **`context/specifications/archive/2026-11-12-close-leaves-no-sqlite-side-files.md`** and **`agents/2026-11-21-a-timed-out-close-leaves-no-connection-open/spec.md`**, both landed. A closed SQLite storage leaves its database file and nothing beside it.
- **`agents/2026-11-21-a-sqlite-writer-beside-a-batch-waits-for-its-commit/spec.md`**, landed. A SQLite writer waits five seconds a try for four tries.
- **`agents/2026-11-21-a-storage-owns-its-engine-well/spec.md`**, drafted and not built. It rewrites `src/vfs/storage/backends/database/engine.py`, and so does landing 1 here. Whichever lands second is rebased on the first. Its decision 1, settings sent once for each connection, then covers the store's connections too.
- **`agents/2026-11-21-a-cancelled-call-is-whole-on-every-path/spec.md`**, drafted and not built. It rewrites `src/vfs/storage/backends/database/attempts.py`. This spec adds one function to that module and changes none.
- **The eight other specs of the overview**, each drafted and none built, read at `59946f0d` and again at `7c383f32`. This spec needs nothing from any of them to be built. What each asks of the store is answered in decision 27.
  - Spec 1, `a-row-carries-a-vid-and-a-change-can-require-it`, and spec 6, `a-policy-judges-each-step`, keep no record and do not use the store.
  - Spec 2, `a-session-is-stored-named-and-forked`: `vfs_sessions` (its decision 13, "`vfs_sessions` holds one row per session, under a key that is never used twice"), `resolve` (decision 14), the use written behind as the kind `SESSION_USE` (decision 17), removal and its one sweeper (decision 22).
  - Spec 3, `the-session-remembers-what-it-read`: `vfs_session_stamps` (decision 4), its store statement (decision 6), a read's stamps behind and a change's with the change (decision 8), the trim (decision 15), and the six functions through which other specs reach the stamps (decision 21, "Other specs reach the stamps through six functions of one module").
  - Spec 4, `a-session-works-in-turns-and-rewinds-or-forks-at-one`: `vfs_session_turns` (decision 2), the counter (decision 4), the rewind's one transaction (decision 12), the fork's copy (decision 17).
  - Spec 5, `a-rewind-puts-a-sessions-files-back`: `vfs_session_changes` (decision 3), written by the record-after form (decision 4).
  - Spec 7, `a-job-is-interrupted-and-resumed`: `vfs_jobs` and `vfs_job_pages` (decision 4), the conditional update (decision 5), the job committed before its result returns (decision 6), the claim and its lease (decisions 21 and 23), `cancel_session_jobs` (decision 35), the lapse (decision 36).
  - Spec 8, `an-interrupted-line-replays-its-replies`: `vfs_job_replies` (decision 9).

## Terms

- **Record.** One row the kernel keeps about calls: a session, a turn, a stamp, a change, a job, a reply of a line.
- **Kernel store.** The one object, for each file system, through which every record is read and written. In code it is `KernelStore`. The overview calls it by this name.
- **Root storage.** The storage of the mount at `/`, which the kernel owns.
- **Place.** The database a kernel store keeps its tables in: a SQLAlchemy URL, the engine arguments, a schema. In code it is `RecordPlace`.
- **Root's file.** On SQLite, the database file of the root storage. Since the ruling of 2026-11-23 the store's tables are in it.
- **Writer.** On SQLite, the one connection that may write a database file at a time. Every other writer of that file waits.
- **Synchronous.** Sent and awaited before the call returns.
- **Written behind.** Put in a buffer in memory and written by a task of the store's own, after the call that produced it has returned.
- **Flush.** One transaction in which that task writes rows from the buffer.
- **Kind.** One sort of row that is written behind, with the function that writes a batch of it.
- **Scope.** A value a caller attaches to rows it puts behind, so that it can later wait for those rows alone.
- **Sweep.** The removal of records whose expiry has passed.
- **First touch.** The first use of a database by a process, where its tables are made or verified.
- **Format version.** An integer the store writes when it makes its tables, and compares on every first touch.
- **Attempt.** One try of one transaction. `documentation/maintainers/cancellation.md` defines it.
- **Engine core.** The part of today's `EngineHost` that any database needs and that knows nothing of a mount.

## What the code does today

Read on 2026-11-22 at `6dae6a1d`. A probe is a script that was run. The scripts of 2026-11-22 are under the session's scratch directory, in `specs/spec0/`, and are not kept in the repository. A row that cites `probes/` was run on 2026-11-23 at `1c10dca1`, by a script kept in this work directory.

| Fact | How it is known |
|---|---|
| The kernel's constructor takes `storage`. With none it makes an `InMemoryStorage`. The root mount is `owned`. | Read, `src/vfs/base.py:301-302` and `:319-327`. Run: the default root is an `InMemoryStorage` and is owned. |
| The constructor does no I/O and binds nothing to a loop. The synchronous face builds the kernel on the caller's thread and starts one loop thread. | Read, `src/vfs/base.py:286-331` and `src/vfs/sync.py:120-135`, `:648-656`. Run: the facade starts one thread, `vfs-sync-loop`, and `close()` ends it. |
| The kernel keeps no table of its own. Every call on a storage goes through `_call_storage`, and a storage "opens and commits its own transaction inside each method, and the kernel never sees one". | Read, `src/vfs/base.py:2852-2879`. |
| `close()` empties the mount table, then closes each owned storage once, all at the same time, each within `close_timeout`. A close that was cancelled keeps what it had not closed, and a second `close()` finishes. A storage whose own close outlived `close_timeout` is not kept: the timeout is collected as an error, and the kept set is emptied after the gather. | Read, `src/vfs/base.py:539-579`. Run, `probes/probe_close_timeout.py`: after a timeout the second `close()` did not enter the storage's close again, and after a cancellation it did. |
| A session is an object in memory. `open_session` returns `AsyncSession(self, authority)`. | Read, `src/vfs/base.py:655-663`. |
| A storage declares verbs through `capabilities()`, a set of `Op`. What is not a verb is an optional protocol: `SupportsHolds`, `SupportsTraits`, `SupportsRebuild`, `SupportsClose`. | Read, `src/vfs/storage/protocol.py:469-577`. Run: the default root satisfies all four, and its 24 capabilities are verb names. |
| One class serves every storage. `SQLiteStorage` and `PostgresStorage` construct `DatabaseStorage`, and `InMemoryStorage` is a `SQLiteStorage` whose path is `:memory:`. | Read, `src/vfs/storage/backends/sqlite.py:77-85`, `memory.py:36-77`. |
| A storage builds one `EngineHost`. The host builds the engine, the mount's tables, the session factory, and runs first touch. | Read, `src/vfs/storage/backends/database/backend.py:166-173`, `engine.py:161-242`. |
| `EngineHost` holds two things in one class. One is what any database needs: the engine (`:195`), the profile (`:198`), the listeners that refuse a cancelled attempt (`:203-208`), the turns of a one-connection database (`:211-213`), SQLite's transaction control (`:215-216`, `:955-985`), the retry (`:336-371`), the classifier (`:373-399`), the file settings (`:575-582`) and the dispose (`:547`). The other is what only a mount needs: the mount's tables (`:182`), the vector probe, the root row and the posture (`:625-696`), the planner statistics. | Read. The module is held at 1,008 lines, `tests/lint/allowlist.py:32` (1,017 at `b00ab57`, where the landings were cut). |
| First touch makes the tables when the meta table is missing, under a serialization point, and writes `SCHEMA_FORMAT_VERSION`, which is 28. A database of another version is refused with `vfs.unavailable.schema` and the words "re-provision the mount". Nothing migrates a schema. | Read, `engine.py:625-663`, `:698-703`, `:913-930`, `src/vfs/models/rows.py:135`. Pinned by `test_version_mismatch_refuses_loudly`, `tests/storage/database/test_engine.py:254`. |
| SQLite's connections carry `busy_timeout = 5000` and `synchronous = FULL`, and the file is put in WAL. A busy writer is retried four times. | Read, `dialects.py:368-381`, `engine.py:170-171`. |
| On Postgres a verb runs at REPEATABLE READ and a topology verb at READ COMMITTED. | Read, `dialects.py:420-421`, `:476-504`. |
| The statement budgets have one home: `membership_budget`, `chunked`, `rows_per_statement`, `statement_budget` and `bulk_insert`. | Read, `dialects.py:541-548`, `:573-630`, `:673-724`. |
| SQLAlchemy is imported by the database adapter, by `models/rows.py` and `models/vector.py`, and by the two named storages. No module of the kernel imports it. The lint lets four modules import the adapter. | Run, a search of `src/vfs`. Read, `tests/lint/test_code_shape.py:39-42`. |
| On SQLite an attempt runs in a task its caller's cancellation does not enter. A task started inside an attempt copies the attempt's mark. | Read, `attempts.py:97`, `documentation/maintainers/cancellation.md`. |
| No work in `src/vfs` starts on a timer of its own. The statistics pass is started by a write, and expired trash is removed when a caller runs `sweep`, whose cutoff reads `datetime.now(UTC)` in place. | Read, `engine.py:449-462`, `trash.py:388`. |
| `BEGIN IMMEDIATE` on a connection that has attached a second database locks that database too. A second connection's write to the attached file was refused `database is locked`. | Run, `probe_sqlite_files.py`, step 2. |
| Two engines on one SQLite file, the mount's and a second, leave the file and no side file once both are closed, in either order and together. With one connection of the second engine still out at the dispose, `-wal` and `-shm` stay, and they stay after that connection is returned. | Run, `probes/probe_sqlite_close.py`. |
| A SQLite connection creates its file when it is opened, before any statement. Two engines that were built and never connected created no file. | Run, `probe_sqlite_files.py` step 1, `probe_vfs.py` step B. |
| A mount opened on a file that already holds tables it did not make verifies its own meta row and serves. A store's first touch before the mount's leaves the file at page size 16,384 in WAL, and the mount then makes its 24 tables beside the store's. The mount's first touch and the store's, started at once on a fresh file, both served, eight times of eight. | Run, `probes/probe_sqlite_first_touch.py`. |
| Eight first touches of one store's tables at once made one meta row, on SQLite and on Postgres. | Run, `probes/probe_statements.py`. |
| A role with no `CREATE` on the schema, or with no rights on the tables, is refused with SQLSTATE `42501`. The adapter has a test for that code, `is_insufficient_privilege`, and `classify_failure` does not use it: it reads the refusal as a permanent statement defect, `vfs.internal`. | Read, `dialects.py:832`, `engine.py:373-399`. Run, `probes/probe_postgres_refusals.py`. |
| A SQLite mount whose file is read-only serves a read, and refuses a write with `vfs.unavailable`, retryable. It serves a read when its directory is read-only too. | Run, `probe_readonly.py`. |
| SQLAlchemy gives a SQLite file a queue pool and `:memory:` a pool of one connection. It reads `file::memory:?cache=shared&uri=true` as a file. | Run, `probe_vfs.py` steps B and G. Read, `drivers.py:124-127`, `:145`. |
| `UPDATE … RETURNING`, an upsert with a `WHERE` on the update, and `DELETE … WHERE key IN (SELECT … ORDER BY … LIMIT)` compile for both dialects and ran on SQLite. Two connections handed out 2, 3, 4, 5, 6, 7 with no repeat. | Run, `probe_statements.py` and `probe_sqlite_files.py` step 5. |
| A task started with `context=contextvars.Context()` does not see its starter's context variables. Python 3.11 is the floor. | Run, `probe_vfs.py` step F. Read, `pyproject.toml:19`. |
| A read issues 4 statements and a one-file write 21 on SQLite and 17 on Postgres, as a named principal. | The study, `research.md:48-53`. |

## The problem

The kernel keeps nothing. Eight specs each need a row that outlives a call: what a session saw, where a turn ended, a job that waits for an answer. Three facts decide where such rows can live.

- **On SQLite they share the mount's one writer, wherever they are written from.** The study shared the file and 12 of 19 flushes failed after the five-second lock wait, the buffer grew to 2,360 rows, and claims timed out and refused the writes they guarded (`research.md:13`). With a file of its own no flush failed. The ruling of 2026-11-23 keeps one file all the same, so the store has to be built so that every one of those failures is a delay or a refusal, or a loss that decision 4 names and a caller is told of.
- **A read cannot write them itself.** One synchronous row for each call turned a SQLite read into a writer: during a batch its median went from 70 ms to 856 ms (`research.md:15`). The reference deployment refuses any design where a read waits on a writer.
- **A record cannot join the mount's transaction.** A storage commits inside its own method, and a change may land on a mount that is not the root. So "with the change" has to mean something other than one transaction, and every spec that writes a record beside a change has to know exactly what.

Left to themselves, eight specs would answer these eight ways.

## Decisions

### 1. A record is not first-class and has no path

A record is a row the kernel keeps about calls. It is not an Entry, it adds no value to `kind`, and no path names it. No verb reads, lists, greps or searches it, the `/.vfs` subtree does not show it, and it is in no storage's tables. It is reached through management methods that later specs add, as a grant and a posture are.

Of the constitution's five primitives this spec manipulates none. It touches Mount in one way: the root mount's storage says where the records are kept. A view of sessions or jobs in the namespace is left out of all nine specs.

Reason: Article 1 allows five first-class things and requires each to have a path. A record with a path would need a kind, a revision and rights of its own, and the overview rules that a session, a turn and a job are records and not primitives.

### 2. The root storage names a place, and the kernel builds one store on it

A file system has exactly one `KernelStore`. The kernel builds it in its constructor from the place its root storage names, with no I/O. The store owns its own engine, its tables, its buffer and its one background task. The storage's own code never reads or writes a kernel table, and the store never reads or writes a mount's table.

| Shape | Verdict |
|---|---|
| The storage implements the whole record interface | Rejected. Every later spec would add methods to the storage protocol, a third-party storage would have to write all of them, and every mount that is not the root would carry machinery nothing calls. |
| The kernel opens sessions on `storage.engine` | Rejected. That engine is the storage's, and it is there "for listeners alone" (`backend.py:191-198`). Nothing but the storage makes a transaction on it (`documentation/maintainers/cancellation.md`), and a third-party storage has none. |
| The storage names a place, and the kernel builds the store there | Chosen. A storage answers one question with one value. Everything else is written once. |

The store lives in a new package, `src/vfs/kernel_store/`. Every statement about a record is written there, by this spec and by the eight that follow, so `vfs.base` and `vfs.session` keep importing no SQLAlchemy. The package sits on a rung of its own in `LAYERS`, above `vfs.storage.backends` and below `vfs.mounts`. Its module `vfs.kernel_store.store` joins `ADAPTER_IMPORTERS`, because it builds on the adapter's engine core, its dialect profiles and its statement budgets.

Reason: one buffer and one flusher for each router is the shape the study measured (`research.md:157`), and a store that belongs to the kernel is one for each file system by construction.

### 3. A storage declares its place through one optional attribute

`src/vfs/storage/protocol.py` gains a value and a protocol. It still imports no SQLAlchemy.

```python
@dataclass(frozen=True, slots=True)
class RecordPlace:
    url: str | URL                                    # a SQLAlchemy URL of SQLite or of Postgres
    label: str                                        # how a message names the place; never a URL, which can hold a password
    engine_arguments: Mapping[str, Any] | None = None
    schema: str | None = None
    durable: bool = True                              # False for a database in memory

    @classmethod
    def in_memory(cls) -> RecordPlace: ...            # url "sqlite+aiosqlite://", label "memory", durable False


@runtime_checkable
class SupportsRecordPlace(Protocol):
    @property
    def record_place(self) -> RecordPlace | None: ...
```

- `DatabaseStorage` gains the read-only property `record_place`. It does no I/O. What it returns on each engine is decisions 4, 5 and 6.
- The kernel asks once, in its constructor. A storage with no such attribute, or one that returns `None`, gets `RecordPlace.in_memory()`.
- A third-party storage has to provide nothing. To have the kernel's records kept, it returns a `RecordPlace` that names a SQLite file or a Postgres database. It writes no table and no statement.
- A place never prints a password. `DatabaseStorage.record_place` hands the URL as SQLAlchemy's `URL`, which masks its password when it is printed, and `RecordPlace` leaves `url` and `engine_arguments` out of its `repr`. A place printed in a log or a traceback shows its label, its schema and `durable`.
- A place whose URL is of another dialect raises `ValueError` when the store is built, which is when the file system is made. It names the dialect and never the URL, as `url_of_engine` does (`drivers.py:78-94`): "the kernel keeps its records in SQLite or Postgres, and the root storage's record_place names a URL of {dialect!r}". A `DatabaseStorage` on the generic floor returns `None`, so it never raises.
- It is not a capability. `capabilities()` is a set of verbs that the gate reads, and a record is reached by no verb.
- `RecordPlace` is exported from `vfs` and `SupportsRecordPlace` from `vfs.storage`, because the docs export refuses a public signature that names a type no exported name reaches (`documentation/maintainers/how-we-name.md`, "Public and private").

Reason: an optional protocol is how a storage already says what is not a verb (`SupportsHolds`, `SupportsClose`). A URL is the smallest thing a storage can give that lets one implementation serve every storage.

### 4. On SQLite the place is the mount's own file, on connections of the store's own

Ruled on 2026-11-23. This decision's first form was "On SQLite the place is a second file beside the mount's, named with `-kernel`", which the study recommended and roadmap decision D67 had taken. The ruling reverses both, and states the price below.

For a storage on a SQLite file, `record_place` is the storage's own URL: the same file. The kernel's tables are made in it, beside the mount's, under names that begin with `vfs_kernel_`, `vfs_session` or `vfs_job`. The store reaches the file through an engine of its own, so a store transaction is never a mount's transaction and never rides a mount's connection. The storage's `engine_arguments` are passed on without `pool`, as on Postgres. A `pool` object belongs to one engine. A `creator` or `connect_args` makes a connection each time it is called and belongs to none, and a file that only they can open, an encrypted one for example, must be opened by the store's connections too. The label is the file's path as text. The schema is `None`.

This is the rule Postgres has in decision 5: the kernel's tables live in the root storage's database, on connections of the store's own.

| Case | What happens |
|---|---|
| The file | The mount's. No other file is made, by a file system that keeps records or by one that keeps none. |
| The tables | Made at the store's first use, in the mount's file. The mount's own tables, its meta row and its format number are not touched. |
| Journal mode and settings | The file is already in WAL. The store's connections carry `synchronous = FULL` and `busy_timeout = 5000`, the SQLite profile's own settings (`dialects.py:368-381`), sent by the same code. The vector extension is not loaded on them. |
| `ATTACH` | Never used. |
| `:memory:` | Decision 6. |
| `file::memory:` with `uri=true` | `record_place` is `None`. SQLAlchemy reads that URL as a file. |
| A mount file that is read-only | The mount serves reads. The store cannot be written: a row written behind is held and in the end dropped, by decisions 14 and 15, a synchronous call raises `KernelStoreUnavailable`, and one `WARNING` names the path. Each row put behind starts one attempt, which fails at once and waits for nothing (`probes/output.md`, section 7). The store does not fall back to memory. After `close()` the `-wal` and `-shm` files stay, as they do today for a read-only mount with no store: a connection that cannot write does not remove them. |
| `close()` | The file stays, with its records in it. Its `-wal` and `-shm` files are removed once the last connection of either engine closes (decision 19). |
| A copy or a backup of the file | Carries the sessions and the jobs with the files. |

**The price, which is SQLite's alone.** A SQLite file has one writer. The store's writes and the mount's writes now share it.

- **A read still never waits.** A read's whole dealing with the store is `put_behind`, and a `query` reads beside the writer in WAL.
- **A store write waits behind a mount write, and a mount write behind a store write.** A flush holds the writer for one batch of at most 1,024 rows, a `commit` for its statements, a sweep for one chunk. Each is a commit's length.
- **During a batch on the mount, the store's writes stall.** A 10,000-entry write held the writer for about 28 seconds in the study. With the log in the mount's file, 12 of 19 flushes failed, the buffer grew to 2,360 rows, and claims timed out (`research.md:13`, `:89`). With a file of its own no flush failed. That measured difference is what this ruling gives up.
- **The action log, when it is built, shares the same writer** and writes twice for each change. Its spec costs that against this decision.

**What was measured on 2026-11-23**, on a stand-in for this store beside today's code (`probes/output.md`, sections 1 to 5). The stand-in waits four tries and flushes as soon as it is free, as this store does. In every window no read waited and no read failed.

| The file's writer is | Flushes that failed | Most rows in the buffer, of 16,384 | A change's record that was lost |
|---|---|---|---|
| free, with eight readers and one writer | 0 of 155 | 213 | 0 |
| held about 8 seconds by a 10,000-entry write | 0 of 38 | 1,503 | 0 |
| held 30 seconds, three times over | 3 of 4 | 12,210 | 1 of 7 |
| held 60 seconds | 2 of 3 | 16,384, and 9,047 rows dropped | 0 of 3 |

In a file of the store's own, the first three windows failed no flush and lost no record, and the buffer held 12 rows at most. The 60-second window was run in the mount's file alone.

- **Most failures are a delay or a refusal.** A flush that fails keeps its rows (decision 15). A change checks the buffer before the store, so in one process a session still finds what it was shown. Another process finds the stamp late, and its change is refused until one read. A job that cannot be stored or claimed is refused as unavailable and can be tried again. A one-file write by another caller is already refused in that window today (`agents/2026-11-21-a-write-beside-a-batch-on-sqlite-is-refused-after-twenty-seconds/spec.md`).
- **A record that goes with a change can be lost, and not only delayed.** A `record_after` that waits out its four tries, about 21 seconds, returns its warning, and the change stands with no record, for good (decision 10). The caller is told: the result carries the warning. A stamp lost this way costs the session one refusal, which one read clears. A change row lost this way is a change that a rewind does not put back (spec 5, decision 4). It took a writer held longer than 20 seconds to do it: 1 one-file write of 7 behind 30-second holds, and none behind an 8-second batch.
- **Rows written behind are dropped when a writer is held longer than the buffer lasts.** At 439 reads a second the buffer was full after 37 seconds, and a 60-second hold dropped 9,047 rows. Each is a row decision 14 lets go. A dropped stamp costs a refusal that one read clears, and a dropped use leaves the session's last use behind by one touch.
- **A sweep pass takes most of the writer while it runs.** Its chunks follow each other, and a SQLite writer that waits polls for the file with sleeps of up to 100 ms. Beside a pass of 600,000 rows a one-file writer landed 17 writes in 9 seconds, against 102 beside a pass in another file. None was refused. A long pass is run when the root is quiet (decision 17).
- **The one read that calls the store waits on the mount's writer.** A read that a policy stops stores its job with `commit` (decision 22, rule 3), behind a batch on the root for up to four tries.
- **A process that closes behind a held writer drops what it had buffered.** Its last flush makes one try and gives up (decision 19).
- **With nothing else running the cost is small.** A read's median did not move, 21.4 ms to 21.9. A one-file write's moved from 49 ms to 52. The store wrote 17 batches a second where a file of its own wrote 115, and a store commit waited 4.5 ms at the median to begin and 0.56 seconds at most.

Reason: one file is what a person who keeps a SQLite database expects. There is one thing to copy, to back up and to delete, the tutorial's sentence that `vfs.db` is the only file stays true for every file system, and the rule is the same on both engines. The price falls on a writer held for longer than about 20 seconds, which on SQLite is a long batch or batches one after another, and the working agreement gives that load to Postgres: SQLite serves demos and local applications. On Postgres, with a pool of its own, no flush and no record failed in any window that was run, a 10,000-entry write among them. Reason against a fallback to memory: a failure to write can be passing, and a process that silently kept its jobs in memory would save a job that no other process can resume.

### 5. On Postgres the place is the mount's database and schema, on a pool of the store's own

For a storage on Postgres, `record_place` is the storage's URL, its schema, and its `engine_arguments` without `pool`. The label is the schema's name, or "the default schema" when none is set.

- **The same database and schema.** The tables sit beside the mount's. Their names begin with `vfs_kernel_`, `vfs_session` or `vfs_job`, and no mount table's name does. A lint holds both halves.
- **A pool of its own.** The store builds a second engine. Its pool has the class and the size of the mount's, because both come from the same arguments. A `pool` object the application made belongs to one engine and is left out, and the store's pool is then SQLAlchemy's default.
- **READ COMMITTED, pinned.** A counter and a claim must read what a rival committed while they waited for its row lock. Every store transaction carries the isolation level in its execution options, as a topology verb does (`dialects.py:492-504`), so a default of another level on the role, the database or the server changes nothing. Without the pin, and with the server's default at REPEATABLE READ, two connections that took 50 numbers each had 50 statements refused `40001` (`probes/output.md`, section 10).
- **Every supported major version, 15 to 19.** The store issues `CREATE TABLE`, `INSERT … ON CONFLICT`, `UPDATE … RETURNING`, `DELETE … WHERE … IN (SELECT … LIMIT)` and `pg_advisory_xact_lock`. None is newer than Postgres 9.5. It needs no extension and does not probe for pgvector.
- **The role.** First touch makes the tables, so it needs `CREATE` on the schema once, as the mount's first touch does. Where the serving role may not create tables, the first record call of a role that may makes them, and the serving role is granted `SELECT`, `INSERT`, `UPDATE` and `DELETE` on each kernel table. Until both are done, the serving role's record calls are refused as decision 9 says, with a detail that names the grant.
- **A listener on `storage.engine` is not on the store's engine.** What reaches both is `engine_arguments`: `async_creator`, `connect_args`, the pool's size.

Reason for the schema: the study put the log in the mount's schema and found nothing waited (`research.md:107`). Reason for a pool of its own: it is the configuration that was measured, a second engine with the same pool defaults (`research.md:29`), and it was measured again on 2026-11-23 against the mount's pool (`probes/output.md`, sections 13 and 14). With 32 writing sessions a record added 22 to 25 ms to a write's median of 192 ms on the mount's pool, on a pool of 15 and on a pool of 32 alike, and the store's pool never held more than 8 connections. Beside 32 batches of 10,000, which exhaust the mount's pool, a record on the mount's pool failed 5 times and a flush once, each after the pool's 30-second wait, and on a pool of its own nothing failed. A larger pool bought nothing. The size follows the mount's because a call's store transaction and its mount transaction never overlap, so the store needs one connection for each change in flight and one for the flusher, which is what the mount's pool was sized for.

### 6. A root in memory keeps its records in a second database in memory

A storage whose URL SQLAlchemy gives the pool of one connection returns `RecordPlace.in_memory()`. That is the test `merge_engine_arguments` already uses (`drivers.py:145`), and `InMemoryStorage` meets it. The store then has a private in-memory database of its own, with its own connection and its own turn lock. A store transaction never takes the mount's turn, and a verb never waits behind a flush. The records end when the store is closed or the process ends.

A file system whose records are in memory, and which holds a mount whose storage names a durable place, logs one `WARNING` on `vfs.kernel_store`, at the first record it writes while such a mount is held, whenever the mount was added:

> this file system keeps its sessions and jobs in memory, because its root storage names no database for them; they end with this process and no other process sees them. A mount beneath the root is a database: make the root storage a database to keep them there.

Reason: one implementation serves the in-memory role on the code path the engines run, which is why `InMemoryStorage` is SQLite (`memory.py:1-8`). The warning is for the one shape where the files outlive the process and the sessions do not, which nothing else would show.

### 7. The store's engine is built on the part of the engine host that is not about a mount

`EngineHost` is split. A new class `EngineCore`, in `src/vfs/storage/backends/database/core.py`, takes what any database needs, and `EngineHost` becomes a subclass that adds the mount.

```python
class EngineCore:
    def __init__(self, *, url, engine_arguments=None, retry_attempts=4, retry_base_delay=0.05, vector=True) -> None: ...
    engine: AsyncEngine
    session_factory: Callable[[], AsyncSession]
    profile: DialectProfile
    parameter_budget: int
    membership_budget: int
    async def with_retry(self, fn): ...
    def classify_failure(self, exc, *, context): ...
    async def apply_file_settings(self) -> None: ...
    async def close(self) -> None: ...
```

- The members keep the names they have on `EngineHost`, so no caller of the host changes.
- `vector=False` leaves the vector extension out of the checkout. The store passes it.
- A subclass is told when a one-connection database opens a second connection, and makes its tables again. `EngineHost` does this today through `_rearm`.
- The split changes no behaviour. `engine.py` falls under its held count, and its entry in `MODULE_LINE_BASELINE` is lowered with it, or removed if the module is then under the ceiling.

The store holds one `EngineCore`, built at the store's first use. So on SQLite the store's attempts run out of a cancelled caller's reach, its failed cursors close, its in-memory database takes turns, and its close leaves no side file, by the code that already does each for a mount.

Reason: a second copy of the engine set-up would drift from the first, and the rules it carries were each paid for with a defect: a cancelled call that cost an in-memory database, a cursor that kept a write lock.

### 8. The tables are made at the store's first use, and a store of another format is refused

- **Where the tables are written.** `src/vfs/models/kernel_rows.py` holds `build_kernel_tables(schema=None) -> KernelTables`, a `NamedTuple` of tables on one `MetaData`, as `build_vfs_tables` is. A spec that owns a table adds it there.
- **This spec's one table.** `vfs_kernel_meta` has `id` (an integer key, checked to be 1), `format_version` (an integer, not null) and `created_at`.
- **The constants.** `KERNEL_FORMAT_VERSION: Final = 1`. `KERNEL_TABLE_PREFIXES: Final = ("vfs_kernel_", "vfs_session", "vfs_job")`.
- **First touch.** It is lazy and idempotent, and runs on the caller's loop at the first `query`, `commit` or flush. It sends the file settings, then opens one writer transaction. It takes the serialization point: `BEGIN IMMEDIATE` on SQLite, and on Postgres `pg_advisory_xact_lock` on a key made from the meta table's qualified name, which is not the mount's key. If the meta table is missing it runs `create_all(checkfirst=True)`. It reads the meta row, and inserts one when there is none, under a savepoint so that a rival's insert is harmless. A first touch that fails is not remembered, and the next call tries again.
- **Changing the shape.** A landing that adds or changes a kernel table adds one to `KERNEL_FORMAT_VERSION`. The constant is one line, so two branches that both change the tables meet there as a merge conflict.
- **No migration and no reset.** Nothing alters a table, and nothing drops one.
- **A store made by another build.** Its format differs, and it is refused with `vfs.unavailable.schema`, `data={"found": f, "expected": e}`. Every `query` and `commit` raises, every row written behind is dropped, and one `WARNING` is logged. The file verbs are not affected.

The detail of that refusal is:

> the kernel store at {label} has format {found} and this build keeps format {expected}; no session or job is kept until it is made again: {remedy}

The remedy on both engines is to drop the kernel's tables and nothing else: on SQLite "close every process that uses {path} and drop these tables: {names}", and on Postgres "drop these tables in schema {schema}: {names}". `{names}` is the list of `build_kernel_tables`, in the order they are to be dropped, dependents first. The remedy names the tables and not a prefix, because neither engine reserves the prefixes: a file that held an application's own `vfs_session_notes` was served by both first touches (`probes/output.md`, section 7), and a person told to drop by prefix would drop that table too. The remedy never names the file for deletion, since the file holds the mount.

Reason for refusing: it is the mount's own rule, "verified, never repaired" (`engine.py:635-637`). Reason against a reset: two builds can serve one store at once during a deployment, and each would drop the other's tables; and a reset would end every waiting job with no word. The design is not released, so there is no store to migrate. When the first release ships, this decision is rewritten with the working agreement's section on the project's stage.

### 9. The store is used through `query` and `commit`, and a failure is one exception

```python
async def query(self, fn: Callable[[Transaction], Awaitable[T]]) -> T
async def commit(self, fn: Callable[[Transaction], Awaitable[T]]) -> T

class KernelStoreUnavailable(Exception):
    error: ResultError
```

- `Transaction` is SQLAlchemy's `AsyncSession`, under the one name the store gives it. In VFS a session is something else (spec 2), so every signature of the store and every module of `vfs.kernel_store` calls this object a transaction. `fn` runs SQLAlchemy Core statements on it with `transaction.execute(statement)`, and reads a row count from the result where it needs one.
- Each runs first touch when it is needed, then `fn` on one transaction under the core's retry. `commit` opens a writer transaction, `BEGIN IMMEDIATE` on SQLite, and commits when `fn` returns. An exception from `fn` rolls back and is raised as it is.
- `fn` runs again from its first statement when the engine asks for a retry. It reads everything from its arguments and its transaction.
- The `fn` of a `query` writes nothing. A SQLite transaction that reads and then writes is refused whenever another connection committed in between, and that refusal is not retried (`dialects.py:382-384`).
- A `commit` waits as a mount's write does: four tries, and on SQLite five seconds a try.
- A driver failure that escapes the retry, retries that run out, a pool that gives no connection, a refused first touch and a closed store each raise `KernelStoreUnavailable`. Its `error` is classified by the core's `classify_failure` with the context `kernel store`, or is first touch's refusal. The kinds are the ones that exist: `vfs.unavailable`, `vfs.unavailable.backend`, `vfs.unavailable.schema` and `vfs.internal`. Retries that run out are `vfs.unavailable` and retryable, and not the `vfs.conflict` a mount's write answers, because no precondition of a caller's is stale. Their detail is "kernel store kept losing to concurrent changes: {the retry's own words}", as a mount's is with the verb's name. The error names no path. A closed store answers `vfs.unavailable.backend` with "the filesystem is closed", the kernel's own words (`base.py:3069-3071`).
- **A refusal for want of a privilege is not a defect in VFS.** A first touch or a write refused with SQLSTATE `42501`, which `is_insufficient_privilege` tests (`dialects.py:832`), is `vfs.unavailable`, not retryable, and never the `vfs.internal` that the core's classifier gives it. The store checks for it before it calls the classifier. Its detail is "the role may not make or write the kernel's tables in {label}: make them once with a role that may, and grant this role SELECT, INSERT, UPDATE and DELETE on these tables: {names}".
- No new error kind is added.

Reason: a caller of the store is kernel code that turns a failure into a `Result`. One exception that carries a classified error lets each of eight specs do that in one `except`.

### 10. A record that goes with a change is written in a transaction of the store's own, after the change or before it, and never inside it

"With the change" means: inside the same public call, before that call returns, in a transaction on the store. It never means the mount's transaction, on either engine, for any mount. There are two forms, and a spec that writes a record beside a change says which it uses.

```python
async def record_after(self, fn: Callable[[Transaction], Awaitable[object]]) -> ResultError | None
```

`record_after` is a `commit` with two differences. It never raises for a store failure: it returns a warning, which the caller adds to the change's result, as a held advisory rides a later write today (`engine.py:489-506`). And it runs in a task its caller's cancellation does not enter. That is one new function in `attempts.py`, `run_to_its_end`, which waits as `run_out_of_reach` does and does not mark the attempt.

**Record after.** The storage method runs and commits the change. Then `record_after(fn)` commits the record.

| The process dies, or the call is cancelled | What is left |
|---|---|
| before the change commits | nothing |
| after the change commits and before the record commits | the change, and no record |
| after the record commits | both |

A record exists only if its change landed. A landed change may lack its record. This form is for a record that can only be made from what the change returned, or whose absence errs toward a refusal or a second read. Two specs take it. Spec 3 stores the stamps a change leaves this way (its decision 8, "A read writes its stamps behind, and a change writes them with the change", step 7). Spec 5 stores its change rows this way (its decision 4, "A session writes its change rows after the change commits, by spec 0's record-after form, before the verb returns"), because the vid after a change is not known before it, and a claim left in doubt could not be put back. One `record_after` takes one `fn`, and that `fn` may write the rows of both specs, so a change through a session costs the store one transaction for its stamps and its change rows together.

**Claim before.** `commit(claim)` writes a row that says what is about to be done. Then the change runs. Then `record_after(completion)` marks the claim as done, or as not done when the change was refused.

| The process dies, or the call is cancelled | What is left |
|---|---|
| before the claim commits | nothing |
| after the claim commits and before the change commits | the claim, and no change |
| after the change commits and before the completion commits | the claim and the change, and no completion |
| after the completion commits | all three |

A change exists only if its claim was committed first. A claim that cannot be written raises, and the change is not attempted. A claim with no completion is in doubt: its change landed or it did not, and the store cannot say which. The spec that owns the claim settles it by reading the entry against what the claim recorded. This form is for a step that must not be carried out twice or by two callers. Spec 7 takes it: its claim is one conditional update committed before the saved step is dispatched, its finish is a second committed statement, and a claim with no finish is freed by a lease (its decisions 21, "Exactly one resume carries a job on, and the loser is refused with the job's state", and 23, "A claim is a lease of five minutes, and a job left running past it is carried on again under the same guard"). A completion need not go through `record_after`: a caller that must know whether its completion landed uses `commit` and handles the raise.

Rules for both forms:

- **A failed `record_after`.** The change stands. The call returns its own result with one more error, of severity `warning`, kind `vfs.unavailable`, not retryable, whose detail is "the change is committed, and the kernel's record of it was not written: {cause}". The state is the second row of the first table, or the third row of the second.
- **A cancelled caller.** A caller cancelled while the storage method runs is raised its cancellation by the storage's own rule, and the kernel does not learn whether the change landed. No record is written, so the state is one of the first two rows. A caller cancelled inside `record_after` waits for the attempt in flight, which runs to its commit. No further try is started. The caller is then raised the cancellation it was cancelled with, the same object, by the rule `run_out_of_reach` has.
- **The order is fixed.** A record is never written before its change without a completion to follow, and never inside the mount's transaction.

Reason for two transactions everywhere: on any engine the change may be on another mount, and a storage commits inside its own method. A promise of one transaction that held only for a Postgres root could not be tested on the other shapes, and specs would lean on it. Reason for `record_after` out of reach: the window between the two commits is then a crash's width and not a cancellation's.

### 11. A counter is a column that one statement adds to and returns

```python
async def next_number(self, transaction, counter: Column[int], *where: ColumnElement[bool], count: int = 1) -> int
```

It issues `UPDATE <table> SET <counter> = <counter> + :count WHERE <where> RETURNING <counter>`, inside the caller's `commit`, and returns the last number of the block. The block is the `count` numbers that end there. A column that starts at 0 hands out 1 first. When no row matches it raises `LookupError`, so the owner makes the row first, in the same `commit`, with an upsert that does nothing on a conflict.

- The counter is a column on the row that owns the sequence. A session's row holds the counter of its turn numbers, and spec 4's statement S3 is this statement (its decision 4, "`start_turn` stores the turn at once, takes its number from the session's counter, and returns the turn id"). No counter is shared by the whole store. A sequence that only one process at a time can advance needs no `next_number`: spec 8 keeps its journal's counters in the line record, which the holder of the job's claim alone writes (its decision 9).
- Two processes never get the same number. On SQLite one writer holds the file. On Postgres the second update waits for the first one's row lock and then reads the committed value, at READ COMMITTED, which decision 5 pins.
- The numbers have no gap when the number is used in the `commit` that took it, because a rollback returns the number with everything else.

Reason: the overview rules that an order is a counter and never a clock. One statement on the owner's row needs no sequence object and no lock of its own, and it queues only the callers of one session or one job.

### 12. A batch of rows is written in chunked statements through four helpers

```python
async def insert_rows(self, transaction, table: Table, rows: Sequence[Mapping[str, object]]) -> None
async def upsert_rows(self, transaction, table: Table, rows: Sequence[Mapping[str, object]], *,
                      key: Sequence[str], update: Sequence[str], newest: str | None = None) -> int
def key_chunks(self, keys: Sequence[K], *, width: int = 1) -> Iterator[Sequence[K]]
async def delete_expired(self, transaction, table: Table, *, key: Column[Any], expires: Column[datetime],
                         now: datetime, limit: int, where: ColumnElement[bool] | None = None) -> int
```

- `insert_rows` is the adapter's `bulk_insert` (`dialects.py:673-724`): `COPY` on Postgres, the driver's `executemany` on SQLite, paged under the live parameter budget.
- `upsert_rows` sorts the rows by `key`, cuts them by `rows_per_statement` under the same budget, and issues one `INSERT … ON CONFLICT (key) DO UPDATE SET …` for each chunk. An empty `update` makes it `DO NOTHING`. It returns how many rows it inserted or updated, so an insert that did nothing says so. With `newest`, the update carries `WHERE excluded.<newest> >= <table>.<newest>`, so an older row never replaces a newer one. Two rows with one key in one call raise `ValueError`, because Postgres refuses a statement that would update one row twice (`21000`) and SQLite does not: it counted 2 rows and stored the later one (`probes/output.md`, sections 9 and 10). The check is what keeps the two engines alike.
- `key_chunks` cuts a key list by the membership budget, for an `IN` list. `width` is the binds one key takes, 2 for a pair.
- `delete_expired` issues `DELETE FROM t WHERE key IN (SELECT key FROM t WHERE expires <= :now [AND where] ORDER BY expires LIMIT :limit)` and returns the rows removed. It is the statement the study measured for reclaim (`research.md:42`). Its text and its binds, three on SQLite and two on Postgres, do not change with the rows it removes.

These four, and the two that decision 25 adds, are the only shapes the store offers for many rows. Any other statement of a later spec binds a fixed number of parameters, or is cut by decision 25's `row_chunks`.

Reason: a 10,000-entry write through a session is a supported call, and it writes 10,000 records. Chunking owned in one place is what keeps eight specs under SQLite's 32,766 variables and SQLAlchemy's 32,700 parameters. Sorted keys make two processes lock rows in one order.

### 13. A record written behind goes to one buffer for each file system, which one task empties as soon as it is free

```python
@dataclass(frozen=True, slots=True)
class BehindKind:
    name: str
    write: Callable[[KernelStore, Transaction, Sequence[Mapping[str, object]]], Awaitable[None]]
    key: tuple[str, ...] | None = None

def register_behind(self, kind: BehindKind) -> None
def put_behind(self, kind: BehindKind, rows: Iterable[Mapping[str, object]], *, scope: Hashable | None = None) -> None
```

- **`put_behind` is a plain function.** It adds rows to the buffer, wakes the task and returns. It awaits nothing, sends nothing and never raises for a store failure. It is called on the loop's thread only.
- **A read verb's whole dealing with the store is `put_behind`.** So a read adds no synchronous statement, and it does not wait for one. The one exception is a read that a policy stops, which decision 22's third rule gives.
- **Kinds.** The kernel registers each kind once, when it is built. A second kind of one name raises `ValueError`, and so does a `put_behind` of a kind that was not registered.
- **Rows that share a key become one row.** When a kind has a `key`, a row put behind replaces a buffered row of that kind whose key fields are equal, in the earlier row's position. A kind's `key` is the conflict key of its statement, or coarser, so that no flush holds two rows of one conflict key. Spec 3's `STAMPS` is keyed by the session and the path and leaves the turn out, which is coarser than its statement's key (its decision 8).
- **The task.** The store has one background task. It starts at the first `put_behind`, on the running loop, with `context=contextvars.Context()`, and is named `vfs-kernel-store`. It does not copy its starter's context, so it carries no attempt's mark and no call's context variables.
- **A flush.** The task takes up to `FLUSH_ROWS`, which is 1,024, from the head of the buffer. It groups them by kind, in the order the kinds were registered, hands a keyed kind its rows sorted by key, and runs every kind's `write` in one `commit`. Each `write` uses decision 12's helpers, so each statement is under the parameter cap whatever the batch.
- **When it flushes.** It flushes while the buffer holds anything, and then waits for the next `put_behind`, `drain` or `close`. There is no row count to reach and no timer. Rows put in one turn of the loop ride one flush. While a flush is in flight the rows that arrive wait for the next, so batches grow with load.
- **Order.** Rows of one kind are written in the order they were put, keyed rows excepted, which are sorted. Kinds are written in the order they were registered, so a kind that needs another kind's row is registered after it. The store promises no order between a row written behind and a synchronous write. A kind that is written both ways makes its upsert monotone with `newest`, on a counter, or takes the other way decision 24 gives a kind that has no counter.
- **A loop that changes.** The task belongs to the loop of the first `put_behind`. A `put_behind` on another loop starts the task there, and the buffer goes with it. This is the case of `VirtualFileSystem.wrap` (`sync.py:138-148`).
- **A cancelled call.** The task is the store's and no caller's cancellation reaches it. A read that is cancelled before its storage answers puts nothing.
- **A process that dies.** It loses the rows in the buffer and the flush in flight: at most `BEHIND_CAPACITY` rows, and in the study at most 258.

Reason for flushing as soon as free: a session used in the next request, by another process, must find what this one saw "a moment after each read". A flush that waited for 256 rows would hold a quiet session's rows until `close`, and a timer would put a clock in every test. Reason for one buffer and one task: it is what the study measured.

### 14. The buffer is bounded, drops its oldest rows when full, and holds only records that may be dropped

`BEHIND_CAPACITY` is 16,384 rows. When a `put_behind` would pass it, the oldest rows are dropped until the buffer fits, and `KernelStore.dropped` counts them. One call that puts more than 16,384 rows keeps its last 16,384.

**Every record written behind may be dropped. A record that may not be dropped is never written behind.** It is written with `commit` or `record_after`, and decision 10 says what its failure leaves. So a kind is written behind only when losing a row errs toward a refusal or a second read: a stamp from a read (spec 3, decision 8), a session's use (spec 2, decision 17, "Every call through a handle reports one use, written behind, and a row is touched at most once in five minutes"), the trim of a session's stamps (spec 3, decision 15).

Reason for the oldest: after an outage the rows that land are the newest, which are the ones a session acts on next. Reason for a bound in rows: a row of a record is a few short columns, bounded by its column widths, so 16,384 rows is about 16 MB at ordinary widths, by estimate. The bound guards against rows piling up while the store cannot be written. It is not a limit on a call: the store's capacity is the flusher's, estimated at about 30,000 rows a second on a SQLite file of its own by `probe_flush.py`. In the mount's file it is what the file's writer leaves it, and the bound was reached when that writer was held for 37 seconds (decision 4). A byte budget, through `vfs.batching`, is the direction if a kind with wide rows appears.

### 15. A failed flush keeps its rows when a retry can clear the failure, and drops them when none can

Every log record of the store goes to the logger `vfs.kernel_store`.

- **A failure a retry can clear.** The store cannot be reached, its writer is held past the retry budget, a connection is lost, or the role lacks a privilege that a grant gives it (decision 9), in which case the one `WARNING` names the grant. The rows go back to the head of the buffer. The task waits for the next `put_behind`, `drain`, sweep chunk or `close` and tries again. In a process that puts nothing more, the rows of a failed flush wait until `close`, and another process does not find them until then. The first failed flush after a good one logs one `WARNING`: "the kernel store at {label} could not be written ({cause}); records written behind are held in memory, and the oldest are dropped past {capacity}". The first good flush after a failure logs one `INFO`: "the kernel store at {label} is written again after {n} failed flushes; {m} records were dropped".
- **A failure no retry can clear.** An integrity error, a statement defect, a value over the engine's cap, a store of another format. The batch is tried once more in one transaction, a kind at a time, each kind under a savepoint. The kinds that fail again are dropped and counted, and the others are written. If the second try itself meets a failure a retry can clear, every row goes back to the buffer, as above. One `ERROR` is logged for each kind dropped, "a flush of {n} {kind} records to the kernel store at {label} can never land ({cause}); they are dropped". A store of another format drops the whole batch with no second try, and has decision 8's one `WARNING`.

Reason: a short outage should cost no row, as it cost none in the study (`research.md:101`). A batch that can never land would otherwise block the head of the buffer until every row behind it was dropped. A flush carries up to 1,024 rows of every kind and every session, so without the second try one row that can never land would drop the rows of kinds that have nothing wrong with them.

### 16. `drain` waits for the records of one scope

```python
async def drain(self, scope: Hashable | None = None) -> None
```

It returns when every row put behind before the call, under that scope, has been written or dropped. With no scope it waits for every row. When nothing of the scope is waiting it returns at once and sends nothing. When the flush that carries one of those rows fails, it raises `KernelStoreUnavailable`. A caller that is cancelled while it waits loses no row: the flush goes on.

A change that must read what its own session wrote behind calls `drain` with the session's scope first, or reads those rows where they wait with decision 24's `waiting_behind`. Either is allowed to a change. A read does neither.

Reason: a session reads a file and edits it in the next call, in one process. The stamp may still be in the buffer. Waiting for one scope's rows costs no statement of its own, since the flush was going to run, and it does not wait behind another session's backlog.

### 17. Expired records are removed by the public `sweep` in bounded chunks, and a record past its expiry reads as absent before it is swept

Ruled on 2026-11-23. This decision's first form was "Expired records are removed by a counted sweep in bounded chunks", in which each process swept by itself after a count of its own writes. The ruling keeps one way and not two: nothing is removed until `sweep` is called, which is the rule the trash already has.

```python
Sweeper = Callable[[KernelStore, Transaction, datetime, int], Awaitable[int]]

def register_sweeper(self, name: str, sweep: Sweeper) -> None
async def sweep(self) -> int
```

- **Expiry does not depend on the sweep.** Every read of a table that expires filters on its expiry against `store.now()`. The sweep only gives the space back.
- **A sweeper.** A spec that owns a table with an expiry registers one, in the order parents and dependents need. It is handed the store, a transaction, the pass's one reading of the clock, and a limit. One call removes at most `limit` rows in all, in the `commit` it is given, and returns how many. It removes a parent only when its dependents are gone. Its statements are `delete_expired` and decision 25's `delete_where`, and decision 26 gives the common case ready-made.
- **A pass.** For each sweeper in turn, the store calls it in a `commit` of its own with `SWEEP_CHUNK`, which is 5,000, until a call removes no row. There is no cap on the chunks of a pass: a pass ends when one of its calls removes no row. Beside another pass that can be before the table is clean, and the other pass goes on. Each chunk is a transaction of its own, so a lock is held for a commit's length, and a pass that is cancelled or fails has removed whole chunks and nothing else. On Postgres a write beside a pass did not slow. On SQLite a pass's chunks follow each other and a waiting writer polls for the file, so a write gets through between two chunks only now and then: beside a pass of 600,000 rows a one-file writer landed 17 writes in 9 seconds and none was refused (decision 4, the price). A long pass on SQLite is run when the root is quiet. The store's own flush is not left to that chance: between two chunks a pass wakes the task when rows wait, as `drain` does, waits for that one flush and no other, and goes on whether it landed or failed. So a process's rows written behind are held for a chunk and not for a pass. A pass holds no transaction between two chunks, so the flush waits for nothing the pass holds. A sweeper that works in smaller batches than its limit is called again while it still finds work. A pass that fails logs one `WARNING` and ends, and the next pass starts over.
- **When: only when the public `sweep` is called.** `AsyncVirtualFileSystem.sweep()` on the trash view of the root mount, which is its default path, runs the storage's retention as it does today and then awaits one pass of the store. Nothing else starts a pass: no count of writes, no timer, no `close`. The store's background task writes and never removes.
- **For whom.** The pass runs only when the storage's retention succeeded, so only for a caller allowed to sweep the root's trash. A `sweep` of any other path, or of another mount's trash, runs none.
- **A root that cannot be swept.** Where the root mount masks `sweep` with `deny_ops`, where its storage declares none, or where the caller may not write the root's trash, no pass runs and no other call removes an expired record. Expired records read as absent and their rows stay, as that root's trash stays too. A deployment that masks `sweep` on the file system its agents use calls it from a file system of its own over the same database, with no mask.
- **What the caller gets.** The result is the storage's own. A pass that fails adds one error of severity `warning` to it, as a failed `record_after` does.
- **A file system that keeps no record.** A pass on a store whose meta table is missing removes nothing and makes no table.
- **By which process.** Any process that calls `sweep`. No process leads. Two passes at once remove each row once: on SQLite they take turns on the file's one writer, and on Postgres the second waits a chunk for the first one's row locks and then finds the rows gone. A pass whose call finds its rows already taken counts none and ends, so one of two passes can end early. Of two passes over 40,000 rows on Postgres, one ended after 10,000 and the other removed the rest (`probes/output.md`, section 10).
- **In a test.** `store.sweep()` is the pass itself, with no trash retention before it, and returns the rows removed.
- It lands with landing 4.
- **A record with no expiry is never removed.** An expiry column may be null, which means never: `delete_expired` compares `expires <= :now`, which a null does not meet, and a read that filters on an expiry treats a null as live. A session has no expiry unless the developer sets `session_lifetime` (spec 2, decision 18, as ruled on 2026-11-23), so by default the sweep removes expired jobs and no session.

Reason for the public `sweep` alone: a storage does no work in the background, so nothing is destroyed until `sweep` is called (`src/vfs/base.py:1143`), and a deployment schedules that call already, or its trash is never emptied. One call then gives back all the space there is to give: the trash, the expired jobs, and the sessions where a lifetime is set. It reaches a process of any length, where a count of writes never came due in a short one. And nothing is removed that a developer did not ask to have removed. Reason against keeping the count beside it: two ways to remove the same rows are two sets of rules and tests for no further guarantee. Reason for 5,000: it is the chunk the study measured, 21 ms a chunk at the median on SQLite and 67 ms on Postgres (`research.md:118`).

### 18. Every time comes from one clock that a test replaces

`KernelStore(place, *, clock=…)` takes a function that returns an aware UTC `datetime`, and by default the system's. `store.now()` calls it, and `store.clock` can be assigned. Every time a record stores and every expiry it is compared with is a bound parameter from `store.now()`. No statement of the store names the engine's own clock. `tests/support/kernel_store.py` gives a clock that a test steps forward.

Two processes compare an expiry one of them wrote with the other's clock. Their clocks differ by seconds, and the lifetimes are a day for a job and whatever a developer sets for a session. A time is stored for display and for expiry only, as the overview rules.

Reason: a test of expiry that waited for time to pass would read a clock, and a statement that read the engine's clock could not be stepped.

### 19. `close` flushes the buffer, ends the task and disposes the store's engine, inside the kernel's own close

`AsyncVirtualFileSystem.close()` closes the store as one more target of the gather it already runs (`base.py:569-573`), within the same `close_timeout`, beside the storages and not after them.

1. The mount table is emptied first, as today, so a later verb is refused.
2. The store stops taking rows and starts no further try. A `put_behind` after this is dropped and raises nothing. A `query`, `commit` or `record_after` after this raises or returns `vfs.unavailable.backend`. One that began before this ends the attempt it has in hand and starts no other: if that attempt fails, a `query` or a `commit` raises and a `record_after` returns its warning.
3. The task flushes until the buffer is empty, one try for each flush and not four. A flush that fails ends the flushing, the rows left are dropped and counted, and one `WARNING` says how many. A failed flush is not raised from `close`, since every such row may be dropped.
4. The task ends. It is awaited, for as long as the budget below allows, and never interrupted, so no interrupt is left pending on a connection.
5. The store waits for its transactions in flight. It counts every `query`, `commit` and `record_after` that began before step 2, and waits for that count to reach zero.
6. The engine core is disposed, in a `finally`, as a storage's is (`engine.py:541-547`). An error here is raised with the storages' errors, alone or in the group.

**The store keeps to a budget, and a close that is cut short is safe. It does not lean on a second `close()` after a timeout.** Today's kernel keeps a target only when its own `close` is cancelled. A target whose close outlives `close_timeout` is collected as an error and is not kept (`base.py:569-574`), so a second `close()` never enters it again. The store is one more target and gets the same. It cannot bound every wait: a flush that lands is followed by another, a statement in hand has no bound the store sets (decision 25), and on Postgres a checkout waits the pool's 30 seconds unless `pool_timeout` is set. So it does two things. It stops by a budget of its own, and it makes the cut-short path leave nothing open.

The budget:

- `KernelStore.close(*, within=None)` takes the seconds it has, and the kernel passes its `close_timeout`, 10 by default. The store's budget is `within` less one second, which is kept for the dispose, and never less than half of `within`. With no `within` there is no budget.
- The budget is a `Deadline` of `vfs.deadline`: `Deadline.after(budget)`, made once when `close` is entered and handed to the steps as an argument, or `Deadline.never()` with no `within`. What is left is read from it with `remaining()`. The store reads no clock of its own, so the rule the gate holds stands: one module reads the monotonic clock for a deadline (`src/vfs/deadline.py:1-19`, `tests/lint/test_code_shape.py:536-544`), and one fake clock patched there drives this budget with every other. It is not the clock of decision 18, since no record holds it.
- Nothing is left when `remaining()` is zero. A test passes `within=0`, for which it is zero at the first reading, and steps no clock.
- The task is already running when `close` is entered, so it is told the budget with the signal that tells it to close. It keeps the `Deadline` in a local for that close's flushes. No attribute of the store holds a deadline, which the module's rule forbids on a long-lived object (`src/vfs/deadline.py:14-15`), and a second `close()` after a cancelled one makes a `Deadline` of its own and never reads the first one's as spent.
- Before each flush at close, the task reads what is left of the budget. With nothing left it starts no flush. Otherwise the flush makes its one try, and on SQLite that try waits for the file's writer at most the smaller of `busy_timeout`, 5 seconds, and half of what is left. It sets that on its own connection before its `BEGIN IMMEDIATE`.
- Step 5's wait ends when the count reaches zero or when the budget is spent.
- Steps 3 and 5 run at the same time. With the defaults, a close behind a writer held throughout ends in about 5 seconds, where four tries would have taken about 21 against a timeout of 10.
- When the budget is spent with rows left or with work in hand, the store takes the cut-short path below by itself, and its `close` returns with no error. The rows left are dropped and counted in step 3's one `WARNING`.

The cut-short path is taken when the budget is spent, when the kernel's timeout fires first, and when the close is cancelled. The last two reach the store as the same thing, a cancellation of its `close`.

1. The task starts no further flush. It ends after the flush it has in hand, and the rows left are dropped and counted. This is settled before the dispose, so no flush opens a connection on the engine's new pool.
2. The engine is disposed, in a `finally`.
3. A flush or a transaction still running closes its own connection when it ends and returns it to no pool, as an analysis pass that a close left running does (`engine.py:536-539`). The side files go when that connection closes.

A cancelled close keeps the store, as it keeps a storage (`base.py:559-565`), and a second `close()` waits for work still in hand and disposes again. A close that the kernel timed out is not kept, and needs no second call.

Other cases:

- A store that was never used has no engine and no task, and its close does nothing.
- A durable store keeps its records. An in-memory store loses them, with the jobs that were waiting.
- On SQLite the directory then holds the mount's file and no side file. Two engines hold connections on that file, the mount's and the store's, and SQLite removes the `-wal` and `-shm` files when the last connection of either closes, so the close of whichever engine ends second is the one that leaves the directory clean. A connection that is still out when its engine is disposed is not closed by the dispose, and the side files stay (`probes/output.md`, section 6), which is why step 5 comes before step 6.

Reason: the store has an engine and a task, and they follow the rule every storage follows. Flushing at close is what makes a short script's last reads reach the next process. Reason for one try at close: with one file, a process that closes while another process's batch holds the writer is an ordinary case, and four tries there outlast the default timeout, leave the engine undisposed and leave the side files beside the database, which the landed close specs promise cannot happen. Reason for a budget of the store's own: a close beside a busy writer is ordinary on one SQLite file, and without it that close would end as the kernel's `TimeoutError`, raised for rows that may be dropped. Reason against keeping a timed-out target for a second `close()`: it would change what today's kernel does for every storage, and a store whose cut-short path leaves nothing open needs no second call.

### 20. Many processes share one store, and the synchronous face adds nothing of its own

**Two calls in one process.** Each `commit` is a transaction of its own on a connection of its own. On a SQLite file the second waits for the file's one writer, which a mount's write may also hold, in memory it waits for its turn, and on Postgres it waits only for a row the first one wrote. Rows that two calls put behind sit in the buffer in the order they arrived.

**Many processes.**

- First touch is serialized by decision 8, and a rival's meta row is harmless.
- A counter, an upsert and a sweep are correct under rivals by decisions 11, 12 and 17. A deadlock on Postgres between two flushes, or between a flush or a `commit` and a sweep chunk, is `40P01` and is retried by the core. Sorted keys make two upserts lock rows in one order, and none deadlocked when they did. A sweep's delete locks rows in the order its scan finds them, which sorting keys does not govern.
- On SQLite every process shares the file's one writer, and the store shares it with the mount. A flush holds it for one batch, a `commit` for its statements, a sweep for one chunk. A process that finds it held, by the store or by a mount's write, waits as any SQLite writer does.
- A row in one process's buffer is not seen by another until it is flushed, which is a moment after it was put.
- A process on another build is refused the store by decision 8, and still serves files.

**The synchronous face.** `VirtualFileSystem` forwards to the kernel on its loop thread, so the store's task lives on that loop. `close()` cancels the calls in flight, waits for them, and then closes the kernel, which closes the store (`sync.py:658-664`). A call cancelled inside `record_after` ends by decision 10 before that wait is over. The store's interface is private and `async`, so it has no synchronous twin, and the parity test covers the public methods that later specs add.

Reason: the reference deployment is many callers on one database, and the facade is a thin wrapper by design.

### 21. The store judges no rights, and no session, policy or tool can reach it

Every call on the store is the kernel's own. The store is handed no authority and asks no rights question. It treats the system authority, a named caller and the anonymous caller alike, because it does not see them. Which caller may see a record is decided by the spec that owns the record, by the owner key the overview defines.

The store is `fs._kernel_store`, a private attribute of the kernel. No public method returns it. A session, a policy and a tool hold nothing that reaches it, as a session cannot reach a `Mount` (`documentation/maintainers/mounts.md`). A test keeps it so.

Reason: a row about calls can name paths a caller may not see. Keeping the store behind the kernel means every way to it is a method that some spec wrote a rights rule for.

### 22. The interface is private, and this is all of it

```python
class KernelStore:
    def __init__(self, place: RecordPlace, *, clock: Callable[[], datetime] = …,
                 retry_attempts: int = 4, retry_base_delay: float = 0.05,
                 behind_capacity: int = BEHIND_CAPACITY) -> None

    # facts, with no I/O
    tables: KernelTables
    durable: bool
    dropped: int
    engine: AsyncEngine                      # for a listener alone
    parameter_budget: int
    membership_budget: int
    clock: Callable[[], datetime]
    def now(self) -> datetime

    # transactions: decisions 9 and 10
    async def query(self, fn) -> T
    async def commit(self, fn) -> T
    async def record_after(self, fn) -> ResultError | None

    # statements, called inside fn: decisions 11, 12 and 25
    async def next_number(self, transaction, counter, *where, count=1) -> int
    async def insert_rows(self, transaction, table, rows) -> None
    async def upsert_rows(self, transaction, table, rows, *, key, update, newest=None) -> int
    def key_chunks(self, keys, *, width=1) -> Iterator[Sequence[K]]
    def row_chunks(self, rows, *, width=None) -> Iterator[Sequence[Mapping[str, object]]]
    async def delete_where(self, transaction, table, *, key, where, limit, order_by=None) -> int
    async def delete_expired(self, transaction, table, *, key, expires, now, limit, where=None) -> int

    # written behind: decisions 13 to 16 and 24
    def register_behind(self, kind: BehindKind) -> None
    def put_behind(self, kind, rows, *, scope=None) -> None
    def waiting_behind(self, kind, *, scope=None, keys=None) -> list[Mapping[str, object]]
    def discard_behind(self, kind, *, scope=None, keys=None) -> int
    async def drain(self, scope=None) -> None

    # the sweep: decision 17
    def register_sweeper(self, name: str, sweep: Sweeper) -> None
    async def sweep(self) -> int

    # life: decisions 8 and 19
    async def ensure_ready(self) -> None     # raises KernelStoreUnavailable
    async def close(self, *, within: float | None = None) -> None
```

`vfs.kernel_store` exports `KernelStore`, `KernelStoreUnavailable`, `BehindKind`, `Sweeper`, `Transaction`, decision 26's `expiry_sweeper` and the constants. The members that decisions 24 to 26 add are in the listing above. It is documented on a Maintainers page and carries no compatibility promise.

A spec that keeps a record follows eight rules.

1. Its table is added to `build_kernel_tables`, its name begins with one of `KERNEL_TABLE_PREFIXES`, and the landing adds one to `KERNEL_FORMAT_VERSION`.
2. Its statements are in a module of `vfs.kernel_store`, never in `vfs.base` or `vfs.session`.
3. A read verb calls `put_behind` and nothing else of the store, unless a policy stops it: a read that is interrupted has read nothing, and its job is stored with `commit` (spec 7, decision 6, "The job is committed before the interrupted result is returned").
4. Every stored time and every expiry compared comes from `store.now()`, and every read of a table that expires filters on the expiry.
5. Many rows are written with decision 12's helpers, or by a statement of the spec's own that decision 25 admits.
6. A record written beside a change names its form, record after or claim before.
7. A kind's `key` is its statement's conflict key or coarser. A kind that is also written synchronously passes `newest`, or, where its rows have no counter, the spec reads `waiting_behind` before its synchronous write and calls `discard_behind` for the keys it writes, and states what a row of the flush in flight can then do.
8. A table that expires has a sweeper.

A ninth point is not a rule of the store and is recorded here because every table meets it: a table that names a session names it by `session_key` (spec 2, decision 13), and a turn by its number (spec 4, decision 2, "`vfs_session_turns` holds one row per turn").

Reason: eight specs build on this interface at the same time. A list each can copy is what keeps eight designs of storage from appearing.

### 23. The work is four landings

1. **The engine core.** `EngineCore` is split from `EngineHost`. No behaviour changes.
2. **The place.** `RecordPlace`, `SupportsRecordPlace` and `DatabaseStorage.record_place`.
3. **The store.** The tables, first touch, `query`, `commit`, `record_after`, the counter, the helpers, the clock, the kernel's construction of the store and its close.
4. **The writer and the sweep.** `put_behind`, the task, `drain` and the sweep.

Of the members decisions 24 to 26 add, `row_chunks`, `key_chunks` with a width, `delete_where` and the row count of `upsert_rows` land with the third, and `waiting_behind`, `discard_behind` and `expiry_sweeper` with the fourth.

The Maintainers page lands with the third and is completed by the fourth. Each docstring named under "What the docs must say" lands with the landing that makes it true.

Reason: each leaves the tree green and is of use alone. The first is a refactor that the second and third need. The third is enough for a spec that writes only synchronously, and the fourth for one that writes behind.

### 24. A caller can read and withdraw what waits in the buffer, and a deferred task is a kind

```python
def waiting_behind(self, kind: BehindKind, *, scope: Hashable | None = None,
                   keys: Iterable[tuple[object, ...]] | None = None) -> list[Mapping[str, object]]
def discard_behind(self, kind: BehindKind, *, scope: Hashable | None = None,
                   keys: Iterable[tuple[object, ...]] | None = None) -> int
```

Both are plain functions, as `put_behind` is. They send nothing, await nothing, and are called on the loop's thread. Each takes a scope, a list of keys, or both, and acts on the rows of the kind that carry the scope and whose key is listed. With neither it raises `ValueError`. A key is the tuple of the kind's `key` fields.

- **`waiting_behind`** returns the rows that were put behind and are not yet stored or dropped: those in the buffer, and those of the flush in flight. A row leaves when its flush commits or when it is dropped. So a caller that finds no waiting row for a key reads the store, and the row is in one or the other unless it was dropped.
- **`discard_behind`** takes rows out of the buffer and returns how many. A row of the flush in flight is not withdrawn, and is stored.
- **A kind written both ways that has no counter.** `newest` needs a column that orders two rows of one key. Where none exists, the spec reads `waiting_behind` before its synchronous write and calls `discard_behind` for the keys it writes. Only a row of the flush in flight can then land after the synchronous write, and the spec states what that row does. Spec 3's stamps are the case: no counter orders two stamps of one path, and the one late row costs one refusal that one read clears (its decisions 5 and 8).
- **The cost** is the rows of that scope, or the keys given. The store keeps, for each scope, the keys it holds in the buffer, which it needs for `drain` already.
- **No callback is offered.** The store does not tell a submitter when a row is stored or dropped. A second table kept in step by callbacks is a copy that can drift from the buffer, and the buffer can be read.
- **A deferred task is a kind.** A task that must run behind, after rows, is a kind whose row names the task and whose `write` runs its statements. Its `key` is what the task is for, so many requests for one thing become one run. It is registered after the kind whose rows it follows, so it runs after them in the same flush. It may be dropped, as any row may.
- **One flush is one transaction, and its `info` lasts that long.** Every `write` of a flush receives the same `Transaction`. SQLAlchemy gives it a dictionary, `transaction.info`, which begins empty and ends with the transaction. A function that several kinds call in one flush keeps what it found there. A retry starts a new transaction with an empty one.
- **The order of the kinds** is the order the kernel registers them in when it is built. With the nine specs built it is: spec 2's `SESSION_USE` (its decision 17, which registers it before any kind of another spec), then spec 3's `STAMPS` (its decision 8), then spec 3's `STAMP_TRIMS` (its decision 15, "A session's stamps are bounded at 16 MiB, and the earliest turns go first"). No kind leans on another's rows: each `write` calls spec 2's `resolve` itself, the use with `create=False` and the stamps with `create=True` (spec 2, decision 14).

Who uses them: spec 3's change reads a stamp that still waits without a statement, and takes its paths out of the waiting rows before it records (its decision 8, steps 2 and 7). Spec 3's decision 21 has a removed session's waiting stamps withdrawn with `discard_behind(STAMPS, scope=ref.scope)`. Spec 2's removal awaits `drain(ref.scope)` before it frees the name (its decision 22, "Removal frees the id in one commit and reclaims the rest in bounded chunks"), and spec 4's rewind and fork call `drain` first (its decisions 12 and 17). A drain and a discard both leave no row of this process to land after the removal.

Reason: three specs asked for three things under five names: settle, discard, withdraw, a pending table, an awaited flush. Waiting is `drain`, which the first draft had. Reading and withdrawing are the other two, and each is a lookup in a dictionary the writer already keeps.

### 25. A statement of a spec's own is within the interface when its binds are fixed or its rows are cut by the store's budgets

```python
def row_chunks(self, rows: Sequence[Mapping[str, object]], *, width: int | None = None
               ) -> Iterator[Sequence[Mapping[str, object]]]
async def delete_where(self, transaction, table: Table, *, key: Column[Any] | Sequence[Column[Any]],
                       where: ColumnElement[bool], limit: int, order_by: ColumnElement[Any] | None = None) -> int
```

A spec is not held to decision 12's four helpers. Three kinds of statement of its own are admitted.

- **A multi-row statement of its own shape, cut by `row_chunks`.** `row_chunks` slices rows by `rows_per_statement` under the live parameter budget, as `upsert_rows` does. `width` is the binds one row takes when the statement binds more than the row's own fields. Spec 3's store statement is one (its decision 6, "A stamp is stored by one statement shape, and a row whose session or turn is gone stores nothing"), and so is the insert of spec 2's `resolve`, whose read of pairs is cut by `key_chunks(pairs, width=2)` (its decision 14, "The row is first written by the first record that needs it, through one function, `resolve`").
- **A bounded delete, `delete_where`.** It issues `DELETE FROM t WHERE key IN (SELECT key FROM t WHERE <where> [ORDER BY …] LIMIT :limit)` and returns the rows removed. `key` is one column or several, and several are compared as a row value. `delete_expired` is this statement with the expiry as its `where` and its order. It serves the reclaim of a removed session's rows, 5,000 to a transaction (spec 2, decision 22; spec 5, decision 16, "A rewind of the memory alone removes no change row, and a fork copies none"), and the third step of spec 3's trim (its decision 15).
- **A statement that binds a fixed number of parameters, whatever rows it touches.** An `INSERT … SELECT`, as the fork's copy of turns and of stamps is (spec 4, decision 17, "A fork copies the turns below the fork point, their stamps and their shell state, in statements with a fixed number of binds"). A ranged `DELETE`, as the rewind's removal of turns and of stamps is (spec 4, decision 12, "`rewind(before=turn)` removes that turn and every later one, with their stamps, and cancels their waiting jobs, in one transaction"). A conditional `UPDATE` whose row count the caller reads, as a job's change of state and `cancel_session_jobs` are (spec 7, decision 5, "A job is in one of four states, and every change of state is one conditional update on its revision", and decision 35).

Two rules go with them.

- **Several specs' functions run in one `commit`.** `fn` hands its `transaction` to each. The rewind's steps are several specs' statements in one transaction (spec 4, decision 12), and its stamp rows are removed and a fork's copied by spec 3's functions, which take the caller's `Transaction` (spec 3, decision 21). A line's stop writes spec 7's job row and spec 8's pages together (spec 8, decision 9, "`vfs_job_replies` holds a journal as pages of at most 1 MiB, appended at each stop"). A function that takes "the store, or a transaction of it" takes the `Transaction`.
- **The store bounds a statement's binds and never the rows it touches.** A statement of fixed binds holds the SQLite store's one writer for its own length, and on Postgres holds its row locks until the commit. What bounds its rows is a bound of the spec that owns it, such as the 16 MiB of stamps one session keeps, and that spec states the hold under its own Cost. Where its rows have no bound, that spec says so and names the direction. A sweeper is the one exception: it removes at most `limit` rows in a call, by decision 17, because nobody asked for it and nobody is waiting for it.

Run on 2026-11-22, `probe_round_two.py`, on SQLite and compiled for Postgres: a bounded delete by a three-column key removed 5 of 8 rows at a limit of 5; an insert that does nothing on a conflict reported 8 rows written, then 1 of 4; a transaction's `info` kept a value to its end, and the next transaction's was empty.

Reason: a rewind and a fork move a session's rows without bringing one into Python, which no helper that takes rows can do. The parameter caps bound a statement's text, and a statement whose text does not grow meets them at any size.

### 26. A table that expires with its dependents is swept by one ready-made sweeper

```python
def expiry_sweeper(table: Table, *, key: Column[Any], expires: Column[datetime],
                   dependents: Sequence[Column[Any]] = ()) -> Sweeper
```

It is a function of `vfs.kernel_store` that returns a `Sweeper` for `register_sweeper`. Each of `dependents` is a column of another table that holds the parent's key. That column's table is the dependent, and its primary key is the key its rows are deleted by.

One call, with `limit` rows to spend:

1. For each dependent in order, a `delete_where` of its rows whose column names a parent that has expired, up to what is left of the limit.
2. Then a `delete_where` of the parents that have expired and have no dependent row left, oldest first, up to what is left.

It returns the rows it removed in all. A parent is never removed before its dependents, and every statement binds the same few values at any size. A spec that lands later and keeps rows under the same parent adds its column to `dependents`.

Who uses it: spec 7 sweeps `vfs_jobs` with `vfs_job_pages.job_id` as its dependent (its decision 36, "A waiting job lapses `job_lifetime` after it stopped, 24 hours by default, and the sweep removes it"). Spec 8 removes a line's pages by a sweeper of its own, one bounded statement registered before spec 7's, which also takes the pages of a job whose row is gone (its decision 9). Spec 7's decision 36 also names `vfs_job_replies.job_id` as a dependent. Both may stand: the pages are gone before the row either way, and the second to look finds nothing. Spec 2's sweep is not this shape. It is one sweeper of its own, `sessions` (its decision 22).

A dependent row whose parent's row is already gone is not this sweeper's: it looks for expired parents. That case is spec 8's own statement.

Reason: two specs asked for a sweep arm that takes a table, its expiry column and a dependent table. Written once, the order of dependents before parents cannot be got wrong twice.

### 27. Each need the other eight specs state on the store is met by a named member, or is answered here

Read from each spec's "Builds on" at `59946f0d`, and checked against each spec's text at `7c383f32`. Specs 1 and 6 state none.

| Spec, and what it asks | Where it is met |
|---|---|
| 2: a store for every root storage, with `vfs_sessions` made in it | Decisions 2 and 6. The table is added to `build_kernel_tables` (decision 8). |
| 2: a synchronous path, a writer transaction on SQLite, READ COMMITTED on Postgres, one exception, the two budgets | `commit` and `KernelStoreUnavailable` (decision 9), decision 5, `parameter_budget`, `membership_budget`, `row_chunks`, `key_chunks`. |
| 2: a writer that keeps one use for each session | A kind whose `key` is the session's owner key and id (decision 13). |
| 2: the writer calls `resolve` at each flush, once for each session, before any other spec's rows | Not the writer, which knows no session. Each kind's `write` calls `resolve` on the flush's one transaction before it writes, which spec 2's decision 14 now lists caller by caller. `transaction.info` is there for a function that wants to read once a flush (decision 24); spec 2 does not use it. |
| 2: `settle` and `discard` for one session | `drain(scope)` (decision 16) and `discard_behind(kind, scope=…)` (decision 24). The scope is spec 2's `ref.scope`. |
| 2: a sweep that calls its two passes and can stop between chunks | One sweeper, `sessions`, of decision 17's shape (spec 2, decision 22). The task flushes between two calls. |
| 2 and 4: plain reads that do not wait on the store's writer, and a way to count statements | WAL and `query` (decisions 4 and 9); a listener on `store.engine` (decision 22). |
| 3: a submit that issues no statement and does not wait | `put_behind` (decision 13). |
| 3: a waiting row replaced by a later one of its key, and withdrawn by its key | A keyed kind (decision 13), and `discard_behind(kind, keys=…)` (decision 24). |
| 3: a kind written both ways with no counter to order its rows | Decision 24, and rule 7 of decision 22, in the words spec 3 asked for. |
| 7: a read that a policy stops stores its job before it returns | Rule 3 of decision 22, in the words spec 7 asked for. |
| 3: the writer tells the submitter when a row is stored or dropped | Not offered. `waiting_behind` gives the rows not yet stored or dropped (decision 24), and spec 3's decision 8 now reads the buffer and keeps no table of its own. |
| 3: a flush at a declared count of rows and after a declared delay of a second or less | Neither exists. The task flushes as soon as it is free (decision 13), so the window is one flush, which is shorter than what was asked. |
| 3: a drain on both faces, and a `close` that drains | `drain` (decision 16) and decision 19. The store's `drain` is private and `async`. No public call flushes the writer, by the last round's ruling 4, and `close` flushes it. |
| 3: a synchronous path with the waits and retries a change has | `commit` and `record_after` (decisions 9 and 10). |
| 3: a deferred task run by the writer in order with its rows | A kind (decision 24). |
| 3: rows chunked by the live parameter budget | `row_chunks` (decision 25). |
| 3: a statement of the store attributed to the call that issued it | A synchronous statement runs in its caller's context, and the task runs in a context of its own (decision 13), so a context variable and a listener on `store.engine` tell them apart, as the study did. |
| 4: a transaction that runs Core statements at READ COMMITTED on Postgres, and `vfs_session_turns` made with the other tables | `commit` (decisions 5 and 9), decision 8. |
| 4: an awaited flush of what this process has queued | `drain()` with no scope, or with the session's (decision 16). |
| 3 and 4: rows removed and copied in bulk on a rewind and a fork | Statements of fixed binds (decision 25). |
| 5: `record_after`, `query`, `commit`, `insert_rows`, and a record written after its change | As decision 22 lists them. Decision 10 names spec 5's choice of the record-after form. |
| 7: several statements in one committed transaction; an update that reports its row count | `commit` (decision 9) and decision 25. |
| 7: an insert that does nothing when a unique index refuses it, and reports that | `upsert_rows(…, update=())`, which returns the rows written (decision 12). |
| 7: a sweep arm for a table, its expiry column and a dependent table | `expiry_sweeper` (decision 26). |
| 7: one clock function that every expiry reads and a test replaces | `store.now()` (decision 18). |
| 8: one transaction that holds a row of `vfs_jobs` and rows of `vfs_job_replies` | One `commit` whose `fn` hands its transaction to spec 7's function (decision 25). |
| 8: a sweep that calls its orphan statement | A sweeper of spec 8's own, registered with `register_sweeper`, whose one statement carries the call's `limit` (spec 8, decision 9; decisions 17 and 26 here). |
| 2, 3, 4, 7, 8: the same on a root storage in memory | Decision 6. |

Reason: each of the eight was written without sight of this spec, and each named what it needed in its own words. One table shows that no need was left to be met by an invention at build time.

### 28. Where this spec leaves Plan 9 and Unix it says so, with the constraint that moved it

Article 3 of the constitution has VFS follow a convention of Plan 9 or Unix wherever one exists, and requires a deviation to be a numbered decision that names the principle, the deviation, the motivating constraint and the expected expiry. This is that decision. The section "Prior art, and where this spec departs" lists each point where a convention exists, what this spec does, and for each departure the four things the Article asks for. The conventions are those of a file system keeping its own bookkeeping: where it lives, when the record of a read is written, who removes what has expired, how a second writer waits, and what `close` owes.

Reason: a person who knows `noatime`, a journal inode, `cron` and `fsync` should be able to predict what the kernel's records do, and where they cannot, the place to learn why is the spec that decided it.

## Cost

Costed against the reference deployment in the working agreement. A store transaction is counted as the study counted: cursor statements, with SQLite's explicit `BEGIN` among them and no `COMMIT`.

**Per verb call, about 150,000 a day.** A read through a session adds no synchronous statement and awaits nothing of the store. The one read that does is a read a policy stops, which stores its job in one `commit` and has read nothing (spec 7, decision 6); it is costed there. Its rows ride a flush: one transaction with one statement for each kind present. At the peak of 20 calls a second, three in four of them reads, that is at most 15 flushes a second, and fewer as load makes batches. Measured in the mount's own SQLite file with eight readers and one writer (`probes/output.md`, section 1), on a laptop whose `synchronous = FULL` does not force the disk: the store wrote 17 batches a second, a store commit waited 4.5 ms at the median to begin and 0.56 seconds at most, and a read's median was 21.9 ms against 21.4 with no store. On Postgres a read's median was 11.6 ms against 9.5. Those are sizes from one machine and not a test. A call with no session and no job touches the store not at all.

**Per file write, about 1,050,000 a day.** Only a write that carries a record pays. The nightly million and the day's machine writes carry none. A write through a session, about a quarter of the verb calls and so about 37,500 a day, adds one store transaction when it records after and two when it claims before, which is the study's "an effect adds exactly two". That is 5 to 10 store transactions a second at the peak. The study measured the time of two such transactions on Postgres under 32 writing sessions: a one-file write's median moved from 188 ms to 338 ms (`research.md:77`). Measured again on 2026-11-23 with one record transaction after each write, under 32 writing sessions on Postgres: a write's median moved from 192 ms to between 214 and 217 ms, on the mount's pool, on a pool of 15 and on a pool of 32 (`probes/output.md`, section 13). On SQLite under 32 writing sessions no write was refused and no record failed. A `drain` adds no statement of its own.

**Per index visit, about 11,000,000 a day.** Nothing. The index reads and writes no kernel table.

**Per batch, 100 a night.** A batch with no session adds nothing. A 10,000-entry write through a session is one store transaction of `ceil(10,000 / floor(32,700 / columns))` statements: 2 for a row of 5 columns and 5 for a row of 15. Measured for the 20,000 rows that specs 3 and 5 write together, 10,000 stamps and 10,000 change rows of 15 columns: one transaction of 1.17 seconds on SQLite and 1.72 to 1.81 seconds on Postgres (`probes/output.md`, sections 4 and 12).

**Per corpus.** Nothing is done for each file. A sweep is for each expired row: one statement for each 5,000. The study reclaimed 150,000 rows in 31 statements, in 1.2 s on SQLite and 2.0 s on Postgres.

**Per lock.**

| Question | Answer |
|---|---|
| What is locked on SQLite | The one writer of the root's file, which the mount's writes take too (decision 4). |
| Who holds it, and for how long | A flush, for one batch of at most 1,024 rows. A `commit`, for its statements, which was 1.2 seconds for the 20,000 rows of a 10,000-entry write's stamps and change rows, measured. A sweep, for one chunk of 5,000 rows, 21 ms at the median and 202 ms at most in the study, and 70 ms at the median and 302 ms at most in the mount's file. First touch, once for each process. Each is a commit's length. A pass's chunks follow each other, so what a waiter sees on SQLite is most of the pass (decision 17). A mount's write holds the same writer for its own length, and a 10,000-entry write for about 28 seconds in the study. |
| Who waits | Another writer of the file: a flush, a record write of a change, a sweep chunk, and a write, edit, delete or move on the root mount, in this process or another. Behind a store write the wait is a commit's length. Behind a batch on the mount, a store write waits five seconds a try for four tries and then fails as decision 4 says. A read that a policy stops waits there too, because it stores its job with `commit`. |
| Who does not wait | Every read, list, glob, grep and search of every mount that no policy stops. Every write on a mount that is not the root. Every `query` of the store, since WAL serves a reader beside the writer. |
| What is locked on Postgres | The rows a statement writes, and at first touch one advisory lock for the length of that transaction. No table lock is taken. |
| In memory | The store's own turn lock, on its own connection. A verb takes the mount's, which is another. |

A read never waits on the store, because a read never calls it, the read that a policy stops excepted. The store's own longest hold is a batch's record write, which on SQLite queues other writers of the file and no reader. No table lock is taken on either engine, so the working agreement's rule for a table lock does not arise. SQLite's one writer is the engine's own, and it leaves every read running.

**What decisions 24 to 26 add.** `waiting_behind` and `discard_behind` issue no statement and cost the rows of one scope in memory. `expiry_sweeper` is one statement for each dependent and one for the parents in a call, each with the same few binds. A statement of fixed binds costs the store one statement at any size, and holds the SQLite store's writer for as long as it runs; the spec that owns it costs that hold against its own bound.

**Connections.** On Postgres a process holds two pools on the root's database, each of the mount's size: by default 5 kept and up to 15 at a peak, each. A pool opens a connection when one is asked for and none is free, so the store's pool holds what its own work needs and no more. A process that mostly reads holds one store connection, the flusher's. A process with many changes in flight at once holds up to 5 kept and 15 at a peak. A store that is not used opens none.

**Memory.** The buffer holds at most 16,384 rows, about 16 MB at ordinary widths. Each store connection on SQLite carries the profile's settings as a mount's does, among them a page cache of up to 256 MiB (`dialects.py:368-376`), and the store's pool holds up to 15.

**Storage.** Nothing of a session is removed unless a lifetime is set, so the store grows with use and has no bound. That is the ruling of 2026-11-23, and it is not a designed cap. Each owning spec states its rows. At spec 3's and spec 4's figures a year is up to about 41 million stamp rows, from 112,500 reads a day through sessions, and 5.5 million turn rows, from 15,000 turns a day. They are in the root's database, and on SQLite in the mount's file. This is an estimate from those specs' Cost sections and was not run.

**First touch.** Once for each process and store: the file settings, a look for the meta table, one read of its row.

## Left as it is

- **No session, job, stamp, turn or change is built.** Specs 2 to 8 own them. This spec registers no kind and no sweeper.
- **The action log.** It will be a kind and a sweeper of this store, on this file. Its completion, which the study says is retried and never dropped, is a record that may not be dropped, so by decision 14 it is not written behind. How it is retried, and what bounds the backlog while the store cannot be written, is the action log's spec.
- **One transaction for a change and its record on a root mount.** The study names it for Postgres and did not measure it (`research.md:158`). Since the ruling of 2026-11-23 the same is open on SQLite, where the change and its record are now in one file. It is the direction that would end the lost record decision 4 names, for a change on the root.
- **The store sharing the mount's pool on Postgres.** Measured, and it failed records beside a storm of batches (decision 5).
- **Planner statistics for the kernel's tables on SQLite.** The statistics pass is the mount's and analyses the mount's tables alone (`engine.py:732-742`). The kernel's tables are planned without `sqlite_stat1`: after 3,000 rows in a store table it named six mount tables and none of the store's.
- **A store connection with settings of its own on SQLite.** It carries the mount's page cache and memory map, which a few narrow tables do not need.
- **An engine shared by several storages**, which `a-storage-owns-its-engine-well` leaves to a later spec.
- **The session settings sent at every checkout on SQLite.** The store's connections pay them as a mount's do, until that spec's decision 1 lands.
- **A way to remove the kernel's records from a SQLite file and keep the files.** The tables can be dropped by hand, as decision 8's remedy says. No call does it.
- **A named storage that is not the root keeping the records.**
- **A file system carried across `fork`.** Its buffer would be copied, as its engines would.
- **The time of the trash.** `sweep_rows` keeps reading the system clock.

## Tests

Each is written and seen failing before the code. A count is of cursor statements recorded by a `before_cursor_execute` listener on `store.engine`, of rows read back, of files in a directory, of log records, or of an exit status. None reads a clock. Three seams are added through the adapter's `seam` (`seams.py:41-52`): `kernel-store:before-try`, at the start of each try of a `query`, a `commit` or a `record_after`; `kernel-store:before-commit`, inside `commit` and `record_after` before the commit is sent; and `kernel-store:before-flush`, in the task before it takes a batch. *Both engines* means a SQLite file and the Postgres leg behind `VFS_TEST_POSTGRES_URL`; every other test runs on a SQLite file and in memory.

Landing 1, `tests/storage/database/test_core.py`:

- `test_a_core_opens_no_connection_when_it_is_built`: 0 `connect` events, and 0 files in the directory.
- `test_a_core_without_the_vector_function_loads_no_extension`: 0 probes for the vector function in a checkout.
- `test_the_engine_host_is_an_engine_core`: the members of decision 7 are the host's own. The suite of `tests/storage/database/test_engine.py` passes with its patches of `profile_for`, `create_async_engine` and `random` moved to the core module, where those names are read.

Landing 2, `tests/storage/test_record_place.py`:

- `test_a_sqlite_storage_names_its_own_file`: the place's database is the storage's path, `durable` is true, the arguments are the storage's without `pool`, a `creator` among them, and 0 files exist after the property is read.
- `test_a_path_with_a_question_mark_keeps_it`: `notes?v2.db` gives `notes?v2.db`, and the URL's query is the storage's.
- `test_an_in_memory_storage_names_a_place_in_memory`: `durable` is false.
- `test_a_memory_url_read_as_a_file_names_no_place`, and `test_a_storage_on_the_generic_floor_names_no_place`: `None`.
- `test_a_postgres_storage_names_its_own_database_and_schema`: the URL and schema are the storage's, the arguments carry `pool_size` and not `pool`. No connection is made.
- `test_a_label_never_holds_the_password`: neither the label nor `repr(place)` holds it, for a URL given as text and for one given as SQLAlchemy's `URL`.
- `test_a_place_of_another_dialect_is_refused_when_the_store_is_built`: a `ValueError` that names both dialects and not the URL.

Landing 3, `tests/kernel_store/test_store.py`. A test that writes rows writes them in `vfs_kernel_probe`, a table that `tests/support/kernel_store.py` makes, since this spec's one table holds one row:

- `test_a_file_system_that_keeps_no_record_makes_no_file`: a write, a read and a close on a SQLite root leave exactly one file, and the store's engine saw 0 connections.
- `test_first_use_makes_the_kernel_tables_in_the_mounts_file`: the directory holds 1 file, that file holds `vfs_kernel_meta` whose row holds `KERNEL_FORMAT_VERSION`, and the mount's meta row and `SCHEMA_FORMAT_VERSION` are as they were.
- `test_close_leaves_one_file_and_no_side_file`: after records were written and the kernel closed, the directory holds exactly `knowledge.db`. The same with the store's engine disposed before the mount's and after it.
- `test_a_store_commit_waits_for_the_mount_writer_and_then_lands`: a mount write is held at the `write:before-apply` seam, one `commit` is started and has not returned, counted as 0 rows; the write is released and the row is there, counted as 1.
- `test_a_store_commit_behind_a_held_mount_writer_fails_as_unavailable`: with each checkout's `busy_timeout` at 0 and the mount's writer held, 4 `BEGIN IMMEDIATE`, one `KernelStoreUnavailable` that is retryable, and the mount's write lands when released.
- `test_a_mount_read_returns_while_the_store_writer_is_held`: a rival holds the file's writer through the store's engine, and a `read`, a `grep`, a `glob` and a `search` each return, counted as 4 results. An `edit` with no session started meanwhile has not returned, and lands when the rival commits.
- `test_two_stores_touch_one_place_first_together`: both are ready and the meta table holds 1 row. Both engines.
- `test_a_store_of_another_format_is_refused_and_named`: the raise carries `vfs.unavailable.schema` with `found` and `expected`, the detail names each kernel table and no prefix, and a file `read` still succeeds. Both engines.
- `test_the_store_pins_read_committed`: on the Postgres leg, with `default_transaction_isolation` set to `repeatable read` in the connection's settings, two stores take 50 numbers each, the 100 are exactly 1 to 100, and the store's engine saw 0 statements refused.
- `test_a_role_that_may_not_create_is_told_the_grant`: on the Postgres leg, a role with no `CREATE` on the schema calls `commit`. It raises `KernelStoreUnavailable` of kind `vfs.unavailable`, not retryable, whose detail names the grant and each table, counted as 1 raise and 0 errors of kind `vfs.internal`. The same for a role with no rights on tables that exist.
- `test_a_query_is_not_a_writer`: on SQLite its transaction begins with `BEGIN` and 0 `BEGIN IMMEDIATE`.
- `test_a_commit_behind_a_held_writer_gives_up_after_four_tries`: with each checkout's `busy_timeout` at 0, 4 `BEGIN IMMEDIATE` and one `KernelStoreUnavailable` that is retryable.
- `test_a_closed_store_answers_as_the_closed_kernel_does`: kind `vfs.unavailable.backend`, detail "the filesystem is closed".
- `test_next_number_has_no_repeat_and_no_gap_under_two_stores`: two stores take 50 numbers each at once, and the 100 are exactly 1 to 100. Both engines.
- `test_a_block_of_numbers_ends_at_what_is_returned`: `count=5` after 7 returns 12.
- `test_next_number_on_no_row_raises`.
- `test_insert_rows_stays_under_the_parameter_budget`: 10,000 rows of 5 columns with the budget narrowed to 1,000 go in 50 pages of at most 200 rows, counted by cursor events on SQLite and by a spy on the driver's `copy_records_to_table` on Postgres. Marked `slow`. Both engines.
- `test_upsert_rows_chunks_sorts_and_keeps_the_newest`: 10,000 rows under the same budget are 50 statements of at most 1,000 binds, with keys in order; a second call with lower `newest` values changes 0 rows, and one with higher changes 10,000. Marked `slow`. Both engines.
- `test_an_upsert_that_names_a_key_twice_is_refused`: a `ValueError`, and 0 statements sent. Both engines, since on SQLite nothing but this check refuses it.
- `test_delete_expired_binds_the_same_values_whatever_it_removes`: with 3 expired rows and with 12,000, the statement's text and its bind count are the same, and it removes at most `limit`.
- `test_record_after_survives_its_callers_cancellation`: the caller is cancelled at the `kernel-store:before-commit` seam, the row is there, counted as 1, and the error raised is the object the caller was cancelled with.
- `test_record_after_returns_a_warning_when_the_store_cannot_be_written`: one error of severity `warning` and kind `vfs.unavailable`, and no raise.
- `test_a_failed_first_touch_is_tried_again`: a second call after a held writer is released succeeds.
- `test_upsert_rows_says_how_many_rows_it_wrote`: an insert that does nothing on a conflict returns 8 for 8 new rows, then 1 for 4 rows of which 3 are there. Both engines.
- `test_row_chunks_and_key_chunks_cut_by_the_budget`: with the budget narrowed to 1,000, 10,000 rows of 5 fields are 50 chunks, and at `width=10` they are 100; 10,000 pairs at `width=2` are chunks of at most half the membership budget.
- `test_delete_where_removes_at_most_its_limit_by_a_three_column_key`: of 8 rows that match, a limit of 5 removes 5 and leaves 3, and the statement's bind count is the same with 8,000. Both engines.
- `test_two_functions_share_one_commit`: a `fn` that hands its transaction to two functions leaves both their rows, and when the second raises it leaves neither, counted as 2 rows and 0.
- `test_a_transactions_info_ends_with_it`: a value put in `transaction.info` is read later in the same `commit`, and the next `commit`, and a retried attempt, begin with an empty one.
- `test_two_commits_at_once_both_land`: two `commit` calls gathered on one store leave 2 rows, on a SQLite file, in memory and on Postgres. Both engines.
- `test_a_process_that_dies_between_a_change_and_its_record_leaves_the_change_alone`: a child process writes a file through the kernel and leaves through `os._exit(0)` at the `kernel-store:before-commit` seam of its `record_after`. The parent reads the file, counts 0 records, and the exit status is 0. Marked `slow`.
- `test_a_process_that_dies_after_its_claim_leaves_the_claim_in_doubt`: a child process commits a claim and leaves at the `write:before-apply` seam, and a second leaves at the seam of its completion. The parent counts 1 claim with no completion each time, with the file absent the first time and present the second. Marked `slow`.

Landing 3, `tests/base/test_kernel_store.py`:

- `test_the_kernel_builds_its_store_with_no_io`: 0 connections on either engine after construction.
- `test_an_in_memory_root_keeps_records_on_a_connection_of_their_own`: the store's engine opened 1 connection, which is not the mount's, and a `commit` returns while a mount call holds its turn.
- `test_a_root_that_names_no_place_keeps_records_in_memory`: a storage with no `record_place`, and `store.durable` is false.
- `test_records_in_memory_beside_a_database_mount_warn_once`: 1 `WARNING` on `vfs.kernel_store` at the first write, 0 at the second. When the database mount is added after the first record, 0 at that record and 1 at the next.
- `test_close_closes_the_store_within_the_close_timeout`, `test_a_cancelled_close_keeps_the_store_for_a_second_close`, and `test_a_store_that_fails_to_close_joins_the_storages_errors`: counted as closes and as errors in the group.
- `test_close_waits_for_a_record_in_flight`: a `record_after` is held at the `kernel-store:before-commit` seam, `close()` is started, and the record is released. The row is there, counted as 1, the store's engine has 0 connections open, and the directory holds 1 file.
- `test_a_commit_in_hand_at_close_starts_no_further_try`: with the file's writer held and each checkout's `busy_timeout` at 0, a `commit` is held at the `kernel-store:before-try` seam of its first try and `close()` is started. Released, it has sent 1 `BEGIN IMMEDIATE` and not 4, and raises `KernelStoreUnavailable`.
- `test_no_verb_shows_a_kernel_table`: after 3 records are written, `tree("/")`, `glob("**")` and the `/.vfs` listing return the rows they returned before, counted.
- `test_a_session_cannot_reach_the_kernel_store`: no public attribute of `AsyncSession` or `Session` is or returns a `KernelStore`.

Landing 4, `tests/test_sync.py`:

- `test_the_facade_closes_the_kernel_store`: 3 rows put behind through the facade's kernel are in the root's file after `close()`, the directory holds 1 file, and no `vfs-sync-loop` thread is left.

Landing 4, `tests/kernel_store/test_behind.py`:

- `test_a_flush_behind_a_held_mount_writer_keeps_its_rows`: 3 rows put behind while the mount's writer is held stay in the buffer after the failed flush, 1 `WARNING` is logged, `waiting_behind` returns the 3, and after the release and one more put all are written.
- `test_close_behind_a_held_writer_still_disposes_the_store`: the file's writer is held by another connection and 3 rows are put behind. `close()` sends 1 `BEGIN IMMEDIATE` on the store's engine and not 4, logs 1 `WARNING` that counts 3 rows dropped, and leaves 0 store connections open. When the holder closes, the directory holds 1 file.
- `test_a_close_with_no_budget_left_starts_no_flush`: with 3 rows waiting, `store.close(within=0)` sends 0 `BEGIN IMMEDIATE`, raises nothing, logs 1 `WARNING` that counts 3 rows dropped, and leaves 0 store connections open.
- `test_a_close_cut_short_starts_no_further_flush`: a flush is held at the `kernel-store:before-commit` seam while 2,000 more rows wait, and `store.close(within=0)` returns. Released, the store's engine has sent 0 further `BEGIN IMMEDIATE` and has 0 connections open, `dropped` grew by the 2,000, the held flush's rows are stored, and the directory holds 1 file. The same when the close is cancelled in place of the budget being spent.
- `test_a_read_only_file_holds_its_rows_and_warns_once`: on a file made read-only, 3 rows put behind one at a time leave 3 rows waiting and 1 `WARNING` that names the path, the task made 3 tries, counted at the `kernel-store:before-flush` seam, and a `commit` raises `KernelStoreUnavailable`.
- `test_a_role_that_may_not_write_keeps_its_rows_and_names_the_grant`: on the Postgres leg, 3 rows put behind by a role with no rights on the tables are still waiting after the flush, counted as 1 `WARNING` that names the grant and 0 `ERROR`. After the grant and one more put, 4 rows are written.
- `test_a_kind_that_can_never_land_drops_its_own_rows_alone`: a flush holds 3 rows of a kind whose `write` breaks a constraint and 3 of a kind that is sound. 3 rows are written, `dropped` grows by 3, and 1 `ERROR` names the first kind.
- `test_put_behind_sends_nothing_before_it_returns`: with the task held at the `kernel-store:before-flush` seam, the store has issued 0 statements when `put_behind` returns; released and drained, the rows are there.
- `test_the_task_runs_in_a_context_of_its_own`: a context variable the putter set is unset inside the kind's `write`, counted as 1 observation.
- `test_rows_put_in_one_turn_ride_one_flush`: 300 rows are 1 writer transaction, and 3,000 are 3.
- `test_rows_with_one_key_become_one_row`: 50 puts of one key send 1 row.
- `test_keyed_rows_reach_the_writer_sorted`, and `test_kinds_flush_in_the_order_they_were_registered`.
- `test_a_full_buffer_drops_its_oldest_and_counts_them`: with a capacity of 8 and the task held, 12 puts leave `dropped == 4` and the newest 8 are written.
- `test_a_flush_stays_under_the_parameter_cap`: 10,000 rows of a 15-column kind are 10 flushes, and no statement binds more than the budget. Marked `slow`. Both engines.
- `test_a_failed_flush_keeps_its_rows_and_the_next_put_sends_them`: 3 rows stay, 1 `WARNING` is logged, and after one more put 4 rows are written and 1 `INFO` is logged.
- `test_a_flush_that_can_never_land_drops_its_batch`: a batch of one kind that can never land is tried 2 times and no more, counted as writer transactions. 1 `ERROR`, `dropped` grows by the batch, and a later batch is written.
- `test_drain_returns_at_once_when_its_scope_has_nothing_waiting`: 0 statements.
- `test_drain_waits_for_its_scope_alone`, `test_drain_raises_when_its_flush_fails`, and `test_a_cancelled_drain_loses_no_row`.
- `test_a_put_after_close_is_dropped_and_raises_nothing`, and `test_close_flushes_what_the_buffer_holds`.
- `test_a_process_that_dies_loses_at_most_its_buffer`: a child process commits 5 rows, puts 7 behind with the task held, and leaves through `os._exit(0)`. The parent reads 5 rows and 0 of the 7, and the exit status is 0. Marked `slow`.
- `test_a_put_on_another_loop_moves_the_task_there`.
- `test_waiting_behind_returns_what_is_buffered_and_what_is_in_flight`: with the task held before a flush, 3 rows are waiting; with it held at the `kernel-store:before-commit` seam of that flush, the same 3; after the commit, 0. 0 statements are issued by the calls.
- `test_discard_behind_withdraws_by_scope_and_by_key`: of 6 waiting rows in two scopes, a discard of one scope returns 3, a discard of 2 keys returns 2, and 1 row is written.
- `test_a_row_in_flight_is_not_withdrawn`: a discard during the flush returns 0 and the row is stored.
- `test_waiting_and_discard_with_no_scope_and_no_key_are_refused`: a `ValueError` each.
- `test_a_deferred_task_runs_once_after_its_rows`: 50 requests of one key are 1 call of the task's `write`, made after the `write` of the kind registered before it, in the same transaction.

Landing 4, `tests/kernel_store/test_sweep.py`:

- `test_a_record_past_its_expiry_is_still_there_until_a_sweep`: the clock is stepped, 0 rows are removed, and `sweep()` then removes them.
- `test_a_pass_removes_expired_rows_in_chunks_of_five_thousand`: 12,000 expired rows and 100 live ones are 4 delete statements, which remove 5,000, 5,000, 2,000 and 0, and 100 rows are left. Marked `slow`.
- `test_a_pass_goes_on_until_nothing_expired_is_left`: 60,000 expired rows are removed by one pass in 13 delete statements, 12 that remove 5,000 and 1 that removes none. Marked `slow`.
- `test_nothing_is_swept_until_sweep_is_called`: with expired rows in a registered table, 2,000 commits, 20 flushes and a `close` call the sweeper 0 times and remove 0 rows.
- `test_a_cancelled_pass_has_removed_whole_chunks`: a pass over 12,000 expired rows is cancelled at the `kernel-store:before-commit` seam of its second chunk. 5,000 rows are gone and 7,000 are left, counted.
- `test_two_passes_at_once_remove_each_row_once`: two stores remove 2,000 rows between them, and the two counts add up to 2,000 whichever pass ends first. Both engines.
- `test_a_flush_runs_between_two_chunks`: a pass over 12,000 expired rows is held at the `kernel-store:before-commit` seam of its first chunk, and 3 rows are put behind. Released, the flush's rows are written before the second chunk's delete is sent, counted in the order of the store's statements: the flush's `INSERT`, then the second chunk's `DELETE`. A second case has the flush fail: the pass still sends its second chunk.
- `test_a_root_that_masks_sweep_runs_no_pass`: a root built with `deny_ops={"sweep"}` and 3 expired rows calls the sweeper 0 times, and a second file system over the same file with no mask removes the 3.
- `test_a_sweeper_with_small_batches_is_called_until_it_finds_nothing`: a sweeper that removes 100 rows a call is called 4 times for 300 expired rows.
- `test_an_expiry_sweeper_removes_dependents_before_parents`: 3 expired parents with 4 dependent rows each, and 1 live parent with 2. A call with a limit of 5 removes 5 dependent rows and 0 parents. The calls that follow remove the other 7 and then the 3 parents. 1 parent and 2 dependent rows are left, and no call removes more than 5. Both engines.
- `test_an_expiry_sweeper_binds_the_same_values_at_any_size`.
- `test_a_row_with_no_expiry_is_never_swept`: 3 rows whose expiry is null and 2 that are past theirs, with the clock stepped a year on. A pass removes 2, and 3 are left.
- `test_the_public_sweep_runs_one_pass`: `fs.sweep()` with 3 expired rows in a registered table removes them, counted as 1 call of the sweeper that found work. `fs.sweep("/m/.vfs/trash")` on another mount, and a `sweep` refused for want of rights, call the sweeper 0 times.
- `test_a_public_sweep_makes_no_kernel_table`: on a file system that kept no record, `fs.sweep()` leaves the database with the tables it had, counted.
- `test_a_failed_pass_is_a_warning_on_the_sweep`: the store's writer is held, and `fs.sweep()` is a success that carries 1 error of severity `warning`.

Lint, `tests/lint/test_code_shape.py` and `tests/models/test_kernel_rows.py`:

- Every kernel table's name begins with one of `KERNEL_TABLE_PREFIXES`, and no table of `build_vfs_tables` does.
- `vfs.kernel_store.store` is the one new name in `ADAPTER_IMPORTERS`, and `vfs.kernel_store` has a rung.
- Under `src/vfs/kernel_store/` one line reads the system clock, the default of `clock`, and none reads the monotonic clock or a loop's time: the budget of `close` is a `Deadline`.
- `vfs.base`, `vfs.session`, `vfs.sync` and `vfs.sync_session` import no SQLAlchemy, and `vfs.storage.protocol` imports none at run time.

## Scope

In, by landing:

1. `src/vfs/storage/backends/database/core.py` (new), `engine.py`, `tests/lint/allowlist.py` for the lowered count.
2. `src/vfs/storage/protocol.py`, `src/vfs/storage/__init__.py`, `src/vfs/__init__.py`, `src/vfs/storage/backends/database/backend.py` for the property.
3. `src/vfs/models/kernel_rows.py` (new), `src/vfs/kernel_store/__init__.py` and `store.py` (new), one function in `attempts.py`, `src/vfs/base.py` for the construction and the close, `tests/lint/test_code_shape.py` for the rung and the importer, `tests/support/kernel_store.py` (new). The support module holds a clock that a test steps, and `probe_table(store)`, which makes a table named `vfs_kernel_probe` with a key, a counter and an expiry in a `commit` of the store's own, for the tests of this spec that write rows. The table is a test's and is in no build of `build_kernel_tables`.
4. `src/vfs/kernel_store/behind.py` and `src/vfs/kernel_store/sweep.py` (new), and `src/vfs/base.py` for the pass that `sweep` awaits.

The docs: `documentation/how-to/take-vfs-to-production.md` (new) with landing 3 and completed by landing 4, with its entry in `documentation/navigation.json` and its one link from `documentation/tutorials/keep-your-files-in-a-database.md`; `documentation/maintainers/kernel-store.md` (new) with landings 3 and 4, `documentation/maintainers/cancellation.md`, `documentation/reference/python-api/storage.md`, and the docstrings in `sqlite.py`, `postgres.py`, `memory.py`, `backend.py` and `base.py`.

`base.py` is held at 3,090 lines and grows by the store's construction and its close, so its entry is raised by that count, as the write preconditions raised it.

Out: every table but `vfs_kernel_meta`, every public method of a session or a job, the action log, and everything under "Left as it is". The Postgres leg is run before the branch's pull request, by the `db_test` skill.

## What the docs must say

- **An early page for a reader who is going to production,** by the ruling of 2026-11-23: a page of its own, `documentation/how-to/take-vfs-to-production.md`, first in the how-to section of `documentation/navigation.json`, which the last section of the tutorial `documentation/tutorials/keep-your-files-in-a-database.md` links to. It says three things. `VirtualFileSystem()` with no storage keeps everything in memory, sessions and jobs included, and all of it ends with the process. A production system gives the root a database, `VirtualFileSystem(storage=PostgresStorage(...))`, and its sessions and jobs are then kept there and seen by every process. A database mounted beneath an in-memory root keeps its files and not the sessions, and VFS logs one warning when that is the shape. The same page says to call `fs.sweep()` on a schedule: it empties the trash and removes expired jobs, and expired sessions where `session_lifetime` is set, and nothing is removed until it is called. It says that a file system which masks `sweep` for its agents runs no sweep, and that the schedule then calls it from a file system of its own over the same database, with no mask. It says that on SQLite a long sweep is run when the file is quiet, and that Postgres is the engine for a system with long batches or many writers. For Postgres it names the grant a serving role needs when it may not create tables.
- **`documentation/maintainers/kernel-store.md`, new.** What the store is and why it is one for each file system. Where it lives on each engine. The two transactions and the two forms of decision 10, with both tables. The writer, what it drops and when. The sweep and the clock. The eight rules of decision 22. That it is private.
- **`documentation/maintainers/cancellation.md`.** `record_after` runs out of its caller's reach and is not marked, and why.
- **The docstring of `SQLiteStorage`.** A file system whose root is this storage keeps its sessions and jobs in the same file, in tables of their own. A copy of the file carries them. SQLite has one writer for a file, so while a large batch is being written a session's records are written late, and a job cannot be stored or resumed until the batch ends. A change made through a session while another writer holds the file for longer than about 20 seconds can land without its record, and its result then carries a warning that says so. Postgres has no such wait.
- **The docstring of `PostgresStorage`.** The kernel's tables are in the same schema, on a second pool of the same size, and a listener put on `storage.engine` does not reach it.
- **The docstring of `InMemoryStorage`.** Sessions and jobs are in memory too, and end with the process.
- **The docstring of `DatabaseStorage.record_place`,** and the Storage reference page under "Writing a Storage Backend", for `RecordPlace`.
- **The docstring of `AsyncVirtualFileSystem.sweep`.** A sweep of the root's trash also removes the kernel's expired records: jobs past `job_lifetime`, and sessions past `session_lifetime` where one is set. A session is never removed for its age unless a lifetime is set. A root that masks `sweep`, or a caller who may not write the root's trash, removes none of them, and no other call does.
- **The docstring of `AsyncVirtualFileSystem.close`.** It writes what the file system had not yet written about its sessions, and then releases the store. When another process holds a SQLite file's writer, it tries once and drops what it could not write.
- **`documentation/tutorials/keep-your-files-in-a-database.md` gains one link, to the production page, and is otherwise not changed.** Its last step says `vfs.db` is the only file to remove (`:96`). Since the ruling of 2026-11-23 that is true of every file system on SQLite, with records or without. A test holds it.

A docstring changes, so `scripts/docs.sh check` runs before the pull request.

## Prior art, and where this spec departs

Read on 2026-11-23 in the clones and at the lines the research memo `research/2026-11-23-where-a-system-keeps-its-own-records.md` records. `systemd` is not cloned, so its `tmpfiles` rules for age were not read.

Where this spec agrees:

- **Bookkeeping lives in the store it describes.** ext4's journal is inode 8 of the file system it protects, FFS's is a file in the root directory, and SQLite's and Postgres's own tables are in the user's file and the user's database. The kernel's tables are in the root storage's own file and its own database (decisions 4 and 5), and a copy of the store carries them.
- **The record of a read is made after the read, in memory, by a call that cannot fail the read.** That is `touch_atime` in Linux, `IN_ACCESS` in FFS and `fileRAccess` in fossil. It is `put_behind` here (decision 13).
- **Most reads leave no new record.** `relatime` writes a time only when it is stale, and a day apart at most. Rows of one key become one row here, and a session's use is written at most once in five minutes.
- **A crash loses what was only in memory.** `lazytime` holds a time for up to a day, and Postgres discards its statistics after a crash. A process that dies here loses its buffer.
- **A store of another format is refused and not repaired.** ext4 refuses an unknown feature, fossil another version of its super block, and Postgres another catalog version. Decision 8 refuses another `format_version`.
- **Expired state is removed by a job that somebody schedules, and nothing is removed until then.** FreeBSD's cleaner of `/tmp` is a `cron` script that ships turned off, Plan 9 ships none, and fossil discards no snapshot until an operator sets a lifetime. Decision 17 removes nothing until `sweep` is called.
- **What has expired reads as gone before it is removed.** A Linux key past its time is refused on use before its collector runs. Every read of a table that expires filters on the expiry.
- **Nothing expires unless a lifetime is set.** A file does not, and a fossil snapshot does not by default. A session does not.
- **Reclaim is a privileged act.** The `cron` job runs as root and fossil's commands are console commands. The pass runs only for a caller allowed to sweep the root's trash.
- **One writer, taken when the transaction begins.** That is SQLite's rule for a file in WAL, and every store transaction that writes begins as a writer.
- **The shutdown of a file system flushes.** fossil's `fsClose` writes its metadata before it ends. The kernel's `close` writes what the store had buffered.

Where this spec departs. Each row is a deviation under Article 3.

| The convention | What this spec does | The constraint that moved it | Expiry |
|---|---|---|---|
| Plan 9 serves a server's own state as files: fossil's snapshots, its archive and its users file are in the tree. | A record has no path, and no verb shows it (decision 1). | Article 1 gives a path only to an Entry, which has a kind, a revision and rights. A session row has none of the three, and Article 3's own limit is to keep out what would need a dishonest file shape. | When a view of sessions and jobs under `/.vfs` is designed. All nine specs leave it out. |
| An access time is advisory. No operation in Unix or Plan 9 is refused because one was not written. | A stamp that was dropped refuses the session's next change of that path until one read (decision 14). | The record is what a session's protection against a lost update rests on, so its loss must err toward a refusal and never toward a change that should have been refused. | None. |
| A delayed record is written on a timer: each second in fossil, 30 seconds in FFS, 12 hours under `lazytime`. | It is written as soon as the store's one task is free, with no timer (decision 13). After a failed flush it waits for the next row and for no clock (decision 15). | Another process takes up the same session in the next request and must find what this one saw; and a timer would put a clock in every test. | None. |
| A journaling file system writes a change and its record as one transaction. | Two transactions, on both engines and for every mount (decision 10). A change can land without its record, and the caller is told. | The change may land on a mount that is not the root, and a storage commits inside its own method. | When a change and its record on a root mount share one transaction, which "Left as it is" names. |
| A file system's bookkeeping is made when the file system is made, by `newfs`, `tunefs` or `flfmt`. | The tables are made at the store's first use (decision 8). | VFS has no provisioning step: a mount makes its own tables at first touch, and a file system that keeps no record must make none. | None. |
| ext4 can keep its journal on another device, and fossil its archive on another server. | No argument names another place for the records (choice 3). | One thing to copy, to back up and to delete, and a root in memory that keeps everything in memory. | When a deployment needs the records apart from the root; "Left as it is" names a storage that is not the root. |
| The system's own names are out of the user's reach: SQLite refuses a table named `sqlite_…`, and no name reaches an ext4 journal's inode. | Three prefixes are reserved by a lint in VFS. Neither engine knows them, and an application's table in the same file or schema can take one. The remedy of decision 8 therefore names tables and never a prefix. | The database is the application's, and VFS reserves nothing in it that the engine would enforce; the mount's own tables stand the same way. | None. |
| A store of another format does not mount at all. | The records are refused and the files are served (decision 8). | The mount has a format number of its own, and a difference in the records' format says nothing about the files. | The first release, when decision 8 is rewritten. |
| A second writer waits without end (`flock`), or is refused at once and tries again itself (Plan 9's exclusive-use files). | It waits five seconds a try for four tries and is then refused as unavailable; rows written behind are tried again by the store (decisions 4, 9 and 15). | SQLite's one writer and its timed poll, and the rule a mount's write already follows; an agent must be answered in a bounded time. | None. |
| Where a lifetime is set, the system reaps by itself: fossil from a timer, Linux from its collectors. | No timer and no leader; only the public `sweep` (decision 17). | A storage does no work in the background, and nothing is destroyed that a developer did not ask to have destroyed. | None. |
| `close` writes nothing that was delayed; where it does (NFS) it returns the error; a closed descriptor is gone, error or not; and `fsync` is the call that waits. | `close` flushes; a failed flush is logged and not raised; a `close` that was cancelled is finished by a second; and no public call waits for the records (decision 19). | `close` here is the unmount of a file system and not the close of a file. Every record written behind may be dropped (decision 14), so no caller is owed its arrival, and a change that must read its own session's rows drains them inside the kernel (decision 16). | None. |

## Earlier decisions this reverses

- **The study's flusher waited for 256 rows.** This one flushes as soon as it is free, because a session's rows must reach another process without a later row to push them. Criterion 2 of roadmap story H0, "the 256th adds exactly one insert carrying 256 rows", no longer describes the writer, and H0's spec restates it.
- **Criterion 6 of story H0 reclaims "in chunks of `membership_budget`".** The sweep's chunk is 5,000 rows, the size the study measured, by a statement that binds no key list and so meets no parameter cap.
- **Roadmap story H0's rule iv puts the log in the root mount's storage.** The storage names the place and the kernel's store keeps the rows. On both engines the place is the root storage's own database.
- **Roadmap decision D67, and the study's condition.** D67 put the log on SQLite in a database file of its own, and the study's GO was "provided SQLite's log has a file of its own" (`research.md:183`). The ruling of 2026-11-23 keeps one file. What the study measured in the shared file is stated in decision 4 as the price, and the roadmap's row for D67 and its note under story H0 are changed when landing 2 lands.
- **This spec's own decision 4, as first drafted:** a second file named with `-kernel`. With it go the choice of a suffix, the tests of a sibling file, and the promise that a store write is served while the mount's writer is held.
- **`EngineHost` "owns one mount's database connectivity".** The connectivity becomes `EngineCore`, and the host is what a mount adds to it.
- **This spec's first draft named the record of what a session changed as the case for the claim-before form.** Spec 5 writes that record after the change (its decision 4), and decision 10 now says so. The claim-before form's case is a job's step.
- **This spec's own decision 17, as first drafted:** each process swept by itself, after its first 64 writes to the store and after every 1,024 from then on, eight chunks at most a pass. By the ruling of 2026-11-23 a pass runs only when the public `sweep` is called, and goes on until nothing expired is left.
- **This spec's first draft ended a sweeper's turn when a call removed fewer than 5,000 rows.** Decision 17 now ends it when a call removes none, so a sweeper with smaller batches finishes its work.
- **This spec's own decision 19, as first drafted:** a close cut short by its timeout kept the store for a second `close()`. Today's kernel keeps a target only on a cancellation. The store now keeps to a budget at close, makes one try for each last flush, leaves nothing open when it is cut short, and leans on no second call.
- **This spec's own decision 5, as first drafted:** READ COMMITTED "with no pin". The level is pinned.
- **This spec's own decision 15, as first drafted:** a batch that can never land was dropped whole. It is tried once more a kind at a time.
- **`documentation/maintainers/cancellation.md` says "nothing but the storage makes a session, a connection or a transaction on the engine".** That stays true of the storage's engine. A file system now has a second engine, the store's, which a listener on `storage.engine` does not reach.

## Choices for the owner

Each is decided above, and the decision stands until it is ruled on. Two that earlier rounds listed are ruled and are not here: `RecordPlace` is a public name, and no public call flushes the writer.

1. **Ruled on 2026-11-23: on SQLite the records are in the mount's own file, and there is no second file.** Decision 4 states the price. The choice this item first held, the suffix of a sibling file, has nothing left to name. The spec review of 2026-11-23 measured the price after the ruling, and decision 4 now carries the figures. One of them the ruling did not have before it: behind a writer held longer than about 20 seconds, a change made through a session can land without its record, for good, and the caller is told by a warning. With nothing else running, and beside a 10,000-entry write of about 8 seconds, nothing failed and nothing was lost. **Ruled again on 2026-11-23, with that figure in view: one file stands.** Reason: on a SQLite file no other writer is expected to hold the database for that long. SQLite serves demos and local applications, and a load that holds its writer for more than 20 seconds, a long batch or batches one after another, belongs on Postgres, where the same windows lost nothing. The other choice was a second file.
2. **Ruled on 2026-11-23, and since measured: the store has a pool of its own on Postgres,** of the mount's size. The kernel's store is its own thing and not the storage's, so it does not borrow the storage's connections. The other choice is the mount's pool: no second set of connections, and a flusher that can wait behind batches. Measured in the spec review of 2026-11-23 (`probes/output.md`, sections 13 and 14): with 32 writing sessions a record costs the same 22 to 25 ms on the mount's pool, on a pool of 15 and on one of 32, and the store's pool was never more than 8 deep. Beside 32 batches the mount's pool gave a record no connection in 30 seconds five times and a flush once, and a pool of the store's own failed nothing. The default stands: a pool of the store's own, of the mount's size.
3. **Ruled on 2026-11-23: no argument names another storage for the records.** A root in memory keeps them in memory, and warns once when a database is mounted beneath it. The other choice was `VirtualFileSystem(records=…)`. Reason: a file system made with no storage is in memory, its sessions and jobs with its files, which is right for a first trial and for a test. A system that goes to production gives its root a database, and an early page of the docs says so ("What the docs must say").
4. **A store of another format is refused, never reset.** A reset would be kinder while the design is unreleased, and would end waiting jobs without a word.
5. **A place that cannot be written is not replaced by memory.**
6. **Ruled on 2026-11-23: expired records are removed only when the public `sweep` of the root's trash is called.** The count this spec first had, 64 writes and then every 1,024 in each process, is gone, and no new public name is added. The sweep removes only what has expired, and a session has no expiry unless the developer sets one: a session is part of a conversation's state, and a conversation taken up again after 90 days must find what it had read. A job expires after `job_lifetime`, 24 hours by default, and is swept.
7. **The store is a package of its own, `vfs.kernel_store`, and one of its modules may import the adapter.** The other choice is a package inside the adapter.
8. **The store tells no submitter when a row is stored or dropped.** A caller reads what waits, with `waiting_behind`. The other choice is a callback for each row, which spec 3 asked for.

## Where this spec disagrees with the overview or the guides

1. **`documentation/how-to/interrupt-a-job-and-ask-a-person.md`, "Find Jobs That Are Waiting".** The first draft proposed a sentence here. The guide already carries it (`:477`, "A file system whose root storage is in memory keeps its jobs in memory too, even when a database is mounted beneath the root"), and no change is proposed.
2. **`documentation/how-to/keep-a-session-for-each-conversation.md`, the paragraph that begins "A session is stored in the database".** It says VFS keeps the session "in the database you already run". Since the ruling of 2026-11-23 that is true as written on both engines, and no change is proposed.
3. **The overview's "kept by the storage of the root mount".** This spec reads it as "kept in the place the root storage names". The storage class gains one property and no record logic. No change to the overview's words is proposed.

The first draft listed a fourth: the overview's public names held none of this spec's. Ruling 10 of the reconciliation adds `RecordPlace` and a storage's `record_place` to that list, so it is settled.

## Needs no other spec meets yet

Nothing was open at `7c383f32`. The rulings of 2026-11-23 came after it, and four specs still say what the rulings reversed. Each is its owner's to change, and none is needed to build this spec.

- **Spec 2.** Its Cost has the counted sweep, "a pass calls it up to eight times, and a pass is due every 1,024 writes of a process". Its decision 18 is still headed by a session that expires after 30 days, under the ruling's note. Its reclaim ends a step when a call "returns fewer than it was asked for", where a sweeper here ends when a call removes none.
- **Spec 3.** Its Cost says "Sessions live 30 days".
- **Spec 4.** Its decision on turns and its Cost bound a session's turns by the 30 days.
- **Spec 5.** Its line on a session's age reasons from the 30 days.
- **An expiry must be a stored column.** `delete_expired` compares a stored column with the pass's one reading of the clock. Spec 2's decision 18 has yet to settle whether a session's expiry is stored, or worked out from `last_used_at` and the lifetime of the process that asks. This store's sweep needs the first, or a sweeper of spec 2's own whose `where` works the expiry out from the lifetime it is handed.

The six items of the second round are closed:

1. Spec 2 has each kind's `write` call `resolve`, and lists the callers in its decision 14. It keeps no memo in `transaction.info`, which costs a flush that holds a use and a stamp of one session one more read, and breaks nothing. Decision 24 here now gives the order of kinds as spec 2's decision 17 has it.
2. Spec 2's sweep is one `Sweeper`, `sessions`, that works in the `commit` it is given and stops at `limit` rows (its decision 22). Its `settle` is `drain(ref.scope)`.
3. Spec 8's orphan statement carries `LIMIT :limit` and is a sweeper of its own (its decision 9).
4. Spec 3 keeps no table beside the buffer, and reads it with `waiting_behind` and withdraws with `discard_behind` (its decision 8).
5. A public drain is ruled out by the last round's ruling 4. `close` flushes. Spec 3 keeps the choice for the owner.
6. Spec 7 registers `expiry_sweeper(jobs, key=jobs.c.job_id, expires=jobs.c.expires_at, dependents=(pages.c.job_id,))` (its decision 36).

The two items other specs addressed to this one are met:

- **Spec 3, item 1: a kind written both ways that has no counter.** Met by rule 7 of decision 22, in the words asked for, and by decision 24.
- **Spec 7, item 1: a read that a policy stops.** Met by rule 3 of decision 22, in the words asked for, as the last round's ruling 3 has it. Decision 13 and "Cost" name the exception.

Two sentences in other specs differ from this one and break nothing. Each is its owner's to change.

- Spec 2's "Builds on" says no call drops one scope's rows, so its removal drains first. `discard_behind` is that call (decision 24). A drain serves as well: the rows are written and then removed with the rest.
- Spec 7's decision 36 names `vfs_job_replies.job_id` as a dependent of its sweeper, and spec 8's decision 9 registers a sweeper of its own for the same rows. Decision 26 says why both may stand.

## Not checked

What the spec review of 2026-11-23 ran is no longer here: the store in the mount's SQLite file, two engines at `close`, the mount's first touch beside tables it did not make, the counter, a sweep and a deadlock on Postgres 19, the flusher as designed, the three pool shapes, a read-only Postgres, and `bulk_insert` from outside a storage's session. Each is cited where it is used, and `probes/output.md` holds the figures. All of it ran on a stand-in for the store beside today's code, on one machine, since nothing of this spec is built.

- **The store itself.** Every figure is the stand-in's. The rules this spec adds after the review were not run at all: one try at close, the wait for transactions in flight, a pass that lets its own store's flush go first, a batch tried again a kind at a time, the pinned isolation level, and the privilege refusal.
- **A root that cannot be swept.** That a masked `sweep`, a storage that declares none, or a caller with no rights runs no pass is read from the gate (`base.py:258-267`, `ops.py:101`, `:174`) and was not run.
- **Postgres 15 to 18.** One container ran, Postgres 19.0. The study did not run them either.
- **`expiry_sweeper`,** on either engine.
- **The batch storm on Postgres.** The run beside 32 batches is one window of 90 seconds for each pool shape, and was not repeated.
- **The size of the store over a year.** The 41 million stamp rows and 5.5 million turn rows of "Cost" are worked out from specs 3 and 4 and were not run.
- **A loss of power.** The tests of decision 10 end a process between two commits. None cuts the power, so what the two engines keep of a commit that had returned rests on `synchronous = FULL` and on Postgres's own durability.
- **A real `fsync`.** The flush times are from a laptop whose `synchronous = FULL` does not force the disk.
- **The line counts** `engine.py` falls to and `base.py` rises to.
- **The other eight specs after `7c383f32`.** Each was read there in its "Builds on", its list of unmet needs and the decisions cited here. Names are frozen from that commit. What a decision says may still have changed in the last round, which every spec revised at once.
- **Decision 26 on Postgres.** The bounded delete by a row value and the row count of an insert that does nothing ran on Postgres 19 and held. A dependent's delete through a subquery was compiled for Postgres and run on SQLite. To run: the tests marked *Both engines* that name `expiry_sweeper`, on the Postgres leg.
- **How long a statement of fixed binds holds the SQLite store's writer** at the sizes specs 3 and 4 allow: a rewind that removes 16 MiB of stamps, a fork that copies 100,000 turns. To run: each on a SQLite file with a second task counting its own `commit` calls served meanwhile.

## One line

The kernel has one store of its own for each file system, in a place its root storage names, which a read writes to only from behind and a change writes to in a second transaction whose every crash point is stated.
