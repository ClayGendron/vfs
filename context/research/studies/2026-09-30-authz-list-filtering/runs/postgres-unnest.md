## postgres — 50,000 entries, the count statement end to end, median of 5 warm runs (ms)

| caller | ranges | values (statements) | unnest (1 statement) | drive (table) |
|---|---|---|---|---|
| 1 folders (0.1%) | 2 | 3.8 (1) | 3.2 | 3.2 |
| 10 folders (1.0%) | 20 | 6.2 (1) | 5.1 | 4.7 |
| 100 folders (10.0%) | 200 | 13.0 (1) | 6.4 | 5.6 |
| 500 folders (50.0%) | 1,000 | 51.8 (1) | 11.5 | 16.4 |
| 10% via 1 top | 2 | 4.9 (1) | 5.3 | 5.6 |
| 10% via 5000 files | 10,000 | 459.7 (10) | 28.2 | 54.6 |
