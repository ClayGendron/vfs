<!-- Produced by `uv run --no-sync python visible_df_cost.py` on 2026-09-28 (Apple silicon laptop, vfs engine protocol 10). Raw output, unedited below this line. -->

# Visible-set statistics on vfs block postings (SciFact, vfs engine)

## Block-max bounds under visible statistics (SciFact, N = 5,183)

| hidden | shape | blocks | stored bound too low | rescaled bound too low | median true/rescaled |
|---|---|---|---|---|---|
| 5% | clustered | 38,348 | 5,407 (14.1%) | 0 | 0.999 |
| 5% | scattered | 38,243 | 5,564 (14.5%) | 0 | 1.000 |
| 50% | clustered | 27,876 | 3,608 (12.9%) | 0 | 0.994 |
| 50% | scattered | 28,803 | 3,119 (10.8%) | 0 | 0.994 |
| 90% | clustered | 12,368 | 679 (5.5%) | 0 | 0.910 |
| 90% | scattered | 13,755 | 637 (4.6%) | 0 | 0.891 |

## Per-partition df rows on SciFact (global summary rows: 36,764)

| partitions | shape | (term, partition) rows | x global |
|---|---|---|---|
| 4 | contiguous | 74,005 | 2.01 |
| 4 | random | 74,390 | 2.02 |
| 16 | contiguous | 142,257 | 3.87 |
| 16 | random | 142,787 | 3.88 |
| 64 | contiguous | 250,937 | 6.83 |
| 64 | random | 251,722 | 6.85 |
| 256 | contiguous | 384,880 | 10.47 |
| 256 | random | 383,467 | 10.43 |

## Cost at 1 x SciFact: N = 5,183, vocabulary 36,764, postings 620,499, id-blob bytes 788,690 (build 0.7s)

Today's ranking fetch, lower bound (head blocks only, id blobs; tf and dl blobs roughly double it):

| per query | mean | median | p95 | max |
|---|---|---|---|---|
| head id-blob KB | 5.2 | 4.9 | 9.6 | 13.0 |

### hidden 5%, clustered (259 hidden ids; 1 id ranges; methods disagree on 0 queries)

| per query | mean | median | p95 | max |
|---|---|---|---|---|
| full: blocks decoded | 116.8 | 114.0 | 227.0 | 275.0 |
| full: id-blob KB fetched | 14.1 | 13.6 | 27.6 | 33.5 |
| full: engine ms (decode + intersect) | 1.5 | 1.4 | 2.6 | 8.6 |
| complement: blocks decoded | 15.2 | 14.0 | 27.0 | 34.0 |
| complement: id-blob KB fetched | 1.7 | 1.6 | 3.3 | 3.9 |
| complement: engine ms | 0.2 | 0.2 | 0.3 | 2.2 |
| ranges: boundary blocks decoded | 13.6 | 13.0 | 25.0 | 30.0 |
| ranges: id-blob KB fetched | 1.5 | 1.4 | 2.9 | 3.4 |
| ranges: engine ms | 0.2 | 0.2 | 0.3 | 1.6 |

### hidden 5%, scattered (259 hidden ids; 254 id ranges; methods disagree on 0 queries)

| per query | mean | median | p95 | max |
|---|---|---|---|---|
| full: blocks decoded | 116.8 | 114.0 | 227.0 | 275.0 |
| full: id-blob KB fetched | 14.1 | 13.6 | 27.6 | 33.5 |
| full: engine ms (decode + intersect) | 1.0 | 1.0 | 1.9 | 3.8 |
| complement: blocks decoded | 116.8 | 114.0 | 227.0 | 275.0 |
| complement: id-blob KB fetched | 14.1 | 13.6 | 27.6 | 33.5 |
| complement: engine ms | 0.4 | 0.4 | 0.8 | 1.2 |
| ranges: boundary blocks decoded | 116.8 | 114.0 | 227.0 | 275.0 |
| ranges: id-blob KB fetched | 14.1 | 13.6 | 27.6 | 33.5 |
| ranges: engine ms | 0.4 | 0.4 | 0.8 | 1.1 |

### hidden 50%, clustered (2,591 hidden ids; 1 id ranges; methods disagree on 0 queries)

| per query | mean | median | p95 | max |
|---|---|---|---|---|
| full: blocks decoded | 116.8 | 114.0 | 227.0 | 275.0 |
| full: id-blob KB fetched | 14.1 | 13.6 | 27.6 | 33.5 |
| full: engine ms (decode + intersect) | 0.9 | 0.8 | 1.7 | 5.7 |
| complement: blocks decoded | 66.2 | 64.5 | 126.0 | 153.0 |
| complement: id-blob KB fetched | 8.0 | 7.7 | 15.5 | 18.9 |
| complement: engine ms | 0.9 | 0.8 | 1.7 | 6.7 |
| ranges: boundary blocks decoded | 18.9 | 18.0 | 35.0 | 41.0 |
| ranges: id-blob KB fetched | 1.9 | 1.8 | 3.7 | 4.6 |
| ranges: engine ms | 0.8 | 0.7 | 1.5 | 6.8 |

