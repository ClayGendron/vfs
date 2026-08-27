# MCP 2026-07-28: the stateless revision — what changed, and where it meets vfs

- **Status**: research memo (commits us to nothing; feeds the MCP serve
  pass — specs 054/056's serve story, spec 045's wire contract, and the
  deferred cursor/pagination and long-batch questions)
- **Date**: 2026-08-10
- **Owner**: Clay Gendron
- **Question**: MCP published its 2026-07-28 specification revision — the
  largest since the protocol launched. What exactly changed, what is the
  ecosystem doing about it, and what does it mean for vfs, whose entire
  design is "an MCP design" (result envelope as `structured_content`,
  serve() as the wire boundary, 10,000+-file batches as a supported
  contract)?
- **Evidence gathered**: published spec pages (changelog, MRTR pattern,
  extensions overview, announcement blog) fetched 2026-08-10; three
  parallel line-level studies of freshly-pulled read-only reference
  checkouts — `~/Git/Repos/modelcontextprotocol` @ `b25c0874` (the
  2026-07-28 schema, SEPs 2575/2567/2663/2596/2577, transport docs),
  `~/Git/Repos/python-sdk` @ `a4f4ccd0` (the official SDK's v2 line),
  and `~/Git/Repos/fastmcp` @ `6475650` (FastMCP 4, now PrefectHQ).
  Citations are repo-relative to those checkouts; vfs artifacts are
  cited from `src/vfs/` and `context/`.

---

## 1. The revision in one page

2026-07-28 is a **stable release**, published on that date after a
release candidate locked 2026-05-21, and it is the biggest MCP revision
since launch. The headline: MCP stops being a bidirectional, stateful,
session-holding protocol and becomes a **request/response stateless
protocol**. Everything else in the revision — header routing, response
caching, the MRTR pattern, the tasks extension, the deprecation policy —
is either a consequence of that flip or infrastructure to make it
governable.

The shape of the change:

- **No handshake, no sessions.** `initialize`/`notifications/initialized`
  and the `Mcp-Session-Id` header are gone (SEP-2575, SEP-2567). Every
  request is self-contained: it carries its protocol version and client
  capabilities in `_meta`, and servers must not infer capabilities from
  prior requests.
- **No server-initiated requests.** The server→client back-channel
  (`sampling/createMessage`, `elicitation/create`, `roots/list` as
  standalone requests) is replaced by **Multi Round-Trip Requests**
  (MRTR): the server returns an interim result asking for input; the
  client retries the original request with the answers attached (§3).
- **Cross-call state is application data.** Servers that need state
  across calls mint **opaque handles returned in tool results and passed
  back as ordinary tool arguments** — deliberately not a protocol
  construct (§5).
- **Durability is an extension.** SSE resumability (`Last-Event-ID`) is
  removed; a broken response stream *is* the cancellation, and the
  client re-issues the request fresh. Workloads needing durability are
  pointed at the **tasks extension** (`io.modelcontextprotocol/tasks`),
  now outside the core (§4).
- **A real deprecation regime.** Roots, Sampling, Logging, Dynamic
  Client Registration, and the legacy HTTP+SSE transport are formally
  Deprecated under a new feature-lifecycle policy with a twelve-month
  minimum window (§6).

Enterprise endorsements at launch (AWS/Bedrock, Cloudflare, Google
Cloud, Microsoft Foundry, Netlify, Supabase, Figma) frame the stateless
flip as the production-scaling fix it is: plain round-robin load
balancing, no sticky sessions, no shared session storage.

## 2. The stateless core, precisely

### 2.1 Per-request envelope

Every request carries, in `params._meta`
(`schema/2026-07-28/schema.ts:63-111`):

- `io.modelcontextprotocol/protocolVersion` — **required**; must match
  the `MCP-Protocol-Version` HTTP header or the server answers `400` +
  `HeaderMismatch` (`-32020`).
- `io.modelcontextprotocol/clientCapabilities` — **required**; empty
  object means "no optional capabilities"; servers MUST NOT infer
  capabilities from prior requests.
- `io.modelcontextprotocol/clientInfo` — optional/SHOULD. (SEP-2575's
  text says Required; the shipped schema says optional — the schema
  wins, `schema.ts:90`.)
- `io.modelcontextprotocol/logLevel` — optional, replaces
  `logging/setLevel`; absent means the server must not send
  `notifications/message` for that request. Already deprecated with the
  Logging feature.

Results carry `io.modelcontextprotocol/serverInfo` in `_meta`
(`schema.ts:143-158`). Version mismatch yields
`UnsupportedProtocolVersionError` (`-32022`) with
`data.{supported, requested}` — the one error auto-negotiating clients
key their fallback on.

### 2.2 `server/discover`

Servers **MUST** implement `server/discover` (`schema.ts:655-697`):
returns `supportedVersions`, `capabilities`, optional `instructions`,
and is itself cacheable (`ttlMs`/`cacheScope` required in its result).
Clients MAY call it up front or negotiate inline per-request; on stdio
it doubles as the era probe. There is no `serverInfo` field in the
discover body — identity rides `_meta` on every result.

### 2.3 Required `resultType` on every result

`Result.resultType` is a **required** field: `"complete"` for ordinary
results, `"input_required"` for MRTR interim results
(`schema.ts:216-236`); the tasks extension reserves `"task"`. Clients
must read absence (from older servers) as `"complete"`. The union is
open — extensions may add values.

### 2.4 What was removed outright

`ping` (both directions), `logging/setLevel`,
`notifications/roots/list_changed`, `resources/subscribe`/`unsubscribe`,
the HTTP GET stream endpoint, and SSE resumability. The 2026-07-28
`ClientNotification` union is `CancelledNotification` alone; the schema
defines **no `ServerRequest` union at all**
(`python-sdk src/mcp-types/mcp_types/methods.py:179`) — "no
back-channel" is a type-level fact, not a convention.

Server-pushed change notifications survive only via
**`subscriptions/listen`**: one long-lived POST response stream the
client opts into per notification type (`toolsListChanged`,
`promptsListChanged`, `resourcesListChanged`, `resourceSubscriptions`;
`schema.ts:1270-1288`). The server acknowledges the honored subset;
notifications on that stream are tagged with the subscription's request
ID. Request-scoped notifications (`progress`, `message`) flow only on
their originating request's response stream.

### 2.5 Broken streams and the missing idempotency story

On HTTP, **closing the SSE response stream is the cancellation** of the
in-flight request (`seps/2575-stateless-mcp.md:346-358`); on stdio the
client sends `notifications/cancelled`. Resumability is gone because
resuming would require per-request server state. The client's remedy is
to **re-issue the request as a new request with a new ID**.

The SEP's own words for anything that can't afford that: "Workloads that
need durability or resumability MUST use the tasks primitive instead"
(`seps/2575-stateless-mcp.md:360-369`). Two flags on that sentence:

- It was written when tasks were core; tasks are now an **optional
  extension**, so a given server may legitimately offer neither
  resumability nor tasks.
- There is **no protocol-level idempotency key, request-dedup
  mechanism, or at-most-once guarantee anywhere in the revision**. The
  only tool-level signal is the non-authoritative
  `ToolAnnotations.idempotentHint`. A re-issued request may execute
  twice; the sanctioned mitigations are the tasks extension and
  naturally-addressable operations (handles, §5).

### 2.6 Header routing on Streamable HTTP

The transport is POST-only. Required headers on every request:
`MCP-Protocol-Version`, `Mcp-Method` (the JSON-RPC method), and — for
`tools/call`, `resources/read`, `prompts/get` — `Mcp-Name` (the tool
name / URI), so load balancers and gateways route without parsing
bodies. Servers **MUST reject header/body mismatches** (`400` +
`-32020`) — the stated threat is a gateway authorizing on the header
while the server executes the body
(`docs/specification/2026-07-28/basic/transports/streamable-http.mdx:580-603`).

Tools may additionally annotate input-schema properties with
`x-mcp-header`, and conforming clients **MUST** mirror those argument
values into `Mcp-Param-{name}` headers (string/integer/boolean only, no
`number`, statically reachable via `properties` keys only — no `$ref`,
no `oneOf`, no arrays). Servers must reject mismatches between mirrored
header and body value.

Also notable: tool `inputSchema`/`outputSchema` are loosened to **full
JSON Schema 2020-12** (composition, conditionals, `$ref`/`$defs`;
defaults to 2020-12 when `$schema` is absent), `structuredContent` is
widened from JSON object to **any JSON value**, and a new error-code
allocation policy partitions the JSON-RPC server range: `-32000..-32019`
implementation-defined, `-32020..-32099` reserved for the spec.

## 3. MRTR — the replacement for the back-channel

A server needing mid-call input returns an `InputRequiredResult`
(`resultType: "input_required"`) carrying:

- `inputRequests` — a map of server-assigned keys to embedded request
  objects (`ElicitRequest`, `CreateMessageRequest`, `ListRootsRequest`);
- `requestState` — an **opaque server blob** the client must echo back
  verbatim on retry, and must not inspect or modify.

The client gathers answers, then **retries the original request** (new
JSON-RPC ID) with `inputResponses` + `requestState` attached. Supported
on exactly `tools/call`, `resources/read`, `prompts/get`. The server
processing the retry needs nothing beyond the retry request itself —
that is the point.

Security posture is explicit and unusually sharp: servers **MUST treat
`requestState` as attacker-controlled**; if it influences authorization
or business logic it must be integrity-protected (HMAC/AEAD), with
principal binding, TTL, and origin-request binding recommended inside
the protected payload. The python-sdk ships this as infrastructure:
AES-256-GCM under HKDF-derived keys, principal/audience/expiry claims
enforced fail-closed by a middleware boundary so handlers never touch
the codec (`python-sdk src/mcp/server/request_state.py:96-360`). Its
default key is per-process — multi-replica deployments must supply
shared keys.

Two structural notes:

- Two of MRTR's three embedded request types (sampling, roots) are
  themselves deprecated (§6) — post-window, **MRTR is effectively
  elicitation-only**.
- MRTR retry results **MUST NOT be cached**, and interim
  `input_required` results carry no cache hints.

## 4. Tasks: the durability answer, as an extension

`io.modelcontextprotocol/tasks` (SEP-2663, Final; normative text lives
in the `ext-tasks` repo). Redesigned end-to-end from the 2025-11-25
experimental core version — **not wire-compatible** with it.

Mechanics that matter for a batch workload:

- **Negotiation is per-request, server-decided.** The client declares
  the extension in `_meta` client capabilities on each request; the
  server may then answer any `tools/call` with a `CreateTaskResult`
  (`resultType: "task"`, task fields inlined: `taskId`, `status`,
  `ttlMs`, `pollIntervalMs`) instead of running it synchronously. No
  per-request opt-in, no tool-level `taskSupport` flag. A server that
  *cannot* run a request synchronously for a non-declaring client
  answers `-32021` (missing required client capability).
- **Creation is strongly consistent**: the server must not return the
  handle until `tasks/get` on it would resolve.
- **Polling, not blocking.** `tasks/get` is a pure idempotent read
  (statuses: `working`, `input_required`, `completed`, `cancelled`,
  `failed`); `tasks/update` is the write path for delivering
  `inputResponses` mid-task; `tasks/cancel` is a cooperative,
  eventually-consistent ack. The old blocking `tasks/result` is gone
  (`-32601` under the extension).
- **`completed` includes tool-level failure**: a `CallToolResult` with
  `isError: true` lands in `completed`, not `failed` — `failed` is
  reserved for JSON-RPC-level errors. Partial batch failure is a
  *result*, not a task failure.
- **`tasks/list` is removed and deliberately not replaced** — without
  sessions there is no scope a server can define unilaterally, and
  supporting listing at all would leak one caller's task IDs to
  another. Consequence: **the client is the sole registry of its own
  task IDs** and is told to persist them durably to survive restarts
  (`seps/2663-tasks-extension.md:33,312,957`).
- **No `notifications/progress` on tasks at all** — progress rides the
  human-readable `statusMessage` and/or the task's eventual result.
  Optional push: `notifications/tasks` via `subscriptions/listen` with
  a `taskIds` filter (an extension-added filter field — not in the core
  `SubscriptionFilter`), each notification carrying the full task
  snapshot.
- **Routing**: `tasks/*` requests must set `Mcp-Name` to the `taskId`,
  so intermediaries can pin a task's polls to the instance holding its
  state.
- Task IDs may function as bearer tokens for the stored state — the SEP
  requires enumeration-resistant entropy and authn/authz on every
  task-touching request.

## 5. Cross-call state: server-minted handles (SEP-2567)

The sessions post-mortem is worth internalizing: after a year in the
spec, sessions never converged on a meaning (fresh session per tool
call in ChatGPT, per process in IDEs, per page load on the web, almost
never resumed), and their mere *possibility* forced orchestrators into
`O(subagents × servers)` `tools/list` calls because any list could be
session-scoped. Statelessness makes it `O(servers)`.

The replacement is a documented **pattern, not a protocol construct**:
a tool returns `{"basket_id": "bsk_a1b2c3"}` in `structuredContent`;
later tools take `basket_id` as an ordinary argument. The normative
residue is small but binding:

- **List results MUST NOT vary per-connection or as a side effect of
  other requests** — the "call `connect_database()` and a `query` tool
  appears" pattern is no longer permitted. Expose the tool
  unconditionally; let it error usefully without a valid handle.
  (Lists may still vary by the authorization presented.)
- Non-normative but mirrored into the spec's tools page
  (`docs/specification/2026-07-28/server/tools.mdx:683-736`): handles
  opaque; **possession is not authorization** — validate
  `(handle, auth_context)` per call, ≥128 bits entropy if
  unauthenticated; durability documented in the tool description
  (visible to the model, not just to humans); expired handles return
  recoverable errors naming the handle, not "invalid argument";
  creation takes parameters so state can't exist half-configured;
  cleanup and re-listing tools offered so a model can recover.
- Client responsibility: keep handles alive across **context
  compaction** — a summarized-away handle orphans its state.

Rollout is a clean break: no deprecation window for sessions;
session-dependent servers stay on older revisions until migrated.

## 6. Caching, deprecation policy, extensions framework

**Caching (SEP-2549).** Six result types are `CacheableResult` with
**required** `ttlMs` (freshness, ms) and `cacheScope`
(`public`/`private`): `server/discover`, `tools/list`, `prompts/list`,
`resources/list`, `resources/templates/list`, `resources/read`
(`schema.ts:1081-1110` and subclasses). `tools/call` is *not*
cacheable. Servers SHOULD return `tools/list` in deterministic order —
explicitly to stabilize client-side LLM prompt caches. Note the name
collision: `CacheableResult.ttlMs` (cache freshness) and the task
`ttlMs` (retention, nullable) are unrelated fields.

**Deprecation (SEP-2596, SEP-2577).** A formal Active → Deprecated →
Removed lifecycle with a **twelve-month minimum window** measured from
the deprecating revision's release. Deprecated in 2026-07-28, earliest
removal in the first revision on or after 2027-07-28: **Roots** (pass
paths as tool parameters/config instead), **Sampling** (call your LLM
provider directly), **Logging** (stderr / OpenTelemetry), **Dynamic
Client Registration** (→ Client ID Metadata Documents). The legacy
HTTP+SSE transport and the `includeContext` server values are
reclassified Deprecated on shorter fuses. Selection rationale: weakest
adoption-to-complexity ratio, and sampling/roots are the two biggest
security surfaces in the protocol (server-steered completions;
filesystem disclosure).

**Extensions (SEP-2133).** Reverse-DNS identifiers
(`io.modelcontextprotocol/tasks`; third parties use their own domain,
e.g. `com.example/my-extension`), negotiated via an `extensions` map in
both capability objects, always off by default, evolving independently
of the core. Official today: tasks, MCP Apps
(`io.modelcontextprotocol/ui` — inline interactive UI in
conversational clients), and two auth extensions (OAuth client
credentials, Enterprise Managed Authorization).

## 7. Ecosystem state (first-hand, 2026-08-10)

**python-sdk** (`a4f4ccd0`): v2 on `main` is the stable line
(`mcp` + `mcp-types` distributions, lock-stepped); v1.x is maintenance.
One server serves **both eras from the same process** — a
first-request classifier picks handshake vs modern per connection
(`src/mcp/server/runner.py:602-646`), and the streamable-HTTP manager
splits on the version header (`src/mcp/server/streamable_http_manager.py:181-193`).
`FastMCP` the class is renamed `MCPServer`; decorator shape is
unchanged. MRTR has three API tiers, the best being `Resolve`
dependency injection, which transparently batches
elicitation/sampling/roots into `InputRequiredResult` on modern
connections and falls back to real back-channel requests on legacy ones
(`src/mcp/server/mcpserver/resolve.py`). Cache hints are stamped
per-field with `ttl_ms=0`/`private` conservative defaults
(`src/mcp/server/caching.py:45-58`). **The tasks extension is not
implemented** — only reserved seams (open `ResultType`, extension
method bindings) exist (`docs/whats-new.md:145`).

**fastmcp** (`6475650`): now **FastMCP 4** under PrefectHQ, a monorepo
(`fastmcp_slim` core, `fastmcp_tasks`, `fastmcp_remote`) pinned to SDK
v2 and fully on 2026-07-28 — dual-era from one deployment, modern by
default for its client. Two findings that bind design work:

- **`ctx.sample()` is gone on every era** (constructor kwarg raises
  `TypeError` citing SEP-2577); `ctx.elicit()` survives but **raises on
  modern connections** — the MRTR return-value pattern is the only
  modern path, and the two mechanisms are mutually exclusive by era
  (`fastmcp_slim/fastmcp/server/context.py:1089`,
  `server/mixins/mcp_operations.py:279-292`).
- **Tasks are a full first-class subsystem** (`fastmcp_tasks`,
  SEP-2663, Redis-backed via Docket): `task=True` on the `@tool`
  decorator, durable `input_required` parking, encrypted task-context
  snapshots, modern-era only — a legacy client just runs the tool
  synchronously.
- Its session replacement (`fastmcp_slim/fastmcp/server/sessions.py`)
  states the operative security fact plainly: isolation comes from the
  authenticated principal; **without auth, a session/handle id is a
  bearer capability and sessions are not a boundary between clients**.

Also: ADR 022 grounded its "tools reach the wire only via explicit
registration" claim on `fastmcp/server/server.py:1634`; that file moved
in the 4.0 monorepo split — the surface survives byte-for-byte at
`fastmcp_slim/fastmcp/server/server.py:1795` (now delegating to a
provider layer). The ADR's argument stands; the citation is stale.

## 8. Where it meets vfs

vfs has no serve layer yet — spec 054 waits on `serve()` existing, and
ADR 022 is drafted but unratified. That timing is now an asset: **vfs
can build modern-era-first and never carry the deprecated surface.**
The impacts, from most to least binding:

### 8.1 The 10k-batch contract collides with re-issue semantics

This is the sharpest finding. vfs's contract says 10,000+-file batches
in a single call are supported, not an edge case. On the 2026-07-28
wire, a long-running `tools/call` whose response stream breaks is
*cancelled by definition*, and the client's remedy is to re-issue —
with **no protocol idempotency mechanism** to make the re-issue safe.
A re-issued 10k-file `write` is a double-execution question vfs's
storage layer answers per-entry (versions, guarded updates) but the
verb surface has never had to answer as a whole.

The spec's own answer for durable long work is the tasks extension —
whose semantics happen to fit vfs's existing result philosophy
remarkably well: a partial-failure batch is a `completed` task whose
`CallToolResult` carries `isError: true`, i.e. **evidence in the
result, verdict derived** — exactly ADR 010's posture. But adopting it
means choosing a serving stack that has it (FastMCP 4 today; python-sdk
not yet), accepting a poll-based client contract, and accepting that
progress reporting rides `statusMessage` (no `notifications/progress`
on tasks). The serve() spec needs an explicit decision: which verbs (if
any) may go task-backed, at what batch-size threshold, and what the
synchronous path promises when a stream breaks mid-batch.
[NEEDS CLARIFICATION: is task-backed execution in scope for the first
serve() landing, or is the first landing synchronous-only with
documented re-issue semantics?]

### 8.2 The deferred cursor question now has its wire answer

Spec 093's truncation-flag decision deferred keyset resumption "to the
MCP pass, where a cursor becomes wire-representable." SEP-2567 settles
what that looks like: a cursor is a **server-minted opaque handle in a
tool result, passed back as an ordinary tool argument** — with binding
etiquette vfs should adopt wholesale: opaque (no parseable structure),
possession ≠ authorization (validate against the principal — spec 070's
concern), lifetime documented *in the tool description*, and expiry
returning a recoverable, named error — which in vfs terms is a result
kind in the `KIND_CONTRACTS` table with a `refresh` retry class, not a
raw failure. The read-family cursor (glob/ls/tree/grep) should be
specced against this pattern.

### 8.3 Spec 045's wire contract gets both easier and stricter

- **Easier**: tool schemas are now full JSON Schema 2020-12, so the
  16-verb request schemas can be pinned faithfully (composition,
  conditionals, `$defs`) rather than flattened to the old
  properties-only shape. `structuredContent` widening to any JSON value
  costs nothing (the envelope payload is already an object) but the
  envelope's own tolerant-reader rules (`extra='allow'`) mean inbound
  payloads carrying `resultType` or future spec fields already
  round-trip safely.
- **Stricter**: `tools/call` params now include `inputResponses` and
  `requestState` — spec 045's unknown-param policy must classify these
  as *protocol-owned*, not verb kwargs, before the schemas are pinned.
  And the new error-code allocation policy (`-32000..-32019`
  implementation-defined, `-32020..-32099` spec-reserved) is the lane
  vfs's JSON-RPC `error.data` usage (`envelope.py:88`) must stay
  inside if vfs ever mints protocol-level codes.
- **List determinism**: `tools/list` must be deterministic and must not
  vary per-connection — vfs's registered verb surface is static per
  serve(), so this is free, but it *forbids* any future
  "capability-dependent tool appears after a call" design, and the
  drift test pinning `ALL_OPS` (`src/vfs/ops.py`) becomes indirectly a
  wire-contract test.

### 8.4 ADR 022 survives; its citation and one premise need refresh

The topology-lock policy is untouched — if anything strengthened: with
no server-initiated requests and no sessions, "nothing unregistered
exists on the wire" is now backed by the protocol's own no-back-channel
construction. Two mechanical notes for ratification: the fastmcp
grounding citation moved (`fastmcp_slim/fastmcp/server/server.py:1795`,
provider indirection behind it), and the ADR's "serve-lifetime session
state" phrasing should be reworded — it means host-process lifetime,
which is fine, but "session" now collides with a concept the protocol
deleted. Relatedly, spec 070's principal-scoped sessions must not lean
on `Mcp-Session-Id` (it no longer exists); the principal comes from the
authorization layer, and FastMCP 4's warning applies verbatim: without
auth, any vfs-minted handle is a bearer capability.

### 8.5 vfs never needed the deprecated features — confirm and move on

vfs's planned wire surface uses tools only: no Roots (mount topology is
host-side by ADR 022; paths arrive as tool parameters, which is
exactly the suggested Roots migration), no Sampling (vfs calls no LLM
through its client), no MCP Logging (the envelope *is* the diagnostic
channel; operational logging is stderr/OTel). The one interactive
primitive vfs might ever want — confirmation before a risky operation —
maps to MRTR elicitation, but ADR 027 (delete never destroys) was
designed precisely so no verb on the agent surface needs a confirmation
gate. Worth stating in the serve() spec so nobody adds elicitation
casually: on the modern era it forces the MRTR return-shape into the
tool's type union, and vfs tools should stay
`resultType: "complete"`-only until a concrete need exists.

