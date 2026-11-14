# A docx note is written once and a span is clamped: the docx renderer does work in proportion to the text it writes, and consults the budget before it collects

A fix to the docx renderer (`src/vfs/rendering/docx.py`) and a small addition to the rendering Builder (`src/vfs/rendering/markdown.py`). It is not structural: no public verb, schema, rights, SQL or dialect change, so the engine legs are not needed; the docx renderer's revision rises by one, so each docx entry re-renders once on the next index pass. It answers two medium findings of the 0.1.0a1 security audit, run `vfs-run-1-2026-11-07` at commit `3586750`: `vfs.rendering.docx:note-reference-inline-expansion` and `vfs.rendering.docx:table-gridspan-expansion`, and four smaller shapes of the same class found while reading the module. No intention and no research memo: the costs are plain in the source and were counted here on small, well-formed documents. It is the second of three rendering fixes for that audit. [The container spec](2026-11-13-an-office-container-is-measured-before-it-is-opened.md) lands first; it bounds the decompressed input before any library opens it, and this spec bounds what the renderer does with that input. [The xlsx spec](2026-11-13-an-xlsx-sheet-is-read-under-the-clock-and-its-tables-stream.md) lands third and builds on the Builder as this spec leaves it. The order among the three is fixed; their place in the rest of the queue is not, so every count of existing nodes below reads as at `5d47a21a`, plus what earlier landings add. Code is cited at `5d47a21a`, whose `src/vfs/rendering/` and `tests/rendering/` equal the audited commit's (EXECUTED: `git diff --stat 35867501 5d47a21a` over both folders is empty).

## The problem

Labels: EXECUTED means a probe ran here, in the session scratchpad, on documents of a few kilobytes built with the pinned python-docx 1.2.0 (`uv.lock`); READ means read in the cited file; INFERRED means reasoning.

READ. Every limit a rendering honours (`RenderLimits`: characters, the output-to-input ratio, the unit cap, the seconds) is enforced inside the Builder, line by line, as text is appended (`markdown.py:275-289`), and the clock only at unit boundaries and between table rows. Nothing bounds the work a renderer does before it hands the Builder a string. Any place where the docx renderer's work is set by a repetition or a declared attribute of the input, and not by the text that reaches the Builder, escapes every limit. The findings name two such places; reading the module found five more of the same class, the fifth found by [the spec review](../../reviews/2026-11-13-a-docx-note-is-written-once-and-a-span-is-clamped-spec-review.md).

READ, the first finding. `_Writer._inline` (`docx.py:131-149`) builds a paragraph's whole string before `Builder.paragraph` sees it, and at every footnote or comment reference it appends a fresh copy of the whole note (`_note`, `docx.py:152-154`). Nothing limits how often one note is copied, and the budget is consulted only after the string exists. Section headers and footers take the same path. EXECUTED on a small document: the characters handed to the Builder grow with the number of references, and a paragraph the budget cannot hold is still built whole before the Builder refuses it.

READ, the second finding. `_Writer.table` (`docx.py:127-129`) builds every row of a table as `[cell.text for cell in row.cells]` before `Builder.table` sees any of it. In python-docx 1.2.0 `_Row.cells` yields one entry per grid column a cell declares it spans (`docx/table.py:396-435`), reading the declared value with no comparison to the table's grid, and the renderer reads the cell's text once per entry. EXECUTED on a small table: the cells built and the cell-text reads follow the declared span, not the grid.

READ and EXECUTED, four of those five. A vertically merged cell is resolved by python-docx walking up the column, one row at a time, for every continued cell (`_tc_above`, `docx/oxml/table.py:739-742`), so a merged column costs the square of its height, and the merged cell's text is read again in every continued row. A header or footer part named by several sections' own definitions is walked once per section that names it (`docx.py:56-58`, `66-68`). The footer loop runs after the body loop has stopped, and each paragraph is walked by `_inline` whether or not the Builder has already stopped. And `_note_texts` (`docx.py:90-101`) visits every note element at any depth and joins every text below it, so note elements nested inside one another are read once per level. Each grows with the shape of the input, not with the text written.

