# The session remembers what it read, and refuses a change to a file that moved on

A draft, written on 2026-11-22. It is not reviewed, and nothing is built. It replaces, at this path, the spec merged from pull request 42, whose decisions 1 and 2 (the etag and `if_match`) moved to spec 1 and whose decisions 3 to 9 are rewritten here. It rests on the map of the nine specs (`agents/2026-11-22-the-specs-for-jobs-and-sessions/overview.md`), the guide `documentation/how-to/keep-a-session-for-each-conversation.md`, five of the session studies under `agents/2026-11-22-a-session-is-stored-named-and-forked/research/` (`coding-agent-sessions.md`, `chat-protocols.md`, `langgraph-threads.md`, `framework-session-stores.md`, `history.md`), the log cost study (`agents/2026-11-21-what-a-log-row-per-call-costs/research.md`), the rulings at the end of `agents/2026-11-22-shell-review/reviews/verification.md`, and four scripts run on 2026-11-22 against the branch `a-job-is-interrupted-and-resumed` at `6dae6a1d`, cited below as runs 1 to 4. Specs 0, 1, 2, 4 and 7 were being drafted at the same time and were not read. What this spec needs from each is stated as a need under "Builds on".

## The outcome wanted

An agent reads `/notes/plan.md` through its session in one request. Ten minutes later, in another request served by another process, it edits the file through the same session. If the file is as the session saw it, the edit lands. If another caller changed it, or it is now a different file at that path, nothing is written and the call is refused with the words "Changed since it was read". A change to an existing file the session was never shown is refused with "Not read yet". The caller's code carries no version. One read clears either refusal. A session's own writes never cause one. A shell line gets the same guard, with or without a stored session.

## Builds on

Each line gives the state on 2026-11-22.

- **The write preconditions**, `agents/2026-11-20-write-takes-preconditions-and-an-append/`. Landed. `write(if_version=, if_versions=, if_absent=, append=)`, the guard on the material `UPDATE`, `conflict` with the current `version`, `exists` with `version` and `content_hash`.
- **The log cost study**, `agents/2026-11-21-what-a-log-row-per-call-costs/research.md`. Done. A row written behind adds zero synchronous statements to a read. On SQLite the kernel's rows need a file of their own.
- **Spec 0**, `agents/2026-11-22-the-kernel-keeps-records-of-its-own/`. Drafted at the same time as this spec, and not read. Needed:
  1. A submit that takes rows for a kernel table, issues no statement and does not wait.
  2. A waiting row is replaced by a later row submitted with the same key, and can be withdrawn by that key. Here the key is the session's address and the path.
  3. The writer tells the submitter when a row is stored and when a row is dropped. A row is dropped when the buffer is full or the store refuses it.
  4. A flush when a declared number of rows wait, and when the oldest waiting row has waited a declared delay. This spec's window is that delay. One second or less is needed, because a model takes longer than that between two tool calls.
  5. A drain, on both faces: it returns when every row submitted before it is stored or dropped. `close` drains.
  6. A synchronous path: one statement on the kernel store, now, in a transaction of its own, with the waits and retries a change has.
  7. A deferred task of the owning table, run by the writer in order with its rows. The trim of decision 15 is one.
  8. Rows chunked to a statement by the live parameter budget, as `rows_per_statement` does (`src/vfs/storage/backends/database/dialects.py:580`).
  9. A statement of the kernel store is attributed to the call that issued it, so a test counts a call's synchronous statements. The study did this with `before_cursor_execute` and a context variable.
- **Spec 1**, `agents/2026-11-22-a-row-carries-an-etag-and-a-change-can-require-it/`. Drafted at the same time as this spec, and not read. Needed:
  1. `Observation.etag` on every row that has a version, whatever `columns` names. `version` is filled that way today (run 4).
  2. `if_match=` on `write`, `edit`, `delete` and `move`, checked inside the transaction that changes the row.
  3. A carrier for a precondition per path on each batch form: `write(entries=)`, `edit(observations=)`, `delete(observations=)` and `move(moves=)`. This spec calls it `if_matches`, a mapping from path to etag.
  4. A marker in that mapping that requires no live row at a path, so one batch can hold `if_match` for some paths and "must be absent" for others. Today `if_absent` is one flag for the whole call and is refused beside `if_versions`. Decision 9 says what is done without the marker.
  5. Two functions private to the kernel: one takes an etag apart into its entry key and its version, one puts them back. The entry key is at most 255 characters, and two rows have one entry key only when they are one entry of one mount.
  6. The etag on each row a change returns: `write`, `edit`, `move`, `copy`, `mkdir` and `restore`.
- **Spec 2**, `agents/2026-11-22-a-session-is-stored-named-and-forked/`. Drafted at the same time as this spec, and not read. Needed:
  1. The owner key of an authority, derived with no statement.
  2. A statement that turns an address (owner key and session id) into the session's surrogate key, making the session row when there is none. A stamp is something to remember.
  3. `strict` is an argument of the handle, read at each call, and stored nowhere.
  4. `session.delete()` and the expiry of a session remove its rows in `vfs_session_stamps`, and drain this process's writer first.
  5. A ruling on a flush that reaches the store after its session was deleted. A row addressed by key stores nothing then (decision 6). A row addressed by owner key and id would make the session again, with one stale stamp in it.
- **Spec 4**, `agents/2026-11-22-a-session-works-in-turns-and-rewinds-or-forks-at-one/`. Drafted at the same time as this spec, not read, and built after it. Needed:
  1. The number of the turn a handle is in: an integer the store hands out, never used twice in one session, known to the handle with no statement once `start_turn` has returned. Until spec 4 lands every stamp carries turn number 1.
  2. For a handle on which no turn was started, the number is fixed before a stamp of that handle is stored. If spec 4 finds it only when the row is stored, a rewind that lands between a read and its flush leaves that read's stamp in the latest kept turn, and spec 4 owns closing that.
  3. Spec 4 changes the liveness test of the store statement (decision 6) from "the session row exists" to "the turn row exists".
  4. A rewind to before turn `n` removes every row of the session whose `turn` is `n` or more, and every waiting row of this process for those turns. It drains first.
  5. A fork copies every row of the source whose `turn` is before the fork point, or every row when `before` is `None`, under the new session's key with the turn numbers the copied turns carry. It drains first. It is one `INSERT ... SELECT`, whose work is bounded by decision 15.
  6. A ruling on a call through a handle whose turn a rewind removed. Its stamps store nothing.
- **Spec 7**, `agents/2026-11-22-a-job-is-interrupted-and-resumed/`. Drafted at the same time as this spec, and not read. Needed:
  1. A job stores the address of its session and the number of its turn.
  2. The precondition a session filled in is part of the saved step. A change resumed after a wait is still held to the file the agent saw.
  3. A resumed job's change runs through the guarded router of decision 9 for that session, so its result refreshes that session's stamps, in whichever process resumes it.
