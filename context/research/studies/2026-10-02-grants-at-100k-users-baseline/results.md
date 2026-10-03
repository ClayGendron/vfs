# Results — every number with its engine and N

Medians of 3 warm runs unless a cell says otherwise; cold = first run on a fresh session or process.
`pieces` and `admits` are pure Python on the event loop. The 100k world has 2 files per home (see README).

## World and load

| engine | N | entries | grant rows | memberships | load entries s | load grants s |
|---|---|---|---|---|---|---|
| postgres | 1,000 | 23,213 | 2,141 | 5,000 | 0.7 | 0.1 |
| postgres | 10,000 | 230,303 | 21,401 | 50,000 | 5.8 | 0.4 |
| sqlite | 1,000 | 23,213 | 2,141 | 5,000 | 0.5 | 0.0 |
| sqlite | 10,000 | 230,303 | 21,401 | 50,000 | 4.8 | 0.3 |
| sqlite | 100,000 | 501,203 | 214,001 | 500,000 | 10.9 | 3.7 |

## 1. resolve_authority (ms)

| engine | N | caller | cold (rows + 2×resolve) | warm cache hit | pure resolve(read) | _everyone_arms | rows read | holes | owner arms |
|---|---|---|---|---|---|---|---|---|---|
| postgres | 1,000 | ordinary | 13.44 | 1.6 | 2.79 | 0.97 | 1043 | 1,000 | 1 |
| postgres | 1,000 | heavy (u000986) | 12.57 | 1.39 | 2.97 | 0.99 | 1045 | 1,000 | 1 |
| postgres | 1,000 | pair | 12.81 | 1.24 | 3.3 | 1.08 | 1044 | 1,000 | 2 |
| postgres | 1,000 | anonymous | 7.62 | 1.36 | 1.1 | 0.96 | 1001 | 1,000 | 0 |
| postgres | 1,000 | system | 0.02 | 0.0 | — | — | — | 0 | 0 |
| postgres | 10,000 | ordinary | 121.76 | 1.4 | 66.71 | 11.51 | 10037 | 10,000 | 1 |
| postgres | 10,000 | heavy (u005437) | 144.68 | 1.28 | 87.21 | 11.92 | 10063 | 10,000 | 1 |
| postgres | 10,000 | pair | 70.96 | 1.27 | 34.2 | 11.53 | 10085 | 10,000 | 2 |
| postgres | 10,000 | anonymous | 46.74 | 1.26 | 12.38 | 11.49 | 10001 | 10,000 | 0 |
| postgres | 10,000 | system | 0.01 | 0.0 | — | — | — | 0 | 0 |
| sqlite | 1,000 | ordinary | 10.18 | 0.37 | 2.81 | 0.9 | 1043 | 1,000 | 1 |
| sqlite | 1,000 | heavy (u000986) | 10.15 | 0.37 | 2.72 | 0.98 | 1045 | 1,000 | 1 |
| sqlite | 1,000 | pair | 9.86 | 0.33 | 2.73 | 0.9 | 1044 | 1,000 | 2 |
| sqlite | 1,000 | anonymous | 6.09 | 0.26 | 1.04 | 0.92 | 1001 | 1,000 | 0 |
| sqlite | 1,000 | system | 0.01 | 0.0 | — | — | — | 0 | 0 |
| sqlite | 10,000 | ordinary | 118.03 | 0.59 | 66.55 | 11.89 | 10037 | 10,000 | 1 |
| sqlite | 10,000 | heavy (u005437) | 151.37 | 1.09 | 88.36 | 12.28 | 10063 | 10,000 | 1 |
| sqlite | 10,000 | pair | 77.97 | 0.51 | 36.22 | 13.36 | 10085 | 10,000 | 2 |
| sqlite | 10,000 | anonymous | 68.57 | 1.73 | 14.51 | 12.39 | 10001 | 10,000 | 0 |
| sqlite | 10,000 | system | 0.02 | 0.01 | — | — | — | 0 | 0 |
| sqlite | 100,000 | ordinary | 1832.09 | 3.59 | 994.18 | 230.6 | 100042 | 100,000 | 1 |
| sqlite | 100,000 | heavy (u056940) | 2533.49 | 0.58 | 1735.34 | 237.08 | 100072 | 100,000 | 1 |
| sqlite | 100,000 | pair | 827.79 | 0.74 | 271.02 | 232.02 | 100082 | 100,000 | 2 |
| sqlite | 100,000 | anonymous | 799.28 | 0.68 | 247.37 | 231.89 | 100001 | 100,000 | 0 |
| sqlite | 100,000 | system | 0.01 | 0.0 | — | — | — | 0 | 0 |

