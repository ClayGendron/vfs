# The three channels on SciFact (vfs tokenizer and formula)

Adversary: reads every visible row, plants 4 + 64 anchor documents (channel a) and a 128-document ladder (channel c), then asks one query per vocabulary term (400 terms, stratified by visible df). Truth: the term occurs in at least one hidden row. `df_h` is the hidden document frequency; the estimate is the adversary's. Channel c is handed the true N and avg_dl.

### random h=10%: visible 4665, hidden 518, planted 196

- channel a corpus solve from two anchor queries (68 rows): N_est=5378 (true 5379, hidden-size estimate 517 vs true 518); avg_dl_est=1058.548 (true 1058.748); 0.0s
- channel b: export gives N exactly (5379); hidden vocabulary not visible anywhere: 1870 terms (16% of the hidden set's vocabulary), each revealed by naming it in a query (k terms per query -> k dfs of ~12.4 bits each)
- channel c: mean df interval width from the 128-rung ladder 11.58 docs

**a-planted**

| band | n | base rate | precision | recall | accuracy | df_h exact | df_h MAE |
|---|---|---|---|---|---|---|---|
| all |  400 | 0.50 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 1-1 |  100 | 0.05 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 2-5 |  100 | 0.27 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 6-30 |  100 | 0.67 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 31+ |  100 | 1.00 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |

**a-oracle**

| band | n | base rate | precision | recall | accuracy | df_h exact | df_h MAE |
|---|---|---|---|---|---|---|---|
| all |  400 | 0.50 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 1-1 |  100 | 0.05 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 2-5 |  100 | 0.27 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 6-30 |  100 | 0.67 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 31+ |  100 | 1.00 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |

**b-stats**

| band | n | base rate | precision | recall | accuracy | df_h exact | df_h MAE |
|---|---|---|---|---|---|---|---|
| all |  400 | 0.50 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 1-1 |  100 | 0.05 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 2-5 |  100 | 0.27 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 6-30 |  100 | 0.67 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 31+ |  100 | 1.00 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |

**c-ranks**

| band | n | base rate | precision | recall | accuracy | df_h exact | df_h MAE |
|---|---|---|---|---|---|---|---|
| all |  400 | 0.50 | 1.000 | 1.000 | 1.000 | 0.995 | 5.20 |
| df_v 1-1 |  100 | 0.05 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 2-5 |  100 | 0.27 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 6-30 |  100 | 0.67 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 31+ |  100 | 1.00 | 1.000 | 1.000 | 1.000 | 0.980 | 20.79 |

_(6s)_

### random h=50%: visible 2591, hidden 2592, planted 196

- channel a corpus solve from two anchor queries (68 rows): N_est=5377 (true 5379, hidden-size estimate 2590 vs true 2592); avg_dl_est=1041.557 (true 1041.781); 0.0s
- channel b: export gives N exactly (5379); hidden vocabulary not visible anywhere: 10782 terms (41% of the hidden set's vocabulary), each revealed by naming it in a query (k terms per query -> k dfs of ~12.4 bits each)
- channel c: mean df interval width from the 128-rung ladder 46.11 docs

**a-planted**

| band | n | base rate | precision | recall | accuracy | df_h exact | df_h MAE |
|---|---|---|---|---|---|---|---|
| all |  400 | 0.80 | 1.000 | 1.000 | 1.000 | 0.993 | 0.01 |
| df_v 1-1 |  100 | 0.41 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 2-5 |  100 | 0.80 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 6-30 |  100 | 1.00 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 31+ |  100 | 1.00 | 1.000 | 1.000 | 1.000 | 0.970 | 0.03 |

**a-oracle**

| band | n | base rate | precision | recall | accuracy | df_h exact | df_h MAE |
|---|---|---|---|---|---|---|---|
| all |  400 | 0.80 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 1-1 |  100 | 0.41 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 2-5 |  100 | 0.80 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 6-30 |  100 | 1.00 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 31+ |  100 | 1.00 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |

**b-stats**

| band | n | base rate | precision | recall | accuracy | df_h exact | df_h MAE |
|---|---|---|---|---|---|---|---|
| all |  400 | 0.80 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 1-1 |  100 | 0.41 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 2-5 |  100 | 0.80 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 6-30 |  100 | 1.00 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 31+ |  100 | 1.00 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |

**c-ranks**

| band | n | base rate | precision | recall | accuracy | df_h exact | df_h MAE |
|---|---|---|---|---|---|---|---|
| all |  400 | 0.80 | 1.000 | 1.000 | 1.000 | 0.988 | 11.45 |
| df_v 1-1 |  100 | 0.41 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 2-5 |  100 | 0.80 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 6-30 |  100 | 1.00 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 31+ |  100 | 1.00 | 1.000 | 1.000 | 1.000 | 0.950 | 45.80 |

_(6s)_

### random h=90%: visible 518, hidden 4665, planted 196

- channel a corpus solve from two anchor queries (68 rows): N_est=5379 (true 5379, hidden-size estimate 4665 vs true 4665); avg_dl_est=1053.887 (true 1053.884); 0.0s
- channel b: export gives N exactly (5379); hidden vocabulary not visible anywhere: 25071 terms (72% of the hidden set's vocabulary), each revealed by naming it in a query (k terms per query -> k dfs of ~12.4 bits each)
- channel c: mean df interval width from the 128-rung ladder 374.01 docs

**a-planted**

| band | n | base rate | precision | recall | accuracy | df_h exact | df_h MAE |
|---|---|---|---|---|---|---|---|
| all |  400 | 0.93 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 1-1 |  100 | 0.74 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 2-5 |  100 | 0.99 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 6-30 |  100 | 1.00 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 31+ |  100 | 1.00 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |

**a-oracle**

| band | n | base rate | precision | recall | accuracy | df_h exact | df_h MAE |
|---|---|---|---|---|---|---|---|
| all |  400 | 0.93 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 1-1 |  100 | 0.74 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 2-5 |  100 | 0.99 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 6-30 |  100 | 1.00 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 31+ |  100 | 1.00 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |

**b-stats**

| band | n | base rate | precision | recall | accuracy | df_h exact | df_h MAE |
|---|---|---|---|---|---|---|---|
| all |  400 | 0.93 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 1-1 |  100 | 0.74 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 2-5 |  100 | 0.99 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 6-30 |  100 | 1.00 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 31+ |  100 | 1.00 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |

**c-ranks**

| band | n | base rate | precision | recall | accuracy | df_h exact | df_h MAE |
|---|---|---|---|---|---|---|---|
| all |  400 | 0.93 | 1.000 | 1.000 | 1.000 | 0.777 | 144.24 |
| df_v 1-1 |  100 | 0.74 | 1.000 | 1.000 | 1.000 | 0.950 | 0.05 |
| df_v 2-5 |  100 | 0.99 | 1.000 | 1.000 | 1.000 | 0.900 | 0.10 |
| df_v 6-30 |  100 | 1.00 | 1.000 | 1.000 | 1.000 | 0.870 | 0.13 |
| df_v 31+ |  100 | 1.00 | 1.000 | 1.000 | 1.000 | 0.390 | 576.68 |

_(6s)_

### topical h=10%: visible 4665, hidden 518, planted 196

- channel a corpus solve from two anchor queries (68 rows): N_est=5380 (true 5379, hidden-size estimate 519 vs true 518); avg_dl_est=951.700 (true 951.610); 0.0s
- channel b: export gives N exactly (5379); hidden vocabulary not visible anywhere: 1721 terms (19% of the hidden set's vocabulary), each revealed by naming it in a query (k terms per query -> k dfs of ~12.4 bits each)
- channel c: mean df interval width from the 128-rung ladder 33.21 docs

**a-planted**

| band | n | base rate | precision | recall | accuracy | df_h exact | df_h MAE |
|---|---|---|---|---|---|---|---|
| all |  400 | 0.35 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 1-1 |  100 | 0.04 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 2-5 |  100 | 0.13 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 6-30 |  100 | 0.39 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 31+ |  100 | 0.83 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |

**a-oracle**

| band | n | base rate | precision | recall | accuracy | df_h exact | df_h MAE |
|---|---|---|---|---|---|---|---|
| all |  400 | 0.35 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 1-1 |  100 | 0.04 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 2-5 |  100 | 0.13 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 6-30 |  100 | 0.39 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 31+ |  100 | 0.83 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |

**b-stats**

| band | n | base rate | precision | recall | accuracy | df_h exact | df_h MAE |
|---|---|---|---|---|---|---|---|
| all |  400 | 0.35 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 1-1 |  100 | 0.04 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 2-5 |  100 | 0.13 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 6-30 |  100 | 0.39 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 31+ |  100 | 0.83 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |

**c-ranks**

| band | n | base rate | precision | recall | accuracy | df_h exact | df_h MAE |
|---|---|---|---|---|---|---|---|
| all |  400 | 0.35 | 1.000 | 0.986 | 0.995 | 0.993 | 4.24 |
| df_v 1-1 |  100 | 0.04 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 2-5 |  100 | 0.13 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 6-30 |  100 | 0.39 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 31+ |  100 | 0.83 | 1.000 | 0.976 | 0.980 | 0.970 | 16.97 |

_(6s)_

### topical h=50%: visible 2591, hidden 2592, planted 196

- channel a corpus solve from two anchor queries (68 rows): N_est=5378 (true 5379, hidden-size estimate 2591 vs true 2592); avg_dl_est=1065.839 (true 1066.027); 0.0s
- channel b: export gives N exactly (5379); hidden vocabulary not visible anywhere: 11927 terms (47% of the hidden set's vocabulary), each revealed by naming it in a query (k terms per query -> k dfs of ~12.4 bits each)
- channel c: mean df interval width from the 128-rung ladder 23.29 docs

**a-planted**

| band | n | base rate | precision | recall | accuracy | df_h exact | df_h MAE |
|---|---|---|---|---|---|---|---|
| all |  400 | 0.73 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 1-1 |  100 | 0.30 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 2-5 |  100 | 0.69 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 6-30 |  100 | 0.92 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 31+ |  100 | 1.00 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |

**a-oracle**

| band | n | base rate | precision | recall | accuracy | df_h exact | df_h MAE |
|---|---|---|---|---|---|---|---|
| all |  400 | 0.73 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 1-1 |  100 | 0.30 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 2-5 |  100 | 0.69 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 6-30 |  100 | 0.92 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 31+ |  100 | 1.00 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |

**b-stats**

| band | n | base rate | precision | recall | accuracy | df_h exact | df_h MAE |
|---|---|---|---|---|---|---|---|
| all |  400 | 0.73 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 1-1 |  100 | 0.30 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 2-5 |  100 | 0.69 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 6-30 |  100 | 0.92 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 31+ |  100 | 1.00 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |

**c-ranks**

| band | n | base rate | precision | recall | accuracy | df_h exact | df_h MAE |
|---|---|---|---|---|---|---|---|
| all |  400 | 0.73 | 1.000 | 1.000 | 1.000 | 0.988 | 11.33 |
| df_v 1-1 |  100 | 0.30 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 2-5 |  100 | 0.69 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 6-30 |  100 | 0.92 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 31+ |  100 | 1.00 | 1.000 | 1.000 | 1.000 | 0.950 | 45.31 |

_(6s)_

### topical h=90%: visible 518, hidden 4665, planted 196

- channel a corpus solve from two anchor queries (68 rows): N_est=5380 (true 5379, hidden-size estimate 4666 vs true 4665); avg_dl_est=1291.720 (true 1291.546); 0.0s
- channel b: export gives N exactly (5379); hidden vocabulary not visible anywhere: 27164 terms (78% of the hidden set's vocabulary), each revealed by naming it in a query (k terms per query -> k dfs of ~12.4 bits each)
- channel c: mean df interval width from the 128-rung ladder 171.35 docs

**a-planted**

| band | n | base rate | precision | recall | accuracy | df_h exact | df_h MAE |
|---|---|---|---|---|---|---|---|
| all |  400 | 0.87 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 1-1 |  100 | 0.57 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 2-5 |  100 | 0.92 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 6-30 |  100 | 1.00 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 31+ |  100 | 1.00 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |

**a-oracle**

| band | n | base rate | precision | recall | accuracy | df_h exact | df_h MAE |
|---|---|---|---|---|---|---|---|
| all |  400 | 0.87 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 1-1 |  100 | 0.57 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 2-5 |  100 | 0.92 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 6-30 |  100 | 1.00 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 31+ |  100 | 1.00 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |

**b-stats**

| band | n | base rate | precision | recall | accuracy | df_h exact | df_h MAE |
|---|---|---|---|---|---|---|---|
| all |  400 | 0.87 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 1-1 |  100 | 0.57 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 2-5 |  100 | 0.92 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 6-30 |  100 | 1.00 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |
| df_v 31+ |  100 | 1.00 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 |

**c-ranks**

| band | n | base rate | precision | recall | accuracy | df_h exact | df_h MAE |
|---|---|---|---|---|---|---|---|
| all |  400 | 0.87 | 1.000 | 1.000 | 1.000 | 0.860 | 64.57 |
| df_v 1-1 |  100 | 0.57 | 1.000 | 1.000 | 1.000 | 0.900 | 0.20 |
| df_v 2-5 |  100 | 0.92 | 1.000 | 1.000 | 1.000 | 0.870 | 0.15 |
| df_v 6-30 |  100 | 1.00 | 1.000 | 1.000 | 1.000 | 0.910 | 13.34 |
| df_v 31+ |  100 | 1.00 | 1.000 | 1.000 | 1.000 | 0.760 | 244.59 |

_(6s)_


# Mitigations on SciFact (vfs tokenizer and formula)

## 1. nDCG@10 on the visible qrels, per statistics policy

All rows visible, global statistics: **0.6627**

| split | h | visible | queries | global | visible | bucket2 | snapshot |
|---|---|---|---|---|---|---|---|
| random | 10% | 4665 | 268 | 0.6647 | 0.6628 | 0.6630 | 0.6683 |
| random | 50% | 2591 | 150 | 0.6850 | 0.6775 | 0.6802 | 0.6802 |
| random | 90% | 518 | 37 | 0.8338 | 0.8402 | 0.8430 | 0.8362 |
| topical | 10% | 4665 | 246 | 0.6521 | 0.6509 | 0.6506 | 0.6550 |
| topical | 50% | 2591 | 155 | 0.6936 | 0.7007 | 0.6922 | 0.6943 |
| topical | 90% | 518 | 29 | 0.6984 | 0.7136 | 0.7008 | 0.7111 |

_(18s)_

## 2. Multiplayer: statistics over the subject set's intersection

Each principal sees a random 70% of the corpus (or a topical 70% for the topical row); the session sees the intersection.

| principals | mix | intersection | queries | global stats | intersection stats | each principal's own stats (mean) |
|---|---|---|---|---|---|---|
| 1 | random | 3628 (70%) | 216 | 0.7047 | 0.7017 | 0.7017 |
| 2 | random | 2529 (49%) | 152 | 0.7124 | 0.7114 | 0.7100 |
| 3 | random | 1771 (34%) | 123 | 0.7287 | 0.7333 | 0.7315 |
| 5 | random | 860 (17%) | 62 | 0.8083 | 0.7909 | 0.8075 |
| 2 | topical+random | 2541 (49%) | 144 | 0.6831 | 0.6839 | 0.6848 |
| 3 | topical+random | 1784 (34%) | 113 | 0.6876 | 0.6883 | 0.6910 |

_(11s)_

## 3. The cross-mount merge: per-mount export vs the union fallback

Two mounts (random halves), the caller sees a random 50% of each. Each mount ranks its visible rows to depth 30 with its own policy; the router re-scores the union with the summed exports (or the union's own texts) and applies the order law.

One index over the caller's visible rows, visible stats: 0.6962; global stats: 0.6890

| mount-local stats | export summed by the router | nDCG@10 | leaks hidden df? |
|---|---|---|---|
| global | global | 0.6885 | yes: df over hidden rows |
| global | visible | 0.6929 | yes: df over hidden rows |
| global | union | 0.6917 | yes: df over hidden rows |
| visible | visible | 0.6960 | no |
| visible | union | 0.6950 | no |

_(6s)_

## 4. Residual leak: the score-channel adversary against each policy

Random and topical h=50%. The adversary plants the anchors, is handed the policy's N and avg_dl (the most it could learn), recovers each term's *policy* df from one two-term query, and predicts "present in hidden rows" by the rule that is certain under that policy: recovered df above the visible df (global, snapshot), or a different bucket (bucket2).

| split | policy | recovered = policy df exactly | base rate | precision | recall | accuracy |
|---|---|---|---|---|---|---|
| random | global | 1.000 | 0.80 | 1.000 | 1.000 | 1.000 |
| random | visible | 1.000 | 0.80 | nan | 0.000 | 0.198 |
| random | bucket2 | 1.000 | 0.80 | 1.000 | 0.910 | 0.927 |
| random | snapshot | 1.000 | 0.80 | 1.000 | 0.424 | 0.537 |
| topical | global | 1.000 | 0.70 | 1.000 | 1.000 | 1.000 |
| topical | visible | 1.000 | 0.70 | nan | 0.000 | 0.302 |
| topical | bucket2 | 1.000 | 0.70 | 1.000 | 0.731 | 0.812 |
| topical | snapshot | 1.000 | 0.70 | 1.000 | 0.441 | 0.610 |

_(23s)_

## 5. Cost model: visible-set df per query

Corpus: N = 5183, vocabulary 36764, mean dl 219 tokens, total postings 620499.

| per SciFact query | mean | median | p95 | max |
|---|---|---|---|---|
| distinct indexed terms k | 12.0 | 11 | 21 | 26 |
| posting rows under the query's terms (sum of global df) | 14028 | 13619 | 27575 | 33453 |
| same, as a share of N | 2.71 | 2.63 | 5.32 | 6.45 |

Terms in more than 20% of documents: 52 (of, the, and, in, to, that, for, with, ...). They carry most of the rows and almost none of the score.


