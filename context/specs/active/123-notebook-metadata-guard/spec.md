# 123 — The notebook fallback promise kept: no metadata shape wedges reindex

- **Status: draft, 2026-08-25.**
- **Born from** the chunking-arc landing review
  (`../../../research/2026-08-25-chunking-arc-landing-review.md`),
  finding F9 — pre-existing at the review's base and flagged rather
  than charged ("would be major if in range"). The 2026-08-25
  decision pass ruled to fix it regardless of provenance: a
  user-writable file wedging a maintenance verb is not triaged away
  on a technicality.
- **Date:** 2026-08-25
- **Owner:** Clay Gendron
- **Kind:** robustness fix in the chunking model's notebook splitter.
  Well-formed notebooks split identically before and after.
- **Depends on:** the chunking model (`models/chunking.py`), spec 117
  (whose `split_batch` added the second call site that widens the
  blast radius).
- **Relates to:** the trash-path lead (are trashed .ipynb bodies
  excluded from the chunk pass by law or by dirty-flag accident? —
  recorded in the memo, not taken up here).

## Intent

**`split_notebook` promises "malformed notebooks fall back to the
recursive splitter" and keeps the promise only for the cells
extraction.** The metadata reads are unguarded: a *valid* .ipynb
(json-parseable, schema-plausible) whose `metadata` is a list, or
whose `kernelspec.language` is a non-string (`42`), raises a raw
`AttributeError` out of the splitter. Because the chunk pass splits
every dirty body, one such user-writable file wedges **every
subsequent `reindex()`** until the file is deleted — executed
end-to-end: grep still serves via the scan overlay, and reindex
recovers only after deletion. The function, its docstring, and the
crash are byte-identical at the review's base; the reviewed set
added a second unguarded call site (`split_batch`) and rebatched
around it without re-asserting the promise.

Laws that bind the slice:

1. **The docstring is the contract:** any notebook the JSON parse
   admits either splits as a notebook or falls back to the recursive
   splitter — no input shape may raise out of the splitter.
2. **Well-formed notebooks are untouched:** the guard discipline
   must not change the split of any notebook the current code
   handles; the committed chunking fixtures are the referee.
3. **The batch and single forms stay pinned equal** across the new
   malformed shapes, per the existing parity convention.

## Shape

- **§1 The guards.** The `metadata` / `kernelspec` / `language`
  reads take the same isinstance discipline the cells path already
  has: any shape violation routes to the recursive-splitter
  fallback, per the docstring. Sweep the function for the same class
  of unguarded read while in there — the fix is a discipline, not
  two call sites.
- **§2 The pins.** A malformed-notebook battery: metadata-as-list,
  `kernelspec.language: 42`, kernelspec-as-string, and the
  already-handled cells shapes as controls — each asserting fallback
  (not raise), on `split` and `split_batch` alike, plus one
  end-to-end row: a wedging notebook written into a store, then
  `reindex()` completes and the file is chunked by the fallback.

## Slices

One slice — guards and battery together.
