# Study: image renderings — immich's derived-artefact pipeline and fastembed's image models

- **Status:** study
- **Date:** 2026-10-05
- **Owner:** Clay Gendron
- **Sources:**
  - `immich` — shallow clone of `main` @ `07daf87` (2026-10-05); **AGPL-3.0** — study only, never copy.
  - `fastembed` — `origin/main` @ `0db8d09` (2026-10-05); Apache-2.0.
  - Caption seams, read for one paragraph each: `markitdown` (MIT), `haystack` (Apache-2.0), `llama_index` (MIT). Not refreshed for this study; cited at the checkout on disk.
- **Method:** read the immich server schema (`server/src/schema/tables/`), the smart-search, OCR, metadata, media and job services, the database/search/job repositories, the `immich_ml` Python package, the migrations touching the vector tables, and the user docs on model choice. Read fastembed's `image/`, `late_interaction_multimodal/` and the text-side CLIP/SigLIP entries. Every claim is marked **observed** (read in the source, cited `repo:path:line`) or **inferred** (my reading of why).
- **Decision this feeds:** whether an image entry's searchable rendering is a text description (caption + OCR) stored as its text content, produced as a reindex step through a provider seam like ADR 054's embedding provider; and how to stamp, invalidate, queue and bound that work.

## 1. immich: the per-asset row and its derived artefacts

### 1.1 The asset row

**Observed.** `asset` is one row per uploaded file (`immich:server/src/schema/tables/asset.table.ts:64-148`). The columns that matter here:

| column | type | note |
|---|---|---|
| `checksum` | `bytea` (sha1), indexed | unique per `(ownerId, checksum)`; the upload dedup key (`:31-42`) |
| `originalPath`, `originalFileName` | text | the original bytes live on disk, never in Postgres |
| `type` | enum | image / video / other |
| `width`, `height` | `integer NULL` | **on the asset row**, filled by metadata extraction (`:140-144`) |
| `thumbhash` | `bytea NULL` | a tiny placeholder hash of the thumbnail (`:107-108`) |
| `fileCreatedAt`, `fileModifiedAt`, `localDateTime` | timestamptz | dates resolved from EXIF with fs mtime as fallback |
| `isEdited` | bool | edits do not overwrite extracted dimensions (`metadata.service.ts:381-383`) |

Everything else derived from the bytes lives in a **side table keyed by `assetId`**, one table per artefact kind. No ML output sits on the asset row.

### 1.2 The derived artefacts, one table each

| artefact | table | shape | produced by | "needs work" test | invalidation |
|---|---|---|---|---|---|
| EXIF / metadata | `asset_exif` (`asset-exif.table.ts:15-121`) | PK `assetId`; make, model, `exifImageWidth/Height`, `orientation` (varchar), `dateTimeOriginal`, lens, fNumber, focalLength, iso, lat/long, city/state/country (reverse-geocoded), `description` (text, default `''` — "or caption"), fps, exposure, `projectionType`, `colorspace`, `bitsPerSample`, `rating`, `tags[]`, `lockedProperties[]` | `metadata.service.ts:229` via exiftool-vendored | `asset_job_status.metadataExtractedAt IS NULL` | re-run with `force` |
| thumbnail / preview / fullsize | `asset_file` (`asset-file.table.ts:16-47`) | `(assetId, type, isEdited)` unique; `path` on disk; `isProgressive`, `isTransparent` | `media.service.ts:192` | missing file row | regenerate with `force` |
| CLIP embedding | `smart_search` (`smart-search.table.ts:4-18`) | PK `assetId`; `embedding vector(512)` with `STORAGE EXTERNAL`; HNSW `vector_cosine_ops` (`ef_construction=300, m=16`) | `smart-info.service.ts:88` | **row absent** — `NOT EXISTS (select from smart_search where assetId = asset.id)` (`asset-job.repository.ts:213-219`) | `TRUNCATE smart_search` or column retype |
| OCR boxes | `asset_ocr` (`asset-ocr.table.ts:15-73`) | one row per detected text box: 8 normalised corner coords (0–1), `boxScore`, `textScore`, `text`, `isVisible` | `ocr.service.ts:31` | `asset_job_status.ocrAt IS NULL` (`asset-job.repository.ts:455-467`) | `TRUNCATE` both OCR tables (`ocr.repository.ts:30-35`) |
| OCR search text | `ocr_search` (`ocr-search.table.ts:4-20`) | PK `assetId`; one `text` column = all boxes' text tokenised and joined by space; GIN trigram index on `f_unaccent(text)` | same job, same upsert CTE (`ocr.repository.ts:59-70`) | same | same |
| faces | `asset_face` + `face_search` (`face-search.table.ts:4-17`) | bounding box + `vector(512)` HNSW cosine | face detection job | `facesRecognizedAt IS NULL` | per-job |
| job stamps | `asset_job_status` (`asset-job-status.table.ts:4-21`) | PK `assetId`; `facesRecognizedAt`, `metadataExtractedAt`, `duplicatesDetectedAt`, `ocrAt` — all `timestamptz NULL` | each job's last line | — | — |

