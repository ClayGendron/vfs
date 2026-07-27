# 077 — ULID referential identity: durable references move to `entry_id`

- **Status:** implemented 2026-07-21 (ADR 019 accepted same day; plan.md
  executed in the working tree — suite green at 1460 passed at landing,
  1468 after the same-day five-lens review hardening; `ruff`/`ty` at
  zero, the portability acceptance test passing on first run). Two
  conscious departures, both recorded in plan.md. First, pin 4 said
  `_upsert_layer` RETURNING carries "path and version only", but it must
  also carry ``entry_id`` — a clobber lands on the rival's row, which
  keeps its identity, so the staged entry adopts the returned
  ``entry_id`` or its content rows would wire to a ULID that owns no
  entry row. The catch-retry layer, by contrast, learns nothing back (a
  clean insert is all our own rows; its conflict arm adopts identity via
  the occupant probe in ``_resolve_rows``), and its
  ``membership_budget`` parameter fell away with the read-back. Second,
  pin 1's closing clause ("the module docstring's identity paragraph
  re-cites ADR 004 + 019") was dropped: the repo rule is that
  traceability lives in `context/`, never in code comments or
  docstrings, and the pin predated that rule's application here.
- **Decision:** ADR 019 (amends ADR 004 pin 2). Evidence:
  `context/research/2026-07-21-ulid-referential-identity.md`.

## Scope

Re-key every durable dependent reference from the engine-minted integer
surrogate `id` to the application-minted ULID, renamed `entry_id`,
stored binary-16. Demote `id` to an unreferenced local row locator. The
write pipeline wires identity client-side; depth layering and
arbitration are unchanged in structure.

**Untouched:** the memory backend (no ids exist there), `base.py`
routing, the results envelope, POSIX gate semantics, version rules,
arbitration modes, and the two-budget chunking discipline.

## Pins

1. **Schema (`rows.py`).** `entries.node_id` → `entries.entry_id`,
   binary-16 on every engine (native uuid only where its sort preserves
   ULID time-order — Postgres; `RAW(16)` on Oracle; fixed `BINARY(16)`
   everywhere else, SQL Server included, whose `UNIQUEIDENTIFIER` sort
   order forfeits time-locality; text ULID in an indexed role is out of
   spec). Re-typed to match: `parent_id`,
   `original_parent_id`, `content.entry_id`, `versions.entry_id`,
   `chunks.entry_id`, `edges.source_id`/`target_id`.
   `UNIQUE(parent_id, name)` moves with the type. `id` stays the
   integer primary key on every table that has one. Posting lists keep
   integer doc ids (regenerable-cache doctrine, per ADR 019 pin 2).
   Constant tables (`ENTRY_ROW_ONLY_COLUMNS` etc.) follow the rename.
   The module docstring's identity paragraph re-cites ADR 004 + 019.
2. **Boundary conversion has one home.** Two helpers beside the schema
   in `rows.py` (ULID string ↔ stored binary value); the domain and
   API surface carries the 26-char ULID string only; no other module
   converts.
3. **Staging (`staging.py`).** `StagedEntry.entry_id` becomes the ULID
   string, never `None`: `stage_create` mints it (`str(ULID())`),
   `stage_update` copies it from the committed row. The learned-id
   states disappear from the dataclass and its docstrings.
4. **Write pipeline (`writes.py`).**
   - `_fetch_committed` selects `entry_id`, drops `id`.
   - `_entry_values` consumes the staged ULID and the parent's ULID;
     `_parent_id` becomes a single upfront lookup (staged parent's
     minted id, else committed row) — no post-insert resolution.
   - `_upsert_layer` RETURNING carries `path` and `version` only
     (arbitration outcomes and clobber versions); no id harvesting.
   - `_catch_retry_layer` drops its id read-back block entirely;
     `_resolve_rows`' occupant probe returns the occupant's `entry_id`
     for the create→clobber conversion.
   - `_update_materials`, `_replace_content`, `_bump_parents` key on
     `entry_id`.
   - Depth layering and per-layer fail-fast are retained: layers still
     learn winners before wiring children (arbitration-loss detection,
     ADR 019 pin 4).
5. **Read family (`reads.py`, `descent.py`).** Content joins on
   `entries.entry_id`; `ls` stays parent-keyed — batched into chunked
   `parent_id IN` selects regrouped per parent; descent/miss
   classification is path-based and unchanged.

## Hardening record (2026-07-21, five-lens review of the landing)

On-disk and shape deltas the review landed beyond the pins as written —
recorded here so the format story is complete before this spec's
residue flows backward:

- **ULIDKey's storage election is three-armed** (pin 1 now states it):
  Postgres native uuid, Oracle `RAW(16)`, `BINARY(16)` everywhere else,
  gated by a postgresql allow-list because `supports_native_uuid` is
  not sort-aware (MSSQL and MariaDB both report it while mis-sorting).
- **Body columns re-typed** — `content.content`, `versions.content`,
  `versions.version_diff`, `chunks.content` went `String()` →
  `Text().with_variant(LONGTEXT, "mysql")`: bare `String()` is a MySQL
  DDL hard-fail and MySQL's plain TEXT caps bodies at 64KB. An emitted-
  DDL change on every engine (TEXT/CLOB/VARCHAR(max)/LONGTEXT).
- **The standalone `parent_id` index is dropped.** Every parent-equality
  path (`ls` children, arbitration occupant probe) rides the leading
  column of `UNIQUE(parent_id, name)`, which also serves the name
  ordering; the extra B-tree bought no read and taxed every insert.
- **`ls` batches its children reads** — chunked `parent_id IN` regrouped
  per parent (pin 5 now states it), replacing one SELECT per anchor.
- **Catch-retry arbitration savepoints per chunk** — a conflict
  re-drives only its own budget-sized chunk row-at-a-time, never the
  whole depth layer.

## Acceptance criteria

- No durable table column references `entries.id`; the pipeline never
  selects, returns, or binds `entries.id` (grep-clean outside
  `rows.py`'s PK definition).
- **The portability test** (the reason this story exists): copy every
  table row-wise into a freshly provisioned schema, letting integer ids
  re-mint freely; tree traversal (`ls`/`tree`), content reads, and edge
  joins are intact via `entry_id` — no remapping step.
- A child-of-minted-parent batch (`parents=True`, or dir+children in
  one batch) wires with zero id read-back statements.
- API surface unchanged: observations and errors carry paths and
  26-char ULID strings only; no binary or integer identity leaks.
- Suite green; `ruff`/`ty` at zero; `storage_demo.ipynb` raw-peek cell
  refreshed to show `entry_id`.

## Ordering

Stage 1 (schema + converters) → Stage 2 (staging) → Stage 3 (writes) →
Stage 4 (reads) → Stage 5 (tests + notebook), landed as one story;
`plan.md` is written at execution time per house convention.
