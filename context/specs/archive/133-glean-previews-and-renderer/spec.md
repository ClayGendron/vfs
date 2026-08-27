# 133 — previews and the glean renderer: `Match.preview` with line bounds, bolded terms, rank-ordered output

- **Status:** **landed 2026-08-27** — drafted 2026-08-26 from ADR 052 pin 7. Fourth of
  the glean arc; small and self-contained on top of spec 132's rows.
  Both slices landed in one session; landing note below.
- **Born from:** ADR 052 §7; memo
  `../../../research/2026-08-26-glean-previews-and-result-shape.md`;
  study `../../../research/studies/2026-08-26-glean/preview-and-snippets.md`
  (prototype `preview_proto.py`: 10–22 µs per chunk, 314 µs per
  10-entry page).
- **Date:** 2026-08-26
- **Owner:** Clay Gendron
- **Kind:** model fields on `Match`, a pure preview function in
  `src/vfs/results/`, a `glean` branch in `render.py`.
- **Depends on:** spec 132 (the rows), spec 130 (the folded query terms
  the bolder matches against).
- **Relates to:** `_render_grep`'s line conventions; ADR 007 (display
  budgets are not verb parameters).

## Intent

An agent uses three things from a hit: the path, the line range, and a
short excerpt. Today glean would render through `_render_path_list`,
which **sorts by path** — a ranked list printed alphabetised. This spec
gives glean its own rank-ordered renderer and a query-biased, bolded,
token-bounded preview built only from the chunk text already on the
row.

## Decided semantics

