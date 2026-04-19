# MCP Specification — Influences for VFS and FSP

> Reference repo: `/Users/claygendron/Git/Repos/modelcontextprotocol`
> Latest stable spec: 2025-11-25; draft in progress

## Overview

The Model Context Protocol (MCP) is a JSON-RPC 2.0 protocol that enables LM agents to discover and invoke tools, consume resources, and request sampling on a stateful host. It enforces capability negotiation during initialization, models operations as either agent-controlled (Tools), host-controlled (Prompts), or host-driven context (Resources), and has evolved since November 2024 to include pagination, task-augmented execution, and elicitation (server-initiated user prompts). FSP layered directly on MCP is the wire spec for file system operations; VFS is the persistence library that shapes the object model FSP serializes.

## Navigation Guide

The spec repo is versioned by release date (2024-11-05, 2025-03-26, 2025-06-18, 2025-11-25) plus `/draft` for in-progress work. Entry points:

- **Spec sources**: `/docs/specification/{version}/` (MDX files, rendered at modelcontextprotocol.io)
- **TypeScript schema**: `/schema/draft/schema.ts` — the source of truth; schema.json is auto-generated
- **SEP process**: `/docs/seps/` — 31+ enhancement proposals; governance at `/GOVERNANCE.md`
- **Core concepts**: Start with `/docs/specification/draft/basic/lifecycle.mdx`, then `/server/` and `/client/`
- **What to skip**: SDK implementations, blog posts, tutorial code. Focus on spec docs and schema.

## File Index

| Path | Purpose |
|------|---------|
| `/docs/specification/draft/basic/index.mdx:25–244` | Messages, auth, JSON schema usage, `_meta` field, icon handling |
| `/docs/specification/draft/basic/lifecycle.mdx:41–200` | initialize, initialized, capability negotiation (roots, sampling, elicitation, tasks) |
| `/schema/draft/schema.ts:225–320` | JSON-RPC error codes: PARSE_ERROR (-32700), INVALID_REQUEST, METHOD_NOT_FOUND (-32601), INVALID_PARAMS, INTERNAL_ERROR; URL_ELICITATION_REQUIRED (-32042) |
| `/docs/specification/draft/server/tools.mdx:1–250` | Tool discovery (tools/list, pagination), tool invocation (tools/call), list-changed notifications, inputSchema/outputSchema as JSON Schema, tool names (1–128 chars, alphanumeric + `_-.`) |
| `/docs/specification/draft/server/resources.mdx:1–180` | Resource URIs, resources/list, resources/read, resource templates (URI templates RFC 6570), subscriptions, list-changed |
| `/docs/specification/draft/server/utilities/pagination.mdx:1–101` | Cursor-based pagination (opaque tokens, server-determined page size), `nextCursor`, invalid cursors = INVALID_PARAMS |
| `/docs/specification/draft/basic/transports.mdx:20–160` | stdio (newline-delimited JSON), Streamable HTTP (POST/GET with SSE), session management, resumability, DNS rebinding protection |
| `/docs/specification/draft/client/sampling.mdx` | Server-initiated sampling requests; client approves tool use and context inclusion |
| `/docs/specification/draft/client/roots.mdx` | Server inquiries into host filesystem roots (read-only, user-defined scope) |
| `/docs/specification/draft/client/elicitation.mdx` | Server-initiated forms and URL-based credential requests (form mode, URL mode) |
| `/docs/specification/draft/basic/utilities/progress.mdx` | Progress notifications via `progressToken` in `_meta` |
| `/docs/specification/draft/basic/utilities/tasks.mdx` | Task-augmented requests (async ops returning CreateTaskResult immediately, polled via tasks/list) |
| `/schema/draft/schema.ts:410–593` | InitializeRequestParams, InitializeResult, ClientCapabilities, ServerCapabilities (experimental, roots, sampling, elicitation, tasks, extensions) |
| `/docs/seps/` | ~31 enhancement proposals; browse 1024 (client security), 1036 (URL elicitation), 1046 (OAuth), 1303 (input validation), 1577 (sampling with tools), 1613 (JSON Schema 2020-12) |

## Core Concepts (What They Did Well)

