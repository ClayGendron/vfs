# 020 — Remote Backends as Mount Targets

- **Status:** draft
- **Date:** 2026-05-02
- **Owner:** Clay Gendron
- **Kind:** feature · transport · the FSP wire layer
- **Depends on:** 015 (router calls public API), 016 (cleanup),
  017 (topology resource), 018 (bind), 019 (unions)
- **Enables:** 021, 022 (cross-server edges and hybrid search
  across backends both require the wire to exist first)

## Intent

Make `add_mount` accept any FSP-speaking backend, in-process or
out-of-process, with **no router code change between them**. The
in-process case stays procedural (no JSON serialization) — Plan 9's
"kernel devices use the procedural form" lesson, applied. The
out-of-process case goes over JSON-RPC on a transport (stdio for
spawned subprocesses, HTTP/WebSocket for remote services).

After this story:

```python
# In-process, today's shape — still works
await client.add_mount("/data",
    DatabaseFileSystem(engine=engine))

# In-process, URI-driven (story 017's ctl write):
await client.write("/.mounts/ctl",
    "mount /data database://prod-pg?schema=docs flags=REPL\n")

# Subprocess server (e.g., a Slack-FS):
await client.add_mount("/slack",
    await connect("mcp+stdio:///opt/slack-fs/main.py"))

# Remote HTTPS service:
await client.add_mount("/corp",
    await connect("mcp+https://fsp.corp.example.com:8443"))
```

The router calls `fs.read(...)` on each. The local one runs SQL
directly; the remote ones marshal to JSON-RPC over their transport.

## Why

- **The product needs it.** Knowledge backends will not all be
  Python classes. Slack, Jira, Notion, Confluence, Salesforce,
  internal data stores — each runs as its own service or vendor.
  The mount API has to span them.
- **Plan 9's most consequential idea.** A 9P endpoint is a 9P
  endpoint, kernel device or remote disk or `import` from another
  machine. Without that uniformity, distribution costs you a new
  abstraction every time.
- **The synthesis memo committed to it.** Capability negotiation,
  transport over MCP/JSON-RPC, FSP as the wire format — all
  named, none built. This story ships the foundation.
- **The procedural-when-local rule is non-negotiable.** Local
  database calls cannot pay JSON-encode costs. The transport
  abstraction has to make that free.

## Scope

### In

1. **`VFSTransport` protocol.**
   ```python
   class VFSTransport(Protocol):
       async def call(self, method: str, params: dict) -> dict:
           """One request/response round-trip."""

       async def notify(self, method: str, params: dict) -> None:
           """One-way message (subscriptions, progress)."""

       async def subscribe(self, method: str, params: dict
                           ) -> AsyncIterator[dict]:
           """Streaming response."""

       async def close(self) -> None:
           """Tear down the transport."""
   ```

2. **`RemoteFS(VirtualFileSystem)`.**
   Public methods marshal to JSON-RPC and unmarshal:
   ```python
   class RemoteFS(VirtualFileSystem):
       def __init__(self, transport: VFSTransport, *, name: str):
           super().__init__(storage=False)
           self._t = transport
           self._name = name

       def uri(self) -> str:
           return self._t.uri()

       async def read(self, path=None, *, candidates=None,
                      user_id=None) -> VFSResult:
           reply = await self._t.call("fs.read", {
               "path": path,
               "candidates": candidates.to_json() if candidates else None,
               "user_id": user_id,
           })
           return VFSResult.from_json(reply)
       # ... write, stat, glob, grep, search, query, etc.
   ```
   No session, no engine, no `_*_impl`. Just JSON in, JSON out.

3. **Three transports shipped.**
   - **`mcp+stdio://path/to/server`** — spawn a subprocess, talk
     JSON-RPC over its stdin/stdout. Used for in-tree Python
     servers and external commands.
   - **`mcp+http://host:port`** / **`mcp+https://`** — talk HTTP
     to a remote MCP server.
   - **`mcp+ws://`** / **`mcp+wss://`** — WebSocket variant for
     bidirectional streaming.

