# Markdown renderers for binary documents: markitdown and docling

- **Status:** study
- **Date:** 2026-10-05
- **Owner:** Clay Gendron
- **Sources:**
  - `microsoft/markitdown` — `~/Git/Repos/markitdown`, shallow clone of
    `main` @ `4cc9fa1` (2026-10-03), MIT. Package root is
    `packages/markitdown/`; paths below are relative to the repo.
  - `docling-project/docling` — `~/Git/Repos/docling`, shallow clone of
    `main` @ `d15cf10` (2026-10-05), MIT. The package on PyPI is now
    `docling-slim` 2.133.0 (`pyproject.toml:6-7`).
  - `docling-core` 2.99.0 (MIT) — not a clone. docling's `DoclingDocument`,
    Markdown serializer and chunkers live in this sister package, so it was
    installed into the scratch dir and read with `inspect.getsource`.
  - Hugging Face model API (`huggingface.co/api/models/<repo>?blobs=true`),
    fetched 2026-10-05, for model weight sizes.
- **Method:** read the converters, backends, serializers and `pyproject`
  files; grepped the test ground-truth Markdown for the emitted conventions;
  ran three scratch experiments (pdfminer page boundaries, the markitdown
  xlsx path on blank cells and on a 10,000-row sheet). Everything below is
  **observed** unless marked **inferred**. No code was copied.

The design question this feeds: a binary entry's body is bytes and a derived
**text rendering** is stored as its text content, so the chunker (line-range
chunks), grep (line-numbered hits), glean and link extraction run unchanged.
The open sub-questions are the rendering format, page/sheet/slide markers,
table rendering, embedded images, xlsx size, and dependency weight.

---

## 1. markitdown

### 1.1 Architecture

- **One output type.** Every converter returns `DocumentConverterResult`
  holding a `markdown` string and an optional `title`
  (`_base_converter.py:5-39`). There is no document model; Markdown *is* the
  model.
- **Detection: `StreamInfo` + magika.** `StreamInfo` is a frozen dataclass of
  `mimetype`, `extension`, `charset`, `filename`, `local_path`, `url`
  (`_stream_info.py:5-19`). `MarkItDown._get_stream_info_guesses` enriches
  the caller's guess with `mimetypes`, then runs Google's **magika** ML
  file-type classifier on the bytes and `charset_normalizer` for text
  (`_markitdown.py:737-830`). When magika disagrees with the extension, *both*
  guesses are tried in order. magika is a hard core dependency
  (`pyproject.toml:27-34`).
- **Registration and priority.** Converters register with a float priority;
  `PRIORITY_SPECIFIC_FILE_FORMAT = 0.0`, `PRIORITY_GENERIC_FILE_FORMAT =
  10.0`, lower first, stable sort, later registrations tried first within a
  priority (`_markitdown.py:101-107`, `227-252`, `705-735`). `_convert` loops
  guesses × sorted converters, calls `accepts()` then `convert()`, and keeps
  the first non-None result (`_markitdown.py:602-690`).
- **Output normalisation, which matters for line numbers.** At the end of
  `_convert` every line is `rstrip()`ed and runs of three or more newlines
  collapse to two (`_markitdown.py:602-690`, the two `re` calls just before
  `return res`). A leading `\x0c` on a line survives this (see PDF).
- **Option seams are kwargs.** `llm_client`, `llm_model`, `llm_prompt`,
  `exiftool_path`, `style_map` are taken by the `MarkItDown` constructor and
  copied into every `convert()` call's kwargs (`_markitdown.py:150-226`,
  `620-640`). `exiftool_path` falls back to `$EXIFTOOL_PATH` and then to a
  `shutil.which` hit in an allow-list of system directories (`:197-224`).
- **Per-format imports are guarded.** Each converter wraps its third-party
  import in `try/except ImportError`, stores `sys.exc_info()`, and raises
  `MissingDependencyException` only when `convert()` runs
  (`_pdf_converter.py:60-67`, `_docx_converter.py:15-21`,
  `_xlsx_converter.py:14-26`, `_pptx_converter.py:19-24`).
- **Plugins** load from the `markitdown.plugin` entry-point group
  (`_markitdown.py:112-131`); README mentions a `markitdown-ocr` plugin that
  adds OCR through the same `llm_client` vision path (`README.md:131-157`).

### 1.2 PDF (`converters/_pdf_converter.py`)

- **Imports:** `pdfminer.high_level` and `pdfplumber` (`:62-66`); extra
  `pdf = ["pdfminer.six>=20251230", "pdfplumber>=0.11.9"]`
  (`pyproject.toml:58`).
- **Two paths, chosen per document.** Every page is opened with pdfplumber
  and a word-position heuristic (`_extract_form_content_from_words`,
  `:120-395`) decides whether the page is "form-like" (3+ aligned columns,
  ≥20% table rows, adaptive column tolerance). Form pages become pipe tables
  plus plain lines; other pages use `page.extract_text()`. If **no** page was
  form-like, the whole document is re-extracted with
  `pdfminer.high_level.extract_text` instead, because pdfminer spaces prose
  better (`:552-574`). Any exception falls back to pdfminer (`:576-579`).
