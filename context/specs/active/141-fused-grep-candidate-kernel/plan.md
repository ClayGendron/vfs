# 141 — plan

## Approach

Kernel first, behind a protocol bump, with the Python parity test
proving it against the oracle before any product line changes. Then
the two call sites convert in one commit, so `grep.py` never holds
both shapes.

## §1 Kernel design (`crates/vfs-core/src/postings.rs`)

- **Decode as an iterator, not a `Vec`.** `struct Postings<'a> { bytes:
  &'a [u8], last: i64 }` implementing `Iterator<Item = Result<i64,
  PostingError>>`: read one LEB128 varint, add to `last`, yield. The
  first value is absolute (the encoder writes the first id raw, then
  deltas — mirror `encode_postings`' law exactly; verify against the
  pure codec's docstring and `_append_varint`). Refusals become
  `PostingError` variants with the same message text the pure codec
  raises (`tests/models/test_postings.py` is the catalog: empty blob,
  truncated varint, > 10-byte varint, canonical-form zero byte,
  non-positive first id, non-positive delta, above `MAX_DOC_ID`).
- **AND = sorted merge of the rarest blob against the rest.** Decode
  the smallest blob into `Vec<i64>` (its ids are the upper bound on
  survivors). For each remaining blob in the group, walk its iterator
  and the survivors together, keeping matches — `O(n + m)` per blob,
  survivors shrink monotonically. An empty survivor set ends the group
  early. The planner already orders blobs rarest-first; the kernel
  trusts the order but is correct under any order (K1 pins that it is
  *fast* under the right one).
- **OR = k-way merge of the groups' survivor vectors** with dedup
  (a `BinaryHeap` of `(id, group)` or, since group counts are small
  (k ≤ 4 per ADR 033), a simple repeated two-way merge).
- **Allow = one more sorted merge**; `allow` arrives sorted and
  unique (`grep_rows`'s `allow_list_ids` is built that way — the
  binding asserts monotone or sorts defensively; decide at
  implementation, sort is 10 K ints ≈ 0.1 ms).
- **Cap** = `truncate(cap)` on the final `Vec`; return `(vec, total)`.
- All of it inside `py.allow_threads` in the binding.

## §2 Binding (`python.rs`)

```rust
#[pyfunction]
#[pyo3(signature = (groups, allow, cap))]
fn candidate_ids(
    py: Python<'_>,
    groups: Vec<Vec<PyBackedBytes>>,
    allow: Option<Vec<i64>>,
    cap: usize,
) -> PyResult<(Vec<i64>, usize)>
```

`PyBackedBytes` borrows `bytes` zero-copy and copies `bytearray`;
`memoryview` needs `PyBuffer` — accept it by converting at the
Python call site if any driver ever returns one (the per-leg pin
says today none do). `PostingError` → `PyValueError` with the
message. `PROTOCOL_VERSION = 5`; `EXPECTED_PROTOCOL = 5` in
`native.py`; `_native.pyi` gains the signature.

## §3 Call sites

`grep.py` today (lines ~259–276, ~428–472):

```python
laddered = _index_doc_ids(plan, blobs)          # numpy ladder
doc_ids = np.intersect1d(laddered, allow, ...)  # allow
if doc_ids.size > CANDIDATE_BUDGET: doc_ids = doc_ids[:CANDIDATE_BUDGET]
```

after:

```python
groups = [[blobs[g] for g in group] for group in plan.groups]   # rarest-first per group, as today
try:
    doc_ids, total = extension().candidate_ids(groups, allow_list_ids, CANDIDATE_BUDGET)
except ValueError as error:
    raise PostingCorruptionError(str(error)) from error
truncated = total > CANDIDATE_BUDGET
```

`DocIds = Annotated[list[int], "sorted entries-table surrogate ids"]`.
The downstream `IN`-list chunker takes the list directly (no
`.tolist()`). `_index_doc_ids` is deleted. Confirm in slice B whether
the "no gram blobs chosen" (scan-only) path bypasses the kernel or
passes `groups=[]` — the kernel returns empty for no groups; the
caller's existing branch decides, keep whichever is already
structured.

`postings.py`: delete `decode_varints`, `decode_postings`, the numpy
import, the `NDArray` typing import; keep `encode_postings`,
`MAX_DOC_ID`, `PostingCorruptionError`, `PostingsBuilder` Protocol,
`postings_builder()`. Module docstring rewritten: the codec's decode
side lives in the crate; this module owns the encoder, the refusal
type, and the builder contract.

`tests/support/oracles/postings.py`: a stdlib `decode_postings(blob)
-> list[int]` and `decode_varints(blob) -> list[int]` (byte loop,
same refusals) — the referee for §4 and the replacement for every
test that called the numpy versions (`test_postings.py`,
`test_lexical.py`, `test_indexing.py`, `storage/database/test_lexical.py`
drop `.tolist()` / `np.array_equal`).

## §4 Parity test design

`TestCandidateKernel` in `tests/test_native.py`:

- Generator: `random.Random(seed)`; universe `1..50_000`; per case 1–4
  groups of 1–4 blobs, each blob a sorted sample of 0–3,000 ids, with
  planted overlaps (a shared core set per group so AND is non-empty
  ~half the time), an `allow` of `None` or a sorted sample, `cap` in
  `{1, 10, 25_000}`. Oracle: sets → `sorted(union of intersections) ∩ allow`,
  `count = len`, `ids = [:cap]`. 200 cases; plus the hand cases for
  K2, K3, K5, K6 and `MAX_DOC_ID`.
- Refusals: each blob from `test_postings.py`'s catalog, wrapped as
  one group, through `grep`'s call site (a storage fixture with a
  planted corrupt posting row) — asserts `PostingCorruptionError`
  and the message.
- Timing pin (K1): the `return`-shaped case from the study
  (`studies/2026-08-27-rust-kernels-replace-numpy/results/grep_sites.json`
  has the shape; regenerate synthetic blobs at 199 K postings) at
  ≤ 0.6 ms median of 5 — marked `slow`, run in the coverage leg only.

## Trade-offs

- **`count` as a second return** instead of a `truncated` bool: the
  count is free and lets the caller decide the signal; keep the
  caller's `total > CANDIDATE_BUDGET` law where it is.
- **Returning `list[int]` not `bytes`**: the seam study measured
  boxing 25 K ids at 0.26 ms, equal to today's `.tolist()`; bytes
  would save nothing and cost a decode at the `IN`-list chunker.
- **Not exposing a standalone decoder**: the 2026-08-12 and 08-27
  memos both measured it as slower than numpy when it returns a list.
  Tests use the oracle; the product never needs a bare decode.

## Verification

1. `cargo test -p vfs-core` (kernel unit tests: each refusal, AND/OR/
   allow/cap laws on small vectors).
2. `uv sync --reinstall-package vfs-py`; `uv run pytest tests/test_native.py -q`.
3. Slice B: `scripts/ci.sh 3.13` at 100 %; the four engine legs
   (`db_test` skill) for the blob-type pin.
4. Slice C: `uv run python context/research/studies/2026-08-27-rust-kernels-replace-numpy/bench_e2e_grep.py`
   against the landing store; fill the criteria table.
