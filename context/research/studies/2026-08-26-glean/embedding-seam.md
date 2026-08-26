# The embedding provider seam in Storage

- **Study for**: `../../2026-08-26-glean-brief.md` — question 11 ("The
  embedding seam in Storage"), plus gap 3 (embedding identity and
  migration) and gap 4 (embedding at 10k-batch scale).
- **Date**: 2026-08-26
- **Sources** (reference clones under `~/Git/Repos`, read-only, refreshed
  2026-08-26; public docs by URL in *Sources* at the end):
  langchain @ 43bed06205 (`libs/core/langchain_core/embeddings/`,
  `libs/partners/openai/langchain_openai/embeddings/base.py`);
  llama_index @ d802122 (`llama-index-core/llama_index/core/base/embeddings/base.py`,
  `llama-index-integrations/embeddings/llama-index-embeddings-openai/.../base.py`,
  `.../llama-index-embeddings-huggingface/.../utils.py`);
  haystack @ 71b0ee6 (`haystack/components/embedders/`);
  lancedb @ 2fbf6d6 (`python/python/lancedb/embeddings/`);
  mem0 @ 39bc023 (`mem0/embeddings/`, `mem0/configs/embeddings/base.py`);
  cognee @ 690c0ec02 (`cognee/infrastructure/databases/vector/embeddings/`);
  model2vec @ 280b341 (`model2vec/model.py`, `pyproject.toml`, `LICENSE`);
  fastembed @ c48247f (`pyproject.toml`, `LICENSE`);
  openai-python @ 555ac48 (`src/openai/resources/embeddings.py`,
  `src/openai/_constants.py`, `src/openai/_base_client.py`);
  letta @ 4511fa0bc — the refreshed clone carries **no Python source**
  (README, policies, and CITATION only), so letta's embedder config could
  not be studied from the tree and is omitted rather than reconstructed.
  vfs ground truth: `src/vfs/models/vector.py`, `src/vfs/models/rows.py`,
  `src/vfs/models/chunk.py`, `src/vfs/models/chunking.py`,
  `src/vfs/storage/backends/database/indexing.py`, `.../backend.py`,
  `.../offload.py`, `.../engine.py`, `src/vfs/base.py`, and the July memo
  `../../2026-07-25-multimodal-storage-and-search.md` §4.
- **Scripts and raw numbers**: `embedding-seam/` beside this file
  (`corpus.py`, `hash_embed.py`, `bench.py`, `bench_fe2.py`, `results.md`).

## Question

What must the embedding provider seam inside `Storage` be so that: the
router hands `glean`'s query string to each mount and the mount embeds
it with *its own* model; the reindex pipeline fills the `chunks.embedding`
column that today nothing fills; LangChain and OpenAI embedders work out
of the box; a 10,000-file reindex (~10⁵ chunks) stays bounded in requests,
time, and money; the model identity is durable and a mismatch refuses
honestly; a re-split that yields identical chunk text never re-embeds; and
the whole conformance suite runs offline with no API key and no heavy
dependency?

## Part A — provider interfaces in the field

Every studied library converges on the same five-part shape, differing
only in where each part lives. The table is the finding; the prose after
it says what each library adds.

