# 103 — Grep pipeline performance: a Rust core for the index build and read path

- **Status: slice A complete 2026-08-16** — born from the linux-tree
  benchmark
  (`../../../research/studies/2026-08-16-linux-grep-benchmark/`),
  which put numbers on the pipeline's interpreted hot loops at real
  scale. Clay's directional resolution in session (2026-08-16): the
  measured-slow parts of the grep index build and read path move to
  **Rust**, with the acceptance bar set at **outperforming rg on
  every row of the recorded benchmark** — not just the selective
  rows the index already wins. Slice A's three memos landed the same
  day (profile: `../../../research/2026-08-16-grep-read-path-profile.md`;
  prior art: `../../../research/2026-08-16-verify-stage-prior-art.md`;
  packaging: `../../../research/2026-08-16-rust-accelerator-packaging.md`)
  and Clay resolved the posture fork in two steps: pure-Python
  fallback stays, and — after rejecting the memo's two-package
  recommendation at review — **one package, the pendulum model**
  (maturin mixed layout, fallback inside every wheel; §1), with the
  Rust workspace shaped for the vfs-js / vfs-rs future. Slices B–D
  are unblocked.
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

- **§1 The Rust core and its boundary — one package, pendulum
  model.** `vfs-py` moves to maturin's mixed Rust/Python layout: the
  complete pure-Python implementation keeps shipping inside every
  wheel, and the extension module rides beside it on platforms with
  wheels (`abi3-py311` — one wheel per platform). Runtime
  try-imports the extension, checks a small protocol version, warns
  once on mismatch, and falls back; which core is active is exposed
  for tests and diagnostics. Wheel-less platforms build from the
  sdist with maturin's self-bootstrapping toolchain (≥ 1.8.4) — a
  toolchain download rather than a pure install is the recorded
  residual of rejecting the two-package shape. The Rust side is a
  workspace **designed for the multi-language future** (Clay,
  2026-08-16: vfs-js and vfs-rs sibling implementations are the
  roadmap): engine logic — trigram extraction over the folded
  stream, per-doc unique-gram sets, postings grouping, delta-varint
  codec, content scanning — lives in binding-free core crates under
  `crates/`; the pyo3 crate is a thin binding embedded in the
  vfs-py wheel, and future napi/wasm or native-Rust surfaces bind
  the same cores. The seam passes buffer-protocol bytes in and
  bytes/ints out — **no rust-numpy** (no advertised abi3 support;
  the packaging memo records the facts) and never Python objects
  per gram. The pure-Python implementations remain in-tree as the
  reference and fallback path, and the full suite runs green on
  both sides of the seam.
- **§2 Build side.** Extraction parallelized across entries in Rust
  (GIL released), postings grouped and varint-encoded in Rust, and
  the build streamed in gram-range partitions — discharging the
  whole-corpus-resident profile `build_epoch`'s docstring records as
  a known suboptimality. Target: the linux corpus reindexes in
  **≤ 60 s** (stretch: ≤ 15 s), from 672 s.
- **§3 Read side.** The profile pins the target: verify is 82–99.7%
  of every query while all index stages together cost ≤ 25 ms — the
  read-side rewrite is the verify stage, full stop. The discipline
  is the field consensus the prior-art memo records (*lines are
  presentation, not matching*):
  - the planner's **longest guaranteed literal run** rides the plan
    into the verify stage; candidate content is scanned for that
    folded literal in Rust (memmem) — never pre-split into lines;
    per hit, the enclosing line is recovered backward/forward and
    only that line slice reaches the authority.
  - **Confirmed vs Candidate hits** (ripgrep's `LineMatchKind`
    shape): when the literal is the whole effective pattern
    (leading/trailing `.*` stripped — `.*alloc_page.*` reduces to a
    substring search), the hit is already confirmed and Python `re`
    never runs; case-exact patterns still verify case on the raw
    slice. This alone deletes the 102 s pathology (3,720 candidates
    at 4.5% precision reduce to memmem + 418 line recoveries).
  - verify parallelized across entries while the Rust scan holds no
    GIL (`allow_threads`; no abi3 restriction).
  - the **wall deadline moves inside the hit loop** — the profile
    caught the wildcard row running 102 s against a 10 s budget
    because the deadline is only consulted between content batches.
  Authority unchanged: every admitted line still passes through
  Python `re`; the prefilter only discards what cannot match, and
  fold-comparison keeps the orbit invariant (never ASCII-lowercase).
