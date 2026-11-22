# A session works in turns, and is rewound or forked at one

This is a draft, written on 2026-11-22 and reconciled the same day with the other eight specs that `agents/2026-11-22-the-specs-for-jobs-and-sessions/overview.md` maps. It is not reviewed, and nothing in it is built. It is spec 4 of the nine. It rests on that overview, on steps 4, 5 and 6 of `documentation/how-to/keep-a-session-for-each-conversation.md`, on the seven studies under `agents/2026-11-22-a-session-is-stored-named-and-forked/research/`, and on the code at `59946f0d`, read and probed on 2026-11-22. Another spec's decision is cited by its number and its heading, as each stood in its first draft.

## The outcome wanted

A chat application handles each message in a new request. At the top of the request it names the conversation and the message, and from then on everything VFS records for that request is filed under that message. When the user edits an earlier message, the application tells VFS once, and the session forgets everything from that message on and nothing before it. When the user branches the conversation, the application names the new conversation, and it starts with what the first one knew at the branch point. The shell is where the last line left it, in the next request and in another process.

```python
session = fs.session(authority, "conv_123")
session.start_turn("msg_5")                 # at the top of every request
session.cli("cd /notes && cat budget.md")   # the next line starts in /notes

session.rewind(before="msg_5")              # the user edited msg_5
branch = session.fork("conv_456", before="msg_4")
```

## Builds on

Each entry gives the state of what is built on, then what this spec takes from it. What no other spec provides yet is listed under "Needs no other spec meets yet".

