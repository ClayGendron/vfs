# glean: the embedding provider seam in Storage

- **Status**: research memo — design input for the embedding-provider
  ADR (a public Storage surface). One of five memos from the 2026-08-26
  glean research leg (brief:
  [2026-08-26-glean-brief.md](2026-08-26-glean-brief.md)). Companions:
  [glean in the engine](2026-08-26-glean-in-the-engine.md) (where the
  vectors are stored and scored),
  [fusion and cross-mount merge](2026-08-26-glean-fusion-and-cross-mount-merge.md),
  [ranking signals and the ranker API](2026-08-26-glean-ranking-signals-and-ranker-api.md),
  [previews and the result shape](2026-08-26-glean-previews-and-result-shape.md).
  Commits us to nothing.
- **Date**: 2026-08-26
- **Owner**: Clay Gendron
- **Question**: The router hands `glean`'s query string to each mount;
  the mount must embed it with *its own* model, and the reindex pipeline
  must fill the `chunks.embedding` column nothing fills today. What must
  the provider seam be so that LangChain and OpenAI embedders work out
  of the box with single and batch embedding; a 10,000-file reindex
  (~10⁵ chunks) stays bounded in requests, time and money; the model
  identity is durable and a mismatch refuses honestly; a re-split that
  yields identical chunk text never re-embeds; and the conformance suite
  runs offline with no key and no heavy dependency?
- **Evidence gathered**: the embedding-seam study
  ([studies/2026-08-26-glean/embedding-seam.md](studies/2026-08-26-glean/embedding-seam.md)):
  six provider interfaces read in refreshed checkouts (LangChain,
  llama_index, haystack, LanceDB, mem0, cognee), the OpenAI / Voyage /
  Cohere / Gemini API limits from vendor docs, and executed throughput
  measurements of three offline providers on 10⁴ real-size chunks;
  the engine-matrix study's client-floor benchmark
  ([engine-matrix.md §4](studies/2026-08-26-glean/engine-matrix.md));
  the independent design's serialisation experiment
  ([unconstrained-design.md §12.2](studies/2026-08-26-glean/unconstrained-design.md)).
- **Headline**: **Embedding is a step of `reindex` — every index stays
  synced with the one call (Clay, 2026-08-26) — but it cannot take the
  shape of the existing phases.** The ETL contract (10k files → ~10⁵
  chunks → 5×10⁷ tokens) is 167 OpenAI requests bound by the
  300k-tokens-per-request cap, which at Tier 1–2 rate limits is a
  **50-minute network wait** against a 5-minute reindex lease TTL and a
  writer-transaction lock horizon; inside the verb it runs as a
  streaming per-batch loop *after* publish, on the event loop under a
  small semaphore (hosted
  providers are I/O-bound; TPM binds long before latency), with local
  CPU providers hopping through `call_offloaded`. LangChain's
  `Embeddings` ABC carries neither model nor dimension, so vfs needs its
  own protocol and the LangChain adapter is *told* its identity; the
  identity is stamped on the existing `meta` row and a mismatch refuses
  the vector leg (`reindex` migrates). The chunk row already is the
  `(model, content_hash)` cache — one leak to plug on re-split. Offline:
  a stdlib hashing embedder (9,777 chunks/s, zero dependencies) is the
  conformance default; model2vec potion-base-8M (5,212 chunks/s, 31 MB,
  no torch) is the optional real-semantics extra; fastembed is rejected
  (3.9 chunks/s, 141 MB). Vectors travel as packed float32, never JSON
  text — 14× faster and 5× smaller at the floor, and ~1,200× faster to
  parse.

---

## 1. What exists

`Vector[dim, model]` subclasses validate length; `VectorType(dimension,
model_name, postgres_native)` refuses a bind whose `Vector` carries a
*different* model name but accepts a bare `list[float]` with none
(`src/vfs/models/vector.py:210–226`); `NativeEmbeddingConfig` shapes the
pgvector column at table-build time and is the only place a model name
is configured — on the Postgres-native path only. The `chunks` table
has one `embedding` column (JSON text on the portable path, pgvector
`vector(n)` natively); staleness is `embedding IS NULL`; chunk rows
carry `content_hash = sha256(content)`. Nothing durable says which model
produced a stored row, and nothing calls a model.