READ, the fifth, from the spec review. `_Writer.paragraph` reads `paragraph.style.name` for every paragraph (`docx.py:118`). With no declared style python-docx walks every style element to find the default (`docx/oxml/styles.py:292-300`), and a declared id is placed into a query over the styles part (`docx/oxml/styles.py:307`). So each lookup costs work the styles part sets, and an empty paragraph charges nothing to the budget, so no budget stop ends it. The header and footer loops read no clock. EXECUTED by the reviewer, on both trees: style elements visited grow as paragraphs times styles, in the body and in a header alike, and a declared id holding a quote mark makes the render raise the library's query error.

READ, what is already bounded. Runs, tabs, breaks, hyperlinks, simple and complex fields, tracked insertions, text boxes and picture placeholders are each visited once by `element.iter()` and add at most their own text. Deleted text, field instructions, endnotes, body-level content controls and tables nested in cells are not read at all. Picture placeholders are capped by `RenderLimits.embedded_count`. Each costs work in proportion to the input, and the container spec bounds that input.

READ and EXECUTED, pptx. `pptx.py` shares the Builder but has neither finding's shape. Its rows yield each table cell element once, whatever span it declares, and it has no note references; a slide's notes belong to that slide. Its renderer is out of this spec (Scope).

READ, reach. Rendering runs when the index pass renders pending bytes rows, on the shared offload pool of the host process, for any principal who can write a file, when the docx extra is installed, as both findings' traces record; the registry turns only a raised exception into a state (`registry.py:105-108`).

## Architecture

Dashed is what this spec adds or changes.

```mermaid
flowchart LR
  classDef planned stroke-dasharray: 6 4,stroke-width:2px;
  REG["registry.py RendererRegistry.render<br/>unchanged"]
  RENDER["docx.py DocxRenderer.render<br/>revision + 1"]
  NOTES["_note_texts<br/>direct children of the notes root only"]
  PARTS["_Writer.parts<br/>each header or footer part once, the clock before each paragraph"]
  PARA["_Writer.paragraph<br/>returns at once when the Builder stopped"]
  STYLES["_Styles<br/>one pass over the styles part, a lookup per paragraph"]
  INLINE["_Writer._inline<br/>stops once kept text passes remaining"]
  ONCE["_Writer._note<br/>full at the first reference, marker after"]
  LAYOUT["_layout<br/>span clamped to the grid, merges resolved by offset"]
  SOURCE["_Source<br/>one cell's flattened text, read once"]
  ROWS["_Writer._rows<br/>rows drawn lazily, a row stops past remaining"]
  KEPT["markdown.py kept_length"]
  REM["Builder.remaining"]
  TABLE["Builder.table(rows, width=)<br/>draws rows one at a time"]
  REG --> RENDER
  RENDER -.-> NOTES
  RENDER -.-> PARTS -.-> PARA
  RENDER --> PARA -.-> INLINE -.-> ONCE
  RENDER -.-> LAYOUT -.-> SOURCE
  LAYOUT -.-> ROWS -.-> TABLE
  INLINE -.-> KEPT
  INLINE -.-> REM
  ROWS -.-> KEPT
  ROWS -.-> REM
  PARA -.-> STYLES
  class NOTES,PARTS,PARA,STYLES,INLINE,ONCE,LAYOUT,SOURCE,ROWS,KEPT,REM,TABLE,RENDER planned
```

Page this changes: none; the architecture folder was retired on 2026-10-31, and the landing notes will say so in one line.

Terms. A character is **kept** when no line rule of the Builder can drop it: anything but whitespace (as `str.isspace` defines it) and NUL. **Remaining** is the number of characters the character budget still admits. A cell's **source** is the cell element that holds its text: itself, or for a vertical continuation the cell it continues.

## Decisions

### 1. A note's text is written in full at its first reference in the rendering, and every later reference to the same note is its bare marker, ` [footnote 7]` or ` [comment 0]`

