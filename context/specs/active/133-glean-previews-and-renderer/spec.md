# 133 — previews and the glean renderer: `Match.preview` with line bounds, bolded terms, rank-ordered output

- **Status:** ready — drafted 2026-08-26 from ADR 052 pin 7. Fourth of
  the glean arc; small and self-contained on top of spec 132's rows.
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
