# 067. The Enforcement Spine: Rights Compile to a Bounded Literal Predicate in App Code, at One Chokepoint, on Every Engine

- **Status:** accepted 2026-09-06 (Clay, each option put as a question and
  ratified as written; ratifies ADR 021 D1, D2, D4; amends D3; closes the groups fork). Drafted 2026-09-05 as Phase 3 of the
  principals and permissions research programme
  (`../research/2026-09-05-principals-and-permissions-research-plan.md`);
  companions 062 to 067 were ratified together.
- **Date:** 2026-09-05
- **Deciders:** Clay Gendron
- **Decided by:** human (Clay, 2026-09-06). Originally drafted by Claude from study S1
  (`../research/2026-09-05-permissions-predicate-at-scale.md`) and lens
  L4 (every engine that filters a list compiles the policy into the
  query at one place; the Zanzibar family cannot list cheaply under
  intersection).

## Context

ADR 021 fixed the grant model's spine from prior art and left the
mechanism's cost to measurement. Lens L4 confirmed the field's
consensus: Oracle VPD appends a predicate string, SQL Server binds an
inline table-valued function, Postgres prepends security quals, and
Oso, OPA and Cedar partially evaluate the policy and hand the residual
to SQL. SQLite has nothing, so app-level compilation is the only floor
that reaches every production engine. The Zanzibar systems check
cheaply and list expensively; under an intersection they degenerate to
one check per candidate.

Study S1 built the model at 111k and 995k entries with 10,000
principals, skewed ownership, five grants per principal, a few
everyone-style grants, groups, and subject sets of 2, 5 and 20, on
SQLite, Postgres, MariaDB, SQL Server and Oracle (the last two under
emulation; ratios and plan shapes are the evidence there). Its findings:

- The correlated `EXISTS` ADR 021 sketched works everywhere and is the
  slowest read shape: one grant-index probe per candidate row (a
  grep-shaped pass on Postgres: 10 ms as a literal predicate, 94 ms as
  `EXISTS`). Resolving the caller's covering prefixes first (about 10
  rows, one indexed read) and shipping them as literal `LIKE` arms is
  3 to 19 times faster on Postgres and never slower elsewhere.
- The ranked join-back (up to 3,000 candidate ids from `glean`) is
  bounded and fast in every shape when chunked by `membership_budget`.
- The write point check should not query per path: fetch the caller's
  grant rows once and resolve the longest prefix in app code (11 ms
  for 10k paths, one statement regardless of batch size).
- An exhaustive materialised `visible(principal, entry)` table is
  disqualified: everyone-grants make it 1,850 times the entry table,
  and it does not read faster.
- A membership subquery inside the `EXISTS` is catastrophic (35 s on
  Postgres, 188 s on MariaDB for the grep pass); the same rights as a
  literal group list cost 13 to 110 ms.
- For a subject set of 20, AND-of-`EXISTS` costs 314 ms and the grouped
  `HAVING COUNT(DISTINCT) = n` 130 ms on Postgres; the pre-resolved
  prefix intersection costs 22 ms, the same as a single principal,
  because the meet *shrinks* the prefix set and binds fall with n.
- No shape breaks a bind budget, but the literal forms are bounded by
  the caller's grant count, not the batch, so a declared cap is needed.

## Decision

1. **Grant rows stay as 021 decided:** additive-only, `(principal_id,
   path_prefix, level)`, prefix coverage `path = prefix OR path LIKE
   prefix || '/%'`, levels `invisible < read < read_write`, no deny
   rows, no materialised visibility table.
2. **Rights are resolved in app code, per statement, at one
   chokepoint, into a bounded literal predicate.** For the authority
   (ADR 062): read the grant rows of every subject and of every group
   each subject belongs to (one indexed statement per subject, or one
   chunked `IN` over the set), compute in app code the *covering prefix
   set* for the level the verb needs, and for a subject set the
   *intersection* of the members' covering sets (ADR 066), then compile
   that set into `owner_id = :p OR path LIKE :prefix_i || '/%' OR path
   = :prefix_i ...` arms. This is the query-side analogue of the
   dispatch funnel and the only place a predicate is built.
3. **Groups: a memberships table, resolved per statement into the
   literal.** ADR 021's fork closes toward a memberships indirection
   (the Zanzibar and database precedent) with the resolution done in
   app code and shipped as data, never as a subquery. Nested groups
   are resolved by a bounded walk with a declared depth.
4. **Writes check points from the same resolved rows.** The longest
   matching prefix for each path in a batch is computed in app code
   against the resolved grant rows; the batch fails whole at the gate
   before any statement (`EROFS` before the first byte, L1).
5. **Ranked join-back chunks by `membership_budget`** and uses the
   dialect's membership form (ADR 061); the predicate is applied inside
   the candidate query, before any content function (ADR 065 rule 4),
   and the statistics query joins the same predicate.
6. **Bounds are declared, not discovered.** A per-authority cap on the
   number of prefix arms (the sum over subjects after intersection)
   and on subject-set size, each with its own refusal kind; past the
   prefix cap the spine falls back to the correlated `EXISTS` form,
   which is slower but bounded by one bind. The grouped `HAVING` form
   is not used. Everything else is one bind plus the chunked candidate
   list.
7. **The resolved rights are cached per grant revision.** The
   covering-prefix set for an authority is memoised keyed by the spine's
   revision (ADR 064 rule 2); any grant or membership write bumps the
   revision. Statement caches are keyed by the authority's shape so a
   baked query is never reused across principals (L4).
8. **The system actor skips step 2 and is stamped** (ADR 062 rule 4).

## Options considered

- **Correlated `EXISTS` as the primary form (ADR 021 D3 as written).**
  Kept as the fallback past the cap; rejected as primary on S1's 3 to
  19x.
- **Materialised visibility (Zanzibar-shaped).** Rejected: 1,850x the
  entry table under everyone-grants, no read benefit.
- **Grouped `HAVING COUNT(DISTINCT principal) = n` for the set.**
  Rejected: 6x the intersection form at n = 20 and it repeats the
  candidate list three times.
- **Membership subquery in the predicate.** Rejected: seconds where
  the literal costs milliseconds.
- **Native row security where available (Postgres RLS, SQL Server
  security policies, Oracle VPD).** Rejected as the mechanism, kept as
  a possible belt-and-braces layer per engine: it cannot reach SQLite
  and would split the chokepoint.

## Consequences

- Spec 058 is written against a resolver (rows to covering prefixes to
  intersection to arms) plus a compiler (arms to a dialect-bounded
  predicate), both in app code, with S1's scripts as the benchmark and
  the budgets as declared constants on the `DialectProfile` only where
  SQLAlchemy takes no position.
- The grant table gains a revision counter; memberships gain a table.
- `glean`, `grep`, `glob`, listing and the edge verbs all take their
  predicate from one function.
- What becomes harder: a caller with thousands of distinct prefixes
  (a pathological grant set) pays the `EXISTS` fallback; the docstring
  says so and names the cap.
