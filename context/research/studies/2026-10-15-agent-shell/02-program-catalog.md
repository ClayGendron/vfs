# The program catalog: what the vfs agent shell ships, in what order, and as what

Date: 2026-10-15. Researcher: S2. Study: agent-shell (brief `00-brief.md`).

Clones and commits read (all `~/Git/Repos/<name>`, refreshed 2026-10-15 unless marked): busybox@371fe9f (GPL-2.0), toybox@6a0c0ef (0BSD), uutils-coreutils@4945ecf (MIT), sbase@b30fb56 (MIT), plan9port@b6564bd9 (MIT, Plan 9 Foundation), 9front@a0806493 (**DIRTY clone, not refreshed**, 13 case-collision files modified; MIT per Plan 9 Foundation relicence; no root LICENSE file in the clone), just-bash@9ab0e0d (Apache-2.0), bashkit@b7904a4 (MIT), just-bash-py@48d111c (Apache-2.0), lifo@5a35d05 (MIT), amla-sandbox@169384f (Python MIT; bundled wasm runtime AGPL-3.0/BUSL-1.1, study only), gemini-cli@d42e3f1e7 (**DIRTY clone**: the working tree was overwritten by an unrelated project, so every citation is from `git show d42e3f1e7:<path>`, Apache-2.0 upstream), opencode@13263f30ed (MIT), codex@16e578d (Apache-2.0), claude-agent-sdk-python@aada024 (MIT), deepagents@0bf167654 (MIT), deepagentsjs@9f3bfd5 (MIT), eve@5666d2f0d (Apache-2.0), ripgrep@3fce3b5 (MIT/Unlicense).

Evidence labels used below: **EXECUTED** (a script or build I ran; outputs are under `experiments/s2/`), **READ** (read in a checkout, cited `repo:path:line`), **INFERRED** (my judgement, from transcripts I have seen and from documentation I know; not measured).

Experiments folder: `experiments/s2/` holds `lists/*.txt` (one command list per source), `matrix.py` → `matrix.md` and `classes.md`, `loc_just-bash.tsv`, `loc_bashkit.tsv`, `uu_wc_build.log`, `run_wasm_wc.py` → `run_wasm_wc.out`, and `lists/ripgrep-flags.txt`.

Term of art, once: a **program** is anything an agent types at the head of a pipeline segment (`grep`, `head`, `cd`). A **builtin** is a program the shell answers itself. A **verb** is one of vfs's 25 operations (`read`, `grep`, `glob`, ...). A **segment** is one command between pipes.

---

## Summary

The catalog is small, and the corpus proves it. Across 12,627 real Claude Code Bash calls (67,446 pipeline segments; executed by E2, `experiments/e2/commands.md`), nine programs make 86% of all segments: `grep`, `head`, `echo`, `sed`, `cd`, `uv run`, `tail`, `cat`, `ls`. Classified by how vfs would answer them, 29.7% of segments are vfs-verb builtins, 35.1% are pure text programs, 24.1% are shell builtins, 1.2% are guest interpreters, and 9.1% are host programs the shell will never run (`uv`, `git`, `docker`, `ps`, `curl`). So a first slice of about 25 programs covers roughly 90% of what agents type, and the first five text programs to get right are `head`, `tail`, `sed -n 'a,bp'`, `wc -l` and `cut`. The peer agent shells agree: 40 commands are shipped by all four full reimplementations (just-bash, bashkit, just-bash-py, lifo), and that intersection is almost exactly the tier-1 and tier-2 lists below. Cost per program is measurable: a median text program is 233 lines in just-bash and 525 in bashkit, while `sed`, `awk`, `find` and `jq` are 2,500–10,000 lines each — those four are interpreters in their own right and are the ones to consider as wasm programs or dependencies rather than hand kernels. A wasm path is real: `uu_wc` from uutils compiles to `wasm32-wasip1` in 16 s and runs correctly under wasmtime with piped stdin (executed). Clay's rule governs the whole catalog: every program keeps its native name and real flag semantics; the corpus only orders which forms to implement first.

---

## Findings

### F1. The source command sets, counted (EXECUTED)

Lists are in `experiments/s2/lists/`. The extraction one-liners are recorded in the file header of `matrix.py` and in this section.

| source | count | how counted | licence |
|---|---:|---|---|
| busybox | 390 | `//applet:IF_*(APPLET*(name` comments across `*.c` (the applet table moved out of `include/applets.src.h` into per-source comments; 448 applet lines, 390 distinct names) | GPL-2.0 |
| toybox | 198 (+52 pending) | `toys/{posix,lsb,other,android,net}/*.c`; `toys/posix/` alone is 69 | 0BSD |
| uutils-coreutils | 108 | `src/uu/*` minus `checksum_common` | MIT |
| sbase | 96 | the README status table (`UTILITY` column; includes the `sha238sum` typo as printed) | MIT |
| plan9port | 151 | `src/cmd/` entries (`bin/` is not built in the clone: 57 scripts only) | MIT |
| 9front | 425 | `sys/src/cmd/` (300) ∪ `rc/bin/` (133 rc scripts); DIRTY clone | MIT (Plan 9 Foundation) |
| just-bash | 90 | `name: "<cmd>"` entries in `packages/just-bash/src/commands/registry.ts` (77 directories; several directories register two or three names such as `grep`/`egrep`/`fgrep`, `gzip`/`gunzip`/`zcat`, `python`/`python3`, `bash`/`sh`) | Apache-2.0 |
| bashkit | 193 | 168 names in the `register_builtins!` macro at `crates/bashkit/src/interpreter/mod.rs:2096` plus 25 custom-constructed ones registered below it (`date`, `git`, `jq`, `yq`, `ssh`, `sudo`, `vi`, `nano`, ...); the README says 167 | MIT |
| just-bash-py | 69 | `src/just_bash/commands/*` directories minus helpers | Apache-2.0 |
| lifo | 81 | `packages/core/src/commands/{fs,text,io,archive,system,net}/*.ts` minus browser shims | MIT |
| amla-sandbox | 13 | the applet list stated in `src/amla_sandbox/__init__.py:27` and `langgraph.py:369` (`grep jq tr head tail sort uniq wc cut cat echo ls` plus the `tool` applet); the Rust runtime is not in the clone | MIT (Python), AGPL/BUSL (wasm) |

Plan 9 has no `head`, `find`, `xargs` (plan9port) or `which`: it uses `sed 10q`, `walk` (9front), and `rc` idioms. That is why `head` shows "4 of 6 Unix sets" in the matrix.

### F2. Toybox's ranking method, and our analogue (READ)

Toybox's roadmap (`toybox:www/roadmap.html`, "Use case: provide a self-hosting development environment") ranks commands by **what a real build actually invokes**, not by what a standard lists. The method: wrap `$PATH` with a command-logging shim (`mkroot/record-commands`, `toys/example/logpath.c`), build Linux From Scratch and AOSP under it, then `awk '{print $1}' root/build/log/*-commands.txt | sort -u`. The standards (POSIX-2024, LSB 4.1, man-pages, RFCs) are a checklist afterwards, and the roadmap says openly that each includes commands it will never implement.

Our analogue is E2's corpus: 418 Claude Code transcripts, 12,627 Bash calls, head words, flags and constructs recorded (EXECUTED by E2; `experiments/e2/mine_commands.py`). That corpus is the ranking authority for this catalog. The classic sets are the checklist.

### F3. The corpus, by program and by class (EXECUTED: `matrix.py` → `classes.md`)

Base: 67,446 pipeline segments (the head-word table in `e2/commands.md`).

