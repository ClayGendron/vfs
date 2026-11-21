# What a log row per call costs

A study, run on 2026-11-21 against `dev` at `9240a9d` with nothing under `src/` changed, carrying out story L0 of `context/standards/roadmap.md` as `spec.md` in this directory specifies it. Every figure below comes from a script in `scripts/` and a result file in `results/`, and is named beside the table it sits in. `results/tables.md` holds every table the scripts produced, rendered by `scripts/report.py`. Sources: SQLite 3.53.1 through aiosqlite 0.22.1; PostgreSQL 19.0 with pgvector 0.8.7 in the `docker/compose.test.yml` container; Python 3.13.18; one machine of 4 cores of an Intel Xeon at 2.30 GHz and 15.7 GB, with the server, the client and the scripts on it together.

## The answer

**GO for the leaned design, with one change on SQLite: the log lives in a database file of its own, not in the mount's file.**

- **The statement bar is met on both engines.** Written behind, a read adds zero synchronous statements. An effect adds exactly two: the claim and the completion. This held on every one of the 11,340 counted agent-sized calls per engine, and on every batch that was served.
- **A read does not move.** Under 32 sessions, a `read`'s median moved by 15 ms on SQLite and 4 ms on Postgres, against a spread between repeated runs of 80 ms and 26 ms. That is inside the spread, which is the bar the spec recommends.
- **A read never waits on a writer.** While a 10,000-entry write ran, reads under the leaned design took what they took with no log at all, on both engines.
- **On SQLite the log cannot share the mount's file.** There the flush and the claims queue behind the batch for SQLite's one writer: 12 of 19 flushes failed after the 5-second lock timeout, the buffer grew to 2,360 rows, and claims timed out and refused effects. With the log in a file of its own beside the mount's, no flush failed, the slowest took 0.58 s, and the buffer never held more than 257 rows.

**NO-GO for one synchronous row per call.** On SQLite it turns every read into a writer: during a batch a read's median went from 70 ms to 856 ms, its 95th percentile to 5.1 s, and rows were lost when the lock timeout ran out. On Postgres it costs a round trip every read pays: under 32 sessions a `read`'s median moved from 52 ms to 149 ms, almost three times the spread.

In one line: write reads behind and claim effects, and on SQLite give the log a file of its own.

## The question

Story H0 makes every call vfs makes a row: who, what, how many rows, how long. That is about 150,000 rows a day at the reference deployment, three in four of them from reads. Two costs were not known. The first is statements and time: what a row adds to a `read` of four statements and to a 10,000-entry `write` of about sixty. The second is waiting: SQLite has one writer, and a row written inside a read makes that read a writer, so the read would queue behind every write and every batch. The reference deployment refuses any design in which a read waits on a writer.

H0 leans on a design no one had measured. An effect's row is claimed before the effect and completed after it, in two synchronous statements. A read's row goes to a bounded buffer that is flushed every 256 rows. This study measured that design against two simpler ones: no log, and one synchronous row per call.

## How it was measured

Everything was run from the scripts in `scripts/`, through the public verbs only. `scripts/run_all.sh` runs them in order, each under its own deadline.

- **The database.** Every run opens a fresh database: a new SQLite file, or a new Postgres schema. One `SQLiteStorage` or `PostgresStorage` is mounted at `/`. The log is a table of its own, `l0_call_log`, in the same database (on SQLite, the same file, unless the run says otherwise), reached through a second SQLAlchemy engine on the same URL with the same pool defaults. The storage's own engine is touched only to put a listener on it, which its docstring allows.
- **The row.** Fifteen columns: the call's id, its run and parent, its start, its elapsed nanoseconds, the actor, the verb, the first 16 paths as JSON and their count, rows, statements, bytes, the outcome, the mount, and a status (`running` or `done`). Beside the primary key are two indexes: `started_at`, which retention reads, and `run_id`, which a resume reads. So the row is as wide as the one story H0 names.
- **The three modes.**
  - *none*: the verb is called and nothing is written.
  - *sync*: every call, read or effect, inserts one complete row after the verb returns, in a transaction of its own, before the call returns.
  - *leaned*: a read appends its row to an in-process buffer. One flusher task writes 256 rows as one multi-row insert, on a connection of its own, whenever 256 are waiting, and the rest at close; a failed flush puts its rows back and tries again. An effect inserts a `running` row before the verb is entered (the claim) and updates it to `done` with its outcome after (the completion). A claim that cannot be written refuses the effect.
