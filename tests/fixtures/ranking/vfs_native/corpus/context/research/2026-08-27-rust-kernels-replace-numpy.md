# Rust kernels replace numpy: every remaining site measured on the full linux store

- **Status**: research memo (commits us to nothing). Feeds the spec that
  implements ADR 057 (*one engine: the Rust extension is required, pure
  Python is a test oracle, numpy leaves the core*) — its numbers size
  that spec's landing criteria. The brief was written for a pending ADR;
  ADR 057 was accepted while the benchmarks ran, so the headline here is
  the Rust-vs-numpy arm per site. The stdlib arm was measured anyway and
  is kept: it is the evidence for why the oracle is not a product.
- **Date**: 2026-08-27
- **Owner**: Clay Gendron
- **Question**: numpy has five remaining sites in `src/`. If each moves
  to a kernel in our own Rust crate, what does that cost or buy in
  latency and memory at production scale — and what would a stdlib-only
  pure-Python spelling of each have cost, had the fallback survived?
- **Evidence gathered**: executed benchmarks on the spec 130 landing
  store — the **full linux checkout** written through `DatabaseStorage`
  and reindexed by the live tree on 2026-08-26 (`landing_full.sqlite`,
  7.3 GB, schema format 8): 77,866 files / 83,625 entries, 674,445
  chunks, gram index 245,399 grams / 128 MB of posting blobs (widest
  gram 76,258 entries), lexical index 4.82 M terms / 5.18 M blocks /
  65.2 M postings. Three arms per site — **numpy** (the live code),
  **stdlib** (plain loops, `bisect`, `array`, `struct`; no numpy),
  **Rust** (a throwaway pyo3 crate, `vfs_kernels_rs`, built by maturin
  in 11 s; site 5 uses the shipped `vfs._native.lexical_score`) — every
  arm asserted identical (including corruption refusals) before timing;
  median of 7 runs, wall-clock; `tracemalloc` peak for numpy vs stdlib.
  Plus two end-to-end runs through the public/planned paths under each
  arm: `DatabaseStorage.grep` (8 query shapes, median of 3) and the
  ADR 055 two-round lexical search (31 queries × 2 k, median of 5).
  Apple M1 Pro, 32 GB, macOS (darwin 25.5.0), Python 3.13.11, numpy
  2.4.2, rustc 1.97.1, maturin 1.15.0, pyo3 0.29 (abi3-py311).
  Scripts, crate source, raw JSON and run commands are in
  `studies/2026-08-27-rust-kernels-replace-numpy/`.
- **Sources**: `2026-08-12-posting-path-rust-kernel.md` (decode +
  intersect on the 990 K-chunk spike corpus; this memo extends it to
  the lexical sites and to end-to-end shares, and does not repeat it);
  `2026-08-16-grep-read-path-profile.md` (the "index ≤ 25 ms, verify
  82–99.7 %" claim, re-measured below on the current tree);
  `2026-08-26-bm25-storage-design.md` and spec 130's landing table (the
  query shapes and the Rust-vs-numpy scorer numbers this memo
  confirms); ADR 039, ADR 055 decision 4, ADR 057.

---

## 0. One-paragraph version

Rust beats numpy at every site, by 5× (decode) to 25–35× (the grep
ladder) to 15–20× (the BM25 scorer), and the kernels are small (the
whole throwaway crate is ~330 lines). Where it shows depends on the
path. On grep, the numpy sites are already cheap: the ladder is 1–14 ms
inside a 40 ms – 2.4 s call (2–4 % unscoped, 16 % on a scoped grep,
which Rust takes to 3 %). On the lexical query, compute is 85–95 % of
the two-round search and Rust makes the whole query 2.7–3.9× faster —
but almost all of that is the scorer, which the live tree already
dispatches to Rust; the two numpy sites left there (summary decode,
block selection) are under 1 ms. So the move is worth doing because it
deletes a dependency and a tier, and because it removes the last
numpy from the live grep path; users feel it on scoped greps, and
would feel the scorer if it were not already Rust. The one fact that
binds the spec: the grep kernel must be *fused* — blobs in, a bounded
id list out — because a decode-only kernel returning ids to Python
gives back 90 % of its win in boxing.

## 1. Where numpy lives today (verified)

`grep -rn numpy src/` finds three modules; nothing else imports it.

