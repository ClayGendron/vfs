# A call that reaches several mounts bounds each mount

This is the third draft. The first two were each reviewed by a fresh reader on 2026-11-18, and each was found not yet fit to build. The second review confirmed the design of the second draft and stopped it for one thing in this spec and for the spec of the first landing. Three things changed in this draft. "Where the code goes" is rewritten for landing 3: a search call is put under its mount's timeout where it is built, with its mount in hand, and not where the calls are gathered. Decision 2 now says that a batch's rows are not timed and that the `stat` of a mounted root inside a batch is. And every name and line count is corrected to commit `a64dd18c`, which holds the fixes the second draft named as coming. The spec of the first landing, `spec-a-cancelled-call-leaves-its-storage-intact.md` in this directory, was rewritten the same day. This draft is not built. The same reader read it a third time on 2026-11-18 and found it fit to build, on one condition that is now written here: where a call gains the keyword `timed`, it is a named keyword-only parameter of `MountListing.called`, `listed`, `_dispatch_entry` and `_dispatch_read`, so it is never passed on to a storage among the other keywords. The choices under "Choices to confirm" are not yet answered, and nothing is built until they are. It stands on `research.md`, which was corrected after each review.

## The outcome wanted

One storage that does not answer must not hold the answers of the others. A read that reaches several storages waits a set time for each, returns what the others gave, and names the one that was late. The late call is told to stop. A write is never cut by time. No fixed time is put on work that grows with the size of a mount.

## Builds on

This spec is built on the branch `a-mount-is-listed-as-a-directory-is` at commit `a64dd18c`, which holds `public-names-follow-the-naming-rules` and `glossary-rules`. It has not landed on `dev`. Every name and line below was read at that commit. Five things there are part of what this spec stands on.

- `MountListing` in `src/vfs/mounts.py` is a snapshot of the mount table, built again whenever the table changes, by `update_mount` as well. One call reads one snapshot. A mount's `timeout` is read from the snapshot, so a change by `update_mount` applies to the next call and never to a call in flight.
- The snapshot is handed the kernel's raw storage call, `_call_storage`, and makes every storage call of a read through its own method `called`. Its other methods are `listed`, `tree`, `matched` and `shown`, and the private `_heads` and `_directory`.
- `ls`, `stat` and `tree` take a hop from the call's budget in `_dispatch_read`.
- `_attach_mount` takes `judged: MountJudgement | None`. It takes `timeout` beside it.
- `_Dispatches`, which a `glob` or a `grep` over several mounts builds, has a `settle` step that runs after the calls are gathered.

Three other specs share files with this one.

- `spec-a-cancelled-call-leaves-its-storage-intact.md`, in this directory. It lands first. Decision 6 cancels calls, and a cancelled call destroys an in-memory storage until that spec is built.
- `agents/2026-11-18-add-mount-takes-a-posture/spec.md`. It adds `posture` to `add_mount`. The keyword order is `permissions`, `posture`, `timeout`, `deny_ops`. Whichever of the two is built second places its keyword and rewrites the shared docstring from the file as it then stands.
- `agents/2026-11-17-search-applies-its-file-filters-to-rows-in-hand/spec.md`. It moves three helpers out of `base.py`, and it is built at `e97ca9a9`, a later commit than the one this spec was read at. Landing 3 of this spec changes the same routes and is built on top of it.

Two files are held at an exact line count by `MODULE_LINE_BASELINE` in `tests/lint/allowlist.py`, and neither may grow: `src/vfs/base.py` at 3079 and `src/vfs/sync.py` at 1078. "Where the code goes" says how each is paid for. Each landing ends with the entry set to the file's new exact count, since the lint refuses a file below its entry as it refuses one above.

## Terms

- **Timeout.** The number of seconds the kernel waits for one timed call. It is the one noun for this in code and in the docs. The first draft called it a bound.
- **Timed call.** A storage call the kernel waits for only up to the mount's timeout. Decision 2 says which calls are timed.
- **Addressed storage.** The storage that holds the path that `ls`, `stat` or `tree` names, the storage of each row in a batch, or the only storage a call reaches. The call has no answer without it.
- **Late call.** A timed call that was still running when its timeout passed.
- **Mark.** What the kernel keeps for a mount whose timed call ran late, until a later timed call answers in time.
- **Probe.** The one timed call that is still sent to a marked mount in each timeout.
- **Stage budget.** The 10 seconds each row-matching stage already has, `WALL_TIME_BUDGET`. It cuts work and returns the rows found so far.

## What the precedent is

Read on 2026-11-18. The clones, commits, licences and pages are in `research.md`, "Sources". The linux, 9front and plan9 clones were dirty and were read as they stood.

