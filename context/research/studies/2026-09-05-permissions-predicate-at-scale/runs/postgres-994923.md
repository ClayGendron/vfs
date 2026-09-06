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
| n=2 join-back K=1000 | 9.7 · 196r · 1002b | 10.9 · 196r · 3003b | 5.4 · 196r · 1054b |
| n=5 glob | 538.8 · 40003r · 8b | 306.1 · 40003r · 12b | 162.1 · 40003r · 68b |
| n=5 grep | 595.7 · 16043r · 8b | 337.1 · 16043r · 12b | 39.8 · 16043r · 68b |
| n=5 join-back K=1000 | 10.1 · 196r · 1005b | 12.4 · 196r · 3006b | 5.8 [first 140] · 196r · 1065b |
| n=20 glob | 2104.7 · 40003r · 23b | 1200.5 · 40003r · 27b | 46.7 · 40003r · 233b |
| n=20 grep | 1264.0 · 16043r · 23b | 1555.4 · 16043r · 27b | 48.1 · 16043r · 233b |
| n=20 join-back K=1000 | 17.1 · 196r · 1020b | 24.7 · 196r · 3021b | 7.2 · 196r · 1230b |

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
