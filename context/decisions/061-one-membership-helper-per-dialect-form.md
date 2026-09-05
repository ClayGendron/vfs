# 061. One Membership Helper, the Profile Declares the Form — a VALUES Derived Table on SQL Server

- **Status:** accepted 2026-09-04 — decided by Clay in session after
  the SQL Server membership-read study ("sounds good, lets commit
  this"; "can we now implement the improved in_list for MSSQL?").
- **Date:** 2026-09-04
- **Deciders:** Clay Gendron
- **Decided by:** human
- **Context source:**
  `context/research/2026-09-04-mssql-membership-reads.md` and its
  study `context/research/studies/2026-09-04-mssql-membership-reads/`
  (the flip matrix over 20k / 200k / 1M rows, the bind-typing trace
  and code-page probe, the membership-forms matrix, the lock
  profiles); spec 144's landing note (the lock that made the scan a
  table lock).

## Context

Every chunked membership read in the database backend — some 45
`column IN (...)` sites over `path`, `entry_id`, and integer keys —
was built inline as `column.in_(chunk)`. On SQL Server the optimizer
plans a long `IN` list as a clustered index scan on small tables (the
flip moves with table size; it is the cost model, not a threshold),
every `nvarchar` bind is converted against the `varchar` key, and one
non-Latin path in the list makes the seek range swallow the table.
Under spec 144's `UPDLOCK` the scan became a table-level exclusive
lock per statement. Typing the binds as `varchar` is not a fix: the
driver reads a `varchar` bind in the database's code page and loses
CJK and emoji paths on any non-UTF-8 database (measured: 62 of 64
rows). A `VALUES` derived table of the keys, cast once server-side
through the column's UTF-8 collation, seeks at every table size and
loses nothing; `OPENJSON` ties on time but estimates a constant 50
rows, the EF Core regression on non-unique columns.

## Decision

1. **One owner.** Every chunked membership predicate is built by
   `storage/backends/database/membership.py`: `membership(column,
   keys, profile)` for predicates, `locked_lookup(table, key, keys,
   columns, profile)` for guard reads that must hold their rows.
   Sites never spell `column.in_(chunk)` themselves.
2. **The profile declares the form.** `DialectProfile.membership` is
   `"in_list"` (the expanding bind list every compiler renders — the
   default, and what Postgres, MariaDB, Oracle, SQLite, and the
   generic floor keep) or `"values"` (SQL Server only). A spelling
   changes only when a measurement on that engine says so.
3. **The SQL Server form.** `column IN (SELECT CAST(keys.v COLLATE
   <utf8> AS varchar(n)) FROM (VALUES ...) AS keys (v))` for string
   keys; binary and integer keys join uncast. Guard reads take the
   join shape — `FROM (VALUES ...) AS keys (v) JOIN table WITH
   (UPDLOCK, FORCESEEK) ON ...` — because the `IN` shapes refuse
   `FORCESEEK`, and without it a locking read the optimizer plans as
   a scan is a table lock. The profile's `row_lock_hint` names both
   hints; the chunk (`in_list_budget`) becomes 2,000, a lock budget
   (two key locks per row under the 5,000-lock escalation trigger)
   as much as a bind budget.
4. **Never** type the binds through `setinputsizes` (lossy), use
   `OPENJSON` (the fixed estimate), or disable lock escalation.

## Consequences

- **Easier:** a per-engine plan finding is a profile field and one
  module, not forty edits; non-Latin keys are pinned on every leg;
  the SQL Server 10k-edge batch stops taking table locks.
- **Harder:** every function that chunks now carries the profile
  (the same pair, `profile, membership_budget`, the write path
  already used); SQLAlchemy's `values()` is not cache-keyed by
  shape, so each `VALUES` statement compiles fresh (~20 ms
  client-side, ~80 ms server-side per distinct length) — a recorded
  profile, far under the seconds it replaces, with a bindparam-shaped
  construct as the named future direction if it ever measures.
- **Committed to:** spec 145 lands the helper, the routing, the
  rendering pins, the non-Latin canary on every leg, and the lock
  profile pin on the mssql leg.

Evidence: the memo's flip matrix (scans from 1,024 elements at 20k
rows, seeks to 2,067 at 1M), code-page probe (62/64 with `varchar`
binds on `master`), forms matrix (`VALUES` 13–17 ms per 2,067 keys
against 4,060 ms shipped at 20k rows; two key locks per row, no
escalation at 40,000 locks), and the in-session prototype of the
SQLAlchemy-built forms (the `IN` shapes raise 8622 under `FORCESEEK`;
the join seeks and locks 2 keys per row). Refines ADR 059 (dialects
served on the floor keep the `in_list` form); amends nothing.
