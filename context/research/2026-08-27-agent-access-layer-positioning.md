# Positioning: the access layer for agents, and the catalog above it

- **Status**: research memo (commits us to nothing; feeds a positioning
  ADR and the README rewrite)
- **Date**: 2026-08-27
- **Owner**: Clay Gendron
- **Question**: Clay wants to bill vfs as "the library to control what
  your agents can access and perform" — not a harness builder like
  LangGraph, not the agent loop, but what an agent can do once it is
  built and running. Three questions follow. (1) Is "agent control
  plane" the right name for that? (2) What is the market asking for
  right now, and which of those problems can vfs credibly solve?
  (3) How does an admin UI — Clay's "Unity Catalog for agents" — fit
  with the library?
- **Method**: web survey of the August 2026 market (governance surveys,
  the "agent control plane" category as vendors and analysts now define
  it, MCP gateways, agent identity, sandboxes, file-based context
  engineering, Databricks' June 2026 Unity Catalog announcements), plus
  a subagent digest of this repo's five prior positioning memos to find
  the through-line and the disagreements. Sources in §9. Survey numbers
  below come from vendor-published reports (AvePoint, Gravitee, Okta)
  and analyst press releases (Gartner, Forrester, Futurum); treat them
  as directional, not audited.
- **Prior memos this builds on**:
  `2026-06-09-direction-and-developer-first-strategy.md`,
  `2026-06-13-openclaw-positioning-and-demo.md`,
  `2026-07-13-company-analysis.md`,
  `2026-07-22-control-plane-data-plane-prior-art.md`.

---

## 1. Bottom line

**"Agent control plane" is the right idea and the wrong name.** The idea —
govern what a running agent can touch, not how its loop runs — is exactly
vfs. But in 2026 the phrase has become a formal enterprise category
(Forrester is evaluating it; Futurum published a reference framework;
Google, IBM, ServiceNow, and Salesforce are the names attached), and that
category means *a management system above agents* — deploy, operate,
monitor, govern a fleet. vfs is not that. vfs sits *in the data path*.

**Recommended category for the library: the access layer for agents.**
"Access" is the buyer's own word (least privilege, access control, data
access); "layer" places vfs in the path rather than above it; and nobody
has claimed the phrase.

**Clay's "plane" instinct is right for a second product.** A layer sits
in the path and enforces. A plane sits above it and shows and decides.
The admin UI Clay wants — see what is in a namespace, who can reach what,
which tools live where, what changed — is a catalog over the library,
structurally very close to Databricks' Unity Catalog. Working names:
**vfs** (the access layer) and **vfs Catalog** (the plane).

**The differentiation against Databricks must be said out loud**, because
Databricks launched Unity AI Gateway in June 2026 to govern agents, MCP
services, skills, and tools through Unity Catalog. The line: Unity
Catalog requires Databricks and governs tables; vfs requires a DSN and
governs paths.

---

## 2. What the market is asking for (August 2026)

The blocker has moved from "can we build an agent" to "can we govern
one." The numbers agree across independent sources:

| Signal | Number | Source |
| --- | --- | --- |
| Delayed an AI deployment because not ready to govern it | 86.9% | AvePoint, State of AI 2026 |
| Had an agent-related security incident in the last 12 months | 88% | Gravitee, n = 900+ executives and practitioners |
| Most common incident type: **data leakage** | 50.1% | Gravitee |
| Second: manipulation by untrusted input | 49.6% | Gravitee |
| Treat agents as identity-bearing principals | 21.9% | Gravitee |
| Agents authenticate with **shared API keys** | 45.6% | Gravitee |
| Authorization is custom hardcoded logic | 27.2% | Gravitee |
| Agents running with no security oversight or logging | > 50% | Gravitee |
| Apply the same security controls to agents as to human workers | 34% | Okta, AI Agents at Work 2026 |
| Agentic projects cancelled by end of 2027 (cost, unclear value, **inadequate risk controls**) | > 40% | Gartner, June 2025 |
| Enterprises that will demote or decommission autonomous agents after governance failures | 40% by 2027 | Gartner, May 2026 |

