# 144 — endpoint liveness under lock: closing the delete-vs-mkedge race

- **Status:** landed and archived 2026-09-04 — commit `d0de6f0`. The
  MSSQL finding (below) resolved the same day: `with_for_update()` is
  a silent no-op on the T-SQL compiler, and the lock goes through
  `dialects.lock_rows`, which spells it from the profile's
  `row_lock_hint` (`UPDLOCK` on SQL Server). Drafted 2026-09-04 from
  the executed race study; Clay adopted the memo's recommendation in
  session the same day. Discharges the second recorded follow-up of
  spec 143's landing note. ADR 018 amended at this landing.
- **Born from:** memo `../../../research/2026-09-04-delete-vs-mkedge-race.md`
  and its rerunnable study
  (`../../../research/studies/2026-09-04-delete-vs-mkedge-race/`);
  spec 143's landing review (the finding); ADR 018 pins 5–9 (the
  mirror and lifetime doctrine this completes).
- **Amends (record at the mining pass):** ADR 018 — the edge-lifetime
  law gains its enforcement clause: endpoint liveness is checked
  insert-side, under row locks, in the same transaction that inserts
  the edge; delete's cascade alone (the delete-side half) is proven
  insufficient by the staged race and by Oak's and gel's identical
  open windows.
- **Date:** 2026-09-04
- **Owner:** Clay Gendron
- **Kind:** two behavior changes in
  `storage/backends/database/edges.py` — the endpoint resolve locks
  its rows for `mkedge`, and reindex re-convergence reclaims authored
  edges touching trashed entries — plus the race pins, drift tests,
  and scale re-verification. No schema change, no verb-surface
  change, no new module.
- **Depends on:** spec 143 (the edge verbs, the mirror, the
  re-convergence pass — all live), the seam machinery
  (`storage/backends/database/seams.py`), the retryable-conflict
  classification (deadlocks already ride the retry channel), the
  `with_for_update()` guard shape (`repair_edge_drift`,
  `segments.py` — proven portable on all four engine legs).
- **Relates to:** spec 138 (the extractor writes edge rows at the row
  layer during reindex — it does not take the verb's locks, which is
  why arbitration stays; its rows are covered by the reindex reclaim
  instead), spec 136 (the in-degree signal is the first reader that
  would have consumed a stray), spec 067 (traversal — arrives to a
  table whose liveness invariant actually holds).

## Intent