## 2. Provider interfaces in the field → what the protocol must carry

All six libraries converge on document-batch + query-single. What each
adds, and what it means for vfs:

| Requirement | Evidence | Consequence |
|---|---|---|
| **Query/document asymmetry is the provider's** | E5 `query:`/`passage:`, BGE's query-side instruction, Voyage `input_type`, Cohere `search_query`/`search_document`, sentence-transformers `encode_query`/`encode_document` | two methods (`embed_query`, `embed_documents`), prefixes applied inside the adapter — a single `embed(texts)` cannot serve E5/BGE |
| **Dimension is required** | LanceDB `ndims()` and cognee `get_vector_size()` require it because they own a fixed-width column; LangChain and llama_index (pure adapters) do not | vfs owns fixed-width columns → `dimension` is a required property |
| **Identity is a string nobody persists** — except LanceDB | LanceDB serialises the embedding function's config into table metadata; LangChain's base has no model or dimension at all | the seam cannot adopt LangChain's ABC; its adapter is told `model_id` and `dimension`; identity is persisted (§4) |
| **Async-native** | llama_index and cognee async; LangChain defaults to an executor hop; LanceDB/mem0 sync | the protocol is async; sync/CPU providers are wrapped explicitly |
| **Batching lives in the library, not the provider** | llama_index `embed_batch_size` loop, LangChain-OpenAI `chunk_size` + tiktoken split, haystack `batch_size=32`; only LanceDB's Voyage function batches by tokens | storage owns the batch splitter (it already owns `chunked`/`byte_chunked`/`membership_budget`); the provider declares caps and embeds one batch |
| **Caching keyed on raw text is the anti-pattern** | llama_index's `embeddings_cache` omits the model — a model swap serves stale vectors | the cache key is `(model, content_hash)`, which the chunk row already holds |
| **Retries stay in the client** | openai-python retries 2× honouring `Retry-After`; LanceDB wraps in exponential backoff | per-request retries in the adapter; cross-batch policy in storage |

## 3. Batch physics and the ETL contract

OpenAI `/v1/embeddings`: **8,192 tokens per input**, **2,048 inputs per
request**, **300,000 tokens summed per request**; `dimensions=` is
Matryoshka truncation (3-large at 256 still beats ada-002); 3-small
$0.02/M tokens, 3-large $0.13/M; rate limits Free 40k TPM, Tier 1–2
1M TPM, Tier 3–4 5M, Tier 5 10M; the Batch API is half price with a
24 h window but its *enqueued-token* cap is 3M at Tier 1. Voyage:
≤ 1,000 inputs and 320K tokens (voyage-4) per request, 8M TPM at
Tier 1. Cohere: ≤ 96 texts per call, 2,000 inputs/min. Gemini: per-
request caps unpublished; gemini-embedding-001's 2,048-token input cap
is within one CJK chunk of vfs's 2,048-character chunk ceiling.

vfs's splitter caps a chunk at 2,048 *characters*; measured ≈ 464 tokens
per 2,322-char chunk, so ~500 tokens is the planning figure and the
10,000-file batch is **5 × 10⁷ tokens**:

| Provider / model | Requests (binding cap) | Wall at documented rate | List cost |
|---|---|---|---|
| OpenAI 3-small | **167** (300k tokens/req → 600 chunks/req; the input cap would allow 49) | Free ≈ 21 h; **Tier 1–2 ≈ 50 min**; Tier 3–4 ≈ 10 min; Tier 5 ≈ 5 min | **$1.00** (batch $0.50) |
| OpenAI 3-large | 167 | same | **$6.50** (batch $3.25); 3,072-d ≈ 1.2 GB of float32 per 10⁵ chunks — `dimensions=1024` cuts storage 3× free |
| OpenAI Batch API | 2 batches | Tier 1's 3M enqueued cap → 17 sequential batches; usable from Tier 3 | half price |
| Voyage voyage-4 | 157 | ≈ 6 min | $3.00 (free under the 200M allowance) |
| Cohere embed-v4 | **1,042** (96/req) | ≈ 50 min (inputs/min binds) | — |

