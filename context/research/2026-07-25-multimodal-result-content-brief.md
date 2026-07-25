# Multimodal Result content: typed content blocks for the wire (brief)

- **Status**: problem brief — a seed, not the memo. A full research memo
  should supersede this file; it commits us to nothing.
- **Date**: 2026-07-25
- **Owner**: Clay Gendron
- **Question**: The `Result` envelope carries rows and errors — text-shaped
  evidence. Models are multimodal, and the MCP tool-result wire format is an
  *ordered array of typed content blocks* (`text`, `image`, `audio`,
  resource links). How does `Result` grow a typed content channel so verbs
  can emit media, results still chain under the algebra, and the wire
  projection emits MCP-shaped content arrays — without breaking the
  envelope's existing contracts?

---

## Why this exists

Two facts collided:

1. **An LLM can only "see" media that reaches it as a typed block.** In
   every model API (Anthropic Messages, and MCP mirrors this), an image is
   `{"type": "image", "source"/"data": <base64>, "mimeType"/"media_type": ...}`
   — a tagged block the harness decodes into pixels for the vision encoder.
   The *same base64 bytes* placed in a text stream are pure token noise; no
   model can see them. Whether media is visible is decided entirely by
   which block type wraps it, i.e. by *us*, at the tool boundary.
2. **The hermetic shell has two output consumers with different physics.**
   The hermetic-runtime direction
   ([2026-07-24-hermetic-runtime-and-wasm-cli.md](2026-07-24-hermetic-runtime-and-wasm-cli.md))
   stands: pipes carry structured values, the shell is the kernel. But the
   shell's output crosses to the model over two channels:
   - **stdout / text projection** — text only, forever. Media can never
     cross here; the best possible representation is a placeholder
     (path/id + mime + size + description).
   - **MCP tool result** — a `content` array where `text` and `image`
     (and `audio`) blocks interleave freely, in order, in one result. The
     model sees prose and pixels together in a single tool call. This is
     the channel that makes the runtime genuinely multimodal.

Today's `Result` cannot express case 2 at all. `to_payload()`
(`src/vfs/results/envelope.py:640`) produces one JSON dict for MCP
`structured_content`; there is no notion of a content block, so a `read`
of a PNG has nowhere to put the image except inside a text field — where
it is invisible.

## What exists today (ground truth for the memo)

- `Result` (`src/vfs/results/envelope.py:249`): frozen `Observation` rows
  keyed by path, `errors` with kind/severity/locus, derived `success`,
  algebra (`+` merge, rebase distributing over merge), lossless
  `to_payload()`/`from_payload()` across the MCP seam. The 057 corpus
  ([2026-07-08-result-envelope.md](2026-07-08-result-envelope.md)) is the
  contract's spine — anything added must obey "verdict/evidence
  disagreement unrepresentable" and "optional dual channels rot."
- `src/vfs/results/render.py` / `projection.py`: the text-facing side.
- The MCP spec and python-sdk studies
  ([2026-04-19-mcp-specification.md](2026-04-19-mcp-specification.md),
  [2026-04-19-mcp-python-sdk.md](2026-04-19-mcp-python-sdk.md)) predate
  this question — re-read them specifically for `CallToolResult.content`
  block types, ordering guarantees, and how `structured_content` and
  `content` coexist in one result.
- nushell's `PipelineData` (`ByteStream` vs `Value`, studied in the
  hermetic memo) is the closest prior art for a shell pipeline that
  carries bytes *as bytes* until a boundary renders them.

## What the full memo needs to settle

1. **Where blocks live.** A `content: list[ContentBlock]` channel on
   `Result`? Media as a species of `Observation` row (they're keyed by
   path — a read of `/charts/q3.png` *is* evidence about a path)? Or a
   projection-time concern only (rows stay bytes-agnostic; the MCP
   renderer fetches payloads)? Each interacts differently with the merge
   algebra and with `from_payload` round-tripping.
2. **The block vocabulary.** Minimum: `text`, `image`, `audio` +
   `mimeType` + base64 data, matching MCP's shapes so projection is
   mechanical. What about MCP `resource_link` / embedded resources —
   vfs paths are natural resource URIs. [NEEDS CLARIFICATION: do we adopt
   MCP's exact block taxonomy or define ours and project onto theirs?]
3. **Algebra semantics for media.** Rows merge keyed by path with
   dedup — what keys a content block? Does `+` concatenate content in
   op order? Does rebase touch blocks (it shouldn't — it rebases
   path/source, never message; blocks are closer to message)?
4. **Ordering / interleaving.** The whole value of the MCP channel is
   *ordered* text-image-text interleaving (a document read where each
   figure appears in place). The representation must preserve order, not
   just carry a bag of attachments.
5. **Budgets.** Images are expensive as vision tokens (thousands per
   image on current APIs). Default posture should probably be
   elide-with-placeholder, media-on-request — same budget doctrine the
   envelope already applies to error lists. A placeholder needs enough
   text (path, mime, byte size, maybe a stored description) for the
   model to decide whether to fetch.
6. **The stdout rule.** One deterministic text rendering for any media
   block (placeholder form), so the CLI/text projection never emits
   base64 into a text stream. Text-native media (SVG is XML) may pass
   through as text — it is model-readable and editable there.
7. **Mime-type reality check.** Model APIs accept a short list
   (image/jpeg, png, gif, webp; audio similar). What happens to media
   outside that list — pass through with mime intact (MCP allows it,
   harness may drop it), or classify at the seam?
8. **Executed-code output.** Programs in the sandbox (Monty/wasm) will
   produce media (matplotlib PNGs, generated audio). How does a program's
   output become typed blocks rather than bytes-on-stdout — is that the
   `run` verb's projection duty?

## Suggested method

Same discipline as 057: primary-source study first —
`~/Git/Repos/modelcontextprotocol` + `python-sdk` (block shapes, harness
behavior), Anthropic Messages API tool_result content rules, nushell
`ByteStream` (bytes-until-boundary), and at least one consumer
(opencode/gemini-cli checkouts already exist) for how real harnesses
forward mixed content. Then adversarial pass against `envelope.py`'s
invariants. Output: a full research memo superseding this brief, feeding
an ADR on the content channel.