| Question | Kernels with mounts | Systems that fan out and merge |
|---|---|---|
| Is there a timeout by default? | No. NFS is `hard` by default on Linux and FreeBSD. FUSE, autofs and 9P have none. | Mostly no. Elasticsearch, gRPC and Thanos set none. Trino's is 100 days. A Vitess tablet's 30 s is the exception, and it kills the query. |
| Where is it set? | On the mount: NFS `soft`, `timeo`, `retrans`. On the connection for FUSE. | On the member: a shard, a store, a remote cluster. gRPC sets it on the call. |
| What does the caller see for a slow member? | An error for that file system. Plan 9 keeps the covered entry when the mounted root's `stat` fails. | Elasticsearch, Thanos and Vitess return the other members' rows and name the missing one. Trino, Citus and `postgres_fdw` fail the whole call. |
| Is the member told to stop? | 9P sends `Tflush`. FUSE aborts the connection. NFS `soft` only stops retrying. | Yes. gRPC cancels on both sides at the deadline. `postgres_fdw` sends a cancel and gives the cancel 30 s. Vitess kills the query. |
| Is that proof it stopped? | No. A reply may arrive after `Tflush`. | No. gRPC: the two sides' "conclusions may not match". Elasticsearch: a cancelled task "may continue to run". |
| What is a fixed time put on? | NFSv4 `soft` cuts a request that was sent only when the connection breaks, not by time. | Elasticsearch's shard timeout returns the hits found so far. gRPC judges a connection by a keepalive ping, not by a real call. |
| What happens to writes? | nfs(5): a soft timeout "can cause silent data corruption". | No system gives a write a partial answer by timeout. |
| Is a member known to be down asked again? | autofs answers at once after a write to its daemon fails. | gRPC answers `Unavailable` at once while the connection is down, and tries the connection again after a delay. |

Five things follow for VFS.

- **Reads return a partial answer that names what is missing. Writes do not.**
- **What is late is told to stop, and that is never proof that it did.**
- **A timeout is a setting on what is waited for: a mount, a store, a shard.** "Member" in this section is the other systems' word for it, and not the VFS glossary's.
- **A fixed time fits a small exchange and does not fit work that grows.** NFSv4 and gRPC judge the far side by its connection or a ping. Where a time is put on real work, the work returns what it has.
- **Waiting without limit is the common default.** A timeout that is on by default is VFS's own choice.

## The problem

One stuck storage holds every call that reaches it, and every call that reaches a directory above it.

Executed on 2026-11-18, on the in-memory storage. A kernel has a root, a mount at `/data` and a mount at `/slow`, with one file in each. The storage at `/slow` was made to wait for ever in its reads. Each call was given 1.0 s.

| Call | `/slow` healthy | `/slow` stuck |
|---|---|---|
| `ls("/")` | `/data`, `/root.md`, `/slow` | No answer |
| `tree("/")` | Five rows | No answer |
| `glob("/*")` | `/data`, `/root.md`, `/slow` | No answer |
| `glob("**/*.md")` | Three files | No answer |
| `grep("needle")` | Three files | No answer |
| `ls("/data")` | `/data/report.md` | `/data/report.md`, at once |

The cause is `gather_settled`, which waits for every storage with no limit.

More facts, executed or read.

- **The rules that report a failing mount already fit a late one.** Executed. A spike made the kernel wait 0.3 s for each storage other than the root's and then return a failed result with one `timeout` error. `ls("/")` returned `/data`, `/root.md` and `/slow`, with one `warning` of kind `timeout` at `/slow`. `tree`, `glob` and `grep` did the same. No line of `mounts.py` was changed.
- **A call left running holds more than a connection.** Read. A read runs at `REPEATABLE READ` on Postgres and MariaDB, so it holds a snapshot, which holds back vacuum on Postgres. `src/vfs` sets no statement timeout on any engine. On a dead peer nothing ends the call.
- **Calls left running use up the pool.** Executed. A file database has 5 connections and 10 more on overflow. With 15 calls left running, the next call waited until one of them ended.
- **A cancelled call costs a file database one connection and no data.** Executed, at every statement of a write.
- **A cancelled call destroys an in-memory storage.** Executed. This is the defect that lands first.
- **`tree` has no stage budget.** Read, `tree_rows` in `storage/backends/database/reads.py`. Its time grows with the subtree. `glob`, `grep` and `search` each have one.
- **A cancel that nobody awaits holds nobody.** Executed by the review. The caller of a cancelled call waits for the statement only when it awaits the cancellation.

## Decisions

### 1. Only a read is timed. A write is never cut by time

A timeout applies to read verbs only. Every other verb waits for its storage as it does today: the mutations, the grant verbs and `run`. A write batch that reaches several mounts returns only when every mount has answered.

Reason: no system studied gives a write a partial answer by timeout, and nfs(5) names data corruption as the price of trying. A write cancelled at its commit was executed and had landed. `gather_settled` exists so that no batch goes on changing things behind a caller who has seen a failure.

### 2. A call is timed when another answer waits on it and its own work is small or has a budget

| Call | Storage call | Timed |
|---|---|---|
| `ls`, `tree` and `glob` at a directory that holds mount points | The `stat` of each mounted root | Yes |
| `glob`, `grep` or `search` that reaches two or more storages | Every call, the root probes included | Yes |
| `glob`, `grep` or `search` that reaches one storage | That call | No |
| `tree` over a region | The `tree` of each mount beneath the path | No. Decision 3 gates it. |
| `ls`, `stat` or `tree` of one path | The storage that holds the path | No |
| Any read verb given `observations` | The call that carries the batch's rows | No |
| `ls` given `observations` that name a directory which holds mount points | The `stat` of each mounted root in it | Yes, as in the first row |
| `locate` with `exists`, and the rights check of a mount change | One call | No |
| Any verb that is not a read | Every call | Never |

