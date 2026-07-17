# OpenViking — Influences for VFS and FSP

> Reference repo: `/Users/claygendron/Git/Repos/OpenViking`

## Overview

OpenViking is a context database designed for AI agents, unifying memory, resources, and skills into a hierarchical filesystem paradigm backed by vector retrieval and progressive content loading. Unlike traditional flat-vector RAG, OpenViking models context as a virtual filesystem (`viking://` URIs), implements a three-tier content model (L0 abstract ≈100 tokens / L1 overview ≈2k tokens / L2 detail on-demand), and applies directory-recursive semantic search with reranking. The architecture separates content storage (AGFS, a user-space filesystem in Rust) from index storage (vector database + metadata), dual-path traversal (intent-driven hierarchical search vs. simple vector fallback), and session-based memory self-iteration. FSP's VFS mount routing and semantic search capabilities can directly inherit OpenViking's patterns: the hierarchical retriever's priority-queue recursive descent, the L0/L1/L2 concept mapping to cached metadata layers, URI scoping for multi-tenancy, and the separation of filesystem operations (CRUD) from search intelligence.

## Navigation Guide

**Entry points (understand these first):**
- `/Users/claygendron/Git/Repos/OpenViking/docs/en/concepts/01-architecture.md` — System overview, service layer, dual-layer storage (AGFS + vector index)
- `/Users/claygendron/Git/Repos/OpenViking/docs/en/concepts/07-retrieval.md` — Find vs. search, intent analysis, hierarchical retrieval algorithm, rerank strategy
- `/Users/claygendron/Git/Repos/OpenViking/README.md` — "Filesystem management paradigm", "Tiered context loading", "Directory recursive retrieval"
- `/Users/claygendron/Git/Repos/OpenViking/openviking/storage/viking_fs.py:185–250` — VikingFS main class, singleton pattern, URI conversion
- `/Users/claygendron/Git/Repos/OpenViking/openviking/retrieve/hierarchical_retriever.py:45–150` — HierarchicalRetriever class, vector search, rerank client dispatch

**Data model & namespace:**
- `/Users/claygendron/Git/Repos/OpenViking/openviking/core/context.py:26–100` — Context class, ContextType enum (SKILL/MEMORY/RESOURCE), ContextLevel enum (L0/L1/L2)
- `/Users/claygendron/Git/Repos/OpenViking/openviking/core/namespace.py:1–100` — URI scoping, user/agent/session/resource roots, ResolvedNamespace
- `/Users/claygendron/Git/Repos/OpenViking/crates/ragfs/src/core/types.rs:10–65` — FileInfo struct (name, size, mode, mod_time, is_dir)

**Storage & retrieval:**
- `/Users/claygendron/Git/Repos/OpenViking/crates/ragfs/src/core/filesystem.rs` — AGFS filesystem interface (in Rust)
- `/Users/claygendron/Git/Repos/OpenViking/openviking/retrieve/intent_analyzer.py` — LLM-driven intent decomposition
- `/Users/claygendron/Git/Repos/OpenViking/openviking/service/` — FSService (CRUD ops), SearchService (find/search), SessionService (memory iteration)

**What to skip:** Examples, bot framework code, deployment tooling, OpenTelemetry instrumentation, crypto/auth layers (understand at a high level, not implementation details). VikingBot (the agent framework built on OpenViking) is orthogonal to VFS/FSP design.

## File Index

