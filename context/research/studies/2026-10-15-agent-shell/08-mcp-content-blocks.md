# S8 — MCP typed tool-result content: the vocabulary vfs's one wire adapter must follow

- **Date:** 2026-10-15
- **Researcher:** S8 (agent-shell study)
- **Question:** pin exactly what the MCP standard says today about typed tool-result content, re-verify the July memo (`context/research/2026-07-25-multimodal-result-content.md` §2.5, §2.6, §4 Q2/Q6/Q7, §6 items 6–9) against the current revision, and produce the row→block projection vfs's adapter should implement.
- **Clones read (commit, date):** `modelcontextprotocol` 86f6e0c6 (2026-10-14, Apache-2.0/MIT transition); `python-sdk` 754254c0 (2026-10-13, MIT); `fastmcp` e2fcc41 (2026-10-08, Apache-2.0); `claude-agent-sdk-python` aada024 (2026-10-15, MIT); `opencode` 13263f30ed (2026-10-16, `origin/dev`, MIT); `codex` 16e578d (2026-10-15, Apache-2.0); `gemini-cli` **DIRTY, unusable** — see Finding 10.
- **Executed:** two scripts under `experiments/s8/` — `mcp_blocks_experiment.py` (a stdio MCP server driven by the official SDK client over a logging relay, wire validated against the JSON Schema of three revisions) and `vfs_bytes_row_probe.py` (what the live vfs tree does with a bytes row today). Outputs are beside them (`*.out`, `wire_*.jsonl`).
- **Evidence labels:** `[EXECUTED]` ran here and the output is saved; `[READ]` read in a checkout or a fetched page; `[INFERRED]` my reasoning; `[NOT VERIFIED: why]` could not be checked.

## Summary