Two tests decide a row.

- **Does another answer wait on it?** The addressed storage has no bystander. When it does not answer, the call has nothing to return.
- **Does its honest time stay small?** The `stat` of a root is one row. `glob`, `grep` and `search` carry a stage budget inside the storage and return what they found when it runs out. A `tree` and a batch have no budget, and their time grows with what was asked for.

The first draft timed a batch of `observations` across mounts. The rows of a batch are no longer timed. Each storage in a batch is addressed by rows the caller named, and a batch of 10,000 rows is a supported call. The `stat` of a mounted root that `ls` of a listed directory adds is timed, in a batch as in a single call: a batch reaches it through `MountListing.listed` and `_directory`, `mounts.py:387-436` and `613-642`, and it is the same one-row call.

A root probe is the `stat` of the roots a caller named for a `glob` or a `grep`, one call for each mount that holds some. It is a small batch, as large as the list of roots the caller wrote, and it is timed with the search it belongs to.

Reason: the harm in the problem is to the bystander. A fixed time on work that grows is a ceiling on size, which the working agreement forbids. NFSv4 does not cut a sent request by time for the same reason.

### 3. The `tree` of a mount beneath a region is asked only after that mount's root has answered

Today a `tree` over a region asks each mount beneath it for its `stat` and its `tree` at the same time: `MountListing.tree` gathers the target's `tree`, `_heads` and each deeper `tree` in one step, `mounts.py:437-502`. Under this design the two are asked in turn, for each mount on its own.

- The `stat` of the mounted root is a timed call.
- When it answers in time, the mount's `tree` is sent and is waited for without a timeout, as the `tree` of the addressed mount is. A refusal or a failure of the `stat` that is not a late call changes nothing: the `tree` is sent as today.
- When the `stat` is late, or the mount is marked, the mount's `tree` is not sent. The mount point shows as a bare row with the record of decision 5.
- A mount that cannot answer `stat` is asked for its `tree` as today.
- The mounts are still asked at the same time as each other and as the addressed storage.

The number of storage calls does not change. The longest path of a `tree` over a region grows by one `stat`.

One case is left. A storage that answers its `stat` and then never answers its `tree` holds the call, as an addressed storage does.

Reason: the first draft cut the `tree` of a mount at 30 s. The review showed that is a ceiling on the size of a mount that a whole-tree listing can include, and that the cut work ran on and was dropped. The `stat` of the root is VFS's keepalive ping: a small call that says whether the storage is answering. A storage that answers is given the time its work needs.

### 4. The timeout is a number of seconds on the mount, with a default on the kernel

- A mount has `timeout`: a positive number of seconds, or `None` for no timeout. `None` already means unbounded for `max_depth` and for `Deadline`.
- `add_mount` takes `timeout`, after `posture` and before `deny_ops`. Left out, the mount takes the kernel's default, and the number is stored on the mount when it is attached.
- `update_mount` takes `timeout`. Left out, the mount's timeout is left alone. `None` removes it. To return a mount to the kernel's default, that number is passed.
- The kernel's constructor takes `mount_timeout`, a positive number or `None`. Its default is 30. The root mount takes it, and `update_mount("/", timeout=...)` changes it.
- A number that is zero or less raises `ValueError`.
- `Mount.to_payload()` carries `timeout`, as a number or `None`.
- No verb takes a timeout as an argument.

The default is `3 * WALL_TIME_BUDGET`, a named constant in `vfs/mounts.py`. A storage's `grep` or `search` can run two stages under a budget in one call, so three budgets leave room for both and for the statements around them.

This is not a cap on scale. It is put only on calls whose honest time does not grow with the corpus, it can be removed for each mount, and a late call is always named.

Reason: NFS, FreeBSD, FUSE, Thanos and Elasticsearch set the timeout on the mount, the store or the remote cluster, because the latency is the member's own. The first draft used `0` for no timeout. The review pointed to the code's own convention, and it is followed.

### 5. A late call is reported as a `timeout` failure of its mount

When a timed call's timeout passes, the kernel stops waiting and takes this result in place of the storage's answer: no rows, and one error.

| Field | Value |
|---|---|
| `kind` | `timeout`, which is `vfs.timeout`. No new kind is added. |
| `path` and `source` | The mount's path. |
| `detail` | The verb, the timeout in seconds, that the call was cancelled, and that a call which names this mount alone is waited for without limit. It names no path. |
| `severity` | `error` as made. The merge rules below then apply. |

Every rule that reports a failing mount today then reports a late one with no change.

| Where the late mount is | Rows | Record |
|---|---|---|
| A mount point in `ls`, `tree` or `glob` | The mount point shows as a bare row. | One `warning` |
| A mount beneath a `tree` | The mount point shows bare, and nothing beneath it. | One `warning` |
| A mount asked whole by `glob`, `grep` or `search` | The other mounts' rows. | One `warning`. The call fails only when every mount fails. |
| A mount the caller named in `glob`, `grep` or `search` | The other mounts' rows. | One `error`. The call fails, as it does today for a named mount that fails. |

The record does not send a caller to the untimed call as a remedy. Its retry class is `transient`: the advice is to retry. The `detail` states the fact that the mount asked alone is waited for, so that a caller who does ask knows what it is choosing.