**1. Capability Negotiation is Mandatory and Transactional**  
Initialize establishes an explicit handshake: client declares (roots, sampling, elicitation, tasks, extensions), server declares (tools, resources, prompts, logging, tasks). No capability = METHOD_NOT_FOUND. This is load-bearing for security (consent-driven, not discovery-driven) and enables forward compatibility (ignore unknown capabilities gracefully).

**2. Three Orthogonal Primitives with Clear Control Flow**  
Tools (model-controlled) ≠ Prompts (user-controlled) ≠ Resources (host-controlled). The control hierarchy is explicit in the spec and enforces the right mental model: agents invoke tools, users select prompts, the host surfaces resources. This prevents scope creep (don't jam file reads into prompts; don't expose tools as resources).

**3. Pagination is Unbounded and Cursor-Opaque**  
A server can page results without exposing a page size or structure. Clients must treat cursors as opaque tokens and never assume `null`/empty string means "no more results" — only `nextCursor` presence signals continuation. This is robust against server implementations that change page strategy mid-session.

**4. Error Codes Are Semantic, Not Prescriptive**  
The spec defines 5 standard JSON-RPC codes (PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS, INTERNAL_ERROR) plus one MCP extension (URL_ELICITATION_REQUIRED). INVALID_PARAMS covers unknown tool, invalid tool args, invalid cursor, malformed schema — the error *data* field is where semantic detail lives. This avoids explosion of error codes while keeping responses actionable.

**5. `_meta` is a Reserve Field for Protocol Extensions**  
Both requests and responses can attach `_meta` (MetaObject for notifications, RequestMetaObject with `progressToken` for requests). Prefix rules (reverse DNS, second-label `modelcontextprotocol`/`mcp` reserved) prevent collisions. OpenTelemetry trace context (traceparent, tracestate, baggage) rides in `_meta`. This is how progress notifications, task tokens, and future extensions stay out of the core schema.

**6. Lifecycle is Three Phases with Strict Ordering**  
Initialize (capability exchange), Initialized notification (server prepares), Operation (normal requests/responses), Shutdown (implicit, no explicit close in base protocol). The client **MUST NOT** send non-ping requests before initialize response; the server **MUST NOT** send non-ping/non-logging before initialized. This prevents race conditions and makes capability mismatches fail fast.

**7. Tasks Are Async-as-a-Primitive, Not Polling Theater**  
A request with `task: { name: string }` returns immediately with CreateTaskResult (task ID, status=pending), and results are retrieved via tasks/list or tasks/result. This is better than "fire off the request and poll in a loop" because the server controls status transitions and can batch multiple result retrievals. Task-augmented execution is negotiated per-request-type (sampling/createMessage, elicitation/create, tools/call).

**8. Transports Are Pluggable (stdio + Streamable HTTP)**  
stdio is the baseline (newline-delimited JSON on stdin/stdout); Streamable HTTP with SSE allows long-lived server deployments. Both are stateful sessions with resumability (SSE Last-Event-ID), and both require DNS rebinding protection on HTTP. The abstract Message concept makes custom transports viable.

## Anti-Patterns & Regrets

**1. Resource Templates as a Partial Solution**  
Resources/templates use URI templates (RFC 6570) for parameterization, but the spec does not mandate how arguments map to completion APIs or validation. This has led to inconsistency — some servers treat templates as "list and instantiate," others as "discovery hints." A tighter binding between template variables and completion/argument schema would have prevented ad-hoc workarounds.

**2. Elicitation Design Sprawl (Form vs. URL modes)**  
Form mode (structured field elicitation) and URL mode (out-of-band credential requests via browser) coexist without a unified model. Clients must implement both; servers must choose. SEP-1036 (URL elicitation) arrived mid-flight and feels bolted-on. The spec should have unified them under a single "elicitation request" type with mode variants.

**3. Tool Argument Validation is Underspecified**  
Tools declare `inputSchema` as JSON Schema, but the spec does not mandate validation failure behavior (reject at call time vs. pass through and let the tool report). SEP-1303 (input validation errors as tool execution errors) is a post-hoc clarification. Server implementations vary; FSP/VFS must enforce consistent validation before the tool runs.

**4. Sampling Context Inclusion (`includeContext`) is Deprecated But Not Removed**  
Early versions of sampling had an `includeContext` parameter (none, system, assistant) to control what context the LLM sees. Tool-use support made this redundant, but clients still negotiate `sampling.context` capability for backwards compat. Specs accrete; incomplete deprecation creates confusion.

