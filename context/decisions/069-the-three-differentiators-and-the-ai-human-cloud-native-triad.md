# 069. The Three Differentiators — Governed Mutation, Built-in Search, One Shared Namespace — and the AI-native / Human-native / Cloud-native Triad

- **Status:** proposed 2026-09-17 — drafted from Clay's statement in
  conversation (quoted in Context) after the two 2026-09-15 studies;
  **awaiting Clay's ratification of the wording.** Refines ADR 058
  (the category, the mechanism line, the layer/plane split all stand);
  does not supersede it. Companions: ADR 006 (tenant isolation as a
  permission layer), ADR 013/017 (per-entry revisions), ADR 021 (the
  grant spine), ADR 059 (every supported dialect has a distance
  function), ADR 060 (the default local embedding model), ADR 062–067
  (authority, versions naming actor and subjects, hidden rows, the
  subject set, the enforcement spine), ADR 068 (open by default).
- **Date:** 2026-09-17
- **Deciders:** Clay Gendron
- **Decided by:** human — the three differentiators and the triad are
  Clay's; Claude drafted the record and the built/designed honesty
  lines under each.
- **Context source:**
  `../research/2026-09-15-eve-vercel-agent-framework.md` (Vercel's eve,
  the industry convergence table, eve as a consumer of vfs) and
  `../research/2026-09-15-filesystem-over-database-landscape-and-vfs-differentiation.md`
  (the four category peers on one rubric, fourteen adjacent systems,
  the ranked differentiation, the Arize counter-argument). Both stand
  on ADR 058's positioning memo,
  `../research/2026-08-27-agent-access-layer-positioning.md`.

---

## Context

ADR 058 fixed the category ("the access layer for agents"), the
mechanism line (the namespace), and the stack line (frameworks build,
control planes set policy, gateways check the call, vfs enforces on the
data). It did not say *why a buyer picks vfs over another system that
also gives an agent a filesystem over a database*, because in August
that comparison did not yet need making.

By September it does. The two studies found that the category has
converged on the two things vfs used to lead with:

- **The verb set is universal.** read, write, edit, ls, glob, grep. Deep
  agents, Cloudflare Computer, MongoDB's VFS, Letta MemFS, Mastra
  Workspaces, Anthropic's Managed Agents memory, the Claude memory tool,
  and eight smaller projects all expose it within a name or two.
- **"Over a database" is a slot value, not a design.** Box says it
  plainly: a filesystem "is an interface contract." Deep agents, Mastra,
  Mirage and the Claude memory tool make the store pluggable. LangSmith
  puts it in Postgres, Cloudflare in SQLite inside a Durable Object,
  MongoDB in Atlas, Letta in git.

What did *not* converge is what the database is for. Every peer uses it
as a disk: a durable place for bytes that outlive the sandbox. A few use
it as an index. None uses it as a gate. Three of the four wrote the
deferral down: MongoDB, "access control, tenant isolation, data
residency, retention, and audit requirements should be enforced through
the application"; LangChain, "Direct backend usage does not currently
incorporate permissions"; Cloudflare, "treat workspace files as
agent-local scratch, not shared mutable state." Letta's row-level access
predicate discards its `access` argument and filters on organization
alone. Tenancy everywhere is "one store per principal" (one Durable
Object per tenant, one memory store per user, one namespace tuple per
user, one git repo per agent), which cannot express a document shared by
two callers with different rights.

Clay's statement of the differentiation, in conversation on 2026-09-17:

> 1. Permissions with versioning and reversibility. Every file mutation
>    that originates from VFS goes through our write/edit methods so an
>    agent cannot mutate the file system in a corruptable way.
>    Additionally, everything runs through permissions so it is easy to
>    scope permissions by person or agent to dynamically control access
>    while working with many agents at once.
> 2. Search indexes built in that scale. We have glob, grep, bm25
>    (glean) and graph that work out of the box with no tuning needed
>    (later we can add in all the knobs).
> 3. Cloud native and multi user. VFS is built around being run in the
>    cloud and servicing multiple clients and users at once. It is easy
>    to let everyone in the enterprise share and use the same
>    filesystem.
>
> VFS is AI native (cli and search indexes along with permissions),
> human native (familiar abstraction for storing data and information
> and navigation), and cloud native (db backed and async/fastapi ready).

