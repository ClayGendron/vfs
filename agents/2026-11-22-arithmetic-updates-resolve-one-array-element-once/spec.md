# Arithmetic updates resolve one array element once

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

An arithmetic update preserves unrelated array entries and evaluates an indexed lvalue once.

## The problem

An indexed update can evaluate its subscript twice, valid negative indices can be written literally, and unindexed arithmetic on an associative map can replace the map with a scalar.

## Proposed changes

Canonicalize the lvalue before reading or writing. Normalize relative indices against the indexed array and preserve an associative map when updating its implicit zero key.

## Acceptance tests

Compare the final array and subscript counter with Bash for a side-effectful index, a valid negative index and an implicit associative element update.

## Builds on

[machine/arith.rs L103](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/arith.rs#L103) · [machine/arith.rs L165](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/arith.rs#L165) · [machine/arith.rs L229](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/arith.rs#L229)

See also [The shell closes its known failures and counts depth by construct](../2026-11-21-the-shell-closes-its-known-failures/spec.md).