## 2. Rights.ranges() / pieces() (read rights)

| engine | N | caller | shipped pieces ms | study linear ms | equal | points | opens | owner pieces | JSON bind bytes |
|---|---|---|---|---|---|---|---|---|---|
| postgres | 1,000 | ordinary | 111.16 | 1.32 | True | 1,000 | 1,999 | 2 | 91,925 |
| postgres | 1,000 | heavy (u000986) | 113.49 | 1.56 | True | 1,000 | 1,999 | 2 | 91,925 |
| postgres | 1,000 | pair | 116.68 | 1.31 | True | 1,001 | 2,001 | 4 | 92,017 |
| postgres | 1,000 | anonymous | 114.07 | 1.35 | True | 1,001 | 2,001 | 0 | 92,017 |
| postgres | 10,000 | ordinary | 17892.2 | 17.47 | True | 10,000 | 19,999 | 2 | 919,925 |
| postgres | 10,000 | heavy (u005437) | 17347.46 | 14.17 | True | 10,000 | 19,999 | 2 | 919,925 |
| postgres | 10,000 | pair | 17670.19 | 14.81 | True | 10,001 | 20,001 | 98 | 920,017 |
| postgres | 10,000 | anonymous | 17519.92 | 17.6 | True | 10,001 | 20,001 | 0 | 920,017 |
| sqlite | 1,000 | ordinary | 113.46 | 1.26 | True | 1,000 | 1,999 | 2 | 91,925 |
| sqlite | 1,000 | heavy (u000986) | 113.2 | 1.25 | True | 1,000 | 1,999 | 2 | 91,925 |
| sqlite | 1,000 | pair | 113.92 | 1.31 | True | 1,001 | 2,001 | 4 | 92,017 |
| sqlite | 1,000 | anonymous | 111.54 | 1.29 | True | 1,001 | 2,001 | 0 | 92,017 |
| sqlite | 10,000 | ordinary | 18355.13 | 17.48 | True | 10,000 | 19,999 | 2 | 919,925 |
| sqlite | 10,000 | heavy (u005437) | 20323.31 | 16.76 | True | 10,000 | 19,999 | 2 | 919,925 |
| sqlite | 10,000 | pair | 20839.66 | 18.69 | True | 10,001 | 20,001 | 98 | 920,017 |
| sqlite | 10,000 | anonymous | 22061.08 | 21.83 | True | 10,001 | 20,001 | 0 | 920,017 |
| sqlite | 100,000 | ordinary | timed out at 60s | 264.41 | not checked (shipped timed out) | 100,000 | 199,999 | 2 | 9,199,925 |
| sqlite | 100,000 | heavy (u056940) | skipped: same holes as a caller that timed out | 287.78 | not checked (shipped timed out) | 100,000 | 199,999 | 2 | 9,199,925 |
| sqlite | 100,000 | pair | skipped: same holes as a caller that timed out | 240.88 | not checked (shipped timed out) | 100,001 | 200,001 | 154 | 9,200,017 |
| sqlite | 100,000 | anonymous | skipped: same holes as a caller that timed out | 298.67 | not checked (shipped timed out) | 100,001 | 200,001 | 0 | 9,200,017 |

## 3. Range join — visible_entries (ms)

