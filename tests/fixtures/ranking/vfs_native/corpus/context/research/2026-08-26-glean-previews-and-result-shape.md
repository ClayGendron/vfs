# glean previews and the result shape: entries out, query-biased excerpts, line numbers, bolded terms

- **Status**: research memo — design input for the glean spec's result
  section (and, if the field placement is contested, one ADR line). One
  of five memos from the 2026-08-26 glean research leg (brief:
  [2026-08-26-glean-brief.md](2026-08-26-glean-brief.md)). Companions:
  [fusion and cross-mount merge](2026-08-26-glean-fusion-and-cross-mount-merge.md)
  (which chunks per entry come back),
  [glean in the engine](2026-08-26-glean-in-the-engine.md) (the
  statement that returns them),
  [ranking signals and the ranker API](2026-08-26-glean-ranking-signals-and-ranker-api.md),
  [the embedding seam](2026-08-26-glean-embedding-seam.md). Commits us
  to nothing.
- **Date**: 2026-08-26
- **Owner**: Clay Gendron
- **Question**: Glean returns top-*n* entries. Each must show its path,
  the relevant line numbers, and a Google-style preview of its relevant
  chunks with the query's keywords bolded, and the preview must be fast.
  What do the snippet literature and the code-search tools do, what does
  vfs's `Match`/`Observation`/`render.py` carry today, and what must
  change — including for a vector-only hit with no keyword to bold?
- **Evidence gathered**: the preview study
  ([studies/2026-08-26-glean/preview-and-snippets.md](studies/2026-08-26-glean/preview-and-snippets.md)):
  Turpin et al. SIGIR 2007, Lucene's UnifiedHighlighter, tantivy's
  SnippetGenerator, zoekt's line selection and display caps, ripgrep's
  contract, GitHub/Sourcegraph/Google rendering, and an executed
  prototype selector timed on 10,000 real chunks from this repository.
- **Headline**: Every mature design converges on four decisions — a
  unit (line, for code), a coverage-first score (distinct query terms,
  then occurrences and adjacency, with a weak positional prior), a
  bounded top-*k* of units, and hard character caps with a head-of-text
  fallback. The Turpin problem (64–75 % of snippet time is *finding the
  document*) does not exist for glean as long as the preview reads the
  chunk text the fused statement already returned and never issues a
  second fetch. The prototype costs **10–22 µs per chunk and 314 µs for
  a 10-entry × 3-chunk page** — three orders of magnitude under the
  statement's round trip. What must change in the tree: one
  `Observation` per entry carrying its top-K chunk `Match` rows; a new
  `Match.preview` with its own line bounds beside the untouched
  `content` contract; markdown `**term**` bolding with merged spans; a
  `glean` branch in `_render_body` that prints in rank order — today
  glean falls through to `_render_path_list`, which **sorts by path**,
  so a ranked result would render alphabetised.

---

## 1. What the caller uses

The primary glean caller is an LLM agent over MCP reading
`Result.to_str()` markdown. From a hit it uses three things: the
**path** (to `read` or `grep` next), the **line range** (to read a
window rather than the file), and a **short excerpt** to decide
whether to bother. Anything more is paid for twice — in the context
window and in latency. A 2 KB chunk is ~500 tokens, so 10 entries × 3
raw chunks would be ~15k tokens for one search. The preview must be
token-bounded *by construction*: a character cap per line and per
preview, a line window, and a chunk count per entry, sized so a default
`limit=10` page stays in the low thousands of tokens.

## 2. What the field does

- **Turpin, Tsegay, Hawking & Williams (SIGIR 2007)** score every
  sentence with five features — heading, first/second line, query-term
  count with repeats, *distinct* query terms, longest contiguous run —
  into a max-heap; their Figure 6 shows distinct-term coverage is the
  feature that carries query bias; the rest are tie-breakers. Their
  cost is dominated by seek (64–75 %), which vfs avoids because the
  chunk `content` column rides on the fused row.
