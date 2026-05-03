# 022 — Hybrid Search Across Mounts

- **Status:** draft
- **Date:** 2026-05-02
- **Owner:** Clay Gendron
- **Kind:** feature · search · cross-backend ranking
- **Depends on:** 015, 016, 017, 019, 020
- **Enables:** real multi-corpus knowledge search; the agent
  pattern of "search everything I have access to"

## Intent

Make hybrid (BM25 + vector) search work across multiple mounts
so a single query returns one merged, ranked list spanning every
backend the session can see, with each result honestly carrying
provenance about where it came from.

This is harder than glob fanout because **scoring is not
embarrassingly parallel**. BM25's IDF is corpus-specific.
Vector similarity is dimensionality-and-model-specific. Naive
"call each mount, concatenate, sort by score" produces wrong
rankings — a backend with shorter documents gets unfair BM25
boost; a backend with a different vector model contaminates the
list with non-comparable similarities.

This story defines:

- The **per-backend score normalization** rules that make merging
  honest.
- The **router-level merge / re-rank** policy.
- The **provenance contract** so the agent (and the user) can
  see "this came from your scratch", "this came from the shared
  corpus", "this came from the Slack mount".

## Why

- **Multi-tenant queries are the core use case.** Search across
  a shared corpus + the user's private workspace + a Slack
  archive is what makes VFS more than a document index.
- **The shadow-resolution work in 019 needs a concrete consumer.**
  Per-candidate `Detail.mount` provenance only means anything if
  search uses it.
- **Today's hybrid is single-backend.** The router fans out for
  glob/grep but does not merge ranked search results across
  mounts in a coherent way. With unions (019) and remote
  backends (020) this becomes a correctness gap, not just an
  ergonomic one.

## Scope

### In

1. **Per-backend score normalization.**
   Every backend returns scores normalized to **`[0, 1]` at the
   backend boundary.** This is already in the synthesis memo.
   The router does not re-scale; it trusts the boundary.
   Backends that produce raw scores convert before returning
   (BM25 normalization to `[0,1]` per corpus; vector cosine
   already in range).

2. **Three-mode hybrid score in `VFSResult.Detail`.**
   ```python
   class Detail:
       ...
       lexical_score: float | None      # BM25 / FTS
       vector_score: float | None       # cosine / dot / L2 normalized
       hybrid_score: float | None       # backend's chosen blend
       mount: str                        # which mount produced this
       index: str | None                 # which index inside the mount
   ```
   Backends fill what they have. The router has *all three* per
   candidate from each backend.

3. **Router-level merge.**
   ```python
   async def search(self, *, query: str, paths=(),
                    kinds=("hybrid",), top_k=20, ...) -> VFSResult:
       # 1. Decide which mounts to query (paths filter, capabilities)
       # 2. Fan out: each mount returns its top_k normalized
       #    candidates with all three scores filled in.
       # 3. Re-rank at the router: merge by hybrid_score, then
       #    apply diversity / dedup / shadow-filter rules.
       # 4. Trim to top_k overall.
   ```
   The router does not re-score; it picks among already-scored
   candidates. (No second BM25 pass.)

4. **Diversity rules.**
   Default rule: at most `ceil(top_k / mount_count)` from any
   one mount in the merged result, until shortage forces more.
   This prevents one large corpus from dominating. Configurable
   via `diversity="proportional"|"open"|"strict_round_robin"`.

5. **Shadow filtering (from 019).**
   Search candidates whose path is shadowed by a higher-priority
   union member at the same union path are dropped before
   re-rank. This is the user's correctness requirement.

6. **Per-mount IDF, never blended.**
   BM25 IDF is computed per backend, never across the merged
   result. Documented and tested. A short-doc backend cannot
   suppress the IDF of a long-doc backend.

7. **Vector model compatibility.**
   Each backend declares its embedding model id. The router
   refuses to merge vector hits across **different** models and
   warns in the result's `errors` field:
   `mount.search_partial_no_vector_merge — backends use different
   embedding models; lexical scores merged, vectors per-mount`.
   Lexical hits still merge.

8. **Per-candidate provenance.**
   Every result carries `mount`, `index`, `lexical_score`,
   `vector_score`, `hybrid_score`. Agents and UIs can branch on
   provenance and show source labels.

9. **Capability flags (matching 020).**
   - `search.lexical` — backend supports BM25/FTS
   - `search.vector` — backend supports vector similarity
   - `search.hybrid` — backend has its own blend policy
   - `search.embedding_model` — model identifier string

   Backends without `search.*` are skipped during search fanout.

10. **Search through unions (019 interaction).**
    Each union member is queried independently. The router
    drops shadowed candidates, then merges across the
    union's *visible* members. Per-mount diversity rules
    treat each union member as a distinct mount (a 3-member
    union counts as 3 mounts for the diversity cap).

