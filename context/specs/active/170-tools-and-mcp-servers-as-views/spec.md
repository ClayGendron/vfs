# 170 — Tools and MCP servers as views: host functions and remote servers projected under `/.vfs`, callable by name

- **Status:** draft — cut 2026-10-15 from ADR 082 pins 3, 6, 11,
  13–15; amended the same day from the pre-build review
  (`research/studies/2026-10-15-agent-shell/15-spec-170-review-before-build.md`)
  and Clay's six decisions on it. Lands after spec 169 and with or
  after spec 171 §2. Not started. **Needs one small study before it
  is built**, three pieces, each counted, never timed:
  1. *A supervisor spike.* The one-task-per-server connection owner
     (§3.3) against stdio and streamable HTTP on Python 3.11 and
     3.13: closed through `VirtualFileSystem.close()`'s
     `asyncio.gather` / `wait_for` shape; a call cancelled by the
     wall budget leaves the connection usable; a killed stdio server
     is respawned exactly once on the next call.
  2. *A real-server schema census.* The tools of three or four widely
     used servers (the reference filesystem server, a GitHub server,
     one TypeScript/zod server), each property counted against a row
     of the flag table (§2), and the tools that need `--json`
     counted. It decides whether dotted flags for nested objects
     (`--where.field a`) earn a later pass.
  3. *Legacy servers in the wild.* `mode="auto"` against one
     2025-06-18 stdio server and one streamable-HTTP server that
     issues `Mcp-Session-Id`: discovery, an absent `ttlMs`, session
     expiry.
  No `[NEEDS CLARIFICATION]` remains.
- **Date:** 2026-10-15
- **Owner:** Clay Gendron
- **Kind:** feature (two router-owned catalogues: `ToolView` over
  registered Python callables and `McpView` over connected MCP
  servers, both projected under `/.vfs` and joined to `/.vfs/bin`;
  one router-internal gated door `_invoke`; one grants seam
  `rungs_at`; the optional extra `vfs-py[mcp]`; `SupportsRun` is
  deleted).
- **Depends on:** spec 169 (the views, the union, the index, the bin
  columns `callable_kind` and `resolved`); spec 171 §2 (it hosts the
  inbound function `from_call_tool_result`, whose table this spec
  owns, §4); spec 167 task zero item 4 (amended: `SupportsRun` is
  deleted, not renamed); ADR 082 (pins 3, 6, 11–15, amended as
  below); ADR 084 (pins 1–3, 6); ADR 085; ADR 083 pin 6.
