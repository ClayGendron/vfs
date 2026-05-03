# 015 — Routers Call the Public API, Not the Impl

- **Status:** draft
- **Date:** 2026-05-02
- **Owner:** Clay Gendron
- **Kind:** architectural · namespace boundary
- **Depends on:** existing `VirtualFileSystem` base, `_route_*` chokepoints,
  `_*_impl` terminal methods
- **Enables:** mounting external (out-of-process / remote) backends,
  Plan 9-shaped FSP wire compatibility, decoupled engine/session
  lifecycle (subsumes Rec 07 of the namespace redesign HTML)

## Intent

Make the router-to-backend boundary the same shape that an FSP wire
call would take. Today the router calls private `_{op}_impl`
methods on backend instances and passes a SQLAlchemy `AsyncSession`
across the boundary as a keyword argument. That call shape only
makes sense in-process; you cannot send a session over a socket.

Flip the contract:

- **The router only calls the backend's public methods**
  (`read`, `write`, `stat`, `glob`, `grep`, `delete`, `edit`,
  `mkdir`, `mkedge`, `copy`, `move`, etc.).
- **Public methods take values only** — paths, candidates, flags,
  user_id. No sessions, engines, weakrefs, or other in-process
  handles.
- **Each backend manages its own session/transaction internally.**
  The router does not know about sessions and never opens one on
  behalf of a backend.
- **`_*_impl` methods become an internal implementation detail of
  each backend**, called by the backend's own public method, not
  by the router.

The router becomes transport-agnostic: a `DatabaseFileSystem` that
runs SQL in-process and a `RemoteFS` that proxies calls to a
remote MCP/FSP server are interchangeable from the router's point
of view. Both look like a `VirtualFileSystem` subclass whose
public methods take values and return `VFSResult`.

## Why

Three load-bearing reasons.

### 1. The router currently leaks storage internals.

`base.py:480` (`_route_single`) does:

```python
async with fs._use_session() as s:
    result = await getattr(fs, f"_{op}_impl")(
        rel, user_id=user_id, session=s, **kwargs,
    )
```

The router opens a session on behalf of the backend, then calls
into the backend's *private* method passing that session. Three
problems with this:

- **It assumes every backend has a session.** A future
  backend that doesn't speak SQL (e.g. a Slack-FS, a memory-FS, a
  remote proxy) has to either invent a fake session or override
  every router code path.
- **It binds the router to the SQLAlchemy lifecycle.** The
  `async with fs._use_session()` is doing transaction management
  at the wrong layer; the router has no business deciding when a
  backend's transaction begins or ends.
- **It cannot be ported to a wire protocol.** A session object
  is not JSON-serializable. Today's router-to-impl call shape
  has no remote analogue.

### 2. Public methods are already FSP-shaped — but no one calls them through the router.

`VirtualFileSystem.read`, `.write`, `.stat`, etc. take values in
and return `VFSResult` out. That signature *would* survive a
JSON-RPC round-trip. The router bypasses them, so the FSP-shaped
surface exists but isn't load-bearing. Result: the wire format
and the procedural format have already drifted (sessions exist on
one side, not the other), even though no remote backend has been
written yet.

Plan 9 made the same call we want to make here, and made it with
discipline: the kernel device API and the 9P wire protocol have
the *same shape*. `Tread(fid, offset, count)` and the procedural
`devread(chan, offset, count)` carry the same fields. The mount
driver translates between them mechanically. That discipline is
what lets a kernel device and a remote file server be mounted
identically. We need the same discipline.

### 3. Mounting external servers (in-process Python class *or* a
remote MCP/FSP server *or* a Slack-FS box across the network) is
the next major capability the project commits to. It cannot be
built without this flip first. The router has to be able to
dispatch to a backend whose internals it knows nothing about.

