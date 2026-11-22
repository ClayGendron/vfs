# The native binding validates guest output ranges before allocating

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

A malformed guest output range is refused before its claimed size drives a host-side allocation.

## The problem

The native return path allocates from a guest-reported length before checking the corresponding Wasm memory range. This is a boundary-hardening finding for malformed guest replies.

## Proposed changes

Validate pointer and length together against current linear memory and the host wire allowance before copying. Use the existing internal-error result for an invalid guest response.

## Acceptance tests

At the decoder boundary inject a valid small range, an out-of-bounds range and an invalid length. Check error classification and that host allocation follows validation.

## Builds on

[crates/vfs-core/src/shell_binding.rs L510](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-core/src/shell_binding.rs#L510)

See also [The shell's module crosses its boundary in binary](../2026-11-21-the-shell-crosses-its-boundary-in-binary/spec.md).
