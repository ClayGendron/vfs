# 171 — The MCP adapter and `serve()`: one `cli` tool beside the verbs, rows projected to MCP's five blocks, a minimal `resources` capability

- **Status:** draft — cut 2026-10-15 from ADR 085 and ADR 082 pin 12, and the peers' tool contracts. Resolves the open question "`serve()` re-spec: one tool with a verb argument, or one tool per verb?" (the answer: the verbs as tools, plus `cli`). Amended the same day by the pre-build review (`../../../research/studies/2026-10-15-agent-shell/16-spec-171-review-before-build.md`) and Clay's eight decisions on it (recorded in §0 and the "Decisions" list below). Lands after spec 167; independent of 168–170. Not started. One `[NEEDS CLARIFICATION]` in §3.
- **Date:** 2026-10-15
- **Owner:** Clay Gendron
- **Kind:** feature (`src/vfs/mcp/`: the entry point `serve()` over the official `mcp` SDK, the adapter `to_call_tool_result` and its inverse, the schemas, the `resources` handlers, the `vfs:///` URI codec; `render.py` gains errors-first order and a shown-row count; `ops.py` gains `AGENT_OPS`; `pyproject.toml` gains the `mcp` extra; `tests/support/mcp_schema/` holds the vendored schemas).
- **Depends on:** ADR 085 (all pins, as amended by this spec's review); ADR 022 (the topology rule); ADR 084 pins 3, 5, 6; ADR 083 pin 7; spec 167 (the `cli` meta-verb, the placeholder and the render cap); spec 149 (`authority_from_token`, the token verifier, the open-mount refusal), which lands with or before this; the `mcp` and `mcp-types` 2.x SDK (speaks 2026-07-28 and the legacy handshake); `results/envelope.py`'s `to_payload`/`from_payload`; `params.py`'s `PARAMS`.
- **Research it stands on:** the memo §10, §11; study `08-mcp-content-blocks.md` (the vocabulary, the client matrix, the executed wire validation under three revisions in `experiments/s8/`); study `09-agent-shell-peers.md` F3 (the tool descriptions verbatim) and fork 1; the review above and its probes in `experiments/r171/` (`p1` schema and payload sizes, `p1b` columns and base64, `p2` the SDK's per-revision sieve, `p3` input schemas, `p4` replay).

**Decisions (Clay, 2026-10-15, on the review's questions).**

1. A non-zero exit code is not an MCP error. `isError = not result.success`; a program's own non-zero exit (`grep` with no match, `false`) leaves `success` true, and `exit_code` rides in the extras.
2. No shell state persists between `cli` calls on the wire. Each call starts at `workdir`, default `/`.
3. `structuredContent` carries the same rows the text block showed, plus one truncation warning. Links get `LINK_BUDGET` 64. `max_errors` is applied.
4. The three MCP `schema.json` files are vendored under `tests/support/mcp_schema/` with their licence notice. No network in tests.
5. Clients on revisions older than 2025-06-18 get degraded blocks: links and audio flattened to the placeholder text. Never a refusal. The adapter knows the negotiated revision.
6. A `cli` line whose last stage is a single bytes read fetches the bytes at the terminal boundary, under the media budget, so a host exposing only `cli` can show a model an image.
7. `serve()` only at v1. No `vfs serve` command.
8. Over HTTP a request with no token is anonymous, judged by the ladder. A token derives the `Authority` per request through `get_access_token()`. stdio takes `serve(authority=…)`. A handler never passes `authority=None`. The system actor is refused. A spy test pins zero `None` authorities.

## Intent

After this spec a host runs `await serve(fs, transport=…)` and an MCP client sees the vfs verbs as tools plus one `cli` tool whose input is a command string. Every tool returns one text block holding the rendered result, typed blocks for media within budget, resource links for some of the rest, and `structuredContent` carrying the same rows the text showed. Every channel is bounded, whatever the batch size. A `vfs:///` link can be read back through `resources/read`. Every request runs under an `Authority` derived for that request alone, and never under the system actor.

## 0. The entry point and identity (`mcp/serve.py`)

- **The signature.**

  ```python
  async def serve(
      fs: VirtualFileSystem,
      *,
      transport: Literal["stdio", "http"],
      authority: Authority | None = None,          # stdio only
      token_verifier: TokenVerifier | None = None, # http only (spec 149)
      host: str = "127.0.0.1",
      port: int = 8000,
      tools: Collection[str] | None = None,
      allow_open: bool = False,
  ) -> None
  ```

  There is no `vfs serve` console command at v1; it waits for a router-construction story (a URL, mounts) of its own.
- **The package.** `vfs.mcp` imports `mcp` and `mcp_types` at module top. They install through a new extra `vfs-py[mcp]` pinning `mcp>=2.3,<3`; the dev group gains `mcp` and `jsonschema` so the suite covers the package at 100%. The core install never imports `vfs.mcp`.
- **Identity, per request.** The 2026-07-28 revision has no sessions, so there is nothing to bind an authority to but the request.
  - Streamable HTTP: the handler calls the SDK's `get_access_token()` (the per-request contextvar set by the bearer middleware). A verified token gives `authority_from_token(claims)` (spec 149). No token gives `Authority.anonymous()`, judged by the ladder like any caller, so it reaches exactly what each mount's posture gives everyone. An invalid token is HTTP 401 before any handler runs.
  - stdio: the host passes `authority=` once and it serves every request on the pipe. `authority` is required for stdio and refused for http; a `token_verifier` is the reverse.
  - A handler always passes an explicit `authority=` to the router. It never passes `None`, so the router's `default_authority` fallback (`base.py` `_admitted`) is never reached from the wire.
  - The system actor is refused: `serve()` raises before binding a transport when the stdio authority or `fs`'s `default_authority` is `Authority.system()`, and `authority_from_token` already refuses the reserved system `sub` (spec 149). The system actor is the only authority under which a payload's declared `owner_id` is honoured, so this rule is what keeps identity off the wire.
- **The served tool set.** `(fs.capabilities() & AGENT_OPS) | {"cli"}`, intersected with `tools` when the host passes it (this is how a host exposes only `cli`: `tools={"cli"}`). `AGENT_OPS = ALL_OPS - DEVELOPER_OPS` is a new derived constant in `ops.py` (after spec 167 removes `run`, it holds 20 verbs: copy, delete, edit, glean, glob, grant, grants, graph, grep, ls, mkdir, mkedge, move, read, restore, revoke, rmedge, stat, tree, write). An unknown dialect withholds `glean` and `graph` from `capabilities()`, so it serves 18 verbs plus `cli`.
- **The topology rule (ADR 022).** A served node exposes no topology mutation, and any opt-in is loud and needs both the server and the node to agree. No mount-admin verb is in `ALL_OPS`, and no `cli` program reaches one, so the rule holds by construction; a test pins that no served tool and no kernel program names `add_mount`, `remove_mount`, `bind`, `unbind` or `remount`.
- **The open-mount refusal (spec 149).** `serve()` refuses to start while any bound mount's posture is `open` unless `allow_open=True`; the refusal names the mounts.
- **Cache hints.** The server is built with `Server(cache_hints=…)` giving `CacheHint(ttl_ms=0, scope="private")` for `tools/list`, `resources/list`, `resources/templates/list` and `resources/read`. Without them the SDK rejects a 2026-07-28 `tools/list` (`experiments/r171/p2`).
- **Synchronous, complete-only, and re-issue.** Served calls are synchronous and return `complete` only (spec 149 rule 5; no MRTR, no tasks). A broken response stream does not cancel a mutation in flight: the handler shields the router call, so a batch commits or fails as it would in process. A client that re-issues a call meets the verbs' own replay behaviour, which each mutating tool's description states and a replay test pins per verb. Today (`experiments/r171/p4`): a `write` of identical content reports `updated`; a second `mkedge` reports `updated`; a second `move` or `delete` is a `not_found` failure even though the first call succeeded.

## 1. The tools (`mcp/schemas.py`)

### 1.1 Input schemas come from `PARAMS`, never from signatures

- One function `input_schema(op) -> dict` projects `vfs.params.PARAMS[op]`, one branch per `ParamKind`. Python signatures are never introspected: the SDK's `func_metadata` fails on 7 of the 20 verbs and exposes `authority` on the other 13 (`experiments/r171/p3`).
- The plain kinds map directly: `path` and `str` to `string` (with `enum` from `choices`), `int` to `integer` with `minimum`/`maximum`, `bool` to `boolean`, `str_seq` to an array of strings. The router's param gate already accepts JSON lists for `str_seq` and `str_set`, so the handler passes them through unchanged.
- The awkward kinds:

  | Parameter (kind) | Verbs | On the wire |
  |---|---|---|
  | `authority` (`authority`) | all 20 | never; filled per request (§0) |
  | `observations` (`observations`) | read, stat, ls, delete, restore, edit, glob, grep, glean, graph | never; row-addressed chaining is the `cli` pipe's job (`glob … \| grep` passes rows in process) |
  | `columns` (`str_set`) | read, stat, ls, tree, glob, grep, glean, graph | array, `uniqueItems: true`, items an `enum` of `OBSERVATION_FIELDS` |
  | `entries` (`entries`) | write | array of `{path, content}` or `{path, data}` objects; no other `Entry` field (`owner_id`, `external_id`, `content_hash`, timestamps, `render_status`) is accepted |
  | `data` (`bytes`) | write, and `entries[].data` | a standard-base64 string (RFC 4648 §4); the handler decodes with `base64.b64decode(validate=True)`; a decode failure is `invalid` |
  | `moves`, `copies` (`pairs`) | move, copy | array of `{src, dest}` objects |
  | `edges` (`edges`) | mkedge, rmedge | array of `{source, target, edge_type, weight?}` objects |
  | `edits` (`edits`) | edit | array of `{old, new, replace_all?}` objects |
  | `provenance` (`str`) | mkedge | never; the handler stamps `agent` when the actor's kind is `service`, else `user` |

- The SDK's low-level server does not validate arguments, so the handler builds the router call through one inverse function `call_args(op, arguments) -> dict` that accepts only projected names and the restricted item shapes above; an unknown name, an extra item field (an `owner_id` on an entry) or a malformed base64 string is `invalid` before the router is called.
- `RULES` and `VALUE_RULES` are not encoded in JSON Schema. The router's param gate refuses them as `invalid`, which reaches the client as `isError: true` (MCP 2025-11-25, SEP-1303: input validation is a tool execution error).
- A drift test pins that every `PARAMS` row of every `AGENT_OPS` verb is either projected or named in a `WITHHELD` set (`authority`, `observations`, `provenance`).

### 1.2 The output schema is a declared wire model

- `outputSchema` is the schema of a declared model `ResultPayload` in `mcp/schemas.py`: `success` (boolean, required); `ops`, `observations` and `errors` (required); the known extras as optional typed properties (`grants`, `members`, `exit_code`, `statuses`, `stderr`, `set_e_tripped`); `additionalProperties: true` so a newer peer's fields stay legal. It is not `Result.model_json_schema()`, which validates every payload today only because it declares no `required` and omits `success` (`experiments/r171/p1` §A).
- A drift test pins that `ResultPayload` validates every `structuredContent` the adapter emits, and that its row properties equal `Observation`'s fields. The schema's size is measured in the test and recorded in the landing notes.

### 1.3 Descriptions and annotations

- Each verb tool's `description` is its entry in a `TOOL_DESCRIPTIONS` table in `mcp/schemas.py`: one or two plain sentences, plus the replay line for a mutating verb (§0). A drift test pins one entry per `AGENT_OPS` verb.
- Tool annotations are derived from `ops.py`, never hand-set: `readOnlyHint = op in READ_OPS or op == "grants"`; `destructiveHint = op in {"delete", "move", "write", "edit", "revoke"}`; `idempotentHint` is not set. `cli` is neither read-only nor marked destructive.

### 1.4 The `cli` tool

- Input: `{command: string}` or `{argv: string[]}` (`oneOf`), optional `workdir: string` (default `/`), optional `timeout_ms: integer` (minimum 1).
- `timeout_ms` can shorten the line's deadline, never lengthen it: the deadline is `min(timeout_ms, WALL_TIME_BUDGET)` (ADR 084 pins 5 and 6).
- Each call runs in a fresh shell session at `workdir` with an empty environment (decision 2). `cd`, `export` and `history` last for the rest of the line only. Spec 167's `Session` fields are not carried across calls on the wire; a sealed session handle is a later spec.
- The handler calls `fs.cli(command | argv, authority=…, cwd=workdir)`.
- The description is the text in the appendix, verbatim. It may be shortened for a host that exposes only `cli` by dropping the sentence that points at the `read` tool.

## 2. The adapter (`mcp/adapter.py`)

### 2.1 Shape

- `to_call_tool_result(result, *, revision: str, projection=None) -> CallToolResult`. Pure: it never fetches and never performs I/O. It runs only at the final boundary; a projected payload is never stored or re-forwarded (July memo D2). `from_call_tool_result` (§2.6) is the one sanctioned way back in.
- One `TextContent` first, then typed blocks in row order. The text block and `structuredContent` must each be sufficient alone (ADR 085 pin 5).
- `isError = not result.success`, for every tool including `cli`. On every wire test, `isError == not structuredContent["success"]` (July memo A1).
- `resultType` is left to the SDK, which stamps it on modern sessions and omits it on legacy ones.

### 2.2 Every channel is budgeted, and the three agree

- **The text block** is `render.py`'s capped rendering (spec 167's 32,768-character cap), under `projection` when the caller passed `columns`, else the op's default.
- **`structuredContent`** carries exactly the rows the text block showed before the cap (`render.py` reports the count; §2.4), and `to_payload(max_errors=PAYLOAD_ERROR_BUDGET)` with `PAYLOAD_ERROR_BUDGET = 100`. Rows past the shown set are elided from the payload and named by one warning `vfs.budget_exhausted.truncated` with `data["vfs.elided"] = {"rows": N, "first": <path>}` and the same paging hint as the text marker. Without this, a 10,000-row `ls` is 1,790,064 characters of payload against 32,768 of text (`experiments/r171/p1` §D), and codex shows the model only the payload.
- **Typed blocks** follow ADR 085 pin 7: at most 8 blocks, at most 1 MiB raw each, at most 4 MiB raw per result. The inline budget is first-fit in row order: a row that does not fit becomes a link, and later rows may still inline.
- **Resource links** are minted only for rows in the shown set, at most `LINK_BUDGET = 64` per result. A row past the link budget keeps its placeholder in the text and its row in the payload.
- Elision never changes `success`. In process, nothing is dropped. Every budget is a declared constant in `mcp/adapter.py`; a host may tighten, never loosen. The caps come from client and transport limits (codex's substitution of `structuredContent` for `content`, Claude Code's 16 MiB transport cap and 25,000-token result cap), not from vfs, and the module docstring says so.

### 2.3 The row-to-block table

The adapter's tests walk this table row by row.

| Row or result shape | Text block | Typed block | `structuredContent` |
|---|---|---|---|
| file, `content` set | rendered | none | row |
| file, bytes, `data` not populated | placeholder | none | row |
| file, bytes, `data` populated, image (PNG, JPEG, GIF, WebP) within budget | placeholder | `ImageContent` | row without bytes |
| file, bytes, `data` populated, `audio/*` within budget | placeholder | `AudioContent` | row without bytes |
| file, bytes, `data` populated, anything else or over budget | placeholder | `ResourceLink` within `LINK_BUDGET`, else none | row without bytes |
| file, bytes, `data` populated, `mime_type` not populated | placeholder with `?` for the mime | none; the mime is never guessed | row without bytes |
| SVG or `text/*` stored as bytes, `data` populated | its rendering, as text | none | row without bytes |
| directory, edge, graph node, trash or version row | rendered | none | row |
| program output at `/.vfs/run/<call>/stdout`, text | verbatim | none | row |
| program output, bytes | placeholder | none: no link until spec 169 serves `/.vfs/run`; an image within budget may inline | row without bytes |
| `grants=` / `members=` extras | the grants table | none | extras |
| `cli` extras (`exit_code`, `statuses`, `stderr`, `set_e_tripped`) | stderr lines after the rows, then the statuses | none | extras |
| fatal error | errors section first (§2.4) | none | errors (rolled up past 100) |
| warning or info | after the rows, never cut by the cap (§2.4) | none | errors (rolled up past 100) |

- "Row without bytes" means `data` removed and `"data"` removed from `populated`, so `from_payload` rebuilds an honest "not fetched" row (ADR 085 pin 10; `experiments/r171/p1` §C shows that dropping the bytes but keeping the mask makes a row claim "fetched, and null").
- `_meta` on every typed block carries `dev.vfs/path`, and `dev.vfs/version` only when `version` is populated and not null. Links carry `name` (the basename), `mimeType` when populated, `size` from `size_bytes` when populated, the placeholder as `description`, and `annotations.lastModified` from `updated_at` when populated.
- The tool handler, not the adapter, adds `{path, kind, mime_type, size_bytes, version}` to any requested projection that includes `data`, so the adapter rarely meets a bytes row without its mime. `read(columns={"data"})` alone populates no mime (`experiments/r171/p1b`).

### 2.4 The text block: errors first, and the cap never cuts them

Owned here, in `render.py` (spec 167 task zero lands the placeholder and the cap; this spec changes their order):

- `render_result` leads with the errors section when `not result.success`. Today the body renders first and errors after it (`render.py:62-71`).
- The cap never cuts the errors section. When the text exceeds the cap, the body is cut to fit; the errors section and the marker are always printed, on success (warnings) and on failure alike.
- `render.py` exposes the number of rows the capped text showed (a `Rendered(text, shown)` value from one function the adapter calls), so the payload can carry the same rows.
- The marker's paging hint is op-aware. Under `cli` it names `head`, `tail` and `sed -n`. On a verb tool it names the verb's own bound (`max_count` for `glob` and `grep`, `limit` for `glean` and `graph`), or the `cli` form (`cli: sed -n 'A,Bp' <path>`) for `read`, `ls`, `stat` and `tree`, which have none.

### 2.5 Revisions and encoding

- **Degraded blocks below 2025-06-18** (decision 5). `revision` is the negotiated protocol version (`ctx.protocol_version`). For 2024-11-05 and 2025-03-26 the adapter emits only `TextContent` and `ImageContent`: no `ResourceLink`, no `AudioContent` and no `structuredContent` (none of the three is in both revisions' vocabulary). The rows those blocks would have carried keep their placeholders in the text. A client is never refused. The SDK's own per-revision sieve does not strip these blocks (`experiments/r171/p2`), so the adapter must.
- **Standard base64.** `ImageContent.data`, `AudioContent.data` and `BlobResourceContents.blob` are encoded with `base64.b64encode` from the row's `bytes`, never taken from the row's JSON: `Observation` serializes bytes as URL-safe base64, which a strict standard decoder rejects (`experiments/r171/p1b`). A test uses bytes whose base64 needs `+` and `/`.

### 2.6 The inverse (`from_call_tool_result`, for spec 170)

`from_call_tool_result(result, *, at: Path) -> Result`:

- If `structuredContent` is a vfs payload (it has `ops`, `observations` and `errors`), the result is `Result.from_payload(structured | {"success": not isError})`. Each typed block whose `_meta["dev.vfs/path"]` names a row puts its bytes back on that row (`data` set, `"data"` added to `populated`), since the payload carries none.
- Otherwise the blocks become rows under `at`: the text blocks join into one `content` row at `at/stdout`; each image or audio block is a bytes row at `at/<n>.<ext>` with its mime; a link is a row at its own `vfs:///` path, or at `at/<n>` for a foreign URI, with `source` the URI and no bytes; a non-vfs `structuredContent` is one `application/json` row at `at/structured.json`.
- An unknown block type is kept raw in a `Result` extra `vfs.blocks` and rendered as its placeholder; it is never dropped. `Observation` is not open, so the raw block cannot ride a row.
- Block bytes decode with `base64.b64decode(validate=True)`; a failure quarantines the block as a warning, as `from_payload` quarantines a malformed row.
- `isError: true` with no classifiable error becomes the fatal `vfs.internal` claim `from_payload` already synthesizes. Spec 170's open marker on the `isError` kind is answered by this rule.

## 3. `cli` at the boundary (amends spec 167 §4 and ADR 083 pin 7)

- **The verdict** (decision 1). A line refused before anything runs (`vfs.unsupported.construct`, `vfs.invalid.syntax`, a parser or argv budget, the system actor) is a fatal error on the `Result`. A stage's classified errors (a `cat` of a missing file) ride the `Result` at warning severity, as `merge_branches` demotes fan-out, so they show in the text and the payload without failing the call. A program's own non-zero exit is evidence in `exit_code` and `statuses` and never sets `isError`. `Decided 2026-10-15 (default applied): a wall-deadline timeout (`vfs.timeout`, exit 124) is a fatal error on the `Result`, so `isError: true`; rows already emitted ride with it. Reconciled with spec 167 §6 the same day: a stage's classified fatal error (`ls /nope | wc -l`) makes `success` false and `isError` true even when `exit_code` is 0, because `success` is derived from the errors; a program's own non-zero exit does not.`
- **The terminal fetch** (decision 6). When the last stage of a line is a single bytes read (`cat` or `read` with exactly one operand, no redirection of its stdout), the shell projects `data` plus the identity columns of §2.3 at the terminal boundary. The adapter then applies the media budget: an accepted image within budget inlines, anything else becomes a link or stays a placeholder. A text file's row carries no `data` (the `content`/`data` split is exclusive), so the extra projection costs nothing there. Any other last stage keeps elide-by-default.

## 4. `resources`

- Capability `{}`. `resources/list` is empty. `resources/templates/list` is one template `vfs:///{+path}`, named `vfs path`. All three carry `ttlMs: 0`, `cacheScope: "private"` (§0).
- `resources/read` runs `read(path, columns={"content", "data", "mime_type", "kind", "version", "size_bytes"})` with the request's authority (§0). Today `columns={"data"}` alone returns nothing for a text file and no mime for a blob (`experiments/r171/p1b`).
  - A row with `data` returns one `BlobResourceContents{uri, mimeType, blob}` (standard base64).
  - A row with `content` returns one `TextResourceContents{uri, mimeType?, text}`.
  - A directory is `-32602` with `data.reason = "directory"`.
  - Not found, hidden and denied are `-32602` with `data.uri`, and the message never says which.
  - A row whose `size_bytes` exceeds `RESOURCE_READ_BYTE_BUDGET` (12 MiB raw, so base64 stays under Claude Code's 16 MiB transport cap) is `-32603` with `data = {"size_bytes", "budget"}`, and the bytes are never fetched (a `stat` decides first). The docstring names the future direction: ranged reads, which MCP does not have yet.
- **The URI codec.** One pair, `vfs_uri(path) -> str` and `path_from_vfs_uri(uri) -> Path`, mints and parses every URI the server emits or accepts: scheme `vfs`, empty authority, the global path percent-encoded per RFC 3986 with `/` kept. A URI with an authority, a query or a fragment is `-32602`. Never `file://`.

## 5. The wire validation

- The three MCP `schema.json` files for 2025-06-18, 2025-11-25 and 2026-07-28 are vendored under `tests/support/mcp_schema/<revision>/` with the upstream licence notice beside them (decision 4). The tests use no network.
- A test drives the server through the SDK's client over stdio with a logging relay (the study's experiment shape) in four modes: pinned 2026-07-28, `auto`, `legacy` (negotiates 2025-11-25), and a forced 2025-03-26 handshake (a raw `initialize` with that `protocolVersion`, sent through the relay).
- Each result is validated against the schema of the revision its session negotiated and against every older vendored revision down to 2025-06-18: a modern result against all three, a legacy result against 2025-11-25 and 2025-06-18 only (it has no `resultType` by design, so it is never checked against 2026-07-28). The 2025-03-26 session asserts the degraded shape of §2.5 (text and image blocks only, no `structuredContent`), since no schema for it is vendored.
- Error results are validated against `ResultPayload` explicitly: the SDK's client skips output-schema validation when `isError` is true.
- Hand-built instances are rejected by the vendored 2026-07-28 schema: a video block, a link without a `name`, an image without a `mimeType`.

## Scope

In: the above. Out: prompts, sampling, logging, subscriptions and `listChanged`, tasks (the background channel when jobs exist), MRTR (`input_required`), a transport other than stdio and streamable HTTP, vendor `_meta` hints (`anthropic/maxResultSizeChars` and kin), a `vfs serve` console command, a sealed `cli` session handle, ranged resource reads.

## Acceptance criteria

1. `tools/list` names exactly the `AGENT_OPS` verbs in `fs.capabilities()` plus `cli`: 21 tools on the default router, 19 on an unknown dialect, 1 with `tools={"cli"}`. None is `sweep`, `posture`, `add_member`, `remove_member` or `run`. No input schema names `authority`, `observations` or `provenance` (counted over the listing).
2. Over the `read` tool: a text file returns one text block and zero typed blocks. `read(path, columns=["data"])` of a 70-byte PNG returns the placeholder text and one `ImageContent` whose `_meta` holds `dev.vfs/path` and `dev.vfs/version`. The same call on an MP4 returns the placeholder and one `ResourceLink` with a `vfs:///` URI and `size`.
3. Over the `cli` tool: `cat /photos/pixel.png` returns one `ImageContent`; `cat /photos/pixel.png | wc -c` returns zero typed blocks.
4. Over the `ls` tool on a directory of 10,000 files: the text block is at most 32,768 characters plus the marker; `structuredContent` holds the same number of rows the text showed and one `vfs.budget_exhausted.truncated` warning whose `vfs.elided.rows` equals 10,000 minus that number (counted).
5. Adapter unit test, in process: a `Result` of 10,000 image rows with `data` populated yields at most 8 typed blocks, at most 4 MiB raw, and at most 64 links; a `Result` of 10,000 errors yields at most 100 plus the rollup entries in `structuredContent` (counted).
6. `structuredContent` carries no bytes, validates against `ResultPayload`, and round-trips through `from_payload` to rows whose `populated` lacks `data`.
7. `isError == not structuredContent["success"]` on every wire test. A classified refusal (`read` of a missing path) is `isError: true` with its first error line within the first 200 characters of the text, even when the batch also holds 5,000 rows. A capped success keeps every warning line. An unknown tool is JSON-RPC `-32602`.
8. `cli('grep nomatch /notes/a.md')` is `isError: false` with `exit_code == 1`; `cli('false')` is `isError: false` with `exit_code == 1`; `cli('for x in a; do :; done')` is `isError: true`. `cli('cd /notes')` then `cli('pwd')` prints `/`. A `timeout_ms` above 10,000 leaves the deadline at 10 s.
9. A spy on the router sees zero calls with `authority=None` across the MCP test module. `serve(fs, transport="stdio", authority=Authority.system())` raises before binding a transport; so does a router whose `default_authority` is the system actor. An HTTP request with no token reads a `shared` mount and is denied on a `private` one; an invalid token is 401. A wire `write` whose entry declares `owner_id` is refused as `invalid` by `call_args`.
10. `serve()` refuses to start with an `open` mount unless `allow_open=True`, and names the mount. No served tool and no kernel program names a mount-admin verb.
11. `resources/read` returns a blob with `mimeType` for a bytes row and the exact text for a text row; a hidden path, a missing path and a directory are `-32602`; a row over 12 MiB is `-32603` and its bytes are never fetched (spied). `vfs:///` URIs round-trip for paths holding a space, `#`, `?`, `%` and a non-ASCII letter.
12. A block built from bytes whose base64 needs `+` and `/` decodes with a strict standard decoder, outbound and inbound.
13. The wire validates in the four session modes of §5 against the vendored schemas, and the 2025-03-26 session carries no link, no audio and no `structuredContent`.
14. The inverse: a vfs payload with one `ImageContent` keyed by `dev.vfs/path` rebuilds the row with its bytes and `"data"` in `populated`; an unknown block type lands in `vfs.blocks` and renders as a placeholder.
15. Each mutating tool's description states its replay behaviour, and a replay test per mutating verb pins it.
16. `scripts/ci.sh` green at 100% coverage with the `mcp` extra in the dev group; the core install imports nothing from `mcp`.

## Appendix: the `cli` tool description

Verbatim, about 2,300 characters. The first paragraph's vocabulary may also go into the server's `instructions` field.

```text
Run a shell command line against this vfs: a filesystem stored in a database
and shared with other agents and people. The shell speaks a bash-shaped POSIX
subset. It is not a computer: no host operating system, no network, no
package manager, no processes that outlive the call.

Who it runs as. Every command runs as you. cat, ls, grep, rm and the rest call
the same verbs as this server's other tools, with your rights and nothing
more. There is no sudo. A path you cannot list does not exist for you. A path
you can list but not read answers "permission denied".

What parses. Pipelines (|); lists (; && ||); ( ) and { }; redirections
(< > >> 2>&1); here-documents; $( ) and backticks; $VAR, ${VAR:-x} and the
POSIX ${...} forms; quoting; globs (* ? [ ] {a,b}); set -e. The whole line is
parsed before anything runs. Refused before anything runs, with a hint:
if/for/while/case, functions, [[ ]], $(( )), <( ), <<<, arrays and &. Split
the work into simpler lines or separate calls.

Programs. cat ls grep rg find tree stat file mkdir rm cp mv touch head tail
sed wc cut nl echo printf test [ basename dirname seq date env pwd cd which
type help, plus glean (ranked search) and graph (follow links between files).
Run "help" or "<name> --help" for the forms each one supports. An unsupported
flag exits 2 and names the missing form. git, curl, python, sudo and chmod are
not here (exit 127, with a hint for what to use instead).

Files. rm moves a file to the trash; the restore tool brings it back. Every
overwrite keeps a version; stat shows the number. A binary file prints one
line instead of bytes: [binary <path> <mime> <size>B v<version>]. When a line
ends by reading one image (cat photo.png), the image itself is returned too.
Otherwise, to see an image, call the read tool with columns ["data"].

Output. You get stdout, then stderr lines, then the exit status of each stage.
Output over 32,768 characters is cut with a marker saying how much was
removed. Page with head, tail, sed -n 'A,Bp', grep -m N, or a narrower path.
A line has 10 seconds (exit 124 when it runs out).

State. Each call starts in workdir (default /) with an empty environment. cd
and export last only for the rest of the line. Use absolute paths across
calls.

Exit status. 0 success. 1 a command failed (not found, already exists,
conflict) or found nothing. 2 bad usage. 124 timeout. 126 found but you may
not run it. 127 not found. A non-zero status is not a tool error; the tool
reports an error only when the line was refused before anything ran.

Input. command: the line to run. Or argv: a list of words, run without
parsing (no globs, no expansion). workdir: where the line starts. timeout_ms:
a shorter limit; it cannot raise the 10-second limit.
```

## Landing notes

(Filled in on landing.)

## Rebase notes of 2026-10-24 (ADR 087 and specs 174–181)

ADR 087 and the eight specs cut from it touch the served surface in the places below. Each note names the owning spec; nothing is built.

- **The `write` tool (174)** gains `if_version`, `if_absent` and `append`, and loses `overwrite` (`if_absent=True` is exactly today's `overwrite=False`). The removal is a public-surface change pending Clay (ADR 087, *Pending Clay*).
- **Integrity (175).** An integrity failure is `isError` with no retry hint. Every write tool's output schema gains `content_hash`. `scrub` is never registered as a tool.
- **Paging (176).** The listing tools take `after` and `limit` from `PARAMS` and pass `limit=LISTING_PAGE` by default. When the text cap cuts rows, the adapter sets the envelope's `next_after` to the last row shown, and the paging hint names `after=`.
- **Replay (177).** The projection table gains the `token` parameter kind. `idempotentHint` is `op in IDEMPOTENT_OPS`, and each tool's replay line is rendered from the `REPLAY` table in `ops.py`; §0's "today" probe sentence is replaced by that table. Criterion 15 is met by 177's `ReplayContract` family. The `cli` description gains one sentence: a re-sent line runs again.
- **Ranges (178).** `range` crosses the wire as an object `{offset, length}`, both 0 to 2³¹−1.
- **Features (179).** The tool list includes the derived verbs; a feature a mount refuses comes back as `vfs.unsupported` with `data["vfs.feature"]`.
- **History (180).** `versions` is a tool with `readOnlyHint` and `idempotentHint`; the `read` tool gains an optional `version`. `sweep` and the garbage gauge never reach the wire.
- **Identity (181).** The withheld `observations` row loses `glob` and `grep` (chaining moves onto `Result`). The `columns` enum and `ResultPayload` gain `entry_id` and `owner_id` automatically. A schema test asserts no tool property is named `entry_id`.
