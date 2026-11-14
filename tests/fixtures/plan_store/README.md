# Captured scan-tier plans

Inputs to the plan store reader's pin, `tests/test_plan_store.py::test_the_scan_reader_sees_the_walks_of_the_old_world`. They are not a contract on any engine's output format. Each file is one plan of the scan tier's statement as the engine's reader in `tests/support/plan_store.py` receives it. All were captured on 2026-11-13 from the lane `lane/scan-tier` over `1c06ecfc`.

- `*-old-*`: the plan store as first built. Its files had the one-character body `x`, which the index never encodes, so 50,001 of 56,203 rows awaited the index.
- `*-walk-*`: a walk hidden in a seek's shape, forced by the builder's `probe_walks.py` on a small store of 2,000 files in a throwaway schema; or, for the five files marked constructed below, a shape the reader does not parse, written by hand beside a seek it does. Those five are constructed, not captures: they pin that what the reader cannot read counts as a scan.
- `*-corrected*`: the plan store with every body encoded and exactly one row awaiting the index.

| File | Engine | Captured by | What it holds |
|---|---|---|---|
| `postgresql-old-whole.txt` | Postgres 17 | the session lead's engine leg | The whole caller's plan, verbatim: a walk of `ix_vfs_entries_path` with no index condition. |
| `mariadb-old-whole.txt` | MariaDB | the session lead's engine leg | The whole caller's `EXPLAIN` row, verbatim: `type: index` on `ix_vfs_entries_path`. |
| `mariadb-old-partial.txt` | MariaDB | the session lead's engine leg | The 300-root caller's `EXPLAIN` row, verbatim: an `index_merge` `sort_union` over ranges of `ix_vfs_entries_path` and `ix_vfs_entries_owner_id`. |
| `mssql-old-whole.xml` | SQL Server 2025 | the session lead's engine leg | Excerpt: the whole caller's showplan access operator, a `Clustered Index Scan`. Its attributes are as captured; the rest of the showplan is dropped. |
| `mssql-old-partial.xml` | SQL Server 2025 | the session lead's engine leg | Excerpt: the 300-root caller's access operators, a full `Index Scan` of `ix_vfs_entries_everyone_path` and its key lookup. Attributes as captured; the rest dropped. |
| `oracle-old-whole.txt` | Oracle 23ai Free | the builder's probe | Excerpt: the whole caller's `DBMS_XPLAN` plan-table rows that the probe kept, `TABLE ACCESS FULL VFS_ENTRIES`. |
| `oracle-old-half-everyone.txt` | Oracle 23ai Free | the builder's probe | The half caller's first statement's plan-table rows: an `INDEX RANGE SCAN` of `IX_VFS_ENTRIES_EVERYONE_PATH` beside `INDEX UNIQUE SCAN`s of the path index. |
| `oracle-old-half-fullscan.txt` | Oracle 23ai Free | the builder's probe | The half caller's second statement's plan-table rows: an `INDEX FULL SCAN` of `IX_VFS_ENTRIES_PATH`. |
| `postgresql-walk-nonleading.txt` | Postgres 17 | the builder's probe | `WHERE kind = 'file'` with the kind index dropped and sequential and bitmap scans off: an `Index Only Scan` of `ix_vfs_entries_encoded_kind` whose `Index Cond` names only its second column. |
| `mssql-walk-wholeindex.xml` | SQL Server 2025 | the builder's probe | Excerpt: `WHERE path <> '/'` under `WITH (FORCESEEK, INDEX(ix_vfs_entries_path))`, an `Index Seek` whose two ranges, `< '/'` and `> '/'`, are each open at one end and together cover the whole index. Attributes and seek predicates as captured; the rest dropped. |
| `oracle-walk-skipscan.txt` | Oracle 23ai Free | the builder's probe | `WHERE kind = 'file'` under `INDEX_SS`: an `INDEX SKIP SCAN` of `IX_VFS_ENTRIES_ENCODED_KIND`. |
| `postgresql-walk-unknown.txt` | Postgres | constructed | A `Tid Range Scan` on `vfs_entries`, a node type the reader does not name, under an `Append` beside an `Index Scan` of the dirty index. |
| `mariadb-walk-unknown.txt` | MariaDB | constructed | An `EXPLAIN` row of `type: index_subquery`, an access type the reader does not name, on the dirty index. |
| `mssql-walk-partitioned.xml` | SQL Server | constructed | An `Index Seek` of the dirty index whose seek keys sit in a `SeekPredicatePart` with no `SeekPredicateNew`, a form the reader does not read. |
| `oracle-walk-unnamed.txt` | Oracle | constructed | An `INDEX FULL SCAN` of `SYS_C008123`, a system-named index the plan does not tie to `VFS_ENTRIES`, beside an `INDEX RANGE SCAN` of the dirty index. |
| `sqlite-walk-scantable.txt` | SQLite | constructed | A `SEARCH` of the dirty index beside `SCAN TABLE vfs_entries`, the spelling of a scan before SQLite 3.36. |
| `sqlite-old-whole.txt` | SQLite 3.50 | the builder's probe | The whole caller's statement with the path index forced by `INDEXED BY`, a walk of that index. On the old world SQLite's rarity hint kept the seek, so this is the walk the reader must still name. |
| `postgresql-corrected.txt` | Postgres 17 | the builder's probe | Excerpt: the 300-root caller's first statement, its plan cut inside the `Filter` line. It is an `Index Scan` of `ix_vfs_entries_encoded_kind` on its index condition. |
| `mariadb-corrected.txt` | MariaDB | the builder's probe | The 300-root caller's `EXPLAIN` row, verbatim: `type: range` on `ix_vfs_entries_encoded_kind`. |
| `mssql-corrected-*.xml` | SQL Server 2025 | the builder's probe | Excerpts: the access operators of the whole caller's statement (an `Index Seek` of `ix_vfs_entries_encoded_kind`) and of a 300-root owner-floor statement (an equality `Index Seek` of `ix_vfs_entries_owner_id`). Attributes and seek predicates as captured; the rest dropped. |
| `oracle-corrected.txt` | Oracle 23ai Free | the builder's probe | The 300-root caller's plan-table rows: `INDEX RANGE SCAN IX_VFS_ENTRIES_ENCODED_KIND`. |
| `sqlite-corrected.txt` | SQLite 3.50 | the builder's probe | The `EXPLAIN QUERY PLAN` detail of every statement: `SEARCH` on `ix_vfs_entries_encoded_kind`. |
