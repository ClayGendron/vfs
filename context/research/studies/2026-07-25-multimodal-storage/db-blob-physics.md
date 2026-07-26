# Bulk blob physics per SQL engine, and what SQLAlchemy models of it

- **Study for**: [multimodal storage and search brief](../../2026-07-25-multimodal-storage-and-search-brief.md), storage question 2 (dialect physics of bulk blobs), with bearing on questions 3 (size ceilings) and the batch contract.
- **Date**: 2026-07-25
- **Sources**: local `sqlalchemy` (MIT), `postgres` (PostgreSQL license), `sqlite` (public domain) checkouts; vendor docs online. License rule observed — no GPL clones opened.

---

## 1. How SQLAlchemy routes a bulk insert: two regimes, no byte accounting

SQLAlchemy 2.x has exactly two bulk-insert regimes, and which one runs is a
per-dialect flag, not a per-statement or per-type decision:

- **insertmanyvalues** ("imv"): the compiler rewrites `INSERT ... VALUES (…)`
  into pages of multi-`VALUES` statements —
  `INSERT ... VALUES (…), (…), …` — each page one `cursor.execute()`.
  Enabled by `dialect.use_insertmanyvalues`
  (`lib/sqlalchemy/engine/default.py:248`, default `False`).
- **DBAPI executemany**: one statement, N parameter sets, handed to
  `cursor.executemany()` — the driver does array binding.

The imv decision is made in `_get_crud_params`
(`lib/sqlalchemy/sql/crud.py:1723-1738`): `toplevel and
compiler.for_executemany and dialect.use_insertmanyvalues and (returning or
use_insertmanyvalues_wo_returning)`. **Column types never appear in this
predicate** — there is no LOB/LargeBinary gating anywhere. A `LargeBinary`
column participates in imv exactly like an `Integer`.

### Page sizing is rows and bind-parameter count — never bytes

`SQLCompiler._deliver_insertmanyvalues_batches`
(`lib/sqlalchemy/sql/compiler.py:5747-5888`) sizes each page as:

1. start from `insertmanyvalues_page_size` (default **1000 rows**,
   `engine/default.py:256`; psycopg2 raises it to **5000**,
   `dialects/postgresql/psycopg2.py:313`);
2. shrink so total binds stay under `insertmanyvalues_max_parameters`
   (default **32,700**, `engine/default.py:257` — just under the PostgreSQL
   wire protocol's int16 parameter-count field; MSSQL overrides to **2,099**,
   `dialects/mssql/base.py:3140-3142` — "the docs say 2100, in fact you can
   have 2099"; SQLite pre-3.32 overrides to 999,
   `dialects/sqlite/base.py:2230-2232`).

