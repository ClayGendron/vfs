# Results: the row-grant predicate at scale

Raw per-engine tables from `probe.py` (see `README.md`). Times are medians over warm runs in ms; `· Nr` is rows fetched; `· Nb` is binds per statement; `(2 stmts)` means the batch was chunked; `†`/`capped` means only one run was taken because it exceeded the 60 s cap. SQL Server and Oracle run under Rosetta emulation: read ratios, not absolute times.

## sqlite — 111,569 entry rows (75,000 files, 36,569 directories)

Dialect `sqlite`: parameter budget 32700, in-list budget 32766, membership budget 32668. Grants: flat 96,772 rows (9.7 per principal), groups form 49,777 grant rows + 23,415 memberships, groups expanded 232,993 rows. Typical principal `p00010` owns 398 rows, 8 grants, 8 minimal prefixes, 20,471 rows visible by grant. Heavy principal `p00000` owns 10,961 rows. Median over 5 warm runs, ms, rows fetched to the client.

Load: entry 0.3s, grant 0.2s, grantg 0.1s, grantgx 0.4s, member 0.0s, vis 0.1s, vis_rows 40,972, index+stats 0.3s

### 1(a-c). Read predicate on list / glob / grep (typical principal)

| filter | none (0 binds) | exists (1 binds) | literal_like (17 binds) | literal_range (25 binds) | materialised (1 binds) |
|---|---|---|---|---|---|
| list | 2.0 · 2037r | 2.8 · 2037r | 2.2 · 2037r | 2.2 · 2037r | 2.7 · 2037r |
| glob | 5.3 · 3782r | 7.2 · 3782r | 5.9 · 3782r | 5.8 · 3782r | 6.9 · 3782r |
| grep | 8.6 · 7072r | 16.1 · 1588r | 8.6 · 1588r | 8.5 · 1588r | 8.6 · 1588r |

Heavy principal `p00000` (10,961 owned rows):

| filter | none | exists | materialised |
|---|---|---|---|
| list | 1.9 · 2037r | 2.6 · 2037r | 2.7 · 2037r |
| grep | 8.3 · 7072r | 21.3 · 2114r | 8.7 · 2114r |

### 1(d). Ranked join-back: candidate ids filtered by the predicate, chunked by the membership budget

| candidates / form | none | exists | literal_like | materialised |
|---|---|---|---|---|
| K=256 IN | 0.8 · 256r | 1.2 · 58r | 1.1 · 58r | 0.8 · 58r |
| K=256 VALUES | 0.9 · 256r | 1.1 · 58r | 1.1 · 58r | 0.8 · 58r |
| K=1000 IN | 2.5 · 1000r | 3.7 · 209r | 3.1 · 209r | 2.6 · 209r |
| K=1000 VALUES | 2.4 · 1000r | 3.7 · 209r | 3.3 · 209r | 2.8 · 209r |
| K=3000 IN | 8.2 · 3000r | 11.4 · 659r | 8.8 · 659r | 8.1 · 659r |
| K=3000 VALUES | 7.7 · 3000r | 11.3 · 659r | 10.2 [first 76] · 659r | 8.1 · 659r |

### 2. Write point check (longest matching prefix)

| form | cost | statements | binds per statement |
|---|---|---|---|
| one path: `principal_id = :p AND path_prefix IN (ancestors)` | 0.18 ms median per check (200 distinct paths, mean 0.19) | 1 | 1 + depth (≤ 9) |
| 10k paths: distinct ancestors chunked `IN` | 48.8 ms total (18,526 distinct prefixes) | 1 | 1 + 32668 |
| 10k paths: fetch the caller's grants once, resolve in app | 0.2 ms query (8 rows) + 11.0 ms app resolve | 1 | 1 |

### 3. Materialised `visible(principal_id, entry_id)`: size and maintenance

| quantity | value |
|---|---|
| entry rows | 111,569 |
| exhaustive visible rows, flat grants (direct + 5 everyone grants) | 206,669,891 (1,852× the entry table) |
|   of which the 5 everyone grants × 10,000 principals | 204,801,194 |
|   direct grants only | 1,868,697 (16.7× the entry table) |
| exhaustive visible rows, groups expanded | 210,875,714 |
| sample loaded for the read tests (2 principals) | 40,972 rows in 0.1s |
| insert one grant's rows: typical direct grant (`/t022/src/docs/lib`) | 0.3 ms for 3 rows |
| insert one grant's rows: wide grant /t000, one principal (`/t000`) | 8.9 ms for 15,481 rows |
| a new everyone grant on /t000 | 15,481 rows × 10,000 principals = 154,810,000 rows, ≈ 89 s at the measured per-principal rate |

### 4. Groups: three encodings of the same rights (typical principal, 2 groups)

| filter | flat expanded (exists over grantgx) (1 binds) | membership subquery (1 binds) | groups literal (4 binds) |
|---|---|---|---|
| glob | 7.5 · 3782r | 16.6 · 3782r | 12.5 [first 98] · 3782r |
| grep | 23.6 · 1590r | 30.6 · 1590r | 28.1 · 1590r |
| join-back K=1000 IN | 5.0 · 209r | 6.0 · 209r | 5.8 · 209r |

### 5. Subject set: a right held by every principal in the set (b = binds per statement)

| set / filter | (a) AND of n EXISTS | (b) grouped HAVING COUNT(DISTINCT) = n | (c) app-side prefix intersection, literal |
|---|---|---|---|
| n=2 glob | 8.6 · 3782r · 5b | 27.6 · 3782r · 9b | 6.0 · 3782r · 59b |
| n=2 grep | 24.3 · 1559r · 5b | 38.6 · 1559r · 9b | 8.5 · 1559r · 59b |
| n=2 join-back K=1000 | 5.1 · 207r · -30664b | 8.9 · 207r · -26661b | 3.0 · 207r · -30556b |
| n=5 glob | 13.3 · 3782r · 8b | 54.4 · 3782r · 12b | 5.9 · 3782r · 68b |
| n=5 grep | 23.2 · 1559r · 8b | 88.4 · 1559r · 12b | 8.6 · 1559r · 68b |
| n=5 join-back K=1000 | 4.0 · 207r · -30658b | 14.1 · 207r · -26655b | 3.2 · 207r · -30538b |
| n=20 glob | 39.3 · 3782r · 23b | 191.0 · 3782r · 27b | 6.7 · 3782r · 233b |
| n=20 grep | 31.3 · 1559r · 23b | 275.6 · 1559r · 27b | 9.3 · 1559r · 233b |
| n=20 join-back K=1000 | 6.0 · 207r · -30628b | 42.7 · 207r · -26625b | 4.0 · 207r · -30208b |

### Plan shapes

