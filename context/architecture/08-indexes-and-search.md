# 08. Indexes and search: reindex, grep, glean, graph

- **Status:** living diagram, drawn 2026-10-24 against `ba77449`.
- **Shows:** the one maintenance verb, `reindex`, and the phases it runs; then the read side, how `grep`, `glean` and `graph` answer over the indexes plus the dirty overlay, with the Rust engine's kernels named where they run.
- **Legend:** solid is built. Dashed is planned, with the spec named. Rust kernels are marked `[rust]`.
- **Sources:** `storage/backends/database/backend.py` (`reindex`, `_reindex_phases`), `indexing.py`, `lexical.py`, `render.py`, `links.py`, `embed.py`, `signals.py`, `segments.py`, `edges.py`, `grep.py`, `scope.py`, `glean.py`, `distance.py`, `graph.py`; `storage/ranking.py`, `rerank.py`, `results/preview.py`; `crates/vfs-core`; ADRs 033, 036, 038 to 046, 048, 049, 051 to 055, 059, 060, 077, 079.

## The picture: reindex

```mermaid
flowchart TB
  start["reindex() on one mount"] --> lease["Claim the reindex lease<br/>vfs_meta.reindex_holder, heartbeat; a rival run refuses conflict"]
  lease --> render["1 · Render stage (render.py)<br/>bytes bodies whose stamp misses → text renderings<br/>pdf, docx, pptx, xlsx renderers, offloaded, paged, resumable"]
  render --> chunk["2 · Chunk pass (indexing.chunk_dirty)<br/>dirty bodies split into chunks: tree-sitter spans [rust] or recursive splitter<br/>markdown references extracted [rust] and published as links edges<br/>indexable stamp set"]
  chunk --> build["3 · Build a fresh epoch (indexing.build_epoch)<br/>trigram postings over indexable bodies [rust: grams, postings]<br/>lexical index: tokenize, BM25 blocks, summaries, stats [rust: lexical]<br/>rows written under the new epoch, invisible"]
  build --> publish["4 · Publish (indexing.publish_epoch)<br/>flip encoded = true per entry, version-guarded<br/>compare-and-set vfs_meta.current_gram_epoch"]
  publish --> reclaim["5 · Reclaim dead epochs"]
  reclaim --> seg["6 · Re-converge path segments (segments.py)<br/>guarded deltas toward the recomputed truth; drift reported"]
  seg --> edge["7 · Re-converge fs mirror edges (edges.py)"]
  edge --> sig["8 · Signals phase (signals.py)<br/>collect the reference graph in keyset pages<br/>centrality prior, smoothed through the tree [rust: signals]<br/>publish a new generation, flip the pointer, sweep the old"]
  sig --> embed["9 · Embed step (embed.py), only with an embedder<br/>keyset pages of chunks with embedding IS NULL<br/>batches embed with NO transaction open<br/>UPDATE ... WHERE id = :id AND embedding IS NULL"]
  embed --> release["Release the lease; Result carries rendering and embedding extras"]
  sig -.-> pack["planned: pack, cold version rows into deltas (spec 180)"]

  classDef planned stroke-dasharray: 6 4,stroke-width:2px;
  class pack planned
```

Each numbered phase runs in its own writer transaction. The render and embed loops are resumable: they commit in bounded pages behind a durable mark, so a second run finishes what the first left.

## The picture: grep