| engine | N | caller | count cold | count warm | visible rows | fetch cold | fetch warm |
|---|---|---|---|---|---|---|---|
| postgres | 1,000 | ordinary | 320.58 | 233.64 | 2234 | 218.33 | 219.76 |
| postgres | 1,000 | heavy (u000986) | 241.1 | 9.85 | 2234 | 266.05 | 20.47 |
| postgres | 1,000 | pair | 424.01 | 361.91 | 2213 | 340.64 | 357.25 |
| postgres | 1,000 | anonymous | 99.66 | 96.84 | 2213 | 112.98 | 100.58 |
| postgres | 10,000 | ordinary | 387.14 | 313.48 | 20324 | 407.64 | 384.34 |
| postgres | 10,000 | heavy (u005437) | 341.44 | 113.8 | 20324 | 406.33 | 154.1 |
| postgres | 10,000 | pair | 484.2 | 505.89 | 20303 | 556.09 | 544.29 |
| postgres | 10,000 | anonymous | 253.06 | 256.96 | 20303 | 358.17 | 302.2 |
| sqlite | 1,000 | ordinary | 6.49 | 4.47 | 2234 | 10.94 | 9.13 |
| sqlite | 1,000 | heavy (u000986) | 4.32 | 3.93 | 2234 | 8.8 | 9.34 |
| sqlite | 1,000 | pair | 5.22 | 3.82 | 2213 | 9.81 | 9.06 |
| sqlite | 1,000 | anonymous | 5.54 | 4.24 | 2213 | 9.21 | 8.79 |
| sqlite | 10,000 | ordinary | 33.62 | 30.81 | 20324 | 84.54 | 83.3 |
| sqlite | 10,000 | heavy (u005437) | 56.23 | 31.18 | 20324 | 89.36 | 78.71 |
| sqlite | 10,000 | pair | 31.7 | 31.43 | 20303 | 85.03 | 77.15 |
| sqlite | 10,000 | anonymous | 31.36 | 29.36 | 20303 | 79.87 | 76.72 |
| sqlite | 100,000 | ordinary | 291.05 | 284.25 | 201206 | 749.71 | 746.47 |
| sqlite | 100,000 | heavy (u056940) | 291.28 | 292.45 | 201206 | 772.96 | 754.4 |
| sqlite | 100,000 | pair | 286.17 | 282.71 | 201203 | 744.86 | 741.15 |
| sqlite | 100,000 | anonymous | 283.51 | 286.01 | 201203 | 746.97 | 743.51 |

## 3b. Recall of the ordinary caller's join

| engine | N | stored rows | exact visible | join rows | recall | extra | admits agrees with oracle on sample | sample rows | admits over sample s |
|---|---|---|---|---|---|---|---|---|---|
| postgres | 1,000 | 23,213 | 2,234 | 2234 | 1.0 | 0 | True | 1221 | 0.02 |
| postgres | 10,000 | 230,303 | 20,324 | 20324 | 1.0 | 0 | True | 1221 | 0.11 |
| sqlite | 1,000 | 23,213 | 2,234 | 2234 | 1.0 | 0 | True | 1221 | 0.02 |
| sqlite | 10,000 | 230,303 | 20,324 | 20324 | 1.0 | 0 | True | 1221 | 0.12 |
| sqlite | 100,000 | 501,203 | 201,206 | 201206 | 1.0 | 0 | True | 1203 | 2.8 |

## 4. Clause fan — visibility_clauses (first clause; ms)

