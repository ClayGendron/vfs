# Descriptor predicates use the live descriptor table

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

A predicate for a shell descriptor path reflects whether that descriptor is open.

## The problem

The special-path predicate can recognize the descriptor prefix without checking the descriptor itself, while opening the path checks the table.

## Proposed changes

Use shared resolution for descriptor existence and open operations.

## Acceptance tests

Check an open, closed and never-opened descriptor in the same shell. Compare the predicate with the descriptor’s availability.

## Builds on

[machine/test.rs L32](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/test.rs#L32)

See also [The shell closes its known failures and counts depth by construct](../2026-11-21-the-shell-closes-its-known-failures/spec.md).