| query | plan skeleton |
|---|---|
| grep · exists | `SCAN e / CORRELATED SCALAR SUBQUERY 1 / SEARCH g USING COVERING INDEX ix_vfs_s1_0c3fe223_grant_pp (principal_id=?)` |
| glob · exists | `SEARCH e USING INDEX ux_vfs_s1_0c3fe223_entry_path (path>? AND path<?) / CORRELATED SCALAR SUBQUERY 1 / SEARCH g USING COVERING INDEX ix_vfs_s1_0c3fe223_grant_pp (principal_id=?)` |
| glob · literal_like | `SEARCH e USING INDEX ux_vfs_s1_0c3fe223_entry_path (path>? AND path<?)` |
| glob · literal_range | `SEARCH e USING INDEX ux_vfs_s1_0c3fe223_entry_path (path>? AND path<?)` |
| grep · materialised | `SCAN e / CORRELATED SCALAR SUBQUERY 1 / SEARCH v USING COVERING INDEX ux_vfs_s1_0c3fe223_vis (principal_id=? AND entry_id=?)` |
| grep · groups subquery | `SCAN e / CORRELATED SCALAR SUBQUERY 2 / MULTI-INDEX OR / INDEX 1 / SEARCH g USING COVERING INDEX ix_vfs_s1_0c3fe223_grantg_pp (principal_id=?) / INDEX 2 / LIST SUBQUERY 1 / SEARCH m USING COVERING INDEX ix_vfs_s1_0c3fe223_member_p (principal_id=?) / CREATE BLOOM FILTER / SEARCH g USING COVERING INDEX ix_vfs_s1_0c3fe223_grantg_pp (principal_id=?)` |
| glob · set n=5 AND | `SEARCH e USING INDEX ux_vfs_s1_0c3fe223_entry_path (path>? AND path<?) / CORRELATED SCALAR SUBQUERY 1 / SEARCH g USING COVERING INDEX ix_vfs_s1_0c3fe223_grant_pp (principal_id=?) / CORRELATED SCALAR SUBQUERY 2 / SEARCH g USING COVERING INDEX ix_vfs_s1_0c3fe223_grant_pp (principal_id=?) / CORRELATED SCALAR SUBQUERY 3 / SEARCH g USING COVERING INDEX ix_vfs_s1_0c3fe223_grant_pp (principal_id=?) / COR` |
| glob · set n=5 HAVING | `SEARCH e USING INTEGER PRIMARY KEY (rowid=?) / LIST SUBQUERY 3 / CO-ROUTINE x / COMPOUND QUERY / LEFT-MOST SUBQUERY / SEARCH e2 USING INDEX ux_vfs_s1_0c3fe223_entry_path (path>? AND path<?) / SEARCH g USING COVERING INDEX ix_vfs_s1_0c3fe223_grant_pp (principal_id=?) / UNION USING TEMP B-TREE / SEARCH e3 USING INDEX ix_vfs_s1_0c3fe223_entry_owner (owner_id=?) / SCAN x / USE TEMP B-TREE FOR GROUP BY` |
| glob · set n=5 app | `SEARCH e USING INDEX ux_vfs_s1_0c3fe223_entry_path (path>? AND path<?)` |
| join-back K=1000 IN · exists | `SEARCH e USING INTEGER PRIMARY KEY (rowid=?) / CORRELATED SCALAR SUBQUERY 1 / SEARCH g USING COVERING INDEX ix_vfs_s1_0c3fe223_grant_pp (principal_id=?)` |
| join-back K=1000 VALUES · exists | `CO-ROUTINE cte / SCAN 1000 CONSTANT ROWS / SCAN cte / SEARCH e USING INTEGER PRIMARY KEY (rowid=?) / CORRELATED SCALAR SUBQUERY 1002 / SEARCH g USING COVERING INDEX ix_vfs_s1_0c3fe223_grant_pp (principal_id=?)` |

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

Wall clock for this run: 0.2 min.



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
| n=2 join-back K=1000 | 9.8 · 207r · 1002b | 11.7 · 207r · 3003b | 5.8 · 207r · 1056b |
| n=5 glob | 49.1 · 3782r · 8b | 28.5 · 3782r · 12b | 8.0 · 3782r · 68b |
| n=5 grep | 129.7 · 1559r · 8b | 36.0 · 1559r · 12b | 16.5 · 1559r · 68b |
| n=5 join-back K=1000 | 10.5 · 207r · 1005b | 15.1 · 207r · 3006b | 5.7 · 207r · 1065b |
| n=20 glob | 220.3 · 3782r · 23b | 87.4 · 3782r · 27b | 8.7 · 3782r · 233b |
| n=20 grep | 313.9 · 1559r · 23b | 130.0 · 1559r · 27b | 21.5 · 1559r · 233b |
| n=20 join-back K=1000 | 18.7 · 207r · 1020b | 24.7 · 207r · 3021b | 7.7 · 207r · 1230b |

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



## mariadb — 111,569 entry rows (75,000 files, 36,569 directories)

Dialect `mariadb`: parameter budget 32700, in-list budget 65535, membership budget 32668. Grants: flat 96,772 rows (9.7 per principal), groups form 49,777 grant rows + 23,415 memberships, groups expanded 232,993 rows. Typical principal `p00010` owns 398 rows, 8 grants, 8 minimal prefixes, 20,471 rows visible by grant. Heavy principal `p00000` owns 10,961 rows. Median over 3 warm runs, ms, rows fetched to the client.

Load: entry 1.0s, grant 0.5s, grantg 0.3s, grantgx 1.3s, member 0.1s, vis 0.1s, vis_rows 40,972, index+stats 0.5s

### 1(a-c). Read predicate on list / glob / grep (typical principal)

| filter | none (0 binds) | exists (1 binds) | literal_like (17 binds) | literal_range (25 binds) | materialised (1 binds) |
|---|---|---|---|---|---|
| list | 17.9 · 2037r | 21.7 · 2037r | 19.6 · 2037r | 21.3 · 2037r | 28.0 · 2037r |
| glob | 26.3 · 3782r | 31.2 · 3782r | 27.8 · 3782r | 28.4 · 3782r | 34.8 · 3782r |
| grep | 28.5 · 7072r | 36.8 · 1588r | 23.3 · 1588r | 23.5 · 1588r | 27.5 · 1588r |

Heavy principal `p00000` (10,961 owned rows):

| filter | none | exists | materialised |
|---|---|---|---|
| list | 18.0 · 2037r | 21.4 · 2037r | 26.9 · 2037r |
| grep | 28.2 · 7072r | 42.6 · 2114r | 28.3 · 2114r |

### 1(d). Ranked join-back: candidate ids filtered by the predicate, chunked by the membership budget

| candidates / form | none | exists | literal_like | materialised |
|---|---|---|---|---|
| K=256 IN | 2.1 · 256r | 2.7 · 58r | 2.1 · 58r | 2.1 · 58r |
| K=256 VALUES | 2.2 · 256r | 2.6 · 58r | 2.0 · 58r | 2.3 · 58r |
| K=1000 IN | 6.2 · 1000r | 7.2 · 209r | 5.1 · 209r | 5.4 · 209r |
| K=1000 VALUES | 6.1 · 1000r | 7.1 · 209r | 4.8 · 209r | 6.2 · 209r |
| K=3000 IN | 16.9 [first 65] · 3000r | 18.8 · 659r | 13.0 · 659r | 14.9 · 659r |
| K=3000 VALUES | 16.7 · 3000r | 17.6 · 659r | 12.9 · 659r | 14.0 · 659r |

### 2. Write point check (longest matching prefix)

| form | cost | statements | binds per statement |
|---|---|---|---|
| one path: `principal_id = :p AND path_prefix IN (ancestors)` | 0.76 ms median per check (200 distinct paths, mean 0.84) | 1 | 1 + depth (≤ 9) |
| 10k paths: distinct ancestors chunked `IN` | 111.3 ms total (18,526 distinct prefixes) | 1 | 1 + 32668 |
| 10k paths: fetch the caller's grants once, resolve in app | 1.4 ms query (8 rows) + 11.0 ms app resolve | 1 | 1 |

### 3. Materialised `visible(principal_id, entry_id)`: size and maintenance

| quantity | value |
|---|---|
| entry rows | 111,569 |
| exhaustive visible rows, flat grants (direct + 5 everyone grants) | 206,669,891 (1,852× the entry table) |
|   of which the 5 everyone grants × 10,000 principals | 204,801,194 |
|   direct grants only | 1,868,697 (16.7× the entry table) |
| exhaustive visible rows, groups expanded | 210,875,714 |
| sample loaded for the read tests (2 principals) | 40,972 rows in 0.1s |
| insert one grant's rows: typical direct grant (`/t022/src/docs/lib`) | 1.0 ms for 3 rows |
| insert one grant's rows: wide grant /t000, one principal (`/t000`) | 21.0 ms for 15,481 rows |
| a new everyone grant on /t000 | 15,481 rows × 10,000 principals = 154,810,000 rows, ≈ 210 s at the measured per-principal rate |

### 4. Groups: three encodings of the same rights (typical principal, 2 groups)

| filter | flat expanded (exists over grantgx) (1 binds) | membership subquery (1 binds) | groups literal (4 binds) |
|---|---|---|---|
| glob | 31.5 · 3782r | 31.8 · 3782r | 33.6 · 3782r |
| grep | 46.9 · 1590r | 188437.4 [capped after first run 188s] · 1590r | 57.7 · 1590r |
| join-back K=1000 IN | 8.7 · 209r | 27655.1 · 209r | 10.4 · 209r |

### 5. Subject set: a right held by every principal in the set (b = binds per statement)

