# 001. Storage Is an Object the Node Holds, Not a Thing the Node Is

- **Status:** accepted
- **Date:** 2026-07-04
- **Deciders:** Clay Gendron
- **Decided by:** human

## Context

`VirtualFileSystem` fused two roles behind a constructor flag: a **router
node** (mount table, verb surface, gates) and an **abstract storage
backend** (the `_{op}_impl` seam reached by
`getattr(self, f"_{op}_impl")`). The fusion had four costs:

- The `storage: bool` flag was an identity claim enforced by nothing.
- The getattr seam was the one contract `ty` could not check: a backend
  that forgot an impl failed at *dispatch time* with a raw
  `AttributeError` — on the exception channel story 037 reserved for
  router bugs, which a forgotten backend method is not.
- `capabilities()` was hand-declared, with nothing tying the declared
  set to the impls that actually existed — while the no-probe rule makes
  agents *trust* that set, and the roadmap makes partial backends (an
  in-memory backend without `glean`, an MCP tool catalog doing only
  `ls`/`read`/`run`) the normal case.
- The database backend port was imminent, and every `_read_impl` it
  landed would fossilize the shape. This was the last cheap moment to
  choose: the router was fresh, 1,591 lines, at 100% coverage.

## Options considered

- **Keep the inherited `_*_impl` seam** — pros: it existed, was
  documented, and was fully covered; subclassing with three impl
  methods is a low floor; and — the strongest argument — the session
  contract has an obvious home ("open a transaction in an overridden
  `_call_local_impl`, hand the session to each impl"). Cons: the seam
  is invisible to the type checker; a subclass sees every private
  method of a ~1,600-line router and can shadow one silently;
  `capabilities()` can drift from reality without any test failing.
- **Composed `StorageBackend` protocol** (chosen) — pros: a missing
  method is a `ty` error at the constructor hand-off, before anything
  runs; capabilities become *derivable* from what the object
  implements; the node's mental model becomes uniform (a router over
  things it holds — mounts across edges, storage underneath). Cons: a
  16-arm `match` funnel replaces one clever line; migration churn
  across the router, its tests, and the flag checks; backends lose
  ambient `self` (node context) and cross-verb atomicity loses its
  "override the funnel harder" escape hatch.
- **Composed, but one flat 16-method protocol** — rejected granularity
  variant: it makes partial backends liars again (stub the methods you
  lack), which defeats derived capabilities. Op-family protocols
  (`SupportsRead`, `SupportsPatternSearch`, `SupportsGlean`,
  `SupportsMutation`, `SupportsGraph`, `SupportsRun`) keep "what a backend genuinely
  supports" checkable per family.

## Decision

We chose the composed shape: `VirtualFileSystem(storage=...)` accepts a
`StorageBackend` (the read family is the minimum viable backend — the
mountability probe needs `stat`), with `runtime_checkable` protocols
per op family. The settled details, argued in full in story 046:

- The router seam is an exhaustive `match op:` ending in
  `assert_never` — the stringly seam dies at one chokepoint, in checked
  form. Adding a verb to `ops.py` fails `ty` until the funnel routes it.
- `capabilities()` defaults to a *derived* set (which families the
  storage object satisfies, plus what the node's spine and mounts
  answer); a hand-declared override stays legitimate for policy, but
  the default can no longer lie.
- Transactions are backend-internal: each backend opens and commits its
  own session inside its op methods. The router never sees a session —
  the rejected option's strongest argument is answered by relocation,
  not loss: the wrapper moves one method deep into the backend with the
  same information hiding.
- Provider inheritance survives *inside* the backend family
  (`DatabaseStorage → PostgresStorage → MSSQLStorage`); user-facing
  classes like `PostgresFileSystem` remain as thin constructor wiring.

Spike evidence (both files in `context/specs/archive/046-storage-composition-decision/`,
executed 2026-07-04): `spike_inherited.py` — a `storage=True` subclass
defining no impls passes `ty` clean and crashes only at dispatch;
`spike_composed.py` — the same omission against the protocol fails `ty`
at the hand-off site, while a provider subclass overriding one method
type-checks unchanged.

## Consequences

- **Easier:** honest `capabilities()` for partial backends; the
  database port builds against a checked contract; `close()` disposes
  mounts and own storage symmetrically; test doubles implement a small
  protocol instead of subclassing the router.
- **Harder:** the 16-arm funnel is real verbosity; error-message
  branding needs a deliberate home (a backend concern now, not ambient
  `self`); cross-verb atomicity, if ever wanted, must be a designed
  protocol entry point rather than an override.
- **Committed to:** the protocol *is* the storage seam the database
  backend story builds on. The seam is local-only either way — remote
  and MCP mounts (034) are reached through public methods and never see
  this decision.

Executed by story 049 (`context/specs/archive/049-storage-backend-protocol/`).
