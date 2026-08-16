# 103 — Grep pipeline performance: a Rust core for the index build and read path

- **Status: draft 2026-08-16** — born from the linux-tree benchmark
  (`../../../research/studies/2026-08-16-linux-grep-benchmark/`),
  which put numbers on the pipeline's interpreted hot loops at real
  scale. Clay's directional resolution in session (2026-08-16): the
  measured-slow parts of the grep index build and read path move to
  **Rust**, with the acceptance bar set at **outperforming rg on
  every row of the recorded benchmark** — not just the selective
  rows the index already wins. Research-first: slice A's memos gate
  the design; no code before the packaging fork is resolved.
- **Date:** 2026-08-16
- **Owner:** Clay Gendron
- **Kind:** performance rewrite of the grep hot loops behind
  unchanged contracts — the verbs, the algebra, the refusal gate,
  the Result shapes, and the soundness authorities do not move.
- **Depends on:** ADR 033 (gate, budgets, epoch lifecycle), ADR 036
  (entry-grain extraction), ADR 038 (planner caps and the variant
  compiler), spec 100 (landed planner).
- **Relates to:** the linux benchmark study (five measured targets),
  `build_epoch`'s recorded whole-corpus-resident profile
  (`storage/backends/database/indexing.py`), the open-questions
  entry "Rust extension posture for the grep pipeline."

## Intent

The 2026-08-16 benchmark (93,760 files / 1.59 GB, 25 queries) named
five costs, all interpreted-throughput problems, none design
problems:

1. **Index build: 672 s at ~2.4 MB/s** — the pure-Python per-byte
   trigram loop (`_iter_byte_trigrams`) walks 1.6 B positions
   through the interpreter; postings accumulation and delta-varint
   encoding are Python loops over hundreds of millions of entries.
2. **A ~700 ms fixed per-call floor at 94K docs** (1.7 ms at 10K in
   the ladder) — unattributed; profile before designing.
