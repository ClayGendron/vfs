# 130 — the lexical index: one code-aware tokenizer and epoch-scoped BM25 tables built by reindex

- **Status: landed 2026-08-26.**
  All three slices: the code-aware tokenizer and Lucene-accurate BM25
  formula in `models/lexical.py` with a two-pass streaming builder;
  the four epoch-scoped `lex_*` tables (`SCHEMA_FORMAT_VERSION` 6 → 7,
  `INDEX_FORMAT_VERSION` 2 → 3, the lexical constants in the options
  hash) built inside `build_epoch` and swept by both reclaims; the
  `lexical_stats` export; the fidelity referee (`tests/support/
  lexical_fidelity.py`) green on sqlite and all four Docker legs.
  One deviation from the sketch, recorded in `plan.md` §1: the build
  streams the corpus twice instead of holding every posting — the
  whole-corpus builder would have been an out-of-memory on the linux
  store, not a slow path. Ledger rows L1–L5 proven. Numbers and the
  Rust-port trigger in the landing note below. First of the glean arc
  (130 → 138); no verb changes — spec 132 reads what this builds.
- **Born from:** ADR 051 §3–4; memo
  `../../../research/2026-08-26-glean-in-the-engine.md` §3; study
  `../../../research/studies/2026-08-26-glean/lexical-leg.md`.
- **Date:** 2026-08-26
- **Owner:** Clay Gendron
- **Kind:** new derived index in the database backend, riding the gram
  epoch's build/publish/reclaim discipline; schema and index format
  bumps.
- **Depends on:** the gram epoch machinery (`indexing.py`:
  `build_epoch`, `publish_epoch`, `reclaim_epochs`, `INDEX_FORMAT_VERSION`,
  `index_options_hash`), `code_grams.fold_content`, `ByteBatcher` (spec
  128), `chunked()`/`insertmanyvalues` budgets (`dialects.py`).
- **Relates to:** spec 132 (the consumer), spec 137 (the router's BM25
  reuses this tokenizer), the accuracy study's anchor-text arm (ADR
  053 consequences; a later field on these tables).

## Intent

grep's gram index nominates exact matches and carries no term
frequencies; glean needs a *ranked* lexical leg that produces the same
BM25 ranking on all six engines and joins into one statement. ADR 051
rules out engine full-text (five incompatible scores, five tokenizers)
in favour of our own term tables — a published, reproduced method
(Kamphuis et al. 2020) whose SQL form ranked identically to bm25s in
the study (top-10 overlap 1.0, τ = 1.0).

## Decided semantics

1. **Tables**, all epoch-scoped and keyed for contiguous posting runs:
   `lex_docs(epoch, chunk_id, entry_id, dl)` PK `(epoch, chunk_id)`,
   index `(epoch, entry_id)`; `lex_terms(epoch, term, chunk_id, tf,
   weight)` PK `(epoch, term, chunk_id)`; `lex_df(epoch, term, df, idf)`
   PK `(epoch, term)`; `lex_stats(epoch, n_docs, avg_dl)` PK `(epoch)`.
   `term` is folded text (fork E2: text now, integer ids later if the
   linux-store bytes ever argue for −22 %). `weight` is precomputed
   `idf · tfc(tf, dl)` (fork E3: 2–3× faster than the runtime formula).
2. **Formula**: Lucene-accurate BM25 — `idf = ln(1 + (N − df + 0.5)/(df
   + 0.5))` (never negative), exact `dl`, `(k1+1)` retained so a
   single-term score reads as `≤ (k1+1)·idf`; k1 = 1.2, b = 0.75. Both
   constants and the tokenizer version enter `index_options_hash()` so
   a retune forces a rebuild, never a mixed index.
