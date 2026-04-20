# Graphify & LightRAG — Influences for VFS and FSP

> Reference repos: `/Users/claygendron/Git/Repos/graphify` and `/Users/claygendron/Git/Repos/LightRAG`

## Overview

Graphify and LightRAG sit on opposite ends of the "turn a corpus into queryable structure" problem, and both inform VFS's mount/extraction/query story. **Graphify** is a multimodal knowledge-graph builder for code assistants: it reads a directory of files (code, docs, papers, images, audio/video), uses a three-pass extraction pipeline (deterministic tree-sitter AST → domain-aware Whisper transcription → Claude semantic extraction), assembles a NetworkX graph with confidence-tagged edges (`EXTRACTED | INFERRED | AMBIGUOUS`), and exports HTML/JSON/Obsidian/MCP surfaces. **LightRAG** is an enterprise-grade LightRAG-paper implementation: it chunks documents, LLM-extracts entities and relations, builds a knowledge graph, and serves hybrid (vector + graph) retrieval across five query modes (`naive | local | global | hybrid | mix`) over 16+ pluggable storage backends (JSON, Neo4j, Postgres, Mongo, Qdrant, Milvus, Faiss, Memgraph, OpenSearch, Redis). For VFS, graphify maps closest to the **extraction pipeline and write path** (how content flows into `vfs_objects`), while LightRAG maps closest to the **storage abstraction and query surface** (how mounts expose heterogeneous backends behind a single protocol). Both converge on a pattern VFS is already reaching for: one user-facing surface, many pluggable backends, typed row discrimination (LightRAG namespaces ≈ VFS `kind`), and path-level tenant scoping.

## Navigation Guide

**Graphify entry points:** `graphify/__main__.py` (CLI dispatch), `graphify/detect.py` (file classification + `.graphifyignore`), `graphify/extract.py` (tree-sitter + LLM extraction), `graphify/build.py` (NetworkX assembly).

**Graphify pipeline stages:** `detect → extract → build → cluster → analyze → report → export`. Each stage reads cache + writes cache; failures at any stage don't lose prior work.

**Graphify MCP surface:** `graphify/serve.py` — stdio MCP server with `query_graph`, `get_node`, `get_neighbors`, `shortest_path`. DFS/BFS are token-budgeted.

**LightRAG entry points:** `lightrag/lightrag.py` (the `LightRAG` orchestrator), `lightrag/operate.py` (extraction + query ops), `lightrag/base.py` (four abstract storage base classes), `lightrag/api/lightrag_server.py` (FastAPI wrapper).

**LightRAG storage contract:** `base.py` defines `StorageNameSpace`, `BaseKVStorage`, `BaseVectorStorage`, `BaseGraphStorage`, `DocStatusStorage`. Every backend in `kg/*_impl.py` implements a subset of these.

**LightRAG query dispatch:** `lightrag.py:aquery` → `aquery_llm` → either `kg_query` (graph path) or `naive_query` (vector-only) in `operate.py`. Mode strings (`naive|local|global|hybrid|mix|bypass`) are branched on via if/elif.

**Skip:** Both repos have large `tests/`, `examples/`, WebUI (LightRAG React 19 app), Docker/k8s tooling, and polyglot README translations — none of that informs the design.

## File Index

