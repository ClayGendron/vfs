# 077 — ULID referential identity: durable references move to `entry_id`

- **Status:** implemented 2026-07-21 (ADR 019 accepted same day; plan.md
  executed in the working tree — suite green at 1460 passed, `ruff`/`ty`
  at zero, the portability acceptance test passing on first run). Two
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
   binary-16 (SQLAlchemy `Uuid`; `BINARY(16)` variant on SQL Server —
   `UNIQUEIDENTIFIER` sort order forfeits time-locality; text ULID in
   an indexed role is out of spec). Re-typed to match: `parent_id`,
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
   `entries.entry_id`; `ls` stays parent-equality with the converted
   binary param; descent/miss classification is path-based and
   unchanged.

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
