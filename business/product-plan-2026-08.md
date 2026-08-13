# The Two-Hat Product: What We Sell Around VFS

- **Status:** draft (v1.0) — 2026-08-07
- **Purpose:** Answer "VFS is open source — what's the product?" with a plan
  that keeps the enterprise console as the revenue line while adding the
  user-facing surfaces (file browser, docs) that make VFS feel like a
  premium product rather than a library.
- **Method:** Three parallel research agents (competitive landscape,
  open-core business playbook, surface build costs), all findings dated
  2026-08-07 with sources, synthesized against
  `context/research/2026-07-13-company-analysis.md` (the 20-agent
  adversarial company analysis) and the product discussion of 2026-08-07.
- **Relationship to the July memo:** This plan keeps the July memo's core
  (BYOC governed mount plane, Postgres wedge, three gates) and **amends one
  standing decision**: user-facing *surfaces* (browser, docs) are in scope
  as demand generation and demo; agent *harnesses* (chat UIs) remain out.

---

## 1. Thesis

**Sell to the admin, delight the user.** One web application, two hats:

- **The admin hat** — a single pane of glass over everything agents can
  touch: every mount, agent, principal, permission, and audited action;
  every write versioned and reversible. This is the invoice.
- **The user hat** — a Dropbox-quality file surface over the same
  namespace: browse, preview, upload, share, restore, edit docs. Anything
  a user stores is automatically available to their agents, under the same
  permissions. This is demand generation, retention, and the live demo of
  the thing the admin is paying for.

The precedent is the standard enterprise two-audience play (Slack, Notion
Enterprise, M365) executed the open-core way (Supabase Studio over
Postgres). Users pull the product in through shared links and a pleasant
surface; admins buy because of the pane; agents ride along via MCP with
the same principals and audit trail.

**The one-sentence differentiation** (from the competitive research — the
square nobody occupies): *a governed, open-source data plane where agents'
reads and writes, the permission model, and the audit/version history are
the same system — over the SQL databases enterprises already run.* Every
adjacent player has exactly one piece: gateways and identity vendors audit
actions but own no data; workspace incumbents permission agents only
inside their own silo; Mesa versions writes but only in its own greenfield
store; TigerFS versions writes on one engine as a cloud funnel. The audit
log here isn't a reconstruction of what happened somewhere else — it is
the storage engine's own history.

## 2. What the invoice says (the paid line)

The research across Supabase, Grafana, Coder, n8n, LangSmith, Logfire,
Temporal, and Langfuse found a near-uniform paid line — the same trio at
six of seven comparables:

1. **SSO into the console** (IdP/SAML/OIDC binding, SCIM) — note the
   split Supabase draws: auth features *for your app's users* are cheap or
   free; SSO *into the admin surface itself* is the org tier.
2. **Audit** — aggregation, retention ladders, SIEM/log streaming export.
3. **Multi-org / fleet RBAC** — custom roles, org-scoped permissions,
   quotas, HA. Coder's line is the cleanest model: *one org free,
   unlimited users; many orgs, audit, and IdP group-sync paid.*

Applied to VFS:

| | Free (OSS + personal tier) | Paid (org tier / BYOC) |
|---|---|---|
| Library, MCP server, all verbs | ✅ forever | — |
| Versioning, trash, restore | ✅ | — |
| Path-prefix permissions, basic principals | ✅ | — |
| Console, single org | ✅ (open source, like Supabase Studio) | — |
| File browser + doc surface | ✅ personal namespace | — |
| SSO/IdP binding into the console, SCIM | — | ✅ |
| Audit aggregation, retention, SIEM export | — | ✅ |
| Multi-org fleet view, custom roles, quotas | — | ✅ |
| Row-level / per-principal grant management UI | — | ✅ |
| BYOC gateway container + control plane | — | ✅ |

Two rules from the failure-mode research guard this line:

