# Head preserves the unread suffix on a shared file descriptor

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

After head takes a prefix, the next reader of the same regular-file descriptor sees exactly the remaining bytes.

## The problem

The command advances the shared file reader by a chunk and then keeps only the requested prefix. A later reader can lose the unread suffix.

## Proposed changes

Consume only the selected prefix or return the unused suffix to state shared by all duplicates of the descriptor.

## Acceptance tests

Use consecutive readers on one redirected regular file. Check byte and line modes, a boundary in the middle of a chunk and a request that reaches EOF.

## Builds on

[programs/text.rs L287](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/text.rs#L287) · [programs/mod.rs L168](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/mod.rs#L168)
