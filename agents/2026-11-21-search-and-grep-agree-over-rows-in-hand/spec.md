# Search and grep agree over rows in hand

A draft, written on 2026-11-21 from what pull request 25 and the earlier readings of search left. It is not reviewed, and nothing is built.

## The outcome wanted

`search` and `grep` given the same rows and the same patterns treat each row the same way: a brace pattern is expanded once in the kernel, a row in the trash view is matched or reported, and a batch of nothing but head rows answers the same way from both.

## Builds on

`agents/2026-11-17-search-applies-its-file-filters-to-rows-in-hand/spec.md`, pull request 15, and pull request 25, which made `search` leave out a row at a storage's root.

## The problem

Each was shown by a script that ran, unless it says otherwise.

- **`search` without `observations` does not expand a brace pattern in the kernel, as `grep` does.** `*.{md,rst}` matches nothing there, and a glob that cannot be parsed is refused once by each mount, so one bad pattern gives as many errors as there are mounts.
- **`grep` over a held row in the trash view matches nothing and reports nothing.** The caller cannot tell an empty match from a row that was never searched.
- **A batch of nothing but head rows makes `grep` fail `wrong_kind`, where `search` now answers empty.** A head row is the row of a mount point, of `/`, or of `/.vfs/trash`. Pull request 25 noted the difference, which predates it.
- **A storage searches 10,000 rows in hand close to its time budget.** 8 to 9 seconds against 10, on SQLite in memory, measured once by the clock. At the reference deployment, 10,000 rows is a supported batch, and a batch that reaches the budget returns fewer rows with no other sign.

## Decisions

1. **The kernel expands brace patterns for `search` as it does for `grep`,** and refuses a pattern that cannot be parsed once, before any mount is called.
2. **`grep` over a held row in the trash view searches that deleted row's body,** as `read` of the same row returns it, and a row it cannot search gets an error record.
3. **`grep` leaves out head rows, as `search` does,** so a batch of nothing but head rows answers with no rows and no error from both.
4. **The 10,000-row search is profiled by counting statements and rows visited,** and the work that grows faster than the batch is found and fixed in the storage.

## Tests

A parity test runs `grep` and `search` over the same held rows and patterns, head rows and trash rows among them, and compares what each leaves out and what each refuses. A counted test pins the statements of a 10,000-row search.

## Scope

In: the kernel's pattern handling for `search`, `grep` over rows in hand, and the database storage's search over rows in hand. Out: ranking.

## Not checked

- Where the 10,000-row search spends its time. The 8 to 9 seconds were read off a clock, once.
- Whether a deleted row's body is still held for every row the trash view lists.

## Choices to confirm

1. **Decision 3: does `grep` leave out head rows, or does `search` go back to refusing them?** Recommended: `grep` leaves them out, as `search` does since pull request 25.
2. **Decision 2: does `grep` search a deleted row?** Recommended: yes. Alternative: refuse a trash row with a record. Its cost: a caller who pipes the trash view into `grep` must filter first.

## One line

`search` and `grep` treat the same rows and patterns the same way, and a search over 10,000 rows in hand is counted and kept well inside its budget.
