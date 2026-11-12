# A dirty row costs grep about 10 µs and glean about 175 µs whatever the store size, neither verb reaches the 10 second wall inside its budget, both drop the same last-path file at their cap, and glean's cost is tokenizing in Python

Clay asked on 2026-11-09 whether glean could brute-force the dirty rows the way grep does, or whether both verbs should carry one limit past which dirty files are left out, and whether the rule should differ by store size ([the brief](00-brief.md)). This is study 02, the measured cost curve: corpora of 10,000 and 100,000 files were built and fully indexed on SQLite, dirtied by rewriting N files chosen uniformly at random for N in 500, 2,000, 5,000, 10,000 and 25,000, and five grep patterns and five glean queries were run three times at each level, with glean measured both at its default `OVERLAY_BUDGET` of 500 and with the constant lifted to 25,000 in the harness; a Postgres leg repeated the 100,000-file store at N of 10,000 and 25,000. The work took about two and a half hours of wall time, of which the SQLite runs took 10 minutes and the Postgres leg about 16 minutes of running across three attempts (a failed store clone, a compounding run whose second level under-counted, and an exact top-up level). The baseline this extends is [02-baseline-measurements](../2026-10-31-incremental-index-refresh/02-baseline-measurements.md); its approach was reused, its files were not. Everything here was run against vfs at commit b85e3df; nothing under `src/` or `tests/` was edited.

Labels: EXECUTED means a command ran here and the claim reports its output; READ means read in a cited file; INFERRED means reasoning from the two.

## Sources

Machine: Apple M1 Pro, 10 cores, 32 GB (34,359,738,368 bytes), macOS Darwin 25.5.0; Python 3.13.11 through uv; SQLite 3.50.4 through aiosqlite; SQLAlchemy 2.0.52; PostgreSQL 17.11 (Debian, aarch64) with pgvector 0.8.6 in the `vfs-test-postgres-1` Docker container at `postgresql+asyncpg://vfs:vfs@localhost:54320/vfs`, whose data directory is a 3.9 GB tmpfs. The Rust extension `vfs._native` was already built and imported cleanly (EXECUTED: `sysctl -n machdep.cpu.brand_string hw.ncpu hw.memsize`, `uv run python --version`, `uv run python -c "import sqlite3; print(sqlite3.sqlite_version)"`, `uv run python -c "import vfs._native"`, `select version()` on the server). Levels ran sequentially, never in parallel; one other light agent was reading files on the machine during the runs.

Code read for the method: `src/vfs/storage/backends/database/grep.py`, `src/vfs/storage/backends/database/glean.py`, `src/vfs/storage/backends/database/scope.py` (`entries_for_scan`), `src/vfs/storage/backends/database/reads.py` (`content_for_entries`), `src/vfs/storage/backends/database/offload.py` (`WALL_TIME_BUDGET`), `src/vfs/storage/backends/database/backend.py` (`DatabaseStorage.__init__`, `grep`, `glean`, `write`, `reindex`, `_vector_leg_for`), `src/vfs/models/lexical.py` (`tokenize`, `score_blocks`), `src/vfs/models/rows.py`, `tests/support/server_schemas.py` and `tests/conftest.py` (how the Postgres leg provisions a schema and drops it).

Scripts and raw outputs, all under [experiments/](experiments/): [corpus.py](experiments/corpus.py) (the generator), [harness.py](experiments/harness.py) (store opening, the statement counter, the phase wrappers, the SQLite copy and the Postgres schema clone), [study.py](experiments/study.py) (the driver), [tables.py](experiments/tables.py) (renders every table below from the JSON into [tables.md](experiments/tables.md)), and the results `results_sqlite_10000.json`, `results_sqlite_100000.json`, `results_postgres_100000.json`, `results_postgres_100000_exact25000.json` with their logs `log_sqlite_10000.txt`, `log_sqlite_100000.txt`, `log_postgres_100000.txt`, `log_postgres_100000_exact25000.txt` and `log_postgres_100000_attempt1_clone_diskfull.txt`. The commands, run from the `experiments/` folder: `uv run python study.py --engine sqlite --files 10000 --levels 500,2000,5000,10000`; `uv run python study.py --engine sqlite --files 100000 --levels 500,2000,5000,10000,25000`; `uv run python study.py --engine postgres --files 100000 --levels 10000,25000` (failed cloning the store, see section 8) then `uv run python study.py --engine postgres --files 100000 --levels 10000,25000 --reuse-base --compound` (its second level reached 23,401 dirty rows, see section 8) then `uv run python study.py --engine postgres --files 100000 --levels 25000 --reuse-base --compound --out results_postgres_100000_exact25000.json`; `uv run python tables.py`.

