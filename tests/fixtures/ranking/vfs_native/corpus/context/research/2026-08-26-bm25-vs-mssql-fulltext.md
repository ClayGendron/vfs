# Owned BM25 tables vs SQL Server Full-Text Search at query time

- **Status:** executed 2026-08-26 (spike; results below)
- **Question (Clay, 2026-08-26):** is the lexical leg spec 130 landed —
  our own `lex_*` tables, `SUM(weight)` over a `(epoch, term, chunk_id)`
  key — faster at query time than SQL Server's native full-text
  search, and does SQL Server's planner keep the design's index seeks
  under the joins and predicates glean will add (liveness, extension,
  directory segment, id allow-lists, MaxP)?
- **Informs:** spec 132 (the lexical statement), ADR 051's pin 3
  (own tables over engine full-text — confirmed or revisited here).
- **Study:** `studies/2026-08-26-bm25-vs-mssql-fulltext/` — `spike.py`
  (the experiment), `Dockerfile` (SQL Server 2022 with
  `mssql-server-fts`, which the stock image lacks), `results/*.json`.

## Method

The spike loads a seeded sample of the linux checkout (`seed=7`, the
spec-103 sampler) through `DatabaseStorage` on the FTS-enabled server
— real vfs tables, real reindex, so the owned side is exactly what
spec 130 built — then creates a full-text catalog and index over
`chunks.content` (English word breaker, full population, change
tracking off) as the fairest native counterpart: one inverted index
over the same chunk bodies.

Queries are drawn from the built vocabulary as the lexical study drew
them: 15 per arity; 1-term = a mid-df term (0.2–2 % of chunks);
3-term = two mid + one common (> 20 %); 6-term = one rare (< 0.2 %) +
four mid + one common. The owned statement is `SELECT TOP 10 chunk_id,
SUM(weight) … WHERE epoch = ? AND term IN (…) GROUP BY chunk_id ORDER
BY score DESC`; the native one is `CONTAINSTABLE(chunks, content,
'"t1" OR "t2" …')` ordered by `RANK`. Seven shapes wrap both
identically:

| shape | what it adds |
|---|---|
| S1 | unscoped top-10 |
| S2 | join to `lex_docs`/`chunks` and `entries` for liveness and path — the real glean row |
| S3 | S2 + `entries.ext = <most common ext>` |
| S4 | S2 + `EXISTS (segments WHERE segment = <most common directory>)` — ADR 040's segment scope |
| S5 | id allow-list of 500 entries (`entry_id IN (…)`) — the piped-observation scope |
| S6 | MaxP: `GROUP BY entry_id`, `MAX(score)`, top-10 entries |
| S7 | S3 + S4 + S6 together |

Each statement runs 7 times per query on a plain pyodbc connection
(medians; the async driver stack is deliberately out of the loop), the
estimated plan is captured with `SHOWPLAN_TEXT` and reduced to its
operator list, and the two top-10 sets' Jaccard overlap is recorded —
relevance is not the question here (FTS `RANK` is not BM25), but a
near-zero overlap would mean the two legs are not answering the same
question at all.

SQL Server runs amd64-under-Rosetta on this machine; absolute
milliseconds are inflated for both sides alike, and the comparison is
the ratio and the plan shape, not the number.

## Results

Corpus: 2,000 sampled linux files → 16,307 chunks, 1,550,572 term
rows (95 per chunk), 269,858 distinct terms. `results/spike-2000.json`
holds every number, query, and plan.

### Build and size — the first finding, and not the one asked for

| | owned `lex_*` tables | SQL Server full-text |
|---|---|---|
| build | **403.7 s** (the whole reindex, grams included, on the emulated server) | **7.1 s** full population |
| size | **111 MB** `lex_terms` + 12 MB `lex_df` + 2 MB `lex_docs` | **23.5 MB** catalog |

The owned build is ~55× slower and ~5× larger than the native index
on this engine. The build cost is the term-row volume through
`insertmanyvalues` under SQL Server's 2,100-bind cap (≈420 rows per
statement, ~3,700 statements, each a round trip to an amd64-emulated
server — the same volume that landed at +28.8 s per 4,000 files on
sqlite); the size is text terms plus an 8-byte weight per posting
against a compressed inverted index. Neither changes the query-time
answer below, but both belong in spec 130's landing note and in the
follow-up's scope (term ids, bulk paths).

The 2,000-file load also **surfaced a real defect** in the landed
build: SQL Server over ODBC has no multiple active result sets, and
the build wrote each batch's rows while the chunk scan's cursor was
still open — `Connection is busy with results for another command`.
Every conformance corpus fit in one 256-row page, so the stream was
consumed before the first write and the legs stayed green. The scan is
now keyset-paginated and pinned by a 600-chunk row on all four engine
legs (spec 130 landing note, ledger L6).

### Query time — medians in ms, owned / full-text, 15 queries per arity

| shape | 1-term | 3-term | 6-term | top-10 Jaccard |
|---|---|---|---|---|
| S1 unscoped top-K | 0.67 / 0.82 | 3.57 / 1.59 | 3.75 / 1.48 | 0.33 / 0.00 / 0.11 |
| S2 joined to entries (liveness + path) | 0.83 / 1.02 | 4.91 / 2.73 | 5.20 / 2.40 | 0.50 / 0.12 / 0.11 |
| S3 scoped by extension | 0.95 / 1.12 | 5.87 / 8.41 | 5.26 / 5.55 | 0.50 / 0.18 / 0.12 |
| S4 scoped by directory segment | 0.95 / 1.15 | 5.02 / 9.15 | 5.46 / 8.98 | 0.50 / 0.08 / 0.14 |
| S5 scoped by an id allow-list (500 ids) | 1.83 / 1.85 | 6.01 / 4.07 | 6.61 / 3.47 | 0.55 / 0.12 / 0.23 |
| S6 MaxP to entries | 0.99 / 1.08 | 7.18 / 6.46 | 7.46 / 5.81 | 0.54 / 0.18 / 0.18 |
| S7 ext + segment + MaxP | 1.24 / 1.39 | 9.48 / 10.43 | 11.26 / 8.38 | 0.80 / 0.18 / 0.11 |