- **The shell**, `src/vfs/shell/` and the nine drafts under `agents/2026-11-22-shell-*`. The shell is landed. The drafts are not built, and four of them (file reads, descriptors, file operations, sed edits) hand their guards to this spec.

## Terms

- **Etag.** Spec 1's opaque string for one entry at one version. It has two parts, the **entry key** and the **version**.
- **Stamp.** A session's memory of one path. It is one of three kinds: a **file** stamp (an entry key and a version), a **directory** stamp (the session was shown that a directory is there), or an **absent** stamp (the session was shown that nothing is there, or removed what was).
- **Shown.** A row is shown to a session when a call through that session returns it and the store produced it in that call.
- **Current stamp.** The one stamp of a path that a session acts on.
- **Strict.** The rule that a session does not change an existing file or directory it holds no stamp for.
- **Address.** What names a session with no statement: its owner key and its id. Once known, also its surrogate key and its turn number.
- **Kernel store.** Where the kernel keeps its own records, owned by spec 0.
- **Written behind.** Handed to spec 0's writer and stored later, after the call has returned.
- **Pending table.** The stamps one process has submitted and not yet heard are stored or dropped.
- **Window.** The time between a read's return and the flush that stores its stamps.
- **Guarded router.** The kernel's verbs wrapped with the rules of this spec. A session holds one. A line holds one.
- **Probe.** A call the shell's host makes to decide how to run a command. Its row is never printed. (The scripts behind this spec are called runs, to keep the two apart.)
- **Line session.** The strict, unstored session a bare `fs.cli` line runs in.

## What the code does today

Run or read on 2026-11-22 at `6dae6a1d`. The four runs are scripts kept outside the repository. Runs 1, 2 and 4 call the public verbs on an in-memory kernel. Run 3 runs the statements of decisions 6, 7 and 15 on SQLite 3.50.4.

| Fact | How it is known |
|---|---|
| A session holds an authority, a closed flag and the kernel, and nothing else. | Read, `src/vfs/session.py:61-66`. |
| Every session verb is the kernel's verb with `authority=` filled in. `edit`, `delete` and `move` take no precondition. | Read, `src/vfs/session.py:97-106`, `:181-203`, `:258-266`. |
| The synchronous session wraps the asynchronous one. | Read, `src/vfs/sync_session.py:36-49`. |
| `open_session` returns a new object on each call, and nothing is stored. | Read, `src/vfs/base.py:655-663`. |
| `cli` runs a line straight on the kernel. `Session.cli` does the same with the session's authority. | Read, `src/vfs/base.py:1668-1677`, `src/vfs/session.py:414-417`. |
| The shell's host answers every request with a public verb of one router. A read, a stat and a listing are `read`, `stat` and `ls`. Every effect is one of `write`, `mkdir`, `delete`, `copy`, `move`. | Read, `src/vfs/shell/host.py:369-437`, `:471-493`. |
| A stat request is asked for a printed `stat`, for a test, and before a redirection and a removal. The host cannot tell them apart. | Read, `src/vfs/shell/host.py:420-427`. |
| The served `grep -r` and `find` each stat their operands first. | Read, `src/vfs/shell/programs.py:282`, `:501`. |
| A file writer's first flush carries its opening mode. Every later flush is `append`. The request names a path, bytes and a mode, and no writer. A refused writer sends nothing again. | Read, `crates/vfs-shell/src/machine/files.rs:195-224`, `crates/vfs-shell/src/machine/mod.rs:174-178`. |
| A refusal whose kind the host has no word for prints `Invalid argument`. `conflict` is one. | Read, `src/vfs/shell/host.py:94-102`, `:495-505`, `crates/vfs-shell/src/machine/mod.rs:244-257`. |
| An error line is the severity, the path, the message, then the kind's hint and retry class. A child kind takes its own row of `KIND_CONTRACTS` when it has one. | Read, `src/vfs/results/render.py:93-123`, `src/vfs/results/kinds.py:161`, `:314-329`. |
| `Observation` carries `version` and `content_hash`, and no etag. | Read, `src/vfs/models/entry.py:451-460`. |
| `version`, `kind` and `path` come back on every row whatever `columns` names. | Run 4. |
| A change returns the changed row with its new version and its kind. A move and a copy return the destination row alone. A directory delete returns the directory row alone. `mkdir(parents=True)` returns each directory it made. `write(parents=True)` returns the file alone. | Runs 1 and 4. |
| A directory's version moves when a direct child is made, removed, moved or copied. It does not move when a child's body changes. | Run 1: 1, then 2 after a child was made, 2 after an edit, 5 after a copy and a move. |
| A directory move rewrites the paths of what is beneath it. Those rows keep their entry and their version. | Read, `src/vfs/storage/backends/database/topology.py:313`, `:392`. Run 1: a child was at version 1 before and after. |
| `read` of a directory is `wrong_kind`. `tree` of a directory does not return the directory's own row. | Runs 1 and 2. |
| A read of a deleted file, of a file beneath a deleted directory, and of a file beneath a missing directory are each `not_found`. The second and third name the ancestor as the path and the file in `data["vfs.target"]`. | Runs 2 and 4. |
| `mkedge` and `grant` move no file's version. | Run 2. |
| `glob`, `grep` and `search` with `observations=` filter rows in hand, and `glob` hands them back as they were given. | Read, `src/vfs/base.py:1375-1394`, and the docstrings of the three. |
| The in-memory storage is the SQLite storage on a private database. | Read, `src/vfs/storage/backends/memory.py:40`. |
| A path key is at most 1,024 UTF-8 bytes and is bytewise on both engines. | Read, `src/vfs/paths.py:41`, `src/vfs/models/rows.py:170-194`. |

## The problem

- **Nothing remembers a read.** A caller that reads and writes back must carry the version itself. The shell carries none, so `sed -i` writes back unguarded.
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

A stamp has no path in the namespace and no verb. It is reached only through a session, as a grant is reached through `grant`. It composes two things Article 1 already has: an entry's identity and its revision.

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
| A row with no etag: a bare mount row, an edge row | Nothing. |

- A row of kind `file` leaves a file stamp from its etag. A row of kind `directory` leaves a directory stamp.
- The key of a stamp is the path as the row carries it: the router's resolved, absolute path. A path a caller writes is resolved the same way before a stamp is looked up, so `/a//f.txt` and `/a/f.txt` are one key.
- The result the caller gets is the kernel's result, unchanged.
- An absent stamp matters. A session holds a file stamp. Another caller deletes the file. The session's write is refused as changed. Its read answers `not_found`. Without the absent stamp the stale file stamp would refuse every later write, and no read could clear it.
- A directory stamp from a listing matters. `ls /build` then `rm -r /build` is the common order, and `ls` does not return the row of `/build` (run 2). Without the stamp the removal would be refused as unread, and the hint would say to read a thing that cannot be read.
- Rows in hand are the caller's. A caller could put any etag on one. Only what the store produced in the call is shown.