## 1. The answer in one paragraph

EXECUTED and INFERRED. On this machine a dirty row costs grep's scan tier 17 to 25 µs and about 7 KB of body read when the scan tier is the whole call, and 10 to 13 µs per dirty row on the slope of the whole five-pattern suite; it costs glean's overlay 155 to 180 µs and the same 7 KB, of which 135 to 145 µs is `_overlay_blocks`, the tokenize-and-count loop that runs once per body in Python around the Rust tokenizer, and only about 25 µs is SQL (nominee fetch, surrogate-id fetch and body fetch together). The two figures are the same on the 10,000-file and the 100,000-file store: the dirty set, not the corpus, sets the scan-tier bill, exactly as the brief's reference-scale note predicts. Neither verb reached the 10 second wall under either budget: grep's slowest call was 1.02 s and glean's 4.56 s at 25,000 dirty rows with the lifted budget, so the wall is never the operative limit; the count budgets are. The count budgets drop the same file: at 25,001 dirty rows grep (candidate budget 25,000) and glean with the lifted budget (25,000) both lost the sentinel file whose path sorts last, and glean at its default budget lost it from 501 dirty rows on, including the level with exactly 500 rewritten files plus the sentinel. glean at the default 500 is flat at about 0.1 s per call at every level, with the `overlay budget {scanned: 500, budget: 500}` record on every call. Postgres changes the constants, not the shape: it adds about 45 µs per dirty row of body transfer to both verbs (grep's scan-only pattern 65 µs a row, glean's lifted overlay 210 to 225 µs a row, the same 145 µs of it in Python), issues the same statement counts, and loses the same sentinel at 25,001 rows; its worst lifted-budget glean call at 25,000 rows was 9.4 s, so there the lifted budget and the wall meet. If glean brute-forced the dirty set the way grep does, every dirty row would cost it about 17 times what it costs grep, and about 85 per cent of that is Python work that a Rust kernel for the overlay's tokenize-and-count would remove; at that point one shared limit for both verbs would be affordable at the same number.

## 2. Method

EXECUTED. The corpus generator draws words Zipf-style (exponent 1.0, offset 10) from a seeded 30,000-word vocabulary, with 27 per cent English function words and 3 per cent code identifiers, so a query term of rank r has a real document frequency and idf. Body sizes are log-normal around a 4 KB median with sigma 1.0, clamped to 300 B and 200 KB. The 5,000-document check printed a median of 4,155 bytes, a mean of 6,803, a 90th percentile of 15,100, a 99th of 42,036 and a maximum of 186,920 bytes; a 100,000-file corpus is about 680 MB of text. Files sit in 3,600 directories (`/dAA/dBB/dCC/fNNNNNN.md`, 20 × 15 × 12), so the 10,000-file store has about 3 files a directory and the 100,000-file store about 28. Document i always has the same size class; a rewrite (`salt=1`) changes the words only.

EXECUTED. Each store was written through `DatabaseStorage.write` in batches of 10,000 entries with `parents=True`, then `reindex()` was run until the count of live file rows with `encoded = false` was zero; one run sufficed on every store. For each level a fresh copy of the clean indexed store was made (on SQLite a `PRAGMA wal_checkpoint(TRUNCATE)` then a file copy, 0.05 s at 10,000 files and 0.5 s at 100,000), N files chosen by `random.sample` were rewritten through `write` in batches of 10,000, and a sentinel file `/zzz/zzz/last.md` holding the term `qzxvunique` was written last, so the dirty set is N + 1 rows and the sentinel is the dirty row whose path sorts last. Levels never compound on SQLite; the Postgres leg is the exception named in section 8.

EXECUTED. The store was opened with `grep_wall_seconds=600` and `glean_wall_seconds=600` for the three-repetition measurement so the curve is visible past 10 s where it goes there, and then reopened with the default wall (`WALL_TIME_BUDGET = 10.0`) for one pass of every pattern and query so the records a caller sees today are on file. Statements were counted with a `before_cursor_execute` listener on the engine, bucketed by phase. The phases are module-attribute wrappers installed in the harness process only: for glean `entries_for_scan` (nominee fetch, rows counted), `_surrogate_ids`, `content_for_entries` (bodies counted and their bytes summed), `_overlay_blocks` (timed on the offload thread), `score_blocks` while inside `_overlay`, and `_overlay` itself; for grep `_entries_for_docs` (index rows), `_posting_blobs` (posting bytes), `entries_for_scan` (scan rows and their stored `size_bytes`), `content_for_entries` (bodies and bytes) and `VerifyOffload.hit_lines` and `count_lines` (the matcher). `glean.OVERLAY_BUDGET` was set to 25,000 around the lifted-budget calls and restored to 500 after each; both the nominee `limit` and the truncation record read the module global, so the patch reaches both (READ in `glean.py`). Every value in the tables is the median of three runs unless a column says otherwise.

