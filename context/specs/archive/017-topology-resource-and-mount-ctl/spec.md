# 017 — Topology Resource (`/.mounts/`) and Mount Ctl

- **Status:** draft — the programmatic `list_mounts()` half is
  superseded by 068's `mounts()`/`MountInfo` (landed 2026-07-11); the
  synthetic `/.mounts/` file tree and ctl-file write surface stay
  parked (the admin surface is deliberately not part of the namespace).
- **Date:** 2026-05-02
- **Owner:** Clay Gendron
- **Kind:** feature · introspection · FSP surface
- **Depends on:** 015 (router-public-api), 016 (namespace cleanup)
- **Enables:** 018, 019, 020 (bind, unions, remote backends all
  appear in the topology view; ctl is the single mount-mutation surface)

## Intent

Make mount topology a **first-class, readable, writable resource
inside the namespace itself.** Today there is no way for a caller
(Python introspector, MCP agent, ops tool) to ask the router
"what is mounted where?" Topology lives only inside `_mounts`.

Plan 9's answer: synthesize files. `/proc/N/status` is "what is
this process doing?"; `/net/cs` is "what networks can I reach?".
Apply the same pattern to mounts.

This story ships:

- **`list_mounts()` public API on `VirtualFileSystem`** — values
  in, values out, JSON-serializable.
- **`/.mounts/` synthesized read-only tree** — one directory per
  mount, with files for `root`, `backend`, `flags`, `permissions`,
  `status`. The router serves these without storage.
- **`/.mounts/ctl` writable surface** — textual verb dispatch
  (`mount`, `unmount`, `bind`) parsed by a `Cmdtab`-shaped table.
- **`add_mount` / `remove_mount` become thin wrappers around a
  ctl write.** Python and MCP/FSP go through one code path.
- **MCP tools `fs.mount.list / .add / .remove`** land as direct
  consumers of the same surface.

## Why

- **Discoverability.** A new agent session today has to be told
  out-of-band what's mounted. After this story it does
  `read("/.mounts/")` to find out.
- **Symmetry.** Currently Python can mount; FSP cannot. Anything
  Python does should also be doable over the wire. One ctl
  surface gets us there with no second implementation.
- **Subscribability.** Once `/.mounts/` is a tree, MCP
  `notifications/resources/updated` on a path under it becomes
  the natural event for "topology changed." Graph caches and
  search indexers subscribe; everything else stays simple.
- **Operability.** A mount that fails to come up should be
  visible as `status: "error: ..."` in `/.mounts/<path>/status`,
  not buried in a Python exception that nobody saw.
- **Foundation.** Stories 018 (bind), 019 (unions), 020
  (remote backends) all need a place to be visible. The
  topology resource is that place.

## Scope

### In

1. **`MountInfo` value type.**
   ```python
   @dataclass(frozen=True)
   class MountInfo:
       path: str
       backend_uri: str           # "database://...", "bind:///dump"
       flags: MountFlag           # REPL today; richer post-019
       permissions: PermissionMap
       storage: bool              # False for VFSClient routers
       status: Literal["ok", "starting", "error", "unmounted"]
       error: str | None = None   # populated when status == "error"
   ```
   JSON-serializable. No callables, no engines.

2. **Public `list_mounts()`.**
   ```python
   def list_mounts(self, *, recursive: bool = False) -> list[MountInfo]:
       """Snapshot. Recursive=True walks nested routers."""
   ```

3. **Backend `uri()` method.**
   Every `VirtualFileSystem` subclass implements `uri() -> str`.
   `DatabaseFileSystem` returns
   `database://<engine.url>?schema=<schema>`. The default impl
   on the base class returns
   `inproc://<class.__name__>/<id(self):x>` for backends that
   haven't overridden it (good enough for introspection,
   not for remounting yet — that comes in 020).

4. **Synthesized `/.mounts/` tree.**
   The router serves it directly — no storage backend involved.
   Implementation hooks into the routing layer:
   - `read("/.mounts")` → directory listing of mount paths
     (URI-encoded for filesystem-safe filenames)
   - `read("/.mounts/<encoded>")` → directory listing of that
     mount's metadata files (`root`, `backend`, `flags`, ...)
   - `read("/.mounts/<encoded>/root")` → the absolute mount path
   - `read("/.mounts/<encoded>/backend")` → the backend URI
   - `read("/.mounts/<encoded>/flags")` → human-readable flags
   - `read("/.mounts/<encoded>/permissions")` → permission map
   - `read("/.mounts/<encoded>/status")` → status string
   - `glob("/.mounts/**")` works
   - `stat` on any of the above returns synthetic metadata

   These are read-only paths. Writes return `permission denied`.
   The one writable path is `/.mounts/ctl`.

5. **Writable `/.mounts/ctl`.**
   ```text
   mount   <path> <backend-uri> [flags=<flags>] [perms=<perms>]
   unmount <path>
   bind    <source> <target>    [flags=<flags>]
   ```
   Parsed by a `Cmdtab`-shaped dispatcher (the lib9p shape).
   Each verb is one row; adding a verb is one row added.
   `respondcmderror`-shaped errors echo the bad input back.

6. **`add_mount` / `remove_mount` route through ctl.**
   ```python
   async def add_mount(self, path, fs, *, flags=MountFlag.REPL,
                       permissions=None) -> None:
       cmd = (f"mount {shlex.quote(path)} {fs.uri()} "
              f"flags={flags.name}"
              + (f" perms={permissions.name}" if permissions else ""))
       await self._write_mounts_ctl(cmd.encode())
   ```
   Same for `remove_mount`. The Python API stays — only its
   internal implementation flips. Tests written against the
   public API don't change.