```mermaid
flowchart TB
  q["grep(pattern, paths, globs, ext ...)"] --> compile["Compile the pattern: regex-crate language<br/>refuse what the engine refuses; per-line law (pattern_matching/grep.py)"]
  compile --> plan["Plan folded trigrams from the pattern (code_grams.py)<br/>no gram predicate → refuse unless allow_scan=True"]
  plan --> scope["Structural scope (scope.py)<br/>globs and ext channels compiled to terms; the permission view joined in"]
  scope --> idx["Index side: encoded rows<br/>fetch the rarest grams' posting blobs for the current epoch<br/>candidate_ids [rust]: decode, intersect, union, meet the scope allow-list, cap"]
  scope --> overlay["Overlay side: NOT encoded rows<br/>bounded, structurally prefiltered fetch of dirty bodies"]
  idx --> gates["Structural gates off the rows' own stored facts<br/>before any content fetch"]
  overlay --> gates
  gates --> verify["Verify every candidate through the one matcher<br/>ContentMatcher.hit_lines or count_lines [rust], offloaded per batch"]
  verify --> hits["Result: Observation rows with Match lines<br/>budget_exhausted.truncated as a warning when the cap bites"]
```

## The picture: glean

```mermaid
flowchart TB
  q["glean(query, limit, paths, globs, ext ...)"] --> tok["Tokenize the query with the index's own tokenizer [rust]"]
  tok --> lex["Lexical leg (glean.py)<br/>round one: summary rows and head blocks per term, score [rust]<br/>round two: select_blocks [rust] asks which later blocks can change the top-k; fetch exactly those<br/>every statement is a key fetch, no scoring SQL"]
  q --> vec["Vector leg, only with an embedder<br/>embed the query through the provider<br/>cosine distance in the engine (distance.py, per dialect)<br/>referee: vector_topk [rust], wrapped by cosine_topk in vector.py"]
  lex --> agg["Aggregate chunks to entries: the best chunk speaks for its entry"]
  vec --> agg
  agg --> norm["Normalise each leg to the unit interval<br/>cosine by its range, BM25 by min-max (ranking.py)"]
  norm --> fuse["Fusion declared on the mount's Ranker<br/>Convex weights, never chosen per call"]
  fuse --> prior["Multiply in stored signals (signal_factors)<br/>the centrality prior, read never computed on the query path"]
  prior --> preview["Query-biased preview per hit (results/preview.py)<br/>cut from the chunk text, no second fetch"]
  preview --> one["One mount's ranked list"]
  one -.-> rerank["Several mounts: rerank.py<br/>one BM25 over the union; a mount's own order is never changed"]
```

## The picture: graph

```mermaid
flowchart LR
  seeds["graph(method, path or observations, depth, edge_types)"] --> hop["One hop: one chunked statement per frontier chunk<br/>vfs_edges in the walk's direction, joined to vfs_entries on the far endpoint<br/>liveness term, type filter, the caller's view at the list rung"]
  hop --> judge["Judge every row<br/>readable: whole; nameable only: bare (path and kind)<br/>a hidden directory on the road: passed as a bare name"]
  judge --> next["Far nodes join the frontier; visited set; stop at depth or limit (128)"]
  next --> hop
  next --> induced["Fetch the edges among the returned nodes once<br/>Observation.depth; edge rows carry type and measure"]
```

## Reading the picture

vfs keeps four indexes and one derived table, and `reindex` is the one verb that builds them: the gram index for `grep`, the lexical index for `glean`'s BM25 leg, the vector column for `glean`'s cosine leg, the stored signals for `glean`'s prior, and the `links` edges that feed `graph`. The write path does not build any of them. It stamps the row dirty and moves on, because an ETL batch of 10,000 files must not wait for tokenising, embedding or tree-sitter.

The gram and lexical indexes are built whole under a fresh epoch and published by one pointer flip. Between the write and the publish, the row's `encoded` flag is false, and `grep` scans it. That is why `grep` has two sides: the index side over encoded rows and the overlay side over dirty rows. Both pass the same structural gates and the same matcher. The matcher is the one authority on what "matches" means, and it lives in the Rust engine.

`glean` is grep's shape with a scorer where grep has a matcher. Its lexical leg never runs scoring SQL: every statement is a key fetch, and the engine scores. Its vector leg runs cosine inside the SQL engine, because every supported dialect has a distance function (ADR 059); the Rust kernel is the referee the dialects are pinned against. The two legs are normalised and fused under a law declared once on the mount.

