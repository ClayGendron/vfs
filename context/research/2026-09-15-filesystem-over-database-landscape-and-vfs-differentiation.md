# "Filesystem the agent sees, database underneath": the four peers, the wider set, and where vfs differentiates

- **Status**: research memo (commits us to nothing; feeds the positioning
  refresh under ADR 058, the search-first vs governance-first sequencing
  question, the `serve()` re-spec, and the versioning and write-precondition
  design)
- **Date**: 2026-09-15
- **Owner**: Clay Gendron
- **Question**: The eve memo (`2026-09-15-eve-vercel-agent-framework.md`
  §6) noted that four independent teams shipped "a filesystem the agent
  sees, a database the operator runs" in the last year: LangChain's deep
  agents and the LangSmith Agent Builder memory system on Postgres,
  Cloudflare Computer on SQLite in a Durable Object, MongoDB's VFS for deep
  agents on Atlas, and Letta MemFS on git. Clay asked for a proper study of
  each and an opinion on how vfs differentiates itself.
- **Method**: fresh clones, each checked out at its upstream default branch
  and license-checked: `cloudflare/computer` (`main` @ `7ce8259`,
  2026-09-14, MIT), `langchain-ai/langchain-mongodb` (`main` @ `ed0b50d`,
  2026-09-10, MIT), `langchain-ai/deepagents` refreshed to `origin/main` @
  `1d3232c` (2026-09-14, MIT), `letta-ai/letta` refreshed to `origin/main`
  @ `5bcdd177d` (2026-09-10, Apache-2.0; the Python server was archived
  off `main` on 2026-08-15, so its MemFS code was read via `git show` at
  the last source-bearing commit). One subagent per system read the code
  and the primary web sources against a single twelve-point rubric
  (identity, storage model, agent surface, permissions, versioning,
  search, scale, relations, sharing, coupling, stated non-goals, stated
  principles) and closed with an adversarial "what they would say vfs
  lacks" section. A fifth subagent surveyed the adjacent set from public
  pages (Mastra Workspaces, Anthropic Managed Agents memory, Cloudflare
  Agent Memory and Artifacts, OpenAI, Google ADK, Box, and eight smaller
  2026 projects). I read the Cloudflare `dofs` schema, the deepagents
  permission code, and vfs's mission and standards myself. The vfs-side
  facts come from the live tree brief prepared for the eve memo. Cites
  and describes only; no code copied. Star counts and download numbers
  are same-day API reads; vendor claims are marked as such.
- **Licenses**: computer MIT; langchain-mongodb MIT; deepagents MIT;
  letta Apache-2.0 (core; cloud parts are hosted and closed). Study
  freely; copy nothing.
- **Sources line**: the four clones above plus the web sources in §11.
  Sub-reports with file:line citations live in the session scratchpad
  and back every claim here.

---

## 1. Bottom line

**The category is real, crowded, and already converged on the two things
vfs used to lead with.** Every system in this memo exposes the same verb
set to the model (read, write, edit, ls, glob, grep). Every one of them
puts a store the operator runs underneath the path interface. "A
filesystem for agents" no longer differentiates anything, and neither
does "over a database." Both are the floor.

**What differentiates is what the database is *for*.** Every peer uses
its database as a disk: a durable place to put bytes so they outlive the
sandbox. A few also use it as an index (MongoDB, Mastra, memgres,
agent-vfs). None uses it as a gate. In every one of the four, and in
almost all of the adjacent set, permission is either a client-side check
in the tool wrapper, a whole-store switch, or explicitly "the
application's job." That phrase recurs almost verbatim:

- MongoDB: "access control, tenant isolation, data residency, retention,
  and audit requirements should be enforced through the application."
- LangChain: "Direct backend usage does not currently incorporate
  permissions"; "trust the LLM ... enforce boundaries at the tool/sandbox
  level."
- Cloudflare Computer: "Treat workspace files as agent-local scratch, not
  shared mutable state"; "no ownership model."
- Letta: the row-level access predicate literally discards its `access`
  argument and filters on organization only.
- Anthropic Managed Agents memory: no ACL within a store; "attach multiple
  stores when different parts of memory have different owners."

**vfs's differentiation, stated once:** *peers use the database as a disk;
vfs uses it as a gate.* The principal is on every call, the permission is
compiled into the same statement as the read, the version row names who
wrote and on whose behalf, and search runs over the rows the caller may
see. That is the "access layer" positioning ADR 058 already holds, and
this study is the strongest evidence for it so far: four teams built the
disk and each wrote down that they were leaving the gate to someone else.

**Five differentiators hold up, in this order.** (1) Authority in the
statement, not the wrapper. (2) One namespace shared by many principals
with different rights, instead of one store per principal. (3) Versioned,
attributed, reversible writes as the audit sink. (4) Search as a property
of the tree (read-your-writes, permission-scoped, fused with graph
signal) instead of a sidecar index. (5) Production scale as a contract:
five SQL engines, bounded 10k-file batches, no designed ceiling, against
peers' 10 GB, 2,000-file, and 10,000-memory caps. A sixth, runtime
independence, is true in principle and false in practice until `serve()`
exists.

