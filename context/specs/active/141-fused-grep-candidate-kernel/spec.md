# 141 — the fused grep candidate kernel: `candidate_ids` in the crate, numpy leaves `postings.py` and `grep.py`

- **Status:** ready — drafted 2026-08-27 from ADR 057 decision 3 and
  the 2026-08-27 memo's recommendation (land this kernel first).
  Second of the ADR 057 arc; depends on spec 140.
- **Born from:** ADR 057
  (`../../../decisions/057-one-engine-the-rust-extension-is-required.md`);
  `../../../research/2026-08-27-rust-kernels-replace-numpy.md` §3, §4,
  §8, §10, §12 (the measured shape and the seam study);
  `../../../research/2026-08-12-posting-path-rust-kernel.md` ("fusion
  is the kernel; a thin decode function is not worth building").
- **Date:** 2026-08-27
- **Owner:** Clay Gendron
- **Kind:** a Rust kernel replacing the only live numpy path. `grep`'s
  output does not change: the same candidate set, the same order, the
  same truncation signal, the same corruption refusals. The referee
  is the existing grep suites plus a kernel parity test against the
  oracle codec.
- **Depends on:** spec 140 (one engine; the oracle codec in
  `tests/support/oracles/postings.py`).
- **Relates to:** spec 132 (its scope intersect is this kernel's
  allow-list path), spec 142 (numpy's exit from `pyproject.toml`),
  ADR 033 (the gate/ladder/truncation discipline — unchanged), ADR
  039 decision 7 (`CANDIDATE_BUDGET = 25_000` — unchanged).

---

## Intent

One call into the crate does everything the posting stage does
today: decode each chosen blob, AND within each group rarest-first,
OR across groups, intersect with the scoped allow-list, cap at
`CANDIDATE_BUDGET`, and hand back at most `cap` sorted doc ids as a
Python list plus the uncapped count. Doc ids never leave Rust until
they are capped. `postings.py` and `grep.py` stop importing numpy.

Why fused and not a decoder: the memo measured a decode kernel that
returns a Python list at 0.75 ms against numpy's 0.47 — slower — while
the fused ladder runs 0.20–0.35 ms against numpy's 4.5–12.8. Boxing
before the cap is the whole cost; boxing after it is free (the
`IN`-list chunker already boxes ≤ 25,000 ids today).

## Shape

- **§1 The kernel.** In `crates/vfs-core/src/postings.rs` (beside the
  encoder it must invert):

  ```rust
  pub fn candidate_ids(
      groups: &[Vec<&[u8]>],      // per AND-group, rarest-first blobs
      allow: Option<&[i64]>,      // sorted scoped ids, or None
      cap: usize,
  ) -> Result<(Vec<i64>, usize), PostingError>
  ```

  Decode is streaming LEB128 delta with the same refusals the pure
  codec has (`PostingCorruptionError` cases: empty blob, truncated
  varint, over-long varint, non-canonical zero-padded byte,
  non-positive first id, non-positive delta, id above `MAX_DOC_ID`).
  AND is a sorted-merge intersection starting from the smallest blob;
  an empty group short-circuits to empty. OR is a k-way sorted merge
  with dedup. The allow intersect is a sorted merge. The cap slices
  the sorted survivors; the second return value is the pre-cap count
  so the caller keeps raising the candidate-budget truncation. Runs
  off the GIL (`allow_threads`) — the inputs are borrowed bytes.

- **§2 The binding.** `python.rs`:
  `candidate_ids(groups: list[list[bytes]], allow: list[int] | None,
  cap: int) -> tuple[list[int], int]`. Blobs arrive as
  `Vec<Vec<PyBackedBytes>>` (zero-copy from `bytes`; the binding also
  accepts `bytearray` / `memoryview` by copying — the buffer protocol,
  not `bytes` alone). Corruption maps to `ValueError` with the pure
  codec's message text; the call site re-raises
  `PostingCorruptionError` from it. `PROTOCOL_VERSION` → 5; the stub
  gains the signature.

- **§3 The call sites.** `grep.py`: `_index_doc_ids` and the allow-list
  / cap block in `grep_rows` collapse into one `candidate_ids` call;
  `DocIds` becomes `list[int]`; `.size`, the slice, `.tolist()`, and
  every `np.` disappear. The planner's rarest-first ordering and the
  byte budget are unchanged — the kernel receives what the planner
  already chose. `postings.py`: `decode_varints` and `decode_postings`
  leave `src/` (their remaining product caller was `grep.py`; the
  lexical builder's `decode_varints` uses at `lexical.py:539-541` are
  in the pure builder, which spec 140 moved). They live on as the
  oracle codec in `tests/support/oracles/postings.py`, rewritten in
  stdlib (`int.from_bytes`-free byte loop). `numpy` is no longer
  imported in `postings.py` or `grep.py`.

- **§4 Parity and refusals.** `tests/test_native.py` gains
  `TestCandidateKernel`: for generated groups (random sorted id sets,
  including empties, singletons, `MAX_DOC_ID`, and overlaps chosen so
  AND/OR/allow each matter) the kernel's `(ids, count)` equals the
  oracle's decode → AND → OR → allow → cap in plain sets and sorted
  lists; every corruption case in `tests/models/test_postings.py`
  raises `PostingCorruptionError` through `grep`'s call site with the
  same message. A per-engine-leg test pins that the blob type reaching
  the kernel is `bytes` on sqlite, Postgres, MySQL, SQL Server, Oracle
  (the memo's cross-driver risk).

- **§5 Landing measurement.** The study's `bench_grep_sites.py` and
  `bench_e2e_grep.py` re-run against the live kernel on the spec 130
  landing store; criteria in the table below.

## Mutation ledger

- **K1** AND uses the largest blob first — killed by the parity test
  (result equal either way) **and** a timing pin at the `return`
  shape (≤ 0.6 ms; largest-first is measurably slower).
- **K2** cap applied before the allow intersect — killed by a parity
  case where the allow-list removes ids below the cap boundary.
- **K3** count returned post-cap — killed by asserting `count >
  len(ids)` on an over-budget case.
- **K4** a corruption case decodes silently — killed by the refusal
  suite routed through `grep`.
- **K5** OR keeps duplicates — killed by a two-group case sharing ids.
- **K6** empty group returns the other groups' union instead of
  empty — killed by a parity case with one empty AND-group.

## Slices

- **A** — §1 + §4's kernel parity: the Rust function, its unit tests
  in `cargo test`, the binding behind protocol 5, the Python parity
  test against the oracle. `grep.py` untouched; green on both.
- **B** — §3: the call sites convert; numpy leaves the two modules;
  the refusal suite re-routed; the per-leg blob-type pin.
- **C** — §5: the measurement, the landing note.

Gates: `cargo test -p vfs-core`; `scripts/ci.sh 3.13` at 100 %; all
four engine legs (the blob-type pin); the criteria table.

## Landing criteria (this machine, the spec 130 landing store)

| criterion | measured in the memo | target |
|---|---|---|
| ladder, `return` (199 K postings → 46 K survivors) | 0.35 ms (numpy 12.8) | ≤ 0.6 ms |
| ladder, `kmalloc` (111 K → 4 K) | 0.20 ms (numpy 4.5) | ≤ 0.3 ms |
| allow-list intersect, 46 K × 10 K | 0.20 ms (numpy 1.7) | ≤ 0.25 ms |
| scoped grep end-to-end, `kmalloc` under `/drivers/net/**` | 31 ms (numpy 36) | ≤ 33 ms |
| unscoped grep end-to-end, `kmalloc` | 152 ms (numpy 157) | ≤ 157 ms |
| `import numpy` in `postings.py`, `grep.py` | present | absent |
| corruption refusals through `grep` | 7 cases | 7 cases, same messages |