| engine | N | caller | clauses | build ms | binds | terms | cold | warm | result |
|---|---|---|---|---|---|---|---|---|---|
| postgres | 1,000 | ordinary | 1 | 19.99 | 2,003 | 4,007 | 1444.3 | 1297.2 | 2234 |
| postgres | 1,000 | pair | 1 | 21.11 | 2,006 | 4,012 | 1417.22 | 1320.7 | 2213 |
| postgres | 1,000 | anonymous | 1 | 22.07 | 2,000 | 4,000 | 311.75 | 242.86 | 2213 |
| postgres | 10,000 | ordinary | 2 | 239.17 | 20,000 | 40,000 | None | None | None |
| postgres | 10,000 | pair | 2 | 282.04 | 20,000 | 40,000 | None | None | None |
| postgres | 10,000 | anonymous | 1 | 191.73 | 20,000 | 40,000 | None | None | None |
| sqlite | 1,000 | ordinary | 1 | 19.51 | 2,003 | 4,007 | None | None | None |
| sqlite | 1,000 | pair | 1 | 57.52 | 2,006 | 4,012 | None | None | None |
| sqlite | 1,000 | anonymous | 1 | 20.9 | 2,000 | 4,000 | None | None | None |
| sqlite | 10,000 | ordinary | 2 | 212.72 | 20,000 | 40,000 | None | None | None |
| sqlite | 10,000 | pair | 2 | 394.07 | 20,000 | 40,000 | None | None | None |
| sqlite | 10,000 | anonymous | 1 | 415.36 | 20,000 | 40,000 | None | None | None |
| sqlite | 100,000 | ordinary | 2 | 2946.8 | 200,000 | 400,000 | None | None | None |
| sqlite | 100,000 | pair | 2 | 3668.78 | 200,000 | 400,000 | None | None | None |
| sqlite | 100,000 | anonymous | 1 | 4592.71 | 200,000 | 400,000 | None | None | None |

### Hole ladder (one root arm with H holes, one clause, count over the N=1,000 table)

| engine | holes | binds | cold ms | warm ms | result |
|---|---|---|---|---|---|
| sqlite | 500 | 1,001 | 439.05 | 421.57 | 12713 |
| sqlite | 900 | 1,801 | 614.52 | 583.37 | 4313 |
| sqlite | 990 | 1,981 | 644.87 | 641.35 | 2423 |
| sqlite | 1,000 | 2,001 | None | None | None |
| sqlite | 1,010 | 2,021 | None | None | None |
| sqlite | 1,100 | 2,201 | None | None | None |
| sqlite | 2,000 | 4,001 | None | None | None |
| postgres | 1,000 | 2,001 | 2124.89 | None | 2213 |
| postgres | 2,000 | 4,001 | 2861.38 | None | 2213 |
| postgres | 5,000 | 10,001 | timed out at 45s | None | None |

## 5. End to end through DatabaseStorage (ms; one fresh process per verb, cold = first call, warm = second)