- **The calls.** The corpus is 2,000 files of about 4 KB, the reference deployment's median, in 100 directories. `read` reads one file. `grep` looks for `MFA` under one directory of 20 files, five of which match. The corpus is not indexed, so grep runs its scan tier. `write` writes one new 4 KB file. The batch writes 10,000 new 4 KB files in 100 directories in one call.
- **Sessions.** Under 1, one session issues 60 calls back to back. Under 32, 32 sessions of 32 different principals issue 6 calls each at once, in one process and one event loop, through one router. Each session's first three calls are a warm-up and are not counted.
- **Statements.** SQLAlchemy's `before_cursor_execute` event, on both engines, attributed to the call through a context variable, so a count is the call's own under any concurrency. A `COMMIT` is not a cursor statement on either driver and is not counted; vfs's own explicit `BEGIN` on SQLite is. The flusher runs in a context of its own, so its statements are never a call's.
- **Time.** `time.perf_counter` around each call, with the log write included. Each configuration reports three figures: the median of the repeats' medians; the spread, which is the largest repeat median less the smallest; and the median of the repeats' 95th percentiles.
- **Repeats.** Five for the agent-sized calls and the single batch. Two for 32 batches at once, because each leaves 320,000 files. The modes rotate their order each repeat.
- **Waiting.** Eight reader sessions issue `read` back to back, and one more session issues one-file `write` calls. They run first in a quiet two-second window and then while a tenth session writes 10,000 entries. A call counts as *during* the batch when its interval overlaps the batch's. Each mode is repeated three times.
- **Growth.** The table is filled with 30 days of 150,000 rows each, shaped like the reference deployment's mix: three reads, lists, globs and greps for each write or edit, and search at 4%. The many-path verbs carry 1 to 40 paths, of which 16 are kept, and 30% of calls are in a run. Sizes come from the engine's own page accounting: `dbstat` on SQLite, and `pg_relation_size` and `pg_indexes_size` on Postgres.
- **Reclaim.** The oldest day is deleted in chunks of 5,000 by one statement shape that never grows: `DELETE … WHERE call_id IN (SELECT call_id … WHERE started_at < :cutoff ORDER BY started_at LIMIT :n)`. Readers, a one-file writer and a probe that inserts one log row every 50 ms run beside it.

## Statements per call

From `results/calls-sqlite.json` and `results/calls-postgres.json` (`scripts/measure_calls.py`). The first column is what the verb itself issued; the next three are what the log added, synchronously, inside the call.

| call | SQLite: the verb | Postgres: the verb | added, none | added, sync | added, leaned |
|---|---|---|---|---|---|
| `read` | 4 | 4 | 0 | 1 | **0** |
| `grep` | 14 | 14 | 0 | 1 | **0** |
| one-file `write` | 21 | 17 | 0 | 1 | **2** |
| 10,000-entry `write` | 74 | 57 | 0 | 1 | **2** |

The counts are the same under 1 session and under 32, for every call that was served. A 10,000-entry write is still one row with `rows = 10000`; its first 16 paths are kept and its count is 10,000.

The flush is one statement of 256 rows × 15 columns = 3,840 bind parameters on both engines. That is 12% of the tightest budget in play: SQLAlchemy's 32,700, asyncpg's 32,767 and SQLite's 32,766. At 15 columns a flush could hold 2,180 rows before it needed a second statement, so `LOG_FLUSH_ROWS = 256` never chunks.

## Wall time per call

From the same files. Milliseconds: the median of five repeats' medians, the spread between them in brackets, and the change against no log. The single-session batch is in seconds.

