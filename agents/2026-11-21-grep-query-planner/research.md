# How database grep spends its time today, and what a planner can know before it fetches a body

Working notes for `spec.md`. Every figure was taken on the sandbox described in `reviews/brief.md`, with vfs at commit `5dfdcc79` and SQLite, on a 10-core, 32 GB macOS machine. Counts are exact. Timings are medians of warm runs, and the ones marked *loaded* were taken while another session ran a parallel test suite and a Docker VM (load average 48 on 10 cores). Those are not used for any decision and are re-measured before one is built. The earlier benchmark (`agents/2026-11-21-linux-grep-benchmark/`) ran at 08:28 to 08:47, before that load, with Docker's VM already up from 08:12.

## R1. A scoped grep pays for its root's parent subtree

`experiments/` and `../2026-11-21-linux-grep-benchmark/crossover.py`, read through a traced `allow_list_ids`. `grep(paths=("/drivers/atm",))` compiles two allow-list arms: `/drivers/atm/**`, with segments `{drivers, atm}`, and `/drivers/atm` itself, the root's own row, with segments `{drivers}` and only a name fact. The segment table bounds an arm by its segments alone, so the second arm admits every entry under any directory named `drivers`. The union came back as 40,262 ids for a 30-file directory, in 42.7 ms. The candidate fetch then resolved all 40,262 in two 18,180-bind statements, at 108 ms. The whole call took 230 ms. The same search spelled `globs=("/drivers/atm/**",)` built 38 ids in 3.4 ms and took 13 ms.

This explains why the earlier crossover measured `drivers/atm` (30 files), `drivers/clocksource` (100) and `drivers/md` (296) at the same index cost: all three pay for `drivers`. The 1,033-file `drivers/gpu/drm/amd/display/dc` was cheaper, at 19 ms, because its parent's rarest segment is small. A root that is a file pays the same way: `/include/linux/dcache.h` built 3,958 ids, and `/fs/open.c` with `/fs/read_write.c` built 2,462.

## R2. The path index answers the scope question in under half a millisecond

`experiments/e1_scope_probe.py`, raw SQL on a read-only connection. `SELECT id, size_bytes FROM vfs_entries WHERE kind = 'file' AND path > :root || '/' AND path < :root || '0' LIMIT :t + 1` runs as `SEARCH vfs_entries USING INDEX ix_vfs_entries_path (path>? AND path<?)`.

| scope | files | exact range ids, ms | today's segment allow-list, ms (ids) | probe T=256 | T=1,024 | T=4,096 |
|---|---|---|---|---|---|---|
| mm/tests | 1 | 0.00 | 0.62 (976) | 0.01 | 0.01 | 0.01 |
| kernel/kcsan | 10 | 0.00 | 1.17 (2,908) | 0.01 | 0.01 | 0.01 |
| drivers/atm | 30 | 0.01 | 17.23 (40,300) | 0.02 | 0.02 | 0.02 |
| drivers/md | 296 | 0.08 | 17.59 (40,563) | 0.09 | 0.11 | 0.11 |
| drivers/gpu/drm/amd/display/dc | 1,033 | 0.35 | 4.45 (2,737) | 0.11 | 0.43 | 0.43 |
| drivers/media | 3,023 | 0.81 | 20.74 (44,511) | 0.10 | 0.36 | 1.10 |
| drivers/gpu | 8,036 | 2.61 | 24.23 (48,889) | 0.09 | 0.36 | 1.71 |
| drivers | 37,340 | 12.69 | 17.28 (40,262) | 0.10 | 0.36 | 1.67 |

A bounded probe costs in proportion to its limit and never to the scope. The exact range costs about 0.34 µs per id. Both use an index the table already has. On Postgres the range spelling is the one to use. A bound `LIKE` falls to a sequential scan once asyncpg's named statement switches to its generic plan, while the range keeps its index condition. That was measured by the spec "Postgres reads a subtree by its range", in flight on branch `vfs-serves-sqlite-and-postgres-only` when this was written, and that spec makes the range the rule on both engines.

## R3. In hand beats the ladder up to a few hundred files, locally

`../2026-11-21-linux-grep-benchmark/crossover.py`. Reading a scope's files and grepping them through `grep(observations=rows)` costs about 3 ms plus 0.05 to 0.09 ms a file, and the pattern barely matters. Listing the files with `glob` adds about 5 ms plus 0.025 ms a file. The ladder's cost followed R1's parent subtree, not the scope. In hand won on every scope of 296 files or fewer for every pattern, and the ladder won on every scope of 1,033 or more, except one tie. Caller-built rows work: `grep(observations=[Observation(path=..., kind="file"), ...])` over two files took 3.3 to 5.1 ms in 5 statements.

## R4. The index side is cheap; bodies are the cost