- **Page boundaries — the answer is "accidentally, sometimes".** Experiment
  (reportlab 2-page PDF): `pdfminer.high_level.extract_text` returns
  `'Page one text\n\n\x0cPage two text\n\n\x0c'` — a **form feed `\x0c`
  after every page**. pdfplumber's per-page `extract_text()` returns clean
  page strings, which markitdown joins with `"\n\n"` (`:574`), **dropping the
  boundary**. So: prose-only PDFs carry invisible `\x0c` page ends (the
  orchestrator's `rstrip` leaves a *leading* `\x0c` on the next page's first
  line); form-like PDFs carry no page marker at all. Neither path emits a
  visible, numbered marker.
- **Tables.** Form-path tables are padded GFM pipe tables with a `---`
  separator row and the first detected row as header (`:351-379`,
  `_to_markdown_table` `:78-117`). No `<table>` HTML, no spans.
- **Headings:** none — pdfminer/pdfplumber output is flat text. Lone
  MasterFormat numbers (`.1`) are merged into the following line
  (`:14-57`, `:587`).
- **Images / OCR:** none. Scanned PDFs render to empty text (inferred from
  the absence of any image or OCR call).

### 1.3 DOCX (`converters/_docx_converter.py`, `converter_utils/docx/`)

- **Imports:** `mammoth` (`:17`); `lxml` inside the styles repair
  (`pre_process.py:225`); extra `docx = ["mammoth~=1.11.0", "lxml"]`
  (`pyproject.toml:56`). `DocxConverter` subclasses `HtmlConverter`.
- **Pipeline:** `pre_process_docx` rewrites the zip in memory — fixes
  zip-entry casing, rewrites `w:dstrike`→`w:strike`, repairs styles missing
  `w:type`/`w:styleId`, and converts OMML math to LaTeX wrapped in `$…$` /
  `$$…$$` (`pre_process.py:55-74`, `128-144`, `207-247`, `269-274`; the
  OMML→LaTeX table is `math/omml.py`, 417 lines + `latex_dict.py`). Then
  `mammoth.convert_to_html` with a style map (caller map + embedded map +
  `u => u`) (`:92-118`), then the shared HTML→Markdown path (`:123`).
- **Conventions:** whatever mammoth emits as HTML, through markdownify with
  ATX headings (`_markdownify.py:36`): `#`-headings from Word heading
  styles, GFM pipe tables from `<table>`, `<u>` kept literally (`:159-172`),
  checkboxes `[x]`/`[ ]` (`:146-157`).
- **Embedded images.** mammoth's default is an inline `data:` URI, and
  `_CustomMarkdownify.convert_img` **truncates data URIs** to
  `![alt](data:image/png;base64...)` unless `keep_data_uris=True`
  (`_markdownify.py:140-144`). Alt text comes from the Word `descr`
  attribute via mammoth (inferred; mammoth behaviour, not markitdown code).
  A subclass hook `_image_to_html(image_stream, stream_info, **kwargs)`
  can return an HTML fragment per image; `_DocxImages` tags each image with
  a UUID attribute and splices the fragment back into the HTML, lifting block
  content out of paragraphs (`_docx_converter.py:105-121`, `125-143`;
  `converter_utils/docx/_images.py:50-111`). **No LLM captioning for docx
  images in core** — the README says LLM descriptions are "currently only
  for pptx and image files" (`README.md:284`).
- **Page markers:** none. Word has no page concept in the XML and mammoth
  emits none.

### 1.4 XLSX / XLS (`converters/_xlsx_converter.py`)

- **Imports:** `pandas` + `openpyxl` (xlsx), `pandas` + `xlrd` (xls)
  (`:15-26`); extras `xlsx = ["pandas", "openpyxl"]`, `xls = ["pandas",
  "xlrd"]` (`pyproject.toml:57`). Includes a zip-rewrite repair for the
  legacy `showZeroes` attribute (`:40-93`).
- **Conventions:** `pd.read_excel(sheet_name=None)` → for each sheet
  `## {sheet name}` then `DataFrame.to_html(index=False)` through the HTML
  converter (`:151-159`). One GFM pipe table per sheet; the whole sheet is
  one table.
- **Experiment (scratch, replicating this exact path):** blank cells render
  as the literal text `NaN`, blank header cells as `Unnamed: N`, duplicate
  headers get pandas suffixes (`0.1`), integers in a float column render as
  `3.0`, and **row 1 is always the header** even when it is data. A sheet of
  10,000 rows × 6 columns rendered to **590,480 chars / 10,002 lines in
  1.6 s** (`read_excel` 0.22 s). No bound is applied: a sheet renders in
  full, O(cells).
