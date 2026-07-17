# Language Server Protocol — Influences for VFS and FSP

> Reference repo: `/Users/claygendron/Git/Repos/language-server-protocol`

## Overview

The Language Server Protocol (LSP) is a JSON-RPC 2.0–based specification defining how editors (clients) and language analysis engines (servers) communicate over a uniform wire. LSP matters for VFS/FSP as a reference design for **capability negotiation, versioned synchronization, incremental vs. full updates, error spaces, dynamic registration, and URI handling**. While LSP targets text documents and editor features, its solutions to encoding negotiation, partial results, and incremental state sync directly inform how FSP should expose file system operations over MCP.

## Navigation Guide

The LSP repo is organized as Markdown specifications in `/Users/claygendron/Git/Repos/language-server-protocol/_specifications/lsp/{3.17,3.18}/`:
- **Base protocol** (`specification.md` lines 23–384): JSON-RPC, error codes, request/notification/response shape, cancellation, progress.
- **Core types** (`types/` folder): URI, position, versioned documents, text edits, ranges.
- **Server lifecycle** (`general/initialize.md`): capability exchange, `initialize`/`initialized`/`shutdown`/`exit`.
- **Text synchronization** (`specification.md` lines 485–620): `didOpen`, `didChange` (full vs. incremental), `didSave`, versioning.
- **Dynamic capabilities** (`messages/{3.18,3.17}/registerCapability.md`, `unregisterCapability.md`): runtime capability add/drop.
- **Messages** (`messages/3.18/` folder): `$/progress`, `$/cancelRequest`, `window/showMessage`, etc.
- **Meta model** (`metaModel/metaModel.json`): machine-readable spec describing 180+ requests/notifications.

Skip: language features (`language/`), notebook support, workspace symbol/configuration unless modeling multi-backend discovery.

## File Index

| Path:Line | Purpose |
|-----------|---------|
| `_specifications/lsp/3.18/specification.md:23–100` | Base protocol: JSON-RPC framing, headers, ErrorCodes enum (ParseError -32700 through RequestCancelled -32800). |
| `_specifications/lsp/3.18/specification.md:313–350` | Cancellation: `$/cancelRequest` notification, error code -32800, partial results allowed on cancel. |
| `_specifications/lsp/3.18/specification.md:354–384` | Progress: `$/progress` generic notification with token-based reporting, independent of request ID. |
| `_specifications/lsp/3.18/specification.md:413–432` | Capabilities: client/server announce features via `ClientCapabilities`/`ServerCapabilities` during `initialize`. |
| `_specifications/lsp/3.18/types/uri.md` | URI semantics: RFC 3986, encoding ambiguity (colons/drive letters), consistency requirement, `DocumentUri` type. |
| `_specifications/lsp/3.18/types/position.md` | Position: `line`/`character` tuple, position encoding negotiation (UTF-8/UTF-16/UTF-32), @since 3.17. |
| `_specifications/lsp/3.18/general/initialize.md:1–100` | `initialize` request: `InitializeParams` (processId, clientInfo, rootUri, capabilities, trace, workspaceFolders). |
| `_specifications/lsp/3.18/general/initialize.md:100–300` | `ClientCapabilities`: textDocument, workspace, window, notebook capabilities with dynamic registration flags. |
| `_specifications/lsp/3.18/textDocument/didChange.md` | Text sync: `DidChangeTextDocumentParams`, versioned identifier, full vs. incremental `TextDocumentContentChangeEvent`. |
| `_specifications/lsp/3.18/specification.md:495–620` | `TextDocumentSyncKind`: None (0), Full (1), Incremental (2); `openClose`, `change`, `save`, `willSave` options. |
| `_specifications/lsp/3.18/types/partialResults.md` | Partial results: `partialResultToken` in params, `$/progress` stream, final response empty, errors invalidate partial results. |
| `_specifications/lsp/3.18/messages/registerCapability.md` | Dynamic registration: `client/registerCapability` request (server→client), `Registrations` list with method/options/scopeUri. |
| `_specifications/lsp/3.18/specification.md:353–382` | Work-done progress: `workDoneToken` in params, `WorkDoneProgressBegin/Report/End` value types via `$/progress`. |
| `_specifications/lsp/3.18/metaModel/metaModel.json` | Meta model: 180+ methods, each with `messageDirection`, `clientCapability`, `serverCapability`, `partialResult`, `registrationOptions`. |
| `_specifications/lsp/3.17/general/initialize.md:50–100` | Position encoding negotiation (@since 3.17): `general.positionEncodings` client capability, `positionEncoding` in server init result. |

## Core Concepts (What They Did Well)

### 1. Capability Negotiation via Structured Initialization