**Three honesty notes.** First, of the five, only (4) and (5) are built;
(1) and (2) are structural today (mount and prefix rules, mutating verbs
only, no principal enforcement) and (3) has a schema and no writer. The
gate is the pitch and the gate is the unbuilt half. Second, on versioning
vfs is currently *behind* the hosted peers: Anthropic mints an immutable
version on every write with 30-day retention and redaction; vfs mints
nothing yet. Third, there is a live counter-argument (Arize, June 2026:
"every time you fake a filesystem, you sign up to maintain one") that vfs
should answer directly rather than ignore: vfs is not a faked filesystem
over a database for convenience; it is a namespace with semantics a real
filesystem cannot provide. Where a real filesystem plus ripgrep is enough,
it wins, and vfs should say so.

One-line version: everyone built the disk and deferred the gate; vfs is
the gate, and the gate is the part vfs has designed but not yet shipped.

---

## 2. The four, on one rubric

### 2.1 The comparison table

| | deep agents / LangSmith | Cloudflare Computer | MongoDB VFS for deep agents | Letta MemFS |
|---|---|---|---|---|
| **What** | LangGraph harness with a pluggable `BackendProtocol` behind eight file tools; LangSmith Agent Builder stores agent memory files in Postgres "in the shape of a filesystem" | Virtual filesystem in a Durable Object's SQLite; container or isolate compute attached as a tool | A deep agents backend: bytes in S3, chunks and embeddings in Atlas; `grep`/`glob`/`ls` served by Atlas, `read`/`write`/`edit` by S3 | Agent memory as a git repository the agent edits with file tools; `system/` files pinned into the prompt |
| **Who, when, license** | LangChain; first commit 2025-07-27; MIT; 29.4k stars; v0.7.14 | Cloudflare; open-sourced 2026-08-03 as "PREVIEW ONLY, NOT suitable for production"; MIT; 9.2k stars; v0.3.0 | MongoDB with LangChain; package 2026-08-08, v0.1.0 on 2026-08-24, blog 2026-09-03; MIT | Letta; announced 2026-02-12; Apache-2.0 core, cloud-hosted repos; 24.7k stars; Python server archived 2026-08-15, live code is TypeScript `letta-code` |
| **Storage model** | Whole-file blob plus two timestamps keyed by path string; directories synthesized by prefix at list time; seven backends (LangGraph state, LangGraph Store on Postgres rows, disk, shell, LangSmith sandbox, Hub commits, composite) | Real inode tree: `vfs_nodes`, `vfs_dirents`, content-addressed 512 KiB chunks in `vfs_blobs`/`vfs_chunks`, POSIX mode bits, a monotonic `rev` counter for sync; ~10 GB per Durable Object | One Atlas document per 512-token chunk (`source_path`, `chunk_index`, `content`, `embedding`, page and char offsets, `etag`); no size, mtime, owner, or tenant field; hard-coded collection `demo_chunks` | Bare git repo per agent at `{org}/{agent}/repo.git` in object storage; Postgres `blocks` table as a cache ("git is the source of truth"); every server commit downloads the whole `.git` to a tempdir |
| **Agent surface** | `ls, read_file, write_file, edit_file, delete, glob, grep, execute`; `ls` returns bare paths; `grep` is literal only, capped at 1,000 | `read` (line and byte continuations), `ls` (size, mtime, paged), `find`, `grep` (regex, paged), `write`, `edit` (unique `oldText`, fuzzy fallback, atomic batch, returns a diff), `delete`, `exec`, `publish` | Exactly the deep agents eight, no `delete`; `ls` and `glob` omit size and mtime "rather than faked"; grep 20, glob 200, ls 1,000, no pagination | Server: one `memory` tool (`create`, `str_replace`, `insert`, `delete`, `rename`); letta-code: the coding-agent set (Read, Write, Edit, Bash, Grep, Glob) plus git; tree rendered into the prompt with each file's description line |
| **Permissions** | `FilesystemPermission(operations, paths, mode=allow/deny/interrupt)`, first match wins, **enforced in each tool closure before the backend call**; no principal; per-user isolation is a namespace tuple the deployer must remember | **No principal, no per-path ACL, no owner column.** "Gated" means a `readonly` tool set, `EROFS` on read-only R2 mount roots, a backend `access` flag, and an egress policy; tenant = the Durable Object | **None.** The S3 prefix is the only boundary, enforced on the S3 side and not re-applied as a search filter; all deployments on a cluster share one collection | `WHERE organization_id = ?`; the `access` list is deleted; `read_only` is a per-file frontmatter flag; isolation between agents on one machine is an OS sandbox |
| **Versioning, audit** | None in core ("permanent and irreversible"); Hub backend has commits; parallel edits are an admitted race | No history: a write drops old chunks for GC; git via isomorphic-git is the versioning story; "audited" = tracing spans, default no-op | None: `write` is a blind overwrite, only `edit` uses `IfMatch`; updates delete old chunks; "the log is the only record" | One commit per edit under a 60 s Redis lock; single `main`; history via `get_history`; no revert API; author type derived by substring of the email |
| **Search** | `grep`/`glob` page the **entire namespace** into Python and scan; literal only; no ranked search in core (named as missing; issue #5531 open) | JavaScript regex scan over every file via `readFile`; no FTS5, no vectors, no ranking | On Atlas, `grep` is not grep: a `$rankFusion` of Lucene full-text and vector search, 0.5/0.5, top-40, capped at 20, path filter applied **after** retrieval; on community MongoDB it is an escaped substring regex; no read-your-writes ("intentionally eventually consistent") | **None over memory** (issue "closed as not planned"); optional client-side QMD (SQLite FTS5 + sqlite-vec); the deprecated folders path had Python `re` grep and pgvector, unfused |
| **Scale posture** | Context-shaped caps (100-line reads, 1,000 grep matches); `upload_files` is a per-file `put` loop; Postgres in practice | ~10 GB; single writer; cross-container writes are silent last-write-wins; "aim for agent-scale workspaces, not full monorepos" | 64 MiB per object; one unbounded `$in` for change detection; all changed objects downloaded into memory before chunking; serial uploads | 2,000 files and 10 MiB per shared repo; depth 2 and 20k chars per file by default; whole-repo download per commit; Postgres or SQLite only |
| **Relations** | None | Hardlinks and symlinks only | None | None (hierarchy plus description; a `MEMORY.md` index per directory) |
| **Sharing unit** | The backend instance or store namespace tuple | The Durable Object ("one agent, one container, one DO") | The S3 prefix plus the fixed collection | The git repository, read-write for every attached agent; cloud-only for shared repos |
| **Coupling** | Hard to LangGraph internals; soft to LangSmith cloud | Hard to Workers, Durable Objects, Containers; soft to the Vercel AI SDK | Hard to deep agents; soft to Atlas for storage, hard for the advertised search; S3-only in practice | Hard to Letta's runtime, Redis, the cloud git service, and an OS sandbox |

### 2.2 One paragraph each

**LangChain deep agents and LangSmith.** The most-adopted of the four and
the one that states its position most clearly. The file layer exists to
serve memory, skills, and context offloading inside the LangGraph loop:
"LLMs are great at working with filesystems, but from an infrastructure
perspective it is easier and more efficient to use a database." A path is
a dictionary key; a directory is a prefix. The permission model is real
per-path glob rules with an `interrupt` mode that becomes human approval,
but it lives in the eight tool closures and nowhere else, which the
maintainers say in the docstring: "Direct backend usage does not
currently incorporate permissions." Any custom tool, MCP tool, memory
middleware, or application script sees everything. Search on the Store
backend pages the whole namespace across the wire for every `ls`, `grep`,
and `glob`. MongoDB's package is the market saying "we want a database
behind this exact protocol," and it landed within a month of the protocol
being stable.

**Cloudflare Computer.** The closest to vfs in schema and the furthest in
purpose. The `dofs` package is a real inode tree in SQLite with tables
named `vfs_nodes`, `vfs_dirents`, `vfs_blobs`, and `vfs_chunks`,
content-addressed 512 KiB chunks, POSIX mode bits, and a `_vfs_mounts`
registry with read-only and read-write modes guarded at the data layer.
Its purpose is capacity: "there's nowhere near enough compute in the
world for every company to give each of their users' agents their own
containerized compute environment," so the filesystem lives in the
Durable Object and the container becomes "a place your data visits." The
contributions are sync, FUSE, exec, and in-process git. The absences are
stated: no ownership model, no history, no audit table, single writer,
"agent-local scratch." The team looked at Turso's AgentFS and rejected its
schema for lacking content addressing, which tells you what they optimize
for: bytes moving between a store and a container, not rows answering a
policy question.

**MongoDB VFS for deep agents.** The one that is honest about being two
systems. "Object storage is the data plane for file bytes, while MongoDB
Atlas is the control and search plane." Write goes to S3 only; a polling
or SQS watcher re-chunks and re-embeds; "don't rely on a file being
greppable immediately after writing it." On Atlas, `grep` silently
becomes hybrid semantic search with rank fusion and no scores; on
community MongoDB it becomes a substring find; regex never. The path
filter is applied after a top-40 retrieval, so a narrow scope is a
post-filter, which is the bug the first community issue reports. The
blog's deferral sentence is the clearest statement of the gap in the
whole set. The package is early (a hard-coded `demo_chunks` collection),
but the design intent is fully legible.

**Letta MemFS.** The one that chose git, and the one whose peers' ideas
vfs should study most closely for the *prompt* side. "Files are simple,
universal primitives that both humans and agents can work with using
familiar tools." The tree is always in the system prompt as signposts,
each file carries a `description` line, and the agent controls what is
always loaded by moving files into `system/`. That is a context policy,
not a storage feature, and vfs has no equivalent. On the storage side the
model is weak: one org-wide predicate, no search over memory in-product,
whole-repo download per commit, 2,000-file caps, and the Python server
has now been archived in favor of a TypeScript harness. Letta's own
benchmark ("filesystem all you need," 74% on LoCoMo with only file tools)
is the strongest published evidence that the interface matters more than
the retrieval mechanism, which cuts both ways for vfs's search
investment.

---

## 3. The adjacent set

Short profiles are in the sub-report; the table is what matters.

| System | Storage underneath | Per-path permission | Per-principal permission | Versioning | Search | Coupled to |
|---|---|---|---|---|---|---|
| Mastra Workspaces | Provider slot: local, S3, GCS, Azure, Drive, Vercel, Archil, Mesa, AgentFS (SQLite); no Postgres provider | Provider `readOnly`, `basePath`, per-tool approval; "file-tool and command-tool policies are independent" | A resolver picks a different filesystem per user | Provider's | BM25 / vector / hybrid; "filesystem and index mutations are independent" | Mastra |
| Anthropic Managed Agents memory | Hosted, undisclosed; 100 kB per memory, 10,000 per store, 8 stores per session | Per store `read_only`/`read_write`, filesystem-enforced; none within a store | One store per user, team, or project | Immutable version per write, 30-day retention, redact, `content_sha256` precondition; no restore endpoint | None (grep and glob over the mount) | Claude API |
| Anthropic client-side memory tool | Yours | Yours | Yours | Yours | Yours | None |
| Cloudflare Agent Memory | Durable Objects plus Vectorize | Not path-shaped | Profile and namespace | Fact supersession | Five-channel hybrid with RRF | Cloudflare |
| Cloudflare Artifacts | Git objects chunked in Durable Object SQLite | Per repo | Per-repo credential | Git | None | Cloudflare |
| OpenAI file search | Hosted vector stores, read-only | Per store | Per API key | None | Hybrid | OpenAI |
| Google ADK artifacts | In-memory or GCS | None documented | Session vs `user:` prefix | Integer versions | None | ADK, GCS |
| Box as deep agents backend | Box | Box folder permissions | Box identity | Box versions | Box | Box |
| AgentFS (Turso) | One SQLite file | None | None | Snapshot by copy | None | None |
| Mirage (Strukto) | Stores nothing; mounts services | `hide`/`show`, `allow`/`ask`/`deny` | Per-profile credentials | None | `grep` | None |
| agent-vfs | SQLite or Postgres, one table | None | User-ID scoping | None | FTS5 plus optional vector | SDK adapters |
| mcp-virtual-fs | Postgres with trigram indexes | None | Per session; optional Row Level Security | None | glob and grep | MCP |
| memgres | Postgres `ltree` plus pgvector | None | Users, namespaces, scoped tokens | Hash-chained diffs, blame, reconstruct, crypto-shred | Lexical, semantic, hybrid | MCP or HTTP |
| Mesa | Proprietary versioned POSIX | "Fine-grained access control" | Per mount | Branches, full history | None | Hosted |
| YoloFS (paper) | Local overlay | Progressive per-path permission | User-gated | Staging plus snapshots | None | None |

Two entries deserve a sentence. **memgres** is the closest thing in the
wild to vfs's storage thesis (a Postgres document tree with hash-chained
history, blame, hybrid recall, and scoped tokens) at hobby scale, with no
per-path rules. **mcp-virtual-fs** is the only project that pushes
tenancy into the database's own policy engine (Row Level Security),
which is the same instinct as vfs's compiled predicate, applied at the
engine tier rather than the library tier.

