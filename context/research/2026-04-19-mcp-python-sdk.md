# MCP Python SDK — Influences for VFS and FSP

> Reference repo: `/Users/claygendron/Git/Repos/python-sdk`

## Overview

The Anthropic MCP Python SDK is a production-grade server/client framework with two complementary APIs: a low-level `Server` class for handler registration and a higher-level `MCPServer` (exported as `FastMCP` elsewhere) for declarative tool/resource/prompt definition. The SDK handles transport abstraction (stdio, SSE, HTTP/Streamable), structured tool invocation with context injection, resource URIs, prompt templating, experimental task APIs, and sophisticated error handling with elicitation/sampling callbacks. For VFS and FSP: the core value is **clean separation of tool discovery from tool invocation, resource vs. tool semantics, async-first architecture, and how context flows through the call stack**. FSP already uses `MCPServer.tool()` as its sole transport to MCP; this research extracts patterns for how VFS metadata should serialize and how FSP's file ops should partition into tools vs. resources.

## Navigation Guide

**Root entry points:** `src/mcp/` contains `shared/` (types, exceptions), `types/` (MCP protocol models), `client/` (ClientSession, Client), and `server/` (the main API). **Server layers:** Low-level `server/lowlevel/server.py` (Server class, message dispatch), mid-level `server/mcpserver/server.py` (MCPServer, decorators), high-level `server/mcpserver/{tools,resources,prompts}/` (registration managers). **Transports:** `server/{stdio,sse,streamable_http,websocket}.py` + `server/session.py` (SessionMessage routing). **Do not review:** auth system (separate OAuth middleware), client experimental tasks (not yet stabilized), lowlevel.experimental (internal SPI). **Most relevant subtrees:** `server/mcpserver/tools/base.py` (Tool registration and context injection), `server/mcpserver/resources/` (Resource base class, FunctionResource lazy loading), `server/elicitation.py` (interactive form/URL elicitation), `types/_types.py` (Tool, Resource, CallToolResult schema), `client/session.py` (ClientSession message loop).

## File Index

- `src/mcp/server/mcpserver/server.py:129-200` — MCPServer init: manages tool/resource/prompt managers, lifespan, low-level Server delegation, auth config.
- `src/mcp/server/mcpserver/tools/base.py:22-89` — Tool class: function wrapping, parameter JSON schema inference, output_schema, async/sync detection, context_kwarg resolution.
- `src/mcp/server/mcpserver/tools/base.py:91-119` — Tool.run(): arg validation via Pydantic, context injection, UrlElicitationRequiredError re-raise.
- `src/mcp/server/mcpserver/resources/base.py:17-44` — Resource abstract base: uri, name, mime_type, annotations, async read() protocol.
- `src/mcp/server/mcpserver/resources/types.py:22-75` — TextResource, BinaryResource, FunctionResource: lazy-load via wrapped callable, auto-JSON serialization fallback.
- `src/mcp/server/lowlevel/server.py:101-150` — Server class: handler registration, lifespan context manager, on_list_tools/on_call_tool callbacks, InitializationOptions.
- `src/mcp/server/lowlevel/server.py:200+` — Server.run(): message dispatch loop, session management, transport binding.
- `src/mcp/server/elicitation.py:52-142` — Elicitation validation and handlers: primitive-only schema restriction, form vs. URL modes, AcceptedElicitation/DeclinedElicitation/CancelledElicitation outcomes.
- `src/mcp/server/mcpserver/utilities/context_injection.py:13-46` — Context injection: inspects function signature for Context type hint, injects via kwarg if found.
- `src/mcp/server/mcpserver/utilities/func_metadata.py:*` — FuncMetadata: Pydantic model creation from function signature, call_fn_with_arg_validation, output schema extraction (not read yet, infer from codebase).
- `src/mcp/server/session.py:*` — ServerSession: message dequeue loop, handler dispatch, notification sending, progress token tracking (key for FSP cancellation).
- `src/mcp/server/streamable_http.py:*` — Streamable HTTP transport: EventStore, one-shot vs. long-polling semantics, response routing.
- `src/mcp/server/sse.py:*` — SSE server transport: streaming content blocks, session lifecycle.
- `src/mcp/types/_types.py:*` — MCP protocol: Tool (input_schema, outputSchema, structured_content), Resource (uri, mime_type), CallToolResult (content + structured_content), progress_token, task APIs.
- `src/mcp/client/client.py:36-150` — Client high-level API: context manager, transports (in-memory, streamable-http, custom), callbacks for sampling/elicitation/logging.
- `src/mcp/client/session.py:*` — ClientSession: message router, call_tool/read_resource/get_prompt calls, sampling request handling (paired with server elicitation).
- `examples/servers/simple-tool/mcp_simple_tool/server.py:*` — Minimal lowlevel.Server example: handler functions, JSON schema inline, error raises as ValueError.
- `examples/servers/simple-resource/mcp_simple_resource/server.py:*` — Resource example: urlparse for URI extraction, hardcoded SAMPLE_RESOURCES, TextResourceContents wrapping.
- `src/mcp/server/mcpserver/exceptions.py:*` — MCPServerError, ValidationError, ResourceError, ToolError: exception hierarchy for tool/resource failures.

