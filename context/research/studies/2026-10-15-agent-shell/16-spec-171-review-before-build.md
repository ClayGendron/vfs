# Review of spec 171 — the MCP adapter, `serve()`, the `cli` tool and `resources`

- **Date:** 2026-10-15
- **Reviewer:** pre-build review, written as the developer who must build it.
- **Tree:** `main` at `ac5c515`, working tree as found. Nothing under `src/`, `tests/` or the spec was modified. New files only under `experiments/r171/` and this file.
- **Clones:** `python-sdk` at `754254c0` (2026-10-13, MIT) and `modelcontextprotocol` at `86f6e0c6` (2026-10-14, MIT moving to Apache-2.0). Read as found, not refreshed (read-only instruction); both are the commits study 08 used.
- **What I read:** spec 171 in full; spec 167 (§1 task zero, §3, §4, §6, acceptance); ADR 085 (all twelve pins); ADR 082 pins 12 and 15; ADR 084 pins 3, 5, 6; ADR 081 pins 6–9; ADR 083 pin 6; ADR 022; spec 149; archived spec 054 and the open questions "serve() topology-lock", "`serve()` re-spec … one tool per verb?" and "MCP 2026-07-28: long-batch execution model"; the agent-shell memo §10, §11, §12; study 08 in full with `experiments/s8/` and its outputs; study 03's exit-code table; study 09 F3, F4 and fork 1; the July memo §4 Q1–Q8 and §5 (A1–H6); the stateless-revision memo §1 and §8.4; specs 169 and 170 where they touch `/.vfs/run` and the inbound adapter. Live tree: `results/envelope.py`, `results/render.py`, `models/entry.py`, `ops.py`, `params.py`, `authority.py`, `base.py` (signatures, `_admitted`, `capabilities`), `session.py`, `pyproject.toml`. SDK: `server/lowlevel/server.py`, `server/runner.py`, `server/caching.py`, `server/auth/middleware/auth_context.py`, `server/context.py`, `mcpserver/utilities/func_metadata.py`, `client/session.py`, `client/client.py`, `mcp_types/version.py`, `mcp_types/methods.py`.
- **Evidence labels:** **EXECUTED** (a script ran; output saved beside it under `experiments/r171/`), **READ** (`file:line`), **INFERRED** (my reasoning from the two).

## Verdict

The spec is not ready to build. Its direction is right and ADR 085 already decided most of the hard things. But the spec is 105 lines over a wire with five moving parts, and a builder hits four walls on day one. First, only one of the wire's three channels is bounded: a 10,000-row `ls` puts 1.79 million characters into `structuredContent`, which one client shows the model instead of the text. Second, the input schemas have no named source, and the obvious source, the SDK's signature introspection, fails on 7 of 20 verbs and exposes `authority` on the other 13. Third, the `cli` tool's error verdict is defined twice, by ADR 085 and by study 03, and the two disagree. Fourth, how an `Authority` reaches each call under the stateless revision is unspecified, and nothing stops a server from answering as the system actor. Each wall has a short amendment below.

## Readiness score: 47 / 100

Eight dimensions. Each is scored against what a builder needs to start without asking a question.

| # | Dimension | Score | Why |
|---|---|---|---|
| 1 | Intent and scope | 8 / 12 | Intent is clear and the out-of-scope list is good. `serve()`'s signature and the `vfs serve` command are named but not defined. |
| 2 | Fidelity to the decisions | 8 / 12 | ADR 085's pins are carried. ADR 022's one-line topology rule, spec 149's open-mount refusal and the stateless revision's "no sessions" are not. |
| 3 | The row-to-block contract | 6 / 13 | The spec points at ADR 085 pin 6. That table covers file rows only. Directories, edges, grants extras, program output, a missing mime and a null version are not placed. The inverse adapter has no table. |
| 4 | The tool interface | 4 / 13 | No source for input schemas; the `cli` description is promised from an appendix that does not exist; the output schema conforms but declares almost nothing. |
| 5 | Identity and security | 6 / 13 | "The `Authority` spec 149 derives from the session" has no session to derive from. The system actor, `mkedge`'s `provenance="system"` default and a declared `owner_id` are unguarded. |
| 6 | Scale and bounds | 3 / 13 | `structuredContent`, resource links, error lists and `resources/read` all grow with batch size. |
| 7 | Testability | 6 / 12 | Criterion 6 cannot pass as written. Criterion 2's 10,000-image read is unreachable through the wire tools. Most criteria count nothing. |
| 8 | Sequencing and dependencies | 6 / 12 | Depends on 167 and 149 correctly. Misses: `mcp` is not a dependency; `/.vfs/run` links dangle until spec 169; errors-first rendering has no owner. |

## Findings, most severe first

### 1. Only one of the wire's three channels is bounded — **blocks the build**

