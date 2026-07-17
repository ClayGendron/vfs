# 015 — Routers Call the Public API, Not the Impl

- **Status:** superseded in shape by 056 (2026-07-07) — the intent
  survives: the load-bearing rule (a value-only, MCP-serializable
  boundary between composed namespaces) re-reads as "the router calls
  only the storage protocol; the protocol *is* the wire shape."  The
  concrete mechanism (routers calling mounted routers' public verbs)
  is gone: 056 mounts storage, not routers, and composition crosses
  the boundary through the adapter or the MCP dialect.
- **Date:** 2026-05-02
- **Owner:** Clay Gendron
- **Kind:** architectural · namespace boundary
- **Depends on:** existing `VirtualFileSystem` base, `_route_*` chokepoints,
  `_*_impl` terminal methods
- **Enables:** mounting external (out-of-process / remote) backends,
  MCP-shaped VFS server/client adapters, Plan 9-shaped FSP wire
  compatibility, decoupled engine/session lifecycle (subsumes Rec
  07 of the namespace redesign HTML)

## Intent

Make the router-to-backend boundary the same shape that an MCP
filesystem tool call or FSP wire call would take. Today the router
calls private `_{op}_impl`
methods on backend instances and passes a SQLAlchemy `AsyncSession`
across the boundary as a keyword argument. That call shape only
makes sense in-process; you cannot send a session over a socket.

Flip the contract:

- **The router only calls a child/terminal mount's public methods**
  (`read`, `write`, `stat`, `glob`, `grep`, `delete`, `edit`,
  `mkdir`, `mkedge`, `copy`, `move`, etc.).
- **Public methods take values only** — paths, candidates, flags,
  user_id. No sessions, engines, weakrefs, or other in-process
  handles.
- **Each filesystem manages its own self-storage session/transaction internally.**
  The router does not know about sessions and never opens one on
  behalf of another filesystem.
- **`_*_impl` methods become an internal implementation detail of
  each filesystem**, called only by the filesystem that owns the
  storage. A parent/router must not call a child mount's impl.

The router becomes transport-agnostic: a `DatabaseFileSystem` that
runs SQL in-process and a `MCPFileSystemMount` that proxies calls
to a remote MCP server are interchangeable from the router's point
of view. Both look like a `VirtualFileSystem` subclass whose
public methods take values and return `VFSResult`.

## MCP Framing

Story 015 should make VFS build *around* MCP, not merely be
serializable later. The target architecture is:

```text
VFS public method        MCP primitive
────────────────────────────────────────────────────────────────
read/stat/ls/glob       tools/call for executable filesystem API
write/edit/delete/...   tools/call for mutations
VFSResult               wrapper around MCP CallToolResult
Candidate / VFS item    structuredContent item + optional resource link
readable file contents  resources/read view, where useful
filesystem namespace    resources/list or resource templates, where useful
mount lifecycle         one MCP ClientSession per mounted MCP server
```

This does **not** mean every file operation must be implemented
using MCP inside the process. Local SQL backends should stay fast
and call local storage directly through `_call_local_impl(...)`.
It means every cross-mount call uses the same shape that an MCP
tool call would use: JSON-serializable arguments in, MCP-shaped
result out, no Python sessions or engines across the boundary.

Two MCP roles fall out of this:

1. **VFS as an MCP server.** A VFS instance can expose tools such
   as `vfs.read`, `vfs.write`, `vfs.edit`, `vfs.delete`,
   `vfs.glob`, `vfs.grep`, and `vfs.stat`. Those tools call the
   existing public VFS methods and return MCP `CallToolResult`
   objects. Read-only resource views can also expose stable
   `vfs://...` URIs through `resources/list`,
   `resources/templates/list`, and `resources/read`.

2. **VFS as an MCP client/mount.** A mounted MCP server is a
   `VirtualFileSystem` adapter with one MCP client session. If
   the remote server exposes the VFS/FSP tool set, the adapter
   routes `read`, `write`, `edit`, etc. directly to those tools.
   If the remote server exposes unrelated tools (`get_emails`,
   `clone_repo`, etc.), the adapter exposes them as tool entries
   under a namespace, but discovery reads must not execute them.

The core safety rule:

```text
read/stat/ls/glob discover or return state.
call_tool executes generic tools.
filesystem protocol tools may be called by filesystem methods.
```

So `read("/tools/github/clone_repo")` should return the tool
schema/description, not clone a repository. Execution is explicit
through a tool-call API or a later carefully designed write-to-tool
convention.

## Why

Five load-bearing reasons.

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

### 2. Public methods are already MCP/FSP-shaped — but no one calls them through the router.

`VirtualFileSystem.read`, `.write`, `.stat`, etc. take values in
and return `VFSResult` out. That signature *would* survive a
JSON-RPC round-trip. The router bypasses them, so the MCP/FSP-shaped
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

### 3. MCP expects isolated client/server boundaries.

MCP's architecture is client-host-server: a host manages security
policy and multiple clients; each client maintains one isolated
session with one server; servers expose focused tools, resources,
and prompts. VFS should fit that shape naturally. A mount backed by
another MCP server should look like one isolated client session from
the router's point of view, not like a Python object whose SQL
session factory can be reached into.

### 4. Mounting external servers (in-process Python class *or* a
remote MCP/FSP server *or* a Slack-FS box across the network) is
the next major capability the project commits to. It cannot be
built without this flip first. The router has to be able to
dispatch to a backend whose internals it knows nothing about.

