# Study: Apache Tika as the reference design for an extraction seam

- **Status:** study (read-only; nothing here is imported by vfs)
- **Date:** 2026-10-05
- **Owner:** Clay Gendron
- **Sources:** `~/Git/Repos/tika`, shallow clone of `main` @ `37f2c4b`
  (committed 2026-10-05), Apache-2.0 (`tika:LICENSE.txt`). The tree is
  the unreleased 4.2.0 line (`tika:CHANGES.txt:1`), so some of what is
  cited (the `pages` block, `TimeoutLimits`, `PipesForkParser`) is newer
  than the 3.x Tika most writeups describe. Citations are
  `tika:<path>:<line>`; paths under `tika-core/` are
  `tika-core/src/main/java/org/apache/tika/...` and are abbreviated to
  `core:<package>/<File>` below.
- **Method:** read tika-core (parser, detect, sax, io, config,
  extractor, metadata packages), the PDF module, the OOXML extractors in
  the microsoft module, tika-pipes (`PipesServer`, `PipesClient`,
  `PipesForkParser`, `PipesResult`), the tika-server resource and its
  docs, and the configuration docs. No code was run; this is a design
  read. Each finding is marked **observed** (read in the source) or
  **inferred** (my reading of what it implies).

## The question this answers

vfs is deciding how a binary entry (PDF, docx, xlsx, pptx, image)
gets a derived text rendering stored in `vfs_content` so chunking,
grep, glean and link extraction run unchanged. Tika is the most
complete extraction seam in the open; this study records its shape so
vfs can borrow the *conventions* (not the code, not the library — vfs
is Python).

## 1. The interface: one call, stream in, handler plus metadata out

**Observed.** The whole of Tika hangs off a two-method interface
(`core:parser/Parser.java:35-68`):

- `getSupportedTypes(context)` — the media types this parser claims.
- `parse(stream, handler, metadata, context)` — consumes the stream
  (does not close it, `:51-52`), writes XHTML SAX events to `handler`,
  and treats `metadata` as **both input and output** (`:60`): the
  caller seeds it with a resource name and a declared type, the parser
  fills it in.

Four things ride on that call:

| piece | what it is | cite |
|---|---|---|
| `TikaInputStream` | A stream wrapper that can spool itself to a temp file on demand (`getPath()`), knows whether its length is *measured* or merely *declared* (`hasReliableLength()`), and can measure by spooling (`getLength()`). | `core:io/TikaInputStream.java:443-507` |
| `ContentHandler` | SAX sink. Parsers write XHTML; the caller picks the rendering by picking the handler. | `core:parser/Parser.java:48` |
| `Metadata` | A multi-valued string map with typed `Property` keys (internal vs external, value types). | `core:metadata/Metadata.java:209-405`, `core:metadata/Property.java:18-42` |
| `ParseContext` | A map keyed by Java class: limits, the embedded-document extractor, password provider, the parser to recurse with. | `core:parser/ParseContext.java:70-99` |

**Observed.** The one-call facade is `Tika.parseToString`: it wraps a
`WriteOutContentHandler(maxLength)` in a `BodyContentHandler`, parses,
swallows the SAX exception *only if* it was the write-limit signal, and
returns whatever text accumulated (`core:Tika.java:525-538`). That is
the "truncate and return" contract in one place.

**Observed.** Detectors that need random access spool the stream
themselves by calling `getFile()` (`core:detect/DefaultDetector.java:51-52`).
The PDF parser does the same: it enables rewind so later stages (xref
scan, renderer, per-page renders) can reopen the document
(`tika-parsers/.../pdf/PDFParser.java:191-195`).

**Inferred.** The design decision underneath: a parser is handed one
*source* that can be read once as a stream or promoted to a file, and
the seam never asks the caller which it has. vfs's blob row is the
file case; a streaming ingest is the stream case.

## 2. Detection: how a parser is chosen

**Observed.** `Detector.detect(stream, metadata, context)` returns a
`MediaType` or `application/octet-stream`; it must `mark` before
reading and `reset` before returning, and never closes the stream
(`core:detect/Detector.java:37-58`).

**Observed.** `DefaultDetector.detect` is a fixed pipeline
(`core:detect/DefaultDetector.java:136-161`):

1. A **user override** or **parser override** in metadata short-circuits
   everything (`core:detect/CompositeDetector.java:99-115`; keys
   `tk:content-type-user-override`, `tk:content-type-parser-override`).
