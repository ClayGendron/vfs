# Audit: search (glob, grep, glean, graph), the embedding provider seam, BM25 + vector fusion, chunking, renderers

- Audited 2026-10-28 against `90f5883` (`git log`, EXECUTED). Read-only.
- Labels: READ (I read it), EXECUTED (I ran it), INFERRED (deduced, not directly verified).
- Env note (EXECUTED): this container's venv lacks the `documents` extras, so `tests/rendering/test_renderers.py` and `tests/storage/database/test_render.py` fail at *collection* (`import docx`). That is an environment fact, not a repo bug — but it means the document extras are a hard dev dependency of the suite. BEIR cache (`~/.cache/vfs/ranking`) is also absent here, so the `slow` BEIR quality tests skip.

---

## 1. Built today

### 1.1 glean, end to end (READ)

Entry: `src/vfs/storage/backends/database/backend.py:554` `DatabaseStorage.glean`. Sequence:

1. `ensure_ready` (first touch, vector-function probe) — `backend.py:566`.
2. `_vector_leg_for(query, scoped)` — `backend.py:604-658`. Mints a `VectorLeg(query_vector, model_id, tier, prelude)` or returns `None` plus a *record*:
   - no provider → `ErrorKind.unavailable`, severity `info`, `data.reason="no_provider"` (`backend.py:617-623`);
   - stored space ≠ configured provider (`EngineHost.embedding_stale`, `engine.py:241-250`) → `ErrorKind.conflict`, `warning`, `reason="stale_identity"` (`backend.py:625-644`);
   - `provider.embed_query` raises → `ErrorKind.unavailable`, `warning`, `retryable=True`, `reason="embed_failed"` (`backend.py:645-652`).
   - **Query-time embedding of the query string is built**: `_embed_query` (`backend.py:669-680`) calls `provider.embed_query`, unit-normalises, memoises in a 256-entry LRU keyed `(model_id, query)` (`QUERY_VECTOR_CACHE`, `backend.py:171`), under `asyncio.wait_for(…, glean_wall_seconds)`.
   - Tier: `native_ann` only when profile `vector_distance == "ann"`, a native column within pgvector's 2,000-d index cap (`_ann_indexed`, `backend.py:660-667`; `PGVECTOR_INDEX_MAX_DIMENSION` `models/rows.py:153`) and (unscoped or `ann_honours_scope`); pgvector ≥ 0.8 gets the `SET LOCAL hnsw.iterative_scan = relaxed_order` prelude (`backend.py:174-175, 656-657`). Otherwise `native_exact`.
3. `glean_rows` — `glean.py:215-431`, one session, SELECTs only, redriven on `StaleSnapshot`:
   - tokenizes the query with the index's Rust tokenizer (`glean.py:257`); no term → `ErrorKind.invalid` (`:258-260`);
   - **lexical leg**: round one fetches summary rows + head blocks (`HEAD_BLOCKS=8`, `:125`), scores in Rust (`score_blocks`), round two asks `select_blocks` which later blocks can change the top-k and fetches exactly those by full PK prefix, arms packed under the bind budget (`_chunk_ranking` `:466-513`, `_packed_arms` `:516-528`). No scoring SQL on any dialect. Two rungs: allow-list ≤ `SCOPE_ID_BUDGET=5000` → filter-then-fetch; wider → fetch-then-filter with one `PROBE_DEEPEN=4` deepening and a `truncated` warning (`:310-335`);
   - **vector leg**: one statement shape on every dialect — `chunks JOIN entry … WHERE embedding IS NOT NULL AND chunked AND <kind> AND <pushdown> ORDER BY <cosine distance>, id LIMIT depth` (`_vector_leg` `:598-687`), distance spelled per dialect by `distance.py:31-43` (`<=>` pgvector, `vector_distance(…,COSINE)` Oracle, `VECTOR_DISTANCE('cosine',…)` MSSQL, `vec_distance_cosine` MariaDB and SQLite/sqlite-vec). Depth `max(10*limit, 100)` (`:131-135`). Narrow allow-list runs per id chunk and merges client-side; wide scope deepens once. Under a partial view it runs once per visibility clause (`:648-650`). Scores are `1 - distance`;
   - **overlay**: `NOT encoded` rows (≤ `OVERLAY_BUDGET=500`) are tokenized live and scored with the epoch's statistics (`:365-385`) — the lexical leg only; the vector leg has no overlay (`embedding IS NOT NULL`);
   - **fusion** `_fuse(ranker, hits, vector_hits)` (`:389`): each leg MaxP-aggregated to entries, cosine normalised by `unit_cosine` ((cos+1)/2), BM25 by `min_max` over the candidate union, combined by the mount's `Ranker.fusion` (`storage/ranking.py:100-143` `Convex`, default even 0.5/0.5 at `:111`; `RRF` `:145-191` as the rank-only floor);
   - **signals**: `signal_factors` multiplies stored priors in (`:390-392`; `signals.py`), read never computed on the query path;
   - result: `Observation` per entry, `Match` rows per top chunk (`TOP_CHUNKS=3`), query-biased preview (`results/preview.py`), `lexical_stats` export and a `legs` extra naming tier/model/depth/hits and `"fused": "client"` (`:417-431`).
