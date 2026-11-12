# Study 03 tables: kernel run started 2026-11-09 11:41:05, finished 2026-11-09 11:43:47; base counts {'entry': 103921, 'chunks': 462963, 'posting_list': 7480, 'lex_postings': 768707, 'files': 100000, 'not_encoded': 0, 'epoch': 1}

## Level N = 5,000: copy 0.78 s, dirty 4.22 s, not_encoded 5001, level total 22.5 s, rss 2142.0 MB

### N = 5,000 dirty rows (+ sentinel): study 02, Python overlay, median of 3 (its own session)

| query | wall s | nominees | nominee s | surrogate s | bodies MB | body fetch s | tokenize-and-count s | overlay s | stmts | hits | lexical hits | tokenize us/row | overlay us/row | call us/row |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2 words (ranks 300, 3000) | 0.883 | 5,001 | 0.030 | 0.039 | 34.0 | 0.081 | 0.700 | 0.827 | 12 | 10 | 2054 | 139.9 | 165.4 | 176.5 |
| 3 words (ranks 40, 1500, 9000) | 0.896 | 5,001 | 0.029 | 0.039 | 34.0 | 0.080 | 0.698 | 0.827 | 12 | 10 | 4098 | 139.5 | 165.5 | 179.2 |
| 4 words (ranks 700, 2000, 5000, 15000) | 0.880 | 5,001 | 0.029 | 0.040 | 34.0 | 0.080 | 0.698 | 0.825 | 12 | 10 | 1706 | 139.6 | 165.0 | 176.0 |
| 2 very common (ranks 5, 12) | 0.967 | 5,001 | 0.029 | 0.040 | 34.0 | 0.079 | 0.703 | 0.832 | 12 | 10 | 5643 | 140.6 | 166.4 | 193.5 |
| 2 rare (ranks 8000, 20000) | 0.871 | 5,001 | 0.030 | 0.039 | 34.0 | 0.080 | 0.696 | 0.821 | 12 | 10 | 1013 | 139.2 | 164.2 | 174.3 |

### N = 5,000 dirty rows (+ sentinel): this session, Python overlay, 1 pass

| query | wall s | nominees | nominee s | surrogate s | bodies MB | body fetch s | tokenize-and-count s | overlay s | stmts | hits | lexical hits | tokenize us/row | overlay us/row | call us/row |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2 words (ranks 300, 3000) | 0.908 | 5,001 | 0.030 | 0.037 | 34.0 | 0.106 | 0.696 | 0.847 | 12 | 10 | 2054 | 139.1 | 169.4 | 181.7 |
| 3 words (ranks 40, 1500, 9000) | 1.019 | 5,001 | 0.030 | 0.065 | 34.0 | 0.152 | 0.696 | 0.923 | 12 | 10 | 4098 | 139.3 | 184.7 | 203.8 |
| 4 words (ranks 700, 2000, 5000, 15000) | 0.902 | 5,001 | 0.030 | 0.041 | 34.0 | 0.082 | 0.712 | 0.843 | 12 | 10 | 1706 | 142.4 | 168.6 | 180.5 |
| 2 very common (ranks 5, 12) | 0.960 | 5,001 | 0.029 | 0.038 | 34.0 | 0.078 | 0.703 | 0.828 | 12 | 10 | 5643 | 140.5 | 165.6 | 191.9 |
| 2 rare (ranks 8000, 20000) | 0.867 | 5,001 | 0.029 | 0.037 | 34.0 | 0.078 | 0.695 | 0.817 | 12 | 10 | 1013 | 138.9 | 163.3 | 173.4 |

### N = 5,000 dirty rows (+ sentinel): this session, kernel overlay, median of 3

