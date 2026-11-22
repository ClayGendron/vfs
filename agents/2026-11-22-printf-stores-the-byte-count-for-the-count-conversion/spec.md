# Printf stores the byte count for the count conversion

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

The count conversion consumes its variable argument and stores the number of emitted bytes.

## The problem

The formatter currently omits the assignment and can leave the argument available to later conversions.

## Proposed changes

Use checked variable assignment for the count and advance the argument cursor exactly once.

## Acceptance tests

Check the stored count after multibyte output and the value consumed by the following conversion. Include a readonly destination.

## Builds on

[machine/printf.rs L206](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/printf.rs#L206)

See also [The shell closes its known failures and counts depth by construct](../2026-11-21-the-shell-closes-its-known-failures/spec.md).