| # | site | file | what numpy does | any other implementation? |
|---|---|---|---|---|
| 1 | posting decode | `models/postings.py` `decode_varints` / `decode_postings` | vectorized LEB128 decode: 8 array passes (`flatnonzero`, `repeat`, shifts, `add.at`, `cumsum`) | none in Python. Rust decodes varints privately in `lexical.rs` (`decode_varints`, `decode_ids`) and `postings.rs`, exports nothing |
| 2 | grep ladder | `storage/backends/database/grep.py` `_index_doc_ids`, `grep_rows` | `np.intersect1d` rarest-first k=4 AND per group; `np.unique(np.concatenate)` OR; allow-list `intersect1d`; slice to `CANDIDATE_BUDGET` (25,000); `DocIds` is an `NDArray[int64]` alias | none |
| 3 | summary decode | `models/lexical.py` `decode_summary` | a **Python loop** already; numpy only in the final `np.array(...)` copies into `BlockSummary` | none |
| 4 | block selection | `models/lexical.py` `competing_blocks` | `searchsorted` + `maximum.at` + `flatnonzero` | none |
| 5 | BM25 scorer | `models/lexical.py` `pure_score_blocks` | `concatenate`, `repeat`, `isin`, `unique`, `bincount`, `lexsort` | **yes** — `vfs._native.lexical_score`, parity-pinned; `score_blocks` dispatches to it |

Sites 3–5 have **no caller in `src/` yet** outside `lexical.py` itself:
spec 132 (the lexical verb) is pending. Site 2 is on a live user path
(`grep`) today. So the grep sites are the only ones a user can feel now.

## 2. Method

The bench never invents inputs. For grep it reproduces the live
planner's choice exactly — `build_code_gram_query` → `_plan_groups` →
`_posting_meta` → `_choose_grams` (rarest-first, k = 4, under the 4 MB
byte budget) → `_posting_blobs` — through a real session on the store,
so every arm runs over the blobs `grep_rows` would decode. For lexical
it draws queries the way the spec 130 landing did (seed 7): 1-term =
one mid-df term (0.2–2 % of chunks), 3-term = two mid + one common
(> 20 %), 6-term = one rare + four mid + one common, 10 per arity,
plus the adversarial all-common `struct if` (58 % / 55 % of chunks;
5,983 blocks, 3 MB of blobs). Every term's blocks are fetched whole
once; the arms then run on the same bytes.

Arms:

