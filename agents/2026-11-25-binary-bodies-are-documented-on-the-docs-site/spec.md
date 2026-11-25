# The docs site explains how to store and search documents, what a rendering and a render status are, and the unit-marker grammar, with glossary entries for source, rendering, unit marker and render status

A draft, written on 2026-11-25. It is not reviewed, and nothing is built. Every claim about the tree is checked against `dev` at `27f3d24d`; a claim marked EXECUTED was run on 2026-11-25 against the synced package, in scratch scripts outside the repository. It serves stories X3 and X4 of [the roadmap](../../context/standards/roadmap.md) at gate f (`roadmap.md:938`, `:951`), whose criteria name paths under the retired `docs/` tree, so the tests below are this unit's own criteria. It is unit 152-4 of [the conversion map](../2026-11-25-the-backlog-converted/units.md), converted from slice D and the acceptance line "Docs" of [the archived binary bodies spec](../../context/specifications/archive/152-binary-bodies-and-text-renderings/spec.md) (lines 143 and 153), as sorted by [the study of that source](../2026-11-25-the-backlog-converted/studies/051-162/152-binary-bodies-and-text-renderings.md) and [the reassessment against dev](../2026-11-25-the-backlog-converted/reassessment/bodies-and-mounts.md), section 152-4. It rests on slices A and B of the source, which are built, and on [the documentation rules](../../documentation/maintainers/how-we-document.md). It waits on nothing that is not built.

## The outcome wanted

A developer or an ETL pipeline that holds PDFs, Word, PowerPoint and Excel files finds a how-to on the docs site that takes them from a folder to a `grep` hit inside a PDF: install the extra, write the files as bytes, see them wait as `pending`, run `rebuild`, then read, grep and search their text and get the original bytes back. A reader who wants to know why it works that way finds an explanation page that says what a rendering is, when it is made, what each of the ten render statuses means for `read`, `grep` and `search`, and how the unit-marker lines `<!-- page 3 -->`, `<!-- slide 3 -->` and `<!-- sheet 2: Budget -->` are written. The glossary defines Render status, Rendering, Source and Unit marker, each with its type, and the reference pages show the docstrings that mark them. It is seen when `scripts/docs.sh check` passes and the real export lists seventeen terms.

## Builds on

- Slices A and B of the archived spec 152, built: the bytes body and its `source` (`src/vfs/models/media.py:18`, `src/vfs/models/entry.py:107-109`), the ten render statuses (`media.py:23-46`), the renderer seam, registry and four renderers (`src/vfs/rendering/`), the unit-marker grammar (`src/vfs/rendering/markdown.py:61-70`), the render stage of `rebuild` and `refresh` and its report (`src/vfs/storage/backends/database/render.py:97-142`), and the read notes (`src/vfs/storage/backends/database/reads.py:937-972`).
- Decision 5 of [the write-preconditions work](../2026-11-20-write-takes-preconditions-and-an-append/spec.md), built: "A staged update of a live row whose final material equals the committed material is dropped from the plan", so writing the same document again answers `unchanged` and renders nothing.
- [The documentation rules](../../documentation/maintainers/how-we-document.md) and [the docstring rules](../../documentation/maintainers/how-we-write-docstrings.md): the glossary's two files and six parts, the 25-word summary, the `:term:` marker, and what `scripts/docs.sh check` refuses. They stand in for stories X3 and X4, which named no page layout that exists.
- [The listing-pages docs draft](../2026-11-21-the-docs-say-how-a-listing-pages/spec.md), the precedent for a unit that adds glossary terms and pages and no code.
- Units of this conversion that change what these pages say, none a dependency, build order any. [Unit 152-3](../2026-11-25-an-image-written-as-bytes-renders-a-metadata-header/spec.md), drafted and not built, adds a fifth renderer behind `vfs[images]` (its decisions 1 and 2; its decision 4 is the umbrella of the documents) and states that this unit "names five formats if this lands first". [Unit 159-1](../2026-11-25-a-small-binary-write-renders-its-own-bytes-before-it-returns/spec.md), drafted and not built, renders a small write before it returns. [Unit 152-2](../2026-11-25-search-says-how-many-bytes-rows-it-could-not-read/spec.md), drafted and not built, adds a search warning for pending rows. [Unit 167-2](../2026-11-25-a-bytes-row-renders-a-placeholder-and-leaves-the-payload-only-when-asked/spec.md), drafted and not built, prints a `[binary ...]` line before a bytes row's text. Whichever lands second edits the paragraph decision 13 names.

