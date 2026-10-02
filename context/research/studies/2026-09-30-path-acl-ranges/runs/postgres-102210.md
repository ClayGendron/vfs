## postgres — 102,210 entry rows, 100,200 doc rows (10 tops x 200 folders x 50 files x 1 chunks), load 2s, median of 5 warm runs, ms

PostgreSQL 17.11 (Debian 17.11-1.pgdg12+2) on aarch64-unknown-linux-gnu, compiled by gcc (Debian 12.2.0-14+deb12u1) 12.2.0, 64-bit


### entries

| form | 10 spread | 100 spread | 500 spread | 100 adjacent |
|---|---|---|---|---|
| none | 8.2 | 9.0 | 9.0 | 8.5 |
| a_like | 1.9 | 16.3 | 195.8 | 11.6 |
| b_range | 2.0 | 6.2 | 34.3 | 2.8 |
| c_values | 1.8 | 4.3 | 15.2 | 1.6 |
| c_temp | 10.7 | 13.7 | 27.0 | 5.2 |
| d_or | 1.6 | 4.5 | 21.3 | 2.0 |
| d_values | 1.4 | 2.8 | 5.3 | 1.0 |
| c_unnest | 1.9 | 3.9 | 10.5 | 1.6 |
| d_unnest | 1.4 | 2.5 | 8.0 | 1.1 |

### corpus

| form | 10 spread | 100 spread | 500 spread | 100 adjacent |
|---|---|---|---|---|
| none | 18.9 | 18.9 | 19.4 | 30.0 |
| a_like | 1.5 | 16.0 | 185.4 | 29.4 |
| b_range | 1.3 | 8.0 | 31.8 | 15.4 |
| a_like_semi | 1.5 | 16.9 | 93.5 | 23.3 |
| b_range_semi | 1.2 | 7.7 | 35.7 | 21.4 |
| c_values | 1.2 | 7.2 | 29.3 | 15.4 |
| c_temp | 4.0 | 11.3 | 34.3 | 27.2 |
| d_or | 6.4 | 8.3 | 21.1 | 15.1 |
| d_values | 9.3 | 10.2 | 25.9 | 19.3 |
| e_or | 0.7 | 4.7 | 86.1 | 2.7 |
| e_values | 0.6 | 1.3 | 14.4 | 3.0 |
| c_unnest | 1.4 | 7.8 | 41.5 | 17.7 |
| d_unnest | 9.4 | 10.3 | 25.7 | 21.5 |
| e_unnest | 0.7 | 1.3 | 11.3 | 2.6 |
| g_sums | 0.001 | 0.009 | 0.068 | 0.004 |

### topk

| form | 10 spread | 100 spread | 500 spread | 100 adjacent |
|---|---|---|---|---|
| none | 34.3 | 33.4 | 35.0 | 33.3 |
| a_like | 4.1 | 26.4 | 202.6 | 24.9 |
| b_range | 4.2 | 16.6 | 45.2 | 16.2 |
| a_like_semi | 5.0 | 24.1 | 109.7 | 22.2 |
| b_range_semi | 7.0 | 17.0 | 44.9 | 16.6 |
| c_values | 3.3 | 16.1 | 36.7 | 16.0 |
| e_values | 1.8 | 3.9 | 16.2 | 3.4 |

### visible chunks — 50,100 candidate chunk ids (half the corpus), ms

| form | 10 spread | 100 spread | 500 spread | 100 adjacent |
|---|---|---|---|---|
| chunked IN join + app admit (today) | 177.4 | 119.3 | 126.8 | 128.2 |
| bisect over doc ranges, pure Python | 7.3 | 9.0 | 11.4 | 7.0 |


### maintenance — one statement each, rolled back, ms (entry table 102,210 rows)

| operation | rows touched | ms |
|---|---|---|
| rename a folder in place — path rewrite | 51 | 1.1 |
| rename a top folder in place — path rewrite | 10,221 | 89.4 |
| move a folder to the far end — dense preorder shift | 102,209 | 912.6 |
| move a folder next door — dense preorder shift | 102 | 3.5 |
| insert one row at the front — dense preorder shift | 102,209 | 1053.4 |