- **numpy** — the live functions, called as the live code calls them.
- **stdlib** — `kernels_py.py`: plain byte loops with the full
  corruption-check set, a fused decode+intersect (rarest blob to a set,
  later blobs streamed), `bisect` for block selection, and two scorer
  spellings — *full* (decode everything, like the numpy path) and
  *skip* (the Rust engine's block-max skip, in Python). All sums
  accumulate in the engines' order, so results are bit-identical.
- **Rust** — `vfs_kernels_rs`: `decode_postings` (packed int64 bytes
  out; a `Vec<i64>`-returning twin as a control), `intersect_rarest`
  (fused: rarest blob decoded, later blobs streamed with a two-pointer
  merge — the 2026-08-12 shape), `union_sorted`, `intersect_sorted`,
  `decode_summary`, `competing_blocks`. Every input is bytes
  (`PyBackedBytes`, zero-copy from `bytes`); every output is packed
  native-endian int64/float64 `bytes`; the heavy work runs under
  `py.detach` like the shipped bindings. Site 5 is the shipped
  `_native.lexical_score`.

"Median" below is the median of 7 timed calls (3 for the grep
end-to-end, 5 for the lexical end-to-end) after a warm-up. Memory is
`tracemalloc` peak, which sees numpy's buffers and every Python object
but **not** a Rust kernel's internal `Vec`s — so Rust memory is
reported as its returned payload only, and the numpy-vs-stdlib
comparison is the one `tracemalloc` measures fairly.

## 3. Site 1 — posting decode (the largest chosen blob per pattern)

| blob | doc ids | numpy | stdlib (one pass) | **Rust → bytes** | Rust → `np.frombuffer` | Rust → `list` | Rust returns `Vec<i64>` |
|---|---:|---:|---:|---:|---:|---:|---:|
| `randomize_kstack_offset` rarest gram | 4,357 | 0.063 ms | 0.56 ms | **0.005 ms** | 0.005 ms | 0.050 ms | 0.050 ms |
| `pr_debug` | 18,082 | 0.184 | 2.25 | **0.026** | 0.028 | 0.220 | 0.226 |
| `kmalloc` | 48,611 | 0.474 | 6.23 | **0.065** | 0.086 | 0.697 | 0.747 |
| `return` | 52,411 | 0.545 | 6.54 | **0.100** | 0.106 | 0.652 | 0.656 |

- Rust decode is **5–9× faster than numpy** when the ids stay packed
  (bytes, or a numpy view over the bytes).
- Handing the ids to Python as a list costs ~12 ns per id (boxing) —
  **a decode kernel that returns a list is no faster than numpy.** This
  repeats the 2026-08-12 finding: fuse, do not export decode.
- stdlib decode is 10–13× slower than numpy. Peak memory for the 48 K
  blob: numpy 1.9 MB (its eight intermediate arrays), stdlib 2.1 MB
  (a list of boxed ints).

Site 1 has no reason to exist as its own kernel: nothing in `src/`
needs a decoded array except site 2 (which should fuse it) and site 5
(which already decodes in Rust). The `tfs`/`dls` decode inside
`pure_score_blocks` goes away with site 5.

## 4. Site 2 — the grep ladder (decode + rarest-first AND + OR-union)

`_index_doc_ids`' post-fetch algebra over the planner's exact blobs.
"Candidates" is the union the ladder returns; `return` is capped later
by `CANDIDATE_BUDGET`, not here.

| pattern | groups | postings decoded | blob bytes | candidates | numpy | stdlib (fused) | **Rust (fused)** | Rust ÷ numpy | numpy peak | stdlib peak |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `xyzzy_no_such_symbol_42` | 1 | 620 | 887 | 3 | 0.10 ms | 0.12 ms | **0.002 ms** | 50× | 27 KB | 4 KB |
| `randomize_kstack_offset` | 1 | 11,963 | 12.5 KB | 42 | 0.51 | 1.87 | **0.020** | 25× | 278 KB | 211 KB |
| `EXPORT_SYMBOL_NS_GPL` | 1 | 29,629 | 29.9 KB | 669 | 1.23 | 4.60 | **0.069** | 18× | 557 KB | 935 KB |
| `kmalloc` | 1 | 111,016 | 111 KB | 4,087 | 4.49 | 16.70 | **0.196** | 23× | 3.1 MB | 0.6 MB |
| `pr_debug` | 1 | 61,058 | 61 KB | 4,708 | 2.75 | 9.63 | **0.164** | 17× | 1.2 MB | 1.2 MB |
| `static\s+int\s+\w+_probe` | 2 | 125,433 | 125 KB | 13,964 | 6.63 | 19.71 | **0.274** | 24× | 3.2 MB | 2.3 MB |
| `->next` | 1 | 73,659 | 74 KB | 3,347 | 3.01 | 11.26 | **0.146** | 21× | 2.2 MB | 0.6 MB |
| `!= NULL` | 1 | 110,071 | 110 KB | 14,479 | 5.87 | 18.14 | **0.370** | 16× | 2.3 MB | 4.0 MB |
| `alloc_page` | 1 | 84,927 | 85 KB | 3,586 | 3.52 | 12.85 | **0.213** | 17× | 2.0 MB | 1.8 MB |
| `return` | 1 | 198,718 | 199 KB | 46,335 | 12.78 | 31.23 | **0.351** | 36× | 3.7 MB | 8.0 MB |
| `(mutex_lock\|spin_lock)` | 2 | 136,397 | 137 KB | 11,864 | 6.57 | 22.09 | **0.556** | 12× | 1.8 MB | 2.1 MB |

- **Rust is 12–36× faster than numpy**, and never above 0.6 ms on this
  store. The widest ladder (`return`, 199 K postings, 46 K survivors)
  takes 0.35 ms.
- The stdlib fused spelling is 2.4–3.7× slower than numpy — the same
  ratio the 2026-08-12 memo found on the chunk-level corpus. Its memory
  is *lower* than numpy's on mid-width queries (the fused loop never
  materializes later blobs) and higher on the widest (a set of 52 K
  boxed ints).
- The candidate counts are entry-level (77,866 files), so `return`
  yields 46 K candidates here where the 2026-08-12 chunk-level corpus
  gave 257 K. The ratios hold across both scales.

The allow-list intersect (scoped grep — `np.intersect1d(laddered,
allow)` in `grep_rows`) at a 10,000-entry scope:

| ladder result | survivors | numpy | stdlib (set) | **Rust (two-pointer, incl. packing the allow list)** |
|---|---:|---:|---:|---:|
| 42 (`randomize_kstack_offset`) | 7 | 0.38 ms | 0.17 ms | **0.12 ms** |
| 4,087 (`kmalloc`) | 534 | 0.50 | 0.30 | **0.13** |
| 14,479 (`!= NULL`) | 1,890 | 0.77 | 0.48 | **0.17** |
| 46,335 (`return`) | 5,918 | 1.72 | 1.06 | **0.20** |