Reason: Elasticsearch, Thanos and Vitess answer a slow member with the other rows and a record that names it. VFS has the kind already. The review showed that the first draft's advice, "call that mount alone", led into the one call that has no timeout.

### 6. A late call is cancelled at its timeout, and nobody waits for the cancellation

- At the timeout the kernel cancels the late call's task and returns the record of decision 5 at once. It does not await the cancelled task.
- The kernel keeps a reference to the task until it ends. The event loop keeps only weak ones.
- A callback on the task runs when it ends. It drops the reference. If the task ended with an exception other than the cancellation, the callback passes it to `loop.call_exception_handler`. No caller is left to raise it to.
- A caller's own cancellation is as it is today. It cancels that caller's storage calls still in flight.
- The cancel is sent to a call on any storage the kernel calls, owned or borrowed.

What the cancel does on each driver. Only the two SQLite rows were executed.

| Storage | What a cancelled read leaves |
|---|---|
| In-memory SQLite | After landing 1, the cancel stops nothing in flight: a read's unit of work runs its statements to their end, and the database is intact. A call cancelled before its turn sends nothing. Today the database is lost. |
| SQLite in a file | The statement runs to its end on its thread. One connection is replaced. No data is lost. |
| Postgres, asyncpg | A cancel request goes to the server. The connection is replaced. The snapshot and the pool slot are freed. |
| MariaDB, aiomysql | The socket is closed and the pool slot freed. The server is not told, and may run the statement on. |
| SQL Server, aioodbc | The statement runs on in its thread. Whether the close waits behind it was not checked. |
| Oracle, oracledb | A break is sent. The driver waits for the server's reset with no limit of its own. |

The kernel promises that it asks. It does not promise that the driver stops. On a dead peer, two of the drivers above may hold the cancelled task. Decision 7 does not depend on the task ending.

The first draft left the late call running. The review proposed cancelling it after a second timeout had passed. This draft cancels at the first.

Reason: every system studied that times a member also signals it at the deadline, and none waits a second period. A call left running holds a connection and a snapshot with no end on a dead peer. At the reference peak, hundreds of calls can be queued behind a slow storage's pool, and each would still run after its caller had gone: a cancel while a call waits for a connection costs nothing and removes it. The first draft's two reasons against cancelling do not survive the review. The caller is held only when it awaits the cancellation, and the lost database is a defect of one storage, fixed first.

### 7. A mount whose timed call ran late is marked, and one probe in each timeout clears it

- A mount is marked when a timed call to it runs late.
- While it is marked, a timed call for it is not sent. The kernel answers at once with one error of kind `backend_unavailable`, at the mount's path. Its `detail` says an earlier call to the mount ran out its timeout. Its `data` carries `retry_after_ms`, the time until the next probe.
- One timed call is still sent in each timeout: the first to arrive once a timeout has passed since the mark was set or the last probe was sent. It is the probe. It is an ordinary call, and its answer is used.
- The mark clears when a probe answers in time. It also clears when `update_mount` is given a `timeout`, and it goes with the mount at `remove_mount`. It does not wait for any late call to end.
- An untimed call is not affected by the mark and does not clear it.
- The mark is kept for each mount, in memory, by the kernel. No storage call and no lock is added.
- Calls already waiting when the mark is set each run out their own timeout.
- One limit is known. A storage that serves one call at a time, as the in-memory storage does, or one whose pool is used up, makes a root `stat` wait behind a long call. That `stat` can run late and mark a mount that is busy and not down. The mark then clears with the first probe after the long call ends.

The merge rules of decision 5 apply to the `backend_unavailable` record as they do to any failing mount: a bare row and a `warning` in a listing.

The first draft stopped asking a storage until its last late call ended, and reported the skip as `timeout`. The review found four faults, and each is answered.

| Fault | Answer |
|---|---|
| One long `tree` marks the mount. | A `tree` is no longer a timed call. Only a root `stat` or a call with a stage budget can mark. |
| The rule cleared only when the late call ended, which may be never. | The mark clears on a probe, and never reads the late call. |
| A storage that recovers is sent a full window of calls. | One probe in each timeout is sent until one answers. |
| The skip did no work and timed nothing out. | Its kind is `backend_unavailable`, which is what gRPC answers when it does not send. |

Reason: without the mark, every listing of a directory above a dead mount waits a whole timeout, for as long as the mount is down. The precedent is gRPC's, read correctly this time: a connection is judged down by a small exchange, calls are then answered `Unavailable` at once, and the connection is tried again after a delay. VFS's timed calls are small exchanges or carry a budget, so one that runs late is a fair sign. The first draft cited gRPC's fail-fast for a rule keyed on slow calls. gRPC's follows the connection, and the memo is corrected.

### 8. The stage budgets keep their own clocks

- The kernel's own stages run before the timed calls are sent or after they return: planning, admissions, the judging of mount points, and the ranking of a `search`. No mount's timeout covers them.
- A storage's stages run inside its timed call. Their budgets are not shortened by the timeout. The default is three stage budgets so that a storage returns its own truncated answer before the kernel stops waiting.
- A storage can be built with longer budgets, through `grep_wall_seconds` and the like. Its mount then needs a `timeout` of at least three of its own budgets. The docs say so.
- The two records stay distinct. `truncated` means work was cut and the rows found are returned: refine the call. `timeout` means a storage did not answer and none of its rows are returned: retry.

