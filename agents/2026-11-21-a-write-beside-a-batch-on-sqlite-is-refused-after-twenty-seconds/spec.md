# A write beside a batch on SQLite is refused after twenty seconds

A draft, written on 2026-11-21 from the study `agents/2026-11-21-what-a-log-row-per-call-costs/`, read against `dev` at `9240a9d`. It is not reviewed, and nothing is built. Its first step is to decide what SQLite owes a one-file write that arrives while a 10,000-entry write is running.

## The outcome wanted

A stated and tested answer for one case on SQLite: an agent's one-file `write` arrives while an ETL batch of 10,000 entries is running in the same process. Today it waits up to about 20 seconds and is then refused `vfs.conflict`. Either that is the contract, and the docs and the classified error say so, or the write is served after the batch and the contract says how long it may wait.

## Builds on

- The study's `results/waits-sqlite.json` and `results/calls-sqlite.json`, measured with `scripts/measure_waits.py` and `scripts/measure_calls.py` on SQLite 3.53.1.
- The reference deployment in `AGENTS.md`, which puts SQLite in demos and local applications and lists a 10,000-file batch as a supported contract.

## The problem

Each fact is marked run or read.

- **A one-file write beside a batch waits about 20 s and can be refused.** With no log at all, a session writing one 4 KB file at a time beside a 10,000-entry write saw a maximum of 20.5 s, 20.6 s and 20.8 s in three repeats, and in each repeat one write was refused `vfs.conflict: write kept losing to concurrent changes: a retryable engine conflict outlived 4 attempts`. Run.
- **Twenty seconds is four attempts of the 5 s `busy_timeout`.** The SQLite profile sets `PRAGMA busy_timeout = 5000`, and the host's retry loop in `engine.py` gives a write four attempts before it raises `StaleSnapshot` with that message. Read.
- **The batch holds the writer for long stretches.** The same batch took 5.7 to 6.3 s alone and about 28 s beside eight reader sessions in one process. The one-file writer completed four to six writes in that window, so the batch does not hold the writer throughout; how long it holds it at a stretch is inferred from the 20 s waits, not measured. Run, then inferred.
- **32 batches at once lose three in four.** With 32 sessions each writing 10,000 entries at once, 48 of 64 batches over two repeats were refused with the same `vfs.conflict`, with no log. Run.
- **Reads do not wait.** WAL serves readers beside the writer, and read latency during the batch was unchanged. Run.

## Decisions to make

1. **What a write beside a batch is owed on SQLite**: a bounded wait and then a classified refusal that says a batch held the writer, or a wait that lasts until the writer is free.
2. **Whether `vfs.conflict` is the right kind.** A lock held by a rival is not a conflict over the same rows; the refusal may belong under `unavailable` with a retry class.
3. **Whether the batch should yield the writer between chunks**, so a one-file write lands between them. This changes a batch's atomicity, so it is a decision, not a fix.

## Tests

A counted test on the SQLite leg: a one-file write started while a batch holds the writer either lands or is refused with the declared kind, and the number of attempts it made is the declared number. No test asserts on seconds.

## Scope

In: SQLite's answer to a write beside a batch, its error kind, and the docs sentence. Out: Postgres, where rows lock, not the database; the action log, which the study above covers.

## Not checked

- Whether a batch in another process holds the writer as long as one in the same process.
- Whether the four attempts are the right number on SQLite, or were set for Postgres's serialization failures.

## One line

On SQLite a one-file write that arrives during a 10,000-entry write waits four 5-second lock timeouts and is then refused as a conflict, and the contract should say whether that is what it is owed.