| query | wall s | nominees | nominee s | surrogate s | bodies MB | body fetch s | tokenize-and-count s | overlay s | stmts | hits | lexical hits | tokenize us/row | overlay us/row | call us/row |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2 words (ranks 300, 3000) | 0.377 | 5,001 | 0.029 | 0.038 | 34.0 | 0.079 | 0.192 | 0.316 | 12 | 10 | 2054 | 38.4 | 63.2 | 75.3 |
| 3 words (ranks 40, 1500, 9000) | 0.391 | 5,001 | 0.030 | 0.039 | 34.0 | 0.080 | 0.195 | 0.322 | 12 | 10 | 4098 | 38.9 | 64.5 | 78.1 |
| 4 words (ranks 700, 2000, 5000, 15000) | 0.379 | 5,001 | 0.029 | 0.039 | 34.0 | 0.080 | 0.199 | 0.325 | 12 | 10 | 1706 | 39.7 | 65.1 | 75.8 |
| 2 very common (ranks 5, 12) | 0.480 | 5,001 | 0.030 | 0.038 | 34.0 | 0.079 | 0.199 | 0.325 | 12 | 10 | 5643 | 39.7 | 64.9 | 96.0 |
| 2 rare (ranks 8000, 20000) | 0.363 | 5,001 | 0.029 | 0.037 | 34.0 | 0.079 | 0.191 | 0.314 | 12 | 10 | 1013 | 38.2 | 62.9 | 72.5 |

Parity (Python against kernel, lifted budget, limit 10):
- 2 words (ranks 300, 3000): same paths True, max score delta 0.0
- 3 words (ranks 40, 1500, 9000): same paths True, max score delta 0.0
- 4 words (ranks 700, 2000, 5000, 15000): same paths True, max score delta 0.0
- 2 very common (ranks 5, 12): same paths True, max score delta 0.0
- 2 rare (ranks 8000, 20000): same paths True, max score delta 0.0

Sentinel recall through the kernel at budget 25000: found True; records []
Truncation records on the kernel runs: []

## Level N = 10,000: copy 0.45 s, dirty 8.06 s, not_encoded 10001, level total 41.3 s, rss 2306.7 MB

### N = 10,000 dirty rows (+ sentinel): study 02, Python overlay, median of 3 (its own session)

| query | wall s | nominees | nominee s | surrogate s | bodies MB | body fetch s | tokenize-and-count s | overlay s | stmts | hits | lexical hits | tokenize us/row | overlay us/row | call us/row |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2 words (ranks 300, 3000) | 1.711 | 10,001 | 0.062 | 0.078 | 68.2 | 0.123 | 1.397 | 1.615 | 12 | 10 | 3083 | 139.7 | 161.5 | 171.1 |
| 3 words (ranks 40, 1500, 9000) | 1.777 | 10,001 | 0.063 | 0.079 | 68.2 | 0.127 | 1.411 | 1.644 | 12 | 10 | 7180 | 141.1 | 164.4 | 177.7 |
| 4 words (ranks 700, 2000, 5000, 15000) | 1.716 | 10,001 | 0.065 | 0.077 | 68.2 | 0.123 | 1.405 | 1.622 | 12 | 10 | 2365 | 140.5 | 162.2 | 171.7 |
| 2 very common (ranks 5, 12) | 1.843 | 10,001 | 0.062 | 0.078 | 68.2 | 0.123 | 1.410 | 1.634 | 12 | 10 | 10299 | 141.0 | 163.4 | 184.3 |
| 2 rare (ranks 8000, 20000) | 1.713 | 10,001 | 0.064 | 0.077 | 68.2 | 0.123 | 1.403 | 1.623 | 12 | 10 | 1026 | 140.3 | 162.3 | 171.3 |

### N = 10,000 dirty rows (+ sentinel): this session, Python overlay, 1 pass

| query | wall s | nominees | nominee s | surrogate s | bodies MB | body fetch s | tokenize-and-count s | overlay s | stmts | hits | lexical hits | tokenize us/row | overlay us/row | call us/row |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2 words (ranks 300, 3000) | 1.771 | 10,001 | 0.089 | 0.073 | 68.2 | 0.159 | 1.393 | 1.645 | 12 | 10 | 3083 | 139.3 | 164.5 | 177.1 |
| 3 words (ranks 40, 1500, 9000) | 1.770 | 10,001 | 0.062 | 0.075 | 68.2 | 0.150 | 1.396 | 1.641 | 12 | 10 | 7180 | 139.6 | 164.1 | 177.0 |
| 4 words (ranks 700, 2000, 5000, 15000) | 1.725 | 10,001 | 0.061 | 0.075 | 68.2 | 0.122 | 1.389 | 1.602 | 12 | 10 | 2365 | 138.9 | 160.2 | 172.5 |
| 2 very common (ranks 5, 12) | 1.825 | 10,001 | 0.060 | 0.076 | 68.2 | 0.125 | 1.395 | 1.617 | 12 | 10 | 10299 | 139.5 | 161.7 | 182.5 |
| 2 rare (ranks 8000, 20000) | 1.674 | 10,001 | 0.060 | 0.075 | 68.2 | 0.121 | 1.378 | 1.589 | 12 | 10 | 1026 | 137.8 | 158.9 | 167.4 |

