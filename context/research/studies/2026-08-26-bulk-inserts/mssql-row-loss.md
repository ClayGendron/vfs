# SQL Server's silent row loss under `fast_executemany`, explained

- **Date:** 2026-08-26. **Spec:** 139 (fork: "fast_executemany only with
  the silent row loss explained and a per-table proof"). **ADR:** 056.
- **Question (Clay):** why did a 300-row bulk insert of NULL-free `entry`
  rows land only 203 rows, with no error and a committed transaction,
  when pyodbc's `fast_executemany` was armed on the bulk statement's own
  cursor — while 1,000 `lex_postings` rows landed 1,000? Which rows,
  deterministic or not, whose bug, and is there a safe form of the mode?
- **Method:** fourteen probe scripts under `prototype/mssql_row_loss/`
  (`run.sh` runs one; every outcome is a line in `results.jsonl`, 138
  lines) against the Docker SQL Server (`docker/compose.test.yml`,
  SQL Server 16.00.4265 under Rosetta, ODBC Driver 18.06.0002, pyodbc
  5.3.0, aioodbc 0.5.0, SQLAlchemy 2.0.52). The server's own view came
  from an Extended Events session on the probe's `@@SPID`
  (`rpc_completed`, `error_reported`, `attention`). No `src/` or
  `tests/` file was changed; the removed `"array"` mode was rebuilt in
  the scripts from the tree's own `_bulk_statement` / `_bulk_values`.
- **Docker's honesty:** counts, statement texts and server events are
  exact; the *number* of rows that land before the cancel (74–90) is a
  race and jitters run to run; microseconds are Rosetta microseconds —
  ratios carry, seconds do not.

## 1. The plain-language summary

The rows were not lost by the database. They were never run. Here is
the chain, one idea at a time.

The bulk statement was built by compiling a *one-row* insert. On SQL
Server, SQLAlchemy adds a clause to a one-row insert: `OUTPUT
inserted.id`. That clause makes the insert hand back the new row's
identity number. SQLAlchemy adds it so that a single insert can report
its primary key. So the statement we sent was not a plain insert; it was
an insert that returns one row of data per execution.

`fast_executemany` is pyodbc's "parameter array" mode. It hands the
whole batch of rows to the ODBC driver at once. The ODBC driver for SQL
Server does not have a true array insert; it sends one `sp_execute` call
per row, all in one stream. Because our statement returns data, each of
those executions produces its own small result set. The ODBC rule is
that the application must walk through those result sets one by one
(`SQLMoreResults`). pyodbc's fast path does not walk them — it returns
as soon as the first result arrives.

Then the cursor is closed. Closing a cursor with results still pending
means "discard them". To discard results that are still streaming, the
driver sends the server an *attention* — the cancel signal. The server
stops the batch where it is, logs "The statement has been terminated"
(message 3621, not an error to the client), and drops every execution
it had not yet run. Whatever had run before the cancel arrived stays in
the transaction, which then commits. That is why about 80 rows of every
page landed and the rest vanished, with no exception: a cancel is not an
error.

Block rows landed because `lex_postings` has no identity column, so no
`OUTPUT` clause, so no result sets, so nothing pending, so no cancel.
Remove the `OUTPUT` clause (compile the statement with `.inline()`) and
every row lands — 300, 1,000 and 5,000 — in the original async shape.

One line: **the array mode sent an insert that returns rows; pyodbc's
fast path leaves those rows unread; closing the cursor cancels the rest
of the batch; the fix is to compile the statement without `OUTPUT`.**

## 2. Reproduction

Every number is `landed / expected` for one run; "error" is what Python
saw; `rowcount` is `cursor.rowcount` after the call. Entry rows are the
spec-139 probe5 rows (twelve keys; Core's scalar defaults add `lines`,
`size_bytes`, `encoded`, `indexable` → 16 columns → the tree's page is
`2099 // 16 = 131` rows; 300 rows = pages of 131 + 131 + 38). Block rows
are the 7-column `lex_postings` rows (page 299).

### 2.1 The original shape — SQLAlchemy async `mssql+aioodbc`, listener arms the cursor

`before_cursor_execute` sets `cursor.fast_executemany = True` for every
executemany; rows go through `connection.exec_driver_sql(sql, tuples)`
with the statement compiled once by `_bulk_statement` (`rl_async_listener.py`).

| rows | page | landed | error | rowcount per call | missing |
|---|---|---|---|---|---|
| entry, null-free, 300 | 131 (tree) | **210**, **212**, **212**, **209** (four runs) | none | −1, −1, −1 | tail of page 1 (≈84–130) and tail of page 2 (≈216–261); the 38-row page 3 intact |
| entry, null-free, 300 | 1 | 300 | none | — | — |
| entry, null-free, 300 | 10 | 300 | none | −1 ×30 | — |
| entry, null-free, 300 | 50 | 300 | none | −1 ×6 | — |
| entry, null-free, 300 | 80 | 300 | none | −1 ×4 | — |
| entry, null-free, 300 | 100 | **263** | none | −1 ×3 | 81–99, 181–199, 281–299 |
| entry, null-free, 300 | 300 | **85** | none | −1 | 85–299 |
| entry, with NULLs, 300 | 131 | **211** | none | −1 ×3 | 88–130, 2xx–261 |
| block, 1,000 | 299 | 1,000 | none | −1 ×4 | — |

The earlier session's "203 of 300" is this row at page 131 on a
different day: ≈85 + ≈80 + 38.

### 2.2 Bare pyodbc, sync, with the server's own trace (`rl_bare_pyodbc.py`)

Same statement, same tuples, `cursor.fast_executemany = True;
cursor.executemany(sql, page); cursor.close()`, then `SELECT COUNT(*)`
on the same connection **before** commit and again after.

| page | landed | pre-commit count | error | `cursor.messages` | server: `attention` | server: `error_reported` |
|---|---|---|---|---|---|---|
| 1 | 300 | 300 | none | [] | 0 | 0 |
| 10 | 300 | 300 | none | [] | 0 | 0 |
| 50 | 300 | 300 | none | [] | 0 | 0 |
| 80 | **295** | 295 | none | [] | 3 | 1 × 3621 "The statement has been terminated." |
| 100 | **243** | 243 | none | [] | 3 | 1 × 3621 |
| 131 | **198**, **195** | 198 | none | [] | 2 | 1 × 3621 |
| 300 | **81** | 81 | none | [] | 1 | 1 × 3621 |

So: SQLAlchemy and aioodbc are not in the loop — bare pyodbc loses the
same rows. The rows are absent *before* commit, so nothing was rolled
back; they never executed. The server's RPC log shows the driver's
shape: one `sp_describe_undeclared_parameters`, one `sp_prepare`, then
one **`sp_execute` per row**, then `sp_unprepare`. In every losing run
the count of completed `sp_execute` calls is `landed + 1` — the one the
attention terminated — and no other error is reported.

### 2.3 The mechanism, isolated (`rl_mechanism.py`, bare pyodbc, 300 entry rows in one call)

| after `executemany` | landed | pending results found by `nextset()` | server `attention` | seconds |
|---|---|---|---|---|
| `cursor.close()` (what pyodbc and SQLAlchemy do) | **85** | — | 1 | 0.016 |
| drain: `while cursor.nextset(): pass`, then close | **300** | **299** | 0 | 0.016 |
| `time.sleep(1.5)`, then close | **300** | — | 1 (arrives after the batch finished; nothing left to cancel) | 0.014 |
| never close; `connection.commit()` directly | **76** | — | 1 (the next wire operation discards the pending results) | 0.014 |
| `fast_executemany = False` (row-at-a-time) | 300 | — | 0 | 0.247 |
| block rows, 1,000 in pages of 299, close | 1,000 | **0** | 0 | 0.017 |
| block rows, 1,000 in one call, close | 1,000 | — | 0 | 0.039 |
| entry with NULLs, page 131, close | **198** | — | 2 | 0.014 |

Three readings: (a) every lost row is *behind* the pending results —
draining them lands everything; (b) it is a race — sleeping before the
close lets the server finish, so the same cancel arrives with nothing
left to kill; (c) block rows leave nothing pending, which is why they
never lose.

### 2.4 What makes entry rows leave results pending — the bisect

- **Nineteen plain tables** (`rl_bisect.py`: INT IDENTITY PK, VARCHAR PK,
  heap, BINARY(16), DATETIME/DATETIME2 as object and string, BIT,
  BIGINT, UTF-8 collated VARCHAR(1024), NVARCHAR, sixteen INT columns,
  three VARCHARs, identity + UNIQUE, bytes vs bytearray, VARBINARY): all
  300/300, zero pending. (Aside: a `'YYYY-MM-DD HH:MM:SS.ffffff'` string
  into DATETIME raises "String data, right truncation" — loudly, not
  silently.)
- **Fourteen DDL variants of the real entry table** with a hand-written
  9-column `INSERT ... VALUES (?, …)` (`rl_bisect3.py`: with all eight
  indexes, no indexes, no identity, INT identity, no UNIQUE(parent_id,
  name), BITs as INT, no UTF-8 collations, only the inserted columns…):
  all 300/300, zero pending — **including the exact `create_all` DDL
  plus every index**.
- **Inside the real table with the tree's compiled statement**
  (`rl_bisect2.py`): full 12 keys → 86 landed, 299 pending; no datetime
  keys → 86, 299 pending; only the four required keys → 82 landed.
  Column *types* are not it.
- **The two remaining differences** (`rl_bisect4.py`): Core's compiled
  SQL vs hand SQL, and Core's `bytearray` vs `bytes` for the ULID:

| statement | ULID as | landed on close | pending on drain |
|---|---|---|---|
| Core-compiled (`… OUTPUT inserted.id VALUES (?, …)`) | bytearray | **86** | 299 |
| Core-compiled | bytes | **75** | 299 |
| Core-compiled, BITs as `bool` | bytes | **87** | 299 |
| hand-written (no `OUTPUT`) | bytearray | 300 | 0 |
| hand-written | bytes | 300 | 0 |
| hand-written, BITs as `bool` | bytes | 300 | 0 |

The compiled text is
`INSERT INTO t (entry_id, path, name, kind, lines, size_bytes, chunked, encoded, indexable) OUTPUT inserted.id VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`.
The `OUTPUT inserted.id` is the whole difference. `lex_postings` has no
IDENTITY column, so its compiled statement carries no `OUTPUT`
(`rl_compile_check.py` prints both).

### 2.5 Where `OUTPUT` comes from (`rl_compile_check.py`, no database)

`insert(entry).values({name: bindparam(name) …}).compile(dialect=d)` —
exactly what `_bulk_statement` does — renders the dialect's *implicit
returning* for a table whose `implicit_returning` is the default `True`
and whose PK is an IDENTITY/serial:

| dialect | plain compile | `.inline()` | `compile(for_executemany=True)` |
|---|---|---|---|
| sqlite | — (uses `lastrowid`, `favor_returning_over_lastrowid=False`) | — | — |
| mysql | — (no `insert_returning`) | — | — |
| postgresql | `RETURNING cc.id` | — | — |
| **mssql** | **`OUTPUT inserted.id`** (`favor_returning_over_lastrowid=True`) | — | — |
| oracle | `RETURNING cc.id INTO :ret_0` | — | — |

Core's own executemany compiles with `for_executemany=True`, which drops
the clause — so SQLAlchemy's documented `create_engine(…,
fast_executemany=True)` path never sends `OUTPUT` to a parameter array.
The array mode's docstring promised "exactly the values Core would have
sent"; the statement *text* was not what Core would have sent. In the
live tree this is latent, not active: sqlite and MySQL (the two
`"driver"` dialects) render nothing, Postgres's `"copy"` mode uses only
`statement.names`, and SQL Server and Oracle are pinned `"core"`.

### 2.6 The safe forms (`rl_safe.py`)

| form | 300 | 1,000 | 5,000 | statement tail |
|---|---|---|---|---|
| bare pyodbc, `.inline()`-compiled statement, one call | 300 | 1,000 | — | `… deleted_at) VALUES` |
| SQLAlchemy sync `mssql+pyodbc`, `create_engine(fast_executemany=True)`, `conn.execute(insert(entry), rows)`, `use_setinputsizes` False and True | 300 | 1,000 | — | no `OUTPUT` (executemany compile) |
| SQLAlchemy async `mssql+aioodbc`, `create_async_engine(fast_executemany=True)`, same | 300 | 1,000 | — | no `OUTPUT` |
| **the original listener shape with the `.inline()` statement, paged at 131** | **300** | **1,000** | **5,000** | `… deleted_at) VALUES` |

TDS packet size does not move the loss point (`SQL_ATTR_PACKET_SIZE`
4096 → 85 landed; 8192 → 82; 16384 → 82; 32767 → 82 of 1,000 in one
call). `SET NOCOUNT ON` does not either (77). Neither was expected to —
the pending items are result sets, not row-count messages.

### 2.7 Errors inside a batch, and `VARCHAR(max)` (`rl_midbatch.py`, `rl_midbatch2.py`)

One row of 300 duplicates another row's unique `path`:

| statement | duplicate at row | on close | on drain |
|---|---|---|---|
| with `OUTPUT` | 0 | **74 landed, no error** | 77 landed, `IntegrityError` raised by `nextset()` |
| with `OUTPUT` | 150 | **81 landed, no error** | 222 landed, `IntegrityError` on the 150th `nextset()` |
| with `OUTPUT` | 299 | 84 landed, no error | — |
| `.inline()` (no `OUTPUT`) | 0 / 150 / 299 | **`IntegrityError` raised**, 299 landed | same |

So with a result-set-per-row statement, even the *error* is a pending
result and is dropped with the rest. Without result sets the driver
returns `SQL_ERROR` from `SQLExecute` and pyodbc raises. Note the
semantics of the raise: SQL Server executed the other 299 sets ("it is
data source-specific whether all rows except the error set are
executed"); the call is not atomic the way Core's multirow `VALUES`
statement is — the enclosing transaction's rollback is what makes the
batch all-or-nothing.

The `content` table (`VARCHAR(max)` body, data-at-execution territory):
300 rows of 20 KB plus one of 400 KB through the inline statement →
300/300, 6,380,000 characters, no error.

## 3. The mechanism, with sources

1. **The driver executes a parameter array as one execution per set, and
   declares per-set results.** `SQLGetInfo` on the live connection
   returns `SQL_PARAM_ARRAY_ROW_COUNTS = SQL_PARC_BATCH` and
   `SQL_PARAM_ARRAY_SELECTS = SQL_PAS_BATCH` (`rl_driverinfo.py`) — "a
   result set is available for each set of parameters" — and the ODBC
   reference says drivers may "simulate it by executing a SQL statement
   multiple times, each with a single set of parameters"
   ([Using Arrays of Parameters](https://learn.microsoft.com/en-us/sql/odbc/reference/develop-app/using-arrays-of-parameters?view=sql-server-ver17)).
   The Extended Events log shows exactly that: `sp_prepare` once,
   `sp_execute` per row. [SQLMoreResults](https://learn.microsoft.com/en-us/sql/odbc/reference/syntax/sqlmoreresults-function?view=sql-server-ver16)
   is how an application steps through the per-set results.
2. **pyodbc's fast path does not step through them.** In
   [`src/params.cpp`](https://raw.githubusercontent.com/mkleehammer/pyodbc/master/src/params.cpp)
   `ExecuteMulti` sets `SQL_ATTR_PARAMSET_SIZE`, calls `SQLExecute`,
   raises only when `!SQL_SUCCEEDED(rc) && rc != SQL_NEED_DATA && rc !=
   SQL_NO_DATA`, collects diagnostics on `SQL_SUCCESS_WITH_INFO`
   (`GetDiagRecs`, no raise), services data-at-execution parameters, and
   returns. It never calls `SQLMoreResults`, never sets
   `SQL_ATTR_PARAM_STATUS_PTR` or `SQL_ATTR_PARAMS_PROCESSED_PTR`, and
   consumes no result set. In [`src/cursor.cpp`](https://raw.githubusercontent.com/mkleehammer/pyodbc/master/src/cursor.cpp)
   `Cursor_executemany` sets `cursor->rowcount = -1` and returns `None`
   (which is why `rowcount` is −1 in every table above and cannot serve
   as a guard). The wiki's
   [fast_executemany notes](https://github.com/mkleehammer/pyodbc/wiki/Features-beyond-the-DB-API)
   mention memory and Microsoft-driver-only; nothing about result sets.
3. **Closing the cursor discards pending results by cancelling.**
   pyodbc's `free_results` / close issue `SQLFreeStmt(hstmt, SQL_CLOSE)`,
   which "closes the cursor … and discards all pending results"
   ([SQLFreeStmt](https://learn.microsoft.com/en-us/sql/odbc/reference/syntax/sqlfreestmt-function?view=sql-server-ver17)).
   With results still on the wire, the driver discards them by sending
   a TDS attention; the server's log shows `attention` followed by 3621
   "The statement has been terminated." (severity 10 — informational)
   in every losing run and in none of the intact ones. The un-run
   `sp_execute` calls are simply gone. Waiting 1.5 s before the close
   (§2.3) lands all 300: same cancel, nothing left to cancel.
4. **Which rows, and why the number wobbles.** Deterministic in *shape*
   (the tail of every page whose response stream outran what the driver
   had already buffered — pages of ≤ 80 entry rows never lose, pages of
   ≥ 100 lose everything past ≈ 80), nondeterministic in *count* (74–90
   across runs) because it is a race between the server executing the
   stream and the attention arriving. Row content is irrelevant: string
   lengths, datetimes with microseconds and offsets, NULLs, `bytearray`
   vs `bytes` all made no difference.
5. **Prior reports of the same loss.** pyodbc
   [#1053](https://github.com/mkleehammer/pyodbc/issues/1053)
   ("fast_execute many stops after x inserts": a procedure that `SELECT`s
   `SCOPE_IDENTITY()` — a result set per set — lands 900–1,100 of 1,500
   with no error; closed as not planned) and
   [#665](https://github.com/mkleehammer/pyodbc/issues/665) ("Silent
   failures when using fast_executemany": a later set fails inside a
   procedure, the earlier set commits, nothing is raised — the
   `SQL_SUCCESS_WITH_INFO` swallow in `ExecuteMulti`, hypothesis 1 of
   this study, which our §2.7 shows is real when the statement returns
   result sets and moot when it does not). SQLAlchemy's
   [2.0.49 changelog](https://docs.sqlalchemy.org/en/20/changelog/changelog_20.html)
   (#13152) only exposes the attribute through aioodbc; the adapter in
   `sqlalchemy/connectors/aioodbc.py` proxies `fast_executemany` to the
   pyodbc cursor and aioodbc's `Cursor.executemany` runs
   `pyodbc.Cursor.executemany` in a thread — a pass-through, not a
   participant. [`Insert.inline()`](https://docs.sqlalchemy.org/en/20/core/dml.html)
   is documented as the switch: "for backends that support 'returning',
   this turns off the 'implicit returning' feature for the statement."

**Whose bug.** Ours first: `_bulk_statement` compiled a single-row
insert and so inherited SQL Server's implicit `OUTPUT inserted.id`, a
statement Core never sends to executemany. pyodbc second: its fast path
cannot safely run any statement that returns rows per parameter set —
it neither drains them nor warns, and its issue tracker has carried
that since 2019. The driver and the server behave as the ODBC reference
says they should. SQLAlchemy's aioodbc adapter is innocent, and
`use_setinputsizes` is irrelevant (both settings land every row in
§2.6).

## 4. The hypotheses, scored

| # | hypothesis | verdict |
|---|---|---|
| 1 | per-row ODBC errors swallowed as `SQL_SUCCESS_WITH_INFO` | Real in pyodbc (`GetDiagRecs`, no raise) but **not this loss**: `cursor.messages` was empty in every losing run, the server reported no error but 3621, and a duplicate-key row under the inline statement *does* raise. |
| 2 | sub-batching inside pyodbc | **No.** `ExecuteMulti` sizes one array per call; the loss point (~80 rows) is the driver/server stream, and it does not move with page size (only whether a page exceeds it) or TDS packet size. |
| 3 | the async adapter | **No.** Bare pyodbc reproduces it byte for byte; SQLAlchemy's documented `fast_executemany=True` engines (sync and async) land every row because their executemany compile carries no `OUTPUT`. |
| 4 | transaction / commit interplay | **No.** Pre-commit and post-commit counts agree; the rows never executed; a single connection and transaction throughout. |
| 5 | which rows | The tail of each page past ≈ 80 rows; the count is a race (74–90); content-independent. |
| 6 | NULL-bearing rows / larger block batches | NULL rows lose identically (198–211 of 300 at page 131). Block rows never lose (1,000 in pages of 299 and in one call), because their statement returns nothing. |
| — | (added) column types — datetimes as strings, `bytearray`, BIT, UTF-8 collations, IDENTITY, unique indexes | **No.** Nineteen plain tables and fourteen DDL variants of the real table, all 300/300 with a hand-written statement. |
| — | (added) the implicit `OUTPUT inserted.id` clause | **Yes.** The one difference between the losing and the intact statement (§2.4); `.inline()` removes it and the original shape lands 5,000/5,000. |

## 5. The fork: is there a safe form, and what would it cost?

**A safe form exists.** Compile the bulk statement with `.inline()` (or
`for_executemany=True`), so it returns nothing per parameter set, and
arm `fast_executemany` on that statement's cursor only. In the original
async listener shape that landed 300, 1,000 and 5,000 entry rows;
mid-batch constraint violations raise `IntegrityError`; `VARCHAR(max)`
bodies land. The proof the fork asked for would be:

1. a compile-time pin, no server needed: `_bulk_statement`'s text
   carries no `OUTPUT`/`RETURNING` on any dialect (the `.inline()`
   compile is cheap hardening for the live `"driver"` dialects too, even
   though sqlite and MySQL render nothing today);
2. a per-table landing test on the SQL Server leg for every bulk table
   (`entry`, `content`, `versions`, `chunks`, `lex_*`, `posting_list`,
   `segments`): `count == len(rows)` after the call, at ≥ 300 rows per
   page — 80 is the line, so a 131-row page is above it and the test
   would have caught this;
3. a mid-batch failure test: the raise, and the rollback of the whole
   transaction (the driver call itself is not atomic).

What is **not** available as a guard: `cursor.rowcount` (pyodbc pins it
to −1 under `fast_executemany`), `cursor.messages` (empty — a cancel is
not a diagnostic), and draining `nextset()` from inside SQLAlchemy
(`exec_driver_sql` closes the cursor before a caller could).

**What it would buy.** Less than the spec's number suggests for the
table that matters. The 31 µs/row vs 41 (Core with `fast_executemany`)
vs 86 (Core plain) was measured on `lex_postings` — seven narrow
columns, no identity, no `OUTPUT` — and stands. On 4,000 entry rows
(`rl_timing.py`, aioodbc, three repetitions after warm-up):

| shape | µs/row |
|---|---|
| Core `"core"` mode as pinned (multirow `VALUES` pages, no fast path) | 88–99 |
| Core on an engine created with `fast_executemany=True` | 85–100 |
| array mode, `.inline()`, paged at the tree's 131 rows/call | 126–137 |
| array mode, `.inline()`, all 4,000 rows in one call | 80–88 |

SQL Server's "fast" executemany is still one `sp_execute` RPC per row
plus one `sp_prepare` per call; Core's multirow `VALUES` is one RPC per
131 rows. Paged as the tree pages, the array mode is *slower* on entry
rows; unpaged it is a wash. The win the spec measured is real only for
narrow rows in big single calls — and the parameter-budget paging that
keeps Oracle and SQL Server statements bounded is exactly what erases
it here. Engine-wide `fast_executemany` (SQLAlchemy's documented switch)
stays refused for the reason the spec recorded: it rewrites every
UPDATE executemany's rowcount to −1, which the guarded bumps verify.

**Reading it honestly.** The mode is not unsafe by construction; it was
unsafe by *our* construction — a statement with an implicit `OUTPUT`
fed to a driver path that cannot carry result sets. The fix is one
method call and one test. But the fixed mode buys SQL Server nothing on
the entry table and about 10 µs/row on block rows over Core-with-fast
(which is itself refused engine-wide), at the price of a per-statement
arming listener, a non-atomic driver call, and a per-table proof on a
leg that runs under Rosetta. The pin `bulk_insert="core"` for SQL Server
is the right call today; the fork can be reopened with this memo's
three-part proof when a measured SQL Server workload wants it.

## 6. What remains unexplained

- **Why ≈ 80.** The loss point is stable at 74–90 entry rows regardless
  of page size above it and of TDS packet size (4 KB–32 KB), so it is
  not "one packet of responses". It is some buffer between the server's
  send side and the driver's receive side that the first `SQLExecute`
  return drains; we did not find its name. It does not matter to the
  verdict: any page above it loses, and the fix removes the pending
  results altogether.
- **Whether the driver ever returns `SQL_SUCCESS_WITH_INFO` here.** With
  the inline statement a bad row raised; with `OUTPUT` the error was a
  pending result. We never observed the parameter-status path pyodbc
  ignores, so #665's shape (a procedure) may still be a separate way to
  lose an error silently even without result sets. A future proof should
  include a procedure-free check that a *later* set's failure raises —
  §2.7 covers rows 0, 150 and 299 for plain inserts and it did.

## Sources

- Probe scripts and every recorded outcome: `prototype/mssql_row_loss/`
  (`rl_*.py`, `run.sh`, `results.jsonl`), run 2026-08-26/27 against
  `docker/compose.test.yml`'s SQL Server (16.00.4265), ODBC Driver 18
  (18.06.0002), pyodbc 5.3.0, aioodbc 0.5.0, SQLAlchemy 2.0.52.
- Microsoft ODBC reference: [Using Arrays of Parameters](https://learn.microsoft.com/en-us/sql/odbc/reference/develop-app/using-arrays-of-parameters?view=sql-server-ver17),
  [SQLMoreResults](https://learn.microsoft.com/en-us/sql/odbc/reference/syntax/sqlmoreresults-function?view=sql-server-ver16),
  [SQLFreeStmt](https://learn.microsoft.com/en-us/sql/odbc/reference/syntax/sqlfreestmt-function?view=sql-server-ver17).
- pyodbc: [`src/params.cpp`](https://raw.githubusercontent.com/mkleehammer/pyodbc/master/src/params.cpp)
  (`ExecuteMulti`), [`src/cursor.cpp`](https://raw.githubusercontent.com/mkleehammer/pyodbc/master/src/cursor.cpp)
  (`Cursor_executemany`, `free_results`), the wiki's
  [Features beyond the DB API](https://github.com/mkleehammer/pyodbc/wiki/Features-beyond-the-DB-API),
  issues [#1053](https://github.com/mkleehammer/pyodbc/issues/1053) and
  [#665](https://github.com/mkleehammer/pyodbc/issues/665).
- SQLAlchemy: [Core DML — `Insert.inline()`](https://docs.sqlalchemy.org/en/20/core/dml.html),
  [2.0 changelog](https://docs.sqlalchemy.org/en/20/changelog/changelog_20.html)
  (2.0.49, #13152), and in the venv `sqlalchemy/connectors/aioodbc.py`,
  `sqlalchemy/connectors/asyncio.py`, `sqlalchemy/dialects/mssql/pyodbc.py`
  (`do_executemany` sets `cursor.fast_executemany` when the engine flag
  is on; `use_insertmanyvalues_wo_returning = False` under it).