3. **Tokenizer** (`src/vfs/models/lexical.py`, beside `code_grams.py`,
   sharing `fold_content`): split on runs of `[^\p{L}\p{N}_]`; split each
   run on `_` and on case change; emit the whole folded identifier
   *and* its parts (`PostingsBuilder → postingsbuilder, postings,
   builder`; `pthread_create → pthread_create, pthread, create`); drop
   one-character parts; keep digit-led tokens whole (`0x1f`); cap a
   term at 64 bytes post-fold and drop longer; **no stemming, no stop
   list**. Pure-Python reference now; a Rust port behind `vfs.native`
   is a later spec if the build's tokenizer share (~40 % today) is
   measured to matter — the pure reference stays byte-identical as the
   fallback and the parity test, as for grams.
4. **Build**: inside `build_epoch`'s existing content scan over
   `chunked ∧ indexable ∧ live` entries — per chunk row, tokenize,
   count tf, record `dl`; after the scan, `df` per term and `avg_dl`;
   then `weight` per row; rows written in `ByteBatcher` batches under
   the bind budget. The index is a regenerable epoch cache **rebuilt
   whole per reindex** (fork E4: incremental maintenance measured 97 s
   per 1,000 entries vs ~4 s for a corpus rebuild; no chunk-keyed
   secondary index).
5. **Publish and reclaim** ride the gram epoch: the same `encoded`
   flips and pointer CAS make the lexical epoch current; `reclaim_epochs`
   drops dead epochs' lexical rows with the gram rows. The invariant
   extends verbatim: **`encoded=True` implies the entry's terms are in
   the current lexical epoch.**
6. **Term statistics are exported** by a small function
   (`lexical_stats(session, tables, epoch, terms) -> {term: (df, idf)},
   (N, avg_dl)`) — one `IN`-list probe on `lex_df` plus one `lex_stats`
   row — because ADR 052 makes corpus-wide statistics a `SupportsGlean`
   requirement; spec 132 calls it, spec 137 consumes it.
7. **Format bumps**: `SCHEMA_FORMAT_VERSION` 6 → 7 (new tables),
   `INDEX_FORMAT_VERSION` 2 → 3; the existing first-touch refusal and
   generation re-dirty laws apply unchanged.

## Scope

In: the four tables, the tokenizer module, the build/publish/reclaim
extension, the stats export, the pins. Out: any query statement (132),
the scan overlay (132), BM25F fields — path, anchor text — (the shape
is a boosted-tf column at build time; a later spec), CJK tokenisation
(fork E7, open question), the Rust tokenizer.

## Slices

- **A — tokenizer**: `lexical.py` with the reference implementation and
  its pins (whole+parts emission, one-char drop, digit-led, the 64-byte
  cap, Turkic fold agreement with `fold_content`, determinism across
  processes).
- **B — tables and build**: schema, the `build_epoch` extension,
  `weight` precomputation, `ByteBatcher` batching, options hash;
  publish/reclaim parity with grams.
