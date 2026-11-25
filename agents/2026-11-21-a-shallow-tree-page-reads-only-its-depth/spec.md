# A shallow tree page reads only its depth

A draft, written on 2026-11-21 from slice C of `context/specifications/active/176-the-listing-cursor/spec.md` and choice 3 of `agents/2026-11-21-a-listing-comes-back-a-page-at-a-time/spec.md`, which left it out of that work. It is not reviewed, and nothing is built.

## The outcome wanted

`tree(path, max_depth=d, limit=n)` reads at most `d × (n + 1)` rows a page, however deep the subtree goes beneath the bound.

## Builds on

The listing cursor of `agents/2026-11-21-a-listing-comes-back-a-page-at-a-time/spec.md`: `Result.next_after`, the keyset pages in `src/vfs/storage/backends/database/listings.py`, the fill rule in `keyset.py`, and the partial index `ix_vfs_entries_live_path (path) WHERE deleted_at IS NULL`.

## The problem

A `tree` page under `max_depth` filters on a slash count computed from `path` (`_slash_count` in `listings.py`). The term is a residual filter, so every row in the page's path range is read and the rows deeper than the bound are dropped. Spec 176 measured it on SQLite at its appendix A: `tree("/n", max_depth=1)` over 10 directories of 100 files, `limit=5`, read 506 and 605 rows for 5 rows a page. The listing cursor kept that profile and says so in the `tree_rows` docstring.

## Decisions

1. **A stored `depth` column,** the number of `/` in the stored path, written wherever `path` is written: the write plan, a move's root and every descendant it rewrites, and a copy. It is a cache of `path`, as `path` is of the `(parent_id, name)` chain, and a drift test pins `depth == path.count("/")` on every row the conformance battery writes, moves or copies.
2. **A partial index `(depth, path) WHERE deleted_at IS NULL`,** by the measurement of `agents/2026-11-21-a-listing-comes-back-a-page-at-a-time/research.md`: a composite that leads with `deleted_at` is not picked by Postgres.
3. **A page under `max_depth = d` is one stream per depth,** each `depth = r + k AND path > :after AND path < :upper ORDER BY path LIMIT :batch`, merged by the frontier rule. The streams chunk by `arm_budget`, so no statement grows with `d`.

## Tests

`tree("/n", max_depth=1, limit=5)` over 10 directories of 100 files visits at most 6 rows a page on SQLite (plan) and Postgres (`EXPLAIN ANALYZE`); `max_depth=2` at most 12. A move of a 10,000-row subtree issues the same number of statements as before. Counts, never clocks.

## Scope

In: the column, its writers, the index, the per-depth streams, the schema format version. Out: anything else of the cursor.

## Not checked

- Whether one `UNION ALL` statement of per-depth branches, spec 176's shape, costs fewer round trips than one statement per depth on each engine.
- How `agents/2026-11-21-postgres-reads-a-subtree-by-its-range/spec.md`, which rewrites the subtree predicate as a range, meets the per-depth streams.

## Choices to confirm

1. **One statement per depth or one `UNION ALL`?** Recommended: one statement per depth, the stream shape the fill rule already merges, unless a count on both engines shows the union is cheaper.

## One line

A stored depth and a partial index let a shallow `tree` page read only the rows within its depth.
