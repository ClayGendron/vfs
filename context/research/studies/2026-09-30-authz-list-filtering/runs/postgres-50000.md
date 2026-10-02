## postgres — 50,000 entries, one chunk each, median of 3 warm runs (ms)

| caller | arms | shape | count ms | top10 ms | rows seen |
|---|---|---|---|---|---|
| 1 folders (0.1%) | 1 | like | 1.1 | 0.9 | 50 |
| 1 folders (0.1%) | 1 | range | 1.4 | 0.8 | 50 |
| 1 folders (0.1%) | 1 | tree | 7.5 | 7.1 | 50 |
| 1 folders (0.1%) | 1 | stab (+4 ms cover write) | 53.6 | 52.1 | 50 |
| 1 folders (0.1%) | 1 | drive | 9.1 | 4.3 | 50 |
| 1 folders (0.1%) | 1 | values | 8.2 | 6.3 | 50 |
| 10 folders (1.0%) | 10 | like | 5.4 | 4.3 | 500 |
| 10 folders (1.0%) | 10 | range | 2.8 | 2.2 | 500 |
| 10 folders (1.0%) | 10 | tree | 12.8 | 12.2 | 500 |
| 10 folders (1.0%) | 10 | stab (+3 ms cover write) | 49.3 | 49.1 | 500 |
| 10 folders (1.0%) | 10 | drive | 12.5 | 7.1 | 500 |
| 10 folders (1.0%) | 10 | values | 6.9 | 6.6 | 500 |
| 100 folders (10.0%) | 100 | like | 14.5 | 14.8 | 5,000 |
| 100 folders (10.0%) | 100 | range | 8.2 | 7.9 | 5,000 |
| 100 folders (10.0%) | 100 | tree | 17.6 | 16.7 | 5,000 |
| 100 folders (10.0%) | 100 | stab (+4 ms cover write) | 121.9 | 117.8 | 5,000 |
| 100 folders (10.0%) | 100 | drive | 8.5 | 7.6 | 5,000 |
| 100 folders (10.0%) | 100 | values | 15.3 | 14.3 | 5,000 |
| 500 folders (50.0%) | 500 | like | 149.2 | 142.5 | 25,000 |
| 500 folders (50.0%) | 500 | range | 31.4 | 32.2 | 25,000 |
| 500 folders (50.0%) | 500 | tree | 1803.9 | 2172.9 | 25,000 |
| 500 folders (50.0%) | 500 | stab (+13 ms cover write) | 150.4 | 142.0 | 25,000 |
| 500 folders (50.0%) | 500 | drive | 20.7 | 20.3 | 25,000 |
| 500 folders (50.0%) | 500 | values | 53.6 | 54.6 | 25,000 |
| 10% via 1 top | 1 | like | 6.2 | 5.4 | 5,000 |
| 10% via 1 top | 1 | range | 5.7 | 5.3 | 5,000 |
| 10% via 1 top | 1 | tree | 10.0 | 9.4 | 5,000 |
| 10% via 1 top | 1 | stab (+4 ms cover write) | 54.4 | 52.6 | 5,000 |
| 10% via 1 top | 1 | drive | 7.1 | 5.6 | 5,000 |
| 10% via 1 top | 1 | values | 7.7 | 6.0 | 5,000 |
| 10% via 5000 files | 5000 | like | 322.3 | 455.4 | 5,000 |
| 10% via 5000 files | 5000 | range | 267.7 | 278.5 | 5,000 |
| 10% via 5000 files | 5000 | tree | 20380.4 | 18185.4 | 5,000 |
| 10% via 5000 files | 5000 | stab (+69 ms cover write) | 117.8 | 115.8 | 5,000 |
| 10% via 5000 files | 5000 | drive | 72.0 | 66.8 | 5,000 |
| 10% via 5000 files | 5000 | values | 463.3 | 462.8 | 5,000 |