## Core Concepts (What They Did Well)

**1. Tool-Resource Duality:** Tools are *actions* (request → response), Resources are *state* (URI → lazy-loaded content). This is orthogonal to whether something is synchronous or async—both can be either. FSP's `read`, `write`, `edit`, etc., are clearly tools (they're action-oriented, have parameters, return results). But FSP's metadata (`.connections/`, `.versions/`, `.apis/`) could be Resources if you want clients to subscribe to them rather than poll. The SDK doesn't conflate these; it's a useful mental model for FSP to borrow.

**2. Declarative Registration via Decorators:** `@mcp.tool()` and `@mcp.resource()` extract metadata (docstrings, type hints, return types) and build protocol messages automatically. No manual JSON schema writing. For VFS: the `_impl` pattern is already imperative; MCPServer's decorator pattern is the inverse—ask VFS if a declarative wrapper over `_impl` would be cleaner for FSP's tool surface.

**3. Context Injection without Boilerplate:** The `find_context_parameter()` pattern (inspect signature for `Context` type hint, inject if present) is elegant—no explicit `ctx=request_context` plumbing needed. Relevant to VFS if you ever want FSP tools to access user scope, permissions, or request metadata. Current FSP doesn't; but it's a pattern worth knowing.

**4. Output Schema Parity with Input:** Both input (`input_schema`) and output (`outputSchema`) are first-class in the Tool protocol. Agents can discover expected return shape ahead of time. VFS's `GroverResult` already does this structurally (one unified result envelope), but FSP tools should document their output shape explicitly—not just in docstrings. **Implication:** every FSP tool should have an `outputSchema` in its MCP listing.

**5. Lazy Loading for Resources:** `FunctionResource` wraps a callable and defers execution until `read()` is called. Useful for expensive operations (fetching from a remote API, hydrating a large file). If FSP ever exposes `/database/...` or `/remote-service/...` as resources, this is the pattern to use—list them cheap, read them expensive.

**6. Async-First Architecture:** Every handler is async-native. Sync code is wrapped in `anyio.to_thread.run_sync()`. VFS's async-first design aligns perfectly. Implication: FSP's tool implementations should stay async-native or be explicit about sync-to-async bridges.

**7. Structured Error Handling with Semantics:** The five-exception hierarchy (MCPServerError, ValidationError, ResourceError, ToolError, + Pydantic validation) is tight. Errors are *semantic* (what kind of failure), not errno codes. Matches VFS's `_classify_error` design. **Implication:** FSP should extend this hierarchy for file-specific errors (NotFoundError, WriteConflictError, MountError) and preserve semantic clarity in the wire format.

**8. Elicitation and Sampling Callbacks:** Interactive form-based data collection (elicitation with schema validation) and model sampling (ask Claude to decide) are wired into the tool execution path. Not directly relevant to FSP today, but if FSP ever needs "user confirm before delete" or "model decide which mount to use", this is the API.