- **Embedded images** are opt-in through the same `_image_to_html` hook;
  `_XlsxImages` walks the drawing relationships in the zip, and renders
  images **after** the sheet's table under `<h3>Images in this sheet:</h3>`
  (`:160-168`, `converter_utils/_xlsx_images.py:99-115`). Default: images
  are silently dropped.
- **Sheet markers:** the `## {sheet}` heading is the only marker; it can
  collide with a document heading only in the sense that it *is* a heading.

### 1.5 PPTX (`converters/_pptx_converter.py`)

- **Imports:** `python-pptx` (`:21`); extra `pptx = ["python-pptx"]`.
- **Conventions:**
  - `<!-- Slide number: N -->` on its own line before each slide (`:88`).
  - The title placeholder becomes `# Title` (`:109-112`); other text frames
    are emitted verbatim, one per shape, shapes sorted by (top, left),
    groups recursed in the same order (`:116-135`).
  - Tables: first row → `<th>`, HTML-escaped, then through the HTML
    converter → GFM pipe table (`:305-323`).
  - Charts: `### Chart: <title>` plus a Category × series pipe table, or
    `[unsupported chart]` (`:325-364`).
  - Speaker notes: `### Notes:` + text, only when non-empty (`:139-147`).
- **Embedded images** (`_convert_picture_to_markdown`, `:171-233`): emitted
  as `![alt](Picture1.jpg)` — a **fake filename** derived from the shape
  name (`:232-233`); with `keep_data_uris=True` a full base64 data URI
  (`:228-231`). The alt text is the LLM caption if one was produced, else
  the shape's `descr` (accessibility alt), else the shape name, with
  `[]`/newlines stripped (`:215-226`). SVG-only pictures are resolved from
  the `asvg:svgBlip` extension (`:235-281`).
- **LLM caption seam.** When `llm_client` and `llm_model` are present,
  `llm_caption()` base64-encodes the image, builds an OpenAI chat
  `messages=[{role: user, content: [{type: text, text: prompt}, {type:
  image_url, image_url: {url: data:…}}]}]` and calls
  `client.chat.completions.create(model=…, messages=…)`
  (`converters/_llm_caption.py:7-50`). The default prompt is
  `"Write a detailed caption for this image."` (`:11`). The client is
  **duck-typed** to the OpenAI SDK shape — any object with
  `.chat.completions.create` works; `openai` is only a test dependency
  (`pyproject.toml:80-84`). Caption failures are swallowed and fall back to
  alt text (`:185-195`).

### 1.6 Standalone images (`converters/_image_converter.py`)

- Accepts `image/jpeg`, `image/png` only (`:8-13`). Output is a key: value
  list of selected EXIF fields (`ImageSize`, `Title`, `Caption`,
  `Description`, `Keywords`, `Artist`, `Author`, `DateTimeOriginal`,
  `CreateDate`, `GPSPosition`) obtained by **shelling out to the `exiftool`
  binary** (`:48-66`; `_exiftool.py:10-57`, which also refuses exiftool
  < 12.24 for CVE-2021-22204), followed by `# Description:` + the LLM
  caption when a client is configured (`:68-81`). The caption code is a
  copy of `_llm_caption.py` (`:87-138`). **No OCR.** Without exiftool and
  without an LLM the rendering is the empty string.

### 1.7 HTML and the markdownify layer

- `HtmlConverter` parses with BeautifulSoup `html.parser`, strips `script`
  and `style`, converts `<body>` through `_CustomMarkdownify`; on
  `RecursionError` (deeply nested HTML) it falls back to `get_text("\n")`
  unless `strict=True` (`_html_converter.py:42-91`).
- `_CustomMarkdownify` fixes: ATX headings, `data:` URIs truncated, JS and
  non-http/file links de-linked, URL paths percent-quoted
  (`_markdownify.py:25-179`). This layer is what makes docx, xlsx and pptx
  tables look alike: all three go through `<table>` → markdownify.

### 1.8 Dependencies and limits

| Extra | Pulls in | Compiled / binary |
|---|---|---|
| core | `beautifulsoup4`, `requests`, `markdownify`, `magika~=0.6.1`, `charset-normalizer`, `defusedxml` | magika ships an ONNX model and `onnxruntime` (inferred — not measured here) |
| `pdf` | `pdfminer.six`, `pdfplumber` (which brings `pypdfium2`) | pypdfium2 wheel 3.4 MiB (observed during the scratch install) |
| `docx` | `mammoth~=1.11.0`, `lxml` | lxml |
| `xlsx` / `xls` | `pandas`+`openpyxl` / `pandas`+`xlrd` | pandas (+numpy) |
| `pptx` | `python-pptx` | lxml, Pillow |
| images | none in pip; `exiftool` **binary** at runtime | — |
| captions | none; duck-typed OpenAI-style client | — |

Limits: **none documented or enforced** — no max file size, page count or
timeout anywhere in `_markitdown.py` (grep for `limit|timeout|max_` finds
only an HTTP download chunk size, `:592`). The README's only guidance is
"sanitize your inputs" (`README.md:398`).