Spec 143's landing review found, and the 2026-09-04 study proved on
all four client/server engines: a rival `delete` committing between
`mkedge`'s endpoint resolve and its insert leaves an authored edge
naming a trashed entry. Reindex is blind to it (the trashed entry
still has its row), and `restore` resurrects it as a live edge —
silently violating "restore never re-mints." The field's verdict is
clean: systems that enforce the reference only delete-side (Oak, gel)
leave exactly this window open; the systems that close it (juicefs,
Postgres's own FK machinery) both do it with an insert-side lock on
the referenced row. vfs already has the delete-side half — the
cascade. This spec adds the insert-side half, and extends reindex
re-convergence to reclaim any stray that reaches the table anyway.

## Decided semantics

1. **`mkedge` resolves its endpoints under row locks.** The endpoint
   resolve in `mkedge_rows` becomes a locking read
   (`with_for_update()` on the entry rows, the house guard shape),
   chunked under `membership_budget` with paths sorted, in the same
   transaction that probes and inserts. The lock is the liveness
   proof: a path that resolves under lock names a live entry that
   cannot be trashed before this transaction commits. A rival delete
   then serializes to one of two honest outcomes — it waits and its
   cascade removes the just-created edge (mkedge truthfully reported
   `created`; the endpoint died afterward), or it commits first and
   mkedge truthfully refuses `not_found`. No third state exists.
2. **`rmedge` takes no lock.** It only deletes. A rival endpoint
   delete cascading the same rows converges to the identical end
   state — the edge is gone either way — which is already `rmedge`'s
   documented arbitration posture. Adding locks there would buy
   nothing and cost hot-endpoint serialization on a read-mostly path.
3. **The lock is dialect-aware, and the profile declares it.**
   *(Amended 2026-09-04 by the implementation finding below — the
   original pin said "plain `with_for_update()`, everywhere"; that is
   wrong on SQL Server.)* Every guard read that must hold its rows
   goes through one helper, `dialects.lock_rows(stmt, table,
   profile)`: `with_for_update()` where the compiler renders it
   (Postgres, MariaDB, Oracle — verified blocking against the rival
   delete; SQLite renders nothing, lawfully, its writer transaction is
   the lock), and the profile's `row_lock_hint` as a table hint where
   one is declared. SQL Server declares `UPDLOCK` — SQLAlchemy models
   the API but its T-SQL compiler drops it (the clause exists only on
   cursors there), a genuine per-dialect fact SQLAlchemy takes no
   working position on, owned by the profile the way `cosine_distance`
   owns the distance spelling. `UPDLOCK` alone is the minimal correct
   hint: update locks on the addressed keys, held to commit, exactly
   what `FOR UPDATE` means elsewhere; `HOLDLOCK` is not taken (its
   key-range locks guard phantoms the guard never reads). The
   pre-existing reindex guards (`repair_edge_drift`,
   `repair_segment_drift`) route through the same helper — they were
   no-ops on SQL Server too, resting on the guard-miss re-check alone.
   The Postgres refinement the study surfaced — `FOR KEY SHARE` is
   sufficient and shared, so concurrent `mkedge` batches naming one
   hot endpoint need not serialize against each other (on SQL Server
   the analogue is the `REPEATABLEREAD` hint, measured to block the
   delete with a shared key lock) — is a separate recorded future
   direction, taken only if hot-endpoint contention measures as a
   real cost. Never a cap: correctness is identical either way.
4. **Deadlocks ride the existing retry channel.** Lock acquisition is
   chunked over sorted paths, so `mkedge` batches order consistently
   against each other. Against `delete`'s claim order a deadlock
   remains constructible; every engine's deadlock code is already
   classified retryable, and the write path's redrive discipline is
   the answer — a pin, not new machinery.
5. **Arbitration stays.** The savepoint redrive
   (`_insert_arbitrated`) remains: the verb's locks serialize
   verb-vs-verb duplicates, but row-layer writers — spec 138's
   extractor foremost — insert edge rows without the verb's locks,
   and the unique key remains the referee for that race.
6. **Reindex re-convergence reclaims trash-touching authored
   edges.** The collect pass learns each entry's liveness (the trash
   scope is a path fact it already streams past) and records any
   authored (non-`fs`) edge touching a trashed entry as drift; the
   repair pass deletes those rows under the same guard discipline as
   `FsDelta` — the entry row re-read locked, the delta applied only
   while the entry is still trashed, a rival restore's synchronous
   truth respected by skipping. Every reclaim surfaces as a
   warning-severity record: with pin 1 in place a stray means a
   mint-site bug, and it must surface. The fs mirror rows of trashed
   entries remain lawful — trash keeps its mirror; only authored
   rows are reclaimed.
7. **The invariant sharpens from aspiration to law.** "Zero authored
   edge rows touching trashed ids" is now enforced at both ends —
   prevented at insert, reclaimed at reindex — and the staged race
   from the study becomes a permanent pin in both commit orders.

## Scope

