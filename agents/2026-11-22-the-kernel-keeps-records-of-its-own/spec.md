# The kernel keeps records of its own

A draft, written on 2026-11-22 and read against `a-job-is-interrupted-and-resumed` at `6dae6a1d`. It is not reviewed, and nothing is built. It is spec 0 of the nine that `agents/2026-11-22-the-specs-for-jobs-and-sessions/overview.md` maps. It rests on the study `agents/2026-11-21-what-a-log-row-per-call-costs/research.md`, on roadmap decision D67 (`context/standards/roadmap.md:1278`), and on five probe scripts run on 2026-11-22 against SQLite 3.50.4 and SQLAlchemy 2.0.52 on Python 3.13.11, which are named where they are used. No probe ran on Postgres. It was reconciled on 2026-11-22 with the eight other drafts as they stood at `59946f0d`: decisions 24 to 27 are that round's, a sixth probe was run for them, and no decision was renumbered.

## The outcome wanted

The kernel has one place to keep rows about calls, and one small private interface to it. A session, a turn, a stamp, a change, a job and a line's journal are kept there by the eight specs that follow, and the action log later. Each of those specs names its table and its statements and invents nothing about storage: where the rows live on each engine, how the tables come to exist, how a row is written without a read waiting for it, how a row is written with a change, how a number is handed out, how expired rows leave, and what `close` does.

This spec builds no session and no job. It builds the place and the interface.

## Builds on

- **The log cost study**, `agents/2026-11-21-what-a-log-row-per-call-costs/research.md`. Run on 2026-11-21. It is the measured basis: written behind, a read adds zero synchronous statements; on SQLite the kernel's rows cannot share the mount's file; one buffer for each router with one flusher held at most 258 rows.
- **Roadmap decision D67**, decided: on SQLite the log is a database file of its own beside the mount's file, and on Postgres it is in the root mount's schema.
- **`agents/2026-11-20-vfs-serves-sqlite-and-postgres-only/spec.md`**, landed as pull request 30. Two engines, and a generic floor fit for testing only.
- **`context/specifications/archive/2026-11-12-close-leaves-no-sqlite-side-files.md`** and **`agents/2026-11-21-a-timed-out-close-leaves-no-connection-open/spec.md`**, both landed. A closed SQLite storage leaves its database file and nothing beside it.
- **`agents/2026-11-21-a-sqlite-writer-beside-a-batch-waits-for-its-commit/spec.md`**, landed. A SQLite writer waits five seconds a try for four tries.
- **`agents/2026-11-21-a-storage-owns-its-engine-well/spec.md`**, drafted and not built. It rewrites `src/vfs/storage/backends/database/engine.py`, and so does landing 1 here. Whichever lands second is rebased on the first. Its decision 1, settings sent once for each connection, then covers the store's connections too.
- **`agents/2026-11-21-a-cancelled-call-is-whole-on-every-path/spec.md`**, drafted and not built. It rewrites `src/vfs/storage/backends/database/attempts.py`. This spec adds one function to that module and changes none.
- **The eight other specs of the overview**, each drafted and none built, read at `59946f0d` while each was being revised. This spec needs nothing from any of them to be built. What each asks of the store is answered in decision 27.
  - Spec 1, `a-row-carries-an-etag-and-a-change-can-require-it`, and spec 6, `a-policy-judges-each-step`, keep no record and do not use the store.
  - Spec 2, `a-session-is-stored-named-and-forked`: `vfs_sessions` (its decision 13, "`vfs_sessions` holds one row per session, under a key that is never used twice"), `resolve` (decision 14), the use written behind (decision 17), removal and its two sweep passes (decision 22).
  - Spec 3, `the-session-remembers-what-it-read`: `vfs_session_stamps` (decision 4), its store statement (decision 6), a read's stamps behind and a change's with the change (decision 8), the trim (decision 15).
  - Spec 4, `a-session-works-in-turns-and-rewinds-or-forks-at-one`: `vfs_session_turns` (decision 2), the counter (decision 4), the rewind's one transaction (decision 12), the fork's copy (decision 17).
  - Spec 5, `a-rewind-puts-a-sessions-files-back`: `vfs_session_changes` (decision 3), written by the record-after form (decision 4).
  - Spec 7, `a-job-is-interrupted-and-resumed`: `vfs_jobs` and `vfs_job_pages` (decision 4), the conditional update (decision 5), the job committed before its result returns (decision 6), the claim and its lease (decisions 21 and 23), `cancel_session_jobs` (decision 35), the lapse (decision 36).
  - Spec 8, `an-interrupted-line-replays-its-replies`: `vfs_job_replies` (decision 9).

## Terms

- **Record.** One row the kernel keeps about calls: a session, a turn, a stamp, a change, a job, a reply of a line.
- **Kernel store.** The one object, for each file system, through which every record is read and written. In code it is `KernelStore`. The overview calls it by this name.
- **Root storage.** The storage of the mount at `/`, which the kernel owns.
- **Place.** The database a kernel store keeps its tables in: a SQLAlchemy URL, the engine arguments, a schema. In code it is `RecordPlace`.
- **Sibling file.** On SQLite, the store's database file, which sits beside the mount's file.
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

Read on 2026-11-22 at `6dae6a1d`. A probe is a script that was run. The scripts are under the session's scratch directory, in `specs/spec0/`, and none is kept in the repository.

