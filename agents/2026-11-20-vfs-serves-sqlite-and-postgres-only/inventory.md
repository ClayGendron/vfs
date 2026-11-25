# Inventory: dropping MariaDB/MySQL, SQL Server and Oracle (SQLite and Postgres stay; GENERIC stays, warned)

Taken on 2026-11-20 at commit `c42dccd4`, on the branch `vfs-serves-sqlite-and-postgres-only`. Line numbers are at that commit. It is the list of every change landing 1 of `spec.md` makes. The executed computations used that commit's installed package. No tracked file was changed to take it.

Labels: **READ** (seen at the cited file:line), **EXECUTED** (a command ran; output reported), **INFERRED**.

Action vocabulary: **delete** (exists only for a dropped engine), **collapse** (an abstraction with 3+ variants that now has 2, or 2 that now has 1), **keep** (GENERIC, SQLite or Postgres still uses it), **reword** (prose/comment only).

---

## 0. Headline numbers (rough)

| Area | Removed (approx. lines) | Notes |
|---|---|---|
| `src/` | 750 to 900 | dialects.py ~300, ranges.py ~100, rows.py ~70, membership.py ~65, labels.py ~40, vector.py + vector_native.py ~65, value-cap chain ~55, drivers/distance/descent ~30, docstring rewording across ~15 files |
| `tests/` | 1,000 to 1,300 | marker-scoped legs 339 (EXECUTED, script below), plan_store.py ~180, test_dialects.py ~250, test_rows.py ~80, test_vector_native.py ~60, test_membership.py ~45, races/indexing/topology/grep/search/coherence/traverse/lexical/labels/ranges/edges/reads/drivers ~150 |
| Packaging and tooling | ~420 | uv.lock ~190 (6 packages, 177 lines of blocks plus vfs-py metadata), compose 77 + header, initdb 7, docker/README ~70, test-dialects.yml ~25, pyproject 8 |
| Skills | ~150 | db_test ~120 of 205; code_review, scale_review, spec_review, test_suite, workflow_template.js, check_workflow.py a few lines each |
| Prose | ~25 sentences | AGENTS.md 6 places, README 1, CONTRIBUTING 1, documentation 3 pages + 1 SVG, agents/tasks.md 2 tasks |
| `crates/` | 0 | EXECUTED: `grep -rliE 'mssql|oracle|mariadb|mysql|sql ?server' crates` returns nothing |

---

## 1. `src/` per file

### 1.1 `src/vfs/storage/backends/database/dialects.py` (1,170 lines; about 300 removed)

| Lines | Symbol | Action | Why |
|---|---|---|---|
| 12-16 | module docstring "Known engines (sqlite, postgresql, mssql, oracle, mariadb)" | reword | READ |
| 72 | `MembershipForm = Literal["in_list", "values"]` | delete (with field `membership`) | `"values"` is MSSQL's only (READ 575) |
| 74 | `RangeSource` members `openjson`, `json_table`, `json_table_clob` | collapse to `Literal["json_each", "unnest"]` | READ: 584, 619, 650 are the only declarers |
| 77-95 | `RangeHints`, `NO_RANGE_HINTS` | delete | only ORACLE sets it (READ 651-656); GENERIC and the rest take the empty default |
| 97-99 | `RELABEL_ROWS = 50_000` | keep value; reword | see section 2 |
| 101-103 | `BLOB_PAGE_BYTES = 8 MiB` + comment "the mysql family sends one statement as one packet" | keep value; reword | see section 2 |
| 106-115 | `ValueCap` | delete | only MARIADB declares `value_cap_query` (READ 625-626) |
| 117-128 | `_ESCAPED_BYTES`, `wire_bytes` | delete | MySQL text-protocol escaping only |
| 150-164 | `ShareLock` | collapse: drop `hint` (MSSQL, READ 574) and the `"table"` form (ORACLE, READ 642); keep `"row"` (SQLite/PG), `"exclusive"` (GENERIC, READ 666), `door` (PG, READ 533) |
| 169-416 | `DialectProfile` docstring (248 lines) | reword; roughly 75 lines go: `tuple_in` T-SQL note (196-200), `like_bracket_class` (202-207), `content_bytes` NVARCHAR (214-217), `bulk_insert` pyodbc (225-227), `vector_distance`/caps naming SQL Server/MariaDB/Oracle (231-244), `range_source`/`range_join`/`range_hints` (246-275), `row_lock_hint` (289-304), `membership` (309-321), `guard_miss` MariaDB (327-330), `relabel_rows` "five engines... SQL Server" (340-344), `statistics_listing` server list (376-381), `probe_entry_filter` (409-414) |
| 423 | field `row_lock_hint` | delete | MSSQL only (READ 573); `lock_rows` collapses to `with_for_update()` |
| 425 | field `membership` | delete | MSSQL only |
| 432-434 | field `retryable_driver_codes` + comment | delete or keep for GENERIC (decision, see 2.9) | only MARIADB (612) and ORACLE (643) set it |
| 436 | `values_join` | keep | POSTGRESQL True (536); MSSQL also |
| 437 | `tuple_in` | keep | False on GENERIC and MSSQL, True on SQLite/PG |
| 438 | field `like_bracket_class` | delete | MSSQL only (579) |
| 439 | `content_bytes` | keep | SQLite only |
| 442 | `bulk_insert` | keep | SQLite "driver", PG "copy", GENERIC "core" — still three modes |
| 443 | `vector_distance` `Literal["none","exact","ann"]` | keep | SQLite exact, PG ann, GENERIC none |
| 444-445 | `vector_dimension_cap`, `ann_dimension_cap` | **dead today**: no reader anywhere in `src/` or `tests/` (EXECUTED grep: only the declarations at 444-445 and values at 555-556, 586, 622, 649) | delete (pre-existing dead fields) or keep for PG; decision |
| 446 | `ann_honours_scope` | keep (or collapse: after the drop `ann` is PG only and PG is True) | read at backend.py:649 |
| 447-449 | `range_source`, `range_join`, `range_entry_hint` | keep `range_source` (None = GENERIC), keep `range_join` (SQLite `CROSS JOIN`, PG/GENERIC `JOIN`); delete `range_entry_hint` (MARIADB only, 621) |
| 450-453 | `value_cap_query`, `value_cap_setting` + comment | delete | MARIADB only |
| 454 | `range_hints` | delete | ORACLE only |
| 465-467 | `stored_length` + comment naming SQL Server/MariaDB | keep field (SQLite "length", PG "octet_length"); reword comment |
| 563-590 | `MSSQL` profile | delete | |
| 592-629 | `MARIADB` profile + 4-line comment | delete | |
| 631-657 | `ORACLE` profile + 5-line comment | delete | |
| 659-667 | `GENERIC` + comment "the tightest known key and IN-list budgets" | keep values; reword provenance (see 2.6) | |
| 669-675 | `PROFILES` | collapse to SQLite and Postgres | |
| 678-688 | `profile_for` | keep; candidate warning site is its caller, see section 6 | |
| 729-744 | `lock_rows` | collapse: the `with_hint` branch (743-744) and the T-SQL paragraph go | READ |
| 751-753 | `_FILTER_BIND_RESERVE = 32` | keep | engine-neutral |
| 770-772 | `_PATTERN_ARM_CEILING = 200` "clears every known engine's bind, IN-list, and depth caps" | keep value; reword (section 2.4) | |
| 809-811 | `_STATEMENT_BIND_RESERVE = 8` "driver wrappers (ODBC's sp_prepexec...)" | keep value; reword (section 2.5) | |
| 955-961 | `_DRIVER_UNIQUE_CODES = {1062, 1}`, `_SQLSTATE_BARE_INTEGRITY`, `_MSSQL_UNIQUE_NUMBERS` | delete or keep for GENERIC (decision 2.9) | 1062 is MySQL errno, 1 is ORA-00001, 2627/2601 SQL Server |
| 979-1000 | `is_retryable` docstring (MySQL 1205, MariaDB 1305) | reword; keep the unwind walk (INFERRED: Postgres also fails a savepoint release after a deadlock aborts the transaction, so the walk is not MariaDB-only) |
| 1003-1019 | `is_unique_violation` | collapse: SQLite code, else SQLSTATE 23505 — unless GENERIC keeps driver codes (2.9) |
| 1033-1048 | `is_value_too_large` | collapse: drop the MySQL 1153 arm (1047-1048); keep `sqlite3.DataError` and SQLSTATE class 54 |
| 1093 | `_MYSQL_PACKET_TOO_LARGE = 1153` | delete | |
| 1100-1112 | `_sqlstate_of` pyodbc-args branch (1109-1111) | delete or keep for GENERIC (2.9) | asyncpg exposes `sqlstate` |
| 1115-1127 | `_driver_code_of` | delete or keep for GENERIC (2.9) | MySQL family and python-oracledb only |
| 1145-1147 | `_bulk_statement` comment "implicit OUTPUT/RETURNING" | keep (`.inline()` is harmless on SQLite/PG; INFERRED) |