- **Never cripple the core** (RethinkDB's lesson inverted; CockroachDB's
  free-tier-cannibalization retreat noted as the risk on the other side).
  Failures cluster where the free artifact *is* the whole product;
  survivors sell an operational surface — fleet management, compliance —
  that the free artifact makes *necessary* at org scale.
- **Never price the user surface.** The moment the browser/docs surface
  costs per-seat money, we are in the seat war against free-bundled
  Microsoft/Google/Notion. The user hat is free; the org machinery around
  it is not.

## 3. Pricing (benchmarked, mid-2026)

Two archetypes exist; we use the tiered one (Supabase/n8n shape) because
BYOC deployments don't meter cleanly:

- **Free** — OSS everything + hosted personal namespace with the browser
  surface. (Grafana's math: every free instance is a trial underway;
  they convert 1–3% of 1M+ OSS instances into $250M+ ARR.)
- **Pro, ~$25–50/mo** self-serve — small team, single org, hosted
  convenience. Sits in the $25–79 cluster where AI dev-infra entry pricing
  lives, and far under the p-card threshold.
- **Team/Org, ~$500–700/mo** self-serve ceiling — the governance cliff
  (SSO-into-console, audit aggregation, multi-org). Comparables: Supabase
  Team $599, n8n Business €667, Langfuse Teams $499. Research synthesis on
  procurement: **≤ ~$500–$1K/mo (~$6–12K/yr) clears a platform-team card
  without procurement** (p-card limits $500–5K; card-vs-PO threshold mode
  $15K/yr).
