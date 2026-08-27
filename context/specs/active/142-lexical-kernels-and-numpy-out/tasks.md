# 142 — tasks

## Slice A — the two kernels

- [ ] A1 `tests/support/oracles/lexical.py`: stdlib `decode_summary`
      and `competing_blocks` oracles; parity tests in
      `tests/test_native.py::TestLexicalKernels` written first
      (boundary case for L3, best-plus-max case for L2, refusal for
      L1).
- [ ] A2 `crates/vfs-core/src/lexical.rs`: `decode_summary` (confirm
      the byte layout from the encoder; round-trip unit test) and
      `competing_blocks`; unit tests.
- [ ] A3 `python.rs`: the two `#[pyfunction]`s over packed bytes;
      `PROTOCOL_VERSION = 6`; `EXPECTED_PROTOCOL = 6`; `_native.pyi`;
      `lib.rs` exports; `uv sync --reinstall-package vfs-py`.
- [ ] A4 `lexical.py`: `BlockSummary` fields to packed `bytes` with
      `block_count` (and element accessors only if a consumer needs
      them); `decode_summary` / `competing_blocks` dispatch;
      `score_blocks` takes `Sequence[int] | None` and packs with
      `array('q')`.
- [ ] A5 Gate: `cargo test -p vfs-core`; `scripts/ci.sh 3.13` at 100 %.

## Slice B — numpy out

- [ ] B1 `lexical.py`: delete numpy / `NDArray` imports and every `np.`.
- [ ] B2 `tests/support/lexical_fidelity.py` rewritten in stdlib.
- [ ] B3 `tests/models/test_lexical.py`, `tests/models/test_postings.py`,
      `tests/storage/database/test_indexing.py`, `tests/test_native.py`:
      stdlib in place of numpy.
- [ ] B4 `pyproject.toml`: remove `numpy>=2.4.2`; `uv lock`; `uv tree`
      shows numpy only under the `search` extra.
- [ ] B5 Import-hygiene test: `numpy` not in `sys.modules` after
      importing every `vfs.*` module (L4).
- [ ] B6 ADR 035 status-line note (numpy coupling released).
- [ ] B7 Gate: `scripts/ci.sh` full matrix; `db_test` four legs at
      τ = 1.0.

## Slice C — measurement and landing

- [ ] C1 Re-run `bench_lexical_sites.py` and `bench_e2e_lexical.py`
      from the 2026-08-27 study; record as `results/after-142.json`.
- [ ] C2 Fill the criteria table; landing note; `STATUS.md`; move to
      `archive/`.
