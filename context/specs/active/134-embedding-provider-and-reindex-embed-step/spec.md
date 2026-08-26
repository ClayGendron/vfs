# 134 — the embedding provider seam and embedding as a streaming step of `reindex`

- **Status:** ready — drafted 2026-08-26 from ADR 054 (all pins) and
  ADR 051 pin 2 (packed float32). Fifth of the glean arc: fills the
  `embedding` column so spec 135 has vectors to rank.
- **Born from:** ADR 054; memo
  `../../../research/2026-08-26-glean-embedding-seam.md`; study
  `../../../research/studies/2026-08-26-glean/embedding-seam.md`.
- **Date:** 2026-08-26
- **Owner:** Clay Gendron
- **Kind:** new public protocol and adapters (`src/vfs/embedding/`), a
  `meta`-row identity, a new `reindex` step, a portable vector-column
  format change; schema format bump.
- **Depends on:** the reindex lease and beat (`indexing.py`,
  `backend._held_reindex_lease`), `chunk_dirty` (the carry-over hook),
  `ByteBatcher`/`chunked` budgets, `offload.call_offloaded` (CPU
  providers), `VectorType` (`models/vector.py`).
- **Relates to:** spec 135 (reads the vectors; adds the SQL Server and
  MariaDB native types), spec 131 (the hash embedder becomes the
  harness's floor provider from here).

## Intent

Nothing fills `chunks.embedding` today. Embedding is one of the indexes
vfs builds, so it is a step of `reindex` — synced with chunks, grams,
lexical postings and signals under one call — but it cannot take the
shape of the existing phases: the 10k-file contract is ~167 hosted
requests and tens of minutes at low rate-limit tiers, and a writer
transaction cannot span that. The event loop is never held.

## Decided semantics

1. **Protocol** (`EmbeddingProvider`, `@runtime_checkable`): `model_id`
   (provider- and dimension-qualified), `dimension`, `max_input_tokens
   | None`, `max_batch_inputs`, `max_batch_tokens | None`,
   `estimate_tokens(text)`, `async embed_query(text) -> list[float]`,
   `async embed_documents(texts) -> Embedded(vectors, tokens)`. The
   provider embeds one batch within its caps and applies its own
   query/document prefixes; it never batches across requests, caches or
   counts cost. Vectors cross as `list[list[float]]`.
2. **Adapters**: `OpenAIEmbeddingProvider(client: AsyncOpenAI, model,
   dimensions=None)` (caps 2,048 / 300k / 8,192; `usage.total_tokens`
   reported) and `LangChainEmbeddingProvider(embeddings, *, model_id,
   dimension=None)` (dimension probed once by a sentinel) on the
   existing `openai` / `langchain` extras; `HashEmbeddingProvider(dimension=64)`
   in core (`\w+` tokens, `crc32` signed buckets, L2-normalised;
   deterministic across processes) as the conformance default and the
   in-memory backend's default; `Model2VecEmbeddingProvider` behind a new
   `embed-local` extra. CPU providers' `embed_documents` hops through
   `call_offloaded`.
3. **Injection**: `DatabaseStorage(url=…, embedder=…)`. No provider
   means lexical-only glean with the trait `glean_signals="lexical"`
   and an absent-vector record on each answer.
4. **Identity on `meta`**: `embedding_model`, `embedding_dimension`,
   stamped when the first embedding is written, verified at
   `ensure_ready`. Dimension mismatch on a native column → `invalid` at
   `ensure_ready`; model mismatch → the vector leg refuses with a
   `conflict` record (lexical-only served) and `reindex` migrates: the
   stale identity re-dirties every embedding (NULL under the new
   identity), re-embeds, re-stamps. Never auto-migrate on a read.
5. **The chunk row is the cache**: `chunk_dirty` reads `(content_hash,
   embedding)` for the rows it will delete (chunked) and carries each
   vector onto the fresh row with the same hash; each embed batch first
   dedups against embedded rows sharing a `content_hash`. No cache
   table.
6. **The step** — after `publish_epoch`, inside the held lease: select
   one budget's worth of `(id, content)` where `embedding IS NULL`
   ordered by id (short read; a `token_batched(rows, provider)` sibling
   of `byte_chunked` cuts on `max_batch_inputs`, `max_batch_tokens` with
   headroom — plan ~5/6 of the cap — and the write-back's bind budget)
   → embed with no transaction open → `UPDATE … SET embedding = :v
   WHERE id = :id AND embedding IS NULL` (short write) → check `lost` →
   repeat. Hosted providers run on the event loop under
   `asyncio.Semaphore(k)` (k = 4 default; a constructor knob), with a
   per-request timeout and `Retry-After` honoured by sleeping; a
   provider exception ends the step with a classified warning, leaving
   the rest `NULL` for the next run. The `reindex` result reports
   `embedded / cached / tokens / requests / unembedded` (warning severity
   when `unembedded > 0`).
7. **Portable vector bytes**: `VectorType`'s portable path becomes
   packed little-endian float32 in `LargeBinary`, normalised on write
   when the metric is cosine; the pgvector-native path is unchanged
   (`NativeEmbeddingConfig`); MySQL never uses its `VECTOR` type. A
   one-way migration reads any legacy JSON rows and re-packs them at
   reindex (or simply NULLs them under the new identity — decide in
   plan.md; no production rows exist).
8. **Format bump**: `SCHEMA_FORMAT_VERSION` 7 → 8 (meta columns, column
   type); `chunk_generation`-style re-dirty on identity change.

## Scope

In: the protocol and four providers, injection, identity and
mismatch, cache carry-over and dedup, the step, the batcher, the byte
format, tests (offline only; the OpenAI adapter tested against a fake
transport). Out: the SQL Server/MariaDB native types and the vector leg
(135), the space registry (media), the OpenAI Batch API mode
(deferred), header-driven rate adaptation (fork 5).

## Slices

- **A — protocol and providers**: `embedding/` package, the hash
  provider, the model2vec extra, the OpenAI and LangChain adapters with
  fake-transport tests; `token_batched`.
- **B — identity and bytes**: meta columns, `ensure_ready` checks, the
  mismatch refusals, packed float32 in `VectorType`, schema bump.
- **C — the reindex step**: the streaming loop, semaphore, lease
  interaction (a beat keeps ticking through a slow batch — pinned with a
  slow fake provider), carry-over in `chunk_dirty`, per-batch dedup, the
  result records; conformance rows on every engine leg with the hash
  provider.

## Landing criteria

- `scripts/ci.sh 3.13` green with no network and no model download; the
  model2vec adapter's tests skip when the package or cached model is
  absent.
- Engine legs green: a reindex with the hash provider embeds every
  chunk on all five real engines; a mismatch refuses as specified.
- Ledger rows: the beat survives a slow batch (lease not lost); a crash
  mid-step loses at most one batch (resume pin); identical chunk text is
  never re-embedded (cache pin).
- Landing note records embed throughput for the hash and model2vec
  providers on the linux store.
