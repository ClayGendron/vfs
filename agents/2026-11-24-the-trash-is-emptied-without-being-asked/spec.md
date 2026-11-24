# The trash is emptied without being asked

A draft, written on 2026-11-24 from the work on `agents/2026-11-24-a-deleted-row-gives-up-its-path/spec.md`, which leaves it out. It is not reviewed, and nothing is built.

## The outcome wanted

A deleted row older than the mount's `trash_days` is removed without any caller asking for it, in bounded pieces, and a deployment can see when the pass last ran and how much it removed.

## The problem

- No code calls the retention pass. `sweep` is reached only through the public verb (`src/vfs/base.py`, `src/vfs/session.py:217`), read on `dev` at `27f3d24`. A mount whose owner never calls it keeps every deleted row, with its body, its version rows and its derived rows, for good.
- `trash_days` is 90 by default (`src/vfs/storage/backends/database/backend.py:143`). The docs read as if a deleted file is kept for that long and then goes. Nothing makes the second half true.
- The deletes spec makes this matter more. A name written and deleted `n` times then holds `n` deleted rows where it holds one today, and its "Cost" section sizes the standing deleted rows on a retention pass that runs.
- One retention pass takes the mount's serialization point as its first statement and scans the body tables for orphans inside that transaction (`trash.py:617-657`). Every delete, restore and move on the mount waits behind it. Numbered spec 180, a draft, bounds the pass with `limit=` and `after=`.

## Choices

1. **Who calls it.** The daily rebuild, which is already the one pass over the corpus; a job of its own, once jobs are built; or the owner of the deployment, with the docs saying so plainly and a count of expired rows shown where a deployment looks.
2. **How much one call removes.** The whole backlog, as today, or a bounded slice with a cursor, as numbered spec 180 has it.
3. **Whether the orphan scan rides the pass.** It reads two whole tables. It could run rarely, as a verb of its own.

## Tests

A count of deleted rows older than `trash_days` is 0 after the pass that the chosen caller runs, with no call to `destroy` by the test. One slice removes at most its limit.

## One line

Retention is a promise only if something keeps it, and today nothing runs the pass unless a caller asks.