Reason: the verification rulings say bodies and listings both stamp, and the guide says that listing the directory a file is in is enough. A session that stamped bodies alone would force a read of a 5 MB file before it could be removed.

### 3. A listing stamps at most 1,024 rows

`LISTING_STAMP_ROWS = 1024`. A call other than `read` stamps the first 1,024 rows of its result, in the order the result holds them. The directory stamp of the directory listed is beside the cap. A `read` is never cut.

- A row past the cap is not stamped. A change to it is refused as unread, and `stat` of it clears that.
- 1,024 rows are one statement of 6,144 bind parameters, under a fifth of the tightest budget of 32,700.
- A `read` of many bodies in one call submits a stamp for each. What spec 0's writer cannot hold it drops, and a dropped stamp is a lost stamp (decision 8).

Reason: a listing has no page of its own, so a `glob` of ten million rows would hand ten million rows to a writer that every session shares. The cap keeps one call from filling it. The largest directory in the Linux tree holds 1,533 entries, and a median directory two, so the cap is past what a model can act on from one result.

### 4. The table is `vfs_session_stamps`, one row per session, path and turn

| Column | Type | Holds |
|---|---|---|
| `session` | the type of the key of `vfs_sessions` | the session's surrogate key |
| `path` | `BytewiseString(MAX_PATH_LENGTH)` | the path |
| `turn` | `Integer` | the number of the turn the row belongs to |
| `kind` | `String(1)`, not null | `f` file, `d` directory, `a` absent |
| `entry` | `String(255)`, null unless `kind` is `f` | the etag's entry key |
| `version` | `BigInteger`, null unless `kind` is `f` | the etag's version |

- The primary key is `(session, path, turn)`. There is no other index.
- On SQLite the table is made without a rowid. Measured over 100,000 rows with paths of 57 bytes on average: 114 bytes a row without a rowid, 185 with one (run 3).
- The etag is stored as its two parts, so the store can compare two stamps of one entry. A directory and an absence store no part.
- A row holds no time. Nothing in this spec orders by a clock.

Reason: the overview fixes the key, because a rewind must restore what an earlier turn saw. The entry key and the version are separate columns because decision 5 compares them inside one statement.

### 5. One stamp per path is current, and a new one replaces it unless it is the same file at the same or a lower version

The current stamp of a path is the row of the highest turn for that session and path.

A new stamp is merged by one rule, in memory and in the store:

- A file stamp is dropped when the current stamp is the same entry at a higher version.
- A stamp equal to the current one is dropped when the current row is in the submitting handle's turn or a later one.
- Otherwise it becomes the current stamp.

Where it is written:

- In the turn of the handle that submitted it, when the current row is in that turn or an earlier one. A current row in an earlier turn is left as it is, and a new row is written. So a path shown again in a later turn, unchanged, has a row in that turn too.
- In the row of the later turn, when a later turn already holds the path's current row. That row is updated in place.

Three things follow.

- **A read clears.** After any handle of the session is shown a row, the current stamp is that row or a higher version of the same entry. No turn order and no flush order can leave a lower version in front of it.
- **A rewind is exact.** The guide's two cases hold. A file read in `msg_4` and again in `msg_5` keeps its `msg_4` row, and is still read after a rewind. A file read in `msg_4` and changed in `msg_5` goes back to its `msg_4` row, which no longer matches the file, so a change is refused until it is read again.
- **A handle in an earlier turn is still heard.** A job resumed in the turn it started in, or a second device still in the turn before, writes into the later turn's row. A rewind to before that later turn removes it. The cost is a refusal.

Reason: an order between two stamps of one path must be a counter and never a clock (`framework-session-stores.md`, lessons 2 and 3). The version of one entry is a counter the store already keeps, so no new one is needed and a read does not have to fetch one. Two stamps of different entries have no order, so the later arrival wins, and the read that follows a refusal is the later arrival.

### 6. A stamp is stored by one statement shape, and a row whose session or turn is gone stores nothing

The statement, in SQLite's spelling, for any number of rows up to the parameter budget:

```sql
WITH v(session, path, turn, kind, entry, version) AS (VALUES (?, ?, ?, ?, ?, ?), ...)
INSERT INTO vfs_session_stamps (session, path, turn, kind, entry, version)
SELECT v.session, v.path,
       max(v.turn, coalesce((SELECT max(c.turn) FROM vfs_session_stamps c
                             WHERE c.session = v.session AND c.path = v.path), v.turn)),
       v.kind, v.entry, v.version
FROM v
WHERE <the session of v is live>
  AND NOT EXISTS (
        SELECT 1 FROM vfs_session_stamps c
        WHERE c.session = v.session AND c.path = v.path
          AND c.turn = (SELECT max(m.turn) FROM vfs_session_stamps m
                        WHERE m.session = v.session AND m.path = v.path)
          AND c.kind = v.kind
          AND CASE WHEN v.kind = 'f'
                   THEN c.entry = v.entry
                        AND (c.version > v.version
                             OR (c.version = v.version AND c.turn >= v.turn))
                   ELSE c.turn >= v.turn END)
ON CONFLICT (session, path, turn) DO UPDATE
  SET kind = excluded.kind, entry = excluded.entry, version = excluded.version
  WHERE NOT (vfs_session_stamps.kind = excluded.kind
             AND (excluded.kind <> 'f'
                  OR (vfs_session_stamps.entry = excluded.entry
                      AND vfs_session_stamps.version >= excluded.version)))
```

- On Postgres `max` of two values is `GREATEST`, and nothing else differs.
- The liveness test is `EXISTS` on the session's row in `vfs_sessions`. Spec 4 changes it to the turn's row in `vfs_session_turns`.
- Every subquery is a search of the primary key (run 3, `EXPLAIN QUERY PLAN`).
- The rows of one statement are deduplicated by session and path, the last submitted kept, and sorted by session and path. Postgres refuses a statement that touches one row twice, and two statements that lock rows in one order cannot deadlock.
- A row submitted with an address and no key is given its key first, by spec 2's statement.
- The same shape serves a flush and a change. Fifteen cases were run through it on SQLite (run 3): a new path, a lower version, an equal stamp in a later turn, a higher version, a handle in an earlier turn, another entry, a straggler of the first entry, an absent stamp, an absence again in a later turn, a file after an absence, a turn that is gone, a directory, a batch of two, a lower version from a later turn, and an equal stamp from an earlier turn. A rewind was then run over the rows.

Reason: one statement with no read before it keeps a flush at one round trip, and the merge is decided where two processes meet, in the store.

### 7. The current stamp is read in one keyed statement

```sql
SELECT s.path, s.kind, s.entry, s.version FROM vfs_session_stamps s
WHERE s.session = ? AND s.path IN (?, ...)
  AND s.turn = (SELECT max(m.turn) FROM vfs_session_stamps m
                WHERE m.session = s.session AND m.path = s.path)
```

