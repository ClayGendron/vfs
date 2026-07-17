# Landscape Claim Verification — Findings So Far (WIP, handoff)

- **Date:** 2026-07-12
- **Owner:** research (deep-research workflow, interrupted mid-verify)
- **Status:** **in progress — handoff doc.** Search and fetch phases are
  complete; adversarial verification is ~1/3 done (zero refutations so
  far); synthesis has not run. §5 has exact instructions to finish.
- **Question:** do the two competitive claims from the 2026-06-09
  direction review still hold as of 2026-07-12?
  - **Claim 1:** no shipping project offers all four retrieval modes
    (glob/grep, semantic, graph) native to one filesystem-shaped
    namespace with one composable result type over mountable
    heterogeneous backends.
  - **Claim 2:** no shipping project offers the "agent contract"
    filesystem (closed error taxonomy, declared capabilities, revision
    stamps, bounded enumeration, composable results, MCP-mountable);
    AgentFS is the closest peer and has no search/retrieval.

## 1. Provisional verdicts

- **Claim 1: HOLDS (provisional, high confidence).** 30 sources
  fetched; no project ships all four verbs in a filesystem-shaped
  namespace over mountable backends. The two closest approaches attack
  from opposite sides and each lack half the intersection (§3).
- **Claim 2: HOLDS (provisional, medium-high confidence).** AgentFS is
  unchanged since 0.6.4 (2026-03-25) and still ships no search, no MCP,
  no contract features. The caveat: LangChain deepagents is visibly
  drifting toward pieces of the agent contract (§3, deepagents row).

Every verification vote completed before interruption (27 votes across
the deepagents-cluster claims) returned **refuted=false at high
confidence**, mostly by re-fetching primary sources (live docs, release
pages, source files) on 2026-07-12. Nothing found so far weakens either
claim; the unverified remainder (§4) is where a surprise would hide.

## 2. What the harness completed

Run `wf_e24307bd-490`, five search angles → 5 searches → **30 sources
fetched** (~146 claims extracted) → top 25 claims ranked for 3-vote
adversarial verification → **27/75 votes completed, 0 refutations**
→ synthesis not reached.

## 3. Findings by project (from fetched-source claims; ✓ = vote-verified)

- **LangChain deepagents** (releases through 0.7.0a6, 2026-07-07) ✓ —
  still pattern-only: exposed tools are exactly ls, read_file,
  write_file, edit_file, delete, glob, grep (+ conditional execute); no
  semantic, vector, or graph anywhere in code, docs, or all ~213
  release bodies. ✓ CompositeBackend now does longest-prefix path
  routing over heterogeneous backends (the mounts half of Claim 1). Contract
  drift to watch: bounded grep/glob with `truncated` partial results
  (0.7.0a4), tool allowlists, delete-capability removal when a backend
  lacks it, structured-error-results convention for backend authors,
  commit-hash optimistic concurrency in ContextHubBackend only. Known
  wart: glob semantics differ per backend (basename-only on
  StateBackend; ripgrep-vs-Python fallback divergence) — silent
  zero-match successes, no honest error taxonomy.
- **deepagents-backends** (community, DiTo97, v0.2.0 2026-04-17) ✓ —
  six remote backends incl. **PostgreSQL** behind a common
  BackendProtocol; pattern retrieval only; no MCP, no contract
  features; dormant since April.
- **Turso AgentFS** (latest 0.6.4, 2026-03-25; docs re-fetched
  2026-07-12) — unchanged: copy-on-write isolation, single SQLite
  file, audit, cloud sync. No search of any kind, no MCP, no
  capability/revision/pagination contract. Releases Jan–Mar 2026 were
  infrastructure (inode architecture, encryption, POSIX permissions).
  **Latent risk:** the Turso engine underneath now ships native vector
  search + Tantivy FTS — the primitives exist one layer down if they
  choose to surface them.
- **LlamaIndex / LlamaCloud** — the most credible new movement, from
  the RAG side: the **Retrieval Harness** (beta, 2026-06-29) unifies
  semantic/hybrid retrieval + server-side regex grep + file
  listing/read in one filesystem-shaped tool surface; **legal-kb**
  (2026-07-05) demoes retrieve/findFiles/readFile/grepFile with
  citations, pagination, per-file versioning. Missing: graph verb,
  mounts, MCP, error taxonomy; grep is single-file-scoped; hosted
  proprietary service, not a library.
