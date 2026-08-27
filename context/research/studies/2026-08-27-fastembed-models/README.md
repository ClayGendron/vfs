# fastembed models for the local embedding default

**Question.** Should vfs's recommended local embedding model be
`sentence-transformers/all-MiniLM-L6-v2` served through fastembed — or a
newer small model (bge, arctic, jina), or a hosted flagship (OpenAI
text-embedding-3-large)? Measured on our own harness: time to embed,
time to answer a query, and ranking quality alone and fused with the
BM25 lexical leg.

**Sources.** fastembed clone refreshed to `c48247f` (origin/main,
2026-08-19) on 2026-08-27 — license Apache-2.0, re-checked after
refresh. Published MTEB Retrieval numbers from the arctic-embed README
(Snowflake-Labs/arctic-embed). All benchmarks run in-session on Apple
Silicon (macOS, CPython 3.13, `bench_fastembed.py` in this directory);
OpenAI arms against the live API, dimensions=1024.

## What fastembed pulls in

28 packages, ~100 MB installed: `onnxruntime` (inference), `tokenizers`,
`numpy`, `huggingface-hub` (model downloads), `pillow` (image models),
`loguru`, `mmh3`, `py-rust-stemmers`, plus the requests/httpx stack. No
torch, no transformers — a fraction of sentence-transformers' footprint,
heavier than model2vec (~30 MB).

## The survey: small dense models fastembed serves

| Model | dim | size | MTEB Retrieval | served as |
|---|---|---|---|---|
| all-MiniLM-L6-v2 | 384 | 0.09 GB | 41.95 | fp32 |
| BAAI/bge-small-en-v1.5 | 384 | 0.067 GB | 51.68 | **int8 only** (`qdrant/*-onnx-q`) |
| snowflake-arctic-embed-xs | 384 | 0.09 GB | 50.15 | fp32 |
| snowflake-arctic-embed-s | 384 | 0.13 GB | 51.98 | fp32 |
| jinaai/jina-embeddings-v2-small-en | 512 | 0.12 GB | — | fp32 |
| BAAI/bge-base-en-v1.5 | 768 | 0.21 GB | 53.25 | **int8 only** |

On paper bge-small and arctic beat MiniLM by ~10 MTEB points. The
benchmark says that advantage does not survive contact with a CPU or
with fusion — see the findings.

## Results

Harness: `tests/ranking` golden corpora, glean through the verb, Convex
50/50 fusion, nDCG@10 via ranx. vfs_native = 200 docs / 1,540 chunks /
40 queries; scifact = 5,183 docs / 6,324 chunks / 300 queries. Full
numbers in `results.json`.

### vfs_native (BM25 baseline 0.7589)

| Arm | embed | chunks/s | vector-only | fused 50/50 | query mean |
|---|---|---|---|---|---|
| hash (floor) | 0.4 s | ~3,900 | 0.3150 | 0.7692 | 26 ms |
| potion (model2vec) | 0.9 s | ~1,700 | 0.5765 | 0.7809 | 24 ms |
| **MiniLM-L6-v2** | 12.7 s | 122 | 0.6273 | **0.7998** | 36 ms |
| arctic-xs | 62.5 s | 25 | 0.6925 | 0.7786 | 28 ms |
| arctic-s, jina-small | >120 s | ~13 | — | invalid¹ | — |
| OpenAI 3-large @1024 | 6.8 s² | API | 0.7393 | 0.7959 | 334 ms |

### scifact (BM25 baseline 0.6580)

| Arm | embed | vector-only | fused 50/50 | query mean |
|---|---|---|---|---|
| hash (floor) | 1.4 s | — | 0.5612 (hurts) | 38 ms |
| potion | 0.8 s | — | 0.6583 | 34 ms |
| **MiniLM-L6-v2** | 35 s | 0.6233 | **0.6903** | 48 ms |
| OpenAI 3-large @1024 | 61 s² | **0.7659** | 0.6934 | 337 ms |

¹ arctic-s and jina-small exceeded the embed step's 120 s per-call
timeout on 2,048-input batches; vectors never landed and their "fused"
runs were lexical-only (finding 3). Their honest quality is unmeasured;
their speed alone (~13 chunks/s) disqualifies them as a default.
² API wall time with 4 concurrent batches, not local compute.

## Findings

