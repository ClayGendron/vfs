## Oracle (single index, mount A stack, top-10)

| nDCG@10 | MRR@10 | Recall@10 |
|---|---|---|
| 0.2948 | 0.4956 | 0.1386 |

## Mounts: hybrid A/B/C — split: random (sizes [1249, 1222, 1162]) — per-mount limit m=10

Union recall ceiling at 3m=30: 0.1829. Union docs with zero BM25 overlap: 3198 (33.0% of union), of which relevant: 43.

| strategy | nDCG@10 | MRR@10 | Recall@10 | nDCG vs oracle |
|---|---|---|---|---|
| (i) naive score sort (Result.top) | 0.1399 | 0.3202 | 0.0530 | -0.1549 |
| (ii) round-robin interleave | 0.2580 | 0.4286 | 0.1272 | -0.0369 |
| (iii) RRF across mounts k=60 | 0.2371 | 0.3600 | 0.1270 | -0.0577 |
| (iv-a) min-max per mount, then sort | 0.2600 | 0.4307 | 0.1281 | -0.0349 |
| (iv-b) z-score per mount, then sort | 0.2651 | 0.4381 | 0.1291 | -0.0298 |
| (v) Clay: union + in-process BM25 (union stats) | 0.2873 | 0.4733 | 0.1364 | -0.0075 |
| (v') union + BM25 with corpus-wide stats | 0.3097 | 0.5173 | 0.1452 | +0.0148 |
| (vi-a) union + RRF(union BM25, per-mount minmax cos) | 0.2550 | 0.4383 | 0.1279 | -0.0398 |
| (vi-b) union + CC 0.5(union BM25 mm, per-mount mm cos) | 0.2764 | 0.4863 | 0.1292 | -0.0184 |
| (vi-c) union + CC 0.5 with corpus-wide BM25 stats | 0.2863 | 0.4974 | 0.1328 | -0.0085 |

## Mounts: hybrid A/B/C — split: random (sizes [1249, 1222, 1162]) — per-mount limit m=20

Union recall ceiling at 3m=60: 0.2186. Union docs with zero BM25 overlap: 7485 (38.6% of union), of which relevant: 111.

| strategy | nDCG@10 | MRR@10 | Recall@10 | nDCG vs oracle |
|---|---|---|---|---|
| (i) naive score sort (Result.top) | 0.1399 | 0.3202 | 0.0530 | -0.1549 |
| (ii) round-robin interleave | 0.2580 | 0.4286 | 0.1272 | -0.0369 |
| (iii) RRF across mounts k=60 | 0.2371 | 0.3600 | 0.1270 | -0.0577 |
| (iv-a) min-max per mount, then sort | 0.2609 | 0.4306 | 0.1301 | -0.0339 |
| (iv-b) z-score per mount, then sort | 0.2645 | 0.4325 | 0.1304 | -0.0303 |
| (v) Clay: union + in-process BM25 (union stats) | 0.2898 | 0.4810 | 0.1385 | -0.0051 |
| (v') union + BM25 with corpus-wide stats | 0.3090 | 0.5163 | 0.1468 | +0.0141 |
| (vi-a) union + RRF(union BM25, per-mount minmax cos) | 0.2499 | 0.4306 | 0.1177 | -0.0450 |
| (vi-b) union + CC 0.5(union BM25 mm, per-mount mm cos) | 0.2871 | 0.5035 | 0.1322 | -0.0077 |
| (vi-c) union + CC 0.5 with corpus-wide BM25 stats | 0.2945 | 0.5083 | 0.1344 | -0.0004 |

## Mounts: hybrid A/B/C — split: random (sizes [1249, 1222, 1162]) — per-mount limit m=50

Union recall ceiling at 3m=150: 0.2759. Union docs with zero BM25 overlap: 23261 (48.0% of union), of which relevant: 377.

| strategy | nDCG@10 | MRR@10 | Recall@10 | nDCG vs oracle |
|---|---|---|---|---|
| (i) naive score sort (Result.top) | 0.1399 | 0.3202 | 0.0530 | -0.1549 |
| (ii) round-robin interleave | 0.2580 | 0.4286 | 0.1272 | -0.0369 |
| (iii) RRF across mounts k=60 | 0.2371 | 0.3600 | 0.1270 | -0.0577 |
| (iv-a) min-max per mount, then sort | 0.2603 | 0.4298 | 0.1312 | -0.0346 |
| (iv-b) z-score per mount, then sort | 0.2653 | 0.4530 | 0.1278 | -0.0295 |
| (v) Clay: union + in-process BM25 (union stats) | 0.2961 | 0.4939 | 0.1424 | +0.0012 |
| (v') union + BM25 with corpus-wide stats | 0.3077 | 0.5158 | 0.1465 | +0.0129 |
| (vi-a) union + RRF(union BM25, per-mount minmax cos) | 0.2466 | 0.4291 | 0.1152 | -0.0482 |
| (vi-b) union + CC 0.5(union BM25 mm, per-mount mm cos) | 0.2989 | 0.5041 | 0.1416 | +0.0040 |
| (vi-c) union + CC 0.5 with corpus-wide BM25 stats | 0.3035 | 0.5105 | 0.1453 | +0.0087 |

## Mounts: hybrid A/B/C — split: topic (k-means k=3 on potion-8M) (sizes [1206, 1253, 1174]) — per-mount limit m=10

Union recall ceiling at 3m=30: 0.1847. Union docs with zero BM25 overlap: 3354 (34.6% of union), of which relevant: 42.

| strategy | nDCG@10 | MRR@10 | Recall@10 | nDCG vs oracle |
|---|---|---|---|---|
| (i) naive score sort (Result.top) | 0.1433 | 0.3020 | 0.0624 | -0.1515 |
| (ii) round-robin interleave | 0.2329 | 0.3881 | 0.1270 | -0.0620 |
| (iii) RRF across mounts k=60 | 0.2142 | 0.3375 | 0.1254 | -0.0807 |
| (iv-a) min-max per mount, then sort | 0.2385 | 0.3879 | 0.1288 | -0.0564 |
| (iv-b) z-score per mount, then sort | 0.2392 | 0.3947 | 0.1310 | -0.0556 |
| (v) Clay: union + in-process BM25 (union stats) | 0.2898 | 0.4862 | 0.1385 | -0.0050 |
| (v') union + BM25 with corpus-wide stats | 0.3076 | 0.5204 | 0.1465 | +0.0127 |
| (vi-a) union + RRF(union BM25, per-mount minmax cos) | 0.2519 | 0.4220 | 0.1327 | -0.0429 |
| (vi-b) union + CC 0.5(union BM25 mm, per-mount mm cos) | 0.2682 | 0.4666 | 0.1332 | -0.0266 |
| (vi-c) union + CC 0.5 with corpus-wide BM25 stats | 0.2785 | 0.4823 | 0.1382 | -0.0164 |

## Mounts: hybrid A/B/C — split: topic (k-means k=3 on potion-8M) (sizes [1206, 1253, 1174]) — per-mount limit m=20

Union recall ceiling at 3m=60: 0.2159. Union docs with zero BM25 overlap: 7785 (40.2% of union), of which relevant: 120.

| strategy | nDCG@10 | MRR@10 | Recall@10 | nDCG vs oracle |
|---|---|---|---|---|
| (i) naive score sort (Result.top) | 0.1433 | 0.3020 | 0.0624 | -0.1515 |
| (ii) round-robin interleave | 0.2329 | 0.3881 | 0.1270 | -0.0620 |
| (iii) RRF across mounts k=60 | 0.2142 | 0.3375 | 0.1254 | -0.0807 |
| (iv-a) min-max per mount, then sort | 0.2384 | 0.3862 | 0.1279 | -0.0565 |
| (iv-b) z-score per mount, then sort | 0.2419 | 0.3983 | 0.1314 | -0.0529 |
| (v) Clay: union + in-process BM25 (union stats) | 0.2908 | 0.4845 | 0.1387 | -0.0040 |
| (v') union + BM25 with corpus-wide stats | 0.3091 | 0.5162 | 0.1477 | +0.0143 |
| (vi-a) union + RRF(union BM25, per-mount minmax cos) | 0.2529 | 0.4258 | 0.1294 | -0.0419 |
| (vi-b) union + CC 0.5(union BM25 mm, per-mount mm cos) | 0.2835 | 0.4895 | 0.1369 | -0.0113 |
| (vi-c) union + CC 0.5 with corpus-wide BM25 stats | 0.2901 | 0.4979 | 0.1387 | -0.0048 |

## Mounts: hybrid A/B/C — split: topic (k-means k=3 on potion-8M) (sizes [1206, 1253, 1174]) — per-mount limit m=50

Union recall ceiling at 3m=150: 0.2778. Union docs with zero BM25 overlap: 23976 (49.5% of union), of which relevant: 377.

| strategy | nDCG@10 | MRR@10 | Recall@10 | nDCG vs oracle |
|---|---|---|---|---|
| (i) naive score sort (Result.top) | 0.1433 | 0.3020 | 0.0624 | -0.1515 |
| (ii) round-robin interleave | 0.2329 | 0.3881 | 0.1270 | -0.0620 |
| (iii) RRF across mounts k=60 | 0.2142 | 0.3375 | 0.1254 | -0.0807 |
| (iv-a) min-max per mount, then sort | 0.2346 | 0.3852 | 0.1250 | -0.0603 |
| (iv-b) z-score per mount, then sort | 0.2461 | 0.4156 | 0.1335 | -0.0488 |
| (v) Clay: union + in-process BM25 (union stats) | 0.2956 | 0.4903 | 0.1424 | +0.0007 |
| (v') union + BM25 with corpus-wide stats | 0.3056 | 0.5147 | 0.1436 | +0.0108 |
| (vi-a) union + RRF(union BM25, per-mount minmax cos) | 0.2516 | 0.4209 | 0.1270 | -0.0432 |
| (vi-b) union + CC 0.5(union BM25 mm, per-mount mm cos) | 0.2896 | 0.4914 | 0.1374 | -0.0053 |
| (vi-c) union + CC 0.5 with corpus-wide BM25 stats | 0.2946 | 0.4966 | 0.1396 | -0.0002 |

## Mounts: C lexical-only — split: random (sizes [1249, 1222, 1162]) — per-mount limit m=10

Union recall ceiling at 3m=30: 0.1881. Union docs with zero BM25 overlap: 2738 (28.3% of union), of which relevant: 33.

| strategy | nDCG@10 | MRR@10 | Recall@10 | nDCG vs oracle |
|---|---|---|---|---|
| (i) naive score sort (Result.top) | 0.2079 | 0.4248 | 0.0850 | -0.0869 |
| (ii) round-robin interleave | 0.2718 | 0.4398 | 0.1369 | -0.0231 |
| (iii) RRF across mounts k=60 | 0.2579 | 0.3969 | 0.1360 | -0.0369 |
| (iv-a) min-max per mount, then sort | 0.2753 | 0.4413 | 0.1405 | -0.0196 |
| (iv-b) z-score per mount, then sort | 0.2882 | 0.4814 | 0.1363 | -0.0067 |
| (v) Clay: union + in-process BM25 (union stats) | 0.2893 | 0.4753 | 0.1374 | -0.0056 |
| (v') union + BM25 with corpus-wide stats | 0.3104 | 0.5179 | 0.1469 | +0.0155 |
| (vi-a) union + RRF(union BM25, per-mount minmax cos) | 0.2668 | 0.4511 | 0.1332 | -0.0280 |
| (vi-b) union + CC 0.5(union BM25 mm, per-mount mm cos) | 0.2872 | 0.4880 | 0.1401 | -0.0077 |
| (vi-c) union + CC 0.5 with corpus-wide BM25 stats | 0.2979 | 0.5034 | 0.1436 | +0.0030 |

## Mounts: C lexical-only — split: random (sizes [1249, 1222, 1162]) — per-mount limit m=20

Union recall ceiling at 3m=60: 0.2228. Union docs with zero BM25 overlap: 6503 (33.6% of union), of which relevant: 90.

| strategy | nDCG@10 | MRR@10 | Recall@10 | nDCG vs oracle |
|---|---|---|---|---|
| (i) naive score sort (Result.top) | 0.2079 | 0.4248 | 0.0850 | -0.0869 |
| (ii) round-robin interleave | 0.2718 | 0.4398 | 0.1369 | -0.0231 |
| (iii) RRF across mounts k=60 | 0.2579 | 0.3969 | 0.1360 | -0.0369 |
| (iv-a) min-max per mount, then sort | 0.2756 | 0.4416 | 0.1410 | -0.0193 |
| (iv-b) z-score per mount, then sort | 0.2885 | 0.4851 | 0.1374 | -0.0063 |
| (v) Clay: union + in-process BM25 (union stats) | 0.2888 | 0.4834 | 0.1387 | -0.0060 |
| (v') union + BM25 with corpus-wide stats | 0.3088 | 0.5159 | 0.1468 | +0.0139 |
| (vi-a) union + RRF(union BM25, per-mount minmax cos) | 0.2589 | 0.4433 | 0.1226 | -0.0359 |
| (vi-b) union + CC 0.5(union BM25 mm, per-mount mm cos) | 0.2928 | 0.4975 | 0.1391 | -0.0021 |
| (vi-c) union + CC 0.5 with corpus-wide BM25 stats | 0.2989 | 0.5083 | 0.1395 | +0.0040 |

## Mounts: C lexical-only — split: random (sizes [1249, 1222, 1162]) — per-mount limit m=50

Union recall ceiling at 3m=150: 0.2830. Union docs with zero BM25 overlap: 20934 (43.2% of union), of which relevant: 349.

| strategy | nDCG@10 | MRR@10 | Recall@10 | nDCG vs oracle |
|---|---|---|---|---|
| (i) naive score sort (Result.top) | 0.2079 | 0.4248 | 0.0850 | -0.0869 |
| (ii) round-robin interleave | 0.2718 | 0.4398 | 0.1369 | -0.0231 |
| (iii) RRF across mounts k=60 | 0.2579 | 0.3969 | 0.1360 | -0.0369 |
| (iv-a) min-max per mount, then sort | 0.2750 | 0.4412 | 0.1419 | -0.0199 |
| (iv-b) z-score per mount, then sort | 0.2892 | 0.4913 | 0.1380 | -0.0056 |
| (v) Clay: union + in-process BM25 (union stats) | 0.2957 | 0.4902 | 0.1437 | +0.0008 |
| (v') union + BM25 with corpus-wide stats | 0.3077 | 0.5158 | 0.1465 | +0.0129 |
| (vi-a) union + RRF(union BM25, per-mount minmax cos) | 0.2511 | 0.4396 | 0.1146 | -0.0438 |
| (vi-b) union + CC 0.5(union BM25 mm, per-mount mm cos) | 0.2970 | 0.4969 | 0.1405 | +0.0022 |
| (vi-c) union + CC 0.5 with corpus-wide BM25 stats | 0.3029 | 0.5086 | 0.1441 | +0.0080 |

## Mounts: C lexical-only — split: topic (k-means k=3 on potion-8M) (sizes [1206, 1253, 1174]) — per-mount limit m=10

Union recall ceiling at 3m=30: 0.1842. Union docs with zero BM25 overlap: 2915 (30.1% of union), of which relevant: 35.

| strategy | nDCG@10 | MRR@10 | Recall@10 | nDCG vs oracle |
|---|---|---|---|---|
| (i) naive score sort (Result.top) | 0.1915 | 0.3778 | 0.0783 | -0.1034 |
| (ii) round-robin interleave | 0.2426 | 0.3946 | 0.1321 | -0.0522 |
| (iii) RRF across mounts k=60 | 0.2293 | 0.3698 | 0.1309 | -0.0655 |
| (iv-a) min-max per mount, then sort | 0.2542 | 0.3953 | 0.1355 | -0.0406 |
| (iv-b) z-score per mount, then sort | 0.2649 | 0.4396 | 0.1363 | -0.0299 |
| (v) Clay: union + in-process BM25 (union stats) | 0.2845 | 0.4774 | 0.1363 | -0.0103 |
| (v') union + BM25 with corpus-wide stats | 0.3093 | 0.5220 | 0.1463 | +0.0145 |
| (vi-a) union + RRF(union BM25, per-mount minmax cos) | 0.2606 | 0.4378 | 0.1346 | -0.0343 |
| (vi-b) union + CC 0.5(union BM25 mm, per-mount mm cos) | 0.2759 | 0.4652 | 0.1375 | -0.0189 |
| (vi-c) union + CC 0.5 with corpus-wide BM25 stats | 0.2885 | 0.4947 | 0.1405 | -0.0064 |

## Mounts: C lexical-only — split: topic (k-means k=3 on potion-8M) (sizes [1206, 1253, 1174]) — per-mount limit m=20

Union recall ceiling at 3m=60: 0.2171. Union docs with zero BM25 overlap: 6822 (35.2% of union), of which relevant: 95.

| strategy | nDCG@10 | MRR@10 | Recall@10 | nDCG vs oracle |
|---|---|---|---|---|
| (i) naive score sort (Result.top) | 0.1915 | 0.3778 | 0.0783 | -0.1034 |
| (ii) round-robin interleave | 0.2426 | 0.3946 | 0.1321 | -0.0522 |
| (iii) RRF across mounts k=60 | 0.2293 | 0.3698 | 0.1309 | -0.0655 |
| (iv-a) min-max per mount, then sort | 0.2525 | 0.3944 | 0.1334 | -0.0423 |
| (iv-b) z-score per mount, then sort | 0.2690 | 0.4491 | 0.1375 | -0.0258 |
| (v) Clay: union + in-process BM25 (union stats) | 0.2890 | 0.4830 | 0.1398 | -0.0058 |
| (v') union + BM25 with corpus-wide stats | 0.3093 | 0.5162 | 0.1477 | +0.0144 |
| (vi-a) union + RRF(union BM25, per-mount minmax cos) | 0.2584 | 0.4387 | 0.1307 | -0.0364 |
| (vi-b) union + CC 0.5(union BM25 mm, per-mount mm cos) | 0.2837 | 0.4772 | 0.1381 | -0.0112 |
| (vi-c) union + CC 0.5 with corpus-wide BM25 stats | 0.2924 | 0.5017 | 0.1400 | -0.0024 |

## Mounts: C lexical-only — split: topic (k-means k=3 on potion-8M) (sizes [1206, 1253, 1174]) — per-mount limit m=50

Union recall ceiling at 3m=150: 0.2783. Union docs with zero BM25 overlap: 21769 (44.9% of union), of which relevant: 351.

| strategy | nDCG@10 | MRR@10 | Recall@10 | nDCG vs oracle |
|---|---|---|---|---|
| (i) naive score sort (Result.top) | 0.1915 | 0.3778 | 0.0783 | -0.1034 |
| (ii) round-robin interleave | 0.2426 | 0.3946 | 0.1321 | -0.0522 |
| (iii) RRF across mounts k=60 | 0.2293 | 0.3698 | 0.1309 | -0.0655 |
| (iv-a) min-max per mount, then sort | 0.2485 | 0.3932 | 0.1307 | -0.0464 |
| (iv-b) z-score per mount, then sort | 0.2715 | 0.4591 | 0.1386 | -0.0233 |
| (v) Clay: union + in-process BM25 (union stats) | 0.2959 | 0.4875 | 0.1433 | +0.0011 |
| (v') union + BM25 with corpus-wide stats | 0.3056 | 0.5147 | 0.1436 | +0.0108 |
| (vi-a) union + RRF(union BM25, per-mount minmax cos) | 0.2567 | 0.4325 | 0.1296 | -0.0382 |
| (vi-b) union + CC 0.5(union BM25 mm, per-mount mm cos) | 0.2934 | 0.4960 | 0.1429 | -0.0015 |
| (vi-c) union + CC 0.5 with corpus-wide BM25 stats | 0.2964 | 0.5048 | 0.1414 | +0.0015 |

