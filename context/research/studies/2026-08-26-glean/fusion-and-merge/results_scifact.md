## Oracle (single index, mount A stack, top-10)

| nDCG@10 | MRR@10 | Recall@10 |
|---|---|---|
| 0.6057 | 0.5624 | 0.7561 |

## Mounts: hybrid A/B/C — split: random (sizes [1766, 1727, 1690]) — per-mount limit m=10

Union recall ceiling at 3m=30: 0.8506. Union docs with zero BM25 overlap: 504 (5.6% of union), of which relevant: 0.

| strategy | nDCG@10 | MRR@10 | Recall@10 | nDCG vs oracle |
|---|---|---|---|---|
| (i) naive score sort (Result.top) | 0.2125 | 0.1990 | 0.2842 | -0.3932 |
| (ii) round-robin interleave | 0.4767 | 0.3963 | 0.7477 | -0.1289 |
| (iii) RRF across mounts k=60 | 0.4768 | 0.3972 | 0.7462 | -0.1289 |
| (iv-a) min-max per mount, then sort | 0.4693 | 0.3912 | 0.7302 | -0.1363 |
| (iv-b) z-score per mount, then sort | 0.5050 | 0.4312 | 0.7518 | -0.1006 |
| (v) Clay: union + in-process BM25 (union stats) | 0.6390 | 0.6059 | 0.7649 | +0.0334 |
| (v') union + BM25 with corpus-wide stats | 0.6684 | 0.6351 | 0.7888 | +0.0628 |
| (vi-a) union + RRF(union BM25, per-mount minmax cos) | 0.5759 | 0.5212 | 0.7766 | -0.0298 |
| (vi-b) union + CC 0.5(union BM25 mm, per-mount mm cos) | 0.6092 | 0.5769 | 0.7418 | +0.0036 |
| (vi-c) union + CC 0.5 with corpus-wide BM25 stats | 0.6067 | 0.5730 | 0.7382 | +0.0010 |

## Mounts: hybrid A/B/C — split: random (sizes [1766, 1727, 1690]) — per-mount limit m=20

Union recall ceiling at 3m=60: 0.8856. Union docs with zero BM25 overlap: 1285 (7.1% of union), of which relevant: 2.

| strategy | nDCG@10 | MRR@10 | Recall@10 | nDCG vs oracle |
|---|---|---|---|---|
| (i) naive score sort (Result.top) | 0.2125 | 0.1990 | 0.2842 | -0.3932 |
| (ii) round-robin interleave | 0.4767 | 0.3963 | 0.7477 | -0.1289 |
| (iii) RRF across mounts k=60 | 0.4768 | 0.3972 | 0.7462 | -0.1289 |
| (iv-a) min-max per mount, then sort | 0.4624 | 0.3889 | 0.7093 | -0.1432 |
| (iv-b) z-score per mount, then sort | 0.5032 | 0.4335 | 0.7452 | -0.1024 |
| (v) Clay: union + in-process BM25 (union stats) | 0.6404 | 0.6084 | 0.7633 | +0.0348 |
| (v') union + BM25 with corpus-wide stats | 0.6657 | 0.6322 | 0.7873 | +0.0600 |
| (vi-a) union + RRF(union BM25, per-mount minmax cos) | 0.5838 | 0.5313 | 0.7749 | -0.0218 |
| (vi-b) union + CC 0.5(union BM25 mm, per-mount mm cos) | 0.6401 | 0.6077 | 0.7599 | +0.0344 |
| (vi-c) union + CC 0.5 with corpus-wide BM25 stats | 0.6259 | 0.5875 | 0.7676 | +0.0203 |

## Mounts: hybrid A/B/C — split: random (sizes [1766, 1727, 1690]) — per-mount limit m=50

Union recall ceiling at 3m=150: 0.9270. Union docs with zero BM25 overlap: 5148 (11.4% of union), of which relevant: 2.

| strategy | nDCG@10 | MRR@10 | Recall@10 | nDCG vs oracle |
|---|---|---|---|---|
| (i) naive score sort (Result.top) | 0.2125 | 0.1990 | 0.2842 | -0.3932 |
| (ii) round-robin interleave | 0.4767 | 0.3963 | 0.7477 | -0.1289 |
| (iii) RRF across mounts k=60 | 0.4768 | 0.3972 | 0.7462 | -0.1289 |
| (iv-a) min-max per mount, then sort | 0.4619 | 0.3890 | 0.7077 | -0.1438 |
| (iv-b) z-score per mount, then sort | 0.4945 | 0.4247 | 0.7403 | -0.1111 |
| (v) Clay: union + in-process BM25 (union stats) | 0.6527 | 0.6221 | 0.7689 | +0.0470 |
| (v') union + BM25 with corpus-wide stats | 0.6625 | 0.6310 | 0.7799 | +0.0569 |
| (vi-a) union + RRF(union BM25, per-mount minmax cos) | 0.5731 | 0.5207 | 0.7656 | -0.0325 |
| (vi-b) union + CC 0.5(union BM25 mm, per-mount mm cos) | 0.6578 | 0.6225 | 0.7864 | +0.0521 |
| (vi-c) union + CC 0.5 with corpus-wide BM25 stats | 0.6452 | 0.6056 | 0.7873 | +0.0395 |

## Mounts: hybrid A/B/C — split: topic (k-means k=3 on potion-8M) (sizes [1424, 1404, 2355]) — per-mount limit m=10

Union recall ceiling at 3m=30: 0.7998. Union docs with zero BM25 overlap: 526 (5.8% of union), of which relevant: 0.

| strategy | nDCG@10 | MRR@10 | Recall@10 | nDCG vs oracle |
|---|---|---|---|---|
| (i) naive score sort (Result.top) | 0.2743 | 0.2483 | 0.3668 | -0.3314 |
| (ii) round-robin interleave | 0.3647 | 0.2902 | 0.6112 | -0.2409 |
| (iii) RRF across mounts k=60 | 0.4014 | 0.3375 | 0.6115 | -0.2042 |
| (iv-a) min-max per mount, then sort | 0.3717 | 0.2933 | 0.6268 | -0.2339 |
| (iv-b) z-score per mount, then sort | 0.4378 | 0.3817 | 0.6218 | -0.1678 |
| (v) Clay: union + in-process BM25 (union stats) | 0.6372 | 0.6087 | 0.7499 | +0.0315 |
| (v') union + BM25 with corpus-wide stats | 0.6537 | 0.6262 | 0.7614 | +0.0480 |
| (vi-a) union + RRF(union BM25, per-mount minmax cos) | 0.5271 | 0.4730 | 0.7273 | -0.0786 |
| (vi-b) union + CC 0.5(union BM25 mm, per-mount mm cos) | 0.5616 | 0.5317 | 0.6818 | -0.0440 |
| (vi-c) union + CC 0.5 with corpus-wide BM25 stats | 0.5612 | 0.5303 | 0.6823 | -0.0445 |

## Mounts: hybrid A/B/C — split: topic (k-means k=3 on potion-8M) (sizes [1424, 1404, 2355]) — per-mount limit m=20

Union recall ceiling at 3m=60: 0.8634. Union docs with zero BM25 overlap: 1529 (8.5% of union), of which relevant: 2.

| strategy | nDCG@10 | MRR@10 | Recall@10 | nDCG vs oracle |
|---|---|---|---|---|
| (i) naive score sort (Result.top) | 0.2743 | 0.2483 | 0.3668 | -0.3314 |
| (ii) round-robin interleave | 0.3647 | 0.2902 | 0.6112 | -0.2409 |
| (iii) RRF across mounts k=60 | 0.4014 | 0.3375 | 0.6115 | -0.2042 |
| (iv-a) min-max per mount, then sort | 0.3716 | 0.2931 | 0.6290 | -0.2340 |
| (iv-b) z-score per mount, then sort | 0.4380 | 0.3829 | 0.6251 | -0.1677 |
| (v) Clay: union + in-process BM25 (union stats) | 0.6515 | 0.6205 | 0.7670 | +0.0458 |
| (v') union + BM25 with corpus-wide stats | 0.6607 | 0.6289 | 0.7781 | +0.0551 |
| (vi-a) union + RRF(union BM25, per-mount minmax cos) | 0.5197 | 0.4737 | 0.6874 | -0.0859 |
| (vi-b) union + CC 0.5(union BM25 mm, per-mount mm cos) | 0.5947 | 0.5643 | 0.7141 | -0.0110 |
| (vi-c) union + CC 0.5 with corpus-wide BM25 stats | 0.5784 | 0.5437 | 0.7124 | -0.0272 |

## Mounts: hybrid A/B/C — split: topic (k-means k=3 on potion-8M) (sizes [1424, 1404, 2355]) — per-mount limit m=50

Union recall ceiling at 3m=150: 0.9209. Union docs with zero BM25 overlap: 6217 (13.8% of union), of which relevant: 3.

| strategy | nDCG@10 | MRR@10 | Recall@10 | nDCG vs oracle |
|---|---|---|---|---|
| (i) naive score sort (Result.top) | 0.2743 | 0.2483 | 0.3668 | -0.3314 |
| (ii) round-robin interleave | 0.3647 | 0.2902 | 0.6112 | -0.2409 |
| (iii) RRF across mounts k=60 | 0.4014 | 0.3375 | 0.6115 | -0.2042 |
| (iv-a) min-max per mount, then sort | 0.3669 | 0.2916 | 0.6140 | -0.2388 |
| (iv-b) z-score per mount, then sort | 0.4366 | 0.3818 | 0.6268 | -0.1690 |
| (v) Clay: union + in-process BM25 (union stats) | 0.6635 | 0.6333 | 0.7807 | +0.0579 |
| (v') union + BM25 with corpus-wide stats | 0.6627 | 0.6312 | 0.7799 | +0.0570 |
| (vi-a) union + RRF(union BM25, per-mount minmax cos) | 0.5177 | 0.4636 | 0.7140 | -0.0879 |
| (vi-b) union + CC 0.5(union BM25 mm, per-mount mm cos) | 0.6189 | 0.5850 | 0.7441 | +0.0132 |
| (vi-c) union + CC 0.5 with corpus-wide BM25 stats | 0.6018 | 0.5678 | 0.7274 | -0.0039 |

## Mounts: C lexical-only — split: random (sizes [1766, 1727, 1690]) — per-mount limit m=10

Union recall ceiling at 3m=30: 0.8446. Union docs with zero BM25 overlap: 41 (0.5% of union), of which relevant: 0.

| strategy | nDCG@10 | MRR@10 | Recall@10 | nDCG vs oracle |
|---|---|---|---|---|
| (i) naive score sort (Result.top) | 0.2526 | 0.2573 | 0.2782 | -0.3530 |
| (ii) round-robin interleave | 0.5064 | 0.4186 | 0.7954 | -0.0993 |
| (iii) RRF across mounts k=60 | 0.5353 | 0.4605 | 0.7913 | -0.0704 |
| (iv-a) min-max per mount, then sort | 0.5000 | 0.4142 | 0.7804 | -0.1056 |
| (iv-b) z-score per mount, then sort | 0.5637 | 0.4978 | 0.7904 | -0.0420 |
| (v) Clay: union + in-process BM25 (union stats) | 0.6257 | 0.5877 | 0.7681 | +0.0200 |
| (v') union + BM25 with corpus-wide stats | 0.6673 | 0.6346 | 0.7854 | +0.0616 |
| (vi-a) union + RRF(union BM25, per-mount minmax cos) | 0.5975 | 0.5489 | 0.7733 | -0.0082 |
| (vi-b) union + CC 0.5(union BM25 mm, per-mount mm cos) | 0.6337 | 0.5987 | 0.7661 | +0.0281 |
| (vi-c) union + CC 0.5 with corpus-wide BM25 stats | 0.6349 | 0.5985 | 0.7709 | +0.0292 |

## Mounts: C lexical-only — split: random (sizes [1766, 1727, 1690]) — per-mount limit m=20

Union recall ceiling at 3m=60: 0.8876. Union docs with zero BM25 overlap: 262 (1.5% of union), of which relevant: 2.

| strategy | nDCG@10 | MRR@10 | Recall@10 | nDCG vs oracle |
|---|---|---|---|---|
| (i) naive score sort (Result.top) | 0.2526 | 0.2573 | 0.2782 | -0.3530 |
| (ii) round-robin interleave | 0.5064 | 0.4186 | 0.7954 | -0.0993 |
| (iii) RRF across mounts k=60 | 0.5353 | 0.4605 | 0.7913 | -0.0704 |
| (iv-a) min-max per mount, then sort | 0.4959 | 0.4121 | 0.7696 | -0.1098 |
| (iv-b) z-score per mount, then sort | 0.5665 | 0.5023 | 0.7921 | -0.0391 |
| (v) Clay: union + in-process BM25 (union stats) | 0.6371 | 0.6045 | 0.7606 | +0.0314 |
| (v') union + BM25 with corpus-wide stats | 0.6657 | 0.6322 | 0.7873 | +0.0600 |
| (vi-a) union + RRF(union BM25, per-mount minmax cos) | 0.5834 | 0.5307 | 0.7666 | -0.0222 |
| (vi-b) union + CC 0.5(union BM25 mm, per-mount mm cos) | 0.6477 | 0.6158 | 0.7666 | +0.0420 |
| (vi-c) union + CC 0.5 with corpus-wide BM25 stats | 0.6433 | 0.6085 | 0.7709 | +0.0376 |

## Mounts: C lexical-only — split: random (sizes [1766, 1727, 1690]) — per-mount limit m=50

Union recall ceiling at 3m=150: 0.9303. Union docs with zero BM25 overlap: 2155 (4.8% of union), of which relevant: 2.

| strategy | nDCG@10 | MRR@10 | Recall@10 | nDCG vs oracle |
|---|---|---|---|---|
| (i) naive score sort (Result.top) | 0.2526 | 0.2573 | 0.2782 | -0.3530 |
| (ii) round-robin interleave | 0.5064 | 0.4186 | 0.7954 | -0.0993 |
| (iii) RRF across mounts k=60 | 0.5353 | 0.4605 | 0.7913 | -0.0704 |
| (iv-a) min-max per mount, then sort | 0.4925 | 0.4108 | 0.7613 | -0.1131 |
| (iv-b) z-score per mount, then sort | 0.5642 | 0.5032 | 0.7864 | -0.0414 |
| (v) Clay: union + in-process BM25 (union stats) | 0.6448 | 0.6118 | 0.7663 | +0.0391 |
| (v') union + BM25 with corpus-wide stats | 0.6625 | 0.6310 | 0.7799 | +0.0569 |
| (vi-a) union + RRF(union BM25, per-mount minmax cos) | 0.5774 | 0.5261 | 0.7620 | -0.0282 |
| (vi-b) union + CC 0.5(union BM25 mm, per-mount mm cos) | 0.6592 | 0.6263 | 0.7798 | +0.0535 |
| (vi-c) union + CC 0.5 with corpus-wide BM25 stats | 0.6528 | 0.6172 | 0.7823 | +0.0471 |

## Mounts: C lexical-only — split: topic (k-means k=3 on potion-8M) (sizes [1424, 1404, 2355]) — per-mount limit m=10

Union recall ceiling at 3m=30: 0.8138. Union docs with zero BM25 overlap: 108 (1.2% of union), of which relevant: 0.

| strategy | nDCG@10 | MRR@10 | Recall@10 | nDCG vs oracle |
|---|---|---|---|---|
| (i) naive score sort (Result.top) | 0.3297 | 0.3181 | 0.3808 | -0.2759 |
| (ii) round-robin interleave | 0.4046 | 0.3176 | 0.6907 | -0.2010 |
| (iii) RRF across mounts k=60 | 0.4679 | 0.4002 | 0.6899 | -0.1378 |
| (iv-a) min-max per mount, then sort | 0.4082 | 0.3175 | 0.7030 | -0.1974 |
| (iv-b) z-score per mount, then sort | 0.5147 | 0.4619 | 0.6913 | -0.0910 |
| (v) Clay: union + in-process BM25 (union stats) | 0.6385 | 0.6075 | 0.7578 | +0.0329 |
| (v') union + BM25 with corpus-wide stats | 0.6578 | 0.6275 | 0.7748 | +0.0521 |
| (vi-a) union + RRF(union BM25, per-mount minmax cos) | 0.5664 | 0.5256 | 0.7230 | -0.0393 |
| (vi-b) union + CC 0.5(union BM25 mm, per-mount mm cos) | 0.5973 | 0.5631 | 0.7291 | -0.0083 |
| (vi-c) union + CC 0.5 with corpus-wide BM25 stats | 0.5906 | 0.5552 | 0.7276 | -0.0150 |

## Mounts: C lexical-only — split: topic (k-means k=3 on potion-8M) (sizes [1424, 1404, 2355]) — per-mount limit m=20

Union recall ceiling at 3m=60: 0.8768. Union docs with zero BM25 overlap: 555 (3.1% of union), of which relevant: 2.

| strategy | nDCG@10 | MRR@10 | Recall@10 | nDCG vs oracle |
|---|---|---|---|---|
| (i) naive score sort (Result.top) | 0.3297 | 0.3181 | 0.3808 | -0.2759 |
| (ii) round-robin interleave | 0.4046 | 0.3176 | 0.6907 | -0.2010 |
| (iii) RRF across mounts k=60 | 0.4679 | 0.4002 | 0.6899 | -0.1378 |
| (iv-a) min-max per mount, then sort | 0.4039 | 0.3157 | 0.6919 | -0.2017 |
| (iv-b) z-score per mount, then sort | 0.5166 | 0.4680 | 0.6905 | -0.0891 |
| (v) Clay: union + in-process BM25 (union stats) | 0.6467 | 0.6160 | 0.7640 | +0.0411 |
| (v') union + BM25 with corpus-wide stats | 0.6597 | 0.6286 | 0.7758 | +0.0540 |
| (vi-a) union + RRF(union BM25, per-mount minmax cos) | 0.5386 | 0.4933 | 0.7024 | -0.0671 |
| (vi-b) union + CC 0.5(union BM25 mm, per-mount mm cos) | 0.6078 | 0.5721 | 0.7424 | +0.0021 |
| (vi-c) union + CC 0.5 with corpus-wide BM25 stats | 0.5900 | 0.5569 | 0.7158 | -0.0156 |

## Mounts: C lexical-only — split: topic (k-means k=3 on potion-8M) (sizes [1424, 1404, 2355]) — per-mount limit m=50

Union recall ceiling at 3m=150: 0.9242. Union docs with zero BM25 overlap: 3411 (7.6% of union), of which relevant: 3.

| strategy | nDCG@10 | MRR@10 | Recall@10 | nDCG vs oracle |
|---|---|---|---|---|
| (i) naive score sort (Result.top) | 0.3297 | 0.3181 | 0.3808 | -0.2759 |
| (ii) round-robin interleave | 0.4046 | 0.3176 | 0.6907 | -0.2010 |
| (iii) RRF across mounts k=60 | 0.4679 | 0.4002 | 0.6899 | -0.1378 |
| (iv-a) min-max per mount, then sort | 0.3995 | 0.3138 | 0.6786 | -0.2061 |
| (iv-b) z-score per mount, then sort | 0.5194 | 0.4700 | 0.6997 | -0.0863 |
| (v) Clay: union + in-process BM25 (union stats) | 0.6586 | 0.6288 | 0.7763 | +0.0530 |
| (v') union + BM25 with corpus-wide stats | 0.6627 | 0.6312 | 0.7799 | +0.0570 |
| (vi-a) union + RRF(union BM25, per-mount minmax cos) | 0.5178 | 0.4699 | 0.6897 | -0.0878 |
| (vi-b) union + CC 0.5(union BM25 mm, per-mount mm cos) | 0.6094 | 0.5752 | 0.7341 | +0.0038 |
| (vi-c) union + CC 0.5 with corpus-wide BM25 stats | 0.6079 | 0.5753 | 0.7291 | +0.0022 |

