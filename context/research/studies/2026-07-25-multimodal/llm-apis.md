# Model-API ground truth: what tool results can actually contain

- **Subject**: the physics the multimodal Result design must obey — per-provider
  rules for media in tool results (Anthropic Messages, OpenAI Responses, Google
  Gemini), the MCP spec's block contract, and observed harness behavior.
- **Date**: 2026-07-25. Sources: official provider docs (fetched today), the
  MCP spec checkout at `~/Git/Repos/modelcontextprotocol` (2025-11-25 revision),
  and the `opencode` checkout (harness conversion code, read directly).

## What it is

Every frontier model API now has a typed-content-block channel for tool
results. This was not true two years ago: OpenAI tool results were
string-only until the Responses API added image/file parts, and Gemini
function responses were JSON-only until the Gemini 3 series. Anthropic's
Messages API has allowed blocks in `tool_result` the longest. The three
providers converged on the same shape — a tool result is *either a plain
string or an ordered array of typed parts* — which is precisely the shape
MCP standardized. The physics below is what each channel accepts, what it
costs, and what real harnesses do between MCP and the model API.

---

## 1. Anthropic Messages API

### What a tool_result may contain

`tool_result.content` is optional and is either a **string** or a **list of
content blocks** of types **`text`, `image`, `document`, or `search_result`**
([handle-tool-calls](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls)):

> `content` (optional): The result of the tool, as a string …, a list of
> nested content blocks …, or a list of document blocks … These content
> blocks can use the `text`, `image`, `document`, or `search_result` types.

- **No audio.** The Messages API has no audio content block anywhere — not
  in user content, not in tool results. An open SDK feature request
  (Feb 2026) confirms audio input "is currently not available as a content
  type" ([anthropic-sdk-python#1198](https://github.com/anthropics/anthropic-sdk-python/issues/1198)).
- The docs show an interleaved example (`text` block, then `image` block)
  inside a single `tool_result`, plus a documents example (`document` with
  `source: {type: "text", media_type: "text/plain", data: ...}`).
- `is_error: true` marks failures; error text goes in `content`.
- Structural rules (400 on violation): tool_result blocks must immediately
  follow their tool_use message, and must come FIRST in the user message's
  content array — any text comes after all tool results.

### Image sources and mimes

