# 023 — Per-Session Namespaces

- **Status:** draft
- **Date:** 2026-05-02
- **Owner:** Clay Gendron
- **Kind:** feature · namespace · concurrency model
- **Depends on:** 015, 016, 017, 018, 019
- **Enables:** real multi-tenant deployments; "rebind /docs to my
  tenant"; safe concurrent agent sessions on one router

## Intent

Move from one global mount table per `VFSClient` to **a private
mount overlay per session**. A session sees the global mounts
the router was configured with, plus its own additions /
rebinds / unmounts. Edits in one session do not affect other
sessions.

This is `rfork(RFNAMEG)` translated to our async/MCP world.

After this story:

```python
async with vfs.session() as s:
    if user.tenant:
        await s.bind(f"/tenants/{user.tenant}/docs", "/docs")
    if user.is_admin:
        await s.add_mount("/audit", AuditFS(...))
    return await s.read("/docs/notes.md")  # resolves to user's tenant
```

Two MCP requests against the same `VFSClient` from different
tenants get different `/docs` resolutions. Neither knows about
the other's mounts. The global router holds the canonical
mounts; sessions own overlays.

## Why

- **Multi-tenancy without per-tenant routers.** Today, isolating
  tenants requires either separate `VFSClient` instances or
  threading every call through tenant-aware path filters.
  Per-session namespaces collapse that to one router with one
  tenant-aware overlay per request.
- **The bind/union model is most useful per-session.** Story
  018 (bind) and 019 (unions) ship machinery; this story
  ships the *policy* — that bind/union are typically session-
  local, not router-global.
- **Plan 9 fidelity.** This is the single most distinctive idea
  in Plan 9. The window-system pattern (each window has its own
  namespace) is exactly the agent-session pattern.
- **The user explicitly likes the idea** but worried about
  agent UX ("how do agents discover overlays?"). This story
  answers that question concretely.

## Scope

### In

1. **`VFSSession` class.**
   ```python
   class VFSSession:
       """Owns a private mount overlay over a parent router.

       Reads see parent ∪ overlay. Edits mutate only overlay.
       Concurrent sessions cannot see each other's overlays.
       """
       def __init__(self, parent: VirtualFileSystem, *,
                    user_id: str | None = None,
                    permissions: PermissionMap | None = None):
           self._parent = parent
           self._overlay: dict[str, list[MountedFS]] = {}
           self._user_id = user_id
           self._permissions = permissions

       async def add_mount(self, ...): ...
       async def remove_mount(self, ...): ...
       async def bind(self, ...): ...
       async def read(self, ...): ...
       # ... full public API ...

       def fork(self) -> VFSSession: ...
       async def close(self) -> None: ...
   ```

2. **Resolution layering.**
   `_match_mount` consults overlay first, then parent. Overlay
   entries can override or extend parent entries. The cycle
   guard from 016 includes overlay edges.

3. **Default behavior unchanged.**
   `VFSClient.read(...)` (no session) continues to work — it's
   equivalent to `VFSClient.session().read(...)` with an empty
   overlay. Existing callers don't migrate.

4. **`async with vfs.session() as s:` context manager.**
   Opens a session, runs body, closes the session
   (releases overlay-only mounts; parent mounts are untouched).

5. **`s.fork()` for `rfork(RFNAMEG)` semantics.**
   Returns a new session with a *copy* of this session's
   overlay. Parent edits no longer propagate. Used for
   sub-tasks that need to experiment with namespace edits.

6. **MCP-session ↔ VFS-session binding.**
   Each MCP session gets one `VFSSession`. The MCP server holds
   them in a dict keyed by MCP session id. Lifecycle:
   - On MCP `initialize`, create a session, optionally apply
     defaults (per-tenant binds, per-role mounts).
   - On every MCP tool call, look up the session and call
     `s.<method>(...)`.
   - On MCP `shutdown` or disconnect, close the session.

7. **`/.mounts/` shows overlay.**
   Reading `/.mounts/` from a session shows parent + overlay
   together. A `Detail.scope` field marks each entry as
   `"global"` or `"session"` so agents can tell.

8. **`/.mounts/ctl` writes go to the overlay by default.**
   Sessions can mutate their own overlay through ctl. A
   `--global` flag on the verb (or a separate
   `/.mounts/global/ctl` path) is required to mutate the
   parent — gated by admin permission.

9. **Permission overlays.**
   A session can carry its own `PermissionMap` overlaying the
   parent's. A read-only session sees the same paths but
   can't write. This is the per-session analogue of
   `permissions=` on `add_mount`.

10. **Shadow / bind / union work per-session.**
    A session-only bind doesn't appear in another session.
    A session-only union member doesn't shadow other sessions'
    views. Tests cover concurrent sessions with deliberately
    conflicting overlays.

11. **Discoverability for agents.**
    Two affordances so agents can adapt to session-specific
    namespaces:
    - On MCP `initialize`, the response includes a snapshot of
      `/.mounts/` so the agent's first request already knows
      the mount layout.
    - The agent can `read("/.mounts/")` at any time to refresh.
    - `Detail.scope` ("global" vs "session") tells the agent
      which entries are stable across sessions vs. session-
      specific.