4. Router: `base.py:1463` fans out `min(3*limit, 256)` per mount and merges with `rerank.merge_ranked` (`rerank.py`, `BM25Rerank` over corpus-wide exported statistics, order law) — single mount skips the rerank.

**Graph leg in glean**: none. The only "graph" contribution to ranking is the stored centrality prior (`Signal(measure=InDegree|PageRank|Katz)`, `ranking.py:220-287`, kernel `crates/vfs-core/src/signals.rs`), off by default (`Ranker(signals=())`, `ranking.py:384`).

**Traits** (`backend.py:289-296`): `glean_signals = "hybrid"` iff an embedder is configured else `"lexical"`; `glean_staleness = "overlay"`; vocabulary pinned in `storage/protocol.py:74-87`. **Capabilities** (`backend.py:272-287`): `glean` withheld iff `profile.vector_distance == "none"` (the generic floor); `graph` is never withheld (ADR 079 amendment honoured).

**Vectors are built at `reindex` only** (READ `backend.py:1118-1147`, `_embed_step` `:1405-1480`; arch doc 08). The write path stamps dirty flags; `chunk_dirty` carries existing vectors onto re-split rows with the same `content_hash` (`indexing.py:245, 291-294, 586-620`). INFERRED: no write-path call touches `chunks.embedding` beyond that carry.

### 1.2 The embedding provider seam (READ)