EXECUTED. No embedding provider was configured. Every glean result carried the info record "no embedding provider is configured; the lexical leg alone answered" and `legs.vector` was `None` on all 300 lifted-budget and default-budget calls, so the vector leg was a no-op throughout and the overlay figures are the lexical leg alone.

READ. The grep patterns were a rare literal (`demekaness`, Zipf rank 12,000, `fixed_strings=True`), a common word (`bavozo`, rank 40, in about a quarter of the files), an alternation regex (`ivethha|duka`, ranks 2,000 and 2,500), a case-insensitive word (`WIDE` with `case_mode="insensitive"`, rank 800) and a pattern matching almost nothing (`neverappears`, every trigram present in the corpus, no file holding the word). The glean queries were `lubavibu nessstenha` (ranks 300 and 3,000), `bavozo lubeproes namenessho` (40, 1,500, 9,000), `stkien ivethha cobu ivewearce` (700, 2,000, 5,000, 15,000), `goniha bitiondu` (5 and 12) and `mikelode larocon` (8,000 and 20,000), all at `limit=10`.

## 3. The builds

EXECUTED.

| store | write wall s | reindex wall s | reindex SQL stmts | chunks | gram posting rows | lex posting rows | store size | peak RSS |
|---|---|---|---|---|---|---|---|---|
| SQLite 10,000 files | 8.3 | 11.9 | 360 | 46,810 | 7,473 | 93,378 | 352 MB | 955 MB |
| SQLite 100,000 files | 75.9 | 146.6 | 2,604 | 462,963 | 7,480 | 768,707 | 4,041 MB | 4.9 GB (5.2 GB over the run) |
| Postgres 100,000 files | 106.1 | 160.2 | 2,259 | 462,963 | 7,480 | 768,707 | 2,341 MB | not recorded (server side) |

INFERRED. The 100,000-file reindex is 12 times the 10,000-file one for 10 times the files, and the peak RSS of the whole-corpus build is 4.9 GB; the brief's 20 minute cap was never near. The gram posting row count is flat at about 7,500 because the synthetic vocabulary has few distinct trigrams, as the baseline also saw; the lexical rows grow with the files.

## 4. grep: the cost curve

EXECUTED. The suite summary, five patterns, median of three runs each. "Sum" adds the five medians; "slowest" is the largest of them; "scan bytes" is the stored `size_bytes` of the scan-tier nominees of the median pattern.

| store | N dirty | sum of 5 medians s | slowest median s | scan nominees per call | scan bytes MB | SQL stmts per call |
|---|---|---|---|---|---|---|
| 10,000 | 500 | 0.408 | 0.210 | 501 | 3.4 | 6 to 9 |
| 10,000 | 2,000 | 0.483 | 0.179 | 2,001 | 13.4 | 6 to 9 |
| 10,000 | 5,000 | 0.684 | 0.238 | 5,001 | 34.1 | 7 to 9 |
| 10,000 | 10,000 | 0.988 | 0.241 | 10,001 | 68.8 | 8 to 10 |
| 100,000 | 500 | 2.680 | 1.012 | 128 to 501 | 1.0 to 3.4 | 6 to 16 |
| 100,000 | 2,000 | 2.854 | 1.009 | 499 to 2,001 | 4.0 to 13.9 | 6 to 17 |
| 100,000 | 5,000 | 3.072 | 0.972 | 1,203 to 5,001 | 8.1 to 34.0 | 7 to 17 |
| 100,000 | 10,000 | 3.325 | 0.978 | 2,478 to 10,001 | 16.7 to 68.2 | 8 to 17 |
| 100,000 | 25,000 | 4.102 | 1.021 | 6,253 to 25,000 | 43.6 to 172.4 | 11 to 16 |

EXECUTED. The pattern that isolates the scan tier is `neverappears`: it nominates no index candidate (0 index rows at every level), so its whole cost is the scan tier reading and matching every dirty body. Its median per call was 0.011, 0.036, 0.085 and 0.172 s on the 10,000-file store and 0.013, 0.073, 0.121, 0.247 and 0.630 s on the 100,000-file store at N of 500, 2,000, 5,000, 10,000 and 25,000, that is 17 to 25 µs per dirty row and 2.5 to 3.7 µs per KB of body, split at N = 25,000 into 0.168 s nominee fetch (one statement, 25,000 rows), 0.416 s body fetch (172 MB in `CONTENT_BYTE_BUDGET` batches) and 0.014 s in the matcher. The matcher is never the cost; the body fetch is about 70 per cent of it and the nominee statement about 25 per cent.

