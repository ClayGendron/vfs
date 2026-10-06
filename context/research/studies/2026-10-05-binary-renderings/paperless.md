# Study: paperless-ngx — original bytes, archive PDF, and extracted text on one row

- **Status:** study
- **Date:** 2026-10-05
- **Owner:** Clay Gendron
- **Sources:** `~/Git/Repos/paperless-ngx`, shallow clone of `dev` @ `c780586`
  (2026-10-05), **GPL-3.0** (`LICENSE`). Studied read-only; nothing copied.
  Citations are `paperless-ngx:path:line`. See `sources.md` in this folder.
- **Method:** read the `Document` model and its migrations, the consumer
  pipeline and parser registry, the five built-in parsers, the re-OCR and
  bulk-edit tasks, the Tantivy search backend, the metadata endpoint, the
  AI/LLM index, and the docs for OCR limits and document versions.

> Note on the checkout. The `dev` branch has moved well past the released
> line: parsers now live under `src/paperless/parsers/` (not
> `paperless_tesseract/`, `paperless_text/`, `paperless_tika/`), the parser
> registry is score-based (`get_parser_for_file`, not
> `get_parser_class_for_mime_type`), full-text search is **Tantivy**, not
> Whoosh (`paperless-ngx:src/documents/search/__init__.py:4`), and
> **document file versions** exist (`root_document`, `version_index`,
> migrations 0012/0015). The study reports `dev` and flags where the released
> line differed.

## 1. The row shape

One Django model, `Document`, holds the original file's identity, the
archive PDF's identity, and the extracted text
(`paperless-ngx:src/documents/models.py:158-356`). Files live on disk under
`ORIGINALS_DIR` / `ARCHIVE_DIR` / `THUMBNAIL_DIR`; the row stores names and
hashes, never bytes.

| column | type | what it describes | cite |
|---|---|---|---|
| `content` | `TextField(blank=True)` | "The raw, text-only data of the document … primarily used for searching" | `models.py:190-197` |
| `content_length` | `GeneratedField(Length("content"), db_persist=True)` | DB-maintained char count of the rendering, for statistics | `models.py:199-206`, migration `0006` |
| `mime_type` | `CharField(256, editable=False)` | libmagic type of the **original** | `models.py:208` |
| `checksum` | `CharField(64, db_index)` | SHA-256 of the **original bytes** | `models.py:217-223` |
| `archive_checksum` | `CharField(64, null, db_index)` | SHA-256 of the **archive PDF** bytes | `models.py:225-233` |
| `page_count` | `PositiveIntegerField(null)` | pages, PDFs only | `models.py:235-245` |
| `filename` / `archive_filename` | `FilePathField(1024, unique, null)` | on-disk names of original / archive | `models.py:267-285` |
| `original_filename` | `CharField(1024, null)` | the upload name | `models.py:287-295` |
| `root_document`, `version_index`, `version_label` | FK self / int / char | file-version chain (dev only) | `models.py:315-338` |
| `storage_type` | — | **removed** (was gpg/unencrypted) | migration `0003` |

Observations:

- There is **no hash of the text**, and **no stamp of which extractor or
  extractor version produced it**. The row's only link from text to bytes is
  that they share a row.
- `checksum` history: MD5 (32 chars, `unique=True`) in the squashed initial
  (`paperless-ngx:src/documents/migrations/0001_squashed.py:745-752`);
  uniqueness dropped in `0005`; widened to 64 and recomputed as SHA-256 by a
  data migration that streams rows with `iterator(chunk_size=500)` and
  `bulk_update` in batches of 500
  (`paperless-ngx:src/documents/migrations/0016_sha256_checksums.py:11-13,45-94`).
  `archive_checksum` got its index in `0026`.
- `compute_checksum` is a 64 KiB-chunked SHA-256 over the file
  (`paperless-ngx:src/documents/utils.py:189-201`).
- The hashes serve **duplicate detection**: preflight refuses (or warns on)
  a file whose SHA-256 matches any row's `checksum` **or**
  `archive_checksum`
  (`paperless-ngx:src/documents/consumer.py:1042-1093`).