- **Spec lines.** L29–32, L49–54, L92 ("of 10,000 images returns at most 8 inline blocks and 4 MiB").
- **Problem.** A tool result has three channels: the text block, the typed blocks (images, audio, links), and `structuredContent`. The text block has the 32,768-character render cap (spec 167). Inline media has ADR 085 pin 7's budget. Nothing else does. ADR 085 pin 7 says "links for the rest", so 10,000 images give 9,992 `ResourceLink` blocks. `structuredContent` is the whole `to_payload()`.
- **Evidence.**
  - EXECUTED `p1_schema_and_payload.out` §D: a 10,000-row `ls` is **1,790,064 characters** of payload against 169,999 characters of text (which the cap cuts to 32,768). A 10,000-image read with no bytes is **2,080,066 characters** of payload.
  - READ study 08 F8: codex sends the model **only** `structuredContent` when it is present and drops `content`; opencode makes it the primary output. So for two of four clients the unbounded channel is the one the model sees.
  - READ study 08 F8: Claude Code fails any HTTP response over 16 MiB. A `glob "**"` over a million files would be about 180 MB of payload (INFERRED from the 179 characters per row measured above).
  - READ `envelope.py:723-751`: `to_payload(max_errors=…)` already exists and already does the E4 shape (head plus a rollup entry, verdict invariant). The spec sets no value, so a 10,000-error batch ships 10,000 errors.
  - READ July memo §5 E4: "budgets cap the boundary, never the algebra … placeholder with machine-readable count/size/address, verdict invariant, nothing dropped in-process."
- **Amendment (spec text, §2).** "**Every channel is budgeted, and the three agree.** The text block is `render_result` under the cap. `structuredContent` carries exactly the rows the text block showed before the cap, and `to_payload(max_errors=PAYLOAD_ERROR_BUDGET)` with `PAYLOAD_ERROR_BUDGET = 100`. Rows past the shown set are elided from the payload and named by one warning `vfs.budget_exhausted.truncated` with `data["vfs.elided"] = {"rows": N, "first": <path>}` and the same paging hint as the text marker. Typed blocks follow pin 7. Resource links are minted only for rows in the shown set and at most `LINK_BUDGET = 64` per result; a row past it keeps its placeholder in the text and its row in the payload. Elision never changes `success`; in-process nothing is dropped. Each budget is a declared constant in `mcp/adapter.py`; a host may tighten, never loosen. These caps come from client and transport limits (codex's substitution, Claude Code's 16 MiB transport cap), not from vfs; the docstring says so." Add acceptance: "A 10,000-row `ls` result through the adapter yields a text block of at most 32,768 characters plus the marker, a payload with the same row count as the text, one `truncated` warning, and zero links (counted). A 10,000-image result with `data` populated yields at most 8 typed blocks, at most 4 MiB raw, and at most 64 links (counted)."

### 2. The input schemas have no named source, and the obvious one is wrong — **blocks the build**

- **Spec line.** L38: "each with the verb's parameters as the input schema".
- **Problem.** A builder will reach for the SDK's `func_metadata` over the router's methods. That path breaks and leaks.
- **Evidence.**
  - EXECUTED `p3_input_schemas.out` §B: `func_metadata` **fails** on `copy`, `glob`, `grant`, `mkedge`, `move`, `rmedge`, `write` (annotations live under `TYPE_CHECKING`). On the other 13 it **exposes `authority`** as a wire parameter, with `Authority`, `Principal` and `Narrowing` in `$defs`. Spec 149 rule 3: "No served tool exposes an `authority` parameter."
  - READ `params.py:1-11`: the per-op parameter table already names "the wire dialect's schema projection" as its third consumer. Its kinds (`params.py:32-47`) are exactly the mapping a builder needs. The router's param gate already accepts JSON lists for `str_seq` and `str_set` (`params.py:39-40`), so no list-to-tuple shim is needed.
  - EXECUTED `p3_input_schemas.out` §A, the awkward parameters over the 20 agent-facing verbs:

    | Kind | Where | Wire treatment |
    |---|---|---|
    | `authority` (20 verbs) | every verb | never on the wire; filled per request (finding 4) |
    | `observations` (10) | read, stat, ls, delete, restore, edit, glob, grep, glean, graph | dropped; row-addressed chaining is the `cli` pipe's job (`glob … \| grep` passes rows in process, spec 167 criterion 2) |
    | `columns` (8, `str_set`) | read, stat, ls, tree, glob, grep, glean, graph | array, `uniqueItems`, items an enum of `OBSERVATION_FIELDS` |
    | `entries` (`write`) | `Entry` has `owner_id`, `external_id`, `content_hash`, `created_at`, `render_status` (READ `entry.py:81-109`) | items restricted to `{path, content}` or `{path, data}`; nothing else |
    | `data` (`bytes`, `write`) | | standard base64 string, decoded by the handler; a decode failure is `invalid` (isError) |
    | `pairs` (move, copy) | `Sequence[TwoPathOperation \| tuple]` | array of `{src, dest}` objects |
    | `edges` (mkedge, rmedge) | `Edge` | items `{source, target, edge_type, weight?}` |
    | `edits` (`edit`) | `EditOperation{old, new, replace_all}` (READ `replace.py:32-41`) | items of that shape |
    | `provenance` (`mkedge`) | default `"system"` (READ `params.py:214-221`) | not on the wire; the handler stamps it from the actor's kind |