| engine | N | caller | verb | cold | warm | rows | note |
|---|---|---|---|---|---|---|---|
| postgres | 1,000 | ordinary | tree / | 606.67 | 398.77 | 2,233 |  |
| postgres | 1,000 | ordinary | glob /shared/*/*.md | 81.95 | 60.01 | 2,000 |  |
| postgres | 1,000 | ordinary | ls /home | 61.0 | 31.06 | 101 |  |
| postgres | 1,000 | pair | tree / | 717.76 | 508.87 | 2,212 |  |
| postgres | 1,000 | pair | glob /shared/*/*.md | 80.26 | 59.58 | 2,000 |  |
| postgres | 1,000 | pair | ls /home | 61.22 | 33.67 | 100 |  |
| postgres | 1,000 | anonymous | tree / | 425.7 | 250.11 | 2,212 |  |
| postgres | 1,000 | anonymous | glob /shared/*/*.md | 68.99 | 58.08 | 2,000 |  |
| postgres | 1,000 | anonymous | ls /home | 37.59 | 22.83 | 100 |  |
| postgres | 1,000 | system | tree / | 208.17 | 160.44 | 23,212 |  |
| postgres | 1,000 | system | glob /shared/*/*.md | 20.56 | 21.45 | 2,000 |  |
| postgres | 1,000 | system | ls /home | 20.96 | 15.07 | 1,100 |  |
| postgres | 10,000 | ordinary | tree / | 21115.43 | 5021.24 | 20,323 |  |
| postgres | 10,000 | ordinary | glob /shared/*/*.md | 4086.5 | 3967.35 | 20,000 |  |
| postgres | 10,000 | ordinary | ls /home | 1053.94 | 914.56 | 101 |  |
| postgres | 10,000 | pair | tree / | 21320.16 | 4837.21 | 20,302 |  |
| postgres | 10,000 | pair | glob /shared/*/*.md | 4019.52 | 3956.38 | 20,000 |  |
| postgres | 10,000 | pair | ls /home | 932.8 | 857.23 | 100 |  |
| postgres | 10,000 | anonymous | tree / | 20690.37 | 4622.96 | 20,302 |  |
| postgres | 10,000 | anonymous | glob /shared/*/*.md | 4006.92 | 3924.32 | 20,000 |  |
| postgres | 10,000 | anonymous | ls /home | 800.88 | 776.45 | 100 |  |
| postgres | 10,000 | system | tree / | 1870.37 | 3214.29 | 230,302 |  |
| postgres | 10,000 | system | glob /shared/*/*.md | 171.02 | 151.22 | 20,000 |  |
| postgres | 10,000 | system | ls /home | 89.14 | 126.53 | 10,100 |  |
| sqlite | 1,000 | ordinary | tree / | 233.65 | 69.01 | 2,233 |  |
| sqlite | 1,000 | ordinary | glob /shared/*/*.md | 93.83 | 90.11 | 2,000 |  |
| sqlite | 1,000 | ordinary | ls /home | 56.5 | 45.66 | 101 |  |
| sqlite | 1,000 | pair | tree / | 241.35 | 79.89 | 2,212 |  |
| sqlite | 1,000 | pair | glob /shared/*/*.md | 77.45 | 61.22 | 2,000 |  |
| sqlite | 1,000 | pair | ls /home | 47.46 | 34.74 | 100 |  |
| sqlite | 1,000 | anonymous | tree / | 191.78 | 67.39 | 2,212 |  |
| sqlite | 1,000 | anonymous | glob /shared/*/*.md | 68.48 | 61.9 | 2,000 |  |
| sqlite | 1,000 | anonymous | ls /home | 30.85 | 21.27 | 100 |  |
| sqlite | 1,000 | system | tree / | 135.38 | 227.41 | 23,212 |  |
| sqlite | 1,000 | system | glob /shared/*/*.md | 19.06 | 18.21 | 2,000 |  |
| sqlite | 1,000 | system | ls /home | 15.24 | 11.31 | 1,100 |  |
| sqlite | 10,000 | ordinary | tree / | 21183.66 | 4170.42 | 20,323 |  |
| sqlite | 10,000 | ordinary | glob /shared/*/*.md | 4237.95 | 4094.49 | 20,000 |  |
| sqlite | 10,000 | ordinary | ls /home | 938.05 | 824.96 | 101 |  |
| sqlite | 10,000 | pair | tree / | 21980.58 | 4217.18 | 20,302 |  |
| sqlite | 10,000 | pair | glob /shared/*/*.md | 4182.23 | 4064.68 | 20,000 |  |
| sqlite | 10,000 | pair | ls /home | 940.12 | 861.39 | 100 |  |
| sqlite | 10,000 | anonymous | tree / | 21913.28 | 4238.42 | 20,302 |  |
| sqlite | 10,000 | anonymous | glob /shared/*/*.md | 4164.14 | 4204.75 | 20,000 |  |
| sqlite | 10,000 | anonymous | ls /home | 883.27 | 818.65 | 100 |  |
| sqlite | 10,000 | system | tree / | 2001.27 | 3094.18 | 230,302 |  |
| sqlite | 10,000 | system | glob /shared/*/*.md | 177.4 | 147.79 | 20,000 |  |
| sqlite | 10,000 | system | ls /home | 86.44 | 132.57 | 10,100 |  |
| sqlite | 100,000 | ordinary | tree / | — | — | — | {'timed_out_s': 60.0} |
| sqlite | 100,000 | ordinary | glob /shared/*/*.md | — | — | — | {'timed_out_s': 60.0} |
| sqlite | 100,000 | ordinary | ls /home | — | — | — | {'timed_out_s': 60.0} |
| sqlite | 100,000 | system | tree / | 5835.38 | 8346.12 | 501,202 |  |
| sqlite | 100,000 | system | glob /shared/*/*.md | 2786.43 | 3081.97 | 200,000 |  |
| sqlite | 100,000 | system | ls /home | 1400.27 | 2586.29 | 100,100 |  |