- **Spec 0, the kernel keeps records of its own.** Drafted.
  - `KernelStore`, by its decision 22 (The interface is private, and this is all of it), and the eight rules that decision gives a spec that keeps a record. Decision 24 here says which form each write of this spec uses.
  - `query` and `commit`, by its decision 9 (The store is used through `query` and `commit`, and a failure is one exception). A `commit` begins as a writer on SQLite and runs at READ COMMITTED on Postgres, which decision 4 here needs.
  - `record_after`, by its decision 10 (A record that goes with a change is written in a transaction of the store's own, after the change or before it, and never inside it).
  - `next_number`, by its decision 11 (A counter is a column that one statement adds to and returns).
  - Its decision 12 (A batch of rows is written in chunked statements through four helpers) allows any other statement that binds a fixed number of parameters. The ranged `DELETE` and the `INSERT ... SELECT` of decisions 12 and 17 here are of that kind.
  - `drain`, by its decision 16 (`drain` waits for the records of one scope). `rewind` and `fork` call it first.
  - `store.now()`, by its decision 18 (Every time comes from one clock that a test replaces).
  - `build_kernel_tables` and `KERNEL_FORMAT_VERSION`, by its decision 8 (The tables are made at the store's first use, and a store of another format is refused).
  - `store.engine`, for a test's `before_cursor_execute` listener.
- **Spec 2, a session is stored, named and forked.** Drafted.
  - `session_key`, and the columns `last_turn`, `turn_count`, `parent_key`, `parent_id` and `fork_turn` of `vfs_sessions`, by its decision 13 (`vfs_sessions` holds one row per session, under a key that is never used twice). That spec asks this one to maintain those five, and decisions 4, 12, 17 and 19 do.
  - `resolve` and `SessionRef`, by its decision 14 (The row is first written by the first record that needs it, through one function, `resolve`).
  - A handle keeps no copy of the key, by its decision 16 (A handle keeps no copy of the row, so every record names its session by owner and id). Every statement here finds the key again.
  - The handle's slots, with `_turn` for this spec, by its decision 3 (The handle holds seven values, and only its current turn ever changes).
  - The rule for a session id and the generator of one, by its decisions 10 (An id is 1 to 255 visible ASCII characters, kept exactly as given) and 11 (A generated id is `ses_` and 26 characters from 128 random bits). `fork` uses both, and decision 3 here takes the first for a turn id.
  - Who owns a session, by its decisions 7 (An anonymous authority owns no session) and 8 (The system authority owns sessions as one owner, and lists every owner's).
  - `SESSION_CHILDREN` and `SESSION_RECLAIM_CHUNK`, by its decision 22 (Removal frees the id in one commit and reclaims the rest in bounded chunks). `remove_turns` of decision 2 here joins that tuple.
  - A session is removed with `fs.remove_session(authority, id)`, by ruling 4 of the reconciliation, and it expires by that spec's decision 18.
  - What a management call does on a closed file system, by its decision 24 (After its file system is closed, a handle answers as the file system does).
  - `builtins-ignorelist = ["id"]` in `pyproject.toml`, in that spec's first landing, by ruling 9. Run on 2026-11-22: `def start_turn(id: ...)` fails `ruff check --select A` without it.
- **Spec 3, the session remembers what it read.** Drafted.
  - `vfs_session_stamps` and its columns `session`, `path` and `turn`, by its decision 4 (The table is `vfs_session_stamps`, one row per session, path and turn).
  - Its liveness test, by its decision 6 (A stamp is stored by one statement shape, and a row whose session or turn is gone stores nothing). That spec asks this one for the turn form of the test, and decision 8 here gives it.
  - The guarded router and the order of a change, by its decision 8 (A read writes its stamps behind, and a change writes them with the change).
  - Its rule for a rewind and a fork, items 4 and 5 of what its "Builds on" asks of this spec: a rewind to before turn `n` removes every stamp of the session whose `turn` is `n` or more, with this process's waiting rows for those turns; a fork copies every stamp whose `turn` is below the fork point. Decisions 12 and 17 here issue exactly those.
  - The bound on that copy, by its decision 15 (A session's stamps are bounded at 16 MiB, and the earliest turns go first).
  - The two refusals, `vfs.conflict.changed` and `vfs.conflict.unread`, by its decision 12. The tests here name them.
  - `Session.cli` runs through the session's guarded router, by its decisions 16 and 17. Decision 10 here adds the shell state to that call.
- **Spec 5, a rewind puts a session's files back.** Drafted, with this spec's first draft read.
  - `files=` and `preview=` on `rewind`, by its decisions 6 (A rewind with files walks the session's change rows newest first and undoes each one) and 12 (A preview returns the same report and changes nothing).
  - The field `files` of `Rewind`, by its decision 11 (The report is a `Result` on a new field of `Rewind`).
  - The order of the file step and the memory, by its decision 10 (A rollback puts back what it can and reports the rest, and only a failure stops the memory from being rewound).
  - `RewindStep`, by its decision 13 (A rewind with files is one step to the policies and one job to an interrupt) and ruling 7.
  - Step R4 of decision 12 here issues no statement, and a fork copies no change row, by its decision 16 (A rewind of the memory alone removes no change row, and a fork copies none).
  - Its change rows name a turn by `turn_number`, and use `make_first_turn` of decision 7 here, by its decision 4.
- **Spec 6, a policy judges each step.** Drafted. None of this spec's four calls is a step. A handle `fork` returns carries the source handle's policies.
- **Spec 7, a job is interrupted and resumed.** Drafted.
  - `cancel_session_jobs(store, session_key, *, from_turn, reason)`, by its decision 35 (A session's delete, its expiry and a rewind cancel its waiting jobs through one call, and a fork takes none).
  - A job row carries `session_key`, `turn_number` and `turn_id`, by its decisions 4 and 7.
  - A resumed job stays in its turn with no handle in memory, by its decision 34 (A resumed job stays in its turn, and what it writes is remembered by its session). So this spec offers no way to put a handle in a stored turn.
- **Spec 8, an interrupted line replays its replies.** Drafted. Its line record holds the directory and the environment a line started with (its decision 3), and a stopped line changes none of its session's shell state (its decision 24). Decision 10 here stores the state when a line ends and never when it stops, which is what that spec asks.
- **The shell speaks bash.** Built, pull request 37. A line runs in a machine that is given a directory and an environment, and reports output and a status.
- **The shell acts as bash where it refused.** Drafted, at `agents/2026-11-22-the-shell-acts-as-bash-where-it-refused/spec.md`. Its line 69 gives `history` bash's non-interactive answer, which is nothing printed and status 0. Decision 9 agrees with it.
- **The shell's module crosses its boundary in binary.** Drafted. It rewrites `crates/vfs-shell-wasm/src/wire.rs`, which decision 10 also changes. Whichever lands second carries the end state across the new wire.
- **Roadmap story F7, as built.** Its criterion 7 is not met, at `context/standards/roadmap.md:685`. Decisions 9 and 10 meet its first half and reverse its second.

## Terms

- **Kernel store.** Where the kernel keeps its own records. In code it is spec 0's `KernelStore`.
- **Session.** VFS's side of one conversation, stored under its owner and its id.
- **Owner key.** The key spec 2 derives from the authority that owns a session.
- **Session key.** The integer `session_key` of a session's row in `vfs_sessions`. It is never used twice.
- **Handle.** The Python object `fs.session(...)` returns. Making one does no I/O.
- **Turn.** One message from the user and everything done in answer to it. A turn partitions a session's records.
- **Turn id.** The name the host gives a turn. It is unique within one session.
- **Turn number.** An integer the store gives a turn when it is made. Numbers rise in the order turns are made. They may skip.
- **Counter.** The column `last_turn` on the session's row. A turn's number is the counter after one is added to it.
- **Started handle.** A handle on which `start_turn` has returned. It holds a turn id and a turn number.
- **Latest turn.** The turn of a session with the greatest number.
- **Live and dead.** A turn is live while it has a row. A record that names a turn number with no row is dead.
- **Stamp.** A session's memory of one path. Spec 3 owns it.
- **Waiting job.** A stored job in the state `interrupted`. Spec 7 owns it.
- **Line.** One call of `cli`: a line of bash.
- **Shell state.** What a session keeps of its shell between two lines. Decision 9 says exactly what.
- **Fork point.** The number below which a fork copies turns.
- **Lineage.** The parent and the fork point recorded on a fork's row.
- **Written behind.** Put in spec 0's buffer and stored a moment after the call returns.

## What the code does today

Read and run on 2026-11-22. The shell facts were run again at `59946f0d` after the extension was rebuilt, with lines that read a file. The scripts are `probe_shell2.py` and `probe_turns2.py` in the session's scratch directory.

| Fact | How it is known |
|---|---|
| A session holds an authority, a closed flag and the file system. It holds no id and no turn. | Read, `src/vfs/session.py:61`. |
| `open_session` returns a new object on each call and stores nothing. | Read, `src/vfs/base.py:655`. |
| `rows.py` defines no session table. No table uses a foreign key. | Run, a search of `src/vfs/models/rows.py`. |
| `Session.cli` takes `cwd="/"` and passes it on. `cd /notes && pwd` prints `/notes`, and `pwd` on the next line of the same session prints `/`. | Run. Read, `src/vfs/session.py:414` and `src/vfs/sync_session.py:364`. |
| `export X=1`, `Y=2` and a function `f` on one line are all gone on the next. `echo "[$X] [$Y]"` prints `[] []`, and `f` is status 127. | Run. |
| A line starts with five exported variables: `HOME`, `LC_ALL`, `PATH`, `PWD` and `TZ`. `PWD` is set from `cwd`. | Run, `export -p`. Read, `src/vfs/shell/host.py:51` and `:222`. |
| After `cd`, `PWD` is exported and `OLDPWD` is not. | Run, `declare -p PWD OLDPWD` prints `declare -x PWD` and `declare -- OLDPWD`. |
| `history` prints `not supported in this shell` with status 1. | Run. Read, `crates/vfs-shell/src/machine/builtins.rs:338`. |
| The machine holds variables, functions, options, a directory and a directory stack while a line runs. | Read, `crates/vfs-shell/src/machine/shell.rs:275`. |
| When a line ends, the machine reports output, requests, a status and the pipeline statuses. It reports no directory and no variable. | Read, `crates/vfs-core/src/shell_binding.rs:215` and `:221`, `crates/vfs-shell-wasm/src/wire.rs:264`, `src/vfs/shell/host.py:253`. |
| A management method of the synchronous face refuses by raising. `add_mount` returns nothing and raises. `grants` and `set_posture` return a `Result`. | Read, `src/vfs/sync.py:709`, `src/vfs/base.py:337` and `:1741`. `Location` is a `NamedTuple`, at `src/vfs/mounts.py:538`. |
| The parity test pairs every coroutine of `AsyncSession` with a twin, and pins their count. | Read, `tests/test_sync.py:246` and `:254`. |
| `how-we-name.md` lists four verbs for a method that acts on a noun: `add` and `remove`, `set`, `update`, `open` and `close`. `start` is not one. | Read, `documentation/maintainers/how-we-name.md:29`. |
| `UPDATE ... RETURNING` is already issued on both engines. | Read, `src/vfs/storage/backends/database/writes.py:981`. |
| The in-memory storage is the SQLite storage over a private database. | Read, `src/vfs/storage/backends/memory.py:1`. |

The statements of decisions 4, 10, 12 and 17 were run on a SQLite file, with SQLAlchemy Core, on SQLite 3.50.4, against a stand-in for `vfs_sessions` with spec 2's column names. "Turn statements" are those that name `vfs_session_turns`, `last_turn` or `turn_count`. A stand-in read and insert took the place of `resolve`.

| Fact | Count |
|---|---|
| `start_turn` of a new id | 4 turn statements: one read, then the counter, the insert and the count in one transaction |
| `start_turn` of an id the session has | 1 statement, a read |
| 32 threads start 16 ids, each id twice at once | 16 turns made, 16 distinct numbers, each id answered with one number to both callers, 2 numbers skipped, and `turn_count` equal to the rows |
| The read of the shell state | 1 statement, served by the partial index |
| A rewind's transaction | 3 turn statements: the turn's number, the removal with 2 binds, and the count |
| The same id started again after a rewind | a new turn with a number above every earlier one |
| A fork's transaction | 4 turn statements: the turn's number, the lineage, the copy with 3 binds, and the count |
| A fork's copy of 100,000 turns | 1 statement with 3 binds |
| A second fork to the same id | the lineage update changes no row |
| The first new turn of a fork whose `fork_turn` is 4 | numbered 5 |

## The problem

A session today is an authority and nothing else, so nothing can be filed under a message, and nothing can be taken back to one.

- **An edit keeps the conversation's id.** A chat client that edits or regenerates sends the same conversation id and a shorter history. Nothing on the wire names a branch (`chat-protocols.md`, sections 4 and 5). A server that guesses the edit by comparing message lists gets it wrong: AG-UI's LangGraph integration misses a regenerate of the first reply and drops an edited message (its issues 2109 and 2154). A server that is not told keeps the old turn: assistant-ui's issue 9758 reports a session that "keeps the original turn after every edit".
- **A session with no partition cannot forget part of itself.** The stamps spec 3 stores would otherwise be one set. After an edit, the session would remember reads that the conversation no longer holds.
- **The shell forgets where it is.** Each request is a new process. The line `cd /notes` is forgotten by the next line, as the probe shows.
- **A branch needs a second session that starts with the first one's memory.** Without a copy, the branch's first change to a file is refused as unread.

## Decisions

### 1. A turn is a record the kernel keeps, and it adds no primitive

A turn has no path. It is not an entry, and no verb returns one. It is reached through management methods of a session, as a grant is reached through `grants`. A view of turns in the namespace is left out, as the overview leaves out a view of sessions and jobs.

Reason: Article 1 of the constitution allows five first-class things and gives each a path. A turn is a fact about calls, not an object a caller reads or writes.

### 2. `vfs_session_turns` holds one row per turn

```python
turns = Table(
    "vfs_session_turns",
    metadata,
    Column("session_key", BigInteger, primary_key=True),
    Column("number", BigInteger, primary_key=True),
    Column("turn_id", BytewiseString(TURN_ID_MAX), nullable=False),
    Column("shell_state", LargeBinary, nullable=True),
    Column("started_at", _timestamp(), nullable=False),
    UniqueConstraint("session_key", "turn_id", name="uq_vfs_session_turns_id"),
)
Index(
    "ix_vfs_session_turns_state",
    turns.c.session_key,
    turns.c.number,
    sqlite_where=turns.c.shell_state.is_not(None),
    postgresql_where=turns.c.shell_state.is_not(None),
)
```

- The table joins `build_kernel_tables` in `src/vfs/models/kernel_rows.py`, and its landing adds one to `KERNEL_FORMAT_VERSION`. Its statements are in a new module, `src/vfs/kernel_store/turns.py`.
- `session_key` is spec 2's 64-bit key. A turn is named everywhere by that key and its `number`.
- The primary key is `(session_key, number)`. It serves every range this spec reads, removes or copies.
- The unique constraint on `(session_key, turn_id)` is what makes one id one turn.
- `turn_id` is compared byte for byte. `BytewiseString` pins `COLLATE "C"` on Postgres, and SQLite's default is bytewise already. `TURN_ID_MAX` is 255.
- `shell_state` is null while no line of the turn has changed the state. Decision 10 says what it holds.
- `started_at` is `store.now()` when the turn was made. It is shown by `turns()`. Nothing orders by it and nothing compares it.
- There is no foreign key. No table in the tree has one.
- The table has no expiry of its own and so no sweeper. Its rows go with their session. `remove_turns(session, session_key, limit) -> int` deletes at most `limit` turns of one key and returns the count: `DELETE FROM vfs_session_turns WHERE session_key = :k AND number IN (SELECT number FROM vfs_session_turns WHERE session_key = :k ORDER BY number LIMIT :limit)`. It joins spec 2's `SESSION_CHILDREN`, and is called with `SESSION_RECLAIM_CHUNK`.
- A row holds no count of stamps, changes or jobs. Those tables name the turn. The turn does not name them.
- A session has no cap on its turns. A row is at most 255 bytes of id, and holds a state only when a line changed it. Nothing prunes a live session's turns. They go with the session, which expires 30 days after its last use. The direction, if a session of very many turns is ever measured to matter, is to fold turns older than a declared age into one row. It is not built.

Reason: the overview gives this table four things to hold, and an order must be a counter and never a clock. A partial index keeps the read of decision 10 to one probe however many turns ran no line.

### 3. A turn id is 1 to 255 characters with no control character, and VFS makes one when none is given

The first draft admitted any character that is not a control character. The rule is now spec 2's rule for a session id, so that the guide's one sentence about an id is true of both.

- A turn id is a `str` of 1 to 255 visible ASCII characters, `0x21` to `0x7E`: spec 2, decision 10 (An id is 1 to 255 visible ASCII characters, kept exactly as given). It holds no space, no control character and nothing outside ASCII.
- An id is compared exactly. It is not trimmed, folded or normalized.
- An id need only differ from the other turns of the same session.
- Any other value is refused with `vfs.invalid` before any statement runs. The detail is `a turn id is a string of 1 to 255 visible ASCII characters`.
- With no id, VFS makes one: `turn_` followed by 8 characters drawn with `secrets.choice` from `0123456789ABCDEFGHJKMNPQRSTVWXYZ`. That is 40 random bits.
- A made id that the session already has is found by decision 4's insert, which then inserts no row. A new id is made and the insert runs again, up to `TURN_ID_ATTEMPTS`, which is 4. After that the call raises `vfs.internal`.
- An id VFS made is an id like any other. The host passes it back to carry the turn on.

Reason: the ids come from other systems. Vercel's `generateId` makes 16 alphanumerics, AG-UI and LangGraph make UUIDs, and message ids read `msg_...` (`chat-protocols.md`, section 1). The rule admits all of them, and one rule for both ids is one thing to learn. A made id is random because a name made from a clock collided within one second in the OpenAI Agents SDK (`framework-session-stores.md`, section 4). It is short because the unique constraint, not its length, keeps it unique.

### 4. `start_turn` stores the turn at once, takes its number from the session's counter, and returns the turn id

```python
async def start_turn(self, id: str | None = None) -> str: ...
```

The statements, in order. `:o` and `:i` are the owner key and the session id of the handle's `SessionRef`.

```sql
-- S1, in a query
SELECT t.number
FROM vfs_sessions s
JOIN vfs_session_turns t ON t.session_key = s.session_key AND t.turn_id = :t
WHERE s.owner_key = :o AND s.id = :i AND s.expires_at > :now

-- one commit
-- S2  resolve(session, [ref], create=True, ...) gives the session key :k, making the row when there is none
-- S3  store.next_number(session, vfs_sessions.last_turn, session_key = :k) gives :n
-- S4
INSERT INTO vfs_session_turns (session_key, number, turn_id, started_at)
SELECT :k, :n, :t, :now
WHERE NOT EXISTS (SELECT 1 FROM vfs_session_turns WHERE session_key = :k AND turn_id = :t)
-- S5, only when S4 inserted a row
UPDATE vfs_sessions SET turn_count = turn_count + 1 WHERE session_key = :k
-- S6, only when S4 inserted no row
SELECT number FROM vfs_session_turns WHERE session_key = :k AND turn_id = :t
```

- When S1 finds the turn, the call returns. Nothing is written.
- With a made id, S1 is not issued, and S4 is the check that the id is new.
- Otherwise S3 takes the number. The update locks the session's row, so two processes that start turns in one session run S3 one after the other, and each reads a different counter.
- S4 inserts the turn unless the session has the id by then. The loser of a race inserts nothing, reads the winner's number with S6, and is in the winner's turn. Its own number is skipped.
- S5 keeps `turn_count` equal to the session's rows. It runs only for a turn that was made.
- The handle then holds the id and the number, and no key. `start_turn` returns the id.
- The turn is stored when `start_turn` returns. A turn in which nothing else happens still has its row.
- `resolve` refreshes the session's time of last use by its own rule (spec 2, decision 17).

The cases:

- **Two processes, two ids.** Two turns, two numbers. Which is lower is the order of their S3.
- **Two processes, one id.** One turn. Both return the id, and both handles hold the same number.
- **A crash or a cancel inside the commit.** The transaction is rolled back. The counter, the count and the table are as they were.
- **Postgres.** A `commit` runs at READ COMMITTED, so the second transaction's S4 takes its snapshot after it has waited for the first to commit, and sees the first's row. The unique constraint is the backstop: an `IntegrityError` on it is read as "the session has this turn", and S6 runs.
- **The in-memory store.** One connection, and every transaction takes its turn on it.
- **The synchronous face.** `Session.start_turn` is the twin, through the management hop.
- **The system authority and an anonymous caller.** The system authority owns sessions and starts turns in them. An anonymous authority owns no session, so no handle exists to call this on (spec 2, decisions 7 and 8). `start_turn` judges no right to any file.

Reason: a number from a clock or from `max(number) + 1` can be taken twice. A counter updated under the row's lock cannot. A skipped number costs nothing, because a number is an order and never a count, and the count is a column of its own.

### 5. Starting a turn the session already has carries it on, and a removed turn starts again as a new one

- `start_turn` with an id the session has makes no second turn. It is one read, at any number of calls, from any process.
- This holds for an earlier turn too. With `msg_4` and `msg_5` stored, `start_turn("msg_4")` puts the handle in `msg_4`. Nothing is removed, and `msg_5` stays. What the handle then records names `msg_4`'s number. Where a stamp of an earlier turn lands when a later turn already holds the path is spec 3's decision 5 (One stamp per path is current, and a new one replaces it unless it is the same file at the same or a lower version).
- After `rewind(before="msg_5")`, `start_turn("msg_5")` finds no such turn and makes one, with a number above every number the session has given out.
- `start_turn` never rewinds. No call of VFS infers an edit from the ids it is shown.

Reason: a turn often spans several requests, and a request is sometimes sent twice. Both must be harmless. A late request for an earlier message does happen: a tool's result for `msg_4` can arrive after `msg_5` has started. Inferring an edit is what the studied servers got wrong.

### 6. The turn is on the handle, and the store holds no current turn

- `session.turn` is a property that does no I/O. It is the id of the turn the handle is in, or `None` on a handle that has started none.
- The handle holds the turn's id and its number in `_turn`, the slot spec 2's decision 3 leaves for it.
- Two handles of one session hold their own turns. One may be in `msg_4` while another is in `msg_5`.
- A call takes the handle's turn when the call begins. A `start_turn` on the same handle part-way through a long call does not move that call.
- The session's row has no column for a current turn. `last_turn` is the last number handed out, and names no turn a handle is in.
- This is the one fact a handle holds that the store does not: which of the session's turns this request is working in.

Reason: two requests on one session must not fight over a pointer. A stored pointer would be written by every `start_turn` and read by every call. A resumed job would then file its work under whichever turn was current, not the one it started in. A second device would move the first one's records to its own message. The request already knows its message, so the request carries it. The OpenAI Agents SDK kept its current branch in one object's memory and no parent on the row, and a new process was back on `main` (`framework-session-stores.md`, section 4). Here the lineage is on the row, and what stays in memory is only what each request is told again.

### 7. A handle with no turn files each record under the session's latest turn, found when the record is written

- A call through a handle that has started no turn does not look a turn up. A read verb therefore issues no statement.
- Each record such a call leaves names its turn with one subquery, inside the statement that writes the record:

  ```sql
  (SELECT max(number) FROM vfs_session_turns WHERE session_key = :k)
  ```

- When the session has no turn, that subquery is null and the writing statement inserts nothing. The writer then calls `make_first_turn(session, session_key) -> int` and writes again. `make_first_turn` is S3, S4 and S5 with a made id, and its insert is guarded by "the session has no turn", so two writers make one first turn.
- A record that also shows the turn's id, as a job's row does, calls `latest_turn(session, session_key) -> Turn | None`, one read by the primary key.
- The handle stays without a turn. Its next record is filed under whatever turn is latest then.
- The first turn VFS makes has a made id. The host learns it from `turns()`.

The cases:

- **A read through such a handle.** The stamp is written behind and is filed at the flush. No statement runs during the read.
- **A turn starts between the read and the flush.** The stamp is filed under the newer turn. A rewind to before that turn then forgets the read. The cost is one refusal as unread and a second read.
- **A rewind lands between the read and the flush, in another process.** The stamp is filed under the latest turn that is left, and the session remembers one read the rewound conversation no longer holds. Spec 3 asks this spec to close that case. It is not closed, and "Needs no other spec meets yet" says why. In the process that rewinds it cannot happen, because a rewind drains first.
- **A change, a line or an interrupted job.** Each writes its record with the change, so the subquery runs in that statement.

Reason: the guide promises that calls made before any turn is started go into the session's latest turn, or into a first turn VFS makes. Looking the turn up on the first call would put a synchronous statement on a read. Resolving at the write keeps the read free.

### 8. A removed turn's number is never used again, and a record that names it is dead

- A rewind removes rows and never lowers the counter. No later turn takes a removed turn's number.
- A record is dead when no row of `vfs_session_turns` has its session key and its turn number. The predicate is:

  ```sql
  EXISTS (SELECT 1 FROM vfs_session_turns t WHERE t.session_key = :k AND t.number = :n)
  ```

- This is the turn form of the liveness test that spec 3's decision 6 asks this spec for. A stamp of a dead turn stores nothing.
- A dead stamp is never honoured. A dead change row belongs to no live turn. Spec 5 still selects it by its number when a later rewind's range covers it (its decision 6), which is safe because the number belongs to nothing else.
- A dead record is removed by the next rewind whose range covers its number, and with its session. No sweep looks for dead records.
- The same holds after a session is removed and its id used again. The new session has a new key, and the old handle's turn number has no row under it.
- A read through a handle whose turn was removed is served. Its stamp is dead.
- A change through a handle whose turn was removed is refused with `vfs.not_found`, and nothing is dispatched. The detail is `turn 'msg_5' was removed by a rewind; nothing was changed`. The check is one more selected column on the statement spec 3 issues at step 2 of a change. Where spec 3 issues none for a call, that call is not checked.
- A handle with no turn has no turn to check. Its records go to the latest live turn, by decision 7.

Reason: a rewind cannot wait for every process. A stamp that another process put behind before the rewind arrives after it, and a call that was running goes on recording. Were the number used again, that late record would belong to a new turn. Because it is not, a late record belongs to nothing. The refusal of a change exists because the alternative misleads: with its stamps dead, a strict session would refuse the change as unread, the agent would read again, and that stamp would be dead too. opencode's refusals that hid the cause produced "up to 295 consecutive failures" (`coding-agent-sessions.md`, section 7).

### 9. A session keeps its shell's working directory and its exported variables, and nothing else of the shell

| Part of the shell | Kept | Why |
|---|---|---|
| The working directory | Yes | A new bash process starts where its parent stood. |
| Exported variables, `PWD` left out | Yes | A new bash process inherits its environment. `PWD` is set from the directory. |
| Variables that are not exported | No | A new process does not inherit them. |
| Functions, `export -f` included | No | A function is a parsed body. Keeping it would parse it again on every line. |
| Options, `shopt`, aliases, traps, the directory stack, the positional parameters, `$?` | No | A new process has none of them. |
| History | No | Bash run on a line keeps none, the draft named under "Builds on" gives `history` that answer, and the host keeps the messages. |

- The rule in one sentence: each line of a session is a new bash process, started in the directory where the session's last line ended, with the environment that line had exported.
- `Session.cli` takes `cwd: str | None = None`. `None` starts the line in the session's directory. A path starts the line there, with the session's variables. `VirtualFileSystem.cli` keeps `cwd="/"` and keeps nothing.
- A session with no stored state starts a line at `/` with `ENVIRONMENT`, as today.
- The line starts at the stored path as text. Whether that directory still exists, and whether the caller may still list it, is found by the line's first verb.

Reason: the guide's fork table says a fork copies "the shell's directory and variables". The environment and the directory are what one Unix process hands the next, so the rule needs no list of its own and matches what bash does. A history would be one write of the whole line on every line, on the multiplier that is paid most often, to keep something the host already has.

### 10. The shell state is stored on the turn row when a line ends having changed it, and a line starts from the nearest state at or before its turn

- The state is one value: the UTF-8 bytes of a JSON object, `{"cwd": "/notes", "env": {"HOME": "/", ...}}`, with keys sorted, no spaces, and characters outside ASCII written as themselves. Two equal states are equal bytes.
- **A line starts** with one read, in a `query`:

  ```sql
  SELECT t.shell_state
  FROM vfs_session_turns t JOIN vfs_sessions s ON s.session_key = t.session_key
  WHERE s.owner_key = :o AND s.id = :i AND s.expires_at > :now
    AND t.number <= :n AND t.shell_state IS NOT NULL
  ORDER BY t.number DESC LIMIT 1
  ```

  A handle with no turn reads without the `t.number <= :n` term.
- **A line ends.** When the machine reports that the line ran to its end, it reports its main shell's directory and exported variables. When that state differs from the state the line started with, one statement stores it, through `record_after`:

  ```sql
  UPDATE vfs_session_turns SET shell_state = :state
  WHERE number = :n AND session_key =
        (SELECT session_key FROM vfs_sessions WHERE owner_key = :o AND id = :i AND expires_at > :now)
  ```

  A handle with no turn resolves the session with `create=True`, names the number with decision 7's subquery, and makes the first turn when there is none.
- A line that changes neither the directory nor an exported variable writes nothing.
- The state is stored before `cli` returns, so the next request reads it.
- **Nothing is stored** when the line did not parse, when a budget, the deadline or a cancel ended it, or when it is interrupted and saved as a job. A resumed line stores its state when it ends, in the turn it started in, as spec 8's decision 24 (A resumed line runs as its caller, in the session and turn it started in, and its stamps cross the stop) needs.
- An update that matches no row stores nothing. That is a line whose turn or whose session was removed.
- **A store that cannot be read** when the line starts refuses the line, with the store's classified error, and nothing runs. A session that cannot find its shell does not guess a directory.
- **A store that cannot be written** when the line ends leaves the result as it is, with spec 0's one warning, of kind `vfs.unavailable`. The line ran, and its result is not lost.
- The machine gains the report. `Status::Done` carries the main shell's directory and exported variables, and `ShellMachine.end_state()` returns `(cwd, [(name, value), ...])`, or `None` for a line that did not run to its end.
- `host.py` gains `ShellState`, a `NamedTuple` of `cwd` and `env`, and `run_line_from(fs, line, authority, state, ...)`, which returns the result and the end state. `run_line` becomes that call with the default state, and returns the result alone, so `fs.cli` is unchanged. `LineResult` gains no field. The two routers spec 3's decision 17 gives `run_line` are passed through as they are.

What follows from the read:

- A later turn starts where the earlier one ended, with no copy made when the turn starts.
- A line in an earlier turn starts from that turn's state, not from a later turn's.
- After a rewind, the state is the state of the latest turn that is left. The rewind writes nothing to restore it.
- A fork's copied rows carry the state with them.

Reason: the overview puts the state on the turn row, as it was when the turn ended. Storing only a change keeps the common line, which changes no directory, to one read. Reading the nearest earlier state lets a rewind and a fork restore the shell by removing or copying rows, with no second rule to keep in step.

### 11. The kept variables are bounded by `SHELL_ENV_BYTES`, and two lines at once leave the state of the one that ends last

- `SHELL_ENV_BYTES` is 32,768. It counts the bytes of the `env` object as decision 10 encodes it.
- When a line ends with more exported than that, the stored state is the line's new directory with the variables the line started with. The result carries one warning of kind `vfs.budget_exhausted.truncated`. Its detail gives the bytes and the bound, and says that the directory was kept and the variables were not.
- The directory is a path, so it is at most `MAX_PATH_LENGTH` bytes, which is 1,024 (`src/vfs/paths.py:41`). A stored state is therefore at most `SHELL_ENV_BYTES` and one encoded path.
- **Two lines at once in one turn.** Each starts from the state stored when it started. Each stores its own end state when it ends, if it changed anything. The state left is the state of the line that ended last, whole. The two are not merged.
- A line that changed nothing never overwrites the state another line stored.
- The conflict mode is last writer wins, and this is the declaration Article 5 asks for.

Reason: Linux bounds an environment too, and a typical one is a few kilobytes. The bound is a budget on one session's shell, not a cap on any corpus. Two bash processes started from one parent do not merge their environments either, and a state write that was refused would have nowhere to go, since the line has already run.

### 12. `rewind(before=turn)` removes that turn and every later one, with their stamps, and cancels their waiting jobs, in one transaction

```python
async def rewind(self, *, before: str, files: bool = False, preview: bool = False) -> Rewind: ...

class Rewind(NamedTuple):
    before: str                   # the turn id given
    turns: int                    # turn rows removed
    jobs: int                     # waiting jobs cancelled
    files: Result | None = None   # spec 5's report; None when files=False
```

`files`, `preview` and the field `files` are spec 5's: its decisions 6, 11 and 12. This decision is the call with `files=False`.

In order:

1. The id is checked by decision 3.
2. `store.drain` is awaited for the session's scope, so that this process's own stamps of the removed turns are stored and then removed.
3. R1, in a `query`: `resolve(session, [ref], create=False, ...)`, then `SELECT number FROM vfs_session_turns WHERE session_key = :k AND turn_id = :t`. It gives the session key and the number `n` of the turn, or decision 14's refusal.
4. One `commit` on the kernel store. It finds the key again, and then:

   | Step | Table | What happens | Owner |
   |---|---|---|---|
   | R2 | `vfs_jobs` | `cancel_session_jobs(session, :k, from_turn=:n, reason=REWIND_CANCEL_REASON)` | spec 7, decision 35 |
   | R3 | `vfs_session_stamps` | `DELETE FROM vfs_session_stamps WHERE session = :k AND turn >= :n`, with this process's waiting rows for those turns | spec 3, item 4 of what it asks of this spec |
   | R4 | `vfs_session_changes` | No statement | spec 5, decision 16 |
   | R5 | `vfs_session_turns` | `DELETE FROM vfs_session_turns WHERE session_key = :k AND number >= :n` | this spec |
   | R6 | `vfs_sessions` | `UPDATE vfs_sessions SET turn_count = turn_count - :removed WHERE session_key = :k`, when R5 removed a row | this spec |

5. If the handle's own turn was removed, the handle has no turn.
6. The call returns a `Rewind`. `turns` is R5's row count and `jobs` is R2's count.

- Steps R2 to R6 are one function, `rewind_turns(session, session_key, n) -> tuple[int, int]`. Spec 5's resumed rollback calls it with the key and the number its job saved (its decision 13).
- `REWIND_CANCEL_REASON` is `The session was rewound to before the turn this job was made in.` A job cancelled this way reads "Cancelled by the system", by spec 7's decision 35.
- R6 is the last statement, so the session's row is locked for the commit alone. `last_turn`, the owner and the lineage are not written.
- `vfs_job_replies` is spec 8's, and goes with its job by spec 8's rule.
- Every statement names the session key and a number. None takes a bind for a row.

Reason: ruling 13 says a rewind restores what earlier turns saw. With a stamp row for each turn that saw a path, removing the rows of the removed turns leaves the earlier turn's stamp, and nothing is rebuilt. One transaction means no reader ever sees a turn without its stamps or stamps without their turn.

### 13. A rewind changes no file, restores the shell by removing rows, and cannot be undone

- A rewind with `files=False` issues no statement to any mount. Every file a removed turn changed stays as that turn left it.
- A file read in a kept turn and changed in a removed one is remembered as it was read. Its etag has moved on, so the session's next change to it is refused with `vfs.conflict.changed` until the file is read again. This is spec 3's rule, working as the guide's table shows.
- The shell state after the rewind is decision 10's read over the turns that are left.
- **The hook for spec 5.** With `files=True`, spec 5's rollback runs after step 3 and before step 4. The turns and their change rows are still stored then. Step 4 runs only when nothing in the rollback failed. If anything failed, the memory is untouched, `rewind` raises with the report, and the same rewind can be asked again: spec 5, decision 10. After step 4, spec 5 moves the stamps of the files it put back: its decision 14.
- **A rollback that a policy interrupts.** Nothing is put back and step 4 does not run. `rewind` returns `Rewind(before, 0, 0, files=<the interrupted result>)`. When the job is resumed, spec 5 runs the rollback and then `rewind_turns`: its decision 13.
- **A preview.** `preview=True` with `files=True` reads and removes nothing: spec 5, decision 12.
- **A rewind cannot be undone.** The rows are deleted, not hidden. A host that wants to keep the old line of the conversation forks first.

Reason: no studied chat protocol or framework rewinds a side effect, and the two coding agents that restored files from snapshots lost other callers' work or filled the disk (`coding-agent-sessions.md`, sections 5 and 7). What a rewind removes is safe to lose: a lost stamp only causes a refusal and a second read. ADK rewinds by appending an event and hiding what came after it from every later read (`framework-session-stores.md`, section 5). Here that would put a filter on every read of a stamp, and keep rows that nothing bounds. opencode's stored revert state was 78% of one 687 MB database (`coding-agent-sessions.md`, section 2).

### 14. A rewind to before a turn the session has not is refused with `vfs.not_found`

- When R1 finds no session row, or no turn with that id, the call raises `NotFoundError`. Nothing is removed or cancelled, and no file step runs.
- The detail is `session 'conv_123' has no turn 'msg_9'; nothing was rewound`.
- A session of another owner under the same id is a different session. The caller's own session has no such turn, and the answer is the same refusal.
- A turn that an earlier rewind removed is a turn the session has not.

Reason: a mistyped id must never pass as a rewind that did nothing. The host would go on believing that the session had forgotten what it still remembers.

### 15. A rewind never waits for a call, a job or another rewind

VFS keeps no record that a call is running, so a rewind has nothing to wait on and takes no lock before it reads.

| Case | What happens |
|---|---|
| A call of a removed turn is running | It runs on. A file it changes stays changed. Its stamps are dead, by decision 8. Its handle's next change is refused. |
| A call of a kept turn is running | Nothing changes for it. Its stamps are filed under its turn and stay. |
| A job of a removed turn is waiting | It is cancelled in R2. A later `resume` of it answers that it was cancelled. |
| A job of a kept turn is waiting | It stays waiting. When it is resumed it runs in its turn, and what it records stays. |
| A job of a removed turn is `running` | It is not touched and finishes, by spec 7's decision 35. If it then stops at an interrupt, it is stored as waiting under a dead turn. "Needs no other spec meets yet" has the rule this needs. |
| Two rewinds at once | Both return. The turns left are those before the earlier of the two points. Each reports the rows its own statements removed, and each lowers `turn_count` by its own. |
| A second rewind whose turn the first has removed | It is refused by decision 14 if it reads after the first commits. Otherwise it removes what is left of its range, which may be nothing. |
| A rewind to before the first turn | Every turn is removed. The session's row stays, with `turn_count` 0. The shell is at `/` with `ENVIRONMENT`. The session has no stamp. The next record makes a first turn, by decision 7. |
| A `start_turn` of a new id at the same time | If it commits first, its turn is in the range and is removed. If it commits second, its turn is kept. |

Reason: the reference deployment refuses a design that makes a call wait on a person's act. A claim written by every call so that a rewind could wait would be a write on every read. The guide tells a host to run one turn of a conversation at a time. Where it does not, each case above ends in a state the next call can read truthfully.

### 16. `fork(id, before=turn)` makes a new session of the same owner under an id that owner has not used

```python
async def fork(self, id: str | None = None, *, before: str | None = None) -> AsyncSession: ...
```

- `id` is checked as `fs.session` checks it, and raises what it raises: spec 2, decision 10. With no id, spec 2's `new_session_id` makes one.
- The new session has the owner of the source. There is no fork to another owner.
- **An id is in use** when the owner's row for it has handed out a turn number or has a parent: `last_turn > 0` or `parent_id` is not null. A row that only `resolve` made holds nothing, and a fork takes it.
- **An id in use is refused** with `vfs.exists`, raised as `WriteConflictError`, and nothing is copied. The detail is `session 'conv_456' already exists; nothing was copied`. Its `data` is `{"parent": ..., "fork_turn": ...}` of the session that is there, so a host that lost the reply to its own fork can recognise it.
- `id` equal to the source's own id is refused with `vfs.invalid`.
- The same id under another owner is no conflict.
- `before` names a turn of the source. A turn the source has not is refused as decision 14 refuses it, and no session is made.
- `before` leaves the named turn out, as a rewind does. There is no argument that keeps it. A fork that keeps every turn passes no `before`.
- The call returns a handle to the new session, made as `fs.session` makes one. It carries the source handle's authority, `strict` and policies. It has no turn.

Reason: a branch in a chat application is a new conversation with a new id, and the host already has that id. Adopting an existing session under the id would hand back a session that may have gone its own way. The OpenAI Agents SDK once accepted an existing branch name and silently merged a second history into it (`framework-session-stores.md`, section 4). The point of a fork is a turn, and never any message id, for the reason ACP moved its fork from a message id to a cursor the agent names: not every message is a position the system can act at (`wire-protocol-sessions.md`, section 4). A turn is a position VFS itself recorded. One `before` serves both a rewind and a fork, where Codex has `beforeTurnId` and `lastTurnId` (`coding-agent-sessions.md`, section 4).

### 17. A fork copies the turns below the fork point, their stamps and their shell state, in statements with a fixed number of binds

In order: the checks, `store.drain` for the source session's scope, then one `commit`.

```sql
-- F1  resolve(session, [source ref], create=False, ...) gives :src, or nothing
-- F2  the fork point :n
SELECT number FROM vfs_session_turns WHERE session_key = :src AND turn_id = :before   -- with before
SELECT last_turn + 1 FROM vfs_sessions WHERE session_key = :src                       -- without
-- F3  resolve(session, [new ref], create=True, ...) gives :new
-- F4  the lineage, and the test that the id is not in use
UPDATE vfs_sessions
SET parent_key = :src, parent_id = :source_id, fork_turn = :n - 1, last_turn = :n - 1
WHERE session_key = :new AND last_turn = 0 AND parent_id IS NULL
-- F5
INSERT INTO vfs_session_turns (session_key, number, turn_id, shell_state, started_at)
SELECT :new, number, turn_id, shell_state, started_at
FROM vfs_session_turns WHERE session_key = :src AND number < :n
-- F6
INSERT INTO vfs_session_stamps (session, path, turn, kind, entry, version)
SELECT :new, path, turn, kind, entry, version
FROM vfs_session_stamps WHERE session = :src AND turn < :n
-- F7
UPDATE vfs_sessions SET turn_count = :copied WHERE session_key = :new
```

- The fork point `n` is the number of the turn `before` names. With no `before` it is the source's `last_turn` plus one, so every turn is copied. A source with no row gives `n = 1`.
- F4 changes no row when the id is in use. The function then raises decision 16's refusal, and the `commit` is rolled back.
- A copied turn keeps its id and its number. A stamp therefore copies as it is. F6 is spec 3's rule and spec 3's columns.
- `fork_turn` and the new session's `last_turn` are both `n - 1`. Every turn the fork took is numbered at or below `fork_turn`, and its first new turn is numbered `n` or above.
- `turn_count` is F5's row count.
- The shell state is copied with the rows, by decision 10.
- A source that has stored nothing gives an empty new session, with `parent_id` recorded and `parent_key` null. F5 and F6 are not issued.
- F5 has three binds at any number of turns. No row comes into Python.
- **The bound on the copy.** F5 copies one row for each turn below the fork point. F6 copies at most the 16 MiB spec 3's decision 15 lets one session hold. The number of turns has no cap, by decision 2, and "Cost" gives what a copy of 100,000 turns holds.
- **A crash or a cancel.** The transaction is rolled back, and the new id has no session.
- **A fork while a call runs.** The copy holds what is committed when each statement runs. A stamp that another process has put behind and not yet stored is not copied. The fork then refuses a change to that file as unread, and one read clears it.
- **A turn in progress.** VFS keeps no record that a turn has ended. A fork with no `before` copies the latest turn as far as it has got. Nothing live comes with it.

Reason: a copy of the session's own records is what every studied system does. A fork that read through its parent would walk a chain on every lookup, and a removal of the parent would break the child. LangGraph's forks are a parent pointer with no branch identity, and its regressions come back to that (`langgraph-threads.md`, section 5). Stamps are safe to copy because each is checked again at the write.

### 18. A fork shares every file and leaves behind every job and every record of a change

| A fork copies | A fork shares | A fork leaves behind |
|---|---|---|
| Turns below the fork point | Every file | Waiting jobs |
| Their stamps | | Change rows |
| Their shell state | | |

- **Files.** There is one file system. A change through either session is seen by the other, whose next write to that file is refused as changed until it reads the file again. Neither has a private copy.
- **Jobs.** No row of `vfs_jobs` is copied or changed, as spec 7's decision 35 says. A job names its session by key, so the fork's `jobs()` is empty, and a resume of the parent's job through the fork is answered as a job that does not exist.
- **Change rows.** No row of `vfs_session_changes` is copied, as spec 5's decision 16 says. A fork's later rewind therefore puts back only files the fork itself changed, never the parent's.

Reason: "A fork() in the road" finds that a fork must say, resource by resource, what it copies and what it shares, because whoever is not told assumes a copy (`history.md`, lineage 5). Every studied agent system shares the files (`forking-files.md`, the survey). A waiting job is a question already put to a person, and a copy would put it twice. ACP's fork starts with no background work, and opencode's copies only settled history (`wire-protocol-sessions.md`, section 4; `coding-agent-sessions.md`, section 4). LangGraph's whole-thread copy must carry a waiting interrupt, and one question can then be answered from two threads (`langgraph-threads.md`, section 4).

### 19. A fork records its parent and its fork point, and nothing reads through them

- The new row holds `parent_key`, the source's key; `parent_id`, the source's id; and `fork_turn`, by decision 17. They are spec 2's columns, written once, by F4.
- The fork point is a number and not a turn id, because an id can be used again after a rewind and a number cannot. This is spec 2's ruling in its decision 13, and the first draft's `fork_before` column is gone.
- Lineage is a record of where a session came from. No lookup of a stamp, a turn or a state follows it.
- **A fork of a fork.** Its parent is the session it was forked from, not the first ancestor. Its copied turns include those its parent had copied, under the same numbers.
- **Removing or expiring the parent** changes nothing in the fork. The fork has its own rows. `parent_key` then points at no row, and `parent_id` still shows the name, which may since have been used for a new session: spec 2, decision 22.
- **Removing the fork** changes nothing in the parent.
- `session.parent` is a property that does no I/O. On the handle `fork` returns it is the source's id. On every other handle it is `None`. It is fixed when the handle is made, as `id` is, and it is never a copy of the row. The handle gains one slot for it, `_parent`.
- The stored lineage of every session of an owner is `SessionInfo.parent`, in `fs.sessions` (spec 2, decision 20).

Reason: opencode keeps a fork's lineage apart from a child's and does not carry a delete into forks. Codex refuses to delete a source that forks still read from (`coding-agent-sessions.md`, sections 3 and 4). A copy needs neither rule. A handle is made with no I/O and keeps no copy of its row, so the only parent a handle can truthfully hold is the one its own `fork` call just recorded, and the listing is the stored read.

### 20. `session.turns()` lists a session's turns a page at a time

```python
async def turns(self, *, after: str | None = None, limit: int = TURNS_PAGE) -> tuple[Turn, ...]: ...

class Turn(NamedTuple):
    id: str
    number: int
    started_at: datetime
```

- The turns come oldest first, by number.
- `limit` is from 1 to `TURNS_PAGE_MAX`, which is 1,000. `TURNS_PAGE` is 100. Any other value is refused with `vfs.invalid`.
- `after` is a turn id. The page holds the turns numbered above it. The next page is asked for with the last row's id. A page shorter than `limit` is the last.
- An `after` that is no turn of the session is refused with `vfs.not_found`. That is a turn a rewind removed between two pages, and the host starts again.
- A session that has stored nothing gives `()`.
- One statement in a `query`, joined to the session's row by owner key and id with its expiry, which fetches at most `limit` rows. It is not a use of the session.
- The name is on the overview's list of public names, by ruling 10.

Reason: the host maps its own message ids by supplying them, so it needs no listing for that. It needs one for the turn VFS made. Calls made before any `start_turn` go into a first turn with a made id, and without a listing the host could never name that turn to rewind before it. Article 2 of the constitution refuses a design that makes a caller guess.

### 21. `start_turn`, `rewind`, `fork` and `turns` return plain values and raise a refusal

This is ruling 5 of the reconciliation: a call that manages the kernel's own records returns a plain value and raises a classified error, and a call that carries out, previews or reports file-system work returns a `Result`.

- `start_turn` returns a `str`, `turns` a tuple of `Turn`, and `fork` a handle.
- `rewind` returns a `Rewind`. Its counts are plain values. Its file report, `Rewind.files`, is a `Result`, and is spec 5's.

| Refusal | Kind | Raised as |
|---|---|---|
| A turn id that breaks decision 3 | `vfs.invalid` | `ValidationError` |
| `limit` out of range, or `fork` to the source's own id | `vfs.invalid` | `ValidationError` |
| `rewind`, `fork` or `turns` naming a turn the session has not | `vfs.not_found` | `NotFoundError` |
| `fork` to an id in use | `vfs.exists` | `WriteConflictError` |
| A made turn id that collided four times | `vfs.internal` | `VFSError` |
| A kernel store that cannot be reached | the kind of `KernelStoreUnavailable.error` | `exception_for_kind` of it, which is `VFSError` |
| A session id given to `fork` that breaks spec 2's rule | none | `TypeError` or `ValueError`, as `fs.session` raises |
| A closed file system | none | `ValueError` on the kernel and `RuntimeError` on the synchronous face, as spec 2's decision 24 has for `exists` |

- Each classified exception carries a `Result` with the one fact, as `MountError` does.
- No new kind is added. Ruling 6 lists the kinds the nine add, and none is this spec's.
- One refusal is not raised. A change through a handle whose turn was removed, in decision 8, is a verb's refusal and is in that verb's `Result`.
- None of the four is a step. No policy of spec 6 is asked about `start_turn`, `turns`, `fork` or a rewind of the memory. A rewind with files is spec 5's `RewindStep`.
- `start` joins the verbs of `documentation/maintainers/how-we-name.md`: "The thing begins, or is carried on when it already has begun, and nothing must be closed", with `start_turn()` as its example. `rewind` and `fork` are bare verbs. `turns` is a plural noun. This spec's first landing carries that line, beside spec 2's amendment of the same page.

Checked against the management methods as they are today: `add_mount` returns nothing and raises, and `grants` and `set_posture` return a `Result`. These four are of the first kind, so nothing departs from the ruling.

Reason: `start_turn` returns an id and `fork` returns a handle, so neither has a `Result` to carry a refusal. Article 2 of the constitution asks for one envelope on every public operation. The mount methods already stand outside it, and each refusal here still carries a classified fact from the closed vocabulary. These calls are made by the host's own code and never by an agent. A failed `Result` from `rewind` that nobody reads is the silent rewind decision 14 exists to prevent.

### 22. A host maps its chat stack to a session and its turns by five rules

1. **The session id is the stack's conversation id, passed as it came.** The same authority and id reach the same session from any process.
2. **The turn id is the id of the user's message being answered.** Every request that belongs to that message starts the same id. Any number of starts make one turn.
3. **An edit or a regenerate is one `rewind` and one `start_turn`.** The rewind is to before the first message the client threw away. VFS never infers it.
4. **A branch into a new conversation is one `fork`,** to the new conversation's id, before the first message not carried over.
5. **Every id a stack makes is accepted as it comes,** when it is 1 to 255 visible ASCII characters.

| Stack | Session id | Turn id | The host rewinds when |
|---|---|---|---|
| Vercel AI SDK | the chat `id` | the id of the last user message in `messages` | `trigger` is `regenerate-message`, or `submit-message` arrives with `messageId` set |
| AG-UI | `threadId` | the id of the last user message in `messages` | its own comparison of `messages` with what it stored finds a shorter or edited list |
| LangGraph | `thread_id` | an id the application gives the run and keeps with its checkpoint | the application goes back to that checkpoint |
| Its own | the conversation's id | the user message's id | the application's own edit path runs |

The table is a contract of VFS in this sense: given the calls each row implies, the session holds the turns the row implies. The tests replay each row as a list of requests and count the turns. The AG-UI row is settled by the reconciliation: its turn id is the user message's id.

Reason: every studied protocol carries a conversation id and a message id, and none carries an edit (`chat-protocols.md`, section 6). AG-UI's `runId` is new for every run, and one message's work spans several runs when a tool's result or an answer to an interrupt comes back as a new run. A turn named by `runId` would be a turn for each of them, and no later request names the first.

### 23. The work is five landings, each green

1. The table, `start_turn`, `turn`, `turns`, `make_first_turn`, `remove_turns` and decision 8's predicate. After spec 0's third landing and spec 2's second.
2. The shell state: the machine's report, the read and the write. After spec 3's second landing, which gives `Session.cli` its guarded router.
3. `rewind(before=)`, with R3 and without R2. After spec 3's second landing.
4. `fork` and `parent`. After spec 3's second landing.
5. The rule for jobs: R2, and the fork's test that jobs stay behind. With spec 7's landing of its job record or after it, whichever is later.

Spec 5's third landing needs the first of these, and its fourth needs the third. `files=` and `preview=` arrive with spec 5's fourth landing.

Reason: each landing is of use alone and leaves the tree green. Between landings 3 and 5 a rewind cancels no job, and until spec 7 lands there is no stored job to cancel.

### 24. Each write of this spec uses one of spec 0's forms, and none is written behind

| Write | Form | Why |
|---|---|---|
| A new turn: S2 to S6 | `commit` | It goes with no change of a file. A store that cannot be written raises, and no turn is started. |
| The shell state at a line's end | `record_after` | It follows a line that has already run. A failure is a warning on the line's result, and a cancelled caller still has the state stored. |
| A rewind: R2 to R6 | `commit` | It is the kernel's own records alone. |
| A fork: F1 to F7 | `commit` | The same. |
| `make_first_turn` | Inside the `commit`, the `record_after` or the flush of the record that needs it | It is called by the writer of a stamp, a change row, a job or a shell state. |
| `remove_turns` | Inside spec 2's reclaim `commit` | It is one of `SESSION_CHILDREN`. |

- Every read is a `query`: S1, R1, the read of the shell state and `turns()`.
- This spec registers no kind with `register_behind` and puts nothing behind. A turn is never dropped, so by spec 0's decision 14 it may not be written behind.
- It registers no sweeper, since its table has no expiry of its own.
- The function a `commit` is given runs again from its first statement on a retry. Each function here reads everything from its arguments and its session, and none keeps a count from an earlier try.
- Every stored time is `store.now()`, and every read through `vfs_sessions` filters on `expires_at`.
- The statements that are not spec 0's helpers each bind a fixed number of parameters.

Reason: ruling 1 of the reconciliation asks every spec that keeps a record to say which of spec 0's forms each write uses. A turn row is the thing other records hang on, so it is committed before the call that made it returns.

## Cost

Costed against the reference deployment in the working agreement. One multiplier is new, and is derived: **per turn**. The table gives 150 verb calls a user a day at about 10 actions a prompt, which is about 15 prompts a user a day and 15,000 turns a day for 1,000 users. That is about 0.5 a second over an eight-hour day and about 2 a second at the peak.

**Per verb call, about 150,000 a day.** This spec adds no statement to any verb, read or write. The turn's number is an integer on the handle. A read through a handle with no turn adds none either, by decision 7.

**Per turn, about 15,000 a day.** A new turn is one read, then `resolve`, the counter, the insert and the count in one transaction: 5 statements when the session's row is there and was used in the last five minutes, and 6 on a session's first record. That is about 75,000 statements and 15,000 small transactions a day.

**Per request.** A request that carries a turn on is one read. If every one of the 150,000 calls were its own request, that is 135,000 reads a day, about 5 a second over the working day and about 20 at the peak, each a probe of two unique indexes.

**Per line.** A line through a session adds one read, of at most one row through the partial index. It adds one update only when the line changed the directory or an exported variable. A line is one of the 150,000 calls a day. The share of calls that are lines is not measured.

**Per file write, per index visit, per corpus.** Nothing. The removal of an expired session's turns is one statement of at most 5,000 rows for each chunk of spec 2's reclaim.

**Per batch.** A 10,000-entry write through a session issues no statement of this spec. Specs 3 and 5 each write their own records, with one turn number for the whole batch.

**Per rewind and per fork.** Each is a person's act. No measurement of how often a user edits or branches exists, and the rate is an assumption. A rewind is one read of two statements, `resolve` and the turn's number, and then one transaction: `resolve`, the cancel, the two removals and the count. A fork is one transaction: two calls of `resolve`, the fork point, the lineage, two copies and the count. No statement of either takes a bind for a row.

**Rows.** 15,000 turn rows a day. A session expires 30 days after its last use, so at least 30 days of turns are live: 450,000 rows or more, each about 100 bytes and its two index entries. A conversation that is used every day keeps all of its rows.

**The locks.**

| Lock | Held for | Who waits | Who does not |
|---|---|---|---|
| The session's own row, taken by S3 | S3, S4, S5 and the commit | Another new turn in the same session, and any write of spec 2 to that row, a touch included | Every read. Every verb call. Every other session. A `start_turn` that carries a turn on. |
| The session's own row, taken by R6 or F7 | The commit | The same callers | The same |
| The new session's row, taken by F4 | The fork's copies and the commit | A second fork to the same id, and a record that makes that id's row at the same moment | Everything else. The id is not yet a session any handle uses. |
| The rows a rewind removes | The rewind's transaction | A flush that writes a stamp of a removed turn of that one session | Everything else |
| The SQLite kernel store's one writer | Each transaction of this spec | Every other writer of the kernel store: a new turn, a flush of stamps, a change row, a saved job | Every read of every kind. Every write to a mount, which is another file. Nobody waits on Postgres. |

- No lock of this spec is held for a batch's body, an index pass or a person's pause. No table lock is taken.
- No read verb waits on any of them, on either engine.
- On SQLite the longest hold is a fork or a rewind of a long session. Measured on a SQLite file, as research and not as a test: a copy of 100,000 turns took 0.09 seconds and their removal 0.07. The copy and the removal of stamps are bounded by spec 3's 16 MiB and were not timed.
- S3 is the first statement after `resolve`, so the row is held for two more statements and the commit. The insert cannot come first, because it needs the number.

**What grows.** The rows a fork copies and a rewind removes grow with the turns of the one session. The statements do not: each has a fixed text and a fixed number of binds. Nothing declared bounds a session's turns, and decision 2 says so with its direction.

**Memory.** A page of `turns()` is at most 1,000 rows. A shell state is at most `SHELL_ENV_BYTES` and one path. Nothing else comes into Python.

## Left as it is

- **No queue and no claim for turns.** Two turns of one session may run at once. VFS does not order them and does not refuse the second.
- **No end of a turn.** A turn is never closed, and nothing records that one has finished.
- **No private view of the files for a fork.** The overview leaves it out.
- **No merge of a fork back into its parent,** and no fork to another owner.
- **No undo of a rewind.**
- **Functions, unexported variables, options, aliases and history between lines.** Decision 9 says why.
- **`OLDPWD`.** The machine does not export it, so `cd -` as a line's first command answers as bash does when `OLDPWD` is not set. Exporting it on `cd` is bash parity and belongs to the shell's own specs.
- **A line with no session.** `fs.cli` starts at `/` and keeps nothing. Spec 3's line session stores nothing either.
- **The rendered hint of `vfs.not_found`.** It speaks of a path. Decision 8's refusal reaches an agent only when a host goes on using a handle after rewinding its turn.
- **A listing newest first,** and the fork point in `SessionInfo`.
- **Turns over MCP.**

## Tests

Each is written and seen failing before the code. A count is of statements recorded by a `before_cursor_execute` listener on `store.engine`, leaving out `BEGIN`, `COMMIT`, `PRAGMA`, `SAVEPOINT`, `RELEASE` and `ROLLBACK`. "Turn statements" are those whose text names `vfs_session_turns`, `last_turn` or `turn_count`. No test reads a clock. Unless a test says otherwise it runs on the in-memory store, on a SQLite file and on the Postgres leg.

`tests/session/test_turns.py`:

- `test_start_turn_stores_one_turn_and_returns_its_id`: 4 turn statements, 1 row, `last_turn` and `turn_count` are 1, and the return value equals `session.turn`.
- `test_starting_a_turn_the_session_has_carries_it_on`: the second start is 1 statement and writes none. The table still has 1 row. The same from a second file system over the same database.
- `test_a_made_id_is_turn_and_eight_characters`: the id matches `^turn_[0-9A-HJKMNP-TV-Z]{8}$`. With the generator patched to repeat an id the session has once, 2 inserts run and 1 turn is made. Patched to repeat it always, the call raises after 4 inserts, and the counter, the count and the table are unchanged.
- `test_two_file_systems_never_take_one_number`: two file systems over one database, 32 starts of 16 ids at once. 16 rows, 16 distinct numbers, `turn_count` 16, and each id answered with one number to both callers. On a SQLite file and the Postgres leg.
- `test_a_turn_id_is_checked_before_any_statement`, parametrized: `""`, 256 characters, an id with a space, with a NUL, with a newline, `café`, an `int` and `bytes` each raise `ValidationError` at 0 statements. 255 characters, a UUID, 16 alphanumerics and `msg_01` are each accepted.
- `test_the_turn_is_on_the_handle`: two handles of one session start two turns and each reports its own. A third handle reports `None`. No column of `vfs_sessions` names a turn a handle is in.
- `test_a_handle_keeps_no_session_key`: a session is removed with `fs.remove_session` and its id used again. A handle made before the removal starts a turn, and the turn is a row of the new key.
- `test_an_earlier_turn_started_again_is_carried_on`: with `msg_4` and `msg_5`, a start of `msg_4` leaves 2 rows with their numbers, and the handle is in `msg_4`.
- `test_a_read_through_a_session_issues_no_turn_statement`, parametrized over `read`, `stat`, `ls`, `tree`, `glob`, `grep` and `search`, with a started handle and with one that has no turn: 0 turn statements before the flush.
- `test_a_ten_thousand_entry_write_issues_no_turn_statement`: 0 turn statements. Marked `slow`.
- `test_a_handle_with_no_turn_files_under_the_latest`: a line through such a handle stores its state on the latest turn's row. On a session with no turn, 1 turn with a made id is made, and a second such line makes no second.
- `test_two_writers_make_one_first_turn`: two file systems, two lines at once on a session with no turn. 1 row, and `turn_count` 1.
- `test_turns_lists_a_page_at_a_time`: 250 turns at `limit=100` come as pages of 100, 100 and 50, oldest first, each turn once, each page 1 statement that fetches at most 100 rows. An `after` that is no turn raises `NotFoundError`. `limit=0` and `limit=1001` raise `ValidationError`. A session that stored nothing gives `()`.
- `test_remove_turns_removes_a_chunk`: 12,000 turns and a limit of 5,000 are removed in calls that return 5,000, 5,000 and 2,000, each 1 statement with 3 binds. Marked `slow`. `test_a_removed_session_has_no_turn_row`: after `fs.remove_session` and one sweep, 0 rows carry the old key.
- `test_a_store_that_cannot_be_reached_raises`: `start_turn`, `turns`, `rewind` and `fork` each raise a `VFSError` whose result holds a `vfs.unavailable` fact.

`tests/session/test_shell_state.py`:

- `test_the_next_line_starts_where_the_last_ended`: `cd /notes` through one handle, then `pwd` through a new handle of the same session, prints `/notes`.
- `test_an_exported_variable_is_kept_and_nothing_else_is`: after `export X=1; Y=2; f() { :; }; alias a=b; set -e`, the next line prints `X` as `1` and `Y` as empty, `f` is status 127, and `$-` holds no `e`.
- `test_a_line_that_changes_nothing_writes_nothing`: 1 turn statement, a read. `test_a_line_that_changes_directory_writes_once`: 2.
- `test_cwd_given_starts_the_line_there_with_the_kept_variables`.
- `test_a_later_turn_inherits_and_an_earlier_turn_keeps_its_own`: `cd /a` in `msg_4`, `cd /b` in `msg_5`. A line in `msg_6` starts in `/b`, and a line through a handle carried on in `msg_4` starts in `/a`.
- `test_variables_over_the_bound_are_not_kept`: an exported value of 40,000 bytes leaves the stored variables as they were, keeps the new directory, and gives 1 warning of kind `vfs.budget_exhausted.truncated`.
- `test_a_line_that_did_not_end_stores_nothing`, parametrized over a line that does not parse, one ended by a loop budget, one ended by its deadline and one cancelled: 0 writes.
- `test_two_lines_at_once_leave_the_last_to_end`: with a seam that holds line A open while line B runs `cd /b` to its end, A then ends after `cd /a` and the stored directory is `/a`. When A changes nothing, it stays `/b`.
- `test_a_store_that_fails_at_a_lines_end_warns`: the line's result is a success with 1 warning of kind `vfs.unavailable`. `test_a_store_that_fails_at_a_lines_start_refuses_the_line`: nothing runs, counted as 0 statements on the mount.
- `test_a_line_with_no_session_keeps_nothing`: 0 statements on the kernel store.
- In `tests/shell/test_host.py`: `end_state()` is `None` before the line ends and after a line a budget ended, and holds the directory and the exported variables after one that ran to its end. In `crates/vfs-shell`, a case that a `cd` inside a subshell is not reported and a `cd` before `exit 3` is.

`tests/session/test_rewind.py`:

- `test_the_guides_rewind`: the guide's steps 4 and 5. The rewind returns `Rewind(before="msg_5", turns=1, jobs=0, files=None)`. An edit of the file read in both turns goes through with no read. An edit of the file changed in `msg_5` is refused `vfs.conflict.changed`. `pwd` prints `/`. The file still holds the edit, and 0 statements ran on the mount's engine during the rewind.
- `test_a_rewind_is_one_read_and_one_transaction`: 3 turn statements, the turn's number, the removal and the count. The removal has 2 binds. The same at 10,000 turns, marked `slow`. `turn_count` equals the rows left.
- `test_a_turn_the_session_has_not_is_refused`: `NotFoundError` whose message holds the turn id, 0 writes. The same for a session that stored nothing, and for a turn an earlier rewind removed.
- `test_a_removed_turn_starts_again_as_a_new_turn`: its number is above every number given before.
- `test_a_rewind_to_before_the_first_turn`: 0 turns are left, `turn_count` is 0, the session still exists, a line starts at `/`, and the next line makes 1 new first turn.
- `test_two_rewinds_at_once`: with a seam between the read and the transaction, both return, the turns left are those before the earlier point, the two counts sum to the turns removed, and `turn_count` equals the rows left.
- `test_a_handle_in_a_removed_turn`: its edit fails with `vfs.not_found` naming the turn, at 0 mutation statements on the mount. Its read is served. A later handle's edit of the file it read is refused `vfs.conflict.unread`. The handle that asked for the rewind reports `turn is None`.
- `test_a_stamp_that_arrives_after_the_rewind_is_dead`: a second file system reads in `msg_5` through a started handle and holds its flush, the first rewinds, the second flushes. The stamp table holds 0 rows of the removed turn, and an edit of that file is refused `vfs.conflict.unread`.
- Landing 5: `test_a_waiting_job_of_a_removed_turn_is_cancelled`, with the reason of decision 12 and `jobs == 1`. `test_a_waiting_job_of_a_kept_turn_stays`, resumed afterwards, with its write remembered. `test_a_running_job_of_a_removed_turn_finishes`.

`tests/session/test_fork.py`:

- `test_the_guides_fork`: `branch.id` and `branch.parent` are `conv_456` and `conv_123`. The branch edits a file the parent read with no read of its own. The parent's next edit of that file is refused `vfs.conflict.changed`. `pwd` in the branch prints the parent's directory, and an exported variable is there. The `fs.sessions` row of the branch has `parent == "conv_123"`.
- `test_a_fork_before_a_turn_holds_the_turns_below_it`: `turns()` of the fork is the source's below the point, with the same ids and numbers, and `turn_count` equals them. A file read only in a later turn is unread in the fork. The fork's next turn is numbered above `fork_turn`.
- `test_a_fork_copies_turns_in_one_statement`: 1 insert into `vfs_session_turns` with 3 binds, at 10 turns and at 10,000, marked `slow`.
- `test_an_id_in_use_is_refused`: `WriteConflictError` of kind `vfs.exists` with the `data` of decision 16, and the source and the existing session are unchanged, rows counted. The source's own id raises `ValidationError`. The same id under another owner forks. An id whose row holds no turn and no parent is taken.
- `test_a_turn_the_source_has_not_is_refused`: `NotFoundError`, and the new id has no session.
- `test_a_fork_of_a_session_that_stored_nothing`: an empty session whose `parent_id` is recorded.
- `test_a_fork_of_a_fork`: its parent is the session it was forked from, and its turns include the first session's.
- `test_removing_the_parent_leaves_the_fork`: the fork's turns and stamps are as they were, and its `fs.sessions` row still shows the parent's id. The same after the parent expires. `test_removing_the_fork_leaves_the_parent`.
- `test_a_fork_that_fails_part_way_makes_nothing`: an error injected between F5 and F6 leaves no session row and no turn row under the new id.
- `test_a_stamp_still_put_behind_elsewhere_is_not_copied`: a second file system's held flush is not in the fork, whose edit is refused `vfs.conflict.unread`. This process's own rows are drained first and are copied.
- `test_the_handle_a_fork_returns`: `turn is None`, `parent` is the source's id, with the source's `strict` and policies. A handle from `fs.session` for the same id has `parent is None`.
- Landing 5: `test_a_fork_leaves_waiting_jobs_behind`: the fork's `jobs()` is empty, the parent's holds 1, and a resume through the fork is refused.

`tests/session/test_chat_mapping.py`, each case a list of requests replayed against one session:

- `test_vercel_tool_round_trips_are_one_turn`: three requests whose last user message is `m2` leave 1 turn.
- `test_vercel_regenerate_rewinds_and_starts_again`: `rewind(before="m2")` and `start_turn("m2")` leave the same ids, with `m2` under a new number.
- `test_vercel_edit_with_a_new_id`: `rewind(before="m2")` and `start_turn("m2b")` leave `m1` and `m2b`.
- `test_agui_runs_of_one_message_are_one_turn`: three runs with three `runId`s and one last user message leave 1 turn.
- `test_langgraph_a_node_run_again_carries_the_turn_on`.
- `test_no_start_rewinds`: a start of an earlier id, and a start of a new id while later turns exist, each remove 0 rows.
- `test_a_branch_is_one_fork`.

`tests/test_sync.py`: `start_turn`, `turns`, `rewind` and `fork` each have a twin, and the pinned count at line 254 rises by four on top of what specs 2, 3 and 7 add. `turn` and `parent` are properties of both faces.

## Scope

In:

- `src/vfs/kernel_store/turns.py`, new: the statements, `make_first_turn`, `latest_turn`, `rewind_turns` and `remove_turns`.
- `src/vfs/turns.py`, new: the constants, `Turn`, `Rewind`, the id check and the generator. It issues no statement.
- `src/vfs/models/kernel_rows.py`: the table of decision 2, and one added to `KERNEL_FORMAT_VERSION`.
- `src/vfs/session.py` and `src/vfs/sync_session.py`: `start_turn`, `turn`, `turns`, `rewind`, `fork`, `parent`, and `cli` with `cwd=None`.
- `src/vfs/shell/host.py`: `ShellState`, `SHELL_ENV_BYTES`, and `run_line_from`.
- `crates/vfs-shell/src/machine/mod.rs`, `crates/vfs-shell-wasm/src/wire.rs`, `crates/vfs-core/src/shell_binding.rs` and `src/vfs/_native.pyi`: the end state. After a Rust edit the extension is built again.
- `src/vfs/__init__.py`: `Turn` and `Rewind`.
- The tests above, and `tests/lint/allowlist.py` where a module on the size list grows.
- The docs below.

Out: everything under "Left as it is", and the definition of every table but `vfs_session_turns`. This spec writes five columns of `vfs_sessions` and issues two statements on `vfs_session_stamps`, each as its owner rules.

Files that another spec also changes, each of which must name this one: `session.py`, `sync_session.py` and `tests/test_sync.py` (specs 2, 3, 5 and 7); `kernel_rows.py` (specs 0, 2, 3, 5 and 7); `shell/host.py` (specs 3 and 8); `wire.rs` and `shell_binding.rs` (the binary boundary, and `agents/2026-11-22-shell-wire-and-instance-lifecycle`); `how-we-name.md` (spec 2); the session guide (specs 2, 3, 5 and 7).

The landings are decision 23's five. Each runs `scripts/ci.sh`, `scripts/docs.sh check` and the Postgres leg before its pull request. Landing 2 also runs `cargo test -p vfs-core` and the shell crate's tests.

## What the docs must say

- Start a turn at the top of every request. Starting a turn the session has carries it on.
- A turn id follows the rule of a session id: 1 to 255 visible ASCII characters.
- `session.turn` is `None` until a turn is started on the handle. Calls made before that are filed under the session's latest turn when their record is written, and `turns()` shows the turn VFS made.
- A session's shell keeps its directory and its exported variables, as a new process would inherit them. It keeps no function, no unexported variable and no history. Variables past 32,768 bytes are not kept, and the line says so.
- A rewind changes what the session remembers and no file. It raises for a turn the session has not. It cannot be undone, so fork first to keep the old line.
- A handle whose turn was rewound away can still read. Its changes are refused until a turn is started.
- A fork copies turns, what was seen, and the shell's directory and variables. It shares every file. It leaves waiting jobs and the record of changes behind. An id already in use is refused.
- `parent` on the handle a fork returns is the session it came from. The listing of sessions is the stored record.
- In the table of chat stacks, AG-UI's turn id is the id of the last user message, not `runId`.

Pages, each changed: the session guide's steps 4, 5 and 6 and its table of chat stacks; the docstrings of the six new names, which are the reference pages; `documentation/reference/shell.md` for what a session keeps between lines; `documentation/maintainers/how-we-name.md` for `start`; the glossary for "turn", "fork point" and "shell state".

## Earlier decisions this reverses

- Roadmap story F7, criterion 7, at `context/standards/roadmap.md:696`: "`history` holds at most 1,000 entries". No history is kept. The criterion's first half, that `Session.cli` keeps `cwd` across calls, is met by decisions 9 and 10.
- `Session.cli(line, *, cwd="/")`, as built: the default becomes `None`, which means the session's own directory.
- The docstring of `src/vfs/session.py`, "A session holds exactly one authority and its own lifecycle, nothing more": a handle also holds its turn. Spec 2 reverses the rest of that sentence.
- `documentation/maintainers/how-we-name.md`, the list of verbs: `start` is added.
- This spec's own first draft, in four places: a turn id admitted any character that is no control character, and now follows the session id's rule (decision 3); the handle kept the session's key, and now keeps none (decisions 4 and 10); the fork point was also stored as a turn id, and is now a number alone (decision 19); `parent` was learned from the row, and is now fixed when the handle is made (decision 19).

## Choices for the owner

Each is decided above and stands until it is ruled on.

1. **No history is kept.** Decision 9. The other choice is the roadmap's 1,000 entries, at one write of the line's text for every line.
2. **The shell keeps the directory and the exported variables only.** Decision 9. The other choice keeps every variable and every function, which is what one long-lived bash would do and not what a new process does.
3. **`SHELL_ENV_BYTES` is 32,768.** Decision 11.
4. **A rewind cannot be undone.** Decision 13. The other choice hides removed turns and adds a filter to every read of a stamp.
5. **A fork to an id in use is refused, and a repeated fork is not answered with the first.** Decision 16.
6. **`parent` is on the handle a fork returns and on no other.** Decision 19. The other choice drops it from the handle and leaves the listing as the one read.
7. **A change through a handle whose turn was removed is refused, and a read is served.** Decision 8.
8. **A turn id follows the session id's rule.** Decision 3. The other choice admits spaces and characters outside ASCII in a turn id alone.
9. **A read made through a handle with no turn, just before a rewind in another process, is remembered.** Decision 7. The other choice is a statement on that read, or a column and a comparison in spec 3's flush.

## Where this spec disagrees with the overview or the guides

1. **The overview gives spec 2 the amendment of `how-we-name.md` for `session` alone.** Change proposed: this spec's first landing adds `start` to that page's verbs. Evidence: `documentation/maintainers/how-we-name.md:29` lists four verbs, `start_turn` is fixed by ruling 12, and spec 2's decision 25 adds no verb.
2. **The guide says a handle's `turn` holds the id of the turn the handle is in.** Change proposed: add "or `None` before a turn is started on it". Evidence: a handle is made with no I/O and a read may issue no statement, so a handle cannot know the latest turn (decisions 6 and 7).
3. **The guide's Step 6 reads `branch.parent` with no word on other handles.** Change proposed: add "A handle asked for later with `fs.session` does not carry it; `fs.sessions` lists each session's parent." Evidence: a handle keeps no copy of its row, by spec 2's decision 16.

Three points of the first draft are settled by the reconciliation and are gone from this list: `session.turns()` is on the overview's list of names (ruling 10), the argument `id` is allowed by spec 2's first landing (ruling 9), and AG-UI's turn id is the user message's id.

## Needs no other spec meets yet

1. **Spec 3, decision 7 (The current stamp is read in one keyed statement).** It reads the row of the highest turn and does not ask whether that turn is live. On Postgres a flush and a rewind that overlap can leave one stamp of a removed turn: the flush's liveness test sees the turn before the rewind commits, and the rewind's R3 does not see the flush's row. The decision would need: "The current stamp of a path is the row of the highest turn that has a row in `vfs_session_turns`. Both the outer row and the `max` are filtered by spec 4's predicate, `EXISTS (SELECT 1 FROM vfs_session_turns t WHERE t.session_key = s.session AND t.number = s.turn)`."
2. **Spec 3, decision 8 (A read writes its stamps behind, and a change writes them with the change), step 2.** Decision 8 here refuses a change through a handle whose turn was removed. The step would need: "For a started handle the lookup also selects spec 4's predicate for the handle's turn. When it is false the call is refused `vfs.not_found`, with the detail `turn '<id>' was removed by a rewind; nothing was changed`, and nothing is dispatched."
3. **Spec 3, the scope of its rows written behind.** `rewind` and `fork` drain one session. Its decision 8 would need: "A session's stamps are put behind with `scope=(owner_key, id)`, so `store.drain((owner_key, id))` waits for that session's rows alone."
4. **Spec 7, decision 5 (A job is in one of four states, and every change of state is one conditional update on its revision).** A job of a removed turn that is `running` can stop again and wait under a dead turn. The decision would need: "The insert that stores a job, and the update from `running` to `interrupted`, carry spec 4's predicate for the job's `session_key` and `turn_number`. A job whose turn has no row is not stored as waiting: it ends `cancelled`, with the reason `cancel_session_jobs` is given by a rewind."
5. **Spec 2, decision 3 (The handle holds seven values, and only its current turn ever changes).** Decision 19 here adds a slot. The decision would need: "`_parent`, public as `parent`: the id of the session a `fork` made this handle from, fixed when the handle is made, and `None` on a handle from `fs.session`. The handle holds eight values."
6. **Spec 2, decision 13 (`vfs_sessions` holds one row per session, under a key that is never used twice), the row for `fork_turn`.** It reads "the number of the last turn the fork took from its parent". Decision 17 here writes `n - 1`, which may be a number no turn holds. The row would need: "every turn the fork took from its parent is numbered at or below it".

One need that another spec states on this one is not met. Spec 3 asks, in item 2 of what its "Builds on" asks of spec 4, that the turn number of a handle with no turn be fixed before its stamp is stored, so that a rewind between a read and its flush cannot leave the stamp in the latest kept turn. It is not met, because such a handle has made no statement and a read may make none, so nothing the handle holds says where the session stood when the read was made. Decision 7 states the case and its cost: one read that the session remembers and the rewound conversation does not, only from a handle that started no turn, only in another process than the one that rewinds, and only inside one flush. The etag of that stamp is still checked at the write, so no other caller's change is ever overwritten. A host that starts a turn on every request never meets it, since a started handle's late stamp is dead.

## Not checked

- **Postgres.** No server was available. To run on the Postgres leg: `test_two_file_systems_never_take_one_number`, for the counter and the guarded insert at READ COMMITTED; `test_two_rewinds_at_once`; `test_a_stamp_that_arrives_after_the_rewind_is_dead` with the flush and the rewind overlapping, which is item 1 above; and the creation of the partial index `ix_vfs_session_turns_state`.
- **The other eight specs as they stand after their own reconciliation.** Each was read in its first draft. A decision cited here by number and heading may have moved.
- **`resolve` as written by spec 2.** The probe used a stand-in read and insert. The statement counts under "Cost" add spec 2's own table of counts to the four turn statements that were run.
- **F6 and R3 against spec 3's table.** They are written from its decision 4's columns and were not run.
- That bash run on a line prints nothing for `history`, and that bash exports `OLDPWD` after `cd`. The first is taken from the draft named under "Builds on". Neither was run against bash.
- What the machine's report of its end state adds to a line's `fuel_used`. `tests/shell/test_host.py:738` reads that figure.
- How often a user edits, regenerates or branches, and what share of calls are lines.
- A fork or a rewind on SQLite while a 10,000-file batch runs. The kernel store is a file of its own, so the two should not meet. It was not run.

## One line

A session's records are filed under the message they answer, so a rewind forgets from one message on, a fork starts a second session from one, and the shell is where the last line left it.