**Observed.** Two different "done" signals coexist: OCR, metadata, faces and duplicates stamp a **timestamp on `asset_job_status`**; the CLIP embedding has **no timestamp** — the existence of the `smart_search` row is the stamp (`asset-job.repository.ts:216-218`). **Inferred.** The timestamp form exists because those jobs can legitimately produce *nothing* (an image with no text still counts as "OCR done"); a presence-as-stamp form cannot say "done, empty" without a sentinel row. Note `ocr_search` is only inserted when at least one box was found (`ocr.repository.ts:61`), which is exactly why OCR needed `ocrAt`.

**Observed.** OCR keeps two renderings of the same output: the structured boxes (`asset_ocr`, for the UI overlay) and a flattened search string (`ocr_search`, for trigram search). The search string is rebuilt from the boxes by a migration when the tokenizer changed (CJK bigrams, `migrations/1764483051488-OCRBigramsForCJK.ts`: truncate `ocr_search`, then stream `asset_ocr` grouped by asset in pages of 5,000 and re-tokenise). **Inferred.** The structured form is the source of truth; the flat text is a derived index that can be regenerated without re-running the model.

### 1.3 Thumbnails and previews

**Observed.**
- Three sizes, all written to disk under `<media>/thumbs/<ownerId>/<assetId>_<type>[_edited].<format>` (`cores/storage.core.ts:124-131`); only the path is in Postgres.
- Defaults (`dtos/config.dto.ts:695-716`): thumbnail = WebP, 250 px, q80; preview = JPEG, 1440 px, q80; fullsize = disabled (JPEG when on); colourspace P3; `extractEmbedded: false` (RAW embedded preview not used by default).
- `thumbhash` is computed from the decoded preview and stored as `bytea` on the asset row (`media.service.ts:170-182`, `media.repository.ts:242-252`) — a ~25-byte blurred placeholder for the UI.
- **The ML jobs consume the preview, not the original.** CLIP encodes `AssetFileType.Preview` (`asset-job.repository.ts:223-229`); OCR takes `asset.previewFile` (`ocr.service.ts:38-47`); both return `Failed` if the preview is missing. Orientation is applied at decode (`media.service.ts:242-253`), so the preview is upright.
- Dimensions: metadata extraction reads `ImageSize` first because `ImageWidth/ImageHeight` are the embedded preview's size on CR2/RAF RAW files (`metadata.service.ts:555-570`), then swaps width/height when EXIF orientation is sideways (`:366-368`). The media job later overwrites `width/height` from the actual decoded fullsize (`media.service.ts:185-186`).

**Inferred.** The preview is immich's "normalised input": one decode, one orientation fix, one colourspace, bounded to 1440 px, and every model reads that instead of a 50 MB RAW. It is a cache of decode work, not a user feature.

### 1.4 Vector search path