The MCP content-block vocabulary has not changed shape since the revision the July memo read. It is still exactly five blocks — `text`, `image`, `audio`, `resource_link`, `resource` (embedded) — with the same required fields, the same `annotations` (`audience`, `priority`, `lastModified`) and a `_meta` slot on every block. There is no video block, and the 2026-07-28 schema rejects one `[EXECUTED]`. What changed around the blocks matters more than the blocks: the current revision is **2026-07-28**, a large stateless rewrite. Every result now carries a required `resultType`; `structuredContent` may be any JSON value, not only an object; `outputSchema` may be any JSON Schema 2020-12; `resources/read` results carry required `ttlMs` and `cacheScope`; `resources/subscribe` is gone, replaced by `subscriptions/listen`; resource-not-found is `-32602`. The `_meta` key grammar (reverse-DNS prefix, `mcp`/`modelcontextprotocol` second labels reserved) landed in 2025-11-25. The spec gives no tool-result size guidance at all; the only size facts are `Resource.size` (bytes before base64, "to estimate context window usage") and per-client limits (Claude Code: 25,000 tokens including image data). On the client side the picture is stark: of the four harnesses, only `text` and `image` reach every model; `audio` reaches one (codex, when the model has the modality); `resource_link` is flattened to a bare URI (opencode), to raw JSON text (codex), or dropped (Claude Code, per a closed bug and Anthropic's own SDK comment); nobody fetches a link. Two harnesses also replace the entire `content` array with `structuredContent` when it is present (codex) or make it the primary output (opencode) — so the structured payload and the text block must each be sufficient alone. The live vfs tree today renders a bytes row as an empty body `[EXECUTED]` and base64-encodes bytes into `to_payload()` `[EXECUTED]`, so both projections need the placeholder rule and a bytes-exclusion rule before any adapter ships. The one-line answer: adopt the five blocks verbatim; one rendered text block first, then media blocks keyed by path in `_meta`; `isError = not result.success`; `structuredContent = Result.to_payload()` with row bytes stripped; `resource_link` with a `vfs:///path` URI plus a minimal `resources` capability at v1 so links are honest.

## Findings

### 1. The revisions, and which one is current `[READ]`

`docs/specification/` and `schema/` each hold six directories: `2024-11-05`, `2025-03-26`, `2025-06-18`, `2025-11-25`, `2026-07-28`, `draft` (modelcontextprotocol, `ls docs/specification schema`). `schema/2026-07-28/schema.ts:30` sets `LATEST_PROTOCOL_VERSION = "2026-07-28"`; `schema/draft/schema.ts` is byte-identical in length (3,197 lines) and its changelog says "Changes since the most recent release will accumulate here" (`docs/specification/draft/changelog.mdx`) — the draft is empty. So the current revision is 2026-07-28. The July memo read 2025-11-25 (memo §2.5, first paragraph), and the task brief named 2025-06-18; this report diffs from both.

The official Python SDK at PyPI `mcp 2.3.0` / `mcp-types 2.3.0` knows all five released revisions and speaks 2026-07-28 as `LATEST_MODERN_VERSION` (`python-sdk:src/mcp-types/mcp_types/version.py:24-55`) `[READ]`; the experiment confirmed the negotiated version on the wire `[EXECUTED]`.

### 2. The block vocabulary, exact, 2026-07-28 `[READ]`

From `modelcontextprotocol:schema/2026-07-28/schema.ts`. "Required" means the field has no `?`.

| Block | `type` | Required fields | Optional fields | Lines |
| --- | --- | --- | --- | --- |
| TextContent | `"text"` | `text: string` | `annotations`, `_meta` | 2316-2331 |
| ImageContent | `"image"` | `data: string` (base64, `@format byte`), `mimeType: string` | `annotations`, `_meta` | 2340-2362 |
| AudioContent | `"audio"` | `data: string` (base64), `mimeType: string` | `annotations`, `_meta` | 2371-2393 |
| ResourceLink | `"resource_link"` | `uri: string` (`@format uri`), `name: string` | `title`, `description`, `mimeType`, `size: number` (bytes before base64), `annotations`, `icons`, `_meta` | 1719-1721, inherits `Resource` 1441-1475 and `BaseMetadata` 954-968, `Icons` 934-949 |
| EmbeddedResource | `"resource"` | `resource: TextResourceContents \| BlobResourceContents` | `annotations`, `_meta` | 1734-1745 |

- `ContentBlock = TextContent | ImageContent | AudioContent | ResourceLink | EmbeddedResource` (schema.ts:2305-2306). Nothing else. The word "video" appears once in the whole revision, in the index page describing the MCP Apps extension ("video players rendered inline", `docs/specification/2026-07-28/index.mdx:87`) — a UI extension, not a content block.
- `ResourceContents` (1514-1527): `uri` required, `mimeType?`, `_meta?`. `TextResourceContents` adds `text: string` ("must only be set if the item can actually be represented as text", 1535-1541); `BlobResourceContents` adds `blob: string` base64 (1548-1555).
- `Annotations` (2270-2300): `audience?: Role[]` where `Role = "user" | "assistant"` (1694); `priority?: number` with `@minimum 0`, `@maximum 1` ("1 means most important, effectively required; 0 means entirely optional"); `lastModified?: string` ISO 8601. The schema enforces the numeric range and the audience enum: `priority: 1.5` and `audience: ["system"]` are rejected `[EXECUTED]`.
- `CallToolResult extends Result` (1809-1834): `content: ContentBlock[]` required; `structuredContent?: unknown` ("any JSON value ... that conforms to the tool's outputSchema if one is defined"); `isError?: boolean` ("If not set, this is assumed to be false"); plus `Result`'s `_meta?: ResultMetaObject` and **`resultType: ResultType` required** (223-235): "Servers implementing this protocol version MUST include this field. ... when a client receives a result from a server implementing an earlier protocol version (which does not include `resultType`), the client MUST treat the absent field as `"complete"`."
- `ImageContent.mimeType` and `AudioContent.mimeType` carry the only mime guidance in the content section: "Different providers may support different image types." The spec states **no accepted image mime list for content blocks**. The only mime list in the revision is for `icons` ("Clients that support rendering icons MUST support at least `image/png`, `image/jpeg`; SHOULD also support `image/svg+xml`, `image/webp`", 949-957) and it is about icons, not tool results.
- `_meta` key grammar (`MetaObject`, 35-48): a key is an optional prefix plus a name. The prefix is dot-separated labels ending in `/`, labels start with a letter and end with a letter or digit; reverse-DNS is recommended; **any prefix whose second label is `modelcontextprotocol` or `mcp` is reserved** (`io.modelcontextprotocol/`, `dev.mcp/`, `com.mcp.tools/`; `com.example.mcp/` is not reserved). The name starts and ends alphanumeric, interior may have `-`, `_`, `.`. The JSON Schema does not police this (a reserved prefix validates `[EXECUTED]`); it is prose law only.

### 3. Prose rules around the blocks, 2026-07-28 `[READ]`

From `docs/specification/2026-07-28/server/tools.mdx` unless noted.

- All five block types "support optional annotations ... audience, priority, and modification times. This is the same annotation format used by resources and prompts" (lines 410-416).
- Resource links: "the tool will return a URI that can be subscribed to or fetched by the client" (451-453); "Resource links returned by tools are not guaranteed to appear in the results of a `resources/list` request" (468-471, and schema.ts:1714).
- Embedded resources: "Servers that use embedded resources **SHOULD** implement the `resources` capability" (473-476). "It is up to the client how best to render embedded resources for the benefit of the LLM and/or the user" (schema.ts:1727-1730).
- Structured content: "any JSON value ... that conforms to the tool's `outputSchema` if one is defined. For backwards compatibility, a tool that returns structured content SHOULD also return the serialized JSON in a TextContent block" (496-500). The note adds that `structuredContent` "is server-produced result data and is unrelated to LLM structured outputs."
- Output schema: "Servers **MUST** provide structured results that conform to this schema. Clients **SHOULD** validate structured results against this schema" (509-515). The schema may be any JSON Schema 2020-12 (schema.ts:1999-2005); an array-typed output schema is given as a worked example (578-631).
- Error handling (738-786): two mechanisms. **Protocol errors** are JSON-RPC errors for "issues with the request structure itself that models are less likely to be able to fix: unknown tool, malformed requests, server errors." **Tool execution errors** "contain actionable feedback that language models can use to self-correct": "API failures, input validation errors (e.g., date in wrong format, value out of range), business logic errors" — reported with `isError: true`. "Clients **SHOULD** provide tool execution errors to language models." The 2025-11-25 changelog (minor change 5, SEP-1303) is where input-validation errors were moved from protocol errors to execution errors.
- Security (787-803): servers MUST "sanitize tool outputs"; clients SHOULD "validate tool results before passing to LLM".
- Size and encoding: the tools page has **no** size guidance for a tool result. `grep -rn -iE "token|large result|size limit"` across tools.mdx, resources.mdx and basic/index.mdx finds only `Resource.size` ("Optional size in bytes", resources.mdx:310; schema.ts:1466-1471: "before base64 encoding or any tokenization ... can be used by Hosts to display file sizes and estimate context window usage"), the icon security note ("Consumers MAY set limits for image and content size", basic/index.mdx:481), and the resources security list ("Binary data MUST be properly encoded", resources.mdx:431). Encoding for binary is base64 everywhere (`@format byte`).

### 4. The `resources` capability, 2026-07-28 `[READ]`

From `docs/specification/2026-07-28/server/resources.mdx` and schema.ts.

- Declaration: `capabilities.resources: { subscribe?: boolean, listChanged?: boolean }` (schema.ts:793-862; resources.mdx:39-81). A server with neither feature declares `"resources": {}`.
- Obligations once declared: it "**MUST** respond to `resources/list` requests with the set of resources currently available ... This set **MAY** be empty and **MAY** change over time ... but **MUST NOT** vary per-connection ... The set **MAY** vary by the authorization presented on the request" (resources.mdx:70-78).
- `resources/read` returns `contents: (TextResourceContents | BlobResourceContents)[]`; binary is `blob` base64 (schema.ts:1229-1231; resources.mdx:316-334). "Servers **MAY** return multiple resource contents in response to a single `resources/read` request. For example, a server could return the contents of several files when a directory resource is read" (resources.mdx:168-170). The result extends `CacheableResult`, so `ttlMs` (ms, `@minimum 0`; 0 means immediately stale) and `cacheScope` (`"public"` | `"private"`) are required (schema.ts:1081-1110) — the experiment's legacy-session read result is invalid against 2026-07-28 for exactly these two fields plus `resultType` `[EXECUTED]`.
- Templates: `resources/templates/list` returns `ResourceTemplate { uriTemplate (RFC 6570), name, title?, description?, mimeType?, annotations?, icons?, _meta? }` (schema.ts:1481-1507; resources.mdx:181-230).
- Subscriptions: `resources/subscribe` and `resources/unsubscribe` are **removed**; a client lists URIs in `subscriptions/listen`'s `notifications.resourceSubscriptions` and receives `notifications/resources/updated` tagged with `io.modelcontextprotocol/subscriptionId` (resources.mdx:244-267; changelog major change 4).
- Errors: not found → JSON-RPC `-32602` ("Invalid Params"; was `-32002`, clients SHOULD still accept it); internal → `-32603`; "Servers **MUST NOT** return an empty `contents` array for a non-existent resource" (resources.mdx:402-426).
- URI schemes (resources.mdx:366-400): `https://` only "when the client is able to fetch and load the resource directly from the web on its own"; `file://` "to identify resources that behave like a filesystem. However, the resources do not need to map to an actual physical filesystem", and servers "MAY identify file:// resources with an XDG MIME type like `inode/directory`"; `git://`; "Custom URI schemes **MUST** be in accordance with RFC3986, taking the above guidance in to account." The list "is not exhaustive — implementations are always free to use additional, custom URI schemes."
- Security: "Servers **MUST** validate all resource URIs", "**MUST** sanitize file paths to prevent directory traversal attacks when serving `file://` resources" (resources.mdx:428-435).

### 5. What changed since 2025-06-18 (and since 2025-11-25) that touches content `[READ]`

Method: `diff schema/2025-06-18/schema.ts schema/2026-07-28/schema.ts` filtered to content names, plus both changelogs and a diff of the Tool Result prose. The five block interfaces and their field sets are **unchanged** from 2025-06-18 through 2026-07-28; every diff hunk inside them is a doc comment or the `_meta` type name (`{ [key: string]: unknown }` → `MetaObject`). `Annotations.lastModified` (2025-06-18 schema.ts:1127) and `Resource.size` (:556) already existed in 2025-06-18.

2025-11-25 (changelog `docs/specification/2025-11-25/changelog.mdx`):

1. `icons` on `Tool`, `Resource`, `ResourceTemplate`, `Prompt`, `Implementation` (SEP-973) — so `ResourceLink` gained `icons?` by inheritance.
2. `_meta` became the typed `MetaObject` with the key grammar and the reserved-prefix rule above.
3. JSON Schema 2020-12 became the default dialect (SEP-1613).
4. Tool name guidance (SEP-986): 1–128 chars, `[A-Za-z0-9_.-]`, case-sensitive, unique per server.
5. Input validation errors are tool execution errors, not protocol errors (SEP-1303).
6. Sampling gained tool calling with `ToolUseContent` and `ToolResultContent` (SEP-1577) — these are **sampling-message** blocks, not `CallToolResult` blocks; `ToolResultContent.content` is `ContentBlock[]`, i.e. it reuses the same five.

2026-07-28 (changelog `docs/specification/2026-07-28/changelog.mdx`):

1. `resultType` required on every `Result` (major change 8, SEP-2322).
2. `structuredContent` loosened from `{ [key: string]: unknown }` to `unknown`; `outputSchema` loosened to any 2020-12 schema (minor change 10, SEP-2106). A scalar or array `structuredContent` is invalid against 2025-06-18 and valid against 2026-07-28 `[EXECUTED]`.
3. `CacheableResult` with required `ttlMs`/`cacheScope` on `tools/list`, `prompts/list`, `resources/list`, `resources/read`, `resources/templates/list` (minor change 5, SEP-2549).
4. `resources/subscribe`/`unsubscribe` replaced by `subscriptions/listen` (major change 4).
5. Resource not found `-32002` → `-32602` (minor change 6).
6. Stateless protocol: no `initialize`; every request carries `_meta["io.modelcontextprotocol/protocolVersion"]` and `clientCapabilities`; servers SHOULD stamp `_meta["io.modelcontextprotocol/serverInfo"]` on results; `server/discover` is mandatory (major changes 2-3). The experiment's modern wire shows all of this `[EXECUTED]` (`experiments/s8/wire_auto.jsonl`).
7. Deprecated: Roots, Sampling, Logging (SEP-2577) — `ToolUseContent`/`ToolResultContent` and `LoggingLevel` carry `@deprecated` in the schema.
8. A non-normative "Stateful Tools" section: servers needing cross-call state return an explicit handle as ordinary tool output and accept it as an argument (tools.mdx:683-736).
9. An error-code allocation policy: `-32000..-32019` implementation-defined, `-32020..-32099` reserved for MCP (minor change 12).

Nothing in either revision adds a video block, a size rule for `content`, or a mime accept-list for `image`/`audio`.

### 6. How the official Python SDK builds and serializes results `[READ]` + `[EXECUTED]`

`python-sdk` 754254c0 (the PyPI 2.3.0 line):

- Types now live in a separate distribution `mcp-types` with per-revision modules (`src/mcp-types/mcp_types/_v2025_11_25/`, `_v2026_07_28/`) and a revision-agnostic `_types.py` that the top-level names export. The 2026-07-28 `CallToolResult` has `result_type: str` required with alias `resultType`, `structured_content: Any | None` with alias `structuredContent`, `is_error: bool | None` with alias `isError`, `meta` with alias `_meta` (`_v2026_07_28/__init__.py:2984-3024`). `ContentBlock = TextContent | ImageContent | AudioContent | ResourceLink | EmbeddedResource` (:2344).
- `resultType` is stamped by the server runner, **only on modern sessions**: "Spec 2026-07-28: `Result.resultType` is required ... this covers everything else: custom methods, extension methods, and empty results" (`src/mcp/server/runner.py:386-393`). On a legacy (handshake) session the wire omits it, and the result is then valid against 2025-11-25 and invalid against 2026-07-28 `[EXECUTED]`.
- `isError`: `MCPServer._handle_call_tool` turns any non-`MCPError` exception into `CallToolResult(content=[TextContent(text=str(exc))], is_error=True)` and re-raises `MCPError` as a protocol error (`src/mcp/server/mcpserver/server.py:437-456`); the tool layer documents the split — `MCPError` "means respond with a protocol error", everything else "reaches the model as an is_error result" (`tools/base.py:195-212`).
- Return-value conversion (`utilities/func_metadata.py:624-655`): a `ContentBlock` passes through; `Image`/`Audio` helpers become blocks; lists flatten; anything else is JSON-dumped into one `TextContent`. The `Image` helper guesses mime by extension from a five-entry map and defaults raw bytes to `image/png` with **no sniffing** (`utilities/types.py:9-61`); `Audio` likewise defaults to `audio/wav`.
- Resources: `Resource.read()` returns `str | bytes`; bytes become `BlobResourceContents(blob=base64(...))` (`mcpserver/server.py:478-484`). So a resource read **can** return binary, and the experiment's `resources/read` of a `vfs:///` URI returned a `blob` that validates against all three revisions `[EXECUTED]`.
- The in-process `Client(server, mode="2026-07-28")` path dispatches Python objects directly "without JSON-RPC framing" (`src/mcp/client/client.py:109-121`), so a memory-stream spy records nothing for it. To see the real 2026-07-28 wire I ran the server over stdio behind a logging relay (`experiments/s8/mcp_blocks_experiment.py`, roles `--relay`/`--serve`).

### 7. fastmcp's helpers and conversions `[READ]`

`fastmcp` e2fcc41 (PyPI 4.1.0), `fastmcp_slim/fastmcp/`:

- `Image`, `Audio`, `File` helpers at `utilities/types.py:268-500`. `Image` maps format/extension through `mimetypes.guess_type` plus a small override map and defaults raw bytes to `image/png`; `Audio` to `audio/wav`; `File.to_resource_content` yields an `EmbeddedResource` whose URI is the real file's `file://` URI or a synthetic `file:///resource.<ext>` for raw bytes, with `text/*` decoded to `TextResourceContents` (utf-8, then latin-1) and everything else to a `blob`. No sniffing anywhere; no size budget anywhere.
- `_convert_to_single_content_block` (`tools/base.py:498-522`): `bytes` are decoded as utf-8 into a `TextContent`, and on failure **base64-encoded into a `TextContent`** — the July memo's anti-pattern is still there at :515-520.
- `ToolResult.structured_content` must be a `dict` (`tools/base.py:145-148`), stricter than the 2026-07-28 "any JSON value".
- `convert_result` (`tools/base.py:367-430`): a `CallToolResult` passes through; content-typed returns skip `structured_content` unless an output schema exists; otherwise the value is serialized to JSON for `structured_content` and the text block is the JSON dump — the spec's SHOULD.
- Prefab UI results put a placeholder string `"[Rendered Prefab UI]"` in `content` and the real payload in `structured_content` (`tools/base.py:525-570`) — the pattern, as the July memo noted.

### 8. Client-side consumption, verified in source

**Claude Code** (official docs `https://code.claude.com/docs/en/mcp`, fetched 2026-10-15) `[READ]`:

- "When an MCP tool returns a PNG, JPEG, GIF, or WebP image, Claude sees the image inline in the conversation. The inline copy may be scaled down or compressed to fit the model's image size limits. Claude Code also saves the original bytes to a file in the session's `tool-results` directory ... and gives Claude the path" (v2.1.283+).
- "Claude Code displays a warning when MCP tool output exceeds 10,000 tokens and limits output to 25,000 tokens by default" (`MAX_MCP_OUTPUT_TOKENS`); "Tools that return image data are still subject to the token limit"; a successful text-only result over 50,000 characters is persisted to a file and replaced by a path; `_meta["anthropic/maxResultSizeChars"]` on a tool raises that per-tool threshold up to 500,000.
- "when a tool returns a result marked `isError: true`, Claude receives the result's text as the tool's error message. Error text longer than about 11,000 characters keeps only its first 5,000 and last 5,000 characters."
- Transport cap: an HTTP/SSE response body or a WebSocket message over 16 MiB fails the request.
- Resources: `@server:protocol://resource/path` mentions, "automatically fetched and included as attachments when referenced"; "Claude Code automatically provides tools to list and read MCP resources when servers support them."
- `resource_link` and `audio` blocks in tool results: the docs say nothing. A community-mirrored bug (claudeissues.com #53453, Claude Code 2.1.117, filed 2026-04-26, closed "not planned" 2026-05-29) reports "When an MCP tool returns a `resource_link` content item, Claude Code does not attempt to fetch or display it ... the resource is completely dropped", and that embedded PDF blobs are ignored while images work `[READ, third-party page]`. Anthropic's own `claude-agent-sdk-python` says the same in code for in-process SDK servers: "Resource links and text resources are flattened to text because that is what the CLI renders; binary resources and unknown block types are dropped with a warning" (`src/claude_agent_sdk/__init__.py:473-510`; a link becomes `name\nuri\ndescription` text; `audio` hits the "Unsupported content type" branch). Also from that file: Claude Code reads client hints from vendor-prefixed `_meta` keys "because MCP clients drop annotation fields they do not know" (:460-468). Current behaviour for external servers on `resource_link`, embedded blobs and `audio`: `[NOT VERIFIED: closed source; no changelog entry found by web search on 2026-10-15]`.

**opencode** 13263f30ed `[READ]` (`packages/core/src/mcp/client.ts:429-444`): `text` → text; `image` and `audio` → a `media` part with `data` + `mimeType`; `resource_link` → **text containing only `part.uri`** (name, description, mimeType, size dropped); embedded text resource → text; embedded blob with a mimeType → media; blob without mimeType → text of the uri; anything else → dropped (`return []`). Then `packages/core/src/tool/mcp.ts:78-108`: on `isError` the tool throws a `ToolFailure` whose message is the **joined text parts only** — structured content and media are discarded on error; otherwise the model-facing `output` is `result.structured` when present, else the joined text (JSON-parsed if it looks like JSON and no output schema was declared), with `content` carried beside it. `packages/core/src/aisdk.ts:565-590`: media whose mime starts with `image/` or equals `application/pdf` is pulled **out** of the tool result into a following user message, and the tool result text becomes "Media attached in the following user message." when nothing else is left; other media (audio) stays as a `file` item inside the tool result, provider-dependent. Compaction renders media as `[<mime> omitted]` (`session/compaction.ts:835`).

**codex** 16e578d `[READ]`:

- Model-facing conversion `codex-rs/protocol/src/models.rs:2436-2575`. First: **if `structuredContent` is present and not null, the model receives only its JSON serialization as text and the `content` array is discarded** (:2448-2465), unless a block carries `_meta["codex/encryptedContent"]`. Otherwise per block: `text` → `input_text`; `image` → `input_image` as a `data:<mime>;base64,...` URL (mime defaults to `application/octet-stream` if absent; detail from `_meta["codex/imageDetail"]`); `audio` → `input_audio`; **everything else — `resource_link`, `resource`, unknown types, malformed blocks — becomes an `input_text` holding the raw JSON of the block** (:2509-2511, :2571-2573). The unit test `converts_unstructured_mcp_content_to_items` (:3515-3570) pins a `resource_link` arriving as its JSON text. So the search's "dropped" claim is wrong for current main: links are not dropped, they are shown as JSON.
- `codex-rs/core/src/mcp_tool_call.rs:948-985`: when the model lacks the modality, an `image`/`audio` block is replaced by a text block `<image content omitted because you do not support image input>` / `<audio content omitted ...>`.
- TUI rendering `codex-rs/tui/src/history_cell/mcp_result.rs:52-110`: text verbatim; image → "Returned image" (first decodable image previewed); audio → `<audio content>`; embedded resource → `embedded resource: <uri>`; link → `link: <uri>`; unknown → the block's JSON.
- Context accounting counts image bytes by detail tier and audio by duration (`context_manager/history.rs:1300-1345`); a test pins that large structured content is truncated for the response item (`tools/context_tests.rs:133`).

**gemini-cli**: see Finding 10. The July memo §2.9 (current-main reads from 2026-07) records: per-block transform, display placeholders `[Image: image/png]` and `[Link to <title>: <uri>]`, `resource_link` flattened to prose, audio/video stripped as "[SYSTEM: Binary content stripped…]" for non-Gemini-3 models, no fetch of links `[READ, July memo]`.

### 9. The client support matrix

"Model" = what reaches the model; "UI" = what the human sees. CC = Claude Code; SDK = claude-agent-sdk-python in-process servers; OC = opencode; CX = codex; GC = gemini-cli (July memo).

| Block | CC model | SDK model | OC model | CX model | GC model |
| --- | --- | --- | --- | --- | --- |
| `text` | rendered | passed | passed (or replaced by `structured` when present) | passed (replaced by `structuredContent` when present) | passed |
| `image` (png/jpeg/gif/webp) | inline, scaled; original saved to disk | passed | moved to the next user message as a file part | `input_image` data URL; placeholder text if the model lacks vision | passed as inline data (Gemini-3 only) |
| `audio` | `[NOT VERIFIED]` | dropped with warning | kept as a file item in the tool result (provider-dependent) | `input_audio`; placeholder if unsupported | stripped with a system note |
| `resource_link` | dropped per #53453 (2.1.117); `[NOT VERIFIED]` today | flattened to `name\nuri\ndescription` | bare `uri` as text | raw JSON as text | prose `[Link to <title>: <uri>]` |
| `resource` (text) | `[NOT VERIFIED]` | flattened to its text | its text | raw JSON as text | prose |
| `resource` (blob) | ignored per #53453 | dropped with warning | media if mimeType present | raw JSON as text (base64 inside) | stripped |
| `structuredContent` | `[NOT VERIFIED]` | passed through | becomes the primary `output` | **replaces `content` entirely** | `[NOT VERIFIED]` |
| `isError: true` | text becomes the error message, middle-truncated past ~11k chars | passed | only text parts survive, as the failure message | `success: false` on the output | — |
| fetches a link via `resources/read`? | no (`@` mentions and a list/read tool exist) | no | no | no | no |

Reading of the matrix: the **text block is the only universally rendered block**, the image block is the only media block every harness shows a model, and `structuredContent` can **replace** the text block in two harnesses. Everything vfs needs an agent to know must therefore be present in the text block *and* in the structured payload, independently.

### 10. The gemini-cli clone is unusable `[READ]`

`~/Git/Repos/gemini-cli` is marked DIRTY at d42e3f1e7 in `refresh.log`. Its working tree is not gemini-cli: `package.json` is `@snhu-ai/datum-cli` ("DATUM CLI - Data Analytics Tool for Understanding Metadata"), `git status` shows every tracked file deleted and the checkout replaced by another project; `licenses.log` recorded that project's MIT licence under gemini-cli's name. The HEAD commit (2025-08-01) is real gemini-cli, but its `packages/core/src/tools/mcp-tool.ts` delegates block conversion to `@google/genai`'s `mcpToTool` (`git show HEAD:...:109-125`), fourteen months stale. I did not cite it for behaviour; the July memo §2.9 (which read current main in 2026-07) stands in. The clone should be re-cloned before any future study.

### 11. What the live vfs tree does with a bytes row today `[EXECUTED]`

`experiments/s8/vfs_bytes_row_probe.py`, run with `uv run python -I`:

- `Result.to_str()` on a read with a text row and a bytes row prints `==> /photos/pixel.png <==` followed by an **empty body**. There is no placeholder anywhere in `src/vfs/results/render.py` (grep for placeholder/mime/data finds only error-data plumbing); `_render_read` prints `o.content or ""` (`render.py:311-320`). The "canonical placeholder for media" the brief states as law is not implemented in the renderer.
- `Result.to_payload()` serializes the row's `data` as base64 inline (`"data": "iVBORw0KGgo..."`), because `Observation.model_config` sets `ser_json_bytes="base64"` (`src/vfs/models/entry.py:419-420`). `from_payload` round-trips it exactly. A 1 MiB image becomes ~1.4 M characters of `structuredContent`; a 10,000-row batch with projected bytes is unbounded.
- Per spec 152 §1, a read never fetches bytes unless the caller projects the `data` column; `content` of a bytes entry holds its rendering (the image metadata header of §8). So in the common case a `read` of a PNG returns text (the rendering) plus `mime_type`, `size_bytes`, `content_hash`, `version`; bytes arrive only on request. The adapter therefore sees `data` populated only when the caller asked for it — the July memo's "adapter never fetches" rule is already structurally true.

### 12. The experiment, end to end `[EXECUTED]`

`experiments/s8/mcp_blocks_experiment.py` (run: `uv run --with mcp --with jsonschema python -I <script> ~/Git/Repos/modelcontextprotocol/schema`; `mcp 2.3.0`, `mcp-types 2.3.0`, `jsonschema 4.26.0`, Python 3.13). One tool `read` with an `outputSchema`, returning `[TextContent(rendered table + placeholder line), ImageContent(1×1 PNG, annotations, _meta{dev.vfs/path, dev.vfs/version}), ResourceLink(vfs:///clips/intro.mp4, mimeType video/mp4, size)]` plus `structuredContent` shaped like a `Result.to_payload()`, and a `resources/read` handler returning a `blob`. Driven three ways through a logging relay:

| Session mode | Negotiated | Wire methods | `tools/call` result valid against |
| --- | --- | --- | --- |
| `"2026-07-28"` (pinned) | 2026-07-28 | `tools/call`, `tools/list`, `resources/read` (no handshake) | 2026-07-28, 2025-11-25, 2025-06-18; response valid as `JSONRPCResultResponse` |
| `"auto"` | 2026-07-28 | `server/discover`, then the same | same |
| `"legacy"` | 2025-11-25 | `initialize`, `notifications/initialized`, then the same | 2025-11-25, 2025-06-18; **invalid** against 2026-07-28 (`resultType` missing); `resources/read` also lacks `ttlMs`, `cacheScope` |

The modern wire (`wire_auto.jsonl`) shows the request `_meta` (`protocolVersion`, `clientInfo`, `clientCapabilities: {}`) and the result `_meta["io.modelcontextprotocol/serverInfo"]`, `resultType: "complete"`, `ttlMs: 0`, `cacheScope: "private"` on the read and list results. Hand-built instances: a `video` block, a `resource_link` without `name`, an `image` without `mimeType`, `priority: 1.5` and `audience: ["system"]` are rejected; an embedded blob resource without `mimeType`, a scalar `structuredContent`, `isError: true` beside an image block, and a reserved `_meta` prefix are accepted (the last by the schema only — prose forbids it). The fixture labels the PNG as "67 B"; its decoded length is 70 bytes (the schema does not care; the vfs probe reports 70).

### 13. July memo re-verification

| Memo claim | Status today |
| --- | --- |
| §2.5 five-block union, stable across 2025-11-25 and draft | Still true for 2026-07-28 and its (empty) draft; field sets unchanged since 2025-06-18 (Findings 2, 5). |
| §2.5 `structuredContent` beside `content`, with a SHOULD to restate as text | True; `structuredContent` is now any JSON value, and the SHOULD stands (Finding 3). |
| §2.5 no normative ordering sentence; blocks unkeyed; no merge story | Still true; nothing in 2026-07-28 orders or keys blocks. |
| §2.5 `resource_link` + `resources/read` is the spec's elide mechanism; fetching needs `resources` | True; now with `-32602` not-found, `ttlMs`/`cacheScope`, and `subscriptions/listen` (Finding 4). Also: no studied client fetches a link (Finding 9). |
| §2.5 embedded blob rendering is client-discretionary | Unchanged wording (schema.ts:1727-1730). |
| §2.5 `isError` is for model-visible self-correction | Unchanged; the 2025-11-25 SEP-1303 clarification strengthens it (Finding 3). |
| §2.5 fastmcp base64-in-text anti-pattern | Still present at `tools/base.py:515-520` (Finding 7). |
| §2.6 provider physics (audio unlandable on Claude/OpenAI; jpeg/png/webp intersection; Claude Code 25k tokens incl. images) | Claude Code figures re-confirmed from the live docs, plus new facts: originals saved to disk, 50k-char persist threshold, 16 MiB transport cap, `anthropic/maxResultSizeChars` (Finding 8). Provider APIs not re-fetched (out of scope per the task). |
| §4 Q2 adopt the five blocks verbatim; vfs keys in `_meta` | Still the right call; `_meta` key grammar now binds the prefix (Finding 2). |
| §4 Q6 one canonical placeholder enforced at the render chokepoint | Not yet implemented; a bytes row renders empty (Finding 11). |
| §4 Q7 raw mime inside, closed accept-list at the boundary | Spec still names no accept-list for content blocks; the only list is for icons (Finding 2). Claude Code's documented inline set is PNG/JPEG/GIF/WebP (Finding 8). |
| §6 items 6–9 (placeholder grammar, adapter, accept-lists, budgets) | All still open; this report proposes 6 and 7 below and scopes 8 and 9. |

## What this means for vfs

Terms: a *row* is an `Observation`; the *adapter* is the one function that turns a `Result` into a `CallToolResult`; *projection* is that mapping; the *placeholder* is the one-line text that stands in for bytes in any text stream.

### A. The vocabulary vfs adopts

Exactly the five blocks of 2026-07-28, every field named as the schema names it (`mimeType`, `isError`, `structuredContent`, `resultType`), and no sixth block of our own. Unknown block types arriving from a peer are preserved raw and degraded to a placeholder, never dropped — the existing unknown-kind doctrine. The adapter emits `resultType: "complete"` itself only if the SDK layer does not (the Python SDK stamps it on modern sessions and omits it on legacy ones, which is what each revision's schema wants).

### B. The row→block projection table

Inputs per row: `content` (text source, or a bytes entry's rendering), `data` (populated only when the caller projected it), `mime_type`, `size_bytes`, `path`, `kind`, `version`, `content_hash`. "Accepted image" = `image/png`, `image/jpeg`, `image/webp`, `image/gif` (the four Claude Code documents inline; `gif` is in that set, the July memo's three-way provider intersection is not — a fork below). "Budget" = the adapter's inline media budget (fork below).

| Row shape | Text block (always) | Typed block | `_meta` on the typed block |
| --- | --- | --- | --- |
| text source (`content` set, `data` None) | rendered as today | none | — |
| bytes entry, `data` **not** populated (the default read) | rendering + placeholder line | none at v1 (the text names path, mime, size, version; the agent re-reads with `columns={"data"}`) | — |
| bytes entry, `data` populated, accepted image, within budget | placeholder line | `ImageContent{data, mimeType}` | `dev.vfs/path`, `dev.vfs/version` (prefix is a placeholder until a domain is chosen) |
| accepted image over budget, or image mime outside the accepted set | placeholder line | `ResourceLink{uri: vfs:///<path>, name: basename, mimeType, size, description: placeholder}` | same |
| `audio/*` within budget | placeholder line | `AudioContent{data, mimeType}` | same |
| `audio/*` over budget | placeholder line | `ResourceLink` | same |
| `video/*`, `application/pdf`, `application/octet-stream`, any other binary | placeholder line | `ResourceLink` (never an embedded blob at v1) | same |
| `image/svg+xml`, any `text/*` stored as bytes | its rendering as text | none | — |
| directory, edge, version rows | rendered as today | none | — |
| classified errors | rendered errors section, as today | none | — |

Block order: **one `TextContent` first** holding the whole rendered `Result` (table, headers, placeholders, errors), then the typed blocks in row order. Rationale from Finding 9: opencode and gemini-cli destroy interleaving, codex and Claude Code keep it, two harnesses may show the model only `structuredContent` — so order cannot carry meaning, the text block must be sufficient alone, and each typed block must be self-describing through its `_meta` path. Annotations: `audience: ["user", "assistant"]` and `priority` are harmless but no studied client reads them (`[INFERRED]` from the four conversions, none of which touches `annotations`); emit `lastModified` from `updated_at` on `ResourceLink`s because it is free, and nothing else at v1.

### C. The `isError` rule

`isError = not result.success` — true only when a fatal error is present. A result with rows plus warnings is `isError: false` with the errors rendered in the text block and present in `structuredContent.errors`. An empty row set with no fatal error is `isError: false`. Protocol errors (JSON-RPC) are reserved for what the spec lists: an unknown tool, a request that fails the `CallToolRequest` schema, a server crash; a vfs classified refusal (`invalid`, `not_found`, `denied`) is a tool execution error, exactly the SEP-1303 reading ("input validation errors ... enable model self-correction"). Two consequences from Finding 9: on `isError: true` opencode keeps **only the text parts**, and Claude Code shows the text as the error message with middle truncation past ~11k chars — so the text block of an error result must lead with the classified errors, compactly, before any rows. The SDK skips output-schema validation on error results (`python-sdk:src/mcp/client/client.py:865`), so `structuredContent` may stay on error results too.

### D. `structuredContent` and `outputSchema`

`structuredContent = Result.to_payload(...)` with **row bytes stripped** and `"data"` removed from each row's `populated` mask, so `from_payload` rebuilds an honest "not fetched" row. Finding 11 shows the current `to_payload` inlines base64 — that must change at the adapter before anything else, or a projected-bytes batch is unbounded on the wire. Bytes travel only in typed blocks, under the budget. `outputSchema` is `Result.model_json_schema()` (2020-12, which pydantic emits); the spec's MUST-conform then binds the adapter to the same serializer `to_payload` uses — one serializer, as the memo required. The spec's SHOULD "also return the serialized JSON in a TextContent block" is not followed: vfs's text block is the rendered table because that is the agent-facing surface and because two clients already substitute the structured payload for the text (Finding 9) — restating JSON in text would double the tokens in the others for nothing.

### E. `resources` at v1, and the URI scheme

Implement the capability minimally, because a `resource_link` is a promise ("a URI that can be subscribed to or fetched by the client") and the spec says servers that embed resources SHOULD declare it:

- `capabilities.resources: {}` (no `subscribe`, no `listChanged`).
- `resources/list` → empty (explicitly allowed; the catalog is the filesystem, reached through `glob`/`ls`), `ttlMs: 0`, `cacheScope: "private"` (results vary by the caller's grants).
- `resources/templates/list` → one template `vfs:///{+path}`, `name: "vfs path"`.
- `resources/read` → `storage.read(path, columns={"data"})` with the caller's authority; a bytes entry returns one `BlobResourceContents{uri, mimeType, blob}`, a text entry one `TextResourceContents`; a directory returns its listing as `text/plain` with `mimeType: "inode/directory"` is tempting but a non-goal at v1; not found → `-32602` with `data.uri`; denied → `-32602` too (the spec gives no permission code; `[INFERRED]`).
- Subscriptions and `listChanged`: not at v1 (the stateless `subscriptions/listen` stream is a transport feature with no vfs consumer yet).

URI scheme: **`vfs:///<global path>`** — custom scheme per RFC 3986, empty authority, the global (mount-prefixed) path as the path. Not `file://`: although the spec allows `file://` for things that "behave like a filesystem" without being one, a client that fetches `file://` on its own would read the host's disk — the wrong store and a side door by implication (ADR 069). Not `https://`: the spec reserves it for links the client can fetch directly from the web. The scheme is also what the placeholder names, so an agent can hand it straight back to `read`.

### F. The placeholder grammar (proposal)

One line, ASCII, no newline, no `|` (it must sit inside a Markdown table cell), exact byte count (no human units — `Resource.size` is exact and token estimators want exact):

```
placeholder := "[" "binary" SP path SP mime SP size "B" SP "v" version [ SP "--" SP description ] "]"
path        := the row's global vfs path, as rendered elsewhere
mime        := the row's mime_type verbatim (never a guess)
size        := size_bytes as a decimal integer
version     := the row's version number
description := the first line of the bytes entry's rendering, cell-escaped, truncated to 80 chars
```

Examples: `[binary /photos/pixel.png image/png 70B v3 -- PNG 1x1 RGB]`, `[binary /clips/intro.mp4 video/mp4 10485760B v1]`. Checked against what dropping clients show (Finding 9): opencode shows a link as a bare URI and codex as JSON — both lose `description` and `size` — so the placeholder in the text block, not the link, is where path, mime and size must live; Claude Code may drop the link entirely, which the placeholder survives; gemini-cli's own `[Image: mime]` and `[Link to title: uri]` are the same shape. Enforcement point: `render.py`'s `_render_read` and the block/table formatters, as the memo's Q6 said — the renderer emits the placeholder for any row whose `source` is bytes, whether or not `data` is populated, so the text projection never depends on whether bytes were fetched.

### G. Budgets and sizes, in MCP terms only

The spec gives no number. The facts that bound a default: Claude Code's 25,000-token result cap *includes* image data and its 16 MiB transport cap; opencode's and codex's byte-based context accounting of images; the 10,000-row batch contract. So the budget is **per result, not per row**: a `read` of 10,000 images must emit at most the budget's worth of inline blocks and links for the rest, regardless of chunking. The value is a fork below.

### H. What to reject

- Any provider-specific adapter or accept-list beyond the four-mime image set and MCP's own shapes (the task's rule; the memo's Q7 intersection becomes a documented choice of *which* four, not a per-provider table).
- `EmbeddedResource` blobs as the carrier for non-image media at v1 (nothing renders them to a model except opencode, and then only `application/pdf`).
- Per-row interleaved blocks as the primary channel (two of four harnesses flatten them).
- Base64 in any text block, ever (fastmcp's `tools/base.py:515-520` is the cautionary line).
- Relying on `annotations` for anything load-bearing (no studied client reads them).

## Forks for the ADRs

1. **Inline media budget value.** Options: (a) 1 MiB raw per block and 4 MiB raw per result, host-tunable; (b) match the tightest documented client cap by tokens (Claude Code 25k tokens incl. images — not computable from bytes); (c) a count cap (first N images inline, the rest links). Lean **(a)** with a count cap of 8 as a second guard; bytes are what MCP and every studied client count, and the per-result rule keeps the 10k-batch contract.
2. **Accepted image set.** (a) PNG/JPEG/WebP (the July memo's provider intersection); (b) PNG/JPEG/GIF/WebP (what Claude Code documents inline, and what codex/opencode pass through by prefix). Lean **(b)**: it is the only list a studied MCP client publishes, and the adapter is MCP-only by rule.
3. **`EmbeddedResource` vs `ResourceLink` for non-image media.** (a) always `ResourceLink`; (b) `EmbeddedResource` blob within budget, link above; (c) blob only for `application/pdf`. Lean **(a)** at v1 — one carrier for "not inline", the link already has `mimeType` and `size`, and blobs reach a model in exactly one client.
4. **One text block + `structuredContent` vs per-row interleave.** Lean **one text block first, media after, keyed by `_meta` path** — the only shape that survives all four clients and the two that substitute `structuredContent` for `content`.
5. **Implement `resources` at v1?** (a) no, links are informational; (b) minimal: capability `{}`, empty list, one template, `read` by `vfs:///path`; (c) full with `listChanged`. Lean **(b)**: cheap, makes every link honest, and is the only way an agent on a client that *does* fetch (none today) could get bytes without a second tool.
6. **URI scheme.** `vfs:///<global path>` vs `file://`. Lean `vfs:///`, for the no-side-door reason in §E.
7. **`_meta` prefix.** vfs needs a reverse-DNS prefix it owns (`dev.vfs/` is a stand-in; any prefix with `mcp` or `modelcontextprotocol` as the second label is reserved). Decide the domain in the ADR.
8. **Should `to_payload` ever carry bytes?** (a) never on the wire (adapter strips); (b) a `include_bytes` flag for in-process use only. Lean **(a)** on the wire with the flag kept for the in-process round-trip tests that exist today.
9. **Client-specific `_meta` hints** such as `anthropic/maxResultSizeChars` on tools. They are legal MCP (`_meta` extension keys) but are one client's knob. Lean **no at v1**; revisit if a host asks.
10. **Error-result text shape.** Lean: on `isError: true`, the text block is the errors section first, rows after — because one client keeps only the text on error and another middle-truncates it.

## Sources

- `modelcontextprotocol@86f6e0c6` (2026-10-14): `schema/2026-07-28/schema.ts` (lines cited inline), `schema/2026-07-28/schema.json`, `schema/2025-11-25/schema.{ts,json}`, `schema/2025-06-18/schema.{ts,json}`, `schema/draft/schema.ts`; `docs/specification/2026-07-28/server/tools.mdx`, `.../server/resources.mdx`, `.../basic/index.mdx`, `.../changelog.mdx`, `.../deprecated.mdx`, `.../index.mdx`; `docs/specification/2025-11-25/changelog.mdx`; `docs/specification/draft/changelog.mdx`; `schema/2026-07-28/examples/{CallToolResult,ResourceLink}/*.json`.
- `python-sdk@754254c0` (2026-10-13): `src/mcp-types/mcp_types/version.py`, `_types.py`, `_v2026_07_28/__init__.py`; `src/mcp/server/runner.py`, `src/mcp/server/mcpserver/server.py`, `tools/base.py`, `utilities/func_metadata.py`, `utilities/types.py`, `resources/types.py`; `src/mcp/client/client.py`, `_memory.py`, `stdio.py`; `src/mcp/shared/memory.py`; `tests/client/test_client.py`, `tests/interaction/README.md`.
- `fastmcp@e2fcc41` (2026-10-08): `fastmcp_slim/fastmcp/utilities/types.py:268-500`, `fastmcp_slim/fastmcp/tools/base.py:95-190, 367-430, 498-600`.
- `claude-agent-sdk-python@aada024` (2026-10-15): `src/claude_agent_sdk/__init__.py:455-520`.
- `opencode@13263f30ed` (2026-10-16, `origin/dev`): `packages/core/src/mcp/client.ts:84, 429-444`; `packages/core/src/tool/mcp.ts:78-108`; `packages/core/src/aisdk.ts:565-640`; `packages/core/src/session/compaction.ts:835`.
- `codex@16e578d` (2026-10-15): `codex-rs/protocol/src/models.rs:2436-2575, 3515-3570`; `codex-rs/core/src/mcp_tool_call.rs:948-985`; `codex-rs/tui/src/history_cell/mcp_result.rs:52-110`; `codex-rs/core/src/context_manager/history.rs:1300-1345`; `codex-rs/core/src/tools/context_tests.rs:133`.
- `gemini-cli` at d42e3f1e7: DIRTY and replaced by an unrelated project; not used (Finding 10). gemini-cli behaviour cited from `context/research/2026-07-25-multimodal-result-content.md` §2.9.
- vfs: `src/vfs/models/entry.py:393-480`, `src/vfs/results/envelope.py:316-380, 723-770, 799-810`, `src/vfs/results/render.py:42-70, 296-322`, `src/vfs/base.py` (`read`/`write` signatures), `context/specs/active/152-binary-bodies-and-text-renderings/spec.md` §1, §7, §8, §10; `context/research/2026-07-25-multimodal-result-content.md` §2.5, §2.6, §2.9, §4, §6; `context/open-questions.md` ("Result content must be typed blocks").
- Web, fetched 2026-10-15: Claude Code MCP docs `https://code.claude.com/docs/en/mcp` (output limits, "Images in tool results", "Use MCP resources", `anthropic/maxResultSizeChars`); community bug mirror `https://claudeissues.com/issue/53453-bug-mcp-resource-link-silently-ignored-pdf-blobs-not-processed-and-no-docs-on-su` (Claude Code 2.1.117, closed not planned 2026-05-29); web searches for codex and Claude Code changelog entries (none found on `resource_link`/`audio`; codex PRs #9815 and #5600 are image-ordering and image-to-model fixes).
- Experiments: `experiments/s8/mcp_blocks_experiment.py` + `.out`, `wire_2026-07-28.jsonl`, `wire_auto.jsonl`, `wire_legacy.jsonl`; `experiments/s8/vfs_bytes_row_probe.py` + `.out`. PyPI versions used: `mcp 2.3.0`, `mcp-types 2.3.0`, `fastmcp 4.1.0`, `jsonschema 4.26.0`.
