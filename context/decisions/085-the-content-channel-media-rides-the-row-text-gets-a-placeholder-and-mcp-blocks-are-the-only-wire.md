# 085. The content channel: media rides the row, the text projection prints one canonical placeholder, and MCP's five blocks are the only wire

- **Status:** proposed 2026-10-15 (Clay's decisions the same day: MCP
  only, no provider adapters; `dev.vfs/` as the `_meta` prefix; 1 MiB
  per block, 4 MiB per result, 8 blocks; PNG, JPEG, GIF, WebP inline;
  a 32,768-character render cap). Resolves the open question "Result
  content must be typed blocks for the MCP wire" (2026-07-25) and
  takes the July memo's eleven ADR decisions. Feeds specs 167 and
  171; amends spec 152 §10 and spec 155.
- **Date:** 2026-10-15
- **Amended 2026-10-15** after the pre-build review of spec 171 and Clay's answers: all three channels budgeted and the terminal fetch (pin 7); revision-aware degradation and the base64 alphabet (pin 4).
- **Deciders:** Clay Gendron
- **Decided by:** human (Clay set the multimodal-from-day-one rule and
  MCP as the only wire; the assistant drafted the projection from the
  July memo and the 2026-10-15 re-verification)

## Context

`research/2026-07-25-multimodal-result-content.md` decided the shape:
media rides on `Observation` rows, no stored block vocabulary, blocks
minted only at the boundary by an adapter that never fetches, a
canonical text placeholder that never carries base64. Spec 152 slice
A landed the storage half: `Entry.data` XOR `content`, `mime_type`,
`vfs_blobs`, the renderer seam. Study `08-mcp-content-blocks.md`
re-verified the wire on 2026-10-15:

- The current MCP revision is 2026-07-28. The block vocabulary is
  unchanged in shape since 2025-06-18: `text`, `image`, `audio`,
  `resource_link`, embedded `resource`, with the same required fields
  and annotations. There is no video block and the schema rejects one.
  New around the blocks: `resultType` required on every result;
  `structuredContent` any JSON value; required `ttlMs` and
  `cacheScope` on list and read results; `subscriptions/listen`
  replaces subscribe; not-found is `-32602`; a typed `_meta` key
  grammar with reserved prefixes. No tool-result size guidance and no
  accepted image mime list for content blocks.
- Clients, verified in source: text is the only block every client
  renders; image is the only media block every harness shows a model;
  opencode flattens a link to a bare URI and moves images into a
  following user message; codex renders links as raw JSON text and,
  when `structuredContent` is present, discards the content array;
  Claude Code's docs name PNG, JPEG, GIF and WebP inline, a
  25,000-token result cap including image data, and originals saved to
  disk; a closed bug and Anthropic's SDK say links and blobs are
  dropped. Nobody fetches a resource link.
- The live tree, executed: `to_str()` renders a bytes row as an empty
  body; `to_payload()` inlines base64 bytes without bound when `data`
  is projected.
- bash-tool caps each stream at 30,000 characters with a marker; it is
  the only cap tuned for a model's context. just-bash-py's silent stop
  at 100,000 lines with exit 0 is the anti-pattern.

## Options considered

- **Rows inside, MCP's five blocks at the boundary, one text block
  first, links for the rest (chosen).** Pros: survives every client;
  the text block and the payload each stand alone; one adapter.
  Cons: a dropping client loses the media and keeps only the
  placeholder, which is the floor by design.
- **Provider-specific adapters (Anthropic, OpenAI, LangChain).**
  Rejected by Clay: MCP only.
- **Embedded blobs for non-image media.** Rejected at v1: exactly one
  client renders them, and only PDFs.
- **Per-row interleaved blocks as the primary channel.** Rejected: two
  of four clients destroy interleaving.
- **Base64 in a text block.** Rejected, ever: fastmcp still does it and
  it is token noise.

## Decision

Twelve pins.

1. **The row is the one internal representation.** `content` XOR
   `data`, plus `mime_type`, `size_bytes`, `path`, `kind`, `version`,
   `content_hash`. No block vocabulary inside the envelope. Modality is
   derived from the mime at projection time.
2. **The placeholder, one line, enforced at the render chokepoint.**
   Grammar: `[binary <path> <mime> <size>B v<version>[ -- <description>]]`,
   ASCII, no newline, no `|`, exact byte count, the description the
   first line of the rendering truncated to 80 characters. Emitted by
   `render_result` for the verb tools, in multi-row plain renders and
   at the `cli` display, for any row whose source is bytes or whose
   `data` is populated, whether or not `data` was fetched, so the text
   projection never depends on the fetch; a row with a rendering prints
   the placeholder, then the rendering. It never enters a byte seam: a
   single binary read crosses a pipe raw (ADR 083).
   Text-native media (SVG, any `text/*` stored as bytes) renders as its
   text. Base64 never reaches a text stream. Inbound, a resource link
   renders as `[link <uri> <mime> <size>B -- <name>]` and an unknown
   block as `[unknown block <type>]`.
3. **The render cap is 32,768 characters** (Clay, 2026-10-15), an
   opt-in `budget` on the renderer that the `cli` display and the MCP
   adapter pass; a pipe is never capped. One canonical marker states
   characters removed, rows remaining and how to page, op-aware. The
   cap never cuts the errors section; the body is cut to fit, stdout
   before stderr, and the renderer reports how many rows it showed. It
   is a rendering fact; the execution byte budget of ADR 084 is the
   separate refusal.
