# 055. BM25 the Way grep Is Built: Block Postings per Term, the Rust Lexical Engine, and Client-Side Scoring Under a Client-Side Fusion

- **Status:** accepted 2026-08-26 — decided by Clay on the storage
  memo ("lets do that exactly, and it seems like this is also a good
  candidate for implementing in rust in vfs-core"). **Amends ADR 051**
  (pin 1 for the lexical leg; pin 3's tables; pin 4's df ceiling) and
  reopens spec 130 for a superseding rewrite before spec 132 builds
  the query path. Companions: ADR 052 (fusion — unchanged in
  substance, now client-side on every engine), ADR 048/049 (the Rust
  engine and the offload seam this rides).
- **Date:** 2026-08-26
- **Deciders:** Clay Gendron
- **Decided by:** human
- **Context source:** `context/research/2026-08-26-bm25-storage-design.md`
  and its studies (`studies/2026-08-26-bm25-storage/`: `pg_textsearch.md`,
  `paradedb-tantivy.md`, `vectorchord-bestmatch-lucene.md`,
  `prototype-benchmark.md`, and `review-validation.md` — the staff
  review of the first draft of this record, tested on the prototype
  store; pins 1, 2 and 4 carry its corrections), the SQL Server spike
  (`2026-08-26-bm25-vs-mssql-fulltext.md`), and spec 130's first
  landing note.

## Context

Spec 130 landed ADR 051's lexical index as decided: one row per
`(epoch, term, chunk_id)` with a precomputed BM25 weight, scored by an
in-engine `SUM(weight)`. It ranks identically on five engines (the
fidelity referee holds, τ = 1.0) and the SQL Server spike showed the
planner keeps it in index seeks under every scope glean will issue.
It also measured at **32 bytes per posting, 96 postings per chunk**:
3.09 M rows and 120 MB for a 4,000-file linux sample, +28.8 s on a
2.7 s reindex (~9 min for the full checkout against ADR 048's 60 s),
55× slower to build and 5× larger than SQL Server's own full-text
index, and ~1 B rows / ~29 GiB at 10 M chunks. The whole-corpus
in-memory builder the spec sketched would have been an out-of-memory
on the linux store, not a slow path; the two-pass stream that landed
holds memory but doubles the tokenizer's work.

Three prior-art studies (TigerData's `pg_textsearch`, ParadeDB's
`pg_search`/Tantivy, VectorChord-bm25 with pg_bestmatch and Lucene as
the reference) converge on one structure none of which stores a row
per posting: blocks of 128–256 compressed postings with a skip summary
beside each, corpus statistics frozen per index generation, and
top-k by block-max skipping. The machinery that needs an index access
method (memtables, tombstones, LSM compaction, segment pins,
per-candidate heap visibility) exists only to support in-place
mutation — which vfs's epoch rebuild declines by design — and the
weakest point of every AM-based design is filters and joins
(post-filter recall loss, over-fetch-and-retry).

The prototype benchmark built that structure on spec 130's own corpus,
in Python and in Rust, on sqlite and the four Docker engines:
**exact** rankings (45/45 identical top-10s, τ = 1.0, three scorers
pairwise), **4.3 bytes per posting**, **53 MB vs 120 MB**, build
**9.5 s in Python and 2.6 s in Rust vs 28.8 s** (≈50 s for the full
linux checkout in Rust — inside the 60 s target), a Rust tokenizer
byte-identical on every chunk at 10.9×, a Rust decode+score of
0.16 ms at 10 k postings against 1.1 ms in numpy and 2.0 ms for the
in-engine `SUM`; on the engines the block table is 0.22–0.27× the
size, loads 4–5× faster, and the fetch-then-score path wins on
Postgres, MySQL and SQL Server at 3+ terms and on every scoped shape
(Oracle alone still favours in-SQL unscoped, 4.4 vs 2.9 ms with the
numpy scorer — covered by the Rust one).

vfs already has this architecture for the gram index: one row per
`(epoch, gram)` holding a delta+varint blob, built by the Rust engine
behind `vfs.native` with a byte-identical pure fallback, fetched by
`WHERE epoch = ? AND gram_key IN (…)` and intersected client-side under
a measured cost ladder.

## Options considered

- **Keep the relational tables and cut constants** — term ids (fork
  E2), per-dialect bulk loads, dropping bind processing: 3–4× at best,
  still O(postings) rows, still the `SUM` over a common term's whole
  run at query time. Rejected: it does not change the asymptote.
- **Block postings scored in SQL** — impossible portably: no engine
  decodes a blob in a query without an extension or a UDF per dialect.
- **Block postings scored client-side, Python only** — 3× the build,
  2.25× the bytes, numpy scoring at parity with the engine `SUM`.
  Viable as the fallback, not as the engine: the tokenizer stays 55 %
  of the build.
- **Block postings built and scored in the Rust engine, pure fallback
  pinned byte-identical** — the gram index's architecture. Chosen.
- **Quantised norms or weights** (a byte per posting, as all three
  prior-art systems do) — 1.9 B/posting saved for 2–11 % score error
  and the loss of the τ = 1.0 referee. Declined; recorded as the
  fallback if bytes ever outrank fidelity.
- **`max_weight` as an in-SQL fetch filter** (the memo's fork F2) —
  measured wrong as a scalar predicate and useless as the per-term
  cut; replaced by client-side block selection over summaries.
- **Impact-ordered block fetch for all-common queries** — measured not
  to close on docid-ordered blocks; declined.

## Decision

1. **Storage: one row per `(epoch, term, block)`, one summary row per
   term.** `lex_postings(epoch, term, block_no, doc_count, doc_ids, tfs,
   dls)` PK `(epoch, term, block_no)`, block size 128 (64 ties; 256
   spills sqlite's in-page payload and every engine's comfortable row),
   blobs delta+varint in the gram codec's family — chunk-id deltas,
   tfs, and **exact** dls so a block scores without a `lex_docs` probe.
   `lex_df(epoch, term, df, idf, max_weight, blocks)` is the term's
   **summary row**: its idf, its maximum weight over every block, and
   `blocks` — one `(min_doc delta, max_weight)` pair per block, ~10 B
   per block (~0.08 B per posting) — so a term's whole skip structure
   is read without touching a posting. `lex_stats(epoch, n_docs,
   avg_dl, k1, b)` pins the constants every stored weight and bound
   were computed under: a summary is valid only at build values, and
   a query-time `k1`/`b` can never be offered without a rebuild.
   `lex_docs` stays as spec 130 built it (the entry join and MaxP).
   `lex_terms` is dropped. Epoch-scoped, published by the same
   `encoded` flips and pointer CAS, reclaimed with the epochs, rebuilt
   whole — the invariant "`encoded=True` implies the entry's terms are
   in the current lexical epoch" is unchanged.
2. **`max_weight` is the true per-block maximum**, computed at the
   drain once `idf` and `avg_dl` are fixed — not the
   `idf · tfc(max_tf, min_dl)` bound the memo proposed, which the
   review measured at 0.957× the truth at the median, 0.783 at worst,
   exact on 2.8 % of blocks (`review-validation.md` §3); `max_tf` and
   `min_dl` carry nothing the truth does not, and are not stored. It is
   **never a SQL predicate**: a scalar `WHERE max_weight >= θ` changed
   30 of 30 multi-term top-10s on the prototype store, and the
   WAND-correct per-term cut `θ − Σ others' maxima` fired 0 % of the
   time at three and six terms (§1 there). It serves the client —
   block selection between rounds (pin 4) and the scorer's skip. ADR
   051 pin 4's df ceiling is replaced by that selection: no term is
   dropped from a query; a flooding term's blocks are left in the
   engine when no candidate inside their id range can still compete.
3. **The build lives in `crates/vfs-core`** (`lexical.rs`: the
   tokenizer port and the block encoder) behind `vfs.native`, with the
   pure-Python builder as the byte-identical fallback and the parity
   pin, exactly as grams. One streaming pass over spec 130's
   keyset-paged chunk scan, blocks flushed as they fill, rows written
   in `chunked` inserts, memory bounded by the vocabulary (one open
   block per term). The Rust tokenizer is driven by tables generated
   from the interpreter's own `\w` / `isupper` / `islower` / `isdigit`
   / `casefold`, so it cannot disagree with CPython on what a letter or
   a fold is; the parity test runs the whole fixture corpus through
   both. The tokenizer's rules (ADR 051 pin 4) are unchanged.
4. **Query: two rounds; a third only for overflowing terms.** Round
   one is two statements that need nothing from each other: the
   `lex_df` probe (`df, idf, max_weight, blocks` for the query terms,
   with the `lex_stats` row) and the **head fetch** — `lex_postings
   WHERE epoch = ? AND term IN (…) AND block_no < 8` — so a term of at
   most eight blocks (1,024 postings) is complete in round one. The
   engine scores what it has. For each term with blocks past the head,
   the summaries and the round-one candidates decide which blocks can
   still change the top-k — the block alone clears θ, or a candidate
   inside its id range could cross θ with it — and round two fetches
   exactly those by key: `(term = ? AND block_no IN (…)) OR (term = ?
   AND block_no IN (…))`, each list under `membership_budget`, never a
   row-value `(term, block_no) IN (…)` (SQL Server has no row-value
   constructors in `IN`). Decode + BM25 + top-k in the Rust engine with
   the numpy path as the pinned fallback, both accumulating in the same
   term / block / posting order so the sums are bit-identical, ordered
   `score DESC, chunk_id`; MaxP to entries client-side over `lex_docs`.
   Query terms go through the same tokenizer; score agreement with a
   pure BM25 over the same tokens is the referee (τ = 1.0), on every
   engine. **The scale property this buys:** every round-one candidate
   lies in at most one block of a common term, so round-two bytes are
   bounded by candidates × one block per overflowing term, independent
   of the term's df — 68–74 % of the common term's blocks skipped at
   32 k chunks (`review-validation.md` §1), above 95 % at 10 M. The
   bound holds while θ exceeds the overflowing terms' summed maxima,
   which a top-10 anchored by a real rare term guarantees and a
   K = 1,000 fusion leg may not (the landing measurement runs the
   fusion K, not top-10 alone). An all-common query fetches its lists:
   impact-ordering blocks does not close (280 of 281 blocks on
   `struct if`) because a common term's block maxima are flat in docid
   order — the known limit of block-max, stated, not designed around.
5. **Scope, like grep.** Predicate scopes (globs via the segments
   join, `ext`, `kind`, liveness, `user_id`) and piped id lists resolve
   to a candidate **id set in SQL first**, then intersect with the
   decoded postings (`np.intersect1d` / Rust); a cost ladder in grep's
   shape — per-byte fetch+decode, per-candidate cost, measured — decides
   filter-then-fetch versus fetch-then-filter. Client-side scope fetches
   of tens of thousands of ids per query are not a path (8–96 ms
   measured); an allow-list is one intersection.
6. **Fusion is client-side on every engine.** The vector leg keeps
   its in-engine distance CTE and tiers (ADR 051 pins 5, 8; spec 135);
   the lexical leg supplies its ranked list from the scorer; ADR 052's
   `Fusion.fuse` combines the two (convex by default, RRF as the floor)
   with the signal factors of ADR 053 applied at the same point. ADR
   051 pin 1's single fused statement is thereby **amended to the
   vector leg alone**: the "client floor" it reserved for MySQL and
   `GENERIC` becomes the lexical leg's one path everywhere, and the
   cross-engine byte-identical-ranking guarantee is carried by one
   scorer with a pinned fallback instead of five dialect compilations.
7. **The freshness overlay** (ADR 051 pin 7) is unchanged in
   substance and simpler in shape: the `NOT encoded` set is tokenized
   and scored client-side with the epoch's statistics by the same
   scorer, and merged into the lexical list before fusion.
8. **Format bumps**: `SCHEMA_FORMAT_VERSION` 7 → 8 (`lex_terms`
   dropped, `lex_postings` added), `INDEX_FORMAT_VERSION` 3 → 4; the
   block size, codec tag and tokenizer version enter the options hash.

## Consequences

- Spec 130 is reopened and rewritten (block postings, summaries, the
  Rust engine, the scorer, block selection); it lands **before** spec
  132, whose lexical statements become the two rounds plus scoped-id
  resolution and the ladder. Spec 135's `Fusion.to_sql` is dropped — `fuse` is the only
  path; the vector CTE, tiers, native types and dialect facts stand.
  Spec 136's signal factor applies at fusion time over the candidate
  union (one `signals` probe) rather than as a join inside a fused
  statement. Spec 137's `BM25Rerank` is the same scorer over the
  union's chunk texts. Spec 131's BM25 baseline driver reads the block
  tables through the scorer.
- The relational tables spec 130 first landed are replaced, not kept:
  no production rows exist, and a stored index is a regenerable epoch
  cache (drop-and-rebuild on the format bump, as ever).
- Index bytes ~0.9× content (2.25× smaller than landed); ~5–6 GiB and
  ~10 M rows at 10 M chunks instead of ~29 GiB and ~1 B rows; the full
  linux checkout rebuilds in ~50 s in Rust. The tokenizer's Rust port
  answers spec 130's recorded trigger.
- Exactness is kept: exact `dl` per posting, Lucene-exact formula,
  the true block maximum, τ = 1.0 against pure BM25 — the fidelity
  referee moves over as is, and gains a row: round one plus the
  selected round-two blocks must score identically to the whole fetch.
- What is given up: in-engine fusion of the two legs in one statement
  (never measured to matter — fusion is arithmetic over two short
  lists), and SQL's ability to join arbitrary predicates *into* the
  scoring (replaced by id-set resolution and the ladder, which the
  benchmark showed beats the join on every engine at 3+ terms).
- **Write cadence is a reindex-trigger policy, not an index shape.**
  Rebuild + the freshness overlay (pin 7) already is the append design
  once reindex runs in the background on a trigger — a chunk count, or
  the overlay's measured cost; spec 132 measures the overlay's slope.
  The first landing's row-per-posting table as a delta tape (an
  insert-friendly representation of the un-encoded set scored against
  the frozen statistics — VectorChord's growing tape, code at a351e7b)
  changes what the overlay *reads*, not what it means; its trigger is
  that slope. Not built now, even for an agent-memory headline.
- Forks carried: a per-epoch `dl` array cached client-side (−1.9 of
  4.34 B fetched, for long-lived processes only); parallel build by
  ordinal shard with rayon when a corpus outgrows one core; term ids
  (ADR 051 E2) now that the text key is ~40 % of the postings table on
  sqlite; a 10 M-chunk store as its own spike (the projection:
  `return` is 19 MB of blobs and 36 k blocks there, its summary
  ~360 KB).
