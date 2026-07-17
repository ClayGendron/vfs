# 029 — Structure-Aware Chunking for All File Types

- **Status:** draft
- **Date:** 2026-05-22
- **Owner:** Clay Gendron
- **Kind:** feature
- **Depends on:** 014 (auto-chunk write phase, `VFSEntry.chunk()` /
  `split_content` contract)
- **Supersedes:** 028 (markdown structure-aware chunking). Markdown is no longer
  a special case with its own parser — it rides the same generic tree-sitter
  walker as every other type. 028's goal (heading-aware, code-fence-safe
  markdown chunks) is delivered here as one grammar entry, not a dedicated
  module.

## Intent

Give **every** file a structure-aware default chunker through a single,
language-agnostic engine. Today non-trivial files run through the recursive
separator splitter (`split_with_line_ranges`): a walk over
`("\n\n", "\n", " ", "")` at a 2 KB budget that cuts wherever the budget lands —
mid-function, mid-statement, mid-JSON-object, inside a markdown code fence. The
result is poor retrieval targets and ugly citations.

This story adds one chunker, `split_code`, driven by
`tree-sitter-language-pack` (~306 grammars). It parses a file with the grammar
for its type and chunks on real syntax-tree boundaries:

1. Recurse the parse tree. Any node that fits the budget is emitted whole.
2. A node larger than the budget recurses into its children.
3. The resulting contiguous, file-covering byte spans are greedily packed back
   up to the budget.

One algorithm covers all languages **including markdown and Python**. The
markdown grammar is heading-hierarchical (content nests inside its heading's
`section` node), so the same size-based descent cuts at heading boundaries and
recurses into sub-headings for free — no markdown-specific code, no separate
parser. Adding a language is one `ext/filename → grammar` entry. Only files
with no grammar (plain text, logs, lockfiles, unknown extensions) keep the
recursive separator fallback.

## Why

- **Pure separator splitting is blind to syntax.** It cuts inside function
  bodies, splits a JSON object mid-pair, severs an HTML element from its open
  tag, and (the original 028 defect) cuts inside markdown fenced code blocks —
  a `#` comment line in a Python fence is indistinguishable from a heading to a
  string matcher.
- **Syntax boundaries are the natural retrieval unit.** A function, class,
  type, top-level config block, or markdown section is what a query is usually
  after. Cutting there keeps the unit intact in one chunk.