2. **Magic bytes** via `MimeTypes`; the result is stamped as
   `tk:content-type-magic-detected` whatever wins later (`:144-146`).
3. **Container detectors** loaded by SPI (OLE2, zip-family) run next
   (`:148-150`).
4. **Text detection** runs only if both of the above said
   octet-stream (`:152-157`).
5. The **most specific** candidate wins, decided by the media-type
   registry's supertype hierarchy; an unrelated container verdict beats
   magic (`:163-198`).

**Observed.** Inside `MimeTypes.detect`, the magic read is bounded by
the registry's minimum prefix length and is only *shortened* by a
reliable measured length — a declared `Content-Length` may lie and
would silently truncate the magic prefix (`core:mime/MimeTypes.java:544-562`).
Then the **filename glob** and the **declared Content-Type** are
applied as *hints*: a hint can specialise or select among the magic
candidates, but a hint that contradicts magic loses
(`:564-614`, `applyHint` `:627-650`). The exception is interpreted
server-side scripts over HTTP, where the name is ignored (`:594-596`).

**Observed.** `CompositeParser` builds a `MediaType -> Parser` map from
every component's `getSupportedTypes`, normalised through the
registry; **later entries override earlier ones** (`core:parser/CompositeParser.java:114-137`).
Lookup reads `tk:content-type-parser-override` first, then
`Content-Type`, then walks up the supertype chain, and finally returns
the fallback — `EmptyParser` by default (`:300-323`, `:77`). An unknown
type is therefore "no text", not an error.

**Observed.** Per-mime overrides are a decorator, not a registry
mutation: `ParserDecorator.withTypes`, `withoutTypes`,
`withMimeFilters` wrap a parser so it claims or disclaims a set of
types (`core:parser/ParserDecorator.java:72-104`). In JSON config this
is `_mime-include` / `_mime-exclude` on a parser entry
(`tika-serialization/.../loader/ParserLoader.java:102,342-359`). A
`parsers` list loads *only* what it names; a `default-parser` entry
brings the rest back, and configuring a parser excludes its default
copy automatically (`tika:docs/modules/ROOT/pages/configuration/index.adoc:111-125`).

**Observed.** `AutoDetectParser.parse` is the full top-level sequence
(`core:parser/AutoDetectParser.java:148-225`): optional digest → detect
→ stamp `Content-Type` → metadata-only short-circuit → zero-byte check
(throws `ZeroByteFileException` by default, `:166-175`) → wrap the
handler in `SecureContentHandler` → seed `Parser` and `Detector` into
the context so embedded documents recurse through the same composite
(`:260-273`) → delegate. `CompositeParser.parse` then wraps any
`RuntimeException`, `IOException` or `SAXException` that did not come
from the stream or the handler into a `TikaException`, so a parser bug
is classified rather than leaking (`core:parser/CompositeParser.java:337-379`).

**Observed.** OCR engines are not parsers in this tree. A
`ContentEnricher` is a parser a *container parser invokes* on bytes it
already parsed (OCR on an image, a rendered page); it is never
dispatched to by the composite (`core:parser/enricher/ContentEnricher.java:17-29`;
`configuration/index.adoc:205-262`).

## 3. What the XHTML body carries, per format

**Observed.** `XHTMLContentHandler` is the parser-side helper. It
lazily emits `<html><head>` (one `<meta name= content=>` per metadata
value, then `<title>`), then `<body>`; after every block element in its
`ENDLINE` set it appends `\n`, and before `li`, `dd`, `dt`, `td`,
`th` it prepends `\t` (`core:sax/XHTMLContentHandler.java:47-73,282-283,298-300`).
So the plain-text projection of any Tika document already has
newline-terminated blocks and tab-separated cells, without the text
handler knowing anything about tables.

**Observed.** Output renderings are chosen by handler type: `TEXT`,
`HTML`, `XML`, `BODY`, `IGNORE`, `MARKDOWN` — the factory's default is
now `MARKDOWN` (`core:sax/BasicContentHandlerFactory.java:42,143-156`).
`ToTextContentHandler` drops everything but character events (and
skips `style`/`script` bodies). `ToMarkdownContentHandler` turns
`<table>` into GFM pipe tables but treats `<div>` as a bare block
boundary — **the `class` attribute, and with it the page/sheet/slide
identity, is lost in Markdown output**
(`core:sax/ToMarkdownContentHandler.java:197-200,325-335`).

### PDF

