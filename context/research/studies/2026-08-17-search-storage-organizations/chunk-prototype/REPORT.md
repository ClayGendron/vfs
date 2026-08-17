# Chunk-granularity grep: measured end-to-end, not just the bound

Prototype study, 2026-08-17. Question: does the 8.4-28.8x fetch-byte
reduction promised by chunk-granularity nomination (research memo
`2026-08-17-search-storage-organizations.md`, ARITH s1) convert into a
real end-to-end speedup on a real pipeline against a real
chunk-granularity gram index?

**Answer: mostly no on this backend, with two real wins and several
design lessons.** On warm local SQLite the chunk pipeline is a net
*loss* (aggregate 0.75-0.83x vs the identical file-granularity
pipeline; geomean 0.78x) despite a measured 6.6x total fetch-byte
reduction. Cold (fresh APFS clone per run), it wins only where the
byte cut is extreme (mutex_lock@drm 1.49x, rare-literal 1.60x) and
loses or washes elsewhere - cold cost is page-touch-shaped, and 2 KB
semantic chunks multiply candidate row count by 2.2-2.8x while cutting
bytes. Recall was **exact on every measured row**: purely chunk-local
gram emission lost zero matching lines across all 17 rows.

## Setup

- Store: APFS clone of `linux-bench/linux.sqlite` (93,760 files,
  93,664 encoded, 1.221 GB content; live gram index epoch 1: 257,012
  posting rows / 141.5 MB blobs). Repo untouched at `1b36b4a`;
  everything here lives in `chunk-proto/` on the clone
  (`linux-chunk.sqlite`), new `proto_*` tables only.
- Chunk source: the existing `vfs_chunks` (726,817 rows, avg 1,680 B,
  7.76 chunks/file; 87.5% of chunks are 1-2 KB). Verified on a
  300-entry sample: per entry, chunk contents concatenate **exactly**
  to the body (no gaps, no duplicated text); ~14% of chunk boundaries
  cut mid-line (147,927 corpus-wide) - the line-range "overlap" is a
  mid-line cut, not repeated text.
- Doc ids: dense, entry-major (entry path, then chunk ordinal), so
  each entry's chunks are one contiguous interval
  (`proto_entry_intervals`); mapping table `proto_chunk_map`
  (doc_id, chunk_rowid, entry_sid, entry_id, path, line extents,
  bytes). Same posting codec (`vfs.models.postings`), same fold, same
  builder, via the **Rust engine** (`vfs.native`, `active_core() ==
  "rust"`); emission is purely chunk-local (no boundary tail - that
  was the experiment).
- Harness (`harness.py`): one staged pipeline, mode-switched only at
  the posting source, doc-id space, and candidate fetch. Stages mirror
  `grep_rows` and reuse its live internals (`allow_list_ids`,
  `_plan_groups`/`_choose_grams`/`_ladder_defers`, `_entries_for_docs`,
  `_passes_gates`, `_entries_for_scan`, the native `hit_lines`
  matcher). Budgets: `POSTING_BYTE_BUDGET` as-is; candidate budget
  25,000 (both modes) plus an unbounded chunk leg. Ground truth: real
  `storage.grep` on the same clone (5-run medians), plus rg on the
  mirror for untruncated references. RUNS=5 medians throughout.

## Index build (the design's cost, measured)

| | live (gram,file) | proto (gram,chunk) | ratio |
|---|---|---|---|
| posting rows (grams) | 257,012 | 256,994 | 1.000 |
| postings pairs | 133,728,772 | 362,969,692 | **2.71x** |
| blob bytes | 141.5 MB | 386.2 MB | **2.73x** |

Build wall time: **11.7 s total** on the Rust engine (7.5 s fold+feed
of 1.22 GB, 0.8 s drain+insert, rest DDL and mapping rows). The
pure-Python fallback was not needed. The prior ARITH projection
(2.38x blobs, 2.42x pairs, from a 500-file sample) **underestimated**:
measured whole-corpus cost is 2.71-2.73x.

## The newline pin (step 3a)

For all 12 scoped-bench patterns and all 25 unscoped ladder patterns:
`build_code_gram_query` (fixed_strings where the bench uses it) emits
**zero grams containing byte 0x0A**. Every pattern plans indexable
(no `GramAny`). Pin: *no benchmark query can ever require a
newline-bearing gram*, so line-aligned chunk boundaries are invisible
to these plans; only mid-line cuts can matter. (`newline_pin.json`)

