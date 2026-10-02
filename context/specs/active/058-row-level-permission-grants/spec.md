# 058 — Row-level grants: the enforcement spine

- **Status:** **built 2026-09-29, awaiting Clay's review** — the
  storage half, the router surface, the tests, the real-engine legs,
  the performance gate and the records are done; `scripts/ci.sh` has
  not been run. See *Implementation progress* at the end of this spec.
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
  arm, and **every** deeper `*` row that lowers the level beneath it is
  a hole attached to it (`path LIKE :p || '/%' AND NOT path LIKE :q ||
  '/%'`), not only the nearest (ADR 071 rule 6). The root prefix
  compiles to "true", never `LIKE '//%'` (ADR 071 rule 5). Both arm
  kinds count against the clause budget (§4).

### 1. The rows

- **`grants(principal_id, path_prefix, level, granted_by, granted_at,
  revision)`.** Additive-only: a row states a positive fact and there
  is no deny row. `principal_id` is a `sub` (070) or a group id.
  `path_prefix` is a canonical vfs path in **mount-relative
  coordinates** (as `PermissionMap` rules are), stored in the same
  bytewise collation as `entries.path`; `/` means the whole mount.
  `level ∈ {read, read_write}`; *invisible* is the absence of any
  covering row. Unique `(principal_id, path_prefix)`.
- **Group ids are `group:<name>`** in the same `principal_id` column
  (ADR 071 rule 7); `Principal` refuses a `sub` with that prefix.
- **`memberships(principal_id, group_id, granted_by, granted_at)`**,
  resolved per statement (ADR 067 rule 3) from this table only; a
  token's `groups` claim is ignored for rights. Nested groups are
  walked in app code to `MAX_GROUP_DEPTH = 8`; a deeper nesting or a
  cycle is refused at membership write, under the lock the revision
  bump takes, and never silently truncated at read.
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

1. Walk each subject's group closure, **per subject, never pooled**
   (ADR 071 rule 3): one chunked statement per nesting level. Then read
   the rows of every subject, every closure group and `*` in one
   chunked `IN`. Memoised per `(subjects, grant_revision)`.
2. Per subject, compute the **covering prefix set** at the required
   level: the minimal set of prefixes (a longer prefix under a
   qualifying shorter one is dropped).
3. For a set, compute the **meet**: the intersection of the members'
   covering sets, where "intersection" of prefix sets is the set of
   longest common coverage (a prefix `p` survives iff every member has
   a covering prefix that is `p` or an ancestor of `p`; the result is
   the deepest such `p`s). S1 measured this shrinking the arm count as
   the set grows.
4. Emit `Rights(level, arms, owner_arms, whole)`: the everyone arms
   (each with its holes) plus the meet's prefixes, and **one owner arm
   per member** (ADR 071 rule 4): rows that member owns, under the
   meet of the *other* members' coverage, trimmed of what the shared
   arms already cover. `whole` is set when an arm covers the root with
   no hole: the caller sees everything, and every filter is skipped.
   `Rights.admits(path, owner_id)` is the same decision in Python and
   the authority every row passes.

`MAX_SUBJECTS` is 070's.

### 4. The compiler (app code, one function)

`visibility_clauses(entry, rights) -> list[Clause] | None`: each arm
and owner arm becomes a unit (`path = :p OR path LIKE :p_esc || '/%'`,
minus its holes; `owner_id = :o AND (...)`), and the units pack into
OR-clauses, each spending at most half the membership budget and
holding at most `arm_budget` units (ADR 071 rule 1, the glob fan's
budget). A caller's statement runs once per clause and the results
merge by path; for a top-k the merge stays exact. `None` means the
whole mount. The same function serves every read builder. These
clauses are pushdowns: every fetched row still passes `Rights.admits`.

### 5. Reads filter

Every read applies `visible(rights_at(read))` inside the query, before
any content function (ADR 065 rule 4): `read`, `stat`, `ls`, `tree`,
`glob`, `grep` (the regex runs only on admitted rows; the visibility
check runs beside the structural gates before any body is fetched), `glean`
(the candidate query carries the predicate before scoring and `LIMIT`;
the vector leg's distance is computed only on admitted rows), `graph`
and the edge reads (an edge is visible iff **both** endpoints are
visible), `locate` (table facts only; hidden answers not-found),
`versions`, and the memory entry's `ls` of mount points (mount points
are structure and always visible). A hidden row is `not_found`, with
the same payload as an unknown path.

**The road** (ADR 070). A hidden directory with a visible row beneath
it is *on the road*: it shows in `ls`, `glob` and `tree` with path and
kind only, `stat` answers those two fields, `read` answers `wrong_kind`,
and listing it shows only its visible and road children. The road is
computed from rows that exist: the arm roots that exist, and for owned
rows a bounded byte-range probe beneath each candidate directory. A
hidden directory with nothing visible beneath stays absent. `locate`
with `exists` probes under the caller's authority, so it answers what
`stat` would.