### N = 10,000 dirty rows (+ sentinel): this session, kernel overlay, median of 3

| query | wall s | nominees | nominee s | surrogate s | bodies MB | body fetch s | tokenize-and-count s | overlay s | stmts | hits | lexical hits | tokenize us/row | overlay us/row | call us/row |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2 words (ranks 300, 3000) | 0.687 | 10,001 | 0.060 | 0.077 | 68.2 | 0.123 | 0.382 | 0.598 | 12 | 10 | 3083 | 38.2 | 59.8 | 68.7 |
| 3 words (ranks 40, 1500, 9000) | 0.747 | 10,001 | 0.060 | 0.077 | 68.2 | 0.121 | 0.394 | 0.637 | 12 | 10 | 7180 | 39.4 | 63.7 | 74.6 |
| 4 words (ranks 700, 2000, 5000, 15000) | 0.703 | 10,001 | 0.062 | 0.077 | 68.2 | 0.121 | 0.398 | 0.610 | 12 | 10 | 2365 | 39.8 | 61.0 | 70.3 |
| 2 very common (ranks 5, 12) | 0.814 | 10,001 | 0.061 | 0.076 | 68.2 | 0.121 | 0.396 | 0.640 | 12 | 10 | 10299 | 39.6 | 64.0 | 81.4 |
| 2 rare (ranks 8000, 20000) | 0.681 | 10,001 | 0.060 | 0.076 | 68.2 | 0.123 | 0.383 | 0.595 | 12 | 10 | 1026 | 38.3 | 59.5 | 68.1 |

Parity (Python against kernel, lifted budget, limit 10):
- 2 words (ranks 300, 3000): same paths True, max score delta 0.0
- 3 words (ranks 40, 1500, 9000): same paths True, max score delta 0.0
- 4 words (ranks 700, 2000, 5000, 15000): same paths True, max score delta 0.0
- 2 very common (ranks 5, 12): same paths True, max score delta 0.0
- 2 rare (ranks 8000, 20000): same paths True, max score delta 0.0

Sentinel recall through the kernel at budget 25000: found True; records []
Truncation records on the kernel runs: []

## Level N = 25,000: copy 0.45 s, dirty 17.76 s, not_encoded 25001, level total 98.5 s, rss 2306.7 MB

### N = 25,000 dirty rows (+ sentinel): study 02, Python overlay, median of 3 (its own session)

| query | wall s | nominees | nominee s | surrogate s | bodies MB | body fetch s | tokenize-and-count s | overlay s | stmts | hits | lexical hits | tokenize us/row | overlay us/row | call us/row |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2 words (ranks 300, 3000) | 4.356 | 25,000 | 0.172 | 0.198 | 172.4 | 0.311 | 3.571 | 4.130 | 12 | 10 | 6268 | 142.8 | 165.2 | 174.2 |
| 3 words (ranks 40, 1500, 9000) | 4.424 | 25,000 | 0.169 | 0.205 | 172.4 | 0.313 | 3.595 | 4.151 | 12 | 10 | 16544 | 143.8 | 166.0 | 177.0 |
| 4 words (ranks 700, 2000, 5000, 15000) | 4.361 | 25,000 | 0.174 | 0.243 | 172.4 | 0.267 | 3.585 | 4.132 | 12 | 10 | 4489 | 143.4 | 165.3 | 174.4 |
| 2 very common (ranks 5, 12) | 4.555 | 25,000 | 0.174 | 0.200 | 172.4 | 0.262 | 3.611 | 4.170 | 12 | 10 | 24343 | 144.4 | 166.8 | 182.2 |
| 2 rare (ranks 8000, 20000) | 4.316 | 25,000 | 0.171 | 0.199 | 172.4 | 0.310 | 3.559 | 4.106 | 12 | 10 | 1191 | 142.4 | 164.2 | 172.6 |

### N = 25,000 dirty rows (+ sentinel): this session, Python overlay, 1 pass

