# Harness consumers of MCP content: gemini-cli and opencode

Study of how two production agent-CLI harnesses consume the MCP tool-result
content channel and forward it to model APIs. These are the consumers a vfs
MCP projection must satisfy.

Sources (all primary):

- **gemini-cli** local checkout `~/Git/Repos/gemini-cli`, HEAD `d42e3f1e7`
  (~Aug 2025). NOTE: the working tree of this checkout has been overwritten
  by an unrelated project; all local reads were done via `git show HEAD:...`
  against intact git objects. Current upstream `main` was fetched from
  raw.githubusercontent.com into the scratchpad
  (`scratchpad/fetched/mcp-tool-main.ts`, `tool-executor.ts`,
  `genContentUtils.ts`, `geminiChat.ts`, `models.ts`, `textUtils.ts`).
- **opencode** local checkout `~/Git/Repos/opencode`, HEAD `aef0e58ad7`
  (current, working tree intact).
- **@google/genai** (js-genai) `src/mcp/_mcp.ts` fetched from upstream main.
- **vercel/ai** provider types fetched from upstream main.

---

## 1. What they are

Both are agent harnesses that sit between (a) MCP servers + built-in tools
and (b) a model API. Both must solve the exact seam the vfs brief describes,
twice over:

- **inbound**: MCP `CallToolResult.content` (ordered typed blocks) → the
  model API's tool-result representation;
- **human-facing**: the same result → what the terminal/UI shows.

They differ in model seam: gemini-cli targets the Gemini
`functionResponse` shape (historically text-only); opencode targets the
Vercel AI SDK's `ToolResultOutput`, which *does* have a typed content
variant.

---

## 2. Data model at the tool boundary

### gemini-cli

A tool returns `ToolResult { llmContent: PartListUnion, returnDisplay:
string }` — one channel for the model (genai `Part`s: `{text}`,
`{inlineData:{mimeType,data}}`, `{fileData}`, `{functionResponse}`), one
pre-rendered string for the human. Dual channel, duplicated by every tool.

Built-in `read_file` on media (local checkout,
`git show HEAD:packages/core/src/utils/fileUtils.ts` lines ~334-349):
image/pdf/audio/video are read whole, base64'd into
`llmContent: { inlineData: { data, mimeType } }` with
`returnDisplay: "Read image file: <relpath>"`. File cap 20MB; SVG is passed
as *text* (≤1MB, "Read SVG as text"); binary files are refused with a text
message ("Cannot display content of binary file"). Type detection is
extension/mime first (`detectFileType`, fileUtils.ts ~120-196), then a
content sniff (nul byte, >30% non-printable ⇒ binary, fileUtils.ts ~60-95).

Current-main MCP tools declare an explicit discriminated union of MCP
blocks (`mcp-tool-main.ts:123-154`): `McpTextBlock`, `McpMediaBlock`
(`type: 'image' | 'audio'`, `mimeType`, `data`), `McpResourceBlock`
(`resource.{text?,blob?,mimeType?}`), `McpResourceLinkBlock`
(`uri`, `title?`, `name?`).

### opencode

The native tool contract is **one text string plus an unordered media
bag** (`packages/opencode/src/tool/tool.ts:34-40`):

```ts
execute(...): Promise<{
  title: string
  metadata: M
  output: string
  attachments?: MessageV2.FilePart[]
}>
```

`FilePart` carries `mime` + a `data:<mime>;base64,` URL. Built-in `read`
on an image/PDF (`packages/opencode/src/tool/read.ts:65-91`) returns
`output: "Image read successfully"` + one attachment with the full base64
data URL — *no size cap on the media branch*. SVG is excluded from the
image path (`file.type !== "image/svg+xml"`, read.ts:66-67) and flows as
text; binary files throw (`Cannot read binary file`, read.ts:94).

The persisted tool state (`packages/opencode/src/session/message-v2.ts:250-263`,
`ToolStateCompleted`) is `{ output: string, attachments?: FilePart[],
metadata, ... }` — **no ordered content array exists in storage**.

---

## 3. The inbound MCP path, traced

### gemini-cli, Aug-2025 checkout: media silently dropped

The SDK layer (`@google/genai` `McpCallableTool.callTool`, js-genai
`src/mcp/_mcp.ts` upstream main ~line 165-180) does **no block
transformation at all** — it stuffs the *entire* `CallToolResult` JSON
(base64 included) into a Gemini part:

```ts
functionCallResponseParts.push({
  functionResponse: { name, response: callToolResponse as Record<string, unknown> },
});
```

Then the Aug-2025 gemini-cli `convertToFunctionResponse`
(`git show HEAD:packages/core/src/core/coreToolScheduler.ts:141-200`) sees
a part with `functionResponse.response.content` and reduces it with
`getResponseTextFromParts` (`generateContentResponseUtilities.ts:26-38`),
which maps `part.text` and filters — MCP text blocks happen to have
`.text` so they survive; **image/audio blocks have no `.text` and are
silently deleted from what the model sees.** Meanwhile the human display
(`git show HEAD:packages/core/src/tools/mcp-tool.ts:150-180`)
JSON.stringify'd non-text content into a markdown code block — i.e. **raw
base64 dumped into the terminal**. This shipped for months.

### gemini-cli, current main: explicit per-block transform

`transformMcpContentToParts` (`mcp-tool-main.ts:512-541`) flatMaps the MCP
content array **in order**:

- `text` → `{ text: wrapUntrusted(block.text) }` — MCP text is wrapped in
  `<untrusted_context>` markers (`textUtils.ts` `wrapUntrusted`) as
  prompt-injection hygiene. Note the asymmetry: *media cannot be wrapped.*
- `image` / `audio` → **two parts**: an annotation text part
  `[Tool '<name>' provided the following image data with mime-type: …]`
  followed by `{ inlineData: { mimeType, data } }`
  (`mcp-tool-main.ts:456-473`). Provenance is fabricated as adjacent text
  because the block itself has no key.
- `resource` with `text` → text part; with `blob` → annotation +
  `inlineData` (mime defaulted to `application/octet-stream`)
  (`mcp-tool-main.ts:475-498`).
- `resource_link` → **flattened to text**:
  `Resource Link: ${title||name} at ${uri}` (`mcp-tool-main.ts:500-504`).
  Never fetched, never resolved.
- unknown block types → `null` → filtered out (dropped).

`structuredContent` is not consulted at all (no reference in the file).
Tool-level `isError` short-circuits into a text error message before any
transform (`mcp-tool-main.ts:311-325`).

### gemini-cli: the model seam destroys interleaving

Current `convertToFunctionResponse`
(`genContentUtils.ts:49` onward) re-buckets the ordered parts:

- all text parts are **joined with `\n` into a single
  `functionResponse.response.output` string** — text/media interleaving
  order is lost at the protocol seam;
- `inlineData` parts with `audio/*` or `video/*` mime are **stripped** —
  replaced by
  `[SYSTEM: Binary content (audio/mpeg) stripped from response due to
  protocol limitations.]` — because Gemini's function-response channel
  cannot carry them; for `read_file`/`read_many_files` they are instead
  stashed under a magic key `__binary_injection__`
  (`BINARY_INJECTION_KEY`, `genContentUtils.ts:18,146`);
- surviving image `inlineData` parts are placed **inside**
  `functionResponse.parts` only if
  `supportsMultimodalFunctionResponse(model)` — which is literally
  `model.startsWith('gemini-3-')` (`models.ts`); on older models they ride
  as **sibling parts after the functionResponse** in the same turn, with
  the text stub carrying `output` ("Binary content provided (N item(s))"
  when there was no text).

The `__binary_injection__` payload is later exhumed by
`geminiChat.extractBinaryInjections` (`geminiChat.ts:659-678`) and turned
into a **fabricated three-turn exchange** (`geminiChat.ts:456-490`):
(1) the cleaned tool response, (2) a synthetic model turn
`"Binary content received. Proceeding with analysis."` with a synthetic
thought signature, (3) the binary parts re-sent as the next user/info
message. This is the length a harness must go to when the protocol's
tool-result channel is text-shaped and the media is real.

### opencode: MCP blocks → text + attachment bag

The MCP client wraps each server tool via AI SDK `dynamicTool`; `execute`
returns the raw `CallToolResult` validated against `CallToolResultSchema`
(`packages/opencode/src/mcp/index.ts:120-148`). The session layer then
re-shapes it (`packages/opencode/src/session/prompt.ts:773-822`):

