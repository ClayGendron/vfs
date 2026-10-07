# 152 — Binary bodies and text renderings: bytes in a blob row, a stamped Markdown rendering in the content row

- **Status:** drafted 2026-10-05, awaiting Clay's review. Written the
  same day as the research memo it stands on, after Clay fixed the two
  forks the memo left to him: the file's bytes are versioned and are
  edited only by replacing them through `write`; there is no edit
  through the rendering in this spec ("edit the bytes at this time
  through write, no edit through rendering right now"). Not started.
- **Date:** 2026-10-05
- **Owner:** Clay Gendron
- **Kind:** feature (two tables touched, one added; one new reindex
  stage; one new provider seam; the read and write verbs learn bytes)
- **Depends on:** the write pipeline and the fingerprint-skip law as
  built (`storage/backends/database/indexing.py`), ADR 054 (the
  provider-seam shape and the reindex-step shape this spec copies for
  images), ADR 056 (bulk inserts take the driver's executemany; the
  bytes page nests inside it), the dialect budgets
  (`storage/backends/database/dialects.py`), the July multimodal memo's
  wire half (media rides rows; the adapter mints blocks at the
  boundary).
- **Decisions it implements:** none ratified yet. The *Decided
  semantics* below are proposed from the memo and from Clay's two
  answers; the ADR on binary bodies is cut from that section on
  ratification. Rules that merely restate existing law say so.
- **Research it stands on:**
  `../../../research/2026-10-05-binary-files-and-derived-text-renderings.md`
  and its seven studies under
  `../../../research/studies/2026-10-05-binary-renderings/`; the July
  memo `../../../research/2026-07-25-multimodal-result-content.md`
  (§6 question 1 is the storage half this spec supplies).

## Intent

Today a binary file cannot enter vfs at all: `Entry.content` is `str`,
the body column is `Text`, and the model refuses null bytes
(`src/vfs/models/entry.py:134-139`). Agents and pipelines hold PDFs,
Office documents and images alongside their Markdown and code, and
they want three things from them: to store and retrieve the bytes
unchanged, to grep and glean the words inside them next to everything
else, and to have the file versioned like any other entry.

The design is Clay's sketch with the memo's four sharpenings. A binary
file is an ordinary entry whose body is bytes in a new `vfs_blobs` row.
A **rendering** of it, Markdown text, is written to `vfs_content` under
the same entry id by a per-format renderer, so chunking, the gram
index, grep, glean and link extraction run unchanged, and the
permissions join covers the rendering for free. The rendering is
stamped on the entry row with the bytes hash and a renderer generation,
exactly as chunks and links are stamped, so the existing skip law
decides when to re-render. A rendering that could not be made is a
stamped state with a reason, never a body. The rendering is read-only
and is not versioned; the bytes are. For an image the rendering is a
metadata header; a caption from a vision model is a named fork, not
built here (Clay, 2026-10-05).

One line: bytes are the body, the rendering is a derived index in the
content row, failure is a state and not a body, and `write` is the only
way to change a binary.

## Decided semantics

### 1. The body is bytes or text, never both

- A new table `vfs_blobs(entry_id, created_at, body)`, keyed by entry
  identity like `vfs_content`, holds the file's bytes. The body column
  is physically last (the `vfs_content` rule; measured as an elevenfold
  scan win on SQLite in the memo).
- An entry's **source** is bytes or text. A text entry has no blob
  row. A bytes entry has a blob row and, once rendered, a content row
  that holds its rendering. The source is recorded on the entry row as
  `source` (`text` | `bytes`), so no verb needs a join to know which
  table the body lives in.
- `Entry` gains `data: bytes | None`. Supplying both `data` and
  `content` is a validation error, as explicit content on a directory
  is today. A bytes entry's `content` is `None` at construction;
  storage fills it from the rendering on read. `Observation` mirrors
  `data` as an elided-by-default field: a read never fetches bytes
  unless the caller projects the `data` column.
- `content_hash` and `size_bytes` on the entry row describe the
  **bytes** for a bytes entry: that is what the caller wrote and what
  `write`, `move`, `copy` and a change-detecting pipeline compare.
  `lines` describes the text the verbs see, which for a bytes entry is
  the rendering (zero until rendered); the column docstring says so.
- `mime_type` on a bytes entry is sniffed from the leading bytes for
  the formats this spec renders (PDF, the four OOXML types, PNG, JPEG,
  GIF, WebP, TIFF); the caller's declared value and the extension may
  narrow among candidates but never override the magic verdict (Tika's
  rule). An unrecognised body keeps the caller's declared type or
  `application/octet-stream`. A text entry's `mime_type` is unchanged.

### 2. `write` is the only way to change a binary

- `write(path=…, data=…)` stores a bytes entry; `write(entries=[…])`
  with `Entry(data=…)` rows is the batch form. `overwrite`, `parents`
  and the gates behave as for text. Writing text onto a bytes path
  replaces the entry's source (the blob row is deleted, the rendering
  stamp cleared); writing bytes onto a text path does the reverse. A
  write is whole-file: there is no partial or ranged write.