In: the locking resolve for `mkedge`, the deadlock-retryable pin, the
staged-race pins (seam-staged locally, natural-timing on the engine
legs), the reindex reclaim with its drift tests and restore-race
guard test, docstring true-ups in `edges.py`, scale re-verification
of the 10k-edge batch under locks (including observing and recording
SQL Server's lock-escalation behavior — a measurement, never a
designed limit). Out: any schema change; FK constraints (they cannot
express soft-delete liveness — the memo's gel section); share-lock
refinements (future direction, pin 3); restore-side edge sweeping
(redundant once insert-side prevention lands); the hub-probe cost
(spec 143's other follow-up — separate decision, needs the degree
study first).

## Slices

- **A — the lock**: the locking endpoint resolve in `mkedge_rows`
  (mkedge-only; `rmedge` keeps the plain read), the staged-race pin
  in both orders, the deadlock classification pin,
  `scripts/ci.sh 3.13` green at 100 %.
- **B — the reclaim**: liveness in `collect_edge_drift`, guarded
  reclaim in `repair_edge_drift`, the warning vocabulary, stray
  injection and restore-race guard tests, green again.
- **C — legs, scale, landing**: the race pins on all four engine
  legs (`test_races.py`), the 10k-edge batch re-verified under locks
  with the MSSQL escalation observation recorded, full matrix,
  landing note, archive.

## Landing criteria

- The staged race from the study, re-run against all four engines,
  produces no stray in either commit order: delete-first yields
  `not_found`, mkedge-first yields a created edge that the delete's
  cascade removes.
- An injected stray (row-layer insert of an authored edge touching a
  trashed id) is reclaimed by the next reindex with a loud warning; a
  restore racing the repair wins cleanly (the reclaim skips).
- The 10,000-edge `mkedge` batch still lands in one call on every
  engine leg; SQL Server's behavior at ~20k row locks is measured
  and recorded in the landing note, whatever it is.
- `scripts/ci.sh` full matrix green; all engine legs green;
  coverage 100 %.
- `edges.py`'s docstrings state the lock as the liveness proof and
  the reclaim as the backstop; spec 143's landing-note follow-up is
  discharged by reference to this spec.

## Implementation findings (2026-09-04, paused mid-slice-A)

What is written and green, and the one finding that paused the work.

### Done and green

- **Slice A src** (`edges.py`): `_endpoint_ids` gained
  `for_update: bool = False` (per-chunk `with_for_update()` over the
  already-sorted paths); `mkedge_rows` passes `for_update=True`,
  `rmedge_rows` stays a plain read; docstrings trued (module
  lifetime paragraph, `mkedge_rows` arbitration paragraph).
- **Slice B src** (`edges.py`): `EdgeRebuildState.strays`
  (`dict[int, set[str]]`); `collect_edge_drift` streams `entry.path`,
  marks trashed ids by `TRASH_ROOT` prefix (`_in_trash`), records
  authored rows touching one; `repair_edge_drift` locks the recorded
  endpoints in the shared `FsDelta` guard read, reclaims a stray only
  while an endpoint is still trashed (a vanished endpoint reads as
  still-dead), skips on a restore, and emits `_stray_warning`.
- **Tests**: the seam-staged race pin
  (`test_edges.py::TestEndpointLocks`, sqlite — green) launches the
  rival delete as a task and asserts it blocks in-window, then
  converges; the two reclaim tests
  (`test_edges.py::TestEdgeRebuild`) — stray-injected-and-reclaimed
  and restore-wins-the-guard — green; the engine-leg twin
  (`test_races.py::TestMkedgeEndpointLocks`).
- **Verified**: the local suite and the engine-leg race pin are green
  on **Postgres, MariaDB, Oracle** — the lock blocks the rival delete
  on all three. All four engines' deadlock codes already sit in the
  retryable tables (40P01/40001, 1213/1205, ORA-00060), so no new
  retry machinery is needed.

### The finding that paused it — MSSQL

The engine-leg race pin **fails on SQL Server**: the rival delete
commits inside the window. Root cause, probed directly (the probe
script is in the session scratchpad, to fold into the study on
resume):

- SQLAlchemy renders `select(...).with_for_update()` on the MSSQL
  dialect as a **bare `SELECT`** — no `FOR UPDATE`, no table hint.
  The lock is silently dropped, so the resolve takes no lock and the
  rival delete proceeds. (This means the pre-existing
  `with_for_update()` guards in `repair_edge_drift` and `segments.py`
  are also no-ops on MSSQL today — they rely on the reprobe/guard-miss
  discipline for correctness there, not the lock; only spec 144 makes
  the lock itself load-bearing, which is why the gap surfaced now.)
- Spelling the lock as `select(...).with_hint(entry, "WITH (UPDLOCK,
  HOLDLOCK)")` **does** block the rival delete (probe confirmed: the
  delete waited behind the hint until the lock was released). Trash
  rewrites `path`, so the delete needs an exclusive lock that
  conflicts with the held update-lock — the same key-update mechanics
  the study found on Postgres.

### Resolved on resume (2026-09-04) — the four research items

Probes in the study directory
(`../../../research/studies/2026-09-04-delete-vs-mkedge-race/`:
`mssql_lock_probe.py`, `mssql_lock_scale_probe.py`), run against the
live SQL Server 2025 container, in both locking READ COMMITTED and
READ_COMMITTED_SNAPSHOT databases.

1. **The construct: `UPDLOCK` alone.** It takes one KEY U lock per
   addressed row, held to commit, and the rival delete blocks behind
   it in both isolation modes. `UPDLOCK, HOLDLOCK` also blocks but
   holds three `RangeS-U` key-range locks per row — phantom protection
   over ranges the guard never reads, and range locks are what
   escalate and block neighbouring inserts. `ROWLOCK` adds nothing.
   `REPEATABLEREAD` (a shared key lock held to commit) also blocks the
   delete — it is the `FOR KEY SHARE` analogue, recorded for the
   share-lock future direction.
2. **Blocking cost and escalation at 10k: none at key granularity;
   the scan is the cost.** With statements that seek, locking 20,000
   endpoint rows in one transaction takes 2.0 s, peaks at 40,000 KEY U
   locks (two per row: the path index key and the clustered key) and
   never escalates — SQL Server's 5,000-lock threshold is per
   statement, and no chunk reaches it. But the optimizer plans the
   chunked `path IN (...)` resolve as a clustered index **scan** from
   somewhere between 1,024 and 1,500 list elements on a 20k-row table
   (the binds arrive as `nvarchar` against the `varchar` column, so
   every plan carries a `CONVERT_IMPLICIT`), and at today's MSSQL
   chunk of 2,067 every statement scans: 4–6 s each, U locks on every
   row, escalation to a table X lock per statement. **This is the
   pre-existing shape of every chunked membership read on SQL Server**
   — the plain resolve before this spec scanned identically (the plain
   read takes S locks it releases per row, so it never escalated) —
   and the lock inherits it rather than causing it. The 10,000-edge
   batch still lands in one call: 18 s create / 17 s touch / 23 s
   remove on the emulated container, one escalation per verb
   (`index_lock_promotion_count` +1 each), versus 0.3–0.5 s on
   Postgres. Recorded as a scale profile, never a designed limit; the
   fix is the plan, not the lock, and it is out of this spec's scope —
   see *Recorded follow-ups* below.
3. **The helper's shape: a profile field plus one function.**
   `DialectProfile.row_lock_hint: str | None` (MSSQL: `"UPDLOCK"`) and
   `lock_rows(stmt, table, profile)` in `dialects.py`, gated on the
   profile's dialect name so a declared hint never leaks into another
   engine's SQL; the generic floor declares no hint and trusts the
   compiler. All three lock sites route through it — the mkedge
   resolve (`_endpoint_ids(..., lock=profile)`), and both reindex
   repair guards, which thereby become real locks on SQL Server (they
   were bare SELECTs there; their guard-then-apply was racy under
   READ COMMITTED without the lock). Signatures gained `profile` in
   the house position (`session, tables, profile, membership_budget,
   ...`).
4. **The deadlock surface under the storm.** The mkedge-vs-delete
   storm pin (`test_races.py::TestMkedgeEndpointLocks::
   test_mkedge_bursts_against_deletes_leave_no_stray`: two opposed
   edge bursts of 300 against three spoke deletes and the folder
   delete, ten rounds, natural timing) surfaces only the lawful race
   kinds on every engine, and reindex finds zero strays after every
   round. See the landing note for the per-leg run.

### Recorded follow-ups (out of scope here)

- **SQL Server membership reads scan past ~1k `IN` elements.** Every
  chunked `path IN (...)` / `entry_id IN (...)` read on MSSQL plans as
  a clustered scan at the declared chunk (2,067), costing seconds per
  statement on a 20k-row table and, under a lock, a table-lock
  escalation per statement. Candidates for a research memo: lower
  the MSSQL `in_list_budget` to the measured seek range (the flip
  point moves with table statistics, so it needs measuring at 1M
  rows too), bind the string keys as `varchar` (SQLAlchemy's pyodbc
  setinputsizes sends `String` as `SQL_VARCHAR`, yet the plan shows
  `nvarchar` binds — the TypeDecorator path needs tracing), or a
  VALUES-join / table-valued-parameter membership form. Not a lock
  question; owned by whichever spec takes the MSSQL read path.

## Landing note (2026-09-04)

- **Local**: `scripts/ci.sh 3.13` green — 3,101 passed, 950 skipped,
  coverage 100.00 %; ruff, format, and ty at zero.
- **Engine legs**: the full four-leg suite (`-m "postgres or mariadb
  or mssql or oracle"`) green — 941 passed, 8 skipped — on Postgres 17,
  MariaDB 11.8, SQL Server 2025, Oracle 23ai. The staged race pin
  (`TestMkedgeEndpointLocks`) and the new storm pin (two opposed edge
  bursts of 300 against three spoke deletes and the folder delete,
  ten rounds) pass on all four; the storm surfaced only the lawful
  race kinds and reindex found zero strays after every round.
- **Scale**: the 10,000-edge `mkedge` batch lands in one call under
  the lock on every leg — create / touch / remove: Postgres
  0.3 / 0.5 / 0.4 s; MariaDB 0.3 / 3.8 / 3.6 s; Oracle 1.2 / 8.7 /
  5.1 s; SQL Server 18.1 / 17.1 / 22.9 s with one table-lock
  escalation per verb (`index_lock_promotion_count` +1 each). The SQL
  Server figures are the pre-existing `IN`-list scan (see *Recorded
  follow-ups*); the emulated container inflates every absolute
  number, so the ratios are the record.
- **Spec 143's race follow-up** is discharged by this spec.
- **Left for the mining pass**: the ADR 018 amendment note (the
  enforcement clause), the archive move, and the MSSQL membership-read
  memo commissioned 2026-09-04 (in progress under
  `research/2026-09-04-mssql-membership-reads.md`).