### 8.6 Serving-stack choice is now a real decision

Both candidate stacks serve both eras from one process, so vfs does not
have to choose an era — it has to choose a stack. python-sdk v2:
official, disciplined wire pins (snapshot tests), AEAD `requestState`
infrastructure, but **no tasks**. FastMCP 4: tasks today (with a Redis
operational dependency), richer server ergonomics, era-gated
elicitation, but a heavier and faster-moving dependency that just went
through an ownership and packaging split. Given 8.1, the tasks question
and the stack question are the same question, and it deserves its own
research-then-ADR pass when serve() work starts — including the option
of vfs implementing the tasks extension itself on python-sdk's reserved
seams (`ResultType` open union, `MethodBinding`), since a vfs task
handle could be backed by the same storage layer as everything else.

### 8.7 Smaller consequences worth recording

- **Caching**: vfs list results (`tools/list` of the verb surface,
  any future resource exposure) should ship deliberate
  `ttlMs`/`cacheScope` values; the conservative default
  (`0`/`private`) is correct until a decision says otherwise.
- **Header routing**: `Mcp-Name` routing on tool names means gateways
  can rate-limit `write` separately from `read` with zero vfs work —
  a free operational win worth mentioning in the serve() spec.
  `x-mcp-header` mirroring of a vfs argument (e.g. a mount prefix) is
  *possible* but constrained (primitive, statically-reachable) and
  should not shape the verb schemas.