- **One generic walker beats N hand-tuned extractors — and beats a second
  parser.** A prototype that hand-coded per-language node-type sets did not
  scale past a couple of languages. A size-based recursive descent over the
  uniform tree-sitter node API (`named_child_count`, `start_byte`, `end_byte`)
  needs no per-language knowledge and works identically across all 306 grammars
  (LlamaIndex's `CodeSplitter` uses this shape). Because tree-sitter already
  parses markdown hierarchically, folding markdown in removes a whole parser
  (`markdown-it-py`) and a dedicated `split_markdown` module for output that is
  equivalent on real docs.
- **The dispatch seam already exists.** `VFSEntry.chunk()` can see the file
  path; `split_content` (a `@staticmethod(content)`) cannot. `chunk()` resolves
  a grammar from the path and routes to `split_code`. After this story, the only
  files on the recursive fallback are those with no grammar at all.

## Decisions (settled before implementation)

Decided in design + prototyping (`scripts/chunk_viz.py`); not open for the
implementation to relitigate:

- **One generic byte-span algorithm for all file types**, markdown and Python
  included. No per-language node-type configuration. Splitting decisions use
  only node size and child structure.
- **Byte spans, not line spans.** tree-sitter nodes are byte/column-precise;
  several nodes can share a line. Slicing by UTF-8 **byte** offsets (then
  computing line numbers from those offsets) keeps reconstruction exact even
  with multibyte characters. A line-based slicer double-counts shared lines.
  Verified byte-exact across all repo files.
- **`tree-sitter-language-pack` is the chunking dependency** (core, already
  landed). **`markdown-it-py` is removed** — markdown uses the pack's `markdown`
  grammar. Rationale: the pack is already a required heavyweight; a second
  markdown parser earns nothing once tree-sitter parses markdown hierarchically.
  Determinism does not depend on installed extras (the pack is always present).
- **The pack ships a Rust-native binding with a non-standard API** — *not* the
  `tree_sitter` PyO3 binding. Pin this in code comments so a future reader does
  not "fix" it back:
  - `parser.parse(source: str)` — takes **`str`**, not `bytes`.
  - `tree.root_node()` — a **method**, not a property.
  - Node accessors (`kind`, `named_child_count`, `start_byte`, `end_byte`, …)
    are **methods**. No `named_children` list; iterate `named_child(i)` for
    `i in range(named_child_count())`.
  - `start_byte` / `end_byte` index the **UTF-8 encoding** of the source.
- **No overlap.** Structural chunking replaces overlap; the separator fallback
  for an oversized indivisible leaf also runs at `overlap=0`.
- **Char/byte budget, default 2048.** No tokenizer in the cut path. The size
  test compares UTF-8 byte length (≥ char length — conservative, never
  over-budget).
- **No line-snapping of chunk boundaries.** Boundaries fall on AST-node edges,
  usually line starts but occasionally mid-line for languages allowing multiple
  statements per line. AST-accurate beats cosmetic line alignment.

## Scope

### In

1. **`split_code(content, *, language, chunk_size=2048)` in `vfs.chunking`.**
   Returns `list[tuple[str, int, int]]` — `(chunk_text, line_start, line_end)`,
   1-indexed lines — same shape as `split_with_line_ranges`. Returns `[]` when
   the whole content fits one chunk. `language` is a
   `tree-sitter-language-pack` grammar name.

   Algorithm:
   - Parse `content` with a cached parser for `language`.
   - Recursive descent collecting contiguous byte spans: emit a node whole if
     `end_byte - start_byte <= chunk_size` or it has no named children;
     otherwise recurse into named children, emitting interstitial gaps
     (punctuation/comments between children, plus any leading/trailing gap
     inside the node) as their own spans.
   - Greedily merge adjacent spans while merged byte length `<= chunk_size`.
   - Per merged span: decode `data[start:end]`, skip whitespace-only, compute
     `line_start = data[:start].count(b"\n") + 1`,
     `line_end = line_start + text.count("\n")`. A merged span that is a single
     oversized indivisible leaf falls back to `split_with_line_ranges(...,
     overlap=0)`.
   - On any parse/binding error, fall back to `split_with_line_ranges` (chunking
     never raises).

2. **`language_for_path(path) -> str | None` in `vfs.chunking`** — resolves a
   grammar name from a path, **basename first, then extension**:
   - Extension map (no leading dot), ≥90 entries, e.g. `md/mdx/markdown/rmd/qmd
     → markdown`, `py/pyi → python`, `rs → rust`, `tsx → tsx`, `c → c`,
     `cpp → cpp`, `cs → csharp`, `html → html`, `json → json`,
     `yaml/yml → yaml`, … (full table in code).
   - Special-filename map for files with no usable extension:
     `Dockerfile/Containerfile → dockerfile`, `Makefile/GNUmakefile → make`,
     `CMakeLists.txt → cmake`, `go.mod → gomod`, `go.sum → gosum`,
     `go.work → gowork`, `requirements.txt → requirements`,
     `.gitignore → gitignore`, `.gitattributes → gitattributes`,
     `.editorconfig → editorconfig`.
   - Returns `None` for `.ipynb` (handled by `split_notebook`) and any unmapped
     path.
   - Every grammar name validated against the pack's supported set at import;
     unknown names dropped, not fatal.

3. **Jupyter notebooks** (`.ipynb`) → `split_notebook(content, *,
   chunk_size=2048)`. A notebook is a JSON document of cells with embedded
   outputs, execution metadata, and base64 image blobs — chunking it as raw
   JSON produces useless targets. The extractor parses the JSON, walks
   `cells[]`, and chunks each cell's joined `source` only (outputs/metadata
   discarded): markdown cells via `split_code(..., language="markdown")`, code
   cells via `split_code(..., language=<kernel language>)` from
   `metadata.kernelspec.language` (default `python`). Line ranges are
   cell-relative with the cell index recorded in the chunk path segment.
   Malformed JSON falls back to `split_content`.

