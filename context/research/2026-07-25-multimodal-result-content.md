# Multimodal Result content: typed content blocks for the wire

- **Status**: DRAFT research memo, for review — supersedes the
  [2026-07-25 brief](2026-07-25-multimodal-result-content-brief.md);
  commits us to nothing, feeds an ADR on the content channel.
- **Date**: 2026-07-25
- **Owner**: Clay Gendron
- **Question**: The `Result` envelope carries rows and errors —
  text-shaped evidence. Models are multimodal, and the MCP tool-result
  wire format is an *ordered array of typed content blocks* (`text`,
  `image`, `audio`, resource links). How does `Result` grow a typed
  content channel so verbs can emit media, results still chain under the
  algebra, and the wire projection emits MCP-shaped content arrays —
  without breaking the envelope's existing contracts?
- **Evidence gathered**: eleven parallel primary-source studies,
  committed alongside this memo under
  [studies/2026-07-25-multimodal/](studies/2026-07-25-multimodal/) —
  [PowerShell](studies/2026-07-25-multimodal/powershell.md),
  [nushell](studies/2026-07-25-multimodal/nushell.md) (including its
  in-tree MCP server), the
  [structured-shell lineage](studies/2026-07-25-multimodal/structured-shells.md)
  (murex, elvish, TermKit),
  [Jupyter's display protocol](studies/2026-07-25-multimodal/jupyter.md),
  the [MCP spec + python-sdk + fastmcp](studies/2026-07-25-multimodal/mcp.md),
  the [three frontier model APIs](studies/2026-07-25-multimodal/llm-apis.md),
  [cross-provider SDK taxonomies](studies/2026-07-25-multimodal/sdk-taxonomies.md)
  (LangChain v1, Vercel AI SDK), the
  [A2A protocol](studies/2026-07-25-multimodal/a2a.md), two production
  [harness consumers](studies/2026-07-25-multimodal/harness-consumers.md)
  (gemini-cli, opencode),
  [terminal graphics protocols](studies/2026-07-25-multimodal/terminal-media.md),
  and an adversarial
  [ground-truth study](studies/2026-07-25-multimodal/envelope.md) of the
  live envelope's invariant set.
- **Citation provenance**: citations are repo-relative to sibling
  checkouts under `~/Git/Repos/` unless prefixed, with two exceptions.
  **murex** has no local sibling (its checkout vanished mid-study);
  `murex:` cites resolve against upstream `github.com/lmorg/murex` at
  commit `8678ad8`. **gemini-cli**'s local working tree is overwritten by
  an unrelated project; its cites were read from the checkout's intact
  git objects (`git show HEAD:`, HEAD `d42e3f1e7`, ~Aug 2025) plus
  upstream `main` fetched from raw.githubusercontent.com on 2026-07-25
  (`mcp-tool-main.ts` etc. denote fetched current-main files). Our own
  code is cited from `src/vfs/` at commit 276d096.

---

## 1. Two corrections to the brief, then the shape of the answer

Ground truth first, because the brief itself has two errors that reshape
its questions:

- **There is no `+` operator on `Result`.** The algebra is `|` (union),
  `&` (intersection), `-` (difference), plus `Result.merge` (a pure fold
  of `|`) and `Result.merge_branches` (zero-progress demotion)
  (`src/vfs/results/envelope.py:449-529`). Every "does `+` concatenate
  content in op order" question must be re-asked as "what does `|` do" —
  and `|` already has pinned laws
  (`tests/test_result_laws.py:58-133`).
- **There is no MCP layer in `src/vfs` today.** `to_payload()` is
  documented as the future `structured_content` half
  (`envelope.py:640-641`); the content-array emitter is greenfield.
  There is no existing seam it conflicts with, only seams it must feed
  from.

And one fact that gates everything: **there is no binary channel
anywhere in the live tree.** `Entry.content` and `Observation.content`
are `str | None` with null-byte rejection (`src/vfs/models/entry.py:
132-139, 388`). A PNG cannot currently be stored, read, or observed.
The brief's "read of a PNG" presupposes a storage-side bytes story that
must be designed first; this memo treats that as a prerequisite, not a
detail.

The answer this memo argues, in one paragraph: the owner's
break-from-Unix stance is right and every studied system supports it,
but the lawful shape is narrower than "add a `content: list[ContentBlock]`
to `Result`." Media enters the envelope as **masked, path-keyed,
version-attested evidence on `Observation` rows** — bytes (or a
reference) plus the `mime_type` field that already exists — so the
merge algebra, rebase, per-item quarantine, projection narrowing, and
budget machinery all apply unchanged. In-document interleaving rides on
**`Match`-style anchored regions inside a row**, not on a new top-level
channel. The **ordered MCP block array is minted exactly once, by a
greenfield boundary adapter** that deterministically unrolls rows into
MCP's five-block vocabulary — blocks are a projection product, never
stored envelope state. The text projection emits **one canonical,
device-independent placeholder form** for any media (path + mime + size
+ description), enforced at the render chokepoint, and that placeholder
is not a nostalgic CLI affordance: it is the only guaranteed-delivery
channel the model-API physics leaves standing.

## 2. Prior art

Deep detail lives in the underlying studies, committed under
[studies/2026-07-25-multimodal/](studies/2026-07-25-multimodal/) and
linked per section; this section carries what bears on the decision.

### 2.1 PowerShell — twenty years of typed pipes, and the scars

PowerShell's pipeline never carries text between cmdlets; text exists
only in the FormatAndOutput subsystem, and the host injects
`Out-Default` at the end of every interactive pipeline
(PowerShell:src/Microsoft.PowerShell.ConsoleHost/host/msh/Executor.cs:
186-198) — which is why `ls` prints a table with zero ceremony. The
"multimodal CLI still feels like a CLI" ergonomic is proven at
production scale. Three findings bind the design:

- **The format→output interface is itself an ordered stream of typed
  blocks** — `FormatStartData`/`FormatEntryData`/`FormatEndData` packets
  designed to survive serialization boundaries, with out-of-band entries
  interleaving in order inside a document sequence
  (PowerShell:src/System.Management.Automation/FormatAndOutput/common/
  FormattingObjects.cs:4-153). Direct precedent for an ordered block
  array as a *projection product*.
- **Render blocks leaking into the pipeline is its most infamous
  defect**: `Format-Table | Export-Csv` emits serialized format packets,
  and `Out-Default` filters them by string-prefix match on the type name
  (FormatAndOutput/out-console/OutConsole.cs:106-115). Blocks as
  ordinary pipeline values, distinguishable only by convention, is what
  twenty years of that mistake looks like.
- **The native seam destroyed binary data for ~18 years** — everything
  crossing to/from native programs went through console-encoding text
  lines (engine/NativeCommandProcessor.cs:2038, 2078); the fix
  (`PSNativeCommandPreserveBytePipe`, engine/pipeline.cs:270-292,
  engine/BytePipe.cs) binds raw byte streams end-to-end, bypassing the
  object world. A typed pipeline that forces foreign output through
  text decoding destroys media, and retrofitting bytes-as-bytes is
  expensive.

Also instructive: the "one deterministic rendering" is
device-parameterized (80-col fallback, ANSI knobs —
FormatAndOutput/out-console/ConsoleLineOutput.cs:507,
FormatAndOutput/common/PSStyle.cs:642), causing display-width data loss
at semantic boundaries. A wire-facing canonical text rendering must be
width- and decoration-independent.

### 2.2 nushell — bytes-until-boundary, and the sidecar that rots

nushell's `ByteStream` carries a three-way coercion color
(Binary/String/Unknown) *on the stream itself*
(nushell:crates/nu-protocol/src/pipeline/byte_stream.rs:100-114), while
the precise mime lives in sidecar `PipelineMetadata.content_type`
(nu-protocol/src/pipeline/metadata.rs:21-28). The split is the
[nushell study](studies/2026-07-25-multimodal/nushell.md)'s central
lesson: the on-stream color survives everything; the sidecar
mime **dies at every materialization boundary** — storing a pipeline in
a variable keeps only the `Value` and drops all metadata
(nu-engine/src/eval_ir.rs:508-517), and every slicing command must
manually remember to clear the mime ("a slice is not the whole file;
drop MIME", nu-command/src/filters/first.rs:200-202). Media type must
live *inside* the value it describes, never beside it.

nushell also ships the exact seam this memo is about: an in-tree MCP
server (`nu --mcp`). Its choices are damning evidence *for* the brief's
stance:

- Every result is a single text block plus a `structured_content`
  mirror, despite the SDK supporting image blocks
  (nushell:crates/nu-mcp/src/evaluation.rs:497-502).
- Binary output is destroyed silently: ByteStreams collect through
  `String::from_utf8_lossy` with the mime discarded unread
  (evaluation.rs:745-786). `open photo.png` reaches the model as U+FFFD
  confetti. **Multimodal visibility does not fall out of a typed
  pipeline; it must be an explicit boundary contract.**
- Budgets, they got right: outputs over a limit (default 10KB,
  `NU_MCP_OUTPUT_LIMIT`) become a note pointing at a server-side
  `$history.N` handle holding the full value for later retrieval
  (evaluation.rs:18-19, 661-675) — elide-with-handle, proven ergonomic
  in production.
- Under `--mcp`, `print` goes to stderr, external stdin is nulled, and
  ANSI is disabled globally because "MCP is a computer-to-computer
  protocol" (evaluation.rs:272-275) — the runtime must know it is
  serving a protocol, not a terminal.

### 2.3 The structured-shell lineage — murex, elvish, TermKit

Three independent designers broke from raw-text pipes; none reverted
the typing; the failures were scope, mutable stream state, or
parallel-channel structure — never the typed-content idea.

- **TermKit (2011)** is the direct multimodal-CLI precedent: producers
  stay bytes-dumb ("you can `cat` a PNG and have it just work"),
  streams carry MIME headers, and a boundary formatter picks an output
  plugin by mime specificity (TermKit:Node/shell/formatter.js:51-68).
  Its `Content-Type` + `schema` parameter split
  (`application/json; schema=termkit.files`, formatter.js:373-377) is
  strong precedent for transport taxonomy plus orthogonal semantic
  annotation. It died of adoption scope — rewriting the whole toolchain
  plus a new UI before being useful — which falsifies only the
  strategy of demanding the world convert first.
- **elvish** carries two mandatory parallel bands per pipe (byte file +
  value channel, elvish:pkg/eval/port.go:17-21). It is the existence
  proof that *non-optional* dual channels do not rot — and the proof of
  what parallel channels cost: cross-band ordering is nondeterministic
  (documented at elvish:website/ref/language.md:977-985 and reproduced
  empirically — `put (echo a; put b; echo c; put d)` interleaves
  differently run to run), and band mismatch deadlocks (`range 40 |
  cat` hangs forever). **A dual-band design cannot express "figure 2
  appears after paragraph 3."** Decisive for ordering: one ordered
  sequence of typed items, not a text channel plus a media band.
- **murex** attaches one write-once mime-derived tag per byte stream;
  media mimes collapse to an opaque `bin` tag
  (murex:lang/define_mime.go:41-42) and render only at the `open`
  boundary, where a per-type openagent sniffs terminal capability and
  renders pixels inline, degrading to text
  (murex:config/defaults/profile_any.mx:701-795) — a small multimodal
  CLI shipping today. Its abandoned fd-3 experiment (externals
  self-declaring their type — fully written, commented out,
  murex:lang/exec.go:153-215) says executed programs will never speak
  the block protocol; the boundary must classify their bytes. Its
  spin-loop `GetDataType` with an in-code admission of fearing
  deadlocks (murex:builtins/pipes/streams/utils.go:42-46) says mutable
  type state on live streams is a hazard class a frozen envelope
  avoids entirely.

### 2.4 Jupyter — the stance shipped in 2011

Jupyter is fourteen years of deployed proof: executed code's stdout is
a text-only `stream` message forever, while rich values cross as typed
mime-keyed `display_data` bundles
(jupyter_client:docs/messaging.rst:1522-1529, 1554-1575). The terminal
frontend still feels like a plain REPL because every bundle carries a
**mandatory, un-disableable `text/plain` floor**
(messaging.rst:1686-1687; the one formatter that cannot be disabled,
ipython:IPython/core/formatters.py:659) — that floor *is* the brief's
stdout rule, in production since 2011. Findings that reshape the
questions:

- **Two axes, never conflated**: alternatives of one value are an
  *unordered selection set* (the mimebundle dict, consumer picks);
  distinct outputs are an *ordered sequence* (IOPub arrival order
  frozen into nbformat). And the sequence axis rests on transport
  arrival with a documented undefined case (async output after idle,
  messaging.rst:1748-1756) — order must live in the data structure,
  not the wire.
- **Identity arrived six years late** (`display_id`, protocol 5.1,
  opt-in, random, replace-all-matches, no merge —
  messaging.rst:1605-1653). Keying should be first-class from day one;
  vfs's path keys are structurally stronger than anything Jupyter had.
- **The bloat pathology is structural**: `Image` defaults to
  `embed=True` because notebook outputs have no address ("viewable
  later with no internet connection", ipython:IPython/core/display.py:
  923-930); every execution inlines fresh base64, and `transient`,
  `figure_formats`, and the strip-on-save ecosystem are the scar
  tissue. vfs has paths as native addresses — elide-with-placeholder is
  the correct inversion. The counter-risk: the link form broke
  QtConsole ("not able to display images if `embed` is set to `False`",
  display.py:932) — **a placeholder-by-default design needs a
  guaranteed fetch path or blocks become dead links.**
- The run-verb template: the kernel hooks the display path
  (`sys.displayhook` → `execute_result`, `display()` → `display_data`,
  matplotlib backend → bundle) while raw stdout stays a `stream` —
  typed output by hooking the runtime, never by parsing stdout.
- The honest counterweight: consumer-picks multi-representation
  bundles exist because Jupyter served many unknown frontends, and its
  producer hooks accreted three generations needing a four-rule
  precedence ladder (formatters.py:148-247). vfs has effectively one
  consumer class; producer-picked single representations with a text
  floor capture the value at a fraction of the machinery.

### 2.5 MCP — the exact wire target

Two earlier sibling memos —
[2026-04-19-mcp-specification.md](2026-04-19-mcp-specification.md) and
[2026-04-19-mcp-python-sdk.md](2026-04-19-mcp-python-sdk.md) — cover MCP
broadly but predate the content-block question; this section's schema
reads (2025-11-25, detailed in the
[mcp study](studies/2026-07-25-multimodal/mcp.md)) supersede them for
this topic.

`CallToolResult` runs **two coexisting channels in one envelope**:
required `content: ContentBlock[]` (model-facing) beside optional
`structuredContent` (typed JSON), with a backwards-compat SHOULD that
structured content also be restated as text
(modelcontextprotocol:schema/2025-11-25/schema.ts:1106-1132;
docs/specification/2025-11-25/server/tools.mdx:326). The block union is
exactly five shapes, stable across 2025-11-25 and draft: `text`,
`image`/`audio` (base64 `data` + free-form `mimeType`), `resource_link`
(uri, name, description, mimeType, `size` — documented explicitly for
estimating context-window usage, schema.ts:829-834), and embedded
`resource` (schema.ts:1742-1747). Every block carries `annotations?`
(`audience`, `priority` 0–1) and a `_meta` extension slot. Facts that
bind:

- **Ordering is implied by JSON array semantics and contractually
  defended by nobody** — no normative sentence in the whole spec covers
  content ordering. vfs must own interleaving order itself.
- **Blocks are anonymous and unkeyed; MCP has zero merge story.** The
  only naturally keyed blocks are the uri-bearing ones — pointing at
  path/uri as the natural key.
- `resource_link` + `resources/read` is the spec's own
  elide-with-placeholder mechanism; serving the fetch side requires the
  vfs MCP server to implement the `resources` capability.
- Embedded-blob rendering is client-discretionary ("it is up to the
  client how best to render", schema.ts:1051-1055) — **`ImageContent`
  is the only image shape whose purpose is model visibility**; media
  that must be seen projects there, not to blobs.
- `isError` is a lossy boolean whose stated purpose is model-visible
  self-correction ("otherwise the LLM would not be able to see that an
  error occurred", schema.ts:1122-1125) — vfs's derived
  `success → isError` mapping is exactly the intended pattern.
- fastmcp contains both the anti-pattern and the pattern for the stdout
  rule: undecodable bytes silently become base64 inside a `TextContent`
  (fastmcp:fastmcp_slim/fastmcp/tools/base.py:508-514 — invisible token
  noise), while its Prefab results put a placeholder string in
  `content` with the real payload in `structuredContent`
  (base.py:519, 557-562).

### 2.6 Model-API physics — what tool results can actually contain

All three providers converged on the same shape — a tool result is a
string OR an ordered array of typed parts — with typed media added
recently by OpenAI (Responses API `input_image`/`input_file`) and
Google (Gemini 3 `FunctionResponsePart` with `inlineData`), and
longest-standing on Anthropic (text/image/document/search_result in
`tool_result`). Raw-text-only tool output is now the legacy shape at
every provider. The physics that constrain the design (all web sources
fetched 2026-07-25; full citation index in the
[llm-apis study](studies/2026-07-25-multimodal/llm-apis.md)):

- **Audio is nearly unlandable**: Anthropic Messages has no audio
  modality anywhere
  ([anthropic-sdk-python#1198](https://github.com/anthropics/anthropic-sdk-python/issues/1198));
  OpenAI function outputs have no `input_audio`
  ([function-calling guide](https://developers.openai.com/api/docs/guides/function-calling));
  only Gemini 3+ can hear a tool's audio (32 tokens/second,
  [Gemini audio docs](https://ai.google.dev/gemini-api/docs/audio)). An
  audio block sent toward Claude or GPT can only survive as a text
  placeholder.
- **The safe image-mime intersection is exactly
  `image/jpeg` + `image/png` + `image/webp`.** Anthropic
  *enum-validates* `media_type` — a mime outside its list of four is not
  expressible in the API schema and the request is rejected with a 400
  `invalid_request_error`
  ([vision docs](https://platform.claude.com/docs/en/docs/build-with-claude/vision))
  — so passing an arbitrary mime through can poison the entire request,
  not merely be dropped.
- **Real image costs**: Claude 64–4,784 tokens per image (28-px
  patches, hi-res tier cap 4,784; a 1000×1000 image = 1,296 —
  [vision docs](https://platform.claude.com/docs/en/docs/build-with-claude/vision)),
  gpt-4o class 85 + 170/tile
  ([images-vision guide](https://developers.openai.com/api/docs/guides/images-vision)),
  Gemini 258/768-px tile
  ([image understanding](https://ai.google.dev/gemini-api/docs/image-understanding))
  — and Claude Code caps a whole MCP tool result at 25,000 tokens
  *including* image data (`MAX_MCP_OUTPUT_TOKENS`,
  [Claude Code MCP docs](https://code.claude.com/docs/en/mcp)). A
  handful of images exhausts the default budget. Provider-side
  auto-downscaling (1568/2576-px long edge on Claude, 2048-px box on
  OpenAI, 768-px tiles on Gemini) means pixels above the tier cap are
  pure request-size waste — the seam should downscale before encoding.
- Model APIs preserve and reward interleaved ordering (Anthropic
  documents image-before-text preference and interleaved labeled
  sequences,
  [vision docs](https://platform.claude.com/docs/en/docs/build-with-claude/vision))
  — but both observable harnesses destroy it (below), so blocks must be
  self-describing, not position-dependent.
- Gemini 3 uniquely links the structured and media channels: multimodal
  function-response parts get a `displayName` and the structured JSON
  references them via `{"$ref": "<displayName>"}`
  ([function-calling docs](https://ai.google.dev/gemini-api/docs/function-calling))
  — prior art for keying media blocks from structured content.

### 2.7 Cross-provider SDK taxonomies — LangChain and Vercel

Both teams faced the brief's vocabulary question and chose opposite
architectures for where the neutral form lives; their scars are the
finding.

- **Store the typed form; derive the wire — never the reverse.**
  LangChain stores the raw provider wire format and lazily derives
  typed blocks through five provenance-guessing translator passes
  (langchain:libs/core/langchain_core/messages/base.py:250-259), plus a
  `str | list` dual representation, an `output_version` env flag, and
  `source_type` field-sniffing — the optional-dual-channels-rot
  doctrine realized over four years. Vercel stores typed parts and
  projects one-way per provider; it stays coherent.
- **Vercel's endpoint after nine deprecations is ONE media block**:
  `type: "file"` with required `mediaType` as the modality
  discriminator and a tagged source union
  `{data | url | reference | text}` as an orthogonal axis
  (ai:packages/provider-utils/src/types/content-part.ts:62-102;
  deprecation graveyard at content-part.ts:359-533). Encoding source or
  modality into block-type names multiplied types that must be
  validated forever. LangChain's per-modality blocks duplicated
  factories and drifted (`create_image_block` misses the
  base64-requires-mime check its siblings have,
  langchain:libs/core/langchain_core/messages/content.py:1037 vs
  1099-1101).
- **Degradation is decided entirely at the provider seam**, three ways
  for the same neutral content: Anthropic maps image/pdf natively and
  drops other media with a warning
  (ai:packages/anthropic/src/convert-to-anthropic-prompt.ts:522-535);
  OpenAI Chat Completions `JSON.stringify`s the whole array — base64
  becomes token noise, the brief's exact failure mode, shipped in
  production
  (ai:packages/openai/src/chat/convert-to-openai-chat-messages.ts:
  327-331); Google's legacy path hoists media out and fabricates a text
  placeholder ("Tool executed successfully and returned this image…",
  ai:packages/google/src/convert-to-google-messages.ts:183-187).
- LangChain's `ToolMessage.content`/`artifact` split (model-visible vs
  never-sent full output, langchain:libs/core/langchain_core/messages/
  tool.py:73-80) is prior art for keeping heavy payloads out of the
  model channel by construction. Its `.text` projection silently
  ignores media — a media-only message renders as empty string
  (base.py:279-292) — confirming one deterministic text projection is
  expected and that placeholder beats silence.
- Vercel's `Tool.toModelOutput` hook + defaults (string → text block,
  else json; ai:packages/ai/src/prompt/create-tool-model-output.ts:
  16-30) is the exact "the verb owns projecting raw output into typed
  blocks" shape, performed for a foreign runtime by `mcpToModelOutput`
  (ai:packages/mcp/src/tool/mcp-client.ts:147-177).

### 2.8 A2A — the other protocol's answer

A2A v1.0 (Linux Foundation, late 2025) is an independent, multi-vendor
answer to typed multimodal content between LLM-backed processes — and
it disagrees with MCP on the key vocabulary question. Its smallest unit
is a single unified `Part` with a proto oneof carrier — `text | raw
(bytes) | url | data` — plus orthogonal `media_type`, `filename`, and
free metadata on every part (A2A:specification/a2a.proto:221-242).
Media kind is never a type, only a mime string; there is no ImagePart.
The v1.0 revision *scrapped* the v0.3 MCP-style discriminated union
(`kind: text/file/data` with nested `FileWithBytes|FileWithUri`) for
member-presence discrimination and mime-on-every-part
(A2A:docs/specification.md:3434-3527). Inline-vs-reference is a carrier
choice inside one concept (`raw | url` as sibling oneof members), and
the worked example takes raw bytes inbound but returns produced media
as a token-bearing storage URL (docs/specification.md:1692-1750).

Other bearings: A2A separates dialogue (Message.parts) from outputs
(Artifact: id, name, description, ordered parts) from verdict
(TaskStatus) — three channels, one Part type (a2a.proto:163-184,
254-293); the only content algebra is key-by-container-id +
concatenate-parts-in-arrival-order (`TaskArtifactUpdateEvent` with
append/last_chunk, a2a.proto:307-322); parts are never keyed, deduped,
or merged. Mime is open-world declaration + closed-world acceptance:
per-call `accepted_output_modes` and a typed
`ContentTypeNotSupportedError` refusal (a2a.proto:143-146;
docs/specification.md:559). And A2A has **no text projection at all**
— an entire 1.0 inter-agent protocol operates purely on typed parts,
which both confirms the stance (nobody building agent pipes in 2025
chose stdout) and marks the stdout rule as genuinely vfs-local novelty
(A2A has no human terminal in its loop).

### 2.9 Harness consumers — gemini-cli and opencode

The consumers a vfs MCP projection must satisfy, read at line level
([harness-consumers study](studies/2026-07-25-multimodal/harness-consumers.md);
gemini-cli provenance per the preamble — `git show HEAD:` reads plus
fetched current-main files):

- gemini-cli's Aug-2025 tree **silently dropped** all MCP image/audio
  blocks (only `.text` fields extracted —
  `git show HEAD:packages/core/src/core/coreToolScheduler.ts:141-200`)
  while JSON-dumping raw base64 into the terminal
  (`git show HEAD:packages/core/src/tools/mcp-tool.ts:150-180`);
  current main fixed both with a per-block transform
  (`transformMcpContentToParts`, `mcp-tool-main.ts:512-541`) and
  deterministic display placeholders (`[Image: image/png]`,
  `[Link to <title>: <uri>]` — `getStringifiedResultForDisplay`,
  `mcp-tool-main.ts:551-584`; `resource_link` flattened to prose at
  `mcp-tool-main.ts:500-504`) — the exact failure/fix cycle the brief
  predicts.
- Both model seams destroy interleaving: gemini joins all text with
  `\n` into one `functionResponse.output` and appends media (nested in
  `functionResponse.parts` only for `gemini-3-*` models); opencode
  emits one joined text block then all media
  (opencode:packages/opencode/src/session/message-v2.ts:442-473).
  opencode's `content: result.content // preserve ordering` field is
  vestigial — persistence stores only `output` + `attachments`, so
  ordering dies at the first save.
- opencode's MCP wrapper has **no branch for `audio` or
  `resource_link`** — silently dropped, no placeholder
  (opencode:packages/opencode/src/session/prompt.ts:773-807). Neither
  harness ever fetches a resource link; gemini flattens it to prose.
- Gemini's protocol cannot carry audio/video in function responses, so
  gemini-cli strips them with "[SYSTEM: Binary content stripped…]" —
  except `read_file`, which smuggles them under a
  `__binary_injection__` key (`genContentUtils.ts:18, 146`) later
  expanded into a fabricated three-turn exchange (synthetic model ack,
  binary re-sent as user message —
  `geminiChat.extractBinaryInjections`, `geminiChat.ts:659-678`,
  `geminiChat.ts:456-490`). This is the length a harness goes to when
  the tool-result channel is text-shaped and the media is real.
- Both budget **text only** (overflow-to-file + pointer — the same
  doctrine as the envelope's error budgets); media is never truncated
  or token-counted, and opencode's compaction deletes attachments
  first. Placeholders must carry path+mime+size so evicted media stays
  re-fetchable.
- Both treat SVG as text; both decide visibility by mime *prefix*;
  neither has any path from executed-program stdout bytes to a media
  block — the run verb's projection duty is vfs-novel territory.

### 2.10 Terminal media — the human boundary

Three incompatible terminal graphics protocols (kitty APC, iTerm2 OSC
1337, sixel) all reduce to the same tuple — bytes + format/mime + size
+ optional name — which is exactly what an MCP image block needs; one
media shape feeds both boundaries mechanically
(https://sw.kovidgoyal.net/kitty/graphics-protocol/,
https://iterm2.com/documentation-images.html,
https://www.arewesixelyet.com/). Every protocol enforces declared chunk
budgets (kitty 4096-byte APC chunks; iTerm2 grew a multipart mode for
tmux's cap) — the terminal world independently re-derived the
no-unbounded-statement doctrine. Support is fragmented enough that the
no-graphics rung is the *median* case, and every mature tool (timg,
chafa, `kitten icat`) ships a fidelity ladder ending in text.

The agent-CLI precedent is Claude Code's own tracker: inline terminal
images have not shipped as of 2026-07
(https://github.com/anthropics/claude-code/issues/2266, #54546 and
dupes); the blocker is architectural — a repaint-loop TUI sanitizes
escapes, cannot reserve image heights, and regenerates scrollback from
a text-only transcript, losing images permanently. What Claude Code
ships today is the brief's asymmetry lived in reverse: `Read` on a PNG
feeds the model a typed image block while the transcript shows a text
placeholder. The placeholder rung is the load-bearing part; inline
pixels are progressive enhancement — cheap for a print-and-scroll CLI,
rewrite-grade for a repaint TUI. No tool stores protocol-encoded bytes;
all store source + mime and encode per consumer at the boundary.

## 3. The stance, evaluated: "break from Unix"

The owner's stance — typed, media-separated content blocks in the pipe,
not stdout; traditional-CLI ergonomics preserved; a multimodal CLI —
gets independent confirmation from every direction studied:

- **Shells**: PowerShell (20 years), nushell, murex, elvish, TermKit
  all broke from raw-text pipes; none reverted the typing; the working
  parts of each are exactly the parts that broke from Unix, and the
  documented warts are exactly the retained-Unix seams (PowerShell's
  18-year binary corruption, nushell's `run_external` wire wart and
  nu-mcp's lossy text, elvish's byte-band deadlocks).
- **Representation**: Jupyter shipped the stance in 2011 — stdout stays
  a text stream, rich values cross as typed mime-tagged structure, and
  the terminal still feels like a REPL because of the mandatory
  `text/plain` floor.
- **Protocols**: MCP's model-facing channel is already an ordered array
  of typed blocks; A2A — a whole inter-agent protocol — has no untyped
  byte stream anywhere; both SDK ecosystems (LangChain, Vercel) and all
  three frontier providers converged on ordered typed-part arrays.
  Raw-stdout-only tool output is the legacy shape industry-wide.
- **Even the terminals agree from the opposite shore**: the maximally
  Unix world of terminal emulators concluded raw text cannot carry
  media and invented typed, framed, mime-tagged envelopes — content
  blocks spelled in escape sequences — and the pain of that smuggling
  (tmux eating sequences, chunk caps, detection round-trips) is the
  cost of not having a typed channel.

So the memo takes the position: **the stance is correct, and vfs has
already executed most of it** — pipes carry `Result` envelopes, text
renders once at the final boundary, the renderer owns the text form
(`envelope.py:28-30`; `src/vfs/results/render.py:10-13`). What remains
is extending the break all the way to the wire, and the evidence
amends the stance in five specific ways:

1. **Blocks are a boundary product, never pipeline or envelope
   currency.** PowerShell's format-object leakage is the counterexample
   that settles it; the envelope's algebra (§5) independently forbids a
   stored ordered block list.
2. **One ordered sequence of typed items, never parallel channels.**
   elvish's reproduced cross-band nondeterminism and deadlocks kill the
   text-channel-plus-media-band shape; TermKit and MCP get interleaving
   for free from a single sequence.
3. **The break must extend to the wire.** nushell broke from Unix in
   the middle and kept it at the edges; its own MCP server mangles
   binary through `from_utf8_lossy`. The boundary contract is where
   multimodality is won or lost.
4. **The text projection is not nostalgia; it is the guaranteed-delivery
   channel.** The typed channel is per-provider lossy — audio lands
   only on Gemini 3+, mimes intersect at jpeg/png/webp, Anthropic
   400-rejects unknown types, and observed harnesses fuse text and drop
   exotic blocks silently. Every media block needs a deterministic text
   form it degrades to; no counterexample exists anywhere in the
   corpus.
5. **Zero ceremony is a mechanism, not a vibe.** PowerShell
   host-injects `Out-Default`; nushell's renderer is an ordinary
   implicit command; both SDKs auto-lift bare strings into text blocks
   while nothing ever auto-lowers media into strings; Jupyter's floor
   renders text with no user action. vfs already has the analogous
   chokepoint (`render_result`); the multimodal CLI must keep the text
   case exactly as cheap as today.

One honest caveat: TermKit — the closest system ever built to the
hypothesized multimodal CLI — died. But it died of demanding the world
convert before being useful, not of its data model, and the stance's
"still feels like a CLI" clause is precisely the lesson its death
teaches.

## 4. Synthesis: the eight questions settled

### Q1 — Where blocks live

**Recommended: media as masked, path-keyed evidence on `Observation`
rows (the brief's candidate B) as the carrier; the ordered block array
minted only at the boundary by a greenfield MCP adapter (candidate A
resurrected as projection output, never stored); reference +
fetch-on-request as the budget posture (candidate C's form, expressed
through the existing `read` verb rather than a new mechanism).**

The evidence: a stored `content: list[ContentBlock]` on `Result` fails
the algebra — an ordered unkeyed list has no idempotence (`r | r`
duplicates blocks; the diamond `(a | b) & b` double-counts), value-dedup
of narrative blocks silently rewrites meaning, and the nine
field-by-field construction sites make any unthreaded field a standing
silent-loss bug (§5). PowerShell's leakage independently warns against
blocks as ordinary values. Projection-time-only fetch fails on the
other side: a re-fetch at the boundary can ship bytes of version N+1
while the row attests version N — reopening the evidence/emission
divergence class the envelope exists to kill — and violates render
purity (`render.py:8-9`) while quietly making media a final-hop-only
privilege (inter-mount hops carry structured payload only,
`envelope.py:28-30`).

Row-borne media satisfies nearly everything for free: path-keyed dedup,
left-wins-by-mask merge, masks-union, version agree-or-null, rebase
with overflow, per-item quarantine, and the projection machinery —
including elide-by-default (unprojected means never fetched from
storage, `src/vfs/results/projection.py:45-57`). Its one honest
weakness is interleaving, addressed under Q4. External support:
nushell proves type-on-the-value survives where sidecar metadata rots;
A2A's Artifact (id, name, description, ordered parts) is a working
precedent for media as keyed, named evidence distinct from status and
dialogue; Vercel proves store-typed/derive-wire beats the reverse;
terminal tools store source bytes + mime and encode per consumer at
the boundary; LangChain's content/artifact split shows heavy payloads
kept out of the model channel by construction.

### Q2 — The block vocabulary

**Recommended: no stored block vocabulary at all inside the envelope —
the internal representation is row fields (bytes/reference + the
existing `mime_type`) — and adopt MCP's five-block taxonomy verbatim at
the wire projection, so projection is mechanical and identity-shaped.
vfs extensions (the path key on a bare `ImageContent`) ride in
vfs-prefixed `_meta` keys.**

The two mature protocols genuinely disagree here — MCP makes `image` a
block type; A2A makes it a mime string on a generic carrier — and this
is an ADR-level choice worth naming. The memo leans A2A/Vercel-shaped
*internally* (modality derived from mime; inline-vs-reference as a
source choice, not a type) because Vercel's nine deprecations show
per-modality-per-source type names multiply and drift, and because vfs
rows already are the generic carrier with `mime_type` attached. But at
the wire, MCP's taxonomy is the target and adopting it exactly makes
the projection a mime→species dispatch (fastmcp's `text/*` fork,
fastmcp:fastmcp_slim/fastmcp/utilities/types.py:436-452, is the
pattern). Unknown block types arriving from newer peers get the
existing unknown-kind doctrine: preserved raw, degraded to the text
placeholder, never dropped, never guessed (the `VFSErrorKind` doctrine,
`src/vfs/results/kinds.py:26-34`; degrade-by-longest-known-prefix in
`kind_family`, `kinds.py:248`). Every block must be strict JSON
(one serializer, `envelope.py:640-667`).

### Q3 — Algebra semantics for media

**Recommended: the only key a media payload has is the row's path; the
algebra needs no new laws because media rides existing row-merge
semantics (left-wins-by-mask, masks-union, version agree-or-null). And
contra the brief's instinct that "blocks are closer to message":
anything carrying a vfs path is on the path side of the rebase line and
MUST rebase**, or a mounted hop ships dangling links
(`envelope.py:97-99` — rebase touches path/source/data, never message;
the 9P werrstr scar in the
[result-envelope memo](2026-07-08-result-envelope.md)). The strongest
counter-evidence is named and overruled: the
[harness-consumers study](studies/2026-07-25-multimodal/harness-consumers.md)'s
own lesson reads gemini-cli and opencode as evidence for blocks as
unkeyed, message-like sequences — op-ordered concatenation, untouched
by rebase — and indeed no observed consumer would rebase anything. But
those consumers sit at a final boundary and never re-forward results
across mounts, while vfs envelopes hop mounts as a matter of course; a
non-rebased path-bearing block ships dangling links on the first
mounted hop, so ground truth overrules the consumer reading.

No studied system has a content merge algebra — PowerShell's packets,
A2A's parts, both SDKs' block lists are unkeyed ordered sequences whose
only operation is order-preserving concatenation; Jupyter's
`display_id` update is replace-all, not merge. That absence is itself
the finding: content is document-shaped where it is a document, and the
lawful way to get set-shaped semantics is to key it by path — which
rows already do. Media fields are version-coupled evidence like
`content` already is; the `version` agree-or-null rule
(`envelope.py:422-426`) stamps cross-snapshot composites honestly.

### Q4 — Ordering and interleaving

**Recommended: order is a property of the value, expressed as
`Match`-style anchored regions inside a row for in-document placement,
and arranged into the ordered block array by the boundary adapter — one
row = one media object for the common case (`read /charts/q3.png`);
anchored sub-row regions for a document whose figures interleave with
its text.**

Jupyter's two axes must not be conflated: alternatives of one value are
a selection problem; distinct outputs are a sequence problem. The
sequence must live in the data structure (Jupyter's
transport-arrival-order hole; Claude Code losing images on scrollback
re-render from a text-only transcript). Renderers already re-sort rows
by path (`render.py:296`), so row-granularity emission order is not
meaning today — ordering is a boundary arrangement concern, and `Match`
(`entry.py:335-353`) is the existing shape for "a thing positioned
within a document." The adapter unrolls a row deterministically:
text-before-anchor, media block, text-after. elvish's reproduced
nondeterminism forbids the parallel-channel alternative; MCP's contract
silence plus both harnesses flattening order means each media block's
caption must be self-describing (name the figure, its path, its mime)
so meaning survives a consumer that reorders — emit ordered blocks
anyway, because flattening is lossy but safe while un-flattening is
impossible.

### Q5 — Budgets

**Recommended: elide-with-placeholder by default, media-on-request,
using the exact `max_errors` template: budgets cap the boundary, never
the algebra; nothing is dropped in-process; the placeholder carries
machine-readable path/mime/size/count; the verdict is invariant under
elision (`envelope.py:651-667, 732-756`). On the wire this is
`resource_link` + `size` (+ `annotations.priority` as a hints-only
overlay); the fetch is `read` with the media field projected — an
existing verb, not a new mechanism.**

The numbers make this the only scalable posture: 1.3k–4.8k tokens per
image on Claude, a 25k-token cap on a whole MCP result including image
bytes, and a supported 10k-row batch contract that makes per-row inline
base64 an unbounded payload. Production precedent: nu-mcp's
limit + `$history.N` handle (with env-tunable budgets — they retuned a
timeout because a model gave up on the tool); both harnesses'
overflow-to-file + pointer; A2A's `include_artifacts=false` default and
url-part-as-placeholder; TermKit's 4096-byte hex clip with "N bytes
total, M shown". Jupyter is the proof by inversion: embed-by-default
without addresses bloated an ecosystem for a decade. Two obligations
travel with the posture: the fetch path must actually exist (the
QtConsole dead-link lesson — and serving MCP `resources/read` requires
the `resources` capability), and the seam should downscale images to
the provider tier cap before base64-encoding, since anything above it
is pure waste.

### Q6 — The stdout rule

**Recommended: one canonical, device-independent placeholder text form
for any media — path + mime + byte size + optional stored description —
enforced at the render chokepoint like the existing one-line-ness and
cell-escaping defenses (`render.py:91-107, 253-255`), not left to
producer discipline. Base64 never reaches a text stream. Text-native
media (SVG is XML) passes through as text.**

This is the best-evidenced rule in the corpus. For it: Jupyter's
mandatory `text/plain` floor (deployed since 2011); PowerShell's
host-injected single renderer reused at every text seam — with the
amendment that the canonical form must be width- and ANSI-independent
(their device-parameterized rendering caused data loss); both harnesses
independently invented `[Image: mime]` placeholders after shipping the
base64-dump failure mode; every provider's docs confirm base64-in-text
is token noise; LangChain's silently-empty `.text` shows placeholder
beats silence; terminal tools' fidelity ladders all bottom out in a
deterministic text rung. Both harnesses and gemini's file reader treat
SVG as text, matching the brief. nushell's Unknown-passes-raw
compromise is explicitly rejected at an LLM boundary: classify
everything; non-text gets the placeholder. Per the hermetic memo's
wire-format lesson, the placeholder grammar is a pre-ship canonical
decision, not an emergent default.

### Q7 — Mime reality

**Recommended: carry the raw mime verbatim inside the envelope (the
`mime_type` field already exists on Entry and Observation,
`entry.py:88, 390`), and make acceptance a closed, per-boundary
decision at projection time: the MCP adapter emits a typed media block
only for the boundary's known-good set (image intersection:
jpeg/png/webp; transcode or downscale where cheap) and degrades
everything else to the placeholder with the true mime named — never
silent drop, never hard error.**

The prior art genuinely splits here and the memo picks a side. Jupyter
says classify nothing at the seam, carry mime open-world, let consumers
ignore what they don't understand — correct for a many-unknown-frontend
world. But the model-API physics overrules it for this seam: Anthropic
enum-validates and 400-rejects, so open passthrough can poison an
entire request rather than degrade one block. The synthesis is A2A's
shape adapted: open-world mime *inside* the envelope, closed-world
acceptance *at each projection*, with an explicit typed downgrade
instead of A2A's refusal error. Classification dispatches on a small
normalized core / mime prefix (nushell's curated-overrides-then-guess
table, both harnesses' `startsWith('image/')`, TermKit's specificity
ladder), while the block always keeps the true mime.

### Q8 — Executed-code output

**Recommended: program-produced media becomes vfs entries via the wasm
write-back-at-`fd_close` mechanism
([hermetic memo](2026-07-24-hermetic-runtime-and-wasm-cli.md) §4.3),
and the `run` result references them by path — the executed-code
question reduces to the same reference-vs-inline choice as `read`.
Ephemeral stdout bytes are captured at op time into the
`{stdout, stderr, exit_code}` record; the `run` verb owns the
projection duty of classifying that byte output, and stdout-scraping is
the fallback, never the model.**

Every line of evidence converges: murex's abandoned fd-3 experiment and
TermKit's wrapper strategy say external programs will never self-declare
block types; PowerShell's pre-BytePipe era says scraping stdout as text
loses media at birth; Jupyter's template is hooking the runtime's
display path while stdout stays a text stream; Vercel's `toModelOutput`
puts exactly this duty on the tool/framework; nu-mcp shows what happens
when the boundary skips it. Neither production harness has any path
from program stdout bytes to a media block — this is genuinely novel
vfs territory, and the write-back mechanism makes it cheap: the sandbox
writes `/plots/fig1.png`, the entry lands in vfs with a path and a
mime, and the `run` result cites it like any other evidence.

## 5. Adversarial pass: the recommendation vs the envelope invariants

The [ground-truth study](studies/2026-07-25-multimodal/envelope.md)'s
invariant set is binding. Walking the
recommended design (row-borne media + Match-style anchors + boundary
adapter + placeholder rule) against it, in the study's labels:

- **A1 (verdict derived; no evidence/emission divergence).** Satisfied
  by construction: bytes ship inside the same envelope as the version
  that attests them. This is precisely why projection-time fetch was
  rejected. The ADR must still pin the boundary adapter to *never*
  perform reads — placeholders come from the mask, not from a re-fetch.
- **A2 (`__bool__` untouched).** A media field on rows does not perturb
  truthiness. Trivially satisfied; state it in the ADR anyway.
- **B1/B2 (rows frozen, keyed by path; Observation NOT open).** The new
  field inherits the mask discipline, but `Observation` has default
  `extra` (`entry.py:382`) — an older client's `from_payload` silently
  strips the media field. That degrades to today's behavior (media
  invisible), which is acceptable, but it is a conscious compat call
  the ADR must record — and must decide whether `Observation` becomes
  `extra='allow'` alongside, knowing the ground-truth finding that
  open-model fields survive a wire hop but are dropped by the first
  algebra operation anyway (open model is pass-through, not
  merge-safe).
- **B3 (no binary channel exists).** The hard prerequisite. The ADR
  cannot be written for the envelope alone; it needs the storage/model
  bytes story first: where bytes live (column, table, or external
  store), how `CONTENT_KINDS` gates them, and how null-byte-rejecting
  `content: str` and a bytes field coexist without becoming an optional
  parallel pair (see F2 below).
- **B4 (Match precedent).** Anchored media regions must be specified:
  the anchor type (start/end bounds + payload-or-reference), where the
  list lives on the row, and its merge behavior — filled lists are
  copied under C2's left-wins rule, which is coherent but must be
  stated (two observations of the same path do not interleave their
  anchor lists; left's list wins where populated).
- **C1–C3 (algebra laws).** Satisfied for free by row carriage — this
  is the design's core claim. No new laws, no new dedup identity, no
  diamond double-count: the law tests need extension only to assert
  media fields ride the existing properties.
- **C7 (nine construction sites).** The lethal hazard is avoided
  *because* nothing is added at the `Result` level. The ADR should
  state this as a rule, not a coincidence: the content channel adds
  fields to `Observation` only; any future Result-level field proposal
  re-triggers the nine-site threading hazard and needs its own
  justification.
- **D1–D3 (rebase).** Row-borne media rebases for free, overflow
  discipline included (`envelope.py:581-620`). The one new obligation:
  the boundary adapter emits path-bearing wire shapes (`resource_link`
  uris, `_meta` path keys). Since the adapter runs only at the final
  boundary, after any rebase, links are minted post-rebase and cannot
  dangle — but the ADR must pin "the adapter is final-boundary-only;
  projected payloads are never stored or re-forwarded," or the D2
  guarantee silently erodes.
- **E1 (one serializer, strict JSON).** Media bytes cross the
  structured wire as base64 strings inside the row payload. Fine — but
  combined with H6 this makes the default projection posture
  (elide-by-default) load-bearing, not optional.
- **E2 (per-item leniency).** Rows already get per-item quarantine, so
  malformed media rides existing machinery — one bad row cannot poison
  the envelope, and no new list needs adding to `_validated_items`
  (`envelope.py:758-779`). If the ADR ever adds a non-row block list,
  it must be added there or one malformed block quarantines the whole
  channel.
- **E3 (512-byte quarantine clip).** A malformed multi-megabyte base64
  payload is clipped to junk on quarantine — media loss is recorded,
  never preserved. Acceptable; the ADR should name it (loss-on-record,
  same as today's rows).
- **E4 (budgets cap the boundary, never the algebra).** The media
  elision regime must copy the `max_errors` shape exactly: applied in
  `to_payload`/the adapter, placeholder with machine-readable
  count/size/address, verdict invariant, nothing dropped in-process.
- **F2 (optional dual channels rot).** The sharpest specification
  burden. A row must never carry media bytes *and* a text `content`
  duplicating them, and the media field must never be
  optional-and-parallel to `content`. The ADR must make the split
  structural: which of `content` / media-bytes a row carries is
  determined by kind/mime (`CONTENT_KINDS` is the existing gate,
  `entry.py:42-43`), defaulted by construction, mutually exclusive —
  not two fields producers may or may not fill.
- **F3 (unknown degrades, never drops).** Unknown block types from
  newer peers: preserved raw, degraded to the placeholder. Mirrors the
  kind/severity doctrine; must be stated for the adapter's inbound
  direction.
- **G1–G3 (render once, pure, chokepoint-defended).** The adapter is a
  *sibling* of the pure renderer, not part of it — it performs no I/O
  (A1 above) and is the only place ordered block arrays are minted. The
  placeholder rule is enforced at the chokepoint in the style of the
  existing structural defenses: the text surface rejects raw
  base64-shaped media content the way it already collapses forged
  sibling lines.
- **G4/G5 (projection double duty; render-time ordering).** A media
  field slots into projection vocabulary for free: projectable,
  SQL-narrowing, elide-by-default — unprojected means the bytes are
  never even fetched from storage, which is the budget posture at the
  cheapest possible layer. Ordering stays an arrangement concern.
- **G6 (cross-op merges must render).** The ADR must define what a
  merged, cross-op result renders as on both surfaces when rows carry
  media — the generic fallback needs a placeholder-bearing answer.
- **H1 (values never lazy).** The row holds materialized bytes or a
  reference; no streams inside the value. Consistent with whole-file
  staging in the wasm design.
- **H5/H6 (executed code; 10k batches).** Write-back makes program
  media into entries (Q8); per-row inline base64 at 10k rows is an
  unbounded payload, so the reference form plus E4 budgets are
  mandatory, and the boundary should chunk any inline media by declared
  budget — the same `membership_budget`/`chunked()` doctrine the
  database backend and, independently, every terminal graphics protocol
  arrived at.

Net: the recommended design survives the invariant set with zero new
algebra laws, at the cost of a storage-side bytes prerequisite (B3), a
compat decision (B2), a structural exclusivity rule (F2), an anchor
specification (B4), and a handful of pins the ADR must state explicitly
(adapter purity and final-boundary-only placement, the placeholder
grammar, the E4-shaped elision regime, G6's merged rendering).

## 6. Open questions — what the ADR must decide

1. **The storage bytes story (prerequisite).** Where binary content
   lives (row column vs separate table vs external store), how
   `CONTENT_KINDS` gates it, size ceilings, and how metrics/hashing
   extend to bytes. The envelope design cannot land before this.
2. **The Observation media field shape.** Bytes-inline vs
   reference-only vs both (Vercel's tagged source union is the
   precedent for both-as-one-field); whether `size_bytes` and
   width/height are carried (terminal protocols and TUI row-reservation
   want dimensions; MCP `size` wants bytes); base64-at-rest vs
   encode-at-serialization.
3. **The exclusivity rule (F2).** Exact construction-time semantics of
   content-vs-media by kind/mime, and what `read` returns for a media
   path when the media field is unprojected.
4. **The anchor type.** Shape of Match-style media anchors, their home
   on the row, and their arrangement contract in the adapter.
5. **Observation compat.** Whether `Observation` goes `extra='allow'`
   when the media field lands, and how old-client stripping is
   documented.
6. **The placeholder grammar.** The canonical text form (path, mime,
   size, description — field order, escaping, one-line rule), decided
   pre-ship as a wire format, plus its enforcement point in
   `render.py`.
7. **The MCP adapter.** Placement (sibling to render), the
   row→block unrolling rules, `_meta` key names for the path,
   whether/when the vfs server implements the `resources` capability so
   `resource_link` placeholders are fetchable, and inbound handling of
   unknown block types.
8. **Per-boundary mime accept-lists and downscaling.** The known-good
   set per target (Claude/OpenAI/Gemini intersections), where
   downscale-to-tier-cap happens, and whether transcoding
   (e.g. HEIC→JPEG) is in scope or placeholder-only.
9. **Budget knobs.** Default media budget at `to_payload`/the adapter,
   its env/parameter tunability (nu-mcp's lesson), and interaction with
   `max_errors`-style rollups in one payload.
10. **The `run` capture rule.** The op-time `{stdout, stderr,
    exit_code}` record's classification duty for stdout bytes
    (sniff-as-fallback), and how write-back artifacts are cited in the
    run result's rows.
11. **The CLI rendering architecture.** Print-and-scroll (inline
    terminal graphics become a contained, negotiated enhancement — the
    timg/icat shape) vs repaint TUI (inline graphics become
    rewrite-grade — the unshipped Claude Code wall). This choice is
    upstream of any inline-media work on the human side and should be
    made deliberately, early.