| boundary | element | cite |
|---|---|---|
| page | `<div class="page">` … `</div>` | `tika-parsers/.../pdf/AbstractPDF2XHTML.java:333,961` |
| paragraph | `<p>` from PDFBox's paragraph detection | `tika-parsers/.../pdf/PDF2XHTML.java:182-194` |
| line | `\n` (ignorable whitespace), word separator as characters | `:231-245` |
| annotation | `<div class="annotation">` with `annotationTitle` / `annotationSubject` / `annotationContents` sub-divs | `AbstractPDF2XHTML.java:1043-1078` |
| bookmarks | nested `<ul><li>` | `:1466-1506` |
| AcroForm | `<div class="acroform"><ol>…` | `:1567-1577` |

**Observed.** `sortByPosition` is a config flag (default `false`)
pushed into the PDFBox text stripper, alongside `averageCharTolerance`
0.3, `spacingTolerance` 0.5, `dropThreshold` 2.5,
`suppressDuplicateOverlappingText` false
(`tika-parsers/.../pdf/PDFParserConfig.java:65-113,201-217`). A page
cap `maxPages` (-1) breaks the page loop (`:147`;
`AbstractPDF2XHTML.java:1715-1719`). Per page, two numbers are added to
metadata: `pdf:chars-per-page` and `pdf:unmapped-unicode-chars-per-page`
(`AbstractPDF2XHTML.java:929-930`; `core:metadata/PDF.java:120-122`) —
they are the OCR verdict's inputs.

**Observed.** OCR is a *text policy*, not a parser option
(`core:parser/pages/TextPolicy.java`): `EXTRACT` (never OCR), `AUTO`
(OCR a page whose extracted text is poor), `EXTRACT_AND_OCR`, `OCR`
(engine only), `NONE`. `AUTO`'s thresholds default to
`totalCharsPerPage` 10 and `unmappedUnicodeCharsPerPage` 10; there is
an `ocr.maxPages` budget and the per-task deadline clips each OCR call
(`core:parser/pages/PagesConfig.java` `Auto.defaults`, `Ocr`;
`docs/.../configuration/pages.adoc:1-85`). `pdf:ocr-page-count` is
stamped after the parse (`PDFParser.java:258`). A page whose text or
OCR failed is still emitted and closed (`AbstractPDF2XHTML.java:951-953`).

### docx (SXWPFWordExtractorDecorator)

**Observed.**

- Paragraphs are `<p>`; a paragraph whose style name starts with
  `Heading N` becomes `<hN>` (capped at `h6`); any other named style
  becomes `<p class="styleName">` with spaces turned to underscores
  (`tika-parsers/.../microsoft/WordExtractor.java:159-178`).
- Tables are literal `<table><tr><td>`; paragraphs inside a cell are
  separated by `\n` rather than nested `<p>`
  (`.../ooxml/OOXMLTikaBodyPartHandler.java:150-152,278-315`).
- Order: headers first, then the main body, then diagrams, charts and
  footers at the end — "OOXML is flow-based, not page-based", so there
  is no page boundary in docx output (`.../ooxml/SXWPFWordExtractorDecorator.java:258-300`).
- Footnotes, endnotes and comments are inlined *at the point of
  reference* inside `<div class="footnote|endnote|comment">`
  (`OOXMLTikaBodyPartHandler.java:384-406`); a glossary document gets
  `<div class="glossary">` (`SXWPFWordExtractorDecorator.java:128-134`).
- `OfficeParserConfig` defaults: `includeHeadersAndFooters` true,
  `includeDeletedContent` false, `includeMoveFromContent` false,
  `includeShapeBasedContent` true, `extractMacros` false,
  `extractThumbnail` true, `includeGlossary` true
  (`.../microsoft/OfficeParserConfig.java:24-48`).

### pptx (SXSLFPowerPointExtractorDecorator)

**Observed.** One `<div class="slide-content">` per slide
(`.../ooxml/SXSLFPowerPointExtractorDecorator.java:197-224`); after
each slide, in order, `<div class="slide-master-content">`,
`<div class="slide-notes">`, `<div class="slide-notes-master">` when
configured (`:226-241`; defaults `includeSlideNotes` true,
`includeSlideMasterContent` true). Hidden slides are counted into
`msoffice:ppt:num-hidden-slides` (`:131-133`). The wrapper div comes
from a shared helper that wraps any related part in
`<div class="<label>">` (`.../ooxml/AbstractOOXMLExtractor.java:691-730`).

