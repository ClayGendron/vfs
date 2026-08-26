# Study: the lexical leg — BM25 over our own tables vs engine full-text, tokenization for code, passage-to-entry aggregation

- **Study for**: [2026-08-26-glean-brief.md](../../2026-08-26-glean-brief.md),
  questions 2 (lexical index: engine FTS or our own tables?) and 6
  (passage-to-entry aggregation), plus gap 1 (freshness) on the lexical
  side. The engine-matrix study verifies engine FTS on real engines; this
  study does the design and the portable-table pricing.
- **Date**: 2026-08-26
- **Sources** (reference checkouts read-only, cited by commit; nothing
  copied):
  - `~/Git/Repos/bm25s` @ a213158 (2026-08-24, MIT) —
    <https://github.com/xhluca/bm25s>
  - `~/Git/Repos/lucene` @ 091a987 (2026-08-26, Apache-2.0) —
    <https://github.com/apache/lucene>
  - `~/Git/Repos/tantivy` @ 266a6c4 (2026-08-19, MIT) —
    <https://github.com/quickwit-oss/tantivy>
  - `~/Git/Repos/zoekt` @ a9206004 (2026-08-26, Apache-2.0) —
    <https://github.com/sourcegraph/zoekt>
  - `~/Git/Repos/pyserini` @ 71072b4 (2026-08-22, Apache-2.0) —
    <https://github.com/castorini/pyserini>
  - Papers and docs by URL in *Sources* at the end.
- **Executed experiment**: scripts and raw results under
  [`lexical-leg/`](lexical-leg/) — `build_and_time.py` (project
  interpreter, builds the portable tables in sqlite from a real corpus
  split by vfs's own `Chunk.split_batch`) and `compare_bm25s.py` (a
  throwaway venv with bm25s 0.3.11, never the project venv). Apple
  Silicon laptop, Python 3.13, SQLite 3.50.4 in-memory, plain `sqlite3`
  for the statement harness.

---

## Question

The gram index gives grep an exact-match candidate set with no term
frequencies and no ranking. `glean` needs a *ranked* lexical leg that
(a) produces BM25-quality scores, (b) runs as one statement per mount on
Postgres, MariaDB, MySQL, SQL Server, Oracle, and SQLite, (c) accepts the
glob scope as an allow-list *before* scoring, (d) joins into the fused
RRF statement, (e) ranks chunks but returns entries, and (f) says
honestly what it serves between a write and the next reindex. Two
candidates: each engine's native full-text ranking, or a portable
`(term, chunk, tf|weight)` table — the gram index's sibling — scored with
`SUM(...) GROUP BY chunk_id` in plain SQL.

## Findings by theme

### 1. BM25 variants: which one, and does it matter?

**The record says the variant does not matter; the tokenizer does.**
Kamphuis, de Vries, Boytsov and Lin (ECIR 2020) compared eight BM25
variants — Robertson original, Lucene default (lossy one-byte length),
Lucene accurate (exact length), ATIRE, BM25L, BM25+, BM25-adpt, and
TF_l∘δ∘p×IDF — on Robust04, Core17 and Core18 with `k1=0.9, b=0.4`. AP
spread on Robust04 is .2516–.2571; ANOVA and Tukey's HSD find no
significant difference between any pair, on any collection. Their
closing line: "Does it matter? ... the answer appears to be 'no, it
does not'." They add that "differences due to more mundane settings
(such as the choice of stopwords) are often larger than the differences
we observe here", and that Lucene's lossy length approximation buys
negligible time (52 vs 55 ms/topic) so exact lengths would be the better
default. Two details matter for us:

- **They ran the study in a relational database.** The Lucene index was
  exported to MonetDB ("OldDog", after Mühleisen, Samar, Lin and de
  Vries, SIGIR 2014) and each variant was "expressed declaratively" as
  a variation on one SQL query over term/document tables; they verified
  the SQL reproduces Anserini's output "setting aside unavoidable
  differences related to floating point precision". BM25-in-SQL over a
  term table is therefore a *published, reproduced method*, not a hack.
- **The (k1+1) factor is cosmetic.** ATIRE multiplies the TF component
  by (k1+1) "to make it look more like the classic RSJ weight; this has
  no effect on the resulting ranked list, as all scores are scaled
  linearly". Lucene ≥ 8 dropped it. Any spelling we pick ranks the same;
  only absolute score values differ — which matters for nothing in an
  RRF design (rank-only) and for cross-mount merge only if scores were
  ever compared raw (the brief's R3 says they should not be).

**What the deployed implementations actually compute** (read in the
checkouts):

| implementation | IDF | TF component | length | defaults |
|---|---|---|---|---|
| Lucene `BM25Similarity` (`lucene/core/.../similarities/BM25Similarity.java`) | `log(1 + (N − n + 0.5)/(n + 0.5))` — never negative | `freq / (freq + k1·(1 − b + b·dl/avgdl))`, no (k1+1) | one-byte `SmallFloat` norm, 256-entry cache | k1 = 1.2, b = 0.75 |
| tantivy `src/query/bm25.rs` | identical to Lucene | `idf·(k1+1)` folded into the weight, same saturation | 256-entry fieldnorm cache, same lossy scheme | `const K1 = 1.2, B = 0.75` (not tunable at query time) |
| bm25s `bm25s/scoring.py` | `method="lucene"` (default): Lucene's; also robertson (clamped at 0 unless `allow_negative`), atire `log(N/df)`, bm25l, bm25+ | `_score_tfc_lucene` = robertson form without (k1+1); atire adds it | exact token counts | k1 = 1.5, b = 0.75 |
| pyserini `LuceneSearcher.set_bm25` | Lucene's | Lucene's | Lucene's | **k1 = 0.9, b = 0.4** (Anserini's, tuned on newswire) |
| zoekt `index/score.go` | **constant** — "we treat the inverse document frequency (idf) as constant. This is supported by our evaluations which showed that for keyword style queries, idf can down-weight the score of some keywords too much" | `((k+1)·f)/(k·(1−b+b·L)+f)` with `f` a BM25F term frequency (filename/symbol matches count ×5; test/vendor files ÷5) | **bytes**, `L = fileLength/averageFileLength`; per-line scoring uses line bytes / 100 | k = 1.2, b = 0.75 |