---

## 2. docling

### 2.1 Architecture

- **A typed document model, then serializers.** Every backend produces a
  `DoclingDocument` (pydantic, in `docling-core`), re-exported from
  `docling/datamodel/document.py:30-38`. Items (`TextItem`,
  `SectionHeaderItem`, `TableItem`, `PictureItem`, lists, groups) carry a
  list of `ProvenanceItem(page_no, bbox, charspan)` (docling-core
  `types/doc/document.py`, class `ProvenanceItem`). Pages are declared with
  `doc.add_page(page_no, size)`. Content is layered (`ContentLayer.BODY`,
  `FURNITURE`, `NOTES`, `INVISIBLE`); Markdown export defaults to `BODY`.
- **Format → (backend, pipeline).** `DocumentConverter` maps each
  `InputFormat` to a `FormatOption` (`document_converter.py:121-380`,
  defaults `:385-420`). PDF and images run `StandardPdfPipeline` (ML);
  Office formats run `SimplePipeline` (declarative backend, no models).
  PDF default backend is `ThreadedDoclingParseDocumentBackend`
  (`:272-275`); `pypdfium2_backend.py` is the alternative; images are
  wrapped as a one-page PDF-like backend (`backend/image_backend.py`).
- **Limits are first-class.** `DocumentLimits(max_num_pages, max_file_size,
  page_range)` (`datamodel/settings.py:26-29`), all defaulting to
  `sys.maxsize` / `(1, sys.maxsize)`, settable per `convert()` call
  (`document_converter.py:556-562`, `627-645`; a `FileSizeLimitExceededError`
  comes from docling-core `utils/file.py`). `PipelineOptions.document_timeout`
  (seconds, `None` = none) stops processing and returns
  `PARTIAL_SUCCESS` with a `TIMEOUT` error item; the docstring recommends
  **90–120 s in production** (`datamodel/pipeline_options.py:1389-1400`,
  `2085-2088`). The Excel backend caps a drawing XML part at 10 MB and an
  image part at 50 MB against zip bombs (`backend/msexcel_backend.py:331-334`).

### 2.2 PDF: StandardPdfPipeline vs NativePdfPipeline

- **Standard (default).** `_init_models` builds, in order: page
  preprocessing, OCR (auto-selected engine), layout object detection
  (default `docling-layout-heron`, RT-DETR), layout post-processing, table
  structure (TableFormer), page assembly, reading order, heading hierarchy,
  and the optional code/formula VLM (`pipeline/standard_pdf_pipeline.py:
  602-697`). The pipeline is multi-threaded per stage with bounded queues
  (`:4-17`, `:230-300`).
- **Defaults** (`datamodel/pipeline_options.py:2080-2215`):
  `do_table_structure=True`, `do_ocr=True` (`OcrAutoOptions`),
  `do_code_enrichment=False`, `do_formula_enrichment=False`,
  `generate_page_images=False`, `generate_picture_images=False`,
  `images_scale=1.0`, `force_backend_text=False`. OCR renders pages at
  `scale=3.0` → 216 DPI (`:258-268`).
- **TableFormer `FAST` vs `ACCURATE`.** `TableStructureOptions.mode`
  defaults to `ACCURATE`; the docstring says fast "prioritizes speed over
  precision", accurate is "recommended for production" (`:122-172`). Weight
  files (HF API, repo `docling-project/docling-models` rev `v2.3.0`,
  `models/stages/table_structure/table_structure_model.py:103-108`):
  **fast 145.5 MB, accurate 212.8 MB**. No timing numbers are published in
  the repo docs (grep for pages/s, sec/page finds nothing).
- **Native (model-free).** `NativePdfPipeline` turns every text cell from
  the parser into a `TextItem` with a provenance box and every embedded
  bitmap into a `PictureItem`; "no layout, OCR or table model runs, so
  conversion is fast, but the document has **no reading order, headings or
  tables**" (`pipeline/native_pdf_pipeline.py:80-89`;
  `document_converter.py:302-334`). This is the docling equivalent of
  markitdown's pdfminer path, with per-item page numbers kept.
- **Provenance in PDFs:** every item has `page_no` + bbox (observed in the
  native pipeline; the standard pipeline's assemble step builds the same
  items from layout clusters — inferred from `page_assemble_model` usage).

### 2.3 Office backends (SimplePipeline, no models)

- **DOCX** (`backend/msword_backend.py`, `python-docx`): walks the XML,
  emits headings, lists, tables (`add_table` `:3344`), pictures and
  footnotes/endnotes (`:908-910`). OMML equations become LaTeX wrapped in
  `<eq>…</eq>` bookends and split into inline formula items (`:800`,
  `:2445-2531`). Pictures: image bytes → PIL → `ImageRef`; WMF/EMF fall back
  to a LibreOffice conversion; 1×1 "spacer" images go to the `INVISIBLE`
  layer (`:3535-3567`, `:3644-3700`). **`grep -c "ProvenanceItem("` is 0**:
  the Word backend attaches no provenance, so **no page numbers and no
  page breaks are possible for docx** in docling either.
