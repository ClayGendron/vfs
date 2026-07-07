# 050 — Spine Classification Diverges by Input Shape for Non-Listing Reads

- **Status:** closed by 056 (2026-07-07) — the spine and the second
  funnel are gone; both input shapes classify through the same
  entry-keyed dispatch.  The inherited design question is settled:
  grouped reads classify per row (atomicity is a mutation concern);
  grouped mutations stay rejected whole at the gate.
- **Date:** 2026-07-07
- **Owner:** Clay Gendron
- **Kind:** fix (behavioral-contract inconsistency) + small design decision
- **Depends on:** 041 (mount spine visibility — the classification rule),
  040 (the one terminal gate)
- **Enables:** the chained-rows contract holding uniformly — a result's
  observations mean the same thing fed back through any verb

## Intent

Make a spine path classify the same way through every input shape.
Today the classification depends on how the caller addressed it:

- `read("/data")` (single path, `/data` on the spine) →
  `wrong_kind` ("Is a directory") from `_gate_terminal`'s spine step.
- `read(observations=[Observation(path="/data")])` → the gate runs
  with `spine_check=op in MUTATING_OPS` (`_dispatch_grouped_observations`),
  which is `False` for reads — so the row dispatches into local storage
  and surfaces whatever storage says, typically `not_found`.

Same verb, same path, different error kind. `graph` has the same
divergence. The gate's docstring calls the grouped-read carve-out
deliberate ("the rest dispatch as today"), but the observable result
contradicts story 041's own rule: a spine path fails *exactly the way a
stored directory fails* — `wrong_kind`, never `not_found`.

## Why

- The chained contract is the product surface: `ls` rows feed `stat`,
  `stat` rows feed `read`. An agent that `ls`-es `/`, gets the spine
  row `/data`, and chains it into `read` sees `not_found` for a
  directory it was just told exists. That reads as namespace
  inconsistency, not as a kind error.
- The two kinds drive different caller behavior: `not_found` invites
  retry/create; `wrong_kind` says "wrong verb for this entry." The
  spine case is unambiguously the latter.

## Scope

- In `_dispatch_grouped_observations`, classify a spine-path row for
  every non-spine-read verb as `wrong_kind`, matching the single-path
  gate — i.e. the spine check should not be conditioned on
  `MUTATING_OPS` alone. `ls`/`stat`/`tree` keep their upstream peel.
- Same-shape check for the scoped fan-out path (`_route_fanout` with
  `paths=`): a scope resolving to a spine path deliberately *expands*
  (story 041) — that stays; this story touches only row-shaped input
  to non-listing verbs (`read`, `graph`, and grouped mutations already
  handled).
- Tests: extend `test_non_listing_verbs_classify_spine_paths_as_directories`
  with the observation shape; keep the `/data/ghost` `not_found`
  contrast in both shapes.

## Acceptance criteria

- For a router with a mount at `/data/a`:
  `read(observations=[Observation(path="/data")])` fails `wrong_kind`
  with `path == "/data"`, identical to `read("/data")`.
- Same for `graph(method, observations=...)`.
- A non-spine absent path keeps `not_found` through both shapes.
- No change to `ls`/`stat`/`tree` grouped behavior (spine peel) or to
  mutation classification (already `wrong_kind`).

## Open questions

- `[NEEDS CLARIFICATION]` Should the batch reject whole (matching the
  all-gates-before-any-dispatch rule) or classify per row? The
  mutation path rejects whole today; reads have no partial-execution
  hazard, but consistency argues for whole-batch rejection.
