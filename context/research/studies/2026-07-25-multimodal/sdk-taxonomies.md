# Cross-provider SDK block taxonomies: LangChain standard content blocks & Vercel AI SDK message parts

Study for the multimodal Result content brief
(`context/research/2026-07-25-multimodal-result-content-brief.md`).
Primary sources: local checkouts `~/Git/Repos/langchain` (langchain-core v1)
and `~/Git/Repos/ai` (Vercel AI SDK, Apache-2.0). All citations are
repo-relative `file:line` under those roots.

Both teams faced exactly the brief's question 2: define a neutral content
block vocabulary and project it onto each provider's wire format. They chose
opposite architectures for *where the neutral form lives*, and their scars
are the most instructive part of the study.

---

## 1. What each is

**LangChain v1 standard content blocks** (`libs/core/langchain_core/messages/content.py`)
are TypedDicts forming a discriminated union `ContentBlock`
(content.py:845-853). A message is "a list of content blocks, allowing for
the natural interleaving of text, images, and other content in a single
ordered sequence"; "an adapter for a specific provider is responsible for
translating this standard list of blocks into the format required by its
API" (content.py:8-14). Crucially, the *stored* field on `BaseMessage` is
still the historical `content: str | list[str | dict]` (base.py:103); the
standard blocks are a **lazily derived view** via the `content_blocks`
property (base.py:199-260).

**Vercel AI SDK message parts** are two distinct persistent taxonomies with
an explicit one-way conversion:

- `UIMessage.parts` — UI/persistence layer: `TextUIPart`, `ReasoningUIPart`,
  `FileUIPart`, `SourceUrlUIPart`, `SourceDocumentUIPart`, `ToolUIPart`
  (typed per tool name as `tool-${NAME}`), `DynamicToolUIPart`,
  `DataUIPart` (`data-${NAME}`), `CustomContentUIPart`, `StepStartUIPart`
  (packages/ai/src/ui/ui-messages.ts:77-91).
- `ModelMessage` content parts — the model boundary: `TextPart`, `FilePart`,
  `ReasoningPart`, `CustomPart`, `ToolCallPart`, `ToolResultPart`
  (packages/provider-utils/src/types/content-part.ts).
- `convertToModelMessages()` maps the former to the latter
  (packages/ai/src/ui/convert-to-model-messages.ts:47), and each provider
  package maps ModelMessages to its wire format.

## 2. The data model

### 2.1 LangChain block list and field shapes

Union members (content.py:845-853, KNOWN_BLOCK_TYPES content.py:856-877):
`text`, `reasoning`, `tool_call`, `tool_call_chunk`, `invalid_tool_call`,
`server_tool_call`, `server_tool_call_chunk`, `server_tool_result`,
`image`, `audio`, `video`, `file`, `text-plain`, `non_standard`.

Common fields on every block: `type` (Literal discriminator), optional `id`
(provider-generated or `lc_`-prefixed UUID4, content.py:147-153), optional
`index` ("Index of block in aggregate response. Used during streaming",
content.py:240-241), optional `extras: dict[str, Any]` for
provider-specific metadata (content.py:243-244).

Media blocks (`ImageContentBlock` content.py:498-546, audio/video/file
analogous) carry **three mutually optional source fields plus mime**:

- `url: NotRequired[str]`
- `base64: NotRequired[str]` (mime "Required for base64 data",
  content.py:528-531)
- `file_id: NotRequired[str]` — "Reference to the image in an external file
  storage system. For example, OpenAI or Anthropic's Files API"
  (content.py:522-526)
- `mime_type: NotRequired[str]` with IANA reference.

Factory functions enforce "Must provide one of: url, base64, or file_id"
(content.py:1033-1035). Notably `create_image_block` *lacks* the
"mime_type required with base64" check that `create_video_block`,
`create_audio_block`, and `create_file_block` all have
(content.py:1037 vs 1099-1101, 1165-1167, 1231-1233) — per-modality
factory duplication drifting in practice.

