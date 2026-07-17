# Company analysis: what to build around VFS

- **Status:** draft (v1.0) — 2026-07-11
- **Purpose:** A researched, adversarially-tested answer to "what is the
  product/company around VFS?", and what that answer implies for development
  priorities.
- **Method:** 20-agent research workflow: 3 repo readers (architecture,
  vision, execution maturity) + 4 web researchers (competitors, market
  timing, business models, ecosystem trajectory) ran in parallel; 4 company
  theses were then generated from distinct angles, each red-teamed
  independently by a market skeptic and a technical skeptic with repo
  access; a final synthesis pass re-verified every load-bearing critique
  claim against the live tree before ranking. Sources cited in §8.

---

## 1. Bottom line

**The company is the governed mount layer between agent harnesses and the
databases an organization already runs.** Apache-2.0 `vfs-py` is the
interface and the funnel — one MCP tool, sixteen verbs, pushdown-fast
search, versioned reversible writes, verified principals, and an
append-only audit journal, all in the open. The business is a **BYOC
control plane**: a gateway container in the customer's VPC (credentials
never leave their network) plus a thin closed hosted layer — policy
management, IdP binding, audit aggregation, fleet console. The wedge is
**Postgres read replicas and zero-copy branches**; MSSQL is the in-account
expansion story, never the front door. Agent apps built on VFS are demos,
not products. Never relicense.

This was not any single thesis as pitched. All four theses tested took
serious damage (§4) — but their four independently-written steelmen
converged on the same corrected company. Four adversarial tracks arriving
at one plan is the strongest signal in the research packet.

The scoreboard is **named production users and one paid pilot** — not
GitHub stars, not a published spec, not harness defaults.

## 2. Why now — and why the window is short

The market evidence divides into four findings, each load-bearing.