- Size is **not stored**: the metadata endpoint `stat()`s the files at
  request time (`original_size`, `archive_size`)
  (`paperless-ngx:src/documents/views.py:1479-1482,1519-1530`).

## 2. Eager, synchronous, one task per file

Consumption is a Celery task, `consume_file`, that runs a plugin chain
(preflight → ASN → collate → barcodes → workflow triggers → consumer) over
**one** file (`paperless-ngx:src/documents/tasks.py:185-282`). Uploads
enqueue one task per file (`paperless-ngx:src/documents/views.py:2205`);
the watched-folder consumer does the same per stable file
(`paperless-ngx:src/documents/management/commands/document_consumer.py:360`).
There is no multi-file ingest call.

Inside `ConsumerPlugin.run` (`paperless-ngx:src/documents/consumer.py:404-820`):

1. Copy to scratch, sniff MIME with libmagic; an `application/octet-stream`
   named `.pdf` is repaired with `qpdf` first (`consumer.py:423-457`).
2. Pick a parser via the registry; **no parser → the file is refused** with
   `UNSUPPORTED_TYPE` and no row is created (`consumer.py:466-478`).
3. Decide `produce_archive` (`should_produce_archive`, `consumer.py:127-185`):
   forced on when the parser `requires_pdf_rendition` (Office, mail), off
   when it `can_produce_archive` is false (plain text), else by
   `ARCHIVE_FILE_GENERATION` = always / never / **auto** (images and
   textless PDFs yes, born-digital PDFs no).
4. `parse()`, thumbnail, `get_text()`, date, archive path, `page_count` —
   all **before** any DB write (`consumer.py:517-573`).
5. One `transaction.atomic()` creates the row with `content=text`,
   `checksum=SHA256(original)`, then copies the files into place and sets
   `archive_checksum` from the written archive (`consumer.py:606-764`,
   `_store` at `851-912`).
6. `document_consumption_finished` fans out to matching, workflows, the
   search index and the LLM index (`paperless-ngx:src/documents/apps.py:24-31`).

So the rendering is **eager**: the row does not exist until the text does.
A parse failure (`ParseError` or any exception) calls `_fail`, which raises
`ConsumerError`; **nothing is stored** (`consumer.py:575-588`, `230-240`).

## 3. The parser registry (keyed by MIME, resolved by score)

`ParserRegistry.get_parser_for_file(mime_type, filename, path, allow_remote)`
iterates external (entry-point) parsers then built-ins, keeps those whose
`supported_mime_types()` dict contains the MIME, asks each for `score()`
(`None` declines), and returns the highest
(`paperless-ngx:src/paperless/parsers/registry.py:332-407`). Built-ins are
registered at `registry.py:192-210`. The protocol every parser satisfies is
`ParserProtocol` (`paperless-ngx:src/paperless/parsers/__init__.py:117-443`):
`supported_mime_types`, `score`, `can_produce_archive`,
`requires_pdf_rendition`, `configure`, `parse(path, mime, produce_archive=)`,
`get_text`, `get_date`, `get_archive_path`, `get_thumbnail`,
`get_page_count`, `extract_metadata`, context-manager cleanup.

`score` is how a parser **withdraws when its service is absent**: Tika
returns `None` unless `TIKA_ENABLED`
(`paperless-ngx:src/paperless/parsers/tika.py:131-135`); the remote (Azure
Document Intelligence) parser returns `None` unless an engine is configured
(`paperless-ngx:src/paperless/parsers/remote.py:7-11,139-170`).

## 4. How text is produced, per MIME

