## postgres 100,000 files (results_postgres_100000.json)

Started 2026-11-09 11:02:27, finished 2026-11-09 11:07:54; Apple M1 Pro, 10 cores, 32 GB; Python 3.13.11; levels [10000, 25000].

### Build

Base store reused: {'entry': 103921, 'chunks': 462963, 'posting_list': 7480, 'lex_postings': 768707, 'files': 100000, 'not_encoded': 0, 'epoch': 1}.

### Suite summary per level

| N dirty | grep: sum of 5 medians s | grep: slowest median s | grep scan bytes MB | glean@500: sum s | glean@500 slowest s | glean@25000: sum s | glean@25000 slowest s | glean@25000 body MB | glean@25000 tokenize s (median query) |
|---|---|---|---|---|---|---|---|---|---|
| 10,000 | 9.559 | 2.710 | 54.6 | 4.513 | 3.793 | 14.8 | 5.815 | 68.2 | 1.459 |
| 25,000 | 10.9 | 2.599 | 71.7 | 4.556 | 3.806 | 29.7 | 8.839 | 159.2 | 3.388 |

### Per-dirty-entry slopes

| from N | to N | grep: s per dirty entry per call | grep: bytes per dirty entry | glean@25000: s per dirty entry per call | glean@25000: bytes per dirty entry | glean tokenize s per entry |
|---|---|---|---|---|---|---|
| 10,000 | 25,000 | 18 µs | 3,018 | 198 µs | 6,070 | 128 µs |

### grep per pattern

| N dirty | pattern | median wall s | SQL stmts | index rows | scan rows | scan bytes MB | body bytes fetched MB | nominee s | body fetch s | verify s | files hit | records |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 10,000 | rare literal (rank 12000) | 1.629 | 13 | 5,291 | 10,001 | 68.2 | 202.1 | 0.057 | 1.466 | 0.026 | 686 | none |
| 10,000 | common word (rank 40) | 2.316 | 13 | 22,514 | 2,486 | 16.8 | 224.6 | 0.022 | 1.744 | 0.060 | 23,854 | candidate budget (3/3) |
| 10,000 | alternation regex (ranks 2000|2500) | 2.710 | 16 | 17,015 | 7,985 | 54.6 | 321.3 | 0.045 | 2.335 | 0.048 | 8,924 | candidate budget (3/3) |
| 10,000 | case-insensitive word (rank 800) | 2.244 | 14 | 22,522 | 2,478 | 16.7 | 249.2 | 0.020 | 1.876 | 0.041 | 8,080 | candidate budget (3/3) |
| 10,000 | matches almost nothing | 0.661 | 7 | 0 | 10,001 | 68.2 | 68.2 | 0.058 | 0.556 | 0.011 | 0 | none |
| 25,000 | rare literal (rank 12000) | 2.193 | 14 | 4,496 | 20,504 | 139.7 | 253.7 | 0.132 | 1.908 | 0.037 | 667 | candidate budget (3/3) |
| 25,000 | common word (rank 40) | 2.361 | 13 | 19,189 | 5,811 | 39.8 | 216.6 | 0.055 | 1.662 | 0.092 | 22,671 | candidate budget (3/3) |
| 25,000 | alternation regex (ranks 2000|2500) | 2.599 | 15 | 14,529 | 10,471 | 71.7 | 299.3 | 0.076 | 2.207 | 0.048 | 7,949 | candidate budget (3/3) |
| 25,000 | case-insensitive word (rank 800) | 2.196 | 14 | 19,126 | 5,874 | 40.3 | 238.0 | 0.054 | 1.803 | 0.042 | 7,584 | candidate budget (3/3) |
| 25,000 | matches almost nothing | 1.528 | 9 | 0 | 23,401 | 159.2 | 159.2 | 0.160 | 1.270 | 0.029 | 0 | none |

### glean at the default overlay budget (500)

| N dirty | budget | query | median wall s | SQL stmts | nominees | bodies | body MB | nominee s | body fetch s | tokenize s | score s | overlay s | overlay hits | hits | records |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 10,000 | 500 | 2 words (ranks 300, 3000) | 0.151 | 11 | 500 | 500 | 3.6 | 0.009 | 0.029 | 0.075 | 0.000 | 0.112 | 112 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 10,000 | 500 | 3 words (ranks 40, 1500, 9000) | 0.266 | 11 | 500 | 500 | 3.6 | 0.009 | 0.029 | 0.075 | 0.000 | 0.112 | 321 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 10,000 | 500 | 4 words (ranks 700, 2000, 5000, 15000) | 0.155 | 11 | 500 | 500 | 3.6 | 0.009 | 0.029 | 0.074 | 0.000 | 0.112 | 81 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 10,000 | 500 | 2 very common (ranks 5, 12) | 3.793 | 11 | 500 | 500 | 3.6 | 0.009 | 0.029 | 0.075 | 0.000 | 0.112 | 477 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 10,000 | 500 | 2 rare (ranks 8000, 20000) | 0.147 | 11 | 500 | 500 | 3.6 | 0.009 | 0.029 | 0.076 | 0.000 | 0.112 | 6 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 25,000 | 500 | 2 words (ranks 300, 3000) | 0.158 | 11 | 500 | 500 | 3.5 | 0.017 | 0.030 | 0.075 | 0.000 | 0.112 | 123 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 25,000 | 500 | 3 words (ranks 40, 1500, 9000) | 0.286 | 11 | 500 | 500 | 3.5 | 0.017 | 0.028 | 0.076 | 0.000 | 0.113 | 303 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 25,000 | 500 | 4 words (ranks 700, 2000, 5000, 15000) | 0.158 | 11 | 500 | 500 | 3.5 | 0.016 | 0.029 | 0.075 | 0.000 | 0.110 | 75 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 25,000 | 500 | 2 very common (ranks 5, 12) | 3.806 | 11 | 500 | 500 | 3.5 | 0.017 | 0.029 | 0.076 | 0.000 | 0.113 | 476 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 25,000 | 500 | 2 rare (ranks 8000, 20000) | 0.148 | 11 | 500 | 500 | 3.5 | 0.017 | 0.028 | 0.074 | 0.000 | 0.109 | 5 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |

### glean at the lifted overlay budget (25,000)

| N dirty | budget | query | median wall s | SQL stmts | nominees | bodies | body MB | nominee s | body fetch s | tokenize s | score s | overlay s | overlay hits | hits | records |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 10,000 | 25,000 | 2 words (ranks 300, 3000) | 2.215 | 11 | 10,001 | 10,001 | 68.2 | 0.056 | 0.535 | 1.459 | 0.000 | 2.115 | 2,198 | 10 | none |
| 10,000 | 25,000 | 3 words (ranks 40, 1500, 9000) | 2.313 | 11 | 10,001 | 10,001 | 68.2 | 0.055 | 0.576 | 1.472 | 0.001 | 2.161 | 6,297 | 10 | none |
| 10,000 | 25,000 | 4 words (ranks 700, 2000, 5000, 15000) | 2.200 | 11 | 10,001 | 10,001 | 68.2 | 0.055 | 0.539 | 1.456 | 0.000 | 2.100 | 1,474 | 10 | none |
| 10,000 | 25,000 | 2 very common (ranks 5, 12) | 5.815 | 11 | 10,001 | 10,001 | 68.2 | 0.093 | 0.539 | 1.475 | 0.002 | 2.126 | 9,402 | 10 | none |
| 10,000 | 25,000 | 2 rare (ranks 8000, 20000) | 2.306 | 11 | 10,001 | 10,001 | 68.2 | 0.055 | 0.581 | 1.452 | 0.000 | 2.216 | 145 | 10 | none |
| 25,000 | 25,000 | 2 words (ranks 300, 3000) | 5.176 | 11 | 23,401 | 23,401 | 159.2 | 0.145 | 1.294 | 3.391 | 0.001 | 4.966 | 5,178 | 10 | none |
| 25,000 | 25,000 | 3 words (ranks 40, 1500, 9000) | 5.314 | 11 | 23,401 | 23,401 | 159.2 | 0.150 | 1.260 | 3.364 | 0.003 | 4.924 | 14,781 | 10 | none |
| 25,000 | 25,000 | 4 words (ranks 700, 2000, 5000, 15000) | 5.200 | 11 | 23,401 | 23,401 | 159.2 | 0.163 | 1.279 | 3.388 | 0.001 | 4.926 | 3,430 | 10 | none |
| 25,000 | 25,000 | 2 very common (ranks 5, 12) | 8.839 | 11 | 23,401 | 23,401 | 159.2 | 0.150 | 1.259 | 3.409 | 0.004 | 5.011 | 22,019 | 10 | none |
| 25,000 | 25,000 | 2 rare (ranks 8000, 20000) | 5.163 | 11 | 23,401 | 23,401 | 159.2 | 0.149 | 1.325 | 3.370 | 0.000 | 4.959 | 334 | 10 | none |

