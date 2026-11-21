# Round 3: adversarial review of the grep planner design

**Verdict: Fit to build with changes.** No plan was found to return different rows from another under a view, the trash side, the meta subtree, rows awaiting the index, or a rival write and publish committed mid-call. Two findings are medium. The index fold and the matcher use different Unicode case tables, so a ladder plan loses rows that in hand returns. And decision 5's "U first" step costs in proportion to the corpus, which decision 6 does not price. Two findings are low.

The pinned code is `5dfdcc79`, and `$PIN` is the `src` of a checkout of that commit. The scripts are in `$R3 = agents/2026-11-21-grep-query-planner/reviews/scripts/round-3/`, with their output beside them as `*.out`. They run from the repository root as `PYTHONPATH=$PIN uv run python $R3/<script> <args>`. `r3_06` also needs `$R3` on `PYTHONPATH`. Every run used SQLite, and no Postgres leg was run. The load average was 4.75 during `r3_03` and 7.1 during `r3_05`, so both timings are *loaded*, and no finding rests on them. Every finding rests on counts.

## Findings, high to low

### M1. Decision 0: the index fold and the matcher's case orbit come from different Unicode tables

Scripts: `r3_01_fold_orbit.py`, `r3_02_fold_e2e.py`.

The index is folded in Python: `fold_content` (Turkic-i, then `str.casefold`), called from `indexing.py`. Its invariant is stated against `re.IGNORECASE`, and it is pinned by an orbit scan of sre. The matcher is regex-syntax 0.8.11, whose case table is Unicode 16. Python 3.13's `unicodedata` is 15.1.

`r3_01` compiles every cased codepoint through `compile_verifier` as case-insensitive, and runs it over a body that holds every codepoint. It found 54 pairs that the matcher treats as equal and the index fold does not. Examples are `ɤ ~ U+A7CB`, `ƛ ~ U+A7DC`, `U+1C89 ~ U+1C8A`, and all 44 Garay letters.

`r3_02` shows this end to end on a fresh store that was rebuilt, so every row is encoded. In each of 4 cases the ladder (`paths=`) loses a row that in hand (`observations=`) returns. No warning reaches the caller.

```
'ɤabc' case=smart         ladder ['/u/rams_lower.txt']   in hand [+ '/u/rams_upper.txt']
'ƛqrs' case=smart         ladder []                      in hand ['/u/lambda_upper.txt']
Garay, insensitive        ladder []                      in hand ['/u/garay_upper.txt']
'Ɤabc' insensitive   ladder ['/u/rams_upper.txt']   in hand [+ '/u/rams_lower.txt']
```

The fold also changes with the interpreter. `'Ɤ'.casefold()` is `'Ɤ'` on Python 3.11, 3.12 and 3.13, and `'ɤ'` on 3.14. The index is stored, so an index folded under one interpreter and planned under another fails to nominate a case-sensitive literal as well. This was shown on the fold function alone, not end to end.

Decision 0 says that one HIR walk "serves the folded gram plan". The walk is sound only if it applies the index's own fold to each class member, and it must never fold with the crate's simple case table. Rust's standard library has no full casefold: `ß` stays `ß`, while the index holds `ss` (`r3_01b`). Decision 0's differential test runs over syntax, so it cannot find this.

Changes needed:

- State the fold invariant against the matcher's case orbit, and pin it with `r3_01`'s scan run against the Rust matcher.
- Fold the index and the plan with one table, owned beside the matcher.
- Store the fold's Unicode version with the index generation, so that a change forces a rebuild.

This holds on both engines.

### M2. Decisions 5 and 6, against the reference deployment: reading U first costs in proportion to the corpus, and the cost model does not see it

Script: `r3_03_u_first_cost.py`. It runs the ladder corpus-wide with no allow-list, as decision 5 does above T. Bodies and the scan side are stubbed out.

| pattern | U | largest chosen `doc_count` | posting bytes fetched |
|---|---|---|---|
| `dentry_lru_isolate` | 85 | 5,873 | 10,317 |
| `i_count` | 6,096 | 41,807 | 117,146 |
| `return 0;` | 29,561 | 49,663 | 164,633 |
| `struct` | 57,528 | 66,833 | 246,022 |