| Fact | How it is known |
|---|---|
| The kernel's constructor takes `storage`. With none it makes an `InMemoryStorage`. The root mount is `owned`. | Read, `src/vfs/base.py:301-302` and `:319-327`. Run: the default root is an `InMemoryStorage` and is owned. |
| The constructor does no I/O and binds nothing to a loop. The synchronous face builds the kernel on the caller's thread and starts one loop thread. | Read, `src/vfs/base.py:286-331` and `src/vfs/sync.py:120-135`, `:648-656`. Run: the facade starts one thread, `vfs-sync-loop`, and `close()` ends it. |
| The kernel keeps no table of its own. Every call on a storage goes through `_call_storage`, and a storage "opens and commits its own transaction inside each method, and the kernel never sees one". | Read, `src/vfs/base.py:2852-2879`. |
| `close()` empties the mount table, then closes each owned storage once, all at the same time, each within `close_timeout`. A close that was cancelled keeps what it had not closed, and a second `close()` finishes. | Read, `src/vfs/base.py:539-579`. |
| A session is an object in memory. `open_session` returns `AsyncSession(self, authority)`. | Read, `src/vfs/base.py:655-663`. |
| A storage declares verbs through `capabilities()`, a set of `Op`. What is not a verb is an optional protocol: `SupportsHolds`, `SupportsTraits`, `SupportsRebuild`, `SupportsClose`. | Read, `src/vfs/storage/protocol.py:469-577`. Run: the default root satisfies all four, and its 24 capabilities are verb names. |
| One class serves every storage. `SQLiteStorage` and `PostgresStorage` construct `DatabaseStorage`, and `InMemoryStorage` is a `SQLiteStorage` whose path is `:memory:`. | Read, `src/vfs/storage/backends/sqlite.py:77-85`, `memory.py:36-77`. |
| A storage builds one `EngineHost`. The host builds the engine, the mount's tables, the session factory, and runs first touch. | Read, `src/vfs/storage/backends/database/backend.py:166-173`, `engine.py:161-242`. |
| `EngineHost` holds two things in one class. One is what any database needs: the engine (`:195`), the profile (`:198`), the listeners that refuse a cancelled attempt (`:203-208`), the turns of a one-connection database (`:211-213`), SQLite's transaction control (`:215-216`, `:955-985`), the retry (`:336-371`), the classifier (`:373-399`), the file settings (`:575-582`) and the dispose (`:547`). The other is what only a mount needs: the mount's tables (`:182`), the vector probe, the root row and the posture (`:625-696`), the planner statistics. | Read. The module is held at 1,008 lines, `tests/lint/allowlist.py:32`. |
| First touch makes the tables when the meta table is missing, under a serialization point, and writes `SCHEMA_FORMAT_VERSION`, which is 28. A database of another version is refused with `vfs.unavailable.schema` and the words "re-provision the mount". Nothing migrates a schema. | Read, `engine.py:625-663`, `:698-703`, `:913-930`, `src/vfs/models/rows.py:135`. Pinned by `test_version_mismatch_refuses_loudly`, `tests/storage/database/test_engine.py:254`. |
| SQLite's connections carry `busy_timeout = 5000` and `synchronous = FULL`, and the file is put in WAL. A busy writer is retried four times. | Read, `dialects.py:368-381`, `engine.py:170-171`. |
| On Postgres a verb runs at REPEATABLE READ and a topology verb at READ COMMITTED. | Read, `dialects.py:420-421`, `:476-504`. |
| The statement budgets have one home: `membership_budget`, `chunked`, `rows_per_statement`, `statement_budget` and `bulk_insert`. | Read, `dialects.py:541-548`, `:573-630`, `:673-724`. |
| SQLAlchemy is imported by the database adapter, by `models/rows.py` and `models/vector.py`, and by the two named storages. No module of the kernel imports it. The lint lets four modules import the adapter. | Run, a search of `src/vfs`. Read, `tests/lint/test_code_shape.py:39-42`. |
| On SQLite an attempt runs in a task its caller's cancellation does not enter. A task started inside an attempt copies the attempt's mark. | Read, `attempts.py:97`, `documentation/maintainers/cancellation.md`. |
| No work in `src/vfs` starts on a timer of its own. The statistics pass is started by a write, and expired trash is removed when a caller runs `sweep`, whose cutoff reads `datetime.now(UTC)` in place. | Read, `engine.py:449-462`, `trash.py:388`. |
| `BEGIN IMMEDIATE` on a connection that has attached a second database locks that database too. A second connection's write to the attached file was refused `database is locked`. | Run, `probe_sqlite_files.py`, step 2. |
| Two files, two connections: while the mount's writer was held, a write to the sibling was served. | Run, the same probe, step 3. |
| A SQLite connection creates its file when it is opened, before any statement. Two engines that were built and never connected created no file. | Run, `probe_sqlite_files.py` step 1, `probe_vfs.py` step B. |
| A second engine on `knowledge.db-kernel` in WAL, beside a live mount on `knowledge.db`, left four side files while open. After its dispose and the kernel's close the directory held `knowledge.db` and `knowledge.db-kernel`, and nothing else. | Run, `probe_vfs.py` step D. |
| A SQLite mount whose file is read-only serves a read, and refuses a write with `vfs.unavailable`, retryable. It serves a read when its directory is read-only too. | Run, `probe_readonly.py`. |
| SQLAlchemy gives a SQLite file a queue pool and `:memory:` a pool of one connection. It reads `file::memory:?cache=shared&uri=true` as a file. | Run, `probe_vfs.py` steps B and G. Read, `drivers.py:124-127`, `:145`. |
| `UPDATE … RETURNING`, an upsert with a `WHERE` on the update, and `DELETE … WHERE key IN (SELECT … ORDER BY … LIMIT)` compile for both dialects and ran on SQLite. Two connections handed out 2, 3, 4, 5, 6, 7 with no repeat. | Run, `probe_statements.py` and `probe_sqlite_files.py` step 5. |
| A task started with `context=contextvars.Context()` does not see its starter's context variables. Python 3.11 is the floor. | Run, `probe_vfs.py` step F. Read, `pyproject.toml:19`. |
| A read issues 4 statements and a one-file write 21 on SQLite and 17 on Postgres, as a named principal. | The study, `research.md:48-53`. |

## The problem

The kernel keeps nothing. Eight specs each need a row that outlives a call: what a session saw, where a turn ended, a job that waits for an answer. Three facts decide where such rows can live.

- **On SQLite they cannot be in the mount's file.** The study shared the file and 12 of 19 flushes failed after the five-second lock wait, the buffer grew to 2,360 rows, and claims timed out and refused the writes they guarded (`research.md:13`). With a file of its own no flush failed.
- **A read cannot write them itself.** One synchronous row for each call turned a SQLite read into a writer: during a batch its median went from 70 ms to 856 ms (`research.md:15`). The reference deployment refuses any design where a read waits on a writer.
- **A record cannot join the mount's transaction.** A storage commits inside its own method, a change may land on a mount that is not the root, and on SQLite the record is in another file. So "with the change" has to mean something other than one transaction, and every spec that writes a record beside a change has to know exactly what.

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
| The kernel opens sessions on `storage.engine` | Rejected. That engine is the storage's, and it is there "for listeners alone" (`backend.py:191-198`). On SQLite it is the wrong file, and a third-party storage has none. |
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
- A place whose URL is of another dialect raises `ValueError` when the store is built, naming both dialects and never the URL, as `url_of_engine` does (`drivers.py:78-94`). A `DatabaseStorage` on the generic floor returns `None`, so it never raises.
- It is not a capability. `capabilities()` is a set of verbs that the gate reads, and a record is reached by no verb.
- `RecordPlace` is exported from `vfs` and `SupportsRecordPlace` from `vfs.storage`, because the docs export refuses a public signature that names a type no exported name reaches (`documentation/maintainers/how-we-name.md`, "Public and private").

Reason: an optional protocol is how a storage already says what is not a verb (`SupportsHolds`, `SupportsClose`). A URL is the smallest thing a storage can give that lets one implementation serve every storage.

### 4. On SQLite the place is a second file beside the mount's, named with `-kernel`

For a storage on a SQLite file, `record_place` is the storage's own URL with `-kernel` appended to its database, so `knowledge.db` gives `knowledge.db-kernel` in the same directory. The URL's query is kept. The storage's `engine_arguments` are not: a `creator` or a `pool` made for the mount's file would hand the store the wrong file. The label is the sibling's path as text. The schema is `None`, also when the storage names a schema, which on SQLite is an attached database.

| Case | What happens |
|---|---|
| The file | Made at the store's first use, by SQLite, when the first connection opens. A file system that keeps no record never opens one, so it makes no file. |
| Journal mode and settings | WAL, `synchronous = FULL`, `busy_timeout = 5000`: the SQLite profile's own settings (`dialects.py:368-381`), sent by the same code. The vector extension is not loaded. |
| `ATTACH` | Never used. A mount's `BEGIN IMMEDIATE` locks an attached database for the whole of a batch, which is the defect the second file removes. |
| `:memory:` | Decision 6. |
| `file::memory:` with `uri=true` | `record_place` is `None`. SQLAlchemy reads that URL as a file, so a name made from it would be a real file beside nothing. |
| A read-only mount file in a directory that can be written | The mount serves reads. The sibling is made and records are kept. |
| A sibling that cannot be made or written | The store is unavailable. A row written behind is held and in the end dropped, by decisions 14 and 15, a synchronous call raises `KernelStoreUnavailable`, and one `WARNING` names the path. The store does not fall back to memory. A file system on read-only media keeps its records by taking an in-memory root and mounting the database beneath it. |
| `close()` | The sibling stays. Its `-wal` and `-shm` files are removed, as the mount's are. |
| A deleted sibling, with no process using it | Safe. Sessions are forgotten and waiting jobs are gone. Nothing in the mount's file refers to the sibling. |

Reason for a second file: the study's finding, and probe step 3 beside step 2. Reason for the name: SQLite's own side files are the database's name with a suffix, so `knowledge.db*` matches the mount's file and everything that belongs with it. Reason against a fallback to memory: a failure to open a file can be passing, and a process that silently kept its jobs in memory would save a job that no other process can resume.

### 5. On Postgres the place is the mount's database and schema, on a pool of the store's own