| call | SQLite none | SQLite sync | SQLite leaned | Postgres none | Postgres sync | Postgres leaned |
|---|---|---|---|---|---|---|
| `read` × 1 | 3.9 (1.5) | 5.6, +1.7 | 5.1, +1.2 | 2.7 (0.8) | 4.1, +1.4 | 2.8, +0.1 |
| `read` × 32 | 245 (72) | 286, +42 | 259, **+15** | 52 (33) | 149, **+97** | 57, **+4** |
| `grep` × 1 | 18.9 (7.7) | 20.8, +1.9 | 17.5, −1.4 | 18.0 (4.9) | 18.9, +0.8 | 16.6, −1.4 |
| `grep` × 32 | 3,890 (368) | 3,747, −143 | 3,904, +14 | 348 (101) | 421, +74 | 361, +14 |
| `write` × 1 | 17.3 (3.0) | 20.1, +2.9 | 18.7, +1.4 | 16.3 (3.1) | 17.2, +0.8 | 16.4, +0.0 |
| `write` × 32 | 321 (57) | 263, −58 | 162, −158 | 188 (72) | 237, +49 | 338, **+151** |
| 10,000-entry `write` × 1 | 6.1 s (0.6) | 5.9 s | 6.0 s | 7.6 s (1.6) | 7.7 s | 7.6 s |

What the table says:

- **Alone, every mode is within a couple of milliseconds**, about the spread itself. A row costs a round trip and an insert, and on a 4 ms read that round trip is about 1.5 ms.
- **Under 32 sessions, the synchronous row is the expensive one on Postgres.** Every read waits for its own insert, and 32 sessions share one log pool of 15 connections. The leaned design moves a read by 4 ms against a spread of 33 ms.
- **The leaned effect costs time on Postgres under 32 sessions:** +151 ms on a one-file write of 188 ms, a little over its spread of 136 ms. Two log transactions per write, from 32 sessions through a pool of 15, queue for connections. The statement bar holds; the time is the pool's. On SQLite the same cell moved the other way, because there all writes queue for the one writer anyway.
- **The batch does not notice its two log statements** on either engine.
- **32 batches at once are not served by vfs on either engine, with or without a log.** On SQLite 16 of 64 were served with no log, 16 with sync and 12 leaned. On Postgres the figures were 10, 11 and 12. The refusals are `vfs.conflict` after four attempts and, on Postgres, a pool checkout that timed out after 30 s. The log changes nothing there that matters, and both engines' figures are findings about vfs, written as specs (below).

## Waiting while a batch runs

From `results/waits-sqlite.json` and `results/waits-postgres.json` (`scripts/measure_waits.py`). Eight readers and one one-file writer, quiet and then during a 10,000-entry write; medians over three repeats, in milliseconds.

| engine and mode | batch | read median, quiet → during | read p95, quiet → during | one-file writes refused | log writes failed | flushes failed / run | slowest flush | buffer high water |
|---|---|---|---|---|---|---|---|---|
| SQLite none | 28.3 s | 84 → 72 | 99 → 152 | 3 | — | — | — | — |
| SQLite sync | 5.7 s | 70 → **856** | 645 → **5,109** | 0 | 2 rows lost | — | — | — |
| SQLite leaned | 28.8 s | 79 → 76 | 95 → 200 | 9 | 10 | **12 / 19** | **5.3 s** | **2,360** |
| SQLite leaned, log in its own file | 26.6 s | 81 → 82 | 97 → 231 | 3 | 0 | 0 / 24 | 0.58 s | 257 |
| Postgres none | 7.8 s | 17 → 33 | 35 → 543 | 0 | — | — | — | — |
| Postgres sync | 8.2 s | 26 → 53 | 47 → 625 | 0 | 0 | — | — | — |
| Postgres leaned | 8.5 s | 17 → 35 | 44 → 521 | 0 | 0 | 0 / 6 | 0.43 s | 258 |

What the table says, engine by engine.

**SQLite, one synchronous row per call.** Every read becomes a writer for one insert. It then waits behind the batch for SQLite's one writer, for as long as the batch holds it or until the 5-second `busy_timeout` runs out. The read's median went from 70 ms to 856 ms and its 95th percentile to 5.1 s, and two rows were lost to `database is locked`. This is the shape the reference deployment refuses. The batch finished faster here (5.7 s against 28 s) only because the readers were stuck waiting and stopped competing for the process.

**SQLite, leaned, log in the mount's file.** Reads did not wait: their median stayed at 76 ms, because a read's row went to the buffer. But everything the log writes went to the same one writer the batch holds:

