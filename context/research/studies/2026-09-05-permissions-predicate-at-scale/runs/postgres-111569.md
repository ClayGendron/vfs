## postgres — 111,569 entry rows (75,000 files, 36,569 directories)

Dialect `postgresql`: parameter budget 32700, in-list budget 65535, membership budget 32668. Grants: flat 96,772 rows (9.7 per principal), groups form 49,777 grant rows + 23,415 memberships, groups expanded 232,993 rows. Typical principal `p00010` owns 398 rows, 8 grants, 8 minimal prefixes, 20,471 rows visible by grant. Heavy principal `p00000` owns 10,961 rows. Median over 3 warm runs, ms, rows fetched to the client.

Load: entry 0.9s, grant 0.5s, grantg 0.3s, grantgx 1.2s, member 0.1s, vis 0.2s, vis_rows 40,972, index+stats 0.7s

### 1(a-c). Read predicate on list / glob / grep (typical principal)

| filter | none (0 binds) | exists (1 binds) | literal_like (17 binds) | literal_range (25 binds) | materialised (1 binds) |
|---|---|---|---|---|---|
| list | 4.0 · 2037r | 16.2 · 2037r | 4.7 · 2037r | 5.1 · 2037r | 8.3 · 2037r |
| glob | 5.5 · 3782r | 19.0 · 3782r | 4.8 · 3782r | 4.5 · 3782r | 9.0 · 3782r |
| grep | 10.2 · 7072r | 94.4 · 1588r | 5.1 · 1588r | 5.2 · 1588r | 71.3 · 1588r |

Heavy principal `p00000` (10,961 owned rows):

| filter | none | exists | materialised |
|---|---|---|---|
| list | 3.8 · 2037r | 17.6 · 2037r | 8.3 · 2037r |
| grep | 11.1 · 7072r | 99.8 · 2114r | 24.8 [first 69] · 2114r |

### 1(d). Ranked join-back: candidate ids filtered by the predicate, chunked by the membership budget

| candidates / form | none | exists | literal_like | materialised |
|---|---|---|---|---|
| K=256 IN | 2.3 · 256r | 3.5 · 58r | 2.8 · 58r | 6.0 · 58r |
| K=256 VALUES | 2.3 · 256r | 3.6 · 58r | 2.7 · 58r | 2.7 · 58r |
| K=1000 IN | 4.5 · 1000r | 9.3 · 209r | 5.1 · 209r | 8.5 · 209r |
| K=1000 VALUES | 10.8 · 1000r | 10.5 · 209r | 8.6 · 209r | 6.2 · 209r |
| K=3000 IN | 12.5 · 3000r | 29.6 · 659r | 13.7 · 659r | 15.1 · 659r |
| K=3000 VALUES | 18.3 · 3000r | 33.7 · 659r | 15.6 · 659r | 16.4 [first 99] · 659r |

### 2. Write point check (longest matching prefix)

| form | cost | statements | binds per statement |
|---|---|---|---|
| one path: `principal_id = :p AND path_prefix IN (ancestors)` | 0.63 ms median per check (200 distinct paths, mean 0.68) | 1 | 1 + depth (≤ 9) |
| 10k paths: distinct ancestors chunked `IN` | 84.7 ms total (18,526 distinct prefixes) | 1 | 1 + 32668 |
| 10k paths: fetch the caller's grants once, resolve in app | 1.5 ms query (8 rows) + 11.0 ms app resolve | 1 | 1 |

### 3. Materialised `visible(principal_id, entry_id)`: size and maintenance

| quantity | value |
|---|---|
| entry rows | 111,569 |
| exhaustive visible rows, flat grants (direct + 5 everyone grants) | 206,669,891 (1,852× the entry table) |
|   of which the 5 everyone grants × 10,000 principals | 204,801,194 |
|   direct grants only | 1,868,697 (16.7× the entry table) |
| exhaustive visible rows, groups expanded | 210,875,714 |
| sample loaded for the read tests (2 principals) | 40,972 rows in 0.2s |
| insert one grant's rows: typical direct grant (`/t022/src/docs/lib`) | 2.3 ms for 3 rows |
| insert one grant's rows: wide grant /t000, one principal (`/t000`) | 28.8 ms for 15,481 rows |
| a new everyone grant on /t000 | 15,481 rows × 10,000 principals = 154,810,000 rows, ≈ 288 s at the measured per-principal rate |

### 4. Groups: three encodings of the same rights (typical principal, 2 groups)

| filter | flat expanded (exists over grantgx) (1 binds) | membership subquery (1 binds) | groups literal (4 binds) |
|---|---|---|---|
| glob | 13.8 · 3782r | 15905.5 · 3782r | 30.6 · 3782r |
| grep | 43.5 · 1590r | 35476.1 · 1590r | 109.2 · 1590r |
| join-back K=1000 IN | 8.8 · 209r | 4305.0 · 209r | 12.8 · 209r |

