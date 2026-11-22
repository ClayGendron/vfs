# Output process substitutions run alongside their producers

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

A producer and its output substitution consumer make finite progress and observe EOF in order.

## The problem

The consumer starts after the producing command returns, while the producer can wait on a full pipe or retain a descriptor needed for EOF.

## Proposed changes

Schedule reader and writer concurrently and release command-owned writer ends at completion. Preserve the tracked output-substitution case.

## Acceptance tests

Pass a finite multi-buffer stream followed by EOF, and cover a consumer that exits early. Assert final bytes, completion status and closed descriptors.

## Builds on

[machine/exec.rs L1787](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/exec.rs#L1787) · [machine/exec.rs L1865](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/exec.rs#L1865)

See also [The shell closes its known failures and counts depth by construct](../2026-11-21-the-shell-closes-its-known-failures/spec.md).
