# 079 — execution plan (2026-07-23)

## Spike finding that amends pin 1/2

The spec keyed the RETURNING arm on `dialect.update_returning` alone
(pin 1: "never from a `DialectProfile` constant"). Live spike: SQLite
declares `update_returning=True` and `update_returning_multifrom=True`,
but SQLAlchemy's `values()` construct compiles the join source as
`(VALUES ...) AS incoming (v_id, ...)` — a column-aliased table alias
SQLite rejects (`sqlite3.OperationalError: near "("`). SQLAlchemy models
no capability for "VALUES accepted as an UPDATE join source", so per the
house rule (a profile field is justified exactly where SQLAlchemy takes
no position) the set-based arm gains a declared gate:
`DialectProfile.values_join` — `True` on postgresql and mssql, `False`
on the floor. The spec's capability pins stay primary: the field only
*narrows* `update_returning and update_returning_multifrom`, never
substitutes for them.

## The attribution ladder (as built)

Flags verified on the live async drivers:

| driver              | upd_returning | multifrom | sane_rowcount | sane_multi |
|---------------------|---------------|-----------|---------------|------------|
| sqlite+aiosqlite    | True          | True      | True          | True       |
| postgresql+asyncpg  | True          | True      | True          | False      |
| mssql+aioodbc       | True          | True      | True          | False      |
| oracle+oracledb     | True          | False     | True          | True       |
| mysql+aiomysql      | False         | False     | True          | True       |

1. **VALUES-join RETURNING** — `profile.values_join` and
   `dialect.update_returning` and `dialect.update_returning_multifrom`
   (postgres, mssql). One set-based guarded UPDATE per chunk over a
   `values()` join, `RETURNING entry_id, version`; success is exactly
   membership in the returned set. Chunked by the tighter of
   `membership_budget` and `rows_per_statement` (each tuple carries
   11 binds — id, base, ver, 8 material columns), so a 10,000-entry
   batch stays batch-native and bounded.
2. **Executemany + sane aggregate** — `dialect.supports_sane_multi_rowcount`
   (sqlite, mysql/mariadb, oracle). The guarded executemany runs under a
   savepoint; an aggregate rowcount equal to the row count is statement-
   native proof every guard matched (each statement matches ≤ 1 row via
   the unique `entry_id` index). On mismatch the savepoint rolls back —
   guarded updates
   are not idempotent, so attribution must not re-run them over applied
   state — and rung 3 re-drives row-by-row.
3. **Per-row rowcount** — `dialect.supports_sane_rowcount` (the unknown-
   driver floor, and rung 2's attribution fallback). One statement per
   row, `rowcount == 0` classifies `conflict`. SQLAlchemy's own choice
   when a version guard must be verified without RETURNING.
4. **Neither** — the guarded arm returns one classified `unsupported`
   error; unverifiable writes are refused, not guessed.

The unguarded (`"absorb"`) arm keeps its executemany `version = version + 1`
and learns assigned versions from the VALUES-join RETURNING on rung 1 or
a chunked select of **its own ids only** on the floor — reading a row you
unconditionally own is learning, not attribution. A vanished absorb row
still classifies `conflict`. The post-image read-back over *all* updates
is deleted.

## Steps

1. **Regression test first, failing** — `tests/test_storage_conformance.py`:
   plan a guarded overwrite from a version-1 snapshot, let a rival commit
   one increment via the public API, execute the stale plan on a fresh
   READ COMMITTED session. Must fail `conflict`; the entry row's
   `content_hash` must hash the stored content afterwards. Marked
   `mssql` (natural READ COMMITTED — the torn-row engine) and `mysql`
   (REPEATABLE READ, but InnoDB UPDATEs are current-reads, so the guard
   misses the same way; the old code caught it only by accident of the
   snapshot read-back). Run against the Docker harness.
2. **`dialects.py`** — `values_join: bool = False` field; `True` on
   POSTGRESQL and MSSQL; docstring states the decision SQLAlchemy takes
   no position on.
3. **`writes.py`** — `_update_materials` gains `profile` and
   `parameter_budget`; the ladder above; `_values_update` helper (one
   statement shape, guard optional, shared by both arms on rung 1);
   `_guarded_by_rowcount` per-row helper (rungs 2–3); read-back deleted;
   docstring rewritten to state the ladder.
4. **Unit tests** (`test_backends_database.py`) — arm selection against
   stub dialects; rung-2 fast path (default sqlite run), mismatch
   fallback (existing stale-guard test), forced rung 3 and rung 4 via
   monkeypatched dialect flags; VALUES-arm executor covered by a
   hand-rolled session double returning canned RETURNING rows (sqlite
   cannot execute the construct — that is the spike finding).
5. **Real engines** — full db_test cycle: regression test red on MSSQL
   before step 3, green after; conformance legs on postgres/mysql/mssql/
   oracle prove both arms live.
6. Spec amendment note, open-questions entry resolved, coverage 100%,
   ruff/ty zero.

## Floor-arm cost (measured 2026-07-23, mysql:8.4 in Docker, loopback)

1,000-entry batches through the public write API: create 0.25 s;
overwrite via the rung-2 fast path (one guarded executemany) 0.40 s;
overwrite with the fast path disabled (forced rung-3, 1,000 sequential
statements) 0.47 s. Loopback hides network RTT — the per-row arm's cost
scales with round trips on a real network, which is exactly what the
aggregate fast path bounds: a clean N-row overwrite batch is one
executemany regardless of N, and the per-row walk runs only when a
conflict actually exists (a failing batch) or on unknown drivers
without sane multi-row counts.

## Landed alongside (Oracle leg, found by this spec's verification)

Two pre-existing provisioning defects surfaced when the Oracle leg
first ran: the root row's ``name=""`` (Oracle folds ``''`` to NULL —
NOT NULL violation; root name is now the un-typable ``"/"``) and the
surrogate ``id`` keys carrying no ``Identity()`` (Oracle's dialect
generates nothing for a bare autoincrement primary key; Postgres moves
from ``BIGSERIAL`` to standard ``GENERATED BY DEFAULT AS IDENTITY``,
the other engines' DDL is unchanged). Oracle: 56 failed → 62 passed.