| MIME family | parser | text source | archive/rendition | page_count | cite |
|---|---|---|---|---|---|
| `application/pdf`, `image/{jpeg,png,tiff,gif,bmp,webp,heic}` | `RasterisedDocumentParser` (score 10) | born-digital PDF: `pdftotext -layout -enc UTF-8`; else OCRmyPDF (Tesseract) sidecar text, falling back to `pdftotext` of the OCR'd PDF | PDF/A via OCRmyPDF; images → PDF/A even with OCR off (img2pdf + pikepdf) | pikepdf `len(pdf.pages)`, **PDFs only; images → None** | `tesseract.py:46-55,235-263,497-664`, `utils.py:68-110,236-265` |
| Office + ODF + RTF | `TikaDocumentParser` | Tika server `as_text` (`parsed.content.strip()`); on HTTP 500 retries `from_buffer` | **always** a PDF via Gotenberg/LibreOffice (`requires_pdf_rendition=True`) | counted on the **rendition PDF** | `tika.py:42-55,152-162,212-276,338-358` |
| `text/plain`, `text/csv`, `application/csv` | `TextDocumentParser` | file read as UTF-8, `errors="replace"` fallback | none | None | `text.py:35-39,164-187` |
| `message/rfc822` | `MailDocumentParser` | a **formatted header block** (`Subject:`, `From:`, `To:`, `CC:`, `Attachments:`) + HTML body through Tika + plain body, whitespace-collapsed | always a PDF via Gotenberg | — | `mail.py:58-59,197-275` |
| PDF + images, remote | `RemoteDocumentParser` (`uses_remote_service=True`) | Azure DI `DocumentContentFormat.TEXT`; born-digital PDFs skip the remote call and use `pdftotext` | PDF with text layer from Azure | — | `remote.py:42-50,117,237-282,488` |

**Text format: plain text, no markup.** `post_process_text` collapses runs
of horizontal whitespace, strips leading/trailing per line, and **replaces
`\0` with a space "to prevent issues with saving to postgres"**
(`paperless-ngx:src/paperless/parsers/utils.py:114-130`). Returns `None` for
whitespace-only input so "no text" and "layout padding" are the same. Mail
is the one parser that writes its own labelled lines. Azure's
`DocumentContentFormat.TEXT` is chosen over Markdown. Tantivy indexes the
text as-is after Unicode normalization
(`paperless-ngx:src/documents/search/_backend.py:515-527`).

Born-digital detection: text counts as real if the PDF is tagged or the
normalized text exceeds `PDF_TEXT_MIN_LENGTH = 50` chars
(`utils.py:26,133-166`); the same predicate drives both "make an archive?"
and "skip OCR?" so the two never disagree (`utils.py:139-148`).

## 5. Failure handling — what ends up in `content`

| situation | outcome | cite |
|---|---|---|
| unsupported MIME | refused, no row | `consumer.py:474-478` |
| parser raises | `ConsumerError`, no row, task marked failed | `consumer.py:575-588` |
| OCR finds no text | force-OCR retry; still none → `content = ""` with a warning | `tesseract.py:613-614,624-651,656-663` |
| encrypted / signed PDF | OCR impossible; keep original's text if any, else `""` | `tesseract.py:615-621`; docs `usage.md:643-648` |
| remote engine unconfigured | `content = ""`, warning | `remote.py:263-268` |
| Ghostscript PDF/A render fails | `ParseError` with a hint | `tesseract.py:481-495` |
| bad UTF-8 in text file | decode with `errors="replace"` | `text.py:187`, `utils.py:196` |
| image too large | Pillow pixel limit; `OCR_MAX_IMAGE_PIXELS` passes `max_image_mpixels` to OCRmyPDF; doc still consumed, text may be missing | `tesseract.py:368-380`, `docs/configuration.md:1072-1078` |

An **empty rendering is a legal stored state**, and the sanity checker
later flags rows with no content as a warning
(`paperless-ngx:src/documents/sanity_checker.py:282-284`). No status or
reason column records *why* content is empty.

## 6. Limits and time bounds

| knob | default | effect | cite |
|---|---|---|---|
| `CELERY_TASK_TIME_LIMIT` (`PAPERLESS_WORKER_TIMEOUT`) | 1800 s | hard per-task limit; **also** the Tika and Gotenberg HTTP timeouts | `settings/__init__.py:708`, `tika.py:181-192` |
| `TASK_WORKERS` / `THREADS_PER_WORKER` | 1 / cpu-derived | Celery concurrency; OCRmyPDF `jobs` | `settings/__init__.py:692-693,801-803`, `tesseract.py:281` |
| `OCR_PAGES` | unset | OCR only pages `1-N` (disables the sidecar) | `tesseract.py:320-324`, `docs/configuration.md:1041-1055` |
| `OCR_MAX_IMAGE_PIXELS` | Pillow default | see §5 | `tesseract.py:368-380` |
| `suggestion_content` | 1.2 M chars | classifier input cropped to 800k head + 200k tail | `models.py:435-460` |
| text thumbnail | 50 MiB / 100 k chars | preview only | `text.py:242-249` |
| `MAX_STORED_FILENAME_LENGTH` | 1024 | falls back to default naming | `models.py:159`, `consumer.py:699-709` |

