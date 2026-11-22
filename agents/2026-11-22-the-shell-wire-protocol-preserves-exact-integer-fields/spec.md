# The shell wire protocol preserves exact integer fields

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

File sizes, offsets and supported budget values retain their exact integer values when exchanged through the wire protocol.

## The problem

JSON numbers are converted through a floating-point representation before integer fields are recovered, which rounds large exact values.

## Proposed changes

Parse integer fields directly with checked range conversion for the declared type. Preserve the rules for fields that genuinely take fractional values.

## Acceptance tests

Round-trip adjacent large u64 values and field boundaries with standard JSON. Check out-of-range and fractional inputs for integer fields.

## Builds on

[crates/vfs-shell-wasm/src/wire.rs L822](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell-wasm/src/wire.rs#L822)

See also [The shell's module crosses its boundary in binary](../2026-11-21-the-shell-crosses-its-boundary-in-binary/spec.md).
