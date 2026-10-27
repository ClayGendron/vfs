# Review of spec 170 — tools and MCP servers as views

Reviewer: pre-build review, 2026-10-15. Tree at `main` (`ac5c515`), working tree as found. Nothing under `src/`, `tests/` or the spec was modified. Reference clones read only: `python-sdk` @ `754254c0` (2026-10-13, MIT) and `mcpfs` @ `640511e` (2026-03-06, MIT), both refreshed today per `refresh.log`.

What I read: spec 170; its parents 169 and 167; ADRs 082 (pins 2, 3, 6, 11–15), 084 (pins 2, 3, 6, 9), 085 (all pins), 083 pin 6, 069 pin 1; archived spec 034 (`spec.md`, `design.md`); spec 171 §1–§3; memos `2026-08-10-mcp-2026-07-28-stateless-revision.md`, `2026-09-04-mcpfs-projecting-mcp-servers-into-a-namespace.md`, `2026-10-15-the-agent-shell-prior-art-and-experiments.md` §5, §10, §11; studies 03 (F5, the exit-code table), 08 (findings 2–9, A–H), 09 (F3); the live tree (`storage/protocol.py`, `base.py` `run` and the dispatch funnel and `close`, `skills.py`, `paths.py`, `models/entry.py`, `results/kinds.py`, `storage/grants.py`); `python-sdk/src/mcp/client/` (`client.py`, `_probe.py`, `caching.py`, `_input_required.py`, `session.py`) and `src/mcp/server/mcpserver/server.py`; `mcpfs/internal/toolfs/classify.go`, `internal/fuse/toolnode.go`, `README.md`.

Evidence labels: **EXECUTED** (a script ran; scripts and outputs in `experiments/r170/`), **READ** (`file:line`), **INFERRED** (my reasoning from the two).

## Verdict in one line

Not ready to build. The direction is sound, but four things are undecided or contradict the tree: a `read` that runs code, a call seam the ADRs forbid, a permission rule with no machinery under it, and an inbound mapping that names fields that do not exist. The study the spec asks for is now mostly done below; what is left is small.

## Readiness score: 40 / 100

| # | Dimension | Weight | Score | Why |
|---|---|---|---|---|
| 1 | Intent and scope | 10 | 7 | The intent is clear. The scope is not: resources are "in" with no path rule; `listChanged` is both out of scope and a `[NEEDS CLARIFICATION]`. |
| 2 | Fit with ADRs and sibling specs | 15 | 6 | Spec 034 is cited as "active" and never reconciled. `SupportsToolCall` collides with ADR 082 pin 2 and with `run` leaving `Op`. The inbound adapter lives in spec 171, which lands independently. |
| 3 | Interfaces and data model | 15 | 5 | "The row's payload" and "the link as `source`" name fields that do not exist on `Observation`. The flag rule is one sentence. Which verbs the views serve is unstated. |
| 4 | Security and permissions | 15 | 5 | A `read` that executes host-authority code; posture at paths that hold no row, with no seam to judge it; host authority unnamed as the one kind that exceeds its caller; remote text unbounded. |
| 5 | Failure classification | 10 | 3 | `isError` is a `[NEEDS CLARIFICATION]`; no map for JSON-RPC errors or SDK raises; `vfs.internal` misused for a host tool's bug. |
| 6 | Lifecycle, concurrency, scale | 10 | 2 | Deferred wholesale to "study". The SDK's task-affinity rule breaks the naive design (executed). |
| 7 | Research grounding | 10 | 6 | Strong studies on blocks and peers; the client side of 2026-07-28 was never studied; the mcpfs memo's two main warnings were not carried in. |
| 8 | Testable acceptance criteria | 15 | 6 | Five criteria; two hang on open markers; nothing tests flags, stdin, `--json`, lifecycle, or call counts. |

## Findings, most severe first

### 1. A `read` that invokes the tool is a side door — **blocking**

- **Spec lines.** 44–51 ("a tool with no required parameters also answers `read` by invoking it"), and ADR 082 pin 13 ("A tool with no required parameters is a file: `cat` invokes it").
- **Problem.** "No required parameters" does not mean "safe to run". `deploy`, `restart`, `purge_cache` and `send_digest` all take no required argument. A `read` that runs them makes `read` a verb with side effects. Every path that issues a `read` then executes code with the host's authority:
  - `cat`, `head`, `wc`, `grep -r … /.vfs/tools`, `cat /.vfs/tools/*` (one glob, N tool runs);
  - a chained batch `read(observations=…)` over a `glob` (ten thousand rows is a supported batch);
  - spec 171's `resources/read` of `vfs:///.vfs/tools/x`, which MCP declares cacheable — a tool call through a cacheable method;
  - a guest program's `path_open` (spec 169 hides `/.vfs` from guests today, but the rule now carries weight it did not before).