### hidden 50%, scattered (2,591 hidden ids; 1,294 id ranges; methods disagree on 0 queries)

| per query | mean | median | p95 | max |
|---|---|---|---|---|
| full: blocks decoded | 116.8 | 114.0 | 227.0 | 275.0 |
| full: id-blob KB fetched | 14.1 | 13.6 | 27.6 | 33.5 |
| full: engine ms (decode + intersect) | 1.2 | 0.9 | 2.1 | 25.4 |
| complement: blocks decoded | 116.8 | 114.0 | 227.0 | 275.0 |
| complement: id-blob KB fetched | 14.1 | 13.6 | 27.6 | 33.5 |
| complement: engine ms | 1.5 | 1.3 | 3.0 | 20.5 |
| ranges: boundary blocks decoded | 116.8 | 114.0 | 227.0 | 275.0 |
| ranges: id-blob KB fetched | 14.1 | 13.6 | 27.6 | 33.5 |
| ranges: engine ms | 1.5 | 1.3 | 2.8 | 15.6 |

### hidden 90%, clustered (4,664 hidden ids; 1 id ranges; methods disagree on 0 queries)

| per query | mean | median | p95 | max |
|---|---|---|---|---|
| full: blocks decoded | 116.8 | 114.0 | 227.0 | 275.0 |
| full: id-blob KB fetched | 14.1 | 13.6 | 27.6 | 33.5 |
| full: engine ms (decode + intersect) | 0.4 | 0.3 | 0.7 | 15.1 |
| complement: blocks decoded | 108.5 | 106.0 | 210.0 | 255.0 |
| complement: id-blob KB fetched | 13.3 | 12.8 | 26.1 | 31.7 |
| complement: engine ms | 1.5 | 1.4 | 2.7 | 19.9 |
| ranges: boundary blocks decoded | 18.9 | 18.0 | 34.0 | 40.0 |
| ranges: id-blob KB fetched | 1.8 | 1.7 | 3.5 | 4.2 |
| ranges: engine ms | 1.3 | 1.1 | 2.3 | 18.5 |

### hidden 90%, scattered (4,664 hidden ids; 471 id ranges; methods disagree on 0 queries)

| per query | mean | median | p95 | max |
|---|---|---|---|---|
| full: blocks decoded | 116.8 | 114.0 | 227.0 | 275.0 |
| full: id-blob KB fetched | 14.1 | 13.6 | 27.6 | 33.5 |
| full: engine ms (decode + intersect) | 0.5 | 0.4 | 1.1 | 9.8 |
| complement: blocks decoded | 116.8 | 114.0 | 227.0 | 275.0 |
| complement: id-blob KB fetched | 14.1 | 13.6 | 27.6 | 33.5 |
| complement: engine ms | 2.0 | 1.6 | 4.5 | 10.9 |
| ranges: boundary blocks decoded | 116.8 | 114.0 | 227.0 | 275.0 |
| ranges: id-blob KB fetched | 14.1 | 13.6 | 27.6 | 33.5 |
| ranges: engine ms | 1.9 | 1.6 | 4.2 | 9.5 |

## Cost at 40 x SciFact: N = 207,320, vocabulary 36,764, postings 24,819,960, id-blob bytes 30,622,718 (build 25.0s)

Today's ranking fetch, lower bound (head blocks only, id blobs; tf and dl blobs roughly double it):

| per query | mean | median | p95 | max |
|---|---|---|---|---|
| head id-blob KB | 11.9 | 11.0 | 21.3 | 24.7 |

### hidden 5%, clustered (10,366 hidden ids; 1 id ranges; methods disagree on 0 queries)

| per query | mean | median | p95 | max |
|---|---|---|---|---|
| full: blocks decoded | 4,389.6 | 4,241.0 | 8,626.0 | 10,462.0 |
| full: id-blob KB fetched | 566.6 | 547.1 | 1,111.4 | 1,348.9 |
| full: engine ms (decode + intersect) | 32.6 | 25.8 | 75.5 | 108.9 |
| complement: blocks decoded | 231.5 | 225.5 | 450.0 | 546.0 |
| complement: id-blob KB fetched | 30.2 | 29.4 | 58.3 | 71.0 |
| complement: engine ms | 3.4 | 2.8 | 7.8 | 12.0 |
| ranges: boundary blocks decoded | 21.5 | 20.0 | 39.0 | 46.0 |
| ranges: id-blob KB fetched | 3.1 | 2.9 | 5.5 | 6.6 |
| ranges: engine ms | 3.2 | 2.5 | 7.8 | 38.7 |

### hidden 5%, scattered (10,366 hidden ids; 9,872 id ranges; methods disagree on 0 queries)