- It returns at most one row a path.
- The paths are chunked by `membership_budget` and the results merged. 10,000 paths are one statement on both engines.
- The stamps beneath a directory are read by range, with `s.path >= :prefix || '/' AND s.path < :prefix || '0'` in place of the membership and `s.kind <> 'a'` added. The column is bytewise, so the range is the subtree. A batch that names many directories reads 500 ranges to a statement, under SQLite's expression depth of 1,000.
- A lookup reads the pending table first (decision 8) and asks the store only for the paths the pending table lacks.

Reason: a change needs the stamp of each path it names and nothing else, so its cost follows the call and never the session.

### 8. A read writes its stamps behind, and a change writes them with the change

**A read.** The guarded router calls the kernel's verb. It turns the rows into stamps, merges them into the pending table, hands them to spec 0's writer, and returns the result. It issues no statement and waits for nothing. This holds for every row of decision 2's table that is not a change, the absent and directory stamps included.

**What is kept in memory.** A handle keeps its address, `strict`, and a count of the bytes of stamps it has submitted since its last trim (decision 15). It keeps no stamp. The kernel keeps one pending table for all its handles: a mapping from a session's owner key and id to the stamps that session's handles have submitted in this process and that the writer has not yet reported stored or dropped. Its size is bounded by the writer's buffer. A second handle of the same session in the same process reads the same pending table, which is how the guide's `later.edit(...)` passes with no drain.

**What another process sees.** The store. Inside the window it lacks the stamp. A change through it is refused as unread, or as changed when an older stamp is there. It is never let through. One read through that process clears it.

**How wide the window is.** From the read's return to the writer's next flush: spec 0's delay, which this spec needs at one second or less. A process that stops or is frozen before the flush never closes it.

**How a host closes it.** By the drain. A host that answers each request from a process that then stops calls the drain before it answers. A host with long-lived processes needs no call.

**A stamp lost in a crash** is the same case with no end: the session forgets that one read. The failure is a refusal that one read clears.

**With `strict=False`** a stamp that is not yet flushed, or is lost, leaves the file unread to another process, and an unread file is let through there. That is what `strict=False` asks for (decision 15).

**A change.** The order of a change through the guarded router:

1. Resolve the paths the call names.
2. Look up their current stamps: the pending table, then the store (decision 7).
3. Refuse what strict refuses (decision 9). Nothing is dispatched.
4. Fill in the preconditions (decision 9).
5. Dispatch through the kernel. The policies and interrupts of specs 6 and 7 are inside this step.
6. Turn the refusals the filled preconditions caused into the two kinds of decision 12.
7. Store the stamps the change leaves (decision 13) by the statement of decision 6, on spec 0's synchronous path. Take those paths out of the pending table, and withdraw them from the writer's waiting rows.
8. Return the result.

- Step 7 is shielded from cancellation. A caller cancelled after its change committed still has the stamp stored, and then ends cancelled.
- Step 7 can fail. The change has happened, so the result stays a success. The stamps are put in the pending table and handed to the writer, and one `WARNING` is logged on `vfs.session`.
- Step 2 can fail. Then the call is refused `vfs.unavailable` and nothing is dispatched, strict or not. A session that cannot read what it saw does not guess.
- A change that is interrupted (spec 7) moves no stamp.

Why not one transaction: a stamp is in the kernel store, and the file may be in any mount. On SQLite the kernel store is a file of its own, by the study's finding. So a crash between step 5 and step 7 leaves the stamp behind the file. It can never be ahead of it, because a stamp is made from a row the store returned. The failure is again a refusal that one read clears.

Reason: reads are about three calls in four. One synchronous row a read was measured as a NO-GO on both engines: on SQLite it made every read a writer, and on Postgres it added 97 ms to a read under 32 sessions. A change must be synchronous because the next tool call may be served by another process, and a session that refused its own write there would repeat opencode's failure.

### 9. A session fills in the precondition and, when strict, refuses a change to what it was not shown

A precondition the caller states always wins. It reaches storage unchanged, strict does not apply to that path, and its refusal is storage's own.

Where the caller states none:

| Call | Current stamp is a file | No stamp, strict | No stamp, `strict=False` |
|---|---|---|---|
| `write` of one path | `if_match` from the stamp | sent with `if_absent=True`: a new file is made, an occupant is refused as unread | sent as written |
| `write(append=True)` | none (decision 10) | none | none |
| `write(entries=...)` | `if_matches` for the stamped paths | each unstamped path must be absent | unstamped paths sent as written |
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
- The rules hold for every authority, the system authority included. A stamp is not a right.
- A `write(entries=...)` under strict that holds stamped and unstamped paths is one call when spec 1's marker for "must be absent" exists. Without it, it is two calls: the stamped paths with `if_matches` first, then the unstamped ones with `if_absent=True`. If the first is refused the second is not sent. If the second is refused the first has landed, and the result holds the rows of the first and the errors of the second.
- `copy` reads its source and refuses an occupied destination, `mkdir` makes, and `restore` revives a row that reads as absent. None destroys what a session was not shown.

Reason: the precondition is checked inside the transaction that changes the row, so the session adds no check of its own to race with. Strict is the default because a changed file is only half the hazard: an agent that removes or overwrites a file it never looked at is guessing.

### 10. An append is never held to a stamp, and moves one only when it landed directly on it

A `write(append=True)` through a session carries no precondition from the session, stamped or not.

After it succeeds:

- Its status is `created`: the path takes a file stamp from the result. The session wrote the whole body.
- Its status is `updated`, and the current stamp is the same entry at exactly one version less: the stamp moves to the result. Nobody wrote between.
- Anything else: the stamp is left as it is.

"One version less" is exact, because every material write adds exactly one to the version (the record the write preconditions spec cites, and run 1: an append took a file from 3 to 4).

Reason for no precondition: an append destroys nothing, the guide says it needs no read, and the landed append exists so that concurrent appends all land. A precondition from a stamp would refuse the append whenever another caller had appended first, and under contention the caller would read, lose and read again without end. Reason for the narrow move: a stamp moved by every append would let a session read a log at version 5, miss a rival's version 6, append version 7, and then overwrite the file with a stamp of 7. The rival's lines would be destroyed unseen.

### 11. A directory takes no precondition, and being shown it is enough

A `delete` or `move` whose target has a directory stamp is sent with no precondition from the session. Under strict a directory with no stamp is refused as unread. A directory is shown by a listing of its parent, a `stat` of it, a `tree` above it, the result of the `mkdir` that made it, or a listing of the directory itself (decision 2).

- A file stamp on a path that is now a directory fails `if_match`, and is refused as changed.
- A directory that was replaced by another directory after it was shown is removed without a refusal. A delete can be undone from the trash, and a move destroys nothing.

Reason: a directory's version moves when a direct child is made, removed or renamed (run 1), by the session as much as by anybody. A version comparison would refuse `rm -r` of a directory the session had itself written into, which is the false refusal opencode's users reported.

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

When each is given:

