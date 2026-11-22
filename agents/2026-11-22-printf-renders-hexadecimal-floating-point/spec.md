# Printf renders hexadecimal floating point

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

Lowercase and uppercase hexadecimal float conversions produce the corresponding Bash representation.

## The problem

These conversions currently select decimal scientific formatting.

## Proposed changes

Implement hexadecimal mantissa, binary exponent, precision and case handling for this conversion.

## Acceptance tests

Compare the emitted representation for an exactly representable finite value at default and explicit precision for both letter cases.

## Builds on

[machine/printf.rs L472](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/printf.rs#L472)

See also [The shell closes its known failures and counts depth by construct](../2026-11-21-the-shell-closes-its-known-failures/spec.md).