### Sentinel recall

| N dirty | not encoded after dirtying | grep finds sentinel | grep wall s | glean@500 finds sentinel | glean@500 record | glean@25000 finds sentinel | glean@25000 record |
|---|---|---|---|---|---|---|---|
| 10,000 | 10,001 | True | 0.629 | False | overlay budget {"scanned":500,"budget":500} (1/1) | True | none |
| 25,000 | 23,401 | True | 1.534 | False | overlay budget {"scanned":500,"budget":500} (1/1) | True | none |

### One pass under the default 10 s wall

| N dirty | verb | call | wall s | SQL stmts | hits | records |
|---|---|---|---|---|---|---|
| 10,000 | grep | rare literal (rank 12000) | 2.116 | 13 | 686 | none |
| 10,000 | grep | common word (rank 40) | 2.972 | 13 | 23854 | candidate budget (1/1) |
| 10,000 | grep | alternation regex (ranks 2000|2500) | 2.747 | 16 | 8924 | candidate budget (1/1) |
| 10,000 | grep | case-insensitive word (rank 800) | 2.245 | 14 | 8080 | candidate budget (1/1) |
| 10,000 | grep | matches almost nothing | 0.670 | 7 | 0 | none |
| 10,000 | glean@25000 | 2 words (ranks 300, 3000) | 2.218 | 11 | 10 | none |
| 10,000 | glean@25000 | 3 words (ranks 40, 1500, 9000) | 2.353 | 11 | 10 | none |
| 10,000 | glean@25000 | 4 words (ranks 700, 2000, 5000, 15000) | 2.165 | 11 | 10 | none |
| 10,000 | glean@25000 | 2 very common (ranks 5, 12) | 5.890 | 11 | 10 | none |
| 10,000 | glean@25000 | 2 rare (ranks 8000, 20000) | 2.205 | 11 | 10 | none |
| 25,000 | grep | rare literal (rank 12000) | 2.315 | 14 | 667 | candidate budget (1/1) |
| 25,000 | grep | common word (rank 40) | 2.419 | 13 | 22671 | candidate budget (1/1) |
| 25,000 | grep | alternation regex (ranks 2000|2500) | 2.687 | 15 | 7949 | candidate budget (1/1) |
| 25,000 | grep | case-insensitive word (rank 800) | 2.242 | 14 | 7584 | candidate budget (1/1) |
| 25,000 | grep | matches almost nothing | 1.499 | 9 | 0 | none |
| 25,000 | glean@25000 | 2 words (ranks 300, 3000) | 5.268 | 11 | 10 | none |
| 25,000 | glean@25000 | 3 words (ranks 40, 1500, 9000) | 5.339 | 11 | 10 | none |
| 25,000 | glean@25000 | 4 words (ranks 700, 2000, 5000, 15000) | 5.224 | 11 | 10 | none |
| 25,000 | glean@25000 | 2 very common (ranks 5, 12) | 8.901 | 11 | 10 | none |
| 25,000 | glean@25000 | 2 rare (ranks 8000, 20000) | 5.208 | 11 | 10 | none |

### Level walls

| N | fresh-store copy s | dirty write s | level total s | peak RSS MB |
|---|---|---|---|---|
| 10,000 | 0.03 | 11.86 | 126.1 | 423.8 |
| 25,000 | 0.03 | 17.69 | 200.5 | 511.5 |

## postgres 100,000 files (results_postgres_100000_exact25000.json)

Started 2026-11-09 11:08:22, finished 2026-11-09 11:11:35; Apple M1 Pro, 10 cores, 32 GB; Python 3.13.11; levels [25000].

### Build

Base store reused: {'entry': 103924, 'chunks': 462963, 'posting_list': 7480, 'lex_postings': 768707, 'files': 100001, 'not_encoded': 23401, 'epoch': 1}.

### Suite summary per level

| N dirty | grep: sum of 5 medians s | grep: slowest median s | grep scan bytes MB | glean@500: sum s | glean@500 slowest s | glean@25000: sum s | glean@25000 slowest s | glean@25000 body MB | glean@25000 tokenize s (median query) |
|---|---|---|---|---|---|---|---|---|---|
| 25,000 | 10.9 | 2.580 | 74.3 | 4.549 | 3.824 | 31.9 | 9.385 | 170.4 | 3.692 |

### Per-dirty-entry slopes

| from N | to N | grep: s per dirty entry per call | grep: bytes per dirty entry | glean@25000: s per dirty entry per call | glean@25000: bytes per dirty entry | glean tokenize s per entry |
|---|---|---|---|---|---|---|

### grep per pattern

| N dirty | pattern | median wall s | SQL stmts | index rows | scan rows | scan bytes MB | body bytes fetched MB | nominee s | body fetch s | verify s | files hit | records |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 25,000 | rare literal (rank 12000) | 2.163 | 14 | 4,388 | 20,612 | 141.0 | 252.5 | 0.130 | 1.910 | 0.039 | 652 | candidate budget (3/3) |
| 25,000 | common word (rank 40) | 2.336 | 13 | 18,773 | 6,227 | 42.7 | 215.2 | 0.046 | 1.671 | 0.105 | 22,532 | candidate budget (3/3) |
| 25,000 | alternation regex (ranks 2000|2500) | 2.580 | 15 | 14,213 | 10,787 | 74.3 | 296.9 | 0.068 | 2.211 | 0.044 | 7,837 | candidate budget (3/3) |
| 25,000 | case-insensitive word (rank 800) | 2.210 | 14 | 18,698 | 6,302 | 43.3 | 236.2 | 0.046 | 1.827 | 0.043 | 7,500 | candidate budget (3/3) |
| 25,000 | matches almost nothing | 1.629 | 10 | 0 | 25,000 | 170.4 | 170.4 | 0.168 | 1.402 | 0.028 | 0 | candidate budget (3/3) |

### glean at the default overlay budget (500)

| N dirty | budget | query | median wall s | SQL stmts | nominees | bodies | body MB | nominee s | body fetch s | tokenize s | score s | overlay s | overlay hits | hits | records |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 25,000 | 500 | 2 words (ranks 300, 3000) | 0.153 | 11 | 500 | 500 | 3.6 | 0.004 | 0.030 | 0.079 | 0.000 | 0.117 | 127 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 25,000 | 500 | 3 words (ranks 40, 1500, 9000) | 0.273 | 11 | 500 | 500 | 3.6 | 0.005 | 0.029 | 0.082 | 0.000 | 0.117 | 306 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 25,000 | 500 | 4 words (ranks 700, 2000, 5000, 15000) | 0.155 | 11 | 500 | 500 | 3.6 | 0.005 | 0.030 | 0.080 | 0.000 | 0.116 | 74 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 25,000 | 500 | 2 very common (ranks 5, 12) | 3.824 | 11 | 500 | 500 | 3.6 | 0.004 | 0.029 | 0.079 | 0.000 | 0.115 | 475 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 25,000 | 500 | 2 rare (ranks 8000, 20000) | 0.144 | 11 | 500 | 500 | 3.6 | 0.004 | 0.029 | 0.078 | 0.000 | 0.115 | 5 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |

### glean at the lifted overlay budget (25,000)

| N dirty | budget | query | median wall s | SQL stmts | nominees | bodies | body MB | nominee s | body fetch s | tokenize s | score s | overlay s | overlay hits | hits | records |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 25,000 | 25,000 | 2 words (ranks 300, 3000) | 5.624 | 11 | 25,000 | 25,000 | 170.4 | 0.161 | 1.366 | 3.677 | 0.001 | 5.382 | 5,553 | 10 | overlay budget {"scanned":25000,"budget":25000} (3/3) |
| 25,000 | 25,000 | 3 words (ranks 40, 1500, 9000) | 5.761 | 11 | 25,000 | 25,000 | 170.4 | 0.164 | 1.361 | 3.719 | 0.003 | 5.372 | 15,813 | 10 | overlay budget {"scanned":25000,"budget":25000} (3/3) |
| 25,000 | 25,000 | 4 words (ranks 700, 2000, 5000, 15000) | 5.595 | 11 | 25,000 | 25,000 | 170.4 | 0.163 | 1.350 | 3.692 | 0.001 | 5.309 | 3,677 | 10 | overlay budget {"scanned":25000,"budget":25000} (3/3) |
| 25,000 | 25,000 | 2 very common (ranks 5, 12) | 9.385 | 11 | 25,000 | 25,000 | 170.4 | 0.164 | 1.329 | 3.731 | 0.004 | 5.358 | 23,540 | 10 | overlay budget {"scanned":25000,"budget":25000} (3/3) |
| 25,000 | 25,000 | 2 rare (ranks 8000, 20000) | 5.547 | 11 | 25,000 | 25,000 | 170.4 | 0.172 | 1.327 | 3.683 | 0.000 | 5.288 | 354 | 10 | overlay budget {"scanned":25000,"budget":25000} (3/3) |