- `unread` before dispatch, for an `edit`, `delete` or `move` that strict refuses.
- `unread` in place of storage's `exists`, at a path where the session filled in `if_absent=True`.
- `changed` in place of storage's refusal of an `if_match` the session filled in. That refusal is a `conflict`, or a `not_found` that names the path or an ancestor of it.
- Never for a precondition the caller stated. That refusal stays storage's own, with its `version`.
- A consumer that knows neither kind reads both as `conflict`, by `kind_family`. Both raise `WriteConflictError`.

What stops a loop:

- **A refusal moves no stamp.** The same call sent again is refused again, with the same words, as often as it is sent. Nothing but a row shown, or the session's own change, moves a stamp.
- **One read is enough.** The read's stamp is in the pending table before the read returns, so the next call in that process passes. A read that answers `not_found` leaves an absent stamp, so the next write makes the file.
- **A refusal is cheap.** An `unread` refusal of `edit`, `delete` or `move` reaches no mount. A `changed` refusal runs one snapshot read and no mutation statement, as a stale `if_version` does today.
- **The host puts the file beside the refusal.** A host's tool wrapper that sees either kind reads the path through the session and returns the current body with the refusal. The model's next attempt is then made from the file as it is, and the read has stamped it. The docs carry this as the pattern for a tool.
- VFS counts no refusals. A count would live in one process, and a loop of tool calls crosses processes.

Reason for no version and no etag: the one use of a current version in a model's hands is to send it back as `if_version` or `if_match`, which writes over a body it has not seen. Storage's own `conflict` carries the version because there the caller chose its precondition. opencode's 295 retries came from a refusal that did not show the model the new content, and a version number does not show it either.

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
| a change made by a resumed job | Its row above, written for the job's session (spec 7, need 3). |

- A directory delete or move reads the stamps beneath it by the range statement of decision 7, and the same paths of the pending table. The rows it writes are chunked to the parameter budget. The work is bounded by decision 15.
- Carrying is sound because a directory move leaves each row beneath it at its entry and its version (`topology.py:313`, `:392`).
- A batch move matches each row of the result to its pair by the resolved destination path.
- A change made with a precondition the caller stated refreshes in the same way.

Reason: every write path must refresh the stamp of the session that made the write. opencode's shell and plugin writes did not, and the same session's next edit then failed (`coding-agent-sessions.md`, lesson 3).

### 14. Stamps merge per path, and no merge can let a stale write through

Two calls on one session may run at once, in one process or in two. Each stamps its own paths. Two stamps of one path meet under the rule of decision 5.

The invariant: every stamp a session holds was made from a row the store returned to that session, from a row that session's own change returned, or was copied by a fork from such a stamp. A filled precondition holds only when the row at the path is the entry and version of the current stamp. So a change through a session lands only on a state that session was shown. The merge chooses among stamps that were all shown. Its choice can cause a refusal, and nothing else.

| Case | What happens |
|---|---|
| Two calls of one process are shown one file at versions 5 and 7, in either order | The current stamp is 7. A write lands if the file is still at 7. |
| The same in two processes, flushed in either order | The same. The statement drops the lower version. |
| A read is shown version 5, and a change of the same session makes version 6 before the read's stamp is flushed | The change stores 6 at once. The flush of 5 is dropped. |
| Two calls change one file at once | Both hold the same stamp. Storage lets one through. The other is refused as changed. |
| Process A reads and has not flushed. Process B is asked to change the file | B is refused as unread or as changed. A read through B clears it. |
| A read's stamp of one entry is flushed after the session moved that entry away and made a new file at the path | The stale stamp replaces the new one. The next change is refused as changed, and one read clears it. A change takes its paths out of the writer's waiting rows, so only a flush already in flight can do this. |
| Two whole turns at once on one session | Each handle stamps as above. A stamp of the earlier turn is written into the later turn's row when the later turn holds the path. VFS queues no turns, as the guide says. |

Being shown version 7 does not mean a model used it. A session vouches that the current file was put in front of its caller, and for nothing a model did with it.

Reason: a read record is a set of validators checked at write time, so it is safe to copy and safe to lose (`history.md`, lineage 4). A whole-set overwrite loses one side's stamps (`chat-protocols.md`, lesson 8), and a delta per call does not (`framework-session-stores.md`, lesson 10).

### 15. A session's stamps are bounded at 16 MiB, and the earliest turns go first

- `SESSION_STAMP_BYTES = 16 * 1024 * 1024`.
- Each row is charged the UTF-8 bytes of its path plus `STAMP_ROW_BYTES = 128`. A row cost 57 bytes beside its path on SQLite without a rowid and 128 with one (run 3). The higher figure is kept, because Postgres was not measured.
- The bound is in bytes. At the measured mean path of 57 bytes it is about 90,000 stamps.

**The trim** is a deferred task of spec 0's writer, for one session:

1. Measure: `SELECT turn, sum(octet_length(path) + 128) FROM vfs_session_stamps WHERE session = ? GROUP BY turn`. One statement over the session's own rows.
2. If the total is over the bound, remove whole turns, the lowest number first, while more than one turn is left and the total is over three quarters of the bound: `DELETE ... WHERE session = ? AND turn <= ?`. The cut is worked out from the measure, so this is one statement.
3. If one turn is left and it is still over three quarters of the bound, remove from it in path order, 5,000 rows to a statement, until it is not: `DELETE ... WHERE (session, path, turn) IN (SELECT ... WHERE session = ? AND turn = ? ORDER BY path LIMIT 5000)`. The statement never grows.

**When it runs.** A handle submits one trim with the first stamp it submits, and one more for each `STAMP_TRIM_BYTES = 1024 * 1024` of charges it submits after that. So a session passes its bound by at most 1 MiB for each handle writing at once. A trim goes down to three quarters of the bound, and not to the bound, so that the next mebibyte does not remove rows again.

- Removing low turns first never brings an older stamp back in front of a newer one.
- A path shown again in a later turn has a row in that turn (decision 5). So a turn-sized trim forgets the files the session has gone longest without being shown.
- Inside one turn no order of touching is stored, so step 3 goes in path order. Until spec 4 lands every row is in one turn, and step 3 is the only eviction.
- A line session's table holds the same bound in memory and forgets the stamp set longest ago.

**What forgetting can do.** Under strict, an evicted path is unread: a change to it is refused, and one read clears that. Under `strict=False` an evicted path is unread and is let through, because that is what `strict=False` asks for. Forgetting never lets a write through a strict session.

Reason: the bound is in bytes because a path is up to 1,024 bytes and a count of entries would bound nothing. It is enforced by a measure of the stored rows, because an estimate kept in a process dies with the process, and one process for each request is the normal case.

### 16. A bare line is a strict session of its own, and it is never stored

`fs.cli(line, authority=...)` runs the line through a guarded router whose stamps are a table in memory, made for the line and dropped when it ends. It is strict. It submits nothing to the writer and issues no statement on the kernel store. Nothing of it can be asked for again.

