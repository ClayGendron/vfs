# A grep under many sessions on SQLite serves fewer calls than one session

A draft, written on 2026-11-21 from the study `agents/2026-11-21-what-a-log-row-per-call-costs/`, read against `dev` at `9240a9d`. It is not reviewed, and nothing is built. Its first step is to find where the time goes, because the same calls in a line are served five times faster.

## The outcome wanted

On SQLite, 32 sessions issuing `grep` at once in one process are served at least as many calls a second as one session issuing the same greps back to back. Today they are served about one fifth as many. Either the cause is removed, or the docs say what a SQLite mount serves under concurrency and why.

## Builds on

- The study's `results/pool-sqlite.json`, `results/pool-postgres.json` and `results/calls-sqlite.json`, measured with `scripts/measure_pool.py` and `scripts/measure_calls.py` on SQLite 3.53.1 and PostgreSQL 19.0, on one machine of 4 cores.
- The reference deployment in `AGENTS.md`: about 20 verb calls a second at peak, with greps among the three reads in four. SQLite serves demos and local applications, where a handful of agents on one host is the ordinary case.

## The problem

Each fact is marked run or read.

- **One session: about 50 greps a second.** A `grep` for `MFA` under one directory of 20 files of about 4 KB, in a corpus of 2,000 files that is not indexed, took a median of 18.9 ms from one session. Run.
- **32 sessions: about 9 greps a second.** The same grep from 32 sessions at once took a median of 3.5 to 4.0 s, and the window served 8.4 to 9.7 calls a second over six runs. Run.
- **The pool is not the cause.** A pool of 32 connections with no overflow served 8.7 to 9.7 calls a second, the same as the default 5 and 10. Run.
- **Postgres is not slowed the same way.** The same 32 sessions on Postgres served ⟨pg_grep_rate⟩ greps a second. Run.
- **`read` is not slowed the same way.** 32 sessions of `read` on SQLite served 115 to 174 calls a second, where one session serves about 250. Run.
- **The machine was not idle.** During the SQLite runs the process used about 180% of a CPU with about a third of it in system time, which points at threads contending, not at a busy disk. Run once, by `top`, and not recorded in a result file.
- **What grep runs over an unindexed corpus.** The scan tier fetches the scoped rows' bodies and verifies them on the process's offload pool, a `ThreadPoolExecutor` of `OFFLOAD_WORKERS`; each SQLite connection is an aiosqlite thread of its own. Read.

## Decisions to make

1. **Where the time goes**, found with a profile of the 32-session run on SQLite: the aiosqlite threads, the offload pool, the GIL between them, or a lock in the storage.
2. **Whether the indexed path is slowed the same way.** The study's corpus was never rebuilt; an indexed grep fetches far fewer bodies.
3. **What the fix is**, once the cause is known: fewer threads in contention, a statement shape that fetches less, or a documented limit on SQLite's concurrency, which `AGENTS.md` does not allow as a designed cap.

## Tests

A counted test on the SQLite leg, once the cause is known: the statements, rows fetched or hops of 32 concurrent greps are no more than 32 times one grep's. No test asserts on seconds or calls a second.

## Scope

In: `grep` under concurrency on SQLite, indexed and not. Out: Postgres; the action log, which the study above covers.

## Not checked

- Whether `glob` and `search` slow the same way under 32 sessions on SQLite.
- Whether more cores change the ratio.

## One line

On SQLite, 32 sessions of `grep` in one process are served about 9 calls a second where one session alone is served about 50, the pool is not the cause, and the cause is not yet known.
