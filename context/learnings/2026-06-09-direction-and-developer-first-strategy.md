# Direction review + developer-first platform strategy

> Date: 2026-06-09
> Scope: project direction — review of the refactor wave (stories 015/031/032/033,
> `paths.py`, `models2.py`, `base2.py`), the mid-2026 competitive landscape for
> agent filesystems and agentic search, and a strategy for making VFS a
> developer-first platform for data engineers with an org/enterprise product on top.
> Trigger: "review recent work — is it going in the right direction? Research
> online and recommend a direction. How do we make VFS developer-first, leaning
> on 'building agents is a data engineering problem'?"
> Companion to [`2026-06-03-turbopuffer-architecture.md`](./2026-06-03-turbopuffer-architecture.md).

## If only one sentence survives

The refactor is converging on genuinely good fundamentals and the market has
validated the core thesis — "filesystem as the agent interface" went from
contrarian to consensus in under a year — but the differentiators (glean + graph
inside the namespace, MCP mounts) are unshipped while the window is open, so the
next quarter should optimize for **shipping a vertical slice of all four verbs
over Postgres exposed via MCP**, wrapped in a **zero-config, Arrow-speaking,
CLI-and-MCP-first developer experience** aimed at data engineers, with the
paid layer (SSO/RBAC/console/audit) kept strictly out of the OSS core.

---

## Part 1 — Review of recent work

### Code: converging, quality is high

The last ~15 commits plus the working tree form a coherent arc:

- **`paths.py` is the strongest module.** `VFSPath` as a validated `str`
  subclass minted only through the `resolve_path` gate; single-pass idempotent
  normalization; the `/.vfs/__meta__` grammar (chunks/versions/edges) enforced
  structurally at the gate; boundary-aware `with_mount`/`without_mount` that
  correctly rejects non-boundary prefixes (`/mnt/foobar` is not under
  `/mnt/foo`). ~1,400 lines of tests with good pathological coverage.
- **`models2.py`** correctly unfuses domain value from ORM entity (pure
  Pydantic), uses `model_fields_set` for explicitness tracking, and gates
  `path` through `VFSPath` at the field level.
- **`base2.py`** has sound mount lifecycle logic — cycle detection,
  longest-prefix routing, and a clean dispatch seam where `_call_local_impl`
  is the *only* place a filesystem touches its own impl while children are
  always reached via public methods. That seam is exactly the shape an MCP
  tool call needs: story 015 is being realized in code, not just on paper.

Concerns (none direction-threatening):

1. **`parent_dir_id`/`parent_file_id` in models2 are currently undead** — the
   columns exist (story 033 Phase 2) but the computed properties read from the
   path and nothing synchronizes them. Decide which is authoritative before
   the write path freezes.
2. **Old/new module drift** (`base.py`/`base2.py`, `models.py`/`models2.py`).
   Expected mid-refactor, but the cutover should be an explicit near-term
   step; some tests still import the old models.
3. **`VFSResult` error semantics across the mount boundary are undocumented.**
   Once a child mount is a remote MCP server, "what does `success=False`
   mean" is a wire contract — write it down now.

### Design docs: coherent wave, two honest tensions

Stories 015 → 031 → 032 → 033 form a clean dependency chain: public-API
boundary, then one door for entry creation, one door for path resolution, one
door for persistence. The reference grounding (Linux `vfs_create`, Plan 9,
SQLite) is real rigor, and the turbopuffer learning independently validates
the index design.

- **Tension A:** the "everything is a file" claim is only true for
  *user-addressable* metadata — the trigram posting list is necessarily a side
  channel. Docs should say precisely: user metadata is paths; derivation
  machinery (index, embeddings, BM25 stats) is internal.
- **Tension B:** stories 031/032/033 are not on the v0.1.0 critical path in
  the roadmap, yet they absorb all current effort. Fundamentals-first is
  defensible, but the demo-able product is not getting closer week over week.
  Treat "old modules deleted, tests green on the new core" as the wave's exit
  criterion and close it fast.

**Verdict: right direction. The risk is pace, not direction.**

---

## Part 2 — The mid-2026 landscape

### The thesis won

"Filesystem as the agent interface" is now mainstream consensus:

- Anthropic: context-engineering post (Sep 2025 — paths as lightweight
  identifiers), Agent Skills (folders + SKILL.md, now an open standard),
  memory tool (a virtual-filesystem contract), "Code execution with MCP"
  (Nov 2025 — MCP servers presented as files; 98.7% token reduction).
- Jerry Liu, "Files Are All You Need" (Jan 2026) — names the exact gap VFS
  targets: scalable file search where "semantic/keyword indexing needs
  integration with file operations" for 1k–1M+ docs.
  <https://www.llamaindex.ai/blog/files-are-all-you-need>
