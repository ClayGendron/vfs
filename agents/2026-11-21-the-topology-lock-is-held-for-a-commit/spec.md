# The topology lock is held for a commit

A draft, written on 2026-11-21 from two defects that the inventory of the drop found by reading. It is not reviewed, and nothing is built.

## The outcome wanted

A delete, restore, sweep, move or copy holds the topology lock only for the length of its commit, as the working agreement's rule on locks requires, and a relabel writes only the rows whose level changes.

## The problem

### A topology verb holds the lock for its whole batch

Read. `serialize()` takes the lock row as the verb's first statement. A 10,000-target delete therefore stalls every other delete, restore, sweep, move and copy on the mount for the length of the batch. The working agreement says a lock other callers need is held for the length of a commit, never for a batch's body, and that a lock taken as a transaction's first statement is held for everything after it.

### A relabel rewrites rows whose level is already right

Read. `relabel_spans` has no `everyone_level <> :rank` term, so a relabel writes every row in its region, those already at the new level among them. Each write costs a row version on Postgres.

## Decisions

1. **The lock row is taken as the verb's last statement before its commit,** and the verb's reads before it are checked again under the lock. What must be checked again is the first thing this spec's build finds out, by a spike.
2. **`relabel_spans` gains the term `everyone_level <> :rank`.**

## Tests

A counted test on Postgres: while a 10,000-target delete runs its body, a second delete on the same mount returns before the first commits. For decision 2, a relabel over a region where half the rows are already at the new level writes the other half alone, counted as rows updated.

## Scope

In: `serialize()` and the five verbs that take it, and `relabel_spans`. Out: the posture change's own lock.

## Not checked

- Neither defect was run. Both were read.
- What a verb that takes the lock last must check again, for each of the five verbs.

## One line

A topology verb takes its lock as it commits and not as it starts, and a relabel writes only the rows whose level changes.