## Terms

- **The how-to**: the new page `documentation/how-to/store-and-search-documents.md`.
- **The explanation**: the new page `documentation/explanation/how-a-document-becomes-searchable-text.md`.
- **The four terms**: the glossary terms Render status, Rendering, Source and Unit marker.

## What the code does today

- A bytes write is pending until an index pass. A PDF written with `data=` stats as `render_status` `pending`, `read` answers the warning "the binary awaits a rendering; run rebuild" and no text, and `grep` and `search` find nothing in it; after `await storage.rebuild()` the result's `rendering` extra is `{'rendered': 1, 'empty': 0, 'unsupported': 0, 'failed': 0, 'cached': 0, 'unrendered': 0}`, `read` returns the text under `<!-- page 1 -->`, `grep` reports `/docs/q.pdf:2:The quokka smiles`, and `search` ranks it (EXECUTED, `InMemoryStorage` under `AsyncVirtualFileSystem`). A text file is found by `grep` and `search` before any pass (EXECUTED).
- The index passes are methods of the storage, not of the kernel. `rebuild` and `refresh` are declared on the storage protocol (`src/vfs/storage/protocol.py:561-563`) and served by `DatabaseStorage` (`backend.py:1147-1153`); neither `AsyncVirtualFileSystem` nor the synchronous `VirtualFileSystem` has either verb (EXECUTED, grep of `src/vfs/base.py` and `src/vfs/sync.py`). The `write` docstring already says "The text of a bytes body is rendered later, by ``rebuild``" (`src/vfs/base.py:944`).
- `refresh` before the first `rebuild` refuses `unavailable` with "no index is published yet; run rebuild" (`src/vfs/storage/backends/database/indexing.py:493`; EXECUTED). A second index run while one holds the lease is refused `conflict`, retryable, "an index run is already running ... retry after it finishes" (`maintenance.py:203-204`). A new renderer generation is the next `rebuild`'s work, not a `refresh`'s (`maintenance.py:152-166`).
- `read` leaves `data` out unless `columns` names it, and then returns the bytes written, byte for byte (EXECUTED). `stat` and `ls` carry `render_status` and `source` on each observation (EXECUTED), and their printed text shows neither, even with `columns` naming `render_status` (EXECUTED).
- `edit` of a bytes file is refused `wrong_kind` with "binary body; replace the bytes through write" (`src/vfs/storage/backends/database/writes.py:1169-1171`; EXECUTED), where the source spec said `unsupported`. The `edit` and `read` docstrings say nothing of bytes (`base.py:810-818`, `:1036-1047`).
- A file with no renderer is `unsupported` after a pass, and `read` answers "no text rendering (unsupported)" (EXECUTED). An absent extra stamps `unavailable`, and the reason that names the extra, "the pdf renderer needs vfs[pdf]" (`src/vfs/rendering/registry.py:104-105`), is stored in `render_detail`, which no verb returns (EXECUTED, grep of `src/vfs` for `render_detail`).
- The extras are `pdf`, `docx`, `pptx`, `xlsx` and `documents = ["vfs-py[pdf,docx,pptx,xlsx]"]` (`pyproject.toml:57-63`). docx carries no unit markers; pdf writes `page`, pptx `slide`, and xlsx `sheet` with the sheet's title as its label (`pdf.py:45`, `pptx.py:54`, `xlsx.py:122`, `docx.py:79`).
- The glossary holds thirteen terms and none of the four (`documentation/reference/glossary.md:16-170`). Its order is checked case-folded (`scripts/docs_export.py:283-306`), so "Render status" sorts before "Rendering".
- `tests/scripts/test_docs_export.py:864-870` asserts the real glossary is `["Arm", "Entry", "Kernel", "Mount", "Storage"]` and that Entry's related terms are `["Arm", "Mount", "Storage"]`. The export of the real tree returns thirteen terms, and Entry's related terms are `["Arm", "Mount", "Storage", "Vid"]` (EXECUTED, `docs_export.export` over `documentation/`), so the test as written cannot pass on `dev` (INFERRED; the test was not run).
- No test runs the fences of `documentation/`. Sybil runs `README.md` and the retired `docs/` tree only (`conftest.py:39-45`). The pages are held by the docs gate and by `tests/scripts/test_docs_site.py:70-80`, which refuses a code line wider than 64 characters outside a `text` block.
- The word "source" has two other public senses, an edge's end (`src/vfs/models/edge.py:37`, `mkedge(source=...)` at `base.py:1180`) and `ResultError.source`; the word "rendering" has one, printing a `Result` as text (the docstrings of `Match` and `Result.__str__`) (EXECUTED, a scan of the export's public docstrings).

