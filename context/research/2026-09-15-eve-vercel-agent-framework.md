# eve (Vercel): the agent-is-a-directory framework, and whether it is a vfs consumer

- **Status**: research memo (commits us to nothing; feeds the `serve()`
  re-spec, the vfs-js open question, the memory/skills story, and the
  positioning refresh under ADR 058)
- **Date**: 2026-09-15
- **Owner**: Clay Gendron
- **Question**: Vercel launched **eve** in June 2026 as "the open framework
  for building agents", calling it *filesystem-first*. Four questions.
  (1) What is it and how does it actually work? (2) What principles
  underlie it? (3) How is Vercel positioning it, and what does the launch
  say about where the industry is converging on how agents get built?
  (4) Clay's instinct: something like eve could be a *consumer* of vfs.
  Is that right, and where exactly would it plug in?
- **Method**: fresh clone of `vercel/eve` into `~/Git/Repos/eve` (upstream
  default branch `main`, commit `23e2e7c`, 2026-09-15, tag `eve@0.55.0`
  cut 2026-09-14). Two subagents read the code and docs line by line
  (one on architecture, harness, durability, protocols and dependencies;
  one on files, sandbox, memory, skills, connections, auth and MCP). A
  third did the outside view: Vercel's own posts and docs, trade press,
  practitioner write-ups, Hacker News, and a survey of peer projects for
  the convergence question. A fourth digested vfs's own standards,
  positioning memos, ADRs 058 and 062 to 068, the live `src/` surface,
  and the new `docs/` on authority. I then read the seams myself
  (`docs/concepts/state.md`, `docs/memory/*`, `docs/connections/mcp.mdx`,
  `docs/sandbox.mdx`, `docs/concepts/security-model.md`,
  `docs/guides/session-context.md`, `research/first-class-memory.md`).
  Cites and describes only; every line of vfs code stays ours. Web
  numbers (stars, downloads, Vercel's internal-agent counts) are
  vendor-reported or same-day API reads; treat them as directional.
- **License**: Apache-2.0 (`LICENSE`; `NOTICE` lists the vendored
  code-mode runtime, devalue, quickjs-wasi and QuickJS under MIT). Study
  freely; copy nothing.
- **Sources line**: `vercel/eve` @ `23e2e7c` (2026-09-15). 1,395 commits
  since the first commit on 2026-06-16; ten authors carry most of it.
  `packages/eve/src`: 2,505 TypeScript files, 502k lines, of which 252k
  are tests (half). Public numbers on 2026-09-15: 5,149 stars, 546
  forks, 57 contributors, 852 open issues, ~673k npm downloads/week.
  Sub-reports with file:line citations are in the session scratchpad
  and were the basis for every claim below; the web sources are listed
  in §10.

---

## 1. Bottom line

**eve is Next.js for agents, and it means that literally.** An agent is a
directory. `instructions.md` is the system prompt. A file under `tools/`
is a tool, named by its filename. A file under `skills/` is a skill,
under `channels/` a front door, under `schedules/` a cron job, under
`memory/` a memory slot, under `connections/` an MCP or OpenAPI server.
eve walks that directory at build time, compiles it into a manifest, and
runs it as a durable workflow where every model call is a checkpoint.
The framework's own defaults are files in the same grammar, so a user
replaces a built-in by writing a file at the same path. That is the
whole idea, and the Vercel team is disciplined about saying it the same
way everywhere: "the directory is the contract."

**"Filesystem-first" means the authoring surface, not the runtime data
model.** This is the finding that matters most for vfs. At runtime an
eve agent does not read its own `agent/` tree. It reads and writes a
per-session **sandbox** at `/workspace` through `read_file`,
`write_file` and `bash` (with `glob` and `grep` as opt-in shell-outs to
ripgrep). That sandbox has **no per-path permissions, no versioning, no
index, no shared namespace across agents or tenants, and no mount
abstraction**, and eve's own docs tell you it is lossy: "Persist
important artifacts outside the sandbox." Durable state lives in the
workflow journal (typed `defineState` slots), and long-term memory lives
in a *provider* behind a small, principal-scoped interface. The default
memory provider is one bounded `MEMORY.md` document per scope in Vercel
Blob.

**Clay's instinct is right, with one precise correction.** eve can be a
consumer of vfs, but not as its filesystem. The two clean seams are:

1. **An MCP connection.** `defineMcpClientConnection` points an agent at a
   remote MCP server; the model discovers its tools through
   `connection_search` and calls them as `vfs__read`, `vfs__glean`, and
   so on. eve layers a tool allow-list and approval policies on top, and
   per-caller auth resolvers can forward the verified principal
   (`ctx.session.auth.current`) as a bearer token or header. This is the
   most direct path and needs zero code on eve's side.
2. **A memory provider.** `defineMemoryProvider({ recall, capture, tools })`
   is driven at fixed lifecycle points with an opaque per-tenant scope
   key derived from the verified principal. A vfs-backed provider would
   recall via `glean` over a per-scope subtree and expose `save`,
   `search`, `forget` as tools. eve owns *when*; the provider owns
   storage, ranking, retention. That split is exactly the access-layer
   posture vfs already holds.

The sandbox itself is not a seam. The `SandboxBackend` contract requires
running shell commands, so a database-backed namespace cannot *be* a
backend. The only way to make vfs the model's actual `/workspace` is the
just-bash escape hatch (a pure-JS bash over a virtual filesystem), which
is eve's no-binaries fallback, not its production path.

**What blocks it today is on our side, not theirs.** vfs has no `serve()`
in the live tree (the MCP server story was cancelled and is to be
re-specced), and it is Python-only while eve is TypeScript. Both eve
seams talk HTTP, so neither needs vfs-js; they need a served vfs. The
practical consequence of this memo is that the `serve()` re-spec should
be written against a concrete consumer, and eve is a good one: MCP
`2026-07-28` with stateless `2025-11-25` compatibility (the version eve
itself serves), a small tool surface found by description, structured
content, and a replay-stable idempotency key per call (eve supplies one).

**On convergence.** The industry has converged on four things, and eve is
the loudest statement of the first: *the agent sees a filesystem; the
operator runs a database; tools and data arrive over MCP; identity is
attested at a boundary the agent cannot reach.* Four independent teams
(LangSmith on Postgres, Cloudflare Computer on SQLite, MongoDB's VFS for
deep agents on Atlas, Letta MemFS on git) rebuilt "filesystem the agent
sees, database the operator runs" in the last year. That is vfs's exact
shape, so the category is real and getting crowded. Every one of them
defers per-path permissions tied to a principal, versioning with audit,
and search inside the tree to "the application". Those are the three
things vfs's one-sentence pitch names. What is *not* converging is the
Next.js move itself: extending file conventions from context to *wiring*
(tools, channels, schedules as files the framework compiles) is eve's
own bet, and its peers still register those in code.

One-line version: eve authors agents as directories and runs them as
durable workflows; its runtime files are an ephemeral sandbox; vfs plugs
in as an MCP connection or a memory provider, and the thing that stops
that today is that vfs cannot yet be served.

---

## 2. What eve is

### 2.1 The facts

eve is an open-source TypeScript framework from Vercel for building,
running and scaling agents, announced 2026-06-17 at Vercel Ship London
and published under Apache-2.0 the day before. It ships as one npm
package, `eve`, plus a CLI (`npx eve@latest init`). The monorepo holds
the framework (`packages/eve`), a private integration catalog
(`packages/eve-catalog`), a self-modification shim
(`packages/eve-self-modification`), an adapter for the Buzz messenger
(`packages/eve-buzz-acp-adapter`), a docs site, templates, fixtures,
end-to-end suites, and 25 design notes under `research/`.

The velocity is the roadmap. `eve@0.10.0` shipped on 2026-06-16;
`eve@0.55.0` on 2026-09-14. That is roughly 45 minor versions in 13
weeks. The notable additions since launch are memory as a provider
interface (September), self-modification promoted out of experimental,
a registry with `eve add`, eve as an MCP *server*, ACP support for Zed,
and per-session dollar limits that pause for approval.

Vercel says it runs "more than a hundred" and elsewhere "hundreds" of
its own agents on eve, names several (a data analyst, a lead-routing
agent, a support agent), and says agents went from under 3% to around
29% of its deployments in a year. All of that is vendor-stated.

### 2.2 The directory grammar

The team's phrase is "an agent is a directory". The grammar, from the
getting-started doc and the discovery code:

| Slot | What it is | Notes |
|---|---|---|
| `instructions.md` (or `.ts`, or a directory) | the always-on system prompt | required on the root agent |
| `agent.ts` | `defineAgent({ model, … })` | optional; the default is one line |
| `tools/<name>.ts` | a typed tool (`defineTool` with a Zod schema and `execute`) | name comes from the path |
| `skills/<name>.md` or `skills/<name>/SKILL.md` | a procedure loaded on demand | Anthropic Agent Skills format |
| `connections/<name>.ts` | a remote MCP server or OpenAPI document | tools appear as `<name>__<tool>` |
| `channels/<name>.ts` | a front door: HTTP, Slack, Discord, Teams, Telegram, MCP, ACP | root only |
| `schedules/<name>.ts` or `.md` | a cron job | root only |
| `subagents/<id>/` | a nested agent with the same grammar | nestable |
| `memory/<slot>.ts` | a memory slot bound to a provider and a scope | added Sept 2026 |
| `hooks/`, `sandbox/`, `lib/`, `extensions/`, `instrumentation.ts` | observers, the one sandbox, helper code, mounted packages, OTel | |

Names are derived from paths and never declared twice. Location is the
only registration: "Its location under `subagents/` is the only thing
that marks it as a subagent."

### 2.3 The one-sentence positioning, in Vercel's words

"Like Next.js for web apps, but for agents." "An agent is a directory."
"The directory is the contract." "Markdown for instructions and skills,
TypeScript for tools. Durable by default." "Agents today are where the
web was before frameworks, with everyone hand-rolling the same
plumbing." Guillermo Rauch: "I built Next with a simple premise:
pages/index.js is all you need," and eve reduces that to
`agent/instructions.md`.

---

## 3. How it works

This section is mechanism, not marketing. Each subsection ends with the
one fact that matters for vfs.

### 3.1 Authoring compiles; it does not run

`discoverAgent` is one linear walk of `agent/` that never imports
authored code. It emits a source manifest; `compileAgent` normalizes each
slot and writes a versioned manifest under `.eve/`. TypeScript
definition modules are *evaluated at compile time*; static things
(instructions, skills, prompt-form schedules) become manifest data, and
only executable things (tools, channels, hooks, memory, dynamic
resolvers) stay as runtime entries.

The design move underneath is what eve calls **programmatic agent
sources**: a logical path selects a slot and derives its public name; a
separate *binding* says how to load it. The framework's own defaults
(`agent.ts`, `sandbox.ts`, `tools/bash.ts`, `tools/read_file.ts`,
`channels/eve.ts`, …) are registered as ordinary sources at canonical
logical paths, so authoring `agent/tools/agent.ts` with `disableTool()`
removes the built-in. The team's slogan for this is "`eve` can be built
with `eve`."

The `define*` helpers are near-identity functions that exist for typing
and a brand. `defineAgent` and `defineSchedule` literally return their
argument; only `defineChannel` builds something.

*For vfs*: the authored tree is a build input on real disk. Nothing in
eve reads it as a live data store, so "eve's agent directory lives in
vfs" is not an integration; it would be a build-time loader. eve's
"logical path vs physical binding" is the same separation vfs makes
between a mount path and its backend.

### 3.2 The harness: the AI SDK with its loop switched off

eve uses the Vercel AI SDK's `ToolLoopAgent` but sets it to stop after
one step. eve owns the multi-step loop so each step can be a workflow
checkpoint. A step function returns one of three things: another step
(continue), `null` (park and wait for a human or a message), or done.
The loop continues while the last message is a tool result.

The system prompt is assembled in a fixed order: system-role
instructions, a workspace block naming what `bash` can see, a
parallel-actions note, a subagent-messaging note, a `## Connections`
section, and one line per skill. Tool descriptions never enter the
string; they travel as the SDK tool set. Memory recall and dynamic
user-role instructions enter the *message* array, never the system
slot. Compaction fires at 90% of the model's context window: first it
truncates older tool results above 2,000 characters, then it runs a
temperature-0 "context checkpoint" summary that *updates* the previous
summary rather than replacing history.

Skills are progressive disclosure, exactly: every skill is one line in
the prompt; the model calls `load_skill`; the body arrives as a tool
result. "Active skill instructions are never injected into the system
prompt."

*For vfs*: eve's context discipline ("put information in the narrowest
surface that needs it") is the reason a vfs served over MCP should
return small, paged results and let the tree's metadata (sizes, names,
description lines) do the disclosure work.