Half the Rust time here is packing the 10 K Python ints of the allow
list into bytes (`array('q', allow)`, ~0.1 ms); the merge itself is
tens of microseconds. numpy pays the same packing inside `np.asarray`.

## 5. Site 3 — summary decode (`decode_summary`)

| summary | blocks | live (loop + `np.array`) | stdlib (loop, lists) | **Rust → bytes** | Rust → lists |
|---|---:|---:|---:|---:|---:|
| 1-term query (median) | 16 | 0.006 ms | 0.004 ms | **0.000 ms** | 0.001 ms |
| 3-term query (median, all terms) | 1,553 | 0.451 | 0.356 | **0.005** | 0.040 |
| 6-term query (median) | 1,534 | 0.444 | 0.351 | **0.006** | 0.042 |
| `struct if` (all-common) | 5,983 | 1.647 | 1.304 | **0.016** | 0.149 |
| `struct` alone (widest term) | 3,075 | 0.846 | 0.673 | **0.008** | — |

- The live version is already a Python loop; its `np.array` copies at
  the end make it 25 % *slower* than the stdlib spelling. Memory:
  265 KB vs 217 KB for `struct`.
- Rust is ~90× faster than the loop and ~0.3 µs per block, but the
  loop is 0.3–1.3 ms at any query this store can produce. Site 3 is
  **not a performance site**; it moves to Rust because ADR 057 says one
  engine, and because the round-two selection (site 4) wants the
  summary in the packed form the kernel emits.

## 6. Site 4 — block selection (`competing_blocks`)

The ADR 055 two-round protocol: heads (`block_no < 8`) scored, θ = the
k-th score, then `competing_blocks` per overflowing term (summed over
the query's overflowing terms, with `rest` = the later terms' maxima).

| query | overflowing terms | summary blocks | candidates | competing (k=10) | numpy | stdlib (`bisect`) | **Rust** |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1-term | 1 | 16 | 1,024 | 12 | 0.031 ms | 0.082 ms | **0.004 ms** |
| 3-term | 3 | 1,553 | 3,064 | 84 | 0.334 | 0.967 | **0.065** |
| 6-term | 5 | 1,533 | 5,060 | 150 | 0.799 | 2.401 | **0.150** |
| `struct if` | 2 | 5,983 | 1,840 | 2,916 | 0.270 | 0.774 | **0.077** |

At K = 1,000 (the fusion depth) the competing counts rise (239 / 589 /
5,983) but the times do not move: the cost is `candidates × terms`
`searchsorted` probes, not the output. Rust is 5× numpy, 15× stdlib;
all three are under 2.5 ms.

## 7. Site 5 — the BM25 scorer (numpy fallback vs shipped Rust)

Every block of every query term fetched; top-k over all of them.

| query | blocks | postings | k | numpy (`pure_score_blocks`) | stdlib full | stdlib skip | **Rust (`lexical_score`)** | Rust ÷ numpy |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1-term | 16 | 1,982 | 10 | 0.76 ms | 1.67 ms | 1.80 ms | **0.20 ms** | 4× |
| 3-term | 1,553 | 198,673 | 10 | 75.9 | 227.8 | 47.5 | **4.41** | 17× |
| 3-term | | | 1,000 | 75.6 | 226.7 | 68.8 | **6.28** | 12× |
| 6-term | 1,534 | 195,802 | 10 | 75.3 | 222.4 | 48.4 | **3.92** | 19× |
| 6-term | | | 1,000 | 77.4 | 223.2 | 95.9 | **9.42** | 8× |
| 3-term, 5,000-id allow-list | 1,553 | 198,673 | 10 | 59.0 | — | 37.6 | **2.07** | 28× |
| `struct if` | 5,983 | 765,671 | 10 | 288 | 801 | 958 | **71.6** | 4× |
| `struct if` | | | 1,000 | 287 | 817 | 922 | **72.2** | 4× |

Peak memory at k = 10: 3-term **numpy 19.3 MB vs stdlib-skip 3.2 MB**
(numpy materializes every decoded array for all 199 K postings; the
skip loop decodes a fraction); all-common numpy 74 MB vs stdlib-skip
120 MB (nothing skips, and a dict of 400 K boxed floats is heavier
than arrays).