LSP solves the "feature matrix" problem elegantly: instead of clients asking "what do you support?", both sides *announce* capabilities upfront in `InitializeParams.capabilities` and `InitializeResult.capabilities`. Each feature is a path like `textDocument.hover.contentFormat` (string array) or `workspace.workspaceFolders` (boolean). This is load-bearing for extensibility — servers can ignore unknown client capabilities (forward-compatible) and clients ignore unknown server capabilities (server can add features without breaking older clients).

**Key:** Capabilities are grouped hierarchically (textDocument, workspace, window, general) and subdivided by operation (hover, completion, codeAction). This same pattern applies to FSP: instead of hardcoding which FS operations an MCP server supports, FSP should announce `fsCapabilities.read`, `fsCapabilities.write`, `fsCapabilities.glob`, etc., and let clients discover them.

### 2. Versioned Synchronization with Explicit Change Semantics

LSP distinguishes three text sync modes: None, Full, Incremental. The protocol pins down what Full means (`TextDocumentContentChangeEvent.text` with no range) vs. Incremental (same event with range + rangeLength). The `VersionedTextDocumentIdentifier` includes a numeric `version` that increments on every change, guaranteeing client and server agree on sequence. This is critical for agents — they can retry a completion request if a document version mismatch is detected.

**Key:** Text sync separates *protocol semantics* (which edits to send, in what order) from *implementation* (how to merge them into state). VFS and FSP should adopt the same: a document/object version, a clear definition of what "full write" vs. "incremental edit" means, and a requirement that servers reject stale requests.

### 3. Position Encoding Negotiation (@since 3.17)

LSP originally locked position offsets to UTF-16 (2 code units per character in many scripts). This broke when JavaScript and Python used UTF-8 (1 byte per ASCII, 3–4 per emoji). In 3.17, the spec formalized position encoding negotiation: client advertises supported encodings (`utf-8`, `utf-16`, `utf-32`) in order of preference; server picks one and announces it back. Both sides then measure character offsets in the negotiated encoding.

**Key:** This is a solved problem FSP can mirror. If FSP ever supports byte-level edits or position-based features, negotiate encoding upfront. UTF-8 is sane for text; UTF-16 is legacy compatibility; UTF-32 is rare but defined. Grover already uses NFC, so adding a `positionEncoding` capability is cheap.

### 4. Cancellation and Partial Results via Generic Progress Token

LSP allows cancellation via `$/cancelRequest` (notification, no response). A canceled request must still send a response (JSON-RPC rule), but can include partial results. The `partialResultToken` enables streaming: a `workspace/symbol` request with `partialResultToken: "x"` receives zero or more `$/progress` notifications with `token: "x"` and incremental symbol arrays, then a final empty `result: null`. Servers can thus stream large result sets without buffering.

**Key:** FSP should support cancellation for long-running operations (`glob` on a huge tree, `grep` on billions of lines). Partial results are less critical for file ops but matter for search. The token-based progress model is cleaner than callback-based streaming.

### 5. Dynamic Capability Registration (Late-Binding)

In LSP 3.14+, servers can call `client/registerCapability` and `client/unregisterCapability` *after* `initialize`. This enables on-demand feature activation (e.g., "watch this file type only if a config file exists"). The request includes `Registrations` array with method, options, and optional `scopeUri`. Clients apply/revoke them immediately.

**Key:** For FSP, this means an MCP server can start without `/search` operations, then register them once the vector store initializes. No restart needed. The `scopeUri` equivalent in FSP would be a mount path prefix (e.g., "only glob inside `/data`").

### 6. URI Semantics: Encoding Ambiguity as a Documented Tradeoff

LSP acknowledges that URIs are strings and encoding is implementation-defined. It explicitly warns: clients (VS Code) may encode colons in drive letters (`file:///C%3A/`) while others don't (`file:///c:/`). The spec says: **be consistent within your implementation and don't assume the other side uses the same encoding.** This is refreshingly honest — rather than mandate percent-encoding, the spec lets implementations optimize and documents the gotcha.

**Key:** VFS and FSP should adopt the same stance on paths. Document that paths are NFC-normalized, NUL/control-free, and follow POSIX semantics (stored as strings, not percent-encoded). If cross-system paths ever matter, document the encoding once and leave it.

## Anti-Patterns & Regrets

### 1. Capability Surface Sprawl

LSP has 180+ request methods and 100+ notification methods. The capability space is equally sprawling: `textDocument.completion.completionItem.resolveSupport.properties` is a 6-level path. New capabilities are added every version (3.15, 3.16, 3.17, 3.18). Client implementations struggle to maintain a complete capability matrix. Newer agent-focused protocols (OpenHands, SWE-agent) reject this: they expose 8–15 tools, not 180 methods.

**Implication for FSP:** Don't enumerate every FS operation as a separate capability. Bundle related ops (e.g., `read`, `stat` → `objectCapability`; `write`, `edit`, `delete` → `mutationCapability`). Start with 5 capabilities, not 50. Add dynamically only when a use case demands it.

