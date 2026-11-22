# Expanded arithmetic respects the configured depth

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

Source arithmetic and expressions materialized during execution both obey the caller’s arithmetic nesting allowance.

## The problem

Arithmetic parsing at execution time receives a fixed depth even when the caller supplied a smaller parse limit.

## Proposed changes

Carry the configured depth into runtime expression parsing and report exhaustion with the established parse or execution classification for that entry point.

## Acceptance tests

Check an ordinary expression at its exact configured boundary, one beyond it, and the same expression read from a variable.

## Builds on

[machine/arith.rs L43](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/arith.rs#L43) · [syntax/arith.rs L61](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/syntax/arith.rs#L61)

See also [A line has a verb budget, a host sets the shell's budgets, and a cli call may only tighten them](../2026-11-21-a-line-has-a-verb-budget-and-cli-tightens-it/spec.md).
