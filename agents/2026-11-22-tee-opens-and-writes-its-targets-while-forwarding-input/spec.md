# Tee opens and writes its targets while forwarding input

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

Named tee destinations receive the appropriate prefix as the stream advances.

## The problem

It buffers input, forwards stdout, then opens and writes destinations after EOF. Early downstream termination can leave the destination untouched.

## Proposed changes

Open destinations before reading and write charged, bounded chunks to active destinations. Avoid accumulating a full copy in the stdout-only case.

## Acceptance tests

Inspect file open and write order on a finite stream and when a downstream reader closes early. Verify per-destination failures, accepted bytes and memory usage.

## Builds on

[programs/text.rs L1703](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/text.rs#L1703)