`content` itself is unbounded (`TextField`).

## 7. Does a changed original trigger re-extraction? No — originals never change

In paperless the original file is **immutable** once stored. Every
mutation path creates **new bytes as a new consume**:

- A new file for an existing document is uploaded with `root_document_id`
  and consumed as a **new version row** (`views.py:2185-2212`,
  `consumer.py:252-291,609-669`). The version row carries its own
  `checksum`, `content`, `page_count`, `mime_type`, `archive_checksum`.
- Rotate, delete-pages, edit-pdf, split, merge, remove-password all write a
  new file and enqueue `consume_file` (`bulk_edit.py:452-520,741-1120`).
- The sanity checker recomputes SHA-256 and reports a **mismatch** between
  file and `checksum` (`sanity_checker.py:220-240`) but does not re-extract.

Re-extraction of the *same* bytes is **operator-triggered only**:

- `bulk_edit.reprocess` enqueues `update_document_content_maybe_archive_file`
  **once per document** (`bulk_edit.py:405-418`).
- That task re-runs the parser on `source_path`, and `UPDATE`s `content`
  (and `archive_checksum`, `archive_filename` when an archive was produced)
  **in place**, recording old→new in the audit log; then re-indexes
  (`tasks.py:371-509`). No parser found → logged error, row untouched
  (`tasks.py:395-400`).
- `document_archiver --overwrite` runs the same task over all rows through a
  `ProcessPoolExecutor` (`management/commands/document_archiver.py:47-70`,
  `base.py:465-505`).

There is **no generation stamp**, so after upgrading Tesseract, changing
`OCR_LANGUAGE`, or switching parsers, nothing marks rows stale; the operator
must know to reprocess. The released-line behaviour was identical.

## 8. Is the text versioned? Per file version yes (dev); per re-render no

- **Released line:** one row, one `content`; re-OCR overwrote it. Not
  versioned. (Confirmed: the only history was the optional audit-log diff,
  `tasks.py:439-473`.)
- **`dev`:** each file version is its own `Document` row chained by
  `root_document` + `version_index` (unique per root,
  `models.py:340-356`; migrations `0012`, `0015`). The root's **effective
  content** is the newest version's `content`
  (`get_effective_content`, `models.py:379-432`;
  `annotate_effective_content` as a correlated subquery,
  `versioning.py:31-49`). Search indexes **only the root**, with the
  effective content; versions are not separately searchable
  (`signals/handlers.py:800-808`, `_backend.py:502-515`). Docs call this
  "file history for a document" (`docs/usage.md:94-105`).
- Within one version row, **re-rendering still overwrites** `content`; the
  text has no history of its own.

## 9. Is the rendering read-only? No

`content` is a writable field of `DocumentSerializer`
(`paperless-ngx:src/documents/serialisers.py:1314-1344`; only `deleted_at`
is read-only). `DocumentViewSet.update` routes a `content` edit to the
**latest version row** (or the `?version=` one), saves
`update_fields=["content","modified"]`, re-indexes and fires
`document_updated` (`views.py:1287-1335`). Users correct OCR by hand; the
next `reprocess` silently replaces the correction (only the audit log keeps
it).

## 10. Bulk operations and bounds

- **Ingest:** one task per file; concurrency = `TASK_WORKERS`; no batch
  ingest API. `DATA_UPLOAD_MAX_NUMBER_FIELDS = None`
  (`settings/__init__.py:524`).
- **Metadata bulk edits** (tags, correspondent, permissions…) do one
  `UPDATE`/M2M change and enqueue a single `bulk_update_documents(ids)`
  task, which annotates effective content once and re-indexes via a batch
  (`bulk_edit.py:119-370`, `tasks.py:314-345`).
