# Invalid arithmetic subscripts leave arrays intact

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

An invalid array subscript yields a diagnostic without falling back to element zero.

## The problem

Several assignment and removal builtin paths discard arithmetic errors and use index zero instead.

## Proposed changes

Use a shared fallible resolver for indexed writes and removals. Abort the requested mutation on an invalid subscript.

## Acceptance tests

Exercise each affected builtin with an invalid subscript and a sentinel at zero. Check status and every element afterward.

## Builds on

[machine/builtins.rs L465](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/builtins.rs#L465) · [machine/builtins.rs L1364](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/builtins.rs#L1364)

See also [The shell closes its known failures and counts depth by construct](../2026-11-21-the-shell-closes-its-known-failures/spec.md).