### 1.2 `src/vfs/storage/backends/database/ranges.py` (404 lines; about 100 removed)

| Lines | What | Action |
|---|---|---|
| 27-34 | docstring: "five-engine measurement", "seconds on MariaDB" | reword |
| 46-50 | imports `CLOB`, `LargeBinary`, `String` (used only by the dropped spellings/`_utf8`) | delete (INFERRED from reading the file: `CLOB` 292/313, `LargeBinary` 295/316, `String` 404) |
| 68 | `from vfs.models.rows import MSSQL_UTF8_COLLATION` | delete |
| 116-120 | everyone-branch Oracle hint | delete |
| 161-173 | `range_counts` docstring "a mysql-family caller reads bytes" | reword |
| 176-181 | `derived_hint` (always `None` without ORACLE) | delete; its one caller is lexical.py:586-593 (`hint` / `prefix_with`) |
| 189-222 | `_OpenJsonPairs`, `_JsonTableValues`, `_JsonTablePairs`, `_JsonTableClobValues`, `_JsonTableClobPairs` | delete |
| 235-261 | their `@compiles` renderers (keep `_render_range_join` 264-270) | delete |
| 288-295, 309-316 | `point_rows` / `open_rows` branches for openjson, json_table_clob, json_table | delete; each function keeps `unnest` and `json_each` |
| 374-379 | `_range_select` hint branches (`range_entry_hint`, `range_hints.ranges`) | delete |
| 398-404 | `_utf8` | delete |

### 1.3 `src/vfs/storage/backends/database/labels.py` (660 lines; about 40 removed)

| Lines | What | Action |
|---|---|---|
| 44-45 | "three on Oracle" | reword |
| 60-66 | Oracle stamp-table lock, SQL Server executor thread | delete (keep the Postgres multixact sentence) |
| 84 | `MSSQL_UTF8_COLLATION` import | delete |
| 123-124 | `_BOUND` (only the text spellings use it) | delete with 640-655 (INFERRED from reading) |
| 420-424 | `range_source is None` literal-count loop | keep (GENERIC) |
| 528-536 | `_stamp_under_share`: `"table"` arm (Oracle) and `hint` arm (MSSQL) | collapse to `"exclusive"` (GENERIC) and `FOR SHARE` (SQLite/PG) |
| 540-543 | `_lock_stamps` | keep (Postgres `door`, READ 283-284) |
| 594-596 | `_text` (bytes decode, MySQL family) | delete; 427 `_text(lo), _text(hi)` becomes plain |
| 618-660 | `_relabel_opens`: OPENJSON (640-647), JSON_TABLE (648-655), `range_hints.relabel` (658-659), docstring 623-631 | collapse to the `json_each`/`unnest` `UPDATE … FROM` arm plus the literal-`OR` GENERIC arm |

### 1.4 `src/vfs/storage/backends/database/membership.py` (131 lines; about 65 removed)

- 1-31 docstring: the `VALUES` form, guard-read seek, embed exception — reword to the in-list form.
- 37-38: `String, cast, collate, column, values` and `from sqlalchemy.dialects import mssql` — delete those no longer used.
- 40: `BytewiseString` import — delete.
- 54-55 `_MSSQL = mssql.dialect()` — delete.
- 63-68 `membership`: collapses to `target.in_(list(keys))`. The `profile` parameter becomes unused; about 100 call sites across 25 modules pass it (EXECUTED: grep count of `membership(`/`locked_lookup(`/`lock_rows(` callers). Keeping the parameter avoids shotgun surgery; dropping it is a large mechanical edit. Decision for the spec.
- 89-102 `locked_lookup`: collapses to the in-list arm (99-100).
- 110-131 `_key_rows`, `_typed`: delete.
- 71-73 `rare`, 76-86 `live_chunks`: keep.

### 1.5 `src/vfs/storage/backends/database/distance.py` (48 lines)

- 1-15 docstring naming Oracle/SQL Server/MariaDB wire forms — reword.
- 36-41: oracle and mssql branches delete; `("mariadb", "sqlite")` collapses to `"sqlite"`.
- 46-48 `has_cosine_distance`: collapse to `("postgresql", "sqlite")`; only reader is tests/models/test_vector_native.py:85,97 (EXECUTED grep). Candidate for deletion (no `src/` reader).

### 1.6 `src/vfs/storage/backends/database/drivers.py` (134 lines)