- **Evidence.**
  - READ `mcpfs/internal/toolfs/classify.go:43-46`: "required list empty → static file" is the rule the spec copies. READ `internal/fuse/toolnode.go:44-54`: that file's `Getattr` runs the tool, so `ls -l` executes it. The 2026-09-04 memo §1 and §5 call this "the single most consequential design error in the repo" and say vfs should adopt "stat never executes".
  - mcpfs also guards with name verbs first (`classify.go:36-41`). The spec drops even that guard.
  - READ memo 2026-08-10 §6: `tools/call` is not cacheable; `resources/read` is. MCP itself says a tool call is not a file read.
  - READ ADR 069 pin 1: "There is no shell, no side door … the check runs on the storage call." A `read` rung that runs host code is exactly a door the ladder does not see. `deny_ops` cannot mask `read` (READ `protocol.py` docstring; reads must work on read-only mounts), so a host has no lever.
  - INFERRED: if `read` returns a result, `stat` cannot be honest about `size_bytes` or `content_hash` without running the tool. If `read` returns the manifest, `stat` is honest for free.
- **Amendment (spec text, §1 projection).** "`/.vfs/tools/<name>` is a file whose content is the manifest. `read`, `stat`, `ls`, `glob` and `grep` on it never execute the tool; its `size_bytes` and `content_hash` are the manifest's. A tool runs only when its name is a command word (`name args`) or its path is (`/.vfs/tools/name args`). `cat` prints the manifest." And amend ADR 082 pin 13's last sentence to: "A tool with no required parameters runs as `name` with no arguments; `cat` shows its manifest." If Clay wants a file-shaped result later, it is MCP resources (cacheable, sized, declared `ttlMs`), not tools — the memo's "resources are rows by default, tools by opt-in".

### 2. The call seam: `SupportsToolCall` has no route that keeps the gates — **blocking**

- **Spec lines.** 12–15, 90–92 ("`SupportsToolCall` … is the capability an MCP mount declares; the program table's `mcp` kind calls it"); spec 167 §1 item 4.
- **Problem.** Four facts do not fit together.
  1. Spec 167 removes `run` from `Op`. READ `base.py:3032-3035`: the funnel dispatches to storage by `Op` name. READ `protocol.py:508-515`: `capabilities()` declares `Op`s, and `_FAMILY_OPS` maps `SupportsRun` to `"run"`. With no `Op`, a storage cannot declare the capability and the funnel cannot dispatch to it.
  2. ADR 082 pin 2: a program's `Fs` has "no execution verb". So the `mcp` kind's `main(call)` cannot reach a tool through `call.fs`.
  3. Calling `storage.call_tool(...)` directly from the shell skips the funnel: no capability gate, no `deny_ops`, no permission gate, no `_admitted` authority, no `TransportError` → `backend_unavailable` normalization (READ `protocol.py:90-97`). That is a side door.
  4. The spec calls McpView a router-served view (lines 12–13, 69–73) and also "an MCP mount" (line 90). ToolView is called by the router; McpView through a storage capability. Two shapes for one idea.
- **Reconciling with spec 034.** READ `specs/archive/034-mcp-native-mounts/spec.md:20-32`: 034 had two modes. A server that *declares* the vfs protocol (`experimental["dev.vfs.filesystem"]`) is a **routing mount** — its tools are vfs verbs, and it belongs on the mount table (roadmap 020). Any other server is a **catalogue** — its tools are callables. Spec 170 covers only the second and never says so. The clean split: a vfs-protocol server stays a mount (future, roadmap 020); a generic server is a router-owned catalogue under `/.vfs/mcp`. Then nothing in storage executes, and `SupportsRun` can simply be deleted in spec 167 instead of renamed.
- **Amendment (spec text, replaces lines 90–92).** "Tools and MCP tools are called through one router-internal door, `VirtualFileSystem._invoke(path, arguments, *, authority) -> Result`. It is not an `Op`, not agent-facing, and not on `Fs`; the shell runner calls it for the `tool` and `mcp` kinds after resolution. Its gate order is ADR 084 pin 1's: resolve (127 if the caller cannot `list` the entry), then `read` on the entry (126), then the call. ToolView and McpView implement one protocol, `CallableCatalogue` (`entries()`, `call(name, arguments, authority)`), owned by the router, not mounted. `SupportsRun` is deleted, not renamed. A server that declares the vfs protocol is a routing mount (spec 034's routing mode, roadmap 020), out of scope here." This needs ADR 082 pin 12's last two sentences amended.

### 3. "Regular posture rules at their paths" has no machinery for paths that hold no row — **blocking**

- **Spec lines.** 65–67, 121–122; ADR 082 pin 11; ADR 084 pin 2.
- **Problem.** Tool entries are synthesized; no row exists at `/.vfs/tools/search`. Every visibility check in the tree is a predicate over stored rows and their labels. Nothing answers "what rung does this caller hold at a path with no row?" through a public verb.
- **Evidence.**
  - EXECUTED `posture_at_view_paths.out`: posture and grant rows at `/.vfs/tools` and `/.vfs/tools/search` are accepted by the root mount's grants table today (A–D). So the *policy rows* have a home: the root binding.
  - EXECUTED `grants_as_caller_at_view_path.out`: with everyone at `list` on `/.vfs/tools` and alice granted `read`, `grants("/.vfs/tools/search")` answers alice's rows, but bob (who should see the name and get 126) gets `not_found`, and anonymous gets `unauthenticated`. The router cannot derive bob's rung from public verbs.
  - READ `storage/grants.py:169-179` (`level_at`) and `:477-479` (`Rights.reaches`): the machinery to judge a path with no row already exists. It is how a creation is judged. It is just not exposed.
  - EXECUTED, same file: on a fresh node everyone holds `read_write` at `/`. With "no special default", **every caller, anonymous included, can call every host tool**, and a host tool runs with the host's authority (finding 6).
  - Spec 169 §1 says a mutation into any view is `invalid`. It does not say whether `posture` and `grant` count. They must stay lawful there, or the rule cannot be expressed at all.