### Sentinel recall

| N dirty | not encoded after dirtying | grep finds sentinel | grep wall s | glean@500 finds sentinel | glean@500 record | glean@25000 finds sentinel | glean@25000 record |
|---|---|---|---|---|---|---|---|
| 25,000 | 25,001 | False | 1.647 | False | overlay budget {"scanned":500,"budget":500} (1/1) | False | overlay budget {"scanned":25000,"budget":25000} (1/1) |

### One pass under the default 10 s wall

| N dirty | verb | call | wall s | SQL stmts | hits | records |
|---|---|---|---|---|---|---|
| 25,000 | grep | rare literal (rank 12000) | 2.222 | 14 | 652 | candidate budget (1/1) |
| 25,000 | grep | common word (rank 40) | 2.353 | 13 | 22532 | candidate budget (1/1) |
| 25,000 | grep | alternation regex (ranks 2000|2500) | 2.620 | 15 | 7837 | candidate budget (1/1) |
| 25,000 | grep | case-insensitive word (rank 800) | 2.230 | 14 | 7500 | candidate budget (1/1) |
| 25,000 | grep | matches almost nothing | 1.635 | 10 | 0 | candidate budget (1/1) |
| 25,000 | glean@25000 | 2 words (ranks 300, 3000) | 5.618 | 11 | 10 | overlay budget {"scanned":25000,"budget":25000} (1/1) |
| 25,000 | glean@25000 | 3 words (ranks 40, 1500, 9000) | 5.773 | 11 | 10 | overlay budget {"scanned":25000,"budget":25000} (1/1) |
| 25,000 | glean@25000 | 4 words (ranks 700, 2000, 5000, 15000) | 5.622 | 11 | 10 | overlay budget {"scanned":25000,"budget":25000} (1/1) |
| 25,000 | glean@25000 | 2 very common (ranks 5, 12) | 9.349 | 11 | 10 | overlay budget {"scanned":25000,"budget":25000} (1/1) |
| 25,000 | glean@25000 | 2 rare (ranks 8000, 20000) | 5.578 | 11 | 10 | overlay budget {"scanned":25000,"budget":25000} (1/1) |

### Level walls

| N | fresh-store copy s | dirty write s | level total s | peak RSS MB |
|---|---|---|---|---|
| 25,000 | 0.03 | 2.35 | 192.7 | 485.1 |

## sqlite 10,000 files (results_sqlite_10000.json)

Started 2026-11-09 10:44:31, finished 2026-11-09 10:46:23; Apple M1 Pro, 10 cores, 32 GB; Python 3.13.11; levels [500, 2000, 5000, 10000].

### Build

| step | wall s | SQL stmts | files | chunks | posting rows | lex posting rows | not encoded | epoch |
|---|---|---|---|---|---|---|---|---|
| write (10000 files, 10,000 per call) | 8.29 | - | - | - | - | - | - | - |
| reindex #0 | 11.9419 | 360 | 10,000 | 46,810 | 7,473 | 93,378 | 0 | 1 |
Store size 352.5 MB; peak RSS 955.4 MB; base build total 20.4 s.

### Suite summary per level

| N dirty | grep: sum of 5 medians s | grep: slowest median s | grep scan bytes MB | glean@500: sum s | glean@500 slowest s | glean@25000: sum s | glean@25000 slowest s | glean@25000 body MB | glean@25000 tokenize s (median query) |
|---|---|---|---|---|---|---|---|---|---|
| 500 | 0.408 | 0.210 | 3.4 | 0.486 | 0.107 | 0.490 | 0.105 | 3.4 | 0.069 |
| 2,000 | 0.483 | 0.179 | 13.4 | 0.483 | 0.102 | 1.692 | 0.348 | 13.4 | 0.271 |
| 5,000 | 0.684 | 0.238 | 34.1 | 0.515 | 0.111 | 4.308 | 0.897 | 34.1 | 0.714 |
| 10,000 | 0.988 | 0.241 | 68.8 | 0.562 | 0.128 | 8.482 | 1.716 | 68.8 | 1.405 |

### Per-dirty-entry slopes

| from N | to N | grep: s per dirty entry per call | grep: bytes per dirty entry | glean@25000: s per dirty entry per call | glean@25000: bytes per dirty entry | glean tokenize s per entry |
|---|---|---|---|---|---|---|
| 500 | 2,000 | 10 µs | 6,632 | 160 µs | 6,632 | 134 µs |
| 2,000 | 5,000 | 13 µs | 6,904 | 174 µs | 6,904 | 146 µs |
| 5,000 | 10,000 | 12 µs | 6,946 | 167 µs | 6,946 | 140 µs |

### grep per pattern

| N dirty | pattern | median wall s | SQL stmts | index rows | scan rows | scan bytes MB | body bytes fetched MB | nominee s | body fetch s | verify s | files hit | records |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 500 | rare literal (rank 12000) | 0.023 | 8 | 564 | 501 | 3.4 | 17.9 | 0.003 | 0.011 | 0.001 | 84 | none |
| 500 | common word (rank 40) | 0.210 | 9 | 6,013 | 501 | 3.4 | 59.1 | 0.003 | 0.066 | 0.008 | 6,264 | none |
| 500 | alternation regex (ranks 2000|2500) | 0.052 | 8 | 1,868 | 501 | 3.4 | 32.2 | 0.003 | 0.025 | 0.002 | 936 | none |
| 500 | case-insensitive word (rank 800) | 0.111 | 9 | 5,096 | 501 | 3.4 | 56.3 | 0.003 | 0.054 | 0.004 | 1,820 | none |
| 500 | matches almost nothing | 0.011 | 6 | 0 | 501 | 3.4 | 3.4 | 0.003 | 0.005 | 0.000 | 0 | none |
| 2,000 | rare literal (rank 12000) | 0.047 | 8 | 491 | 2,001 | 13.4 | 25.9 | 0.011 | 0.026 | 0.002 | 83 | none |
| 2,000 | common word (rank 40) | 0.179 | 9 | 5,078 | 2,001 | 13.4 | 60.6 | 0.011 | 0.067 | 0.010 | 6,256 | none |
| 2,000 | alternation regex (ranks 2000|2500) | 0.072 | 9 | 1,627 | 2,001 | 13.4 | 38.3 | 0.012 | 0.036 | 0.002 | 963 | none |
| 2,000 | case-insensitive word (rank 800) | 0.148 | 9 | 4,275 | 2,001 | 13.4 | 58.1 | 0.011 | 0.060 | 0.005 | 1,819 | none |
| 2,000 | matches almost nothing | 0.036 | 6 | 0 | 2,001 | 13.4 | 13.4 | 0.011 | 0.020 | 0.001 | 0 | none |
| 5,000 | rare literal (rank 12000) | 0.093 | 9 | 306 | 5,001 | 34.1 | 42.3 | 0.030 | 0.050 | 0.002 | 73 | none |
| 5,000 | common word (rank 40) | 0.238 | 9 | 3,153 | 5,001 | 34.1 | 63.7 | 0.029 | 0.081 | 0.010 | 6,226 | none |
| 5,000 | alternation regex (ranks 2000|2500) | 0.118 | 9 | 1,019 | 5,001 | 34.1 | 49.7 | 0.029 | 0.060 | 0.004 | 965 | none |
| 5,000 | case-insensitive word (rank 800) | 0.149 | 9 | 2,653 | 5,001 | 34.1 | 62.2 | 0.028 | 0.076 | 0.005 | 1,811 | none |
| 5,000 | matches almost nothing | 0.085 | 7 | 0 | 5,001 | 34.1 | 34.1 | 0.026 | 0.048 | 0.002 | 0 | none |
| 10,000 | rare literal (rank 12000) | 0.196 | 10 | 0 | 10,001 | 68.8 | 68.8 | 0.055 | 0.099 | 0.004 | 76 | none |
| 10,000 | common word (rank 40) | 0.241 | 10 | 0 | 10,001 | 68.8 | 68.8 | 0.055 | 0.091 | 0.011 | 6,217 | none |
| 10,000 | alternation regex (ranks 2000|2500) | 0.169 | 10 | 0 | 10,001 | 68.8 | 68.8 | 0.053 | 0.092 | 0.005 | 950 | none |
| 10,000 | case-insensitive word (rank 800) | 0.209 | 10 | 0 | 10,001 | 68.8 | 68.8 | 0.054 | 0.095 | 0.006 | 1,843 | none |
| 10,000 | matches almost nothing | 0.172 | 8 | 0 | 10,001 | 68.8 | 68.8 | 0.055 | 0.092 | 0.006 | 0 | none |

### glean at the default overlay budget (500)

