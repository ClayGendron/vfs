# 048. Semantic Chunking: Reindex-Side by Law, a Rust Engine with Vendored Grammars, and a Degraded Pure Fallback

- **Status:** accepted 2026-08-25 — closes the chunking fork spec 103
  left open (recorded in `../open-questions.md`) and the
  write-vs-reindex question Clay posed against it. Refines ADR 039's
  engine-parity clause: chunking becomes the one declared exception
  to byte-identical engines (see Decision §3). Spec to follow; the
  open-questions entry archives against this ADR.
  **§3 amended 2026-08-25 (Clay, in session, at spec 117 slice A):**
  grammar delivery is **crates.io grammar crates** (cargo-managed,
  `Cargo.lock` as the pin, the pack's `language_definitions.json` as
  the reference for which grammar serves each name), not vendored
  `parser.c` archives — the vendoring trial measured ~0.5 GB of
  generated C for the 68-grammar set, a maintenance system Clay
  declined, and §4's deletion of the Python pack had already
  dissolved the rev-parity argument that motivated vendoring.
  Consequence accepted with the amendment: coverage is the ~60
  grammars with live compatible crates; the stragglers (astro,
  clojure, csv, json5, tcl, tsv, vb, vue) take the character
  splitter — the same fallback unmapped extensions already take —
  and terraform rides the hcl grammar. Spec 117 records the resolved
  crate mapping (final: 57 crates serving 59 names; latex joined the
  fallback set on a broken publish).
  **Implemented by spec 117, all slices landed 2026-08-25**
  (`../specs/archive/117-rust-chunking-engine/`; note recorded at
  the mining pass). Implementation facts that bind: **the seam
  carries spans, never text** — the engine returns byte spans with
  line ranges and an oversized flag; the host slices content,
  filters whitespace-only chunks, and re-splits oversized leaves, so
  the character splitter and all unicode semantics live only in
  Python. **§5's skip-key carrier resolved as two entry columns**
  (`chunk_source_hash`, `chunk_generation`; `SCHEMA_FORMAT_VERSION`
  5 → 6) stamped inside the existing guarded version flip; the
  generation value is `{active_core()}:{CHUNK_GENERATION}`, so an
  engine switch or a declared grammar bump re-dirties by one
  set-based statement. Measured at the gate: linux chunk wall
  161 s → ~24 s, reindex verb 54 s, wheel 449 KB → 9.0 MB (the
  wheel-size number is now CI-gated at a 50 MB budget).
- **Date:** 2026-08-25
- **Deciders:** Clay Gendron (all four selections, made against the
  executed evidence: placement ratified reindex-side; the deferred
  home chosen as Rust tree-sitter in vfs-core — "we should be writing
  rust code for exactly this purpose"; all 68 mapped grammars
  bundled; pure fallback degrades to the recursive splitter and the
  pack dependency is deleted; fingerprint-skip adopted).
- **Context source:**
  `../research/2026-08-25-semantic-chunking-write-vs-reindex.md`
  (executed write/edit/batch benchmarks; nine-system prior-art study)
  and `../research/2026-08-25-rust-tree-sitter-chunking.md` (executed
  Rust spike with 500/500 span parity and rayon scaling; grammar
  supply-chain and packaging study).

## Context

Semantic chunking — `Chunk.split`'s tree-sitter walk — is 161 s of
the 191 s linux-corpus reindex, serves only the future embedding
pipeline, and runs today inside the reindex verb via the Python
`tree-sitter-language-pack` binding. Two questions stacked: should the
split move to the write path, and if not, where on the deferred side
does its cost go? The measurements answered the first: inline
chunking would be ~8 % on a small agent write but +106 % on a
mid-size edit and 10–12× the entire write pipeline on a 10k ETL
batch, its 46–404 ms large-file tail cannot be shed to a thread (the
pack's `Parser` is a thread-pinned pyo3 class whose panic escapes the
fallback as a `BaseException`), and nine studied systems defer this
work class — the one same-shape system (Oak) shipped a synchronous
mode and deprecated it. The second question's evidence: a Rust port
of the span walker reproduced the Python engine's merged spans
exactly on 500/500 sampled files, gained nothing single-threaded
(1.1× — same C core), and gained 6.6× on 8 rayon workers, GIL-free.
Meanwhile the grammar supply chain surfaced as the real design load:
the pack ≥1.8 downloads grammar dylibs from the network on first use
(an operational fact previously unrecorded), and crates.io grammar
crates are too stale to trust (25 of the 68 grammars vfs maps are a
year-plus stale, 4 missing).

## Decision

1. **Placement is law: chunking never runs on the write path.**
   Writes and edits stamp `chunked = False` and do nothing else;
   the split runs on the deferred side, today the reindex verb's
   Phase A. Latency spent where the user feels it, multiplied per
   edit and per batch row, buys nothing a deferred split doesn't —
   chunk rows gate no commit and have no next-microsecond reader.