4. **`InProcTransport` for testing only.**
   A degenerate transport whose `call` directly invokes the
   target backend's public method without serialization. Same
   wire shape, zero overhead. Useful for testing FSP servers
   in unit tests; **production code does not use this**, because
   in-process backends keep their existing direct-method-call
   path (per the procedural-vs-wire decision).

5. **Backend URI registration.**
   ```python
   register_backend_factory("database", build_database_fs)
   register_backend_factory("mssql", build_mssql_fs)
   register_backend_factory("mcp+stdio", build_remote_fs_stdio)
   register_backend_factory("mcp+http", build_remote_fs_http)
   ```
   `client.write("/.mounts/ctl", "mount /x <uri> ...")` looks up
   the URI scheme, calls the factory, mounts the result.

6. **FSP server skeleton (subprocess-mode).**
   A new `vfs.fsp_server` module:
   ```python
   def serve_stdio(fs: VirtualFileSystem) -> None:
       """Read JSON-RPC from stdin, dispatch to fs's public methods,
       write replies to stdout. Loops forever."""
   ```
   The minimal viable server. Used by `mcp+stdio://` clients.
   Out: full MCP protocol compliance — that's a follow-up. This
   story ships the FSP-shaped subset (one method per
   `VirtualFileSystem` public method).

7. **Capability negotiation at `version`/`initialize`.**
   The client sends an `initialize` request; the server replies
   with a list of supported methods (`["fs.read", "fs.write",
   "fs.glob", ...]`). Methods not advertised return
   `MountError(CapabilityNotSupported)` if invoked. Mirrors
   9P's `Tversion` and the synthesis memo's capability map.

8. **Streaming results via `subscribe`.**
   Long-running calls (large globs, future graph workspaces from
   story 024) use `subscribe` to stream pages. JSON-RPC progress
   tokens carry the stream.

9. **`MountInfo.status` reflects transport health.**
   `mcp+http://` mount that can't reach its server shows
   `status="error"` in `/.mounts/<encoded>/status`. Reconnect
   on next call; status flips back to `ok` on success.

10. **Lifecycle on `close`.**
    `VFSClient.close()` walks every mount and calls `fs.close()`,
    which for a `RemoteFS` calls `transport.close()`. Subprocess
    transports terminate the child; HTTP transports close their
    connection pool.

11. **No router code changes.**
    The router calls public methods (story 015). Remote backends
    implement public methods. Therefore the router doesn't need to
    know about remoteness. A test asserts: removing every
    reference to `RemoteFS` from `base.py`, `client.py`, and
    `routing.py`, the codebase still has a working remote-mount
    feature (because `RemoteFS` lives in its own module and the
    router only sees it as a `VirtualFileSystem`).

### Out

- Authn/authz between client and remote server. Out of scope
  here; story 028 (auth) handles it. The remote FSP server runs
  unauthenticated for now (loopback or trusted network).
- Connection pooling and retry policy for HTTP transport beyond
  basics. A `httpx.AsyncClient` is enough for v1.
- Multi-tenant remote servers. The remote server serves one
  filesystem per process for v1.
- A non-Python FSP server reference impl (Go, Rust, etc.). The
  protocol is JSON-RPC; a polyglot impl is feasible but not
  this story's job.

## Acceptance Criteria

1. **Round-trip a read through stdio.** Spawn `python -m
   vfs.fsp_server <fixture-fs>`, mount via `mcp+stdio://`, call
   `read("/x")`, get the same bytes as a direct in-process
   call.

2. **Round-trip through HTTP.** Run an HTTP fixture server,
   mount via `mcp+http://`, same test.

3. **Round-trip through WebSocket.** Same.

4. **No router code change.** Diff `base.py` between branches:
   only the changes from stories 015–019 should be present. No
   transport-specific code in the router.

5. **`RemoteFS.uri()` round-trips.** A mount registered via URI
   reports the same URI in `/.mounts/<encoded>/backend`.

6. **In-process direct-method call still works.** A
   `DatabaseFileSystem` mounted directly (no URI) bypasses
   transport entirely. Benchmark: zero JSON serialization on
   the hot path.