Phase timing through wrapped helpers (`grep_module` functions replaced in a throwaway script; no source edited). Corpus-wide `i_count`: posting metadata 0.5 ms, blobs 0.5 ms, the intersection kernel under 1.5 ms, and the candidate entry fetch 39 ms for 6,101 ids. Content fetch was 180 ms and verify 22 ms. This agrees with `context/research/2026-08-16-grep-read-path-profile.md`, which found every index stage at 1.8% or less of a call. The exact, uncapped candidate count is therefore known for about 3 ms before any body is fetched. No statistic needs to estimate it.

The posting metadata's `doc_count` estimates it badly in both directions. For `i_count`, the rarest chosen gram's `doc_count` is 11,890 against 6,096 candidates, and the independence product is about 600. The grams of an identifier are strongly correlated.

## R5. Trigram candidates are a loose superset; a literal is nearly exact

`experiments/e3_corpus_precision.py`, corpus-wide, 22 patterns, exact counts:

| pattern | ladder candidates | all trigrams | all 4-grams | literal present | matches |
|---|---|---|---|---|---|
| `i_count` | 6,096 | 5,924 | 1,373 | 221 | 221 |
| `f_ref\|f_count` | 9,595 | 9,438 | 2,151 | 1,011 | 1,011 |
| `return 0;` | 29,561 (25,000 fetched) | 24,999 | 24,763 | 24,762 | 24,762 |
| `EXPORT_SYMBOL_GPL` | 4,297 | 3,714 | 3,602 | 3,599 | 3,599 |
| `kmalloc` | 4,144 | 4,144 | 3,713 | 3,711 | 3,711 |
| `spin_lock_irqsave` | 3,836 | 3,803 | 3,771 | 3,508 | 3,508 |
| `copy_from_user` | 1,716 | 1,622 | 1,272 | 1,251 | 1,251 |
| `pr_debug` | 4,802 | 3,806 | 2,326 | 2,306 | 2,306 |
| `-EINVAL` | 17,427 | 17,427 | 17,207 | 17,207 | 17,207 |
| `MODULE_LICENSE` | 17,330 | 15,490 | 12,637 | 12,634 | 12,634 |
| `TODO` | 3,540 | 3,540 | 3,144 | 3,144 | 3,144 |
| `#include <linux/slab\.h>` | 9,138 | 9,125 | 9,123 | 9,121 | 9,121 |
| `struct page \*` | 8,736 | 6,907 | 1,877 | 1,448 | 1,448 |
| `^static int __init` | 8,364 | 8,206 | 6,931 | 5,926 | 5,901 |
| `\.read_iter\|\.write_iter\|\.mmap` | 2,098 | 2,053 | 650 | 619 | 619 |
| `^struct dentry \{` | 1,430 | 1,270 | 184 | 1 | 1 |
| `^struct inode \{` | 3,007 | 2,981 | 94 | 1 | 1 |
| `dentry_lru_isolate` | 85 | 20 | 2 | 1 | 1 |
| `__follow_mount_rcu` | 161 | 70 | 2 | 2 | 2 |
| `ramfs_get_inode\|ramfs_fs_type` | 156 | 26 | 7 | 4 | 4 |
| `alloc_page` | 3,720 | 3,490 | 866 | 756 | 756 |
| `xyzzy_no_such_symbol_42` | 3 | 0 | 0 | 0 | 0 |
| **total, untruncated rows** | **109,681** | **103,056** | **70,932** | **66,471** | **66,446** |

"All trigrams" and "all 4-grams" are simulated over the fetched candidates' bodies: a body is kept when every gram of some branch's literal occurs in it. The 4-gram column is the most a 4-gram index could nominate under the same plan. Intersecting every trigram, which needs no index change, removes 6% of candidates. A 4-gram index removes 35%, and 4 to 16 times on single patterns. A literal test removes 39%, within 25 files of the true matches.

Candidates are heavier than the corpus mean: `i_count`'s 6,096 candidates hold 386 MB, 63 KB each, against a 17 KB mean. A file with more text holds more grams.

## R6. The unindexed tail is a floor on every call

96 files over the indexable caps (366 MB, the amdgpu register headers among them) are never encoded. Every grep scans them on the scan side. Corpus-wide `xyzzy_no_such_symbol_42`, three candidates and no match, took 86 ms, 47 ms of it fetching content, almost all of it the tail. Locally that is a floor. On a remote database, every corpus-wide grep moves those 366 MB over the wire, about 2.9 s at 1 Gbit/s.

## R7. What a remote database changes

Projected, not measured, by `../2026-11-21-linux-grep-benchmark/project.py`: a round trip per counted statement plus transfer per body byte. The ladder issues 19 to 42 statements and in hand 5 to 11. Round trips favour in hand slightly; transfer favours the ladder, and favours anything that keeps bodies in the database. The server-side literal test (`instr` on SQLite, `strpos` on Postgres) was timed only under load and is re-measured on a quiet machine before decision 6 is taken.
