# 056 — Storage Mounts: One Router, One Table, One Funnel

- **Status:** spec settled — research review 2026-07-07 (6
  primary-source studies, 3 adversarial lenses, no fatals); all open
  questions resolved with owner 2026-07-07; plan/tasks pending
- **Date:** 2026-07-07
- **Owner:** Clay Gendron
- **Kind:** refactor (mount model) + feature (adapter, MCP backend/server)
- **Depends on:** 049 (`StorageBackend` protocol), 055 (POSIX mount
  lifecycle, stored mount points), ADR 002 (engine ownership), ADR 003
  (parent rule)
- **Supersedes in shape:** 015 (router-calls-public-API — intent
  survives, mechanism replaced), 042's cross-instance commit gate, 048
  (closed by lock restructuring), the `_reachable_ids` cycle machinery
- **Enables:** `VFSStorage` remote mounts, generic `MCPStorage` tool
  mounts, the vfs MCP server; closes 050

## Intent

A mount binds a **storage instance**, not another router.  Today
`Binding(path, fs)` holds a `VirtualFileSystem`, which forces two
dispatch funnels (`_call_local_op` / `_call_remote_op`), `_parent`
chains, cross-instance commit gates, add_mount delegation, and
recursive close.  After this story the table maps
`path -> (StorageBackend, MountMeta)`, there is exactly one funnel, and
one `VirtualFileSystem` = one namespace = one policy layer.  The
storage protocol is the data plane; `add_mount` / `remove_mount` /
`close` / permissions are the router's control plane and are **not**
part of the protocol — no wire message can mutate a remote table.

This is the shape of every system studied.  A Linux `vfsmount` binds a
superblock (a filesystem instance: storage + ops) plus per-mount flags
— never a router; the NFS client is a `file_system_type` *under* the
one VFS, and nfsd is a service *wrapping* the composed namespace to
serve it back out.  Plan 9's per-process namespace binds channels to
file servers, `devmnt` is the one driver that serializes namespace
verbs onto 9P, and `exportfs` turns a composed namespace back into a
server.  FUSE backends implement a flat verb protocol with mount
mutation on a separate privileged path.  PyFilesystem2's `MountFS` and
fsspec's `DirFileSystem` are the same move at library level.  MCP's
`ClientRequest` union structurally lacks admin verbs — exports and
mount tables are configured locally in every one of these systems.
Router-mounts-router has no precedent anywhere.

Composition is recovered the Plan 9 way: a `VFSStorageAdapter`
presents a `VirtualFileSystem` as a `StorageBackend` (the exportfs
move); an MCP server wraps a router and serves its verbs as tools;
`VFSStorage` is the devmnt — a backend whose verbs serialize onto an
MCP session speaking the vfs dialect.  A server that does *not* speak
the dialect still mounts: generic `MCPStorage` surfaces any MCP
server as a namespace of runnable tools (decision 23).
Router-in-router becomes a special case you opt into, not the
primitive everything pays for.

## Decisions settled (research review 2026-07-07)

1. **A Binding holds `(path, storage, meta)`.**  `MountMeta` carries
   an optional mount-relative `PermissionMap`, `no_overlay: bool`,
   `owned: bool`, and the capability snapshot cached at bind.
   Identity (`name`, `description`) and capabilities live on the
   storage itself — see decisions 2 and 14.  Precedent:
   `struct vfsmount` = superblock + root + `mnt_flags` — policy on
   the entry, state on the storage, never a router.
2. **Capabilities are protocol, not inference.**  `StorageBackend`
   gains a required `capabilities() -> frozenset[Op]` — every backend
   declares what it can do, and `storage_ops()` presence-sniffing
   dies.  Self-declaration is what keeps indirection honest: a
   backend may expose only the read verbs, the adapter answers with
   its wrapped router's live set (a concrete adapter class defines
   every verb method, so structural sniffing would over-claim
   through it), and `VFSStorage` derives its set from paginated
   `tools/list`.  The gate consults the entry's bind-time snapshot,
   invalidated on `list_changed` or reconnect.  (A per-entry
   tightening override was considered and dropped: mount-level
   restriction is the permission map's job, and a Linux-style
   `MNT_READONLY` flag can return later without table changes.)