**Observed.**
- Extension choice at boot: `VECTOR_EXTENSIONS = [VectorChord, Vector]` (`constants.ts:37`) — VectorChord preferred when installed, pgvector otherwise; a `DB_VECTOR_EXTENSION` env override exists (`database.repository.ts:33-51`). Version pins: VectorChord `>=0.3 <2`, pgvector `>=0.5 <1`, Postgres `>=14` (`constants.ts:23-25`).
- Index DDL per extension (`utils/database.ts:1102-1125`): VectorChord `vchordrq` with `residual_quantization=false`, `spherical_centroids=true`, `lists=[N]`; pgvector HNSW `ef_construction=300, m=16`. Both `vector_cosine_ops`. `lists` is sized from the row count: 1 below 128k rows, then a power of two from `count/1000` (`database.repository.ts:363-369`); probes = `lists/8`.
- Query: `ORDER BY smart_search.embedding <=> :query` (cosine distance), inner-joined to the asset filter, `LIMIT size+1 OFFSET` paging, `size` capped at 1,000, inside a transaction that sets `vchordrq.probes` locally (`search.repository.ts:320-337`).
- Text queries are embedded through the ML service's CLIP **textual** tower and memoised in-process keyed `modelName + query + language` (`search.service.ts:325-340`). Image-as-query reuses the stored embedding of another asset (`:342-345`).
- Duplicate detection is a second consumer of the same embedding (`maxDistance: 0.01` default, `config.dto.ts:631-634`; `duplicate.service.ts:354-371`).

### 1.5 The model-change story (the part vfs cares most about)

**Observed.** The CLIP model name is **not stored in the database as a stamp**. It lives in system config (`machineLearning.clip.modelName`, default `ViT-B-32__openai`, `config.dto.ts:627-630`), and the only durable fact the DB carries is the **column's own dimension**, read back from `pg_attribute.atttypmod` (`database.repository.ts:297-320`, falls back to 512 with a warning). Dimensions per model are a hardcoded table of ~57 names → 512/640/768/1024/1152/1536 (`constants.ts:68-126`); an unknown name is refused at config validation (`smart-info.service.ts:23-32`).

On `ConfigUpdate` (`smart-info.service.ts:34-65`), under a Postgres advisory lock `CLIPDimSize = 512` (`enum.ts:1009`, `database.repository.ts:458-499`):
1. if the new model's dim differs from the column's dim → `setDimensionSize(dim)`: delete all rows, add a CHECK on `array_length`, drop `clip_index`, `ALTER COLUMN embedding TYPE vector(dim)`, recreate the index, `VACUUM ANALYZE` (`database.repository.ts:322-357`);
2. else if only the name changed → `TRUNCATE smart_search` (`:359-361`);
3. then **nothing is re-queued** — a `TODO` says a reindex job "should be scheduled, though user confirmation should probably be requested" (`smart-info.service.ts:62-63`). The docs tell the admin to press "All" on the Smart Search job (`docs/docs/features/searching.md:62-69`).

Per-job guard against a race with a config change (`smart-info.service.ts:103-116`): embed → if the dim-size lock is busy, wait → re-read config → if the model name changed since the job started, **skip** (drop the vector) → else upsert. **Inferred.** Because the stamp is the column type, the only safe reaction to a model change is a full truncate: a 512-d vector from model A and a 512-d vector from model B are indistinguishable in the table. The TODO and the doc step 6 are the cost of keeping identity in config.

The `force` path of the queue-all job re-applies `setDimensionSize` "in case it failed earlier" (`smart-info.service.ts:74-78`), i.e. the dimension change is not transactional with the config write and may need repair.

### 1.6 The job model