### 3.3 Durability: every step is a Vercel Workflow checkpoint

eve's nouns are session, turn, step, task. Each is a Vercel Workflow SDK
run or a step inside one. A session is one long-lived workflow run whose
run id *is* the session id. A turn is a child run. A step is one model
call plus the inline tool calls it triggers. The **entire session
snapshot** (history, `defineState` slots, sandbox reconnect metadata,
limits) rides inside every step result. "Workflow step results are the
atomic persistence boundary for session program memory." There is no
eve-owned database.

Where the journal lives is the Workflow "world": `world-local` is plain
JSON files under `.eve/.workflow-data`; `world-vercel` is Vercel's
hosted service; `world-postgres` or any `createWorld()` package is
pluggable. The Workflow SDK is vendored into eve, not a peer.

Approvals and questions park the run and hold no compute. The tool loop
emits `input.requested` and returns `null`; the driver blocks on a
durable hook; a later `POST /eve/v1/session/:id` with `inputResponses`
(or a Slack button click) resumes the hook. Channel addresses *are*
workflow hook tokens.

eve's own `turn-performance.md` is an honest 900-line accounting: about
3.1 s per turn on hosted Workflow, 86% of it outside the model call, and
a run-per-turn prototype that cut p50 by 63% but "cannot ship because
it loses live-deployment, cancellation, and runtime-wait semantics."

