# 056 — Plan

Approach: three passes, each independently landable and verified at
its own session end (pytest/ruff/ty once per session, per the working
agreement).

- **Pass A — protocol + router core.**  The big deletion: vocabulary,
  protocol members, backend/double updates, permissions re-plumb, and
  the base2 rebuild.  Everything else depends on this.
- **Pass B — the adapter.**  Router-as-storage; needs only Pass A.
- **Pass C — the MCP trio.**  Client backends and server wrapper;
  needs Pass A (protocol) and B (the server wrapper's composition
  story is adapter-shaped).  Brings the `mcp` dependency into
  pyproject.

055's outstanding test tasks (8–12) fold into Pass A's test work —
the mount/dispatch suites they targeted are reshaped by this story,
so porting them twice would be waste.

## Pass A

### 1. Errors and vocabulary (`vfs/results2.py`, `vfs/ops.py`)

Three new error kinds: `backend_unavailable` (dead transport, decision
12), `busy` (data-plane mutation at a bind site, decision 18),
`budget_exhausted` (hop/TTL exhaustion, decision 13; non-retryable).
A fan-out branch that fails with any of these merges as that scope's
classified failure while siblings succeed — the existing per-scope
merge shape, no new machinery.

### 2. Protocol (`vfs/storage.py`)

- `StorageBackend` gains three required members: `name: str`,
  `description: str`, `capabilities() -> frozenset[Op]`.  The read
  family remains the *verb* minimum.
- Delete `storage_ops()` (storage.py:300) — presence-sniffing dies
  with decision 2.
- New `TransportError` family (base class the funnel normalizes to
  `backend_unavailable`; wire backends raise it, in-process backends
  never do — "raw exception = backend bug" stays true for them).
- `SupportsClose` docstring gains the contract: idempotent,
  dead-peer-tolerant.
- Path-form contract for backend-returned paths stated on the
  protocol; the funnel normalizes and validates.

### 3. Backends and doubles

- `InMemoryStorage`: `name`/`description` constructor kwargs with
  sane defaults; `capabilities()` returns the full implemented set
  regardless of `allow_files` (capabilities speak ops, not per-kind
  guarantees, per 055).  Batched reads (`read`/`stat`/`ls` with
  observations) classify **per row** — good rows plus one classified
  error per failure, `success=False` when any failed; single-path
  keeps fail-whole, mutations stay batch-atomic.  (Landed: noted
  asymmetry to revisit — `mkdir(parents=True)` reports minted
  ancestors as rows, `write(parents=True)` mints silently.)
- `tests/base_doubles.py`: every double gains the three members;
  doubles that fake partial families declare exactly what they
  implement.

### 4. Permissions (`vfs/permissions.py`)

- `check_writable` (permissions.py:248) re-plumbed to take a
  `PermissionMap` + error context instead of a `VirtualFileSystem`.
- New composition helper: given the ordered entries from `/` to the
  terminal, gate against each entry's map in that entry's
  mount-relative coordinates; most restrictive wins (decision 3).
  The `/.vfs` alias rules keep firing because rel paths stay
  mount-relative.

### 5. Router rebuild (`vfs/base2.py`)

Ordered so the tree stays comprehensible mid-edit; it will not run
until step 5 completes (expected, per repo posture).

1. **Types:** `MountMeta` (permission_map, no_overlay, owned, cached
   capability snapshot); `Binding` → `(path, storage, meta)`;
   constructor builds the identity entry at `/` from its own storage.
2. **Deletions:** `_call_remote_op` + its static match, `_parent`,
   `_root`, `_reachable_ids`, `_commit_mount`'s cross-instance half,
   add_mount delegation, `allow_child_mounts`, recursive close
   bookkeeping, `_resolve_terminal`'s nesting loop, every fs-is-self
   branch.
3. **Resolve:** single longest-prefix match returning the entry;
   `ResolvedTerminal` keeps its `(binding, rel)` shape.
4. **One funnel:** `_call_storage` is the only dispatch; it
   normalizes `TransportError` → `backend_unavailable` and applies
   decoration at the rebase seam (mount rows get the entry storage's
   live `description`).
5. **Gates:** capabilities from the entry's bind-time snapshot;
   ancestor permission composition via the section-4 helper;
   `no_overlay` refusal for binds beneath a flagged entry.
6. **Entry-keyed dispatch at all five identity-keyed sites:**
   `_group_observations_by_terminal`, `_route_two_path` (cross-entry
   → `cross_mount`), `_route_entry_batch`, `mkedge`'s cross-mount
   check + delegation branch, `_route_fanout`'s grouping +
   region-expansion dedupe (two keyspaces collapse into one).
7. **Shadowing:** results through entry M drop rows at/under deeper
   bind paths before merging; `tree` descends deeper binds and
   subtracts their region; `ls` at a directory holding mount points
   unions storage rows with table entries; `_merge_results` docstring
   corrected.