Three things worth saying twice:

- The spec 130 landing numbers are **confirmed**: 4.1 ms Rust vs 79 ms
  numpy at 3 terms then; 4.4 vs 76 now on the same store.
- The stdlib *skip* spelling beats numpy at k = 10 (47 ms vs 76 ms):
  block-max skipping avoids most of the decode, which the numpy path
  cannot do. So the "slow fallback" would have been the second-fastest
  scorer — and still 11× slower than the Rust engine. This is the
  cleanest illustration of why a numpy tier buys nothing we own.
- `struct if` is the block-max limit ADR 055 states: nothing skips,
  Rust takes 72 ms for 766 K postings. Unchanged by anything here.

## 8. End-to-end: `DatabaseStorage.grep` under each arm

The public verb on the full store; only `_index_doc_ids`' algebra and
`grep_rows`' three numpy touches are swapped per arm (the fetch half,
entry resolution, content fetch and the Rust verify are the live tree).
Median of 3 after a warm-up; results identical across arms (same files,
same lines).

| query | files / lines | total numpy | total stdlib | total Rust | index stage numpy | index stdlib (algebra) | index Rust (algebra) | entries | content |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| zero-hit `xyzzy_…_42` | 0 / 0 | 41 ms | 40 ms | 40 ms | 0.9 ms | 0.8 (0.1) | 0.7 (0.01) | 0 | 28 |
| `randomize_kstack_offset` | 4 / 9 | 42 | 43 | 41 | 1.3 | 2.5 (1.9) | 0.7 (0.04) | 1 | 28 |
| `kmalloc` | 3,680 / 8,201 | 157 | 169 | 152 | 5.6 | 17.6 (16.8) | 1.1 (0.22) | 24 | 82 |
| `pr_debug` (word) | 2,252 / 13,168 | 170 | 176 | 167 | 3.9 | 10.5 (9.7) | 1.0 (0.20) | 28 | 91 |
| `static\s+int\s+\w+_probe` | 9,308 / 10,974 | 356 | 370 | 365 | 7.3 | 20.5 (19.6) | 1.2 (0.33) | 74 | 175 |
| `!= NULL` | 2,873 / 7,810 | 358 | 368 | 349 | 7.0 | 18.6 (17.7) | 1.3 (0.41) | 81 | 208 |
| `return` (budget-truncated) | 24,608 / 657,290 | 2,423 | 2,520 | 2,478 | 14.0 | 31.7 (30.7) | 1.4 (0.43) | 134 | 254 |
| `kmalloc` scoped `/drivers/net/**` | 409 / 728 | 36 | 48 | 31 | 5.6 | 17.8 (17.0) | 1.1 (0.22) | 3 | 6 |

"Index stage" is the whole `_index_doc_ids` call: posting meta, blob
fetch, decode and set algebra. Under Rust that stage is almost all SQL
(0.7–1.4 ms); the algebra is 0.01–0.43 ms.

What this corrects in the 2026-08-16 profile:

- **"Index stage ≤ 25 ms" — confirmed** (0.9–14 ms with numpy, at up to
  46 K candidates).
- **"Verify is 82–99.7 % of every query" — no longer true.** That
  profile predates the Rust verify (ADR 039, spec 103 slice C). Today
  the per-call floor is **40 ms, not ~700 ms**: the 96 permanently
  unindexed big files (366 MB) cost 28 ms of content fetch plus ~12 ms
  of Rust verify, where they cost 1.13 s of Python `re`. On a
  mid-width query (`kmalloc`, 157 ms) the split is now: verify + result
  assembly ~45 ms (29 %), content fetch 82 ms (52 %), entry resolution
  24 ms (15 %), index 5.6 ms (3.6 %). Only the budget-saturated
  `return` row is still verify-dominated (~2.0 s of 2.4 s, at 657 K
  matching lines — much of it result assembly).
- So the numpy sites' share of user-visible grep latency is **2–4 %
  unscoped, 16 % on the scoped query** (5.6 of 36 ms). Rust takes the
  scoped query from 36 ms to 31 ms and its index share to 3 %; stdlib
  would have taken it to 48 ms (37 %). Content fetch, not the index, is
  the next thing to look at on the read path.

## 9. End-to-end: the two-round lexical search under each arm