### xlsx (XSSFExcelExtractorDecorator)

**Observed.** Per sheet: `<div class="sheet"><h1>SheetName</h1>
<table><tbody>` … `</tbody></table>` then headers, footers, shape
text and hyperlinks, then `</div>`
(`.../ooxml/XSSFExcelExtractorDecorator.java:207-256`). Each row is
`<tr>`, each cell `<td>` holding the *formatted* value; gaps between
cells are emitted as empty `<td>` so columns stay aligned; a cell
comment is appended as `<br>author: text` (`:1052-1080`). Missing rows
are skipped unless `includeMissingRows` is on. Hidden and
very-hidden sheet names, data connections, external links, DDE links
and the like are metadata booleans, not text
(`core:metadata/Office.java:161-235`).

**Inferred.** With the `\t`-before-`td` and `\n`-after-`tr` rules from
§3's first paragraph, the plain-text projection of a sheet is a
TSV-like block headed by the sheet name. That is the convention worth
keeping.

### Embedded documents (all containers)

**Observed.** When an embedded document's text is inlined into the
parent, it is wrapped in `<div class="package-entry">` with an `<h1>`
holding the resource name (switchable by
`SAXOutputConfig.writeFileNameToContent`, default true)
(`core:extractor/ParsingEmbeddedDocumentExtractor.java:194-206`;
`core:sax/SAXOutputConfig.java:51`). Every embedded part is typed by
`tk:embedded-resource-type`, one of `INLINE`, `ATTACHMENT`, `MACRO`,
`METADATA`, `FONT`, `THUMBNAIL`, `RENDERING`, `VERSION`,
`ALTERNATE_FORMAT_CHUNK` (`core:metadata/TikaCoreProperties.java:554-564`).
Nesting of `package-entry` divs is itself a guarded limit (§4).

## 4. Write limits: truncate and flag, not fail

**Observed.** All output limits sit in one object in the context
(`core:config/OutputLimits.java:69-79`):

| limit | default | on breach |
|---|---|---|
| `writeLimit` (chars, total across container + embedded) | -1 (unlimited) | truncate, set `tk:exception:write-limit-reached=true`; **throw only if** `throwOnWriteLimit` (default false) |
| `maxXmlDepth` | 100 | always throws |
| `maxPackageEntryDepth` (nested `div.package-entry`) | 10 | always throws |
| `zipBombThreshold` (chars before the ratio check arms) | 1,000,000 | — |
| `zipBombRatio` (output chars : input bytes) | 100 | always throws |

The docstring states the policy outright: the write limit is a
truncation with a flag; the security limits have "no silent truncation
option" (`:36-44`).

**Observed.** `WriteOutContentHandler.characters` writes the remaining
budget, then either throws `WriteLimitReachedException` or sets
`ParseRecord.writeLimitReached`; after that every further character
event is silently dropped (`core:sax/WriteOutContentHandler.java:158-196`).
The exception is a `SAXException` subclass whose message says "Text up
to the limit is however available", with a cause-chain walker so any
wrapper can recognise it (`core:exception/WriteLimitReachedException.java:31-64`).
`CompositeParser` re-raises it unwrapped so it is never mistaken for a
parser failure (`core:parser/CompositeParser.java:366-367`).

**Observed.** In recursive mode the limit is one shared counter across
every handler in the tree (`SecureHandlerCounter`,
`core:parser/RecursiveParserWrapper.java:332-353`); a limit hit in the
parent means no children are parsed, and a limit hit in a child marks
that child's metadata and propagates (`:63-67,281-284`).

**Observed.** The zip-bomb guard counts output characters against input
bytes; the denominator is the measured length or the bytes read so far,
never a declared `Content-Length` ("a declared Content-Length is the
file's claim") (`core:sax/SecureContentHandler.java:213-243`). Its
private SAX exception is converted to `TikaException("Zip bomb
detected!")` only by the handler instance that raised it (`:207-211`).

**Observed.** Diagnostics are themselves bounded: at most 100 parser
names, 100 exceptions, 100 warnings, 100 embedded metadata objects per
parse; external-reference strings capped at 20 entries of 1,000 chars
(`core:parser/ParseRecord.java:45-53,115-131`). Exception strings can be
redacted (`FULL` / `MESSAGE_REDACTED` / `REDACTED`) and length-capped
with a `...[truncated]` marker (`core:config/ExceptionReporting.java:26-45`).

**Observed.** At depth 0, `CompositeParser` folds the record into the
container's metadata: `tk:exception:embedded-exception` (one per
failure), `tk:exception:embedded-warning`, and the four booleans
`write-limit-reached`, `embedded-resource-limit-reached`,
`embedded-depth-limit-reached`, `task-deadline-reached`
(`core:parser/CompositeParser.java:389-416`).