---

## 4. What the field has converged on (and therefore what does not differentiate)

1. **The verb set.** read, write, edit by string replacement, ls, glob,
   grep. Every system, hosted or open, framework or library. The Anthropic
   memory tool, deep agents, Computer, Mastra, agent-vfs, OpenViking all
   land within a name or two of each other. vfs's verbs match; that is
   table stakes, not a lead.
2. **Path interface, pluggable store.** Box says it plainly: "a filesystem
   doesn't have to mean literal files on disk. It's an interface
   contract." Deep agents, Mastra, Mirage, and the Claude memory tool make
   the store a slot. "Over a database" is one slot value among many.
3. **Whole-file writes with a content-hash precondition.** Anthropic
   (`content_sha256`), memgres (`base_hash`, 409), MongoDB (`IfMatch` on
   edit only), eve (read-before-write stamp). This is the emerging
   write-safety idiom and vfs should adopt it on the served surface.
4. **Truncation with a reason.** Deep agents' grep and glob results carry
   `truncated` plus a reason (budget, unreadable, transport); Computer's
   read returns `nextOffset` and `nextByteOffset`. Agents loop when a
   result is silently cut. vfs's `max_count` and `limit` bounds exist;
   the served envelope should say *why* it stopped.
5. **The shell is the enforcement gap.** Mastra: approval on `write_file`
   "doesn't stop the agent from using `execute_command` to write the same
   mounted path." Deep agents refuse permissions with a shell backend
   unless every rule is scoped to composite routes. Anthropic's self-hosted
   note admits the same. Only Mirage and ChromaFs close it by
   re-implementing bash. vfs's constitution rules out a virtualized shell,
   and this evidence supports the ruling: the systems with a shell cannot
   enforce path policy, and they say so.
