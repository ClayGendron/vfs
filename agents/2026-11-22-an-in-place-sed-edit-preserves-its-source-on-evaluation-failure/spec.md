# An in-place sed edit preserves its source on evaluation failure

Draft, 2026-11-22. Priority finding from the shell review of `cbda2721`.

## The outcome wanted

A file under edit retains its original bytes when evaluation of that file fails.

## The problem

The interpreter queues the current file’s replacement before checking the evaluation result. The adapter applies the queued writes even on an error status.

## Proposed changes

Stage the replacement per file. Publish it only on a successful completion, including a valid early quit. Retain completed edits of earlier independent files.

## Acceptance tests

Use an injected evaluation error after ordinary output has been buffered. Compare the original bytes and replacement count, and cover an explicit successful quit separately.

## Builds on

[programs/sed.rs L1332](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/sed.rs#L1332) · [programs/sed.rs L1356](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/sed.rs#L1356) · [programs/mod.rs L320](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/mod.rs#L320)
