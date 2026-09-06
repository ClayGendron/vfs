# 058 — Row-level grants: the enforcement spine

- **Status:** shaped — **written in full 2026-09-06 against ADR 067**
  (and 062, 064, 065, 066; all ratified by Clay 2026-09-06) after the
  principals and permissions research programme; the 2026-07-08 seed's
  forks are all resolved below. Awaiting Clay's read before
  implementation (Clay, 2026-09-06: "rewrite the specs only, then stop
  for review"). Sequenced after 070.
- **Date:** 2026-09-06 (seed 2026-07-08)
- **Owner:** Clay Gendron
- **Kind:** feature (authorization: grant rows, the resolver and the
  compiler at one chokepoint, enforcement on every read, write, ranked
  and topology verb, visible-set search statistics, the grant admin
  verbs, and a conformance suite)
- **Depends on:** 070 (the `Authority` the spine consumes; attribution
  columns), ADR 061 (membership helpers), the dialect budgets
  (`storage/backends/database/dialects.py`)
- **Decisions it implements:** ADR 067 (the spine), ADR 065 (hidden
  rows are absent; statistics over the visible set), ADR 066 rules 2,
  3, 6, 8, 9 (the intersection law and its predicate), ADR 064 rules
  2, 4, 5, 6 (grant revision; ownership from the container; revert is
  a write), ADR 021 as ratified
- **Studies it is benchmarked against:**
  `../../../research/studies/2026-09-05-permissions-predicate-at-scale/`
  (S1: the shapes and their costs per engine) and
  `../../../research/studies/2026-09-05-glean-statistics-leak/` (S2:
  the leak the statistics rule closes)
- **Subsumes:** the old 009 grants layer (share links and capability
  tokens remain a future spec); `permissions.py`'s path-space
  `PermissionMap` stays as *structure* that binds every caller (ADR
  062's structural term), unchanged

## Intent

Two callers, same query, different rows, enforced in the SQL itself
and never by post-filtering. Spec 058's seed said that; the ADRs now
say how. **Ownership is a column, sharing is a relation, grants attach
to the namespace, levels form a ladder, reads filter sets, writes
check points, and the meet of a subject set is computed where the
grants live.** Study S1 fixed the mechanism: resolve the caller's
rights in app code to a bounded literal predicate at one chokepoint.
Study S2 fixed the one thing the seed missed: statistics are part of
visibility.

## Decided semantics

### 1. The rows

- **`grants(principal_id, path_prefix, level, granted_by, granted_at,
  revision)`.** Additive-only: a row states a positive fact and there
  is no deny row. `principal_id` is a `sub` (070) or a group id.
  `path_prefix` is a canonical vfs path in **mount-relative
  coordinates** (as `PermissionMap` rules are), stored in the same
  bytewise collation as `entries.path`; `/` means the whole mount.
  `level ∈ {read, read_write}`; *invisible* is the absence of any
  covering row. Index `(principal_id, path_prefix)`.
- **`memberships(principal_id, group_id)`**, resolved per statement
  (ADR 067 rule 3). Nested groups are walked in app code to a declared
  depth `MAX_GROUP_DEPTH`; a deeper nesting is refused at membership
  write, never silently truncated at read.
- **`grant_revision`**: one monotonic counter per storage, bumped by
  every grants or memberships write; stamped onto each version row
  (`versions.grant_revision`, ADR 064 rule 2) and used as the memo key
  for resolved rights.
- **Coverage** is by prefix: `path = prefix OR path LIKE prefix || '/%'`
  with `%` and `_` in prefixes escaped per dialect. The prefix
  coordinate entrenches against the parked full-dirent end-state
  (`open-questions.md`); that cost is accepted with ADR 021.

### 2. The ladder and the floor

`invisible < read < read_write`. A subject's level on a path is the
**maximum** over all covering rows, its own and its groups'.
Additive-only means more rows only widen, so no longest-prefix
resolution is needed on the grant side. (Longest-prefix resolution
belongs to *structure*, `PermissionMap`, where restriction tightens;
grants only widen.)
The **owner floor**: `owner_id = sub` is an implicit `read_write` for
that subject; it applies per member inside a set (ADR 064 rule 4; a
set-created row has no owner and no floor).

### 3. The resolver (app code, one function)

For an `Authority` and a verb's required level:

1. Read every subject's grant rows and its groups' rows: one indexed
   statement per subject (`principal_id IN (:sub, :g1, ...)`, chunked
   by `membership_budget`), memoised per `(authority shape,
   grant_revision)`.
2. Per subject, compute the **covering prefix set** at the required
   level: the minimal set of prefixes (a longer prefix under a
   qualifying shorter one is dropped).
3. For a set, compute the **meet**: the intersection of the members'
   covering sets, where "intersection" of prefix sets is the set of
   longest common coverage (a prefix `p` survives iff every member has
   a covering prefix that is `p` or an ancestor of `p`; the result is
   the deepest such `p`s). S1 measured this shrinking the arm count as
   the set grows.
4. Emit `ResolvedRights(arms: tuple[str, ...], owner_subject: str |
   None, fallback: bool)`. `owner_subject` is set only for a set of
   one. `fallback` is set when `len(arms) > MAX_PREFIX_ARMS`; the
   compiler then emits ADR 067's correlated `EXISTS` against the
   grants table for that subject, bounded by one bind, and for a set
   the AND of per-member `EXISTS`. It is slower and the docstring
   says so.

`MAX_PREFIX_ARMS` is derived, not guessed: `(parameter_budget - the
statement's other binds) // 2`, floored at a declared minimum, so the
literal form never exceeds a dialect's bind budget at a 10k batch.
`MAX_SUBJECTS` is 070's.

### 4. The compiler (app code, one function)

`visible(rights) -> ColumnElement`: `owner_id = :o` (only when
`owner_subject`) `OR path = :p_i OR path LIKE :p_i_esc || '/%'` for
each arm. The same function serves every read builder. For the
`fallback` shape it emits the `EXISTS` form. Statement caches are keyed
by the arm count and owner presence, never reused across authorities
with different shapes (ADR 067 rule 7).

### 5. Reads filter

Every read applies `visible(rights_at(read))` inside the query, before
any content function (ADR 065 rule 4): `read`, `stat`, `ls`, `tree`,
`glob`, `grep` (the regex runs only on admitted rows; the gram
prefilter joins back through the predicate before scoring), `glean`
(the candidate query carries the predicate before scoring and `LIMIT`;
the vector leg's distance is computed only on admitted rows), `graph`
and the edge reads (an edge is visible iff **both** endpoints are
visible), `locate` (table facts only; hidden answers not-found),
`versions`, and the memory entry's `ls` of mount points (mount points
are structure and always visible). A hidden row is `not_found`, with
the same payload as an unknown path.

### 6. Writes check

Every mutating verb resolves at `read_write` and checks each target
path's longest matching arm in app code (ADR 067 rule 4); a batch of
10k paths is one resolver call and no per-path statement. The batch
**fails whole at the gate** before the first statement. Refusal kinds:
a target the authority cannot *see* answers `not_found` (ADR 065 rule
2); a visible target it may not write answers `permission_denied`;
structure's read-only answers `read_only` as today. A write that would
return the row it wrote never silently drops it. `move` needs
`read_write` at source and destination for every subject and is a
permission event: rows leaving a granted prefix become invisible to
those who held only that prefix (decided, not a surprise; the info
record names it). `copy` stamps `owner_id` per ADR 064 rule 4.
`restore` and revert are writes under current rights. `sweep`
(destruction) requires `read_write` on the swept prefix for every
subject, and the system actor is the intended caller. `mkedge` needs
`read_write` on the source and `read` on the target; `rmedge` needs
`read_write` on the source.

### 7. Statistics are visibility (ADR 065 rule 5)

`glean`'s `N`, `avg_dl` and per-term `df` are computed over the rows
`visible(rights_at(read))` admits, in the same statement family that
fetches candidates, memoised per `(authority shape, grant_revision,
index generation)`. The mount's `lexical_stats` export to the
cross-mount merge is computed over the same visible set and carries
only terms a visible row contains; the merge's union fallback is
therefore visible-scoped by construction. S2's scripts become a
regression: with a hidden partition, a visible document's score is
identical to the score computed on the visible corpus alone.

### 8. The grant verbs

Router verbs, gated like any mutating verb, and the only way widening
happens (ADR 063 rule 2):

- `grant(path, principal, level, *, authority)`: the granting subject
  set must hold `read_write` on `path` (every member), and may grant at
  most its own level (attenuation); the system actor may grant
  anything. Writes a row with `granted_by = actor` and bumps the
  revision.
- `revoke(path, principal, *, authority)`: same gate; removes rows the
  granter could have written.
- `grants(path, *, authority)`: lists rows on `path` and its ancestors
  the authority can see (its own, its groups', and all rows if it holds
  `read_write` there).
- Memberships are administered through `add_member` / `remove_member`
  by the system actor or a principal holding a declared `groups:admin`
  scope `[NEEDS CLARIFICATION: scope name and whether a group has an
  owner principal, as Plan 9's group leaders; lean: a group is a
  principal whose own `read_write` grant on a reserved
  `/_groups/<id>` path is the admin right, so no new scope]`.

### 9. Derived rows

Chunks, postings, vectors, links and versions carry no grant of their
own; every derived read joins back through the entry table's
predicate. `owner_id` on chunks stays as a denormalised copy for the
existing owner-scoped paths and is otherwise unused by the spine.

### 10. The system actor

`Authority.system()` skips the resolver: no predicate, no point check,
every version row stamped `provenance = system`. A `strict` mode that
*errors* when a grant would have filtered is a follow-up for backups
(ADR 062 rule 4); this spec ships the bypass only.

### 11. Budgets and refusals

Two new kinds under `budget_exhausted`: `vfs.budget_exhausted.authority`
for an oversize subject set or a group walk deeper than
`MAX_GROUP_DEPTH`. The prefix cap never refuses; it falls back.

## Non-goals

- Narrowing, `pending`, the ask ledger (148); the edge (149).
- An `execute` level (open-questions: parked until a consumer asks).
- Share links and capability tokens (a future spec).
- Native RLS as a second layer (rejected in ADR 067; may return per
  engine as a follow-up).
- Sensitivity labels and expiry on grants (enterprise follow-ups; the
  row shape leaves room: `expires_at` is one nullable column away).

## Acceptance criteria

- The resolver and compiler are pure functions under `storage/` with
  unit tests for: owner floor; maximum-level resolution; the covering
  set; the meet for sets of 1, 2, 5, 20 (S1's shapes); the fallback
  past `MAX_PREFIX_ARMS`; LIKE escaping of `%` and `_`; bind counts
  under every dialect profile at a 10k batch.
- Every read builder applies the predicate before any content
  function, pinned per verb by a test that plants a hidden row whose
  content would match and asserts it never appears, never changes a
  count, and never changes a visible row's score.
- Every mutating verb: hidden target answers `not_found`; visible
  unwritable target answers `permission_denied`; a mixed 10k batch
  fails whole with no statement issued (asserted on the recorder
  storage); `move` out of a granted prefix hides the rows from the
  prefix-only holder.
- Edges: hidden endpoint hides the edge; `mkedge` gate as decided.
- `glean`: S2's regression (visible score identical with and without
  a hidden partition) on SQLite and one server engine; `lexical_stats`
  export contains no hidden-only term.
- Grant verbs: attenuation (cannot grant above one's own level), gate,
  revision bump, `granted_by = actor`; a widened grant is seen by an
  open session on its next call (ADR 063 rule 2).
- The pjdfstest-shaped conformance suite: one test module per verb,
  enumerating `(authority shape, row state, verb) → kind` triples, run
  on `InMemoryStorage` (accept-and-ignore is **not** conformant here:
  `InMemoryStorage` implements the resolver too, or the suite marks it
  unsupported) and on every engine leg.
- Performance gate: S1's `probe.py` run against the shipped resolver
  and compiler on Postgres stays within 1.5x of the study's literal
  form for the grep pass and the 1,000-id join-back.
- `scripts/ci.sh 3.13` green; all four engine legs green.

## Slices

| Slice | Content | Lands green? |
|---|---|---|
| A | tables (`grants`, `memberships`, revision, `versions.grant_revision`), schema version bump, migrations note; the resolver and compiler, pure, unit-tested against S1's shapes | yes |
| B | reads: every read builder takes the predicate; hidden = not-found; the per-verb hidden-row tests | yes |
| C | writes: the point check, batch gate, refusal mapping, `move`/`copy`/`restore`/`sweep`/edges | yes |
| D | `glean` statistics and the `lexical_stats` export over the visible set; S2 regression | yes |
| E | grant verbs and memberships admin; attenuation; the widening-seen-next-call test | yes |
| F | the conformance suite and the S1 performance gate | yes |

## Open questions

- Group administration (§8, marked). Everything else the seed left
  open is decided: NULL owner (ADR 064), additive-only (ADR 021/067),
  groups (ADR 067), edges (§5, §6), derived rows (§9), ranked join-back
  (§5, §7), RLS (rejected), move (§6), 009 (subsumed).