Reason: a stage budget cuts work the process is doing and returns part of it. A mount's timeout is on waiting for someone else, and there is no part to return.

### 9. `close()` gives late calls half of `close_timeout`, then closes the storage

For a storage the kernel owns, `close()` cancels any timed call still running on it, waits for the cancelled calls for at most half of `close_timeout`, and then closes the storage within what is left, whether or not they ended. A storage the kernel does not own is not closed, and its cancelled calls are left to end.

Reason: a storage is closed after the calls on it have stopped where that is possible, as the engine already stops its analysis pass before it disposes. A cancelled call can be stuck in a driver's thread, and the review showed that waiting for it without a limit of its own could use up the whole of `close_timeout` before the storage was closed.

### 10. How a timeout crosses a hop is decided, and is built with the first storage that wraps a kernel

No storage in `src/vfs` wraps a kernel, so nothing is built for this now. The rule is kept so that such a storage is built to it.

- When a timed call starts, its timeout becomes one instant, a `Deadline`, set in a context variable in that call's own task, beside the hop budget.
- A kernel entered inside that call waits for each of its own timed calls until the earlier of the inherited instant and its own mount's timeout. The instant never lengthens a wait.
- A timed call whose inherited instant has already passed is not sent.
- A storage that reaches a kernel over a wire sends the seconds that are left.

Two gaps are known. The inner kernel's stages keep a fresh budget and do not read the instant, so an inner partial answer is lost when the outer timeout fires first. And `Deadline` reads its own clock while an asyncio timer reads the loop's, so a test that patches one does not move the other.

Reason: gRPC carries one deadline across hops as the time that is left. The review called building it now speculative, and it is. The working agreement lists speculative generality as a smell.

### 11. Nothing is added to the storage protocol, and `gather_settled` is unchanged

No timeout is passed to a storage, and no statement timeout is set on any engine. `gather_settled` still waits for every call it is given. A timed call returns at its timeout, so the gather settles on time. Its docstring says that a cancelled read may still be unwinding when the results are returned, and that it changes nothing.

Reason: every storage is timed with no change to it. A statement timeout is a different setting on each engine and is a change of its own.

## Where the code goes

Every line number in this section is at `a64dd18c`.

**The one place a call is timed.** `MountListing.called`, `mounts.py:371-385`, is where the snapshot makes a storage call. It takes one new keyword, `timed`, false by default. When it is true, `called` starts the storage call as a task, waits the mount's timeout, and for a late call cancels it and returns the record of decision 5. The mount is the one `called` is already given, so the timeout is never applied without its mount. `AskStorage` and `_call_storage` are unchanged. `_call_storage` also serves `_probe_mount_site` and `_probe_location`, `base.py:747` and `2582`, and cannot tell a timed call from any other.

**What outlives a snapshot.** One small class in `mounts.py` keeps the cancelled tasks, and from landing 4 the marks. The kernel makes one for its lifetime and hands it to each snapshot, because a snapshot is replaced when the table changes and the marks must not be.

**Landing 2, the listing.** All of it is inside `mounts.py`.

- `_heads`, `mounts.py:577-611`, passes `timed=True` on each `stat` it makes. Every listing that shows a mount point reaches `_heads`: `tree`, `matched`, and `_directory` for `ls`, in a batch as in a single call.
- `tree`, `mounts.py:437-502`, no longer gathers the deeper `tree` calls beside `_heads`. For each mount it reaches, it awaits that mount's head and then its `tree`, as decision 3 says, and the mounts still run beside each other.
- `base.py` changes only for the options and for `close()`.

**Landing 3, the searches.** The second draft timed the calls where `_route_fanout` gathers them, `base.py:1913`. The second review showed three faults in that. The gathered list holds `points`, which is `MountListing.matched`: a kernel stage followed by `_heads`. Timing it there would put a kernel stage under a mount's timeout, against decision 8, and would time each head twice. And a root probe in that list does not carry its mount. So nothing is timed at the gather. Each call is timed where it is built, with its mount in hand.

| Call | Built at | Change |
|---|---|---|
| A mount of a `search`, named or asked whole | The two lists in `_route_fanout`, `base.py:1901-1909` | `timed` is passed to `_dispatch_entry`, which passes it to `called` |
| A mount of a `glob` | The `branches` of `_glob_dispatches`, `base.py:2034-2052`, which call `listing.called` | `timed` is passed |
| A mount of a `grep` | The `branches` of `_grep_dispatches`, `base.py:2116-2130`, which call `_dispatch_entry` | `timed` is passed |
| A root probe | The `stat` in `_root_probe`, `base.py:2237-2239`, through `_dispatch_read` and `listed` | `timed` is passed down to the `called` that carries the probe's rows. The judging that follows it in `_root_probe` is a kernel stage and stays outside. |
| `points` | `listing.matched`, `base.py:2033` | None. Its `_heads` times each `stat` already. |