6. **"One store per principal" is the industry's tenancy answer.** One
   Durable Object per tenant, one memory store per user, one namespace
   tuple per user, one S3 prefix per tenant, one git repo per agent. It
   does not compose: a document two users share must be copied or its
   whole store shared. This is the single most important pattern in the
   study, because it is exactly what vfs's subject sets and per-path grants
   are designed to replace.

---

## 5. Where vfs differentiates, ranked

Each entry gives the claim, the peer evidence, vfs's status today, and
the risk. Status words: **built** (in `src/`), **structural** (a weaker
form is built), **designed** (spec or ADR, no code).

### 5.1 Authority in the statement, not the wrapper

*Claim.* The permission check runs inside the storage call, on every
verb, for every caller, and the search statistics never see a row the
caller may not.

*Peer evidence.* Deep agents enforce in the tool closure and say so:
"Direct backend usage does not currently incorporate permissions."
Computer: "Backend construction fixes maximum authority"; there is no
per-call subject. MongoDB: the prefix is enforced on the S3 side and
"not re-applied as a search-side filter," and the blog defers access
control to the application. Letta: the access predicate discards its
`access` argument. Anthropic: no ACL within a store. Only mcp-virtual-fs
(Postgres RLS) and Box (the backend's own ACL) put the check in the data
path, and neither is a general library.

*vfs status.* **Structural.** A `PermissionMap` per mount, composed
most-restrictive-wins, checked for mutating verbs only. Reads are not
gated. `permission_denied` is a reserved kind nothing produces. The
principal reaches storage on every call and stamps `owner_id`, but
refuses nothing. Grants, posture, hidden rows, and the bounded compiled
predicate are spec 058, written and unimplemented. The statistics-leak
memo already establishes why the check must be in the statement.

*Risk.* This is the pitch and the unbuilt half. Every month it stays
designed, a peer can ship a namespace-tuple-plus-RLS answer that is good
enough for most buyers. The predicate-at-scale research shows it is
buildable within the engine caps; the sequencing question in
`open-questions.md` is where this decision lives.

### 5.2 One namespace, many principals, different rights

*Claim.* One tree, shared by agents and humans who hold different rights
on different paths, without copying data or sharing whole stores.

*Peer evidence.* Computer: "one agent, one container, one DO"; "agent-
local scratch, not shared mutable state." Letta: a human and an agent
hold the same org-level right; the sharing unit is a whole repository.
Anthropic: "attach multiple stores when different parts of memory have
different owners or access rules." Deep agents: two users are kept apart
only if the deployer computes different namespace tuples, and forgetting
it "share[s] the same storage." Nobody in the set can express "this
subtree is visible to the support agent, editable by the on-call human,
and invisible to the tenant's other agents" inside one store.

*vfs status.* **Built** at the namespace tier (mounts, bind, remount,
longest-prefix routing, cross-mount refusals classified) and **designed**
at the rights tier (subject sets with the intersection law, posture by
prefix, hidden rows). The Plan 9 heritage is the whole point here and it
is the one design lineage no peer shares.

*Risk.* Modest. The mount layer works. The rights layer rides on 5.1.

### 5.3 Versioned, attributed, reversible writes as the audit sink

*Claim.* Every mutation leaves a row naming actor, subjects, provenance,
and source identity; delete never destroys; content rolls back.

*Peer evidence.* The open-source database-backed peers do not version:
deep agents ("permanent and irreversible"), Computer (old chunks are
garbage-collected; "audited" is a no-op tracing observer), MongoDB
("the log is the only record"), agent-vfs, mcp-virtual-fs. The hosted
peers do: Anthropic mints an immutable version per write, retains 30
days, supports redaction, and attributes to the session; Mesa has
branches and full history; Cloudflare Artifacts is git. Letta has git
commits with author type guessed from an email substring. Nobody
attributes a version to a *principal chain* (who acted, on whose behalf).

*vfs status.* **Designed, with a gap to close.** Delete and restore are
built and reversible. Every observation carries a version stamp. No write
path mints a version row; content history, reconstruction, and the
attribution columns are schema-landed and unused. The README's "every
mutation is versioned so it can be undone" is ahead of the code.

*Risk.* High, because it is a claimed feature. Today vfs is behind
Anthropic's memory store on this axis. The differentiation is attribution
to the authority (actor plus subjects plus provenance), which no peer has,
but that argument only lands once version rows exist.

### 5.4 Search as a property of the tree, not a sidecar

*Claim.* glob, grep, glean, and graph run over the same rows the writes
touch, in the same transaction domain, scoped by the same permission
predicate, and glean fuses a signal (graph) no peer can compute because
no peer has edges.

*Peer evidence.* Mastra: "Filesystem and index mutations are independent
... Queries read that index, not the live filesystem." MongoDB: "neither
option gives read-your-writes for search"; path filters applied after
retrieval; regex never. Deep agents: whole-namespace scan in Python;
semantic search named as missing. Computer: regex scan; no index. Letta:
no search over memory in-product. Anthropic: none. Only agent-vfs,
memgres, and OpenViking put lexical plus vector behind the path
namespace, and none fuses graph signal or scopes results by a
permission predicate.

*vfs status.* **Built**, the strongest half. glob and grep with declared
budgets and classified refusals; glean's fused ranker; typed edges via
`mkedge`. Two caveats: the `graph` verb has a router and vocabulary but
no backend implementation, and glean is withheld on dialects with no
cosine function (by design, ADR 059).

*Risk.* Low on the mechanism, real on the framing. Letta's benchmark
says the interface matters more than retrieval; MongoDB and Mastra now
ship hybrid search; agent-vfs does it in 17 stars. Hybrid search is
becoming table stakes. The defensible claims are the ones peers state
they lack: read-your-writes, permission-scoped results, and the graph
leg.

### 5.5 Production scale as a contract

*Claim.* Five SQL engines, statements chunked to the tightest engine's
budget, 10,000-file batches as a supported call, and no designed corpus
ceiling.

*Peer evidence.* Computer: ~10 GB per Durable Object, single writer,
"not full monorepos." Letta: 2,000 files and 10 MiB per repo, depth 2.
Anthropic: 10,000 memories per store, 100 kB each. MongoDB: one
unbounded `$in`, serial uploads, everything in memory before chunking.
Deep agents: per-file `put` loops; Postgres in practice. Every peer
serves one audience (agent scratch) on one engine (SQLite in a DO,
Postgres, Atlas, git).

*vfs status.* **Built.** Two audiences, five engines, membership budgets,
the bulk-load door for the system actor.

*Risk.* Low. This is the least glamorous differentiator and the most
verifiable. It also answers the ETL audience nobody else addresses.

### 5.6 Runtime independence (conditional)

*Claim.* A library and an MCP server, usable from any loop.

*Peer evidence.* Every one of the four is bound to a loop or a cloud:
LangGraph, Durable Objects plus the AI SDK, deep agents, Letta's runtime.
Mastra and Anthropic are bound to their frameworks. memgres,
mcp-virtual-fs, and agent-vfs are the only runtime-independent ones, and
they are small.

*vfs status.* **Designed.** No `serve()` in the live tree; the only
surface is in-process Python. Until that changes vfs is *more* coupled
than an HTTP-only peer.

*Risk.* This is the gate to everything in §5 being reachable by a
TypeScript framework. The eve memo makes the same point.

---

## 6. Where vfs does not differentiate, and should not pretend to

- **An execution surface.** Computer, Mastra, letta-code, and deep agents'
  sandbox backends give the agent a shell over the same tree. vfs rules
  this out by constitution. The study supports the ruling on enforcement
  grounds (§4.5), but it is still the first thing a coding-agent
  audience will ask for, and the honest answer is "reach vfs from inside
  your sandbox as a client."
- **An object-store data plane for large binaries.** MongoDB and Archil
  keep bytes in S3; Mastra mounts buckets. vfs keeps content in SQL rows.
  A 64 MiB PDF in a Postgres row is a real question the multimodal
  storage open question already holds; this study adds urgency, not an
  answer.
- **Rich-document ingestion.** MongoDB chunks PDF, DOCX, XLSX, PPTX per
  page with zip-bomb guards. vfs indexes text it is handed.
- **Git compatibility.** Letta, Computer, and Cloudflare Artifacts let a
  human `git clone` the agent's tree. vfs's history is rows. This is a
  UX gap, not a semantic one, and the Catalog plane is where it would be
  answered.
- **A context policy.** Letta's `system/` pin and rendered tree with
  description lines decide what is *always* in the prompt. Deep agents'
  tuned prompt says when to grep versus read. vfs is substrate and has
  no opinion here, by design. It should make the tree's metadata (size,
  mtime, a description line) cheap to fetch so hosts can build the
  policy, which is what Letta and Anthropic's context-engineering essay
  both say agents are tuned for.
