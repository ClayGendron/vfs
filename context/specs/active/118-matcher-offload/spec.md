# 118 — Matcher offload: verify calls on an owned worker, deadline across the hop

- **Status: drafted 2026-08-25.** Born from ADR 049 (which ratifies
  `../../../research/2026-08-18-matcher-offload.md` §5); pulled
  forward of the concurrency story by Clay in session. The two
  open-questions entries this closes archive against ADR 049.
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

- **A — wrapper + executor:** the decorator, ownership, lifecycle,
  absolute-deadline pass; conformance suites green untouched.
- **B — cancellation and redrive:** abandonment semantics tested;
  seam-staged superseded-worker row; docstrings state the batch
  residency.
- **C — the proof:** loop-responsiveness test (tick-gap bound with
  a slow matcher double on both engines), the ~µs-scale tax
  acknowledged in the module docstring, engine legs re-run, full
  `scripts/ci.sh` green.

## Open questions

- Executor sizing: cores vs `min(cores, N)` — settle in slice A by
  measurement of contention with rayon inside the native call (the
  native batch is already parallel; over-subscribing threads that
  each fan into rayon may want a smaller pool).
- zoekt's two-lane scheduler (interactive vs batch demotion) is the
  recorded shape if agent-vs-ETL contention ever measures real; out
  of scope here.