| Path | Purpose |
|------|---------|
| `/Users/claygendron/Git/Repos/OpenViking/README.md:45–57` | Five core concepts: filesystem paradigm, tiered loading, directory recursion, observable retrieval, session self-iteration |
| `/Users/claygendron/Git/Repos/OpenViking/docs/en/concepts/01-architecture.md:1–50` | System architecture diagram: client → service layer → retrieve/session/parse → storage (AGFS + vector index) |
| `/Users/claygendron/Git/Repos/OpenViking/docs/en/concepts/07-retrieval.md:1–150` | Retrieval flow: intent analysis (0–5 queries), hierarchical search (priority queue, directory recursion), rerank (optional) |
| `/Users/claygendron/Git/Repos/OpenViking/openviking/core/context.py:26–50` | Context type enum (SKILL, MEMORY, RESOURCE), context level enum (ABSTRACT=0, OVERVIEW=1, DETAIL=2) |
| `/Users/claygendron/Git/Repos/OpenViking/openviking/core/namespace.py:46–79` | URI roots: `viking://resources`, `viking://user/{user_id}`, `viking://agent/{agent_id}`, `viking://session` |
| `/Users/claygendron/Git/Repos/OpenViking/openviking/storage/viking_fs.py:185–250` | VikingFS class: singleton, AGFS client wrapping, URI-based operations, L0/L1 reading, relation management |
| `/Users/claygendron/Git/Repos/OpenViking/openviking/retrieve/hierarchical_retriever.py:45–150` | HierarchicalRetriever: priority queue, directory-level vector search, score propagation (SCORE_PROPAGATION_ALPHA=0.5), rerank dispatch |
| `/Users/claygendron/Git/Repos/OpenViking/openviking/retrieve/intent_analyzer.py` | IntentAnalyzer: LLM decomposes query into TypedQuery list (context_type, intent, priority) |
| `/Users/claygendron/Git/Repos/OpenViking/crates/ragfs/src/core/types.rs:10–85` | FileInfo (name, size, mode, mod_time, is_dir), WriteFlag enum (Create/Append/Truncate/None) |
| `/Users/claygendron/Git/Repos/OpenViking/crates/ragfs/src/core/filesystem.rs` | AGFS filesystem trait: read/write/mkdir/rm/mv/ls/stat/glob/grep operations |
| `/Users/claygendron/Git/Repos/OpenViking/docs/en/concepts/03-context-layers.md` | L0 abstract (1-sentence summary), L1 overview (core + usage), L2 detail (full content) |
| `/Users/claygendron/Git/Repos/OpenViking/docs/en/concepts/04-viking-uri.md` | URI syntax: `viking://scope/path`, scope types (resources, user, agent, session, temp, queue) |
| `/Users/claygendron/Git/Repos/OpenViking/pyproject.toml:1–100` | Dependencies: pydantic, httpx, pdfplumber, openai, volcengine, fastapi, tree-sitter-* (code parsing) |
| `/Users/claygendron/Git/Repos/OpenViking/Cargo.toml:1–97` | Rust crates: ragfs (AGFS impl), ov_cli (CLI), ragfs-python (Python bindings); tokio, axum, sqlx, aws-sdk-s3 |

## Core Concepts (What They Did Well)

### 1. Filesystem Paradigm as Abstraction Boundary

**What:** Rather than treating context as flat vectors in a database, OpenViking models all context (memories, resources, skills) as files and directories under a unified `viking://` URI scheme. Directories are navigable via `ls`, `tree`, `glob`; files can be read with progressive content loading (L0 → L1 → L2). The filesystem is virtual — backed by a database (AGFS), not block storage — but agents interact with it like `/resources/api_docs/auth/oauth2.md`.

**Why it matters:** Agents have a mental model of filesystems; they expect hierarchical organization, path resolution, and POSIX-like semantics. Pushing context through a vector-search API requires agents to understand query reformulation and relevance scoring. With a filesystem, agents can use exploratory navigation: `ls viking://resources/`, `cat viking://resources/api_docs/README.md`, `grep "oauth" viking://resources/` — the same commands they use locally.

**VFS implication:** VFS's mount routing, path resolution, and CRUD operations are the right mental model. Don't hide the structural organization behind a semantic-search API; expose the tree so agents can navigate and understand context organization. Make `ls` return rich metadata (abstract, size, type) so agents can make informed decisions without extra network round-trips.

**FSP implication:** FSP's protocol should expose filesystem operations (read, write, ls, mkdir, rm, mv, stat) as first-class, not as sugar over a document-store API. These operations are how agents reason about context organization. Include a `tree` or `ls --recursive` operation for quick structural exploration.