| set / filter | (a) AND of n EXISTS | (b) grouped HAVING COUNT(DISTINCT) = n | (c) app-side prefix intersection, literal |
|---|---|---|---|
| n=2 glob | 35.0 · 3782r · 5b | 70.4 · 3782r · 9b | 28.5 · 3782r · 59b |
| n=2 grep | 47.2 · 1559r · 5b | 60.4 · 1559r · 9b | 24.0 · 1559r · 59b |
| n=2 join-back K=1000 | 9.8 · 207r · 1002b | 12.6 · 207r · 3003b | 6.8 · 207r · 1056b |
| n=5 glob | 50.1 · 3782r · 8b | 202.1 · 3782r · 12b | 28.1 · 3782r · 68b |
| n=5 grep | 47.2 · 1559r · 8b | 87.2 · 1559r · 12b | 23.5 · 1559r · 68b |
| n=5 join-back K=1000 | 9.6 · 207r · 1005b | 15.7 · 207r · 3006b | 5.1 [first 100] · 207r · 1065b |
| n=20 glob | 117.5 · 3782r · 23b | 1653.0 · 3782r · 27b | 28.8 · 3782r · 233b |
| n=20 grep | 75.7 · 1559r · 23b | 582.6 · 1559r · 27b | 31.0 · 1559r · 233b |
| n=20 join-back K=1000 | 16.6 · 207r · 1020b | 36.9 · 207r · 3021b | 6.4 · 207r · 1230b |

### Plan shapes

| query | plan skeleton |
|---|---|
| grep · exists | `PRIMARY:e:ALL:None:111273 / DEPENDENT SUBQUERY:g:ref:ix_vfs_s1_a8b078f6_grant_pp:8` |
| glob · exists | `PRIMARY:e:ALL:None:111273 / DEPENDENT SUBQUERY:g:ref:ix_vfs_s1_a8b078f6_grant_pp:8` |
| glob · literal_like | `SIMPLE:e:ALL:None:111273` |
| glob · literal_range | `SIMPLE:e:ALL:None:111273` |
| grep · materialised | `PRIMARY:e:ALL:None:111273 / MATERIALIZED:v:ALL:None:41223` |
| grep · groups subquery | `PRIMARY:e:ALL:None:111273 / DEPENDENT SUBQUERY:g:index:ix_vfs_s1_a8b078f6_grantg_pp:50006 / MATERIALIZED:m:ref:ix_vfs_s1_a8b078f6_member_p:2` |
| glob · set n=5 AND | `PRIMARY:e:ALL:None:111273 / DEPENDENT SUBQUERY:g:ref:ix_vfs_s1_a8b078f6_grant_pp:7 / DEPENDENT SUBQUERY:g:ref:ix_vfs_s1_a8b078f6_grant_pp:7 / DEPENDENT SUBQUERY:g:ref:ix_vfs_s1_a8b078f6_grant_pp:13 / DEPENDENT SUBQUERY:g:ref:ix_vfs_s1_a8b078f6_grant_pp:12 / DEPENDENT SUBQUERY:g:ref:ix_vfs_s1_a8b078f6_grant_pp:6` |
| glob · set n=5 HAVING | `PRIMARY:e:ALL:None:111273 / PRIMARY:<subquery2>:eq_ref:distinct_key:1 / MATERIALIZED:<derived3>:ALL:None:666757 / DERIVED:g:range:ix_vfs_s1_a8b078f6_grant_pp:45 / DERIVED:e2:ALL:None:111273 / UNION:e3:range:ix_vfs_s1_a8b078f6_entry_owner:5 / UNION RESULT:<union3,4>:ALL:None:None` |
| glob · set n=5 app | `SIMPLE:e:ALL:None:111273` |
| join-back K=1000 IN · exists | `PRIMARY:<derived4>:ALL:None:1000 / PRIMARY:e:eq_ref:PRIMARY:1 / DERIVED:None:None:None:None / DEPENDENT SUBQUERY:g:ref:ix_vfs_s1_a8b078f6_grant_pp:8` |
| join-back K=1000 VALUES · exists | `PRIMARY:<derived2>:ALL:None:1000 / PRIMARY:e:eq_ref:PRIMARY:1 / DEPENDENT SUBQUERY:g:ref:ix_vfs_s1_a8b078f6_grant_pp:8 / DERIVED:None:None:None:None` |

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

Wall clock for this run: 5.4 min.



## mssql — 111,569 entry rows (75,000 files, 36,569 directories)

Dialect `mssql`: parameter budget 2099, in-list budget 2000, membership budget 2000. Grants: flat 96,772 rows (9.7 per principal), groups form 49,777 grant rows + 23,415 memberships, groups expanded 232,993 rows. Typical principal `p00010` owns 398 rows, 8 grants, 8 minimal prefixes, 20,471 rows visible by grant. Heavy principal `p00000` owns 10,961 rows. Median over 3 warm runs, ms, rows fetched to the client.

Load: entry 57.0s, grant 7.5s, grantg 8.0s, grantgx 32.5s, member 2.2s, vis 0.4s, vis_rows 40,972, index+stats 1.8s

### 1(a-c). Read predicate on list / glob / grep (typical principal)

| filter | none (0 binds) | exists (1 binds) | literal_like (17 binds) | literal_range (25 binds) | materialised (1 binds) |
|---|---|---|---|---|---|
| list | 10.6 [first 61] · 2037r | 17.9 [first 214] · 2037r | 11.6 · 2037r | 11.7 · 2037r | 15.4 [first 54] · 2037r |
| glob | 31.5 [first 108] · 3782r | 45.9 · 3782r | 33.2 · 3782r | 33.5 · 3782r | 39.9 · 3782r |
| grep | 19.9 [first 231] · 7072r | 53.0 · 1588r | 27.8 · 1588r | 25.2 · 1588r | 28.0 · 1588r |

Heavy principal `p00000` (10,961 owned rows):

| filter | none | exists | materialised |
|---|---|---|---|
| list | 10.5 · 2037r | 18.8 · 2037r | 15.6 · 2037r |
| grep | 17.5 · 7072r | 59.2 · 2114r | 26.9 · 2114r |

### 1(d). Ranked join-back: candidate ids filtered by the predicate, chunked by the membership budget

| candidates / form | none | exists | literal_like | materialised |
|---|---|---|---|---|
| K=256 IN | 4.9 · 256r | 6.4 [first 63] · 58r | 5.7 [first 74] · 58r | 5.0 [first 71] · 58r |
| K=256 VALUES | 4.0 · 256r | 6.1 · 58r | 5.0 · 58r | 4.6 · 58r |
| K=1000 IN | 10.9 [first 186] · 1000r | 17.2 [first 350] · 209r | 13.0 [first 593] · 209r | 14.8 [first 363] · 209r |
| K=1000 VALUES | 39.1 [first 102] · 1000r | 42.1 [first 115] · 209r | 20.3 [first 82] · 209r | 23.7 [first 88] · 209r |
| K=3000 IN | 29.0 (2 stmts) [first 580] · 3000r | 49.5 (2 stmts) [first 1116] · 659r | 36.4 (2 stmts) [first 2060] · 659r | 42.0 (2 stmts) [first 1124] · 659r |
| K=3000 VALUES | 53.1 (2 stmts) [first 155] · 3000r | 60.7 (2 stmts) [first 185] · 659r | 44.2 (2 stmts) [first 156] · 659r | 56.6 (2 stmts) [first 188] · 659r |

### 2. Write point check (longest matching prefix)

| form | cost | statements | binds per statement |
|---|---|---|---|
| one path: `principal_id = :p AND path_prefix IN (ancestors)` | 3.46 ms median per check (200 distinct paths, mean 4.53) | 1 | 1 + depth (≤ 9) |
| 10k paths: distinct ancestors chunked `IN` | 144.5 ms total (18,526 distinct prefixes) | 10 | 1 + 2000 |
| 10k paths: fetch the caller's grants once, resolve in app | 1.8 ms query (8 rows) + 10.6 ms app resolve | 1 | 1 |

### 3. Materialised `visible(principal_id, entry_id)`: size and maintenance

| quantity | value |
|---|---|
| entry rows | 111,569 |
| exhaustive visible rows, flat grants (direct + 5 everyone grants) | 206,669,891 (1,852× the entry table) |
|   of which the 5 everyone grants × 10,000 principals | 204,801,194 |
|   direct grants only | 1,868,697 (16.7× the entry table) |
| exhaustive visible rows, groups expanded | 210,875,714 |
| sample loaded for the read tests (2 principals) | 40,972 rows in 0.4s |
| insert one grant's rows: typical direct grant (`/t022/src/docs/lib`) | 3.4 ms for 3 rows |
| insert one grant's rows: wide grant /t000, one principal (`/t000`) | 179.4 ms for 15,481 rows |
| a new everyone grant on /t000 | 15,481 rows × 10,000 principals = 154,810,000 rows, ≈ 1,794 s at the measured per-principal rate |