No lexical verb exists yet (spec 132 is pending), so the study drives
the storage the way spec 132 will, per ADR 055 decision 4: the `lex_df`
probe and the head fetch (`block_no < 8`) as two statements; summary
decode (site 3); score the heads (site 5) to get θ and the round-one
candidates; `competing_blocks` per overflowing term (site 4); the
keyed round-two fetch (`(epoch = ? AND term = ? AND block_no IN (…))
OR …`); the final score (site 5). Per arm the three compute sites swap;
SQL time is bucketed apart from compute. Final top-k lists asserted
identical across arms. Median of 5 per query, then the median over the
arity's 10 queries.

| query | k | blocks scored | round-two blocks | **numpy total (SQL / compute)** | stdlib total (compute) | **Rust total (SQL / compute)** | Rust ÷ numpy |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1-term | 10 | 12 | 4 | 2.5 ms (1.0 / 1.4) | 3.5 (2.4) | **1.4 (1.0 / 0.4)** | 1.8× |
| 1-term | 1,000 | 16 | 8 | 2.9 (1.1 / 1.8) | 4.0 (3.0) | **1.6 (1.1 / 0.5)** | 1.8× |
| 3-term | 10 | 91 | 67 | 9.2 (1.4 / 7.8) | 14.9 (13.5) | **3.4 (1.3 / 2.1)** | 2.7× |
| 3-term | 1,000 | 242 | 218 | 17.3 (1.7 / 15.6) | 23.5 (21.9) | **5.1 (1.7 / 3.4)** | 3.4× |
| 6-term | 10 | 156 | 116 | 15.6 (1.7 / 13.8) | 23.0 (21.4) | **5.1 (1.5 / 3.6)** | 3.1× |
| 6-term | 1,000 | 592 | 552 | 38.1 (2.7 / 35.4) | 55.9 (53.6) | **9.8 (2.2 / 7.6)** | 3.9× |
| `struct if` | 10 | 2,916 | 2,900 | 157 (7.4 / 150) | 561 (553) | **55 (7.1 / 48)** | 2.9× |
| `struct if` | 1,000 | 5,983 | 5,967 | 314 (14.1 / 300) | 946 (932) | **96 (13.6 / 82)** | 3.3× |

- On SQLite the SQL side of a lexical query is 1–14 ms; **compute is
  85–95 % of the query** under the numpy arm. That is the opposite of
  grep, where the index side is 2–4 %. The lexical sites are where a
  kernel is user-visible.
- Rust makes the whole two-round query **2.7–3.9× faster** at 3–6 terms
  (9.2 → 3.4 ms; 38 → 9.8 ms), and the compute inside it 3.7–4.7×.
  Almost all of that is site 5, the scorer — which the live tree
  **already dispatches to Rust** (`score_blocks` → `lexical_score`).
  So today's tree, once spec 132 wires it, would already sit within
  ~1 ms of the Rust column: sites 3 + 4 together cost 0.3–0.8 ms of it
  under numpy and 0.01–0.15 ms under Rust (§5, §6).
- The two-round protocol's scale property holds in every arm: at
  k = 10 a 3-term query fetches 67 round-two blocks of the 1,553 it
  could (4.3 %), a 6-term query 116 of 1,534 (7.6 %). Spec 130's
  landing measured 9.7 % / 7.5 % with the whole-store bound; the
  difference is that this study fetches only competing blocks past the
  head, as the design says.
- The stdlib arm is 1.4–1.6× numpy end-to-end at 3–6 terms and 3–3.6×
  on the all-common query — the block-skip spelling saves it on
  ordinary queries and cannot on `struct if`.

## 10. The seam shape

ADR 057 decision 3 says: blobs cross the seam as bytes, survivors come
back as bytes or a Python list, and no array type is exposed at the
boundary. The question for the spec is whether `grep.py`'s `DocIds`
(an `NDArray[int64]` alias today) can become a plain `list[int]` with
no measurable cost at the two places `grep_rows` touches it after the
ladder: the `CANDIDATE_BUDGET` slice and the allow-list intersect. The
seam study measures each shape at the **widest** set the store can
produce (the `return` gram's 76,258 ids; the ladder's real union is
46 K) and at the budget (25,000).

| operation | packed bytes | Python `list[int]` | numpy array (today) |
|---|---:|---:|---:|
| produce the shape from the kernel's bytes, 76 K ids | — | 0.90 ms (boxing, ~12 ns/id) | 0.0004 ms (`np.frombuffer` view) |
| kernel returns `Vec<i64>` instead of bytes, 76 K | — | +0.95 ms | — |
| slice to `CANDIDATE_BUDGET` | 0.0035 ms (200 KB copy) | 0.058 ms | 0.0001 ms (view) |
| `tolist()` for the `IN`-list chunker, 25 K ids | 0.26 ms | 0.12 ms (a copy) | 0.29 ms |
| allow-list intersect, 76 K × 10 K (9,785 survivors) | **0.14 ms** (0.23 incl. packing the allow list) | 1.58 ms (set) | 2.42 ms (`intersect1d`) |
| payload held for 76 K ids | 596 KB | 2.7 MB | 596 KB |

