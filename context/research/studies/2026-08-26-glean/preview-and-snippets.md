# Query-biased previews: snippet selection, keyword bolding, line numbers, and the result shape

- **Study for**: `../../2026-08-26-glean-brief.md` — question 12 (preview
  generation), gap 12 (preview without keywords), and the output half of
  gap 2 (entries, not chunks). Feeds the glean memo; commits us to nothing.
- **Date**: 2026-08-26
- **Sources** (reference checkouts under `~/Git/Repos`, read-only; commits
  as of this study):
  - `lucene` @ 091a987 — https://github.com/apache/lucene
    (`lucene/highlighter/src/java/org/apache/lucene/search/uhighlight/`,
    `.../highlight/package-info.java`, `.../vectorhighlight/package-info.java`)
  - `tantivy` @ 266a6c4 — https://github.com/quickwit-oss/tantivy
    (`src/snippet/mod.rs`)
  - `zoekt` @ a9206004 — https://github.com/sourcegraph/zoekt
    (`index/score.go`, `index/contentprovider.go`, `index/limit.go`,
    `api.go`, `doc/design.md`, `web/templates.go`)
  - `ripgrep` @ 435f59f — https://github.com/BurntSushi/ripgrep
    (`crates/core/flags/defs.rs`, `GUIDE.md`)
  - Turpin, Tsegay, Hawking & Williams, "Fast Generation of Result Snippets
    in Web Search", SIGIR 2007 — https://dl.acm.org/doi/10.1145/1277741.1277766
    (read from the author-uploaded PDF mirrored at
    https://boyter.org/static/abusing-aws-lambda/snippet/Fast_generation_of_result_snippets_in_web_search.pdf)
  - Sourcegraph, "Keeping it boring (and relevant) with BM25F" —
    https://sourcegraph.com/blog/keeping-it-boring-and-relevant-with-bm25f
  - GitHub, "The technology behind GitHub's new code search" —
    https://github.blog/engineering/the-technology-behind-githubs-new-code-search/;
    "GitHub code search is generally available" —
    https://github.blog/news-insights/product-news/github-code-search-is-generally-available/;
    "About GitHub Code Search" —
    https://docs.github.com/en/search-github/github-code-search/about-github-code-search
  - Google Search Central, "How to write meta descriptions / snippets" —
    https://developers.google.com/search/docs/appearance/snippet
  - OpenAI Help Center, "What are tokens and how to count them?" —
    https://help.openai.com/en/articles/4936856-what-are-tokens-and-how-to-count-them
  - vfs live tree: `src/vfs/models/entry.py`, `src/vfs/models/chunk.py`,
    `src/vfs/models/chunking.py`, `src/vfs/models/code_grams.py`,
    `src/vfs/storage/backends/database/grep.py`, `src/vfs/results/render.py`,
    `src/vfs/results/projection.py`, `src/vfs/results/envelope.py`,
    `src/vfs/base.py`, `context/decisions/007-fused-glean-search-surface.md`
- **Executed artifacts**: `preview-and-snippets/preview_proto.py` (the
  selector prototype and benchmark) and `preview-and-snippets/results.txt`
  (its output on this machine).

## Question

Glean returns top-*n* entries. Each entry must show its path, the relevant
line numbers, and a Google-style preview of its relevant chunks with the
query's keywords bolded — and the preview must be fast (R5). What do the
snippet-generation literature and the code-search tools do, what does
vfs's `Match`/`Observation`/`render.py` shape carry today, and what has to
change so the preview is (a) built only from chunk text the fused
statement already fetched, (b) O(chunk length), and (c) bounded in
characters/tokens — including the vector-only hit that has no keywords to
bold?

## Part A — the algorithms

### A.1 Turpin, Tsegay, Hawking & Williams (SIGIR 2007)

The paper is about the *engine* around snippet generation, and its
sentence scorer is deliberately simple. Figure 2, "Simple sentence ranker
that operates on raw text with one sentence per line", scores every
sentence `L = [w1..wm]` of a document with five features:

| feature | meaning |
| --- | --- |
| `h` | 1 if the sentence is a heading, else 0 |
| `ℓ` | 2 if it is the document's first line, 1 if the second, else 0 |
| `c` | number of `wi` that are query terms, **counting repetitions** |
| `d` | number of **distinct** query terms present |
| `k` | length of the longest **contiguous run** of query terms |

then "Use a weighted combination of c, d, k, h and ℓ to derive a score s",
inserts each sentence into a max-heap, and removes "the number of
sentences required from the heap to form the summary" — "the top two or
three returned as the snippet". The authors refuse to fix the weights:
"In order to avoid bias towards any particular scoring mechanism, we
compare sentence quality later in the paper using the individual
components of the score." Their Figure 6 shows that the *sentence
position* component (`h + ℓ`) is the one most disturbed by reordering and
that *distinct terms* (`d`) is the second — i.e. `d` is the feature that
actually carries query bias; `c` and `k` are tie-breakers.

The heritage is Tombros & Sanderson's *query-biased summarisation* and
Luhn's *significant sentences* ("a cluster of significant terms"): a
bracketed section of significant terms scores as (number of significant
words)² / (words in the sentence) — a density measure, which is what a
density-per-line scorer in vfs inherits.

Where the time goes (their Table 3, WT50G, 10 snippets per query,
whole-document processing): **Seek 45 ms, Read 4 ms, Score & Decode 21 ms**
— "the majority of time spent generating a snippet is in locating the
document on disk ('Seek'): 64% for whole documents, and 75% for half
documents." Their contribution — a semi-static word-level compression
(CTS) that lets query terms be matched as integers in the compressed
stream — cuts the scoring half by 58% (Table 2), and their caching
simulations show "if as little as 1% of the documents can be cached in
RAM ... then around 75% of seeks can be avoided."

**What transfers to vfs.** Nothing about the document fetch: vfs's fused
statement returns the chunk *row*, and the chunk's `content` column is on
that row (`rows.py:424` — `content` is `NOT NULL`), so the preview's input
is already in process memory with the ranking result. The whole Turpin
problem — the 64–75% of time spent finding the document — does not exist
for glean as long as the preview reads the chunk text it was handed and
**never issues a second content fetch**. What does transfer is the
scorer's shape: distinct-term coverage first, occurrence count and
adjacency as tie-breakers, position as a weak prior, a top-*k* of scored
units. Their 21 ms for ten documents' worth of scoring on a 2007 SPARC is
also the baseline the measurement below beats by four orders of magnitude
per document, on 2 KB chunks instead of 5.7 KB web pages.

### A.2 Lucene's UnifiedHighlighter (and its two predecessors)

`UnifiedHighlighter.java` states the algorithm in its class javadoc: it
"treats the single original document as the whole corpus, and then
scores individual passages as if they were documents in this corpus. It
uses a `BreakIterator` to find passages in the text; by default it breaks
using `getSentenceInstance(Locale.ROOT)`. It then iterates in parallel
(merge sorting by offset) through the positions of all terms from the
query, coalescing those hits that occur in a single passage into a
`Passage`, and then scores each Passage using a separate `PassageScorer`."

The pieces, from the source:

- **Passage formation** (`FieldHighlighter.highlightOffsetsEnums`): the
  comment reads "treat sentence snippets as miniature documents ... score
  each sentence as `norm(sentenceStartOffset) * sum(weight * tf(freq))`".
  A new passage opens when a term offset falls past the current passage's
  end; its bounds come from `breakIterator.preceding(...)` /
  `following(...)` around the *centre* of the match "so the result's
  length may be closer to fragsize". A bounded `PriorityQueue<Passage>`
  of size `maxPassages` keeps the top-*k*; ties break on start offset
  (earlier wins). Passages are finally re-sorted by
  `passageSortComparator` (offset order by default) for display.
- **Scoring** (`PassageScorer`): `k1 = 1.2`, `b = 0.75`, `pivot = 87`
  ("typical average english sentence length" in characters).
  `weight(contentLength, totalTermFreq)` is an IDF stand-in that
  "approximate[s] #docs from content length" as `1 + contentLength /
  pivot`; `tf(freq, passageLen)` is BM25 saturation with passage length
  normalised against the pivot; `norm(passageStart) = 1 + 1 /
  log(pivot + passageStart)` boosts early passages ("passages towards
  the beginning of the document are more useful for summarizing"). The
  file carries the honest comment "TODO: this formula is completely made
  up. It might not provide relevant snippets!" — the same refusal to
  claim a principled weighting Turpin makes.
- **Offsets sources** (`OffsetSource`): `POSTINGS` (offsets stored in
  the index), `TERM_VECTORS`, `ANALYSIS` (re-tokenise the stored text
  at highlight time), and combinations; `getOffsetSource` picks the
  cheapest available. `ANALYSIS` is the fallback everyone gets — which
  is the mode vfs is in, since the gram index stores no positions
  (brief: "exact-match only, no term frequencies, no positions").
- **Bounds**: `DEFAULT_MAX_LENGTH = 10000` characters of the field are
  considered at all; `maxPassages` per field; `maxNoHighlightPassages`
  — "the number of leading passages ... when no highlights could be
  found" — the *no-keyword fallback is the head of the text*, the same
  answer gap 12 wants.
- **Formatting** (`DefaultPassageFormatter`): `<b>`/`</b>` tags and a
  `"... "` ellipsis joining discontiguous passages; escaping is a
  formatter option.

The predecessors it unified: the original `Highlighter` (package doc:
"extract the most interesting sections of a piece of text and highlight
them, with the help of `Fragmenter`, fragment `Scorer`, and `Formatter`
classes") re-analyses the text per hit and is the slow, flexible one; the
`FastVectorHighlighter` ("fast for large docs ... highlight fields need
to be stored with Positions and Offsets ... take into account query boost
and/or IDF-weight to score fragments") trades index size for speed. The
Unified highlighter's contribution was to make the offset source a
runtime choice rather than three products. For vfs the lesson is that
the **re-analysis mode is the right one when the text is short and
already in hand** — a 2 KB chunk re-scans in microseconds (measured
below), so storing positions to avoid the scan would be speculative
generality.

### A.3 tantivy's SnippetGenerator

`src/snippet/mod.rs` is the smallest correct design in the set:

- `SnippetGenerator::create` collects the query's terms for one field
  and weights each `1.0 / (1.0 + doc_freq)` — a cheap IDF; terms absent
  from the index are dropped.
- `search_fragments` walks the tokenizer's stream once; a
  `FragmentCandidate` accumulates tokens until `next.offset_to -
  fragment.start_offset > max_num_chars` (default
  `DEFAULT_MAX_NUM_CHARS = 150`), then a new candidate starts *at the
  token that overflowed*. `try_add_token` adds the term's score and
  pushes the token's byte range to `highlighted` when
  `terms.get(&token.text.to_lowercase())` hits. Fragments with score 0
  are discarded. The doc comment allows overlapping candidates "to leave
  optimization opportunity to the fragment selector upstream".
- `select_best_fragment_combination` — despite the name — picks **one**
  fragment: `max_by` score, ties broken toward the *earlier* start
  offset (the comparator reverses `(start, stop)`), and rebases the
  highlight ranges to the fragment. No fragment → `Snippet::empty()`.
- Scoring is **sum of matched-term scores per occurrence** (repeats do
  add — the brief's "no bonus for repeats" is not quite right: each
  occurrence adds `score` again; there is no *extra* bonus beyond that
  and no distinct-term or adjacency feature). `collapse_overlapped_ranges`
  sorts, dedupes, and merges the highlight ranges before `to_html`
  wraps them in `<b>`; `set_snippet_prefix_postfix` swaps the tags.

The fixed-width character window scanned once is exactly the O(n)
selector vfs needs; the difference for code is that windows should align
to *lines*, not to a byte budget, because the caller wants line numbers.

### A.4 zoekt: line-level selection and per-file caps

zoekt's unit of display is the **line**, with optional context lines,
and its selection is a scored sort followed by a hard display cap.

- **Which lines**: `contentprovider.fillContentMatches` groups candidate
  matches by the line containing them (`newlines.atOffset`), extends the
  line range if a merged match crosses a newline, and fills
  `LineMatch{LineStart, LineEnd, LineNumber, Line, Before, After,
  LineFragments}` — `Before`/`After` are `numContextLines` lines on each
  side. `fillContentChunkMatches` / `chunkCandidates` is the newer shape:
  adjacent matches whose context windows would overlap are merged into
  one `ChunkMatch` with a `Ranges` list — the same "merge overlapping
  regions" grep's renderer does in vfs.
- **Line scoring** (`score.go:scoreLine`, classic mode): per line, the
  best single match wins, scored by *word boundary* (`scoreWordMatch =
  500`, `scorePartialWordMatch = 50`), *symbol* status (`scoreSymbol =
  7000` when the match is exactly a ctags symbol definition,
  `scorePartialSymbol` for edge/overlap), a per-language symbol-kind
  boost (`scoreSymbolKind`), and filename-base matches (`scoreBase =
  7000`). BM25 mode (`scoreLineBM25`) instead treats each match as a
  term and computes saturated tf with the line's length as the document
  length; `doc/design.md` explains it "rewards multiple term matches on a
  line" and skips IDF "to keep the implementation simple".
- **Ordering and caps**: `eval.go` calls `sortMatchesByScore` /
  `sortChunkMatchesByScore` per file (highest-scoring lines first), and
  `limit.go:NewDisplayTruncator` enforces `SearchOptions.MaxDocDisplayCount`
  ("Truncates the number of documents (i.e. files) after collating and
  sorting") and `MaxMatchDisplayCount` ("Truncates the number of matchs
  after collating and sorting"). `limitChunkMatches` trims a chunk's
  `Ranges`, its `SymbolInfo`, and its `Content` in lockstep, removing the
  trailing lines that the dropped ranges justified — the cap is a
  *budget across the whole result*, consumed file by file in rank order.
  `NumContextLines` is documented with the caveat that "the included
  context lines might contain matches and it's up to the consumer of the
  result to remove those lines."
- **Rendering** (`web/templates.go`): a line-number column
  (`<u>{{.LineNum}}</u>:`), before-context lines, the match line with
  each fragment as `{{LimitPre 100 .Pre}}<b>{{.Match}}</b>{{LimitPost 100
  .Post}}` — i.e. **100 characters of pre/post context around each bold
  span** — then after-context lines.

Sourcegraph's BM25F post confirms the two-tier use in production:
"Compute file-level BM25F to rank files by relevance to the query", then
"within each of those file results, compute line-level BM25F to determine
the most relevant chunks to display first", computing "the term
frequencies for each line, boosting matches on symbols, while using the
line's length in place of the usual file length in BM25 calculation";
symbols and filenames get a term-frequency boost of 5 versus content's
1, and "the final ranking is not too sensitive to the exact choice of
boost."

### A.5 ripgrep: the terminal-native contract

ripgrep's output contract is line-oriented and its knobs are the
vocabulary agents already know: `-C/--context NUM` "Show NUM lines before
and after each match" (with `-A`/`-B` partially overriding it — "-A2 -C1
is equivalent to -A2 -B1"), `-m/--max-count` "Limit the number of
matching lines", and `-M/--max-columns` "omit lines longer than this
limit in bytes. Instead of printing long lines, only the number of
matches in that line is printed" — with `--max-columns-preview` in the
guide's sample config ("Don't let ripgrep vomit really long lines to my
terminal, and show a preview"). Match lines join with `:` and context
lines with `-` (`path:N:text` / `path-N-text`), which vfs's
`_render_grep` already reproduces. The relevant lesson is the
**long-line cap**: a minified or generated line must not blow the
preview budget, and ripgrep's answer — truncate and say so — is the
right one for a token-bounded consumer.

### A.6 Synthesis

Every mature design converges on the same four decisions:

1. **Unit** — sentence (Turpin, Lucene), fixed char window (tantivy), or
   line (zoekt, ripgrep). Code wants lines: the consumer needs line
   numbers, and lines are what grep already renders.
2. **Score** — distinct-term coverage dominates; occurrence count and
   adjacency are tie-breakers; every implementation applies a positional
   prior (Turpin's `ℓ`, Lucene's `norm`, tantivy's earlier-wins tie);
   zoekt adds structural priors (symbol, word boundary) that vfs lacks
   the index for today.
3. **Selection** — a bounded top-*k* of units (heap or single max), then
   a display order (Lucene re-sorts by offset; zoekt by score).
4. **Bounds** — a character cap on the unit (150 tantivy, `pivot=87`
   Lucene, 100 pre/post zoekt), a count cap per document
   (`maxPassages`, `MaxMatchDisplayCount`), and a no-hit fallback to the
   head (Lucene's `maxNoHighlightPassages`).

## Part B — how code-search products render a ranked hit

- **GitHub code search.** The GA post describes results "organized by
  file, with the matching lines displayed in context", term highlighting
  in the code view, and a symbols pane; the engineering post says the
  backend must "double check each document (to validate matches and
  detect ranges for them) before scoring, sorting, and returning the
  requested number of results", that the query service aggregates shards,
  re-sorts by score, and returns "the top 100", and that "the GitHub.com
  front end then still has to do syntax highlighting, term highlighting,
  pagination". The docs cap the surface at "100 results (5 pages)" with
  no sort control. The rendered shape (public UI, not documented as a
  contract): repo/path header, then a handful of matching lines each
  with a line number and highlighted spans, with a "show more matches"
  affordance per file.
- **Sourcegraph.** Same shape — path header, ranked chunk matches with
  line numbers, bolded fragments, expandable context — plus the
  file-rank and symbol boosts above; zoekt's `web/templates.go` is the
  reference rendering (line-number column, bold fragments, 100-char
  pre/post trim).
- **Google web snippets.** The result is title / URL / description.
  Google's doc says "Snippets are designed to emphasize and preview the
  page content that best relates to a user's specific search. This means
  that Google Search might show different snippets for different
  searches" and "the snippet is truncated in Google Search results as
  needed, typically to fit the device width" (a `max-snippet:[number]`
  meta tag caps it); the usual ~155–160-character desktop figure is a
  community measurement of that pixel width, not a Google contract.
  Query-term bolding in the description is the visible convention the
  phrase "Google-style preview" in R5 refers to.

**What an LLM agent actually consumes.** The primary glean caller is an
agent over MCP reading `Result.to_str()` markdown. From a hit it uses
three things: the **path** (to `read` or `grep` next), the **line range**
(to read a window rather than the file), and a **short excerpt** to
decide whether to bother. Anything beyond that is paid for twice — once
in the model's context window, once in latency — and a 2 KB chunk is
roughly 500 tokens by OpenAI's published rule of thumb ("1 token ≈ 4
characters ... of English text"), so 10 entries × 3 raw chunks would be
~15k tokens for a single search. The preview must therefore be
**token-bounded by construction**: a character cap per line and per
preview, a line-count window, and a chunk count per entry, all with
defaults sized so a default `limit=10` result stays in the low
thousands of tokens. (Measured below: 4 lines × ≤160 chars, ≤480 chars
per preview, 3 previews per entry ⇒ ≤1,440 chars ≈ 360 tokens per entry
worst case, ≈3.6k tokens per 10-entry page, typically far less because
code lines are short.)

## Part C — vfs's result shape today and what must change

### C.1 Today

- `Match(start, end, match, content, score)` (`entry.py:334`): the
  docstring already anticipates glean — "`match` is grep's hit line
  (`None` when the whole region matched, as in a glean chunk hit)",
  "`score` is the region's own relevance (glean); the row-level
  `Observation.score` is the aggregate (max) across regions." Its
  `content` is "the region's own text", so "rendering a match never
  requires fetching the file."
- `Observation` (`entry.py:361`): `score`, `matches`, and the
  `populated` mask; no preview field.
- grep fills matches in `grep.py:376` — `Match(start=s, end=e, match=m,
  content=c)` per verified span (before/after context already folded
  into `start`/`end`) — and `_observe_hit` (`grep.py:796`) stamps `path`,
  `matches`, optional `score` (count mode), and the mask. Region text is
  the verifier's window; no bolding, no truncation.
- Rendering: `_render_body` special-cases grep, tree, read, stat, and the
  action verbs; **glean falls through to `_render_path_list`**, whose
  table path sorts rows **by path** (`sorted(result.observations, key=lambda
  x: x.path)`) — a ranked list would render alphabetised. The projection
  default is `("path", "score")` (`projection.py:48`); `_format_field`
  renders a `matches` list as `"start-end,start-end"` and floats to four
  decimals. `_render_grep` is the only renderer that walks `Match.content`
  per line (with the `:`/`-` separator convention). `Result.top(k)` sorts
  by `Observation.score`.
- ADR 007's asymmetry note pins that a parameter may select *what to
  answer*, never *how*; a preview knob (window size, char cap) is a
  rendering budget, not a strategy — it belongs on the render/projection
  side or as a backend default, not as a glean strategy selector.

### C.2 What must change

1. **One `Observation` per entry, carrying its top-K chunk regions as
   `Match` rows.** The fused statement ranks chunks; aggregation to
   entries (gap 2's other half — MaxP/SumP — is another study's call)
   yields, per entry, an ordered list of its contributing chunks. Each
   becomes `Match(start=chunk.line_start, end=chunk.line_end, match=None,
   content=<preview or chunk text>, score=<chunk score>)`. K defaults
   small (3) and is a bounded budget like zoekt's `MaxMatchDisplayCount`,
   not "all chunks that scored". `Observation.score` is the fused
   entry score; the chunk scores are comparable only within the entry.
2. **A `preview` on `Match`, distinct from `content`.** Two fields, two
   contracts: `content` stays the region's raw text (grep's contract —
   what `_render_grep` prints verbatim, what a caller slices by line
   number), while `preview: str | None` is the query-biased, bolded,
   truncated excerpt with its own `preview_start`/`preview_end` line
   bounds (1-indexed, absolute in the file — a sub-range of
   `start..end`). Overloading `content` with bolded, truncated text
   would break the "region's own text" promise and make grep and glean
   disagree on what the same field means. The projection vocabulary
   gains nothing new at the `Observation` level: `matches` already
   projects, and the renderer decides which of a match's fields to show.
3. **Bolding is markdown `**term**`.** Output is markdown
   (`_render_path_list`'s own docstring: "Markdown is the one textual
   format agents and chat UIs both parse reliably"), so the preview
   carries `**…**` spans; an ANSI or HTML renderer is a formatter
   concern layered on the same span list, exactly Lucene's
   `PassageFormatter` split. Two consequences to design in: (a) a
   preview that lands inside a fenced code block in the render must
   not be bolded there (markdown does not style inside fences) — the
   renderer either prints previews as quoted plain lines with bold
   markers, or prints the span list; (b) literal `*` in code needs no
   escaping for agents in practice, but the renderer should merge
   overlapping spans (tantivy's `collapse_overlapped_ranges`) so nested
   `**` never appears.
4. **A glean renderer.** `_render_body` gets a `glean` branch: rows in
   **rank order** (never path-sorted), a path header per entry with its
   score, then per match a `path:start-end` line-range line and the
   preview lines. Table mode stays available for row-level projections
   (`("path","score","updated_at")`), where `matches` renders as its
   `start-end` list as today.
5. **Vector-only previews** (gap 12): a hit with no lexical term present
   in the chunk — because the query had no lexical terms surviving
   folding, or because the vector leg alone surfaced the chunk — gets
   the **head of the top chunk**: the first W lines, same character
   caps, `preview_start = chunk.line_start`, no bold spans. This is
   Lucene's `maxNoHighlightPassages` and the natural-order baseline in
   Turpin. It is explicitly *not* an error or a warning: the envelope
   already carries tier/unembedded-count warnings (gap 9); the preview
   just degrades.
6. **"Fast" is a contract, stated in the docstring**: the preview is
   built only from the chunk `content` column the fused statement
   already returned (no second fetch, no `_content_for_entries`-style
   round trip); it is one pass over the chunk text with the query's
   folded terms (O(chunk length × terms) with a whole-chunk miss
   short-circuit); and it is capped by a declared line window and
   character cap. The measurement below is the evidence that this
   contract costs microseconds, not milliseconds.

### C.3 Folding and terms

The bolder must match what the lexical leg matched, or the preview will
claim hits the ranker never saw (and vice versa). Today's one shared fold
is `code_grams.fold_content` (Turkic-i pre-fold + `str.casefold`), and
the gram index stores a single folded stream; the lexical leg's term
tokenizer/stemmer is the lexical-leg study's decision. Whatever it picks,
the preview needs from it exactly one thing: **the list of folded query
terms** (post-stop-word, post-stem) plus a way to test a chunk token
against them. The prototype uses substring matching on the folded line
with a whole-word bonus (zoekt's `WordMatch` / `PartialWordMatch`
distinction), which is the right *superset* behaviour for a bolder — a
stem `embed` should bold `embedding` — and matches Match/fold semantics
grep already enforces (case-insensitive equality via `casefold`; index
map from folded offsets back to the original because folding can change
string length, e.g. `İ` → `i̇`).

## Executed measurement

`preview-and-snippets/preview_proto.py` — stdlib plus read-only calls to
`vfs.models.chunk.Chunk.split_batch` (the production splitter, default
`chunk_size = 2048` characters) and `vfs.models.code_grams.fold_content`.
Corpus: every UTF-8 text file under `src/`, `context/`, and `tests/` of
this repo, split into chunks and cycled to exactly 10,000 (mean 1,515
chars / 28.4 lines per chunk, median 1,670 / 29, max 2,048 / 119).
Python 3.13.11, arm64 (Apple silicon), `uv run`, best of three passes.

The selector: fold the whole chunk once (C-level `casefold`; newlines
survive folding so folded and original lines align), short-circuit to
the head if no term occurs anywhere, else score each line — Σ over
*distinct* terms present of `log2(1+len)` × (1.0 whole-word | 0.5
partial) + min(0.25 × extra occurrences, 1.0) + an adjacency run bonus —
slide a `W = 4`-line window, add 0.5 × distinct-terms-covered per
window, take the best window (earliest on ties), bold merged spans with
`**…**`, trim lines to 160 chars keeping the first bold span in view,
cap the preview at 480 chars.

| query | terms | µs / chunk | 10k chunks |
| --- | ---: | ---: | ---: |
| `embedding` | 1 | 10.6 | 106 ms |
| `chunk line_start embedding` | 3 | 21.9 | 219 ms |
| `reindex lease heartbeat epoch postings publish` | 6 | 22.1 | 221 ms |
| `zzqx` (term present nowhere → head fallback) | 1 | 9.1 | 91 ms |
| empty query (vector-only) | 0 | 3.3 | 33 ms |

**A 10-entry × 3-chunk result page (30 previews, 3-term query): 314 µs.**
The first, naive version of the same selector — folding every line
separately with an index map — cost 70–84 µs/chunk (1.9 ms per page);
folding once per chunk and building the map lazily, only for non-ASCII
lines that actually contain a term, is the 3–7× win, and it is what a
production implementation should do. Both are three to four orders of
magnitude under the fused statement's own round trip, so the preview
is never the thing to optimise; the only way to make it slow is a
second content fetch.

Three previews the prototype produced (3-term query `chunk line_start
embedding`; 6-term query for the third; line bounds are absolute file
lines; `**` is the bold marker):

```
/src/vfs/models/__init__.py:3-6  (chunk 1-37, score 8.20)
``entry`` holds the namespace ``Entry`` plus ``Observation``/``Match``;
``**chunk**``, ``version``, and ``edge`` are the entry-scoped metadata models,
one per table; ``rows``, ``vector``, ``versioning``, ``**chunk**ing``, and
``code_grams`` carry the supporting column, **embedding**, and content machinery.

/src/vfs/models/chunk.py:1-4  (chunk 1-56, score 6.96)
"""The ``**Chunk**`` model — one indexed unit of a file's content.

A **chunk** is entry-scoped metadata, not a namespace entry: its identity is
``(file, **chunk**_index)`` — the owning file's path plus its position in the

/src/vfs/models/rows.py:471-474  (chunk 442-482, score 25.06, 6-term query)
        # **Reindex** single-runner **lease**: holder token + last-**heartbeat** **epoch**
        # millis. NULL holder or a stale **heartbeat** means the **lease** is free.
        Column("**reindex**_holder", String(ULID_LENGTH)),
        Column("**reindex**_**heartbeat**", BigInteger),
```

and the vector-only fallback (no terms → head of the chunk, line bounds
still reported):

```
/src/vfs/__init__.py:1-4  (chunk 1-30, vector-only head)
__version__ = "0.0.22"

from vfs import permissions
from vfs.base import MountInfo, VirtualFileSystem
```

Two things the examples show that a spec should pin: partial-word
bolding (`**chunk**ing`, `**reindex**_holder`) is what a stem-tolerant
bolder produces and reads well for code identifiers; and the window
scorer prefers the *dense* 4-line region over the single best line — the
`rows.py` window covers five of six query terms across four lines, which
is the Turpin `d`-first behaviour.

## Bearing on vfs

**Recommendation.** Build the preview as a pure function over
`(chunk_text, chunk_line_start, folded_query_terms)` in
`src/vfs/results/` (it is a rendering concern that backends call, not a
storage concern), with the line-window density scorer above: distinct
terms first, occurrences and adjacency as tie-breakers, earliest window
on ties, `**…**` spans merged, per-line and per-preview character caps,
head-of-chunk fallback. Carry the result on `Match` as `preview` plus
`preview_start`/`preview_end`, next to the untouched `content`/`start`/
`end` contract. One `Observation` per entry with its top-K (default 3)
chunk `Match` rows ordered by chunk score; `Observation.score` is the
fused entry score. Add a `glean` branch to `_render_body` that prints in
rank order — path and score, then `path:start-end` and the preview lines
per match — and never path-sorts. Declare in the function's docstring
that the input is the fused statement's own chunk text and that no
second fetch is made. Costs: ~20 µs per chunk, ~0.3 ms per result page,
≈3.6k tokens per 10-entry page at the worst case of the default caps.

**Named forks for the memo/ADR:**

1. **Preview field placement** — a new `Match.preview` (+ bounds) beside
   `content` (recommended: keeps grep's raw-text contract) vs. reusing
   `Match.content` for the bolded excerpt (one field, but grep and glean
   would disagree on its meaning) vs. an `Observation.preview` string
   (one per entry; loses per-chunk line bounds).
2. **Unit of selection** — line window of W lines (recommended; line
   numbers fall out, matches grep's render) vs. tantivy-style character
   window (tighter token bound, but line bounds become approximate) vs.
   Lucene-style sentence break iterator (wrong unit for code).
3. **Score function** — the density scorer above (distinct-term
   coverage, whole-word bonus, adjacency) vs. a Lucene-style BM25-of-
   passages with IDF from the lexical leg's term statistics (better
   discrimination when the lexical leg *has* document frequencies; the
   preview then depends on the leg's index shape). Sourcegraph's finding
   that "the final ranking is not too sensitive to the exact choice of
   boost" argues for the simple scorer until the evaluation harness
   (gap 8) says otherwise.
4. **Where the defaults live** — window lines, per-line and per-preview
   char caps, and K chunks per entry as render-layer constants
   overridable by projection/`to_str` (recommended: they are display
   budgets, ADR 007-safe) vs. glean parameters (crosses into "how"
   territory) vs. backend config.
5. **Bold marker** — markdown `**…**` in the carried string
   (recommended; the wire is markdown) vs. carrying only span offsets
   and letting each renderer mark up (cleaner for ANSI/HTML, but every
   consumer of the raw `Result` then has to render). A span list *and*
   the markdown string is the belt-and-braces option if a non-markdown
   renderer is ever real.
6. **Whole-word vs. substring bolding** — substring with a whole-word
   score bonus (recommended; stem-tolerant, matches identifiers like
   `chunk_index`) vs. whole-word only (cleaner bolding, misses
   `embedding` for `embed`).
7. **Long-line policy** — trim to a cap keeping the first bold span in
   view with `…` (recommended, ripgrep's `--max-columns-preview` spirit)
   vs. drop the line and print a count (ripgrep's `-M` default).

## Sources

- Turpin, A., Tsegay, Y., Hawking, D., Williams, H. E. "Fast Generation
  of Result Snippets in Web Search." SIGIR 2007, pp. 127–134.
  https://dl.acm.org/doi/10.1145/1277741.1277766 — PDF read from the
  author upload mirrored at
  https://boyter.org/static/abusing-aws-lambda/snippet/Fast_generation_of_result_snippets_in_web_search.pdf
- Apache Lucene @ 091a987:
  `lucene/highlighter/src/java/org/apache/lucene/search/uhighlight/UnifiedHighlighter.java`,
  `FieldHighlighter.java`, `PassageScorer.java`, `DefaultPassageFormatter.java`;
  `.../search/highlight/package-info.java`;
  `.../search/vectorhighlight/package-info.java` —
  https://github.com/apache/lucene
- tantivy @ 266a6c4: `src/snippet/mod.rs` —
  https://github.com/quickwit-oss/tantivy
- zoekt @ a9206004: `index/score.go`, `index/contentprovider.go`,
  `index/limit.go`, `index/eval.go`, `api.go`, `doc/design.md`,
  `web/templates.go`, `README.md` — https://github.com/sourcegraph/zoekt
- ripgrep @ 435f59f: `crates/core/flags/defs.rs` (`-C`, `-M`, `-m`),
  `GUIDE.md` — https://github.com/BurntSushi/ripgrep
- Sourcegraph, "Keeping it boring (and relevant) with BM25F" —
  https://sourcegraph.com/blog/keeping-it-boring-and-relevant-with-bm25f
- GitHub Engineering, "The technology behind GitHub's new code search" —
  https://github.blog/engineering/the-technology-behind-githubs-new-code-search/
- GitHub, "GitHub code search is generally available" —
  https://github.blog/news-insights/product-news/github-code-search-is-generally-available/
- GitHub Docs, "About GitHub Code Search" —
  https://docs.github.com/en/search-github/github-code-search/about-github-code-search
- Google Search Central, snippet documentation —
  https://developers.google.com/search/docs/appearance/snippet
- OpenAI Help Center, "What are tokens and how to count them?" —
  https://help.openai.com/en/articles/4936856-what-are-tokens-and-how-to-count-them
- vfs live tree (this repo, working tree at study time):
  `src/vfs/models/entry.py`, `src/vfs/models/chunk.py`,
  `src/vfs/models/chunking.py`, `src/vfs/models/code_grams.py`,
  `src/vfs/models/rows.py`, `src/vfs/storage/backends/database/grep.py`,
  `src/vfs/results/render.py`, `src/vfs/results/projection.py`,
  `src/vfs/results/envelope.py`, `src/vfs/base.py`,
  `context/decisions/007-fused-glean-search-surface.md`
- Executed: `preview-and-snippets/preview_proto.py`,
  `preview-and-snippets/results.txt`