3. **Permissions stay per-entry, in mount-relative coordinates;
   ancestors compose by restriction.**  `check_writable` takes a
   `PermissionMap` plus error context, not a filesystem; rel paths
   stay mount-relative so the `/.vfs` alias rules keep firing.
   Resolution walks entries `/` → terminal and the most restrictive
   layer wins (Linux: `MNT_READONLY || SB_RDONLY`).  **Behavior change
   recorded:** a read-only root over a writable `/scratch` mount is
   now read-only end-to-end; today only the terminal gates.
4. **Bind is the primitive; mkdir is sugar.**  `bind` succeeds onto an
   existing **empty** directory in the parent-path-owning storage (the
   `graft_tree` analogue: exists + directory + empty); `add_mount` =
   mkdir-if-absent + bind, `parents=` per ADR 003.  This fixes
   rebind-after-restart on persistent backends (055's fused mkdir
   fails `exists` on every process restart) and turns crash orphans
   into valid mount sites instead of poison.  Linux, Plan 9, and FUSE
   never create mount points; the mkdir half is owned as udisks-style
   convenience, not claimed as POSIX.
5. **`remove_mount` = unbind + strict non-recursive rmdir.**  Never a
   cascade/permanent delete: once the parent path's storage can be
   shared or remote, 055's "provably empty" claim no longer holds and
   the current call is a data-loss bug.  A non-empty rmdir fails loud,
   leaving a plain directory — loud, honest, recoverable.
6. **The node's own storage is the `/` entry.**  An identity binding
   carries it; the fs-is-self branches at every chokepoint die, and
   every terminal gates and dispatches identically.  Linux's rootfs is
   just the first mount in the namespace.
7. **Nesting stays; shadowing is the Linux rule.**  Longest-prefix
   nested entries replace nested routers.  Results surfacing through
   entry M are filtered to drop rows at or under deeper bind paths
   before merging (the `__traverse_mounts` full-shadow rule); `tree`
   descends deeper binds and subtracts their region from the shallower
   answer; `ls` of a directory holding mount points unions the owning
   storage's rows with table entries.  `_merge_results`' "disjoint
   prefixes" docstring is corrected — shadow-filtering is what
   restores disjointness.  (This closes the MountFS #486 shape, the
   one part of the design with no working library precedent.)
8. **Cross-mount move/copy is a typed `cross_mount` refusal (EXDEV).**
   No silent copy+delete fallback (the fsspec/PyFilesystem degrade is
   non-atomic and opaque — wrong for an agent-facing tool); same-entry
   pairs delegate to the backend's native verb.  All grouping keys and
   the cross-mount check move to the **mount entry** (binding
   identity), not `id(storage)` or `id(fs)`.
9. **Aliasing (one storage object at two paths) is forbidden in v1** —
   an `id()`-keyed duplicate check at bind, the cheap successor to
   `_reachable_ids`' duplicate rejection.  Entry-keyed dispatch and
   identity-deduped close land anyway, so lifting the restriction
   later (Linux bind mounts are the precedent for "allow") is removing
   one check, not a redesign.
10. **`close()` releases what this process holds and ends its own
    sessions.**  Wire messages may release *this client's* handles —
    9P Tclunk, HTTP session DELETE, stdio termination (which ends the
    server process by MCP spec design) — but never mutate remote
    topology.  Mechanics: snapshot-and-clear the table under the lock;
    close storages outside it, identity-deduped, `owned`-gated, each
    with a per-backend timeout, gathered rather than sequential.
    `SupportsClose` is contractually idempotent and dead-peer-tolerant
    (FUSE `destroy`: the connection may already be gone).  A storage
    is unbound before its close is awaited, so cancellation mid-close
    can strand un-disposed resources (re-run `close`) but never leaves
    a closed storage reachable through the table.
