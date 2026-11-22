# An explicit transfer target directory must be a directory

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

Copy or move with an explicit target directory refuses an absent or regular-file destination even with one source.

## The problem

The single-source branch can reinterpret an explicit directory argument as an ordinary destination file.

## Proposed changes

Keep the explicit-directory requirement through option parsing, destination lookup and transfer dispatch.

## Acceptance tests

Cover a missing path, a file and a directory. The first two receive no transfer requests and the valid directory receives the expected basename.

## Builds on

[programs/files.rs L519](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/files.rs#L519)