| N dirty | budget | query | median wall s | SQL stmts | nominees | bodies | body MB | nominee s | body fetch s | tokenize s | score s | overlay s | overlay hits | hits | records |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 500 | 500 | 2 words (ranks 300, 3000) | 0.097 | 12 | 500 | 500 | 3.4 | 0.003 | 0.004 | 0.068 | 0.000 | 0.078 | 120 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 500 | 500 | 3 words (ranks 40, 1500, 9000) | 0.099 | 12 | 500 | 500 | 3.4 | 0.003 | 0.004 | 0.069 | 0.000 | 0.079 | 313 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 500 | 500 | 4 words (ranks 700, 2000, 5000, 15000) | 0.096 | 12 | 500 | 500 | 3.4 | 0.003 | 0.004 | 0.069 | 0.000 | 0.078 | 68 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 500 | 500 | 2 very common (ranks 5, 12) | 0.107 | 12 | 500 | 500 | 3.4 | 0.004 | 0.005 | 0.070 | 0.000 | 0.079 | 477 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 500 | 500 | 2 rare (ranks 8000, 20000) | 0.087 | 11 | 500 | 500 | 3.4 | 0.003 | 0.004 | 0.069 | 0.000 | 0.078 | 4 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 2,000 | 500 | 2 words (ranks 300, 3000) | 0.098 | 12 | 500 | 500 | 3.3 | 0.004 | 0.005 | 0.069 | 0.000 | 0.079 | 109 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 2,000 | 500 | 3 words (ranks 40, 1500, 9000) | 0.099 | 12 | 500 | 500 | 3.3 | 0.004 | 0.005 | 0.067 | 0.000 | 0.077 | 324 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 2,000 | 500 | 4 words (ranks 700, 2000, 5000, 15000) | 0.095 | 12 | 500 | 500 | 3.3 | 0.004 | 0.005 | 0.068 | 0.000 | 0.077 | 87 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 2,000 | 500 | 2 very common (ranks 5, 12) | 0.102 | 12 | 500 | 500 | 3.3 | 0.004 | 0.005 | 0.067 | 0.000 | 0.076 | 476 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 2,000 | 500 | 2 rare (ranks 8000, 20000) | 0.089 | 11 | 500 | 500 | 3.3 | 0.004 | 0.005 | 0.069 | 0.000 | 0.079 | 10 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 5,000 | 500 | 2 words (ranks 300, 3000) | 0.103 | 12 | 500 | 500 | 3.6 | 0.005 | 0.005 | 0.075 | 0.000 | 0.085 | 115 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 5,000 | 500 | 3 words (ranks 40, 1500, 9000) | 0.102 | 12 | 500 | 500 | 3.6 | 0.004 | 0.005 | 0.073 | 0.000 | 0.083 | 333 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 5,000 | 500 | 4 words (ranks 700, 2000, 5000, 15000) | 0.100 | 12 | 500 | 500 | 3.6 | 0.004 | 0.005 | 0.074 | 0.000 | 0.083 | 78 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 5,000 | 500 | 2 very common (ranks 5, 12) | 0.111 | 12 | 500 | 500 | 3.6 | 0.004 | 0.005 | 0.076 | 0.000 | 0.086 | 469 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 5,000 | 500 | 2 rare (ranks 8000, 20000) | 0.098 | 11 | 500 | 500 | 3.6 | 0.005 | 0.005 | 0.075 | 0.000 | 0.086 | 10 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 10,000 | 500 | 2 words (ranks 300, 3000) | 0.110 | 14 | 500 | 500 | 3.7 | 0.006 | 0.005 | 0.077 | 0.000 | 0.087 | 120 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 10,000 | 500 | 3 words (ranks 40, 1500, 9000) | 0.113 | 14 | 500 | 500 | 3.7 | 0.005 | 0.005 | 0.077 | 0.000 | 0.086 | 332 | 10 | scope probe budget {"window":16000,"found":0} (3/3); overlay budget {"scanned":500,"budget":500} (3/3) |
| 10,000 | 500 | 4 words (ranks 700, 2000, 5000, 15000) | 0.109 | 14 | 500 | 500 | 3.7 | 0.006 | 0.005 | 0.078 | 0.000 | 0.088 | 75 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 10,000 | 500 | 2 very common (ranks 5, 12) | 0.128 | 14 | 500 | 500 | 3.7 | 0.005 | 0.005 | 0.078 | 0.000 | 0.088 | 475 | 10 | scope probe budget {"window":16000,"found":0} (3/3); overlay budget {"scanned":500,"budget":500} (3/3) |
| 10,000 | 500 | 2 rare (ranks 8000, 20000) | 0.102 | 10 | 500 | 500 | 3.7 | 0.005 | 0.005 | 0.078 | 0.000 | 0.087 | 9 | 9 | overlay budget {"scanned":500,"budget":500} (3/3) |

### glean at the lifted overlay budget (25,000)

| N dirty | budget | query | median wall s | SQL stmts | nominees | bodies | body MB | nominee s | body fetch s | tokenize s | score s | overlay s | overlay hits | hits | records |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 500 | 25,000 | 2 words (ranks 300, 3000) | 0.097 | 12 | 501 | 501 | 3.4 | 0.003 | 0.004 | 0.069 | 0.000 | 0.079 | 121 | 10 | none |
| 500 | 25,000 | 3 words (ranks 40, 1500, 9000) | 0.099 | 12 | 501 | 501 | 3.4 | 0.003 | 0.004 | 0.069 | 0.000 | 0.078 | 313 | 10 | none |
| 500 | 25,000 | 4 words (ranks 700, 2000, 5000, 15000) | 0.097 | 12 | 501 | 501 | 3.4 | 0.003 | 0.004 | 0.069 | 0.000 | 0.078 | 68 | 10 | none |
| 500 | 25,000 | 2 very common (ranks 5, 12) | 0.105 | 12 | 501 | 501 | 3.4 | 0.003 | 0.004 | 0.070 | 0.000 | 0.079 | 478 | 10 | none |
| 500 | 25,000 | 2 rare (ranks 8000, 20000) | 0.093 | 11 | 501 | 501 | 3.4 | 0.003 | 0.005 | 0.072 | 0.000 | 0.082 | 4 | 10 | none |
| 2,000 | 25,000 | 2 words (ranks 300, 3000) | 0.336 | 12 | 2,001 | 2,001 | 13.4 | 0.011 | 0.020 | 0.271 | 0.000 | 0.308 | 438 | 10 | none |
| 2,000 | 25,000 | 3 words (ranks 40, 1500, 9000) | 0.342 | 12 | 2,001 | 2,001 | 13.4 | 0.011 | 0.020 | 0.271 | 0.000 | 0.308 | 1,248 | 10 | none |
| 2,000 | 25,000 | 4 words (ranks 700, 2000, 5000, 15000) | 0.340 | 12 | 2,001 | 2,001 | 13.4 | 0.011 | 0.020 | 0.271 | 0.000 | 0.308 | 307 | 10 | none |
| 2,000 | 25,000 | 2 very common (ranks 5, 12) | 0.348 | 12 | 2,001 | 2,001 | 13.4 | 0.011 | 0.020 | 0.272 | 0.000 | 0.311 | 1,899 | 10 | none |
| 2,000 | 25,000 | 2 rare (ranks 8000, 20000) | 0.326 | 11 | 2,001 | 2,001 | 13.4 | 0.011 | 0.020 | 0.270 | 0.000 | 0.307 | 34 | 10 | none |
| 5,000 | 25,000 | 2 words (ranks 300, 3000) | 0.858 | 12 | 5,001 | 5,001 | 34.1 | 0.029 | 0.048 | 0.714 | 0.000 | 0.811 | 1,089 | 10 | none |
| 5,000 | 25,000 | 3 words (ranks 40, 1500, 9000) | 0.872 | 12 | 5,001 | 5,001 | 34.1 | 0.026 | 0.046 | 0.716 | 0.001 | 0.809 | 3,138 | 10 | none |
| 5,000 | 25,000 | 4 words (ranks 700, 2000, 5000, 15000) | 0.897 | 12 | 5,001 | 5,001 | 34.1 | 0.027 | 0.052 | 0.720 | 0.000 | 0.826 | 804 | 10 | none |
| 5,000 | 25,000 | 2 very common (ranks 5, 12) | 0.849 | 12 | 5,001 | 5,001 | 34.1 | 0.028 | 0.048 | 0.693 | 0.001 | 0.788 | 4,712 | 10 | none |
| 5,000 | 25,000 | 2 rare (ranks 8000, 20000) | 0.832 | 11 | 5,001 | 5,001 | 34.1 | 0.029 | 0.047 | 0.698 | 0.000 | 0.791 | 64 | 10 | none |
| 10,000 | 25,000 | 2 words (ranks 300, 3000) | 1.688 | 14 | 10,001 | 10,001 | 68.8 | 0.053 | 0.085 | 1.398 | 0.000 | 1.605 | 2,192 | 10 | none |
| 10,000 | 25,000 | 3 words (ranks 40, 1500, 9000) | 1.713 | 14 | 10,001 | 10,001 | 68.8 | 0.055 | 0.086 | 1.432 | 0.001 | 1.611 | 6,321 | 10 | scope probe budget {"window":16000,"found":0} (3/3) |
| 10,000 | 25,000 | 4 words (ranks 700, 2000, 5000, 15000) | 1.697 | 14 | 10,001 | 10,001 | 68.8 | 0.054 | 0.092 | 1.405 | 0.000 | 1.620 | 1,529 | 10 | none |
| 10,000 | 25,000 | 2 very common (ranks 5, 12) | 1.716 | 14 | 10,001 | 10,001 | 68.8 | 0.055 | 0.086 | 1.417 | 0.002 | 1.607 | 9,461 | 10 | scope probe budget {"window":16000,"found":0} (3/3) |
| 10,000 | 25,000 | 2 rare (ranks 8000, 20000) | 1.669 | 10 | 10,001 | 10,001 | 68.8 | 0.054 | 0.087 | 1.391 | 0.000 | 1.599 | 142 | 10 | none |