- **§4 The per-call floor — attributed.** The profile found it: 96
  permanently-unindexed entries (over `MAX_INDEXABLE_BYTES` = 2 MB
  or 20K distinct grams; linux's amdgpu headers, 366 MB) are
  content-fetched and line-by-line regexed on **every** call —
  1.1 s even for zero-hit queries. The fix is §3's own mechanism —
  memmem over the overlay tail costs ~0.1–0.3 s and Confirmed hits
  skip regex — so the floor needs no separate machinery. Whether
  the big-file caps themselves rise is decided on slice C's
  measurements. Target: zero-hit ≤ 25 ms at 94K docs where the
  overlay tail is empty; ≤ the memmem cost of the tail otherwise.
- **§5 Budgets at scale.** Re-derive `CANDIDATE_BUDGET` (10,000
  entries — the cap the nine truncated benchmark rows actually hit;
  the posting-byte budget was the first record's misattribution,
  since corrected) against the 5 GB index reality — likely
  corpus-scaled rather than constant, with the truncation record
  and refine guidance unchanged. With §3's rejection speed, a much
  larger candidate set is affordable; truncation remains for
  genuinely adversarial widths.

## Research tasks (slice A) — **done 2026-08-16**

- **Packaging memo** — landed as
  `../../../research/2026-08-16-rust-accelerator-packaging.md`:
  two-package shape forced (maturin has no optional-extension mode),
  psycopg-model exact-pin extra, `abi3-py311` one-wheel-per-platform
  with the buffer protocol available and `allow_threads`
  unrestricted, no rust-numpy, uv workspace layout, maturin-action
  CI on native arm runners, sdist published (self-bootstrapping
  toolchain since maturin 1.8.4). Resolved the posture fork.
- **Profiling memo** — landed as
  `../../../research/2026-08-16-grep-read-path-profile.md`: verify
  is 82–99.7% everywhere; the floor is the 366 MB unindexable
  overlay tail re-verified per call; candidate precision 47%
  (`pr_debug`) and 4.5% (wildcard); the wall deadline's batch
  granularity let 10 s become 102 s; `CANDIDATE_BUDGET`
  misattribution corrected.
- **Prior-art memo** — landed as
  `../../../research/2026-08-16-verify-stage-prior-art.md`: the
  cross-tool law (lines are presentation, not matching), ripgrep's
  inner-literal Confirmed/Candidate contract, zoekt's
  two-rarest-trigrams + verify-by-comparison and cost-staged
  evaluation, codesearch's line-aware byte-DFA floor.

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

- **A** — **done 2026-08-16**: the three memos landed; posture fork
  resolved with Clay; targets confirmed against the profile (§3–§5
  updated from its attributions).
- **B** — build side: extraction/grouping/encode in Rust behind the
  import seam; partitioned build; reindex target met.
- **C** — read side: literal-run prefilter with Confirmed/Candidate
  hits, line recovery around hits, parallel verify, in-loop
  deadline; wildcard and word rows beat rg; big-file cap decision
  on this slice's measurements.
- **D** — budget re-derivation, the bench gate re-run recorded, ADR
  for the decision set, true-ups.

## Open questions

- **Dependency posture — resolved 2026-08-16** (Clay, in session,
  in two steps): pure-Python fallback stays; the shape is **one
  package, the pendulum model** — Clay rejected the memo's
  two-package recommendation at review, a staff-pattern survey
  surfaced the maturin mixed-layout shape (pendulum 3's), and Clay
  picked it, adding the vfs-js / vfs-rs roadmap constraint §1
  records. The bench gate binds the accelerated path; the resolved
  open-questions entry moved to
  `../../../open-questions-archive.md`.
- **Fold ownership:** does the Rust core reproduce the fold (one
  pass, pinned by the exhaustive orbit test) or receive pre-folded
  bytes from Python (two passes over content, no duplication risk)?
  The bytes-in seam makes the two shapes swappable — decide in
  slice B on measured extraction throughput.
- **Bench-gate hardware:** the bar is pinned to the recorded
  machine and method (M-series laptop, rg-on-checkout, warm cache,
  median of 3). A different machine re-baselines rg first — the
  gate is relative, never a stored absolute.