`NonStandardContentBlock` (`{"type": "non_standard", "value": {...}}`,
content.py:790-828) is the catch-all; per-field provider extras go in
`extras`, with a stated plan to move to PEP 728 `extra_items=Any`
(content.py:40-46).

### 2.2 Vercel part list and field shapes

The model-boundary `FilePart` (content-part.ts:62-102) is the media
workhorse:

- `data: FileData | DataContent | URL | ProviderReference` — a **tagged
  discriminated union for the source**: `{type:'data'}` raw bytes,
  `{type:'url'}`, `{type:'reference'}` (provider file id from
  `uploadFile`), `{type:'text'}` inline text (content-part.ts:66-75;
  zod: prompt/content-part.ts:54-62).
- `mediaType: string` — required; may be a full IANA type, a top-level
  segment (`image`, `audio`), or a wildcard normalized to top-level
  (content-part.ts:83-94).
- optional `filename`, `providerOptions`.

**`ImagePart` is deprecated**: "Use `FilePart` with `mediaType: 'image'`
instead" (content-part.ts:29-31; zod prompt/content-part.ts:40-42). Vercel
converged all modalities into ONE media part discriminated by mediaType,
not by block type.

`FileUIPart` on the UI side has no raw-bytes field at all: media is a
`url` ("a URL to a hosted file or a Data URL") plus `mediaType`,
`filename`, and optional `providerReference` which "takes precedence over
`url` in model messages" (ui-messages.ts:180-219). Data URLs are the
base64 channel.

`CustomPart` is the escape hatch: `kind: \`${string}.${string}\`` (a
`provider.type` string) with all payload in `providerOptions`
(content-part.ts:127-141).

### 2.3 Tool results specifically

**LangChain**: `ToolMessage` has `content` (what the model sees) *and*
`artifact: Any` — "Artifact of the Tool execution which is not meant to be
sent to the model. Should only be specified if it is different from the
message content" (messages/tool.py:73-80); the docstring example puts
stdout in content and the image in artifact (tool.py:45-64). Media that
*should* reach the model goes in `content` as data blocks, and the
Anthropic partner recursively formats a tool_result's content by treating
it as a message: `_format_messages([HumanMessage(block["content"])])`
(libs/partners/anthropic/langchain_anthropic/chat_models.py:610-615).

**Vercel**: `ToolResultPart.output: ToolResultOutput` is a tagged union of
six shapes: `text`, `json`, `execution-denied`, `error-text`, `error-json`,
and `content` (content-part.ts:247-547). The `content` variant is an
ordered array restricted to `text | file | custom` (plus 8 deprecated
types, see §5). Success/error is encoded in the output *type*
(`error-text`/`error-json`), not a parallel flag — verdict and evidence
cannot disagree. The default projection from a tool's raw output is
`createToolModelOutput`: use the tool's optional `toModelOutput()` hook if
present, else `string → {type:'text'}`, anything else `{type:'json'}`
(packages/ai/src/prompt/create-tool-model-output.ts:16-30).

The AI SDK's own MCP client is the precedent for "raw output → typed
blocks at the boundary": `mcpToModelOutput` maps MCP `CallToolResult.content`
per-part — `text`→text, `image {data, mimeType}`→
`{type:'file', mediaType, data:{type:'data', data}}`, anything else →
`JSON.stringify` into a text part (packages/mcp/src/tool/mcp-client.ts:147-177).

## 3. The boundary-rendering story (neutral → provider wire), and what gets lossy

### 3.1 LangChain: wire format is stored; neutral is derived

