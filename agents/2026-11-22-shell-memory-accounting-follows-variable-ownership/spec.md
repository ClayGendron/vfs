# Shell memory accounting follows variable ownership

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

Forked variables, scoped assignments and associative bucket storage are reflected in live shell memory until their final owner releases them.

## The problem

Forked variable tables are cloned without charging, then child changes can release charges still owed by the parent. Scope removal can leave charges for values already discarded. Associative maps also allocate 1,024 bucket headers whose cost is omitted from their footprint.

## Proposed changes

Track shared or copied variable storage explicitly. Charge allocated capacity including associative buckets, and release scope-owned allocations on every return path.

## Acceptance tests

Measure live usage before a fork, after independent assignment and after scope exit. Empty and single-entry maps incur their actual storage cost, and repeated completed calls return to baseline.

## Builds on

[machine/shell.rs L344](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/shell.rs#L344) · [machine/exec.rs L1164](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/exec.rs#L1164) · [machine/exec.rs L1460](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/exec.rs#L1460) · [machine/vars.rs L19](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/crates/vfs-shell/src/machine/vars.rs#L19)

See also [A line has a verb budget, a host sets the shell's budgets, and a cli call may only tighten them](../2026-11-21-a-line-has-a-verb-budget-and-cli-tightens-it/spec.md).