**5. No Built-in Caching or Content Addressing**  
MCP provides `icons` (URIs), `_meta` (arbitrary), and `title`/`description` (free text), but no standard content hash, versioning, or cache headers. This forces clients to re-fetch resources on every session or implement custom caching. A `ETag`/`Last-Modified` analog in the protocol would reduce load on stateless servers.

**6. Task-Augmented Execution Came Late and Is Sparse**  
Tasks are a 2025-11-25 addition that only covers sampling and elicitation requests, not tools/call. The spec notes `execution.taskSupport` on tools (forbidden, optional, required), but tooling and adoption are minimal. Servers that want async behavior have to roll their own; VFS needs to decide whether to expose this or hide it.

**7. Extensions Lack a Discovery Mechanism**  
Clients declare `extensions: { [key: string]: JSONObject }` in capabilities, servers can see them, but the spec does not mandate extension listing. Servers can't query "what extensions does this client support?" without post-hoc negotiation. This is fine for 1:1 integrations but scales poorly.

## Implications for VFS (Implementation)

1. **Object Model and Serialization**  
   VFS's `Entry` (path, kind, size_bytes, content, lines, score, in_degree, out_degree, updated_at) must serialize cleanly to MCP's `TextContent` / `BlobResourceContents` types. Each Entry field maps to a Tool result or Resource read: `content` → text field, `lines` → matched regions, `score` → ranking annotation in `_meta`. Implement `Entry.to_mcp_content()` and `VFSResult.to_mcp_tool_result()` converters early.

2. **Error Taxonomy and User Scoping**  
   VFS's five-class error model (NotFoundError, MountError, WriteConflictError, ValidationError, GraphError) must map cleanly to MCP's INVALID_PARAMS / INTERNAL_ERROR / METHOD_NOT_FOUND. Implement a `_classify_mcp_error()` that mirrors `_classify_error()` — same logic, different code constants. User scoping (user_id parameter) should flow through as a `_meta` field so FSP can enforce per-user quotas or audit logging later.

3. **Mount Routing and Roots**  
   VFS mounts can surface as MCP `roots` (server → client): `/data` (DatabaseMount), `/local` (LocalFileSystem), etc. Implement `list_roots()` that queries `_mounts` and returns `Root` objects (uri, name). The `uri` should be something like `file:///data` or `database://catalog/schema`. This lets the client understand the namespace topology without asking for a full `ls /`.

4. **Pagination Must Surface Through Results**  
   If a glob or grep returns 10k entries, the router should cap at 1000 and return a `nextCursor`. VFSResult needs a `cursor: str | None` and `next_cursor: str | None` field. Implement cursor handling in the base router so all operations inherit it. A cursor encodes (function, path_filter, offset) — keep it opaque in the API but stable across sessions (no timestamps).

5. **Permissions and Consent**  
   VFS's `PermissionMap` (directory-prefix overrides) should inform tool capability negotiation. If `/private` is read-only, `tools/list` should not offer write/delete tools for that prefix. Implement `describe_accessible_tools()` that respects the permission map. This is the VFS analog of MCP's "users must consent before tool invocation."

6. **Progress and Long-Running Ops**  
   glob/grep on a large dataset might take seconds. Implement `_meta.progressToken` handling: when a request includes `progressToken`, the router can emit `notifications/progress` with the token. VFSResult should carry progress metadata so FSP can emit these notifications on behalf of the underlying VFS.

7. **Task Support (Future)**  
   Don't expose task augmentation yet (too new, too sparse), but design VFSResult with a `task_id: str | None` field so a future version can return CreateTaskResult instead of blocking. The async polling backend is already there in the routing layer; just needs the wrapper.

## Implications for FSP (Protocol)

