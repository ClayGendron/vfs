# 148 — Sessions: narrowing, sub-sessions, the subject set's lifecycle, and the `pending` kind

- **Status:** seed — born 2026-09-06 from ADR 063 (the session law)
  and ADR 066 (the subject set), ratified by Clay the same day. Not
  scheduled; sequenced after 070 (the facade it extends) and 058 (the
  grants a narrowing narrows). `[NEEDS CLARIFICATION]` markers are
  unresolved forks.
- **Born from:** ADR 063, ADR 066 (join and leave; the leak-notice
  follow-up), the Mirage memo §3.6 to §3.9 and §4.3 to §4.5
  (`../../../research/2026-09-04-mirage-design-patterns.md`), the
  YoloFS memo §5.3 (progressive permission), lens L5's harness findings
  (`../../../research/2026-09-05-permissions-lens-agent-native-2026.md`
  Q2, Q5, take rows 2 to 6, 10, 15, 16), roadmap 023 (per-session
  namespaces)
- **Date:** 2026-09-06
- **Owner:** Clay Gendron
- **Kind:** feature (session state beyond the authority: a narrowing
  document, sub-sessions, set membership changes, the `pending` result
  kind and its ledger)
- **Depends on:** 070 (`Session`, `Narrowing.NONE`), 058 (grants;
  the refusal kinds), 047 (error vocabulary; this spec adds
  `pending` and a profile refusal sub-kind)

## Intent

070's session carries an authority and a lifecycle and nothing else.
This spec gives `Narrowing` content and the session three powers,
each of which can only *reduce* what the session may do: a profile
that hides paths and denies verbs, sub-sessions that inherit the
parent's intersection, and a subject set that can be narrowed by a
joiner. It also gives the session one way to say "not now, but
someone could allow this": the `pending` kind, bound to the exact
request, answered outside the session by an attributed grant or a
one-shot allowance.

## Decided semantics (from the ADRs)

1. **Narrowing only.** `session.narrow(profile)` returns a new session
   whose narrowing is the old one intersected with `profile`; a
   profile that would add a right is refused with
   `vfs.permission_denied.profile`? `[NEEDS CLARIFICATION: the refusal
   for "this would widen" is a caller error (`invalid`) or a
   classified permission kind; lean: `invalid`, since the request is
   malformed, and a *profile* refusal at verb time is the sub-kind]`.
   The session object is copy-on-write and holds no reference to a
   wider session (ADR 063 rule 1).
2. **The profile document** is one frozen value: `paths` (hide
   globs, show globs), `verbs` (deny list), `mounts` (per-prefix
   narrowing). Rules resolve by Mirage's anchor depth (deeper wins,
   ties break by verb) `[NEEDS CLARIFICATION: adopt anchor depth, or
   vfs's longest-prefix rule from `PermissionMap`; lean: longest
   prefix, one rule for structure and profile]`. A hide is a
   projection before any lookup (ADR 065 rule 3). Refusal by profile
   is classified apart from refusal by grant (`ENOTCAPABLE` vs
   `EACCES`, lens L1).
3. **Sub-sessions intersect.** `session.child(profile=..., subjects=...)`
   yields a session whose narrowing is the parent's ∩ its own, whose
   subject set is a superset of the parent's? `[NEEDS CLARIFICATION:
   may a child *add* subjects (narrowing the meet) but never remove
   one; lean: yes, adding is narrowing]`, whose `source_identity` is
   inherited (ADR 064 rule 3), and whose lifetime ends with the
   parent's (AWS chained sessions).
4. **Join and leave.** `session.join(principal)` narrows the very next
   statement; nothing already surfaced is re-graded (Clay,
   2026-09-06); a **leak notice** is a follow-up: on join, return the
   set of previously surfaced paths the joiner cannot see, which
   requires the session to remember what it surfaced
   `[NEEDS CLARIFICATION: in scope here or a later spec; lean: a
   `surfaced` ring buffer with a declared cap, here]`. There is no
   `leave`: a member leaving is a new session from a fresh edge proof
   (ADR 066 rule 5).
5. **`pending`.** A verb the narrowing or the grants refuse but a
   principal could allow answers a `Result` with a `pending` record
   carrying a digest of the exact request (verb, canonical arguments,
   authority shape, grant revision) and a TTL. `session.answer(digest,
   allowance)` is *not* a session method: answers are grant rows (058's
   `grant`) or one-shot allowances recorded in an **ask ledger**
   keyed by digest, written by a principal with the authority through
   the grant channel, never through the session. A re-run of the same
   request with a live allowance proceeds once; a stale or foreign
   answer is dropped (ADK's argument match; A2A's `once` scope).
   Timeout is the host's policy; storage never blocks, crashes or
   auto-rejects (L5 take row 15).
6. **Namespaces (roadmap 023).** A per-session namespace overlay, if
   it returns, is session state on this type with `RFNOMNT`
   semantics: once set, no operation may add or bypass a mount.

## Non-goals

- The wire shape of `pending` (MRTR `requestState`): spec 149 and the
  MCP stateless memo §8.5.
- Grants themselves (058); the edge (149).

## Acceptance criteria (first cut)

- `narrow` never widens (property test over random profiles); refusal
  kinds distinct for profile and grant.
- A child session cannot do what its parent cannot (property test).
- `join` narrows the next statement; the audit shows the new set.
- `pending` carries a digest; a one-shot allowance admits exactly one
  re-run; a grant row admits all subsequent runs; a foreign answer
  admits nothing.

## Open questions

- The three markers above; whether the ask ledger lives in storage
  (per mount) or on the router (one ledger per instance).