### Sentinel recall

| N dirty | not encoded after dirtying | grep finds sentinel | grep wall s | glean@500 finds sentinel | glean@500 record | glean@25000 finds sentinel | glean@25000 record |
|---|---|---|---|---|---|---|---|
| 500 | 501 | True | 0.011 | False | overlay budget {"scanned":500,"budget":500} (1/1) | True | none |
| 2,000 | 2,001 | True | 0.036 | False | overlay budget {"scanned":500,"budget":500} (1/1) | True | none |
| 5,000 | 5,001 | True | 0.086 | False | overlay budget {"scanned":500,"budget":500} (1/1) | True | none |
| 10,000 | 10,001 | True | 0.170 | False | overlay budget {"scanned":500,"budget":500} (1/1) | True | none |

### One pass under the default 10 s wall

| N dirty | verb | call | wall s | SQL stmts | hits | records |
|---|---|---|---|---|---|---|
| 500 | grep | rare literal (rank 12000) | 0.026 | 8 | 84 | none |
| 500 | grep | common word (rank 40) | 0.174 | 9 | 6264 | none |
| 500 | grep | alternation regex (ranks 2000|2500) | 0.051 | 8 | 936 | none |
| 500 | grep | case-insensitive word (rank 800) | 0.108 | 9 | 1820 | none |
| 500 | grep | matches almost nothing | 0.011 | 6 | 0 | none |
| 500 | glean@25000 | 2 words (ranks 300, 3000) | 0.127 | 12 | 10 | none |
| 500 | glean@25000 | 3 words (ranks 40, 1500, 9000) | 0.098 | 12 | 10 | none |
| 500 | glean@25000 | 4 words (ranks 700, 2000, 5000, 15000) | 0.097 | 12 | 10 | none |
| 500 | glean@25000 | 2 very common (ranks 5, 12) | 0.104 | 12 | 10 | none |
| 500 | glean@25000 | 2 rare (ranks 8000, 20000) | 0.088 | 11 | 10 | none |
| 2,000 | grep | rare literal (rank 12000) | 0.052 | 8 | 83 | none |
| 2,000 | grep | common word (rank 40) | 0.226 | 9 | 6256 | none |
| 2,000 | grep | alternation regex (ranks 2000|2500) | 0.071 | 9 | 963 | none |
| 2,000 | grep | case-insensitive word (rank 800) | 0.121 | 9 | 1819 | none |
| 2,000 | grep | matches almost nothing | 0.036 | 6 | 0 | none |
| 2,000 | glean@25000 | 2 words (ranks 300, 3000) | 0.337 | 12 | 10 | none |
| 2,000 | glean@25000 | 3 words (ranks 40, 1500, 9000) | 0.344 | 12 | 10 | none |
| 2,000 | glean@25000 | 4 words (ranks 700, 2000, 5000, 15000) | 0.341 | 12 | 10 | none |
| 2,000 | glean@25000 | 2 very common (ranks 5, 12) | 0.350 | 12 | 10 | none |
| 2,000 | glean@25000 | 2 rare (ranks 8000, 20000) | 0.327 | 11 | 10 | none |
| 5,000 | grep | rare literal (rank 12000) | 0.132 | 9 | 73 | none |
| 5,000 | grep | common word (rank 40) | 0.202 | 9 | 6226 | none |
| 5,000 | grep | alternation regex (ranks 2000|2500) | 0.109 | 9 | 965 | none |
| 5,000 | grep | case-insensitive word (rank 800) | 0.149 | 9 | 1811 | none |
| 5,000 | grep | matches almost nothing | 0.116 | 7 | 0 | none |
| 5,000 | glean@25000 | 2 words (ranks 300, 3000) | 0.825 | 12 | 10 | none |
| 5,000 | glean@25000 | 3 words (ranks 40, 1500, 9000) | 0.837 | 12 | 10 | none |
| 5,000 | glean@25000 | 4 words (ranks 700, 2000, 5000, 15000) | 0.845 | 12 | 10 | none |
| 5,000 | glean@25000 | 2 very common (ranks 5, 12) | 0.911 | 12 | 10 | none |
| 5,000 | glean@25000 | 2 rare (ranks 8000, 20000) | 0.836 | 11 | 10 | none |
| 10,000 | grep | rare literal (rank 12000) | 0.168 | 10 | 76 | none |
| 10,000 | grep | common word (rank 40) | 0.230 | 10 | 6217 | none |
| 10,000 | grep | alternation regex (ranks 2000|2500) | 0.205 | 10 | 950 | none |
| 10,000 | grep | case-insensitive word (rank 800) | 0.178 | 10 | 1843 | none |
| 10,000 | grep | matches almost nothing | 0.163 | 8 | 0 | none |
| 10,000 | glean@25000 | 2 words (ranks 300, 3000) | 1.679 | 14 | 10 | none |
| 10,000 | glean@25000 | 3 words (ranks 40, 1500, 9000) | 1.698 | 14 | 10 | scope probe budget {"window":16000,"found":0} (1/1) |
| 10,000 | glean@25000 | 4 words (ranks 700, 2000, 5000, 15000) | 1.622 | 14 | 10 | none |
| 10,000 | glean@25000 | 2 very common (ranks 5, 12) | 1.837 | 14 | 10 | scope probe budget {"window":16000,"found":0} (1/1) |
| 10,000 | glean@25000 | 2 rare (ranks 8000, 20000) | 1.724 | 10 | 10 | none |

### Level walls

| N | fresh-store copy s | dirty write s | level total s | peak RSS MB |
|---|---|---|---|---|
| 500 | 0.05 | 0.35 | 5.7 | 955.4 |
| 2,000 | 0.05 | 1.2 | 12.0 | 955.4 |
| 5,000 | 0.05 | 3.05 | 25.9 | 965.3 |
| 10,000 | 0.08 | 6.01 | 47.6 | 1019.2 |

## sqlite 100,000 files (results_sqlite_100000.json)

Started 2026-11-09 10:46:55, finished 2026-11-09 10:55:21; Apple M1 Pro, 10 cores, 32 GB; Python 3.13.11; levels [500, 2000, 5000, 10000, 25000].

### Build

| step | wall s | SQL stmts | files | chunks | posting rows | lex posting rows | not encoded | epoch |
|---|---|---|---|---|---|---|---|---|
| write (100000 files, 10,000 per call) | 75.92 | - | - | - | - | - | - | - |
| reindex #0 | 146.5713 | 2604 | 100,000 | 462,963 | 7,480 | 768,707 | 0 | 1 |
Store size 4041.0 MB; peak RSS 4899.7 MB; base build total 222.9 s.

### Suite summary per level

| N dirty | grep: sum of 5 medians s | grep: slowest median s | grep scan bytes MB | glean@500: sum s | glean@500 slowest s | glean@25000: sum s | glean@25000 slowest s | glean@25000 body MB | glean@25000 tokenize s (median query) |
|---|---|---|---|---|---|---|---|---|---|
| 500 | 2.680 | 1.012 | 3.4 | 0.601 | 0.175 | 0.602 | 0.177 | 3.4 | 0.071 |
| 2,000 | 2.854 | 1.009 | 13.9 | 0.678 | 0.199 | 2.073 | 0.495 | 13.9 | 0.286 |
| 5,000 | 3.072 | 0.972 | 34.0 | 0.618 | 0.181 | 4.497 | 0.967 | 34.0 | 0.698 |
| 10,000 | 3.325 | 0.978 | 54.6 | 0.633 | 0.184 | 8.760 | 1.843 | 68.2 | 1.405 |
| 25,000 | 4.102 | 1.021 | 74.7 | 0.664 | 0.191 | 22.0 | 4.555 | 172.4 | 3.585 |

