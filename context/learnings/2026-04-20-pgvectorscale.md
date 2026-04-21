# pgvectorscale for the Postgres backend

> Companion to `src/vfs/backends/postgres.py`. Written while asking whether to add Timescale's `pgvectorscale` alongside the `pgvector` index we already require. If only one sentence survives: **not yet — the wins show up at deployment corpora that don't exist today, and adopting now means carrying an extra extension dependency and an index-method branch for a workload that HNSW handles comfortably. Reconsider when either (a) a single deployment's `vfs_objects.embedding` count crosses ~1–5M, or (b) label-filtered ANN becomes a product requirement.**

## Why we're here

`PostgresFileSystem` currently enforces `CREATE EXTENSION vector` and an ANN index in one of `("hnsw", "ivfflat")` (`postgres.py:71`, `postgres.py:208-241`). `pgvectorscale` is Timescale's follow-on extension that adds a third index type — `diskann` — plus two features that plain pgvector does not have (Statistical Binary Quantization, label-based filtered ANN). It's not a replacement for pgvector; it depends on it, reuses the `vector(N)` column type, and `CREATE EXTENSION vectorscale CASCADE` pulls pgvector in automatically.

The question is whether Grover's workload justifies the extra operational surface today.

## What Grover's workload actually looks like

This matters because "pgvectorscale vs pgvector" is a scale question, and the scale premise needs to match reality, not a generic RAG comparison.

- **Deployment-wide, not per-user.** `vfs_objects` is one heterogeneous table per mounted `DatabaseFileSystem`. User/mount scoping is a path-prefix filter (`WHERE path LIKE '/{scope}/%'`), transparent to the VFS API. Row counts accumulate across every user, every mount, every version, every chunk — not per tenant. See `docs/architecture.md:16-53` and story 003 `spec.md:28-31`, `:94-102`.
- **Embeddings are on chunks, not just files.** `VFSObject.embedding` lives on the same table as files, directories, versions, and edges (`src/vfs/models.py`, story 003 `spec.md:217-249`). A single 10k-document deployment with chunked content can already be in the 100k–1M embedding range.
- **Precedent for "what's large":** Story 006's `pg_textsearch` evaluation cites Tiger's MS-MARCO benchmark at 138M passages (`context/learnings/2026-04-20-postgres-native-bm25.md:50-52`). That's the scale the BM25 extension call was made against, and it's roughly the same magnitude where DiskANN pulls away from HNSW.
- **Query shape:** short, concurrent, top-k, agent-driven (story 006 `spec.md:25-33`). Same shape that pgvectorscale is tuned for — but also the shape HNSW is already excellent at.

So "scale" here means a single deployment's full corpus, which can realistically grow large. It still doesn't mean *every* deployment will.

## What pgvectorscale actually adds

### StreamingDiskANN index

A new index method alongside `hnsw`/`ivfflat`. Based on Microsoft's DiskANN with streaming ingest support. The practical difference from HNSW:

- **Disk-resident graph.** HNSW wants the whole graph in RAM; DiskANN keeps hot pieces in memory and streams the rest. This is the cost story — you can index corpora larger than RAM without paying for RAM.
- **Benchmarks are at 50M vectors.** Timescale reports 471 QPS at 99% recall on 50M Cohere embeddings, 11× Qdrant, 28× lower p95 vs Pinecone s1, 75% lower infra cost vs Pinecone self-hosted. These are marketing numbers but the shape is consistent with DiskANN literature.
- **Below ~1M vectors the delta is noise.** Multiple independent benchmarks put HNSW and DiskANN within each other's error bars until the working set stops fitting in RAM. Grover deployments well under that threshold gain nothing measurable from switching.
- **Relaxed ordering by default.** Results may return slightly out of order; exact rank order requires wrapping in a materialized CTE. This is a behavior change for `_vector_search_impl` — currently the ORDER BY on `<=>` is authoritative (`postgres.py:633+`).
- **Incompatible with `UNLOGGED` tables.** Not a current concern for Grover, but worth noting.

### Statistical Binary Quantization (SBQ)

