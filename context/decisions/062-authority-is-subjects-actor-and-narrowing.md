# 062. Authority Is a Subject Set, an Actor, and a Narrowing: the Model Every Statement Runs Under

- **Status:** accepted 2026-09-06 (Clay, each option put as a question and
  ratified as written; supersedes the shape of spec 070's decision 1; keeps 070's decisions 4, 6 and 7; refines ADR 006 and ADR 058). Drafted 2026-09-05 as Phase 3 of the
  principals and permissions research programme
  (`../research/2026-09-05-principals-and-permissions-research-plan.md`);
  companions 062 to 067 were ratified together.
- **Date:** 2026-09-05
- **Deciders:** Clay Gendron
- **Decided by:** human (Clay, 2026-09-06). Originally drafted by Claude from the five lens memos,
  the framing memo and the two studies; the position is Clay's
  (2026-09-05: "an agent is an entity that acts on behalf of a
  principal; all actions are scoped to a principal, admin being one").
- **Context source:** the synthesis memo
  `../research/2026-09-05-permissions-synthesis.md` and the lens memos
  it digests.

## Context

vfs has two safety invariants. The first, every action is reversible
or versioned, exists (ADR 013, 017, 027). The second, every action is
scoped to a principal, does not: `user_id` is plumbed and inert, and the
only enforcement is per-mount path rules that treat every caller the
same. The MCP server cannot ship before the second invariant without
shipping fail-open.

The research tested one shape against fifty years of prior art: a
**subject** (whose rights apply), an **actor** (who is doing the work),
and **attenuation** (the actor holds at most the subject's rights, and a
session can only narrow them). The shape survived, with three
corrections the lenses forced:

1. The actor/subject split in Unix (real vs effective uid) and Plan 9
   (`hostid` vs `uid` in the ticket request) was built to *widen* or is
   *thrown away* at a boundary. Setuid exists so a program can run
   above its invoker; Plan 9's auth server writes the same name into
   both slots before the file server sees the ticket. The precedent
   is for the *pair*, not for what the pair is for. vfs's pair exists
   to attribute and to narrow, never to widen, and it must survive
   every boundary.
2. No system runs on intersection alone; each ships a named, gated
   widening (Casper, macaroon third-party caveats, Kerberos S4U2self,
   AWS resource policies naming a session, `SECURITY DEFINER`). The
   best of them stamp its use in the audit. vfs names exactly one and
   stamps it.
3. Every identity token in the field has exactly one subject. A set of
   subjects (the multiplayer case, ADR 066) is a session construct
   computed where the grants live, never a wire object.

## Decision

Every statement vfs executes runs under one **authority**, a frozen
value with three parts:

| Part | Meaning | Where it comes from |
|---|---|---|
| **subjects** | the non-empty set of principals whose grants apply | verified at the edge (070 D6), or named at construction for the library case (070 D4's `default_principal`) |
| **actor** | the principal doing the work: an agent, a service, or the subject acting directly (then actor = subject) | the edge (the token's `act` claim, the agent's own identity) or construction |
| **narrowing** | the session's profile: what this session has given up | the session (ADR 063); starts at "nothing given up" |

The **effective rights** of a statement are

> the intersection, over every subject in the set, of that subject's
> grants (ADR 067), intersected with the actor's profile, intersected
> with the session's narrowing, intersected with the structural rules
> (path-space permission maps, op masks, topology locks) that bind
> every caller.

Six rules follow and are binding:

1. **The actor contributes no rights.** An agent acting for Alice can
   never do what Alice cannot, whatever the agent's own grants. The
   actor's profile only narrows. (Hardy's deputy; framing memo T12 to
   T15 and T62.)
2. **An empty subject set denies everything.** It is not vacuously
   true. (SpiceDB's intersection arrow, `check.go:842-844`; 070's
   fail-closed rule.)
3. **Admin is a principal.** An administrator is a subject with wide
   grants who goes through the same pipeline, can be vetoed by
   structure, and is named in the audit like anyone else. Root as a
   principal through the same evaluator, with jail and MAC able to
   veto it, is the Unix lesson (`kern_priv.c`); Casbin's `r.sub ==
   "root"` matcher term is the engine version.
4. **One marked exception: the system actor.** `Principal.system()`
   (070 D4, resolved with Clay 2026-07-10) is an actor with no subject
   that bypasses row grants and only row grants, for batch loaders and
   backups. Every version row it writes is stamped as system-asserted
   (Kerberos's `SERVICE_ASSERTED_IDENTITY`), it never crosses a wire,
   and structure still binds it. A stricter mode that *errors* rather
   than bypasses when a grant would have filtered (Postgres
   `row_security = off`) is the shape for backups and audits.
5. **A service principal is an actor whose profile is its whole
   authority.** When an agent is deployed as its own identity (Claude
   Tag's per-room account, Entra Agent ID), vfs models it as actor =
   subject = the service principal, with the sponsoring admin recorded
   in the audit (Entra's mandatory sponsor). It is one principal in a
   subject set like any other; it is never a way around one.
6. **The pair survives every boundary.** Version rows, results, logs
   and remote mounts carry both the actor and the subjects (ADR 064).
   A remote mount's far side re-derives rights under its own principal
   table from the *verified names* the near side attests (Plan 9's
   text names on the wire, each side owning its id table); it never
   trusts a forwarded token (070 D7).

The value shape: `Principal(sub, scopes, kind)` with `kind` one of
`user`, `service`, `system`; an `Authority(subjects, actor, narrowing)`
frozen value constructed at one site (070 D1's single construction
site, widened to the triple). Groups are not on the principal; they
are resolved by the spine per statement (ADR 067).

## Options considered

- **Impersonation (actor = subject, "act as").** Rejected. It is
  setuid: the audit lies about who acted, and every harness that does
  it has the confused deputy on record. The field's own drift is the
  other way (Entra OBO, RFC 8693 `act`).
- **Agent as its own principal only (service accounts, no on-behalf-of).**
  Rejected as the *only* model, kept as rule 5. It is what Claude Tag
  ships for connected tools and Anthropic documents the consequence:
  "whatever the connected account can read or write is available to
  every member". A shared credential is the inversion of least
  privilege.
- **Capabilities in a bearer token (macaroon/biscuit style grants).**
  Rejected for the data plane (lens L3). vfs's grants are large and
  mutable; every token system keeps the big policy server side and
  ships only the narrowing. Attenuation is kept; the token is not.
- **`switch hats`: an agent serving several people picks one subject
  per call.** Rejected. It is Hardy's failed fix. The subject set
  (ADR 066) removes the choice.

## Consequences

- Spec 070 is rewritten around `Authority`: the session facade
  constructs it once; every verb threads it; storage consumes it as
  trusted data (070 D3 stands).
- Spec 058's predicate compiles from the subject set, not a single
  `principal_id` (ADR 066, 067).
- Version rows gain the actor and the subject set (ADR 064); the
  `created_by` column is no longer enough.
- The actor's profile and the session narrowing are the same
  mechanism at two levels (ADR 063).
- The MCP `serve()` spec builds the edge: token in, `Authority` out,
  nothing identity-shaped accepted as a parameter.
- What becomes harder: every read and write carries a set-valued
  predicate; ADR 067 prices it from study S1.
