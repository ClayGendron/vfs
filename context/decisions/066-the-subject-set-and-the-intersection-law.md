# 066. Multiplayer: the Subject Set, the Intersection Law for Read and Write, and the Join and Leave Rules

- **Status:** proposed 2026-09-05 (Phase 3 of the permissions
  programme); **awaiting Clay's ratification.** Companion to 062
  (which defines the set as the subject part of an authority), 064
  (attribution of a set), 065 (hide-for-any-member) and 067 (the
  predicate shape). Binds spec 070's session facade and spec 058's
  predicate.
- **Date:** 2026-09-05
- **Deciders:** Clay Gendron
- **Decided by:** pending — the rule is Clay's (2026-09-05: "a list of
  principals ... act in a least privileged way on behalf of all of them
  (can read or write unless all principals share the permission)");
  the grounding is drafted by Claude from lenses L1 to L5, the framing
  memo (T58 to T64) and studies S1 and S2.

## Context

An agent often works for several people at once. Claude tagged in a
group chat is the canonical case: every reply is seen by every member,
so it must not surface what any one member cannot see and must not
change what any one member cannot change. The research asked where
anyone has computed the greatest lower bound of several people's rights
and acted under it.

The answer is: almost nowhere, and the one place is exact. Unix's
supplementary groups, the sticky bit and best-match ACL groups are
*joins*; every meet in the lineage (Landlock layers, Capsicum rights,
the bounding set, jail flags, veto chains) is one principal narrowing
itself. Plan 9's only shared session (`srv -a`, `9pserve -A`) collapses
every client into the poster. Tokens attenuate one authority block and
cannot express the meet of two people's grants. Every identity token in
the field has exactly one subject. The vendors ship three
approximations: space-only content (Claude Tag), asker-plus-leak-gate
(Microsoft Copilot in Teams), and a per-room service account (Claude
Tag's connected tools, which Anthropic documents as "available to every
member"). The one exact precedent is SpiceDB's intersection arrow,
`relation.all(permission)`: every subject in the live relation must
hold the right, an empty set denies, caveats AND, and membership is
read live so a joiner narrows the next check immediately. Bell-LaPadula
is not the meet on both axes ("no write down" lets the lowest member
write the most), so the read-and-write rule needs its own statement.

## Decision

1. **The subject of a session may be a set.** It is non-empty; an
   empty set denies everything (ADR 062 rule 2).
2. **The intersection law.** The session holds a right on a row only
   when *every* member holds it: a row is readable iff readable by
   every member, writable iff writable by every member, and search
   statistics are computed over the intersection of the members'
   visible sets (ADR 065). This is stricter than Bell-LaPadula on the
   write side, deliberately: the reply and the write are the room's,
   and the room's lowest-cleared member must be able to stand behind
   both.
3. **The meet is computed on the spine, per statement, from live grant
   rows.** It is never carried in a token and never crosses a wire as
   an object; a remote mount receives the verified member names under
   the near side's attestation and re-derives the meet under its own
   table, where a member it does not know holds nothing and so the
   meet is empty (ADR 062 rule 6). The predicate shape is ADR 067's.
4. **The actor contributes nothing; admin in the set is one term.** An
   admin bot in a group chat adds no rights (framing memo T62). An
   admin *member* is intersected like anyone else. A per-room service
   account is a set of one service principal (ADR 062 rule 5), and
   naming it so is the whole protection.
5. **Joining narrows at once; leaving never widens.** A member added to
   the session narrows the very next statement (SpiceDB's live read;
   Landlock's "a new layer applies immediately"). What the session
   already surfaced is not re-graded, but the audit shows the set at
   each version (ADR 064). A member leaving does not widen the live
   session: the session stays at the old meet until it is re-minted
   from a fresh edge proof (ADR 063 rule 4; no attenuation system
   widens a live credential). The field does the opposite on both
   counts (joining widens the joiner's view of history in Teams and
   Claude Tag); vfs is the first to say otherwise, and says it because
   the room, not the joiner, is the unit of safety.
6. **Hidden from any member is hidden from the session** (ADR 065
   rule 7), and a refusal in the room never tells the room what one
   member cannot see.
7. **Space-only is the zero-grant baseline.** Content the room itself
   holds (a mount every member may read) passes the meet trivially;
   naming it lets a deployment start there and add grants.
8. **The set is bounded.** A declared budget on set size, with its own
   refusal kind when exceeded (AWS's `PackedPolicyTooLarge`), keeps
   the compiled predicate inside every dialect's bind budget.
9. **Ownership of what the set creates is the container's** (ADR 064
   rule 4): `owner_id` NULL, every member's access via the prefix
   grants that admitted the write.

## Options considered

- **Asker-plus-leak-gate** (compute under one member, detect the set
  difference, ask before sharing). Rejected: it detects the leak
  instead of avoiding it, and its refusal confirms existence.
- **Space-only as the whole answer.** Kept only as the baseline
  (rule 7); it answers no question that needs a member's grants.
- **A per-room service account instead of the members.** Rejected as
  a substitute (it is the inversion of least privilege); kept as one
  principal kind that may sit in a set.
- **Bell-LaPadula's lowest clearance.** Rejected: right for reads,
  wrong for writes.
- **Leaving widens the live session.** Rejected: nothing in fifty
  years of attenuation widens a live credential, and a departed
  member's grants may already have shaped what the room holds.

## Consequences

- Spec 070's facade takes `subjects: Iterable[Principal]`; the single
  principal is the set of one.
- Spec 058's predicate is set-valued from day one; ADR 067 chooses the
  shape from study S1.
- The version side table (ADR 064) carries one row per member.
- Study S2's multiplayer partition (intersection statistics within
  0.017 nDCG@10 of global down to a 17 % corpus) is the quality
  guarantee to pin.
- Open, deliberately: whether a session may *re-grade* already
  surfaced content on join is a product decision; the ADR fixes only
  that future statements narrow.
