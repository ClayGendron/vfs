# Online verification of the per-dialect bulk-insert pins

- **Date:** 2026-08-26. Produced by a research subagent from official
  docs, driver and SQLAlchemy source on GitHub `main`, and issue
  trackers — no local code read, no code run. Its twin, the adversarial
  pass, is `review-refute.md`. What the two changed in ADR 056 and spec
  139 is listed at the end.

## 1. sqlite / aiosqlite → "driver" — VERIFIED (result), mechanism corrected

`sqlite3.executemany` prepares once and runs bind → step → reset per
row inside the C loop (CPython `Modules/_sqlite/cursor.c`); aiosqlite
runs the whole call as one job in its worker thread. **Correction:**
Core does not use insertmanyvalues pages for a non-RETURNING INSERT on
sqlite (`use_insertmanyvalues_wo_returning` is `False` there), so the
6.7 µs/row Core number is *also* `sqlite3.executemany` — the 3.5× gap
is Core's per-row compiled-parameter processing, nothing else. Paging
by the parameter budget is harmless but not the binding constraint in
driver mode (each statement carries one row).

## 2. PostgreSQL / asyncpg → "copy" — VERIFIED, two integration risks

asyncpg `executemany` pipelines one Bind/Execute per row with a single
Sync (atomic since 0.22); maintainers point bulk users to COPY
(asyncpg #123, RFC #289). `copy_records_to_table` is binary-format
COPY. Core on asyncpg *does* page multirow statements without
RETURNING (`use_insertmanyvalues_wo_returning = True`), consistent
with 9.1 vs 11–24 µs. COPY fires triggers and enforces constraints,
does not fire rules, is not supported on RLS-enabled tables, applies
defaults for omitted columns (PostgreSQL `COPY` docs).

- **Risk A — the transaction may not have started.** SQLAlchemy's
  asyncpg adapter starts the driver transaction lazily on the first
  cursor execute (`_prepare_and_execute`: `if _transaction is None:
  _start_transaction()`); `DefaultDialect.do_begin` is a no-op. A raw
  COPY as the first operation runs in autocommit and a later rollback
  does not undo it. → `bulk_insert` issues a statement on the
  connection before the raw COPY.
- **Risk B — codecs.** Binary COPY needs binary encoders; text-format
  `set_type_codec` registrations break it (asyncpg #762, #783).
  SQLAlchemy registers json/jsonb binary codecs; `inet`/`cidr` text
  codecs when native inet is off. Every column needs a Python value
  the binary codec accepts. → the processed values are Core's own bind
  output; vfs's tables carry no json/inet columns.

## 3. MySQL / aiomysql — VERIFIED that the modes converge

aiomysql `executemany` matches `RE_INSERT_VALUES` and concatenates
rows into one statement up to `max_stmt_length = 1,024,000` bytes,
flushing when exceeded; non-matching statements fall back to a per-row
loop (aiomysql `cursors.py`, same design in PyMySQL). Core does not
page a non-RETURNING MySQL INSERT (no `use_insertmanyvalues_wo_returning`),
so both modes land in the same client-side rewrite; 44 vs 51 µs is
Core's per-row processing only. Caveat: the rendered INSERT must end
with `VALUES (…) [ON DUPLICATE …]` and carry only placeholders, or the
driver silently degrades to one execute per row.

## 4. SQL Server / aioodbc → "core" — reason CONTRADICTED, conclusion held

`AsyncAdapt_aioodbc_cursor` **does** expose `fast_executemany` since
SQLAlchemy 2.0.49 (#13152; the repo was on 2.0.46 when the attribute
was missing). Independently, plain pyodbc `executemany` is "essentially
equivalent to" repeated `execute()` (pyodbc wiki); `MSDialect` honours
both the 2,100-parameter and 1,000-row `VALUES` caps
(`insertmanyvalues_max_parameters = 2100`, `insertmanyvalues_page_size
= 1000`). `fast_executemany=True` flips
`use_insertmanyvalues_wo_returning = False` — it *replaces* multirow
pages with parameter-array executemany, a different trade-off, with
known hazards on `(max)` columns (pyodbc #867, #802; sqlalchemy #5334).

## 5. Oracle / python-oracledb → PARTIALLY VERIFIED; a real driver-mode bug

Large `bytes` bind fine without setinputsizes: `bytes` → `DB_TYPE_RAW`,
`max_size = len(value)`, thin mode writes binds over
`caps.max_string_size` after the short ones (the ORA-24816 avoidance);
LOBs up to 1 GB as bytes (LOB guide). **Bug:** without `setinputsizes`,
python-oracledb binds `datetime.datetime` as DATE and "does not examine
the value to determine if any fractional seconds are present"
(cx_Oracle #161) — Core sets `TIMESTAMP`; driver mode silently
truncates microseconds. SQLAlchemy's oracle dialect uses
`bind_typing = SETINPUTSIZES` for DATETIME/TIMESTAMP/NVARCHAR/RAW/int/
float, all of which `exec_driver_sql` skips. → Oracle pins `"core"`
(179 engine-leg failures under `"driver"` confirmed it).

## 6. Parameter-limit guard — PARTIALLY VERIFIED

sqlite `SQLITE_MAX_VARIABLE_NUMBER` 999 before 3.32, 32,766 after
(irrelevant to per-row executemany); MySQL: the driver splits at
1,024,000 bytes, far under the 64 MB server default — the unguarded
case is one row over `max_allowed_packet`; SQL Server: 2,100
parameters per request and 1,000 rows per `VALUES`, both covered by
the dialect defaults in core mode; PostgreSQL: Bind message parameter
count is `Int16` (65,535) for Core pages, no limit for COPY; Oracle:
no documented array-DML row cap, `batch_size` exists (3.4.0).

## 7. What `exec_driver_sql` skips — VERIFIED, two additions

`_init_statement` applies no bind processors and never calls
`setinputsizes` (`is_text`), and never runs `_process_execute_defaults`.
`before_cursor_execute` events and `do_executemany` hooks still run.
**Additions:** SQL-expression defaults (`default=func.now()`) and
`Sequence` defaults must be refused alongside callables; compile the
INSERT with the target dialect so paramstyle escaping is applied.

## Net corrections taken

1. ADR 056 context reworded: on sqlite and MySQL, Core's path is
   already `cursor.executemany`; the gap is Core's per-row processing.
2. SQL Server: `fast_executemany` measured after upgrading SQLAlchemy
   to 2.0.52 (see `bulk-inserts.md`), the pin decided by that number.
3. `bulk_insert` copy mode issues a statement before the raw COPY and
   translates driver errors by SQLSTATE class (23 → `IntegrityError`).
4. Oracle pinned `"core"`; the microsecond truncation is the recorded
   reason.
5. Only scalar Python-side defaults are filled; callable, SQL-expression
   and `Sequence` defaults are refused.