### 6. Writes check

Every mutating verb resolves at `read_write` and checks each target
path's longest matching arm in app code (ADR 067 rule 4); a batch of
10k paths is one resolver call and no per-path statement. The batch
**fails whole at the gate** before the first statement. Refusal kinds:
a target the authority cannot *see* answers `not_found` (ADR 065 rule
2); a visible target it may not write answers `permission_denied`;
a target beneath a road directory answers `permission_denied`, decided
on the directory before the name is looked up (ADR 070 rule 4);
structure's read-only answers `read_only` as today. A creation is
judged by whether an arm covers the new path. A subtree mutation
(`delete`, `move`, `sweep` of a directory) checks every row beneath
the target, not only the prefix, since an owner-floor row or a
posture hole can sit inside a writable directory. A write that would
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

A caller whose rights cover the whole mount (`Rights.whole`, the
default open posture) uses the stored statistics: the fast path. Every
other caller gets exact visible-set statistics: `N` and `avg_dl` over
the rows `Rights.admits` passes, and per-term `df` over the visible
chunks. Stored block bounds are rescaled for the visible corpus
(`max_weight × idf_v/idf_g × max(1, avg_dl_v/avg_dl_g)`) so block
skipping stays safe. Scoring runs only on visible chunks; the vector
leg runs once per clause and merges. The mount's `lexical_stats` export to the
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
- `posture(path, posture, *, authority)`: writes the `*` row (§0).
- Memberships are administered through `add_member(group, member, *,
  path)` / `remove_member(...)` by **the system actor only** in this
  landing (ADR 071 rule 8); *path* only picks the mount. A per-group
  admin flag is a follow-up. The `/_groups/<id>` lean is dropped: under
  the default open posture it made everyone a group admin.
- `posture`, `add_member` and `remove_member` are developer-plane
  verbs, never on an agent surface. Answers ride as `grants=` and
  `members=` rows, not observations; the router rebases each row's
  `path_prefix` to router coordinates.

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
`MAX_GROUP_DEPTH`. A wide rights set never refuses; it fans (§4).

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
  set; the meet for sets of 1, 2, 5, 20 (S1's shapes); the clause
  fan past one statement's budget; LIKE escaping of `%` and `_`; bind counts
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

- None. Group administration (§8) closed 2026-09-28 (ADR 071 rule 8).
  Everything else the seed left open is decided: NULL owner (ADR 064), additive-only (ADR 021/067),
  groups (ADR 067), edges (§5, §6), derived rows (§9), ranked join-back
  (§5, §7), RLS (rejected), move (§6), 009 (subsumed).

## Implementation progress (2026-09-28)

Paused 2026-09-28 after the storage half, resumed 2026-09-29.

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

### Built — the storage half (2026-09-28, commit `8ce8c72`)

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
  modify/upsert/create/read, `subtrees`, `row`), and the grant verbs'
  bodies (`grant_rows`, `revoke_rows`, `list_grants`, `set_posture`,
  `add_member_rows`, `remove_member_rows`, `bump_revision`,
  `posture_row`).
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
  its own transaction (`None` on the whole-mount fast path);
  `read`/`stat`/`ls`/`tree`/`glob` filter and show road directories;
  `grep` passes the view beside its structural gates before any body
  is fetched; `glean` computes the visible lexicon, scores only
  visible chunks with rebounded blocks, runs the vector leg once per
  clause, filters the overlay, and exports visible statistics only.
- Mutations gate before their first write (`write`, `edit`, `mkdir`,
  `mkedge`, `rmedge`) or right after the serialization point
  (`delete`, `sweep`, `move`, `copy`, `restore`; `topology.py`'s
  `gate=`). Subtree mutations check every row beneath the target.
- A direct storage call naming no authority runs as the system actor
  for rights (trusted in-process code); ownership stamping is
  unchanged.

### Built — the router surface, tests and records (2026-09-29)

- **Router surface.** `ops.py`: the six grant ops, `GRANT_OPS`,
  `GRANT_WRITE_OPS`, `WRITE_GATED_OPS`; `posture`, `add_member`,
  `remove_member` join `DEVELOPER_OPS`. `permissions.py` gates on
  `WRITE_GATED_OPS`, so a read-only mount refuses grant writes and
  still lists grants. `SupportsGrants` and its `_FAMILY_OPS` row.
  `VirtualFileSystem.grant/revoke/grants/posture/add_member/remove_member`
  route to the mount holding the path (`_route_grant`), with funnel
  arms, and rebase each answered `grants=` row's `path_prefix` to
  router coordinates. `Session` mirrors all six. `params.py` rows
  (`level` is `read | read_write`; `posture` is `open | shared |
  private`). Grant answers render as a table
  (`render._render_grant_rows`). `Principal` refuses `*` and a `sub`
  starting `group:`; the reserved names now come from `authority.py`
  (`EVERYONE_NAME`, `GROUP_NAME_PREFIX`). `locate(exists=True)` and
  `locate_edge` probe under the caller's authority.
