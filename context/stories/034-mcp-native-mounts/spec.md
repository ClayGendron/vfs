# 034 — MCP-Native Mounts: routing VFS servers, materializing generic tool servers

- **Status:** draft
- **Date:** 2026-06-13
- **Owner:** Clay Gendron
- **Kind:** feature + architecture
- **Depends on:** 015 (routers call public API, not impl), 020 (remote backends
  as mount targets), 017 (topology resource and mount ctl), and the `/.agents`
  tool/skill kinds + `capabilities()`/`run` router primitives landed alongside
  this story
- **Enables:** VFS as an MCP *client* — mount any MCP server into the namespace;
  generic tools become indexed, searchable files under `/.agents/tools`;
  `run` as the one execution verb

## Intent

Make VFS mount remote MCP servers as first-class members of its namespace, with
**two modes that the server itself selects by a single declared field:**

1. **Routing mount** — a server that declares it speaks the **VFS protocol** is
   delegated to: the parent forwards public verbs (`read`/`grep`/`run`/…) to the
   server and rebases the `VFSResult` it returns. Nothing is copied on mount.
2. **Materializing provider** — any other MCP server cannot answer VFS search, so
   its tool catalog is **pulled into the parent's storage** at `/.agents/tools`
   by an explicit `index` pass, where each tool becomes a `TOOL.md` file that
   chunks and indexes like any other. The live session is kept only to serve
   `run`. This is the `updatedb`/`locate` model: the session is the source of
   truth, `/.agents/tools` is its rebuilt index.

The whole inbound direction reduces to one class — `MCPFileSystem` — whose
projection is chosen at `attach` time from the server's declaration.

> This story is the inbound (client) half. The outbound half — `vfs serve`,
> exposing a `VirtualFileSystem` *as* an MCP server — is a sibling story; the two
> share the same wire contract (a VFS server is what `vfs serve` produces and
> what a routing mount consumes). [NEEDS CLARIFICATION: split into 035, or fold
> the serve direction in here?]

## Why — the friction

VFS's thesis is one namespace over many backends, with tools as discoverable
files loaded on demand. MCP is the cross-product protocol for remote tools and
resources, and `base2`'s router was already built for it: the router calls a
child mount's **public methods only** (values in, `VFSResult` out), so a remote
MCP server can sit behind the same seam as a local `DatabaseFileSystem`. What is
missing is the mount class itself and — the crux of this story — a principled
answer to **how a mount decides what kind of server it is talking to**, and
**how a server that cannot answer search still becomes searchable.**

Two facts shape the design:

- **A filesystem's search index only spans its own chunks.** A routing mount can
  answer `grep` because it delegates. A generic MCP server has no
  grep/glean/semantic-search over its tools — so the *only* way those tool
  definitions become searchable is to copy them into something that gets
  chunked: the parent's storage. You cannot index what you do not store.
- **Tool names are not a contract.** A generic MCP server may expose a tool named
  `read` whose arguments and result shape are unrelated to VFS's `read`. Calling
  it as if it were the VFS verb is a category error. Conformance to the VFS
  protocol must be a *declared* fact, never inferred from a coincidence of
  naming.

## The VFS-protocol declaration

A server announces conformance with **one field** at `initialize`:
`capabilities.experimental["dev.vfs.filesystem"]`, carrying a protocol version
(e.g. `{"version": "1"}`). That single field is the **only** signal that selects
the routing projection. VFS never infers conformance from tool names or schemas.

Consequences:

- **No `vfs.` tool prefix.** A conforming server names its verb tools by the bare
  VFS verb (`read`, `stat`, `ls`, `glob`, `grep`, `glean`, `search`, `run`, …).
  The declaration — not a naming convention — is what authorizes VFS to treat
  them as the protocol.
- **A VFS server is still an ordinary MCP server.** A non-VFS client sees
  normally-named tools and simply ignores the declaration, so a `vfs serve`
  endpoint works for everyone. (Requirement carried from the design discussion.)
- **Absence is the default.** No declaration → generic → materializing provider.

The full protocol contract a conforming server promises (verb tool names + path
arguments + `VFSResult`-shaped `structuredContent`) is specified in
[`design.md`](./design.md).

## Current state

- `base2.VirtualFileSystem` routes a child mount through its public methods;
  `capabilities()` (returns `None` = no limit) gates dispatch with an
  `unsupported` error and **no wire call** when a verb is absent; `run(path,
  *, arguments)` is the routed execution verb. (Landed with this story.)
- `paths.py` derives `kind="tool"`/`kind="skill"` from the reserved user-space
  `/.agents/{tools,skills}/<name>` grammar; `TOOL.md`/`SKILL.md` manifests stay
  `kind="file"` so they chunk and index normally; builders `tool_path`,
  `skill_path`, `tool_manifest_path`, `skill_manifest_path` exist. (Landed.)
- No `MCPFileSystem`, no `index`/materialization, no `ClientSession` wiring, and
  no storage backend in the `base2` world yet.