- `timed` is true when the plan holds two or more storages. `_route_fanout` already works that out for a ranked search, `base.py:1887`, and each builder has the plan.
- The gather, `settle` and `_Dispatches` are unchanged. The review's fix carried a mount beside each probe in `_Dispatches`. Timing inside the probe needs no such field.
- `_dispatch_entry` and `_dispatch_read`, `base.py:2786` and `2797`, each gain the keyword and pass it on. `listed` passes it to the calls it makes.

**`base.py` ends no longer than it began, in each landing.**

- Landing 2 gains `mount_timeout` on the constructor, `timeout` on `add_mount` and `update_mount` with their docstring lines, and the hand-over in `close()`. It is paid by moving the part of `close()` that closes the storages, 21 lines at `base.py:540-560`, into `mounts.py` as one function, which decision 9 rewrites in any case. If the file is still over, the checks of the two new arguments move to `mounts.py` beside `validate_deny_ops`.
- Landing 3 gains the keyword at five places and on two signatures, one of which is at 119 characters today and will wrap. That is about a dozen lines. It is paid by moving the static method `_merge_fanout`, 18 lines at `base.py:2252-2269`, to `mounts.py` beside `gather_settled`, with the same arguments and the same body.
- The file is counted before any other code is written, in each landing. While this draft was written the checkout moved on to `e97ca9a9`, where the search-filters spec is built and `base.py` is 3073 lines. The line numbers above are not those of that commit, and the rule stands whatever the count is.
- **`sync.py` gains six lines**: the argument and its hand-over in the constructor, in `add_mount` and in `update_mount`. They are paid by writing the signature of `grant` in that file on one line, which fits in the line length at 115 characters and frees seven. The posture spec takes `sweep` for its own two lines.

## Landings

Each is green on its own, and each is one pull request.

1. **A cancelled call leaves its storage intact.** The spec of its own. It is first because landing 2 cancels calls, and today a cancelled call destroys the default storage. It is also a defect for any host that cancels a call, with or without this design.
2. **The timeout in listings.** `timeout` on the mount and `mount_timeout` on the kernel, the timed root `stat`, the gate on `tree`, the `timeout` record, the cancel and the kept tasks, `close()`, and the docs for these. After it, `ls`, `tree` and the mount points of a `glob` no longer wait on a late mount. A search across mounts still does.
3. **The timeout in searches.** The timed calls of `glob`, `grep` and `search` across storages. It is built on top of the search-filters spec, which changes the same routes and is built at `e97ca9a9`.
4. **The mark and the probe.** Decision 7. Until it lands, every timed call to a dead mount waits a whole timeout.
5. **Crossing a hop.** Decision 10, when a storage that wraps a kernel exists.

The posture spec and landing 2 both change `add_mount`. Either may go first.

## Cost

A healthy call makes the storage calls it makes today. Each timed call adds one task and one timer, in memory. No statement is added and no lock is taken.

| Call | Storage calls today | Under this design |
|---|---|---|
| `ls` of a directory with `k` mount points | 1 + `k` | 1 + `k` |
| `tree` over `m` mounts | 1 + 2`m` | 1 + 2`m`, with each mount's `tree` after its `stat` |
| `ls`, one mount late, before it is marked | No answer | 1 + `k`, answered at the timeout |
| `ls`, that mount marked | No answer | `k`, answered at once; 1 + `k` for the one probe in each timeout |

At the reference deployment a verb call is one of about 150,000 a day, and about 20 a second at peak. The healthy path adds nothing that is multiplied by the corpus.

When a mount goes late, each timed call that reaches it in the first 30 seconds waits out its own timeout and is then cancelled. At peak that is at most about 600 calls, if every call reached that mount. Each holds a task until it is cancelled. The connections they hold are capped by the storage's own pool, 15 by default, and the rest are cancelled while they wait for one. Once the mount is marked, a timed call costs it nothing but the probe.

Each cancel on a server engine costs one connection, which the pool replaces. At most the pool's size is replaced when a mount goes late, and one for each probe after that.

## Left as it is

- **A write to a stuck storage.** It waits without limit. A limit for writes belongs inside the storage, as a statement timeout the engine enforces, where the engine rolls the transaction back whole.
- **A read of one mount, and a batch.** They wait without limit, by decision 2. A host that puts its own limit around such a call cancels it, and landing 1 makes that safe.
- **A storage that answers its `stat` and not its `tree`.** It holds a `tree` over a region, by decision 3.
- **A timeout for the whole call.** None is added. A call's longest time is the sum of its stages and its longest timed call.
- **A stage budget for `tree`.** None is added.

## Tests

In `tests/base/test_mount_timeout.py`, written and seen failing before the code.

Four rules hold for every test, so that none depends on the speed of the machine.

- A storage double waits on a gate until the test opens it, and answers without any I/O once it does.
- Only the stuck mount is given a short timeout, of a few milliseconds. Healthy mounts keep the default.
- A test that proves a call is still waiting sleeps four timeouts and asserts that the task is not done.
- No test asserts on elapsed time. Every other assertion is on rows, records and counts of calls recorded by the double.

Landing 2.