## Straddle findings (step 3b)

- **Zero recall loss.** Chunk-unbounded mode reproduced the exact
  (path, line) set of the file-granularity pipeline and real
  `storage.grep` on every non-truncating row (all 12 scoped + all
  measured unscoped except copyright, which truncates by design), and
  matched rg's untruncated 42,148 lines on `kfree -w`.
- The copyright -i gap (rg 89,002 vs chunk-unbounded 88,861) is
  **entirely** the 141 lines living in the 96 non-encoded scan-side
  files, which the chunk leg's overlay skip dropped (budget
  denomination artifact, below) - 0 lines lost in encoded files, 0
  false positives (`copyright_gap.json`).
- Straddle exposure is real but did not bite: 7 / 24 / 9 / 29 matching
  lines of mutex_lock@drm / kzalloc@net / EXPORT_SYMBOL_GPL@drivers /
  kfree sit on a mid-line chunk cut, and all were still found -
  a *line* split across chunks is only lost when the pattern
  *occurrence itself* is split by the cut, which occurred zero times.
  ARITH exp1b's "5/15/4/2 missed match-holding chunks" are chunks
  holding only a fragment of a matching line; the sibling chunk still
  nominates the line, so missed *chunks* != missed *lines*.
- Corpus-wide, exactly **18 grams** exist in the file index and not
  the chunk index - 16 contain `\n`, 2 are UTF-8 BOM-byte straddles.
  No queryable literal in either bench can require them, but a
  production design must still close the hole (occurrence-split
  mid-line cuts and BOM/odd-byte patterns are legal inputs): emit each
  chunk with a 2-byte tail of its predecessor, or nominate file-level
  on boundary-gram hits.

## Warm results (5-run medians, same process, page cache warm)

ms; `chunk` = unbounded chunk leg (file-equivalent budget); `ex-ov` =
scan-overlay stage excluded from both (it is mode-independent: the 96
non-encoded files, up to ~365 MB verified per call, identical cost
both sides). n% = file/chunk (>1 means chunk faster).

