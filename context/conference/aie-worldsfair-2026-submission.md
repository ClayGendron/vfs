# AI Engineer World's Fair 2026 — Talk Submission Working Doc

- **Status:** draft (v0.1) — seeded 2026-04-30
- **Owner:** Clay Gendron
- **Conference:** AI Engineer World's Fair 2026, San Francisco, June 29 – July 2, 2026
- **Submission portal:** https://app.ai.engineer/e/ai-engineer-worlds-fair-2026/speaker-registration
- **Final deadline:** May 30, 2026 (first-draft deadline April 12 already passed; submissions still open)

---

## 1. Logistics quick-ref

| Field | Value |
|---|---|
| Format target | Stage Talk, 15–20 min (no on-stage Q&A) |
| Tracks to submit to | Search & Retrieval (primary), Graphs, Enterprise (multiple submissions are encouraged) |
| Length cap on abstract | Sessionize standard — keep < 1500 chars per abstract; ~600–900 is the sweet spot |
| Speaker bio | One short paragraph, third person, with one credential and one specificity |

---

## 2. Title — kill the working title, pick a stance

**Working title (do not submit):**
> "The Enterprise Knowledge Warehouse: How to compose semantic search, graph traversal, and file systems to build the AI enabled enterprise"

**Why it fails the AIE WF bar:**

- 21 words. swyx's published advice is "what rolls off the tongue."
- Colon used as setup-payoff crutch (explicitly flagged in dx.tips/titles).
- "compose," "build the AI-enabled enterprise" — the "leveraging / towards" family.
- Survey-shaped. Names a category, not a takeaway. Accepted titles name a number, a domain, a stance, or a death.

**Title options, ranked. Pick one for primary, vary the others across the three track submissions:**

1. **"Unix Beats RAG. Engineer Data as a File System."** — primary. Two short sentences: a historical stance ("X beats Y" is a swyx-favored shape) plus a concrete imperative. Six words then five. No colon, no "leveraging," no vague benefit. Reads aloud cleanly. Matches the brand voice exactly.
2. **"Your Filesystem Is Your RAG."** — strong backup. Stance, claim-shaped, four words.
3. **"Stop Building RAG Pipelines. Mount Your Knowledge."** — imperative + reframe. Pairs well with the Search & Retrieval track.
4. **"One Namespace, Three Indexes: Vectors, Graphs, and Files Under `ls`."** — for the Graphs track; surfaces the trifecta. The colon here separates a count claim from a concrete payload, not a vague benefit.
5. **"The Knowledge Warehouse Is Dead. Long Live the Knowledge Filesystem."** — for the Enterprise track. Provocation works on that audience.

Avoid: any title containing *enterprise*, *leveraging*, *composable*, *unified platform*, *seamless*, *next-gen*. The brand doc bans them; the conference desk-rejects them.

---

## 3. Abstract — three angles, same talk

Each is ~700 chars. Lead with a stance, name the problem in one sentence, name the architectural move in one sentence, name the proof in one sentence, name the takeaway in one sentence. No bullets in the submitted abstract — Sessionize renders flat prose better.

### 3a. Search & Retrieval track — "Unix Beats RAG. Engineer Data as a File System."

> Agents that operate on enterprise knowledge end up as the integration layer between a vector store, a graph database, a versioned blob store, and an auth service — paying for that integration in context tokens, latency, and bugs. VFS collapses the four into one identity model: every chunk, every embedding, every graph edge, every version is a path. `grep`, `glob`, semantic `search`, and graph `traverse` return the same result type, composable with set algebra (`&`, `|`, `-`). We'll walk through how a Unix-shaped retrieval surface changes what an agent can do over a long horizon — and show the production deployment behind it: `[METRIC: corpus size, query latency, agent task success delta]`.

### 3b. Graphs track — "One Namespace, Three Indexes."

> Vector search finds what's similar. Graph traversal finds what's connected. Filesystems hold the canonical bytes. Today these live in three systems with three identity models — and the agent ends up reconciling them at runtime. This talk shows how to fuse all three into one namespace where graph nodes, vectors, and files share paths, return one result type, and compose with `&`, `|`, `-`. We'll cover the schema (one table, kinded entries, longest-prefix mount routing), the query model (lazy AST that pushes down to the underlying database), and the production numbers from `[DEPLOYMENT]`: `[GRAPH HOPS, RECALL@K, P95]`. Code is open source (`pip install vfs-py`).

### 3c. Enterprise track — "Stop Building RAG Pipelines. Mount Your Knowledge."

> Every Fortune 500 AI initiative ends up shaped the same way: a pipeline that ETLs documents into a vector store, a separate ingestion into a graph database, a third path for canonical files, and an ACL system that none of the three agree with. The pipeline is the bug. We replaced the pipeline with a virtual filesystem that mounts existing data sources — Postgres, MSSQL, SharePoint, Slack — into one namespace, indexes them in place, and exposes one MCP tool to agents. `[N]` engineers, `[Y]` corpora, `[Z]` agents in production, no new database. This is a talk about deleting infrastructure, not adding it.