**bm25s's shape is the table's shape.** bm25s does not score at query
time: `build_index_from_ids` precomputes `idf(t) · tfc(tf, dl)` for
every `(token, doc)` pair once and stores it as a CSC sparse matrix
(`data/indices/indptr` arrays, saved as `data.csc.index.npy` etc.);
`get_scores` is a gather-and-sum over the query's columns. A SQL table
`lex_terms(term, chunk_id, weight)` with `SUM(weight) ... GROUP BY
chunk_id` is exactly that matrix with the term as the column key. The
eager precomputation is legal because idf and avgdl are corpus
constants of one build — for us, of one *epoch*.

**Recommendation for the formula: Lucene-accurate.** Lucene's IDF
(non-negative by construction, so no clamping rule), exact document
length (Kamphuis's own suggestion; we have the integer, there is no
byte to save), `(k1+1)` included so single-term scores read as
`idf·something ≤ (k1+1)·idf` (Lucene-classic/ATIRE spelling — matches
zoekt's and Sourcegraph's published pseudocode). Defaults **k1 = 1.2,
b = 0.75**: Lucene's, tantivy's, FTS5's, zoekt's; pyserini's 0.9/0.4 is
a newswire tuning with no code-corpus evidence behind it. Both live in
the epoch's `options_hash` so a retune forces a rebuild, never a mixed
index.

### 2. A portable lexical index in plain SQL vs engine full-text

**The engine FTS landscape is five incompatible scores** (docs; the
engine-matrix study verifies on the Docker legs):

| engine | primitive | what the score is | BM25? | scope before scoring | joins into an RRF CTE | freshness |
|---|---|---|---|---|---|---|
| Postgres | `tsvector` + GIN, `ts_rank_cd` | cover density (Clarke, Cormack, Tudhope 1999) over term positions with document-length normalization bits; the docs: "the ranking functions do not use any global information" — **no IDF** | no — BM25 needs an extension (ParadeDB `pg_search`, VectorChord-BM25, Timescale `pg_textsearch`), none assumable on a managed instance | yes (WHERE + GIN) | yes | synchronous (GIN pending list) |
| SQLite | FTS5 `bm25()` | real BM25 with Lucene's IDF, "k1 and b are both constants, hard-coded at 1.2 and 0.75", result "multiplies ... by -1", per-column weights | yes | `rowid IN (...)` beside the MATCH | yes | synchronous (a b-tree per committed transaction, `automerge` 4 / `crisismerge` 16) |
| MySQL / MariaDB | InnoDB FULLTEXT, `MATCH ... AGAINST` | the docs' formula is `rank = TF · IDF · IDF` with `IDF = log10(N/df)`; **no length normalization, no saturation**; `innodb_ft_min_token_size` (default 3) and a built-in stop list | no | yes (WHERE) | yes | synchronous, with an FTS cache flushed on `OPTIMIZE TABLE` |
| SQL Server | `CONTAINSTABLE` / `FREETEXTTABLE` `RANK` | ordinal 0–1000 whose "actual values are unimportant and typically differ each time the query runs"; CONTAINSTABLE: `HitCount · 16 · log2((2 + N)/n) / MaxOccurrence` with document length bucketed into 32 ranges (a 50-word and a 100-word row "are treated the same"); FREETEXTTABLE: genuine Okapi BM25 (k1 = 1.2, b = 0.75, k3 = 8) but over inflectional and thesaurus expansions "treated as separate words", not switchable off | FREETEXTTABLE only, with expansion baked in | yes (join on `KEY`) | yes | **asynchronous population** — rank statistics "vary in accuracy if the intermediate indexes aren't merged" |
| Oracle | CONTEXT index, `SCORE()` | "inverse frequency algorithm based on Salton's formula", 0–100; "inserting, updating or deleting documents is likely to change the score" and "perfect relevance ranking is obtained by running a query right after optimizing the index" | no | yes | yes | manual / on-commit / interval `SYNC` |

Every column but "joins into a CTE" is a portability loss. Two are
fatal for the brief's requirements: (i) **R3, cross-mount merge** —
rank-only fusion survives score incompatibility, but a mount on
MySQL ranks by unsaturated TF-IDF while its sibling on SQLite ranks by
BM25, so the *rankings themselves* are of different quality and the
merge is dishonest in a way no normalization fixes; (ii) **gap 8,
determinism** — a conformance suite cannot pin stable top-*n* across
engines when the engines disagree on the order. Tokenization is also
engine-owned (MySQL's min-token 3 drops `os`, `fd`, `id`; FTS5's
`unicode61` splits on `_` unless `tokenchars` is set; Postgres's parser
has its own opinions about `foo_bar` and `foo.bar`) so the query-side
tokenizer would need a per-engine twin — exactly the drift the gram
index was built to avoid.