*For vfs*: durability is orthogonal to us and we should not build it.
The obligation it imposes is that vfs must be safe to call from a
*replayed* step: idempotent or version-conditioned writes. eve hands
every remote tool call a replay-stable `callId` for exactly this. The
open `serve()` question about re-issued 10k-file writes is the same
question from our side.

### 3.4 Files at runtime: the sandbox, and what it lacks

Every agent has exactly one sandbox per durable session, rooted at
`/workspace`. The model reaches it through `bash`, `read_file`,
`write_file`, and opt-in `glob`, `grep`, `sleep`. The tools live in the
trusted app runtime and *proxy* into the sandbox; the sandbox has no
`process.env` and no path back. Backends: Vercel Sandbox (Firecracker
microVM) when hosted on Vercel, else Docker, else microsandbox, else
just-bash (pure-JS bash over a virtual filesystem under
`.eve/sandbox-cache/`). Custom backends are public: `{ name, create,
prewarm }` returning a session that must implement `run`/`spawn`,
`readFile`, `writeFile`, `removePath`, `resolvePath`.

Now the absences, each verified in the code:

- **No permission model on paths.** Path handling is `$HOME` expansion
  plus "must start with `/`". The docs' answer is to wrap `write_file`
  in a hand-written prefix check. No allow/deny lists, no read-only
  roots, no principal on the sandbox session.
- **No versioning.** `read_file` stores a SHA-256 stamp; `write_file`
  refuses to overwrite a file that was never read or that changed since.
  That is stale-write hygiene, not history. Nothing records prior
  content; there is no revert. The docs say sandbox loss is lossy by
  contract and to "persist important artifacts outside the sandbox."
- **No index and no ranked search.** `glob` and `grep` shell out to
  `rg`, `find`, or `grep`. Lexical only.
- **No `stat`, `readdir`, `exists`, `rename`, or edit primitive.** A
  code comment notes that adding `exists()` "would require a sandbox
  session API change." There is no `edit_file` in the framework set;
  `write_file` takes complete contents.
- **No shared namespace.** One sandbox per agent per session; a subagent
  may opt in to its parent's. `defineState` "is never shared with
  subagents." Skills are per agent.
- **No cross-source mounts.** The only mount abstraction is a just-bash
  `MountableFs` used internally by self-modification (`/source` over
  `agent/`, read-only overlays for traces, logs and docs). External data
  is reached as *tools* through connections, never presented as files.
- **No typed relations.** Nothing resembling edges anywhere in `docs/`,
  `research/` or `src/` for agent data.

"Code mode" is not a file sandbox either. The QuickJS/WASI runtime in
the NOTICE backs a single `Workflow` tool that runs a model-written
JavaScript orchestration program over subagent calls.

*For vfs*: this is the gap list. Every item is something vfs has or has
designed, and eve's docs already tell users to solve the first two
outside eve.

### 3.5 Memory: the seam that fits best

A memory **slot** is a file (`agent/memory/<slot>.ts`) that binds a
provider to an eve-resolved namespace and scope. eve drives the provider
at fixed points: `recall` on `turn.started` (required) and after
compaction; `capture` on `turn.completed` and before compaction;
`tools()` once per turn after recall. eve owns slot names, scope
resolution, timing, attribution and supersession of recalled messages,
and tool qualification (`<slot>__<tool>`). The provider owns "storage
and indexing, retrieval, ranking, and formatting, what to extract,
retention and deletion." The docs say it plainly: "Anything that can
read and write under that key can be a memory provider: a Postgres
table, a vector index, a key-value store, or an HTTP API."

The provider contract, exactly:

- `recall["turn.started"](ctx) → { messages: [{ content, id? }] } | null`.
  A message with an `id` inserts or replaces; without one it appends.
  "Recall cannot retract, only supersede."
- `capture["turn.completed"](ctx) → void`, with `ctx.messages` (projected
  history) and `ctx.operationId` (a replay-stable idempotency key).
- `tools(ctx) → map of defineTool() values`.
- Every handler gets `ctx.memory.scope.key`, an opaque versioned SHA-256
  digest of namespace and scope, and must partition every read and
  write by it. "The model never supplies or changes the key."

Scope is author-chosen. `byPrincipal` returns `null` for anonymous and
runtime principals and otherwise a tuple of principal type,
authenticator, issuer and id. The multi-tenant pattern returns
`[tenantId, principal]` from *verified* session auth and disables memory
when it cannot. Recalled content enters model context as **user-role**
messages attributed to the slot, "never as system instructions."

The default provider, `fileMemory()`, keeps one bounded `MEMORY.md` per
scope in Vercel Blob with etag compare-and-swap (64 KiB document, 2 KiB
entries, 4,000 recalled chars), offers only `save_memory` and
`remove_memory`, and does no automatic capture. The document "lives in a
backend, not in the agent's sandbox filesystem." Third-party providers
(Supermemory, Upstash, Kybernesis, a Mem0 template) add semantic recall
and auto-capture. Cross-provider search and administrative APIs are
explicit non-goals in the 1,300-line design note.

*For vfs*: this is the interface a vfs memory provider implements. A
scope key maps to a subtree; recall is `glean` scoped to it; capture is
a `write`; the tools are `save`, `search`, `forget`. vfs's `Authority`
carries the same identity eve's scope tuple carries.

### 3.6 Connections, principals, and MCP in both directions

A **connection** is a file under `agent/connections/` wrapping a remote
MCP server (Streamable HTTP or SSE) or an OpenAPI document. "The model
never sees a connection's URL or credentials." It discovers tools
through `connection_search`, keyed on the connection's description, and
calls them as `<connection>__<tool>`. Per connection you get a tool
allow-list or block-list ("prefer `allow` for the smallest safe
surface"), an approval policy (`never()`, `once()`, `always()`, or a
custom function over `{ session, toolName, toolInput }`), and
application-provided arguments that eve strips from the model-facing
schema and injects before execution.

Auth is one of: a static `getToken`, `headers`, per-caller resolver
functions that read the session, or interactive OAuth through Vercel
Connect. Tokens are "cached per step and never serialized to durable
state."

A real **principal** flows through every run. Route auth stamps a
`SessionAuthContext` (`principalId`, `principalType` of user, app or
runtime, `authenticator`, `issuer`, `attributes`) onto the session;
tools and resolvers read `ctx.session.auth.current` (the active turn's
caller) and `auth.initiator` (who started the session). Schedules run as
the framework principal `eve:app`. User-scoped connections fail with
`principal_required` if the caller is not a user. Identity crosses
remote-agent hops only as metadata, opt-in, never as tokens.

eve also **serves** MCP: `mcpChannel` at `/eve/v1/mcp` exposes
`agent_start`, `agent_get`, `agent_update`, `agent_cancel`, on spec
`2026-07-28` with stateless `2025-11-25` compatibility, so Claude Code
and peers can delegate durable work to an eve agent.

"Passport" appears nowhere in the repo. It is a Vercel platform product
(an OIDC gate in front of deployments); eve meets it only through
Vercel's Trusted Sources.

*For vfs*: the connection is the front door. The principal eve carries
is the one vfs's `Authority` wants, and eve's docs already show the
per-caller header resolver that forwards it. eve's allow-list and
approval gates give vfs mutations a human-approval front before vfs's
own `pending` kind exists.

### 3.7 Self-modification, extensions, protocols

Self-modification is a declared subagent that edits the agent's *own
authoring directory*: locally through a just-bash mount of `agent/` at
`/source`; when deployed, by cloning the repo into a sandbox and opening
a **draft GitHub PR** that is never merged automatically. Extensions are
npm packages with an `extension/` tree in the same grammar, mounted
under a prefix; they cannot own memory, sandbox or agent config. ACP is
Zed's Agent Client Protocol served over stdio; UCP is a commerce profile
at `/.well-known/ucp`; Buzz is a Nostr messenger bridged through ACP.

### 3.8 Portability, honestly

The package has exactly two runtime dependencies (`nitro`, `undici`);
everything else, including the Workflow SDK, `@vercel/sandbox`, the MCP
server SDK and just-bash, is vendored or a peer. The AI SDK is a hard
peer. Self-hosting is `eve build && eve start`: a Node 24 service with a
local-file or Postgres workflow world and Docker, microsandbox, just-bash
or custom sandboxes. What you lose off Vercel: the Agent Runs dashboard,
Vercel Connect OAuth brokering, AI Gateway OIDC, microVM sandboxes, and
Cron. The root `package.json` describes eve as "for durable backend
agents on Vercel"; the published package says "run anywhere." Both are
true of different layers.

---

## 4. Core principles

Quoted or paraphrased from `AGENTS.md` (which `CLAUDE.md` includes),
`docs/README.md`, and the research notes, in the order the code
enforces them:

1. **The filesystem is the authoring interface, and defaults are files
   too.** "Derive names from file paths." "Every ordinary framework
   default is a first-class eve primitive at a canonical logical path."
2. **Docs are the product, because agents read them.** "Docs is priority
   #1. Agents read your docs before they ever touch your product." The
   docs ship inside the npm tarball at `node_modules/eve/docs`, and the
   repo's own `SKILL.md` tells coding agents to read them. "Your errors
   are documentation."
3. **A lean core that can build itself.** "The core should expose hooks
   and internal APIs so that broad functionality is built on top of it."
   "Code is liability."
4. **Wrap every third party; own the surface.** "Do not expose
   third-party APIs as eve public APIs." Runtime dependencies "only as a
   last resort."
