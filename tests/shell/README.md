# The shell corpus

Every case here is a script written for this corpus, and bash's record is its answer. Tests never run bash: they read the records.

## A case

`cases/<area>/<name>.sh` is one construct to a file, a few lines of bash that print what the construct does. Its first lines are headers:

```bash
# tier: language
# world: none
```

- `tier: language` means the script runs only builtins, keywords and functions: no program. `tier: program` means it runs at least one program (`cat`, `grep`, `sort`, ...).
- `world: none` runs the script in an empty working directory. `world: seed` runs it in a fresh copy of `world/`.
- `stderr: exact` makes the case compare standard error as text. Without it, standard error is compared as empty or not.

`cases/<area>/<name>.json` is the record: what bash 5.3 printed and the status it exited with, made by `scripts/shell_record.py` in an image pinned by digest. A record is never written by hand.

A deliberate difference from bash keeps bash's record and gains `<name>.shell.json`, the shell's own answer; `deltas.txt` names the case and gives its reason.

## The environment a case runs in

The working directory is `/work`. The environment is exactly `HOME=/home/agent`, `PATH=/usr/local/bin:/usr/bin:/bin`, `LC_ALL=C.UTF-8`, `TZ=UTC`, `USER=agent`, `LOGNAME=agent` and `TERM=dumb`, and bash adds its own variables. `$0` is `bash`. Standard input is empty. The script is run as `bash --norc --noprofile -c "$script" bash` by an unprivileged user.

## Rules for a case

- **A record must be a function of the script.** Nothing that changes from run to run: no `$$`, `$BASHPID`, `$PPID`, `$RANDOM`, `$SRANDOM`, `$SECONDS`, `$EPOCHSECONDS`, `date`, `sleep`, `time`, `/proc`, `hostname`, `ulimit`, file modification times, `ls -l`, and no two concurrent jobs that both write output. The recorder runs every case twice and refuses a case whose runs differ.
- **No whole-state listings.** No bare `set`, `declare -p`, `export -p`, `env`, `alias` or `shopt` with no names: they print bash's private variables.
- **No version.** Nothing prints `$BASH_VERSION`, `$BASH_VERSINFO` or `$MACHTYPE`.
- **A language case runs no program.** In place of `cat`, read with `while IFS= read -r line || [ -n "$line" ]; do printf '%s\n' "$line"; done`, or with `mapfile`.
- **A syntax error runs nothing before it.** Bash runs a script command by command, and this shell parses the whole script first. A case about a syntax error has the error in its first command, so bash also runs nothing.
- **Small.** Most cases are 2 to 15 lines, and none prints more than a few KB.
