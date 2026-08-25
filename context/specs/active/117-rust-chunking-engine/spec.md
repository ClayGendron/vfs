# 117 — Rust chunking engine: vendored grammars, parallel split, degraded pure fallback

- **Status: all slices landed 2026-08-25** (A–D, same day drafted —
  slice statuses inline below carry the measured numbers). Born from
  ADR 048 and its two research memos
  (`../../../research/2026-08-25-semantic-chunking-write-vs-reindex.md`,
  `../../../research/2026-08-25-rust-tree-sitter-chunking.md`).
  Spec 103's last open fork is discharged — both specs now await
  their backward-flow mining pass; nothing further blocks archiving
  either.
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
2. **Grammars are crates.io crates on one runtime** *(reshaped
   2026-08-25 by Clay at slice A — ADR 048 carries the amendment
   note; the vendored-`parser.c` plan was discarded when its trial
   measured ~0.5 GB of generated C and §3's pack deletion had
   already dissolved the rev-parity motive)*. `Cargo.lock` is the
   pin, `cargo update` is the bump, and the pack's
   `language_definitions.json` stays the reference for which grammar
   serves each name. Resolved empirically at tree-sitter 0.26:
   **57 crates serving 59 grammar names** (typescript's crate also
   carries tsx; hcl serves terraform; forks where the canonical
   crate is dead: `kotlin-ng`, `md`, `sequel`, `svelte-ng`,
   `toml-ng`). Nine names have no usable crate and take the
   character splitter — astro, clojure, csv, json5, latex (broken
   publish), tcl, tsv, vb, vue — recorded in the coverage-contract
   test. Grammar bumps remain declared events: a bump changes the
   chunk generation (§4) and must update the fixtures in the same
   landing.
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

- `crates/vfs-core/src/chunk.rs` — registry + walker + merge + rayon
  batch driver returning `SpanRow` byte-spans with line ranges;
  grammar crates as `Cargo.toml` dependencies; `python.rs` gains
  `chunk_spans` (GIL-detached) and `supported_grammars`;
  `PROTOCOL_VERSION` 2 → 3. The engine returns spans, never text:
  the host slices content, filters whitespace-only chunks, and
  re-splits oversized leaves with its character splitter (which
  therefore lives only in Python — no Rust port needed).
- `src/vfs/models/chunking.py` shrinks to routing + the character
  splitter + notebook cell routing (cells still route per grammar;
  their splits go through the same seam). `native.py` grows the
  chunk entry point with the pure fallback;
  `_AVAILABLE_GRAMMARS` comes from `supported_grammars()` instead
  of the pack.
- `src/vfs/storage/backends/database/indexing.py`: `chunk_dirty`
  batches dirty bodies into one native call and applies the
  fingerprint-skip law.
- Licenses: grammar crates carry their licenses through normal
  cargo metadata; the license audit rides `cargo` tooling rather
  than a hand-kept attributions file.

## Slices

- **A — the core** *(landed 2026-08-25)*: crate set resolved
  empirically (57 crates / 59 names on tree-sitter 0.26; smoke
  test parsed every registered grammar; ~79 MB unstripped static
  binary measured), `chunk.rs` with registry + walker + merge +
  rayon batch, `chunk_spans`/`supported_grammars` bindings,
  protocol bump, `cargo test -p vfs-core` green (7 chunk tests).
  Engine-behavior fixtures land with slice B where the assembled
  Python-visible chunks exist to pin.
- **B — the seam:** `native.py` entry with pure fallback,
  `chunking.py` reroute (span assembly, strip filter, oversized
  re-split), pack dependency deleted, divergence pins,
  coverage-contract test against `supported_grammars()`, fixtures,
  `uv sync --reinstall-package vfs-py` note honored.
- **C — the dirty pass** *(landed 2026-08-25)*: `chunk_dirty` splits
  through one `Chunk.split_batch` call (grammar-routed bodies cross
  the seam in a single batch); the fingerprint-skip law spares
  same-hash re-splits and the generation law re-dirties stale
  shapes — carried by two new entry columns (`chunk_source_hash`,
  `chunk_generation`; SCHEMA_FORMAT_VERSION 5 → 6), stamped inside
  the existing guarded flip via a column-to-column SET. Both law
  pins proven with their mutants (ledger rows P1/P2). Engine legs
  re-run in slice D with the gate.
- **D — the gate** *(landed 2026-08-25)*: linux corpus (93,760
  files) — write 52 s, **reindex 54 s** as a verb, inside the ≤60 s
  target (from 191 s at spec 103's close, 672 s pure baseline; the
  chunk wall fell 161 s → ~24 s, matching the spike's 6.6×
  projection); all 25 grep bench queries at their healthy profile
  (55–742 ms) on the new store. Wheel: 449 KB → **9.0 MB** (the
  81 MB extension strips and deflates ~9:1 — far under PyPI's
  100 MB cap). Full matrix green (3.11–3.14); all four engine legs
  green on schema 6 (Postgres 210, MySQL 211, MSSQL 212,
  Oracle 209 — the MySQL flip-count pin trued up to name the
  generation re-dirty statement, as sqlite's was).

## Open questions

- Worker count: default to available parallelism inside the native
  call, or a declared knob beside `grep_wall_seconds`? (Lean:
  available parallelism, no knob until a consumer asks — the call is
  already bounded by batch size.)
- ~~Vendoring mechanics~~ — dissolved by the slice-A reshape:
  grammar delivery is crates.io crates; there is nothing to vendor.