This story is the precondition for that work. It does not
introduce remote backends (that's its own story) — it re-shapes
the router-to-backend boundary so remote backends can be added
without re-engineering the dispatch layer.

### 4. It subsumes the engine-disposal coupling.

Rec 07 of the namespace HTML (`docs/plan9-mount-namespace-recommendations.html`)
proposes decoupling engine lifecycle from mount membership.
Today's `remove_mount` calls `await fs._engine.dispose()`. That
coupling exists *only because the router can see `fs._engine`*.
Once the router only ever calls the public API, it has no
visibility into engines, sessions, connection pools, or any
other lifecycle handle. The "dispose on unmount" hack disappears
on the same move. Rec 07 is no longer a separate fix — it's a
free consequence of getting this boundary right.

## Scope

### In

1. **Move session management from router into backend public methods.**

   Each backend's public method is responsible for opening the
   session (or whatever its native unit-of-work is), running
   the operation, and committing/rolling back. The router never
   sees the session.

   ```python
   # On VirtualFileSystem (base class):
   async def read(self, path: str | None = None, *,
                  candidates: VFSResult | None = None,
                  user_id: str | None = None) -> VFSResult:
       # router-level concerns: validation, candidate dispatch,
       # mount routing — UNCHANGED.
       ...
       # When dispatching to a terminal:
       result = await fs.read(rel, candidates=..., user_id=user_id)
       #   ^^ public method, not _read_impl

   # On DatabaseFileSystem (storage backend):
   async def read(self, path: str | None = None, *,
                  candidates: VFSResult | None = None,
                  user_id: str | None = None) -> VFSResult:
       # backend-internal: open session, dispatch to _read_impl,
       # commit/rollback.
       async with self._use_session() as s:
           return await self._read_impl(
               path, candidates=candidates, user_id=user_id, session=s,
           )
   ```

   The router-level public method handles routing, prefix
   rebasing, error classification. The backend-level public method
   handles transaction management. They share the same name and
   signature; that is the point.

2. **Update every router chokepoint to call public methods.**

   The five router chokepoints in `base.py` each get the same
   one-line edit:

   - `_route_single` (`base.py:445`)
   - `_route_two_path` (`base.py:484`)
   - `_route_write_batch` (`base.py:1000`)
   - `_dispatch_grouped_candidates` (`base.py:254`)
   - `_route_*_fanout` (glob, grep, generic) (`base.py:613, 742, 958`)
   - `_cross_mount_transfer` (`base.py:562`)

   Today they all do some form of:

   ```python
   async with fs._use_session() as s:
       impl = getattr(fs, f"_{op}_impl")
       result = await impl(..., session=s, ...)
   ```

   After:

   ```python
   method = getattr(fs, op)
   result = await method(...)   # no session, no impl
   ```

3. **Move `_use_session()` to be a private helper on backends that
   need it.**

   It already lives on `VirtualFileSystem` because the router calls
   it. After this story, only the backend's own public methods
   call `_use_session()`. It can stay on the base class as a
   shared helper for SQL backends, but the router never invokes it.

4. **Remove `session` from public method signatures.**

   `VirtualFileSystem.read/write/stat/...` currently have no
   `session` kwarg. That's already correct at the public API
   level — only the impls do. After this story, the impls keep
   `session` (because backend-internal callers still need to pass
   one through), but no external caller (router included) ever
   sees it.

5. **One-line guarantee on the router: it never references
   `fs._engine`, `fs._session_factory`, `fs._use_session`, or
   `_*_impl` after this story.** Enforced by lint or grep in CI.

6. **Sessions become a backend-internal contract.**

   Within a single backend, a public method may delegate to
   helpers that share a session — that's how `DatabaseFileSystem`
   keeps a multi-step write in one transaction. The session
   contract is purely intra-backend. The router does not
   participate.

7. **Cross-mount calls each open their own transaction per
   backend.**

   `_cross_mount_transfer` already does read-from-source then
   write-to-dest. After this story, those become two calls to
   `src_fs.read(...)` and `dst_fs.write(...)`. Each backend opens
   its own session for its own call. There is no shared
   transaction across backends today, and we are explicitly not
   adding one. (Cross-mount atomicity has never been promised;
   see story 014 multi-mount semantics.)

8. **Backend ownership of error classification stays the same.**

   Public methods on backends already convert exceptions into
   `VFSResult(success=False, errors=...)` (see `_classify_error`
   in `exceptions.py`). The router relies on this and continues
   to. No change to that contract.

### Out

- **Mounting remote / external backends.** That is the next
  story (`016-remote-backends-as-mount-targets`). This story
  re-shapes the boundary; the next story uses the new boundary.
- **A wire protocol spec (FSP).** The synthesis memo committed
  to FSP. This story is the *precondition* for FSP — once the
  router only calls public methods, the public method signatures
  *are* FSP. But formalizing the spec, choosing the JSON shape,
  and building the transport are separate work.
- **Removing `_*_impl` methods.** They stay. They are the
  backend-internal step under each public method. They keep
  `session` and other backend-private kwargs; they are simply no
  longer called by the router.
- **Changing the public method surface.** Names, signatures,
  return types are all unchanged. This is purely about who calls
  them.
- **Async unit-of-work refactor across backends.** Each backend
  decides for itself how to manage its session. The base class
  ships a shared helper (`_use_session`) but does not mandate
  its use.

## Architectural Implications

### Three layers, clear roles

```text
┌─────────────────────────────────────────────────────────────┐
│  Router layer — public methods on VirtualFileSystem         │
│  (mount resolution, prefix rebasing, candidate dispatch)    │
│  Calls: backend.read(...) / .write(...) / etc.              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ values only
┌─────────────────────────────────────────────────────────────┐
│  Backend public layer — same method names on subclasses     │
│  (session management, transaction boundaries, error class.) │
│  Calls: self._read_impl(..., session=s) / etc.              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ session + values
┌─────────────────────────────────────────────────────────────┐
│  Backend impl layer — _*_impl methods                        │
│  (SQL, vector store, graph queries — backend internals)     │
└─────────────────────────────────────────────────────────────┘
```

The middle layer is the FSP boundary. Above it: router. Below
it: storage. The middle layer's signature can be serialized to
JSON; nothing above or below it can.

### A `RemoteFS` is now expressible

After this story, the following becomes a complete (skeleton) backend:

```python
class RemoteFS(VirtualFileSystem):
    def __init__(self, transport):
        super().__init__(storage=False)
        self._t = transport

    async def read(self, path: str | None = None, *,
                   candidates: VFSResult | None = None,
                   user_id: str | None = None) -> VFSResult:
        return VFSResult.from_json(await self._t.call("read", {
            "path": path,
            "candidates": candidates.to_json() if candidates else None,
            "user_id": user_id,
        }))

    # ... write, stat, glob, grep, delete, edit, mkdir, mkedge, ...
```

It has no `_use_session`, no `_engine`, no `_*_impl`. It is just
a `VirtualFileSystem` whose public methods do RPC. The router
mounts it the same way it mounts a `DatabaseFileSystem`, calls
the same methods, gets the same results.

This is the payoff. It is *only* possible after this story.

### Engine-disposal coupling disappears

`remove_mount` today contains:

```python
fs = self._mounts.pop(path)
self._rebuild_sorted_mounts()
if fs._engine is not None:
    await fs._engine.dispose()
```

After this story, the router has no business knowing
`fs._engine` exists. `remove_mount` becomes:

```python
self._mounts.pop(path)
self._rebuild_sorted_mounts()
# lifecycle is the caller's concern; close the fs explicitly
# when truly done.
```

`VFSClient.close()` continues to call `fs.close()` on each mount
during its own shutdown — which is the right place for it.

## Worked Examples

### Example A — A simple read, before and after

Before:

```text
VFSClient.read("/tenants/acme/docs/x.md")
  └─ _route_single("read", "/tenants/acme/docs/x.md")
       ├─ resolve to (DatabaseFileSystem(acme), "/x.md", "/tenants/acme/docs")
       ├─ async with fs._use_session() as s:           ◄── router opens session
       │     result = await fs._read_impl(
       │                  "/x.md", session=s, user_id=...)
       └─ return result.add_prefix("/tenants/acme/docs")
```

After:

```text
VFSClient.read("/tenants/acme/docs/x.md")
  └─ _route_single("read", "/tenants/acme/docs/x.md")
       ├─ resolve to (DatabaseFileSystem(acme), "/x.md", "/tenants/acme/docs")
       ├─ result = await fs.read("/x.md", user_id=...)  ◄── public method
       │     │
       │     └─ inside DatabaseFileSystem.read:
       │           async with self._use_session() as s:
       │               return await self._read_impl(
       │                            "/x.md", session=s, user_id=...)
       └─ return result.add_prefix("/tenants/acme/docs")
```

Externally identical behavior. Internally: the session is now
private to the backend; the router only saw values.

### Example B — A two-path move across mounts

Before (`_cross_mount_transfer`):

```python
async with src_fs._use_session() as s:
    read_results = ... await src_fs._read_impl(p, session=s, ...) ...
async with dst_fs._use_session() as s:
    write_results = ... await dst_fs._write_impl(..., session=s) ...
async with src_fs._use_session() as s:
    delete_results = ... await src_fs._delete_impl(p, session=s, ...) ...
```

After:

```python
read_results = await self._merge_results(
    [await src_fs.read(p, user_id=user_id) for p in src_rels])
# each call opens its own session inside src_fs
write_results = await self._merge_results(
    [await dst_fs.write(path=p, content=c, user_id=user_id, overwrite=...)
     for p, c in zip(...)])
delete_results = await self._merge_results(
    [await src_fs.delete(p, user_id=user_id) for p in src_rels])
```

The router never opens a session. Each backend handles its own
transaction(s). The contract about cross-mount non-atomicity is
unchanged — it was never atomic and still isn't.

### Example C — Glob fanout

Before (`_route_glob_fanout`):

The router calls `fs.glob(...)` on each mount (this one is
already public-API-shaped) but for self-storage drops to:

```python
async with self._use_session() as s:
    return await self._glob_impl(pattern=..., session=s, ...)
```

After:

```python
return await self.glob(pattern=..., ...)
```

For glob/grep, the public-API form is mostly already in place
because `_route_*_fanout` calls `fs.glob` / `fs.grep` on child
mounts (treating them as black boxes). The cleanup is to make
**self-storage** dispatch use the same path. Today self-storage
gets special-cased into the impl; after this story, it doesn't.

### Example D — A future RemoteFS mounted alongside a DatabaseFileSystem

```python
client = VFSClient()
await client.add_mount("/local", DatabaseFileSystem(engine=local))
await client.add_mount("/slack", RemoteFS(connect("mcp+http://slack-fs:8080")))

# Hybrid search across both:
result = await client.search(query="claim audit trail",
                              paths=("/local/", "/slack/"))
```

The router cannot tell the two backends apart. It calls
`local_fs.search(...)` and `slack_fs.search(...)` and merges the
results. The local one runs SQL; the remote one runs JSON-RPC.
Same code path in the router. **This example only works after
this story is done.**

## How VFS Components React

### MCP + database

Today an MCP tool call lands in `VFSClient.read(...)` which calls
`_route_single` which reaches into the backend's impl with a
session. After this story, the MCP tool call lands in
`VFSClient.read(...)` which calls `_route_single` which calls
`backend.read(...)`. The backend opens its own session.
Externally identical, but now the same MCP tool call would work
unchanged if the backend were a remote MCP server instead of a
local SQL backend. The MCP tool surface is the FSP surface is
the public method surface — three names for the same shape.

### Graph traversal

Graph queries today go through `DatabaseFileSystem._graph_impl`
helpers that share a session with the surrounding read/write call.
After this story, graph queries are still served from inside the
backend's session. The router does not participate. A traversal
that crosses a mount boundary still goes back to the router (one
fan-out per mount), and each mount's graph query runs in its
own session. Cross-mount graph edges are still handled at the
router level — same as today, with cleaner code.

### Vector / BM25 hybrid search

Hybrid search dispatch fans out to each backend's `search` /
`grep` public methods, merges per-backend ranked candidates,
re-scores at the router level. After this story, the per-backend
calls are just public method calls. A `VectorStoreFS` that
proxies a remote vector store (e.g. a Databricks vector index
exposed as an FSP server) plugs into the same fan-out without
changing dispatch code. BM25 IDFs remain per-backend because
they're computed inside the backend; the merge logic at the
router doesn't care whether the IDF was computed in-process or
over the wire.

## Acceptance Criteria

1. **Router never calls `_*_impl`.** A grep over `src/vfs/base.py`
   for `_impl(` returns zero hits inside `_route_*` and
   `_dispatch_*` chokepoints. (CI lint enforces this.)

2. **Router never opens a session.** A grep over `src/vfs/base.py`
   for `_use_session` inside the router chokepoints returns zero
   hits. The only callers of `_use_session` are inside backend
   public methods (`DatabaseFileSystem.read/write/...`) and
   subclass overrides.

3. **Each backend's public methods open their own session.**
   `DatabaseFileSystem.read`, `.write`, `.stat`, `.glob`, `.grep`,
   `.delete`, `.edit`, `.mkdir`, `.mkedge`, `.copy`, `.move` each
   own their session lifecycle. No public method takes `session`
   as a parameter.

4. **`_*_impl` signatures unchanged.** They still take `session`
   as a kwarg. They are called by their backend's own public
   method. Tests that exercise impls directly continue to work
   (with the test passing in a session as before).

5. **No regression in transaction semantics.** A single
   `vfs.write(batch)` that auto-chunks + auto-indexes still runs
   in one transaction (per mount). Story 014's per-mount
   atomicity guarantee is unchanged.

6. **Engine-disposal removed from `remove_mount`.** `remove_mount`
   only updates the mount table. `VFSClient.close()` walks every
   mount and calls `fs.close()` on each.

7. **`VFSClient.close()` and `VirtualFileSystem.close()` are the
   only places that dispose engines.** Tests assert that
   `remove_mount` followed by `add_mount` of the same backend
   instance does not require reconnect.

8. **Cross-mount move/copy uses public methods.**
   `_cross_mount_transfer` calls `src_fs.read(...)`,
   `dst_fs.write(...)`, `src_fs.delete(...)` — no `_*_impl`,
   no session in the router.

9. **Glob/grep self-storage uses public methods.**
   `_route_glob_fanout._query_self()` and
   `_route_grep_fanout._query_self()` call `self.glob(...)` /
   `self.grep(...)` instead of `self._glob_impl(...)` /
   `self._grep_impl(...)`.

10. **Public API surface is JSON-serializable.** A test asserts
    that every public method's argument list and return type
    can round-trip through JSON. (Mock `Candidate` and `VFSResult`
    serialization; assert no Python-only types appear in
    signatures.)

11. **A skeleton `RemoteFS(VirtualFileSystem)` mounts and serves
    reads.** Concrete implementation is out of scope, but the
    test fixture ships a stub `RemoteFS` that raises
    `NotImplementedError` from public methods, mounts cleanly,
    and is dispatched to by the router with no session opened
    on its behalf. The point of this AC is to prove that a
    no-storage, no-engine, no-session backend can be a
    first-class mount target.

12. **No new public API.** This is a pure refactor of the
    router-to-backend boundary. No new methods on
    `VirtualFileSystem`, `VFSClient`, `VFSClientAsync`, or any
    backend. No new fields on `VFSResult`. No new exceptions.

13. **No public behavior regression.** All existing tests pass
    unchanged. End-to-end behavior of every public method is
    bit-identical for in-process callers.

## Risks

- **Subtle session-sharing regression.** Today a multi-step
  router operation (e.g. `_cross_mount_transfer` reading then
  writing) runs each step under its own session. If any router
  code accidentally relied on session-state continuity across
  impl calls, the refactor could surface that. Mitigation: the
  router never had a *single* session that spanned multiple
  backends, so this is unlikely; tests for cross-mount move/copy
  must verify that the existing read-then-write contract holds.

- **Performance: extra `async with` per public call.** The
  backend now opens a session inside its public method even for
  trivial reads. The cost is negligible (`AsyncSession` setup is
  cheap) but worth measuring on the hot path. Mitigation:
  benchmark before/after on a 100k-row glob.

- **Subclass overrides may have referenced `_*_impl` from
  outside the backend.** Code that overrides `_*_impl` keeps
  working; code that *calls* `_*_impl` from outside the backend
  (a test, a tool) will see the same behavior because the impl
  is unchanged — only the router stopped calling it.

- **Lifecycle responsibility shift.** Callers that today rely on
  `remove_mount` disposing the engine have to add an explicit
  `await fs.close()` (or, more typically, rely on
  `VFSClient.close()` to do it). A migration note in the
  changelog covers the transition.

- **Two methods named the same on parent and child.** The
  router-level `read` and the backend-level `read` share a name.
  This is intentional (it is the FSP boundary), but it can
  confuse a reader. Mitigation: docstrings on each layer
  explicitly state which layer they implement; the base-class
  `read` docstring says "delegates to terminal backend's
  `read`"; the backend's `read` docstring says "owns its own
  transaction; calls `_read_impl` internally."

- **A backend that overrides the router-level public method
  (e.g. for caching) has to be careful.** If a `VirtualFileSystem`
  subclass overrides `read` for a routing-time concern (a cache
  layer), it must call `super().read(...)` to dispatch through
  the router. Documented in the base-class docstring.

## Open Questions

1. **Should the router-level `read` and the backend-level `read`
   have different names** (e.g. `route_read` vs `read`)?
   Default: no. Plan 9 uses the same shape on both sides; the
   shared name is the contract. A subclass that wants both has
   `super().read(...)` available.

2. **Should `_*_impl` be renamed to something that signals
   "private to this backend"** (e.g. `_storage_read`, `_dialect_read`)?
   Default: no, not in this story. The current name is fine; the
   semantic shift (router stops calling it) is the change.

3. **Do graph methods follow the same flip?** Default: yes.
   Anything the router calls today via `_*_impl` becomes a public
   method call after this story.

4. **What about helpers like `_dispatch_grouped_candidates`?**
   They are router-internal and call public methods on
   backends. They stay router-internal. The flip is at the
   router-to-backend edge, not within the router.

5. **Should we ship a small `mount://` URI scheme that lets
   `add_mount("/data", "mount://database://prod-mssql?schema=docs")`
   work?** Default: no, not in this story. URI-based
   construction is part of the next story (remote backends as
   mount targets).

## References

- `src/vfs/base.py:445` — `_route_single` (calls `_{op}_impl` today)
- `src/vfs/base.py:484` — `_route_two_path` (same)
- `src/vfs/base.py:562` — `_cross_mount_transfer` (multi-step session use)
- `src/vfs/base.py:613` — `_route_glob_fanout` (self-storage path)
- `src/vfs/base.py:742` — `_route_grep_fanout` (same)
- `src/vfs/base.py:1000` — `_route_write_batch` (write impl)
- `src/vfs/base.py:1062` — `_use_session` (the helper that moves)
- `src/vfs/client.py:102` — `VFSClient.add_mount` (where lifecycle
  decisions land for the synchronous facade)
- `docs/plan9-mount-namespace-recommendations.html` — Rec 07
  (decouple engine lifecycle from mount membership) is subsumed
  by this story.
- `context/learnings/2026-04-19-fsp-vfs-synthesis.md` — synthesis
  memo committing to FSP and capability negotiation; this story
  is the precondition.
- `~/.claude/projects/-Users-claygendron-Git-Repos-grover/memory/plan9_to_vfs_guidance.md`
  — Rule 12 ("code-size sanity check") and the FSP boundary
  discussion in the auto-memory notes.
- Plan 9 source `lib9p/srv.c` and `lib9p/ramfs.c` — the canonical
  example of a public-API-only backend; the lib9p `Srv` callback
  table is exactly the FSP shape this story moves toward.
