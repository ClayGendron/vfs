# 134 — the embedding provider seam and embedding as a streaming step of `reindex`

- **Status:** landed 2026-08-27 (landing note below) — drafted
  2026-08-26 from ADR 054 (all pins) and ADR 051 pin 2 (packed
  float32). Fifth of the glean arc: fills the `embedding` column so
  spec 135 has vectors to rank.
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

## Landing note (2026-08-27)

Every pin of ADR 054 is live; the suite runs offline with no key and no
model download. Landed together with spec 135 and ADR 059 in one
working tree.

**Landed**

- **`vfs.embedding`** (new package): the `EmbeddingProvider` protocol
  (`model_id`, `dimension`, the three caps, `estimate_tokens`,
  `embed_query`, `embed_documents -> Embedded(vectors, tokens)`), the
  `LocalEmbeddingProvider` base (a sync kernel hopped to an executor —
  the loop's default pool unless given one; the query embeds inline),
  `HashEmbeddingProvider(dimension=64)` (the harness's pinned algorithm
  moved into core: the lexical tokenizer's tokens and bigrams, BLAKE2b
  buckets, L2-normalised; `tests/ranking/embedders.py` now imports it
  and its digest pin holds), `Model2VecEmbeddingProvider` behind the
  new `embed-local` extra (the loader resolves `model2vec` on demand so
  importing vfs never loads it — or numpy), `OpenAIEmbeddingProvider`
  (2,048 / 300k / 8,192 caps, `usage.total_tokens`, `dimensions=` for
  the 3-family; duck-typed on `client.embeddings.create`, tested on a
  fake transport) and `LangChainEmbeddingProvider` (the async pair;
  width probed once by a sentinel; identity qualified `provider/model@dim`).
- **Identity on `meta`**: `embedding_model`, `embedding_dimension`
  (`SCHEMA_FORMAT_VERSION` 8 → 9), adopted at first touch, re-read at
  the start of every embed step (a rival may have stamped since). A
  stored width other than a native column's refuses first touch as
  `invalid`; a stored model other than the configured provider's is a
  *stale* space (`host.embedding_stale`) — served lexical-only by glean,
  migrated by `reindex` (every vector cleared, the pair unstamped, the
  first batch written re-stamps).
- **Packed float32** — `VectorType`'s portable path is little-endian
  float32 in a binary column (`vector_codec.pack_vector` /
  `unpack_vector`), unit-normalised on write by the embed step; no
  legacy JSON tolerance (the schema bump is the migration; no
  production rows existed). The native column follows the embedder's
  width automatically (see spec 135's note for the four native types).
- **The embed step** (`embed.py`, orchestrated by `DatabaseStorage._embed_step`
  after the gram/lexical publish and the segment pass, inside the same
  lease): keyset pages of `embedding IS NULL` rows of live, chunked
  entries (`EMBED_PAGE_ROWS = 4,096`), `token_batched` on
  `max_batch_inputs` exactly and `max_batch_tokens` at 5/6 headroom
  (a giant rides alone), over-cap inputs truncated by the provider's
  own estimator and counted, batches embedded with no transaction open
  under `asyncio.Semaphore(embed_concurrency=4)` with a per-request
  `embed_timeout_seconds=120` and one `Retry-After` (seconds or ms,
  duck-typed off the exception's `response.headers`, capped at 60 s)
  honoured by sleeping, one short write per page (`UPDATE … WHERE id =
  :id AND embedding IS NULL`, the meta pair stamped with the first
  vectors landed), the lease's `lost` flag checked between pages. A
  provider failure ends the step with an `unavailable` warning
  (retryable) and leaves the rest NULL for the next run. The reindex
  result carries an `embedding` extra — `model, embedded, cached,
  tokens, requests, truncated, unembedded`.
- **The chunk row is the cache**: `cached_vectors` lends one stored
  vector per `content_hash` (two chunked probes: lowest embedded id
  per hash, then those rows), rows sharing a hash within a page embed
  once, and `chunk_dirty` carries vectors across a re-split onto fresh
  rows with the same hash (`_carried_embeddings`, skipped when the
  space is stale).
- **Surface**: `DatabaseStorage(embedder=, native_embedding=,
  embed_concurrency=, embed_timeout_seconds=)`, `.embedder`;
  `InMemoryStorage` defaults to the hashing provider; every conformance
  leg carries it.
- **Tests**: `tests/embedding/` (37 rows: the protocol on all five
  providers, the helpers, the CPU base's hop, the hash pin and cosine
  honesty, the three adapters on doubles, potion's digest pin when
  cached); `tests/storage/database/test_embed.py` (26 rows: every
  chunk embedded and stamped, no provider → no step, cross-entry dedup,
  a later page borrowing a stored vector, carry-over through a re-split,
  the model-change migration, failure then resume, a failure before any
  vector leaves the space unstamped, the timeout, `Retry-After` once and
  a refusal that keeps refusing, the lost lease between pages, the beat
  through a slow batch, trashed rows skipped, the batcher's laws,
  truncation, the identity refusals); three conformance rows on every
  leg (`test_reindex_embeds_every_chunk_and_reports_the_space`,
  `..._re_embeds_only_the_changed_entry`,
  `..._identical_bodies_share_one_embedding`); `tests/models/test_vector.py`
  rewritten for the packed format.

**Deviations from the spec, all deliberate**

- *The hash provider is the harness's algorithm, not the spec's sketch*
  (`\w+` + `crc32`): spec 131 landed the tokenizer-plus-bigrams BLAKE2b
  form with a digest pin; core adopts that so the pin is one function.
- *No truncated-warning when rows remain without a failure*: the loop
  advances by keyset and stops only on failure or a lost lease, so the
  branch was unreachable; `unembedded` in the extra is nonzero only
  beside a failure record.
- *CPU providers hop to the loop's default executor, not the host's
  offload pool*: the provider has no host; a caller may hand it any
  executor. Recorded as a fork.
- *The pgvector index DDL and extension* (`CREATE EXTENSION IF NOT
  EXISTS vector`, `CREATE INDEX … USING hnsw`) are PostgreSQL-only DDL
  events on the table, within pgvector's 2,000-dimension index cap —
  the scaffold ADR 051 pin 8 anticipated, landed here because the
  native column now follows the embedder.

**Gates** — `scripts/ci.sh 3.13` green at 100 % coverage and the
Postgres, MariaDB, SQL Server 2025 and Oracle legs green; the counts,
the two engine findings and the embed throughput (3,425 chunks/s hash,
3,301 chunks/s potion on a 3,975-file linux sample, write-bound on
sqlite) are in the 135 note's *Measurements* and *Gates*.