5. **Pre-1.0: break, don't shim.** "Favor correctness and simplicity over
   backwards compatibility. No legacy fallback logic." The design notes
   repeat it: "never both," "no backwards fallback."
6. **Durability is the differentiator, and it is measured.** Every model
   step is a checkpoint by default; non-idempotent tools are the
   author's problem; wire payloads outlive deployments; the cost is
   accounted for in a 900-line note.
7. **Context in the narrowest surface.** System vs user role split,
   skills on demand, sandbox files instead of pasted context, subagents
   as separate contexts.
8. **Secrets never reach the model.** Two contexts with a trust boundary;
   file tools proxy into the sandbox; connection credentials are
   invisible to the model.
9. **Ship with a disclaimer, not a guardrail.** "Unless you configure
   stricter controls, eve agents may operate with permissive settings."
10. **Research → decide → implement, in-repo.** Public API changes
    "usually require a research doc"; `research/` notes carry
    `issue`/`status`/`last_updated` frontmatter.

Principles 2, 5 and 10 are ours too. Principle 9 is the opposite of
vfs's posture on the data path, and it is the opening.

---

## 5. How Vercel positions it, and how it landed

### 5.1 The Agent Stack in a folder

Three days after eve, Vercel's CTO published "the Agent Stack": a model
layer (AI SDK, AI Gateway as "a CDN for tokens"), a workflow execution
layer (Workflow SDK, Vercel Sandbox), and a data and tool integration
layer (Vercel Connect minting "short-lived, scoped tokens", Chat SDK),
with eve as "an opinionated, open-source implementation of the Agent
Stack in a single directory." Fluid Compute, Cron, Instant Rollback and
Agent Runs observability round it out. Passport (OIDC in front of every
internal app and agent) launched the same week. The framework is free;
"eve usage is billed through the Vercel resources and third-party
services your agent uses."

Vercel set the thesis up over the preceding year: the Workflow
Development Kit (October 2025, "durability as a language-level
concept"); skills.sh and the "Agent skills explained" FAQ (January
2026); the eval post "AGENTS.md outperforms skills" (an always-on 8 KB
index scored 100% vs 79% for on-demand skills, which is exactly eve's
`instructions.md` vs `skills/` split); Skills Night (69,000 skills, 2M
CLI installs); and Vercel Sandbox GA as "the execution layer for
agents." Rauch's strategic frame, in a July TechCrunch interview, is
decoupling: the agent layer should be a portable framework you get from
someone other than the model vendor.

### 5.2 Reception

Trade press was warm and descriptive (The Register, InfoQ, The New
Stack, LogRocket, MarkTechPost). InfoQ placed eve "alongside LangGraph,
CrewAI, AutoGen, and Strands" and quoted both a "looks like Claude Code
but multi-tenant" reaction and "I don't get what this is changing."

Practitioners who deployed it said yes with a lock-in caveat. One
running nine agents: "the gap between 'I wrote a tool' and 'the model
can call it' is gone," but it is "tightly coupled to
Workflows/Sandbox/Connect," pre-release dependencies broke, and delivery
can fail "without a signal." A studio with five agents: "eve absorbed
everything that used to be bespoke infrastructure, and left us with the
part that's actually ours, the rules." Infisical: the default `.env`
pattern means "the agent holds a live secret," and local durability
"doesn't persist." A memory vendor noted memory happens "around the
turn, not inside it." Comparison pieces frame the choice as "Mastra for
portability, eve for Vercel-native speed and DX."

Hacker News was indifferent: every launch thread scored four points or
fewer, and the largest eve thread (a "software factory" template, ten
points) drew "vercel just pumping out slop." No Reddit threads
surfaced. No Vercel staff engaged on HN. eve's audience is Vercel's
developer base and the agent-tooling press, not the HN crowd.

### 5.3 Adoption, measured today

| Project | GitHub stars | npm weekly downloads |
|---|---|---|
| vercel/eve | 5,149 | 673k |
| mastra-ai/mastra | 28,065 | 1.24M |
| cloudflare/agents | 5,572 | 1.23M |
| openai/openai-agents (JS) | 29,454 | 1.29M |
| anthropics/claude-agent-sdk (JS) | 8,100 | 8.97M |
| langchain-ai/deepagents | 29,442 | |
| openclaw/openclaw | 389,754 | |

Read: three months old, a fifth of Mastra's stars, half its npm volume,
driven by Vercel's distribution. Users beyond Vercel are small teams,
memory vendors shipping providers, and one third-party IDE. A blog
claiming 16,000 stars is wrong.

---

## 6. What eve says about convergence

Grades: **real** (multiple independent vendors, a spec or foundation),
**emerging** (several vendors, no standard), **mostly Vercel**.

