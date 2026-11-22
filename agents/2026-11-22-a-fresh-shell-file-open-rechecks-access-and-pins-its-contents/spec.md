# A fresh shell file open rechecks access and pins its contents

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

A new logical open passes through the router, and all chunks of one admitted open refer to one file version.

## The problem

The per-line cache key is a path. A new offset-zero read can hit a completed read’s body without asking the router again. A concurrent edit or revocation is invisible on that reopen. Exposure is limited to data already obtained by the same authority in that line. Conversely, eviction can cause a later chunk to come from a newer version.

## Proposed changes

Key read state by logical reader and pinned version. On eviction, reacquire the same version or report a read error. Recheck current authority at a subsequent open.

## Acceptance tests

Use two logical opens across a version or permission change. Verify the second open follows current routing, and evict a reader midway to check for mixed-version output.

## Builds on

[src/vfs/shell/host.py L375](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/src/vfs/shell/host.py#L375) · [machine/exec.rs L1967](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/exec.rs#L1967) · [machine/files.rs L108](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/files.rs#L108)
