# Path indexing prior art: how the field puts path predicates into candidate nomination

- **Status**: research memo — design input for a pending decision on
  indexing path information so glob predicates participate in
  candidate nomination (grep today; glob, semantic search, and any
  future surface tomorrow), instead of filtering after nomination.
- **Date**: 2026-08-17
- **Owner**: Clay Gendron
- **Question**: Can vfs index path information — e.g. a posting list
  per unique directory segment, sharing the content gram index's
  doc-id space — so glob/path predicates intersect with content
  candidates *before* entry and content fetch? How do production
  systems solve this, and which shapes survive vfs's constraints
  (multi-reader/writer SQL backend, stateless calls, no designed
  scale caps)?
- **Evidence gathered**: line-level read-only studies of four
  reference checkouts (zoekt Apache-2.0, codesearch BSD-3, ripgrep
  MIT/Unlicense, postgres PostgreSQL License — all re-confirmed),
  public design writing (GitHub Blackbird, plocate, Lucene,
  Qdrant/pgvector/Weaviate/Milvus, voidtools), and measurements on
  the 2026-08-16 linux-tree store (93,760 files; script in
  `studies/2026-08-17-path-indexing-prior-art/`). Cites and
  describes only — every line of vfs code stays ours.

---

## 1. Where vfs stands today

Glob and ext predicates never touch nomination. `grep_rows` slices
candidate doc ids to `CANDIDATE_BUDGET` *by entry id, before any
path is known*, fetches entry rows for all survivors, and only then
applies the compiled glob per candidate in Python
(`storage/backends/database/grep.py`). Two measured consequences at
linux scale:

- **Cost**: the per-candidate gate builds a validated `Path` per row
  — ~121 ms per 25,000 candidates before any glob even runs (a
  name-arm glob adds ~92 ms more) — inside calls that total
  380–1,460 ms. Every saturated call pays this even with no filters.
- **Recall**: because truncation precedes the glob, a scoped query
  on a wide pattern silently loses rows — `copyright` under
  `LICENSES/**` keeps only whatever LICENSES files landed in the
  first 25,000 ids. The scoped result set is small and fully
  servable; the pipeline just cannot see the scope in time.

One dormant asset: the entries table already stores `ext` as a
column, so extension predicates are pushable into the candidate
fetch SQL today, with no new index at all.

## 2. The field's three shapes

### 2a. No path index — filter a path list after nomination

**codesearch** stores paths only as a sorted, prefix-compressed name
list keyed by ordinal fileid (`index/read.go:7-119`); the `-f`
filter runs the file regex over each *content-nominated* candidate's
name, in memory, after trigram intersection
(`cmd/csearch/csearch.go:124-139`). Path text is never trigrammed.
The name list is the small part by construction — 5.08 MB of a
157 MB index (~3%) for a linux-sized tree. With no content literal
to nominate (`-brute`), the filter degrades to sweeping every name.

**Everything (voidtools)** is the pure-path extreme: the entire
filename database lives in RAM (~100 MB per million files), built by
reading the NTFS MFT directly and kept current by tailing the USN
journal; content is deliberately not indexed.

### 2b. Path text as a sibling gram corpus, same doc-id space

**zoekt** indexes the whole path string with the *identical*
trigram machinery as content — two symmetric `postingsBuilder`s
(`index/shard_builder.go:304-305`), same ngram size, same doc-id
space, corpus selected by one boolean (`index/indexdata.go:385-390`).
Postings are corpus-global rune offsets, not doc ids, so one posting
list yields both the candidate doc and the in-doc position. `file:`
patterns ride the same regexp→literal extraction as content; a
gramless `file:.*_test` degrades to per-doc regexp over names. The
filename corpus is the always-in-RAM tier, and a per-doc **cost
ladder** (const → memory → content → regexp,
`index/matchtree.go:51-56`) means filename predicates veto a doc
before content is fetched — cost ordering, not a planner. Two
details worth keeping: `lang:` filters on old shards are *lowered
into filename-trigram regexes* (`(?i)\.go$`, `index/eval.go:86-117`)
— the path index doubling as the cheap gate for another surface —
and doc-level metadata (repo, branch, language) is plain per-doc
arrays and bitmasks, not posting lists.