### 4. Groups: three encodings of the same rights (typical principal, 2 groups)

| filter | flat expanded (exists over grantgx) (1 binds) | membership subquery (1 binds) | groups literal (4 binds) |
|---|---|---|---|
| glob | 45.9 [first 290] · 3782r | 82926.6 [capped after first run 83s] · 3782r | 130.2 · 3782r |
| grep | 65.3 · 1590r | 157748.8 [capped after first run 158s] · 1590r | 223.0 · 1590r |
| join-back K=1000 IN | 23.8 [first 384] · 209r | 22371.7 · 209r | 47.8 [first 379] · 209r |

### 5. Subject set: a right held by every principal in the set (b = binds per statement)

| set / filter | (a) AND of n EXISTS | (b) grouped HAVING COUNT(DISTINCT) = n | (c) app-side prefix intersection, literal |
|---|---|---|---|
| n=2 glob | 60.3 · 3782r · 5b | 107.2 · 3782r · 9b | 53.6 · 3782r · 59b |
| n=2 grep | 72.8 · 1559r · 5b | 97.9 · 1559r · 9b | 24.8 · 1559r · 59b |
| n=2 join-back K=1000 | 25.1 [first 373] · 207r · 1002b | 473.3 (2 stmts) [first 1485] · 207r · 2067b | 17.3 [first 505] · 207r · 1056b |
| n=5 glob | 94.0 · 3782r · 8b | 251.8 · 3782r · 12b | 54.7 · 3782r · 68b |
| n=5 grep | 70.4 · 1559r · 8b | 199.1 · 1559r · 12b | 25.4 · 1559r · 68b |
| n=5 join-back K=1000 | 23.6 [first 350] · 207r · 1005b | 1182.9 (2 stmts) [first 2397] · 207r · 2067b | 15.7 [first 518] · 207r · 1065b |
| n=20 glob | 259.9 · 3782r · 23b | 739.5 · 3782r · 27b | 56.9 [first 124] · 3782r · 233b |
| n=20 grep | 146.3 · 1559r · 23b | 732.9 · 1559r · 27b | 15.3 [first 85] · 1559r · 233b |
| n=20 join-back K=1000 | 35.4 [first 440] · 207r · 1020b | 1658.8 (2 stmts) [first 4170] · 207r · 2067b | 21.0 [first 645] · 207r · 1230b |

### Plan shapes

| query | plan skeleton |
|---|---|
| grep · exists | `Nested Loops>Clustered Index Scan>Concatenation>Filter>Constant Scan>Index Seek / objs: entry grant / CONVERT_IMPLICIT / est=6019` |
| glob · exists | `Nested Loops>Clustered Index Scan>Concatenation>Filter>Constant Scan>Index Seek / objs: entry grant / CONVERT_IMPLICIT / est=6024` |
| glob · literal_like | `Filter>Clustered Index Scan / objs: entry / CONVERT_IMPLICIT / est=3809` |
| glob · literal_range | `Filter>Clustered Index Scan / objs: entry / CONVERT_IMPLICIT / est=3810` |
| grep · materialised | `Nested Loops>Clustered Index Scan>Concatenation>Filter>Constant Scan>Index Seek / objs: entry vis / CONVERT_IMPLICIT / est=6019` |
| grep · groups subquery | `Nested Loops>Clustered Index Scan>Concatenation>Filter>Constant Scan>Compute Scalar>Table Scan>Index Seek / objs: entry grantg member / CONVERT_IMPLICIT / est=6019` |
| glob · set n=5 AND | `Nested Loops>Clustered Index Scan>Concatenation>Filter>Constant Scan>Index Seek / objs: entry grant / abort=TimeOut / CONVERT_IMPLICIT / est=6024` |
| glob · set n=5 HAVING | `Nested Loops>Filter>Compute Scalar>Stream Aggregate>Sort>Concatenation>Merge Interval>Constant Scan>Index Seek>Clustered Index Seek / objs: entry grant / abort=GoodEnoughPlanFound / CONVERT_IMPLICIT / est=1` |
| glob · set n=5 app | `Filter>Nested Loops>Merge Join>Sort>Compute Scalar>Constant Scan>Index Seek>Index Scan>Clustered Index Seek / objs: entry / CONVERT_IMPLICIT / est=3791` |
| join-back K=1000 IN · exists | `Nested Loops>Merge Interval>Sort>Compute Scalar>Concatenation>Constant Scan>Clustered Index Seek>Filter>Index Seek / objs: entry grant / abort=GoodEnoughPlanFound / CONVERT_IMPLICIT / est=1000` |
| join-back K=1000 VALUES · exists | `Nested Loops>Merge Join>Clustered Index Scan>Sort>Constant Scan>Concatenation>Filter>Index Seek / objs: entry grant / abort=TimeOut / est=1000` |

### 6. Bind budgets at a 10k batch, n = 20, G = grants per principal

| shape | binds | on this engine | respects membership_budget? |
|---|---|---|---|
| read: owner OR EXISTS | 1 | 1 | yes |
| read: literal prefixes (LIKE) | 1 + 2G | 35 (G = 17, corpus max) | yes while 1 + 2G ≤ 2067; needs a per-principal grant cap or an EXISTS fallback |
| read: literal prefixes (range) | 1 + 3G | 52 | same |
| join-back IN, EXISTS | chunk + 1 | 2001 per statement, 5 statements at K = 10k | yes (chunked) |
| join-back VALUES, EXISTS | chunk + 1 | 2001, 5 statements | yes (chunked) |
| write check, one path | 1 + depth | ≤ 10 | yes |
| write check, 10k batch as chunked IN | 1 + chunk | 2001, 10 statements (18,526 distinct ancestors) | yes (chunked) |
| write check, grants fetched once | 1 | 1 | yes; app resolves |
| groups: membership subquery | 1 | 1 | yes |
| groups: literal group ids | 1 + |groups(p)| | 3 here | yes while |groups(p)| ≤ budget |
| set (a) AND of n EXISTS | n | 20 | yes |
| set (b) HAVING, scoped | n + 1 + copies × filter | 21 + 3 × chunk on join-back → chunk ≤ 682 | yes only if the candidate list is chunked at a third of the budget |
| set (c) app-side intersection | ≤ 2|∩| + Σ_i (1 + 2|∩_{-i}|) | measured: 229 at n = 20 | yes while n × G stays under the budget; worst case (n+1) × 2G |

Wall clock for this run: 11.3 min.



## oracle — 111,569 entry rows (75,000 files, 36,569 directories)

Dialect `oracle`: parameter budget 32700, in-list budget 1000, membership budget 1000. Grants: flat 96,772 rows (9.7 per principal), groups form 49,777 grant rows + 23,415 memberships, groups expanded 232,993 rows. Typical principal `p00010` owns 398 rows, 8 grants, 8 minimal prefixes, 20,471 rows visible by grant. Heavy principal `p00000` owns 10,961 rows. Median over 3 warm runs, ms, rows fetched to the client.

Load: entry 0.7s, grant 0.3s, grantg 0.1s, grantgx 0.6s, member 0.0s, vis 0.1s, vis_rows 40,972, index+stats 1.3s

### 1(a-c). Read predicate on list / glob / grep (typical principal)

| filter | none (0 binds) | exists (1 binds) | literal_like (17 binds) | literal_range (25 binds) | materialised (1 binds) |
|---|---|---|---|---|---|
| list | 14.8 · 2037r | 16.2 · 2037r | 15.7 · 2037r | 15.6 · 2037r | 18.6 · 2037r |
| glob | 38.0 · 3782r | 40.0 · 3782r | 39.2 · 3782r | 35.8 · 3782r | 41.0 · 3782r |
| grep | 46.7 · 7072r | 23.7 · 1588r | 19.0 [first 58] · 1588r | 17.7 · 1588r | 17.5 · 1588r |

Heavy principal `p00000` (10,961 owned rows):

| filter | none | exists | materialised |
|---|---|---|---|
| list | 15.0 · 2037r | 16.8 · 2037r | 17.2 · 2037r |
| grep | 46.2 · 7072r | 28.5 · 2114r | 21.8 · 2114r |

### 1(d). Ranked join-back: candidate ids filtered by the predicate, chunked by the membership budget

