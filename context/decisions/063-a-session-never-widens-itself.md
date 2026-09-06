# 063. The Session Law: a Session Never Widens Itself, Principals Widen by Grant, and One Actor Is the Marked Exception

- **Status:** accepted 2026-09-06 (Clay, each option put as a question and
  ratified as written; binds spec 070's session facade, roadmap 023 and the future `ask` rung). Drafted 2026-09-05 as Phase 3 of the
  principals and permissions research programme
  (`../research/2026-09-05-principals-and-permissions-research-plan.md`);
  companions 062 to 067 were ratified together.
- **Date:** 2026-09-05
- **Deciders:** Clay Gendron
- **Decided by:** human (Clay, 2026-09-06). Originally drafted by Claude from lenses L1 (Landlock,
  Capsicum, the bounding set, Setuid Demystified), L2 (`RFNOMNT`,
  `none`, factotum's one-shot capability), L3 (every attenuation system)
  and L5 (every harness's "always allow").

## Context

Attenuation is the one point on which all five lenses agree: the holder
of authority can only cut it down. Capsicum refuses any
`cap_rights_limit` that adds a bit; WASI's `fd_fdstat_set_rights` can
only remove; a macaroon holder can add caveats and never remove one;
Landlock layers only stack; a Plan 9 process can drop to `none` and
never climb back; an AWS session policy cannot grant more than the
role. That is the session law, with fifty years of precedent.

Two things complicate it. First, every agent harness in 2026 widens a
session by a human click ("always allow" appends an allow rule in all
six; three persist it; the Claude Agent SDK's callback may answer with
a mode change to user settings). Second, the sendmail incidents in
Setuid Demystified show the failure of a narrowing that leaves a way
back: a dropped privilege regained through a saved reference. And no
harness attenuates a subagent: subagents get their own rule set, not
the parent's intersection.

## Decision

1. **A session never widens itself.** Every change to a session's
   narrowing is a subset test; a change that would add a right is
   refused with its own classified kind (Capsicum's
   `CAPFAIL_INCREASE`; L1's `ENOTCAPABLE` vs `EACCES` distinction).
   The session object is copy-on-write and holds no reference to a
   wider one (framing memo T19).
2. **Rights are re-derived per call, never cached at open.** A grant
   revoked or added takes effect on the next statement (Plan 9's
   "checked at open, never again" is rejected). Widening therefore
   exists, but only *outside* the session: a principal with the
   authority adds a grant row, attributed to them (ADR 064), and every
   session sees it on its next call. The ask channel and the grant
   channel are different APIs (L5 #4).
3. **A sub-session's authority is the parent's intersected with its
   own.** A subagent, a child session, a delegated task: its profile
   is the parent's profile intersected with whatever it declares
   (Landlock's ptrace rule: the tracer must hold a superset; AWS's
   chained session cannot outlive or exceed its parent; OWASP ASI07).
   No harness does this; vfs states it as law.
4. **Widening is a new session from a new proof.** Where a workflow
   needs more than the session has, the answer is a fresh
   `Authority` constructed at the edge from fresh verification, never
   an in-session escalation (Plan 9's `#¤/capuse`: one-shot, minted by
   a trusted agent, spent once).
5. **`ask` is a Result, bound to the request.** A statement the
   session may not perform but a principal could allow returns a
   `pending` kind carrying a digest of the exact request. An answer is
   either a one-shot allowance for that digest or a grant row; both
   are attributed. A stale or foreign answer is dropped (ADK's
   argument match, A2A's `once` scope, Mirage's ledger). Timeout is
   the host's policy, never storage behaviour.
6. **The marked exception.** The system actor (ADR 062 rule 4) is the
   only authority that starts wider than a subject's grants. Its use
   is stamped on every row it writes.

## Options considered

- **Harness-style "always allow" inside the session.** Rejected. It is
  how every harness works, and it is the sendmail bug with a nicer
  name. The same outcome is reachable as an attributed grant row.
- **Cache rights at session open for speed.** Rejected. Zanzibar's
  zookies exist because "immediate" must mean the same thing
  everywhere; a stale session is a widening in disguise. The cost is
  ADR 067's problem.
- **Widening gated by a second party inside the session (macaroon
  discharge, S4U2self).** Considered; kept only as the grant-row
  channel. The second party is the principal who grants, and the grant
  lives on the spine.

## Consequences

- Roadmap 023's per-session namespace gets `RFNOMNT` semantics by
  default: once set, no operation may add or bypass a mount.
- Spec 070's facade gains `narrow()` and nothing that widens.
- A `pending` result kind and an ask ledger are new work, sequenced
  after the spine.
- Refusals come in three classified kinds: hidden (not found, ADR 065),
  denied by grant, refused by profile.