A renderer does work in proportion to the text it emits, and a note referenced again adds no new text. The bare marker is the form a note with no text already takes (`docx.py:154`), so the grammar gains nothing, and the id ties the marker to the full text above it. Word writes one reference per footnote and per comment, so an ordinary document renders exactly as today; only a document that repeats a reference changes, and only after the first one.

### 2. `_Writer._inline` reads `Builder.remaining` once and stops collecting a paragraph as soon as the kept characters it holds exceed it

Every kept character costs one character of budget on whatever line it lands, so a paragraph holding more kept characters than remain cannot fit, and the Builder will cut it. The cut lands on the same line it lands on today: the lines before the stopping piece are today's lines, and the line holding it costs at least as much as today's longer line, so both are refused. Counting every character instead would stop early on whitespace the Builder drops, and a paragraph that fits would lose its tail with no cut recorded. The overshoot is one piece: one text run's own text, or one note's text, once.

### 3. `_Writer.paragraph` returns at once when the Builder has stopped

The footer loop, and the paragraphs after a cut inside a header, still reach the writer once the Builder has stopped. Nothing they collect can be written, so collecting it is work no text pays for.

### 4. Each header or footer part is written once, at the first section whose own definition names it, keyed by the part object

A part named again holds no new text. Python-docx loads one part object per part name, so the object identifies the part however many relationships reach it, and a set of them costs one lookup per section. Python-docx's own `add_section` writes no reference for a later section (EXECUTED: one reference, then none), and Word links such sections the same way (INFERRED from python-docx's linked-header model, which the suite's `test_a_linked_header_is_written_once` pins), so an ordinary document renders as today.

### 5. `_note_texts` reads only the direct children of the notes part's root

The schema puts every footnote and comment directly under its part's root, so an ordinary document reads the same notes. A note element nested in another is read as part of the note that holds it, and each text element is then read once.

### 6. The table writer walks the parsed table's own elements and never `_Row.cells` or `_Cell.text`: its rows from `tbl.tr_lst`, its cells from `tr.tc_lst`, its grid from the `w:gridCol` children of `w:tblGrid`, and a cell's text as `"\n".join(p.text for p in tc.p_lst)`

That is the text `_Cell.text` returns, read from the element python-docx already parsed, so no class of the optional library is named. The renderer reaches python-docx only through `self.library`, and a fix that named a library class the writer was never handed has failed before on exactly that. The writer already reads `paragraph._p` the same way. It also reads `table._tbl`, `tr.grid_before`, `tc.grid_span` and `tc.vMerge`, python-docx's parsed-element properties at 1.2.0 (`docx/oxml/table.py:72`, `:473`, `:542`), and decision 15's style table stands on `styles.element._iter_styles()`, `style.styleId`, the raw `w:val` of the style's `w:name` child, read as decision 15 reads the type and the default, because python-docx's `name_val` raises on a `w:name` with no value and the pass reads every style, and `paragraph._p.style` in the same way, and finds the grid with `tbl.find` so that a table with no `w:tblGrid` reads as no grid rather than raising. A change to any of these in a later python-docx raises inside `render`, which the registry stamps `failed` for every docx entry; the pinned lock and this suite meet it before an upgrade lands.

### 7. A cell's declared span is read as at least one, and adds copies only while its row has fewer cells than the grid has columns; every cell element keeps one cell

A span cannot make more cells than the table has columns, and every cell the input holds stays visible. A well-formed table's spans fill its grid exactly, so it renders as today. A table with no `w:tblGrid`, or one that declares no `w:gridCol`, takes as its grid the most cell elements any one of its rows holds, a count of the input's own elements, so a span there adds copies only up to that width.

### 8. A vertical continuation takes the source that starts at its grid offset in the row above, copied as many times as that source's own span allows, and a continuation with nothing above it holds its own text

The offset is the row's `grid_before` plus the declared spans of the cells before it, which is how python-docx finds the cell above, and each row keeps a map from offset to source, so each continuation costs one lookup and not a walk up the column. The text is the source's, read once, so a merged column renders the root's text in every row, as today. Today a continuation in the first row, or one with no cell at its offset above, makes the whole render fail with python-docx's `ValueError`; treating it as a cell that starts there renders the table, as a word processor does.

