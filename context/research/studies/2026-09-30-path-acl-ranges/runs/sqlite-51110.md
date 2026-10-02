## sqlite — 51,110 entry rows, 50,100 doc rows (10 tops x 100 folders x 50 files x 1 chunks), load 0s, median of 5 warm runs, ms

3.50.4


### entries

| form | 10 spread | 100 spread | 500 spread | 100 adjacent |
|---|---|---|---|---|
| none | 0.3 | 0.3 | 0.3 | 0.3 |
| a_like | 0.1 | 1.9 | 12.8 | 1.9 |
| b_range | 0.1 | 1.3 | 10.1 | 1.3 |
| c_values | 0.1 | 0.9 | 4.4 | 0.9 |
| c_temp | 0.1 | 0.7 | 3.7 | 0.7 |
| d_or | 0.1 | 1.3 | 9.6 | 1.2 |
| d_values | 0.0 | 0.1 | 0.5 | 0.1 |

### corpus

| form | 10 spread | 100 spread | 500 spread | 100 adjacent |
|---|---|---|---|---|
| none | 18.3 | 19.0 | 18.2 | 19.7 |
| a_like | 0.6 | 221.4 | 854.2 | 216.3 |
| b_range | 0.5 | 212.3 | 828.4 | 245.9 |
| a_like_semi | 0.5 | 6.3 | 36.7 | 6.2 |
| b_range_semi | 0.4 | 5.6 | 40.6 | 5.5 |
| c_values | 0.4 | 4.3 | 21.5 | 4.2 |
| c_temp | 0.4 | 4.1 | 20.7 | 4.0 |
| d_or | 0.4 | 53.5 | 158.1 | 53.7 |
| d_values | 0.3 | 3.5 | 17.6 | 3.3 |
| e_or | 0.1 | 0.8 | 4.1 | 0.7 |
| e_values | 0.0 | 0.2 | 1.2 | 0.2 |
| g_sums | 0.001 | 0.009 | 0.046 | 0.001 |

### topk

| form | 10 spread | 100 spread | 500 spread | 100 adjacent |
|---|---|---|---|---|
| none | 19.9 | 19.8 | 19.9 | 19.9 |
| a_like | 0.6 | 220.7 | 797.8 | 216.0 |
| b_range | 0.6 | 212.4 | 850.7 | 241.5 |
| a_like_semi | 0.5 | 6.3 | 37.5 | 6.4 |
| b_range_semi | 0.5 | 5.7 | 34.3 | 5.7 |
| c_values | 0.4 | 4.3 | 22.2 | 4.3 |
| e_values | 0.1 | 0.4 | 2.1 | 0.4 |

### visible chunks — 25,050 candidate chunk ids (half the corpus), ms

| form | 10 spread | 100 spread | 500 spread | 100 adjacent |
|---|---|---|---|---|
| chunked IN join + app admit (today) | 31.4 | 32.4 | 33.7 | 30.9 |
| bisect over doc ranges, pure Python | 4.0 | 4.4 | 6.9 | 2.6 |


### maintenance — one statement each, rolled back, ms (entry table 51,110 rows)

| operation | rows touched | ms |
|---|---|---|
| rename a folder in place — path rewrite | 51 | 0.7 |
| rename a top folder in place — path rewrite | 5,111 | 16.5 |
| move a folder to the far end — dense preorder shift | 51,109 | 70.0 |
| move a folder next door — dense preorder shift | 102 | 1.0 |
| insert one row at the front — dense preorder shift | 51,109 | 60.9 |