| Path | Purpose |
|------|---------|
| `graphify/extract.py:14–65` | `LanguageConfig` dataclass; per-language AST node-type specs for tree-sitter |
| `graphify/extract.py:99–500` | Per-language walkers (Python, JS, Go, Rust, Java, C/C++); deterministic structural pass |
| `graphify/build.py:30–86` | `_normalize_id()`, `build_from_json()` — ID normalization, dedup, AST-before-semantic merge |
| `graphify/validate.py:1–73` | Extraction schema: `REQUIRED_NODE_FIELDS`, `REQUIRED_EDGE_FIELDS`, `VALID_CONFIDENCES = {EXTRACTED, INFERRED, AMBIGUOUS}` |
| `graphify/cache.py:20–93` | `file_hash()` (SHA256 of body, not path; YAML frontmatter-stripped for markdown); atomic `save_cached()` |
| `graphify/cluster.py:21–102` | Leiden (graspologic) with Louvain fallback; oversized-community splitting at 25% threshold |
| `graphify/analyze.py:11–91` | `god_nodes()` (top-degree filtered), `surprising_connections()` (cross-file vs. cross-community) |
| `graphify/transcribe.py:20–120` | faster-whisper with domain-aware prompt derived from god nodes; yt-dlp audio download cached by URL hash |
| `graphify/watch.py:15–200` | `_rebuild_code()` — fast AST-only rebuild, preserves prior semantic layer |
| `graphify/export.py:271–320` | `attach_hyperedges()` — N-ary group rendering for cohesive node sets |
| `graphify/serve.py:150–300` | MCP stdio server; token-budgeted DFS/BFS; backward-compat (`links → edges`) on load |
| `graphify/security.py:26–120` | `validate_url()` (no `file://`, blocks private IPs/cloud metadata), `_NoFileRedirectHandler`, `safe_fetch()` with `max_bytes` |
| `LightRAG/lightrag/lightrag.py:210` | `LightRAG` orchestrator class; storage lifecycle + workspace scoping |
| `LightRAG/lightrag/lightrag.py:1237` | `ainsert()` entry point; enqueue → chunk → extract → merge → rebuild → status |
| `LightRAG/lightrag/lightrag.py:2622` | `aquery()` dispatcher; routes to `kg_query` or `naive_query` by mode |
| `LightRAG/lightrag/base.py:85` | `QueryParam` dataclass: mode, top_k, chunk_top_k, stream, enable_rerank, max_entity_tokens |
| `LightRAG/lightrag/base.py:173` | `StorageNameSpace` — root ABC; every backend has a namespace + workspace |
| `LightRAG/lightrag/base.py:218` | `BaseVectorStorage` — `query()`, `upsert()`, `delete_entity()` |
| `LightRAG/lightrag/base.py:356` | `BaseKVStorage` — `get_by_id(s)()`, `upsert()`, `filter_keys()` |
| `LightRAG/lightrag/base.py:405` | `BaseGraphStorage` — `has_node()`, `node_degree()`, `get_node_edges()` |
| `LightRAG/lightrag/base.py:810` | `DocStatusStorage` — PENDING / PROCESSING / COMPLETED / FAILED tracking |
| `LightRAG/lightrag/operate.py:101` | `chunking_by_token_size()` — default 1200 tokens, 100 overlap |
| `LightRAG/lightrag/operate.py:2501` | `merge_nodes_and_edges()` — cross-chunk entity/relation dedup |
| `LightRAG/lightrag/operate.py:2883` | `extract_entities()` — LLM-driven; results cached in `KV_STORE_LLM_RESPONSE_CACHE` |
| `LightRAG/lightrag/operate.py:3164` | `kg_query()` — entity/relation retrieval + chunk aggregation |
| `LightRAG/lightrag/operate.py:4930` | `naive_query()` — vector-only path |
| `LightRAG/lightrag/namespace.py:7–22` | Namespace constants (text_chunks, entities, relationships, llm_response_cache, doc_status) |
| `LightRAG/lightrag/types.py:12–30` | `KnowledgeGraphNode`, `KnowledgeGraphEdge`, `KnowledgeGraph` |
| `LightRAG/lightrag/kg/json_kv_impl.py:28` | Reference file-based KV backend |
| `LightRAG/lightrag/kg/neo4j_impl.py:66` | Production graph backend |
| `LightRAG/lightrag/api/lightrag_server.py:1` | FastAPI app; mounts document/query/graph/ollama routers |

## Core Concepts (What They Did Well)

### 1. Three-Pass Extraction with Confidence Tags (Graphify)

**What:** Graphify separates extraction into orthogonal passes, each producing edges with explicit confidence:

1. **AST pass** (`extract.py`) — tree-sitter walks, no LLM. Edges tagged `EXTRACTED`, confidence 1.0.
2. **Transcription pass** (`transcribe.py`) — faster-whisper on video/audio, prompt seeded with corpus god nodes. Output feeds pass 3.
3. **Semantic pass** — Claude extracts concepts/relations from docs, papers, images, and transcripts. Edges tagged `INFERRED` with a `confidence_score ∈ [0, 1]`, or `AMBIGUOUS` for flagged uncertainty.

Validation (`validate.py:1–73`) enforces a schema — every node has `label`, `source_file`, `source_location`; every edge has `source`, `target`, `relation`, `confidence ∈ {EXTRACTED, INFERRED, AMBIGUOUS}`.

**Why it matters:** Structural extraction is cheap, deterministic, and cache-friendly. The expensive LLM pass is additive — you can stop after pass 1 and still get a usable graph. Confidence tags survive into the final export, so downstream consumers can filter strict vs. best-effort.

**VFS implication:** Writes to `vfs_objects` should carry a confidence/provenance tag. A row written by a structural mount ("Postgres schema introspection") is high-confidence ground truth; a row written by a semantic summarizer mount is inferred and should be filterable. Don't collapse the two into the same column.

**FSP implication:** Every read response should include provenance metadata (`source_mount`, `confidence`, `confidence_score`). Clients can request `min_confidence=EXTRACTED` to opt out of inferred data.

### 2. Per-Content SHA256 Cache with Body-Only Hashing (Graphify)

**What:** `cache.py:file_hash()` hashes file **content**, not path. For markdown it strips YAML frontmatter first, so metadata-only edits (e.g., flipping `reviewed: true`) don't invalidate. Writes are atomic via `os.replace` with a `shutil.copy2` fallback for Windows.

**Why it matters:** Cache hit rates stay high across reviews, renames, and cross-machine checkouts. The hash is portable — move the corpus to a new machine, the cache still matches.

**VFS implication:** Content-addressed blob storage is a natural fit for `vfs_objects`. Store body hash separately from metadata hash; a rename is a metadata change, not a content change, and should not invalidate derived artifacts.

### 3. Pluggable Storage via Four Abstract Base Classes (LightRAG)

**What:** `base.py` defines a minimal quartet — `BaseKVStorage`, `BaseVectorStorage`, `BaseGraphStorage`, `DocStatusStorage` — all rooted at `StorageNameSpace` (which carries `namespace` + `workspace`). Every backend in `kg/` (16+ implementations) implements a subset. The orchestrator (`LightRAG` class) holds typed references and never touches a backend-specific method.

```python
class LightRAG:
    chunk_entity_relation_graph: BaseGraphStorage
    entities_vdb: BaseVectorStorage
    relationships_vdb: BaseVectorStorage
    text_chunks: BaseKVStorage
    llm_response_cache: BaseKVStorage
    doc_status: DocStatusStorage
```

Swapping Neo4j for Postgres is a config string change — `graph_storage="PGGraphStorage"` — not a code change.

**Why it matters:** The abstraction is tight enough that 16 backends coexist without leaking. `BaseKVStorage` has 6 methods. `BaseGraphStorage` has ~10. No `execute_raw_sql` escape hatch — every op goes through the ABC.

**VFS implication:** VFS's mount protocol should mirror this. Define the minimum surface (`read`, `write`, `list`, `stat`, `delete`, `search`) and forbid escape hatches. If a mount needs richer access, it exposes a typed capability (`supports_semantic_search: bool`), not a raw-query method.

**FSP implication:** The wire protocol advertises capabilities per mount in the handshake. Clients feature-detect rather than assume. LightRAG's `storage_implementation_compatibility_check` pattern is worth adopting.

### 4. Namespace + Workspace Two-Level Partitioning (LightRAG)

**What:** Every storage instance is scoped by `(namespace, workspace)`. `namespace` is a fixed enum-like string identifying the logical row role (`text_chunks`, `entities`, `llm_response_cache`, `doc_status`). `workspace` is a user-chosen string for multi-tenancy. Backends apply workspace differently: file backends subdirectory it, Postgres makes it a column filter, Qdrant applies payload-based partitioning.