- Protocol `EmbeddingProvider` (`embedding/provider.py:57-86`): `model_id`, `dimension`, `max_input_tokens`, `max_batch_inputs`, `max_batch_tokens`, `estimate_tokens`, `embed_query`, `embed_documents -> Embedded(vectors, tokens)`. `LocalEmbeddingProvider` (`:104-137`) hops `embed_batch` to an executor; `LOCAL_BATCH_INPUTS = 2_048` (`:42`).
- Adapters: `HashEmbeddingProvider` (`hashing.py`, BLAKE2b signed feature hashing of index tokens + bigrams, 64-d default — the conformance floor and `InMemoryStorage`'s default, `storage/backends/memory.py:57`); `Model2VecEmbeddingProvider` (`model2vec.py`, default `minishlab/potion-base-8M`, lazy import, `embed-local` extra); `OpenAIEmbeddingProvider` (`openai.py`, caps 2,048/300k/8,192, Matryoshka `dimensions`, `usage.total_tokens`); `LangChainEmbeddingProvider` (`langchain.py`, identity supplied, width probed once).
- Extras (`pyproject.toml:51-53`): `openai`, `langchain`, `embed-local = ["model2vec>=0.5"]`. **No fastembed anywhere** in `src/`, `pyproject.toml`, `docs/`, `README.md` (EXECUTED grep: the only MiniLM mention is a comparison comment in `model2vec.py:92`).
- Tests (EXECUTED, 95 passed/1 skipped across `tests/embedding`, `test_vector_leg.py`, `test_embed.py`, `test_sqlite_vec.py`): protocol conformance of all four adapters (`test_provider.py:37`), OpenAI and LangChain via fake transports, model2vec via a loaded model object; the real potion pin skips when the Hub cache is absent (`test_adapters.py:131`, `tests/ranking/test_embedders.py:27`).

### 1.3 The embed step of reindex (READ)

`embed.py` + `backend.py:1405-1480`: keyset pages of `EMBED_PAGE_ROWS=4_096` NULL-embedding rows of live chunked entries; `token_batched` cuts by `max_batch_inputs` and `max_batch_tokens` with 5/6 headroom (`:112-134`); per-input truncation (`:136-144`); batches embed with no transaction open under `asyncio.Semaphore(embed_concurrency=4)` and `EMBED_TIMEOUT_SECONDS=120` per request, one `Retry-After` honoured (`:346-368`); landing is `UPDATE … WHERE id=:id AND embedding IS NULL` executemany (`:214-240`); content-hash cache from the chunk table itself (`cached_vectors` `:185-211`); lease `lost` checked between pages; provider failure ends the step with `ErrorKind.unavailable` warning, retryable, and the `embedding` extra reports `embedded/cached/tokens/requests/truncated/unembedded` (`:95-104`).

**Identity / model pinning**: `vfs_meta.embedding_model` + `embedding_dimension` (`models/rows.py:648-651`), stamped by the first landed batch (`write_vectors` `:232-239`), read at first touch (`engine.py:579-593`). Model change → `clear_embeddings` then re-embed under the new identity (`backend.py:1421-1429`). A stored width ≠ the native column's width refuses first touch with `ErrorKind.invalid` naming "re-provision the mount" (`engine.py:583-592`). Native column: `NativeEmbeddingConfig` is synthesised from the embedder's width when not given (`engine.py:153-154`), the chunks table takes the engine's own vector type on Postgres/Oracle/MSSQL/MariaDB plus the pgvector HNSW DDL (`rows.py:405-414, 592-593, 912-913`); SQLite keeps packed float32.

### 1.4 Distance-function proof and engines (READ)

- `DialectProfile.vector_distance` (`dialects.py:362`): sqlite `exact`, postgresql `ann`, mssql `exact`, mariadb `ann`, oracle `ann`, GENERIC `none` (`:417, 442, 481, 513, 540, 553-558`).
- `VectorFunction` on the profile (`:378-384`): SQLite probes `SELECT vec_version()`; Postgres probes `pg_extension` and declares `CREATE EXTENSION IF NOT EXISTS vector` as the install the explicit verb alone runs (`:418-426, 444-454`). First touch probes and refuses `unavailable` naming the fix (`engine.py:407-420, 449-477`); `install_extensions()` (`backend.py:1099-1116`, `engine.py:271-296`) runs the install under a savepoint and answers `permission_denied` for a non-superuser. sqlite-vec is a core dependency (`pyproject.toml:41`) loaded on every connection by the pool hook (`engine.py:638-644`). Pinned in `test_sqlite_vec.py` (24 tests, EXECUTED green) and `test_dialects.py:181-182`.
- Every engine leg runs the storage contract with the hashing embedder (`tests/storage/test_conformance.py:9, 86-106`), so the in-engine cosine statement executes on Postgres/MariaDB/MSSQL/Oracle when `VFS_TEST_<ENGINE>_URL` is set. The Rust `vector_topk` kernel is the referee (`test_vector_leg.py:288`).

### 1.5 Fusion quality harness (READ; partly EXECUTED)

`tests/ranking/`: `vfs_native` golden set (200 docs / 40 queries / graded qrels, `corpora.py`, `test_harness.py:115-124`), BEIR `scifact`+`nfcorpus` loaded from `$VFS_RANKING_CACHE` or `~/.cache/vfs/ranking`, **skipped when absent** and marked `slow` (`:83-88, 126, 154-165`). Gate: `ndcg@10 >= baseline - 0.005` for BM25 (`:57`) and glean == driver arm equality. Pins: `top10.json` (lexical, every leg), `top10_hybrid.json` (verb on the 64-d hashing embedder, sqlite + memory only, `pins.py:38, 66-83`, `test_harness.py:174-185`), `top10_merge.json` (router over two mounts, sqlite and each sqlite+server mix, lexical only). The hybrid arms with hash/potion embedders are *recorded* not gated (`test_vector_only_and_fused_are_recorded`, `:226`). EXECUTED: harness, `tests/storage/test_ranking.py`, `tests/test_rerank.py` collection ran green minus the two rendering modules; BEIR deselected/skipped here.

### 1.6 Permissions in glean (ADR 065) (READ)

- Visible-set statistics are built: `_visible_lexicon` (`glean.py:701-756`) recounts `N`, `avg_dl` and each term's `df` over the rows the view admits, rescales every block bound, and scores only visible chunks; `_visible_corpus` (`:759-798`) uses the dialect's range join or clause fan. Both legs and the overlay pass every row through `view.holds` (`:380, 574-577, 652-653`). The vector leg computes distance only on rows a clause admits (`:648-650`).
- Pinned indirectly: `tests/storage/database/test_rights.py:706-714` compares glean paths+scores across every partial-read shape; `:295` asserts a partial caller's glean. **No direct statistics-leak regression test exists** (EXECUTED grep for `leak` in `tests/` finds only unrelated files; ADR 065 "Consequences" asked for S2's scripts to become one). The known open cost: visible `df` reads every block of each query term (`open-questions.md:309-310`).

### 1.7 grep and glob (READ, briefly)

