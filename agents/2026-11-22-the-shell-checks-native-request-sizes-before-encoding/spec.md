# The shell checks native request sizes before encoding

Draft, 2026-11-22. Priority finding from the shell review of `cbda2721`.

## The outcome wanted

An input outside the line’s configured allowances is rejected before native serialization creates proportional temporary buffers.

## The problem

The Python binding copies stdin and formats a complete wire document before entering the Wasm guest. Serialization and conversion can hold the GIL while unrelated callers wait.

## Proposed changes

Preflight source and input sizes at the native boundary, account for environment and wire buffers, and release the GIL around pure Rust conversion after safely owning the required inputs.

## Acceptance tests

Use small configured limits and conversion counters. Confirm rejection precedes encoding and check that an admitted request still produces the same guest input.

## Builds on

[crates/vfs-core/src/shell_binding.rs L79](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-core/src/shell_binding.rs#L79) · [crates/vfs-core/src/shell_binding.rs L99](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-core/src/shell_binding.rs#L99) · [crates/vfs-shell-wasm/src/wire.rs L391](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell-wasm/src/wire.rs#L391)

See also [A line has a verb budget, a host sets the shell's budgets, and a cli call may only tighten them](../2026-11-21-a-line-has-a-verb-budget-and-cli-tightens-it/spec.md).
