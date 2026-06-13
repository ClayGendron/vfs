# 034 — Design: MCP-Native Mounts

Architecture for [`spec.md`](./spec.md). Covers the mount class, the VFS-protocol
contract, the `updatedb`-style materialization, `run` dispatch, and lifecycle.

## 1. One class, two projections

`MCPFileSystem(VirtualFileSystem)` wraps a `ClientSession` exactly as a
`DatabaseFileSystem` wraps a SQL engine — the session is the storage seam, and
the parent router only ever sees public methods and `VFSResult` (story 015). It
is constructed `storage=False, allow_child_mounts=False`: a remote namespace owns
its own mount table; the parent never mounts *into* it.

`attach` is the only constructor that matters:

```python
@classmethod
async def attach(cls, session, *, name, server_url=None):
    init = await session.initialize()
    decl = (init.capabilities.experimental or {}).get(VFS_CAPABILITY)
    if decl is not None:
        return cls(session, name=name, server_url=server_url,
                   mode="vfs", capabilities=_verbs_from(decl))
    listing = await session.list_tools()
    return cls(session, name=name, server_url=server_url,
               mode="tools", tools=list(listing.tools))
```

The declaration — and *only* the declaration — chooses the projection. See §3.

## 2. The Plan 9 / Unix grounding

The design is two well-worn ideas kept apart on purpose.

- **Mount is composition, not a new world (Plan 9; constitution §1.4).** A routing
  mount composes a remote namespace into ours; the kernel device API and the 9P
  wire have the same shape, and the mount driver translates mechanically. Our
  driver is `_call_remote`: a VFS verb becomes a `tools/call`, the
  `CallToolResult` becomes a `VFSResult`.
- **Search over a remote source is an index, not live grep (`updatedb`/`locate`).**
  `locate` never walks the live filesystem; it greps a `db` that `updatedb` built
  on demand. A generic MCP server is a remote source with no search; its catalog
  is materialized into `/.agents/tools` (the `db`) by an explicit `index` pass
  (the `updatedb`). The live session stays the source of truth and the executor;
  the index is derived and refreshable.

The separation gives the two non-negotiables: **mechanism ≠ policy** (mounting is
not indexing, so `add_mount` does no I/O) and **derived data with explicit
invalidation** (the index is a cache with a clear rebuild step, never a second
*authority*).

## 3. The VFS-protocol contract