## 5. Recursion limit and the embedded-file policy

**Observed.** `EmbeddedLimits` (`core:config/EmbeddedLimits.java:77-80`):
`maxDepth` -1, `maxCount` -1, both non-throwing by default. The
semantics differ on purpose: hitting **depth** stops recursion below
that document but siblings continue; hitting **count** is a hard stop
for the rest of the parse (`:34-46`). Each sets its own
`tk:exception:*-limit-reached` flag (`:50-51`).

**Observed.** The check order is deadline → count → depth, and it runs
inside `parseEmbedded` even when a container forgot to call
`shouldParseEmbedded`, so limits cannot be bypassed
(`core:extractor/ParsingEmbeddedDocumentExtractor.java:111-180`).
Embedded-document failures are *recorded, not thrown*:
`EncryptedDocumentException` and any `TikaException` go to the record;
only `CorruptedFileException` is rethrown (as an `IOException`) "to
avoid infinite loops on corrupt sqlite3 files" (`:227-234`). An aborted
child parse has its open elements drained so the `package-entry` div
stays well-formed (`:212-214,246-249`).

**Observed.** Selection hooks: a `DocumentSelector(metadata) -> bool`
and a `FilenameFilter` in the context (`:74-87`;
`core:extractor/DocumentSelector.java`). Zero-byte embedded files are
ignored when `IgnoreZeroByteFileException` is in the context
(`core:parser/RecursiveParserWrapper.java:297-299`).

**Observed.** Two output shapes exist for a container:

- **Inline** (plain `AutoDetectParser`): children's text flows into the
  parent body inside `package-entry` divs; one metadata object.
- **Recursive** (`RecursiveParserWrapper`): one `Metadata` per
  document, content in `tk:content`, the container first in the list;
  each child carries `tk:embedded-resource-path` (name-based, unsafe as
  a filesystem path), `tk:embedded-id-path` (id-based, safe),
  `tk:embedded-id`, `tk:embedded-depth`, `tk:parse-time-millis`
  (`core:parser/RecursiveParserWrapper.java:55-61,247-254`;
  `core:metadata/TikaCoreProperties.java:87-138`). A nameless child
  gets a generated `embedded-N.<ext>` and
  `tk:resource-name-extension-inferred=true` (`:192-213`). Note the
  wrapper "holds all data in memory" (`:73-74`).

## 6. Timeouts, forking, isolation

**Observed — cooperative layer.** `TimeoutLimits`
(`core:config/TimeoutLimits.java:73-78`): `totalTaskTimeoutMillis`
3,600,000, `progressTimeoutMillis` 120,000, `throwOnDeadline` false. One
`ParseTimeout` per task is shared down every nesting level, so an OCR
call inside a zip inside a PDF draws from the same remaining budget;
`budgetFor(requested) = min(requested, remaining)`
(`core:config/ParseTimeout.java:27-33,173-192`). `checkpoint()` is
called at every `CompositeParser.parse` boundary
(`core:parser/CompositeParser.java:347-350`). Cancellation on an
exhausted deadline happens **only at embedded-document boundaries**:
remaining children are skipped, content so far is returned, and
`tk:exception:task-deadline-reached` is set (`ParseTimeout.java:219-223`;
`ParsingEmbeddedDocumentExtractor.java:112-133`). A per-operation
timeout reports both what it asked for and what it was granted
(`core:exception/TikaTimeoutException.java:30-70`).

**Observed — hard layer.** The in-process layer cannot stop a hung
parser; the forked JVM is the kill switch. In `PipesServer` the parse
runs on a worker thread while the main loop sends a `WORKING` heartbeat
every `heartbeatIntervalMillis` (default 1,000), kills the JVM at
`total + progress` (a grace window so the cooperative wind-down can
emit a `PARTIAL_TIMEOUT` result), and kills it when no checkpoint has
happened for `progressTimeoutMillis`
(`tika-pipes/tika-pipes-core/.../server/PipesServer.java:607-704`;
`PipesConfig.java:99`). `OutOfMemoryError` anywhere → exit with a
distinct code (`:641-651,706-714`). The heartbeat must be shorter than
the socket timeout or a healthy server looks dead (`:318-335`).