## The problem

Bytes bodies have been built since slices A and B and are documented only in docstrings. No page outside the API reference mentions `data=`, a rendering or `rebuild` (EXECUTED, grep of `documentation/`), so a reader who writes a PDF meets `pending`, a warning and an empty `grep`, with no page that says an index pass is the next step. The one loading how-to tells a reader to skip a file that is not valid text (`documentation/how-to/load-a-folder-of-files.md`, Step 3). At the reference deployment the text share of 10,000,000 files is high by count and low by bytes, an assumption the table marks as one, so much of the 3 to 7 TB of bodies is not text and documents of these four kinds are a part of it; a pipeline that does not know `refresh` either leaves them unsearchable or runs `rebuild` after every batch, a 10,000,000-file visit for each of 100 nightly batches. The glossary cannot be linked for the words the docstrings already use, so the reference shows "rendering" as plain prose with no definition.

## Decisions

### 1. Two new pages, four glossary terms, a bounded set of docstring markers, and two docstring sentences; no code changes behaviour.

The pages are written under a person's guidance, as `documentation/maintainers/how-we-work.md:86` requires of every page that is not generated, so the build is guided work for the pages and the glossary, and autonomous for the markers, the test and the gate. This spec decides the files, the order, the facts each page states and the exact glossary summaries; the prose is the guided session's. Precedent: the listing-pages docs draft; the roadmap's X3 state line (`roadmap.md:940`).

### 2. The how-to is `documentation/how-to/store-and-search-documents.md`, titled "Store and Search Documents", listed second under How-to Guides, after `/how-to/load-a-folder-of-files`.

Reason: the source names a how-to "store and search documents" (`spec.md:143`), and a reader arrives from the loading how-to, which it extends to bytes. The How-to directory then holds five pages, under the sixteen-child limit (`how-we-work.md:87`). The navigation entry is a bare route string, as its neighbours are (`documentation/navigation.json:37`).

### 3. The how-to runs on `AsyncVirtualFileSystem` over an `InMemoryStorage` held in its own variable, with `await` at the top level.

Reason: the index passes are coroutines on the storage and neither face has them, so the only supported way to render is `await storage.rebuild()` on the loop the storage runs on. The synchronous face runs its own loop thread, and awaiting its storage from another loop is not a contract the tree states or tests. A sentence says the steps are the same on `SQLiteStorage` and `PostgresStorage`, linking the tutorial that keeps files in a database. Precedent: `documentation/how-to/rewind-a-conversation-and-put-its-files-back.md` uses `await`.

### 4. The how-to's steps, in order, and what each shows.

"Before You Begin": Python 3.11 or later, `pip install "vfs-py[documents]"`, and a table of the four formats with the extra each needs and the unit it marks (PDF `pdf` page, Word `docx` none, PowerPoint `pptx` slide, Excel `xlsx` sheet), and the file system set up. Step 1, write a folder's documents as bytes in one batch: one `Entry(path=..., data=file.read_bytes())` per file, `fs.write(entries, parents=True)`, and the single form `fs.write(path=..., data=...)` in one sentence. Step 2, see that they wait: `render_status` read from `result.observations`, the `read` warning, and a `grep` with no hit. Step 3, render them: `result = await storage.rebuild()` and `result.rendering`. Step 4, read, grep and search: a `read` of a PDF showing its page markers, a `grep` hit, a `search`. Step 5, get the original bytes back: `fs.read(path, columns=frozenset({"data"}))`. Variations: "Keep the Text Up to Date", which runs `refresh` after a batch once a `rebuild` has published an index, names its refusal before that, and says a `conflict` means another pass is running and is retried after it; "Write a Document Again", where the same bytes answer `unchanged` and render nothing and new bytes answer `updated` and are `pending` until the next pass; "Change a Document", where `edit` is refused `wrong_kind` and the change is a new `write`; "A File VFS Cannot Render", where `unsupported` means no renderer for the type and `unavailable` means the extra is missing, fixed by installing it and running `rebuild`, because a `refresh` does not retry a new renderer. Each fact is in "What the code does today" above. Reason: the order is the one a first reader meets the states in. Precedent: the step and variation shape of `load-a-folder-of-files.md`.