- **Amendment (spec text, §1).** "Input schemas are projected from `vfs.params.PARAMS`, never from Python signatures, by one function `input_schema(op) -> dict` in `mcp/schemas.py` with one branch per `ParamKind` as the table in this spec gives. `authority` and `observations` are never projected; `mkedge`'s `provenance` is stamped `agent` for a `service` actor and `user` otherwise. `RULES` and `VALUE_RULES` are not encoded in JSON Schema; the router's param gate refuses them as `invalid`, which reaches the client as `isError: true` (MCP 2025-11-25 SEP-1303: input validation is a tool execution error). A drift test pins that every `PARAMS` row of an agent-facing op is projected or listed as withheld." Add acceptance: "No tool's input schema names `authority`, `observations` or `provenance` (counted over `tools/list`)."

### 3. The `cli` tool's error verdict is defined twice, and the two disagree — **blocks the build**

- **Spec lines.** L52 (`isError = not result.success`), L40–44 (the `cli` tool), criterion 4.
- **Problem.** ADR 085 pin 9 says `isError = not result.success`. Study 03's exit-code table says the MCP result for a command is `isError = ($? != 0)`. Spec 167 never says whether a stage's classified error (a `cat` of a missing file) lands in the `Result`'s `errors`, or only in the stage's stderr text. So a builder cannot write the `isError` test for `cli`.
- **Evidence.**
  - READ study 03 lines 709-732: "The MCP tool result for a command is: `isError = ($? != 0)`".
  - READ ADR 085 pin 9; July memo §5 A1: "verdict derived; no evidence/emission divergence".
  - READ spec 167 §4: "errors to the stage's stderr, never into the pipe"; criterion 2: `ls /nope | wc -l` exits 0 with `statuses == [1, 0]`. Silent on `Result.errors`.
  - READ study 09 F3: bash-tool returns `{stdout, stderr, exitCode}` and never fails the tool call on a non-zero exit; bashkit's `error` field means "failed before running".
  - INFERRED: if `isError = ($? != 0)` while no fatal error sits on the `Result`, then `isError` and `structuredContent.success` disagree on the same call. That is the lying verdict A1 forbids. And `grep x f` with no match (exit 1) would show as a tool failure in every client.