EXECUTED. On the 100,000-file store the index side spends the candidate budget before the scan tier is consulted for the common patterns. `bavozo` (rank 40) nominated 24,872 encoded candidates at N = 500 and the scan tier received the remaining 128 rows; `WIDE` (insensitive) 24,865 and 135; both carried the `candidate budget` record on all three runs at every level. The alternation `ivethha|duka` crossed the budget at N = 10,000 (17,015 index + 7,985 scan) and the rare literal `demekaness` at N = 25,000 (4,368 index + 20,632 scan). As dirty rows leave the index the index side shrinks and the scan side grows, and the sum is pinned at 25,000: at N = 25,000 every one of the five patterns carried the record, `neverappears` with 25,000 of its 25,001 nominees. These index-heavy calls fetched 150 to 320 MB of bodies per call at every N, which is why the 100,000-file suite costs 2.7 s at N = 500 against 0.4 s on the 10,000-file store: that is the index tier's price for a common word on a large store, not a dirty-set cost.

INFERRED from the two paragraphs above. The scan tier's per-row cost is independent of the store size (17 to 25 µs on both stores) and the five-pattern slope is 10 to 13 µs per dirty row per call on the 10,000-file store and 10 to 23 µs on the 100,000-file one, the larger early figure being the common patterns' scan share growing from 128 rows as their index share shrinks. grep's record for the budget is the bare phrase `at the candidate budget` with `data = None`; it does not say how many rows the scan tier received or how many it left out, where glean's record carries `{scanned, budget}`.

## 5. glean: the cost curve at 500 and at 25,000

