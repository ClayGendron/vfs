# 058 — Row-level grants: the enforcement spine

- **Status:** **in progress 2026-09-28** — the storage half is built
  and the existing suite passes on it; the router surface, the tests,
  and the context records are outstanding. See *Implementation
  progress* at the end of this spec for what is done and what is left.
- **Earlier status:** shaped — **written in full 2026-09-06 against ADR 067**
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
- **Decisions it implements:** ADR 068 (posture; the anonymous
  principal; the mount-side `unauthenticated`), ADR 067 (the spine), ADR 065 (hidden
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

### 0. Posture: the everyone level (ADR 068)

- **A mount has a posture**, `open | shared | private`, stored as a
  row in the grants table under the reserved principal id `*` at
  `path_prefix = "/"`: `open` = `("*", "/", "read_write")`, `shared` =
  `("*", "/", "read")`, `private` = no `*` row at `/`. **The default is
  `open`**: first touch plants the row unless the storage was
  constructed with `posture="shared"` or `posture="private"`.
  `mounts()` and `grants("/")` show it.
- **Posture applies per directory, deepest prefix wins.** `posture(path,
  level, *, authority)` writes or replaces the `*` row at *path*
  (`private` writes a `*` row at level `none`). The everyone level on a
  path is the level of the deepest covering `*` row. Principal and
  group grants stay additive and max-resolved on top (§2); the `*`
  rows are the one longest-prefix ladder on the grant side, because
  they are the only rows that can *narrow*. The verb needs
  `read_write` on *path* for every subject, like `grant`.
- **The anonymous principal** (`Authority.anonymous()`, 070 as
  amended) holds only the everyone level: the resolver reads `*` rows
  for it and nothing else, and it owns nothing (`owner_id` NULL).
  Every other authority holds the everyone level too — the resolver
  includes the `*` rows in every subject's read.
- **A non-open posture refuses anonymous as `unauthenticated`**: when
  the authority is anonymous and the mount's root `*` row is below
  `read_write` (for a write) or absent (for a read), the verb answers
  `vfs.unauthenticated` with the hint "open a session, or configure
  default_authority" — the 401 lives at the mount, not the router.
  Below the root, a nested `private` prefix simply hides its rows from
  anonymous like any other invisible row.
- **Compilation.** The `*` rows compile beside the grant arms: each
  covering `open`/`shared` prefix at the required level is a `LIKE`
  arm, and each deeper `*` row that lowers the level is a `NOT LIKE`
  arm attached to it (`path LIKE :p || '/%' AND NOT path LIKE :q ||
  '/%'`). Both arm kinds count against `MAX_PREFIX_ARMS`.

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
- **The reserved principal id `*`** is the posture row (§0); it is
  never a `sub` (070 reserves it beside `system` and `anon`).
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
  unit tests for: the posture ladder (open root with a private child;
  shared root with an open child; anonymous holds only `*` rows); owner floor; maximum-level resolution; the covering
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
| A | tables (`grants`, `memberships`, revision, `versions.grant_revision`), the posture row on first touch (default `open`), schema version bump, migrations note; the resolver and compiler, pure, unit-tested against S1's shapes and the posture ladder | yes |
| B | reads: every read builder takes the predicate; hidden = not-found; the per-verb hidden-row tests | yes |
| C | writes: the point check, batch gate, refusal mapping, `move`/`copy`/`restore`/`sweep`/edges | yes |
| D | `glean` statistics and the `lexical_stats` export over the visible set; S2 regression | yes |
| E | grant verbs, `posture`, and memberships admin; attenuation; the widening-seen-next-call test; the mount-side `unauthenticated` for anonymous | yes |
| F | the conformance suite and the S1 performance gate | yes |

## Open questions

- Group administration (§8, marked). Everything else the seed left
  open is decided: NULL owner (ADR 064), additive-only (ADR 021/067),
  groups (ADR 067), edges (§5, §6), derived rows (§9), ranked join-back
  (§5, §7), RLS (rejected), move (§6), 009 (subsumed).

## Implementation progress (2026-09-28)

Work paused mid-landing at Clay's request. Nothing below is on
`main` yet except what the commit carrying this section contains.

### Decisions taken before building (Clay, 2026-09-28)

Three questions were researched and ruled before any code:

- **Q1 — can a caller see the folders above its grant?** Option
  **(b′)**: a directory is *on the road* when a row the caller can see
  lies beneath it. A road directory shows as a bare name (path and
  kind only — no version, time, size, owner or child count), lists
  only its visible or road children, answers `wrong_kind` to `read`,
  and refuses every write beneath it as `permission_denied`, decided
  on the directory before the target name is looked up. The road is
  computed from rows that exist, never from grant prefixes. Memo:
  `../../../research/2026-09-28-traverse-visibility-unix-plan9.md`.
- **Q2 — groups.** Clay's case (max within each person, min across
  the people acting together) is in scope and already this spec's
  §2–§3. Accepted with the memo's fixes: owner arms per member (not
  "set of one" only); `MAX_PREFIX_ARMS` bounded by expression depth as
  well as binds; the root prefix compiles to "true", not `LIKE '//%'`;
  posture holes cut every covering everyone arm, not the nearest;
  group ids are `group:<name>`; membership comes from the
  `memberships` table only (the token's `groups` claim is ignored);
  `add_member`/`remove_member` are system-actor only in this landing
  (the `/_groups/<id>` lean is dropped — under the default open
  posture it made everyone a group admin); nesting capped at 8,
  cycles and over-depth refused at write under the revision row's
  lock. Memo: `../../../research/2026-09-28-group-permissions-max-within-min-across.md`.
- **Q3 — search statistics.** ADR 065 rule 5 stands as ratified. A
  caller whose rights cover the whole mount uses the stored
  statistics (the fast path; the default open posture); every other
  caller gets exact visible-set statistics; stored block bounds are
  rescaled (`max_weight × idf_v/idf_g × max(1, avg_dl_v/avg_dl_g)`).
  Path-ordered lexical ids (the memo's option e) are deferred to their
  own ADR. Memo: `../../../research/2026-09-28-search-statistics-under-permissions-precedent.md`;
  the executed planted-ladder attack is
  `../../../research/studies/2026-09-28-search-statistics-precedent/planted_ladder_demo.py`.
- **The wide-predicate fallback (changes §3 step 4 and ADR 067 rule
  6).** Not the correlated `EXISTS`, and not the staged
  resolved-prefixes table the Q2 memo proposed: a predicate too wide
  for one statement splits into clauses the way glob's pattern fan
  does (each inside the dialect's bind and depth budgets), the
  statement runs once per clause, and results merge — exact for a
  `LIMIT` too, since every row of the global top k is admitted by some
  clause and ranks at least as high within it. `Rights.admits` in
  Python is the authority every row passes; SQL clauses are pushdowns.
  No new table, and reads never write.

### Built (uncommitted before this commit)

- `src/vfs/storage/grants.py` — the pure half: `GrantLevel`,
  `Posture`, `GrantRow`, `Arm`, `OwnerArm`, `Rights` (`admits`,
  `covers`, `covers_subtree`, `roots`), `minimise`, `meet`,
  `meet_all`, and `resolve` (per-member union, the meet, everyone arms
  with every lower row as a hole, per-member owner arms).
- `src/vfs/storage/backends/database/rights.py` — the storage half:
  `read_revision`, `RightsCache` (LRU keyed by subjects and grant
  revision), `resolve_authority` (closure walk one statement per
  nesting level, refused past `MAX_GROUP_DEPTH`; the system actor
  skips it), `posture_refusal` (anonymous → `unauthenticated`),
  `visibility_clauses` (the chunked fan), `Visibility` (`admits`,
  `road`, `seen_kinds`), `WriteGate` (`targets` in modes
  modify/upsert/create/read, `subtrees`, `row`, `creatable`), and the
  grant verbs' bodies (`grant_rows`, `revoke_rows`, `list_grants`,
  `set_posture`, `add_member_rows`, `remove_member_rows`,
  `bump_revision`, `posture_row`).
- Schema format **14** (`models/rows.py`): `grants` (surrogate key,
  unique `(principal_id, path_prefix)`), `memberships` (key
  `(principal_id, group_id)`, reverse index on `group_id`,
  `granted_by`/`granted_at`), `meta.grant_revision`,
  `versions.grant_revision`; `Version.grant_revision` on the model and
  `Version.create`. First touch plants the posture row
  (`EngineHost(posture=...)`, default `open`).
- `VFSErrorKind.authority_budget` (`vfs.budget_exhausted.authority`)
  with its contract row.
- `DatabaseStorage(posture=...)`; every read verb resolves a view in
  its own transaction (`_viewed`; `None` on the whole-mount fast
  path); `read`/`stat`/`ls`/`tree`/`glob` filter and show road
  directories (`reads.py`: `_screen`, `road_observation`,
  `_visible_rows`); `grep` passes the view beside its structural gates
  before any body is fetched; `glean` computes the visible lexicon
  (`_visible_lexicon`, `_visible_corpus`, `_all_blocks`,
  `_visible_chunks`), scores only visible chunks with rebounded blocks,
  runs the vector leg once per clause (`_nearest` merge), filters the
  overlay, and exports visible statistics only.
- Mutations: `write` (upsert), `edit` (modify), `mkdir` (create),
  `mkedge` (source modify, target read), `rmedge` (source modify) gate
  before the first write; `delete`, `sweep`, `move`, `copy` gate right
  after the serialization point (`topology.py` gained `gate=`); subtree
  mutations check every row beneath (`WriteGate.subtrees` — closes the
  owner-floor-on-a-directory hole the spec's prefix-only rule left);
  `restore` judges each resolved trash row and its destination
  (`permit=`, `owner_id` added to the restore columns).
- `DatabaseStorage.grant/revoke/posture/grants/add_member/remove_member`.
- `owner_id` rides every candidate fetch (`scope.FETCH_RIDE`).
- A direct storage call naming no authority runs as the system actor
  for rights (trusted in-process code); ownership stamping is
  unchanged.

State at the pause: `ruff check`, `ruff format` and `ty check src`
clean; the full suite passed (3,353 passed, 967 skipped) after the
storage wiring, with `tests/models/test_rows.py` updated for the two
new tables. Everything default-open takes the fast path, so the suite
exercises no partial view yet. `scripts/ci.sh` was **not** run.

### Outstanding

**1. Router surface.**
- `ops.py`: add `grant`, `revoke`, `grants`, `posture`, `add_member`,
  `remove_member` to `Op`; a new class `GRANT_OPS`, its writing subset
  `GRANT_WRITE_OPS`, and `WRITE_GATED_OPS = MUTATING_OPS |
  GRANT_WRITE_OPS`; `ALL_OPS` gains `GRANT_OPS`; `posture`,
  `add_member`, `remove_member` join `DEVELOPER_OPS` (never on an agent
  surface).
- `permissions.check_writable_composed` keys on `WRITE_GATED_OPS`, so
  a read-only mount refuses grant writes.
- `storage/protocol.py`: a `SupportsGrants` family and its
  `_FAMILY_OPS` row.
- `base.py`: the six public verbs (path-routed; the membership verbs
  take the mount's path), their arms in `_call_storage`, and gating.
- `session.py`: the agent-facing ones (`grant`, `revoke`, `grants`).
- `params.py` table rows; `results/projection.py` defaults for the
  new ops (their answers ride as `grants=` / `members=` extras).
- `authority.py`: `Principal` refuses a `sub` starting `group:` and the
  reserved `*`.
- `locate(exists=True)` / `locate_edge` probe storage as the system
  actor today, which leaks existence: probe under the caller's
  authority instead.
- Pins to update: `tests/test_ops.py` (vocabulary, the permission
  set's identity, developer plane, router surface), `tests/test_params.py`,
  `tests/storage/test_protocol.py`, `tests/base/test_dispatch.py`,
  `tests/base/test_gates.py`.

**2. Tests** (none written yet for partial views).
- The resolver oracle: port `studies/2026-09-28-group-permissions/model.py`'s
  pointwise oracle into `tests/support/oracles/` and pin
  `grants.resolve` and `Rights.admits` against it on random worlds, and
  the compiled clauses on SQLite.
- Per read verb: a hidden row whose content would match never
  appears, never changes a count, never moves a visible score; road
  directories show as path and kind only; a hidden ancestor misses
  exactly as a missing one.
- Write gate: hidden → `not_found`, visible-unwritable →
  `permission_denied`, a write under a road-only directory refused
  before lookup, `parents=True` over a hidden ancestor, a mixed 10k
  batch fails whole with no write statement, subtree mutations,
  restore.
- Posture: the everyone ladder, nested private/shared, anonymous →
  `unauthenticated` on shared (write) and private (read and write).
- Grant verbs: gate, attenuation, revision bump, `granted_by`, a
  widened grant seen on the next call; memberships: system-only,
  cycle and depth refusals, per-member (never pooled) groups.
- `glean`: the S2 regression — the planted-ladder demo as a test (a
  visible score identical with and without a hidden partition), the
  export carries no hidden-only term, the vector leg per clause.
- A conformance mixin across every engine leg (pjdfstest-shaped
  `(authority shape, row state, verb) → kind` triples).
- 100% coverage on the new modules.

**3. Real engines.** Run the four legs (`db_test`): the owner-road
query uses a correlated byte range with `concat` on an aliased
column, not yet executed off SQLite; the new tables' DDL on every
engine; S1's `probe.py` against the shipped resolver on Postgres as
the performance gate.

**4. Context records.**
- An ADR for road visibility (Q1).
- An ADR amending 067 rule 6 (the chunked fan replaces the `EXISTS`
  fallback) and recording the group rules (Q2).
- This spec's body brought in line with the decisions above (the seven
  Q2 tightenings, §3 step 4, §8's marker closed, §5's road rules, §7's
  fast path and bound rescale).
- `open-questions.md` entries: path-ordered lexical ids (the flat-cost
  visible `df`); stored ranking signals leak hidden in-links
  (unstudied, off by default); trash rows under a non-open posture
  are visible only to their owner or a whole-mount caller, so a
  granted non-owner cannot restore what it deleted; grep's candidate
  budget counts hidden candidates; rows deleted since an index build
  still count in the stored statistics until reindex.
- A STATUS entry on landing; reference docs for the grant verbs.

**5. Known limitations to state in docstrings or records.**
- A partial caller's `glean` reads every block of every query term —
  cost grows with the terms' corpus-wide document frequency (said in
  `_visible_lexicon`'s docstring).
- `list_grants` gates on prefix coverage, not on visible rows.
- A `posture=` passed to an already-provisioned mount is ignored; the
  stored posture wins.