**Observed.** `PipesClient` maps the outcome to a status and marks the
fork for restart on `TIMEOUT`, `OOM`, socket timeout or an unexpected
exit code; it also runs its own backstop timer from the task's
`TimeoutLimits` in case the server's watchdog never fires
(`tika-pipes/tika-pipes-core/.../PipesClient.java:469-515,529-545,581-605`).
Forks are recycled after `maxFilesProcessedPerProcess` (100,000)
(`PipesConfig.java:91,135`); socket and startup timeouts default to 60 s;
request-supplied limits are clamped to an operator maximum
(`maxTotalTaskTimeoutMillis`, `PipesConfig.java:123-130`;
`TimeoutLimits.clampedTo`, `:184-193`).

**Observed.** `PipesResult.RESULT_STATUS` is grouped into five
categories — `FATAL`, `INITIALIZATION_FAILURE`, `TASK_EXCEPTION`,
`PROCESS_CRASH` (`OOM`, `TIMEOUT`, `UNSPECIFIED_CRASH`) and `SUCCESS`
(`EMPTY_OUTPUT`, `PARSE_SUCCESS`, `PARSE_SUCCESS_WITH_EXCEPTION`,
`PARSE_EXCEPTION_NO_EMIT`, …, `PARTIAL_TIMEOUT`)
(`tika-pipes/tika-pipes-api/.../PipesResult.java:38-95`). The
`PipesForkParser` throws only for infrastructure statuses; crashes and
per-document errors come back *as results*, and the next call restarts
the fork (`tika-pipes/tika-pipes-fork-parser/.../PipesForkParser.java:343-400`).
Payloads ≤ `maxInlineBytes` (10 MB) ride inline over the socket; larger
ones go by temp-file path (`:274-295`; `PipesConfig.java:71`).

**Observed.** The legacy `ForkParser`, which streamed SAX events across
the process boundary, is being replaced because that was "complex and
error-prone"; the replacement returns the finished text in metadata
(`PipesForkParser.java:20-30`). tika-server runs *every* parsing
endpoint in a fork — "not optional" — and answers `429` when no fork is
free versus `503` when a fork crashed, OOM'd or timed out
(`tika:docs/modules/ROOT/pages/using-tika/server/index.adoc:24-51`).

**Observed — memory.** The PDF parser hands PDFBox a mixed
memory/scratch-file setting capped at `maxMainMemoryBytes` 512 MB
(`PDFParserConfig.java:135`; `PDFParser.java:201-207`); a
`TikaMemoryLimitException` exists for allocation caps
(`core:exception/TikaMemoryLimitException.java`).

## 7. Which metadata keys are universal

**Observed.** Namespaces: `tk:` is Tika-native and reserved
(`core:metadata/TikaCoreProperties.java:55`); document facts use
Dublin Core (`dc:`), XMP, and format prefixes (`pdf:`, `msoffice:`,
`xmpTPg:`). The universal set, as `TikaCoreProperties` aliases it
(`:349-431`):

| concern | key |
|---|---|
| identity | `Content-Type` (`core:metadata/HttpHeaders.java:39`), `Content-Length`, `Content-Language`, `tk:resource-name` |
| detection trace | `tk:content-type-magic-detected`, `tk:content-type-hint`, `tk:content-type-user-override`, `tk:content-type-parser-override` |
| who parsed | `tk:parsed-by`, `tk:parsed-by-full-set`, `tk:parse-time-millis` |
| descriptive | `dc:title`, `dc:creator`, `dc:description`, `dc:subject`, `dc:language`, `dc:format`, `dc:identifier`; `dc:created`, `dc:modified`; `xmp:CreatorTool`; `meta:last-author` (as `MODIFIER`) |
| size | `xmpTPg:NPages` (`core:metadata/PagedText.java:34`); `meta:page-count`, `meta:slide-count`, `meta:word-count`, `meta:character-count`, `meta:table-count`, `meta:image-count` (`core:metadata/Office.java:92-148`) |
| per page (emitted renders) | `tk:page:number`, `tk:page:rotation` (`core:metadata/TikaPagedText.java:27-69`) |
| state | `tk:encrypted`, `tk:has-signature`, `tk:exception:*`, `tk:embedded-*`, `tk:digest:<ALG>` |