`storage/backends/database/grep.py` (gram index, candidate budget 25,000, posting/content byte budgets, overlay scan, `StaleSnapshot` redrive, Rust `candidate_ids` + `ContentMatcher`); `pattern_matching/glob.py` (one compile chokepoint, 64-arm cap); `pattern_matching/grep.py` (regex-crate language gate). Mature; out of the 0.1.0 critical path for theme (3).

### 1.8 Rust kernels (READ `crates/vfs-core/src/python.rs:496-515`)

`distinct_gram_count`, `supported_grammars`, `chunk_spans`, `markdown_refs`, `tokenize`, `lexical_char_classes`, `lexical_casefolds`, `lexical_score`, `candidate_ids`, `decode_summary`, `select_blocks`, `vector_topk`, `centrality_prior`; classes `PostingsBuilder`, `LexicalBuilder`, `ContentMatcher`. Modules: `chunk.rs` (tree-sitter, ~60 grammars incl. markdown, `:29-34`), `grams.rs`, `lexical.rs` + `lexical_tables.rs` (frozen Unicode tables), `links.rs` (markdown refs), `postings.rs`, `signals.rs`, `vectors.rs` (cosine top-k, rayon past 4,096 rows), `verify.rs` (matcher).

### 1.9 Chunking (READ)

`models/chunking.py`: recursive character splitter + structure-aware tree-sitter spans through `chunk_spans`; `EXTENSION_TO_GRAMMAR` map; markdown is heading-hierarchical via `tree-sitter-md`; `split_notebook` routes Jupyter cells by kernel; surrogate/NUL scrub; `CHUNK_GENERATION` stamp law. Tests `tests/models/test_chunking.py`.

### 1.10 Renderers for binary bodies (READ)

- Formats: `pdf` (pypdf), `docx` (python-docx), `pptx` (python-pptx), `xlsx` (openpyxl) — `rendering/registry.py:44-46`, each behind its extra (`pyproject.toml:60-64`); images (spec 152 slice C) **not started**.
- Failure classification is a *state on the row*, never a raise: `RenderStatus` = `pending|ok|truncated|partial|empty|unsupported|unavailable|encrypted|corrupt|failed…` (`models/media.py:21-40`); the registry answers `unsupported` (no renderer), `unavailable` (extra missing, naming `vfs[<extra>]`), and `failure_from(exc)` → `failed` (`registry.py:99-110`, `seam.py:308-340`). `read` before reindex answers pending with an `unavailable` record (spec 152 AC). The render stage (`render.py`) runs first in reindex, keyset-paged, deduped by bytes hash, guarded stamp landing, generation-bump re-render. 40+ pins in `test_render.py`, format pins in `tests/rendering/test_renderers.py`.

### 1.11 graph and edges (READ)

`graph.py`: frontier walk, four methods (`inbound|outbound|neighborhood|meet`), rights judged on every hop at `list`/`read` (`ops.py:141` `Needs("read", traverse="list")`), induced edges, `limit` 128. Edge types today: reserved `fs` mirror (`models/edge.py:27`), extracted `links` from markdown (`models/links.py`, `storage/.../links.py`, 16 pins in `test_links.py` incl. an every-engine leg), and user-minted types via `mkedge`. `imports` is spec 147, status *seed*.

---

## 2. In flight

| Doc | Status line (READ) | What it would change in this domain |
|---|---|---|
| ADR 051 | accepted 2026-08-26; pin 2 withdrawn by 059 | Pin 1 ("one fused SQL statement") is **not** what is built — fusion is client-side (`glean.py:428 "fused": "client"`, per ADR 055). Status line does not say pin 1 was superseded. |
| ADR 052 | accepted | Convex fusion, MaxP, cross-mount rerank, harness with 0.005 gate — built. |
| ADR 053 | implemented by spec 136 | Signals/Ranker — built. |
| ADR 054 | accepted | Provider seam, identity on meta, embed as reindex step — built. |
| ADR 055 | accepted; client floor withdrawn | Block postings scored in Rust — built. |
| ADR 057 | accepted | One engine, no pure fallback — built; one stale docstring (below). |
| ADR 059 | accepted; pin 4 amended by 079 | Withhold only `glean` on the floor — built. |
| **ADR 060** | accepted 2026-08-27 | Says `FastEmbedEmbeddingProvider` with MiniLM joins `vfs.embedding` and `fastembed` joins `embed-local`; also "committed to" fixing the 120 s × 2,048-input timeout before the provider lands. **Neither has happened** (spec 137 archive `:221` confirms). |
| ADR 065 (+080) | accepted | Visible-set statistics — built; regression test for the leak not written. |
| ADR 077 | accepted 2026-10-12, reconciled 10-13 | Probe/`install_extensions` — built. |
| ADR 079 (+080) | accepted 2026-10-14 | graph as frontier walk — built (spec 164). |
| Spec 147 | seed, not scheduled | `imports` edges from Python import statements at reindex; needed for the centrality prior on code. |
| Spec 152 | slices A+B built, awaiting review; C (images), D (docs) not started | Image header renderer + `vfs[images]`; `docs/api.md`, how-to, reference pages. |
| Spec 155 | draft; folded into 167 §5 (ADR 085) | Render budget / readable scores — renderer layer, not storage. |
| Spec 159 | draft, narrowed 2026-10-08 | Render inline at `write` for ≤16 bytes rows / ≤8 MiB with a 5 s limit; outside the transaction. |
| Spec 179 | active | `SupportsGlean` on the kernel seam; `FEATURES` gains `lexical_index`/`vector_index`, drift test ties them to `glean_signals`. |
| Spec 171 | active | MCP adapter exposes `glean` as a tool — needs a provider configurable without a Python object (see gaps). |

