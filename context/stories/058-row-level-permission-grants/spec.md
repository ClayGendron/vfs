# 058 — Row-level permission grants

- **Status:** seed — intent and research pointers only; full spec to be
  written by team. `[NEEDS CLARIFICATION]` markers are unresolved design
  forks, not omissions.
- **Date:** 2026-07-08
- **Owner:** Clay Gendron
- **Kind:** feature (authorization layer — row-space permissions on the
  entry table)
- **Depends on:** 056 storage mounts (one table, one funnel), existing
  `src/vfs/permissions.py` (`PermissionMap`), `VFSEntry.owner_id`
  (already present and indexed in `src/vfs/models.py`)
- **Prior art:** story `009-cloud-style-sharing-and-access-control`
  (April draft, pre-056 — overlaps heavily on sharing semantics and
  cloud-model research; must be reconciled or superseded by this story)

## Intent

VFS has two access-control mechanisms today, both in **path-space**:
mount-wide `PermissionMap` (developer config, applies to every caller
identically) and `user_scoped=True` path rewriting (isolation, not
sharing). Neither can express: *"Bob can read `/projects`, Carol can
read and write `/projects/roadmap.md`, Dave cannot see either exists."*

This story adds **row-space permissions**: the same query, run as
different principals, returns different rows — enforced in the SQL
itself, never by post-filtering.

The target mental model (worked out in design discussion, 2026-07-08):

- **Ownership is a column, sharing is a relation.** `owner_id` stays the
  one-to-one case; per-principal sharing lives in a grants table —
  `(principal_id, path_prefix, level)` — because permission between a
  person and a file is a relation, not a row property.
- **Levels form a ladder:** `(invisible) < read < read_write`. Every
  check is "resolve the caller's level on this path, compare to what the
  op needs." Owner is an implicit `read_write` grant.
- **Reads filter sets, writes check points.** Read ops compile
  visibility into a predicate on every SELECT (owner OR shared OR a
  covering grant), applied at a single query-construction chokepoint —
  the query-side analogue of 056's dispatch funnel. Mutations do a
  point check (ancestor-prefix chain lookup, longest prefix wins — same
  algorithm as `PermissionMap._resolve`) and reject with a structured
  error.
- **Grants attach to the namespace, not the rows.** A grant on
  `/projects` covers rows created under it tomorrow with zero
  maintenance; coverage is computed at query time from the path string
  (`path = prefix OR path LIKE prefix || '/%'`). No tree traversal, no
  recursive CTEs: walking up is a prefix chain computed in app code,
  walking down is one indexed LIKE range scan.
- **Lean additive-only:** grants only widen access; level may vary by
  depth but visibility is never denied by a deeper grant. This keeps the
  read predicate a bare EXISTS and confines longest-prefix resolution to
  the cheap write-time point check.

Non-goals: identity/authentication (who the caller is remains an input,
threaded as `user_id` through `_call_storage` already), share links and
capability tokens (009 territory), cross-VFS federation.

## Research resources

Nine reference repos are cloned locally as shallow clones under
`~/Git/Repos/` (siblings of this repo), chosen for which part of the
design each informs:

| Local clone | Upstream | What to study |
| --- | --- | --- |
| `storage/` | supabase/storage | **Closest overall match** — an `objects` table of path-keyed file rows with Postgres RLS enforcement. `migrations/` for schema + policies; the `search`/`list_objects` SQL functions for index-friendly listing under RLS. |
| `openfga/` | openfga/openfga | Zanzibar-style grants-as-relations; its canonical tutorial is Google Drive folder inheritance. Store schema (tuple table) = grants table in relational form. |
| `spicedb/` | authzed/spicedb | The other flagship Zanzibar. "check" vs "lookup-resources" maps exactly onto the point-check / set-filter asymmetry above. |
| `minio/` | minio/minio | S3 IAM prefix-matching policy evaluation — battle-tested edge cases for `prefix/*` semantics (boundary chars, wildcard interaction). |
| `django-guardian/` | django-guardian/django-guardian | Per-object grants in a Python ORM; `get_objects_for_user()` compiles grants into queryset filters. Reference for API ergonomics, not matching logic. |
| `oso/` | osohq/oso | Deprecated as a product, but the `sqlalchemy-oso` data-filtering adapter is the best design reading on compiling policy into SQLAlchemy predicates (never post-filter). |
| `jackrabbit-oak/` | apache/jackrabbit-oak | Hierarchical per-node ACLs done exhaustively, including allow *and deny*. Consult for edge cases (move semantics, admin bypass); also the cautionary tale for the subtractive model. |
| `gitlabhq/` | gitlabhq/gitlabhq | `traversal_ids` — materialized ancestor arrays with GIN indexes; the alternative encoding of "ancestry on the row." Also DeclarativePolicy for membership-with-inheritance at scale. |
| `casbin/` | apache/casbin | Embedded policy engine (no service — matches VFS's library architecture) with `keyMatch` path-pattern functions. |

Suggested reading order: `storage/` (validates the architecture),
OpenFGA's Drive tutorial (pressure-tests the grants semantics),
`minio/` prefix matcher (string edge cases). Oak and GitLab are
encyclopedias to consult per-question, not front-to-back reads.

## Open questions for the full spec

- `[NEEDS CLARIFICATION]` Reconcile with 009: does 058 subsume 009's
  grants layer, with 009 narrowing to share links/tokens on top? 009
  also predates 056 — its enforcement points no longer exist as written.
- `[NEEDS CLARIFICATION]` NULL-owner semantics: shared rows readable by
  all — but writable by whom? (Lean: read-only to scoped callers;
  restriction tightens, never loosens.)
- `[NEEDS CLARIFICATION]` Additive-only confirmed, or is a deny/`none`
  level required? (Everything above assumes additive-only; a deny level
  forces longest-prefix resolution into every read predicate.)
- `[NEEDS CLARIFICATION]` Groups: `principal_id` as user-only at first,
  or ship the `memberships(user, group)` indirection in v1?
- `[NEEDS CLARIFICATION]` Edge rows: visible iff both endpoints visible,
  or stamped with creator's owner at mkedge time? (Discussion leaned:
  enforce both-endpoints at creation, stamp for single-table reads.)
- `[NEEDS CLARIFICATION]` Derived-row invariant: chunks already inherit
  `owner_id`; version rows do not — audit every row-creation site.
- `[NEEDS CLARIFICATION]` Ranked-search enforcement: gram posting lists
  store bare doc_ids — the visibility predicate must apply at the
  entry-table join-back, before scoring/LIMIT. Same question for
  pgvector ANN (pre-filter recall tradeoff).
- `[NEEDS CLARIFICATION]` Postgres RLS as defense-in-depth over the
  app-level predicates (portable baseline stays app-level for
  SQLite/MSSQL/Databricks)? If yes: `SET LOCAL` identity plumbing
  through the async session layer.
- `[NEEDS CLARIFICATION]` `move`/`copy` semantics under grants: move is
  a permission event (subtree entry/exit changes visibility silently) —
  desired, but must be a decision, not a surprise.