| # | Candidate convergence | Grade | Evidence beyond eve | What it means for vfs |
|---|---|---|---|---|
| 1 | The filesystem is the agent's context and memory interface | **real** | Agent Skills (~45 clients); AGENTS.md (60k repos, now under the Linux Foundation's AAIF); Claude Code's CLAUDE.md, rules and `MEMORY.md`; Anthropic's context-engineering essay ("file paths… as lightweight identifiers"); Manus ("the file system as the ultimate context"); Letta MemFS (memory in a git repo, tree in the prompt as "signposts"); OpenClaw's workspace of markdown files; LangChain deep agents' virtual FS with per-path allow/deny; LangSmith storing that FS in Postgres; MongoDB's VFS for deep agents; Cloudflare Computer (FS in SQLite in a Durable Object); Anthropic Managed Agents memory mounted at `/mnt/memory` with per-write versions; Mastra Workspaces | The interface thesis is won. Four teams independently put a database under the tree. The category is crowded; the differentiators are the ones those teams defer to "the application": per-path permission tied to a principal, versioning with audit, search inside the tree. |
| 1b | The *whole agent* (tools, channels, schedules) is a directory the framework compiles | **mostly Vercel** | Peers use directories for instructions, skills and memory; Mastra, LangGraph, OpenAI Agents SDK and Cloudflare's `Agent` class define tools and durability in code | vfs can host this shape (a subtree per agent) but should not compete with it. The `/.agents/{tools,skills}` families already match the halves that *are* converging. |
| 2 | Progressive disclosure: skills loaded on demand | **real** | The Agent Skills three-stage load; Claude Code path-scoped rules and 200-line `MEMORY.md`; Claude Agent SDK tool search on by default; Letta's self-managed disclosure; Vercel's own eval that always-on rules beat skills for every-turn facts | Disclosure is a property of the tree. An `ls`/`stat` that returns size, mtime and a description line is what these clients are tuned for. |
| 3 | Durable execution as the substrate for long-running agents | **real** on the idea, none on a standard | Temporal's OpenAI Agents integration; Inngest, Restate, DBOS; Cloudflare Workflows; LangGraph checkpointers; Vercel Workflow | Do not build it. Be safe to call from a replayed step: idempotent or version-conditioned writes. |
| 4 | Sandbox by default; "code mode" replacing tool calls | **real** (sandbox) / **emerging** (code mode) | E2B, Modal, Daytona, Cloudflare Sandbox, Vercel Sandbox; Cloudflare Code Mode (1.17M tokens to ~1,000); Anthropic "code execution with MCP" (tools as files on a filesystem); Managed Agents split "brain from hands" | eve keeps typed tools plus bash and does not adopt code mode. Anthropic's code-mode pattern is itself a filesystem pattern: tools become files the model browses, which is what `/.agents/tools/<name>/TOOL.md` already is. |
| 5 | Approvals and agent identity as first-class | **real** (approvals) / **emerging→real** (identity) | LangGraph `interrupt()`, Temporal parking, Cloudflare HITL; MCP Enterprise-Managed Authorization (ID-JAG) stable since 2026-06; Okta Agent SSO GA 2026-08; Auth0 for AI Agents; SPIFFE at MCP gateways; Cloudflare credential injection at a proxy; Vercel Passport and Connect; eve's `byPrincipal` | Identity is converging on the same shape: agent as a first-class principal, short-lived delegated tokens, credentials injected where the agent cannot reach. vfs's "the host verifies the token, builds the `Authority`" is that shape. Audit formats are still per-vendor; versioning is the audit sink everyone lacks. |
| 6 | MCP as the tool and data plane | **real** | MCP under the Linux Foundation (AWS, Anthropic, Block, Cloudflare, Google, Microsoft, OpenAI); 10,000+ servers; every SDK consumes it; eve consumes *and* serves it; the code-mode camp changes presentation, not the wire | MCP is the right serving surface. Target `2026-07-28` with stateless `2025-11-25` compatibility. Clients doing tool search or code mode want a small stable tool surface plus something to browse. |
| 7 | Memory as a provider interface | **emerging** | Mem0, Zep, Letta, Supermemory, Cognee adapters; Mastra's pluggable memory; Microsoft Agent Framework's before/after-run context provider; a deep agents `MemoryProvider` proposal; eve's recall/capture/tools contract | Two live designs: provider-hook (recall before the turn, capture after) and filesystem (the agent reads and writes memory with file tools). A permissioned, versioned, searchable tree serves both, which is a stronger position than either a memory API or a file store. eve's default provider is literally a file. |

The one-line version of the convergence: *the agent sees a filesystem;
the operator runs a database; tools arrive over MCP; identity is
attested at the boundary.* eve is the loudest statement of the first
clause. The parts eve leaves ephemeral are exactly vfs's product.

---

## 7. Could eve be a consumer of vfs? My opinion

Yes. Not as its filesystem. As its **data layer behind two seams it
already exposes**, carrying the principal it already has. Here is the
argument in three parts: where it plugs in, what stops it today, and
what each side would get.

### 7.1 The seams, ranked

| Rank | eve seam | What vfs would be | Effort on eve's side | Verdict |
|---|---|---|---|---|
| 1 | **MCP connection** (`agent/connections/vfs.ts`) | One remote MCP server; the model finds `vfs__read`, `vfs__glob`, `vfs__grep`, `vfs__glean`, `vfs__write`, `vfs__edit`, `vfs__delete`/`restore` by description; eve's `tools.allow` and approval policy sit on top; a per-caller `auth`/`headers` resolver forwards the verified principal | none; it is authored config | **the front door.** Zero eve code. The model gets tools, not `/workspace` paths, so `bash` cannot see vfs. That is fine: the shared, durable, permissioned tree is what the sandbox is *not* for. |
| 2 | **Memory provider** (`agent/memory/vfs.ts`) | `recall` = `glean` scoped to the subtree for `scope.key`; `capture` = `write` keyed by `operationId`; `tools` = `save`, `search`, `forget` | a thin TypeScript package that calls the served vfs over HTTP or MCP | **the best fit conceptually.** eve's split (it owns when, the provider owns storage/ranking/retention) is the access-layer posture. Caveat: recall semantics are accumulate-and-supersede, per slot, per agent. |
| 3 | **Memory document backend** | `read`/`write` one `MEMORY.md` per scope with compare-and-swap on the version stamp | trivial | works today in shape, but stores one bounded document; a demo, not the product |
| 4 | **just-bash `filesystem`** | vfs *as* `/workspace`, via a custom `IFileSystem` | a TypeScript FS adapter over served vfs | the only way to be the model's actual filesystem, confined to the no-binaries fallback backend. Interesting for a demo; not a production path. |
| 5 | **Custom `SandboxBackend`** | vfs paired with real compute, syncing `/workspace` from vfs | large | the contract demands `run`/`spawn` of shell commands; a database-backed namespace alone cannot satisfy it. Not a seam for vfs, by our own constitution (no FUSE, no virtualized bash). |