Three institutional markers put a date on this:

- The **NSA published MCP security guidance** (May 2026): least
  privilege per tool and per resource, explicit denial of file-system
  and network paths a server does not need, OAuth 2.1 with PKCE.
- **Okta shipped Agent SSO** (GA 2026-08-24) and Okta for AI Agents
  (GA 2026-04-30): first-class identity for agents as principals.
- **Gartner published its first Magic Quadrant for AI Governance
  Platforms** (June 2026); it sizes the market from $65M (2024) to
  $1.4B (2030).

The recurring phrase is **least privilege**: an agent should see and touch
only what its task needs.

### 2.1 The interface side has converged on the file system

In parallel, the industry has adopted vfs's interface thesis:

- **LangChain deep agents** give the agent `ls`, `glob`, `grep`, `read`,
  `write`, `edit` over a file system and call it context engineering.
  The post frames the file system as "a single interface through which
  an agent can flexibly store, retrieve, and update an infinite amount of
  context." It does **not** address access control, multi-tenancy,
  persistence guarantees, or scale — those are open.
- **Anthropic Managed Agents memory** (public beta 2026-04-23) mounts
  memory at `/mnt/memory/` in the agent's container; every write creates
  an immutable version; stores are read-only or read-write; **each store
  is capped at ~100 KB (~25K tokens), eight stores per session**;
  backend undisclosed; workspace-scoped.
- The **file-native agentic systems** paper (arXiv 2602.05447, 9,649
  experiments, 11 models, schemas to 10,000 tables) finds frontier
  models improve with file-based retrieval and handle 10,000-table
  schemas by partitioning the namespace.
- The Agent Skills standard (`SKILL.md`, Dec 2025) is read by ~40
  products as of June 2026 — skills are files in a tree.

So the file-as-interface bet is won (the July company memo said the same).
The governance of that file surface is unbuilt everywhere.

---

## 3. Where the category lines are drawn now

The vendors and analysts have settled on a stack. The definitions matter
because they decide what a reader hears when we pick a name.

**Agent control plane** — "the system that deploys, operates, monitors,
and governs agents across an organization" (IBM; Obot uses the same
words). Obot's five components: agent identity, permissions and access
control, lifecycle management, runtime policy enforcement, observability
and audit. Obot's own distinctions:

- vs. framework: *"Frameworks build agents. The control plane governs
  what those agents can touch."* (This is nearly Clay's sentence.)
- vs. MCP gateway: *"The control plane is the governance authority. The
  MCP gateway is the enforcement mechanism at the tool access layer."*

**Futurum's Agent Control Plane Framework** (April 2026) names five
layers, and one of them is the slot vfs occupies:

| Layer | Name | Their one-liner |
| --- | --- | --- |
| 0 | Execution environment | "where governance becomes physical: without it, all control above is advisory" |
| 1 | **Knowledge authority** | **"restricts what agents may access and understand"** |
| 2 | Behavior guardrails | "makes unsafe actions structurally impossible, not just prohibited" |
| 3 | Governance | authorization between reading context and writing state |
| 4 | Coordination | observable, auditable multi-agent protocols |

Their principle: *"agents decide, control planes govern, execution
environments enforce, and systems generate evidence."* Enforcement lives
where the data is.

**The rest of the stack**, with who owns each slot:

| Slot | Governs | Sees | Names |
| --- | --- | --- | --- |
| Framework | how the agent thinks and loops | the prompt | LangGraph, CrewAI, OpenAI Agents SDK |
| Control plane | fleet policy, lifecycle, audit | agents as objects | Google, IBM, ServiceNow, Salesforce, Microsoft Agent 365 |
| MCP gateway | the tool call | tool names and arguments | Lunar MCPX, MintMCP, Kong, AWS AgentCore Gateway, Obot |
| Identity | who the agent is | the principal | Okta, Auth0 |
| Sandbox | where code runs | the process | E2B ($35M), Modal ($4.65B, May 2026), Daytona ($24M) |
| Context / memory | what the agent reads and writes | files | LangChain files, Anthropic `/mnt/memory` |