### 9. A source's text is flattened once and its kept length counted once, and the writer hands the Builder the flattened text

`table_cell` flattens again and escapes, and flattening is idempotent, so the line is byte for byte today's. Copies of one source share one string, so text that the Builder flattens to nothing costs nothing per copy.

### 10. The table's width is computed from the layout, before any text is read, and its rows are drawn lazily: the Builder pulls each row only after the line before it was written, and a row stops collecting once its kept characters exceed `Builder.remaining`, read when the row is drawn

The width must be today's, the longest row's cell count, or the header's padding would change; the layout gives it from counts alone. Drawing lazily lets the Builder's own per-line budget and per-row clock stop the table, so no row past the cut is read. A stopped row is refused for the reason decision 2 gives, and the writer draws nothing after it.

### 11. The Builder gains three things, and only these: the property `Builder.remaining`, the function `kept_length(text)` in `markdown.py`, and a keyword `width` on `Builder.table`, with which rows may be any iterable drawn one at a time

`remaining` is `0` once the rendering has stopped, and otherwise the budget less the characters written, never negative; it does not fold in the ratio guard, because passing the ratio is a loud failure, not a cut. `kept_length` lives beside `flatten` because the Builder's cost rules are its own. `table(rows)` without `width` reads every row first and takes the longest row's length, exactly as today, so every existing call keeps its meaning. The xlsx spec, landing third, streams its rows through this same keyword.

### 12. A cut stays the existing, honest truncation, and no new limit is added

Every stop here leaves the Builder to cut, so the rendering is `truncated` with today's notice and detail, or `empty` when nothing fit, exactly as today. No `RenderLimits` field is added and nothing caps what vfs stores: the bounds are the budget the rendering already has and the grid the document declares.

### 13. `DocxRenderer.revision` rises by one over the value it holds when this spec is built, 1 at `5d47a21a`

A changed rendering must carry a new generation, or the skip law keeps the old text. If the container spec, landing first, has already raised it, this spec raises it once more and the landing notes say so; as that spec is signed, it raises none, so the value is 2.

The cost, honestly. The new generation makes every docx row dirty for the render stage, and the first index pass after the landing pays it, whichever pass that is: in working hours a 15-minute partial pass, not the daily rebuild. That pass re-renders every docx entry; each landed rendering resets the entry's chunk and index flags, so the same pass re-splits it and re-posts its gram index entries, while embeddings of unchanged chunk text are carried by the chunk cache (`indexing.py:294`). The reference deployment does not measure its docx share. At a tenth of its 10,000,000 files, that is about 1,000,000 renders, the size of the nightly batch, landing at once, with their chunks on the per-index-visit multiplier, which is the largest one AGENTS.md names. The render stage's keyset pages and byte cuts bound each step, and the pass pays it once. The project is pre-release, so nothing spreads it.

### 14. Each bound lands with its mutant as a row of the mutant ledger, G1 to G16

The testing standard says a pinned law is proven by the mutation it kills and that the mutation lands as a ledger row. The ledger holds no row whose target is under `src/vfs/rendering/` (EXECUTED: `grep -c rendering context/standards/mutant-ledger.md` reports 0), so no row is re-anchored. The prefix is G because [the refresh spec](2026-10-31-refresh-the-incremental-index-verb.md), written first, claims D1 to D10, and G is used neither by the ledger nor by any queued spec.

### 15. A paragraph's heading level is read from a style table the writer builds once, at its first paragraph, in one pass over the styles part's parsed element; python-docx's `Paragraph.style` is never called

