# Study: the A2A (Agent2Agent) protocol Part taxonomy

- **Subject repo**: `~/Git/Repos/A2A` (Apache-2.0; Linux Foundation project, proto package
  `lf.a2a.v1`). Shallow checkout at v1.0-era head (`0ef1b02`, single commit).
- **Canonical source of truth**: `specification/a2a.proto` — the JSON wire shape is
  *derived* from the proto via the ProtoJSON canonical encoding
  (`adrs/adr-001-protojson-serialization.md`; JSON Schema is a non-normative build
  artifact, `specification/json/README.md`).
- **Why it matters for the brief**: A2A is an independent, very recent (v1.0, late 2025)
  answer to exactly the question the brief asks — how typed multimodal content moves
  between LLM-backed processes — designed by a different lineage than MCP (Google →
  Linux Foundation vs Anthropic), and it *changed its answer* between 0.3 and 1.0,
  which makes the delta itself evidence.

---

## 1. What it is

A2A standardizes peer collaboration between opaque agents: discovery (AgentCard),
task lifecycle (Task/TaskStatus/TaskState), messaging (Message), outputs (Artifact),
and streaming (StreamResponse events), over three bindings (JSON-RPC, gRPC,
HTTP+JSON) generated from one proto. Its self-declared design principle:

> "**Modality Agnostic:** Support exchange of diverse content types including text,
> audio/video (via file references), structured data/forms, and potentially embedded
> UI components (e.g., iframes referenced in parts)."
> — `docs/specification.md:38`

Note the parenthetical: even in the principles statement, audio/video and UI are
handled "via file references", not via dedicated block types. That is the single
most important stance of the whole design.