The **principal handoff** is what makes seams 1 and 2 more than
plumbing. eve carries `principalType`, `principalId`, `issuer`,
`authenticator` and `attributes` (including a tenant id) on every turn,
resolved from a *verified* token, and its docs already show a header
resolver that reads `ctx.session.auth.current` and forwards a
tenant-scoped bearer to an MCP connection. vfs's rule is that the host
verifies the token and builds the `Authority` from the verified subject.
eve is the host. `Authority.of(Principal(sub))` for a user turn;
`Authority.system()` or a service principal for a schedule running as
`eve:app`; `Authority.on_behalf_of({...}, actor=service)` for a
multi-tenant support agent. The shape lines up without an adapter
concept on either side.

### 7.2 What stops it today is on our side

- **vfs cannot be served.** There is no `serve()` in `src/`; the MCP
  server story was cancelled and is to be re-specced. `Result.to_payload()`
  is wire-ready. Until a served vfs exists, a TypeScript framework
  cannot reach vfs at all. This is the single gating item, and it gates
  every framework consumer, not just eve.
- **vfs-js is not needed for seams 1 and 2.** Both talk HTTP. Seam 2
  needs a *thin* TypeScript client package, not a second implementation.
  Seam 4 would need more, and seam 4 is not the product.
- **vfs enforces structure, not principals, today.** Permission is a
  per-mount `PermissionMap` checked on mutating verbs; grants, posture
  and hidden rows are spec 058, written and unimplemented; no write
  path mints a version row yet. So the three differentiators the
  convergence table names (per-path permission tied to a principal,
  versioning with audit, search in the tree) are one-third built (search)
  and two-thirds designed. eve would consume the built third on day one
  and the designed two-thirds as they land.

### 7.3 What each side gets

