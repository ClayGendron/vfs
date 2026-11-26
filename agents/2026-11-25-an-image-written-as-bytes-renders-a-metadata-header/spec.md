# An image written as bytes renders a header of format, dimensions and readable EXIF tags, stores its width and height, and a PDF's embedded images get the same placeholder line docx and pptx emit

A draft, written on 2026-11-25. It is not reviewed, and nothing is built. Every claim about the tree is checked against `dev` at `27f3d24d`. It serves story E8 of [the roadmap](../../context/standards/roadmap.md) at gate 0.2 ("E8 — Render at write (159), images (152 C), `imports` edges (147), tuned fusion defaults", `context/standards/roadmap.md:638`); the story's whole text is "Independent of theme 3. Render at write moves up if D21 says so.", so the tests below are this unit's own criteria. It is unit 152-3 of [the conversion map](../2026-11-25-the-backlog-converted/units.md), converted from [the archived binary bodies spec](../../context/specifications/archive/152-binary-bodies-and-text-renderings/spec.md), sections 4 (embedded images), 7 (bundled renderers and extras), 8 (images), slice C and the image-header acceptance line, as sorted by [the study of that source](../2026-11-25-the-backlog-converted/studies/051-162/152-binary-bodies-and-text-renderings.md) and [the reassessment against dev](../2026-11-25-the-backlog-converted/reassessment/bodies-and-mounts.md). It rests on [the binary renderings memo](../../context/research/2026-10-05-binary-files-and-derived-text-renderings.md) and on slices A and B of the source, which are built. It waits on nothing that is not built.

## The outcome wanted

An agent or an ETL pipeline writes a PNG, JPEG, GIF, TIFF or WebP file as bytes. After the next `refresh` or `rebuild`, `stat` and `ls` show `render_status` `ok`, `read` returns a short header (format, pixel dimensions, orientation, and the camera, capture date, position, title, keywords and description where the file carries them), and `grep` and `search` find the image by any of those words. The entry's row holds the image's width and height in `media_width` and `media_height`. A host without Pillow sees `unavailable` naming `vfs[images]`. The rendering of a PDF carries one `![](embedded:n)` line for each image a page draws, as docx and pptx renderings already carry for their pictures. An image written before the upgrade is rendered by the next `rebuild` with no migration.

## Builds on

- Slices A and B of the archived spec 152, built: the bytes body, the renderer seam (`src/vfs/rendering/seam.py`), the registry (`registry.py`), the Markdown `Builder` (`markdown.py`), the four document renderers and the render stage of `rebuild` and `refresh` (`src/vfs/storage/backends/database/render.py`, `maintenance.py:414-475`). The dimension columns and the stamp that fills them are part of it.
- Unit 152-1, built on `dev` as decision 5 of [the write preconditions spec](../2026-11-20-write-takes-preconditions-and-an-append/spec.md): "A write of the body a row already holds is `unchanged`". A staged update whose `kind`, `source`, `content_hash` and `mime_type` equal the committed row's is dropped from the plan (`src/vfs/storage/backends/database/staging.py:459-484`), so a same-bytes overwrite keeps the rendering, its stamp and the two dimensions. This unit relies on that shape and pins it for images.
- [The two-engine spec](../2026-11-20-vfs-serves-sqlite-and-postgres-only/spec.md), built: the engines served are SQLite and Postgres, and an unknown dialect on the generic floor.
- [The refresh spec](../../context/specifications/archive/2026-10-31-refresh-the-incremental-index-verb.md), built: `refresh` renders only rows a write left `pending` (`render.py:150-188`, the `regenerate` flag).
- Sibling units of this conversion, none a dependency, each written, not reviewed and not built. [Unit 159-1](../2026-11-25-a-small-binary-write-renders-its-own-bytes-before-it-returns/spec.md) renders the binaries of a write within its budget before the write returns, through whatever the registry holds, and lands them through `land_renderings`, "the pass's own guarded stamp" (its decisions 1 and 11), so whichever of the two lands second gains images at write, their two dimensions included, with no further change to source. Its decision 21 rules what a test sees after a small bytes write, and the Tests section below follows it. [Unit 152-2](../2026-11-25-search-says-how-many-bytes-rows-it-could-not-read/spec.md) counts the pending bytes rows in a search's scope on one retryable warning (its decisions 2 and 7). It edits no source file named here, and it adds a class and a row of its own to two test files this unit also adds to, `tests/storage/database/test_render.py` and `tests/support/storage_contract.py`. [Unit 152-4](../2026-11-25-binary-bodies-are-documented-on-the-docs-site/spec.md) documents renderings and names five formats if this lands first; if that unit lands first, its decision 13 names the places on its pages that this unit edits (What the docs must say). Build order: any.

## Terms

- **Header**: the whole rendering of an image, three to nine lines of the form `label: value`.
- **Opener**: the class Pillow ships for one image format, such as `PIL.PngImagePlugin.PngImageFile`. Constructing it parses the file's header and decodes no pixel.
- **Paint**: one image a PDF page's content stream draws, either an image XObject named by a `Do` operator, at the page's level or inside a form XObject, or an inline image.
- **Stored dimensions**: the width and height of the pixel matrix as the file encodes it, before any EXIF rotation.

## What the code does today