| class | what it is | segments | share |
|---|---|---:|---:|
| a | vfs-verb builtin (`grep`, `cat`, `ls`, `find`, `rg`, `mkdir`, `cp`, `rm`, `mv`, `du`, `stat`, `tree`, `file`, `ln`, `readlink`) | 20,028 | 29.7% |
| b | pure text program (`head`, `tail`, `sed`, `wc`, `cut`, `awk`, `sort`, `nl`, `tr`, `uniq`, `tee`, `diff`, `paste`, `fold`, `base64`, `tar`) | 23,646 | 35.1% |
| c | shell builtin (`echo`, `cd`, `sleep`, `unset`, `printf`, `source`, `break`, `export`, `time`, `date`, `which`, `wait`, `true`, `test`, `set`, `shift`, `exit`, `continue`) | 16,223 | 24.1% |
| d | wasm program | 0 | 0.0% (nothing in the corpus is wasm-only today; `sqlite3`, `jq`, `tar` would land here) |
| e | guest interpreter (`python3`, `perl`, `python`, `bash`) | 789 | 1.2% |
| f | never: host process, network, package manager, VCS (`uv` 5.4%, `git` 2.8%, `docker` 0.24%, `ps` 0.12%, `curl` 0.12%, `gh`, `pkill`, `pgrep`, `cargo`, `pdftotext`, `uptime`, `chmod`, `pmset`, `sysctl`, `kill`, `psql`, `open`, `nproc`, `tokei`) | 6,117 | 9.1% |
| — | miner artefacts (bare numbers, stray flags such as `-u`, `-n`, script names) | 544 | 0.8% |

