# A refused file chunk stays a read error

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

A stream consumer can distinguish a refused later chunk from clean end of file.

## The problem

After the first file chunk, any non-data host reply is converted to an empty final chunk. The consumer can return success on truncated input.

## Proposed changes

Propagate typed errors from the descriptor into each consumer, retaining any bytes already read and the existing evidence policy.

## Acceptance tests

Deliver one successful chunk followed by a refusal. Check command status and the accepted prefix, then repeat with a genuine EOF that must succeed.

## Builds on

[machine/files.rs L119](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/files.rs#L119) · [programs/mod.rs L175](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/mod.rs#L175)
