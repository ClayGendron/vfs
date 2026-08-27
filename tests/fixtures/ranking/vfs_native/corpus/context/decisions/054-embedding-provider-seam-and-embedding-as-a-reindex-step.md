# 054. The Embedding Provider Seam: a vfs-Owned Protocol on the Storage, Identity on the Meta Row, and Embedding as a Streaming Step of `reindex`

- **Status:** accepted 2026-08-26 — the provider half of the glean
  decision set, resolved by Clay in session (the R4 review of the
  2026-08-26 research leg). Companions: ADR 051 (where vectors are
  stored and scored), ADR 052 (fusion), ADR 053 (signals). Refines the
  July multimodal memo's space-registry recommendation into its
  single-space first landing.
- **Date:** 2026-08-26
- **Deciders:** Clay Gendron
- **Decided by:** human
- **Context source:** `context/research/2026-08-26-glean-embedding-seam.md`
  and its study (`studies/2026-08-26-glean/embedding-seam.md`), plus the
  floor benchmark in `engine-matrix.md` §4.

## Context

The `chunks.embedding` column exists and nothing fills it; `Vector[dim,
model]` and `VectorType(model_name=…)` are bind-time checks with no
durable record of which model produced a stored row. Clay's
requirements: an embedding provider that is part of Storage, embeds the
query (the router hands the string to the mount) and the chunks,
supports LangChain and OpenAI out of the box with single and batch
calls — and, from the review, **embedding is one of the indexes vfs
builds and must stay synced with the `reindex` call**, taking as long as
it takes provided the event loop is never held.

The research read six provider interfaces, the OpenAI / Voyage / Cohere
/ Gemini limits, and measured three offline providers on 10⁴ real-size
chunks. The binding number: the 10,000-file ETL contract is ~10⁵ chunks
and 5 × 10⁷ tokens — 167 OpenAI requests bound by the 300k-token cap,
which at Tier 1–2 rate limits is a ~50-minute network wait against a
5-minute reindex lease TTL. Cost: $1.00 (text-embedding-3-small) to
$6.50 (3-large) per batch.

## Options considered

- **The protocol**: adopt LangChain's `Embeddings` ABC (carries neither
  model nor dimension; vfs owns fixed-width columns — rejected) vs a
  vfs-owned protocol with adapters (chosen).