Because `content` stores whatever the provider returned, `content_blocks`
must *guess provenance*: it wraps unknown dicts as `non_standard`, then runs
five sequential parsing passes — v0-multimodal, OpenAI Chat Completions,
Anthropic, Google GenAI, Bedrock Converse — each attempting to unpack
non_standard blocks (base.py:250-259). The Anthropic pass converts
`document`/`image` blocks by their `source.type`
(base64/url/file/text) into v1 `file`/`image`/`text-plain` blocks and
preserves unknown keys via `_populate_extras`
(block_translators/anthropic.py:29-139); anything unrecognized stays
`non_standard` (anthropic.py:451-458).

Outbound (v1 → Anthropic wire), `_format_data_content_block`
(partners/anthropic/chat_models.py:304-427):

- image url → `{"type":"image","source":{"type":"url",...}}`; data-URI urls
  parsed into base64 sources (304-318)
- image base64 → `source:{type:"base64", media_type, data}` (319-327)
- image file_id → `source:{type:"file", file_id}` (328-343)
- file → `document` block; missing mime defaults to `application/pdf`
  (353-370); `text-plain` → document with text source (403-411)
- **video → hard `ValueError`**: "Block of type video is not supported"
  (413-415). Unsupported source keys also raise (344-351).
- extras pass-through is a **whitelist**: only `cache_control`,
  `citations`, `title`, `context` survive to the wire (417-425). Everything
  else in `extras` is silently lost at this boundary.

### 3.2 Vercel: three providers, three degradation strategies

The same neutral `{type:'content'}` tool output degrades differently per
provider — the clearest evidence in either repo that the *wire* decides
whether media is visible:

- **Anthropic** (packages/anthropic/src/convert-to-anthropic-prompt.ts:455-590):
  maps parts natively — text→text; file with top-level mediaType `image` →
  `image` block (url or base64); `application/pdf` → `document` (+ beta
  flag); **any other file media type → warning + part dropped**
  (522-535: "unsupported tool content part type ... with media type",
  returns `undefined`, filtered out). `json` output → `JSON.stringify`
  (574-578); `is_error` from `error-*` types (585-588).
- **OpenAI Chat Completions**
  (packages/openai/src/chat/convert-to-openai-chat-messages.ts:318-347):
  tool message content is a plain string, so `content`, `json`, and
  `error-json` outputs are **all `JSON.stringify`'d** (327-331). A base64
  image in a tool result reaches GPT as token noise inside a JSON string —
  the exact failure mode the brief's "Why this exists" §1 names.
- **Google** (packages/google/src/convert-to-google-messages.ts:66-199):
  two code paths keyed by model generation. Gemini 3+: media parts ride
  *inside* `functionResponse.parts` as `inlineData` (71-138); text parts
  are joined with `\n` and an empty text set defaults to
  `"Tool executed successfully."` (128-131). Pre-Gemini-3 legacy: media is
  **hoisted out of the tool result** into top-level `inlineData` parts with
  a synthetic adjacent text part — "Tool executed successfully and returned
  this image as a response" (145-198) — i.e. the harness fabricates a
  text placeholder and moves the pixels somewhere the model can see them.

Provider-executed tool results are stricter still: Anthropic requires
`json`-typed output and emits an "unsupported" warning otherwise
(convert-to-anthropic-prompt.ts:876-889 and repeats at 938, 1072, 1135, 1174).

## 4. Ordering, streaming, and merge semantics

- Both taxonomies are **ordered arrays**; ordering is the representation.
  LangChain: "natural interleaving ... in a single ordered sequence"
  (content.py:10-11). Vercel: `UIMessage.parts: Array<...>`
  (ui-messages.ts:74), and `convertToModelMessages` walks parts in order,
  flushing an assistant "block" at each `step-start` boundary part
  (convert-to-model-messages.ts:405-421).
- Merge is **order-preserving concatenation, keyed only for streaming**:
  LangChain `merge_content` appends lists / concatenates trailing strings
  (base.py:366-406); `ToolCallChunk`s merge only when `index` values are
  equal and non-None (content.py:291-307). The `index` field is the
  streaming aggregation key, not an identity key. Neither SDK dedups or
  keys media blocks by content; block `id` exists for tracking, not merge.
