# 008. Result Is the Only Failure Channel in the Tree; Raising Is a Boundary Opt-In

- **Status:** accepted
- **Date:** 2026-07-16 (decided 2026-07-03 with story 037, commit
  06cf551; this record promotes it out of the archived story)
- **Deciders:** Clay Gendron
- **Decided by:** human

## Context

The router carried a `raise_on_error` flag on every node, copied onto
whole subtrees at mount time. Two personas need opposite failure
behavior, and the flag served neither safely:

- **An app serving an LLM agent must never raise.** Errors reach the
  agent as text — the failed `Result` renders to prose, or crosses MCP
  with `is_error` — and the conversation continues. A mis-set flag here
  is an unhandled exception in front of an agent.
- **A developer running an ETL must get loud failures.** A silent
  failed `Result` in a fire-and-forget script reads as "okay, it
  worked" — the exact outcome to prevent.

Story 037 reproduced two defects the node-level flag caused
(reproduction script preserved as
`context/specs/archive/037-boundary-raise-and-result-channel/repro.py`):

- **Fire-and-forget mutations.** `asyncio.gather` propagates the first
  child exception without awaiting siblings, so under
  `raise_on_error=True` a grouped write spanning a failing and a slow
  healthy terminal raised while the healthy write **landed after the
  caller saw the exception** — a retry double-applies, and the
  successful group's row statuses were discarded unseen.
- **Dual-channel plumbing.** Internal composition points had to handle
  both failed `Result`s and kind-mapped exceptions (`_probe`'s
  exception arms existed almost entirely for this), with the flag as
  mutable shared state nothing kept coherent after mount time.

## Options considered

- **Keep the node-level flag** — rejected: it is the root cause of
  both defects above.
- **Raise only at the tree's root node** — rejected: **root is a role,
  not a type.** A filesystem's public verbs are simultaneously the API
  a direct caller uses *and* the seam a parent dispatches through once
  it is mounted — a node that raises because-it-is-currently-root
  starts throwing into its new parent's gather the moment `add_mount`
  gives it a parent. Even self-dispatch breaks (the mountability probe
  calls public `stat` on *self*). A node can never know whether it is
  the outermost frame; **only the caller knows**.
- **Boundary adapter chosen by the caller** (chosen) — the raise lives
  in a wrapper that is outermost by construction; the node layer is
  uniform.

## Decision

`Result` is the **only** failure channel inside the mount tree; no
filesystem node ever raises a VFS error. Raising is an opt-in at the
outermost call boundary. The live shape:

- **`raise_if_failed(result)`** (`src/vfs/exceptions.py:96`) is the
  boundary adapter: success passes through (so it composes inline);
  failure raises each **fatal** entry (`result.failures` — warnings and
  info never raise) as its kind-mapped exception via
  `exception_for_kind`, with the full `Result` attached as `.result` so
  batch partial-successes stay inspectable; multiple failures raise an
  `ExceptionGroup` so a fan-out reports every downed terminal. An
  unknown kind from a newer peer raises as base `VFSError` — the
  broadest class, never a narrower one that would misstate a failure
  this client cannot classify (`exceptions.py:81-93`).
- **No node-level flag exists.** `VirtualFileSystem` has no
  `raise_on_error`; nothing in `src/` carries one. The kind→exception
  map is boundary-only.
- **Every dispatch gather settles before the router reports.**
  `_gather_settled` (`src/vfs/base.py:1957`) runs all sibling groups
  to completion; a raised exception is by definition an impl *bug*
  (the Result channel never raises) and propagates only after all
  siblings finish — a partial batch can never keep mutating behind a
  caller who already saw a failure. Cancellation outranks bugs.
- Two contract fixes ride along: failed results carry `function` (an
  agent on the wire can tell which verb failed), and `Result.__bool__`
  means *success*, nothing more — a successful glob with zero matches
  is truthy; emptiness is `len()` (`src/vfs/results/envelope.py:340`).

## Consequences

- **Easier:** the LLM-app path is structurally safe — there is no flag
  on any node to mis-set, and every error renders as text or an MCP
  `is_error` payload; internal composition handles exactly one channel
  (the probe's exception arms are gone); the ETL contract is one
  wrapper — `raise_if_failed(await fs.write(...))` or a raising client
  facade — applied once, at the boundary.
- **Harder:** a raw `fs` call in a script fails silently unless the
  author opts in — the raising boundary **is** the ETL contract, and
  forgetting it recreates the silent-failure risk (now in exactly one
  visible place); backends must be disciplined that genuine failures
  become `Result` errors, since anything raised is treated as a bug.
- **Committed to:** every storage backend and every mounted node
  returns `Result` for every failure, whether it is a root, a leaf, or
  about to become either; new dispatch sites must settle all siblings
  before reporting; truthiness stays success-only.

Decided and executed in story 037
(`context/specs/archive/037-boundary-raise-and-result-channel/spec.md`);
the derived-success/`failures` envelope it leans on was refined by
story 057 (`context/research/2026-07-08-result-envelope.md`).