- **PPTX** (`backend/mspowerpoint_backend.py`, `python-pptx`): one
  `doc.add_page(page_no=slide_ind+1, size=…)` per slide and a `CHAPTER`
  group named `slide-N` (`:1470-1481`); every text/table/picture item has
  `ProvenanceItem(page_no=slide+1, bbox=shape box)` (`:312-313`). Shapes are
  iterated by position, groups recursed (`:1515-1532`). Speaker notes go to
  `ContentLayer.NOTES` (`:1534-1551`) — so they are **excluded** from the
  default Markdown export. Pictures keep their bytes as `ImageRef`
  (`:905-960`); charts keep their data and can be rasterised through
  LibreOffice (`:1399-1439`).
- **XLSX** (`backend/msexcel_backend.py`, `openpyxl`): "Each worksheet is
  converted into a separate page"; disconnected groups of cells become
  **separate tables** (flood fill, `_find_data_tables` `:951`,
  `_find_table_bounds` `:1035`); images become `PictureItem`s; provenance
  bbox is in **cell-index units** (`:302-329`). Legacy `.xls` goes through
  LibreOffice first. `MsExcelBackendOptions.sheet_names` filters sheets and
  `page_range` applies to sheets as pages (`:591-630`). Merged cells are
  indexed (`:207-241`). Ground truth `tests/data/xlsx/groundtruth/
  xlsx_01.xlsx.md`: `## Sheet1`, then a pipe table; `## Sheet2` with two
  tables for two cell regions.
- **Images as input** run the full StandardPdfPipeline (layout + OCR), so
  a PNG of a scanned page yields text; a photo yields a `PictureItem`.

### 2.4 Markdown export (docling-core 2.99.0)

`DoclingDocument.export_to_markdown(...)` and `MarkdownParams`
(docling-core `transforms/serializer/markdown.py`):

- **Page breaks.** `page_break_placeholder: str | None = None` — off by
  default. When set, `_iterate_items(add_page_breaks=True)` compares each
  item's `prov[0].page_no` with the previous one and yields a
  `_PageBreakNode(prev_page, next_page)` whenever it increases
  (`transforms/serializer/common.py`, `_iterate_items`). The node serialises
  to a sentinel `#_#_DOCLING_DOC_PAGE_BREAK_{prev}_{next}_#_#`, and
  `serialize_doc` replaces **every** sentinel with the **same constant
  placeholder string** (`markdown.py`, `serialize_doc`,
  `_get_page_breaks`). So the page numbers are known at replacement time
  but **not written** by the public API; a numbered marker needs a
  subclass overriding `serialize_doc`. Items without provenance (all of
  docx) never trigger a break. `export_to_markdown(page_no=N)` exports one
  page.
- **Tables.** `MarkdownTableSerializer`: GFM pipe tables, "exactly one
  header row and no spans"; multi-row column headers are joined per column
  with ` - `; a table with no `column_header` cells uses row 0 as header.
  Separator row is `| - | - |` (ground truth). `compact_tables=False` pads
  columns; the field doc says compact "is better for large tables and
  downstream processing". `escape_html=True` and `escape_underscores=True`
  by default.
- **Pictures.** `MarkdownPictureSerializer`: caption (before or after by
  `caption_placement`), then annotations when present — the picture
  classifier's class name and/or a description text — then the image part:
  `image_mode=PLACEHOLDER` → `<!-- image -->` (default); `EMBEDDED` →
  `![Image](data:image/png;base64,…)`, or an error comment if no image was
  generated; `REFERENCED` → `![Image](<uri>)`. Charts with tabular data are
  emitted as a pipe table (`enable_chart_tables=True`).
- **Text.** Single `\n` inside a paragraph becomes a GFM hard break
  (`"  \n"`); headings collapse newlines to spaces
  (`MarkdownTextSerializer._md_line_breaks`, `_heading_line_breaks`).
  Ground truth (`tests/data/pdf/groundtruth/2203.01017v2.md`): `## `
  headings, paragraphs, pipe tables, **no page markers** by default; pptx
  ground truth has slide titles as `# ` and bullets, **no slide markers**.

### 2.5 Picture description (captioning) and classification

- `PictureDescriptionApiOptions`: OpenAI-compatible chat-completions `url`
  (default `http://localhost:8000/v1/chat/completions`), `headers`,
  `params`, `timeout=20.0`, `concurrency=1`, `prompt="Describe this image
  in a few sentences."`, `provenance` string, `usage_response_key`
  (`datamodel/pipeline_options.py:886-975`). Requires
  `enable_remote_services=True` on the pipeline — **network is opt-in**.
- `PictureDescriptionVlmOptions` runs a local HF model; presets
  `HuggingFaceTB/SmolVLM-256M-Instruct` and
  `ibm-granite/granite-vision-3.3-2b` (`:1098-1107`;
  `docs/usage/enrichments.md:128-173`). Off by default
  (`do_picture_description`, `:1475`); classification
  (`docling-project/DocumentFigureClassifier-v2.5`,
  `datamodel/stage_model_specs.py:1084-1089`) is also a switch.
