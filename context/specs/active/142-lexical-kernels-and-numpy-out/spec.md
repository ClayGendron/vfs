# 142 — the lexical kernels: summary decode and block selection in the crate, the numpy scorer deleted, numpy leaves `pyproject.toml`

- **Status:** ready — drafted 2026-08-27 from ADR 057 decision 3 and
  the 2026-08-27 memo §5–§7, §9, §12. Third of the ADR 057 arc;
  depends on specs 140 and 141. The memo suggests these kernels ride
  spec 132's query path, where they get their first caller; this spec
  is written standalone so it can land before, with, or after 132 —
  whichever comes first. If 132 lands first it takes §1–§2 as its own
  slice and this spec shrinks to §3–§4.
- **Born from:** ADR 057
  (`../../../decisions/057-one-engine-the-rust-extension-is-required.md`);
  `../../../research/2026-08-27-rust-kernels-replace-numpy.md`; ADR
  055 §4 (superseded on the fallback clause); ADR 035 (its numpy
  coupling of the Python floor, released here).
- **Date:** 2026-08-27
- **Owner:** Clay Gendron
- **Kind:** two small Rust kernels (~80 lines), one deletion, one
  dependency removed. The lexical search's output does not change;
  its compute is already the Rust scorer. The referee is the lexical
  parity suite and the fidelity referee (`lexical_fidelity.py`,
  τ = 1.0), both rewritten without numpy.
- **Depends on:** spec 140 (oracles; the stdlib `pure_score_blocks`
  oracle already replaced the numpy one), spec 141 (numpy already out
  of `postings.py` and `grep.py` — after this spec no `src/` module
  imports it).
- **Relates to:** spec 132 (the query path these serve), specs 135
  and 136 (their kernel candidates are *not* this spec — named in
  §4), spec 137 (its fallback clause is void, nothing to build).

---

## Intent

The last numpy in `src/` — `decode_summary`, `competing_blocks`, and
the `candidates` conversion in `score_blocks` — moves into the crate
or becomes plain Python, and `numpy` leaves `dependencies` in
`pyproject.toml`. After this spec `grep -rn numpy src/` is empty,
`uv.lock` has no numpy in the core resolution, and the `search`
extra's transitive numpy (via `usearch`) is the only place it can
appear — an extra, not core.

## Shape

- **§1 Summary decode.** `decode_summary(blob) -> BlockSummary` calls
  `extension().decode_summary(blob) -> tuple[bytes, bytes]`: the
  per-term summary's `first_ids` as packed little-endian `i64` and
  `max_weights` as packed `f64`, kept packed inside `BlockSummary`
  (its two fields become `bytes`; a `block_count` property reads
  `len(first_ids) // 8`). Refusals (truncated blob, non-monotone
  first ids) raise `ValueError` → the lexical module's existing
  corruption class. Measured 0.005 ms vs numpy's 0.45 on 1,553
  blocks; the shape exists so the arrays never materialize as Python
  objects between rounds.

- **§2 Block selection.** `competing_blocks(summary, candidates,
  scores, theta) -> list[int]` calls
  `extension().competing_blocks(first_ids: bytes, max_weights: bytes,
  candidates: bytes, scores: bytes, theta: float) -> list[int]` — the
  round-two rule unchanged: a block competes when its `max_weight ≥
  theta` or when the best round-one score of a candidate falling in
  the block plus the block's max could reach `theta`. Block numbers
  come back as a Python list (≤ a few thousand ints, ~0.05 ms).
  `candidates` and `scores` are the packed `bytes` the scorer already
  produces / consumes; `score_blocks`'s `np.ascontiguousarray(...)
  .tobytes()` becomes `struct.pack` / `array('q').tobytes()` over a
  `list[int]` — or, better, the scorer returns candidates packed and
  they are never unpacked (the plan decides on the round-one/round-two
  handoff shape).

- **§3 The deletion and the dependency.** `pure_score_blocks` (numpy)
  is already gone (spec 140 replaced it with a stdlib oracle). Delete
  the `numpy` / `NDArray` imports from `lexical.py`; delete
  `numpy>=2.4.2` from `pyproject.toml`; `uv lock`; rewrite
  `tests/support/lexical_fidelity.py` and any remaining `np.` in
  `tests/` (`test_lexical.py`, `test_indexing.py`, `test_native.py`)
  in stdlib. ADR 035's status line gets a note: the numpy 2.4.x hold
  no longer constrains the 3.11 floor.

- **§4 What this spec does not build, on the record.** Spec 135's
  client-floor cosine over `membership_budget` batches (MySQL /
  `GENERIC`) and spec 136's PageRank / Katz power iteration are
  measured-scale kernel candidates per the memo §11; each is that
  spec's own slice, shaped `bytes in, list out`, with its own
  measurement. Spec 135's fusion over ≤ 2 K floats is plain Python.
  Spec 137 needs no kernel. None of them may reintroduce numpy.

## Mutation ledger

- **L1** `decode_summary` accepts a truncated blob — killed by the
  refusal test.
- **L2** `competing_blocks` drops the "best + max ≥ theta" clause —
  killed by a parity case where a block competes only through it.
- **L3** `competing_blocks` uses `side="left"` semantics at a block
  boundary (candidate == first_id of the next block) — killed by a
  boundary case.
- **L4** numpy re-enters `src/` — killed by an import-graph test
  asserting `numpy` is not in `sys.modules` after `import vfs` and
  its submodules.
- **L5** the fidelity referee silently computes with a different
  BM25 than the engine — unchanged referee, τ = 1.0 on all five
  engines (the existing `db_test` legs).

## Slices

- **A** — §1 + §2: the two kernels behind protocol 6, parity tests
  against stdlib oracles in `tests/support/oracles/lexical.py`,
  call sites converted.
- **B** — §3: numpy out of `lexical.py`, `tests/`, `pyproject.toml`,
  `uv.lock`; ledger L4; ADR 035 note.
- **C** — the measurement (`bench_lexical_sites.py`,
  `bench_e2e_lexical.py` from the study), the landing note.

Gates: `cargo test -p vfs-core`; `scripts/ci.sh` full matrix (the
dependency change touches every leg); the four engine legs for τ = 1.0.

## Landing criteria (this machine, the spec 130 landing store)

| criterion | measured in the memo | target |
|---|---|---|
| summary decode, 5,983 blocks | 0.016 ms (numpy 1.3–1.6) | ≤ 0.03 ms |
| block selection, 6 terms × 5 K candidates | 0.15 ms (numpy 0.8) | ≤ 0.2 ms |
| two-round lexical search, 3-term k=10, end-to-end | 3.4 ms (numpy path 9.2) | ≤ 3.6 ms |
| two-round lexical search, 6-term K=1000 | 9.8 ms (numpy 38.1) | ≤ 10.5 ms |
| scorer, 3 terms / 1,553 blocks | 4.4 ms | unchanged |
| `grep -rn numpy src/` | 3 modules | empty |
| `numpy` in `pyproject.toml` `dependencies` | present | absent |
| fidelity τ on five engines | 1.0 | 1.0 |