### 2. Three-Tier Content Model (L0/L1/L2) for Token Efficiency

**What:** Every directory and file in OpenViking stores three progressive levels of content:
- **L0 (Abstract)**: One-sentence summary (≈100 tokens) — quick relevance check
- **L1 (Overview)**: Core information + usage scenarios (≈2k tokens) — agent planning phase
- **L2 (Detail)**: Full original content — loaded on-demand

These are stored in parallel: `.abstract.md`, `.overview.md`, and the full content file. Agents query by specifying the level they need; retrieval returns the appropriate tier.

**Why it matters:** LLM context windows are expensive. Stuffing every document's full text into a prompt causes cost explosion and noise. By storing summaries alongside full content, OpenViking lets agents make decisions with cheap L0/L1 data, then fetch L2 only when necessary. This is similar to database query optimization (index → intermediate result → full row).

**VFS implication:** VFS should adopt this pattern explicitly. When storing files, generate and store L0/L1 representations (using LLM or heuristic summary) in special `.abstract.md` and `.overview.md` files within each directory. Make these discoverable and queryable without fetching the full content. Example: `{"op": "stat", "path": "/data/file.txt", "include_levels": ["L0", "L1"]}` returns `{"abstract": "...", "overview": "...", "size": 1024, "type": "text"}`.

**FSP implication:** FSP should allow clients to request content at specific levels. Add a `level` parameter to read operations:
```json
{
  "op": "read",
  "path": "/file.txt",
  "level": "L0"  // Return only abstract
}
```
or
```json
{
  "op": "read",
  "path": "/file.txt",
  "level": "L2"  // Return full content
}
```
This lets clients stay within token budgets while exploring large codebase structures.

### 3. Hierarchical Retrieval via Priority Queue (Not Flat Vector Search)

**What:** OpenViking's HierarchicalRetriever does not search a flat collection of documents. Instead:
1. Determine starting directories based on context type (MEMORY → `viking://user/memories`, RESOURCE → `viking://resources`, SKILL → `viking://agent/skills`)
2. Global vector search within those directories to find candidate files/directories
3. For each candidate, recursively search *children* (subdirectories) with score propagation: `new_score = 0.5 * embedding_score + 0.5 * parent_score`
4. Use a priority queue to explore high-scoring directories first (best-first search)
5. Stop when convergence threshold is reached (same top-K unchanged for 3 rounds)

This hierarchy matters: it constrains search scope, provides context (a result under `/resources/api_docs/` has different meaning than one under `/resources/examples/`), and scales to millions of items without the N² cost of flat search.

**Why it matters:** Semantic similarity is imperfect. A "token endpoint" query might match both `/security/oauth2.md` and `/tutorials/getting_started.md` in flat vector space. But if you search recursively starting from `/security/`, you'll find the true hit higher in the ranking because its parent directory itself is relevant. The directory hierarchy disambiguates.

**VFS implication:** VFS should implement a similar hierarchical search in its `_glob_impl` and semantic search methods. Don't flatten the tree. When a backend receives a recursive glob or find request, use the directory structure to constrain and rank results. Example: `glob("/data/**.py")` should traverse `/data/` recursively, prioritizing matches in directories that themselves match the query intent.

**FSP implication:** FSP's search protocol should support directory-scoped queries:
```json
{
  "op": "find",
  "query": "authentication",
  "scope": "viking://resources/apis",  // Search within this subtree
  "recursive": true,
  "limit": 10
}
```
Backends implement hierarchical search within the scope, not global table scans.

### 4. Intent Analysis + Query Decomposition (LLM-Driven Search Strategy)

**What:** OpenViking's `search()` API (vs. simple `find()`) uses an `IntentAnalyzer` that parses a user query via LLM and decomposes it into 0–5 `TypedQuery` objects, each with:
- `query`: Rewritten, normalized query string
- `context_type`: One of SKILL, MEMORY, RESOURCE
- `intent`: Semantic purpose ("create RFC", "find example", "get user preference")
- `priority`: Integer 1–5 ranking

