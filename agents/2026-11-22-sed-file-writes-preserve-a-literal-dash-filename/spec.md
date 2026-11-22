# Sed file writes preserve a literal dash filename

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

A dash named by sed’s file-write instruction receives file output, with stdout preserving its own contents.

## The problem

The common file writer treats a dash name as stdout regardless of the calling utility’s operand semantics.

## Proposed changes

Resolve stream aliases at the caller. Keep the ordinary file-writing primitive literal.

## Acceptance tests

With a fixture directory, compare a sed write to the dash filename with GNU sed. Check file contents and stdout separately and retain stdin-alias behavior where appropriate.

## Builds on

[programs/mod.rs L242](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/mod.rs#L242)