- **Zep "Context Lake"** (2026-05-31) — four retrieval modes including
  graph traversal and pattern matching over one substrate — but
  graph-shaped, not filesystem-shaped: no path namespace, no glob/grep
  over paths, no mounts, no MCP. Also owns the "context lake" keyword.
- **desplega-ai agent-fs** (TypeScript/Bun, v0.10.1 2026-07-09,
  13 stars) — new entrant: SQLite-backed agent FS with **semantic
  search (multi-provider embeddings), per-file versioning, and MCP
  exposure**. No native glob/grep (shell-over-FUSE only), no graph, no
  mounts, no contract features. Low traction but the closest
  shape-match to VFS's positioning among new entrants.
- **Mesa** (announced 2026-04-28, private beta) — commercial
  "filesystem for agents" with git-style branches/diffs/history via
  FUSE+SDK. Versioning lane only: no search, no graph, no MCP.
- **ToolFS** (Go/FUSE) — paths + memory + RAG in one namespace;
  dormant (6 commits, last 2026-01-21).
- **"Everything is Context" / AFS paper** (arXiv 2512.05470, Dec 2025;
  AIGNE framework) — academic formalization of exactly VFS's shape:
  heterogeneous backends (vector stores, memory DBs, MCP endpoints)
  mounted as subtrees, pattern + semantic search in-namespace,
  versioning/ACL/audit metadata. No graph verb, no contract wire
  details. Ideas competitor, not a shipping one — but expect citations
  of it in future products.
- **Others:** Mintlify ChromaFs (shell-commands→vector-DB translation),
  ByteDance OpenViking (`viking://` tiered-access context FS),
  markdownfs (Rust: grep/find + git-style versioning + MCP, no
  semantic/graph) — all partial, none with graph.

**Pattern across the field:** everyone converges on 2–3 verbs from
their home turf (RAG products adding grep; storage products adding
versioning; deepagents adding mounts) — nobody has the graph verb in a
filesystem namespace, and nobody has the composed contract. Graph
remains VFS's most defensible verb, consistent with the 2026-06-09
review.

## 4. What is NOT yet verified

- ~16 of the 25 ranked claims never got their 3-vote panel — all
  AgentFS/LlamaIndex/Zep/new-entrant claims above marked without ✓ are
  extracted-from-source but not adversarially verified.
- Synthesis (dedup, confidence ranking, final report) never ran.
- Angles arguably under-covered by the search phase: Letta, Sourcegraph,
  Mirage, cognee got no dedicated fetched source (search hits went to
  higher-relevance URLs); a finishing pass could spot-check those four
  by hand.

## 5. How to finish this research

The workflow is resumable — completed agents are cached and will not
re-run (same script, same args):

1. Script: `~/.claude/projects/-Users-claygendron-Git-Repos-vfs/962eb829-d2e2-45a1-9eca-efa2db1442c6/workflows/scripts/deep-research-wf_e24307bd-490.js`
2. Journal/raw results: `~/.claude/projects/-Users-claygendron-Git-Repos-vfs/962eb829-d2e2-45a1-9eca-efa2db1442c6/subagents/workflows/wf_e24307bd-490/journal.jsonl`
3. Resume with the SAME args string the run was launched with (it is
   embedded in this doc's §"Question" and verbatim in the session; the
   scope agent's cached decomposition is keyed on it):
   `Workflow({scriptPath: <script above>, resumeFromRunId: "wf_e24307bd-490", args: <original question>})`
4. **Model caveat:** the script's verify + synthesize `agent()` calls
   carry `model: "opus"` (added 2026-07-12 after a stop/resume), but
   the resumed run was observed still executing on the session model
   (fable) — the per-call override did not visibly take effect under
   resume. If Opus execution matters, either run the finishing session
   with the session model set to Opus (`/model`), or extract the
   remaining ~16 claims from the journal and verify them via direct
   Agent-tool calls with a model override, then synthesize by hand.
5. When it completes, fold the final report into this doc (drop the
   WIP marker) and true up the 2026-06-09 direction review's matrix.

## 6. Provisional bottom line

Both claims held at the 2/3-verified mark, with two watch items for
the next quarter: **LlamaCloud's Retrieval Harness** (semantic+grep in
a file namespace, moving fast, hosted) and **deepagents' contract
drift** (truncated-result bounds, capability-conditional tools,
backend mounts — the hand-rolled version of our contract, assembling
piece by piece). The four-verb-plus-contract intersection remains
unoccupied; the window the 2026-06-09 review described is still open
but the RAG-side players are now one verb (graph) and one primitive
(mounts) away.
