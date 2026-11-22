# The session remembers what it read, and refuses a change to a file that moved on

A draft, written on 2026-11-22 and reconciled the same day with the other eight specs of the overview, in two further rounds, the last against their text at `7c383f32`. It is not reviewed, and nothing is built. It replaces, at this path, the spec merged from pull request 42, whose decisions 1 and 2 (the etag and `if_match`) moved to spec 1 and whose decisions 3 to 9 are rewritten here. It rests on the map of the nine specs (`agents/2026-11-22-the-specs-for-jobs-and-sessions/overview.md`), the guide `documentation/how-to/keep-a-session-for-each-conversation.md`, five of the session studies under `agents/2026-11-22-a-session-is-stored-named-and-forked/research/` (`coding-agent-sessions.md`, `chat-protocols.md`, `langgraph-threads.md`, `framework-session-stores.md`, `history.md`), the log cost study (`agents/2026-11-21-what-a-log-row-per-call-costs/research.md`), the rulings at the end of `agents/2026-11-22-shell-review/reviews/verification.md`, and five scripts run on 2026-11-22 at `6dae6a1d` and `59946f0d`, cited below as runs 1 to 5. The other eight specs were read in the working tree on 2026-11-22, some at `59946f0d` and some part-way through their own second round. Each is cited by its number, its decision and that decision's heading, because they were being revised at the same time.

## The outcome wanted

An agent reads `/notes/plan.md` through its session in one request. Ten minutes later, in another request served by another process, it edits the file through the same session. If the file is as the session saw it, the edit lands. If another caller changed it, or it is now a different file at that path, nothing is written and the call is refused with the words "Changed since it was read". A change to an existing file the session was never shown is refused with "Not read yet". The caller's code carries no etag. One read clears either refusal. A session's own writes never cause one. A shell line gets the same guard, with or without a stored session.

## Builds on

Each line gives the state on 2026-11-22, then what is taken, by the name its owner gives it.

