# FSP / VFS Synthesis — Cross-Cutting Decisions from the 11 Reference Memos

> Companion memo. Source memos: `2026-04-19-{plan9-and-plan9port, unix-history, freebsd, libfuse, filesystem-spec, language-server-protocol, scip, mcp-specification, mcp-python-sdk, langchain, langgraph}.md`.

## Purpose

VFS is the Python library that implements agent-first virtual file systems backed by databases. FSP is the MCP-layered wire protocol that VFS speaks. The two co-evolve: **VFS shapes what FSP can expose; FSP constrains what VFS must guarantee.** This memo pulls the 11 reference writeups into concrete decisions and a sequencing plan. It does not re-argue what those memos already settled — consult them for detail.

## Framing — three primitives, two artifacts

Every cross-cutting pattern in the corpus reduces to three primitives:

1. **Entry** — an object in a namespace (file, dir, chunk, connection, version, api). The unit of content addressing.
2. **Mount** — a namespace root backed by one `VirtualFileSystem`. The unit of routing and capability.
3. **Version** — a monotone stamp on an Entry. The unit of cache invalidation and read consistency.

And two artifacts both layers must agree on:

- **Result envelope** — `VFSResult` in the library, `FSPResult` on the wire. Same shape, serialized differently.
- **Capability map** — declared by every backend (to VFS) and every server (to FSP clients). No method is callable without a matching capability.

## Decisions

### 1. Entry carries a version stamp (Qid-inspired)

Borrowed from Plan 9's `Qid (path, vers, type)`, FreeBSD's vnode generation counter, LangGraph's `channel_versions`, LSP's `VersionedTextDocumentIdentifier`.

