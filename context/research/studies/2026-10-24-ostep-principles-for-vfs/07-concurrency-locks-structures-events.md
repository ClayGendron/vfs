# Study 07: concurrency, locks, concurrent structures and events

- **Date:** 2026-10-24
- **Brief:** `00-brief.md` in this folder.
- **Book section:** OSTEP version 1.10, chapters 26, 28, 29, 30, 32 and 33 (the session's pdftotext split, file `07-concurrency-locks-structures-events.txt`). Chapters 26, 29, 32 and 33 read in full. Chapters 28 and 30 read for their principles; the hardware-instruction detail of chapter 28 (test-and-set, LL/SC, Peterson) skipped. Page numbers are the book's own, which restart at 1 in every chapter, so a citation reads "ch. 32 p. 7".
- **No book text is quoted.** Every idea from the book is paraphrased and cited by chapter and page.
- **vfs at HEAD `ac5c515`** (2026-10-24). Read: `CLAUDE.md`, `src/vfs/base.py`, `src/vfs/storage/backends/database/` (`writes.py`, `serialized.py`, `dialects.py`, `membership.py`, `engine.py`, `offload.py`, `edges.py`, `segments.py`, `glean.py`, `grep.py`, `lexical.py`, `backend.py`), `src/vfs/results/kinds.py`, `crates/vfs-core/src/` (`python.rs`, `verify.rs`), ADRs 013, 017, 019, 025, 044, 078, spec 167, and the 2026-10-23 kernel memo (§0, §4).
- **Correction to the brief that set this study:** it named ADRs 027 and 028 as the serialization-point records. At HEAD they are "delete never destroys" and "turso in-memory backend". The serialization point is ADR **078**, and the conflict re-drive and batch-writer doctrine is ADR **025**. This study cites those.
- **Reference repos read for two facts** (read-only, not refreshed; not a study set): `~/Git/Repos/linux` at `faeab1661` (`fs/namei.c`, `lock_rename`), `~/Git/Repos/sqlite` at `3d17c3f9e` (`src/main.c`, `sqliteDefaultBusyCallback`).
- **Experiments:** two scripts in the session scratchpad, `/private/tmp/claude-501/-Users-claygendron-Git-Repos-vfs/5d8df80f-e1a8-4b32-8c5d-fd4fe65a3cc5/scratchpad/s07/lost_update.py` and `/private/tmp/claude-501/-Users-claygendron-Git-Repos-vfs/5d8df80f-e1a8-4b32-8c5d-fd4fe65a3cc5/scratchpad/s07/lock_order.py`, run with `uv run python -I` against a file-backed SQLite mount.
- **Labels:** **READ** (the book with chapter and page, or a vfs file at `ac5c515`), **EXECUTED** (ran here), **INFERRED** (my reasoning).

Three words used all through this study:

- A **critical section** is a stretch of code that touches shared state and must not run in two places at once.
- A **lost update** is the classic race: two workers each read a value, each compute a new one from what they read, and each write. The second write erases the first.
- A **lock order** is an agreed sequence for taking locks, so that two workers never each hold what the other one wants.

---

## 1. What the chapters say

**Chapter 26, Concurrency: an introduction.** A thread is a second point of execution inside one address space. Two threads that update one shared variable can interleave mid-update, because one line of source is several machine steps: load, change, store (READ, ch. 26 pp. 6-10). The result then depends on timing; the book calls that a race condition, and the code that races a critical section (READ, ch. 26 p. 10). The cure is mutual exclusion, so that only one thread is inside the section at a time. Behind it is a larger idea: a group of actions that must appear to happen all at once or not at all, which the database world calls a transaction (READ, ch. 26 p. 11). The chapter closes with a file-system example that matters here: two processes that both append to one file both update shared structures (the size, the block map), so the append is a critical section (READ, ch. 26 p. 13). A second need is named too: one thread waiting for another to finish something (READ, ch. 26 p. 12).

**Chapter 28, Locks.** A lock is a variable that is either free or held by exactly one owner. Wrapping a critical section in lock and unlock makes it behave like one indivisible step (READ, ch. 28 pp. 1-2). One lock for everything is coarse-grained; one lock per piece of data is fine-grained and allows more parallel work (READ, ch. 28 p. 2). The chapter's lasting tool is its three test questions for any lock: does it give mutual exclusion (correctness); does every waiter get a fair turn, or can one starve (fairness); and what does it cost with no contention, with contention on one CPU, and with contention across many CPUs (performance) (READ, ch. 28 p. 3). Spin locks pass correctness and fail fairness (READ, ch. 28 p. 9). A ticket lock built on fetch-and-add hands out turns in arrival order, so it is fair (READ, ch. 28 pp. 12-13). Yielding instead of spinning wastes less but still lets one thread starve (READ, ch. 28 pp. 14-15). A queue of sleeping waiters fixes waste and starvation together (READ, ch. 28 pp. 15-16). What the chapter calls a two-phase lock is: spin for a moment, then sleep (READ, ch. 28 p. 20). That is not the database meaning of two-phase locking; see §4.

**Chapter 29, Lock-based concurrent data structures.** The simplest thread-safe structure is the old one plus one big lock, taken on every call. It is correct. If it is fast enough, stop there (READ, ch. 29 pp. 1-2). A counter with one lock scales badly: four threads take far longer than one (READ, ch. 29 pp. 2-3). The approximate counter fixes that. Each CPU keeps a local count under its own lock, and every so often (a threshold the book calls S) moves its local total into one global count. A larger S gives more speed but a global value that lags the truth by up to S per CPU (READ, ch. 29 pp. 3-6). Two warnings follow. More concurrency is not automatically faster: a lock per list node (hand-over-hand locking) usually loses to one lock, because taking and releasing locks costs more than it saves (READ, ch. 29 pp. 7, 10). And early returns are where locks leak: a path that exits without undoing what it took is a common bug site (READ, ch. 29 p. 10). A hash table with a lock per bucket scales very well (READ, ch. 29 p. 12). The summary rule is Knuth's: start with one big lock and refine only when a measured problem appears. Linux and SunOS both began with one big kernel lock and split it later, when multicore made it the bottleneck (READ, ch. 29 p. 14).

**Chapter 30, Condition variables.** A condition variable is a queue a thread can sleep on until some state changes, and another thread wakes it (READ, ch. 30 pp. 1-2). Hold the lock when you wait and when you signal (READ, ch. 30 p. 5). Under the semantics nearly every system uses (Mesa semantics), a wake-up is only a hint that the state may have changed. By the time the woken thread runs, another thread may have changed it back (READ, ch. 30 pp. 9-10). So the woken thread must check its condition again, in a loop, every time (READ, ch. 30 pp. 10, 14). The producer/consumer problem, a shared bounded buffer between writers and readers, is the chapter's worked example. The book notes a Unix pipe is exactly such a buffer (READ, ch. 30 p. 6).

**Chapter 32, Common concurrency problems.** A study of real bugs in MySQL, Apache, Mozilla and OpenOffice (Lu et al.) found most were not deadlocks (READ, ch. 32 pp. 1-2). Of the non-deadlock bugs, nearly all (the book gives 97%) were one of two kinds (READ, ch. 32 p. 5). An **atomicity violation** is a check-then-act pair that was meant to be indivisible and was not (READ, ch. 32 pp. 2-3). An **order violation** is a rule that one step must come before another, with nothing enforcing it (READ, ch. 32 pp. 3-5). Deadlock needs four conditions at once: mutual exclusion, hold-and-wait, no preemption, and a circular wait (READ, ch. 32 p. 7). Remove any one and deadlock cannot happen. The most practical removal is a fixed order for taking locks. A total order is best. A partial order by lock class works in big systems; the book cites the Linux memory-map code. Ordering locks by their address is a neat trick when a function receives two locks in either order (READ, ch. 32 pp. 7-8). Hold-and-wait can be removed by taking one global lock before taking any others, at a cost in concurrency (READ, ch. 32 pp. 8-9). No-preemption can be dodged with trylock and back-off, but two threads can then retry in step forever (livelock); a random delay before retrying breaks the rhythm (READ, ch. 32 p. 9). Lock-free code built on compare-and-swap removes mutual exclusion itself (READ, ch. 32 pp. 10-12). Avoidance by scheduling needs to know in advance which locks each task takes, and it costs parallelism (READ, ch. 32 pp. 12-13). Detect and recover is the last option. It is sensible when deadlock is rare, and many database systems do it (READ, ch. 32 pp. 13-14). Tom West's law sits beside it: do not spend heavily to prevent a rare, cheap failure (READ, ch. 32 p. 13).

**Chapter 33, Event-based concurrency.** An event loop waits for something to happen, then runs a short handler for it, one at a time (READ, ch. 33 pp. 1-2). Choosing which event to handle next is the scheduling, so the program controls it (READ, ch. 33 p. 2). With one CPU and one loop, no lock is needed, because nothing interrupts a handler (READ, ch. 33 p. 5). The price is one hard rule: a handler must never make a call that blocks, because a blocked handler stops the whole server (READ, ch. 33 p. 5). Asynchronous I/O is the answer: start the I/O, return at once, learn later that it finished (READ, ch. 33 pp. 6-7). Where no async form exists, a hybrid hands the blocking work to a pool of threads (READ, ch. 33 p. 7). The cost is state: the handler that finishes the work must find what the first handler knew. The book calls the fix a continuation, a saved record of what to do next (READ, ch. 33 pp. 7-9). Four things stay hard (READ, ch. 33 p. 9). Multicore brings locks back. Implicit blocking, such as a page fault, still stalls the loop. A routine that changes from non-blocking to blocking forces its callers to change. And disk and network async I/O never fully unify.

---

## 2. Principles vfs should adopt

vfs's concurrency has three layers. The study treats them in turn.

| Layer | What runs concurrently | Book chapter that fits |
|---|---|---|
| In one process | asyncio tasks on one event loop | ch. 33, almost exactly |
| Across processes | many MCP servers, CLI calls and ETL workers on one database | ch. 26, 28 and 32: the SQL engine's row locks are the locks |
| In the Rust engine | rayon worker threads inside one native call | ch. 29 |

Items 1 to 5 answer the five questions this study was set. Items 6 to 14 are further principles the chapters teach.

### 1. A read followed by a write is a critical section; without a guard, the second writer silently erases the first

- **Book:** ch. 26 pp. 6-10 (the counter race), p. 13 (two processes appending to one file is the book's own example).
- **Status: half follows.**
- **Inside one vfs call, vfs is safe.** Every material update carries its check inside the write: `WHERE version = base AND path = path-at-snapshot AND deleted_at IS NULL` (READ, `writes.py` `_guarded_stmt` and the `_update_materials` docstring; ADR 013 pin 1). That is compare-and-swap done by the SQL engine (book: ch. 32 pp. 10-11). A miss classifies as `vfs.conflict`, retryable (READ, `writes.py` `_conflict`). `edit` reads the body and writes the new one inside the same transaction, under the same guard (READ, `writes.py` `edit_rows`). Parent bumps are `version = version + 1` computed by the engine, the single indivisible add the book wishes for in ch. 26 pp. 11-12, so rival bumps compose and never lose a count (READ, `writes.py` `_bump_parents`).
- **Across two vfs calls, vfs loses data.** `write` takes no version precondition (READ, `base.py` `write` signature: `path`, `content`, `data`, `overwrite`, `parents`, `authority`, nothing else). Spec 167 says this outright: `>>` is a `read` then a `write`, with no version precondition, so concurrent appends can lose data (READ, `context/specs/active/167-the-shell-pipeline-core/spec.md` lines 383-386). Yesterday's memo is confirmed from the spec text.
- **EXECUTED.** On a file-backed SQLite mount, 20 asyncio tasks each read `/log2.txt`, appended one line, and wrote it back. **All 20 writes reported success. One line survived.** A two-caller interleaving (both read, then both write) kept only the second caller's line, again with both writes reporting success. The same 20 appends done through `edit` (replace the `END` marker with `line + END`) kept all 20 lines.
- **Why this is worse than a failure:** the loser is told it succeeded. Nothing in the result says a rival's bytes were erased (EXECUTED, the `success` count above).
- **The error already exists; the argument does not.** `ErrorKind.conflict` is documented as a stale precondition, re-read and retry with the current version (READ, `results/kinds.py` line 78). No public write verb lets a caller state that precondition.
- **Change it implies:** `write(if_version=)` and `write(if_absent=)`, the conditional writes the kernel memo §4.2 already proposes; and `>>` built as a guarded append (an `if_version` write, or a storage append that runs read and write in one transaction, as `edit` already does), never as two calls. (INFERRED.)

### 2. Take locks in one fixed order, so no two writers can each hold what the other wants

- **Book:** ch. 32 pp. 7-8 (circular wait; total and partial order; order by address).
- **Status: half follows.** The rule is stated and followed on some paths, and not on the hot one.
- **Where vfs orders its locks (READ):**
  - The doctrine is written down: callers sort and chunk the keys they lock, so rival batches lock in one order (`dialects.py` `lock_rows` docstring; `membership.py` `locked_lookup` docstring).
  - Parent bumps run in sorted path order (`writes.py` line 1049, `sorted(bumps)`). EXECUTED: a create batch given `/e/q`, `/d/p`, `/e/n` bumped `/d` then `/e`.
  - `bump_many` sorts ids (`serialized.py` line 228).
  - Edge endpoints are locked in sorted path order (`edges.py` `_endpoint_ids`), and edge drift repair locks sorted ids (`edges.py` line 316).
- **Where it does not (READ and EXECUTED):**
  - The guarded material updates of a write batch run in the **caller's order**. `plan.staged` is a dict filled in request order (`writes.py` `write_rows`, `staging.py` `self.staged`), and `_apply` walks it. EXECUTED: an overwrite batch given `c, a, b, z, y` issued its `UPDATE` rows in exactly that order.
  - Creates insert in the caller's order inside each depth layer (EXECUTED: `q, p, n`).
  - Segment drift repair locks entry rows in table-scan order, then orphans, unsorted (`segments.py` lines 211-214). That contradicts `locked_lookup`'s own docstring, which tells callers to sort.
- **The phases do form a partial order by class (INFERRED from the READ sequence in `_apply`):** creates, then file-row updates, then version rows, then bodies, then parent directory rows last. Files and directories are separate classes, and directories are always taken last. That is the same shape as the Linux lock classes the book cites. What is missing is an order *inside* the file class.
- **The four deadlock conditions against a vfs batch write:**

  | Condition | Present in a vfs write batch? | Evidence |
  |---|---|---|
  | Mutual exclusion | Yes. An `UPDATE` holds a row lock to commit; an insert holds a unique-key lock. | INFERRED from engine semantics; `lock_rows` docstring says the same (READ) |
  | Hold-and-wait | Yes. A batch holds every row it touched in earlier statements and chunks while it waits for the next. | READ, `_apply` runs many statements in one transaction |
  | No preemption | Mostly. Only the engine's deadlock detector takes a lock away, by aborting one transaction. | INFERRED |
  | Circular wait | **Possible.** Two batches that update the same two files in opposite caller orders. | INFERRED from the EXECUTED caller-order finding |

- **Engine by engine (INFERRED):** this can happen on Postgres, SQL Server, Oracle and MariaDB. It cannot happen on SQLite, where the writer lock covers the whole database for the whole transaction (READ, `engine.py` docstring, `BEGIN IMMEDIATE`). One global lock has no hold-and-wait.
- **The backstop is real (READ):** the engines' deadlock codes are declared retryable (`40P01` and `40001` in `dialects.py` line 349; MariaDB `1213` line 507; Oracle `ORA-00060` line 535), and `EngineHost.with_retry` re-runs the whole method from a fresh snapshot (`engine.py` lines 297-320). The race suite drives deadlocks on purpose and requires that every one rides the retry channel (`tests/storage/database/test_races.py` lines 198-203).
- **Change it implies:** sort the staged rows by `entry_id` (or path) before the insert layers and before the guarded-update pass; the plan already holds them in a dict, so the sort is cheap. Sort the ids in `repair_segment_drift`. One caveat: for a set-based `UPDATE ... FROM (VALUES ...)`, the engine's plan picks the row order, so sorting is a strong hint, not a proof. Detect and recover stays the backstop. (INFERRED.)

### 3. An event loop must never block

- **Book:** ch. 33 p. 5 (the rule, and the tip that states it); p. 7 (the thread-pool hybrid); p. 9 (implicit blocking).
- **Status: follows, with a few CPU residuals.**
- **What keeps the loop free (READ):**
  - All database I/O goes through async drivers under SQLAlchemy's async engine. SQLite rides `aiosqlite`, whose own worker thread owns the real handle (`engine.py` `_load_sqlite_vec` docstring).
  - The offload seam moves CPU-heavy work to a thread pool the backend owns (`offload.py`): grep's verify stage, reindex's chunk and posting stages, the lexical build (`lexical.py` lines 85-97), glean's overlay blocks (`glean.py` line 872), the render step (`backend.py` line 1288), and centrality signals (`signals.py` line 123). This is the book's hybrid of events plus a pool for the work that would block.
  - Embedding calls run in an executor (`embedding/provider.py` line 136).
  - The Rust matcher releases the GIL for a whole batch (`offload.py` docstring; `py.detach` in `python.rs`).
- **No sync I/O found (EXECUTED grep over `src/vfs`):** no `run_in_executor` outside the embedding provider, no `to_thread`, no `run_coroutine_threadsafe`, no `time.sleep`, no builtin `open(`, no `requests`, `urllib` or `socket` use. The only threads are the offload pool and the embedding executor, and `offload.py` declares itself the tree's one deliberate threaded code.
- **Residual CPU that still runs on the loop (READ; impact INFERRED):**
  - glean's lexicon step calls the Rust `candidate_ids` over every block of every query term, then once more per term (`glean.py` lines 731-741). The function's own docstring says this work grows with the terms' corpus-wide document frequency, not with what the caller sees. It is not offloaded.
  - grep's `candidate_ids` call is inline too (`grep.py` line 422); its docstring says it is sub-millisecond even on the widest ladders.
  - sha256 and line counting of every body run inside `Entry` validation and the version mint (`models/entry.py` line 232, `versions.py` line 151).
  - One pydantic `Observation` is built per returned row; the kernel memo measured this as the cost of a 10,000-row listing. These are the vfs version of the book's page-fault problem: not a blocking call, but work that holds the loop all the same.
- **The book's other event lessons, already absorbed (READ):** `async`/`await` is the continuation the book builds by hand (ch. 33 pp. 7-9), so vfs pays no manual stack cost. The offload seam's four laws (absolute deadline, one batch in flight, cancellation as safe abandonment, survival across close) are the care ch. 33 p. 9 asks for when a routine's blocking nature changes.
- **Change it implies:** a counted pin per verb, in the style `CLAUDE.md` asks for: count the native calls a verb makes on the loop thread versus through `call_offloaded`, so a new inline kernel is a visible change. Offload glean's lexicon union when its input block count passes a threshold. (INFERRED.)

### 4. One shared counter bumped by every writer does not scale; keep local counts and merge, trading exactness for throughput

- **Book:** ch. 29 pp. 1-6 (the precise counter, the approximate counter, the threshold S).
- **Status: largely follows. One hot counter remains, and an ADR already names its removal.**
- **Global counters vfs has already removed or never had (READ):**

  | Counter | Status | Record |
  |---|---|---|
  | Per-mount revision counter | Removed. On Postgres it queued every writer behind one row, about one writer per mount. | ADR 013 (context and pin 2) |
  | Entry ids | Never a sequence. ULIDs minted client-side, no shared state. | ADR 019 |
  | Version numbers | One per-entry monotone value; no two entries' versions compare. | ADR 017; `writes.py` module docstring |
  | Mount-wide change cursor | `updated_at`, coarse wall clock, deliberately approximate. | ADR 013 pin 4 |
  | Serialization point | Moved off the hot meta row onto its own lock row. | ADR 078 |
  | Corpus statistics (`n_docs`, `avg_dl`) | Built once per reindex epoch, not on every write; glean re-derives the visible statistics at query time. | `lexical.py` docstring; `glean.py` `_visible_corpus` |

  The corpus statistics are the approximate counter almost exactly: the global value lags the truth until the next reindex, and that lag buys a write path that never touches them (INFERRED).
- **The counter that remains: the parent directory's version (READ).** Every create or removal under a directory runs `version = version + 1` on the parent's row (`writes.py` `_bump_parents`; `serialized.py` `bump`). That is a precise counter per directory. `/` is the hottest one: ADR 078 rejected locking the root row precisely because every create under `/` bumps it.
- **The ETL batch is fine (READ and EXECUTED).** One batch bumps each distinct parent once, whatever the number of children (`derive_bumps`, the sorted `pairs`). That is the approximate counter's local accumulation, with the batch as the threshold S.
- **Many agents writing into one folder are not (INFERRED).** Each agent's create holds the parent row's lock until it commits, so creates in one directory commit one at a time. On Postgres the op isolation is `REPEATABLE READ` (READ, `dialects.py` line 436), so a second writer that finds the row changed by a committed rival gets a serialization failure and redrives. Under a burst, some writers will spend their four attempts.
- **ADR 013 pin 5 already names the direction:** derive a directory's change state from its children at read time, through the `parent_id` index, and take stored parent bumps off the write path (READ). That is the book's lesson applied: stop sharing one count, sum the parts when someone asks.
- **The Rust engine (READ, `crates/vfs-core/src`).** The parallel kernels (`verify.rs`, `chunk.rs`, `links.rs`, `vectors.rs`) are rayon map-and-collect over independent items. No shared mutable state. A relaxed `AtomicBool` serves only as a "deadline hit" flag. Each thread works alone and the results merge at the end, which is the approximate counter's shape. One global `Mutex` exists: `python.rs` line 30, a single `GramExtractor` scratch bitmap behind `distinct_gram_count`. That function does not release the GIL, so the GIL already serializes its callers and the Mutex is uncontended (INFERRED). If it ever detaches the GIL, it becomes a big lock across the offload workers; give each worker its own scratch then.
- **Change it implies:** none new. This study adds two things to ADR 013 pin 5. The book's evidence that it is the right direction. And a test shape for when it lands: count the statements that touch a parent row per create, and pin the count at zero.

### 5. Judge every lock on three axes: correctness, fairness, performance

- **Book:** ch. 28 p. 3 (the three axes, and performance split into no contention, contention on one CPU, contention on many), p. 9 (a spin lock scored), pp. 12-16 (ticket and queue locks for fairness).
- **Status: half follows.** The ADRs argue correctness and performance with care. **Fairness is never named.**
- **The arbitration design scored (READ for the mechanism; the fairness and contention cells are INFERRED unless marked):**

  | Mechanism | Correctness | Fairness | Performance, no contention | Performance, contended |
  |---|---|---|---|---|
  | Create arbitration (`upsert` or `catch_retry`, `writes.py`) | Unique `(parent_id, name)` index decides the winner; the loser is classified, adopted or clobbered by declared rule | Whoever commits first wins; no order promise | Zero extra statements on upsert engines | `catch_retry` re-drives a conflicted chunk row by row (ADR 025) |
  | Guarded update (version compare-and-swap) | Guard in the `UPDATE` itself; misses classify `conflict` or redrive | A loser retries; nothing bounds how often it loses | Zero extra statements | Whole-batch re-drive is O(batch) per conflict, accepted in ADR 025 |
  | Serialization point (`vfs_lock` row, `serialize()`) | One serialized verb per mount at a time | The engine's lock-wait queue on Postgres, SQL Server, Oracle, MariaDB (arrival order, roughly); SQLite's busy handler sleeps on a delay table and retries, with no queue (READ, sqlite `src/main.c` `sqliteDefaultBusyCallback`), so no starvation guard there | One statement per verb (ADR 078) | A 10,000-row subtree delete makes every other delete, move, copy, restore and sweep on the mount wait; writes and reads do not wait (ADR 078) |
  | Retry channel (`with_retry`, `engine.py`) | Whole method from a fresh snapshot; exhaustion is a retryable `conflict` | 4 attempts, 50 ms doubling, **no jitter** (READ, `engine.py` lines 137-138, 308-319); two rivals that collided back off in step, the rhythm ch. 32 p. 9 warns of | No cost when nothing conflicts | About 350 ms of sleep at worst (50, 100, 200 ms between four attempts), then refusal: a bounded failure, not starvation forever |
  | Read coherence (ADR 044) | Authoritative verdict re-read after the reads it vouches for | Readers never wait, writers never wait | Two combined reads | About 1 ms when a rival demotion lands (ADR 044 measurement) |
  | One-connection pool lock (`_SerializedSessions`, `engine.py`) | One op at a time on a shared DBAPI connection | `asyncio.Lock` wakes waiters in arrival order | Uncontended acquire | Ops queue in order |
  | Reindex lease (`backend.py` lines 1121-1185) | One runner; a heartbeat proves it is still held | A crashed holder is preempted by TTL expiry | One beat statement per interval | A second runner is refused, not queued |

- **Two gaps the table shows (INFERRED):**
  - The retry backoff has no random part. The book's cure for livelock is a random delay (ch. 32 p. 9). Adding jitter is one line in `with_retry`.
  - No ADR on arbitration states what a loser can expect. "Up to four tries, then a retryable `conflict`" is a fine answer. It should be the written contract, so that an ETL caller knows to retry and an agent knows the refusal is honest.
- **Change it implies:** add fairness as a named axis in the next arbitration or concurrency ADR; add jitter to `with_retry`.

### 6. Start with one big lock; split it only when contention is measured

- **Book:** ch. 29 p. 14 (Knuth's law, the big kernel lock story), p. 7 (more concurrency is not automatically faster).
- **Status: follows.**
- **Evidence (READ):** delete, restore, sweep, move and copy run one at a time per mount behind one row (ADR 078; `serialized.py` `serialize`). ADR 025 refuses the chunked-savepoint optimization until production telemetry shows conflicts inside large batches. Linux chose the same grain for the same job: a cross-directory rename takes one per-filesystem mutex before it locks the two directories (READ, linux `fs/namei.c` `lock_rename`, `s_vfs_rename_mutex`).
- **Change it implies:** none now. When the time comes, the trigger is measured queue time on the serialization point. ADR 025's revisit trigger needs a retry count to exist; `with_retry` keeps none (READ). A counter of retries per verb is the measurement that trigger depends on (INFERRED).

### 7. Fold the check into the act (atomicity violations)

- **Book:** ch. 32 pp. 2-3 (check-then-use without a lock); p. 5 (atomicity and order violations are nearly all non-deadlock bugs).
- **Status: follows inside a call** (item 1 covers the cross-call gap).
- **Evidence (READ):** every guard predicate lives in the same statement as the write (`writes.py` `_update_materials` docstring). A guard read that must stay true until commit uses `lock_rows` (`dialects.py`). A serialized verb's reads all run after it takes the serialization point, so its refusal checks judge post-rival state (`serialized.py` module docstring). Parent bumps check `path` and `deleted_at` in the bump itself, so a parent moved or deleted mid-window fails the bump (`writes.py` `_bump_parents`).
- **Change it implies:** none beyond item 1.

### 8. Make every ordering rule structural (order violations)

- **Book:** ch. 32 pp. 3-5.
- **Status: follows.**
- **Evidence (READ):** creates insert parents before children, layer by depth (`writes.py` `_insert_creates`). The reindex lease cancels and awaits its heartbeat task *before* releasing, so a late beat can never revive a released lease (`backend.py` `_held_reindex_lease`). `serialize()` is always the verb's first statement (`serialized.py`).
- **Change it implies:** none.

### 9. A wake-up is a hint; check the condition again (Mesa semantics, while not if)

- **Book:** ch. 30 pp. 9-10, p. 14.
- **Status: follows.**
- **Evidence (READ):** ADR 044 is this rule for grep. The preamble's emptiness verdict is advisory. The verdict that permits skipping the scan is read again after the reads it vouches for. `with_retry` re-derives everything from a fresh snapshot each attempt rather than patching the old plan (`engine.py`). The reindex run checks a `lost` event that a heartbeat sets (`backend.py`).
- **Change it implies:** none. This is the pattern a future write precondition should follow too: the version a caller presents is a hint, and the guard re-checks it at the write.

### 10. Detect and recover is a sound choice when the failure is rare and recovery is cheap

- **Book:** ch. 32 pp. 13-14 (databases detect deadlocks this way); p. 13 (Tom West's law).
- **Status: follows.**
- **Evidence (READ):** deadlock and serialization codes are retryable per dialect (`dialects.py`), the whole method retries (`engine.py`), and the race suite asserts that deadlocks ride that channel (`test_races.py`). ADR 025 accepts the costly re-drive because conflicts are rare.
- **Change it implies:** measure "rare". A retry counter per verb (item 6) is what turns this from assumption into evidence.

### 11. Avoidance by scheduling needs global knowledge and costs parallelism

- **Book:** ch. 32 pp. 12-13.
- **Status: half follows.** ADR 025's doctrine, one batch writer per mount or per disjoint subtree, is avoidance by scheduling, with the operator as the scheduler (READ). Nothing in vfs checks or reports a violation.
- **Change it implies:** none required. The doctrine is honest about being a documentation duty (ADR 025 decision 3).

### 12. Watch the exits: a path that returns early must undo what it took

- **Book:** ch. 29 p. 10.
- **Status: follows.**
- **Evidence (READ):** a failed batch runs no mutation statement at all, because staging finishes before execution (`writes.py` module docstring). Each op owns one transaction, which rolls back on any raise (`writes.py` docstring: functions never begin or commit). The one-connection lock is released in a `finally` (`engine.py` `_SerializedSession.__aexit__`). Offload cancellation leaves a worker that touches no session (`offload.py`).
- **Change it implies:** none.

### 13. In an event loop, atomicity lasts only until the next `await`

- **Book:** ch. 33 p. 5 (no locks needed, on one CPU, inside one handler) and p. 9 (multicore brings them back).
- **Status: follows.**
- **Evidence (READ):** mount-table changes that await take an `asyncio.Lock` (`base.py` line 368 and its four `async with` sites). The shared-connection pool takes one too (`engine.py` `_SerializedSessions`). Across processes, vfs relies on the SQL engine, which is correct: many vfs processes against one database is the book's multicore case, and there the locks come back.
- **Change it implies:** none.

### 14. Prefer models that need no locks at all

- **Book:** ch. 32 p. 14 (the summary's closing advice: new models such as MapReduce avoid locks; avoid locks unless you must).
- **Status: follows where it matters most.** The read path holds no locks and makes no writer wait (ADR 044). Index coverage is row state, not an ordered watermark, so reindex needs no fence (ADR 013 pin 3). The Rust kernels share nothing (item 4).
- **Change it implies:** none.

---

## 3. Nouns and verbs

"Adopt the name" means use the book's word. "Own name" means keep the concept under vfs's word. "Not have" means vfs should deliberately lack it.

| Book term (chapter, page) | vfs today | Verdict and reason |
|---|---|---|
| critical section (26 p. 10) | none as a word; the op's transaction | Own name: "the op's transaction" is the critical section, and every verb has exactly one |
| race condition (26 p. 10) | "race" in tests (`test_races.py`) | Adopt: already used |
| atomicity, transaction (26 p. 11) | one transaction per op; batches all-or-nothing | Own name: "a batch fails whole" (`writes.py`) |
| mutual exclusion (26 p. 10) | serialization point; row locks | Own name |
| lock, mutex, owner (28 pp. 1-2) | `vfs_lock` table; `lock_rows`; `asyncio.Lock` | Adopt the word lock for the row and the in-process lock; keep "serialization point" for the per-mount one |
| coarse vs fine-grained locking (28 p. 2) | per-mount serialization point vs per-row guards | Adopt the words in ADRs: they name the trade ADR 078 made |
| compare-and-swap (28 p. 10; 32 p. 10) | the version guard, `WHERE version = base` | Own name "guarded update"; say in docs that it is compare-and-swap |
| fetch-and-add (28 p. 12) | `version = version + 1` parent bump | Own name "bump" |
| ticket lock, fairness (28 pp. 3, 12-13) | none | Adopt fairness as an evaluation axis (item 5); do not build a ticket lock, the engines own lock queues |
| spin lock, yield (28 pp. 6-15) | none; SQLite's busy handler is a sleep-and-retry loop | Not have: vfs never spins; waits are engine queues or `asyncio.sleep` |
| queue lock, park/unpark, futex (28 pp. 15-19) | engine lock-wait queues; `asyncio.Lock` | Not have our own; the engine and asyncio provide it |
| two-phase lock (28 p. 20) | none | Not have the word: it collides with database two-phase locking (§4) |
| thread-safe structure (29 p. 1) | none | Not needed: Python state is per-op; shared state lives in the database |
| approximate counter, threshold S (29 pp. 3-6) | per-entry versions; epoch-built corpus statistics; batch-once parent bumps | Own names; cite the concept in ADR 013 pin 5's follow-up |
| hand-over-hand locking (29 pp. 9-10) | none | Not have: the book shows it rarely wins |
| big kernel lock (29 p. 14) | the per-mount serialization point | Own name; the analogy is useful in ADRs |
| condition variable, wait, signal (30 pp. 1-5) | `asyncio.Event` (reindex `lost`) | Own name; no cross-process wait exists (§4) |
| Mesa semantics, re-check in a loop (30 pp. 9-10, 14) | advisory then authoritative verdict (ADR 044); `with_retry` | Own name; ADR 044 is the vfs statement of it |
| producer/consumer, bounded buffer (30 p. 6) | spec 167's pipe between stages | Adopt the term bounded buffer in spec 167: the book itself names a pipe as one |
| atomicity violation, order violation (32 pp. 2-5) | none | Adopt both words for review checklists (`scale_review`, `adversarial_review`) |
| deadlock, four conditions (32 p. 7) | "deadlock" in docstrings and tests | Adopt: already used |
| lock ordering, total and partial (32 pp. 7-8) | "callers order the rows they lock (sorted keys)" (`lock_rows` docstring) | Adopt "lock order"; make it true on the write path (item 2) |
| prevention lock for hold-and-wait (32 pp. 8-9) | `serialize()` as a verb's first statement | Own name |
| trylock, livelock, random back-off (32 p. 9) | `with_retry` back-off, no jitter | Adopt the word livelock and add jitter (item 5) |
| lock-free (32 pp. 10-12) | the read path (ADR 044 title: read-path coherence without locks) | Adopt: ADR 044 already uses the idea |
| avoidance by scheduling (32 pp. 12-13) | one batch writer per subtree (ADR 025) | Own name; it is an operator duty, not a scheduler |
| detect and recover (32 pp. 13-14) | retryable classification plus `with_retry` | Own name "retry channel" |
| event loop, event handler (33 pp. 1-2) | asyncio loop; each verb coroutine | Adopt: Python's own words |
| blocking vs non-blocking call (33 p. 3) | "holds the loop" (`offload.py`) | Adopt the word blocking in reviews; a counted pin can enforce it (item 3) |
| asynchronous I/O (33 pp. 6-7) | async drivers through SQLAlchemy | Adopt: already true |
| hybrid with a thread pool (33 p. 7) | the offload seam, `call_offloaded` | Own name "offload" |
| continuation, manual stack management (33 pp. 7-9) | `async`/`await` frames | Not needed as a concept: the language gives it |
| implicit blocking (page fault) (33 p. 9) | inline CPU on the loop (item 3) | Adopt the idea under "loop occupancy" |

---

## 4. What does not transfer, and why

- **vfs never builds a lock.** The book builds locks from hardware instructions and kernel sleep queues (ch. 28). vfs takes its locks from the SQL engine: row locks, unique-index key locks, `FOR UPDATE` or `UPDLOCK`. It never spins and never touches an atomic instruction in Python. All of chapter 28's construction detail stays in the book. (INFERRED.)
- **The shared state is not shared memory.** The book's threads share one address space. vfs's processes share a database over a network. A vfs worker sees other workers' changes only through statements, and only as its isolation level allows. (INFERRED.)
- **Isolation levels have no book chapter.** The book's lock is binary: held or free. A database has shared, update and exclusive locks, plus snapshot reads. That is why the same vfs code waits on SQL Server's locking `READ COMMITTED` and does not wait on Postgres MVCC, the exact coupling ADR 078 fixed (READ, ADR 078 context). Postgres at `REPEATABLE READ` turns a lost-update race into a serialization failure instead of a wait (INFERRED). None of this is in the book.
- **Two-phase lock means two different things.** In the book it is spin briefly, then sleep (ch. 28 p. 20). In databases, two-phase locking means a transaction takes locks while it runs and releases them all at the end. vfs's one-transaction-per-op holds every row lock to commit, which is the database meaning (INFERRED). Using the word in a vfs ADR without saying which would confuse.
- **Detect and recover is cheaper here than in the book.** The book pictures recovery as a restart, maybe with a human involved (ch. 32 pp. 13-14). In a database the detector aborts one transaction and the client retries in milliseconds. So for vfs, detect and recover is a first-class strategy, not a last resort. (INFERRED.)
- **No condition variables across processes.** The book's wait-and-signal works inside one process. vfs has no cross-process wake-up: no `LISTEN/NOTIFY`, no notification table. Waiting for a reindex is a lease and a refusal, not a wake-up (READ, `backend.py`). The bounded-buffer lesson does fit the shell pipe of spec 167, because that runs inside one process. (INFERRED.)
- **Chapter 33's claim that events need no locks holds only inside one process and only between two `await`s.** vfs is many processes on one database, which is the book's multicore case (ch. 33 p. 9) as the normal state, not the hard edge. (INFERRED.)
- **Page faults become GIL and CPU stalls.** Python does not page-fault in a way vfs can see. Its implicit blocking is CPU on the loop thread and work that holds the GIL. (INFERRED.)
- **No per-CPU anything.** The approximate counter shards by CPU. vfs shards by row: one version per entry, one bump per parent. The database already runs different rows in parallel, so the row is the natural local counter. (INFERRED.)

---

## 5. The one design lesson

Inside one vfs call, every check sits inside the write that depends on it, and that is why vfs's concurrency is correct today. Across two calls nothing guards the gap, so an agent's read-modify-write and the shell's `>>` lose a rival's update and report success; the book's oldest lesson, a read then a write is a critical section, says the kernel's `write` must accept the version it is replacing. The smaller lessons follow the same line: take row locks in one sorted order on the hot write path as the cold paths already do, score each lock on fairness as well as correctness and cost, and keep removing shared counters the way ADR 013 already started.

One-line version: guard the gap between calls, not only the inside of each call.