Reading the table:

- **Boxing is the only cost, and it is paid today anyway.** The
  `IN`-list chunker needs Python ints for the binds, so `grep_rows`
  already boxes ≤ 25,000 ids via `.tolist()` (0.29 ms). A kernel that
  returns the survivors as a Python list capped at `cap` boxes the same
  25,000 ids once (0.26–0.30 ms) and nothing else ever needs boxing.
  **Net change at the budget: zero.** The one shape to avoid is boxing
  *before* the cap — a 76 K-id list costs 0.9 ms and 2.7 MB where bytes
  cost 596 KB.
- **The slice is free in every shape** (≤ 0.06 ms). The allow-list
  intersect is 10–17× cheaper in the kernel than in numpy and should
  move inside it, so the ids never leave Rust until they are capped.
- Therefore the recommended seam is **one call**:
  `candidate_ids(groups: list[list[bytes]], allow: list[int] | None,
  cap: int) -> tuple[list[int], int]` — the planner's chosen blobs per
  AND-group in rarest-first order (as the driver returns them), the
  scoped allow-list as the Python ints `allow_list_ids` already holds
  (a 10 K-int `Vec<i64>` extraction is ~0.1 ms, the same as packing),
  and back: at most `cap` sorted survivors as a Python list plus the
  uncapped count, so the caller can still raise the "candidate budget"
  truncation. Decode, AND, OR, allow-intersect and cap all happen
  inside; `DocIds` becomes `list[int]`; `.size`, the slice and
  `.tolist()` disappear from `grep_rows`; `PostingCorruptionError` is
  raised from the binding's `ValueError` at the call site. No
  `rust-numpy`, no buffer type in a signature, nothing for `ty` to
  model beyond `list[int]`.
- The blobs come in as `bytes` and pyo3's `PyBackedBytes` borrows them
  without a copy (it copies `bytearray`); `Vec<PyBackedBytes>` per
  group is what the study used. The lexical kernels take the same
  shape: `decode_summary(blob) -> (bytes, bytes)` packed, kept packed
  inside `BlockSummary` and handed straight to `competing_blocks(...)
  -> list[int]` (block numbers are ≤ a few thousand ints; boxing is
  ~0.05 ms at 5,983).

## 11. Specs that planned numpy (ADR 057 decision 4)

| spec | planned numpy use | what this memo says |
|---|---|---|
| 132 lexical leg | "scorer over the fetched blocks (numpy fallback)"; `competing_blocks`; `np.intersect1d` for scope | affected. The fallback is deleted with site 5 (Rust scorer exists); sites 3–4 are the ~80-line kernels above; scope intersect is the site 2 kernel's `intersect_sorted` (0.02–0.2 ms at 10 K ids) |
| 135 vector leg + fusion | `Fusion.fuse` "numpy over two short arrays"; MySQL/`GENERIC` client-floor vector scoring "in numpy with a running top-K" | fusion is ≤ 2 K floats — plain Python (a list comprehension over 1,000 pairs is ~0.1 ms; not measured here, arithmetic). The client-floor cosine over `membership_budget` batches of embeddings **is** a measured-scale kernel (thousands of rows × 384–1,536 dims per batch) — it belongs in the crate as `bytes in (f32 rows), top-K out`; not measured in this memo |
| 136 ranking signals | PageRank / Katz "~30-line numpy power-iteration kernel (`np.bincount`)" with a pure-Python fallback | `bincount` over edge arrays is exactly the shape sites 2 and 5 show Rust winning by 15–35×; at linux scale (83 K entries, ~100 K+ `fs` edges, 20 iterations) plain Python would be ~1 s per build, Rust tens of ms — a kernel, in the reindex phase, not on a query path. Not measured here |
| 137 `BM25Rerank` | "the same `vfs.native` scorer over freshly tokenized chunk texts, numpy fallback" | the fallback clause is void; the Rust scorer already serves. No new kernel |

## 12. What this means for the ADR 057 spec

**Recommendation — land in this order:**

