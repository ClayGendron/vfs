# 049. Verify Leaves the Event Loop by Thread; the Backtracking Residual Is Settled by Engine Choice

- **Status:** accepted 2026-08-25 — ratifies the matcher-offload
  memo's recommendation and closes both forks it was commissioned
  for: "Grep verify occupies the event loop" and "Bounding the pure
  scan's backtracking residual" (both archive from
  `../open-questions.md` against this ADR). Complements ADR 046
  (wall discipline; partiality stays result-level — untouched here)
  and ADR 039 (the Rust engine as match authority — its linear-time
  guarantee becomes load-bearing for §2). Implemented by
  `../specs/active/118-matcher-offload/`.
- **Date:** 2026-08-25
- **Deciders:** Clay Gendron — the 2026-08-18 decision pass parked
  both forks on the concurrency story; Clay pulled them forward
  2026-08-25 ("why can't we work on the grep event loop now?" —
  nothing blocked it but sequencing) and ratified the residual lean
  in the same session.
- **Context source:** `../research/2026-08-18-matcher-offload.md`
  (executed: tick-gap harness on both engines, `to_thread` and
  process-pool measurements, CPython `_sre`/GIL facts verified on
  3.10–3.14; prior art: SQLAlchemy, MCP SDKs, opendal, zoekt,
  codesearch), recorded by the 2026-08-18 remediation-landing
  review's decision pass.

## Context

The verify stage runs synchronously inside the grep coroutine on
both engines: up to a full `grep_wall_seconds` (default 10 s) of
matching holds the event loop, so concurrent callers on one host
stall behind one heavy grep. The memo measured the fix and its
limit: the Rust seam already detaches the GIL (`py.detach` over
`PyBackedBytes`, rayon inside), so a worker thread fully solves
occupancy there (1,535 ms worst-case tick gap → 29–41 ms); on the
pure engine a thread bounds stalls at the longest single `re` call
(GIL hand-over between calls) but cannot touch one pathological
backtracking episode — a single GIL-holding C call that no timer
can interrupt and no thread can bound (2,151 ms off-loop vs
2,141 ms on-loop; a 0.5 s `wait_for` fired at 2.13 s). The only
hard stop is process death, a posture no studied library adopted.
The per-call thread tax is ~38 µs. Separately, ADR 048 has since
dissolved the chunking half of the joint worker-posture question
(chunking parallelism is rayon inside a native call, not worker
processes), leaving the process posture parked on its own.

## Decision

1. **Verify calls leave the event loop through a worker thread.**
   A decorating wrapper around the `ContentMatcher` protocol at the
   storage call site — never a per-engine fork — running each
   per-batch `count_lines`/`hit_lines` call on a small executor the
   backend owns (sized to cores, not the loop's shared default
   executor, per the ownership etiquette the prior art draws).
   Batches stay sequential; results stay index-aligned; the
   completed→truncate→break flow and the wall-breach recording are
   untouched. The absolute deadline crosses the hop — the relative
   budget is computed at worker start, so queue wait can never
   silently extend the wall.
2. **Cancellation is abandonment made safe** (SQLAlchemy's stance,
   fitted to a seam where the worker never touches the session):
   a cancelled await returns immediately, the worker finishes into
   the void, its ≤32 MiB batch residency is accepted and
   documented, and a superseded worker from a `StaleSnapshot`
   redrive is harmless by construction. No protocol-level interrupt
   is invented.
3. **The pure engine's exponential residual is settled by engine
   choice, not chased with mechanisms.** The Rust engine — the
   default wheel — is the linear-time answer (codesearch's posture:
   the engine choice *is* the timeout story). The pure fallback
   keeps its disclosed residual: deadline consulted between slices,
   one slice's backtracking uninterruptible, magnitudes named in
   the docstring, budget stacking as landed by spec 112. This
   mirrors ADR 048 §4's posture: the pure fallback is a fallback of
   record with declared limits, not a parity twin in every
   dimension.
4. **Process workers stay rejected for now.** Process death is the
   only true bound on a backtracking episode (measured kill at
   0.507 s, ~255 ms pool rebuild per kill), and it remains a
   library-posture question — reopened only if a daemonized host
   posture ever makes worker ownership natural. With chunking's
   half dissolved by ADR 048, that question stands alone in
   `open-questions.md` territory only if a real consumer raises it;
   no entry is kept open for it.

## Options considered

- **Thread offload** (adopted): solves occupancy wholesale on the
  Rust engine, bounds pure stalls at one `re` call, ~38 µs tax.
- **Cooperative yields between content batches**: cheaper but
  bounds the stall at a whole batch (up to 32 MiB of matching) and
  buys nothing for the Rust engine the thread doesn't already buy.
- **Accept occupancy**: rejected by the decision to serve
  concurrent agents from one host — the high-concurrency audience
  is first-class.
- **Threads for the residual**: measured non-viable — physics, not
  design (a single sre episode holds the GIL as one C call).
- **Process pool with kill**: the only hard bound; rejected as a
  posture no studied library accepted, held for a future joint
  decision if ever warranted.

## Consequences

- The first deliberate threads in `src/`: one small owned executor
  with backend lifecycle (created lazily, shut down at close), a
  declared exception to the tree's no-threads status quo.
- Concurrent grep callers on one host stop queueing behind a heavy
  verify: worst-case loop occupancy drops from wall-budget scale to
  tens of milliseconds on the default engine.
- The wrapper is seam-shaped: engines never learn about threads;
  `ContentMatcher` implementations stay synchronous and immutable
  per call, and the one-in-flight-batch-per-verifier invariant is
  now a stated law rather than an accident.
- A pure-only install under a hostile pattern can still burn a
  worker thread to completion — disclosed, budget-stacked, and
  bounded by engine choice everywhere the wheel installs.
- The memo's measured numbers become the spec's acceptance
  criteria (loop-gap bound with a slow matcher, deadline fidelity
  across the hop, abandonment harmlessness under redrive).
