# 047. The Storage Seam Takes Branded Paths; Hydration Law for Every Reader; Maintenance Batched Once per Call

- **Status:** accepted 2026-08-18 — spec 111's decision set, written
  at the 107–116 mining pass (2026-08-19). Extends ADR 041's hydration
  law (declared for grep's assembly) to every backend reader and
  states the seam precondition it rests on; ADR 040 §2's batched
  `move_postings` shape becomes what delete actually issues.
- **Date:** 2026-08-18
- **Deciders:** Clay Gendron (the "wins are measured where the
  finding measured" law); the ls-precondition fork settled by
  declaration in session.
- **Context source:** the 2026-08-18 review campaign
  (`../research/2026-08-18-glob-grep-review-campaign.md`, findings 7,
  10, 11 — `Path(str)` 8.77 µs vs `Path._brand` 0.15 µs per row at
  38.9 % of a 20k-row glob; delete paying 40 % of a 72 s 10k-target
  run in single-element `move_postings` calls on live Postgres; the
  allow-list's corpus-width union, 103 MB traced at a 1M-entry
  scope). Implemented by spec 111; widths pinned by spec 113.

## Context

ADR 041 declared backend row hydration a branded site — stored paths
are canonical by invariant, so re-validating them per row is waste —
but only grep obeyed it: `reads._observe` (read/stat/ls/tree/glob)
ran the full gate per row and glob minted a second gated `Path` per
candidate. Delete called the batch-native `move_postings` once per
target. And the review's adjacent lead — `ls(path="/flat")` with a
plain `str` dying as a raw `AttributeError` at the storage seam —
needed the seam's precondition either declared or refused.

## Options considered

- **Seam precondition: declare branded `Path` loudly, or refuse a bare
  `str` typed** — declared: the storage protocol docstring states
  paths cross the seam as branded `Path` objects and a bare `str` is
  out of contract; string-holding callers go through the router,
  which resolves. A typed refusal at every backend entry would pay a
  per-call check to serve a caller the contract already excludes.
- **Batch the move/restore executor too** — inspected and left
  per-pair with the reason recorded: its descendant work already
  batches, the root move is one triple per pair (no 10k-per-call
  contract shape), and the occupant-trash interleave would need its
  own deferral-hazard audit; revisit when a measurement names it.

## Decision

1. **Paths cross the storage seam as branded `Path` objects.** The
   seam's precondition, declared in the protocol docstring; the
   router is where strings become paths.
2. **Every backend reader hydrates by re-brand, and row-fact gates run
   over ridden columns.** `_observe` re-brands stored paths; glob's
   candidate gate is `passes_row_filters` over `name`/`ext` columns
   queried beside the caller's mask and stripped from the observation
   (the ride vocabulary is `ROW_GATE_FIELDS`, declared once beside the
   gate — spec 116). Measured: glob 311 → 146 ms, ls 277 → 204 ms on
   the finding's 20k-row shapes, counts identical.
3. **Delete accumulates its root posting deltas and flushes one
   `move_postings` batch per call after adjudication.** Nothing in the
   loop reads segments; refused targets never accumulate; the
   expired-bucket 1:1 delta lawfully rides the rename fast path.
   Measured at the 10k-target contract: sqlite 21.8 → 16.0 s, live
   Postgres 48.5 → 36.0 s (−26 % both).
4. **Wins are measured where the finding measured, and batch widths
   are pinned by the mirror referee.** A change that fails to
   reproduce its predicted win is re-examined, not shipped; the
   segment-mirror battery carries multi-target delete, multi-pair
   move, and multi-target restore rows (spec 113), because a
   last-delta-only mutant survived every single-target row.
5. **Corpus-scaled allocations are acknowledged, never capped.**
   `pathterms` carries the measured profile of its in-memory union and
   names the SQL-side join as the future direction; no size limit is
   implied — the no-designed-caps rule in docstring form.

## Consequences

- Backend entry points may assume a branded `Path`; a caller holding
  a `str` is a router caller.
- A new row→model site follows the re-brand pattern; a sweep for
  stragglers (tree assembly, conformance helpers) is cheap follow-up
  once three exemplars exist.
- Any verb doing per-item maintenance a batch API exists for is a
  finding; any batching it lands must carry a batch-width mirror row.