- Vercel tool parts are a per-call **state machine**
  (`input-streaming → input-available → output-available | output-error |
  output-denied`, ui-messages.ts:279-382) keyed by `toolCallId` — identity
  lives on the call, not the content block.

## 5. Versioning and migration pain (the cautionary tales)

**LangChain's string-vs-list dual representation never died.** v1 still
stores `content: str | list[str | dict]` (base.py:103); `content_blocks`
transposes a bare string into `[{"type":"text",...}]` on every access
(base.py:225-233). Consequences visible in code:

- v0 multimodal blocks used the **same `type` values** (`image`, `audio`,
  `file`) with an extra `source_type` discriminator, so v1 parsing needs
  presence-guards: "Guard against v0 blocks that share the same `type`
  keys — if `source_type` in item → non_standard" (base.py:241-244), and
  `is_data_content_block` must accept both generations with special-cases
  (content.py:908-947). Lesson: reusing a discriminator value across
  schema generations forces field-sniffing forever.
- `PlainTextContentBlock` "existed in `langchain-core<1.0.0` ... the only
  shared keys between the old and new versions are `type` and `text`,
  though the `type` value has changed from `'text'` to `'text-plain'`"
  (content.py:654-659) — a rename to dodge its own text block.
- `.text()`-method → `.text`-property migration required `TextAccessor`, a
  `str` subclass whose `__call__` emits a deprecation warning
  (base.py:47-90).
- Opting into storing the standard format is a runtime flag,
  `output_version: 'v0' | 'v1'` read from env `LC_OUTPUT_VERSION`
  (language_models/chat_models.py:322-343) — the dual representation is
  now *configuration*.
- Because raw wire dicts are the stored truth, provenance is lost and the
  derived view must try five translators in sequence (base.py:250-259).

**Vercel's deprecation graveyard shows type-name proliferation.** The
tool-result `content` union still carries 8 deprecated members —
`file-data`, `file-url`, `file-id`, `file-reference`, `image-data`,
`image-url`, `image-file-id`, `image-file-reference`
(content-part.ts:359-533; zod prompt/content-part.ts:205-256) — all
collapsed into one `file` part whose *source* is the tagged `FileData`
union and whose *modality* is `mediaType`. Encoding source (data/url/id)
or modality (image/file) into the block-type name multiplied types
(2 modalities × 4 sources); making them orthogonal axes collapsed the
matrix. `ImagePart` itself is deprecated in favor of `FilePart`
(content-part.ts:29-31). The zod schemas must validate the deprecated
shapes indefinitely because persisted messages contain them.

## 6. Lessons for vfs, numbered against the brief

**Q1 — where blocks live.** Strongest signal in the study: *store the
neutral typed form and derive wire projections* (Vercel), never *store the
wire form and derive the typed view* (LangChain). LangChain's lazy
`content_blocks` with five guessing passes (base.py:250-259) is what the
057 doctrine "optional dual channels rot" looks like after four years:
`str | list`, `output_version`, `source_type` sniffing. Vercel's two
*mandatory* representations with a total conversion function
(`convertToModelMessages`) stay coherent because neither is optional and
conversion is one-way. LangChain's `ToolMessage.artifact`
(tool.py:73-80) is prior art for the brief's "media as evidence that
doesn't automatically cross the wire" — a separate full-output channel
distinct from model-visible content.