**Read across the "sees" column.** The gateway sees tool names. Identity
sees principals. Nobody in the stack sees the **rows and files** — the
data surface itself — with an agent-native interface and a governance
story. The context/memory slot has the interface and no governance; the
governance slots have no data interface.

---

## 4. The gap vfs fits

vfs is Futurum Layer 1 built as a library: the namespace is the policy.
What an agent can see is what it can do. A tool is a path (`run`), so
tool access falls out of the same rule. This is Plan 9's model, and the
prior-art memo already documents that our router is the strongest
control-plane surface in the tree (C2, namespace construction).

Why this slot is defensible against the big control-plane vendors rather
than in competition with them: enforcement on the data surface has to be
**in the data path** — in-process, at the routing chokepoint, before
dispatch. A SaaS above the agent cannot do it. So the natural
relationship is complementary: *control planes set the policy, gateways
check the tool call, vfs enforces on the data — the files, rows, and
tools the agent actually touches.*

### 4.1 Problems vfs can credibly solve, mapped to the pain

| Market pain (§2) | vfs answer | State of the tree today |
| --- | --- | --- |
| Data leakage (50.1%) | One namespace; per-mount and per-prefix permission at the routing chokepoint; tenant isolation as a permission layer, not a path prefix (ADR 006) | Router-level: **built**. Row-level grants: proposed (ADR 021) |
| Over-privileged tools (NSA guidance) | Tools live at paths; no path, no tool | `run` verb designed; enforcement is the same permission map |
| No audit trail of what the agent changed | Every mutation versioned and reversible (ADR 013, 017) | Designed; the July memo calls versioning and audit "aspirations, not features" |
| Shared keys, agents without identity (45.6%) | `Principal` seam (spec 070) binding to Okta/Auth0 — integrate, do not compete | **Not built** |
| Context engineering at scale | glob/grep/glean/graph on Postgres, SQL Server, Oracle; 10,000-entry batch contract; unbounded, vs. Anthropic's 100 KB stores | **Built — the strongest part** |
| Memory that survives and is shared | One namespace on the database you already run | Storage built; versioning partial |

The honest read: the **search** half is the built half; the **governed**
half is the half the market is buying. Positioning should point where we
are going and the README should keep saying what is real. Principal
(spec 070) and grants (ADR 021 → spec 058) are the two things to ship
before leaning hard on "governed."

### 4.2 The buyer disagreement, resolved by the market

The prior memos disagreed on the buyer. June 2026 said data engineers,
bottom-up, dlt/dbt-adjacent. July 2026 said platform and AI-infra teams
stalled in security review, and killed the data-team vertical. The
survey data in §2 — 86.9% delaying on governance readiness, 14.4% with
full security approval — is the July buyer. This memo takes July's side.
The June memo's *distribution* insight (developer-first, pip-install,
permissive core as the funnel) survives; only the persona changes.

---

## 5. Names considered

Criteria: (a) says *bounded / governed*; (b) says *what the agent
touches* — data and tools, not the loop; (c) uses a noun nobody has
already claimed; (d) works for both a developer and a security buyer;
(e) no "agentic" — Gartner's "agent washing" word.