- **A harness.** None. Correct by mission, and every peer that has one
  will say vfs is "just storage."

---

## 7. The counter-argument, and the answer

Arize's June 2026 benchmark compared a Postgres-backed virtual filesystem
against a "SQL skill" (query once, materialize locally, use real bash) and
found the skill more accurate on synthesis questions (99 versus 93 out of
100). Their warning: "Every time you fake a filesystem, you sign up to
maintain one, and the closer you push it to behave like the real thing,
the more you've just rebuilt the real thing, slower." Blocks & Files
raised the same latency concern about Box's layer.

The argument is right against the thing it tested: a filesystem faked
over a database for the model's convenience, where a real filesystem
would do. vfs should not defend that thing. The answer is that vfs is not
a filesystem emulation; it is a namespace with semantics a POSIX
filesystem cannot provide: a principal on every call, visibility that
differs by caller on one tree, versions attributed to an authority,
typed edges, and ranked search scoped by the same predicate. Where none
of that is needed, ext4 plus ripgrep wins and vfs should say so in its
own docs. Where it is needed, the alternative is not a real filesystem;
it is the "application" every peer defers to, which today means each
team writes its own gate.

This also sets the bar for the served path: vfs must not be *slower*
than a peer at the verbs everyone shares. The benchmark work already done
on grep and glob is the right kind of evidence; the served surface needs
the same.