Conformance is a **declared contract**, never inferred from tool names (a generic
server's `read` tool is unrelated to ours — spec "Why"). A conforming server
promises three things:

1. **Declaration.** `initialize` returns
   `capabilities.experimental["dev.vfs.filesystem"] = {"version": "1", ...}`.
   Present ⇒ routing; absent ⇒ materializing. One field, full stop.
2. **Verb tools, bare-named.** Public verbs are tools named by the bare verb —
   `read`, `stat`, `ls`, `glob`, `grep`, `glean`, `search`, `run`, and the
   write family — **no `vfs.` prefix**. The declaration scopes them; a prefix
   would be redundant and would break "also a normal MCP server."
3. **Path in, `VFSResult` out.** Each verb tool takes VFS path/observation
   arguments and returns `VFSResult.to_payload()` as `structuredContent`, so the
   routing mount reconstructs with `VFSResult.from_payload`. `isError` ⇔
   `not success`; the `VFSErrorKind` rides in the payload (results2 already
   guarantees this round-trips).

Because the contract is declared, a routing mount's `capabilities()` is the
declared verb set (from the declaration if it lists verbs, else a baseline), and
the existing dispatch gate (`base2._capability_error`) rejects an unsupported
verb with no wire call — the no-probe rule (constitution Article 2 §2).

### Routing-mode dispatch

```python
async def _call_remote(self, op, **kwargs):
    args = {k: v for k, v in kwargs.items() if v is not None}
    res = await self._session.call_tool(op, arguments=args)   # bare verb name
    if res.is_error:
        return self._error(_text(res.content), kind=VFSErrorKind.unavailable)
    return VFSResult.from_payload(res.structured_content or {"function": op})
```

`read`/`stat`/`ls`/… are one-liners over `_call_remote`; the parent rebases the
result with `.with_mount(prefix)` as it does for any child.

## 4. Materializing mode — producer and consumer

### Producer (this story)

`tool_manifests()` is pure: it turns the cached catalog into materializable
entries, one `TOOL.md` per tool, addressed by `tool_manifest_path`.

```python
def tool_manifests(self) -> list[tuple[Path, str]]:
    return [(tool_manifest_path(t.name), self._render(t)) for t in self._tools.values()]
```

Each `TOOL.md` is **self-describing plain text** — the searchable surface plus
provenance so `run` can find its way home:

```markdown
---
name: clone_repo
provider: github
server: mcp+https://nonvfs.example.com/mcp
---

Clone a GitHub repository into the workspace.

## Arguments

```json
{ "type": "object", "properties": { "repo": { "type": "string" } }, "required": ["repo"] }
```
```

The manifest is `kind="file"` (the unit directory `/.agents/tools/clone_repo` is
`kind="tool"`), so the normal chunk→index pipeline makes its name, description,
and arguments grep/glean-able with zero special handling.

### Consumer (deferred — needs a storage backend)

`parent.index(provider)` is the `updatedb` pass:

1. pull `provider.tool_manifests()`,
2. `write` each into the parent's `/.agents/tools` storage (chunk + index follow),
3. **reconcile**: add new, update changed, hard-delete tools that vanished —
   idempotent, and the natural landing point for MCP `tools/list_changed`.

Unmount hard-deletes the provider's `/.agents/tools/<provider>` subtree.

## 5. `run` dispatch — two tiers

`run /.agents/tools/<…>` routes (via `base2._route_single`) to the parent storage
that owns `/.agents`, whose run impl:

1. reads the target `TOOL.md` provenance (`provider`, `server`, source `name`),
2. **fast path:** if that provider's session is registered live, call
   `provider.call(name, arguments)`,
3. **resilient path:** else reconnect from `server` and call — so a cold daemon
   or a stateless CLI still runs, and the index is never a dangling pointer.

`call` is the execution primitive on the provider:

```python
async def call(self, tool_name, arguments=None) -> VFSResult:
    res = await self._session.call_tool(tool_name, arguments=arguments or {})
    text = _text(res.content)
    if res.is_error:
        return self._error(text or f"Tool {tool_name!r} failed",
                           kind=VFSErrorKind.unavailable, path=tool_path(tool_name))
    return VFSResult(function="run",
                     observations=[Observation(path=tool_path(tool_name), kind="tool", content=text)])
```

[NEEDS CLARIFICATION: `tools/call` `structuredContent` is richer than text — does
the run result keep it (a new `Observation`/`VFSResult` slot), or render to text
for v1?]

## 6. Lifecycle

| Step | Effect | I/O? |
|---|---|---|
| `attach(session)` | initialize, read declaration, fix projection, cache catalog | one round-trip |
| `add_mount(provider)` | pure mount-table update (+ register for run dispatch) | **none** |
| `index(provider)` | pull catalog → write/reconcile `/.agents/tools` → chunk+index | yes (explicit) |
| `run /.agents/tools/<…>` | resolve provenance → live session or reconnect → `call` | yes |
| `remove_mount(provider)` | drop session; hard-delete materialized subtree | yes |

`add_mount` staying pure is the mechanism/policy line (§2); `index` is the only
place catalog I/O happens.

## 7. Build order

1. **Producer + execution core** (this increment): `attach`, `capabilities()`,
   `tool_manifests()`, `call()`, routing `_call_remote`/verbs — duck-typed
   session, `mcp` types under `TYPE_CHECKING` only, **no runtime `mcp` dep**,
   tested against a fake session.
2. **Transport** (`connect(url)` for `mcp+http(s)://`/`mcp+stdio://`) + the `mcp`
   optional dependency group.
3. **Consumer** (`parent.index`, run-dispatch registry, unmount cleanup) — lands
   with the `base2` storage backend.
4. **Refresh** on `tools/list_changed` (re-`index`) and resource subscriptions.

## 8. Roads not taken

- **Tool-name / schema sniffing** to detect a VFS server — rejected: names are
  not a contract; only the declared field is authoritative (spec "Why").
- **`vfs.` tool prefix** — rejected: the declaration already scopes the verbs, and
  a prefix breaks "a VFS server is also a normal MCP server."
- **Live grep across the wire** for a generic server — rejected: search needs the
  parent's chunks, so materialize (the `updatedb` model) rather than proxy.
- **Implicit materialization inside `add_mount`** — rejected: fuses mechanism and
  policy and hides network I/O in a table update; `index` is explicit.
- **A second live `/<provider>` subtree alongside the index** (topology option 2)
  — rejected: it duplicates *authority*. One canonical address per tool in
  `/.agents/tools`; the live session is the executor, not a parallel namespace.