- The bundled registry holds four renderers: `RendererRegistry.bundled()` returns pdf, docx, pptx and xlsx (`src/vfs/rendering/registry.py:44-46`). `src/vfs/rendering/` holds `seam.py`, `registry.py`, `markdown.py`, `pdf.py`, `docx.py`, `pptx.py`, `xlsx.py` and no image renderer (EXECUTED, `ls`).
- The sniffer proves five image types by magic: `image/png`, `image/jpeg`, `image/gif` and `image/tiff` in `_MAGIC` (`src/vfs/models/media.py:95-104`) and `image/webp` by its RIFF branch (`media.py:116-117`), each as a bare string literal. A body no signature matches keeps its declared type (`media.py:127`).
- A type no renderer claims is answered `unsupported` with the detail `no renderer for <type>` (`registry.py:101-103`). A `read` of such a row returns no text and a warning `no text rendering (unsupported)` (`src/vfs/storage/backends/database/reads.py:963-966`), and `grep` and `search` never see it.
- `media_width` and `media_height` are `Integer` columns of `vfs_entries` (`src/vfs/models/rows.py:415-416`) and row-only (`rows.py:86`). `Rendering` carries `width` and `height` (`seam.py:178-179`), `settle` keeps them (`seam.py:272`, `:274`), the guarded stamp writes them (`render.py:366-367`, `:417-418`), a twin borrows them (`render.py:228-252`), a copy carries them (`src/vfs/storage/backends/database/topology.py:104-105`) and a write clears them (`src/vfs/storage/backends/database/writes.py:1336-1337`). No renderer sets either, so both are null on every row (EXECUTED, `grep -rn "width\|height" src/vfs/rendering/`).
- The extras are `pdf`, `docx`, `pptx`, `xlsx`, `documents = ["vfs-py[pdf,docx,pptx,xlsx]"]` and `all`, which names `documents` (`pyproject.toml:56-64`). There is no `images` extra. Pillow 12.3.0 is locked (`uv.lock:2144-2145`) as a dependency of python-pptx (`uv.lock:2562-2567`).
- The PDF renderer writes each page's text and nothing for an image, and its docstring says so (`src/vfs/rendering/pdf.py:7-9`, `:44-47`). docx and pptx write one `![alt](embedded:n)` line per picture (`docx.py:206`, `pptx.py:100`) through `Builder.image` (`markdown.py:263-273`), which counts against `RenderLimits.embedded_count` and marks the rendering `partial` past it (`markdown.py:268-270`, `:310-312`). A placeholder is appended as structure, not text, so it never lifts a rendering out of `empty` (`markdown.py:272`, `:327-334`).

## The problem

An agent cannot find a photograph by its camera, its date or the caption its file carries, because an image is `unsupported` and has no text. A listing cannot show an image's size, because nothing stores it. A reader of a PDF's rendering cannot tell that a page holds a figure, though the source spec promised the placeholder line "in any document" (section 4). At the reference deployment's 10,000,000 files, every image is a row that `grep` and `search` cannot reach, and every scanned page is silent about what it holds.

## Decisions

### 1. The bundled `image` renderer claims exactly the five image types the sniffer proves by magic.

`vfs.models.media` gains `PNG`, `JPEG`, `GIF`, `TIFF` and `WEBP` for the five type strings, and the tuple `IMAGE_TYPES` holding them in that order, directly under them; `_MAGIC` and the WebP branch of `sniff_mime` use the names. `ImageRenderer.mimes` is `IMAGE_TYPES`. An image type the sniffer cannot prove (BMP, HEIC, AVIF, SVG) keeps its declared type and stays `unsupported`. Reason: magic decides the family and a declaration never overrides it, so these five are the only image types a row carries with proof. A body declared as one of the five that matches no signature still reaches its opener, which refuses it (decision 12). Precedent: the source, sections 1 and 8; the names follow `PDF`, `DOCX`, `XLSX` and `PPTX` (`media.py:63-66`).

### 2. Pillow is the parser, behind a new extra named `images`.

`pyproject.toml` gains `images` among the renderer extras, and `ImageRenderer.extra` is `"images"`. Reason: Pillow reads the header and the EXIF block of all five formats, it is already installed wherever `vfs[pptx]` is, and a third-party parser is a dependency decision on its own merits, outside the rule that vfs's engine code is Rust (AGENTS.md, Tooling, "Scope"). Precedent: the source, section 7 ("`image` on Pillow (`vfs[images]`)"); the memo names Pillow for image dimensions. The study names this as a dependency ruling that is not on record; it is choice 1.

### 3. The extra's floor is `pillow>=11.3`, and the lock stays at 12.3.0.

Reason: an extra's floor names the oldest release the project can claim on every interpreter it tests, and the CI matrix is 3.11 to 3.14 (`.github/workflows/test.yml:53`). 11.3.0 is the oldest release with a `cp314` wheel: 11.2.1 lists `cp39` to `cp313` and 11.3.0 adds `cp314` (EXECUTED 2026-11-25, PyPI's JSON file listing). A comment above the line gives this reason in words, as the `xlsx` line's comment does (`pyproject.toml:60-62`).

### 4. The `documents` umbrella gains `images`, and `all` follows through it.

`documents` becomes `vfs-py[pdf,docx,pptx,xlsx,images]`; the `all` line is unchanged because it names `documents` (`pyproject.toml:64`). The umbrella installs no new distribution, since `pptx` already brings Pillow. Reason: one install line gives every bundled renderer, and a renderer left out of it would be `unavailable` on a host that asked for all of them. Precedent: the source, section 7 ("the umbrella `vfs[documents]` for all five").

### 5. No describer, caption, OCR or image vector is built.

Decided 2026-10-05: no image description provider is built; the rendering of an image is its header alone. The generation of decision 15 leaves room for a later suffix, and nothing else here is shaped for one. Precedent: the source, section 8 and its non-goals; the study, open choice 7.

### 6. The rendering of an image is `label: value` lines in one fixed order, with no heading and no unit marker.

