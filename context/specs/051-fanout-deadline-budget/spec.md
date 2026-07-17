# 051 — A Deadline for Fan-Out: One Hung Mount Must Not Stall the Namespace

- **Status:** draft — found in the base2 line-by-line review, 2026-07-07
- **Date:** 2026-07-07
- **Owner:** Clay Gendron
- **Kind:** feature (dispatch robustness)
- **Depends on:** 036 (router verb surface), 040 (terminal gate),
  034 (MCP-native mounts — the remote terminals that make this real)
- **Enables:** mounting remote/MCP terminals without giving any one of
  them veto power over every namespace-wide query

## Intent

Give the router's parallel dispatch a time budget. `_gather_settled`
awaits every sibling with no deadline, so an unscoped `glob`/`grep`/
`glean` — and any grouped dispatch spanning terminals — blocks until
the *slowest* terminal answers. For in-process backends that is
correct and cheap. The moment a mount is a network hop (MCP, story
034), one hung catalog stalls every namespace-wide query for every
caller, with no classified failure and nothing for the caller to act on.

The error vocabulary already reserved the slot: `VFSErrorKind.timeout`
(ETIMEDOUT) exists and nothing in the router ever produces it.

## Why

- The no-probe rule means the router *trusts* `capabilities()` and
  dispatches without a health check — the right call, but it makes a
  deadline the only backstop against a live-but-unresponsive terminal.
- Settled-sibling semantics ("no mutation lands behind a failure the
  caller already saw") must survive: a timeout on reads can cancel
  stragglers safely; a timeout on mutations cannot simply abandon a
  write mid-flight. Reads and mutations need different policies.
- A namespace query is only as useful as its worst mount. Partial
  results with a classified `timeout` error per slow terminal is
  strictly better than an unbounded hang.

## Scope

- A per-dispatch time budget, plumbed to the chokepoints that fan out
  (`_route_fanout`, `_dispatch_grouped_observations`,
  `_route_two_path`, `_route_entry_batch`, `_spine_tree` descents).
- On expiry for **read-class ops**: cancel stragglers, merge what
  settled, and append one `timeout` error per unanswered terminal
  (path = the mount prefix), `success=False` — the fan-out analogue of
  a downed mount's `unavailable`.
- On expiry for **mutations**: `[NEEDS CLARIFICATION]` cancelling a
  dispatched write violates "a partial batch never keeps mutating
  behind a caller who saw a failure" in the other direction — the
  backend may have committed. Options: (a) no deadline on mutations,
  ever; (b) deadline waits but stops *reporting* (bad — lies); (c)
  deadline with an explicit "outcome unknown" error kind. Leaning (a)
  for this story; mutations already gate up front, and slow ≠ hung.
- Where the budget lives: `[NEEDS CLARIFICATION]` a per-call kwarg on
  the public verbs, a per-mount attribute set at construction/mount
  time, or a node-level default with per-call override. A per-mount
  setting matches "the mount knows its own transport"; a per-call
  kwarg matches "the caller knows its patience." Possibly both.
- Out of scope: retries, circuit breaking, health probes — those are
  policy layers above the router.

## Acceptance criteria

- An unscoped `grep` over one fast mount and one that never answers
  returns within the budget: the fast mount's rows present, one
  `timeout` error naming the slow mount's prefix, `success=False`.
- A scoped read into a single hung terminal fails `timeout`, not hang.
- Mutations are exempt (or the chosen alternative is implemented and
  documented in the gate/chokepoint docstrings).
- Cancellation semantics unchanged: an outer cancel still re-raises
  `CancelledError` untouched, taking precedence over timeouts.
- No budget configured → today's behavior, bit-for-bit.