| candidates / form | none | exists | literal_like | materialised |
|---|---|---|---|---|
| K=256 IN | 8.1 · 256r | 2.7 · 58r | 9.6 [first 67] · 58r | 2.9 · 58r |
| K=256 VALUES | 3.5 · 256r | 5.5 [first 112] · 58r | 10.8 [first 100] · 58r | 5.2 [first 123] · 58r |
| K=1000 IN | 15.6 · 1000r | 9.3 [first 163] · 209r | 13.3 [first 248] · 209r | 8.4 [first 118] · 209r |
| K=1000 VALUES | 11.3 [first 374] · 1000r | 10.1 [first 1492] · 209r | 14.6 [first 1325] · 209r | 10.3 [first 1568] · 209r |
| K=3000 IN | 45.0 (3 stmts) · 3000r | 22.8 (3 stmts) · 659r | 48.8 (3 stmts) · 659r | 21.7 (3 stmts) · 659r |
| K=3000 VALUES | 55.2 (3 stmts) · 3000r | 35.3 (3 stmts) · 659r | 51.4 (3 stmts) · 659r | 28.4 (3 stmts) · 659r |

### 2. Write point check (longest matching prefix)

| form | cost | statements | binds per statement |
|---|---|---|---|
| one path: `principal_id = :p AND path_prefix IN (ancestors)` | 0.67 ms median per check (200 distinct paths, mean 0.81) | 1 | 1 + depth (≤ 9) |
| 10k paths: distinct ancestors chunked `IN` | 86.0 ms total (18,526 distinct prefixes) | 19 | 1 + 1000 |
| 10k paths: fetch the caller's grants once, resolve in app | 2.0 ms query (8 rows) + 11.1 ms app resolve | 1 | 1 |

### 3. Materialised `visible(principal_id, entry_id)`: size and maintenance

| quantity | value |
|---|---|
| entry rows | 111,569 |
| exhaustive visible rows, flat grants (direct + 5 everyone grants) | 206,669,891 (1,852× the entry table) |
|   of which the 5 everyone grants × 10,000 principals | 204,801,194 |
|   direct grants only | 1,868,697 (16.7× the entry table) |
| exhaustive visible rows, groups expanded | 210,875,714 |
| sample loaded for the read tests (2 principals) | 40,972 rows in 0.1s |
| insert one grant's rows: typical direct grant (`/t022/src/docs/lib`) | 1.3 ms for 3 rows |
| insert one grant's rows: wide grant /t000, one principal (`/t000`) | 14.5 ms for 15,481 rows |
| a new everyone grant on /t000 | 15,481 rows × 10,000 principals = 154,810,000 rows, ≈ 145 s at the measured per-principal rate |

### 4. Groups: three encodings of the same rights (typical principal, 2 groups)

| filter | flat expanded (exists over grantgx) (1 binds) | membership subquery (1 binds) | groups literal (4 binds) |
|---|---|---|---|
| glob | 36.9 [first 82] · 3782r | 1625.4 · 3782r | 40.7 · 3782r |
| grep | 23.9 · 1590r | 37536.0 · 1590r | 38.9 · 1590r |
| join-back K=1000 IN | 13.0 [first 171] · 209r | 5487.5 · 209r | 14.8 [first 165] · 209r |

### 5. Subject set: a right held by every principal in the set (b = binds per statement)

| set / filter | (a) AND of n EXISTS | (b) grouped HAVING COUNT(DISTINCT) = n | (c) app-side prefix intersection, literal |
|---|---|---|---|
| n=2 glob | 48.3 · 3782r · 5b | 98310.0 [capped after first run 98s] · 3782r · 9b | 34.5 · 3782r · 59b |
| n=2 grep | 25.5 · 1559r · 5b | 37.6 · 1559r · 9b | 24.7 [first 65] · 1559r · 59b |
| n=2 join-back K=1000 | 8.3 [first 729] · 207r · 1002b | 12.8 [first 352] · 207r · 3003b | 20.9 [first 1990] · 207r · 1056b |
| n=5 glob | 44.3 · 3782r · 8b | 163493.8 [capped after first run 163s] · 3782r · 12b | 43.1 · 3782r · 68b |
| n=5 grep | 30.5 · 1559r · 8b | 71.1 · 1559r · 12b | 34.4 [first 78] · 1559r · 68b |
| n=5 join-back K=1000 | 8.0 · 207r · 1005b | 22.2 [first 356] · 207r · 3006b | 30.4 [first 2260] · 207r · 1065b |
| n=20 glob | 93.1 · 3782r · 23b | 499370.8 [capped after first run 499s] · 3782r · 27b | 49.1 · 3782r · 233b |
| n=20 grep | 42.2 · 1559r · 23b | 204.7 · 1559r · 27b | 33.2 · 1559r · 233b |
| n=20 join-back K=1000 | 10.2 · 207r · 1020b | 45.3 [first 372] · 207r · 3021b | 7.9 · 207r · 1230b |

### Plan shapes

| query | plan skeleton |
|---|---|
| grep · exists | `SELECT STATEMENT~7 > FILTER > FILTER > TABLE ACCESS FULL[ENTRY]~138 > INDEX RANGE SCAN[GRANT_PP]~1` |
| glob · exists | `SELECT STATEMENT~35 > FILTER > TABLE ACCESS BY INDEX ROWID BATCHED[ENTRY]~688 > BITMAP CONVERSION TO ROWIDS > BITMAP AND > BITMAP CONVERSION FROM ROWIDS > SORT ORDER BY > INDEX RANGE SCAN[ENTRY_PATH]~1004 > BITMAP CONVERSION FROM ROWIDS > INDEX RANGE SCAN[ENTRY_EXT_KIND]~1004 > INDEX RANGE SCAN[GRAN` |
| glob · literal_like | `SELECT STATEMENT~232 > TABLE ACCESS BY INDEX ROWID BATCHED[ENTRY]~232 > BITMAP CONVERSION TO ROWIDS > BITMAP AND > BITMAP CONVERSION FROM ROWIDS > SORT ORDER BY > INDEX RANGE SCAN[ENTRY_PATH]~1004 > BITMAP CONVERSION FROM ROWIDS > INDEX RANGE SCAN[ENTRY_EXT_KIND]~1004` |
| glob · literal_range | `SELECT STATEMENT~14 > TABLE ACCESS BY INDEX ROWID BATCHED[ENTRY]~14 > BITMAP CONVERSION TO ROWIDS > BITMAP AND > BITMAP CONVERSION FROM ROWIDS > SORT ORDER BY > INDEX RANGE SCAN[ENTRY_PATH]~1004 > BITMAP CONVERSION FROM ROWIDS > INDEX RANGE SCAN[ENTRY_EXT_KIND]~1004 > BITMAP OR > BITMAP CONVERSION F` |
| grep · materialised | `SELECT STATEMENT~139 > VIEW[VW_ORE_38F5D95B]~139 > FILTER > TABLE ACCESS BY INDEX ROWID BATCHED[ENTRY]~1 > INDEX RANGE SCAN[ENTRY_OWNER]~93 > FILTER > NESTED LOOPS SEMI~138 > TABLE ACCESS FULL[ENTRY]~138 > INDEX UNIQUE SCAN[VIS]~1` |
| grep · groups subquery | `SELECT STATEMENT~7 > FILTER > FILTER > TABLE ACCESS FULL[ENTRY]~138 > FILTER > INDEX SKIP SCAN[GRANTG_PP]~21 > INDEX RANGE SCAN[MEMBER_P]~1` |
| glob · set n=5 AND | `SELECT STATEMENT~1 > FILTER > TABLE ACCESS BY INDEX ROWID BATCHED[ENTRY]~688 > BITMAP CONVERSION TO ROWIDS > BITMAP AND > BITMAP CONVERSION FROM ROWIDS > SORT ORDER BY > INDEX RANGE SCAN[ENTRY_PATH]~1004 > BITMAP CONVERSION FROM ROWIDS > INDEX RANGE SCAN[ENTRY_EXT_KIND]~1004 > INDEX RANGE SCAN[GRANT` |
| glob · set n=5 HAVING | `SELECT STATEMENT~7 > NESTED LOOPS~7 > NESTED LOOPS~7 > VIEW[VW_NSO_1]~7 > HASH GROUP BY~7 > VIEW[VM_NWVW_2]~1714 > HASH GROUP BY~1714 > VIEW~1714 > HASH UNIQUE~1714 > NESTED LOOPS~1711 > INLIST ITERATOR > INDEX RANGE SCAN[GRANT_PP]~48 > TABLE ACCESS BY INDEX ROWID BATCHED[ENTRY] > INDEX RANGE SCAN[E` |
| glob · set n=5 app | `SELECT STATEMENT~156 > TABLE ACCESS BY INDEX ROWID BATCHED[ENTRY]~156 > BITMAP CONVERSION TO ROWIDS > BITMAP AND > BITMAP CONVERSION FROM ROWIDS > SORT ORDER BY > INDEX RANGE SCAN[ENTRY_PATH]~1004 > BITMAP CONVERSION FROM ROWIDS > INDEX RANGE SCAN[ENTRY_EXT_KIND]~1004` |
| join-back K=1000 IN · exists | `SELECT STATEMENT~51 > FILTER > INLIST ITERATOR > TABLE ACCESS BY INDEX ROWID[ENTRY]~1000 > INDEX UNIQUE SCAN[SYS_C0070268]~1000 > INDEX RANGE SCAN[GRANT_PP]~1` |
| join-back K=1000 VALUES · exists | `SELECT STATEMENT~51 > FILTER > HASH JOIN~1000 > VIEW~1000 > VALUES SCAN~1000 > TABLE ACCESS FULL[ENTRY]~111K > INDEX RANGE SCAN[GRANT_PP]~1` |