*eve gets* the thing its own docs tell users to find elsewhere: a
durable, shared, permissioned, searchable, versioned tree that outlives
the sandbox, is visible to many agents and to humans, and answers "who
wrote this, on whose behalf" for audit. Concretely it fills the seven
absences in §3.4. Its memory story gets ranked recall over a real store
with the scope enforced *in the query* (the docs ask for exactly that:
"include the locked scope in the database or service query itself, not
as a filter after a global search"), which is what hidden-row-absent
search statistics are for.

*vfs gets* a consumer with a real principal on every call, an approval
front for mutations before `pending` exists, a replay-stable idempotency
key per call to design `serve()` against, and a test of the "access
layer under someone else's loop" positioning with a framework that is
loud about being the loop.

### 7.4 Risks and honest caveats

- eve is three months old, pre-1.0, breaks on purpose, and its
  organic community is thin. Building *to* eve is not the point;
  building `serve()` so that eve-shaped consumers can plug in is.
- eve's audience is TypeScript. Seam 2 requires us to publish or bless
  a TypeScript package. That is a small, bounded commitment, but it is
  a commitment and it reopens the vfs-js question in a narrower form.
- Memory recall is accumulate-and-supersede and per slot. A vfs provider
  cannot retract a recalled fact within a session; it can only
  supersede it. Fine for facts; awkward for "forget."
- Tool count. `connection_search` finds tools by description, and code-
  mode and tool-search clients want a small surface. vfs's 19 verbs are
  already at the edge. The served surface should be the agent-facing
  subset, and `sweep` and topology admin must stay off the wire (as
  ADR 022 already says).
- The category is crowded (§6, row 1). Cloudflare, MongoDB, LangSmith
  and Letta each own a "database under the tree." What they defer is our
  product; being consumable by their frameworks is the test.

---

## 8. What vfs should take from eve

Design lessons, not code. Each is a pattern eve has that maps onto a
live vfs question.

1. **Version-conditioned writes as the replay contract.** eve's
   read-before-write stamp (hash on read, refuse on mismatch) is the
   minimal thing a durable-execution client needs from a store. vfs
   already carries a per-entry `version` on every observation; the
   served `write` and `edit` should accept an expected version and
   refuse with a classified kind, so a replayed step is safe.
   Feeds the `serve()` execution-model question.
2. **An idempotency key per call.** eve gives remote tools a
   replay-stable `callId` and memory providers an `operationId`. The
   served vfs should accept one and make a re-issued 10k-file write a
   no-op. Same open question.
3. **The opaque scope key.** eve hashes namespace and scope into a
   versioned digest and stores only that in durable state: "never raw
   principal." vfs's audit columns will name actor and subjects; the
   memo notes the alternative of storing a digest for logs that leave
   the database.
4. **Recalled memory is user-role, never system.** eve refuses to let
   retrieved content into the highest-authority slot. When vfs writes
   the how-to for serving skills and memory, it should say the same:
   recalled entries are data, instructions are the host's.
5. **Docs ship in the package, for agents.** eve puts its docs in the
   tarball and its `SKILL.md` says "read `node_modules/eve/docs`." vfs
   already materializes agentskills-conformant `SKILL.md`; the wheel
   should carry the how-to docs the same way. Small, and it compounds.
6. **Logical path vs physical binding, with defaults as ordinary
   sources.** vfs's mount table is this idea; eve's extra step is that
   the framework's own built-ins occupy ordinary paths so a user can
   shadow them. The `/.agents/tools` family could work the same way
   when `run` lands: built-in tools are entries, and a mount can shadow
   them.
7. **Least privilege as an allow-list at the consumer.** eve's
   `tools.allow` is the consumer-side twin of vfs's per-mount
   `deny_ops`. Both should exist; the served vfs should advertise its
   capabilities so the consumer's allow-list can be derived rather than
   typed.
8. **Measure the cost of your differentiator.** eve's
   `turn-performance.md` accounts for what durability costs per turn.
   vfs's equivalent is the permission predicate at scale, already
   researched; the served path should be benchmarked the same way once
   it exists.

---

## 9. Open questions this memo raises

- **`serve()` should be re-specced against a named consumer.** eve is a
  good one: MCP `2026-07-28`, stateless `2025-11-25` compatibility, an
  agent-facing tool subset found by description, structured content,
  expected-version writes, an idempotency key. This sharpens the
  existing open question rather than adding one.
  `[NEEDS CLARIFICATION: does the served surface expose all agent-facing
  verbs as separate tools (eve's connection_search favours few, well-
  described tools) or one tool with a verb argument (the "one MCP tool,
  sixteen verbs" line from the July company memo)?]`
- **A TypeScript client, narrowly.** Seam 2 needs a thin `eve` memory
  provider package that calls a served vfs. That is not vfs-js, but it
  is TypeScript we would own or bless.
  `[NEEDS CLARIFICATION: does vfs publish reference adapters for host
  frameworks (an eve memory provider, a deepagents backend), or document
  the wire and let hosts write them?]`
- **Where an agent's bundle lives in the namespace.** eve's agent is a
  directory. The reserved `/.agents` tree has two families, `tools` and
  `skills`. Hosting an agent-shaped subtree (instructions, skills, memory
  per agent) is either a plain user directory or a third family.
  `[NEEDS CLARIFICATION: is an agent bundle a user-namespace directory,
  or a reserved `/.agents/<agent>/` family with its own path grammar?]`

Pointers for all three are in `context/open-questions.md`.

---

## 10. Sources

Code: `~/Git/Repos/eve` @ `23e2e7c` (2026-09-15), Apache-2.0. Files read
directly: `README.md`, `AGENTS.md`, `NOTICE`, `docs/concepts/*`,
`docs/memory/*`, `docs/connections/mcp.mdx`, `docs/sandbox.mdx`,
`docs/guides/session-context.md`, `docs/patterns/multi-tenant-*.md`,
`docs/channels/mcp.md`, `research/*.md`, and the subagent line reads of
`packages/eve/src/{discover,compiler,framework,harness,execution,
runtime,shared,public,tools,sandbox,subagents,self-modification,acp}`.

Primary (Vercel):
https://vercel.com/blog/introducing-eve ·
https://vercel.com/changelog/introducing-eve-an-open-source-agent-framework ·
https://vercel.com/eve · https://vercel.com/docs/eve ·
https://vercel.com/docs/eve/concepts · https://vercel.com/docs/eve/pricing ·
https://vercel.com/blog/agent-stack ·
https://vercel.com/blog/vercel-for-enterprise-apps-and-agents ·
https://vercel.com/changelog/vercel-passport-generally-available ·
https://vercel.com/changelog/persistent-memory-for-eve-agents ·
https://vercel.com/blog/introducing-workflow ·
https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals ·
https://vercel.com/blog/agent-skills-explained-an-faq ·
https://vercel.com/blog/skills-night-69000-ways-agents-are-getting-smarter ·
https://eve.dev · https://eve.dev/docs · https://github.com/vercel/eve ·
https://www.linkedin.com/posts/rauchg_introducing-eve-activity-7473021460064894976-TpfK ·
https://techcrunch.com/2026/07/06/vercel-ceo-guillermo-rauch-on-the-fight-to-split-off-models-from-agents/

Reception:
https://www.theregister.com/devops/2026/06/19/vercel-debuts-eve-open-source-agent-framework-tries-to-fix-shadow-ai-with-passport/5258726 ·
https://www.infoq.com/news/2026/06/vercel-eve-agents/ ·
https://thenewstack.io/vercel-launches-eve-an-open-source-framework-that-treats-agents-as-directories/ ·
https://blog.logrocket.com/vercel-eve-ai-agents/ ·
https://www.marktechpost.com/2026/06/17/vercel-releases-eve/ ·
https://www.mindstudio.ai/blog/what-is-vercel-eve-framework-file-system-ai-agents ·
https://www.mager.co/blog/2026-06-18-vercel-eve/ ·
https://zackproser.com/blog/is-vercel-eve-worth-it-agent-framework-review ·
https://robotostudio.com/blog/building-agents-on-eve ·
https://infisical.com/blog/eve-support-agent-zero-credentials ·
https://hindsight.vectorize.io/blog/2026/07/06/eve-persistent-memory ·
https://www.bitdoze.com/mastra-vs-eve-typescript-ai-agents/ ·
https://www.cipherprojects.com/blog/posts/vercel-eve-alternatives-2026/ ·
https://news.ycombinator.com/item?id=48576088 ·
https://news.ycombinator.com/item?id=49331599

Convergence:
https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills ·
https://agentskills.io/home · https://agents.md/ ·
https://www.linuxfoundation.org/press/linux-foundation-announces-the-formation-of-the-agentic-ai-foundation ·
https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents ·
https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus ·
https://www.letta.com/blog/benchmarking-ai-agent-memory/ ·
https://www.letta.com/blog/context-repositories/ ·
https://www.langchain.com/blog/how-we-built-agent-builders-memory-system ·
https://docs.langchain.com/oss/python/deepagents/overview ·
https://www.mongodb.com/company/blog/technical/vfs-langchain-deep-agents-searchable-filesystem-agents ·
https://docs.openclaw.ai/reference/AGENTS.default ·
https://code.claude.com/docs/en/memory ·
https://developers.cloudflare.com/changelog/post/2026-08-03-cloudflare-computer/ ·
https://blog.cloudflare.com/code-mode-mcp/ ·
https://www.anthropic.com/engineering/code-execution-with-mcp ·
https://www.anthropic.com/engineering/managed-agents ·
https://sdtimes.com/anthropic/anthropic-adds-memory-to-claude-managed-agents/ ·
https://mastra.ai/docs/workspace/overview ·
https://temporal.io/blog/announcing-openai-agents-sdk-integration ·
https://aaronparecki.com/2025/11/25/1/mcp-authorization-spec-update ·
https://startwithidentity.com/blog/2026-08-24-okta-agent-sso-cross-app-access-general-availability/ ·
https://devblogs.microsoft.com/cosmosdb/native-agent-memory-for-microsoft-agent-framework-powered-by-azure-cosmos-db/ ·
https://github.com/langchain-ai/deepagents/issues/5531

Counts: GitHub star counts via `gh api repos/<owner>/<repo>` and npm
weekly downloads via `api.npmjs.org/downloads/point/last-week/<pkg>`,
both read 2026-09-15.
