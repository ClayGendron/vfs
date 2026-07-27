# 088 — Error attribution: helpers carry the caller's target

- **Status:** landed 2026-07-26 (`67aa7bd`, one landing with specs
  086/087; all four engine legs green) — awaiting the backward-flow
  mining pass, then deletion. The hand-rolled `exists` site was already deleted by
  087 decision 3; the helper extensions and site adoptions landed as
  specified.
- **Evidence:**
  `context/research/2026-07-26-writes-topology-review-verification.md`
  §2 — all four findings cite-checked; the restore attribution loss
  demonstrated live on Postgres.
- **Depends on:** spec 087 (decision 3 deletes one of the affected
  sites; land 087 first).

## Problem

The envelope declares `already_exists` "the one construction" of the
occupied-site `exists` classification, and the classification ladder's
convention is that an error whose `path` is not the caller's requested
row stamps `data["target"]` with what the caller asked for. Both are
violated in topology: the claim-race handler hand-rolls a second
`exists` construction because the helper cannot carry `data`; restore's
no-replace refusal drops the requested trash-side target entirely
(demonstrated: the error is unattributable in a batch, and two trash
rows refusing to the same dest collapse under the envelope's
value-identity dedup); and the occupant kind-mismatch refusals bypass
`wrong_kind()`, naming no kind where every sibling module names one.

## Decisions this spec owns

1. **`already_exists` and `wrong_kind` gain optional attribution** —
   `target=` (and, where 087 leaves a consumer, a data-detail merge)
   — delegating to `classified`, which already models `target`. The
   monopoly docstrings stand; the helpers just stop forcing violators.
2. **Topology adopts the helpers everywhere.** The restore no-replace
   refusal stamps the requested target; the transfer-verb
   `already_exists(dest)` site stamps the pair's src-side attribution;
   the two "Cannot {op} onto" sites become
   `wrong_kind(occupant["kind"], dest, target=...)`. Message text is
   declared non-load-bearing; conformance pins kinds, which do not
   change.
3. **Writes' arbitration losses stamp target parity** where the
   error's path is the caller's own row (polish, no information
   change).
4. **`_PendingTransfer` moves to the shared-types tier** — it serves
   two banner groups; the tier rule places it beside
   `_SNAPSHOT_COLUMNS`. Cut/paste only.

## Acceptance criteria

- One construction of `exists` and of the occupant kind refusal across
  `src/`; no hand-rolled `ResultError(kind=exists)` in topology.
- A trash-side restore refusal carries the requested trash path in
  `data["target"]`; two same-dest refusals no longer dedup-collapse.
- Full suite, `ruff`, `ty` at zero; conformance kind pins unchanged.

## Non-goals

- Unifying the two `wrong_kind` message vocabularies across
  descent/results ("Not a directory" vs "Is a directory") — a
  results-vocabulary question for a contract review, filed in
  `open-questions.md` if pursued.
