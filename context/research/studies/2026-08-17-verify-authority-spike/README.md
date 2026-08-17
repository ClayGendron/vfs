# Study: verify-stage strategies — current, whole-text, prefilter, Rust

Supporting artifacts for `../../2026-08-17-verify-authority-spike.md`
(the memo carries the results table, findings, and the slice-C
recommendation).

## Contents

- `spike.py` — two phases. `candidates` reproduces the 25 benchmark
  rows' candidate + overlay sets in memory from the production planner,
  gate, native engine, and a ladder replica (sanity anchors print
  against the recorded 2026-08-16 run). `bench` races S0 (live
  `verify`), S1 (whole-text `finditer`), and S2 (guaranteed-literal
  prefilter with the Confirmed shortcut), cross-checks all counts
  against S0, measures the str→bytes encode tax, and writes the rust
  manifest.
- `rust/` — the S3 binary (regex crate + memchr + rayon): whole-body
  regex scan with line recovery (single/multi-thread) and the
  memmem-prefilter variant. Standalone crate, outside the repo
  workspace.
- `py_results.json`, `rust_results.json` — raw results (2026-08-17,
  linux checkout `faeab1661`, 93,760 files / 1.59 GB, M-series laptop,
  Python 3.13, median of 3).

## Reproducing

Needs the read-only linux checkout under `~/Git/Repos/linux` (override
with `LINUX`) and a scratch dir for the cache:

```sh
CACHE=/path/to/scratch uv run python spike.py candidates
CACHE=/path/to/scratch RUNS=3 uv run python spike.py bench
(cd rust && cargo run --release -- $CACHE/rust_manifest.json \
    > rust_results.json)
```

Candidate assembly is ~20 s with the native engine active; the bench
phase is dominated by S0 on the wrapped-wildcard row (~130 s × RUNS).
The corpus is a moving checkout — compare strategies within a run, not
absolute numbers across checkout states; the candidates phase prints
the corpus/overlay/truncation anchors to confirm a faithful replica.