`Session.cli(line)` runs the line through the session's own guarded router. Its stamps are the stored session's, with that handle's `strict`. So `cat f` in one line and `sed -i ... f` in the next are one guarded read and write, across two requests.

- `fs.cli("sed -i s/a/b/ /f")` on a file the line never read lands. `sed` reads the file through the line, which stamps it, and writes it back with that stamp. The guard is on the time between the two.
- `fs.cli("rm /f")` is refused as unread. `fs.cli("cat /f > /dev/null; rm /f")` and `fs.cli("ls /; rm /f")` land.
- `fs.cli("rm *.log")` lands: the expansion lists the directory through the line.

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

- A stat request never stamps, because the machine asks the same question before a redirection, before a removal and for a test, and the request does not say which. So `stat f; rm f` in a line is refused as unread, where `session.stat` then `session.delete` in Python lands.
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

- A file replaced, moved or deleted between two chunks of `>` fails the writer with status 1. Its later chunks are not sent, and the other file is intact.
- `echo x >> log` from twenty lines at once leaves twenty lines.
- `echo a > f; echo b >> f` guards the second write with the first's etag. A rival's write between the two refuses it. That is more than `>>` asks, inside one line.
- Two writers of one line on one file share the path's etag and interleave, as bash's do.
- A writer opened with `>>` on a file the line did not make is not guarded between its chunks. A chunk can land after a rival's append. No byte is destroyed.

Reason: decision 10 leaves an append unguarded, so the guard of a continuing chunk has to be stated by the one party that knows the chunk continues a writer. The request names no writer, and the opening mode is the only sign the host has.

### 19. Both faces and both stores share one implementation

The rules live once, in the guarded router. `AsyncSession` holds one, a line holds one, and the synchronous `Session` wraps `AsyncSession` as it does today. The stored table and the line's table sit behind one small interface: look up, show, change. The parity test covers `strict=` and the two refusals on the synchronous face.

Reason: a rule written twice drifts, and the synchronous twin already wraps the asynchronous session for that reason.

### 20. Two landings, each green

1. **The rules and the line.** The two kinds and their words. The stamp, the merge rule, the table in memory, the guarded router. `fs.cli` in a line session. The host's two routers, the chunk writer, and the two host errors in the crates. It needs spec 1. A stored session is not yet guarded.
2. **Stored stamps.** `vfs_session_stamps`, its statements, the pending table, the write behind and the synchronous path, the trim, strict on a stored session, and `Session.cli`. It needs specs 0 and 2. The docs land here.

Reason: the first is of use alone, since it closes the shell's unguarded write-back. The second holds everything that touches the kernel store, so the bound lands with the rows it bounds.

## Cost

Costed against the reference deployment. Its figures: 150,000 verb calls a day, about three in four of them reads. About 10 actions a prompt and 4 prompts a session, so 40 calls a session and about 3,500 sessions a day. Sessions live 30 days.

**Per verb call.** A read adds no synchronous statement on any engine. In the process it adds one dictionary store for each row it stamps, at most 1,025 for a call that is not a `read`. Behind, it adds its rows to a flush.

**Rows written behind.** An *assumption*: a session is shown about 320 rows, 10 listings of 30 rows and 20 single rows. That is about 1,100,000 stamps a day, 13 a second on average and about 50 at the 4× peak. At 256 rows a statement it is under one statement a second. No public measurement of rows per listing exists.

**Per file write.** A change through a session adds two statements on the kernel store: the lookup and the store. The lookup is not issued when the stamp is still in the pending table. A handle's first change also runs spec 2's statement once. At the organic 50,000 writes a day, if every one went through a session, that is 100,000 statements a day, about one a second. The nightly batch runs with no session and pays nothing.

**Per batch.** A 10,000-entry `write` through a session adds three statements: one lookup of 10,000 keys, and two stores, at 5,450 rows to a statement and 6 bind parameters a row. A directory delete or move adds one range read and one store statement for each 5,450 stamps beneath it.

**Per index visit.** Nothing.

**Per corpus.** Nothing reads the whole table. Storage at the assumption above: 105,000 live sessions of 320 rows, at the 114 to 185 bytes a row measured on SQLite, are 4 to 6 GB. The bound is a ceiling on one session and not a forecast: every live session at its bound would be 1.6 TB.

**The trim.** One measure for each handle that stamps, about 14,000 a day at 4 prompts a session, each over one session's rows.

**Per lock.** A store statement takes row locks on one session's rows, for one statement. No table is locked. On SQLite the kernel store has one writer, held for one statement. A change of a session can wait behind one flush. A read waits on nothing, because it issues no statement. The kernel store is not the mount's file, so nothing here waits behind a batch.

**Memory.** The pending table, bounded by the writer's buffer. One integer a handle. A line's table, up to 16 MiB for the length of the line. The host's writer mapping, 1 MiB.

**Time.** Not measured. The study found two log transactions a write cost a write 151 ms on Postgres under 32 sessions, and suspected the pool without confirming it. A change's two statements here are the same shape.

## Left as it is

- **A directory that `write(parents=True)` made is not stamped.** The result names the file alone (run 4). Removing that directory needs a listing first. A row for each parent a write made would close it, and is the write verb's to add.
- **What is beneath a copied or a restored directory is not stamped.** The result names the directory alone, and a copy's entries are new.
- **A stat inside a line never stamps.** The request would have to say whether its answer is printed.
- **A writer opened with `>>` is not guarded between its chunks.** The request would have to name its writer.
- **A directory is not held to its entry.** The row has room for an entry key, and a comparison of the entry alone can be added without a change to the table.
- **No stamp travels with a request.** A host that keeps state itself could send its stamps as HTTP sends `If-Match`. Nothing here prevents it.
- **Stamps over MCP, without a session object**, is roadmap decision D51.
- **A count of refusals, and a body inside a refusal.** The host's wrapper does both.
- **Where spec 5 writes.** Its record of a change belongs at step 7 of decision 8, beside the stamps.

## Tests

