# Unset preserves unrelated associative array keys

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

Deleting a literal associative key preserves every other element and the binding’s attributes.

## The problem

Unset handles special-looking subscripts before checking the array kind, which can discard the entire map.

## Proposed changes

Resolve the binding and array kind before interpreting the subscript. Preserve indexed-array whole-element behavior and attributes.

## Acceptance tests

Create an associative array with literal special keys and an unrelated sentinel. Remove present and absent keys and compare the entire declaration with Bash.

## Builds on

[machine/builtins.rs L1488](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/builtins.rs#L1488)

See also [The shell closes its known failures and counts depth by construct](../2026-11-21-the-shell-closes-its-known-failures/spec.md).