- **`subscriptions/listen`** is the wire shape any future vfs
  watch/notify story must fit: opt-in per type, one stream, no
  unsolicited pushes. The metadata/watch open questions should cite it
  rather than inventing a channel.
- **Two `ttlMs` fields exist** (cache freshness vs task retention).
  If vfs adopts both surfaces, never share a constant or a name for
  them internally.
- **SEP text drifts from shipped reality** (SEP-2663 says
  `2026-06-30`; SEP-2575 disagrees with the schema on `clientInfo`).
  When the serve() spec cites the protocol, cite the schema and
  changelog, not SEP prose.

## 9. What this memo feeds

1. **The serve() research-then-ADR pass** (successor to specs 034/054/
   056-Pass-C): era policy (modern-first is now the obvious lean), the
   stack decision (§8.6), and the long-batch execution model (§8.1) —
   the last one is the decision with real design risk.
2. **Spec 045 (verb wire contract)**: JSON Schema 2020-12 pinning,
   protocol-owned params, error-code lanes (§8.3).
3. **The read-family cursor question** deferred from spec 093: handle
   etiquette per SEP-2567 (§8.2).
4. **ADR 022 ratification**: refreshed citation and wording (§8.4).

Sources: [2026-07-28 changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog) ·
[announcement](https://blog.modelcontextprotocol.io/posts/2026-07-28/) ·
[MRTR pattern](https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/mrtr) ·
[extensions overview](https://modelcontextprotocol.io/docs/extensions/overview) ·
reference checkouts as cited inline.
