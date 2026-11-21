# What a log row per call costs

A draft, written on 2026-11-21 from story L0 of `context/standards/roadmap.md`, read against `dev` at `ffaede80`. It is not reviewed, and nothing is run. It is a study: it lands a memo and its scripts in this directory, and nothing under `src/` or `tests/`.

## The outcome wanted

Before the action log is specified, one question has a measured answer: what does one log row per call cost an agent-sized call and a 10,000-entry batch, on SQLite and on Postgres, and which way of writing the row keeps that cost inside the bar. The answer is a memo that ends in GO or NO-GO.

## Builds on

- Story L0 of `context/standards/roadmap.md`, which this spec carries out, and story H0, the action log, which waits on its answer.
- The reference deployment in `AGENTS.md`: about 150,000 verb calls a day, about 20 a second at peak, three reads for each write, and the four rules for a lock.
- `context/specifications/active/177-replay-the-contract-and-the-request-key/spec.md`, for the claim-first shape an effect row takes.

## The problem

No table records a call. The time a call took is stored nowhere. `import logging` appears in two modules, `src/vfs/authority.py` and `src/vfs/storage/backends/database/engine.py`, and neither records a call.

The action log is a must for 0.1.0, so the question is not whether to log but how. The multiplier is the verb call: one row per call is about 150,000 inserts a day, and three in four of those calls are reads.

Two costs are not known.

- **Statements and time.** What a row adds to a `read` that issues a handful of statements, and to a 10,000-entry `write` that issues tens.
- **Waiting.** SQLite has one writer. A row written inside a read makes that read a writer, and it then queues behind every write and every batch. The reference deployment refuses any design in which a read waits on a writer.

Story H0 leans on a design that has not been measured: an effect row is claimed before the effect and completed after it, in two synchronous statements, and a read row goes to a bounded buffer that is flushed every 256 rows. This study measures that design against the two simpler ones.

## Decisions

1. **Three ways of writing the row are measured.** No log at all; one synchronous row per call; and the leaned design, in which reads are written behind from a buffer and effects are claimed and completed synchronously.
2. **Four calls are measured:** one `read`, one `grep`, one `write` and one `write` of 10,000 entries. Each is run under 1 session and under 32 concurrent sessions, on SQLite and on Postgres.
3. **Each run records three things.** Statements issued per call, counted with SQLAlchemy's `before_cursor_execute` event. Wall time per call, as a median and a 95th percentile, with the spread between repeated runs. And how long a `read` waits while a 10,000-entry `write` is in flight.
4. **The log is built outside `src/`.** The scripts wrap the public verbs, and the wrapper writes each row to a table of its own in the same database. The row holds the columns story H0 names (the call's id, its run and parent, its start, its elapsed nanoseconds, the actor, the verb, the first 16 paths and their count, rows, statements, bytes, the outcome and the mount), so the row is as wide as the real one.
5. **The buffer is flushed on a connection of its own.** A flush is one insert of 256 rows. The study counts its statements and its bind parameters against each dialect's budget, and measures how long it waits behind a batch on SQLite and what the buffer holds meanwhile.
6. **The bar is stated in statements.** Written behind, a read adds zero synchronous statements. An effect adds exactly two. The memo states the measured cost against that bar and says GO or NO-GO. On NO-GO it names the shape it recommends in its place.
7. **Growth and reclaim are measured too,** because the log's retention rests on them. Bytes per row on each engine, and from that the table's size after one day and after 30 days at 150,000 rows a day. And the cost of deleting one day of rows in chunks: its statements, and whether a read waits while it runs.
8. **Wall time stays in the memo.** A clock measures the machine. Nothing this study times becomes a test, and the acceptance of story H0 counts statements only.

## Tests

None land in `tests/`. The study is checked in three ways. Each script runs from one command under `uv run` and carries its own deadline. The memo records the commit, the engine versions and the machine. And every figure in the memo names the script and the run that produced it.

The Postgres runs use a local container, started and torn down as `.claude/skills/db_test/SKILL.md` says, and reached through `VFS_TEST_POSTGRES_URL`.

## Scope

In: the scripts, their results and the memo `research.md`, all in this directory.

Out: any change under `src/` or `tests/`; the spec of the action log; the read side, `calls`; the durable run.

## Not checked

- Nothing is measured yet. Every number in the memo is new.
- Whether 32 concurrent sessions on Postgres need a connection pool larger than the default.
- What changes when the log lives in a different storage from the mount a call writes to. Story H0 puts the log in the root binding's storage, so a write to another mount pays for a second connection. The study measures one storage and says so.

## Choices to confirm

1. **What overhead in wall time is a GO?** The bar is in statements, and no bar exists for time. Recommended: GO when the statement bar is met and a read's median under 32 sessions moves by less than the spread between repeated runs.
2. **Is the buffer one per router or one per session?** Recommended: one per router, with one flusher, because a session is short and a buffer per session would flush mostly at `close()`. The study measures that shape and notes the other.
3. **Which Postgres version?** Recommended: 19, the version the local engine leg runs.

## One line

A study on both engines measures three ways of writing one log row per call, in statements, in time and in how long a read waits, and ends in a GO or a NO-GO that the action log's spec is then written from.
