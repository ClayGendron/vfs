# 145 — membership predicates: one helper, the profile's form, VALUES on SQL Server

- **Status:** built and verified 2026-09-04 — implementing ADR 061 the
  day it was decided; every gate green (see the landing note), awaiting
  commit and archive.
- **Born from:** ADR 061; memo
  `../../../research/2026-09-04-mssql-membership-reads.md`; spec 144's
  recorded follow-up (the lock made the scan a table lock).
- **Date:** 2026-09-04
- **Owner:** Clay Gendron
- **Kind:** one new module (`storage/backends/database/membership.py`),
  one profile field (`DialectProfile.membership`) plus the MSSQL
  profile's budget and hint, and the mechanical routing of ~38
  chunk-scale `.in_(` sites with the profile plumbed to the functions
  that chunk. No schema change, no verb-surface change.
- **Depends on:** spec 144 (`lock_rows`, `row_lock_hint`), the chunking
  discipline (`chunked`, `membership_budget`), `BytewiseString` /
  `ULIDKey` (the key types the cast rule reads).

## Intent

Make membership predicates one concern with one owner, so an engine's
plan behaviour is a declared profile fact, and give SQL Server the form
its optimizer seeks on at every table size without losing non-Latin
keys — the `VALUES` derived table cast through the column's UTF-8
collation, and the join shape under `UPDLOCK, FORCESEEK` where rows
must stay locked.

## Decided semantics

1. **`membership(column, keys, profile)`** returns the predicate for one
   chunk: `column.in_(keys)` under `in_list`; under `values`,
   `column IN (SELECT <typed> FROM (VALUES ...) AS keys (v))` where
   `<typed>` is `CAST(keys.v COLLATE <utf8> AS varchar(n))` for
   `BytewiseString` and plain `String` columns (their own length) and
   the bare column for `ULIDKey` and integer keys, whose binds already
   match the column's type.
2. **`locked_lookup(table, key, keys, columns, profile)`** returns the
   guard read: `select(columns).where(key IN keys)` through `lock_rows`
   under `in_list`; the `VALUES` join under `values`, hinted by
   `lock_rows`. The three guard sites (the mkedge endpoint resolve and
   both reindex repair guards) use it; `lock_rows` stays the lock
   primitive.
3. **The profile declares the form**: `membership="in_list"` everywhere
   but MSSQL (`"values"`). MSSQL's `in_list_budget` is 2,000 — a lock
   budget (two key locks per row, under the 5,000 escalation trigger
   per statement) that is also under the 2,100-bind cap — and its
   `row_lock_hint` is `UPDLOCK, FORCESEEK`.
4. **Query-sized memberships stay inline**: `ext`/`kind` sets, the
   query's own terms and grams, block-number lists, and the tuple-IN
   guard are not chunk-scale and keep `.in_`.
5. **The profile travels explicitly**: every function that chunks takes
   `profile` beside `membership_budget` (the pair the write path already
   used); no hidden state, no compile-time lookup.
6. **Recorded, not capped**: `values()` statements compile per call
   (SQLAlchemy does not cache-key the derived table by shape); the
   measured cost is tens of milliseconds against the seconds replaced.

## Slices

- **A — the helper and the profile**: `membership.py`, the field, the
  MSSQL budget and hint, rendering pins (`test_membership.py`,
  `TestLockRows` trued to the two-hint spelling).
- **B — the routing**: every chunk-scale site through the helper, the
  profile plumbed to a fixed point, the three guard reads through
  `locked_lookup`, direct test callers updated.
- **C — legs, scale, landing**: the non-Latin canary batch in the
  conformance contract (every leg), the lock-profile pin on the mssql
  leg, the 10k-edge batch re-timed on SQL Server, full matrix, landing
  note, archive.

## Landing criteria

- `scripts/ci.sh 3.13` green at 100 %; four engine legs green.
- On the mssql leg a 2,000-key locked lookup holds only key locks; the
  four non-Latin canaries round-trip through `stat`/`read` on every leg
  in a batch larger than any chunk.
- The SQL Server 10k-edge batch runs without a table-lock escalation.

## Landing note (2026-09-04)

- **Local**: `scripts/ci.sh 3.13` green — 3,114 passed, 956 skipped,
  coverage 100.00 %; ruff, format, ty at zero.
- **Engine legs**: the full four-leg suite green — 947 passed, 8
  skipped — on Postgres 17, MariaDB 11.8, SQL Server 2025, Oracle
  23ai; that includes the new contract row (2,007 paths with four
  non-Latin canaries through `stat`/`read` in one call, every leg) and
  the two mssql pins (a 2,000-key locked lookup holds 4,000 key locks
  and no table lock; the `VALUES` predicate finds every canary).
- **Prototype findings that shaped the code**: the `IN (SELECT ...)`
  and `EXISTS` spellings of the derived table seek only by luck and
  raise 8622 under `FORCESEEK`; forcing a loop join makes them seek
  the wrong way and lock every row. Only the join accepts the hint and
  locks two keys per row — hence `locked_lookup`'s join shape and the
  predicate/guard split. Through SQLAlchemy's `values()` a 2,000-key
  statement costs ~20 ms to compile client-side and ~150 ms on first
  execution, ~50 ms after (raw driver: 13 ms) — the recorded profile.
- **Scale**: the 10k-edge batch, idle CPU. SQL Server create 18.1 s →
  2.4 s with **zero** lock escalations (`index_lock_promotion_count`
  unchanged across create and touch, against +1 per verb before);
  Postgres 0.3 s, MariaDB 0.3 s, Oracle 0.5 s unchanged. Touch and
  remove read 5–9 s on every engine in some runs and 0.3–0.5 s in
  others, on this tree and on the tree before it alike: `auto_explain`
  shows the per-row touch `UPDATE` (keyed by the full triple) planned
  on the `(source_id, edge_type)` index with `Rows Removed by Filter:
  9999` — the batch's one hub has 10,000 out-edges, and which index the
  planner picks varies per run. That is spec 143's recorded hub-degree
  follow-up, unchanged by this spec.
- **Environment**: the engine containers were found stopped mid-run
  (another session's teardown) and brought back with the documented
  compose command; the code-page probe's `vfs_utf8` and the lock
  probe's `vfs_rcsi` databases remain in the SQL Server container until
  its next teardown.
