# 089 — Descent shared idioms: name the bounded-SQL loops once

- **Status:** open — born 2026-07-26 from the post-086 verification
  campaign's extraction review (small refactor; spec.md only).
- **Evidence:**
  `context/research/2026-07-26-writes-topology-review-verification.md`
  §3 — all sites cite-verified; the escaped-LIKE behavior pinned
  empirically on all four engines; import-cycle feasibility checked.
- **Depends on:** specs 087 and 088 (land first — this refactor moves
  already-correct code; net behavior change is zero by definition).

## Problem

Five call sites across writes/topology/reads independently implement
the identical bounded fetch loop — `chunked(paths, membership_budget)`
→ `path IN (chunk)` → merge into a dict — and six sites compose the
escaped subtree-LIKE predicate by hand. Both idioms are
correctness-relevant (the chunk budget is the Oracle/MSSQL floor; a
future site forgetting `escape=` is an injection-shaped bug class
nothing currently pins), and every scale review re-audits each copy.
The campaign's extraction review confirmed these are genuinely one
concept each — and equally confirmed that the larger resemblances
(guard ladders, savepoint claims) are not, so this spec's scope is
exactly the idioms and no more.

## Decisions this spec owns

1. **`rows_by_path` kernel in `descent.py`** — bounded membership
   select merged into a `dict[str, RowMapping]`; parameters: columns,
   caller-computed path iterable, budget, optional `source` for the
   content join. A separate **`targets_with_ancestors`** set builder
   serves the two snapshot sites; no `ancestors=` flag on the kernel
   (one site needs chain-without-target, which a flag cannot express).
   Call sites: writes `_fetch_committed`, topology `_fetch_snapshot`,
   `_final_rows`, `_dest_parent_id`'s fetch half, reads
   `_mappings_by_path` (reshaping reads' `_entry_select` into a
   (columns, source) computation). The id-keyed loops are a different
   family and stay put.
2. **`subtree_filter` / `descendant_filter` in `descent.py`** —
   self-or-descendants and strict-descendants predicates, composed on
   `escape_like` with `escape=` always explicit. The helper owns the
   ROOT branch (naive composition yields `//%`). `liveness_filters`
   recomposes as conjuncts on `descendant_filter` — never a negated
   `or_` (SQL text change). Glob's bare-prefix LIKE is excluded.
   Call sites: topology `_purge_subtree`, `_fetch_subtree`,
   `_descendant_rewrites`; reads `tree_rows`, `_anchor_fan`; descent
   `liveness_filters`.
3. **Riders:** `miss_errors` promoted from reads to `descent.py`
   beside `classify_misses` (writes' inline copy adopts it);
   `supports_values_update(profile, dialect)` into `dialects.py`
   (capability arbitration is its charter; two writes sites).
4. **LIKE-metachar paths become conformance pins.** The campaign's
   decoy family — `%`, `_`, and backslash paths beside near-miss
   siblings, exercised through write/tree/glob(pattern and scope
   anchor)/cascade delete/trash-side tree — lands in the conformance
   suite, engine-legged. Nothing currently pins this class.

## Acceptance criteria

- The named call sites import from `descent.py`/`dialects.py`; no
  behavioral diff (same statements modulo bind names, verified by the
  suite), net negative line count.
- `descent.py` gains no import from writes/topology/reads (cycle-free,
  as today).
- The metachar conformance family passes on sqlite and all four engine
  legs.
- Full suite, `ruff`, `ty` at zero; coverage held.

## Non-goals

- The guarded-statement primitive, savepoint-claim combinator,
  chunked-insert recovery, error-text constructors, and observation
  assembly — examined and rejected by the extraction review; the
  resemblances are mechanism-level echoes of deliberately different
  concurrency postures.