Each is written and seen failing before the code. Counts are of statements recorded by a `before_cursor_execute` listener and attributed to the call, of calls seen by a recording storage, of rows, of refusals, or of an exit status. Never of time. "Both stores" means the line's table and a stored session, on memory, on a SQLite file and on the Postgres leg.

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
- `test_a_stated_precondition_reaches_storage_unchanged`: the recording storage sees the caller's `if_version` and `if_match`. Their refusal is `vfs.conflict` with `version`.
- `test_strict_refuses_what_was_not_shown`: one case a verb, as a named caller and as the system authority. `edit`, `delete` and `move` give `unread` and the recording storage sees 0 calls. A `write` of an absent path makes it. A `write` over an occupant gives `unread` and the body is intact.
- `test_without_strict_an_unread_change_goes_through_and_a_changed_file_does_not`.
- `test_each_read_verb_stamps`: one case each for `read`, `stat`, `ls`, `tree`, `glob`, the three modes of `grep`, `search` and `traverse`. A delete of a returned path then lands. A row with no version stamps nothing.
- `test_rows_in_hand_stamp_nothing`: `glob(observations=...)` with a forged etag, then a delete. Refused as unread.
- `test_a_listing_stamps_at_most_the_cap`: `ls` of 1,500 files leaves 1,025 stamps. A delete of the first row lands and of the last is refused as unread.
- `test_a_listed_directory_can_be_removed`: `ls /d`, then `delete /d`. Without the `ls`, `unread`.
- `test_a_read_that_finds_nothing_clears_a_stale_stamp`: stamp, a rival's delete, a write refused as changed, a read answered `not_found`, a write that makes the file. Counted: 1 refusal.
- `test_an_append_is_never_refused_and_does_not_launder`: read, a rival's append, the session's append lands and the file has every line. The session's overwrite is then `changed`. And read, append, overwrite with no rival: all land.
- `test_a_session_can_remove_what_it_filled`: `mkdir`, two writes inside, `delete` of the directory. 0 refusals.
- `test_a_removed_directory_takes_its_stamps_with_it`: stamp three files beneath, delete the directory, write one of the paths. Made, with 0 refusals.
- `test_a_moved_directory_carries_its_stamps`: stamp a file beneath, move the directory, edit the file at its new path with no read. Lands.
- `test_a_batch_write_fills_each_path`: three stamped and two new entries land. With one stamped file changed, no stamped row lands and the error names that path.
- `test_two_shows_of_one_file_keep_the_higher_version`: both orders of versions 5 and 7. The current stamp is 7 in each.
- `test_a_lookup_that_fails_refuses_the_change`: `vfs.unavailable`, and the recording storage sees 0 calls.
- `test_a_store_that_fails_keeps_the_change_and_the_stamp`: the result is a success, the stamp is in the pending table, 1 `WARNING`.
- `test_a_cancel_after_the_change_still_stores_the_stamp`: a second kernel on the same database reads the new stamp.
- `test_a_line_table_forgets_the_stamp_set_longest_ago`: the bound patched to 4 KiB. The first path stamped is `unread`, the last is not.

`tests/session/test_stamp_statements.py`, on a SQLite file and the Postgres leg:

- `test_a_read_through_a_session_adds_no_statement`: one case a read verb, and one for a read answered `not_found`. The statements attributed to the call on the mount equal those of the same call on the kernel, and on the kernel store they are 0. After the drain the writer has issued 1 store statement.
- `test_a_change_adds_a_lookup_and_a_store`: 2 statements on the kernel store, and 1 when the stamp is still pending.
- `test_ten_thousand_paths_are_looked_up_within_the_budget`: 1 statement at the engine's budget, 10 with `membership_budget` narrowed to 1,000, and none over it. Marked `slow`.
- `test_a_ten_thousand_entry_write_stores_in_two_statements`: 1 lookup and 2 stores. Marked `slow`.
- `test_the_store_statement_merges`: the fifteen cases of run 3, as a table of rows before, rows submitted and rows after.
- `test_the_rows_of_a_statement_are_unique_and_sorted`: a batch with one path twice binds it once, the last kept, in path order.
- `test_a_directory_delete_reads_its_stamps_by_range`: 3,000 stamps beneath: 1 range statement and 1 store statement.
- `test_a_batch_of_directories_reads_ranges_within_the_depth`: 1,200 directories in one `delete`: 3 range statements.
- `test_a_capped_listing_flushes_in_one_statement`: 1,025 rows, one statement, 6,150 bind parameters.
- `test_two_processes_meet_in_the_store`: two kernels on one database. A reads and does not drain, B's edit is `unread`. A drains, B's edit lands. Counted: 1 refusal.
- `test_a_row_of_a_deleted_session_stores_nothing`: 0 rows after the flush.
- `test_the_trim_removes_the_lowest_turns_first`: the bound patched to 4 KiB, rows in three turns. After the trim the total is at or under 3 KiB and every row left is of the highest turns. Counted: 1 measure and 1 delete.
- `test_the_trim_inside_one_turn_goes_in_path_order`: one turn over the bound. The rows left are the last in path order.
- `test_a_handle_trims_once_and_then_each_mebibyte`: the count of trims submitted.
- `test_forgetting_refuses_under_strict`: an evicted path is `unread`, and one read clears it.

`tests/shell/test_host.py`:

- `test_a_line_guards_a_read_and_a_write_back`: `cat /f` then `sed -i` with a rival's edit between them. `sed` fails, `/f` keeps the rival's body, standard error holds `File changed`, and the evidence holds one `vfs.conflict.changed`.
- `test_sed_in_place_on_a_file_the_line_never_read_lands`, and with a rival between its read and its write, is refused.
- `test_a_line_refuses_to_remove_what_it_was_not_shown`: `rm /f` exits 1 with `File not read yet` and `/f` is there. `cat /f > /dev/null; rm /f` and `ls /; rm /f` exit 0.
- `test_a_stat_in_a_line_never_stamps`: `stat /f; rm /f` exits 1, and the guarded router sees 0 `stat` calls.
- `test_a_replaced_file_fails_its_writer`: a three-chunk redirection with a replacement after the first chunk. Status 1, 2 writes dispatched, the replacement intact.
- `tests/shell/test_engines.py::test_lines_that_append_at_once_lose_no_line`, which exists, still passes: the lines at once each leave their line.
- `test_a_line_can_append_to_a_path_it_removed`: `echo a > /f; rm /f; echo b >> /f` leaves `b`.
- `test_the_writer_mapping_is_bounded`: `WRITING_BYTES` patched small. A later chunk of the writer that gave way is sent with no `if_match`, counted on the recording storage.
- `test_a_bare_line_stores_nothing`: 0 statements on the kernel store and an empty pending table.
- `test_two_lines_of_one_session_are_one_guard`: `Session.cli("cat /f")`, then `sed -i` through a second handle of the same session. It lands. With a rival's edit between, it is refused.

`tests/test_sync.py`:

- `test_the_sync_session_refuses_as_the_async_one_does`: the two refusals and `strict=False` on `Session`.
- `test_a_sync_session_verb_is_the_facade_call_with_the_authority_filled_in` (`tests/test_sync.py:620`) is rewritten. It compares what a recording storage saw through a session and directly, and through a session the storage now also sees the precondition filled in.

## Scope

Files, by landing.