Example: User asks "Help me write an API docs RFC using our template and coding style." The LLM emits:
1. RESOURCE, priority=5, "API documentation RFC template"
2. MEMORY, priority=4, "User's coding style preferences"
3. SKILL, priority=3, "Write API documentation"

Each typed query is then passed to the hierarchical retriever independently, results are merged by priority.

**Why it matters:** Agents don't naturally decompose complex requests. A human asking for "help writing docs" implicitly wants (template) + (style guide) + (examples). Forcing the agent to issue three separate queries is clunky. The LLM decomposes once, the system parallelizes retrieval, and the agent gets a cohesive result set ranked by relevance + intent.

**VFS implication:** VFS's `find()` is currently a simple string query. Consider adding a `search()` method that accepts a query plus optional `context_hints` (enum: MEMORY/RESOURCE/SKILL). VFS can then constrain its internal search scope and focus backends on the right namespaces. Example:
```python
await fs.search(
    query="authentication pattern",
    context_hints=[ContextType.RESOURCE, ContextType.MEMORY],
    limit=5
)
```
VFS routes to `viking://resources/` and `viking://user/memories/` first.

**FSP implication:** FSP's `find` operation should optionally accept `context_type` and `intent` hints from clients. This guides the search strategy:
```json
{
  "op": "find",
  "query": "REST API endpoints",
  "context_type": "RESOURCE",
  "intent": "code_example",
  "limit": 10
}
```
Backends can weight results differently based on intent (prioritizing examples vs. documentation).

### 5. Relation Graph as Metadata Plane (Separate from Content)

**What:** OpenViking stores relation entries in parallel with the filesystem. A relation is a tuple `(id, uris[], reason, created_at)` — explicit connections between resources. For example:
- User reads `/docs/auth.md`, agent creates relation: `id="rel_123", uris=["/docs/auth.md", "/docs/oauth2.md"], reason="oauth2_spec_reference"`

Relations are queryable independently via `list_relations(uri)` or `relations(filter)`. They're stored in `.relations.json` files within directories or in a dedicated index.

**Why it matters:** The filesystem is static structure; relations capture discovered patterns and agent reasoning. When retrieving context for a follow-up query, relations let you say "the agent previously linked these two docs; include both." This creates a feedback loop: agent acts (reads file A), links it to file B, future queries use those links to improve retrieval.

**VFS implication:** VFS's connection graph (currently stored as `grover_connections` table with source/target) is the relation concept. Make connections queryable and updateable through VFS operations:
```python
await fs.link(source="/path/a", target="/path/b", reason="related_to_auth")
await fs.unlink(source="/path/a", target="/path/b")
connections = await fs.relations(uri="/path/a")  # Get all outgoing relations
```
This mirrors OpenViking's relation API.

**FSP implication:** FSP should expose relations as first-class operations:
```json
{
  "op": "link",
  "source": "/path/a",
  "target": "/path/b",
  "reason": "contains_same_api"
}
```
and
```json
{
  "op": "relations",
  "uri": "/path/a",
  "direction": "outgoing"  // or "incoming" or "both"
}
```

### 6. Session-Based Memory Self-Iteration (Context Extraction + Feedback Loop)

**What:** OpenViking's `SessionService` tracks agent interactions (messages, tool calls, results) within a session. At session end, the service:
1. **Compresses** old messages (keep recent N rounds, archive older)
2. **Extracts** 8-category memories: learned behaviors, user preferences, code patterns, task templates, error handling, domain knowledge, tool usage, decision rationale
3. **Generates** L0/L1 summaries for extracted memories
4. **Stores** in `viking://user/memories/` and `viking://agent/memories/`
5. **Vectors** these memories in the index

Future queries can then retrieve these learned memories, creating a feedback loop: agent acts → learns → future agent builds on learned context.

