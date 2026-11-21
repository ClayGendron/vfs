# An old index epoch is dropped as a table

A draft, written on 2026-11-21 from candidate 4 of `agents/2026-11-20-vfs-serves-sqlite-and-postgres-only/research.md`, which the memo marks "spec first, large". It is not reviewed, and nothing is built.

## The outcome wanted

The daily rebuild reclaims the epoch it replaced by dropping a table, not by deleting its rows, and no reader of the live epoch waits on the reclaim.

## Builds on

The memo's experiment X3, and the 2026-10-31 memo in `context/research/` that measured repeated rebuilds on SQLite.

## The problem

`reclaim_epochs` deletes every old-epoch row of every epoch-scoped table in one transaction: the gram postings, `lex_docs`, `lex_postings`, `lex_df`, `lex_stats` and the fingerprints. At the reference deployment's daily rebuild that is about 200,000,000 deleted rows a day, with their write-ahead log and vacuum. On SQLite, seven rebuilds slowed the lexical build from 3.6 s to 30.2 s.

## Decisions

1. **Each epoch writes its own tables,** and the reclaim drops them once the live pointer has moved past them.
2. **Each read resolves its table names from the live epoch** it reads at its start.
3. **On Postgres, a list partition per epoch is the alternative,** reclaimed by `DETACH … CONCURRENTLY` and `DROP`. Which of the two is a choice below.

## Cost

Per corpus, once a day: the deletes become a drop of a few hundred kilobytes of catalog. Per lock: a drop takes an exclusive lock on a table no reader of the live epoch reads, so no reader waits. Risk: DDL moves into the rebuild's lifecycle, medium to large.

## Tests

A test on each engine that a reader of the live epoch never waits on a reclaim, counted as reads that return while the drop's transaction is open. A counted test of the statements a reclaim sends.

## Scope

In: the epoch-scoped tables, `indexing.py`'s reclaim, and how a read names its tables. Out: the build itself.

## Not checked

- Whether asyncpg's `copy_records_to_table` can pass `FREEZE` for a build into a table created in the same transaction.

## Choices to confirm

1. **A table per epoch, or a partition per epoch on Postgres?** Recommended: a table per epoch, since it is one shape on both engines.

## One line

The rebuild drops the epoch it replaced as a table, so a day's reclaim costs a drop and not 200,000,000 deletes, and no reader waits on it.
