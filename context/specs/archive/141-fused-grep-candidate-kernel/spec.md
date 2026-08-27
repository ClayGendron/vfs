# 141 — the fused grep candidate kernel: `candidate_ids` in the crate, numpy leaves `postings.py` and `grep.py`

- **Status: landed 2026-08-27.** Slices A–C in one landing:
  `candidate_ids` in the crate behind protocol 5, `grep.py` and
  `postings.py` free of numpy, the refusal catalog routed through
  `grep`, the blob-type pin green on all four engines, the after-
  measurement in `results/after-141.json`. Second of the ADR 057 arc
  (140 → 141 → 142). Details in the landing note below.
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

## Landing note (2026-08-27)

- **What landed.** `crates/vfs-core/src/postings.rs` gains the read
  side: a streaming `Varints` reader and `Postings` iterator carrying
  the codec's seven refusals as `PostingError` (messages identical to
  the deleted pure decoder's), `decode_postings`, and
  `candidate_ids(groups, allow, cap) -> (survivors, total)` — the
  rarest blob decoded once, every later blob stream-merged against
  the shrinking survivors, groups unioned (the sort skipped when only
  one group survives), the allow-list met by a sorted merge, the cap
  applied last. Every blob is validated even after the intersection
  empties. The binding takes `Vec<Vec<PyBackedBytes>>` (zero-copy from
  `bytes`), runs detached from the GIL, and maps `PostingError` to
  `ValueError`; `PROTOCOL_VERSION` → 5. `grep.py`'s `_index_doc_ids`
  fetches the planner's chosen blobs and makes the one call;
  `DocIds` is `list[int]`; `.size`, the slice, `.tolist()` and
  `np.` are gone; the caller reads the pre-cap count for the
  candidate-budget truncation. `postings.py` keeps the encoder, the
  refusal type and the builder contract; `decode_varints` /
  `decode_postings` left `src/` (the oracle codec in
  `tests/support/oracles/postings.py` serves every test that decodes).
- **Tests.** `TestCandidateKernel`: 200 generated ladders against a
  set oracle, the hand cases (K2 cap-after-allow, K3 pre-cap count,
  K5 dedup, K6 empty group, `MAX_DOC_ID`), refusal after an emptied
  intersection, and a `slow` timing pin on the `return` shape (< 5 ms
  median, generous against CI noise). `test_postings.py` decodes
  through a single-blob kernel call and pins all seven refusals as
  `ValueError` with the codec's messages; `test_grep.py` routes the
  same seven blobs through `storage.grep` and pins
  `PostingCorruptionError`'s message in the `internal` error.
  `StorageContract.test_grep_posting_blobs_reach_the_engine_as_bytes`
  spies on `_native.candidate_ids` and pins `bytes` on every engine.
- **Legs.** `scripts/ci.sh 3.13`: 2,794 passed, 100 % coverage.
  Postgres 214, MySQL 214, SQL Server 214, Oracle 211 passed — each one
  more than the spec 139 landing, the new pin. `cargo test -p vfs-core`
  38 passed.
- **Measurement** (`results/after-141.json`, this machine, the spec 130
  landing store, medians; the memo's like-for-like comparator is its
  `ladder_rust_tolist_ms` row — the throwaway packed bytes, and boxing
  to a list is the seam ADR 057 chose):

  | criterion | numpy (memo) | throwaway + tolist (memo) | shipped |
  |---|---:|---:|---:|
  | ladder, `return` (199 K postings → 46 K), capped at 25 K | 12.8 ms | 0.85 ms | **0.69 ms** |
  | ladder, `kmalloc` (111 K → 4 K) | 4.5 ms | 0.24 ms | **0.36 ms** |
  | ladder + 10 K allow-list, `return` | 12.8 + 1.7 ms | — | **0.72 ms** |
  | scoped grep e2e, `kmalloc` under `/drivers/net/**` | 36 ms | 31 ms | **30–32 ms** |
  | unscoped grep e2e, `kmalloc` | 157 ms | 152 ms | **157 ms** |
  | `import numpy` in `postings.py`, `grep.py` | present | — | absent |
  | corruption refusals through `grep` | 1 case | — | 7 cases, same messages |

  The spec's ≤ 0.6 ms / ≤ 0.3 ms targets were written against the
  throwaway's packed-bytes rows (0.35 / 0.20 ms) — the wrong
  comparator once the seam boxes to a list; against the boxing rows
  the shipped kernel is at or under on `return` and ~0.1 ms over on
  `kmalloc` (4 K ids boxed plus the group's extra validation). The
  end-to-end rows match the memo's Rust arm within noise, and the
  index stage is now ≤ 1 ms on every shape this store produces.
- **Residue.** `rustfmt --check` is not a gate in this repo
  (pre-existing diffs in `chunk.rs`); `cargo clippy --all-features`
  needs a Python for pyo3-ffi and is not run by CI. The union's k-way
  merge is a sort+dedup — fine at ≤ 4 groups; a heap merge is the
  next lever if wide alternations ever show in a profile.