2. **The split engine moves to Rust in `crates/vfs-core`**, behind
   the existing `vfs.native` seam pattern: the pyo3 entry detaches
   the GIL, parses and walks with one `tree_sitter::Parser` per rayon
   worker, and returns chunk spans for a batch of files in one call.
   Expected profile: the linux-corpus chunk wall drops from 161 s to
   ~25 s at 8 workers, and the reindex verb's event-loop occupancy
   for chunking goes to approximately zero. *Amendment (2026-08-25,
   chunking-arc landing review, F1):* GIL detachment alone never
   delivered the occupancy claim — it frees threads, not the calling
   coroutine, and the loop measured dead for the whole chunk wall
   (2,000 files → 2,250 ms worst gap). Spec 120 makes the claim true
   by hopping every CPU-bound reindex stage through the backend's
   offload pool; the measured post-offload bound is ~50 ms worst
   loop gap at a 2,000-file probe corpus on both engines (inline:
   483 ms native at that corpus, 1,327 ms pure at 1,000 files), the
   residual gap set by the session's own on-loop statement work,
   not the chunk or posting CPU.
3. **All 68 mapped grammars are bundled statically**, as generated
   `parser.c` sources vendored at exactly the `repo` + `rev` pins of
   the pack's `language_definitions.json` at adoption time, compiled
   by `build.rs` via `cc`. No network at runtime, no dlopen, no
   crates.io staleness. Cost accepted: ~85–100 MB of object code,
   ~25 MB wheel growth (inside PyPI's 100 MB default), slower cold
   builds. Grammar-rev bumps are declared, test-gated events — they
   change stored chunk shapes.
4. **The pure-Python fallback degrades to the recursive character
   splitter, and the `tree-sitter-language-pack` dependency is
   deleted.** Structure-aware chunking is a native-engine capability
   by contract. This is the one declared exception to ADR 039's
   byte-identical-engines law: for chunking, the pure engine is a
   *fallback of record with different output*, not a parity twin —
   documented as such, with the divergence pinned by tests (the pure
   path's chunks are the character splitter's, exactly). The parity
   corpus that pins byte-identical behavior binds the Rust engine's
   spans against vendored fixtures instead of a second live engine.
5. **Fingerprint-skip joins the dirty pass**: `chunk_dirty` skips
   re-splitting an entry whose current `content_hash` already
   produced its stored chunks *under the same engine and grammar
   generation* — the skip key carries an engine/grammar stamp so an
   engine switch (pure ↔ native) or a rev bump cannot be masked by
   an unchanged body.

## Options considered

- **Write-path chunking** (inline, or inline-under-a-size-threshold):
  rejected on the executed numbers above; the threshold variant adds
  a two-path complexity the field avoids for no user-visible gain.
- **Process-pooling the Python split**: ~8× available but imports a
  worker-process posture question (daemonized hosts, uvicorn) shared
  with the matcher-offload fork, and keeps the thread-pinned,
  network-downloading Python binding at the center.
- **Accepting the wall**: honest but leaves the reindex verb 3×
  over its ≤60 s target for data nothing yet reads.
- **crates.io grammar crates** (difftastic's main model): workable
  runtime-version story (`LanguageFn` decoupling) but 4 grammars
  missing, 25 stale, fork-name fragmentation, and revs that cannot
  track the pack's pins.
- **Runtime-loaded grammars** (helix/pack model): smallest wheel,
  but imports download-on-first-use and dlopen into a seam that is
  deliberately self-contained and hermetic.
- **Keeping the pack as the pure engine at pinned revs**: preserves
  chunk parity across engines but keeps the dependency and its
  network semantics alive for pure-only installs; Clay chose
  hermeticity and deletion over parity for a fallback whose output
  is derived data, not user-facing truth.

## Consequences

- The write pipeline stays chunk-free forever; the ETL 10k-batch
  contract keeps its ~2 s profile.
- `vfs-core` grows a second engine concern (grams, verify, now
  chunking) and its first vendored-C surface; wheel size becomes a
  watched number with per-grammar features as the future escape
  hatch.
- The pack dependency, its download cache, and its thread-pin panic
  hazard all leave the tree; `EXTENSION_TO_GRAMMAR` becomes the
  contract for what the native engine must cover.
- Pure-Python installs chunk with the character splitter — a
  declared, tested degradation, named in docstrings.
- Chunk-shape stability is now versioned: grammar-rev bumps and
  engine changes re-dirty affected entries through the stamped skip
  key rather than silently coexisting with stale chunks.
- The reindex verb's ≤60 s linux-scale target becomes reachable
  (~30 s index build + ~25 s parallel chunking), letting spec 103
  archive once the implementing spec lands.
