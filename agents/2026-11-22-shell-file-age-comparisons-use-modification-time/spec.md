# Shell file age comparisons use modification time

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

Both conditional syntaxes compare existing paths by their modification times.

## The problem

The stat reply omits the timestamp, so newer-than and older-than both answer false when the paths exist.

## Proposed changes

Carry comparable modification times through the reference host, VFS adapter and wire. Preserve Bash’s rules for equality and missing operands.

## Acceptance tests

Check older, newer and equal timestamps and both missing-operand orders on each host.

## Builds on

[machine/test.rs L203](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/test.rs#L203) · [src/vfs/shell/host.py L408](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/src/vfs/shell/host.py#L408)
