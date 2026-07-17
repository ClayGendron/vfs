# 006. One Global Namespace: Tenant Isolation Is a Permission Layer, Not a Path Prefix

- **Status:** accepted
- **Date:** 2026-07-16 (decided 2026-06 in story 032's handoff, executed
  2026-06-06 in commit 7d8d86f; this record promotes it out of the
  archived story)
- **Deciders:** Clay Gendron
- **Decided by:** human

## Context

The pre-refactor multi-tenant scheme scoped storage by **path prefix**:
every canonical path was rewritten to `/{user_id}/...` on its way into
the backend (`scope_path`) and stripped on the way out (`unscope_path`).
Story 032's resolution-chokepoint audit found the scheme was a
per-call-site convention, not a funnel: `_scope_path` was hand-called at
the top of ~15 backend methods, and at least four sites hand-encoded the
`/{user_id}` layout directly into LIKE patterns and glob prefixes
(`032-unified-path-resolution-chokepoint/design.md §1`). Worse, the
scoped form leaked into the layering question itself: scoping is
*storage layout policy* — a pure router has no rows to scope, and baking
one tenant layout into the routing layer would force it onto every
mount and double-scope with the backend.

Meanwhile permission rules checked in unscoped coordinates could be
gamed across the scope boundary (the `permissions.py` docstring's
`/wiki/alice/synthesis` example), because the rule language and the
storage layout disagreed about what a path meant.

## Options considered

- **Keep path-prefix scoping in the backend** — smallest change; keeps
  the per-call-site convention, the double-encoding hazard, and the
  rule/layout mismatch; every new backend re-implements the layout.
- **Scope at the router chokepoint** — one funnel, but forces a single
  tenant layout onto every mount (a remote or union mount may scope
  differently or not at all) and still leaves two path forms alive.
- **Permission layer over one global namespace** (chosen) — the Unix
  model: there is one tree; an implementer who wants per-user areas
  makes `/users/{name}` and grants that principal access to that
  subtree. Isolation is authorization, not path rewriting.

## Decision

The `/{user_id}` path-prefix scheme is dropped. There is **one global
namespace** with **one canonical path form**; tenant isolation is a
permission layer over subtrees of that namespace.

- `scope_path` / `unscope_path` / `validate_user_id` are deleted; no
  `ScopedPath` form exists. Verified live: `src/vfs/paths.py` contains
  none of them — paths have exactly one canonical form, minted at the
  `resolve_path` gate.
- The principal survives as data, not as namespace: every routed verb
  and every storage-protocol method threads `user_id: str | None` —
  "local caller identity; never on the wire"
  (`src/vfs/params.py:80`, `src/vfs/base.py`,
  `src/vfs/storage/protocol.py`) — for attribution and future
  principal-aware authorization, never for path rewriting.
- Authorization lives in `src/vfs/permissions.py`: per-mount
  `PermissionMap` layers (default plus prefix overrides) composed along
  the mount path, most-restrictive-wins — the Linux
  `MNT_READONLY || SB_RDONLY` shape. Rules are written in
  mount-relative coordinates against real paths, so the rule language
  and the namespace can no longer disagree. Per-principal policy
  (shares/ReBAC) is a designed extension point on the same global
  namespace, not a return of scoping.

**Scope note:** story 032 bundled a second design — a typed path handle
(`VFSPath`). That half is deliberately *not* part of this record: it is
its own concern and took its own course (it landed and was later
renamed to the live `Path` gate type, `src/vfs/paths.py:169`). This ADR
binds only the namespace/tenancy half.

## Consequences

- **Easier:** one path form end-to-end — no scope/unscope seams for a
  backend to miss, no hand-encoded `/{user_id}/%` LIKE patterns;
  permission rules mean what they say because they name real paths;
  mounts compose freely (nothing forces a tenant layout on a mount);
  multi-tenancy becomes an *implementer pattern* (`/users/{name}` +
  a grant) rather than engine machinery.
- **Harder:** isolation is only as strong as the permission layer —
  permission-filtered *enumeration* (ls/glob/grep that hide unreadable
  subtrees per principal) must eventually be pushed into backends;
  until per-principal grants exist, `PermissionMap` is path-policy
  only, and hard isolation requires separate engines/tables (the
  documented block-device analogy in `permissions.py`).
- **Committed to:** no path-prefix tenancy, ever — a backend that
  rewrites caller paths by principal is out of spec; principal-aware
  authorization builds on `user_id` + the permission layer over the one
  global tree.

Decided in story 032
(`context/specs/archive/032-unified-path-resolution-chokepoint/HANDOFF.md`,
Decision 1); the reference-system survey behind "authorization is
separate from name handling" (Linux, Plan 9, FreeBSD, fsspec) is in the
same folder's `vfspath-typed-handle.md §2, §8`.
