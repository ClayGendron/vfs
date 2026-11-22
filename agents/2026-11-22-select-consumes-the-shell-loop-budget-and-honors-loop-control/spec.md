# Select consumes the shell loop budget and honors loop control

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

Each select iteration counts once and break or continue observes the same loop depth as other compound loops.

## The problem

Its loop omits the accounting used by other loops. A top-level break can fail to exit the body, allowing subsequent statements to run.

## Proposed changes

Use shared loop bookkeeping. Restore depth after every exit and carry multi-level loop control to its proper enclosing loop.

## Acceptance tests

Compare top-level and nested select behavior against Bash. Check effects following a break and count iterations under a small limit.

## Builds on

[machine/exec.rs L746](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/exec.rs#L746) · [machine/builtins.rs L218](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/builtins.rs#L218) · [machine/builtins.rs L2191](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/builtins.rs#L2191)

See also [The shell closes its known failures and counts depth by construct](../2026-11-21-the-shell-closes-its-known-failures/spec.md).