The table maps each `w:style`'s `styleId`, the first with that id as python-docx's query finds, to whether its `w:type` is `paragraph` and to its name, mapped to the name python-docx shows (`BabelFish.internal2ui`, reached through `load_library("docx.styles")` as the pptx renderer reaches its enum); the default is the last paragraph style whose `w:default` is on. A paragraph's id is its own `w:pPr/w:pStyle/@w:val` (`paragraph._p.style`); an id that is empty, missing from the table or not a paragraph style falls back to the default, as python-docx does (`docx/styles/styles.py:76-115`). The type, the default and the name are read as raw attributes, so an unrecognised value reads as not paragraph and not default, and a style whose `w:name` is missing or has no value has no name: the pass never fails on it, and a paragraph that uses it reads as body text. Each lookup is then one dictionary probe, so the work is one pass over the styles part per render, never paragraphs times styles. A declared id is never placed in a query, so an id holding a quote mark renders the paragraph as body text where today the render fails. The pass is `document.styles.element._iter_styles()`, python-docx's own walk of the `w:style` children (`docx/oxml/styles.py:318-320`), which criterion 15's spy counts. Like decision 6's properties, a change to it in a later python-docx raises inside `render` and is stamped `failed`. A `_Writer` made without a style table, as the suite's `_inline` node makes one, reads every paragraph as body text.

### 16. The header and footer loops read the clock before each paragraph, as the body loop does before each block

The body loop asks `builder.boundary` once a block, which reads the clock (`markdown.py:136-147`); the header and footer loops asked nothing. `_Writer.parts` now calls `builder.out_of_time()` once before each paragraph and stops when it answers true, so the rendering is `partial` with today's detail, and the same cadence holds everywhere: one clock read per block written.


## Intent

After this spec, rendering one docx costs work in proportion to the text the rendering writes plus one pass over the input. A note's text is built once. A header or footer part is walked once. A style is looked up in a table read once. A span never makes more cells than the grid. A merged cell is resolved by one lookup and read once. Once the budget is spent, nothing more is collected, and every loop that writes reads the clock once a block. Every ordinary document renders byte for byte as today, cut or not.

The sentence was checked against every loop the Design keeps or adds. The body's block list and the section list are one pass each. Each distinct header or footer part is walked once, with a clock read and a stopped check per paragraph. Each paragraph costs one style probe and an `element.iter()` walk that ends at decision 2's stop. The notes parts and the styles part are read once each. A table's layout is one pass over its cell elements, and its rows are drawn only while the Builder takes them. Pictures are one per placeholder element and capped. No loop runs per reference, per section naming a part, per declared span, per merge height or per style.

Output changes in exactly these places, each a document Word does not write: a repeated note reference after its first (decision 1); a header or footer part named by more than one section (decision 4); nested note elements (decision 5); a span past the grid or below one, and in a table that declares no grid a span past its widest row (decision 7); a vertical continuation with nothing above it (decision 8), and a styles part or style id python-docx cannot query, or a paragraph using a style it cannot name (decision 15), each of which renders where today the render fails; and, under decision 16, a rendering the clock cuts no longer carries the header or footer paragraphs that today are written after the clock has run out; its status and detail are today's.

## Design

**`src/vfs/rendering/markdown.py`.** `kept_length(text) -> int` after `table_cell`: `len("".join(text.split())) - text.count("\x00")`, with a docstring saying appended text costs at least this much. `Builder.remaining`, a property beside `spent`. `Builder.table(rows: Iterable[Sequence[object]], *, width: int | None = None) -> bool`: if stopped, `False`; with no width, rows become a list and the width is the longest row's, `0` for none; the first row is drawn, and none means `True`; then today's loop over `chain((first,), drawn)`, the clock checked before every row after the first, as today. `Iterable` joins the `TYPE_CHECKING` imports and `chain` the top imports. The module docstring gains one sentence on the three.

**`src/vfs/rendering/docx.py`.** `DocxRenderer.revision` per decision 13, and `render` calls `writer.parts(...)` for the headers and then for the footers. In `_Writer`: a `_written` set of `(kind, id)` and the method `_note` (decision 1), replacing the module function; `parts(items)` with its clock read before each paragraph (decisions 4 and 16); `paragraph` with its early return (decision 3) and its level from `_Styles.name(paragraph._p)` (decision 15), `_Writer` taking the `_Styles` as an optional third argument so the suite's existing `_Writer(builder, notes)` call keeps working; `_inline` with decision 2's stop; `table` and the generator `_rows` (decisions 6 and 10). New private helpers under the Internal helpers banner: `_Styles` (decision 15), `_Source` (decision 9) and `_layout(rows, grid)` (decisions 7 and 8), with the grid found by `tbl.find` and its fallback (decisions 6 and 7). `_note_texts` per decision 5. A constant `_ON`, the on values of an OOXML boolean (`1`, `true`, `on`), sits with the module's constants, and `load_library` joins the import from `seam`. The module docstring names the bound in two sentences. All imports stay at the top, and no python-docx name is imported.

