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
| n=2 join-back K=1000 | 9.8 · 207r · 32668b | 12.6 · 207r · 32667b | 6.8 · 207r · 32668b |
| n=5 glob | 50.1 · 3782r · 8b | 202.1 · 3782r · 12b | 28.1 · 3782r · 68b |
| n=5 grep | 47.2 · 1559r · 8b | 87.2 · 1559r · 12b | 23.5 · 1559r · 68b |
| n=5 join-back K=1000 | 9.6 · 207r · 32668b | 15.7 · 207r · 32667b | 5.1 [first 100] · 207r · 32668b |
| n=20 glob | 117.5 · 3782r · 23b | 1653.0 · 3782r · 27b | 28.8 · 3782r · 233b |
| n=20 grep | 75.7 · 1559r · 23b | 582.6 · 1559r · 27b | 31.0 · 1559r · 233b |
| n=20 join-back K=1000 | 16.6 · 207r · 32668b | 36.9 · 207r · 32667b | 6.4 · 207r · 32668b |

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