**Observed.**
- BullMQ on Redis, one queue per job family, `attempts: 1`, `removeOnComplete: true`, `removeOnFail: false` (`repositories/config.repository.ts:284-288`). **No automatic retries**; a failed job stays visible and the admin re-runs "Missing" (`docs/docs/guides/remote-machine-learning.md:60`).
- Per-queue concurrency from config (`config.dto.ts:598-614`): metadata 5, thumbnails 3, **smartSearch 2, ocr 1**, faces 2, video 1, background 5. Applied at boot and on config change (`queue.service.ts:98-102`).
- The upload chain is a sequence of jobs, each queued by the previous one's completion hook (`job.service.ts:104-188`): upload → `AssetExtractMetadata` (`asset-media.service.ts:187`) → emits `AssetMetadataExtracted` → `StorageTemplateMigrationSingle` → `AssetGenerateThumbnails` → fan-out to `SmartSearch`, `AssetDetectFaces`, `Ocr` (+ `AssetEncodeVideo`) → `SmartSearch` done → `AssetDetectDuplicates`. Thumbnails gate every ML job because the ML jobs read the preview.
- Bulk ("queue all") jobs stream asset ids from a cursor query and enqueue in batches of `JOBS_ASSET_PAGINATION_SIZE = 1000` (`constants.ts:27`; `smart-info.service.ts:80-82`; `utils/misc.ts batched`). Each ML job is **one asset, one HTTP call** to the ML service — no cross-asset batching on the server side.
- The ML service (`immich_ml/main.py:165-203`) takes one `image` or one `text` per `POST /predict` plus an `entries` JSON naming the models and tasks; it loads models lazily, caches them with a TTL (default 300 s, `config.py:59`), and evicts idle ones. Batch size caps exist only inside a request (faces 4, OCR 6 crops; `config.py:41-43`).
- Models are pulled by `huggingface_hub.snapshot_download` from the `immich-app/<model>` org at revision `main` into `~/.cache/immich_ml/<model>/<task>/` (`models/base.py:63-74`, `config.py:58,77-78`); the model name alone (`ViT-B-32__openai`) identifies the ONNX files; `textual` and `visual` towers are separate ONNX graphs (`models/clip/visual.py:62-89`, `textual.py:101-116`), preprocessing config read from the repo's `preprocess_cfg.json`.
- OCR is PaddleOCR PP-OCRv5 in ONNX (`models/constants.py:78-88`; default `PP-OCRv5_mobile`, min detection 0.5, min recognition 0.8, `maxResolution 736`, `config.dto.ts:642-648`): a detector producing quad boxes, then a CTC recogniser per crop (`models/ocr/detection.py`, `recognition.py`).

### 1.7 Metadata kept on the row vs the side table

**Observed.** The asset row keeps only what listing and layout need (`width`, `height`, dates, `thumbhash`, `duration`). The EXIF side table keeps ~30 columns, several of them user-editable and lockable (`lockedProperties`, `metadata.service.ts:490-531`: description, dateTimeOriginal, lat/long, rating, tags, timeZone are written back to the file via exiftool). The `description` column is explicitly the user's caption ("or caption", `asset-exif.table.ts:77-78`), seeded from `ImageDescription`/`Description` tags (`metadata.service.ts:308`). **Inferred.** immich never generates a caption; its "description" is human-authored metadata, and its searchable renderings are the CLIP vector (semantic) and the OCR text (lexical), plus trigram search on the filename (`asset.table.ts:53-57`).

## 2. fastembed: image and multimodal embeddings in Python

**Observed** (`fastembed/image/onnx_embedding.py:13-58`, `siglip_embedding.py:7-16`, `text/clip_embedding.py:8-21`, `text/siglip_embedding.py:7-20`, `text/onnx_embedding.py:167-178`, `late_interaction_multimodal/colpali.py:20-32`, `colmodernvbert.py:25-33`):