- **Amendment (spec text, §2, proposed; Clay's question 1).** "For `cli`, `isError = not result.success` as for every verb. A line refused before running (`vfs.unsupported.construct`, `vfs.invalid.syntax`, a parser or argv budget, the system actor) is a fatal error on the `Result`. A stage's classified errors ride the `Result` at warning severity, as `merge_branches` demotes fan-out, so they are visible in the payload and the text but do not fail the call. A non-zero `$?` is evidence in the `exit_code` and `statuses` extras and never sets `isError`. Spec 167 §4 is amended to match." Add acceptance: "`cli('grep nomatch /f')` is `isError: false` with `exit_code == 1`; `cli('for x in a; do :; done')` is `isError: true`; in both, `isError == not structuredContent.success` (asserted for every `cli` test)."

### 4. How each call gets its `Authority` is undefined, and nothing stops the system actor — **blocks the build**

- **Spec lines.** L32–33 ("runs under the `Authority` spec 149 derives from the session"), L17–18.
- **Problem.** The 2026-07-28 revision has no sessions. Spec 149 rule 3 binds "MCP's own session id" to the verified triple, but `Mcp-Session-Id` no longer exists. The authority must be derived **per request**. stdio carries no token at all. And the router's fallback can silently make a wire call run as the system actor.
- **Evidence.**
  - READ stateless memo §1 ("No handshake, no sessions … `Mcp-Session-Id` header [is] gone") and §8.4 ("principal-scoped sessions must not lean on `Mcp-Session-Id`").
  - READ SDK `auth_context.py:13-20`: `get_access_token()` reads a per-request contextvar set by the bearer middleware. That is the per-request door on HTTP.
  - READ `base.py:3065-3078`: `_admitted(None)` returns `default_authority` when one is configured, "the ETL shape, `Authority.system()`".
  - READ `authority.py:216-227`: `owner_for` honours a payload's declared `owner_id` only under the system actor. So a server whose handler ever passes `authority=None` to a system-defaulted router lets a wire `write` stamp any owner it likes.
  - READ ADR 084 pin 3: `cli` refuses the system actor. Nothing says the verb tools do.
- **Amendment (spec text, new §0 "Identity").** "Every handler derives an `Authority` per request and passes it explicitly; a handler never calls the router with `authority=None`. On streamable HTTP the authority is `authority_from_token(get_access_token())` (spec 149); an invalid token is HTTP 401. On stdio the host passes `serve(fs, authority=…)` once; that authority serves every request on the pipe. `serve()` refuses to start when the stdio authority, or the router's `default_authority`, is the system actor. There is no MCP session; the stdio pipe's lifetime is not a session either." Spec 149 rule 3 is amended to drop the session-id binding. Add acceptance: "A spy on the router sees zero calls with `authority=None` across the whole MCP test module; `serve(fs, authority=Authority.system())` raises before binding a transport."

### 5. The `cli` session's state has no carrier on a stateless wire — **should fix (product choice)**

- **Spec lines.** L40–44 (`workdir`); spec 167 §6 ("One session per conversation"; `cwd`, `env`, `exported`, `history`).
- **Problem.** Spec 167 gives the shell a working directory and an environment that persist across calls. Over 2026-07-28 there is no conversation identity on the wire. A builder must choose where `cd /proj` lives between two `cli` calls.
- **Evidence.** READ the stateless memo §1: "Cross-call state is application data … opaque handles returned in tool results and passed back as ordinary tool arguments", and §8.4: "without auth, any vfs-minted handle is a bearer capability". READ study 09 F3: just-bash resets env and cwd on every `exec`; just-bash-py and bashkit's Python binding keep them.
- **Options.** (a) Each call is a fresh shell at `workdir` (default `/`); `cd` and `export` last for the rest of the line. (b) A server-minted handle in `structuredContent`, sealed to the principal, passed back as an argument. (c) A process-lifetime session on stdio only, (a) on HTTP.
- **Amendment (lean (a)).** "Over MCP each `cli` call runs in a fresh shell session at `workdir` (default `/`) with an empty environment; `cd`, `export` and `history` last for the rest of the line. The description says so. A handle-based session is a later spec." Add acceptance: "`cli('cd /a')` then `cli('pwd')` prints `/`."

### 6. Criterion 6 cannot pass as written, and the SDK passes blocks older revisions do not have — **should fix**

- **Spec lines.** L71–76, criterion 6 (L99–100).
- **Problem.** "Validates against all three schema revisions in the three session modes" cannot hold. A legacy session's result has no `resultType`, so it is invalid against 2026-07-28 by design. Separately, a legacy client may negotiate 2024-11-05 or 2025-03-26, and the SDK does not strip blocks those revisions lack.
- **Evidence.**
  - EXECUTED (study 08) `s8/mcp_blocks_experiment.out:328`: legacy result "INVALID 2026-07-28 … 'resultType' is a required property".
  - EXECUTED `p2_sdk_version_sieve.out`: the SDK's per-revision sieve keeps `audio` and `resource_link` on 2024-11-05 and 2025-03-26. Validated against those revisions' own published schemas, the result is **INVALID**: audio and `resource_link` are not in 2024-11-05's vocabulary; `resource_link` is not in 2025-03-26's.
  - READ `mcp_types/version.py:24-37`: the handshake reaches four revisions back to 2024-11-05.
  - READ: the study validated against the local `modelcontextprotocol` clone's `schema.json`. CI has no clone, and the tree has no schema fixtures.
- **Amendment (spec text, §2 and §4).** "`to_call_tool_result(result, *, revision)` takes the negotiated revision (`ctx.protocol_version`). Below 2025-06-18 it emits no `resource_link` and no `structuredContent`; below 2025-03-26 no `audio`. A dropped block's row keeps its placeholder in the text. The wire test drives the three client modes and validates each result against the schema of the revision its session negotiated and against every older revision down to 2025-06-18. A fourth case pins a 2025-03-26 handshake: text and image only." The schema fixtures need Clay's call (question 4).

### 7. `resources/read` as written returns nothing for a text file, no mime for a blob, and has no size bound — **should fix**

- **Spec lines.** L63–68, criterion 5. ADR 085 pin 11 carries the same text.
- **Problem.** `read(path, columns={"data"})` does not fetch what a resource read needs.
- **Evidence.** EXECUTED `p1b_columns_and_base64.out`:
  - Text file, `columns={"data"}`: success, `content=None`, `data=None`. A `TextResourceContents` would have nothing to carry. The spec says a server "MUST NOT return an empty `contents` array" for a missing resource (READ study 08 F4); returning an empty text for a real one is worse.
  - Bytes file, `columns={"data"}`: `mime_type` is not populated. `BlobResourceContents` would carry no `mimeType`.
  - No bound: a link is minted precisely for media over 1 MiB, and reading that link returns the whole object as base64. Claude Code fails any HTTP response over 16 MiB (READ study 08 F8).
  - The URI codec is unstated. `vfs:///{+path}` is RFC 6570 reserved expansion; a path with a space, `#`, `?` or `%` must round-trip (INFERRED).
- **Amendment (spec text, §3).** "`resources/read` runs `read(path, columns={"content", "data", "mime_type", "kind", "version", "size_bytes"})`. A row with `data` returns one `BlobResourceContents{uri, mimeType, blob}`; a row with `content` returns one `TextResourceContents{uri, mimeType?, text}`; a directory is `-32602` with `data.reason = "directory"`. A row whose `size_bytes` exceeds `RESOURCE_READ_BYTE_BUDGET` (12 MiB raw, so base64 stays under the 16 MiB transport cap) is `-32603` with the size and the cap in `data`, and the docstring names the future direction (ranged reads). One pair `vfs_uri(path)` / `path_from_vfs_uri(uri)` mints and parses every URI, percent-encoding per RFC 3986." Add acceptance: "A `vfs:///` URI round-trips for paths holding a space, `#`, `?`, `%` and a non-ASCII letter; a text file reads back its exact text."

### 8. The row-to-block table covers file rows only — **should fix**

- **Spec lines.** L49–54 (delegates to ADR 085 pins 4–10).
- **Problem.** ADR 085 pin 6 places text rows, unfetched bytes rows, images, audio and "everything else". A builder meets more shapes than that. Study 08's table names directories, edges, versions and errors but ADR 085 dropped them.
- **Evidence.** EXECUTED `p1_schema_and_payload.out` §B: grants answers ride as extras (`grants=`), not rows; `read(columns={"data"})` rows carry no `mime_type`; a merged result can stamp `version` null (READ `envelope.py:489-490`). READ ADR 083 pin 6 and spec 169 L58: program output is a row at `/.vfs/run/<call-id>/stdout`, which only spec 169 serves.
- **Amendment (spec text, §2, a table the adapter's tests walk row by row).**

  | Row or result shape | Text block | Typed block | Payload |
  |---|---|---|---|
  | file, `content` set | rendered | none | row |
  | file, bytes, `data` not populated | placeholder | none | row |
  | file, bytes, `data` populated, accepted image within budget | placeholder | `ImageContent` | row without bytes |
  | same, `audio/*` within budget | placeholder | `AudioContent` | row without bytes |
  | same, anything else or over budget | placeholder | `ResourceLink` (finding 1's cap) | row without bytes |
  | same, but `mime_type` not populated | placeholder with `?` mime | none; never a guess | row |
  | SVG or `text/*` stored as bytes, `data` populated | its rendering | none | row without bytes |
  | directory, edge, graph node, trash or version row | rendered | none | row |
  | program output at `/.vfs/run/…/stdout`, text | verbatim | none | row |
  | program output, bytes | placeholder | none; no link until spec 169 serves `/.vfs/run` | row without bytes |
  | `grants=` / `members=` extras | the grants table | none | extras |
  | `cli` extras (`exit_code`, `statuses`, `stderr`, `set_e_tripped`) | stderr after rows, then the status | none | extras |
  | fatal error | errors first (finding 11) | none | errors |
  | warning or info | after rows, never cut by the cap (finding 11) | none | errors |

  And: "`_meta["dev.vfs/version"]` is omitted when `version` is not populated or is null. Inline budget is first-fit in row order: a row that does not fit becomes a link, and later rows may still inline. The tool handler, not the adapter, adds `{path, kind, mime_type, size_bytes, version}` to any requested projection that includes `data`, so the adapter never meets a bytes row without its mime."

### 9. The output schema conforms but declares almost nothing, and costs about 14,000 characters per tool — **should fix**

- **Spec lines.** L39, L53–54.
- **Evidence.** EXECUTED `p1_schema_and_payload.out` §A and §B:
  - `Result.model_json_schema()` works today in both modes. It is a valid 2020-12 schema (it passes `Draft202012Validator.check_schema`). Every live payload validates against it, raw and with bytes stripped: read, ls, stat, glob, graph, grants, an error, a write.
  - But it validates because it constrains little. The root has `additionalProperties: true` and no `required`. `success`, the field every client checks, is **not declared** (it is a property, not a field). The `grants=` and `members=` extras and `cli`'s `exit_code`, `statuses`, `stderr`, `set_e_tripped` are not declared.
  - It is 14,105 characters. Twenty-one tools carrying it put about 296,000 characters into `tools/list` (INFERRED: 14,105 × 21).
- **Amendment (spec text, §1).** "`outputSchema` is the schema of a declared wire model `ResultPayload` in `mcp/schemas.py`: `success` (boolean, required), `ops`, `observations` and `errors` (required), and the known extras as optional typed properties; `additionalProperties: true` keeps newer peers' fields legal. A drift test pins that `ResultPayload` validates every `to_payload()` the adapter emits and that its row properties equal `Observation`'s fields. The schema size is measured in the test and reported in the landing notes."

### 10. The row serializer's base64 is URL-safe; MCP blocks need standard base64 — **should fix**

- **Evidence.** EXECUTED `p1b_columns_and_base64.out`: `Observation`'s JSON for bytes `fa fb fc fd fe ff` is `-vv8_f7_…`, the URL-safe alphabet. Standard base64 is `+vv8/f7/…`. A strict standard decode of the serializer's output fails ("Only base64 data is allowed"). The emitted schema says `format: base64url`. READ study 08 F2: `ImageContent.data` and `BlobResourceContents.blob` are `@format byte` (standard).
- **Why it matters.** After task zero the payload carries no bytes, so the payload is safe. But a builder who builds `ImageContent.data` from the row's JSON, or decodes an inbound block with `Observation.model_validate_json`, corrupts any image whose base64 holds `+` or `/`.
- **Amendment (spec text, §2).** "Typed blocks and resource contents encode with `base64.b64encode` from the row's `bytes`, never from the row's JSON. The inverse decodes with `base64.b64decode(validate=True)` and classifies a failure as a quarantined block." Add a test with bytes whose base64 needs `+` and `/`.

### 11. Errors-first has no owner, and the render cap can cut warnings — **should fix**

- **Spec lines.** L52–53 ("errors first on error"), criterion 4.
- **Evidence.**
  - READ `render.py:62-71`: today the body renders first and errors are appended after it. Only `write` and the no-rows failure lead with errors.
  - READ spec 167 §1 item 2: the cap is "applied last in `render_result`". On a large success with warnings (a truncated `glob`, a `vfs.unavailable` row), the warnings come after the body and are cut first. ADR 085 pin 5 says the text block must be sufficient alone.
  - READ spec 167 §1: the marker reads "page with head, tail or sed -n". On a verb tool (`read`, `ls`) the agent cannot pipe. `read` and `ls` have no paging parameters.
  - EXECUTED `p1_schema_and_payload.out` §B: the default `read` of an unrendered PNG warns "run reindex", which is a developer-plane action no agent tool offers (a spec 152 matter, noted here because it is what the agent reads on this wire).
- **Amendment (spec text, §2; and spec 167 task zero item 2).** "`render_result` leads with the errors section when `not result.success`. The cap never cuts the errors section: the body is cut to fit, and the errors and the marker are always printed. On a verb tool the marker's paging hint names the verb's own bound (`max_count`, `limit`) or the `cli` form (`cli: sed -n 'A,Bp' <path>`)." Add acceptance: "A failed batch with 5,000 rows renders its first fatal error within the first 200 characters; a capped success keeps every warning line."

### 12. The inverse adapter is undefined where spec 170 depends on it — **should fix**

- **Spec lines.** L55–57.
- **Problem.** `from_call_tool_result` is one line. Spec 170 §2 already assumes it maps images and audio to "media rows with bytes and mime", links to rows "carrying the link as `source`", `structuredContent` "to the row's payload", and `isError` to a classified kind. Several of those have no slot.
- **Evidence.** READ `entry.py:420`: `Observation` is frozen and not open (`extra` is default), so a row cannot carry "a payload" or a raw unknown block. READ `envelope.py:779-786`: `from_payload` already reconciles a peer's failure claim. READ spec 170 L60-64: the `isError` mapping is an open `[NEEDS CLARIFICATION]`. INFERRED: when both ends are vfs, the payload has no bytes (task zero), so the only way bytes cross is the typed blocks; the inverse must put them back on their rows.
- **Amendment (spec text, §2).** "`from_call_tool_result(result, *, at: Path) -> Result`. If `structuredContent` is a vfs payload (it has `ops`, `observations`, `errors`), the result is `Result.from_payload(structured | {"success": not isError})` and each typed block whose `_meta["dev.vfs/path"]` names a row puts its bytes back on that row (`data`, `populated` plus `data`). Otherwise blocks become rows under `at`: text joins into one `content` row at `at/stdout`; each image or audio block is a bytes row at `at/<n>.<ext>`; a link is a row at its own path with `source` the URI and no bytes; non-vfs `structuredContent` is one `application/json` row at `at/structured.json`. An unknown block type is kept raw in a `Result` extra `vfs.blocks` and rendered as a placeholder. `isError` with no classifiable error becomes the fatal `vfs.internal` claim `from_payload` already synthesizes." That also closes spec 170's open marker, or 170 cites this.

### 13. `serve()` itself is undefined — **should fix**

- **Spec lines.** L10–12, L27–28.
- **Problem and evidence**, one item each:
  - **The signature.** "`await serve(fs, …)`" leaves the arguments to the builder. READ: transport, host and port, the stdio authority (finding 4), a token verifier (spec 149), `allow_open` (spec 149 L78–83), the tool filter, and the budgets all need a parameter.
  - **The `mcp` dependency.** READ `pyproject.toml:34-42`: `mcp` is not a dependency or an extra. The `vfs.mcp` package imports it at module top (CLAUDE.md's import rule), so it needs an extra `vfs-py[mcp]` pinning `mcp>=2.3,<3`, and the dev group needs `mcp` and `jsonschema` for 100% coverage.
  - **`vfs serve`.** READ `pyproject.toml`: there is no `[project.scripts]`. A console command needs a way to build the router (a database URL, mounts). Nothing in the spec says how.
  - **"Hosts may expose only `cli` by listing."** No mechanism is named. READ `base.py:774-786`: `capabilities()` is the self-declared op set, and unknown dialects withhold `glean` and `graph` (CLAUDE.md). The list should be derived from it.
  - **`tools/list` cache hints.** EXECUTED `p2_sdk_version_sieve.out`: on 2026-07-28 the SDK **rejects** a `tools/list` result with no `ttlMs` and `cacheScope`. READ SDK `caching.py:1-40`: `Server(cache_hints=…)` fills them. The spec names cache hints only for `resources/list`.
  - **ADR 022's rule.** READ `open-questions.md:65-71` and spec 054's archive note: "the serve spec, when written, carries the one-line rule". Spec 171 does not.
  - **`timeout_ms`.** READ ADR 084 pin 5 (`WALL_TIME_BUDGET` 10 s) and pin 6 ("a mount may tighten, never loosen"). Spec 167's `cli` takes no timeout. Undefined whether a caller can raise it.
  - **Tool descriptions and annotations.** Where each verb's description comes from is unstated. MCP tool annotations (`readOnlyHint`, `destructiveHint`) are what hosts' permission layers read, and `ops.py` already classifies every verb.
- **Amendment (spec text, new §0 "The entry point").** "`serve(fs, *, transport: Literal["stdio", "http"], authority: Authority | None = None, token_verifier: TokenVerifier | None = None, host: str = "127.0.0.1", port: int = 8000, tools: Collection[str] | None = None, allow_open: bool = False) -> None`. The served tool set is `(fs.capabilities() & AGENT_OPS) | {"cli"}`, intersected with `tools` when given. `tools/list`, `resources/list` and `resources/templates/list` carry `CacheHint(ttl_ms=0, scope="private")`. A served node exposes no topology mutation, and any opt-in is loud and needs both the server and the node to agree (ADR 022). `serve()` refuses to start while a bound mount is `open` unless `allow_open=True` (spec 149). `cli`'s `timeout_ms` is `min(timeout_ms, WALL_TIME_BUDGET)`; it can shorten, never lengthen. Each verb tool's description is the first paragraph of a `TOOL_DESCRIPTIONS` table in `mcp/schemas.py` (one sentence per verb, drift-tested against `AGENT_OPS`); `readOnlyHint` is `op in READ_OPS`, `destructiveHint` is `op in {"delete", "move", "write", "edit", "revoke"}`. The package installs as the `mcp` extra. `vfs serve` waits for a later spec." (Question 7 asks whether `vfs serve` is in v1.)

### 14. Re-issue and cancellation semantics are unstated — **should fix**

- **Evidence.** READ open question "MCP 2026-07-28: long-batch execution model" (`open-questions.md:187-193`): "a broken response stream *is* cancellation, the client re-issues the request fresh, and the protocol ships no idempotency mechanism"; it lists the serve spec as blocked on this. Spec 171's scope excludes tasks, which is fine, but says nothing about what a dropped stream does to a 10,000-file `write` in flight.
- **Amendment (spec text, §2).** "Served calls are synchronous; served tools return `complete` only (spec 149 rule 5). A broken response stream does not cancel a mutation in flight: the handler shields the router call, so a batch commits or fails as it would in process. A re-issued call meets the verbs' own replay behaviour, documented per verb in the tool description and pinned by a replay test per verb." EXECUTED `p4_replay.out` shows today's behaviour: a `write` of identical content reports `updated` (not `unchanged`), a second `mkedge` reports `updated`, and second `move` and `delete` calls are `not_found` failures. So a re-issued `move` looks like a failure to the agent even though the first call succeeded; the description must say so, or the replay test will pin a surprise. Close the open question when this lands.

### 15. Acceptance criteria that count nothing or cannot be reached — **should fix**

- Criterion 1: list the exact set. "`tools/list` names exactly the 20 agent-facing verbs present in `capabilities()` plus `cli` (21 on the default router; 18 plus `cli` on an unknown dialect, which withholds `glean` and `graph`)." EXECUTED `p3_input_schemas.out`: the 20 are copy, delete, edit, glean, glob, grant, grants, graph, grep, ls, mkdir, mkedge, move, read, restore, revoke, rmedge, stat, tree, write.
- Criterion 2: a default `read` fetches no bytes (READ `p1` §B: `read png default` has no `data`), so "a read of a PNG returns … one `ImageContent`" fails unless the call projects `data`. Write "`read(path, columns=["data"])`". "A read of 10,000 images" is not reachable through the wire tools: `read` takes one path and `observations` is not on the wire (finding 2). Make it an adapter unit test over an in-process `Result`.
- Criterion 4: name the code. "An unknown tool is JSON-RPC `-32602`."
- Criterion 6: see finding 6.
- Missing: the `authority=None` spy and the system refusal (finding 4); the `cli` verdict (finding 3); the channel budgets (finding 1); the base64 alphabet (finding 10); the URI round trip (finding 7); `isError == not structuredContent.success` asserted in every wire test (A1).

### 16. Nits

- L42: "drafted from the peers' … in the study's appendix". No appendix exists in study 08, study 09 or the memo (READ, grep). The draft is in the appendix of this review.
- Study 09 fork 1 says `cli` is "the 26th tool". It is the 21st.
- L41: `workdir` here, `cwd` on `VirtualFileSystem.cli` in spec 167 §6. Pick one wire name.
- L50: `_meta` "`dev.vfs/path`": the second label is `vfs`, which is not reserved (study 08 F2). Fine. State that the keys are a public contract (ADR 085 consequence).
- Spec 149's rule 6 says an absent token is `unauthenticated` (401), and its posture note says a `shared` mount serves callers with no token as anonymous. Those conflict (question 8).
- July memo §5 D2: "the adapter is final-boundary-only; projected payloads are never stored or re-forwarded". Say it in §2; the inverse (finding 12) is the one sanctioned way back in.

## What the spec gets right

- **One adapter, pure, beside the renderer.** It never fetches (July memo A1, G1–G3). EXECUTED `p1` §B shows `data` is populated only when the caller projects it, so purity is structurally true already.
- **`isError = not result.success` for the verbs.** `success` is a derived property (READ `envelope.py:379-382`) and a model validator drops any stored claim (`envelope.py:361-373`). The verdict cannot lie. A1 holds.
- **`structuredContent = to_payload()` without bytes and without `data` in the mask.** EXECUTED `p1` §C: the honest strip round-trips to a row whose `populated` lacks `data` and whose `data` is `None`, with no error. Dropping the bytes but keeping the mask produces a row that claims "fetched, and null"; the spec's wording is exactly what avoids that.
- **A schema can be emitted today.** EXECUTED `p1` §A: `Result.model_json_schema()` is valid 2020-12 and every live payload conforms. Finding 9 asks for a tighter one, not a different mechanism.
- **The verbs plus one `cli` tool, developer verbs never registered.** It answers the open question with the peers' evidence, and keeps `read`'s ladder as the only read door.
- **A minimal `resources` capability** so links are honest, and `vfs:///` not `file://`.
- **`resultType` left to the SDK.** READ `runner.py:386-393`: the runner stamps it on modern sessions and omits it on legacy ones, which is what each revision's schema wants.

## Questions only Clay can answer

1. **Is a non-zero exit an MCP error?** (Finding 3.) Proposed: no. `isError` is true only when the line is refused before running or a fatal error lands on the `Result`. `grep` with no match is `isError: false`, `exit_code: 1`.
2. **Where does the shell's `cd` live between two calls?** (Finding 5.) Proposed: nowhere. Each call is a fresh shell at `workdir`. A sealed session handle is a later spec.
3. **How big may `structuredContent` be?** (Finding 1.) Proposed: the same rows the text block showed, plus one elision fact. Alternative: a fixed row or byte constant.
4. **May the tests vendor the MCP `schema.json` files** for 2025-06-18, 2025-11-25 and 2026-07-28 as fixtures (spec artifacts, MIT moving to Apache-2.0, about 460 KB)? CLAUDE.md forbids copying code from reference repos. Without them, the wire test can only use the SDK's sieve, which EXECUTED `p2` shows is too lenient to catch a wrong block on an old revision.
5. **The oldest client revision.** Degrade blocks for 2024-11-05 and 2025-03-26 clients (proposed), or refuse them?
6. **Images through `cli`.** By ADR 083 pin 7 the terminal of a `cli` line keeps elide-by-default, so `cat photo.png` never shows the image. A host that exposes only `cli` can then never show a model an image. Should a `cli` line whose last stage is `cat` or `read` of an accepted image project `data` within budget?
7. **`vfs serve` in this spec, or `serve()` only?** Proposed: `serve()` only; the console command needs a router-construction story first.
8. **A request with no token over HTTP.** Anonymous (serving `shared` mounts, spec 149's posture note) or 401 (spec 149 rule 6)? Proposed: anonymous when any mount is `shared`, else 401; an invalid token is always 401.

## Appendix: the `cli` tool description, drafted

Assumes the proposed answers to questions 1, 2 and 6 (no to 6). Plain text, about 2,300 characters. The shared vocabulary (what vfs is) can move into the server's `instructions` field if hosts show it.

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
line instead of bytes: [binary <path> <mime> <size>B v<version>]. To see an
image, call the read tool with columns ["data"].

Output. You get stdout, then stderr lines, then the exit status of each stage.
Output over 32,768 characters is cut with a marker saying how much was
removed. Page with head, tail, sed -n 'A,Bp', grep -m N, or a narrower path.
A line has 10 seconds (exit 124 when it runs out).

State. Each call starts in workdir (default /) with an empty environment. cd
and export last only for the rest of the line. Use absolute paths across
calls.

Exit status. 0 success. 1 a command failed (not found, already exists,
conflict). 2 bad usage. 124 timeout. 126 found but you may not run it. 127
not found. A non-zero status is not a tool error; the tool reports an error
only when the line was refused before anything ran.

Input. command: the line to run. Or argv: a list of words, run without
parsing (no globs, no expansion). workdir: where the line starts. timeout_ms:
a shorter limit; it cannot raise the 10-second limit.
```

## Executed scripts

All under `experiments/r171/`, run from the repo root with `uv` (Python 3.13, pydantic 2.12.5, `mcp` 2.3.0, `mcp-types` 2.3.0).

- `p1_schema_and_payload.py` → `.out` (`uv run --with jsonschema python …`): schema emission from `Result` in both modes; every live payload shape validated raw and stripped; the honest and dishonest strips through `from_payload`; payload and text sizes at 10,000 rows. One mislabel: the case "alice read hidden" ran after alice was granted `read` on `/photos` by the case before it, so it is not a hidden read; it is not cited above.
- `p1b_columns_and_base64.py` → `.out`: what `read(columns={"data"})` returns for a text row and a bytes row; the base64 alphabet of the row serializer.
- `p2_sdk_version_sieve.py` → `.out` (`uv run --with mcp --with jsonschema python …`): the SDK's per-revision sieve over every known revision; the sieved result against each revision's published `schema.json`; the `tools/list` cache-hint requirement.
- `p3_input_schemas.py` → `.out` (`uv run --with mcp python …`): the params table's kinds over the 20 agent-facing verbs; the SDK's `func_metadata` over the router's signatures.
- `p4_replay.py` → `.out`: what a second `write`, `mkedge`, `move` and `delete` report.

## One line

The adapter's design is sound, but before building, the spec must bound `structuredContent` and links, project input schemas from `params.py`, settle what `isError` means for `cli`, and say how each request gets its non-system `Authority`.