- **Flushes failed.** 12 of 19 flushes waited the full 5 s and failed. Their rows were kept and put back, so no row was lost, but the buffer grew to 2,360 rows against a capacity of 4,096. Eight readers at about 100 reads a second fill a buffer at that rate for as long as a batch holds the writer, so a busier host or a longer batch overflows it.
- **Claims failed.** Effect claims failed after 5 s and refused their writes. Nine one-file writes were refused, against three with no log, because a claim waits one `busy_timeout` where vfs's own write waits four.
- **One completion failed.** That effect was served, but its row stayed `running`. A resume that read it would call the step in doubt, though it had finished. Story H4 counts a `running` row as a crash, and here a lock produced one.

**SQLite, leaned, log in a file of its own.** The log has a writer of its own, so nothing it writes waits on the batch. No flush failed and the slowest took 0.58 s. The buffer never held more than 257 rows. One-file writes were refused as often as with no log, three, because that refusal is vfs's own and not the log's.

**Postgres.** Rows lock, the database does not, so no mode made anything wait on the batch's locks. Reads slowed during the batch in every mode equally, from about 17 ms to 34 ms at the median and to about 0.5 s at the 95th percentile, with no log too. That is the one process busy with the batch, not a lock. About 0.4 s of each stall is the study's own harness building the 10,000 entries on the same event loop (measured at 387 to 402 ms); the rest is not attributed. Every flush succeeded, the slowest in 0.43 s.

## Growth and reclaim

From `results/growth-sqlite.json` and `results/growth-postgres.json` (`scripts/measure_growth.py`). The table holds the 15 columns and both indexes.

| | SQLite | Postgres |
|---|---|---|
| bytes per row, heap and indexes | 572 | ⟨pg_bpr⟩ |
| after 1 day, 150,000 rows | 82 MB (68 heap, 14 index) | ⟨pg_1⟩ |
| after 30 days, 4,500,000 rows | 2.4 GB (2.0 heap, 0.4 index) | ⟨pg_30⟩ |
| one day reclaimed in chunks of 5,000 | 31 statements, 1.2 s; a chunk 21 ms median, 202 ms max | ⟨pg_reclaim⟩ |
| what the delete freed | 81 MB to the file's free list; the next day's rows reused it and the file grew by 0.4 MB | ⟨pg_free⟩ |

Bytes per row did not move between one day and thirty (570.6 and 571.6 on SQLite), so the size is linear in rows, and a 30-day retention holds the table at about 30 days of rows. At the reference deployment that is about 2.4 GB on SQLite and ⟨pg_30_short⟩ on Postgres. Both are small beside the corpus itself, which holds 3 to 7 TB of bodies.

The reclaim is cheap and waits on nothing that matters:

| probe, during the delete | SQLite median, max | Postgres median, max |
|---|---|---|
| `read` (leaned) | 67 ms, 112 ms (quiet 69, 147) | ⟨pg_read⟩ |
| one-file `write` (leaned) | 242 ms, 320 ms (quiet 176, 320) | ⟨pg_write⟩ |
| one log row, inserted alone | 41 ms, 983 ms (quiet 112, 185) | ⟨pg_row⟩ |

On SQLite a chunk holds the writer for about 20 ms and at most about 200 ms, so a log row inserted beside it waited up to a second once. A read did not wait at all. That is the same reason as above for a log file of its own on SQLite: the reclaim, the flush and the claims then share a writer only with each other.

## The pool

From `results/pool-sqlite.json` and `results/pool-postgres.json` (`scripts/measure_pool.py`): 32 sessions of five calls each, three times, with no log, on the default pool of 5 and 10 overflow and on a pool of 32.

| | SQLite default | SQLite 32 | Postgres default | Postgres 32 |
|---|---|---|---|---|
| `read` median, ms | 167 to 270 | 210 to 228 | ⟨pgpool_rd⟩ | ⟨pgpool_r32⟩ |
| `grep`, calls a second | 8.4 to 9.0 | 8.7 to 9.7 | ⟨pgpool_gd⟩ | ⟨pgpool_g32⟩ |

