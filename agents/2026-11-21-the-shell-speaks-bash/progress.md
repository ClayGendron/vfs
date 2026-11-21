# Progress

## Step in hand

Steps 6 and 7: the vfs host, `cli` on the public surface, the reference page, and the remaining corpus cases.

## Score

3,179 of 3,320 corpus cases pass against `MemoryHost` (95.8%), `scripts/shell_score.sh`. Every case parses, or classifies as bash classifies it. A one-in-ten sample of the passing language-tier cases runs through the vfs host under pytest (`tests/shell/test_host.py`) and agrees.

The weighted 100-command sample of the 2026-10-15 study parses 100 of 100, and so does its 100-command coverage set. 72 of the weighted 100 run (`crates/vfs-shell/tests/measured_corpus.rs`). Each of the other 28 names a program this shell never runs: `git` (10), `uv` (7), `docker` (3), `date` (3), and `awk`, `curl`, `diff`, `perl`, `pgrep`, `pkill`, `ps`, `psql`, `python3`, `sleep` and `uname` once each.

## Done

- **Step 0.** `research-runtime.md`, `research-bash-suites.md`, and the spec review `reviews/spec-review.md` with its disposition.
- **Step 1.** The recorder `scripts/shell_record.py`, the referee `debian:sid-slim` pinned by digest (bash 5.3.15, GNU coreutils 9.12), the seed tree `tests/shell/world/`, the case format `tests/shell/README.md`, 3,320 recorded cases in 38 areas, `known_failures.txt`, `deltas.txt` with 35 refusal records, and `scripts/shell_score.sh`.
- **Step 2.** `crates/vfs-shell`: no dependencies, no unsafe code, the clippy denials of decision 9, the source rules of decisions 1, 4 and 9, the parser, and the parser fuzz target. Reviewed in `reviews/step-1-2-code-review.md`, with its disposition.
- **Steps 3 to 5.** The machine: async Rust polled inside `step`, keyed requests, pipes, jobs, every expansion, the builtins, the counted memory, the slice, and cancel. The programs: `cat`, `cp`, `cut`, `find`, `grep`, `head`, `ls`, `mkdir`, `mv`, `rm`, `sed`, `sort`, `tail`, `tee`, `touch`, `tr`, `uniq` and `wc`. The laws and the machine fuzz target are in `crates/vfs-shell/tests/laws.rs`. The module is `crates/vfs-shell-wasm`; its laws run under `wasmi` in `crates/vfs-shell-wasm/tests/module_laws.rs`.
- **Step 6.** `vfs.shell.run_line`, the native `ShellMachine` in `vfs-core`, and `cli` on `AsyncVirtualFileSystem`, `AsyncSession`, `VirtualFileSystem` and `Session`. Each request is one public verb with the admitted authority, a spied test holds it, and the system actor is refused.
- **Step 7.** `documentation/reference/shell.md`.

## Decided inside the laws

- A case runs as `bash --norc --noprofile -c "$script" bash` in `/work`, as an unprivileged user, with the environment in `tests/shell/README.md`.
- Bash parses and runs one top-level command at a time, and this shell parses the whole line first. A syntax-error case puts its error in the first command, so the two agree. Two extglob cases are malformed to bash only because `extglob` was off when bash parsed them.
- Refused before anything runs: `eval`, `source`, `.`, `exec`, `trap`, `jobs`, `fg`, `bg`, `disown`, `suspend`, `alias`, `unalias` and `coproc`. A refused word reached at run time also ends the line with status 2.
- A request key is the path of the task in the walk (one index for each enclosing pipeline stage, subshell, substitution and job) and the request's ordinal in that task.
- Process substitution runs its list to its end into a buffer before the command that names it. `>(list)` feeds its list once the command ends.
- A file written through a redirection is created or truncated when it is opened, as bash does. Its bytes are held and written in one appending request when the redirection ends; a read of the same path writes them first.
- A loop iteration is one run of a loop's body.
- The vfs host reads each body once for the line and forgets it at any mutation. A verb a program was refused is kept as a warning: a program's failure is not the call's.
- `cli` is a management method, not an op, and joins `MANAGEMENT_METHODS`. It returns `vfs.shell.LineResult`, a `Result` with `stdout`, `stderr` and `exit_status`.

## Reported and not taken

- The vfs host drives the native build, not the module in a runtime. `research-runtime.md` recommends linking `wasmtime` into `vfs-core`, at about 3.5 MB of wheel; that is decision 15's carriage, and it is not built.
- The binding does not release the interpreter lock during a slice: the machine is not `Send`, by design, so a slice runs on the calling thread.
- `grep -r` and `find` walk through `list` and `read` instead of the indexed verbs.
- The Oils spec-suite rate is not measured, and the differential fuzzer is not built.
- The weighted sample's run rate is 72%, below the 85% the spec names. Every line that does not run names a program the roadmap says never runs.
- Roadmap F1 (removing `SupportsRun`), `move(replace=)` and `glob(case_mode=)` are not built.
- `printf` floats use 64-bit doubles where bash uses `long double`, so `%.20f` and `1e309` differ.
- The regular-expression engine has no back-references, and a match longer than 4,000 characters ends the search.

## Next

The remaining 141 known failures, the step 3 to 5 review's findings, then the pull request.
