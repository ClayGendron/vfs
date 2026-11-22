# Copy and move expose the production occupied-target policy

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

Shell tests distinguish the VFS transfer contract from GNU replacement semantics and exercise occupied targets on both database engines.

## The problem

MemoryHost allows overwriting an occupied destination, including dropping a nonempty directory in one move path. The production database transfer rejects an occupied destination. The Python corpus sampler excludes program-tier cases and its engine test uses fresh destinations.

## Proposed changes

Keep the production refusal on an occupied transfer destination. Express the divergence in the shell conformance fixtures and align the reference host for VFS-specific tests. Preserve existing children of nonempty destinations.

## Acceptance tests

Run occupied-file and nonempty-directory cases on MemoryHost, SQLite and PostgreSQL. Inspect both trees, command status and VFS refusal. Keep fresh-destination successes covered.

## Builds on

[host/memory.rs L378](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/host/memory.rs#L378) · [host/memory.rs L416](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/host/memory.rs#L416) · [programs/files.rs L588](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/files.rs#L588) · [src/vfs/storage/backends/database/topology.py L188](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/src/vfs/storage/backends/database/topology.py#L188) · [tests/shell/test_host.py L104](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/tests/shell/test_host.py#L104) · [tests/shell/test_engines.py L64](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/tests/shell/test_engines.py#L64)