---

## 8. What this changes for vfs

1. **Governance-first has its evidence.** The open sequencing question
   asks whether principals and grants move ahead of the remaining glean
   work. This study answers it: hybrid search is now shipped by MongoDB,
   Mastra, Cloudflare Agent Memory, and two hobby projects; per-path,
   per-principal enforcement in the data path is shipped by nobody. Spec
   058 is the differentiator; the remaining glean signals are table
   stakes. The recommendation is (b) in that entry: principals and grants
   now, glean's remaining legs after.
2. **Version rows must land, and soon.** Hosted peers already version
   every write. vfs claims it in the README and does not do it. The
   attribution columns are the differentiating part; the minting is the
   prerequisite.
3. **`serve()` gates runtime independence.** Same conclusion as the eve
   memo, now with four more consumers in view: deep agents (a
   `BackendProtocol` adapter over a served vfs is a small package, and
   MongoDB shows the shape), Mastra (a filesystem provider), Anthropic's
   client-side memory tool (the purest "your store" seam), and eve.
4. **Adopt the content-hash precondition on the wire.** `write` and
   `edit` should accept an expected version or content hash and refuse
   with a classified kind on mismatch. Anthropic, memgres, MongoDB, and
   eve all converge on this; it is also what a replayed durable step
   needs.