A2A positions itself as complementary to MCP: MCP is agent→tool ("using
capabilities"), A2A is agent↔agent ("partnering on tasks") — `docs/specification.md:3598-3610`,
expanded in `docs/topics/a2a-and-mcp.md` ("A2A focuses on agents partnering on
tasks, whereas MCP focuses on agents using capabilities"). vfs's Result crosses an
MCP-shaped seam, but its verbs compose like agents delegating work — A2A's content
model is prior art for the *inter-process* leg of the brief's question.

## 2. The data model

### 2.1 Part — the unit of content (v1.0, current)

`specification/a2a.proto:221-242`:

```proto
message Part {
  oneof content {
    string text = 1;                 // the string content of a text part
    bytes  raw  = 2;                 // raw file bytes; base64 string in JSON
    string url  = 3;                 // a url pointing to the file's content
    google.protobuf.Value data = 4;  // arbitrary structured JSON value
  }
  google.protobuf.Struct metadata = 5;  // optional per-part metadata
  string filename = 6;                  // optional, any part type
  string media_type = 7;                // MIME type, "available for all part types"
}
```

Four *content carriers*, three *conceptual kinds*:

- **TextPart** → `{ "text": "...", "mediaType": "text/plain" }`
- **FilePart** → `{ "raw": <b64>, ... }` **or** `{ "url": "https://...", ... }`
  plus `filename` + `mediaType` — the inline-vs-reference choice is a `oneof`
  *inside one kind*, not two kinds.
- **DataPart** → `{ "data": {...}, "mediaType": "application/json" }`

Media specificity (image vs audio vs video vs PDF) is **not** in the type system at
all — it lives entirely in the `media_type` string. There is no ImagePart. A PNG is
a file part whose `media_type` is `image/png` (`a2a.proto:239-241`; worked example
`docs/specification.md:1692-1750`).

### 2.2 The v0.3 → v1.0 redesign — a live verdict on discriminator style

v0.3.x Parts were a discriminated union with an inline `kind` tag and a nested
file object (`docs/specification.md:3439-3460`):

```json
{ "kind": "text", "text": "Hello, world!" }
{ "kind": "file", "file": { "name": "diagram.png", "mimeType": "image/png",
                            "fileWithBytes": "iVBORw0KGgo..." } }
{ "kind": "data", "data": {...} }
```

`file` itself was a union: `fileWithBytes` (base64) **or** `fileWithUri`
(`docs/whats-new-v1.md:289-296`, `docs/specification.md:3448-3460`) — exactly the
inline-vs-reference pair the brief's `resource_link` question mirrors, and A2A had
it from the start.

v1.0 **removed the `kind` discriminator entirely and flattened the union**
(`docs/specification.md:3434-3527`, `docs/whats-new-v1.md:275-359`): member
presence is the discriminator (`{"text": ...}` vs `{"raw": ...}` vs `{"url": ...}`
vs `{"data": ...}`), matching proto `oneof` semantics. Their stated rationale
(`docs/specification.md:3519-3527`):

- reduces redundancy (no field name + `kind` value both saying "text");
- aligns JSON-RPC and gRPC representations;
- simplifies codegen; avoids modeling inheritance in schema languages;
- improves type safety in strongly-typed languages.

Two quieter v1.0 changes matter more than the discriminator (`docs/whats-new-v1.md:338-348`):
`mediaType` was **promoted from file-only to every part type** (a text part can be
`text/markdown`; a data part can carry a vendor JSON mime), and `filename`
likewise. The unified Part converged on: *one envelope, orthogonal fields
(carrier, mime, name, metadata)* rather than *N block classes each with its own
field set* — the opposite direction from MCP's `type: "image" | "audio" | ...`
taxonomy.

Cost they accepted: ProtoJSON cannot round-trip unknown fields
(`adrs/adr-001-protojson-serialization.md`, "Loss of roundtrip capability"), and
member-presence discrimination is harder to validate in plain JSON Schema (their
schema pipeline needed a custom proto→JSON-Schema build, `specification/json/README.md`).

### 2.3 Per-part metadata

`Part.metadata` is a free `Struct` (`a2a.proto:235-236`). Two sanctioned uses in
the docs:

- **Provenance/reference**: a client answering a disambiguation question puts
  `artifactId`/`taskId` references *in Part metadata* (`docs/topics/life-of-a-task.md:112-119`).
- **Schema/content negotiation**: a request part carries
  `metadata: { "mediaType": "application/json", "schema": {...} }` to ask the
  agent for output in a specific JSON shape (`docs/specification.md:1769-1790`).

So metadata is where *keying, provenance, and expectations* live — the typed
fields stay minimal.

## 3. Message vs Artifact — two containers, one Part

- **Message** (`a2a.proto:254-277`): one conversational turn; `role`
  (ROLE_USER/ROLE_AGENT), `repeated Part parts` (REQUIRED), IDs
  (message/context/task), extensions, `reference_task_ids`. Messages are the
  *dialogue* channel — questions, clarifications, status prose.
- **Artifact** (`a2a.proto:279-293`): a *task output*; `artifact_id` (unique
  within task), human `name`, `description`, `repeated Part parts` ("must contain
  at least one part"), metadata, extensions. Artifacts are the *result* channel.
- **Task** (`a2a.proto:163-184`) holds both: `repeated Artifact artifacts` (the
  outputs) and `repeated Message history` (the conversation), plus TaskStatus
  whose optional `message` carries a status-attached Message (`a2a.proto:211-219`).

This is a deliberate **verdict/evidence-adjacent split**: status (state enum +
message) is separate from outputs (artifacts), and both are separate from dialogue
(history). Within either container, parts are an ordered `repeated` array — order
is positional and preserved by ProtoJSON; there is no per-part key, index, or id.
The only content addressing is at the **artifact** level (`artifact_id`), and the
identity story leans on it hard (§5).

## 4. Boundary rendering, negotiation, and the mime reality

A2A has **no rendering rule** — no "text projection" of a file part, no
placeholder form. Instead it prevents the problem contractually, by *media-type
negotiation before content flows*:

- AgentCard declares `default_input_modes` / `default_output_modes` **as media
  types** (`a2a.proto:386-390`), overridable per skill
  (`AgentSkill.input_modes/output_modes`, `a2a.proto:447-450`; example card
  advertising `image/png` outputs at `docs/specification.md:2168-2200`).
- Each send carries `SendMessageConfiguration.accepted_output_modes`: "A list of
  media types the client is prepared to accept for response parts. Agents SHOULD
  use this to tailor their output." (`a2a.proto:143-146`; example
  `docs/specification.md:2825`).
- Unsupported media is a **typed refusal**, not silent degradation:
  `ContentTypeNotSupportedError` (JSON-RPC `-32005`, gRPC `INVALID_ARGUMENT`,
  HTTP 400) — `docs/specification.md:559,1186`.
- Security guidance: "Agents SHOULD sanitize or validate file content types and
  reject unexpected media types" (`docs/specification.md:3182`).

So where the brief asks "what happens to media outside the model-visible mime
list — pass through or classify?", A2A's answer is a third option: **declare,
negotiate per-call, refuse with a typed error**. The mime string is open-world;
the *acceptance set* is closed per interaction.

For inline-vs-reference, A2A gives both carriers equal standing and lets size
economics decide: the worked file-exchange example uploads `raw` bytes inbound and
returns a **`url` part with a token-bearing storage link** outbound
(`docs/specification.md:1692-1750`) — inline for small inputs, reference for
produced outputs. Nothing in the protocol forces either; there is no size
threshold in the spec.

## 5. Ordering, streaming, and the closest thing to an algebra

Streaming (`SendStreamingMessage` → `stream StreamResponse`,
`a2a.proto:31-42,790-803`) delivers exactly one of: `Task`, `Message`,
`TaskStatusUpdateEvent`, `TaskArtifactUpdateEvent` per event. The stream contract
(`docs/specification.md:206-212`): either a single Message then close, or a Task
followed by status/artifact update events until terminal state. Ordering is
guaranteed only as "simple, linearly ordered sequences … Implementations SHOULD
avoid re-ordering events" (`docs/specification.md:2973`).

**Incremental content delivery is keyed merge-by-append**
(`a2a.proto:307-322`):

```proto
message TaskArtifactUpdateEvent {
  string task_id = 1;  string context_id = 2;
  Artifact artifact = 3;
  bool append = 4;      // append parts to previously sent artifact with same ID
  bool last_chunk = 5;  // final chunk of the artifact
}
```

i.e. the merge rule for content is: **key = `artifact_id`; operation = concatenate
`parts` in arrival order; `append=false` replaces, `append=true` extends;
`last_chunk` closes** ("stream large files or data structures in chunks, with
fields like `append` and `lastChunk` to help reassemble",
`docs/topics/streaming-and-async.md:21`). Parts themselves are never keyed,
deduped, or merged — only their container is.

Beyond a task, A2A **refuses to define a content algebra at all**: tasks are
immutable once terminal; refinements are *new tasks* producing *new artifacts*;
version linkage between an artifact and its refinement "is not part of the A2A
protocol specification" — clients track it, aided by the convention that agents
reuse a consistent artifact `name` across versions while `artifact_id` changes
(`docs/topics/life-of-a-task.md:80-131,217-235`). Identity by stable
human-readable name + fresh id per version is their dedup story.

## 6. What A2A deliberately left out, and why

- **No media-specific part types** (no ImagePart/AudioPart/VideoPart). The
  modality-agnostic principle (`docs/specification.md:38`) routes all media
  through the file carrier + `media_type`. Consequence: adding a new modality is
  a *string*, not a schema change — but a consumer cannot know from the type
  system whether it can render a part; it must dispatch on mime.
- **No annotations/audience/priority on parts** (MCP has `annotations.audience`,
  `priority`). A2A's nearest equivalent is free-form `Part.metadata`.
- **No embedded-resource or resource-subscription block** (MCP `resource` /
  `resource_link` with server-side reads and subscriptions). A2A's `url` part is
  a bare pointer with no protocol-level fetch semantics — fetching is out of
  band (HTTP + the token in the URL, `docs/specification.md:1740-1746`).
- **No rendering/projection rule** — there is no "text fallback" for a file part
  anywhere in the spec. A2A's consumers are agents with harnesses, not
  terminals; the protocol assumes every consumer handles every negotiated mime.
- **No cross-task merge/versioning semantics** — explicitly delegated to
  clients (`docs/topics/life-of-a-task.md:121-131`).
- **No inline `kind` strings** as of v1.0 — carrier-field presence is the tag
  (`docs/specification.md:3484-3527`).
- **Extensibility is out-of-band**: new content behaviors arrive as extension
  URIs declared on AgentCard/Message/Artifact (`a2a.proto:273-274,291-292`,
  `docs/specification.md:1139`), not as new part kinds.

## 7. Lessons for vfs, numbered against the brief

**Q1 (where blocks live).** A2A separates *dialogue* (Message parts) from
*outputs* (Artifact parts) from *status* (TaskStatus) — three channels, one Part
type. Mapped to Result: media evidence is closest to A2A's **Artifact** — named,
id-keyed, described, composed of ordered parts — not to status/message. Their
Artifact fields (`artifact_id`, `name`, `description`, `parts`) look strikingly
like "an Observation about a path that carries content": the brief's
media-as-a-species-of-row option has a working precedent, provided the row owns an
*ordered parts list* rather than a single blob (`a2a.proto:279-293`).

**Q2 (block vocabulary).** A2A's v1.0 evidence argues for a **small
carrier-based vocabulary (text / bytes / reference / structured-data) with mime as
an orthogonal field on every block**, rather than MCP's media-kind taxonomy
(text/image/audio as distinct types). Both real protocols converged on ~3-4 block
kinds; they disagree on whether "image" is a type or a mime. If vfs defines its
own blocks A2A-style (carrier + mime) it gains an open modality set and trivial
SVG/text handling (SVG is just `text` + `image/svg+xml`), and projection onto
MCP's taxonomy is a mechanical mime→type dispatch at the seam. Their v0.3
`FileWithBytes | FileWithUri` and v1.0 `raw | url` show inline-vs-reference as a
*carrier choice within one concept* — the brief's `resource_link` question need
not be a separate block kind (`a2a.proto:224-234`, `docs/whats-new-v1.md:289-359`).

**Q3 (algebra).** A2A's only content-merge law: key by container id, concatenate
parts in arrival order, `append`/`last_chunk` flags (`a2a.proto:307-322`). It
deliberately defines **no dedup and no cross-container merge** — refinement
means new id, same name (`docs/topics/life-of-a-task.md:121-131`). For Result:
`+` concatenating content in op order matches the only semantics A2A found
defensible; expecting media blocks to dedup like path-keyed rows has no precedent
here. A2A also confirms blocks are message-like, not source-like: nothing in
artifact identity is rebased.

**Q4 (ordering).** Parts are a plain ordered `repeated` array inside their
container; order is positional, never keyed, and streams "SHOULD avoid
re-ordering" (`docs/specification.md:2973`). Prior art thus says: preserve order
by *sequence in a container*, and if chunked delivery is ever needed, key the
container, not the block.

**Q5 (budgets).** A2A's budget mechanism is **negotiation, not elision**:
`accepted_output_modes` per call + `history_length` truncation
(`a2a.proto:143-154`) + `include_artifacts=false` defaulting artifact bodies out
of task listings "to reduce payload size" (`a2a.proto:698-700`,
`docs/specification.md:246`). That last one is the closest analogue to the
brief's elide-with-placeholder posture: the heavy channel is opt-in per request.
A2A has no placeholder rendering because its `url` carrier *is* the placeholder —
a reference part costs a URL, not vision tokens.

**Q6 (stdout rule).** A2A offers no help — it has no text projection at all.
Its absence is itself evidence *for* the brief's stance: a protocol built purely
for agent consumers never needed one; vfs needs one only because it also serves a
terminal. The two-consumer problem is vfs-specific and must be solved locally.

**Q7 (mime reality).** A2A keeps mime open-world but makes acceptance
closed-world per interaction: declared modes, per-call accepted list, typed
`ContentTypeNotSupportedError` refusal (`a2a.proto:143-146,386-390`;
`docs/specification.md:559`). Adapted to vfs: pass mime through intact in the
envelope, and let the *projection seam* own the "model can see it or not"
decision — with an explicit, typed downgrade (to reference/placeholder) instead
of silent dropping.

**Q8 (executed-code output).** Nothing direct, but the file-exchange example is
the pattern: an agent that *produces* an image returns a **url part into managed
storage**, not inline bytes (`docs/specification.md:1723-1746`). For sandbox
programs emitting matplotlib PNGs: write to the store, emit a reference block;
inline `raw` is for when the consumer asked for it.

**On the owner's break-from-Unix stance.** A2A is a full independent
confirmation of the core claim: a 1.0, Linux-Foundation-governed, multi-vendor
protocol for inter-agent communication chose *typed parts with per-part media
types* as its smallest unit of content, with no untyped byte-stream channel
anywhere in the design — and its v1.0 revision doubled down (mime on every part).
Nobody building agent-to-agent pipes in 2025 chose stdout. The caveat it adds:
A2A could go pure-typed because it has *no human terminal in the loop*; vfs's
"multimodal CLI" must add the text projection A2A never needed, which is exactly
where the brief's stdout rule (Q6) carries all the novelty.

## 8. Citations index

- Part (v1.0): `~/Git/Repos/A2A/specification/a2a.proto:221-242`
- Message: `a2a.proto:254-277`; Artifact: `a2a.proto:279-293`; Task: `a2a.proto:163-184`
- TaskStatus: `a2a.proto:210-219`; TaskState: `a2a.proto:186-208`
- TaskArtifactUpdateEvent (append/last_chunk): `a2a.proto:307-322`
- StreamResponse: `a2a.proto:790-803`; stream patterns: `docs/specification.md:206-212`; ordering: `docs/specification.md:2973`
- accepted_output_modes: `a2a.proto:143-146`; history_length: `a2a.proto:150-154`; include_artifacts: `a2a.proto:698-700`
- AgentCard modes: `a2a.proto:386-390`; AgentSkill modes: `a2a.proto:447-450`; card example: `docs/specification.md:2168-2200`
- Modality-agnostic principle: `docs/specification.md:38`
- v0.3 kind/FilePart legacy + removal rationale: `docs/specification.md:3434-3527`; `docs/whats-new-v1.md:275-359`
- fileWithBytes/fileWithUri (v0.3): `docs/specification.md:3448-3460`; `docs/whats-new-v1.md:289-296,352-359`
- File exchange example (raw in, url out): `docs/specification.md:1692-1750`
- Schema-in-metadata example: `docs/specification.md:1769-1790`
- Part metadata artifact references: `docs/topics/life-of-a-task.md:112-119`
- Artifact mutation/versioning left to clients: `docs/topics/life-of-a-task.md:121-131,217-235`
- ContentTypeNotSupportedError: `docs/specification.md:559,1186`; sanitize media types: `docs/specification.md:3182`
- MCP relationship: `docs/specification.md:3598-3610`; `docs/topics/a2a-and-mcp.md`
- ProtoJSON decision: `adrs/adr-001-protojson-serialization.md`
- JSON schema non-normative: `specification/json/README.md`
- Streaming/append reassembly: `docs/topics/streaming-and-async.md:21`