1. `src/vfs/stamps.py`, new: the stamp, the merge rule, the line's table, the guarded router. `src/vfs/results/kinds.py`: two members and two rows. `src/vfs/base.py` and `src/vfs/sync.py`: `cli`. `src/vfs/shell/host.py` and `src/vfs/shell/programs.py`: the two routers, the writer mapping, the two host errors. `crates/vfs-shell/src/machine/mod.rs`, `crates/vfs-core/src/shell_binding.rs` and `crates/vfs-shell-wasm/src/wire.rs`: two members of `HostError` and their words. The tests of `tests/results`, `tests/shell` and the line's half of `tests/session`. Every test under `tests/shell` that removes, moves or overwrites, through `fs.cli`, a file its line was not shown is changed to show it first or to expect the refusal.
2. The table and its statements (the store, the lookup with its range form, the trim's measure and its two deletes), where spec 0 puts a kernel table. `src/vfs/stamps.py`: the stored table and the pending table. `src/vfs/session.py` and `src/vfs/sync_session.py`: each verb through the guarded router. `tests/session`, `tests/test_sync.py`. The docs. `tests/lint/allowlist.py`, where a listed module grew.

Out: everything under "Left as it is", and what specs 0, 1, 2, 4 and 7 own.

## What the docs must say

- A session remembers each file it is shown, by the file and its version, and stores that in the database.
- A change to a file that changed since is refused, and so is a change to a file the session was never shown. One read clears either. A session's own writes never cause one.
- Making a file and appending to one need no read.
- A listing counts for its first 1,024 rows and for the directory listed.
- A read costs the same with a session as without. A host whose process stops after each request calls the drain before it answers.
- A refusal is the same however often the call is sent. A tool wrapper that sees `vfs.conflict.changed` or `vfs.conflict.unread` reads the file and returns it with the refusal.
- A shell line with no session guards itself for the line and stores nothing. It refuses to remove, move or overwrite a file it was not shown. `stat` in a line is not a read.
- `strict=False` protects only what the session still remembers.

Pages: `documentation/how-to/keep-a-session-for-each-conversation.md`. The `ErrorKind` docstring, for the two kinds and that they carry no `data`. The docstrings of `cli` and of the session's `write`, `edit`, `delete` and `move`. `documentation/reference/shell.md`. `documentation/reference/glossary.json`, for stamp and strict.

## Earlier decisions this reverses

- **The spec merged from pull request 42, decisions 3 to 9.** A stamp was held in the session object and dropped by `close()`. It is now a stored row. The bound was 64 MiB in memory with the least recently touched evicted. It is 16 MiB of stored rows with the earliest turns evicted. The refusals were `conflict` with `data["reason"]`. They are two kinds with no `data`. An append to a stamped file carried `if_match`. It carries none. A directory carried `if_match`. It carries none. It said eviction never makes a call succeed. That holds under strict alone. Its test expected `fs.cli("sed -i ...")` on an unread file to be refused. It lands.
- **Ruling 6 of the verification**, that a multi-chunk writer is guarded by its stamp, each append refreshing it and the next requiring it. The outcome is kept. The etag is carried by the host and stated, because an append no longer takes a precondition from a stamp.
- **The docstring of `src/vfs/session.py`**, that a call through a session and the direct call return the same result and that a session is sugar. A session can now refuse what the kernel would do.
- **The `ErrorKind` docstring**, that a `conflict` may carry `version`. The two child kinds carry none.
- **Roadmap story K10**, already superseded by the merged spec.

## Choices for the owner

Each is decided above, and stands until it is ruled on.

1. **Listings stamp, up to 1,024 rows a call.** The other choices are bodies alone, which forces a read before a removal, and no cap, which lets one `glob` fill the writer.
2. **The bound is 16 MiB a session, and the earliest turns go first.**
3. **A refusal carries no current version and no etag.** The session study's lesson 4 said to carry the version. This spec holds that a version shows a model nothing and invites a write over an unseen body.
4. **An append is never guarded by a stamp.** The merged spec guarded it.
5. **A bare `fs.cli` line is strict.** `fs.cli("rm /f")` on a file the line was not shown is refused.
6. **A directory needs only to have been shown.** No precondition is sent for one, so a directory swapped for another after it was listed is removed without a refusal.
7. **The session rules hold for the system authority.**

## Where this spec disagrees with the overview or the guides

With the overview: nothing.

With `documentation/how-to/keep-a-session-for-each-conversation.md`:

1. **"Forgetting never lets a write through that would have been refused."** True of a strict session. With `strict=False` a forgotten stamp makes the file unread, and an unread file is let through. Proposed: begin the sentence "In a strict session," and add to the paragraph on `strict=False` that it protects only what the session still remembers. The same holds for a read lost when a process stops, in step 3. Evidence: decision 15, and the meaning the guide itself gives `strict=False`.
2. **"There is nothing to close and nothing to save."** True of the handle. A process that stops straight after a request loses the reads it has not flushed. Proposed: add "A host whose process stops after each request calls the drain before it answers." Evidence: decision 8 and `chat-protocols.md`, lesson 2.
3. **"Reading the file, or listing the directory it is in, is enough."** A listing counts for its first 1,024 rows. Proposed: add "A listing of more than 1,024 rows counts for the first 1,024." Evidence: decision 3.
4. **The hint of "Not read yet" says "Read it first".** A directory cannot be read (run 2: `wrong_kind`). Proposed hint: "This file has not been read in this conversation, so nothing was changed. Read it first, or list it if it is a directory, then make the change." This spec keeps the guide's words until that is ruled on.
5. **"the session forgets the files it has gone longest without touching."** True by turn. Inside one turn no order is stored, and rows go in path order. Proposed: "the session forgets what it was shown in its earliest turns first."

## Not checked

- **Postgres.** No server was running. The store statement, the lookup's plan, the range read and the bytes a row were run on SQLite 3.50.4 alone. `GREATEST`, `ON CONFLICT ... DO UPDATE ... WHERE` and a `VALUES` list as a source are read as Postgres has them.
- **Two flushes at once on Postgres.** Under READ COMMITTED the `NOT EXISTS` of one statement does not see a row another is inserting. The `WHERE` of the `DO UPDATE` is there for that case. It was not run.
- **Shell lines.** The installed extension is older than the Python beside it and refuses `host_programs`, so no line was run. Every claim about a line is read from the host and the machine.
- **The time a change's two statements add** under 32 sessions, on either engine.
- **The drafts of specs 0, 1, 2, 4 and 7.** None was read. Each need above is a need and not a fact, and the names this spec gives another spec's parts (`if_matches`, the drain, the marker for "must be absent") are placeholders for the names those specs give.
- **Rows shown per session.** The 320 is an assumption, and with it the 4 to 6 GB and the 13 rows a second.
- **The liveness test on the session row.** Run 3 ran the store statement against a turn table, the form spec 4 gives it.
- **The tests strict changes.** How many tests under `tests/shell` remove, move or overwrite, through `fs.cli`, a file their line was not shown was not counted.
- **The bytes a row on Postgres.** The charge of 128 is SQLite's.
- **The flush already in flight** when a change withdraws its paths (decision 14). The case is argued and was not run.
- **A fork and a rewind**, which spec 4 builds on the rows described here.

## One line

A session stores, per path and turn, the entry and version it was shown, writes that behind a read and with a change, and refuses a change to a file that moved on or that it never saw, in words that one read clears.
