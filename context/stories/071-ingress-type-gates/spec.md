# 071 — Ingress type gates: the router owns wire-facing validation

- **Status:** seed — direction decided (router gates), design not started.
  Drafted from the adversarial probe sweep of `VirtualFileSystem`
  (2026-07-10; probe scripts were session-temporary, evidence recorded
  here).
- **Date:** 2026-07-10
- **Owner:** Clay Gendron
- **Kind:** hardening (data-plane contract — no new verbs, no storage
  protocol changes)
- **Depends on:** 057 result envelope (classified errors), 069 routing
  decomposition (the shapes the gates land in)

## Intent

The router's contract is *values in, `Result` out — the data plane never
raises*. That holds for paths (one gate: `resolve_path`) but not for the
other typed parameters of the public verbs. The probe sweep produced raw
`TypeError`/`AttributeError` raises through public verbs from
type-garbage a wire adapter could forward verbatim from JSON:

- `tree(max_depth="2")` — router arithmetic raised (**fixed** — gated in
  `_route_single`'s tree arm, 2026-07-10).
- `glob(max_count="5")` / `glean(limit="5")` — router compare raised;
  `max_count=2.5` raised *after* dispatch at the post-merge trim
  (**fixed** — `_route_fanout`'s bound check now requires an int,
  2026-07-10).
- `mkedge(edge_type=123)` — would have raised in path minting (**gated**
  earlier, pinned by test).
- `grep(123)` / `grep(b"…")` / `glob(123)` — raise inside the backend's
  matcher.
- `ext=(123,)` on glob/grep — `AttributeError` in the backend.
- `grep(before_context="2")`, per-file `max_count="3"` — backend
  arithmetic raises.
- `write(path=…, content=None)` and other payload-shape holes — backend
  truth today (memory classifies; a lenient backend answers success).
- `run(arguments=123)` — pure passthrough, backend's problem on arrival.

The funnel classifies only `TransportError`; everything else is the
impl-bug channel, which is *correct* for backend bugs but wrong for
forwarded caller garbage. Today the distinction is accidental: whichever
code touches the value first decides whether the caller gets a
classified `invalid` or a stack trace.

## Decision (recorded)

**The router owns ingress.** Every public verb validates the types and
value ranges of its non-path parameters at the routing layer and
classifies violations as `invalid` before any dispatch — same rule as
paths, same outcome as the `max_depth` / `row_cap` / `edge_type` gates
already landed. Alternatives considered and declined:

- *Funnel-level catch* (convert `TypeError`/`ValueError` from any
  backend call): one seam, but it blurs the impl-bug channel — real
  backend bugs would surface as classified errors instead of loudly.
- *Adapter obligation* (validation is the wire adapter's job): leaves
  every embedded-Python caller unprotected and every adapter
  re-implementing the same table.

## Shape (to design)

- One shared helper rather than more ad-hoc `isinstance` lines — the
  three landed gates are the pattern to consolidate: check, classify
  `invalid` with `got {value!r}`, zero dispatch on refusal.
- A per-verb parameter table (name → type, bounds, None-ness) likely
  lives beside the `Op` definitions in `ops.py`, so the wire dialect can
  reuse it for schema generation later.
- Bool-vs-int policy needs one decision (`True` currently passes int
  gates); whatever is chosen, apply it uniformly.
- Enum-valued params (`output_mode`, `case_mode`) silently fall through
  to defaults on bogus values today — gate or document, uniformly.
- Out of scope: hung-backend timeouts and regex backtracking (DoS
  surfaces, not type validation — separate story if pursued).

## Acceptance sketch

Every public verb refuses type/range garbage on every non-path
parameter with `invalid` and an empty dispatch log; the existing three
gates' tests fold into the shared table's suite; ty stays clean (gates
are runtime belt over the static suspenders, `ty: ignore` only in
tests).
