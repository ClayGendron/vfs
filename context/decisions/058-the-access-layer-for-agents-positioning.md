# 058. The Access Layer for Agents: the Category, the Namespace as the Mechanism, "Control Plane" Reserved for the Subsystem, and the Layer/Plane Product Split

- **Status:** proposed 2026-08-27 — drafted as the follow-through the
  positioning memo names in its §9 ("a positioning ADR"); **awaiting
  Clay's ratification.** The README rewrite that rides on it landed in
  the same session and stands or falls with it. Companions: ADR 006
  (tenant isolation as a permission layer — the enforcement model this
  record names), ADR 021 (the grant spine — still *proposed*; nothing
  here ratifies it), ADR 013/017 (per-entry revisions — the audit
  story), `../research/2026-07-22-control-plane-data-plane-prior-art.md`
  (whose use of "control plane" for the mount/permission subsystem this
  record keeps). Does not touch `standards/mission.md`; see
  Consequences.
- **Date:** 2026-08-27
- **Deciders:** Clay Gendron
- **Decided by:** pending — drafted by Claude from the memo; the
  category was the memo's recommendation, and the question was Clay's.
- **Context source:**
  `../research/2026-08-27-agent-access-layer-positioning.md` (the August
  2026 market survey, the category definitions as vendors and analysts
  now use them, the names table, the Unity Catalog comparison), and the
  four prior positioning memos it digests
  (`2026-06-09-direction-and-developer-first-strategy.md`,
  `2026-06-13-openclaw-positioning-and-demo.md`,
  `2026-07-13-company-analysis.md`,
  `2026-07-22-control-plane-data-plane-prior-art.md`).

---

## Context