- **Why not store the entries (spec 034's `updatedb`)?** INFERRED: host functions are facts about one process. Two vfs processes on one Postgres register different tools. Stored tool rows would show process B tools it cannot run. Synthesized entries plus stored *policy* is the right split: entries are per process, policy is shared.
- **Amendment (spec text, new §4 "Permissions on catalogue entries").** "Policy rows for every `/.vfs` catalogue path live in the root binding's grants table. `posture` and `grant` at a catalogue path are lawful; `write`, `delete`, `move` and `mkdir` there are `invalid` (spec 169). `SupportsGrants` gains `rungs_at(paths, *, authority) -> dict[Path, Rung]`: the caller's rung at each path from the posture rows and spans on its chain (`level_at` and `Rights.reaches`), one chunked statement per `membership_budget` slice, never a row label. The catalogue views call it once per listing or resolution for all their entries. Below `list`: absent, 127. `list`: listed, 126 on call. `read` or above: callable. A root binding without `SupportsGrants` answers its mount `permissions` (the `Permission` map) at every catalogue path." Add the four engine legs to the acceptance criteria (this is a new statement shape).

### 4. The inbound adapter names fields that do not exist and skips three block cases — **blocking**

- **Spec lines.** 74–85; ADR 082 pin 15; spec 171 §2 (`from_call_tool_result`).
- **Problems.**
  - "`structuredContent` to the row's payload": READ `models/entry.py:393-452` — `Observation` has no payload field. (Spec 034's design §5 saw the same gap and planned a new slot plus a drift-test change.)
  - "resource links to rows carrying the link as `source`": READ `models/media.py:18` — `source` is `Literal["text", "bytes"]`, the very field ADR 085 pin 2's placeholder keys on. A URI cannot go there. (Spec 169's `/.vfs/bin` uses `source` for "the real path"; same collision, finding 10.)
  - No rule for the embedded `resource` block, for unknown block types ("preserved raw" — preserved where?), or for row paths when one call yields several rows (ADR 083 pin 6 defines one row at `/.vfs/run/<call>/stdout`).
  - The placeholder grammar needs a vfs path and `v<version>` (ADR 085 pin 2). A remote link has neither.
  - Ownership: spec 171 owns `from_call_tool_result` but lands "independent of 168–170". If 170 lands first, the function does not exist.
- **Evidence.** EXECUTED `schema_shapes_probe.out`: a real server returns `text`, `image`, `resource_link`, embedded `resource` and `structuredContent` together; a `str` tool returns text `"w1\nw2"` *and* `structuredContent {"result": "w1\nw2"}` — not a textual duplicate, so "drop the restated JSON" is not a usable rule.
- **Amendment (spec text, replaces lines 76–85 after "Calling is as §1 with the schema").**

  > The inbound table (spec 170 owns it; spec 171 hosts the function and lands first or with it). Row *i* is at `/.vfs/run/<call-id>/<i>`, *i* the block's index.
  >
  > | Block | Row |
  > |---|---|
  > | `text` | `content` = text, `mime_type` `text/plain` |
  > | `image`, `audio` | `data` = decoded bytes, `mime_type` from the block |
  > | `resource` with `text` | `content` = text, `mime_type` from the block, the URI in `Result` extras `links[i]` |
  > | `resource` with `blob` | `data` = decoded bytes, as above |
  > | `resource_link` | `content` = one line `[link <uri> <mime> <size>B -- <name>]` (ASCII, no `|`, the fields present), `mime_type` `text/plain`; the block in `links[i]` |
  > | any other `type` | `content` = `[unknown block <type>]`; the raw block in `Result` extras `raw_blocks[i]` |
  >
  > `structuredContent` rides as the `Result` extra `structured` (any JSON value), never as a row, except when `content` is empty: then one row `content` = its JSON, `mime_type` `application/json`. `annotations` and `_meta` are dropped except `dev.vfs/path` and `dev.vfs/version`, which, from a vfs server, become the row's own `path` and `version`. Inbound bytes count against `STDOUT_BYTE_BUDGET`; a block that would cross it becomes its placeholder line with the warning, never a partial image. `isError` — see finding 5.

### 5. `isError` and the errors around it: map by mechanism, not by guess — **should-fix** (it resolves the `[NEEDS CLARIFICATION]`)

- **Spec lines.** 81–85, 119–120; also line 61 (`vfs.internal`).
- **Problem.** `isError` lumps together very different failures. Neither `invalid` ("fix the parameter", retry never) nor `unavailable` ("retry shortly") fits them all. Line 81 and line 84 also contradict each other.
- **Evidence.** EXECUTED `schema_shapes_probe.out`, against python-sdk's own server: a missing required argument, a wrong type, an **unknown tool**, and an **unexpected exception** all come back as `isError: true` with text. None is a JSON-RPC error. So the client cannot tell "your input was wrong" from "the server crashed" from the flag alone. READ `server.py:436-456`: a deliberate `ToolError` sends its message; any other exception sends only "Error executing tool boom" and logs the detail on the server (EXECUTED: the trace is in `schema_shapes_probe.stderr`, not on the wire).
- **The rule that fits everything.** A tool's `isError` is that program's own non-zero exit. Study 03's exit-code table already says a program's own failure is "its code, its stderr text", with no vfs kind minted. Treat the tool the same way.
- **Amendment (spec text).**

  > `isError: true` is the tool's non-zero exit: stage status 1, every text block to the stage's stderr, `structured` kept as the extra, no rows. No `ErrorKind` is minted for it. Failures before or around the call classify by mechanism:
  >
  > | What happened | Kind | Exit |
  > |---|---|---|
  > | missing required property, uncoercible flag, unknown flag (checked client-side, before any wire call) | `vfs.invalid` | 2 |
  > | JSON-RPC `-32602` from the server | `vfs.invalid` | 2 |
  > | JSON-RPC `-32601`, or the name absent from the last listing | `vfs.not_found` on the shell's result | 127 |
  > | `-32021` (missing client capability), an input-required (elicitation) request, `InputRequiredRoundsExceededError` | `vfs.unsupported` (no ask inside vfs, ADR 084 pin 4) | 126 |
  > | `-32000` "Connection closed", or any transport error | `vfs.unavailable.backend` | 1 |
  > | the wall budget | `vfs.timeout` | 124 |
  > | the SDK rejects `structuredContent` against `outputSchema` | rows from `content` kept; `structured` dropped; one warning | 0 |
  >
  > A host tool (ToolView) that raises `ToolError(message)` exits 1 with the message on stderr. Any other exception exits 1 with `<name>: tool failed (<ExceptionType>)` on stderr; the detail is logged on the host, never sent to the caller. `vfs.internal` is not used: it means "vfs itself broke".

  Evidence for each row: EXECUTED `lifecycle_probe.out` (3) and (4) for `-32000` and the elicitation refusal; READ `mcp_types/jsonrpc.py:73-103` for the codes; READ `client.py:772-860` for `InputRequiredRoundsExceededError` and the output-schema `RuntimeError` (`session.py:1118-1154`).

### 6. Tools are the one kind that holds more than its caller — say it, and say what the tool receives — **should-fix**

- **Spec lines.** 57–62, 101–102; ADR 082 pin 3 ("host's authority"); ADR 084 pin 3 ("a program never holds more than its caller").
- **Problem.** ADR 084 pin 3 is stated for programs. Tools are not programs (ADR 082 pin 3). So a tool *can* hold more than its caller, and with finding 3's default every caller can run every tool. The spec never says this plainly. It also never says whether a tool that calls vfs gets the caller's `Fs` or the host's own handle. If the host's, a `read` holder can cause writes it could not make itself — a confused deputy that ADR 069 pin 1's "no side door" claim does not cover.
- **Amendment (spec text, §1 Execution).** "A tool runs with the host's authority. It is the one callable kind that may exceed its caller; the trust line in `type` says so. A tool that declares a parameter typed `Fs` receives the caller's `Fs` (ADR 082 pin 2) and nothing wider; vfs gives a tool no other vfs handle. What a tool does outside vfs is the host's responsibility." Add to §1 Permissions: "On a fresh node everyone holds `read_write` at `/`, so every caller can call every tool; a host that registers a tool with side effects sets a posture on `/.vfs/tools` first. The docs show it." (Or Clay changes the default; question 2.)

### 7. The MCP client lifecycle: what the 2026-07-28 client actually requires — **should-fix** (resolves the lifecycle half of the study)

- **Spec lines.** 86–89, 71–73.
- **What the SDK already does (READ, `python-sdk` @ `754254c0`).** `Client(server, mode="auto")` probes `server/discover` and falls back to the legacy handshake by itself (`client/_probe.py:1-25`, `client.py:336-345`). The legacy path is the SDK's job, not McpView's. `cache=CacheConfig()` honours `ttlMs` and `cacheScope` per client (`client.py:364-373`, `caching.py`). A `HEADER_MISMATCH` re-lists and resends once (`client.py:840-852`). `x-mcp-header` mirroring needs the tool listed first and is automatic (`session.py:1067-1112`).
- **What McpView must do itself (EXECUTED `lifecycle_probe.out` unless marked).**
  1. **Own each connection in one task.** Opening a `Client` in one task and closing it in another raises `RuntimeError: Attempted to exit cancel scope in a different task` (part 2). READ `base.py:660-662`: `close()` runs each `storage.close()` in its own task through `asyncio.gather` and `wait_for`. So a naive McpView cannot be closed by `VirtualFileSystem.close()`. One supervisor task per server must enter and exit the client; calls are sent to it.
  2. **Calls may run concurrently.** Twenty concurrent `tools/call` on one stdio client all returned, all distinct (part 1). No per-call lock is needed.
  3. **Reconnect is ours.** After a stdio server dies, the call and every later call raise `MCPError: Connection closed` (code `-32000`); the SDK does not respawn (part 3). A server that dies during connect surfaces as that error inside an `ExceptionGroup` from `__aenter__` (first run of the probe). McpView unwraps, classifies `unavailable.backend`, and reconnects on the next call with bounded backoff.
  4. **`ttlMs: 0` is the default.** python-sdk servers stamp `ttlMs: 0` and `cacheScope: "private"` on `tools/list` (part 5; `schema_shapes_probe.out`), and legacy servers send no `ttlMs`, which the SDK treats as `default_ttl_ms=0` (`caching.py:113`). So "cached under `ttlMs`" means "never cached" for most servers. Without a floor, every `ls /.vfs/bin` lists every server over the wire.
  5. **Never auto-retry a call.** A cancelled `tools/call` may have run; 2026-07-28 has no idempotency key (memo 2026-08-10 §2.5). Only discovery may be retried.
  6. **Walk pagination, bounded.** `tools/list` pages by `nextCursor`; the SDK's own re-list caps at 100 pages (`client.py:84`).
  7. **No elicitation, no sampling, no tasks.** McpView passes no callbacks and declares no extensions; the refusals classify as in finding 5.
- **Amendment (spec text, replaces lines 86–89).** "Lifecycle: `add_mcp(name, server=…)` connects eagerly through the SDK's `Client(…, mode="auto")`, which owns era negotiation and the legacy handshake; a server that cannot connect raises at `add_mcp`, not inside an agent's command. One supervisor task per server enters and exits the client; `remove_mcp` and `close()` signal it. Calls run concurrently on the one client. On `-32000` or a transport error the call classifies `unavailable.backend` and the supervisor reconnects on the next call, with backoff capped by a declared constant. A `tools/call` is never retried. The listing is fetched at connect and refreshed when it is stale: fresh for the server's `ttlMs`, but never refetched more than once per `cli` call and never more often than `MCP_LIST_FLOOR_MS` (a declared constant, default 30 s; `add_mcp(…, list_floor_ms=)` tightens or loosens it). The walk is bounded by `MCP_LIST_PAGE_BUDGET` pages. A tool missing from a refreshed listing is 127; `listChanged` via `subscriptions/listen` is out of scope (the floor covers it). Credentials are per-server configuration passed to the transport and never touch `os.environ` (memo 2026-09-04 §3.5)."

### 8. The JSON-schema-to-flags rule is specifiable now — **should-fix** (resolves the other half of the study)

- **Spec lines.** 52–56; ADR 082 pin 13.
- **What schemas look like.** EXECUTED `schema_shapes_probe.out`, from python-sdk's server deriving schemas from plain type hints (the same pydantic path `register_tool` will use): `type` scalars; `enum` with `type: string` for `Literal`; `$ref: #/$defs/X` for an `Enum` or a model; `anyOf: [T, {type: null}]` with `default: null` for `Optional`; `anyOf: [{string}, {integer}]` for `str | int`; arrays with `items`; `additionalProperties` objects for `dict`; `pattern`, `description`, `default`, `title`. `required` holds only parameters without defaults. 2026-07-28 allows full 2020-12 (`oneOf`, `allOf`, conditionals) at any level (memo 2026-08-10 §2.6).
- **What the server does with bad input.** EXECUTED: missing and wrong-typed arguments come back as `isError`, not as a protocol error; a string `"5"` for an `integer` is coerced by *this* server (pydantic), which a zod server would not do; an unknown property is **silently accepted**. So the client must coerce and must refuse unknown flags itself.
- **Amendment (spec text, replaces lines 52–56).**

  > Flags map onto the top-level `properties` of the input schema. One flag per property, `--<name> <value>` or `--<name>=<value>`; a kebab alias (`--max-count` for `max_count`) when no other property claims it. `--` ends flags. Before matching, a property's schema is normalized: a local `$ref` into `$defs` or `definitions` resolves one level; `anyOf`/`oneOf` with exactly one non-null arm, or `type: [T, "null"]`, becomes `T`.
  >
  > | Normalized property | Flag form | Coercion |
  > |---|---|---|
  > | `string` | `--x value` | verbatim; `--x=` is the empty string |
  > | `string` with `contentEncoding: base64` | `--x @path` or stdin | the bytes, base64-encoded |
  > | `integer` | `--x 5` | base-10 integer, else `vfs.invalid` |
  > | `number` | `--x 0.5` | finite float, else `vfs.invalid` |
  > | `boolean` | `--x`, `--no-x`, `--x=true\|false` | never a separate value word |
  > | `enum` or `const` (any arm types) | `--x member` | must equal a member after coercing to that member's type |
  > | `array` of a scalar above | repeat the flag: `--tag a --tag b` | each item by `items`; never comma-split |
  > | `array` of anything else | repeat the flag | each value parsed as JSON |
  > | `object`, a model, `anyOf`/`oneOf` of several non-null arms, or no `type` | `--x '<json>'` | parsed as JSON; if that fails and a `string` arm exists, the text as a string |
  >
  > Positionals bind to `required` scalar properties in `required` order; a positional past them is `vfs.invalid`. Defaults are never sent; the server applies them. Checked client-side, before the call: every top-level `required` property is present; every value coerces; no unknown flag (`vfs.invalid`, exit 2, ADR 082 pin 4). Nested rules (`pattern`, bounds, nested `required`) are the server's to judge; its answer is the tool's exit (finding 5). `--help` and the `vfs.invalid` detail render one line per property: name, type, required or default, enum members, description.
  >
  > **stdin.** When the stage has a producer or a `<` redirect, stdin binds to the one `required` property no flag or positional set, if that property is a `string` (UTF-8 text; non-UTF-8 is `vfs.invalid`), a base64 `string` (the raw bytes), or an `object`/`array` (stdin parsed as JSON). Zero or several such properties with stdin present is `vfs.invalid` naming them. A host may pin the binding at registration (`register_tool(…, stdin="body")`). Tool stages consume bytes (ADR 083 pin 2): an upstream row stage is rendered first.
  >
  > **`--json '<object>'`** is the whole arguments object, sent as given. It excludes every property flag, positional and stdin binding (`vfs.invalid` if mixed); `--json -` reads the object from stdin. A property named `help` or `json`, a name that is not a valid flag word, or a schema whose top level is not an `object` with `properties` (a top-level `oneOf`, say) is reachable only through `--json`; `--help` says so.

  The same table serves ToolView. There the host also validates fully with the function's own pydantic model before calling, so a host tool's bad input is always `vfs.invalid`, exit 2, before it runs.

### 9. Tool return values: `application/json` for everything is wrong for `str` — **should-fix**

- **Spec lines.** 57–62; ADR 082 pin 15.
- **Problem.** A tool that returns `"hello"` would print `"hello"` with quotes, as one JSON row. `cat` would show JSON punctuation. Bytes have no rule. `None` has no rule. A sync function blocks the event loop.
- **Amendment (spec text).** "The return value becomes rows by type: a `Result` passes through unchanged; `str` is one text row (`text/plain`); `bytes` one bytes row (the mime the host declared at registration, else `application/octet-stream`); `None` no row; anything else is one row whose `content` is its JSON (pydantic models through `model_dump_json`), `mime_type` `application/json`. The row is at `/.vfs/run/<call-id>/stdout`. A sync function runs in a worker thread; at the deadline the call reports `vfs.timeout` and the thread is abandoned, not killed (Python cannot kill a thread; the docs say so). A per-tool deadline may only tighten `WALL_TIME_BUDGET` (ADR 084 pin 6)."

### 10. Name and column collisions in `/.vfs/bin` — **should-fix** (shared with spec 169)

- **Spec lines.** 96–98.
- **Problems.**
  - `kind=tool` and `kind=mcp`: READ `paths.py:38`, `ObjectKind = Literal["file", "directory"]`. `Observation.kind` cannot hold them.
  - `source` = "their view path": `source` is `Literal["text", "bytes"]` (finding 4).
  - Remote names change under you. A server's listing can gain `deploy` between two calls (the floor in finding 7 bounds how fast). If the MCP view sits before `/opt/bin` in the union, a remote server can take over a bare name that used to run a stored program. Two servers that both list `search` collide silently: first wins.
  - MCP tool names may contain `.`; vfs segments allow it, but `<server>.<tool>` qualification (spec 034's `exe <provider>.<tool>`) then becomes ambiguous.
- **Amendment.** "The bin view's columns are `program_kind` (`program`, `tool`, `mcp`) and `target` (the entry's path); `kind` stays the `ObjectKind` `file`. Views join the union after every stored program directory unless the host places them otherwise. An MCP tool is also reachable by its path (`/.vfs/mcp/<server>/tools/<tool>`), which is never shadowed. When two members offer one name, `which -a` lists every one; the shadowed ones carry a `shadowed` flag." (Spec 169 must carry the same column rename.)

### 11. Manifests from a remote server are untrusted text — **should-fix**

- **Spec lines.** 74–76, 99–102.
- **Problem.** `type`, `help`, `--help` and `cat` put a server's `description` and schema `description`s straight into an agent's context. A hostile or compromised server can write instructions there ("tool poisoning"), and can change them after the host connected (the listing refreshes).
- **Evidence.** READ `skills.py:37-42`: vfs already rejects `<` and `>` in skill frontmatter because "angle brackets in frontmatter can inject instructions into the system prompt", and caps `DESCRIPTION_MAX` at 1024.
- **Amendment.** "Every manifest line from a server is rendered as data: control characters removed, each description capped at `MANIFEST_DESCRIPTION_BUDGET` characters with the truncation marker, prefixed by the provenance line `runs on <server>`. The manifest's `content_hash` is shown by `stat`, so a host can see a description change. vfs never places manifest text in a system prompt."

### 12. The `mcp` dependency is heavy and undeclared — **should-fix**

- **Evidence.** READ `python-sdk/pyproject.toml`: `mcp` pulls `starlette`, `uvicorn`, `sse-starlette`, `pyjwt[crypto]`, `opentelemetry-api`, `httpx2`, `jsonschema`, `python-multipart`, and raises the `pydantic` floor to 2.12. READ vfs `pyproject.toml`: none of these are dependencies today; `pydantic>=2.0`. `scripts/ci.sh` checks a wheel budget. Spec 034's criterion 6 wanted `vfs` importable and testable without `mcp`.
- **Amendment.** "`mcp` is an optional extra, `vfs-py[mcp]`, shared with spec 171. McpView lives in `vfs/mcp/client.py`, imported only through the extra (top-of-module imports, per CLAUDE.md). `add_mcp` without the extra raises at the call with an install hint. ToolView and the flag mapping need no extra. The `mcp` group joins the dev dependencies so the suite runs an in-process server." Also: a LangChain `BaseTool` (line 41) is accepted by shape (`name`, `description`, `args_schema`, `ainvoke`), so `vfs` never imports `langchain_core` outside its extra.

### 13. Resources: in scope with no path rule — **should-fix**

- **Spec lines.** 72–73 (`/resources/<…>`), 106.
- **Problem.** A resource URI (`https://…/a.pdf?x=1`, `repo://acme/app/README.md`, `file:///etc/hosts`) has no stated mapping to a vfs path. Query strings, length past `MAX_PATH_LENGTH`, collisions and templates (RFC 6570, not enumerable) are all open.
- **Amendment (pick one).** (a) Out of scope at v1; `/.vfs/mcp/<server>/resources` lists nothing. Or (b) in scope with: "a listed resource is a file at `resources/<n>` (its index in the listing) whose manifest line names the URI; `read` of it runs `resources/read` (cacheable, `ttlMs` honoured, `size` from the listing); templates are listed, not readable." Lean (b) — it is the honest file-shaped half (memo 2026-09-04 §4.1) and it is the natural home for the "file-shaped result" finding 1 takes away from tools.

### 14. Which read verbs do the views serve? Search is the premise spec 034 was built on — **should-fix**

- **Spec lines.** absent.
- **Problem.** Spec 034's whole premise was "tools as discoverable, searchable files": `grep` and `glean` over tool descriptions. Spec 169 keeps `/.vfs` out of unscoped `glob` and `grep`. Spec 170 does not say whether `grep -r x /.vfs/tools` or `glean` scoped to `/.vfs/mcp` work at all.
- **Amendment.** "The catalogue views serve `read`, `stat`, `ls`, `tree`, `glob` and `grep` over their manifests (grep scans the rendered manifest in memory; the catalogue is small by nature and its size is stated, not capped). `glean` over catalogues is out of scope at v1." Or Clay decides glean matters (question 4).

### 15. Acceptance criteria — **should-fix**

- Criteria 2 and 3 depend on open markers. Nothing tests the flag table, stdin, `--json`, lifecycle, the call count, or the dependency rule. No engine legs, though finding 3 adds a statement.
- **Amendment (add).**
  6. Each row of the flag table, for ToolView and for an in-process MCP server: one passing call and one `vfs.invalid` (exit 2, zero wire calls, spied).
  7. `cat f | upload` binds `body`; `cat f | upload --body x` is `vfs.invalid`; `--json` with a property flag is `vfs.invalid`; `--json -` reads stdin.
  8. `cat /.vfs/tools/x`, `stat`, `ls -l /.vfs/tools`, `grep -r . /.vfs/tools` issue zero tool calls (spied).
  9. `ls /.vfs/bin` twice in one `cli` call issues one `tools/list` per server; inside the floor, zero (counted).
  10. A stdio server killed mid-session: the call is `vfs.unavailable.backend`, exit 1; the next call respawns once (counted); a timed-out call is issued exactly once.
  11. `VirtualFileSystem.close()` closes every McpView with no cross-task error, on 3.11 and 3.13.
  12. `import vfs` and the ToolView suite pass without `mcp` installed.
  13. The 126/127 split of criterion 3 holds on the four engine legs.

### 16. Nits

- Line 7 cites `specs/active/034-mcp-native-mounts`; it is `specs/archive/034-mcp-native-mounts`.
- Line 24 credits study 09 F3 with just-bash's `invokeTool` hook; that is in study 03 (F3's table, line 145) and study 05 (line 249). F3 of study 09 has amla only.
- ADR 082 pin 6 says servers are "projected the way mcpfs classifies it". The 2026-09-04 memo §5 says not to take mcpfs's name heuristic. Reword the pin to "projected by declared shape".
- Line 81 ("`isError` to a classified `vfs.unavailable` or the error text as `invalid`") contradicts line 84's lean. Finding 5 replaces both.
- Scope (line 108) puts `listChanged` out; line 89 asks to study it. Finding 7 settles it: out, the floor covers it.
- `register_tool` and `add_mcp` have no inverse (`unregister_tool`, `remove_mcp`). A host that rotates credentials needs `remove_mcp`.
- ADR 084 pin 8's `deny_ops` mask by program name does not reach tools (they are on no mount). Say that a host masks a tool by not registering it or by posture.
- Two `ttlMs` fields exist (cache freshness vs task retention, memo 2026-08-10 §8.7). Name the constant for the first only.
- A version for a synthesized entry: say `version` is `None` and `content_hash` is the manifest's, so the placeholder and `stat` never invent history.

## What the spec gets right

- Tools as entries with a manifest, callable by name with the same convention as every program. One calling convention is the right call.
- Showing trust in `type` ("runs on the host", "runs on <server>").
- Using the same adapter inbound and outbound (ADR 085), so one module owns the block vocabulary.
- Putting MCP servers under `/.vfs/mcp/<server>/` per server: names cannot collide across servers by path, only in the bin union.
- Leaving sampling, subscriptions and prompts-as-callables out. Executed: elicitation over a modern connection already fails closed in the SDK (`lifecycle_probe.out` (4)), so "no ask inside vfs" costs nothing.

## Questions only Clay can answer

1. **Does `cat` ever run a tool?** (finding 1.) Proposed: no. `cat` shows the manifest; a tool runs only as a command. ADR 082 pin 13's last sentence is amended. File-shaped results come from MCP resources.
2. **The default for tools on a fresh node.** (findings 3, 6.) Your rule is "no special default". Its consequence: on a fresh node every caller, anonymous included, can run every host tool with the host's authority. Keep it (and document "set a posture on `/.vfs/tools` before registering a tool with side effects")? Or make `register_tool` and `add_mcp` take a required `posture=`? Proposed: keep the rule, document it, and have `register_tool` warn when the effective posture at `/.vfs/tools` is above `list` for anonymous.
3. **`SupportsRun`: delete, not rename?** (finding 2.) Proposed: delete it in spec 167. Catalogues are router-owned; a vfs-protocol server is a routing mount (spec 034's routing mode, roadmap 020), later. This amends ADR 082 pin 12.
4. **Search over tools.** (finding 14.) Spec 034 made tools searchable files. Is `grep` over the catalogues enough at v1, or should `glean` rank tool descriptions (the "find the right tool among 500" case)? Proposed: `grep` now, `glean` later.
5. **Resources at v1?** (finding 13.) Proposed: yes, by listing index, read through `resources/read`.

## What the one remaining study must still answer

Most of it is answered above: the flag table (finding 8, from executed schemas), the error map (finding 5, executed), and the client lifecycle facts (finding 7, executed). Three small things remain. Each is an afternoon, not a study set.

1. **A supervisor spike.** Build the one-task-per-server owner against stdio and streamable HTTP on Python 3.11 and 3.13. Check: close through `VirtualFileSystem.close()`'s `gather`/`wait_for` shape; a call cancelled by the wall budget leaves the connection usable; respawn after a kill. Count, never time.
2. **A real-server schema census.** List the tools of three or four widely used servers (the reference filesystem server, a GitHub server, one TypeScript/zod server) and count how many properties fall in each row of the flag table, and how many tools need `--json`. This tells us whether dotted flags for nested objects (`--where.field a`) are worth a later pass.
3. **Legacy servers in the wild.** Confirm `mode="auto"` against a 2025-06-18 stdio server and one streamable-HTTP server with `Mcp-Session-Id`: discovery, `ttlMs` absent, session expiry. The SDK claims to handle all three (`_probe.py:1-25`); it has not been run against a real legacy peer here.

The `rungs_at` statement shape (finding 3) is spec work, not study: the machinery exists (`grants.py:169`, `:477`).

## Executed scripts

All under `experiments/r170/`, run from the repo root.

- `posture_at_view_paths.py` → `.out` (`uv run python …`): posture and grant rows at `/.vfs/tools/...` are accepted by the root mount today; a write there is lawful today; a stored row there is gated by them.
- `grants_as_caller_at_view_path.py` → `.out` (`uv run python …`): no public verb gives a `list`-holder or anonymous their rung at a path with no row; a fresh node gives everyone `read_write` at `/`.
- `schema_shapes_probe.py` → `.out` and `.stderr` (`uv run --with mcp python -I …`, `mcp` 2.3.0): the input schemas pydantic emits for every common parameter shape; missing, wrong-typed and unknown-tool calls all return `isError`; unknown properties are accepted silently; an unexpected exception's detail stays in the server's log; the five block types plus `structuredContent` on one result; `ttlMs: 0` on `tools/list`.
- `lifecycle_probe.py` → `.out` (same command): 20 concurrent calls on one stdio client succeed; open-in-one-task, close-in-another raises; a dead server is `MCPError -32000` on every later call; elicitation fails closed; `ttlMs: 0` defeats the SDK cache.

## One-line version

Build the views, but first decide that `cat` never runs a tool, give the call one gated door instead of a storage capability, add a seam that judges rungs at paths with no row, and write down the inbound table, the flag table and the client lifecycle this review drafts.