This story is the precondition for that work. It does not
introduce remote backends (that's its own story) — it re-shapes
the router-to-backend boundary so remote backends can be added
without re-engineering the dispatch layer.

### 5. It subsumes the engine-disposal coupling.

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

1. **Move cross-mount session management out of the router.**

   Each filesystem's public method still handles routing. When the
   resolved terminal filesystem is `self`, the public method may
   open `self`'s session and call `self._*_impl(...)`. When the
   resolved terminal filesystem is a mounted child, the router calls
   the child's public method and never opens that child's session.

   ```python
   # On VirtualFileSystem (base class):
   async def read(self, path: str | None = None, *,
                  candidates: VFSResult | None = None,
                  user_id: str | None = None) -> VFSResult:
       # router-level concerns: validation, candidate dispatch,
       # mount routing — UNCHANGED.
       ...
       fs, rel, prefix = self._resolve_terminal(path)
       if fs is self:
           result = await self._call_local_impl(
               "read", path=rel, candidates=candidates, user_id=user_id
           )
       else:
           result = await fs.read(rel, candidates=candidates, user_id=user_id)
       return result.add_prefix(prefix)
   ```

   The public method handles routing, prefix rebasing, and error
   classification. Local self-storage still reaches `_read_impl`,
   but only through a local helper on the same object. Child mounts
   are always reached through the public API. That is the protocol
   boundary.

2. **Update every router-to-mount chokepoint to call public methods.**

   The five router chokepoints in `base.py` each get the same
   one-line edit:

   - `_route_single` (`base.py:445`)
   - `_route_two_path` (`base.py:484`)
   - `_route_write_batch` (`base.py:1000`)
   - `_dispatch_grouped_candidates` (`base.py:254`)
   - `_route_*_fanout` (glob, grep, generic) (`base.py:613, 742, 958`)
   - `_cross_mount_transfer` (`base.py:562`)

   Today they often do some form of:

   ```python
   async with fs._use_session() as s:
       impl = getattr(fs, f"_{op}_impl")
       result = await impl(..., session=s, ...)
   ```

   After, when `fs is not self`:

   ```python
   method = getattr(fs, op)
   result = await method(...)   # no session, no impl
   ```

   When `fs is self`, the chokepoint calls a local self-storage
   helper that opens `self`'s session and invokes `self._*_impl`.
   This explicit self/child split prevents public-method recursion.

3. **Move `_use_session()` to be a private helper on backends that
   need it.**

   It already lives on `VirtualFileSystem` because the router calls
   it. After this story, only local self-storage helpers and backend
   public methods call `_use_session()`. It can stay on the base
   class as a shared helper for SQL backends, but parent routers
   never invoke it on child mounts.

4. **Remove `session` from public method signatures.**

   `VirtualFileSystem.read/write/stat/...` currently have no
   `session` kwarg. That's already correct at the public API
   level — only the impls do. After this story, the impls keep
   `session` (because backend-internal callers still need to pass
   one through), but no external caller (router included) ever
   sees it.

5. **One-line guarantee on the mount boundary: parent routers never
   reference `child._engine`, `child._session_factory`,
   `child._use_session`, or `child._*_impl` after this story.**
   Local `self._use_session()` and `self._*_impl` remain allowed for
   self-storage. Enforced by focused tests/grep around dispatch sites.

6. **Sessions become a backend-internal contract.**

   Within a single filesystem, a public method may delegate to
   helpers that share a session — that's how `DatabaseFileSystem`
   keeps a multi-step write in one transaction. The session
   contract is purely intra-filesystem. Parent routers do not
   participate in child transaction management.

7. **Cross-mount calls each open their own transaction per
   backend.**

   `_cross_mount_transfer` already does read-from-source then
   write-to-dest. After this story, those become public calls to
   `src_fs.read(...)` and `dst_fs.write(...)`, preferably batched
   (`read(candidates=...)`, `write(entries=...)`,
   `delete(candidates=...)`) rather than one public call per file.
   Each backend opens its own session for its own call. There is no shared
   transaction across backends today, and we are explicitly not
   adding one. (Cross-mount atomicity has never been promised;
   see story 014 multi-mount semantics.)

8. **Backend ownership of error classification stays the same.**

   Public methods on backends already convert exceptions into
   `VFSResult(success=False, errors=...)` (see `_classify_error`
   in `exceptions.py`). The router relies on this and continues
   to. No change to that contract.

9. **Define the MCP-shaped VFS protocol surface.**

   Story 015 should document the filesystem tool names, argument
   envelopes, result envelope, and resource URI conventions that
   future MCP adapters will use. The local implementation still
   calls Python methods, but the value shape must be mechanically
   translatable to `tools/call`.

   Baseline filesystem tools:

   ```text
   vfs.read(path | candidates, columns?, user_id?)
   vfs.write(path/content | entries, overwrite?, user_id?)
   vfs.edit(path | candidates, edits, user_id?)
   vfs.delete(path | candidates, permanent?, cascade?, user_id?)
   vfs.stat(path | candidates, columns?, user_id?)
   vfs.ls(path | candidates, columns?, user_id?)
   vfs.mkdir(path, user_id?)
   vfs.move(src/dest | moves, overwrite?, user_id?)
   vfs.copy(src/dest | copies, overwrite?, user_id?)
   vfs.glob(pattern, paths?, ext?, max_count?, columns?, user_id?)
   vfs.grep(pattern, paths?, ext?, globs?, context?, columns?, user_id?)
   ```

   Namespacing can decide later whether MCP tool names are dotted
   (`vfs.read`) or plain (`read`) inside a dedicated VFS server.
   The important contract is that the arguments are JSON values and
   the result is MCP-tool-result-shaped.

10. **Document `VFSResult` as an MCP `CallToolResult` wrapper.**

   The current `VFSResult(success, errors, function, candidates)`
   remains source-compatible for this story, but the target contract
   is:

   ```text
   VFSResult
     ├─ content              # MCP ContentBlock[], model-readable text
     ├─ structuredContent    # operation, items/candidates, errors, cursors
     ├─ isError              # inverse of success
     └─ _meta                # routing, timing, backend, projection metadata
   ```

   During Story 015, this is a spec-level constraint: do not add
   route code that assumes `VFSResult` can only be the current
   Pydantic model. Remote mounts should be able to return a
   `CallToolResult` that is wrapped into a `VFSResult` at the
   adapter boundary.

11. **Separate resources from tools.**

   MCP resources are a good fit for read-only context and stable
   URIs. VFS should expose files as resources where useful, but
   mutation and search remain tools. Generic non-filesystem MCP
   tools may appear in the VFS namespace as discoverable entries,
   but `read` must show schema/metadata only. Execution belongs to
   explicit tool invocation.

12. **Treat MCP tool annotations as hints, not authorization.**

   `readOnlyHint`, `destructiveHint`, `idempotentHint`, and
   `openWorldHint` are useful for UI and planning, but the VFS
   permission system remains authoritative. A remote server's
   annotations must never override VFS mount permissions,
   `check_writable`, user scoping, or confirmation policy.

### Out

- **Production MCP server/client adapters.** This story defines
  the MCP-shaped boundary and may include tiny stubs for tests, but
  a real stdio/Streamable HTTP server, auth, process management,
  reconnect, and deployment packaging belong in follow-up stories.
- **Full `VFSResult` migration.** Story 015 documents the MCP
  target shape and avoids blocking it. Actually replacing the
  current result model with `CallToolResult` fields is a separate
  result-envelope story.
- **Generic MCP tool namespace execution.** This story can specify
  how generic tools should be represented, but adding `call_tool`
  or a write-to-tool execution convention is separate API work.
- **A standalone wire protocol spec (FSP).** MCP becomes the
  deployment/interoperability protocol. A smaller VFS/FSP profile
  may still be useful as the subset of MCP tools that make a server
  mountable as a filesystem, but it is not a separate transport in
  this story.
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
│  Public method / router layer on VirtualFileSystem          │
│  (mount resolution, prefix rebasing, candidate dispatch)    │
│  Child mount: calls backend.read(...) / .write(...) / etc.  │
│  Self-storage: calls local self-storage helper              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ child: values only / self: local session
┌─────────────────────────────────────────────────────────────┐
│  Mount public API or local self-storage helper              │
│  (transaction boundaries, error classification)             │
│  MCP mount calls tools; local storage calls self._*_impl     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ local storage only: session + values
┌─────────────────────────────────────────────────────────────┐
│  Backend impl layer — _*_impl methods                        │
│  (SQL, vector store, graph queries — backend internals)     │
└─────────────────────────────────────────────────────────────┘
```

The public method surface is the MCP/FSP boundary. When the target
is a child mount, the parent router uses only that boundary. When
the target is self-storage, the same public method may drop below
the boundary into a local helper; that local path is not a remote
contract and must never be used on another filesystem.

### An `MCPFileSystemMount` is now expressible

After this story, the following becomes a complete (skeleton) backend:

```python
class MCPFileSystemMount(VirtualFileSystem):
    def __init__(self, client):
        super().__init__(storage=False)
        self._client = client

    async def read(self, path: str | None = None, *,
                   candidates: VFSResult | None = None,
                   user_id: str | None = None) -> VFSResult:
        call = await self._client.call_tool("vfs.read", {
            "path": path,
            "candidates": candidates.model_dump(mode="json") if candidates else None,
            "user_id": user_id,
        })
        return VFSResult.from_mcp_tool_result(call)

    # ... write, stat, glob, grep, delete, edit, mkdir, mkedge, ...
```

It has no `_use_session`, no `_engine`, no `_*_impl`. It is just
a `VirtualFileSystem` adapter whose supported public methods call
MCP tools. The router mounts it the same way it mounts a
`DatabaseFileSystem`, calls the same methods, gets the same
results. The adapter must override every public operation it
supports so it does not inherit the self-storage route.

This is the payoff. It is *only* possible after this story.

### A VFS MCP server is also expressible

The reverse adapter is symmetrical: expose VFS public methods as
MCP tools and translate `VFSResult` into `CallToolResult`.

```python
@mcp.tool(name="vfs.read", annotations={"readOnlyHint": True})
async def mcp_vfs_read(path: str | None = None,
                       candidates: dict | None = None,
                       user_id: str | None = None) -> CallToolResult:
    result = await vfs.read(
        path=path,
        candidates=VFSResult.model_validate(candidates) if candidates else None,
        user_id=user_id,
    )
    return result.to_mcp_tool_result()

@mcp.resource("vfs://{path}")
async def mcp_vfs_resource(path: str) -> ReadResourceResult:
    result = await vfs.read("/" + path.lstrip("/"))
    return result.to_mcp_resource_result()
```

Tools are the authoritative filesystem API because they support
structured outputs, errors, mutations, and search. Resources are a
read-only context view over the same namespace.

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
       │     └─ inside acme.read:
       │           resolve terminal inside acme
       │           fs is self, so call acme._call_local_impl("read", ...)
       │             async with self._use_session() as s:
       │                 return await self._read_impl(
       │                              "/x.md", session=s, user_id=...)
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
src_candidates = VFSResult(function="read", candidates=[Candidate(path=p) for p in src_rels])
read_results = await src_fs.read(candidates=src_candidates, user_id=user_id)

entries = [
    VFSEntry(path=dst_rel, content=candidate.content or "")
    for dst_rel, candidate in zip(dst_rels, read_results.candidates, strict=True)
]
write_results = await dst_fs.write(entries=entries, overwrite=overwrite, user_id=user_id)

delete_candidates = VFSResult(function="delete", candidates=[Candidate(path=p) for p in src_rels])
delete_results = await src_fs.delete(candidates=delete_candidates, user_id=user_id)
```

The parent router never opens a child session. Each backend handles
its own transaction(s), and the public calls stay batched where the
API already supports batching. The contract about cross-mount
non-atomicity is unchanged — it was never atomic and still isn't.

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
return await self._call_local_impl(
    "glob",
    pattern=pattern,
    paths=paths,
    ext=ext,
    max_count=self_max_count,
    columns=columns,
    user_id=user_id,
)
```

For glob/grep, the public-API form is mostly already in place
because `_route_*_fanout` calls `fs.glob` / `fs.grep` on child
mounts (treating them as black boxes). The cleanup is to make
**self-storage** dispatch explicit and local, not to recursively
call `self.glob(...)`.

### Example D — A future MCP mount alongside a DatabaseFileSystem

```python
client = VFSClient()
await client.add_mount("/local", DatabaseFileSystem(engine=local))
await client.add_mount(
    "/slack",
    MCPFileSystemMount(await connect_mcp("https://slack-fs.example/mcp")),
)

# Hybrid search across both:
result = await client.search(query="claim audit trail",
                              paths=("/local/", "/slack/"))
```

The router cannot tell the two backends apart. It calls
`local_fs.search(...)` and `slack_fs.search(...)` and merges the
results. The local one runs SQL; the remote one calls MCP
`tools/call`. Same code path in the router. **This example only
works after this story is done.**

### Example E — Generic MCP tools exposed as VFS entries

A non-filesystem MCP server can still be mounted into the namespace
as a tool catalog:

```text
/tools/github/clone_repo
/tools/github/list_pull_requests
/tools/gmail/search_messages
```

Reading one of those paths returns the tool definition:

```python
schema = await vfs.read("/tools/github/clone_repo")
```

Executing it is explicit:

```python
result = await vfs.call_tool(
    "/tools/github/clone_repo",
    {"repo": "org/project", "dest": "/workspace/project"},
)
```

`call_tool` is not part of this story's implementation scope, but
the namespace rule belongs here because it prevents accidental side
effects from ordinary file reads.

## How VFS Components React

### MCP + database

Today an MCP tool call lands in `VFSClient.read(...)` which calls
`_route_single` which reaches into the backend's impl with a
session. After this story, the MCP tool call lands in
`VFSClient.read(...)` which calls `_route_single` which calls
`backend.read(...)`. The backend opens its own session.
Externally identical, but now the same MCP tool call would work
unchanged if the backend were a remote MCP server instead of a
local SQL backend. The MCP tool surface, the VFS/FSP profile, and
the public method surface are the same shape at the mount boundary.

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
exposed as an MCP server) plugs into the same fan-out without
changing dispatch code. BM25 IDFs remain per-backend because
they're computed inside the backend; the merge logic at the
router doesn't care whether the IDF was computed in-process or
over the wire.

## Acceptance Criteria

1. **Parent routers never call a child mount's `_*_impl`.** Every
   router chokepoint checks `fs is self` before any private impl
   access. If `fs is not self`, dispatch is through
   `getattr(fs, op)(...)` only.

2. **Parent routers never open a child mount's session.** No code path
   does `child._use_session()`. `_use_session()` is called only for
   local self-storage (`self._call_local_impl(...)`) or by a subclass
   on itself.

3. **Self-storage has one explicit local helper.** The allowed local
   path is centralized (for example `_call_local_impl(op, ...)`) and
   is the only place that opens `self._use_session()` and calls
   `self._*_impl(...)` from the base class.

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

8. **Cross-mount move/copy uses batched public methods.**
   `_cross_mount_transfer` calls `src_fs.read(candidates=...)`,
   `dst_fs.write(entries=...)`, and
   `src_fs.delete(candidates=...)` — no `_*_impl`, no child
   session in the router.

9. **Glob/grep child fanout uses public methods; self-storage uses the local helper.**
   `_route_glob_fanout._query_self()` and
   `_route_grep_fanout._query_self()` call the local helper, while
   child mounts continue to receive `fs.glob(...)` / `fs.grep(...)`.

10. **Public API surface is JSON/MCP-serializable.** A test asserts
    that every filesystem public method's argument list and return
    value can round-trip through JSON. (Mock `Candidate` and
    `VFSResult` serialization; assert no Python-only types appear in
    signatures.) The serialized form must be usable as MCP
    `tools/call.params.arguments`.

11. **`VFSResult` has a documented MCP projection.** This story does
    not have to migrate the result model, but it must define and test
    helper behavior at the boundary: a successful VFS result maps to
    `CallToolResult(content=[...], structuredContent={...})`; a VFS
    execution error maps to `isError=true`, not a protocol-level
    JSON-RPC error.

12. **A skeleton `MCPFileSystemMount(VirtualFileSystem)` mounts and
    receives public calls.** Concrete transport implementation is out
    of scope, but the test fixture ships a stub MCP client whose
    `call_tool(name, arguments)` records calls and returns canned
    MCP-shaped tool results. The parent router dispatches to it with
    no session opened on its behalf. The point of this AC is to prove
    that a no-storage, no-engine, no-session MCP-backed filesystem
    can be a first-class mount target.

13. **A skeleton VFS MCP server adapter can be generated from the
    public surface.** Concrete stdio/HTTP serving is out of scope, but
    the spec/test fixture should prove the tool registry can describe
    `vfs.read`, `vfs.write`, `vfs.edit`, `vfs.delete`, `vfs.glob`,
    and `vfs.grep` with JSON Schemas and output schemas.

14. **Resource views are read-only.** If resource adapter sketches are
    added, `resources/read` maps only to VFS read-like operations.
    Mutations and generic tools are represented as tools, not
    resource reads.

15. **No new filesystem public API.** This is still primarily a
    refactor of the router-to-backend boundary. No new filesystem
    operations are added to `VirtualFileSystem`, `VFSClient`,
    `VFSClientAsync`, or any backend in this story. `call_tool` and
    generic MCP tool execution are follow-up API work.

16. **No public behavior regression.** All existing tests pass
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

- **Performance: extra public-method hop for child mounts.** Child
  dispatch now goes through the public method before the child reaches
  its own local storage path. The overhead should be negligible, but
  it is worth measuring on hot fanout paths. Mitigation: benchmark
  before/after on a 100k-row glob and preserve batched candidate/write
  calls.

- **External callers may have referenced `_*_impl`.** Code that
  overrides `_*_impl` keeps working. Code outside the owning
  filesystem that calls a private impl should migrate to the public
  API, because private impl methods are no longer a mount boundary.

- **Lifecycle responsibility shift.** Callers that today rely on
  `remove_mount` disposing the engine have to add an explicit
  `await fs.close()` (or, more typically, rely on
  `VFSClient.close()` to do it). A migration note in the
  changelog covers the transition.

- **One method name has two local roles.** A public method like
  `read` both routes and, when the terminal is `self`, reaches local
  storage through `_call_local_impl`. This is intentional (it is the
  MCP/FSP boundary), but it can confuse a reader. Mitigation: docstrings
  explicitly state that public methods dispatch across mounts and use
  a local helper only for self-storage.

- **A backend that overrides the router-level public method
  (e.g. for caching) has to be careful.** If a `VirtualFileSystem`
  subclass overrides `read` for a routing-time concern (a cache
  layer), it must call `super().read(...)` to dispatch through
  the router. Documented in the base-class docstring.

- **MCP result migration can become too large.** Replacing
  `VFSResult` with a literal `CallToolResult` shape touches renderers,
  query composition, tests, and CLI output. Mitigation: Story 015
  only requires documented conversion boundaries; a later result
  story can change the internal model once routing is clean.

- **Resources can tempt accidental execution.** MCP resources are
  application-driven context, while tools perform actions. A VFS view
  over generic MCP tools must not execute on `read`. Mitigation:
  represent generic tools as schemas/resources for discovery and
  reserve execution for explicit tool invocation.

- **Tool annotations are untrusted hints.** A remote MCP server can
  label a tool read-only or idempotent, but VFS cannot rely on that
  for authorization. Mitigation: VFS permissions and confirmation
  policy remain authoritative.

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
   Anything the router calls on a child mount today via `_*_impl`
   becomes a public method call after this story. Self-storage graph
   work remains local.

4. **What about helpers like `_dispatch_grouped_candidates`?**
   They are router-internal and call public methods on
   backends. They stay router-internal. The flip is at the
   router-to-backend edge, not within the router.

5. **Should we ship a small `mount://` URI scheme that lets
   `add_mount("/data", "mount://database://prod-mssql?schema=docs")`
   work?** Default: no, not in this story. URI-based
   construction is part of the next story (remote backends as
   mount targets).

6. **Should VFS MCP tool names be `read` or `vfs.read`?**
   Default: use `vfs.*` when a server may expose non-VFS tools, and
   allow plain names only for dedicated VFS-only servers. The adapter
   should discover by metadata/output schema rather than name alone.

7. **Should files primarily be MCP resources or MCP tools?**
   Default: both, with different purposes. Tools are the canonical
   operation API because they support mutations, search, structured
   output, and tool execution errors. Resources are read-only context
   views over stable file URIs.

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
- MCP specification 2025-11-25:
  - `https://modelcontextprotocol.io/specification/2025-11-25/architecture`
    — host/client/server separation and one isolated client session
    per server.
  - `https://modelcontextprotocol.io/specification/2025-11-25/server/tools`
    — tools, structured content, output schemas, and tool execution
    errors.
  - `https://modelcontextprotocol.io/specification/2025-11-25/server/resources`
    — resources as read-only context identified by URIs.
  - `https://modelcontextprotocol.io/specification/2025-11-25/basic/transports`
    — stdio and Streamable HTTP transports.
- `/Users/claygendron/Git/Repos/python-sdk/src/mcp/types/_types.py`
  — local MCP SDK source for `CallToolResult`, `Tool`,
  `ReadResourceResult`, `ServerCapabilities`, and tool annotations.
- `/Users/claygendron/Git/Repos/python-sdk/src/mcp/client/session.py`
  — local MCP SDK source for `ClientSession.call_tool`,
  `list_tools`, `read_resource`, and output-schema validation.
- `~/.claude/projects/-Users-claygendron-Git-Repos-grover/memory/plan9_to_vfs_guidance.md`
  — Rule 12 ("code-size sanity check") and the FSP boundary
  discussion in the auto-memory notes.
- Plan 9 source `lib9p/srv.c` and `lib9p/ramfs.c` — the canonical
  example of a public-API-only backend; the lib9p `Srv` callback
  table is exactly the FSP shape this story moves toward.
