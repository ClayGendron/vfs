# Captured scan-tier plans

Inputs to the plan store reader's pin, `tests/test_plan_store.py::test_the_scan_reader_sees_the_walks_of_the_old_world`. They are not a contract on any engine's output format. Each file is one plan of the scan tier's statement as the engine's reader in `tests/support/plan_store.py` receives it. All were captured on 2026-11-13 from the lane `lane/scan-tier` over `1c06ecfc`, unless the table says otherwise.

- `*-old-*`: the plan store as first built. Its files had the one-character body `x`, which the index never encodes, so 50,001 of 56,203 rows awaited the index.
- `*-walk-*`: a walk hidden in a seek's shape, forced by the builder's `probe_walks.py` on a small store of 2,000 files in a throwaway schema; or, for the files marked constructed below, a shape the reader does not parse, written by hand beside a seek it does. Those are constructed, not captures: they pin that what the reader cannot read counts as a scan.
- `*-corrected*`: the plan store with every body encoded and exactly one row awaiting the index.

| File | Engine | Captured by | What it holds |
|---|---|---|---|
| `postgresql-old-whole.txt` | Postgres 17 | the session lead's engine leg | The whole caller's plan, verbatim: a walk of `ix_vfs_entries_path` with no index condition. |
| `postgresql-walk-nonleading.txt` | Postgres 17 | the builder's probe | `WHERE kind = 'file'` with the kind index dropped and sequential and bitmap scans off: an `Index Only Scan` of `ix_vfs_entries_encoded_kind` whose `Index Cond` names only its second column. |
| `postgresql-walk-unknown.txt` | Postgres | constructed | A `Tid Range Scan` on `vfs_entries`, a node type the reader does not name, under an `Append` beside an `Index Scan` of the dirty index. |
| `sqlite-walk-scantable.txt` | SQLite | constructed | A `SEARCH` of the dirty index beside `SCAN TABLE vfs_entries`, the spelling of a scan before SQLite 3.36. |
| `sqlite-old-whole.txt` | SQLite 3.50 | the builder's probe | The whole caller's statement with the path index forced by `INDEXED BY`, a walk of that index. On the old world SQLite's rarity hint kept the seek, so this is the walk the reader must still name. |
| `postgresql-corrected.txt` | Postgres 17 | the builder's probe | Excerpt: the 300-root caller's first statement, its plan cut inside the `Filter` line. It is an `Index Scan` of `ix_vfs_entries_encoded_kind` on its index condition. |
| `sqlite-corrected.txt` | SQLite 3.50 | the builder's probe | The `EXPLAIN QUERY PLAN` detail of every statement: `SEARCH` on `ix_vfs_entries_encoded_kind`. |
| `postgresql-corrected-pending.txt` | Postgres 17 | the session lead's engine leg, 2026-11-14, over the refresh lane's `62ce1abb` | The scan tier's statement on the store the refresh landing provisions, verbatim from the failing node's message: an `Index Scan` of `ix_vfs_entries_index_pending` whose `Index Cond` bounds its leading column, `encoded = false`, and `deleted_at IS NULL`, rows=1. |
| `postgresql-walk-pending-nonleading.txt` | Postgres | constructed | An `Index Scan` of `ix_vfs_entries_index_pending` whose `Index Cond` names only its second and third columns, `chunked` and `indexable`: a walk of the dirty index the bound must refuse, as `postgresql-walk-nonleading.txt` is for `ix_vfs_entries_encoded_kind`. |
