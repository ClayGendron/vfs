# Rust tree-sitter chunking in vfs-core — spike, parity, and packaging

- **Date:** 2026-08-25
- **Provenance:** commissioned by Clay in the same session as
  `2026-08-25-semantic-chunking-write-vs-reindex.md`, immediately after
  its decision pass: placement ratified reindex-side, and among the
  deferred-home options Clay selected **Rust tree-sitter in vfs-core**
  ("we should be writing rust code for exactly this purpose … we
  should be able to run the chunking process for multiple files at
  once"), with fingerprint-skip adopted and the path set as research →
  ADR → spec. Two investigations, run 2026-08-25: an executed Rust
  spike (a cargo scratch crate porting the span walker; scripts and
  crate in the session scratchpad, ephemeral; this memo carries the
  operative numbers), and a packaging/prior-art study — web research
  plus two fresh reference clones made for this pass, both
  license-checked MIT: `~/Git/Repos/tree-sitter-language-pack` (the
  pack's own repo, now the xberg-io/Kreuzberg project) and
  `~/Git/Repos/difftastic`.
- **Headline:** the spike works and the fork's premise holds. A
  ~60-line Rust port of `_atomic_spans` + `_merge_spans` produced
  **byte-identical merged spans on 500/500 sampled files** (265 C from
  linux, 173 Python from sqlalchemy, 62 Rust from oxigraph) against
  the live Python engine. Single-threaded Rust is **not** faster
  (1.1× — both engines run the same C tree-sitter core; parse
  dominates), but that was never the point: with one `Parser` per
  rayon worker the same 500-file population drops 1,266 ms → **192 ms
  on 8 threads (6.6×)**, GIL-free — projecting the linux-corpus
  161 s chunk wall to **~25 s**. The real design load is not the code
  but the **grammar supply chain**: vfs's chunking today silently
  depends on network-downloaded grammar dylibs (the pack's 1.x model —
  an unrecorded operational fact), crates.io grammar crates are too
  stale to trust (25 of the 68 grammars vfs maps are ≥1 year stale,
  4 missing), and the strong option is difftastic's/the old pack's
  model — **vendor generated `parser.c` at exactly the revs the
  pack's `language_definitions.json` pins**, which buys engine parity
  by construction and a hermetic wheel at ~15–25 MB compressed for a
  curated set (PyPI's default cap is 100 MB/file).

## 1. The spike (executed)

Design: dump the Python engine's merged spans
(`_merge_spans(_atomic_spans(content, grammar, 2048), 2048)`) for a
seeded 500-file sample as JSON; a scratch cargo crate (tree-sitter
0.25.10, crates.io grammar crates `tree-sitter-c` 0.24.2,
`tree-sitter-python` 0.25.0, `tree-sitter-rust` 0.24.2, rayon) ports
the walker — iterative descent, emit-whole when a node fits budget or
has no named children, interstitial gap spans, greedy contiguous
merge — and replays the same files.

- **Parity: 500/500 exact span-list matches**, per grammar 265/265 c,
  173/173 python, 62/62 rust. Even across *different grammar
  deliveries* (pack-built dylibs vs crates.io crates) the trees agreed
  on this sample — encouraging, but not a guarantee; the vendoring
  strategy below makes it structural instead of lucky.
- **Serial: 1,203 ms Rust vs 1,266 ms Python (1.1×).** Parse
  dominates and both bindings drive the same C core, so a Rust port
  buys almost nothing single-threaded. Honesty note for the ADR: the
  win is *parallelism and GIL freedom*, not per-parse speed.
- **Rayon (one `Parser` per worker via `map_init`): 2 threads 2.0×,
  4 threads 3.6×, 8 threads 6.3× vs Rust serial** (192 ms for the
  500-file set; 6.6× vs Python). Near-linear to 4, tapering by 8
  (laptop, mixed P/E cores). Projection for the linux corpus's 161 s
  chunk wall: **~25 s at 8 workers**, with the event loop untouched
  (the pyo3 entry would detach the GIL like the existing verify seam).
- The port is small: the walker and merge are ~60 lines of Rust; the
  remaining Python (`split_code`'s oversized-leaf fallback, the
  recursive character splitter, notebook routing) is deterministic
  string logic, straightforward to port and property-test for parity.

## 2. The grammar supply chain vfs stands on today (verified locally)

`tree-sitter-language-pack` ≥1.8 (vfs pins it) is **not** a bundle of
grammars. The installed package is a 3.9 MB pyo3 binding
(`_native.abi3.so`); grammars arrive as **platform dylibs downloaded
on first use** from the project's GitHub releases into a per-user
cache (`~/Library/Caches/tree-sitter-language-pack/v1.8.1/libs` —
69 dylibs, 103 MB, on this machine), `dlopen`ed with hash
verification. Its manifest pins every grammar to an exact upstream
`repo` + `rev` at ABI 14 (`sources/language_definitions.json`, 371
entries in the current repo). Consequences worth recording regardless
of this fork:

- **First chunk of a new file type can hit the network.** An
  air-gapped or locked-down host parses nothing the cache doesn't
  already hold (the pack does support a mirror-override for the
  manifest URL). This behavior is invisible in vfs's docs and tests
  today.
- The pack's own Python wheels went from ~30 MB (0.9, statically
  bundled, 165 languages) to 2.1–2.4 MB + a 21–25 MB zstd per-platform
  bundle (504 MB uncompressed across 371 dylibs) — their scale forced
  download-on-demand; vfs's curated need does not.

## 3. Grammar delivery options (studied)

vfs maps **94 extensions → 68 grammars** (`EXTENSION_TO_GRAMMAR`).

- **crates.io grammar crates** (difftastic's main model — 58 crates on
  one tree-sitter 0.26 runtime, proving the version story workable;
  the `tree-sitter-language`/`LanguageFn` decoupling since late 2024
  ends runtime-version coupling): queried live for all 68 —
  **64 exist, 4 missing** (astro, tcl, terraform, vb), and **25 of the
  64 are stale** (no release since 2024; sql last published 2021,
  svelte/vue/toml 2022). Several healthy ones live under fork names
  (`-ng`, `-orchard`, `tree-sitter-sequel`). Fatal for parity: crate
  revs will not track the pack's pinned revs, so the Rust engine and
  the Python fallback could disagree on tree shape.
- **Vendored generated `parser.c`, compiled by `build.rs` via `cc`**
  (difftastic does this for four grammars; the pack's old model did it
  wholesale; the pack `generate`s parsers at pinned revs with a pinned
  CLI at ABI 14): full rev control. **Vendoring the exact revs from
  the pack's `language_definitions.json` makes Rust-engine and
  Python-fallback trees identical by construction** — the parity
  mechanism, not a hope.
- **Runtime loading** (helix, tree-sitter CLI, the pack's current
  model): smallest wheel, but imports dlopen + download-on-first-use
  semantics into `vfs._native`, which today is a self-contained static
  seam. Runs against the hermetic posture.
- **WASM** (zed's extension model): heavier machinery (wasmtime store)
  than a chunking engine needs; noted, not pursued.

## 4. Size and packaging (measured)

Compiled grammars are almost pure parse tables (`__TEXT` ≈ 98 % of
the dylib), so static linking neither shrinks nor bloats them much:

| grammar | compiled size |
|---|---|
| json | 0.03 MB |
| python | 0.49–0.83 MB |
| c | 0.66 MB |
| rust | 1.2–1.5 MB |
| typescript | 1.8 MB |
| cpp | 5.7–6.0 MB |
| kotlin | 5.9–6.2 MB |
| fsharp | 11.6 MB |
| sql | 11.1–11.4 MB |

The 69 grammars this machine's cache holds total **103 MB**; the
~31-grammar "popular" tier is ~65 MB of object code. Tables deflate
well (~4:1 in a wheel zip): a curated 50–68 grammar static set lands
at roughly **15–25 MB of wheel growth** on today's 449 KB abi3 wheel —
comfortably inside PyPI's **100 MB default per-file cap** (raisable on
request; the full-371 route would not fit and is why the pack moved
off it). The escape hatches the field uses: per-grammar cargo
features (diffsitter, syntastica), strip + `opt-level=s` for the C
objects, and above all *curation* — the tail is where the weight is.
Cold-build cost exists (typescript's parser.c alone is ~8.3 MB of C)
but `cc` compiles grammars in parallel and difftastic sustains ~60
statically linked grammars as a routine `cargo build`.

## 5. Threading and cancellation facts (Rust binding)

`tree_sitter::Parser` is `Send` (one per thread / `map_init` with
rayon — the spike's pattern); `Language` is `Send + Sync` and cheap to
clone, one per grammar feeds every worker. The 0.25/0.26 API replaced
`set_timeout_micros` with a progress-callback abort
(`parse_with_options`) — cooperative cancellation is available if
chunking ever needs a deadline, aligning with the wall-discipline
the matching seam already declares. This is the door the Python
binding slams shut: the pack's `Parser` is a thread-pinned pyo3 class
(the write-vs-reindex memo measured the panic), so parallel chunking
is unreachable from Python, full stop.

## 6. Forks the ADR must settle

1. **Grammar set**: all 68 mapped grammars (~85–100 MB object,
   ~25 MB wheel growth) vs a curated tier with the heavy tail dropped
   (fsharp + sql alone are ~23 MB) — dropped extensions fall back to
   the recursive character splitter exactly as unmapped extensions do
   today, which is a *language-coverage* choice, not a scale cap.
2. **The pure-fallback story**: (a) keep the pack as the pure-Python
   engine at the same pinned revs — chunk parity across engines,
   pinned like the matcher, but the network-download semantics of §2
   persist for pure-only installs; (b) pure fallback degrades to the
   recursive splitter — hermetic, but the two engines emit different
   chunks, breaking the byte-identical-engines law the native seam
   pins today; (c) structure-aware chunking becomes native-only by
   contract. This is the sharpest fork; it decides whether the pack
   dependency survives at all.
3. **Where parity is pinned**: a conformance corpus (the spike's
   dump-and-replay shape) in `tests/test_native.py`'s style, and
   whether grammar-rev bumps are a declared, test-gated event (they
   change stored chunk shapes, which `content_hash`-keyed
   fingerprint-skip would otherwise mask).
4. **Worker count and placement**: rayon inside the pyo3 call (the
   spike's shape, matching the verify seam's detach pattern) — the
   scheduling knob (all cores vs a declared budget) and its
   interaction with the reindex lease belong to the spec.