**Why it matters:** Most RAG systems are static. Once a document is indexed, it doesn't change. But agents learn through repeated interactions — the patterns they discover should inform future queries. Session-based extraction bridges the gap: context isn't just ingested data; it's also synthesized knowledge from agent execution.

**VFS implication:** VFS doesn't manage sessions currently (that's an FSP/agent runtime concern), but VFS should **support append-only memory writing** so agents can accumulate learned context. Add a method:
```python
await fs.write(
    path="viking://agent/memories/learned_patterns.md",
    content="Pattern: always check for CORS headers in API responses",
    append=True  # Append to existing file
)
```
This lets agents iteratively build up learned context without overwriting.

**FSP implication:** FSP should allow append-only writes (similar to log files). Add an `append` flag to write operations:
```json
{
  "op": "write",
  "path": "/learned_patterns.md",
  "content": "...",
  "append": true,
  "deduplicate": true  // Optional: only append if content doesn't already exist
}
```
This supports agent-driven memory accumulation without mutation conflicts.

### 7. Dual-Path Storage: AGFS (Content) + Vector Index (Metadata)

**What:** OpenViking separates storage into two layers:
- **AGFS** (Rust user-space filesystem): Stores L0/L1/L2 content, multimedia, directory structure, relations
- **Vector Index** (SQL + vector database): Stores URIs, embeddings, metadata, no actual content

When you `read()` a file, AGFS is queried. When you `search()`, the vector index is queried first (fast, returns URIs + abstracts), then AGFS is lazily accessed for full content.

**Why it matters:** Decoupling content from index enables different optimization strategies. Content storage needs efficient read/write, concurrent access, and quotas. Index storage needs fast vector similarity search, filtering, and metadata joins. Mixing them leads to compromise. By separating, each layer uses the right storage engine (filesystem for content, vector DB for search).

**VFS implication:** VFS's current design already separates this somewhat: the `grover_objects` table (content) and `grover_vectors` table (embeddings). Make this separation explicit in the API:
- `_read_impl()` queries `grover_objects` only
- `_search_impl()` queries `grover_vectors` + metadata, returns URIs + abstracts
- `_find_impl()` chains: search (fast) → lazy read (on-demand)

Document which operations hit which storage layer; this guides performance expectations.

**FSP implication:** FSP should expose both layers:
```json
{
  "op": "search",
  "query": "OAuth",
  "level": "L0"  // Only return abstracts from vector index, don't fetch full content
}
```
Returns fast, cheap results. Later:
```json
{
  "op": "read",
  "path": "/path/a",  // From search result
  "level": "L2"  // Now fetch full content
}
```

### 8. Rerank as Optional Post-Processing (Not Mandatory)

**What:** OpenViking's `HierarchicalRetriever` implements reranking as an optional fallback:
1. If rerank provider is configured and mode is THINKING, use rerank model (e.g., Cohere, Volcengine)
2. Otherwise, use embedding scores directly
3. If rerank fails (API error, timeout), fall back to embedding scores (degrade gracefully)

Rerank takes top-K candidates from vector search and refines scores using a cross-encoder model or LLM.

**Why it matters:** Vector search (recall) and rerank (precision) are complementary. Vector search is fast but imperfect; rerank is slower but more accurate. Making rerank optional lets systems scale: low-latency queries skip rerank, high-quality queries use it. Graceful fallback ensures the system doesn't break if the rerank service is unavailable.

**VFS implication:** VFS's search scoring is currently vector-only. If a reranker becomes available (via config), wire it as an optional post-processing step:
```python
# In _search_impl or hierarchical_retriever
candidates = await vector_index.search(query, limit=20)  # Recall phase
if rerank_config and rerank_config.is_available():
    candidates = await rerank_client.rerank(query, candidates)  # Precision phase
    candidates = [c for c in candidates if c.score >= threshold]
return candidates[:limit]
```
Document that rerank is optional and degrades gracefully.

**FSP implication:** FSP's search API should advertise rerank capability:
```json
{
  "op": "capabilities"
}
```
returns
```json
{
  "rerank_available": true,
  "rerank_provider": "cohere"
}
```
Clients can then decide: request reranked results (slower) or not (faster).