**The interface bet is won.** "Agents work best through files and bash" is
no longer contrarian; it is the industry default. Anthropic's memory tool
is literally a filesystem interface, and its "code execution with MCP"
post showed filesystem-presented tools cutting a workflow from 150k to 2k
tokens (98.7%). Agent Skills — folders of files — went from Anthropic
feature to cross-vendor standard in about two months. OpenAI's Agents SDK
ships mountable sandbox storage. Letta's own research found a plain
filesystem agent beating specialized memory systems (74% on memory tasks,
per Arize's survey). Claude Code — a terminal agent — went GA to $1B ARR
in ~6 months. VFS does not need to argue for the interface anymore.

**The category is named and crowding fast.** "Agent filesystem" now has a
published VC thesis (Amplify, May 2026) and a cohort: Mirage
(strukto-ai, 3.3k stars, ~50 backends, the identical "mount everything,
agents speak bash" pitch), TigerFS (TigerData's CTO, mounts existing
Postgres via FUSE with path-filter→SQL compilation), AGFS (PingCAP
co-founder, FUSE/REST over Redis/S3/SQL with commercial arm db9.ai),
Turso AgentFS (SQLite-backed POSIX FS with audit trail), Mesa (managed
versioned filesystem, private beta with legal/healthcare design
partners), and Box's virtual-filesystem pitch. **Nobody in the cohort
combines heterogeneous existing-DB mounting + identity/ACLs + versioned
reversible writes + semantic and graph verbs.** That composed whole is
the defensible position; "DB as filesystem" alone is not — two funded
founders independently shipped it within the last year. Realistic window
before harness defaults and managed services harden: 12–24 months.

**Money attaches to governed access, not retrieval.** Every open-core
comparable monetizes the stateful, identity-holding layer, never the
library: Supabase (~$170M ARR, $10.5B), LangChain ($1.25B valuation on
~$12–16M ARR, nearly all hosted LangSmith), LlamaIndex → LlamaCloud,
Pydantic → Logfire (the closest solo-Python-founder template: adoption
first, Sequoia seed, adjacent hosted product). The cautionary tales are
equally consistent: RethinkDB ("users would pay less over a lifetime than
a Starbucks coffee"), and Pinecone exploring a sale after vector search
commoditized into every database. Retrieval primitives commoditize;
authz + audit clears procurement — Arcade.dev raised $60M for exactly
"which agent, on behalf of which user, did what," and agent
execution/identity/governance infrastructure took ~20.7% of 2026 YTD
agentic deals.

**Governance of agent data access is officially unsolved.** The 2026 MCP
roadmap names audit trails, SSO-integrated auth, and gateway behavior as
open gaps. The official Postgres MCP server was deprecated after a SQL
injection bypassed its read-only mode — raw agent access to production
databases is being actively discredited at the moment demand peaks
(LangChain's survey: 57% of orgs have agents in production, missing/wrong
context the top reliability failure; ~33% of negative-ROI agent failures
cite insufficient tool/data access). Enterprises are converging on
zero-copy isolation: Databricks Lakebase branching, lakeFS per-agent
branches, read replicas. The buyer will mount a governed branch, never a
primary — and the compliance surface they need (identity, audit,
reversibility) is exactly what VFS's architecture is shaped for and
exactly what no lab wants to own, because labs do not want customer
database credentials and compliance liability.

## 3. Two honesty corrections (verified against the tree)

The synthesis re-checked every critique claim in the repo. Two stand out
because they must change public positioning today:

1. **The projection gap.** "Mount your existing tables as files" is the
   differentiating promise, and it does not exist — in code *or* specs.
   src2's `DatabaseFileSystem` stores everything in a single VFS-owned
   `vfs_entries` table: it is a file store *in* Postgres, not a projection
   *of* customer tables. None of the 71 stories covers table→path
   projection. Until it ships, the honest claim is: **"your existing
   Postgres becomes your agents' governed substrate"** (namespace, search,
   graph, versions, audit live in the database you already run, under your
   DBA's rules) — not "your tables appear as files." Projection is the
   designed second act and the durable differentiator vs Mesa/Turso/Mirage;
   do not claim it before it exists.
2. **Versioning and audit are aspirations, not features.** The versioning
   models have no backend callers; `revision` appears only in the conflict
   error kind; there is no audit code and no audit story; the permission
   vocabulary is `read`/`read_write` with no principal dimension, and
   `user_id` is caller-asserted and inert. Every public claim of "versioned,
   reversible, permission-aware" must be qualified until Gates 1–2 (§6)
   land.

## 4. Four theses, adversarially tested

| Thesis (angle) | Market verdict | Exec verdict | Disposition |
|---|---|---|---|
| VFS Cloud — governed mount plane (open-core) | weak | viable-with-changes | **Base of the recommendation**, corrected to BYOC |
| The Default Mount — MCP-standard play | weak | weak | Dead as stated; donates the distribution motion and depth wedge |
| VFS Data Plane — "the filesystem is the audit log" | weak | weak | Dead as stated; donates the audit primitive and read-only posture |
| Rove — vertical data-team agent product | weak | weak | Dead as a company; donates the demo |

**VFS Cloud (open-core + managed cloud).** The only thesis a critic rated
viable, and the only one whose kill-shots all have adopted fixes. Standing
criticisms and their corrections: hosted credential custody is unsellable
for a bus-factor-1 pre-SOC-2 vendor → invert to BYOC-in-VPC with a thin
closed control plane; first dollar in H1 2027 is too late → paid design
pilots in H2 2026 against the self-hosted stack; MSSQL-first walks onto
Microsoft's home field (Entra/Purview/Fabric own that buyer) → Postgres
replicas/branches first, MSSQL as in-account expansion. Its honest
liability stands: the paid primitives (principal-aware ACLs, audit) are
~0% built and pre-design.

**The Default Mount (protocol/standard play).** Killed on timing and
resourcing: the LangChain analogy is inverted (LangChain was first at
category creation; VFS enters a named, crowded category), a solo founder
cannot win a ubiquity race against Mirage's velocity, TigerFS's parent
company, and Linux Foundation working groups, and spec-as-moat is
backwards — Arcade authored a spec *from* standing ($60M, existing
product), not into it. What survives: the depth wedge ("the only credible
way to put an agent on an *existing* org database — governed,
pushdown-fast, reversible, one MCP tool") and the distribution rituals
(one harness integrated deeply, benchmark published, registry listings).
A spec follows adoption; publish FSP only when two external backend
authors ask for it.

**VFS Data Plane (compliance-led enterprise sale).** Killed on the trust
sale: a regulated CISO will not make a pre-SOC-2, bus-factor-1 alpha
project the audit *system of record* — the security review the thesis
claims to pass is the vendor review that kills it. EU AI Act budgets flow
to Purview/Splunk/Sentinel, not new data planes; auditors accept exported
logs, they do not audit architectures. What survives: the append-only
audit journal as an OSS chokepoint primitive, read-only-first mounts, and
the corrected buyer framing — **"the container that gets your agent pilot
through security review," sold to platform engineers, not CISOs.**

**Rove (vertical product on the substrate).** Killed hardest, on both
fronts. Market: "deliberately not text-to-SQL" collapses into the
text-to-SQL comp set at day 1 of a 30-day pilot, judged before any
compounding moat exists; the dbt-Slack persona's data lives in
Snowflake/BigQuery, not the OLTP Postgres the product mounts. Exec: the
load-bearing capability (project customer tables with citation-grade
revisions) doesn't exist and the #1 stated priority ported the wrong
product; aggregates need `run`-executes-SQL, at which point Rove *is* a
text-to-SQL agent; the "knowledge namespace" moat is exportable markdown.
Both critics' steelmen concede it's a different company wearing the same
coat. What survives: a thin Claude-driven demo harness dogfooded on this
repo's own `context/` tree plus a seeded Postgres is the right Show HN
artifact.

## 5. The recommended direction, stated fully

Run the convergent steelman:

- **OSS (Apache-2.0, forever):** `vfs-py` as the fastest way to put an
  existing database under an agent — pip install, one MCP tool, sixteen
  verbs, SQL pushdown so `grep`/`glean`/`graph` execute in the database
  (the only shipped answer to the "grep-over-API amplifies backend calls"
  objection that sinks FUSE-based rivals). Verified principals, path-prefix
  ACLs, the audit journal, and byte-exact undo all live in the open —
  because the governed demo is the adoption driver, and an auditable
  library is adoptable where a credential-holding solo vendor is not.
- **Paid (BYOC control plane):** a gateway container deployed in the
  customer's VPC — credentials never leave their network — plus a thin
  closed hosted layer: policy console, IdP binding, audit aggregation,
  fleet view. Priced from day one; hosted custody deferred until
  post-SOC-2, post-seed.
- **Wedge:** Postgres read replicas and zero-copy branches
  (Neon/Lakebase/lakeFS/RDS-replica targets), read-only by default,
  `deny_ops` on sources. Never demo against a primary.
- **Buyer:** the platform/AI-infra team whose agent pilot is stalled in
  security review. Pitch is subtractive: agents get `ls`/`grep`/`glean`
  over exactly what this principal may see, every op journaled, every
  write reversible.

**What must be true:**

1. Postgres port + MCP server + fresh PyPI release land by end of Q3 2026
   — the wedge is nonfunctional until then.
2. Pushdown demonstrably wins: one public, reproducible token/latency
   benchmark beating "Claude Code + reference Postgres MCP server" and any
   FUSE-style scan.
3. Read-only table projection can be specced and shipped within two
   quarters — it separates VFS from Mesa/Turso/Mirage and closes the §3
   gap.
4. Labs keep stopping at scratch workspaces and memory folders, and
   neither Microsoft nor the MCP working groups ship cross-vendor governed
   DB mounts inside the window.
5. OSS traction converts: 2–3 paid design pilots ($3–5k/mo, non-prod
   replicas, procurement-light) and a seed + first hire by mid-2027.

**Leading indicators:** fresh-release date vs plan; a stranger completing
the quickstart unaided; downloads/stars slope vs Mirage; first external
issue/PR/backend author; the benchmark cited by someone else; count of
*named* teams running VFS against a real Postgres (target: 10 by early
2027); inbound design-partner conversations; Mesa GA date; MCP auth/audit
working-group output (adopt it the week it lands); Anthropic/OpenAI
release notes for anything resembling org-DB mounting.

## 6. Development priorities — three gates, next three quarters

**Gate 1 (Q3 2026): ship the wedge.** Exit: a stranger runs the demo.

1. Port the Postgres backend onto the v2 storage protocol — read family
   first, then mutation + live versioning, then glean/graph pushdown
   (FTS/pgvector/trigram/Steiner-tree from src2). Add a SQLite backend
   (`aiosqlite` is already a dependency) for the zero-setup
   `uvx vfs serve` demo.
2. Land the MCP trio (story 056 Passes B/C) + `serve()`; add the `mcp`
   dependency.
3. Fresh PyPI release; regenerate docs from the live API; delete the
   dead-API quickstart/examples and the Grover-era repo-root clutter. The
   stale package shipping a dead API is the single largest adoption
   blocker.
4. Fan-out deadline (story 051) — small, drafted, required before any real
   mount.
5. Publish the benchmark as a deliverable: tokens + latency vs naive MCP
   baseline; pushdown vs scan.
6. Distribution ritual: 5-minute quickstart, one tested `.mcp.json` Claude
   Code recipe done deeply (not four harnesses thinly), asciinema,
   Show HN, MCP registry listing.

**Gate 2 (Q4 2026): make governance real in OSS.** Exit: the governed
demo — verified principal, scoped namespace, audit trail, byte-exact undo.

7. Story 070: verified `Principal` enforced at the router chokepoint,
   OIDC/JWT at MCP ingress.
8. Permission redesign: principal-aware allow/deny on path prefixes (the
   current two-value, principal-blind vocabulary cannot express the
   product). Market namespace-level governance honestly; row-level grants
   (058) stay a paid-tier follow-on.
9. **New story: append-only audit journal** at the chokepoint —
   (principal, session, path, verb, result-class), addressable under
   `/.vfs/audit`, JSONL/OTel export. No such story exists today; it is
   the demo that closes pilots.
10. Make versioned writes live on the Postgres backend; script the
    "rewind the rogue agent" undo demo.
11. **New story: read-only table projection** (tables→paths, pushdown
    filters, honest grep≈FTS semantics); ship a first cut.
12. Replica/branch-first ergonomics: read-only defaults, `deny_ops` on
    source mounts, documented Neon/Lakebase/lakeFS/RDS-replica patterns.
13. Open 3–5 design-partner conversations (platform teams stalled in
    security review).

**Gate 3 (Q1 2027): convert.** Exit: first dollar + seed evidence.

14. BYOC gateway MVP: one container in the customer's VPC, IdP binding,
    SIEM export; thin closed control plane (policy console, fleet/audit
    view) — priced from day one.
15. Close 2–3 paid pilots at $3–5k/mo on non-production replicas.
16. Raise the seed on named users + benchmark + pilot revenue; make the
    first hire. MSSQL port only if a pilot pulls it.

**Roadmap deltas** (`roadmap.md` is the stale Plan 9 wave, 015–024, while
stories reach 071 — rewrite it around the three gates):

- **Defer:** 018 binds, 019 unions/shadow, 021 cross-server edges, 022
  hybrid cross-mount search, 023 per-session namespaces (keep only the
  minimal principal↔session binding 070 needs), 024 graph workspaces.
  None closes a user or a dollar inside the window.
- **Pull forward:** 056 (MCP trio) to priority #1; 070; 051; 054 resolves
  with `serve()`. Story 020's transport survives only as embodied in the
  MCP server.
- **Add** (missing from roadmap *and* stories): audit journal; table
  projection; BYOC gateway; benchmark artifact; `security.md` + threat
  model (the constitution currently punts it).
- **Kill:** FSP as a published spec + conformance suite + registry (defer
  until two external backend authors ask); hosted credential custody
  pre-SOC-2; the console/SSO demo instinct from ROADMAP-v0.1.0;
  MSSQL-first; the cross-org-mounts narrative in any pitch; Rove as a
  product. Freeze new `base.py` architecture stories beyond 070/051 — the
  June memo already named this failure mode ("the chokepoint refactor
  absorbs all effort while the demoable product isn't getting closer"),
  and every critic independently found every thesis's plan 3–4x solo
  capacity. The freeze is what makes the arithmetic close.

## 7. Risks and forward bets

**Top 5 risks:**

1. **Window vs solo capacity.** Two rewrites in five months; demonstrated
   velocity is architecture iteration, not shipping. *Mitigation:* three
   serial gates with dated exits and a kill/replan check at each;
   architecture freeze; port-don't-redesign; hire immediately after first
   pilot/seed (the story specs + constitution make onboarding a real
   asset).
2. **Absorption and spec closure.** Anthropic's memory tool is already
   filesystem-shaped; the MCP roadmap names audit/SSO/gateway as its own
   priority with Arcade holding the pen. *Mitigation:* occupy the layer
   labs won't hold — customer DB credentials and compliance liability —
   via BYOC; when MCP auth/audit semantics land, ship the reference
   implementation within weeks rather than competing; stay off Microsoft's
   front porch (Postgres wedge).
3. **The projection gap** (§3). *Mitigation:* reposition public claims
   now; spec projection in Q4 as first-class; benchmark it; treat it as
   the moat work — TigerFS is the only competitor attempting it and is
   Postgres-only FUSE.
4. **Trust, procurement, and a fatal CVE.** One SQLi-class incident (what
   killed the official Postgres MCP server) would end a governance brand
   permanently. *Mitigation:* BYOC only; read-only defaults;
   parameterized pushdown; publish `security.md` + threat model before the
   first pilot conversation; pilots on non-prod replicas; audit journal
   inspectable in OSS.
5. **Distribution failure.** Mirage has 3.3k stars and ships weekly; the
   Pydantic funnel requires adoption that doesn't exist yet.
   *Mitigation:* depth over breadth — one benchmarked killer demo, one
   harness integrated deeply; distribution rituals as roadmap items with
   KPIs; hard checkpoint: fewer than ~10 named users by end of Q4 2026 →
   flip to direct pilot sales on the governed demo.

**Three forward bets, restated as standing decisions:**

1. *Files-as-interface wins; labs own the generic workspace.* Build only
   beneath the platforms — heterogeneous org-DB mounts behind one MCP
   tool. Never build an agent harness or app; never compete with
   scratch-workspace/memory products. Claude Code integration is
   distribution priority #1.
2. *Funded managed services (Mesa, Turso, Box) contest the category within
   12–24 months.* Win on embeddability and depth now — pip-install,
   in-process, no service dependency, pushdown proven in public. Hard
   deadline: fresh release + MCP server + Postgres mount + published
   benchmark before end of Q3 2026, ahead of Mesa GA. Never chase Mirage's
   connector count.
3. *Enterprises mount branches and replicas, never prod primaries.* Make
   replica/branch mounting the paved path — read-only by default,
   `deny_ops` on sources, documented branch targets, identity + audit as
   headline OSS features. Where branches exist, rollback rides
   branch-merge semantics rather than reimplementing them.

## 8. Key sources

Competitive landscape:

- TigerFS (TigerData CTO, Apr 2026) — https://tigerfs.io/ ·
  https://www.infoq.com/news/2026/04/tigerfs-postgresql-filesystem/
- Mirage (strukto-ai) — https://github.com/strukto-ai/mirage
- AGFS (PingCAP co-founder) — https://github.com/c4pt0r/agfs
- Turso AgentFS — https://turso.tech/blog/agentfs
- Mesa — https://www.mesa.dev/blog/introducing-mesa-filesystem-for-agents
- Amplify Partners, "File systems for agents" (May 2026) —
  https://www.amplifypartners.com/blog-posts/file-systems-for-agents
- Arcade.dev $60M Series A (agent authz/audit; authored MCP authorization
  spec) — https://www.arcade.dev/blog/arcade-series-a/

Market timing and the interface bet:

- Anthropic, "Code execution with MCP" (150k→2k tokens) —
  https://www.anthropic.com/engineering/code-execution-with-mcp
- Anthropic memory tool (filesystem-shaped) —
  https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool
- MCP 2026 roadmap (audit/SSO/gateway named unsolved) —
  https://blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/
- LangChain State of Agent Engineering —
  https://www.langchain.com/state-of-agent-engineering
- Gartner: >40% agentic projects canceled by end-2027 —
  https://www.gartner.com/en/newsroom/press-releases/2025-06-25-gartner-predicts-over-40-percent-of-agentic-ai-projects-will-be-canceled-by-end-of-2027
- Postgres MCP server SQLi deprecation —
  https://securitylabs.datadoghq.com/articles/mcp-vulnerability-case-study-SQL-injection-in-the-postgresql-mcp-server/
- Arize, agent interfaces survey (filesystem-over-database consensus) —
  https://arize.com/blog/agent-interfaces-in-2026-filesystem-vs-api-vs-database-what-actually-works/

Business models:

- Databricks–Neon (~$1B; >80% of DBs agent-created) —
  https://www.databricks.com/company/newsroom/press-releases/databricks-agrees-acquire-neon-help-developers-deliver-ai-systems
- Supabase $500M @ $10.5B —
  https://www.cnbc.com/2026/06/04/database-startup-supabase-raises-500-million-10point5-billion-valuation.html
- LangChain $1.25B on ~$12–16M ARR —
  https://techcrunch.com/2025/10/21/open-source-agentic-startup-langchain-hits-1-25b-valuation/
- Pydantic seed/Series A (the solo-founder template) —
  https://techcrunch.com/2024/10/01/sequoia-backs-pydantic-to-expand-beyond-its-open-source-data-validation-framework/
- RethinkDB postmortem —
  https://github.com/coffeemug/defstartup/blob/master/_posts/2017-01-18-why-rethinkdb-failed.md
- lakeFS per-agent branches —
  https://www.businesswire.com/news/home/20260610833771/en/lakeFS-for-Agentic-AI-Isolated-Reproducible-Enterprise-Data-for-Every-Agent
