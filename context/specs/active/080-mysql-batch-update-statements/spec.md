# 080 — MySQL-family batch updates go set-based, not per-row

- **Status: researched 2026-08-25** — slice A delivered as
  `../../../research/2026-08-25-mysql-family-batch-update-shapes.md`: the four research questions answered live on MySQL 8.4 and MariaDB 11.4 — FOUND_ROWS pinned as the semantic SQLAlchemy always sets, the UNION ALL derived-table multi-table UPDATE as the family's one join shape (3.8–4.1× the per-row loop at 10k), savepoint-and-redrive attribution proven, the MariaDB leg green at parity. Design (slice B) waits on
  Clay's review of the memo.
- **Status:** draft 2026-07-23 — research first; no implementation
  until the preconditions below are verified on real engines.
- **Evidence:** `context/open-questions.md` — "MySQL-family batch
  UPDATEs are per-row driver round trips" (multi-agent review of the
  spec 079 landing; scale lens, CONFIRMED 3/3, executed repro against
  the aiomysql/pymysql executemany gate).
- **Depends on:** spec 079 (statement-attributed guarded updates) —
  this spec changes only *which statements* the mysql-family arm runs,
  never the attribution doctrine 079 pinned.

## Problem

The mysql-family drivers (pymysql, aiomysql, asyncmy) batch
`executemany` only for INSERT/REPLACE (`RE_INSERT_VALUES`); an UPDATE
falls back to a per-row `execute()` loop, and SQLAlchemy's
insertmanyvalues rewrite is INSERT-only. On mysql/mariadb the guarded
aggregate arm and the unguarded absorb executemany therefore cost one
driver round trip per staged row: a 10,000-entry overwrite batch —
the supported ETL contract — is ~10,000 sequential UPDATEs inside one
REPEATABLE READ transaction. Results stay correct and statement size
stays bounded; the defect is cost and lock-window width (the batch
holds row locks for the loop's duration, widening the 1205/1213
retry window whose classification restarts the whole method).
Postgres/MSSQL (VALUES-join RETURNING arm) and oracledb (true array
DML) are unaffected. plan.md's "a clean N-row overwrite batch is one
executemany regardless of N" is false on this family; its own
loopback measurements (0.40s fast vs 0.47s forced per-row at 1,000
rows) corroborate the per-row reality.

## Research questions (answer before designing)

1. **Rowcount semantics.** The candidate fix verifies an all-matched
   batch by aggregate `rowcount == N` with no RETURNING. SQLAlchemy's
   mysql dialects default to `CLIENT_FOUND_ROWS` (rowcount = rows
   *matched*), and today matched == changed because the guard always
   bumps `version` — but the fix must pin which semantic it needs and
   assert the connection flag, not inherit the coincidence.
2. **Statement shape.** MySQL/MariaDB accept multi-table UPDATE with a
   derived-table join (`UPDATE t JOIN (SELECT ... UNION ALL ...) v ON
   ...`) but not the column-aliased `(VALUES ...)` form SQLAlchemy
   renders for the postgres/mssql arm (MariaDB ≥10.3 has `VALUES` with
   different aliasing). Establish the one shape both family members
   execute, how SQLAlchemy renders it, and its bind-parameter width
   per row for chunking.
3. **Attribution on mismatch.** A set-based UPDATE has one aggregate
   rowcount: on `rowcount != N` the arm must fall back exactly as the
   aggregate rung does today (savepoint rollback, per-row re-drive) —
   confirm the savepoint interplay under REPEATABLE READ and the
   catch-retry arbitration layer.
4. **Both family members, real engines.** Every answer verified live
   on the mysql and mariadb Docker legs via the `db_test` cycle —
   dialect-name resolution burned us once (ADR 024); no "mysql only"
   evidence is accepted for a family-wide change.

## Acceptance criteria

- A clean N-row guarded overwrite batch on mysql/mariadb executes
  O(chunks) driver round trips, not O(N); the chunk math is pinned by
  a budget-forcing unit test like the VALUES-arm pin in
  `test_backends_database.py`.
- Attribution behavior is byte-identical to today's contract: exact
  per-row blame on conflict, no success without statement evidence
  (079's doctrine), the refusal arm untouched.
- The rowcount-semantics dependency is asserted at runtime or pinned
  by test — not assumed.
- Both mysql and mariadb conformance legs green and enforcing; the
  torn-row regression pin still red on the pre-079 code shape.
- plan.md 079's executemany claim corrected to name the final
  per-family statement shapes.
