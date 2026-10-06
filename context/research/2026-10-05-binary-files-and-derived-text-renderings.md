# Binary files in vfs: bytes as the body, a derived text rendering as the searchable form

- **Status:** research memo (commits us to nothing). Answers the storage
  half the July multimodal memo left open as its first prerequisite
  (`2026-07-25-multimodal-result-content.md` §6 question 1: "where binary
  content lives"). Feeds an ADR on binary bodies and renderings, then a
  spec.
- **Date:** 2026-10-05
- **Owner:** Clay Gendron
- **Question:** How do images, docx, xlsx, pptx and PDF files fit the vfs
  model? Clay's sketch, 2026-10-05: store the file's bytes in a new blobs
  table; run a converter that writes a text rendering of the file into
  the existing content table for the same entry; let chunking, grep,
  glean and link extraction run on that text unchanged; for an image the
  rendering is a written description. The sub-questions this memo had to
  settle: what keys a rendering and when it is rebuilt; whether it is
  versioned, editable, or bounded; what the entry row's hash and size
  describe; what text each format becomes and how a line maps back to a
  page; what happens with no converter, a failed converter, or a hung
  one; how a 10,000-file ingest stays bounded; what the blob column is
  on five engines; and whether an image's rendering is a caption, an
  image vector, or both.
- **Method:** seven parallel read-only studies of sixteen reference
  checkouts, plus one executed experiment (SQLite blob throughput and
  row layout), all under
  `studies/2026-10-05-binary-renderings/`: `renditions.md` (git
  `textconv`, Jackrabbit Oak's extracted-text cache, Nuxeo renditions and
  fulltext), `paperless.md` (paperless-ngx's document row),
  `tika.md` (Apache Tika's parser seam, limits and status model),
  `markdown-renderers.md` (MarkItDown and Docling output),
  `framework-converters.md` (haystack, llama_index, langchain
  converters), `images.md` (Immich's ML pipeline, fastembed's image
  models), `blob-storage.md` (SQLite, Postgres, the SQLAlchemy dialects
  for MariaDB, SQL Server and Oracle; S3-backed and chunked stores).
  Nothing under `src/` or `tests/` was touched.
- **Sources (clones):** the table in
  `studies/2026-10-05-binary-renderings/sources.md`. Ten local clones
  refreshed to their upstream default branch on 2026-10-05 (git,
  jackrabbit-oak, haystack, llama_index, langchain, fastembed, sqlite,
  postgres, langchain-mongodb, computer); six cloned shallow the same
  day (tika Apache-2.0, paperless-ngx GPL-3.0, markitdown MIT, docling
  MIT, immich AGPL-3.0, nuxeo Apache-2.0); langchain-community (MIT)
  cloned into the session scratchpad because the langchain monorepo now
  holds only the parser seam. Licences read after the refresh; the
  copyleft clones are study-only under the no-copy rule.

---

## 1. The answer in one paragraph

Clay's sketch holds, and the prior art sharpens it in four places. A
binary file is an ordinary entry whose body is bytes in a `vfs_blobs`
row; its text rendering lives in `vfs_content` under the same entry id,
so every text verb runs unchanged and the permissions join covers it
for free. The four sharpenings: (1) the rendering is **stamped** on the
entry row with the bytes hash and a renderer generation, exactly as
chunks and links are stamped today, so the existing fingerprint-skip
law decides when to re-render and a generation bump re-renders a corpus
without an operator sweep; (2) a rendering that could not be made is a
**stamped state with a reason, never a body**, because every system
that stored an empty or sentinel string made "no text" indistinguishable
from "not attempted" and, in one case, grep-matchable; (3) the rendering
is **read-only and not separately versioned**: the file's bytes are
versioned like any body, and the text of an old version is regenerable
from its bytes plus the generation (Clay, 2026-10-05: binary files are
versioned, and changed only by replacing the bytes through `write`;
edit through the rendering is deferred, see spec 152); (4) the blob
column needs a
`LONGBLOB` variant on MariaDB and bulk inserts need a **bytes-in-flight
budget** nested inside today's bind-count paging, or a 10,000-file
ingest is ten gigabytes resident in one statement.

## 2. What the tree holds today, and the pattern it already has

- `Entry.content` is `str`; the body column is `Text`; null bytes are
  refused (`src/vfs/models/entry.py:134-139`). A PNG cannot be stored.
- The entry row carries two stamp pairs, `chunk_source_hash` +
  `chunk_generation` and `link_source_hash` + `link_generation`
  (`src/vfs/models/rows.py:395-402`). Reindex compares each pair to the
  current body hash and the current engine generation and rebuilds what
  is stale (`indexing.py:258-262`, the fingerprint-skip law). Embedding
  is a reindex step behind a provider seam (ADR 054).
- The July memo decided the wire half: media rides rows keyed by path,
  the MCP adapter mints `image` blocks at the boundary from the row's
  bytes and mime, with a per-boundary accept list and a text
  placeholder for everything else. It named the storage bytes story as
  the prerequisite this memo answers.

The design below is that stamp pattern applied one step earlier in the
chain: bytes → rendering (new) → chunks → grams, postings, vectors,
links (existing).

## 3. Findings per sub-question

Each finding names what was observed and what is inferred from it.

### 3.1 What keys the rendering, and when it is rebuilt

- *Observed.* All three rendition systems key the derived text by
  content identity: git by blob oid in `refs/notes/textconv/<driver>`,
  Oak by the blob's content identity, Nuxeo by document plus
  modification date (the weakest). Only git carries an extractor
  identity, and as one validity string whose change drops the whole
  cache (`renditions.md` §1, §5.1). Paperless keys nothing: a changed
  OCR engine is invisible and re-rendering is a manual whole-corpus
  command (`paperless.md` §7). Immich keeps the CLIP model name in
  config, not the database; a model change truncates the vector table
  and the admin re-runs the job by hand (`images.md` §1.3).
- *Inferred.* Stamp the entry row with `render_source_hash` (the bytes
  hash) and `render_generation` (renderer name and version, e.g.
  `pypdf/6.1` or `docx-xml/1`; for images the describer's provider and
  version). The fingerprint-skip law applies unchanged: same hash under
  the same generation, do nothing. A generation bump is per row and
  recoverable, which is strictly better than git's whole-cache drop and
  Immich's truncate. Rebuild in the reindex pass as a stage **before**
  chunk-split, so the same pass chunks the new text; the write path
  stores the entry and the blob synchronously and never renders inline
  (the file exists, is listable and downloadable at once; paperless's
  "no row until the text exists" is wrong for a filesystem).
- *Observed.* Oak's cache exists mainly so one blob referenced from two
  nodes is extracted once. *Inferred.* Two entries sharing a
  `render_source_hash` under the current generation copy the rendering
  row, the same shape as `carry_embeddings`.

### 3.2 Versioned, editable, bounded

- *Observed.* Nuxeo pins stored renditions to an immutable checked-in
  version so they cannot go stale; git's per-blob key has the same
  effect; Oak and Nuxeo fulltext keep only the current text. Paperless
  lets users hand-correct OCR through the API and then silently discards
  the correction on the next reprocess (`paperless.md` §6).
- *Inferred.* The rendering is **not versioned**: a version row for a
  binary entry snapshots the bytes hash and a blob reference, and the
  text of an old version is rendered on demand from its bytes. The
  rendering is **read-only**: a write to a binary path replaces the
  blob and dirties the stamp; an `edit` or text `write` aimed at the
  rendering is a classified refusal, never a silent write to
  `vfs_content` that the next reindex would overwrite. Corrections, if
  ever wanted, are a sidecar text entry.
- *Observed.* Oak truncates at 100,000 characters and keeps the prefix;
  Nuxeo at 128 KiB; Tika's write limit truncates, keeps the text and
  sets a flag, and no layer treats that as an error (`tika.md` §4). No
  framework converter bounds a rendering at all; a 10,000 × 6 sheet
  rendered to 590 KB over 10,002 lines in 1.6 s (`markdown-renderers.md`
  §4.5).
- *Inferred.* A per-rendering character budget, truncate at a unit
  boundary with a visible marker and the `truncated` state; a
  per-file extractor budget, not a corpus cap, and the house rule
  against designed caps means the budget is a declared constant with
  the size profile in the docstring.

### 3.3 What the entry row's hash and size describe

- *Observed.* Every system keeps the bytes' identity on the owner
  (Nuxeo's `file:content` digest and length, Oak's blob, git's oid,
  paperless's `checksum`) and the text's own facts elsewhere.
- *Inferred.* `content_hash` and `size_bytes` describe the **bytes**:
  that is what the caller wrote and what `write`, `move` and a change
  detecting pipeline compare. The rendering's hash is the stamp's job.
  `lines` keeps its meaning as "lines of the text the verbs see", which
  for a binary is the rendering, and the docstring says so. Both this
  memo's reviewers of the row shape (`renditions.md` §5.5,
  `paperless.md`) reached the same split independently.

### 3.4 The failure states

- *Observed.* Oak stores the literal string `TextExtractionError` as
  the text when a parser is missing, throws or times out, and a timeout
  is persisted as never-retry (`renditions.md` §2). Nuxeo stores `""` on
  any failure, so an empty file and a failed extraction are the same
  row. Paperless stores `""` with no reason column and a later sanity
  checker is the only thing that notices. Tika, by contrast, returns a
  crashed or timed-out parse as a **result with a status**, in five
  categories, and its truncation flag is a signal every layer checks
  rather than an exception (`tika.md` §4, §8).
- *Inferred.* Record the outcome as a state on the entry row, never as
  a body. A content row exists only when text was produced; the stamp
  is always written, with a small fixed status set: `ok`, `truncated`,
  `partial` (deadline or embedded-limit hit, text so far valid),
  `empty` (parsed, no text), `encrypted`, `unsupported` (no renderer
  for the type), `unavailable` (renderer's extra not installed),
  `corrupt`, `crashed` (worker died), plus a bounded diagnostics list.
  The skip law then does not retry under the same generation, a
  generation bump or an extra install does retry, grep and glean can
  say "binary, no rendering" instead of matching a sentinel or staying
  silent, and a read of a binary not yet rendered returns a classified
  "not rendered yet" row (Nuxeo's in-progress marker) rather than an
  empty body. Two reviewers (`renditions.md` §5.7, `paperless.md`)
  arrived at "state, not body"; `tika.md` wanted an always-written
  content row with flags. The memo takes the first: a sentinel in
  `vfs_content` would be chunked, embedded and grep-matchable, and the
  stamp on the entry row carries the flags just as well.

### 3.5 What text each format becomes

- *Observed.* MarkItDown and Docling converge on one Markdown subset:
  ATX headings, GFM pipe tables, `![alt](target)` images, HTML comments
  for out-of-band markers (`markdown-renderers.md` §4.1). Tika's XHTML
  carries `div.page`, `div.slide-content` and `div.sheet` boundaries,
  and its own Markdown handler drops them (`tika.md` §3). MarkItDown's
  `<!-- Slide number: N -->` is the only numbered, visible, single-line
  unit marker any studied project emits by default; its PDF path loses
  pdfminer's form feeds in a join. Docling keeps page provenance per
  item and throws the number away at export. haystack puts `\f` between
  pages and counts them in its splitter. docx has no page concept in any
  project; neither MarkItDown nor Docling trusts `lastRenderedPageBreak`.
- *Inferred.* Render to a line-oriented Markdown subset. One marker
  grammar for all unit kinds, an HTML comment on its own line before the
  unit's first content line and emitted even for empty units:
  `<!-- page 3 -->`, `<!-- slide 3 -->`, `<!-- sheet 2: Budget -->`
  (plus a `## Budget` heading after the sheet marker, which is what the
  model reads as context). No markers for docx. A visible comment beats
  haystack's `\f` because it survives every join, is greppable, and an
  agent reading the file sees it; the two studies disagreed here
  (`framework-converters.md` §8 for `\f`, `markdown-renderers.md` §4.2
  against control characters) and the memo sides with the visible
  marker. A small `(unit, first_line)` table on the rendering lets grep
  label a hit with its page and lets a chunk carry a page without
  scanning text. Normalise inside the renderer (strip trailing spaces,
  collapse three or more newlines to two, drop NULs before Postgres
  `TEXT`, which paperless learned the hard way) so line numbers are
  stable across re-renders.
- *Tables, inferred from both studies.* GFM pipe tables, one row per
  line, compact, blank cells empty (never `NaN`, never `Unnamed: N`,
  which rules out the pandas route), `|` escaped and in-cell newlines
  collapsed. For xlsx: read cells with openpyxl directly, render each
  contiguous cell region as its own table (Docling), and use Excel
  column letters as the header with the 1-based row number as the first
  column so a grep hit reads as a cell address (haystack). pptx: shape
  text per slide, tables as rows, notes as a sub-block after the slide,
  master and layout text off (Tika turns it on and the footer then hits
  on every slide). docx: heading styles to heading levels, tables
  interleaved in body order, headers first and footers last, footnotes
  and comments inline where referenced (Tika's conventions; python-docx
  is the only Python library of the three studied that walks body order
  and keeps tables).
- *Embedded images.* All three frameworks drop them by default;
  MarkItDown links to a filename that does not exist; Docling emits an
  identity-free `<!-- image -->`. *Inferred.* Drop in the first landing
  with the document's own alt text in a placeholder line. Extracting
  each embedded image as a sibling entry and linking it is the natural
  filesystem move and a real edge for the link extractor, but it
  multiplies the rows that permissions, delete, move and versions keep
  in step; it is a named fork, not the default.
- *Scanned PDFs.* The text-layer path renders nothing for them. Say so:
  a marker line per page with no text, state `empty`, not silence.

### 3.6 The extractor seam and its limits

- *Observed.* Tika's seam is four pieces: a source that knows its
  measured length, a detector that trusts magic bytes first and lets
  the filename and the declared type only narrow among magic candidates,
  a parser registry keyed by media type with a supertype walk and
  last-registered-wins, and a parser protocol that takes a stream and
  returns structure plus metadata (`tika.md` §1 to §3). Unknown type
  falls to an empty parser, not a refusal. langchain's `Blob` →
  `BaseBlobParser` → `MimeTypeBasedParser` and haystack's `ByteStream`
  + `FileTypeRouter` (with `unclassified` and `failed` buckets) are the
  same shape in Python (`framework-converters.md` §8).
- *Observed, limits.* Tika: write limit truncates and flags; the
  decompression-bomb ratio (100:1 after one million characters) and the
  nesting depth always fail loudly; embedded depth and count are
  non-throwing with flags; timeouts are cooperative inside the parser
  and hard only in a forked process with a heartbeat, a stall timer and
  a recycle-after-N-files rule, because two generations of Tika showed
  a hung native parser cannot be stopped any other way (`tika.md` §4 to
  §6).
- *Inferred.* `render(bytes, mime, name, limits) -> Result[Rendering]`,
  a registry keyed by exact mime then pattern with a supertype walk,
  mime from the entry (declared, checked against magic), never from a
  filename alone, and three distinct classified outcomes: no renderer,
  renderer unavailable (extra missing), renderer failed (reason as
  data). One `RenderLimits` value (characters, output-to-input ratio,
  embedded depth and count, pages, wall time) passed to every render.
  Isolation: the bundled renderers (pypdf, python-docx, openpyxl,
  python-pptx) are pure Python, so the first landing runs them through
  the existing offload executor with a time budget and records a
  timeout as `partial`; a subprocess pool with heartbeat, kill and
  recycle is the named fork for native or model-backed renderers such
  as a layout pipeline, and the memo records Tika's finding that only a
  process can stop a hung native parser.

### 3.7 Libraries and packaging

- *Observed.* pypdf is the in-core PDF default in haystack and
  llama_index and the named loader in langchain; python-docx is the only
  docx library that interleaves tables, keeps hyperlinks and emits
  rendered page breaks (docx2txt flattens; unstructured is heavy);
  xlsx is pandas-over-openpyxl in two frameworks and absent in the
  third; pptx is python-pptx. None of the three ships pip extras for
  parsers: lazy imports with a pip hint, checked in a constructor or at
  call time. MarkItDown's extras are light pure Python; Docling's default
  PDF path needs torch and about 385 MB of weights, with caption models
  from 513 MB to 6 GB (`markdown-renderers.md` §4.7).
- *Inferred.* pypdf, python-docx, openpyxl (no pandas) and python-pptx
  behind real uv extras per format with an umbrella `vfs[documents]`;
  Pillow for image dimensions; probe the extras once at registry
  construction and report a missing one as the `unavailable` state on
  the entry, never as an exception at render time. Caption or OCR
  enrichment is a separate tier, plain HTTP to an OpenAI-compatible
  endpoint with an `image_url` data-URI part (what both MarkItDown and
  Docling send), network off by default, shaped like Docling's explicit
  options (endpoint, headers, prompt, timeout, concurrency) rather than
  MarkItDown's duck-typed SDK client. A layout pipeline (Docling) is a
  heavy optional renderer plugin, never a core dependency. The Rust rule
  does not apply: these are third-party parsers, a dependency decision
  on its own merits, not engine code.

### 3.8 Images: caption versus vector

- *Observed.* Immich keeps the asset row thin and every ML artefact in a
  side table keyed by asset id: EXIF, thumbnails on disk, a CLIP
  `vector(512)` with an HNSW cosine index, OCR boxes plus a flattened
  trigram-indexed OCR text, faces. It never generates captions; the
  human caption is an EXIF field. It **added OCR as a separate lexical
  rendering** because a photo of a receipt is found by its words. Its
  CLIP identity lives in config, and a model change is a truncate plus
  an admin-triggered re-run (`images.md` §1). fastembed's text-image
  pairs (CLIP ViT-B/32 at 512 dimensions, jina-clip, SigLIP2) cap text
  at 64 to 77 tokens and share a space only by naming convention; the
  CPU-friendly document models (ColPali) are multi-vector, which vfs's
  one-vector-per-chunk tables do not hold (`images.md` §2).
- *Inferred.* The image's rendering is **caption plus OCR text**,
  produced by a describer seam shaped like ADR 054's embedder and run as
  a reindex step; no CLIP image-vector table in the first landing. A
  caption drops an image into the existing machinery with no new
  tables, no second space and no dimension-change story; the vector
  space stays the named future direction ADR 054 already reserved. The
  stamp is per entry (`render_generation` names the describer and
  version), an image with no text still gets a stamp, invalidation is by
  comparison not truncate, and the write-back is conditional on the
  expected generation so a render started under describer A is not
  written once B is configured. Keep width, height, format (sniffed,
  not from the extension), orientation and capture date on the row,
  cheaply and without a model; put the readable EXIF subset and any
  embedded `ImageDescription` tag into the rendering text, where it is
  greppable. Store no thumbnails: the describer receives a transient
  bounded upright downscale, which is what Immich's preview really is.

### 3.9 Blob storage on five engines

- *Measured* (`blob-storage.md`, script in the session scratchpad):
  1,000 × 1 MiB rows through SQLAlchemy `LargeBinary` executemany on
  SQLite, 16 KiB pages: 464 rows/s, 0.2% file overhead, 1.96 ms
  full-body point read, 55 µs for a 4 KiB head via `blobopen`; a
  narrow-column scan is 13.6 ms with the blob last against 149 ms with
  it first, while primary-key point reads are unaffected.
- *Observed.* SQLite caps a value and a row at `SQLITE_MAX_LENGTH`
  (1 GB default) and its own documentation puts the files-beat-blobs
  crossover at 100 KB. Postgres `bytea` is TOASTed at about 2 kB, lz4 or
  pglz compressed by default, 1 GB field cap; `SET STORAGE EXTERNAL`
  skips compression for already-compressed bytes and makes `substring`
  a ranged fetch; large objects are a 4 TB, transaction-bound,
  orphan-prone alternative. MariaDB renders `LargeBinary` as a bare
  `BLOB`, 64 KiB, and a statement is one packet under
  `max_allowed_packet`. SQL Server renders `VARBINARY(max)` only on a
  connected dialect (offline DDL prints `IMAGE`). Oracle binds bytes as
  `DB_TYPE_RAW` up to 1 GB. SQLAlchemy 2.0.52 excludes no LOB column
  from `insertmanyvalues` and pages by bind count only, never bytes.
- *Inferred.* `LargeBinary` with a `LONGBLOB` variant on the MySQL
  family, exactly as `_body_text()` pins `LONGTEXT`; Postgres `SET
  STORAGE EXTERNAL` in the DDL; the column physically last. Bulk inserts
  page blob rows with the existing `byte_chunked` flush law nested
  inside the count page, with a declared byte budget per page in the
  low tens of MiB (measure), and the singleton exemption carries a file
  larger than the budget alone. Only the engines' own per-value caps
  classify, as `unsupported` naming the engine's number or the server
  setting, never a vfs-wide ceiling. Whole-value reads everywhere except
  SQLite `blobopen` and Postgres `EXTERNAL` plus `substring` are the
  documented current profile, with the ranged-read forks named. An
  external store (S3 plus a pointer row, or a dofs-style
  content-addressed chunk table) is deferred until a measured workload
  wants objects past an engine cap, ranged reads where the engine has
  none, or cross-region bytes; the S3 design studied documents its own
  read-your-writes gap.

## 4. The design, consolidated

| piece | rule |
|---|---|
| body | bytes in `vfs_blobs(entry_id, created_at, body)`, body last, `LargeBinary` + `LONGBLOB` variant + Postgres `EXTERNAL`; a text file has no blob row; a row is bytes or text as its source, never both |
| entry row | `content_hash`, `size_bytes`, `mime_type` describe the bytes; `lines` describes the text the verbs see; new `render_source_hash`, `render_generation`, `render_status`, bounded diagnostics; images add width, height, format, orientation, capture date |
| rendering | Markdown subset in `vfs_content` under the same entry id; unit markers as HTML comment lines; compact pipe tables; a `(unit, first_line)` table beside it; normalised and NUL-free; read-only; unversioned; truncated at a budget with the state set |
| when | the write stores entry and blob synchronously; the reindex pass renders dirty binaries before chunk-split under the fingerprint-skip law; dedup by bytes hash; conditional write-back on the expected generation |
| failure | no content row, a stamped state and reason; a read of an unrendered binary is a classified "not rendered yet"; grep and glean skip knowingly; a generation bump or an extra install re-dirties |
| seam | `render(bytes, mime, name, limits) -> Result[Rendering]`; mime-keyed registry with supertype walk and last-wins; outcomes: no renderer, unavailable, failed; one `RenderLimits`; offload executor now, subprocess pool as the fork for native renderers |
| images | caption plus OCR through a describer seam like ADR 054's embedder; no image-vector table yet; no stored thumbnails |
| packaging | per-format extras plus `vfs[documents]`; caption tier is HTTP only and network-off by default; layout pipelines are plugins |
| bulk | blob inserts paged by bytes inside the count page; rendering per sub-batch with a per-extractor time budget, nothing held open across a provider call |
| permissions | unchanged: rendering, chunks and caption key on the entry id, so the visible-set join covers them |

## 5. Open questions for the ADR

1. **Unit markers.** The visible `<!-- page N -->` comment line (this
   memo) or haystack's `\f` line. The memo's reason for the comment is
   that it survives joins and is readable by the agent; the cost is one
   extra line per unit in the rendering.
2. **xlsx table shape.** Cell-address form (column letters as header,
   row number as first column) or first-row-as-header. The first is
   greppable as a cell address; the second reads more naturally.
3. **Embedded images.** Placeholder with alt text (default here) or
   extracted sibling entries with a real link. The second is the
   filesystem-shaped answer and a permissions and lifecycle cost.
4. **Where the `(unit, first_line)` table lives.** A JSON column on
   the content row, a small side table, or derived at read time by
   scanning markers.
5. **The render status set.** The nine states above, or fewer. Which
   states glean reports in its envelope, as it reports `unembedded`.
6. **Isolation tier.** Whether the first landing needs the subprocess
   pool for the pure-Python renderers, or only the offload executor with
   a budget. Tika's evidence is about native parsers.
7. **Per-value caps.** Confirm on the engine legs that executemany with
   LOB columns behaves on Oracle (undocumented) and measure the byte
   budget per page on MariaDB against its `max_allowed_packet`.
8. **The caption prompt and describer identity.** What the generation
   string carries for a hosted model (provider, model id, prompt hash),
   so a prompt change re-renders.
9. **`read` of a binary.** The rendering by default with bytes on
   request, as the July memo's placeholder grammar assumed; the exact
   parameter and the wire projection for the bytes are the MCP
   adapter's.

## 6. One-line version

Bytes are the body, the rendering is a stamped derived index in the
content table, failure is a state and not a body, and the only new
engine facts are a `LONGBLOB` pin and a bytes budget on bulk inserts.
