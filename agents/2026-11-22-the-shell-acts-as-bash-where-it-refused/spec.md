# The shell acts as bash where it refused

A draft, written on 2026-11-22 from a study of every deliberate departure of the shell from bash, made against the branch `the-shell-speaks-bash` at `bcf8966`. It is not reviewed, and nothing is built.

Ruled on 2026-11-22: the shell acts just like Linux bash in every way it can. This lands before `0.1.0b1`, when the public surface is frozen.

## The outcome wanted

`tests/shell/deltas.txt` holds only the cases listed under "What cannot act as bash", each with its reason. Every word the parser refuses today runs as bash runs it under `bash -c`, and a line is parsed and run one complete command at a time, as bash does.

## Builds on

- `agents/2026-11-21-the-shell-speaks-bash/spec.md` and its `progress.md`.
- The 35 delta cases under `tests/shell/cases/`, which already carry bash's record, so each item below is measured by cases that move from `deltas.txt` to passing.
- The job table (`sh.jobs`, `hub.job_status`), `deparse.rs`, `run_top`'s skip of the rest of a line after an error, and the `Value` request the vfs host already answers for `time` and `random`.

## The problem

- **A refused word fails the whole line before anything runs.** `set -e; trap 'echo cleanup' EXIT; echo body` prints nothing and exits 2, where bash prints `body`, then `cleanup`. The refused words are `eval`, `source`, `.`, `exec`, `trap`, `jobs`, `fg`, `bg`, `disown`, `suspend`, `alias`, `unalias` and `coproc`.
- **The refusals were never a security wall.** Every effect of a line is still a public verb called as the caller. A parse at run time happens inside the module, where fuel and counted memory already bound it.
- **Variables bash sets expand to nothing here, with no error.** These are `$RANDOM`, `$SECONDS`, `$EPOCHSECONDS`, `$EPOCHREALTIME`, `$SRANDOM`, `$BASH_VERSION`, `BASH_VERSINFO`, `$HOSTNAME`, `$MACHTYPE`, `$BASH_SOURCE` and `$BASH_COMMAND`. `$$` is 1000 in every line, so `tmp=/tmp/x.$$` names one file in every concurrent line.
- **`bash -c`, `sh -c` and `bash FILE` answer 127.**
- **`kill` prints that signals are not supported**, and `umask`, `time`, `ulimit`, `history` and `logout` answer otherwise than bash.
- **`command -v grep` prints `/usr/bin/grep`, and running that path answers 127.**
- **A line is parsed whole before it runs.** A syntax error on a later line stops the earlier lines from running, where bash runs them, then prints the error and exits 2. On one line the two agree, because bash's unit is the complete command up to a newline. Only parsing one command at a time can make `shopt -s expand_aliases` and `shopt -s extglob` on an earlier line exact.
- **Process substitution runs its list to its end before the command that names it**, where bash runs the two side by side.

## Decisions

1. **A line is parsed and run one complete command at a time, as bash does** (ruled on 2026-11-22).
   - The source-bytes check stays at the start of the line.
   - `parse` stays in the crate for a host that wants a check without a run, as `bash -n` gives.
   - A parse budget spent part-way through ends the line with 137 and a budget fact.
   - This retires the spec's decision that a line which does not parse "fails and changes nothing", and the `cli` docstring and reference page change with it.
   - `success` keeps its meaning: a syntax error on a later line means the line did not run to its end as written. `statuses` shows which pipelines ran.
2. **One routine runs text under a name**, used by the top level, `eval`, `source`, `.`, `bash -c`, `sh -c`, `bash FILE` and trap handlers.
   - It parses under the line's parse limits, charges the tree to counted memory, and counts one level of the `nesting` budget for each text nested inside another.
   - Its requests take the next ordinals of the current task, so request keys stay deterministic.
   - `source` reads its file with one `read` as the caller, and a refusal reads as bash's `No such file or directory` or `Permission denied`, with status 1.
   - `bash -c` and `bash FILE` run the routine in a subshell.
   - A function defined inside the text outlives it, so a function carries the script its here-documents live in.
3. **`trap` is a table of handlers on the shell.**
   - `EXIT` runs at the end of the line, at `exit`, at a `set -e` exit, and in each subshell that set its own.
   - `ERR` fires where `set -e` would exit; `set -E` decides whether functions inherit it.
   - `DEBUG` runs before each simple command, with `BASH_COMMAND`; `RETURN` runs when a function or `source` returns; `set -T` decides whether functions inherit both.
   - `trap -p` and `trap -l` print as bash prints them.
   - A signal trap is accepted and fires only for the line's own `kill` of `$$`.
