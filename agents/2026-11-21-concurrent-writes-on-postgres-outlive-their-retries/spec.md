# Concurrent writes on Postgres outlive their retries

A draft, written on 2026-11-21 from the study `agents/2026-11-21-what-a-log-row-per-call-costs/`, read against `dev` at `9240a9d`. It is not reviewed, and nothing is built. Its first step is to find which row 32 concurrent one-file writes contend on, because none of them names a path another names.

## The outcome wanted

32 sessions writing one new file each, each into a directory of its own, are all served on Postgres. Today about one write in seventy is refused `vfs.conflict` with no log and no other load. A conflict between writes that name no common path is either removed, or is the declared and documented cost of a row the design chose to share, with its retry budget sized for the reference deployment's 20 calls a second at peak.

## Builds on

- The study's `results/calls-postgres.json`, measured with `scripts/measure_calls.py` on PostgreSQL 19.0 with pgvector 0.8.7, one local container, 4 cores.
- The reference deployment in `AGENTS.md`: about 20 verb calls a second at peak, one write in four, and a 10,000-file batch as a supported contract.

## The problem

Each fact is marked run or read.

- **One-file writes conflict.** 32 sessions, each writing new 4 KB files one after another into `/agents/<run>/s<NN>/`, a directory per session, with no log: 13 of 960 counted writes over five repeats were refused `vfs.conflict`. With the study's two log modes the counts were 10 and 14, so the log is not the cause. A single session saw none. Run.
- **SQLite serves the same load with no refusal.** The same calls on SQLite, whose single writer serializes them, refused none of 960. Run.
- **The refusal outlived four attempts.** The message is `write kept losing to concurrent changes: a retryable engine conflict outlived 4 attempts`, raised by the host's retry loop in `engine.py`. Read.
- **An op runs under `REPEATABLE READ` on Postgres.** The Postgres profile pins `op_isolation="REPEATABLE READ"`, under which two transactions that update one row fail the later one with a serialization error. Which shared row the writes update (a directory aggregate, a mount row, a statistics row) is not known. Read, then not checked.
- **32 batches at once mostly fail.** 32 sessions each writing 10,000 entries at once: 54 of 64 batches over two repeats were refused, either `vfs.conflict` as above or `vfs.unavailable` because the default pool of 5 and 10 overflow timed out a checkout after 30 s. Run.

## Decisions to make

1. **Which row the writes share,** found by logging the serialization failures' relation on the Postgres leg, before any change.
2. **Whether that row is shared by design.** If it is a directory aggregate, the reference deployment already budgets about 30 updates a second on a hot row, and the aggregate's write may be coalesced or moved after the commit. If it is not by design, the contention is removed.
3. **Whether four attempts are enough** once the contention is known, and whether the backoff spreads rivals far enough at 32 sessions.
4. **Whether a storage should size its pool for its concurrency,** or say in its docstring that 32 concurrent batches need `engine_arguments` with a pool of 32.

## Tests

A counted test on the Postgres leg: 32 concurrent one-file writes into 32 directories are all served, and the number of retried attempts is pinned. No test asserts on seconds.

## Scope

In: the contention behind concurrent one-file writes on Postgres, the retry budget, and the pool sentence. Out: SQLite's single writer, which `agents/2026-11-21-a-write-beside-a-batch-on-sqlite-is-refused-after-twenty-seconds/spec.md` covers; the action log.

## Not checked

- Whether the refusals happen on Postgres 15 to 18, or on a server with more cores.
- Whether writes into one shared directory conflict more often than writes into a directory each.

## One line

On Postgres, 32 sessions writing new files into directories of their own lose about one write in seventy to a serialization conflict that outlives four retries, and the row they contend on is not yet known.