### Per-dirty-entry slopes

| from N | to N | grep: s per dirty entry per call | grep: bytes per dirty entry | glean@25000: s per dirty entry per call | glean@25000: bytes per dirty entry | glean tokenize s per entry |
|---|---|---|---|---|---|---|
| 500 | 2,000 | 23 µs | 4,985 | 196 µs | 6,959 | 143 µs |
| 2,000 | 5,000 | 15 µs | 4,596 | 162 µs | 6,708 | 137 µs |
| 5,000 | 10,000 | 10 µs | 4,230 | 171 µs | 6,835 | 141 µs |
| 10,000 | 25,000 | 10 µs | 3,372 | 177 µs | 6,947 | 145 µs |

### grep per pattern

| N dirty | pattern | median wall s | SQL stmts | index rows | scan rows | scan bytes MB | body bytes fetched MB | nominee s | body fetch s | verify s | files hit | records |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 500 | rare literal (rank 12000) | 0.137 | 12 | 5,849 | 501 | 3.4 | 151.5 | 0.004 | 0.077 | 0.006 | 673 | none |
| 500 | common word (rank 40) | 1.012 | 14 | 24,872 | 128 | 1.0 | 230.6 | 0.002 | 0.483 | 0.040 | 24,732 | candidate budget (3/3) |
| 500 | alternation regex (ranks 2000|2500) | 0.761 | 16 | 18,881 | 501 | 3.4 | 298.9 | 0.004 | 0.497 | 0.021 | 9,120 | none |
| 500 | case-insensitive word (rank 800) | 0.757 | 15 | 24,865 | 135 | 1.0 | 257.5 | 0.002 | 0.463 | 0.062 | 8,498 | candidate budget (3/3) |
| 500 | matches almost nothing | 0.013 | 6 | 0 | 501 | 3.4 | 3.4 | 0.003 | 0.005 | 0.000 | 0 | none |
| 2,000 | rare literal (rank 12000) | 0.198 | 12 | 5,761 | 2,001 | 13.9 | 159.8 | 0.013 | 0.126 | 0.006 | 667 | none |
| 2,000 | common word (rank 40) | 1.009 | 14 | 24,478 | 522 | 4.1 | 229.8 | 0.005 | 0.521 | 0.033 | 24,583 | candidate budget (3/3) |
| 2,000 | alternation regex (ranks 2000|2500) | 0.820 | 17 | 18,577 | 2,001 | 13.9 | 304.6 | 0.013 | 0.526 | 0.023 | 9,122 | none |
| 2,000 | case-insensitive word (rank 800) | 0.754 | 15 | 24,501 | 499 | 4.0 | 256.4 | 0.005 | 0.468 | 0.021 | 8,426 | candidate budget (3/3) |
| 2,000 | matches almost nothing | 0.073 | 6 | 0 | 2,001 | 13.9 | 13.9 | 0.013 | 0.054 | 0.001 | 0 | none |
| 5,000 | rare literal (rank 12000) | 0.368 | 13 | 5,577 | 5,001 | 34.0 | 175.2 | 0.032 | 0.280 | 0.007 | 664 | none |
| 5,000 | common word (rank 40) | 0.972 | 14 | 23,736 | 1,264 | 8.6 | 227.8 | 0.012 | 0.423 | 0.038 | 24,301 | candidate budget (3/3) |
| 5,000 | alternation regex (ranks 2000|2500) | 0.829 | 17 | 18,086 | 5,001 | 34.0 | 316.8 | 0.030 | 0.581 | 0.022 | 9,162 | none |
| 5,000 | case-insensitive word (rank 800) | 0.782 | 15 | 23,797 | 1,203 | 8.1 | 253.4 | 0.012 | 0.524 | 0.019 | 8,307 | candidate budget (3/3) |
| 5,000 | matches almost nothing | 0.121 | 7 | 0 | 5,001 | 34.0 | 34.0 | 0.030 | 0.081 | 0.003 | 0 | none |
| 10,000 | rare literal (rank 12000) | 0.495 | 14 | 5,291 | 10,001 | 68.2 | 202.1 | 0.066 | 0.361 | 0.011 | 686 | none |
| 10,000 | common word (rank 40) | 0.978 | 14 | 22,514 | 2,486 | 16.8 | 224.6 | 0.022 | 0.437 | 0.035 | 23,854 | candidate budget (3/3) |
| 10,000 | alternation regex (ranks 2000|2500) | 0.861 | 17 | 17,015 | 7,985 | 54.6 | 321.3 | 0.053 | 0.559 | 0.025 | 8,924 | candidate budget (3/3) |
| 10,000 | case-insensitive word (rank 800) | 0.745 | 15 | 22,522 | 2,478 | 16.7 | 249.2 | 0.021 | 0.487 | 0.019 | 8,080 | candidate budget (3/3) |
| 10,000 | matches almost nothing | 0.247 | 8 | 0 | 10,001 | 68.2 | 68.2 | 0.065 | 0.163 | 0.005 | 0 | none |
| 25,000 | rare literal (rank 12000) | 0.763 | 15 | 4,368 | 20,632 | 142.8 | 252.0 | 0.151 | 0.499 | 0.015 | 654 | candidate budget (3/3) |
| 25,000 | common word (rank 40) | 1.021 | 14 | 18,747 | 6,253 | 43.6 | 215.3 | 0.053 | 0.419 | 0.072 | 22,513 | candidate budget (3/3) |
| 25,000 | alternation regex (ranks 2000|2500) | 0.915 | 16 | 14,257 | 10,743 | 74.7 | 296.7 | 0.088 | 0.574 | 0.021 | 7,849 | candidate budget (3/3) |
| 25,000 | case-insensitive word (rank 800) | 0.773 | 15 | 18,740 | 6,260 | 43.7 | 236.0 | 0.054 | 0.456 | 0.018 | 7,478 | candidate budget (3/3) |
| 25,000 | matches almost nothing | 0.630 | 11 | 0 | 25,000 | 172.4 | 172.4 | 0.168 | 0.416 | 0.014 | 0 | candidate budget (3/3) |

### glean at the default overlay budget (500)

