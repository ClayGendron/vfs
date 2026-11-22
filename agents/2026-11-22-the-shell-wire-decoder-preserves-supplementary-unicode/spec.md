# The shell wire decoder preserves supplementary Unicode

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

Equivalent raw UTF-8 and valid escaped JSON Unicode pairs decode to the same shell text.

## The problem

The JSON reader converts escaped UTF-16 code units independently. External encoders that escape supplementary characters can change source, names or paths.

## Proposed changes

Decode valid pairs as one scalar and reject malformed surrogate sequences consistently before dispatch.

## Acceptance tests

Round-trip a supplementary character as raw and escaped JSON in source and paths using a standard encoder. Check rejection of unpaired surrogate values.

## Builds on

[crates/vfs-shell-wasm/src/wire.rs L864](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell-wasm/src/wire.rs#L864)

See also [The shell's module crosses its boundary in binary](../2026-11-21-the-shell-crosses-its-boundary-in-binary/spec.md).