**9. Progress Tokens and Streaming:** Tools can issue progress notifications (via `progress_token` in CallToolRequestParams). Experimental tasks API allows returning `CreateTaskResult` instead of `CallToolResult` for long-running work. Relevant for FSP's grep/semantic_search if they become expensive—progress should be wired from the start.

**10. Transport Abstraction:** stdio, SSE, HTTP/Streamable, WebSocket all share the same Server implementation. Transport is injected at the boundary (stdio_server context manager, sse_app ASGI, streamable_http_app). FSP doesn't vary transports yet, but the pattern teaches that transport-specific code should not leak into business logic.

## Anti-Patterns & Regrets

**1. Tool vs. Resource Ambiguity in Documentation:** The SDK docs don't clearly state when to use a tool vs. a resource. "Tools are for actions; resources are for state" is *implied* but not explicit. Consequence: servers sometimes expose the same capability as both (e.g., "get_config" as a tool AND a resource), which confuses clients. **For FSP:** the File System Protocol README doesn't distinguish. `read` is clearly a tool (action), but are `.versions/` entries resources or tool results? Answer it now, document it in FSP's conceptual model.

**2. Structured Output Schema Not Enforced:** Tools can declare `outputSchema`, but the SDK doesn't validate that the actual `structured_content` matches the schema. Pydantic validation happens for inputs; it should happen for outputs too. **For VFS/FSP:** ensure GroverResult and FSPResult validation is bidirectional.

**3. Resource URI Semantics Underspecified:** The SDK says "resources have URIs" but doesn't mandate a scheme or hierarchy. Examples use `file:///path`, `http://...`, even bare strings. Clients have to parse each scheme separately. No built-in URI normalization. **For FSP:** pin URI format early. FSP paths are already hierarchical; an `fsp://` scheme would be cleaner than ad-hoc schemes per backend. **Implication:** define FSP URI syntax (e.g., `fsp://mount_name/path/to/resource`) and validate it.

**4. Context Injection Happens Late:** Context is injected *just before* function call, not at handler registration time. If a tool needs to access context to validate arguments, there's no hook—validation happens after context is available. Workaround is to do manual validation inside the tool body. **For FSP:** if you need path validation (e.g., user-scoped permission check) to happen before attempting the operation, you might need custom validation logic in the tool body, not in the JSON schema.

**5. Error Messages Leak Implementation Details:** When a Pydantic validation fails during tool invocation, the error message includes the field name and type, which is useful for humans but might be verbose for agents. No filtering or customization hook. **For FSP:** craft error messages to be agent-friendly (concise, actionable), not just human-friendly.

**6. Pagination Not Wired into Tool Results:** Tools return `CallToolResult` with a flat `content` list. Pagination is only for `list_tools`, `list_resources`, `list_prompts`. If a tool returns a very large result (e.g., `grep` on a 10k-line file), there's no pagination mechanism—the agent gets flooded. **For FSP:** cap result sets (50 items max for glob/grep, as per SWE-agent recommendations). FSP already does this implicitly (returns data + meta), but FSP should document pagination semantics clearly in the tool descriptions.

**7. Transport-Specific Bugs Hard to Diagnose:** The streamable HTTP transport has a separate `EventStore` (in-memory event queue for long-polling) that can dequeue messages out of order in rare race conditions. The stdio transport is simpler but blocks on I/O. No unified logging of transport behavior. **For FSP:** if FSP ever supports multiple transports, add transport-level logging/tracing from the start.

**8. Sampling and Elicitation Coupling:** Elicitation (user form) and sampling (LM model) are distinct, but the code paths both funnel through `ServerSession.elicit_*` and expect a callback. If a server doesn't provide the callback, requests hang silently. **For FSP:** if FSP ever needs interactive user input (e.g., credentials for remote backend), make the callback *required* at init time, not optional.

## Implications for VFS (Implementation)

