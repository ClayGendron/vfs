# Round 2: adversarial review of the revised grep planner design

**Verdict: Fit to build with changes.** One finding is high: a mismatch between two pattern parsers. It is older than the planner, and the planner makes it visible as rows that differ from one plan to another. Every round-1 finding is closed by a run, the four-way plan order returns today's rows or more, and decision 7's extraction is sound when it is built over the HIR (the regex crate's parsed form of the pattern) as specified. The changes are listed under each finding.

The pinned code is `5dfdcc79`, and `$PIN` is the `src` of a checkout of that commit. The scripts are in `$R2 = agents/2026-11-21-grep-query-planner/reviews/scripts/round-2/`, with their output beside them as `*.out`. They run from the repository root as `PYTHONPATH=$PIN uv run python -W ignore $R2/<script> <args>`. The HIR dump is the exception: `cd $R2/hirdump && cargo run --offline -q`, built against `regex-syntax = "=0.8.11"`, the version in `Cargo.lock`. Every run used SQLite, and no Postgres leg was run. The timings in `r2_03_timing.out` were taken at a load average of 2.0 to 2.2. All other figures are counts.

## Round-1 findings, verified by execution

| Round 1 | Status | Run and observed |
|---|---|---|
| H1, case variants lost | **closed** for patterns in Python's syntax | `r2_02`: e5 on round 1's store gives `[Kk]malloc → {malloc}` and `Kmalloc\|kmalloc → {Kmalloc, kmalloc}`, and both inline-flag patterns give `None`. No row is lost. `r2_05`: e5 run through `compile_verifier`'s own wrapping (fixed strings, word wrap, smart case) over Unicode case pairs, `\b` inside runs, `{0}`, `{n,m}`, escapes and `(?x)` found 0 violations against the Rust matcher. The new H1 below is the exception: syntax that Python's parser reads differently. |
| H2, `invert_match` | **closed** | `r2_02`: with the test off under invert, the scan side keeps all three files, round 1's two lost rows among them. |
| M1, probe visits the scope | **closed** | `r2_02`: `SEARCH vfs_entries USING COVERING INDEX ix_vfs_entries_path`. The probe visits exactly the rows it returns (301, 1,025, 1,025). Tombstones are judged on those rows only. |
| M2, branch ignores scope size | **closed** for ids resolved; see M2 below for probe rows | `r2_03`: the ids the candidate fetch resolved equal U in every allow-listed-by-range pair, and U was always no more than n. |
| M3, unindexable pattern | **closed** | `r2_02`: `a` is refused over 1 file and over 37,340 files alike. With `allow_scan`, in hand and the scan tier give identical per-file counts for `^$`, `x*` and `.`. |
| M4, unbounded statement | **closed, as declared** | `r2_03`: the full allow-list measured 39,795 ids for `/drivers`, which is the declared exception. |
| M5, root's own row | **closed** | `r2_02`: n = 1 for `/include/linux/dcache.h`. `r2_03`: in hand returns today's rows for both file-root scopes. |
| L1, mean of latencies | **closed** | `r2_02`: `SELECT 1` has a median of 0.134 ms (spread 0.126 to 0.215 ms), against 0.848 ms for a 40,000-row count. On SQLite this measures aiosqlite's thread hop, not a network. |
| L2, 4-gram fold | **closed** | The spec now quotes `r06`'s figures (44.1% folded, 45.3% raw, `TODO` 0.7%). |
| L3, overlapping roots | **closed** | `r2_02` and `r2_03`: `/drivers` with `/drivers/md` reduces to `/drivers`, and its rows equal `/drivers` alone. |
| L4, arms at the seam | **closed** | Decisions 1 and 2 now name `**`. Round 1's `r01` trace stands. |

**Plan parity of the revision** (`r2_03_dispatch.py`, T = 200). Decision 5's order was prototyped end to end: in hand, allow-listed by range, range-scoped, and allow-listed in full. It ran over 12 scopes and 8 patterns: 1 to 37,340 files, multiple roots, overlapping roots, file roots, `(?i)`, case-insensitive, `\b` and alternation. In 93 of the 96 pairs the rows were identical to today's code, with line spans and match text. In the other 3 pairs, today's code truncates at the candidate budget and the planned call does not. `r2_03b` shows that today's rows are a subset of the planned rows in each of those pairs (15,101 within 17,688, and 3,199 within 3,353).

## New findings, high to low

### H1. Decisions 5 and 7: Python's parser and the regex crate read some admitted patterns differently, so plans disagree and today's index side loses rows

Scripts: `r2_01_syntax_mismatch.py`, and the HIR dump in `hirdump/`.

The matcher is the regex crate. The language gate (`_gate`), the gram planner (`code_grams`) and e5's prototype all read the pattern with Python's `sre_parse` instead. The two parsers disagree on syntax that the gate admits:

- `\<` and `\>` are word-boundary assertions in the crate, and an escaped literal in sre.
- `\b{start}` is an assertion in the crate. sre reads it as `\b` followed by the literal text `{start}`.
- `[[:alpha:]]` is a POSIX class in the crate. sre reads a class followed by a literal `]`.
- `x[a[bc]]y` is a nested class in the crate. sre ends the class early.

The HIR dump shows the crate's reading. For example, `\<i_count` becomes `Concat([Look(WordStartUnicode), Literal("i_count")])`, and `[[:alpha:]]_count` becomes `Concat([Class({'A'..='Z', 'a'..='z'}), Literal("_count")])`.

Observed on the sandbox. The database grep of today is the ladder; in hand is `grep(observations=...)`, which reads every body with the Rust matcher. Neither returned an error.

```
/fs (2354 files) '\<i_count'           database grep:   0 rows; in hand:  10 rows; rows the database grep misses: 10
/fs (2354 files) 'i_count\>'           database grep:   0 rows; in hand:  26 rows; rows the database grep misses: 26
/fs (2354 files) '[[:alpha:]]_count'   database grep:   0 rows; in hand: 751 rows; rows the database grep misses: 751
/fs (2354 files) '\<kmalloc'           database grep:   6 rows; in hand: 421 rows; rows the database grep misses: 415
```

The same patterns break e5. Its prototype requires `<i_count`, `{start}i_count`, `i_count>`, `]_count` and `]y`, none of which the matched bodies hold. A property test of e5 against the Rust matcher, with a generator that emits this syntax, found 28,650 violations in 460,530 bodies. e5's own generator emits only Python syntax, and reproduced its 0 violations in 557,140 bodies.

Decision 5's parity claim cannot hold while this stands. A pattern returns 6 rows when its scope routes to a ladder and 421 when the scope routes to in hand. The gram extraction is out of the spec's scope, but the spec's claim depends on it.

Changes needed:

- The gate refuses every construct that the two parsers read differently. Otherwise the gram planner and the literal extraction both walk the crate's HIR.
- Decision 7's property test runs against the Rust matcher, with a generator that covers the crate's own syntax.
- The present loss in today's grep is reported as a bug in its own right.

This holds on both engines, because the parsers are engine-independent.

### M1. Decision 6: the local T figure comes from the ladder before decisions 1 and 2

Script: `r2_03_dispatch.py --time`, medians of 7 warm runs, load 2.0.

| scope (range entries) | rare pattern: in hand / ladder (ms) | `-EINVAL`: in hand / ladder (ms) |
|---|---|---|
| /kernel/kcsan (10) | 3.2 / 5.9 | 3.3 / 7.2 |
| /kernel/bpf (87) | 7.0 / 7.1 | 8.8 / 11.0 |
| /drivers/clocksource (100) | 6.8 / 6.1 | 7.1 / 8.8 |
| /drivers/net/wireless/ath/ath9k (112) | 10.0 / 6.0 | 10.1 / 8.6 |
| /fs/btrfs (144) | 9.8 / 5.9 | 10.7 / 10.0 |
| /mm (208) | 11.6 / 7.5 | 12.7 / 11.4 |
| /drivers/md (301) | 17.2 / 7.3 | 19.0 / 12.2 |

With R1's parent-subtree cost removed, the ladder's floor is 6 to 7.5 ms. In hand overtakes it below about 100 entries for a rare pattern, and below about 140 for a common one. The spec's local T of 150 to 250 is derived from R3's ladder, which still paid R1's cost. At that T, scopes of 112 to 208 entries take in hand for a rare pattern at 33% to 67% above the best plan, which breaks the check that the planner stays within 20% of the best.

Locally, in hand gains at most about 3 ms. Its real gain is the statement count on a remote engine: 5 statements against 15 to 17.

Two caveats. The in-hand path timed here is `grep(observations=...)` through the router, not a native plan. The probes ran on a side connection for both plans.

Change needed: re-derive T on the fixed ladder.

### M2. Decision 5: the second probe reads up to 25,001 rows before U is consulted

Script: `r2_03_dispatch.py`. Observed:

- `/arch` with `/fs` and `dentry_lru_isolate`: the probes read 22,197 rows, and 16 ids were resolved (U = 16).
- `/drivers/gpu` with the same pattern: the probes read 8,828 rows for U = 33.

"Ids resolved at most min(n, U)" counts the entry fetch and leaves out the probe's own n rows. Those rows are paths and ids moved to the client on every call over T. On Postgres they are also heap visits (see L2 below).

U costs about 3 ms (R4) and needs no allow-list. Two cheaper orders exist:

- Read U first, then run the second probe with a limit of `min(U, SCAN_TIER_BUDGET) + 1`.
- Take the range-scoped plan whenever U < n.

Either keeps the reads at about min(n, U).

### L1. Decision 6: in hand's price counts the unindexed tail, and the ladder's floor does not

Script: `r2_04_tail_and_pg_index.py`. For `/drivers/gpu/drm/amd/include/asic_reg/dcn` (38 files), in hand's B is 171.3 MB, of which 143.1 MB is unencoded. The ladder fetched 143.1 MB for a pattern with a single match in the whole corpus. Two other directories show the same: 115.3 MB against 103.8 MB, and 63.1 MB against 48.2 MB.

Decision 6 charges in hand `B·c_byte` and the ladder a one-candidate floor. Where `c_byte` dominates, in hand loses to a plan that moves 84% of the same bytes. Decision 9 says every ladder plan prices the tail, so decision 6's floor should include the scope's unencoded bytes.

### L2. Decision 3: "covered by ix_vfs_entries_path" holds on SQLite only

Script: `r2_04_tail_and_pg_index.py`. vfs's own metadata, compiled for Postgres, gives `CREATE UNIQUE INDEX ix_vfs_entries_path ON vfs_entries (path)`. `id` is SQLite's rowid, so the probe is covered there. On Postgres, `SELECT id, path` needs a heap visit per row. It is still bounded by T, or by 25,001 on the second probe. An `INCLUDE (id)` makes it index-only. This was compiled, not run on a server.

### L3. Decision 7: the Python prototype factors common prefixes, and the HIR does not

Script: e5 itself. e5 gives `f_ref|f_count → {ref, count}` and `\.read_iter|\.write_iter|\.mmap → {read_iter, write_iter, mmap}`, because sre lifts a branch's common prefix out of the alternation. The HIR dump gives `abc|abd → Alternation([Literal("abc"), Literal("abd")])`.

R5's "within 25 files" was measured with hand-picked full literals, so it describes the HIR build, not the prototype. This costs precision only.

## Questions

- Decision 6 sets T "where in hand's price at T rows of the scope's mean size reaches that floor". The probe reads `id, path` only, so the scope's mean size is unknown when T must be fixed. Is it a corpus mean, or one kept per storage?

## Attacked and held

- **The HIR facts decision 7 relies on**, from the dump under the matcher's builder flags. `(?i)` and the call's case flag lower to classes, with the Kelvin sign and `ſ` folded in: `(?i)s → Class{S, s, ſ}`. `(?i)İ` stays `Literal("İ")`, which is exact because the crate gives it no fold. `[Kk]` is a class, and `[k]x` merges to `Literal("kx")`. `Kmalloc|kmalloc` stays two literals. `foo\bbar` splits at `Look`. `(abc){0}x` becomes `Literal("x")`. `(ab){2,3}` is a repetition with min 2. `[a-c&&b]x` becomes `Literal("bx")`. Given these, the specified walk is sound on every construct tried.
- **The gate refuses backreferences, look-arounds and mid-pattern flags** (`r2_05`), so the extraction never meets them.
- **e5's algorithm in Python's own syntax** (`r2_05`): 0 violations over 25 patterns times 3 case modes times fixed strings times word wrap, against the Rust matcher, Unicode case pairs included.
- **Truncation never drops an in-scope row** (`r2_03b`): where today truncates, the planned call returns a superset of today's rows and carries no warning.

## Not attacked

- No Postgres leg was run, and none was run with added latency.
- No real grants or tombstones were tested through vfs. The sandbox is read-only, and the "What is checked" item on a writable copy is still open.
- The remote side of decision 6 was not run.