The posting bytes follow `doc_count`, and `doc_count` follows the corpus. The figure of "about 3 ms" (R4) belongs to 94,000 files. At 10,000,000 files the same lists are about 107 times larger, up to about 26 MB for `struct`. Every scoped grep above T pays that, and on Postgres the bytes cross the wire. This is an extrapolation from these counts.

Decision 6 prices the ladder at `F_l`, the floor of a one-candidate answer. That floor leaves out these bytes. Their exact size is already in the posting metadata (`byte_size`), which is read in about 0.5 ms before any blob is fetched. Today's `_ladder_defers` uses it. Decision 6 drops it.

Change needed: price the ladder from `byte_size` before the blobs are fetched. Then let in hand, or the range ids taken as the candidate set, serve any scope whose posting bill exceeds `n·c_row`, and not only `n ≤ T`.

### L1. Decisions 3 and 5: the probe's limit applies per root

Script: `r3_07_per_root_limit.py`.

| roots | limit | rows read, a limit per root | rows returned, one limit over all roots |
|---|---|---|---|
| 24 top-level directories | 25,001 | 85,084 | 25,001 |
| 145 directories under `/drivers` | 141 (T + 1) | 9,933 | 141 |

The probe's reads are bounded by the number of roots times the limit, not by the limit. Change needed: put one `LIMIT` over the union of the roots.

### L2. Decisions 7 and 8: the literal test changes the statistic that turns it on

Script: `r3_05_cbyte_feedback.py`. It fetches one batch of 600 bodies (11,662,847 bytes) twice. Without the test, 11,662,847 bytes are returned. With `instr`, 178,811 bytes are returned, and the server still reads all 11,662,847.

`c_byte` is defined as the "observed body bytes per second of content batches". With the test on, that figure no longer measures transfer. Read per byte returned, it rose from 0.24 to 71.8 ns/B (a loaded timing), so a test that has been turned on keeps itself on. Change needed: sample `c_byte` only on batches that run without the test, or meter the bytes from `size_bytes`.

## Attacked and held

- **View, trash and `/.vfs` on a writable copy** (`r3_04_view_trash_meta.py`, with `r3_04b` and `r3_04c` beside it).
  - *The store:* 2,116 Linux files under `/pub` (posture read, with root posture none), `/team` (granted to `group:eng`, and alice is a member), `/alice` (owned by alice) and `/secret` (bob holds read on one subtree). It has 96 tombstoned files, 73 rows awaiting the index, and 14 rows under `/.vfs`.
  - *The matrix:* 4 callers (system, alice, bob, anonymous) times 13 scopes times 8 patterns. The scopes include multiple roots, a file root, trash roots and `/.vfs/ipc`. The patterns include `invert_match` and `allow_scan`. That is 1,664 greps.
  - *Rows:* today, in hand, allow-listed by range and range-scoped returned identical rows in every cell.
  - *Bodies:* no plan fetched a body outside the caller's readable set. The layout oracle agreed with `read` on every sampled file.
  - *The gap:* the router refuses an anonymous grep over `/pub` as `Unauthenticated`, but serves `/pub/late`. Anonymous coverage therefore rests on `/pub/late`. The refusal is outside this design.
- **Staleness** (`r3_06_staleness.py`). A rival committed a write, a delete and a rebuild at `grep:after-pointer-read`. All four plans returned the rows of the snapshot the call began on, and none raised `StaleSnapshot`. The verb's `BEGIN` pins one snapshot on SQLite. Postgres pins `REPEATABLE READ` (`op_isolation`), which was read, not run. On these two engines, in hand needs no generation read.
- **Decision 8's rows.** Given the parity above, the cost state changes only which plan runs, never the rows, except where the wall truncates. The state is read on one event loop.
- **A root of `/`**, where the range would be the degenerate `//` to `/0`, never reaches the seam, because `admit_scope` refuses it.

## Not attacked

- No Postgres leg was run, and none was run with added latency.
- Decision 7's literal test was not tested under truncation, where decision 8's choice could change the rows if the test rides the scan side's capped statement.