Timescale's variant of binary quantization. Encodes each vector dimension as one bit based on learned statistics rather than a fixed threshold. 32× storage reduction with better recall than naive BQ. Tangential to Grover today — we store full-precision embeddings and haven't hit a storage wall — but it's the feature that makes DiskANN viable on embedding-heavy deployments.

### Label-filtered ANN (Filtered DiskANN)

This is the feature most relevant to Grover's data model. The index can be built with a label column, and filtered queries (`WHERE label = X`) stay efficient inside the ANN traversal rather than pre-filtering or post-filtering around it.

Grover routinely combines vector search with path-prefix filters — user scoping, mount scoping, directory scoping, edge-type filters. Today these are expressed as `WHERE path LIKE ...` around the ANN `ORDER BY`. At small scale that's fine; at large scale it's the classic "filter vs. ANN ordering" problem where pgvector's `WHERE` either over-retrieves or loses recall. Filtered DiskANN would let us encode the scope as a label and push the filter into the graph walk.

This is the feature I'd come back for *before* the raw throughput numbers matter.

## Cost of adopting it now

- **Another required extension.** Today `_verify_vector_schema` (`postgres.py:149-243`) fails fast if `pg_extension WHERE extname = 'vector'` is missing. Adopting pgvectorscale means a second `CREATE EXTENSION vectorscale` check and a migration path for existing deployments. It also narrows the set of Postgres hosts the backend will run on: AWS RDS/Aurora ship neither, Tiger Cloud and self-hosted Linux/ARM are fine, and Postgres on Intel Mac dev laptops has no supported build (Docker/ARM/Linux only).
- **Index-method plumbing.** `VECTOR_INDEX_METHODS` (`postgres.py:71`) and `postgres_vector_column_spec` in `src/vfs/models.py` would need `diskann` added with its own opclass mapping (`vector_cosine_ops`, `vector_l2_ops`, `vector_ip_ops`). Same structural pattern as the existing hnsw/ivfflat branch, so not architecturally new, just wider.
- **Query-shape nuance.** Relaxed ordering and label-aware query building are behavior changes in the native vector path, not just a schema swap. Worth doing deliberately, not as a drive-by.
- **Licensing.** pgvectorscale is PostgreSQL-licensed (permissive). No legal friction — unlike pg_search, which was the AGPL/enterprise split we worried about in the BM25 memo.

## Recommendation

**Hold.** Keep the current `hnsw`/`ivfflat` allow-list. The backend already enforces the right schema invariants for native pgvector, and Grover's typical deployment corpus sits below the inflection point where DiskANN's throughput and cost story actually materializes.

**Revisit when any of the following is true:**

1. A single deployment's `vfs_objects.embedding` count (not file count — chunk+version count) crosses ~1–5M, or is projected to within a release cycle.
2. A product requirement surfaces for scope-filtered ANN where path-prefix pre-filtering measurably hurts recall or latency (this is the realistic first trigger — filtered DiskANN is hard to replicate with `WHERE` clauses around an HNSW scan).
3. Storage cost for full-precision embeddings becomes meaningful at the deployment we're sizing against.

At that point adoption is structurally cheap: same `vector(N)` column, new index method, extra `CREATE EXTENSION` check, one more branch in `postgres_vector_column_spec` and `_verify_vector_schema`. The groundwork in story 003 (native-only pgvector path, no legacy serialized-embedding fallback at request time) already lines up for it.

## Cross-references

- `src/vfs/backends/postgres.py:67-243` — current native-vector contract and schema verifier.
- `src/vfs/models.py` — `postgres_vector_column_spec`, `resolve_embedding_vector_type`; where a new index method lands.
- `context/stories/003-postgres-filesystem-with-native-vector-search/spec.md:217-249` — native vector search contract this learning builds on.
- `context/learnings/2026-04-20-postgres-native-bm25.md` — sibling decision on BM25 extensions; same pattern of "when does an extension earn its dependency cost?".
- [timescale/pgvectorscale](https://github.com/timescale/pgvectorscale) — upstream, including Filtered DiskANN docs.
- [Tiger Data: pgvector vs Pinecone, 75% less cost](https://www.tigerdata.com/blog/pgvector-is-now-as-fast-as-pinecone-at-75-less-cost) — 50M-vector benchmark underlying the perf claims above.