**The portable table.** The gram index's sibling, epoch-scoped and
published by the same pointer flip:

```
lex_docs (epoch, chunk_id, entry_id, dl)          PK (epoch, chunk_id); index (epoch, entry_id)
lex_terms(epoch, term, chunk_id, tf, weight)      PK (epoch, term, chunk_id)   -- weight = idf·tfc, precomputed
lex_df   (epoch, term, df, idf)                   PK (epoch, term)
lex_stats(epoch, n_docs, avg_dl)                  PK (epoch)
```

The PK order `(epoch, term, chunk_id)` makes each term's rows a
contiguous run of the B-tree — a posting list stored as rows instead of
a blob. Scoring is one statement:

```sql
SELECT t.chunk_id, SUM(t.weight) AS score
FROM   lex_terms t
WHERE  t.epoch = :epoch AND t.term IN (:t1, :t2, ...)          -- ≤ membership budget; a query has tens of terms
GROUP  BY t.chunk_id
ORDER  BY score DESC, t.chunk_id
LIMIT  :n
```

Arithmetic, `IN`, `GROUP BY`, `ORDER BY`, `LIMIT` — every declared
dialect has them, and `GENERIC` serves it unchanged. Glob scope joins
*inside* the statement, two ways: an id allow-list as a semi-join
(`t.chunk_id IN (SELECT chunk_id FROM lex_docs WHERE entry_id IN
(:ids))`, chunked under the membership budget with a client merge —
the ids grep materializes today) or, better, the segments
table itself (`JOIN segments sg ON sg.entry_id = sd.entry_id AND
sg.segment = :seg`), which keeps the whole allow-list server-side with
zero id binds — the first vfs index where scope pushdown never leaves
the engine, because grep's allow-list only comes back to the client to
intersect with numpy-decoded posting *blobs*, and here there are no
blobs. Liveness rides the same join (`entry.deleted_at IS NULL`,
`entry.encoded`), and the whole thing is a CTE the fused statement can
reference. Per-entry aggregation (§4) wraps it.

**Fidelity is exact** (executed, §Experiment): top-10 overlap 1.0 and
Kendall τ 1.0 against bm25s on 45 queries; the score ratio is exactly
2.2 = (k1+1), the cosmetic factor.

**Update cost under the epoch discipline.** The index is a regenerable
cache rebuilt whole per reindex, like the postings — a 10,000-file
dirty batch costs the corpus rebuild, which the executed numbers price
at roughly 3.5–4.5 s per 1,000 files of pure-Python tokenization +
executemany on sqlite (§Experiment). The pure-Python tokenizer is the
floor to move: the gram builder's precedent (Rust `PostingsBuilder`
behind `vfs.native`) applies verbatim — feed folded bytes, drain
`(term, chunk_id, tf, weight)` rows in byte-capped batches under
`insertmanyvalues`. Incremental maintenance (delete + reinsert one
entry's rows through a chunk-keyed secondary index the rebuild never
needs, +70 % table bytes) measured **97 s for 1,000 entries at 11,608
chunks** — 6.7 s at 2,690 chunks, so it grows with the table, not just
with the batch — against 4 s to rebuild the same 1,024-file corpus
whole. Row-wise maintenance of a term table is the wrong shape on
sqlite and would need per-engine tuning elsewhere; the epoch rebuild
is the fork to keep.

**Size.** Measured 2.0–2.8× the content bytes with the term text on
every row; integer term ids cut the posting table by 22 % at the price
of a term→id lookup (one small IN-select) per query. Both are far above
the gram posting blobs' ratio but of the same order as any inverted
index that keeps tf; the `weight` REAL can become a `tf` SMALLINT with
the formula evaluated at query time (§Experiment: 2–3× slower
statement, three joins) if bytes ever matter more than latency.

### 3. Tokenization for a corpus that is mostly code

**What the field does:**

- **Lucene/Elasticsearch** — the canonical identifier splitter is
  `WordDelimiterGraphFilter` (`lucene/analysis/common/.../miscellaneous/`)
  with `SPLIT_ON_CASE_CHANGE | SPLIT_ON_NUMERICS | PRESERVE_ORIGINAL`:
  `camelCase → camel, Case (+ camelCase)`; Elastic's docs warn to pair it
  with the `keyword`/`whitespace` tokenizer, not `standard`, because a
  punctuation-stripping tokenizer destroys the delimiters first.
- **tantivy** — `SimpleTokenizer` splits on every non-alphanumeric
  character (so `_` is a delimiter — `pthread_create → pthread, create`,
  the whole identifier is *lost*); no case-change splitter; filters for
  lowercase, ASCII folding, Snowball stemming, stop words, `RemoveLong`,
  and a dictionary-based `SplitCompoundWords` (German nouns, not code).
  No code tokenizer ships.