---

## 3. Gaps vs the 0.1.0 goal (theme 3: a Vector Embedding Provider, glean uses BM25 + vector at query time)

Rating: **built / partial / planned / missing**.

| Item | Rating | Evidence |
|---|---|---|
| Query-time embedding of the query string | built | `backend.py:669-680` |
| BM25 + vector fused at query time, client-side, every supported engine | built | `glean.py:389`, `distance.py` |
| Provider configured on the mount (`DatabaseStorage(embedder=…)`) | built | `backend.py:198` |
| Provider configured per node / per path | missing (by design: one space per mount, ADR 054 pin 4) | — |
| Provider configurable by *name/URL/env* (needed by `serve()` and the CLI, themes 6/8) | missing | no registry/factory in `embedding/__init__.py` |
| Bounded batch embedding at reindex (inputs, tokens, pages, concurrency, lease) | built | `embed.py:112-134, 266-325` |
| Provider failure classification | built (`unavailable` retryable warning at reindex; `unavailable`/`conflict` records at glean) | `backend.py:617-652, 1470-1479` |
| Dimension/model pinning per mount on the meta row | built | `rows.py:648-651`, `engine.py:579-593` |
| Re-embed when the model changes (same width) | built | `backend.py:1421-1429` |
| Re-embed when the model changes to **another width on a native column** | missing (first touch refuses `invalid`, "re-provision the mount") | `engine.py:583-592` |
| Default local model per ADR 060 (fastembed MiniLM) | missing; code default is model2vec potion | `pyproject.toml:53`, `model2vec.py:91` |
| Timeout × batch-size fix ADR 060 committed to | missing | `embed.py:58`, `provider.py:42`, study finding 3 |
| Hybrid ordered top-10 pin on the four server engines | partial (sqlite + memory only; servers run the contract but no ordered hybrid pin) | `pins.py:66-83`, `test_harness.py:174-203` |
| Hybrid quality gate (fused ≥ BM25 baseline) with a real model | partial (recorded, not asserted) | `test_harness.py:226` |
| BEIR quality pin | partial (slow, skips when the cache is absent; absent in this env — EXECUTED) | `test_harness.py:126, 154-165` |
| Statistics-leak regression test (ADR 065) | missing | grep `tests/` |
| Vector leg freshness (unembedded rows absent until reindex; trait says `overlay`) | partial — the trait vocabulary cannot say "lexical overlay, vector reindex-only" | `glean.py:641`, `backend.py:295` |
| Tuned fusion default (study: fixed 50/50 hurts a strong leg) | planned (ADR 052 says the harness tunes α; nothing persists a per-provider default) | `ranking.py:111` |
| Docs: `docs/reference/api.md` has **no** glean section; no how-to for configuring an embedder | missing | EXECUTED `grep -c glean docs/reference/api.md` → 0 |
| Renderers pdf/docx/pptx/xlsx | built | `registry.py:46` |
| Image renderer (152 C), docs (152 D) | planned | spec 152 |
| Render at write (159) | planned | spec 159 |
| `imports` edges (147) | planned | spec 147 |
| graph in glean (a graph *leg*) | missing (only the stored prior; not required by theme 3) | — |

---

## 4. Risks: wrong, stale, or contradictory