**Why it matters:** One server, many tenants, no cross-contamination. The namespace is frozen at design time; the workspace is runtime. This cleanly separates "what kind of data" from "whose data."

**Mapping to VFS (no schema change required):**

- **`namespace` ≈ existing `kind` column** on `VFSObjectBase` (`src/vfs/models.py:109–111`). VFS already discriminates row roles — file, directory, chunk, version, connection, api node — via `kind`, with nullable fields gated by it. This is the same idea LightRAG hardcodes into separate storage classes. VFS gets it in one table.
- **`workspace` ≈ existing `/{user_id}/...` path prefix + `owner_id` column** (`docs/plans/user_scoped_filesystem.md:16`). Tenant uniqueness is path-level; `path` stays globally unique because it's prefixed, and `owner_id` backs authorization queries. `user_id` is a per-call parameter, scoped at the DB boundary inside terminal `_*_impl` methods (per the user-scoped-filesystem pattern).

The takeaway for VFS is **not** "add a workspace column" — that work is already done via path prefixing. It's "LightRAG's namespace/workspace decomposition is the same decomposition VFS already has as `kind` + scoped path; keep both axes explicit and don't let future features collapse them into a single opaque identifier."

### 5. Document Status Tracking as First-Class Storage (LightRAG)

**What:** `DocStatusStorage` extends `BaseKVStorage` with an enum state machine: `PENDING → PROCESSING → COMPLETED | FAILED`. Insertion enqueues the doc, the pipeline updates status as it progresses, and resumption on failure reads status to skip completed work. The doc status is the durable log of what's been processed.

**Why it matters:** Crash recovery is trivial — restart reads `PENDING` + `PROCESSING` and resumes. No separate queue, no separate WAL.

**VFS implication — careful mapping:** This is **not** the same thing as VFS's content-before-commit rule (`docs/internals/fs.md:91`). Content-before-commit governs *write durability within a single transaction* — body lands on disk, then the metadata row commits, and the VFS context manager rolls back on failure. The row is never visible in an in-between state to `read`/`ls`/`search`. LightRAG's `DocStatusStorage` is a different animal: it's a **separate sidecar namespace** tracking long-running, post-commit derivation work (extract entities, embed chunks, build graph). VFS should mirror that separation — any async-derivation state lives in its own surface (e.g., a derivation-jobs namespace or a separate `kind`), not as a mutable column on the primary `vfs_objects` row that normal reads would encounter. Mixing the two would violate VFS's "committed rows are fully live" invariant.

### 6. LLM Response Cache as a Storage Namespace (LightRAG)

**What:** `KV_STORE_LLM_RESPONSE_CACHE` is not a bolt-on — it's a namespace alongside `text_chunks` and `entities`. Any LLM call goes through `use_llm_func_with_cache()`, which keys by prompt hash and returns cached responses. The cache is a `BaseKVStorage`, so it can be backed by any of the 16 implementations.

**Why it matters:** Re-runs are free. A failed ingest that re-runs only pays for the chunks that changed. No global memoization decorator; the cache is a first-class storage object with its own workspace scoping.

**VFS implication:** VFS's expensive per-object computations (summaries, embeddings, extractions) should be cached as a distinct namespace in `vfs_objects`, keyed by `(object_hash, computation_id, version)`. A user-facing `vfs clear-cache --namespace=summaries` just drops that namespace.

### 7. Query-Mode Dispatch Behind a Single Entry Point (LightRAG)

**What:** `aquery(query, param: QueryParam)` is the only query method clients call. `param.mode` ∈ `{naive, local, global, hybrid, mix, bypass}` selects the retrieval strategy. Each mode has a different cost/latency/recall profile, but the surface is identical.

