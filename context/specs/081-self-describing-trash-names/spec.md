# 081 — Self-describing trash names and the reported trash location

- **Status:** landed 2026-07-24 — ADR 026 decided everything; this
  spec was the execution package for its pins 1–2. Awaiting its
  residue-mining pass and deletion.
- **Evidence:** `context/decisions/026-self-describing-trash-names-and-restore-contract.md`
  (pins 1–2 and the "Committed to" list);
  `context/research/2026-07-23-trash-prior-art-naming-and-restore.md`.
- **Depends on:** spec 072 slice 9 (the landed topology verbs). The
  restore verb (ADR 026 pins 3–4) and the sweep verb (pin 5) are
  explicitly *not* this spec — they follow as their own specs.

## Problem

The landed delete verb still implements the naming ADR 026 superseded:
`topology.py` renames a trashed row to its **bare ULID**, so every
`ls` of a bucket is unreadable without a join — incoherent with
ADR 014's raw-browsable trash. And the delete result never reports
where the row went: the deleting agent has to search trash to find its
own file. Tests pin the superseded shape
(`len(name) == ULID_LENGTH`).

## Scope

1. **In-bucket name becomes `<ULID>-<original_name>`** (ADR 026
   pin 1). The whole name tail-truncates to `MAX_SEGMENT_LENGTH`
   (255 bytes) without ever splitting a UTF-8 sequence; the fixed
   26-byte ULID prefix is untouchable by position, so uniqueness and
   time-sorted listings survive any truncation. The name is display
   only — `original_name`/`original_parent_id`/`deleted_at` stay the
   sole authority; nothing parses a trash name.
2. **Delete reports the trash location** (ADR 026 pin 2, mechanism
   resolved here): a new `Observation` **query field** `trash_path` —
   a fact about *(entry, operation)*, exactly the model's definition
   of a query field, with `status` as precedent. Stamped on every
   trashed row's observation, including covered/subsumed targets
   (derived from the snapshot: the outermost covering target's trash
   name plus the old suffix — deterministic, order-independent).
   Unpopulated for permanent purges and for a root the bucket-chain
   cycle forces to purge. `with_mount`/`without_mount` rebase it
   alongside `path`. The delete one-liner renders it
   (`Deleted /a.txt → /.vfs/trash/...`) for single-target results.
3. **Contract wording**: `topology.py`'s module contract and
   `_reparent_to_trash` drop the "name swapped to the entry's ULID"
   language.

## Acceptance criteria

- Bucket listings show `<ULID>-<original_name>`; extension survives;
  same-named same-hour deletes differ by ULID prefix.
- Truncation: a name that would exceed 255 bytes keeps the full ULID
  prefix and cuts only the tail, never mid-UTF-8-sequence — pinned
  with a multi-byte character straddling the cut.
- Budget interaction: a maximal 255-byte original name still fits the
  1,024-byte path budget by construction (the bucket prefix + name
  tops out at ~281 bytes); the descendant-rewrite refusal
  (`unaddressable`) stays the only overflow gate, with its byte math
  re-pinned against the longer prefix.
- Every trashed observation carries `trash_path`; it resolves (stat/
  read succeed at it); covered targets report their derived address;
  `permanent=True` leaves it unpopulated.
- The `Observation` drift tests admit `trash_path` as a query field on
  no model; mount rebasing carries it.
- Full suite, `ruff`, `ty` at zero; all four Docker engine legs green
  (`BytewiseString` truncation is exactly where engines differ).

## Non-goals

- The restore verb and its `(original_parent_id, original_name)`
  index (next spec — which must also true up ADR 026 pin 3's stale
  "indexed" claim against `models/rows.py`).
- The sweep verb and retention policy (blocked on the open question).
- Memory-backend changes (it hard-deletes; no trash contract there).
