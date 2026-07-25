# MCP's tool-result content model — the exact wire target

> Subject study for the multimodal Result content brief
> (`context/research/2026-07-25-multimodal-result-content-brief.md`).
> Primary sources: `~/Git/Repos/modelcontextprotocol` (spec repo, current
> stable revision **2025-11-25**; repo HEAD `fb8438ce` 2026-04-19, draft
> checked for divergence), `~/Git/Repos/python-sdk` (official SDK, HEAD
> 2026-04-14), `~/Git/Repos/fastmcp` (v3 layout, `fastmcp_slim/`, HEAD
> 2026-07-09). Supersedes the content-block coverage of the 2026-04-19
> general MCP studies.

## 1. What it is

MCP's `tools/call` response is `CallToolResult` — **two parallel channels
in one result** plus a boolean verdict:

```ts
export interface CallToolResult extends Result {
  content: ContentBlock[];                        // REQUIRED, "unstructured"
  structuredContent?: { [key: string]: unknown }; // optional typed JSON
  isError?: boolean;                              // default false
}
```
(`schema/2025-11-25/schema.ts:1106-1132`)

`content` is the model-facing channel: an ordered array of typed blocks
the host renders into the LLM conversation. `structuredContent` is the
machine channel, optionally governed by the tool's `outputSchema`. The
draft schema's `CallToolResult` and `ContentBlock` union are **identical**
to 2025-11-25 (`schema/draft/schema.ts:1549-1587`, `:2323-2328`) — this
shape is stable.

## 2. The data model — full block taxonomy, exact fields

`ContentBlock = TextContent | ImageContent | AudioContent | ResourceLink |
EmbeddedResource` (`schema/2025-11-25/schema.ts:1742-1747`).

| Block | Discriminator | Payload fields | Extras |
|---|---|---|---|
| `TextContent` | `type:"text"` | `text: string` | `annotations?`, `_meta?` (schema.ts:1754-1771) |
| `ImageContent` | `type:"image"` | `data: string` (base64, `@format byte`), `mimeType: string` | `annotations?`, `_meta?` (schema.ts:1778-1802) |
| `AudioContent` | `type:"audio"` | `data: string` (base64), `mimeType: string` | `annotations?`, `_meta?` (schema.ts:1809-1833) |
| `ResourceLink` | `type:"resource_link"` | everything from `Resource`: `uri` (required), `name` (required, from `BaseMetadata`), `title?`, `description?`, `mimeType?`, `size?`, `icons?` | `annotations?`, `_meta?` (schema.ts:1046-1048, 804-840, 530-545) |
| `EmbeddedResource` | `type:"resource"` | `resource: TextResourceContents \| BlobResourceContents` — `{uri, mimeType?, text}` or `{uri, mimeType?, blob(base64)}` | `annotations?`, `_meta?` (schema.ts:1058-1071, 883-921) |

Notable field facts:

- **`Resource.size`** is "the size of the raw resource content, in bytes
  (i.e., before base64 encoding)… can be used by Hosts to display file
  sizes and **estimate context window usage**"
  (schema.ts:829-834). The spec itself ships the budget signal the brief's
  question 5 asks for.
- **Every block carries `annotations?` and `_meta?`.** `_meta` is the
  sanctioned extension slot (prefix rules keep keys collision-free) — a
  place vfs could stash a path key on a bare `ImageContent` without
  leaving the wire contract.
- The sampling side has two extra block types (`ToolUseContent`,
  `ToolResultContent`, schema.ts:1695-1700, 1840-1897) that are **not**
  in the tool-result union; `ToolResultContent.content` reuses
  `ContentBlock[]` + `structuredContent` — blocks are the universal
  tool-result currency in both protocol directions
  (schema.ts:1874-1897).

Python SDK mirrors this 1:1 with snake_case + camelCase aliases
(`alias_generator=to_camel`, `python-sdk/src/mcp/types/_types.py:39-42`):
`TextContent`/`ImageContent`/`AudioContent` at `_types.py:883-932`,
`EmbeddedResource` at `:1028`, `ResourceLink(Resource)` at `:1045`,
`ContentBlock` union at `:1054`, `CallToolResult` at
`:1198` (`content: list[ContentBlock]` required, `structured_content:
dict | None`, `is_error: bool = False`).

## 3. structuredContent and content coexisting

The spec's coexistence rule is one sentence: *"For backwards
compatibility, a tool that returns structured content SHOULD also return
the serialized JSON in a TextContent block"*
(`docs/specification/2025-11-25/server/tools.mdx:326`). The worked
example (tools.mdx:371-393) shows exactly that: the same weather JSON
appears twice — once stringified in `content[0].text`, once as
`structuredContent`.

Contract around `outputSchema` (tools.mdx:328-334):