For a storage on Postgres, `record_place` is the storage's URL, its schema, and its `engine_arguments` without `pool`. The label is the schema's name, or "the default schema" when none is set.

- **The same database and schema.** The tables sit beside the mount's. Their names begin with `vfs_kernel_`, `vfs_session` or `vfs_job`, and no mount table's name does. A lint holds both halves.
- **A pool of its own.** The store builds a second engine. Its pool has the class and the size of the mount's, because both come from the same arguments. A `pool` object the application made belongs to one engine and is left out, and the store's pool is then SQLAlchemy's default.
- **READ COMMITTED, with no pin.** A counter and a claim must read what a rival committed while they waited for its row lock. The topology verbs take the same isolation for the same reason (`dialects.py:492-504`).
- **Every supported major version, 15 to 19.** The store issues `CREATE TABLE`, `INSERT … ON CONFLICT`, `UPDATE … RETURNING`, `DELETE … WHERE … IN (SELECT … LIMIT)` and `pg_advisory_xact_lock`. None is newer than Postgres 9.5. It needs no extension and does not probe for pgvector.
- **The role.** First touch makes the tables, so it needs `CREATE` on the schema once, as the mount's first touch does. Where the serving role may not create tables, the first record call of a role that may makes them.
- **A listener on `storage.engine` is not on the store's engine.** What reaches both is `engine_arguments`: `async_creator`, `connect_args`, the pool's size.

Reason for the schema: the study put the log in the mount's schema and found nothing waited (`research.md:107`). Reason for a pool of its own: it is the configuration that was measured, a second engine with the same pool defaults (`research.md:29`). A flusher that drew on the mount's pool would wait behind a storm of batches, which on Postgres already waits 30 seconds for a connection (`research.md:142`). The size follows the mount's because a call's store transaction and its mount transaction never overlap, so the store needs one connection for each change in flight and one for the flusher, which is what the mount's pool was sized for.

### 6. A root in memory keeps its records in a second database in memory

A storage whose URL SQLAlchemy gives the pool of one connection returns `RecordPlace.in_memory()`. That is the test `merge_engine_arguments` already uses (`drivers.py:145`), and `InMemoryStorage` meets it. The store then has a private in-memory database of its own, with its own connection and its own turn lock. A store transaction never takes the mount's turn, and a verb never waits behind a flush. The records end when the store is closed or the process ends.

A file system whose records are in memory, and which holds a mount whose storage names a durable place, logs one `WARNING` on `vfs.kernel_store`, at the first record it writes:

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

The remedy on SQLite is "close every process that uses it and delete the file {path}". On Postgres it is "drop the tables in schema {schema} whose names begin with vfs_kernel_, vfs_session or vfs_job".

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
- A driver failure that escapes the retry, retries that run out, a pool that gives no connection, a refused first touch and a closed store each raise `KernelStoreUnavailable`. Its `error` is classified by the core's `classify_failure` with the context `kernel store`, or is first touch's refusal. The kinds are the ones that exist: `vfs.unavailable`, `vfs.unavailable.backend`, `vfs.unavailable.schema` and `vfs.internal`. Retries that run out are `vfs.unavailable` and retryable, and not the `vfs.conflict` a mount's write answers, because no precondition of a caller's is stale. The error names no path. A closed store answers `vfs.unavailable.backend` with "the filesystem is closed", the kernel's own words (`base.py:3069-3071`).
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

A record exists only if its change landed. A landed change may lack its record. This form is for a record that can only be made from what the change returned, or whose absence errs toward a refusal or a second read. Two specs take it. Spec 3 stores the stamps a change leaves this way (its decision 8, "A read writes its stamps behind, and a change writes them with the change", step 7). Spec 5 stores its change rows this way (its decision 4, "A session writes its change rows after the change commits, by spec 0's record-after form, before the verb returns"), because the etag after a change is not known before it, and a claim left in doubt could not be put back. One `record_after` takes one `fn`, and that `fn` may write the rows of both specs, so a change through a session costs the store one transaction for its stamps and its change rows together.

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

Reason for two transactions everywhere: on SQLite the record is in another file, on any engine the change may be on another mount, and a storage commits inside its own method. A promise of one transaction that held only for a Postgres root could not be tested on the other shapes, and specs would lean on it. Reason for `record_after` out of reach: the window between the two commits is then a crash's width and not a cancellation's.

### 11. A counter is a column that one statement adds to and returns

```python
async def next_number(self, transaction, counter: Column[int], *where: ColumnElement[bool], count: int = 1) -> int
```

It issues `UPDATE <table> SET <counter> = <counter> + :count WHERE <where> RETURNING <counter>`, inside the caller's `commit`, and returns the last number of the block. The block is the `count` numbers that end there. A column that starts at 0 hands out 1 first. When no row matches it raises `LookupError`, so the owner makes the row first, in the same `commit`, with an upsert that does nothing on a conflict.

- The counter is a column on the row that owns the sequence. A session's row holds the counter of its turn numbers, and spec 4's statement S3 is this statement (its decision 4, "`start_turn` stores the turn at once, takes its number from the session's counter, and returns the turn id"). No counter is shared by the whole store. A sequence that only one process at a time can advance needs no `next_number`: spec 8 keeps its journal's counters in the line record, which the holder of the job's claim alone writes (its decision 9).
- Two processes never get the same number. On SQLite one writer holds the file. On Postgres the second update waits for the first one's row lock and then reads the committed value, at READ COMMITTED.
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
- `upsert_rows` sorts the rows by `key`, cuts them by `rows_per_statement` under the same budget, and issues one `INSERT … ON CONFLICT (key) DO UPDATE SET …` for each chunk. An empty `update` makes it `DO NOTHING`. It returns how many rows it inserted or updated, so an insert that did nothing says so. With `newest`, the update carries `WHERE excluded.<newest> >= <table>.<newest>`, so an older row never replaces a newer one. Two rows with one key in one call raise `ValueError`, because Postgres refuses a statement that would update one row twice.
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
- **A read verb's whole dealing with the store is `put_behind`.** So a read adds no synchronous statement, and it does not wait for one.
- **Kinds.** The kernel registers each kind once, when it is built. A second kind of one name raises `ValueError`, and so does a `put_behind` of a kind that was not registered.
- **Rows that share a key become one row.** When a kind has a `key`, a row put behind replaces a buffered row of that kind whose key fields are equal, in the earlier row's position. A kind's `key` is the conflict key of its upsert.
- **The task.** The store has one background task. It starts at the first `put_behind`, on the running loop, with `context=contextvars.Context()`, and is named `vfs-kernel-store`. It does not copy its starter's context, so it carries no attempt's mark and no call's context variables.
- **A flush.** The task takes up to `FLUSH_ROWS`, which is 1,024, from the head of the buffer. It groups them by kind, in the order the kinds were registered, hands a keyed kind its rows sorted by key, and runs every kind's `write` in one `commit`. Each `write` uses decision 12's helpers, so each statement is under the parameter cap whatever the batch.
- **When it flushes.** It flushes while the buffer holds anything, and then waits for the next `put_behind`, `drain` or `close`. There is no row count to reach and no timer. Rows put in one turn of the loop ride one flush. While a flush is in flight the rows that arrive wait for the next, so batches grow with load.
- **Order.** Rows of one kind are written in the order they were put, keyed rows excepted, which are sorted. Kinds are written in the order they were registered, so a kind that needs another kind's row is registered after it. The store promises no order between a row written behind and a synchronous write. A kind that is written both ways makes its upsert monotone with `newest`, on a counter.
- **A loop that changes.** The task belongs to the loop of the first `put_behind`. A `put_behind` on another loop starts the task there, and the buffer goes with it. This is the case of `VirtualFileSystem.wrap` (`sync.py:138-148`).
- **A cancelled call.** The task is the store's and no caller's cancellation reaches it. A read that is cancelled before its storage answers puts nothing.
- **A process that dies.** It loses the rows in the buffer and the flush in flight: at most `BEHIND_CAPACITY` rows, and in the study at most 258.

