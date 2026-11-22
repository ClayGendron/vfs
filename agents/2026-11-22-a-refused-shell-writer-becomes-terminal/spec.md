# A refused shell writer becomes terminal

Draft, 2026-11-22. Priority finding from the shell review of `cbda2721`.

## The outcome wanted

Once a descriptor’s write fails it emits no further chunks and preserves the first error.

## The problem

The writer consumes its opening mode before learning the result and can later switch to append after a refusal. A concurrent creator can then receive bytes from the failed writer.

## Proposed changes

Commit the opening transition only on success. Make a refusal terminal for that writer, including later flushes.

## Acceptance tests

Use a host double returning an exists conflict on an opening chunk. Assert zero follow-up writes, identity of the existing content, and a failing command status. Cover a refusal after one accepted chunk.

## Builds on

[machine/files.rs L193](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/files.rs#L193) · [machine/shell.rs L415](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/shell.rs#L415)