- Descriptions land as annotations/meta on the `PictureItem` and are
  printed by the Markdown picture serializer (2.4).

### 2.6 Chunking (docling-core `transforms/chunker/`)

- `HierarchicalChunker` yields one chunk per item (lists merged, tables
  whole) with `DocMeta(doc_items, headings, captions, origin)`;
  `doc_items` are the full `DocItem`s, so **every chunk keeps its
  provenance (page_no + bbox)**. `HybridChunker` adds a tokenizer
  (default HuggingFace via `transformers`; `semchunk` required), splits
  oversized chunks, merges undersized peers, and can repeat table headers
  (`hybrid_chunker.py`, class docstring and fields;
  `docs/concepts/chunking.md:61-83`). Chunk text is serialised from the
  items, so page markers are *not* in chunk text; page lives in metadata.
- A `LineBasedTokenChunker` exists for tables/code/logs (`docs/concepts/
  chunking.md:85-99`) — the closest analogue to vfs's line-range chunks.

### 2.7 Dependencies and model weights

`pyproject.toml` (comment at `:48`: "MINIMAL BASE (8 packages) - ~50MB"):

| Extra | Pulls in |
|---|---|
| base | `pydantic`, `docling-core`, `pydantic-settings`, `filetype`, `requests`, `certifi`, `pluggy`, `tqdm`, `langcodes` (`:49-59`) |
| `convert-core` | `numpy`, `pillow`, `rtree`, `scipy` (`:79-84`) |
| `format-pdf` | `pypdfium2` + `docling-parse` (`:96-105`) |
| `format-docx/pptx/xlsx` | `python-docx`, `python-pptx`, `openpyxl` (`:108-122`) |
| `feat-ocr-*` | `rapidocr` (+`onnxruntime`), `easyocr` (+`scikit-image`), `tesserocr`+`pandas`, `ocrmac` (`:198-227`) |
| `models-local` | `torch`, `torchvision`, `docling-ibm-models`, `accelerate`, `huggingface_hub` (`:232-240`) |
| `models-vlm-inline` | `transformers`, `timm`, `open-clip-torch`, `mlx-vlm` on Apple silicon, … (`:258-275`) |
| `feat-chunking` | `docling-core[chunking]` → `transformers`, `semchunk` (`:280-284`) |
| `standard` | pdf + models-local + rapidocr + office + web + latex + email + iwork + chunking + cli (`:311-313`) |

Model weights (HF API, bytes → MB, observed 2026-10-05):

| Model | Repo | Size |
|---|---|---|
| Layout (default Heron) | `docling-project/docling-layout-heron` `model.safetensors` | 171.7 MB |
| TableFormer fast / accurate | `docling-project/docling-models` `model_artifacts/tableformer/{fast,accurate}` | 145.5 MB / 212.8 MB |
| Code/formula VLM | `docling-project/CodeFormulaV2` | 631 MB |
| SmolVLM-256M (caption preset) | `HuggingFaceTB/SmolVLM-256M-Instruct` | 513 MB |
| Granite Vision 3.3-2b (caption preset) | `ibm-granite/granite-vision-3.3-2b` | 5.95 GB |
| Picture classifier | `docling-project/DocumentFigureClassifier-v2.5` | not measured |
| RapidOCR "small" `ch` models | URL list in `models/stages/ocr/rapid_ocr_model.py:133` | not measured |

So the **default PDF path** (layout + TableFormer accurate, OCR auto,
no enrichments) downloads ≈ 385 MB of weights on top of a torch install;
`docling-tools models download` prefetches them
(`utils/model_downloader.py:55-140`). The **native** PDF path needs only
`format-pdf` (pypdfium2 + docling-parse) and no weights. Office formats need
only their parser and `convert-core` (Pillow for images).

---

## 3. Comparison: emitted conventions per format