| row | real | file | chunk | n% | file ex-ov | chunk ex-ov | n% ex-ov |
|---|---|---|---|---|---|---|---|
| EXPORT_SYMBOL_GPL @ drivers/** | 203.0 | 159.1 | 227.0 | 0.70x | 106.5 | 172.4 | 0.62x |
| kzalloc @ drivers/net/** | 71.3 | 61.4 | 79.0 | 0.78x | 59.7 | 77.3 | 0.77x |
| mutex_lock @ drivers/gpu/drm/** | 112.3 | 105.0 | 113.7 | 0.92x | 52.0 | 60.8 | 0.85x |
| copyright -i @ fs/ext4/** (defers) | 6.2 | 5.3 | 9.4 | 0.56x | 4.1 | 8.0 | 0.52x |
| napi_gro_receive @ drivers/net/** | 27.4 | 25.1 | 38.0 | 0.66x | 23.5 | 36.6 | 0.64x |
| GFP_KERNEL @ mm/** | 12.4 | 11.5 | 17.9 | 0.64x | 10.1 | 16.7 | 0.61x |
| cgroup_subsys_state ext=h | 59.4 | 59.2 | 60.7 | 0.98x | 5.9 | 7.0 | 0.84x |
| cgroup_subsys_state @ *.h | 60.0 | 58.6 | 59.5 | 0.98x | 5.7 | 6.8 | 0.84x |
| spin_lock @ kernel/**/*.c | 20.5 | 17.7 | 36.7 | 0.48x | 16.2 | 35.2 | 0.46x |
| napi_gro_receive NOT drivers/** | 9.3 | 9.4 | 9.5 | 1.00x | 6.3 | 6.5 | 0.96x |
| probe @ spi-*.c | 34.1 | 32.1 | 92.3 | 0.35x | 30.7 | 92.3 | 0.33x |
| obj- @ Makefile | 79.9 | 51.9 | 45.1 | 1.15x | 50.3 | 43.5 | 1.16x |
| copyright -i unscoped (see note) | 925.0 | 508.2 | 779.1 | 0.65x | 508.2 | 779.1 | 0.65x |
| EXPORT_SYMBOL_GPL unscoped | 253.0 | 176.6 | 152.4 | 1.16x | 120.3 | 95.8 | 1.26x |
| kfree -w unscoped | 516.8 | 349.6 | 281.6 | 1.24x | 294.8 | 281.6 | 1.05x |
| randomize_kstack_offset | 60.3 | 60.1 | 57.9 | 1.04x | 5.9 | 4.2 | 1.40x |
| xyzzy_no_such_symbol_42 (zero-hit) | 58.5 | 57.2 | 55.9 | 1.02x | 3.4 | 3.1 | 1.12x |

**Aggregate: file 1,748 ms vs chunk 2,116 ms with overlay (0.83x);
1,304 vs 1,727 ex-overlay (0.75x); geomean per-row 0.80x / 0.78x.**
Total candidate fetch: file 1,297.7 MB vs chunk 197.4 MB - a real
**6.6x byte reduction that still loses wall time warm**, because warm
SQLite returns bytes at page-cache speed (~17 ms for 94 MB) while the
chunk side pays 2.2-2.8x more candidate rows, a chunk_map resolution
stage, allow-list->interval expansion, and 2.7x posting decode.
Recall (all three sources agree exactly): every row OK except the
designed truncations; detail in `results.json`. Per-row posting bytes
read, candidates fetched, and fetch bytes for both modes are in
`results.json` (`metrics`).

copyright -i unscoped note: the chunk-unbounded leg does *more work*
than file mode - full recall (88,861 lines, 58,144 chunks / 92.8 MB)
vs file mode truncated at 25,000 files (40,926 lines, 419.9 MB), so
0.65x understates chunking there. The near-equal-work comparison is
the 25,000-chunk leg: **310.7 ms vs 508.2 ms (1.64x) for ~the same
line count (40,763 vs 40,926)** - chunking turns the corpus's worst
truncating row from 508 ms to 311 ms, or serves *full* recall in
779 ms where file mode cannot without fetching 700+ MB.

## Cold results (fresh APFS clone per run - a new vnode defeats the page cache; overlay excluded, it is mode-independent; 5-run medians)

| row | file cold | chunk cold | n% |
|---|---|---|---|
| EXPORT_SYMBOL_GPL @ drivers/** | 468.0 | 489.4 | 0.96x |
| kzalloc @ drivers/net/** | 223.4 | 263.7 | 0.85x |
| mutex_lock @ drivers/gpu/drm/** | 251.4 | 168.2 | **1.49x** |
| copyright -i unscoped, 25k budget | 1,115.0 | 812.4 | **1.37x** (~equal work) |
| copyright -i unscoped, unbounded | 1,115.0 (truncated) | 2,156.0 (full recall) | n/a |
| kfree -w unscoped | 1,119.5 | 1,224.7 | 0.91x |
| randomize_kstack_offset | 51.6 | 32.2 | **1.60x** |

Cold attribution (per-stage, `cold_results.json`): the fetch stage
does win where ARITH predicted - mutex_lock@drm content_fetch 179.5 ->
65.9 ms (2.7x, matching exp1d's 2.6x) - but kzalloc's fetch barely
moves (149.4 -> 139.5 ms: 3,175 chunk rows cost what 1,437 full bodies
cost, because cold cost is per-page-touch, and 2 KB chunk rows are a
sparse subset of scattered pages), and the chunk-only stages
(interval expansion 14-71 ms, chunk_map 10-137 ms, 2x decode) eat the
remainder. **The rare-literal row the brief flagged as the potential
2.38x-posting-cost net loss (randomize_kstack_offset) is the opposite
- chunking's best cold win (1.60x)**: its posting bill rose only
13.5 KB -> 29.6 KB while its fetch fell 5.2 MB -> 53 KB. The posting-
size fear was misplaced; the real threat to chunking is candidate
*row multiplication* on hot patterns, not posting bytes on rare ones.

## Where chunking lost, and why

1. **Warm local SQLite makes bytes nearly free.** The lever's premise
   ("fetch bytes dominate") holds for *bytes* but not for *time* on a
   warm mmap'd store; the chunk pipeline's extra per-row and per-stage
   costs (chunk_map, interval expansion, 2.7x decode, 2.2-2.8x fetch
   units) exceed the byte savings on 13 of 17 rows.
2. **2 KB semantic chunks are the wrong retrieval quantum.** 7.76
   chunks/file at avg 1,680 B means a matched file frequently
   nominates several chunks; candidate row count - the unit cold
   page-touch cost and networked round trips actually price - grows
   faster than bytes shrink. The field's 16-64 KB fixed retrieval
   chunks would cut the multiplier ~8-32x at the same byte bound;
   this measurement is direct evidence for the memo's "semantic
   chunks are the wrong fetch unit as-is" caveat.
3. **`CANDIDATE_BUDGET` must be denominated in files (or re-derived),
   not reused as a chunk count.** At 25,000 *chunks*, `probe @
   spi-*.c` returned **0 of 601 lines** (34,829 laddered chunks,
   truncated in path order before the name-fact gate could focus
   them), and the overlay-consultation rule (`remaining =
   CANDIDATE_BUDGET - candidates`) silently skipped the scan side on
   kfree/copyright chunk legs (the 141-line copyright gap). Any spec
   must translate the budget into the chunk domain (e.g. budget
   entries, not chunks, or budget after entry-level gating).
4. **The allow-list seam changes shape.** Entry ids must become chunk
   intervals; the prototype's `proto_entry_intervals` lookup cost
   14-71 ms cold on wide scopes (drivers/** = 20k entries). A real
   design would carry interval bounds on the entry row or the segment
   postings - but the cost is structural: scoped chunk grep pays an
   extra mapping join somewhere.

Where it won: rows with extreme byte cuts and low chunk multiplication
(mutex_lock@drm cold 1.49x), rare literals (1.60x cold, 1.40x warm
ex-overlay), zero-hit ladder cost (parity), the biggest warm unscoped
verifies (EXPORT_SYMBOL_GPL 1.26x, kfree 1.05x ex-overlay - the
verify stage itself is consistently 2-3x cheaper on chunk text), and
the truncating row at equal work (1.37-1.64x). Chunking also lets the
same budget deliver *full* recall on copyright -i at 92.8 MB fetched
where file mode needs 700+ MB.

## What this harness does NOT capture

- **Result assembly and the session/op floor**: both modes stop at
  (path, line) pairs - no `Observation` construction, no Result
  envelope, no router/MCP layers. Real `storage.grep` medians are
  reported beside the staged runs (the staged file mode tracks them
  within ~10-35%; the gap is assembly + op overhead). Both modes
  exclude them **equally**, so ratios are unaffected but absolute ms
  are optimistic.
- **The scan overlay was file-shaped in both modes** and excluded from
  ex-overlay/cold numbers; a production chunk mode would run the same
  file-shaped overlay, so this is fair, but the overlay's own cost
  (~52 ms warm on this store's 96 huge non-encoded files) is a shared
  tax the chunk lever cannot touch.
- **Networked engines are the untested case the lever most plausibly
  serves**: on Postgres/MSSQL/Oracle, fetch cost is round-trip- and
  row-shaped, not page-shaped; 6.6x fewer bytes but 2.5x more rows
  could land either way. This experiment prices SQLite only.
- **No boundary-tail emission was built** (that was the point - it
  proved unnecessary for recall on every measured query), so the
  2.73x index cost is the floor; closing the occurrence-split hole
  adds a small increment.
- **No concurrent writers, single caller, MacBook NVMe**; cold = new
  APFS vnode, not a cold device.

## Verdict for the decide stage

The chunk lever as previously sketched - chunk postings over the
existing 2 KB semantic chunks - **does not clear its bar on the
measured backend**: 2.73x index bytes for a warm-aggregate 0.75-0.83x
(a slowdown), with genuine wins confined to extreme-cut rows, rare
literals, and truncating rows. The bound->speedup conversion fails
because cold/remote cost is row-shaped, not byte-shaped. If the
lever proceeds, this measurement argues for: (a) 16-64 KB fixed
retrieval chunks (cuts the row multiplier ~10x), (b) budget
denominated in entries, (c) interval mapping carried on entry rows,
(d) boundary-tail emission for the occurrence-split hole, and (e) a
networked-engine measurement before committing, since that is the
deployment whose cost shape actually matches the lever's premise.

## Files

- `build_index.py`, `build_stats.json` - proto index build (11.7 s, ratios)
- `newline_pin.py`, `newline_pin.json` - the 37-pattern newline pin
- `harness.py`, `results.json` - dual-mode staged pipeline, warm suite
- `cold_one.py`, `cold_driver.py`, `cold_results.json` - cold experiment
- `straddle_diag2.py`, `copyright_gap.json` - recall/straddle diagnosis
- `probe_chunks.py`, `smoke.py` - chunk-shape probe, harness smoke test
- `linux-chunk.sqlite` - the clone (proto_* tables added; originals untouched)