4. **Path dispatch in `VFSEntry.chunk()`.** Order: `.ipynb` → `split_notebook`;
   else `language_for_path(self.path)` resolves a grammar → `split_code`; else
   `split_content` (recursive fallback). `split_content` stays the documented
   override hook and the splitter for everything with no grammar. No special
   markdown branch — markdown resolves to the `markdown` grammar like any other.

5. **`markdown-it-py` removed** from dependencies; the `split_markdown` module
   and its tests from 028 are deleted (folded into `split_code`).

6. **Tests** covering: function/class boundary integrity (no chunk starts
   inside a function body for a multi-function file over budget); markdown
   code-fence integrity (no chunk starts inside a fence — the 028 acceptance
   case, now satisfied via the `markdown` grammar); byte-exact reconstruction
   (concatenated chunks == source), including a multibyte-char file; packing
   keeps chunk count near the separator splitter, not one-node-per-chunk;
   oversized-leaf separator fallback; the `[]` no-split case; line-range
   accuracy (`1 <= line_start <= line_end <= total_lines`); parse-error
   fallback; special-filename resolution (`Dockerfile`, `go.mod`); notebook
   routing (`.ipynb` → `split_notebook`, outputs discarded); dispatch
   (`.rs`/`.md`/`.py` → `split_code`; `.txt` → `split_content`).

### Out