---

## 4. Talk arc (15–20 min target)

| Min | Beat | What's on screen |
|---|---|---|
| 0:00 – 1:30 | **Cold open: the four-system slide.** Vector DB, graph DB, blob store, auth service, with arrows looping back through the agent. "This is the bug." | Diagram |
| 1:30 – 3:00 | The pitch in one slide: every chunk, version, edge, embedding is a path. One result type. One MCP tool. | `ls /docs/policy.md/.chunks/` live in a terminal |
| 3:00 – 6:00 | **The architectural move.** Single `vfs_entries` table, `kind` discriminator, longest-prefix mount routing, terminal-vs-delegating method pattern. Why one table beats four. | Schema slide + base-class slide |
| 6:00 – 10:00 | **The composition story.** `glob`, `grep`, `search`, `traverse` all return `VFSResult`. Live demo: `search(query) & traverse(path, depth=2) - glob("**/*.test.ts")`. | Terminal session, real corpus |
| 10:00 – 13:00 | **The agent payoff.** Same demo, this time driven by an LLM through one MCP tool. Token savings vs. multi-tool RAG. Long-horizon write/restore. | Side-by-side context-window diff |
| 13:00 – 16:00 | **Production numbers.** `[DEPLOYMENT]` corpus size, query latency, recall, agent task success. What broke and what didn't. | Numbers slide |
| 16:00 – 18:00 | **The harder claim.** Filesystem semantics aren't a metaphor — they're the cheapest available identity model that agents already understand. Unix won; let it win again. | One-line slide |
| 18:00 – 19:30 | Where to start: `pip install vfs-py`, the FSP MCP server, the open questions. | Install + GitHub + email |

**Demo discipline:** the live demo is the talk. Slides exist to label what just happened in the terminal. Three-screen rule: terminal, diagram, terminal.

---

## 5. Speaker bio (placeholder — needs your fill-in)

> Clay Gendron builds VFS (`vfs-py`), an open-source virtual filesystem that mounts heterogeneous enterprise data into a single namespace for AI agents. Previously `[ROLE]` at `[COMPANY]`, where he `[ONE-SENTENCE PROOF — built X for Y users / shipped Z system]`. He thinks Plan 9 was right and is annoyed it took the industry 30 years to need it.

The last sentence is optional swagger; cut if it doesn't match how you want to show up. The "Plan 9 was right" line is on-brand for the project and signals technical depth, but it's a vibe choice.

---

## 6. What you still need to gather (the gap between this draft and submission)

This is the work between here and "submit." Numbers are what flips intersection-talk submissions from accepted to keynote-adjacent.

1. **One quantified deployment.** A real corpus, real users, real metric. Examples that would land:
   - "We indexed 4.2M documents across 14 Postgres + SharePoint mounts in 38 minutes."
   - "Agent task success on `[BENCHMARK]` rose from 61% (multi-tool RAG) to 78% (single-MCP VFS)."
   - "P95 retrieval latency on a 1.1M-chunk corpus: 84ms across vector + BM25 + graph."
   - If there is no production deployment yet, a benchmark on a public corpus (HotpotQA, MuSiQue, RobustQA — Sam Julien's 86.31% was on RobustQA) is the next-best thing.
2. **One named user / design partner**, even if just "an investment bank's research team" or "an internal Fortune 500 platform team." Anonymous is fine; vague is not.
3. **One screenshot of the live composition.** Terminal session of `search & traverse - glob` returning real results. This is the slide that sells the talk.
4. **A commitment to record the talk on time.** AIE WF requires pre-recording readiness; missed recording windows are a common reject reason on resubmission.
5. **Confirm the final title.** Submit with #1 ("Your Filesystem Is Your RAG.") as primary unless you have a stronger stance ready.

---

## 7. Submission checklist

- [ ] Pick final title (default: "Unix Beats RAG. Engineer Data as a File System.")
- [ ] Fill `[METRIC]` / `[DEPLOYMENT]` / `[N/Y/Z]` placeholders in all three abstracts with real numbers
- [ ] Write speaker bio with real prior role + one proof point
- [ ] Capture demo screenshot for submission
- [ ] Submit Search & Retrieval variant (primary)
- [ ] Submit Graphs variant
- [ ] Submit Enterprise variant
- [ ] Optional: submit a 5-min Lightning version of the same idea — high acceptance rate, hedges the bet
- [ ] Tag submissions with `open-source`, `production`, `MCP` where the form allows

---

## 8. Sources backing this draft

- AIE WF 2026 site — https://www.ai.engineer/worldsfair
- AIEWF 2025 CFP (Sessionize) — https://sessionize.com/ai-engineer-worlds-fair-2025/
- swyx — CFP Advice — https://www.swyx.io/cfp-advice
- swyx / dx.tips — Stop Writing Long Boring Titles — https://dx.tips/titles
- swyx — Organizing AIEWF 2024 (rejection patterns) — https://www.swyx.io/aiewf-2024
- Latent Space — AIEWF 2025 Keynotes recap — https://www.latent.space/p/aiewf-2025-keynotes