## Anti-Patterns & Regrets

### 1. Vector Index Inconsistency with Content Store

**Issue:** When content is deleted or moved in AGFS, the vector index may not be updated immediately. Results can include references to non-existent URIs.

**Regret:** OpenViking had to add explicit vector sync operations (`vector_sync_on_rm`, `vector_sync_on_mv`) to keep the index consistent. This couples filesystem operations to index maintenance.

**For VFS:** Treat the vector index as a cache, not a source of truth. When `_rm_impl` deletes a file, it must also delete the corresponding vectors. Design the schema so this is atomic (e.g., foreign key with ON DELETE CASCADE) or implement a cleanup job. Don't let stale vectors accumulate.

### 2. Context Type Inference Fragility

**Issue:** When a user uploads a document, OpenViking guesses whether it's a RESOURCE, SKILL, or MEMORY. This guess is wrong often enough that users have to manually re-organize or re-index.

**Regret:** The `_derive_context_type()` heuristic (based on URI path patterns) is brittle. A file under `/agent/skills/` is assumed to be a skill, but if the user uploaded it to the wrong directory, retrieval fails.

**For VFS:** Don't rely on path-based context type inference. Instead, allow users to declare context type explicitly (as metadata or URI annotation). Example: `viking://resources/apis/oauth2.md?context_type=RESOURCE` or store type in `.meta.json` alongside the file. Let agents override the inferred type.

### 3. Permission Model Mismatch

**Issue:** OpenViking uses Unix-style permissions (read/write by user/agent/group) but doesn't enforce them consistently. Some operations check permissions, others bypass them.

**Regret:** The permission model is aspirational but incomplete. Agents can often read resources they shouldn't, depending on which API they call.

**For VFS:** Define permissions early and enforce them in every operation. VFS already has a `PermissionMap` — use it consistently. Example: `check_readable(user_id, path)` before every read, `check_writable(user_id, path)` before every write. Make enforcement automatic, not optional.

### 4. Rerank Threshold Tuning Difficulty

**Issue:** Rerank score thresholds are heuristic (usually 0–1 on a cross-encoder model). Users don't know what threshold to set. Too low = noisy results; too high = no results.

**Regret:** OpenViking exposes `score_threshold` as a config parameter but provides no guidance. Users either guess or turn reranking off.

**For VFS:** If supporting reranking, expose it but with sensible defaults. Document what the score range means (e.g., "0.7 = 70% confidence this is relevant"). Provide a calibration utility: given sample queries + expected results, suggest a threshold. Or use a learned threshold from your training data.

### 5. L0/L1 Generation Async Overhead

**Issue:** When a document is added to OpenViking, L0/L1 generation happens asynchronously in the background. Users must `wait_processed()` explicitly to ensure summaries are ready. If they don't wait, subsequent `search()` calls return incomplete results (L0/L1 may be missing).

**Regret:** The async queueing is necessary for performance but creates a consistency gap. Distributed queries now must handle "partial processing" state.

**For VFS:** If supporting L0/L1 generation, either:
1. Generate synchronously on write (simple, slower) — user waits for summaries before return.
2. Generate asynchronously but queue queries until ready (more complex, no consistency gap) — `search()` waits internally.
3. Return partial results with a "processing" flag and let clients retry (simplest, but agents must handle retries).

Document clearly which mode VFS uses.

### 6. Session Compression Loses Fine-Grained History

**Issue:** OpenViking's session compression aggregates older messages into batches and summarizes them. Fine-grained message history (who said what when) is lost after N rounds.

**Regret:** Useful for cost reduction but harmful for debugging. If an agent misbehaved 50 messages ago, you can't find the exact interaction.

**For VFS:** If implementing session history, store full messages append-only, but allow lazy summarization. Keep a `messages` table and a separate `summaries` table. Don't aggregate; let agents query both if needed.

### 7. Cyclic Relation Detection Missing