- `text` → pushed to `textParts` (later `join("\n\n")`);
- `image` → `FilePart` attachment with
  `url: data:${mimeType};base64,${data}`;
- `resource` → `resource.text` to textParts, `resource.blob` to an
  attachment (`filename: resource.uri` — the uri survives as filename);
- **`audio`: no branch — silently dropped.**
- **`resource_link`: no branch — silently dropped.**

The wrapper returns
`{ output: truncatedText, attachments, content: result.content /* directly
return content to preserve ordering when outputting to model */ }`
(prompt.ts:815-820) — but the persistence layer
(`packages/opencode/src/session/processor.ts:172-189`) stores only
`output`, `metadata`, `title`, `attachments`; `ToolStateCompleted` has no
`content` field. **The "preserve ordering" comment is vestigial: ordering
is lost the moment the result is persisted.**

### opencode: the model seam has a typed channel — and still flattens

`toModelOutput` (`message-v2.ts:442-472`) converts a completed tool part
to the AI SDK's tool-result output. With attachments present:

```ts
{ type: "content", value: [
    { type: "text", text: outputObject.text },        // ALL text, joined
    ...attachments.map(a => ({ type: "media", mediaType: a.mime,
                               data: /* base64 after the comma */ })),
] }
```

One text block first, then all media — interleaving lost even though the
target type supports arbitrary ordering. The target is the AI SDK
`LanguageModelV2ToolResultOutput`
(vercel/ai `packages/provider/src/language-model/v2/language-model-v2-prompt.ts:187`):

```ts
| { type: 'text'; value: string }
| { type: 'json'; value: JSONValue }
| { type: 'error-text' | 'error-json'; ... }
| { type: 'content'; value: Array<{type:'text';text} | {type:'media';data;mediaType}> }
```

i.e. the mainstream SDK's tool-result contract is *itself* a typed
content-block union — text OR json OR ordered text/media blocks — which
provider adapters map onto Anthropic `tool_result.content`, OpenAI, etc.

Model capability gating (`packages/opencode/src/provider/transform.ts:10-16,
200-233`): `mimeToModality` maps mime prefix → image/audio/video/pdf, and
unsupported parts are replaced with a *text* part
`ERROR: Cannot read "<file>" (this model does not support image input).
Inform the user.` — but this filter runs **only on user-role messages**;
media inside tool results bypasses it entirely.

---

## 4. Boundary rendering: what the human sees

- gemini-cli current (`getStringifiedResultForDisplay`,
  `mcp-tool-main.ts:551-584`): per-block deterministic placeholders,
  joined by newline — text verbatim, `[Image: image/png]`,
  `[Audio: audio/wav]`, `[Link to <title>: <uri>]`,
  `[Embedded Resource: <mime>]`, `[Unknown content type: X]`. The terminal
  never sees base64. (The Aug-2025 version JSON-dumped base64 — the fix
  was to invent exactly the placeholder rule the vfs brief proposes.)
- gemini-cli built-in read: `returnDisplay: "Read image file: <relpath>"`.
- opencode terminal TUI (`packages/opencode/src/cli/cmd/tui/`): **no
  attachment rendering at all** — grep for "attachment" returns nothing;
  the human sees only the text `output` ("Image read successfully").
- opencode web UI (`packages/ui/src/components/message-part.tsx:340-401`):
  image/PDF attachments render as `<img src="data:...">` thumbnails with a
  click-to-preview dialog; other mimes render a folder icon.

## 5. Budgets

Both harnesses budget **text only**; media is never truncated, resized,
or counted:

- gemini-cli (`tool-executor.ts:200-297`): a char-threshold truncation
  applies to (a) string shell output and (b) MCP results that are a
  *single text part*; overflow is written to a project temp file and the
  kept text carries a pointer (`formatTruncatedToolOutput`). A multi-part
  (media-bearing) result skips truncation entirely. Separate hard caps:
  20MB per read file, 1MB SVG-as-text.
- opencode (`packages/opencode/src/tool/truncation.ts:10-14, 50-…`):
  2000 lines / 50KB text budget; overflow saved under
  `<data>/tool-output` with 7-day retention, path returned in
  `metadata.outputPath`. The image attachment path has **no byte cap**.