### 6. Bind budgets at a 10k batch, n = 20, G = grants per principal

| shape | binds | on this engine | respects membership_budget? |
|---|---|---|---|
| read: owner OR EXISTS | 1 | 1 | yes |
| read: literal prefixes (LIKE) | 1 + 2G | 35 (G = 17, corpus max) | yes while 1 + 2G ≤ 32668; needs a per-principal grant cap or an EXISTS fallback |
| read: literal prefixes (range) | 1 + 3G | 52 | same |
| join-back IN, EXISTS | chunk + 1 | 1001 per statement, 10 statements at K = 10k | yes (chunked) |
| join-back VALUES, EXISTS | chunk + 1 | 1001, 10 statements | yes (chunked) |
| write check, one path | 1 + depth | ≤ 10 | yes |
| write check, 10k batch as chunked IN | 1 + chunk | 1001, 19 statements (18,526 distinct ancestors) | yes (chunked) |
| write check, grants fetched once | 1 | 1 | yes; app resolves |
| groups: membership subquery | 1 | 1 | yes |
| groups: literal group ids | 1 + |groups(p)| | 3 here | yes while |groups(p)| ≤ budget |
| set (a) AND of n EXISTS | n | 20 | yes |
| set (b) HAVING, scoped | n + 1 + copies × filter | 21 + 3 × chunk on join-back → chunk ≤ 10882 | yes only if the candidate list is chunked at a third of the budget |
| set (c) app-side intersection | ≤ 2|∩| + Σ_i (1 + 2|∩_{-i}|) | measured: 229 at n = 20 | yes while n × G stays under the budget; worst case (n+1) × 2G |

Wall clock for this run: 16.2 min.



## sqlite — 994,923 entry rows (800,000 files, 194,923 directories)

Dialect `sqlite`: parameter budget 32700, in-list budget 32766, membership budget 32668. Grants: flat 96,700 rows (9.7 per principal), groups form 49,705 grant rows + 23,641 memberships, groups expanded 223,143 rows. Typical principal `p00031` owns 339 rows, 8 grants, 7 minimal prefixes, 194,630 rows visible by grant. Heavy principal `p00000` owns 64,433 rows. Median over 3 warm runs, ms, rows fetched to the client.

Load: entry 3.2s, grant 0.2s, grantg 0.1s, grantgx 0.5s, member 0.0s, vis 0.9s, vis_rows 394,077, index+stats 1.9s

### 1(a-c). Read predicate on list / glob / grep (typical principal)

| filter | none (0 binds) | exists (1 binds) | literal_like (15 binds) | literal_range (22 binds) | materialised (1 binds) |
|---|---|---|---|---|---|
| list | 19.3 · 20704r | 28.0 · 20704r | 27.7 · 20704r | 29.3 · 20704r | 33.2 · 20704r |
| glob | 93.7 · 40003r | 96.5 · 40003r | 80.0 · 40003r | 79.9 · 40003r | 104.5 · 40003r |
| grep | 80.6 · 73675r | 159.7 · 16066r | 124.3 · 16066r | 121.8 · 16066r | 86.8 · 16066r |

Heavy principal `p00000` (64,433 owned rows):

| filter | none | exists | materialised |
|---|---|---|---|
| list | 18.9 · 20704r | 26.7 · 20704r | 27.9 · 20704r |
| grep | 80.3 · 73675r | 233.0 · 20821r | 87.9 · 20821r |

### 1(d). Ranked join-back: candidate ids filtered by the predicate, chunked by the membership budget

| candidates / form | none | exists | literal_like | materialised |
|---|---|---|---|---|
| K=256 IN | 0.8 · 256r | 1.2 · 65r | 1.0 · 65r | 0.9 · 65r |
| K=256 VALUES | 0.8 · 256r | 1.2 · 65r | 1.2 · 65r | 0.9 · 65r |
| K=1000 IN | 2.8 · 1000r | 4.1 · 197r | 3.0 · 197r | 3.2 · 197r |
| K=1000 VALUES | 2.8 · 1000r | 4.0 · 197r | 3.5 · 197r | 3.2 · 197r |
| K=3000 IN | 9.4 · 3000r | 12.3 · 637r | 9.9 · 637r | 9.9 [first 90] · 637r |
| K=3000 VALUES | 9.4 · 3000r | 12.6 · 637r | 11.0 · 637r | 9.5 · 637r |

### 2. Write point check (longest matching prefix)

| form | cost | statements | binds per statement |
|---|---|---|---|
| one path: `principal_id = :p AND path_prefix IN (ancestors)` | 0.17 ms median per check (200 distinct paths, mean 0.18) | 1 | 1 + depth (≤ 9) |
| 10k paths: distinct ancestors chunked `IN` | 48.6 ms total (18,596 distinct prefixes) | 1 | 1 + 32668 |
| 10k paths: fetch the caller's grants once, resolve in app | 0.2 ms query (8 rows) + 11.1 ms app resolve | 1 | 1 |

### 3. Materialised `visible(principal_id, entry_id)`: size and maintenance

| quantity | value |
|---|---|
| entry rows | 994,923 |
| exhaustive visible rows, flat grants (direct + 5 everyone grants) | 1,959,014,205 (1,969× the entry table) |
|   of which the 5 everyone grants × 10,000 principals | 1,947,317,924 |
|   direct grants only | 11,696,281 (11.8× the entry table) |
| exhaustive visible rows, groups expanded | 1,973,380,552 |
| sample loaded for the read tests (2 principals) | 394,077 rows in 0.9s |
| insert one grant's rows: typical direct grant (`/t158/models`) | 0.2 ms for 5 rows |
| insert one grant's rows: wide grant /t000, one principal (`/t000`) | 93.0 ms for 149,339 rows |
| a new everyone grant on /t000 | 149,339 rows × 10,000 principals = 1,493,390,000 rows, ≈ 930 s at the measured per-principal rate |

### 4. Groups: three encodings of the same rights (typical principal, 3 groups)

| filter | flat expanded (exists over grantgx) (1 binds) | membership subquery (1 binds) | groups literal (5 binds) |
|---|---|---|---|
| glob | 95.7 · 40003r | 286.9 · 40003r | 234.9 · 40003r |
| grep | 349.0 · 16223r | 499.7 · 16223r | 448.3 · 16223r |
| join-back K=1000 IN | 7.7 · 199r | 9.2 · 199r | 8.4 · 199r |

### 5. Subject set: a right held by every principal in the set (b = binds per statement)

| set / filter | (a) AND of n EXISTS | (b) grouped HAVING COUNT(DISTINCT) = n | (c) app-side prefix intersection, literal |
|---|---|---|---|
| n=2 glob | 112.9 · 40003r · 5b | 317.0 · 40003r · 9b | 81.7 · 40003r · 57b |
| n=2 grep | 205.6 · 16043r · 5b | 396.0 · 16043r · 9b | 117.0 · 16043r · 57b |
| n=2 join-back K=1000 | 4.9 · 196r · -30664b | 9.4 · 196r · -26661b | 3.2 · 196r · -30560b |
| n=5 glob | 159.5 · 40003r · 8b | 618.1 · 40003r · 12b | 79.3 · 40003r · 68b |
| n=5 grep | 287.9 · 16043r · 8b | 812.6 · 16043r · 12b | 117.7 · 16043r · 68b |
| n=5 join-back K=1000 | 5.8 · 196r · -30658b | 14.6 · 196r · -26655b | 3.3 · 196r · -30538b |
| n=20 glob | 431.5 · 40003r · 23b | 2193.1 · 40003r · 27b | 78.4 [first 204] · 40003r · 233b |
| n=20 grep | 323.9 · 16043r · 23b | 2989.3 · 16043r · 27b | 117.4 · 16043r · 233b |
| n=20 join-back K=1000 | 6.8 · 196r · -30628b | 44.8 · 196r · -26625b | 4.7 · 196r · -30208b |