11. **Search through binds (018).**
    Bind aliases forward to upstream. Path rewriting at the
    bind boundary. Scores are unchanged.

12. **Search through remote backends (020).**
    Remote backends serve `fs.search` over the wire. They run
    their own BM25/vector internally and return normalized
    candidates. The router merges the same way as for in-process
    backends.

### Out

- A globally calibrated scoring system that normalizes across
  embedding models. Open research; out of scope. Different
  models yield non-comparable scores, period.
- Cross-corpus IDF (true global BM25). Requires shared corpus
  statistics; we deliberately don't.
- Re-ranking via a separate cross-encoder. A future story
  ("re-rank with model X") layers on top of this.
- Federated query optimization. Today's fanout is "all eligible
  mounts in parallel"; tuning is later.
- Persistence of search sessions / refinement. That is story
  024 (graph workspace) generalized to search.

## Acceptance Criteria

1. **Single-mount search unchanged.** Existing one-backend
   search behavior is bit-identical for a single-mount setup.
2. **Two-mount search merges correctly.** Tests assert that a
   query against `[scratch, shared]` returns candidates from
   both, ranked by `hybrid_score`, with `Detail.mount` set.
3. **Diversity rule enforced.** With `top_k=10` and 3 mounts of
   1000 docs each, no mount supplies more than 4 of the 10
   results unless others lack candidates.
4. **Shadow filtering applied.** A scratch-shadowed file in
   shared is not returned, even if its score would have ranked
   it.
5. **Per-mount IDF maintained.** A test fixture where one
   backend has 3-word docs and another has 300-word docs:
   the short-doc backend's per-corpus IDF dominates its hits;
   doesn't bleed into the long-doc backend's hits.
6. **Embedding-model-mismatch warning.** Two backends with
   different `embedding_model` capability strings produce a
   merged result with `errors` carrying the partial-merge
   warning; lexical scores still merged.
7. **Provenance in JSON.** Every candidate's `Detail` has
   `mount`, `index`, and the three score fields. Round-trips
   through `VFSResult.to_json` / `from_json`.
8. **Search through bind.** Same query against `/docs` (a bind)
   returns the same candidates as against the source (paths
   rebased to `/docs`).
9. **Search through union.** Three-member union returns merged
   results respecting the per-member shadow rules from 019.
10. **Search through remote.** A `mcp+stdio://` mount's results
    merge into the local result with no router-side
    accommodation needed.
11. **Capabilities pruning.** A backend without `search.lexical`
    contributes only vector hits; a backend without
    `search.vector` contributes only lexical hits; a backend
    with neither is skipped silently.
12. **Performance.** Search across 5 mounts each with 100k docs
    returns in <500ms on a fixture (numbers indicative).

## Risks

- **Score normalization is an honest-but-imperfect heuristic.**
  Different backends' [0,1] scores are not strictly comparable
  even after normalization. Mitigation: be explicit in docs;
  surface `mount` in `Detail` so the agent can branch; provide
  diversity rules so one corpus can't dominate.
- **Different embedding models.** Real-world deployments have
  this. Mitigation: per-mount vector ranks separately;
  user/agent decides which mount to dig into.
- **Backend without normalized scores.** Some external backends
  return raw similarity numbers. Mitigation: a small adapter
  per backend kind that does the normalization at the
  `RemoteFS` boundary.
- **Latency from slowest mount.** Fanout waits for the slowest.
  Mitigation: per-mount timeout (default 2s); slow mount
  contributes nothing to merged result; warning in `errors`.
- **Search-shadow bug.** The shadow-filter pass is critical;
  must be tested across union, bind, and remote.

## Open Questions

1. **Does the router pick the hybrid blend coefficient or does
   each backend?** Default: each backend computes its
   `hybrid_score` per its own policy; router uses that as-is.
   Future story: configurable router-level re-blend.

2. **Should `top_k` be per-mount or global?** Default: global,
   with diversity cap. Per-mount `top_k` is computed as
   `top_k * 2` to give the merge enough overlap to pick from.

3. **What about queries that span only certain mounts (e.g.,
   `paths=("/tenants/acme/",)`)?** Default: handled by the
   path-prefix pre-filter; only matching mounts are queried.

4. **Should empty mounts be excluded from diversity?**
   Default: yes — diversity cap is over mounts that
   actually contributed candidates.

## References

- `src/vfs/bm25.py`, `src/vfs/vector.py` — single-backend score impls
- `src/vfs/results.py` — `Detail`, `Candidate` (extend with
  scores + mount + index)
- `src/vfs/base.py:613, 742, 958` — fanout helpers (already do
  glob/grep merge; this story models search after them)
- Synthesis memo §"unified search result shape", §"capability
  negotiation"
- Story 020 — capability declaration shape
- Story 019 — shadow filtering precondition