- **C — stats export and fidelity pins**: `lexical_stats`; a fidelity
  test that scores a fixture corpus through the tables in SQL and
  compares top-10 and Kendall τ against a pure-Python BM25 over the same
  tokens (the study's referee, in-tree, no bm25s dependency).

## Landing criteria

- `scripts/ci.sh 3.13` green; 100 % coverage; ruff/format/ty zero.
- Engine legs (postgres, mysql, mariadb, mssql, oracle) green: the
  build lands and the fidelity pin holds on every dialect.
- The reindex wall on the linux store stays under ADR 048's 60 s target
  *or* the tokenizer's share is measured and recorded as the trigger
  for the Rust port (state the number in the landing note).
- Index bytes per chunk recorded in the landing note (the study measured
  ~2.1–2.8× content bytes).
- Ledger rows: the `weight`/`options_hash` fingerprint (a constant
  change forces a rebuild), and the publish invariant (a `NOT encoded`
  entry has no current-epoch lexical rows).

## Open forks (recorded, not blocking)

E2 term text vs id; E7 CJK; the anchor-text field (ADR 053 F10 /
ADR 051 E8) as the first BM25F column once the extractor (spec 138)
produces referring lines.

## Landing note (2026-08-26)

- **Fidelity.** The stored weights summed in SQL rank exactly as a
  from-scratch BM25 over the same tokens — identical top-10 and
  Kendall τ = 1.0 on every query of the fixture corpus, on sqlite,
  Postgres 17, MySQL 8.4, SQL Server 2022, and Oracle 23 (the referee
  is shared by the sqlite test and the four engine rows in
  `tests/storage/test_conformance.py`). There is no MariaDB leg in the
  harness yet (spec 135 adds the image); the MySQL leg covers the
  family's `VARBINARY` key path.
- **The linux store, measured on the spec-103 corpus's seeded 4,000-file
  sample** (59.7 MB, 32,243 chunks, 8.7 M tokens, 3.09 M term rows —
  96 per chunk — 487 k distinct terms), sqlite, idle machine:
  reindex without the lexical build 2.7 s; with it 31.4 s — **the
  lexical build adds 28.8 s per 4,000 files**. The tokenizer alone is
  4.9 s per pass, 9.9 s for the two passes: **34 % of the build**. The
  other two thirds are row assembly and the inserts (3.1 M rows
  through `insertmanyvalues` on aiosqlite). Scaled to the full
  checkout (76 k eligible files) that is ~9 min against ADR 048's 60 s
  reindex target — **over it by ~9×**, so the number the spec asked
  for is recorded: the tokenizer's share is 34 %, and a Rust port of
  the tokenizer alone would recover at most a third. The larger lever
  is the row volume: term ids instead of text (fork E2, −22 % bytes
  and smaller binds), per-dialect bulk paths (`COPY`, `LOAD DATA`,
  bulk insert) for the term rows, and dropping the per-value
  `BytewiseString` bind processing on dialects where it is the
  identity. Those are the follow-up's candidates; none is a cap.
- **Index bytes.** With the sqlite tables `WITHOUT ROWID` the lexical
  index is 120 MB for 59.7 MB of content — **2.02× content, 3.7 KB per
  chunk** (`lex_terms` 99 MB, `lex_df` 19 MB, `lex_docs` 1 MB), inside
  the study's 2.1–2.8× band. With a rowid it was 211 MB (3.5×): the
  PK autoindex duplicated every row.
- **Memory.** The build holds one `df` per distinct term (487 k on the
  sample) and one batch of rows at a time; nothing scales with the
  number of postings.
- **A scale defect the engine legs missed, caught by the MSSQL spike
  (`../../../research/2026-08-26-bm25-vs-mssql-fulltext.md`).** The
  first cut streamed the chunk scan with `yield_per` and wrote each
  batch's rows *inside* the stream; SQL Server over ODBC (no MARS)
  refuses a write while a cursor is open — `Connection is busy with
  results for another command` — and the 2,000-file corpus failed
  its reindex. Every conformance corpus was under one 256-row page,
  so the stream was fully consumed before the first write and nothing
  failed. The scan is now keyset-paginated (`_SCAN_PAGE_ROWS = 256`,
  every page fetched whole before a write), pinned on sqlite by
  statement shape and on all four engine legs by a 600-chunk corpus
  (`…LexicalBuildBeyondAPage`). Ledger row L6.
- **On SQL Server** (the spike memo above, 2,000 files → 16,307
  chunks, 1.55 M term rows, amd64-emulated server): the whole reindex
  took 403.7 s and the lexical tables 125 MB, against 7.1 s and
  23.5 MB for the engine's own full-text index over the same chunks.
  The gap is the term-row volume through the 2,100-bind cap (~420
  rows per statement); the levers are the same as above, with the
  table-valued-parameter / fast-executemany path first on that
  engine. Query time is single-digit milliseconds on both sides;
  the memo's verdict and forks carry the rest.
- **Ledger rows** L1–L6 (`../../../standards/mutant-ledger.md`), each
  proven in an isolated worktree: the options fingerprint drops the
  lexical constants; the scan loses its liveness gate; a reclaim
  forgets the lexical tables; `dl` counts distinct terms; idf loses
  its smoothing. The `indexable` gate on the scan is designed-inert
  (plan.md §4) and is not a row.