- A write of a bytes entry stores the entry and the blob **synchronously**
  and renders nothing inline: the file exists, is listable and readable
  as bytes the moment the write returns. The rendering is the reindex
  pass's work (§5). Paperless's "no row until the text exists" is the
  shape this rule rejects.
- `edit` on a bytes entry refuses `unsupported`, with a message naming
  `write` as the verb that changes a binary. The rendering is never a
  write target: the next reindex would overwrite it (paperless's
  silent-discard footgun), and a text edit of a derived view would have
  nothing to write back to. Edit through the rendering is a named
  non-goal, not a future promise.
- `delete`, `restore`, `move`, `copy` and `sweep` carry the blob row
  with the entry id exactly as they carry the content row; `copy`
  duplicates the blob row (content-addressed sharing is a fork, §Open
  questions). The trash judges a bytes entry by its origin as it does
  any entry.

### 3. The bytes are versioned; the rendering is not

- `vfs_versions` gains a `data` blob column, physically last. A version
  of a bytes entry is a full snapshot (`is_snapshot` true, `content` and
  `version_diff` null, `content_hash` and `size_bytes` the bytes'); no
  diff form exists for bytes. The text of an old version is rendered on
  demand from its bytes when a verb asks for it; no rendering is stored
  per version. This is Nuxeo's and git's rule (a rendition pinned to
  immutable bytes cannot go stale) and the cheap half of paperless's.
- No write path mints a version row today (the 070 landing note: the
  attribution columns wait for the version-content story). This spec
  adds the column and the rule so that story, when it lands, versions
  bytes and text by one law; it does not build the version verb.

### 4. The rendering: a line-oriented Markdown subset

- The rendering is UTF-8 text in `vfs_content` under the entry id,
  restricted to a Markdown subset every construct of which is
  line-delimited: ATX headings, paragraphs, GFM pipe tables one row per
  line, `![alt](…)` placeholders, HTML comment lines for markers. Never
  a construct that spans lines without a visible line break, never raw
  HTML tables, never a control character for structure (pdfminer's form
  feed is invisible in grep output and lost by the first join).
- **Unit markers.** One grammar for every unit kind: an HTML comment on
  its own line, emitted before the unit's first content line and
  emitted even for an empty unit, so unit *k* is always the *k*-th
  marker of its kind:

  ```
  <!-- page 3 -->
  <!-- slide 3 -->
  <!-- sheet 2: Budget -->
  ```

  A sheet marker is followed by a `## Budget` heading, which is what a
  model reads as context. docx carries no page markers; the libraries
  that could invent them do not trust the hint they would use.
- **The unit table.** Rendering also records `render_units`, a bounded
  JSON array of `(kind, number, label, first_line)` on the entry row,
  so grep can label a hit with its page and a chunk can carry a page
  without scanning text. It is derived from the markers and is
  rebuildable from the rendering alone.
- **Tables.** GFM pipe tables, compact, one row per line; blank cells
  empty (never `NaN`, never `Unnamed: N`); `|` escaped and in-cell line
  breaks collapsed to a space (haystack's two rules). For xlsx the
  header row is the Excel column letters and the first column is the
  1-based Excel row number, so a grep hit reads as a cell address and a
  sheet with no header row renders without inventing one; each
  contiguous cell region is its own table (Docling), so a sparse sheet
  is not a grid of blanks. For docx and pptx tables the first row is
  the header.
- **Per format**, following Tika's conventions as conventions:
  - *PDF*: one page block per page in page order, paragraphs inside;
    reading order from the content stream. A page with no text layer
    still gets its marker and nothing else (a scanned page is visible
    as empty, not silent).
  - *docx*: flow; heading styles to heading levels one to six; tables
    interleaved in body order; headers first, footers last; footnotes
    and comments inline at the point of reference and marked.
  - *pptx*: one slide block per slide; shape text in slide order;
    tables as rows; the slide's notes as a sub-block after it; master
    and layout text off (Tika turns it on and the footer then hits on
    every slide).
  - *xlsx*: one sheet block per sheet, visible and hidden alike (the
    text is in the file; hiding is a view property), the hidden flag
    in the unit table.
  - *Embedded images* in any document: a placeholder line carrying the
    document's own alt text or caption, `![alt](embedded:<n>)`, and
    nothing else. Extracting them as sibling entries is a fork.
- **Normalisation inside the renderer**, so line numbers are stable
  across re-renders and independent of the upstream library's
  whitespace: strip trailing spaces, collapse three or more newlines to
  two, drop NULs (Postgres `TEXT` refuses them; paperless learned it),
  end with one newline.
- **Budget.** `RENDER_CHARS`, a declared module constant, bounds one
  rendering. Truncation happens at a unit boundary, appends one visible
  line `<!-- truncated: N of M units -->`, and sets the `truncated`
  state. It is a per-file extractor budget with the size profile in
  the docstring, not a corpus cap; an xlsx rendering is linear in cell
  count and the memo measured 10,000 × 6 cells at 590 KB.

### 5. The stamp, the skip law, and the reindex stage

- Three new columns on the entry row: `render_source_hash` (the bytes
  hash the rendering was made from), `render_generation` (the renderer
  registry's generation string for that mime, §7), `render_status`
  (§6). The pair follows `chunk_source_hash` + `chunk_generation` and
  `link_source_hash` + `link_generation`; the fingerprint-skip law
  applies unchanged: same bytes hash under the same generation, do
  nothing. A generation bump re-dirties every bytes entry of that type
  on the next reindex; no operator sweep, no truncate (Immich's and
  paperless's failure).
- **A new first stage of the reindex pass, `render_dirty`**, runs
  before `chunk_dirty` inside the same lease: select the bytes entries
  whose stamp pair misses, in keyset pages bounded by bytes in flight
  (the blob page of §9), render each through `call_offloaded` with the
  per-render time budget, write the rendering and the stamp in one
  short write per page, check the lease, repeat. The same pass then
  chunks the new text, so one `reindex` leaves every index at the same
  generation (ADR 054's requirement). A write to a bytes entry resets
  `chunked`, `encoded` and `indexable` exactly as a text write does;
  the render stamp mismatch is what makes it dirty.
- **Dedup.** Two entries with the same `render_source_hash` under the
  current generation copy the rendering row instead of rendering twice
  (the `carry_embeddings` shape; Oak's reason for its cache).
- **The conditional write-back.** The stamp is written `WHERE
  render_source_hash IS DISTINCT FROM :hash OR render_generation IS
  DISTINCT FROM :generation` in the engine's spelling, so a render that
  began under one generation is not written once another is
  configured, and a rival's identical write is a no-op (ADR 054 rule 6).
- **Pending is visible.** Between the write and the first reindex the
  entry's `render_status` is `pending` and it has no content row. A
  verb that needs text says so (§6); nothing invents an empty body.

### 6. Failure is a state, never a body

`render_status` is one of a fixed set; a content row exists only for
`ok`, `truncated` and `partial`:

| status | meaning | content row | verbs that need text |
|---|---|---|---|
| `pending` | written, not yet rendered | none | `read` returns the row with `content` null and a record of kind `unavailable` (retry class *transient*, message: run `reindex`); grep and glean skip the entry |
| `ok` | rendered in full | yes | normal |
| `truncated` | rendered up to the budget | yes | normal, plus an info record of kind `budget_exhausted.truncated` on `read` |
| `partial` | the time budget or an embedded limit cut it; text so far is valid | yes | as `truncated` |
| `empty` | parsed, no text (a blank sheet, a scanned PDF) | none | `read` returns `content` as the empty string; grep and glean skip |
| `unsupported` | no renderer registered for the mime | none | `read` returns `content` null and a record of kind `unsupported` (retry *never*) |
| `unavailable` | a renderer exists but its extra is not installed | none | as `unsupported`, the message naming the extra |
| `encrypted`, `corrupt`, `failed` | the renderer refused or raised | none | as `unsupported`, the reason in the message |

- A bounded `render_detail` text column carries the reason (exception
  class and a capped message, the renderer's name) for the failure
  states and the truncation counts for the budget states. It is never
  free-form beyond that cap.
- Nothing from this table ever reaches `vfs_content`: a sentinel body
  would be chunked, embedded and grep-matchable (Oak's
  `TextExtractionError`), and an empty body would make "no text" and
  "not attempted" one row (Nuxeo, paperless).
- `stat` and `ls` project `render_status` like any entry column.
  `glean` reports the unrendered count in its envelope as it reports
  `unembedded`. The `reindex` result reports `rendered, cached,
  unrendered` at warning severity when `unrendered > 0`.
- Retry follows the skip law: the same bytes under the same generation
  are not retried for `unsupported`, `unavailable`, `encrypted`,
  `corrupt` or `failed`; a generation bump, an extra install (which
  changes the generation, §7) or a new write retries.

### 7. The renderer seam

- `render(source, limits) -> Rendering`, where `source` is the bytes,
  the sniffed mime and the entry's name, and `Rendering` is a value:
  the text, the unit table, the status, the detail, and for images the
  dimensions. Renderers are synchronous and CPU-bound; the stage hops
  them through `call_offloaded`.
- A **registry** keyed by exact mime, then a supertype walk (the
  macro-enabled OOXML types fall to their plain renderer), last
  registered wins so a host-supplied renderer displaces a bundled one.
  The registry is built once at storage construction and **probes each
  renderer's extra then**: a renderer whose import fails registers as
  `unavailable` with the extra's name, never raising at render time
  (haystack's constructor-time check, classified instead of thrown).
- **The generation string** is `<renderer name>/<renderer version>`
  where the version is the bundled renderer's own constant plus the
  parser library's version (`pdf/1+pypdf-6.1`), so a library upgrade
  re-renders. An `unavailable` renderer's generation is
  `<name>/unavailable`, so installing the extra changes the generation
  and the skip law retries.
- **One `RenderLimits` value** passed to every render: `chars` (§4's
  budget), `ratio` (output to input, Tika's decompression-bomb guard,
  always a loud `failed`), `embedded_depth` and `embedded_count`
  (non-throwing, set `partial`), `pages`, `seconds`. Defaults are
  module constants; a host may lower them, never raise `ratio`.
- **Bundled renderers and extras**: `pdf` on pypdf (`vfs[pdf]`),
  `docx` on python-docx (`vfs[docx]`), `pptx` on python-pptx
  (`vfs[pptx]`), `xlsx` on openpyxl, read-only mode, no pandas
  (`vfs[xlsx]`), `image` on Pillow (`vfs[images]`), and the umbrella
  `vfs[documents]` for all five. The Rust rule does not apply: these
  are third-party parsers, a dependency decision on its own merits, and
  none is engine code. A layout pipeline (Docling) is a host-supplied
  renderer, never a core dependency.
- **Isolation.** The bundled renderers are pure Python, so the first
  landing runs them on the offload executor with the `seconds` budget
  checked between units and a `partial` result when it is spent. The
  memo records Tika's finding that only a separate process can stop a
  hung native parser; a subprocess pool with heartbeat, kill and
  recycle is the named fork for native or model-backed renderers, not
  built here.

### 8. Images: a metadata header

- The `image` renderer always produces a header, needing no model:
  one line each for format, width × height, orientation, and the
  readable EXIF subset (camera, capture date, GPS, title, keywords, an
  embedded `ImageDescription` verbatim), so an image is greppable by
  what its file says about itself. `media_width` and `media_height`
  are also stored as integer columns on the entry row for listing. The
  generation is `image/1+pillow-<version>`.
- **A describer is a fork, not built** (Clay, 2026-10-05: "do not
  worry about an image description provider"). The memo records its
  shape: a protocol like ADR 054's `EmbeddingProvider` injected on the
  storage, its model id folded into the image generation so a model or
  prompt change re-dirties every image, a transient downscale as its
  input, its caption appended under a `## Description` heading, run
  inside `render_dirty` with no transaction open across the call. The
  header-only rendering and the generation string are shaped so that
  fork adds a suffix and nothing else changes.
- No image-vector table. The media vector space stays the named future
  direction ADR 054 reserved.

### 9. Blob storage on five engines

- `LargeBinary` with a `LONGBLOB` variant on the MySQL family, exactly
  as `_body_text()` pins `LONGTEXT`: a bare `BLOB` silently caps a body
  at 64 KiB. On Postgres the DDL adds `ALTER COLUMN body SET STORAGE
  EXTERNAL`: file bytes are mostly pre-compressed and `EXTERNAL` makes
  `substring` a ranged fetch. SQL Server renders `VARBINARY(max)` on a
  connected dialect; the engine leg asserts it. Oracle `BLOB`, bytes
  bound as raw. Nothing else per dialect.
- **Bulk inserts page by bytes as well as by count.** SQLAlchemy pages
  `insertmanyvalues` by bind count only; ten thousand one-megabyte rows
  in one execute would be ten gigabytes resident, and a MySQL-family
  statement is one packet under `max_allowed_packet`. Blob rows are
  paged with the existing `byte_chunked` flush law nested inside the
  count page, with a declared byte budget per page (`BLOB_PAGE_BYTES`,
  low tens of MiB, measured on the legs); the singleton exemption
  carries a file larger than the budget alone. Reads of a page of
  bodies are bounded the same way.
- **Only the engines' own caps classify.** A body past an engine's
  single-value cap (`max_allowed_packet` on MariaDB, 1 GB `bytea` on
  Postgres, `SQLITE_MAX_LENGTH`, 1 GB raw bind on Oracle, 2 GB on SQL
  Server) classifies `unsupported` naming the engine's number or the
  server setting; there is no vfs-wide ceiling and no hard-coded
  16 MB. Reads are whole-value everywhere except where the engine has
  a cheap ranged read, documented as the current profile with the forks
  named; a `read` never refuses by size.
- The external-store seam (a pointer row with a null body) and a
  content-addressed chunk table are recorded forks, not built.

### 10. What does not change

- Permissions: the rendering, its chunks and the blob key on the entry
  id, so the visible-set join, the owner floor and the everyone level
  cover them with no new rule. A bytes entry's `everyone_level` is
  labelled at its minting site like any row.
- The wire: the MCP adapter, when it lands, projects a bytes entry's
  `data` as an `image` block for the boundary's accepted image types
  and a placeholder naming the true mime otherwise, from the row, as
  the July memo decided. This spec adds the row.
- The oracle, the parity tests, the grants algebra, the range join.

## Non-goals

- Edit through the rendering, with write-back into the binary (Clay,
  2026-10-05: "no edit through rendering right now").
- Partial or ranged writes; ranged reads beyond the engines' own.
- Rendering stored per version; a version verb (the version-content
  story owns it).
- An image describer provider, captions or OCR of standalone images
  (Clay, 2026-10-05); an image-vector space; thumbnails or previews as
  stored artefacts.
- Extracting embedded images as entries; OCR of embedded images.
- A subprocess pool for renderers; a layout pipeline in core.
- An external blob store; content-addressed blob sharing across
  entries.
- Deriving `mime_type` for text entries, or any change to how text
  entries are hashed, chunked or indexed.

## Acceptance criteria

- `ruff check`, `ruff format --check` and `ty` at zero across `src/`
  and `tests/`; 100% coverage holds; `cargo test -p vfs-core` untouched.
- A `StorageContract` extension runs on every engine leg: a PDF, a
  docx, an xlsx, a pptx and a PNG written as bytes read back
  byte-identical, with `content_hash` and `size_bytes` the bytes';
  `write` of bytes onto text and text onto bytes switches the source
  and leaves one body row; `edit` on a bytes entry is `unsupported`;
  `read` before reindex is `pending` with the `unavailable` record;
  `reindex` renders, and grep then hits a word that exists only inside
  the PDF, the docx, a sheet cell and a slide; the hit's line sits
  under the right unit marker; `stat` shows `ok`.
- Every status in §6 is pinned by a fixture that produces it
  (encrypted PDF, truncated sheet, an unregistered mime, a renderer
  whose extra is absent, a corrupt OOXML zip, a blank image) and each
  pin kills the mutant that stores a body for it.
- The skip law is pinned: a same-bytes overwrite re-renders nothing
  (statement count); a generation bump re-renders every entry of the
  type; a dedup pair renders once.
- The conditional write-back is pinned by the seam harness: a render
  that began under generation A is not written once B is configured.
- The bytes page is pinned on MariaDB with `max_allowed_packet` set
  low: a batch whose total exceeds the packet lands in several
  statements, and a single body larger than the page budget rides
  alone; the over-cap body classifies `unsupported` naming the setting.
- `LONGBLOB` on MariaDB, `VARBINARY(max)` on SQL Server and `EXTERNAL`
  on Postgres are asserted by the engine legs from the live catalog.
- The image header is pinned: a PNG and a JPEG with EXIF render their
  dimensions and tags; a blank image is `ok` with the header alone;
  `media_width` and `media_height` are stored.
- Docs: `docs/api.md` (`write` with `data`, `read` and the `data`
  column, `edit`'s refusal, the status set), a how-to "store and search
  documents", the explanation page on renderings, and `docs/reference`
  for the unit-marker grammar and the status table.
- The full suite, `ruff`, `ruff format --check` and `ty` green before
  each landing commit; `scripts/ci.sh` only when Clay asks.

## Slices

| Slice | Content | Lands green? |
|---|---|---|
| A | Bytes in and out: `vfs_blobs`, the `data` column on `vfs_versions`, `source`, the render stamp and status columns, `media_width`/`media_height`, format 19 and the migration; `Entry.data` and the XOR; `Observation.data` elided by default; `write` with bytes (single and batch, the bytes page, the per-value cap classification, source switching), `read`/`stat`/`ls` with `pending`; `edit` refusal; the topology verbs carrying the blob row; the contract extension for bytes round-trips on all five legs. No renderer yet: every bytes entry is `pending`. | yes |
| B | The renderer seam: `Rendering`, `RenderLimits`, the registry with probing and generations, the `render_dirty` stage with dedup and the conditional write-back, the status machine, the normaliser and the unit table; the `pdf`, `docx`, `pptx` and `xlsx` renderers behind their extras; the unit-marker and table conventions; grep and glean honouring the statuses; the status fixtures and the mutant pins. | yes |
| C | Images: the `image` renderer (header, dimensions, EXIF subset, the two dimension columns) behind `vfs[images]`, its pins; the `vfs[documents]` umbrella. | yes |
| D | Docs and the API surface: `docs/api.md`, the how-to, the explanation page, the reference pages; the `Session` facade's `write(data=…)`; the glossary entries (source, rendering, unit marker, render status). | yes |

A lands first and alone; B needs A; C needs B; D closes. The engine
legs run on A (the blob facts) and B (the statuses are engine-neutral,
but the MariaDB packet pin is A's).

## Open questions

- **Marker grammar versus form feeds.** This spec takes the visible
  comment line; the framework study preferred `\f`. Decided here
  unless Clay prefers the invisible form.
- **xlsx header shape.** Cell-address form (column letters, row
  numbers) is decided here for addressability; first-row-as-header
  reads more naturally and is one flag away if wanted.
- **`copy` of a bytes entry** duplicates the blob row. A
  content-addressed blob table (one body per hash, a count) would make
  copies and dedup free and ranged reads possible; it is the
  in-database fork the memo names, and it changes the delete and sweep
  paths.
- **`read` of a bytes entry's bytes.** The `data` column projection is
  the in-process answer; the wire answer (an image block, a resource
  link, base64) is the MCP adapter's and is not decided here.
- **Where `render_units` lives.** A text column holding JSON on the
  entry row is chosen for portability; a side table would let a chunk
  join to its page. Revisit when a verb needs the join.
- **The ADR.** Cut from §Decided semantics on ratification; the memo's
  §5 lists the forks it should record as decided.

## Implementation progress — slice A

**2026-10-05.** Bytes in and out, on every engine. A bytes entry lands
its body in `vfs_blobs` and its stamp as `pending`; nothing renders yet.

- **Schema, format 19.** `vfs_blobs(entry_id, created_at, data)` with
  the body last; `LargeBinary` pinned to `LONGBLOB` on the mysql family
  and to the unlengthed `VARBINARY` on MSSQL (which renders `max`), with
  a Postgres `after_create` DDL setting `STORAGE EXTERNAL`. The entry
  row gains `source`, `render_status`, `render_source_hash`,
  `render_generation`, `render_detail`, `render_units`, `media_width`
  and `media_height`; `vfs_versions` gains `data`. `ENTRY_BODY_HOMES`
  names which table homes each body field, and the drift pins check it.
- **Models.** `Entry.data`, `Entry.source` (derived from the body) and
  `Entry.render_status`; a bytes body is a content statement for every
  gate, is refused beside `content`, hashes and sizes as the bytes,
  sniffs its `mime_type` by magic with the extension and the declared
  type narrowing only (`models/media.py`), and starts `pending`. A
  hydrated bytes entry keeps its row's metrics and rendering.
  `with_content` refuses a bytes entry. `Observation` mirrors the three
  fields and serialises bytes as base64 both ways. `Version.data` is a
  snapshot-only payload, exclusive with the text payloads.
- **Write path.** `write(path=…, data=…)` and `Entry(data=…)` rows;
  the param gate knows `bytes` and refuses `content` beside `data`. The
  plan stages `data` and `source`; the clobber set clears every render
  column so an overwrite restarts the stamp and drops a stale
  rendering; both body tables are cleared for every bearing row so a
  source switch leaves one body; blob inserts page by bytes in flight
  under `BLOB_PAGE_BYTES` (8 MiB) inside the bind-count page. `edit`
  on a bytes row refuses `unsupported` naming `write`. The set-based
  VALUES update casts its integer cells: an all-NULL VALUES column is
  text to Postgres, and the two dimension columns are integers.
- **Read path.** `source` and `render_status` are entry-backed
  observation fields; `data` is a body field fetched only when
  projected, through `bodies_joined`. `read` appends a render note per
  bytes row: `pending` is a transient `unavailable` warning, a cut
  rendering an info `truncated`, a failure an `unsupported` warning,
  `empty` the empty string. Copy carries both bodies and every render
  column; purge and the orphan sweep drain both body tables.
- **The engines' own caps.** `is_value_too_large` recognises SQLite's
  `DataError`, SQLSTATE class 54 and the mysql packet error 1153 by code
  and type; the host classifies them `unsupported`, naming the engine's
  message, never a vfs number. Pinned on SQLite by lowering
  `SQLITE_LIMIT_LENGTH` on the live connection.
- **Tests.** `test_media.py`; bytes entries and versions in
  `test_models.py`; the body-home drift pins in `test_rows.py`; the
  bytes section of `StorageContract` (seven tests: round trip and
  metrics, the pending read, the source switch both ways, the edit
  refusal, copy, delete and restore, listings); the blob write
  mechanics in `test_writes.py` (statement shape, source switch,
  overwrite dropping the rendering, byte paging, the edit refusal, the
  cap); the projection and render notes in `test_reads.py`; the cap
  classifier in `test_dialects.py`; orphan blobs in `test_coherence.py`;
  the catalog pins per engine in `test_conformance.py` (`bytea` stored
  `e`, `longblob`, `varbinary(-1)`, `BLOB`).
- **Gates.** `ruff check`, `ruff format --check`, `ty` at zero. Full
  suite: 3,773 passed, 1,344 skipped, 100% coverage (10,337
  statements); `pytest docs`: 23 passed. Postgres leg: 336 passed
  (including the bytes contract and the `bytea`/`EXTERNAL` catalog
  pin). Oracle leg: 332 passed, plus its catalog pin and two bytes
  contract tests run against the live server. MariaDB and MSSQL legs
  not run (no container up); their catalog pins run with the next
  engine session. `scripts/ci.sh` not run (Clay's rule).
- **Left for slice B.** The chunk pass stamps a pending bytes row as
  chunked-and-ineligible with its bytes hash as `chunk_source_hash`;
  when the renderer writes a content row it must also clear that stamp,
  or the skip law would keep the rendering unsplit.