**Issue:** OpenViking allows agents to create relations freely. A document can be linked to another, which links back (A→B→A), creating cycles. No cycle detection exists.

**Regret:** When traversing relations, graphs with cycles can cause infinite loops or quadratic behavior.

**For VFS:** If implementing a relation/connection graph, add cycle detection. Either:
1. Forbid cycles (validate on link creation) — simplest.
2. Allow cycles but mark them; traversal algorithms skip marked edges.
3. Compute strongly-connected components and represent as meta-nodes.

Document which approach you choose.

## Implications for VFS (Implementation)

### 1. Implement Hierarchical Search with Priority Queue

Extend VFS's `_search_impl` to use OpenViking's pattern:
- Start from root directories (constrained by context_type or explicit scope)
- Global vector search within root to find candidate files/directories
- For each candidate, recursively search children with score propagation
- Use heapq to order by relevance score
- Stop at convergence (top-K unchanged for N rounds)

This avoids O(N) flat search and provides context-aware ranking.

### 2. Add L0/L1 Metadata Layers to File Model

Extend the `Entry` or `Detail` dataclass to include:
```python
@dataclass
class Entry:
    path: str
    is_dir: bool
    size: int
    abstract: Optional[str] = None  # L0
    overview: Optional[str] = None  # L1
    version: Optional[str] = None
    content_type: Optional[str] = None
```

When storing files, compute and store L0/L1 (via LLM summary or heuristic). Make them queryable without fetching full content.

### 3. Namespace Scoping for Multi-Tenancy

Adopt OpenViking's namespace pattern:
```
viking://resources/       # Shared resources
viking://user/{user_id}/  # User-scoped memory
viking://agent/{agent_id}/ # Agent-scoped skills
viking://session/{session_id}/ # Ephemeral session data
```

Enforce scoping at the VFS level: a user can only see `viking://user/{their_id}/`. Query all backends with this prefix constraint.

### 4. Relation Graph as First-Class Storage

Extend `grover_connections` to be queryable and updateable via VFS operations:
```python
await fs.link(source, target, reason="...")
await fs.unlink(source, target)
connections = await fs.relations(path, direction="outgoing")
```

Store relations with timestamps and metadata. Let backends query by relation type or traverse multi-hop paths.

### 5. Support Append-Only Writes

Add an `append` flag to `_write_impl`:
```python
async def _write_impl(
    self,
    path: str,
    content: Union[str, bytes],
    append: bool = False,  # New
    user_id: Optional[str] = None,
) -> VFSResult[None]:
```

For append=True, concatenate new content to existing file. Useful for agents accumulating logs or learned patterns.

### 6. Graceful Reranker Fallback

If integrating a reranker, make it optional:
```python
if self.rerank_config and self.rerank_config.is_available():
    try:
        scores = await rerank_client.rerank(query, candidates)
    except Exception as e:
        logger.warning(f"Rerank failed: {e}, falling back to vector scores")
        scores = [c.score for c in candidates]
else:
    scores = [c.score for c in candidates]
```

Document which operations use reranking and when fallback occurs.

### 7. Track Content Versions Separately from Index Versions

Maintain two version sequences:
- **Content version**: Incremented when file content changes (L0/L1/L2)
- **Index version**: Incremented when metadata changes (permissions, tags, relations)

This allows queries like "what changed since I last read?" without re-embedding unchanged content.

## Implications for FSP (Protocol)

### 1. Add `level` Parameter to Read Operations

```json
{
  "op": "read",
  "path": "/api_docs/oauth2.md",
  "level": "L0",  // "L0", "L1", "L2", or "L0+L1+L2" (default: L2)
  "include_metadata": true  // Optional: return {abstract, overview, size, type}
}
```

Returns only the requested tier(s), saving tokens and network.

### 2. Expose Search as Distinct from Read

```json
{
  "op": "search",
  "query": "authentication",
  "scope": "viking://resources",  // Optional: constrain search
  "context_type": "RESOURCE",  // Optional: hint for hierarchy
  "limit": 10,
  "level": "L0"  // Return abstracts only
}
```

