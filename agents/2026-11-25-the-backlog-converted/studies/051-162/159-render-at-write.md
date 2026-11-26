# Study: A binary body is readable when write returns, rendered at write time below a budget

## Verdict

live-0.2. Nothing of the spec is built: a bytes write still lands `render_status = 'pending'` and no render runs on the write path (READ `src/vfs/storage/backends/database/writes.py:1217`; EXECUTED grep for `INLINE_RENDER` over `src/vfs` found nothing). The roadmap places it in E8 at gate 0.2, with D21's unruled lean "No, unless the first served pilot hits it" (READ `context/standards/roadmap.md:582-584`, `:1052`, `:1093`).

The problem is narrower than the spec states: the landed incremental verb `refresh()` renders only the bytes rows a write changed at O(dirty) (READ `src/vfs/storage/backends/database/maintenance.py:152-176`), so a host no longer has to run a whole-corpus pass after an upload; it still has to run a lease-holding pass, and a rival run still refuses (READ `maintenance.py:199-215`). The gap that remains is that the write itself returns an unreadable binary (INFERRED).

## Against the tree

Tree read at HEAD `3166469` on 2026-11-25 (EXECUTED `git log --oneline -1`); the task names `0ed462f`, and every fact below is from the checkout as it stands.

What the spec depends on, and where it stands now:

- `render_rows` is pure, takes rows, blobs, registry, limits and a cache, and runs whole on the offload pool (READ `src/vfs/storage/backends/database/render.py:278-310`). The spec's citation `render.py L268-280` is stale in line only.
- `land_renderings` is the guarded stamp: one UPDATE per row guarded by `source = 'bytes'`, `content_hash = b_hash` and "not already this stamp", then deletes and re-inserts the content rows in `BLOB_PAGE_BYTES` pages and resets `chunked`, `encoded`, `indexable` and `chunk_source_hash` (READ `render.py:320-391`). It answers `Result(ops=("rebuild",))` (READ `render.py:344`, `:391`), so a write-path caller must not forward its ops (INFERRED).
- `_render_step` has moved from `backend.py` to `maintenance.py` and takes a `MaintenanceContext` with a `regenerate` flag (READ `maintenance.py:414-480`); the move is the landed spec `context/specifications/archive/2026-11-12-the-full-pass-is-named-rebuild-and-its-pipeline-leaves-the-backend.md:101`, `:177`.
- `RenderLimits` lives in `src/vfs/rendering/seam.py:96-120` and now carries container limits beside `seconds` (READ). `RENDER_SECONDS = 60.0` (READ `seam.py:64`). `seconds` is applied per render, a `Deadline(at=started + limits.seconds)` inside each renderer (READ `src/vfs/rendering/docx.py:64`, `pptx.py:39`, `xlsx.py:106`, `markdown.py:115`).
- `RENDERED_STATUSES = {ok, truncated, partial}` (READ `src/vfs/models/media.py:36`). `RENDER_PAGE_ROWS = 256` (READ `render.py:67`). `BLOB_PAGE_BYTES = 8 MiB` (READ `src/vfs/storage/backends/database/dialects.py:103`).
- `_material_values` is at `writes.py:1194-1221` and resets every render stamp to pending for a bytes row (READ).
- The write path already runs one pre-transaction offloaded hop, `measured_entries(entries, offload_pool())`, before `_execute_write` opens a session (READ `src/vfs/storage/backends/database/backend.py:689-691`, `writes.py:144-160`). That is the seam an inline render would sit beside (INFERRED).
- A read of a pending bytes row answers an `unavailable` warning, retryable, "the binary awaits a rendering; run rebuild" (READ `src/vfs/storage/backends/database/reads.py:865-900`).
- grep's overlay scans `NOT encoded` rows, so a rendering landed with `encoded = False` is served by grep at once without any index pass (READ `src/vfs/storage/backends/database/grep.py:1-38`; declared `grep_staleness: "overlay"` at `backend.py:259`). The spec's claim that grep serves the rendering "from the scan side at once" holds (INFERRED from both).
- `InMemoryStorage` has no render step at all (EXECUTED grep for `render` over `src/vfs/storage/backends/memory.py`, no hits). The spec is database-only and says so implicitly; the conversion should say it explicitly (INFERRED).

