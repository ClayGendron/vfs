# Blob storage: engine facts for file bytes in a row, and the external-store alternative

- **Status:** study
- **Date:** 2026-10-05
- **Owner:** Clay Gendron
- **Sources (all clones read-only, refreshed 2026-10-05):**
  - `sqlite` origin/master @ `3d17c3f9e` (public domain)
  - `postgres` origin/master @ `6b858a36` (PostgreSQL licence)
  - `sqlalchemy` HEAD @ `de83fa72d` (MIT; `LICENSE` checked). The installed
    wheel the experiment ran on is SQLAlchemy 2.0.52.
  - `langchain-mongodb` origin/main @ `9873d8b` (MIT)
  - `computer` origin/main @ `070359f` (MIT, Cloudflare)
  - `git` @ `5a7d1e8045` (GPL-2.0; studied for its filter docs only)
  - Public docs fetched where the clone does not carry them, cited by
    URL: sqlite.org `intern-v-extern-blob.html` and `fasterthanfs.html`;
    python-oracledb `user_guide/lob_data.html`; MariaDB KB
    `innodb-dynamic-row-format`; MySQL 8.4 `packet-too-large`; Microsoft
    Learn `binary-and-varbinary-transact-sql`; pyodbc wiki `Data-Types`.
- **Method:** source reading of the four clones (`repo:path:line`
  citations; no code copied), the SQLAlchemy dialect flags and DDL
  printed from the installed wheel, and one SQLite experiment run
  through `uv run python` from the vfs root. Labels: **observed** (read
  in source or docs), **measured** (the experiment), **inferred** (our
  reasoning from observed facts), **unverified** (general knowledge the
  clones and fetched pages did not confirm).