4. **A wall ends the line as `SIGKILL` ends a process** (ruled on 2026-11-22). A wall is the deadline, the fuel, the module's memory or a cancel. The line ends with 124, 137 or 130 and runs no trap, so nothing does work past its budget.
   - The ruling names a fallback if this proves wrong: `EXIT` runs after a wall, outside the fuel cap. That fallback would need its own bound, since a handler is unbounded text.
5. **`exec` with only redirections changes the shell's own descriptors for the rest of the line**, as `exec 3<f`, `exec >log 2>&1` and `exec 3>&-` do. Each command's output is written through as it ends, so a wall loses nothing bash would have written. `exec` with a command resolves it as a program only, runs it, and ends the line with its status without running `EXIT`.
6. **Job control gives bash's non-interactive answers.**
   - `fg`, `bg` and `suspend` print bash's own messages with status 1.
   - `jobs` lists the line's jobs, each with its text from `deparse.rs`.
   - `disown` drops a job from the table.
   - `kill` of a job ends its task and records 128 plus the signal; `wait` then returns it.
   - `kill` of `$$` runs the trap or ends the line with 128 plus the signal.
   - `kill` of any other pid prints `No such process`, with status 1.
   - `wait -n` waits for the next job to end.
7. **`alias` and `unalias` define, list and remove aliases**, which is bash's non-interactive default exactly. With `shopt -s expand_aliases`, an alias takes effect from the next complete command, which decision 1 makes exact.
8. **The variables come from the host at first use, through the `Value` request.**
   - `$$` is a `pid` value, unique among the process's live lines; `$!` and `$BASHPID` derive from it by ordinal.
   - `RANDOM` takes one seed from the host and then runs the machine's own generator. A line stays a function of its text and its replies.
   - The fixed values (`BASH_VERSION`, `BASH_VERSINFO`, `MACHTYPE`) are constants of the crate. The rest come from the host: `HOSTNAME`, and the clock values for `SECONDS`, `EPOCHSECONDS` and `EPOCHREALTIME`.
9. **Process substitution runs beside its command**, as a task with a bounded pipe, as pipeline stages do. `coproc` is a job with two pipes and the `COPROC` array.
10. **The small builtins act as bash.**
    - `umask` stores and prints its value, with no effect, since vfs keeps no mode bits.
    - `time` prints `real` from two clock values, with `user` and `sys` as zeros.
    - `ulimit` prints the line's real budgets; lowering one is allowed, and raising one prints bash's `cannot modify limit: Operation not permitted`.
    - `history` prints nothing, with status 0. `logout` prints `not login shell: use 'exit'`.
    - `enable` and `compgen` act as bash.
    - `help` prints the shell's own usage text, since reproducing bash's would copy it.
    - A table program's absolute name (`/usr/bin/grep`) runs it.
    - The machine serves `/dev/zero` and `/dev/urandom`.
11. **`HOME` stays `/`** (ruled on 2026-11-22). It is what a container user with no home gets, and bash acts on whatever environment it is given.

## What cannot act as bash

- **A signal from outside.** A line is no process, so nothing can address it. A cancel ends it with 130 and runs no handler.
- **A trap after a wall**, by decision 4.
- **A job that outlives the call.** The line waits for its jobs at its end, bounded by the deadline.
- **Stopping a job.** Nothing sends a stop signal, so `fg`, `bg` and `suspend` give bash's non-interactive answers.
- **Another process.** There is none to signal.
- **Unbounded work.** The budgets are the contract.
- **The order in which concurrent jobs interleave.** Request keys must be deterministic, so the shell prints one fixed order among those bash could print.
- **CPU times**, which have no process accounting behind them.
- **Mode bits, owners and symlinks.** These are what vfs stores today. Whether vfs stores mode bits is an open question on the program-table spec.
- **The text of `help`.**

## Tests

- The delta cases move from `deltas.txt` to passing, and the corpus ratchet holds them.
- A law that request keys stay equal over two runs of a line that uses `eval` and `source`.
- The stack law is measured again with a parse at run time on top of a deep run.
- A case that runs the commands before a syntax error on a later line, against bash's record.
- A counted test that a wall runs no trap.
- A test that two concurrent lines get different `$$` values.

## Scope

- The crate: the parser's top level, the machine, the builtins.
- The vfs host's `Value` answers.
- `documentation/reference/shell.md`: the refused-words table goes, and the parse paragraph changes.

## Not checked

- The cost of the stack law with a parse at run time.
- How many delta cases each decision moves.
- Whether `extglob` should then be a syntax error when it is off, as in bash; today the parser always accepts it.

## Choices to confirm

- Whether `bash -n`-style checking is offered on `cli` as a flag. It is not recommended, because it adds surface.

## One line

Every refused word runs as bash runs it inside one call, a line is parsed one command at a time, and only outside signals, traps after a wall, jobs past the call and unbounded work stay different.
