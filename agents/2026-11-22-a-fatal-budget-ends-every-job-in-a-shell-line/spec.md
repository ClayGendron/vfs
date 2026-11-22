# A fatal budget ends every job in a shell line

Draft, 2026-11-22. Priority finding from the shell review of `cbda2721`.

## The outcome wanted

When any job spends a line-wide interpreter budget, the caller receives the fatal reason and no subsequent operation begins.

## The problem

The background scheduler converts a fatal interpreter condition into an ordinary job status and drops the flush result. The foreground can continue and the enclosing call can report success after an interpreter-level limit is spent. The separate Wasm fuel and memory limits still apply.

## Proposed changes

Latch the first fatal condition in shared execution state and stop polling jobs for new effects. Preserve ordinary background command exit statuses for wait.

## Acceptance tests

Under a small limit, test both foreground and background termination with a recording host. Assert the line status, reason and absence of later mutations.

## Builds on

[machine/exec.rs L219](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/exec.rs#L219) · [machine/exec.rs L256](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/exec.rs#L256) · [machine/io.rs L90](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/io.rs#L90)

See also [A line has a verb budget, a host sets the shell's budgets, and a cli call may only tighten them](../2026-11-21-a-line-has-a-verb-budget-and-cli-tightens-it/spec.md).
