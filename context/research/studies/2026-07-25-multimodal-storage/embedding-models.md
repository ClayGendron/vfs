# Study: the multimodal embedding model landscape, 2025–2026 ground truth

- **Date**: 2026-07-25
- **Brief**: [2026-07-25-multimodal-storage-and-search-brief.md](../../2026-07-25-multimodal-storage-and-search-brief.md),
  search questions 7–10, especially **question 8** (which models, what
  dimensions/costs, one joint space vs multiple spaces per corpus).
- **Method**: online primary sources only — official model docs, vendor
  blogs, Hugging Face model cards, arXiv papers, benchmark leaderboards.
  Every claim carries a URL. Local repo citations only for vfs's own
  `Vector` machinery.

---

## 1. Interleaved text+image single-vector embedders

These are the models that make `glean` over a mixed corpus plausible: one
API call takes text, images, or an interleaved sequence of both, and
returns one vector in one joint space. All of the 2025–2026 generation are
**true interleaving** models (a single VLM tower attending across
modalities), not CLIP-style dual towers — the vendors explicitly position
this against CLIP's separate-encoder design
([Voyage](https://docs.voyageai.com/docs/multimodal-embeddings),
[Jina v4 paper](https://arxiv.org/abs/2506.18902)).

### Summary table

| Model | Released | Inputs | Dims (default / Matryoshka) | Max input | Price | License / access |
|---|---|---|---|---|---|---|
| voyage-multimodal-3 | 2024-11 | interleaved text+image | 1024 | 32K tokens; ≤16M px/image | $0.12/M text tokens; $0.60/B pixels | proprietary API |
| voyage-multimodal-3.5 | 2026-01 | interleaved text+image+**video** | 1024 / 256, 512, 2048 | 32K tokens; 20 MB per image/video; 1,000 inputs/request | same as above | proprietary API |
| Cohere embed-v4.0 | 2025-04 | interleaved text+image (incl. PDF pages) | 1536 / 256, 512, 1024 | 128K tokens; ≤2M px/image | $0.12/M text tokens; $0.47/M image tokens | proprietary API (Cohere, AWS, Azure) |
| jina-embeddings-v4 | 2025-06 | text+image+PDF, interleaved; dual single-/multi-vector | 2048 / 128–2048; or 128-d per token | 32K tokens | API + open weights | weights **Qwen Research License (non-commercial)** |
| jina-clip-v2 | 2024-11 | text OR image (dual tower, CLIP-style) | 1024 / down to 64 | 512×512 images; 89 languages | API + open weights | weights **CC-BY-NC-4.0** |
| Gemini Embedding 2 (`gemini-embedding-2-preview`) | 2026-03 | text+image+**video+audio+PDF**, interleaved | 3072 / 128–3072 (768/1536/3072 recommended) | 8,192 tokens; 6 images; 120 s video; 6-page PDF per request | preview, pricing TBA (text-only `gemini-embedding-001` is $0.15/M) | proprietary API (Gemini API, Vertex) |
| nomic-embed-multimodal-7b | 2025-04 | interleaved text+image | single-vector | — | self-host | **Apache-2.0**, weights+data+code open |
| TwelveLabs Marengo 3.0 | 2025-12 GA | video+audio+image+text, one space | **512** | 4-hour videos | Bedrock / TwelveLabs API | proprietary API |

### Per-model notes

**Voyage voyage-multimodal-3 / 3.5.** The 2024 model established the
interleaved-input, screenshot-native pitch: "vectorizing interleaved
texts + images and capturing key visual features from screenshots of
PDFs, slides, tables, figures … eliminating the need for complex document
parsing", claiming +19.63% average retrieval accuracy over the next-best
multimodal model across 20 datasets
([announcement](https://blog.voyageai.com/2024/11/12/voyage-multimodal-3/)).
The January 2026 successor **voyage-multimodal-3.5** adds video input and
Matryoshka output (256/512/1024/2048), keeps the 32K context, and allows
1,000 inputs per request
([docs](https://docs.voyageai.com/docs/multimodal-embeddings),
[announcement](https://blog.voyageai.com/2026/01/15/voyage-multimodal-3-5/)).
Pricing: $0.12/M text tokens plus $0.60 per **billion pixels**; the
matching text model voyage-3.5 is $0.06/M tokens — the multimodal model
costs 2× per text token
([pricing](https://docs.voyageai.com/docs/pricing)).
The decisive fact for question 8: Voyage evaluated 3.5 on a 38-dataset
text retrieval suite and reports it **within 0.29% of voyage-3-large**,
their flagship text embedder
([announcement](https://blog.voyageai.com/2026/01/15/voyage-multimodal-3-5/)).

**Cohere embed-v4.0** (April 2025). Unified embeddings from mixed text+
image input, 128K context (whole long documents in one vector), Matryoshka
256/512/1024/1536, images to 2M pixels
([changelog](https://docs.cohere.com/changelog/embed-multimodal-v4),
[Azure catalog](https://ai.azure.com/catalog/models/embed-v-4-0)).
Pricing $0.12/M text tokens, $0.47/M image tokens
([EmbeddingCost](https://embeddingcost.com/cohere)). Third-party spec
sheets put its MTEB text score at ~65.2, ahead of OpenAI
text-embedding-3-large (64.6)
([pythonalchemist](https://www.pythonalchemist.com/embeddings/cohere-embed-v4))
— i.e. its text-only quality is competitive with dedicated text
embedders, though below the MTEB frontier (~68).

**Jina jina-embeddings-v4** (June 2025). 3.8B parameters on a
Qwen2.5-VL-3B-Instruct base; the interesting architecture: **one model,
two output modes** — a 2048-d single vector (Matryoshka-truncatable to
128) via mean pooling, and 128-d-per-token multi-vectors for
ColBERT-style late interaction, switchable per call; task-specific LoRA
adapters for retrieval / semantic similarity / code
([paper](https://arxiv.org/abs/2506.18902),
[model page](https://jina.ai/models/jina-embeddings-v4/)).
The paper reports multi-vector mode consistently 7–10% better than
single-vector on visual tasks (ViDoRe 90.17 vs 84.11)
([paper](https://arxiv.org/html/2506.18902v2)). But its MTEB-en score is
**55.97** ([model page](https://jina.ai/models/jina-embeddings-v4/)) —
far below dedicated text embedders (frontier ~68) — the clearest
counter-example to "one space for everything". Open weights are under
the **Qwen Research License — non-commercial**; commercial use is
API-only ([HF card](https://huggingface.co/jinaai/jina-embeddings-v4)).
The older **jina-clip-v2** (0.9B, dual-tower CLIP-style, 1024-d
Matryoshka to 64, 89 languages, 512×512 images) is likewise
**CC-BY-NC-4.0** ([announcement](https://jina.ai/news/jina-clip-v2-multilingual-multimodal-embeddings-for-text-and-images/),
[HF card](https://huggingface.co/jinaai/jina-clip-v2)).

**Google Gemini Embedding 2** (`gemini-embedding-2-preview`, public
preview 2026-03-10). The first frontier-lab *natively multimodal*
embedder: text, images, video, audio, and PDFs into **one 3,072-d
space**, with interleaved multi-modality inputs in a single request;
MRL truncation to any size 128–3,072 (768/1536/3072 recommended). Caps
per request: 8,192 text tokens, 6 images, 120 s of video, 6-page PDFs;
audio is ingested natively, no transcription step
([Google announcement](https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-embedding-2/),
[Gemini API docs](https://ai.google.dev/gemini-api/docs/models/gemini-embedding-2-preview)).
Its text-only MTEB score is reported at 67.99–68.17 vs 68.32 for the
text-only `gemini-embedding-001` — effectively parity
([Milvus comparison](https://milvus.io/blog/choose-embedding-model-rag-2026.md)).
The two models' spaces are **incompatible** — migrating means
re-embedding the corpus
([Vertex docs](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/embedding-2)).
`gemini-embedding-001` (text-only) prices at $0.15/M tokens, $0.075/M
batch ([pricing](https://ai.google.dev/gemini-api/docs/pricing)).

**Nomic nomic-embed-multimodal / colnomic-embed-multimodal (3B/7B)**
(April 2025). The open-weights option: directly encodes interleaved
text+images; the single-vector `nomic-embed-multimodal` variants trade
accuracy for storage; the multi-vector `colnomic` variants score 61.2
(3B) and 62.7 (7B) NDCG@5 on ViDoRe-v2 — state of the art among open
models at release. **7B is Apache-2.0** with weights, training data, and
code released; the 3B inherits a research-only base-model license
([Nomic announcement](https://www.nomic.ai/news/nomic-embed-multimodal),
[HF 7B card](https://huggingface.co/nomic-ai/colnomic-embed-multimodal-7b)).

**Also in the field**: Qwen3-VL-Embedding (open, 8B scores 67.9 MMTEB —
"on par with similarly sized text-only embedding models" but slightly
below the text-only Qwen3 embedders,
[paper](https://arxiv.org/pdf/2601.04720)); VLM2Vec-V2 (research,
videos+images+visual documents,
[paper](https://arxiv.org/pdf/2507.04590)).

---

## 2. Late-interaction document-image retrieval (ColPali lineage)

### The shape

ColPali (July 2024) reframed document retrieval: instead of
OCR → layout analysis → chunking → text embedding, feed the **page
image** to a vision-language model and keep **one embedding per image
patch**, scoring queries ColBERT-style — each query token takes its max
similarity over all page patches (MaxSim), summed
([paper](https://arxiv.org/pdf/2407.01449)).

Why it wins on visually rich documents: on the ViDoRe v1 benchmark,
ColPali scored **NDCG@5 = 81.3 vs 67.0** for the best
text-extraction pipeline (OCR + captioning + text embedder)
([paper](https://arxiv.org/pdf/2407.01449),
[reproducibility study](https://arxiv.org/pdf/2505.07730)). Tables,
figures, charts, and layout carry meaning OCR discards; the patch grid
keeps it. Indexing is also simpler and faster — no OCR stage at all.

### The cost model — a real schema consequence

The price is **storage amplification**. Standard ColPali emits ~**1,024
patch vectors per page** (32×32 grid at 448×448 input), each 128-d;
at float16 that is **256 KB per page**, i.e. ~1 billion vectors for a
1M-page corpus
([ColPali methodology](https://www.emergentmind.com/topics/colpali-methodology),
[Mixpeek guide](https://mixpeek.com/guides/late-interaction-retrieval),
[Qdrant](https://qdrant.tech/blog/qdrant-colpali/)).
Compare: one 1024-d float32 single vector is 4 KB/page — a **~64×**
difference. A schema that assumes "one vector per chunk" cannot hold a
late-interaction index; it needs a multi-row (chunk_id, vector_seq,
vector) shape or an opaque packed-blob column, plus MaxSim scoring that
no SQL vector type provides natively (Qdrant/Vespa implement
multi-vector MaxSim; SQL engines' vector columns are single-vector
top-k).

Compression is an active research line, not a solved default:
Light-ColPali/ColQwen2 clusters patch vectors hierarchically, retaining
up to 98.2% of accuracy at far lower footprint
([Light-ColPali](https://www.emergentmind.com/topics/light-colpali-colqwen2));
training-free pruning ("structural anchor pruning") is a 2026 topic
([arXiv](https://arxiv.org/pdf/2601.20107)).

### Lineage, licenses, current leaderboard

- **ColQwen2** (vidore/colqwen2-v1.0): Qwen2-VL-2B backbone under
  **Apache-2.0**, LoRA adapters under **MIT** — commercially usable
  open weights
  ([HF card](https://huggingface.co/vidore/colqwen2-v1.0)).
- **ColNomic 7B**: Apache-2.0, ViDoRe-v2 62.7 NDCG@5
  ([Nomic](https://www.nomic.ai/news/nomic-embed-multimodal)).
- **jina-embeddings-v4 multi-vector mode**: strongest published ViDoRe
  numbers (90.17 v1 avg) but non-commercial weights
  ([paper](https://arxiv.org/html/2506.18902v2)).
- **ViDoRe v3** (2026, ILLUIN + NVIDIA; 10 datasets, 26K+ pages,
  6 languages): as of Feb 2026 the leader is
  nemotron-colembed-vl-8b-v2 at **NDCG@10 = 63.42**; even top
  late-interaction models stay **under 65** — harder enterprise queries
  (multi-hop, open-ended, non-textual) remain unsolved
  ([Nemotron ColEmbed V2](https://arxiv.org/pdf/2602.03992),
  [ViDoRe benchmarks overview](https://www.emergentmind.com/topics/vidore-benchmarks),
  [ViDoRe v2 paper](https://arxiv.org/pdf/2505.17166)).

Takeaway for vfs: late interaction is the quality frontier for
"documents as images" (PDF pages, slides, scans) and specialized
late-interaction models **beat general single-vector multimodal
embedders on that task** ([DRAG assessment](https://arxiv.org/pdf/2508.03644)).
But its multi-vector storage shape is a different animal from the
one-vector-per-chunk schema, and its scoring operator (MaxSim) is not
expressible as a portable SQL vector query. It should be treated as an
*optional, pluggable index shape*, not the default glean path.

---

## 3. Audio: is there a production text+audio joint space?

**Partial yes, with a sharp caveat.** Two production systems now ingest
audio natively into a joint space with text:

- **Gemini Embedding 2** embeds audio directly ("native ingestion
  without transcription") into the same 3,072-d space as text/image/video
  ([Google](https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-embedding-2/)) — preview status.
- **TwelveLabs Marengo 3.0** (GA Dec 2025, Amazon Bedrock) embeds
  video, audio, image, and text into one 512-d latent space
  ([TwelveLabs](https://www.twelvelabs.io/blog/marengo-3-0),
  [Bedrock docs](https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-marengo.html)).

But benchmark ground truth says joint audio-text spaces are only good at
*acoustic* semantics. **MAEB** (Massive Audio Embedding Benchmark, 2026;
30 tasks, 50+ models) finds contrastive audio-text (CLAP-lineage) models
"perform excellently on environmental sound classification but score
near random on multilingual speech tasks", while speech-specialized
models show the inverse — "models excelling on acoustic understanding
often perform poorly on linguistic tasks, and vice versa", with **no
single architecture bridging both**
([MAEB](https://arxiv.org/abs/2602.16008)). CLAP research remains active
(M2D-CLAP, GLAP,
[overview](https://www.emergentmind.com/topics/contrastive-language-audio-pretraining))
but is about sound/music semantics, not spoken content.

**Honest 2026 answer**: for *what was said* (meetings, podcasts, voice
notes — the dominant agent use case), **transcribe-then-embed-text
(Whisper-style ASR → text embedder) is still the right pipeline**, and it
lands in vfs's existing derived-text sidecar story (brief question 6) —
the transcript is greppable and gleanable with zero new machinery. A
CLAP-style or Gemini-2 audio vector is an *additional* space worth
having only for acoustic search ("find the clip with breaking glass").

---

## 4. Video

Same pattern, one notch behind audio. Production options exist:
voyage-multimodal-3.5 accepts video inputs (20 MB cap,
[docs](https://docs.voyageai.com/docs/multimodal-embeddings)); Gemini
Embedding 2 takes up to 120 s of video per request
([docs](https://ai.google.dev/gemini-api/docs/models/gemini-embedding-2-preview));
Marengo 3.0 is the specialist — up to 4-hour videos, temporal segment
embeddings, all in its own 512-d space
([TwelveLabs](https://www.twelvelabs.io/blog/marengo-3-0)). Research
(VLM2Vec-V2) is unifying video with visual documents
([paper](https://arxiv.org/pdf/2507.04590)). The practical fallback
mirrors audio: keyframe extraction (image path) + transcript (text
path) as derived sidecars, with a native video space as an optional
extra.

---

## 5. Question 8 settled: one space or many?

**Claim tested**: can one corpus live in ONE joint space — do multimodal
embedders embed pure text well enough to retire the text embedder?

**Evidence for "one space is now viable" (text+image only):**

- voyage-multimodal-3.5 within **0.29%** of voyage-3-large (their best
  text model) on a 38-dataset text retrieval suite
  ([Voyage](https://blog.voyageai.com/2026/01/15/voyage-multimodal-3-5/)).
- Gemini Embedding 2 at 67.99–68.17 MTEB vs 68.32 for the dedicated
  text model — parity
  ([Milvus](https://milvus.io/blog/choose-embedding-model-rag-2026.md)).
- Cohere embed-v4 ~65.2 MTEB, above OpenAI text-embedding-3-large
  ([pythonalchemist](https://www.pythonalchemist.com/embeddings/cohere-embed-v4)).

**Evidence against "one space for everything":**

- jina-embeddings-v4: MTEB-en **55.97** — a strong visual retriever
  that is a weak text embedder
  ([Jina](https://jina.ai/models/jina-embeddings-v4/)).
- Qwen3-VL-Embedding slightly below same-size text-only Qwen3 embedders
  on pure text ([paper](https://arxiv.org/pdf/2601.04720)).
- Late-interaction document specialists beat every single-vector joint
  model on visually rich documents (ViDoRe: 90.17 multi-vector vs 84.11
  single-vector for the *same* Jina model;
  [paper](https://arxiv.org/html/2506.18902v2)); general multimodal
  embedders sometimes underperform even text-only embedders on
  document retrieval ([DRAG assessment](https://arxiv.org/pdf/2508.03644)).
- Audio/video: the joint spaces that exist (Marengo 512-d, Gemini-2
  3072-d) are different vendors, different dimensions, mutually
  incompatible, and MAEB shows no audio model covers both acoustic and
  linguistic meaning ([MAEB](https://arxiv.org/abs/2602.16008)).
- Spaces are mutually incompatible even within one vendor
  (gemini-embedding-001 vs -2:
  [Vertex docs](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/embedding-2)),
  and cross-space cosine similarity is meaningless
  ([Medium/Gemini-2 analysis](https://medium.com/@milesk_33/gemini-embedding-2-one-vector-space-to-replace-your-multimodal-pipeline-d44883c164b6)).

**Verdict.** For a text+image corpus embedded fresh with a frontier
API model (Voyage 3.5-multimodal, Gemini Embedding 2, Cohere v4), one
joint space is now a defensible default — the text-quality tax has
collapsed to ~0–3 MTEB points. But the *architecture* cannot assume it:
(a) open/self-hosted deployments don't get that parity (Jina v4, Qwen3-VL);
(b) audio and video have no shared space with anyone's text space;
(c) the document-image quality frontier is multi-vector late interaction,
a structurally different index; (d) corpora accrete history — an existing
text corpus embedded with model A cannot be queried through model B's
space without full re-embedding. **The honest 2026 architecture is
multi-space with fan-out-and-fuse**: `glean` fans a query out to each
space present in the corpus (embedding the query once per space), runs
per-space top-k, and fuses ranked lists (RRF is the standard fusion,
already the norm in hybrid dense+sparse search). One-space corpora are
then just the degenerate single-fan case, which the same code serves.

**What vfs already permits.** The `Vector` model tracks model name and
dimension per vector — `Vector[1024, "voyage-multimodal-3.5"]` — and
`VectorType` validates both on read/write
(`src/vfs/models/vector.py:64-97`, `210-226`); `NativeEmbeddingConfig`
carries `model_name` alongside dimension for pgvector columns
(`src/vfs/models/vector.py:48-62`). Coexisting spaces were anticipated:
the missing pieces are plural — *multiple* embedding columns/tables (one
per space, since native vector columns are fixed-dimension), a
space-registry (model name → dimension → which entry kinds it covers),
and per-space query fan-out in glean. Nothing in the current model
blocks this; nothing in it implements it yet.

---

## 6. Schema consequences worth carrying into the storage memo

1. **Dimension is per-space, not per-corpus.** 512 (Marengo) to 3,072
   (Gemini-2) in production today; Matryoshka truncation is now
   universal (all six major models), so a corpus policy of "truncate to
   1024" is realistic for cost control — but truncation choice is part
   of the space identity (a 768-truncated and full 3072 Gemini vector
   are comparable, but the *column* is one width).
2. **A chunk may carry zero, one, or many vectors** — zero (media
   awaiting embedding, or a space that doesn't cover its kind), one per
   single-vector space, or ~1,024 for a late-interaction space. The
   multi-vector case needs its own row shape (`chunk_id, seq, vector`)
   or packed blob, and its MaxSim scoring lives above SQL.
3. **Model-name mismatch is a correctness bug, not a tuning detail** —
   cross-space cosine is noise; `VectorType`'s model-name validation is
   the right instinct and should extend to query-time (a glean query
   embedded with model A must only score against model-A vectors).
4. **Media pricing is pixel-/token-denominated and cheap enough for
   default-on** ($0.60/B pixels ≈ $0.0006 per 1M-pixel page at Voyage;
   $0.47/M image tokens at Cohere) — embedding-on-write for images is
   economically similar to embedding text.
5. **Derived-text sidecars (question 6) are the audio/video embedding
   story today**, not a fallback: transcripts feed the existing text
   space; native audio/video vectors are an optional extra space.
