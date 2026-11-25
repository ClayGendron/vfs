# A key list is one array bind

A draft, written on 2026-11-21 from candidate 3 of `agents/2026-11-20-vfs-serves-sqlite-and-postgres-only/research.md`. It is not reviewed, and nothing is built.

## The outcome wanted

Every key list is sent as one bound array, so a call site has one statement text whatever the list's length, and a list the size of the corpus is one statement, not hundreds.

## Builds on

`agents/2026-11-20-vfs-serves-sqlite-and-postgres-only/spec.md` and its memo's experiment X4.

## The problem

Every key list is an expanding `IN`, built in one owner, `membership()`. Its text changes with its length, so a Postgres connection prepares a new statement for each length: X4 measured 804 prepares in 800 executions once lengths vary. Some lists are corpus-sized: `_visible_chunks` over every chunk a query term names is about 300 statements for 10,000,000 ids.

## Decisions

1. **On Postgres, membership is `col = ANY($1::type[])`.** X4 shows its generic plan still seeks the index, at 3 keys and at 5,000. vfs already binds arrays this way for rights ranges.
2. **On SQLite, membership is `IN (SELECT value FROM json_each(?))`,** which X4 shows keeps its index. vfs already uses `json_each` for ranges.
3. **A declared element budget stays,** as a bound on memory and on how long a statement holds its locks, so no statement grows without limit.
4. **The multi-row `VALUES` writes are not in this spec.** `INSERT … SELECT FROM unnest(...)` needs its own count of statements and prepares first.

## Tests

A counted test: a call site run with lists of 1, 10, 100 and 5,000 keys prepares one statement on Postgres. Each converted call site's plan is checked on the Postgres leg, since a generic plan estimates an array at 10 elements.

## Scope

In: `membership.py` and every call site it serves. Out: the bulk writes, by decision 4.

## Not checked

- The plan of each call site after the change. X4 checked one shape.

## Choices to confirm

1. **What element budget bounds an array?** Recommended: the 32,668 chunk the memo uses for a 10,000-key snapshot, to be measured.

## One line

A key list is one bound array on both engines, with one statement text per call site and a declared budget on its size.
