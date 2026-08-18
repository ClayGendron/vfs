# 110 — Seam bounds: the pure engine honors the wall clock, the ingress gate gets maxima

- **Status: all slices landed 2026-08-18.**
  §1: the pure matcher consults the deadline *within* each body, at
  16-line slice boundaries on all four scan paths (whole-text via
  `finditer(text, begin, stop)` on line boundaries — `^`/`$`/`\b`
  judge identically since boundaries land just after `\n` and the
  gate already refused look-arounds; per-line via a stride check);
  expiry mid-body returns the partial hits as a lawful subset,
  reported incomplete. The residual floor — one slice's
  backtracking, uninterruptible inside `re` — measured 273 ms on
  16 catastrophic 18-char lines and recorded in the docstring. The
  unbudgeted path is one whole-body slice: zero overhead. §2: every
  int ParamSpec carries `maximum=INT_CEILING` (2³¹−1, the tightest
  integer all seams carry — probed live: the pyo3 context channels
  overflow at 2³², cap at 2⁶⁴); over-max refuses typed `invalid`
  naming the parameter, and the former raw-OverflowError repro
  (`before_context=2**32`) is now a router refusal pin, with the
  ceiling itself served end-to-end on the live engine. §3: parity
  rows — the ReDoS shape bounded on the pure engine (str and bytes
  spellings) and completed by the linear authority under the same
  budget, mid-body subset rows on both split and whole paths, the
  7-channel maximum sweep — all green on both engines (the pure CI
  leg runs them without the extension). §4: the event-loop
  occupancy fork recorded in `context/open-questions.md` for Clay,
  deliberately not landed. Full 3.13 leg green (2,558 tests, 100%
  coverage).
- **Drafted 2026-08-18.**
  Born from the review campaign memo
  (`../../../research/2026-08-18-glob-grep-review-campaign.md`),
  findings 5 (adversarial lens, major) and 14 (adversarial lens,
  minor after verification corrected its mechanism). Both are seam
  defects: inputs the boundary admits behave differently — or
  catastrophically — depending on which engine sits behind it.
- **Date:** 2026-08-18
- **Owner:** Clay Gendron
- **Kind:** bounded changes to the pure-Python matcher's deadline
  discipline and the ingress gate's parameter specs. No storage
  statements move; the Rust core's matching semantics do not move;
  the router's "never raises" contract is restored, not redefined.
- **Depends on:** spec 103 / ADR 039 (the two-engine seam and the
  verify authority), spec 097 ("the bound is time, not shape" — the
  law finding 5 shows the pure engine breaking), spec 098 (line
  semantics the chunked scan must preserve).
- **Relates to:** the event-loop occupancy lead (§4 — scoped here
  as a recorded fork, not a landed change), spec 106 (the bytes
  bodies the matcher now receives — the fix must hold for both
  spellings).

## Intent

Two ways the seam's promise fails today:

1. **The pure engine consults the deadline only between bodies.**
   Python `re` backtracks unboundedly within one `finditer`, so on
   the pure engine — a documented first-class configuration
   (`VFS_PURE_PYTHON=1`, CI's fallback leg, extension-less-wheel
   installs) — `grep(pattern="(a+)+bcd")` against a 35-byte body
   under a declared 2.0 s budget was still running at 30 s, with no
   truncation record and no error; the Rust engine answers in 4 ms
   (linear per body). Worse than one slow call: verify runs
   synchronously inside the grep coroutine, so the hang occupies
   the entire event loop. ADR 039's cataloged pure-engine residuals
   are semantic nits (Turkic orbit, `\N{...}`); an unbounded hang
   is not in that class.
2. **The ingress gate declares minima but no maxima on its int
   channels.** `before_context=2**32` (or `max_count=2**64`) passes
   the router, then raises a raw `OverflowError` out of the public
   API on the Rust build while the pure engine returns normally —
   an engine-divergent raw exception on router-admitted input,
   against the router's declared "never raises" posture. The
   review's sweep note: *no* int channel in the ingress table
   carries a maximum.

Laws that bind the slices:

1. **The wall budget bounds every engine.** A deadline is honored
   within a body, not just between bodies; when time expires
   mid-body the call reports incomplete through the existing
   truncation channel (the `ContentMatcher` contract already
   promises the incomplete-report return — this makes it true on
   the pure engine).
2. **Engine parity includes refusals and bounds.** Any input the
   gate admits produces the same result shape on both engines; any
   input one engine cannot honor is refused at the gate for both,
   typed `invalid` — never a raw exception, never an
   engine-divergent success.
3. **Semantics do not drift.** The chunked pure scan returns
   byte-identical matches to the unchunked scan wherever both
   finish (the parity battery is the referee, over str and bytes
   bodies); maxima are set at the seam's honest capability, not at
   convenience.

## Shape

- **§1 The pure engine's per-body bound.** The pure matcher scans
  each body in slices with the deadline consulted between slices —
  slice boundaries chosen on line boundaries so spec 098's line
  semantics are preserved exactly, and sized so the deadline check
  costs nothing measurable on the parity battery. A pattern that
  backtracks catastrophically *within one line* remains bounded by
  the slice's line count, not unbounded by the body: the residual
  worst case is one line's backtracking, recorded honestly in the
  matcher's docstring as the pure engine's floor. Timeout mid-scan
  → the incomplete-report return, surfaced as the existing
  wall-time truncation.
- **§2 Maxima at the ingress gate.** Every int ParamSpec gains a
  declared maximum (the sweep the review asked for — context
  windows, max_count, and the rest of the table): values the Rust
  seam can carry (u64/usize floors) and the pure engine matches.
  Over-max refuses typed `invalid` at the router, same as the
  existing minima refusals; the pyo3 seam never sees a value it
  would overflow on. The former OverflowError repro becomes a
  refusal test on both engines.
- **§3 The parity gate.** The engine-parity battery gains: the
  ReDoS shape under a small budget (both engines return, within
  bound, with the truncation record; the pure engine's answer is a
  lawful subset reported incomplete); boundary values at each new
  maximum (max, max+1) on both engines; the bytes/str spellings of
  both. The pure-only CI leg runs them without the extension.
- **§4 The event-loop fork — recorded, not landed.** Even bounded,
  a full `grep_wall_seconds` of synchronous matching occupies the
  event loop (Rust engine included) — real for the high-concurrency
  agent audience. The candidate designs (offload verify to a worker
  thread via the seam; cooperative yields between batches) carry
  real trade-offs (GIL behavior differs by engine; ordering and
  cancellation semantics). This spec records the fork and its
  evidence pointer; the decision is taken with Clay when the
  concurrency story is in view, not smuggled into a bounds fix.

## Slices

- **A. The pure bound.** §1 with the ReDoS rows and the parity
  battery extension; the residual worst case measured and recorded.
- **B. The maxima.** §2's sweep with per-channel boundary tests on
  both engines; the raw-OverflowError repro converted to a refusal
  pin.
- **C. The record.** §3 complete in CI (including the pure leg);
  §4's fork written into open questions / ADR territory as decided;
  spec status updated for the mining pass.

## Open questions

- **§4's fork**, as above — worker-thread offload vs cooperative
  yielding vs accepting occupancy, decided separately.
- **Slice size for §1**: line-boundary slicing assumes lines are
  reasonably bounded; a single pathological multi-megabyte line
  makes the slice large. If the parity battery shows it matters, a
  byte-cap fallback that still respects spec 098's semantics (never
  splitting a match window) is the follow-up shape.