1. **The fused grep kernel first** (sites 1 + 2 together, one call).
   It is the only site on a live user path today, it deletes numpy from
   both `postings.py` and `grep.py` at once (the two modules where
   numpy is load-bearing at import), and it is the biggest measured
   win: 12–36× vs numpy, ≤ 0.6 ms at the widest ladder this store
   makes. Shape: `candidate_ids(groups: list[list[bytes]], allow:
   list[int] | None, cap: int) -> list[int]` — blobs in, at most `cap`
   survivors out as a Python list (see §10). The corruption refusals
   move with it (`PostingCorruptionError` raised from the binding's
   `ValueError`). The `PurePostingsBuilder` stays only as the oracle
   ADR 057 decision 2 names, in `tests/support/`.
2. **The lexical summary decode and block selection** (sites 3 + 4) in
   the same slice as spec 132's query path, where they get their first
   caller. ~80 lines of Rust, 5–90× vs numpy, but sub-millisecond
   either way (0.3–0.8 ms of a 3.4–9.8 ms Rust-scored query) — landing
   them earlier buys nothing a user sees, and the lexical query's real
   cost, the scorer, is already Rust. `BlockSummary` keeps its
   two-field shape with packed `bytes` in place of arrays.
3. **Delete `pure_score_blocks`** (site 5) whenever numpy leaves
   `pyproject.toml` — the Rust scorer is the only caller-facing path
   already, and the parity test keeps a deliberately slow loop (the
   `score_blocks_full` spelling in the study is one) as its referee.

**Landing criteria the spec can cite** (this machine, this store):

| criterion | measured |
|---|---|
| grep ladder kernel, `return` (199 K postings → 46 K survivors) | ≤ 0.6 ms (0.35 measured); numpy 12.8 |
| grep ladder kernel, `kmalloc` (111 K postings → 4 K) | ≤ 0.3 ms (0.20); numpy 4.5 |
| scoped grep end-to-end, `kmalloc` under `/drivers/net/**` | ≤ 33 ms (31); numpy 36 |
| allow-list intersect, 46 K × 10 K | ≤ 0.25 ms (0.20 incl. packing); numpy 1.7 |
| summary decode, 5,983 blocks | ≤ 0.03 ms (0.016); loop 1.3–1.6 |
| block selection, 6 terms × 5 K candidates | ≤ 0.2 ms (0.15); numpy 0.8 |
| scorer, 3 terms / 1,553 blocks, k = 10 | unchanged: 4.4 ms Rust; numpy 76 |
| `tracemalloc` peak, scorer 3 terms | numpy 19 MB is gone; Rust holds its `Vec`s off-heap (untracked) |

**Gaps and risks, named:**

- **Rust memory is not measured by `tracemalloc`.** The kernels'
  internal `Vec`s are invisible to it; only their returned bytes show.
  The fused ladder's peak is bounded by the rarest blob's ids plus the
  survivors (`Vec<i64>` each) — ~0.8 MB for `return` — which is below
  numpy's 3.7 MB by construction, but this is arithmetic, not a
  measurement. An `ru_maxrss` run per arm in separate processes would
  close it.
- **The stdlib arm is a test oracle only.** Its numbers (2.4–3.7× numpy
  on the ladder, 11× the Rust scorer) say what shipping it would have
  cost: `kmalloc` scoped from 36 ms to 48 ms, the ladder at 31 ms on
  `return`. ADR 057 makes that moot; the `kernels_py.py` spellings are
  candidate oracles for `tests/support/`.
- **`struct if` stays at 72 ms** in Rust — the block-max limit ADR 055
  names, not a kernel problem.
- **Site 2 cross-driver input types.** `PyBackedBytes` is zero-copy
  from `bytes` and copies from `bytearray`/`memoryview`. aiosqlite,
  psycopg, pyodbc and oracledb all return `bytes` for `LargeBinary`,
  but the binding should accept the buffer protocol and the spec should
  pin one test per engine leg that the blob type reaching the kernel is
  `bytes`.
- **Not measured**: the 135 client-floor cosine kernel and the 136
  power-iteration kernel (shapes named in §11); a Postgres/MSSQL run
  (the SQL share of the lexical query will differ; the compute share
  will not).

**One-line version:** Rust beats numpy 5–36× at every site and the
kernels are small; the grep sites are only 2–16 % of a call while the
lexical sites are 85–95 % of a query (and the big one, the scorer, is
already Rust) — land the fused grep kernel first because it removes
numpy from the live path, keep the seam bytes-in/list-out, and let
sites 3–5 ride spec 132.
