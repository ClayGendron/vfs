# Validating the spec-130b review on the prototype store

- **Date:** 2026-08-26
- **Script / results:** `prototype/review_validation.py` →
  `prototype/results/review_validation.json`; store `optionb_rs.sqlite`
  (block 128, 32,243 chunks, 3.09 M postings at 4.344 B each), the
  benchmark's drawn 1/3/6-term queries (15 each; a 3-term query is two
  mid-df terms plus one common, a 6-term query one rare, four mid, one
  common).
- **Question:** a staff review of the rewritten spec 130 made four
  claims and two small asks. Which hold on the design's own data?

## 1. The SQL fetch filter — confirmed, and worse than claimed

| arity | blocks/query (median) | `max_weight >= θ` (one scalar θ, the final top-10 floor): top-10 changed | blocks it drops | per-term WAND cut `θ − Σ others' max`: blocks skipped | same, with the true block max |
|---|---|---|---|---|---|
| 1 | 2 | 0 / 15 | 2.8 % | 2.8 % | 13.9 % |
| 3 | 84 | **15 / 15** | 98.5 % | **0.0 %** | 0.0 % |
| 6 | 90 | **15 / 15** | 98.7 % | **0.0 %** | 0.0 % |

A single θ as a per-row predicate strips every common-term block —
and the common term is what separates the rare-term docs, so every
multi-term top-10 changes. The WAND-correct per-term cut is safe and
never fires at three or six terms. **`AND max_weight >= :threshold`
leaves the design** (ADR 055 pin 2, spec 130 §2, spec 132).

Where the 65 % came from and whether it transfers: the common term is
**96 % of a 3-term query's bytes** (93 % at six). The reviewer's
two-round fetch — every other term's blocks whole, score, then the
common term's blocks only where they can still change the top-10 (the
block alone clears θ, or a candidate inside its id range could cross θ
with it; decided client-side from a per-block `(min_doc, max_weight)`
summary, no decode) — leaves in the engine:

| arity | common blocks skipped, one decision | progressive (re-score after each fetched block) | query bytes saved (one decision / progressive) |
|---|---|---|---|
| 3 | 67.8 % (68.8 % true max) | 72.0 % (72.9 %) | 65.2 % / 69.4 % |
| 6 | 73.4 % (74.1 %) | 76.6 % (77.3 %) | 68.4 % / 71.5 % |

So the 65 % does transfer — as a client-decided second fetch by
primary key, not as a SQL predicate. A range-overlap-only rule (no
scores: skip when no other term posts in the block's range and the
bound is under θ) gets 24 % at three terms and 8.5 % at six; the
candidate *scores* from round one are what make the skip.

**Impact ordering for all-common queries — not confirmed.** For
`struct if` (60 % and 54 % of chunks), fetching blocks by true max
descending with exact per-candidate bounds from the summaries needed
**280 of 281 blocks** before the top-10 was provably final: common
terms' block maxima are flat in docid order, so nothing saturates.
That is the known weakness of docid-ordered block-max on all-common
queries (impact-ordered postings are a different layout). The honest
position is that an all-common query fetches its lists; the summaries
make it no worse, and the size of the lists is the defence.

## 2. Scale — the arithmetic, and what the benchmark did not run

Commonest terms in the sample and their projected blob bytes
(4.344 B/posting, exact `dl` inline):

| term | share of chunks | full linux (~645 k chunks) | 10 M chunks | blocks at 10 M |
|---|---|---|---|---|
| struct | 59.6 % | 1.6 MB | 23.5 MB | 44 k |
| if | 54.5 % | 1.5 MB | 22.6 MB | 43 k |
| return | 46.0 % | 1.2 MB | 19.0 MB | 36 k |
| int | 45.8 % | 1.2 MB | 19.0 MB | 36 k |

The reviewer's "~10 MB at 10 M chunks" is ~19 MB with exact `dl`s. A
per-term summary at ~7 B per block (`min_doc` delta varint + the
block max) is ~0.05 B/posting: `return`'s summary at 10 M chunks is
~250 KB against 19 MB of blobs. The full-linux run (the spec's own
landing criterion) plus an adversarial all-common query is due before
the fetch shape is frozen; a 10 M-chunk store is a separate spike (a
~4 GB index, hours to build). The `dl`-array fork (a per-epoch
client-cached array, −1.9 of 4.34 B fetched) is real for a long-lived
process and irrelevant to a CLI call — a fork with a trigger.

## 3. `idf · tfc(max_tf, min_dl)` is a bound, not the maximum — confirmed

Over the 15,072 blocks of every term with `df ≥ 128`:

| true max / loose bound | value |
|---|---|
| median | 0.957 |
| p10 | 0.895 |
| minimum | 0.783 |
| blocks where the bound is exact | 2.8 % |

The finisher already holds the block; computing the true maximum at
the drain is one decode per block (3 M postings ≈ tens of
milliseconds). With it the per-term cut's skips at one term go from
2.8 % to 13.9 % and the two-round skips gain a point; more to the
point, "exact" becomes true. `max_tf` and `min_dl` then carry
nothing the true maximum does not — the columns go.

## 4. Update cadence — a decision, not a measurement

Not testable here. The current design: writes never touch the index;
a query overlays the `NOT encoded` set by tokenising it live against
the epoch's frozen statistics (ADR 051 pin 7, ADR 055 pin 7); reindex
is an explicit verb. The reviewer's delta tape (the first landing's
row-per-posting table as an insert-friendly store scored by
`SUM(weight)` against the frozen stats, folded in at the next rebuild)
is VectorChord's growing tape and exists at a351e7b. Its price: every
write tokenises and inserts ~100 rows per chunk inside the write
transaction, and the publish invariant gains a third state. The
question the reviewer asks — which write cadence vfs targets — is the
owner's.

## The two small asks

- **Tie-breaking and summation order** — agreed and free: both
  scorers accumulate in the same term / block / posting order
  (`np.bincount` adds sequentially; the Rust accumulator adds in the
  same order), so the sums are bit-identical, and the order is
  `score DESC, chunk_id ASC`.
- **Oracle and `IN` lists** — the block fetch lists are integers
  (`block_no`) chunked under `membership_budget` (Oracle's 1,000 is
  already the declared floor); the term list is the query's few terms.
  Term ids stay fork E2.