**Tests.** A new module, `tests/rendering/test_docx_bounds.py`, holds the nodes of criteria 1 to 10 and 14 to 18 with their small document builders, made with python-docx and edits to its parsed elements, as `test_footnotes_are_written_at_their_reference` stages its note today. It counts with spies installed by `monkeypatch`: `CT_P.text` reads, `_Writer._inline` calls, the characters handed to `Builder.paragraph`, the rows the Builder draws, the style elements `CT_Styles._iter_styles` yields, and the clock reads of `vfs.rendering.markdown.monotonic`, replaced by a counter that answers "not yet" a set number of times and then "past", so no test reads a clock. It also holds `test_a_stopped_row_ends_the_draw`, which drains `_Writer._rows` directly over a two-row layout under a budget of one character and asserts it yields exactly one partial row; this covers the stop's `return`, which the Builder never reaches because it refuses that row. `tests/rendering/test_markdown.py` gains a class `TestWhatIsLeft` with criteria 11 to 13. Every import in both files stands at the top of the file, `kept_length` among `test_markdown.py`'s; no test imports inside a function. No existing test changes.

**Tests first.** Every criterion node is written and seen failing on the base tree before the code changes. EXECUTED on a scratch build of this design over a copy of `5d47a21a`: the fourteen nodes of criteria 1 to 13 fail on the base and pass on the build; of the four nodes the review added, the style, clock and stopped-row nodes fail on the base and pass on the build, and the no-grid node passes on both, because it pins output this spec keeps, so its red is its mutant (G16); criterion 14's node was not run there and is red on the base by construction, whose revision is 1; the existing nodes, 96 in `tests/rendering/` and 41 in `tests/storage/database/test_render.py` at `5d47a21a`, pass unchanged on the build; at the build those counts are `5d47a21a`'s plus what earlier landings add, the container spec's nodes under `tests/rendering/` among them; and coverage of `docx.py` and `markdown.py` is 100% over all of them.

**Scale.** Per rendered document, in operations: one pass over the body's elements, one over each distinct header and footer part, one over each notes part, one over the styles part and one dictionary probe per paragraph; one clock read per block written, body, header or footer; per table, one layout pass over its cell elements and one text read per source drawn; and the text built never exceeds what the Builder writes plus one piece or one row. Nothing grows with references, sections, declared spans, merge height or styles. The reference deployment's multiplier is the per-index-visit one, about 11,000,000 visits a day, of which docx renders are a share; this spec makes each one cheaper, and the one-time re-render of decision 13 is paid by the first pass after the landing, as that decision says.

**`context/standards/mutant-ledger.md`** gains rows G1 to G16 after K12, provenance "a docx note is written once and a span is clamped": G1 the note-once check dropped; G2 the paragraph stop dropped; G3 the stop counting every character, not kept ones; G4 the part set dropped; G5 the stopped return in `paragraph` dropped; G6 notes read at every depth again; G7 copies taken as the declared span; G8 a source's text read on every call; G9 a continuation never resolved upward; G10 the in-row stop dropped; G11 `table` with a width reading every row first; G12 `remaining` ignoring a stopped Builder; G13 `kept_length` counting NULs; G14 the style table undone, two directions: `_Writer.paragraph` reading `paragraph.style` again, or the table reading each name through `name_val`; G15 the clock read in `parts` dropped; G16 the no-grid fallback dropped. EXECUTED on the scratch build, G1 to G13 before decisions 15 and 16 were added to it and G14 to G16 after: each fails at least one criterion node and no existing node; G14 fails criterion 15 alone, G15 criterion 16 alone, G16 criterion 17 alone.