Headline facts (E2's numbers, EXECUTED by E2): `grep` 20.9%, `head` 15.8%, `echo` 13.4%, `sed` 12.1%, `cd` 9.3%, `uv run` 5.3%, `tail` 4.1%, `cat` 3.9%, `ls` 3.1%. Pipe in 74% of calls, `&&` 44%, a glob in 25%, `2>&1` 16%, `>` 14%, heredoc 12%, `$VAR` 12%, `for` 4.7%, `$( )` 3.7%, `||` 1.4%, `if` 0.9%, `while` 0.4%, `&` 0.2%. Median segments per call is about 4.

The forms matter more than the names. `sed -n` is 7,739 of 8,180 `sed` segments (95%), i.e. ranged line reads (`sed -n '120,160p'`), and `sed -i` is 242. `grep -n` 7,690, `grep -rn` 2,392, `grep -v` 1,433, `grep -i` 1,261, `grep -E` 1,105, `grep --include` 930, `grep -A` 604 (many `-A<N>` variants), `grep -rln` 374, `grep -c` 255, `grep -e` 213, `grep -o` 85, `grep -l` 76, `grep -q` 25, `grep -m1` 25. `head -N` dominates `head` (`-20`, `-30`, `-40`, `-60`, `-5`, `-3`, ...); `head -c` 28. `tail -N` likewise; `tail -c` 81; `tail -n` 36. `cat -n` 660. `wc -l` 587. `cut -c1-200` family about 350; `cut -d:` and `-f1` about 120 (the miner split them off as `-n -d:`/`-n -f1`). `find -name` 336, `-o` 186, `-path` 130, `-type` 78, `-not` 47, `-iname` 45, `-prune` 44, `-print` 38, `-maxdepth` 27. `rg -n` 328, `-i` 97, `--no-heading` 43, `-e` 34, `-g` 33, `--glob` 26, `-t` 23, `-l` 23. `mkdir -p` 246. `nl -ba` 141 (every `nl` use). `sort -rn` 62, `-u` 23. `uniq -c` 84 (every `uniq` use). `awk -F:` 25. `sed -E` 25, `-e` 43. `ls -la` 68, `-d` 30. `rm -f` 34, `-rf` 33. `time -p` 72. `perl -e` 109, `perl -0pi`/`-pi` 101 (in-place edits by regex: a form `sed -i`/`edit` serves). `python3 -c` 31.

Guest-interpreter demand: `python3` 1.0% + `uv run` 5.3% + `perl` 0.16% + `python` 0.01% + `bash` 0.006% ≈ 6.5% of segments if `uv run` is counted as "run Python". Never-class demand with real counts: `git` 2.8% (the largest), `docker` 0.24%, `ps` 0.12%, `curl` 0.12%, `gh` 0.09%, `pkill` 0.07%, `pgrep` 0.04%, `cargo` 0.03%, `kill` 0.007%.

### F4. The peer intersection and the Unix-only remainder (EXECUTED: `classes.md`)

Shipped by all four full agent shells (just-bash, bashkit, just-bash-py, lifo): **40** commands — `base64 basename cat chmod cp curl cut date diff dirname du env file grep head help ln ls mkdir mv nl rev rm rmdir sed seq sleep sort stat strings tac tail tar tee tr tree uniq wc which xargs`. amla-sandbox's 12 are a strict subset of that minus `tree`.

Shipped by every classic set (toybox, busybox, uutils, sbase): **54** — the POSIX floor (`basename cat chgrp chmod chroot cksum comm cp cut date dd dirname du echo env expand false fold head link ln md5sum mkdir mkfifo mknod mktemp nice nl nohup od paste printenv printf pwd readlink rm rmdir seq sleep sort split sync tail tee test touch true tsort tty uname uniq unlink wc yes`).

Unix-only (in some classic set, in no agent shell): **694** names — device, boot, network, kernel-module, init, terminal, printing, typesetting and Plan 9 toolchain commands (`mount`, `insmod`, `getty`, `fdisk`, `troff`, `8c`, `acme`, `venti`, ...). None appears in the corpus. They are the "f" class by construction and confirm that the agent-shell category has already converged on a text-and-files subset.

Only one agent shell ships `cd`, `unset`, `export`, `break`, `source`, `wait`: bashkit, because the others count them as interpreter builtins, not commands (just-bash implements them in `src/interpreter/`, not `src/commands/`). The corpus shows these are 10% of segments; a vfs catalog must list them.

### F5. What the harnesses expose, and what they call safe (READ)

The verb-shaped floor every harness agrees on is **read, write, edit, ls, glob, grep, and a shell**:

- deepagents (Python): `FsToolName = Literal["ls", "read_file", "write_file", "edit_file", "delete", "glob", "grep", "execute"]` (`deepagents:libs/deepagents/deepagents/middleware/filesystem.py:1607`); the read/write classification is explicit: `ls read_file glob grep` → `"read"`, `write_file edit_file delete` → `"write"` (`:172–178`), and parallel file mutations are refused (`_parallel_file_mutation_error`, `:199`). `execute` exists only when the backend is a sandbox (`SandboxBackendProtocol.execute`, `backends/protocol.py:903`).
- deepagentsjs: the same seven names plus `execute` in `libs/deepagents/src/middleware/fs.ts:1254–1937`.
- eve: provided tools `bash`, `glob`, `grep`, `read_file`, `write_file`, `web_fetch`, `web_search`, `ask_question`, `sleep`, task/workflow tools (`eve:packages/eve/src/tools/provided/`). Its `bash` returns `{status: "completed", exitCode, stdout, stderr, truncated}` or `{status: "running", pid, outputDirectory}` after 30 s (`bash.ts:14–40`): a process model vfs does not need, but the two-state output shape is worth copying in spirit.
- Claude Agent SDK: built-in tool names referenced in README/docs are `Bash`, `Read`, `Write`, `Edit`, `MultiEdit`, `Glob`, `Grep`, `Skill` (counted across the repo, EXECUTED grep: Bash 17, Read 13, Write 9, Skill 8, Grep 4, Glob 3, Edit 3, MultiEdit 1); permission is by tool name and optional specifier (`"Read"`, `"Read()"`, `"Bash(git:*)"`-style strings, `types.py:2203–2231`). Server-side tools include `bash_code_execution` and `text_editor_code_execution` (`types.py:1226`).
- gemini-cli (at d42e3f1e7): tools `ls`, `read-file`, `read-many-files`, `write-file`, `edit`, `glob`, `grep`, `shell`, `memoryTool`, `web-fetch`, `web-search` (`git ls-tree d42e3f1e7 packages/core/src/tools/`). Its shell policy (`packages/core/src/utils/shell-utils.ts:205–335`): split the command on operators (`splitCommands`), take each segment's head (`getCommandRoots`), **hard-deny any command substitution** `$( )`, `<( )`, `>( )` or backticks (`detectCommandSubstitution`, `:130`; message at `:221`), then a blocklist of `excludeTools: ["run_shell_command(<prefix>)"]` wins over an allowlist of `coreTools: ["run_shell_command(<prefix>)"]`, both matched as whole-word prefixes (`isPrefixedBy`, `:229`). Two modes: "default allow" (no session allowlist) and "default deny" (a session allowlist is present; everything must be in it). There is no built-in safe list — the operator writes it.
- opencode: the `shell` tool (`packages/core/src/tool/plugin/shell.ts:104`, id `opencode.tool.shell`) runs a scanner (`packages/core/src/shell/scan.ts`) that returns either `{kind: "scanned", commands: [{resource, words, ...}]}` or `{kind: "opaque", reason}` with reasons `command-substitution`, `compound-command`, `dynamic-command-name`, `dynamic-execution`, `heredoc`, `invalid-redirect`, `invalid-structure`, `unterminated-escape`, `unterminated-quote` (`scan.ts:3–13`). Every scanned command becomes a permission resource; the rule set is `ask | allow | deny` per pattern, last match wins, and a bare string means `{"*": action}` (`packages/core/src/v1/config/permission.ts:5–40`). Again: no built-in list of safe commands; the scanner makes commands addressable and the config decides.
- codex: two layers. (1) `codex-execpolicy` is a Starlark policy language: `prefix_rule(pattern=[...], decision="allow|prompt|forbidden", justification, match, not_match)` with alternatives per token and `host_executable` path pinning (`codex:codex-rs/execpolicy/README.md`); the shipped example allows `ls`, `cat`, `head`, `printenv`, prompts on `cp`, forbids `git reset --hard` (`execpolicy/examples/example.codexpolicy`). `core/src/exec_policy.rs:67–146` keeps a `BANNED_PREFIX_SUGGESTIONS` list — prefixes a user may not blanket-allow: every shell (`bash -c`, `sh -lc`, `zsh`, `fish`, `dash`, `ksh`, `cmd /c`, `powershell -Command`), every interpreter (`python3 -c`, `node -e`, `perl -e`, `ruby -e`, `php -r`, `lua -e`, `julia -e`, `deno eval`, `bun -e`, `osascript`), plus `env`, `git`, `rm`, `sudo`, `npm/pnpm/yarn run`. (2) `shell-command/src/parse_command.rs` classifies a command for display and approval into `ParsedCommand::{Read, ListFiles, Search, Unknown}` (`protocol/src/parse_command.rs:9–33`): `cat`, `head`, `tail`, `nl`, `sed -n` → Read (`:2467–2708`); `ls`, `eza`, `find`, `fd` → ListFiles (`:2292–2438`); `grep`, `egrep`, `fgrep`, `rg`, `git grep` → Search (`:2349–2466`). `is_small_formatting_command` (`:2128`) treats `wc tr cut sort uniq tee column yes printf` as always-formatting, `xargs` unless its subcommand mutates, `awk` without a file operand, and `head`/`tail` without a file operand, so a pipeline `cat f | head -n 40` summarizes as the read of `f`. Mutation detectors: `sed -i` (`sed_has_in_place_flag`, `:2235`), `rg --replace` (`:2236`), and `rm -f`/`-rf` as dangerous (`command_safety/is_dangerous_command.rs:205–215`).

Three facts carry over to vfs. First, every harness treats **ls/read/glob/grep as read** and **write/edit/delete as mutation**; vfs's ladder (`none < list < read < add < contribute
< read_write`) already names these rungs. Second, harnesses that decide safety by parsing
(codex, opencode, gemini-cli) all stumble on the same constructs — command substitution,
heredocs, dynamic command names — and either deny or go opaque; a shell that *is* the
executor does not have this problem, because `grep` can only ever be `storage.grep()`
(ADR 069). Third, no harness ships a safe-command list; they ship a **classifier plus a
policy language**. The vfs analogue is the rung each verb already declares.

### F6. Cost per text program, measured on the peers (EXECUTED: `loc_*.tsv`)

just-bash (TypeScript), implementation lines per command directory, tests excluded: median 233, first quartile 124, third quartile 455 over 73 commands (engines and guests excluded). bashkit (Rust), per builtin source file: median 525, q1 273, q3 892 over 106 files (shared helpers, generated code and the interpreter/git/ssh/curl/sqlite directories excluded). The big ones, just-bash / bashkit: `awk` 6,669 / 10,111; `sed` 4,060 / 4,171; `find` 2,475 / 3,365; `rg` 3,207 / 14,774 (bashkit's includes a regex engine port); `jq` 670 (just-bash's own) / 9,820 (bashkit vendors jaq); `tar` 3,344 / 3,130 (archive); `grep` 1,161 / 3,030; `ls` 800 / 2,638; `sort` 732 / 1,641; `printf` 2,028 / 1,091; `diff` 551 / 651; `sqlite3` 1,930 (over sql.js) / 4,720 (over turso). The small ones: `head` 355 / 676 (head+tail), `tail` 63 (shares head's code), `wc` 236 / 431, `cut` 253 / 1,158 (cut+tr), `nl` 387 / 608, `uniq` 142 / 1,641 (sort+uniq), `tr` 373, `cat` 302 / 289, `tee` 83, `rev` 121, `tac` 72, `basename` 90, `dirname` 64, `seq` 261 / 534, `base64` 311 / 224, `echo` 241 / 190, `comm` 190 / 409, `paste` 220 / 467, `fold` 294 / 281, `expand` 634 / 603, `column` 360 / 327, `md5sum` 299 / 501 (checksum).

Reading: a tier-1/tier-2 text program costs 100–500 lines in either language, and the whole 25-program first slice is on the order of 6,000 lines plus the argument parser. `sed`, `awk`, `find`, `jq`, `tar`, `rg`-with-its-own-regex and `sqlite3` are the 2,500–15,000-line items; they are interpreters or engines, not programs.

just-bash also records, per command, the flag set it fuzzes (`flagsForFuzzing`, `src/commands/fuzz-flags.ts`); counting `flag: "` entries gives a floor on each command's accepted flags: `rg` 21, `grep` 21, `gzip` 20, `sort` 14, `ls` 11, `tar` 10, `jq` 9, `join` 8, `find` 8, `cat` 7, `xargs` 6, `nl` 6, `mktemp` 6, `diff` 6, `yq` 5, `split` 5, `sed` 5, `du` 5, `cp` 5, `column` 5, `wc` 4, `uniq` 4, `tree` 4, `tr` 4, `touch` 4, `timeout` 4, `tail` 4, `head` 4, `cut` 4, `date` 4 (EXECUTED count). Those are close to the flag lists in the catalog below.

### F7. A wasm coreutil builds and runs (EXECUTED)

`cargo build --release --target wasm32-wasip1 -p uu_wc --target-dir <scratch>` in the uutils clone (the clone stayed clean; `git status` is empty) finished in **16.2 s** (32 s CPU), compiling 72 crates, producing `wc.wasm` of **1,325,099 bytes** (release, unstripped; `experiments/s2/uu_wc_build.log`). uutils CI builds the `feat_wasm` feature set for `wasm32-wasip1` and `wasm32-wasip2` and runs the integration tests under wasmtime (`uutils-coreutils:.github/workflows/wasi.yml:27–68`); `feat_wasm = ["feat_common_core", "nproc"]` and `feat_common_core` names **78** utilities (`Cargo.toml:592–594`), including every text program in this catalog (`head tail wc cut sort uniq tr nl tac fold paste comm join expand unexpand od base64 base32 md5sum sha*sum cksum split csplit fmt pr tsort shuf numfmt seq yes tee cat ls cp mv rm mkdir rmdir touch ln readlink realpath basename dirname echo printf printenv env true false test date sleep`) but not `grep`, `sed`, `awk`, `find`, `diff`, `xargs` (those are separate uutils projects: findutils, diffutils, sed).

`experiments/s2/run_wasm_wc.py` runs the module under `wasmtime` (Python package, via `uv run --with wasmtime`) with stdin from a file, stdout and stderr to files, fuel metered. Results (`run_wasm_wc.out`): `wc -l -w -c` on a 37-byte, 4-line, 6-word sample printed `4 6 37`; `wc -l` printed `4`; `wc --words` printed `6`; `wc --bogus` printed clap's "unexpected argument" usage text to stderr and exited non-zero. Fuel used was 1.09–1.15 million units per run. wasmtime-py surfaces `proc_exit` as an exception even for exit code 0 (the "trap/exit" line in the output); a runner must catch it and read the code. The July memo's 17-function WASI shim list (`2026-07-24` §4.2) is what this module needs from the host; it ran under wasmtime's own WASI here, not under a vfs shim.

### F8. ripgrep's flag surface versus what agents use (EXECUTED count; INFERRED usage)

ripgrep defines **108** long flags (`crates/core/flags/defs.rs`, `name_long` values; list in `lists/ripgrep-flags.txt`) and 42 short ones. The corpus touches nine: `-n`, `-i`, `--no-heading`, `-e`, `-g`/`--glob`, `-t`, `-l`, and by inference `-A/-B/-C`, `-w`, `-F`, `-v`, `-c`, `-m`, `-o`, `-S`, `--hidden`, `--no-ignore`, `-N`, `--json`, `--files`, `--max-depth`. The other ~85 are engine tuning (`--dfa-size-limit`, `--mmap`, `--threads`), encoding, colour, hyperlink and type-definition flags that have no meaning over a database and should be accepted-and-ignored or refused as `unsupported` with a one-line reason, never silently misread.

### F9. What vfs's verbs already answer (READ: `src/vfs/base.py:879–1570`, `src/vfs/ops.py`)

- `grep(pattern, *, paths, observations, ext, ext_not, globs, globs_not, case_mode ["sensitive"|"insensitive"|"smart"], fixed_strings, word_regexp, invert_match, before_context, after_context, output_mode ["lines"|"files"|"count"], max_count, allow_scan, columns)` (`base.py:1326–1345`, `ops.py:175–176`). `max_count` is per file, ripgrep's `-m` (`:1368`). Matches carry `start`, `end`, `match` (line), `preview` (`models/entry.py:347–375`), so `-n` and `-o` are renderings of data the row already has. The regex engine is Rust `regex` (`crates/vfs-core/src/verify.rs:26,90`), i.e. ERE-like syntax with no backreferences and no lookaround: `grep -E` and `rg` map directly; `grep` (BRE) needs a BRE→ERE translation of `\(`, `\)`, `\{`, `\|`, `\+`, `\?`; `grep -P`/`rg -P` (PCRE) is `unsupported`.
- `glob(pattern, *, paths, ext, ext_not, globs_not, kind, max_count, columns)` (`:1234–1246`): `*` within a segment, `**` across, `{a,b}` alternation, slash-free patterns match leaf names at any depth. That is `find -name`, `-iname` (with `case_mode` absent today — `-iname` needs it), `-path`, `-type` (`kind`), `-not -name` (`globs_not`) and `-maxdepth` (not yet: a glob does not know depth; `tree(max_depth)` does).
- `read(path | observations, *, columns)` (`:879–890`): the whole body, text or bytes, no line window parameter. `cat`, `head`, `tail`, `sed -n 'a,bp'`, `nl` are `read` plus a line-slicing step in the program.
- `ls(path, *, columns)`, `tree(path, max_depth, *, columns)`, `stat(path, *, columns)` (`:892–931`). Columns are selectable (`results/projection.py`).
- `write(entries | path+content|data, *, overwrite, parents)` (`:935–960`): `parents=True` is `mkdir -p`; `overwrite=False` is `set -o noclobber`/`cp -n`.
- `edit(path, old, new | edits, replace_all)` (`:987–1005`): sequential, atomic multi-edit. That is `sed -i 's/old/new/'` with a fixed string, `perl -pi -e 's/.../.../'`, and the harness `edit_file`.
- `delete`, `restore`, `sweep`, `mkdir`, `mkedge`, `rmedge`, `move`, `copy`, `glean(query, limit)`, `graph(...)`, `run(path, arguments)` (`:1030–1570`, `ops.py:36–60`).
- `Observation` fields (`models/entry.py:393–453`): `path kind content data source render_status content_hash mime_type size_bytes version edge_type edge_target edge_weight edge_distance created_at updated_at deleted_at score matches in_degree out_degree depth status populated`. `Entry` adds `name ext lines owner_id external_id`. There are no mode bits, no link count, no uid/gid numbers. `content_hash` exists, so `sha256sum`-class programs can be a `stat` column if the algorithm matches (`[NOT VERIFIED: which hash content_hash uses]`).

---

## What this means for vfs

### The rule (Clay, 2026-10-15), recorded

Common commands keep their **native names and native behaviour**, so the shell feels native to agents and to people. `sed`, `head`, `tail`, `cat -n`, `wc`, `cut`, `sort`, `find` and the rest ship under their own names with their real flag semantics. The corpus tells us which **forms** to implement first — `sed -n 'a,bp'` and `sed -i 's/x/y/'` before the full sed language — and how each form maps to a verb on the inside. We do not replace a familiar command with a vfs-specific spelling or a verb name, and we do not say that `sed -n` "is" `read`. Each command's forms are classified by usage tier so a first implementation covers the measured forms and grows into the full program without changing what the agent types. A form outside the implemented subset returns a classified `unsupported` naming the form (`sed: the 'y' command is not implemented yet`), never a wrong answer.

### The catalog

Tiers: **T1** ships with the first slice (verb builtins, shell builtins, the read-shaped text forms, so that a one-segment command or a `cat | head` style pipe works). **T2** ships with pipes and the pure text programs (Rust kernels in `crates/vfs-core` where the program is a few hundred lines; the shell's argument table in Python). **T3** arrives as wasm programs installed as entries under the bin namespace. **T4** is guest interpreters. **Never** is refused with `ErrorKind.unsupported` and a hint. Class letters: (a) vfs-verb builtin, (b) pure text program, (c) shell builtin, (d) wasm program, (e) guest interpreter, (f) never. "Corpus" is E2's segment count. "Peers" is how many of the five agent shells ship it. Flags are the forms to support first; "→" is the verb mapping. Flag selections beyond the corpus are INFERRED.

#### Tier 1 — first slice (about 90% of segments once pipes exist; about 55% as single commands)

| command | corpus | peers | class | flags / forms to support first | vfs mapping |
|---|---:|---:|---|---|---|
| `grep` | 14,094 | 5 | a | `-n -r/-R -v -i -E -F -w -l -L -c -m N -A N -B N -C N -e PAT --include=G --exclude=G -o -q -h -H -s`; BRE by default, `-E` ERE; `-P` → unsupported | `storage.grep(pattern, paths, case_mode=-i, fixed_strings=-F, word_regexp=-w, invert_match=-v, before/after_context=-B/-A/-C, output_mode=lines\|files(-l)\|count(-c), max_count=-m, globs=--include, globs_not=--exclude)`; `-n`, `-o`, `-h/-H` are renderings of `Match`; `-q` sets exit status only; `-L` = files minus `files`; `-r` without a dir operand = scope `.`; a directory operand without `-r` is `grep: dir: Is a directory` like GNU |
| `rg` | 393 | 3 | a | `-n -N -i -S -F -w -v -l -c -m -A -B -C -e -g/--glob -t/--type -T --no-heading --heading -o --hidden --no-ignore -s --files --max-depth --json`; `-P` → unsupported; ~85 engine flags accepted-and-ignored or refused with reason | same verb call as `grep`; ripgrep's output grammar (file heading, `line:` prefix, `--no-heading` = grep style); `-t py` = `ext=("py",)`; `--files` = `glob("**")` |
| `cat` | 2,609 | 5 | a | `-n -b -s -A -v -e -t`; multiple operands; `-` for stdin | `read(path)` per operand, concatenated; `-n` numbers lines; a media row (bytes, `mime_type`) is emitted as the row itself — see fork 4 |
| `head` | 10,644 | 5 | b | `-n N`, `-N`, `-n -N`, `-c N`, `-q -v`, multiple files | `read` then slice; stdin from the pipe |
| `tail` | 2,747 | 5 | b | `-n N`, `-N`, `-n +N`, `-c N`, `-q -v`; `-f/-F` → unsupported (no streaming) | `read` then slice |
| `sed` (forms) | 8,180 | 4 | b | T1 forms: `-n 'A,Bp'`, `-n 'Ap'`, `-n '/re/p'`, `-n '/re/,/re/p'`, `'s/x/y/[gI]'`, `-i[SUF] 's/x/y/'`, `-E`, `-e` repeated, `Nq`, `'/re/d'`, `'Nd'`, `$p`; full language (`y`, `a/i/c`, hold space, branches) is T2/T3 | ranged prints are `read` + slice; `-i s///` with a fixed string is `edit(old,new,replace_all=g)`; regex `s///` is read + Rust regex replace + `write` (overwrite) |
| `ls` | 2,097 | 5 | a | `-l -a -A -la -lh -1 -d -R -t -S -r -F --color (ignored)`; operands may be globs | `ls(path)`; `-R` = `tree`; `-d` = `stat` of each operand; the long format is fork 5 |
| `cd`, `pwd` | 6,277 | 1 | c | `cd DIR`, `cd`, `cd -`, `cd ..`; `pwd -P/-L` same | shell state; `cd` validates with `stat` (kind must be directory) |
| `echo` | 9,038 | 4 | c | `-n -e -E`; `echo ---` separators are 1,600 uses | shell builtin |
| `printf` | 175 | 3 | c | `%s %d %5.2f %x %%`, `\n \t`, reuse of format over extra args | shell builtin (a 1–2k-line program in the peers; our kernel can be smaller by delegating to Python `%` with a whitelist) |
| `wc` | 626 | 5 | b | `-l -w -c -m -L`, multiple files with total | read + count; a media row counts `size_bytes` for `-c` |
| `mkdir` | 248 | 4 | a | `-p`, `-v`; multiple operands | `mkdir(path)`; `-p` = `write(parents=True)` semantics |
| `rm` | 79 | 4 | a | `-r/-R -f -v`; `-i` → treated as `-f` in a non-interactive shell with a note; `--` | `delete(path)`; `-r` on a directory = delete subtree; without `-r` on a dir: `rm: dir: is a directory` |
| `cp` | 187 | 4 | a | `-r/-R -p -n -v -f`; `cp SRC... DIR` | `copy(src, dst)`; `-n` = `overwrite=False` |
| `mv` | 13 | 4 | a | `-f -n -v`; `mv SRC... DIR` | `move(src, dst)` |
| `touch` | — | 4 | a | `touch F...`; `-c`; `-d/-t` → unsupported | `write(path, content="", overwrite=False)` if absent, else `edit` no-op that bumps `updated_at` `[NOT VERIFIED: whether a no-op write bumps the row]` |
| `stat` | 3 | 4 | a | `stat F`, `-c FMT` with `%s %n %y %F`, `-f` → unsupported | `stat(path, columns)` |
| `file` | 7 | 4 | a | `file F...`, `-b`, `--mime-type` | `stat` → `mime_type`, `kind` |
| `tree` | — | 4 | a | `-L N -a -d -I G -P G --noreport` | `tree(path, max_depth=-L)` |
| `find` (forms) | 282 | 3 | a | T1: `-name -iname -path -ipath -type f\|d -not/! -o -a -maxdepth N -mindepth N -prune -print -print0 -newer -size -empty -delete(→ T2) -exec ... \; (→ T2, as a shell loop)` | compiled to `glob` (`-name` → pattern, `-path` → globs, `-type` → kind, `-not -name` → globs_not) plus `tree`-depth and `stat` post-filters; see fork 2 |
| `test`, `[`, `[[` | 3 (+106 `[[` calls) | 1 | c | `-f -d -e -s -z -n -r -w -x -L`, `=`, `!=`, `-eq -ne -lt -gt`, `&&`/`\|\|` inside `[[`, `=~` | file predicates call `stat`; `-r/-w/-x` answer the caller's rung on the ladder (`read`, `read_write`, `run`-able) |
| `true`, `false`, `:` | 9 | 2 | c | — | exit status |
| `export`, `unset`, `env`, `printenv`, `set`, `local`, `declare`, `readonly`, `shift`, `read`, `eval`, `exec`, `exit`, `return`, `break`, `continue`, `source`/`.`, `alias`, `unalias`, `type`, `command`, `builtin`, `hash`, `help`, `history` | ~450 | 1 | c | the bash 5.2 builtin table (`bashkit:crates/bashkit/src/builtins/mod.rs:626–688` is the reference list of 61 names) | shell state; `source F` = `read(F)` then interpret; `env` with no args prints the environment, `env VAR=x cmd` runs with an overlay; `exec`/`eval` are grammar questions for ADR 1 |
| `which`, `type -P`, `command -v` | 11 | 4 | c | `which CMD...`, `-a`, `-s` | resolution in the bin namespace (Plan 9 `/bin` style): a builtin answers `/bin/<name>` style paths; an installed program answers its entry path |
| `sleep`, `timeout` | 250 | 4 | c | `sleep N[s\|m]`, `timeout N CMD` | shell; bounded by a host cap; `timeout` wraps a program with a deadline |
| `time` | 34 | 2 | c | `time CMD`, `-p` | shell; prints real/user/sys (user/sys as 0 or omitted) |
| `date` | 22 | 4 | c | `+FMT`, `-u`, `-d STR`/`-r F` (→ `stat updated_at`), `-I` | host clock through the shell; never a storage call |
| `basename`, `dirname` | — | 4 | c | `basename P [SUF]`, `-s SUF`, `-a`; `dirname P...` | pure string ops on `vfs.paths` |
| `seq` | — | 4 | c | `seq N`, `seq A B`, `seq A S B`, `-s SEP`, `-w` | shell |
| `whoami`, `id -un`, `hostname`, `uname` | 0 | 4 | c | — | `whoami` prints the caller's principal (identity is a value on the call); `hostname`/`uname` print constants naming the vfs mount |

#### Tier 2 — with pipes: the pure text programs (Rust kernels unless noted)

| command | corpus | peers | class | flags / forms to support first | vfs mapping |
|---|---:|---:|---|---|---|
| `cut` | 462 | 5 | b | `-c LIST`, `-b LIST`, `-d D -f LIST`, `-s`, `--complement`, `--output-delimiter` | stdin or `read` |
| `sort` | 230 | 5 | b | `-n -r -u -k N[,M] -t D -f -h -V -s -o F -c -R`, stable `-s` | stdin; `-o F` = `write` |
| `uniq` | 86 | 5 | b | `-c -d -u -i -f N -s N -w N` | stdin |
| `tr` | 103 | 5 | b | `SET1 SET2`, `-d`, `-s`, `-c`, classes `[:upper:]` etc., ranges `a-z` | stdin |
| `nl` | 141 | 4 | b | `-ba` (every use), `-bt`, `-w N`, `-s SEP`, `-v N` | `read` + number |
| `tee` | 43 | 4 | b | `tee F...`, `-a` | passes rows through; writes with `write(overwrite)`/append = `read`+`write` |
| `xargs` | — | 4 | b/c | `-n N`, `-I {}`, `-0`, `-r`, `-d D`, `-P N` (accepted, serial), `-t` | a shell construct: splits stdin into argument batches and runs a program by name; `find ... \| xargs grep` must work in T2 |
| `tac`, `rev` | — | 4 | b | — | stdin |
| `paste`, `comm`, `join` | 6 | 3–4 | b | `paste -d D -s`; `comm -1 -2 -3 -i`; `join -t D -1 N -2 N -a -v` | stdin + `read` |
| `fold`, `expand`, `unexpand`, `column` | 7 | 3–4 | b | `fold -w N -s`; `expand -t N`; `column -t -s D -c N` | stdin |
| `diff`, `cmp` | 27 | 4 | b | `diff -u -r -q -w -b -i -N --color(ignored)`, `-u3`; `cmp -s` | `read` both; unified diff kernel (Myers) in `vfs-core` — do not reach for a crate's output format without owning the renderer |
| `strings`, `od`, `xxd`, `hexdump` | — | 2–4 | b | `strings -n N`; `od -c -x -A x -N n`; `xxd -l n -s off -p -r`; `hexdump -C` | `read` (bytes body for media rows) |
| `base64`, `base32` | 9 | 4 | b | `-d`, `-w 0`, `-i` | stdin/`read`; bytes-capable (see fork 4) |
| `md5sum`, `sha1sum`, `sha256sum`, `sha512sum`, `cksum`, `b2sum` | — | 3–4 | b | `-c`, `--tag`, `-b` | `read` + hash; `sha256sum` may read `content_hash` off `stat` when algorithms agree |
| `split`, `csplit` | — | 3 | b | `split -l N -b N -d -a N PREFIX` | `read` + `write` many |
| `shuf`, `numfmt`, `tsort`, `fmt`, `pr`, `ptx` | — | 1–2 | b | `shuf -n N -e`; `numfmt --to=iec`; `fmt -w N` | stdin; low priority, ship as uutils wasm (T3) rather than kernels |
| `yes` | — | 2 | c | `yes [STR]` | bounded by the pipe consumer; refuse without a consumer |
| `sed` (full) | — | 4 | b/d | the rest of POSIX sed: `y`, `a`/`i`/`c`, `N`/`D`/`P`, hold space `h`/`H`/`g`/`G`/`x`, `b`/`t` labels, `w F`, `r F`, `l`, `=`; GNU `-z`, `-s`, `0,/re/`, `\|`, `\+` | kernel or wasm: fork 1 |
| `awk` (forms) | 331 | 3 | b/d | T2 forms: `'{print $N}'`, `'{print $NF}'`, `-F SEP`, `'NR==N'`, `'NR>=A && NR<=B'`, `'/re/'`, `'/re/ {print $2}'`, `'{s+=$1} END {print s}'`, `'!seen[$0]++'`, `'{print NR": "$0}'`, `-v var=x`; the full language is T3 | fork 1 |
| `jq` (forms) | — | 3 | b/d | `.`, `.a.b`, `.[]`, `.[N]`, `-r`, `-c`, `-s`, `keys`, `length`, `select(...)`, `map(...)`, `\| `, `--arg`; full jq is T3 | fork 1; a JSON row (`mime_type: application/json`) is the natural input |

#### Tier 3 — wasm programs installed as entries in the bin namespace

| command | corpus | class | precedent | note |
|---|---:|---|---|---|
| `sqlite3` | 0 (`psql` 4) | d | just-bash (sql.js, 1,930 lines of glue), bashkit (turso, 4,720) | whole-file staging (July memo §4.3): the `.db` entry's bytes are the preopen; `-csv -json -header -cmd`, dot-commands `.tables .schema .dump .read .mode`. Note the irony and keep it: vfs *is* a database, but `sqlite3 file.db` must mean the file. |
| `jq`, `yq` | 0 | d | just-bash, bashkit, just-bash-py | jq has official wasm builds; or `jaq` (Rust, MIT) as a kernel dependency — fork 1 |
| `awk`, `sed` (full) | see T2 | d | onetrue-awk / goawk compile to WASI | fork 1 |
| `tar`, `gzip`, `gunzip`, `zcat`, `zip`, `unzip`, `xz`, `bzip2` | 4 | d | just-bash (3,344 lines), bashkit (3,130), lifo | `tar -czf`, `-xzf`, `-tf`, `-C`; whole-file staging in both directions; uutils has no tar, so this is a wasm port of a Rust `tar`+`flate2` tool we build ourselves |
| the uutils 78 (`feat_common_core`) | — | d | this study, F7 | the fallback for any T2 program we have not yet written as a kernel: install `wc.wasm`-style modules as entries; 1.3 MB each unstripped, so `wasm-opt`/strip before shipping, and one `coreutils.wasm` multicall binary is 1 module for all 78 |
| `python3` via CPython-on-WASI, `node` via QuickJS | 667 / 0 | d→e | just-bash (`python3`, `js-exec`), bashkit (`cpython` dir, 2,703 lines), llm-wasm-sandbox | these are T4 guests but *arrive* as wasm programs; same ABI as `sqlite3` |
| `pdftotext`, `tokei`, `html-to-markdown` | 21 / 3 / 0 | d | just-bash ships `html-to-markdown`; `pdftotext` is the corpus's biggest "document" demand | vfs's document renderers (spec 152) already answer `pdftotext` for a PDF row: `cat report.pdf` returns the media row whose text rendering is the extracted text; a `pdftotext` program is then one line over `read` with the rendered text. Record as T3 with the renderer as the engine. |

#### Tier 4 — guest interpreters

| command | corpus | class | precedent | note |
|---|---:|---|---|---|
| `python3`, `python`, `uv run python` | 1.0% + part of 5.3% | e | Monty (verified read-only in the July memo), CPython-on-WASI (just-bash, bashkit, llm-wasm-sandbox, pyodide) | `-c CODE`, `-m MOD`, `script.py`, stdin; `uv run` is a host program and stays "never" — but `uv run python -c ...` and `uv run pytest` are the single largest demand in the corpus (5.3%), and the honest answer is a classified refusal that names the guest: `uv: not available in this shell; python3 is` |
| `node`, `js-exec` | 0 | e | QuickJS (just-bash, amla, quickjs-rs) | `-e CODE`, script |
| `perl` | 110 | e | none | 101 of 110 uses are `perl -pi -e 's/.../.../'` and `perl -0pi`: in-place regex edits that `sed -i`/`edit` serve. Refuse `perl` with `unsupported` and the hint `use sed -i or edit`. Not a guest to build. |
| `bash`, `sh` | 4 | e | just-bash, bashkit register `bash`/`sh` as re-entry | `bash -c STR` and `bash script.sh` re-enter the vfs shell itself (the only interpreter the kernel trusts); `bash` with no args is a no-op |

#### Never — refused as `unsupported`, with the reason the refusal carries

| commands | corpus | why never | refusal hint |
|---|---:|---|---|
| `uv`, `cargo`, `npm`, `npx`, `pip`, `make`, `gh`, `tokei`, `odbcinst` | 5.4% + ~0.3% | host toolchains and package managers; they spawn processes and touch the host filesystem | `unsupported: <name> is a host program; this shell runs programs installed under /bin only` |
| `git` (`log`, `status`, `diff`, `show`, `add`, `commit`, `grep`, ...) | 2.8% | a host VCS over a host working tree; vfs rows carry `version` but no commit graph | `unsupported`; the hint names `stat` (version) and the trash/restore verbs. `git grep` → hint `grep`. Record the demand: the largest never-class item, and the one a future `history`-style verb could partly serve |
| `docker`, `psql`, `ssh`, `scp`, `sftp`, `curl`, `wget`, `ping`, `dig`, `nc` | 0.6% | network and remote processes; ADR 069 (no side door) | `unsupported: network is not available in this shell`; a host may later mount a fetch *tool* under `/.agents/tools` and `run` it — that is the only door |
| `ps`, `pkill`, `pgrep`, `kill`, `top`, `jobs`, `bg`, `fg`, `nohup`, `wait` (with jobs), `&` | 0.3% | no processes exist: every program runs to completion inside one `Result`; `&` is 0.2% of calls | `unsupported: this shell has no background processes`; `wait` with nothing to wait on is a no-op (keep bash behaviour) |
| `sudo`, `su`, `chmod`, `chown`, `chgrp`, `umask`, `mount`, `umount`, `chroot` | `chmod` 14 | authority is a value on the call, never a command; permissions are the ladder and grants | `unsupported: permissions are grants; see grant/revoke`; `chmod +x tool.py` gets the hint that executability is the `/.agents/tools` family, not a bit |
| `uptime`, `nproc`, `sysctl`, `pmset`, `free`, `df`, `open`, `sync`, `tty`, `stty`, `clear`, `reset` | 0.1% | host machine facts or terminal control | `unsupported: no host`; `clear` may be a no-op |
| everything in the 694 Unix-only list (F4) | 0 | devices, boot, kernel, printing, typesetting | `unsupported: not a program in this shell` with a `which`-style `not found` exit 127 |

#### Coverage of the corpus by tier (EXECUTED sums, from `classes.md`)

| after shipping | segments covered | share |
|---|---:|---:|
| T1 (classes a + c, plus the T1 forms of head/tail/sed/wc) | a 29.7% + c 24.1% + head/tail/sed-n/wc ≈ 32.9% | ≈ 86.7% |
| T2 (all of class b) | + remaining b | 88.9% |
| T3 (wasm) | + 0 today | 88.9% |
| T4 (guests: python3, python, bash) | + 1.0% | 89.9% |
| never (f) + artefacts | the remaining 10.1% | — |

The ceiling is 89.9% of segments; `uv` and `git` alone are 8.2% of the never class. By *calls* rather than segments the number will be lower, because one never-class segment fails the whole call: that is why the coverage score below is defined on calls.

### The coverage score

Definition (what we will measure, in order of strictness; each is a fraction of **Bash calls**, weighted equally, over the E2 corpus or any later corpus mined the same way):

1. **parse rate** — the call's full command string parses under the v1 grammar (ADR 1): pipes, `&&`/`||`/`;`, redirects incl. `2>&1` and `>>`, heredocs, `$VAR`/`${VAR:-x}`, `$( )`, globs, brace expansion, `for`/`if`/`while`/`case`, functions, `[[ ]]`, `$(( ))`. Measured by the parser alone on the recorded construct set.
2. **resolve rate** — every segment's head word resolves in the bin namespace (builtin or installed program). A head that resolves to a classified `unsupported` program counts as resolved-but-refused; report that share separately as the *refusal rate*.
3. **flag rate** — every flag used in every segment is in the program's supported table for its tier (the forms column above). An accepted-and-ignored flag counts; an `unsupported` flag does not.
4. **run rate** — the call executes on a fixture mount (a synthetic tree with the file kinds the corpus touches: source files, markdown, JSON, a PDF, an image) and ends with exit 0 or a *correct* non-zero (e.g. `grep` no-match = 1). Compared against bash on the same fixture for the text programs (the oracle), with the known deltas listed (no `-f`, no processes).

Report all four as `covered / total calls`, and the headline is the run rate. The in-scope variant excludes calls whose head is class f (so `git`/`uv` do not mask progress on `grep`); report both, never only the in-scope one. Because E2 recorded only names, flags and constructs (privacy), the replay corpus is **synthesized** from the (command, flag, construct) distribution, not replayed verbatim; the generator and fixture live under `tests/support/` as an oracle-style asset, and the counts (segments resolved, flags accepted) are asserted — never wall-clock — per CLAUDE.md.

### Names and mappings to adopt, things to reject

Adopt:

- One program table, one argument parser, one renderer per program. The argument table is data (name, short, long, takes-value, tier, maps-to), so `help <cmd>` and the `unsupported`-flag refusal come from the same table that the parser uses (just-bash's `flagsForFuzzing` and bashkit's `invalid_option` helper are the precedents).
- Codex's `ParsedCommand` idea as the shell's **summary line**: each call is summarized as reads/lists/searches/mutations of paths before it runs, so a host that wants to prompt can prompt on the summary. The vfs version is exact, not best-effort, because the shell knows the verb each segment calls.
- deepagents' rule that read tools are `read` and `write_file`/`edit_file`/`delete` are `write`: the shell computes the **maximum rung** a call needs from its segments (`grep`→read, `sed -i`→read_write, `mkdir`→add, `run`→run) and asks the ladder once before executing anything (ADR 4).
- gemini-cli's prefix-rule shape for host policy (`run_shell_command(git status)`) and codex's three decisions (allow / prompt / forbidden) with a `justification` the refusal can print: a host denies a program by prefix on the bin namespace.
- The 61-name bash builtin list (bashkit) as the builtin surface to aim at, implemented in the order the corpus demands (`cd echo export unset source test true false set shift break continue return exit local read printf wait` first).

Reject:

- A separate `vfs`-flavoured verb vocabulary at the prompt (`vfs read`, `search`). Clay's rule. The verbs are the inside.
- Any gemini-style blanket ban on `$( )`: it is 3.7% of calls plus 4.4% backticks; the vfs shell evaluates substitution itself, so there is no injection surface to ban.
- `tail -f`, `watch`, `&`, `jobs`: no process model in v1 (0.2% of calls). Refuse clearly; do not simulate.
- `perl` as a guest: 92% of its uses are regex in-place edits; serve them with `sed -i`.
- Numeric-only or decoration flags on `ls`/`rg`/`grep` (`--color`, `--line-buffered`, `--mmap`): accept and ignore, do not refuse — refusing cosmetic flags would fail real calls for nothing.

---

## Forks for the ADRs

**Fork 1 — `sed`, `awk`, `jq`: Rust kernels in `crates/vfs-core`, or wasm programs?** Options: (A) hand-written kernels for the measured forms only (`sed -n` ranges and `s///`, awk `print $N`/`-F`/`NR`/`/re/`/sum, jq path expressions and `-r`), with the full languages refused as `unsupported` until later; (B) full interpreters as wasm programs installed in `/bin` (onetrue-awk/goawk, GNU sed via wasi-sdk or uutils-sed, jq's official wasm), with the T1/T2 forms handled by the same program; (C) A for the forms now, B for the full language later, same name throughout. Evidence: the measured forms are a few hundred lines each (just-bash's `head`-class programs are 100–400 lines) while the full languages are 4,000–10,000 (F6); `sed -n` alone is 12% of all segments and must be in T1, before any wasm runtime exists. Lean: **C**. The kernel covers the forms, the wasm program replaces the kernel's body for the full language when T3 lands, and the agent types the same thing both times. For `jq`, add the option of depending on `jaq-core` (MIT) as a crate — a framework-dependency decision, not a copy — against building a wasm `jq` entry; lean wasm, because jq's demand is zero in the corpus and a dependency has a wheel cost.

**Fork 2 — `find`: a glob alias or its own program?** Options: (A) `find` rewrites to `glob` and refuses anything but `-name`; (B) its own program with the POSIX predicate grammar (`-name -iname -path -type -not -o -a -prune -maxdepth -newer -size -empty -print -print0 -exec -delete`), compiled to `glob`+`tree`+`stat` calls and post-filters. Evidence: 282 uses, with `-o` 186, `-path` 130, `-type` 78, `-not` 47, `-prune` 44, `-maxdepth` 27 — the predicate language is used, not just `-name`; the peers all ship a real `find` (just-bash 2,475 lines, bashkit 3,365). Lean: **B**, own program, T1 for the listed predicates; `-exec`/`-delete` in T2 as a shell loop over the result rows; `glob` gains `case_mode` (for `-iname`) and the shell computes depth from `tree`.

**Fork 3 — `rg` and `grep`: one program with two names?** Options: (A) one program, one flag table, both names; (B) two front-ends (two flag tables, two output grammars) over one verb call; (C) ship only `grep` and alias `rg` to it. Evidence: both call `storage.grep()` with the same parameters, but the flag tables differ (`--include` vs `-g`; `-t py` has no grep equivalent; `-r` is implicit in `rg`; `-P` differs), and the default output differs (rg groups by file with a heading and no filename prefix; grep prints `file:line:text`); agents use both (`grep -rn` 2,392 vs `rg -n` 328) and expect each one's output shape. Lean: **B**: one verb, two names, two flag tables, two renderers, sharing the BRE/ERE translation and the `unsupported`-flag table. Not A, because a merged table misreads `-g` and `-t`; not C, because `rg --no-heading` and `rg -t` are real uses.

**Fork 4 — `cat` of a binary returns the media row (yes, per the brief): the consequence.** The row carries `data` + `mime_type` and a text rendering when a renderer exists (spec 152). Consequences to write down: (i) the text projection prints the canonical placeholder, one line, so `cat img.png | wc -l` is 1 and `cat img.png | wc -c` must be `size_bytes` — which means every text program declares whether it is **bytes-capable** (`wc -c`, `base64`, `sha256sum`, `xxd`, `od`, `file`, `head -c`, `tail -c`, `cp`, `tee`, `>` redirection consume `data`) or **text-only** (`grep`, `sed`, `cut`, `sort` consume the rendering or the placeholder); (ii) `cat a.png > b.png` and `cat a.pdf | base64 -w0` are correct because the pipe payload is rows, not bytes (ADR 3); (iii) `cat report.pdf | grep total` searches the *rendering* (`render_status` says whether one exists), which is better than Unix, and the docstring must say so; (iv) the MCP projection of the same `Result` yields an image/resource block, never base64 text (brief; July memo §4). Lean: adopt the bytes-capable flag per program as a column in the program table.

**Fork 5 — what `ls -la` shows when the row has owner, version and mime, not mode bits.** Options: (A) fake Unix mode bits (`-rw-r--r--`) from nothing; (B) print the row's real columns in the long format's *positions*: a kind glyph (`d` directory, `-` file, `l` edge), the caller's effective rung on the ladder in the mode column (`list`→`l--`, `read`→`r--`, `add`→`r-a`, `contribute`→`r-c`, `read_write`→`rw-`, or spelt out), `version` where the link count goes, `owner_id` where the owner goes, `mime_type` in place of the group, `size_bytes`, `updated_at`, `name`; (C) long format = `stat` columns chosen by `columns`, with `-l` selecting a documented default set. Evidence: `ls -la` is 68 uses, `ls -d` 30; agents read the size, the date and the name and almost never the bits; the `Observation` has no bits to show (F9); deepagents' `ls` returns `FileInfo` with `size`, `modified_at`, `is_dir`. Lean: **B with C's mechanism** — a fixed default long format whose fields are real, documented once in the program's help, and `columns` for anything else. Never A: a fake mode string is a lie an agent will act on.

**Fork 6 (new) — `uv run`/`python3` demand versus the guest bet.** 6.5% of segments are "run Python". Options: refuse all of it until T4; or ship `python3 -c` early via Monty (sandboxed interpreter, no CPython-on-WASI runtime) as the first guest, with `uv run` refused and hinted. Lean: Monty first for `-c` and small scripts; measure the share it recovers with the coverage score before building the WASI runtime.

**Fork 7 (new) — `git` is 2.8% and will never run.** Options: refuse with a hint; or teach the refusal to point at what vfs *does* have (`stat` → `version`, the trash view, `restore`), and open a question for a `history`-style verb later. Lean: refuse + hint now; record the demand in `open-questions.md` rather than inventing a verb here.

---

## Sources

Repositories (`~/Git/Repos/`, commits as in the header; licences from `licenses.log`): busybox@371fe9f `*/*.c` `//applet:` comments; toybox@6a0c0ef `toys/*/`, `www/roadmap.html` (lines 330–420 of the tag-stripped text: the LFS command list and the `record-commands` method); uutils-coreutils@4945ecf `src/uu/`, `Cargo.toml:592–594`, `.github/workflows/wasi.yml`, `src/uu/wc/Cargo.toml`; sbase@b30fb56 `README`; plan9port@b6564bd9 `src/cmd/`; 9front@a0806493 (DIRTY) `sys/src/cmd/`, `rc/bin/`; just-bash@9ab0e0d `packages/just-bash/src/commands/{registry.ts,fuzz-flags.ts,*/}`; bashkit@b7904a4 `crates/bashkit/src/builtins/mod.rs:626–688`, `crates/bashkit/src/interpreter/mod.rs:2096–2400`, `README.md:17,644,663`; just-bash-py@48d111c `src/just_bash/commands/`; lifo@5a35d05 `packages/core/src/commands/`; amla-sandbox@169384f `src/amla_sandbox/__init__.py:27`, `langgraph.py:369`; gemini-cli@d42e3f1e7 (DIRTY; via `git show`) `packages/core/src/tools/`, `packages/core/src/utils/shell-utils.ts:15–347`; opencode@13263f30ed `packages/core/src/tool/plugin/shell.ts`, `packages/core/src/shell/scan.ts:1–60`, `packages/core/src/v1/config/permission.ts`; codex@16e578d `codex-rs/execpolicy/README.md`, `execpolicy/examples/example.codexpolicy`, `core/src/exec_policy.rs:54–146`, `shell-command/src/parse_command.rs:2128–2720`, `shell-command/src/command_safety/is_dangerous_command.rs`, `protocol/src/parse_command.rs:9–33`; claude-agent-sdk-python@aada024 `src/claude_agent_sdk/types.py:529,1226,2203–2332`, `README.md`; deepagents@0bf167654 `libs/deepagents/deepagents/middleware/filesystem.py:160–192,1607–1611,2028`, `backends/protocol.py:436–963`; deepagentsjs@9f3bfd5 `libs/deepagents/src/middleware/fs.ts:1254–1937`; eve@5666d2f0d `packages/eve/src/tools/provided/`; ripgrep@3fce3b5 `crates/core/flags/defs.rs`.

vfs (live tree, HEAD ac5c515): `src/vfs/base.py:879–1570`, `src/vfs/ops.py:1–90,175–176`, `src/vfs/storage/protocol.py:121–290`, `src/vfs/models/entry.py:53–110,347–453`, `crates/vfs-core/src/verify.rs:26,90`; study inputs `experiments/e2/commands.md` (EXECUTED by E2, 2026-10-15), `00-brief.md`, `refresh.log`, `licenses.log`.

Executed artefacts (this study): `experiments/s2/lists/*.txt`, `matrix.py`, `matrix.md`, `classes.md`, `loc_just-bash.tsv`, `loc_bashkit.tsv`, `uu_wc_build.log`, `run_wasm_wc.py`, `run_wasm_wc.out`. Toolchain: `cargo` with `wasm32-wasip1`; `wasmtime` Python package via `uv run --with wasmtime` (not installed in the project).

No web sources were consulted; every documentation claim about POSIX/GNU flag semantics is marked INFERRED and should be checked against POSIX.1-2024 when a program's argument table is written.