### Plan shapes

| query | plan skeleton |
|---|---|
| grep · exists | `SCAN e / CORRELATED SCALAR SUBQUERY 1 / SEARCH g USING COVERING INDEX ix_vfs_s1_310cb02b_grant_pp (principal_id=?)` |
| glob · exists | `SEARCH e USING INDEX ux_vfs_s1_310cb02b_entry_path (path>? AND path<?) / CORRELATED SCALAR SUBQUERY 1 / SEARCH g USING COVERING INDEX ix_vfs_s1_310cb02b_grant_pp (principal_id=?)` |
| glob · literal_like | `SEARCH e USING INDEX ux_vfs_s1_310cb02b_entry_path (path>? AND path<?)` |
| glob · literal_range | `SEARCH e USING INDEX ux_vfs_s1_310cb02b_entry_path (path>? AND path<?)` |
| grep · materialised | `SCAN e / CORRELATED SCALAR SUBQUERY 1 / SEARCH v USING COVERING INDEX ux_vfs_s1_310cb02b_vis (principal_id=? AND entry_id=?)` |
| grep · groups subquery | `SCAN e / CORRELATED SCALAR SUBQUERY 2 / MULTI-INDEX OR / INDEX 1 / SEARCH g USING COVERING INDEX ix_vfs_s1_310cb02b_grantg_pp (principal_id=?) / INDEX 2 / LIST SUBQUERY 1 / SEARCH m USING COVERING INDEX ix_vfs_s1_310cb02b_member_p (principal_id=?) / CREATE BLOOM FILTER / SEARCH g USING COVERING INDEX ix_vfs_s1_310cb02b_grantg_pp (principal_id=?)` |
| glob · set n=5 AND | `SEARCH e USING INDEX ux_vfs_s1_310cb02b_entry_path (path>? AND path<?) / CORRELATED SCALAR SUBQUERY 1 / SEARCH g USING COVERING INDEX ix_vfs_s1_310cb02b_grant_pp (principal_id=?) / CORRELATED SCALAR SUBQUERY 2 / SEARCH g USING COVERING INDEX ix_vfs_s1_310cb02b_grant_pp (principal_id=?) / CORRELATED SCALAR SUBQUERY 3 / SEARCH g USING COVERING INDEX ix_vfs_s1_310cb02b_grant_pp (principal_id=?) / COR` |
| glob · set n=5 HAVING | `SEARCH e USING INTEGER PRIMARY KEY (rowid=?) / LIST SUBQUERY 3 / CO-ROUTINE x / COMPOUND QUERY / LEFT-MOST SUBQUERY / SEARCH e2 USING INDEX ux_vfs_s1_310cb02b_entry_path (path>? AND path<?) / SEARCH g USING COVERING INDEX ix_vfs_s1_310cb02b_grant_pp (principal_id=?) / UNION USING TEMP B-TREE / SEARCH e3 USING INDEX ix_vfs_s1_310cb02b_entry_owner (owner_id=?) / SCAN x / USE TEMP B-TREE FOR GROUP BY` |
| glob · set n=5 app | `SEARCH e USING INDEX ux_vfs_s1_310cb02b_entry_path (path>? AND path<?)` |
| join-back K=1000 IN · exists | `SEARCH e USING INTEGER PRIMARY KEY (rowid=?) / CORRELATED SCALAR SUBQUERY 1 / SEARCH g USING COVERING INDEX ix_vfs_s1_310cb02b_grant_pp (principal_id=?)` |
| join-back K=1000 VALUES · exists | `CO-ROUTINE cte / SCAN 1000 CONSTANT ROWS / SCAN cte / SEARCH e USING INTEGER PRIMARY KEY (rowid=?) / CORRELATED SCALAR SUBQUERY 1002 / SEARCH g USING COVERING INDEX ix_vfs_s1_310cb02b_grant_pp (principal_id=?)` |

### 6. Bind budgets at a 10k batch, n = 20, G = grants per principal

| shape | binds | on this engine | respects membership_budget? |
|---|---|---|---|
| read: owner OR EXISTS | 1 | 1 | yes |
| read: literal prefixes (LIKE) | 1 + 2G | 35 (G = 17, corpus max) | yes while 1 + 2G ≤ 32668; needs a per-principal grant cap or an EXISTS fallback |
| read: literal prefixes (range) | 1 + 3G | 52 | same |
| join-back IN, EXISTS | chunk + 1 | 32669 per statement, 1 statements at K = 10k | yes (chunked) |
| join-back VALUES, EXISTS | chunk + 1 | 32669, 1 statements | yes (chunked) |
| write check, one path | 1 + depth | ≤ 10 | yes |
| write check, 10k batch as chunked IN | 1 + chunk | 32669, 1 statements (18,596 distinct ancestors) | yes (chunked) |
| write check, grants fetched once | 1 | 1 | yes; app resolves |
| groups: membership subquery | 1 | 1 | yes |
| groups: literal group ids | 1 + |groups(p)| | 4 here | yes while |groups(p)| ≤ budget |
| set (a) AND of n EXISTS | n | 20 | yes |
| set (b) HAVING, scoped | n + 1 + copies × filter | 21 + 3 × chunk on join-back → chunk ≤ 10882 | yes only if the candidate list is chunked at a third of the budget |
| set (c) app-side intersection | ≤ 2|∩| + Σ_i (1 + 2|∩_{-i}|) | measured: 229 at n = 20 | yes while n × G stays under the budget; worst case (n+1) × 2G |

Wall clock for this run: 1.2 min.



## postgres — 994,923 entry rows (800,000 files, 194,923 directories)

Dialect `postgresql`: parameter budget 32700, in-list budget 65535, membership budget 32668. Grants: flat 96,700 rows (9.7 per principal), groups form 49,705 grant rows + 23,641 memberships, groups expanded 223,143 rows. Typical principal `p00031` owns 339 rows, 8 grants, 7 minimal prefixes, 194,630 rows visible by grant. Heavy principal `p00000` owns 64,433 rows. Median over 3 warm runs, ms, rows fetched to the client.

Load: entry 7.0s, grant 0.4s, grantg 0.3s, grantgx 1.0s, member 0.1s, vis 1.7s, vis_rows 394,077, index+stats 2.1s

### 1(a-c). Read predicate on list / glob / grep (typical principal)

| filter | none (0 binds) | exists (1 binds) | literal_like (15 binds) | literal_range (22 binds) | materialised (1 binds) |
|---|---|---|---|---|---|
| list | 31.3 · 20704r | 155.0 · 20704r | 33.2 · 20704r | 31.7 · 20704r | 129.2 · 20704r |
| glob | 45.7 [first 96] · 40003r | 234.3 · 40003r | 37.8 · 40003r | 74.8 · 40003r | 103.3 · 40003r |
| grep | 93.3 · 73675r | 519.3 · 16066r | 35.8 · 16066r | 34.7 · 16066r | 239.4 · 16066r |

Heavy principal `p00000` (64,433 owned rows):

| filter | none | exists | materialised |
|---|---|---|---|
| list | 30.3 · 20704r | 170.3 · 20704r | 125.7 · 20704r |
| grep | 104.8 · 73675r | 578.1 · 20821r | 247.1 · 20821r |

### 1(d). Ranked join-back: candidate ids filtered by the predicate, chunked by the membership budget

| candidates / form | none | exists | literal_like | materialised |
|---|---|---|---|---|
| K=256 IN | 2.4 · 256r | 4.0 · 65r | 2.3 · 65r | 2.6 · 65r |
| K=256 VALUES | 2.4 · 256r | 3.5 · 65r | 2.6 · 65r | 2.7 · 65r |
| K=1000 IN | 5.3 · 1000r | 9.6 · 197r | 5.4 · 197r | 48.3 · 197r |
| K=1000 VALUES | 5.6 · 1000r | 11.3 · 197r | 6.8 · 197r | 8.4 · 197r |
| K=3000 IN | 14.4 · 3000r | 33.1 · 637r | 14.4 · 637r | 53.0 · 637r |
| K=3000 VALUES | 48.2 · 3000r | 35.0 · 637r | 16.3 · 637r | 18.4 · 637r |