PDF additionally stamps `pdf:encrypted`, `pdf:has-xfa`,
`pdf:has-acro-form-fields`, `pdf:has-marked-content`,
`pdf:ocr-page-count`, the `pdf:docinfo:*` originals, and the access
permissions (`PDFParser.java:590-726`; `core:metadata/PDF.java`).

## 8. The failure vocabulary

**Observed** (`core:exception/`):

| class | meaning | top-level | embedded |
|---|---|---|---|
| `EncryptedDocumentException` | needs a password; `tk:encrypted=true` is set first | thrown | recorded |
| `UnsupportedFormatException` | parser recognised the type but not this variant | thrown | recorded |
| `ZeroByteFileException` | empty input | thrown by default | ignorable |
| `CorruptedFileException` | stop now, do not retry siblings | thrown | rethrown |
| `TikaMemoryLimitException` | an allocation cap | thrown | recorded |
| `TikaTimeoutException` | one operation's budget (requested vs granted) | thrown | recorded |
| `FileTooLongException` (`IOException`) | the fetcher's byte cap, before parsing | thrown | — |
| `WriteLimitReachedException` (`SAXException`) | a signal, not an error: text up to the limit is good | swallowed by the facade | marks child |
| `EmbeddedLimitReachedException` (`RuntimeException`) | `MAX_DEPTH` / `MAX_COUNT` / `DEADLINE`, only when configured to throw | thrown unwrapped | — |

An unknown type reaches `EmptyParser` and yields an empty body with no
error (§2).

## What this says for vfs

Labels: **observed** = Tika does this; **inferred** = my proposal for
vfs, informed by the observation.

### The extractor seam (proposal, in prose)

**Inferred.** Four small pieces, mirroring Tika's four:

- A **source**: the entry's blob bytes plus its declared name and
  declared media type. It must be able to say whether its length is
  measured (a `vfs_blobs` row always is) and to hand a parser either
  bytes or a temp-file path on request. This is Tika's
  `TikaInputStream` with the streaming case dropped for now.
- A **detector**: `detect(head_bytes, name, declared_type) ->
  media_type`. Order as Tika's: magic first, then the filename and the
  declared type as hints that may only specialise or choose among the
  magic candidates, never override them. Record the magic verdict on
  the rendering row separately from the final verdict. A caller-level
  override key must exist for the cases where magic is wrong.
- A **renderer registry**: `media_type -> renderer`, with a supertype
  walk (`application/vnd.ms-excel.sheet.macroenabled.12` falls back to
  the OOXML renderer; `text/*` falls back to the text renderer) and a
  last-registered-wins rule so a user-supplied renderer displaces the
  bundled one. Include/exclude filters live on the registration, not in
  the renderer. The fallback is an **empty rendering with
  `unsupported` set**, not a refusal — Tika's `EmptyParser`.
- A **renderer protocol**: `media_types()` and
  `render(source, limits) -> rendering`. The rendering is a value: the
  text, a block list (see below), a metadata dict, and a diagnostics
  record. Metadata flows in (name, declared type) and out, as in Tika.

**Inferred.** Do *not* copy Tika's intermediate: a SAX stream of XHTML
is right for a Java library with HTML consumers and wrong for vfs,
which has one consumer (`vfs_content`). Produce a small typed block
list instead — `page`, `sheet`, `slide`, `section`, `heading(level)`,
`paragraph`, `table(rows)`, `embedded(name, type)` — and project it to
text once. Tika's own Markdown handler shows the cost of not doing
this: the `div class="page"` boundary is lost in Markdown output (§3).

### Per-format conventions worth copying as conventions

**Observed in Tika; inferred as vfs conventions:**

- **PDF**: one block per page, in page order; paragraphs inside;
  `sortByPosition` off by default (reading order from the content
  stream), on as an option for multi-column scans. Record chars-per-page
  so an OCR verdict can be made later without re-parsing. Cap pages
  (`maxPages`) as a limit, not a feature.
- **docx**: flow, no pages. Heading styles → heading levels 1–6; other
  styles → paragraphs. Tables as rows of tab-separated cells. Headers
  first, body, footers last. Footnotes, endnotes and comments inline at
  the point of reference, marked as such.
- **pptx**: one block per slide with the slide number, then that
  slide's notes as a sub-block; master/layout text off by default (Tika
  turns it on, which duplicates placeholder text across slides —
  a vfs grep hit on every slide for the footer is noise).
- **xlsx**: one block per sheet headed by the sheet name; rows as
  tab-separated formatted values with empty cells kept so columns
  align; hidden sheets listed in metadata, their content included (the
  text is in the file; hiding is a view property).