- **Research it stands on:** the memo §5, §10 and §11; study
  `03-program-abi-and-bin-namespace.md` (F3's table, F5, the
  exit-code table); study `05-guest-interpreters.md` (just-bash's
  `invokeTool` hook); study `08-mcp-content-blocks.md`; study
  `09-agent-shell-peers.md` F3 (amla's `tool name.func --arg val`);
  `research/2026-09-04-mcpfs-projecting-mcp-servers-into-a-namespace.md`
  (§1, §4.1, §5: "stat never executes", resources as the honest
  file-shaped half); `research/2026-08-10-mcp-2026-07-28-stateless-revision.md`
  (§2.5, §2.6, §6); the archived spec
  `specs/archive/034-mcp-native-mounts` (its two modes, separated in
  §5); the review's executed probes in
  `research/studies/2026-10-15-agent-shell/experiments/r170/`.

## Intent

After this spec a host registers a Python function once and an agent
sees it as `/.vfs/tools/<name>` and runs it as `<name> --arg value`.
A connected MCP server appears as `/.vfs/mcp/<server>/` with its
tools, resources and prompts as entries. Tools of both kinds are in
`/.vfs/bin` with the same calling convention as any program, and
`type <name>` says where each runs. Who may call a tool is who may
read its entry. Reading an entry never runs anything: `cat` of a
tool shows its manifest, and a tool runs only when it is typed as a
command.

## 1. Tools (`ToolView`)

- **Registration.** `VirtualFileSystem(tools=[…])`, or
  `register_tool(fn, *, name=None, description=None, schema=None,
  stdin=None, mime_type=None, deadline=None, capabilities=())` and its
  inverse `unregister_tool(name)` on the admin plane. A plain
  function with type hints is accepted, sync or async; its schema is
  derived from the signature through pydantic, or given. A LangChain
  `BaseTool` is accepted by shape (`name`, `description`,
  `args_schema`, `ainvoke`), so `vfs` never imports `langchain_core`
  outside its extra.
- **Projection.** `/.vfs/tools/<name>` is a file whose content is the
  manifest: name, description, the input JSON schema, the trust line
  (§6), the capabilities the host declared (such as network). `read`,
  `stat`, `ls`, `tree`, `glob` and `grep` on it **never execute the
  tool**. Its `size_bytes` and `content_hash` are the manifest's; its
  `version` is `None`, so nothing invents a history for it. `cat`
  prints the manifest.
- **Running.** A tool runs only when its name is a command word
  (`name args`) or its path is (`/.vfs/tools/name args`). It is called
  through the one door of §5. Flags map onto its schema by §2. The
  host also validates the arguments with the function's own pydantic
  model before calling, so a host tool's bad input is always
  `vfs.invalid`, exit 2, before it runs.
- **What a tool holds.** A tool runs in the host process with the
  host's authority. It is the one callable kind that may hold more
  than its caller (the exception to ADR 084 pin 3, which governs
  programs), and the trust line in `type` says so. A tool that
  declares a parameter typed `Fs` receives the caller's `Fs` (ADR 082
  pin 2: the verbs curried with the caller's `Authority`) and nothing
  wider; vfs gives a tool no other vfs handle. What a tool does
  outside vfs is the host's responsibility.
- **Return value to rows.** A `Result` passes through unchanged. A
  `str` is one text row (`text/plain`), never JSON. `bytes` is one
  bytes row with the mime the host declared at registration, else
  `application/octet-stream`. `None` is no row. Anything else is one
  row whose `content` is its JSON (pydantic models through
  `model_dump_json`), `mime_type` `application/json`. A single row is
  at `/.vfs/run/<call-id>/stdout` (ADR 083 pin 6).
- **Failure.** A tool that raises `ToolError(message)` exits 1 with
  the message on stderr. Any other exception exits 1 with
  `<name>: tool failed (<ExceptionType>)` on stderr; the detail is
  logged on the host and never sent to the caller. No `ErrorKind` is
  minted for a tool's own failure, and `vfs.internal` is never used
  for it: that kind means vfs itself broke. (python-sdk's server draws
  the same line between a deliberate `ToolError` and an unexpected
  exception.)
- **Execution.** An async function is awaited. A sync function runs
  in a worker thread; at the deadline the call reports `vfs.timeout`,
  exit 124, and the thread is abandoned, not killed (Python cannot
  kill a thread; the docs say so). `WALL_TIME_BUDGET` applies; a
  per-tool `deadline` may only tighten it (ADR 084 pin 6).

## 2. The calling convention: JSON schema to flags

One rule serves `ToolView` and `McpView`.

- **Flags.** One flag per top-level property of the input schema,
  `--<name> <value>` or `--<name>=<value>`, with a kebab alias
  (`--max-count` for `max_count`) when no other property claims it.
  `--` ends flags.
- **Normalization first.** A local `$ref` into `$defs` or
  `definitions` resolves one level. `anyOf`/`oneOf` with exactly one
  non-null arm, or `type: [T, "null"]`, becomes `T`.
- **The table.**

  | Normalized property | Flag form | Coercion |
  |---|---|---|
  | `string` | `--x value` | verbatim; `--x=` is the empty string |
  | `string` with `contentEncoding: base64` | stdin, or `--x @path` | the bytes, base64-encoded |
  | `integer` | `--x 5` | base-10 integer, else `vfs.invalid` |
  | `number` | `--x 0.5` | finite float, else `vfs.invalid` |
  | `boolean` | `--x`, `--no-x`, `--x=true\|false` | never a separate value word |
  | `enum` or `const` (any arm types) | `--x member` | must equal a member after coercion to that member's type |
  | `array` of a scalar above | repeat the flag: `--tag a --tag b` | each item by `items`; never comma-split |
  | `array` of anything else | repeat the flag | each value parsed as JSON |
  | `object`, a model, `anyOf`/`oneOf` of several non-null arms, or no `type` | `--x '<json>'` | parsed as JSON; if that fails and a `string` arm exists, the text as a string |

- **Positionals** bind to the `required` scalar properties in
  `required` order. A positional past them is `vfs.invalid`.
- **Defaults** are never sent. The server, or the host function,
  applies them.
- **Checked client-side, before any call:** every top-level
  `required` property is present; every value coerces; no unknown
  flag. Each failure is `vfs.invalid`, exit 2, with zero wire calls
  (ADR 082 pin 4). Unknown properties are refused here because a real
  server accepts them silently. Nested rules (`pattern`, bounds,
  nested `required`) are the server's to judge; its answer is the
  tool's exit (§4).
- **stdin.** When the stage has a producer or a `<` redirect, stdin
  binds to the one `required` property no flag or positional set, if
  that property is a `string` (UTF-8 text; anything else is
  `vfs.invalid`), a base64 `string` (the raw bytes), or an
  `object`/`array` (stdin parsed as JSON). Zero or several such
  properties with stdin present is `vfs.invalid`, naming them. A host
  may pin the binding at registration (`stdin="body"`). A tool stage
  consumes bytes (ADR 083 pin 2), so an upstream row stage is
  rendered first.
- **`--json '<object>'`** is the whole arguments object, sent as
  given. It excludes every property flag, positional and stdin
  binding (`vfs.invalid` if mixed). `--json -` reads the object from
  stdin. A property named `help` or `json`, a name that is not a
  valid flag word, and a schema whose top level is not an `object`
  with `properties` (a top-level `oneOf`, say) are reachable only
  through `--json`; `--help` says so.
- **`--help` and the `vfs.invalid` detail** render one line per
  property: name, type, required or default, enum members,
  description.

## 3. MCP servers (`McpView`)

### 3.1 Connection

- `add_mcp(name, server=…, *, list_floor_ms=None, credentials=None)`
  and `remove_mcp(name)` on the admin plane. `server` is what the
  SDK's `Client` takes: a URL (streamable HTTP) or stdio parameters.
- Projection: `/.vfs/mcp/<name>/tools/<tool>`,
  `/.vfs/mcp/<name>/resources/<n>`, `/.vfs/mcp/<name>/prompts/<p>`.
- Credentials are per-server configuration passed to the transport.
  They never touch `os.environ` (one server's secrets must not reach
  another server's subprocess).
- A server's identity is the connection's: every vfs caller who may
  call its tools acts through the one credential the host configured.
  `tools/list` is therefore one list per server, not per caller.

### 3.2 Entries

- **Tools.** Each tool entry's `content` is its manifest from
  `tools/list` (`title`, `description`, `inputSchema`,
  `outputSchema`, icons, annotations), rendered as untrusted text
  (§6). As in §1, reading never executes. The tool runs as a command
  through §5; the call is `tools/call`; the result comes inbound by
  §4.
- **Resources.** A listed resource is a file at `resources/<n>`, `n`
  its index in the listing of the last refresh. The entry's manifest
  line names the URI, the mime and the size the listing gave. `cat`
  (a `read`) issues `resources/read` for the URI recorded at listing
  time; the result comes inbound by §4's table; the server's
  `ttlMs` is honoured. `stat` never fetches: `size_bytes` is the
  listing's `size`, else `None` (unknown, never 0). Resource
  templates are listed with their `uriTemplate`, not readable. Over
  HTTP, a request that reaches a resource with no token is anonymous
  and is judged by the ladder like any other read (this binds spec
  171's `resources/read`).
- **Prompts** are listed with their arguments, never callable.

### 3.3 Lifecycle under 2026-07-28

The SDK owns era negotiation: `add_mcp` connects through
`Client(…, mode="auto")`, which probes `server/discover` and falls
back to the legacy handshake itself. It also owns `ttlMs` and
`cacheScope` caching, re-listing after `HEADER_MISMATCH`, and
`x-mcp-header` mirroring. McpView adds four rules.

1. **One task per connection.** `add_mcp` connects eagerly; a server
   that cannot connect raises at `add_mcp`, not inside an agent's
   command. One supervisor task per server enters and exits the
   client; calls are sent to it and may run concurrently on the one
   client. `remove_mcp` and `close()` signal the supervisor. (The
   SDK refuses to close a client from a task other than the one that
   opened it, and `close()` disposes each binding in its own task.)
2. **Reconnect.** On `-32000` ("Connection closed") or a transport
   error the call classifies `vfs.unavailable.backend` and the
   supervisor reconnects on the next call, with backoff capped by
   `MCP_RECONNECT_BACKOFF_MS`. A failure inside connect arrives
   wrapped in an `ExceptionGroup`; it is unwrapped before it is
   classified.
3. **A refresh floor above `ttlMs: 0`.** The listing is fetched at
   connect and refreshed when stale: fresh for the server's `ttlMs`
   (the cache-freshness field; the tasks extension's `ttlMs` is a
   different thing and shares no constant), but never refetched more
   than once per `cli` call and never more often than
   `MCP_LIST_FLOOR_MS` (default 30 s; `add_mcp(…, list_floor_ms=)`
   sets it per server). Most servers send `ttlMs: 0` and legacy
   servers send none, so without the floor every `ls /.vfs/bin` would
   list every server. The page walk is bounded by
   `MCP_LIST_PAGE_BUDGET`. A tool missing from a refreshed listing is
   127. `listChanged` through `subscriptions/listen` is out of scope;
   the floor covers it.
4. **Never auto-retry a tool call.** A cancelled `tools/call` may
   have run, and 2026-07-28 has no idempotency key. Only discovery is
   retried.

McpView passes no sampling, elicitation or roots callback and
declares no extension; what that refuses is classified in §4.

## 4. The inbound table and the failure map

Spec 170 owns this table; spec 171 §2 hosts the function
(`from_call_tool_result`) and lands first or with this spec.

- **Blocks to rows.** Row *i* is at `/.vfs/run/<call-id>/<i>`, *i*
  the block's index.

  | Block | Row |
  |---|---|
  | `text` | `content` = text, `mime_type` `text/plain` |
  | `image`, `audio` | `data` = decoded bytes, `mime_type` from the block |
  | `resource` with `text` | `content` = text, `mime_type` from the block; the URI in the `Result` extra `links[i]` |
  | `resource` with `blob` | `data` = decoded bytes, as above |
  | `resource_link` | `content` = one line `[link <uri> <mime> <size>B -- <name>]` (ASCII, no `\|`, only the fields present), `mime_type` `text/plain`; the block in `links[i]` |
  | any other `type` | `content` = `[unknown block <type>]`; the raw block in the `Result` extra `raw_blocks[i]` |

- `structuredContent` rides as the `Result` extra `structured` (any
  JSON value), never as a row — except when `content` is empty: then
  one row whose `content` is its JSON, `mime_type`
  `application/json`.
- `annotations` and `_meta` are dropped, except `dev.vfs/path` and
  `dev.vfs/version`, which, from a vfs server, become the row's own
  `path` and `version`.
- Inbound bytes count against `STDOUT_BYTE_BUDGET`. A block that
  would cross it becomes its placeholder line with the
  `budget_exhausted.truncated` warning, never a partial image.
- The inbound block-to-row function is spec 171 §2.6's
  `from_call_tool_result`; this section states its contract.
- **`isError: true` is the tool's own non-zero exit:** stage status
  1, every text block to the stage's stderr, `structured` kept as the
  extra, no rows. No `ErrorKind` is minted for it. (A real server
  returns `isError` alike for bad arguments, an unknown tool and a
  crash, so the flag alone cannot say which.)
- **Failures around the call classify by what happened:**

  | What happened | Kind | Exit |
  |---|---|---|
  | missing required property, uncoercible value, unknown flag (client-side, before any wire call) | `vfs.invalid` | 2 |
  | JSON-RPC `-32602` from the server | `vfs.invalid` | 2 |
  | JSON-RPC `-32601`, or the name absent from the last listing | `vfs.not_found` on the shell's result | 127 |
  | `-32021` (missing client capability), an input-required (elicitation) request, `InputRequiredRoundsExceededError` | `vfs.unsupported` (no ask inside vfs, ADR 084 pin 4) | 126 |
  | `-32000` "Connection closed", or any transport error | `vfs.unavailable.backend` | 1 |
  | the wall budget | `vfs.timeout` | 124 |
  | the SDK rejects `structuredContent` against `outputSchema` | rows from `content` kept; `structured` dropped; one warning | 0 |

## 5. The call door and the two kinds of MCP server

- **One door.** Tools and MCP tools are called through one
  router-internal method, `VirtualFileSystem._invoke(path, arguments,
  *, authority) -> Result`. It is not an `Op`, not agent-facing, and
  not on `Fs`; the shell runner calls it for the `tool` and `mcp`
  kinds after resolution. Its gate order is ADR 084 pin 1's: resolve
  (127 if the caller cannot `list` the entry), then `read` on the
  entry (126), then the call.
- **Router-owned catalogues.** `ToolView` and `McpView` implement one
  protocol, `CallableCatalogue` (`entries()`, `call(name, arguments,
  authority)`). The router owns them; they are not mounted, and
  nothing in storage executes.
- **`SupportsRun` is deleted**, not renamed: it leaves
  `storage/protocol.py`, `_FAMILY_OPS` and the dispatch funnel, with
  `run` (spec 167 task zero item 4, amended).
- **Spec 034's two modes separate.** A server that declares the vfs
  protocol (`experimental["dev.vfs.filesystem"]`) is a routing mount:
  its tools are vfs verbs and it belongs on the mount table (roadmap
  020; out of scope here). Any other server is a catalogue under
  `/.vfs/mcp`, and its tools are callables. Spec 034's `updatedb`
  materialization is not taken: tool entries are facts about one
  process and are synthesized; only their policy is stored (below).

### 5.1 Permissions on catalogue entries

- Tool, MCP and resource entries follow the regular posture rules at
  their paths (ADR 082 pin 11, ADR 084 pin 2). No special default.
- Policy rows for every `/.vfs` catalogue path live in the root
  binding's grants table. `posture` and `grant` at a catalogue path
  are lawful; `write`, `delete`, `move` and `mkdir` there are
  `invalid` (spec 169).
- **Spec work, the `rungs_at` seam.** `SupportsGrants` gains
  `rungs_at(paths, *, authority) -> dict[Path, Rung]`: the caller's
  rung at each path, computed from the posture rows and spans on its
  chain (the same `level_at` and `Rights.reaches` a creation is
  judged by), never a row label. It issues one chunked statement per
  `membership_budget` slice. The catalogues call it once per listing
  or resolution for all their entries. Below `list`: absent from
  `ls` and `/.vfs/bin`, 127. `list`: listed, 126 on a call. `read` or
  above: callable, readable. A root binding without `SupportsGrants`
  answers its mount `permissions` at every catalogue path. This is a
  new statement shape, so it carries the four engine legs.
- **Stated plainly: an open node lets anyone call every host tool.**
  On a fresh node everyone holds `read_write` at `/`, so every
  caller, anonymous included, can call every registered tool and
  every MCP tool, and a host tool runs with the host's authority.
  This is accepted. A host locks it with one line per catalogue:

  ```python
  await fs.posture("/.vfs/tools", "list", authority=Authority.system())
  await fs.posture("/.vfs/mcp", "list", authority=Authority.system())
  ```

  After that everyone sees the names and nobody can call them, until
  a `grant` of `read` on an entry or a directory of entries.
- masking lives in the index's `masked` set (ADR 084 pin 8), so `deny_ops` does not reach tools, which sit on no
  mount. A host masks a tool by not registering it, or by posture.

## 6. Shared

- **`/.vfs/bin`** lists tool and MCP tool entries with
  `callable_kind` `tool` or `mcp` and `resolved` their catalogue path
  (spec 169's columns; `kind` stays the `ObjectKind` `file`, and
  `source` keeps its `text`/`bytes` meaning).
- **Names.** The union order is the index order; the host positions
  the catalogue views in it, after every stored program directory
  unless it places them otherwise. So a remote server cannot take
  over a bare command name that a kernel program or a stored program
  already answers. An MCP tool is always reachable by its path
  (`/.vfs/mcp/<server>/tools/<tool>`), which nothing shadows. When
  two members offer one name, `which -a` lists every one and marks
  the shadowed ones.
- **`type`, `which`, `help`** render the manifest; `--help` on any
  kind renders the forms or the schema (§2).
- **Trust is shown** (ADR 082 pin 14): "runs on the host, with the
  host's authority (network: yes)" or "runs on <server>".
- **Remote text is untrusted.** Every manifest line from a server is
  rendered as data: control characters removed, each description
  capped at `MANIFEST_DESCRIPTION_BUDGET` characters with the
  truncation marker, prefixed by the provenance line `runs on
  <server>`. `stat` shows the manifest's `content_hash`, so a host can
  see a description change between refreshes. vfs never places
  manifest text in a system prompt.
- **Search.** The catalogue views serve `read`, `stat`, `ls`, `tree`,
  `glob` and `grep` over their manifests; `grep` scans the rendered
  manifests in memory. `glean` over the catalogues is a later item.

## 7. The dependency

- `mcp` is an optional extra, `vfs-py[mcp]`, shared with spec 171.
  It pulls starlette, uvicorn, sse-starlette, pyjwt with
  cryptography, opentelemetry-api, httpx2 and jsonschema, and needs
  pydantic 2.12 or newer.
- McpView lives in `vfs/mcp/client.py`, imported only through the
  extra (imports at the top of the module). `add_mcp` without the
  extra raises at the call with the install hint. `ToolView` and the
  flag mapping need no extra.
- The `mcp` package joins the dev dependency group so the suite runs
  an in-process server.

## Scope

In: the two catalogues, the flag mapping, the inbound table and
failure map, the `_invoke` door, the `rungs_at` seam, MCP resources
(listed and readable), the extra. Out: prompts as callables (listed
only); sampling, elicitation, roots, tasks; `subscriptions/listen`
and `listChanged` (the refresh floor covers freshness); `glean` over
catalogues; a tool declaring verb attenuation (`Narrowing`, later);
a vfs-protocol server as a routing mount (roadmap 020); dotted flags
for nested objects (after the census).

## Acceptance criteria

1. A registered function appears at `/.vfs/tools/<name>` and in
   `/.vfs/bin` with `callable_kind=tool`; `<name> --x 1` calls it; a
   `str` return lands as one text row, a `dict` return as one JSON
   row; a missing required parameter is `vfs.invalid`, exit 2, with
   one line per property rendered.
2. A connected MCP server appears under `/.vfs/mcp/<name>/`; one
   call yields a text row, a media row, a `[link …]` row, an embedded
   text row and an unknown-block row at `/.vfs/run/<call-id>/<i>`,
   with `structured` as an extra; an `isError` result is exit 1 with
   its text on stderr and no rows; each row of the §4 failure table
   produces its kind and exit.
3. A caller without `read` on a tool entry gets 126; without `list`,
   the tool is absent from `/.vfs/bin` and the name is 127; the two
   posture lines of §5.1 lock a fresh node exactly so.
4. `type <name>` says where it runs for all three kinds.
5. Each row of the flag table, for ToolView and for an in-process MCP
   server: one passing call and one `vfs.invalid`, exit 2, with zero
   wire calls (spied); an unknown property is refused client-side.
6. `cat f | upload` binds `body`; `cat f | upload --body x` is
   `vfs.invalid`; `--json` with a property flag is `vfs.invalid`;
   `--json -` reads the arguments from stdin.
7. `cat /.vfs/tools/x`, `stat`, `ls -l /.vfs/tools` and `grep -r .
   /.vfs/tools` issue zero tool calls (spied); `cat` of a resource
   issues exactly one `resources/read` and `stat` of it none.
8. `ls /.vfs/bin` twice in one `cli` call issues one `tools/list` per
   server; inside the floor, zero (counted).
9. A stdio server killed mid-session: the call is
   `vfs.unavailable.backend`, exit 1; the next call respawns once
   (counted); a call cancelled by the wall budget is issued exactly
   once.
10. `VirtualFileSystem.close()` closes every McpView with no
    cross-task error, on Python 3.11 and 3.13.
11. `import vfs` and the ToolView suite pass without `mcp` installed;
    `add_mcp` without the extra raises with the install hint.
12. `run` and `SupportsRun` are gone from `ops.py`,
    `storage/protocol.py`, the funnel and the drift test; `_invoke`
    is not an `Op`.
13. A sync tool past its deadline is `vfs.timeout`, exit 124; a tool
    raising a plain exception is exit 1 with the generic stderr line
    and no detail in the `Result`.
14. The 126/127 split of criterion 3 holds on the four engine legs
    (`rungs_at`).
15. `scripts/ci.sh` green at 100%.

## Landing notes

(Filled in on landing.)