1. **Fields**: `Match.preview: str | None`, `Match.preview_start: int |
   None`, `Match.preview_end: int | None` — absolute, 1-indexed, a
   sub-range of `start..end`. `content` keeps its raw-text contract
   (grep's) untouched; grep never populates the preview fields.
2. **The selector** (`src/vfs/results/preview.py`, a pure function over
   `(chunk_text, chunk_line_start, folded_terms)`): fold the chunk once
   (`fold_content`; newlines survive, so lines align); if no term occurs
   anywhere, return the head window; else score each line — Σ over
   *distinct* terms present of `log2(1 + len(term))` × (1.0 whole-word |
   0.5 substring) + a capped extra-occurrence bonus + an adjacency-run
   bonus — slide a W-line window (W = 4) with a coverage bonus, take
   the best window, earliest on ties; bold merged spans with `**…**`
   (never nested); trim lines to 160 chars keeping the first bold span
   in view with `…`; cap the preview at 480 chars. Substring matching
   with a whole-word bonus so `embed` bolds `embedding` and `chunk`
   bolds `chunk_index`; an offset map handles folds that change length.
3. **"Fast" is a docstring contract**: no second content fetch; one
   folded pass; hard caps. The pin is a budget test on 10k chunks
   (≤ 50 µs per chunk on CI hardware) so a regression is caught.
4. **Vector-only hits** (later, spec 135) and chunks with no term
   present take the head window with bounds and no spans — not a
   warning.
5. **Renderer**: `_render_body` gains a `glean` branch printing in
   **rank order** — a path line with the score, then per match a
   `path:start-end` line and the preview lines as quoted plain lines
   (never inside a fence, where markdown does not style). Table mode
   remains for row-level projections (`matches` renders as `start-end`
   lists as today). Display budgets (W, per-line and per-preview caps,
   K) are render-layer constants overridable through `to_str` /
   projection options — never glean parameters.
6. **Where it runs**: the backend fills `preview` on its `Match` rows
   after the statement returns (it has the folded terms); the router's
   merge (spec 137) leaves previews untouched.

## Scope

In: the three fields, the selector and its budget pin, the renderer
branch, tests with the study's three example previews as fixtures.
Out: ANSI/HTML formatters (a later renderer over the same spans),
anchor-text or symbol-aware highlighting, a span-list wire field (fork:
carry both if a non-markdown renderer is ever real).

## Slices

- **A — model and selector**: fields on `Match`, `preview.py`, unit
  tests (whole-word vs substring, merged spans, fold offset map,
  head fallback, caps), the µs budget pin.
- **B — renderer and wiring**: the `glean` branch, backend fill-in,
  rank-order pin (a ranked result never renders path-sorted), docs
  (`docs/api.md` glean row and an example output).

## Landing criteria

- `scripts/ci.sh 3.13` green; the budget pin holds; the rank-order pin
  holds on the sqlite leg and one real engine.
- Landing note records the per-page cost and the worst-case token
  budget at the default caps.

## Landing note (2026-08-27)

**What landed.** Slice A: `Match.preview` / `preview_start` /
`preview_end` (the three travel together; the bounds are a validated
sub-range of `start..end`; grep never fills them);
`src/vfs/results/preview.py` — `select_preview(chunk_text,
chunk_line_start, terms)`, the density scorer exactly as decided (one
fold of the chunk, Σ over distinct terms of `log2(1 + len)` × whole-word
1.0 | substring 0.5, the capped extra-occurrence bonus, the adjacency
run bonus, a W = 4 window with the coverage bonus, earliest on ties,
merged `**…**` spans, 160-char lines trimmed around the first span,
480-char previews with the first line always kept, head window when no
term occurs); the display budgets as module constants, overridable as
keyword arguments. Slice B: the `glean` branch of `_render_body` —
rank order always (a header `path  score=0.8731`, a `path:start-end`
locator per region, the preview as `> ` quoted lines, a bare `>` for a
blank line; row-level projections fall to the Markdown table, also in
rank order — `_render_path_list` keeps sorting for every other op via
the shared `_render_rows`); a region with text but no preview renders
the head of its text, one with neither renders the locator alone.
Glean's default projection is now `("path", "score", "matches")` so the
previews show without asking. The backend fills every region from text
already in hand: the chunk row for index hits, and — new — the live
body the overlay already scored for overlay hits, whose `Match` now
spans the whole document (`start=1, end=<lines>`, `content=None`, the
preview alone) instead of the `(1, 1)` placeholder. `docs/api.md`
carries the glean row and an example page.

**Two things the study did not show.** (1) The lexical tokenizer splits
identifiers, so a query `line_start` arrives as `line_start`, `line`,
`start`; the bolder, being the superset by design, then bolds `line`
inside `newlines`. Correct to the contract, noisy for short terms — a
whole-word-only bolding mode is a one-constant fork if it grates.
(2) The study's 10–22 µs per chunk was measured on random chunks. A
result page is denser by selection — its chunks won on exactly these
terms — so a 10-entry × 3-region page on this repository's `src/` +
`context/research/` costs **1.3–1.8 ms** in Python (≈ 850 term
occurrences over ≈ 270 hit lines), 15–20 % of a 7–9 ms sqlite glean
call and a smaller share on a networked engine. Three passes brought it
from 2.2–2.8 ms (the any-term gate as one alternation regex; the fold
offset map only when folding changed the line's length; each term
walked over the whole folded chunk in C and bucketed by line, so the
Python work is proportional to occurrences). The rest is Python's floor
for that work; if the share ever matters the scan is a crate kernel's
shape. The budget pin (`tests/results/test_preview.py::TestBudget`)
holds at ≈ 20 µs per chunk on a study-shaped synthetic corpus (28-line
chunks, a term on one line in nine) against the 50 µs ceiling; the
implementation reproduces the study's three example previews
byte-for-byte and its per-query timings on the study corpus (11.7 /
22.6 / 24.7 / 10.0 / 4.0 µs for 1 / 3 / 6 terms / miss / empty).

**Token budget at the default caps.** Worst case per 10-entry page:
10 × (header ≈ 60 + 3 × (locator ≈ 50 + 480)) ≈ 16.5 k characters
≈ 4 k tokens. Measured on real pages: 9.1–11.2 k characters, ≈ 2.5–3 k
tokens, against ≈ 15 k tokens for the same page as raw chunks.

**Display budgets and `to_str`.** The caps live in
`vfs.results.preview` and are honoured by the backend at fill time.
Overriding them through `to_str` would need the query's folded terms on
the envelope (only the terms present in the index ride in
`lexical_stats`) — left as a fork: carry the terms, or re-cut from
`Match.content` with the renderer's head fallback.

**Gates.** `scripts/ci.sh 3.13`: 2,905 passed, 927 skipped, coverage
100.00 %, wheel under budget. The timing pin skips under an active
coverage tracer (the tracer alone makes it 12× slower — 239 µs a
chunk) and runs on the plain legs (`scripts/ci.sh 3.14`: 2,905 passed, 927 skipped, the 24 preview rows including the pin, no skip).
Postgres leg (Docker): **226 passed** — spec 132's 225 plus the
rank-order-and-preview row, which asserts in both worlds (overlay and
indexed) that the ranked text never renders path-sorted and every
region's preview is bolded and inside its own bounds. The other three
engine legs were not run this session; the row is engine-agnostic (it
reads the same `Match` rows the 225 already pin).

**Found by the walkthrough notebook (`examples/glean_walkthrough.ipynb`).**
A `paths=`-scoped call through the router came back with
`ops=("glean", "stat")`: the scope-root probe is a `stat` dispatched on
the verb's behalf, and `Result.merge` unions op names, so `result.op`
read `None` and the renderer fell to the cross-op table — path-sorted.
Pre-existing and wider than glean: a scoped `grep` lost its rg-style
lines the same way. Fixed in `_root_probe` (the probe's envelope
carries no op; it answers for the caller's verb) and pinned in
`tests/base/test_grep_namespace.py` for grep and glob.

**Residue.**

- Substring bolding of short split-identifier terms (above).
- `Preview.matched` distinguishes a bolded preview from the head
  fallback for callers; the wire carries only the text and bounds.
- A source line that already holds `**` renders `****term****` —
  Markdown-in-Markdown, unavoidable while the marker rides in the
  string (fork 5 of the memo: a span list beside the text if a
  non-Markdown renderer is ever real).