11. **No storage I/O under the mount lock.**  `add_mount` runs mkdir
    before taking the lock, then re-checks the site and binds;
    `remove_mount` unbinds under the lock and rmdirs after release;
    close disposes outside it.  FUSE's hard-won rule: unbind is local
    table surgery that must succeed against a wedged backend
    (`umount -l`).  042's commit gate shrinks to table-local checks;
    048's reentrancy hazard closes by construction — no awaits under
    the lock means no reentrancy window.
12. **Dead backends: keep-and-error.**  New classified kind
    `backend_unavailable`; the funnel normalizes a defined
    `TransportError` family into it, keeping "raw exception = backend
    bug" true for in-process backends (FUSE settles presentation
    router-side the same way: severed connections become ENOTCONN
    uniformly).  The binding stays bound and errors distinctly — never
    silent auto-unbind; `remove_mount` is the operator action and
    always succeeds locally.  `VFSStorage` auto-reconnects an expired
    HTTP session — one re-initialize attempt per op, the client
    behavior the MCP spec prescribes for a 404'd session — and
    re-derives capabilities and description; a dead stdio child is
    never respawned silently (the session *is* the subprocess;
    operator rebind).
13. **Cycles: budget, not detection.**  Opaque storages defeat
    reachability analysis — that opacity is the feature.  A
    per-request hop/depth budget threads through fan-out, tree, and
    the wire dialect (a TTL field in dialect v1 so every vfs server
    honors it, default 16, constructor-configurable, decremented per
    adapter/MCP boundary); exhaustion classifies as the new `budget_exhausted`
    kind rather than hanging (Plan 9 tolerates loop mounts because
    walks are per-component and finite; our unbounded verbs must be
    made finite the same way).  The local adapter exposes its wrapped
    router's identity so bind-time checks catch the in-process case
    best-effort.  `_parent`/`_root`/`_reachable_ids` are deleted with
    no full successor — a deliberate narrowing, recorded here.
14. **Name and description are protocol members too.**
    `StorageBackend` gains `name` and `description` — identity
    travels with the backend, not the table, so decoration is live by
    construction.  Mount-row decoration moves to the rebase seam and
    reads the entry storage's `description`, so rows surfacing
    through *any* entry — including nested binds through an adapter —
    are decorated against the full table.  The adapter forwards the
    wrapped router's `name`/`description`; `VFSStorage` refreshes
    both from server info on (re)initialize, together with
    capabilities so they cannot diverge.  The router keeps its own
    constructor `name`/`description` — that is what the adapter and
    the MCP server forward.  (Preserves 055 decision 4's liveness
    promise, now protocol-shaped.)
15. **Identity pins at the session.**  The vfs MCP server derives
    `user_id` from authenticated session identity at initialize (the
    9P Tattach model: one session, one identity) and rejects or
    validates client-supplied `user_id` — never trusts it verbatim.
    `VFSStorage` does not forward caller `user_id` as an ordinary tool
    argument.  Forwarding it verbatim is a cross-tenant read hole.
16. **Batch atomicity, honestly scoped.**  All-gates-before-dispatch
    holds over the facts visible in *this* router's table; a terminal
    that is itself a namespace (adapter, `VFSStorage`) may classify a
    pre-validated row post-dispatch, and sibling terminals are not
    rolled back.  Single-terminal batches keep the strong promise.
    Inner denials pass through with classification intact, rebased to
    facade paths.
17. **`no_overlay` replaces `allow_child_mounts`.**  A per-entry flag
    refusing binds beneath that entry; `add_mount`'s mkdir is an
    ordinary gated mutation against the owning entry's permission map,
    so a read-only mount cannot host new mounts.
