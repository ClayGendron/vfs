# A failed Wasm restart has a single defined lifecycle outcome

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

An external host cannot unknowingly step a previous line after a failed attempt to replace it.

## The problem

A failed second start leaves the previous instance active. The Python product uses a fresh instance for each line.

## Proposed changes

Choose and document a precise transition for a repeated start on an active machine. Either reject the restart while preserving the active identity explicitly or invalidate it before processing a replacement.

## Acceptance tests

Exercise first start, repeated start, failed replacement, subsequent step and cancellation. Assert the externally visible state and which line can produce output after each transition.

## Builds on

[crates/vfs-shell-wasm/src/lib.rs L57](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell-wasm/src/lib.rs#L57) · [crates/vfs-shell-wasm/src/lib.rs L83](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell-wasm/src/lib.rs#L83)

See also [The shell's module crosses its boundary in binary](../2026-11-21-the-shell-crosses-its-boundary-in-binary/spec.md).