- 3-5 docstring "SQL Server through pyodbc needs its text binds left as Unicode" — reword.
- 52-61 docstring paragraph on pyodbc `setinputsizes`/`fast_executemany` — delete.
- 69-70 `if backend == "mssql": return {"use_setinputsizes": False}` — delete. (`ClosingConnection` for SQLite stays.)

### 1.7 `src/vfs/models/rows.py` (948 lines; about 70 removed)

| Lines | What | Action |
|---|---|---|
| 67 | `from sqlalchemy.dialects.mysql import LONGBLOB, LONGTEXT` | delete |
| 68 | `from sqlalchemy.dialects.oracle import RAW` | delete |
| 128-131 | `version_number` rename "NUMBER is an Oracle reserved word" | keep the column name (schema), reword comment |
| 170-172 | `_MYSQL_FAMILY = ("mysql", "mariadb")` | delete (note: covers MySQL community, already served as GENERIC; see 2.8) |
| 174-176 | `MSSQL_UTF8_COLLATION` (imported by ranges.py:68, labels.py:84) | delete |
| 179-188 | `_string(length)` — its only job is the mssql variant | collapse to `String(length)` (25 call sites, EXECUTED grep count); DDL on SQLite/PG unchanged (INFERRED: a `with_variant(..., "mssql")` never applies to other dialects) |
| 191-239 | `BytewiseString`: mysql `VARBINARY` arm (223-224), mssql arm (227-228), bind encode (231-234), docstring 197-212 | collapse to PG `collate="C"` + plain `String` fallback; `process_result_value` bytes decode may stay or go |
| 242-252 | `_body_text`: LONGTEXT and mssql variants | collapse to `Text()` |
| 255-266 | `_body_bytes`: LONGBLOB and mssql VARBINARY variants | collapse to `LargeBinary()` |
| 269-279 | `_timestamp`: Oracle `TIMESTAMP WITH TIME ZONE` variant | collapse to `DateTime(timezone=True)` (22 uses of the three helpers, EXECUTED) |
| 282-290 | `_uuid_native` docstring naming MSSQL/MariaDB | reword |
| 296-329 | `ULIDKey`: Oracle `RAW(16)` arm (314-315), docstring 303 | delete the arm |
| 426-427 | "Identity() is explicit for Oracle" | keep `Identity()` (removing it changes Postgres DDL: INFERRED), reword comment |
| 635-646 | `uq_vfs_edges_fs_parent`: `mssql_where` and `"mssql"` in `ddl_if` | collapse to `("sqlite", "postgresql")` |
| 725-727, 776-778, 790 | `LargeBinary().with_variant(LONGBLOB(), *_MYSQL_FAMILY)` on 5 posting/lexical blob columns | collapse to `LargeBinary()` |
| 834-835 | grants surrogate key "inside SQL Server's clustered cap" | keep schema, reword comment |
| 139 | `SCHEMA_FORMAT_VERSION = 27` | keep (INFERRED: no SQLite/PG DDL changes, so no bump) |

### 1.8 `src/vfs/models/vector.py` (358 lines) and siblings

- vector.py 1-13, 187-193 docstrings — reword.
- 47 `from sqlalchemy.dialects.oracle import VECTOR, VectorStorageFormat` — delete.
- 51 `from vfs.models.vector_native import MariaDBVector, MSSQLVector` — delete.
- 81 `NATIVE_VECTOR_DIALECTS = {"postgresql","oracle","mssql","mariadb"}` — collapse to `{"postgresql"}` (exported in `__all__` 72).
- 242-247 `native_type_for` oracle/mssql/mariadb arms — delete.
- 285-290 `process_bind_param` mariadb/oracle/mssql arms — collapse to `pack_vector` vs float list.
- 296, 301-302 `process_result_value` mariadb and mssql arms — collapse.
- `src/vfs/models/vector_native.py` (42 lines, `MSSQLVector`, `MariaDBVector`) — delete whole file.
- `src/vfs/models/vector_codec.py` 3-5 docstring "the MariaDB native type reuses it" — reword.

### 1.9 The value-cap chain (MariaDB `max_allowed_packet`): delete end to end (~55 lines)

- engine.py:82 (`ValueCap` import), 211-213 (`self.value_cap`), 595-596 (first-touch read), 606-611 (`_read_value_cap`).
- staging.py:40, 48 (imports), 161, 166 (`value_cap` param/attr), 209-224 (`within_value_cap`), 302 (its call).
- writes.py:77, 83 (imports), 189, 212, 332, 355 (params), 549-551 (`_BlobPage` cap arm), 1169-1173 (`_blob_wire_size`).
- backend.py:721, 733 (`value_cap=host.value_cap`).
- After this, `_BlobPage(BLOB_PAGE_BYTES, _blob_row_size)` has one size function (writes.py:549); INFERRED collapse candidate.

### 1.10 Other `src/` files: branches and docstrings

| File:lines | What | Action |
|---|---|---|
| descent.py:233-247 | `escape_like` bracket escape (`like_bracket_class`, T-SQL / ORA-01424) | collapse: delete 245-246 and the docstring sentence |
| rights.py:1335-1338 | `_piece_units` docstring "mysql family compares bytes and SQL Server keeps the UTF-8 collation" | reword |
| embed.py:255-260, 271-273 | refusal probe spelled as casts to the column type "because SQL Server merge-joins..." | keep shape (changing it changes SQLite/PG statement text), reword; see 2.7 |
| embed.py:344-347 | "the MySQL family" executemany note | reword |
| indexing.py:133-134 | `CHUNK_SLICE_BYTES` comment names SQL Server/MariaDB/Oracle | reword |
| indexing.py:524-525 | CASE wrapper "engines without boolean select-list expressions (SQL Server)" | keep shape, reword |
| indexing.py:881-885 | flip docstring "MySQL family and MSSQL" | reword |
| indexing.py:948-952 | `_pending_probe` "bare SELECT EXISTS is invalid T-SQL" | keep shape, reword |
| trash.py:502-508 | `_encoded_once_deleted` CASE "because SQL Server has no boolean expression in a value position" | keep shape, reword |
| pages.py:6-8 | pages not cursors: "SQL Server over ODBC" MARS | keep (the other reason, writes between pages, stands), reword |
| serialized.py:112-121 | `serialize` docstring "the profile's hint on T-SQL" | reword |
| scope.py:320-322 | "SQL Server scans the table instead" | delete sentence |
| authorized.py:17-24 | commit point per engine (SQL Server, Oracle, MariaDB) | reword to SQLite/PG |
| engine.py:211-212 | value cap comment | delete (1.9) |
| engine.py:723-724 | root `name="/"` because "Oracle folds '' to NULL" | keep value (data shape), reword |
| staging.py:212 | MySQL packet | delete (1.9) |
| grants.py:530-537 | `Pieces` docstring "SQL Server would pad past" | reword |
| backend.py:243-252, 262-268 | `capabilities` (search withheld when `vector_distance == "none"`), `traits` durability only for `PROFILES` | keep; both are the GENERIC behaviour |
| backend.py:649-651 | ANN gate (`ann_honours_scope`, `profile.name == "postgresql"`) | keep |