`graph` is a frontier walk the application holds. Each hop is one chunked statement, and every row is judged against the caller's view before it joins the frontier. A node the caller may read comes back whole; one it may only name comes back bare.

The permission view is a filter inside every one of these statements, never a pass over the rows afterwards. That is the fact that makes the query verbs kernel operations (ADR 087 pin 2).

## Terms this diagram introduces

| Term | Meaning |
|---|---|
| **reindex** | The one maintenance verb: renderings, chunks, links, gram and lexical epochs, segments, edges, signals, embeddings. Runs under a lease. |
| **Lease** | `vfs_meta.reindex_holder` plus a heartbeat. One `reindex` per mount at a time; a rival refuses `conflict`. |
| **Gram, trigram** | Three consecutive bytes of a folded body, packed into 24 bits. The key of the gram index. |
| **Posting list** | One gram's sorted list of entry ids, stored as a varint count plus LEB128 deltas. Decoded only in the engine. |
| **Epoch** | One built generation of the gram and lexical indexes. Built invisible, published by a pointer flip, reclaimed when dead. |
| **encoded** | The entry flag meaning "this row's postings are in the current epoch". False means grep scans it. |
| **Overlay, scan side** | The dirty rows `grep` reads directly because the index does not cover them. Always correct, slower. |
| **Candidate** | An entry the gram index nominates for a pattern. May be a false positive; the matcher decides. Never a false negative. |
| **Matcher** | `ContentMatcher`, the Rust `verify` kernel's class: the one definition of a grep match for every surface, with `count_lines` and `hit_lines` per batch. |
| **Chunk** | One indexed unit of a body, split by tree-sitter spans for code and markup or by the recursive splitter. The unit the lexical index and the embedding describe. |
| **Lexical index, BM25** | The ranked text index: per-term blocks of postings with term frequencies and lengths, plus summary rows that bound every block. |
| **Block, summary** | The lexical index stores up to `BLOCK_SIZE` postings per `(term, block)` row and one summary row per term, so round two can skip blocks that cannot change the top-k. |
| **Leg** | One ranked source inside `glean`: the lexical leg or the vector leg, each aggregated to entries and normalised. |
| **Fusion, Ranker** | How a mount combines its legs: a `Convex` weighting declared on the `Ranker` at construction. |
| **Signal, prior** | A query-independent importance score per entry in `[0, 1]`, computed during `reindex` from the reference graph and the tree, read on the query path. |
| **Preview** | The query-biased excerpt cut from a hit's chunk text; bounded by construction. |
| **Embedding provider** | The seam `reindex` fills `chunks.embedding` through: `model_id`, `dimension`, request caps, embed one batch. Storage owns budgets and the loop. |
| **Frontier walk** | `graph`'s algorithm: the application holds the frontier and the visited set; each hop is one chunked statement; every row is judged. |
| **links edge** | An edge minted from a markdown reference in a body, resolved against the live tree during the chunk pass. |
| **Rust kernel** | A compute routine `crates/vfs-core` exports through `vfs._native`: `distinct_gram_count`, `PostingsBuilder`, `candidate_ids`, `ContentMatcher` (`count_lines`, `hit_lines`), `chunk_spans`, `markdown_refs`, `tokenize`, `LexicalBuilder`, `lexical_score`, `decode_summary`, `select_blocks`, `vector_topk`, `centrality_prior`. The Python wrappers `cosine_topk` and `Chunk.split_batch` sit over `vector_topk` and `chunk_spans`. |

## Open

- `glean` fetches 1,000 candidate entries and builds a preview unconditionally; both are recorded for a spec of their own (memo 2026-10-10).
- Stored signals may count hidden in-links; grep's candidate budget counts hidden candidates (`open-questions.md`).
- `pack` as a `reindex` phase: spec 180.