18. **Bind sites are busy to the data plane (the EBUSY rule).**
    `delete`, `move`, and `copy`-onto targeting a bind path, or whose
    cascade/subtree region contains bind paths, are refused with the
    new `busy` kind — Linux answers EBUSY for unlink/rename of a mount
    point.  This includes the resolved-into case: `delete("/a")` where
    `/a` is bound resolves to the mount's root and is likewise `busy`
    (unmount first).  Without this rule a cascade delete could remove
    a stored mount-point directory while its binding dangles.
19. **In-flight operations may race unbind/close — contract, not
    refcounts.**  Dispatch resolves terminals without holding the
    mount lock, so an op that resolved its entry before a concurrent
    `remove_mount`/`close` may reach a disposed backend.  v1 pins the
    honest contract (FUSE's ESHUTDOWN move): such races surface as
    `backend_unavailable` where the transport family can classify
    them, and are otherwise a documented raw-error window.  No per-op
    entry refcounts or draining in v1; Linux-style `mntget`/`mntput`
    is the recorded future shape if the window matters in practice.
20. **Wire dialect composites.**  Plain-data batches cross the wire as
    JSON schemas: `Entry` lists, `EditOperation` lists, move/copy
    pairs, `columns` as arrays.  Observation-input grouped dispatch
    does **not** cross: observation mirrors are resolved against the
    *client's* namespace and are meaningless server-side, so
    `VFSStorage` lowers grouped-row calls to path-form (+ columns) —
    recorded as a batch-semantics difference through remote entries.
    The vfs tool names and schemas are the wire protocol and are
    versioned deliberately.
21. **`add_mount` keeps its path default.**  With `name` on the
    protocol (decision 14), `path=None` still defaults to
    `/{storage.name}` — no breaking signature change after all.
    `owned` defaults `True` for a plain backend (constructor `/`
    entry or `add_mount`) — the router disposes what it was handed,
    per ADR 002; the adapter is non-closing by construction, so
    composition never closes a router you still hold.
22. **The mount lock is per-process; shared storage is unsynchronized
    admin.**  Two routers over one persistent/remote storage do not
    serialize mkdir/rmdir/bind against each other — the NFS model, two
    clients mounting one export.  Dual-binding one stored directory
    from two routers is therefore possible and legal; admin races
    surface as ordinary classified storage results (`exists`,
    `not_found`, `not_empty`), never corruption, and a foreign rmdir
    under a live binding lands in the keep-and-error state of
    decision 12, recoverable with `remove_mount`.
23. **Two MCP client backends, two claims.**  `VFSStorage` claims
    "this server speaks the vfs dialect" — the devmnt: the full
    storage protocol serialized onto the versioned vfs tool schemas.
    `MCPStorage` claims only "this is an MCP server" and mounts *any*
    server as a namespace of runnable tools: `tools/list` rows
    surface as `ls`/`stat`-able entries under the mount, `run` maps
    to `call_tool`, and its capability set is the run family plus
    those listing reads.  There is no foreign-filesystem translation
    layer — a generic server is tools, not files; if it speaks files,
    it speaks the dialect.

## Scope

### 1. Mount table and funnel (`vfs/base2.py`)

- `Binding` → `(path, storage, meta: MountMeta)`; identity entry at
  `/` for the node's own storage.
- Delete: `_call_remote_op` and its static match, `_parent`, `_root`,
  `_reachable_ids`, `_commit_mount`'s cross-instance half, add_mount
  delegation into children, `allow_child_mounts`, recursive close
  bookkeeping, `_resolve_terminal`'s nesting loop (single
  longest-prefix match), and the fs-is-self branches at every
  chokepoint.
- Entry-keyed grouping at **all five** identity-keyed sites:
  `_group_observations_by_terminal`, `_route_two_path`,
  `_route_entry_batch`, `mkedge`'s cross-mount check and delegation
  branch, and `_route_fanout`'s scoped grouping + region-expansion
  dedupe (whose two keyspaces collapse into one entry keyspace).
