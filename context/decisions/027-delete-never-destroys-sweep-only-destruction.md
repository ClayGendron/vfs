# 027. Delete Never Destroys; Sweep Is the Only Destroyer

- **Status:** accepted
- **Date:** 2026-07-25
- **Deciders:** Clay Gendron
- **Decided by:** human (Clay, in session — a `topology.py` teaching
  walkthrough surfaced the trash-chain silent-permanence arm and the
  contract question behind it; this record followed same session)

## Context

The landed delete contract promises only "the target is gone from its
address" — recoverability is a courtesy, not a promise. Three arms
destroy data permanently, and two of them are reachable by any caller
of the public verb surface, agents included:

- **The `permanent=True` flag** on `delete` (router, protocol, both
  backends) — permanent destruction as a boolean an agent can pass.
- **The silent upgrade**: a target whose subtree holds the active
  bucket chain (`/.vfs`, `/.vfs/trash`, the current hour-bucket)
  hard-deletes even under `permanent=False` (`topology.py`
  `chain_inside`), signaled only by `trash_path=None` in the result —
  the caller asked for a recoverable delete and got permanence.
- **The memory backend keeps no trash at all**: every delete there is
  permanent, and `restore`/`sweep` classify `unsupported`.

The flag is also load-bearing in three recorded places: the router's
unmount removes the mount-point directory with
`delete(permanent=True)` (`base.py:403`); sweep's contract names
`delete(permanent=True)` as the per-bucket reclamation idiom
(spec 083 pin 2); and the resolved over-budget-trash-rewrite question
(`open-questions.md`, 2026-07-23) names it the documented fallback
when a trash rewrite refuses `unaddressable`.

The production posture puts two audiences on one verb surface, and
agents are the risk case: a single bad tool call can destroy data
unrecoverably, and the silent-upgrade arm means the caller cannot even
know in advance whether a given delete is recoverable. The 2026-07-25
teaching-session review of the `chain_inside` arm made the mixed
contract explicit and forced the question: should destruction be an
agent-reachable power at all?

## Options considered

- **(a) Status quo** — flag plus silent upgrade. Rejected: permanence
  is agent-reachable, sometimes silently, and the contract cannot be
  stated in one sentence.
- **(b) Permission-gate the flag** — keep `permanent` on delete and
  gate it by principal (the execute-tier shape). Rejected: the
  dangerous meaning still lives on the agent-facing verb, one
  misconfiguration away from reachable; the contract stays mixed
  ("delete *sometimes* destroys"); and it spends permission plumbing
  on a boolean when a verb split states the same rule structurally.
- **(c) Split by verb and by plane (chosen)** — delete always
  trashes, safe by construction; sweep is the only destroyer and
  never registers on the agent-facing surface. The contract becomes
  one sentence: *delete is reversible, sweep is not, and agents can
  only do the first.*

## Decision

Six pins:

1. **Delete always trashes.** The `permanent` parameter is removed
   from the public delete surface everywhere — router, params gate,
   storage protocol, both backends. Every successful delete is a
   recoverable reparent into the hour bucket, and every delete
   observation reports its trash address (`trash_path` is always
   present on success — its absence no longer encodes permanence).
2. **What delete cannot trash, it refuses.** The trash-chain arm
   flips from silent hard-delete to a refusal: deleting `/.vfs`,
   `/.vfs/trash`, or the current hour-bucket classifies `invalid`
   with a message naming sweep as the reclamation verb. Silent
   permanence becomes unrepresentable. The `unaddressable` overflow
   refusal stands; its documented fallback becomes the
   developer-plane sweep (or piecewise deletes of deeper subtrees) —
   amending the 2026-07-23 open-questions resolution's
   `permanent=True` wording.
3. **Sweep is the only destroyer, and it accepts any address.**
   Addressed at a mount's trash root, sweep keeps its landed
   retention arm unchanged (canonical bucket-name parse, the
   `trash_days` floor, warning-severity skips — ADR 026 pin 5 and
   spec 083 semantics). Addressed anywhere else, sweep permanently
   purges that subtree wholesale, immediately — the power the retired
   flag held — under the same router EBUSY guard, with the root
   refused. The retention floor binds only the trash-root arm; a
   direct sweep of a bucket address reclaims it regardless of age
   (the per-bucket idiom, re-homed from `delete(permanent=True)`).
