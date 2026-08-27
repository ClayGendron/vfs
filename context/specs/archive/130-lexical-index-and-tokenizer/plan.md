# 130 — plan (rewrite under ADR 055)

The executed prototype (`../../../research/studies/2026-08-26-bm25-storage/prototype/`)
is the design's reference: its numbers are the targets and its
structure is what `src/` and `crates/` implement — written fresh, not
copied, and held to the repo's layout and rules.

## 1. Where things live

- `crates/vfs-core/src/lexical.rs`: tokenizer (generated tables in
  `lexical_tables.rs`), block encoder/decoder, `LexicalBuilder`,
  `score`. Exposed in `python.rs` behind the `python` feature as
  `Tokenizer`, `LexicalBuilder`, `lexical_score`.
- `vfs/native.py`: seam entries beside grams (`tokenize`,
  `lexical_builder()`, `lexical_score`), falling back to
  `models/lexical.py`'s pure implementations.
- `models/lexical.py`: keeps the rules, the formula, the pure builder
  (rewritten to block output), the pure scorer, the summary codec and
  block selection; owns the codec choice (the gram `encode_postings`
  for ids; plain varints for tfs/dls; varint delta + LE `f64` per
  block in the summary).
- `storage/backends/database/lexical.py`: the build over the paged
  scan (one pass: `add_docs` per batch, `finish`, two drains), the
  stats export returning summary rows.

## 2. Decisions the spec leaves to the plan

- **The true maximum at the drain**: a block's maximum needs `idf`
  and `avg_dl`, fixed only by `finish()`, so sealed blocks are held
  (compressed) until then and every summary and block row is complete
  on insert — no UPDATE exists. `finish()` decodes each block once
  (~tens of milliseconds for 3 M postings) for the maximum; `max_tf`
  and `min_dl` are not tracked. Residency measured at landing is the
  *vocabulary*, not the blobs: ~660 B of per-term structure (three
  byte streams, the sealed-block offsets, the map entry) against
  ~4.4 B per posting — +320 MB on 487 k terms, ~5 GB peak on the full
  checkout's 4.82 M terms. An arena for the term streams (one buffer
  per stream, offsets per term) is the ~5× direction; a sharded build
  the direction past one core.
- **Block size 128** (prototype: 64 ties, 256 spills sqlite pages).
  Declared constant in the options fingerprint.
- **Blob types**: `LargeBinary` + `LONGBLOB` variant; max blob length
  measured 256 B at 128 postings — every engine's in-row comfort.
- **Parity harness**: `tests/test_native.py` gains three rows
  (tokens, builder rows, scores); the Unicode tables carry
  `sys.version_info` and `unicodedata.unidata_version`; parity fails
  loudly on a mismatch rather than silently diverging.
- **Fallback scorer in numpy**: the batched form (concatenate blobs,
  decode once, segmented cumsum, `np.unique`/`bincount`) — 1.1 ms at
  10 k postings; per-block block-max is Rust-only (the Python loop
  loses to batched decode). Bit-identity with Rust comes from the
  accumulation order: blocks are laid out terms-by-descending-maximum,
  block order, posting order, and `bincount` adds sequentially in
  that order, as the Rust accumulator does; ties break on chunk id.
- **Block selection in numpy**: `searchsorted` maps each candidate to
  its block by the summary's first ids, `np.maximum.at` folds the best
  candidate score per block, and a block competes when its maximum
  (plus the other overflowing terms' maxima) clears θ alone or lifts
  its best candidate over θ.

## 3. Order of work

A (engine + pure twins + parity) → B (tables, build, bumps, ledger)
→ C (scorer wiring, stats ceilings, referee, landing measurements).
