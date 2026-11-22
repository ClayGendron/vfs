# Array input builtins honor readonly bindings

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

read and mapfile honor readonly flags and target references before replacing an array.

## The problem

The array forms write directly into the selected variable through a setter that does not apply the normal readonly and nameref checks.

## Proposed changes

Resolve and validate the eventual destination through the assignment rules, including readonly targets reached by reference.

## Acceptance tests

Exercise read and mapfile on writable and readonly destinations. Check the diagnostic and original contents. Include the existing readonly mapfile case.

## Builds on

[machine/builtins.rs L834](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/builtins.rs#L834) · [machine/builtins.rs L947](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/builtins.rs#L947)

See also [The shell closes its known failures and counts depth by construct](../2026-11-21-the-shell-closes-its-known-failures/spec.md).
