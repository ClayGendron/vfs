# An in-place sed edit requires its requested backup

Draft, 2026-11-22. Priority finding from the shell review of `cbda2721`.

## The outcome wanted

A requested backup must succeed before the source file can be replaced.

## The problem

The backup and source replacement are independent writes. A refused backup records an error while leaving the source write in the queue.

## Proposed changes

Represent backup and replacement as dependent actions. Surface the backup failure and suppress its dependent replacement.

## Acceptance tests

Refuse the backup on a fake host. Assert the original survives and its write count is zero. On success, verify that the backup contains the original bytes.

## Builds on

[programs/sed.rs L1332](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/sed.rs#L1332) · [programs/mod.rs L320](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/mod.rs#L320)
