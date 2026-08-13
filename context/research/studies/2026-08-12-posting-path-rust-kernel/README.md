# Study: posting-path decode+intersect — stdlib vs numpy vs Rust kernel

Supporting artifacts for `../../2026-08-12-posting-path-rust-kernel.md`.

## Contents

- `bench_python_vs_numpy.py` — three-arm bench (numpy / py_naive /
  py_fused) at the planner's k=4 rarest-first choice.
- `bench_rust_arm.py` — four-arm bench adding rust_fused and the
  rust_decode_only control.
- `vfs_postings_rs/` — the PyO3 crate (abi3-py311): `decode_postings`
  plus the fused `intersect_rarest` (two-pointer merge, survivors only
  cross the boundary).
- `bench_py_vs_np.json`, `bench_rust_arm.json` — raw results
  (2026-08-12, Apple Silicon, Python 3.13, rustc 1.97.1).
- `query_bench_990000.json` — full-pipeline stage timings (k sweep
  1/2/3/4/8/16/all) from the 072 spike harness on the same corpus;
  provides the pipeline totals the memo's percentages divide by.

## Reproducing

The 1.8 GB corpus and 440 MB gram index are not checked in. Rebuild
them with the 072 spike scripts (which also define the data-dir
convention — set `SPIKE_DATA` to choose the location):

```sh
cd context/specs/active/072-database-storage-backend/spike
SPIKE_DATA=/path/to/spike-data uv run python build_corpus.py
SPIKE_DATA=/path/to/spike-data uv run python build_index_sqlite.py 990000
```

Then update `DATA` in the bench scripts to the same location, build the
crate, and run:

```sh
cd vfs_postings_rs && uvx maturin build --release
uv run --with target/wheels/vfs_postings_rs-*.whl python ../bench_rust_arm.py
```

The corpus draws from the read-only reference checkouts under
`~/Git/Repos/` (see `spikelib.CORPUS_REPOS`); byte-identical corpora are
not guaranteed across checkout states, so re-runs should compare arms
within a run, not absolute numbers across runs.
