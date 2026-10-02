## postgres — 994,923 entry rows, median of 5 warm runs

- literal_like: grep 31.9 ms (16066 rows), join-back 6.6 ms (216 rows), 15 binds
- shipped flat: grep 33.0 ms (16066 rows), join-back 4.8 ms (216 rows), 1 clause(s), 8 arms — ratio grep 1.03x, join-back 0.72x vs literal: PASS (gate 1.5x)
- shipped groups: grep 34.6 ms (16223 rows), join-back 5.6 ms (218 rows), 1 clause(s), 25 arms