### 5. Every output block in the how-to is captured by running its steps, and none is written by hand.

The example folder is four documents built with the builders in `tests/support/documents.py` (`pdf_bytes`, `docx_bytes`, `pptx_bytes`, `xlsx_bytes`), named in the page as a folder `reports` of the reader's own files, with the sentence "your output will differ". The build runs the page's fences in a scratch script and pastes what they print. Reason: no test runs these fences (`conftest.py:39-45`), so a hand-written output would drift unseen. Precedent: `load-a-folder-of-files.md` shows the output of its own run and says the count will differ.

### 6. The how-to tells a pipeline to run `refresh` after a batch and `rebuild` once to start and then on the deployment's daily schedule, never after each write.

Reason: `refresh` costs what was written since the last pass, and `rebuild` visits every file (`protocol.py:545-551`, `maintenance.py:152-166`); the arithmetic is under Cost. Precedent: AGENTS.md's reference deployment, "Partial index pass" and "Full rebuild".

### 7. The explanation is `documentation/explanation/how-a-document-becomes-searchable-text.md`, titled "How a Document Becomes Searchable Text", listed second under Explanation.

It has six sections, in this order. Two kinds of body: a file's source is text or bytes, said once, which decides where the body is kept and whether it needs a rendering. What a rendering is: Markdown text made from the bytes, one construct a line, read by `read` and searched by `grep` and `search` in place of the bytes, never edited, and not versioned while the bytes are (`versions.py:5-9`). When it is made: in `rebuild` and `refresh`, not in `write`, so a write of 10,000 files stores them and returns without waiting on a parser; the same bytes under the same renderer are never rendered twice, two files with the same bytes are rendered once, and a new renderer version renders its type again at the next `rebuild`. Render status: the table of decision 8. Unit markers: the grammar of decision 9. Limits: one `RenderLimits` value bounds each render, a rendering cut at `rendering.RENDER_CHARS` ends with the line `<!-- truncated: N of M units -->` and is `truncated`, a time or embedded limit makes it `partial`, and a host can lower the limits; the page names the constants and the reference page, never their values. Reason: these are the questions the source's "explanation page on renderings" answers (`spec.md:143`), each stated by the code cited in Builds on. Precedent: `why-vfs-stores-files-in-a-database.md`, whose sections answer what, why and what it costs.

### 8. The status table holds the ten statuses with three columns: what happened, whether there is text, and what `read` returns.

`pending`, written and not yet rendered, no text, a retryable warning to run `rebuild`. `ok`, rendered in full, text. `truncated`, rendered up to the character budget, text, an info note. `partial`, cut by a time or embedded limit with the text so far valid, text, an info note. `empty`, parsed with no text, the empty string. `unsupported`, no renderer for the type, no text, a warning. `unavailable`, a renderer whose extra is not installed, no text, a warning. `encrypted`, `corrupt` and `failed`, the body could not be read, no text, a warning. One sentence after it: `grep` and `search` see only the statuses that have text. Reason: the table is the code's (`media.py:23-46`, `reads.py:937-972`), and `RenderStatus` is exported, so the reference holds the same list from its docstring. Precedent: the source's status table (`spec.md:73-87`), trued to dev.

### 9. The grammar is stated in five rules.

