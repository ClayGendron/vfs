# The order law on SciFact — spec 137's pre-landing check (2026-09-05)

Produced by `sim_order_law.py` (a copy of the two scratch runs that
produced these tables, merged into one script; seed and setup as
`sim_merge.py`). Oracle nDCG@10 0.6057 (single index, mount A's stack).

## The study's heterogeneous mounts A/B/C (C is a deliberately bad local ranker)

### random m=10
| strategy | nDCG@10 | MRR@10 | R@10 |
|---|---|---|---|
| (v) union BM25, union stats | 0.6390 | 0.6059 | 0.7649 |
| (v') union BM25, corpus-wide stats | 0.6684 | 0.6351 | 0.7888 |
| (v'-iso) + per-mount isotonic (PAVA) | 0.6200 | 0.5806 | 0.7713 |
| (v'-sfx) + per-mount suffix-max | 0.6067 | 0.5598 | 0.7773 |
| (v'-heads) k-way merge on head scores | 0.5961 | 0.5633 | 0.7288 |
| (v-iso) union stats + isotonic | 0.6136 | 0.5724 | 0.7699 |

### random m=20
| strategy | nDCG@10 | MRR@10 | R@10 |
|---|---|---|---|
| (v) union BM25, union stats | 0.6404 | 0.6084 | 0.7633 |
| (v') union BM25, corpus-wide stats | 0.6657 | 0.6322 | 0.7873 |
| (v'-iso) + per-mount isotonic (PAVA) | 0.6200 | 0.5806 | 0.7713 |
| (v'-sfx) + per-mount suffix-max | 0.6067 | 0.5629 | 0.7707 |
| (v'-heads) k-way merge on head scores | 0.5961 | 0.5633 | 0.7288 |
| (v-iso) union stats + isotonic | 0.6162 | 0.5723 | 0.7782 |

### random m=50
| strategy | nDCG@10 | MRR@10 | R@10 |
|---|---|---|---|
| (v) union BM25, union stats | 0.6527 | 0.6221 | 0.7689 |
| (v') union BM25, corpus-wide stats | 0.6625 | 0.6310 | 0.7799 |
| (v'-iso) + per-mount isotonic (PAVA) | 0.6200 | 0.5806 | 0.7713 |
| (v'-sfx) + per-mount suffix-max | 0.6056 | 0.5624 | 0.7674 |
| (v'-heads) k-way merge on head scores | 0.5961 | 0.5633 | 0.7288 |
| (v-iso) union stats + isotonic | 0.6178 | 0.5780 | 0.7738 |

### topic m=10
| strategy | nDCG@10 | MRR@10 | R@10 |
|---|---|---|---|
| (v) union BM25, union stats | 0.6372 | 0.6087 | 0.7499 |
| (v') union BM25, corpus-wide stats | 0.6537 | 0.6262 | 0.7614 |
| (v'-iso) + per-mount isotonic (PAVA) | 0.5943 | 0.5484 | 0.7558 |
| (v'-sfx) + per-mount suffix-max | 0.5937 | 0.5439 | 0.7641 |
| (v'-heads) k-way merge on head scores | 0.5622 | 0.5284 | 0.6848 |
| (v-iso) union stats + isotonic | 0.5916 | 0.5450 | 0.7558 |

### topic m=20
| strategy | nDCG@10 | MRR@10 | R@10 |
|---|---|---|---|
| (v) union BM25, union stats | 0.6515 | 0.6205 | 0.7670 |
| (v') union BM25, corpus-wide stats | 0.6607 | 0.6289 | 0.7781 |
| (v'-iso) + per-mount isotonic (PAVA) | 0.5944 | 0.5484 | 0.7558 |
| (v'-sfx) + per-mount suffix-max | 0.5918 | 0.5432 | 0.7574 |
| (v'-heads) k-way merge on head scores | 0.5622 | 0.5284 | 0.6848 |
| (v-iso) union stats + isotonic | 0.6005 | 0.5546 | 0.7624 |

### topic m=50
| strategy | nDCG@10 | MRR@10 | R@10 |
|---|---|---|---|
| (v) union BM25, union stats | 0.6635 | 0.6333 | 0.7807 |
| (v') union BM25, corpus-wide stats | 0.6627 | 0.6312 | 0.7799 |
| (v'-iso) + per-mount isotonic (PAVA) | 0.5944 | 0.5484 | 0.7558 |
| (v'-sfx) + per-mount suffix-max | 0.5920 | 0.5419 | 0.7597 |
| (v'-heads) k-way merge on head scores | 0.5622 | 0.5284 | 0.6848 |
| (v-iso) union stats + isotonic | 0.5949 | 0.5503 | 0.7524 |


Prefix violations under isotonic: 0 (every mount's surviving rows are a prefix of its list).

## vfs-shaped mounts — one BM25 and one fusion law everywhere

### uniform: potion-8M / bm25(1.2,.75) / cc-minmax a=0.5 on all three — random m=10
| strategy | nDCG@10 | MRR@10 | R@10 |
|---|---|---|---|
| (v') union BM25, corpus-wide stats | 0.6672 | 0.6322 | 0.7921 |
| (v'-iso) + per-mount isotonic (PAVA) | 0.6688 | 0.6310 | 0.8048 |
| (v'-heads) k-way merge on head scores | 0.6657 | 0.6302 | 0.7956 |
| (i) naive score sort (same law everywhere) | 0.6050 | 0.5553 | 0.7851 |

### uniform: potion-8M / bm25(1.2,.75) / cc-minmax a=0.5 on all three — random m=30
| strategy | nDCG@10 | MRR@10 | R@10 |
|---|---|---|---|
| (v') union BM25, corpus-wide stats | 0.6632 | 0.6311 | 0.7816 |
| (v'-iso) + per-mount isotonic (PAVA) | 0.6688 | 0.6310 | 0.8048 |
| (v'-heads) k-way merge on head scores | 0.6657 | 0.6302 | 0.7956 |
| (i) naive score sort (same law everywhere) | 0.6050 | 0.5553 | 0.7851 |

### uniform: potion-8M / bm25(1.2,.75) / cc-minmax a=0.5 on all three — topic m=10
| strategy | nDCG@10 | MRR@10 | R@10 |
|---|---|---|---|
| (v') union BM25, corpus-wide stats | 0.6676 | 0.6322 | 0.7949 |
| (v'-iso) + per-mount isotonic (PAVA) | 0.6582 | 0.6191 | 0.7932 |
| (v'-heads) k-way merge on head scores | 0.6537 | 0.6148 | 0.7917 |
| (i) naive score sort (same law everywhere) | 0.5646 | 0.5205 | 0.7208 |

### uniform: potion-8M / bm25(1.2,.75) / cc-minmax a=0.5 on all three — topic m=30
| strategy | nDCG@10 | MRR@10 | R@10 |
|---|---|---|---|
| (v') union BM25, corpus-wide stats | 0.6634 | 0.6312 | 0.7813 |
| (v'-iso) + per-mount isotonic (PAVA) | 0.6592 | 0.6194 | 0.7966 |
| (v'-heads) k-way merge on head scores | 0.6537 | 0.6148 | 0.7917 |
| (i) naive score sort (same law everywhere) | 0.5646 | 0.5205 | 0.7208 |

### same law, embedders differ: potion-8M / potion-4M / hash-256 — random m=10
| strategy | nDCG@10 | MRR@10 | R@10 |
|---|---|---|---|
| (v') union BM25, corpus-wide stats | 0.6647 | 0.6312 | 0.7848 |
| (v'-iso) + per-mount isotonic (PAVA) | 0.6625 | 0.6278 | 0.7906 |
| (v'-heads) k-way merge on head scores | 0.6616 | 0.6276 | 0.7881 |
| (i) naive score sort (same law everywhere) | 0.5726 | 0.5173 | 0.7689 |

### same law, embedders differ: potion-8M / potion-4M / hash-256 — random m=30
| strategy | nDCG@10 | MRR@10 | R@10 |
|---|---|---|---|
| (v') union BM25, corpus-wide stats | 0.6615 | 0.6300 | 0.7783 |
| (v'-iso) + per-mount isotonic (PAVA) | 0.6625 | 0.6278 | 0.7906 |
| (v'-heads) k-way merge on head scores | 0.6616 | 0.6276 | 0.7881 |
| (i) naive score sort (same law everywhere) | 0.5726 | 0.5173 | 0.7689 |

### same law, embedders differ: potion-8M / potion-4M / hash-256 — topic m=10
| strategy | nDCG@10 | MRR@10 | R@10 |
|---|---|---|---|
| (v') union BM25, corpus-wide stats | 0.6567 | 0.6284 | 0.7639 |
| (v'-iso) + per-mount isotonic (PAVA) | 0.6349 | 0.5991 | 0.7606 |
| (v'-heads) k-way merge on head scores | 0.6271 | 0.5933 | 0.7483 |
| (i) naive score sort (same law everywhere) | 0.4975 | 0.4515 | 0.6633 |

### same law, embedders differ: potion-8M / potion-4M / hash-256 — topic m=30
| strategy | nDCG@10 | MRR@10 | R@10 |
|---|---|---|---|
| (v') union BM25, corpus-wide stats | 0.6597 | 0.6295 | 0.7716 |
| (v'-iso) + per-mount isotonic (PAVA) | 0.6368 | 0.5997 | 0.7673 |
| (v'-heads) k-way merge on head scores | 0.6271 | 0.5933 | 0.7483 |
| (i) naive score sort (same law everywhere) | 0.4975 | 0.4515 | 0.6633 |

### same law, lexical-only mounts (no embedder) — random m=10
| strategy | nDCG@10 | MRR@10 | R@10 |
|---|---|---|---|
| (v') union BM25, corpus-wide stats | 0.6625 | 0.6310 | 0.7799 |
| (v'-iso) + per-mount isotonic (PAVA) | 0.6612 | 0.6292 | 0.7799 |
| (v'-heads) k-way merge on head scores | 0.6622 | 0.6295 | 0.7833 |
| (i) naive score sort (same law everywhere) | 0.6591 | 0.6266 | 0.7774 |

### same law, lexical-only mounts (no embedder) — random m=30
| strategy | nDCG@10 | MRR@10 | R@10 |
|---|---|---|---|
| (v') union BM25, corpus-wide stats | 0.6625 | 0.6310 | 0.7799 |
| (v'-iso) + per-mount isotonic (PAVA) | 0.6612 | 0.6292 | 0.7799 |
| (v'-heads) k-way merge on head scores | 0.6622 | 0.6295 | 0.7833 |
| (i) naive score sort (same law everywhere) | 0.6591 | 0.6266 | 0.7774 |

### same law, lexical-only mounts (no embedder) — topic m=10
| strategy | nDCG@10 | MRR@10 | R@10 |
|---|---|---|---|
| (v') union BM25, corpus-wide stats | 0.6636 | 0.6311 | 0.7824 |
| (v'-iso) + per-mount isotonic (PAVA) | 0.6583 | 0.6226 | 0.7841 |
| (v'-heads) k-way merge on head scores | 0.6581 | 0.6225 | 0.7841 |
| (i) naive score sort (same law everywhere) | 0.6438 | 0.6064 | 0.7774 |

### same law, lexical-only mounts (no embedder) — topic m=30
| strategy | nDCG@10 | MRR@10 | R@10 |
|---|---|---|---|
| (v') union BM25, corpus-wide stats | 0.6625 | 0.6310 | 0.7799 |
| (v'-iso) + per-mount isotonic (PAVA) | 0.6583 | 0.6226 | 0.7841 |
| (v'-heads) k-way merge on head scores | 0.6581 | 0.6225 | 0.7841 |
| (i) naive score sort (same law everywhere) | 0.6438 | 0.6064 | 0.7774 |

