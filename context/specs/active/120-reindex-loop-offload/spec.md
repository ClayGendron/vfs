# 120 — Reindex leaves the event loop: whole-verb offload, split-batch byte budget, honest residency

- **Status: draft, 2026-08-25.**
- **Born from** the chunking-arc landing review
  (`../../../research/2026-08-25-chunking-arc-landing-review.md`),
  finding F1 (the loop stall — the arc's headline major), its
  verified systemic lead (`build_epoch` stalls the loop too), and
  design question Q8 (residency disclosure + byte budget), all ruled
  in the 2026-08-25 decision pass.
- **Date:** 2026-08-25
- **Owner:** Clay Gendron
- **Kind:** concurrency fix in the database backend's reindex path,
  plus a bounded batch shape and a disclosure. No behavior change to
  results: counts, chunk shapes, and row contents are byte-identical
  before and after.
- **Depends on:** ADR 049 / spec 118 (the backend-owned executor and
  the deadline-across-the-hop discipline this generalizes), ADR 048 /
  spec 117 (the chunk pass being offloaded), spec 111 (the
  disclosure convention for whole-corpus profiles).
- **Relates to:** spec 121 (same function, different defect — land
  121 first or rebase it in; both touch `chunk_dirty`'s opening
  statements), the close-lifecycle work in spec 122 (the executor
  the offload rides is shut down there).

## Intent

1. **`reindex()` freezes the event loop for its whole CPU-bound
   wall.** `chunk_dirty` calls `Chunk.split_batch` synchronously
   inside the coroutine; the native `chunk_spans` call detaches the
   GIL — which frees *threads*, not the *loop* — so the calling
   coroutine and every co-scheduled task stall for the entire batch
   parse plus the inline chunk-row assembly. Measured: 2,000 files →
   2,250 ms worst loop gap at a 10 ms heartbeat; 3,000 files →
   3,156 ms (2.52 s in `split_batch` alone); at the landed linux
   gate's ~24 s chunk wall, the loop is dead ~24 s. ADR 048 promises
   "the reindex verb's event-loop occupancy for chunking goes to
   approximately zero" — the landed code does not deliver it, and
   ADR 049's own tick-gap measurement in the same arc is the proof
   that GIL detachment alone never could.
2. **The stall is the verb's, not the chunk pass's.** The
   posting/gram `build_epoch` also runs its CPU-bound work inline on
   the loop (369 ms gap observed in the same probe, growing with the
   corpus). Fixing only the chunk pass would re-file the same
   finding one function over. The decision pass ruled: the offload
   scopes to **every CPU-bound stage of the reindex verb**.
3. **The split batch is unbounded by bytes.** `chunk_dirty` hands
   the whole dirty set's bodies to one `split_batch` call while the
   neighbouring extract phase bounds itself by
   `_EXTRACT_BATCH_BYTES`. Measurement (staged tracemalloc, two
   engines, three corpus shapes) showed the batch encode adds ~0.4×
   content transiently and never raises the call's peak — the 6.1×
   peak is the pre-existing chunk-insert executemany — so this is
   symmetry and transient-residency hygiene, not a peak fix, and the
   spec says so honestly.
4. **The residency profile is undisclosed.** `build_epoch`,
   pathterms, and segments all disclose their whole-corpus profiles
   per the house rule; `chunk_dirty`/`split_code_batch` do not,
   while the generation law adds fresh whole-corpus-dirty triggers
   (generation bump, engine switch).

Laws that bind the slices:

1. **Results are invariant under offload.** Same chunks, same rows,
   same counts, same errors — the executor hop may change *when*
   work runs, never *what* it produces. The parity pins and engine
   legs are the referee.
2. **The absolute deadline crosses every hop** (ADR 049's law): the
   relative budget is cut at worker start, so queue wait shortens
   the budget instead of silently extending the wall.
3. **Occupancy claims are measured, not asserted.** The acceptance
   gate is a loop-gap probe, not prose; whatever bound the landed
   code achieves is the bound the docstring and ADR 048's amendment
   note record.
4. **Suboptimalities are recorded, never converted into limits**
   (house rule): the byte budget bounds a batch shape; it must not
   become a corpus ceiling.

## Shape

- **§1 The offload seam.** Route `Chunk.split_batch` (and the
  chunk-row assembly it feeds) and `build_epoch`'s CPU-bound stages
  through the backend-owned executor `EngineHost` already carries —
  the decorating-wrapper shape `VerifyOffload` established, not ad
  hoc `to_thread` calls. One hop per batch, not per file; the rayon
  parallelism inside the native call is unchanged (the executor
  saturates nothing — cores are already saturated inside one native
  call; the hop exists to free the loop, per ADR 049's sizing
  finding). Decide during planning whether the verify pool is shared
  or a sibling pool is minted; either way spec 122's close rules
  govern its lifecycle.
- **§2 The byte budget.** The split batch is fed in byte-bounded
  sub-batches, constant declared beside `_EXTRACT_BATCH_BYTES` and
  disclosed in the same breath. Sub-batching must preserve
  `split_batch`'s grammar-routing semantics and its pinned equality
  with the single-item forms.
- **§3 The honest record.** `chunk_dirty` (or the module docstring)
  discloses the residency profile with the measured figures (peak
  set by the chunk-insert executemany, ~6.1× content on the measured
  shapes, linear in the dirty set) and names the future direction.
  ADR 048's occupancy claim gains an amendment note pointing at the
  measured post-offload bound.
- **§4 The gate.** The loop-gap probe from the review (heartbeat
  task + `await reindex()`) becomes a pinned test: worst gap bounded
  at a declared threshold on the probe corpus, both engines. Parity:
  chunk rows and posting epochs byte-identical to the pre-offload
  answer; all four engine legs green; the linux-corpus reindex gate
  re-run to confirm the ≤60 s target still holds with the hop and
  sub-batching in place.

## Slices

- **A. Chunk pass offload** — §1 for `chunk_dirty` with §4's probe
  pinning the chunk wall off the loop.
- **B. `build_epoch` offload** — §1 for the posting/gram stages, the
  probe extended to the whole verb.
- **C. Budget and record** — §2 and §3, with the sub-batch equality
  pins and the linux gate re-run.

## Open questions

- Whether the offload executor is the verify pool or a sibling —
  a planning decision, made where spec 122's lifecycle rules can
  see it.
- The loop-gap threshold for §4's pin: tight enough to catch a
  regression to inline execution, loose enough to survive CI noise —
  set it from measured runs, and record the measurement.