**1. GroverResult Serialization:** VFS operations return `VFSResult` with `entries` (flat row shape), `function` (operation name), and metadata. MCP's `CallToolResult` has `content` (list of ContentBlock) and optional `structured_content` (JSON matching outputSchema). **Decision:** when FSP wraps a VFS operation, should the entry list become `content` (text blocks) or `structured_content` (JSON)? **Recommendation:** use `structured_content` for all FSP results. Each entry becomes a JSON object in an array, keyed by operation (glob, grep, etc.). This lets agents parse results as structured data, not text scraping. Provide a text renderer separately for human readability.

**2. Backends and Mount Routing:** VFS's `_read_impl`, `_write_impl`, etc., pattern mirrors MCP's low-level Server handler registration. If VFS gains a new backend (e.g., Redis, remote HTTP), implement the `_*_impl` methods and mount routing rebases the path. **Recommendation:** keep this pattern. It's proven and explicit. The MCPServer decorator pattern is an abstraction layer on top of the low-level Server; VFS doesn't need it—VFS *is* the abstraction layer.

**3. Permission Scoping and Context:** MCPServer has `find_context_parameter()` for injecting request context into tool functions. VFS has `user_scoped=True` to partition data per user. **Integration:** when FSP tools need to enforce user scope, they should pass the user ID from the request context (extracted by MCPServer) to VFS. **Implication:** FSP's `fs = FSP(root, user_scoped=True)` should also accept an optional `user_id` parameter in each tool call, derived from `ctx` if available.

**4. Result Metadata for Agent Cognition:** VFS results carry `kind`, `size`, `hash`, `extension`. FSP currently returns these in a flat `data` dict. **Recommendation:** ensure `GroverResult` has an `OutputSchema` defined in FSP's tool listings. Agents can then understand the schema without parsing text. Example: `read` returns `{path, kind, size, hash, content}` with full type info in the schema.

**5. Error Classification Alignment:** VFS has `_classify_error()` that maps exceptions to five classes. MCP has `MCPError` with a code/message. **Decision:** FSP should translate VFS errors to MCP errors. When VFS raises `NotFoundError`, FSP should catch it and return `MCPError(code=-32601, message="Not found")` or similar. The MCP error codes are defined in the spec; use them consistently.

**6. Graph and Connection Semantics as Resources vs. Tools:** VFS has a connection graph (`/file/.connections/…/target`). Should these be **Tools** (e.g., `add_connection(from_path, to_path, relation_type)`) or **Resources** (e.g., URIs like `fsp://connections/file.id/target`)? **Recommendation:** Tools for mutations (add, delete, update connection), Resources for reads. This preserves the principle that resources are state and tools are actions. FSP's current stub for connections already exposes them as tools—that's correct.

## Implications for FSP (Protocol)

**1. Tool vs. Resource Mapping:** FSP currently maps all ops (read, write, edit, ls, grep, etc.) to tools. **Reconsider:** could `.versions/`, `.connections/`, `.metadata/` be Resources instead? **Recommendation:** keep the current design. File system operations are all *stateful actions*—reading and then writing are not idempotent, so treating them as tools (not resources) is correct. Metadata entries (versions, connections) are *derived state* and could be resources, but FSP's current flat tool surface is simpler and agents grok it. Revisit if you add subscription-like features.

**2. Tool Input/Output Schema Standardization:** Every FSP tool declares `input_schema` in MCP. **Implication:** ensure the output of every tool is also documented with `outputSchema`. Currently FSP doesn't; tools just return `FSPResult.to_dict()`. **Action:** add `outputSchema` to the tool registration. Example: `read` outputs `{ok: bool, path: str, data: str, error: str | null, meta: {...}}` with full JSON schema. Agents can then rely on the schema, not parse docstrings.

**3. Error Codes and Messages:** FSP wraps VFS exceptions. MCP has standard error codes (`-32700` parse error, `-32600` invalid request, `-32601` method not found, `-32602` invalid params, `-32603` internal error, etc.). **Mapping:** FSP's `NotFoundError` → `-32601` (method not found? no—`-32603` internal error is better). `ValidationError` → `-32602`. `MountError` → `-32603`. Document this mapping explicitly in FSP's error handling code.