4. **The wire is MCP's five blocks, verbatim**, every field named as
   the schema names it, no sixth block. The adapter knows the
   negotiated revision: a client older than 2025-06-18 gets only text
   and image blocks and no `structuredContent`; links and audio fall
   back to the placeholder text, never a refusal. Unknown
   block types arriving from a peer are preserved raw in a
   `raw_blocks` extra on the `Result` and degraded to the placeholder
   row. Image data is standard base64, not URL-safe.
5. **Order and sufficiency.** One `TextContent` first holding the whole
   rendered `Result`, then typed blocks in row order. The text block
   must be sufficient alone and `structuredContent` must be sufficient
   alone, because clients differ.
6. **The row-to-block table.** A text row is text only. A bytes row
   with `data` unfetched is the placeholder only. An accepted image
   (PNG, JPEG, GIF, WebP) within budget is `ImageContent`. `audio/*`
   within budget is `AudioContent`. Everything else, and anything over
   budget, is a `ResourceLink` with `uri: vfs:///<global path>`,
   `name`, `mimeType`, `size` and the placeholder as description.
   Never an embedded blob at v1. Directories, edges, version rows and
   the grants extras are text only; a program-output row is text only
   until `/.vfs/run` is served; a bytes row with no mime is a link with
   `application/octet-stream`; text-native bytes render as text. Spec
   171 §2.3 holds the full table.
7. **Budgets are per result, on all three channels**: 1 MiB raw per
   block, 4 MiB per result, at most 8 typed blocks, at most
   `LINK_BUDGET` (64) resource links for rows in the shown set (past
   it, the placeholder only), inline blocks first-fit in row order, and
   `structuredContent` carries
   the same rows the text block showed plus one truncation warning,
   never more (a 10,000-row listing is not 1.8 million characters of
   payload beside 32,768 of text). A `cli` call whose last stage is a
   single bytes read fetches the bytes at the terminal boundary under
   this budget, so a host that exposes only `cli` can show a model an
   image.
8. **`_meta` on every typed block** carries `dev.vfs/path` and, only
   when `version` is populated and not null, `dev.vfs/version` (Clay:
   vfs owns `vfs.dev`). `lastModified` from
   `updated_at` on links. No other annotation is load-bearing.
9. **`isError = not result.success`.** Rows plus warnings are not an
   error. On error the text block leads with the errors section,
   compactly, then rows. A classified refusal is a tool execution
   error, never a JSON-RPC protocol error; protocol errors are for
   unknown tools and malformed requests. For the verb tools the text
   leads with the errors section, rendered by `render.py`. For `cli`
   the text is stdout then stderr; a program's own non-zero exit never
   sets `isError`; a stage's classified fatal error (`ls /nope | wc
   -l`) does, since `success` is derived from the errors; a refusal
   before anything runs is fatal; a wall deadline is fatal.
10. **`structuredContent = Result.to_payload()` with row bytes
    stripped** and `data` removed from each row's populated mask, so a
    round trip rebuilds an honest "not fetched" row; it carries exactly
    the rows the text block showed plus one `budget_exhausted.truncated`
    warning, with `max_errors` 100. `to_payload(include_bytes=False)`
    is the default and never carries bytes on the wire; the flag keeps
    the in-process round-trip tests. `outputSchema` is a declared
    `ResultPayload` model, not the raw envelope schema. The
    spec's SHOULD to restate JSON in a text block is not followed; the
    text block is the rendered table.
11. **`resources` is implemented minimally at v1** so links are
    honest: capability `{}`, an empty list with `ttlMs: 0` and
    `cacheScope: "private"`, one template `vfs:///{+path}`, and `read`
    answering text for a text row and a blob with its mime for a bytes
    row through `read(columns={content, data, mime_type, kind, version,
    size_bytes})` with the caller's authority; a directory, not found
    and denied are `-32602`; a row over `RESOURCE_READ_BYTE_BUDGET`
    (12 MiB), decided by a `stat` before any bytes are fetched, is
    `-32603`; one RFC 3986 URI codec.
    The scheme is `vfs:///`, never `file://` (a client that fetches
    `file://` on its own would read the host's disk).
12. **Guests see the placeholder through the pipe and bytes through a
    file open** (ADR 083). An existing row keeps its source when the
    body allows. A new row a program writes is `content` when the body
    is UTF-8 without NUL and the extension is not on the binary list,
    else `data`; never sniffed alone.

## Consequences

- `render.py` gains the placeholder and the cap; `envelope.py`'s
  payload loses bytes on the wire; spec 155's budget, empty-result and
  score fixes land alongside.
- The MCP adapter is one module beside the renderer, pure, and never
  fetches. It is also the inbound path for MCP tool results (ADR 082
  pin 15).
- Audio and video are stored and linked today; renderers for them (a
  transcript, a caption header) are spec 152's pattern applied to two
  more mimes, later.
- Clients that drop links still see path, mime, size and version in
  the text, and can re-read with `columns={"data"}`.
- The `vfs.dev` domain carries a public namespace commitment: the
  `_meta` keys are part of the wire contract.
