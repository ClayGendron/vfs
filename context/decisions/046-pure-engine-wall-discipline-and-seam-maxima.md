# 046. The Seam's Bounds: the Pure Engine's Wall Discipline, Ingress Maxima, and Partiality as a Result-Level Signal

- **Status:** accepted 2026-08-18 — the decision set of specs 110 and
  112, with the decision pass's Q2 ratification recorded by spec 116,
  written at the 107–116 mining pass (2026-08-19). Refines ADR 039's
  pure-fallback clause (its cataloged residuals were semantic nits;
  an unbounded hang is not in that class) and ADR 033's "the bound is
  time, not shape" law; neither is superseded.
- **Date:** 2026-08-18
- **Deciders:** Clay Gendron (the decision pass: partiality stays
  result-level; the occupancy/residual fork deferred to the
  concurrency story with research commissioned).
- **Context source:** the 2026-08-18 review campaign (findings 5 and
  14: a `(a+)+bcd` body under a 2 s budget still running at 30 s on
  the pure engine; `before_context=2**32` raising a raw
  `OverflowError` through the public API on the Rust build), the
  remediation-landing review (findings 1, 2, 6, 7 — the `^$` phantom
  at slice boundaries and its cap displacement; the exponential
  residual), and the matcher-offload memo
  (`../research/2026-08-18-matcher-offload.md`). Implemented by specs
  110, 112, 116.

## Context

Two engines sit behind one `ContentMatcher` seam. The pure engine
consulted its deadline only between bodies, so one pathological body
held the coroutine — and the event loop — for as long as `re` chose;
the ingress gate declared minima but no maxima on its int channels,
so router-admitted input could overflow the pyo3 seam. Spec 110's
first slicing fix then shipped its own defect: passing a slice end as
`endpos` let MULTILINE `$` match at every 16-line boundary,
fabricating `^$` hits and, under a cap, displacing genuine ones.

## Decision

1. **The wall budget is consulted within a body, at line-boundary
   slices, on every pure scan path.** Slices land just after `\n` so
   `^`/`$`/`\b` judge identically to an unsliced scan; zero-width
   matches landing exactly on a non-final slice end are discarded and
   the next slice judges that position with real context. Expiry
   mid-body returns the hits so far as a lawful subset, reported
   incomplete. The unbudgeted path is one whole-body slice — zero
   overhead.
2. **The residual is disclosed, not bounded.** One slice of `re`
   backtracking is uninterruptible and exponential in line content
   under a pathological pattern (measured 273 ms per 16-line slice of
   18-char lines, doubling per two characters; 75 s for one 30-char
   line); single-slice bodies pay it whole after one entry check; the
   budgeted path also pays linear pre-work (decode + eager split,
   ~2.4× transient residency, ~7 % overrun at 512 MiB) before its
   first check. The `_PureMatcher` docstring carries the magnitudes.
   An overrun leaves results exact — a wall breach, never wrong data.
3. **The incomplete flag is a data-completeness signal, not a wall
   one, and the only partiality signal.** Per-body results are exact
   except that an engine may skip a body it did not reach or leave a
   partial count on the body the budget interrupted; no per-row
   marker exists. Cap-reached is contractual completion. This is the
   `ContentMatcher` Protocol's law so a third engine inherits it.
4. **Every int ingress channel carries `maximum=INT_CEILING`
   (2³¹−1)** — the tightest integer all seams carry; over-max refuses
   typed `invalid` naming the parameter, on both engines. Engine
   parity includes refusals and bounds: any input the gate admits
   produces the same result shape on both engines.
5. **Budgeted parity is pinned, not assumed.** The cross-engine
   battery runs a budgeted-equals-unbudgeted sweep and a
   budgeted-pure-equals-authority sweep over every case — the pin
   whose absence let the phantom ship.
6. **The joint fork — event-loop occupancy and the backtracking
   residual — is deferred to the concurrency story, research done.**
   Measured: the pyo3 seam already detaches the GIL, so thread
   offload fully fixes occupancy on the Rust engine (1,535 ms stall →
   ≤41 ms) and bounds pure-engine stalls at the longest single `re`
   call; one `sre` backtracking episode is thread-unboundable
   (`wait_for`'s timer cannot fire until it returns) — only process
   death hard-stops it, a worker-posture question shared with
   semantic chunking. Lean: settled-by-engine-choice (Rust is the
   linear-time answer; the pure fallback keeps its disclosed
   residual); a pattern-complexity gate would collide with the
   no-designed-caps rule and needs its own pass.

## Consequences

- A deadline is honored within a body on both engines; the Rust
  engine answers the pathological shape in ~5 ms and is the oracle.
- The three deadline-cadence spellings are proven phase-identical
  (first check after 16 lines, then every 16); unifying them is parked
  until the byte-cap-slicing follow-up (a single pathological
  multi-megabyte line) forces one slice-iterator helper.
- Any future engine behind the seam must declare its per-body
  partiality against clause 3 and its maxima against clause 4.
- The `VFS_PURE_PYTHON=1` configuration is first-class and must stay
  inside the same parity battery; its residual is a documented floor,
  never a cap.
