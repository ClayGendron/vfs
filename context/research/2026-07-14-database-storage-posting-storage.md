# 072 research — posting persistence across engines, from source

> **Note (2026-07-16 reorg):** this memo moved here from
> `specs/072-database-storage-backend/research-posting-storage.md`. Sibling citations resolve
> in this directory: `research.md` → `2026-07-13-database-storage-backend.md` ·
> `research-grep-index.md` → `2026-07-13-database-storage-grep-index.md` ·
> `research-pipelines-brief.md` → `2026-07-13-database-storage-pipelines-brief.md` ·
> `research-read-pipeline.md` → `2026-07-13-database-storage-read-pipeline.md` ·
> `research-write-pipeline.md` → `2026-07-13-database-storage-write-pipeline.md` ·
> `research-posting-storage.md` → `2026-07-14-database-storage-posting-storage.md`


Date: 2026-07-14. Method: four read-only precedent passes over sibling
checkouts — SQLite `ext/fts5` (the canonical inverted index persisted in
SQL tables), Postgres `src/backend/access/gin` + TOAST internals (how a
mature engine stores posting lists, and how our `bytea` blobs actually
live), Jackrabbit Oak (Lucene index files persisted into relational
tables across Postgres/MySQL/SQL Server/Oracle/DB2), and SQLAlchemy
2.1.0b3 dialects (what `LargeBinary` renders to, driver limits, and
insertmanyvalues batching mechanics).

Question: is the pinned shape — one row per `(epoch, gram_key)` holding
the gram's **full** sorted doc-id set as a single delta+varint blob
(`rows.py` `posting_list`) — the right persistence design across
SQLite/Postgres/MSSQL, and what does a 1–5M-row batch reindex write
path look like through SQLAlchemy Core?

## Bottom line

**Full-doclist-per-row stands.** Every engine that splits posting lists
does so for two reasons our design removed by construction: seeking
*inside* a common term's list without decoding all of it, and bounding
*in-place update* cost. We never seek within a gram's set (whole-blob
fetch of the k=4 rarest grams, intersect in memory) and never update in
place (batch-only epochs, drop-and-rebuild). Blob capacity is a
non-issue on the shipped tier (SQLite `BLOB`, Postgres `bytea`, MSSQL
`VARBINARY(max)` are all GB-scale); the one real cliff is MySQL, not in
the tier. Chunking stays **reserved, not built**: posting tables are
regenerable caches under the epoch fingerprint's format version, so a
future chunked format is a version bump and drop-and-rebuild, never a
migration.

Three amendments the precedent does demand (pinned in spec §6/§8):

1. **CAS-guard the epoch-pointer flip** — Oak publishes a rebuilt index
   via a checkpoint compare-and-set at commit; a bare `UPDATE` lets two
   concurrent reindexers publish over each other.
2. **Bytes-aware, PK-sorted bulk insert** — SQLAlchemy's insert
   batching is parameter-count-only with no byte limiter; the reindex
   verb must cap batch bytes itself and feed rows sorted by
   `(epoch, gram_key)`.
3. **Hot-blob fetch guard** — enforce the posting-byte budget *before*
   fetch via the `byte_size` catalog column; Postgres detoast makes an
   accidental hot-gram fetch expensive and non-partial.

## 1. FTS5 — inverted index inside a SQL b-tree (`~/Git/Repos/sqlite/ext/fts5`)

- Entire index lives in one two-column table
  `%_data(id INTEGER PRIMARY KEY, block BLOB)` (`fts5_index.c:82`);
  rowids bit-pack segment id / height / pgno (`fts5_index.c:285-299`).
  A separate `%_idx(segid, term, pgno)` b-tree maps term → leaf page
  (`fts5_index.c:6878`).
- **Doclists are always split across fixed-size leaf pages** — never
  one blob per term (`fts5_index.c:29-33`). Default page size
  `FTS5_DEFAULT_PAGE_SIZE = 4050` (`fts5_config.c:19`) — deliberately
  just under SQLite's 4 KB database page to avoid overflow chains. A
  SQLite-internals artifact, not a portable principle.