- Servers **MUST** produce `structuredContent` conforming to the schema.
- Clients **SHOULD** validate it. The python-sdk client goes further: if
  a tool declared an output schema and returns no `structuredContent`,
  the client **raises** (`RuntimeError`), and jsonschema-validates when
  present (`python-sdk/src/mcp/client/session.py:319-348`). Declaring a
  schema makes the structured channel effectively mandatory.

What clients do when both are present is **not specified**. There is no
"prefer structuredContent" rule; the SHOULD-duplicate rule exists
precisely so a content-only client loses nothing. In practice hosts
forward `content` to the model and treat `structuredContent` as
programmatic surface. FastMCP demonstrates the tolerated deviation: its
Prefab UI results put the placeholder string `"[Rendered Prefab UI]"` in
`content` and the real payload in `structuredContent`
(`fastmcp_slim/fastmcp/tools/base.py:519, 557-562`) — the "text block"
does not have to be the serialized JSON; it has to be *a useful text
projection*.

`isError` semantics (schema.ts:1117-1131, tools.mdx "Error Handling"):
tool-execution failures **SHOULD** be reported *inside* the result with
`isError: true`, not as JSON-RPC errors, explicitly "otherwise the LLM
would not be able to see that an error occurred and self-correct."
Protocol errors are reserved for not-finding-the-tool-class failures.
SEP-1303 (Final) extended this: even input-validation failures are tool
execution errors, for the same self-correction reason
(`docs/seps/1303-input-validation-errors-as-tool-execution-errors.mdx`).
`isError` is a bare boolean — no severity, no kind, no locus. All error
*structure* must ride in content/structuredContent.

## 4. Ordering — implied by the array, never stated

**The spec contains no normative sentence about content-array ordering.**
Grepping all of `docs/specification/2025-11-25/` for
"order/ordered/ordering" finds nothing about `content`; the only ordering
language anywhere near tools is a *draft* addition requiring
deterministic `tools/list` ordering for prompt-cache hits
(`docs/specification/draft/server/tools.mdx:58-61`). Ordering of content
blocks is carried entirely by JSON array semantics: hosts render blocks
in sequence because there is nothing else to do, but no client is
contractually obliged to preserve interleaving.

Corroborating structure: `PromptMessage.content` is a **single**
`ContentBlock` (schema.ts:1034-1037) — in prompts, interleaving happens
across the message list; in tool results, the `content` array is the
only interleaving mechanism that exists. Both SDK conversion pipelines
preserve source order and never sort or group
(python-sdk `func_metadata.py:519-525` flattens nested lists with
`chain.from_iterable`, order intact; fastmcp `base.py:576-588` converts
mixed lists item-by-item "without aggregating them").

Consequence for vfs: order preservation is *achievable* (arrays are
ordered end-to-end) but *defended by nobody* — the Result representation
must own it, and cannot cite MCP text if a host reorders.

## 5. Annotations — the underused audience/priority facility

```ts
export interface Annotations {
  audience?: Role[];        // ("user" | "assistant")[]
  priority?: number;        // 0.0–1.0; 1 = "effectively required", 0 = "entirely optional"
  lastModified?: string;    // ISO 8601
}
```
(schema.ts:1707-1737; `Role` at :1024)

Docs: annotations "provide hints to clients about how to use or display"
content; clients can "filter resources based on their intended audience"
and "prioritize which resources to include in context"
(`docs/specification/2025-11-25/server/resources.mdx:318-346`). Every
tool-result content type supports them (tools.mdx:233-239 Note), e.g. an
image block annotated `{"audience": ["user"], "priority": 0.9}`
(tools.mdx:258-264).