**4. Cancellation and Streaming:** MCP has experimental `tasks/cancel` and `progress` notifications. FSP's grep/glob on large datasets could benefit from progress reporting. **Recommendation:** if a user runs `glob("**/*.py")` on a 100k-file mount, FSP should emit progress tokens every 1000 files. Implement this using the experimental tasks API if available, or progress notifications directly. The pattern is: capture `progress_token` from the request, emit progress notifications, check for cancellation before each batch.

**5. URI Namespace and Mount Routing:** MCP resources have URIs; FSP mounts have paths. **Mapping:** a mounted filesystem at `/data/archive` with a file `index.json` should have URI `fsp://archive/index.json` (mount name + relative path) or `fsp:///data/archive/index.json` (absolute path). **Recommendation:** use the relative form for clarity. Define the URI scheme explicitly in FSP's documentation and validate it in resource registration.

**6. Pagination and Bounded Results:** SWE-agent research shows agents prefer bounded, predictable output. FSP's grep/glob should return at most 50 results by default, with a note in `meta` if more exist. **Implication:** add `limit` and `offset` parameters to `glob` and `grep` tools. Current code doesn't have these; add them early.

**7. Composition and Layering:** FSP is an MCP server sitting on top of VFS. If FSP ever becomes a client to a remote FSP server (or multiple FSP servers), or if VFS gains an FSP backend, you have a composition question. **Pattern from MCP:** the Client API allows connecting to a Server (any implementation). Leverage this. If you build FSP client stubs, they can connect to either local VFS or remote FSP instances interchangeably.

**8. Capability Negotiation:** MCP servers declare capabilities at init time (`initialize` response includes `capabilities.tools`, `capabilities.resources`, etc.). FSP should do the same—explicitly declare which backends are mounted, which operations are supported, which features are stable vs. experimental. **Implication:** extend FSP's server initialization to return capability flags (e.g., `supports_vector_search: false`, `supports_semantic_search: false`, `backends: ["local_disk", "database"]`).

## Open Questions

1. **VFS → FSP Result Shape:** Should every FSP tool output conform to a single `{ok, path, data, error, meta}` envelope, or should different tools have different output schemas? The envelope is simple and uniform, but agents might benefit from schema variation (e.g., `grep` results have a different shape than `read` results). Current FSP uses the uniform envelope; is that constraint or feature?

2. **Async Backends and Streaming:** If FSP adds a vector search backend that streams results incrementally, how should that be exposed? MCP's `CallToolResult` takes a list of `ContentBlock`s, not a stream. Should FSP use the experimental tasks API for this, or batch results client-side?

3. **Error Recovery and Elicitation:** If a user tries to delete a protected file, should FSP use elicitation to ask for confirmation? Or should it be declarative (permissions reject, tool returns error, client decides). Current code does the latter; is that sufficient for agents?

4. **Resource vs. Tool for Metadata:** The `.chunks`, `.versions`, `.connections` subdirectories are "magic" metadata. Should they be exposed as Resources (discoverable via `list_resources`), or remain hidden and only accessible via tools? Current FSP doesn't expose them at all.

5. **Mount Routing and Capability Disclosure:** If a user mounts a slow remote backend at `/remote/`, should FSP's tool descriptions indicate which operations are slow? Or should this be discoverable only by trying and getting a timeout? The SDK has no mechanism for "this tool may timeout"; should FSP add one?

6. **User Scoping and Multi-Tenancy:** VFS supports `user_scoped=True`, but FSP doesn't yet. Should FSP accept a `user_id` parameter in initialization, or derive it from request context? If multiple agents use the same FSP instance, how are their mounts isolated? This is an open architectural question.

7. **Structured Outputs and Agent Training:** Agents trained on text-based file operations may not know how to parse JSON `structured_content`. Should FSP provide *both* text and structured output, or commit to structured-only and document the agent expectations? SWE-agent uses text; Claude ecosystem prefers structured.