| Library (file) | Document batch | Query (single) | Async | Dimension | Model identity | Query/document asymmetry | Batch size default / cap |
|---|---|---|---|---|---|---|---|
| LangChain `Embeddings` (`embeddings/embeddings.py`) | `embed_documents(texts)` abstract | `embed_query(text)` abstract | `aembed_documents` / `aembed_query` default to `run_in_executor` of the sync pair | **none** | **none** | two methods, "usually identical" per docstring | none in base; OpenAI partner `chunk_size=1000` |
| llama_index `BaseEmbedding` (`base/embeddings/base.py`) | `get_text_embedding_batch` (splits by `embed_batch_size`) | `get_query_embedding` | `aget_*` variants; `aget_text_embedding_batch` gathers per-batch coroutines, optional `num_workers` | none on base | `model_name: str = "unknown"` | `_get_query_embedding` vs `_get_text_embedding` hooks; HF adapter prepends `query_instruction`/`text_instruction` | `DEFAULT_EMBED_BATCH_SIZE = 10`, field cap `le=2048`; OpenAI adapter 100, asserts ≤ 2048 |
| haystack (`components/embedders/`) | `DocumentEmbedder.run(documents)` — a separate **component** | `TextEmbedder.run(text)` — a separate component | `run_async` on the OpenAI pair | none | `model` constructor arg; response `model` echoed into `meta` | `prefix`/`suffix` strings on both; `meta_fields_to_embed` + `embedding_separator` on the document side | `batch_size=32`, `progress_bar=True` |
| LanceDB `EmbeddingFunction` (`embeddings/base.py`, `registry.py`) | `compute_source_embeddings(texts)` | `compute_query_embeddings(query)` | none (sync, pyarrow/numpy) | **`ndims()` abstract** — required | `@register("name")` alias + pydantic fields persisted as table metadata | two abstract methods; `TextEmbeddingFunction` collapses them; Cohere sets `search_query`/`search_document`; Voyage sets `input_type="query"/"document"` | none in base; Voyage builds token-bounded batches (`voyageai.py:360`) |
| mem0 `EmbeddingBase` (`embeddings/base.py`) | `embed_batch(texts, memory_action)` — default loops `embed` | `embed(text, memory_action)` | none | `embedding_dims` in config (OpenAI adapter defaults 1536, passes `dimensions` only when set) | `model` string in config | `memory_action` ∈ {add, search, update} — a *purpose* tag, not a prefix | OpenAI adapter `MAX_BATCH = 100`, re-sorts by `index` |
| cognee `EmbeddingEngine` (`embeddings/EmbeddingEngine.py`) | `async embed_text(list[str])` — batch only | (same call with one text) | async-native | `get_vector_size()` required; config auto-derives from a provider/model table, else a fallback | `embedding_model` string, `embedding_provider` | none | `get_batch_size()` required on the protocol |

What is common, and what each adds:

- **Two entry points, document-batch and query-single**, in all six. The
  asymmetry is real for a whole model family: E5 expects `"query: "` /
  `"passage: "`, BGE v1.5 expects `"Represent this sentence for searching
  relevant passages: "` on the query side only, Voyage's `input_type`
  prepends `"Represent the query for retrieving supporting documents: "`
  vs `"Represent the document for retrieval: "` server-side, Cohere's
  `input_type` is `search_query` vs `search_document`, and
  sentence-transformers models it as named `prompts` with
  `encode_query`/`encode_document`. The provider, not the caller, owns the
  prefix — a seam that exposes only one `embed(texts)` cannot serve E5/BGE
  correctly. (Sources: Pinecone E5 guide, HF E5 discussion, sbert docs.)
- **Dimension discovery** is required in the two libraries that own a
  fixed-width column (LanceDB `ndims()`, cognee `get_vector_size()`) and
  absent in the two that are pure adapters (LangChain, llama_index).
  vfs owns a fixed-width column on Postgres (`VectorType(postgres_native=
  True)` requires a dimension, `vector.py`), so the seam is in LanceDB's
  position: **dimension is a required property**.
- **Model identity** is a config string everywhere it exists, and absent
  from LangChain's base entirely. A LangChain adapter therefore has to be
  *told* its identity and dimension — the seam cannot adopt LangChain's
  ABC as its own protocol.
- **Async**: llama_index and cognee are async-native; LangChain defaults
  to an executor hop; haystack offers `run_async`; LanceDB and mem0 are
  sync. The seam must be async (it runs inside coroutines under the fan-out
  deadline) and must wrap sync providers explicitly.
- **Batching** lives in the *library*, not the provider, in llama_index
  (`embed_batch_size` loop), LangChain-OpenAI (`chunk_size` plus a
  tiktoken split at `embedding_ctx_length=8191`), haystack, mem0. Only
  LanceDB's Voyage function batches by tokens. Nobody batches by the
  API's documented token-per-request cap except LangChain's tiktoken
  path, and LangChain issue #31227 records that path still producing 400s
  from count drift.
- **Retries**: openai-python retries 2× by default, 0.5 s initial, 8 s
  cap, honoring `retry-after-ms`/`Retry-After`/`x-should-retry`
  (`_constants.py`, `_base_client.py:756-830`); llama_index's OpenAI
  adapter sets `max_retries=10`; LanceDB wraps every call in
  `retry_with_exponential_backoff` (7 retries, base 2, jitter) and offers
  a `rate_limit(max_calls=0.9, period=1.0)` decorator; llama_index's base
  has an optional `rate_limiter` acquired before each batch.
- **Caching**: llama_index's base carries an optional `embeddings_cache`
  keyed on the **raw text** (`_get_text_embeddings_cached`) — not on the
  model, so a model swap serves stale vectors. mem0, haystack, LangChain
  base: no cache. This is the one place the field is worse than what vfs
  already has (a `content_hash` per chunk row).
