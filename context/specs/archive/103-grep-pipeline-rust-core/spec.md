# 103 — Grep pipeline performance: a Rust core for the index build and read path

- **Status: slices A and B complete 2026-08-16** — born from the linux-tree
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
  Rust workspace shaped for the vfs-js / vfs-rs future. Slice B landed
  the same day: the workspace (one `vfs-core` crate, edition 2024,
  binding feature-gated — Clay simplified the two-crate shape in
  review), the maturin mixed layout, the `vfs.native` seam with the
  pure fallback, the build side in Rust, and the CI legs; the linux
  reindex fell 672 s → 191 s, with the surviving 161 s attributed to
  tree-sitter chunking — a new fork recorded in Open questions.
  **2026-08-17:** the verify-authority spike executed
  (`../../../research/2026-08-17-verify-authority-spike.md`) and Clay
  resolved the authority fork against the memo's recommendation:
  **the shared Rust core is the match authority** — one verifier for
  the multi-language future outweighs keeping Python `re` the judge;
  the Intent law and §3 carry the amended shape. **Slice C landed the
  same day** on that design: the `vfs-core` verify module (HIR
  `\n`-strip, wrapping-dot-star reduction, whole-body scan with line
  recovery, rayon batch, in-loop deadline), the `ContentMatcher`
  binding (protocol 2), the shared language gate in
  `pattern_matching.grep` with the pure `re` fallback behind the
  same seam, and both verify call sites (storage batches, router
  chaining) rewired. Measured on the linux candidate sets through
  the production path: zero-hit floor 631 ms → **13 ms** (§4 met),
  wrapped wildcard 130.8 s → **52 ms**, word rows 4.5–5.4 s →
  **50–62 ms**, hit counts identical to the recorded authority on
  every measured row. Both suite legs green at the same count
  (2,391 passed / 838 skipped; coverage 100%; `ruff`/`ty` zero;
  `cargo test` 23), parity/refusal/divergence pins in
  `tests/pattern_matching/test_matcher_parity.py`. **Slice D
  completed 2026-08-17, same day: the bench gate PASSES** — the full
  re-run on the rebuilt store beat rg on every one of the 25 rows
  (vfs 115–644 ms vs rg 2.0–3.6 s; records in the study docstring),
  the ladder re-ran with improvements throughout (reindex build
  4.7 s → 0.9 s at 10K docs, no regressions), `CANDIDATE_BUDGET`
  re-derived 10,000 → 25,000 on the §5 sweep (24 of 25 rows now
  match rg's counts exactly; only `copyright -i`, 62% of the corpus,
  stays loudly truncated), and the decision set is recorded as
  **ADR 039**. The story's one open fork is tree-sitter chunking on
  the reindex path (§2, needs Clay); everything else is done.
  **Fork resolved 2026-08-25:** Clay decided it via **ADR 048**
  (chunking reindex-side by law; the split moves to a rayon-parallel
  Rust engine in vfs-core with all 68 grammars vendored at the
  pack's pinned revs; pure fallback degrades to the character
  splitter; fingerprint-skip stamped by chunk generation), on the
  two 2026-08-25 research memos (write-vs-reindex measurements;
  Rust spike with 500/500 span parity and 6.6× on 8 workers).
  `specs/active/117-rust-chunking-engine/` owns the landing; this
  spec archives when 117 lands.
  **Mined and archived 2026-08-25** (117 landed the same day —
  reindex 191 s → 54 s, meeting the ≤60 s verb target this spec had
  to leave unmet): residue was already downstream — the decision set
  is ADR 039 (refined by 046), the chunking fork's resolution is
  ADR 048, and the four research memos, the verify-authority spike,
  and the two studies landed as they were produced. Folder stays as
  the historical record.
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

