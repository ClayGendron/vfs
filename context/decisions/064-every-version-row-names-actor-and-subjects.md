# 064. Attribution: Every Version Row Names the Actor and the Subjects, and Ownership Comes From the Container

- **Status:** accepted 2026-09-06 (Clay, each option put as a question and
  ratified as written; amends ADR 013/017 and resolves ADR 021's NULL-owner fork). Drafted 2026-09-05 as Phase 3 of the
  principals and permissions research programme
  (`../research/2026-09-05-principals-and-permissions-research-plan.md`);
  companions 062 to 067 were ratified together.
- **Date:** 2026-09-05
- **Deciders:** Clay Gendron
- **Decided by:** human (Clay, 2026-09-06). Originally drafted by Claude from lenses L2 (the auth
  server collapsing `cuid = suid`), L3 (RFC 8693 `act`, AWS
  `SourceIdentity`, macaroon discharges), L4 (`SESSION_USER` vs
  `CURRENT_USER`; no engine records the pair), L5 (only Entra records
  both; Claude Tag has "no per-action log of every task and who asked").

## Context

The audit is where the actor/subject pair earns its keep, and it is
where every precedent loses it. Plan 9's auth server writes one name
into both ticket slots; Kerberos writes the user as `cname` even when a
service acted; fastmcp logs `client_id` as `enduser.id`; Claude Tag
keeps no per-action log. Only Entra Agent ID records both, and only
because the agent is a directory object.

Two questions the multiplayer case adds have no precedent anywhere: who
*owns* a row a set of subjects creates, and how the audit records a
set. The nearest shapes are macaroon discharges (one per third party)
and AWS transitive session tags (one per hop).

## Decision

1. **Every version row records the actor and every subject.** The
   actor is one column. The subjects are one row per member in a side
   table keyed by `(entry_id, version_number)`, because a set can be
   large and the schema must not grow a variable-width column. Both
   are the *verified* names (Plan 9's `cuname`, never the claimed one).
2. **Every version row records provenance and the grant revision.**
   Provenance is one of: subject verified at the edge, subject named at
   construction, system-asserted (ADR 062 rule 4). The grant revision
   is the spine's revision in force when the statement ran
   (Zanzibar's zookie), so a later reader can answer "under which
   grants was this allowed" without replaying history.
3. **The delegation chain is kept, and only the current actor is used
   for policy.** RFC 8693 §4.1: nested `act` claims are attribution,
   not authority. A `source_identity` set once at the edge and
   inherited by every sub-session records who started the chain.
4. **Ownership comes from the container.** `owner_id` is set only when
   the subject set has exactly one member, and then to that member: the
   owner floor (never locked out of one's own rows) applies to a
   person. A row created by a set has `owner_id` NULL, which means *no
   owner floor*: every member's access to it comes from the prefix
   grants that let them write there in the first place (Unix default
   ACLs and NFSv4 inherit flags: the container's default beats the
   creator's umask). This resolves ADR 021's NULL-owner fork: NULL
   grants nothing and is governed by its ancestors.
5. **Ownership never transfers by narrowing.** A principal can never be
   locked out of its own grants by a session's narrowing (NFSv4's
   owner-keeps-`WRITE_ACL`), and `move` does not change `owner_id`.
6. **Revert is a write under current grants.** Who may revert is who
   may write the target path now, with the target version's content;
   the version row of a revert names its actor and subjects like any
   write (Plan 9's dump served under the same permissions; L4's
   content-change zookie). A narrowed actor may not revert its own
   earlier write if it may no longer write there.

## Options considered

- **A synthetic principal id for the set** (one column, the set hashed
  or named). Rejected: no precedent, and it hides the members from the
  audit that exists to show them.
- **Owner = the actor** (the field's answer: "the actor owns it, the
  room can see it"). Rejected: an actor contributes no rights (ADR 062
  rule 1), and an owner floor would give it some.
- **Owner = every member, as grant rows on the new path.** Rejected:
  it converts a prefix model into a per-row ACL at write time and
  breaks the 10k-batch contract.

## Consequences

- `versions.created_by` is renamed or joined by an `actor` column and a
  `version_subjects` side table; ADR 013's row shape changes.
- The reversibility invariant now composes with the permission
  invariant through one rule: revert is a write.
- Batch loaders under the system actor stamp `owner_id` per row as
  data (070 D4) and are recorded as system-asserted.