| query | wall s | nominees | nominee s | surrogate s | bodies MB | body fetch s | tokenize-and-count s | overlay s | stmts | hits | lexical hits | tokenize us/row | overlay us/row | call us/row |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2 words (ranks 300, 3000) | 4.279 | 25,000 | 0.158 | 0.226 | 172.4 | 0.264 | 3.525 | 4.068 | 12 | 10 | 6268 | 141.0 | 162.7 | 171.1 |
| 3 words (ranks 40, 1500, 9000) | 4.340 | 25,000 | 0.159 | 0.190 | 172.4 | 0.250 | 3.529 | 4.016 | 12 | 10 | 16544 | 141.2 | 160.6 | 173.6 |
| 4 words (ranks 700, 2000, 5000, 15000) | 4.253 | 25,000 | 0.161 | 0.195 | 172.4 | 0.250 | 3.556 | 4.040 | 12 | 10 | 4489 | 142.2 | 161.6 | 170.1 |
| 2 very common (ranks 5, 12) | 4.429 | 25,000 | 0.158 | 0.186 | 172.4 | 0.254 | 3.575 | 4.108 | 12 | 10 | 24343 | 143.0 | 164.3 | 177.2 |
| 2 rare (ranks 8000, 20000) | 4.278 | 25,000 | 0.158 | 0.201 | 172.4 | 0.255 | 3.549 | 4.042 | 12 | 10 | 1191 | 142.0 | 161.7 | 171.1 |

### N = 25,000 dirty rows (+ sentinel): this session, kernel overlay, median of 3

| query | wall s | nominees | nominee s | surrogate s | bodies MB | body fetch s | tokenize-and-count s | overlay s | stmts | hits | lexical hits | tokenize us/row | overlay us/row | call us/row |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2 words (ranks 300, 3000) | 1.698 | 25,000 | 0.161 | 0.191 | 172.4 | 0.255 | 0.965 | 1.487 | 12 | 10 | 6268 | 38.6 | 59.5 | 67.9 |
| 3 words (ranks 40, 1500, 9000) | 1.789 | 25,000 | 0.161 | 0.193 | 172.4 | 0.252 | 1.006 | 1.537 | 12 | 10 | 16544 | 40.2 | 61.5 | 71.6 |
| 4 words (ranks 700, 2000, 5000, 15000) | 1.767 | 25,000 | 0.171 | 0.203 | 172.4 | 0.256 | 1.018 | 1.534 | 12 | 10 | 4489 | 40.7 | 61.4 | 70.7 |
| 2 very common (ranks 5, 12) | 1.923 | 25,000 | 0.169 | 0.205 | 172.4 | 0.257 | 1.017 | 1.562 | 12 | 10 | 24343 | 40.7 | 62.5 | 76.9 |
| 2 rare (ranks 8000, 20000) | 1.686 | 25,000 | 0.169 | 0.195 | 172.4 | 0.257 | 0.965 | 1.477 | 12 | 10 | 1191 | 38.6 | 59.1 | 67.4 |

Parity (Python against kernel, lifted budget, limit 10):
- 2 words (ranks 300, 3000): same paths True, max score delta 0.0
- 3 words (ranks 40, 1500, 9000): same paths True, max score delta 0.0
- 4 words (ranks 700, 2000, 5000, 15000): same paths True, max score delta 0.0
- 2 very common (ranks 5, 12): same paths True, max score delta 0.0
- 2 rare (ranks 8000, 20000): same paths True, max score delta 0.0

Sentinel recall through the kernel at budget 25000: found False; records [{'scanned': 25000, 'budget': 25000}]
Truncation records on the kernel runs: ['{"budget": 25000, "scanned": 25000}']

## Slopes between consecutive levels (median over the five queries), us per dirty row
| from N | to N | implementation | call slope | tokenize slope | overlay slope |
|---|---|---|---|---|---|
| 5,000 | 10,000 | Python overlay (1 pass) | 164.4 | 138.5 | 154.4 |
| 5,000 | 10,000 | kernel overlay | 64.8 | 39.4 | 57.0 |
| 10,000 | 25,000 | Python overlay (1 pass) | 171.3 | 144.5 | 162.6 |
| 10,000 | 25,000 | kernel overlay | 69.5 | 40.8 | 60.0 |