| per query | mean | median | p95 | max |
|---|---|---|---|---|
| full: blocks decoded | 4,389.6 | 4,241.0 | 8,626.0 | 10,462.0 |
| full: id-blob KB fetched | 566.6 | 547.1 | 1,111.4 | 1,348.9 |
| full: engine ms (decode + intersect) | 21.6 | 20.6 | 38.4 | 45.3 |
| complement: blocks decoded | 4,387.1 | 4,239.0 | 8,624.0 | 10,457.0 |
| complement: id-blob KB fetched | 566.3 | 546.9 | 1,111.2 | 1,348.2 |
| complement: engine ms | 10.6 | 10.2 | 20.3 | 29.4 |
| ranges: boundary blocks decoded | 4,387.1 | 4,239.0 | 8,624.0 | 10,457.0 |
| ranges: id-blob KB fetched | 566.3 | 546.9 | 1,111.2 | 1,348.2 |
| ranges: engine ms | 10.6 | 10.2 | 19.9 | 48.9 |

### hidden 50%, clustered (103,660 hidden ids; 1 id ranges; methods disagree on 0 queries)

| per query | mean | median | p95 | max |
|---|---|---|---|---|
| full: blocks decoded | 4,389.6 | 4,241.0 | 8,626.0 | 10,462.0 |
| full: id-blob KB fetched | 566.6 | 547.1 | 1,111.4 | 1,348.9 |
| full: engine ms (decode + intersect) | 12.3 | 11.6 | 22.0 | 32.9 |
| complement: blocks decoded | 2,202.2 | 2,125.5 | 4,325.0 | 5,244.0 |
| complement: id-blob KB fetched | 284.7 | 275.1 | 557.7 | 676.6 |
| complement: engine ms | 11.3 | 10.7 | 20.4 | 30.4 |
| ranges: boundary blocks decoded | 22.7 | 21.0 | 41.0 | 48.0 |
| ranges: id-blob KB fetched | 3.3 | 3.1 | 5.9 | 7.2 |
| ranges: engine ms | 9.7 | 9.2 | 17.4 | 25.7 |

### hidden 50%, scattered (103,660 hidden ids; 51,929 id ranges; methods disagree on 0 queries)

| per query | mean | median | p95 | max |
|---|---|---|---|---|
| full: blocks decoded | 4,389.6 | 4,241.0 | 8,626.0 | 10,462.0 |
| full: id-blob KB fetched | 566.6 | 547.1 | 1,111.4 | 1,348.9 |
| full: engine ms (decode + intersect) | 13.9 | 13.2 | 25.1 | 39.4 |
| complement: blocks decoded | 4,389.6 | 4,241.0 | 8,626.0 | 10,462.0 |
| complement: id-blob KB fetched | 566.6 | 547.1 | 1,111.4 | 1,348.9 |
| complement: engine ms | 21.5 | 21.0 | 38.9 | 59.1 |
| ranges: boundary blocks decoded | 4,389.6 | 4,241.0 | 8,626.0 | 10,462.0 |
| ranges: id-blob KB fetched | 566.6 | 547.1 | 1,111.4 | 1,348.9 |
| ranges: engine ms | 21.5 | 20.9 | 39.2 | 55.2 |

### hidden 90%, clustered (186,588 hidden ids; 1 id ranges; methods disagree on 0 queries)

| per query | mean | median | p95 | max |
|---|---|---|---|---|
| full: blocks decoded | 4,389.6 | 4,241.0 | 8,626.0 | 10,462.0 |
| full: id-blob KB fetched | 566.6 | 547.1 | 1,111.4 | 1,348.9 |
| full: engine ms (decode + intersect) | 5.0 | 4.7 | 9.0 | 41.6 |
| complement: blocks decoded | 3,956.6 | 3,820.5 | 7,776.0 | 9,427.0 |
| complement: id-blob KB fetched | 511.4 | 493.7 | 1,003.1 | 1,216.5 |
| complement: engine ms | 20.9 | 19.8 | 37.3 | 46.4 |
| ranges: boundary blocks decoded | 23.2 | 22.0 | 41.0 | 49.0 |
| ranges: id-blob KB fetched | 3.3 | 3.2 | 5.9 | 7.4 |
| ranges: engine ms | 18.1 | 17.2 | 31.6 | 39.7 |

### hidden 90%, scattered (186,588 hidden ids; 18,573 id ranges; methods disagree on 0 queries)

| per query | mean | median | p95 | max |
|---|---|---|---|---|
| full: blocks decoded | 4,389.6 | 4,241.0 | 8,626.0 | 10,462.0 |
| full: id-blob KB fetched | 566.6 | 547.1 | 1,111.4 | 1,348.9 |
| full: engine ms (decode + intersect) | 5.8 | 5.5 | 10.7 | 14.3 |
| complement: blocks decoded | 4,389.6 | 4,241.0 | 8,626.0 | 10,462.0 |
| complement: id-blob KB fetched | 566.6 | 547.1 | 1,111.4 | 1,348.9 |
| complement: engine ms | 27.1 | 25.5 | 50.9 | 64.7 |
| ranges: boundary blocks decoded | 4,389.6 | 4,241.0 | 8,626.0 | 10,462.0 |
| ranges: id-blob KB fetched | 566.6 | 547.1 | 1,111.4 | 1,348.9 |
| ranges: engine ms | 27.5 | 25.9 | 50.7 | 66.6 |