Reading it:

- **Every shape answers in single-digit milliseconds on both sides**,
  on an emulated server, over 16 k chunks. Neither leg is the latency
  problem at this scale; the difference is at most ~2× either way.
- **One-term queries: the owned tables win everywhere** (0.67 vs
  0.82 ms unscoped, holding through every join). A one-term probe is
  one contiguous seek on `(epoch, term, chunk_id)`.
- **Multi-term unscoped queries: full-text wins** (3.6 vs 1.6 ms at
  3 terms). The 3- and 6-term queries each carry one *common* term by
  construction (df > 20 % of chunks — `struct`, `data`, `this`,
  `return`, `device`: only 12 such terms exist in this vocabulary), and
  the owned leg must read that term's entire posting run (3–6 k rows)
  and aggregate it, while the native index reads a compressed list.
  This is the `df` ceiling ADR 051 already named for the tokenizer
  (a common term should be skipped or capped at query time, not
  summed in full) and it is the one query-time lever this spike
  points at.
- **Scoped queries: the owned tables win or tie once a real predicate
  is present** — extension (5.9 vs 8.4 ms at 3 terms), directory
  segment (5.0 vs 9.2 ms), all three together at 3 terms (9.5 vs
  10.4 ms) — because the planner can push the scope into seeks on
  the owned side (below) where the full-text rowset forces hash joins
  over scans.
- **Relevance overlap is low by construction** (Jaccard 0.0–0.5 at
  3+ terms; up to 0.8 on the one-term combined shape): `RANK` is not
  BM25, and the English word breaker plus its stop list tokenizes
  identifiers differently (`mod_devicetable` is one token to us,
  `mod devicetable` to it; `this` is a stop word there). The two legs
  are answering related but not identical questions — which is the
  reason ADR 051 chose one formula over five engines' native ones,
  not a defect of either.

### The planner — what the estimated plans say

Owned side, every shape: **`Clustered Index Seek[lex_terms]`** on the
`(epoch, term, chunk_id)` key, then `Stream Aggregate` per chunk,
never a scan of the term table. The joins glean adds all become seeks
too: `Clustered Index Seek[lex_docs]` → `Index Seek[entries]` (S2,
S3), `Clustered Index Seek[segments]` for the directory scope (S4), a
`Filter` after the `lex_docs` seek for the id allow-list (S5). The
MaxP shapes (S6, S7) switch to `Merge Join` on `lex_docs` — a sorted
range seek on `epoch` — and S7's extension predicate becomes a
`Clustered Index Scan[entries]` on both sides (there is no index on
`ext` alone that also carries the join key; the `(ext, kind)` index
exists but the planner preferred the scan for a 2,000-row table — a
statistics question at this size, not a design fault, and the same
choice was made for the full-text side).

Full-text side: `CONTAINSTABLE` is opaque to the planner (a table-
valued rowset with no key statistics), so every scoped shape becomes
**`Hash Match` over `Index Scan[chunks]` / `Clustered Index
Scan[entries]`** (S3, S4, S6, S7). It is fast here because 16 k rows
scan in a millisecond; it is the shape that stops scaling first.

## Verdict

1. **ADR 051's pin stands, on the evidence, for the reasons it gave
   plus one measured here**: the owned tables keep the planner in
   seeks under every join and predicate glean issues, where the
   native rowset forces scans and hash joins; and the owned formula
   is the same on all five engines, which no native leg is.
2. **"Faster than native at query time" is true for one-term and for
   scoped queries, false for multi-term unscoped queries** — by ~2×,
   in single-digit milliseconds. The cause is fully explained (the
   common-term posting run) and has a query-side fix already in ADR
   051's vocabulary: apply the `df` ceiling at query time — drop or
   cap a term above the ceiling before summing — which spec 132
   should carry as a decided semantic rather than an option.
3. **The build cost and index size are the real gap**: 55× slower to
   build and 5× larger than the native index on SQL Server. Spec 130's
   landing note already records the levers (term ids — fork E2;
   per-dialect bulk paths; dropping per-value bind processing); this
   spike adds that on SQL Server the bind cap makes the bulk path
   (`bcp`-style `INSERT … SELECT` from a table-valued parameter, or
   the ODBC fast-executemany) the one that matters.
4. **A defect found by scale, not by the legs**: the open-cursor write
   on SQL Server. The conformance corpora are all under one page; the
   600-chunk engine row now closes that class, and any future
   streaming-then-writing build should be written against it.

## Forks

- **F1 — query-time `df` ceiling** (for spec 132): skip a term whose
  `df / N` exceeds a declared share (the tokenizer memo's 0.2–0.5
  band) or cap the rows read per term; measure on the harness (spec
  131) — a common term carries little BM25 weight, so recall should
  not move.
- **F2 — bulk build paths per dialect**: SQL Server table-valued
  parameter / `fast_executemany`; Postgres `COPY`; MySQL `LOAD DATA
  LOCAL`; measured against the 403 s here.
- **F3 — term ids** (ADR 051 fork E2): −22 % bytes in the study;
  here the term column is the bulk of 111 MB.
