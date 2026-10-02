# Filter-shape study: results

Run 2026-09-30 on an Apple-silicon laptop. Corpus: 50,000 files at
`/tNN/fNNN/docNNN.md` (10 tops × 100 folders × 50 files), plus 1,010
directory rows, one chunk per file, written in shuffled order (write order is
not path order), dim-64 embeddings. Median of 5 warm runs, milliseconds.
Every method agreed exactly with every other on every caller (the scripts
assert it).

Callers:

| caller | grants | visible chunks |
|---|---|---|
| 1 grant (10%) | `/t03` | 5,000 |
| 5 grants (0.5%) | 5 folders | 250 |
| 100 grants (10%) | every 10th folder | 5,000 |
| 500 grants (50%) | every other folder | 25,000 |
| 5000 file grants (10%) | every 10th file | 5,000 |

Shapes:

- **like**: today's arms, `path = :p OR path LIKE :p/%`, OR'd, 400 arms per
  statement; rows fetched and deduplicated when over 400.
- **range**: the same arms spelled as byte ranges `(path > :p/ AND path < :p0)`.
- **join / values join / unnest**: the caller's rights as rows of `[lo, hi)`
  byte ranges (a temp table, an inline `VALUES` list, or two Postgres array
  binds), joined to `entry` on `path >= lo AND path < hi`.
- **ordinal**: an epoch table `lex_order(epoch, path, chunk_id, ord, cum_dl)`
  numbering chunks in path order with a running length sum. `N` and `Σ dl`
  for a range are two index seeks.
- **post-filter**: the vector leg's whole-mount statement, unfiltered, with
  the caller's ranges checked in Python on the returned rows; the window
  deepens 4× until 10 visible rows arrive.

## SQLite 3.50.4 (`filter_shapes.py`)

Whole-mount vector leg (no filter): 32.6 ms.

| caller | corpus: like | corpus: range | corpus: join | corpus: ordinal | vector: like | vector: range | vector: join |
|---|---|---|---|---|---|---|---|
| 1 grant (10%) | 4.7 | 4.6 | 4.1 | 0.07 | 7.5 | 7.9 | 7.0 |
| 5 grants (0.5%) | 0.3 | 0.2 | 0.2 | 0.08 | 0.4 | 0.3 | 0.3 |
| 100 grants (10%) | 230.2 | 212.6 | 4.2 | 0.58 | 21.7 | 22.0 | 6.9 |
| 500 grants (50%) | 937.1 | 980.4 | 26.1 | 3.02 | 264.4 | 276.7 | 35.6 |
| 5000 file grants (10%) | 10,787.0 | 10,932.7 | 16.5 | 29.99 | 145.9 | 95.6 | 17.2 |

Plans at 100 grants: **like** and **range** both drive from `lex_docs`
(`SEARCH d USING COVERING INDEX ix_docs_entry (epoch=?)`), look up each
entry, and test every arm on every row. **join** scans the range list and
seeks the path index per range (`SEARCH e USING INDEX ... (path>? AND path<?)`).
At 2,000 chunks the same arms plan as `MULTI-INDEX OR`; the planner flips to
the row scan as the table grows.

`join_variants.py` (same corpus):

| caller | temp join | values join | values, split every 500 ranges | range arms, entry-first |
|---|---|---|---|---|
| 1 grant (10%) | 3.9 | 4.0 | 4.0 | 4.3 |
| 5 grants (0.5%) | 0.2 | 0.2 | 0.2 | 0.2 |
| 100 grants (10%) | 4.2 | 4.2 | 3.9 | 18.6 |
| 500 grants (50%) | 25.7 | 22.9 | 20.8 | 242.2 |
| 5000 file grants (10%) | 14.6 | 11.5 | 12.1 | 56.3 |

Forcing the arms to drive from `entry` (a `CROSS JOIN`) gives
`MULTI-INDEX OR` and helps at 100 grants, but not at 500. The split `VALUES`
join sums per-slice aggregates with no row fetch, because the ranges are
disjoint.

