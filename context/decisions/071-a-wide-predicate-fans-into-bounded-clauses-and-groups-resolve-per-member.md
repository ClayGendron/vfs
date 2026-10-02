# 071. A Wide Predicate Fans into Bounded Clauses, and Groups Resolve per Member

- **Status:** accepted 2026-09-28; rule 1 amended by 072 (Clay: "go with your recommendations
  for Q1, Q2 and Q3", then "Chunked fan" for the fallback, over the
  staged table the Q2 memo recommended). Amends ADR 067 rule 6 and
  settles ADR 067 rule 3's open details.
- **Date:** 2026-09-28
- **Deciders:** Clay Gendron
- **Decided by:** human (Clay, 2026-09-28). Drafted by Claude from the
  memo `../research/2026-09-28-group-permissions-max-within-min-across.md`
  and its oracle study `../research/studies/2026-09-28-group-permissions/`.

## Context

ADR 067 compiles an authority's rights into a literal predicate: one
arm per covering prefix, plus owner arms. Rule 6 capped the number of
arms and fell back, past the cap, to a correlated `EXISTS` against the
grant rows, "slower but bounded by one bind".

The Q2 memo showed the fallback is not one bind once groups exist. The
`EXISTS` must name every group in the caller's closure, and every
member's closure in a subject set: up to thousands of binds for a room
of people in many groups. It also found that S1's bind-only arm cap
gives about 16,300 arms on SQLite, which parses at most 998 terms in
one expression. So the cap had to count expression depth too.

The memo recommended a staged table: write the resolved arms to a
keyed table per authority and revision, and join it. That keeps one
bind, but it makes every first read of a new authority a write, and
adds a table to every engine.

The memo also confirmed Clay's case (Ann and John, each in their own
groups, acting together) is in scope and already decided by ADR 066
and 067: each person holds the maximum over their own and their
groups' rows; the pair holds the minimum of the two. It named seven
places the spec text had to be tightened.

## Options considered

- **Correlated `EXISTS` (067 rule 6 as written).** Rejected: not one
  bind with groups, and S1's slowest shape.
- **Staged resolved-prefixes table.** One bind, exact. Rejected: a
  read that writes, a new table per engine, and cleanup of stale
  stagings.
- **Chunked fan.** Split the arms into clauses the way glob splits its
  pattern fan, each clause inside the dialect's bind budget and
  expression depth; run the statement once per clause; merge. Exact,
  including for a top-k `LIMIT`: every row of the global top k is
  admitted by some clause and ranks at least as high within it.

## Decision

1. **A predicate too wide for one statement fans into clauses.** Each
   clause spends at most half the membership budget, leaving room for
   the statement's own id list, and the clause count per statement is
   capped by `arm_budget` (the same bind-and-depth budget glob's fan
   uses). The statement runs once per clause and the results merge by
   path. There is no `EXISTS` fallback and no staged table. Reads never
   write.
2. **`Rights.admits` in app code is the authority on every row.** The
   SQL clauses are pushdowns: they narrow what is fetched, and every
   fetched row still passes the Python check before it is shown.
3. **Groups resolve per member, never pooled.** Each subject's closure
   is its own. The rows for every subject, every closure group, and
   everyone (`*`) are fetched in one chunked `IN`. The membership walk
   runs one chunked statement per nesting level.
4. **Owner arms are per member.** Each subject gets an owner arm: rows
   it owns, under the meet of the *other* members' coverage, trimmed
   of what the shared arms already cover.
5. **The root prefix compiles to "true"**, never `path LIKE '//%'`.
6. **A posture hole cuts every covering everyone arm**, not only the
   nearest.
7. **Group ids are `group:<name>`** in the one `principal_id` column.
   A `Principal` refuses a `sub` with that prefix, and the reserved
   `*`. Membership comes from the `memberships` table only; a token's
   `groups` claim is ignored for rights.
8. **Membership writes are the system actor's only, in this landing.**
   Memberships carry `granted_by` and `granted_at`. Nesting is capped
   at 8 levels. Cycles and over-depth nesting are refused at write,
   under the lock the revision bump takes. The read-side walk refuses
   past the cap (`authority_budget`); it never truncates.

## Consequences

- A caller with a very wide grant set pays one statement per clause
  instead of one statement. The cost grows with its grant count, not
  with the corpus.
- No new table beyond `grants` and `memberships`; no read ever writes.
- A pooled-groups bug is caught by the resolver's oracle parity test
  (`tests/storage/test_grants.py`), which computes max-within,
  min-across path by path on random worlds with nested groups.
- A per-group admin flag (Postgres `ADMIN OPTION`, a Plan 9 group
  leader) is a follow-up; the spec's `/_groups/<id>` lean is dropped,
  because the default open posture made everyone its admin.