- **Re-OCR** is one task per document (§7).
- **Search index writes** take a file lock with 4 attempts × 10 s and
  jittered backoff; on exhaustion the write is deferred to a Celery task
  60 s later rather than failing the caller
  (`_backend.py:57-60,171-262,685-713`). Full rebuild and
  `add_or_update_ids` stream rows with `iterator(chunk_size=1000)` and
  `Prefetch` bounded by the page's IN-list
  (`_backend.py:285-330,1090-1182`; `versioning.py:55-90`).
- **Data migrations** batch at 500 (`0016_sha256_checksums.py:12-13`).
- `merge_as_versions` takes `select_for_update` in pk order and defers
  `content` so the lock never drags bodies (`bulk_edit.py:640-646`).

## 11. Other extracted metadata

- `page_count` on the row (PDFs only; Tika counts the rendition; images
  None) (§4).
- `extract_metadata` is **on demand, not at consume**: the metadata
  endpoint calls the parser for the original (native MIME) and again for
  the archive (`application/pdf`), caches the result, and returns XMP
  entries (`namespace`, `prefix`, `key`, `value`) via pikepdf, or Tika's
  metadata map (`views.py:1456-1540`, `utils.py:268-343`,
  `tika.py:360-392`, protocol note at `parsers/__init__.py:371-404`).
- `lang` is **detected from `content` at request time** with `langdetect`,
  default `"en"` (`views.py:1534-1539`).
- Date: parser-detected (Tika `created`, mail `date`) else regex over
  filename + text (`consumer.py:558-568`).
- `DocumentBarcode` rows (page, value, format) (`models.py:982-1059`).
- `Note` is a separate table (`note`, `created`, `document`, `user`,
  `models.py:942-980`); notes are indexed as a JSON field plus a
  `notes_text` companion for snippets (`_backend.py:574-595`).
- `CustomFieldInstance` values are indexed as JSON (`_backend.py:597-612`).

## 12. Images: OCR'd, never described

Images are OCR'd through OCRmyPDF after conversion to PDF (DPI from EXIF,
`OCR_IMAGE_DPI`, or an A4 estimate; alpha stripped) (`tesseract.py:326-357`).
With `OCR_MODE=off` an image becomes a PDF/A with `content = ""`
(`tesseract.py:542-556`). **No image captioning or vision model exists
anywhere**: `paperless_ai` embeds `Notes + Custom Fields + Content` text
only (`paperless-ngx:src/paperless_ai/embedding.py:125-140`,
`indexing.py:256-298`); a grep of `src/paperless_ai` for
vision/caption/image_url finds nothing.

## 13. Full-text index is outside the database

Tantivy on disk (`settings` index dir), rebuilt from rows; the DB `content`
column is the source of truth and the index a derived cache with its own
schema fingerprint and `needs_rebuild` check
(`_schema.py:195-287`). This is the opposite of vfs, where `vfs_chunks` and
the gram index live in the same database as the body.

---

## What this says for vfs

Legend: **observed** = paperless does this; **inferred** = a vfs
recommendation drawn from what paperless does or lacks.

### What keys the rendering (bytes hash + extractor generation?)

- **Observed:** nothing keys it. `content` is a bare column; `checksum`
  names the bytes, `archive_checksum` names the archive, and no field names
  which extractor, version, language or mode produced the text. The cost is
  §7: staleness after an engine/config change is invisible; re-rendering is
  a manual, whole-corpus `document_archiver --overwrite`.
- **Inferred:** vfs should stamp the rendering exactly as it stamps chunks
  and links — a `(render_source_hash, render_generation)` pair on the
  entry, where `render_source_hash` is the SHA-256 of the blob and
  `render_generation` names the extractor and its grammar/version. The
  existing fingerprint-skip law (`indexing.py:258-262`) then applies
  unchanged: same blob hash under the same generation → keep the rendering.

### When it is rebuilt

- **Observed:** only on explicit reprocess or when new bytes arrive as a new
  version. Bytes are immutable, so "changed original" never happens
  in-place.
- **Inferred:** in vfs bytes *do* change in place (a write to a binary
  path). Rebuild when the stamp pair misses — the same lock-free probe +
  dirty-set pass used for chunking — rather than inline in the write. Bump
  `render_generation` to force a corpus re-render; never require an
  operator sweep.

### Is the rendering versioned with the file?