### 2. Version Churn: Position Encoding, TextDocumentSync, Semantic Tokens

Position encoding (3.17), semantic tokens augmentation (3.16), notebook sync changes (3.18) — each version brought subtle changes to how offsets are calculated or how state is synchronized. Implementers of long-lived servers (Rust-Analyzer, Pyright) have to support multiple protocol versions. This is a tax on complexity.

**Implication for FSP:** Lock down the core sync model (versioning, change semantics) early. Don't change how `didChange` works in 1.1. If you need a new feature, add a capability flag, not a protocol version break.

### 3. Requests with No Guarantee of Response

LSP says "a request that got canceled still needs to return from the server and send a response back." Yet in practice, servers sometimes hang on long-running requests (full project symbol search). The spec doesn't mandate timeout semantics. A client may wait forever if the server crashes or deadlocks.

**Implication for FSP:** Define timeout semantics upfront. If a search takes >30s, the client sends `$/cancelRequest`. The server has 5s to respond with partial results or an error. Document this. Don't rely on "the server will eventually respond."

### 4. Error Codes: JSON-RPC StandardErrorCodes vs. LSP-Defined Ranges

LSP inherits JSON-RPC error codes (-32700 to -32600), then carves out LSP-specific codes (-32899 to -32800). The codes are sparse: -32803 (RequestFailed), -32802 (ServerCancelled), -32801 (ContentModified), -32800 (RequestCancelled). In practice, servers invent their own codes or use `error.data` to pack structured data. The error taxonomy is under-specified.

**Implication for FSP:** Don't try to enumerate error codes. Use semantic error classes (NotFoundError, WriteConflictError, ValidationError) and pack details in `error.data`. FSP already does this with `GroverResult` and five error classes.

## Implications for VFS (Implementation)

### 1. Capabilities as Metadata, Not Feature Gates

Adopt LSP's structured initialization pattern for VFS backends. Instead of:
```python
class DatabaseFS:
    supports_graph = True
    supports_versions = False
```

Model it as:
```python
capabilities: VFSCapabilities = {
    "object_kinds": ["file", "directory", "chunk", "version"],
    "search": ["glob", "grep"],
    "graph": ["successors", "ancestors"],
    "mutations": ["write", "edit", "delete"],
    "vector_index": None,  # not initialized
}
```

Then in `VirtualFileSystem._mount` callbacks, publish capabilities upstream. Agents can query `await vfs.capabilities()` and route requests accordingly.

### 2. Versioning for Cross-Mount Consistency

VFS already has `add_prefix` path rebasing. Add optional versioning to `Entry` and `VFSResult`:
```python
class Entry:
    path: str
    version: int | None = None  # incremented on write
    content_hash: str | None = None  # for cache-busting
```

When a write succeeds, bump the version. If an agent requests a read with `expected_version=v5` and the current version is v6, return a clear error: `{success: false, reason: "ContentModified"}`. This prevents agents from applying edits to stale content.

### 3. User Scoping via Principals, Not Unix Mode Bits

VFS already rejects `chmod`/`chown` semantics (see POSIX memo). For multi-tenant scenarios, model user scope as:
```python
class VFSContext:
    user_id: str
    principal: "admin" | "editor" | "viewer"
    scope: str  # e.g., "/workspace/alice" — paths outside denied
```

Then check scopes in `_route_single` before delegating to `_*_impl`. This maps to LLM+Grover's security model: the agent runs as a specific user, operates within that user's mount tree.

### 4. Object Model: Extend Entry for Domain Richness

Entry is flat: path, kind, content, size, lines, score, degree. For specialized backends (graph, vector), extend with:
```python
class GraphEntry(Entry):
    node_id: str
    edge_type: str | None
    target_path: str | None
```

But keep the base `Entry` projection simple. Agents query `await vfs.read(...)` and get `Entry`. Specialized queries (`vfs.pagerank`, `vfs.semantic_search`) return `GraphEntry` or `VectorEntry` subclasses in `.entries`.

## Implications for FSP (Protocol)

### 1. Capability Announcement at Server Start

FSP's MCP server should expose a `get_capabilities` RPC (or init hook) that returns:
```json
{
  "version": "0.0.2",
  "operations": {
    "crud": ["read", "write", "edit", "delete"],
    "navigation": ["ls", "stat", "tree"],
    "search": ["glob", "grep"],
    "graph": null,
    "vector": null
  },
  "textSyncKind": "Full",
  "positionEncoding": "utf-8",
  "maxResultSize": 10000
}
```

Clients can then shape requests based on what the server supports. If graph is null, don't call `successors`. If vector is present, try semantic search first.

### 2. Versioned Synchronization for Write Ordering