8. **Busy guard:** `delete`/`move`/`copy`-onto targeting a bind path
   or a region containing bind paths → `busy`; a path that resolves
   to a mount root (`rel == /` on a non-root entry) is likewise
   `busy` for those verbs.
9. **Hop budget:** per-request TTL (constructor default 16) threaded
   through fan-out and tree; exhaustion → `budget_exhausted`.  The
   wire field lands with Pass C; the local plumbing lands here.
10. **Lifecycle:** `bind`/`unbind` primitives (bind onto existing
    empty directory; the graft-tree checks); `add_mount` =
    mkdir-if-absent + bind, `remove_mount` = unbind + strict
    non-recursive rmdir; aliasing check (`id()`-duplicate refusal);
    lock discipline — no storage I/O awaited under `_mount_lock`
    (mkdir before, re-check site under lock; rmdir after; close
    disposes outside); `close` = snapshot-and-clear under the lock,
    then gather identity-deduped, `owned`-gated, per-backend-timeout
    closes.

### 6. Pass A tests (`tests/`)

- Rework: `test_base_mounts.py` (bind-onto-empty, restart shape,
  strict rmdir, aliasing refusal, `no_overlay`, mkdir-sugar +
  `parents=`), `test_base_dispatch.py` (one funnel, entry-keyed
  grouping, decoration at rebase), `test_base_gates.py` (snapshot
  capabilities, ancestor composition — pin the read-only-root /
  writable-`/scratch` flip), `test_storage.py` (three required
  members; minimum test updated).
- New: shadow filtering (the MountFS #486 shape), cross-entry
  move/copy → `cross_mount`, the `busy` guard, `backend_unavailable`
  normalization (double raising `TransportError`), close
  ordering/dedupe/cancellation (wedged double with a gate), hop
  budget termination, `test_backends_memory.py` capability/name
  additions (absorbs 055 task 8).
- `test_base_spine.py` retires (055 task 10); grouped-read per-row
  classification pinned (closes 050).

## Pass B — adapter (`vfs/adapter.py`, new)

- `VFSStorageAdapter`: explicit per-verb methods; rebase arguments
  in, results *and error paths/messages* out; clamp `..`/absolute at
  the adapted root; forward `name`/`description`/`capabilities()`
  live; expose wrapped-router identity for best-effort bind-time
  cycle checks.  Not `SupportsClose`; `ClosingAdapter` opt-in.
- Signature bridges: `operations=[ResolvedPair]` → `moves=`/`copies=`;
  `edit` passes `edits=`.
- Tests: rebasing (args, results, errors), root clamp, capability
  forwarding (read-only router → fan-out skips, write gates
  `unsupported` pre-dispatch), nested bind over an adapter,
  mutual-adapter loop → `budget_exhausted`, ClosingAdapter vs default.

## Pass C — MCP trio (`vfs/backends/mcp.py`, `vfs/mcp_server.py`, new)

- Dependency: `mcp` (official python-sdk) added via `uv add`.
- Shared client core: `AsyncExitStack` owning (transport context,
  `ClientSession`); per-call timeout; transport/session failures →
  `TransportError`; teardown tolerates a dead peer.
- `MCPStorage` (generic, decision 23): `ls`/`stat` render paginated
  `tools/list` (name, description/schema), `run` → `call_tool`;
  `capabilities()` = run family + those listing reads, nothing else.
- `VFSStorage` (dialect): every verb → `call_tool` against the
  versioned vfs tool schemas; composite lowering (observation batches
  → path-form; Entry/EditOperation/pair batches as JSON); TTL field
  decremented across the boundary; `isError`/structured content →
  `Result`; `name`/`description`/caps refreshed together on
  (re)initialize; HTTP auto-reconnect (one re-initialize per op),
  stdio never respawned.
- Server wrapper: public verbs as versioned tools — no admin tools;
  `tools.listChanged` + notification when mount changes alter the
  composed set; `user_id` pinned to session identity, client-supplied
  values rejected/validated.
- Tests over the sdk's in-memory transport: dialect round-trip per
  verb, caps from tools/list + invalidation on list_changed, dead
  session → `backend_unavailable` → reconnect re-derives, generic
  MCPStorage tool listing + run, server refuses admin, identity
  pinning.

## Ripples (with Pass A unless noted)

- Stories: 015 superseded-in-shape note; 041 + 050 closed with
  verification; 048 closed by lock restructuring; 054 re-read against
  the new admin surface.  ADR 002 consequence note (first-touch at
  first routed op); ADR 003 unchanged.
- `tests2/` remains quarry; delete ported files as they are mined.

## Trade-offs accepted (recorded in the spec)

- Aliasing forbidden in v1; entry-keying + close dedupe make lifting
  it cheap later.
- No per-op refcounts: ops racing unbind/close may see
  `backend_unavailable` or a raw error — documented window, Linux
  `mntget`/`mntput` is the future shape if it matters.
- Cycles survived by budget, not prevented by detection — a
  deliberate narrowing.