**GitHub Blackbird** ships three parallel ngram families — content,
symbols, and **paths** — over the same sharded doc space; `path:`
qualifiers compile to `paths_grams` iterators intersected with
content iterators, and qualifiers like `lang:`/`repo:` rewrite to
exact index clauses at query-rewrite time. Doc ids are assigned by
rank so posting-list order is result order
([github.blog, 2023-02-06](https://github.blog/engineering/architecture-optimization/the-technology-behind-githubs-new-code-search/)).

**plocate** is this shape with no content at all: trigram posting
lists over path text, where a "doc" is a compressed block of 32
paths, zstd + TurboPFor underneath. Patterns under 3 bytes or
regexes force a linear scan — the degradation cliff is documented in
its man pages ([plocate.sesse.net](https://plocate.sesse.net/)).

### 2c. Structure-aware terms: segments and ancestor prefixes

**pg_trgm** trigrams text *per word* — `/`, `.`, `-` are separators,
and adjacency across them is deliberately unrepresented
(`contrib/pg_trgm/trgm_op.c:337-366`). The canonical database answer
to "index a path column" therefore already decomposes at the segment
boundary. Its wildcard machinery extracts required trigrams from
LIKE patterns with padding only at non-wildcard edges
(`trgm_op.c:951-1079`), and `trgm_regexp.c` compiles a regex NFA
into a trigram formula under hard caps (128 states / 1,024 arcs /
256 trigrams), degrading gracefully to prefix-derived trigrams —
"false positives but no false negatives" — or to a full scan the
cost model prices honestly. The index **never** answers
authoritatively: `recheck = true` unconditionally
(`trgm_gin.c:187-188`).

**Lucene/Elasticsearch `path_hierarchy` tokenizer** emits one exact
term per ancestor prefix — `/one/two/three` → `/one`, `/one/two`,
`/one/two/three` — so a subtree query is a single term lookup,
composable in boolean queries with any other clause
([elastic.co](https://www.elastic.co/docs/reference/text-analysis/analysis-pathhierarchy-tokenizer)).
This is the exact-match complement to segment terms: prefix terms
answer "under this directory" without positional reasoning.

**ripgrep's globset** is prior art for the *matcher* tier: every
glob is classified once into one of seven strategies — literal,
basename-literal, extension, prefix, suffix, required-extension,
full regex (`crates/globset/src/glob.rs:16-67`) — and a path is
dispatched through hash buckets and Aho-Corasick automata before any
regex runs. Its walker prunes whole subtrees on *exclusion* matches
but never on includes — a file below may match `*.rs` though its
directory does not (`crates/ignore/src/overrides.rs:87-110`). The
asymmetry transfers: admission globs constrain files, not
directories, so only certain glob shapes (anchored directory
prefixes) can prune at the directory level.

## 3. Cross-cutting laws the field agrees on

1. **Superset-then-recheck, everywhere.** No system lets a path (or
   trigram) index answer authoritatively; nomination is a lossy
   superset and the real matcher re-verifies every survivor. vfs's
   gate/nominate/verify split is the same contract; path postings
   would slot in without changing it.
2. **Paths are the cheap tier; make that structural.** zoekt's cost
   ladder, Blackbird's rank-ordered doc ids, codesearch's 3% name
   list: every design arranges for path predicates to run before
   content is touched, whether by memory residency, cost ordering,
   or index families.
3. **Graceful degradation is designed, not accidental.** pg_trgm's
   caps, plocate's <3-byte cliff, zoekt's brute-force matchtree:
   each has a named fallback when the pattern yields no indexable
   material, and (in Postgres's case) a cost model honest about it.
4. **Below some scale, arrays beat indexes.** zoekt's repo/lang
   filters are per-doc arrays; Everything is a RAM list. The
   crossover is real but architecture-dependent — see §5.

## 4. Filtered semantic search: the same intersection, one surface over

The vector-search field has converged on a taxonomy directly
relevant to composing glob with semantic search
([Qdrant](https://qdrant.tech/articles/vector-search-filtering/),
[Weaviate](https://docs.weaviate.io/weaviate/concepts/filtering),
[Milvus](https://milvus.io/docs/filtered-search.md)):

- **Post-filtering** (ANN first, filter after) starves on selective
  filters — pgvector's README is bluntest: with default
  `ef_search = 40` and a filter matching 10% of rows, "only 4 rows
  will match on average".
- **Pre-filtering** (filter to an allow-list of ids, then search
  within it) is the correct shape for selective filters; Weaviate
  materializes the allow-list from an inverted index as roaring
  bitmaps and hands it to HNSW.
- **Filter-aware traversal** (Qdrant's filterable HNSW, Weaviate's
  ACORN) and a **cardinality-based planner** that falls back to
  brute-force over the filtered subset when the filter is very
  selective round out the design space.

The transferable fact: whatever structure serves glob-in-nomination
for grep — a doc-id set from path postings — is *exactly* the
allow-list a pre-filtered semantic search needs. One path index,
every surface intersects.

## 5. Measurements at linux scale (93,760 files)

From the 2026-08-16 benchmark store (script in the studies
directory; store rebuilt by the linux-grep-benchmark harness):

- **Segment vocabulary is tiny.** 3,087 unique directory segments;
  "file is under segment S at any depth" costs 356,542 postings
  total — **3.8 per file**, a rounding error beside the content gram
  index.
- **Selectivity is where scoped queries live.** Median segment pins
  11 files, p90 = 92; `ext4` → 80, `sched` → 190, `Documentation` →
  11,277, `net` → 10,730; the widest (`drivers`) → 37,768 (40%).
  Intersecting even the widest halves the candidate space; a typical
  subsystem scope collapses it by 100–1,000×.
- **The whole path corpus is 3.8 MB.** A full-corpus regex sweep in
  Python: 20 ms path-anchored, 163–175 ms name-arm — the codesearch
  shape is *feasible* per call at this scale, but see §6.
- **Extensions are already columns.** `c` 36,786, `h` 26,702,
  extensionless 6,937, `yaml` 5,518, `rst` 3,966 — the ext channel
  needs pushdown, not indexing.

## 6. The vfs constraint the field does not share: no single writer

Every in-memory design above — codesearch's mmapped name list,
zoekt's RAM-resident filename corpus, Everything's MFT snapshot,
plocate's index file — is **single-writer**: one process builds an
immutable index and swaps it atomically; readers see a coherent
snapshot by construction. vfs has no such process. Calls are
stateless, writers land continuously from many connections, and the
only shared memory is the database itself. A per-process path cache
would need revalidation against the database every call (defeating
its purpose), multiplies memory by process count, and smuggles in a
scale assumption (3.8 MB at linux scale is ~400 MB at 10M files) —
a designed cap the project's standards forbid.

The epoch pointer deserves honest mention: vfs *does* own a cheap
per-call validation primitive, and an epoch-stamped cache is
possible in principle. But path facts go stale on a channel content
grams are immune to: **renames**. Content grams survive a rename
(content unchanged; paths are read live at query time), while any
snapshotted path structure is wrong the moment a directory moves —
and a subtree rename cascades to every descendant row. Coherence
under that cascade is a story only the database's transactions can
own. The conclusion for the design space: **the path structure must
be DB-resident and transaction-governed** — posting lists (or term
tables) beside the content gram index, not process memory. Notably,
at 3.8 postings per file, path postings are cheap enough to maintain
*synchronously in the write path* — an option content grams never
had — though subtree renames still need a deliberate answer
(cascade the postings, or lean on ancestor-prefix terms keyed by
parent linkage).

## 7. What this validates, and the open forks

The directory-posting idea is **sound and well-precedented**: path
terms sharing the content doc-id space, intersected at nomination,
verified by the existing glob authority — Blackbird and zoekt ship
the gram-flavored version in production, pg_trgm ships the
segment-decomposed version, and the superset-then-recheck contract
is exactly vfs's existing law. It also fixes both measured defects
of the current pipeline at once: the per-candidate gate cost and the
truncation-before-scope recall loss. The forks a decision needs to
resolve:

1. **Term shape**: bare segment names (unordered superset — `a/b`
   and `b/a` nominate identically, authority disambiguates) vs
   ancestor-prefix terms (Lucene-style, exact for subtree scope,
   order preserved, but invalidated wholesale by ancestor renames)
   vs path trigrams (zoekt/Blackbird — also serves name-arm
   wildcards like `*_test.c`, at ~10–30× the posting volume).
   These compose: segments or prefixes for the dominant
   scope-shaped globs, with name-arm globs served by the ext
   column, a basename term, or trigrams.
2. **Maintenance mode**: synchronous with writes (feasible at 3.8
   postings/file; renames cascade transactionally) vs epoch-cycled
   beside the content grams (rename staleness until republish —
   a false-*negative* risk, which the forbidden-false-negative rule
   does not tolerate; would demand overlay coverage for renamed
   rows).
3. **Planner integration**: where the path-term intersection sits in
   the ladder (before rarest-gram intersection, as a restriction on
   it, or as an independent id-set intersected after), and what the
   degradation is when a glob yields no indexable terms (pg_trgm's
   graceful-prefix posture is the model).
4. **Multi-surface contract**: the path index's output should be a
   doc-id allow-list any surface can consume — grep nomination,
   the glob verb itself, and pre-filtered semantic search (§4) —
   which argues for it living beside, not inside, the grep planner.

---

*Sections below added later the same day: the fork evidence, gathered
to resolve §7 before a decision record.*

## 8. Term-shape economics, measured

`measure_shapes.py` in the studies directory, against the same store:

| Shape | Posting rows | Rows/file | Vocab | `/drivers` rename touches |
|---|---|---|---|---|
| Directory segments | 356,542 | 3.8 | 3,087 | 37,147 |
| Ancestor prefixes | 356,870 | 3.8 | 6,159 | 151,595 |
| Basename terms | 93,760 | 1.0 | 72,320 | 0 |
| Path trigrams | 3,364,630 | 35.9 | 26,770 | 1,304,815 |

Segments and prefixes cost the same at rest; under a hot subtree
rename segments win 4× over prefixes and 35× over trigrams — and
only the segment cascade is expressible as a single scoped `UPDATE`
(the term *name* changes; prefix and trigram terms embed path text,
so they are full delete+insert). Trigrams are the only shape that
serves name-arm wildcards (`*_test.c`), at ~10× the storage.

Synchronous-maintenance microbenchmarks (SQLite, ~412k-row postings
table with the natural `(segment, entry_id)` primary key):

- 10,000-file ETL batch, ~40k posting rows, one transaction:
  **~174 ms** — one more chunked bulk insert beside the existing
  content insert.
- Single-file agent write, 4 rows, own transaction: **~0.6 ms**.
- `/drivers`-scale rename, 37,768 rows, one `UPDATE`: **~50 ms**.

Intersection is free at any width: 25,000 sorted content-candidate
ids ∩ a segment posting costs 61–133 µs whether the posting holds 80
ids (`ext4`) or 37,768 (`drivers`).

## 9. The observed workload

`mine_usage.py` (studies directory) scanned 1,022 Claude Code
session logs on this machine — 18,605 Bash calls yielding 10,519
real file-search invocations (the harness here has no dedicated
Grep/Glob tools, so agents search via `grep`/`find`; single-machine,
one user's projects — one empirical sample, not a population):

- **99.4% of searches are scoped**: 71% to a single file, 22% to a
  directory, 7% via shell glob; only 0.5% sweep unscoped. Directory
  scopes are shallow — ~75% are ≤2 segments deep.
- **Glob shapes** (2,635 patterns): directory-scoped path globs
  47.9% (almost all single-level `dir/*.ext`; `**` appeared 27
  times, braces once), bare extension globs 37.7%, stem wildcards
  8.1%, basename literals 5.9%, character classes ≈0.
- **Pattern side**: 58.5% of grep patterns are OR-of-literals
  alternations (`TODO\|FIXME`); true structural regex is a small
  minority; `-i` 7%.

The taxonomy the measurements price is the taxonomy usage exhibits:
directory scope + extension is ~86% of all glob use, and both are
served by segments plus the existing `ext` column. Stem wildcards —
the one class only trigrams nominate — are 8%, and largely
prefix/suffix-shaped over the stored `name` column (a pushable LIKE)
besides.

## 10. Where the evidence points

Code facts that bind the design (gathered from the live tree; grep
overlay `storage/backends/database/grep.py:442-445`, move cascade
`topology.py:929-954, 1028-1101`, reindex phases `indexing.py`,
glean contract ADR 007 / `params.py:298-303`, pattern-only seam
ADR 031):

- The overlay is purely a per-row `NOT encoded` flag, and **renames
  deliberately produce no dirty signal** — the descendant rewrite
  "bumps no versions and takes no guard … one directory move must
  not flood the dirty overlay". Content grams survive because
  postings store only entry ids and paths are read live; any
  epoch-cycled path structure goes silently stale on rename — a
  false-negative hole.
- The move path already collects every descendant and runs one
  executemany UPDATE over them — a posting cascade joins that
  transaction; a batch write already runs the bulk-insert shapes a
  posting insert would reuse.
- Chunks are keyed by entry identity ("a rename rewrites zero chunk
  rows"), and `glean` already takes a `paths` scope — an entry-id
  allow-list joins both cleanly. ADR 031's law (scoping arrives as
  pattern text on the glob channels; no path channel crosses the
  storage seam) is compatible with an allow-list *derived from*
  those channels inside the storage layer.

Per-fork, the evidence points to:

1. **Term shape: directory segments + the existing `ext` and `name`
   columns; no trigrams, no prefix terms.** Segments serve the
   dominant scope-shaped globs as superset nomination (unordered —
   `a/b` and `b/a` co-nominate; the compiled glob authority
   disambiguates, per the universal superset-then-recheck law);
   `ext` and `name` are already stored columns serving extension
   globs, basename literals, and most stem wildcards as pushable
   SQL predicates. Trigrams would add 10× postings and 35× rename
   cost to nominate an 8%-of-usage class that degrades acceptably
   to fetch-and-filter.
2. **Maintenance: synchronous in the write/topology path.**
   Epoch-cycled path postings are disqualified in their plain form
   (rename staleness = false negatives, no overlay signal exists).
   A repaired variant — a second `path_encoded`-style flag demoted
   by the move's existing descendant UPDATE, with a path-overlay
   query arm — is *correct* and has the smaller implementation
   surface, but it converts a bounded ~50 ms rename-time cost into
   per-query fetch-and-filter over the un-covered partition for an
   unbounded window (reindex is batch-only by decision, and the
   agent workload renames-then-searches immediately). Synchronous
   costs ~174 ms per 10k-file batch, ~0.6 ms per agent write, rides
   the move's own transaction, needs no flag, no second query arm,
   no epoch scoping — and its postings are live truth covering the
   scan-tier overlay too. The flag variant remains viable as a
   lower-risk stepping stone (same table, same query contract).
3. **Planner placement: path terms are peers in the rarest-first
   ladder.** Segment postings share the doc-id space, so nomination
   intersects them with content grams starting from the rarest
   posting of either kind — a scoped-wide query (`copyright` under
   `ext4`) starts from 80 ids instead of 58k, and the candidate
   budget counts *scoped* candidates, fixing the §1 recall loss.
   Globs yielding no segment terms (bare `*.ext`, stem wildcards)
   contribute column predicates to the entry fetch instead, and a
   glob with neither degrades to today's behavior — pg_trgm's
   graceful-degradation posture, with the authority recheck
   unconditional throughout.
4. **Multi-surface contract: an allow-list seam beside the
   planners.** One storage-layer module compiles the glob channels
   to (segment terms + column predicates) and yields entry-id sets;
   grep's ladder, the glob verb's prefilter, and glean's future
   pre-filter (§4: allow-list pre-filtering is the industry answer
   for selective filters) consume the same seam. Scoping still
   arrives as pattern text; the allow-list is an internal artifact,
   not a new channel.