Later landed work that changed the ground:

- `reindex` is renamed `rebuild` (READ the 2026-11-12 archive spec above, `:83-85`).
- `refresh()`, the incremental pass, landed 2026-11-13 and runs the render step with `regenerate=False` over rows whose bytes a write changed, then chunk, delta build and embed, at O(dirty) (READ `context/specifications/archive/2026-10-31-refresh-the-incremental-index-verb.md:182-186`; `maintenance.py:152-176`; roadmap table `context/standards/roadmap.md:519`). The reference deployment runs a partial pass every 15 minutes, floor 1 minute (READ `AGENTS.md`, reference-deployment table), so without this spec a binary is unreadable for up to one pass interval (INFERRED).
- `glean` is renamed `search` (READ `context/specifications/archive/2026-11-09-the-verbs-take-the-names-agents-know.md:1`). EXECUTED grep for `glean` over `src/vfs`: no file.
- Decided 2026-11-15 (D7): `overwrite=` leaves `write`; transfers use `replace=` (READ `context/standards/roadmap.md` §16 row D7). At HEAD `write` still takes `overwrite` (READ `backend.py:681-688`); spec 174 carries the change. The spec does not name `overwrite`, so this binds only a conversion that shows the signature (INFERRED).

The problem statement at HEAD: still true that a write returns `pending`, a read warns with no content, and grep finds nothing in the binary until a pass runs (READ `writes.py:1217`, `reads.py:886-888`). No longer true that the only remedy is a whole-corpus pass (READ `maintenance.py:152-166`).

## Where the roadmap places it

- `context/standards/roadmap.md:531`: Domain E state table, "Renderers pdf/docx/pptx/xlsx; failures as row states | built; images (152 C) and render-at-write (159) planned" (READ).
- `context/standards/roadmap.md:582-584`: story E8, "Render at write (159), images (152 C), `imports` edges (147), tuned fusion defaults · gate 0.2. Independent of theme 3. Render at write moves up if D21 says so." (READ).
- `context/standards/roadmap.md:1052`: §15 "Deliberately not in 0.1.0", "render at write (159) ... 0.2 unless D21" (READ).
- `context/standards/roadmap.md:1093`: D21, "Render at write (159) in 0.1.0?", lean "No, unless the first served pilot hits it.", not marked Decided (READ).

Gate: 0.2 unless D21 is ruled otherwise (READ).

## Units proposed

One unit. The spec is a single landing: one pre-transaction step, three constants, one info record and the counted tests; nothing in it lands apart (INFERRED from spec.md §Scope).

- Slug: a small binary write renders its own bytes before it returns. Title: "A write of at most sixteen binaries totalling one blob page renders them outside its transaction and returns them readable and greppable; a larger write stays pending for the next refresh or rebuild." Gate: 0.2 (moves to 0.1.0 only if D21 is ruled so). Depends on: the landed render seam and `refresh()`; D21 for placement; spec 174 only if the converted text shows `write`'s signature. Rewrite depth: amend (the design stands; names, paths, the `reindex`/`refresh` facts and the latency arithmetic changed).

## Open choices, each verified

The spec carries no `[NEEDS CLARIFICATION]` marker (READ spec.md). Its choices are stated as decided on 2026-10-08 but never reviewed to "Fit to build" (READ spec.md:3), so each is verified here as a lean.

1. Placement in 0.1.0 or 0.2. Lean: 0.2 unless the first served pilot hits it (roadmap D21). Verification: needs-a-ruling. It is a product choice not ruled in §16 (READ `roadmap.md:1093`). Needs a ruling: D21, render at write in 0.1.0 or in 0.2.

