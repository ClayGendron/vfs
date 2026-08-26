## Single legs

| leg | nDCG@10 | MRR@10 | Recall@10 |
|---|---|---|---|
| BM25 only | 0.6625 | 0.6310 | 0.7799 |
| potion-8M cosine only | 0.5064 | 0.4666 | 0.6618 |

## RRF: sensitivity to k (equal weights)

| k | nDCG@10 | MRR@10 | Recall@10 |
|---|---|---|---|
| 0 | 0.6591 | 0.6102 | 0.8279 |
| 1 | 0.6596 | 0.6106 | 0.8252 |
| 5 | 0.6501 | 0.5989 | 0.8202 |
| 10 | 0.6391 | 0.5864 | 0.8189 |
| 30 | 0.6187 | 0.5695 | 0.7894 |
| 60 | 0.6057 | 0.5624 | 0.7561 |
| 100 | 0.6038 | 0.5612 | 0.7528 |
| 300 | 0.6013 | 0.5594 | 0.7478 |
| 1000 | 0.6012 | 0.5593 | 0.7478 |

## Weighted RRF k=60: weight on the vector list

| w_vec (w_lex=1) | nDCG@10 | MRR@10 | Recall@10 |
|---|---|---|---|
| 0.25 | 0.6469 | 0.6055 | 0.7932 |
| 0.5 | 0.6289 | 0.5856 | 0.7832 |
| 1.0 | 0.6057 | 0.5624 | 0.7561 |
| 1.5 | 0.5839 | 0.5386 | 0.7419 |
| 2.0 | 0.5758 | 0.5299 | 0.7378 |
| 3.0 | 0.5633 | 0.5184 | 0.7231 |

## Convex combination: alpha (weight on vector) x normalization

| alpha | min-max nDCG@10 | z-score nDCG@10 | min-max R@10 | z-score R@10 |
|---|---|---|---|---|
| 0.0 | 0.6625 | 0.6625 | 0.7799 | 0.7799 |
| 0.1 | 0.6715 | 0.6725 | 0.7914 | 0.7948 |
| 0.2 | 0.6744 | 0.6797 | 0.8031 | 0.8064 |
| 0.3 | 0.6747 | 0.6726 | 0.8109 | 0.8042 |
| 0.4 | 0.6667 | 0.6660 | 0.8009 | 0.7998 |
| 0.5 | 0.6620 | 0.6604 | 0.8031 | 0.8013 |
| 0.6 | 0.6496 | 0.6505 | 0.7913 | 0.7939 |
| 0.7 | 0.6246 | 0.6330 | 0.7679 | 0.7679 |
| 0.8 | 0.6027 | 0.6102 | 0.7506 | 0.7533 |
| 0.9 | 0.5603 | 0.5697 | 0.7034 | 0.7118 |
| 1.0 | 0.5064 | 0.5064 | 0.6618 | 0.6618 |

## Static prior injection (base: CC alpha=0.5 min-max, and RRF k=60)

| prior | mode | nDCG@10 | MRR@10 | Recall@10 |
|---|---|---|---|---|
| none | CC base | 0.6620 | 0.6205 | 0.8031 |
| none | RRF base | 0.6057 | 0.5624 | 0.7561 |
| noise (uniform random) | extra RRF list (k=60, equal weight) | 0.4603 | 0.3817 | 0.7293 |
| noise (uniform random) | multiplicative x(1+0.5p) | 0.6155 | 0.5822 | 0.7535 |
| noise (uniform random) | multiplicative x(1+2p) | 0.4842 | 0.4508 | 0.6280 |
| noise (uniform random) | additive +0.1p | 0.6561 | 0.6182 | 0.7998 |
| noise (uniform random) | additive +0.3p | 0.6124 | 0.5832 | 0.7377 |
| signal (0.5*any-relevant + 0.5*noise) | extra RRF list (k=60, equal weight) | 0.7710 | 0.7468 | 0.8679 |
| signal (0.5*any-relevant + 0.5*noise) | multiplicative x(1+0.5p) | 0.7730 | 0.7480 | 0.8696 |
| signal (0.5*any-relevant + 0.5*noise) | multiplicative x(1+2p) | 0.8245 | 0.7994 | 0.9186 |
| signal (0.5*any-relevant + 0.5*noise) | additive +0.1p | 0.7023 | 0.6641 | 0.8389 |
| signal (0.5*any-relevant + 0.5*noise) | additive +0.3p | 0.7736 | 0.7438 | 0.8862 |