Three consequences the seam must encode: **token caps bind before
input-count caps** at vfs's chunk size, so the batch splitter meters
tokens with headroom (plan ~250k of 300k — the tiktoken-vs-server drift
in pgai #728 and LangChain #31227 says the headroom is needed); **TPM is
the wall, not latency or RPM** — concurrency above ~4–8 in-flight
requests buys nothing but 429s; **cost is small and countable** — the
OpenAI response carries `usage.total_tokens`, so the seam reports spent
tokens exactly.

## 4. Identity, mismatch, migration

**Where the identity lives.** Stamp `embedding_model` (provider- and
dimension-qualified: `openai/text-embedding-3-small@1536`,
`model2vec/potion-base-8M@256` — `dimensions=` truncation makes one
model name several incompatible spaces) and `embedding_dimension` on
the existing single-row `meta` table, which already stamps
`schema_format_version` (verified at first touch) and `mount_identity`.
This is the single-space degenerate form of the July memo's space
registry; the registry (`spaces(space_id, model_id, dimension, …)` plus
a `(chunk_id, space_id, vector)` side table) stays reserved and the
meta-row pair migrates into it as row 1 when media spaces arrive.
LanceDB's persisted function config and HippoRAG's `index_manifest.json`
(which raises `StateConsistencyError` on a wrong-model query) are the
field's two versions of this.

**Two mismatches, two verdicts.**

- *Dimension mismatch on a native column* (pgvector `vector(1536)` vs a
  3,072-d provider): the column cannot hold the vectors. Refuse at
  `ensure_ready` with an `invalid` result naming both — no verb can
  succeed; the fix is DDL.
- *Model mismatch with a compatible column* (JSON/binary column, or same
  dimension different model — cosine between them is noise): `glean`
  must not silently rank noise. Refuse the **vector leg** with a
  `conflict`-kind record naming stored vs configured model and serve the
  lexical leg alone (the freshness posture applied to identity).
  `reindex` is the migration: a stale identity marks every chunk's
  embedding stale — the same law as `chunk_generation` in `chunk_dirty`,
  where a generation change re-dirties every entry — nulls them under
  the new identity, re-embeds, and re-stamps `meta`. Model swap =
  re-embed the mount, by the verb that owns regeneration, never by a
  write and never by a read (a read verb must not spend 50 minutes and
  $6.50).

## 5. The cache: the chunk row already is one

Two existing laws prevent most re-embedding: the fingerprint-skip law
leaves an entry's chunk rows untouched when its body hash equals
`chunk_source_hash`, and a rename rewrites zero chunk rows. The one
leak: a real re-split in `chunk_dirty` deletes the entry's rows and
inserts fresh ones (`indexing.py:281–284`), dropping embeddings even
where the new chunk text is byte-identical to an old chunk's.

- **Tier 1, no new table** (recommended): before the delete, read
  `(content_hash, embedding)` for the resplit ids where `embedding IS
  NOT NULL` (chunked by the membership budget) and carry each vector
  onto the fresh row with the same hash at insert. With the meta-row
  identity, the row *is* the `(model, content_hash)` cache.
- **Tier 2, cross-entry dedup**: before calling the provider for an
  unembedded batch, look up any embedded row sharing a `content_hash`
  (licence headers, vendored copies, boilerplate) — one `IN`-list probe
  per batch.
- **Tier 3, a separate `embedding_cache(model_id, content_hash,
  vector)`** that survives deletion and trash sweeps: the only version
  that needs schema; a fork, not a requirement.

## 6. Where the embed step runs

**A step of the `reindex` verb — never a phase-transaction.** Clay's
requirement (2026-08-26): vector embeddings are one of the indexes vfs
builds, so they stay synced with the `reindex` call like chunks, grams,
lexical postings and signals — one `reindex` leaves every index at the
same generation, and it is acceptable for the call to take a long time
provided the event loop is never held. The step therefore runs inside
the verb, under the same lease, after `publish_epoch`; what it must not
be is the *shape* of the existing phases. Reindex's phases each run in one writer transaction
with a beat task pulsing the lease every 60 s against a 5-minute TTL. A
50-minute embed inside that shape fails three ways: a writer transaction
held open for 50 minutes is a lock horizon on every engine (the
MySQL-family next-key locks `chunk_dirty` already fights; Postgres
`idle_in_transaction_session_timeout`; Oracle undo retention); the lease
survives only because the beat is an independent task — which works if
the embed step *awaits* on the loop and fails if it blocks it; and a
rival claiming through after a lost beat must find the half-done embed
harmless, which holds only if each written batch is already committed
and idempotent.

**So: a streaming batch loop after `publish_epoch`, inside the verb.**
Select one
budget's worth of `(id, content)` where `embedding IS NULL` (short read
transaction, ordered by id, bounded by tokens and inputs) → embed with no
transaction open → write back with `UPDATE … WHERE id = :id AND
embedding IS NULL` (short writer transaction; a rival's identical write
is a no-op) → check `lost` → repeat. After publish rather than before,
because the gram index is grep's tier and must not wait 50 minutes
behind the vector tier; the vector tier's staleness is already the
"unembedded count as a warning record" posture. The independent design
reached the same shape (per-batch committed, resumable, one batch lost
on crash).

