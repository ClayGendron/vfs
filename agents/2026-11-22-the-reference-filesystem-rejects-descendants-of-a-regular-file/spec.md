# The reference filesystem rejects descendants of a regular file

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

Recursive directory creation on MemoryHost respects the kind of every ancestor.

## The problem

Recursive mkdir on MemoryHost can add a directory below a regular-file ancestor. A test can pass with a tree the production backend would refuse.

## Proposed changes

Validate existing ancestors before inserting inaccessible descendants. Return the proper non-directory error while preserving valid existing entries.

## Acceptance tests

Compare a file ancestor, a directory ancestor and a missing directory chain. Assert the resulting tree and status against the VFS hosts.

## Builds on

[host/memory.rs L87](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/host/memory.rs#L87) · [host/memory.rs L342](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/host/memory.rs#L342)
