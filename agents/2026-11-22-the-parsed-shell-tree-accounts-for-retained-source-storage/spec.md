# The parsed shell tree accounts for retained source storage

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

Function definitions and line offsets have a measurable live footprint within the logical tree budget.

## The problem

Nested function definitions retain overlapping source copies and the line offset table can be rebuilt or held outside tree accounting.

## Proposed changes

Use spans into shared source where possible, retain one offset table and account for allocations while building the tree.

## Acceptance tests

Measure the footprint for nested ordinary definitions and multiline input. Verify the recorded size tracks retained storage and a small allowance refuses admission.

## Builds on

[syntax/parser.rs L1078](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/syntax/parser.rs#L1078) · [syntax/ast.rs L175](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/syntax/ast.rs#L175) · [machine/mod.rs L369](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/mod.rs#L369)

See also [The shell closes its known failures and counts depth by construct](../2026-11-21-the-shell-closes-its-known-failures/spec.md).
