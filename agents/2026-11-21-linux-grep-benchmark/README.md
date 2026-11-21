# Linux grep benchmark: system tools, ripgrep and vfs, and the in-hand crossover

Working material, measured 2026-11-21 on a 10-core, 32 GB macOS machine. vfs ran from commit `5dfdcc79`, with SQLite through `aiosqlite`. The corpus was the Linux checkout at `faeab166`: 93,765 files listed by `rg --files`, of which 93,759 UTF-8 files (1.59 GB) were ingested and 6 binaries were skipped. Full tables are in `results.md`, and raw numbers are in `data/`.

## Ingest

`ingest.py` writes 10,000-entry batches through `DatabaseStorage.write` and then runs `rebuild`. The writes took 53 s and the rebuild 179 s, and the result was a 4.4 GB SQLite file.

## Session replay

`bench.py` reads the seven Bash calls of Claude Code session `ae4b45bb` that ran in the checkout, and splits them into 39 stages: 28 `grep -n` stages, 9 `sed -n` stages and 2 `ls` stages. Each stage runs as the system tools, as the same pipeline with `rg` in place of `grep`, and as vfs verb calls in one long-lived process. All 39 stages give identical output across the three tools.

| stage kind | count | generic ms | rg ms | vfs ms |
|---|---|---|---|---|
| grep (1 to 3 named files) | 28 | 175 | 204 | 434 |
| sed (read a line range) | 9 | 49 | 60 | 28 |
| ls | 2 | 12 | 14 | 7 |

A vfs `grep` scoped to named files costs 9 to 28 ms, against 3 to 13 ms for spawning a `grep` process. The scoped call plans on the corpus-wide posting lists. Reading the file and calling `grep(observations=...)` costs about 3 ms (`scoped_grep.py`).

## Repo-wide

Each of the session's 28 grep patterns was run over the whole tree. Hit sets are identical across the three tools for every pattern.

| | generic `grep -rnI` | `rg -n` | vfs `grep` |
|---|---|---|---|
| total over 28 patterns | 706 s | 84 s | 3.1 s |
| per pattern | 12 to 68 s | 2.2 to 3.4 s | 46 to 343 ms |

For globs, matching names against `*{path-lookup,vfs,locking,porting,mount_api}*` took 538 / 107 / 47 ms (generic / rg / vfs). Matching `**/*.h` (26,702 files) took 458 / 106 / 377 ms.

## Crossover: read in hand vs posting list

`crossover.py` times three things on scopes of 1 to 93,759 files with four patterns. The first is `grep(paths=(scope,))`. The second is `glob("**", kind="file")` over the scope. The third is `grep(observations=rows)`. `project.py` then adds a round trip per counted statement and transfer per in-hand byte, as a model of a remote database.

- The in-hand cost is close to linear in files: about 3 ms plus 0.05 to 0.09 ms a file. The listing adds about 5 ms plus 0.025 ms a file. Both are nearly insensitive to the pattern.
- The index cost does not follow the scope's file count. It was 10 to 21 ms on scopes of 1 to 10 files outside `drivers/`, and 19 to 23 ms on the 1,033-file `drivers/gpu/drm/amd/display/dc`. It was the same 54 / 77 / 65 / 176 ms on `drivers/atm` (30 files), `drivers/clocksource` (100) and `drivers/md` (296). It grows with how common the pattern's grams are: 88 ms for the rare pattern and 1,826 ms for `return 0;` on the whole tree. Untested hypothesis: the cost follows the path-segment posting lists that bound the scope, and the gram posting lists of the pattern.
- Locally, in hand won on every scope of 296 files or fewer, for every pattern. The index won on every scope of 1,033 files or more, except `return 0;` on `drivers/media` (3,023 files), which was a tie (270 vs 262 ms).
- The index path stopped at its 25,000-candidate budget for `return 0;` on `drivers/` and on the whole tree, with a `truncated` warning. The in-hand path returned every hit.
- Statements: the index path issued 19 to 42, the listing 5 to 10, and the in-hand grep 5 to 11. A round trip per statement therefore favours in hand slightly, and transfer per byte favours the index heavily. In the same-region projection (1 ms, 1 Gbit/s), `drivers/md` (5.9 MB) flips to the index for two patterns. Every scope of 1,033 files or more stays with the index under every projection.

The planner's input is therefore two numbers, not one. The first is the scope's file count and bytes, for the in-hand cost. The second is an estimate of the index-side cost from the posting-list sizes the plan would decode.

## Reproduce

```bash
uv run python agents/2026-11-21-linux-grep-benchmark/ingest.py --root ~/Git/Repos/linux --db linux.db
uv run python agents/2026-11-21-linux-grep-benchmark/bench.py --session <transcript>.jsonl --root ~/Git/Repos/linux --db linux.db --out results.json --repo-wide
uv run python agents/2026-11-21-linux-grep-benchmark/crossover.py --root ~/Git/Repos/linux --db linux.db --out crossover.json
uv run python agents/2026-11-21-linux-grep-benchmark/report.py results.json
uv run python agents/2026-11-21-linux-grep-benchmark/project.py crossover.json
```