## 6. Cache churn (20 callers resolved, one grant written, 20 resolved again)

| engine | N | cached before | misses after one grant | recompute s for 20 callers | per caller s | if all N read once (CPU s) |
|---|---|---|---|---|---|---|
| postgres | 1,000 | 20 | 20 | 0.277 | 0.014 | 14 |
| postgres | 10,000 | 20 | 20 | 2.611 | 0.131 | 1,306 |
| sqlite | 1,000 | 20 | 20 | 0.215 | 0.011 | 11 |
| sqlite | 10,000 | 20 | 20 | 2.718 | 0.136 | 1,359 |
| sqlite | 100,000 | 20 | 20 | 42.57 | 2.128 | 212,850 |

## 7. Memory of one cached Resolution (ordinary caller)

| engine | N | Resolution bytes | plus read ranges bytes | 256-entry cache MB |
|---|---|---|---|---|
| postgres | 1,000 | 72,491 | 426,845 | 109.3 |
| postgres | 10,000 | 702,491 | 4,242,845 | 1,086.2 |
| sqlite | 1,000 | 72,491 | 426,845 | 109.3 |
| sqlite | 10,000 | 702,491 | 4,242,845 | 1,086.2 |
| sqlite | 100,000 | 7,002,491 | 42,402,845 | 10,855.1 |

## 8. Rights.admits per row (ordinary caller; µs)

| engine | N | own home file | shared file (root arm) | hidden home file | trap file |
|---|---|---|---|---|---|
| postgres | 1,000 | 0.9 | 20.4 | 12.1 | 18.4 |
| postgres | 10,000 | 0.8 | 187.7 | 109.8 | 169.0 |
| sqlite | 1,000 | 1.0 | 21.0 | 12.4 | 18.9 |
| sqlite | 10,000 | 1.0 | 199.8 | 113.7 | 181.0 |
| sqlite | 100,000 | 0.8 | 4346.5 | 2260.0 | 4030.1 |

## Meet ladder (out of world, pure Python; engine-independent, recorded on sqlite)

| group grants | single-subject resolve ms | pair resolve ms |
|---|---|---|
| 1,000 | 1.95 | 248.67 |
| 3,000 | 6.72 | 2256.59 |
| 10,000 | 18.82 | 25680.39 |

## Postgres at N = 100,000 — not completed

Three attempts, none finished:

1. The first chain was stopped by me at N = 1,000 because the hole
   ladder's statements wedged backends (see README).
2. The second chain reached the 100k load and lost its connection when
   the shared server went through crash recovery during another
   agent's 1M-row writes (`connection was closed in the middle of
   operation` on `bulk insert`, then `the database system is not yet
   accepting connections`).
3. The third attempt loaded the world (501,202 entries in 15 s,
   214,000 grants + 500,000 memberships in 5 s) and completed step 1
   for the ordinary caller, then was stopped on the coordinator's
   instruction while inside the quadratic `pieces()` step.

The one sound partial number, Postgres N = 100,000, ordinary caller,
`resolve_authority` cold: **1,344 ms** (warm hit 3.4 ms; pure
`resolve(read)` 814 ms; `_everyone_arms` 151 ms; 100,042 rows read;
100,000 holes; 1 owner arm). It matches SQLite's 1,832 ms within the
run-to-run noise (the resolver is pure Python past the row read).

Every Postgres timing in this study was taken on a server shared with
another agent's bulk-write spike during the same hour, and is noisy:
the range join's warm count for the same caller shape ranged from 8 ms
to 600 ms across runs. Treat the Postgres rows as order-of-magnitude.
The SQLite rows were taken on a private file.