5. **Say why a result stopped.** The envelope should carry a truncation
   reason (budget, refusal, unreadable), as deep agents' results do, so
   an agent knows whether narrowing helps.
6. **Make the tree's metadata cheap.** `ls` and `stat` returning size,
   version, mtime, and a description line (SKILL.md-style frontmatter
   where present) is what Letta's signposts and Anthropic's essay say
   agents are tuned to use. Cheap to add; it is the substrate half of a
   context policy.
7. **Write the "when not to use vfs" paragraph.** A local checkout plus
   ripgrep beats vfs for a single agent on a single machine with no
   sharing and no policy. Saying so answers Arize and sharpens the pitch.
8. **Positioning sentence candidates**, for the README and ADR 058
   refresh:
   - "Every filesystem for agents stores its files in a database. vfs is
     the one where the database enforces."
   - "Peers use the database as a disk. vfs uses it as a gate."
   - "One namespace. Many principals. Different rights. No copies."

---

## 9. Design patterns worth lifting

Ideas, not code. Each maps onto a live vfs seam.

- **Read-only mount guard at the data layer (Computer).** `EROFS` is
  raised inside the filesystem primitives so that writes arriving by any
  path, including sync, are refused. vfs's `PermissionMap` is already
  checked at the routing chokepoint; the lesson is to keep it there and
  never add a second, wrapper-tier check that a bulk path could skip.
- **Content-addressed chunks with a manifest (Computer).** Dedup and
  streaming range reads fall out of it. Not for now, but the multimodal
  storage question should weigh it against bytes-in-rows.
- **Versions survive deletion; redaction preserves who and when
  (Anthropic).** A deleted memory's versions remain in the store; a
  redacted version keeps its attribution. That is the right shape for
  vfs's version rows and trash.
- **Provenance on every diff, blame per line, crypto-shred on forget
  (memgres).** The `source`/`reason` fields on a change are what an
  audit consumer wants; the crypto-shred is the right answer to "forget"
  in a system that never destroys.
