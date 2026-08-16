# Grep read-path profile at linux scale: verify is the whole story

- **Status**: research memo — slice A of the Rust-core story (spec
  103); attributes the per-call floor and the verify-stage cost the
  linux benchmark measured, so the Rust boundary is drawn from
  numbers, not guesses
- **Date**: 2026-08-16
- **Owner**: Clay Gendron
- **Question**: Where does grep's read path actually spend its time
  at 94K docs / 5 GB index — which stages does the Rust core need to
  own, and what explains the ~700 ms per-call floor and the 102 s
  wrapped-wildcard row?
- **Evidence**: executed stage profile
  (`studies/2026-08-16-grep-pipeline-profiling/profile_grep.py`) over
  the linux benchmark's built store — cProfile cumulative time
  bucketed into pipeline stages plus tier counters wrapped around the
  live functions; direct inspection of the store's flag distribution.

---

## 1. The numbers

Four query shapes through the public `DatabaseStorage.grep`
(cProfile adds roughly 10–30% to absolute times; shares are the
signal):

| query | total | verify | content fetch | all index stages | candidates (index + overlay) | files matched |
|---|---:|---:|---:|---:|---|---:|
| zero-hit `xyzzy_…_42` | 1.28 s | **88.2%** | 7.6% | ≤1.1% | 3 + 96 | 0 |
| selective `randomize_kstack_offset` | 1.37 s | **85.9%** | 9.2% | ≤1.8% | 64 + 96 | 8 |
| word `pr_debug` | 8.73 s | **82.0%** | 12.1% | ≤1.5% | 4,803 + 96 | 2,260 |
| wrapped `.*alloc_page.*` | 102.4 s | **99.7%** | 0.1% | ≤0.2% | 3,720 + 96 | 166 |

## 2. Findings

**The verify stage is 82–99.7% of every query; the index side is
already free.** Posting meta, blob fetch, varint decode, doc-id
intersection, and doc→entry resolution together cost ≤ 25 ms even on
the widest rows at the 5 GB index. The read-side Rust boundary is
therefore the verify stage (and the content fetch behind it, a
steady ~10%) — the SQL/posting machinery needs nothing.

**The per-call floor is 96 permanently-unindexed big files — 366 MB
re-verified on every call.** `_indexable` excludes entries over
`MAX_INDEXABLE_BYTES` (2 MB) or 20K distinct grams
(`indexing.py:389`); the linux corpus has 96 such entries (amdgpu
register headers up to 24 MB, 366 MB total, 23% of corpus bytes).
Sound by design — unindexed entries must ride the scan overlay — but
the cost lands on *every* query: the zero-hit row spends 1.13 s
running Python `re` line-by-line over those 96 files. Arithmetic
checks: Python literal `finditer` sustains ~300 MB/s, and
366 MB ≈ 1.2 s. The floor grows with a corpus's unindexable tail,
not its size.

**Candidate precision quantifies the trigram conjunction's
weakness.** `pr_debug`: 4,803 candidates → 2,260 matching files (47%
precision — the wasted 53% still pays full line-by-line regex).
`.*alloc_page.*`: 3,720 candidates → 166 matching files (4.5%
precision; ~27 ms of regex per candidate). A cheap
literal-substring rejection (`alloc_page` is a guaranteed run of the
pattern) would discard 95% of those candidates without running the
regex at all.

**The wall deadline is consulted at batch granularity only.** The
wildcard row ran 102 s against a 10 s `WALL_TIME_BUDGET`: the
deadline is checked between content batches (`grep.py:240`), and the
verify of an admitted batch runs to completion however long it
takes. Truthfully flagged, but the budget does not bound what it
claims to bound.

**Correction to the benchmark's first record**: the nine truncated
rows hit `CANDIDATE_BUDGET` (10,000 candidate entries,
`grep.py:91`), not the 4 MB posting-byte budget; the run record was
amended.

## 3. Implications for spec 103

- **Read side (§3): the Rust core's one job is candidate
  rejection-before-regex.** Longest-guaranteed-run memmem prefilter
  over content, line selection around hits only, Python `re` kept as
  the authority over the surviving lines. At memmem throughput
  (~GB/s/core), even the 366 MB overlay tail costs ~0.1–0.3 s — the
  floor falls out of the same mechanism; it needs no separate fix.
- **The big-file caps can be revisited but need not be.** Raising
  `MAX_INDEXABLE_BYTES`/`MAX_DISTINCT_GRAMS` (the build-memory
  guards) would shrink the overlay tail, but with a Rust prefilter
  the tail is cheap; decide on slice C's measurements, not now.
- **Deadline enforcement moves inside the verify loop** (per entry,
  or per N lines in Rust) so `wall_seconds` bounds what it names —
  §5's budget re-derivation gains this row.
- **Build side (§2) is untouched by these findings**: the 672 s
  reindex remains extraction-loop-bound as the benchmark recorded;
  nothing here changes that target.
- Restated for the bench gate: with verify at 82–99.7%, beating rg
  on every row is a verify-stage rewrite plus the floor fix — the
  posting ladder already holds its end.

## 4. Limitations

Single machine (M-series laptop), warm cache, sqlite backend;
cProfile inflates absolute times so shares and counters carry the
findings. The 96-file overlay composition is linux-specific —
corpora without a big-file tail have no floor beyond connection
overhead (the 10K-doc ladder's 1.7 ms zero-hit stands as that
control). Stage buckets attribute via function names in the live
modules; renames will need the script's table refreshed.
