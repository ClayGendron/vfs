# Multimodal storage and search: bytes in the database, media in the verbs

- **Status**: DRAFT research memo, for review — supersedes the
  [2026-07-25 storage-and-search brief](2026-07-25-multimodal-storage-and-search-brief.md);
  commits us to nothing, feeds the storage-bytes ADR that gates the
  content-channel ADR of the
  [multimodal result-content memo](2026-07-25-multimodal-result-content.md).
- **Date**: 2026-07-25
- **Owner**: Clay Gendron
- **Question**: Two halves of one gap. **Storage**: the live tree has no
  binary channel — `Entry.content` is `str | None` with null-byte
  rejection, so a PNG cannot be stored, read, or observed. How does vfs
  store media bytes in the database, segmented from text content the way
  bodies are already segmented from metadata, correct at 10,000-file
  batches on the least generous engine? **Search**: once media is
  stored, what do `glob`, `grep`, `glean`, and `graph` mean over it —
  and what does multimodal embedding capability make possible for
  `glean` in particular?
- **Evidence gathered**: eight parallel primary-source studies,
  committed alongside this memo under
  [studies/2026-07-25-multimodal-storage/](studies/2026-07-25-multimodal-storage/) —
  [git's content-addressed object store](studies/2026-07-25-multimodal-storage/git-object-model.md),
  [bulk blob physics per SQL engine](studies/2026-07-25-multimodal-storage/db-blob-physics.md),
  [production storage-system segmentation](studies/2026-07-25-multimodal-storage/storage-systems.md)
  (SeaweedFS, JuiceFS, OpenDAL, fsspec),
  [the 2025–2026 multimodal embedding landscape](studies/2026-07-25-multimodal-storage/embedding-models.md),
  [deployed multimodal search practice + extraction frameworks](studies/2026-07-25-multimodal-storage/search-practice.md)
  (Immich, PhotoPrism, ColPali deployments, RRF, Tika/Spotlight/IFilter),
  [portable vector search across SQL engines](studies/2026-07-25-multimodal-storage/vector-portability.md),
  and two internal ground-truth studies whose constraints are binding —
  [the storage layer](studies/2026-07-25-multimodal-storage/vfs-storage-ground-truth.md)
  and
  [the search layer](studies/2026-07-25-multimodal-storage/vfs-search-ground-truth.md).
- **Citation provenance**: local repos studied with licenses verified —
  `sqlalchemy` (MIT), `postgres` (PostgreSQL license), `sqlite` (public
  domain), `seaweedfs` (Apache-2.0), `juicefs` (Apache-2.0), `opendal`
  (Apache-2.0), `filesystem_spec` (BSD-3), `pyfilesystem2` (MIT) — all
  cited repo-relative to sibling checkouts under `~/Git/Repos/`. Online
  sources are cited by URL (git-scm.com and the Pro Git book, GitHub
  engineering blog, MySQL/Microsoft/Oracle/python-oracledb vendor docs,
  model-vendor docs and arXiv papers, Vespa/Qdrant/Elastic/OpenSearch
  engineering posts, Immich/PhotoPrism/Tika/Apple/Microsoft public
  documentation). Per the license policy, **git was studied via public
  docs only** — no copyleft clone was opened — and Immich and PhotoPrism
  (AGPL-3.0) were likewise studied strictly through public
  documentation. Our own code is cited from `src/vfs/`
  at commit 276d096.

---

## 1. Ground truth first: four facts that reframe the brief

The two internal studies establish facts the brief's numbered questions
assume away. Everything downstream leans on them.

1. **The versions and chunks flows are schema, not code.** The database
   backend mints no version rows and no chunk rows today — the only
   statements touching those tables are the hard-delete arms of
   `_purge_subtree` (`topology.py:510-511`), pack is unlanded
   (`backend.py:56-59`), and `writes.py` never calls `Chunk.split`
   ([storage ground truth](studies/2026-07-25-multimodal-storage/vfs-storage-ground-truth.md) §0;
   [search ground truth](studies/2026-07-25-multimodal-storage/vfs-search-ground-truth.md) §0).
   Binary versioning and media chunking are therefore **design-time
   questions, not retrofits** — the best possible timing.
2. **"Media carries no text" is currently unrepresentable.** The
   after-validator normalizes every non-directory's absent content to
   `""` and measures it (`entry.py:223-227`). The exclusivity rule is
   a carve-out of this normalization, not an addition — the single most
   load-bearing line in the model change.
3. **Writes are deliberately not serialized with topology.** Stated
   twice in the live tree and load-bearing (`topology.py:497-499`,
   `521-527`). Any content-addressed GC design inherits this: a sweep
   cannot assume writes are quiescent.
4. **grep's contract is doubly text-typed and glean/graph are
   unshipped.** The authoritative match is Python `re` over stored text
   with a false-negatives-never candidate doctrine (`code_grams.py:6-9`);
   the match unit is the line (`entry.py:335-345`); glean and graph have
   no live backend implementation at all (`backend.py:56-58`).

## 2. Prior art

Deep detail lives in the studies; this section carries what bears on
the decisions.

### 2.1 git — the hash-keyed shape, end to end

git is the canonical prior art for a content-addressed blob store, and
the study maps every mechanism onto the vfs decision
([git study](studies/2026-07-25-multimodal-storage/git-object-model.md)):

- **Dedup is arithmetic, not a feature** — identical content produces
  the identical key regardless of name or referrer
  ([Pro Git ch. 10.2](https://git-scm.com/book/en/v2/Git-Internals-Git-Objects)).
  But git hashes a *typed, sized* payload (`"blob <size>\0"` + bytes)
  because its store holds four object kinds; a single-kind vfs blob
  table should **hash raw bytes only**, keeping mime an out-of-band
  column so dedup survives mime relabels.
- **Binaries do delta — and git turns deltas off for media.** The pack
  delta mechanism is content-type-agnostic by construction — the format
  defines only byte-range copy/insert instructions
  ([gitformat-pack](https://git-scm.com/docs/gitformat-pack)) — yet
  `core.bigFileThreshold` (default 512 MiB) stores large files
  "deflated, without attempting delta compression" and the `-delta`
  attribute opts out per path
  ([git-config](https://git-scm.com/docs/git-config),
  [git-repack](https://git-scm.com/docs/git-repack)). Snapshot-only
  binary versioning is git's own converged doctrine for exactly this
  content class; content addressing already captures the dominant
  saving (an unchanged asset across ten versions is ten hash references
  to one blob).
- **GC is reachability walks, never refcounts** — becoming unreachable
  is free (a ref deletion); pruning is a batch walk with a two-week
  `gc.pruneExpire` grace window plus mtime freshening, because writers
  store objects *before* the refs that make them reachable, and the
  docs admit the mitigation "falls short of a complete solution"
  ([git-gc](https://git-scm.com/docs/git-gc)). No ADR rejecting
  refcounting exists; reconstruction shows refcounting was structurally
  unavailable to git (no transactions, counts transiently zero at the
  worst moment, half the roots are predicates, counts corrupt silently
  while walks self-heal) — and **most of those reasons disappear on a
  transactional SQL backend**. In SQL the whole walk collapses to one
  chunked `NOT EXISTS` anti-join over `versions.content_hash` /
  `entries.content_hash`, self-healing, with a short
  `created_at > now() - grace` predicate closing the residual
  separate-statement dedup-upsert window — a window that need only
  dominate one batch's flush latency; days, not git's two weeks, with
  the concrete value left to the ADR that designs the GC arm.
- **The rekeying bill.** The SHA-1→SHA-256 transition forced a
  reverse-topological rewrite of the entire object graph because trees
  and commits embed names — but "blobs are identical in both formats
  (no references to other objects)"
  ([hash-function-transition](https://git-scm.com/docs/hash-function-transition)).
  Two cheap lessons: **declare the hash algorithm now** (`content_hash`
  is bare sha256 hex, `rows.py:388` — git's failure to declare forced
  disambiguation by digest length), and **keep blob rows leaves** —
  never embed hashes inside payloads — so a future rehash is a table
  rebuild, not a graph rewrite.
- The loose-object pathologies (inode exhaustion at GitHub's 18.6 PB
  scale, pack-mtime granularity forcing cruft packs — 186 GB→2 GB
  in their pathological case,
  [GitHub blog](https://github.blog/engineering/architecture-optimization/scaling-gits-garbage-collection/))
  are **filesystem artifacts a database blob table does not inherit**:
  B-tree pages are the packfile, a timestamp column trivially has the
  granularity cruft packs restore. The portable lesson is only the
  write-fast/compact-later posture and per-object expiry metadata.

### 2.2 Database blob physics — bytes-per-exchange is the real floor

The [db-blob-physics study](studies/2026-07-25-multimodal-storage/db-blob-physics.md)
read SQLAlchemy and the engines at line level:

- **SQLAlchemy has no LOB gating and no byte accounting.** The
  insertmanyvalues enable predicate checks only dialect flags and
  statement shape (`sqlalchemy:lib/sqlalchemy/sql/crud.py:1723-1738`);
  pages are sized by row count and bind-parameter count only
  (`compiler.py:5859-5877`); `max_allowed_packet` appears nowhere in
  the tree. Oracle alone never enables imv and takes driver
  `executemany` array binding with `setinputsizes(DB_TYPE_RAW)`
  (`dialects/oracle/cx_oracle.py:774-779, 1181-1199`). Both regimes
  accept blobs; neither bounds bytes.
- **Per-value ceilings**: SQLite 1 GB default
  (`sqlite:src/sqliteLimit.h:24`); Postgres bytea 1 GB−1 hard
  (`MaxAllocSize`, `postgres:src/include/utils/memutils.h:40`); MySQL
  effectively `max_allowed_packet` (64 MB default) despite LONGBLOB's
  4 GB type cap
  ([packet-too-large](https://dev.mysql.com/doc/refman/8.4/en/packet-too-large.html));
  SQL Server varbinary(max) 2^31−1; Oracle 1 GB per direct bytes bind
  ([python-oracledb LOB guide](https://python-oracledb.readthedocs.io/en/latest/user_guide/lob_data.html)).
- **MySQL is the per-statement floor and is connection-fatal**: the
  whole rendered statement must fit one packet, text-protocol drivers
  escape binary at up to ~2× inflation, and breach closes the
  connection. A 10,000-file batch at 1 MB/file through today's content
  insert (`writes.py:689`) builds ~1 GB imv pages — MySQL dies around
  row 64. **Byte-denominated flush chunking is mandatory**, and even a
  row-count floor of 1 cannot save a single over-budget value — a
  per-value cap with an escape hatch above it is structurally required.
- **The sharpest portability trap**: `LargeBinary` renders plain `BLOB`
  on MySQL — a 65,535-byte cap
  (`dialects/mysql/base.py:2639-2652`) — so any vfs blob column must
  declare `with_variant(LONGBLOB(), "mysql", "mariadb")`.
- **Portable ranged reads exist** as SQL `substr`/`SUBSTRING` on every
  engine — O(slice) on Postgres only if the column declares
  `SET STORAGE EXTERNAL` (`pg_detoast_datum_slice`,
  `postgres:src/include/fmgr.h:236-245`), cheap insurance since media
  bytes are already codec-compressed. Reads have symmetric byte physics
  (MySQL result rows are packet-capped too), so a stored `size_bytes`
  on the blob row lets read planning budget before fetching payloads.
- **Every engine already segments large values out of the narrow row**
  server-side — Postgres TOAST (~2 KB threshold, ~1,996-byte chunks,
  `heaptoast.h:28-89`), Oracle LOB segments, SQL Server LOB allocation
  units, InnoDB overflow pages, SQLite overflow chains. A sidecar blob
  table aligns with engine internals rather than fighting them.

### 2.3 Production storage systems — who keys bytes how, and how GC runs

[SeaweedFS, JuiceFS, OpenDAL, fsspec](studies/2026-07-25-multimodal-storage/storage-systems.md):

- **Neither production system content-addresses blobs.** Both mint ids
  and key bytes by owner, accepting duplicate bytes; JuiceFS adds a
  `sliceRef` refcount table only where sharing actually arises
  (compaction/clone) and reclaims via hourly `WHERE refs <= 0` sweeps,
  never inline zero-crossing deletes (`juicefs:pkg/meta/sql.go:3706-3724`).
- **Unanimous consistency doctrine**: write bytes first, commit the
  reference second, compensate on failure (`juicefs:pkg/vfs/writer.go:
  195-216`) — committed references never dangle by construction;
  orphaned bytes are the accepted failure mode, reclaimed by offline
  reconciliation with multi-hour cutoffs so in-flight writes are not
  mistaken for garbage.
- **Deletion is everywhere deferred and batched**: SeaweedFS queues fid
  deletions (100k/batch, backoff to 6 h,
  `seaweedfs:weed/filer/filer_deletion.go:23-51`) and vacuums on a
  garbage-ratio threshold; JuiceFS honors `--trash-days` retention
  before physical delete (`base.go:3258-3307`). vfs's trash → restore →
  90-day sweep is exactly the reclamation seam blobs should ride.
- **Byte-denominated transfer units by construction**: JuiceFS splits
  files into 64 MB chunks uploaded as ≤4 MB blocks — the block is the
  bounded upload/retry/cache granularity (`cmd/format.go:154-158`) —
  direct precedent for byte-denominated flush chunking.
- **Declared per-backend byte ceilings are established practice**:
  OpenDAL's `Capability` struct declares numeric caps
  (`write_total_max_size` — "Cloudflare D1 has a 1MB total size limit",
  `opendal:core/core/src/types/capability.rs:134-136`) with conservative
  defaults — the exact species of vfs's `DialectProfile` fields.
- **The external escape hatch's contract exists in fsspec**:
  `ReferenceFileSystem` mixes inline bytes and `(url, offset, size)`
  references per key, resolves lazily, and raises a first-class
  `ReferenceNotReachable` carrying both the reference and the failed
  target (`filesystem_spec:fsspec/implementations/reference.py:34-41,
  605-618`).
- **No system studied delta-encodes binary content anywhere**; and the
  Haystack needle/volume apparatus
  ([paper](http://www.usenix.org/event/osdi10/tech/full_papers/Beaver.pdf))
  exists to fix POSIX per-small-file costs a relational DB already
  absorbs — a blob-per-row sidecar table is *not* the naive design
  Haystack fixed. The one genuine prior-art argument *for* hash-keying
  is version economics: unchanged media across versions costs one row
  instead of one blob.

### 2.4 Embedding models — the 2026 landscape, benchmarked

[embedding-models study](studies/2026-07-25-multimodal-storage/embedding-models.md):

- All 2025–2026 frontier multimodal embedders are true-interleaving
  single-tower models; the text-quality tax of joint spaces has
  collapsed **at the API frontier**: voyage-multimodal-3.5 is within
  0.29% of voyage-3-large on a 38-dataset text suite
  ([Voyage](https://blog.voyageai.com/2026/01/15/voyage-multimodal-3-5/)),
  Gemini Embedding 2 scores 67.99–68.17 MTEB vs 68.32 for the dedicated
  text model
  ([Milvus comparison](https://milvus.io/blog/choose-embedding-model-rag-2026.md)).
  But open/self-hosted joint models still pay heavily —
  jina-embeddings-v4 at MTEB-en 55.97
  ([Jina](https://jina.ai/models/jina-embeddings-v4/)).
- **Late-interaction page-image retrieval beats OCR pipelines
  decisively** on visually rich documents (ViDoRe v1 NDCG@5 81.3 vs
  67.0, [ColPali paper](https://arxiv.org/pdf/2407.01449)) and beats
  single-vector joint embedding on the same model (Jina v4: 90.17
  multi-vector vs 84.11 single-vector) — at ~1,024 128-d vectors per
  page (~256 KB fp16, ~64× a single vector) with MaxSim scoring no SQL
  vector type provides. A structurally different index shape; optional,
  not default. Commercially usable open weights exist (ColQwen2
  Apache-2.0/MIT, colnomic-7b Apache-2.0).
- **Audio**: joint text+audio spaces exist in production (Gemini
  Embedding 2 preview, Marengo 3.0 GA) but MAEB (50+ models) shows
  CLAP-lineage models score near random on speech-semantic tasks
  ([MAEB](https://arxiv.org/abs/2602.16008)) — transcribe-then-embed-
  text remains the honest pipeline for spoken content, landing in the
  derived-text-sidecar story. Video mirrors audio: keyframes +
  transcripts are the practical default.
- **Spaces are mutually incompatible even within one vendor**
  (gemini-embedding-001 vs -2,
  [Vertex docs](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/embedding-2));
  production dimensions span 512 (Marengo) to 3,072 (Gemini-2);
  Matryoshka truncation is universal, but truncation width is part of
  the space identity. Model-name tracking is a correctness requirement.
- Media embedding is cheap enough for default-on embed-at-write:
  $0.60/B pixels (Voyage) ≈ $0.0006 per 1M-pixel page. And ViDoRe v3
  shows even the best models stay under 65 NDCG@10 on enterprise
  multi-hop queries
  ([Nemotron ColEmbed V2](https://arxiv.org/pdf/2602.03992)) — the
  schema must permit swapping spaces without migration pain.

### 2.5 Deployed search practice — Immich, PhotoPrism, ColPali, RRF, and
the extraction lineage

[search-practice study](studies/2026-07-25-multimodal-storage/search-practice.md):

- **Immich is the closest living analog to a multimodal glean**: dual-
  path search (metadata filters vs CLIP smart search) over one Postgres
  database, a separate Python ML service embedding at ingest, ANN via
  pgvector/VectorChord — the engine vfs already targets
  ([docs](https://docs.immich.app/features/searching/)). Changing the
  CLIP model forces re-embedding the whole library
  ([discussion #11862](https://github.com/immich-app/immich/discussions/11862))
  — deployed reality is one model-stamped space per modality family.
  Its OCR search category is grep-over-derived-text shipping in a 2026
  media server.
- **PhotoPrism ships competitive photo search with no vector index at
  all** — TensorFlow classification labels projected into ordinary
  metadata search
  ([docs](https://docs.photoprism.app/user-guide/search/)) — proving
  cheap-metadata-plus-labels is a viable floor.
- **ColPali in production**: Vespa binary-quantizes patch vectors,
  retrieves by hamming ANN, MaxSim-reranks inside storage nodes
  ([Vespa blog](https://blog.vespa.ai/scaling-colpali-to-billions/));
  every deployment keeps page images in ordinary blob storage and only
  patch vectors in the index.
- **Reciprocal rank fusion is the universal shipped fusion**:
  `score = Σ 1/(k+rank)`, k≈60, native in Elasticsearch, OpenSearch,
  Azure AI Search, Weaviate, Qdrant; rank-only, no calibration, within
  ~4% NDCG of tuned score fusion
  ([OpenSearch](https://opensearch.org/blog/introducing-reciprocal-rank-fusion-hybrid-search/)).
- **The extraction lineage converged three independent times** (Tika,
  Spotlight, Windows Search) on the same architecture: a detector maps
  bytes to type (magic + extension + container-aware, never filename
  alone), a plugin-per-mime registry maps type to extractor, output
  splits into cheap metadata properties plus a derived text stream, and
  derived artifacts live in the **search system's own store keyed to
  the source item** — `.Spotlight-V100`, SystemIndex/Windows.edb —
  never as sibling files in the user's namespace
  ([Tika detection](https://tika.apache.org/3.0.0/detection.html);
  [Windows indexing overview](https://learn.microsoft.com/en-us/windows/win32/search/-search-indexing-process-overview);
  [Spotlight internals](https://eclecticlight.co/2025/07/30/a-deeper-dive-into-spotlight-indexes/)).
- **Hostile files force process isolation with resource caps**: Tika
  parses in a forked child by default — "avoid running Tika in the same
  process as anything that matters"
  ([Tika robustness](https://cwiki.apache.org/confluence/display/TIKA/The+Robustness+of+Apache+Tika));
  Windows' filter host runs minimal-rights under a job object with a
  100 MB working-set cap
  ([IFilter docs](https://learn.microsoft.com/en-us/windows/win32/search/-search-ifilter-about)).
  Extraction never runs inline with the write path.
- **Extraction failure degrades to metadata-only, never invisibility**
  (Windows indexes minimal system properties when no IFilter exists);
  **freshness is event-driven regeneration** keyed to source change
  plus a periodic full-crawl repair path — and vfs is better placed
  than either OS: writes are transactional, so derived rows keyed by
  `content_hash` regenerate on version change with no journal.

### 2.6 Vector portability — what the engines actually offer, and the floor

[vector-portability study](studies/2026-07-25-multimodal-storage/vector-portability.md):

- **Community MySQL is the sharpest constraint**: it has a native
  `VECTOR` type but `DISTANCE()` is HeatWave/MySQL-AI-only — stock
  MySQL cannot compute any vector distance server-side
  ([MySQL vector functions](https://dev.mysql.com/doc/refman/9.7/en/vector-functions.html)).
  The GENERIC floor is the *only* MySQL story, not a hypothetical.
- **SQL Server 2025**: `VECTOR` (max 1,998 dims) and `VECTOR_DISTANCE`
  are GA; DiskANN indexing is preview-gated; and clients without new
  TDS drivers — including pyodbc — exchange vectors as varchar(max)
  JSON arrays
  ([vector type docs](https://learn.microsoft.com/en-us/sql/t-sql/data-types/vector-data-type?view=sql-server-ver17)).
  vfs's JSON-text serialization is literally SQL Server's documented
  client protocol.
- **Oracle 23ai** has the most complete native story (65,535 dims,
  HNSW+IVF, per-query `TARGET ACCURACY`) and SQLAlchemy models it
  in-tree since 2.0.41 (`sqlalchemy:lib/sqlalchemy/dialects/oracle/
  vector.py:235-366`) — an `oracle_native` branch in `VectorType`
  mirrors `postgres_native` with zero new dependencies. pgvector 0.8.5
  indexes `vector`/`halfvec` only up to **2,000 dims** — a real cap on
  embedding-model choice.
- **The honest floor arithmetic**: published brute-force numbers (FAISS
  flat p95 44.7 ms at 10M×768) are for in-memory SIMD scans; the vfs
  JSON-text floor pays SQL fetch + `json.loads` per row — ~9 KB and
  30–60 µs per 768-d vector, ~92 MB per 10k-vector query. Data motion,
  not arithmetic, binds. Honest interactive ceiling: **~10k vectors per
  query scope** today; **~30–50k** with packed little-endian float32 in
  `LargeBinary` (3 KB, ~1–2 µs parse — the format MySQL's own `VECTOR`
  already uses).
- **Binary sign quantization + oversampled exact rescore** (96 bytes
  per 768-d vector, Hamming prefilter via `int.bit_count`) is the best
  portable narrowing — endorsed by pgvector (`bit` + rerank) and Oracle
  (BINARY format) — raising the honest interactive ceiling to
  ~500k–1M in plain portable SQL. IVF-in-plain-SQL (offline k-means +
  `cluster_id` B-tree probes) is a documented upgrade path, not the
  floor.
- **The gram doctrine ports only partially**: exact-predicate prefilter
  is lossless, but every other narrowing (IVF probes, Hamming,
  truncation) can drop true neighbors — recall < 1 is intrinsic and
  must be declared, never inherited from grep's promise.

### 2.7 vfs storage ground truth — where a sidecar attaches, what it strains

The binding constraints from the
[storage ground-truth study](studies/2026-07-25-multimodal-storage/vfs-storage-ground-truth.md):

- **The sidecar direction is forced, not chosen**: the body column is
  `_body_text()` with UTF-8 collation pins (`rows.py:210-220, 374`) and
  the model rejects null bytes (`entry.py:132-139`); bytes cannot ride
  it. Precedent for a model-less binary table exists (`posting_list`,
  `rows.py:473-483`), but the drift test protects only modeled fields —
  a model-less blob table forfeits the schema/model lockstep guard.
- **`CONTENT_KINDS` does four incompatible jobs** — text-read gate
  (`reads.py:255`), content routing (`writes.py:684`), edit gate
  (`editing.py:36-38`), `size_bytes` nulling (`entry.py:430-431`) — and
  no single membership set serves media: the set must split, or a
  channel discriminator must reach all four sites.
- **`size_bytes` is 32-bit `Integer`** on entries and versions
  (`rows.py:351, 390`) — an implicit 2 GiB ceiling below several
  engines' LOB caps; silent overflow otherwise.
- **The strongest code-grounded argument for hash-keying is copy, not
  dedup**: `_execute_copy` physically duplicates content bodies inside
  the serialized topology transaction (`topology.py:956-963`), while
  `content_hash` is already in `_SUBTREE_COLUMNS` and reproduced free
  (`topology.py:98, 941`). The decisive argument against is GC: writes
  race the sweep by design (§1 fact 3); refcounts are a hot-row funnel
  that does not compose with the whole-method retry discipline
  (`backend.py:19-25`); serializing blob writes with sweep repeals the
  designed concurrency.
- **Trash and restore ride free under either keying** — reparent and
  move touch only entries rows (`topology.py:727-748, 845-884`);
  entry-keyed blobs close the whole lifecycle as one more DELETE at
  the single hard-delete chokepoint `_purge_subtree`.
- **Staging is buy-the-whole-batch**: all bodies sit in `StagedEntry`
  RAM before execution (`staging.py:50`) — the per-row cap and the 10k
  contract multiply (a 10 MB cap is a 100 GB worst-case staged batch).
- **`_replace_content` rewrites unchanged bodies** (delete-then-insert,
  `writes.py:676-689`) and `_fetch_committed` does not fetch
  `content_hash` (`writes.py:235-242`) — entry-keyed blobs need that
  column fetched to skip no-op rewrites; hash-keying gets the skip
  structurally. Hash-keyed insert-if-absent must follow the per-dialect
  arbitration split, and `catch_retry` engines re-send payload bytes on
  savepoint retries precisely when dedup hits.
- **`_execute_copy` never copies `external_id`**
  (`topology.py:905-907`) — a reference-not-bytes escape hatch silently
  loses its pointer on copy today.
- **The chunks table is structurally ready** to home derived text for
  media entries with zero schema change (entry-keyed, NOT NULL text
  body, embedding column, `rows.py:398-417`) — but `Chunk.line_start`
  semantics are undefined for media, and staleness must wire to the
  blob pass.

### 2.8 vfs search ground truth — the four verbs over media, verified

[search ground-truth study](studies/2026-07-25-multimodal-storage/vfs-search-ground-truth.md):

- **glob** consumes only namespace metadata and already projects
  `mime_type`/`kind` in output rows (`reads.py:51-53`) — but has **no
  mime or kind predicate**; a mime-prefix filter backed by the existing
  `mime_type` column and `ix_ext_kind` index (`rows.py:348, 359`) is
  the one concrete addition media needs, on whichever axis the
  exclusivity rule picks.
- **grep** can never match raw media by type fact: the pattern and
  corpus are `str`, bytes cannot reach the matcher, and the verify step
  *is* the contract. Derived-text chunks on a media entry **just work
  for candidate generation and embedding** — chunk linkage is identity
  (`entry_id`), never text lineage; posting-list doc-ids are chunk PKs.
  They do **not** just work for verify/context/invert/count semantics,
  which are defined per file and need a whole-document text fetch a
  media entry's content-less row cannot serve — the derived-text home
  is a **grep-correctness choice**, not just a storage choice.
- **The false-negatives-never doctrine over media, stated exactly**: a
  media entry with no derived text gives the authoritative matcher no
  text — invisibility is the contract, not a false negative (the scan
  tier already implements it, `memory.py:277`). But once derived text
  exists it *is* corpus, and stale derived text becomes a real false
  negative — freshness is a grep-soundness requirement riding the
  existing `encoded` flag, epoch watermark, and `grep_staleness` trait.
- **glean**: embeddings attach only to chunk rows; model identity is
  type-level, not row-level (`VectorType(model_name=...)` per column,
  `vector.py:210-226`, `rows.py:318-328`) — filter-by-space is
  impossible today, and native vector columns are fixed-dimension, so
  multiple spaces can never share one column. But the verb contract
  already licenses fan-out-and-fuse: backends "fuse the rankings
  however they see fit" with scores only loosely comparable
  (`base.py:1127-1135`). **No verb-signature change needed** except
  query-by-example, which `glean(query: str)` cannot carry.
- **graph — verified unchanged**: edges are narrow ID triples with no
  path/content/kind dependency (`rows.py:419-435`); `Edge` validates
  endpoints only as non-root non-meta paths (`edge.py:35-48`); media-
  derived edges (`derived_from`, `depicts`, `thumbnail_of`, `page_of`
  with confidence in `weight`) need zero schema additions.

## 3. Storage synthesis: the brief's questions 1–6 settled

### Q1 — The blob home: entry-keyed now, hash-ready by construction

**Recommended: a binary sidecar table beside `content`, entry-keyed,
carrying `content_hash` (bare sha256 of raw bytes) and `size_bytes`
(BigInteger) as resident non-key columns — so a later migration to
hash-keying is data motion, not a schema break. Blob GC is thereby
deferred, not designed away; the migration triggers are named below.**

The argument, from both sides honestly:

- **Hash-keying wins three things**: copy (byte duplication inside the
  serialized topology transaction is the strongest code-grounded
  argument, `topology.py:956-963` — hash-keyed copy is a free pointer
  reproduction); version economics (unchanged media across versions
  costs one row, the one genuine prior-art argument for content
  addressing); and idempotent overwrite (same hash → insert-if-absent
  no-ops). git proves the shape end-to-end, and its GC translates to
  SQL as one chunked `NOT EXISTS` anti-join under the sweep verb plus a
  short insert-grace predicate — genuinely small (§2.1).
- **Entry-keying wins the lifecycle**: `_purge_subtree` is the single
  hard-delete chokepoint (permanent delete, sweep, move-over-occupant,
  `topology.py:173, 313, 866`); entry-keyed blobs attach as one more
  `DELETE ... WHERE entry_id IN (chunk)` and the whole trash → restore
  → sweep story closes with zero new concepts. Hash-keyed blobs make
  that chokepoint insufficient and mandate a GC verb that races the
  tree's own documented write/topology concurrency (§1 fact 3) — the
  honest fix is a git-style grace window, but it is a new concurrency
  design, an arbitration story per dialect (with `catch_retry` engines
  re-sending payload bytes on dedup conflicts, §2.7), and a model-less
  table with no drift guard. Refcounts are named and rejected: a hot
  row per popular hash (10,000 files sharing one logo = 10,000 updates
  to one row), a deadlock generator on `catch_retry` engines, and
  incompatible with the whole-method retry discipline.
- **Prior art tips the start, not the end**: neither SeaweedFS nor
  JuiceFS content-addresses (both key by owner; refcounts only where
  sharing actually arose, reclaimed by periodic sweeps, §2.3), while
  git shows the hash-keyed destination is reachable and its SQL GC is
  cheap. Dedup is a choice about version economics, not a correctness
  requirement — and the version flow is unwired today (§1 fact 1), so
  the economics do not bite yet.

The hybrid keeps every option open at near-zero cost: hash raw bytes
only (mime out-of-band, dedup survives relabels — git's lesson
inverted, §2.1), keep blob rows leaves (no hashes inside payloads, so
any future rehash is the easy half of git's problem), and declare the
algorithm. **Migration triggers to record in the ADR**: the version
flow landing (media versions should be hash references, Q4), or
measured copy pain on media subtrees inside the serialized topology
section.

Two obligations land immediately with entry-keying: `_fetch_committed`
must fetch `content_hash` so an unchanged hash skips the blob rewrite
(the blob-era phrasing of metadata-writes-never-rewrite-content:
**an unchanged hash rewrites no blob row**), and the blob table needs
either a small model or a declared-columns pin so the drift test's
lockstep guard is not silently forfeited (§2.7).

### Q2 — Dialect physics: two new byte-denominated DialectProfile fields

**Recommended: extend `DialectProfile` with `payload_byte_budget` (max
accumulated bind-payload bytes per flush statement) and
`value_byte_cap` (per-value refusal line feeding the external escape
hatch), with a `flush_budget` helper taking the tightest of
rows/params/bytes — the `membership_budget`/`chunked` pattern extended
to a bytes denominator.**

This is doctrine-compatible by construction: SQLAlchemy models neither
packet caps nor LOB-bind budgets (§2.2 — `max_allowed_packet` appears
nowhere in the tree), which is exactly the declared-profile-field test.
The two fields are independent — one is an exchange bound, the other a
refusal contract — and neither is derivable from the other. Suggested
declarations from the study: GENERIC and MySQL floor **16 MB** for
`payload_byte_budget` (half the default 64 MB packet to absorb ~2x
text-protocol escape inflation, halved again for SQL overhead and
headroom); 32–64 MB on engines without a
protocol wall, where the budget bounds client/server memory rather
than a hard cap. The flush loop accumulates `len(bytes)` greedily and
cuts a statement before the budget is crossed; row-count and parameter
budgets remain secondary caps. JuiceFS's ≤4 MB block is the production
precedent for byte-denominated transfer units (§2.3).

Non-negotiable DDL facts riding along: the blob column carries the
`LONGBLOB` variant on MySQL (the 64 KB `BLOB` trap, §2.2);
`SET STORAGE EXTERNAL` on the Postgres blob column at table creation
(ranged reads become O(slice); media bytes are already
codec-compressed, so disabling TOAST compression loses little);
`size_bytes` stored beside the bytes so bulk reads budget before
fetching; no RETURNING of blob columns on Oracle; `fast_executemany`
never used for blobs (documented unfit, `dialects/mssql/pyodbc.py:
307-314`). Oracle's executemany allocates one buffer per column sized
to the largest value in the array — one more reason to flush media
rows in small byte-bounded groups.

### Q3 — Size ceilings and the external escape hatch: declare now, defer
the resolver

**Recommended: declare `value_byte_cap` now as the portable per-value
refusal line — sized jointly with the staging posture, not
independently — and declare the escape hatch above it as
reference-not-bytes via `external_id`, projected on the wire as
`resource_link`, with the resolver deferred. Migrate `size_bytes` to
`BigInteger` regardless.**

The coupling is the finding: staging holds every body in RAM before
execution, so cap × 10,000 is the worst-case batch footprint (§2.7).
Either the portable cap is small (single-digit-to-16 MB — the honest
MySQL-shaped floor anyway, §2.2) or the write path grows a
byte-budgeted sub-batch/streaming admission the current plan shape does
not have. The ceiling and the batch contract cannot be chosen
independently; the ADR must pin them together. The 32-bit `Integer`
metrics columns (2 GiB, `rows.py:351, 390`) sit below several engines'
LOB caps — migrate to `BigInteger` so the declared cap, not silent
overflow, is the binding line.

The escape-hatch contract comes assembled from prior art: OpenDAL shows
byte ceilings as declared per-backend capabilities with conservative
defaults; SeaweedFS shows size tiering as a single deployment-config
knob decided by the storage layer at write time, never per call;
fsspec shows the external tier as pure reference + lazy resolution + a
typed dangling error naming both the reference and the failed target
(§2.3). Two seams must be recorded even in deferral: `_execute_copy`
drops `external_id` today (§2.7) — a copy of an escape-hatch entry
silently loses its bytes pointer — and the wire projection of the hatch
is the sibling memo's `resource_link` + `size` posture
([result-content memo](2026-07-25-multimodal-result-content.md) Q5).

### Q4 — Binary versioning: snapshot-only, and pack gains a clause

**Recommended: snapshot-only media versions — no binary delta engine —
with the Version model growing a third lawful payload state
(hash-reference: no payload, lean on `content_hash`) when the version
flow lands; `pack` skips media entries via the channel discriminator.**

The evidence is unanimous and mutually reinforcing. git deltas binaries
mechanically but deliberately turns deltas off for large media
(`core.bigFileThreshold`, the `-delta` attribute, §2.1) — snapshot +
dedup is git's own doctrine for exactly this content class, and content
addressing captures the dominant saving without a delta engine. No
production storage system studied diffs binary content anywhere:
overwrite writes new slices/needles and old bytes ride deferred
deletion; JuiceFS compaction merges references, never diffs (§2.3).
And the vfs versioning provider is irreducibly text-shaped — `difflib`
over `str.splitlines`, `unidiff` replay (`versioning.py:48-113`) —
bytes are type-unrepresentable in it, not merely ill-served.

Because nothing mints version rows yet (§1 fact 1), the entire cost of
the hash-reference version shape is the model change: `Version`
enforces snapshot XOR diff today (`version.py:78-80, 119-125`), and a
reference row is a third state it forbids. That model change is also
the moment hash-keying earns its keep (Q1's migration trigger): under
entry-keying, media versions duplicate bytes per version (a 10-version
100 MB asset stores 1 GB — git's loose-object full-copy problem
re-bought); under hash-keying the version row *is* the reference and
unchanged media costs zero. Either way `pack`'s contract gains a clause
— text channel only — not a binary diff engine; binary delta remains
possible later behind `VersionProvider` pluggability, but nothing in
the corpus asks for it.

### Q5 — The exclusivity rule: model-owned, storage-routed, one
discriminator

**Recommended: text XOR bytes per entry, decided at construction from
kind/mime, carried as a channel discriminator that all enforcement
sites consult — the model owns the invariant, storage only routes.**

The model change is the largest in the story and it is a carve-out, not
an addition: `_derive_and_measure` must stop normalizing a media
entry's absent text to `""` (§1 fact 2), `_derive_identity`'s
arbitration table grows a media column (explicit text content + media
mime = contradiction), metrics split (`size_bytes`/`content_hash` from
raw bytes, `lines` never computed), and `with_content` gets a bytes
twin or a refusal (`entry.py:171-191, 219-227, 304-327`). Hashing raw
bytes — not typed payloads — keeps mime a mutable out-of-band column
and dedup intact across relabels (§2.1).

Storage-side, the four `CONTENT_KINDS` jobs cannot be served by any
single membership set (§2.7): the text-read gate must refuse text reads
of media (today a media entry would pass the gate and return
normalized-empty text, `reads.py:253-256`), routing must send bytes to
the blob channel, the edit gate must refuse media unconditionally, and
`size_bytes` must survive for media. The discriminator answers all
four, and two more things besides: it is the axis glob's new predicate
filters on (§2.8), and it makes the one-canonical-join rule
well-defined — the channel must be knowable from projection/params
*before* the join is built, or "join by channel" quietly becomes
"always join both," dragging a LOB table into every content-projected
plan (§2.7). Whether the discriminator is a new kind, a mime test, or a
stored enum is an ADR decision; the constraint is that it exists, is
derived at construction, and is consultable at all enforcement sites
and in read planning. This is the same structural-exclusivity rule the
result-content memo's F2 demands at the envelope — one rule, both
layers.

### Q6 — Derived text: the system's own store, keyed to the source
version, readable as a document

**Recommended: derived text (OCR, transcripts, captions) lives in the
storage/search layer's own store keyed to the media entry and the
source `content_hash` — a derived-documents table the grep executor can
fetch whole, from which ordinary chunk rows are minted — never as
visible sibling entries in the namespace. Producers are a
detect-then-extract plugin-per-mime registry running isolated and
timeout-bounded off the write path, degrading to metadata-only on
failure; freshness is regeneration keyed to `content_hash` change with
a sweep-style repair pass.**

The precedent is unanimous on the home: Spotlight, Windows Search, and
the Tika pipeline all keep derived artifacts in the search system's own
store keyed to the source item, never beside it in the user's namespace
(§2.5) — which rules out hidden sibling entries (and with them the
lifecycle-critical `derived_from` edge cascade they would require,
§2.8). The chunks table alone is *almost* the answer — derived-text
chunks on a media entry violate no invariant and feed grams and
embeddings unchanged (§2.8) — but grep's verify/context/invert/count
semantics are defined per file and need a whole-document fetch that
per-chunk text cannot serve without breaking context windows across
chunk boundaries. That is why the home is a document-shaped table, with
chunks minted from it exactly as they are minted from `content`. Match
regions over media then address the derived document, and the result
must say so — the anchored-region vocabulary is the sibling memo's B4
seam, shared.

The producer contract imports three binding lessons (§2.5): extraction
runs isolated (forked/sandboxed, resource-capped — Tika's "avoid
running Tika in the same process as anything that matters"), never
inline with the write path; failure degrades to metadata-only, never
blocks ingest or hides the entry (unknown formats stay globbable —
Windows' minimal-properties fallback); detection dispatches on
magic/container-aware type, never filename alone. Freshness is where
vfs beats its precedents: writes are transactional, so "derived rows
keyed by `content_hash`, regenerated on version change" needs no
fsevents/USN journal — only the sweep-style repair pass as the honesty
backstop. And freshness is not hygiene: once derived text exists it is
corpus, and staleness is a grep false negative (§2.8) — the wiring
rides the existing `encoded` flag, epoch watermark, and
`grep_staleness` trait.

## 4. Search synthesis: the brief's questions 7–10 settled

### Q7 — Per-verb meaning over media

The four verbs partition cleanly; one sentence each, then the table:

- **glob** matches *names and metadata* — media joins the day entries
  exist; the one addition is a mime-prefix predicate (and a kind
  predicate if the exclusivity axis is kind), because extension is a
  proxy that lies exactly where media lies.
- **grep** matches *stored text* — media participates exactly by
  carrying derived text; a media entry with no derived text is not in
  the corpus and matches nothing, **by contract, not by accident**.
- **glean** ranks *indexed representations* — media joins by being
  embedded into some space; the fusion contract already covers many
  spaces, the schema does not yet.
- **graph** walks *identities* — media joined the day it got an
  `entry_id`; verified unchanged (§2.8).

| Verb | Media meaning | What exists | What's needed |
|---|---|---|---|
| glob | name/mime/kind/size filtering — the unconditional tier | live on both backends; mime/kind projected in rows | mime-prefix predicate on the exclusivity axis (`rows.py:348, 359`) |
| grep | Python `re` over derived text; whole-document verify + context | chunk/gram machinery accepts derived-text chunks unchanged | derived-documents home (Q6); Match regions declared as addressing derived text; freshness wiring |
| glean | per-space top-k + rank fusion over text and media spaces | verb contract licenses fusion; `Vector` tracks model+dim per type | space registry, space-keyed embeddings store, fan-out + RRF; optional multi-vector shape |
| graph | edges to/from media entries; extraction as edge producer | edges are identity triples — works by construction | nothing (media-derived edge types are just data) |

grep-over-derived-text is not an extension to justify — it is the
25-year default, precedented by name: Windows Search's inverted index
over IFilter text (1996→), Spotlight's `kMDItemTextContent` (2005→),
the Tika→Solr/Elasticsearch pipeline, Immich's OCR category (2025–26)
(§2.5). PhotoPrism adds the floor lesson: classification labels
projected into metadata search are a real alternative tier — content
understanding can land as derived *metadata*, not only as embeddings.

### Q8 — One space or many: multi-space fan-out-and-fuse, with
single-space as the degenerate case

**Recommended: design glean as per-space query fan-out (embed the
query once per space present in scope), per-space top-k, and
reciprocal-rank fusion — with a one-space corpus served as the
degenerate single-fan case of the same code. A space registry (model
name → dimension → covered kinds) plus a space-keyed embeddings store
with row-level model identity are the schema additions; the verb
signature does not change.**

The benchmark evidence cuts both ways and the architecture must honor
both (§2.4). For one joint space: voyage-multimodal-3.5 within 0.29% of
the flagship text embedder; Gemini Embedding 2 at MTEB parity with its
dedicated text sibling — for a fresh text+image corpus on a frontier
API model, one joint space is now a defensible default. Against
assuming it: open/self-hosted joint models pay a large text tax (Jina
v4 at 55.97 MTEB-en); audio and video have no shared space with any
text space (and MAEB shows no audio model bridges acoustic and
linguistic meaning — transcripts through the text space are the honest
spoken-content story); the document-image quality frontier is
multi-vector late interaction, a structurally different index (~1,024
vectors/page, MaxSim above SQL); and corpora accrete history — an
existing text corpus embedded with model A cannot be queried through
model B without full re-embedding, which is Immich's deployed re-embed
cliff (§2.5). Spaces are mutually incompatible even within one vendor;
cross-space cosine is noise; model-name mismatch is a correctness bug.

vfs anticipated the identity primitive — `Vector[dim, model]` and
`VectorType`'s model-name validation (`vector.py:64-97, 210-226`) — but
the tracking is type-level only: no row can say which space its vector
lives in, and fixed-dimension native columns cannot share spaces
(§2.8). The missing pieces are plural: the registry, a side-table keyed
`(chunk_id, space)` (mirroring how `posting_list` already sits beside
chunks as a regenerable store), per-space native projections where the
engine offers them, and — reserved, not built — a multi-vector
`(chunk_id, seq, vector)` shape so late interaction is not foreclosed
(every ColPali deployment keeps page images in blob storage and only
patch vectors in the index, §2.5). RRF is the fusion because it is the
universal shipped answer for incompatible score scales — rank-only, no
calibration, within ~4% of tuned fusion — and because glean's contract
already disclaims score comparability. Engine caps constrain model
choice and belong in declared per-dialect knowledge: pgvector indexes
only to 2,000 dims, SQL Server's type caps at 1,998 — a 3,072-dim
space is storable but not ANN-indexable on the reference engine
(§2.6). The one genuinely new input is query-by-example; a
path-as-query convention would fit the existing signature, and the ADR
should decide whether it enters scope or is declared deferred.

Two amendments to the brief's framing from Q6 and Q7: derived-text
sidecars are not a fallback — they are the *entire* audio/video search
story today (transcripts feed the existing text space); and media
entries with neither derived text nor a media-space embedding are
glob/graph-only, which the contract should state rather than hide.

### Q9 — The portable ANN floor, stated with its ceiling

Following the dialect doctrine (unknown engines are served at a
conservative floor, never refused), the floor that survives the survey
(§2.6):

> **GENERIC floor**: vectors stored in a portable column — packed
> little-endian float32 in `LargeBinary` recommended over today's
> JSON text — scoped by exact predicates first (path subtree, mime,
> mount), then exhaustively scanned and exactly scored client-side.
> Recall is 1.0 by construction. The honest ceiling is a
> **per-query-scope** vector count: ~10k interactive today (JSON),
> ~30–50k with binary packing; beyond that the floor still serves,
> degrading in latency, never in correctness — and the Result should
> carry a degradation note rather than the backend refusing.

Three reframings matter as much as the statement. First, the floor is
not a hypothetical for unknown dialects: **community MySQL lives on it
permanently** — its native `VECTOR` type cannot compute a distance
server-side (§2.6). Second, the ceiling is per query *scope*, not per
corpus: glean's paths parameter makes scope prefilter the primary
scaling lever, and filter-then-exact has zero recall loss — the exact
problem native engines needed iterative index scans to fix, dissolved
at the floor. Third, there is a cheap tier between floor and native
ANN: server-side exact KNN via GA distance functions (pgvector
unindexed, Oracle exact, SQL Server `VECTOR_DISTANCE` through plain
pyodbc JSON binding — vfs's JSON serialization is literally that
protocol). Above that: native ANN per dialect (pgvector HNSW, Oracle
via SQLAlchemy's in-tree `VectorIndexConfig`, SQL Server DiskANN when
GA), and portable narrowing — binary sign quantization + oversampled
exact rescore to ~500k–1M — for engines stuck at the floor at scale.

One doctrine boundary must be declared: the gram-planner promise
("false positives OK, false negatives never") ports only for the
exact-predicate prefilter. Every other narrowing — IVF probes, Hamming
prefilter, Matryoshka truncation — can drop true neighbors; recall < 1
is intrinsic and must be a declared property of the tier, never an
inherited assumption. Two facts become declared per-dialect knowledge
where vector config lives: dimension caps and distance-function
availability — SQLAlchemy takes no position on either for three of the
five engines.

### Q10 — Lifecycle: everything derived cascades; everything stale is
named

**Blobs**: trash and restore ride free — namespace verbs touch only
entries rows, which is the segmentation doctrine paying off (§2.7).
Under the recommended entry-keying, sweep purges blobs at
`_purge_subtree` with the bucket; under a future hash-keying, sweep of
version rows is git's ref deletion (blobs untouched, restore-before-
sweep relinks hashes at zero byte cost) and blob GC rides as a bounded
anti-join arm downstream of sweep, never inside it (§2.1, §2.7).

**Derived artifacts and vectors are cache, not truth**: rebuildable,
keyed to content identity, cascading with the source. Every studied
system drops index entries when the source goes (§2.5); vfs's cascade
is structural if derived documents and embeddings are FK-keyed to the
media entry — they die at the same `_purge_subtree` chokepoint. The
staleness idioms already exist and only need wiring: derived text
regenerates on `content_hash` change (grep soundness, §2.8); embedding
staleness is `embedding IS NULL` per space — which is why vectors must
be per-`(space, chunk)` artifacts keyed to a content version, so one
space re-embedding does not invalidate another; gram staleness rides
the `encoded` flag and epoch watermark; and a sweep-style repair pass
backstops all three, the honest answer every event-driven system also
ships (§2.5).

**Metrics for bytes**: `size_bytes` yes (from raw bytes; BigInteger,
Q3); `lines` never — `Observation` already has no `lines` mirror and
nulls content metrics for non-content kinds (`entry.py:384-397,
412-434`), so the wire shape is already correct; only the `entries.
lines` column stores a vacuous 0, which the ADR should declare
meaningless for the media channel rather than fix.

## 5. The owner's hypothesis, evaluated

The hypothesis: **segment multimodal content out in storage** — a
binary sidecar beside the text `content` table, not a widening of it,
extending the segmentation move the schema already made once.

**Confirmed, with three amendments.** Confirmed from four independent
directions: the model layer *forces* it (the text body column carries
UTF-8 collation pins and null-byte rejection — bytes cannot ride it
even badly, §2.7); every engine already does it internally (TOAST, LOB
segments, overflow pages — the sidecar aligns with engine storage
managers rather than fighting them, §2.2); every production system
draws the same metadata/bytes line (SeaweedFS filer vs volumes, JuiceFS
SQL rows vs object-store blocks, §2.3); and the Haystack critique — the
one serious argument that blob-per-row is naive — dissolves because the
relational engine already provides the packed pages, id index, and
compaction that needles/volumes rebuilt on POSIX (§2.3). The
segmentation also pays its promised dividend: because bodies live off
the narrow row, trash/restore/move never touch bytes, and
metadata-writes-never-rewrite-content extends to media by construction.

The amendments:

1. **Segmentation alone is not the hard part — dialect byte physics
   is.** The sidecar table is the easy half; the genuinely new work is
   the byte-denominated flush budget, the per-value cap coupled to
   staging memory, the LONGBLOB variant, and the per-engine DDL facts
   (Q2, Q3). A sidecar landed without those is correct on SQLite and
   connection-fatal on MySQL at the 64th row.
2. **The segmentation must be structural at the model layer, not just
   the schema layer.** The exclusivity rule is a carve-out of the
   empty-string normalization plus a split of `CONTENT_KINDS`' four
   jobs (Q5); without the model change, the storage sidecar stores
   bytes for entries the read path still serves as empty text.
3. **The sidecar should be hash-ready even though it starts
   entry-keyed.** Resident `content_hash` (raw-bytes sha256, declared
   algorithm), blob-rows-as-leaves, and `size_bytes` beside the bytes
   cost nothing now and convert the hash-keying migration — which the
   version economics will likely eventually demand — from schema break
   to data motion (Q1, Q4).

## 6. Adversarial pass: the recommendation vs the production posture

The recommended design (entry-keyed hash-ready sidecar, byte budgets,
channel discriminator, derived-documents table, multi-space glean,
exact-scan floor) walked against the postures that bind.

- **10,000-file batches on the least generous engines.** The flush
  budget saves the statements, but **staging memory is the unresolved
  multiplier**: `StagedEntry` buys the whole batch in RAM before any
  statement runs (`staging.py:50`), so cap × 10,000 is the footprint —
  a 16 MB cap admits a 160 GB worst-case batch. The ADR must pin the
  cap and the admission posture *together*: either a small cap with a
  documented worst-case bound, or a byte-budgeted sub-batch/streaming
  write path the current plan shape does not have. On Oracle,
  executemany buffers are sized per column to the largest value in the
  array — mixed tiny/huge rows in one array waste
  `arraysize × max_row_bytes`; flush groups must be byte-homogeneous-
  ish, not just byte-bounded. On MSSQL, the 2,099-parameter budget
  already binds and `fast_executemany` must stay off for blobs.
- **The drift test.** It guards only modeled fields; a model-less blob
  table (the `posting_list` precedent) forfeits schema/model lockstep
  silently. The ADR must choose: a small blob model joining the
  homed-fields constants, or an explicit declared-columns pin test.
  Same decision again for the derived-documents table and the
  embeddings side-table — three new tables, three lockstep decisions.
- **Metadata-writes-never-rewrite-content.** Already violated in
  spirit by `_replace_content`'s unconditional delete-then-insert —
  invisible at text sizes, material at blob sizes. The blob-era
  phrasing must be pinned: an unchanged hash rewrites no blob row,
  which requires `content_hash` in the committed snapshot fetch
  (`writes.py:235-242`). Without it, every no-op media overwrite
  rewrites the payload and the invariant is marketing.
- **False-negatives-never.** Two ways to break it. Stale derived text:
  once derived text exists it is corpus, and an unregenerated
  transcript after a media rewrite is a real false negative — freshness
  wiring (content_hash trigger + repair pass) is soundness, not
  hygiene. Vector narrowing: any glean tier that narrows beyond exact
  predicates has recall < 1 intrinsically; the contract must declare
  per-tier recall posture, or the gram doctrine's promise silently
  leaks into a domain where it cannot hold.
- **Sweep/GC races.** Entry-keying avoids the race class now — that is
  half the argument for it. But the design must not *re-import* it by
  accident: if the ADR adopts hash-keying later, the GC arm needs the
  grace-window predicate (insert-grace against separate-statement dedup
  upserts), must run downstream of sweep rather than inside it, and
  must never be refcounts (hot-row funnel, retry-discipline
  incompatibility). And the dedup insert-if-absent path on
  `catch_retry` engines re-sends payload bytes on savepoint retries
  precisely when dedup is working — a probe-first pass shrinks but
  cannot eliminate it; the cost belongs in the ADR's price list.
- **The escape hatch's silent seam.** `_execute_copy` drops
  `external_id` today — under a declared-and-deferred hatch, a copied
  oversized-media entry silently loses its bytes pointer. Declaring the
  hatch obligates fixing the copy path in the same landing, resolver or
  no resolver.
- **The one-canonical-join rule.** Two sidecars (content, blobs) plus a
  derived-documents table threaten "always join everything." The rule
  survives only if the channel is knowable from projection/params
  before the join is built — which is the exclusivity discriminator
  doing double duty. If the discriminator lands late, every
  content-projected read on Oracle drags LOB locators into the plan.
- **The floor's multiplication.** Multi-space glean multiplies the
  exact-scan cost per space present in scope — three spaces at 10k
  scope is three fetch+scan passes. Scope prefilter and per-space
  kind-coverage (a space that doesn't cover media kinds is skipped) are
  the mitigations; the degradation note must name which spaces were
  scanned and at what posture, or the honesty contract quietly erodes.
- **The 2 GiB trap.** `size_bytes` as 32-bit `Integer` on entries and
  versions overflows silently on engines that don't range-check binds.
  BigInteger migration is cheap now, expensive after data lands.

Net: the design survives with no new algebra, no new verb signatures,
and one deferred concurrency design (blob GC) — at the price of a
handful of pins the ADR must state explicitly, listed next.

## 7. Open questions — what the storage-bytes ADR must decide

1. **The blob table shape**: name; entry-keyed with resident
   `content_hash` + `size_bytes` (BigInteger) as recommended, or
   hash-keyed now; modeled vs model-less with a declared-columns pin;
   the `LONGBLOB` variant; `SET STORAGE EXTERNAL` on Postgres.
2. **The channel discriminator**: new kind vs mime-derived vs stored
   enum; its derivation at construction; the four enforcement sites;
   its availability to read planning (one-canonical-join) and to glob's
   new predicate.
3. **`payload_byte_budget` and `value_byte_cap`**: per-dialect values,
   the GENERIC floor, the `flush_budget` helper shape, and the MySQL
   escape-inflation margin.
4. **The staging posture**: the cap × 10,000 coupling — small cap with
   documented bound, or a byte-budgeted sub-batch/streaming admission
   path; whether the batch contract for media differs from text.
5. **The external escape hatch**: the cap that triggers it; the
   `external_id` copy fix; the typed dangling-reference error shape
   (fsspec's both-names contract); resolver deferred or scoped.
6. **The Version model's third payload state** (hash reference): when
   it lands relative to the version flow; pack's text-channel-only
   clause; whether media version rows are legal before hash-keying.
7. **Hash discipline**: `content_hash` declared as sha256-of-raw-bytes;
   the algorithm-migration note; the blob-rows-are-leaves rule (no
   hashes inside payloads, anywhere).
8. **The hash-keying migration triggers**: version-flow landing and/or
   measured copy cost; the GC design that comes with it (grace-window
   anti-join downstream of sweep; refcounts rejected on the record).
9. **The derived-documents home**: table shape keyed to
   `(entry_id, source content_hash)`; how chunks mint from it; the
   region vocabulary replacing line ranges for media (pages, time
   ranges, bboxes) shared with the result-content memo's anchor type;
   how Match declares it addresses derived text.
10. **The extraction registry**: plugin-per-mime detect-then-extract
    contract; the isolation/timeout/resource-cap requirements; the
    metadata-only degradation rule; the freshness trigger and the
    repair pass's home in sweep.
11. **The embedding-space registry and side-table**: schema keyed
    `(chunk_id, space)` with row-level model identity; per-space native
    projections; per-space kind coverage; the reserved multi-vector
    shape; per-dialect declared dimension caps and distance-function
    availability.
12. **The portable vector serialization**: switch from JSON text to
    packed little-endian float32; endianness declaration; the floor
    statement and the Result degradation note's shape (which spaces,
    what posture, what scope size).
13. **glean's query-by-example**: in scope via path-as-query, or
    declared deferred.
14. **The media chunk shape**: relax the chunk row (nullable content,
    region columns) vs a parallel media-chunk table — settled together
    with question 9, since both decide what a "chunk" of a PDF page or
    an audio window is.
15. **Metrics declarations**: `size_bytes` BigInteger migration;
    `lines` declared meaningless for the media channel; what `wc`-shaped
    output reports for media entries.