- **zoekt / Sourcegraph** — no index-time tokenization at all; each
  query "induces" a tokenization by substring match, term frequency is
  counted from the candidate matches (`calculateTermFrequency` keys on
  the *lowered* matched substring), so `create pthread` hits
  `pthread_create()` and `thread_create` does too. IDF is treated as a
  constant (see §1); the blog concedes it "does make it trickier to
  calculate the inverse document frequency" and calls search-time df
  estimation "not insurmountable". BM25F boosts: filename or symbol
  match ×5 on the term frequency, chosen "by comparing a tiny grid of
  options" and "not too sensitive to the exact choice"; test/generated/
  vendor files ÷5. Line-level BM25F (line bytes / 100 as length) picks
  the chunk to display — the preview problem solved by the same
  formula.
- **GitHub Blackbird** — sparse ngram (not fixed trigram) indices over
  content, symbols and paths; ranking is not published beyond "k-merges
  the posting lists by score so relevant documents have lower IDs"; no
  BM25 term index is described.

**Recommendation.** One tokenizer, owned beside `code_grams.py` and
sharing its fold:

1. **Fold exactly as the gram stream does** (`fold_content`: Turkic-i
   pre-fold + `casefold`; no NFC). The query and the index then share
   the invariant the grams already pin, and preview bolding
   (brief gap 12) can reuse the fold.