Reason for flushing as soon as free: a session used in the next request, by another process, must find what this one saw "a moment after each read". A flush that waited for 256 rows would hold a quiet session's rows until `close`, and a timer would put a clock in every test. Reason for one buffer and one task: it is what the study measured.

### 14. The buffer is bounded, drops its oldest rows when full, and holds only records that may be dropped

`BEHIND_CAPACITY` is 16,384 rows. When a `put_behind` would pass it, the oldest rows are dropped until the buffer fits, and `KernelStore.dropped` counts them. One call that puts more than 16,384 rows keeps its last 16,384.

**Every record written behind may be dropped. A record that may not be dropped is never written behind.** It is written with `commit` or `record_after`, and decision 10 says what its failure leaves. So a kind is written behind only when losing a row errs toward a refusal or a second read: a stamp from a read (spec 3, decision 8), a session's use (spec 2, decision 17, "Every call through a handle reports one use, written behind, and a row is touched at most once in five minutes"), the trim of a session's stamps (spec 3, decision 15).

Reason for the oldest: after an outage the rows that land are the newest, which are the ones a session acts on next. Reason for a bound in rows: a row of a record is a few short columns, bounded by its column widths, so 16,384 rows is about 16 MB at ordinary widths, by estimate. The bound guards against rows piling up while the store cannot be written. It is not a limit on a call: the store's capacity is the flusher's, estimated at about 30,000 rows a second on a SQLite file by `probe_flush.py`. A byte budget, through `vfs.batching`, is the direction if a kind with wide rows appears.

### 15. A failed flush keeps its rows when a retry can clear the failure, and drops them when none can

Every log record of the store goes to the logger `vfs.kernel_store`.

- **A failure a retry can clear.** The store cannot be reached, its writer is held past the retry budget, a connection is lost. The rows go back to the head of the buffer. The task waits for the next `put_behind`, `drain` or `close` and tries again. The first failed flush after a good one logs one `WARNING`: "the kernel store at {label} could not be written ({cause}); records written behind are held in memory, and the oldest are dropped past {capacity}". The first good flush after a failure logs one `INFO`: "the kernel store at {label} is written again after {n} failed flushes; {m} records were dropped".
- **A failure no retry can clear.** An integrity error, a statement defect, a value over the engine's cap, a store of another format. The batch is dropped and counted. One `ERROR` is logged, "a flush of {n} records to the kernel store at {label} can never land ({cause}); they are dropped", except for a store of another format, which has decision 8's one `WARNING`.

Reason: a short outage should cost no row, as it cost none in the study (`research.md:101`). A batch that can never land would otherwise block the head of the buffer until every row behind it was dropped.

### 16. `drain` waits for the records of one scope

```python
async def drain(self, scope: Hashable | None = None) -> None
```

It returns when every row put behind before the call, under that scope, has been written or dropped. With no scope it waits for every row. When nothing of the scope is waiting it returns at once and sends nothing. When the flush that carries one of those rows fails, it raises `KernelStoreUnavailable`. A caller that is cancelled while it waits loses no row: the flush goes on.

A change that must read what its own session wrote behind calls `drain` with the session's scope first, or reads those rows where they wait with decision 24's `waiting_behind`. Either is allowed to a change. A read does neither.

Reason: a session reads a file and edits it in the next call, in one process. The stamp may still be in the buffer. Waiting for one scope's rows costs no statement of its own, since the flush was going to run, and it does not wait behind another session's backlog.

### 17. Expired records are removed by a counted sweep in bounded chunks, and a record past its expiry reads as absent before it is swept

```python
Sweeper = Callable[[KernelStore, Transaction, datetime, int], Awaitable[int]]

def register_sweeper(self, name: str, sweep: Sweeper) -> None
async def sweep(self) -> int
```

- **Expiry does not depend on the sweep.** Every read of a table that expires filters on its expiry against `store.now()`. The sweep only gives the space back.
- **A sweeper.** A spec that owns a table with an expiry registers one, in the order parents and dependents need. It is handed the store, a transaction, the pass's one reading of the clock, and a limit. One call removes at most `limit` rows in all, in the `commit` it is given, and returns how many. It removes a parent only when its dependents are gone. Its statements are `delete_expired` and decision 25's `delete_where`, and decision 26 gives the common case ready-made.
- **A pass.** For each sweeper in turn, the store calls it in a `commit` of its own with `SWEEP_CHUNK`, which is 5,000, until a call removes no row or `SWEEP_CHUNKS_PER_PASS`, which is 8, have run. A sweeper that works in smaller batches than its limit is therefore called again while it still finds work. A pass that fails logs one `WARNING` and ends, and the next pass starts over.
- **When.** The store counts its committed write transactions in this process: each flush, each `commit`, each `record_after`, and not the sweep's own. A pass is due after the first 64, and after every 1,024 from then on. The store's task runs it. Between two chunks the task flushes whatever the buffer holds, so a sweep delays a flush by one chunk at most. No pass runs at `close`.
- **By which process.** Any process, on its own count. No process leads. Two passes at once remove each row once: on SQLite they take turns on the sibling's writer, and on Postgres the second waits a chunk for the first one's row locks and then finds the rows gone.
- **By hand.** `sweep()` runs one pass now and returns the rows removed. It is what a test calls.

Reason for a count: no work in VFS starts on a timer today, and a count is what a test can assert. Reason for 64 and then 1,024: a process that lives for a few hundred calls still sweeps once, and a long one spends one indexed probe for each sweeper in about a thousand writes. Reason for 5,000: it is the chunk the study measured, 21 ms a chunk at the median on SQLite and 67 ms on Postgres (`research.md:118`).

### 18. Every time comes from one clock that a test replaces

`KernelStore(place, *, clock=…)` takes a function that returns an aware UTC `datetime`, and by default the system's. `store.now()` calls it, and `store.clock` can be assigned. Every time a record stores and every expiry it is compared with is a bound parameter from `store.now()`. No statement of the store names the engine's own clock. `tests/support/kernel_store.py` gives a clock that a test steps forward.

Two processes compare an expiry one of them wrote with the other's clock. Their clocks differ by seconds and the lifetimes are a day and a month. A time is stored for display and for expiry only, as the overview rules.

Reason: a test of expiry that waited for time to pass would read a clock, and a statement that read the engine's clock could not be stepped.

### 19. `close` flushes the buffer, ends the task and disposes the store's engine, inside the kernel's own close

`AsyncVirtualFileSystem.close()` closes the store as one more target of the gather it already runs (`base.py:569-573`), within the same `close_timeout`, beside the storages and not after them.

1. The mount table is emptied first, as today, so a later verb is refused.
2. The store stops taking rows. A `put_behind` after this is dropped and raises nothing. A `query`, `commit` or `record_after` after this raises or returns `vfs.unavailable.backend`.
3. The task flushes until the buffer is empty. A flush that fails ends the flushing, the rows left are dropped, and one `WARNING` says how many. A failed flush is not raised from `close`, since every such row may be dropped.
4. The task ends. It is awaited and never interrupted, so no interrupt is left pending on a connection.
5. The engine core is disposed. An error here is raised with the storages' errors, alone or in the group.

- A store that was never used has no engine and no task, and its close does nothing.
- A close that is cut short, by its timeout or by a cancellation, keeps the store, as it keeps a storage (`base.py:559-565`). `KernelStore.close()` can be called again, and a second `close()` finishes it. On SQLite a flush in flight ends its statement first, which is at most one `busy_timeout`.
- A durable store keeps its records. An in-memory store loses them, with the jobs that were waiting.
- On SQLite the directory then holds the mount's file and the sibling, and no side file of either.

Reason: the store has an engine and a task, and they follow the rule every storage follows. Flushing at close is what makes a short script's last reads reach the next process.

