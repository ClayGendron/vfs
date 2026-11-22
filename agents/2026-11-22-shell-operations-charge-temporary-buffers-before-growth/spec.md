# Shell operations charge temporary buffers before growth

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

Transient allocations in formatting, reading, translation, sed and captured substitutions observe the configured live-byte budget.

## The problem

Repeated printf formatting, file-backed read/mapfile, tr repeat expansion, multi-operand sed and process-substitution captures can allocate full temporaries first. Native embedders lack the independent Wasm memory ceiling.

## Proposed changes

Charge capacity before extending a buffer and release it when ownership ends. Stream output where possible. Count simultaneously retained operands and records, including temporary copies.

## Acceptance tests

Use small configured limits and modest inputs across printf, read, mapfile, tr, sed and process substitution. Record peak charged bytes and verify ordinary output at an adequate limit.

## Builds on

[machine/printf.rs L23](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/printf.rs#L23) · [machine/builtins.rs L455](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/builtins.rs#L455) · [machine/builtins.rs L582](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/builtins.rs#L582) · [programs/text.rs L1502](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/text.rs#L1502) · [programs/mod.rs L302](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/programs/mod.rs#L302) · [machine/exec.rs L1823](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/exec.rs#L1823)

See also [A line has a verb budget, a host sets the shell's budgets, and a cli call may only tighten them](../2026-11-21-a-line-has-a-verb-budget-and-cli-tightens-it/spec.md).