2. The budget: inline when a batch holds at most 16 bytes entries totalling at most `BLOB_PAGE_BYTES` (8 MiB). Verification: holds. Precedent: the write path already switches on a byte total before its transaction, `MEASURE_OFFLOAD_BYTES` in `measured_entries` (READ `writes.py:152-154`), and the render step already cuts pages by `BLOB_PAGE_BYTES` (READ `maintenance.py:453`). It is a branch on batch size, not a scale cap: above it the write is served exactly as today and the 10,000-file batch contract is untouched (INFERRED against AGENTS.md's production posture).

3. Latency bound: `INLINE_RENDER_SECONDS = 5.0` replacing `RenderLimits.seconds`. Verification: holds-amended. `seconds` is a per-render deadline (READ `docx.py:64` and siblings) and `render_rows` renders rows serially in one offloaded call (READ `render.py:296-309`), so 16 rows at 5 s each bound a write at about 80 s, not 5 s (INFERRED arithmetic); a verb call lasts tens of milliseconds in the reference deployment (READ AGENTS.md, Concurrency row). Amended text: "the inline step runs under one deadline for the whole batch, `INLINE_RENDER_SECONDS`; each render's `RenderLimits.seconds` is the time left on that deadline, and a row the deadline reaches before its render starts is left pending." Precedent: a call-wide wall shared by bounded work, the landed `context/specifications/archive/2026-11-07-chained-grep-verifies-off-the-loop-under-a-wall.md` and `2026-11-07-bounded-work-has-one-home.md` (READ titles; the shared-wall shape is INFERRED from them).

4. A render the inline clock cuts lands `partial` and the next pass does not retry it. Verification: needs-a-ruling. It is consistent with the skip law, which re-renders only on a bytes or generation change (READ `render.py:1-11`) and with `RenderLimits`' "a raise does not retry an entry already refused" (READ `seam.py:107-108`). But a 5 s inline clock against the pass's 60 s makes a permanently worse rendering for a file the pass would have rendered whole (INFERRED). Needs a ruling: (a) land the cut rendering `partial` and stamped, as the spec says, so the text is greppable now and stays cut until the bytes change; or (b) land the cut text but leave the row stamped pending so the next `refresh` re-renders it under the full limits; or (c) land nothing for a cut row and leave it pending.

5. Render outside the transaction, commit body, stamp and text together through `land_renderings`' guard. Verification: holds. Precedent: the render step already renders with no transaction open and lands in a short write (READ `maintenance.py:419-428`), and `measured_entries` runs its hop before the write session opens (READ `backend.py:689-691`). The guard's `content_hash = b_hash` proves itself in the same transaction after `write_rows` stamps the row pending (INFERRED from `render.py:346-358` and `writes.py:1217`). Amend: the ops of `land_renderings`' answer are not forwarded, since it answers `("rebuild",)` (READ `render.py:344`).

6. The render runs before the gate judges the write, so a refused write may have rendered bytes for nothing. Not named in the spec. Verification: holds. Precedent: `measured_entries` already hashes every body before the gate (READ `backend.py:689-697`); the bytes are the caller's own, so no content crosses a rights boundary, and the work is bounded by choice 2 (INFERRED). The conversion states it.

7. `_mutate`'s redrive never re-renders. Verification: holds. Precedent: the measured entries are computed once outside `run`, which is what the redrive re-enters (READ `backend.py:689-712`; redrive at `backend.py:1466-1503`). The renderings computed beside them are reused the same way (INFERRED).

8. Over budget, the result carries an info record naming the budget and saying a pass renders the rest. Verification: holds-amended. Amended text: the record names `refresh` (the O(dirty) pass) and `rebuild`, not `reindex`; its wording follows the read note's existing "run rebuild" (READ `reads.py:886-887`) or names both verbs. Precedent: the classified info records of the search path ("no_provider" at `roadmap.md:520`, READ).

9. Reindex is unchanged and a rival run refuses `conflict`. Verification: holds-amended. Amended text: "`rebuild` and `refresh` are unchanged; both claim the one index lease and a rival refuses." The scoped form the spec dropped now exists as `refresh` (READ `maintenance.py:152-176`), so the spec's reason ("there is no scoped form") is stale, but the conclusion stands (INFERRED).

10. The pass's `rendering` extra counts inline-rendered rows as already rendered. Verification: holds. Precedent: the guard misses a row already carrying the stamp and the report records only landed rows (READ `render.py:374-390`); under `regenerate=False` the pass reads only `pending` rows, so an inline-rendered row is never read at all (READ `refresh` spec decision 19, archive `:182-186`; diagram `:67`).

## What is stale

- `reindex()` as the only pass: now `rebuild()` (full) and `refresh()` (O(dirty)) (READ `maintenance.py:141-176`).
- "glean": now `search` (READ the 2026-11-09 archive spec, `:1`); also "glean's lexical leg" in §Decided semantics 1.
- `_render_step` at `backend.py L1152-1186`: now `maintenance.py:414` (READ).
- `render.py L268-280` for `render_rows`: now `render.py:278` (READ).
- `seam.py L66-76` for `RenderLimits` with six fields: now `seam.py:96`, with ten fields including four container limits (READ).
- `media.py L21-36`: `RENDERED_STATUSES` at `media.py:36` (READ).
- `dialects.py L102`: `BLOB_PAGE_BYTES` at `dialects.py:103` (READ).
- `writes.py L1098-1102` / `L1102`: `_material_values` at `writes.py:1194`, pending stamp at `:1217` (READ).
- `indexing.py L258` for the skip law: the law is stated at `render.py:6-11` and the chunk fingerprint skip at `indexing.py:261-265` per the refresh spec (READ archive `:214`).
- `test_render.py L512-545` spy pattern: the file imports `render_rows` and `land_renderings` at `tests/storage/database/test_render.py:41`; the cited line range is unverified (READ).
- The read warning: says "run rebuild" (READ `reads.py:886`).
- Acceptance criterion `scripts/ci.sh 3.13`: the gate is `scripts/ci.sh` with 3.13 as its default leg (READ AGENTS.md, Tooling).
- The 152 dependency's commit `be504a3` and the research path `../../../research/...`: the folder is `context/research/2026-10-08-smartowl-workspace-integration-issues.md` (INFERRED from the relative path; not opened).

## Notes for the conversion

- Problem statement: restate against `refresh()`. The gap is the interval between a write and the next pass (15 minutes in the reference deployment, floor 1), during which an agent that just wrote a PDF reads a warning and greps nothing (READ AGENTS.md table; `reads.py:886`).
- Cost it against the reference deployment: the inline step rides the per-file-write multiplier (about 1,050,000 a day) only for bytes writes under budget, and costs one extra round trip per row in `land_renderings` plus the render itself (READ `render.py:333-336`). Human saves are 1,000 to 5,000 a day and are the likely binaries (READ AGENTS.md, Organic change row); the nightly 10,000-file batches are over budget and unchanged (INFERRED).
- Lock posture: the render is outside any transaction, and the landing adds the guarded UPDATE and the content insert to the write's own commit, so no new lock is held longer than the write's commit (INFERRED from AGENTS.md "Per lock").
- Write the batch-wide deadline (choice 3, amended) and the cut-render rule (choice 4, a ruling) as numbered decisions.
- Say `InMemoryStorage` is out of scope, or give it the same step; it renders nothing today (EXECUTED grep).
- Acceptance tests count operations: `render_rows` calls and rows passed, `land_renderings` calls, no lease claim on the write path; never wall-clock (READ AGENTS.md, Performance tests).
- Placement waits on D21; the spec can be converted and reviewed now and built at 0.2.