- Per-language node-type tuning, preamble clustering, or heading-path-style
  breadcrumb metadata (a separate story if ever wanted; note tree-sitter
  markdown's `section` nesting would make heading breadcrumbs cheap later).
- Line-snapping of chunk boundaries; token-based sizing; overlap.
- A user-facing ext→grammar override hook (subclassing `split_content` remains
  the escape hatch).
- Re-chunking / migration of already-chunked files — future output only.
- Semantic / embedding-based chunking.

## Behavior contract

- **`split_content` is unchanged** — `@staticmethod(content)` returning the
  recursive split, still the override hook and the fallback for grammarless
  files. Existing subclass overrides and the `staticmethod(chunker)` test-patch
  pattern keep working.
- **Dispatch lives in `chunk()`**, which can see `self.path`; `split_code` and
  `split_notebook` are the dedicated strategies it routes to.
- **Determinism.** Output depends only on `content`, `chunk_size`, and the
  resolved grammar — never on installed extras (the pack is always present).
- **Total coverage.** Every file is chunked by exactly one of: `split_code`
  (any mapped grammar, markdown/Python included), `split_notebook` (`.ipynb`),
  or `split_content` (everything else). Chunking never raises.
- **Never over budget.** Byte-length size test guarantees no merged chunk
  exceeds `chunk_size`; oversized indivisible leaves are separator-filled.

## Acceptance criteria

1. A source file with several top-level functions, sized to span multiple
   chunks, produces **zero** chunks whose first non-blank line falls inside a
   function body without its signature.
2. A markdown file with a fenced code block containing `#`-comment lines, sized
   so the block spans a chunk boundary, produces **zero** chunks whose first
   line falls inside the fence. (The 028 defect; now satisfied via the
   `markdown` grammar.)
3. Concatenating all chunk texts in order reproduces the source exactly, for an
   ASCII file and a multibyte-char file.
4. `split_code` returns `[]` for content `<= chunk_size`.
5. No returned chunk exceeds `chunk_size` bytes, including for a file with a
   single oversized indivisible line (separator fallback engages).
6. Every tuple satisfies `1 <= line_start <= line_end <= total_lines`.
7. `language_for_path` resolves: `"a.rs"→"rust"`, `"a.md"→"markdown"`,
   `"a.py"→"python"`, `"a.tsx"→"tsx"`, `"Dockerfile"→"dockerfile"`,
   `"go.mod"→"gomod"`, `"notes.txt"→None`, `"nb.ipynb"→None`.
8. `VFSEntry(path="/x.rs"|"/x.md"|"/x.py", …).chunk()` routes through
   `split_code`; `/x.ipynb` through `split_notebook`; `/x.txt` through
   `split_content`.
9. A file that does not parse under its grammar still chunks (via fallback)
   without raising.
10. `tree-sitter-language-pack` resolves as a core dependency; `markdown-it-py`
    is no longer a dependency; all pre-existing `chunk()` / `split_content`
    tests pass; coverage stays ≥ the 99% gate.

## Language & file-type coverage

**Covered by `split_code` (representative — full map in code):**

- **Docs / literate:** Markdown, MDX, R Markdown (`.rmd`), Quarto (`.qmd`),
  reStructuredText, LaTeX — markdown family via the heading-hierarchical
  `markdown` grammar.
- **Python:** `.py`, `.pyi`.
- **Systems:** Rust, Go, C, C++, CUDA, Zig, D, Nim, V, Odin.
- **JVM / .NET:** Java, Kotlin, Scala, Groovy, C#, F#, VB.
- **Web / scripting / data science:** JavaScript, JSX, TypeScript, TSX, Vue,
  Svelte, Astro, PHP, Ruby, Lua, Perl, **R** (`.r`/`.R`), Julia, Dart, Elixir,
  Erlang, Clojure, Haskell, OCaml, Swift, Elm, Gleam, Solidity, Tcl.
- **Shell:** Bash/sh/zsh, Fish, PowerShell.
- **Markup / config / data:** HTML, XML, CSS, SCSS, Less, JSON, JSON5, YAML,
  TOML, INI, CSV, TSV.
- **Build / infra / IDL:** Dockerfile, Makefile, CMake, SQL, GraphQL, Protobuf,
  Terraform/HCL, Nix, go.mod/go.sum, requirements.txt, Vim.

**Jupyter notebooks** (`.ipynb`) → `split_notebook` (cell source only).

**Fallback to `split_content`:** plain text (`.txt`), logs, `.env`, lockfiles,
and any unmapped extension — still chunked, just by separators, not syntax.

### Known coverage gaps / ambiguities (documented, not blocking)

- **Ambiguous extensions** resolve to the most common language:
  - `.m` → unmapped (Objective-C vs MATLAB collide; needs a project signal).
    `.h` → C (not C++/Objective-C).
  - `.pl` → Perl (not Prolog). `.v` → unmapped (Verilog vs Coq vs V-lang).
  - `.ts` → TypeScript (never the MPEG/translation senses).
- **No per-extension override hook** in this story; the map is fixed.
  Subclassing `split_content` is the escape hatch.
- **Notebook outputs are intentionally dropped** — source only; chunk line
  ranges are cell-relative, not offsets into the raw `.ipynb` JSON.
- **No `rmarkdown`/`quarto`/`ipynb` tree-sitter grammar exists**; `.rmd`/`.qmd`
  use the `markdown` grammar, `.ipynb` uses the JSON-cell extractor.
- **Generated/huge data files** (`package-lock.json`, coverage reports) parse
  fine but are weak retrieval targets; excluding them is an ingestion-policy
  concern, not a chunker concern.

## Notes / measurements

- Prototype + validation tool: `scripts/chunk_viz.py` (exploratory, not shipped
  behavior). It exercises the exact byte-span algorithm this story productizes,
  for all file types via the same path.
- Whole-repo benchmark (325 files, ~4.9 MB): structure-aware chunking ~680 ms
  (~7 MB/s) vs ~76 ms (~64 MB/s) for pure separator splitting — invisible at
  write time (one file per write; the largest source file, 135 KB, chunks in
  ~15 ms), relevant only for bulk re-index. One-time grammar loading adds ~14 ms
  total; the per-process parser cache makes repeats free. No single file exceeds
  ~5% of total time — cost scales with bytes, not hotspots.
- Validated across all repo files (markdown, Python, Rust/Go/Java/C/C++/C#/HTML/
  CSS/JSON/YAML/TS/TSX/SQL + others): **0 over-budget chunks, 0 errors,
  byte-exact reconstruction** — including a 351 KB deeply-nested `coverage.json`
  (197 chunks) that required raising the recursion limit for the descent.
- Markdown equivalence check: on a 39 KB code-heavy doc, tree-sitter `markdown`
  produced 25 chunks vs markdown-it's heading-section approach 23 — equivalent,
  both fence-safe — confirming markdown loses nothing by folding into the
  generic walker.
