# A page reads around its tombstones on both engines only through partial indexes, and only once the tombstone index holds tombstones alone

This memo answers choice 2 of `spec.md` in this directory: which index keeps a listing page's read work bounded. It was written on 2026-11-21 on the branch `a-listing-comes-back-a-page-at-a-time`, from the tree at `702d961` with slice A built. The probes are in `probes/` beside it. A memo decides nothing; the decision it informs is recorded in the spec's landing notes.

Every claim carries a label. EXECUTED means a command ran and the claim reports its output. READ means the claim was seen in a file that is cited. INFERRED means reasoning from the two.

## The answer in one paragraph

Spec 176 chose two composite indexes, `(parent_id, deleted_at, name)` and `(deleted_at, path)`, because two of the engines it served had no partial index. On SQLite they bound a page at `limit + 1` rows visited. On Postgres 16 the planner never picks them: a page of 10 in a directory whose first 900 of 1,000 children are deleted visits 911 rows, exactly as with no new index. Two partial indexes, `(parent_id, name) WHERE deleted_at IS NULL` and `(path) WHERE deleted_at IS NULL`, are picked by both planners and bound every page at `limit + 1`. One more change is needed on Postgres: on a table that is mostly tombstones, with statistics gathered, the planner prefers the existing full index on `deleted_at` for its `IS NULL` seek, which visits every live row of the table. Making that index partial, `WHERE deleted_at IS NOT NULL`, removes the seek; the trash view and the retention sweep, the only readers it serves, still use it.

## Sources

VFS at `702d961`. SQLite as bundled with the project's Python 3.13. Postgres 16.15 from the Ubuntu 24.04 packages, a scratch cluster, with pgvector 0.6.0 from the same packages for the conformance leg. SQLite's partial-index rule (a `WHERE` term `x IS NULL` makes an index with that predicate usable) and Postgres's predicate proof for partial indexes are as each engine's documentation states them (READ, from memory of the documentation; not re-fetched).

## What was measured

### The page statements in plain SQL, on SQLite

`probes/sqlite_probe.py` builds a database through vfs: `/big` with 10,000 files, `/d` with 1,000 files and the first 900 deleted, `/s` with 1,000 files and nine of every ten deleted. It drains `ls` and `tree` pages with every index-usable term in SQL and one registered function as the only residual term, which counts each row the index range hands over (EXECUTED):

| Index shape | `ls /d`, limit 10 | `ls /s`, limit 10 | `tree /s`, limit 10 | `ls /big`, limit 1,000 |
|---|---|---|---|---|
| Today's indexes | 911 on page 1, then 11 | 101, then 110 | 101, then 110 | 1,001 |
| Composite `(parent_id, deleted_at, name)`, `(deleted_at, path)` | 11 | 11 | 11 | 1,001 |
| Partial `WHERE deleted_at IS NULL` | 11 | 11 | 11 | 1,001 |

Every drain returned the same rows under every shape: 10 pages, none repeated, none lost.

### The same statements on Postgres 16

`probes/pg_probe.sql` builds a table of the same shape with the three directories above and 200,000 more rows in 2,000 directories, a twentieth of them deleted, and runs `ANALYZE`. `probes/pg_probe.py` drains the pages under `EXPLAIN (ANALYZE, FORMAT JSON)` and adds each scan node's actual rows and the rows its filter removed (EXECUTED):

| Index shape | Index the plan reads | `ls /d`, limit 10 | `ls /s` | `tree /s` | `tree /d` |
|---|---|---|---|---|---|
| Today's indexes | the unique `(parent_id, name)`, the unique `path` | 911, then 11 | 101, then 110 | 101, then 110 | 911, then 11 |
| Composite | the same two, never the composites | 911, then 11 | 101, then 110 | 101, then 110 | 911, then 11 |
| Partial | `ix_probe_live_children`, `ix_probe_live_path` | 11 | 11 | 11 | 11 |

On this table the two composites took 8.8 MB and 8.7 MB, the two partial indexes 6.5 MB and 6.4 MB (EXECUTED). The partial indexes are smaller because they hold the live rows alone.

### The conformance leg, on a table that is mostly tombstones

`tests/support/cursor_contract.py` writes 1,000 children, deletes 900, and asks each engine's plan for the page statement vfs itself sends. On Postgres it first runs `ANALYZE` on the table, as autovacuum keeps statistics on a live server. With the partial live indexes added and the tombstone index left whole, the Postgres plan for both the `ls` and the `tree` page read `ix_vfs_entries_deleted_at`, the full index on `deleted_at`, for its `IS NULL` seek (EXECUTED). That seek visits every live row of the table and filters it by parent or range: bounded by the live rows of the mount, not by the page. With that index made partial on `deleted_at IS NOT NULL`, every page on SQLite, in memory and on Postgres read the live partial index, and the Postgres pages visited at most 11 rows (EXECUTED, `TestPostgresConformance` and the two SQLite classes, all passing).

## What it means for the design

- **The composites are not a Postgres design.** Postgres documents `IS NULL` as usable in a B-tree, and the planner still costs the unique index lower when the leading column is bound, so the composite never wins (EXECUTED above; why it costs them so is INFERRED).
- **A partial index is the structural answer on both engines.** It cannot hold a tombstone, so no plan through it can visit one. The plan choice is still the planner's, so the conformance leg pins it on each engine.
- **An index that holds both sides of the tombstone is a seek a live listing can be planned onto.** The full `deleted_at` index offered one. Partial on `IS NOT NULL`, it serves `deleted_at IS NOT NULL` and `deleted_at < :cutoff`, the trash view's and the sweep's terms, on both engines (INFERRED from each engine's partial-index rule; the trash and sweep suites pass with it, EXECUTED).
- **The trash view's listing is the stated exception.** Its rows are the tombstones, and a page of them visits every tombstone in its path range. `sweep` bounds that set.
- **An engine on the generic floor builds every one of these indexes whole.** It is served the same rows, with the tombstones in each index, and is fit for testing only.

## Not measured

- Postgres 15, 17, 18 and 19, and pgvector 0.8. Only 16.15 with pgvector 0.6.0 ran here.
- A real mount at the reference deployment's 10,000,000 rows. The Postgres probe holds 212,000.
- The write cost of the two new indexes: one more entry per live insert in each, and a delete or restore moving the row out of or into them. The 10,000-row write's statement count is unchanged, because index upkeep is the engine's and issues no statement (INFERRED; the write-at-scale tests pass, EXECUTED).