| Phrase | Verdict | Why |
| --- | --- | --- |
| **The access layer for agents** | **Recommended** | Buyer's own word; "layer" = in the path; unclaimed; dev reads API surface, CISO reads enforcement point; leads with the built half without lying about the rest |
| The governed namespace for agents | Runner-up; use as the mechanism line | Truest phrase (Plan 9); covers files, rows, tools in one word; but "namespace" is a developer's word, not a buyer's |
| The agent's operating environment | Acceptable | OS framing, singular, no "agentic"; doesn't name the pain |
| Governed agentic environments | Close, not best | "environment" half-claimed by sandbox vendors; "agentic" worn out; plural reads as a category, not a product |
| The agentic capability plane / layer | Rejected | "Capability" reads as *giving* agents powers (Composio, Arcade); MCP uses "capabilities" for feature negotiation; Futurum uses "capability layers"; "capability plane" is not an established plane |
| Agent control plane | Rejected for the library; kept for the subsystem | Reads as fleet management; category owned by Google/IBM/Forrester; names the smallest part of vfs. Correct as the name of the mount/permission/grant subsystem (the prior-art memo's usage) |
| Agent sandbox / workspace | Rejected | E2B, Modal, Anthropic, Box are standing on those nouns |
| Agent catalog / registry | Rejected for the plane | Now means *a list of agents* (Microsoft Agent 365, Credo, TrueFoundry) — the opposite direction |

Recommended stack:

```
vfs — the access layer for agents
One namespace of everything an agent can see, search, and change. You decide what's in it.

Frameworks build the agent. Control planes set the policy. Gateways check the tool call.
vfs enforces it on the data itself — the files, rows, and tools the agent actually touches.
```

Line one is the category. Line two is the mechanism. Line three tells a
buyer with a control-plane RFP open where vfs slots in, and that it
complements what they have already bought.

---

## 6. Two products: the layer and the plane

Clay's "plane" was pointing at the admin UI, not the library. The split
the July company memo landed on (OSS `vfs-py` as funnel, paid control
plane as business, enterprise features never in the OSS quickstart) now
has a concrete shape:

| | What it does | Where it lives | Working name |
| --- | --- | --- | --- |
| The library | **Enforces.** Every read, search, write, and tool call passes through it | In-process, in the data path, `pip install` | **vfs** — the access layer for agents |
| The admin product | **Shows and decides.** What is mounted, who can reach what, which tools live where, what changed and when | Above the library, reading its introspection surface | **vfs Catalog** (the plane) |

"Catalog" is the right word for the plane: it already means *the place
you go to see what exists, who can see it, and where it came from*. It is
a category word (Unity Catalog, Snowflake Horizon Catalog, Apache
Polaris), not a brand, so the product will eventually need a name of its
own. Avoid "agent catalog" (§5).

---

## 7. The Unity Catalog analogy

### 7.1 Why it is unusually tight

Unity Catalog is Databricks' governance layer: a three-level namespace
(`catalog.schema.object`), securable objects on which privileges are
granted to principals, `GRANT`/`REVOKE`, row filters and column masks,
automatic lineage, audit logs, discovery, and a UI (Catalog Explorer). It
governs tables, views, volumes (files), functions, models, metrics, and
connections. An open-source implementation exists. The model maps onto
vfs almost object-for-object:

| Unity Catalog | vfs |
| --- | --- |
| Three-level namespace `catalog.schema.table` | The path namespace — deeper, and the one agents already speak |
| Securable objects: tables, volumes, functions, models | Entries: files, directories, mounts, tools, edges |
| Volumes — governed file storage, bolted on to a table model | Files are the primitive, not an add-on |
| UC functions exposed as agent tools | `run` — a tool is a path |
| `GRANT SELECT ON ... TO principal` | Additive grants over scopes (ADR 021) |
| Row filters, column masks | Permission at the routing chokepoint; row-level grants next |
| Lineage graph | `graph` / `mkedge` — typed edges as a first-class verb |
| Audit log | Per-entry revisions; every mutation versioned and reversible |
| Discovery and search | `glob` / `grep` / `glean` |
| Catalog Explorer | vfs Catalog |

The one deep difference is the **securable**. Unity Catalog's unit of
governance is the table, because its interface is SQL for humans. vfs's
unit is the path, because its interface is the file system for agents.
Everything else follows from that.

### 7.2 Databricks already claims the agent story

At Data + AI Summit 2026 (June) Databricks launched **Unity AI Gateway**:
"governs models, MCP services, agents, and skills through Unity
Catalog," with "action-level control: governing what an agent does in a
given interaction, not only what it can reach," plus cost caps and model
routing. So "Unity Catalog for agents" is, in effect, already their
tagline. It is a useful sentence in a meeting and a bad sentence on a
homepage, because it hands Databricks the frame.

### 7.3 The differentiation to say out loud

- **Unity Catalog requires Databricks. vfs requires a DSN.** vfs governs
  the Postgres, SQL Server, and Oracle an organization already runs — no
  lakehouse, no migration, no new infrastructure (the same claim the
  July memo makes for the mount layer).
- **Unity Catalog governs the lakehouse from above. vfs governs the
  namespace from inside** — in-process, in the data path, so enforcement
  is physical, not advisory (Futurum Layer 0).
- **Unity Catalog governs tables and bolted files on. vfs governs
  paths** — what agents actually navigate.
- **Open and embeddable.** One library mounts across engines; the plane
  reads what the library already knows.

---

## 8. What the Catalog needs from the library

The prior-art memo's bucket audit (2026-07-22, §2–6) already lists the
gaps, and they are exactly the Catalog's data feeds:

| Bucket | State (per the 2026-07-22 audit) | Catalog panel it feeds |
| --- | --- | --- |
| C7 introspection and telemetry | data exists, no surface serves it | everything — the Catalog is a read surface over mounts, the permission map, tools, and versions. **First thing to build**, and cheap: `mounts()` exists; the rest is publishing what the router already computes |
| C1 capability negotiation | computed, never published | per-mount capabilities |
| C6 authorization | path-only, principal-blind | rules now; *who* once spec 070 lands |
| C5 metadata mutation | no attribute-write verb | edit-in-place from the UI (later) |
| D2 consistency tokens | built, internal-only | "what changed" once revisions are exposed |
| ADR 021 grants | proposed | "who can reach what" |

So **Catalog v1 is a read-only viewer** over what is already built —
namespace, mounts, permission rules, tools at paths, edges. It is a real
product the day the introspection surface exists, and it grows one panel
per shipped subsystem without renaming anything.

---

## 9. What this memo feeds

- A **positioning ADR**: adopt "the access layer for agents" as the
  category for the library, "namespace" as the mechanism line, "control
  plane" reserved for the mount/permission/grant subsystem, and the
  layer/plane split as the product shape. Record the rejected names and
  why.
- The **README rewrite**: replace "Agentic Search on your Database" with
  the three-line stack in §5, while keeping the alpha banner honest about
  which half is built (§4.1).
- **Sequencing input**: principal (spec 070) and grants (ADR 021 →
  spec 058) move ahead of further search work if the governed half is
  what we sell; C7 introspection is the Catalog's prerequisite.
- An **open question** for `open-questions.md`: the plane's real name,
  and whether the Catalog is OSS-with-paid-hosting or closed.

---

## 10. Sources

Market and category (fetched 2026-08-27):

- AvePoint, *State of AI 2026: Trust, Control, and the Rise of AI Agents* — <https://www.avepoint.com/blog/manage/state-of-ai-2026-report>
- Gravitee, *State of AI Agent Security 2026* (n = 900+) — <https://www.gravitee.io/blog/state-of-ai-agent-security-2026-report-when-adoption-outpaces-control>
- Okta, *AI Agents at Work 2026* via Okta for AI Agents — <https://www.okta.com/products/govern-ai-agent-identity/>; Agent SSO GA — <https://www.okta.com/newsroom/press-releases/okta-brings-first-class-identity-to-ai-agents-with-agent-sso/>
- Gartner, *Over 40% of agentic AI projects will be canceled by end of 2027* (2025-06-25) — <https://www.gartner.com/en/newsroom/press-releases/2025-06-25-gartner-predicts-over-40-percent-of-agentic-ai-projects-will-be-canceled-by-end-of-2027>; Forbes on the May 2026 demotion forecast — <https://www.forbes.com/sites/robertszczerba/2026/07/07/why-40-of-agentic-ai-projects-may-be-canceled-by-2027/>
- NSA / CISA, *Model Context Protocol: Security Design* (May 2026) — <https://media.defense.gov/2026/Jun/02/2003943289/-1/-1/0/CSI_MCP_SECURITY.PDF>
- Microsoft, *The state of MCP security in 2026* — <https://techcommunity.microsoft.com/blog/microsoft-security-blog/the-state-of-mcp-security-in-2026/4531327>
- SiliconANGLE, *The agent control plane race hits overdrive at Next 2026* — <https://siliconangle.com/2026/04/22/agent-control-plane-race-hits-overdrive-next-2026-googlecloudnext/>
- IBM, *What is an agent control plane?* — <https://www.ibm.com/think/topics/agent-control-plane>
- Obot, *What is an agent control plane?* — <https://obot.ai/resources/learning-center/what-is-an-agent-control-plane/>
- Futurum, *Agent Control Plane Framework* (April 2026) — <https://futurumgroup.com/press-release/futurum-agent-control-plane-framework-a-reference-model-for-production-ai-agents/>
- Cloud Security Alliance, *Securing the agentic control plane* (2026-03-20) — <https://cloudsecurityalliance.org/blog/2026/03/20/2026-securing-the-agentic-control-plane>
- NeuralTrust, *Best MCP gateways 2026* — <https://neuraltrust.ai/blog/best-mcp-gateways>; Zuplo, *What the best MCP gateways do* — <https://zuplo.com/blog/what-the-best-mcp-gateways-do-in-2026>
- AgentMarketCap, *AI agent sandbox infrastructure 2026* — <https://agentmarketcap.ai/blog/2026/04/07/ai-agent-sandbox-infrastructure-e2b-modal-daytona-fly-machines-secure-code-execution>
- Decube, *What is an agent registry* — <https://www.decube.io/post/what-is-an-agent-registry>; Microsoft Agent 365, June 2026 — <https://techcommunity.microsoft.com/blog/agent-365-blog/whats-new-in-agent-365-%E2%80%93-june-2026/4535107>; Kosmoy, *AI agent governance platforms 2026* (Gartner MQ) — <https://www.kosmoy.com/resources/blog/best-ai-agent-governance-platforms-2026/>
- Atlan, *AI agent data access: governed patterns* — <https://atlan.com/know/ai-agent/how-to-give-ai-agents-access-to-enterprise-data/>

File-based context engineering:

- LangChain, *How agents can use filesystems for context engineering* — <https://www.langchain.com/blog/how-agents-can-use-filesystems-for-context-engineering>
- Anthropic Managed Agents memory (coverage) — <https://opentools.ai/news/anthropic-managed-agents-add-memory-persistent-state-for-ai-that-actually-ships>
- *Structured Context Engineering for File-Native Agentic Systems*, arXiv 2602.05447 — <https://arxiv.org/abs/2602.05447>
- Agent Skills ecosystem 2026 — <https://agentman.ai/blog/agent-skills-ecosystem-report-2026>

Unity Catalog:

- Databricks, *Governing AI agents at scale with Unity Catalog* — <https://www.databricks.com/blog/governing-ai-agents-scale-unity-catalog>
- Databricks, *What's new with Unity AI Gateway, Data + AI Summit 2026* — <https://www.databricks.com/blog/ai-governance-data-ai-summit-2026-whats-new-unity-ai-gateway>
- Databricks, *Expanding agent governance with Unity AI Gateway* — <https://www.databricks.com/blog/ai-gateway-governance-layer-agentic-ai>
- Databricks, *What's new with Unity Catalog, Data + AI Summit 2026* — <https://www.databricks.com/blog/whats-new-unity-catalog-data-ai-summit-2026>
- Databricks docs, *Unity Catalog securable objects* — <https://docs.databricks.com/gcp/en/data-governance/unity-catalog/securable-objects>; *Permissions concepts* — <https://docs.databricks.com/aws/en/data-governance/unity-catalog/access-control/permissions-concepts>

In-repo:

- `context/research/2026-06-09-direction-and-developer-first-strategy.md`
- `context/research/2026-06-13-openclaw-positioning-and-demo.md`
- `context/research/2026-07-13-company-analysis.md`
- `context/research/2026-07-22-control-plane-data-plane-prior-art.md`
- `context/decisions/006-global-namespace-tenant-permissions.md`,
  `013-per-entry-revisions.md`, `021-row-grant-model-spine.md`