Not engine code, despite the word: every "oracle" in `src/vfs/native.py:7`, `pattern_matching/grep.py`, `models/signals.py`, `models/lexical.py`, `models/postings.py` means the pure-Python test oracles in `tests/support/oracles/` (READ). They stay.

---

## 2. Shared code shaped by a dropped engine's limit (the important findings)

### 2.1 Membership chunk size on SQLite and Postgres comes from their own profile and SQLAlchemy, not a shared floor (EXECUTED)

```
sqlite pysqlite   params 32700 membership 32668 arm1 200 arm4 200 depth 1000 relabel 50000
postgresql asyncpg params 32700 membership 32668 arm1 200 arm4 200 depth 1000 relabel 50000
sqlite aiosqlite  params 32700 membership 32668 arm1 200 arm4 200 depth 1000 relabel 50000
generic (32700)   membership 1000 arm1 200 arm8 125
mssql dialect insertmanyvalues_max_parameters 2099; oracle 32700; mysql 32700; DefaultDialect 32700
```

- `membership_budget = min(in_list_budget, parameter_budget - 32)` (dialects.py:767). On both kept engines the parameter budget binds: 32,700 − 32 = 32,668. Their own `in_list_budget` (SQLite 32,766, PG 65,535) never binds. So removing Oracle's 1,000 and SQL Server's 2,099 changes **no** chunk size on SQLite or Postgres.
- `parameter_budget` is SQLAlchemy's `insertmanyvalues_max_parameters` (engine.py:272-274), never a profile value.
- Relabel open-range chunks use `profile.in_list_budget` directly (labels.py:412, 425, 484): SQLite 32,766 and PG 65,535 pairs a statement, their own values.

### 2.2 `RELABEL_ROWS = 50_000` is one shared constant chosen across all five engines (READ dialects.py:97-99, 334-344)

"Measured on all five engines: 50,000 rows per statement ... was safe everywhere (the slowest, SQL Server at 38 µs a row, holds a chunk under two seconds); the value is the same on every profile because no engine measured a reason to differ." SQLite and PG get it from the shared default. Keep the value (behaviour unchanged); the justification must be rewritten without SQL Server, or the spec notes the bound was set by the slowest engine now dropped and is conservative for PG.

### 2.3 `BLOB_PAGE_BYTES = 8 MiB` (READ dialects.py:101-103)

Reason given is two-part: "the mysql family sends one statement as one packet, and every engine materialises the page in RAM". Used on SQLite/PG at writes.py:549, versions.py:92, 154, 206, render.py:388, topology.py:548, maintenance.py:453 (EXECUTED grep). The second reason stands; keep the value, reword.

### 2.4 `_PATTERN_ARM_CEILING = 200` (READ dialects.py:770-772)

"the win saturates by ~200 arms/statement, and 200 clears every known engine's bind, IN-list, and depth caps." Measured across the five engines; it is what SQLite and PG get for every glob/grep/search/rights OR-fan (EXECUTED: `arm1 200 arm4 200`). Keep; reword.

### 2.5 `_STATEMENT_BIND_RESERVE = 8` (READ dialects.py:809-811)

"driver wrappers (ODBC's sp_prepexec among them) spend from the same server cap". It is subtracted in `statement_budget` on every engine, SQLite and PG included. Keep the value (changing it changes chunk sizes); reword.

### 2.6 GENERIC's values, and where they come from (READ dialects.py:659-667; EXECUTED `profile_for('foo')`)

```
DialectProfile(name='foo', key_byte_budget=1700, in_list_budget=1000, arbitration='catch_retry',
  guard_miss='redrive', row_lock_hint=None, share_lock=ShareLock(form='exclusive', hint=None, door=False),
  membership='in_list', op_isolation=None, topology_isolation=None, session_settings=(), file_settings=(),
  retryable_sqlstates=frozenset({'40P01', '40001'}), retryable_sqlite_codes=frozenset(),
  retryable_driver_codes=frozenset(), expression_depth_budget=1000, values_join=False, tuple_in=False,
  like_bracket_class=False, content_bytes=False, bulk_insert='core', vector_distance='none', ...,
  range_source=None, range_join='JOIN', ..., relabel_rows=50000, vector_function=None, ..., stored_length='length')
```