- Every `Entry` gets a `version: str` (monotone; backend's choice of encoding — integer, ULID, or `updated_at || content_hash`).
- Every write increments it.
- Reads may include `if_version=X` for optimistic concurrency; stale reads raise `StaleVersionError`.
- FSP exposes it verbatim on every result; clients cache `(path, version)` to skip re-stat.

**Why:** the Qid pattern is the single cheapest cache-coherency mechanism in the corpus, and FreeBSD's namecache + LSP's versioned sync both prove it scales to high-churn environments.

### 2. Content-addressable hashing is mandatory, algorithm is negotiable

- `Entry.content_hash: str` always populated for file-kind entries (required, not optional — LangChain regretted making `Document.id` optional and it never got upgraded).
- Default SHA-256, prefixed: `sha256:…`. Format stays open so we can rotate algorithms.
- Enables dedup, agent-side caching, and cross-mount identity checks.

### 3. Pagination is cursor-opaque, one direction

Borrowed from MCP spec, LSP partial results, FUSE readdir offset.

- `VFSResult.next_cursor: str | None`. Presence = more results, absence = end. Cursor is opaque to callers.
- Applies to `ls`, `tree`, `glob`, `grep`, all search ops, mount listings.
- Backends encode whatever they need into the cursor (method, offset, filter hash, sort key).
- **Explicit non-goal:** no total-count, no random seek, no backward pagination. Agents don't need it; exposing it invites O(n) lies.

### 4. Errors are semantic classes, not numeric spaces

Borrowed from LSP's measured error enum (5 codes + semantic data), MCP's `INVALID_PARAMS` with `error.data`, VFS's existing `_classify_error`.

- VFS keeps its exception hierarchy. Add: `StaleVersionError`, `WriteConflictError`, `MountError`, `CapabilityNotSupportedError`.
- FSP maps them to a small set of JSON-RPC codes and puts the semantic class in `error.data.class`:
  - `INVALID_PARAMS (-32602)` → not-found, malformed path, unknown tool, stale version
  - `INTERNAL_ERROR (-32603)` → backend failures
  - `METHOD_NOT_FOUND (-32601)` → capability not negotiated
  - `-32042` → reserved for FSP-specific (URL elicitation-style)
- Every error carries `retryable: bool` and optional `suggested_backoff_ms`.
- **Anti-pattern explicitly avoided:** exploding error code enum (LSP regret, fsspec regret).

### 5. Capability negotiation at `initialize`, no method probing

Borrowed from LSP, MCP, and LSP's own measured regret about capability sprawl.

- FSP capability tree is **narrow and operational**, not a 180-method grid like LSP. Draft v0:
  ```
  fs.read, fs.write, fs.edit, fs.delete, fs.move, fs.copy, fs.mkdir
  fs.ls, fs.stat, fs.tree, fs.glob, fs.grep
  fs.semantic_search, fs.lexical_search, fs.vector_search
  fs.graph.traverse, fs.graph.rank
  fs.query
  fs.mount.list, fs.mount.add, fs.mount.remove
  fs.watch  (reserved)
  ```
- Each capability advertises sub-flags: `{ streaming: bool, cancellable: bool, paginated: bool, atomic: bool }`.
- **Backends declare the same map to VFS** (not just FSP to clients). VFS routes based on it; unsupported ops raise `CapabilityNotSupportedError` at resolution time, not mid-operation.
- **Anti-pattern explicitly avoided:** fsspec's late-binding silent failures and LSP's 6-level deep capability paths.

### 6. Mounts are first-class in the protocol

Borrowed from Plan 9 `/srv`, FreeBSD `struct vfsops`, 9pserve multiplexing.

- FSP exposes `fs.mount.list`, `fs.mount.add`, `fs.mount.remove` as tools (when authorized) or read-only resources (otherwise).
- Each mount declares: `prefix`, `backend_type`, `capabilities`, `read_only`, `user_scoped`, `version_model`.
- Path routing is longest-prefix on the client side is fine, but the server must be the source of truth about which mounts exist.
- **No URL chaining.** `cached::s3://…` fsspec-style composition is a documented regret. We compose with explicit mount trees.

### 7. Tool/Resource split is deliberate, not decorative

Borrowed from MCP's three-primitive model and the MCP SDK memo's repeated warning.

- **Tools (model-driven, with arguments):** all CRUD, all traversal, all search, all graph ops, query engine. These are *actions* agents invoke.
- **Resources (host-driven, URI-templated):** mount topology (`fsp://mounts/{mount_id}`), `.connections/` graph (`fsp://{mount}/.connections/{type}/{target}`), `.versions/` history (`fsp://{mount}{path}/.versions/`), capability descriptor (`fsp://capabilities`).
- Resources are readable by URI, subscribable for change notifications, and cacheable.
- **Metadata is not a tool call.** An agent asking "what connections does this file have?" should `resources/read` a URI, not invoke a tool.

### 8. Namespace semantics: absolute, no symlinks, explicit edges

Borrowed from Plan 9 (no symlinks, union directories via bind), FreeBSD (explicit `nullfs`/`unionfs` stacking), SWE-agent ACI (absolute paths only).

- Paths within a mount are absolute and normalized upfront (NFC, no `..`, no repeated slashes).
- Mount prefix is *routing*, not *rewriting* — Plan 9's principle. The terminal backend sees the path relative to its root.
- **The connection graph replaces symlinks.** Connections are first-class Entries in `/.connections/{type}/{target}`, traversed via `fs.graph.traverse`. Agents see edges; no ELOOP, no "follow or not" ambiguity.
- POSIX mode bits, `chmod`, `chown`, setuid, sticky bit — all out. `PermissionMap` on mount boundaries stays.

### 9. Concurrency: versioned reads + reducer-aware writes

Borrowed from LangGraph channels, FreeBSD vnode locking, Unix history's non-atomic `namei` warning.

- **Writes serialize through the backend session.** Content-before-commit ordering (existing rule) is preserved.
- **Concurrent writes to the same path**: default is last-writer-wins with version increment. Backends may opt into reducer semantics per-path (list-append, set-union, counter-add) declared in capabilities.
- **Cross-mount writes**: never atomic, always documented. Use soft-delete + compensation when needed. Two-phase commit is explicitly not a goal.
- **Reads are snapshots.** `glob()` / `tree()` results are a point-in-time view; FSP clients that want liveness use `fs.watch` (future).

### 10. Long operations: progress now, tasks when MCP ships it

Borrowed from LSP partial results + progress, MCP tasks (2025-11-25), FUSE handle semantics.

- Phase 1 (now): `grep`, `glob`, large `tree`, all search ops support MCP progress tokens via `_meta.progressToken` and cancellation via `$/cancelRequest`. Partial results stream as `_meta.partial` notifications; final response empty on cancel.
- Phase 2 (when MCP tasks SEP stabilizes for `tools/call`): operations exceeding a server-side threshold return `CreateTaskResult`, polled via `tasks/list`. Do not adopt before the spec covers tool calls; today it only covers sampling/elicitation.

### 11. Search results share one shape

Borrowed from LangChain (scoring variants), SCIP (occurrence model), fsspec regrets (inconsistent relevance).

- Every search Entry includes `relevance_score: float` in `[0, 1]`, normalized. Backends that emit raw distances must convert. No negotiation of scale.
- Results are capped (default 50, configurable up to capability-declared max) and include a `refinement_hint` field suggesting narrower queries — SWE-agent ACI principle, not a LangChain pattern.
- `semantic_search`, `lexical_search`, `vector_search` return the same envelope. Differences live in `search_meta` (model name, distance metric, filter reducers), not in the result shape.

### 12. Serialization is pluggable, transport is not

Borrowed from LangGraph's `SerializerProtocol`, MCP's structured-content split.

- VFS serialization of object content is backend's choice (text, JSON, msgpack, pickle, protobuf). Each Entry declares `content_encoding`.
- FSP wire transport is always MCP over JSON-RPC — stdio for desktop clients, streamable HTTP for long-lived servers. No custom transports in the near term.
- `CallToolResult.structured_content` carries the typed VFSResult; `content` carries a human-readable rendering. Both populated; clients pick.

## VFS refactors (concrete)

| # | Change | Driver |
|---|--------|--------|
| 1 | Add `Entry.version: str`; backends populate; all write paths increment | Decision 1 |
| 2 | Add `Entry.content_hash: str` required for `kind="file"` | Decision 2 |
| 3 | Add `VFSResult.next_cursor: Optional[str]`; wire through `ls`, `tree`, `glob`, `grep`, search ops | Decision 3 |
| 4 | New exceptions: `StaleVersionError`, `WriteConflictError`, `MountError`, `CapabilityNotSupportedError` | Decision 4 |
| 5 | `Backend.capabilities -> FSCapabilityMap` method on every backend; VFS routes against it | Decision 5 |
| 6 | `VirtualFileSystem.list_mounts()`, `.mount_info(path)` public API | Decision 6 |
| 7 | Normalize `relevance_score` to `[0, 1]` at backend boundary; add `refinement_hint` to search Entries | Decision 11 |
| 8 | `if_version` kwarg on `read`, `edit`, `delete`, `move`; enforced at `_use_session` boundary | Decision 1 |
| 9 | `Entry.content_encoding` field; `SerializerProtocol` indirection for non-text content | Decision 12 |
| 10 | Document mount routing as "Fid-equivalent" in module docstring (pedagogical) | Plan 9 memo |

## FSP deliverables (concrete)

| # | Artifact | Driver |
|---|----------|--------|
| F1 | `fsp/schema/capabilities.py` — capability map dataclass + initialize payload | Decision 5 |
| F2 | `fsp/schema/result.py` — `FSPResult` mirroring `VFSResult`; `to_mcp_tool_result()` converter | Decisions 3, 11, 12 |
| F3 | Error mapper `fsp/errors.py` — VFS exception → JSON-RPC code + `error.data.class` + `retryable` | Decision 4 |
| F4 | Mount topology tools + resources (`fs.mount.list`, `fsp://mounts/…`) | Decision 6 |
| F5 | URI scheme registration: `fsp://{mount}/{path}` canonical form documented | Decision 8 |
| F6 | Progress/cancellation integration for `grep`, `glob`, search | Decision 10 phase 1 |
| F7 | `.connections/`, `.versions/` exposed as Resources, not tools | Decision 7 |
| F8 | Stub tool schemas for `semantic_search`/`lexical_search`/`vector_search` already exist; refit to shared result envelope | Decision 11 |

## Principles (the anti-pattern list)

- **No URL chaining** — explicit mount trees. (fsspec regret)
- **No full-graph wire encoding** — document-local, like SCIP. (LSIF regret)
- **No symlinks** — explicit connection edges. (Plan 9 choice)
- **No POSIX mode bits** — `PermissionMap` at mount boundary. (FreeBSD has it; we skip deliberately)
- **No half-async backends** — all-in or all-out per backend. (fsspec regret)
- **No capability discovery via error probing** — declare at initialize. (LSP + MCP insist)
- **No unbounded search results** — cap + refinement hint. (SWE-agent ACI)
- **No total-count pagination** — cursor presence only. (MCP + FUSE)
- **No interface churn once published** — SEP-style evolution for FSP. (LangChain regret)
- **No migration/backfill scripts** — existing policy.

## Sequencing

**Wave 1 (VFS foundation — unblocks everything):** refactors #1, #2, #3, #4, #5.

**Wave 2 (FSP skeleton — usable v0.1 of the protocol):** F1 (capabilities), F2 (result envelope), F3 (errors), F5 (URI scheme). Wire existing FSP tools through the new envelope.

**Wave 3 (Namespace surface):** VFS #6, #10; FSP F4, F7.

**Wave 4 (Long ops + search):** VFS #7, #8, #9; FSP F6, F8.

**Wave 5 (spec writing):** FSP SEP-0001 freezing capability names + result envelope + error taxonomy. Only after wave 1–3 have run in anger.

## Open questions

These were raised in multiple source memos and remain unresolved. Each needs a short decision memo before the wave it blocks.

1. **Symbol-level addressing** — is SCIP-style `(scheme, package, descriptor+)` a VFS native or an opt-in mount? (blocks wave 4)
2. **Version encoding** — integer counter, ULID, or `updated_at || content_hash`? Consistency across backends matters. (blocks wave 1)
3. **Cross-mount atomicity contract** — document "never atomic" as a hard rule, or support soft-delete + compensation primitives? (blocks wave 3)
4. **Checkpoint / history GC** — infinite `.versions/` history or TTL policy per mount? (blocks wave 3)
5. **`fs.watch` semantics** — kqueue-style notification, LSP-style `didChange` push, or absent from v0.1? (deferred — phase 2)
6. **Content hash algorithm rotation** — how do clients detect which algo was used, and how do we re-hash at scale without the migration-script ban biting us?
7. **Structured vs text MCP output** — always populate both, or let backends pick? Affects agent compatibility with non-MCP-aware clients.

## What this memo does not decide

- Auth / identity beyond user scoping (MCP OAuth SEP-1046 is in flight; revisit after).
- The query engine's language (existing `docs/plans/grover_result_refactor.md` direction holds).
- Backend-specific schemas (each backend documents its own).
- MCP transport choice at deploy time (stdio vs HTTP is a deployment concern, not a protocol concern).
