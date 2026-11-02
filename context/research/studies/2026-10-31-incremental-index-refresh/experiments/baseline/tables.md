## A. Full reindex

| files | step | wall s | chunk s | gram build s | lexical build s | publish+reclaim s | SQL stmts | executemany rows | posting rows | posting MB | lex_postings rows | lex blob MB | lex_docs rows | chunk rows | db MB | WAL MB | peak RSS MB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 10000 | cold build | 13.489 | 8.654 | 0.47 | 3.615 | 0.08 | 278 | 187073 | 7142 | 21.11 | 78999 | 34.29 | 42476 | 42476 | 251.6 | 83.7 | 1050.9 |
| 10000 | no-op (nothing dirty) | 0.483 | 0.003 | 0.0 | 0 | 0 | 24 | 0 | 7142 | 21.11 | 78999 | 34.29 | 42476 | 42476 | 251.6 | 83.7 | 1051.0 |
| 50000 | cold build | 135.958 | 59.158 | 4.98 | 64.365 | 0.48 | 1225 | 874723 | 7142 | 105.89 | 384003 | 172.36 | 213799 | 213799 | 1247.2 | 420.4 | 2820.3 |
| 50000 | no-op (nothing dirty) | 3.758 | 0.032 | 0.01 | 0 | 0 | 24 | 0 | 7142 | 105.89 | 384003 | 172.36 | 213799 | 213799 | 1247.2 | 420.4 | 2820.3 |

## B. Dirty rebuild vs cold

| files | step | dirty before | entry rows | wall s | wall / cold | chunk s | build_epoch s (gram+lex) | build / cold build | SQL stmts | executemany rows | posting rows | lex_postings rows | epoch |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 10000 | cold (all dirty) | 10000 | 10205 | 13.489 | 1.00 | 8.654 | 4.084 | 1.00 | 278 | 187073 | 7142 | 78999 | 1 |
| 10000 | 2,000 new entries dirty | 0 | 12212 | 8.224 | 0.61 | 1.807 | 5.45 | 1.33 | 316 | 174846 | 7143 | 91961 | 2 |
| 10000 | 5% rewritten + 1,501 new | 0 | 13719 | 10.689 | 0.79 | 2.401 | 6.519 | 1.60 | 351 | 191896 | 7166 | 102357 | 3 |
| 10000 | 1% rewritten | 0 | 13719 | 12.906 | 0.96 | 0.158 | 10.522 | 2.58 | 350 | 183615 | 7168 | 102334 | 4 |
| 50000 | cold (all dirty) | 50000 | 51021 | 135.958 | 1.00 | 59.158 | 69.341 | 1.00 | 1225 | 874723 | 7142 | 384003 | 1 |
| 50000 | 2,000 new entries dirty | 0 | 53028 | 126.643 | 0.93 | 5.847 | 115.086 | 1.66 | 1221 | 691595 | 7143 | 397387 | 2 |
| 50000 | 5% rewritten + 1,501 new | 0 | 54535 | 127.548 | 0.94 | 11.812 | 109.992 | 1.59 | 1257 | 716596 | 7166 | 407359 | 3 |
| 50000 | 1% rewritten | 0 | 54535 | 168.926 | 1.24 | 0.586 | 130.465 | 1.88 | 1256 | 701770 | 7168 | 407435 | 4 |

## C. grep under staleness

10000 files (T = a truncation record was returned):