For agent-sized reads the default pool is enough on both engines: a pool of 32 moved nothing beyond the spread. It is not enough for 32 concurrent batches on Postgres, where batches waited 30 s for a connection and were refused. The log's own engine is a second pool of the same size, and under 32 writing sessions it is where the leaned effect's +151 ms on Postgres queued.

## What H0 inherits

The bar, as measured:

1. **Written behind, a read adds zero synchronous statements.** Held on both engines for `read` and `grep`, at 1 and at 32 sessions.
2. **An effect adds exactly two:** the claim before, the completion after. Held for a one-file `write` and a 10,000-entry `write` on both engines.
3. **A flush is one statement of 256 rows**, 3,840 bind parameters, 12% of the tightest budget. It never chunks at 15 columns.

The shape the measurements recommend, beyond the bar:

- **On SQLite the log is a database file of its own**, beside the mount's file, with its own writer. Story H0 puts the log in the root binding's storage. On SQLite that storage's file is the one a batch holds, so the root binding's log needs a file of its own there (an `ATTACH`ed database or a second file). On Postgres the root binding's schema is fine as it is.
- **A claim waits as long as the effect would.** A claim that gives up after one `busy_timeout` refuses effects vfs itself would have served. Its wait and its retries should be the effect's own.
- **A completion that cannot be written is retried, not dropped.** Otherwise a finished effect leaves a `running` row, and a resume calls it in doubt. With the log in its own file on SQLite this did not happen, but the rule should not rest on that.
- **The buffer is one per router, with one flusher,** as the spec's second choice recommends. With the log in its own file the buffer held at most 258 rows on both engines, one flush's worth. A per-session buffer was not measured.
- **The log's connections are sized for the effects, not the reads.** Under 32 writing sessions on Postgres, two log transactions per effect queued on a pool of 15 and cost +151 ms a write. Whether the claim and the completion can ride the effect's own connection, or the completion can join the effect's own transaction for vfs's own verbs, is H0's to decide. Neither was measured.

## Findings about vfs, written as specs

These are not the log's costs, but the study met them, and each is a spec of its own:

- `agents/2026-11-21-a-write-beside-a-batch-on-sqlite-is-refused-after-twenty-seconds/spec.md`: on SQLite a one-file write that arrives during a batch waits four 5-second lock timeouts and is then refused `vfs.conflict`; 32 batches at once lose three in four.
- `agents/2026-11-21-concurrent-writes-on-postgres-outlive-their-retries/spec.md`: on Postgres about one in seventy concurrent one-file writes into directories of their own is refused `vfs.conflict`; 32 batches at once lose most to conflicts and to a 30-second pool checkout.
- `agents/2026-11-21-a-grep-under-many-sessions-on-sqlite-serves-fewer-calls-than-one-session/spec.md`: on SQLite 32 sessions of `grep` serve about 9 calls a second, where one session alone serves about 50 and Postgres under 32 sessions about ⟨pg_grep_rate⟩.

## Not checked

- **A log in another storage than the mount a call writes to.** Story H0 puts the log in the root binding's storage, so a write to another mount pays for a second connection. This study measured one storage. The SQLite log in a file of its own is the nearest measurement of that shape.
- **A buffer per session.** Only one per router was measured.
- **A crash.** Each write discipline's loss on a crash (at most one buffer of read rows, no effect row) was not exercised, only argued.
- **Another machine.** The server, the client and the scripts shared four cores, so every wall time includes their contention. The ratios are the finding, not the milliseconds.
- **Postgres 15 to 18.** Only 19 was run.
- **An indexed corpus.** `grep` ran its scan tier over unindexed rows; an indexed grep issues a different number of statements, but the log adds the same.
- **Where the rest of the read stall during a batch comes from.** About 0.4 s of the 0.7 to 1.2 s maximum is the harness building 10,000 entries on the same event loop. The rest is not attributed to vfs or to the harness.
- **The 30-day figures are measured, not projected.** But one month's rows were bulk-loaded, not written by 150,000 calls a day, so their pages are packed tighter than a table grown by flushes may be.

## One line

One log row per call is affordable when reads are written behind and effects are claimed and completed, which adds zero statements to a read and two to an effect on both engines and leaves every read where it was; it is a GO, provided SQLite's log has a file of its own, and one synchronous row per call is a NO-GO.