- Shadow filtering at the merge seam; `_tree_local` region
  subtraction; decoration at the rebase seam; the `busy` guard on
  data-plane mutations at bind sites; hop budget threaded through
  fan-out and tree.

### 2. Protocol changes (`vfs/storage.py`)

- `StorageBackend` gains three required members: `name`,
  `description`, and `capabilities() -> frozenset[Op]`; the read
  family remains the verb minimum.  `storage_ops()` presence
  derivation is deleted.
- `SupportsClose` docstring gains the idempotent + dead-peer
  contract; the `TransportError` family; the path-form contract for
  backend-returned paths (normalize and validate at the funnel — the
  dirfs #1638/#924 lesson from fsspec).
- `InMemoryStorage` and the test doubles implement the three new
  members; `InMemoryStorage` declares its full op set regardless of
  `allow_files` — capabilities speak ops, not per-kind guarantees,
  per 055.

### 3. Lifecycle and errors (`vfs/base2.py`, `vfs/results2.py`, `vfs/ops.py`)

- `bind`/`unbind` primitives; `add_mount`/`remove_mount` re-expressed
  as sugar per decisions 4–5; `no_overlay` enforcement; lock
  discipline per decision 11; close per decision 10.
- Error vocabulary gains `backend_unavailable`, `busy`, and
  `budget_exhausted` (non-retryable; a fan-out branch that exhausts
  its budget merges as that scope's classified failure while sibling
  scopes succeed — same merge shape as any per-scope refusal).

### 4. Adapter (`vfs/adapter.py`, new)

- `VFSStorageAdapter`: explicit per-verb methods, no getattr
  forwarding (fsspec's `__getattribute__` whitelist is the cautionary
  tale).  Rebases arguments in and results *and error paths/messages*
  out against facade coordinates (PyFilesystem's `unwrap_errors`
  precedent); `..`/absolute escapes clamp at the adapted root
  (exportfs `Exmnt`).  Forwards the wrapped router's `name`,
  `description`, and `capabilities()` live.  Not `SupportsClose` by
  default — never closes its
  wrapped router; a `ClosingAdapter` opt-in exists for owned
  composition.  Signature bridging is small: 14/16 verbs pass
  through; move/copy map `operations=[ResolvedPair]` onto
  `moves=`/`copies=`; edit passes `edits=` and drops the sugar.

### 5. MCP trio (`vfs/backends/mcp.py`, `vfs/mcp_server.py`, new)

- `MCPStorage` (generic, decision 23): same session ownership and
  transport handling as `VFSStorage`; `ls`/`stat` render `tools/list`
  (name, description/schema), `run` maps to `call_tool`, everything
  else is honestly absent from `capabilities()`.
- `VFSStorage`: an `AsyncExitStack` owns (transport context,
  `ClientSession`); each verb maps to `call_tool` with a per-call
  timeout knob; `isError`/structured content map into the `Result`
  channel; transport/session failures map to `backend_unavailable`;
  `name`/`description` from server info and caps from paginated
  `tools/list`, refreshed together per decisions 2 and 14; composite
  lowering per decision 20; teardown tolerates a dead peer.
- Server: a wrapper exposing a local `VirtualFileSystem`'s public
  verbs as versioned tools — never `add_mount`/`remove_mount`/
  `close`/permission tools; declares `tools.listChanged` and notifies
  when mount changes alter the composed capability set;
  session-pinned identity per decision 15.

### 6. Ripples

- Stories: 015 marked superseded-in-shape (its load-bearing rule —
  value-only, MCP-serializable boundary — re-reads as "the router
  calls only the storage protocol; the protocol *is* the wire shape");
  041 and 050 closed with verification (050 closes with per-row
  classification for grouped reads — atomicity is a mutation
  concern); 048 closed by lock
  restructuring; 054 re-read against the new admin surface.  ADR 002
  gains a consequence note (nothing exercises a backend at bind;
  first-touch/session handshake happen at the first routed op, by
  design).  ADR 003 unchanged.
- Tests (`tests/`): mount, capability, and close suites rewrite around
  storage mounts; router-composition tests re-express as adapter
  tests; cycle tests retire in favor of hop-budget tests.  New suites:
  shadow filtering, entry-keyed EXDEV grouping, bind-onto-existing-
  empty, strict rmdir, the `busy` guard, `backend_unavailable`
  mapping, close ordering/dedupe/cancellation, adapter rebasing.
  `tests2/` remains quarry.

## Acceptance criteria

- `add_mount(storage, "/a")` then `add_mount(storage2, "/a/b")`: reads
  through `/a` never surface `storage` rows under `/a/b`; `tree("/")`
  shows `storage2`'s rows there; `remove_mount("/a")` with `/a/b`
  still bound fails busy.
- Restart shape: bind on a persistent backend → new router over the
  same backend → `add_mount` at the same path succeeds onto the
  existing empty directory.
- `remove_mount` of a mount whose directory gained foreign rows fails
  loud without deleting them; `delete("/a", cascade=True)` where a
  bind lives at `/a/m` is refused `busy` with nothing deleted.
- `move("/a/x", "/b/y")` across entries returns `cross_mount`; within
  one entry it delegates to the backend's native move.
- A batch write spanning a local entry and an adapter whose inner
  namespace refuses one row: local rows honor the per-visible-facts
  promise; the inner denial arrives classified and facade-rebased.
- Adapter over a read-capability-only router: scoped fan-out skips it
  up front; a write gates `unsupported` before any dispatch.
- Wedged fake backend: `remove_mount` and a sibling's `close` complete
  within the timeout; the table never binds a closed storage.
- Mutual adapter mounts: unscoped `grep` terminates with
  `budget_exhausted`, not a hang.
- `VFSStorage` against a session that dies: the next op classifies
  `backend_unavailable`; after reconnect, capabilities reflect the
  fresh `tools/list`.

## Open questions

All resolved (review 2026-07-07):

- **Union mounts: ruled out permanently.**  The table stays
  path → one storage; the divergence from Plan 9's ordered per-point
  lists is deliberate.  If union semantics are ever wanted, they
  arrive as a composing backend (the overlayfs move — union as a
  filesystem type, not a table shape) with no table change.
- **Mount-point directories in non-self-owned storage: allowed, no
  flag.**  The Linux-normal case (mount over an NFS subdirectory);
  binding and shadowing stay local, and the shared-artifact hazards
  are already covered by strict rmdir (5), gated mkdir (17), and
  unsynchronized shared admin (22).  A prohibition would have to key
  on backend type — a special case with no principle behind it.
- **Wire dialect: vfs-dialect-only, plus the generic tool mount.**
  No foreign-filesystem translation layer; decision 23's
  `VFSStorage`/`MCPStorage` split is the answer.
- **Reconnect: auto for HTTP sessions, never for stdio** — folded
  into decision 12; the HTTP re-initialize is the MCP-spec-prescribed
  client behavior, and a dead stdio child is a crashed process, not
  an expired session.
- **Hop/TTL budget: wire-dialect v1, default 16,
  constructor-configurable** — folded into decision 13.  Loop
  protection only works if every server in the chain honors the
  field, which means shipping it in the first dialect version.
- **Ancestor-restriction flip ships outright, no compat hatch.**
  Pre-1.0; writable islands stay expressible via path-scoped rules on
  the root's map, so only the composition default changes
  (fail-closed).
- **Grouped reads classify per-row** (whole-batch rejection stays for
  mutations).  Reads are idempotent, so batch atomicity buys no
  safety — atomicity is a mutation concern; this also matches the
  fan-out verbs' per-scope partial results, and closes 050's
  inherited question.