| pattern | clean wall s / stmts / files | dirty 0.1% (10) wall s / stmts / files | dirty 0.5% (50) wall s / stmts / files | dirty 1.0% (100) wall s / stmts / files | dirty 2.0% (200) wall s / stmts / files | dirty 5.0% (500) wall s / stmts / files |
|---|---|---|---|---|---|---|
| rare word (rank 4992) | 0.015 / 7 / 267 | 0.017 / 8 / 317 | 0.02 / 8 / 318 | 0.018 / 8 / 317 | 0.12 / 8 / 315 | 0.105 / 8 / 321 |
| rare word (rank 4874) | 0.016 / 7 / 243 | 0.02 / 8 / 311 | 0.024 / 8 / 311 | 0.022 / 8 / 308 | 0.192 / 8 / 302 | 0.105 / 8 / 299 |
| rare word (rank 4725) | 0.069 / 7 / 264 | 0.049 / 8 / 316 | 0.098 / 8 / 318 | 0.056 / 8 / 319 | 0.232 / 8 / 318 | 0.196 / 8 / 312 |
| mid word (rank 1500) | 0.088 / 8 / 778 | 0.114 / 9 / 920 | 0.12 / 9 / 923 | 0.115 / 9 / 923 | 0.489 / 9 / 927 | 0.282 / 9 / 934 |
| mid word (rank 400) | 0.063 / 7 / 2369 | 0.085 / 8 / 2842 | 0.086 / 8 / 2840 | 0.083 / 8 / 2840 | 0.239 / 8 / 2842 | 0.373 / 8 / 2831 |
| identifier literal | 0.024 / 7 / 736 | 0.034 / 8 / 916 | 0.044 / 8 / 918 | 0.042 / 8 / 922 | 0.134 / 8 / 926 | 0.086 / 8 / 936 |
| identifier literal 2 | 0.024 / 7 / 756 | 0.067 / 8 / 893 | 0.031 / 8 / 892 | 0.033 / 8 / 892 | 0.096 / 8 / 888 | 0.274 / 8 / 894 |
| 3-letter common word | 0.552 / 8 / 9926 | 0.752 / 10 / 11911 | 0.683 / 10 / 11911 | 0.836 / 10 / 11913 | 1.535 / 10 / 11914 | 1.756 / 10 / 11917 |
| regex, literal core | 0.057 / 7 / 767 | 0.076 / 8 / 911 | 0.069 / 8 / 914 | 0.082 / 8 / 917 | 0.258 / 8 / 915 | 0.349 / 8 / 909 |
| regex, literal core 2 | 0.123 / 8 / 4155 | 0.154 / 9 / 5006 | 0.192 / 9 / 5005 | 0.183 / 9 / 5007 | 0.473 / 9 / 5017 | 0.478 / 9 / 4999 |
| TOTAL wall s | 1.03 | 1.37 | 1.37 | 1.47 | 3.77 | 4.00 |

50000 files (T = a truncation record was returned):

| pattern | clean wall s / stmts / files | dirty 0.1% (50) wall s / stmts / files | dirty 0.5% (250) wall s / stmts / files | dirty 1.0% (500) wall s / stmts / files | dirty 2.0% (1000) wall s / stmts / files | dirty 5.0% (2500) wall s / stmts / files |
|---|---|---|---|---|---|---|
| rare word (rank 4992) | 0.067 / 7 / 1331 | 0.135 / 8 / 1382 | 0.172 / 8 / 1378 | 0.813 / 8 / 1379 | 0.841 / 8 / 1376 | 0.176 / 8 / 1384 |
| rare word (rank 4874) | 0.12 / 7 / 1353 | 0.17 / 8 / 1420 | 0.204 / 8 / 1424 | 0.608 / 8 / 1419 | 0.729 / 8 / 1419 | 0.555 / 9 / 1417 |
| rare word (rank 4725) | 0.225 / 9 / 1271 | 0.612 / 10 / 1326 | 0.543 / 10 / 1323 | 1.275 / 10 / 1326 | 1.701 / 10 / 1330 | 1.715 / 10 / 1314 |
| mid word (rank 1500) | 0.895 / 12 / 3898 | 1.144 / 13 / 4043 | 1.259 / 13 / 4054 | 3.01 / 13 / 4053 | 4.01 / 13 / 4060 | 3.179 / 13 / 4071 |
| mid word (rank 400) | 0.788 / 9 / 11818 | 0.851 / 10 / 12286 | 0.974 / 10 / 12288 | 2.29 / 10 / 12277 | 3.101 / 11 / 12281 | 1.759 / 11 / 12282 |
| identifier literal | 0.25 / 7 / 3840 | 0.225 / 8 / 4023 | 0.314 / 8 / 4018 | 1.248 / 9 / 4021 | 1.21 / 9 / 4015 | 1.028 / 9 / 4028 |
| identifier literal 2 | 0.321 / 7 / 3923 | 0.177 / 8 / 4062 | 0.485 / 9 / 4064 | 1.059 / 9 / 4054 | 1.012 / 9 / 4056 | 0.598 / 9 / 4053 |
| 3-letter common word | 6.73 / 11 / 25000 T | 2.466 / 12 / 25000 T | 2.909 / 12 / 25000 T | 8.299 / 12 / 25000 T | 11.385 / 12 / 24999 T | 11.874 / 12 / 24990 T |
| regex, literal core | 1.206 / 10 / 3926 | 0.993 / 11 / 4074 | 1.096 / 11 / 4080 | 1.645 / 11 / 4075 | 0.572 / 11 / 4092 | 1.919 / 11 / 4102 |
| regex, literal core 2 | 2.822 / 12 / 20189 T | 1.244 / 13 / 20180 T | 1.894 / 13 / 20141 T | 4.013 / 13 / 20102 T | 1.952 / 13 / 19997 T | 4.069 / 13 / 19691 T |
| TOTAL wall s | 13.42 | 8.02 | 9.85 | 24.26 | 26.51 | 26.87 |

Truncation records:

| state | pattern | record |
|---|---|---|
| clean | 3-letter common word | truncated: Truncated: at the candidate budget, with the unindexed overlay not consulted; narrow the pattern, add globs or ext filters, or scope with paths |
| clean | regex, literal core 2 | truncated: Truncated: at the candidate budget, with the unindexed overlay not consulted; narrow the pattern, add globs or ext filters, or scope with paths |
| dirty 0.1% (50) | 3-letter common word | truncated: Truncated: at the candidate budget; narrow the pattern, add globs or ext filters, or scope with paths |
| dirty 0.1% (50) | regex, literal core 2 | truncated: Truncated: at the candidate budget; narrow the pattern, add globs or ext filters, or scope with paths |
| dirty 0.5% (250) | 3-letter common word | truncated: Truncated: at the candidate budget; narrow the pattern, add globs or ext filters, or scope with paths |
| dirty 0.5% (250) | regex, literal core 2 | truncated: Truncated: at the candidate budget; narrow the pattern, add globs or ext filters, or scope with paths |
| dirty 1.0% (500) | 3-letter common word | truncated: Truncated: at the candidate budget; narrow the pattern, add globs or ext filters, or scope with paths |
| dirty 1.0% (500) | regex, literal core 2 | truncated: Truncated: at the candidate budget; narrow the pattern, add globs or ext filters, or scope with paths |
| dirty 2.0% (1000) | 3-letter common word | truncated: Truncated: at the candidate budget; narrow the pattern, add globs or ext filters, or scope with paths |
| dirty 2.0% (1000) | regex, literal core 2 | truncated: Truncated: at the candidate budget; narrow the pattern, add globs or ext filters, or scope with paths |
| dirty 5.0% (2500) | 3-letter common word | truncated: Truncated: at the candidate budget; narrow the pattern, add globs or ext filters, or scope with paths |
| dirty 5.0% (2500) | regex, literal core 2 | truncated: Truncated: at the candidate budget; narrow the pattern, add globs or ext filters, or scope with paths |

## D. glean under staleness

10000 files (T = an overlay-budget record was returned):

| query | clean wall s / stmts | dirty 0.1% (10) wall s / stmts | dirty 0.5% (50) wall s / stmts | dirty 1.0% (100) wall s / stmts | dirty 2.0% (200) wall s / stmts | dirty 5.0% (500) wall s / stmts |
|---|---|---|---|---|---|---|
| gakicato deertepo | 0.016 / 8 | 0.039 / 11 | 0.028 / 11 | 0.047 / 11 | 0.127 / 11 | 0.175 / 11 T |
| mulefe arse ouspe | 0.016 / 8 | 0.025 / 12 | 0.029 / 12 | 0.139 / 12 | 0.176 / 12 | 0.246 / 12 T |
| bish ousar suca | 0.02 / 9 | 0.028 / 12 | 0.032 / 12 | 0.218 / 12 | 0.151 / 12 | 0.241 / 12 T |
| hiousment vien pilaza gakifa | 0.018 / 9 | 0.027 / 12 | 0.036 / 12 | 0.199 / 12 | 0.131 / 12 | 0.207 / 12 T |
| Buffer::score_1d27 sihete | 0.022 / 9 | 0.033 / 12 | 0.04 / 12 | 0.235 / 12 | 0.199 / 12 | 0.209 / 12 T |
| TOTAL wall s | 0.09 | 0.15 | 0.17 | 0.84 | 0.78 | 1.08 |

Overlay-budget records (one example per state):

| state | record |
|---|---|
| dirty 5.0% (500) | truncated: Truncated: at the overlay budget; narrow the query, add globs or ext filters, or scope with paths {'scanned': 500, 'budget': 500} |

Freshness of a never-reindexed file at the last path (10000 files):

| state | dirty files | grep finds it | grep wall s | glean ranks it | glean wall s | glean record |
|---|---|---|---|---|---|---|
| dirty 0.1% (10) | 11 | True | 0.005 | True | 0.007 | - |
| dirty 0.5% (50) | 51 | True | 0.005 | True | 0.016 | - |
| dirty 1.0% (100) | 101 | True | 0.084 | True | 0.091 | - |
| dirty 2.0% (200) | 201 | True | 0.046 | True | 0.12 | - |
| dirty 5.0% (500) | 501 | True | 0.075 | False | 0.129 | truncated: Truncated: at the overlay budget; narrow the query, add globs or ext filters, or scope with paths {'scanned': 500, 'budget': 500} |

50000 files (T = an overlay-budget record was returned):

