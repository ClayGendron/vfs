# 021. The Row-Level Grant Model's Spine

- **Status:** proposed (2026-07-22) — drafted from an evidence review
  commissioned in session; **awaiting Clay's ratification.** Nothing in
  spec 058 should be written against this until it is accepted.
- **Date:** 2026-07-22
- **Deciders:** Clay Gendron
- **Decided by:** pending — drafted by Claude from first-hand prior-art
  research; the substance has not yet been argued by a human.
- **Scope:** fixes four load-bearing choices so spec 058 starts from
  decisions rather than from nine open forks. It does **not** decide
  058's remaining forks (NULL-owner writability, edge-row visibility,
  derived-row `owner_id` audit, ranked-search join-back, move/copy
  grant semantics), which need the full spec.

## Context

Spec 058 has sat open since 2026-07-10 with its clarification forks
unresolved, correctly sequenced behind spec 070 (`Principal`) because
enforcement semantics cannot be pinned without a verified identity. But
sequencing is not the same as leaving every question open: four of the
forks are answerable now from prior art and from constraints this
project has already committed to, and answering them removes most of
the design risk from the eventual spec.

The binding constraint throughout is CLAUDE.md's portability posture —
Postgres, SQL Server, Oracle, and other SQLAlchemy-compatible engines
are all production targets, and 10,000-entry batches are a supported
contract. Any enforcement mechanism that only works on one engine, or
whose predicate grows with batch size, is disqualified before its merits
are weighed.

## Decisions

### 1. Grant rows are additive-only

A grant row states a positive fact: this principal has this level over
this scope. There is no deny row. If subtraction is ever needed it
enters as a policy-layer expression over grants, never as a row that
races other rows for precedence.

**Grounding.** The canon separates these two layers consistently.
Postgres RLS combines *permissive* policies with OR and *restrictive*
with AND — `postgres/src/backend/rewrite/rowsecurity.c:213-214`:
"Restrictive policies are combined together using AND, and permissive
policies are combined together using OR" — so deny exists, but as a
policy construct, not as a tuple. The Zanzibar-lineage systems say the
same: SpiceDB's exclusion is a *schema* operator
(`pkg/schemadsl/compiler/compiler_test.go:559-561`,
`permission foos = bars - bazs`; builder at `pkg/namespace/builder.go:231`),
while relationship tuples are purely additive facts; OpenFGA's "but not"
is likewise a model-level rewrite
(`pkg/typesystem/typesystem.go:628-629`). The one system with
tuple-level deny is Jackrabbit Oak's `rep:DenyACE`
(`oak-security-spi/.../AccessControlConstants.java:138`) — the
cautionary tale spec 058 already cites.

**Consequence.** The read predicate stays a bare `EXISTS` over the
grants table, which is 058's own lean, and longest-prefix resolution is
confined to write-time point checks. It permanently forecloses
"share this folder except this one file" as a grant row; that story
would need a policy-layer construct.

### 2. Grants attach to path prefixes

A grant names a path scope; coverage is computed from the entry's path
string at query time.

**Grounding.** Supabase storage — 058's own "closest overall match" —
compiles prefix-scoped listing into SQL functions
(`storage/migrations/tenant/00010-search-files-search-function.sql`,
`0020-list-objects-with-delimiter.sql:3`, `prefix_param text`).

**Consequence, and the coupling that must be tracked.** This entrenches
`Entry.path` as the grant coordinate, which is only coherent while an
entry has exactly one path. The parked full-dirent question
(`open-questions.md`) would give an entry many paths via hard links,
making prefix coverage ambiguous — the classic POSIX hard-link
permission problem. **Accepting this decision raises the cost of ever
unparking that one**, and the two entries now cross-reference each
other for that reason. If the indexed prefix range scan fails to hold at
10,000-row scale on any target engine, GitLab's `traversal_ids` is the
recorded alternative encoding.

### 3. Enforcement is app-level predicate compilation at one chokepoint

The grant predicate is compiled into the query at the single
query-construction chokepoint, in SQLAlchemy Core, on every engine.
Postgres RLS is available later as defense-in-depth for
Postgres-only deployments; it is not the portable baseline.

**Grounding.** Supabase can lean on RLS because it is Postgres-only.
vfs cannot: RLS has no equivalent on the MSSQL profile or the GENERIC
floor, and CLAUDE.md forbids designing to one engine's capabilities.
One chokepoint also means one place to audit, which is the property
that makes an app-level scheme defensible at all.

### 4. `Principal.system()` bypasses row grants

Restated here as the grants layer's contract; the decision itself is
spec 070's.

**Grounding.** The same shape appears in the reference implementation:
`storage/migrations/tenant/0002-storage-schema.sql:30` —
`CREATE ROLE service_role NOLOGIN NOINHERIT bypassrls`.

## Options considered

- **Leave all forks to spec 058.** Rejected: four of them are decidable
  now, and 058's spec-writing is materially harder with them open.
- **Tuple-level deny (Oak's shape).** Rejected: forces longest-prefix
  resolution into every read predicate, and 058 already records it as a
  cautionary tale.
- **RLS as the portable baseline.** Rejected on portability grounds
  above.
- **Ids rather than paths as the grant coordinate.** Deferred, not
  rejected — it is what the full-dirent end-state would require. Chosen
  against for now because paths are what 058's consumers speak and what
  every prefix-listing precedent uses.

## Open, deliberately

The **groups fork** — whether v1 carries a user-only `principal_id` or
a memberships indirection — is *not* decided here. The lean is
user-only with opaque ids, but the evidence is genuinely thin in both
directions: the Zanzibar systems ship groups first-class from day one,
and they are standalone authorization products, so the analogy to a
library cuts both ways. This is the fork most likely to need Clay's
judgment rather than more research.

## Consequences

- Spec 058 starts from four settled choices and five real forks.
- The full-dirent question becomes measurably more expensive to unpark;
  that cost is now recorded in both open-questions entries rather than
  discovered later.
- Per-principal *execute* policy has a home: a level in this ladder,
  not a reopening of spec 039.
- Still blocked on spec 070 landing before 058 can be written.