That is the whole calculation (`compiler.py:5859-5877`). **The batcher never
looks at the size of a bind value.** A 1,000-row page where each row carries a
1 MB `LargeBinary` value is one statement execution moving ~1 GB, and
SQLAlchemy will build it without complaint. `grep -rn max_allowed_packet
lib/sqlalchemy` returns nothing — no engine's byte ceiling is modeled
anywhere in the library. Byte-denominated chunking is entirely the caller's
job, which is exactly the `DialectProfile` doctrine ("what SQLAlchemy takes
no position on", `vfs/src/vfs/storage/backends/database/dialects.py:1-22`).

### Per-dialect answer to question (a): imv or executemany with blobs?

| Dialect | Bulk-insert regime | Evidence |
| --- | --- | --- |
| postgresql (all drivers) | imv, blobs included | `dialects/postgresql/base.py:3446` (`use_insertmanyvalues = True`) |
| mysql / mariadb | imv, blobs included | `dialects/mysql/base.py:2760` |
| mssql (pyodbc) | imv, blobs included | `dialects/mssql/base.py:3127`, max params 2,099 at `:3142` |
| sqlite | imv, blobs included | `dialects/sqlite/base.py:2120` |
| **oracle** | **never imv** — driver `executemany` array binding | `use_insertmanyvalues` is never set in `dialects/oracle/` (stays `False` from `engine/default.py:248`); RETURNING rides `insert_executemany_returning = True` (`dialects/oracle/cx_oracle.py:1101-1102`) |

So on four of five engines a media batch becomes giant multi-`VALUES`
statements; on Oracle it becomes one statement with client-buffered bind
arrays. Neither path degrades row-at-a-time for blobs (imv's row-at-a-time
downgrade at `compiler.py:5768-5816` triggers on RETURNING-ordering and
upsert shapes, not on types). Both paths concentrate the entire page's
payload in client memory and one network exchange — different mechanics, same
byte problem.

### Oracle LOB binding mechanics

The Oracle dialect maps `LargeBinary` to `_OracleBinary`, whose
`get_dbapi_type` returns `DB_TYPE_RAW` for `setinputsizes()`
(`dialects/oracle/cx_oracle.py:774-779`); `DB_TYPE_RAW` is in the dialect's
`include_set_input_sizes` allowlist ("used for BLOB",
`cx_oracle.py:1181-1199`), and `do_set_input_sizes` passes it per bind name
(`cx_oracle.py:1580-1594`). python-oracledb binds bytes directly — "LOBs up
to 1 GB in length can also be handled directly as strings or bytes"
([python-oracledb LOB guide](https://python-oracledb.readthedocs.io/en/latest/user_guide/lob_data.html)) —
so a plain `INSERT` of a 100 MB BLOB needs no temp-LOB choreography. For
`executemany`, the driver allocates one buffer per column sized to the
largest value in the array
([batch statement guide](https://python-oracledb.readthedocs.io/en/latest/user_guide/batch_statement.html):
"python-oracledb will also adjust the size of the buffers … memory has to be
reallocated and data copied") — mixed tiny/huge rows in one array waste
`arraysize × max_row_bytes` of client memory, a second reason to flush media
rows in small byte-bounded groups.

On RETURNING, LOB out-params are forced to real LOB locators
(`DB_TYPE_RAW → BLOB`, `cx_oracle.py:925-938`) to dodge ORA-22835 — RETURNING
a blob column from a bulk media insert is best avoided entirely.

### MSSQL specifics

`LargeBinary` → `_VARBINARY_pyodbc` wraps values in `dbapi.Binary` and NULLs
in `BinaryNull` (FreeTDS SQLWCHAR-coercion workaround,
`dialects/mssql/pyodbc.py:451-471`, colspecs at `:581-583`).
`fast_executemany` is explicitly a "limited size batches that fit in memory"
feature (`pyodbc.py:307-314`), is bypassed when imv is active
(`pyodbc.py:338-342`), and disables `use_insertmanyvalues_wo_returning`
when set (`pyodbc.py:614-616`) — do not reach for it for blobs; pyodbc's own
wiki documents memory blowups with `varbinary(max)` under it. DDL: plain
`LargeBinary` renders `IMAGE` unless `deprecate_large_types` is on, which
SQLAlchemy auto-enables for SQL Server ≥ 2012 (`visit_large_binary`,
`dialects/mssql/base.py:1792-1799`) — `VARBINARY(max)` is what modern
servers get. SQLAlchemy also models `FILESTREAM`
(`VARBINARY(filestream=True)`, `mssql/base.py:1458-1495`) — an engine-native
external-bytes escape hatch, per-engine only.

### MySQL landmine: `LargeBinary` renders `BLOB`, which caps at 64 KB

`visit_large_binary` → `visit_BLOB` → `"BLOB"`
(`dialects/mysql/base.py:2639-2652`). MySQL's `BLOB` holds at most
2^16−1 = **65,535 bytes**; `LONGBLOB` (2^32−1) must be asked for explicitly
([storage requirements](https://dev.mysql.com/doc/refman/8.4/en/storage-requirements.html)).
Any vfs blob column must be declared
`LargeBinary().with_variant(LONGBLOB(), "mysql", "mariadb")` or media over
64 KB fails (or truncates, depending on sql_mode) on the MySQL leg. This is
the single sharpest portability trap found in this study.

---

## 2. Per-engine byte physics (question b)

### Per-value (per-row) ceilings

| Engine | Column type | Hard cap | Practical cap |
| --- | --- | --- | --- |
| SQLite | BLOB | `SQLITE_MAX_LENGTH` default **1,000,000,000** (`sqlite/src/sqliteLimit.h:24`), raisable to 2^31−1 | the default 1 GB; whole value materializes in memory both directions |
| PostgreSQL | bytea | **1 GB − 1** — `MaxAllocSize ((Size) 0x3fffffff)` (`postgres/src/include/utils/memutils.h:40`); [limits page](https://www.postgresql.org/docs/current/limits.html) | far lower in practice: encode/decode and TOAST copies multiply memory; community guidance keeps bytea to low hundreds of MB |
| MySQL | LONGBLOB | 4 GB type cap | **`max_allowed_packet`**: server default **64 MB**, absolute max **1 GB** ([packet-too-large](https://dev.mysql.com/doc/refman/8.4/en/packet-too-large.html): "a communication packet is a single SQL statement sent to the MySQL server") — and see the escaping ×2 note below |
| SQL Server | varbinary(max) | **2^31 − 1** (~2 GB) ([capacity specs](https://learn.microsoft.com/en-us/sql/sql-server/maximum-capacity-specifications-for-sql-server)) | client memory; TDS streams it, no packet-count cap on a single param |
| Oracle | BLOB (SecureFiles) | terabytes (4 GB × block size) | **1 GB per direct bytes bind** ([python-oracledb LOB guide](https://python-oracledb.readthedocs.io/en/latest/user_guide/lob_data.html)); beyond that, temp-LOB streaming API |

### Per-statement / per-exchange ceilings

- **MySQL is the floor.** The entire rendered statement must fit in one
  communication packet ≤ `max_allowed_packet` (default 64 MB); exceeding it
  raises `ER_NET_PACKET_TOO_LARGE` **and closes the connection** — a
  connection-fatal outcome, not a clean error. Worse, the default drivers
  (PyMySQL, mysqlclient) use the *text* protocol: bind values are
  client-side-escaped into the SQL string, and escaped binary inflates up to
  **~2×** (every `\0`, `'`, `\` becomes two bytes). The honest budget per
  statement on MySQL is roughly `max_allowed_packet / 2` minus SQL overhead.
- **PostgreSQL**: no documented statement cap short of memory, but every
  datum ≤ 1 GB (`MaxAllocSize`) and the frontend/backend message length is
  an int32 — a multi-`VALUES` page approaching 1 GB total is in failure
  territory. The extended-protocol parameter-count field is int16, which is
  why SQLAlchemy's 32,700 default parameter budget exists.
- **SQL Server**: batch size cap is 65,536 × network packet size (default
  4 KB → 256 MB of SQL text), but parameterized varbinary rides TDS as
  parameters, so the binding constraint is the **2,100-parameter limit**
  (2,099 usable) plus client/server memory
  ([capacity specs](https://learn.microsoft.com/en-us/sql/sql-server/maximum-capacity-specifications-for-sql-server)).
- **Oracle**: binds are out-of-band from SQL text — no statement-size
  explosion; the constraint is client buffer memory (arraysize ×
  widest-row) and the 1 GB direct-bind cap per value.
- **SQLite**: bind values are not part of SQL text
  (`SQLITE_MAX_SQL_LENGTH` default 1e9 applies to the text only,
  `sqliteLimit.h:89`); per-value 1 GB cap is the only real ceiling.

### Server-side storage behavior (what the engine does with the bytes)

- **PostgreSQL TOAST**: tuples over `TOAST_TUPLE_THRESHOLD` (~2 KB — sized
  so 4 tuples fit a page) get varlena attributes compressed and/or moved to
  the toast table in chunks of `TOAST_MAX_CHUNK_SIZE` (~1,996 bytes — 4
  chunk-tuples per page) (`postgres/src/include/access/heaptoast.h:28-89`).
  Big bytea is therefore already segmented and diced server-side; the row
  keeps an 18-byte pointer. Changing chunking requires initdb.
- **Oracle SecureFiles**: LOBs ≤ ~4,000 bytes (minus control info) store
  inline in the row; larger go out-of-line to the LOB segment regardless of
  declared storage
  ([LOB storage guide](https://docs.oracle.com/en/database/oracle/oracle-database/12.2/adlob/LOB-storage-with-applications.html)).
- **SQL Server**: rows cap at 8,060 bytes; `varbinary(max)` values push to
  LOB allocation units, 24-byte root in-row
  ([capacity specs](https://learn.microsoft.com/en-us/sql/sql-server/maximum-capacity-specifications-for-sql-server), "Bytes per row").
- **MySQL/InnoDB**: long blobs spill to overflow pages (20-byte in-row
  pointer under DYNAMIC row format).
- **SQLite**: blob lives in the B-tree cell with overflow-page chains; the
  [sqlar format](https://sqlite.org/sqlar.html) is the existence proof that
  files-as-blobs in one table is a sane, supported pattern at this scale.

Every engine already does "bodies leave the narrow row" internally. A
separate blob sidecar table in vfs is therefore not fighting the engines —
it aligns with what they do, while keeping the *entries/content* rows narrow
at the SQL level too (no accidental blob detoast/fetch on metadata scans).

---

## 3. Does a 10,000-file batch force byte-denominated flush chunking? (question c)

**Yes — decisively.** Row-count and parameter-count chunking (what
`rows_per_statement` + `chunked` do today,
`vfs/src/vfs/storage/backends/database/dialects.py:254-268`) are the wrong
denominators for media because per-row size varies by six orders of
magnitude. Concrete failure math on today's content path
(`_replace_content` hands the whole batch to one `session.execute(insert(content), rows)`,
`vfs/src/vfs/storage/backends/database/writes.py:676-689`):

- 10,000 media files averaging 1 MB → imv pages of 1,000 rows →
  **~1 GB per statement**. MySQL dies at the default 64 MB packet (~64th
  row of the page, connection closed); PostgreSQL flirts with `MaxAllocSize`;
  MSSQL and Oracle survive only by burning ~1 GB+ of client and server
  memory per flush.
- Even *one* row can exceed an engine's exchange budget (a 100 MB video on
  MySQL's default config) — so a row-count floor of 1 does not save the
  batch; there must also be a declared per-value cap with the external
  escape hatch (brief question 3) above it.

### What the DialectProfile needs

Two new byte-denominated fields, same doctrine as `in_list_budget`
(declared because SQLAlchemy takes no position):

1. **`payload_byte_budget`** — max accumulated bind-payload bytes per flush
   (one imv page / one executemany call). The flush loop walks staged blob
   rows accumulating `len(bytes)` and cuts a statement when the *next* row
   would cross the budget (greedy first-fit keeps order); row-count and
   parameter budgets still apply as secondary caps. Suggested declarations:
   - MySQL/MariaDB: **16 MB** — half the default 64 MB packet to absorb
     ~2x text-protocol escape inflation, halved again for SQL overhead
     and headroom;
   - GENERIC floor: **16 MB** (safe under every engine's default);
   - PostgreSQL / MSSQL / Oracle / SQLite: **32–64 MB** — no protocol wall
     nearby; the budget is really a client/server memory bound, so keep it
     modest rather than chase each engine's theoretical max.
2. **`value_byte_cap`** — max bytes for a single stored blob value, the line
   above which storage refuses (or the external/`external_id` hatch takes
   over). The honest portable floor is **MySQL-shaped**: ~16 MB at default
   config (a value whose escaped form must fit the packet *alongside* its
   statement); engines without the packet wall could declare 256 MB–1 GB,
   but a single portable cap (e.g. 64 MB, documented as requiring
   `max_allowed_packet=256M` on the MySQL leg) is easier to reason about.
   Note the per-value cap cannot be derived from `payload_byte_budget` —
   one is an exchange bound, the other a refusal contract.

The existing pattern generalizes cleanly: `membership_budget` takes the
tighter of two caps; a `flush_budget(profile, parameter_budget)` analog
takes the tightest of rows/params/bytes. No SQLAlchemy facts are being
copied — the library genuinely models none of this (see §1).

One engine-specific relaxation worth recording: on Oracle the budget bounds
client buffer memory, not a protocol wall, and on SQLite it bounds nothing
real — the budget can be generous there. On MySQL it is load-bearing and
connection-fatal when violated.

---

## 4. Streaming / chunked read paths per engine (question d)

SQLAlchemy's read path materializes every blob column whole, per row, on
every engine (Oracle: the default `auto_convert_lobs=True` installs an
output-type handler converting BLOB to a raw buffer,
`dialects/oracle/cx_oracle.py:1422-1429`; disabling it yields LOB locators
with `read()`, `cx_oracle.py:404-415`). Native streaming exists but is
engine-private:

| Engine | Native streaming read | Granularity |
| --- | --- | --- |
| SQLite | `sqlite3_blob_open`/`sqlite3_blob_read` incremental I/O (`sqlite/src/sqlite.h.in:8142-8176`); exposed in Python as `sqlite3.Connection.blobopen()` (3.11+), not via SQLAlchemy | arbitrary offset/length |
| PostgreSQL | `substr(bytea, …)` compiles to `pg_detoast_datum_slice` (`postgres/src/include/fmgr.h:236-245`) — fetches only the needed TOAST chunks **iff the column storage is `EXTERNAL`** (uncompressed); with default `EXTENDED` the whole value decompresses first. Separately, large objects stream via `lo_*` in `LOBLKSIZE` (BLCKSZ/4 = 2 KB) chunks up to 4 TB (`postgres/src/include/storage/large_object.h:68-76`) but live outside row lifecycle (own GC, `vacuumlo`) — a poor fit for trash/restore/sweep |
| Oracle | LOB locator `LOB.read(offset, amount)` ([LOB guide](https://python-oracledb.readthedocs.io/en/latest/user_guide/lob_data.html)); requires `auto_convert_lobs=False` engine-wide in SQLAlchemy | arbitrary; extra round-trips per chunk |
| SQL Server | `SUBSTRING(col, off, len)` on varbinary(max) server-side; no driver-level streaming through pyodbc fetch | arbitrary via SQL |
| MySQL | `SUBSTRING(col, pos, len)` server-side; the row otherwise arrives whole in one packet (result rows are also packet-capped) | arbitrary via SQL |

**The portable floor is SQL-level ranged reads**: every engine has
`substr`/`SUBSTRING` over its binary type, so a
`read_bytes(entry, offset, length)` chunked-read verb can be implemented
portably in one statement shape — with the caveat that it is only O(slice)
on PostgreSQL when the blob column declares `SET STORAGE EXTERNAL`
(a one-line DDL decision to make at table-creation time, and cheap insurance:
media bytes are already compressed — image/video codecs — so disabling TOAST
compression loses little). Native incremental APIs (SQLite `blobopen`,
Oracle locators) are per-engine optimizations behind the same verb, not the
contract. For MySQL, chunk length must itself respect the packet budget.

Result-side symmetric hazard: a `SELECT` returning 1,000 media rows has the
same byte physics as the insert (MySQL row packets, client memory
everywhere). Bulk reads that project blob columns need the same
byte-denominated pagination — which argues for `size_bytes` being a stored
column on the blob row (known before fetching bytes), so read planning can
budget without touching payloads.

---

## 5. Findings against the brief

1. **(a)** insertmanyvalues runs with `LargeBinary` on postgresql, mysql,
   mssql, sqlite (no type gating exists, `crud.py:1723-1738`); Oracle alone
   never enables it and takes driver `executemany` array binding with
   `setinputsizes(DB_TYPE_RAW)` — both regimes accept blobs, neither bounds
   bytes.
2. **(b)** Ceilings: per-value — SQLite 1 GB (default), PG 1 GB−1 hard,
   MySQL `max_allowed_packet` (64 MB default, 1 GB max, ×2 escape
   inflation), MSSQL 2 GB, Oracle 1 GB per direct bind. Per-exchange —
   MySQL's packet is the binding floor; everyone else is memory-bound.
3. **(c)** Byte-denominated flush chunking is mandatory; the profile needs
   `payload_byte_budget` (flush accumulation cap, GENERIC floor 16 MB) and
   `value_byte_cap` (per-value refusal line feeding the external escape
   hatch). SQLAlchemy models neither; the existing
   `membership_budget`/`chunked` pattern extends naturally.
4. **(d)** Portable chunked reads = SQL `substr`/`SUBSTRING`; declare
   `SET STORAGE EXTERNAL` on the PG blob column at DDL time; engine-native
   streaming APIs are optional accelerations. Store `size_bytes` beside the
   blob so reads can budget before fetching.
5. **Trap to fix in any design**: `LargeBinary` alone renders MySQL `BLOB`
   (64 KB cap) — the blob column must carry a `LONGBLOB` variant.
6. **Alignment**: every engine already segments large values out of the row
   (TOAST / LOB segments / overflow pages) — the brief's sidecar-table
   hypothesis rhymes with engine internals rather than fighting them.