4. **Sweep lives on the developer plane.** Sweep is excluded from the
   agent-exposed tool surface (the MCP serve layer and any CLI built
   on it) permanently; it remains a Python-API verb for code and
   deployment jobs. The exclusion mechanism (an op-classification set
   the serve layer consults) is the implementing spec's call. Sweep
   remains explicit and idempotent — ADR 013 pin 5 stands: storage
   owns no background work, so "automatic cleanup" means the
   deployment schedules the trash-root sweep, not a daemon in
   storage.
5. **The contract is universal, so every backend keeps trash.** A
   backend with no trash and no permanent delete could not delete at
   all — pin 1 therefore forces the trash arc onto every served
   backend. For the bespoke memory backend the execution is not to
   hand-roll the arc but to retire the backend: the in-memory role
   re-platforms onto the database backend over an in-process engine
   (ADR 028), so the arc — and every future verb — arrives once,
   from the one implementation, and the `unsupported` carve-outs
   retire with the backend that needed them.
6. **Internal callers hold the same line.** The router's unmount
   switches its `permanent=True` directory removal (`base.py:403`) to
   the ordinary trash delete — still non-cascade, preserving the
   must-not-destroy-rows-the-router-never-saw guarantee. Sweep was
   considered and rejected here: mount admin is intended for the
   agent surface, and routing unmount through sweep — however
   confined (fixed target, childless-only) — would make the pin-4
   plane rule hold by argument instead of by construction. With no
   internal sweep callers on any agent-reachable path, "no
   agent-reachable code calls the destroyer" stays a structural,
   greppable invariant. The empty mount-directory row parks in trash
   as accepted clutter; retention reclaims it.

## Consequences

- **Easier:** the contract states in one sentence and holds by
  construction — no flag audit, no silent arm; a misbehaving agent's
  blast radius is bounded by the trash retention window; recoverability
  is uniform across backends, so the conformance suite drops its
  `@needs("restore")`/`@needs("sweep")` gates; the teaching-session
  ambiguity (refuse vs hard-delete for chain-inside targets) resolves
  honestly — refusal is now coherent because delete no longer holds
  the destroying power.
- **Harder:** destruction requires code access — an agent that
  legitimately needs space reclaimed must hand off to a developer or
  a scheduled job; trash grows strictly monotonically between sweeps,
  so the demand-gated size bound (`open-questions.md`) gains urgency;
  the in-memory role re-platforms onto the database backend first
  (ADR 028, spec 084) — a new dependency and a validation gate ahead
  of the contract flip; deep-tree
  `unaddressable` refusals lose their in-band fallback; and move/copy
  `overwrite` still purges the occupant permanently — the last
  agent-reachable destruction, deliberately **not** closed here and
  filed in `open-questions.md` (trash-the-occupant vs POSIX
  unlink-on-rename parity is its own trade).
- **Committed to:** spec 084 re-platforms the in-memory backend per
  ADR 028 (landing first so the tree stays green); spec 085 executes
  the contract flip (pins 1–4, 6: signatures, the chain-inside refusal,
  sweep's purge arm, the developer-plane op classification, the
  unmount switch, doc and test rewrites); the overwrite-occupant hole
  and the amended overflow fallback are recorded in
  `open-questions.md`.

Evidence: the 2026-07-25 teaching session (chain-inside review);
`topology.py` (`chain_inside` hard-delete arm, sweep's
address refusal); `memory.py` no-trash carve-outs; `base.py:403`;
`open-questions.md` "Trash rewrites can exceed the path column"
(resolved 2026-07-23). Refines ADR 014 pins 3–5 (delete's reparent
shape and sweep's parse-and-drop mechanism stand; sweep's address
space and plane change; delete's permanent arm retires) and ADR 026
(pins 1–5 stand; the consequence naming `permanent=True` the overflow
fallback is superseded). Supersedes spec 072's delete `permanent`
flag and spec 083 pin 2's "any other address refuses `invalid`" —
per-bucket reclamation re-homes onto sweep itself. Supersedes no
numbered ADR.