- With one mount stuck, `ls("/")` returns the parent's rows, a bare row at the mount point and one `warning` of kind `timeout` whose `path` and `source` are the mount's path, and `success` is true.
- The same holds for `tree("/")` and for `glob("/*")`.
- The `detail` of the record names the verb and the timeout, and says the mount asked alone is waited for.
- A `tree` over a region sends a mount's `tree` after that mount's `stat` has answered, and never before.
- A `tree` over a region sends no `tree` to a mount whose `stat` was late, and shows its mount point bare.
- A mount whose `stat` answers and whose `tree` is still running is waited for: the `tree` over the region is not done after four timeouts, and returns the mount's rows when the gate opens.
- A mount that cannot answer `stat` is asked for its `tree`.
- `ls`, `stat`, `tree` and `read` of a path inside the stuck mount are still waiting after four timeouts, and answer when the gate opens.
- A `read` batch across two mounts, one stuck, is not done after four timeouts.
- A `write` batch across two mounts, one stuck, is not done after four timeouts, and returns both results when the gate opens.
- The stuck double sees one cancellation at its timeout.
- The caller has its result while the cancelled double is still unwinding behind a second gate.
- A cancelled call that ends with a fault reaches the event loop's exception handler and no caller, and the kernel holds no reference to it afterwards.
- Cancelling a caller cancels its storage calls still in flight.
- A mount's `timeout` overrides the kernel's. `update_mount` changes it for the next call, and leaves it alone when the argument is left out. `None` removes it. `to_payload()` carries it. Zero and a negative number raise `ValueError`.
- A mount with `timeout=None` is not timed, and neither is any mount of a kernel with `mount_timeout=None`.
- A storage that answers inside the timeout with a `truncated` warning keeps its rows and its warning, and no `timeout` record is added.
- `close()` ends within `close_timeout` when a cancelled call never ends, and the storage's `close` was called. A storage whose own close runs out the time still raises that timeout from `close()`, as any close error is raised today.
- An `ls` batch that names a directory which holds a stuck mount returns that directory's other rows, a bare row at the mount point and one `warning` of kind `timeout`, and the rows of the batch's other targets.
- An in-memory storage holds every row it held before, after a timed `stat` of its root was cancelled inside a statement. This test fails until landing 1 is built.
- A healthy `ls` of a directory with three mount points makes one `ls` call on the parent and one `stat` call on each mount.

Landing 3.

- With one mount stuck, `glob("**")`, `grep` and `search` across mounts return the other mounts' rows and one `warning` of kind `timeout`.
- A `grep` that names two mounts, one stuck, returns the other's rows and one `error` of kind `timeout`, and `success` is false.
- A `grep` that reaches exactly one storage is not done after four timeouts.
- A `glob` with a root named in a stuck mount and a root named in another returns the other's rows and one `error` of kind `timeout`: the stuck mount's root probe was timed.
- A `glob` across mounts whose pattern matches a stuck mount's mount point records one `stat` call on that storage and one cancellation, not two.
- A `glob` whose judging of mount points is held past a mount's timeout is not cut by it: the kernel's own stage keeps its stage budget.

Landing 4.

- After a late call, a second `ls("/")` makes no call on that mount's storage, shows the mount point bare, and carries one `warning` of kind `backend_unavailable` with `retry_after_ms`.
- Of several timed calls that arrive after a timeout has passed, one is sent.
- A probe that answers clears the mark: the call after it reaches the storage and carries no record.
- A probe that is late leaves the mark.
- The mark clears while the first late call is still unwinding.
- `update_mount` with a `timeout` clears the mark. A mount removed and added again is not marked.
- While a mount is marked, `ls` of a path inside it still calls its storage.
- A mount whose `tree` runs long is never marked.

## Scope

In: the timed wait and the cancel; the `timeout` record; `timeout` on `Mount`, `add_mount`, `update_mount` and the payload; `mount_timeout` on the constructors of both kernels; the gate on `tree`; the kept tasks, the mark and the probe; what `close()` does; the default in `vfs/mounts.py`; the moves that pay for `base.py` and `sync.py`; the tests; the docs.

Out: every write. A read of one mount. A batch. The storage protocol. Statement timeouts on any engine. A timeout for each call. The code of decision 10. Landing 1, which has its own spec.

## What the docs must say

- A listing or a search that reaches several mounts waits a set time for each. A mount that is late shows in a listing as a bare row, and the result carries a `timeout` record that names it.
- A `timeout` or `backend_unavailable` record on a mount means none of that mount's rows are in the result. Retry later.
- A call that names one mount is waited for without limit, and so is a batch of rows. A host that needs a limit there puts its own around the call.
- A `tree` over several mounts lists a mount only after that mount's root has answered.
- A write is never cut by time.
- `timeout` on a mount and `mount_timeout` on the kernel are seconds, and `None` waits without limit.
- A storage built with stage budgets longer than the default needs a mount `timeout` of at least three of its own budgets.
- A call that was late is cancelled. On some engines the statement may still run for a while on the server.
- A How-to page, on putting a time limit on a call, says what a caller may count on after a cancelled call: a write cancelled before its commit has begun changes nothing, and one cancelled at its commit or after has landed whole. `documentation/maintainers/cancellation.md` is the page for people who change VFS, and this one is for people who use it.

Pages: `documentation/maintainers/mounts.md`, whose last section says a listing waits with no time limit; the Mount term in the glossary; the docstrings of the kernel class, `add_mount`, `update_mount`, `close`, `Mount`, `MountPayload`, `gather_settled`, and of `ls`, `tree`, `glob`, `grep` and `search`.

