# 117 — Rust chunking engine: vendored grammars, parallel split, degraded pure fallback

- **Status: drafted 2026-08-25.** Born from ADR 048 and its two
  research memos
  (`../../../research/2026-08-25-semantic-chunking-write-vs-reindex.md`,
  `../../../research/2026-08-25-rust-tree-sitter-chunking.md`); the
  decisions are made, this spec owns the landing. Spec 103 archives
  when this lands (its last open fork is ADR 048's subject).
- **Date:** 2026-08-25
- **Owner:** Clay Gendron
- **Kind:** engine move — semantic chunking's tree-sitter walk leaves
  the Python `tree-sitter-language-pack` binding for a rayon-parallel
  core in `crates/vfs-core`, behind the existing `vfs.native` seam.
  One declared behavior change: pure-Python installs chunk with the
  recursive character splitter (ADR 048 §4 — the one exception to the
  byte-identical-engines law, documented and pinned as such). No verb
  or Result movement; write pipeline untouched by law (ADR 048 §1).
- **Depends on:** ADR 048 (all four decisions), ADR 039 / spec 103
  (the vfs-core workspace, `native.py` seam, `PROTOCOL_VERSION`
  discipline, pendulum packaging), spec 095 (reindex integrity and
  engine-parity pins this spec amends for chunking).
- **Relates to:** the embedding-pipeline arc (chunk rows' only
  consumer — glean; this spec does not build it), the
  worker-posture open question (untouched: rayon threads inside one
  native call are not worker processes), spec 116's protocol-law
  style for the seam contract.

## Intent

1. **The split is native and parallel.** `vfs-core` gains a chunking
   module: the iterative span walker (emit a node whole when it fits
   the byte budget or has no named children; interstitial gaps as
   their own spans), greedy contiguous merge, the oversized-leaf
   delegation to the character splitter, and the recursive character
   splitter itself — a batch entry point that takes N
   `(content, grammar)` pairs and returns chunk spans, parsing with
   one `Parser` per rayon worker. The pyo3 binding detaches the GIL
   for the whole batch (the verify seam's pattern). Spike-measured
   expectation at linux scale: the 161 s chunk wall → ~25 s at
   8 workers, event-loop occupancy ~0.
2. **All 68 mapped grammars are vendored, pinned, and hermetic.**
   Generated `parser.c` (plus `scanner.c` where a grammar has one)
   vendored at exactly the `repo` + `rev` the pack's
   `language_definitions.json` pins at adoption time, compiled by
   `build.rs` via `cc`. A checked-in manifest records per grammar:
   repo, rev, ABI, license. No network, no dlopen, no crates.io
   grammar crates. Grammar-rev bumps are declared events: a bump
   changes the chunk generation (§4) and must update the parity
   fixtures in the same landing.
3. **The pure fallback degrades, declaredly.** `chunking.py` routes
   structure-aware splitting through the native seam;
   without the native engine, every extension takes the recursive
   character splitter (exactly what unmapped extensions get today).
   The `tree-sitter-language-pack` dependency — and its
   download-on-first-use grammar cache and thread-pinned-parser
   panic hazard — leaves `pyproject.toml`. The divergence is a
   documented contract: docstrings name it, and a test pins that the
   pure path's output *is* the character splitter's, byte-exact.
   `EXTENSION_TO_GRAMMAR` stays in Python as the routing table and
   becomes the coverage contract — a test pins that every mapped
   grammar name exists in the native engine's vendored set.
4. **Fingerprint-skip with a stamped generation.** `chunk_dirty`
   skips re-splitting a dirty entry whose chunk state was derived
   from the same source `content_hash` under the current **chunk
   generation** — a value covering engine identity (native vs pure)
   and the vendored grammar-set revision. A generation change
   re-dirties: stale chunks may not silently coexist with a new
   engine. The carrier of the per-entry skip key (entry columns vs a
   chunk-state row) is an implementation choice; whichever is chosen,
   the skip must hold under the guarded version-flip discipline
   `chunk_dirty` already obeys, and a same-body overwrite or restore
   must not re-split.

## Shape

- `crates/vfs-core/src/chunk.rs` (walker, merge, character splitter,
  batch driver), `crates/vfs-core/grammars/` (vendored sources +
  manifest), `build.rs` (cc compilation, parallel), `python.rs`
  (batch binding, GIL-detached), `PROTOCOL_VERSION` bump.
- `src/vfs/models/chunking.py` shrinks to routing + the pure
  character splitter + notebook cell routing (cells still route per
  grammar; their splits go through the same seam). `native.py` grows
  the chunk entry point with the pure fallback.
- `src/vfs/storage/backends/database/indexing.py`: `chunk_dirty`
  batches dirty bodies into one native call and applies the
  fingerprint-skip law.
- Licenses: every vendored grammar's license verified permissive and
  recorded (the pack's `ATTRIBUTIONS.md` precedent); the wheel's
  metadata carries the attributions.

## Slices

- **A — the core:** vendoring manifest + sources for the 68
  grammars, chunk module with parity fixtures (the spike's
  dump-and-replay corpus, committed), rayon batch driver,
  `cargo test -p vfs-core` green.
- **B — the seam:** pyo3 batch binding, `native.py` entry with pure
  fallback, `chunking.py` reroute, pack dependency deleted,
  divergence pins, coverage-contract test, `uv sync
  --reinstall-package vfs-py` note honored in CI.
- **C — the dirty pass:** batch call from `chunk_dirty`,
  generation-stamped fingerprint-skip, re-dirty on generation
  change, guarded-flip law preserved; engine legs re-run.
- **D — the gate:** linux-corpus reindex measured as a verb —
  target ≤60 s end-to-end (index build ~30 s + parallel chunking);
  wheel size recorded (expected ~+25 MB, watched against PyPI's
  100 MB cap); full `scripts/ci.sh` matrix green.

## Open questions

- Worker count: default to available parallelism inside the native
  call, or a declared knob beside `grep_wall_seconds`? (Lean:
  available parallelism, no knob until a consumer asks — the call is
  already bounded by batch size.)
- Vendoring mechanics: take committed `parser.c` from each grammar
  repo at the pinned rev vs regenerate with a pinned tree-sitter CLI
  at ABI 14 (the pack regenerates; taking committed artifacts is
  simpler but trusts each repo's checked-in generation). Settle in
  slice A with the choice recorded in the manifest.
