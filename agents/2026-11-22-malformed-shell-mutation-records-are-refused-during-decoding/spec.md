# Malformed shell mutation records are refused during decoding

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

A missing required payload or unknown write mode produces a protocol error before any VFS mutation is dispatched.

## The problem

The wire decoder can assign fallback values to malformed mutation fields. The review identified this as defensive hardening for malformed messages.

## Proposed changes

Validate the required fields and enum variants before constructing a mutation request. Preserve a correctly encoded explicit empty payload.

## Acceptance tests

Give the decoder malformed records and a valid empty write. Assert that only the valid record reaches the recording host.

## Builds on

[crates/vfs-shell-wasm/src/wire.rs L569](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell-wasm/src/wire.rs#L569)

See also [The shell's module crosses its boundary in binary](../2026-11-21-the-shell-crosses-its-boundary-in-binary/spec.md).
