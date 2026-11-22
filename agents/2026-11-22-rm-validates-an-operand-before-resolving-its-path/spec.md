# rm validates an operand before resolving its path

Draft, 2026-11-22. Priority finding from the shell review of `cbda2721`.

## The outcome wanted

An invalid removal operand produces no delete request, regardless of the current directory or recursive and force options.

## The problem

The file program normalizes its operand before requesting deletion. An empty pathname becomes the working directory, and a final dot or double-dot selects its resolved directory. In a writable subtree the resulting request is a real cascading delete. This is a serious failure mode for an empty variable or a malformed cleanup path. The production database independently protects its root.

## Proposed changes

Check the original pathname and its final component, allowing for trailing separators. Preserve the VFS root safeguard and the ordinary deletion of valid targets.

## Acceptance tests

On a recording host, invalid operands leave every entry and the delete log untouched. A valid sibling operand still follows the documented per-operand behavior.

## Builds on

[programs/files.rs L679](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/files.rs#L679) · [machine/exec.rs L1886](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/exec.rs#L1886) · [src/vfs/shell/host.py L476](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/src/vfs/shell/host.py#L476)