| query | clean wall s / stmts | dirty 0.1% (50) wall s / stmts | dirty 0.5% (250) wall s / stmts | dirty 1.0% (500) wall s / stmts | dirty 2.0% (1000) wall s / stmts | dirty 5.0% (2500) wall s / stmts |
|---|---|---|---|---|---|---|
| gakicato deertepo | 0.219 / 9 | 0.163 / 12 | 0.259 / 12 | 0.379 / 12 T | 0.229 / 12 T | 0.784 / 12 T |
| mulefe arse ouspe | 0.177 / 9 | 0.112 / 12 | 0.42 / 12 | 0.541 / 12 T | 0.651 / 12 T | 0.274 / 12 T |
| bish ousar suca | 0.133 / 9 | 0.102 / 12 | 0.175 / 12 | 0.784 / 12 T | 0.48 / 12 T | 0.366 / 12 T |
| hiousment vien pilaza gakifa | 0.165 / 9 | 0.107 / 12 | 0.446 / 12 | 0.826 / 12 T | 0.29 / 12 T | 0.528 / 12 T |
| Buffer::score_1d27 sihete | 0.194 / 9 | 0.166 / 12 | 0.396 / 12 | 0.473 / 12 T | 0.493 / 12 T | 0.252 / 12 T |
| TOTAL wall s | 0.89 | 0.65 | 1.70 | 3.00 | 2.14 | 2.20 |

Overlay-budget records (one example per state):

| state | record |
|---|---|
| dirty 1.0% (500) | truncated: Truncated: at the overlay budget; narrow the query, add globs or ext filters, or scope with paths {'scanned': 500, 'budget': 500} |
| dirty 2.0% (1000) | truncated: Truncated: at the overlay budget; narrow the query, add globs or ext filters, or scope with paths {'scanned': 500, 'budget': 500} |
| dirty 5.0% (2500) | truncated: Truncated: at the overlay budget; narrow the query, add globs or ext filters, or scope with paths {'scanned': 500, 'budget': 500} |

Freshness of a never-reindexed file at the last path (50000 files):

| state | dirty files | grep finds it | grep wall s | glean ranks it | glean wall s | glean record |
|---|---|---|---|---|---|---|
| dirty 0.1% (50) | 51 | True | 0.073 | True | 0.119 | - |
| dirty 0.5% (250) | 251 | True | 0.065 | True | 0.219 | - |
| dirty 1.0% (500) | 501 | True | 0.157 | False | 0.825 | truncated: Truncated: at the overlay budget; narrow the query, add globs or ext filters, or scope with paths {'scanned': 500, 'budget': 500} |
| dirty 2.0% (1000) | 1001 | True | 0.109 | False | 0.621 | truncated: Truncated: at the overlay budget; narrow the query, add globs or ext filters, or scope with paths {'scanned': 500, 'budget': 500} |
| dirty 5.0% (2500) | 2501 | True | 0.273 | False | 0.31 | truncated: Truncated: at the overlay budget; narrow the query, add globs or ext filters, or scope with paths {'scanned': 500, 'budget': 500} |

## E. Write latency

| files | store state | rep | write(500) wall s | SQL stmts |
|---|---|---|---|---|
| 10000 | clean | 0 | 0.203 | 16 |
| 10000 | clean | 1 | 0.155 | 13 |
| 10000 | clean | 2 | 0.158 | 13 |
| 10000 | 5% dirty | 0 | 0.537 | 16 |
| 10000 | 5% dirty | 1 | 0.263 | 13 |
| 10000 | 5% dirty | 2 | 0.238 | 13 |
| 50000 | clean | 0 | 1.417 | 16 |
| 50000 | clean | 1 | 1.06 | 13 |
| 50000 | clean | 2 | 1.309 | 13 |
| 50000 | 5% dirty | 0 | 1.004 | 16 |
| 50000 | 5% dirty | 1 | 1.38 | 13 |
| 50000 | 5% dirty | 2 | 1.327 | 13 |

## F. Builder-only cost

| docs | content MB | chunks | chunk split s | gram build+drain s | gram rows | gram blob MB | lexical build+drain s | lex_df rows | lex block rows | lex blob MB | total CPU s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 100 | 0.62 | 405 | 0.027 | 0.01 | 6109 | 0.21 | 0.022 | 6201 | 6333 | 0.39 | 0.06 |
| 500 | 3.27 | 2131 | 0.118 | 0.025 | 6630 | 1.07 | 0.097 | 6610 | 8160 | 1.8 | 0.24 |
| 2000 | 12.89 | 8462 | 0.494 | 0.077 | 7129 | 4.21 | 0.398 | 7993 | 18038 | 6.97 | 0.97 |
| 6000 | 39.04 | 25555 | 1.56 | 0.205 | 7140 | 12.68 | 1.167 | 11980 | 48234 | 21.05 | 2.93 |
