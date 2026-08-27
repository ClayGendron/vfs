# The lexical index against the gram index, on one store

- **Date:** 2026-08-26, after spec 130's second landing (`aa8f51f`).
- **Question:** how does the lexical index compare to the grep (gram)
  index on the same corpus — build, size, and query — and what does
  the real two-round query cost end to end, SQL included, which the
  landing bench did not time (it timed the scorer and counted blocks).
- **Store:** the landing run's full linux checkout, `landing_full.sqlite`
  — 77,866 files, 674,445 chunks, 1.09 GB of chunk text, sqlite 3.50.4,
  the Rust engine. Scripts: `prototype/compare_queries.py`,
  `prototype/gram_rebuild.py`; numbers: `results/landing_comparison.json`.
- **Sources:** measured here; the gram-side build law is spec 103's
  (`specs/archive/103-grep-pipeline-rust-core`), the lexical build's
  profile is spec 130's landing note.

## Build

| | gram epoch | lexical epoch |
|---|---|---|
| whole rebuild on the loaded store | **13.0 s** (verb wall, lexical no-op'd) | **108 s** (delta; engine ≈ 42 s) |
| postings | 121.1 M (doc = file) | 65.2 M (doc = chunk) |
| rows | 245,399 gram rows | 5.18 M block rows + 4.82 M summary rows |

The lexical build is ~8× the gram build on the same content. The
difference is not the engine — both extract in Rust at comparable
rates — it is the row count: the gram epoch inserts 245 k rows of
~520 B, the lexical epoch inserts 10 M rows through SQLAlchemy's
insert path at ~4.3 µs/row (spec 130's missed criterion; the raw
driver does the same rows at 1.4 µs). The gram epoch's row shape
(one row per gram, the whole posting list in one blob) is what keeps
its insert cheap; the lexical index cannot collapse rows the same way
without losing the per-block fetch the query depends on — the fork
stays "bulk load path", not "fewer rows".

## Size

| | gram | lexical |
|---|---|---|
| posting blobs | 128 MB (**1.06 B/posting**) | 285 MB (**4.37 B/posting**) + 57 MB summaries |
| table bytes (sqlite `dbstat`) | 151 MB | 857 MB (postings 509, `lex_df` 325, `lex_docs` 23) |
| over content (1.63 GB) | 0.09× | 0.53× (0.75× of chunk text) |

Per posting the lexical index is 4× the gram index because it carries
three streams (id, tf, dl) where a gram posting carries one delta. The
larger gap is `lex_df`: 325 MB for 4.8 M terms is ~67 B/term, of which
the summary blob is 12 B — the rest is the key (epoch + term text),
`df`/`idf`/`max_weight` (24 B) and the b-tree's per-cell overhead in a
WITHOUT ROWID table. Term ids (ADR 055's fork) shrink the postings
key, not this row; a leaner row is mostly a narrower `lex_df`.

## Query, end to end

Real SQL on both rounds through `DatabaseStorage`'s session: the
summary probe + head fetch (`block_no < 8`), the scorer, then the
competing blocks by key, the scorer again. Medians over the landing
bench's 15 drawn queries per arity; k = 10 is the user's top-k,
K = 1000 the fusion depth.

| query | wall | round one | blocks fetched | bytes |
|---|---|---|---|---|
| 1 term, k = 10 | **2.3 ms** | 1.0 ms | 12 | 6 KB |
| 3 terms, k = 10 | **7.9 ms** | 1.9 ms | 94 | 47 KB |
| 3 terms, K = 1000 | 9.6 ms (max 26) | 1.8 ms | 277 | 137 KB |
| 6 terms, k = 10 | **14.6 ms** | 1.8 ms | 151 | 76 KB |
| 6 terms, K = 1000 | 19.1 ms (max 28) | 2.0 ms | 578 | 288 KB |
| grep, the same single term as a fixed string, `files` | **173 ms** (max 448) | — | — | 1,432 files matched |
| grep, same, `lines` | 174 ms (max 536) | — | — | — |

Ranked lexical retrieval over 674 k chunks answers in single-digit
milliseconds at three terms and under 20 ms at six with the fusion
depth; the gram-verified grep of one of those terms is ~170 ms
because it must verify ~1,400 candidate files against content. The
two are not substitutes — grep returns every matching line, exact;
glean returns the top chunks by weight — but at the fetch-and-rank
layer the block design costs about 5 % of a grep call.

### The statement shape, corrected

The first run of the same script put the round-two statement in the
shape ADR 055 pinned — `epoch = ? AND ((term = ? AND block_no IN (…))
OR (term = ? AND block_no IN (…)))` — and measured 486 ms at three
terms and 682 ms at six, with round one still at 2 ms. `EXPLAIN QUERY
PLAN` on sqlite 3.50.4:

| shape | plan | ms |
|---|---|---|
| epoch outside the OR, three arms | `SEARCH … USING PRIMARY KEY (epoch=?)` — scans the epoch's 5.2 M rows | 470 |
| `epoch = ?` repeated inside each arm | `MULTI-INDEX OR`, three `(epoch, term, block_no)` seeks | 0.03 |
| `UNION ALL`, one select per term | compound query, three seeks | 0.02 |
| row-value `(term, block_no) IN (VALUES …)` | seek + bloom filter (sqlite only; SQL Server refuses it) | 0.02 |

sqlite's OR optimization needs every arm to be independently
indexable; an equality factored outside the OR is not pushed into the
arms. The pin is amended in ADR 055 and spec 132: the epoch equality
sits inside every arm, so each arm is a complete key prefix. Whether
Postgres, MySQL, SQL Server and Oracle plan the amended shape as key
seeks is a spec 132 landing measurement (they should — BitmapOr /
index_merge / index seek union — but this memo is the reason it is
measured, not assumed).