1. **ADR 060 vs code** (READ). The accepted default local model is MiniLM through fastembed; the code ships model2vec potion as `embed-local` and no fastembed provider. The README/docs make no claim either way. Either build the provider or amend the ADR. The ADR's own "committed to" item — the 120 s per-request timeout against `LOCAL_BATCH_INPUTS=2048` — is unfixed: a local provider under ~17 chunks/s times out every page, the step ends `unavailable` with `unembedded > 0`, and the next reindex repeats the identical batch shape, so it never converges. Also `asyncio.wait_for` cannot cancel the executor thread a `LocalEmbeddingProvider` hops to (`provider.py:134-137`), so the worker keeps computing after the timeout (INFERRED from asyncio semantics).
2. **Stale docstring contradicting ADR 057** (READ `models/chunking.py:38-42`): "A pure-Python install carries no tree-sitter at all, so every extension takes the recursive character splitter there — a declared, tested degradation". There is no pure-Python install.
3. **Architecture page 01 term table** says the generic floor "withholds `glean` and `graph` (ADR 059)" (READ `01-vfs-at-a-glance.md`, Terms table); ADR 079 and `backend.py:284` withhold only `glean`. Page 08 is correct.
4. **ADR 051 pin 1** ("one fused statement … `UNION ALL` + `GROUP BY` fusion in SQL") is not the built design (client-side fusion per ADR 055); ADR 051's status line records only pin 2's withdrawal. A reader of 051 alone gets the wrong architecture.
5. **Hybrid determinism is pinned only where cosine is sqlite-vec's** (READ `pins.py`, `test_harness.py`). The engine-cosine parity on Postgres/MSSQL/Oracle/MariaDB is proven by the contract's hybrid glean tests (spec 179's table names 11 glean + 3 embed contract tests), but an *ordered* hybrid pin on the servers does not exist, so a float-accumulation drift inside an engine's distance function would not be caught as a reorder.
6. **Width-change migration is a re-provision** on native columns (`engine.py:583-592`): swapping `text-embedding-3-small@1536` for a 1024-d model on Postgres refuses every verb until the host drops the mount. ADR 054 promised "model swap is a re-embed by the verb that owns regeneration"; that holds only at equal width.
7. **BEIR gate may never run in CI** (INFERRED): the corpus is downloaded to a user cache and the tests skip when absent; nothing in `scripts/ci.sh` fetches it. The quality gate that exists in CI is the 200-doc golden set.
8. **The `glean_staleness` trait over-promises for the vector leg**: `overlay` is true for BM25 only; a freshly written file is found lexically and absent from the vector leg until reindex (`glean.py:641`).
9. **Fixed Convex 50/50** (study finding 4): on scifact OpenAI vector-only 0.7659 > fused 0.6934. The `Ranker` is settable, but no provider-aware default or documented tuning path exists.
10. **Stored signals may count hidden in-links** (`open-questions.md:314-319`); off by default — not a 0.1.0 blocker unless signals are turned on by default.
11. **Rendering tests import their extras at module top** (`tests/rendering/test_renderers.py:8` `import docx`; EXECUTED collection error here). Fine under `uv sync --all-extras`, but a `uv sync` without extras breaks collection of two modules rather than skipping them.
12. Partial-view glean cost grows with corpus-wide `df` (`glean.py:720-725`, open question) — correct, acknowledged, not capped.

---

## 5. Proposed roadmap stories

### S1. Settle the default local embedder (ADR 060 vs model2vec)
**Why.** The accepted decision and the shipped code disagree. Theme 3 needs one documented "pip install vfs-py[embed-local]; DatabaseStorage(embedder=LocalEmbedder())" answer. Two lawful outcomes: (a) build `FastEmbedEmbeddingProvider` (MiniLM, 384-d, ONNX Runtime, ~100 MB of wheels incl. numpy in the extra only) as ADR 060 says; (b) amend ADR 060 to make potion-base-8M the default and keep fastembed as a documented LangChain route. The study measured MiniLM fused 0.7998 vs potion 0.7809 on vfs_native, 0.6903 vs 0.6583 on scifact; potion is ~15× faster to embed and 3× lighter. **Depends on.** Clay's decision (Q1). S2 if (a). **Acceptance.**
- `vfs.embedding` exports exactly the providers the ADR names; `pyproject.toml` `embed-local` lists their packages; `tests/embedding/test_provider.py::test_every_provider_satisfies_the_seam` covers each.
- The provider's `model_id` is `provider/model@dim` and the identity pin in `tests/ranking/test_embedders.py` records its digest for `PIN_SENTENCE`; the test skips (printed reason) when the model is not cached, never downloads.
- `README.md` and a new `docs/how-to/configure-an-embedding-provider.md` show the one-line opt-in; the docs fence test (Sybil) executes the snippet against `InMemoryStorage`.
- ADR 060's status line records the outcome; no stale "fastembed" claim remains in `context/` living pages (`grep -rn fastembed context/architecture docs` is empty or points at the ADR).

### S2. The embed step converges for slow providers (the ADR 060 committed-to fix)
**Why.** `EMBED_TIMEOUT_SECONDS=120` is per request and `LOCAL_BATCH_INPUTS=2048`; any provider under ~17 chunks/s never lands a vector and every rerun repeats the same failure. A hosted provider's 2,048-input batch at a low tier has the same shape. **Depends on.** none. **Acceptance.**
- A `ScriptedProvider` whose per-input latency makes a 2,048-input batch exceed the timeout still finishes `reindex` with `unembedded == 0` (the step halves the batch, or budgets time per input — design choice recorded in `embed.py`'s docstring); assert on the request count, not the clock.
- A batch that times out is retried at a smaller size at most `log2(max_batch_inputs)` times before the step records `unavailable`; the count of requests issued is pinned.
- `LocalEmbeddingProvider.max_batch_inputs` defaults to a value the memo justifies (≤ 256) and the pin in `tests/embedding/test_provider.py::test_the_declared_caps` is updated.
- A timed-out local batch never leaves a worker thread computing past the next page: the page waits for the hop's future (or the hop is cancelled cooperatively), pinned by counting `embed_batch` calls after the timeout.
- The `embedding` extra gains `retried` (batches shrunk) so operators can see it.

### S3. Provider configuration by name for `serve()`, the CLI and ETL configs
**Why.** Themes 6 and 8 cannot pass a Python object. A small registry — `embedder_from_spec("model2vec:minishlab/potion-base-8M")`, `"openai:text-embedding-3-small@1024"`, `"hash:64"`, `"langchain:<dotted factory>"` — plus env-var resolution of API keys gives one spelling for `DatabaseStorage(embedder=…)`, the MCP server's mount table, and a config file. Keep the object form. **Depends on.** S1; spec 171 (MCP) for the consumer. **Acceptance.**
- `vfs.embedding.embedder_from_spec` parses the four schemes; an unknown scheme or a malformed `@dim` raises `ValueError` naming the schemes (construction time, never a `Result`).
- `openai:` resolves the client from `OPENAI_API_KEY` and refuses `ValueError` when it is absent; the test uses a fake transport and sets the env var with `monkeypatch`.
- `model2vec:` without the extra raises the classified `ImportError` naming `vfs-py[embed-local]` (existing test extended).
- The resulting provider's `model_id` equals what the object form gives for the same arguments (one parametrized test per scheme).
- `docs/how-to/configure-an-embedding-provider.md` documents the grammar.

### S4. Hybrid determinism and quality pins on every engine
**Why.** Theme 3 is "BM25 + vector at query time" on SQLite, Postgres, MSSQL and Oracle (theme 2). The ordered hybrid pin runs only on sqlite + memory; server engines run the contract but no ordered pin. ADR 051 promised byte-identical rankings on all five engines. **Depends on.** none (engine legs via `db_test`). **Acceptance.**
- `tests/ranking/test_harness.py` gains `test_the_hybrid_ordered_top10_pin_holds_on_a_server(env_var)` parametrized over `ENGINE_LEGS`, asserting `top10_hybrid.json` through the verb on a server mount carrying the 64-d hashing embedder; deselected when the URL is unset.
- A fused-arm gate on vfs_native: with the potion model cached, `ndcg@10(fused) >= ndcg@10(bm25) - GATE`; skips with a printed reason when the model is absent.
- `test_vector_leg.py::TestReferee` runs on each engine leg: the engine's top-`depth` order equals `cosine_topk`'s over the same rows (count the rows compared, not time).
- The `legs` extra on each server reports `tier` ∈ {`native_exact`, `native_ann`} as the profile declares (`mssql` exact, `oracle`/`mariadb`/`postgresql` ann when indexed).

### S5. Width change is a migration, not a re-provision
**Why.** ADR 054 pin 4 promised "reindex is the migration". At equal width it is; at a new width on a native column first touch refuses `invalid` and names re-provisioning. A host that upgrades from a 1536-d to a 1024-d model should run `reindex`, not drop the mount. **Depends on.** none. **Acceptance.**
- A mount stamped `openai/text-embedding-3-small@1536` reconfigured with a 1024-d provider: first touch succeeds with a `conflict` record (`reason="stale_identity"`), glean serves lexical-only, and `reindex` rebuilds the vector column at the new width (per-dialect DDL under the lease: `ALTER … TYPE vector(1024)` on Postgres; drop-and-add on MSSQL/MariaDB/Oracle), clears vectors, re-embeds and re-stamps. Pinned on sqlite (packed column, no DDL) and on each engine leg by reading the column width from the live catalog.
- The pgvector index is recreated at the new width; `test_sqlite_vec.py` style pins cover `permission_denied` when the role may not alter.
- `engine.py:583-592` no longer refuses on width; `test_embed.py::test_a_stored_width_other_than_the_native_columns_refuses_at_first_touch` is replaced by the migration pin.
- Statement count of the migration is pinned (one DDL + one clear + the embed step's pages).

### S6. Close the ADR 065 paperwork: the statistics-leak regression test and the trait truth
**Why.** ADR 065 asked for S2's leak scripts to become a regression test; the visible lexicon exists but nothing asserts that a hidden row cannot move a visible score. Separately the `glean_staleness` trait should not claim overlay for the vector leg. **Depends on.** none. **Acceptance.**
- A test writes a corpus, hides half from `bob`, and asserts that for every probe term `result.lexical_stats["terms"][t]["df"]` and every visible row's score are identical whether the hidden half exists or has been deleted (two mounts, same visible rows); the hidden count is unrecoverable from `n_docs`.
- Under the clause fan (generic floor profile) the same assertion holds (the fan merges per clause).
- `traits()` gains or refines a key so `glean_staleness` reads `overlay` for the lexical leg and the vector leg's staleness is declared (`reindex`); `storage/protocol.py`'s vocabulary and its drift test are updated; spec 179's `FEATURES` drift test agrees.
- `docs/reference/api.md` states it.

### S7. glean reference docs and the embedder how-to (spec 152 slice D's search half)
**Why.** `docs/reference/api.md` has no glean section; the README promises hybrid search. 0.1.0 is the first version anyone is asked to depend on (spec 166). **Depends on.** S1, S3. **Acceptance.**
- `api.md` documents `glean` parameters, the records (`no_provider`, `stale_identity`, `embed_failed`, `truncated`), the `legs` and `lexical_stats` extras, `Ranker`/`Convex`/`RRF`/`Signal`, and `install_extensions`.
- The how-to shows SQLite (sqlite-vec, nothing to install), Postgres (`CREATE EXTENSION` or `install_extensions()`), MSSQL 2025 and Oracle 23ai prerequisites.
- Every fenced example executes under the Sybil docs gate in `scripts/ci.sh`.

### S8 (optional for 0.1.0). Fusion weights the harness tunes and a provider can declare
**Why.** Study finding 4: equal weights drag a strong leg down; the right α is corpus- and model-dependent. Minimal form: let a provider declare a suggested `fusion_weight`, keep `Ranker` the authority, and record per-model α in the harness. **Depends on.** S4. **Acceptance.** `Ranker()` with no explicit fusion reads the provider's suggestion when present else 0.5; the hybrid pin is re-recorded; the harness's `optimize_fusion` output is checked into `tests/fixtures/ranking/` for hash and potion.

### S9 (not needed for theme 3; Clay's call). Render at write (spec 159), images (152 C), imports edges (147)
These are independent of the embedding theme. 159 matters once agents upload PDFs through the MCP server and expect `grep` to work before a `reindex`; 147 matters once signals are on by default for code corpora.

**Minimal set that makes theme (3) true for 0.1.0:** S1 + S2 + S3 + S4 + S7 (S5 and S6 are strongly recommended; S8/S9 optional).

---

## 6. Open questions for Clay

1. **Default local model**: honour ADR 060 (build fastembed/MiniLM, numpy in the extra) or amend it to model2vec potion (already shipped, 3× lighter, ~2 nDCG points behind)?
2. **Is a width change a migration vfs performs (DDL under the reindex lease) or an operator re-provision?** Today it is the latter on native columns.
3. **Provider spelling for `serve()`/config**: a URL-ish scheme (`openai:text-embedding-3-small@1024`), a dotted factory path, or both? Where do API keys come from (env only)?
4. **Should `0.1.0` ship a tuned fusion default per provider, or stay at Convex 50/50 with the knob documented?**
5. **Does the vector leg need an overlay for 0.1.0** (embed dirty chunks at query time under a small budget), or is "lexical overlay, vector at reindex" acceptable if the trait says so?
6. **BEIR in CI**: fetch the corpus in `scripts/ci.sh`/CI cache so the slow quality gate actually runs, or accept the 200-doc golden set as the only CI gate?
7. **Render at write (159)** — in or out of 0.1.0? It is the one renderer story an MCP-served agent will notice.
8. **Signals on by default?** If yes, the hidden-in-link leak (open question) must be studied first.
