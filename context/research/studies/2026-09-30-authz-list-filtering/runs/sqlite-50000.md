## sqlite — 50,000 entries, one chunk each, median of 3 warm runs (ms)

| caller | arms | shape | count ms | top10 ms | rows seen |
|---|---|---|---|---|---|
| 1 folders (0.1%) | 1 | like | 1.0 | 0.9 | 50 |
| 1 folders (0.1%) | 1 | range | 0.8 | 0.8 | 50 |
| 1 folders (0.1%) | 1 | tree | 11.2 | 10.0 | 50 |
| 1 folders (0.1%) | 1 | stab (+1 ms cover write) | 16.2 | 15.4 | 50 |
| 1 folders (0.1%) | 1 | drive | 1.2 | 1.0 | 50 |
| 1 folders (0.1%) | 1 | values | 1.7 | 1.6 | 50 |
| 10 folders (1.0%) | 10 | like | 2.0 | 1.9 | 500 |
| 10 folders (1.0%) | 10 | range | 2.0 | 2.2 | 500 |
| 10 folders (1.0%) | 10 | tree | 16.3 | 20.6 | 500 |
| 10 folders (1.0%) | 10 | stab (+2 ms cover write) | 21.5 | 22.7 | 500 |
| 10 folders (1.0%) | 10 | drive | 1.4 | 1.3 | 500 |
| 10 folders (1.0%) | 10 | values | 3.2 | 3.2 | 500 |
| 100 folders (10.0%) | 100 | like | 201.4 | 206.6 | 5,000 |
| 100 folders (10.0%) | 100 | range | 203.7 | 199.2 | 5,000 |
| 100 folders (10.0%) | 100 | tree | 16.0 | 18.4 | 5,000 |
| 100 folders (10.0%) | 100 | stab (+2 ms cover write) | 17.1 | 17.5 | 5,000 |
| 100 folders (10.0%) | 100 | drive | 1.5 | 1.5 | 5,000 |
| 100 folders (10.0%) | 100 | values | 4.8 | 5.0 | 5,000 |
| 500 folders (50.0%) | 500 | like | 894.9 | 871.4 | 25,000 |
| 500 folders (50.0%) | 500 | range | 905.9 | 928.6 | 25,000 |
| 500 folders (50.0%) | 500 | tree | 33.9 | 80.2 | 25,000 |
| 500 folders (50.0%) | 500 | stab (+3 ms cover write) | 19.5 | 21.2 | 25,000 |
| 500 folders (50.0%) | 500 | drive | 5.9 | 6.2 | 25,000 |
| 500 folders (50.0%) | 500 | values | 22.7 | 24.6 | 25,000 |
| 10% via 1 top | 1 | like | 1.7 | 1.7 | 5,000 |
| 10% via 1 top | 1 | range | 1.6 | 1.7 | 5,000 |
| 10% via 1 top | 1 | tree | 5.7 | 6.1 | 5,000 |
| 10% via 1 top | 1 | stab (+1 ms cover write) | 16.0 | 16.9 | 5,000 |
| 10% via 1 top | 1 | drive | 1.2 | 1.3 | 5,000 |
| 10% via 1 top | 1 | values | 1.5 | 1.5 | 5,000 |
| 10% via 5000 files | 5000 | like | 9963.8 | 9948.5 | 5,000 |
| 10% via 5000 files | 5000 | range | 9732.9 | 9967.9 | 5,000 |
| 10% via 5000 files | 5000 | tree | 442.0 | 734.1 | 5,000 |
| 10% via 5000 files | 5000 | stab (+20 ms cover write) | 20.5 | 21.4 | 5,000 |
| 10% via 5000 files | 5000 | drive | 4.9 | 5.1 | 5,000 |
| 10% via 5000 files | 5000 | values | 169.6 | 183.6 | 5,000 |