([vision docs](https://platform.claude.com/docs/en/docs/build-with-claude/vision))

- Sources: `base64`, `url`, `file` (Files API `file_id`; beta header
  `files-api-2025-04-14`). On Bedrock/Vertex only base64.
- Supported formats — exactly four: `image/jpeg`, `image/png`, `image/gif`,
  `image/webp`. "Animations are unsupported, and only the first frame is
  used." `media_type` is an enum in the API schema; a mime outside the list
  is not expressible and the request is rejected (`invalid_request_error`),
  not silently dropped.

### Limits

- Max dimensions 8000×8000 px per image; **if a request has more than 20
  image (and, on Bedrock/Vertex, document) blocks, a stricter per-image cap
  applies** — resize to ≤2000 px per side or images are "rejected with an
  `invalid_request_error` whose message references 'many-image requests'".
- Max size per image: 10 MB base64 on the Claude API (5 MB on
  Bedrock/Vertex); request body cap 32 MB.
- Max images per request: **100** (200k-context models), **600** otherwise;
  20 per message on claude.ai.

### Token cost (current model — supersedes the (w·h)/750 rule)

The brief cites Anthropic's old `(width*height)/750` estimate. The current
documented model is **patch-based**: "Each patch is a 28×28-pixel block …
An image costs `⌈width/28⌉ × ⌈height/28⌉` visual tokens", with two
resolution tiers:

| Tier | Models | Max long edge | Max visual tokens |
|---|---|---|---|
| Standard | pre-4.7 models | 1568 px | 1568 |
| High-resolution | Claude 4.7+ | 2576 px | 4784 |

Documented examples: 200×200 → 64 tokens; 1000×1000 → 1296; 1920×1080 →
1560 (std) / 2691 (hi-res); 3840×2160 → 1560 (std, downscaled) / 4784
(hi-res). Oversized images are auto-downscaled to fit the tier, which caps
cost. So on current Claude models **one screenshot ≈ 1.5k–4.8k input
tokens** — the ceiling roughly tripled with the high-res tier.

### Ordering

Ordering is preserved and meaningful. The vision guide: "Claude works best
when images come before text. Images placed after text or interpolated with
text still perform well" — and the documented multiple-image pattern is
interleaved labels (`Image 1:` text block, image block, `Image 2:` …),
which only makes sense if in-array order reaches the model.

## 2. OpenAI Responses API

### What a function_call_output may contain

([function-calling guide](https://developers.openai.com/api/docs/guides/function-calling),
[API reference](https://developers.openai.com/api/reference/resources/responses/methods/create))

- `output` is "typically a string, where the format is up to you (JSON,
  error codes, plain text, etc.)" **or an array of content parts** of types
  `input_text`, `input_image`, `input_file` — "For functions that return
  images or files, you can pass an array of image or file objects instead
  of a string."
- **No `input_audio` part in function outputs.** Audio input exists only in
  message content for audio-capable models.
- `input_image` carries `image_url` (an https URL **or** a
  `data:image/…;base64,` data URL) or a Files-API `file_id`
  (`purpose: "vision"`), plus a `detail` parameter.
- Note the legacy contrast: Chat Completions `tool` messages remain
  text-only; typed media in tool results is a Responses-API capability.
  This is why older harnesses smuggled screenshots in as user messages.

### Image mimes and limits

([images-vision guide](https://developers.openai.com/api/docs/guides/images-vision))

- Formats: PNG, JPEG, WEBP, **non-animated** GIF.
- "Up to 512 MB total payload size per request", "up to 1500 individual
  image inputs per request".

### Token cost — two regimes by model family

- **Patch models (32×32 px)** — gpt-5-mini/nano, gpt-4.1-mini/nano,
  o4-mini: `⌈w/32⌉×⌈h/32⌉` patches, capped at a **1536-patch budget**
  (image shrunk by `√((32²×1536)/(w×h))` if over), then multiplied:
  ×1.62 (mini family), ×2.46 (nano family), ×1.72 (o4-mini).
- **Tile models (512×512 px)** — gpt-4o, gpt-4.1, gpt-5.x flagship,
  o-series: scale into 2048×2048, shortest side to 768, count 512-px
  tiles: **85 base + 170/tile** (gpt-4o/gpt-4.1 class), 2833+5667
  (gpt-4o-mini), 75+150 (o1/o3), 65+129 (computer-use-preview).
- gpt-5.6 with `detail: "original"`/`"auto"` "uses the original patch
  count without resizing … to a patch budget".

Ballpark: a full-detail 1024×1024 image ≈ 765 tokens on gpt-4o class;
up to ~2.5k–3.8k effective tokens on mini/nano patch models at budget.

## 3. Google Gemini API

### What a functionResponse may contain

([function-calling docs](https://ai.google.dev/gemini-api/docs/function-calling),
[Vertex reference](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/models/function-calling))

- Baseline (all models): `functionResponse.response` is a **JSON object**.
- **Gemini 3 series only**: "you can include multimodal content in the
  function response parts" — media goes in `parts` **nested inside the
  functionResponse part** (`FunctionResponsePart` containing a
  `FunctionResponseBlob` with `inlineData` = mime + base64). Interactions-
  API form: `function_result.result` is an array of typed blocks
  (`{"type":"text",...}`, `{"type":"image","mime_type":...,"data":...}`).
- Cross-referencing: a multimodal part gets a unique `displayName`, and the
  structured JSON response can point at it with `{"$ref": "<displayName>"}` —
  a documented **link between structured content and a media block**, unique
  among the three providers.
- Documented best practice: "move multimodal content inside function
  response parts, not alongside them" (i.e. not as sibling user parts).
- Pre-Gemini-3 models: JSON only; media has no landing spot in a tool
  result (harnesses historically appended it as a separate user turn).

### Media mimes, limits, cost

([image understanding](https://ai.google.dev/gemini-api/docs/image-understanding),
[audio](https://ai.google.dev/gemini-api/docs/audio))

- Image mimes: `image/png`, `image/jpeg`, `image/webp`, `image/heic`,
  `image/heif` (note: **no GIF**, unlike Anthropic/OpenAI; adds HEIC/HEIF).
- Limits: up to **3,600 image files per request**; inline base64 counts
  toward a **20 MB total request** cap; Files API for anything larger or
  reused.
- Image cost: **258 tokens flat if both dims ≤ 384 px**; otherwise tiled
  into 768×768 tiles at **258 tokens per tile** (crop unit
  `floor(min(w,h)/1.5)`; e.g. 960×540 → 6 tiles ≈ 1548 tokens).
- Audio (the only provider of the three that can hear a tool's audio):
  `audio/wav`, `audio/mp3`, `audio/aiff`, `audio/aac`, `audio/ogg`,
  `audio/flac`; **32 tokens per second** (1 min = 1,920 tokens); up to
  9.5 hours per prompt; downsampled to 16 kbps mono.

## 4. The MCP spec's contract (2025-11-25)

From the checkout, `schema/2025-11-25/schema.ts`:

- `ContentBlock = TextContent | ImageContent | AudioContent | ResourceLink
  | EmbeddedResource` (schema.ts:1742-1747); `CallToolResult.content:
  ContentBlock[]` — an ordered array (schema.ts:1890).
- Image and audio blocks are base64 `data` + **free-form `mimeType`**, with
  the spec's only nod to provider reality in a doc comment: "The MIME type
  of the image. **Different providers may support different image types**"
  (schema.ts:1778-1800, same wording for audio at 1809-1830).
- The sampling side mirrors it: `ToolResultContent.content` "has the same
  format as CallToolResult.content and can include text, images, audio,
  resource links, and embedded resources" (schema.ts:~1875-1890).
- `structuredContent` coexists with `content`; "For backwards
  compatibility, a tool that returns structured content SHOULD also return
  the serialized JSON in a TextContent block"
  (docs/specification/2025-11-25/server/tools.mdx:326).
- **Routing hints, not rules**: every content block supports `annotations`
  with `audience: ["user"|"assistant"]` and `priority` 0.0–1.0; clients
  "can use these annotations to filter … prioritize … " — permissive, no
  MUST (server/resources.mdx:318-346).
- **The spec is silent on unsupported media.** Grepping the whole
  2025-11-25 spec for unsupported-content handling finds nothing about
  tool-result media a model can't accept — no drop rule, no placeholder
  rule, no capability negotiation for result modalities. What happens to
  an `audio` block sent to a Claude-backed client is entirely the
  harness's choice.

## 5. What real harnesses actually do (the boundary-rendering story)

- **gemini-cli** (official docs,
  [docs/tools/mcp-server.md](https://github.com/google-gemini/gemini-cli/blob/main/docs/tools/mcp-server.md)):
  supports "rich, multi-part content, including text, images, audio" in one
  tool response, but the documented conversion is: "1. Extract all the text
  and combine it into a single functionResponse part for the model.
  2. Present the image data as a separate inlineData part." — i.e.
  **interleaving is destroyed at the harness**: all text is fused into one
  part, media hangs off the side.
- **opencode** (read directly): `session/prompt.ts:773-807` walks
  `result.content`: `text` → `textParts` (later `join("\n\n")` and
  truncated via `Truncate.output`); `image` → data-URL attachment;
  `resource` → text or blob attachment; **`audio` and `resource_link`
  blocks are silently dropped — no case handles them, no placeholder is
  emitted.** Then `session/message-v2.ts:442-473` renders the model-facing
  tool output as one text block followed by media blocks. Again: text
  fused, order lost, attachments after.
- **Claude Code** ([MCP docs](https://code.claude.com/docs/en/mcp)): images
  in MCP tool results are supported and sent to the model, but "Tools that
  return image data are still subject to `MAX_MCP_OUTPUT_TOKENS`" (default
  **25,000 tokens**, warning at 10,000; `anthropic/maxResultSizeChars`
  raises only the *text* budget). At ~1.3k–4.8k tokens per image, a
  handful of images consumes the entire default MCP result budget.

## 6. Lessons for vfs (numbered against the brief)

**Q2 — block vocabulary.** MCP's five block types are a strict superset of
what any provider accepts. The provider-truth table:

| Capability | Anthropic | OpenAI Responses | Gemini |
|---|---|---|---|
| text in tool result | yes | yes (`input_text`) | yes (JSON/text) |
| image in tool result | yes | yes (`input_image`) | Gemini 3+ only |
| audio in tool result | **no (no audio at all)** | **no** | Gemini 3+ (inferred from blob mimes) |
| document/file in tool result | yes (`document`) | yes (`input_file`) | via inlineData |
| URL sourcing | yes | yes | no (inline/Files API) |
| file-ID sourcing | yes (Files API) | yes | yes (Files API) |

Adopting MCP's taxonomy (`text`/`image`/`audio` + mime + base64, plus
resource links) makes projection mechanical, but the design must assume
**every provider consumes a subset** and the harness decides the remainder.
An `audio` block reaching an Anthropic-backed harness has *no possible
landing spot*; only a text placeholder can represent it.

**Q4 — ordering.** The model APIs preserve and reward interleaving
(Anthropic documents image-then-text preference and interleaved labeled
sequences; OpenAI/Gemini accept ordered part arrays). But the two harnesses
whose conversion code/docs are observable (gemini-cli, opencode) both
**collapse interleaving** — text fused into one part, media appended.
Conclusion for vfs: preserve order in the envelope and the MCP projection
(that is the wire contract), but make each media block's *text vicinity*
self-describing (caption/placeholder naming the figure) so meaning survives
a harness that reorders. Do not build semantics that only work if the
harness preserves position.

**Q5 — budgets (real numbers).** Per image: **~64–4,784 tokens on Claude**
(28-px patches, hi-res cap 4784), **85–~1,100 typical on gpt-4o-class**
(tiles), up to ~3.8k on nano-class patch models, **258–~2,000 on Gemini**
(768-px tiles at 258). Audio on Gemini: 32 tokens/second. Claude Code caps
a whole MCP result at 25k tokens *including image data*. The brief's
elide-with-placeholder, media-on-request default is strongly validated: 5–10
uncapped images can exceed an entire tool-result budget, and provider-side
auto-downscaling means sending pixels above the tier cap (1568/2576 px long
edge on Claude, 2048/1536-patch on OpenAI, 768-tiles on Gemini) is pure
waste — the seam should downscale before base64.

**Q7 — mime reality.** The image intersection across all three providers is
exactly **`image/jpeg`, `image/png`, `image/webp`** (GIF: Anthropic+OpenAI
only, first-frame/non-animated; HEIC/HEIF: Gemini only). Audio: Gemini's
six types only. MCP's `mimeType` is deliberately free-form, and the spec
explicitly acknowledges providers differ — but Anthropic *enum-validates*
`media_type` and 400-rejects anything else, so pass-through of an arbitrary
mime is not merely droppable, it can poison the whole request. vfs must
classify at the seam: emit a media block only for the known-good set,
transcode or placeholder the rest. Silent dropping is the observed harness
default (opencode drops audio/resource_link without a trace) — vfs should
do better and emit the deterministic text placeholder instead.

**Q6 — stdout rule (supporting evidence).** Every provider's docs warn the
same physics the brief states: base64 in a text stream is token noise (the
Anthropic audio feature request states it exactly: bytes in a text block
give the model "no audio modality to perceive"). No provider offers any
mechanism to see media through text. The one-deterministic-placeholder rule
has no counterexample in provider land.

**On the brief's stance (break from Unix).** The industry's direction is
the strongest evidence: all three providers *independently added* typed
content parts to tool results (OpenAI in the Responses API, Gemini in the
Gemini 3 series, Anthropic from early on), and Gemini even added a
`$ref`/displayName link from structured JSON to media blocks — the exact
"typed content channel beside structured content" shape the brief proposes
for `Result`. Raw-text-only tool output is now the legacy shape at every
provider. The caveat the physics adds: the typed channel is *per-provider
lossy* (audio, mimes, budgets), so the design needs the text projection not
as a fallback for old CLIs but as the **guaranteed-delivery channel** every
media block degrades to when the harness or provider can't carry it.

## Citation index

- Anthropic tool_result content types & examples:
  https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls
- Anthropic vision (mimes, limits, 28-px patch cost, tiers, ordering):
  https://platform.claude.com/docs/en/docs/build-with-claude/vision
- Anthropic audio absence: https://github.com/anthropics/anthropic-sdk-python/issues/1198
- OpenAI function outputs: https://developers.openai.com/api/docs/guides/function-calling
- OpenAI Responses API reference (output part types):
  https://developers.openai.com/api/reference/resources/responses/methods/create
- OpenAI vision (mimes, limits, patch/tile costs):
  https://developers.openai.com/api/docs/guides/images-vision
- Gemini function calling (multimodal function responses, Gemini 3):
  https://ai.google.dev/gemini-api/docs/function-calling
- Gemini function-calling reference (FunctionResponsePart/Blob, $ref):
  https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/models/function-calling
- Gemini image understanding: https://ai.google.dev/gemini-api/docs/image-understanding
- Gemini audio: https://ai.google.dev/gemini-api/docs/audio
- MCP schema: ~/Git/Repos/modelcontextprotocol/schema/2025-11-25/schema.ts:1742-1890
- MCP tools spec: ~/Git/Repos/modelcontextprotocol/docs/specification/2025-11-25/server/tools.mdx:225-340
- MCP annotations: ~/Git/Repos/modelcontextprotocol/docs/specification/2025-11-25/server/resources.mdx:318-346
- gemini-cli rich content: https://github.com/google-gemini/gemini-cli/blob/main/docs/tools/mcp-server.md
- opencode conversion: ~/Git/Repos/opencode/packages/opencode/src/session/prompt.ts:773-807,
  ~/Git/Repos/opencode/packages/opencode/src/session/message-v2.ts:442-473
- Claude Code MCP output limits: https://code.claude.com/docs/en/mcp