- **The write preconditions**, `agents/2026-11-20-write-takes-preconditions-and-an-append/`. Landed. `write(if_absent=, append=)`, the snapshot, the guard on the material `UPDATE`, and `exists` with the occupant's facts. Its `if_version` leaves with spec 1.
- **The log cost study**, `agents/2026-11-21-what-a-log-row-per-call-costs/research.md`. Done. A row written behind adds zero synchronous statements to a read. On SQLite the kernel's rows need a file of their own.
- **Spec 0**, `agents/2026-11-22-the-kernel-keeps-records-of-its-own/`. Drafted. Taken:
  - `KernelStore` and its whole interface, decision 22 (The interface is private, and this is all of it), with its eight rules for a spec that keeps a record.
  - `put_behind`, `register_behind` and `BehindKind`, decision 13 (A record written behind goes to one buffer for each file system, which one task empties as soon as it is free). The task flushes as soon as it is free, with no count to reach and no timer, 1,024 rows to a flush.
  - `BEHIND_CAPACITY`, 16,384 rows, the oldest dropped, decision 14 (The buffer is bounded, drops its oldest rows when full, and holds only records that may be dropped).
  - `drain(scope)`, decision 16 (`drain` waits for the records of one scope).
  - `waiting_behind` and `discard_behind`, and a deferred task as a kind, decision 24 (A caller can read and withdraw what waits in the buffer, and a deferred task is a kind). The store reports no row as stored or dropped, so this spec keeps no table of its own beside the buffer.
  - `query`, `commit` and `KernelStoreUnavailable`, decision 9 (The store is used through `query` and `commit`, and a failure is one exception).
  - `record_after`, decision 10 (A record that goes with a change is written in a transaction of the store's own, after the change or before it, and never inside it).
  - `key_chunks`, decision 12 (A batch of rows is written in chunked statements through four helpers).
  - `row_chunks`, `delete_where`, and leave for a statement of fixed binds, decision 25 (A statement of a spec's own is within the interface when its binds are fixed or its rows are cut by the store's budgets).
  - `build_kernel_tables` and `KERNEL_FORMAT_VERSION`, decision 8 (The tables are made at the store's first use, and a store of another format is refused).
  - `close` flushes, decision 19 (`close` flushes the buffer, ends the task and disposes the store's engine, inside the kernel's own close).
- **Spec 1**, `agents/2026-11-22-a-row-carries-an-etag-and-a-change-can-require-it/`. Drafted. Taken:
  - `Observation.etag` on every row that has a version, whatever `columns` names, decision 1 (Every row that carries a version carries an etag, and the storage mints it). `Etag` and `ETAG_LENGTH`, 20, decision 2 (An etag is twenty hexadecimal characters: a keyed digest of the mount, the entry and the version). An etag is compared and never taken apart.
  - Which rows carry one, the rows a change returns included, decision 4 (Each verb fills the etag on the rows it already returns).
  - `if_match` and `if_matches` on `write`, `edit`, `delete` and `move`, decision 6 (`write`, `edit`, `delete` and `move` take `if_match`, and their batch forms take `if_matches`). `if_version` and `if_versions` are gone, decision 7 (`if_version` and `if_versions` leave).
  - The answers of a failed precondition, decisions 9 (The precondition is judged at the snapshot, and the guard each statement already carries holds it) and 12 (A mismatch is `conflict` with the version and the etag of the row at the path, and an etag from another mount is a mismatch like any other).
  - The `etag` trait, decision 13 (A storage declares the `etag` trait, and a mount without it refuses a change that requires one).
  - The mark `ABSENT`, decision 18 (The mark `ABSENT`, in place of an etag, requires that the path holds no live row). Decision 9 here fills it in for a path a strict session was not shown.
  - Spec 1 matches a directory by its entry and its version, decision 10 (A directory is matched as a file is, by its entry and its version). This spec sends no precondition for a directory (decision 11 here), so that rule is never met through a session.
- **Spec 2**, `agents/2026-11-22-a-session-is-stored-named-and-forked/`. Drafted. Taken:
  - `session_key`, decision 13 (`vfs_sessions` holds one row per session, under a key that is never used twice).
  - `SessionRef`, its `scope`, `resolve` and `find`, decision 14 (The row is first written by the first record that needs it, through one function, `resolve`). A handle keeps no copy of the key, decision 16 (A handle keeps no copy of the row, so every record names its session by owner and id).
  - The handle's `_ref`, `_strict` and `_turn`, decision 3 (The handle holds seven values, and only its current turn ever changes), and `strict` read at each call, decision 4 (`strict` and `policies` belong to the handle and are never stored).
  - An anonymous authority owns no session, decision 7 (An anonymous authority owns no session).
  - `SESSION_CHILDREN` and `SESSION_RECLAIM_CHUNK`, decision 22 (Removal frees the id in one commit and reclaims the rest in bounded chunks). A session is removed by `fs.remove_session(authority, id)`, decision 21 (`fs.remove_session(authority, id)` removes a session, and `delete` on a handle is the file verb and nothing else).
- **Spec 4**, `agents/2026-11-22-a-session-works-in-turns-and-rewinds-or-forks-at-one/`. Drafted, and built after this spec. Taken:
  - `vfs_session_turns` and a turn's `number`, decision 2 (`vfs_session_turns` holds one row per turn).
  - The turn is the handle's, decision 6 (The turn is on the handle, and the store holds no current turn).
  - The latest-turn rule and `make_first_turn`, decision 7 (A handle with no turn files each record under the session's latest turn, found when the record is written).
  - Live and dead, and the refusal of a change through a removed turn, decision 8 (A removed turn's number is never used again, and a record that names it is dead).
  - Step R3 of decision 12 (`rewind(before=turn)` removes that turn and every later one, with their stamps, and cancels their waiting jobs, in one transaction) and step F6 of decision 17 (A fork copies the turns below the fork point, their stamps and their shell state, in statements with a fixed number of binds). Decision 21 here gives the two statements, as two functions.
- **Spec 5**, `agents/2026-11-22-a-rewind-puts-a-sessions-files-back/`. Drafted, and built after this spec, but for its first two landings. Taken: `Change` and `Result._changes`, decision 2 (A storage reports every entry row a mutation changed, and what the row was before), which its second landing carries with no session in it. Its first landing is the `read_versions` seam alone. Decisions 10 and 13 here use it where a tree has it.
- **Spec 6**, `agents/2026-11-22-a-policy-judges-each-step/`. Drafted. Taken: a policy is asked inside the kernel's dispatch, decision 10 (A policy is asked after the kernel's gate, after the caller's rights are proven for a change, and before any storage is asked to act).
- **Spec 7**, `agents/2026-11-22-a-job-is-interrupted-and-resumed/`. Drafted. Taken: a step that carries a stale `if_match` is refused when its preview is built, decision 13 (The preview is computed once, as the caller, for seven verbs, and every part of it is bounded); the saved step is carried out with its arguments as saved, decision 22 (The saved step is carried out as its caller, with rights judged again, and with the etags the preview saw as `if_match`); a job carries `session_key` and `turn_number`, decision 34 (A resumed job stays in its turn, and what it writes is remembered by its session).
- **Spec 8**, `agents/2026-11-22-an-interrupted-line-replays-its-replies/`. Drafted. Taken: a bare line's stamps cross a stop, decision 24 (A resumed line runs as its caller, in the session and turn it started in, and its stamps cross the stop), by a journal of what its table was shown, decision 28 (What a bare line was shown is journaled with each entry, and the replay shows it again). Decision 22 here gives the interface it journals through.
- **The shell**, `src/vfs/shell/` and the nine drafts under `agents/2026-11-22-shell-*`. The shell is landed. The drafts are not built, and four of them (file reads, descriptors, file operations, sed edits) hand their guards to this spec.

## Terms

- **Etag.** Spec 1's twenty characters that name one entry at one version in one mount. It is compared and never taken apart.
- **Stamp.** A session's memory of one path. It is one of three kinds: a **file** stamp (an etag), a **directory** stamp (the session was shown that a directory is there), or an **absent** stamp (the session was shown that nothing is there, or removed what was).
- **Shown.** A row is shown to a session when a call through that session returns it and the store produced it in that call.
- **Current stamp.** The one stamp of a path that a session acts on.
- **Strict.** The rule that a session does not change an existing file or directory it holds no stamp for.
- **Kernel store.** Spec 0's `KernelStore`, where the kernel keeps its own records.
- **Written behind.** Put in the store's buffer with `put_behind` and written by the store's task after the call has returned.
- **Scope.** The value attached to rows put behind so that `drain` can wait for them alone. A session's scope is spec 2's `ref.scope`, the pair of its owner key and its id.
- **Window.** The time between a read's return and the flush that stores its stamps.
- **Guarded router.** The kernel's verbs wrapped with the rules of this spec. In code it is `GuardedRouter`. A handle makes one for each call, and a line holds one.
- **Probe.** A call the shell's host makes to decide how to run a command. Its row is never printed. The scripts behind this spec are called runs, to keep the two apart.
- **Line session.** The strict, unstored session a bare `fs.cli` line runs in.
- **Live and dead.** Spec 4's words: a turn is live while it has a row, and a record of a turn with no row is dead.

## What the code does today

Run or read on 2026-11-22. Runs 1 to 3 call the public verbs on an in-memory kernel. Run 4 records, on a proxy of the kernel, the verbs each of thirteen shell lines calls. Run 5 runs the statements of decisions 6, 7, 15 and 21 on SQLite 3.50.4. The scripts are kept outside the repository.

| Fact | How it is known |
|---|---|
| A session holds an authority, a closed flag and the kernel, and nothing else. | Read, `src/vfs/session.py:61-66`. |
| Every session verb is the kernel's verb with `authority=` filled in. `edit`, `delete` and `move` take no precondition. | Read, `src/vfs/session.py:97-106`, `:181-203`, `:258-266`. |
| The synchronous session wraps the asynchronous one. | Read, `src/vfs/sync_session.py:36-49`. |
| `cli` runs a line straight on the kernel. `Session.cli` does the same with the session's authority. | Read, `src/vfs/base.py:1668-1677`, `src/vfs/session.py:414-417`. |
| The shell's host answers every request with a public verb of one router. | Read, `src/vfs/shell/host.py:369-437`, `:471-493`. |
| `cat f` is a `stat` and a `read`. `sed -i` is a `stat`, a `read` and one `write`. `rm f` is a `stat` and a `delete`. `rm *.log` is an `ls` of the directory, then a `stat` and a `delete` for each match. `ls d; rm -r d` is a `stat`, an `ls`, a `stat` and one `delete` with `cascade=True`. `[ -f f ]` is one `stat`. | Run 4. |
| The shell has no `stat` program: `stat f` exits 127. A stat request is asked before a read, a redirection and a removal, and for a test. | Run 4, and `src/vfs/shell/host.py:420-427`. |
| The served `grep -r` and `find` each stat their operands first. | Read, `src/vfs/shell/programs.py:282`, `:501`. |
| `cat big > f` is one `write` of no bytes that makes or empties `f`, then one `write` with `append=True` for the bytes. `cat big >> f` is two writes with `append=True`. The request names a path, bytes and a mode, and no writer. A refused writer sends nothing again. | Run 4, and `crates/vfs-shell/src/machine/files.rs:195-224`, `crates/vfs-shell/src/machine/mod.rs:174-178`. |
| A refusal whose kind the host has no word for prints `Invalid argument`. `conflict` is one. | Read, `src/vfs/shell/host.py:94-102`, `:495-505`, `crates/vfs-shell/src/machine/mod.rs:244-257`. |
| An error line is the severity, the path, the message, then the kind's hint and retry class. A child kind takes its own row of `KIND_CONTRACTS` when it has one. | Read, `src/vfs/results/render.py:93-123`, `src/vfs/results/kinds.py:161`, `:314-329`. |
| `version`, `kind` and `path` come back on every row whatever `columns` names. | Run 3. |
| A change returns the changed row with its kind. A move and a copy return the destination row alone. A directory delete returns the directory row alone. `mkdir(parents=True)` returns each directory it made. `write(parents=True)` returns the file alone. | Runs 1 and 3. |
| A directory's version moves when a direct child is made, removed, moved or copied. It does not move when a child's body changes. | Run 1: 1, then 2 after a child was made, 2 after an edit, 5 after a copy and a move. |
| A directory move rewrites the paths of what is beneath it. Those rows keep their entry and their version. | Read, `src/vfs/storage/backends/database/topology.py:313`, `:392`. Run 1. |
| `read` of a directory is `wrong_kind`. `ls` and `tree` of a directory do not return the directory's own row. | Runs 1 and 2. |
| A read of a deleted file, of a file beneath a deleted directory, and of a file beneath a missing directory are each `not_found`. The second and third name the ancestor as the path and the file in `data["vfs.target"]`. | Runs 2 and 3. |
| An append takes a file from version 3 to version 4. `mkedge` and `grant` move no file's version. | Runs 1 and 2. |
| `glob`, `grep` and `search` with `observations=` filter rows in hand, and `glob` hands them back as they were given. | Read, `src/vfs/base.py:1376-1394`, and the docstrings of the three. |
| The in-memory storage is the SQLite storage on a private database. | Read, `src/vfs/storage/backends/memory.py:40`. |
| A path key is at most 1,024 UTF-8 bytes and is bytewise on both engines. | Read, `src/vfs/paths.py:41`, `src/vfs/models/rows.py:170-194`. |

## The problem

- **Nothing remembers a read.** A caller that reads and writes back must carry the etag itself. The shell carries none, so `sed -i` writes back unguarded.
- **The merged design kept the memory in one process.** A chat application serves each request in a new process. Every chat protocol studied assumes it (`chat-protocols.md`, lesson 2). A session object in memory would hold no stamp on the next request, and strict would refuse every edit.
- **This design was built once, and deleted.** opencode kept a record of each file read, per session, in memory, and compared modification times. The module was 113 lines (`git show 76a141090ea^:packages/opencode/src/file/time.ts`). It was deleted on 2026-04-16. Its failures, from `coding-agent-sessions.md` section 7:
  - Every edit after a restart was refused as unread, because the record was in memory.
  - An edit after an undo was refused, because the restored file had a new modification time.
  - The agent's own shell writes and a formatter left the record stale, so its next edit was refused.
  - One refusal was retried 295 times in five minutes, because it did not help the model recover.
- **The merged design has four holes of its own.**
  - A stamp for every row of every listing has no bound per call. A listing has no page unless one is asked for (`src/vfs/base.py:847-883`).
  - An append to a stamped file carried `if_match`. An agent that had read a shared log could then not append to it once anybody else had. Under contention it would read, lose and read again without end.
  - `if_match` on a directory compared its version. A directory's version moves when the session itself writes a file into it (run 1), so a session could not remove a directory it had filled.
  - It said eviction never lets a write through. With `strict=False` that is false: a forgotten stamp makes the file unread, and an unread file is let through.

## Decisions

### 1. A stamp is a record the kernel keeps about calls, and adds no primitive

A stamp has no path in the namespace and no verb. It is reached only through a session, as a grant is reached through `grant`. It holds one thing Article 1 already has, by way of spec 1's etag: an entry's identity at one revision.

Reason: Article 1 allows five first-class things and requires each to have a path. A session's memory of a read is not one of them, and the overview says so of every record of the nine specs.

### 2. A session stamps what the store shows it

| Call through a session | What it stamps |
|---|---|
| `read` | Every row it returns. |
| `stat`, `ls`, `tree`, `glob`, `grep`, `search`, `traverse` | The rows it returns, up to the cap of decision 3. |
| `ls` and `tree` that succeed | Also the directory listed, with a directory stamp. |
| `read`, `stat`, `ls` or `tree` answered `not_found` for a path it named | That path, with an absent stamp. The refusal may name the path or an ancestor of it. |
| `glob`, `grep` or `search` with `observations=` | Nothing. |
| A change that succeeds | Decision 13. |
| A row with no etag: a bare row, an edge row, a row of a mount that issues none | Nothing. |

- A row of kind `file` leaves a file stamp that holds its etag. A row of kind `directory` leaves a directory stamp, which holds none.
- The key of a stamp is the path as the row carries it: the router's resolved, absolute path. A path a caller writes is resolved the same way before a stamp is looked up, so `/a//f.txt` and `/a/f.txt` are one key.
- The result the caller gets is the kernel's result, unchanged.
- An absent stamp matters. A session holds a file stamp. Another caller deletes the file. The session's write is refused as changed. Its read answers `not_found`. Without the absent stamp the stale file stamp would refuse every later write, and no read could clear it.
- A directory stamp from a listing matters. `ls /build` then `rm -r /build` is the common order, and `ls` does not return the row of `/build` (run 1). Without the stamp the removal would be refused as unread, and the hint would say to read a thing that cannot be read.
- Rows in hand are the caller's. A caller could put any etag on one. Only what the store produced in the call is shown.

Reason: the verification rulings say bodies and listings both stamp, and the guide says that listing the directory a file is in is enough. A session that stamped bodies alone would force a read of a 5 MB file before it could be removed.

### 3. A listing stamps at most 1,024 rows

`LISTING_STAMP_ROWS = 1024`. A call other than `read` leaves at most 1,024 stamps: the directory it listed, where there is one, then the first rows of its result in the order the result holds them. A `read` is never cut.

- A row past the cap is not stamped. A change to it is refused as unread, and `stat` of it clears that.
- 1,024 is one flush of spec 0's task and a sixteenth of its buffer, so one listing can neither fill the buffer nor span two flushes. At 5 columns a row it is 5,120 bind parameters, under a sixth of the tightest budget of 32,700.
- A `read` of many bodies in one call puts a stamp behind for each. Past `BEHIND_CAPACITY` the buffer drops its oldest rows, and a dropped stamp is a lost stamp (decision 8).

Reason: a listing has no page of its own, so a `glob` of ten million rows would hand ten million rows to a buffer that every session shares. The cap keeps one call from filling it. The largest directory in the Linux tree holds 1,533 entries, and a median directory two, so the cap is past what a model can act on from one result.

### 4. The table is `vfs_session_stamps`, one row per session, path and turn

```python
stamps = Table(
    "vfs_session_stamps",
    metadata,
    Column("session_key", <the type of vfs_sessions.session_key>, primary_key=True),
    Column("path", BytewiseString(MAX_PATH_LENGTH), primary_key=True),
    Column("turn_number", BigInteger, primary_key=True),
    Column("kind", String(1), nullable=False),      # "f" file, "d" directory, "a" absent
    Column("etag", String(ETAG_LENGTH)),            # set for "f" alone
    sqlite_with_rowid=False,
)
```

- The primary key is `(session_key, path, turn_number)`. There is no other index, no foreign key and no time.
- The table joins `build_kernel_tables` in `src/vfs/models/kernel_rows.py`, its name begins with `vfs_session`, and its landing adds one to `KERNEL_FORMAT_VERSION`. Its statements are in a new module, `src/vfs/kernel_store/stamps.py`. These are rules 1 and 2 of spec 0's decision 22.
- The table has no expiry of its own and so no sweeper. Its rows go with their session, by decision 21.
- The etag is stored whole, as spec 1 mints it. No version and no entry id is kept beside it, because nothing here needs one: decision 5 orders two stamps by arrival, and decision 10 takes "what the file was before" from the change itself.
- Without a rowid a row is 101 bytes on SQLite at a mean path of 57 bytes, and 173 with one (run 5).
- Until spec 4's first landing every row carries turn number 0, and no statement of this spec reads `vfs_session_turns`.

Reason: the overview fixes the key, because a rewind must restore what an earlier turn saw. The etag is one opaque column because spec 1's decision 2 lets no code take one apart.

### 5. One stamp per path is current, and the stamp that arrives last is the current one

The current stamp of a path is the row of the highest live turn for that session and path. Before spec 4 lands it is the path's one row.

A stamp that is written becomes the current stamp, whatever the row before it held:

- It is written into the row of its own turn: the handle's turn, or for a handle with no turn the session's latest turn, by spec 4's decision 7.
- Every row of the same path in a later turn is removed in the same transaction. A handle in an earlier turn, or a job resumed in the turn it started in, has shown the session something newer than what those rows hold.
- Rows of the same path in earlier turns are left as they are. A path shown again in a later turn, unchanged, has a row in that turn too.

Three things follow.

- **A read clears.** Once the stamp of a read is stored, it is the current stamp until another arrives. No turn order can leave an older row in front of it.
- **A rewind is exact.** The guide's two cases hold (run 5). A file read in `msg_4` and again in `msg_5` keeps its `msg_4` row, and is still read after a rewind. A file read in `msg_4` and changed in `msg_5` goes back to its `msg_4` row, which no longer matches the file, so a change is refused until it is read again.
- **A handle in an earlier turn is filed where spec 4 says.** Its stamp is a row of its own turn, and a later rewind that keeps that turn keeps the stamp.

No counter orders two stamps of one path. An etag cannot be taken apart, a version orders one entry and not two entries that stood at one path, and a number from the store would cost a read a statement. So this spec's kind carries no `newest`, and keeps its order the other way rule 7 of spec 0's decision 22 admits for a kind with no counter: a change reads what still waits in the buffer and withdraws it before it records (decision 8).

Reason: the rule that the last arrival wins has no state a stamp can be stuck behind. The rule that a higher version wins was run in the first draft and is refused here: after one file leaves a path and another comes to stand there at a lower version, every read of the new file would lose to the old stamp, and no read would clear the refusal.

### 6. A stamp is stored by one statement shape, and a row whose session or turn is gone stores nothing

`write_stamps(store, transaction, rows)` is the one function that writes stamps. A flush calls it, and so does a change. Each row holds a `SessionRef` or a `session_key`, a turn number or none, a path, a kind and an etag. Its steps, inside the transaction it is handed:

1. **The key.** Rows that hold a `SessionRef` are resolved by spec 2's `resolve(store, transaction, refs, create=True, lifetime=...)`. A stamp is something to remember, so it makes the session's row. Rows that hold a `session_key`, which a resumed job's do, are left as they are.
2. **The later rows.** For rows of a handle that has a turn, one statement for each session and turn: `DELETE FROM vfs_session_stamps WHERE session_key = :k AND turn_number > :n AND path IN (...)`, cut by `key_chunks`.
3. **The rows.** One statement, cut by `row_chunks`, in SQLite's spelling:

```sql
WITH v(session_key, path, turn_number, kind, etag) AS (VALUES (?, ?, ?, ?, ?), ...)
INSERT INTO vfs_session_stamps (session_key, path, turn_number, kind, etag)
SELECT v.session_key, v.path, n.number, v.kind, v.etag
FROM v
JOIN vfs_sessions x ON x.session_key = v.session_key AND x.removed_at IS NULL
JOIN vfs_session_turns n
  ON n.session_key = v.session_key
 AND n.number = coalesce(v.turn_number, (SELECT max(t.number) FROM vfs_session_turns t
                                         WHERE t.session_key = v.session_key))
WHERE true
ON CONFLICT (session_key, path, turn_number) DO UPDATE SET kind = excluded.kind, etag = excluded.etag
RETURNING session_key, path
```

- **The session is live.** The join to `vfs_sessions` drops a row whose session was removed. That is how a job that finishes after its session was removed leaves no stamp, and no row is left under a key that spec 2's reclaim has passed.
- **The turn is live.** The join to `vfs_session_turns` is spec 4's predicate of its decision 8. A row of a dead turn stores nothing.
- **A handle with no turn.** Its rows carry no number, and the subquery is the one spec 4's decision 7 gives, inside the writing statement.
- **A session with no turn.** Its rows with no number come back from no `RETURNING` row. The writer calls spec 4's `make_first_turn` for each such session and runs the statement again for those rows.
- **Before spec 4 lands** the statement has no join to turns and writes turn 0, and step 2 is not issued.
- The rows of one call are made distinct by session and path first, the last kept, and sorted, so two transactions lock rows in one order and no statement touches one row twice.
- Seven cases were run through the statement on SQLite (run 5): a handle with a turn, a handle with none, a dead turn, a session with no turn, a removed session, the same key again, and a mixed batch. Every join is a search of a primary key.

Reason: one statement with no read before it keeps a flush at one round trip beyond `resolve`. Spec 0's decision 25 admits a multi-row statement of a spec's own when `row_chunks` cuts it. Spec 4's decision 7 wants the latest turn found inside the statement that writes, and its decision 8 wants a dead record to belong to nothing.

### 7. The current stamp is read in one keyed statement

```sql
SELECT live.ok, s.path, s.kind, s.etag
FROM (SELECT EXISTS (SELECT 1 FROM vfs_session_turns t
                     WHERE t.session_key = :k AND t.number = :n) AS ok) live
LEFT JOIN vfs_session_stamps s
  ON s.session_key = :k AND s.path IN (...)
 AND s.turn_number = (SELECT max(m.turn_number) FROM vfs_session_stamps m
                      JOIN vfs_session_turns t ON t.session_key = m.session_key AND t.number = m.turn_number
                      WHERE m.session_key = s.session_key AND m.path = s.path)
```

- It is `current_stamps(transaction, session_key, paths, turn_number=None)`. It returns, for each path, the kind of its current stamp and, for a file, its etag, and with a turn number whether that turn is live.
- It returns at most one row a path, and always at least one row, so `live.ok` is read even when no path has a stamp. That column is the check spec 4's decision 8 asks for. It is left out for a handle with no turn.
- A dead row is never the current stamp, because the inner join reads live turns alone. Decision 6 stores none, but on Postgres a flush and a rewind that overlap can leave one, as spec 4 found: the flush sees the turn before the rewind commits, and the rewind does not see the flush's row.
- The paths are cut by `key_chunks` and the results merged. 10,000 paths are one statement on both engines.
- The stamps beneath a directory are read by range, with `s.path >= :prefix || '/' AND s.path < :prefix || '0'` in place of the membership and `s.kind <> 'a'` added. The column is bytewise, so the range is the subtree. A batch that names many directories reads 500 ranges to a statement, under SQLite's expression depth of 1,000.
- Before spec 4 lands the statement is the membership alone, with no join and no `live`.
- Every search is by a primary key (run 5, `EXPLAIN QUERY PLAN`).

Reason: a change needs the stamp of each path it names and nothing else, so its cost follows the call and never the session.

### 8. A read writes its stamps behind, and a change writes them with the change

**A read.** The guarded router calls the kernel's verb. It turns the rows into stamps and calls `store.put_behind(STAMPS, rows, scope=ref.scope)`. That is its whole dealing with the store, as rule 3 of spec 0's decision 22 requires. It issues no statement and waits for nothing. This holds for the absent and directory stamps of decision 2 as well.

`STAMPS` is a `BehindKind` named `stamps`, whose `write` is `write_stamps` and whose `key` is `("owner_key", "id", "path")`. That key is coarser than the statement's conflict key, since it leaves the turn out. So a later stamp of one path replaces a waiting one whatever turn each handle is in, and no flush holds two rows of one conflict key.

**What is kept in memory.** A handle keeps no stamp, and nothing beyond spec 2's seven values. A handle keeps the owner key and the id and never the session key. Each store and each lookup of a stamp gets the key from spec 2's `resolve` or `find`, in the transaction that uses it. The store's buffer holds the rows that wait, at most `BEHIND_CAPACITY`. The kernel keeps the small table of decision 15, which counts bytes and holds no stamp.

**What another process sees.** The store. Inside the window it lacks the stamp. A change through it is refused as unread, or as changed when an older stamp is there. It is never let through. One read through that process clears it.

**How wide the window is.** One flush. The store's task flushes as soon as it is free, with no count to reach and no timer, so the window is the time of one transaction on the kernel store. A process that is stopped or frozen before that flush never closes it.

**How a host closes it.** A process that lives needs no call: the flush runs by itself. No public call flushes the writer, by ruling 4 of the last round. `close` flushes it (spec 0, decision 19). So a host whose process ends after each request closes the file system before the process ends, and what its sessions were shown is then stored. A host whose process is frozen or killed with no chance to close can lose that request's last reads, as the guide says. The sentence the guide needs is under "What the docs must say".

**A read that a policy stops** is spec 7's. It has read nothing, so it leaves no stamp, and its job is stored with `commit` (spec 7, decision 6, The job is committed before the interrupted result is returned). That is the one statement a read verb can issue on the kernel store, and it is not this spec's.

**A stamp lost** in a crash, or dropped from a full buffer, is the same case with no end: the session forgets that one read. The failure is a refusal that one read clears.

**With `strict=False`** a stamp that is not yet flushed, or is lost, leaves the file unread to another process, and an unread file is let through there. That is what `strict=False` asks for (decision 15).

**A change.** The order of a change through the guarded router:

1. Resolve the paths the call names.
2. Look up their current stamps. First `store.waiting_behind(STAMPS, keys=...)`, with no statement: a stamp that still waits is the last to arrive, and so is the current one. Then, for the paths that had none waiting, one `store.query`: spec 2's `find(store, transaction, ref)`, and `current_stamps` (decision 7) when the session has a row.
3. Refuse what cannot go on. A handle whose turn is dead is refused with spec 4's `vfs.not_found`, in the words of its decision 8: `turn '<id>' was removed by a rewind; nothing was changed`. What strict refuses is refused (decision 9). Nothing is dispatched. A call whose every path had a stamp waiting issues no statement and is not checked for a dead turn, which spec 4's decision 8 allows.
4. Fill in the preconditions (decision 9).
5. Dispatch through the kernel. Spec 6's policies and spec 7's interrupts are inside this step.
6. Turn the refusals the filled preconditions caused into the two kinds of decision 12.
7. `store.discard_behind(STAMPS, keys=...)` for the paths the change touched, so that an older stamp of them does not land after the change's own. Then `await store.record_after(fn)`. Inside it, `fn` calls `record_change_stamps` (decision 21) with the result. Spec 5's change rows are written in the same `fn`, by its decision 4 (A session writes its change rows after the change commits, by spec 0's record-after form, before the verb returns). The warning `record_after` returns, when the store fails, is added to the result.
8. Return the result.

- The form is record after, in the words of spec 0's decision 10. A change that landed may lack its stamp, and a stamp exists only if its change landed.
- A failed step 7 leaves the stamp behind the file. The result is still a success and carries spec 0's warning. The next change is refused as changed, and one read clears it.
- A caller cancelled inside step 7 has its record committed first, by `record_after`'s own rule. A caller cancelled inside step 5 does not learn whether its change landed, and no stamp is written.
- A failed step 2 refuses the call with the `error` of `KernelStoreUnavailable`, and nothing is dispatched, strict or not. A session that cannot read what it saw does not guess.
- A change that is interrupted (spec 7) moves no stamp.
- A stamp can never be ahead of the file, because a stamp is made from a row the store returned.
- A row of a flush already in flight is not withdrawn by step 7, as spec 0's decision 24 says. If it lands after the change's record, the next change is refused as changed, and one read clears it.

Reason: reads are about three calls in four. One synchronous row a read was measured as a NO-GO on both engines: on SQLite it made every read a writer, and on Postgres it added 97 ms to a read under 32 sessions. A change must record before it returns because the next tool call may be served by another process, and a session that refused its own write there would repeat opencode's failure. Reading the buffer is what lets the guide's `later.edit(...)` pass straight after a read, through another handle, with no wait.

### 9. A session fills in the precondition and, when strict, refuses a change to what it was not shown

A precondition the caller states always wins: `if_match`, a key of `if_matches`, or `if_absent=True`. It reaches storage unchanged, strict does not apply to that path, and its refusal is storage's own.

Where the caller states none:

| Call | Current stamp is a file | No stamp, strict | No stamp, `strict=False` |
|---|---|---|---|
| `write` of one path | `if_match` from the stamp | sent with `if_match=ABSENT`: a new file is made, an occupant is refused as unread | sent as written |
| `write(append=True)` | none (decision 10) | none | none |
| `write(entries=...)` | `if_matches` with the etag of each stamped path | `if_matches` with `ABSENT` for each unstamped path | unstamped paths sent as written |
| `edit` | `if_match` | refused as unread, nothing dispatched | sent as written |
| `delete` | `if_match` | refused as unread, nothing dispatched | sent as written |
| `move` | `if_match` on the source | refused as unread, nothing dispatched | sent as written |
| `edit`, `delete`, `move` of many | `if_matches` for the stamped paths | the call is refused whole, with one unread error for each unstamped path, nothing dispatched | unstamped paths sent as written |
| `copy`, `mkdir`, `restore` | none | none | none |
| `sweep`, `mkedge`, `rmedge`, `run`, the grant and membership verbs | none | none | none |
| `cli` | each verb of the line by its row | | |

- "No stamp" is no row, an absent stamp, or, for `write` and `edit`, a directory stamp.
- A directory stamp on the target of `delete` or `move` is decision 11.
- `fs.session(authority, id)` is strict. `fs.session(authority, id, strict=False)` keeps the precondition of a stamped path and lets an unstamped one through.
- A caller that uses the kernel directly keeps today's behaviour.
- The rules hold for every authority that owns a session, the system authority included. A stamp is not a right.
- A mount that issues no etag is decision 23.
- `ABSENT` is spec 1's mark, its decision 18. A `write(entries=...)` under strict that holds stamped and unstamped paths is therefore one call with one mapping, and it fails whole. The single form uses the same mark and not `if_absent=True`, so that a step spec 7 saves carries one shape of precondition, and its resume adds nothing that spec 1's gate would refuse beside it.
- `copy` reads its source and refuses an occupied destination, `mkdir` makes, and `restore` revives a row that reads as absent. None destroys what a session was not shown.

Reason: the precondition is checked inside the transaction that changes the row, so the session adds no check of its own to race with. Strict is the default because a changed file is only half the hazard: an agent that removes or overwrites a file it never looked at is guessing.

### 10. An append is never held to a stamp, and moves one only when it landed directly on it

A `write(append=True)` through a session carries no precondition from the session, stamped or not.

After it succeeds:

- Its status is `created`: the path takes a file stamp from the result. The session wrote the whole body.
- Its status is `updated`, and the file it landed on was the one the session's stamp names: the stamp moves to the result. Nobody wrote between.
- Anything else: the stamp is left as it is.

"The file it landed on" is `Change.etag_before`, from spec 5's decision 2. The stamp moves when that etag equals the etag the stamp holds. In a tree that does not yet carry `Result._changes`, an `updated` append leaves the stamp as it is. The session's next overwrite of that file is then refused as changed, and one read clears it.

Reason for no precondition: an append destroys nothing, the guide says it needs no read, and the landed append exists so that concurrent appends all land. A precondition from a stamp would refuse the append whenever another caller had appended first, and under contention the caller would read, lose and read again without end. Reason for the narrow move: a stamp moved by every append would let a session read a log at one version, miss a rival's append, append its own, and then overwrite the file with a fresh stamp. The rival's lines would be destroyed unseen. Reason for the etag before: a count of versions cannot tell an append that landed on the file the session saw from one that landed on another file at the same version, which is the case spec 1 exists to close.

### 11. A directory takes no precondition, and being shown it is enough

A `delete` or `move` whose target has a directory stamp is sent with no precondition from the session. Under strict a directory with no stamp is refused as unread. A directory is shown by a listing of its parent, a `stat` of it, a `tree` above it, the result of the `mkdir` that made it, or a listing of the directory itself (decision 2).

- A file stamp on a path that is now a directory fails `if_match`, and is refused as changed.
- A directory that was replaced by another directory after it was shown is removed without a refusal. A delete can be undone from the trash, and a move destroys nothing.
- A caller that wants spec 1's whole comparison states it: `delete(path, if_match=row.etag)`.

Reason: spec 1's decision 10 matches a directory by its entry and its version, and a directory's version moves when a direct child is made, removed or renamed (run 1), by the session as much as by anybody. A precondition filled from a stamp would refuse `rm -r` of a directory the session had itself written into, which is the false refusal opencode's users reported.

### 12. The two refusals are `vfs.conflict.changed` and `vfs.conflict.unread`, and neither carries a version

`ErrorKind` gains two members, each a child of `conflict`.

```python
changed = "vfs.conflict.changed"  # ESTALE: the entry changed after this session was shown it
unread = "vfs.conflict.unread"  # ESTALE: this session has not been shown the entry
```

`KIND_CONTRACTS` gains two rows.

| Kind | Phrase | Retry class | Hint | `path` means |
|---|---|---|---|---|
| `changed` | `Changed since it was read` | `refresh` | `This file changed after it was last read in this conversation, so nothing was written. Read it again, then make the change.` | the entry that changed after the session was shown it |
| `unread` | `Not read yet` | `refresh` | `This file has not been read in this conversation, so nothing was changed. Read it first, then make the change.` | the entry the session has not been shown |

Each error is `classified(kind, path)` with no detail, no `data` and `retryable=False`. The two lines the guide prints follow from `_error_line` with no change to the renderer.

The kernel's own `conflict`, for a precondition the caller stated, carries the version and the etag of the row at the path (spec 1, decision 12, A mismatch is `conflict` with the version and the etag of the row at the path, and an etag from another mount is a mismatch like any other); the two session refusals carry neither.

When each is given:

- `unread` before dispatch, for an `edit`, `delete` or `move` that strict refuses. It is judged before any policy is asked, which is what spec 6 and spec 7 need.
- `unread` in place of the refusal of an `ABSENT` the session filled in. From the storage that refusal is `exists`, by spec 1's decision 18.
- `changed` in place of the refusal of an etag the session filled in. From the storage that refusal is a `conflict`, or a `not_found` that names the path or an ancestor of it, by spec 1's decisions 9 and 12.
- Spec 7 refuses a step whose own precondition is already stale when it builds the preview, with spec 1's `stale_etag` fact, a `conflict` (its decision 13). The guarded router turns that by the same rule: `unread` where it had filled in `ABSENT`, `changed` where it had filled in an etag.
- Never for a precondition the caller stated.
- A consumer that knows neither kind reads both as `conflict`, by `kind_family`. Both raise `WriteConflictError`.

What stops a loop:

- **A refusal moves no stamp.** The same call sent again is refused again, with the same words, as often as it is sent. Nothing but a row shown, or the session's own change, moves a stamp.
- **One read is enough.** The next change finds the read's stamp in the buffer or in the store (decision 8), so it passes. A read that answers `not_found` leaves an absent stamp, so the next write makes the file.
- **A refusal is cheap.** An `unread` refusal of `edit`, `delete` or `move` reaches no mount. A `changed` refusal runs one snapshot read and no mutation statement.
- **The host puts the file beside the refusal.** A host's tool wrapper that sees either kind reads the path through the session and returns the current body with the refusal. The model's next attempt is then made from the file as it is, and the read has stamped it. The docs carry this as the pattern for a tool.
- VFS counts no refusals. A count would live in one process, and a loop of tool calls crosses processes.

Reason for no version and no etag: the one use of a current etag in a model's hands is to send it back as `if_match`, which writes over a body it has not seen. Storage's own `conflict` carries it because there the caller chose its precondition. opencode's 295 retries came from a refusal that did not show the model the new content, and an etag does not show it either.

### 13. A session's own change refreshes its stamps

| Change that succeeded | What it leaves |
|---|---|
| `write`, `edit`, `mkdir`, `restore`, `copy` | A stamp for each row of the result, from its etag and its kind. An `unchanged` row counts: the session knows that body. |
| `write(append=True)` | Decision 10. |
| `delete` of a file | An absent stamp at the path. |
| `delete` of a directory | An absent stamp at the path and at each path beneath it that has a current stamp. |
| `move` of a file | An absent stamp at the source, and the destination row's stamp. |
| `move` of a directory | The same, and each current stamp beneath the source is carried to the same place beneath the destination, with an absent stamp left behind. |
| each verb of a shell line | Its row above. Decision 17 sends every effect of a line through the guarded router. |
| a change made by a resumed job | Its row above, written for the job's `session_key` and `turn_number` by `record_change_stamps` (decision 21). |

- A directory delete or move reads the stamps beneath it by the range statement of decision 7, inside the `fn` of step 7. The rows it writes go through `write_stamps`. The work is bounded by decision 15.
- Carrying is sound because a directory move leaves each row beneath it at its entry and its version (`topology.py:313`, `:392`), so its etag is the same at the new path, as spec 1's decision 3 says.
- A batch move matches each row of the result to its pair by the resolved destination path.
- A change made with a precondition the caller stated refreshes in the same way.
- Where the result carries spec 5's `_changes`, each `made` row of kind `directory` takes a directory stamp. That covers the parents a `write(parents=True)` made, which the result's own rows leave out (run 3).

Reason: every write path must refresh the stamp of the session that made the write. opencode's shell and plugin writes did not, and the same session's next edit then failed (`coding-agent-sessions.md`, lesson 3).

### 14. Stamps meet per path, and no order of arrival can let a stale write through

Two calls on one session may run at once, in one process or in two. Each stamps its own paths. Two stamps of one path meet under decision 5: the one that arrives last is current.

The invariant: every stamp a session holds was made from a row the store returned to that session, from a row that session's own change returned, was copied by a fork from such a stamp, or was moved by spec 5's rollback to the state it had put back. A filled precondition holds only when the row at the path has the etag of the current stamp. So a change through a session lands only on a state that session was shown. The order of arrival chooses among stamps that were all shown. Its choice can cause a refusal, and nothing else.

| Case | What happens |
|---|---|
| A read, then a change of the same file, in one process | The change finds the read's stamp in the buffer or the store, fills it in, and records its own. No refusal. |
| Two calls of one process are shown one file at two versions | The later `put_behind` replaces the earlier in the buffer. The current stamp is the later show. |
| The same in two processes | The flush that lands last wins. If that is the older show, the next change is refused as changed, and one read clears it. |
| A read is shown a file, and a change of the same session lands before the read returns | The read's stamp can be stored after the change's. The next change is then refused as changed, and one read clears it. |
| A handle with no turn reads in one process, and a rewind lands in another before the flush | The stamp is filed under the latest turn left, and the session remembers one read the rewound conversation no longer holds. Spec 4's decision 7 states this case and accepts it. The etag is still checked at the write. |
| Two calls change one file at once | Both hold the same stamp. Storage lets one through. The other is refused as changed. |
| Process A reads and has not flushed. Process B is asked to change the file | B is refused as unread or as changed. A read through B clears it. |
| Two whole turns at once on one session | Each handle stamps under its own turn. A stamp of the earlier turn removes the path's rows of the later one. VFS queues no turns, as the guide says. |

Being shown a file does not mean a model used it. A session vouches that the current file was put in front of its caller, and for nothing a model did with it.

Reason: a read record is a set of validators checked at write time, so it is safe to copy and safe to lose (`history.md`, lineage 4). A whole-set overwrite loses one side's stamps (`chat-protocols.md`, lesson 8), and a delta per call does not (`framework-session-stores.md`, lesson 10).

### 15. A session's stamps are bounded at 16 MiB, and the earliest turns go first

- `SESSION_STAMP_BYTES = 16 * 1024 * 1024`.
- Each row is charged the UTF-8 bytes of its path plus `STAMP_ROW_BYTES = 128`. A row cost 44 bytes beside its path on SQLite without a rowid and 116 with one (run 5). The figure is set above both, because Postgres was not measured.
- The bound is in bytes. At the measured mean path of 57 bytes it is about 90,000 stamps.

**The trim** is a deferred task, which spec 0's decision 24 makes a kind: the `write` of a second `BehindKind`, `STAMP_TRIMS`, named `stamp_trims`, registered after `STAMPS` so that a flush trims after it writes. Its key is `("owner_key", "id")`. For each session of the flush, found by spec 2's `find`:

1. Remove the dead rows: `DELETE FROM vfs_session_stamps WHERE session_key = :k AND NOT EXISTS (<the turn's row>)`. After spec 4.
2. Measure: `SELECT turn_number, sum(octet_length(path) + 128) FROM vfs_session_stamps WHERE session_key = :k GROUP BY turn_number`.
3. If the total is over the bound, remove whole turns, the lowest number first, while more than one turn is left and the total is over three quarters of the bound: `DELETE ... WHERE session_key = :k AND turn_number <= :cut`. The cut is worked out from the measure, so this is one statement.
4. If one turn is left and it is still over three quarters of the bound, remove from it in path order, 5,000 rows to a statement, until it is not: `store.delete_where(transaction, stamps, key=<the three key columns>, where=<the session and the turn>, limit=5000, order_by=stamps.c.path)`.

Each statement binds a fixed number of parameters, which spec 0's decision 25 admits. What bounds the rows they touch is this decision's own bound: a trim holds the SQLite store's writer for one measure and at most a quarter of 16 MiB of deletes, about 23,000 rows.

**When it runs.** The kernel keeps one table in memory, `stamp_bytes`, from a session's owner key and id to the bytes of stamps this process has written for it since its last trim. A trim is put behind when a session enters the table, and again each time its count passes `STAMP_TRIM_BYTES = 1024 * 1024`. The table holds at most `STAMP_COUNTED_SESSIONS = 4096` sessions. Past that the one counted longest ago gives way, and a trim is put behind for it. So a session passes its bound by at most 1 MiB for each process writing to it at once, and a process that serves one request trims each session it stamps once.

- A trim goes down to three quarters of the bound, and not to the bound, so that the next mebibyte does not remove rows again.
- Removing low turns first never brings an older stamp back in front of a newer one.
- A path shown again in a later turn has a row in that turn (decision 5). So a turn-sized trim forgets the files the session has gone longest without being shown.
- Inside one turn no order of touching is stored, so step 4 goes in path order. Until spec 4 lands every row is in one turn, and step 4 is the only eviction.
- A line session's table is bounded in memory by `LINE_STAMP_BYTES = 1 << 20`, charged the same way, and forgets the stamp set longest ago. It is smaller because a line lasts seconds and many lines run at once.

**What forgetting can do.** Under strict, an evicted path is unread: a change to it is refused, and one read clears that. Under `strict=False` an evicted path is unread and is let through, because that is what `strict=False` asks for. Forgetting never lets a write through a strict session.

Reason: the bound is in bytes because a path is up to 1,024 bytes and a count of entries would bound nothing. It is enforced by a measure of the stored rows, because an estimate kept in a process dies with the process, and one process for each request is the normal case.

### 16. A bare line is a strict session of its own, and it is never stored

`fs.cli(line, authority=...)` runs the line through a guarded router whose stamps are a table in memory, made for the line and dropped when it ends. It is strict. It calls nothing of the kernel store. It serves any caller a line can run as, the anonymous caller included, who by spec 2's decision 7 owns no stored session.

`Session.cli(line)` runs the line through the session's own guarded router. Its stamps are the stored session's, with that handle's `strict`. So `cat f` in one line and `sed -i ... f` in the next are one guarded read and write, across two requests.

- `fs.cli("sed -i s/a/b/ /f")` on a file the line never read lands. `sed` reads the file through the line, which stamps it, and writes it back with that stamp (run 4: a `stat`, a `read`, a `write`). The guard is on the time between the two.
- `fs.cli("rm /f")` is refused as unread. `fs.cli("cat /f > /dev/null; rm /f")` and `fs.cli("ls /; rm /f")` land.
- `fs.cli("rm *.log")` lands: the expansion lists the directory through the line (run 4).

Reason: the verification ruled that a line run without a session is its own session. A line that reads a file and writes it back is the case the shell cannot guard itself.

### 17. The shell's host sends what a line is shown and what it changes through the guarded router, and its probes through the kernel

`run_line` takes two routers: one for probes and one for the rest. Both have the shape of `Router` (`src/vfs/shell/programs.py:141`), so the shell still imports nothing above it. `Caller` gains the second beside `fs`.

| Request or program call | Goes through | Stamps |
|---|---|---|
| a read request (`host.py:377`) | the guarded router | yes |
| a list request (`host.py:430`) | the guarded router | yes, with the directory |
| a stat request (`host.py:421`) | the kernel | never |
| the stat of an operand of the served `grep` and `find` (`programs.py:282`, `:501`) | the kernel | never |
| every effect (`host.py:471-493`) | the guarded router | decision 13 |
| the `grep`, `glob`, `search`, `traverse` and `edit` calls of the programs | the guarded router | by their verb |

- A stat request never stamps. The machine asks it before a read, before a redirection, before a removal and for a test (run 4), and the request does not say which. So `[ -f f ]; rm f` in a line is refused as unread, where `session.stat` then `session.delete` in Python lands. The shell has no `stat` program.
- `touch` and a `create_new` write state `if_absent=True` themselves, so their `exists` stays `exists`.
- `HostError` gains two members. `vfs.conflict.unread` prints `File not read yet`. `vfs.conflict.changed` and plain `vfs.conflict` print `File changed`. Today each prints `Invalid argument`. The classified fact is kept on the line's result as a warning, as every refusal inside a line is, and carries the hint.

Reason: a probe that stamped would let `rm f` stamp `f` through its own stat, and strict would refuse nothing in a line.

### 18. A writer that spans chunks carries the etag its last chunk left

The host keeps, for the line, a mapping from a path to the etag of the last accepted write of a writer the line opened there.

- An accepted `truncate` or `create_new` write sets it, from the result's etag.
- An `append` request to a path in the mapping is sent with that etag as a stated `if_match`. When it is accepted the mapping takes the new etag.
- An `append` request to a path not in the mapping is a plain append, with no precondition.
- A refused write takes the path out. The machine's writer has failed and sends nothing again (`files.rs:214-224`).
- An accepted remove or move takes out the path and every path beneath it.
- The mapping is bounded by `WRITING_BYTES = 1 << 20`, each path charged its bytes plus its etag's. Past it, the path set longest ago gives way, and a later chunk of that writer is a plain append.

What follows:

- `cat big > f` is an empty write that makes or empties `f`, then appends (run 4). Each append requires the etag the write before it left. A file replaced, moved or deleted between two of them fails the writer with status 1. Its later chunks are not sent, and the other file is intact.
- `echo x >> log` from twenty lines at once leaves twenty lines.
- `echo a > f; echo b >> f` guards the second write with the first's etag. A rival's write between the two refuses it. That is more than `>>` asks, inside one line.
- Two writers of one line on one file share the path's etag and interleave, as bash's do.
- A writer opened with `>>` on a file the line did not make is not guarded between its chunks. A chunk can land after a rival's append. No byte is destroyed.

Spec 1's decision 4 says the host sends no `if_match`. That holds at spec 1's landing, and this decision changes it.

Reason: decision 10 leaves an append unguarded, so the guard of a continuing chunk has to be stated by the one party that knows the chunk continues a writer. The request names no writer, and the opening mode is the only sign the host has.

### 19. Both faces and both stores share one implementation

The rules live once, in `GuardedRouter` in `src/vfs/stamps.py`. A handle makes one for each call from the values spec 2 gives it, a line holds one, and the synchronous `Session` wraps `AsyncSession` as it does today. The stored stamps and the line's table sit behind one small interface: look up, show, change. The parity test covers `strict=` and the two refusals on the synchronous face.

This spec adds no public call. Every verb through a session returns a `Result`, as ruling 5 of the reconciliation has it. Its public surface is the two members of `ErrorKind`, which `vfs` already exports, the meaning it gives `strict`, and what a session's verbs and `cli` now do.

The constants are module constants and no call takes one as an argument. `LISTING_STAMP_ROWS`, `SESSION_STAMP_BYTES`, `STAMP_ROW_BYTES`, `STAMP_TRIM_BYTES`, `STAMP_COUNTED_SESSIONS` and `LINE_STAMP_BYTES` are in `vfs.stamps`. `WRITING_BYTES` is in `vfs.shell.host`, beside `READING_BYTES`. None is exported from `vfs`.

Reason: a rule written twice drifts, and the synchronous twin already wraps the asynchronous session for that reason.

### 20. Two landings, each green

1. **The rules and the line.** The two kinds and their words. The stamp, `GuardedRouter`, the line's table. `fs.cli` in a line session. The host's two routers, the chunk writer, and the two host errors in the crates. It needs spec 1's four landings. A stored session is not yet guarded.
2. **Stored stamps.** `vfs_session_stamps`, the module `vfs.kernel_store.stamps`, the two kinds written behind, `record_after` for a change, the trim, strict on a stored session, `Session.cli`, and `remove_stamps` in `SESSION_CHILDREN`. It needs spec 0's four landings and spec 2's first. The docs land here.

Spec 4's landings then add the turn to the statements: step 2 of decision 6 and the join to turns in its statement, the join and `live` of decision 7, step 1 of the trim, and the two functions its rewind and fork call. Spec 5's second landing, whenever it lands, gives decision 10 its exact rule.

Reason: the first is of use alone, since it closes the shell's unguarded write-back. The second holds everything that touches the kernel store, so the bound lands with the rows it bounds.

### 21. Other specs reach the stamps through six functions of one module

All are in `src/vfs/kernel_store/stamps.py`, and take the `Transaction` of a `commit`, a `query` or a `record_after` their caller holds. No other spec writes a statement of its own against `vfs_session_stamps`, by ruling 2 of the last round: specs 4, 5 and 8 call these six.

| Function | Who calls it | What it does |
|---|---|---|
| `remove_stamps(transaction, session_key, limit) -> int` | Spec 2's reclaim of a removed session, as a member of `SESSION_CHILDREN`, whose shape spec 2 writes `(session, session_key, limit) -> int` | Deletes at most `limit` rows of `vfs_session_stamps` for one `session_key`, in one statement of a fixed shape, and returns the count. The statement is `store.delete_where` on the three key columns with `session_key = :k` as its `where`. |
| `remove_stamps_from(transaction, session_key, number) -> int` | Step R3 of spec 4's rewind | `DELETE FROM vfs_session_stamps WHERE session_key = :k AND turn_number >= :n`. Every stamp of the session whose turn number is `n` or more goes, live or dead. Two binds. |
| `copy_stamps(transaction, source_key, new_key, number) -> int` | The fork's copy of stamps in spec 4's decision 17, its step F6 | `INSERT INTO vfs_session_stamps (session_key, path, turn_number, kind, etag) SELECT :new, path, turn_number, kind, etag FROM vfs_session_stamps s WHERE s.session_key = :src AND s.turn_number < :n AND EXISTS (<the turn's row>)`. Every stamp of the source whose turn number is below the fork point and whose turn is live is copied as it is, with its turn number. Three binds. |
| `current_stamps(transaction, session_key, paths, turn_number=None)` | Step 2 of decision 8, and spec 5's decision 14 (After a rollback the session remembers a put-back file as the state it saw) | Decision 7. Spec 5 compares the etag it returns with the state its rollback put back. |
| `write_stamps(store, transaction, rows)` | A flush, a change, the function below, and spec 5's decision 14 | Decision 6. |
| `record_change_stamps(store, transaction, *, session, turn_number, call, result)` | Step 7 of decision 8, and spec 7's resumed dispatch, its decision 34 | Works out what a change leaves (decision 13) and calls `write_stamps`. `session` is a `SessionRef` from a handle or a `session_key` from a job. |

- **What a rewind removes.** Spec 4's rewind drains the session's scope, then in its one `commit` removes every stamp row of the session whose `turn_number` is at or above the number of the turn `before` names. Rows of lower turns are untouched, so the session then holds what it held when the turn before ended.
- **What a fork copies.** Spec 4's fork drains the session's scope, then in its one `commit` copies every stamp row of the source whose `turn_number` is below the fork point and whose turn is live, under the new `session_key`, with its `turn_number`, `kind` and `etag` as they are. It copies every such row and not the current ones alone, so the fork can itself be rewound exactly.
- A stamp another process put behind before a rewind and stores after it stores nothing when its handle had a turn. A fork does not hold it.
- Spec 2's removal withdraws this process's waiting stamps with `discard_behind(STAMPS, scope=ref.scope)`. One stored later by another process makes the session again holding that one read, which spec 2's decision 22 accepts under "A late record".
- A job that finishes after its session was removed leaves no stamp, by the join of decision 6. That is what spec 7's decision 34 expects.
- The statements were run on SQLite (run 5).

Reason: one module owns every statement on the table, as rule 2 of spec 0's decision 22 requires, and a spec that removes or copies a session's memory does it without knowing a column.

### 22. What a table is shown is plain JSON, and a guarded router is made from a session key and a turn number alone

Spec 8 journals what a bare line's table was shown and shows it again when the line is resumed (its decision 28, What a bare line was shown is journaled with each entry, and the replay shows it again). Spec 7 carries a job on in a process that never held its handle (its decision 34). Three things serve both.

- **The interface of decision 19 takes values that turn into JSON and back.** `look_up(paths)`, `show(stamps)` and `change(stamps)`, where a stamp is a triple of a path, a kind and an etag or none, all strings. A wrapper that notes each `show` and each `change` and makes them again on a fresh table, in order, leaves that table as the first was.
- **The writer mapping moves by one pure rule.** `after_write(path, mode, etag)` is decision 18's rule for an accepted write, and `after_remove(path)` its rule for an accepted remove or move. Spec 8's replay calls them with the etag each journaled `write` kept (its decision 14), and the mapping is rebuilt for a bare line and for a line of a stored session alike.
- **`GuardedRouter.for_job(fs, session_key, turn_number, authority, strict)`** makes a guarded router with no handle. Its stamps are the stored session's, looked up and written by `session_key`, with no `resolve`. A line of a stored session that is resumed can run through one. Spec 7 takes another road to the same end for a single step: its resume reads the session's id by the job's key, makes a handle with `strict=False` and puts it in the job's turn (its decision 34). That handle makes its guarded router as any handle does.

`strict` is the handle's and is stored nowhere, by spec 2's decision 4. A resumed line of a stored session needs the value its handle had. Spec 8 saves it in the line record (its decision 3, The line record holds everything the machine is started with) and passes it to `for_job`. A single step needs none: its `unread` refusal was judged when the call was made, as spec 7's decision 34 says.

Reason: spec 8's decision 24 needs a bare line that read a file, stopped and then wrote it back to be guarded still, and not refused as unread. Rebuilding the table through its own interface means no stamp rule is written twice.

### 23. A mount that issues no etag is outside the guard

A storage that does not declare spec 1's `etag` trait fills no etag, so its rows leave no stamp. A change whose target lies in such a mount is sent as the caller wrote it: the session fills in nothing and strict refuses nothing there. The guarded router asks the kernel for the mount's trait, which is read with no statement, as the kernel reads it for spec 1's gate.

Every storage in the tree declares the trait.

Reason: without this rule a strict session could never change a file of such a mount. Every change would be refused as unread, and no read could clear it, because no read there leaves a stamp. A guard that cannot be satisfied is the loop this spec exists to prevent.

## Cost

Costed against the reference deployment. Its figures: 150,000 verb calls a day, about three in four of them reads. About 10 actions a prompt and 4 prompts a session, so 40 calls a session and about 3,500 sessions a day. Sessions live 30 days.

**Per verb call.** A read adds no synchronous statement on any engine. In the process it adds one `put_behind` of at most 1,024 rows for a call that is not a `read`.

**Rows written behind.** An *assumption*: a session is shown about 320 rows, 10 listings of 30 rows and 20 single rows. That is about 1,100,000 stamps a day, 13 a second on average and about 50 at the 4× peak. No public measurement of rows per listing exists. A flush of stamps is 2 statements, `resolve` and the store statement, and 3 after spec 4 where a row's handle had a turn.

**Per file write.** A change through a session adds a `query` and a `record_after` on the kernel store. They hold 4 statements: `find` and the lookup, then `resolve` and the store statement. They hold 2 when every stamp the change needs still waits in the buffer, since the lookup is then no statement. After spec 4 a handle with a turn adds one, the removal of later rows. A session's first record costs `resolve` one statement more. At the organic 50,000 writes a day, if every one went through a session, that is about 200,000 statements a day, between two and three a second. The nightly batch runs with no session and pays nothing.

**Per batch.** A 10,000-entry `write` through a session adds 5 statements: `find`, one lookup of 10,000 keys, `resolve`, and two store statements at 6,540 rows to a statement and 5 bind parameters a row. A directory delete or move adds one range read and one store statement for each 6,540 stamps beneath it.

**Per index visit.** Nothing.

**Per corpus.** Nothing reads the whole table. Storage at the assumption above: 105,000 live sessions of 320 rows, at the 101 to 173 bytes a row measured on SQLite, are 3 to 6 GB. The bound is a ceiling on one session and not a forecast: every live session at its bound would be 1.6 TB.

**The trim.** One for each process and session, and one for each mebibyte after. With a process a request that is about 14,000 a day at 4 prompts a session, each a measure over one session's rows.

**Per lock.** A store statement takes row locks on one session's rows, for one transaction. No table is locked. On SQLite the kernel store has one writer, held for one flush or one `record_after`. A change of a session can wait behind one flush. The longest holds are the fixed-bind statements over one session's rows: a rewind's removal, a fork's copy and a trim, each bounded by the 16 MiB of decision 15, about 90,000 rows. A read waits on nothing, because it issues no statement. The kernel store is not the mount's file, so nothing here waits behind a batch.

**Memory.** The store's buffer, at most 16,384 rows. The kernel's `stamp_bytes`, at most 4,096 entries. A line's table, up to 1 MiB for the length of the line. The host's writer mapping, 1 MiB.

**Time.** Not measured. The study found two log transactions a write cost a write 151 ms on Postgres under 32 sessions, and suspected the pool without confirming it. A change's two transactions here are the same shape.

## Left as it is

- **What is beneath a copied or a restored directory is not stamped.** The result names the directory alone, a copy's entries are new, and spec 5's `Change` reports nothing for a row beneath.
- **A directory a `write(parents=True)` made is not stamped in a tree without `Result._changes`.** Decision 13 covers it where the tree has it.
- **A stat inside a line never stamps.** The request would have to say whether its answer is printed.
- **A writer opened with `>>` is not guarded between its chunks.** The request would have to name its writer.
- **A directory is not held to its etag by a session.** Decision 11 gives the reason and the caller's own way.
- **No stamp travels with a request.** A host that keeps state itself could send its stamps as HTTP sends `If-Match`. Nothing here prevents it.
- **Stamps over MCP, without a session object**, is roadmap decision D51.
- **A count of refusals, and a body inside a refusal.** The host's wrapper does both.
- **The first write of a redirection is sent twice** when its source cannot be opened (run 4: two empty writes for `head -c N /dev/zero > f`). It is a shell defect that spec 8 found too, and it needs a spec of its own. The second write passes here, since the first left its etag.

## Tests

Each is written and seen failing before the code. Counts are of statements recorded by a `before_cursor_execute` listener on `KernelStore.engine` or on a mount's engine, of calls seen by a recording storage, of rows, of refusals, or of an exit status. Never of time. A count on the kernel store leaves out `BEGIN` and `COMMIT`. "Both stores" means the line's table and a stored session, on memory, on a SQLite file and on the Postgres leg.

`tests/results/test_facts.py`:

- `test_the_two_session_refusals_render_as_the_guide_prints_them`: the two rendered lines equal the guide's two lines, character for character.
- `test_a_session_refusal_carries_no_data_and_is_not_retryable`: `data is None` and `retryable is False` for both.
- `test_an_unknown_child_of_a_session_refusal_reads_as_it`: `kind_family("vfs.conflict.changed.x")` is `changed`. Both kinds raise `WriteConflictError`.

`tests/session/test_stamps.py`, on both stores:

- `test_a_change_to_a_file_that_moved_on_is_refused`: read, a rival's write, the session's edit. One `changed` error, zero mutation statements on the mount, and the rival's body intact.
- `test_a_refusal_moves_no_stamp_and_one_read_clears_it`: the edit three times gives three equal refusals. One read, and the fourth lands. Counted: 3 refusals, 1 read.
- `test_a_path_that_was_freed_is_refused`: four cases, a move away followed by a write, a move or a copy of another file to the path, and a move of the parent. Each `changed`.
- `test_a_delete_and_a_recreate_is_refused`.
- `test_a_session_reads_its_own_writes`: read, write, write. Both land, with no refusal.
- `test_a_stated_precondition_reaches_storage_unchanged`: the recording storage sees the caller's `if_match`. Its refusal is `vfs.conflict` with `version` and `etag`.
- `test_strict_refuses_what_was_not_shown`: one case a verb, as a named caller and as the system authority. `edit`, `delete` and `move` give `unread` and the recording storage sees 0 calls. A `write` of an absent path makes it. A `write` over an occupant gives `unread` and the body is intact.
- `test_without_strict_an_unread_change_goes_through_and_a_changed_file_does_not`.
- `test_each_read_verb_stamps`: one case each for `read`, `stat`, `ls`, `tree`, `glob`, the three modes of `grep`, `search` and `traverse`. A delete of a returned path then lands. A row with no etag stamps nothing.
- `test_rows_in_hand_stamp_nothing`: `glob(observations=...)` with a made-up etag, then a delete. Refused as unread.
- `test_a_listing_stamps_at_most_the_cap`: `ls` of 1,500 files leaves 1,024 stamps, the directory among them. A delete of the first row lands and of the last is refused as unread.
- `test_a_listed_directory_can_be_removed`: `ls /d`, then `delete /d`. Without the `ls`, `unread`.
- `test_a_read_that_finds_nothing_clears_a_stale_stamp`: stamp, a rival's delete, a write refused as changed, a read answered `not_found`, a write that makes the file. Counted: 1 refusal.
- `test_an_append_is_never_refused_and_does_not_launder`: read, a rival's append, the session's append lands and the file has every line. The session's overwrite is then `changed`. And read, append, overwrite with no rival: all land, in a tree with `_changes`.
- `test_a_session_can_remove_what_it_filled`: `mkdir`, two writes inside, `delete` of the directory. 0 refusals.
- `test_a_removed_directory_takes_its_stamps_with_it`: stamp three files beneath, delete the directory, write one of the paths. Made, with 0 refusals.
- `test_a_moved_directory_carries_its_stamps`: stamp a file beneath, move the directory, edit the file at its new path with no read. Lands.
- `test_a_batch_write_fills_each_path`: three stamped and two new entries land. With one stamped file changed, no row lands and the error names that path. With one new path occupied, no row lands and that path is `unread`.
- `test_a_mount_without_etags_is_outside_the_guard`: a recording storage that declares no `etag` trait. An `edit` of an unread file there is dispatched with no `if_match`, and 0 refusals.
- `test_a_lookup_that_fails_refuses_the_change`: the store's `commit` raises. The refusal is the exception's `error`, and the recording storage sees 0 calls.
- `test_a_record_that_fails_keeps_the_change`: `record_after` returns its warning. The result is a success that carries it, and the next edit is `changed`.
- `test_a_line_table_forgets_the_stamp_set_longest_ago`: `LINE_STAMP_BYTES` patched to 4 KiB. The first path stamped is `unread`, the last is not.
- `test_a_table_is_rebuilt_from_what_it_was_shown`: every `show` and `change` of one line table, noted, turned into JSON and back, and made again on a fresh table. `look_up` then answers the same for every path. The writer mapping rebuilt by `after_write` and `after_remove` equals the first.
- `test_a_guarded_router_is_made_from_a_key_and_a_turn`: `GuardedRouter.for_job` on a second kernel that never held the handle. A write through it lands on the session's stamp and records its own, and 0 statements name `owner_key`.
- `test_a_batch_write_is_one_call`: three stamped and two new entries reach the recording storage as 1 call, whose `if_matches` holds three etags and `ABSENT` twice.

`tests/session/test_stamp_statements.py`, on a SQLite file and the Postgres leg:

- `test_a_read_through_a_session_adds_no_statement`: one case a read verb, and one for a read answered `not_found`. With the store's task held, the statements on `KernelStore.engine` are 0, and those on the mount equal those of the same call on the kernel. After the task runs, for a session that already has its row: 2, `resolve` and the store statement.
- `test_a_change_reads_the_buffer_and_records`: a read with the store's task held, then an edit. The edit lands with no flush between, on 2 statements. With the task run first, on 4.
- `test_a_change_withdraws_what_waits_for_its_paths`: a stale stamp of the path put behind while the edit runs is gone from `waiting_behind` after step 7, and the lookup after shows the edit's etag.
- `test_ten_thousand_paths_are_looked_up_within_the_budget`: 1 lookup statement at the engine's budget, 10 with `membership_budget` narrowed to 1,000, and none over it. Marked `slow`.
- `test_a_ten_thousand_entry_write_records_in_two_statements`: 5 statements in all. Marked `slow`.
- `test_the_last_stamp_to_arrive_is_current`: the cases of run 5 as a table of rows before, rows written and the lookup after: two turns, a lookup with no stamp, an earlier turn's newer show, a straggler and the read that clears it, an absence, a directory, a dead row.
- `test_a_stamp_of_a_gone_session_or_turn_stores_nothing`: the seven cases of decision 6, each a count of rows returned.
- `test_the_rows_of_one_write_are_unique`: two stamps of one path in one flush bind one row, the last.
- `test_a_directory_delete_reads_its_stamps_by_range`: 3,000 stamps beneath: 1 range statement and 1 store statement.
- `test_a_batch_of_directories_reads_ranges_within_the_depth`: 1,200 directories in one `delete`: 3 range statements.
- `test_two_processes_meet_in_the_store`: two kernels on one database. A reads with its task held, B's edit is `unread`. A's task runs, B's edit lands. Counted: 1 refusal.
- `test_a_job_of_a_removed_session_leaves_no_stamp`: `record_change_stamps` with a `session_key` whose row is a marker writes 0 rows.
- `test_remove_stamps_takes_a_chunk`: 12,000 rows, `limit` 5,000: 5,000, 5,000, 2,000, 0.
- `test_remove_stamps_from_a_turn_and_copy_below_one`: the rows of run 5. A rewind before turn 5 leaves the turn-4 rows. A copy below 6 holds the rows of live turns below 6 and no dead one. Each is 1 statement.
- `test_current_stamps_gives_the_kind_and_the_etag`: a file, a directory, an absence and a path with no stamp, in 1 statement, with `live` true for a stored turn and false for a removed one.
- `test_the_trim_removes_the_lowest_turns_first`: the bound patched to 4 KiB, rows in three turns. After the trim the total is at or under 3 KiB and every row left is of the highest turns. Counted: 1 measure and 1 delete.
- `test_the_trim_inside_one_turn_goes_in_path_order`: one turn over the bound. The rows left are the last in path order.
- `test_the_trim_removes_dead_rows`: after spec 4.
- `test_a_session_is_trimmed_on_entry_and_each_mebibyte`: the count of `stamp_trims` rows put behind, and one more when a session gives way from `stamp_bytes`.
- `test_forgetting_refuses_under_strict`: an evicted path is `unread`, and one read clears it.

`tests/shell/test_host.py`:

- `test_a_line_guards_a_read_and_a_write_back`: `cat /f` then `sed -i` with a rival's edit between them. `sed` fails, `/f` keeps the rival's body, standard error holds `File changed`, and the evidence holds one `vfs.conflict.changed`.
- `test_sed_in_place_on_a_file_the_line_never_read_lands`, and with a rival between its read and its write, is refused.
- `test_a_line_refuses_to_remove_what_it_was_not_shown`: `rm /f` exits 1 with `File not read yet` and `/f` is there. `cat /f > /dev/null; rm /f` and `ls /; rm /f` exit 0.
- `test_a_test_in_a_line_never_stamps`: `[ -f /f ]; rm /f` exits 1, and the guarded router sees 0 `stat` calls.
- `test_a_replaced_file_fails_its_writer`: `cat /big > /f` with a replacement of `/f` after the empty write. Status 1, 2 writes dispatched, the replacement intact.
- `tests/shell/test_engines.py::test_lines_that_append_at_once_lose_no_line`, which exists, still passes.
- `test_a_line_can_append_to_a_path_it_removed`: `echo a > /f; rm /f; echo b >> /f` leaves `b`.
- `test_the_writer_mapping_is_bounded`: `WRITING_BYTES` patched small. A later chunk of the writer that gave way is sent with no `if_match`, counted on the recording storage.
- `test_a_bare_line_stores_nothing`: 0 statements on `KernelStore.engine` and an empty buffer, for a named caller and for the anonymous caller.
- `test_two_lines_of_one_session_are_one_guard`: `Session.cli("cat /f")`, then `sed -i` through a second handle of the same session. It lands. With a rival's edit between, it is refused.

`tests/test_sync.py`:

- `test_the_sync_session_refuses_as_the_async_one_does`: the two refusals and `strict=False` on `Session`.
- `test_a_sync_session_verb_is_the_facade_call_with_the_authority_filled_in` (`tests/test_sync.py:620`) is rewritten. Through a session the recording storage now also sees the precondition filled in.

## Scope

Files, by landing.

1. `src/vfs/stamps.py`, new: the stamp, `GuardedRouter`, the line's table and the writer mapping's rule. `src/vfs/results/kinds.py`: two members and two rows. `src/vfs/base.py` and `src/vfs/sync.py`: `cli`. `src/vfs/shell/host.py` and `src/vfs/shell/programs.py`: the two routers, the writer mapping, the two host errors. `crates/vfs-shell/src/machine/mod.rs`, `crates/vfs-core/src/shell_binding.rs` and `crates/vfs-shell-wasm/src/wire.rs`: two members of `HostError` and their words. The tests of `tests/results`, `tests/shell` and the line's half of `tests/session`. Every test under `tests/shell` that removes, moves or overwrites, through `fs.cli`, a file its line was not shown is changed to show it first or to expect the refusal.
2. `src/vfs/models/kernel_rows.py`: the table. `src/vfs/kernel_store/stamps.py`, new: the two kinds and the six functions. `src/vfs/stamps.py`: the stored stamps. `src/vfs/base.py`: the two kinds registered when the kernel is built, and `stamp_bytes`. `src/vfs/session.py` and `src/vfs/sync_session.py`: each verb through the guarded router. `tests/session`, `tests/test_sync.py`. The docs. `tests/lint/allowlist.py`, where a listed module grew.

Out: everything under "Left as it is", and what the other eight specs own.

## What the docs must say

- A session remembers each file it is shown, by the file and its version, and stores that in the database.
- A change to a file that changed since is refused, and so is a change to a file the session was never shown. One read clears either. A session's own writes never cause one.
- Making a file and appending to one need no read.
- A listing counts for the directory listed and for its first rows, 1,024 stamps in all.
- A read costs the same with a session as without.
- For a host whose process ends after each request, the guide gains this sentence in step 3, after "a second read": "If your process ends after each request, close the file system before it ends, and what the session has seen is stored first."
- A refusal is the same however often the call is sent. A tool wrapper that sees `vfs.conflict.changed` or `vfs.conflict.unread` reads the file and returns it with the refusal.
- A shell line with no session guards itself for the line and stores nothing. It refuses to remove, move or overwrite a file it was not shown. A test such as `[ -f f ]` is not a read.
- `strict=False` protects only what the session still remembers.

Pages: `documentation/how-to/keep-a-session-for-each-conversation.md`. The `ErrorKind` docstring, for the two kinds and that they carry no `data`. The docstrings of `cli` and of the session's `write`, `edit`, `delete` and `move`. `documentation/reference/shell.md`. `documentation/reference/glossary.json`, for stamp and strict.

## Earlier decisions this reverses

- **The spec merged from pull request 42, decisions 3 to 9.** A stamp was held in the session object and dropped by `close()`. It is now a stored row. The bound was 64 MiB in memory with the least recently touched evicted. It is 16 MiB of stored rows with the earliest turns evicted. The refusals were `conflict` with `data["reason"]`. They are two kinds with no `data`. An append to a stamped file carried `if_match`. It carries none. A directory carried `if_match`. It carries none. It said eviction never makes a call succeed. That holds under strict alone. Its test expected `fs.cli("sed -i ...")` on an unread file to be refused. It lands.
- **Ruling 6 of the verification**, that a multi-chunk writer is guarded by its stamp, each append refreshing it and the next requiring it. The outcome is kept. The etag is carried by the host and stated, because an append no longer takes a precondition from a stamp.
- **The docstring of `src/vfs/session.py`**, that a call through a session and the direct call return the same result and that a session is sugar. A session can now refuse what the kernel would do.
- **The first draft of this spec, where the reconciliation overruled it.** It stored an etag as an entry key and a version, and let a higher version of one entry win. Ruling 3 forbids taking an etag apart, so decisions 4, 5 and 10 are as they now read. It kept a table of waiting stamps in the kernel and wrote a change's stamps under a shield. Spec 0's `waiting_behind`, `discard_behind` and `record_after` replace both, so decision 8 is as it now reads. It sent an unstamped write with `if_absent=True` and a mixed batch as two calls. Spec 1's `ABSENT` replaces both, so decision 9 is as it now reads. It gave a host a drain to call. Decision 8 gives none.
- **Roadmap story K10**, already superseded by the merged spec.

## Choices for the owner

Each is decided above, and stands until it is ruled on.

1. **Listings stamp, up to 1,024 stamps a call.** The other choices are bodies alone, which forces a read before a removal, and no cap, which lets one `glob` fill the buffer.
2. **The bound is 16 MiB a session, and the earliest turns go first.** A line's is 1 MiB.
3. **A refusal carries no current version and no etag.** The session study's lesson 4 said to carry the version. This spec holds that an etag shows a model nothing and invites a write over an unseen body.
4. **An append is never guarded by a stamp.** The merged spec guarded it.
5. **A bare `fs.cli` line is strict.** `fs.cli("rm /f")` on a file the line was not shown is refused.
6. **A directory needs only to have been shown.** No precondition is sent for one, so a directory swapped for another after it was listed is removed without a refusal.
7. **The session rules hold for the system authority.**
8. **The stamp that arrives last wins.** Two shows of one file from two processes can leave the older in front, at the cost of one refusal. The other choice needs a counter that a read would have to fetch.
9. **A mount that issues no etag is outside the guard,** and not refused.
10. **No public call flushes the writer.** `close` flushes it, and a host whose process ends after each request closes the file system first. A process frozen with no chance to close can lose its last reads, at the cost of a refusal. The other choice is a new public name, which the overview's list does not hold.

## Where this spec disagrees with the overview or the guides

With the overview: nothing.

With `documentation/how-to/keep-a-session-for-each-conversation.md`:

1. **"Forgetting never lets a write through that would have been refused."** True of a strict session. With `strict=False` a forgotten stamp makes the file unread, and an unread file is let through. Proposed: begin the sentence "In a strict session," and add to the paragraph on `strict=False` that it protects only what the session still remembers. The same holds for a read lost when a process stops, in step 3. Evidence: decision 15, and the meaning the guide itself gives `strict=False`.
2. **"Reading the file, or listing the directory it is in, is enough."** A listing counts for 1,024 stamps. Proposed: add "A listing of more than about a thousand rows counts for the first of them." Evidence: decision 3.
3. **The hint of "Not read yet" says "Read it first".** A directory cannot be read (run 2: `wrong_kind`). Proposed hint: "This file has not been read in this conversation, so nothing was changed. Read it first, or list it if it is a directory, then make the change." This spec keeps the guide's words until that is ruled on.
4. **"the session forgets the files it has gone longest without touching."** True by turn. Inside one turn no order is stored, and rows go in path order. Proposed: "the session forgets what it was shown in its earliest turns first."

5. **Step 3 says nothing to a host whose process ends after each request.** Proposed, after "the worst that follows is a "Not read yet" refusal and a second read.": "If your process ends after each request, close the file system before it ends, and what the session has seen is stored first." Evidence: decision 8, and spec 0's decision 19.
6. **"A shell line run with `fs.cli(...)` and no session guards itself for the length of the line, so a command that reads a file and writes it back is still protected."** True, and it leaves out the other half of the guard. Proposed: add "It also refuses to remove, move or overwrite a file the line has not read or listed." Evidence: decision 16.

## Needs no other spec meets yet

One item is open. Three others of the round before were read again in the last round, in the owners' text as it was being revised, and are met.

1. **Spec 4, decisions 12 and 17: the columns of `vfs_session_stamps`.** Its R3 and F6 are written with `session`, `turn`, `entry` and `version`, the columns of this spec's first draft. Ruling 3 ended `entry` and `version`, and spec 0's ninth point names a session by `session_key`. Text needed for R3: "`remove_stamps_from(transaction, :k, :n)`, which is `DELETE FROM vfs_session_stamps WHERE session_key = :k AND turn_number >= :n`." For F6: "`copy_stamps(transaction, :src, :new, :n)`, which is `INSERT INTO vfs_session_stamps (session_key, path, turn_number, kind, etag) SELECT :new, path, turn_number, kind, etag FROM vfs_session_stamps s WHERE s.session_key = :src AND s.turn_number < :n AND EXISTS (SELECT 1 FROM vfs_session_turns t WHERE t.session_key = s.session_key AND t.number = s.turn_number)`." What is missing: when this was last read, R3 and F6 were still statements of spec 4's own, with the old columns. Ruling 2 of the last round decides it: spec 4 calls the two functions.

Met, and no longer listed:

- **Spec 0: a kind written both behind and synchronously, with no counter.** Rule 7 of its decision 22 and its decision 24 now admit such a kind, where the spec reads `waiting_behind` before its synchronous write and calls `discard_behind` for the keys it writes. Decision 8 here does both.
- **Spec 8: the `strict` of the handle a line ran through.** Its line record now keeps `strict`, null for a bare line, in its decision 3, and its decision 24 makes the resumed router with it.
- **Spec 5: the functions its decision 14 calls.** It now calls `current_stamps` and `write_stamps`, and writes no statement against the table.

What other specs asked of this one in their own lists at `7c383f32`, and where each is met:

- **Spec 0, item 4:** no table kept beside the buffer; `waiting_behind` and then the store at step 2, `discard_behind` at step 7. Met by decision 8, in those calls. Its note that a flush after a declared delay is met by a flush with no delay is taken: decision 8 states the window as one flush.
- **Spec 0, item 5:** a public name for a drain, if one is wanted. None is added, by ruling 4 of the last round. Decision 8 gives the host's way, `close`, and the guide's sentence is under "What the docs must say". It stays choice 10.
- **Spec 1, its two needs it does not meet:** a function that takes an etag apart, and a way to know that two rows are one entry. Neither is needed any longer. Decision 4 keeps the etag whole. Decision 5 replaces a stamp by any later one, with no comparison of entries. Decision 10 moves a stamp after an append only when spec 5's `etag_before` equals it. These are the rules spec 1 proposes.
- **Spec 2, item 1:** `remove_stamps(session, session_key, limit) -> int` deletes at most `limit` rows of `vfs_session_stamps` for one `session_key`, in one statement of a fixed shape, returns the count, and joins `SESSION_CHILDREN`. Met by decision 21, under that name and shape.
- **Spec 2, item 2:** a handle keeps the owner key and the id and never the session key, and each store and each lookup gets the key from `resolve` or `find` in the transaction that uses it. Met by decision 8, in those words, and the cost is counted for every change.
- **Spec 4, item 1:** the current stamp is the row of the highest live turn, with the outer row and the `max` both filtered by spec 4's predicate. Met by decision 7. Ruling 6 of the last round confirms it.
- **Spec 4, item 2:** the lookup also says whether the handle's turn is live, and a dead one is refused `vfs.not_found` with spec 4's words and nothing dispatched. Met by decision 7 and step 3 of decision 8.
- **Spec 4, item 3:** a session's stamps are put behind with the scope of its owner key and id. Met by decision 8, as spec 2's `ref.scope`.
- **Spec 4, its unmet need of this spec's first draft:** a turn fixed for a handle with none. Spec 4 does not meet it and says why. This spec accepts the case as spec 4's decision 7 states it (decision 14 here).
- **Spec 5, item 1:** a file stamp keeps the etag it was made from, and `current_stamps(session, session_key, paths)` returns each path's kind and, for a file, that etag. Met by decisions 4, 7 and 21. The guarded router and step 7 of decision 8 keep those names.
- **Spec 8, item 6:** `show` and `change` take values that turn into JSON and back, and a guarded router is made from a session key and a turn number alone. Met by decision 22.

What other specs ask of this one under their "Builds on":

- Spec 2: a guard of its own for a line run by a caller that owns no session. Decision 16.
- Spec 6: the two refusals judged before a policy wherever the storage is not needed. Decision 12: `unread` for `edit`, `delete` and `move`, at step 3 of decision 8. The other cases are the storage's own answer, or spec 7's at its preview.
- Spec 7: stamps written for a session and a turn with no handle of the first process. Decision 22. The `unread` refusal judged before any policy. Decision 12.
- Spec 8: the line session and its table, the two routers, the writer mapping and the table's interface, its decisions 16 to 19 as cited. Decisions 16 to 19 and 22 here.

## Not checked

- **Postgres.** No server was available. To run on a Postgres server, each through SQLAlchemy as the store will build it: the store statement of decision 6, with its `VALUES` list as a source, its two joins, `ON CONFLICT ... DO UPDATE` and `RETURNING`; the lookup of decision 7 with its `LEFT JOIN` from one constant row; the `DELETE` of later rows; the four statements of the trim; `copy_stamps`, `remove_stamps_from` and `remove_stamps`; and `EXPLAIN` of the lookup, to confirm the primary key serves it. Then `SELECT pg_total_relation_size('vfs_session_stamps')` over 100,000 rows, for the bytes a row.
- **Two flushes at once on Postgres.** At READ COMMITTED, two transactions that each remove later rows and store one path can both commit. Run two `write_stamps` of one path from two connections, in both orders, and read the current stamp: it must be one of the two.
- **A flush and a rewind at once on Postgres.** Spec 4 reasons that they can leave one dead row. Run a `write_stamps` for turn `n` and `remove_stamps_from` at `n` with the turn's delete, from two connections, and count the rows of turn `n` left: `current_stamps` must return none of them.
- **The time a change's two transactions add** under 32 sessions, on either engine.
- **Rows shown per session.** The 320 is an assumption, and with it the 3 to 6 GB and the 13 rows a second.
- **The turn statements against spec 4's code.** Run 5 used a turn table of two columns. `make_first_turn` and the handle's turn were not run, since spec 4 is not built.
- **`Result._changes`.** Decision 10's rule was not run, since spec 5 is not built.
- **The tests strict changes.** How many tests under `tests/shell` remove, move or overwrite, through `fs.cli`, a file their line was not shown was not counted.
- **The other eight specs after they were read.** Each was being revised. A heading cited here may have changed, and a need listed above may since be met. Spec 7 was read before and after its revision, and specs 5, 6 and 8 for their text on this spec alone.

## One line

A session stores, per path and turn, the etag it was shown, puts that behind a read and records it after a change, and refuses a change to a file that moved on or that it never saw, in words that one read clears.