- **Embedded documents**: inline the child's text in the parent's
  rendering under an `embedded(name, type)` block, typed
  `INLINE` / `ATTACHMENT` / `THUMBNAIL` / `MACRO` as Tika does, and
  default `MACRO`, `FONT`, `METADATA` to *not rendered*. The text of an
  attachment belongs to the parent entry's search surface unless and
  until vfs decides attachments are entries of their own.
- **Text projection**: newline after every block, tab before every
  cell, a blank line between pages/sheets/slides, and a plain marker
  line (sheet name as a heading, "Slide N") so a grep hit lands on a
  recognisable line. These are exactly Tika's `ENDLINE` / `INDENT`
  rules plus the `<h1>` it writes for sheets and embedded files.

### Limits, in one object

**Inferred, from §4–6.** One `RenderLimits` value with defaults, passed
to every render:

| limit | Tika default | proposed vfs stance |
|---|---|---|
| output characters | unlimited; truncate + flag | set a real default (the chunker's budget decides), truncate + flag, never fail |
| output : input ratio after a threshold | 100 : 1 after 1 M chars | copy; this is the decompression-bomb guard and it fails loudly |
| embedded depth / count | unlimited, non-throwing | depth 10 (Tika's package-entry guard), count 1,000; both non-throwing with flags |
| total wall time / progress stall | 1 h / 2 min | much smaller for the agent path (seconds), ETL-sized for the batch path; enforced by the *worker*, not the parser |
| pages | unlimited | optional cap, flagged when hit |
| parser memory | 512 MB PDF scratch | worker RSS cap; see isolation |
| diagnostics | 100 exceptions, 1,000-char strings | copy; bound the row, always |

### CPU isolation

**Observed → inferred.** Tika's conclusion after two generations is
unambiguous: the cooperative timeout returns partial content but cannot
stop a hung native parser; only a separate process can, and the process
must be *killed and restarted*, not asked. For vfs that means
extraction runs in a worker **subprocess** (pool of N), with a
heartbeat, a stall timer, a total timer with a grace window for the
cooperative wind-down, and a recycle-after-N-files rule for leaks. The
parent classifies the outcome into Tika's five categories
(fatal / init / task / crash / success-with-partial) and the crash
categories are *results*, not exceptions — the caller gets a rendering
row saying `crashed`, and the next render restarts the worker. Hand the
worker a path for large blobs and inline bytes for small ones, as pipes
does at 10 MB.

### The failure sentinel

**Inferred, from §4 and §8.** The rendering row in `vfs_content` is
always written, even when empty, so a later pass can see what happened
without re-rendering. It carries a small fixed set of flags, not a free
string:

`ok` · `truncated` (write limit) · `partial` (deadline or
embedded-limit hit; text so far is valid) · `encrypted` · `unsupported`
(no renderer, or the renderer's `UnsupportedFormat`) · `corrupt` ·
`crashed` (worker died: timeout / OOM / unknown) · `empty` (zero bytes,
or a parse that produced no text)

plus a bounded diagnostics list (class name + capped message, at most
N), the detector's two verdicts (magic, final), the renderer name and
version, and `render_time_ms`. Tika's single most useful convention
here is the **write-limit signal that is not an error**: truncated text
is good text with a flag, and every layer above the handler checks the
flag instead of catching an exception. vfs should carry that through:
`truncated` and `partial` renderings are indexed; `crashed`,
`encrypted`, `unsupported` and `corrupt` renderings are indexed as
empty with the flag, and the flag is what a retry policy reads.

### What not to copy

- **Inferred.** Metadata as a stringly multi-map. Keep the universal
  dozen (§7) as typed columns or a typed JSON shape; keep the
  format-specific tail as a JSON blob.
- **Observed.** Streaming parse events across the process boundary —
  Tika retired it.
- **Observed.** `writeMetadataToHead`: Tika writes every metadata value
  into the XHTML `<head>` as `<meta>` tags by default; for a text
  rendering this is noise, and vfs has the metadata column already.

## One-line version

Tika's seam is: detect by magic (names and declared types only
*narrow*), pick a renderer by media type with a supertype walk and
last-wins overrides, render to a block structure with page / sheet /
slide / embedded boundaries, truncate-and-flag on the write limit but
fail loudly on bomb ratios, cut recursion by depth and count with
flags, and run the whole thing in a killable worker whose crash is a
result row, not an exception.