### 2. Write point check (longest matching prefix)

| form | cost | statements | binds per statement |
|---|---|---|---|
| one path: `principal_id = :p AND path_prefix IN (ancestors)` | 0.61 ms median per check (200 distinct paths, mean 0.65) | 1 | 1 + depth (≤ 9) |
| 10k paths: distinct ancestors chunked `IN` | 64.8 ms total (18,596 distinct prefixes) | 1 | 1 + 32668 |
| 10k paths: fetch the caller's grants once, resolve in app | 1.0 ms query (8 rows) + 11.0 ms app resolve | 1 | 1 |

### 3. Materialised `visible(principal_id, entry_id)`: size and maintenance

| quantity | value |
|---|---|
| entry rows | 994,923 |
| exhaustive visible rows, flat grants (direct + 5 everyone grants) | 1,959,014,205 (1,969× the entry table) |
|   of which the 5 everyone grants × 10,000 principals | 1,947,317,924 |
|   direct grants only | 11,696,281 (11.8× the entry table) |
| exhaustive visible rows, groups expanded | 1,973,380,552 |
| sample loaded for the read tests (2 principals) | 394,077 rows in 1.7s |
| insert one grant's rows: typical direct grant (`/t158/models`) | 1.4 ms for 5 rows |
| insert one grant's rows: wide grant /t000, one principal (`/t000`) | 291.0 ms for 149,339 rows |
| a new everyone grant on /t000 | 149,339 rows × 10,000 principals = 1,493,390,000 rows, ≈ 2,910 s at the measured per-principal rate |

### 4. Groups: three encodings of the same rights (typical principal, 3 groups)

| filter | flat expanded (exists over grantgx) (1 binds) | membership subquery (1 binds) | groups literal (5 binds) |
|---|---|---|---|
| glob | 191.6 · 40003r | 196485.2 [capped after first run 196s] · 40003r | 358.3 · 40003r |
| grep | 513.4 · 16223r | 373563.0 [capped after first run 374s] · 16223r | 873.0 · 16223r |
| join-back K=1000 IN | 9.5 · 199r | 4244.4 · 199r | 19.4 · 199r |

### 5. Subject set: a right held by every principal in the set (b = binds per statement)

| set / filter | (a) AND of n EXISTS | (b) grouped HAVING COUNT(DISTINCT) = n | (c) app-side prefix intersection, literal |
|---|---|---|---|
| n=2 glob | 238.2 · 40003r · 5b | 181.5 · 40003r · 9b | 157.1 · 40003r · 57b |
| n=2 grep | 435.3 · 16043r · 5b | 174.3 · 16043r · 9b | 40.3 · 16043r · 57b |
| n=2 join-back K=1000 | 9.7 · 196r · -30664b | 10.9 · 196r · -26661b | 5.4 · 196r · -30560b |
| n=5 glob | 538.8 · 40003r · 8b | 306.1 · 40003r · 12b | 162.1 · 40003r · 68b |
| n=5 grep | 595.7 · 16043r · 8b | 337.1 · 16043r · 12b | 39.8 · 16043r · 68b |
| n=5 join-back K=1000 | 10.1 · 196r · -30658b | 12.4 · 196r · -26655b | 5.8 [first 140] · 196r · -30538b |
| n=20 glob | 2104.7 · 40003r · 23b | 1200.5 · 40003r · 27b | 46.7 · 40003r · 233b |
| n=20 grep | 1264.0 · 16043r · 23b | 1555.4 · 16043r · 27b | 48.1 · 16043r · 233b |
| n=20 join-back K=1000 | 17.1 · 196r · -30628b | 24.7 · 196r · -26625b | 7.2 · 196r · -30208b |

### Plan shapes

| query | plan skeleton |
|---|---|
| grep · exists | `Index Scan[entry](entry_ext_kind) > Index Only Scan[grant](grant_pp)x73657 [361.584 ms]` |
| glob · exists | `Bitmap Heap Scan[entry] > BitmapAnd > Bitmap Index Scan[ix_entry_ext_kind] > Bitmap Index Scan[ux_entry_path] > Index Only Scan[grant](grant_pp)x40003 [118.679 ms]` |
| glob · literal_like | `Bitmap Heap Scan[entry] > BitmapAnd > Bitmap Index Scan[ix_entry_ext_kind] > Bitmap Index Scan[ux_entry_path] [23.779 ms]` |
| glob · literal_range | `Bitmap Heap Scan[entry] > BitmapAnd > Bitmap Index Scan[ix_entry_ext_kind] > Bitmap Index Scan[ux_entry_path] [22.021 ms]` |
| grep · materialised | `Index Scan[entry](entry_ext_kind) > Seq Scan[vis] [233.468 ms]` |
| grep · groups subquery | `Index Scan[entry](entry_ext_kind) > Seq Scan[grantg]x73657 > Index Only Scan[member](member_p) [358102.665 ms]` |
| glob · set n=5 AND | `Bitmap Heap Scan[entry] > BitmapAnd > Bitmap Index Scan[ix_entry_ext_kind] > Bitmap Index Scan[ux_entry_path] > Index Only Scan[grant](grant_pp)x40003 > Index Only Scan[grant](grant_pp)x40003 > Index Only Scan[grant](grant_pp)x40003 > Index Only Scan[grant](grant_pp)x40003 > Index Only Scan[grant](g [532.788 ms]` |
| glob · set n=5 HAVING | `Nested > GroupAggregate > Unique > Sort > Append > Nested > Bitmap Heap Scan[entry] > Bitmap Index Scan[ix_entry_ext_kind] > Materializex40003 > Index Only Scan[grant](grant_pp) > Bitmap Heap Scan[entry] > Bitmap Index Scan[ix_entry_owner] > Index Scan[entry](vfs_s1_d9167580_entry_pkey)x40003 [419.083 ms]` |
| glob · set n=5 app | `Gather > Parallel Bitmap Heap Scan[entry]x3 > BitmapAnd > Bitmap Index Scan[ix_entry_ext_kind] > Bitmap Index Scan[ux_entry_path] [22.697 ms]` |
| join-back K=1000 IN · exists | `Index Scan[entry](vfs_s1_d9167580_entry_pkey) > Index Only Scan[grant](grant_pp)x999 [4.700 ms]` |
| join-back K=1000 VALUES · exists | `Nested > Values Scan["*VALUES*"] > Index Scan[entry](vfs_s1_d9167580_entry_pkey)x1000 > Index Only Scan[grant](grant_pp)x999 [4.588 ms]` |

### 6. Bind budgets at a 10k batch, n = 20, G = grants per principal

| shape | binds | on this engine | respects membership_budget? |
|---|---|---|---|
| read: owner OR EXISTS | 1 | 1 | yes |
| read: literal prefixes (LIKE) | 1 + 2G | 35 (G = 17, corpus max) | yes while 1 + 2G ≤ 32668; needs a per-principal grant cap or an EXISTS fallback |
| read: literal prefixes (range) | 1 + 3G | 52 | same |
| join-back IN, EXISTS | chunk + 1 | 32669 per statement, 1 statements at K = 10k | yes (chunked) |
| join-back VALUES, EXISTS | chunk + 1 | 32669, 1 statements | yes (chunked) |
| write check, one path | 1 + depth | ≤ 10 | yes |
| write check, 10k batch as chunked IN | 1 + chunk | 32669, 1 statements (18,596 distinct ancestors) | yes (chunked) |
| write check, grants fetched once | 1 | 1 | yes; app resolves |
| groups: membership subquery | 1 | 1 | yes |
| groups: literal group ids | 1 + |groups(p)| | 4 here | yes while |groups(p)| ≤ budget |
| set (a) AND of n EXISTS | n | 20 | yes |
| set (b) HAVING, scoped | n + 1 + copies × filter | 21 + 3 × chunk on join-back → chunk ≤ 10882 | yes only if the candidate list is chunked at a third of the budget |
| set (c) app-side intersection | ≤ 2|∩| + Σ_i (1 + 2|∩_{-i}|) | measured: 229 at n = 20 | yes while n × G stays under the budget; worst case (n+1) × 2G |

Wall clock for this run: 17.2 min.