3. **Verify-heavy rows lose to rg** (word mode, hot alternations:
   4.9–5.9 s vs rg's ~3.4 s) — Python `re` over tens of thousands
   of candidate entries dominates.
4. **The wrapped-wildcard pathology: 102 s** — the trigrams of
   `alloc_page` are individually common, the conjunction admits a
   huge candidate set, and the leading-`.*` verify pays per line.
5. **The 4 MB candidate budget truncates 9 of 25 rows** at this
   corpus size — loud and sound, but sized for a smaller world.

The law that binds every slice: **Rust replaces throughput, never
semantics.** Python `re` over raw content remains the sole match
authority; the planner's algebra, caps, and refusal gate keep their
landed shapes; every Rust-side filter is a *necessary* condition —
the same soundness discipline the gram planner already follows,
extended down the pipeline. A wrong answer fast is not an
optimization.

## Shape

- **§1 The Rust core and its boundary.** One extension module
  (pyo3, maturin-built) owning byte-level throughput: trigram
  extraction over the folded stream, per-doc unique-gram sets,
  postings grouping, delta-varint encode/decode, and read-side line
  scanning. The Python/Rust seam passes bytes and numpy arrays,
  never Python objects per gram. The current pure-Python
  implementations remain in-tree as the reference and fallback path
  — one import seam selects the core, and the full suite runs green
  on both sides of it.
- **§2 Build side.** Extraction parallelized across entries in Rust
  (GIL released), postings grouped and varint-encoded in Rust, and
  the build streamed in gram-range partitions — discharging the
  whole-corpus-resident profile `build_epoch`'s docstring records as
  a known suboptimality. Target: the linux corpus reindexes in
  **≤ 60 s** (stretch: ≤ 15 s), from 672 s.
- **§3 Read side.** Three moves, all candidate-narrowing:
  - the planner's **longest guaranteed literal run** rides the plan
    into the verify stage; candidate content is pre-scanned for that
    folded literal in Rust (memmem) before any regex runs — zoekt's
    discipline (two rarest trigrams from postings, the rest by
    string comparison). This alone collapses the wrapped-wildcard
    row: 418 real hits stop paying regex over a trigram-coincidence
    candidate set.
  - line selection in Rust: only lines containing the literal (or,
    for literal-less plans, all lines) reach Python `re`.
  - verify parallelized across entries while the Rust scan holds no
    GIL.
  Authority unchanged: every admitted line still passes through
  Python `re`; the prefilter only discards lines that cannot match.
- **§4 The per-call floor.** Profile first (slice A) — the 700 ms is
  unattributed and may be table-scan-shaped (an O(corpus) check per
  call). Fix what the profile names. Target: zero-hit ≤ 25 ms at
  94K docs.
- **§5 Budgets at scale.** Re-derive `POSTING_BYTE_BUDGET` against
  the 5 GB index reality — likely corpus-scaled rather than
  constant, with the truncation record and refine guidance
  unchanged. The 9 truncated benchmark rows should serve complete
  within their time targets; truncation remains for genuinely
  adversarial widths.

## Research tasks (slice A, bounded — before any code)

- **Packaging and distribution memo:** pyo3 + maturin + abi3 wheel
  matrix (macOS arm64/x86_64, manylinux, Windows), sdist behavior
  without a Rust toolchain, the import-seam fallback design, CI
  wheel builds, and how the extension coexists with the uv dev
  flow. This memo resolves the dependency-posture fork below.
- **Profiling memo:** attribute the 700 ms floor and the
  verify-stage cost split (candidate fetch / content load / line
  split / regex) on the built linux index — the benchmark scratch
  is reusable.
- **Prior-art study (read-only):** zoekt's `contentProvider`
  verification discipline, codesearch's post-filter, ripgrep's
  internals (`memchr`/`memmem`, Teddy multi-substring) — design
  input for §3's prefilter shape; cite, never copy.

## Verification obligations

- **Soundness is regression-gated, not argued:** the grep
  differential battery (planner edition, 181 case-checks) re-runs
  green across the four worlds on **both** sides of the import seam;
  if folding moves to Rust, a pinned exhaustive test proves
  Rust-fold == `fold_content` over every codepoint (the orbit-scan
  machinery already exists in the suite).
- **The bench gate:** the linux benchmark re-runs with the same
  method (rg on the original checkout) and **every one of the 25
  rows beats rg**, including `.*alloc_page.*` and the word rows;
  build time hits the §2 target; the run is recorded in the study
  docstring beside the 2026-08-16 baseline.
- The query-ladder benchmark re-runs; the 10K-doc numbers must not
  regress (the floor fix should improve them).
- A CI leg runs the suite without the extension installed — the
  fallback path is a first-class citizen, not a stale copy.
- No contract drift: gate message, algebra shapes, Result envelope,
  and verb signatures byte-identical before and after.

## Slices

- **A** — the three slice-A memos; packaging fork resolved with
  Clay; targets confirmed against the profile.
- **B** — build side: extraction/grouping/encode in Rust behind the
  import seam; partitioned build; reindex target met.
- **C** — read side: literal-run prefilter, Rust line selection,
  parallel verify; wildcard and word rows beat rg.
- **D** — floor fix, budget re-derivation, the bench gate re-run
  recorded, ADR for the decision set, true-ups.

## Open questions

- **Dependency posture** (the fork slice A must resolve): required
  compiled dependency vs optional accelerator with the pure-Python
  fallback. Production posture argues for the accelerator shape
  (wheels for the platform matrix, sdist still installs anywhere);
  the bench gate then binds the accelerated path. Owned by the
  packaging memo; pointered in `../../../open-questions.md`.
- **Fold ownership:** does the Rust core reproduce the fold (one
  pass, pinned by the exhaustive orbit test) or receive pre-folded
  bytes from Python (two passes over content, no duplication risk)?
  Decide on the profile's numbers in slice A.
- **Bench-gate hardware:** the bar is pinned to the recorded
  machine and method (M-series laptop, rg-on-checkout, warm cache,
  median of 3). A different machine re-baselines rg first — the
  gate is relative, never a stored absolute.
