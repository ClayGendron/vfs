# 118 — Matcher offload: verify calls on an owned worker, deadline across the hop

- **Status: all slices landed 2026-08-25** (A–C, same day drafted —
  slice statuses inline below). Born from ADR 049 (which ratifies
  `../../../research/2026-08-18-matcher-offload.md` §5); pulled
  forward of the concurrency story by Clay in session. The two
  open-questions entries this closes archive against ADR 049. The
  spec awaits its backward-flow mining pass; nothing blocks
  archiving.
  **Mined and archived 2026-08-25:** decision set → ADR 049 (its
  status block carries the implementation note — sizing settled at
  cores by measurement, the one-in-flight law made structural —
  recorded at this pass); the three laws' pins live as mutant-ledger
  rows P3–P5, and the offload module docstring is the standing
  statement of the hop's contract. Folder stays as the historical
  record.
- **Date:** 2026-08-25
- **Owner:** Clay Gendron
- **Kind:** concurrency seam change inside the database backend —
  results, ordering, truncation, and classification are contractually
  identical; the only observable difference is that the event loop
  keeps ticking while verify runs. First deliberate threads in
  `src/` (a declared exception, per ADR 049).
- **Depends on:** ADR 049 (the decision set), ADR 039 (Rust engine
  detaches the GIL — the property the offload rides), spec 110/112
  (wall discipline and budget stacking the wrapper must not
  disturb).
- **Relates to:** the serve()/concurrency arc (this lands at its
  front, already decided), spec 117 (the chunking engine's
  GIL-detached batch call — same seam philosophy, no shared code).

## Intent

1. **A decorating wrapper, not a protocol change.** An
   offload wrapper implements `ContentMatcher` by delegating each
   `count_lines`/`hit_lines` call to a worker; engines stay
   synchronous and thread-ignorant. The storage call site
   (`grep_rows`'s batch loop) is the only place that wraps.
2. **An owned executor with backend lifecycle.** A small
   `ThreadPoolExecutor` owned by the backend (sized ≈ cores,
   created lazily on first verify, shut down in `close()`), never
   the loop's shared default executor. One in-flight batch per
   verifier instance — now a stated invariant, pinned.
3. **The deadline crosses the hop absolute.** The wrapper receives
   the absolute deadline and computes the relative budget at worker
   start; queue wait shortens the budget instead of silently
   extending the wall. The per-batch deadline check and truncation
   flow in the caller are unchanged.
4. **Cancellation is abandonment made safe.** A cancelled await
   returns; the worker finishes into the void (≤32 MiB batch
   residency documented); a superseded worker from a
   `StaleSnapshot` redrive must be provably harmless (it touches no
   session and its results are dropped).

## Shape

- `storage/backends/database/grep.py` (or a sibling seam module):
  the wrapper and the call-site change; `engine.py`/`backend.py`:
  executor ownership and shutdown.
- Tests: a slow-matcher double proving the loop keeps ticking
  (gap-bounded) while verify runs; deadline-fidelity under induced
  queue wait; abandonment under cancellation and under redrive;
  ordering/truncation conformance unchanged on both engines; the
  one-in-flight invariant pinned.

## Slices

- **A — wrapper + executor** *(landed 2026-08-25)*: `offload.py`
  (`VerifyOffload` + `VERIFY_WORKERS`), `EngineHost.verify_executor`
  (lazy, shut down `wait=False` at close, built and borrowed alike),
  `grep_rows` batch loop awaits the wrapper with the absolute
  deadline; sizing settled by measurement (see open questions);
  deadline and one-in-flight laws pinned with their mutants (ledger
  P3/P4); full suite green at 100% coverage, conformance untouched.
- **B — cancellation and redrive** *(landed 2026-08-25)*: abandonment
  rows at the wrapper (cancelled await returns while the worker
  drains; a cancel before worker start never runs the matcher) and at
  the seam (a superseded worker drains harmlessly while its
  successor, on a fresh instance over the shared pool, serves whole);
  the end-to-end row cancels a real ``storage.grep`` mid-verify and
  proves the reissued call answers correctly while the abandoned
  worker still drains — its session closed under it, its results
  dropped. Batch residency (≤32 MiB) stated in the module docstring.
- **C — the proof** *(landed 2026-08-25)*: tick-gap row — the loop
  ticks at ≤0.5 s gaps while a 1 s GIL-releasing matcher double
  verifies (engine-independent by design; CI's native and pure legs
  both run it), pinned with the inline-execution mutant (ledger P5,
  8 failures); the ~40 µs hop tax acknowledged in the module
  docstring; engine legs re-run green; full `scripts/ci.sh` matrix
  green.

## Open questions

- ~~Executor sizing~~ — settled in slice A by measurement (10-core
  box, 32 MiB batches, both engines): native throughput plateaus by
  4 workers and holds flat through cores (~190 batches/s; rayon
  inside one call already saturates the CPUs, and co-running callers
  queue cleanly); only past-cores oversubscription degrades (16
  workers, mild); pure is GIL-flat at every size. **Sized to cores**
  (`os.cpu_count()`), no lower cap, no knob — the pool never
  oversubscribes at that size and capping buys nothing.
- zoekt's two-lane scheduler (interactive vs batch demotion) is the
  recorded shape if agent-vs-ETL contention ever measures real; out
  of scope here.