## Scope

In: decisions 1 to 16. Files: `src/vfs/rendering/docx.py`, `src/vfs/rendering/markdown.py`, `tests/rendering/test_docx_bounds.py` (new), `tests/rendering/test_markdown.py`, `context/standards/mutant-ledger.md`, and this spec's landing notes.

Order and neighbours. This spec lands second of the three rendering fixes. It shares `src/vfs/rendering/docx.py` with [the container spec](2026-11-13-an-office-container-is-measured-before-it-is-opened.md), which lands first and adds the container check's call, as that spec gives it, before `docx.Document` opens the bytes; this spec rebases on that call and on whatever revision it leaves (decision 13). That spec also adds nodes under `tests/rendering/`, in `test_seam.py` and `test_renderers.py`, and ledger rows of its own prefix; this spec edits neither of those test files, and its rows take G. It shares `src/vfs/rendering/markdown.py` and `tests/rendering/test_markdown.py` with [the xlsx spec](2026-11-13-an-xlsx-sheet-is-read-under-the-clock-and-its-tables-stream.md), which lands third and builds on the Builder as decision 11 leaves it; it also edits `Builder.build`, on lines disjoint from this spec's, and its reviewer applied the two to one copy, where they compose. Of the other specs queued under `specifications/active/`, only [the rebuild refactor](2026-11-12-the-full-pass-is-named-rebuild-and-its-pipeline-leaves-the-backend.md) touches `src/vfs/rendering/`: it renames one word in docstrings of `seam.py` and `registry.py`, files this spec does not edit, so no line is shared. None of them edits `tests/rendering/`. So this spec is parallel-safe with them. It must land before [the refresh spec](2026-10-31-refresh-the-incremental-index-verb.md), which runs the render step on an automated pass. [The release-audit spec](2026-11-07-the-release-audit-is-a-review.md) waits on this fix; this spec does not edit it.

Out: the pptx and xlsx renderers, each with its own spec or none, because neither has these findings' shapes; endnotes, body-level content controls and tables nested in cells, which are not rendered today and adding them is a feature; a Rust kernel for the docx walk, which python-docx's tree makes moot; and any bound on the input's own size, which is the container spec's.

## Acceptance criteria

Counts and states, never clocks. Each named node fails on the base tree and passes on the build, as the Design records, except criterion 17's, which pins kept output and whose red is its mutant. Nodes 1 to 10 are in `tests/rendering/test_docx_bounds.py`.