| N dirty | budget | query | median wall s | SQL stmts | nominees | bodies | body MB | nominee s | body fetch s | tokenize s | score s | overlay s | overlay hits | hits | records |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 500 | 500 | 2 words (ranks 300, 3000) | 0.104 | 12 | 500 | 500 | 3.4 | 0.004 | 0.005 | 0.071 | 0.000 | 0.081 | 105 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 500 | 500 | 3 words (ranks 40, 1500, 9000) | 0.116 | 12 | 500 | 500 | 3.4 | 0.003 | 0.005 | 0.071 | 0.000 | 0.081 | 344 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 500 | 500 | 4 words (ranks 700, 2000, 5000, 15000) | 0.105 | 12 | 500 | 500 | 3.4 | 0.004 | 0.005 | 0.070 | 0.000 | 0.081 | 75 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 500 | 500 | 2 very common (ranks 5, 12) | 0.175 | 12 | 500 | 500 | 3.4 | 0.004 | 0.005 | 0.071 | 0.000 | 0.081 | 473 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 500 | 500 | 2 rare (ranks 8000, 20000) | 0.100 | 12 | 500 | 500 | 3.4 | 0.004 | 0.005 | 0.070 | 0.000 | 0.080 | 10 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 2,000 | 500 | 2 words (ranks 300, 3000) | 0.115 | 12 | 500 | 500 | 4.0 | 0.005 | 0.005 | 0.081 | 0.000 | 0.091 | 114 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 2,000 | 500 | 3 words (ranks 40, 1500, 9000) | 0.128 | 12 | 500 | 500 | 4.0 | 0.005 | 0.005 | 0.082 | 0.000 | 0.093 | 324 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 2,000 | 500 | 4 words (ranks 700, 2000, 5000, 15000) | 0.119 | 12 | 500 | 500 | 4.0 | 0.005 | 0.005 | 0.082 | 0.000 | 0.092 | 88 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 2,000 | 500 | 2 very common (ranks 5, 12) | 0.199 | 12 | 500 | 500 | 4.0 | 0.006 | 0.005 | 0.085 | 0.000 | 0.096 | 470 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 2,000 | 500 | 2 rare (ranks 8000, 20000) | 0.117 | 12 | 500 | 500 | 4.0 | 0.005 | 0.005 | 0.083 | 0.000 | 0.094 | 14 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 5,000 | 500 | 2 words (ranks 300, 3000) | 0.105 | 12 | 500 | 500 | 3.4 | 0.006 | 0.005 | 0.070 | 0.000 | 0.080 | 100 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 5,000 | 500 | 3 words (ranks 40, 1500, 9000) | 0.118 | 12 | 500 | 500 | 3.4 | 0.006 | 0.005 | 0.070 | 0.000 | 0.081 | 304 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 5,000 | 500 | 4 words (ranks 700, 2000, 5000, 15000) | 0.109 | 12 | 500 | 500 | 3.4 | 0.006 | 0.005 | 0.070 | 0.000 | 0.081 | 83 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 5,000 | 500 | 2 very common (ranks 5, 12) | 0.181 | 12 | 500 | 500 | 3.4 | 0.007 | 0.005 | 0.070 | 0.000 | 0.080 | 466 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 5,000 | 500 | 2 rare (ranks 8000, 20000) | 0.104 | 12 | 500 | 500 | 3.4 | 0.007 | 0.005 | 0.071 | 0.000 | 0.080 | 10 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 10,000 | 500 | 2 words (ranks 300, 3000) | 0.109 | 12 | 500 | 500 | 3.6 | 0.009 | 0.005 | 0.073 | 0.000 | 0.083 | 112 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 10,000 | 500 | 3 words (ranks 40, 1500, 9000) | 0.121 | 12 | 500 | 500 | 3.6 | 0.009 | 0.005 | 0.073 | 0.000 | 0.083 | 321 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 10,000 | 500 | 4 words (ranks 700, 2000, 5000, 15000) | 0.111 | 12 | 500 | 500 | 3.6 | 0.008 | 0.005 | 0.073 | 0.000 | 0.083 | 81 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 10,000 | 500 | 2 very common (ranks 5, 12) | 0.184 | 12 | 500 | 500 | 3.6 | 0.009 | 0.005 | 0.074 | 0.000 | 0.084 | 477 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 10,000 | 500 | 2 rare (ranks 8000, 20000) | 0.108 | 12 | 500 | 500 | 3.6 | 0.008 | 0.005 | 0.072 | 0.000 | 0.082 | 6 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 25,000 | 500 | 2 words (ranks 300, 3000) | 0.118 | 12 | 500 | 500 | 3.5 | 0.014 | 0.005 | 0.074 | 0.000 | 0.085 | 118 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 25,000 | 500 | 3 words (ranks 40, 1500, 9000) | 0.128 | 12 | 500 | 500 | 3.5 | 0.013 | 0.005 | 0.073 | 0.000 | 0.083 | 316 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 25,000 | 500 | 4 words (ranks 700, 2000, 5000, 15000) | 0.115 | 12 | 500 | 500 | 3.5 | 0.014 | 0.005 | 0.072 | 0.000 | 0.083 | 62 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 25,000 | 500 | 2 very common (ranks 5, 12) | 0.191 | 12 | 500 | 500 | 3.5 | 0.014 | 0.005 | 0.072 | 0.000 | 0.083 | 475 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |
| 25,000 | 500 | 2 rare (ranks 8000, 20000) | 0.113 | 12 | 500 | 500 | 3.5 | 0.013 | 0.005 | 0.073 | 0.000 | 0.084 | 12 | 10 | overlay budget {"scanned":500,"budget":500} (3/3) |

### glean at the lifted overlay budget (25,000)

| N dirty | budget | query | median wall s | SQL stmts | nominees | bodies | body MB | nominee s | body fetch s | tokenize s | score s | overlay s | overlay hits | hits | records |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 500 | 25,000 | 2 words (ranks 300, 3000) | 0.103 | 12 | 501 | 501 | 3.4 | 0.003 | 0.005 | 0.072 | 0.000 | 0.082 | 106 | 10 | none |
| 500 | 25,000 | 3 words (ranks 40, 1500, 9000) | 0.116 | 12 | 501 | 501 | 3.4 | 0.004 | 0.005 | 0.072 | 0.000 | 0.082 | 344 | 10 | none |
| 500 | 25,000 | 4 words (ranks 700, 2000, 5000, 15000) | 0.106 | 12 | 501 | 501 | 3.4 | 0.004 | 0.005 | 0.071 | 0.000 | 0.082 | 75 | 10 | none |
| 500 | 25,000 | 2 very common (ranks 5, 12) | 0.177 | 12 | 501 | 501 | 3.4 | 0.004 | 0.005 | 0.071 | 0.000 | 0.081 | 474 | 10 | none |
| 500 | 25,000 | 2 rare (ranks 8000, 20000) | 0.101 | 12 | 501 | 501 | 3.4 | 0.004 | 0.005 | 0.071 | 0.000 | 0.081 | 10 | 10 | none |
| 2,000 | 25,000 | 2 words (ranks 300, 3000) | 0.393 | 12 | 2,001 | 2,001 | 13.9 | 0.012 | 0.053 | 0.289 | 0.000 | 0.359 | 441 | 10 | none |
| 2,000 | 25,000 | 3 words (ranks 40, 1500, 9000) | 0.405 | 12 | 2,001 | 2,001 | 13.9 | 0.012 | 0.053 | 0.288 | 0.000 | 0.359 | 1,252 | 10 | none |
| 2,000 | 25,000 | 4 words (ranks 700, 2000, 5000, 15000) | 0.389 | 12 | 2,001 | 2,001 | 13.9 | 0.012 | 0.052 | 0.285 | 0.000 | 0.356 | 296 | 10 | none |
| 2,000 | 25,000 | 2 very common (ranks 5, 12) | 0.495 | 12 | 2,001 | 2,001 | 13.9 | 0.012 | 0.053 | 0.286 | 0.000 | 0.360 | 1,873 | 10 | none |
| 2,000 | 25,000 | 2 rare (ranks 8000, 20000) | 0.391 | 12 | 2,001 | 2,001 | 13.9 | 0.012 | 0.053 | 0.285 | 0.000 | 0.358 | 34 | 10 | none |
| 5,000 | 25,000 | 2 words (ranks 300, 3000) | 0.883 | 12 | 5,001 | 5,001 | 34.0 | 0.030 | 0.081 | 0.700 | 0.000 | 0.827 | 1,098 | 10 | none |
| 5,000 | 25,000 | 3 words (ranks 40, 1500, 9000) | 0.896 | 12 | 5,001 | 5,001 | 34.0 | 0.029 | 0.080 | 0.698 | 0.001 | 0.827 | 3,149 | 10 | none |
| 5,000 | 25,000 | 4 words (ranks 700, 2000, 5000, 15000) | 0.880 | 12 | 5,001 | 5,001 | 34.0 | 0.029 | 0.080 | 0.698 | 0.000 | 0.825 | 747 | 10 | none |
| 5,000 | 25,000 | 2 very common (ranks 5, 12) | 0.967 | 12 | 5,001 | 5,001 | 34.0 | 0.029 | 0.079 | 0.703 | 0.001 | 0.832 | 4,706 | 10 | none |
| 5,000 | 25,000 | 2 rare (ranks 8000, 20000) | 0.871 | 12 | 5,001 | 5,001 | 34.0 | 0.030 | 0.080 | 0.696 | 0.000 | 0.821 | 68 | 10 | none |
| 10,000 | 25,000 | 2 words (ranks 300, 3000) | 1.711 | 12 | 10,001 | 10,001 | 68.2 | 0.062 | 0.123 | 1.397 | 0.000 | 1.615 | 2,198 | 10 | none |
| 10,000 | 25,000 | 3 words (ranks 40, 1500, 9000) | 1.777 | 12 | 10,001 | 10,001 | 68.2 | 0.063 | 0.127 | 1.411 | 0.001 | 1.644 | 6,297 | 10 | none |
| 10,000 | 25,000 | 4 words (ranks 700, 2000, 5000, 15000) | 1.716 | 12 | 10,001 | 10,001 | 68.2 | 0.065 | 0.123 | 1.405 | 0.000 | 1.622 | 1,474 | 10 | none |
| 10,000 | 25,000 | 2 very common (ranks 5, 12) | 1.843 | 12 | 10,001 | 10,001 | 68.2 | 0.062 | 0.123 | 1.410 | 0.002 | 1.634 | 9,402 | 10 | none |
| 10,000 | 25,000 | 2 rare (ranks 8000, 20000) | 1.713 | 12 | 10,001 | 10,001 | 68.2 | 0.064 | 0.123 | 1.403 | 0.000 | 1.623 | 145 | 10 | none |
| 25,000 | 25,000 | 2 words (ranks 300, 3000) | 4.356 | 12 | 25,000 | 25,000 | 172.4 | 0.172 | 0.311 | 3.571 | 0.001 | 4.130 | 5,536 | 10 | overlay budget {"scanned":25000,"budget":25000} (3/3) |
| 25,000 | 25,000 | 3 words (ranks 40, 1500, 9000) | 4.424 | 12 | 25,000 | 25,000 | 172.4 | 0.169 | 0.313 | 3.595 | 0.003 | 4.151 | 15,811 | 10 | overlay budget {"scanned":25000,"budget":25000} (3/3) |
| 25,000 | 25,000 | 4 words (ranks 700, 2000, 5000, 15000) | 4.361 | 12 | 25,000 | 25,000 | 172.4 | 0.174 | 0.267 | 3.585 | 0.001 | 4.132 | 3,742 | 10 | overlay budget {"scanned":25000,"budget":25000} (3/3) |
| 25,000 | 25,000 | 2 very common (ranks 5, 12) | 4.555 | 12 | 25,000 | 25,000 | 172.4 | 0.174 | 0.262 | 3.611 | 0.004 | 4.170 | 23,602 | 10 | overlay budget {"scanned":25000,"budget":25000} (3/3) |
| 25,000 | 25,000 | 2 rare (ranks 8000, 20000) | 4.316 | 12 | 25,000 | 25,000 | 172.4 | 0.171 | 0.310 | 3.559 | 0.000 | 4.106 | 416 | 10 | overlay budget {"scanned":25000,"budget":25000} (3/3) |