### 5. Subject set: a right held by every principal in the set (b = binds per statement)

| set / filter | (a) AND of n EXISTS | (b) grouped HAVING COUNT(DISTINCT) = n | (c) app-side prefix intersection, literal |
|---|---|---|---|
| n=2 glob | 22.7 · 3782r · 5b | 18.0 · 3782r · 9b | 5.9 · 3782r · 59b |
| n=2 grep | 97.2 · 1559r · 5b | 22.7 · 1559r · 9b | 5.6 · 1559r · 59b |
| n=2 join-back K=1000 | 9.8 · 207r · 32668b | 11.7 · 207r · 32667b | 5.8 · 207r · 32668b |
| n=5 glob | 49.1 · 3782r · 8b | 28.5 · 3782r · 12b | 8.0 · 3782r · 68b |
| n=5 grep | 129.7 · 1559r · 8b | 36.0 · 1559r · 12b | 16.5 · 1559r · 68b |
| n=5 join-back K=1000 | 10.5 · 207r · 32668b | 15.1 · 207r · 32667b | 5.7 · 207r · 32668b |
| n=20 glob | 220.3 · 3782r · 23b | 87.4 · 3782r · 27b | 8.7 · 3782r · 233b |
| n=20 grep | 313.9 · 1559r · 23b | 130.0 · 1559r · 27b | 21.5 · 1559r · 233b |
| n=20 join-back K=1000 | 18.7 · 207r · 32668b | 24.7 · 207r · 32667b | 7.7 · 207r · 32668b |

### Plan shapes

| query | plan skeleton |
|---|---|
| grep · exists | ` [42.877 ms]` |
| glob · exists | `BitmapAnd > Bitmap Index Scan[ix_entry_ext_kind] > Bitmap Index Scan[ux_entry_path] [10.510 ms]` |
| glob · literal_like | `BitmapAnd > Bitmap Index Scan[ix_entry_ext_kind] > Bitmap Index Scan[ux_entry_path] [2.382 ms]` |
| glob · literal_range | `BitmapAnd > Bitmap Index Scan[ix_entry_ext_kind] > Bitmap Index Scan[ux_entry_path] [1.996 ms]` |
| grep · materialised | ` [21.402 ms]` |
| grep · groups subquery | ` [35558.053 ms]` |
| glob · set n=5 AND | `BitmapAnd > Bitmap Index Scan[ix_entry_ext_kind] > Bitmap Index Scan[ux_entry_path] [44.923 ms]` |
| glob · set n=5 HAVING | `Nested Loop > GroupAggregate > Unique > Sort > Append > Nested Loop > Bitmap Index Scan[ix_entry_ext_kind] > Materializex3782 > BitmapAnd > Bitmap Index Scan[ix_entry_owner] > Bitmap Index Scan[ix_entry_ext_kind] [37.877 ms]` |
| glob · set n=5 app | `BitmapAnd > Bitmap Index Scan[ix_entry_ext_kind] > Bitmap Index Scan[ux_entry_path] [2.163 ms]` |
| join-back K=1000 IN · exists | ` [3.658 ms]` |
| join-back K=1000 VALUES · exists | `Nested Loop > Values Scan["*VALUES*"] [3.990 ms]` |

### 6. Bind budgets at a 10k batch, n = 20, G = grants per principal

| shape | binds | on this engine | respects membership_budget? |
|---|---|---|---|
| read: owner OR EXISTS | 1 | 1 | yes |
| read: literal prefixes (LIKE) | 1 + 2G | 35 (G = 17, corpus max) | yes while 1 + 2G ≤ 32668; needs a per-principal grant cap or an EXISTS fallback |
| read: literal prefixes (range) | 1 + 3G | 52 | same |
| join-back IN, EXISTS | chunk + 1 | 32669 per statement, 1 statements at K = 10k | yes (chunked) |
| join-back VALUES, EXISTS | chunk + 1 | 32669, 1 statements | yes (chunked) |
| write check, one path | 1 + depth | ≤ 10 | yes |
| write check, 10k batch as chunked IN | 1 + chunk | 32669, 1 statements (18,526 distinct ancestors) | yes (chunked) |
| write check, grants fetched once | 1 | 1 | yes; app resolves |
| groups: membership subquery | 1 | 1 | yes |
| groups: literal group ids | 1 + |groups(p)| | 3 here | yes while |groups(p)| ≤ budget |
| set (a) AND of n EXISTS | n | 20 | yes |
| set (b) HAVING, scoped | n + 1 + copies × filter | 21 + 3 × chunk on join-back → chunk ≤ 10882 | yes only if the candidate list is chunked at a third of the budget |
| set (c) app-side intersection | ≤ 2|∩| + Σ_i (1 + 2|∩_{-i}|) | measured: 229 at n = 20 | yes while n × G stays under the budget; worst case (n+1) × 2G |

Wall clock for this run: 4.6 min.