1. A paragraph that refers to one 40-character comment five times renders as the full comment at the first reference and ` [comment 0]` at the other four, and the characters handed to `Builder.paragraph` equal that line's length. Test: `test_a_repeated_note_is_written_once_and_marked_after`.
2. Under `RenderLimits(chars=200)`, a document of a short paragraph and a paragraph of 500 kept characters in 50 runs renders as `truncated` with today's detail and text, and the characters handed to `Builder.paragraph` are at most the short paragraph's, plus 200, plus one run's. Test: `test_a_paragraph_stops_collecting_once_it_cannot_fit`.
3. Four sections whose definitions name one header part of four paragraphs render the header once, and `_Writer._inline` is called eight times: four header paragraphs, three section-break paragraphs and the body's one. Test: `test_a_header_part_named_by_many_sections_is_written_once`.
4. When the budget is spent inside the body, `_Writer._inline` is called twice, for the paragraph written and the one cut, and never for the footer's paragraphs. Test: `test_nothing_is_walked_once_the_budget_is_spent`.
5. Ten nested footnote elements of one character each read as one note of ten characters. Test: `test_nested_note_elements_are_read_once`.
6. On a two-column table whose first cell declares a span past the grid, the row has three cells, the first cell's text twice and the second's once, and `CT_P.text` is read twice. Test: `test_a_span_never_makes_more_cells_than_the_grid`.
7. A one-column table merged down eight rows renders the root's text in all eight rows, as today, with one `CT_P.text` read and no `_tc_above` call. Test: `test_a_vertical_merge_reads_its_text_once`.
8. Under `RenderLimits(chars=300)`, a forty-column header row whose one cell of 20 kept characters spans the grid is drawn with twelve cells, its text read once, and the rendering is `empty`, as today. Test: `test_a_table_stops_drawing_once_the_budget_is_spent`.
9. Under `RenderLimits(chars=300)`, a table of a header row and nineteen rows of two 20-character cells, after one short paragraph, renders `truncated` with today's text, and `CT_P.text` is read eleven times. Test: `test_a_long_table_stops_reading_rows_once_cut`.
10. Ordinary documents render as before: a three-by-three table with one horizontal and one vertical merge, made by python-docx's own `merge`, renders exactly today's text, captured at `5d47a21a`, with nine `CT_P.text` reads, one per paragraph of each source; and for every budget from 1 to 419 characters, a document mixing headings, whitespace runs, breaks, a marker-like line, pipes and a merged table renders identically with `Builder.remaining` and with it patched to no limit, and at every budget from 1 to 419 the mixed document's rendering equals the base's, captured at `5d47a21a` as a fixture: one SHA-256 over the 419 renderings' status, detail and text, held as a literal in the test (EXECUTED: the digest is the same on the base and on the scratch build). Tests: `test_ordinary_documents_render_as_before`, `test_a_cut_lands_where_it_landed_before`. Every existing node of `tests/rendering/` and `tests/storage/database/test_render.py` passes unchanged.
11. `remaining` counts down by each line written and its blank, and is `0` once a line is refused. Test: `tests/rendering/test_markdown.py::TestWhatIsLeft::test_remaining_counts_down_and_is_zero_once_stopped`.
12. `kept_length` is 0 for the empty string, drops whitespace including U+3000 and NUL, and keeps a pipe. Test: `tests/rendering/test_markdown.py::TestWhatIsLeft::test_kept_length_drops_whitespace_and_nuls`.
13. `table(rows, width=2)` over a generator draws only the rows it writes and the one it refuses, pads the header to two cells, and is cut. Test: `tests/rendering/test_markdown.py::TestWhatIsLeft::test_a_table_with_a_width_draws_each_row_after_the_line_before`.
14. `DocxRenderer().version` begins with the revision of decision 13. Test: `tests/rendering/test_docx_bounds.py::test_the_docx_generation_names_its_new_revision`.
15. Twenty empty paragraphs in the body and twenty in a header, over the default styles part of N styles, make `CT_Styles._iter_styles` yield N style elements in all, and render as today; a paragraph whose declared style id holds a quote mark renders as body text; and the same document also holding an unused paragraph style whose `w:name` has no value renders as today, that style counted among the N. Test: `tests/rendering/test_docx_bounds.py::test_a_style_is_looked_up_once`.
16. With the markdown module's clock replaced by a counter that answers "not yet" twice and "past" after, a header of five paragraphs is walked twice, `_Writer._inline` is called twice, and the rendering is `partial` with the first two header paragraphs. Test: `tests/rendering/test_docx_bounds.py::test_header_paragraphs_read_the_clock`.
17. A three-by-three table with its first two header cells merged and no `w:tblGrid` renders today's text, `r0c2` in the third column. This node pins output kept, so it passes on the base too; its red is G16. Test: `tests/rendering/test_docx_bounds.py::test_a_table_with_no_grid_keeps_its_columns`.
18. `_Writer._rows`, drained directly over a two-row layout under a budget of one character, yields exactly one partial row. Test: `tests/rendering/test_docx_bounds.py::test_a_stopped_row_ends_the_draw`.
19. Rows G1 to G16 stand in the ledger, each replayed under the safe-restore rule and killed by at least one failure, the counts in the landing notes; and `scripts/ci.sh` is green at 100% coverage on the tree as committed.

## Landing notes

Filled in on landing.

## One line

The docx renderer now writes a note's text once, a header part once and a span no wider than the grid, looks styles up in a table read once, reads the clock in every loop, and stops collecting when the budget is spent, so its work follows the text it writes while ordinary documents render exactly as before.