**Why it matters (for LightRAG's single use-case):** Retrieval is the only public verb. One method, one parameter object, easy for clients to learn.

**Why it's the wrong template for FSP:** This works for LightRAG because the entire product is "retrieval." VFS's public verbs are distinct actions — `read`, `write`, `ls`, `stat`, `delete`, `search`, `glob`, `grep`, `graph` — each with different types, different auth scopes, and different side effects. Collapsing them under a single `op` with a stringly-typed `operation` field would recreate exactly the if/elif-chain regret called out in Anti-Pattern §1 below, just one level up. The MCP and LSP precedents (`context/learnings/2026-04-19-mcp-specification.md:221`, `.../language-server-protocol.md:170`) both expose explicit namespaced methods + capability discovery for this reason. What VFS should borrow from LightRAG is **the `QueryParam` object per search-family verb** — a single `search` endpoint that takes a `mode` param — not a single top-level dispatcher for every operation.

### 8. God Nodes + Surprising Connections as Derived Analytics (Graphify)

**What:** `analyze.py` produces two derived views on the graph:
- **God nodes** (`analyze.py:39–59`): top-degree nodes, filtered to exclude synthetic hubs (file-level nodes, method stubs, concept-only nodes). These are the architectural hotspots.
- **Surprising connections** (`analyze.py:61–91`): edges that cross file boundaries (in multi-source corpora) or cross communities (in single-source). Ranked `AMBIGUOUS → INFERRED → EXTRACTED` so the uncertain-but-interesting edges surface first.

**Why it matters:** Both are **derived**, not stored. They're recomputed from the graph on demand. The graph itself is the source of truth.

**VFS implication:** Don't pre-materialize analytical views into `vfs_objects`. Compute them lazily on read. A `god_paths` query over the mount graph can surface architectural bottlenecks without a scheduled job writing them to a column.

### 9. Domain-Aware Preprocessing (Graphify)

**What:** Whisper transcription uses a prompt seeded with the corpus's god nodes: `"Key concepts in this corpus: {labels}"`. The transcription is therefore biased toward domain vocabulary before it reaches the semantic LLM pass.

**Why it matters:** Cheap biasing dramatically improves downstream quality. No fine-tuning, no custom models.

**VFS implication:** When a mount performs LLM operations on mount content (e.g., `api-docs` mount summarizing endpoints), seed the prompt with the mount's top entities. VFS can expose this as a mount capability — `mount.domain_context() → list[str]` — wired into the extraction pipeline automatically.

### 10. Incremental, Tiered Updates (Graphify)

**What:** `watch.py:_rebuild_code()` rebuilds the code layer of the graph on file changes **without** re-running the semantic pass. Prior INFERRED edges are preserved. A git post-commit hook (`hooks.py`) wires this up automatically.

**Why it matters:** Tight feedback on the cheap pass; manual trigger for the expensive pass. The user isn't punished with 60-second rebuilds for a one-character code edit.

**VFS implication:** VFS's mount-update contract should distinguish `update_fast` (structural, deterministic, seconds) from `update_full` (includes semantic refresh, minutes). Clients pick based on latency budget. The watch loop calls fast; a nightly cron calls full.

## Anti-Patterns & Regrets

### 1. Query-Mode Dispatch via if/elif Chains (LightRAG)

**Issue:** `aquery_llm` branches on `param.mode` with a large if/elif. Adding a mode means editing the dispatcher.

**Regret:** The backends are polymorphic but the query strategies are not. Strategies should be first-class plugin objects, same as storage backends.

**For VFS:** Make retrieval strategies pluggable — `Retriever` ABC, registry, mode is a string that resolves to a class. Prevents `aquery_llm` rot.

### 2. Namespace Strings Instead of Enums (LightRAG)

**Issue:** `NameSpace` is a class of string constants (`namespace.py:7–22`). Typos silently create new namespaces in the backend. No runtime validation catches `"text_chukns"`.

**Regret:** Shows up in log noise and mysterious empty-result bugs.

**For VFS:** Use a real `Enum` for namespace identifiers. Backends validate on write.

### 3. Document Deletion Rebuilds the Whole KG (LightRAG)

**Issue:** `adelete_document()` doesn't remove individual entities — it purges the doc's chunks and re-derives the graph. If a doc contributed to shared entities, the deletion cost is O(whole corpus).

**Regret:** Deletion was an afterthought. Reference counting wasn't designed in.

**For VFS:** Reference-count shared objects (chunks, entities, derived artifacts) from day one. A delete decrements refcount; only refcount=0 triggers physical removal. This matches Unix inode semantics and the "everything is a file" direction.

### 4. No Transactionality Across Storages (LightRAG)

**Issue:** An insert writes to vector DB, KV, graph, and doc-status in sequence. Any intermediate failure leaves the KG inconsistent. Recovery relies on doc-status being the last write, but partial vector/graph writes are never rolled back.

**Regret:** Fine for single-tenant single-backend, dangerous for production multi-backend.

**For VFS:** Either make `vfs_objects` the single source of truth (all storage goes through one table, one transaction) — which is the current direction — or introduce a two-phase commit / checkpoint mechanism. Don't pretend multi-backend writes are atomic.

### 5. LLM Cache Lacks Schema Versioning (LightRAG)

**Issue:** `KV_STORE_LLM_RESPONSE_CACHE` stores raw JSON strings. If the extraction prompt changes, old cache entries silently deserialize as the new format and produce garbage.

**Regret:** No `schema_version` field on cached entries.

**For VFS:** Every cached derivation carries a `(computation_id, schema_version, prompt_hash)` triple. Version bumps invalidate cleanly.

### 6. Confidence Scores Computed But Under-Exposed (Graphify)

**Issue:** `confidence_score` is stored on every INFERRED edge but doesn't reach the HTML viz or the JSON exports prominently. The MCP server returns the field but doesn't let clients filter on it.

**Regret:** Rich data, shallow surface.

**For VFS:** First-class confidence filtering at the FSP layer. `read(path, min_confidence=0.8)` should be a supported parameter, not something clients emulate with post-filter.

### 7. Cross-Language Call Graphs Are Incomplete (Graphify)

**Issue:** Tree-sitter walkers are per-language. Python calling a Rust extension via `cffi` is invisible to the AST pass.

**Regret:** The semantic pass can catch it if documented, but structural ground truth is language-siloed.

**For VFS:** Cross-mount references (SQL mount → REST mount → file mount) must be inferred globally. Don't let mount implementations each build their own graph in isolation.

### 8. Oversized-Community Split Uses a Hardcoded 25% Threshold (Graphify)

**Issue:** `cluster.py:59–102` splits communities larger than 25% of graph nodes. 25% is arbitrary; the split isn't explained in the report.

**Regret:** Users see a confusing community structure with no audit trail.

**For VFS:** Any heuristic parameter that affects user-visible output should be (a) configurable, (b) reported in output metadata.

### 9. Transcription Prompt Is Frozen Per Run (Graphify)

**Issue:** The domain-aware Whisper prompt is computed once from god nodes at the start of a run. New transcriptions in the same run don't benefit from concepts discovered mid-run.

**Regret:** Feedback loop is too coarse.

**For VFS:** Domain context should refresh after each semantic batch, not per-run.

### 10. Watch Mode Is Asymmetric (Graphify)

**Issue:** Code changes trigger instant rebuild; doc changes only notify. User sees different latency for conceptually similar edits.

**Regret:** The fast-vs-slow distinction leaked into the UX instead of being hidden behind a queue.

**For VFS:** If the system has fast and slow paths, expose one unified "changed" stream and let the backend choose when to do semantic work. Don't make the user remember which edit type triggers what.

## Implications for VFS (Implementation)

### 1. Mount-Protocol Capability Subsets (Not Row-Level ABCs)

LightRAG's four ABCs (`BaseKVStorage`, `BaseVectorStorage`, `BaseGraphStorage`, `DocStatusStorage`) describe *what a backend can hold*. In VFS, that concept lives in two different places already:

- **Row discrimination is `kind`.** `kind` on `VFSObjectBase` (`src/vfs/models.py:109–111`) already separates file, directory, chunk, version, connection, api-node. Don't introduce a parallel `namespace` column — that would duplicate `kind` and fragment queries.
- **Mount capability belongs on the mount protocol.** What's worth borrowing from LightRAG is the *subsetting*: a mount advertises which kinds it supports and which verbs it implements. A read-only Postgres-schema mount produces `kind=directory|file` and nothing else; a full-text-index mount produces `kind=chunk` with `search` support; a graph mount produces `kind=connection`. The dispatcher reads capabilities from the mount, not ABCs from a storage backend.

Result: no new schema, no new column, no new ABC hierarchy — just a capability descriptor on each mount keyed by `kind` + verb.

### 2. Confidence + Provenance on Every Row

Extend the `vfs_objects` schema with:

```sql
confidence      TEXT NOT NULL,           -- EXTRACTED | INFERRED | AMBIGUOUS
confidence_score REAL,                   -- null if EXTRACTED
source_mount    TEXT NOT NULL,           -- which mount wrote this
computation_id  TEXT,                    -- null if not derived
schema_version  INTEGER NOT NULL         -- for cache invalidation
```

These travel through the read path to the FSP wire format.

### 3. Content-Addressed Blob Hashing

Body hash is SHA256 of the **normalized body** (frontmatter-stripped for markdown, whitespace-collapsed where safe, etc.). Rename is a metadata change, not a body change. Cache keys derive from body hash, not path.

### 4. Derivation State on a Separate Surface

LightRAG's `DocStatusStorage` is the right idea for async, post-commit derivation work (semantic summary generation, embedding backfill, graph rebuild), but it must not land on the primary `vfs_objects` row.

- **Primary writes stay atomic.** A `vfs_objects` row is durable-and-live when the session commits (`docs/internals/fs.md:91`). `read`/`ls`/`search` never see a half-finished row.
- **Derivation jobs live separately.** A derivation-jobs table (or a distinct `kind`, e.g. `kind="derivation_job"` with a separate parent-path convention) tracks `PENDING | PROCESSING | COMPLETED | FAILED` against the target object's `id`. Default read paths skip this kind; a dedicated `vfs derivations` surface exposes it.
- **Recovery scans the derivation surface only.** A crash never leaves a primary row in an invalid state — at worst a derivation job is stuck `PROCESSING` and the worker re-runs it.

### 5. Three-Pass Extraction for Mounts

Each mount implements up to three extraction methods:

```python
def extract_structural(self, path) -> list[Object]: ...   # cheap, deterministic
def preprocess(self, obj, domain_ctx) -> Object: ...      # optional (transcribe, parse)
def extract_semantic(self, obj, domain_ctx) -> list[Edge]: ...  # LLM-driven, optional
```

The VFS pipeline calls them in order, caching between phases. Structural failures abort; semantic failures log and continue.

### 6. Derived-View Namespaces

Reserve namespaces for analytics (`god_mounts`, `surprising_connections`, `community_labels`) and compute lazily on read. Store results only if explicitly materialized; default to recompute.

### 7. Refcounted Shared Objects

Chunks, entities, and other cross-object references use refcounting. Delete decrements; physical removal waits for refcount=0. Rebuild on delete is forbidden.

## Implications for FSP (Protocol)

### 1. Explicit Namespaced Verbs + `mode` Only on Retrieval Verbs

Keep FSP verbs explicit (`vfs.read`, `vfs.write`, `vfs.ls`, `vfs.stat`, `vfs.delete`, `vfs.search`, `vfs.glob`, `vfs.grep`, `vfs.graph`). Borrow LightRAG's `QueryParam` pattern **only** for the retrieval-family verbs — `search`, `graph` — where a single verb with a `mode` choice genuinely maps to multiple strategies:

```json
{
  "method": "vfs.search",
  "path": "/mount/foo",
  "mode": "hybrid",
  "min_confidence": "INFERRED",
  "stream": true
}
```

No `vfs.op` super-dispatcher. Clients discover verbs and per-verb capabilities via handshake (see §2), matching the MCP + LSP precedent already cited in VFS's other learnings.

### 2. Capability Negotiation in Handshake

FSP clients receive a capability manifest at connect time:

```json
{
  "mounts": [
    {
      "path": "/postgres",
      "storage": ["object", "index", "graph", "status"],
      "retrieval_modes": ["naive", "local", "hybrid"],
      "supports_stream": true,
      "domain_context": ["User", "Order", "Invoice"]
    }
  ]
}
```

Clients feature-detect; no magic strings in protocol docs.

### 3. Provenance Fields in Every Response

```json
{
  "success": true,
  "data": "...",
  "provenance": {
    "source_mount": "/docs",
    "confidence": "INFERRED",
    "confidence_score": 0.87,
    "computation_id": "semantic_summary_v3",
    "schema_version": 4
  }
}
```

Callers know what they're getting.

### 4. User Scoping Is Server-Derived, Not a Protocol Field

VFS already scopes by user via `/{user_id}/...` path prefix + `owner_id` column (`docs/plans/user_scoped_filesystem.md:16`). FSP should not expose `workspace` or `user_id` as a client-settable wire field. Instead:

- Authenticated identity is bound at session establishment.
- The server injects `user_id` into each terminal `_*_impl` (per the scoping contract); `scope_path` prepends server-side.
- Clients send unscoped paths; paths come back unscoped by `strip_user_scope()`.

This closes the LightRAG gap where `workspace` is a client string and a typo silently creates a new tenant — VFS's scope is non-forgeable by construction.

### 5. Tiered Update Requests

```json
{"method": "vfs.refresh", "paths": ["/mount/docs"], "tier": "structural"}
{"method": "vfs.refresh", "paths": ["/mount/docs"], "tier": "full"}
```

Clients pick by latency budget. `structural` returns in seconds; `full` may queue.

### 6. Status as a Read Target

Use a structured RPC field rather than query-string syntax:

```json
{"method": "vfs.stat", "path": "/mount/foo", "include_status": true}
```

This returns lifecycle state without fetching body content. Clients poll status when resumption matters.

### 7. Streaming Modes

Mirror LightRAG's `stream=True` on queries and LangGraph's `stream_mode` on execution:

- `bytes`: raw chunks
- `records`: parsed row-by-row
- `events`: status transitions (`PENDING → PROCESSING → COMPLETED`)

Client subscribes; server fans out. No change to the request surface.

## Open Questions

1. **Refcount vs. garbage collection.** LightRAG rebuilds the KG on delete because it didn't design refcounting. VFS should refcount, but the boundary is unclear — does an INFERRED edge bump a chunk's refcount, or only EXTRACTED edges? If inference changes over time, refcount churn could be high.

2. **Confidence score calibration.** LLM-reported `confidence_score` values are notoriously uncalibrated. Should FSP expose a post-hoc calibration operation (`vfs.calibrate(mount, ground_truth_set)`) and return calibrated scores separately? Does the unified result schema need both `raw_score` and `calibrated_score`?

3. **Domain-context refresh cadence.** Graphify computes domain context once per run. LightRAG doesn't use domain-aware prompting at all. What's the right cadence for VFS — per mount write, per batch, per day? The cost/benefit trade depends on mount churn rate.

4. **Query-mode taxonomy.** LightRAG's `naive | local | global | hybrid | mix` is a useful starting vocabulary, but it's tied to RAG-style graph+vector retrieval. VFS's mount surface is broader (SQL, REST, filesystem). Should VFS inherit this taxonomy, introduce mount-type-specific modes, or unify around a single `mode` that mounts interpret locally?

5. **Capability-based routing for cross-mount queries.** If a query spans mounts with different capabilities (one supports `semantic_search`, another doesn't), does the dispatcher fall back to the lowest-common-denominator mode, or refuse, or run different modes per-mount and merge? LightRAG doesn't face this because it has one storage; VFS does.

6. **Hyperedges in `vfs_objects`.** Graphify uses hyperedges for group-relations (`attach_hyperedges()`). The current VFS schema has binary connections. Should hyperedges be a distinct namespace, encoded as N-ary rows, or emergent (a "group node" with binary memberships)? Each representation biases downstream queries differently.

7. **Cache schema versioning granularity.** LightRAG's global cache has no schema version. VFS should add one — but at what granularity? Per-mount? Per-computation-id? Per-prompt? Too coarse wastes re-computation; too fine bloats the cache key.
