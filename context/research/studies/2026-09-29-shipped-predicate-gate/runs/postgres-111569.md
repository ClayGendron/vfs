## postgres — 111,569 entry rows, median of 5 warm runs

- literal_like: grep 5.0 ms (1588 rows), join-back 4.6 ms (222 rows), 17 binds
- shipped flat: grep 4.8 ms (1588 rows), join-back 4.1 ms (222 rows), 1 clause(s), 9 arms — ratio grep 0.96x, join-back 0.89x vs literal: PASS (gate 1.5x)
- shipped groups: grep 4.9 ms (1590 rows), join-back 4.6 ms (222 rows), 1 clause(s), 16 arms
