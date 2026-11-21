# Postgres reads a subtree by its range, and searches vectors through its index

A draft, written on 2026-11-21 from candidates 1, 2 and 6 of `agents/2026-11-20-vfs-serves-sqlite-and-postgres-only/research.md`. It is not reviewed, and nothing is built.

## The outcome wanted

A verb that reads a subtree costs what the subtree holds on every Postgres connection, whatever plan the connection has cached. A vector search on Postgres returns the depth it asks for, through the HNSW index, with its recall pinned by a test.

## Builds on

`agents/2026-11-20-vfs-serves-sqlite-and-postgres-only/spec.md`, which leaves SQLite and Postgres as the two tuned engines, and its memo's experiments X1 and X2.

## The problem

### A bound subtree `LIKE` scans all of `vfs_entries` under a generic plan

Run, in experiment X2 on Postgres 17.11 and 18.7. `descendant_filter` spells `path LIKE :root || '/%' ESCAPE '\'`. Postgres derives an index condition from `LIKE` only when the pattern is a constant. asyncpg makes each statement a named server statement, and after five executions on a large subtree vfs's own `tree` statement switched to its generic plan, a sequential scan, and stayed switched on that connection. A keyset page under the same plan read 910,459 buffers for 53 rows, where its range twin read 56. At the reference deployment a switched connection visits 10,000,000 rows for each such call. The `LIKE` is used by the move's descendant collection, the delete's tombstoning, `_deeper_postures`, the meta exclusion of every enumeration, and `tree`.

### On pgvector below 0.8, a vector search returns at most 40 chunks

Run, in experiment X1. The depth is at least 100, and `ef_search` stays at its default of 40. pgvector 0.7 has no iterative scan, and vfs serves `native_ann` there with no prelude. Recall@100 is 0.40 unscoped and 0.039 at a 10% scope.

### `index_method="ivfflat"` builds its index on an empty table and never raises `ivfflat.probes`

Read. The index is created at the `after_create` event. Its recall is expected to be near useless, and it was not run.

## Decisions

1. **A subtree predicate is the bytewise range `path > root || '/' AND path < root || '0'`** on both tuned engines, as `ranges.py` already spells scopes. It is exact under `COLLATE "C"` on Postgres and `BINARY` on SQLite, because `/` sorts just before `0`. The generic floor keeps `LIKE`, behind one profile fact, a bytewise key order.
2. **`native_ann` is served only on pgvector 0.8 or later.** Below it, the exact tier is served.
3. **`index_method="ivfflat"` is removed.**
4. **Postgres 17 is the stated floor, refused at first touch below it.**

## Tests

A Postgres-leg test forces the generic plan and counts the buffers of each subtree statement against the subtree's size. A plan test shows an Index Scan on `ix_vfs_chunks_embedding` whenever the tier says `native_ann`, and a recall test at fixed seeds, scoped and unscoped, compares against the Rust `cosine_topk` referee. A parity test shows the range and the `LIKE` match the same rows on SQLite.

## Scope

In: `descent.py`'s `descendant_filter` and its users, the ANN tier's version gate, `index_method`, and the first-touch version check. Out: a cardinality gate for narrow scopes, which waits on a measured threshold.

## Not checked

- Recall on real embeddings. X1 used synthetic clusters at 128 dimensions.
- Whether `hnsw.max_scan_tuples` cuts a narrow scope short when the planner still chooses HNSW.

## Choices to confirm

1. **Below pgvector 0.8: serve the exact tier, or set `hnsw.ef_search` to the depth?** Recommended: the exact tier, as the simpler rule.
2. **Decision 3: remove ivfflat, or build its index once data exists?** Recommended: remove.

## One line

A subtree is read by its key range so no cached plan scans the whole table, and vector search on Postgres goes through its index only where pgvector can fill the depth.
