# Numeric wait recognizes the current shell’s children

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

A numeric wait operates only on a job owned by the calling shell within that line.

## The problem

The hub knows PIDs across forks even when the current shell has no such child. A subshell can wait for or observe the status of unrelated work in the same line.

## Proposed changes

Check ownership of active and retained job statuses before waiting. Keep the ordinary post-completion wait behavior of a parent for its children.

## Acceptance tests

Exercise parent and subshell waits on their own and each other’s job identifiers. Assert returned statuses, consumption and absence of blocked foreign waits.

## Builds on

[machine/builtins.rs L2102](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/builtins.rs#L2102) · [machine/builtins.rs L2149](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/builtins.rs#L2149) · [machine/shell.rs L343](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/shell.rs#L343)