- **Progress and telemetry**: haystack `progress_bar`, llama_index
  dispatcher events per batch with the model dict as payload. vfs's
  analogue is the `Result` envelope's records, not a tqdm bar.

## Part B — batch physics of the hosted APIs

**OpenAI** (`/v1/embeddings`; client `client.embeddings.create(input=...,
model=..., dimensions=..., encoding_format=...)`, openai-python
`resources/embeddings.py:50-121`, which defaults `encoding_format` to
`base64` and decodes client-side). Documented caps: **8,192 tokens per
input**; **2,048 inputs per request** ("any array must be 2048 dimensions
or less"); **300,000 tokens summed across all inputs per request**
(error text: `Requested 300500 tokens, max 300000 tokens per request`);
empty strings refused. `dimensions` (text-embedding-3 only) is
Matryoshka truncation — the guide says 3-large cut to 256 still beats
full ada-002, and manual truncation must be followed by L2
normalization. Models: 3-small 1,536-d **$0.02/M tokens**, 3-large
3,072-d **$0.13/M**, ada-002 1,536-d. Rate limits (both v3 models share
the table): Free 100 RPM / 40k TPM; Tier 1 3,000 RPM / **1M TPM**; Tier 2
5,000 / 1M; Tier 3 5,000 / 5M; Tier 4 10,000 / 5M; Tier 5 10,000 / 10M.
Responses carry `x-ratelimit-{limit,remaining,reset}-{requests,tokens}`
and `Retry-After`; guidance is exponential backoff with jitter, and
"batching multiple tasks into each request" when RPM binds before TPM.
**Batch API**: `/v1/embeddings` is supported, 50% off ($0.01/M small,
$0.065/M large), 24 h window, ≤ 50,000 requests *and* ≤ 50,000 embedding
inputs per batch, 200 MB file, separate "enqueued tokens" pool (embedding
models: Tier 1 3M, Tier 2 20M, Tier 3 100M, Tier 4 500M, Tier 5 4B), 2,000
batches/hour.

**Voyage**: `input_type` ∈ {`query`, `document`} adds a server-side
instruction; `truncation` defaults `true`; ≤ **1,000 inputs per request**;
total tokens per request by model — 1M (voyage-4-lite / 3.5-lite), 320K
(voyage-4 / 3.5), 120K (voyage-4-large / code-3); `output_dimension` ∈
{2048, 1024 (default), 512, 256}; `output_dtype` float/int8/uint8/binary.
Rates (Tier 1): voyage-4 8M TPM / 2,000 RPM, code-3 3M TPM, lite 16M TPM;
tiers 2–3 multiply by 2×/3×. Prices: voyage-4 $0.06/M, 4-lite $0.02/M,
4-large and code-3 $0.12/M; first 200M tokens free per account.

**Cohere** (`/v2/embed`): `input_type` ∈ {`search_document`,
`search_query`, `classification`, `clustering`, `image`}; `truncate` ∈
{NONE, START, END} with `max_tokens` per input; **≤ 96 texts per call**;
embed-v4 `output_dimension` ∈ {256, 512, 1024, 1536 (default)},
`embedding_types` float/int8/uint8/binary/ubinary/base64. Rate limit:
2,000 inputs/min on both trial and production keys.

**Gemini**: `gemini-embedding-001` takes `task_type` (RETRIEVAL_QUERY,
RETRIEVAL_DOCUMENT, CODE_RETRIEVAL_QUERY, ...) with a 2,048-token input
cap; `gemini-embedding-2` (April 2026) drops `task_type` — the
instruction goes in the prompt — and takes 8,192 tokens; both offer
`output_dimensionality` 128–3072 (MRL; 768/1536/3072 recommended).
Prices: 001 $0.15/M ($0.075 batch), 2 $0.20/M text ($0.10 batch). The
public rate-limit page publishes no RPM/TPM for embedding models (only
batch enqueued-token caps: 500K / 5M / 10M by tier) and defers to the AI
Studio dashboard. mem0 issue #6189 records the Vertex `gemini-embedding-001`
endpoint accepting **one** input per request.

### The ETL contract, in numbers

10,000 files → ~10⁵ chunks. vfs's splitter caps a chunk at `chunk_size=
2048` **characters** (`chunking.py:216-329`); the synthetic corpus below
measured 464 tokens per 2,322-char chunk, so ~500 tokens is the right
planning figure and **5 × 10⁷ tokens** is the job.

| Provider / model | Requests (binding cap) | Wall at documented rate | List cost | Notes |
|---|---|---|---|---|
| OpenAI 3-small | **167** (300k tokens/req → 600 chunks/req; the 2,048-input cap would allow 49) | Free 40k TPM: **~21 h**; Tier 1–2 1M TPM: **50 min**; Tier 3–4 5M TPM: 10 min; Tier 5: 5 min | **$1.00** (batch $0.50) | RPM never binds (167 ≪ 3,000/min); TPM always does |
| OpenAI 3-large | 167 | same table | **$6.50** (batch $3.25) | 3,072-d ≈ 1.2 GB of float32 vectors for 10⁵ chunks; `dimensions=1024` cuts storage 3× at no API cost |
| OpenAI Batch API | 2 batches (50,000 inputs each) | 24 h window; Tier 1 enqueued cap 3M tokens → **17 sequential batches**, Tier 2 (20M) → 3, Tier 3+ → 1 | half price | not viable below Tier 3 for a single 50M-token job |
| Voyage voyage-4 | 157 (320K tokens/req → 640 chunks) | 8M TPM Tier 1: **~6 min** | $3.00 (free under the 200M allowance) | voyage-4-lite: 1M tokens/req → 50 requests, $1.00 |
| Cohere embed-v4 | **1,042** (96 texts/req) | 2,000 inputs/min: **50 min** | not fetched | request count, not tokens, is the wall |
| Gemini embedding-2 | unpublished per-request cap; batch job ≤ 200k requests | unpublished | $10.00 (batch $5.00) | 001's 2,048-token cap is within one CJK chunk of vfs's 2,048-char ceiling |

Three consequences the seam must encode. (1) **Token caps bind before
input-count caps** at vfs's chunk size on every provider that has one, so
the batch splitter must meter tokens, and an estimate is enough only with
headroom — the tiktoken-vs-server drift (pgai #728, LangChain #31227)
says plan at ~250k of 300k. (2) **TPM is the wall, not latency or RPM**:
at Tier 1 a 10k-file reindex is a 50-minute network phase whatever the
concurrency; a concurrency knob above ~4–8 in-flight requests buys
nothing but 429s. (3) **Cost is small and countable**: the OpenAI
response carries `usage.total_tokens`, so the seam can report spent
tokens exactly rather than estimate them.

## Part C — identity, migration, cache

### Where the identity lives today, and where it should

vfs already carries a *type-level* identity: `Vector[dim, model]`
subclasses validate length on construction and `VectorType(dimension,
model_name)` refuses a bind whose `Vector` carries a *different* model
name (`vector.py:210-226`). But the check is advisory — a plain
`list[float]` binds without a name, and nothing at runtime says which
model a stored row came from. `NativeEmbeddingConfig(dimension,
index_method, operator_class, model_name)` (`vector.py:49-63`) shapes the
column at table-build time (`rows.py:323-332`) and is the only place a
model name is configured — on the Postgres-native path only; the JSON
path has no identity at all. The July memo (§4 Q8) already named the
missing pieces: a space registry (model → dimension → kinds) and
row-level space identity, with single-space as the degenerate case.

The field's answer is uniform: identity is a config string checked
nowhere durable (LangChain, llama_index, mem0, cognee) — except LanceDB,
which **persists the embedding function's config into the table's
metadata** (`registry.function_to_metadata`, `get_table_metadata`), so
opening a table recovers which function made its vectors. That is the
right posture for vfs, and the existing single-row `meta` table
(`rows.py:462`) is the precedent: it already stamps
`schema_format_version` (verified at first touch) and `mount_identity`.

**Recommendation**: add `embedding_model` (string) and
`embedding_dimension` (int) to the `meta` row — the single-space
degenerate form of the registry — stamped when the first embedding is
written; `ensure_ready` compares them to the configured provider's
`model_id`/`dimension` exactly as it verifies `schema_format_version`.
The identity string should be provider-qualified and dimension-qualified
(`openai/text-embedding-3-small@1536`, `model2vec/potion-base-8M@256`)
because `dimensions=` truncation makes one model name several
incompatible spaces. The registry generalization — a `spaces` table
`(space_id, model_id, dimension, ...)` and a side table `(chunk_id,
space_id, vector)` — is the July memo's shape and stays reserved; the
meta-row pair migrates into it as row 1 when media spaces arrive.

### Mismatch: how it refuses

Two mismatches, two verdicts:

- **Dimension mismatch on a native column** (Postgres `vector(1536)` and
  a 3,072-d provider): the column physically cannot hold the vectors.
  Refuse at `ensure_ready` — an `invalid` result naming the column
  dimension and the provider — because no verb can succeed; the fix is a
  DDL migration (new column or new mount), out of the verbs' reach.
- **Model mismatch with a compatible column** (JSON column, or same
  dimension different model — cosine between them is noise): `glean`
  must not silently rank noise. Refuse the vector leg with a
  `conflict`-kind record naming stored vs configured model, and serve
  the lexical leg alone with that record at warning severity (gap 1's
  freshness posture, applied to identity). `reindex` is the migration:
  a stale identity marks **every** chunk's embedding stale — the same
  law as `chunk_generation` in `chunk_dirty` (`indexing.py:246-256`),
  where a generation change re-dirties every entry — nulls them under
  the new identity, re-embeds, and re-stamps `meta`. Model swap =
  re-embed the mount, executed by the verb that already owns
  regeneration, never by a write.

### The cache: `(model, content_hash)` — the chunk row already is one

Chunk rows carry `content_hash = sha256(content)` (`chunk.py:76-77`,
`rows.py:431`) and embedding staleness is `embedding IS NULL`. Two
existing laws already prevent most re-embedding: the fingerprint-skip law
leaves an entry's chunk rows untouched when its `content_hash` still
equals `chunk_source_hash` (same-body overwrite or restore re-splits
nothing), and a rename rewrites zero chunk rows. The one leak is a real
re-split: `chunk_dirty` deletes the entry's rows and inserts fresh ones
(`indexing.py:281-284`), dropping their embeddings even where the new
chunk text is byte-identical to an old chunk's.

**Recommendation, tier 1 (no new table)**: before the delete, read
`(content_hash, embedding)` for the resplit ids where `embedding IS NOT
NULL` (chunked by the membership budget), and carry each vector onto the
fresh row with the same hash at insert time. With the meta-row identity,
the row *is* the `(model, content_hash)` cache: identity is mount-wide,
hash is per row. **Tier 2, cross-entry dedup**: before calling the
provider for the unembedded set, look up any embedded row sharing a
`content_hash` (license headers, vendored copies, generated boilerplate)
— one `IN`-list probe per batch under the same budget. **Tier 3, a
separate `embedding_cache(model_id, content_hash, vector)` table** that
survives entry deletion and trash sweeps is the only version that needs
schema, and it is a fork, not a requirement; llama_index's text-keyed
cache is the cautionary example of what not to build (no model in the
key).

### Where the embed step sits in reindex, and why it is not a phase

Reindex today is: claim lease → `chunk_dirty` (one writer transaction,
CPU split offloaded) → `build_epoch` → `publish_epoch` → `reclaim_epochs`,
each "in its own writer transaction" (`backend.py:461-585`), with a beat
task pulsing the lease every 60 s against a 5-minute TTL
(`indexing.py:116-117`) and every phase boundary checking `lost`.

Embedding cannot be a phase of that shape, for one reason with three
faces: at Tier 1 it is a **50-minute network wait**. (a) A writer
transaction held open for 50 minutes is a lock horizon on every engine
(the MySQL-family next-key locks `chunk_dirty`'s docstring already
fights; Postgres `idle_in_transaction_session_timeout`; Oracle undo
retention). (b) The lease TTL is 5 minutes; the beat task keeps the
lease alive only because it is an independent asyncio task — which
works *if* the embed step awaits on the loop (an `await
client.embeddings.create(...)` yields; the beat ticks), and fails if it
blocks it. (c) A rival claiming through after a lost beat must find the
half-done embed harmless, which it is only if each written batch is
already committed and idempotent.

So the embed step is a **streaming batch loop, not a phase**: select
one budget's worth of `(id, content)` where `embedding IS NULL` (short
read transaction, ordered by id, bounded by tokens and inputs); embed
(no transaction open); write back with an `UPDATE ... WHERE id = :id
AND embedding IS NULL` (short writer transaction; a rival's identical
write is a no-op); check `lost` between batches; repeat. Where it goes in
the order: after `chunk_dirty` (rows exist), before `build_epoch` or
after `publish_epoch` — after is better, because the gram index is the
grep tier and should not wait 50 minutes behind the vector tier; the
vector tier's staleness is already tolerated by the "unembedded count as
a warning record" posture in gap 1.

### Why embedding belongs on the event loop, not the offload pool

`offload.py` exists because grep's verify and reindex's split/postings
run **real CPU** inside coroutines and would hold the loop against every
concurrent caller; it moves them to a thread pool sized to cores, one
batch in flight per instance. A hosted embed call is the opposite
profile: microseconds of CPU (JSON encode, base64 decode) around
hundreds of milliseconds to seconds of socket wait. On a thread pool
that wait pins a worker doing nothing — with `OFFLOAD_WORKERS = cores`
(10 here), ten in-flight requests would monopolize the pool grep's
verify shares, and every worker still contends for the GIL to parse the
response. On the loop, `AsyncOpenAI` (httpx) parks the wait in the
selector for free; bounded concurrency is an `asyncio.Semaphore(k)`
with k ≈ 4–8 (TPM binds long before latency does — Part B), and 429s
honor `Retry-After` by sleeping the coroutine, which costs nothing.
The offload pool's laws (deadline crosses absolute, one in flight,
cancellation is abandonment) are CPU laws; the network step needs
different ones — a per-request timeout, and cancellation that closes
the socket rather than lets a worker "finish into the void".

The exception proves the rule: a **local** provider (model2vec, a hash
embedder at 10⁵ chunks, a sentence-transformers model) *is* CPU-bound
and must take `call_offloaded` — the chunk loop's split already does.
So the seam's contract is async, and the adapter for a sync/CPU provider
is the one that hops through the executor (the way `_assess_and_split`
does), not the storage loop.

## Part D — offline and test providers

**model2vec** (MIT; `pyproject.toml`): static embeddings — a token → row
lookup in a safetensors matrix, mean-pooled; no transformer forward
pass. Runtime deps are `numpy`, `tokenizers`, `safetensors`,
`huggingface-hub`, `joblib`, `jinja2`, `tqdm`; **torch is confined to the
`distill`/`onnx`/`train` extras** and was verified absent from the
installed venv (24 packages, no `torch*`). `potion-base-8M` is MIT,
distilled from `bge-base-en-v1.5`, 7.56M parameters, measured `dim=256`
(the HF card's headline "384" is the 32M sibling), 30.2 MB weights +
0.9 MB tokenizer files, MTEB ≈ 51.3 (≈ 92% of all-MiniLM-L6-v2 per the
card). `StaticModel.encode` is deterministic (pure arithmetic), takes
`use_multiprocessing` (joblib above a 10,000-sentence threshold) and
`max_length` truncation. First use downloads from the Hub — a network
touch the test suite must never make, so it would be an *optional*
provider with the model pre-fetched, not the conformance default.

**fastembed** (Apache-2.0): ONNX Runtime inference of real transformer
models (default `BAAI/bge-small-en-v1.5`, int8). Deps: `onnxruntime`
(75 MB), `pillow` (13 MB), `tokenizers`, `huggingface-hub`, `requests`,
`loguru`, `mmh3`. Installs cleanly on 3.13 but is 141 MB of
site-packages and, measured below, **~4 chunks/s on 500-token chunks on
this CPU** — a 10⁵-chunk reindex would take ~7 hours. It is a quality
tier, not a test tier.

**A hashing embedder** (stdlib): tokenize `\w+`, `crc32` each token into
one of `dim` buckets with a sign bit, L2-normalize. Deterministic across
processes (unlike `hash()`), dimension-parameterized, zero download,
zero dependency, and — usefully for a conformance suite — *semantically
honest enough*: identical text gives identical vectors, shared
vocabulary gives positive cosine, disjoint vocabulary gives ~0. It
cannot rank by meaning, and it must not pretend to; it exists so the
suite can pin batching, budgets, cache hits, identity refusal, lease
interaction, tier honesty, and tie-break determinism across every
engine leg. LangChain ships the same idea as
`DeterministicFakeEmbedding` (seeded normal from a text hash,
`embeddings/fake.py`) and haystack as `mock_document_embedder.py`.

### Executed measurement

Apple M1 Pro (10 cores), CPython 3.13.11; throwaway venvs under the
session scratchpad; 10,000 synthetic chunks of 375 words (2,322 chars,
464 tokens by potion's tokenizer). Scripts and raw output in
`embedding-seam/`.

| Provider | site-packages | Beyond vfs's own `numpy` | Import | Model load | Model on disk | 10⁴ chunks × ~500 tokens, 1 thread | Throughput |
|---|---|---|---|---|---|---|---|
| hash embedder (stdlib), dim 256 | 0 | 0 | ~0 | none | 0 | 1.02 s | **9,777 chunks/s** |
| hash embedder, dim 1536 | 0 | 0 | ~0 | none | 0 | 1.68 s | 5,955 chunks/s |
| model2vec `potion-base-8M` (256-d) | 51 MB, 24 pkgs, no torch | ~30 MB (tokenizers 8.4, hf_xet 8.1, hf_hub 3.3, joblib 1.3, safetensors 1.1, ...) | 1.0 s cold / 0.09 s warm | 1.04 s (Hub cache warm) | 31 MB | 1.92 s (`use_multiprocessing=False`); 1.63 s with joblib | **5,212 chunks/s** (6,136 multiprocess); 0.54 ms single call |
| fastembed `bge-small-en-v1.5` int8 ONNX (384-d) | 141 MB, 30 pkgs | ~120 MB (onnxruntime 75, PIL 13, ...) | 4.2 s | 3.45 s | 64 MB | 200 chunks in 51 s → **~43 min per 10⁴**, ~7 h per 10⁵ (extrapolated) | 3.9 chunks/s (21.9 at ~100 tokens) |

Reading: model2vec embeds 10⁵ chunks in ~20 s single-threaded — faster
than the split step it would follow — at 30 MB of extra wheels and a
31 MB one-time download; the hash embedder does it in ~10 s with
nothing; fastembed is two orders of magnitude slower and four times the
install, so it is the wrong offline default even before the dependency
rule is applied.

**Recommendation**: the hash embedder ships in `src/vfs` as the
conformance-suite provider and the in-memory backend's default (no
download, no key, no dependency, deterministic per engine leg —
CLAUDE.md's "no heavy deps without measured need" is satisfied by
measuring that nothing is needed). model2vec becomes an optional extra
(`vfs-py[embed-local]`) — the "works offline with real semantics" tier
for agents on a laptop, with the test suite exercising its adapter only
when the package and a cached model are present. fastembed is not
adopted. OpenAI and LangChain adapters ride the existing `openai` and
`langchain` extras.

## Bearing on vfs

### The protocol, sketched

```python
class Embedded(NamedTuple):
    vectors: list[list[float]]     # portable floats; numpy never crosses the seam
    tokens: int                    # provider-reported when available, else estimated


@runtime_checkable
class EmbeddingProvider(Protocol):
    model_id: str                  # provider-qualified, dimension-qualified:
                                   #   "openai/text-embedding-3-small@1536"
    dimension: int                 # required — vfs owns fixed-width columns
    max_input_tokens: int | None   # per-input cap (8192 OpenAI, 2048 gemini-001); None = unbounded
    max_batch_inputs: int          # per-request input cap (2048 / 1000 / 96 / 1)
    max_batch_tokens: int | None   # per-request token cap (300k / 320k / None)

    def estimate_tokens(self, text: str) -> int: ...          # chars // 4 default; tiktoken if the adapter has it
    async def embed_query(self, text: str) -> list[float]: ...          # applies the model's query prefix
    async def embed_documents(self, texts: Sequence[str]) -> Embedded: ...  # applies the document prefix; ≤ caps
```

The provider declares caps and prefixes and embeds *one* batch; it does
not batch, retry across batches, cache, or count cost. Those belong to
storage, which already owns the budget vocabulary (`chunked`,
`byte_chunked`, `membership_budget`): a `token_batched(rows, provider)`
sibling that cuts on `max_batch_inputs`, `max_batch_tokens` (with
headroom), and the engine's bind budget for the write-back. Storage
also owns the `(model, content_hash)` carry-over and dedup, the
streaming batch loop with lease checks, the `Semaphore(k)`, per-request
timeouts under the fan-out deadline, and the envelope's records
(`embedded=N, cached=M, tokens=T, requests=R, unembedded=U` at warning
severity when U > 0). Retries within one request stay in the adapter
(openai-python already does them; a LangChain embedder's own client
does its own).

Adapters:

- `OpenAIEmbeddingProvider(client: AsyncOpenAI, model, dimensions=None)`
  — `max_batch_inputs=2048`, `max_batch_tokens=300_000`,
  `max_input_tokens=8192`, `dimension` from `dimensions` or the model
  table (1536 / 3072), `model_id` derived; reports `usage.total_tokens`.
- `LangChainEmbeddingProvider(embeddings: Embeddings, *, model_id,
  dimension=None)` — `aembed_documents`/`aembed_query`; dimension
  probed once by embedding a sentinel when not given (LangChain's base
  carries neither); no token report (estimate).
- `Model2VecEmbeddingProvider(StaticModel)` (extra) and
  `HashEmbeddingProvider(dimension=64)` (core) — CPU providers whose
  `embed_documents` hops through `call_offloaded`; caps unbounded.

How the router hands the query over: unchanged — `VFS.glean` fans
`query` out opaquely (`base.py:1252-1290`); each mount's backend calls
its own provider's `embed_query` inside its `glean`, under the fan-out
deadline, so two mounts with two models each embed once with the right
model, and a mount with no provider serves the lexical leg with an
absent-vector record. The `Vector[dim, model]` type and
`VectorType.model_name` stay as the bind-time belt; the meta-row stamp
is the suspenders.

### Named forks for the memo and ADR

1. **Identity home**: meta-row pair now (recommended, single-space
   degenerate) vs. the July registry table immediately vs. config-only
   (rejected — nothing durable says what the rows are).
2. **Mismatch policy**: refuse the vector leg and let `reindex` migrate
   (recommended) vs. auto-migrate on first `glean` (rejected — a read
   verb must not spend 50 minutes and $6.50).
3. **Cache tier**: in-row carry-over + cross-entry dedup (recommended,
   no schema) vs. a separate `(model_id, content_hash)` table that
   survives deletion.
4. **Embed step shape**: streaming per-batch transactions after publish
   (recommended) vs. a fourth phase transaction (rejected — lock horizon
   and TTL).
5. **Concurrency source**: fixed `Semaphore(k)` (recommended first) vs.
   header-driven adaptation from `x-ratelimit-remaining-tokens`.
6. **Test provider**: hash in core + model2vec extra (recommended) vs.
   model2vec as the default (rejected — a Hub download in the suite) vs.
   fastembed (rejected on both size and speed).
7. **Batch-splitter owner**: storage (recommended — it owns budgets) vs.
   provider (the field's llama_index/LangChain shape).
8. **Token estimation**: `chars // 4` with headroom (recommended) vs.
   tiktoken as an optional exact counter — the drift evidence says the
   headroom is needed either way.
9. **Truncation**: refuse over-cap inputs with a record vs. truncate with
   a record (recommended where the API offers `truncation=true`; vfs's
   2,048-char chunk ceiling makes this a CJK-only edge for gemini-001).
10. **Offline bulk (OpenAI Batch API)**: a `reindex` mode for
    half-price, 24-hour embedding — deferred; the enqueued-token caps
    make it a Tier-3-and-up feature.

## Sources

Reference clones (commits above): langchain
<https://github.com/langchain-ai/langchain>; llama_index
<https://github.com/run-llama/llama_index>; haystack
<https://github.com/deepset-ai/haystack>; lancedb
<https://github.com/lancedb/lancedb>; mem0 <https://github.com/mem0ai/mem0>;
cognee <https://github.com/topoteretes/cognee>; model2vec
<https://github.com/MinishLab/model2vec>; fastembed
<https://github.com/qdrant/fastembed>; openai-python
<https://github.com/openai/openai-python>; letta
<https://github.com/letta-ai/letta> (no source at the refreshed commit).

Docs: OpenAI embeddings guide
<https://developers.openai.com/api/docs/guides/embeddings>; embeddings
API reference
<https://developers.openai.com/api/docs/api-reference/embeddings/create>;
model pages <https://developers.openai.com/api/docs/models/text-embedding-3-small>,
<https://developers.openai.com/api/docs/models/text-embedding-3-large>;
rate limits <https://developers.openai.com/api/docs/guides/rate-limits>;
Batch API <https://developers.openai.com/api/docs/guides/batch>; OpenAI
community "Max total embeddings tokens per request"
<https://community.openai.com/t/max-total-embeddings-tokens-per-request/1254699>;
pgai #728 (tiktoken vs server count drift)
<https://github.com/timescale/pgai/issues/728>; LangChain #31227
<https://github.com/langchain-ai/langchain/issues/31227>. Voyage
<https://docs.voyageai.com/reference/embeddings-api>,
<https://docs.voyageai.com/docs/rate-limits>,
<https://docs.voyageai.com/docs/pricing>. Cohere
<https://docs.cohere.com/reference/embed>,
<https://docs.cohere.com/docs/rate-limits>. Gemini
<https://ai.google.dev/gemini-api/docs/embeddings>,
<https://ai.google.dev/gemini-api/docs/rate-limits>,
<https://ai.google.dev/gemini-api/docs/pricing>; mem0 #6189 (Vertex
one-input-per-request) <https://github.com/mem0ai/mem0/issues/6189>.
E5/BGE prefixes: Pinecone "The Practitioner's Guide to E5"
<https://www.pinecone.io/learn/the-practitioners-guide-to-e5/>; HF
multilingual-e5-large discussion #34
<https://huggingface.co/intfloat/multilingual-e5-large/discussions/34>;
sentence-transformers prompts
<https://sbert.net/examples/sentence_transformer/applications/computing-embeddings/README.html>.
model2vec potion-base-8M card <https://huggingface.co/minishlab/potion-base-8M>.