**On the event loop, not the offload pool.** `offload.py` exists because
verify and split are *CPU* inside coroutines; a hosted embed call is
microseconds of CPU around hundreds of milliseconds of socket wait. On
the thread pool that wait pins a worker doing nothing — with
`OFFLOAD_WORKERS = cores`, ten in-flight requests would monopolise the
pool grep's verify shares. On the loop, httpx parks the wait in the
selector for free; bounded concurrency is `asyncio.Semaphore(k)` with
k ≈ 4–8; 429s honour `Retry-After` by sleeping the coroutine. The
offload pool's laws (absolute deadline crossing, one in flight,
cancellation is abandonment) are CPU laws; the network step needs a
per-request timeout and cancellation that closes the socket. The
exception proves the rule: a **local** provider (model2vec, the hash
embedder at 10⁵ chunks) *is* CPU-bound and hops through `call_offloaded`
inside its adapter, the way `_assess_and_split` does.

**How the router hands the query over: unchanged.** `VFS.glean` fans
`query` out opaquely; each mount's backend calls its own provider's
`embed_query` inside its `glean`, under the fan-out deadline, so two
mounts with two models each embed once with the right model, and a
mount with no provider serves the lexical leg with an absent-vector
record. A small LRU keyed `(model_id, query)` memoises repeat queries
(the 2026-08-17 memo measured an 8.2 % exact-repeat rate in agent
searches).

## 7. Offline and test providers, measured

Apple M1 Pro, CPython 3.13.11, 10,000 synthetic chunks of ~500 tokens,
throwaway venvs:

