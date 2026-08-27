# 142 — plan

## Approach

Two tiny kernels, each with a stdlib oracle written first (they are
the spec's truth, and they double as the readable statement of the
round-two rule). Then the dependency comes out and the full matrix
proves nothing else needed it.

## §1 `decode_summary` kernel

`crates/vfs-core/src/lexical.rs` already has the summary *encoder*
(the builder's `next_df_batch` writes the blob) and private varint
decoders. Add:

```rust
pub fn decode_summary(blob: &[u8]) -> Result<(Vec<i64>, Vec<f64>), LexicalError>
```

mirroring `encode_summary`'s law exactly (read `lexical.py:192-223`
for the layout: a count, then first ids as deltas, then weights — the
plan author confirms the byte layout from the encoder before writing
the decoder; the two must round-trip). The binding packs the two
vectors with `bytemuck`-free manual `to_le_bytes` loops into
`PyBytes` (no extra crate). Refusals: truncated, non-monotone firsts,
count mismatch → `LexicalError` → `ValueError`.

Python side: `BlockSummary(first_ids: bytes, max_weights: bytes)`
with `block_count`. Every consumer of `.first_ids[i]` /
`.max_weights[i]` today is `competing_blocks` (moving to Rust) and
the tests — check with `grep -n "first_ids\|max_weights" src/ tests/`
at implementation; if a Python consumer needs an element, give
`BlockSummary` `first_id(i)` / `max_weight(i)` via `struct.unpack_from`
rather than unpacking the whole thing.

## §2 `competing_blocks` kernel

Rule (from `lexical.py:412-434`): for each candidate with score `s`,
find the block whose `first_id ≤ candidate` (`searchsorted(...,
side="right") - 1`); if inside a block (index ≥ 0), `best[block] =
max(best[block], s)`. Return every block index where `max_weight ≥
theta` or `best + max_weight ≥ theta`.

Rust: binary search per candidate over `first_ids` (`partition_point`),
`best: Vec<f64>` initialized to `-inf`, one pass, then a filter. Input
shapes: `first_ids: &[u8]`, `max_weights: &[u8]` (packed, straight
from §1's output — zero conversion between rounds), `candidates:
&[u8]` (packed `i64`), `scores: &[u8]` (packed `f64`), `theta: f64`.
Output `Vec<usize>` → `list[int]`.

**The handoff shape.** Today `score_blocks` returns `list[tuple[int,
float]]` (Rust) and the caller builds numpy arrays for round two.
Options: (a) keep the tuple list and pack with `array('q', ids)
.tobytes()` / `array('d', scores).tobytes()` at the call site
(~0.05 ms at 5 K); (b) have `lexical_score` return packed bytes too.
Take (a): it keeps `lexical_score`'s signature stable (protocol
churn for nothing) and the pack is free at these sizes. Revisit only
if spec 132's measurement says otherwise.

`score_blocks`'s `candidates: NDArray | None` parameter becomes
`Sequence[int] | None`; the seam conversion is `array('q',
candidates).tobytes()`.

## §3 numpy out

- `lexical.py`: delete `import numpy`, `NDArray`, every `np.`;
  `BlockSummary` fields to `bytes`; `competing_blocks` and
  `decode_summary` dispatch to the extension.
- `tests/support/lexical_fidelity.py`: rewrite in stdlib (it is the
  referee for τ = 1.0 — it must stay obviously correct; a dict-based
  BM25 over decoded lists).
- `tests/models/test_lexical.py`, `tests/models/test_postings.py`,
  `tests/storage/database/test_indexing.py`, `tests/test_native.py`:
  replace `.tolist()` / `np.array_equal` / `np.frombuffer` with
  stdlib (`struct.unpack`, lists).
- `pyproject.toml`: remove `"numpy>=2.4.2"`; `uv lock`; confirm
  `uv tree` shows numpy only under the `search` extra (`usearch`).
- `tests/test_dependencies.py` (new, or wherever import hygiene lives):
  after `import vfs` plus every `vfs.*` module via `pkgutil.walk_packages`,
  assert `"numpy" not in sys.modules` (L4).
- ADR 035: append to the status line — "numpy coupling released by
  spec 142 (ADR 057), 2026-08-XX".

## Trade-offs

- **Packed bytes inside `BlockSummary`** makes the type opaque to a
  casual reader. The alternative (lists of Python ints/floats) boxes
  ~6 K objects per term per query — the memo measured the summary
  decode at 0.36 ms as a Python loop vs 0.005 ms packed; small, but
  the point of §1 is that round two never unpacks. Document the field
  law in the NamedTuple docstring.
- **Protocol bump to 6** for two additive functions: additive changes
  could keep the number, but the seam's law is exact-match and a stale
  build with protocol 5 would otherwise fail at first call instead of
  at import. Bump.

## Verification

1. Oracles first: `tests/support/oracles/lexical.py` gains
   `decode_summary` and `competing_blocks` in stdlib; the parity tests
   are written against them before the Rust exists (red), then the
   kernels land (green).
2. `cargo test -p vfs-core`; `uv sync --reinstall-package vfs-py`.
3. `scripts/ci.sh` full matrix after the dependency removal (every leg
   resolves a lockfile without numpy).
4. `db_test` four legs: τ = 1.0 unchanged.
5. `bench_lexical_sites.py` / `bench_e2e_lexical.py` from the study on
   the landing store; fill the table.