The law that binds every slice — **amended 2026-08-17** (Clay, in
session, resolving the verify-authority fork on the spike's evidence,
`../../../research/2026-08-17-verify-authority-spike.md`): **match
semantics are defined once, in the shared Rust core, for every
language surface** — the vfs-py / vfs-js / vfs-rs roadmap means one
verifier all bindings share, not per-language authorities that drift.
The grep pattern language is the regex-crate language (ripgrep's):
constructs beyond it (backreferences, lookarounds) classify
`invalid`, as ripgrep refuses them. The original law's residue
stands where it always mattered: the planner's algebra, caps, and
refusal gate keep their landed shapes; every *prefilter* remains a
necessary condition; the pure-Python fallback engine approximates
the authority with battery-pinned, documented divergences (the
spike measured zero across ~250K matched lines — the accepted
residual of wheel-less installs). A wrong answer fast is still not
an optimization.

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
- **§2 Build side — landed (slice B, 2026-08-16).** The shape that
  landed: extraction, the distinct-gram eligibility gate, postings
  grouping, and varint encode all run in the `vfs-core` engine behind
  the `vfs.native` seam (GIL released per feed batch). The build
  streams — content is fetched with a server-side cursor in bounded
  batches, docs arrive in ascending row-id order, and each gram's
  deltas are varint-encoded *incrementally on arrival*, so peak build
  memory is the compressed posting set (what gram-range partitioned
  re-scans would have bought, without paying P× content fetches); the
  drain feeds gram-ordered, byte-capped inserts. Fold ownership
  resolved: **Python folds** (`casefold` is C-speed; ~3 s of the
  191 s run) and the engine receives pre-folded bytes — one fold
  implementation, no orbit-parity burden on Rust; revisit only if a
  measured need appears. Measured on the linux corpus: `build_epoch`
  272 s → ~6 s, the gate's extraction pass ~192 s → ~3 s. **The ≤60 s
  verb target was NOT met** — reindex is 191 s because tree-sitter
  `Chunk.split` (161 s, GIL-bound, thread-unparallelizable) was hiding
  inside the 672 s unattributed; the grep-index build proper is
  ~30 s. The chunking fork is recorded in Open questions.
- **§3 Read side — reshaped 2026-08-17 by the verify-authority
  resolution and the spike's numbers; landed the same day (slice C)
  with one simplification: the wrapping-dot-star strip happens at
  the HIR level and the crate's own literal engine does the
  prefiltering, so the separate memmem Confirmed/Candidate stage
  below was never needed — no hit runs a second engine**
  (`../../../research/2026-08-17-verify-authority-spike.md`). The
  profile pins the target: verify is 82–99.7% of every query while
  all index stages together cost ≤ 25 ms — the read-side rewrite is
  the verify stage, full stop. The discipline is the field consensus
  the prior-art memo records (*lines are presentation, not
  matching*):
  - the planner's **longest guaranteed literal run** rides the plan
    into the verify stage; candidate content is scanned for that
    literal in Rust (memmem; folded stream for case-insensitive
    patterns, raw for case-exact) — never pre-split into lines; per
    hit, the enclosing line is recovered backward/forward. The
    reduction is mandatory in both engines: the spike measured the
    wildcard row at 1,150 ms under the raw regex crate (its DFA
    does not strip wrapping `.*`) vs 24 ms with the literal
    prefilter.
  - **Confirmed vs Candidate hits** (ripgrep's `LineMatchKind`
    shape): when the literal is the whole effective pattern
    (leading/trailing `.*` stripped — `.*alloc_page.*` reduces to a
    substring search), the hit is already confirmed and no matcher
    runs; case-exact patterns still verify case on the raw slice.
    This alone deletes the 102 s pathology.
  - **Candidate lines are judged by the shared verifier in
    `vfs-core`** (the regex crate, `\n` stripped from classes via
    the regex-syntax HIR — rg's transform — so whole-text scanning
    keeps the per-line law). The pure-Python fallback engine judges
    the same recovered lines with Python `re`, the approximation
    whose divergences the battery pins.
  - verify parallelized across entries while the Rust scan holds no
    GIL (`allow_threads`; no abi3 restriction).
  - the **wall deadline moves inside the hit loop** — the profile
    caught the wildcard row running 102 s against a 10 s budget
    because the deadline is only consulted between content batches.
  The prefilter discipline is unchanged: literal scans only discard
  what cannot match, and fold-comparison keeps the orbit invariant
  (never ASCII-lowercase; the index fold remains a superset of the
  crate's simple-fold orbit, so the index needs no change).
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
- **§5 Budgets at scale — resolved 2026-08-17 (slice D), by
  measurement: 25,000, a constant.** The sweep (10k/25k/50k/100k/
  200k over the nine truncated rows on the rebuilt store) showed
  candidate cost is fetch-dominated at ~75 µs each and plateaus at
  each row's natural width: eight of nine rows fully un-truncate by
  25,000 at 740–1,800 ms, all under rg. Corpus-scaling was
  considered and rejected — it makes hot-row latency grow with
  corpus size, backwards for the latency-sensitive agent audience —
  and 50,000+ only chases `copyright -i` (57,832 files, 62% of the
  corpus, bulk retrieval) past rg's own time. Truncation record and
  refine guidance unchanged; wall deadline unchanged.

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
- **The authority change is pinned, not assumed:** the battery runs
  the same cases through the Rust verifier and the pure-Python
  fallback and pins their agreement on the supported language;
  patterns outside the language (backreferences, lookarounds)
  classify `invalid` with a message naming the refusal, pinned on
  both engines; the known divergence catalog (the spike memo's
  finding 7) gets a test per entry documenting the fallback's
  accepted residual.
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
- **B** — **done 2026-08-16**: `crates/vfs-core` (edition 2024, one
  crate, pyo3 behind the `python` feature — engine stays binding-free
  for the vfs-js/vfs-rs future), maturin mixed layout replacing
  hatchling, the `vfs.native` seam (`vfs._native` extension, protocol
  gate, `VFS_PURE_PYTHON` escape, `active_core()` diagnostics, pure
  reference builder), `build_epoch`/`_indexable` rewired and
  streaming, byte-for-byte parity suite (`tests/test_native.py`),
  publish.yml wheel matrix (maturin-action, abi3-py311, manylinux_2_28
  + musllinux + macOS both arches + Windows + sdist), pure-fallback CI
  leg in test.yml and ci.sh. Reindex 672 s → 191 s; build-side numbers
  and the surviving chunking cost recorded in §2 and the build-profile
  study.
- **C** — **done 2026-08-17** (see Status): read side on the amended
  law. The landed shape simplified the drafted one: the regex
  crate's own literal engine plus the HIR wrapping-dot-star
  reduction replaced a separate memmem Confirmed/Candidate stage —
  the crate's prefilters already run at memmem speed once the
  wrapping `.*` is stripped structurally, so no hit ever runs a
  second engine. Wildcard and word rows measured 50–62 ms against
  rg's recorded 3.0–3.6 s floor. Big-file caps unchanged this
  slice: the 96-entry overlay tail now costs ~13 ms per call, so
  no cap pressure remains — revisit only if slice D's bench re-run
  disagrees.
- **D** — **done 2026-08-17**: the bench-gate re-run recorded (all
  25 rows beat rg; study docstring carries the 10,000-budget gate
  run and the 25,000-budget landed run), the ladder re-run recorded
  (improvements throughout), `CANDIDATE_BUDGET` → 25,000 on the §5
  sweep, ADR 039 written, spec and STATUS trued.

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
- **Verify authority — resolved 2026-08-17** (Clay, in session, on
  the spike's evidence): **the shared Rust core judges matches**,
  overriding the spike memo's keep-Python-`re` recommendation. The
  deciding fact is the roadmap, not speed: vfs-py, vfs-js, and
  vfs-rs must return identical answers, which one verifier in
  `vfs-core` gives structurally and per-language authorities never
  would. Consequences accepted with the decision: the grep pattern
  language is the regex-crate language (ripgrep-compatible;
  backreferences and lookarounds classify `invalid`); drift risk
  inverts onto the pure fallbacks (Python `re` today, JS later),
  confined to extension-less installs and battery-pinned; the
  index fold already supersets the crate's case orbit, so the
  index is untouched. The spike's parity evidence (25/25 rows,
  ~250K matched lines identical) is the empirical basis.
- **Fold ownership — resolved 2026-08-16 (slice B):** Python folds and
  the engine receives pre-folded bytes. Measured basis: the whole
  Python-side fold+normalize pass costs ~3 s of a 191 s reindex, so
  moving it to Rust buys nothing today, while reproducing
  `str.casefold` in Rust would carry an exact-orbit parity burden
  across CPython Unicode versions. The bytes-in seam keeps the shapes
  swappable if that ever changes.
- **Semantic chunking on the reindex path — new fork from slice B's
  measurement (needs Clay):** tree-sitter `Chunk.split` is now 84% of
  the reindex verb (161 s of 191 s on the linux corpus) and serves
  only the embedding pipeline — no gram-path code reads chunk rows.
  It cannot be thread-parallelized (the tree_sitter pyo3 binding holds
  the GIL through `parse`; its `Parser` is thread-pinned — measured
  1.0× on 8 threads). Options: (a) process-pool the splits inside
  `chunk_dirty` (~8× on this machine, but a library verb spawning
  worker processes is a real posture question); (b) move chunking off
  the reindex path (own verb, or lazy on the embedding pipeline's
  schedule) — a contract change; (c) accept the verb's wall and state
  the grep-index build alone meets the target; (d) a Rust tree-sitter
  path in vfs-core (real threads, but grammar-set parity is a big
  scope). The ≤60 s verb target stands or falls on this choice.
- **Bench-gate hardware:** the bar is pinned to the recorded
  machine and method (M-series laptop, rg-on-checkout, warm cache,
  median of 3). A different machine re-baselines rg first — the
  gate is relative, never a stored absolute.