Provenance by field:
- `key_byte_budget=1_700`: identical to MSSQL (565, SQL Server's 1,700-byte index key cap) and ORACLE (638). Copied from a dropped engine.
- `in_list_budget=1_000`: Oracle's ORA-01795 (comment 631-633; ORACLE 639). Copied from a dropped engine. Field docstring 175 says "Oracle's ORA-01795 at 1,000 is the generic floor".
- `arbitration="catch_retry"`: the mode MSSQL, MARIADB, ORACLE take; the portable fallback.
- `guard_miss="redrive"` (default 422): the mode only MARIADB declares among tuned profiles; GENERIC takes it as "never classify off a probe an unknown engine may contradict".
- `share_lock=ShareLock(form="exclusive")`: GENERIC's own.
- `expression_depth_budget=1_000`: SQLite's `SQLITE_MAX_EXPR_DEPTH` (docstring 183-187), shared default on every profile — not from a dropped engine.
- `retryable_sqlstates={"40001","40P01"}`: the standard plus Postgres's deadlock code.
- Everything else: the dataclass defaults.

Two of GENERIC's numbers therefore have only a dropped engine as their source. Behaviour of GENERIC must not change in this landing (decision), so the values stay; what changes is the stated reason ("the tightest caps vfs has met" rather than "the tightest known engine").

### 2.7 Statement shapes chosen for SQL Server that run unchanged on SQLite and Postgres

These stay to keep SQLite/PG statement text identical; only their comments change:
- embed.py:271-273: refusal probe keys spelled as `cast(literal(text), column.type)` "because SQL Server merge-joins the derived-table form ... and converts the column for a plain list". On PG this binds `CAST($n AS VARCHAR(64))` per key (INFERRED).
- trash.py:502-508: `CASE` in a value position instead of a predicate.
- indexing.py:521-528: `case((pending, 1), else_=0)` in the preamble select list.
- indexing.py:944-957: `_pending_probe` as row presence + `LIMIT 1` instead of `SELECT EXISTS`.
- pages.py:6-8: keyset pages rather than a streaming cursor (MARS); also justified by writes between pages.
- rows.py:834-835: `vfs_grants` surrogate key "inside SQL Server's clustered cap" (schema).
- rows.py:426-428: explicit `Identity()` "for Oracle" (schema; INFERRED removing it changes PG DDL).
- engine.py:723-724: the root's `name="/"` because Oracle folds `''` to NULL (data shape).
- rows.py:128-131: `version_number` column name because NUMBER is an Oracle reserved word (schema).
- grants.py:530-537: range bounds avoid "a path plus a low byte, which SQL Server would pad past and Postgres refuse" — the Postgres half stands.
- labels.py:37-47: the mint proof's two statements (watch + hold) is engine-neutral; only "three on Oracle" goes.

### 2.8 `key_byte_budget` never binds today (READ paths.py:41-42, 191-202; staging.py:227-237)

`MAX_PATH_LENGTH = 1024` bytes and `MAX_SEGMENT_LENGTH = 255`; every profile's `key_byte_budget` is ≥ 1,700 (SQLite 4,096, PG 2,704, GENERIC 1,700). `WritePlan.within_budget` therefore never refuses on any engine. paths.py:200-202 promises "a lawful path always fits under the tightest declared `key_byte_budget`" — after the drop the tightest declared is GENERIC's 1,700 (the copied SQL Server number). Keep; reword.

### 2.9 What happens to the dropped engines after the drop: they fall to GENERIC (INFERRED, with an EXECUTED compile)

`profile_for` serves any unknown dialect name (dialects.py:678-688), so a `mariadb://`, `mssql://` or `oracle://` URL keeps resolving — to GENERIC under its own name — and will draw the new warning. With the type variants removed (1.7), plain types compile on those dialects as (EXECUTED):

```
oracle BINARY(16) -> BINARY(16)       oracle DateTime(tz) -> DATE       oracle Text -> CLOB
mysql  String(1024) -> VARCHAR(1024)  mysql  Text -> TEXT               mysql LargeBinary -> BLOB
mssql  LargeBinary -> IMAGE           mssql  Text -> TEXT               mssql String -> VARCHAR (database collation)
```

INFERRED consequences: Oracle has no `BINARY` type, so provisioning fails; MySQL/MariaDB TEXT/BLOB cap at 64 KB and a unique utf8mb4 `VARCHAR(1024)` index exceeds InnoDB's 3,072-byte key cap, so provisioning likely fails; SQL Server mangles non-Latin text without `use_setinputsizes=False` and the UTF-8 collation. So "GENERIC, testing only" will in practice not run on the three dropped engines. Also note: **MySQL community is already served as GENERIC today and today gets the `_MYSQL_FAMILY` variants** (rows.py:172 includes `"mysql"`), so deleting them changes what an existing unknown dialect gets. Decision for the spec:
- (a) delete all three engines' type variants and error-code classification (smallest code; unknown MySQL-family/MSSQL/Oracle URLs fail at first touch), or
- (b) keep the driver-code classification (`_driver_code_of`, `_DRIVER_UNIQUE_CODES`, `_MSSQL_UNIQUE_NUMBERS`, pyodbc SQLSTATE arm) as GENERIC robustness, because GENERIC's `catch_retry` arbitration depends on `is_unique_violation` being right for the unknown driver, or
- (c) refuse the three dialect names explicitly instead of warning.
No test today runs the storage contract on GENERIC end to end (section 3.4), so none of this is proven either way.

### 2.10 Tests that use SQL Server's 2,099 bind budget to exercise tight chunking

After the drop no kept dialect has a small bind budget, so these lose their stress case and need a synthetic budget (the pattern already exists at test_dialects.py:541, `membership_budget(replace(GENERIC, in_list_budget=65_535), 2_099)`):
- tests/storage/database/test_search.py:571-584 (`compiled(MSSQL, mssql.dialect(), 8)`, `membership_budget(MSSQL, 2_099)`).
- tests/storage/database/test_reads.py:1176 (`mssql.dialect().insertmanyvalues_max_parameters`).
- tests/storage/database/test_grep.py:1441 (parametrized `[SQLITE, MSSQL]`), 1707 docstring "binds past SQL Server's 2,099 parameters".
- tests/storage/test_conformance.py:295-307 `TestMSSQLBindBudget` (live leg).

---

## 3. `tests/`

### 3.1 Engine selection

- tests/conftest.py:59-67 `ENGINE_URLS`: delete the `mariadb` (`VFS_TEST_MARIADB_URL`, `VFS_TEST_MYSQL_URL`), `mssql` (`VFS_TEST_MSSQL_URL`), `oracle` (`VFS_TEST_ORACLE_URL`) rows; module docstring 3-7 fine.
- pyproject.toml:160-162 markers `mariadb`, `mssql`, `oracle` — delete.
- tests/support/server_schemas.py: 16-18 docstring (MariaDB database, Oracle user), 44-52 `_DDL` rows for mssql/mariadb/mysql/oracle, 60-65 `ENGINE_LEGS` (3 of 4 rows go), 132-134 the mssql drop arm. Removing the three `ENGINE_LEGS` rows removes those legs from every parametrized user at once: test_races.py (54 references), test_engine, test_embed, test_labels, test_links, test_signals, test_writes, ranking/test_harness (EXECUTED grep).

### 3.2 Marker-scoped items (EXECUTED: AST script over `tests/`, decorators `pytest.mark.{mariadb,mssql,oracle}`)

TOTAL 339 lines in 37 items, plus 6 `pytest.param(..., marks=...)` rows.
- tests/storage/test_conformance.py: 36 items, 300 lines — `TestMariaDBConformance` 242-249, `TestMSSQLConformance` 252-259, `TestOracleConformance` 262-269, `TestMSSQLBindBudget` 295-307, `TestMSSQLMembershipForm` 310-351, `TestMSSQLTornRowRegression` 354-370, `Test{MariaDB,MSSQL,Oracle}TopologyRivals` 459-483, `TestMariaDBFlagFlipRoundTrips` 486-506, `TestMSSQLChunkGuardRegression` 509-533, `TestMariaDBTornRowRegression` 536-555, `Test{MySQL,MSSQL,Oracle}SegmentCascades` 610-625, `...EncodedKindIndex` 663-678, `test_a_directory_is_never_awaiting_the_index_on_{mariadb,mssql,oracle}` 719-734, `...LexicalFidelity` 749-764, `...RankingPin` 779-794, `...LexicalBuildBeyondAPage` 817-832, `...ContentBytesAudit` 866-886, `...BlobColumn` 918-949; plus the 3 param rows at 124-126.
- tests/storage/database/test_races.py: `TestGenerationRedirtyLockScope` 1348-1386 (mariadb). Also 77-81 `_SESSION_ID`/`_LOCK_WAIT` (mariadb/mssql only; their branch at 1232-1233, 1246-1247 and `_lock_waiting` 1711-1716 die), 512-516 `_EXPECTED` rows, 1026 comment, 2075 docstring, 2220 subset `("postgres","mariadb","oracle")` → `postgres`, 2343-2349 `test_the_mariadb_leg_runs_with_snapshot_isolation` (delete).

### 3.3 Compile-only tests against dropped dialects (no server needed; they run in every `uv run pytest`)

| File | Lines | What |
|---|---|---|
| tests/storage/database/test_dialects.py (1,146) | 79-101 `_MySQLError`, `_OracleErrorValue`, `_OracleError`; 145-147 pyodbc SQLSTATE; 174-182 MariaDB tuned / MySQL unknown; 184-196 range joins and hints; 198-202 relabel cap on every profile; 209-230 MySQL errnos, Oracle retry; 238-246 bracket escape; 248-259 content_bytes/values_join lists; 350-372 `_odbc`, unique violation; 386-419 `TestLockRows` (MSSQL hint, leak gate); 454-483 share-lock forms; 537-545 budgets; 906-934, 1025-1084 bulk insert per dialect (MSSQL identity, mode pins); 1087-1125 `TestValueTooLarge` MySQL arm, `TestValueCap`, `TestWireBytes`; many profile tuples like `(POSTGRESQL, MARIADB, MSSQL, ORACLE, GENERIC)` at 119-136, 194-201, 235-259, 1117 | ~250 lines delete/collapse |
| tests/models/test_rows.py (680) | 248-271 (Oracle/generic fallback, MySQL byte keys), 300-324 (fs-parent index per dialect), 468-494 (`ULIDKey` per dialect), 556-612 (LONGTEXT/LONGBLOB, sub-second instants, identity DDL, whole-family DDL on every dialect) | ~80 |
| tests/models/test_vector_native.py (99) | 35-99: native dialects set, DDL per engine, wire forms, cosine per dialect | ~60 (rewrite to PG/SQLite) |
| tests/storage/database/test_membership.py (119) | 56-74, 95-108: the MSSQL `VALUES` form and `UPDLOCK, FORCESEEK` | ~45 |
| tests/support/plan_store.py (973) | 18-19 docstring; 609-626 `_table_statistics` mariadb/mssql arms; 645-655 `_ulid_literal` oracle/mssql; 697-759 `_mariadb_*`, `_mssql_*`, `_oracle_*` plan readers; 776-779 seek sets; 850-948 `_mariadb_access`, `_mssql_access`, `_oracle_access`; 954-972 dispatch rows | ~180 |
| tests/support/storage_contract.py | 1539-1541, 1548-1550 plan regexes for mariadb/mssql/oracle; 1640 T-SQL bracket comment | ~8 |
| tests/test_plan_store.py | 43-75 (6 hits) | check |
| tests/storage/database/test_indexing.py | 20, 38 imports; 807 MSSQL `_pending_probe`; 1182-1184; 1294 comment; 1773 dialect loop; 2175-2177 | ~15 |
| tests/storage/database/test_topology.py | 18, 44-45 imports; 102-113 isolation pins (MSSQL, MariaDB); 146-148 lock spellings | ~12 |
| tests/storage/database/test_traverse.py | 17; 248-249 `INNER LOOP JOIN`, `STRAIGHT_JOIN` | 3 |
| tests/storage/database/test_grep.py | 20, 39; 1441; 1539-1549 compiler loops; 1707 | ~8 |
| tests/storage/database/test_search.py | 21, 47; 571-584; 1118 docstring | ~15 |
| tests/storage/database/test_coherence.py | 16, 30; 428-476 (guard_miss per profile, MariaDB via SQLite); 704; 1097, 1143 (mssql compile) | ~20 (note 442-476 use MARIADB as the redrive-mode profile over SQLite: re-point to GENERIC) |
| tests/storage/database/test_lexical.py | 13; 248; 445 docstring | 3 |
| tests/storage/database/test_labels.py | 92-104 relabel form per dialect | ~8 |
| tests/storage/database/test_ranges.py | 20; 132-141 `test_the_derived_hint_is_oracles_alone` | ~12 |
| tests/storage/database/test_edges.py | 22; 401 `(VALUES` on mssql | 2 |
| tests/storage/database/test_reads.py | 20; 1176 | 2 |
| tests/storage/database/test_drivers.py | 53-56 `test_a_sql_server_url_leaves_text_binds_as_unicode` | 4 |
| tests/storage/database/test_writes.py:527, test_trash.py:1224, test_engine.py:120 | comments/docstrings | reword |

Not dropped-engine code: `tests/support/oracles/*`, `tests/test_oracles.py`, `tests/test_native.py`, `tests/pattern_matching/*`, `tests/models/test_lexical.py`, `tests/storage/test_grants.py`, `tests/base/test_glob_namespace.py` — "oracle" there is the pure-Python reference implementation (READ). They stay.

### 3.4 How the GENERIC floor is tested today (READ)

No conformance class runs `StorageContract` under GENERIC. It is unit-level only, always over SQLite or a compiled dialect:
- `monkeypatch.setattr(EngineHost, "profile", property(lambda self: profile_for("duckdb")))` — test_engine.py:87 (durability trait).
- `monkeypatch.setattr(storage._host, "_profile", replace(GENERIC, name="exotic"))` — test_sqlite_vec.py:238 (search withheld, `cosine_distance("exotic")` refuses).
- `profile_for("duckdb")` / `profile_for("exotic")` / `profile_for("mysql")` values — test_dialects.py:106-108, 180-182, 417, 460; test_coherence.py:448.
- GENERIC passed directly to builders over SQLite sessions or compiled on `postgresql.dialect()` — test_indexing.py:1122, 1144, 2143; test_coherence.py:734, 780-784; test_ranges.py:175; test_grep.py:1550; test_labels, test_topology, test_traverse.
Both monkeypatch routes bypass `EngineHost._policy()`, so a warning emitted in `_policy()` would not fire in those tests (INFERRED); a new test needs a session bind whose dialect name is unknown.

### 3.5 `tests/lint/allowlist.py`

79-80 name `context/specifications/archive/011-mssql-...` and `012-mssql-...` — context-lint allowances for archived files, not engine code. No change (READ). `tests/lint/test_code_shape.py:302` forbids `--mssql` in `context/standards/testing.md` — unaffected.

---

## 4. Packaging and tooling

- pyproject.toml (READ): 56-58 extras `mssql = ["aioodbc>=0.5", "pyodbc>=5.0"]`, `mariadb = ["aiomysql>=0.2"]`, `oracle = ["oracledb>=2.0"]` — delete; 67 `all` drops `mssql,mariadb,oracle`; 160-162 markers. Core deps (34-42) and `postgres` extra (55) unchanged.
- uv.lock (EXECUTED via tomllib): packages that leave — `aioodbc` (only vfs-py), `pyodbc` (aioodbc, vfs-py), `aiomysql` (vfs-py), `pymysql` (aiomysql), `oracledb` (vfs-py), `cryptography` (oracledb only). `cffi`/`pycparser` stay (pyzmq). 177 lines of package blocks + ~15 lines in vfs-py's `dependencies`, `optional-dependencies` (mariadb/mssql/oracle) and `requires-dist`/`provides-extras` (3512-3630). Regenerate with `uv lock`.
- docker/compose.test.yml (126 lines): delete `mariadb` 50-72, `mssql` 74-105, `oracle` 107-126 (77 lines); header 3-19 reword (profiles, Rosetta). Postgres service 28-48 stays: `pgvector/pgvector:pg17`.
- docker/initdb: delete `mariadb/schema-rights.sql` (3) and `oracle/schema-rights.sql` (4); keep `postgres/01-vector.sql`.
- docker/README.md (110): about 70 lines of MariaDB/SQL Server/Oracle setup, ports, Rosetta, ODBC (e.g. 40-70) go.
- .github/workflows/test-dialects.yml (110): matrix rows 41-49 delete (one-row matrix or no matrix), "Install ODBC driver" 64-72 delete, comment 31-33 (runner pinned for the ODBC feed) and 79-81 (Oracle login lag) reword. `uv sync --extra ${{ matrix.dialect }}` keeps working for `postgres`.
- .github/workflows/test.yml:39 and lint.yml:38 use `--all-extras`: unchanged text; they stop installing pyodbc/oracledb/aiomysql (INFERRED: faster sync). publish.yml has no extra reference.
- scripts/: EXECUTED grep finds no engine name in any script. `scripts/ci.sh:62` uses `--all-extras` (unchanged).
- crates/: nothing engine-specific (EXECUTED).
- .claude/skills:
  - db_test/SKILL.md (205): description (3) and most of sections 2-4 (45, 53-59, 69, 82-89, 94-97, 109-122, 138-177) name MariaDB/MSSQL/Oracle, Rosetta, ODBC, phantom-container workaround for mssql; ~120 lines go; the skill becomes Postgres only.
  - code_review/SKILL.md:155 ("four real engines"), 175-176 (`uv sync --extra ... mariadb ... mssql ... oracle`); workflow_template.js:41-43 engine URLs (note 41 says `mariadb+aiomariadb`, which differs from every other place's `aiomysql`); check_workflow.py:28 `ENGINE_PORTS`.
  - scale_review/SKILL.md:3 (description "review for Oracle/SQL Server limits" appears in the skill listing), 21, 72-74 (engine floor check: "Oracle's 1,000-element IN-list cap is the GENERIC floor's in_list_budget; SQL Server's ~2,100 bind parameters bounds both membership chunks and bulk rows; key_byte_budget floors at 1,700").
  - spec_review/SKILL.md:111-112 (the floor "Oracle's 1,000-element IN list, SQL Server's ~2,100 binds").
  - test_suite/SKILL.md:16 ("Postgres/MariaDB/MSSQL/Oracle in Docker").
  - contract_review/SKILL.md:25 and verify_findings/SKILL.md:97 use MSSQL/Oracle as examples only — optional.

---

## 5. Prose

### 5.1 AGENTS.md (READ; quoted)

1. Production posture, "Never assume SQLite" (line 61): "Production runs on Postgres, SQL Server, Oracle, and other SQLAlchemy-compatible engines; SQLite is the dev/test default, not the target. ... The tightest known engine caps are the floor to design against (e.g. Oracle's 1,000-element `IN`-list limit, ORA-01795; SQL Server's ~2,100 bind parameters)." Also conflicts with the new stance that SQLite is core product (demos, local apps).
2. "No statement may grow unboundedly" (62): mechanism text (`in_list_budget`, `membership_budget`, `chunked()`) stays accurate; the "tightest of the two caps" framing may need the floor's new source.
3. "Unknown dialects are served the core verbs, never ranked search" (64): "**Every supported dialect has one**: native on Postgres/pgvector, MariaDB, SQL Server 2025 and Oracle 23ai; sqlite-vec on SQLite ... MySQL community has no distance function and no extension vfs can install, so it is not a supported dialect: a `mysql://` URL is served as an unknown one." Must name SQLite/Postgres only and add the testing-only warning.
4. Reference deployment table, Engines row (89): "| Engines | Postgres as the common case; SQL Server and Oracle at customer sites | the floors above, 1,000-element `IN` lists and about 2,100 bind parameters, are live constraints |".
5. Concurrency row (82) cites the label memo "which calls wait behind a posture change on each engine is measured in [the 2026-11-14 label memo]" — the memo is multi-engine context; the row itself can stay.
6. "How to use it", Per batch (96): "10,000 rows through chunked builders at the engine floor is already about ten statements per table touched" — the arithmetic is 10,000 / Oracle's 1,000. On Postgres the chunk is 32,668 (EXECUTED), so it is one statement.
7. Per lock, "The engine's own reader locks count" (102): "Where an engine makes a plain read wait on an uncommitted write (SQL Server with `READ_COMMITTED_SNAPSHOT` off) ... measured there, one open posture change held every call on the mount" — the example is a dropped engine; the rule can stay with a neutral example or none.
8. Per lock, table-lock rule (101): "A counted test then shows, on every server engine, ..." — still valid (Postgres).
9. Tooling, timeout rule (107): "an experiment run on the SQL Server leg hung with every thread blocked on a lock" — an anecdote; may stay as history or be reworded.
10. Commands (31-41) and Tooling "A bare `uv sync` ... strips the database drivers" (111): unchanged.
Line 113 "a test oracle" is the reference-implementation sense; no change.

### 5.2 Other prose (READ)

- README.md:145: "4,564 tests at 100% coverage, green on SQLite, Postgres, MariaDB, SQL Server and Oracle."
- CONTRIBUTING.md:85: "the real-engine legs (Postgres, MySQL, MSSQL, Oracle) run in Docker via the conformance suite."
- documentation/overview.md:121: "VFS supports Postgres, SQL Server, and Oracle so that most developers and most cloud deployments can adopt it with the database they already run."
- documentation/tutorials/keep-your-files-in-a-database.md:105: "VFS also runs on Postgres, SQL Server, and Oracle, where the URL names that database instead."
- documentation/explanation/why-vfs-stores-files-in-a-database.md:39: "In production it is Postgres, SQL Server, or Oracle, which most teams already operate."
- documentation/images/architecture.svg: a description string "SQLite locally or Postgres, SQL Server, or Oracle in the cloud" and a box label "Postgres, SQL Server, Oracle".
- documentation/maintainers/how-we-work.md:30, 44 say "the database engine legs" generically — no change.
- docs-app/: no engine names in `docs-app/src` or `docs-app/tests` (EXECUTED grep); its content comes from `documentation/` and the docstring export, so the docstring edits above flow through `scripts/docs.sh check`. INFERRED: `vfs.models.vector` is not an exported module, so `NATIVE_VECTOR_DIALECTS` is likely not on a docs page; `docs.sh check` would say.
- examples/search_walkthrough.ipynb: an output cell quotes "Oracle 26ai Free" from older research — optional.
- docs/index.md:19 "oracle" is the word, not the engine.
- agents/tasks.md:28 "Run the SQL Server leg." task (delete); 107 edit/row-lock task names Postgres/MariaDB/SQL Server/Oracle behaviour (reword); 23 mentions engine legs. agents/2026-11-20-write-takes-preconditions-and-an-append/spec.md:30, 41, 42, 278, 313, 390, 394 and agents/2026-11-18-*/ name the dropped engines (working material; update where still in flight).

### 5.3 `context/` cited by live files

- AGENTS.md cites `context/research/2026-11-09-what-an-enterprise-scale-deployment-looks-like.md` (the table's sources, which include the SQL Server/Oracle engine row) and `context/research/2026-11-14-a-mint-must-prove-its-label-against-a-posture-change-committed-inside-its-window.md` (per-engine lock measurements).
- AGENTS.md cites `context/standards/how-we-code.md` (3 engine mentions), `testing.md` (1), `tooling.md` (0), `landing.md` (3) (EXECUTED counts). `context/standards/roadmap.md` (31) and `mutant-ledger.md` (16) are not cited from AGENTS.md by name.
- tests/lint/allowlist.py:79-80 name two archived mssql specs (lint allowance only).
- 901 files under `context/` mention a dropped engine (EXECUTED); none take new work.

---

## 6. Where the GENERIC warning goes

- Resolution point (READ engine.py:563-583): `EngineHost._policy()` calls `profile_for(dialect.name)` once per host, lazily at first use, and caches `self._profile`. This is the natural site: one warning per mount, at the moment an unknown dialect is resolved to the floor, for both a URL-built engine and a borrowed `session_factory`. The membership test already used for durability (`self._host.profile.name in PROFILES`, backend.py:264-266) is the same check.
- Not `profile_for` itself: it is also called per bulk insert (dialects.py:914, `profile_for(dialect.name).bulk_insert`), so a warning there would repeat on every batch (Python's default filter dedupes per call site, but pytest records every one; INFERRED).
- Earlier alternative: `DatabaseStorage(url=...)` already parses the backend name at construction for `engine_arguments` (drivers.py:68, `make_url(url).get_backend_name()`), which would warn at construction — but a borrowed session factory has no URL, so `_policy()` is the only site that covers both.
- `warnings`/`logging` in `src/` today (EXECUTED grep): no `logging` import or logger anywhere in `src/`; one `warnings.warn` — sync.py:30 import, 69-72 `FOREIGN_LOOP_WARNING` constant, 691-700 `_warn_if_blocking_a_foreign_loop` (once per facade, guarded by `self._warned`, `RuntimeWarning`, `stacklevel=_caller_stacklevel()` from sync.py:1080). That is the house pattern to copy: a module constant for the text, a once-latch, an explicit category and stacklevel. There is no vfs logger on this branch.
- pytest config has no `filterwarnings` (READ pyproject.toml:148-163), so a new warning does not fail the suite; the tests that fake GENERIC bypass `_policy()` (3.4).

---

## 7. Minimum Postgres and pgvector versions

- No minimum Postgres server version is stated anywhere in code, docs, CI or skills (EXECUTED grep for `Postgres 1x`, `pg1x`, `server_version`, etc.). `server_version_info` is read only for SQLite's 3.46 statistics gate (engine.py:296-305).
- Tested version: Postgres 17 — `image: pgvector/pgvector:pg17` (docker/compose.test.yml:31), "Postgres 17 + pgvector" (docker/README.md:55); CI uses the same compose file (test-dialects.yml).
- Implicit floor (INFERRED from SQL vfs issues on PG): `SET LOCAL jit = off` (dialects.py:554) needs the `jit` setting, Postgres 11+; `ON CONFLICT` upsert (9.5+), `CREATE INDEX IF NOT EXISTS` (9.5+), multi-argument `unnest` (9.4+). So the effective floor is Postgres 11, untested below 17.
- pgvector: Python package `pgvector>=0.3` (pyproject.toml:55, 77). Extension: no minimum enforced; first touch only proves it exists and reads `extversion` (dialects.py:473, engine.py:597-600). The HNSW index DDL (rows.py:932-948, default `index_method="hnsw"`, rows.py vector.py:97) needs pgvector 0.5.0+ (INFERRED from pgvector history); `hnsw.iterative_scan` is gated on 0.8+ (backend.py:121-122, 651). `PGVECTOR_INDEX_MAX_DIMENSION = 2_000` (rows.py:153).

---

## 8. Things that look surprising

1. Removing Oracle's and SQL Server's caps changes no chunk size on SQLite or Postgres: both already chunk at 32,668 from SQLAlchemy's 32,700 parameter budget (EXECUTED). The "floor" lives only in GENERIC, whose two numbers (1,700 key bytes, 1,000 IN elements) are copied from SQL Server and Oracle.
2. The real shared-floor values that do reach SQLite/PG are `RELABEL_ROWS` (chosen across five engines, SQL Server the slowest), `BLOB_PAGE_BYTES` (half justified by the MySQL packet), `_STATEMENT_BIND_RESERVE` (ODBC's wrapper) and `_PATTERN_ARM_CEILING` (measured on five). All keep their values.
3. After the drop, `mariadb://`, `mssql://` and `oracle://` URLs still resolve — to GENERIC — and will likely fail at provisioning once the type variants go (Oracle has no `BINARY`, MySQL's 64 KB TEXT/BLOB and 3,072-byte key cap, SQL Server collation). MySQL community, already GENERIC, loses the variants it gets today.
4. GENERIC has no end-to-end conformance leg; it is unit-tested only, mostly by monkeypatching the profile over SQLite, which bypasses the place the warning would be emitted.
5. `vector_dimension_cap` and `ann_dimension_cap` are dead fields today on every profile (no reader).
6. `membership(target, keys, profile)` loses its only reason to take `profile`; about 100 call sites pass it.
7. `AGENTS.md`'s per-batch cost line ("about ten statements per table") is Oracle's 1,000-element arithmetic; on Postgres a 10,000-file batch is one membership statement.
8. code_review's workflow_template.js:41 names `mariadb+aiomariadb`, unlike every other URL (`aiomysql`); moot after the drop.