A marker is an HTML comment on a line of its own, `<!-- <kind> <number> -->`, or `<!-- <kind> <number>: <label> -->` when the unit has a name. The kinds are `page` (PDF), `slide` (PowerPoint) and `sheet` (Excel, labelled with the sheet's title and followed by a heading of the same title); a Word document has none. Units are numbered from 1, and a marker is written even for a unit with no text, so the third `page` marker opens page 3. A line of the document that would read as a marker is written with a leading backslash (`markdown.py:51`, `:329-330`), so every marker is one VFS wrote. A cut rendering ends with `<!-- truncated: N of M units -->`. Reason: each rule is the `Builder`'s (`markdown.py:61-70`, EXECUTED for the empty page). Precedent: the source, section 4 (`spec.md:45`).

### 10. Every marker on a page or in the glossary is written as code, in backticks or in a fence, never as a bare line.

Reason: a bare `<!-- ... -->` line in Markdown is an HTML comment, which a renderer drops, so the reader would see nothing where the marker stands.

### 11. The four terms are added to `glossary.md` and `glossary.json` in this order and with these summaries and types.

The order of the seventeen terms is Arm, Entry, Interrupt, Job, Kernel, Mount, Policy, Render status, Rendering, Session, Source, Stamp, Step, Storage, Turn, Unit marker, Vid.

| Term | Summary in `glossary.json` | Types |
|---|---|---|
| Render status | Where the rendering of a bytes body stands, such as waiting, made in full, cut short, empty, or refused with a reason. | `["RenderStatus"]` |
| Rendering | The Markdown text VFS makes from a bytes body, which read, grep and search use in place of the bytes. | `["rendering.Rendering"]` |
| Source | What the body of a file was written as, text or bytes, which decides where it is stored and whether it is rendered. | `["Source"]` |
| Unit marker | A comment line that marks where one page, slide or sheet begins in a rendering, numbered from 1. | `[]` |

The summaries hold 22, 20, 23 and 18 words, with no colon and no link. All four names and types pass the export, and Entry's related terms become `["Arm", "Mount", "Render status", "Source", "Storage", "Vid"]` (EXECUTED, the export over a scratch copy of `documentation/` holding the four terms). Reason: each type is the exported thing (`src/vfs/__init__.py:69`, `:79`; `vfs.rendering.Rendering`), and a marker is a string with no class, as an arm is.

### 12. Each description states the facts below, links the terms named, and names the other sense of its word.

Render status: every entry whose source is bytes has one and a text entry has none; `stat` and `ls` carry it as `render_status`; the ten values in one sentence with a link to the explanation's table; a settled status is tried again only when the bytes change or the renderer changes. It links Entry, Source and Rendering. Rendering: the Markdown text made from a bytes body by the renderer for its type, at `rebuild` or `refresh`; `read` returns it as `content`; it is never edited and not versioned; a rendering of a paged document is divided by unit markers. It links Source, Render status and Unit marker, and says that printing a `Result` as text is also called rendering in the code and is not this term. Source: text or bytes, fixed by whether `content` or `data` was written; a bytes file's text is its rendering; a write of the other kind changes the source. It links Entry and Rendering, and says that the `source` of an edge is the path it starts from and is not this term. Unit marker: the grammar of decision 9 in two sentences and one example in a fence; it links Rendering. Reason: the Job term names the shell job it is not (`glossary.md:61`), which is the precedent for a word the code uses twice; renaming the edge argument or the result printer is a code change outside this unit (choice 1).

### 13. A sibling unit that lands after this one edits the one place its change touches.

Unit 152-3 adds a row to the how-to's format table and to the explanation's list of kinds, a sentence to the Unit marker glossary term, and `vfs-py[images]` to the extras line. Unit 159-1 changes the how-to's Step 2 and the explanation's "When it is made". Unit 152-2 adds the search warning to Step 2 and to the `pending` row. Unit 167-2 re-captures the how-to's read outputs. If any lands before this unit, this unit states its behaviour instead. Reason: the pages describe the tree they are built on, and each change has one home on them.

### 14. Markers go at the first use in these docstrings, and in no others in this unit.

`vfs.rendering`'s module docstring (`src/vfs/rendering/__init__.py:1`), `:term:`rendering``. `RenderStatus` (`media.py:35`), `:term:`rendering``. `Source` (`media.py:19`), `:term:`source``. `rendering.Unit` (`seam.py:152`), `:term:`rendering`` and `:term:`unit marker``. `rendering.unit_marker` (`markdown.py:62`), rewritten as one sentence carrying `:term:`unit marker`` and its two examples. `rendering.RenderLimits`, `rendering.RendererRegistry.generation` and the public members of `rendering.Builder`, `:term:`rendering``. `AsyncVirtualFileSystem.write` (`base.py:944`), `:term:`rendering``. The private module docstring of `vfs.models.media` (`media.py:1-11`), `:term:`source``, `:term:`rendering`` and `:term:`render status``. The docstrings of `Match` and `Result.__str__`, which use "rendering" in the printing sense, take no marker. Reason: these are the public docstrings that use the words in the glossary's sense (EXECUTED, a scan of the export), and the precedent marks public docstrings first and leaves private ones to review (`agents/2026-11-21-docstrings-and-words-follow-the-rules/spec.md`, line 7). The media module is the one private docstring marked, because it is the code's own definition of all three words.

### 15. The `read` and `edit` docstrings each gain the bytes facts.

`read` (`base.py:810-818`): a file written as bytes is read as its rendering, with a warning when it has none, and its bytes are returned only when `columns` names `data`. `edit` (`base.py:1036-1044`): a file written as bytes has no text to edit and is refused with `wrong_kind`, and its bytes are replaced through `write`. Reason: the source's slice D puts these on the API page (`spec.md:143`), and on dev the API page is the docstrings. It is choice 3.

### 16. The real-glossary test pins the seventeen terms and what the build found for the four.

Reason: the test is the one place the real export is held, and it is out of date on dev. Precedent: `tests/scripts/test_docs_export.py:864-870`.

## Cost

Nothing runs in a verb call, a write, an index visit or a lock: the change is pages, glossary entries and docstrings. The pages' guidance has a cost, decided in decision 6. A `rebuild` visits all 10,000,000 files; told to run after each of the 100 nightly batches, a pipeline would make 1,000,000,000 file visits a night where the design budgets 10,000,000 a day for the rebuild, and after each of about 1,050,000 daily single-file writes it would be about 10^13. A `refresh` after a batch visits what the batch wrote, 10,000 files, and costs per batch what the design already budgets per partial index pass. A batch on the page stays within the 10,000-file call the load how-to already shows; the pages name `BLOB_PAGE_BYTES`, `RENDER_CHARS` and `RenderLimits` by name and never restate a size, so a change to a budget does not leave a page wrong. Nothing in the change differs between SQLite and Postgres.

## Left as it is

- No index verb on the kernel or the synchronous face. The how-to works around its absence with the storage's coroutine (decision 3); a verb is a change to the kernel's surface and a story of its own.
- `render_detail` stays unreturned. A reader of `unavailable` learns from the pages which extras exist; returning the stored reason is a change to the read path.
- The hint "This mount does not support the verb; target a mount that does." that follows an `unsupported` rendering on `read` (EXECUTED) reads as a refusal of the verb. The how-to says what `unsupported` means; rewording the hint changes `ErrorKind`'s shared text, which belongs to the results module.
- No test runs the fences of `documentation/`. Making Sybil read the new tree is one change for every page, and the how-to's fences read files from the reader's disk, so this unit does not start it.
- The shell reference's row that a served `grep -r` "never matches" a bytes body (`documentation/reference/shell.md:96`) is not reconciled here; it is not checked whether it means raw bytes or the rendering too.

## Tests

Written first, and seen failing. Counts and states, never clocks. No storage changes, so no Postgres leg; no rights change, so no leak test.

- `tests/scripts/test_docs_export.py::test_the_real_glossary_exports`, rewritten: `list(real_export["glossary"])` is the seventeen terms of decision 11 in order; each summary is non-empty; the types of Render status, Rendering, Source and Unit marker are cited as `["RenderStatus"]`, `["rendering.Rendering"]`, `["Source"]` and `[]`; Entry's related terms are `["Arm", "Mount", "Render status", "Source", "Storage", "Vid"]`; the related terms of the four are `["Entry", "Rendering", "Source"]`, `["Render status", "Source", "Unit marker"]`, `["Entry", "Render status", "Rendering"]` and `["Rendering"]`; the code of each of the four holds at least one cited name, and Unit marker's holds `rendering.unit_marker`; the documentation of each of the four lists `how-to/store-and-search-documents.md` and `explanation/how-a-document-becomes-searchable-text.md`. It fails first on the seventeen terms.
- `tests/scripts/test_docs_site.py::test_no_line_of_code_in_a_page_is_wider_than_64_characters`, unchanged, holds both pages.
- `docs-app/tests/build.test.ts`, "the build writes one page per navigation entry" and "a page's head holds its description, its one address, and the pages before and after it", unchanged, hold both pages in the navigation.
- The gates: `scripts/docs.sh check`, which the branch touches through `documentation/` and docstrings under `src/vfs/`, and `scripts/ci.sh`, which it touches through `tests/` and `src/`.

## Scope

In: `documentation/how-to/store-and-search-documents.md` (new); `documentation/explanation/how-a-document-becomes-searchable-text.md` (new); `documentation/navigation.json`; `documentation/reference/glossary.md` and `glossary.json`; the docstrings of decisions 14 and 15 in `src/vfs/base.py`, `src/vfs/models/media.py`, `src/vfs/rendering/__init__.py`, `seam.py`, `markdown.py` and `registry.py`; `tests/scripts/test_docs_export.py`.

Out: the notebook how-to and the rest of the pipeline how-to of story X3, criteria 2 and 3, which this how-to serves only for binary writes and the `conflict` retry; the roadmap's X3 and X4 state lines, which the conversion's map places; the behaviour of units 152-2, 152-3, 159-1 and 167-2; an index verb on the kernel; running the fences of `documentation/`; markers in private docstrings other than `vfs.models.media`; the retired `docs/` tree.

## Not checked

- `scripts/docs.sh check` and the docs app's own tests were not run, and whether `bun` is present was not looked at. The four terms passed `docs_export.export` over a scratch copy of `documentation/`, which is the Python half of the gate only.
- `test_the_real_glossary_exports` was not run; that it fails on `dev` is inferred from the export's output against its assertion.
- How the docs app draws an HTML comment inside inline code and inside a fence; decision 10 assumes code is drawn literally.
- Every probe ran on SQLite in memory or in a file. The how-to's outputs on Postgres, and over real documents rather than the fixture builders, were not seen.
- Awaiting a synchronous face's storage from another loop worked once with `asyncio.run` on SQLite (EXECUTED); whether it holds on Postgres, or in a notebook's loop, was not tried, which is why decision 3 does not rely on it.
- The twin, generation and install-retry facts of the explanation rest on the test names in `tests/storage/database/test_render.py` (`:231`, `:247`, `:360`), read and not run.
- Whether a served `grep -r` in the shell matches a bytes file's rendering.

## Choices to confirm

1. **The four names, against the code's other senses of "source" and "rendering".** The options are to keep the names the unit and the exported types use and name the other sense in each description, or to rename the edge argument, `ResultError.source` or the result printer first. Side taken: keep the names, because the types `Source` and `RenderStatus` are already exported under them, the Job term is the precedent, and four sentences are cheap to remove if a rename lands.
2. **Where the status table and the grammar live.** The options are the explanation and the glossary, or a hand-written reference page beside `documentation/reference/access-levels.md`. Side taken: the explanation and the glossary, because the reference already shows `RenderStatus` and `unit_marker` from their docstrings and a third copy would drift; moving the table to its own page later adds a file and changes no link target in the glossary.
3. **Whether `read` and `edit` gain their bytes sentences here.** The unit's title names only the pages and the glossary; the source's slice D also names the API page. Side taken: add them, because they are docstring sentences that change no behaviour and the how-to links to them; removing them reverts two paragraphs.
4. **Whether the pages wait for the sibling units.** The options are to write them now against `dev`, or after 152-3, 159-1, 152-2 and 167-2 land. Side taken: now, because each sibling's change has one named paragraph (decision 13), and a page written now serves the readers of the code that exists.

## One line

A how-to, an explanation and four glossary terms put the built bytes bodies on the docs site: write documents as bytes, render them with `rebuild` and `refresh`, read the ten render statuses, and read the unit markers, with docstrings marked and the real-glossary test pinned to seventeen terms.
