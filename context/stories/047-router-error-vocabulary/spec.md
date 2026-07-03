# 047 — Router Input Errors Speak the Caller's Vocabulary

- **Status:** draft
- **Date:** 2026-07-03
- **Owner:** Clay Gendron
- **Kind:** fix (two small caller-facing correctness nits) — a
  spec-only small story per the README
- **Depends on:** 036 (the verb surface these messages describe)
- **Relation to 040:** adjacent but disjoint — 040 fixes *gate* errors'
  structured payloads; this fixes two *input-shape* errors upstream of
  any gate. Land in either order; trivial to fold into 040's PR if that
  is less ceremony.

## Intent

Two places where the router's answer misdescribes the question:

1. **`write()` with no input reports another verb's parameters.**
   `write()` (no entries, no path) delegates to `_route_single`, whose
   neither-nor branch answers *"Exactly one of path or observations must
   be provided"* (`base2.py:540-545`). `write` does not take
   observations — the caller is told to supply a parameter that does not
   exist on the method they called. Fix: `write` validates its own input
   shape before delegating and reports in its own vocabulary ("write
   requires entries, or path with content"), the same pattern `edit` and
   `_route_pairs` already follow for their sugar forms.

2. **`_merge_results([])` loses the op.** The empty-input branch returns
   `Result(observations=[])` with `function=""` (`base2.py:856-857`),
   while every populated merge carries the op through from its inputs.
   The branch is defensive-only today (every caller merges a non-empty
   settled list), which is exactly why it will surface at the worst time
   — a future caller with a legitimately empty group set gets a result
   that renders generically and can't be dispatched on. Fix: `_merge_
   results(results, function=op)` — callers pass the op they already
   hold; the empty branch stops being a special case.

## Test plan

1. `write()` with no arguments → `invalid`, message names `entries` and
   `path`/`content`, `function == "write"`; same for `write(entries=None,
   path=None, content="x")` (content without path).
2. Existing mutual-exclusion case (`entries` + `path`) unchanged.
3. `_merge_results([], function="glob")` → empty success with
   `function == "glob"`; a populated merge keeps today's behavior
   (parametrize both).

## Out of scope

- Gate-error payloads (`path=None` inconsistencies) — 040 owns those.
- Any message *wording* changes beyond the two sites named.
