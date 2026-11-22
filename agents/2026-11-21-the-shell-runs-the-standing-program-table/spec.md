# The shell runs the standing program table, and `ls -l`

A draft, written on 2026-11-21 from a staff review of the shell before its pull request. It is not reviewed, and nothing is built.

Ruled on 2026-11-22: this lands before `0.1.0b1`, when the public surface is frozen, not in the `0.1.0` gate after it.

## The outcome wanted

Every program of the table in `context/specifications/active/167-the-shell-pipeline-core/spec.md`, which `agents/2026-11-21-the-shell-speaks-bash/spec.md` says still stands, runs in the shell, so the measured sample's in-scope lines run.

## Builds on

The library programs of `crates/vfs-shell/src/programs/` and the host-resolved program request.

## The problem

- `ls -l` and `ls -la` are refused as invalid options, and they are among the lines an agent types most; the roadmap's F4.1 has `ls -l` print `kind size_bytes updated_at owner_id version`, never mode bits.

`basename`, `dirname`, `seq`, `env`, `printenv`, `which`, `sleep`, `timeout`, `date`, `whoami`, `hostname`, `uname`, `nl`, `stat`, `file`, `tree`, `rg` and `xargs` are in the table, and each answers 127 today. `date`, `sleep` and `uname` alone are five of the 28 lines of the weighted sample that do not run.

## Decisions

1. Pure transforms (`basename`, `dirname`, `seq`, `nl`, `xargs` over builtins and library programs) join the library.
2. Programs that read the host (`date`, `whoami`, `hostname`, `uname`, `env`, `printenv`, `which`) answer from values the host gives, through the `value` request, so a line stays a function of its replies.
3. `sleep` and `timeout` are bounded by the line's deadline and spend no fuel while they wait.
4. `stat`, `file` and `tree` print from `stat` and `ls`; `rg` is served as `grep -r` is.
5. `ls -l` and its forms print the roadmap's columns from one `ls` of the directory, with the long fields the verb returns.

## Tests

A recorded corpus case for each program, in the program tier.

## Scope

The crate's library and the vfs host's values.

## Not checked

Which of the table's forms an agent uses.

## Choices to confirm

Whether `sleep` waits in real time or ends at once.

## One line

Every program the shell's table names runs.