1. **Which Ops Are Tools, Which Are Resources**  
   FSP must decide: is `read /path` a Tool (model-driven, model chooses what to read) or a Resource? Is `write /path` a Tool? Guidance from MCP:
   - **Tools**: Mutating ops (write, delete, move, mkdir, edit). Model-controlled, require consent, expect tool arguments (path, content, overwrite flag). Implement as `tools/call` with name `fs_write`, `fs_delete`, etc.
   - **Resources**: Non-mutating data (read, stat, ls output, glob results). Host-driven context, surfaced via `resources/read` with URIs like `file:///workspace/path`. But *within* a tool result, the same Entry shape appears (model sees the mutation outcome).
   - **Prompts**: Templated workflows ("analyze this directory," "refactor this function") that guide the model through a series of tool calls. Low priority for FSP 0.0.1, but the schema should allow it.

2. **URI Scheme and Roots**  
   FSP should use `file://` scheme for local paths (RFC 3986 §3.2.1) with optional authority (e.g., `file://localhost/absolute/path` or just `file:///absolute/path`). Mount points become roots: `file:///data/`, `file:///local/`. Implement `roots/list` to advertise the namespace. Clients then understand that `file:///data/foo` is scoped to a specific mount.

3. **Tool Names and Namespace Collision**  
   FSP server exposes tools: `fs.read`, `fs.write`, `fs.glob`, `fs.grep`, `fs.stat`, `fs.ls`, `fs.mkdir`, `fs.move`, `fs.copy`, `fs.delete`, `fs.edit`. Server name is `fsp`, so the full tool path (for a proxy aggregating multiple servers) would be `fsp:fs.read`. This avoids collisions and is readable.

4. **Input Schema and Validation**  
   Each tool's `inputSchema` must declare parameters. Example (`fs.write`):
   ```json
   {
     "type": "object",
     "properties": {
       "path": { "type": "string", "description": "Absolute path to write" },
       "content": { "type": "string", "description": "File content" },
       "overwrite": { "type": "boolean", "default": false }
     },
     "required": ["path", "content"],
     "$schema": "http://json-schema.org/draft/2020-12/schema#"
   }
   ```
   FSP server must validate arguments against this schema before calling VFS. Invalid arguments → INVALID_PARAMS error with JSON Schema validation errors in `error.data`.

5. **Output Schema and Result Shape**  
   Tool results are arrays of content blocks (text, blob, image, pdf). FSP should use:
   ```json
   {
     "type": "object",
     "properties": {
       "content": {
         "type": "array",
         "items": {
           "oneOf": [
             { "type": "object", "properties": { "type": { "const": "text" }, "text": { "type": "string" } } },
             { "type": "object", "properties": { "type": { "const": "blob" }, "mimeType": { "type": "string" }, "data": { "type": "string" } } }
           ]
         }
       }
     },
     "$schema": "http://json-schema.org/draft/2020-12/schema#"
   }
   ```
   Implement a `VFSResult.to_tool_result()` converter that emits this shape.

6. **Pagination in Tool Results**  
   A `glob /workspace/**/*.py` might match 50k files. FSP should truncate at 1000 results and include a `_meta.nextCursor` field, not a top-level pagination object (MCP tools don't have built-in pagination — that's for list/resource operations). The cursor encodes the continuation point; the client can issue another `fs.glob` with `cursor` parameter to fetch the next page.

7. **Error Codes and Semantics**  
   Map VFS errors to MCP codes:
   - NotFoundError → INVALID_PARAMS (code -32602, "path not found")
   - ValidationError (path too long, invalid chars) → INVALID_PARAMS
   - WriteConflictError (permission denied, file exists, write failed) → INVALID_PARAMS with `error.data = { reason: "permission_denied" | "already_exists" | "write_failed" }`
   - MountError (no mount for path) → INVALID_PARAMS ("path does not resolve to any mount")
   - GraphError (cycle, missing node) → INTERNAL_ERROR

8. **Capability Negotiation and Feature Flags**  
   FSP server declares:
   ```json
   {
     "capabilities": {
       "tools": { "listChanged": true },
       "resources": { "listChanged": true },
       "logging": {}
     }
   }
   ```
   If a client doesn't declare `sampling` support, the server should not make sampling requests (e.g., for "suggest a refactoring"). If a client doesn't declare `roots`, don't advertise roots in list/resources. This is forward-compat insurance.

9. **Notifications and Mount Changes**  
   When a mount is added/removed at runtime, FSP should emit `notifications/tools/list_changed` (if the set of available operations changes, e.g., a read-only mount is unmounted). Clients re-fetch tools/list and discover the new namespace.