- **Experiment script:**
  `/Users/claygendron/.claude/jobs/b627c391/tmp/blobs/blob_bench.py`
  (SQLite 3.50.4, Python 3.13.11, sync `sqlite3` driver through
  SQLAlchemy Core; page_size 16384, WAL, synchronous FULL — the vfs
  profile's file settings).

The design question: a binary file's bytes live in a new `vfs_blobs`
table (one row per entry, keyed by `entry_id`, column `LargeBinary`)
beside `vfs_content`, on five engines through SQLAlchemy. Bulk ingest
of 10,000+ files in one call is a contract; no statement may grow with
batch size; no declared scale cap.

---

## 1. SQLite

### Facts

- **The length limit.** `SQLITE_MAX_LENGTH` defaults to 1,000,000,000
  bytes and "also limits the size of a row in a table or index"; the
  hard ceiling is what a signed 32-bit integer counts, 2^31−1
  (`sqlite:src/sqliteLimit.h:16-25`). `SQLITE_LIMIT_LENGTH` is the
  runtime handle on the same number — "the maximum size of any string
  or BLOB or table row, in bytes" (`sqlite:src/sqlite.h.in:4385-4386`);
  `sqlite3_limit()` can only lower it, never raise it past the
  compile-time value (`sqlite:src/main.c:3064`). A column read that
  exceeds it returns `SQLITE_TOOBIG` (`sqlite:src/vdbe.c:755`). Observed.
- **Overflow pages.** A b-tree leaf cell holds payload locally up to
  `maxLeaf = usableSize − 35` bytes; past that, the cell keeps between
  `minLeaf = (usableSize−12)·32/255 − 23` and `maxLeaf` bytes locally
  and the remainder goes to a singly linked chain of overflow pages,
  each carrying a 4-byte next-page pointer and `usableSize − 4` payload
  bytes (`sqlite:src/btree.c:1205-1235` — the distribution strategy is
  part of the file format; the formulas are set where the page
  geometry is computed, `sqlite:src/btree.c` at the `pBt->maxLocal =`
  assignment). At the vfs profile's 16 KiB page: local payload up to
  16,349 bytes, else ~2 KiB stays local and the rest chains at 16,380
  bytes a page. Observed.
- **Why the blob column goes physically last.** SQLite's record format
  is positional: `OP_Column` decodes the header and reads column *i*
  from the row bytes already on the leaf page when the column's end
  offset is inside the local payload (`sqlite:src/vdbe.c:3248-3251`,
  "the common case where the desired content fits on the original
  page"); otherwise it takes the overflow branch
  (`sqlite:src/vdbe.c:3278`). A column that sits *after* a large blob
  therefore lives past the local payload and every read of it walks the
  overflow chain. Large overflow values (> 4,000 bytes, table b-trees
  only) are cached per cursor so re-reading them is not a second copy
  (`sqlite:src/vdbe.c:757-765`). Observed; the cost is measured below.
- **Incremental blob I/O.** `sqlite3_blob_open(db, zDb, zTable,
  zColumn, iRow, flags, &pBlob)` opens a handle on one cell
  (`sqlite:src/sqlite.h.in:8206-8214`); `sqlite3_blob_read/write`
  address a byte range, `sqlite3_blob_bytes` reports the size,
  `sqlite3_blob_reopen` moves the handle to another row of the same
  table and column without re-preparing
  (`sqlite:src/vdbeblob.c:471,478,488,503`). The size of a blob cannot
  be changed through the handle — an `UPDATE` does that, and the
  `zeroblob(N)` function / `sqlite3_bind_zeroblob` pre-sizes a cell for
  later incremental writes (`sqlite:src/sqlite.h.in:8190-8197`). Any
  `UPDATE`/`DELETE` of the row expires the handle, "even a column other
  than the one the BLOB handle is open on"
  (`sqlite:src/sqlite.h.in:8178-8186`). Python 3.11+'s `sqlite3`
  exposes this as `Connection.blobopen()`. Observed.
- **Where files beat blobs.** The SQLite documentation's own
  measurement: "For BLOBs smaller than 100KB, reads are faster when the
  BLOBs are stored directly in the database file. For BLOBs larger than
  100KB, reads from a separate file are faster", and "a database page
  size of 8192 or 16384 gives the best performance for large BLOB I/O"
  (sqlite.org/intern-v-extern-blob.html — not in the source clone;
  observed via the public page). The companion page measures 8–12 KB
  blobs at 35 % faster than `fread()`/`fwrite()` of individual files and
  states "the filesystem will generally be faster for larger blobs,
  since the overhead of open() and close() is amortized over more bytes
  of I/O" (sqlite.org/fasterthanfs.html; it cites a Microsoft SQL Server
  study putting that crossover "between 250KiB and 1MiB"). Observed.

### Measured — 1,000 rows × 1 MiB through `LargeBinary`, executemany

Two tables with identical rows (`entry_id` INTEGER PK, `size` INTEGER,
`body` BLOB): one with `body` physically last, the control with `body`
before `size`. Rows inserted 100 per `execute()` call inside one
transaction; distinct `os.urandom` bytes per row.

| probe | result |
|---|---|
| insert 1,000 × 1 MiB, blob-last table | 2.16 s → 464 rows/s, 464 MiB/s |
| database file after both tables (2 × 1,000 MiB payload) | 2,004 MiB (0.2 % overhead) |
| point read of the full 1 MiB body by PK | 1.96 ms |
| point read of the narrow `size` column by PK, blob last / blob first | 34 µs / 36 µs |
| scan of the narrow column over all 1,000 rows, blob last / blob first | 13.6 ms / 149 ms |
| `blobopen()` + read of the first 4 KiB of a 1 MiB body | 55 µs |

Timings only. The one shape that moved: a scan that never touches the
blob is 11× slower when a narrow column sits *behind* the blob, because
every row's read walks the 1 MiB overflow chain to reach it. A PK point
read of the narrow column is unaffected either way (the first page is
read regardless). The "body column physically last" rule
(`vfs:src/vfs/models/rows.py:434-446`) is therefore worth exactly what
the docstring claims and no more: it protects scans and width changes,
not point reads.

### Table

| | SQLite |
|---|---|
| `LargeBinary` renders | `BLOB` (observed, installed wheel; `sqlalchemy:lib/sqlalchemy/dialects/sqlite/base.py:1966-1967`) |
| max value size | 1 GB default, 2 GB−1 hard; same cap bounds the whole row |
| bulk-insert caveat | none beyond vfs's own residency paging; `sqlite3.executemany` binds each row separately; `SQLITE_LIMIT_LENGTH` is per value, not per statement |
| compression | none server-side |
| partial read | `sqlite3_blob_open` / `Connection.blobopen` (55 µs for a 4 KiB head above) |

## 2. Postgres

### Facts

- **`bytea` and TOAST.** `LargeBinary` renders `BYTEA`
  (`sqlalchemy:lib/sqlalchemy/dialects/postgresql/base.py:3241-3245`).
  Any row wider than `TOAST_TUPLE_THRESHOLD` —
  `MaximumBytesPerTuple(4)`, "normally 2 kB" — is toasted down toward
  `TOAST_TUPLE_TARGET` (`postgres:src/include/access/heaptoast.h:29-50`;
  `postgres:doc/src/sgml/storage.sgml:447-455`). The toaster runs four
  passes: compress `EXTENDED` columns inline, pushing any single value
  still wider than the target straight out of line; externalize the
  remaining `EXTENDED`/`EXTERNAL` columns; compress `MAIN`; externalize
  `MAIN` only as a last resort
  (`postgres:src/backend/access/heap/heaptoast.c:160-270`). Out-of-line
  values are cut into ~2,000-byte chunk rows in the table's own TOAST
  relation (`chunk_id, chunk_seq, chunk_data`, unique index on the pair)
  and the main row keeps an 18-byte pointer regardless of the value's
  size (`postgres:doc/src/sgml/storage.sgml:420-444`). Observed.
- **Compression.** `pglz` or `lz4`; the compile-time default is `lz4`
  where Postgres was built `--with-lz4`, else `pglz`
  (`postgres:src/include/access/toast_compression.h:54-62`); the
  `default_toast_compression` GUC and `ALTER TABLE … SET COMPRESSION`
  choose per column (`postgres:doc/src/sgml/ref/alter_table.sgml:58`).
  `SET STORAGE EXTERNAL` "allows out-of-line storage but not
  compression" and makes `substring()` on wide `bytea` faster "because
  these operations are optimized to fetch only the required parts of
  the out-of-line value when it is not compressed"
  (`postgres:doc/src/sgml/storage.sgml:479-486`;
  `postgres:doc/src/sgml/ref/alter_table.sgml:416`). For bytes that are
  already compressed (PDF, PNG, zip, images) `EXTERNAL` skips a wasted
  `pglz` pass per value and makes the ranged read cheap. Observed.
- **The 1 GB field limit.** "field size: 1 GB"
  (`postgres:doc/src/sgml/limits.sgml:79-80`); it is the varlena
  4-byte header's 30-bit length (`postgres:src/include/varatt.h:87-88,
  255-256`) and `MaxAllocSize = 0x3fffffff` ("1 gigabyte − 1",
  `postgres:src/include/utils/memutils.h:40`). A `bytea` value is
  always read and written as a unit; there is no ranged read below the
  SQL `substring()` level. Observed.
- **Large objects.** `pg_largeobject` stores a LO as `LOBLKSIZE =
  BLCKSZ/4` (2,048-byte) page tuples; the maximum is `INT_MAX ×
  LOBLKSIZE` — the docs say 4 TB
  (`postgres:src/include/storage/large_object.h:55-76`;
  `postgres:doc/src/sgml/lobj.sgml:49-57`). The docs call TOAST what
  "makes the large object facility partially obsolete", with two
  remaining advantages: the 4 TB ceiling and that "reading and updating
  portions of a large object can be done efficiently, while most
  operations on a TOASTed field will read or write the whole value as a
  unit" (ibid.). LO reads and writes "must take place within an SQL
  transaction block" (`postgres:doc/src/sgml/lobj.sgml:115`); there are
  server-side `lo_from_bytea`, `lo_put`, `lo_get(loid, offset, length)`
  and `lo_unlink` (`postgres:doc/src/sgml/lobj.sgml:574-637`). A LO is
  an object in its own right, referenced by OID from any number of rows,
  so deleting a row never deletes its LO — orphan management is the
  application's (or the contrib `lo` module's trigger,
  `postgres:doc/src/sgml/lo.sgml:30-52`). Observed.
- **How the drivers bind bytes.** The wire protocol carries a format
  code per parameter and per result column, 0 text / 1 binary
  (`postgres:doc/src/sgml/protocol.sgml:166-169`). SQLAlchemy's asyncpg
  dialect renders `BYTEA` binds with a cast (`$1::BYTEA`,
  `AsyncpgByteA.render_bind_cast = True`,
  `sqlalchemy:lib/sqlalchemy/dialects/postgresql/asyncpg.py:271-272`)
  and passes `bytes` through unchanged
  (`…/asyncpg.py:1069-1070`); vfs's `"copy"` bulk mode streams the same
  rows as a binary `COPY` (`vfs:…/dialects.py:770-783`). That asyncpg
  (and psycopg 3) send parameters and receive `bytea` in binary format
  is general driver knowledge — **unverified** here (neither driver is
  cloned). `bytea_output` (`hex` default, `escape` legacy; input always
  accepts both, `postgres:doc/src/sgml/config.sgml:10938-10952`) only
  affects *text-format* results, i.e. psycopg2-style fetches and `psql`
  — not a binary-protocol driver. Observed / inferred.

### When `bytea` is right, when LO is

- `bytea` with `SET STORAGE EXTERNAL`: every file under 1 GB, read and
  written whole or by `substring()`; the value is transactional, lives
  in the row's TOAST relation, is dumped, replicated and dropped with the
  table, and binds as an ordinary parameter in a multirow insert or a
  `COPY`. This is the vfs case. Inferred.
- Large objects: only for values past 1 GB, or for a true seek/append
  stream API. The cost is a second object lifecycle (OIDs, manual
  unlink, `vacuumlo`), a transaction requirement around every read, no
  parameter-array insert, and a per-database catalog rather than a
  per-table one. Nothing in the vfs contract asks for either. Inferred.

### Table

| | Postgres |
|---|---|
| `LargeBinary` renders | `BYTEA` (observed) |
| max value size | 1 GB − 1 (varlena / `MaxAllocSize`); LO 4 TB |
| bulk-insert caveat | `COPY` streams row by row with no statement cap; Core pages at `insertmanyvalues_max_parameters = 32700` binds — but each bind carries a whole file, so the page is bounded by *bytes in flight*, not binds (see §6) |
| compression | TOAST `pglz`/`lz4`, per column; `SET STORAGE EXTERNAL` to skip it |
| partial read | `substring(body from i for n)` cheap only under `EXTERNAL`; LO `lo_get(oid, off, len)` |

## 3. MariaDB, SQL Server, Oracle — from the SQLAlchemy dialect sources

### Flags, printed from the installed wheel (observed)

| dialect (driver) | `LargeBinary` DDL | `use_insertmanyvalues` | `supports_multivalues_insert` | `insertmanyvalues_max_parameters` | page |
|---|---|---|---|---|---|
| sqlite (aiosqlite) | `BLOB` | True | True | 32,700 | 1,000 |
| postgresql (asyncpg) | `BYTEA` | True | True | 32,700 | 1,000 |
| mariadb (aiomysql) | `BLOB` | True | True | 32,700 | 1,000 |
| mssql (pyodbc) | `VARBINARY(max)` (with `deprecate_large_types`) | True (`wo_returning` True) | True | 2,099 | 1,000 |
| oracle (oracledb) | `BLOB` | **False** | **False** | 32,700 (unused) | 1,000 |

No dialect excludes LOB columns from insertmanyvalues. There is no
LOB-related branch in `_deliver_insertmanyvalues_batches`
(`sqlalchemy:lib/sqlalchemy/engine/default.py:1003-1028`); the paging
counts binds, never bytes. Oracle simply never enters that path: it
leaves both flags at the `DefaultDialect` values
(`sqlalchemy:lib/sqlalchemy/engine/default.py:384-386`), so Core's
executemany there *is* python-oracledb's array DML — which is why vfs
pins Oracle to `"core"` (ADR 056). Observed.

### MariaDB

- **Type.** `visit_large_binary` → `visit_BLOB` → bare `BLOB`
  (`sqlalchemy:lib/sqlalchemy/dialects/mysql/base.py:2654-2667`). MySQL's
  bare `BLOB` caps at 65,535 bytes — the same trap `_body_text()`
  already closes for text by pinning `LONGTEXT`
  (`vfs:src/vfs/models/rows.py:235-245`). The blob column needs the
  same variant: `LONGBLOB` (4 GB − 1),
  `sqlalchemy:lib/sqlalchemy/dialects/mysql/base.py:2675-2676`. Observed.
- **Packet size.** A packet is "a single SQL statement sent to the
  MySQL server, a single row that is sent to the client, or a binary log
  event"; one larger than `max_allowed_packet` raises
  `ER_NET_PACKET_TOO_LARGE` and closes the connection; the absolute
  maximum is 1 GB (MySQL 8.4 docs, `packet-too-large`; the MySQL 8.4
  server default is 64 MB, client 16 MB). MariaDB's KB page truncated
  before its default — **unverified**; the usual MariaDB server default
  is 16 MB. Two consequences: aiomysql renders executemany as one
  client-side multirow statement chunked at 1,024,000 bytes (ADR 056
  §4), so a page of blob rows is bounded by the driver; and **a single
  row larger than `max_allowed_packet` fails under every mode** — the
  exposure ADR 056 already records. The vfs test container sets no
  packet size (`vfs:docker/compose.test.yml:47-65`). Observed / inferred.
- **On-page layout.** Under InnoDB's `DYNAMIC` row format (the
  default) "only values longer than 40 bytes are considered for storage
  on overflow pages", and once chosen "the entire value of the column is
  stored on overflow pages, and only a 20-byte pointer to the column's
  first overflow page is stored on the main page" (MariaDB KB,
  `innodb-dynamic-row-format`). So the row stays narrow whatever the
  blob's size; column order does not matter the way it does in SQLite.
  Observed.
- **Binary introducer.** Without `binary_prefix=true` on the URL the
  client library can warn `1300 Invalid utf8mb4 character string` on
  binary binds under a utf8mb4 connection charset; the drivers add the
  `_binary` introducer when asked
  (`sqlalchemy:lib/sqlalchemy/dialects/mysql/base.py:395-420`). Observed.

### SQL Server

- **Type.** `visit_large_binary` renders `VARBINARY(max)` when
  `deprecate_large_types` is on (auto-detected from the server version;
  SQL Server 2012+) and the legacy `IMAGE` otherwise — and with the flag
  unset before a connection, DDL rendered offline falls to `IMAGE`
  (`sqlalchemy:lib/sqlalchemy/dialects/mssql/base.py:600-625,
  1794-1808`). `varbinary(max)` holds 2^31−1 bytes; `varbinary(n)` tops
  at 8,000 (Microsoft Learn, `binary-and-varbinary-transact-sql`).
  Observed.
- **Binding.** pyodbc wraps every binary bind in `dbapi.Binary` and
  binds `None` as `BinaryNull` so FreeTDS does not default a binary NULL
  to `SQLWCHAR`
  (`sqlalchemy:lib/sqlalchemy/dialects/mssql/pyodbc.py:451-470`). pyodbc
  binds `bytes` as `SQL_VARBINARY` or `SQL_LONGVARBINARY`, choosing by
  `SQLGetTypeInfo` and falling back to 1 MB when that is unsupported
  (pyodbc wiki, `Data-Types`); the length threshold at which ODBC
  switches to data-at-execution streaming is not documented there —
  **unverified**. `setinputsizes` is on by default in the pyodbc dialect
  and vfs turns it off for its own string reasons
  (`vfs:src/vfs/models/rows.py:176-179`; SQLAlchemy's
  `use_setinputsizes`, `…/mssql/pyodbc.py:338-355`). Observed.
- **Bulk.** The 2,100-parameter cap (`insertmanyvalues_max_parameters =
  2099`, `sqlalchemy:lib/sqlalchemy/dialects/mssql/base.py:3160-3162`)
  and the 1,000-row `VALUES` cap bound a page by *count*; nothing bounds
  it by bytes. ADR 056 keeps `"core"` on MSSQL and refuses
  `fast_executemany` on evidence. Observed.

### Oracle

- **Type.** `visit_large_binary` → `visit_BLOB` → `BLOB`
  (`sqlalchemy:lib/sqlalchemy/dialects/oracle/base.py:1263-1264`). The
  BLOB ceiling is (4 GB − 1) × `db_block_size`; SecureFiles stores small
  LOBs inline (≈ 4,000 bytes) and larger ones out of line — Oracle's
  intro page returned only a table of contents, so these two are
  **unverified**. Observed / unverified as marked.
- **Binding bytes.** SQLAlchemy's `_OracleBinary` passes
  `DB_TYPE_RAW` to `setinputsizes` (previously `BLOB`) and has no bind
  processor, so a Python `bytes` goes straight to the driver
  (`sqlalchemy:lib/sqlalchemy/dialects/oracle/cx_oracle.py:853-866,
  1297`); the `BLOB` DBAPI type is reserved for OUT parameters, where a
  RETURNING of a wide value into a RAW buffer fails with ORA-22835
  ("Buffer too small for CLOB to CHAR or BLOB to RAW conversion … maximum:
  4000"), so the dialect converts those to a LOB var and reads it
  (`…/cx_oracle.py:985-1013`). python-oracledb's docs: `bytes` bind
  directly to BLOB columns and "LOB data is limited to 1 GB in size"
  when bound that way; past 32,767 bytes into a PL/SQL call the driver
  creates a temporary LOB itself; larger streams go through
  `LOB.write()` (python-oracledb `lob_data.html`). Observed.
- **Fetching.** `auto_convert_lobs=True` (default) installs an output
  type handler that returns LOBs as `bytes`/`str` directly rather than
  as locator objects
  (`sqlalchemy:lib/sqlalchemy/dialects/oracle/oracledb.py:504-513`;
  `_CX_ORACLE_MAGIC_LOB_SIZE = 131072` sizes the string-LOB var,
  `…/cx_oracle.py:497`); python-oracledb reads "CLOBs and BLOBs smaller
  than 1 GB … directly as strings and bytes" (`lob_data.html`). The
  array-DML path (`cursor.executemany`,
  `sqlalchemy:lib/sqlalchemy/dialects/oracle/oracledb.py:756-762`) is
  what vfs's `"core"` mode already issues; the docs are silent on LOB
  binds inside executemany — **unverified**, and the Oracle leg is the
  referee. Observed.

### Table

| | MariaDB | SQL Server | Oracle |
|---|---|---|---|
| `LargeBinary` renders | `BLOB` — **64 KiB cap; pin `LONGBLOB`** | `VARBINARY(max)` (`IMAGE` if DDL rendered before connect) | `BLOB` |
| max value size | `LONGBLOB` 4 GB − 1; row and statement ≤ `max_allowed_packet` (≤ 1 GB) | 2^31 − 1 bytes | (4 GB − 1) × block size (unverified); 1 GB as a plain `bytes` bind |
| bulk-insert caveat | one row > `max_allowed_packet` fails in every mode; aiomysql chunks its multirow render at 1,024,000 bytes | 2,099 binds / 1,000 rows per page, count-bounded only | array DML, bind-count unbounded by SQLAlchemy; LOB-in-executemany unverified |
| compression | none by default (InnoDB page compression is a table option) | none by default (row/page compression excludes LOB pages) | SecureFiles `COMPRESS` option, off by default (unverified) |
| off-page layout | DYNAMIC: whole value off-page, 20-byte pointer in row | LOB pages, 16-byte pointer in row (unverified) | inline ≤ ~4,000 bytes else out of line (unverified) |

## 4. The external-store alternative

**langchain-mongodb (`libs/langchain-mongodb-deepagents-vfs`).** The
bytes never enter the database. `S3Backend.read/write/edit` go straight
to S3: `put_object` on write, `get_object` with a `Range` header for
offset/limit reads, and an ETag-conditioned `IfMatch` put for `edit`
(`langchain-mongodb:libs/langchain-mongodb-deepagents-vfs/langchain_mongodb_deepagents_vfs/backends/s3.py:98-198`).
What Atlas keeps is not the file but its search surface: one document
per 512-token chunk (64-token overlap) carrying `source_path`,
`chunk_index`, `content`, `embedding`, `page_number`, `char_start`,
`char_end`, `line_start`, `etag`, `filename`
(`…/dtypes.py:62-75`; `…/chunker.py:40-41`). The ETag is the only
identity the store records — sync and the watcher re-ingest a key only
when S3's ETag differs from the stored one (`…/sync.py:144-162`;
README "ETag-based idempotency"); size comes from `head_object` on
demand (`…/s3.py:253-258`). The price is spelled out in the README: S3
is the source of truth, search is eventually consistent, and a `write`
is greppable only after the watcher's 10 s poll plus indexing. Every
read is capped at 64 MiB (`MAX_READ_BYTES`). Observed.

**computer (`packages/dofs`).** Cloudflare's Durable-Object SQLite
filesystem keeps bytes *in* SQLite but content-addressed. A file is
cut into fixed 512 KiB chunks (`CHUNK_SIZE = 512 * 1024`,
`computer:packages/dofs/src/fs/writeFile.ts:27-29`), each SHA-256'd
(`…/writeFile.ts:139-142, 298-309`). Three tables: `vfs_blobs(hash PK,
size, last_seen)`, `vfs_blob_bytes(hash PK → vfs_blobs, bytes BLOB)`,
and the inode→chunk map `vfs_chunks(inode, idx, hash, size)` with
`PRIMARY KEY (inode, idx)` and an index by hash
(`computer:packages/dofs/src/schema/core.ts:62-84`). Dedup is the
insert itself: `INSERT INTO vfs_blobs … ON CONFLICT(hash) DO UPDATE SET
last_seen` and `INSERT INTO vfs_blob_bytes … ON CONFLICT(hash) DO
NOTHING` (`…/writeFile.ts:516-522`); a ranged read selects only the
chunk rows whose `idx` overlaps the byte range
(`…/readFile.ts:245-262`), and a GC sweeps `vfs_blobs` rows no
`vfs_chunks` row references after a one-hour safety window
(`…/fs/gc.ts:18-36`). The node row denormalizes `size` so `stat` does
not `SUM` chunks (`…/schema/migrations.ts:43-56`). This is the
in-database design that gives partial reads and dedup without leaving
the transaction. Observed.

**Git's clean/smudge filters — the "reference instead of bytes"
precedent.** Git's filter attribute names a `clean` command run on
checkin and a `smudge` command run on checkout, and the docs name the
second use explicitly: "store the content that cannot be directly used
in the repository (e.g. a UUID that refers to the true content stored
outside Git …) and turn it into a usable form upon checkout (e.g.
download the external content)"; `filter.<driver>.required = true`
declares that the pointer is unusable without the filter
(`git:Documentation/gitattributes.adoc:412-446`). A long-running
`process` filter handles every blob of one Git command in one
invocation, with a `delay` capability so a smudge can defer a slow
download (`git:Documentation/gitattributes.adoc:509-530, 612-625`).
Git LFS is the production instance of that pattern: the repository
holds a small text pointer (oid sha256, size) and the bytes live in an
LFS store — **general knowledge; git-lfs is not cloned.** Observed for
the git docs; the LFS pointer shape unverified.

## 5. What this says for vfs

### Column type per dialect

`LargeBinary` is the right Core type, with one variant — the same
shape as `_body_text()`:

| dialect | render | note |
|---|---|---|
| sqlite | `BLOB` | as is |
| postgresql | `BYTEA` | add `ALTER TABLE … ALTER COLUMN body SET STORAGE EXTERNAL` to the DDL: file bytes are mostly pre-compressed and `EXTERNAL` makes `substring()` a ranged fetch |
| mariadb / mysql | **`LONGBLOB` via `with_variant`** | bare `BLOB` silently caps a body at 65,535 bytes — the text table already learned this |
| mssql | `VARBINARY(max)` | ensure DDL is rendered on a connected dialect (`deprecate_large_types` resolves to True); offline it would print `IMAGE` |
| oracle | `BLOB` | as is; `bytes` binds as `DB_TYPE_RAW` and fetches as `bytes` under `auto_convert_lobs` |

Keep the blob column physically last in `vfs_blobs` as `vfs_content`
does. Measured: the rule is a 11× scan win on SQLite and free
elsewhere (InnoDB and TOAST move the value off-page regardless of
position). Inferred from measured + observed.

### The bulk-insert chunking rule for blob rows

Today's paging is count-bounded: binds per statement
(`insertmanyvalues_max_parameters`, `rows_per_statement`) and, on
MSSQL, rows per `VALUES`. For `vfs_blobs` the bind count is tiny (two
or three per row) and irrelevant; **the bound that matters is bytes in
flight**. Three engine facts force it:

1. MySQL-family: one *statement* is one packet, and the packet must fit
   `max_allowed_packet`; aiomysql's 1,024,000-byte client-side chunk
   already keeps a page under it, but only because it meters bytes.
2. SQLite: a page of 100 × 1 MiB rows was a 100 MiB Python list and a
   100 MiB bind array — the experiment's 464 MiB/s is memory-bound, and
   10,000 such rows in one `execute()` would be 10 GiB resident.
3. Postgres `COPY` and Oracle array DML bind row by row, so no
   statement cap applies — but the row list is still materialised in
   Python before the call.

So: page blob rows with `byte_chunked(rows, size_of=len(body),
budget)` — the existing flush law (`vfs:…/dialects.py:592-644`) — nested
inside the count page, with a declared byte budget per page (a value
in the low tens of MiB; measure). The flush law's singleton exemption
("one oversized item rides alone") is exactly right for a file bigger
than the budget: it goes in its own statement. Inferred.

The one thing no chunking can fix: **a single row larger than the
engine's single-value cap** — `max_allowed_packet` on MariaDB (server
setting, default ~16 MB, ceiling 1 GB), 1 GB on Postgres `bytea`, 1 GB
as a plain `bytes` bind on Oracle, 2 GB−1 on SQL Server, 1 GB default
on SQLite. ADR 056 already records the MariaDB instance of this.

### When to recommend an external store seam

Not now, and not as a cap. The row-store design is correct on every
engine for the sizes vfs actually ingests; the external-store designs
studied (S3 + Atlas, Git LFS) buy unbounded object size and a
cheap-to-replicate bytes tier at the price of a second source of
truth, eventual consistency between bytes and search, and a
read-your-writes gap the README of the one production example
documents. `dofs` shows the in-database alternative to both: fixed
chunks, content-addressed, with ranged reads and dedup inside the
transaction. Recommend the seam only when a measured workload wants
one of: (a) objects past the engine's single-value cap, (b) ranged
reads of large bodies on an engine without a cheap `substring`
(SQLite has `blobopen`, Postgres has `EXTERNAL` + `substring`, the
others read whole), or (c) cross-region bytes replication the SQL
engine does not provide. If it comes, the row keeps `(entry_id, size,
sha256, store_key, etag)` and the body column is NULL — the LFS pointer
shape — and a `dofs`-style chunk table is the in-database fork to
weigh against it. Inferred.

### What would force a declared cap — and how to avoid declaring one

- **Per-value engine caps** (table above) are external limits, lawful
  to document: the classification is `unsupported` with the engine's
  number in the message, not a vfs ceiling. On MariaDB the cap is a
  *server setting*, so the honest docstring says "bounded by the
  server's `max_allowed_packet`" and names the setting; it must not
  hard-code 16 MB.
- **Postgres `bytea` at 1 GB** is the tightest fixed cap of the five.
  Do not design a vfs-wide 1 GB rule off it; a body past it on Postgres
  classifies `unsupported` there, and the LO route stays a recorded
  fork, not a reason to cap the others.
- **Bytes-in-flight paging** must be a budget, not a limit: a file
  larger than the page budget rides alone (the flush law), never
  refused.
- **Whole-value reads.** Every engine but SQLite (blobopen) and
  Postgres (`EXTERNAL` + `substring`) reads a body as a unit; a `read`
  with offset/limit on the others is a client-side slice of a full
  fetch. Say so in the docstring as the current profile, with the
  ranged-read fork named (`blobopen`, `substring`, a chunk table) —
  never as a size the verb refuses.

One line: store the bytes in the row as `LargeBinary` with a `LONGBLOB`
variant and Postgres `EXTERNAL`, keep the column last, page bulk inserts
by bytes as well as by count, and let only the engines' own per-value
caps classify — no vfs cap, no external store until a measured
workload asks for one.