Clay wants vfs billed as the library that controls what an agent can
access and perform — not a harness like LangGraph, not the loop, but
what a running agent can touch. Three questions came with that: is
"agent control plane" the name; what is the market buying right now
that vfs can credibly sell; and how does an admin UI (Clay's "Unity
Catalog for agents") relate to the library.

The README has said "Agentic Search on your Database" and led with the
four search verbs. The mission (`standards/mission.md` v0.1) says "the
agentic filesystem". Neither names the pain the market has moved to.
The memo's survey puts the blocker at governance, not capability:
86.9 % of organisations have delayed an AI deployment because they
could not govern it, 88 % report an agent-related security incident in
the last year with data leakage the most common kind, 45.6 % of agents
authenticate with shared keys, and the recurring phrase across the NSA's
MCP guidance, Okta's agent identity launches, and Gartner's first AI
governance Magic Quadrant is **least privilege**. (Vendor-published
figures; directional, not audited — memo §2.)

Two things make the naming non-obvious:

- **"Agent control plane" is now a formal enterprise category**, and it
  means a management system *above* agents — deploy, operate, monitor,
  govern a fleet (IBM's definition; Obot's five components; Forrester
  evaluating; Google, IBM, ServiceNow, Salesforce attached). vfs is not
  that. vfs sits *in the data path*. The phrase would put the library
  in the wrong aisle and name its smallest part. Yet the idea behind it
  — Obot's own line is "frameworks build agents; the control plane
  governs what those agents can touch" — is exactly vfs.
- **The industry has adopted vfs's interface thesis without its
  governance.** LangChain's deep agents give the agent `ls`/`glob`/
  `grep`/`read`/`write`/`edit` and call it context engineering, with
  no access control, multi-tenancy, or scale story; Anthropic's managed
  memory mounts at `/mnt/memory/` and caps each store at ~100 KB. Read
  across the stack's "sees" column (memo §3): the gateway sees tool
  names, identity sees principals, the sandbox sees the process, the
  memory slot sees files and governs nothing. Nobody governs the rows
  and files themselves with an agent-native interface. That slot is
  Futurum's Layer 1, "knowledge authority: restricts what agents may
  access and understand", and enforcement on the data surface has to be
  in-process, at the routing chokepoint, before dispatch — a SaaS above
  the agent cannot do it. So the big control-plane vendors are
  complements, not competitors.

The honest state of the tree against that pain (memo §4.1): the
**search** half — glob, grep, glean on Postgres, SQL Server, Oracle,
10,000-entry batches — is the built half; router-level permissions
(mount-wide and per-prefix, enforced before dispatch; ADR 006) are
built; principals (spec 070) are not built; row-level grants (ADR 021 →
spec 058) are proposed; the versioning-as-audit story is designed and
partial. The governed half is the half the market is buying.

One more constraint: Databricks launched Unity AI Gateway in June 2026,
governing agents, MCP services, skills, and tools through Unity
Catalog. "Unity Catalog for agents" is, in effect, already their
tagline, so the analogy has to be used in a meeting and kept off the
homepage.

## Options considered

The names, against the memo's criteria — says *bounded/governed*; says
*what the agent touches* (data and tools, not the loop); a noun nobody
has claimed; works for a developer and a security buyer; no "agentic"
(Gartner's "agent washing" word):

- **The access layer for agents** — "access" is the buyer's own word
  (least privilege, access control, data access); "layer" places vfs
  in the path rather than above it; unclaimed; a developer reads an API
  surface and a CISO reads an enforcement point; leads with the built
  half without lying about the rest. **Chosen as the category.**
- **The governed namespace for agents** — the truest phrase (Plan 9:
  the namespace *is* the policy) and the one word that covers files,
  rows, and tools at once; but "namespace" is a developer's word, not a
  buyer's. **Runner-up; kept as the mechanism line.**
- **The agent's operating environment** — acceptable: OS framing,
  singular, no "agentic"; does not name the pain. Not taken.
- **Governed agentic environments** — close, not best: "environment" is
  half-claimed by the sandbox vendors, "agentic" is worn out, and the
  plural reads as a category rather than a product. Rejected.
- **The agentic capability plane / layer** — "capability" reads as
  *giving* agents powers (Composio, Arcade); MCP uses "capabilities" for
  feature negotiation; Futurum uses "capability layers"; "capability
  plane" is not an established plane. Rejected.
- **Agent control plane** — reads as fleet management; the category is
  owned by Google/IBM/Forrester; names the smallest part of vfs.
  **Rejected for the library; kept for the subsystem** — the
  mount/permission/grant machinery, which is what the 2026-07-22
  prior-art memo already calls it.
- **Agent sandbox / workspace** — E2B, Modal, Anthropic, and Box are
  standing on those nouns. Rejected.
- **Agent catalog / registry** — now means *a list of agents*
  (Microsoft Agent 365, Credo, TrueFoundry), the opposite direction.
  Rejected as a name for the plane; "catalog" alone survives, see
  below.

The product shape:

- **One product: the library carries the admin story too** — every
  panel Clay wants (what is mounted, who can reach what, which tools
  live where, what changed) would be a library API with no home.
  Rejected: a layer enforces; a plane shows and decides; they are
  different products with different buyers and different licences.
- **Layer and plane as two products** — the library in the data path,
  a catalog above it reading the library's introspection surface. This
  is the July company memo's OSS-funnel / paid-plane split given a
  concrete shape. **Chosen.**

The Databricks framing:

- **"Unity Catalog for agents" as the tagline** — useful in a meeting,
  bad on a homepage: it hands Databricks the frame, and they have
  already claimed the agent story. Rejected as a public line; kept as
  an explanation.
- **Say the differentiation out loud** — DSN vs Databricks, paths vs
  tables, inside vs above. **Chosen.**

## Decision

1. **The category is "the access layer for agents."** It is the first
   line of the README and the phrase vfs is described with wherever a
   category is asked for. It says the library sits *in the path* — in
   process, at the routing chokepoint, before dispatch — and that what
   it does there is decide access. It does not say "agentic", and it
   does not say "control plane".

2. **The mechanism line is the namespace.** The one sentence under the
   category is: *One namespace of everything an agent can see, search,
   and change. You decide what's in it.* What an agent can see is what
   it can do; a tool is a path (`run`), so tool access falls out of the
   same rule; tenant isolation is a permission layer, not a path prefix
   (ADR 006). "Namespace" is the mechanism word in every doc, and
   "governed namespace" is the phrase to reach for when "access layer"
   needs unpacking.

3. **The third line places vfs in the stack a buyer already knows.**
   *Frameworks build the agent. Control planes set the policy. Gateways
   check the tool call. vfs enforces it on the data itself — the files,
   rows, and tools the agent actually touches.* The relationship to the
   control-plane vendors is complementary and is stated that way. The
   full three-line stack (memo §5) is the README's opening and the
   canonical form; the lines are not to be paraphrased apart from each
   other in public copy.

4. **"Control plane" is reserved for the subsystem, never the
   library.** In vfs's own vocabulary it names the mount, permission,
   and grant machinery — namespace construction (mount, bind, unbind,
   remount), the `PermissionMap` and its enforcement before dispatch,
   grants once ADR 021 is ratified, principals once spec 070 lands —
   exactly as the 2026-07-22 prior-art memo uses it. The library as a
   whole is not called a control plane, and the market's "agent control
   plane" (the fleet-management category) is referred to only in the
   third line's sense, as something vfs complements.

5. **Two products: the layer and the plane.** The library **enforces**
   — every read, search, write, and tool call passes through it;
   in-process, `pip install`, the OSS funnel. The admin product **shows
   and decides** — what is mounted, who can reach what, which tools live
   where, what changed and when; it lives above the library and reads
   its introspection surface. Working names: **vfs** for the layer and
   **vfs Catalog** for the plane. "Catalog" is the right *kind* of word
   (the place you go to see what exists, who can see it, and where it
   came from) and is a category word, not a brand — the product needs a
   name of its own, and "agent catalog" is not it (pin above). The
   plane's v1 is a read-only viewer over what the library already
   knows: namespace, mounts, permission rules, tools at paths, edges —
   growing one panel per shipped subsystem without renaming anything.

6. **The Databricks differentiation is said out loud**, in this order:
   Unity Catalog requires Databricks, vfs requires a DSN — it governs
   the Postgres, SQL Server, and Oracle an organisation already runs,
   with no lakehouse and no migration; Unity Catalog governs the
   lakehouse from above, vfs governs the namespace from inside, so
   enforcement is physical, not advisory; Unity Catalog governs tables
   and bolted files on, vfs governs paths — what agents actually
   navigate; and vfs is open and embeddable. "Unity Catalog for agents"
   is an explanation for a meeting and never a headline.

7. **Positioning points where we are going; the README says what is
   real.** The category leads with governance because that is the
   pain; the alpha banner names the built half (the search verbs on the
   database backend; router-level mount and per-prefix permission) and
   the designed-not-built half (principals, row-level grants, tools at
   paths) in the same breath. No public line claims an enforcement
   feature the tree does not have.

8. **The buyer is July's.** Platform and AI-infra teams stalled in
   security review — the 86.9 %-delayed, 14.4 %-fully-approved reader
   of the survey — not the June memo's data engineer. June's
   *distribution* insight survives unchanged: developer-first,
   `pip install`, a permissive core as the funnel; only the persona
   changes.

## Consequences

- **The README opens with the three-line stack** (landed with this
  record): the category as the title, the mechanism line and the
  stack line as the tagline, and an alpha banner that says which half
  is built. "Agentic Search on your Database" and "glob, grep, glean,
  and graph are the four verbs any agent needs" are gone from the
  opening; the four verbs stay as the search section, which is where
  they belong.
- **`standards/mission.md` is now out of step.** Its thesis line, "VFS
  is the agentic filesystem", uses the word this record retires from
  category lines, and its target-user section is the June buyer. This
  record does not edit a standard; a mission revision (v0.2) that
  carries the category, the layer/plane split, and the July buyer is
  the follow-up, and it should re-examine the non-goal "we are not a
  managed service" against the plane (the *library* is still never a
  managed service; the plane may be).
- **Sequencing.** The memo's reading is that if the governed half is
  what we sell, principals (spec 070) and grants (ADR 021 → spec 058)
  move ahead of further search work, and C7 introspection — publishing
  what the router already computes (`mounts()` exists; the permission
  map, tools at paths, and versions do not yet have a read surface) —
  is the Catalog's prerequisite and cheap. This record carries that as
  a consequence, not a ruling: `[NEEDS CLARIFICATION: the memo does not
  itself decide search-first vs governance-first. Does the glean arc
  (specs 132–137) finish before spec 070, ADR 021's ratification, and
  spec 058 start, or do they move ahead of it now? And does C7
  introspection land as its own spec before either?]` The roadmap and
  `specs/STATUS.md` own the answer; this record only says the
  positioning pulls toward governance.
- **ADR 021 is still proposed.** Naming grants as part of the control
  plane subsystem does not ratify the grant spine; spec 058 still waits
  on Clay's acceptance of ADR 021, as that record says.
- **Easier:** one category word for every surface (README, PyPI
  description, MCP server description, talks); a clean answer to "how
  are you different from a control plane / a gateway / Unity Catalog";
  a product boundary for the admin UI that does not leak into the
  library's API.
- **Harder:** the category promises enforcement the tree only partly
  has, which makes the banner's honesty load-bearing until spec 070 and
  spec 058 land; every public sentence now has to be checked against
  pin 7.
- **Committed to:** "the access layer for agents" as the category;
  "namespace" as the mechanism; "control plane" only for the
  mount/permission/grant subsystem; "vfs" and "vfs Catalog" as working
  names with the plane's real name open; the four Databricks
  differentiators as the standing answer; no "agentic" in a category
  line; no "agent catalog", "sandbox", or "workspace" as the noun.
- **Not decided here** (pointers in `../open-questions.md`): the
  plane's real name; whether the Catalog is open source with paid
  hosting or closed; the plane's pricing and licence line; the
  search-first vs governance-first sequencing above.