2. **Split on runs of `[^\p{L}\p{N}_]`**, then split each run on `_`
   and on case change, **emitting the whole folded identifier and its
   parts** (Lucene's `PRESERVE_ORIGINAL`): `PostingsBuilder →
   postingsbuilder, postings, builder`; `pthread_create →
   pthread_create, pthread, create`. Sourcegraph's two motivating
   queries both hit; an exact-identifier query still ranks the defining
   file first because the whole-token match is a separate term with a
   higher IDF. Single-character parts are dropped; a token that starts
   with a digit is kept whole (`0x1f` is not `0, x, 1, f`).
3. **No stemming, no stop list.** Code identifiers are not inflected
   (`Snowball("closes") → close` would merge `closes` with `close` but
   also `indexing` with `index`, hiding a name the user typed); IDF
   already does the stop-word job continuously rather than by list
   (`the`, `self`, `return` get tiny idf), and Kamphuis notes the stop
   list is the *larger* source of variance — better to have none. The
   one knob to carry is a **df ceiling** (skip a query term present in
   > x % of chunks — Lucene's `CommonTermsQuery`, DuckDB's stop list) as
   a latency bound, not a quality one; the experiment's "common"
   term costs are the numbers behind it.
4. **Numbers stay** (`v2`, `404`, `2026`) — cheap and occasionally
   decisive in a technical corpus.
5. **Term length cap** (tantivy `RemoveLong`, default 40): a 300-byte
   base64 blob or minified line is one token nobody will query; cap at
   64 bytes post-fold and drop.

Fields (BM25F) are a later fork: the chunk rows carry no filename or
symbol field today. When they do, zoekt's shape — multiply the term's
tf in the boosted field, then run plain BM25 — is one extra column
(`tf_boosted`) at build time and no query-shape change.

### 4. Passage-to-entry aggregation

**The evidence.** Dai & Callan (SIGIR 2019) split documents into
150-word passages (stride 75) and compare `BERT-FirstP`, `BERT-MaxP`,
`BERT-SumP`. Robust04 nDCG@20 — title queries: FirstP .444, **MaxP
.469**, SumP .467; description queries: .491, **.529**, .524.
ClueWeb09-B title: .286, **.293**, .289; description: **.272**, .262,
.261 (web pages, where the lead passage carries the page). MaxP wins
or ties everywhere a document's relevance can sit anywhere inside it —
the code and technical-prose case. PARADE (Li et al., TOIS 2023) beats
MaxP by aggregating passage *representations* through a transformer,
and its own abstract restricts the gain to "collections with broad
information needs where relevance signals can be spread throughout the
document (such as TREC Robust04 and GOV2)" while "less complex
aggregation techniques may work better on collections with an
information need that can often be pinpointed to a single passage" —
a rerank-stage idea (brief gap 13), not a first-stage one, and not
expressible in SQL. PARM (Althammer et al., ECIR 2022) aggregates
paragraph-level dense retrieval to documents with RRF over paragraph
rankings and a vector-weighted variant; it confirms that rank-based
aggregation to the document is a workable first-stage shape.

**Aggregate, then fuse.** Each leg emits an *entry* ranking (MaxP
inside the leg), and RRF runs over entries. The alternative — fuse
chunk lists, then collapse to entries — has three defects: (i) an
entry with many mediocre chunks occupies many rank positions in each
chunk list and squeezes other entries out of the fused window (a
SumP-shaped bias that Dai & Callan show does not help); (ii) RRF's
`1/(k + rank)` is defined on positions, so the position an entry
"has" after a collapse is ill-defined (its best chunk's? then it *is*
MaxP, computed later and more expensively); (iii) `LIMIT n` on the
fused statement must count entries to be honest about the verb's
contract (R5), which only aggregate-then-fuse gives.

**In SQL, inside each leg**, portable on every declared engine:

```sql
lex AS (
  SELECT d.entry_id, MAX(c.score) AS score
  FROM   (SELECT t.chunk_id, SUM(t.weight) AS score FROM lex_terms t
          WHERE t.epoch = :e AND t.term IN (...) GROUP BY t.chunk_id) c
  JOIN   lex_docs d ON d.epoch = :e AND d.chunk_id = c.chunk_id
  GROUP  BY d.entry_id
)
```

then `ROW_NUMBER() OVER (ORDER BY score DESC, entry_id)` per leg for the
RRF rank — window functions exist on all six engines (SQLite ≥ 3.25,
MySQL 8, MariaDB 10.2, Postgres, SQL Server, Oracle). The preview needs
the *arg*max chunk, not just the max: `ROW_NUMBER() OVER (PARTITION BY
entry_id ORDER BY score DESC, chunk_id) = 1` in the same subquery
yields `(entry_id, best_chunk_id, score)` in one pass — exactly zoekt's
"file-level BM25F to rank files, then line-level BM25F to choose what
to display", except our chunk grain already is the display unit. The
executed cost of MaxP over chunk scoring is 0.1–0.7 ms extra at every
corpus size measured (§Experiment).

### 5. Freshness: what the lexical leg serves between a write and the next reindex

**The state machine, verified in the tree.** A content write stamps
`chunked=False, encoded=False, indexable=False` on the entry
(`writes.py` `_material_values`) and touches no chunk row; the old chunk
rows stay until `chunk_dirty` re-splits them at the next reindex (which
deletes and re-inserts — new `chunk_id`s). So between a write and the
reindex, the entry's chunk rows hold the *previous* body, and any
chunk-keyed lexical epoch scores that previous body. grep's answer to
the same shape is the flag partition: `encoded=True` implies the grams
are in the current epoch; everything `NOT encoded` is the scan
overlay, unioned so staleness never loses a match.

**Posture recommended: the same partition, with a budgeted lexical
overlay and a warning record.**

1. The lexical epoch is built in the same `build_epoch` scan as the
   grams — one pass over `chunked ∧ indexable ∧ live` entries — and
   published by the same `encoded` flips and the same pointer CAS, so
   the gram invariant extends verbatim: **`encoded=True` implies the
   entry's terms are in the current lexical epoch.** The leg joins
   `entry.encoded` (and `deleted_at IS NULL`, and `user_id` scoping) so
   a written-but-unreindexed entry is *excluded* from the index side,
   never served stale.
2. **The overlay is a live-text scan of the `NOT encoded` set**, exactly
   grep's `_entries_for_scan` partition, tokenized and scored
   client-side with the current epoch's `idf` and `avg_dl` (a
   `lex_df` IN-select on the query's terms — a few rows). Executed:
   scoring 100 freshly-written entries' chunks costs 0.18 s, 1,000
   entries ~0.5–0.9 s (§Experiment) — within an agent loop's budget for
   the write-then-search case, and bounded like grep's scan tier: the
   same candidate budget, the same deadline, and the same truncation
   spelling ("N unindexed entries: M scanned live, K not consulted").
   The overlay's scores are on the same scale as the index's (same
   formula, same corpus statistics), so its entries merge into the
   lexical leg's ranking before fusion; the fused statement carries the
   index side only, and the overlay merge is the one client-side step —
   the same place the vector floor already puts its client-side scan
   on MySQL/GENERIC (brief §4).
3. **The warning record** names both counts whenever the `NOT encoded`
   set is non-empty: how many were scanned live and how many the budget
   left unconsulted. For the vector leg the same entries have
   `embedding IS NULL` (the write reset the flags; the reindex has not
   re-embedded); they reach the fused list through the lexical overlay
   alone, which RRF handles natively — an entry missing from one leg
   simply has no contribution from it. The record should say so:
   "K entries ranked by lexical match only (not yet embedded)".

The alternatives were rejected: serving the stale chunk terms silently
violates the invariant grep already pays for; excluding the dirty set
with no overlay makes the verb blind to the file the agent just wrote,
which is the one file it is most likely to search for next (mem0's
"searchable on the next turn" argument, recorded in
`2026-08-25-semantic-chunking-write-vs-reindex.md` §5); and a
write-time lexical index (FTS5/GIN-style pending buffer) is the
"amortized inline" family the same memo found applicable only where the
write can produce a cheap approximation of the derived datum — and it
can, for terms (tokenizing is cheap; splitting is not), so a
**write-time term buffer** is a legitimate *future* fork: a
`lex_pending(entry_id, term, tf)` table written under the write
transaction and unioned by the leg, with the reindex draining it. Not
now: it puts a tokenizer on the write path the ETL contract measures,
and the overlay covers the agent case at the measured cost.

## Executed experiment

Corpora: the vfs repo (`src/ + context/ + docs/`: 628 files, 7.5 MB,
4,909 chunks) and a read-only slice of `~/Git/Repos/linux/drivers/gpu`
taken in path order until the chunk target is met. Chunks are minted by
`Chunk.split_batch` (tree-sitter for `.c/.h/.py`, recursive for
prose). Tokenizer as §3 (fold, split, whole+parts, no stemming/stop).
Statements run 5× each, median taken; 15 queries per arity drawn from
the vocabulary (1-term: mid-df terms; 3-term: two mid + one common
term with df > 20 % of chunks; 6-term: one rare + four mid + one
common). Scope: an id allow-list of 5 % and 50 % of entries (chunked
under a 1,000-id membership budget, statements summed) and one
directory segment join. `seed=7`; raw JSON under `lexical-leg/results/`.

### Build cost and size

| corpus | files | content MB | chunks | term rows | rows/chunk | vocab | split s | tokenize s | insert s | build s / 1k files | `lex_terms` MB | total MB | ×content |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| vfs | 628 | 7.5 | 4,909 | 691,845 | 141 | 29,690 | 0.33 | 0.88 | 1.46 | 4.3 | — | 20.9 | 2.8 |
| linux/gpu 1k | 256 | 4.5 | 2,690 | 286,087 | 106 | 29,880 | 0.09 | 0.46 | 0.41 | 3.8 | 9.0 (norm 7.0) | 10.2 | 2.2 |
| linux/gpu 10k | 1,024 | 19.6 | 11,608 | 1,166,497 | 100 | 87,862 | 0.32 | 1.97 | 1.68 | 3.9 | 37.8 (norm 29.5) | 41.9 | 2.1 |
| linux/gpu ~50k | — | — | — | — | — | — | — | — | — | — | — | — | — |

The ~50k-chunk build (`--max-chunks 50000`) did not complete on this
machine: the run died after the 10k build with an empty log and was
not retried, so the 1k and 10k rows are the scale evidence here; the
per-1k-files build cost is flat across them (3.8–3.9 s) and the
term-driven statement cost tracks the query's df sum, not corpus size.

`norm` = the same rows with an integer `term_id` instead of the term
text (−22 %). Secondary index for incremental maintenance:
+7.0 MB on the 1k build (+69 %); delete + reinsert of one entry's rows
costs ~25 µs/row vs ~1.4 µs/row in the bulk build.

### Statement latency (ms, median over 15 queries; `max` in the JSON)

| chunks | arity | precomputed `SUM(weight)` | runtime formula (3 joins) | entry MaxP | scope: ids 5 % | scope: ids 50 % | scope: segment join | scope-driven ids 5 % / 50 % |
|---|---|---|---|---|---|---|---|---|
| 4,909 (vfs) | 1 | 0.018 | 0.039 | 0.196 | 0.105 | 0.989 | 0.031 | — |
| 4,909 (vfs) | 3 | 0.371 | 0.979 | 0.969 | 0.294 | 2.841 | 0.625 | — |
| 4,909 (vfs) | 6 | 0.416 | 1.234 | 1.040 | 0.482 | 5.094 | 0.700 | — |
| 2,690 (gpu) | 1 | 0.016 | 0.034 | 0.111 | 0.047 | 0.410 | 0.026 | 0.046 / 0.406 |
| 2,690 (gpu) | 3 | 0.258 | 0.752 | 0.664 | 0.118 | 1.286 | 0.583 | 142.8 / 163.4 |
| 2,690 (gpu) | 6 | 0.188 | 0.524 | 0.488 | 0.184 | 2.246 | 0.418 | 144.4 / 159.1 |
| 11,608 (gpu) | 1 | 0.023 | 0.051 | 0.416 | 0.208 | 1.808 | 0.050 | 0.208 / 1.853 |
| 11,608 (gpu) | 3 | 1.016 | 3.134 | 2.693 | 0.638 | 5.867 | 2.492 | 680.5 / 1072.8 |
| 11,608 (gpu) | 6 | 0.896 | 2.690 | 2.380 | 1.142 | 10.775 | 2.223 | 695.1 / 1033.6 |
(no ~50k rows — the build did not complete; see the build table's note.)

Readings:

- **Precomputed weights are 2–3× faster than the runtime formula** and
  need one table instead of four in the statement. The epoch discipline
  makes precomputation free (idf and avgdl are epoch constants).
- **Cost tracks the query's df sum, not corpus size linearly**: the
  3-term rows are dominated by the one common term; a 1-term mid-df
  query is tens of microseconds at every size. A df ceiling on query
  terms is the one latency knob that matters.
- **MaxP is cheap** — the entry wrapper adds a lex_docs probe per
  scored chunk and a second GROUP BY.
- **The id allow-list as a JOIN is planner-fragile; as a semi-join it
  is not.** The 50 % allow-list *slows* the term-driven statement (the
  IN-list is probed per scored row and prunes nothing), and the
  "scope-driven" column is catastrophic for multi-term queries —
  **680 ms (3-term) and 695 ms (6-term) at 11,608 chunks for a 5 %
  allow-list, against 0.64 / 1.14 ms term-driven**. The diagnosis
  (`scope_plans.py`, `results/scope-plans-*.txt`, EXPLAIN QUERY PLAN
  at 10k chunks) says it is the *query shape*, not the index and not
  anything inherent: written as a JOIN, sqlite is free to pick the
  join order, and without table statistics it walked the allow-list's
  ~1,000 chunks and, for each, ran the `term IN (...)` filter through
  the chunk-keyed index — a nested loop over chunks × terms with the
  posting run re-read per chunk. After `ANALYZE` the same SQL replans
  term-driven (38 ms — still 60× worse than the unscoped statement,
  because the IN over ids is evaluated per scored row). Two shapes are
  fast and planner-stable at every width measured: the **semi-join**
  `t.chunk_id IN (SELECT chunk_id FROM lex_docs WHERE entry_id IN
  (...))` — 0.35 ms (3-term) / 0.32 ms (6-term) at 5 %, 0.21 / 0.20 ms
  at 0.5 %, planned as a bloom-filtered list subquery — and the
  **scope-driven PK probe** (`FROM lex_docs sd CROSS JOIN lex_terms t
  ON t.term IN (...) AND t.chunk_id = sd.chunk_id`), 0.75 / 1.37 ms at
  5 % and 0.07 / 0.13 ms at 0.5 %, which probes the `(epoch, term,
  chunk_id)` primary key per (chunk, term) and therefore **needs no
  secondary index at all**. The **segment join** is cheap at every
  width because it is an indexed equality on `(segment, entry_id)`
  that the planner can only run one way. Design consequence: carry
  the glob scope as a segments join by default; carry an id
  allow-list (the observations-piped scope) as a semi-join subquery,
  never as a JOIN; the scope-driven PK probe is the narrow-scope
  ladder rung, chosen by a width threshold like grep's
  `_ladder_defers`, and it costs no index. On the other engines the
  planner decides — the engine-matrix study should run the semi-join
  and the PK-probe shapes on the Docker legs before either is pinned.

### Ranking agreement with bm25s (same tokens, `method="lucene"`, k1 = 1.2, b = 0.75)

| corpus | queries | top-10 overlap (mean / min) | Kendall τ over top-50 union | median SQL/bm25s score ratio | min Spearman ρ of scores |
|---|---|---|---|---|---|
| vfs (4,909 chunks) | 45 | 1.0 / 1.0 | 1.0 | 2.200 | 1.0 |
| linux/gpu 10k (11,608 chunks) | 45 | 1.0 / 1.0 | 1.0 | 2.200 | 1.0 |

Identical rankings; the score ratio is exactly (k1+1) = 2.2, the
constant bm25s's Lucene form omits (§1). bm25s built its CSC index in
0.42 s for 4,909 chunks vs 2.3 s for our tokenize + sqlite insert —
the executemany, not the arithmetic, is the build's cost.

### Overlay (live-text fallback) cost

| corpus | dirty entries | chunks scored | seconds |
|---|---|---|---|
| vfs | 100 | 755 | 0.18 |
| vfs | 628 (all) | 4,909 | 0.88 |
| linux/gpu 1k | 100 | 1,041 | 0.16 |
| linux/gpu 1k | 256 (all) | 2,690 | 0.42 |
| linux/gpu 10k | 100 | 1,309 | 0.20 |
| linux/gpu 10k | 1,000 | 11,251 | 1.79 |
(no ~50k rows — the build did not complete; see the build table's note.)

~1.8 ms per dirty entry, ~0.17 ms per chunk, pure Python — a budgeted
scan tier, not a corpus-wide fallback.

## Bearing on vfs

**Recommendation.** Build the lexical leg on our own tables, not on
engine FTS. Concretely:

1. **Tables** `lex_docs`, `lex_terms`, `lex_df`, `lex_stats` as in §2,
   epoch-scoped, keyed `(epoch, term, chunk_id)`, `weight` precomputed
   with Lucene-accurate BM25, k1 = 1.2, b = 0.75, both in the
   `options_hash`. Built in `build_epoch`'s existing content scan,
   published by the existing `encoded` flips + pointer CAS, reclaimed
   by `reclaim_epochs`. `INDEX_FORMAT_VERSION` bumps.
2. **Tokenizer** in `vfs.models` beside `code_grams`, sharing
   `fold_content`: split on non-word runs, then `_` and case change,
   emit whole + parts, drop 1-char parts, keep digit-led tokens whole,
   cap term length, no stemming, no stop list. Pure reference in
   Python, engine port behind `vfs.native` when the build's tokenizer
   cost is measured to matter (it is ~40 % of build time today).
3. **Statement**: the §4 CTE — chunk `SUM(weight)`, entry `MAX` with
   `ROW_NUMBER() ... PARTITION BY entry_id` for the arg-max chunk, glob
   scope as a `segments` join (id allow-list only for the
   observations-piped scope, brief gap 14, as a semi-join subquery
   chunked under the membership budget), liveness/user/encoded
   predicates on `entry`, `LIMIT n` on entries. Query terms bound as an IN-list under the membership
   budget; a df ceiling skips flooding terms and says so.
4. **Aggregation**: MaxP inside each leg, RRF over entries
   (aggregate-then-fuse).
5. **Freshness**: index side joins `encoded`; a budgeted client-side
   overlay scores the `NOT encoded` set with the epoch's statistics;
   one warning record names scanned / unconsulted / lexical-only
   counts.

**Named forks for the ADR/spec:**

- **F1 — term text vs integer term id on posting rows.** −22 % bytes vs
  one extra lookup per query and a second table in every statement.
  Lean: text now (simpler statement, no id remap across epochs); revisit
  with the linux-store size numbers.
- **F2 — precomputed weight vs `tf` + runtime formula.** 2–3× latency
  and statement simplicity vs REAL bytes per row and k1/b frozen per
  epoch. Lean: precomputed.
- **F3 — chunk grain vs entry grain.** Chunk grain is the fused
  statement's unit, gives MaxP and the preview chunk for free, and
  matches the `chunks` table the vector leg scores. Entry grain (zoekt's
  choice) halves nothing we measured and loses the preview. Lean:
  chunk.
- **F4 — epoch rebuild vs incremental maintenance.** Rebuild matches
  the grams and needs no secondary index; incremental delete +
  reinsert of 1,000 entries measured **97 s at 11,608 chunks** (6.7 s
  at 2,690) with +69 % bytes for the chunk-keyed index, vs ~4 s to
  rebuild the whole 1,024-file corpus. Lean: rebuild, decisively;
  incremental only if a deployment's reindex cadence ever binds, and
  then as a set-based delete-by-chunk-range, never row-wise. A write-time `lex_pending` buffer is the sub-fork if the
  overlay budget proves too small for a deployment.
- **F5 — scope shape.** Segments join by default; an id allow-list
  as a **semi-join subquery** (0.2–0.35 ms at 10k chunks, planner-
  stable), never as a JOIN (0.6–680 ms depending on what the planner
  guesses); the scope-driven **PK probe** as the narrow-scope rung
  (0.07–0.13 ms at 0.5 %), which needs no secondary index. The
  680/695 ms cells in the timing table are the JOIN spelling
  mis-planned, not a property of scope-driven scoring. Width threshold
  like grep's ladder; to be confirmed on the Docker legs by the
  engine-matrix study, since each planner decides differently.
- **F6 — BM25F fields.** Not now (no filename/symbol field on chunk
  rows); the shape is a boosted-tf column at build time, no statement
  change. Symbol extraction is a producer the graph work may also want.
- **F7 — df ceiling and term cap values.** Latency knobs to set with the
  evaluation harness (brief gap 8), not by taste; the experiment gives
  the cost curve.

## Sources

- Kamphuis, de Vries, Boytsov, Lin. *Which BM25 Do You Mean? A
  Large-Scale Reproducibility Study of Scoring Variants*, ECIR 2020 —
  <https://cs.uwaterloo.ca/~jimmylin/publications/Kamphuis_etal_ECIR2020_preprint.pdf>;
  SQL variants at <https://github.com/Chriskamphuis/olddog>.
- Mühleisen, Samar, Lin, de Vries. *Old dogs are great at new tricks:
  column stores for IR prototyping*, SIGIR 2014; demo *Column Stores as
  an IR Prototyping Tool*, ECIR 2014 —
  <https://cs.uwaterloo.ca/~jimmylin/publications/Muhleisen_etal_ECIR2014.pdf>.
- Dai, Callan. *Deeper Text Understanding for IR with Contextual Neural
  Language Modeling*, SIGIR 2019 — <https://arxiv.org/abs/1905.09217>.
- Li, Yates, MacAvaney, He, Sun. *PARADE: Passage Representation
  Aggregation for Document Reranking*, TOIS 2023 —
  <https://arxiv.org/abs/2008.09093>.
- Althammer et al. *PARM: A Paragraph Aggregation Retrieval Model for
  Dense Document-to-Document Retrieval*, ECIR 2022 —
  <https://arxiv.org/abs/2201.01614>.
- Tibshirani. *Keeping it boring (and relevant) with BM25F*, Sourcegraph
  blog, 2025-04-04 —
  <https://sourcegraph.com/blog/keeping-it-boring-and-relevant-with-bm25f>
  (BM25F: Robertson, Zaragoza, Taylor, *Simple BM25 extension to
  multiple weighted fields*, CIKM 2004).
- *The technology behind GitHub's new code search*, GitHub blog, 2023 —
  <https://github.blog/engineering/architecture-optimization/the-technology-behind-githubs-new-code-search/>.
- Lucene `BM25Similarity` —
  <https://lucene.apache.org/core/10_1_0/core/org/apache/lucene/search/similarities/BM25Similarity.html>;
  Elasticsearch *Word delimiter graph token filter* —
  <https://www.elastic.co/docs/reference/text-analysis/analysis-word-delimiter-graph-tokenfilter>.
- SQLite FTS5 — <https://www.sqlite.org/fts5.html>.
- PostgreSQL text search controls (`ts_rank`, `ts_rank_cd`) —
  <https://www.postgresql.org/docs/current/textsearch-controls.html>;
  ParadeDB *Implementing BM25 in PostgreSQL* —
  <https://www.paradedb.com/learn/search-in-postgresql/bm25>;
  VectorChord-BM25 — <https://github.com/tensorchord/VectorChord-bm25>;
  Timescale *pg_textsearch* —
  <https://www.tigerdata.com/blog/introducing-pg_textsearch-true-bm25-ranking-hybrid-retrieval-postgres>.
- MySQL *Natural Language Full-Text Searches* / InnoDB ranking —
  <https://dev.mysql.com/doc/refman/8.0/en/fulltext-natural-language.html>,
  <https://dev.mysql.com/doc/refman/8.0/en/fulltext-boolean.html>.
- SQL Server *Limit search results with RANK* —
  <https://learn.microsoft.com/en-us/sql/relational-databases/search/limit-search-results-with-rank?view=sql-server-ver16>.
- Oracle Text *The Oracle Text Scoring Algorithm* —
  <https://docs.oracle.com/en/database/oracle/oracle-database/21/ccref/oracle-text-scoring-algorithm.html>.
- DuckDB *Full-Text Search Extension* (BM25 over generated SQL tables,
  `k=1.2, b=0.75`, index not auto-updated) —
  <https://duckdb.org/docs/current/core_extensions/full_text_search>.
- In-tree: `src/vfs/storage/backends/database/indexing.py`,
  `grep.py`, `pathterms.py`, `writes.py`; `src/vfs/models/postings.py`,
  `code_grams.py`, `chunk.py`, `rows.py`;
  `context/research/2026-08-25-semantic-chunking-write-vs-reindex.md`.