This is a wire-native answer to the brief's model-vs-human channel
split: `audience: ["user"]` = display-only (don't spend vision tokens),
`audience: ["assistant"]` = model-facing, `priority` = the elision dial.
Two hard caveats from the sources:

- They are **hints** and untrusted (the ToolAnnotations warning at
  tools.mdx:212-215 is about tool-level annotations, but the same
  trust posture runs through content annotations: "It is up to the
  client how best to render", schema.ts:1051-1055).
- Neither SDK sets them by default anywhere in the conversion paths;
  fastmcp merely plumbs a user-supplied `annotations` through its
  `Image`/`Audio`/`File` helpers (`utilities/types.py:251, 306, 369`).
  Host honoring is inconsistent — annotations are an *optimization*
  channel, not a correctness channel.

## 6. Resources as media-by-reference

`resource_link` is the spec's own elide-with-placeholder mechanism: "A
tool MAY return links to Resources… the tool will return a URI that can
be subscribed to or fetched by the client" (tools.mdx:278-296), with the
explicit carve-out that links returned by tools "are not guaranteed to
appear in the results of `resources/list`" (schema.ts:1040-1043) — ad
hoc, per-result URIs are legal. A link carries exactly the placeholder
fields the brief's question 5 enumerates: `uri`, `name`, `description`,
`mimeType`, `size`, `annotations.lastModified`.

Embedded resources are the by-value-with-address form: the payload
(`text` or base64 `blob`) plus its `uri` and `mimeType`
(tools.mdx:297-317); "Servers that use embedded resources SHOULD
implement the `resources` capability". Rendering is explicitly
client-discretionary (schema.ts:1051-1055) — an embedded PNG blob is
**not guaranteed** to reach the vision encoder; `ImageContent` is the
only image shape whose whole purpose is model visibility.

URI schemes (`resources.mdx:348-385`): `https://` only when the client
can fetch it directly itself; `file://` "for resources that behave like
a filesystem" that "do not need to map to an actual physical
filesystem", with XDG mime types like `inode/directory` for non-regular
files; `git://`; custom schemes per RFC 3986. vfs paths slot into
`file://` semantics directly, or a custom `vfs://mount/path` scheme —
both sanctioned. The dereference path is `resources/read` returning the
same `TextResourceContents | BlobResourceContents`, so link → fetch →
embedded round-trips through one content vocabulary.

## 7. Mime-type reality

The schema deliberately refuses to enumerate: "The MIME type of the
image. **Different providers may support different image types**"
(schema.ts:1788-1791, same for audio :1820-1822). MCP passes any mime
through; narrowing to what a model API accepts (jpeg/png/gif/webp…) is
the *host's* problem. FastMCP's guessing shows the practical posture:
extension-based guess, `image/png` default for raw bytes, `audio/wav`
default, `application/octet-stream` fallback
(`fastmcp_slim/fastmcp/utilities/types.py:269-281, 336-350, 396-410`);
its `File` helper routes `text/*` to `TextResourceContents` (decoded
text) and everything else to `BlobResourceContents`
(`utilities/types.py:436-452`) — a mime-driven text-vs-blob fork at the
seam, which is the shape of the brief's SVG-passes-as-text rule.

## 8. How frameworks convert return values (prior art for vfs projection)

**python-sdk MCPServer** (`func_metadata.py:499-530`, `:91-124`):
`None → []`; `ContentBlock → as-is`; `Image`/`Audio` helper → block;
`list/tuple → flatten recursively` (order preserved); `str → TextContent`
verbatim (not JSON-quoted); anything else → `pydantic to_json` →
`TextContent`. Structured content is produced **only** when a return
annotation yields an output schema; non-object returns are wrapped as
`{"result": ...}` (`wrap_output`). `CallToolResult` returned by the
function passes through untouched (with schema validation of its
`structured_content`, `func_metadata.py:106-110`), and `CallToolResult`
in a `Union` return annotation is rejected outright
(`func_metadata.py:273-280`). Uncaught tool exceptions become
`CallToolResult(content=[TextContent(str(e))], is_error=True)`
(`server/mcpserver/server.py:316`).

**fastmcp** (`fastmcp_slim/fastmcp/tools/base.py`):

- `_convert_to_content` (:565-591): `None → []`; single value → one
  block; a list that is *all* ContentBlocks → as-is; a *mixed* list →
  per-item conversion, order kept, "without aggregating"; a list with
  *no* blocks → the whole list JSON-serialized into **one** TextContent.
- `_convert_to_single_content_block` (:490-516): ContentBlock pass;
  `Image → ImageContent`; `Audio → AudioContent`; `File →
  EmbeddedResource`; `str → TextContent`; **`bytes` → utf-8 decode, else
  base64 into a TextContent** (:508-514) — the exact anti-pattern the
  brief's question 6 exists to forbid: invisible token noise as the
  silent fallback for binary.
- `convert_result` (:296-353): `ToolResult` passthrough; raw `bytes` →
  content-only; ContentBlock-ish values skip `structuredContent` unless
  an output schema demands it; otherwise `to_jsonable_python`, with
  dict-only structured when no schema, and `{"result": ...}` wrapping
  driven by an `x-fastmcp-wrap-result` marker in the schema plus a
  `meta={"fastmcp": {"wrap_result": True}}` breadcrumb.
- `ToolResult` (:89-171): `content` required (or synthesized from
  `structured_content`); `is_error` and `meta` force the long-form
  `CallToolResult` return so they survive to the wire (:155-171).
- The `Image`/`Audio`/`File` helpers (`utilities/types.py:243-452`) are
  path-or-bytes constructors with mime guessing and optional
  `annotations` — the ergonomic layer that lets tool authors "return an
  image" with no wire knowledge. This is the role the brief's question 8
  assigns to the `run` verb's projection duty.

## 9. Lessons for vfs, numbered against the brief

1. **Where blocks live** — MCP itself runs *two coexisting channels in
   one envelope*: typed JSON (`structuredContent`) beside ordered
   blocks (`content`), with a SHOULD that the text channel restates the
   structured one. That is structurally identical to vfs's
   `to_payload()` + `to_str()` split, and it means Result does **not**
   have to choose between rows and blocks: rows stay the structured
   channel; an ordered content channel projects beside them. The 057
   worry "optional dual channels rot" is answered in MCP by making one
   channel derived-by-default (every framework auto-derives the text
   block from the value); vfs can make the text projection of media
   blocks equally automatic (placeholder rule), so the channels cannot
   disagree.
2. **Block vocabulary** — adopt MCP's five shapes and field names
   exactly (`text`; `data`+`mimeType` for image/audio; `uri`-bearing
   link and embedded forms). The union is stable across 2025-11-25 and
   draft; projection becomes identity. Extension needs go in `_meta`
   (vfs-prefixed keys), which both SDKs round-trip.
3. **Keying/algebra** — MCP offers *no* prior art: blocks are anonymous,
   unkeyed, never merged. The only blocks with a natural key are the
   uri-bearing ones (`ResourceLink`, `EmbeddedResource.resource.uri`) —
   evidence for keying vfs media blocks by path/uri, or for carrying the
   path in `_meta` on a bare `ImageContent`. Whatever `+` does to blocks
   is vfs's own law; the wire only requires that projection emit one
   ordered array.
4. **Ordering** — the array is ordered but the contract is silent; both
   SDK pipelines preserve order and nothing more. vfs must treat order
   as its own invariant (concatenate in op order is consistent with all
   observed practice) and must not depend on hosts honoring
   interleaving for correctness.
5. **Budgets** — the spec has built-in support for
   elide-with-placeholder: `resource_link` with `uri`, `name`,
   `description`, `mimeType`, `size` (explicitly for "estimating context
   window usage") is the placeholder; `resources/read` is the fetch; and
   `annotations.priority` (0–1) is the importance dial. vfs's
   media-on-request posture can be expressed *in wire vocabulary*
   instead of invented. Caveat: serving the fetch side requires the
   `resources` capability on the vfs MCP server.
6. **The stdout rule** — fastmcp's bytes→base64-into-TextContent
   fallback (:508-514) is the documented anti-pattern; fastmcp's Prefab
   placeholder text beside real structuredContent (:519, 557-562) is the
   documented *pattern*: a deterministic, human/model-readable text
   stand-in in the text channel while the true payload rides the typed
   channel. The spec's backwards-compat SHOULD legitimizes the text
   channel being a projection, not the source of truth.
7. **Mime reality** — the wire is deliberately open ("different
   providers may support different types"); pass mime through intact and
   let the harness police model-API acceptance. The seam's only mime
   decision is block *species* (text vs image vs audio vs blob), which
   fastmcp's `File` text/*-fork already models.
8. **Executed-code output** — both SDKs put conversion in the framework,
   not the tool author: author returns `Image(path=...)`/`Audio(...)`,
   framework guesses mime, base64s, and emits blocks. For vfs the `run`
   verb is that framework: sandbox artifacts (matplotlib PNG on a vfs
   path) become blocks in the verb's projection, never bytes on stdout.
9. **isError vs vfs errors** — `isError` is a lossy boolean projection
   whose *purpose* (spec text) is model-visible self-correction; all
   structure must travel elsewhere. vfs's derived `success` →
   `isError = not success` mapping already matches; severity, kind,
   locus, and demotion semantics survive only in `structuredContent`
   (and, for the model's eyes, in the text projection). Nothing in MCP
   pressures vfs to weaken its error model — it pressures vfs to keep
   errors *inside* the result, which the envelope already does.
10. **Audience annotations** — `audience`/`priority` on every block is
    the wire-native model-vs-human split (display-only artifacts vs
    model-facing evidence) but is hints-only, unset by every framework
    default, and inconsistently honored: use it as an optimization
    overlay on top of vfs's own budget doctrine, never as the mechanism
    that decides correctness.

## 10. Bearing on the "multimodal CLI" stance

The MCP wire is direct evidence *for* the owner's break-from-Unix
hypothesis: the protocol's model-facing channel is already an ordered
array of typed, mime-tagged blocks — text is just one block species, and
the spec's own error doctrine ("otherwise the LLM would not be able to
see that an error occurred", schema.ts:1122-1125) is premised on typed
in-band results rather than exit codes and stderr. Meanwhile the SDKs
show how the CLI *feel* is preserved: plain `str` returns become a text
block with zero ceremony (python-sdk `func_metadata.py:527-530`), and
media needs only a thin `Image(path=...)` wrapper. The one place the
Unix habit leaks back in — fastmcp base64-ing undecodable bytes into
text — is precisely the failure mode the stance names. What MCP does
*not* supply: block keying, merge algebra, ordering guarantees, or any
default use of audience annotations. Those are vfs's to define; the wire
constrains only the final projected shape.