- **Fixes the new tests found.**
  1. `mkdir(exist_ok=True)` on a road directory answered with its
     `version`. Now every gated verb aimed at a road directory itself
     is `permission_denied`.
  2. An owner could not restore a row it had deleted under a private
     posture: the destination was judged as a fresh creation. Now it
     is judged as the row that lands there, with the owner it already
     has (a restore never mints an owner). `WriteGate.creatable` is
     gone.
  3. Anonymous `restore` answered `not_found` for an address not in
     the trash and `unauthenticated` for one in it, which told an
     anonymous caller what the trash held. `restore_rows` gained
     `gate=`, run after the serialization point and before any trash
     lookup.
  4. The resolver kept an everyone arm that an ancestor arm already
     admitted in full (`_already` now compares holes).
- **Tests.** The resolver against a pointwise oracle
  (`tests/support/oracles/grants.py`) on 400 random worlds with nested
  groups, postures and owners (`tests/storage/test_grants.py`); the
  same worlds replayed through the verbs on SQLite, and the compiled
  clauses checked exactly at bind budgets 4, 9 and 2,099
  (`tests/storage/database/test_rights.py`); every partial read under
  a starved budget answers as unstarved; a 49-test conformance mixin (65 cases with the per-verb anonymous rows)
  (`tests/support/grants_contract.py`, wired into every
  `StorageContract` leg) covering hidden rows, the road, the owner
  floor, the subject-set meet, posture, anonymous on every verb, the
  write gate per verb, subtree checks (including past the first
  page), restore, sweep, edges, the grant and membership verbs, and
  glean's planted-ladder regression with a whole-mount control;
  router routing, rebasing, gating and rendering
  (`tests/base/test_grant_routing.py`). Every op-vocabulary pin moved.
- **Real engines.** The conformance file, grants included, passes on
  Postgres (270 tests), MariaDB, SQL Server and Oracle (836 tests
  across the three), the owner-road byte-range query included.
- **The performance gate** (`../../../research/studies/2026-09-29-shipped-predicate-gate/`):
  the shipped `resolve` + `visibility_clauses` against S1's
  `literal_like`, same corpus, same rows returned. Postgres 112k rows:
  grep 0.96x, join-back 0.89x. Postgres 995k rows: grep 1.03x,
  join-back 0.72x. SQLite 112k: grep 1.03x, join-back 0.86x. Gate
  1.5x: **pass**.
- **Records.** ADR 070 (road visibility), ADR 071 (the chunked fan
  and the group rules; amends 067 rule 6), 065 and 067 status lines,
  this spec's body, five `open-questions.md` entries, the how-to *Share
  a folder with grants* (executable), and the docs' status lines and
  glossary.

### Outstanding

- **Partial-access latency (2026-09-30).** `glean` for a caller with
  many grants measured about 440 ms at 100 grants and 2 s at 500 on
  50,000 files (`../../../research/studies/2026-09-29-partial-glean-latency/`):
  two statements tested every chunk against every OR'd arm. Four prior
  art memos (`../../../research/2026-09-30-*`) led to ADR 072 (rights
  as sorted path ranges, one bound value, joined to the path index;
  entries filtered before chunks). Validated 2026-10-01 on all five
  engines (`../../../research/studies/2026-10-01-range-join-engines/`)
  and built the same day (Clay: "go with your recommendations"):
  `Rights.ranges()` in `grants.py`, the `range_source` profile fact,
  `ranges.py`, and `Visibility.entries()` / `narrow()`, used by `tree`
  and the visible-corpus count. Oracle and unknown dialects keep the
  arm fan; the vector leg keeps it too until its count-gate ADR (Clay:
  "can we drop vector for right now?"). Still ruled in for later ADRs:
  the vector leg's count gate, path-ordered chunk numbers per lexical
  epoch, and a better Oracle spelling (a probe).

- `scripts/ci.sh` has not been run (Clay, 2026-09-28: no `ci.sh`
  before commit). Locally: `ruff check`, `ruff format --check` and
  `ty` clean on `src` and `tests`; the full suite green at 100%
  coverage; `pytest docs` green.
- The known limitations, stated in docstrings and records:
  - A partial caller's `glean` reads every block of every query term,
    so its cost grows with the terms' corpus-wide document frequency
    (`_visible_lexicon`; open question: path-ordered lexical ids).
  - `grants` judges visibility of *path* by arm coverage, not rows: a
    path reached only through the owner floor or as a road directory
    answers `not_found` (`list_grants`).
  - A `posture=` passed to an already-provisioned mount is ignored;
    the stored posture wins (`DatabaseStorage`).
  - Trash under a non-open posture, grep's candidate budget, stored
    ranking signals and stored statistics after deletes: see
    `open-questions.md`.