| Aspect | markitdown | docling (Markdown export, defaults) |
|---|---|---|
| Output model | Markdown string only | `DoclingDocument` → Markdown/HTML/JSON/DocTags |
| Headings | ATX `#` (from docx styles, pptx title → `#`, xlsx sheet → `##`) | ATX; pdf headings from the layout model; `## Sheet` for xlsx; pptx title → `#` |
| PDF pages | pdfminer path: `\x0c` at page end (invisible); pdfplumber path: none | per-item `page_no`; `page_break_placeholder` off by default, constant string when on |
| PDF tables | word-position heuristic → padded pipe table (form-like pages only) | TableFormer → pipe table (single header row, spans flattened) |
| PDF headings / reading order | none | layout model + reading-order + heading hierarchy (standard); none (native) |
| OCR | none in core (plugin via LLM vision) | auto engine on by default; RapidOCR/EasyOCR/Tesseract/macOS |
| DOCX pages | none | none (no provenance at all) |
| DOCX math | `$…$` / `$$…$$` LaTeX | LaTeX formula items (`<eq>` bookends internally) |
| DOCX images | `![alt](data:image/png;base64...)` truncated; hook for custom HTML | `<!-- image -->` (+ caption/description if enriched) |
| XLSX sheets | `## Sheet` + one pipe table for the whole sheet (pandas: `NaN`, `Unnamed: N`, row 1 = header) | `## Sheet` + one table **per contiguous cell region**; sheet = page N |
| XLSX images | dropped unless hook overridden (`Images in this sheet:`) | `<!-- image -->` after tables |
| PPTX slides | `<!-- Slide number: N -->` | slide = page N; no marker unless `page_break_placeholder` |
| PPTX notes | `### Notes:` + text | `NOTES` layer, excluded by default |
| PPTX images | `![alt or caption](ShapeName.jpg)` fake path; data URI opt-in | `<!-- image -->`, bytes kept as `ImageRef` |
| PPTX charts | `### Chart: title` + data table | chart data as table; image via LibreOffice opt-in |
| Standalone image | EXIF key/values via `exiftool` + `# Description:` LLM caption | full layout+OCR pipeline (scanned page → text) |
| Captions seam | duck-typed OpenAI client, kwargs, prompt "Write a detailed caption…" | URL/headers/timeout/concurrency/prompt options; remote gated by `enable_remote_services` |
| Table separator | `| --- |` (markdownify) / padded `|---|` (pdf) | `| - |` |
| Escaping | markdownify defaults | `escape_html`, `escape_underscores` on by default |
| Limits | none | `max_num_pages`, `max_file_size`, `page_range`, `document_timeout`, zip-part caps |
| Install for pdf text only | pdfminer.six + pdfplumber (+pypdfium2) | pypdfium2 + docling-parse (native pipeline) |
| Install for pdf layout/tables | n/a | torch + ~385 MB weights |

---

## 4. What this says for vfs

### 4.1 Format of the rendering: Markdown, GFM subset, line-oriented

Both projects converge on the same subset: ATX headings, GFM pipe tables,
`![alt](target)` images, HTML comments for out-of-band markers, LaTeX for
math. That subset is what agents already read well, and every construct is
**line-delimited**, which is exactly what the line-range chunker and
line-numbered grep need. **Recommendation (inferred):** render to Markdown,
restrict to that subset, and never emit a construct that spans lines
without a line break the reader can see (no padded multi-line cells, no
raw `<table>` HTML).

Two normalisation rules worth adopting from the evidence:

- Apply markitdown's final pass — `rstrip` every line, collapse 3+
  newlines to 2 — **inside the renderer**, so line numbers are stable
  across re-renders and independent of the upstream library's whitespace.
- Never rely on control characters for structure: pdfminer's `\x0c` is a
  real page boundary that is invisible in grep output and is lost by the
  first join that touches it.

### 4.2 Markers for pages, sheets and slides

Evidence: markitdown's `<!-- Slide number: N -->` is the only *numbered,
visible, single-line* unit marker either project emits by default; docling
proves the numbers are available (prov `page_no` for pdf, slide, sheet, and
image) but throws them away in the placeholder; docx has **no page
concept** in either project. **Recommendation (inferred):**

- One marker grammar for all unit kinds, an HTML comment on its own line,
  carrying the unit kind, the 1-based number, and for sheets the name:
  `<!-- page 3 -->`, `<!-- slide 3 -->`, `<!-- sheet 2: Budget -->`.
  A comment is invisible to Markdown renderers, greppable, and cannot
  collide with document headings (docling's and markitdown's `## Sheet`
  heading can).
- Emit the marker **before** the unit's first content line, and emit it
  **even for empty units**, so `page k` is always the k-th marker.
- Also keep the human-readable `## <sheet name>` heading for sheets
  (both projects do; it is what the LLM reads as context), directly after
  the marker.
- Because the marker is one line, "which page is line L on" is a scan for
  the last marker at or before L. Storing a small `(unit, first_line)`
  table as entry metadata at render time avoids the scan for grep labels
  and lets glean chunks carry a page without parsing text — this is what
  docling's chunk `DocMeta.doc_items[].prov` does out of band.
- docx: no page markers; mark nothing rather than inventing pages from
  `lastRenderedPageBreak` hints (neither project trusts them).

### 4.3 Tables

- GFM pipe table, **one row per line**, compact (no column padding) —
  docling's own field doc says compact is "better for large tables and
  downstream processing", and padding only costs bytes and breaks
  grep-by-value alignment nowhere.
- Blank cells render as empty, never `NaN`; blank headers render as empty,
  never `Unnamed: N`; integers stay integers. This rules out the pandas
  route — read cells with `openpyxl` directly as docling does.
- Header row: first row of the region (both projects); no spans — flatten
  merged cells by repeating or blanking (docling joins multi-row headers
  with ` - `).