EXECUTED. At the default budget the overlay is flat whatever N is: 500 nominees, 500 bodies, 3.3 to 3.7 MB, 11 to 14 statements, 0.09 to 0.13 s per call on the 10,000-file store and 0.10 to 0.19 s on the 100,000-file store (the slower calls there are the common-term queries' index side), and the `overlay budget {"scanned": 500, "budget": 500}` record on every call at every level, because every level has at least 501 dirty rows. The overlay's own time is 0.08 s of each call, of which 0.07 s is tokenize-and-count.

EXECUTED. With the budget lifted to 25,000 the curve is linear in N.

| store | N dirty | median wall s per query (range over the 5) | nominees | bodies MB | nominee s | surrogate ids s | body fetch s | tokenize s | score s | overlay total s | SQL stmts |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 10,000 | 500 | 0.093 to 0.105 | 501 | 3.4 | 0.003 | 0.004 | 0.004 | 0.069 | 0.000 | 0.079 | 11 to 12 |
| 10,000 | 2,000 | 0.326 to 0.348 | 2,001 | 13.4 | 0.011 | 0.016 | 0.020 | 0.271 | 0.000 | 0.308 | 11 to 12 |
| 10,000 | 5,000 | 0.832 to 0.897 | 5,001 | 34.1 | 0.028 | 0.040 | 0.048 | 0.714 | 0.001 | 0.811 | 11 to 12 |
| 10,000 | 10,000 | 1.669 to 1.716 | 10,001 | 68.8 | 0.054 | 0.080 | 0.086 | 1.405 | 0.001 | 1.607 | 10 to 14 |
| 100,000 | 500 | 0.101 to 0.177 | 501 | 3.4 | 0.004 | 0.004 | 0.005 | 0.071 | 0.000 | 0.082 | 12 |
| 100,000 | 2,000 | 0.39 to 0.49 | 2,001 | 13.9 | 0.012 | 0.016 | 0.052 | 0.286 | 0.000 | 0.358 | 12 |
| 100,000 | 5,000 | 0.87 to 0.97 | 5,001 | 34.0 | 0.030 | 0.040 | 0.080 | 0.698 | 0.001 | 0.825 | 12 |
| 100,000 | 10,000 | 1.71 to 1.84 | 10,001 | 68.2 | 0.060 | 0.080 | 0.120 | 1.405 | 0.001 | 1.630 | 12 |
| 100,000 | 25,000 | 4.32 to 4.56 | 25,000 | 172.4 | 0.172 | 0.198 | 0.311 | 3.571 | 0.001 to 0.004 | 4.130 | 12 |

EXECUTED. Per dirty row, from the medians above divided by N: nominee fetch 5 to 7 µs, surrogate-id fetch 8 µs, body fetch 9 to 12 µs (26 µs at one level on the large store), tokenize-and-count 135 to 146 µs, scoring under 0.2 µs, the overlay as a whole 154 to 179 µs, and the whole call 170 to 196 µs once N is large enough that the index side's fixed 0.08 s stops dominating. The slope between consecutive levels is 160 to 196 µs per dirty row per call for the whole call and 134 to 146 µs for tokenize-and-count alone. The statement count does not move with N: the nominee, surrogate-id and body fetches are one statement each on SQLite because 25,000 ids fit one membership chunk there (READ: `membership_budget` in `dialects.py` is the tighter of the `IN`-list and bind-parameter budgets; on SQLite that is large).

EXECUTED. A separate micro-measurement on 2,000 generated bodies (14.3 MB, 2.18 million tokens) splits the tokenize-and-count phase: the Rust `tokenize` took 0.173 s, 87 µs per body at 83 MB/s, and the Python `Counter(tokens)` took 0.130 s, 65 µs per body. Their sum, 152 µs per body, matches the 135 to 146 µs per row measured inside the verb, so the phase is about 57 per cent the engine's tokenizer and 43 per cent the Python counting loop, and the rest of `_overlay_blocks` (the per-term posting assembly and block encoding) is in the noise.

INFERRED. glean's overlay pays about 17 times grep's scan tier per dirty row (175 µs against 10 µs on the suite slope, or 7 times against the 25 µs of the scan-only grep pattern), and the whole difference is CPU in Python around the tokenizer, not SQL: the SQL legs of both verbs cost about the same 20 to 25 µs per row and move the same 7 KB. The tokenizer kernel exists in Rust already; what the overlay lacks is a kernel that takes the bodies and the terms and returns the per-term postings, which would take the per-row cost to something near grep's. A pure-Python tokenize-and-count is the shape the project's tooling rules name for replacement by a kernel in `crates/vfs-core`.

EXECUTED, a side observation. On the 10,000-file store at N = 10,000 every file is dirty, so the index tier's ranking resolves to no encoded entry: the two common-term queries then carried a `scope probe budget {"window": 16000, "found": 0}` record (the probe deepened four-fold and still found nothing encoded), and the rare query returned 9 hits rather than 10 at the default budget because only 9 of the first 500 dirty paths hold either term. This is the degenerate wholly-dirty store, not a dirty-set cost, but it shows the index tier spending a second probe on a store whose rows are all in the overlay.

## 6. The sentinel recall probe

EXECUTED. After each level's dirtying the sentinel `/zzz/zzz/last.md`, written last and sorting last, was searched for by grep (`qzxvunique`, no index candidate) and by glean (`qzxvunique`) at both budgets.

| store | N dirty | dirty rows | grep finds it | grep scan nominees | glean@500 finds it | glean@25,000 finds it | records |
|---|---|---|---|---|---|---|---|
| 10,000 | 500 | 501 | yes | 501 | no | yes | glean@500: overlay budget {scanned 500, budget 500} |
| 10,000 | 2,000 | 2,001 | yes | 2,001 | no | yes | same |
| 10,000 | 5,000 | 5,001 | yes | 5,001 | no | yes | same |
| 10,000 | 10,000 | 10,001 | yes | 10,001 | no | yes | same |
| 100,000 | 500 | 501 | yes | 501 | no | yes | same |
| 100,000 | 2,000 | 2,001 | yes | 2,001 | no | yes | same |
| 100,000 | 5,000 | 5,001 | yes | 5,001 | no | yes | same |
| 100,000 | 10,000 | 10,001 | yes | 10,001 | no | yes | same |
| 100,000 | 25,000 | 25,001 | no | 25,000 of 25,001 | no | no | grep: candidate budget (no data); glean@500: {scanned 500, budget 500}; glean@25,000: {scanned 25000, budget 25000} |

INFERRED. Both verbs cut the same ordered list at their count and both lost the same file at 25,001 dirty rows, so `entries_for_scan`'s path order does make the two drop the same rows once their limits agree; the budgets are inclusive, so the N = 500 level with its one extra sentinel row already loses it under glean's default. On the 100,000-file store a dirty file holding a common word is in grep's scan tier only if its path is among the first 128 dirty paths, because the index side has already taken 24,872 of the 25,000; the record a caller gets does not say that the overlay was almost entirely left out.

## 7. The 10 second wall

EXECUTED. Under the lifted wall the slowest grep call at any level on either store was 1.02 s (the common word, index side, every level of the 100,000-file store) and the slowest glean call 4.56 s (the two very common terms at N = 25,000 with the lifted budget). The one-pass run under the default 10 s wall produced no wall record on any call at any level on either store, and its walls matched the lifted-wall medians within noise (for example grep 0.77, 0.98, 0.90, 0.78, 0.66 s and glean 4.32, 4.32, 4.31, 4.46, 4.19 s at N = 25,000 on 100,000 files).

INFERRED from the slopes. Neither verb crosses the wall inside its count budget. grep at 17 to 25 µs per scan row would need 400,000 to 600,000 scan-tier rows for 10 s, sixteen to twenty-four times its 25,000 candidate budget; glean at 175 µs per overlay row would cross 10 s on one query at about 57,000 dirty rows, well past the lifted 25,000 and 114 times its default 500. The sum of the five glean queries at the lifted budget passes 10 s between N = 10,000 (8.8 s) and N = 25,000 (22.0 s), near N = 11,400 by linear interpolation, but the wall is a per-call budget and no single call came within half of it. At the reference deployment's dirty sets (READ in the brief: 1,250 to 2,500 rows under a 15 minute refresh, 5,000 to 10,000 hourly, tens of thousands by afternoon with three rebuilds a day and no refresh), a brute-force glean overlay would cost 0.22 to 0.44 s and 9 to 17 MB of body per query at the first, 0.9 to 1.8 s and 34 to 69 MB at the second, and 4.4 s and 172 MB at 25,000; grep's scan tier at the same sets costs 0.03 to 0.06 s, 0.12 to 0.25 s and 0.63 s with the same bytes.

## 8. The Postgres leg

EXECUTED. The 100,000-file store was built on the server in a schema of its own (`curve_base_100000`, created and later dropped the way `tests/support/server_schemas.py` does): write 106.1 s in ten batches of 10,000, reindex 160.2 s and 2,259 statements, 2,341 MB on disk with `vfs_chunks` at 929 MB, `vfs_content` at 576 MB and `vfs_lex_postings` at 439 MB. The planned fresh-copy-per-level, a second schema built by vfs's own DDL and filled by `INSERT ... SELECT` from the base, failed with `DiskFullError: could not extend file` while copying `vfs_chunks`: the container's data directory is a 3.9 GB tmpfs and two copies of the store do not fit (log `log_postgres_100000_attempt1_clone_diskfull.txt`). The leg was rerun in a compounding mode on the base schema itself, each level extending the previous level's dirty set, with the sentinel rewritten at each level. The first compounding run had a defect of mine: its first level sampled with `random.sample` and its second extended a differently shuffled order, so the second level's 15,000 rewrites overlapped the first's 10,000 by 1,599 files and the store held 23,401 dirty rows, not 25,001 (EXECUTED: the `not_encoded` count after dirtying). That level is reported below at its true count. The compounding step was then changed to read the store's live dirty set and top it up to exactly N, and one more level was run at exactly 25,000 plus the sentinel. The dirty count is what the curve is a function of and it is exact in every row below; what compounding changes is that the index tier was already short of the earlier levels' rows when a later level began, which moves the index side's share, not the scan tier's per-row cost.

EXECUTED. The Postgres levels, median of three runs, the store opened with the lifted wall.

| dirty rows | verb | call | median wall s | SQL stmts | index rows | scan rows | bodies fetched | body MB | nominee s | body fetch s | tokenize s | records |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 10,001 | grep | `neverappears` (scan only) | 0.661 | 7 | 0 | 10,001 | 10,001 | 68.2 | 0.054 | 0.582 | - | none |
| 10,001 | grep | `demekaness` rare literal | 1.629 | 13 | 5,291 | 10,001 | 15,292 | 202.1 | 0.056 | 1.470 | - | none |
| 10,001 | grep | `bavozo` common word | 2.316 | 13 | 22,514 | 2,486 | 25,000 | 224.6 | 0.055 | 1.710 | - | candidate budget |
| 10,001 | grep | `ivethha\|duka` | 2.710 | 16 | 17,015 | 7,985 | 25,000 | 321.3 | 0.045 | 2.335 | - | candidate budget |
| 10,001 | grep | `WIDE` insensitive | 2.244 | 14 | 22,522 | 2,478 | 25,000 | 249.2 | 0.020 | 1.876 | - | candidate budget |
| 10,001 | glean@500 | the five queries | 0.147 to 0.266, and 3.793 for the two very common terms | 11 | - | 500 | 500 | 3.6 | 0.009 | 0.029 | 0.075 | overlay budget {scanned 500, budget 500} on every call |
| 10,001 | glean@25,000 | the five queries | 2.200 to 2.313, and 5.815 for the two very common terms | 11 | - | 10,001 | 10,001 | 68.2 | 0.055 | 0.534 to 0.579 | 1.439 to 1.530 | none |
| 23,401 | grep | `neverappears` (scan only) | 1.528 | 9 | 0 | 23,401 | 23,401 | 159.2 | 0.200 | 1.270 | - | none |
| 23,401 | grep | `demekaness` rare literal | 2.193 | 14 | 4,496 | 20,504 | 25,000 | 253.7 | 0.120 | 1.908 | - | candidate budget |
| 23,401 | grep | `bavozo` common word | 2.361 | 13 | 19,189 | 5,811 | 25,000 | 216.6 | 0.052 | 1.766 | - | candidate budget |
| 23,401 | grep | `ivethha\|duka` | 2.599 | 15 | 14,529 | 10,471 | 25,000 | 299.3 | 0.076 | 2.189 | - | candidate budget |
| 23,401 | grep | `WIDE` insensitive | 2.196 | 14 | 19,126 | 5,874 | 25,000 | 238.0 | 0.054 | 1.790 | - | candidate budget |
| 23,401 | glean@500 | the five queries | 0.148 to 0.286, and 3.806 for the two very common terms | 11 | - | 500 | 500 | 3.5 | 0.017 | 0.029 | 0.075 | overlay budget {scanned 500, budget 500} on every call |
| 23,401 | glean@25,000 | the five queries | 5.163 to 5.314, and 8.839 for the two very common terms | 11 | - | 23,401 | 23,401 | 159.2 | 0.145 to 0.163 | 1.259 to 1.325 | 3.352 to 3.391 | none |
| 25,001 | grep | `neverappears` (scan only) | 1.629 | 10 | 0 | 25,000 | 25,000 | 170.4 | 0.171 | 1.405 | - | candidate budget |
| 25,001 | grep | `demekaness` rare literal | 2.164 | 14 | 4,388 | 20,612 | 25,000 | 252.5 | 0.117 | 1.912 | - | candidate budget |
| 25,001 | grep | `bavozo` common word | 2.336 | 13 | 18,773 | 6,227 | 25,000 | 215.2 | 0.048 | 1.645 | - | candidate budget |
| 25,001 | grep | `ivethha\|duka` | 2.580 | 15 | 14,213 | 10,787 | 25,000 | 296.9 | 0.074 | 2.196 | - | candidate budget |
| 25,001 | grep | `WIDE` insensitive | 2.210 | 14 | 18,698 | 6,302 | 25,000 | 236.2 | 0.044 | 1.827 | - | candidate budget |
| 25,001 | glean@500 | the five queries | 0.144 to 0.273, and 3.824 for the two very common terms | 11 | - | 500 | 500 | 3.6 | 0.005 | 0.029 | 0.080 | overlay budget {scanned 500, budget 500} on every call |
| 25,001 | glean@25,000 | the five queries | 5.547 to 5.761, and 9.385 for the two very common terms | 11 | - | 25,000 | 25,000 | 170.4 | 0.160 to 0.164 | 1.323 to 1.366 | 3.652 to 3.767 | overlay budget {scanned 25000, budget 25000} on every call |

EXECUTED. Per dirty row on Postgres: grep's scan-only pattern 65 to 66 µs (0.661 s at 10,001, 1.528 s at 23,401 and 1.629 s at 25,000 scanned rows), of which the body fetch is 56 to 58 µs (68 MB in 0.58 s, 159 MB in 1.27 s, 170 MB in 1.41 s, about 120 MB/s through asyncpg) and the nominee statement 5 to 9 µs; glean's lifted overlay 210 to 225 µs, of which tokenize-and-count is 144 to 150 µs, the SQLite figure, the body fetch 53 to 55 µs against SQLite's 12, the surrogate-id fetch 10 µs and the nominee fetch 6 µs. The statement counts are the same as SQLite's: one statement each for the nominee, surrogate and body fetches in the overlay (25,000 ids fit one membership chunk on Postgres too), and the grep body fetch in 32 MB `CONTENT_BYTE_BUDGET` batches, 3 to 10 statements. No wall record appeared at any level, and the one-pass run under the default wall matched (grep 2.22, 2.35, 2.62, 2.23, 1.63 s and glean 5.62, 5.77, 5.62, 9.35, 5.58 s at 25,001 rows). The sentinel was found by grep and by glean at the lifted budget at 10,001 and 23,401 dirty rows and lost by both at 25,001, grep nominating 25,000 of the 25,001 with the bare `candidate budget` record and glean with `{scanned: 25000, budget: 25000}`; glean at the default budget never found it. The cap behaviour is the engine-independent one section 6 saw on SQLite.

INFERRED. Postgres adds about 45 µs per dirty row of body transfer to both verbs and changes nothing else in the shape: the CPU share of glean's overlay is the same 145 µs per row, the statement counts are flat in N, and the cap behaviour is identical. At 25,000 rows the lifted overlay's worst call was 9.4 s, within 0.6 s of the default wall; a slightly slower network or a larger median body would put the two-very-common-terms query over it, so on Postgres the lifted budget and the wall meet at about the same N (INFERRED from 5.6 s for the ordinary queries and the 3.6 s fixed index cost of that one). The two-very-common-terms query carries a fixed 3.6 s on Postgres that is absent on SQLite (0.18 s) and is independent of the dirty set (3.79 to 3.82 s at the default budget at all three levels, 11 statements): that is the index tier fetching the head and tail blocks of two terms present in most documents over the network, a large-blob transfer cost of the lexical index on this engine rather than a dirty-set cost, named in the last section as a follow-up.

## 9. Per-dirty-row costs side by side

EXECUTED on SQLite, from sections 4 and 5; the Postgres column is section 8.

| cost per dirty row per call | grep, scan-only pattern | grep, five-pattern slope | glean, lifted budget, whole-call slope | glean overlay: SQL legs | glean overlay: tokenize-and-count |
|---|---|---|---|---|---|
| SQLite 10,000 files | 17 to 23 µs | 10 to 13 µs | 160 to 174 µs | about 22 µs | 134 to 146 µs |
| SQLite 100,000 files | 24 to 37 µs | 10 to 23 µs | 162 to 196 µs | about 26 µs | 137 to 145 µs |
| Postgres 100,000 files | 65 to 66 µs | not measured (two levels, index side moving) | 210 to 221 µs | about 70 µs | 144 to 146 µs |
| body bytes read | about 7 KB (6,600 to 6,950 B) | 3,400 to 6,950 B (the index side takes budget from the scan side) | about 7 KB (6,700 to 6,960 B) | the same bytes | none |
| SQL statements | none added by N | none added by N | none added by N on SQLite | 3 statements in all | none |

INFERRED. The number that should decide the shared limit is the glean overlay's 175 µs: at that rate 25,000 dirty rows cost a query 4.4 s of CPU on the offload thread and 172 MB of body traffic, affordable once in a while but not for the reference deployment's 200 ranked searches a day on top of 150,000 verb calls if the dirty set sits at tens of thousands all afternoon; at grep's 10 to 25 µs the same 25,000 rows cost 0.25 to 0.63 s, which is what grep pays today and the baseline already saw. Lifting glean to grep's number without the kernel multiplies the lexical leg's worst case by 44 at the cap; lifting it after a kernel brings the overlay to grep's order and makes one shared count, with one shared record naming scanned and budget, the natural rule, independent of store size because the measured cost never depended on it.

## What this study does not settle

The per-row cost of the overlay with a Rust kernel for tokenize-and-count is an estimate from the micro-measurement (the tokenizer alone is 87 µs per body at 83 MB/s), not a measurement; the follow-up experiment is to prototype the kernel in `crates/vfs-core` behind a harness-only seam and rerun the lifted-budget curve.

The wall was never reached, so the shape of a wall-truncated overlay (how many of the nominated rows are scored before the record, and whether the sentinel is among them) was not observed; the follow-up experiment is a run with `glean_wall_seconds` set to 1 s at N = 25,000.

The Postgres leg ran its levels on one compounding store rather than fresh copies, and did not record server-side CPU or I/O; the follow-up experiment is the same levels on a server whose data directory is on disk, with `pg_stat_statements` on, and a fresh schema per level.

The fixed 3.6 s that the two-very-common-terms query pays on Postgres and not on SQLite sits in the index tier, outside every phase this harness wrapped; the follow-up experiment wraps `lexical_stats`, the head-block fetch and `tail_block_statements` the same way and reports the bytes of posting blocks each moves per query on both engines.

The directory tree was 3,600 directories and no scope or glob was applied, so the scan tier's gated branch (`pattern_arm` fan and `scope_fan`) was never exercised; the follow-up experiment is the same levels under a `globs` channel that admits a tenth of the tree, which is where the nominee statement count can grow.

The 10,000-file level on the 10,000-file store is the wholly-dirty degenerate case and surfaced the `scope probe budget` record; whether that second probe should run when the overlay already holds every row is a design question for the spec, not for this study.

## One line

A dirty row costs grep about 10 to 25 µs and glean about 175 µs on either store size, almost all of glean's share being Python tokenize-and-count around the Rust tokenizer; the 10 second wall is never reached inside either count budget, both verbs drop the same last-path file when their counts agree, and one shared limit becomes affordable for glean the day its overlay counts tokens in the engine.