- Letta benchmark (Aug 2025): files + grep + semantic search beat Mem0's
  specialized graph memory on LoCoMo (74.0 vs 68.5).
  <https://www.letta.com/blog/benchmarking-ai-agent-memory>
- Consensus architecture pieces (Arize Jan 2026, "Filesystems are having a
  moment" Feb 2026): **database as substrate, filesystem as interface** — but
  described as a pattern teams hand-roll, not a product.

### The four verbs match where retrieval landed

The "RAG is dead" debate resolved hybrid: Cursor measured semantic search
+12.5% avg accuracy over grep-only (<https://cursor.com/blog/semsearch>);
Anthropic recommends just-in-time exploration *augmenting* embeddings;
Sourcegraph moved to BM25 over a code graph; "the grep replacement is three
tools, not one" (Jun 2026,
<https://zzet.org/gortex/grep-replacement-for-ai-agents/>). glob/grep/glean/
graph is almost exactly the practitioner consensus.

### Nobody ships the full package

| Project | Mounts | glob/grep | glean | graph | MCP |
|---|---|---|---|---|---|
| deepagents (LangChain) | ✓ CompositeBackend, longest-prefix | ✓ | ✗ (none documented) | ✗ | n/a |
| Mirage (`mirage-ai`, v0.0.2 Jun 2026) | ✓ many connectors | ✓ | ✗ | ✗ | ✗ |
| LlamaIndex SemTools | ✗ | ✓ | ✓ (CLI) | ✗ | ✗ |
| Turso AgentFS | storage/snapshots only | — | ✗ | ✗ | — |
| Sourcegraph | code-only, enterprise SaaS | ✓ | ✓ | ✓ (code graph) | — |
| **VFS (target)** | ✓ | ✓ | ✓ | ✓ (typed file edges) | ✓ |

The intersection — all four verbs over mounted heterogeneous backends, exposed
via MCP, as a Python library — appears unoccupied. **Graph (typed file-to-file
edges as a first-class agent verb) is the most differentiated piece**; nobody
else offers it generically.

### Cautions

- MCP resources are the protocol's least-adopted primitive — expose via MCP
  **tools** (story 015 already designs for this). The prestige framing has
  shifted to "filesystem-first, MCP as one transport," which favors VFS.
- **"glean" name collision**: Glean Technologies is a $7.2B enterprise
  search-for-agents company in the same conceptual space. Fine as a library
  verb; a liability as a marketing keyword.
- Threat vector: LangChain ships semantic search + a real Postgres backend for
  deepagents (their docs already sketch it). Being *the* search-capable
  deepagents backend first is both distribution and defense.

### Direction recommendation

1. **Close the chokepoint wave fast and cut over** (exit criterion above).
2. **Re-sequence toward a vertical slice**: one backend (Postgres), all four
   verbs end-to-end, exposed as an MCP server an agent can mount today. The
   demo is "Claude Code mounts your Postgres knowledge base and
   glob/grep/glean/graphs it." MSSQL parity, console depth, SSO all wait.
3. **Lead with graph** — glean backends are commoditized (consume turbopuffer/
   LanceDB/pgvector, don't compete); mounts are being commoditized; typed
   edges in the agent namespace exist nowhere else. The composability pitch:
   glean output feeds graph traversal because everything is a path.
4. **Ship the deepagents adapter soon** — currently a 30KB design doc, no code.

---

## Part 3 — Developer-first platform strategy

### The narrative lane is open

"Agents need data engineering" consolidated top-down in 2025–26:

- **Fivetran + dbt merger** (completed Jun 1, 2026) branded literally as "the
  data infrastructure for trusted AI agents."
- Snowflake: "control plane for the agentic enterprise"; Databricks: Agent
  Bricks + Neon acquisition (~$1B, "Postgres for agents"); Atlan: "Context
  Lakehouse"; Forrester amplifying "context lake" (arXiv:2601.17019).
- **dltHub** is the closest developer-first articulation ("agentic data
  engineering"; 91% of dlt pipelines now AI-written).

Every articulator is an enterprise platform selling top-down or an
ingestion-layer tool. **Nobody owns the agent-runtime side**: the namespace the
agent works in as an engineered data artifact, built by a developer with a
code-first framework. The phrase "building agents is first and foremost a data
engineering problem" is unclaimed as a slogan. Positioning shorthand: **dbt
transformed warehouse data for humans; VFS transforms organizational knowledge
into a namespace agents can navigate.** VFS sits downstream of dlt/dbt
(compose, don't compete: their pipelines land the data, VFS makes it
agent-navigable) and upstream of agent frameworks.

### The persona bridge is real but early

- Data teams hold formal GenAI responsibility in ~84% of orgs (Monte Carlo);
  56% of orgs have no dedicated AI team, so agent work lands on existing data
  teams (DataTalks.Club 2025–26).
- But dbt's 2026 survey shows data teams adopting AI for *coding* (72%) far
  faster than agent/pipeline operations (24%). VFS targets where the persona
  is being **pulled**, not where it sits — so recipes and templates matter
  more than abstractions. Show the job, not just the API.
- The 2026 data stack to feel native to: dlt/Airbyte → DuckDB → Polars/PySpark
  → dbt → Dagster → FastAPI. Integration surfaces that matter: pip/uv +
  notebook, Arrow/Polars/DuckDB interop, an MCP server day one, Claude
  Code/Cursor-native docs, Postgres.

### DX gaps, audited against v0.0.22, in priority order

1. **Kill first-five-minutes friction.** Today a new user hand-builds an async
   SQLAlchemy engine with `NullPool` before writing a file.
   `VFSClient("vfs.db")` (SQLite default, connection string for Postgres, no
   engine ceremony) is the single highest-leverage change in the repo.
2. **Speak Arrow/DataFrames.** Add `VFSResult.to_arrow()/to_df()` and a bulk
   `ingest(df, ...)` writer with idempotent re-sync. The scheduled
   Dagster/Airflow job that syncs a source into the namespace *is* context
   engineering as a data pipeline — the demo that makes the thesis tangible.
3. **Ship the CLI and the MCP server as one launch.** The query engine exists
   (`g.cli('grep "login" | pagerank | top 10')`) but no `vfs` console script
   ships. The CLI is doubly important: it is also the agent's interface
   (Claude Code drives tools through bash). MCP is *the* integration surface
   of 2026 data tooling (DuckDB, dbt, Snowflake, Unstructured all shipped MCP
   servers). The wedge in one sequence: `pip install vfs-py` → point at
   Postgres → `vfs serve --mcp` → add to Claude Code.
4. **LLM-native docs + a VFS Agent Skill.** The dlt playbook: `llms.txt`,
   docs designed for coding-agent context windows, and a SKILL.md folder
   teaching agents to build with VFS (dbt's Agent Skills repo is the
   template). Acceptance criterion for the docs phase: Claude Code can build
   a working VFS app from the docs alone.
5. **Notebook polish, cheaply.** `_repr_html_` on `VFSResult`, sensible
   defaults, verified in Jupyter and Marimo. No magics yet.

### The two-sided model

- **Framework (Apache-2.0, forever):** library, four verbs, backends, CLI,
  MCP server, deepagents adapter. Licensing evidence is decisive: dbt's ELv2
  Fusion launch caused enough backlash that dbt Core v2.0 returned to Apache
  2.0 within a year; Redis and Elastic both retreated to permissive.
  Restrictive core licensing destroys community trust faster than it protects
  revenue. (Modal proves proprietary + exquisite SDK also works, but the
  bottom-up data-tool route requires the permissive core.)
- **Product (paid):** hosted/control plane — SSO/OIDC, RBAC, audit logging,
  OTel, web console (roadmap Phases 2–4). Discipline this buys: enterprise
  features never add a required dependency or a line of setup ceremony to the
  OSS quickstart.
- **Motion:** community from day one (dbt's Slack predates its revenue; a
  Discord with the founder in it is the solo version) and build-in-public
  launch rituals (Supabase Launch Weeks, dlt's blog cadence). The persona
  discovers tools through HN, practitioner Slack, and increasingly their
  coding agents.

### Sequencing implication for the v0.1.0 roadmap

DX items 1–4 (zero-config client, Arrow bridge, CLI, MCP server) are worth
more for adoption than web-console depth, and most are small. The console and
SSO matter for the org demo; the DX items matter for the flywheel. If anything
slips, let it be console depth — the roadmap already flags that cut.

---

## Source notes

Claims above trace to: Anthropic engineering blog (Sep/Nov 2025), LlamaIndex
blog (Jan 2026), Letta blog (Aug 2025), Cursor blog (semsearch), LangChain
deepagents docs, `mirage-ai` PyPI, Turso AgentFS, Fivetran/dbt merger press
(Jun 1, 2026), dltHub blog, Joe Reis 2026 State of Data Engineering survey
(n=1,101), dbt 2026 State of Analytics Engineering, LangChain State of Agent
Engineering (n=1,340), Monte Carlo/Wakefield survey (2024 — directional),
DataTalks.Club 2025–26 AI Engineering survey, Sacra/Benn Stancil on dbt,
Temporal Series D (Feb 2026), InfoQ on Redis AGPL. Treat third-party stat
aggregations (MCP adoption counts, job-posting growth, Gartner-via-Atlan
figures, Neon ~$1B price) as directional; re-verify before public use.