- opencode compaction (`message-v2.ts:546-547`): old tool results become
  `"[Old tool result content cleared]"` and `attachments` are dropped —
  media is the first thing evicted from history.

## 6. Lessons for vfs, numbered against the brief

**Q1 (where blocks live).** Both consumers converge internally on
"text channel + typed media attachments", and both *lose* MCP's ordered
interleaving at either persistence (opencode) or the protocol seam
(gemini-cli). Neither keys media to anything — provenance is fabricated as
adjacent annotation text (gemini) or a `filename: resource.uri` field
(opencode). If vfs wants order and keying, the envelope must carry them
itself; no consumer will reconstruct either.

**Q2 (block vocabulary).** The empirically safe vocabulary is `text`,
`image`, `resource`(text|blob). `audio` is dropped by opencode and
stripped-with-note by gemini for non-read tools. `resource_link` is never
fetched by either — gemini flattens it to a text pointer, opencode drops
it. Emitting resource links is therefore only useful if the link text
itself is informative (uri + title in prose); embedded `resource` blocks
with `uri` are the only shape where a vfs path survives as data
(opencode keeps it as `filename`).

**Q3 (algebra/keying).** Consumers treat content as an append-only,
per-call, ordered list; no dedup, no keys, no merge. That is evidence for
treating blocks as message-like (op-ordered concatenation under `+`,
untouched by rebase) rather than as keyed row evidence.

**Q4 (ordering).** MCP's order survives exactly one hop (gemini's
`flatMap` transform) and is then destroyed by both model seams (text
joined into one string, media appended after). Only the newest path —
Gemini 3 nested `functionResponse.parts`, and the AI SDK `content`
variant if the producer chose to interleave — can preserve it. Emit
ordered blocks anyway: the seams are moving toward order-preserving
(gemini gates on `model.startsWith('gemini-3-')`), and flattening is
lossy but safe, while un-flattening is impossible.

**Q5 (budgets).** Neither consumer budgets media; both budget text with
overflow-to-file + pointer (the same doctrine the vfs envelope applies to
errors). vfs's proposed elide-with-placeholder / media-on-request default
would be *ahead* of both consumers, and compaction behavior (opencode
deletes attachments first) says media must always be re-fetchable by
path — a placeholder with path+mime+size is exactly what survives.

**Q6 (stdout rule).** Both harnesses independently invented the brief's
placeholder rule for the human channel — `[Image: mime]` /
`"Read image file: path"` — and gemini-cli shipped the failure mode first
(base64 JSON-dumped to terminal, Aug-2025 tree). Both also treat SVG as
text, exactly as the brief proposes.

**Q7 (mime reality).** Visibility is decided by mime *prefix* everywhere
(`startsWith('image/')`, `mimeToModality`). Unsupported classes are
handled at the seam with a deterministic text substitution naming the
mime (`[SYSTEM: Binary content (X) stripped…]`, `ERROR: Cannot read…`),
never a hard error — and gemini's audio/video smuggling (synthetic
three-turn `__binary_injection__` dance, `geminiChat.ts:456-490`) shows
what happens when a protocol channel can't carry a block type the model
could otherwise consume. Pass mime through intact; expect the harness to
classify; give it enough text to degrade gracefully.

**Q8 (executed-code output).** Neither harness has any path from program
stdout bytes to a media block — shell output is text, period; the only
media producers are read-file-style tools and MCP servers. A vfs `run`
verb that projects sandbox-produced media into typed blocks would be
genuinely novel among CLI harnesses.

## 7. Verdict on the owner's stance

The evidence from both consumers is strongly *for* typed blocks and
against raw-stdout piping: every layer that carries media as a typed
block works mechanically; every place media meets a text-shaped channel
it is dropped (Aug-2025 gemini; opencode audio), dumped as noise
(base64-in-terminal), stripped with apology, or smuggled via
protocol-abuse hacks (sibling parts, `__binary_injection__` synthetic
turns). The costs both harnesses pay — dual text/model channels
duplicated per tool, fabricated provenance text, vestigial
ordering-preservation comments — are exactly the costs a typed,
ordered, keyed content channel in the envelope would eliminate. The one
caution: even the best consumers flatten ordering and drop exotic block
types, so the vfs projection must degrade losslessly to
"text placeholder + separately fetchable media", not depend on consumers
honoring the full vocabulary.