- Cell text: escape `|`, replace newlines with a space (docling collapses
  heading newlines; markdownify does likewise in cells).
- xlsx: render **contiguous cell regions as separate tables** (docling), so
  a sparse sheet does not become a grid of empty cells.

### 4.4 Embedded images

Three tiers of information exist, and both projects show the seams:

1. **Placeholder with identity** — always. markitdown's
   `![alt](ShapeName.jpg)` points at a file that does not exist;
   docling's `<!-- image -->` has no identity at all. vfs *is* a
   filesystem, so the natural move (inferred) is to extract each embedded
   image as its own entry beside the document and link it:
   `![<alt>](<relative path of the extracted image entry>)`. The link
   extractor then sees a real edge, and the image can be rendered or
   captioned later on its own.
2. **Alt text / caption from the document** — free: pptx `descr`, docx
   `descr`, caption items in pdf (docling), chart titles. Put it in the
   `[...]` alt slot; put a document caption on the following line.
3. **Generated description or OCR** — optional enrichment, off by default,
   **never network by default** (docling gates it behind
   `enable_remote_services`). Shape the seam like docling's API options
   (endpoint URL, headers, prompt, timeout, concurrency) rather than
   markitdown's duck-typed SDK client — it needs no SDK dependency, and an
   OpenAI-compatible `chat/completions` with an `image_url` data-URI part is
   what both projects send. The result is written back as a line after the
   image link so it is grep-able and chunked with the surrounding text.

Standalone images: markitdown's EXIF rendering needs the `exiftool` binary
and gives nothing without it; docling runs full OCR. For vfs the useful
default is a one-line rendering of dimensions and format (Pillow, optional)
plus the same optional caption/OCR enrichment.

### 4.5 How large an xlsx rendering gets

Observed: 10,000 × 6 cells → 590 KB, 10,002 lines, 1.6 s with the pandas
path; the rendering is linear in cell count and neither project bounds it.
Per CLAUDE.md, vfs must not design a cap. **Recommendation (inferred):**
render all sheets in full, stream with `openpyxl` `read_only=True`
(inferred capability; not exercised here), split sparse sheets into regions,
expose the same *caller* knobs docling has — `sheet_names`, a page/sheet
`page_range`, and a `document_timeout` — and document the size profile in
the docstring. The line-range chunker already handles a 10,000-line file;
the thing to watch is that one table row stays one line so a chunk boundary
never splits a row.

### 4.6 PDF: which path

- **Text-layer path (default, light):** pypdfium2 (3.4 MiB wheel, PDFium)
  or pdfminer.six. Per-page extraction with a numbered marker per page.
  Verified pdfminer gives page boundaries; pypdfium2 is page-oriented by
  construction (inferred). No headings, no tables beyond heuristics — the
  same honesty docling's native pipeline states in its docstring.
- **Layout path (heavy, optional):** docling's StandardPdfPipeline: torch +
  ~385 MB weights (layout 172 MB + TableFormer accurate 213 MB; fast saves
  67 MB), OCR engine extra, `document_timeout` 90–120 s recommended by
  docling itself. This is a renderer plugin, not a core dependency.
- Scanned PDFs are empty under the light path; say so in the rendering
  (a marker line per page with no text) rather than silently rendering
  nothing.

### 4.7 Dependency posture: optional extras, three tiers

| Tier | Extra name (suggested) | Pulls in | Weights / binaries |
|---|---|---|---|
| 0 | core | nothing new; renderers absent → entry has bytes, no text rendering | — |
| 1 | `render-office` | `openpyxl`, `python-pptx`, `python-docx` (or `mammoth`+`markdownify` for the HTML route; markitdown's docx fidelity — styles, math, footnotes — comes from pre-processing the zip, which is ours to write either way) | pure Python + lxml |
| 1 | `render-pdf` | `pypdfium2` (or `pdfminer.six`) | 3.4 MiB wheel, no weights |
| 1 | `render-image` | `Pillow` | — |
| 2 | `render-caption` | none — plain HTTP to an OpenAI-compatible endpoint, opt-in per call | network, off by default |
| 3 | `render-layout` | `docling` (`docling-slim[format-pdf,models-local,feat-ocr-rapidocr]`) | torch + ≥385 MB weights + OCR models |

Both projects guard per-format imports and fail with a named
`MissingDependency` error only when that format is actually converted
(markitdown) or raise `ImportError` with an install hint in the backend
constructor (docling `msexcel_backend.py:352-353`). vfs should classify that
as a `Result` refusal naming the extra, not an exception.

### 4.8 One-line version

Render binaries to a line-oriented GFM Markdown subset; put a numbered
`<!-- page N -->` / `<!-- slide N -->` / `<!-- sheet N: name -->` comment
on its own line before each unit (none for docx); compact one-row-per-line
pipe tables with empty blanks; link embedded images to extracted sibling
entries with document alt text and an opt-in, network-off captioning seam;
light pure-Python extras per format by default and docling's model stack
as a separate heavy extra.