- **Where the embed step runs**: a fourth reindex phase in one writer
  transaction (rejected: a 50-minute lock horizon on every engine; the
  lease survives only if the loop yields); outside `reindex` in a
  background worker (rejected by Clay: every index syncs with the one
  call); **a streaming per-batch loop inside `reindex`, after publish**
  (chosen); on the offload thread pool (rejected for hosted providers:
  microseconds of CPU around seconds of socket wait would pin workers
  grep's verify shares) vs on the event loop under a semaphore (chosen),
  with local CPU providers hopping through `call_offloaded`.
- **Identity home**: config only (nothing durable says what the rows
  are — rejected); the July space registry immediately; **a
  provider- and dimension-qualified `embedding_model` plus
  `embedding_dimension` on the existing `meta` row** (chosen — the
  single-space form; the registry is reserved for media spaces and the
  pair migrates into it as row 1).
- **Mismatch**: auto-migrate on first glean (a read verb spending 50
  minutes and $6.50 — rejected) vs refuse the vector leg with a
  `conflict` record and let `reindex` migrate (chosen).
- **Cache**: a text-keyed cache (llama_index's shape, omits the model —
  rejected) vs a separate `(model_id, content_hash)` table vs **the
  chunk row itself** (chosen: identity is mount-wide, `content_hash` is
  per row).
- **Offline providers**: fastembed (3.9 chunks/s, 141 MB — rejected);
  model2vec potion-base-8M (5,212 chunks/s, 31 MB, no torch; a Hub
  download on first use — optional extra); a stdlib hashing embedder
  (9,777 chunks/s, zero dependencies, deterministic — the conformance
  default).
- **Portable vector bytes**: JSON text (today) vs packed float32
  (chosen; ADR 051 pin 2).

## Decision

1. **A vfs-owned `EmbeddingProvider` protocol**: `model_id` (provider-
   and dimension-qualified, e.g. `openai/text-embedding-3-small@1536`),
   `dimension` (required), `max_input_tokens`, `max_batch_inputs`,
   `max_batch_tokens`, `estimate_tokens(text)`, `async embed_query(text)`
   (applies the model's query prefix) and `async embed_documents(texts)
   -> Embedded(vectors, tokens)` (applies the document prefix; embeds
   one batch within the caps). The provider declares caps and prefixes
   and embeds one batch; it does not batch across requests, cache, or
   count cost. Vectors cross the seam as `list[list[float]]`; numpy
   never does.
2. **Injected on the Storage** — `DatabaseStorage(url=…, embedder=…)`.
   The router is unchanged: each mount embeds the query with its own
   provider inside its `glean`, under the fan-out deadline, memoised in a
   small LRU keyed `(model_id, query)`; a mount with no provider serves
   the lexical leg with an absent-vector record.
3. **Adapters**: `OpenAIEmbeddingProvider(client, model, dimensions=None)`
   (caps 2,048 inputs / 300k tokens / 8,192 per input; `usage.total_tokens`
   reported) and `LangChainEmbeddingProvider(embeddings, *, model_id,
   dimension=None)` (dimension probed once by a sentinel when not given)
   on the existing extras; `HashEmbeddingProvider(dimension)` in core as
   the conformance-suite provider and the in-memory backend's default;
   `Model2VecEmbeddingProvider` as the optional `embed-local` extra;
   fastembed not adopted. CPU providers' `embed_documents` hops through
   `call_offloaded`.
4. **Identity on the `meta` row**: `embedding_model` and
   `embedding_dimension`, stamped when the first embedding is written,
   verified at `ensure_ready` like `schema_format_version`. A dimension
   mismatch on a native column refuses at `ensure_ready` (`invalid`);
   a model mismatch refuses the **vector leg** with a `conflict`-kind
   record and serves lexical-only; `reindex` is the migration — a stale
   identity re-dirties every chunk's embedding (the `chunk_generation`
   law), re-embeds, re-stamps.
5. **The chunk row is the cache.** `chunk_dirty` carries existing
   embeddings onto fresh rows with the same `content_hash` before its
   delete/insert; each batch dedups against embedded rows sharing a
   `content_hash` before calling the provider; no cache table.
6. **Embedding is a step of `reindex`**, after `publish_epoch`, inside
   the same lease, never a phase-transaction: select one budget's worth
   of `(id, content)` where `embedding IS NULL` (short read, token- and
   input-bounded with headroom — plan ~250k of 300k) → embed with no
   transaction open → `UPDATE … WHERE id = :id AND embedding IS NULL`
   (short write; a rival's identical write is a no-op) → check the lease
   → repeat. Hosted providers run on the event loop under
   `asyncio.Semaphore(k≈4–8)` with per-request timeouts and
   `Retry-After` honoured by sleeping the coroutine; a crash loses one
   batch and the next `reindex` resumes. The gram and lexical publish
   never waits behind it. The `reindex` result reports `embedded, cached,
   tokens, requests, unembedded` (warning severity when `unembedded > 0`),
   and glean's envelope names the lexical-only count until it finishes.
7. **Storage owns batching** — a `token_batched(rows, provider)` sibling
   of `byte_chunked` cutting on `max_batch_inputs`, `max_batch_tokens`
   with headroom, and the engine's bind budget for the write-back;
   `chars // 4` as the default estimator; over-cap inputs truncated with
   a record where the API offers truncation.
8. **Vectors are stored as packed little-endian float32** on the portable
   path, normalised on write when the metric is cosine; native types
   where modelled (pgvector; Oracle in-tree `VECTOR`; small
   `UserDefinedType`s for SQL Server and MariaDB); never MySQL's `VECTOR`.

## Consequences

- **Easier:** one `reindex` leaves chunks, grams, lexical postings,
  signals and vectors at the same generation; the suite runs offline
  with no key and no model download; a model swap is a re-embed by the
  verb that owns regeneration; unchanged chunk text is never re-embedded.
- **Harder:** a 10k-file reindex against a hosted provider is tens of
  minutes at low rate-limit tiers, by design; the lease TTL now depends
  on the embed loop yielding (it awaits a socket, or hops to the
  executor); two small vector `UserDefinedType`s to maintain.
- **Committed to:** no embedding on any read path; no auto-migration;
  identity durable in the database, not in configuration; the space
  registry reserved for media, with the meta-row pair as its first row.

Evidence: `embedding-seam.md` (the interface table; the ETL arithmetic;
the throughput table; the field's caching anti-pattern);
`engine-matrix.md` §4 (JSON vs packed float32 at 10k/50k on MySQL);
`unconstrained-design.md` §12.2 (parse-time ratio). Docs: OpenAI
embeddings, rate limits and Batch API; Voyage, Cohere, Gemini; pgai
#728 and LangChain #31227 (token-count drift).