## Earlier decisions this reverses

- Decision 6 of "A mount is listed as a directory is" says no time budget is added and a listing waits for each child. A listing now waits for each child up to its timeout.
- That spec's `tree` asks the target and every mount beneath it at the same time. A mount's `tree` now follows its `stat`.

## What the review found, and the answer

| Finding | Answer |
|---|---|
| H1. A late call never ends, and its storage has no way back. | Taken in part. The late call is cancelled, at the first timeout and not the second. The mark no longer waits on it. No promise is made that a driver ends within a fixed time, because two of them cannot be made to. |
| H2. The rule that stops asking is keyed too coarsely and misreads its precedent. | Taken. Decision 7 is rewritten with a probe and three ways to clear, keyed by mount, and the memo's reading of gRPC is corrected. |
| M1. The record's advice leads into the untimed call. | Taken in part. The record and the docs advise a retry and state that the mount asked alone is waited for. The warning about a lost storage is not put in a record: landing 1 removes the hazard first. |
| M2. Where the code goes, and what the spec stands on. | Taken, with a different seam. The listing calls the timing function itself, so `AskStorage` gains no flag. "Builds on" and "Where the code goes" are new. |
| M3. A fixed time on `tree` is a ceiling on size. | Taken, by a different fix. A `tree` is not timed at all. It is gated on the root's `stat`. A batch is no longer timed either, for the same reason. |
| M4. Several landings. | Taken. Five, with the defect first and decision 10 not built. |
| L1. Naming and the `0` sentinel. | Taken in part. `None` means no timeout and one noun is used. No public constant is added: an argument left out means the default in `add_mount` and no change in `update_mount`. |
| L2. The default ignores a storage's own budgets. | Taken, in decision 8 and the docs. |
| L3. The kind of the skip record. | Taken. `backend_unavailable` with `retry_after_ms`. |
| L4. The order in `close()`. | Taken as written. |
| L5. How a late fault reaches the exception handler. | Taken as written. |
| L6. Timing rules for the tests. | Taken as written. |

The second review confirmed the answers above and raised these.

| Finding | Answer |
|---|---|
| M5. Landing 3's hand-over in `_route_fanout` times a kernel stage, times each head twice, and has no mount for a root probe. | Taken, with a different seam. Checked at `a64dd18c` and true. Nothing is timed at the gather. Each call is timed where it is built, through a `timed` keyword on `MountListing.called`, so `_Dispatches` needs no new field. |
| L7. A batch is said to be untimed, yet the `stat` of a mounted root inside it is timed. | Taken as written, in decision 2, with a test. |
| The wording of the `close()` test. | Taken as written. |
| H1's note: on the in-memory storage the cancel stops nothing in flight. | Taken, in the table of decision 6. |

## Not checked

- **The server engines.** Every experiment ran on SQLite. The four server rows of the table in decision 6 are read from driver source. What a cancel leaves on each, and how long a cancelled task is held on a dead peer, need the engine legs.
- **A peer that has gone silent.** Every experiment used a slow statement that ends.
- **The gate on `tree`.** Decision 3 was not spiked. The spike of the first draft timed every call.
- **The mark and the probe.** Decision 7 was not spiked.
- **The line counts.** The 21 lines of `close()`, the 18 of `_merge_fanout` and the seven of `grant` were counted at `a64dd18c`. No file was edited, and `ruff format` was not run on the result. The dozen lines landing 3 gains are an estimate.
- **The code at `e97ca9a9`.** The checkout moved there while this draft was written. Only its line count of `base.py` and the fact that the search-filters spec is built were read. The names in "Where the code goes" were read at `a64dd18c`.
- **Landing 3's seam.** The `timed` keyword through `_dispatch_entry`, `_dispatch_read` and `listed` was read against the code and was not spiked.
- **Whether three stage budgets is enough** for a storage's slowest honest `grep` or `search` at the reference deployment.
- **The number of mounts and of timed calls in a deployment.** The 600 in "Cost" assumes every call reaches the late mount.

## Choices to confirm

Each can be answered with one word.

1. **Is there a default timeout?** Recommended: yes, 30 seconds. Alternative: no, a mount is timed only when it is given a number, as in almost every system studied. Its cost: the hang in "The problem" stays until each deployment sets one.
2. **Is a late call cancelled?** Recommended: yes, at its timeout, with nobody waiting. Alternative: leave it running. Its cost: on a dead peer it holds a connection and a snapshot with no end.
3. **Is the addressed storage timed too?** Recommended: no. Alternative: yes. Its cost: a fixed time becomes a ceiling on an honest long read of one mount, such as a `tree` of a large mount or a 10,000-row batch, with no narrower call to fall back on.
4. **Is the mark built?** Recommended: yes, as landing 4. Alternative: no. Its cost: every listing above a dead mount waits a whole timeout for as long as the mount is down.

## One line

A listing or a search that reaches several mounts waits a set time for each small or budgeted call, returns the others' rows with a record that names the late mount, cancels the late call, and asks a marked mount once in each timeout; a `tree`, a batch, a read of one mount and every write are never cut by time.