## Target state

- **`MCPFileSystem(VirtualFileSystem)`** wraps a `ClientSession`. `attach`
  initializes the session, reads the declaration, and fixes the projection:
  - **routing** (`vfs` mode): `capabilities()` returns the server's declared verb
    set; each verb forwards to the same-named tool and returns
    `VFSResult.from_payload(callToolResult.structuredContent)`.
  - **materializing** (`tools` mode): `capabilities()` returns `{"run"}` only;
    `tool_manifests()` produces one `(path, TOOL.md content)` per tool for the
    `index` pass; `call(tool, args)` is the execution primitive.
- **`/.agents/tools` is a derived index.** An explicit `index` pass on the parent
  consumes `tool_manifests()`, writes/reconciles the `TOOL.md` files in the
  parent's storage, and lets the normal chunk→index pipeline make them
  grep/glean-able. Each `TOOL.md` carries **provenance** in frontmatter (provider
  id, server URL, source tool name).
- **`run` dispatches in two tiers.** `run /.agents/tools/<…>` resolves to the live
  provider session if registered (fast path), else reconnects from the
  provenance in `TOOL.md` (resilient path) — so the index is never a dangling
  pointer.
- **Lifecycle is explicit.** `add_mount` stays a pure table update (no network
  I/O); `index` is the `updatedb` step; unmount hard-deletes the materialized
  subtree.

## Scope

### In

1. `MCPFileSystem(VirtualFileSystem)` over a (duck-typed) `ClientSession`:
   `attach` + declaration-based projection; `capabilities()` per mode.
2. The **producer**: `tool_manifests()` → `(Path, str)` per tool, with provenance
   frontmatter, paths built via `tool_manifest_path`.
3. The **execution primitive**: `call(tool, arguments)` → `VFSResult` from a
   `tools/call`, mapping `isError` → `not success` and content blocks → text.
4. Routing-mode verbs (`read`/`stat`/`ls`/… ) forwarding to same-named tools and
   reconstructing `VFSResult` from `structuredContent`.
5. Real transport wiring (`connect(url)` for `mcp+http(s)://`, `mcp+stdio://`) and
   the optional `mcp` dependency group — **deferred to a follow-up increment**;
   the producer/execution core is built and tested first against a fake session.
6. The **consumer** (`parent.index`, run-dispatch registry, unmount cleanup) —
   **deferred until a `base2` storage backend exists** (it needs somewhere to
   write and index).

### Out

- The outbound `vfs serve` direction (sibling story).
- The materialization *consumer* and storage backend (named above; depends on the
  `DatabaseFileSystem` rebuild).
- Auth (OAuth/bearer) beyond noting the hook points.
- Live refresh on `tools/list_changed` / resource subscriptions (re-`index` is the
  manual equivalent for v1).
- Generic MCP **resources** (vs tools) — likely `kind="file"` reads later;
  out of scope here.

## Acceptance criteria

1. `MCPFileSystem.attach` selects **routing** iff the server declares
   `experimental["dev.vfs.filesystem"]`, and **materializing** otherwise —
   decided by the declaration alone, with no inspection of tool names.
2. A routing mount's `capabilities()` reflects the declared verb set; calling a
   verb forwards to the **same-named** tool (no `vfs.` prefix) and returns the
   `structuredContent` as a `VFSResult`.
3. A materializing provider's `capabilities()` is exactly `{"run"}`.
4. `tool_manifests()` yields one entry per tool at `/.agents/tools/<name>/TOOL.md`
   (`parse_kind` → `file`), whose content is searchable text (name, description,
   arguments) plus provenance frontmatter (provider, server, source name).
5. `call(tool, args)` issues one `tools/call`, returns a `function="run"`
   `VFSResult`, and maps a tool-level `isError` to a failed result carrying the
   error text.
6. The producer/execution core is covered by tests against a fake session, with
   **no `mcp` runtime dependency** required to import or test `vfs.mcp`.
7. (Deferred-gated) `add_mount` of an `MCPFileSystem` performs **no** network I/O;
   materialization happens only on an explicit `index` call.

## Open questions

- **Provider/tool naming under `/.agents/tools`.** Flat `/.agents/tools/<tool>`
  collides across servers; the grammar makes the unit depth-1. Encode the
  provider in the segment (`<provider>.<tool>`) or revisit the grammar to allow
  `/.agents/tools/<provider>/<tool>`? [NEEDS CLARIFICATION]
- **Declaration payload.** Is `{"version": "1"}` enough, or should the server also
  advertise its verb set and per-verb schemas in the declaration (so
  `capabilities()` needs no separate probe)? [NEEDS CLARIFICATION]
- **Resources vs tools** for a generic server — do we also materialize MCP
  resources as `kind="file"` reads, or tools only for now?
- **Run reconnect identity** — when reconnecting from provenance, how is the
  session keyed/cached, and what auth context is reused?
