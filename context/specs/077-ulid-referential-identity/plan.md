# 077 — execution plan (as run, 2026-07-21)

Executed in one landing, dependency order, tree green at the end.

1. **Schema** (`src/vfs/models/rows.py`) — `ULIDKey` TypeDecorator (26-char
   ULID strings in Python; `Uuid` storage, `BINARY(16)` on MSSQL with byte
   round-trip via `ULID.from_bytes`/`.bytes`); it is the one conversion
   home. `node_id` → `entry_id`; re-typed `parent_id`,
   `original_parent_id`, `content.entry_id`, `versions.entry_id`,
   `chunks.entry_id`, `edges.source_id`/`target_id`. `ENTRY_ROW_ONLY_COLUMNS`
   renamed member; identity docstring rewritten (no ADR references in code,
   per repo rule). Integer `id` columns untouched.
2. **Staging** (`staging.py`) — `StagedEntry.entry_id: str`, required,
   minted by `stage_create` (`str(ULID())`), copied from the committed row
   by `stage_update`. The learned-id states are gone.
3. **Writes** (`writes.py`) — snapshot selects `entry_id` (never `id`);
   `_entry_values` consumes `staged.entry_id`; `_parent_id` is a two-line
   upfront lookup; `_upsert_layer` RETURNING = `(entry_id, path, version)`
   — the pin-4 deviation: clobbers adopt the rival row's surviving
   identity; `_catch_retry_layer` lost RETURNING, the id read-back, and
   its `membership_budget` parameter; `_resolve_rows` probes and adopts
   `entry_id`; `_update_materials` / `_replace_content` / `_bump_parents`
   key on `entry_id`.
4. **Reads** (`reads.py`) — anchor/identity column and content join on
   `entry_id`; `ls` parent-equality unchanged in shape. `engine.py`
   provisions the root with `entry_id`.
5. **Tests** — `test_rows.py` (ULIDKey type assertions, `_entries_row`
   helper, ULID parent keys), `test_backends_database.py` (seeder wires by
   minted ULIDs with no RETURNING; `_resolve_rows` clobber asserts
   identity adoption against the rival's key; stale-guard staged entry),
   and the acceptance test `test_identity_portability.py`: row-wise copy
   into a fresh schema with entries inserted in reversed order (integer
   ids re-mint differently), then tree/ls/read verified and a new child
   written under a copied parent. `storage_demo.ipynb` raw-peek cell shows
   `entry_id` tails and the parent wiring.

Verification: `uv run ruff check` + `format --check` clean, `uv run ty
check` clean, `uv run pytest tests/ -q` 1460 passed / 53 skipped.