7. **`InProcTransport` matches direct-method call results
   semantically.** Test the FSP server contract by mounting a
   `RemoteFS` over `InProcTransport` against a fixture
   `DatabaseFileSystem` and asserting bit-identical results to a
   direct-mount of the same fs.

8. **Capability negotiation works.** A server that omits
   `fs.search` from its initialize reply causes `client.search(...)`
   on that mount to return `MountError(CapabilityNotSupported)`
   without making a wire call.

9. **Streaming results via `subscribe`.** A glob with
   `paginated=True` over `mcp+ws://` arrives in N pages,
   reassembled at the router into one `VFSResult`.

10. **Subprocess crash recovery.** Killing a `mcp+stdio://`
    server's child process surfaces `mount.transport_error`
    in the next call; status flips to `error`. Re-mount works.

11. **`VFSResult.to_json()` and `from_json()` are inverses.**
    Round-trip every primitive `VFSResult` shape (single
    candidate, multi candidate, error result, mixed) through
    JSON.

12. **`Candidate` and `Detail` round-trip.** Same.

13. **Mounting via ctl write works for remote URIs.**
    `write("/.mounts/ctl", "mount /slack mcp+stdio:///opt/slack-fs/main.py")`
    spawns the subprocess, mounts the result.

## Risks

- **JSON encoding cost on remote calls.** Inherent. Mitigation:
  the in-process direct-method path stays the default. Remote
  backends pay the cost; that's acceptable.
- **Async cancellation across the wire.** A cancelled router-
  level call must propagate to the remote server. JSON-RPC
  has no native cancel; we layer one on (`fsp.cancel` notify
  message carrying a request id). MCP progress / cancellation
  semantics inform the design.
- **Schema drift between client and server.** Versioning at
  `initialize`. Mismatched versions refuse to mount and return
  `MountError(InvalidVersion)`.
- **Stdio buffering.** Newline-delimited JSON-RPC over stdio
  needs careful flushing. Use length-prefixed framing
  (Content-Length header, MCP-style) to avoid buffering issues.
- **Long-running requests.** A single `read` on a 10GB file
  cannot fit in one JSON-RPC reply. Today's `VFSResult` already
  paginates; transport must support streaming for these. We
  have `subscribe` for that — but the read pipeline must use it.
- **Deadlocks via re-entrant calls.** A remote backend that
  calls back into the router (e.g., to read another mount) can
  deadlock if not careful. Document: remote backends must not
  call back into their parent router.

## Open Questions

1. **Should we pin to MCP exactly or define FSP as a superset?**
   Default: FSP is a superset / variant of MCP — same envelope,
   FSP-specific methods. This story aligns with MCP framing
   (Content-Length, JSON-RPC 2.0) so existing MCP servers can
   serve FSP with minimal additions.

2. **Are subprocesses launched eagerly or lazily?** Default:
   eagerly at mount time (so failure is loud). A `lazy=true`
   mount flag could defer.

3. **How does a remote backend declare its `MountFlag` support
   for unions?** Default: it doesn't — flags are router-side.
   Remote backends are union members; the router enforces
   union semantics.

4. **What about a backend that wants to *push* updates** (file
   created in Slack, want the agent's view to update)? Default:
   `notifications/resources/updated` over `subscribe`. Agent
   subscribes to relevant paths; remote pushes events.

5. **Versioning of FSP itself.** Default: every server
   advertises an FSP version at `initialize`. Story 029 (FSP
   spec) freezes the contract.

## References

- `src/vfs/base.py` — public method surface (the wire shape)
- `src/vfs/results.py` — `VFSResult.to_json` / `from_json` (need extending)
- Plan 9 networks paper — `cs` (connection server), `dial`,
  textual ctl files
- `lib9p/srv.c` — the canonical "serve a FS over a connection"
  loop; we are writing the JSON-RPC analog
- `lib9p/post.c` — `postmountsrv` and `listensrv`; our
  `serve_stdio` and HTTP server are the same idea
- MCP spec — protocol envelope and capability negotiation
- `docs/plan9-mount-namespace-recommendations.html` — Rec 13
- Synthesis memo §"Capability negotiation at initialize"
