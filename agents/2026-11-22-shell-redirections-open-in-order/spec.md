# Shell redirections open in order

Draft, 2026-11-22. Priority finding from the shell review of `cbda2721`.

## The outcome wanted

A refusal from an earlier redirection prevents later targets and command output from being touched.

## The problem

The deferred-write optimization for output-only commands uses stat to decide whether a path looks writable. Stat cannot prove the subsequent write will be accepted. When a command has multiple redirections, a write denial on the first target can be discovered only after a later writable target has been opened or filled. This violates the documented left-to-right failure guarantee.

## Proposed changes

Open each observable redirection in shell order and establish the authoritative write result before proceeding. Retain single-write coalescing only where it preserves that ordering.

## Acceptance tests

Inject failure at the first open in a multi-target command. Verify the existing second target, both output streams, status and host request order. Keep the ordinary single-target write-count test.

## Builds on

[machine/exec.rs L1008](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/exec.rs#L1008) · [machine/exec.rs L2039](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/exec.rs#L2039) · [machine/exec.rs L2066](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/exec.rs#L2066) · [machine/exec.rs L2358](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/exec.rs#L2358) · [tests/shell/test_host.py L196](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/tests/shell/test_host.py#L196)