10. **Progress and Async Operations**  
    Glob/grep on a large corpus could take 10+ seconds. If the client's initialize response includes `capabilities.sampling` (or a new async capability), FSP can emit `notifications/progress` with partial results, allowing the model to see incremental results. This is a 2026+ feature but should be baked into the schema shape now.

11. **Authentication and Transport**  
    FSP is currently stdio-based (0.0.1 is a CLI server). If HTTP transport is added, implement MCP's Authorization header protocol (Bearer token, OAuth client credentials via SEP-1046). Emit `URLElicitationRequired` (-32042) if auth fails, allowing out-of-band credential collection.

12. **Version Management and SEPs**  
    FSP is unstable (0.0.1); compatibility is not a promise yet. As features land, track them via SEP-style enhancement proposals (if the mcp repo process is adopted) or internal ADRs. The goal: FSP eventually reaches 1.0 with a stable wire protocol.

## Open Questions

1. **Task Augmentation for Tools**  
   Should `fs.write` support task-augmented execution? If yes, writing a 10MB file returns CreateTaskResult immediately, and progress is polled via tasks/result. If no, writes are synchronous and timeout on large files. Unclear which direction VFS/FSP should take given task support is 1-month-old in the spec.

2. **Resource Templates vs. Tool Arguments**  
   Should glob/grep be Resources (templates: `file:///{pattern}`) or Tools (`fs.glob` with argument `{ pattern: string }`)? MCP docs suggest Tools for model-driven actions, but glob/grep are discovery operations (resource-like). The spec doesn't forbid both; FSP should pick one and document why.

3. **Per-User Quotas and Audit Logging**  
   VFS has `user_id` scoping; MCP doesn't have a standard user context field. Should FSP emit a `_meta.user_id` field on all responses? Should authentication and user info be part of the Transport layer (HTTP headers) or the Protocol layer (initialize params)? This affects how FSP enforces per-user rate limits.

4. **Content Hashing and Cache Invalidation**  
   VFS computes content hashes; MCP doesn't standardize them. Should FSP include `_meta.contentHash` or an `x-fsp-etag` extension? If so, clients could cache tool results keyed by hash and avoid re-fetching unchanged paths.

5. **Symlinks and Connections**  
   VFS has a connections graph (`/path/.connections/type/target`). Should this surface as a Tool (list_connections, add_connection) or as Resource metadata (_meta field on Entry)? The spec has no guidance; FSP needs to decide.

## Anti-Patterns to Avoid

1. **Don't conflate Tool results with Resource contents.** A resource/read should return the full file content; a tool/call for fs.read should also return content, but in a Tool result wrapper. Keep them aligned in shape but separate in transport.

2. **Don't use error codes for non-error conditions.** If a path doesn't exist, return INVALID_PARAMS, not METHOD_NOT_FOUND. METHOD_NOT_FOUND is for "this operation isn't supported" (capability-level), not "the argument is bad" (parameter-level).

3. **Don't invent tool names that clash with filesystem commands.** Use namespaced names like `fs.read`, `fs.write`, not `read`, `write`. This prevents collisions when FSP is aggregated with other servers.

4. **Don't make cursors human-readable.** A cursor is opaque; base64-encode (function, offset, filters) and clients will never try to parse or manipulate them. This gives you freedom to change the cursor format later.

5. **Don't emit list_changed notifications spuriously.** If a resource is modified but the list is unchanged, don't emit tools/list_changed. Clients will re-fetch the entire list unnecessarily, defeating pagination.

## Summary for Contributors

Covered: MCP lifecycle (initialize → operation → shutdown), capability negotiation and how it gates optional features, the three primitives (Tools, Resources, Prompts) and their control models, JSON-RPC framing (requests, responses, notifications), error codes (5 standard + URL_ELICITATION_REQUIRED), pagination (cursor-opaque, server-determined page size), transports (stdio, Streamable HTTP with SSE), and extensions via _meta. Skipped: SDK implementations, internal tooling, SEP-1024 through -2149 (too many; picked representatives). Surprising: Task-augmented execution is entirely new (Nov 2025) and only covers sampling/elicitation, not tools; elicitation has two modes (form, URL) without a unified mental model. Open: whether FSP tools should support task augmentation, whether glob/grep are Tools or Resources, how to handle per-user quotas without extending the protocol.