## Postgres 17.11 + pgvector 0.8.6, docker test container (`filter_shapes_pg.py`, `pg_variants.py`)

Timings on the container are noisier: the whole-mount vector leg measured
16.7 ms in one run and 34.1 ms in the next.

| caller | corpus: like | corpus: values join (500 ranges/stmt) | corpus: ordinal (500/stmt) | vector: like | vector: values join |
|---|---|---|---|---|---|
| 1 grant (10%) | 6.3 | 6.3 | 0.63 | 7.9 | 6.8 |
| 5 grants (0.5%) | 1.7 | 6.8 | 0.76 | 1.6 | 32.9 |
| 100 grants (10%) | 14.6 | 8.8 | 2.96 | 16.1 | 24.9 |
| 500 grants (50%) | 147.6 | 43.9 | 15.98 | 51.7 | 64.0 |
| 5000 file grants (10%) | 289.6 | 312.7 | 159.56 | 334.1 | 1,758.1 |

`like` plans as a hash join with a sequential scan of `lex_docs`, the arms
tested once per entry row. Postgres evaluates the arms far faster than
SQLite, but the cost still grows with grants × rows.

One statement for every grant count (`pg_variants.py`, array binds):

| caller | corpus: unnest | corpus: ordinal, unnest | vector: unnest | vector: post-filter (final window) |
|---|---|---|---|---|
| 1 grant (10%) | 13.4 | 4.94 | 20.5 | 59.0 (160) |
| 5 grants (0.5%) | 10.4 | 2.02 | 52.5 | 187.1 (10,240) |
| 100 grants (10%) | 20.7 | 9.17 | 39.5 | 63.4 (160) |
| 500 grants (50%) | 36.0 | 20.19 | 39.1 | 41.1 (40) |
| 5000 file grants (10%) | 34.8 | 99.92 | 111.8 | 45.1 (160) |

The `VALUES` slices at 5,000 file grants cost 20 statements, each planned
as a hash join over the whole chunk table (the planner cannot see the range
list's selectivity), which is why the vector leg reached 1.8 s there. The
array-bind form is one statement and stays flat (35 ms corpus, 112 ms
vector). Post-filtering is cheapest when the caller sees much of the mount
and worst when it sees little (0.5 % visible needed a 10,240-row window).

## Scale: the join grows with visible rows, the ordinal does not (`scale_ordinal.py`, SQLite)

| chunks | caller | visible | join (ms) | ordinal (ms) |
|---|---|---|---|---|
| 50,000 | 1 grant (10%) | 5,000 | 3.9 | 0.06 |
| 50,000 | 100 grants | 5,000 | 4.1 | 0.54 |
| 500,000 | 1 grant (10%) | 50,000 | 82.8 | 0.06 |
| 500,000 | 100 grants | 5,000 | 9.2 | 0.63 |

The join touches every visible row, so a caller who sees 10 % of a
ten-times-bigger mount pays ten times more. The ordinal seeks cost the same
at both sizes: two seeks per range.

## What the numbers say

1. The cost is the **predicate shape and the plan**, not the grant count as
   such. OR'd arms make the engine test every arm against every row. A range
   join makes it seek once per range and touch only visible rows.
2. On SQLite, the join is 50× faster at 100 grants, 36× at 500, and 650× at
   5,000 file grants, and it stays under 30 ms at every size.
3. On Postgres the arms are cheaper, but still grow with grants × rows. A
   single array-bind statement stays flat at 21–36 ms.
4. Ordinal seeks make `N` and `Σ dl` cost two seeks per range, independent of
   how many rows are visible (0.6 ms at 100 grants on SQLite). They lose to
   the join only when ranges outnumber visible rows' worth of work (5,000
   single-file grants).
5. The vector leg wants a switch: pre-filter (join) when the caller sees
   little, post-filter (the whole-mount statement) when the caller sees a
   lot. The exact visible count, which glean computes first anyway, is the
   selectivity estimate.
