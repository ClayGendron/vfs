# Study: deployed multimodal search practice + extraction-framework architecture

- **Date**: 2026-07-25
- **Brief**: [2026-07-25-multimodal-storage-and-search-brief.md](../../2026-07-25-multimodal-storage-and-search-brief.md),
  questions 6 (derived-text sidecars) and 7 (per-verb meaning over media),
  with bearing on 8 (embedding spaces) and 10 (lifecycle/freshness).
- **Method**: online primary sources only. Immich and PhotoPrism are
  **AGPL-3.0** — studied strictly through public docs, official
  discussions, and blog posts (URLs cited); no code read. Apache Tika is
  Apache-2.0; Vespa docs Apache-2.0; Microsoft/Apple platform docs are
  public documentation.

Two halves: (A) how real deployed systems search media; (B) the
25-year-old derived-text extraction lineage (Tika, Spotlight, IFilter).

---

## Part A — How deployed systems search media

### A1. Immich: the closest living analog to a multimodal `glean`

Immich (self-hosted Google Photos alternative, ~70k+ GitHub stars) is
the most instructive precedent because its architecture maps almost
piece-for-piece onto vfs's situation: media bytes in one store, Postgres
as the single search database, and a dual-path search.

**Architecture.** Search is split into two explicit paths
([docs.immich.app/features/searching](https://docs.immich.app/features/searching/)):

- **Metadata search** — traditional keyword/filter matching over file
  properties: file names and extensions, paths, user descriptions,
  locations (reverse geocoding), tags, camera make/model/lens, date
  ranges, media type, album/favorite/archive status, star ratings.
- **Smart (contextual) search** — CLIP-family embeddings. Per the docs,
  Immich "uses Postgres as its search database for both metadata and
  contextual CLIP search," with the contextual side powered by "the
  VectorChord extension, utilizing machine learning models like CLIP,"
  enabling "freeform searches without requiring specific keywords in the
  image or video metadata."

The ML work lives in a **separate Python service** (immich-machine-
learning): image embeddings are computed at ingest and stored as vectors
in a Postgres table; at query time the text query is encoded by the same
CLIP model via the ML service and Postgres does vector similarity
natively (pgvector operator family; VectorChord — successor to
pgvecto.rs, RaBitQ-compressed indexes — for ANN at scale). Text-query
embeddings are cached in an in-memory LRU keyed by model + query +
language. (Search-result synthesis over
[docs.immich.app/features/searching](https://docs.immich.app/features/searching/)
and
[docs.immich.app/administration/postgres-standalone](https://docs.immich.app/administration/postgres-standalone/).)

**How text meets the image index**: one joint space. The image tower of
the CLIP model embeds every asset at ingest; the text tower embeds the
query at search time; both land in the same vector column and nearest-
neighbor distance is the ranking. There is no fusion step between the
two paths in the RRF sense — metadata filters are applied as SQL
predicates *around* the ANN query (pre/post-filtering inside one
engine), not merged as ranked lists.

**Model-choice reality.** The community model guide
([immich discussion #11862](https://github.com/immich-app/immich/discussions/11862))
compares OpenCLIP and SigLIP families (WebLI / DFN-5B / LAION-2B
training sets) plus multilingual variants (NLLB-distilled) on three
axes: memory (RAM/VRAM), speed (MACs), and retrieval recall. Spread is
wide — e.g. `ViT-H-14-378-quickgelu__dfn5b` at 542B MACs scores 0.828
recall vs `ViT-B-16-SigLIP-256__webli` at 29B MACs scoring 0.767 — and
the guide frames the last ~7% of quality as an explicit cost decision.
Multilingual query support is a *model property*, not an engine feature
([immich discussion #6035](https://github.com/immich-app/immich/discussions/6035)).

**The re-embed cliff.** Switching CLIP models requires re-running the
smart-search job over the entire library — every stored image vector is
model-specific, and users are advised to back up Postgres before trying
a new model (#11862). One active embedding space per corpus; a model
change is a bulk migration, not a flag flip. This is the strongest
deployed evidence for the brief's Q8: vfs's `Vector` model-name
parameterization is exactly the bookkeeping Immich needs and has.

**Derived text is a first-class search category.** Immich's searchable
categories include **OCR — "text appearing within images"** — alongside
faces, CLIP context, and metadata
([docs](https://docs.immich.app/features/searching/)). That is
grep-over-derived-text shipping in a mainstream 2026 media server.

### A2. PhotoPrism: the metadata-plus-labels floor, no vectors at all

PhotoPrism ships an entire competitive photo-search product with **no
vector search whatsoever**. Search is pre-defined views plus a filter
grammar over extracted metadata, and content understanding is reduced to
**classification labels**: a TensorFlow (NASNet-family) classifier
assigns labels ("cat", "beach") at index time, and labels become
filterable/browsable facets like any other metadata
([docs.photoprism.app/user-guide/search](https://docs.photoprism.app/user-guide/search/);
[Linux Magazine tutorial](https://www.linux-magazine.com/Issues/2022/256/Machine-Learning-Smarts-for-Shutterbugs);
[pkg.go.dev classify package doc](https://pkg.go.dev/github.com/photoprism/photoprism/internal/classify)).
Browsable/filterable axes: media type (panoramas, vectors, scans,
documents, videos, live photos), albums/folders/people/labels, status
(archived, private, favorites), places/regions, calendar, camera.

Two lessons. First, **classification-into-metadata is a real
alternative to embedding**: content understanding can be projected into
the existing metadata search machinery (labels are just tags) rather
than requiring a vector index — a label is derived *metadata* the way
OCR text is derived *text*. Second, PhotoPrism's newer **external
vision API** ([discussion #4983](https://github.com/photoprism/photoprism/discussions/4983))
moves captioning/labeling to a pluggable external service — the same
plugin-per-capability shape as Part B's extraction frameworks, arrived
at independently.

### A3. ColPali-style document RAG in production

ColPali (late-interaction vision retrieval over document *page images*)
is shipping, and its production story is dominated by one number: the
**per-page vector budget**.

- Each page is a 32×32 patch grid + 6 instruction tokens = **1,030
  vectors of 128 dims per page**
  ([Vespa blog: scaling ColPali to billions](https://blog.vespa.ai/scaling-colpali-to-billions/);
  [Qdrant ColPali blog](https://qdrant.tech/blog/qdrant-colpali/)).
- Float storage is ~100–500 KB per page — "for 1M pages, plan for
  100GB–500GB of raw vector storage before compression"
  ([Spheron overview](https://www.spheron.network/blog/colpali-multimodal-document-rag-gpu-cloud/)).
- Vespa's production recipe: **binary-quantize** patch vectors (32×
  storage saving, ~16 KB/page — "comparable to large text embedding
  models"), retrieve candidates with **hamming-distance ANN** (phase 1),
  then **MaxSim rerank** in place (phase 2). Accuracy cost is small
  (nDCG@5 52.4 → 51.6 on DocVQA); hamming is ~3.5× faster than float
  dot product, ~200M 128-bit hamming distances/sec/core. Crucially they
  compute MaxSim *inside* the storage nodes because "fetching this
  amount of vector data per user query would quickly become a scaling
  bottleneck" ([Vespa blog](https://blog.vespa.ai/scaling-colpali-to-billions/)).
- Engines that ship it: Vespa (native tensor MaxSim), **Qdrant multivector
  collections with a MaxSim comparator + binary quantization**, Milvus,
  Weaviate ([Qdrant blog](https://qdrant.tech/blog/qdrant-colpali/);
  [Vespa solution page](https://vespa.ai/solutions/visual-retrieval-augmented-generation/colpali/)).
  BentoML documents serving the model itself
  ([bentoml.com blog](https://www.bentoml.com/blog/deploying-colpali-with-bentoml)).

**Storage split in every deployment**: the *index* holds patch vectors;
the *page images themselves* live in ordinary blob/document storage and
are fetched by id after ranking. Nobody stores page images inside the
vector index. For vfs: late-interaction media search implies a
**multi-vector-per-chunk** shape (1,030 rows or one packed tensor per
page), which single-vector-per-row `Vector` columns do not express —
worth noting as a *foreclosure risk*, not a requirement.

### A4. Hybrid fusion practice: RRF is the boring, universal answer

When two rankers score in incompatible spaces (BM25 lexical vs vector
cosine — exactly glean's text-space vs media-space problem), deployed
practice has converged on **reciprocal rank fusion**:

`score(d) = Σ_over_rankers 1 / (k + rank_of_d)`, k typically 60.

- Shipped natively by Elasticsearch (`rrf` retriever, k named
  `rank_constant`), OpenSearch (hybrid-search pipeline
  `score-ranker-processor`, `technique: rrf`), Azure AI Search,
  Weaviate, Qdrant
  ([Elastic hybrid search docs](https://www.elastic.co/docs/solutions/search/hybrid-search);
  [OpenSearch RRF blog](https://opensearch.org/blog/introducing-reciprocal-rank-fusion-hybrid-search/)).
- Why rank-based beats score normalization: scores from different
  rankers live on incomparable scales and min-max/L2 normalization is
  "sensitive to outliers"; RRF uses only positions, needs **no
  training, no calibration, no tuning**, and rewards documents that
  rank well in multiple lists
  ([OpenSearch blog](https://opensearch.org/blog/introducing-reciprocal-rank-fusion-hybrid-search/);
  [Serghei's RRF explainer](https://blog.serghei.pl/posts/reciprocal-rank-fusion-explained/)).
- OpenSearch's benchmark: RRF within ~3.9% NDCG@10 of tuned score-based
  combination with slightly better latency — i.e., near-parity for free.

The fan-out-then-fuse pattern (query each index independently, merge
ranked lists by RRF) is precisely what a multi-space `glean` needs:
text chunks in a text embedding space, media in a joint CLIP-family
space, optionally BM25/trigram lexical — N ranked lists, one RRF merge,
no requirement that the spaces share dimensions, models, or score
semantics. Immich shows single-engine filter+ANN works when there is
one space; RRF is the precedented answer the moment there are two.

---

## Part B — The derived-text extraction lineage

Three independently evolved systems — Apache Tika (2004→, Java,
server-side), macOS Spotlight (2005→, desktop), Windows Search/IFilter
(Index Server heritage, 1996→) — converged on the same architecture:
**a detector maps bytes to a type; a per-type plugin registry maps the
type to an extractor; the extractor emits (a) cheap structured
metadata properties and (b) a derived text stream; both land in a
search-owned store, never beside the source file.**

### B1. Apache Tika: detect-then-parse, and what hostile files taught it

**Detection.** The `Detector` interface is one method:
`MediaType detect(InputStream, Metadata)`. `DefaultDetector` composes
via service-loader discovery: magic-byte patterns near the file start
(from `tika-mimetypes.xml`), XML root-element inspection, glob/extension
matching as refinement, caller-supplied content-type hints last —
and **container-aware detectors** for the formats where magic lies
(OLE2, zip-based OOXML/iWork need the container opened to tell members
apart) ([tika.apache.org/3.0.0/detection.html](https://tika.apache.org/3.0.0/detection.html)).
Detection never trusts the filename alone.

**Parsing.** A unified `Parser` interface over 1,000+ formats; the
composite parser dispatches on detected media type.
`RecursiveParserWrapper` handles container recursion: parse an archive
or compound document and get back **a list of Metadata objects, one per
embedded resource**, the first for the outer container, each carrying
its extracted text under `X-TIKA:content` — served over HTTP as
tika-server's `/rmeta` endpoint ("a JSONified list of Metadata objects
for the container document and all embedded documents")
([RecursiveParserWrapper javadoc](https://tika.apache.org/2.0.0/api/org/apache/tika/parser/RecursiveParserWrapper.html);
[TikaServer wiki](https://cwiki.apache.org/confluence/display/TIKA/TikaServer)).
Embedded-failure policy is explicit config (`catchEmbeddedExceptions`):
swallow and continue, or abort the file.

**Hostile files.** Tika's own robustness page is blunt: on arbitrary
input "Tika can go into infinite loops or allocate surprising amounts
of memory (OutOfMemoryExceptions)" — zip bombs (42 KB → ~4 PB), tainted
archives forcing 2 GiB buffers (TIKA-2446), infinite loops. The
mitigations are all **process isolation**:

- `ForkParser` "forks a child process and will protect against OOM and
  infinite loops."
- tika-server ≥ 2.x parses **in a forked child by default**; on OOM,
  timeout, or crash the child shuts down and restarts while the parent
  survives; in-flight requests during restart get **503**, and "you
  won't be able to tell which file caused the problems" when several are
  in flight.
- Doctrine: "avoid running Tika in the same process as anything that
  matters, such as your indexer."
- QA: a ~2M-file regression corpus drawn from Common Crawl run before
  each release, plus fuzzing.

([The Robustness of Apache Tika](https://cwiki.apache.org/confluence/display/TIKA/The+Robustness+of+Apache+Tika);
[TikaServer wiki](https://cwiki.apache.org/confluence/display/TIKA/TikaServer);
[TIKA-2446](https://issues.apache.org/jira/browse/TIKA-2446);
[TIKA-216](https://issues.apache.org/jira/browse/TIKA-216).)

### B2. macOS Spotlight: event-driven freshness, plugin-per-UTI

- **Pipeline**: the `mds` daemon reads `/dev/fsevents` from the kernel;
  on a file change it dispatches (mach messaging) to a pool of
  `mdworker` processes, scaled with event volume. The worker resolves
  the file's **UTI** and loads the matching `.mdimporter` plugin —
  system importers in `/System/Library/Spotlight`, third-party ones in
  `/Library/Spotlight` or inside the app bundle. The plugin entry point
  is `GetMetadataForFile(path) → CFDictionary` of attributes
  ([Doyensec: Staring into the Spotlight](https://blog.doyensec.com/2017/11/15/osx-spotlight.html);
  [Eclectic Light: deeper dive into Spotlight indexes](https://eclecticlight.co/2025/07/30/a-deeper-dive-into-spotlight-indexes/)).
- **Freshness**: fsevents-driven — "the series of steps is usually
  completed within a second or two of the file being created or
  edited." Note the honesty in the Doyensec analysis: under high event
  volume "there is no guarantee it can see and capture every single
  event," which is why full-reindex (`mdutil -E`) exists as the repair
  path ([Eclectic Light: when and how to rebuild](https://eclecticlight.co/2024/11/19/when-and-how-to-rebuild-spotlight-indexes/)).
- **Storage**: derived data lives in a **central per-volume store**,
  the hidden `.Spotlight-V100` folder — never as sidecar files next to
  sources. Indexed content splits into cheap file/extended attributes,
  importer-emitted structured metadata (e.g. EXIF), and extracted text
  (`kMDItemTextContent`), and "metadata and content appear to be
  indexed separately" — two pipelines with different costs
  ([Eclectic Light deeper dive](https://eclecticlight.co/2025/07/30/a-deeper-dive-into-spotlight-indexes/)).
- **Isolation**: extraction runs in expendable `mdworker` child
  processes (sandboxed, per Doyensec), never inside `mds` itself.

### B3. Windows Search: the most explicit spec of the whole shape

Microsoft's indexing-process doc is effectively a design document for
derived-text search
([learn.microsoft.com: indexing process overview](https://learn.microsoft.com/en-us/windows/win32/search/-search-indexing-process-overview)):

- **Freshness**: for NTFS "there is only a single crawl and everything
  else is handled by notifications from the USN Change Journal."
  Three FIFO queues (high-priority notifications, normal notifications,
  periodic crawls). Periodic full crawls exist purely as repair —
  e.g. "the USN Change Journal rolling over." Non-notifying stores
  (FAT) fall back to periodic re-crawl.
- **Plugin registries, two axes**: *protocol handlers* (per data store:
  `file://`, `mapi://`) hand back item streams + metadata; *filters*
  (IFilter) and *property handlers* are selected "by the file name
  extension, MIME type, or class identifier" and emit, respectively,
  text content (with sentence/paragraph/chapter boundaries) and typed
  properties.
- **Graceful degradation**: "If the gatherer is unable to find a
  filter, Windows Search uses the metadata to derive a minimal set of
  system property information (like System.ItemName) and updates the
  index." Unknown formats are still findable by name/date/size —
  extraction failure never means invisibility.
- **Isolation, specified to the byte**: the filter host "runs with
  minimal rights (it can't even access the file system)," is
  periodically recycled, and is recycled early "if a filter consumes
  too many resources." The IFilter interface itself has "no access to
  the disk system or network"; the isolation process runs "under a job
  object that prevents child processes from being created and imposes a
  100 MB limit on the working set"
  ([about filter handlers](https://learn.microsoft.com/en-us/windows/win32/search/-search-ifilter-about);
  [filter best practices](https://learn.microsoft.com/en-us/windows/win32/search/-search-3x-wds-extidx-filters)).
- **Storage**: everything lands in **SystemIndex** — "a property store
  and indices over the properties... and an inverted index for textual
  content" (the Windows.edb database). Two index kinds are named:
  **value indices** (filter/sort on whole property values — the glob
  shape) and **inverted indices** (words within text — the grep shape).

### B4. Cross-cutting: the consensus, distilled

| Concern | Tika | Spotlight | Windows Search |
|---|---|---|---|
| Type resolution | magic + glob + container-aware detectors | UTI | extension / MIME / CLSID |
| Extractor unit | Parser per media type | .mdimporter per UTI | IFilter + property handler per type |
| Output split | Metadata props + `X-TIKA:content` text | attribute dict + `kMDItemTextContent` | properties + text chunks |
| Derived store | caller's index (Solr/ES...) | central `.Spotlight-V100` | central SystemIndex (Windows.edb) |
| Freshness | caller's problem | fsevents push + full-reindex repair | USN journal push + periodic-crawl repair |
| Hostile input | forked child, restart on OOM/timeout | expendable sandboxed mdworker | recycled minimal-rights host, 100 MB cap |
| No extractor | configurable skip/abort | file known by fs attributes only | minimal system properties indexed |

**Metadata vs content value.** None of the systems publishes a
quantified split, but the architecture testifies: every one of them
made cheap metadata the *unconditional* tier (always extracted, always
indexed, the fallback when everything else fails) and content
understanding the *best-effort* tier (isolated, timeout-bounded,
skippable). Deployed search UIs agree — of Immich's ~13 searchable
categories, ~10 are cheap metadata (name, path, date, camera, location,
tags, type, album, rating, description) and 3 are expensive derivations
(faces, OCR, CLIP); PhotoPrism ships competitively on the cheap tier
plus classification labels alone. Cheap metadata is the floor that
always works; embeddings are the ceiling that differentiates.

---

## Bearing on the brief

**Q6 — where derived-text sidecars live.** The unanimous precedent is:
**derived artifacts belong to the search/storage system, keyed to the
source item, in the system's own store — never as visible siblings in
the user's namespace** (`.Spotlight-V100`, SystemIndex, Tika's
caller-owned index). For vfs that argues for chunk rows / a
derived-artifacts table hanging off the media entry's version, not
hidden sibling entries. Producers are a plugin-per-mime registry
(detect-then-extract), with three binding lessons: (1) extraction runs
isolated and timeout-bounded, never inline with the write path — Tika:
"avoid running Tika in the same process as anything that matters";
(2) extraction failure degrades to metadata-only, never blocks ingest
or hides the entry (Windows' minimal-properties fallback); (3)
freshness is event-driven regeneration keyed to source change
(fsevents / USN ≈ vfs's own write path — vfs is *better* placed than
either OS: writes are transactional, so "derived row keyed by
`content_hash` regenerated on version change" needs no journal), with
a periodic sweep-style repair pass as the honesty backstop.

**Q7 — per-verb meaning is precedented, verb by verb.**
- *glob* = Windows "value indices" / Immich metadata search /
  PhotoPrism's whole product: name/mime/kind/size/date filtering,
  near-free, unconditional.
- *grep-over-derived-text is not a novelty — it is the 25-year default.*
  Precedents by name: Windows Search's inverted index over
  IFilter-emitted text (Index Server lineage, 1996→); Spotlight's
  `kMDItemTextContent` full-text search via mdimporter plugins (2005→);
  the Tika → Solr/Elasticsearch ingest pipeline (the standard
  enterprise-search recipe); Immich's OCR search category (2025–26).
  Grep over OCR/transcript text of a media entry is the *expected*
  behavior of a search system, not an exotic extension.
- *glean* = Immich's smart search: one joint CLIP-family space, image
  tower at ingest, text tower at query, ANN in the same database vfs
  already targets (pgvector/VectorChord on Postgres). ColPali is the
  document-page frontier but carries a 1,030-vectors-per-page budget —
  design the chunk/vector schema so multi-vector-per-unit is not
  foreclosed, without building it now.
- *graph*: no deployed media-search system treats edges specially —
  nothing to import; verify edges-to-media works, as the brief says.

**Q8 — spaces.** Deployed reality is one active space per modality
family, model-stamped, with model change = full re-embed (Immich).
Multi-space coexistence + RRF fusion (k≈60, rank-only, no calibration)
is the shipped pattern for fusing text-space and media-space hits —
fan out per space, fuse ranks, never compare raw scores.

**Q10 — lifecycle.** Precedent supports: derived artifacts and vectors
are cache-like (rebuildable), keyed to content identity; event-driven
invalidation on rewrite; periodic repair pass; deletion of source
deletes derivations (all three systems drop index entries when the
source goes — trash/sweep should cascade the same way).
