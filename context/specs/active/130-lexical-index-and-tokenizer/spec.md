# 130 — the lexical index: one code-aware tokenizer and epoch-scoped BM25 tables built by reindex

- **Status:** ready — drafted 2026-08-26 from ADR 051 (pins 3, 4);
  first of the glean arc (130 → 138), each slice landing green and in
  order. No verb changes here: this spec builds and publishes the
  index the glean verb (spec 132) will read.
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
