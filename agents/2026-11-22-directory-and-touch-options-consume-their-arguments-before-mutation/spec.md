# Directory and touch options consume their arguments before mutation

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

A mode or reference-file argument is never treated as an extra path to create or touch.

## The problem

The mkdir mode and touch reference flags are accepted without honoring their argument boundaries.

## Proposed changes

Parse flag arity before collecting operands. Reject unsupported metadata requests before mutation, or implement the requested metadata where the host exposes it.

## Acceptance tests

Check missing and supplied option values and the ordinary no-option form. Inspect every path sent to the host as well as the resulting entries.

## Builds on

[programs/files.rs L736](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/files.rs#L736) · [programs/files.rs L781](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/files.rs#L781)