- Split rationale: (a) seek within a big doclist without loading it —
  large doclists get a `dlidx` skip-tree of first-rowid-per-page
  (`fts5_index.c:205-233`, seek at `fts5_index.c:3149-3172`);
  (b) merge a huge doclist against a small update without rewriting it
  (`fts5_index.c:35-38`). Both motives absent in our design.
- **Rebuild path is our model exactly**: scan content, accumulate in a
  ~1 MiB in-memory hash, flush pages through one persistent prepared
  `REPLACE INTO %_data VALUES(?,?)` (`fts5_storage.c:837`,
  `fts5_index.c:960-977`). Incremental writes use LSM-style leveled
  merges (`automerge=4`, `crisismerge=16`) — machinery we drop by
  being batch-only.

## 2. GIN + TOAST (`~/Git/Repos/postgres`)

- Two regimes: inline compressed posting list in the entry tuple until
  `GinMaxItemSize` (~2,700 bytes on 8 KB pages — the fit-three-items
  rule, `ginblock.h:249-253`), then a posting **tree**. In-tree lists
  are segmented: 128-byte merge floor / 256 target / 384 max
  (`gindatapage.c:34-36`). Segmentation serves sub-page random access
  and bounded in-place re-encode (README 269-275) — plus VACUUM's
  removal-never-grows invariant (`ginpostinglist.c:55-72`). All
  in-place-update concerns; none bind an epoch-immutable design.
- Encoding is delta + varbyte over sorted TIDs
  (`ginpostinglist.c:23-72`) — validates `delta+varint`.
- **Bulk build vs retail insert**: `ginbuild` accumulates key→TID-set
  in memory (red-black tree, flushed at `maintenance_work_mem`) and
  writes each key **once** from a pre-merged sorted set; the parallel
  path tuplesorts so keys arrive in b-tree order
  (`gininsert.c:618-810`). Lesson: pre-aggregate per gram (we do) and
  insert sorted by PK in large batches — per-row retail insert is the
  anti-pattern GIN's fastupdate pending list exists to avoid.
- **TOAST facts for our `bytea` rows**: tuples over ~2 KB toast;
  externalized values split into ~2 KB chunk rows
  (`heaptoast.h:46-89`). Fetching a 100 KB blob by PK = main-row fetch
  + ~50 TOAST-chunk fetches + full decompress (`detoast.c:115-191`,
  `342-382`). **No partial fetch of a compressed toasted value**
  (`detoast.c:410-415`); `substr()` random access requires
  EXTERNAL-uncompressed storage, and even then byte offsets don't align
  with varint doc-id boundaries. Hence the fetch guard: the cost of
  accidentally pulling a hot gram's multi-MB blob is real and
  unmitigable after the fact.

## 3. Jackrabbit Oak — search index persisted in relational tables

- Oak chunks at every layer: 32 KB per Lucene-file chunk
  (`OakBufferedIndexFile.java:48-52` — sized above the blob store's
  4 KB inline floor), 2 MB blocks in `RDBBlobStore`
  (`AbstractBlobStore.java:121`). Motives: **positioned reads** (Lucene
  seeks mid-file; only the touched 32 KB block is fetched) and
  **per-engine capacity traps**. Neither transfers: we fetch whole
  rare-gram blobs, and our tier has no capacity cliff.
- **Per-engine blob DDL it codifies** (`RDBBlobStoreDB.java`,
  `RDBDocumentStoreDB.java`): Postgres `bytea`; SQL Server
  `varbinary(max)` with clustered PK; **MySQL `mediumblob`/`longblob`,
  never plain `blob` (64 KB)**; DB2 `blob(<explicit size>)`. Its
  documented store floor: blobs ≥16 MB, text full-Unicode collating by
  code point (`RDBDocumentStore.java:214-219`).
- **Batch numbers from production**: 64 docs per batched insert
  (`CHUNKSIZE`, `RDBDocumentStore.java:2188-2191`), IN-lists hard-capped
  at 2,048 params (`RDBJDBCTools.java:387-394` — SQL Server's real
  limit is 2,100), large scans paged by keyset
  (`WHERE ID > ? ORDER BY ID` + `setFetchSize`), never OFFSET
  (`RDBBlobStore.java:649-683`).
