# A shell deadline covers queued work and VFS verbs

Draft, 2026-11-22. Priority finding from the shell review of `cbda2721`.

## The outcome wanted

One deadline applies from line admission through the final host reply.

## The problem

Python snapshots the remaining duration before queueing construction. Rust adds it to a later clock reading after input conversion. During execution, a VFS verb can remain suspended beyond the deadline because Python awaits the verb without a timeout. Pending requests from a batch can also begin after expiry. A Wasm epoch check only runs when the guest is executing.

## Proposed changes

Carry the admitted deadline into construction and every host wait. Check the time remaining before dispatch, support cancellation during startup, and report the outcome of an already-committed mutation accurately.

## Acceptance tests

Use controlled queue and verb barriers. Advance a test clock at each barrier and assert timeout status and zero later dispatches. Cover an in-flight operation that had already committed.

## Builds on

[src/vfs/shell/host.py L244](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/src/vfs/shell/host.py#L244) · [src/vfs/shell/host.py L277](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/src/vfs/shell/host.py#L277) · [crates/vfs-core/src/shell_binding.rs L113](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-core/src/shell_binding.rs#L113)

See also [A line has a verb budget, a host sets the shell's budgets, and a cli call may only tighten them](../2026-11-21-a-line-has-a-verb-budget-and-cli-tightens-it/spec.md).