- **Observed (dev):** yes per file version — each version row owns its
  bytes hash *and* its text. The root reads through to the newest version.
  Within a version, re-rendering overwrites.
- **Inferred:** in vfs the rendering is derived, so a `vfs_versions` row for
  a binary entry should snapshot the **blob** (or its hash into the blob
  store), not the rendering; the rendering of an old version is
  regenerable from its bytes + generation. If a version's rendering is ever
  needed cheaply (diff, restore-then-grep), store it as the version's
  `content` snapshot the way text versions already are, but mark it derived
  so a restore re-stamps rather than trusts it.

### Is the rendering read-only?

- **Observed:** no — users hand-correct OCR via the API, and the next
  reprocess discards the correction with only an audit-log trace.
- **Inferred:** make `vfs_content` for a binary entry **read-only through
  the write verb**: a write to the path replaces the blob and dirties the
  stamp; an attempt to write text to a binary entry's rendering is a
  classified refusal. If corrections are wanted, they are a separate
  sidecar text entry, not an edit of the derived row — paperless's
  silent-overwrite footgun is the thing to avoid.

### What `content_hash` / `size_bytes` describe

- **Observed:** `checksum` = original bytes; `archive_checksum` = rendition
  PDF; size is not stored (stat at request); `content_length` is a
  DB-generated char count of the text.
- **Inferred:** `content_hash` and `size_bytes` on the entry row should
  describe the **bytes** (identity, dedupe, version compare — paperless's
  duplicate check matches on either hash). The rendering's own facts live
  in `lines` (already on the row) and the `render_source_hash` stamp; if a
  text length is useful for stats, a persisted generated column is a
  portable, zero-maintenance pattern on Postgres/SQLite (check SQL Server
  and Oracle support before adopting).

### Lazy vs eager

- **Observed:** eager and synchronous inside a background task; the row
  does not exist until the text does, with a 1800 s hard limit that also
  caps the Tika/Gotenberg calls. This is fine for a scanner inbox and wrong
  for a filesystem: a file the user just wrote must exist immediately.
- **Inferred:** write the entry + blob synchronously (the file exists, is
  listable, downloadable); render in the offload/reindex pass behind the
  stamp pair, like `chunked`. Give each extractor call a time budget and
  classify a timeout as a render failure, not a write failure.

### No extractor available

- **Observed:** three different answers — unsupported MIME is **refused
  outright**; a configured-but-absent service makes the parser withdraw by
  `score() → None`; a remote parser that is selected but unconfigured
  stores `""`. Empty content is legal and only a sanity-check warning says
  so. Nothing records *why* content is empty.
- **Inferred:** vfs must accept the bytes regardless (it is a filesystem).
  Leave `vfs_content` absent and record a render **status/reason**
  (`unsupported`, `extractor_missing`, `failed`, `empty`, `timeout`) so
  grep/glean skip the entry knowingly and a later extractor install can
  find the rows to render by status. Do not conflate "no text found" with
  "not attempted".

### Bulk ingest of 10,000+ files in one call

- **Observed:** paperless never does this — one Celery task per file,
  bounded by worker count; the only multi-row paths (metadata bulk edit,
  index rebuild, checksum migration) stream in chunks of 500–1000 and defer
  index writes under lock contention instead of failing.
- **Inferred:** keep the write call bounded by the existing chunked blob
  insert; never render inline. The dirty-set render pass should process in
  byte-bounded sub-batches with a per-extractor time budget and flush per
  sub-batch, mirroring the "streaming per-sub-batch flush" already named as
  the chunk pass's future direction (`indexing.py:286-289`). An extractor
  that needs an external service (Tika) is a pool-limited client, not a
  per-row subprocess.

### Two binding details to carry over

- **Observed:** text destined for Postgres `TEXT` must have `\0` stripped
  (`utils.py:128-129`) — a rendering extractor can emit NULs from PDFs.
  vfs should normalize the rendering the same way before it reaches
  `vfs_content`.
- **Observed:** the "is this PDF born-digital?" predicate is shared by the
  archive decision and the OCR-skip decision so they cannot disagree
  (`utils.py:139-148`). If vfs ever has two consumers of "does this blob
  already contain text", make them share one function.