The lines are `format`, `dimensions`, `orientation`, `camera`, `captured`, `gps`, `title`, `keywords`, `description`, in that order. The first three are always written; each of the other six only when its value is present and non-blank after `flatten` (`markdown.py:73-75`). `format` is Pillow's format name (`PNG`, `JPEG`, `GIF`, `TIFF`, `WEBP`). `dimensions` is `<width>x<height>` with no spaces, so one token finds it. The lines are written as one paragraph through `Builder.paragraph`, so they count as text, inside one markerless unit opened by `Builder.boundary(1)` with `total_units=1`, so the unit table is empty. Reason: a grep for `camera: ` finds every photograph with a known camera, and a hit shows what the value is. Precedent: the source fixes which facts the header states (section 8) and that every construct is one line (section 4); `boundary` is the Builder's opening for a format without units (`markdown.py:178-189`).

```text
format: JPEG
dimensions: 4032x3024
orientation: portrait
camera: Acme Cam 1
captured: 2024-04-30T18:01:02
gps: 40.446111, -79.982222
title: Barn
keywords: barn;dusk
description: a red barn at dusk
```

### 7. Each tag line reads one named EXIF tag, and `title` and `keywords` read the Windows XP tags only.

| Line | Read from (Pillow's `ExifTags` names) | Form |
|---|---|---|
| `camera` | `Base.Make` and `Base.Model` of the first directory | joined by one space; the model alone when it already begins with the make, compared without case |
| `captured` | `Base.DateTimeOriginal` of the `IFD.Exif` directory, else `Base.DateTime` of the first | decision 8 |
| `gps` | `GPS.GPSLatitude`, `GPSLatitudeRef`, `GPSLongitude`, `GPSLongitudeRef` of the `IFD.GPSInfo` directory | decision 8 |
| `title` | `Base.XPTitle` | its bytes decoded as UTF-16-LE, NULs dropped |
| `keywords` | `Base.XPKeywords` | the same decoding, the file's own `;` separators kept |
| `description` | `Base.ImageDescription` | verbatim, through `flatten` |

An XP value is accepted as `bytes` or as a tuple of integers 0 to 255; any other type omits the line. Reason: EXIF has no title or keyword tag but the XP pair, and the other carriers (IPTC, XMP, a PNG text chunk) are separate containers with separate parsers; EXIF is the one block all five openers hand over parsed. Precedent: none on record; it is choice 2.

### 8. A capture date is written in ISO form, and a position in signed decimal degrees.

A value that parses as EXIF's `YYYY:MM:DD HH:MM:SS` is written `YYYY-MM-DDTHH:MM:SS`; any other non-blank value is written as found. No time zone is added, because the tag carries none. A position is `<latitude>, <longitude>`, each degrees plus minutes over 60 plus seconds over 3,600, negated for an `S` or `W` reference, to six decimals. Reason: an agent greps a date as `2024-04-30` and a position as one number pair. Precedent: the xlsx renderer writes its dates by `isoformat()` (`src/vfs/rendering/xlsx.py:243`), so the header carries no second date form.

### 9. `dimensions` and the two columns state the stored dimensions, and an EXIF orientation turns only the `orientation` word.

`dimensions`, `Rendering.width` and `Rendering.height` are the width and height the file encodes. `orientation` is `landscape`, `portrait` or `square`, from the shape as displayed: the stored width and height, exchanged when `Base.Orientation` is 5, 6, 7 or 8. Reason: the columns describe the bytes, as `content_hash` and `size_bytes` do, and a consumer that decodes the bytes gets that matrix; the word is what a person means by a portrait photograph. Precedent: none on record; it is choice 3.

### 10. A dimension past 2,147,483,647 is printed and not stored.

`vfs.models.media` gains `MAX_MEDIA_DIMENSION = 2_147_483_647`, the largest value a 32-bit signed integer holds, beside `MAX_RENDER_GENERATION_LENGTH` (`media.py:59`). When either dimension exceeds it, the `dimensions` line still states both, and the rendering carries `width` and `height` as `None`. Reason: the columns are SQLAlchemy `Integer` (`rows.py:415-416`), which is a 32-bit `integer` on Postgres and a 64-bit value on SQLite, and a renderer's answer must not depend on the engine (constitution, Article 4). A PNG header declaring a width of 2,147,483,648 opens and reports that size (EXECUTED, scratch probe on Pillow 12.3.0). The bound is the engine's own column range, not a size vfs chooses.

### 11. The renderer constructs the format's own opener and reads tags through the base `Image.getexif`, so no pixel is decoded and Pillow's pixel-count guard is not met.

`image.py` maps each of the five types to its opener module and class (`PIL.PngImagePlugin.PngImageFile`, `PIL.JpegImagePlugin.JpegImageFile`, `PIL.GifImagePlugin.GifImageFile`, `PIL.TiffImagePlugin.TiffImageFile`, `PIL.WebPImagePlugin.WebPImageFile`) in a private table of a named tuple `_Opener(module, name)`, resolves each module through `load_library` as `docx.py:72` and `pptx.py:47` do, and constructs the opener over `BytesIO(source.data)`. It never calls `PIL.Image.open` and never calls `load`. It reads tags by calling `PIL.Image.Image.getexif(image)`, the base method. Reason, from probes on Pillow 12.3.0 (EXECUTED 2026-11-25): `Image.open` refuses a PNG header declaring 20,000 by 20,000 pixels with `DecompressionBombError`, while `PngImageFile` reads the same header and reports `(20000, 20000)`; the guard protects a decode this renderer never performs, and applying it would refuse a large scan whose header reads in full. The base `getexif` over each of the five formats, and over a JPEG carrying six tags, called `ImageFile.load` zero times. An opener runs only the parser the row's type names, where `Image.open` offers the body to every registered decoder. Stated cost: a PNG `eXIf` chunk after the pixel data is not read, because the PNG opener stops reading chunks at the first `IDAT`. Precedent: AGENTS.md forbids a designed scale cap that no external system imposes.

### 12. A body its opener refuses is `corrupt`.

Any exception from constructing the opener answers `failure_from(exc, self.name, "corrupt")`, whose detail begins `image: ` and names the exception class and message; for a PNG signature followed by garbage that is `SyntaxError: broken PNG file ...` (EXECUTED). Anything raised after the opener returned reaches the registry, which answers `failed` (`registry.py:106-109`). Reason: the body matched the format's signature or was declared as that format, so a refusal means it is not a readable file of that format. Precedent: the source, section 6; the Office renderers answer a file their library cannot open as `corrupt`, caught as `Exception` (`pptx.py:45-46`, `docx.py:70-71`).

### 13. An unreadable tag omits its own line, and the rendering stays `ok`.

The three directory reads (the first, `IFD.Exif`, `IFD.GPSInfo`) are each guarded: a read that raises yields no line from that directory. A value of the wrong type, an XP value that does not decode as UTF-16-LE, a blank date, or a position that is not three finite numbers within 90 degrees of latitude and 180 of longitude omits its own line and no other. Reason: format and dimensions are true whatever the tags hold, and a zero denominator reads as not-a-number (EXECUTED: `float(IFDRational(1, 0))` is `nan`). Precedent: the source says the image renderer always produces a header (section 8); a failure state is for a rendering that could not be made.

### 14. No render limit is added.

The ten fields of `RenderLimits` (`seam.py:111-120`) bound the header: `chars` cuts a header whose lines pass the budget, as it cuts any rendering, and the width and height are kept on the cut rendering; `seconds` is read when the one unit opens; `ratio` is not reachable, since every value comes out of the body and the guard starts past 1,000,000 characters (`markdown.py:347-349`). No pixel is decoded, so no pixel or memory limit is needed. Reason: a new limit opens the question of how a raised limit retries what it refused, which [the placeholder memo](../../context/research/2026-11-13-how-an-entry-refused-under-a-render-limit-is-retried-once-the-limit-is-raised.md) holds and no spec answers.

### 15. `ImageRenderer` is a `BundledRenderer` whose generation is `image/1+pillow-<version>`, and an absent Pillow is `unavailable` naming `vfs[images]`.

`name = "image"`, `extra = "images"`, `package = "PIL"`, `distribution = "pillow"`, `mimes = IMAGE_TYPES`, and the default `revision` of 1. Without Pillow its generation is `image/unavailable` and the registry answers `the image renderer needs vfs[images]` (`registry.py:104-105`), so installing the extra changes the stamp and the next `rebuild` retries. Precedent: the source, section 8 ("The generation is `image/1+pillow-<version>`"); a bundled renderer's version is `<revision>+<distribution>-<version>` (`seam.py:419-421`).

### 16. The module is `src/vfs/rendering/image.py`, exported from `vfs.rendering`, and the bundled registry lists it last.

`RendererRegistry.bundled()` returns `(PdfRenderer(), DocxRenderer(), PptxRenderer(), XlsxRenderer(), ImageRenderer())`. `vfs/rendering/__init__.py` imports `ImageRenderer` and adds it to `__all__`, as it does each bundled renderer. The module follows AGENTS.md's file organization: the opener table under the constants, the class, then `# Internal helpers` holding `_tag_lines`, `_camera`, `_captured`, `_position`, `_xp_text` and `_orientation_word`, each returning `None` for a value it cannot read. Reason: one module per format is the package's layout, and `rendering` is a public module that lists its offer in `__all__` (`documentation/maintainers/how-we-name.md`, "Public and private").

### 17. An image stamped `unsupported` before this lands is rendered by the next `rebuild`, with no migration, and `refresh` leaves it.

The dirty predicate compares a row's stamp with the generation its own type resolves to today, so a newly claimed type makes its rows dirty in the full pass (`render.py:170-175`, `registry.py:83-97`). `refresh` reads only `pending` rows (`render.py:176`, `:180`), so it renders a new image and leaves an old one for the `rebuild`. Precedent: pinned for a generic type by `tests/storage/database/test_render.py::TestRetryByType::test_an_unsupported_row_is_retried_once_its_type_is_claimed`.

### 18. No statement, table, column or schema format changes, and no verb projects the two dimensions.

The width and height ride the existing guarded stamp; a twin borrows them, a copy carries them and a write clears them, as listed under What the code does today. Both stay row-only columns. `SCHEMA_FORMAT_VERSION` stays 28 (`rows.py:135`). Reason: a field on an observation is a public name, and no listing or wire consumer is specified for it yet. Precedent: the source, section 8 ("`media_width` and `media_height` are also stored as integer columns on the entry row").

### 19. Each image a PDF page paints gets one placeholder line after that page's text, numbered across the document.

Each paint is one line, so an image painted twice is two lines, and an image listed in a resource dictionary and never painted is none. The lines follow the page's text, in painting order, because pypdf returns a page's text whole. The number runs across the document, as it does in docx and pptx. Precedent: the source, section 4 (a placeholder for embedded images "in any document"); `docx.py:206` and `pptx.py:100`.

### 20. Paints are counted on pypdf's operand visitors during the page's one text extraction.

`PdfRenderer` passes `visitor_operand_before` and `visitor_operand_after` to the one `extract_text` call it makes per page. A private `_Paints` class in `pdf.py` holds a stack whose top is the XObject dictionary in force, starting from the page's inherited `/Resources` (`get_inherited`), and the page's count. Before a `Do`, the name is resolved in the top dictionary and one entry is pushed: for a form, the form's own `/Resources` XObject dictionary, or an empty one; for an image, an empty entry, after counting one paint; for a name that does not resolve, an empty entry. After a `Do`, one entry is popped, so the stack is balanced whatever the name was. Before an `INLINE IMAGE` operation, the count rises by one. A lookup that raises is treated as a name that does not resolve, so a malformed entry never fails a page that rendered before. `page.images` is never read: it decodes each image. Reason: the content stream is parsed once, as today, and the walk decodes nothing. pypdf calls the visitors around every `Do` it meets, inside forms too, and skips a cyclic form and every form past `xform_maximum_invocations_per_extraction` (5,000, `pypdf/_configuration.py:90` in 6.19.0) without visiting inside it, so the stack mirrors only what pypdf walked. EXECUTED on pypdf 6.19.0 (scratch probe, 2026-11-25): a page painting `/Im0` twice, a form `/Fm0` painting `/Im0` from its own resources, an inline image and a name `/Nope` that does not resolve reported the operators in that order, with `before` and `after` balanced around each `Do`, and pypdf logged a warning for `/Nope` and raised nothing. A resource dictionary shared by every page, which some producers write, would put every image on every page if the dictionary were read in place of the paints.

### 21. A PDF placeholder carries an empty alt text.

The line is `![](embedded:n)`, the form `Builder.image` writes for a picture with no alt text (`markdown.py:272`). Reason: a PDF's alternate text lives in its structure tree, joined to a paint through marked-content identifiers, and only tagged PDFs have one; a resource name such as `Im0` is a producer's label, not the document's words. Precedent: none on record; it is choice 4.

### 22. PDF placeholders count against `embedded_count`, are structure and not text, and form nesting is not measured against `embedded_depth`.

After a page's text, the renderer writes one `Builder.image("", n)` per paint, and once the document's placeholder count reaches `limits.embedded_count` it calls `drop_embedded()` once and writes no more; the rendering is then `partial` with the detail `embedded objects past <count> dropped` (`markdown.py:310-312`). Stated consequence: a PDF that paints more than 1,000 images at the default limit (`seam.py:59`), such as a scan of more than 1,000 pages with a text layer, becomes `partial` where it was `ok`, with its text whole, and a `read` of it carries the info note every cut rendering carries (`reads.py:960-962`). A PDF whose pages paint images and hold no text is still `empty`, because a placeholder is not the document's text. `embedded_depth` bounds containers a renderer itself follows; here pypdf follows the forms under its own cap. Precedent: the source, section 7 (`embedded_count` is non-throwing and sets `partial`).

### 23. `PdfRenderer.revision` rises to 2, so the next `rebuild` renders every PDF again.

Reason: the output changes for any PDF that paints an image, and a generation is per renderer, not per file; a stamp must name the renderer that made the text, or an old rendering without placeholders is taken as current. Precedent: the xlsx revision bump, pinned by `tests/rendering/test_renderers.py::TestXlsx::test_the_revision_marks_the_changed_output`.

## Cost

- **Statements added: none.** The render stage's dirty selection, twin probe, blob read and guarded stamp are unchanged. Every membership list in them is cut by `membership_budget` through `chunked` (`render.py:211`, `:227`, `:267`, `:380`), and the content insert is paged by `byte_chunked` under `BLOB_PAGE_BYTES`, 8 MiB (`render.py:388`, `dialects.py:81`). An image's blob is read by the stage today already, since every row of a cut that borrowed no rendering has its blob read whatever its type (`maintenance.py:462-465`). Postgres's 32-bit `integer` is the one engine floor this unit meets, and decision 10 bounds it.
- **Per file write: nothing.** The write path is untouched; a write clears the dimensions as it clears every render stamp today. Where unit 159-1 has landed, the header parse of an image in a write within that unit's budget (at most 16 bytes entries totalling one blob page, under one 5-second deadline, its decisions 3 and 4) runs before the write's transaction and not in the pass. The budget, the deadline and the landing's statements are that unit's, and this unit adds none to them.
- **Per index visit, rows added.** Only a new or changed image is dirty (the skip law), so this rides the write rate, about 1,050,000 a day, not the 11,000,000 index visits. The share of images is an assumption: at one write in twenty, about 52,500 header parses a day, each bounded by its body's bytes and decoding no pixel. Each adds one content row of at most nine lines where there was none, one chunk with its postings, and one embedding where a provider is configured. At one file in twenty the 10,000,000-file corpus gains about 500,000 chunks on its 100,000,000, half of one percent.
- **The PDF walk, per PDF render.** Two Python calls per content-stream operator inside the loop pypdf already runs, each one comparison unless the operator is `Do` or an inline image; no new parse and no decode. The stack is as deep as the forms pypdf follows. The placeholder loop calls `Builder.image` at most `embedded_count` times per rendering, about 20 characters each, at most about 20 KB of the 2 MiB `chars` budget (`seam.py:51`).
- **Per corpus, once.** The first `rebuild` after the upgrade renders every image stamped `unsupported` (decision 17) and every PDF again (decision 23). It runs where a whole-corpus operation is admitted: inside the daily rebuild, in keyset pages of `RENDER_PAGE_ROWS` (256, `render.py:67`) cut by `BLOB_PAGE_BYTES`, each landing one short write, the lease checked before each, and resumable, since a stamped row is not selected again. At one file in ten being a PDF or an image (an assumption), that is 1,000,000 renders in at least 3,907 pages, beside the 10,000,000 visits the rebuild makes every day. Twins borrow and are not rendered.
- **Memory per image render.** The body is in flight already, bounded by the stage's cut. The opener holds the header's fields and the EXIF block, which is part of the body. The WebP opener reads the whole body into one bytes object for its demuxer (Pillow 12.3.0 `WebPImagePlugin.py:47`, `:54`), one further copy, so the peak is about twice the largest single body. A WebP header whose canvas declares 16,383 by 16,383 opened with the process's peak resident memory unchanged at 41,756 KiB (EXECUTED, scratch probe, Linux). Renders run one cut at a time on the offload pool with no transaction open (`maintenance.py:466-468`).
- **Locks and readers.** Nothing here takes a lock or opens a transaction. A read never waits on a render: the stage renders outside any transaction and lands in one short guarded write, as today.

## Left as it is

- The render stage, the dirty predicate and the landing: an image renders through them as every format does.
- `documentation/reference/python-api/rendering.md`: its lead sentence names "a PDF or a spreadsheet" as examples and stays true; the page's body is the `vfs.rendering` docstrings, which change.
- The `pdf` extra's floor, `pypdf>=5.0` (`pyproject.toml:57`): the visitors and `get_inherited` exist at 5.0.0 by the reading under Not checked.

## Tests

Each test is written and seen failing before the code that passes it. Counts and states, never clocks. The fixture builders go in `tests/support/documents.py`: `image_bytes(format, size, exif=None)`, built with Pillow as each builder there uses its own library; `png_header_bytes(width, height, chunks=())`, hand-built like the existing `png_bytes` (`documents.py:29-41`), for headers no encoder writes; and `painted_pdf_bytes(pages)`, built with `pypdf.PdfWriter` like `pdf_bytes`, where each page states its text, its paints, its forms and its resource dictionary, inherited from the page tree where asked. A count of decodes spies `PIL.ImageFile.ImageFile.load` with `monkeypatch` and counts its calls.

The types and the extra:

- `tests/models/test_media.py::test_the_image_types_are_exactly_the_ones_magic_proves`: `IMAGE_TYPES` equals the set of image types `sniff_mime` answers across its signatures, in decision 1's order.
- `tests/rendering/test_registry.py::TestExtras::test_every_bundled_renderer_names_a_declared_extra_inside_the_umbrella`: each bundled renderer's `extra` is a key of `[project.optional-dependencies]`, read with `tomllib` as `tests/lint/test_code_shape.py:580` reads it, and is named inside `documents`.
- `tests/rendering/test_registry.py::TestResolution::test_the_bundled_set_claims_the_five_image_types`: each of the five resolves to the renderer named `image`, whose generation begins `image/1+pillow-`.
- `tests/rendering/test_registry.py::TestClassifiedStates::test_a_missing_images_extra_is_unavailable_and_names_it`: an `ImageRenderer` whose `load` answers `None` has the generation `image/unavailable` and renders `unavailable` with no text and the detail `the image renderer needs vfs[images]`.
- `tests/rendering/test_registry.py::TestResolution::test_generations_cover_every_renderer_and_the_unsupported_mark` is amended to resolve an image type beside the four; `test_the_bundled_set_claims_the_four_plain_types` holds unedited.

The image renderer, in a new file `tests/rendering/test_image.py`, beside the per-format files `test_docx_bounds.py` and `test_xlsx_bounds.py`, class `TestImage`:

- `test_an_image_without_tags_is_ok_with_three_lines`: a 3 by 2 PNG renders `ok` with exactly `format: PNG`, `dimensions: 3x2`, `orientation: landscape`, an empty unit table, width 3 and height 2.
- `test_each_image_type_renders_its_format_and_dimensions`: five parametrized cases, one per type.
- `test_a_jpeg_with_tags_renders_every_line_in_order`: a JPEG carrying all six tag groups renders the nine lines in decision 6's order, each in the form of decisions 7 and 8.
- `test_a_camera_model_that_repeats_the_make_is_written_once`: make `Acme`, model `ACME Cam 1` renders `camera: ACME Cam 1`.
- `test_a_turned_image_changes_the_orientation_word_and_not_the_dimensions`: 40 by 30 with orientation 6 renders `orientation: portrait`, `dimensions: 40x30`, width 40 and height 30.
- `test_no_render_decodes_a_pixel`: each of the five types, once with tags and once without, calls `ImageFile.load` zero times.
- `test_a_trailing_png_exif_chunk_is_not_read_and_not_decoded`: a PNG whose `eXIf` chunk follows its `IDAT` renders its three lines, no tag line, and zero `load` calls.
- `test_a_header_past_pillows_pixel_guard_renders`: a PNG header declaring 20,000 by 20,000 renders `ok` with width and height 20,000.
- `test_a_dimension_past_the_columns_range_is_printed_and_not_carried`: a width of 2,147,483,648 renders `dimensions: 2147483648x1` with width and height `None`.
- `test_a_body_its_opener_refuses_is_corrupt`: a PNG signature followed by no valid header renders `corrupt`, no text, a detail beginning `image: `.
- `test_an_unreadable_tag_omits_its_own_line`: a JPEG whose position has a zero denominator and whose title is not UTF-16-LE renders `ok` with no `gps` line, no `title` line, and every other line it carries.
- `test_a_description_is_one_line`: a description holding line breaks renders as one `description` line.
- `test_a_description_past_the_budget_is_cut_and_keeps_the_dimensions`: under a `chars` smaller than the description, the rendering is `truncated`, keeps the lines before it, and keeps width and height.

The PDF walk, in `tests/rendering/test_renderers.py::TestPdf` (its module docstring's "four" becomes "five"):

- `test_painted_images_are_placeholders_after_their_pages_text`: page 1 paints one image twice and one inline image, page 2 one image; the text carries `![](embedded:1)` to `![](embedded:3)` after page 1's text and `![](embedded:4)` after page 2's.
- `test_an_image_inside_a_form_is_resolved_in_the_forms_resources`: under a name the page's dictionary gives to another object, the form's image counts once.
- `test_a_listed_image_never_painted_gets_no_placeholder`: an inherited dictionary listing an image, and no paint, renders no placeholder.
- `test_placeholders_past_the_embedded_count_make_it_partial`: with `embedded_count=2`, a page with text painting 500 images renders two placeholders, is `partial` with `embedded objects past 2 dropped`, and calls `Builder.image` exactly twice.
- `test_a_document_of_images_alone_is_still_empty`: pages that paint and hold no text render `empty` with no text.
- `test_a_name_that_does_not_resolve_never_fails_the_page`: a `Do` of a missing name renders the page's text, no placeholder, `ok`.
- `test_the_page_is_extracted_once_and_no_image_is_decoded`: a three-page PDF calls `extract_text` three times and reads `page.images` zero times.
- `test_the_revision_marks_the_changed_output`: `PdfRenderer.revision == 2` and its version begins `2+pypdf-`.
- `test_one_page_block_per_page_with_empty_pages_visible` passes unedited: a PDF that paints nothing renders as before.

The storage, in `tests/storage/database/test_render.py`, a new class `TestImages` on SQLite as the file's other classes are, every storage built by the file's `_mount` helper (`test_render.py:48`). Decision 21 of unit 159-1 gives that helper `render_at_write=False`, because the file pins the pass, so each row below is `pending` after its write whichever unit lands first:

- `test_rebuild_stores_the_header_and_the_dimensions`: after a PNG and a tagged JPEG are written and `rebuild` runs, each row is `ok` with a generation beginning `image/`, its `media_width` and `media_height`, one content row holding its header and one chunk; the report counts `rendered` 2; a grep for the JPEG's camera returns its path alone.
- `test_an_old_image_waits_for_rebuild_and_not_refresh`: an image stamped `unsupported` under `RendererRegistry()` stays `unsupported` through `refresh` and is rendered by the next `rebuild` under the bundled registry, the report counting `rendered` 1.
- `test_a_twin_image_borrows_the_header_and_the_dimensions`: a second entry with the same bytes is stamped with the report counting `cached` 1 and `rendered` 0, and holds the same width and height.
- `test_a_same_bytes_overwrite_keeps_the_dimensions`: writing the same bytes again answers `unchanged`, and the row keeps `ok` and both dimensions.
- `test_an_overwrite_clears_the_stored_dimensions`: different image bytes leave the row `pending` with both dimensions null; text leaves both dimensions and `render_status` null.
- `test_an_image_lands_with_the_statements_of_any_rendering`: a `rebuild` over one image issues the same statements on `vfs_content`, counted by `_content_writes`, as a `rebuild` over one one-page PDF.

On both engines, the Postgres leg included:

- `tests/support/storage_contract.py::StorageContract::test_rebuild_renders_an_image_header_and_grep_hits_it`, beside `test_rebuild_renders_binaries_and_grep_hits_inside_them`: a 3 by 2 PNG written as bytes is `pending` and unseen by grep before the pass; after it, `stat` shows `ok`, `read` returns its header, and a grep for `dimensions: 3x2` returns its path alone. Where unit 179-1 has landed first, each conformance row named here is a method of the mixin that unit's decision 18 names for it, under the same name and node id, no leg's class line is edited, and `tests/fixtures/conformance/rows.txt` is not edited (its decision 16): this row is a method of `QueryGrepRows`. A conformance row runs the default a caller gets, so where unit 159-1 has landed the PNG is written through that unit's helper `_past_the_render_budget(entries)`, as its test 37 writes the neighbouring row, and the row still starts `pending`. It runs on the three legs, `TestMemoryConformance` (the slow tier), `TestSqliteConformance` and `TestPostgresConformance`: the memory leg is an `SQLiteStorage` (`src/vfs/storage/backends/memory.py:40`) and exposes `rebuild` (EXECUTED 2026-11-25, scratch probe: `isinstance(InMemoryStorage(), SupportsRebuild)` is true, and its `rebuild` stamped a 3 by 2 PNG `unsupported` with the report counting `unsupported` 1).
- `tests/storage/test_conformance.py::test_image_dimensions_are_stored_on_sqlite` and `::test_image_dimensions_are_stored_on_postgres` (marked `postgres`), one shared body in the form of `_a_directory_is_never_awaiting_the_index` (`tests/storage/test_conformance.py:459-494`): the row of a rebuilt 3 by 2 PNG holds `media_width` 3 and `media_height` 2 as integers. It holds in either order with unit 159-1, whose landing at write is the same guarded stamp.

No rights rule changes, so no leak test is added: the rendering is read under the same row gate as every content row.

Gates: `scripts/ci.sh` (the branch touches `src/`, `tests/` and `pyproject.toml`), `scripts/docs.sh check` (docstrings under `src/vfs/` change), and the Postgres leg through the `Dialect tests` workflow (`.github/workflows/test-dialects.yml`) or the `db_test` skill. `cargo test -p vfs-core` is untouched. The 100% coverage gate is met by the tests named: every branch of `image.py` and of `_Paints` is reached.

## Scope

In: decisions 1 to 23. Files: `pyproject.toml`, `uv.lock` (from `uv lock`, which adds the extra and no distribution), `src/vfs/models/media.py`, `src/vfs/rendering/image.py` (new), `src/vfs/rendering/pdf.py`, `src/vfs/rendering/registry.py`, `src/vfs/rendering/__init__.py`, `tests/support/documents.py`, `tests/models/test_media.py`, `tests/rendering/test_registry.py`, `tests/rendering/test_image.py` (new), `tests/rendering/test_renderers.py`, `tests/storage/database/test_render.py`, `tests/support/storage_contract.py`, `tests/storage/test_conformance.py`. Where unit 152-4 has landed first, also the three files its decision 13 sends this unit to: `documentation/how-to/store-and-search-documents.md`, `documentation/explanation/how-a-document-becomes-searchable-text.md` and `documentation/reference/glossary.md`.

Out:

- A describer, captions, OCR, an image-vector space, thumbnails: not built (decision 5).
- The two dimensions as fields of an observation on `stat` or `ls`: an additive public name for the unit that first has a consumer; the wire form of an image belongs to [the wire adapter unit, 171-1](../2026-11-25-the-wire-adapter-projects-a-result-to-mcp-blocks-within-budget/spec.md).
- Titles and keywords from IPTC, XMP or PNG text chunks; a PNG `eXIf` chunk after the pixel data; a frame count for an animated image; image types the sniffer does not prove: a later revision of the renderer.
- A PDF image's alternate text from the structure tree; images in annotation appearance streams; an embedded image extracted as its own entry; OCR of an embedded image: later work on the PDF renderer.
- Rendering at write: [unit 159-1](../2026-11-25-a-small-binary-write-renders-its-own-bytes-before-it-returns/spec.md).
- A count of unrendered bytes rows on a `search` result: [unit 152-2](../2026-11-25-search-says-how-many-bytes-rows-it-could-not-read/spec.md).
- The how-to, the explanation page and the glossary entries for renderings: [unit 152-4](../2026-11-25-binary-bodies-are-documented-on-the-docs-site/spec.md). Where that unit has landed first, this unit edits only the places its decision 13 names.
- Reading only the leading bytes of an image: the stage reads whole bodies. The engine's cut of a `data` slice belongs to [unit 178-1](../2026-11-25-the-engine-cuts-a-byte-slice-of-a-body-on-every-tuned-dialect/spec.md), which changes nothing public, and the `range` argument of `read` to [unit 178-2](../2026-11-25-read-takes-a-byte-range-and-the-row-says-which-slice-it-carries/spec.md), which rests on it. This is the named future direction, not a limit.
- A subprocess pool that can stop a native parser such as libwebp's demuxer, which the render clock cannot interrupt (`seam.py:62-63`): the fork the source names in section 7, not built.
- How a raised render limit retries what it refused: the placeholder memo of decision 14.

## What the docs must say

- `src/vfs/rendering/image.py`: a module docstring stating the header's lines and the honest profile: the parse is bounded by the body's bytes and decodes no pixel; a PNG `eXIf` chunk after the pixel data is not read; the WebP opener copies the body once; no Pillow pixel guard applies because nothing is decoded. `ImageRenderer` carries a class docstring the reference page renders.
- `src/vfs/rendering/pdf.py`: the sentence that embedded images are not placeholder-marked is replaced by decisions 19 to 22 in words.
- `src/vfs/rendering/__init__.py` and `RendererRegistry.bundled`: the bundled renderers read PDF, docx, pptx, xlsx and five image types.
- `src/vfs/models/media.py`: a one-line comment on `MAX_MEDIA_DIMENSION` giving decision 10's reason in words.
- The pages of unit 152-4, only where that unit has landed first. Its decision 13 reads "Unit 152-3 adds a row to the how-to's format table and to the explanation's list of kinds, a sentence to Unit marker, and `vfs-py[images]` to the extras line." The row is images, the extra `images`, no unit. The sentence says that the rendering of an image carries no unit marker (decision 6). The `:term:` markers its decision 14 places in the `vfs.rendering` module docstring and in `registry.py` are kept by this unit's edits to those docstrings. Where this unit lands first, that unit's pages state the five formats themselves and this bullet asks for nothing.

## Not checked

- The Postgres leg was not run. That Postgres stores 3 and 2 in `integer` columns and refuses 2,147,483,648 is its documented type range, not a run.
- pypdf 5.0.0, the `pdf` extra's floor: that it calls the visitors in the same order around `Do`, offers `get_inherited` and names the inline-image operation was read in its wheel when this spec was first drafted on 2026-11-25 and was not read again.
- That every Pillow name the renderer reads (`ExifTags.Base`, `ExifTags.IFD`, `ExifTags.GPS`, the five opener classes, the base `getexif`) behaves the same on 11.3.0 as on 12.3.0: inferred from Pillow's reference; the probes ran on 12.3.0 only.
- The WebP memory probe ran on Linux only; that libwebp's demuxer commits no canvas memory at open on macOS and Windows was not measured.
- That `uv lock` adds the extra and no distribution was not run, nor `scripts/ci.sh`, `scripts/docs.sh check` or the coverage of the new branches.
- The share of images and PDFs in the reference corpus is an assumption; no measurement names it.
- The sibling specs were read as they stood on 2026-11-25: units 159-1, 152-2, 152-4, 171-1, 178-1 and 178-2 are written, not reviewed and not built. What this spec states for the case where one of them lands first (the conformance row written through `_past_the_render_budget`, the `_mount` helper built with `render_at_write=False`, the header parse at write, the three pages of unit 152-4) is read from their text and was not run, because none of that code exists on `dev`.

## Choices to confirm

1. **Pillow as the image parser, behind `vfs[images]`.** Options: Pillow; a stdlib reader of each format's header and EXIF block written in vfs; a kernel in `crates/vfs-core`. Side taken: Pillow, because it reads all five formats, it is in the lock already through python-pptx, and every bundled renderer stands on its format's own library. It is the cheaper to reverse before release: the extra, one module and its tests come out together, and the other two options change no public name but `extra`.
2. **Where a title and keywords are read.** Options: the XP tags alone; the XP tags with IPTC; with XMP; all of those with PNG text chunks. Side taken: the XP tags alone, the smallest reading of the source's "readable EXIF subset". Any wider carrier is additive: a revision bump re-renders every image on the next `rebuild`.
3. **What the columns state.** Options: the stored dimensions in the columns with the rotation in the `orientation` word; the displayed dimensions in the columns. Side taken: stored, the nearer to what the row already says of a bytes entry, whose hash and size describe the bytes. Either is reversed by a revision bump that re-stamps every image.
4. **A PDF placeholder's alt text.** Options: empty; the XObject's resource name; the structure tree's `/Alt`. Side taken: empty, the form the Builder writes for a picture with no alt text. Reading the structure tree later is additive behind a revision bump.

## One line

A bundled Pillow renderer behind a new `images` extra turns a PNG, JPEG, GIF, TIFF or WebP body into a greppable header and its stored width and height without decoding a pixel, and the PDF renderer writes the placeholder line docx and pptx already write for each image a page paints.
