# Study: Rust kernels replace numpy — every remaining site, three arms

Supporting artifacts for `../../2026-08-27-rust-kernels-replace-numpy.md`.

## Contents

- `vfs_kernels_rs/` — the throwaway pyo3 crate (pyo3 0.29, abi3-py311;
  not a workspace member, never shipped): `decode_postings` (packed
  int64 bytes out; `decode_postings_list` as the boxing control),
  `decode_varints`, the fused `intersect_rarest`, `union_sorted`,
  `intersect_sorted`, `decode_summary`, `competing_blocks`. Site 5 uses
  the shipped `vfs._native.lexical_score`.
- `kernels_py.py` — the stdlib-only twins (no numpy): validated varint
  and posting decode, the fused decode+intersect, `bisect` block
  selection, and two scorer spellings (full and block-skip) that
  accumulate in the engines' order so sums are bit-identical.
- `benchlib.py` — store path (`VFS_BENCH_DB`), timing (median of
  `REPEATS`, default 7), `tracemalloc` peak, machine facts.
- `bench_grep_sites.py` — sites 1 and 2 over the live planner's exact
  blob choice per pattern, plus the allow-list intersect.
- `bench_lexical_sites.py` — sites 3, 4 and 5 on the spec 130 landing's
  query draw (seed 7) plus `struct if`.
- `bench_e2e_grep.py` — `DatabaseStorage.grep` under three arms
  (monkeypatches `grep_mod._index_doc_ids` and `grep_mod.np`), with
  stage timers.
- `bench_e2e_lexical.py` — the ADR 055 two-round lexical search under
  three arms, SQL and compute bucketed apart.
- `bench_seam.py` — bytes / list / numpy costs at the `DocIds` boundary
  (slice, `tolist()`, allow-list intersect, payload size).
- `results/` — raw JSON per script (`grep_sites.json`,
  `lexical_sites.json`, `e2e_grep.json`, `e2e_lexical.json`,
  `seam.json`) and the lexical e2e run log. 2026-08-27, Apple M1 Pro,
  Python 3.13.11, rustc 1.97.1.

## Reproducing

The store is the spec 130 landing's full-linux build
(`landing_full.sqlite`, 7.3 GB, schema format 8) — not checked in.
Rebuild it with the landing script, which loads the checkout through
the public write/reindex API:

```sh
cd context/research/studies/2026-08-26-bm25-storage/prototype
uv run --no-sync python landing_bench.py --all --db /path/to/landing_full.sqlite
```

Then build the crate and run the scripts in order (one at a time —
they share the store and the timings are wall-clock):

```sh
cd context/research/studies/2026-08-27-rust-kernels-replace-numpy/vfs_kernels_rs
uvx maturin build --release            # ~11 s; wheel lands in target/wheels/
cd ..
export VFS_BENCH_DB=/path/to/landing_full.sqlite
WHEEL=vfs_kernels_rs/target/wheels/vfs_kernels_rs-*.whl
uv run --project ../../../.. --with $WHEEL python bench_grep_sites.py
uv run --project ../../../.. --with $WHEEL python bench_lexical_sites.py
uv run --project ../../../.. --with $WHEEL python bench_e2e_grep.py
uv run --project ../../../.. --with $WHEEL python bench_e2e_lexical.py
uv run --project ../../../.. --with $WHEEL python bench_seam.py
```

Every script asserts all arms return identical results before timing;
a corruption-parity smoke check (six malformed blobs refused by every
arm) was run by hand and is described in the memo's method. Compare
arms within a run, not absolute numbers across machines.
