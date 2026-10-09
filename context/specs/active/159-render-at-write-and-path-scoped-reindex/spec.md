# 159 — A binary body is readable when `write` returns: render at write time, and a path-scoped reindex

- **Status:** draft — cut 2026-10-08 from the SmartOwl integration memo
- **Date:** 2026-10-08
- **Owner:** Clay Gendron
- **Kind:** feature (database backend: the write pipeline's render
  stage; `reindex` gains a scope)
- **Depends on:** 152 slices A and B (bytes in and out; the renderer
  seam and the `render` stage of `reindex`), the single-runner reindex
  lease (`backend.py`), the fingerprint-skip law (`indexing.py`).
- **Research it stands on:**
  `../../../research/2026-10-08-smartowl-workspace-integration-issues.md`
  item 21; 152's research memo for the renderer costs.

## Intent

Today a binary `write` stores the bytes with `render_status` pending.
Until a `reindex()` runs, `read` returns a warning with no content and
`grep` and `glean` skip the file. `reindex()` covers the whole storage
under one lease, and a second concurrent run refuses `conflict`. So a
host's upload endpoint has to call `reindex()` after every upload and
retry on `conflict`, or show "indexing…" until a background run lands.
Neither is what an agent that just wrote a PDF and wants to grep it
expects.

One line: a small write renders its own entries before it returns; a
big one leaves them for a reindex that can be told which subtree to
visit.

## Decided semantics

1. **`write` renders inline below a budget.** When a write batch holds
   at most N bytes entries (a declared constant beside the chunking
   budgets, say 16) and each is under the per-format size budget 152
   already declares, the write pipeline runs the render stage for
   those entries in the same transaction as the body, then chunks and
   indexes the rendering as a text write would. The entry leaves
   `write` with `render_status` rendered or failed-with-reason, never
   pending. Above the budget the batch takes the pending path as
   today, and the result carries an info record saying so.
   `[NEEDS CLARIFICATION: the inline budget as an entry count, a byte
   total, or both? Leaning both: ≤16 entries and ≤32 MiB of bytes.]`
2. **`reindex(paths=…)` scopes the run.** The verb takes the same
   `paths` channel as the search verbs. A scoped run claims the same
   single-runner lease (two runners on overlapping subtrees would race
   the skip law), visits only entries under the given prefixes, and
   leaves the storage-wide statistics untouched; a full run still
   recomputes them. A scoped run is the host's "index this folder
   now" without paying for the corpus.
3. **A rival run queues, it does not refuse.** `conflict` stays the
   classification when the caller asks for it (`wait=False`); the
   default waits on the lease up to a declared timeout and then runs.
   `[NEEDS CLARIFICATION: queue by default, or keep refuse-by-default
   and add `wait=True`? Leaning wait by default for the scoped form
   and refuse by default for the full form.]`

## Scope

- The inline render branch in the write pipeline, sharing the render
  stage's code with reindex (one renderer call site, two entry
  points).
- `reindex(paths=(), *, wait=…)`; the scoped visit joins the path
  index the way `glob`'s scope does.
- Operation-count tests: a write of two PDFs runs two render calls and
  zero reindex calls; a write of twenty runs zero render calls and
  stamps pending.
- Out of scope: new renderers, OCR (152 names it out), the images
  slice (152 C).

## Acceptance criteria

- `write` of one PDF under budget returns an observation with
  `render_status == "rendered"`, and an immediate `grep` finds a word
  from the PDF.
- `write` of a batch over budget returns `pending` entries and an
  info record naming the budget; `reindex(paths=("/uploads",))`
  renders them and leaves the rest of the storage's stamps untouched.
- Two concurrent scoped reindexes both complete; the second waits.
- `scripts/ci.sh 3.13` green; the Postgres engine leg green.