**Q2 — block vocabulary (adopt MCP's or define ours?).** Both defined
their own and projected — including onto MCP itself (Vercel's MCP client
converts MCP blocks into its neutral form, mcp-client.ts:147-177; the
neutral form then projects to Anthropic/OpenAI/Gemini). Two sub-lessons:
(a) Vercel's endpoint after deprecations is **one media block** (`file`)
with `mediaType` as the modality discriminator and a tagged source union
`data | url | reference | text` — mirroring vfs reality where a path's
bytes + stored mime already exist and "image vs audio" is derivable from
mime. LangChain's per-modality blocks duplicate fields and drift
(missing mime check in `create_image_block`). (b) Keep an explicit
escape hatch (`non_standard` / `custom` + `extras`/`providerOptions`)
so unknown provider content survives round-trips without being forced
into a lossy standard shape. MCP's `resource_link` maps naturally onto
the `url`/`reference` source arm — a vfs path-reference block is the
same idea with a vfs URI.

**Q3 — algebra/keying.** Neither SDK content-keys media blocks; both treat
block lists as ordered sequences that concatenate on merge
(merge_content base.py:366-406), with `index` only as a streaming
aggregation key (content.py:291-307) and `id` for tracking. Precedent
supports the brief's instinct: content is message-like, `+` concatenates
in op order, and rebase should not touch it. Identity that matters
(tool_call_id ↔ result; toolCallId state machine) lives *outside* the
block payload.

**Q4 — ordering.** Universally an ordered array; Vercel additionally
models explicit sequence boundaries as a part (`step-start`,
ui-messages.ts:249-251) rather than out-of-band structure — an option if
Result merge ever needs to preserve per-op grouping inside one content
list.

**Q5 — budgets.** LangChain's content/artifact split is the
elide-by-construction pattern: the expensive payload never enters the
model channel unless deliberately placed there. Google's legacy path
(convert-to-google-messages.ts:183-187) shows the harness synthesizing a
text placeholder next to relocated media — evidence that "placeholder
text + media elsewhere" is a normal, model-legible pattern. Neither SDK
has automatic size-based elision; that remains vfs's own doctrine to
apply.

**Q6 — stdout rule.** LangChain `.text` concatenates only `text`-typed
blocks and *ignores* media entirely (base.py:279-292) — deterministic but
information-destroying (a media-only message renders as empty string, no
placeholder). vfs's placeholder-form rendering is strictly better; the
precedent confirms one deterministic text projection is expected, and
warns against making it silently empty.

**Q7 — mime reality.** Vercel passes mime through the neutral layer
liberally (full type, bare top-level segment, or wildcard;
content-part.ts:83-94) and lets each *provider* adjudicate, with three
observed failure modes: native mapping (Anthropic image/pdf),
drop-with-warning (Anthropic other media,
convert-to-anthropic-prompt.ts:522-535), and stringify-to-noise (OpenAI
CC, convert-to-openai-chat-messages.ts:327-331). LangChain's Anthropic
partner instead hard-errors on unsupported modalities (video →
ValueError, chat_models.py:413-415). For vfs: pass mime intact, classify
at the projection seam, and prefer warning+placeholder over both silent
drop and hard error.

**Q8 — executed-code output.** `Tool.toModelOutput` (provider-utils
types/tool.ts:149) + `createToolModelOutput` defaults
(create-tool-model-output.ts:23-29) is the exact shape: the *verb/tool*
owns an optional projection from raw output to typed blocks, with a sane
default (string→text, else json). `mcpToModelOutput` shows the same duty
performed for a foreign runtime's output. In vfs terms: the `run` verb
owns projecting sandbox bytes into blocks, and unknown output degrades
deterministically (Vercel degrades to stringified JSON text — vfs should
degrade to a placeholder instead).

**On the brief's break-from-Unix stance.** The study is one long
confirmation: whenever these stacks let typed content collapse into a
string channel — OpenAI CC stringifying tool content, LangChain `.text`
dropping media, MCP-unknown blocks stringified — media becomes invisible
to the model, and every harness that *wants* multimodal tool results had
to build an ordered typed-block channel and keep it typed end-to-end.
The text case still gets zero-ceremony treatment in both SDKs (bare
string → text block transposition at the boundary: base.py:225-229,
create-tool-model-output.ts:27-29), which is precisely the "feels like a
CLI for text" property the owner wants: strings auto-lift into text
blocks; nothing auto-lowers media into strings.
