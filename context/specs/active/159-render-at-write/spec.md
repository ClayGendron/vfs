# 159 — A binary body is readable when `write` returns: render at write time below a budget

- **Status:** draft — cut 2026-10-08 from the SmartOwl integration memo;
  revised 2026-10-08 after a review against `0760fe9` (rendering stays
  outside the transaction; a text write chunks nothing; no per-format
  byte budget exists; `"rendered"` is not a status). Narrowed the same
  day (Clay): the path-scoped reindex and the wait-on-lease rules are
  dropped, because the posting index is whole-corpus (`build_epoch`
  rebuilds the full posting set under a fresh epoch) and a scoped run
  could only render and chunk, never index. A rival reindex keeps
  refusing `conflict`.
- **Date:** 2026-10-08
- **Owner:** Clay Gendron
- **Kind:** feature (database backend: the write pipeline gains a
  pre-transaction render step)
- **Depends on:** 152 slices A and B as landed (`be504a3`):
  `render_rows` (pure, no session, `render.py` L268–280),
  `_render_step` (blobs in a short read, render on the offload pool
  with no transaction open, land in a short write; `backend.py`
  L1152–1186), `land_renderings`' guarded stamp, `RenderLimits`
  (`seam.py` L66–76: `chars`, `ratio`, `embedded_*`, `pages`,
  `seconds = 60.0`), `RenderStatus` and `RENDERED_STATUSES = {ok,
  truncated, partial}` (`media.py` L21–36), the fingerprint-skip law
  (`indexing.py` L258), `_material_values` (`writes.py` L1098–1102).
- **Research it stands on:**
  `../../../research/2026-10-08-smartowl-workspace-integration-issues.md`
  item 21; 152's research memo for the renderer costs.

## Intent

Today a binary `write` stores the bytes with `render_status` pending
(`writes.py` L1102). Until a `reindex()` runs, `read` returns a warning
with no content and `grep` and `glean` skip the file. `reindex()`
covers the whole storage under one lease, and a second concurrent run
refuses `conflict`. So a host's upload endpoint has to call `reindex()`
after every upload and retry on `conflict`, or show "indexing…" until a
background run lands. Neither is what an agent that just wrote a PDF
and wants to grep it expects.

One line: a small write renders its own entries before it returns; a
big one leaves them pending for the next full reindex, as today.

## Decided semantics

1. **`write` renders inline below a budget, outside the transaction.**
   When a write batch holds at most `INLINE_RENDER_ROWS` bytes entries
   (16, declared in `render.py` beside `RENDER_PAGE_ROWS`) whose bytes
   total at most one `BLOB_PAGE_BYTES` (8 MiB, `dialects.py` L102),
   the write pipeline renders them on the offload pool **before** its
   transaction opens: `render_rows` over the bytes already in hand (the
   write holds bytes, hash, mime and name, exactly its input), no
   session. The render runs under a lowered `RenderLimits.seconds`
   (`INLINE_RENDER_SECONDS`, 5.0) so a write's latency is bounded; a
   render cut by it lands `partial`, and the next reindex does not
   retry it (same stamp). The transaction then commits body, stamp and
   rendering text together, landing through `land_renderings`' guarded
   stamp so a rival reindex's identical stamp is a no-op and a bytes
   change a miss. The rendering lands as a content row with `chunked`
   and `encoded` reset, exactly as a text write leaves its body:
   grep and glean's lexical leg serve it from the scan side at once,
   and the next full reindex splits, encodes and indexes it. No render
   ever runs while a transaction is open; `_mutate`'s redrive never
   re-renders. The entry leaves `write` with `render_status` in
   `RENDERED_STATUSES` or a settled failure, never `pending`.
2. **Above the budget, nothing changes.** The batch takes the pending
   path as today, and the result carries an info record naming the
   budget and saying a full `reindex()` renders the rest.
3. **Reindex is unchanged.** It stays whole-corpus under the single
   lease, and a rival run refuses `conflict`. There is no scoped form:
   the posting index is built whole under an epoch, so a run that
   visited one subtree could render and chunk it but not index it.

## Scope

- The pre-transaction render step in the write pipeline, sharing
  `render_rows` and `land_renderings` with reindex (one renderer, two
  entry points); the three constants; the over-budget info record.
- The reindex result's `rendering` extra counts inline-rendered rows
  as already rendered (they carry a matching stamp), not as work done.
- Operation-count tests: a write of two PDFs runs `render_rows` once
  over two rows and no reindex; a write of twenty runs no render and
  stamps pending; the existing render tests' spy pattern
  (`test_render.py` L512–545) is the model.
- Out of scope: new renderers, OCR (152 names it out), the images
  slice (152 C), any change to `reindex`.

## Acceptance criteria

- `write` of one PDF under budget returns an observation with
  `render_status == "ok"`, and an immediate `grep` finds a word from
  the PDF with no reindex having run.
- `write` of a batch over budget returns `pending` entries and an info
  record naming the budget; a following `reindex()` renders them.
- A second `reindex()` while one holds the lease still refuses
  `conflict`.
- `scripts/ci.sh 3.13` green; the Postgres engine leg green.