FSP's write path should track versions:
- `write(path, content, expectedVersion=None)` → on success, returns `{ok: true, version: 3}`.
- `edit(path, old, new, expectedVersion=None)` → same.
- If `expectedVersion` is set and doesn't match, return `{ok: false, error: "ContentModified", currentVersion: 5}`.

This prevents race conditions when agents chain writes. If an agent reads at version 2, edits it, then writes at version 2 but the content changed to version 3 in the meantime, the write is rejected. Agent retries or fails explicitly.

### 3. Cancellation for Long-Running Search

FSP's glob/grep should support cancellation:
```
request: glob(pattern="**/*.rs", path="/", partialResultToken="abc123")
response stream:
  $/progress {token: "abc123", value: [10 paths]}
  $/progress {token: "abc123", value: [20 more paths]}
  $/cancelRequest notification arrives
  response: {result: null, error: {code: -32800}}  # RequestCancelled
```

For local filesystems, this doesn't matter much. For remote/slow backends (S3, database), it's essential.

### 4. Dynamic Mount Registration

FSP/Grover's mount system is static at server start. Enable runtime registration:
```
server: registerCapability {
  registrations: [
    {
      method: "mount",
      options: {
        path: "/vector",
        backend: "pinecone",
        capabilities: ["semantic_search", "vector_search"]
      }
    }
  ]
}
```

Then agents can discover new mounts without reconnecting. This pairs with dynamic backend initialization (e.g., user uploads an embedding model; server registers `/embeddings` mount).

### 5. Error Space: Five Semantic Classes, Not errno Codes

FSP already uses `GroverResult` with five error classes. Map them to JSON-RPC error codes:
- `NotFoundError` → -32800 (custom range, could be -32850)
- `WriteConflictError` → -32851 (e.g., already exists, or permission denied)
- `ValidationError` → -32852 (bad path, bad pattern)
- `GraphError` → -32853 (bad query, cycle detected)
- `MountError` → -32854 (no mount for path)

Clients don't need to parse error strings; they check the code. Include `error.data` with details:
```json
{
  "error": {
    "code": -32851,
    "message": "Cannot write /read-only/file.txt",
    "data": {
      "reason": "permission_denied",
      "path": "/read-only/file.txt",
      "operation": "write",
      "required_permission": "write",
      "available_permission": "read"
    }
  }
}
```

### 6. Position Encoding: Declare UTF-8, Stick to It

FSP deals with paths and file content, not cursor positions. But if FSP ever supports line/character ranges (e.g., `read(path, startLine, endLine)`), declare `positionEncoding: "utf-8"` in capabilities and never waver. This sidesteps the UTF-16 mess.

## Open Questions

1. **Capability Versioning:** If FSP 1.0 supports `read`, `write`, `glob` and FSP 2.0 adds `semantic_search`, how do agents detect which version? Model it as a service version separate from operation versions?

2. **Partial Results for Write Operations:** LSP uses partial results for search (streaming symbols). For FSP, could a batch write return partial success? E.g., `write([file1, file2, file3])` succeeds on file1, file2 but file3 fails — return partial results + error? Or fail-fast only?

3. **Mount Topology Discovery:** VFS's mount routing works locally. If FSP exposes multiple backends (disk, database, vector store), should agents be able to query the mount tree dynamically? Add a `mounts()` RPC that returns `{path: "/data", backend: "sqlite", capabilities: [...]}`?

4. **Atomic Cross-Mount Operations:** VFS's `_cross_mount_transfer` for move/copy is non-atomic (writes commit before deletes). Should FSP expose this risk to clients or hide it? Document as "move is copy+delete, may leave duplicates on crash"?

5. **Streaming for Large Results:** Partial results work for unbounded searches (glob, grep). For a read of a 1GB file, should FSP support streaming bytes via `$/progress`, or always return `{error: "FileTooLarge"}`?

6. **Encoding Declaration for Paths:** VFS uses NFC UTF-8 paths, control-char-free. Should FSP's capability announce `pathNormalization: "NFC"` and `pathEncoding: "utf-8"` explicitly?

---

**Covered:** JSON-RPC base protocol, initialize/shutdown lifecycle, capability negotiation, text synchronization (full/incremental/versioned), position encoding negotiation, cancellation with partial results, progress reporting, dynamic registration, URI semantics, error space, meta model structure. 

**Skipped:** language features (hover, completion, symbols), notebook documents, workspace features (file watch, apply edits), window features (show message), specific method deep-dives.

**Surprising findings:** Position encoding negotiation (@since 3.17) is elegant but shows how late protocol fixes are slow to ship. Capability sprawl (180+ methods) is a real complexity tax; FSP should stay focused. Error codes are under-specified; semantic classes are better. Dynamic registration is underused but powerful for multi-backend systems.