1. **MiniLM wins the local tier on both corpora.** Best fused quality
   (0.7998 / 0.6903) *and* the fastest real transformer (~120 chunks/s
   CPU). The newer models' MTEB lead did not show up here: arctic-xs
   embeds 5x slower (512-token window vs MiniLM's 256) and fused
   *below* MiniLM on vfs_native.
2. **The bge trap: fastembed serves bge only int8-quantized**, and
   quantized ONNX crawls on macOS ARM — measured 4.3 docs/s vs
   MiniLM's 114.5 (27x). Via fastembed on Apple Silicon, bge is
   unusable regardless of its MTEB score.
3. **The timeout bug (product finding).** The embed step's per-call
   timeout (120 s) meets `LOCAL_BATCH_INPUTS` = 2,048 inputs per call:
   any embedder slower than ~17 chunks/s times out, vectors silently
   never land, and glean degrades to lexical-only with only a warning
   record. The bench worked around it by declaring
   `max_batch_inputs = 256` on the provider; the product fix (scale
   the timeout with batch size, or a smaller local default) is open.
4. **Fixed 50/50 fusion leaves quality on the table (feeds spec 136).**
   On scifact, OpenAI vector-only (0.7659) beats its own fused arm
   (0.6934): equal weights drag a strong leg toward a weaker one. On
   vfs_native the reverse holds — fusion is the best arm for every
   model. Which leg deserves weight is corpus-dependent; a fixed split
   cannot know.
5. **MiniLM alone never beats BM25** (0.6273 / 0.6233, both under the
   lexical line). Its value is entirely inside the fusion — the hybrid
   design is earning its keep.

## Conclusion

`sentence-transformers/all-MiniLM-L6-v2` through fastembed is the
default local model — decided in ADR 060. Hash (in-memory) and none
(database) stay the zero-install defaults so installing an extra never
silently re-identifies a space.

## Addendum: GPU embedding on Apple Silicon (M-series) — measured

Asked 2026-08-27, in two rounds: can fastembed use the M-series GPU,
and — dropping the fastembed constraint — can the Mac GPU batch and
parallelize embedding at all? MiniLM, 200 vfs_native docs (x5 = 1,000
inputs for the bulk runs), this machine.

**Inside fastembed (ONNX Runtime), the GPU path makes it slower.** The
stock onnxruntime macOS wheel ships `CoreMLExecutionProvider` and
fastembed accepts `providers=[...]`, but CoreML fragments the graph —
20-38 partitions, only 209-292 of 323 nodes eligible, a CPU-GPU
transfer at every boundary — and MiniLM's dynamic sequence lengths
violate CoreML's fixed-shape rule ("unbounded dimension is not
supported"), bouncing subgraphs back to CPU at runtime. Every CoreML
config measured ~37 docs/s vs 112 docs/s plain CPU. The only ONNX
route around it is a static-shape re-export (pad everything to 256) —
upstream model surgery fastembed does not do. `fastembed-gpu` is
CUDA-only.

**Outside fastembed, the GPU delivers ~3x on bulk.** Runtimes that put
the whole graph on Metal, same model and texts:

| runtime | bulk (best batch) | single query | notes |
|---|---|---|---|
| fastembed / ONNX CPU | 112 docs/s | 9.8 ms | the shipped default |
| torch CPU (sentence-transformers) | 156 docs/s (b128+) | 6.9 ms | torch's ARM kernels beat ONNX here |
| **torch MPS** (sentence-transformers) | **344 docs/s** (b256) | 25.3 ms | full torch/transformers stack |
| **MLX** (mlx-embeddings 0.1.0) | **302 docs/s** (b128) | 19.3 ms | 54 pkgs incl. transformers + mlx-audio/vlm; no torch |

Bulk scales with batch size on the GPU exactly as intuition says; the
single query flips the other way — kernel dispatch overhead makes a
batch of one 2-3x *slower* than CPU.

**Implications.** For the agent loop (one query, small dirty sets) the
CPU default is the right one on every axis. For Mac-local bulk ingest
a GPU runtime is a real ~3x, but it means a second runtime dependency
(torch, or the mlx stack) for one platform's bulk path — left as a
possible future `embed-mps`/`embed-mlx` provider behind its own extra,
no decision taken. Within fastembed itself, the CPU default stands:
no GPU knob is warranted there.