- **Atomic publish precedent**: the async indexer flips a checkpoint
  string with an expected-value check at commit —
  `mergeWithConcurrencyCheck` re-reads the pointer and refuses the
  commit if it moved (`AsyncIndexUpdate.java:921-958`), plus a lease so
  two indexers can't run one lane. Direct analogue: our epoch flip must
  be `UPDATE … WHERE current_gram_epoch = :expected` with rows-affected
  checked, not a bare update.

## 4. SQLAlchemy 2.1.0b3 — dialect mechanics

| Dialect | `LargeBinary` DDL | Practical max value | Effective insert page (6 cols) | Fastest pure-Core bulk path |
|---|---|---|---|---|
| SQLite | `BLOB` (`sqlite/base.py:1918`) | ~1 GB (`SQLITE_MAX_LENGTH`) | 1,000 rows (driver `executemany`) | `insert(t), rows` in one txn |
| Postgres | `BYTEA` (`postgresql/base.py:3117`) | ~1 GB/field | 1,000 rows | psycopg3 native `executemany` (or `COPY` outside Core); psycopg2 gets the VALUES rewrite |
| MSSQL | `VARBINARY(max)` on 2012+ (`deprecate_large_types`, `mssql/base.py:1792-1808`, `3310-3313`); `IMAGE` pre-2012 | 2 GB | **349 rows** (2,099-param cap, `base.py:3142`) | default insertmanyvalues with a *small* page for blob-heavy batches; `fast_executemany` pre-binds the whole param array — memory-risky with `VARBINARY(max)` (`pyodbc.py:309`) |
| MySQL | **plain `BLOB` — 64 KB silent-truncation cap** (`mysql/base.py:2648-2652`) | 64 KB unless widened | 1,000 rows | must pin `mysql.LONGBLOB` via `with_variant` first |

- **Batching is parameter-count-only — there is no byte limiter**
  (`sql/compiler.py:5859-5877`; default page
  `insertmanyvalues_page_size = 1000`, `engine/default.py:256`). A
  1,000-row page of ~125 KB blobs materializes a ~125 MB statement.
  Blob sizes are power-law, so the reindex feed should partition by
  blob size: large pages for the tiny-blob majority, small pages for
  heavy grams (per-execute `execution_options(insertmanyvalues_page_size=N)`
  or pre-chunked `executemany` row lists).
- insertmanyvalues without RETURNING only engages on psycopg2 and
  MSSQL-non-fast (`crud.py:1723-1738`); SQLite/psycopg3/asyncpg/MySQL
  use the driver's native `executemany`, which bounds peak memory per
  parameter set — gentler for large blobs.
- No driver-level byte ceiling on a single binary param in the tier;
  MSSQL pyodbc wraps binary NULL specially (`_ms_binary_pyodbc`,
  `pyodbc.py:451-471`) and `setinputsizes` is on by default.

## 5. What this changes (pinned in spec)

1. **§6 storage granularity ruling** — one row per `(epoch, gram_key)`,
   full doclist per blob; chunking reserved via format-version bump.
2. **§6 index lifecycle** — CAS-guarded epoch flip; bulk insert sorted
   by `(epoch, gram_key)` in size-partitioned, byte-capped batches.
3. **§6 execution** — posting-byte budget enforced before fetch via
   `byte_size`; a blob the budget won't cover is never pulled.
4. **§8 blob-type note** — generic `LargeBinary` is correct on the
   shipped tier; a future MySQL tier must pin `LONGBLOB` via
   `with_variant`.

## What held without change

Delta+varint over sorted doc-ids (GIN's own encoding; FTS5's rowid
deltas); the `doc_count`/`byte_size` catalog columns (FTS5's
plan-without-decoding metadata, and now the fetch guard's input); the
prepared-statement batch rebuild (FTS5 `rebuild` is literally this);
composite `(epoch, gram_key)` PK addressing (the engine's b-tree does
what GIN's entry tree does); `ENCODING_ROARING` reserved for a
density-tier upgrade; the k-rarest read policy as the *reason* the
design escapes every splitting motive the precedent engines have.