| model (image tower) | dim | size | licence | text tower in fastembed? | shared space |
|---|---|---|---|---|---|
| `Qdrant/clip-ViT-B-32-vision` | 512 | 0.34 GB | MIT | `Qdrant/clip-ViT-B-32-text` (0.25 GB, 77-token cap, English) | yes — same CLIP, "no prefixes necessary" |
| `Qdrant/Unicom-ViT-B-32` | 512 | 0.48 GB | MIT | **none** in `fastembed/text/` | described "multimodal" but no text side shipped |
| `Qdrant/Unicom-ViT-B-16` | 768 | 0.82 GB | MIT | none | same |
| `Qdrant/resnet50-onnx` | 2048 | 0.10 GB | Apache-2.0 | n/a | unimodal (image→image only) |
| `jinaai/jina-clip-v1` | 768 | 0.34 GB | Apache-2.0 | `jinaai/jina-clip-v1` text (0.55 GB, same name, different `model_file`) | yes, 2024 |
| `google/siglip2-base-patch16-224` | 768 | 0.37 GB | Apache-2.0 | `google/siglip2-base-patch16-224` text (1.13 GB, multilingual, 64-token cap) | yes, 2025, multilingual |
| `Qdrant/colpali-v1.3-fp16` (late-interaction) | 128 per token | 6.5 GB | gemma | built in (`embed_text`/`embed_image` on one class) | yes — multi-vector, page screenshots |
| `Qdrant/colmodernvbert` (late-interaction) | 128 per token | 1.0 GB | — | built in | yes, "CPU friendly" |

Mechanics:
- `ImageEmbedding(model_name).embed(images, batch_size=16, parallel=None)` yields L2-normalised vectors (`onnx_embedding.py:153-181, 204-207`). Input is a path or a `PIL.Image` (`common/types.py:17`), opened lazily per batch (`onnx_image_model.py:82-96`). Preprocessing is built from the HF repo's `preprocessor_config.json` (`common/preprocessor_utils.py:151-159` → `transform/operators.py:270-314`: RGB convert, resize, centre-crop, rescale, normalise). CPU ONNX Runtime; `parallel>1` forks a worker pool for offline bulk.
- Text and image are **separate classes and separate downloads** (`TextEmbedding` vs `ImageEmbedding`); the user pairs them by name. Nothing in the registry links a vision tower to its text tower except the shared name string and the `description` field.
- ColPali/ColModernVBERT are one class with both `embed_text` and `embed_image` (`late_interaction_multimodal_embedding.py:124-168`) — multi-vector output (one 128-d row per patch/token), scored by MaxSim, not a single cosine. ColPali's query path prepends `"Query: "` and pads (`colpali.py:35-39, 170`).

**Inferred.** For vfs the usable single-vector, text↔image pairs today are CLIP ViT-B/32 (small, English, 77 tokens — a caption-length cap), jina-clip-v1 and SigLIP2 (multilingual, 64 tokens). None of these can embed a *document chunk* of text into the image space well — the text towers are trained on captions. ColPali-style models are a different index shape (multi-vector) that vfs's one-vector-per-chunk tables do not hold. ADR 054 already measured fastembed at 3.9 text chunks/s and did not adopt it; the image models are the same CPU ONNX path.

## 3. Caption-as-rendering: three seams, one paragraph each

**markitdown** (`markitdown:packages/markitdown/src/markitdown/converters/_image_converter.py:39-86, 87-140`, MIT) — **observed.** An image converts to Markdown in two layers: first a short metadata block from exiftool (`ImageSize, Title, Caption, Description, Keywords, Artist, Author, DateTimeOriginal, CreateDate, GPSPosition`, one `key: value` line each), then, only if an `llm_client` and `llm_model` are supplied, a `# Description:` section from one chat-completion call with the base64 data-URI and the prompt `"Write a detailed caption for this image."` (overridable via `llm_prompt`). The client is an OpenAI-style object passed through kwargs; no model id is recorded in the output. **Inferred.** This is the minimal seam: metadata is always-on and cheap; the caption is opt-in and the output is plain Markdown text, which is exactly "text content as the rendering".