| Provider | Beyond vfs's own numpy | Model on disk | 10⁴ chunks, 1 thread | Throughput |
|---|---|---|---|---|
| **hash embedder (stdlib)**, dim 256 | 0 | 0 | 1.02 s | **9,777 chunks/s** |
| hash embedder, dim 1536 | 0 | 0 | 1.68 s | 5,955 chunks/s |
| **model2vec `potion-base-8M`** (256-d; the card's "384" is the 32M sibling) | ~30 MB (tokenizers, safetensors, hf_hub, joblib…); **no torch** | 31 MB | 1.92 s | **5,212 chunks/s** (6,136 multiprocess) |
| fastembed `bge-small-en-v1.5` int8 ONNX | ~120 MB (onnxruntime 75 MB, PIL 13 MB…) | 64 MB | 200 chunks in 51 s | 3.9 chunks/s → ~7 h per 10⁵ |

The hash embedder — tokenize `\w+`, `crc32` each token into a signed
bucket, L2-normalise — is deterministic across processes, dimension-
parameterised, zero download, and *semantically honest enough* for a
conformance suite: identical text → identical vectors, shared vocabulary
→ positive cosine, disjoint → ~0. It cannot rank by meaning and must not
pretend to; it exists to pin batching, budgets, cache hits, identity
refusal, lease interaction, tier honesty and tie-break determinism on
every engine leg (LangChain ships the same idea as
`DeterministicFakeEmbedding`). model2vec embeds 10⁵ chunks in ~20 s
single-threaded — faster than the split step — but its first use
downloads from the Hub, which the suite must never do; it is the
"works offline with real semantics" tier for a laptop, exercised by
tests only when the package and a cached model are present.

## 8. Vector bytes on the wire and at rest

Two studies measured the same thing independently. At the client floor
on MySQL 9.7 (384-d, 50k vectors, best of 3): JSON text 4.69 s
(90 % `json.loads`) vs packed float32 0.33 s — **14× faster end to
end, 5.2× smaller** (7,975 vs 1,536 bytes per vector; Python's
`repr(float)` emits ~20 bytes per component). The independent design's
parse-only measurement at 768-d: JSON 1,972 ms vs packed 1.6 ms per
10k — ~1,200×. Packed little-endian float32 in a `LargeBinary` is
therefore the portable column (the floor's precondition, not an
optimisation), with native types where SQLAlchemy or a small
`UserDefinedType` models them (pgvector, Oracle in-tree `VECTOR`, SQL
Server `VECTOR(n)` as JSON over pyodbc, MariaDB `VECTOR(n)`) and never
MySQL's `VECTOR` (pymysql cannot decode the wire type). `Embedded.vectors`
crosses the seam as `list[list[float]]`; numpy never does. Normalise on
write when the metric is cosine so the floor's dot product is the
cosine and native tiers use the cheapest operator.

## 9. The protocol, sketched

```python
class Embedded(NamedTuple):
    vectors: list[list[float]]     # portable floats; numpy never crosses the seam
    tokens: int                    # provider-reported when available, else estimated


@runtime_checkable
class EmbeddingProvider(Protocol):
    model_id: str                  # "openai/text-embedding-3-small@1536"
    dimension: int                 # required — vfs owns fixed-width columns
    max_input_tokens: int | None   # 8192 OpenAI, 2048 gemini-001; None = unbounded
    max_batch_inputs: int          # 2048 / 1000 / 96 / 1
    max_batch_tokens: int | None   # 300k / 320k / None

    def estimate_tokens(self, text: str) -> int: ...                      # chars // 4 default; tiktoken if the adapter has it
    async def embed_query(self, text: str) -> list[float]: ...            # applies the model's query prefix
    async def embed_documents(self, texts: Sequence[str]) -> Embedded: ...  # applies the document prefix; one batch ≤ caps
```

The provider declares caps and prefixes and embeds *one* batch; it does
not batch across requests, cache, or count cost. Storage owns the batch
splitter (a `token_batched(rows, provider)` sibling of `byte_chunked`
that cuts on `max_batch_inputs`, `max_batch_tokens` with headroom, and
the engine's bind budget for the write-back), the carry-over and dedup,
the streaming loop with lease checks, the semaphore, per-request
timeouts under the fan-out deadline, and the envelope's records
(`embedded=N, cached=M, tokens=T, requests=R, unembedded=U`, warning
severity when U > 0). Adapters: `OpenAIEmbeddingProvider(client, model,
dimensions=None)`; `LangChainEmbeddingProvider(embeddings, *, model_id,
dimension=None)` (dimension probed once by embedding a sentinel when not
given); `Model2VecEmbeddingProvider(StaticModel)` (extra) and
`HashEmbeddingProvider(dimension)` (core), both CPU providers whose
`embed_documents` hops through `call_offloaded`.

## 10. Recommendation for the ADR

1. **An `EmbeddingProvider` protocol owned by vfs** (identity, dimension,
   caps, `embed_query`/`embed_documents`), injected on the Storage;
   OpenAI and LangChain adapters on the existing extras; the hash
   embedder in core as the conformance default and the in-memory
   backend's default; model2vec as an optional extra; fastembed not
   adopted.
2. **Identity on the `meta` row**, provider- and dimension-qualified;
   dimension mismatch refuses at `ensure_ready`; model mismatch refuses
   the vector leg with a `conflict` record and `reindex` migrates.
3. **The chunk row is the cache**: carry embeddings across re-splits by
   `content_hash`; cross-entry dedup per batch; no cache table.
4. **Embedding is a step of `reindex`** (Clay, 2026-08-26 — every
   index stays synced with the one call), run as a streaming per-batch
   loop after publish, on the event loop under `Semaphore(k≈4–8)` for
   hosted providers and through `call_offloaded` for CPU providers;
   per-batch commits so a crash loses one batch and the next `reindex`
   resumes; storage-owned token batching with headroom; exact token
   accounting reported on the `reindex` result.
5. **Packed float32 as the portable vector column**; native types where
   modelled; never MySQL's `VECTOR`.
6. The router changes nothing: each mount embeds the query with its own
   provider; no provider means lexical-only with a record.

## 11. Forks the ADR must close

1. Identity home — meta-row pair now (recommended) vs the registry
   table immediately vs config-only (rejected).
2. Mismatch policy — refuse the vector leg and let `reindex` migrate
   (recommended) vs auto-migrate on first glean (rejected).
3. Cache tier — in-row carry-over + dedup (recommended) vs a separate
   table that survives deletion.
4. Embed step shape — settled by Clay 2026-08-26: inside `reindex`,
   streaming per-batch after publish; a single phase transaction is
   rejected (lock horizon, lease TTL).
5. Concurrency — fixed `Semaphore(k)` first vs header-driven adaptation
   from `x-ratelimit-remaining-tokens`.
6. Test provider — hash in core + model2vec extra (recommended) vs
   model2vec default (a Hub download in the suite) vs fastembed.
7. Batch-splitter owner — storage (recommended) vs provider.
8. Token estimation — `chars // 4` with headroom (recommended) vs an
   optional tiktoken exact counter.
9. Truncation — truncate with a record where the API offers it
   (recommended) vs refuse over-cap inputs.
10. OpenAI Batch API as a half-price `reindex` mode — deferred (Tier 3+).
11. Whether the router also accepts a default provider pushed to every
    mount lacking one (raised by the independent design).

## Sources

Study (this repo): `studies/2026-08-26-glean/embedding-seam.md` with
`embedding-seam/{corpus,hash_embed,bench,bench_fe2}.py` and
`results.md`; `engine-matrix.md` §4 (`bench_floor_mysql.py`);
`unconstrained-design.md` §12.2.

Checkouts (refreshed 2026-08-26, read-only): langchain @ 43bed06205
(`libs/core/langchain_core/embeddings/`), llama_index @ d802122,
haystack @ 71b0ee6, lancedb @ 2fbf6d6 (`embeddings/{base,registry}.py`),
mem0 @ 39bc023, cognee @ 690c0ec02, model2vec @ 280b341, fastembed @
c48247f, openai-python @ 555ac48 (`resources/embeddings.py`,
`_base_client.py`); letta @ 4511fa0bc carries no source and was omitted.

Docs: OpenAI embeddings guide and API reference, rate limits, Batch API
(https://developers.openai.com/api/docs/guides/embeddings,
https://developers.openai.com/api/docs/guides/rate-limits,
https://developers.openai.com/api/docs/guides/batch); pgai #728 and
LangChain #31227 (token-count drift); Voyage
(https://docs.voyageai.com/reference/embeddings-api); Cohere
(https://docs.cohere.com/reference/embed); Gemini
(https://ai.google.dev/gemini-api/docs/embeddings); Pinecone's E5 guide
and the sbert prompts docs; model2vec potion-base-8M card
(https://huggingface.co/minishlab/potion-base-8M).