- **Lucene UnifiedHighlighter** treats the document as a corpus and
  scores passages "as if they were documents": `BreakIterator`
  sentences, a BM25-shaped `PassageScorer` (`pivot = 87` chars, an
  early-position norm, and the honest comment "this formula is
  completely made up"), a bounded `maxPassages` priority queue, and
  `maxNoHighlightPassages` — the **no-keyword fallback is the head of
  the text**. Its re-analysis offset mode is the right one when the
  text is short and already in hand; storing positions to avoid a 2 KB
  scan would be speculative generality.
- **tantivy SnippetGenerator**: one pass over the token stream, 150-char
  windows, score = sum of matched-term scores per occurrence, one best
  fragment, earliest wins ties, highlight ranges merged before
  rendering. The O(n) fixed-window selector vfs needs — except code
  wants **line**-aligned windows, because the caller wants line numbers.
- **zoekt**: line-level scoring with word-boundary and symbol boosts,
  `MaxMatchDisplayCount` as a *budget across the whole result* consumed
  file by file in rank order, 100 chars of pre/post context per bold
  span in the web template; Sourcegraph's BM25F post confirms the
  two-tier file-then-line scoring and that "the final ranking is not
  too sensitive to the exact choice of boost".
- **ripgrep**: `-C` context lines, `-m` max count, and `-M
  --max-columns-preview` — a minified line must not blow the budget;
  truncate and say so.
- **Products**: GitHub and Sourcegraph render path → N matching lines
  with line numbers and highlighted spans; Google's snippet is a
  query-biased, truncated description with bolded terms — the visible
  convention "Google-style preview" names.

## 3. vfs today, and what must change

Today: `Match(start, end, match, content, score)` already anticipates
glean — `match=None` "when the whole region matched, as in a glean chunk
hit", per-region `score`, `content` as "the region's own text" so
"rendering a match never requires fetching the file"
(`src/vfs/models/entry.py:334`); `Observation` has no preview field;
grep fills matches in `grep.py:376` and `_observe_hit`; `_render_body`
special-cases grep/tree/read/stat and **glean falls through to
`_render_path_list`, whose table path sorts by path**; the projection
default is `("path", "score")`.

1. **One `Observation` per entry, carrying its top-K chunk regions as
   `Match` rows** — `Match(start=chunk.line_start, end=chunk.line_end,
   match=None, content=<chunk text>, score=<chunk score>)`, K a bounded
   budget (default 3), `Observation.score` the fused entry score, chunk
   scores comparable only within the entry. The fusion memo's
   aggregate-then-fuse statement yields the top-K chunks per winning
   entry in the same pass.
2. **A `preview` on `Match`, distinct from `content`**: `preview: str |
   None` plus `preview_start`/`preview_end` (1-indexed, absolute file
   lines, a sub-range of `start..end`). Two fields, two contracts —
   `content` stays raw (grep's contract; what a caller slices by line
   number), `preview` is the query-biased, bolded, truncated excerpt.
   Overloading `content` would make grep and glean disagree on what one
   field means.
3. **Bolding is markdown `**term**`** (the wire is markdown; an ANSI or
   HTML renderer is a formatter concern over the same spans — Lucene's
   `PassageFormatter` split). Merge overlapping spans so nested `**`
   never appears; print previews as quoted plain lines, never inside a
   fenced block (markdown does not style inside fences).
4. **A `glean` branch in `_render_body`**: rows in **rank order**, a
   path header with the score, then per match a `path:start-end` line
   and the preview lines; table mode stays for row-level projections
   where `matches` renders as its `start-end` list as today.
5. **Vector-only previews**: a hit with no lexical term in the chunk
   gets the **head of the top chunk** — first W lines, same caps,
   `preview_start = chunk.line_start`, no spans. Lucene's
   `maxNoHighlightPassages`; explicitly not a warning — tier and
   unembedded-count records already carry honesty.
6. **"Fast" is a docstring contract**: built only from the chunk text
   the fused statement returned (no second fetch), one folded pass over
   the chunk with the query's terms (a whole-chunk miss short-circuits
   to the head), hard caps on lines and characters.

**Folding and terms.** The bolder must match what the lexical leg
matched or the preview claims hits the ranker never saw. It takes
exactly one thing from the lexical index: the list of folded query terms
(the engine memo's tokenizer — `fold_content`'s Turkic-i pre-fold +
`casefold`, identifier splitting, no stemming). Substring matching on
the folded line with a whole-word bonus is the right *superset*
behaviour — `embed` bolds `embedding`, `chunk` bolds `chunk_index` —
with an index map from folded offsets back to the original because
folding can change string length.

## 4. Measured