### Sentinel recall

| N dirty | not encoded after dirtying | grep finds sentinel | grep wall s | glean@500 finds sentinel | glean@500 record | glean@25000 finds sentinel | glean@25000 record |
|---|---|---|---|---|---|---|---|
| 500 | 501 | True | 0.013 | False | overlay budget {"scanned":500,"budget":500} (1/1) | True | none |
| 2,000 | 2,001 | True | 0.071 | False | overlay budget {"scanned":500,"budget":500} (1/1) | True | none |
| 5,000 | 5,001 | True | 0.149 | False | overlay budget {"scanned":500,"budget":500} (1/1) | True | none |
| 10,000 | 10,001 | True | 0.275 | False | overlay budget {"scanned":500,"budget":500} (1/1) | True | none |
| 25,000 | 25,001 | False | 0.638 | False | overlay budget {"scanned":500,"budget":500} (1/1) | False | overlay budget {"scanned":25000,"budget":25000} (1/1) |

### One pass under the default 10 s wall

| N dirty | verb | call | wall s | SQL stmts | hits | records |
|---|---|---|---|---|---|---|
| 500 | grep | rare literal (rank 12000) | 0.173 | 12 | 673 | none |
| 500 | grep | common word (rank 40) | 1.025 | 14 | 24732 | candidate budget (1/1) |
| 500 | grep | alternation regex (ranks 2000|2500) | 0.732 | 16 | 9120 | none |
| 500 | grep | case-insensitive word (rank 800) | 0.753 | 15 | 8498 | candidate budget (1/1) |
| 500 | grep | matches almost nothing | 0.012 | 6 | 0 | none |
| 500 | glean@25000 | 2 words (ranks 300, 3000) | 0.107 | 12 | 10 | none |
| 500 | glean@25000 | 3 words (ranks 40, 1500, 9000) | 0.118 | 12 | 10 | none |
| 500 | glean@25000 | 4 words (ranks 700, 2000, 5000, 15000) | 0.104 | 12 | 10 | none |
| 500 | glean@25000 | 2 very common (ranks 5, 12) | 0.180 | 12 | 10 | none |
| 500 | glean@25000 | 2 rare (ranks 8000, 20000) | 0.101 | 12 | 10 | none |
| 2,000 | grep | rare literal (rank 12000) | 0.229 | 12 | 667 | none |
| 2,000 | grep | common word (rank 40) | 0.995 | 14 | 24583 | candidate budget (1/1) |
| 2,000 | grep | alternation regex (ranks 2000|2500) | 0.791 | 17 | 9122 | none |
| 2,000 | grep | case-insensitive word (rank 800) | 0.758 | 15 | 8426 | candidate budget (1/1) |
| 2,000 | grep | matches almost nothing | 0.071 | 6 | 0 | none |
| 2,000 | glean@25000 | 2 words (ranks 300, 3000) | 0.391 | 12 | 10 | none |
| 2,000 | glean@25000 | 3 words (ranks 40, 1500, 9000) | 0.405 | 12 | 10 | none |
| 2,000 | glean@25000 | 4 words (ranks 700, 2000, 5000, 15000) | 0.395 | 12 | 10 | none |
| 2,000 | glean@25000 | 2 very common (ranks 5, 12) | 0.468 | 12 | 10 | none |
| 2,000 | glean@25000 | 2 rare (ranks 8000, 20000) | 0.382 | 12 | 10 | none |
| 5,000 | grep | rare literal (rank 12000) | 0.403 | 13 | 664 | none |
| 5,000 | grep | common word (rank 40) | 1.006 | 14 | 24301 | candidate budget (1/1) |
| 5,000 | grep | alternation regex (ranks 2000|2500) | 0.822 | 17 | 9162 | none |
| 5,000 | grep | case-insensitive word (rank 800) | 0.764 | 15 | 8307 | candidate budget (1/1) |
| 5,000 | grep | matches almost nothing | 0.120 | 7 | 0 | none |
| 5,000 | glean@25000 | 2 words (ranks 300, 3000) | 0.888 | 12 | 10 | none |
| 5,000 | glean@25000 | 3 words (ranks 40, 1500, 9000) | 0.921 | 12 | 10 | none |
| 5,000 | glean@25000 | 4 words (ranks 700, 2000, 5000, 15000) | 0.894 | 12 | 10 | none |
| 5,000 | glean@25000 | 2 very common (ranks 5, 12) | 1.000 | 12 | 10 | none |
| 5,000 | glean@25000 | 2 rare (ranks 8000, 20000) | 0.888 | 12 | 10 | none |
| 10,000 | grep | rare literal (rank 12000) | 0.535 | 14 | 686 | none |
| 10,000 | grep | common word (rank 40) | 1.017 | 14 | 23854 | candidate budget (1/1) |
| 10,000 | grep | alternation regex (ranks 2000|2500) | 0.896 | 17 | 8924 | candidate budget (1/1) |
| 10,000 | grep | case-insensitive word (rank 800) | 0.767 | 15 | 8080 | candidate budget (1/1) |
| 10,000 | grep | matches almost nothing | 0.251 | 8 | 0 | none |
| 10,000 | glean@25000 | 2 words (ranks 300, 3000) | 1.785 | 12 | 10 | none |
| 10,000 | glean@25000 | 3 words (ranks 40, 1500, 9000) | 1.790 | 12 | 10 | none |
| 10,000 | glean@25000 | 4 words (ranks 700, 2000, 5000, 15000) | 1.769 | 12 | 10 | none |
| 10,000 | glean@25000 | 2 very common (ranks 5, 12) | 1.845 | 12 | 10 | none |
| 10,000 | glean@25000 | 2 rare (ranks 8000, 20000) | 1.783 | 12 | 10 | none |
| 25,000 | grep | rare literal (rank 12000) | 0.772 | 15 | 654 | candidate budget (1/1) |
| 25,000 | grep | common word (rank 40) | 0.981 | 14 | 22513 | candidate budget (1/1) |
| 25,000 | grep | alternation regex (ranks 2000|2500) | 0.902 | 16 | 7849 | candidate budget (1/1) |
| 25,000 | grep | case-insensitive word (rank 800) | 0.782 | 15 | 7478 | candidate budget (1/1) |
| 25,000 | grep | matches almost nothing | 0.661 | 11 | 0 | candidate budget (1/1) |
| 25,000 | glean@25000 | 2 words (ranks 300, 3000) | 4.325 | 12 | 10 | overlay budget {"scanned":25000,"budget":25000} (1/1) |
| 25,000 | glean@25000 | 3 words (ranks 40, 1500, 9000) | 4.321 | 12 | 10 | overlay budget {"scanned":25000,"budget":25000} (1/1) |
| 25,000 | glean@25000 | 4 words (ranks 700, 2000, 5000, 15000) | 4.305 | 12 | 10 | overlay budget {"scanned":25000,"budget":25000} (1/1) |
| 25,000 | glean@25000 | 2 very common (ranks 5, 12) | 4.459 | 12 | 10 | overlay budget {"scanned":25000,"budget":25000} (1/1) |
| 25,000 | glean@25000 | 2 rare (ranks 8000, 20000) | 4.191 | 12 | 10 | overlay budget {"scanned":25000,"budget":25000} (1/1) |

### Level walls

| N | fresh-store copy s | dirty write s | level total s | peak RSS MB |
|---|---|---|---|---|
| 500 | 0.5 | 0.85 | 19.4 | 5161.0 |
| 2,000 | 0.46 | 2.2 | 27.3 | 5165.0 |
| 5,000 | 0.45 | 5.54 | 40.4 | 5165.0 |
| 10,000 | 0.47 | 9.69 | 63.9 | 5165.0 |
| 25,000 | 0.53 | 19.34 | 132.1 | 5165.0 |