vs.

```json
{
  "op": "read",
  "path": "/path/to/file",
  "level": "L2"
}
```

Clear separation: search for discovery, read for content.

### 3. Hierarchical Search with Optional Rerank

```json
{
  "op": "find",
  "query": "REST endpoints",
  "target_directories": ["viking://resources/apis"],  // Optional scope
  "recursive": true,  // Traverse subdirectories
  "limit": 10,
  "rerank": true,  // Optional: use rerank if available
  "score_threshold": 0.6
}
```

returns

```json
{
  "results": [
    {
      "uri": "viking://resources/apis/rest/endpoints.md",
      "abstract": "...",
      "score": 0.85,
      "reranked": true
    }
  ],
  "converged": true,  // Search stopped due to convergence
  "searched_directories": ["viking://resources/apis"]
}
```

### 4. Relations as First-Class Operations

```json
{
  "op": "link",
  "source": "viking://resources/apis/oauth2.md",
  "target": "viking://resources/apis/token.md",
  "reason": "token_endpoint_spec"
}
```

```json
{
  "op": "relations",
  "uri": "viking://resources/apis/oauth2.md",
  "direction": "outgoing",  // or "incoming" or "both"
  "limit": 10
}
```

### 5. Append-Only Write Support

```json
{
  "op": "write",
  "path": "viking://agent/memories/learned_patterns.md",
  "content": "Pattern discovered: ...",
  "append": true,
  "deduplicate": true  // Optional: skip if content already exists
}
```

### 6. Capabilities Advertisement with Context-Type Support

```json
{
  "op": "capabilities"
}
```

returns

```json
{
  "operations": ["read", "write", "search", "find", "ls", "mkdir", "rm", "mv", "link", "unlink", "relations"],
  "levels_supported": ["L0", "L1", "L2"],
  "context_types": ["RESOURCE", "MEMORY", "SKILL"],
  "rerank_available": true,
  "rerank_provider": "cohere",
  "backends": [
    {"mount": "viking://resources", "type": "database", "max_depth": 5},
    {"mount": "viking://user/{user_id}", "type": "database", "scoped": "per_user"}
  ]
}
```

### 7. Intent-Driven Query Hints

```json
{
  "op": "find",
  "query": "write authentication docs",
  "intent": "create_documentation",  // Hint for intent analysis
  "context_types": ["RESOURCE", "MEMORY", "SKILL"],  // Limit search to these types
  "limit": 10
}
```

Servers can use intent hints to prioritize which backends to query.

## Open Questions

1. **L0/L1 generation cost and timing:** Should VFS generate summaries synchronously (slower write), asynchronously (consistency gap), or lazily (cold-start cost)? What if the LLM is unavailable? Should summaries be cached or regenerated on each write?

2. **Hierarchical search scalability:** With 10M files organized in a deep tree, does priority-queue traversal scale? Should VFS implement early stopping heuristics beyond convergence detection?

3. **Vector index freshness:** How stale can the index be? If a file is modified but its vector isn't updated immediately, will retrieval return correct results? Should there be an explicit `vector_sync` operation?

4. **Rerank provider negotiation:** If FSP supports multiple reranking backends (Cohere, Volcengine, Jina), how do clients specify which to use? Per-request header, per-session config, or auto-selection?

5. **Relation traversal complexity:** If a user queries "find all connected resources to /path/a", how deep should traversal go? Should there be a max depth or max result count to prevent graph explosion?

6. **Session memory extraction strategy:** Should agents control which memories are extracted, or does the system auto-extract all categories? How do you prevent extraction of sensitive data (passwords, API keys) from session transcripts?

7. **Cross-mount relation semantics:** Can a relation link a file in mount A to a file in mount B? If mount B is unmounted, is the relation dangling? Should VFS validate relation URIs on query?

8. **L0/L1 language handling:** OpenViking's summaries are generated in English. How should VFS handle multilingual content? Generate L0/L1 in the original language or normalized to English?