The research memo had ranked five differentiators (authority in the
statement; one namespace with many principals; versioned attributed
writes; search as a property of the tree; production scale as a
contract; plus runtime independence as a conditional sixth). Clay's
three fold those into the shape a buyer hears, and the triad names the
three audiences.

## Options considered

- **A. Keep ADR 058 as the whole positioning.** Category, mechanism,
  stack line, nothing about peers. *Pro:* nothing new to ratify. *Con:*
  the category no longer distinguishes vfs from a system that also says
  "filesystem for agents over a database"; the first question in any
  comparison is unanswered.
- **B. The memo's five ranked differentiators, as written.** *Pro:*
  each is tied to peer evidence and a built/designed status. *Con:*
  five is a list a reader forgets; two of the five (scale contract,
  runtime independence) are proof points for the others, not headlines.
- **C. Clay's three differentiators plus the triad, with the memo's
  built/designed honesty attached to each.** *Pro:* three memorable
  claims that each map onto a real gap every peer left open; the triad
  gives each audience its line; the honesty lines keep ADR 058 pin 7
  ("positioning points where we are going; the README says what is
  real"). *Con:* two of the three are ahead of the tree today, so the
  honesty lines are load-bearing.

## Decision

We chose **C**.

1. **Differentiator one: governed mutation.** *Every mutation goes
   through vfs's own write and edit, under the permission check, and is
   versioned and reversible.* There is no shell, no side door, and no
   "direct backend usage": the check runs on the storage call, for
   every caller, so a custom tool, an MCP client, and a bulk loader get
   the same answer. Permission is scoped by person or agent through the
   authority on the call (ADR 062), which is what makes running many
   agents against one tree safe. *Built today:* the routing chokepoint;
   mount-level and per-prefix rules on mutating verbs (ADR 006);
   reversible delete and restore; the principal threaded to storage and
   stamped as owner. *Designed, not built:* per-principal grants,
   posture, and hidden rows (spec 058, ADR 065–067); content version
   rows (ADR 013/017/064 — the schema is landed, no write path mints a
   row); read-side gating; the `permission_denied` family. Public copy
   says "delete is reversible" and "versioned" only for what the tree
   does.

2. **Differentiator two: built-in search that scales, no tuning.** *glob,
   grep, glean, and graph work out of the box over the database you
   already run.* Peers require an external embedder and vector store
   (Mastra), a paid search tier (MongoDB Atlas M10+), a client-side
   install (Letta plus QMD), or offer a regex scan and nothing else
   (Cloudflare Computer, deep agents). vfs's search runs over the same
   rows the writes touch, in the same transaction domain, scoped by the
   same predicate, with a graph leg no peer can compute because no peer
   has edges. *Built today:* glob, grep, glean's fused ranker, typed
   edges, the default local embedding model (ADR 060), sqlite-vec as a
   core dependency (ADR 059), declared budgets and classified refusals.
   *Not yet:* the `graph` verb has a router and a vocabulary and no
   backend implementation; glean is withheld by design on dialects with
   no distance function. Public copy names `graph` as a verb only once
   a backend serves it. "No tuning" means the defaults are wired; the
   knobs come later and are never required.

3. **Differentiator three: one shared namespace, cloud native and
   multi-user.** *One tree that everyone in the enterprise — every
   agent, every person — shares, with different rights on different
   paths, and no copies.* This is the Plan 9 heritage and the one design
   lineage no peer has: their tenancy answer is one store per principal.
   vfs is database-backed, async throughout, and built to serve many
   clients at once from one process. *Built today:* mounts, bind,
   remount, longest-prefix routing, cross-mount refusals; the async
   session facade; five SQL engines with statements chunked to the
   tightest engine's budget and 10,000-file batches as a supported call
   — the scale contract is this differentiator's proof. *Designed, not
   built:* the rights tier (spec 058); the server — there is no
   `serve()` in the live tree, and until it exists "servicing multiple
   clients" is a library property, not a product one.

4. **The triad names the audiences and is the public shorthand.**
   *AI native* — the verbs an agent already knows, the search indexes,
   and the permissions, all on one surface. *Human native* — the
   filesystem is the abstraction people already use to store, find, and
   navigate information; the same tree an agent works in is one a person
   can read. *Cloud native* — database-backed, async, ready to sit behind
   a FastAPI or MCP server and serve an organisation. Each leg is honest
   about its depth: the AI leg is the built half; the cloud leg is built
   at the library tier and waits on `serve()`; the human leg is the
   thinnest today — Letta, Cloudflare Artifacts, and Box let a person
   `git clone` or open the agent's tree, and vfs's human surface is the
   Catalog plane (ADR 058 pin 5), still a name.

5. **The one-line differentiation, for when a sentence is all there is
   room for:** *Peers use the database as a disk. vfs uses it as a
   gate.* Two alternates carry the same idea: "Every filesystem for
   agents stores its files in a database; vfs is the one where the
   database enforces," and "One namespace. Many principals. Different
   rights. No copies." None of these replaces ADR 058's three-line
   stack; they sit under it.

6. **vfs is not a filesystem emulation, and says where not to use it.**
   The live counter-argument (Arize, June 2026: a Postgres-backed VFS
   scored 93 against a "query once, materialise, use real bash" skill's
   99, with the line "every time you fake a filesystem, you sign up to
   maintain one") is right against the thing it tested. vfs does not
   defend that thing. vfs is a namespace with semantics a POSIX
   filesystem cannot give — a principal on every call, per-caller
   visibility on one tree, attributed versions, typed edges,
   predicate-scoped search. Where none of that is needed (one agent, one
   machine, no sharing, no policy), a checkout plus ripgrep wins, and
   vfs's own docs will say so.

7. **What vfs does not claim.** An execution surface (ruled out by the
   constitution; the study found that every system with a shell admits
   the shell bypasses its path policy). An object-store data plane for
   large binaries (an open question, sharpened, not answered). Rich
   document ingestion. Git compatibility. A context policy (Letta's
   `system/` pin is a host concern; vfs makes the tree's metadata cheap
   so hosts can build one). A harness.

## Consequences

- **Public copy.** The README's opening keeps ADR 058's three lines. Its
  "Why a file system?" section and the alpha banner are the places the
  three differentiators and the triad belong, each with its
  built/designed line. Not landed with this record; the rewrite is the
  follow-up once the wording is ratified. PyPI and MCP server
  descriptions carry the one-liner from pin 5.
- **Sequencing: the evidence now points one way.** ADR 058 left
  search-first vs governance-first as a `[NEEDS CLARIFICATION]`. The
  landscape study answers the factual half: hybrid search is now
  shipped by MongoDB, Mastra, Cloudflare Agent Memory, and two hobby
  projects, while per-path, per-principal enforcement in the data path
  is shipped by nobody. Differentiator one is the unbuilt half of the
  pitch. This record carries the recommendation — principals and grants
  (spec 058) ahead of glean's remaining legs — and leaves the ruling to
  the roadmap entry in `../open-questions.md`, which now cites the
  study.
- **Version rows must land.** Differentiator one claims versioning; the
  hosted peers (Anthropic's memory store, Mesa, Cloudflare Artifacts)
  already mint a version per write; vfs mints none. The attribution
  columns (ADR 064) are the differentiating part and the minting is the
  prerequisite. Until then public copy says "reversible delete," not
  "every mutation is versioned."
- **`serve()` gates differentiator three and every non-Python
  consumer.** Vercel's eve (an MCP connection or a memory provider
  keyed on `byPrincipal`), LangChain's deep agents (a `BackendProtocol`
  adapter — MongoDB shows the shape), Mastra (a filesystem provider), and
  the Claude client-side memory tool are all reachable only through a
  served vfs. The re-spec should be written against eve as the named
  consumer: MCP `2026-07-28` with stateless `2025-11-25` compatibility,
  an agent-facing tool subset found by description, the `Result`
  envelope as structured content, and a per-call idempotency key.
- **Write preconditions on the wire.** The idiom every peer converges on
  — a content hash or expected version on `write` and `edit`, refused
  with a classified kind on mismatch — is what a replayed durable step
  needs and what differentiator one implies. Open question filed.
- **Say why a result stopped.** The served envelope carries a truncation
  reason (budget, refusal, unreadable), as deep agents' results do, so
  an agent knows whether narrowing helps.
- **Make the tree's metadata cheap.** `ls` and `stat` returning size,
  version, mtime, and a description line where frontmatter has one is
  the substrate half of the context policies Letta and Anthropic's
  context-engineering essay describe. Cheap, and it is the human-native
  leg's first concrete step.
- **"When not to use vfs" is written down.** A short statement, per pin
  6; its home (README, mission, or the ADR 058 refresh) is an open
  question.
- **`standards/mission.md` is still out of step** (ADR 058 already says
  so). The v0.2 revision carries the category, the layer/plane split,
  the July buyer, and now the three differentiators and the triad.
- **Easier:** three claims a reader remembers; a direct answer to "how
  is this different from deep agents / Cloudflare Computer / MongoDB's
  VFS / Letta"; a named audience per leg; a clean response to the Arize
  critique.
- **Harder:** two of the three claims are ahead of the tree. The
  built/designed lines under each pin are load-bearing until spec 058,
  version rows, and `serve()` land. Every public sentence is checked
  against them, as ADR 058 pin 7 already requires.
- **Committed to:** the three differentiators in the order and wording
  of pins 1–3; the triad as the public shorthand; "peers use the
  database as a disk, vfs uses it as a gate" as the one-liner; no
  public claim of `graph` until a backend serves it; no public claim of
  content versioning until a write path mints a row; the "when not to
  use vfs" statement as part of the pitch, not an apology.
- **Not decided here** (pointers in `../open-questions.md`): the
  sequencing ruling; write-precondition shape (expected version, content
  hash, or both); bytes in rows vs an object-store data plane above some
  size; the home of the "when not to use" statement; whether vfs
  publishes reference adapters for host frameworks or documents the wire
  only; the plane's real name.

## Learnings this record carries

Things the two studies taught that are not decisions but should not be
re-learned:

- **The interface thesis is won and is not ours to sell.** Anthropic,
  OpenAI, LangChain, Letta, Manus, OpenClaw, Cloudflare, Mastra, and
  Vercel all treat `ls`/`read`/`write`/`grep` over a tree as the agent's
  native I/O. vfs's "why a file system" argument is now common ground;
  the pitch starts one sentence later.
- **"Filesystem-first" can mean authoring, not runtime.** eve's agent is
  a directory the framework compiles; at runtime the agent touches an
  ephemeral sandbox. Read every "filesystem for agents" claim for which
  of the two it means.
- **The deferral sentence is the market's product spec.** Three of four
  peers wrote "the application" should do permissions, tenancy, and
  audit. That sentence is what vfs builds.
- **One store per principal does not compose.** It is the industry's
  tenancy answer and it fails the moment two callers share a document
  with different rights. Subject sets (ADR 066) and per-path grants are
  the answer, and no peer has them.
- **The shell is the enforcement gap, by the peers' own admission.**
  Mastra, deep agents, and Anthropic's self-hosted note all say bash
  bypasses tool-level path policy. The constitution's no-shell rule is
  an enforcement property, not a limitation.
- **Hybrid search is table stakes now.** MongoDB, Mastra, Cloudflare
  Agent Memory, agent-vfs, memgres. The defensible search claims are the
  ones peers say they lack: read-your-writes, permission-scoped results,
  and the graph leg.
- **Hosted peers version; open-source database-backed peers do not.**
  Anthropic's memory versions survive deletion and support redaction
  with attribution preserved; memgres hash-chains diffs and crypto-shreds
  on forget. Those are the shapes vfs's version rows and trash should
  match.
- **Content-hash preconditions are the emerging write-safety idiom**
  (Anthropic, memgres, MongoDB's edit, eve's read stamp).
- **Cloudflare's `dofs` is the nearest schema and the furthest
  purpose.** Tables literally named `vfs_nodes`, `vfs_dirents`,
  `vfs_blobs`, `vfs_chunks`; content-addressed chunks; a read-only
  mount guard at the data layer; no owner, no history, single writer,
  "agent-local scratch." Its contribution is sync and FUSE; ours is the
  gate.
- **eve is a consumer at two seams, not as a filesystem.** An MCP
  connection (zero eve code, allow-list and approval gates on top, the
  verified principal forwarded per call) and a memory provider
  (`recall`/`capture`/`tools` under an opaque per-tenant scope key).
  Both need a served vfs and neither needs vfs-js.
- **Durability is orthogonal; be replay-safe instead.** Every framework
  brings its own engine (Vercel Workflow, Temporal, LangGraph
  checkpoints, Cloudflare Workflows). vfs's obligation is idempotent or
  version-conditioned writes, not a workflow engine.