### 20. Many processes share one store, and the synchronous face adds nothing of its own

**Two calls in one process.** Each `commit` is a transaction of its own on a connection of its own. On a SQLite file the second waits for the sibling's writer, in memory it waits for its turn, and on Postgres it waits only for a row the first one wrote. Rows that two calls put behind sit in the buffer in the order they arrived.

**Many processes.**

- First touch is serialized by decision 8, and a rival's meta row is harmless.
- A counter, an upsert and a sweep are correct under rivals by decisions 11, 12 and 17. A deadlock between two flushes on Postgres is retried by the core.
- On SQLite every process shares the sibling's one writer. A flush holds it for one batch, a `commit` for its statements, a sweep for one chunk. A process that finds it held waits as any SQLite writer does.
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
    async def close(self) -> None
```

`vfs.kernel_store` exports `KernelStore`, `KernelStoreUnavailable`, `BehindKind`, `Sweeper`, `Transaction`, decision 26's `expiry_sweeper` and the constants. The members that decisions 24 to 26 add are in the listing above. It is documented on a Maintainers page and carries no compatibility promise.

A spec that keeps a record follows eight rules.

1. Its table is added to `build_kernel_tables`, its name begins with one of `KERNEL_TABLE_PREFIXES`, and the landing adds one to `KERNEL_FORMAT_VERSION`.
2. Its statements are in a module of `vfs.kernel_store`, never in `vfs.base` or `vfs.session`.
3. A read verb calls `put_behind` and nothing else of the store.
4. Every stored time and every expiry compared comes from `store.now()`, and every read of a table that expires filters on the expiry.
5. Many rows are written with decision 12's helpers, or by a statement of the spec's own that decision 25 admits.
6. A record written beside a change names its form, record after or claim before.
7. A kind's `key` is its upsert's conflict key, and a kind that is also written synchronously passes `newest`.
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
- **`discard_behind`** takes rows out of the buffer and returns how many. A row of the flush in flight is not withdrawn, and is stored. A kind that is also written synchronously therefore still passes `newest` (decision 13).
- **The cost** is the rows of that scope, or the keys given. The store keeps, for each scope, the keys it holds in the buffer, which it needs for `drain` already.
- **No callback is offered.** The store does not tell a submitter when a row is stored or dropped. A second table kept in step by callbacks is a copy that can drift from the buffer, and the buffer can be read.
- **A deferred task is a kind.** A task that must run behind, after rows, is a kind whose row names the task and whose `write` runs its statements. Its `key` is what the task is for, so many requests for one thing become one run. It is registered after the kind whose rows it follows, so it runs after them in the same flush. It may be dropped, as any row may.
- **One flush is one transaction, and its `info` lasts that long.** Every `write` of a flush receives the same `Transaction`. SQLAlchemy gives it a dictionary, `transaction.info`, which begins empty and ends with the transaction. A function that several kinds call in one flush keeps what it found there. A retry starts a new transaction with an empty one.
- **The order of the kinds** is one tuple in the kernel's constructor. With the nine specs built it is: spec 3's stamps (its decision 8), spec 3's trim (its decision 15, "A session's stamps are bounded at 16 MiB, and the earliest turns go first"), then spec 2's use (its decision 17).

Who uses them: spec 2's removal drops what this process has queued for the session before it frees the name (its decision 22, "Removal frees the id in one commit and reclaims the rest in bounded chunks"). Spec 3's change takes its paths out of the waiting rows, and reads a stamp that is still waiting without a statement (its decision 8, steps 2 and 7). Spec 4's rewind and fork call `drain` first (its decisions 12 and 17).

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

- **Several specs' functions run in one `commit`.** `fn` hands its `transaction` to each. The rewind's steps R2 to R5 are four specs' statements in one transaction (spec 4, decision 12). A line's stop writes spec 7's job row and spec 8's pages together (spec 8, decision 9, "`vfs_job_replies` holds a journal as pages of at most 1 MiB, appended at each stop"). A function that takes "the store, or a transaction of it" takes the `Transaction`.
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

Who uses it: spec 7 sweeps `vfs_jobs` with `vfs_job_pages.job_id` as its dependent (its decision 36, "A waiting job lapses `job_lifetime` after it stopped, 24 hours by default, and the sweep removes it"), and spec 8's `vfs_job_replies.job_id` joins that tuple (its decision 9). Spec 2's sweep is not this shape. Its two passes are two sweepers of its own (its decision 22).

Reason: two specs asked for a sweep arm that takes a table, its expiry column and a dependent table. Written once, the order of dependents before parents cannot be got wrong twice.

### 27. Each need the other eight specs state on the store is met by a named member, or is answered here

Read from each spec's "Builds on" at `59946f0d`. Specs 1 and 6 state none.

| Spec, and what it asks | Where it is met |
|---|---|
| 2: a store for every root storage, with `vfs_sessions` made in it | Decisions 2 and 6. The table is added to `build_kernel_tables` (decision 8). |
| 2: a synchronous path, a writer transaction on SQLite, READ COMMITTED on Postgres, one exception, the two budgets | `commit` and `KernelStoreUnavailable` (decision 9), decision 5, `parameter_budget`, `membership_budget`, `row_chunks`, `key_chunks`. |
| 2: a writer that keeps one use for each session | A kind whose `key` is the session's owner key and id (decision 13). |
| 2: the writer calls `resolve` at each flush, once for each session, before any other spec's rows | Not the writer, which knows no session. Each kind's `write` calls `resolve` on the flush's one transaction before it writes, and `resolve` keeps what it found in `transaction.info` (decision 24). See "Needs no other spec meets yet", item 1. |
| 2: `settle` and `discard` for one session | `drain(scope)` (decision 16) and `discard_behind(kind, scope=…)` (decision 24). |
| 2: a sweep that calls its two passes and can stop between chunks | Two sweepers (decision 17). The task flushes between two calls. |
| 2 and 4: plain reads that do not wait on the store's writer, and a way to count statements | WAL and `query` (decisions 4 and 9); a listener on `store.engine` (decision 22). |
| 3: a submit that issues no statement and does not wait | `put_behind` (decision 13). |
| 3: a waiting row replaced by a later one of its key, and withdrawn by its key | A keyed kind (decision 13), and `discard_behind(kind, keys=…)` (decision 24). |
| 3: the writer tells the submitter when a row is stored or dropped | Not offered. `waiting_behind` gives the rows not yet stored or dropped (decision 24). See item 4 below. |
| 3: a flush at a declared count of rows and after a declared delay of a second or less | Neither exists. The task flushes as soon as it is free (decision 13), so the window is one flush, which is shorter than what was asked. |
| 3: a drain on both faces, and a `close` that drains | `drain` (decision 16) and decision 19. The store's `drain` is private and `async`. A public name for it is not added here. See item 5 below. |
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
| 8: a sweep that calls its orphan statement | `vfs_job_replies.job_id` as a dependent of spec 7's `expiry_sweeper` (decision 26). See item 3 below. |
| 2, 3, 4, 7, 8: the same on a root storage in memory | Decision 6. |

Reason: each of the eight was written without sight of this spec, and each named what it needed in its own words. One table shows that no need was left to be met by an invention at build time.

## Cost

Costed against the reference deployment in the working agreement. A store transaction is counted as the study counted: cursor statements, with SQLite's explicit `BEGIN` among them and no `COMMIT`.

**Per verb call, about 150,000 a day.** A read through a session adds no synchronous statement and awaits nothing of the store. Its rows ride a flush: one transaction with one statement for each kind present. At the peak of 20 calls a second, three in four of them reads, that is at most 15 flushes a second, and fewer as load makes batches. A flush of one row took 0.5 ms on a SQLite file of its own, and one of 1,024 rows about 30 ms, on a laptop whose `synchronous = FULL` does not force the disk. Those are an estimate from `probe_flush.py` and not a test. A call with no session and no job touches the store not at all.

**Per file write, about 1,050,000 a day.** Only a write that carries a record pays. The nightly million and the day's machine writes carry none. A write through a session, about a quarter of the verb calls and so about 37,500 a day, adds one store transaction when it records after and two when it claims before, which is the study's "an effect adds exactly two". That is 5 to 10 store transactions a second at the peak. The study measured the time of two such transactions on Postgres under 32 writing sessions: a one-file write's median moved from 188 ms to 338 ms (`research.md:77`). This spec inherits that cost and does not measure it again. A `drain` adds no statement of its own.

**Per index visit, about 11,000,000 a day.** Nothing. The index reads and writes no kernel table.

**Per batch, 100 a night.** A batch with no session adds nothing. A 10,000-entry write through a session is one store transaction of `ceil(10,000 / floor(32,700 / columns))` statements: 2 for a row of 5 columns and 5 for a row of 15.

**Per corpus.** Nothing is done for each file. A sweep is for each expired row: one statement for each 5,000. The study reclaimed 150,000 rows in 31 statements, in 1.2 s on SQLite and 2.0 s on Postgres.

**Per lock.**

| Question | Answer |
|---|---|
| What is locked on SQLite | The sibling file's one writer. Never the mount's file. |
| Who holds it, and for how long | A flush, for one batch of at most 1,024 rows. A `commit`, for its statements, which for a 10,000-row record write is about a third of a second by the estimate above. A sweep, for one chunk of 5,000 rows, 21 ms at the median and 202 ms at most in the study. First touch, once for each process. |
| Who waits | Another writer of the store: a flush, a record write of a change, a sweep chunk, in this process or another. |
| Who does not wait | Every read, list, glob, grep and search of every mount. Every write that carries no record. Every writer of the mount's file, for the store's sake. Every `query` of the store, since WAL serves a reader beside the writer. |
| What is locked on Postgres | The rows a statement writes, and at first touch one advisory lock for the length of that transaction. No table lock is taken. |
| In memory | The store's own turn lock, on its own connection. A verb takes the mount's, which is another. |

A read never waits on the store, because a read never calls it. The longest hold is a batch's record write, which queues other record writers and no reader.

**What decisions 24 to 26 add.** `waiting_behind` and `discard_behind` issue no statement and cost the rows of one scope in memory. `expiry_sweeper` is one statement for each dependent and one for the parents in a call, each with the same few binds. A statement of fixed binds costs the store one statement at any size, and holds the SQLite store's writer for as long as it runs; the spec that owns it costs that hold against its own bound.

**Connections.** On Postgres a process holds two pools on the root's database, each of the mount's size: by default 5 kept and up to 15 at a peak, each. A store that is not used opens none.

**Memory.** The buffer holds at most 16,384 rows, about 16 MB at ordinary widths.

**First touch.** Once for each process and store: the file settings, a look for the meta table, one read of its row.

## Left as it is

- **No session, job, stamp, turn or change is built.** Specs 2 to 8 own them. This spec registers no kind and no sweeper.
- **The action log.** It will be a kind and a sweeper of this store, on this file. Its completion, which the study says is retried and never dropped, is a record that may not be dropped, so by decision 14 it is not written behind. How it is retried, and what bounds the backlog while the store cannot be written, is the action log's spec.
- **One transaction for a change and its record on a Postgres root.** The study names it and did not measure it (`research.md:158`).
- **The store sharing the mount's pool on Postgres.**
- **An engine shared by several storages**, which `a-storage-owns-its-engine-well` leaves to a later spec.
- **The session settings sent at every checkout on SQLite.** The store's connections pay them as a mount's do, until that spec's decision 1 lands.
- **A store tied to its mount's identity.** A mount's file that is deleted and made again beside an old sibling meets stamps of entries that no longer exist. They match nothing, so the worst that follows is a refusal and a second read.
- **A named storage that is not the root keeping the records.**
- **A file system carried across `fork`.** Its buffer would be copied, as its engines would.
- **The time of the trash.** `sweep_rows` keeps reading the system clock.

## Tests

Each is written and seen failing before the code. A count is of cursor statements recorded by a `before_cursor_execute` listener on `store.engine`, of rows read back, of files in a directory, of log records, or of an exit status. None reads a clock. Two seams are added through the adapter's `seam` (`seams.py:41-52`): `kernel-store:before-commit`, inside `commit` and `record_after` before the commit is sent, and `kernel-store:before-flush`, in the task before it takes a batch. *Both engines* means a SQLite file and the Postgres leg behind `VFS_TEST_POSTGRES_URL`; every other test runs on a SQLite file and in memory.

Landing 1, `tests/storage/database/test_core.py`:

- `test_a_core_opens_no_connection_when_it_is_built`: 0 `connect` events, and 0 files in the directory.
- `test_a_core_without_the_vector_function_loads_no_extension`: 0 probes for the vector function in a checkout.
- `test_the_engine_host_is_an_engine_core`: the members of decision 7 are the host's own. The suite of `tests/storage/database/test_engine.py` passes with no edit.

Landing 2, `tests/storage/test_record_place.py`:

- `test_a_sqlite_storage_names_the_file_beside_its_own`: the database is the path with `-kernel`, `durable` is true, the arguments are `None`, and 0 files exist after the property is read.
- `test_a_path_with_a_question_mark_keeps_it`: `notes?v2.db` gives `notes?v2.db-kernel`.
- `test_an_in_memory_storage_names_a_place_in_memory`: `durable` is false.
- `test_a_memory_url_read_as_a_file_names_no_place`, and `test_a_storage_on_the_generic_floor_names_no_place`: `None`.
- `test_a_postgres_storage_names_its_own_database_and_schema`: the URL and schema are the storage's, the arguments carry `pool_size` and not `pool`. No connection is made.
- `test_a_label_never_holds_the_password`.
- `test_a_place_of_another_dialect_is_refused_when_the_store_is_built`: a `ValueError` that names both dialects and not the URL.

Landing 3, `tests/kernel_store/test_store.py`:

- `test_a_file_system_that_keeps_no_record_makes_no_file`: a write, a read and a close on a SQLite root leave exactly one file, and the store's engine saw 0 connections.
- `test_first_use_makes_the_sibling_in_wal_with_its_format`: the sibling exists, its journal mode is `wal`, and its meta row holds `KERNEL_FORMAT_VERSION`.
- `test_close_leaves_the_sibling_and_no_side_file`: the directory holds exactly `knowledge.db` and `knowledge.db-kernel`.
- `test_a_store_commit_is_served_while_the_mount_writer_is_held`: a mount write is held at the `write:before-apply` seam and one `commit` returns, counted as 1.
- `test_a_mount_read_returns_while_the_store_writer_is_held`: a rival holds the sibling's writer, and a `read`, a `grep` and an `edit` with no session each return, counted as 3 results.
- `test_two_stores_touch_one_place_first_together`: both are ready and the meta table holds 1 row. Both engines.
- `test_a_store_of_another_format_is_refused_and_named`: the raise carries `vfs.unavailable.schema` with `found` and `expected`, the detail names the remedy, and a file `read` still succeeds. Both engines.
- `test_a_query_is_not_a_writer`: on SQLite its transaction begins with `BEGIN` and 0 `BEGIN IMMEDIATE`.
- `test_a_commit_behind_a_held_writer_gives_up_after_four_tries`: with each checkout's `busy_timeout` at 0, 4 `BEGIN IMMEDIATE` and one `KernelStoreUnavailable` that is retryable.
- `test_a_closed_store_answers_as_the_closed_kernel_does`: kind `vfs.unavailable.backend`, detail "the filesystem is closed".
- `test_next_number_has_no_repeat_and_no_gap_under_two_stores`: two stores take 50 numbers each at once, and the 100 are exactly 1 to 100. Both engines.
- `test_a_block_of_numbers_ends_at_what_is_returned`: `count=5` after 7 returns 12.
- `test_next_number_on_no_row_raises`.
- `test_insert_rows_stays_under_the_parameter_budget`: 10,000 rows of 5 columns with the budget narrowed to 1,000 go in 50 pages of at most 200 rows, counted by cursor events on SQLite and by a spy on the driver's `copy_records_to_table` on Postgres. Marked `slow`. Both engines.
- `test_upsert_rows_chunks_sorts_and_keeps_the_newest`: 10,000 rows under the same budget are 50 statements of at most 1,000 binds, with keys in order; a second call with lower `newest` values changes 0 rows, and one with higher changes 10,000. Marked `slow`. Both engines.
- `test_an_upsert_that_names_a_key_twice_is_refused`.
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
- `test_records_in_memory_beside_a_database_mount_warn_once`: 1 `WARNING` on `vfs.kernel_store` at the first write, 0 at the second.
- `test_close_closes_the_store_within_the_close_timeout`, `test_a_close_cut_short_keeps_the_store_for_a_second_close`, and `test_a_store_that_fails_to_close_joins_the_storages_errors`: counted as closes and as errors in the group.
- `test_no_verb_shows_a_kernel_table`: after 3 records are written, `tree("/")`, `glob("**")` and the `/.vfs` listing return the rows they returned before, counted.
- `test_a_session_cannot_reach_the_kernel_store`: no public attribute of `AsyncSession` or `Session` is or returns a `KernelStore`.

Landing 3, `tests/test_sync.py`:

- `test_the_facade_closes_the_kernel_store`: 3 rows put behind through the facade's kernel are in the sibling after `close()`, the directory holds 2 files, and no `vfs-sync-loop` thread is left.

Landing 4, `tests/kernel_store/test_behind.py`:

- `test_put_behind_sends_nothing_before_it_returns`: with the task held at the `kernel-store:before-flush` seam, the store has issued 0 statements when `put_behind` returns; released and drained, the rows are there.
- `test_the_task_runs_in_a_context_of_its_own`: a context variable the putter set is unset inside the kind's `write`, counted as 1 observation.
- `test_rows_put_in_one_turn_ride_one_flush`: 300 rows are 1 writer transaction, and 3,000 are 3.
- `test_rows_with_one_key_become_one_row`: 50 puts of one key send 1 row.
- `test_keyed_rows_reach_the_writer_sorted`, and `test_kinds_flush_in_the_order_they_were_registered`.
- `test_a_full_buffer_drops_its_oldest_and_counts_them`: with a capacity of 8 and the task held, 12 puts leave `dropped == 4` and the newest 8 are written.
- `test_a_flush_stays_under_the_parameter_cap`: 10,000 rows of a 15-column kind are 10 flushes, and no statement binds more than the budget. Marked `slow`. Both engines.
- `test_a_failed_flush_keeps_its_rows_and_the_next_put_sends_them`: 3 rows stay, 1 `WARNING` is logged, and after one more put 4 rows are written and 1 `INFO` is logged.
- `test_a_flush_that_can_never_land_drops_its_batch`: 1 `ERROR`, `dropped` grows by the batch, and a later batch is written.
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
- `test_a_pass_stops_after_eight_chunks`: 60,000 expired rows lose 40,000 in 8 statements, and a second pass takes the rest. Marked `slow`.
- `test_a_pass_is_due_after_64_writes_and_then_every_1024`: counted as calls of a sweeper after 63, 64, 1,087 and 1,088 commits.
- `test_two_passes_at_once_remove_each_row_once`: two stores remove 2,000 rows between them. Both engines.
- `test_a_flush_runs_between_two_chunks`.
- `test_a_sweeper_with_small_batches_is_called_until_it_finds_nothing`: a sweeper that removes 100 rows a call is called 4 times for 300 expired rows.
- `test_an_expiry_sweeper_removes_dependents_before_parents`: 3 expired parents with 4 dependent rows each, and 1 live parent with 2. A call with a limit of 5 removes 5 dependent rows and 0 parents. The calls that follow remove the other 7 and then the 3 parents. 1 parent and 2 dependent rows are left, and no call removes more than 5. Both engines.
- `test_an_expiry_sweeper_binds_the_same_values_at_any_size`.

Lint, `tests/lint/test_code_shape.py` and `tests/models/test_kernel_rows.py`:

- Every kernel table's name begins with one of `KERNEL_TABLE_PREFIXES`, and no table of `build_vfs_tables` does.
- `vfs.kernel_store.store` is the one new name in `ADAPTER_IMPORTERS`, and `vfs.kernel_store` has a rung.
- Under `src/vfs/kernel_store/` one line reads the system clock, the default of `clock`.
- `vfs.base`, `vfs.session`, `vfs.sync` and `vfs.sync_session` import no SQLAlchemy, and `vfs.storage.protocol` imports none at run time.

## Scope

In, by landing:

1. `src/vfs/storage/backends/database/core.py` (new), `engine.py`, `tests/lint/allowlist.py` for the lowered count.
2. `src/vfs/storage/protocol.py`, `src/vfs/storage/__init__.py`, `src/vfs/__init__.py`, `src/vfs/storage/backends/database/backend.py` for the property.
3. `src/vfs/models/kernel_rows.py` (new), `src/vfs/kernel_store/__init__.py` and `store.py` (new), one function in `attempts.py`, `src/vfs/base.py` for the construction and the close, `tests/lint/test_code_shape.py` for the rung and the importer, `tests/support/kernel_store.py` (new).
4. `src/vfs/kernel_store/behind.py` (new).

The docs: `documentation/maintainers/kernel-store.md` (new) with landings 3 and 4, `documentation/maintainers/cancellation.md`, `documentation/reference/python-api/storage.md`, and the docstrings in `sqlite.py`, `postgres.py`, `memory.py`, `backend.py` and `base.py`.

`base.py` is held at 3,090 lines and grows by the store's construction and its close, so its entry is raised by that count, as the write preconditions raised it.

Out: every table but `vfs_kernel_meta`, every public method of a session or a job, the action log, and everything under "Left as it is". The Postgres leg is run before the branch's pull request, by the `db_test` skill.

## What the docs must say

- **`documentation/maintainers/kernel-store.md`, new.** What the store is and why it is one for each file system. Where it lives on each engine. The two transactions and the two forms of decision 10, with both tables. The writer, what it drops and when. The sweep and the clock. The eight rules of decision 22. That it is private.
- **`documentation/maintainers/cancellation.md`.** `record_after` runs out of its caller's reach and is not marked, and why.
- **The docstring of `SQLiteStorage`.** A file system whose root is this storage keeps its sessions and jobs in a second file, the path with `-kernel`, made when the first is kept. The two are deleted and backed up together.
- **The docstring of `PostgresStorage`.** The kernel's tables are in the same schema, on a second pool of the same size, and a listener put on `storage.engine` does not reach it.
- **The docstring of `InMemoryStorage`.** Sessions and jobs are in memory too, and end with the process.
- **The docstring of `DatabaseStorage.record_place`,** and the Storage reference page under "Writing a Storage Backend", for `RecordPlace`.
- **The docstring of `AsyncVirtualFileSystem.close`.** It writes what the file system had not yet written about its sessions, and then releases the store.
- **`documentation/tutorials/keep-your-files-in-a-database.md` is not changed.** Its last step says `vfs.db` is the only file to remove (`:96`), and that stays true, because the tutorial keeps no record. A test holds it.

A docstring changes, so `scripts/docs.sh check` runs before the pull request.

## Earlier decisions this reverses

- **The study's flusher waited for 256 rows.** This one flushes as soon as it is free, because a session's rows must reach another process without a later row to push them. Criterion 2 of roadmap story H0, "the 256th adds exactly one insert carrying 256 rows", no longer describes the writer, and H0's spec restates it.
- **Criterion 6 of story H0 reclaims "in chunks of `membership_budget`".** The sweep's chunk is 5,000 rows, the size the study measured, by a statement that binds no key list and so meets no parameter cap.
- **Roadmap story H0's rule iv puts the log in the root mount's storage.** The storage names the place and the kernel's store keeps the rows. On SQLite that is D67's second file.
- **`EngineHost` "owns one mount's database connectivity".** The connectivity becomes `EngineCore`, and the host is what a mount adds to it.
- **This spec's first draft named the record of what a session changed as the case for the claim-before form.** Spec 5 writes that record after the change (its decision 4), and decision 10 now says so. The claim-before form's case is a job's step.
- **This spec's first draft ended a sweeper's turn when a call removed fewer than 5,000 rows.** Decision 17 now ends it when a call removes none, so a sweeper with smaller batches finishes its work.
- **`documentation/maintainers/cancellation.md` says "nothing but the storage makes a session, a connection or a transaction on the engine".** That stays true of the storage's engine. A file system now has a second engine, the store's, which a listener on `storage.engine` does not reach.

## Choices for the owner

Each is decided above, and the decision stands until it is ruled on.

1. **The sibling's suffix is `-kernel`.** Others: `-records`, or a name before the extension.
2. **The store has a pool of its own on Postgres,** of the mount's size. The other choice is the mount's pool: no second set of connections, and a flusher that can wait behind batches.
3. **No argument names another storage for the records.** A root in memory keeps them in memory, and warns once when a database is mounted beneath it. The other choice is `VirtualFileSystem(records=…)`.
4. **A store of another format is refused, never reset.** A reset would be kinder while the design is unreleased, and would end waiting jobs without a word.
5. **A place that cannot be written is not replaced by memory.**
6. **The sweep runs on a count, 64 writes and then every 1,024, and there is no public call for it.** A deployment of very short processes may want one.
7. **The store is a package of its own, `vfs.kernel_store`, and one of its modules may import the adapter.** The other choice is a package inside the adapter.
8. **The store tells no submitter when a row is stored or dropped.** A caller reads what waits, with `waiting_behind`. The other choice is a callback for each row, which spec 3 asked for.
9. **The store adds no public call that waits for the writer.** `close` flushes. The other choice is a public drain on both faces, for a host whose process ends with each request and does not close its file system.

## Where this spec disagrees with the overview or the guides

1. **`documentation/how-to/interrupt-a-job-and-ask-a-person.md`, "Find Jobs That Are Waiting".** It says "A file system that keeps its files in memory keeps its jobs in memory too". Proposed: "A file system whose root storage is in memory keeps its jobs in memory too, even when a database is mounted beneath the root. To resume a job from another process, make the root storage a database." Evidence: the overview's own ruling, and the default root, which is in memory.
2. **`documentation/how-to/keep-a-session-for-each-conversation.md`, the paragraph that begins "A session is stored in the database".** It says VFS keeps the session "in the database you already run". Proposed: add "On SQLite that is a second file beside your database." Evidence: decision D67 and probe step 2.
3. **The overview's "kept by the storage of the root mount".** This spec reads it as "kept in the place the root storage names". The storage class gains one property and no record logic. No change to the overview's words is proposed.

The first draft listed a fourth: the overview's public names held none of this spec's. Ruling 10 of the reconciliation adds `RecordPlace` and a storage's `record_place` to that list, so it is settled.

## Needs no other spec meets yet

Each is a place where another spec's text, as it stood at `59946f0d`, asks the store for something it gives in another form. None stops this spec from being built.

1. **Spec 2, decisions 14 and 17.** They have the writer call `resolve` at each flush. The writer knows no session. Text needed: "`resolve` keeps the keys it found in `transaction.info`, for the length of the transaction, so a flush that names one session in two kinds reads it once. Each kind's `write` calls `resolve` before it writes. The use is a kind registered after every kind that makes rows, and it resolves with `create=False` only the sessions the flush has not yet resolved."
2. **Spec 2, decision 22.** Its sweep's passes read 100 keys at a time and repeat themselves. Text needed: "Each pass is a `Sweeper` registered with spec 0. One call is one transaction, removes at most `limit` rows and returns the count. Spec 0's pass calls it again until it returns 0. `settle` is `drain(scope)` and `discard` is `discard_behind(kind, scope=…)`, with the session's owner key and id as the scope."
3. **Spec 8, decision 9.** Its orphan statement, `DELETE … WHERE job_id NOT IN (SELECT … FROM vfs_jobs)`, removes any number of rows in one sweep call. Text needed: "`vfs_job_replies.job_id` is added to the dependents of spec 7's `expiry_sweeper`, so a job's pages go before its row, at most `limit` rows a call. Pages whose job is already gone are removed by a second sweeper, `delete_where` with that `NOT IN` as its `where` and the same limit."
4. **Spec 3, decision 8.** It keeps a pending table of its own, fed by a report of each row stored or dropped. No such report exists. Text needed: "The pending table is the writer's buffer. The lookup of step 2 calls `waiting_behind(kind, keys=…)` and then the store. Step 7 calls `discard_behind(kind, keys=…)`. No second table is kept." Its need of a flush after a declared delay is met by a flush with no delay.
5. **Spec 3, decision 8, "How a host closes it".** It has a host call a drain before it answers. The store's `drain` is private. This spec adds no public name for it, because ruling 10's list holds none, and `close` flushes. Text needed, in spec 3, if the owner wants the call: the public name, its twin on the synchronous face, and that it awaits `KernelStore.drain()`.
6. **Spec 7, decision 36.** It registers a table, an expiry column and a dependent table with the sweep. Text needed: "The sweeper is `expiry_sweeper(jobs, key=jobs.c.job_id, expires=jobs.c.expires_at, dependents=(pages.c.job_id,))`, registered with `register_sweeper`."

## Not checked

- **Postgres.** No probe ran on a server. The counter under two processes, a sweep under two processes, and a deadlock between two flushes are read from how READ COMMITTED treats a row a rival changed, and are pinned by tests on the Postgres leg. Postgres 15 to 18 were not run by the study either.
- **The flusher as designed.** The study measured a flusher that waits for 256 rows. A flusher that flushes as soon as it is free was not measured under 32 sessions, and neither was its effect on a read's time.
- **The time a record write adds to a change.** The study's +151 ms on Postgres had a pool of 15 as its first suspect, and no run used a larger one.
- **A loss of power.** The tests of decision 10 end a process between two commits. None cuts the power, so what the two engines keep of a commit that had returned rests on `synchronous = FULL` and on Postgres's own durability.
- **A real `fsync`.** The flush times are from a laptop whose `synchronous = FULL` does not force the disk.
- **A read-only Postgres**, such as a standby. The store cannot be written there, and the result is read to be decision 4's unavailable store.
- **The line counts** `engine.py` falls to and `base.py` rises to.
- **Whether `bulk_insert` needs a change to be called from outside a storage's session.** It takes a session and a table, and is read to need none.
- **The other eight specs after `59946f0d`.** Each was read once, in its "Builds on" and in the decisions cited here, while its writer was revising it. A heading or a number cited here may have moved since.
- **Decisions 24 to 26 on Postgres.** The bounded delete by a row value, the row count of an insert that does nothing, and a dependent's delete through a subquery were compiled for Postgres and run on SQLite. To run: the tests marked *Both engines* that name `delete_where`, `upsert_rows` and `expiry_sweeper`, on the Postgres leg.
- **How long a statement of fixed binds holds the SQLite store's writer** at the sizes specs 3 and 4 allow: a rewind that removes 16 MiB of stamps, a fork that copies 100,000 turns. To run: each on a SQLite file with a second task counting its own `commit` calls served meanwhile.

## One line

The kernel has one store of its own for each file system, in a place its root storage names, which a read writes to only from behind and a change writes to in a second transaction whose every crash point is stated.
