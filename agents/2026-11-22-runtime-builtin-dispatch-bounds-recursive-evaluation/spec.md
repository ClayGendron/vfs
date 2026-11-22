# Runtime builtin dispatch bounds recursive evaluation

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

Argument-based test expressions and repeated builtin dispatch stay within the configured execution depth in native and Wasm hosts.

## The problem

Both paths can nest calls while evaluating expanded arguments. The parser’s source nesting count does not cover this later work.

## Proposed changes

Use iterative dispatch for wrappers and a bounded evaluator for recursive test expressions. Surface resource refusal through the shell result.

## Acceptance tests

Use small limits and ordinary argument lists immediately on either side of each boundary. Confirm the native and Wasm entry points return a classified result.

## Builds on

[machine/test.rs L491](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/test.rs#L491) · [machine/builtins.rs L245](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/builtins.rs#L245) · [machine/builtins.rs L2075](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/builtins.rs#L2075)

See also [A line has a verb budget, a host sets the shell's budgets, and a cli call may only tighten them](../2026-11-21-a-line-has-a-verb-budget-and-cli-tightens-it/spec.md).