`preview-and-snippets/preview_proto.py`, stdlib plus read-only calls to
`Chunk.split_batch` and `fold_content`; 10,000 chunks from `src/`,
`context/`, `tests/` (mean 1,515 chars / 28 lines); Python 3.13, Apple
Silicon. The selector folds the whole chunk once, short-circuits to the
head if no term occurs, else scores each line — Σ over *distinct* terms
present of `log2(1+len)` × (1.0 whole-word | 0.5 partial) + a capped
occurrence bonus + an adjacency bonus — slides a 4-line window with a
coverage bonus, takes the best (earliest on ties), bolds merged spans,
trims lines to 160 chars keeping the first bold span in view, caps the
preview at 480 chars.

| query | terms | µs / chunk | 10k chunks |
|---|---:|---:|---:|
| `embedding` | 1 | 10.6 | 106 ms |
| `chunk line_start embedding` | 3 | 21.9 | 219 ms |
| `reindex lease heartbeat epoch postings publish` | 6 | 22.1 | 221 ms |
| absent term → head fallback | 1 | 9.1 | 91 ms |
| empty query (vector-only) | 0 | 3.3 | 33 ms |

**A 10-entry × 3-chunk page: 314 µs.** Folding once per chunk (not per
line) was the 3–7× win over the naive version. Token budget at the
default caps: ≤ 480 chars × 3 previews ≈ 360 tokens per entry worst
case, ≈ 3.6k tokens per 10-entry page, typically far less. Example
previews (bold spans, absolute line bounds, partial-word bolding on
identifiers) are in the study.

## 5. Recommendation for the spec

Build the preview as a pure function over `(chunk_text,
chunk_line_start, folded_query_terms)` in `src/vfs/results/` (a
rendering concern backends call, not a storage concern) with the
line-window density scorer above; carry it on `Match` as `preview` +
bounds beside the untouched `content`/`start`/`end`; one `Observation`
per entry with its top-K chunk `Match` rows in chunk-score order; a
rank-ordered `glean` renderer; head-of-chunk fallback; display budgets
(window lines, per-line and per-preview char caps, K) as render-layer
constants overridable by projection/`to_str` — display budgets are
ADR-007-safe, glean parameters would not be.

## 6. Forks

1. **Preview field placement** — `Match.preview` + bounds (recommended)
   vs reusing `Match.content` (grep/glean would disagree) vs an
   `Observation.preview` (loses per-chunk line bounds).
2. **Unit** — line window (recommended) vs tantivy-style char window vs
   sentence break iterator (wrong unit for code).
3. **Score** — the density scorer (recommended until the harness says
   otherwise; Sourcegraph: boosts barely matter) vs a Lucene-style
   BM25-of-passages using the lexical leg's document frequencies.
4. **Where defaults live** — render-layer constants (recommended) vs
   glean parameters vs backend config.
5. **Bold marker** — markdown in the carried string (recommended) vs a
   span list only vs both.
6. **Whole-word vs substring bolding** — substring with a whole-word
   bonus (recommended).
7. **Long lines** — trim keeping the first span in view with `…`
   (recommended) vs drop and count (ripgrep `-M`).

## Sources

Study (this repo): `studies/2026-08-26-glean/preview-and-snippets.md`
with `preview-and-snippets/preview_proto.py` and `results.txt`.

Turpin, Tsegay, Hawking & Williams, SIGIR 2007
(https://dl.acm.org/doi/10.1145/1277741.1277766); Lucene @ 091a987
(`uhighlight/{UnifiedHighlighter,FieldHighlighter,PassageScorer,DefaultPassageFormatter}.java`);
tantivy @ 266a6c4 (`src/snippet/mod.rs`); zoekt @ a9206004
(`index/{score,contentprovider,limit,eval}.go`, `web/templates.go`);
ripgrep @ 435f59f (`crates/core/flags/defs.rs`, `GUIDE.md`);
Sourcegraph BM25F post
(https://sourcegraph.com/blog/keeping-it-boring-and-relevant-with-bm25f);
GitHub code search posts
(https://github.blog/engineering/the-technology-behind-githubs-new-code-search/);
Google Search Central snippets
(https://developers.google.com/search/docs/appearance/snippet); vfs
live tree: `src/vfs/models/entry.py`, `src/vfs/results/{render,projection,envelope}.py`,
`src/vfs/storage/backends/database/grep.py`.
