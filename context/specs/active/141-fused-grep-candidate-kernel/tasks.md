# 141 — tasks

## Slice A — the kernel

- [ ] A1 `crates/vfs-core/src/postings.rs`: `Postings` streaming
      decoder with `PostingError` variants whose messages match the
      pure codec's; unit tests per refusal.
- [ ] A2 `candidate_ids(groups, allow, cap) -> (Vec<i64>, usize)`:
      rarest-first sorted-merge AND, k-way OR with dedup, allow merge,
      cap; unit tests for K1–K6 laws on small vectors.
- [ ] A3 `python.rs`: the `#[pyfunction]` over `Vec<Vec<PyBackedBytes>>`,
      `allow_threads`, `ValueError` mapping; `PROTOCOL_VERSION = 5`;
      `EXPECTED_PROTOCOL = 5`; `_native.pyi` signature; `lib.rs`
      export.
- [ ] A4 `uv sync --reinstall-package vfs-py`; `cargo test -p vfs-core`.
- [ ] A5 `tests/support/oracles/postings.py`: stdlib `decode_varints`
      / `decode_postings` with the refusal catalog.
- [ ] A6 `tests/test_native.py::TestCandidateKernel`: 200 generated
      cases + hand cases (K2, K3, K5, K6, `MAX_DOC_ID`) against the
      oracle; the `slow` timing pin for K1.
- [ ] A7 Gate: `scripts/ci.sh 3.13` green (product untouched; the
      new function is covered by the parity test through the seam).

## Slice B — the call sites

- [ ] B1 `grep.py`: one `candidate_ids` call replaces `_index_doc_ids`
      + allow intersect + cap; `DocIds = list[int]`; `.tolist()` gone;
      `PostingCorruptionError` re-raised from `ValueError`; numpy
      import gone; module docstring's numpy sentence rewritten.
- [ ] B2 `postings.py`: delete `decode_varints`, `decode_postings`,
      numpy; rewrite the module docstring.
- [ ] B3 Re-point every test that decoded blobs (`test_postings.py`,
      `test_lexical.py`, `test_indexing.py`,
      `storage/database/test_lexical.py`) at the oracle codec; drop
      `np.` from those files where nothing else needs it.
- [ ] B4 Refusal suite routed through `grep` (K4): storage fixture
      with a planted corrupt posting row per catalog case.
- [ ] B5 Per-engine-leg blob-type pin (`bytes` reaches the kernel) —
      in the storage conformance suite so all four legs run it.
- [ ] B6 Gate: `scripts/ci.sh 3.13` at 100 %; `db_test` four legs.

## Slice C — measurement and landing

- [ ] C1 Re-run `bench_grep_sites.py` and `bench_e2e_grep.py` from the
      2026-08-27 study against the live kernel on the spec 130 landing
      store; record in the study dir as `results/after-141.json`.
- [ ] C2 Fill the criteria table; landing note; `STATUS.md`; move to
      `archive/`.