- **Enterprise BYOC** — annual commit, sales-led, unpublished price (every
  mature BYOC vendor gates it: ClickHouse, Redpanda, MintMCP). Benchmarks:
  agent-security enterprise deals typically $20–80K/yr (Prompt Security
  costbench); Teleport median ACV ~$51K. VPC deployment is a *tier
  attribute of the contract*, not a pricing-page row (Arcade's model).
- **Design pilots (first revenue, H2 2026–H1 2027):** $3–5K/mo on
  non-production replicas — consistent with the July memo and with pilot
  research (charge 10–50% of eventual contract value, 60–90 days, MOU with
  a conversion clause and a hard go-paid deadline; free pilots stall).

**Security review before SOC 2:** the evidence pack that substitutes —
documented system boundary, a recent pen-test report with remediation
status, a concise control narrative, and a dated SOC 2 roadmap. CSA STAR
Level 1 self-assessment is free and answers many questionnaires. BYOC
materially narrows the questionnaire (credentials never leave the customer
network) but does not eliminate it — the control plane still touches
metadata. SOC 2 Type I ($7.5–60K, 3–6 months) closes deals while the
Type II observation window runs. Budget this at seed, not before.

## 4. The surface ladder (build / defer / skip)

Engineer-month figures are AI-assisted solo-dev estimates from the build
research (3–5x on greenfield UI, ~1.5x on polish, ~1x on sync engines).

| Rung | Verdict | Cost | Notes |
|---|---|---|---|
| 1. Admin console | **Build** (it is the product) | 2–3 em | shadcn/ui foundation ± Refine (MIT); `@git-diff-view/react` for versions. The hard part is *design*, not code: the path-scoped permission editor (principals × subtrees, inheritance, effective-permission preview) has no off-the-shelf equivalent — study SpiceDB Playground. React-Admin ruled out (its RBAC/audit/history modules are paid EE). |
| 2. File browser | **Build** (the Dropbox hat) | ~3 em | No embeddable whole-app exists (Filestash AGPL; FileBrowser dead — archives Sept 2026 after share-link CVEs; its post-mortem is our cautionary tale). Assemble from MIT blocks: Uppy, react-pdf, Shiki, react-markdown, virtualizer. Virtualization from day one (ETL users guarantee 10k-entry dirs). Share links are permission grants — the server contract is security-critical. |
| 3. Doc editor, single-user | **Build second** | 0.5–2 em | CodeMirror 6 (perfect markdown fidelity) or Milkdown/Crepe (WYSIWYG, remark AST as document model). A wrong save is a restore. The real design problem is the save-conflict UX for *agent-writes-while-human-edits* — our primary scenario. |
| 4. Real-time collab (CRDT) | **Defer** until revenue + hire | 4–8 em + permanent stateful service | The 1-week Yjs demo is a trap; CRDT-vs-file-version reconciliation is so hard the one company doing it (Relay) keeps it proprietary. If ever: file-canonical at rest, Y.Doc per session, serialize back through the normal write path. |
| 5. Desktop access | **Build the bridge, skip the engine** | 0.5–1.5 em (+~1) | WsgiDAV (MIT, Python, custom storage providers — plugs onto our storage layer) + documented `rclone mount` recipes. High-leverage trick: KaraDAV proves implementing Nextcloud's client-compat API gets their mature desktop sync client (conflicts, GUI, tray) for ~1 em. Full bespoke sync: 6–12+ em where AI tooling barely helps; one data-loss bug ends trust. Do last, if ever. |
| 6. Chat view / harness | **Never** (standing decision, upheld) | — | Labs own the harness. Claude, ChatGPT, Copilot are the chat surface; VFS reaches all of them through one MCP server. Deep-link into them. |
| 7. Notion-style databases / app builders | **Skip indefinitely** | — | The full Notion war; moat inverts. Skills need no UI — a skill is files at `/.agents/skills/`, so the browser already is the skill manager. |

**Sensible portfolio (rungs 1–3 + 5): ~6–9 engineer-months.** Adding CRDT
collab and a real sync client roughly triples it — that is the capacity
argument for the defer/skip lines, not just taste. Structural advantage
worth advertising: server-side versioning + trash converts the worst
failure modes of the two hardest surfaces (sync, collab) from data loss
into recoverable annoyance.

## 5. Competitive position

Four groups, one summary line each (full findings in the research packet;
all statuses as of Aug 2026):

- **Agent-filesystem cohort.** Mirage (3.4k stars, ~50 shallow connector
  mounts, no versioning/governance/commercial layer), TigerFS (Postgres-
  only, experimental, a Tiger Cloud funnel), Turso AgentFS (per-agent
  SQLite scratchpad — nearly complementary), AGFS (side project), Mesa
  (the real competitor: production design partners, published pricing
  [$0.20/GB/mo], Git-semantics filesystem — but a silo your data must
  migrate into). **Nobody mounts existing SQL engines in place with
  governance.**
- **Workspace incumbents.** "Agents see what the user sees" is table
  stakes *inside each silo*: Notion agents run with the user's exact
  permissions ($20/seat + credits), Microsoft Work IQ guarantees the index
  creates no new access rights ($30/user + credit packs), Google and Slack
  equivalent. Dropbox Dash is the cautionary tale (Q1 2026: contribution
  "limited") *and* proof the category is live. None mounts your databases;
  none offers reversible agent writes; none is self-hostable.
- **Governance/gateway/identity players.** Arcade ($60M) audits tool
  calls it doesn't own; MCP gateways proxy traffic; identity vendors
  (Okta/WorkOS agent GA products) sell *who the agent is*. Four
  acquisitions in ~9 months (SGNL→CrowdStrike ~$740M, Astrix→Cisco,
  Prompt→SentinelOne, Natoma→Snowflake) mean every security platform will
  sell an "agent actions audited" console within a year — **all of them
  stopping at the tool/credential boundary, none owning the data plane.**
- **Open-core comparables.** Every 2026 valuation pop in the set
  (Supabase 2x to $10.5B, n8n 2x to $5.2B after SAP, Coder/KKR $90M) came
  from repositioning existing infra as *the governed substrate under AI
  agents*. That is VFS's native story, not a pivot.

**Three threats, 12-month horizon:**

1. **Mesa's commercial velocity** — if it adds an MCP surface and an
   SQL-mount story before our console ships, it names the category. Counter:
   make "mount the database you already have — no migration" loud now.
2. **A database vendor bundling good-enough** — TigerFS graduating from
   experiment, Snowflake closing Natoma, Turso's disaggregated direction.
   Counter: engine-agnostic BYOC is the one thing a single-engine vendor
   structurally can't match; speed matters.
3. **Security platforms defining the console vocabulary first** via M&A.
   Counter: don't fight for the CISO's budget; sell the platform team the
   pane that governs *data*, and integrate with (consume) the identity
   vendors rather than competing.

Third-party validation worth citing in every pitch: Amplify's "File
systems for agents" thesis (May 2026) demands multi-agent isolation,
query over unstructured data, dynamic access control, and scale — a spec
that maps almost 1:1 onto VFS's shipped + planned surface, and none of the
companies it names occupies the full square. Box shipping an agent
security/governance suite (July 2026) validates the single-pane thesis —
scoped to Box's silo.

## 6. Motion and timeline

The PLG-to-enterprise pattern across Pydantic/Logfire, PostHog, Plausible,
Cal.com, Supabase, and Grafana: **polished free/user surface ships first;
the enterprise plane trails by 18 months to 4 years; 1–8% of free users
ever pay; founder-led sales carries to ~$1M ARR** (median sales handoff
~$1M; no VP Sales before $3–5M). Supabase's sequence is the template:
dashboard in month 5 (credited with making Postgres approachable), Studio
open-sourced month 23, Enterprise month 26.

Mapped onto the July memo's gates (which stand):

- **Gate 1 (Q3 2026) — unchanged: ship the wedge.** 0.1.0: Postgres
  backend, MCP trio, fresh PyPI release, benchmark, quickstart. No surface
  work before this; the substrate is the funnel.
- **Gate 2 (Q4 2026) — governance in OSS + the first surfaces.** Verified
  principals, audit journal, versioned writes live — and alongside them,
  the console v1 (single-org, open-sourced) and the file browser v1. The
  October talks are the marketing moment; the browser demo ("I share a
  wiki page with a grant; my agent reads it through the same grant") is
  the asset. Open 3–5 design-partner conversations.
- **Gate 3 (Q1–Q2 2027) — convert.** 2–3 paid pilots at $3–5K/mo with MOU
  conversion clauses; BYOC gateway MVP with the paid trio (SSO/audit/
  fleet); doc editor cheap tier; pen-test + CSA STAR + SOC 2 Type I
  started; seed raise on named users + pilot revenue; first hire.
- **Post-hire:** WebDAV/Nextcloud-compat desktop bridge, then revisit
  CRDT collab. Bespoke sync engine: only ever with a team.

**Capacity check (the honest constraint):** Gate 2 now contains both the
governance backend work and ~5 engineer-months of surface work. The July
memo's sharpest finding — every plan exceeded solo capacity 3–4x — still
binds. The mitigations: the console and browser are the *same app* on the
same API; rungs are strictly sequential (console before browser before
editor); each has a demo-grade checkpoint (~half the polished estimate)
sufficient for talks and pilots; and anything on the defer/skip lines
stays there until the first hire.

## 7. What must be true (falsifiable)

1. 0.1.0 (four verbs + MCP) lands before the October talks — the entire
   funnel and both talks depend on it.
2. The paid trio is what pilots actually ask for. If design partners ask
   for something else (e.g., row-level grants UI, table projection), the
   paid line moves to match — the *line placement* is the experiment.
3. The browser surface measurably drives adoption (share-links create
   accounts; quickstart completions rise). If it doesn't move numbers by
   Q1 2027, stop investing in rungs 3+ and double down on the console.
4. Mesa doesn't ship SQL-mounting + MCP before our console v1; no
   incumbent ships cross-vendor governed DB mounts inside the window.
5. 2–3 pilots convert at ≥$3K/mo by mid-2027. Fewer than ~10 named teams
   running VFS against a real Postgres by end of Q4 2026 → flip to direct
   pilot sales on the governed demo (July memo checkpoint, upheld).

## 8. Open questions

- **Console licensing:** open-source the single-org console entirely
  (Supabase Studio model, recommended: it keeps the OSS artifact whole and
  the trust story clean) vs. source-available. Decide before console v1
  ships; changing later is the Airbyte/CockroachDB squeeze story.
- **Hosted personal tier timing:** a hosted free namespace is the best
  browser demo but adds ops + abuse surface pre-hire. Alternative: local
  `uvx vfs serve` + browser as the "personal tier" until the seed.
- **Naming:** the product (console + surfaces) likely wants a name that
  isn't "vfs" (the library). Defer until Gate 2; don't brand before the
  wedge ships.
- **Table projection:** still the durable differentiator vs Mesa/Turso/
  Mirage (July memo §3) and still unbuilt. It outranks every surface rung
  except the console if a pilot pulls it.

---

## Appendix: key sources

Competitive: [Mirage](https://github.com/strukto-ai/mirage) ·
[TigerFS](https://tigerfs.io/) · [Mesa pricing](https://www.mesa.dev/pricing) ·
[Turso AgentFS](https://turso.tech/blog/agentfs) ·
[Box agent governance](https://blog.box.com/introducing-box-agent-security-and-governance) ·
[Notion custom agents](https://www.notion.com/help/custom-agents-security-features) ·
[MS Work IQ](https://www.microsoft.com/en-us/microsoft-365/blog/2026/06/02/announcing-the-new-work-iq-apis/) ·
[Dropbox Dash plans](https://dash.dropbox.com/plans) ·
[Arcade Series A](https://www.businesswire.com/news/home/20260615229631/en/Arcade-Raises-$60M-to-Become-the-Secure-Action-Layer-Behind-Every-Production-AI-Agent) ·
[Amplify thesis](https://www.amplifypartners.com/blog-posts/file-systems-for-agents)

Playbook: [Supabase pricing](https://supabase.com/pricing) ·
[Coder pricing](https://coder.com/pricing) ·
[Grafana enterprise](https://grafana.com/docs/grafana/latest/introduction/grafana-enterprise/) ·
[n8n pricing](https://n8n.io/pricing/) ·
[Bessemer OSS roadmap](https://www.bvp.com/atlas/roadmap-open-source) ·
[Buyer-based open core](https://www.opencoreventures.com/blog/open-core-is-a-misunderstood-business-model) ·
[sso.tax](https://sso.tax/) ·
[WarpStream BYOC pricing](https://www.warpstream.com/pricing) ·
[Nuon BYOC hard parts](https://nuon.co/blog/byoc-hard-parts/) ·
[Design-partner playbook](https://www.bvp.com/atlas/design-partners-the-pre-launch-edge-most-ai-founders-ignore) ·
[Pre-SOC-2 sales](https://sudarshana.io/blog/do-i-need-soc-2-for-enterprise-sales-before-my-first-enterprise-customer) ·
[Grafana funnel](https://www.reo.dev/blog/the-quiet-wedge-that-took-grafana-to-250m-in-a-crowded-market) ·
[Supabase Studio history](https://supabase.com/blog/supabase-studio) ·
[RethinkDB post-mortem](https://gist.github.com/ramalho/93b87e961b6e019be8e1f6f82864b6f9) ·
[CockroachDB license change](https://www.cockroachlabs.com/blog/enterprise-license-announcement/)

Build costs: [shadcn-admin](https://github.com/satnaing/shadcn-admin) ·
[Refine](https://github.com/refinedev/refine) ·
[FileBrowser post-mortem](https://hacdias.com/2026/07/28/filebrowser/) ·
[Milkdown](https://milkdown.dev) ·
[WsgiDAV](https://github.com/mar10/wsgidav) ·
[KaraDAV](https://github.com/kd2org/karadav) ·
[Dropbox sync rewrite](https://dropbox.tech/infrastructure/rewriting-the-heart-of-our-sync-engine) ·
[SpiceDB Playground](https://authzed.com/blog/spicedb-playground-is-open-source)
