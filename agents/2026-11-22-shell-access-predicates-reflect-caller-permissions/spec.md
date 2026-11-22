# Shell access predicates reflect caller permissions

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

Readability and writability tests answer for the admitted caller’s access to the path.

## The problem

The shell treats stat visibility as sufficient for positive access predicates. A readable or listable path may reject a write.

## Proposed changes

Carry the caller-aware access information needed by predicates through host stat or a dedicated authorized query. Respect masking and distinguish read from write access.

## Acceptance tests

Run predicates with read-only, writable and masked paths on the same mount. Compare answers with the applicable VFS permission decisions without writing as a probe.

## Builds on

[machine/test.rs L78](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/test.rs#L78) · [src/vfs/shell/host.py L408](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/src/vfs/shell/host.py#L408)