7. **MCP tool surface.**
   `fs.mount.list` → `read("/.mounts/")` plus a small projection.
   `fs.mount.add` → `write("/.mounts/ctl", ...)` with mount verb.
   `fs.mount.remove` → `write("/.mounts/ctl", ...)` with unmount verb.
   Implemented as one-line proxies; FSP carries no mount-specific
   message types.

8. **Subscription notifications.**
   Each successful ctl write emits an MCP-style
   `notifications/resources/updated` for `/.mounts/`. Subscribers
   choose whether to refresh.

### Out

- The actual `bind` semantics — story 018 implements `BindFS` and
  the bind verb dispatch lands then. The `bind` verb in the ctl
  table is a stub returning `not yet implemented` until 018 ships.
- Union flags semantics — story 019. The `flags=` parameter is
  parsed and stored but only `REPL` is honored until 019 ships.
- Remote backend mounting — story 020 introduces `mcp+stdio://`,
  `mcp+http://` URI schemes. Until 020 ships, the ctl `mount`
  verb only knows how to construct in-process backends from
  registered URI prefixes (`database://` etc.).
- Auth on the ctl surface — story 023 (per-session) or 028
  (auth) handles permission to mutate topology.
- `/.mounts/` writes from agents — restricted to admin role
  initially. The synthesized tree is readable by everyone but
  ctl is admin-only.

## Acceptance Criteria

1. **`list_mounts()` returns one `MountInfo` per mount.** Tests
   assert path, backend URI, flags, permissions, storage, status
   on a fixture with three mounts.

2. **Every backend implements `uri()`.** `DatabaseFileSystem`,
   `MSSQLFileSystem`, `VFSClientAsync`, `VFSClient` all return a
   parseable URI. Tests round-trip the URI string through `urlparse`.

3. **`read("/.mounts/")` returns a directory listing.** One row
   per mount, kind=`directory`. Encoded path is the directory
   name.

4. **`read("/.mounts/<encoded>/<file>")` returns the synthesized
   value.** All five files (`root`, `backend`, `flags`,
   `permissions`, `status`) read correctly. `stat` returns
   reasonable synthetic metadata.

5. **`write("/.mounts/ctl", "mount /x database://...\n")` adds the
   mount.** Subsequent `list_mounts()` includes it. Subsequent
   `read("/.mounts/x/...")` returns its metadata.

6. **`write("/.mounts/ctl", "unmount /x\n")` removes the mount.**
   Verifies symmetry with `remove_mount`.

7. **Multi-line ctl writes.** Three verbs in one write run in
   order. Failure on line 2 is reported as one error referencing
   line 2 only; lines 1 (already executed) is not rolled back,
   line 3 is not run.

8. **`add_mount` / `remove_mount` go through ctl.** Trace the
   internal call path in tests; assert exactly one call to
   `_write_mounts_ctl` per public-API call.

9. **MCP tool fixtures pass.** A test MCP server fronts a
   `VFSClient`, `tools/call fs.mount.list` returns the expected
   structured payload, `tools/call fs.mount.add` reflects in
   `list_mounts()`.

10. **Bad ctl input echoes back.**
    `write("/.mounts/ctl", "frobnicate /x\n")` returns
    `MountError(InvalidVerb)` with message
    `unknown verb: "frobnicate /x"`. The exact bad line appears
    in the error.

11. **Notifications fire.** A test subscriber to
    `/.mounts/` receives one `resources/updated` event per
    successful ctl write.

12. **No public behavior regression.** All existing tests pass.

## Risks

- **Path encoding for mount paths in the synthesized tree.**
  `/tenants/acme/docs` becomes `tenants%2Facme%2Fdocs/` as a
  filename. Document the encoding; don't try to be clever.
- **Locking for ctl writes.** Concurrent `mount` calls must be
  serialized so the mount table doesn't tear. Single
  `asyncio.Lock` on the router is sufficient — mount mutations
  are rare.
- **Status accuracy.** "ok" is straightforward; "error" requires
  catching backend startup exceptions and stashing them. Status
  reporting is best-effort; don't over-engineer it.
- **`/.mounts/` shadowing real paths.** If a user mounts
  something at `/.mounts/`, conflict. Reserve `/.mounts/` and any
  `/.*` prefix for synthetic resources. Document; refuse the mount
  with `MountError(InvalidPath)`.

## Open Questions

1. **Should `/.mounts/` be `/.fsp/mounts/`** so we have a
   namespace for future synthetic resources (`/.fsp/sessions/`,
   `/.fsp/health/`)? Default: yes, but this story keeps it simple
   at `/.mounts/` and renames in 020/023 if pressure builds.

2. **Should permissions for ctl be a per-mount thing
   (`/.mounts/<encoded>/ctl`) instead of router-global
   (`/.mounts/ctl`)?** Default: router-global; per-mount ctl
   writes operate on that one mount's settings (re-flags,
   re-perms) — that's its own feature.

3. **Should `MountInfo` include a `created_at` timestamp?**
   Default: yes, helps debugging.

4. **`status: "starting"` for async-init backends?** Default:
   yes once 020 lands. For now everything starts synchronously
   and is `ok` immediately.

## References

- `src/vfs/base.py:104` — `add_mount` (gets the ctl-write redirect)
- `src/vfs/base.py:117` — `remove_mount`
- `src/vfs/base.py:143` — `_match_mount` (where the mount table is read)
- `src/vfs/__init__.py` — exports get `MountInfo`, `MountFlag`
- Plan 9 `lib9p/parse.c` — `Cmdtab` shape for the verb table
- Plan 9 source: `/sys/src/cmd/plumb/fsys.c` — full example of a
  synthesized FS with one ctl file dispatching multiple verbs
- `docs/plan9-mount-namespace-recommendations.html` — Recs 03, 04