12. **Bookkeeping for fanout.**
    Search/glob/grep fanouts iterate over the *visible* mount
    set (parent ∪ overlay), not the parent alone. All the
    routing helpers in `base.py` take "view of mounts" as a
    parameter so a session can pass its own.

### Out

- A persistent session store (sessions survive process restarts).
  Sessions are in-memory v1.
- Inheritance graph (sessions of sessions of sessions). Two
  levels — parent + session — is enough for v1; `fork()` of a
  forked session works but the resolution cost stays bounded
  because we flatten on fork.
- Cross-session sharing of overlays. Sessions are isolated by
  construction.
- Authentication that decides what a session can mount. That
  is auth (story 028), layered on top.
- A "session" notion for non-MCP callers (CLI, scripts).
  Default behavior (no session = parent view) covers them.

## Acceptance Criteria

1. **Two concurrent sessions are isolated.** Sessions A and B
   each bind `/docs` to different sources. Reading `/docs/x`
   from A and from B returns the right thing for each, in
   parallel.

2. **`fork()` is shallow then independent.** Fork after some
   edits inherits them; later edits in the parent or the fork
   do not propagate to each other.

3. **`async with vfs.session() as s:` cleans up on exit.**
   Overlay mounts are removed when the context exits. Parent
   mounts are untouched. A test confirms `vfs.list_mounts()`
   returns the same list before and after the `with`.

4. **Default callers unchanged.** Existing `VFSClient.read(...)`
   et al continue to work and continue to see the parent
   mounts. No migration needed for non-session callers.

5. **`/.mounts/` reflects parent + overlay.** Reading it from a
   session shows both, with `Detail.scope` set.

6. **MCP session lifecycle wired.** A test MCP server creates
   one `VFSSession` per MCP session id, binds tenant-specific
   mounts on `initialize`, releases on `shutdown`. Concurrent
   MCP requests see correct per-tenant resolutions.

7. **Permission overlay works.** A read-only session denies
   writes that the parent permission map allows.

8. **Bind cycle guard respects overlay.** A bind that creates
   a cycle through an overlay is detected the same way as
   one in the parent.

9. **Search, graph, glob, grep all use session view.** Tests
   confirm fanout iterates over `parent ∪ overlay` and not
   just one or the other.

10. **`Detail.scope` round-trips through JSON.** Both global
    and session entries serialize correctly through `VFSResult`.

11. **Concurrent edit isolation.** A stress test with N
    sessions each rebinding `/docs` to N different sources
    confirms no cross-talk.

12. **`session()` is cheap.** Opening 100 sessions in a
    test takes <100ms. Closing them is similarly fast.

## Risks

- **Memory: per-session overlays cost.** Shouldn't be much —
  small dict per session — but agents-with-many-overlays
  scenarios deserve a benchmark.
- **Resolution cost: parent + overlay walk.** Today's
  `_resolve_terminal` is O(mounts). New resolver is O(parent +
  overlay). Cap by sorting once per session edit, like the
  parent does today.
- **Bind cycle guard with overlay edges.** The visited set
  needs to include overlay edges. Already accounted for in
  story 016's `(id(fs), rel)` shape.
- **Agents that cache the namespace.** An agent that
  introspects `/.mounts/` once and assumes it's stable will
  break across sessions. Mitigation: docs explicitly mark
  `/.mounts/` as session-scoped; the synthesis memo's
  capability negotiation includes `namespace.session_scoped: true`
  so agents know.
- **Search shadow filtering with overlay-only mounts.** The
  filter from 019 needs to see the overlay's higher-priority
  members. Tests cover overlay shadows.
- **`VFSClient.add_mount(...)` from non-session caller.**
  Today it mutates the parent. After this story, it still
  does — but a session caller must use `session.add_mount`
  to get session-local behavior. Documented; tests verify
  both shapes.

## Open Questions

1. **Should the session id propagate as `user_id` automatically?**
   Default: no. `user_id` is a permission concept; session id
   is an isolation concept. Both can be set.

2. **Are there default overlays driven by user role?** Default:
   pluggable via a `session_initializer` callback on
   `VFSClient`. The MCP server provides the callback;
   `VFSClient` doesn't know about MCP.

3. **How do agents discover mounts that *don't* appear in
   their session?** Default: they don't, by design. Cross-
   session visibility is a privacy hole.

4. **Should `fork()` ever flatten the overlay** (e.g., copy
   parent into overlay so further parent edits don't appear)?
   Default: no. `fork` copies the overlay only; parent edits
   continue to propagate to forks unless the fork explicitly
   shadows them.

5. **Performance: should overlay resolution use a tree, not a
   list?** Default: list with longest-prefix sort, same as
   parent. Optimize when actual session counts demand it.

## References

- `src/vfs/base.py:80, 104, 117, 143, 150` — mount table,
  add/remove, match, resolve (each grows a session-aware path)
- `src/vfs/client.py:42` — `VFSClientAsync` (gets `session()`)
- Plan 9 names paper §"Implementation of name spaces" — `rfork`
- Plan 9 from Bell Labs paper §"Command-level View" — windows
  as namespaces
- `docs/plan9-mount-namespace-recommendations.html` — Rec 05
- Story 014 §"Multi-mount semantics" — per-mount atomicity
  carries over per-session