- **A description line in the tree (Letta, Anthropic's essay).** The
  first frontmatter line of a file rendered next to its name. vfs's
  `Skill.to_entries()` already writes agentskills-conformant frontmatter;
  the `ls` projection can surface it.
- **Errors as codes, never stack traces (MongoDB).** Every error carries
  a stable `[EXXXX]` code. vfs's hierarchical kinds are the richer form
  of the same idea; keep them stable across the wire.
- **Refuse permissions you cannot enforce (deep agents).** The middleware
  raises if rules are configured alongside a shell backend that could
  bypass them. vfs's equivalent is `capabilities()` and declared
  refusals: never advertise a gate a mount cannot hold.
- **Truncation reasons (deep agents).** See §8.5.

---

## 10. Open questions this memo raises or sharpens

- **Sequencing (sharpened, not new).** The "search-first or
  governance-first" entry gains a researched note pointing here; the
  recommendation is governance-first.
- **Write preconditions (new).** Whether `write` and `edit` take an
  expected version, a content hash, or both, and what kind a mismatch
  returns. `[NEEDS CLARIFICATION: expected-version (vfs's own stamp) or
  content-sha256 (what peers use and what a client can compute without a
  prior read)?]`
- **Bytes in rows versus an object-store data plane (sharpened).** The
  multimodal storage entry gains a note: MongoDB, Archil, Mastra, and
  Computer's planned R2 tiering all keep large bytes outside the
  relational store. `[NEEDS CLARIFICATION: is there a size above which
  vfs content should live in an object store with the row holding a
  reference, and does that change the read-your-writes guarantee?]`
- **A "when not to use vfs" statement (new, small).** Where it lives
  (README, mission, or the positioning ADR) and what it says.

Pointers for the two `[NEEDS CLARIFICATION]` items are in
`context/open-questions.md`.

---

## 11. Sources

Code (all read-only, none copied): `~/Git/Repos/computer` @ `7ce8259`
(MIT); `~/Git/Repos/langchain-mongodb/libs/langchain-mongodb-deepagents-vfs`
@ `ed0b50d` (MIT); `~/Git/Repos/deepagents` @ `1d3232c` (MIT);
`~/Git/Repos/letta` @ `5bcdd177d` and `113153571` via `git show`
(Apache-2.0).

The four:
https://docs.langchain.com/oss/python/deepagents/overview ·
https://docs.langchain.com/oss/python/deepagents/backends ·
https://docs.langchain.com/oss/python/deepagents/permissions ·
https://www.langchain.com/blog/how-we-built-agent-builders-memory-system ·
https://github.com/langchain-ai/deepagents/issues/5531 ·
https://blog.cloudflare.com/cloudflare-computer/ ·
https://developers.cloudflare.com/changelog/post/2026-08-03-cloudflare-computer/ ·
https://www.infoq.com/news/2026/08/cloudflare-computer-agents/ ·
https://www.mongodb.com/company/blog/technical/vfs-langchain-deep-agents-searchable-filesystem-agents ·
https://github.com/langchain-ai/langchain-mongodb/issues/462 ·
https://www.letta.com/blog/context-repositories/ ·
https://docs.letta.com/concepts/memfs ·
https://docs.letta.com/concepts/shared-memory ·
https://docs.letta.com/agent-sdk/repositories ·
https://www.letta.com/blog/benchmarking-ai-agent-memory/ ·
https://github.com/letta-ai/letta/issues/3234 ·
https://github.com/letta-ai/letta-code

Adjacent:
https://mastra.ai/docs/workspace/overview ·
https://mastra.ai/docs/workspace/filesystem ·
https://mastra.ai/docs/workspace/search ·
https://platform.claude.com/docs/en/managed-agents/memory ·
https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool ·
https://www.anthropic.com/engineering/managed-agents ·
https://blog.cloudflare.com/introducing-agent-memory/ ·
https://blog.cloudflare.com/artifacts-git-for-agents-beta/ ·
https://developers.openai.com/api/docs/guides/tools-file-search ·
https://openai.github.io/openai-agents-python/tools/ ·
https://adk.dev/artifacts/ · https://adk.dev/sessions/memory/ ·
https://blog.box.com/filesystems-context-layer-ai-agents-powered-box ·
https://github.com/box-community/deepagents-filesystem-example ·
https://github.com/tursodatabase/agentfs ·
https://github.com/strukto-ai/mirage ·
https://github.com/johannesmichalke/agent-vfs ·
https://github.com/lu-zhengda/mcp-virtual-fs ·
https://github.com/mozgsml/memgres ·
https://github.com/volcengine/OpenViking ·
https://www.mintlify.com/blog/how-we-built-a-virtual-filesystem-for-our-assistant ·
https://www.mesa.dev/blog/introducing-mesa-filesystem-for-agents ·
https://archil.com/ · https://arxiv.org/abs/2604.13536 ·
https://arize.com/blog/postgresfs-vs-sql-skills-ai-agent-filesystem/ ·
https://www.blocksandfiles.com/ai-ml/2026/03/09/box-pitches-virtual-filesystem-layer-for-ai-agents/5208017

Counts: GitHub stars via `gh api repos/<owner>/<repo>` on 2026-09-15.