**haystack** (`haystack:haystack/components/extractors/image/llm_document_content_extractor.py:32-66, 136-178, 262-374`, Apache-2.0) — **observed.** `LLMDocumentContentExtractor` takes a vision-capable `ChatGenerator` and a fixed prompt (no Jinja variables allowed) whose default is a transcription prompt: extract the content *exactly* as Markdown in reading order, replace figures with `[img-caption]…[/img-caption]`, tables with a Markdown table plus `[table-caption]`, checkboxes as Markdown, and return JSON `{"document_content": …}`. One LLM call per document; the result overwrites `Document.content`, extra JSON keys go to `meta`, failures go to `failed_documents` with `content_extraction_error` in meta (`raise_on_failure=False` default). An optional `detail` ("low"/"high") and a `size` cap feed the image conversion. **Inferred.** This is OCR-by-LLM plus captioning in one prompt — the closest prior art to "caption + OCR text as the entry's text content", and its failure handling (keep the document, mark the meta) is the shape a reindex step wants.

**llama_index** (`llama_index:llama-index-integrations/readers/llama-index-readers-file/llama_index/readers/file/image_caption/base.py:13-96` and `image_vision_llm/base.py:13-107`, MIT) — **observed.** Two local readers: `ImageCaptionReader` runs BLIP-large (`Salesforce/blip-image-captioning-large`) with an optional conditioning prompt, `ImageVisionLLMReader` runs BLIP-2 (`blip2-opt-2.7b`) with the default prompt `"Question: describe what you see in this image. Answer:"`. Both return an `ImageDocument(text=caption, image=<base64 if keep_image>, metadata=extra_info)`. Both pull torch + transformers. **Inferred.** The seam is "reader → text document"; the model is a constructor argument, nothing durable names which model produced the text.

Across the three: the caption is always the **text content** of the resulting document, the model is an injected client/object, and **none records the model identity on the output** — the stamping problem is left to the caller.

## 4. What this says for vfs

### 4.1 Caption vs embedding vs both

**Recommendation: caption + OCR text as the rendering, through the ADR 054 shape; no CLIP image vector in the first landing.**

Why, in plain terms, said twice:
- vfs already has one searchable form for every entry: text content → chunks → grams, lexical postings, and one embedding per chunk in a single mount-wide space (ADR 054 pin 4: one `embedding_model` on the meta row). A caption drops an image into that existing machinery with zero new tables, zero new index types, and it is grep-able and glean-able alongside Markdown and code. A CLIP vector would need a **second space** (a different model, a different dimension, cross-modal only against caption-length text) — the "space registry reserved for media" ADR 054 names and defers.
- immich shows what the CLIP-vector path costs in production: a dedicated `vector(dim)` table whose column type must be re-typed when the model changes, a truncate on any model swap, an advisory-lock dance around dimension changes, and an admin-driven re-run. It also shows CLIP alone is not enough: immich **added OCR as a separate lexical rendering** because a photo of a receipt is found by its words, not its vibe.
- fastembed's text↔image pairs cap text at 64–77 tokens and are trained on captions; they would not let a user's document-style query hit an image, and the only CPU-friendly multimodal document models (ColPali family) are multi-vector, which vfs's tables do not hold.
- Caption quality is the one real loss: a vision-model caption is lossy and model-dependent. **Inferred.** That is acceptable for an agent filesystem whose users search by words, and it is recoverable — a re-caption is a reindex, same as a re-embed.

Keep the CLIP-style image vector as the documented **future direction** (the media space in the registry), not a declared limit.

### 4.2 The stamp-and-invalidate rule

immich's weakness is instructive: identity in config, dimension in the column type, presence-as-stamp, and a TODO where the re-run should be. vfs should not copy that. The rule that fits vfs's existing laws:

- **Stamp the rendering, not the mount.** Each image entry's text content carries a durable `rendered_by` identity on the row that holds it: a provider- and version-qualified id (e.g. `anthropic/claude-…@2026-xx` or `tesseract@5.3`), one for the describer and one for the OCR step, plus the `content_hash` of the *bytes* the rendering was made from. (ADR 054 puts the embedding identity on the meta row because the embedding space is mount-wide; a caption is per entry and may be re-done entry by entry, so the stamp belongs on the entry, like immich's `asset_job_status` timestamps.)
- **"Needs work" = stamp absent or stale**, never row-absent: an image with no text (a blank frame, OCR finding nothing) still gets a stamp, like `ocrAt`. Store the empty rendering explicitly.
- **Invalidate by comparison, not by truncate.** When the configured describer id differs from a row's `rendered_by`, that row is dirty; `reindex` re-renders it. Unchanged bytes (same `content_hash`) under the same describer are never re-sent — the same dedup ADR 054 pin 5 applies to embeddings.
- **The downstream chain re-dirties itself.** A new caption is new text content → new chunks → `chunk_generation` law re-dirties grams, postings and embeddings. One `reindex` leaves every index at the same generation, as ADR 054 requires. Order inside reindex: render (bytes → text) **before** chunk/embed, so the embed step sees the new text.
- **Guard the race immich guards**: a render that started under describer A must not be written once the configured describer is B — write with `WHERE rendered_by IS NULL OR rendered_by = :expected`, the same conditional-update shape as ADR 054's `UPDATE … WHERE embedding IS NULL`.

### 4.3 Job and bulk posture

- Rendering is a **streaming step of `reindex`**, after publish, inside the lease, exactly like embedding (ADR 054 pin 6): select one budget's worth of un-rendered or stale image entries, call the provider with no transaction open, write back with short conditional updates, check the lease, repeat. A crash loses one batch.
- Budgets come from the provider: a hosted vision API is bounded by requests per minute and bytes per request, not tokens; the provider declares `max_batch_inputs` and `max_input_bytes`, and the storage cuts batches on both (a `byte_batched` sibling of ADR 054's `token_batched`). immich's "one asset, one call, concurrency 2" is the hosted shape; a local OCR engine goes through `call_offloaded` like a CPU embedder.
- No automatic retries inside a batch beyond `Retry-After`; a failure leaves the stamp absent and the `reindex` result reports `rendered, cached, unrendered` with warning severity when `unrendered > 0` — the same envelope as `unembedded`. The 10,000-file ETL contract holds because nothing is held open across the provider call.
- Report lexical-only / unrendered counts in `glean`'s envelope until rendering finishes, like the unembedded count today.

### 4.4 Which metadata to keep on the row

- **On the entry row, always, cheaply, without any model:** `width`, `height`, `format` (sniffed from magic bytes, not the extension), byte size and `content_hash` (already there), EXIF orientation as an integer, and the capture date if present. These are what listing, sorting and the describer's input need, and they are immich's asset-row set.
- **In the rendering text, not as columns:** the human-readable EXIF subset markitdown prints (camera, lens, GPS, title/description/keywords tags). Putting it in the text makes it grep-able and glean-able for free and avoids a 30-column side table vfs has no UI for. An embedded `ImageDescription` tag is a free first caption and should be included verbatim.
- **Not kept:** faces, thumbhash, projection type, colourspace — immich needs them for a photo UI; vfs is a filesystem for agents.

### 4.5 Thumbnails

**Recommendation: vfs does not store thumbnails or previews as user-facing artefacts, but the describer provider receives a bounded, upright, RGB downscale rather than the raw bytes.**

immich's preview exists for two reasons: a UI, and a normalised model input (one decode, orientation fixed, bounded to 1440 px). vfs has no UI; the second reason stands. **Inferred:** keep it as a transient step inside the render call (decode → orient → downscale to the provider's declared max edge → encode JPEG/WebP → send), not as a stored blob. If a host later wants previews served through `read`, they can be a derived rendering under the same stamp rule, but nothing in the search path needs them persisted.

### 4.6 One-line version

Make the image's text content a stamped, re-renderable caption-plus-OCR produced as a `reindex` step through a describer seam shaped like ADR 054's embedder; keep `width`/`height`/format/orientation on the row; store no thumbnails; leave the CLIP image space as the named future direction, not a table.
